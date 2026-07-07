// API client — the ONLY module that knows backend URLs, request/response shapes,
// and error mapping (docs/ARCHITECTURE.md). Components/hooks call these functions,
// never fetch() directly.

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export interface User {
  id: number;
  username: string;
  name: string;
  avatar_url?: string | null;
}

/** Enriched profile for the account panel (spec-04): user + resolved dept/role + created. */
export interface Profile extends User {
  department_name: string | null;
  role_name: string | null;
  created_at: string;
}

/** Resolve a server-relative asset path (e.g. an avatar `/static/...`) to a full URL the
 *  browser can load from the API origin. Returns null for an empty/missing path. */
export function assetUrl(path?: string | null): string | null {
  if (!path) return null;
  return /^https?:\/\//i.test(path) ? path : `${BASE_URL}${path}`;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

/** Normalized API error so the UI can branch on kind without parsing strings. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number, // 0 = network/unreachable
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }

  get isAuth(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let resp: Response;
  try {
    // Let the browser set the multipart boundary itself for FormData (avatar upload);
    // force JSON otherwise.
    const isForm = init.body instanceof FormData;
    resp = await fetch(`${BASE_URL}${path}`, {
      ...init,
      // Send/receive the httpOnly refresh cookie (spec-03). Requires the backend to
      // allow credentials with a specific origin (never "*").
      credentials: "include",
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.", 0);
  }

  if (!resp.ok) {
    const detail = await safeDetail(resp);
    throw new ApiError(detail ?? `Request failed (${resp.status}).`, resp.status);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

async function safeDetail(resp: Response): Promise<string | null> {
  try {
    const body = await resp.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  } catch {
    /* non-JSON error body */
  }
  return null;
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function authed<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  try {
    return await request<T>(path, {
      ...init,
      headers: { ...authHeader(token), ...(init.headers ?? {}) },
    });
  } catch (err) {
    // Access token expired? Refresh once (silently) and retry the original request.
    if (err instanceof ApiError && err.isAuth) {
      const fresh = await refreshAccessToken();
      if (fresh) {
        return await request<T>(path, {
          ...init,
          headers: { ...authHeader(fresh), ...(init.headers ?? {}) },
        });
      }
    }
    throw err;
  }
}

// --- Silent refresh ---------------------------------------------------------
// A single shared in-flight refresh so a burst of concurrent 401s triggers at most
// ONE /refresh call (no refresh storm). Callbacks let AuthContext stay in sync.

let refreshInFlight: Promise<string | null> | null = null;
let onAccessToken: (token: string | null) => void = () => {};
let onSessionEnded: () => void = () => {};

/** AuthContext registers how to receive a rotated access token / a dead session. */
export function registerAuthCallbacks(cb: {
  onAccessToken: (token: string | null) => void;
  onSessionEnded: () => void;
}): void {
  onAccessToken = cb.onAccessToken;
  onSessionEnded = cb.onSessionEnded;
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = api
      .refresh()
      .then((res) => {
        onAccessToken(res.access_token);
        return res.access_token;
      })
      .catch(() => {
        onSessionEnded();
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// --- RBAC admin shapes ------------------------------------------------------

export type Scope = "own" | "department" | "all";

export interface ModuleDef {
  key: string;
  label: string;
}

export interface Department {
  id: number;
  name: string;
  code: string;
  description?: string | null;
  parent_id?: number | null;
  head_user_id?: number | null;
  head_name?: string | null;
  /** This department's own role/user counts. */
  role_count?: number;
  user_count?: number;
  /** Branch-rolled-up counts (department + every descendant) — PBI-4001. */
  total_role_count?: number;
  total_user_count?: number;
  /** Org tier tag + its head-title label (spec-06 / PBI-4009). Null = untagged. */
  level_id?: number | null;
  head_title?: string | null;
}

/** A tier in the org-level catalog (spec-06 / PBI-4009). */
export interface UnitLevel {
  id: number;
  name: string;
  rank: number;
  head_title: string;
}

/** A staff member of a department (PBI-4001 detail panel). */
export interface DepartmentMember {
  id: number;
  code?: string | null;
  name: string;
  username: string;
  role_name?: string | null;
  is_active: boolean;
  is_head: boolean;
}

/** A node in a department's delete-preview subtree (spec-05). */
export interface DepartmentSubtreeRow {
  id: number;
  name: string;
  code: string;
}

export interface UserBrief {
  id: number;
  name: string;
  username: string;
}

export interface UserRow {
  id: number;
  /** System-generated employee code (NV001, NV002…); may be null on legacy rows. */
  code: string | null;
  name: string;
  username: string;
  department_id: number | null;
  department_name: string | null;
  role_id: number | null;
  role_name: string | null;
  is_active: boolean;
}

export interface AuditRow {
  id: number;
  actor_user_id: number | null;
  actor_name: string | null;
  action: string;
  target: string;
  detail: string;
  created_at: string;
}

/** Current user's CRUD flags on one module (spec-09 — frontend action gating). */
export interface ModuleCapability {
  module_key: string;
  can_read: boolean;
  can_create: boolean;
  can_update: boolean;
  can_delete: boolean;
  scope: Scope;
  // Quyền chi tiết (Cách B).
  can_reassign: boolean;
  can_export: boolean;
  can_view_debt: boolean;
  can_approve: boolean;
  can_manage_status: boolean;
  can_reset_password: boolean;
  can_lock: boolean;
  can_revoke_sessions: boolean;
  can_assign_role: boolean;
  can_transfer: boolean;
  can_set_head: boolean;
  can_requote: boolean;
  can_manage_price: boolean;
  can_cancel: boolean;
  can_manage_permissions: boolean;
  can_clone: boolean;
  can_toggle_active: boolean;
  can_reparent: boolean;
}

/** A live login session (active refresh token) for the admin user-detail view (spec-08). */
export interface Session {
  id: number;
  user_agent: string | null;
  created_at: string;
  expires_at: string;
}

export interface Role {
  id: number;
  name: string;
  department_id: number;
}

export interface PermissionRow {
  module_key: string;
  can_read: boolean;
  can_create: boolean;
  can_update: boolean;
  can_delete: boolean;
  scope: Scope;
  // Quyền chi tiết (Cách B).
  can_reassign: boolean;
  can_export: boolean;
  can_view_debt: boolean;
  can_approve: boolean;
  can_manage_status: boolean;
  can_reset_password: boolean;
  can_lock: boolean;
  can_revoke_sessions: boolean;
  can_assign_role: boolean;
  can_transfer: boolean;
  can_set_head: boolean;
  can_requote: boolean;
  can_manage_price: boolean;
  can_cancel: boolean;
  can_manage_permissions: boolean;
  can_clone: boolean;
  can_toggle_active: boolean;
  can_reparent: boolean;
}

// --- Khách hàng (CRM), spec-06 ----------------------------------------------

/** Behavioural tier derived from real orders (never an invented master field). */
export type CustomerTier = "new" | "loyal" | "partner" | "regular";

export interface CustomerRow {
  id: number;
  code: string;
  name: string;
  tax_code: string | null;
  phone: string | null;
  email?: string | null;
  address?: string | null;
  contact_name?: string | null;
  credit_limit: number;
  sale_user_id: number | null;
  sale_name: string | null;
  status: string;
  created_at?: string | null;
  /** Công nợ chỉ-đọc: null + no_ar_module=true until Công nợ (SEAM-16) is built. */
  receivable: number | null;
  no_ar_module: boolean;
  /** Derived from real orders. */
  tier: CustomerTier;
  revenue_12m: number;
  orders_total: number;
  last_order_at: string | null;
}

/** List header KPI strip — rolled up over the whole scoped book from real orders. */
export interface CustomerKpis {
  total_customers: number;
  loyal_count: number;
  new_this_month: number;
  avg_order_value: number;
}

export interface CustomerListOut {
  items: CustomerRow[];
  total: number;
  page: number;
  size: number;
  kpis: CustomerKpis;
}

// --- CRM-360 Object-page dashboard + history (real data) --------------------

export interface MonthPoint {
  month: string;
  label: string;
  revenue: number;
  orders: number;
}
export interface ProductSlice {
  label: string;
  revenue: number;
  orders: number;
}
export interface HeatCell {
  month_index: number;
  weekday: number;
  count: number;
}
export interface CustomerDashboard {
  revenue_12m: number;
  orders_12m: number;
  avg_order_value: number | null;
  orders_total: number;
  quotes_total: number;
  win_rate_pct: number | null;
  first_order_at: string | null;
  last_order_at: string | null;
  tier: CustomerTier;
  months: MonthPoint[];
  product_mix: ProductSlice[];
  heatmap: HeatCell[];
  has_data: boolean;
  receivable: ReceivableCard;
}
export interface OrderHistoryRow {
  id: number;
  order_no: string;
  status: string;
  order_kind: string;
  summary: string;
  total: number | null;
  created_at: string;
}
export interface QuoteHistoryRow {
  id: number;
  code: string;
  version: number;
  status: string;
  total: number | null;
  valid_until: string | null;
  created_at: string;
}

export interface CustomerAuditRow {
  at: string;
  kind: "profile" | "order" | "quote";
  action: string;
  title: string;
  detail: string;
  actor_name: string | null;
  ref_type: "order" | "quotation" | null;
  ref_id: number | null;
}

/** A customer carried across a cross-module navigation (CRM → Báo giá / Đơn hàng) so the
 *  target screen opens pre-pinned to the right customer — never an ID typed by hand. */
export interface PinnedCustomer {
  id: number;
  code: string;
  name: string;
  tax_code: string | null;
}

/** Points at an existing customer that already carries the submitted MST (soft warn). */
export interface DuplicateRef {
  id: number;
  code: string;
  name: string;
}

export interface CustomerCreateOut {
  customer: CustomerRow;
  duplicate: DuplicateRef | null;
}

/** The read-only Công nợ card. available=false + message → "Chưa có phân hệ Công nợ". */
export interface ReceivableCard {
  available: boolean;
  credit_limit: number;
  balance: number | null;
  usage_pct: number | null;
  over_limit: boolean | null;
  message: string | null;
}

export interface CustomerDetailOut {
  customer: CustomerRow;
  receivable: ReceivableCard;
}

export interface SaleOption {
  id: number;
  name: string;
}

export interface CustomerInput {
  name: string;
  tax_code: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  contact_name: string | null;
  credit_limit: number;
  sale_user_id: number | null;
  /** Only sent on update (create defaults to active). */
  status?: string;
}

export interface CustomerListParams {
  q?: string;
  sale?: number | null;
  tier?: string | null;
  status?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Sản phẩm in (Product catalog), spec-07 --------------------------------

export interface ProductRow {
  id: number;
  code: string;
  name: string;
  product_type: string;
  binding_type: string | null;
  component_count: number;
}

export interface ProductListOut {
  items: ProductRow[];
  total: number;
  page: number;
  size: number;
}

export interface ComponentOut {
  id: number;
  sequence: number;
  component_type: string;
  paper_master_id: number | null;
  paper_display: string | null;
  colors_front: number;
  colors_back: number;
  page_count: number;
  finished_w: number;
  finished_h: number;
  bleed: number;
  grain_direction: string | null;
}

export interface ProductDetailOut {
  id: number;
  code: string;
  name: string;
  product_type: string;
  binding_type: string | null;
  note: string | null;
  components: ComponentOut[];
}

export interface ComponentInput {
  component_type: string;
  paper_master_id: number | null;
  colors_front: number;
  colors_back: number;
  page_count: number;
  finished_w: number;
  finished_h: number;
  bleed: number;
  grain_direction: string | null;
  sequence: number;
}

export interface ProductInput {
  name: string;
  product_type: string;
  binding_type: string | null;
  note: string | null;
  components: ComponentInput[];
}

export interface EnumOption {
  value: string;
  label: string;
}

export interface ProductEnumsOut {
  product_types: EnumOption[];
  binding_types: EnumOption[];
  component_types: EnumOption[];
  grain_directions: EnumOption[];
}

/** Paper picker state (SEAM-03): available=false + message when Danh mục Giấy is not built. */
export interface PaperPickerOut {
  available: boolean;
  message: string | null;
  items: Array<Record<string, unknown>>;
}

export interface ProductListParams {
  q?: string;
  product_type?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Tính giá (Costing), spec-08 -------------------------------------------

export interface CostingRow {
  id: number;
  code: string;
  product_id: number | null;
  qty_final: number;
  paper_option_count: number;
  status: string;
  /** Giá vốn tổng — null tại P0 (cần SEAM-07..12); UI hiện "—" chứ không số giả. */
  total_cost: number | null;
}

export interface CostingListOut {
  items: CostingRow[];
  total: number;
  page: number;
  size: number;
}

export interface PaperOptionOut {
  id: number;
  sheet_paper_master_id: number | null;
  paper_display: string | null;
  sheet_w: number;
  sheet_h: number;
  pieces_per_sheet: number;
  grain_locked: boolean;
  selected: boolean;
}

export interface OperationOut {
  id: number;
  sequence: number;
  name: string;
  execution_mode: string;
}

export interface CostingDetailOut {
  id: number;
  code: string;
  product_id: number | null;
  qty_final: number;
  status: string;
  note: string | null;
  paper_options: PaperOptionOut[];
  operations: OperationOut[];
}

export interface PaperOptionInput {
  sheet_paper_master_id: number | null;
  sheet_w: number;
  sheet_h: number;
  pieces_per_sheet: number;
  grain_locked: boolean;
  selected: boolean;
}

export interface OperationInput {
  name: string;
  execution_mode: string;
  sequence: number;
}

export interface CostingInput {
  product_id: number | null;
  qty_final: number;
  note: string | null;
  status: string | null;
  paper_options: PaperOptionInput[];
  operations: OperationInput[];
}

export interface CostingEnumsOut {
  statuses: EnumOption[];
  execution_modes: EnumOption[];
}

export interface EstimateWarning {
  severity: "warning" | "blocking_error" | "info";
  code: string;
  message: string;
  source_type?: string | null;
  source_id?: number | null;
}

export interface EstimateCostLineRow {
  id: number;
  category: string;
  description: string;
  source_type?: string | null;
  source_id?: number | null;
  source_snapshot_json?: Record<string, any> | null;
  calculation_snapshot_json?: Record<string, any> | null;
  quantity: number;
  unit: string;
  unit_cost: number;
  setup_cost: number;
  min_charge_applied: boolean;
  total_cost: number;
  note?: string | null;
}

export interface EstimateOptionRow {
  id: number;
  quantity: number;
  total_cost: number;
  warnings_json?: EstimateWarning[];
  can_create_quote?: boolean;
  blocking_error_count?: number;
  warning_count?: number;
  cost_lines?: EstimateCostLineRow[];
}

export interface EstimateDetail {
  id: number;
  estimate_number: string;
  customer_id: number | null;
  product_type: string;
  product_name: string;
  status: string;
  input_spec_json: Record<string, any>;
  quantity_list_json: number[];
  created_by: number | null;
  locked_at?: string | null;
  version?: number;
  parent_id?: number | null;
  superseded_by_id?: number | null;
  created_at: string;
  updated_at: string;
  options: EstimateOptionRow[];
}

export interface EstimateRow {
  id: number;
  estimate_number: string;
  product_type: string;
  product_name: string;
  status: string;
  quantity_list_json: number[];
  total_cost_min: number | null;
  total_cost_max: number | null;
  warnings_count: number;
  blocking_error_count: number;
  created_at: string;
  updated_at?: string | null;
  // Field hiển thị 2 tầng (backend cũ chưa trả — đều optional)
  customer_id?: number | null;
  customer_name?: string | null;
  spec_summary?: string | null;
  machine_type?: string | null;
  unit_cost_min?: number | null;
  created_by_name?: string | null;
}

export interface EstimateStats {
  total: number;
  draft: number;
  calculated: number;
  blocking: number;
}

export interface EstimateListOut {
  items: EstimateRow[];
  total: number;
  page: number;
  size: number;
}

/** Live preview (không lưu) — sidebar Tính giá hiện giá vốn tức thời khi gõ form. */
export interface EstimatePreviewLine {
  category: string;
  description: string;
  total_cost: number;
}

export interface EstimatePreviewOut {
  total_cost: number;
  cost_lines: EstimatePreviewLine[];
  warnings: { severity: string; code: string; message: string }[];
}

export interface EstimateInput {
  product_type: string;
  product_name: string;
  quantity_list: number[];
  input_spec: Record<string, any>;
  customer_id?: number | null;
  status?: string;
}


/** Paper-cost picker state (SEAM-07): available=false + message when Danh mục Giấy is not built. */
export interface PaperCostPickerOut {
  available: boolean;
  message: string | null;
  items: Array<Record<string, unknown>>;
}

/** Product read state (SEAM-11): available=false + message when Sản phẩm chưa expose ProductRead. */
export interface ProductPickerOut {
  available: boolean;
  message: string | null;
  product: Record<string, unknown> | null;
}

export interface SuggestPiecesOut {
  pieces: number;
  message: string | null;
}

export interface CostingListParams {
  q?: string;
  product_id?: number | null;
  status?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Báo giá (Quotation), spec-09 --------------------------------------------

export interface QuotationRow {
  id: number;
  code: string;
  version: number;
  customer_id: number | null;
  customer_name: string | null;
  total: number | null;
  status: string;
  valid_until: string | null;
  // Field hiển thị 2 tầng (đều có default phía backend)
  version_count?: number;
  sent_at?: string | null;
  margin_percent?: number | null;
  estimate_refs?: string[];
  product_summary?: string | null;
  updated_at?: string | null;
  salesperson_name?: string | null;
}

export interface QuotationListOut {
  items: QuotationRow[];
  total: number;
  page: number;
  size: number;
}

export interface QuotationStats {
  total: number;
  draft: number;
  sent: number;
  accepted: number;
  rejected: number;
  expired: number;
  converted_to_order: number;
  cancelled: number;
  need_action: number;
}

/** 1 phiếu tính giá + các mức SL được pick vào báo giá. */
export interface QuotePick {
  estimate_id: number;
  option_ids: number[];
}

export interface CustomerDisplay {
  customer_id: number;
  name: string;
  tax_code: string | null;
  credit_status_display: string;
}

export interface VersionRow {
  id: number;
  version: number;
  status: string;
  total: number | null;
  created_at: string;
  change_reason?: string | null;
}

export interface QuoteItemDetail {
  id: number;
  estimate_id?: number | null;
  estimate_number?: string | null;
  estimate_option_id: number | null;
  line_no: number;
  product_type: string;
  product_name: string;
  product_spec_text: string | null;
  quantity: number;
  unit: string;
  total_cost_snapshot: number;
  margin_percent: number;
  selling_price: number;
  unit_price: number;
  discount_amount: number;
  vat_percent: number;
  vat_amount: number;
  final_amount: number;
  note: string | null;
}

export interface QuotationDetail {
  id: number;
  code: string;
  version: number;
  customer_id: number | null;
  customer: CustomerDisplay | null;
  estimate_id: number | null;
  valid_until: string | null;
  status: string;
  cancel_reason: string | null;
  payment_terms: string | null;
  delivery_terms: string | null;
  delivery_address: string | null;
  customer_note: string | null;
  internal_note: string | null;
  
  // Financial snapshot totals
  total_cost: number;
  subtotal_amount: number;
  discount_amount: number;
  vat_amount: number;
  total: number;
  
  allowed_transitions: string[];
  can_approve: boolean;
  versions: VersionRow[];
  items: QuoteItemDetail[];
}

export interface QuotationInput {
  customer_id: number | null;
  estimate_id?: number | null;
  selected_option_ids?: number[] | null;
  /** Đường đa phiếu: mỗi pick = 1 phiếu tính giá + option đã tick. Ưu tiên nếu có. */
  picks?: QuotePick[] | null;
  /** Gói biên áp chung khi tạo (per dòng chỉnh sau). */
  margin_percent?: number | null;
  valid_until: string | null;
  payment_terms: string | null;
  delivery_terms: string | null;
  delivery_address: string | null;
  customer_note: string | null;
  internal_note: string | null;
}

export interface QuoteItemUpdateInput {
  id: number;
  margin_percent: number;
  manual_selling_price?: number | null;
  manual_unit_price?: number | null;
  discount_amount?: number;
  discount_percent?: number;
  vat_percent?: number;
  rounding?: string;
  note?: string | null;
}

export interface QuotationUpdateInput {
  customer_id: number | null;
  valid_until: string | null;
  payment_terms: string | null;
  delivery_terms: string | null;
  delivery_address: string | null;
  customer_note: string | null;
  internal_note: string | null;
  items: QuoteItemUpdateInput[] | null;
}

export interface QuotationEnumsOut {
  statuses: EnumOption[];
}

/** Một mức số lượng (bậc SL) của Tính giá được tham chiếu. */
export interface CostingQtyOption {
  id: number;
  quantity: number;
  total_cost: number;
  margin_percent: number;
  selling_price: number;
  discount_amount: number;
  vat_percent: number;
  final_price: number;
  unit_price: number;
  actual_margin: number;
}

/** Tính giá picker state */
export interface CostingPickerOut {
  available: boolean;
  message: string | null;
  options?: CostingQtyOption[] | null;
}

export interface QuotationListParams {
  q?: string;
  status?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Đơn hàng bán (Order), spec-10 ------------------------------------------
export interface OrderRow {
  id: number;
  order_no: string;
  customer_id: number | null;
  customer_name: string | null;
  order_type: string;
  order_kind: string;
  status: string;
  total_estimate: number | null;
  has_customer_paper: boolean;
  gate_ordered_ok: boolean;
  created_at: string;
}

export interface OrderListOut {
  items: OrderRow[];
  total: number;
  page: number;
  size: number;
}

export interface OrderLineOut {
  id: number;
  description: string;
  qty: number;
  unit_price_snapshot: number | null;
  norm_snapshot: Record<string, unknown> | null;
  vat_pct_estimate: number;
  line_total: number | null;
}

/** ③→④ gate (F3). deposit_paid=null + deposit_available=false while SEAM-04 (Payment) is TREO. */
export interface OrderGate {
  total: number;
  min_deposit_pct: number;
  deposit_required: number;
  deposit_paid: number | null;
  deposit_available: boolean;
  deposit_shortfall: number;
  quotation_approved: boolean;
  can_confirm: boolean;
}

export interface OrderDetail {
  id: number;
  order_no: string;
  customer_id: number | null;
  customer: CustomerDisplay | null;
  quotation_id: number | null;
  quotation_version: number | null;
  quotation_effective_from: string | null;
  order_type: string;
  order_kind: string;
  parent_order_id: number | null;
  status: string;
  has_customer_paper: boolean;
  vat_pct_estimate: number;
  cancel_reason: string | null;
  cancelled_at_state: string | null;
  created_at: string;
  lines: OrderLineOut[];
  gate: OrderGate | null;
  allowed_transitions: string[];
}

export interface OrderInput {
  quotation_id: number;
  order_type: string;
  order_kind: string;
  parent_order_id: number | null;
  has_customer_paper: boolean;
  vat_pct_estimate: number;
}

export interface OrderEnumsOut {
  order_types: EnumOption[];
  order_kinds: EnumOption[];
  statuses: EnumOption[];
}

export interface ApprovedQuotationRow {
  id: number;
  code: string;
  version: number;
  customer_id: number | null;
  customer_name: string | null;
  total: number | null;
  valid_until: string | null;
}

export interface OrderListParams {
  q?: string;
  status?: string | null;
  order_kind?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Master Data (Cấu hình danh mục) shapes --------------------------------
export interface ProductTypeCatalogRow {
  id: number;
  product_type: string;
  name: string;
  calculation_strategy: string;
  product_group: string;
  technology: string;
  display_order: number;
  version: number;
  description?: string | null;
  required_fields: string[] | null;
  shown_fields: string[] | null;
  default_operations: string[] | null;
  required_operations: string[] | null;
  allowed_materials: string[] | null;
  compatible_technologies: string[] | null;
  allowed_imposition_codes: string[] | null;
  default_imposition_code: string | null;
  dimension_rule_type: string;
  default_bleed_mm: number;
  default_gutter_mm: number;
  default_trim_mm: number;
  allow_rotation?: boolean;
  allow_custom_size?: boolean;
  has_page_count: boolean;
  page_multiple?: number;
  pages_per_signature?: number;
  has_cover_body_split: boolean;
  has_tooling: boolean;
  default_tooling_type?: string | null;
  has_packaging: boolean;
  default_pack_qty?: number;
  default_paper_material_id?: number | null;
  default_cover_material_id?: number | null;
  default_body_material_id?: number | null;
  default_ink_material_id?: number | null;
  allow_extra_operations?: boolean;
  allow_imposition_change?: boolean;
  allow_manual_override?: boolean;
  waste_pct?: number;
  sheet_count_mode: string;
  ink_cost_mode: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface ProductTypeCatalogInput {
  product_type: string;
  name: string;
  calculation_strategy: string;
  product_group?: string;
  technology?: string;
  description?: string | null;
  display_order?: number;
  required_fields?: string[] | null;
  shown_fields?: string[] | null;
  dimension_rule_type?: string;
  default_bleed_mm?: number;
  default_gutter_mm?: number;
  default_trim_mm?: number;
  allow_rotation?: boolean;
  allow_custom_size?: boolean;
  has_page_count?: boolean;
  page_multiple?: number;
  pages_per_signature?: number;
  has_cover_body_split?: boolean;
  allowed_materials?: string[] | null;
  default_paper_material_id?: number | null;
  default_cover_material_id?: number | null;
  default_body_material_id?: number | null;
  default_ink_material_id?: number | null;
  has_packaging?: boolean;
  default_pack_qty?: number;
  default_operations?: string[] | null;
  required_operations?: string[] | null;
  allow_extra_operations?: boolean;
  allowed_imposition_codes?: string[] | null;
  default_imposition_code?: string | null;
  allow_imposition_change?: boolean;
  compatible_technologies?: string[] | null;
  sheet_count_mode?: string;
  ink_cost_mode?: string;
  has_tooling?: boolean;
  default_tooling_type?: string | null;
  allow_manual_override?: boolean;
  waste_pct?: number;
  is_active?: boolean;
}

export interface ProductTypePreviewResult {
  product_type: string;
  name: string;
  shown_fields: string[];
  required_fields: string[];
  routing: string[];
  required_operations: string[];
  allowed_imposition_codes: string[];
  default_imposition_code: string | null;
  dimension_rule_type: string;
  default_bleed_mm: number;
  default_gutter_mm: number;
  default_trim_mm: number;
  sheet_count_mode: string;
  ink_cost_mode: string;
  has_tooling: boolean;
  has_packaging: boolean;
  has_cover_body_split: boolean;
  rules: string[];
  warnings: string[];
}

export interface ProductTypeCatalogListOut {
  items: ProductTypeCatalogRow[];
  total: number;
  page: number;
  size: number;
}

export type PaperSizeGroup = "cong_nghiep" | "kho_a" | "kho_cat" | "custom";

export interface PaperSizeRow {
  id: number;
  code: string;
  name: string;
  size_group: string;
  is_purchase_size: boolean;
  is_print_sheet_size: boolean;
  is_cut_size: boolean;
  size_type: string;
  note: string | null;
  width_cm: number;
  height_cm: number;
  area_m2: number;
  allow_rotation: boolean;
  compatible_machine_ids: number[] | null;
  default_machine_id: number | null;
  parent_size_id: number | null;
  cut_count: number | null;
  cut_waste_rate: number | null;
  version: number;
  effective_from: string | null;
  effective_to: string | null;
  used_count: number;
  /** "Đang dùng trong" = số phiếu tính giá tham chiếu khổ — server tính khi list. */
  used_in_costings: number;
  created_by: number | null;
  updated_by: number | null;
  is_active: boolean;
  created_at: string;
}

export interface PaperSizeDuplicateRef {
  id: number;
  code: string;
  name: string;
  width_cm: number;
  height_cm: number;
  version: number;
}

export interface PaperSizeDuplicateOut {
  matched: PaperSizeDuplicateRef | null;
}

export interface PaperSizeUsageCosting {
  id: number;
  code: string;
  product_name: string | null;
  qty_final: number;
  status: string;
  created_at: string;
}

export interface PaperSizeUsageOut {
  paper_size_id: number;
  code: string;
  name: string;
  costing_count: number;
  costings: PaperSizeUsageCosting[];
}

export interface PaperSizeInput {
  code?: string | null;
  name: string;
  size_group?: PaperSizeGroup;
  is_purchase_size?: boolean | null;
  is_print_sheet_size?: boolean | null;
  is_cut_size?: boolean | null;
  size_type?: string | null;
  note?: string | null;
  is_active?: boolean | null;
  width_cm: number;
  height_cm: number;
  allow_rotation?: boolean;
  compatible_machine_ids?: number[] | null;
  default_machine_id?: number | null;
  parent_size_id?: number | null;
  cut_count?: number | null;
  cut_waste_rate?: number | null;
  effective_from?: string | null;
  effective_to?: string | null;
}

export interface PaperSizeListOut {
  items: PaperSizeRow[];
  total: number;
  page: number;
  size: number;
}

export type ImpositionGroupKind = "one_side" | "two_side" | "multi_page" | "custom";
export type ImpositionAppliesToSides = "any" | "1" | "2" | "multi";

export interface ImpositionTypeRow {
  id: number;
  code: string;
  name: string;
  group_kind: ImpositionGroupKind;
  sides: number;
  finished_factor: number;
  pass_count: number;
  plate_set_factor: number;
  ink_pass_factor: number;
  allow_rotate: boolean;
  shared_plate_set: boolean;
  note: string | null;
  technology: string;
  applies_to_sides: ImpositionAppliesToSides;
  applicable_product_types: string[] | null;
  applicable_machine_ids: number[] | null;
  applicable_paper_size_ids: number[] | null;
  allow_multi_signature: boolean;
  priority: number;
  version: number;
  effective_from: string | null;
  effective_to: string | null;
  used_count: number;
  // "Đang dùng trong" = số TÍNH GIÁ (estimates) đang dùng quy tắc — server tính khi list.
  estimate_count: number;
  created_by: number | null;
  updated_by: number | null;
  is_active: boolean;
  created_at: string;
}

// Kiểm thử nhanh (preview engine) — dùng chung công thức với pricing_engine.
export interface ImpositionPreviewRequest {
  finished_factor: number;
  pass_count: number;
  plate_set_factor: number;
  ink_pass_factor: number;
  geometric_pieces: number;
  quantity: number;
  production_sheets: number;
  colors: number;
  forms: number;
  machine_speed: number;
}

export interface ImpositionPreviewOut {
  finished_pieces_per_sheet: number;
  theoretical_sheets: number;
  machine_sheets: number;
  run_hours: number;
  plates: number;
  ink_impressions: number;
}

export interface ImpositionUsageEstimate {
  id: number;
  estimate_number: string;
  product_name: string;
  status: string;
  created_at: string;
}

export interface ImpositionUsageOut {
  code: string;
  estimate_count: number;
  estimates: ImpositionUsageEstimate[];
}

// Create carries `code`; Update omits it (code is immutable — keyed by the version chain).
// force_version (update only): buộc tạo phiên bản mới kể cả khi chưa dùng.
export interface ImpositionTypeInput {
  code?: string;
  force_version?: boolean;
  name: string;
  group_kind: ImpositionGroupKind;
  sides: number;
  finished_factor: number;
  pass_count: number;
  plate_set_factor: number;
  ink_pass_factor: number;
  allow_rotate: boolean;
  shared_plate_set: boolean;
  note?: string | null;
  technology?: string;
  applies_to_sides: ImpositionAppliesToSides;
  applicable_product_types?: string[] | null;
  applicable_machine_ids?: number[] | null;
  applicable_paper_size_ids?: number[] | null;
  allow_multi_signature: boolean;
  priority: number;
  effective_from?: string | null;
  effective_to?: string | null;
  is_active?: boolean;
}

export interface ImpositionTypeListOut {
  items: ImpositionTypeRow[];
  total: number;
  page: number;
  size: number;
}

export type MaterialGroup = "paper" | "ink" | "film" | "glue" | "packaging" | "auxiliary";

export interface MaterialCostRow {
  id: number;
  material_id?: number;
  price_unit: string;
  unit_price: number;
  supplier: string | null;
  paper_size_id: number | null;
  price_type: string;
  vat_included: boolean;
  transport_fee: number;
  moq: number;
  lead_time_days: number;
  quantity_from: number | null;
  quantity_to: number | null;
  version: number;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
}

export interface MaterialCostInput {
  price_unit: string;
  unit_price: number;
  effective_from: string;
  supplier?: string | null;
  paper_size_id?: number | null;
  price_type?: string;
  vat_included?: boolean;
  transport_fee?: number;
  moq?: number;
  lead_time_days?: number;
  quantity_from?: number | null;
  quantity_to?: number | null;
}

interface MaterialFields {
  material_group?: MaterialGroup | null;
  default_supplier?: string | null;
  base_uom?: string | null;
  purchase_uom?: string | null;
  consumption_uom?: string | null;
  conversion_method?: string | null;
  conversion_factor?: number | null;
  ink_type?: string | null;
  ink_color_system?: string | null;
  ink_color_code?: string | null;
  film_type?: string | null;
}

export interface MaterialRow extends MaterialFields {
  id: number;
  code: string;
  name: string;
  material_type: string;
  unit: string;
  min_fee: number;
  width_cm: number | null;
  height_cm: number | null;
  gsm: number | null;
  thickness_mm: number | null;
  default_waste_pct: number;
  min_purchase_qty: number;
  paper_family: string | null;
  surface: string | null;
  version: number;
  is_active: boolean;
  costs: MaterialCostRow[];
  created_at: string;
  updated_at: string;
}

export interface MaterialInput extends MaterialFields {
  name: string;
  material_type: string;
  unit: string;
  min_fee?: number;
  width_cm?: number | null;
  height_cm?: number | null;
  gsm?: number | null;
  thickness_mm?: number | null;
  default_waste_pct?: number;
  min_purchase_qty?: number;
  paper_family?: string | null;
  surface?: string | null;
  is_active?: boolean;
}

export interface MaterialConvertOut {
  area_m2: number;
  kg_per_sheet: number;
  detail: string;
}

export interface MaterialPriceTestInput {
  price_unit: string;
  unit_price: number;
  sheets?: number;
  gsm?: number | null;
  width_cm?: number | null;
  height_cm?: number | null;
  impressions?: number;
  quantity?: number;
  transport_fee?: number;
}

export interface MaterialPriceTestOut {
  total: number;
  steps: string[];
}

export interface MaterialListStats {
  total_materials: number;
  total_papers: number;
  total_consumables: number;
  no_price_count: number;
  price_updates_this_month: number;
}

export interface MaterialListOut {
  items: MaterialRow[];
  total: number;
  page: number;
  size: number;
  stats: MaterialListStats;
}

export type MachineGroup = "may_in" | "may_can" | "may_be" | "may_xen" | "khac";
export type MachineStatusKind = "active" | "inactive" | "maintenance";
export type MachineRoundingPolicy = "none" | "0.01" | "0.25" | "0.5";

export interface MachineRateRow {
  id: number;
  hourly_rate: number;
  min_charge: number;
  min_run_time_mins: number;
  rate_depreciation: number;
  rate_energy: number;
  rate_maintenance: number;
  rate_labor: number;
  rate_overhead: number;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
}

export interface MachineRateInput {
  hourly_rate: number;
  min_charge: number;
  min_run_time_mins: number;
  rate_depreciation?: number;
  rate_energy?: number;
  rate_maintenance?: number;
  rate_labor?: number;
  rate_overhead?: number;
  effective_from: string;
}

// Shared machine spec fields (row + input).
interface MachineFields {
  name: string;
  machine_type: string;
  process_type: string;
  machine_group: MachineGroup;
  status: MachineStatusKind;
  note: string | null;
  speed: number;
  speed_unit: string;
  min_speed: number | null;
  max_speed: number | null;
  max_width_cm: number | null;
  max_height_cm: number | null;
  min_width_cm: number | null;
  min_height_cm: number | null;
  max_print_width_cm: number | null;
  max_print_height_cm: number | null;
  gripper_cm: number;
  side_margin_cm: number;
  top_bottom_margin_cm: number;
  compatible_paper_size_ids: number[] | null;
  setup_time_mins: number;
  changeover_time_mins: number;
  setup_waste_sheets: number;
  setup_time_base_hour: number;
  setup_time_per_color_hour: number;
  setup_time_per_side_hour: number;
  cleaning_time_hour: number;
  color_change_time_hour: number;
  plate_change_time_per_plate_hour: number;
  color_check_time_hour: number;
  min_setup_time_hour: number;
  max_setup_time_hour: number | null;
  rounding_hour_policy: MachineRoundingPolicy;
  overhead_included: boolean;
  operator_included: boolean;
  num_ink_units: number | null;
  supports_perfecting: boolean;
  supported_materials: string[] | null;
  is_active: boolean;
}

export interface MachineRow extends MachineFields {
  id: number;
  code: string;
  used_count: number;
  created_by: number | null;
  updated_by: number | null;
  rates: MachineRateRow[];
}

export type MachineInput = MachineFields & { code?: string };

export interface MachineListOut {
  items: MachineRow[];
  total: number;
  page: number;
  size: number;
}

export interface OperationCatalogRateRow {
  id: number;
  operation_id: number;
  setup_fee: number;
  run_rate: number;
  labor_rate: number;
  min_charge: number;
  speed: number;
  setup_time_mins: number;
  hourly_rate: number;
  labor_shift_rate: number;
  labor_fixed: number;
  labor_min: number;
  tooling_unit_price: number;
  outsource_supplier: string | null;
  outsource_unit_price: number;
  outsource_setup_fee: number;
  outsource_min_charge: number;
  outsource_transport_fee: number;
  outsource_moq: number;
  outsource_lead_time_days: number;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
  updated_at: string;
}

export interface OperationCatalogRateInput {
  setup_fee: number;
  run_rate: number;
  labor_rate: number;
  min_charge: number;
  speed: number;
  setup_time_mins: number;
  hourly_rate?: number;
  labor_shift_rate?: number;
  labor_fixed?: number;
  labor_min?: number;
  tooling_unit_price?: number;
  outsource_supplier?: string | null;
  outsource_unit_price?: number;
  outsource_setup_fee?: number;
  outsource_min_charge?: number;
  outsource_transport_fee?: number;
  outsource_moq?: number;
  outsource_lead_time_days?: number;
  effective_from: string;
}

export interface OperationCatalogRow {
  id: number;
  code: string;
  name: string;
  operation_type: string;
  unit: string;
  basis_quantity: string;
  pricing_method: string;
  process_group: string;
  process_type: string;
  default_sequence: number;
  quantity_formula_type: string;
  allow_manual_quantity: boolean;
  internal_pricing_method: string;
  labor_people_count: number;
  has_tooling: boolean;
  tooling_type: string | null;
  tooling_rate_id: number | null;
  has_yield_loss: boolean;
  default_yield_rate: number | null;
  default_yield_rule: string | null;
  allow_outsource: boolean;
  is_active: boolean;
  rates: OperationCatalogRateRow[];
  created_at: string;
  updated_at: string;
}

export interface OperationCatalogInput {
  name: string;
  operation_type: string;
  unit: string;
  basis_quantity: string;
  pricing_method: string;
  process_group?: string;
  process_type?: string;
  default_sequence?: number;
  quantity_formula_type?: string;
  allow_manual_quantity?: boolean;
  internal_pricing_method?: string;
  labor_people_count?: number;
  has_tooling?: boolean;
  tooling_type?: string | null;
  tooling_rate_id?: number | null;
  has_yield_loss?: boolean;
  default_yield_rate?: number | null;
  default_yield_rule?: string | null;
  allow_outsource?: boolean;
  is_active?: boolean;
}

export interface OperationPreviewInput {
  sheet_qty?: number;
  finished_qty?: number;
  area_m2?: number;
  book_qty?: number;
  manual_qty?: number;
  execution_mode?: string;
}

export interface OperationPreviewComponent {
  label: string;
  formula: string;
  amount: number;
}

export interface OperationPreviewResult {
  operation_name: string;
  execution_mode: string;
  quantity: number;
  unit: string;
  components: OperationPreviewComponent[];
  total: number;
  warnings: string[];
}

export interface OperationCatalogListOut {
  items: OperationCatalogRow[];
  total: number;
  page: number;
  size: number;
}

export interface CatalogListParams {
  q?: string;
  type?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Nhân sự · Hồ sơ nhân sự (nhan_su), lát #1 -----------------------------

export type EmployeeStatus = "probation" | "active" | "on_leave" | "suspended" | "resigned";

export interface EmployeeRow {
  id: number;
  code: string;
  full_name: string;
  department_id: number | null;
  department_name: string | null;
  position: string | null;
  job_grade: string | null;
  status: string;
  hire_date: string | null;
  probation_end_date: string | null;
  user_id: number | null;
  account_username: string | null;
  photo_url: string | null;
  created_at: string | null;
}

export interface EmployeeDetail extends EmployeeRow {
  date_of_birth: string | null;
  gender: string | null;
  national_id: string | null;
  national_id_date: string | null;
  national_id_place: string | null;
  phone: string | null;
  email: string | null;
  permanent_address: string | null;
  current_address: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  social_insurance_no: string | null;
  pit_tax_code: string | null;
  dependents_count: number;
  bank_account: string | null;
  bank_name: string | null;
  default_shift_id: number | null;
  resign_date: string | null;
  resign_reason: string | null;
  note: string | null;
}

export interface EmployeeKpis {
  total: number;
  active: number;
  probation: number;
  on_leave: number;
  resigned: number;
  probation_ending_soon: number;
}

export interface EmployeeListOut {
  items: EmployeeRow[];
  total: number;
  page: number;
  size: number;
  kpis: EmployeeKpis;
}

export interface EmployeeDuplicate {
  id: number;
  code: string;
  full_name: string;
}

export interface EmployeeCreateOut {
  employee: EmployeeDetail;
  duplicate_national_id: EmployeeDuplicate | null;
  duplicate_social_insurance: EmployeeDuplicate | null;
  account_username: string | null;
}

export interface EmployeeUpdateOut {
  employee: EmployeeDetail;
  duplicate_national_id: EmployeeDuplicate | null;
  duplicate_social_insurance: EmployeeDuplicate | null;
}

export interface EmployeeEvent {
  id: number;
  event_type: string;
  effective_date: string | null;
  field: string | null;
  from_value: string | null;
  to_value: string | null;
  note: string | null;
  actor_user_id: number | null;
  actor_name: string | null;
  created_at: string | null;
}

export interface EmployeeAttachment {
  id: number;
  doc_kind: string;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_by: number | null;
  uploaded_at: string | null;
}

export interface EmployeeActivityRow {
  action: string;
  target: string;
  detail: string;
  actor_name: string | null;
  created_at: string;
}

export interface EmployeeMeta {
  departments: { id: number; name: string }[];
  unlinked_users: { id: number; username: string; name: string }[];
}

export interface EmployeeAccountInput {
  username: string;
  password: string;
  name?: string | null;
  role_id?: number | null;
}

export interface EmployeeInput {
  full_name: string;
  department_id: number | null;
  position?: string | null;
  job_grade?: string | null;
  status?: string;
  hire_date?: string | null;
  probation_end_date?: string | null;
  date_of_birth?: string | null;
  gender?: string | null;
  national_id?: string | null;
  national_id_date?: string | null;
  national_id_place?: string | null;
  phone?: string | null;
  email?: string | null;
  permanent_address?: string | null;
  current_address?: string | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  social_insurance_no?: string | null;
  pit_tax_code?: string | null;
  dependents_count?: number;
  bank_account?: string | null;
  bank_name?: string | null;
  default_shift_id?: number | null;
  note?: string | null;
  account?: EmployeeAccountInput | null;
}

export interface EmployeeTransitionInput {
  kind: string;
  effective_date?: string | null;
  note?: string | null;
  new_department_id?: number | null;
  new_job_grade?: string | null;
  new_position?: string | null;
  resign_reason?: string | null;
}

export interface EmployeeListParams {
  q?: string;
  department_id?: number | null;
  status?: string | null;
  has_account?: boolean | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Chấm công GPS (nhan_su) ------------------------------------------------

export interface WorkLocation {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  radius_m: number;
  is_active: boolean;
  note: string | null;
  created_at?: string | null;
}

export interface WorkLocationInput {
  name: string;
  latitude: number;
  longitude: number;
  radius_m: number;
  note?: string | null;
  is_active?: boolean;
}

export interface AttendanceLog {
  id: number;
  employee_id: number;
  employee_name?: string | null;
  work_location_id?: number | null;
  location_name?: string | null;
  check_type: string;
  checked_at: string;
  latitude?: number | null;
  longitude?: number | null;
  distance_m?: number | null;
  within_range: boolean;
  note?: string | null;
}

export interface NearestLocation {
  id: number;
  name: string;
  radius_m: number;
}

export interface CheckResult {
  success: boolean;
  within_range: boolean;
  check_type: string | null;
  distance_m: number | null;
  nearest_location: NearestLocation | null;
  message: string;
  log: AttendanceLog | null;
}

export interface AttendanceStatus {
  has_employee: boolean;
  employee_name: string | null;
  next_action: string | null;
  last_check: AttendanceLog | null;
  locations_configured: boolean;
}

export interface WorkShift {
  id: number;
  name: string;
  start_time: string;   // "HH:MM"
  end_time: string;
  is_overnight: boolean;
  night_shift: boolean;
  grace_minutes: number;
  is_active: boolean;
  note: string | null;
}

export interface WorkShiftInput {
  name: string;
  start_time: string;
  end_time: string;
  is_overnight?: boolean;
  night_shift?: boolean;
  grace_minutes?: number;
  note?: string | null;
  is_active?: boolean;
}

export interface TimesheetDay {
  first_in: string | null;
  last_out: string | null;
  hours: number | null;
  present: boolean;
  cong: number | null;   // công theo ca (0..1)
  late: boolean;
  early: boolean;
  ot_minutes: number;
  night: boolean;
}

export interface TimesheetRow {
  employee_id: number;
  employee_code: string;
  employee_name: string;
  department_id: number | null;
  department_name: string | null;
  shift_id: number | null;
  shift_name: string | null;
  days: Record<string, TimesheetDay>;
  total_days: number;
  total_hours: number;
  total_cong: number | null;
}

export interface Timesheet {
  year: number;
  month: number;
  days_in_month: number;
  rows: TimesheetRow[];
}

// --- Cấu hình kho hàng (warehouse master data) ------------------------------
export interface WarehouseRow {
  id: number;
  code: string;
  name: string;
  description: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WarehouseInput {
  name: string;
  description?: string | null;
  notes?: string | null;
  is_active?: boolean;
}

export interface WarehouseListOut {
  items: WarehouseRow[];
  total: number;
  page: number;
  size: number;
}

// --- Kho hàng vận hành (warehouse items) ------------------------------------
export interface WarehouseOption {
  id: number;
  code: string;
  name: string;
}

export interface WarehouseItemRow {
  id: number;
  warehouse_id: number;
  warehouse_code: string | null;
  warehouse_name: string | null;
  name: string;
  quantity: number;
  unit: string;
  notes: string | null;
  created_by_user_id: number | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface WarehouseItemInput {
  warehouse_id: number;
  name: string;
  quantity: number;
  unit: string;
  notes?: string | null;
}

export interface WarehouseItemListOut {
  items: WarehouseItemRow[];
  total: number;
  page: number;
  size: number;
}

export const api = {
  login(username: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  me(token: string): Promise<User> {
    return request<User>("/api/auth/me", { headers: authHeader(token) });
  },

  /** Exchange the httpOnly refresh cookie for a new access token (rotates the cookie). */
  refresh(): Promise<LoginResponse> {
    return request<LoginResponse>("/api/auth/refresh", { method: "POST" });
  },

  /** Revoke the refresh token server-side and clear the cookie. */
  logout(): Promise<void> {
    return request<void>("/api/auth/logout", { method: "POST" });
  },

  /** Module keys the current user can Read (for menu/route gating). */
  myPermissions(token: string): Promise<string[]> {
    return authed<{ modules: string[] }>("/api/auth/permissions", token).then(
      (r) => r.modules,
    );
  },

  /** Current user's readable modules + full CRUD matrix (spec-09 action gating). */
  myAccess(
    token: string,
  ): Promise<{ modules: string[]; permissions: ModuleCapability[] }> {
    return authed<{ modules: string[]; permissions: ModuleCapability[] }>(
      "/api/auth/permissions",
      token,
    );
  },

  // --- Self-service profile (spec-04) ---------------------------------------

  /** Enriched current-user profile (department/role names + created_at). */
  profile(token: string): Promise<Profile> {
    return authed<Profile>("/api/auth/me", token);
  },

  /** Change the display name; returns the updated user. */
  updateName(token: string, name: string): Promise<User> {
    return authed<User>("/api/users/me", token, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
  },

  /** Upload a new avatar (JPG/PNG ≤ 2 MB); returns its server path. */
  uploadAvatar(token: string, file: File): Promise<{ avatar_url: string }> {
    const form = new FormData();
    form.append("file", file);
    return authed<{ avatar_url: string }>("/api/users/me/avatar", token, {
      method: "POST",
      body: form,
    });
  },

  /** Remove the avatar → initials fallback. */
  removeAvatar(token: string): Promise<void> {
    return authed<void>("/api/users/me/avatar", token, { method: "DELETE" });
  },

  /** Change the current user's password; ends all sessions (caller returns to Login). */
  changePassword(token: string, currentPassword: string, newPassword: string): Promise<void> {
    return authed<void>("/api/auth/change-password", token, {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  },

  rbac: {
    modules(token: string): Promise<ModuleDef[]> {
      return authed<ModuleDef[]>("/api/rbac/modules", token);
    },
    departments(token: string): Promise<Department[]> {
      return authed<Department[]>("/api/departments", token);
    },
    departmentUsers(token: string, departmentId: number): Promise<DepartmentMember[]> {
      return authed<DepartmentMember[]>(`/api/departments/${departmentId}/users`, token);
    },
    createDepartment(
      token: string,
      name: string,
      description: string | null,
      parentId: number | null,
      levelId: number | null = null,
    ): Promise<Department> {
      return authed<Department>("/api/departments", token, {
        method: "POST",
        body: JSON.stringify({ name, description, parent_id: parentId, level_id: levelId }),
      });
    },
    updateDepartment(
      token: string,
      id: number,
      name: string,
      headUserId: number | null,
      description: string | null,
      levelId: number | null = null,
      parentId: number | null = null,
    ): Promise<Department> {
      return authed<Department>(`/api/departments/${id}`, token, {
        method: "PUT",
        body: JSON.stringify({
          name,
          head_user_id: headUserId,
          description,
          level_id: levelId,
          parent_id: parentId,
        }),
      });
    },
    /** Departments that would be deleted with this one's branch (spec-05 confirm). */
    departmentSubtree(token: string, id: number): Promise<DepartmentSubtreeRow[]> {
      return authed<DepartmentSubtreeRow[]>(`/api/departments/${id}/subtree`, token);
    },
    /** People eligible to head a unit: everyone in the unit + its sub-units (PBI-4004). */
    headCandidates(token: string, id: number): Promise<UserBrief[]> {
      return authed<UserBrief[]>(`/api/departments/${id}/head-candidates`, token);
    },
    deleteDepartment(token: string, id: number): Promise<void> {
      return authed<void>(`/api/departments/${id}`, token, { method: "DELETE" });
    },
    // --- Unit-level catalog (spec-06 / PBI-4009) ---
    unitLevels(token: string): Promise<UnitLevel[]> {
      return authed<UnitLevel[]>("/api/unit-levels", token);
    },
    createUnitLevel(
      token: string,
      name: string,
      rank: number,
      headTitle: string,
    ): Promise<UnitLevel> {
      return authed<UnitLevel>("/api/unit-levels", token, {
        method: "POST",
        body: JSON.stringify({ name, rank, head_title: headTitle }),
      });
    },
    updateUnitLevel(
      token: string,
      id: number,
      name: string,
      rank: number,
      headTitle: string,
    ): Promise<UnitLevel> {
      return authed<UnitLevel>(`/api/unit-levels/${id}`, token, {
        method: "PUT",
        body: JSON.stringify({ name, rank, head_title: headTitle }),
      });
    },
    deleteUnitLevel(token: string, id: number): Promise<void> {
      return authed<void>(`/api/unit-levels/${id}`, token, { method: "DELETE" });
    },
    users(token: string): Promise<UserRow[]> {
      return authed<UserRow[]>("/api/users", token);
    },
    createUser(token: string, name: string, username: string, departmentId: number): Promise<UserRow> {
      return authed<UserRow>("/api/users", token, {
        method: "POST",
        body: JSON.stringify({ name, username, department_id: departmentId }),
      });
    },
    assignUserRole(token: string, userId: number, roleId: number | null): Promise<UserRow> {
      return authed<UserRow>(`/api/users/${userId}/role`, token, {
        method: "PUT",
        body: JSON.stringify({ role_id: roleId }),
      });
    },
    setUserActive(token: string, userId: number, isActive: boolean): Promise<UserRow> {
      return authed<UserRow>(`/api/users/${userId}/active`, token, {
        method: "PUT",
        body: JSON.stringify({ is_active: isActive }),
      });
    },
    /** Edit a user's name + department (spec-08 / PBI-2003); dept change drops the old role. */
    updateUser(token: string, userId: number, name: string, departmentId: number): Promise<UserRow> {
      return authed<UserRow>(`/api/users/${userId}`, token, {
        method: "PUT",
        body: JSON.stringify({ name, department_id: departmentId }),
      });
    },
    /** Reset a user's password → returns the one-time temp password; revokes all sessions. */
    resetUserPassword(token: string, userId: number): Promise<{ temporary_password: string }> {
      return authed<{ temporary_password: string }>(`/api/users/${userId}/reset-password`, token, {
        method: "POST",
      });
    },
    /** Log a user out everywhere (spec-08 / PBI-2008). */
    revokeUserSessions(token: string, userId: number): Promise<void> {
      return authed<void>(`/api/users/${userId}/revoke-sessions`, token, { method: "POST" });
    },
    /** A user's live sessions (device + times), read-only. */
    userSessions(token: string, userId: number): Promise<Session[]> {
      return authed<Session[]>(`/api/users/${userId}/sessions`, token);
    },
    /** Recent activity targeting a user. */
    userActivity(token: string, userId: number): Promise<AuditRow[]> {
      return authed<AuditRow[]>(`/api/users/${userId}/activity`, token);
    },
    /** Bulk-move people to a target department (spec-06 / PBI-4008); old roles are dropped. */
    transferUsers(
      token: string,
      userIds: number[],
      targetDepartmentId: number,
    ): Promise<{ transferred: number }> {
      return authed<{ transferred: number }>("/api/departments/transfer", token, {
        method: "POST",
        body: JSON.stringify({ user_ids: userIds, target_department_id: targetDepartmentId }),
      });
    },
    /** Gán một vai trò cho nhiều người cùng lúc từ màn Phòng ban (bulk). */
    bulkAssignRole(
      token: string,
      userIds: number[],
      roleId: number,
    ): Promise<{ assigned: number }> {
      return authed<{ assigned: number }>("/api/departments/assign-role", token, {
        method: "POST",
        body: JSON.stringify({ user_ids: userIds, role_id: roleId }),
      });
    },
    activityLog(token: string): Promise<AuditRow[]> {
      return authed<AuditRow[]>("/api/audit", token);
    },
    roles(token: string, departmentId: number): Promise<Role[]> {
      return authed<Role[]>(`/api/roles?department_id=${departmentId}`, token);
    },
    createRole(token: string, name: string, departmentId: number): Promise<Role> {
      return authed<Role>("/api/roles", token, {
        method: "POST",
        body: JSON.stringify({ name, department_id: departmentId }),
      });
    },
    renameRole(token: string, roleId: number, name: string): Promise<Role> {
      return authed<Role>(`/api/roles/${roleId}`, token, {
        method: "PUT",
        body: JSON.stringify({ name }),
      });
    },
    deleteRole(token: string, roleId: number): Promise<void> {
      return authed<void>(`/api/roles/${roleId}`, token, { method: "DELETE" });
    },
    permissions(token: string, roleId: number): Promise<PermissionRow[]> {
      return authed<PermissionRow[]>(`/api/roles/${roleId}/permissions`, token);
    },
    savePermissions(
      token: string,
      roleId: number,
      rows: PermissionRow[],
    ): Promise<PermissionRow[]> {
      return authed<PermissionRow[]>(`/api/roles/${roleId}/permissions`, token, {
        method: "PUT",
        body: JSON.stringify({ permissions: rows }),
      });
    },
  },

  // --- Khách hàng (CRM), spec-06 --------------------------------------------
  customers: {
    list(token: string, params: CustomerListParams = {}): Promise<CustomerListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.sale != null) qs.set("sale", String(params.sale));
      if (params.tier) qs.set("tier", params.tier);
      if (params.status) qs.set("status", params.status);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<CustomerListOut>(`/api/customers${suffix}`, token);
    },
    sales(token: string): Promise<SaleOption[]> {
      return authed<SaleOption[]>("/api/customers/sales", token);
    },
    /** Điều chuyển toàn bộ khách của một Sale sang Sale khác (trưởng phòng KD). */
    reassign(
      token: string,
      fromSaleUserId: number,
      toSaleUserId: number,
    ): Promise<{ moved: number; skipped: number }> {
      return authed<{ moved: number; skipped: number }>("/api/customers/reassign", token, {
        method: "POST",
        body: JSON.stringify({
          from_sale_user_id: fromSaleUserId,
          to_sale_user_id: toSaleUserId,
        }),
      });
    },
    /** Điều chuyển các khách ĐƯỢC CHỌN (checkbox) sang một Sale. */
    reassignSelected(
      token: string,
      customerIds: number[],
      toSaleUserId: number,
    ): Promise<{ moved: number; skipped: number }> {
      return authed<{ moved: number; skipped: number }>("/api/customers/reassign", token, {
        method: "POST",
        body: JSON.stringify({
          customer_ids: customerIds,
          to_sale_user_id: toSaleUserId,
        }),
      });
    },
    get(token: string, id: number): Promise<CustomerDetailOut> {
      return authed<CustomerDetailOut>(`/api/customers/${id}`, token);
    },
    dashboard(token: string, id: number): Promise<CustomerDashboard> {
      return authed<CustomerDashboard>(`/api/customers/${id}/dashboard`, token);
    },
    orderHistory(token: string, id: number): Promise<{ items: OrderHistoryRow[] }> {
      return authed<{ items: OrderHistoryRow[] }>(`/api/customers/${id}/orders`, token);
    },
    quoteHistory(token: string, id: number): Promise<{ items: QuoteHistoryRow[] }> {
      return authed<{ items: QuoteHistoryRow[] }>(`/api/customers/${id}/quotations`, token);
    },
    audit(token: string, id: number): Promise<{ items: CustomerAuditRow[] }> {
      return authed<{ items: CustomerAuditRow[] }>(`/api/customers/${id}/audit`, token);
    },
    /** Xuất Excel (CSV) lịch sử mua hàng — fetch as a blob (bearer + refresh-aware). */
    async orderCsvBlobUrl(token: string, id: number): Promise<string> {
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/customers/${id}/orders.csv`, {
          credentials: "include",
          cache: "no-store",
          headers: authHeader(bearer),
        });
      let resp = await doFetch(token);
      if (resp.status === 401) {
        const fresh = await refreshAccessToken();
        if (fresh) resp = await doFetch(fresh);
      }
      if (!resp.ok) throw new ApiError(`Export failed (${resp.status}).`, resp.status);
      const blob = await resp.blob();
      return URL.createObjectURL(blob);
    },
    create(token: string, input: CustomerInput): Promise<CustomerCreateOut> {
      return authed<CustomerCreateOut>("/api/customers", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: CustomerInput): Promise<CustomerCreateOut> {
      return authed<CustomerCreateOut>(`/api/customers/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
  },

  // --- Nhân sự · Hồ sơ nhân sự (nhan_su), lát #1 ----------------------------
  employees: {
    list(token: string, params: EmployeeListParams = {}): Promise<EmployeeListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.department_id != null) qs.set("department_id", String(params.department_id));
      if (params.status) qs.set("status", params.status);
      if (params.has_account != null) qs.set("has_account", String(params.has_account));
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<EmployeeListOut>(`/api/employees${suffix}`, token);
    },
    meta(token: string): Promise<EmployeeMeta> {
      return authed<EmployeeMeta>("/api/employees/meta", token);
    },
    get(token: string, id: number): Promise<EmployeeDetail> {
      return authed<EmployeeDetail>(`/api/employees/${id}`, token);
    },
    create(token: string, input: EmployeeInput): Promise<EmployeeCreateOut> {
      return authed<EmployeeCreateOut>("/api/employees", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: EmployeeInput): Promise<EmployeeUpdateOut> {
      return authed<EmployeeUpdateOut>(`/api/employees/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    transition(token: string, id: number, input: EmployeeTransitionInput): Promise<EmployeeDetail> {
      return authed<EmployeeDetail>(`/api/employees/${id}/transitions`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    events(token: string, id: number): Promise<{ items: EmployeeEvent[] }> {
      return authed<{ items: EmployeeEvent[] }>(`/api/employees/${id}/events`, token);
    },
    activity(token: string, id: number): Promise<{ items: EmployeeActivityRow[] }> {
      return authed<{ items: EmployeeActivityRow[] }>(`/api/employees/${id}/activity`, token);
    },
    attachments(token: string, id: number): Promise<{ items: EmployeeAttachment[] }> {
      return authed<{ items: EmployeeAttachment[] }>(`/api/employees/${id}/attachments`, token);
    },
    upload(token: string, id: number, file: File, docKind: string): Promise<EmployeeAttachment> {
      const form = new FormData();
      form.append("file", file);
      form.append("doc_kind", docKind);
      return authed<EmployeeAttachment>(`/api/employees/${id}/attachments`, token, {
        method: "POST",
        body: form,
      });
    },
    deleteAttachment(token: string, id: number, attachmentId: number): Promise<void> {
      return authed<void>(`/api/employees/${id}/attachments/${attachmentId}`, token, {
        method: "DELETE",
      });
    },
    linkAccount(token: string, id: number, userId: number): Promise<EmployeeDetail> {
      return authed<EmployeeDetail>(`/api/employees/${id}/account`, token, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
    },
    unlinkAccount(token: string, id: number): Promise<EmployeeDetail> {
      return authed<EmployeeDetail>(`/api/employees/${id}/account`, token, { method: "DELETE" });
    },
  },

  // --- Chấm công GPS (nhan_su) ----------------------------------------------
  attendance: {
    locations(token: string): Promise<{ items: WorkLocation[] }> {
      return authed<{ items: WorkLocation[] }>("/api/attendance/locations", token);
    },
    createLocation(token: string, input: WorkLocationInput): Promise<WorkLocation> {
      return authed<WorkLocation>("/api/attendance/locations", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateLocation(token: string, id: number, input: WorkLocationInput): Promise<WorkLocation> {
      return authed<WorkLocation>(`/api/attendance/locations/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    deleteLocation(token: string, id: number): Promise<void> {
      return authed<void>(`/api/attendance/locations/${id}`, token, { method: "DELETE" });
    },
    myStatus(token: string): Promise<AttendanceStatus> {
      return authed<AttendanceStatus>("/api/attendance/me/status", token);
    },
    check(token: string, latitude: number, longitude: number): Promise<CheckResult> {
      return authed<CheckResult>("/api/attendance/check", token, {
        method: "POST",
        body: JSON.stringify({ latitude, longitude }),
      });
    },
    myLogs(token: string): Promise<{ items: AttendanceLog[] }> {
      return authed<{ items: AttendanceLog[] }>("/api/attendance/me/logs", token);
    },
    logs(token: string, employeeId?: number): Promise<{ items: AttendanceLog[] }> {
      const suffix = employeeId != null ? `?employee_id=${employeeId}` : "";
      return authed<{ items: AttendanceLog[] }>(`/api/attendance/logs${suffix}`, token);
    },
    timesheet(token: string, year: number, month: number, departmentId?: number | null): Promise<Timesheet> {
      const qs = new URLSearchParams({ year: String(year), month: String(month) });
      if (departmentId != null) qs.set("department_id", String(departmentId));
      return authed<Timesheet>(`/api/attendance/timesheet?${qs.toString()}`, token);
    },
    /** Xuất bảng công tháng ra CSV — fetch as a blob (bearer + refresh-aware). */
    async timesheetCsvBlobUrl(token: string, year: number, month: number, departmentId?: number | null): Promise<string> {
      const qs = new URLSearchParams({ year: String(year), month: String(month) });
      if (departmentId != null) qs.set("department_id", String(departmentId));
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/attendance/timesheet.csv?${qs.toString()}`, {
          credentials: "include", cache: "no-store", headers: authHeader(bearer),
        });
      let resp = await doFetch(token);
      if (resp.status === 401) {
        const fresh = await refreshAccessToken();
        if (fresh) resp = await doFetch(fresh);
      }
      if (!resp.ok) throw new ApiError(`Export failed (${resp.status}).`, resp.status);
      const blob = await resp.blob();
      return URL.createObjectURL(blob);
    },
    // --- ca kíp (work shifts) ---
    shifts(token: string): Promise<{ items: WorkShift[] }> {
      return authed<{ items: WorkShift[] }>("/api/attendance/shifts", token);
    },
    createShift(token: string, input: WorkShiftInput): Promise<WorkShift> {
      return authed<WorkShift>("/api/attendance/shifts", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateShift(token: string, id: number, input: WorkShiftInput): Promise<WorkShift> {
      return authed<WorkShift>(`/api/attendance/shifts/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deleteShift(token: string, id: number): Promise<void> {
      return authed<void>(`/api/attendance/shifts/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Sản phẩm in (Product catalog), spec-07 -------------------------------
  products: {
    list(token: string, params: ProductListParams = {}): Promise<ProductListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.product_type) qs.set("product_type", params.product_type);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<ProductListOut>(`/api/products${suffix}`, token);
    },
    enums(token: string): Promise<ProductEnumsOut> {
      return authed<ProductEnumsOut>("/api/products/enums", token);
    },
    papers(token: string, q?: string): Promise<PaperPickerOut> {
      const suffix = q ? `?q=${encodeURIComponent(q)}` : "";
      return authed<PaperPickerOut>(`/api/products/papers${suffix}`, token);
    },
    get(token: string, id: number): Promise<ProductDetailOut> {
      return authed<ProductDetailOut>(`/api/products/${id}`, token);
    },
    create(token: string, input: ProductInput): Promise<ProductDetailOut> {
      return authed<ProductDetailOut>("/api/products", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: ProductInput): Promise<ProductDetailOut> {
      return authed<ProductDetailOut>(`/api/products/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/products/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Tính giá (Costing), spec-08 ------------------------------------------
  costings: {
    list(token: string, params: CostingListParams = {}): Promise<CostingListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.product_id != null) qs.set("product_id", String(params.product_id));
      if (params.status) qs.set("status", params.status);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<CostingListOut>(`/api/costings${suffix}`, token);
    },
    enums(token: string): Promise<CostingEnumsOut> {
      return authed<CostingEnumsOut>("/api/costings/enums", token);
    },
    papers(token: string): Promise<PaperCostPickerOut> {
      return authed<PaperCostPickerOut>("/api/costings/papers", token);
    },
    product(token: string, productId: number): Promise<ProductPickerOut> {
      return authed<ProductPickerOut>(`/api/costings/products/${productId}`, token);
    },
    suggestPieces(
      token: string,
      body: { sheet_w: number; sheet_h: number; piece_w: number; piece_h: number; grain_locked: boolean; gripper_cm?: number; edge_trim_cm?: number; bleed_cm?: number; gutter_cm?: number },
    ): Promise<SuggestPiecesOut> {
      return authed<SuggestPiecesOut>("/api/costings/suggest-pieces", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    get(token: string, id: number): Promise<CostingDetailOut> {
      return authed<CostingDetailOut>(`/api/costings/${id}`, token);
    },
    create(token: string, input: CostingInput): Promise<CostingDetailOut> {
      return authed<CostingDetailOut>("/api/costings", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: CostingInput): Promise<CostingDetailOut> {
      return authed<CostingDetailOut>(`/api/costings/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/costings/${id}`, token, { method: "DELETE" });
    },
  },

  estimates: {
    list(token: string, params: { q?: string; product_type?: string | null; status?: string | null; has_blocking?: boolean; sort?: string; page?: number; size?: number } = {}): Promise<EstimateListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.product_type) qs.set("product_type", params.product_type);
      if (params.status) qs.set("status", params.status);
      if (params.has_blocking) qs.set("has_blocking", "true");
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<EstimateListOut>(`/api/estimates${suffix}`, token);
    },
    /** Số đếm cho thanh tab list (backend mới có sau khi restart — caller phải catch). */
    stats(token: string): Promise<EstimateStats> {
      return authed<EstimateStats>("/api/estimates/stats", token);
    },
    get(token: string, id: number): Promise<EstimateDetail> {
      return authed<EstimateDetail>(`/api/estimates/${id}`, token);
    },
    create(token: string, input: EstimateInput): Promise<EstimateDetail> {
      return authed<EstimateDetail>("/api/estimates", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: EstimateInput): Promise<EstimateDetail> {
      return authed<EstimateDetail>(`/api/estimates/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/estimates/${id}`, token, { method: "DELETE" });
    },
    /** §9 — Khóa snapshot phiếu (chốt kết quả, không cho sửa nữa). */
    lock(token: string, id: number): Promise<EstimateDetail> {
      return authed<EstimateDetail>(`/api/estimates/${id}/lock`, token, { method: "POST" });
    },
    /** §7/§9 — Sao chép phiếu (làm mẫu / version mới nếu phiếu nguồn đã khóa). */
    duplicate(token: string, id: number): Promise<EstimateDetail> {
      return authed<EstimateDetail>(`/api/estimates/${id}/duplicate`, token, { method: "POST" });
    },
    /** Live preview (KHÔNG lưu): chạy engine với spec đang gõ để form hiện giá vốn tức thời. */
    preview(token: string, input: { input_spec: Record<string, unknown>; quantity: number }): Promise<EstimatePreviewOut> {
      return authed<EstimatePreviewOut>("/api/estimates/preview", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
  },

  // --- Báo giá (Quotation), spec-09 -----------------------------------------
  quotations: {
    list(token: string, params: QuotationListParams = {}): Promise<QuotationListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<QuotationListOut>(`/api/quotations${suffix}`, token);
    },
    enums(token: string): Promise<QuotationEnumsOut> {
      return authed<QuotationEnumsOut>("/api/quotations/enums", token);
    },
    /** Số đếm cho thanh tab list. */
    stats(token: string): Promise<QuotationStats> {
      return authed<QuotationStats>("/api/quotations/stats", token);
    },
    costing(token: string, costingId: number, _quantity?: number): Promise<CostingPickerOut> {
      return authed<CostingPickerOut>(`/api/quotations/costings/${costingId}`, token);
    },
    get(token: string, id: number): Promise<QuotationDetail> {
      return authed<QuotationDetail>(`/api/quotations/${id}`, token);
    },
    create(token: string, input: QuotationInput): Promise<QuotationDetail> {
      return authed<QuotationDetail>("/api/quotations", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: QuotationUpdateInput): Promise<QuotationDetail> {
      return authed<QuotationDetail>(`/api/quotations/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    transition(
      token: string,
      id: number,
      body: { to_status: string; cancel_reason?: string | null; row_version?: number | null },
    ): Promise<QuotationDetail> {
      return authed<QuotationDetail>(`/api/quotations/${id}/transition`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    requote(token: string, id: number): Promise<QuotationDetail> {
      return authed<QuotationDetail>(`/api/quotations/${id}/requote`, token, {
        method: "POST",
      });
    },
    /** Open the đối-ngoại PDF in a new tab (auth via bearer; returns a blob URL). Refresh-
     *  aware: if the in-memory access token has expired the fetch gets a 401, so we refresh
     *  ONCE (shared in-flight promise, no storm) and retry with the rotated token — exactly
     *  like `authed()`. cache:no-store keeps a stale entry from shadowing the response. */
    async pdfBlobUrl(token: string, id: number): Promise<string> {
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/quotations/${id}/pdf`, {
          credentials: "include",
          cache: "no-store",
          headers: { "Content-Type": "application/json", ...authHeader(bearer) },
        });
      let resp = await doFetch(token);
      if (resp.status === 401) {
        const fresh = await refreshAccessToken();
        if (fresh) resp = await doFetch(fresh);
      }
      if (!resp.ok) throw new ApiError(`PDF failed (${resp.status}).`, resp.status);
      const blob = await resp.blob();
      return URL.createObjectURL(blob);
    },
  },

  // --- Đơn hàng bán (Order), spec-10 ----------------------------------------
  orders: {
    list(token: string, params: OrderListParams = {}): Promise<OrderListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.order_kind) qs.set("order_kind", params.order_kind);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<OrderListOut>(`/api/orders${suffix}`, token);
    },
    enums(token: string): Promise<OrderEnumsOut> {
      return authed<OrderEnumsOut>("/api/orders/enums", token);
    },
    /** Báo giá đã duyệt còn hạn choosable for an order (F1, SEAM-04 quotation_ref). */
    approvedQuotations(token: string): Promise<{ items: ApprovedQuotationRow[] }> {
      return authed<{ items: ApprovedQuotationRow[] }>(
        "/api/orders/approved-quotations",
        token,
      );
    },
    get(token: string, id: number): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}`, token);
    },
    create(token: string, input: OrderInput): Promise<OrderDetail> {
      return authed<OrderDetail>("/api/orders", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    transition(
      token: string,
      id: number,
      body: { to_status: string; cancel_reason?: string | null },
    ): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/transition`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
  },

  // --- Product Types Catalog ------------------------------------------------
  productTypesCatalog: {
    list(token: string, params: CatalogListParams = {}): Promise<ProductTypeCatalogListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<ProductTypeCatalogListOut>(`/api/product-types-catalog${suffix}`, token);
    },
    get(token: string, id: number): Promise<ProductTypeCatalogRow> {
      return authed<ProductTypeCatalogRow>(`/api/product-types-catalog/${id}`, token);
    },
    create(token: string, input: ProductTypeCatalogInput): Promise<ProductTypeCatalogRow> {
      return authed<ProductTypeCatalogRow>("/api/product-types-catalog", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: ProductTypeCatalogInput): Promise<ProductTypeCatalogRow> {
      return authed<ProductTypeCatalogRow>(`/api/product-types-catalog/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/product-types-catalog/${id}`, token, { method: "DELETE" });
    },
    preview(token: string, id: number): Promise<ProductTypePreviewResult> {
      return authed<ProductTypePreviewResult>(`/api/product-types-catalog/${id}/preview`, token, {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    clone(token: string, id: number, body: { new_product_type: string; new_name: string }): Promise<ProductTypeCatalogRow> {
      return authed<ProductTypeCatalogRow>(`/api/product-types-catalog/${id}/clone`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
  },

  // --- Paper Sizes Catalog --------------------------------------------------
  paperSizes: {
    list(
      token: string,
      params: CatalogListParams & {
        size_type?: string | null;
        size_group?: string | null;
        machine_id?: number | null;
        is_active?: boolean | null;
        current_only?: boolean;
      } = {},
    ): Promise<PaperSizeListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.size_type) qs.set("size_type", params.size_type);
      if (params.size_group) qs.set("size_group", params.size_group);
      if (params.machine_id != null) qs.set("machine_id", String(params.machine_id));
      if (params.is_active != null) qs.set("is_active", String(params.is_active));
      if (params.current_only) qs.set("current_only", "true");
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PaperSizeListOut>(`/api/paper-sizes${suffix}`, token);
    },
    get(token: string, id: number): Promise<PaperSizeRow> {
      return authed<PaperSizeRow>(`/api/paper-sizes/${id}`, token);
    },
    history(token: string, id: number): Promise<PaperSizeListOut> {
      return authed<PaperSizeListOut>(`/api/paper-sizes/${id}/history`, token);
    },
    usage(token: string, id: number): Promise<PaperSizeUsageOut> {
      return authed<PaperSizeUsageOut>(`/api/paper-sizes/${id}/usage`, token);
    },
    checkDuplicate(
      token: string,
      params: { width: number; height: number; excludeId?: number | null },
    ): Promise<PaperSizeDuplicateOut> {
      const qs = new URLSearchParams();
      qs.set("width", String(params.width));
      qs.set("height", String(params.height));
      if (params.excludeId != null) qs.set("exclude_id", String(params.excludeId));
      return authed<PaperSizeDuplicateOut>(`/api/paper-sizes/check-duplicate?${qs.toString()}`, token);
    },
    create(token: string, input: PaperSizeInput): Promise<PaperSizeRow> {
      return authed<PaperSizeRow>("/api/paper-sizes", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: PaperSizeInput): Promise<PaperSizeRow> {
      return authed<PaperSizeRow>(`/api/paper-sizes/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    createVersion(token: string, id: number, input: PaperSizeInput): Promise<PaperSizeRow> {
      return authed<PaperSizeRow>(`/api/paper-sizes/${id}/version`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    clone(token: string, id: number): Promise<PaperSizeRow> {
      return authed<PaperSizeRow>(`/api/paper-sizes/${id}/clone`, token, { method: "POST" });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/paper-sizes/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Imposition Types Catalog (Kiểu bình bài) -----------------------------
  impositionTypes: {
    list(
      token: string,
      params: CatalogListParams & { current_only?: boolean; is_active?: boolean; code?: string } = {},
    ): Promise<ImpositionTypeListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.code) qs.set("code", params.code);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      if (params.current_only) qs.set("current_only", "true");
      if (params.is_active !== undefined) qs.set("is_active", String(params.is_active));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<ImpositionTypeListOut>(`/api/imposition-types${suffix}`, token);
    },
    get(token: string, id: number): Promise<ImpositionTypeRow> {
      return authed<ImpositionTypeRow>(`/api/imposition-types/${id}`, token);
    },
    create(token: string, input: ImpositionTypeInput): Promise<ImpositionTypeRow> {
      return authed<ImpositionTypeRow>("/api/imposition-types", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: ImpositionTypeInput): Promise<ImpositionTypeRow> {
      return authed<ImpositionTypeRow>(`/api/imposition-types/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/imposition-types/${id}`, token, { method: "DELETE" });
    },
    // Kiểm thử nhanh — engine thật tính qua imposition_math (không lệch client/server).
    preview(token: string, input: ImpositionPreviewRequest): Promise<ImpositionPreviewOut> {
      return authed<ImpositionPreviewOut>("/api/imposition-types/preview", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    // "Xem tính giá đã dùng" — danh sách estimates đang dùng quy tắc.
    usage(token: string, id: number): Promise<ImpositionUsageOut> {
      return authed<ImpositionUsageOut>(`/api/imposition-types/${id}/usage`, token);
    },
  },

  // --- Materials Catalog ----------------------------------------------------
  materials: {
    list(token: string, params: CatalogListParams & { material_type?: string | null } = {}): Promise<MaterialListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.material_type) qs.set("material_type", params.material_type);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<MaterialListOut>(`/api/materials${suffix}`, token);
    },
    get(token: string, id: number): Promise<MaterialRow> {
      return authed<MaterialRow>(`/api/materials/${id}`, token);
    },
    create(token: string, input: MaterialInput): Promise<MaterialRow> {
      return authed<MaterialRow>("/api/materials", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: MaterialInput): Promise<MaterialRow> {
      return authed<MaterialRow>(`/api/materials/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    toggleActive(token: string, id: number): Promise<MaterialRow> {
      return authed<MaterialRow>(`/api/materials/${id}/toggle-active`, token, {
        method: "PATCH",
      });
    },
    clone(token: string, id: number, body: { gsm: number; width_cm: number; height_cm: number }): Promise<MaterialRow> {
      return authed<MaterialRow>(`/api/materials/${id}/clone`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    addCost(token: string, id: number, input: MaterialCostInput): Promise<MaterialCostRow> {
      return authed<MaterialCostRow>(`/api/materials/${id}/costs`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    costHistory(token: string, id: number): Promise<MaterialCostRow[]> {
      return authed<MaterialCostRow[]>(`/api/materials/${id}/costs/history`, token);
    },
    convert(token: string, body: { gsm: number; width_cm: number; height_cm: number }): Promise<MaterialConvertOut> {
      return authed<MaterialConvertOut>("/api/materials/convert", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    priceTest(token: string, input: MaterialPriceTestInput): Promise<MaterialPriceTestOut> {
      return authed<MaterialPriceTestOut>("/api/materials/price-test", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/materials/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Machines Catalog -----------------------------------------------------
  machines: {
    list(token: string, params: CatalogListParams & { machine_type?: string | null } = {}): Promise<MachineListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.machine_type) qs.set("machine_type", params.machine_type);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<MachineListOut>(`/api/machines${suffix}`, token);
    },
    get(token: string, id: number): Promise<MachineRow> {
      return authed<MachineRow>(`/api/machines/${id}`, token);
    },
    create(token: string, input: MachineInput): Promise<MachineRow> {
      return authed<MachineRow>("/api/machines", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: MachineInput): Promise<MachineRow> {
      return authed<MachineRow>(`/api/machines/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    addRate(token: string, id: number, input: MachineRateInput): Promise<MachineRateRow> {
      return authed<MachineRateRow>(`/api/machines/${id}/rates`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/machines/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Operations Catalog ---------------------------------------------------
  operations: {
    list(token: string, params: CatalogListParams & { operation_type?: string | null } = {}): Promise<OperationCatalogListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.operation_type) qs.set("operation_type", params.operation_type);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<OperationCatalogListOut>(`/api/operations${suffix}`, token);
    },
    get(token: string, id: number): Promise<OperationCatalogRow> {
      return authed<OperationCatalogRow>(`/api/operations/${id}`, token);
    },
    create(token: string, input: OperationCatalogInput): Promise<OperationCatalogRow> {
      return authed<OperationCatalogRow>("/api/operations", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: OperationCatalogInput): Promise<OperationCatalogRow> {
      return authed<OperationCatalogRow>(`/api/operations/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    addRate(token: string, id: number, input: OperationCatalogRateInput): Promise<OperationCatalogRateRow> {
      return authed<OperationCatalogRateRow>(`/api/operations/${id}/rates`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/operations/${id}`, token, { method: "DELETE" });
    },
    preview(token: string, id: number, input: OperationPreviewInput): Promise<OperationPreviewResult> {
      return authed<OperationPreviewResult>(`/api/operations/${id}/preview`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
  },

  // --- Cấu hình kho hàng ----------------------------------------------------
  warehouses: {
    list(
      token: string,
      params: { q?: string; is_active?: boolean | null; sort?: string; page?: number; size?: number } = {},
    ): Promise<WarehouseListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.is_active !== undefined && params.is_active !== null)
        qs.set("is_active", String(params.is_active));
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<WarehouseListOut>(`/api/warehouses${suffix}`, token);
    },
    create(token: string, input: WarehouseInput): Promise<WarehouseRow> {
      return authed<WarehouseRow>("/api/warehouses", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: WarehouseInput): Promise<WarehouseRow> {
      return authed<WarehouseRow>(`/api/warehouses/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/warehouses/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Kho hàng vận hành ----------------------------------------------------
  warehouseItems: {
    options(token: string): Promise<WarehouseOption[]> {
      return authed<WarehouseOption[]>("/api/warehouse-items/warehouse-options", token);
    },
    list(
      token: string,
      params: { warehouse_id?: number | null; q?: string; page?: number; size?: number } = {},
    ): Promise<WarehouseItemListOut> {
      const qs = new URLSearchParams();
      if (params.warehouse_id !== undefined && params.warehouse_id !== null)
        qs.set("warehouse_id", String(params.warehouse_id));
      if (params.q) qs.set("q", params.q);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<WarehouseItemListOut>(`/api/warehouse-items${suffix}`, token);
    },
    create(token: string, input: WarehouseItemInput): Promise<WarehouseItemRow> {
      return authed<WarehouseItemRow>("/api/warehouse-items", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: WarehouseItemInput): Promise<WarehouseItemRow> {
      return authed<WarehouseItemRow>(`/api/warehouse-items/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/warehouse-items/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Plate/Die Rates ------------------------------------------------------
  plateDieRates: {
    list(token: string, params: { q?: string | null; plate_type?: string | null; technology?: string | null; machine_id?: number | null; is_active?: boolean | null; current_only?: boolean; page?: number; size?: number } = {}): Promise<PlateDieRateListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.plate_type) qs.set("plate_type", params.plate_type);
      if (params.technology) qs.set("technology", params.technology);
      if (params.machine_id != null) qs.set("machine_id", String(params.machine_id));
      if (params.is_active !== undefined && params.is_active !== null) qs.set("is_active", String(params.is_active));
      if (params.current_only) qs.set("current_only", "true");
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PlateDieRateListOut>(`/api/plate-die-rates${suffix}`, token);
    },
    get(token: string, id: number): Promise<PlateDieRateRow> {
      return authed<PlateDieRateRow>(`/api/plate-die-rates/${id}`, token);
    },
    history(token: string, id: number): Promise<PlateDieRateListOut> {
      return authed<PlateDieRateListOut>(`/api/plate-die-rates/${id}/history`, token);
    },
    create(token: string, input: PlateDieRateInput): Promise<PlateDieRateRow> {
      return authed<PlateDieRateRow>("/api/plate-die-rates", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    createVersion(token: string, id: number, input: PlateDieRateInput): Promise<PlateDieRateRow> {
      return authed<PlateDieRateRow>(`/api/plate-die-rates/${id}/version`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    clone(token: string, id: number): Promise<PlateDieRateRow> {
      return authed<PlateDieRateRow>(`/api/plate-die-rates/${id}/clone`, token, { method: "POST" });
    },
    usage(token: string, id: number): Promise<PlateDieRateUsageOut> {
      return authed<PlateDieRateUsageOut>(`/api/plate-die-rates/${id}/usage`, token);
    },
    close(token: string, id: number, effectiveTo: string): Promise<PlateDieRateRow> {
      return authed<PlateDieRateRow>(`/api/plate-die-rates/${id}/close`, token, {
        method: "POST",
        body: JSON.stringify({ effective_to: effectiveTo }),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/plate-die-rates/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Norms Catalog (Định mức & Bù hao) ------------------------------------
  norms: {
    list(token: string, params: { q?: string | null; norm_key?: string | null; waste_group?: string | null; product_type?: string | null; machine_id?: number | null; operation_id?: number | null; only_current?: boolean; page?: number; size?: number } = {}): Promise<NormListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.norm_key) qs.set("norm_key", params.norm_key);
      if (params.waste_group) qs.set("waste_group", params.waste_group);
      if (params.product_type) qs.set("product_type", params.product_type);
      if (params.machine_id !== undefined && params.machine_id !== null) qs.set("machine_id", String(params.machine_id));
      if (params.operation_id !== undefined && params.operation_id !== null) qs.set("operation_id", String(params.operation_id));
      if (params.only_current) qs.set("only_current", "true");
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<NormListOut>(`/api/norms${suffix}`, token);
    },
    get(token: string, id: number): Promise<NormRow> {
      return authed<NormRow>(`/api/norms/${id}`, token);
    },
    create(token: string, input: NormInput): Promise<NormRow> {
      return authed<NormRow>("/api/norms", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    close(token: string, id: number, effectiveTo: string): Promise<NormRow> {
      return authed<NormRow>(`/api/norms/${id}/close`, token, {
        method: "POST",
        body: JSON.stringify({ effective_to: effectiveTo }),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/norms/${id}`, token, { method: "DELETE" });
    },
    duplicate(token: string, id: number, effectiveFrom: string, code?: string | null): Promise<NormRow> {
      return authed<NormRow>(`/api/norms/${id}/duplicate`, token, {
        method: "POST",
        body: JSON.stringify({ effective_from: effectiveFrom, code: code ?? null }),
      });
    },
    history(token: string, id: number): Promise<NormListOut> {
      return authed<NormListOut>(`/api/norms/${id}/history`, token);
    },
    usage(token: string, id: number): Promise<NormUsageOut> {
      return authed<NormUsageOut>(`/api/norms/${id}/usage`, token);
    },
    conflicts(token: string): Promise<NormConflictsOut> {
      return authed<NormConflictsOut>("/api/norms/conflicts", token);
    },
    test(token: string, input: NormTestInput): Promise<NormTestOutput> {
      return authed<NormTestOutput>("/api/norms/test", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
  },
};

export interface PlateDieRateRow {
  id: number;
  code: string;
  name: string;
  plate_type: string;
  technology: string;
  unit: string;
  plate_kind: string | null;
  plate_width_mm: number | null;
  plate_height_mm: number | null;
  machine_ids: number[] | null;
  paper_size_ids: number[] | null;
  unit_price: number;
  setup_fee: number;
  min_charge: number;
  pricing_method: string;
  unit_price_area: number;
  unit_price_perimeter: number;
  max_charge: number | null;
  allow_manual_price: boolean;
  reusable: boolean;
  reuse_price_method: string | null;
  maintenance_fee: number;
  supplier: string | null;
  lead_time_days: number;
  transport_fee: number;
  moq: number;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  used_count: number;
  /** "Đang dùng trong": kẽm = số phiếu tính giá; khuôn = số công đoạn. Server tính khi list. */
  used_in_estimates: number;
  used_in_operations: number;
  created_by: number | null;
  updated_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface PlateDieUsageEstimate {
  id: number;
  estimate_number: string;
  product_name: string;
  status: string;
  created_at: string;
}

export interface PlateDieUsageOperation {
  id: number;
  code: string;
  name: string;
  operation_type: string;
}

export interface PlateDieRateUsageOut {
  rate_id: number;
  code: string;
  name: string;
  kind: "kem" | "khuon";
  estimates: PlateDieUsageEstimate[];
  operations: PlateDieUsageOperation[];
}

export interface PlateDieRateInput {
  code?: string;
  name: string;
  plate_type: string;
  technology: string;
  unit: string;
  plate_kind?: string | null;
  plate_width_mm?: number | null;
  plate_height_mm?: number | null;
  machine_ids?: number[] | null;
  paper_size_ids?: number[] | null;
  unit_price?: number;
  setup_fee?: number;
  min_charge?: number;
  pricing_method?: string;
  unit_price_area?: number;
  unit_price_perimeter?: number;
  max_charge?: number | null;
  allow_manual_price?: boolean;
  reusable?: boolean;
  reuse_price_method?: string | null;
  maintenance_fee?: number;
  supplier?: string | null;
  lead_time_days?: number;
  transport_fee?: number;
  moq?: number;
  is_active?: boolean;
  effective_from: string;
}

export interface PlateDieRateListOut {
  items: PlateDieRateRow[];
  total: number;
  page: number;
  size: number;
}

export type WasteGroup = "YIELD_RATE" | "SETUP_WASTE" | "RUNNING_WASTE" | "PAPER_EXTRA_WASTE";

export interface NormRow {
  id: number;
  norm_key: string;
  waste_group: WasteGroup | null;
  calculation_method: string | null;
  value: number;
  code: string | null;
  name: string | null;
  product_type: string | null;
  machine_id: number | null;
  operation_id: number | null;
  operation_key: string | null;
  applicable_product_types: string[] | null;
  applicable_machine_ids: number[] | null;
  qty_min: number | null;
  qty_max: number | null;
  context: any | null;
  context_key: string;
  setup_waste_qty: number | null;
  setup_waste_per_color: number | null;
  setup_waste_per_side: number | null;
  min_waste_qty: number | null;
  max_waste_qty: number | null;
  paper_add_to_purchase: boolean;
  priority: number;
  version: number;
  used_count: number;
  estimate_count: number;
  effective_from: string;
  effective_to: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface NormUsageEstimate {
  id: number;
  estimate_number: string;
  product_name: string;
  status: string;
  created_at: string;
}

export interface NormUsageOut {
  norm_id: number;
  code: string;
  estimate_count: number;
  estimates: NormUsageEstimate[];
}

export interface NormConflictsOut {
  // keys là norm_id (chuỗi trong JSON) → danh sách norm_id có thể xung đột.
  conflicts: Record<string, number[]>;
  labels: Record<string, string>;
}

export interface NormInput {
  norm_key?: string | null;
  waste_group?: WasteGroup | null;
  calculation_method?: string | null;
  value?: number;
  code?: string | null;
  name?: string | null;
  product_type?: string | null;
  machine_id?: number | null;
  operation_id?: number | null;
  operation_key?: string | null;
  applicable_product_types?: string[] | null;
  applicable_machine_ids?: number[] | null;
  qty_min?: number | null;
  qty_max?: number | null;
  context?: any | null;
  setup_waste_qty?: number | null;
  setup_waste_per_color?: number | null;
  setup_waste_per_side?: number | null;
  min_waste_qty?: number | null;
  max_waste_qty?: number | null;
  paper_add_to_purchase?: boolean;
  priority?: number;
  effective_from: string;
  note?: string | null;
}

export interface NormListOut {
  items: NormRow[];
  total: number;
  page: number;
  size: number;
}

export interface NormTestInput {
  quantity: number;
  pieces_per_sheet: number;
  colors: number;
  sides: number;
  forms: number;
  product_type?: string | null;
  machine_id?: number | null;
  operation_keys: string[];
}

export interface NormTestStep {
  label: string;
  detail: string;
  rule_code: string | null;
  value: number | null;
}

export interface NormTestOutput {
  theoretical_sheets: number;
  required_before_print: number;
  sheets_after_yield: number;
  makeready_sheets: number;
  running_sheets: number;
  production_sheets: number;
  paper_extra_sheets: number;
  purchase_sheets: number;
  steps: NormTestStep[];
  warnings: string[];
}

