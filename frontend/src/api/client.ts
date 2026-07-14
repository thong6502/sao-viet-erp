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

export async function authed<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
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
  /** Số HỒ SƠ nhân sự của phòng (Đ2: 'số nhân sự' theo hồ sơ, tách khỏi số tài khoản). */
  employee_count?: number;
  /** Branch-rolled-up counts (department + every descendant) — PBI-4001. */
  total_role_count?: number;
  total_user_count?: number;
  total_employee_count?: number;
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
  can_view_discount: boolean;
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
  can_view_salary: boolean;
  can_adjust: boolean;
  /** A2: don_hang_ban — GĐ duyệt "đơn đặc thù" (chỉ Giám đốc). */
  can_approve_exception: boolean;
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
  can_view_discount: boolean;
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
  can_view_salary: boolean;
  can_adjust: boolean;
  can_approve_exception: boolean;
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
  /** Điều khoản thanh toán riêng (#12) — dữ liệu chờ Công nợ. */
  payment_term_type?: string | null;
  payment_term_days?: number | null;
  prepay_pct?: number | null;
  payment_term_note?: string | null;
  /** Chiết khấu riêng theo KH (#14) — null + discount_hidden khi thiếu quyền `view_discount`. */
  discount_trade_pct?: number | null;
  discount_buyer_pct?: number | null;
  discount_hidden?: boolean;
  /** Nhãn thủ công (#7) — sales gán tay. */
  tags?: string[];
}

/** List header KPI strip — rolled up over the whole scoped book from real orders. */
export interface CustomerKpis {
  total_customers: number;
  loyal_count: number;
  new_this_month: number;
  avg_order_value: number;
  partner_count?: number;
  total_revenue?: number;
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
  kind: "profile" | "order" | "quote" | "care";
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

/** Cảnh báo trùng MỀM theo tiêu chí (#15): field ∈ tax_code | name | email. */
export interface DuplicateWarn {
  field: "tax_code" | "name" | "email";
  id: number;
  code: string;
  name: string;
}

export interface CustomerCreateOut {
  customer: CustomerRow;
  duplicate: DuplicateRef | null;
  duplicates: DuplicateWarn[];
}

// --- Người liên hệ / địa chỉ giao hàng / tài liệu (khảo sát #9–#11, #21) -----

export interface CustomerContact {
  id: number;
  name: string;
  title: string | null;
  duty: string | null;
  phone: string | null;
  email: string | null;
  is_primary: boolean;
}

export interface CustomerContactInput {
  name: string;
  title: string | null;
  duty: string | null;
  phone: string | null;
  email: string | null;
  is_primary: boolean;
}

export interface CustomerAddress {
  id: number;
  label: string;
  address: string;
  phone: string | null;
  note: string | null;
  is_default: boolean;
}

export interface CustomerAddressInput {
  label: string;
  address: string;
  phone: string | null;
  note: string | null;
  is_default: boolean;
}

export interface CustomerAttachment {
  id: number;
  doc_kind: string;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_at: string;
}

// --- Chăm sóc khách hàng (#20/#27/#28) ---------------------------------------

export interface CareEvent {
  id: number;
  kind: string;
  note: string;
  happened_at: string;
  actor_name: string | null;
}

export interface CareTask {
  id: number;
  note: string;
  due_date: string;
  status: "open" | "done" | "cancelled";
  assignee_user_id: number | null;
  assignee_name: string | null;
  done_at: string | null;
  /** Mức nhắc tính từ số ngày quá hạn: 0 chưa đến hạn, 1/2/3 = nhắc lần 1/2/3. */
  remind_level: number;
  overdue_days: number;
}

export interface CareTasksOut {
  items: CareTask[];
  done_on_time: number;
  done_late: number;
  overdue_open: number;
}

/** Một việc đến hạn/quá hạn trong panel "Cần chăm sóc" trên danh bạ. */
export interface FollowupRow {
  id: number;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  note: string;
  due_date: string;
  remind_level: number;
  overdue_days: number;
  assignee_name: string | null;
}

/** Kết quả import CSV (#23): dry_run=true → chỉ xem trước, chưa ghi. */
export interface ImportRowResult {
  row: number;
  status: "created" | "warning" | "error";
  message: string | null;
  code: string | null;
  name: string | null;
}

export interface ImportResultOut {
  dry_run: boolean;
  total: number;
  created: number;
  warnings: number;
  errors: number;
  rows: ImportRowResult[];
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
  /** lead = tiềm năng (#22), active, inactive. Create mặc định active nếu bỏ trống. */
  status?: string;
  /** Điều khoản thanh toán (#12). */
  payment_term_type?: string | null;
  payment_term_days?: number | null;
  prepay_pct?: number | null;
  payment_term_note?: string | null;
  /** Chiết khấu (#14) — backend bỏ qua nếu thiếu quyền `view_discount`; khi Sửa,
   * null = giữ nguyên (xóa CK → gửi 0). */
  discount_trade_pct?: number | null;
  discount_buyer_pct?: number | null;
}

export interface CustomerListParams {
  q?: string;
  sale?: number | null;
  tier?: string | null;
  status?: string | null;
  tag?: string | null;
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

// Phiếu tính giá 4 nhóm (BE: estimate_to_phieu) — snake_case y hệt JSON trả về.
export interface PhieuTinhGiaColOut {
  key: string;
  label: string;
  align?: "left" | "right" | "center";
  // Engine mới trả "number"/"money"; giữ "num"/"formula" cho tương thích phiếu in.
  kind?: "text" | "num" | "formula" | "number" | "money";
}
export interface PhieuTinhGiaGroupOut {
  idx: string;
  name: string;
  columns: PhieuTinhGiaColOut[];
  rows: Array<Record<string, string | number | null>>;
  subtotal: number;
}
export interface PhieuTinhGiaPrintOut {
  header: {
    so_phieu: string;
    ngay_lap: string | null;
    ten_an_pham: string;
    so_luong: number;
    kho_thanh_pham: string;
    dvt: string;
  };
  noi_dung: Array<{ label: string; text: string }>;
  groups: PhieuTinhGiaGroupOut[];
  grand_total: number;
}

// Engine tính giá MỚI (/api/tinh-gia/preview) — không lưu, trả 4 nhóm + cảnh báo.
export interface TinhGiaPreviewIn {
  qty: number;
  pieces_per_sheet: number;
  so_mau: number;
  so_mat: number;
  giay_id: number | null;
  loai_san_pham_id?: number | null;
  cong_doan_ids?: number[];
}
/** Số [Hiện] read-only của 1 thành phần (từ result.meta.components) — soi số cho KTV. */
export interface TinhGiaComponentMeta {
  idx: number;
  name: string;
  gia_von_tp: number;
  so_luong: number; // SL dùng cho sản phẩm này (0 = lấy SL mặc định phiếu)
  gia_von_don: number; // giá vốn / SL của sản phẩm này (đơn giá riêng)
  con: number; // ④ con/tờ engine chốt
  con_auto: boolean;
  so_manh_xa: number; // ① → ② số mảnh xả
  to_net: number; // tờ in NET
  to_gross: number; // tờ in GROSS (đã bù hao)
  to_nguyen: number; // tờ giấy nguyên
  so_kem: number;
  so_luot: number;
}
/** Meta cấp phiếu — tổng hợp nhiều sản phẩm. */
export interface TinhGiaMeta {
  so_luong?: number; // SL mặc định phiếu
  tong_so_luong?: number; // Σ SL các sản phẩm
  so_thanh_phan?: number; // = số sản phẩm
  gia_von_don?: number; // đơn giá BÌNH QUÂN (Σ giá vốn / Σ SL)
  components?: TinhGiaComponentMeta[];
}
export interface TinhGiaPreviewOut {
  meta?: TinhGiaMeta;
  groups: PhieuTinhGiaGroupOut[];
  grand_total: number;
  warnings: string[];
}

/** Bình bài live (POST /api/tinh-gia/binh-bai) — mm; chua_mm = tổng 5 chừa (cm) × 10. */
export interface BinhBaiIn {
  kho_in_dai: number;
  kho_in_rong: number;
  dai_thanh_pham: number;
  rong_thanh_pham: number;
  chua_mm: number;
}
export interface BinhBaiOut {
  con: number;
  cols: number;
  rows: number;
  rotated: boolean;
  usable_dai: number;
  usable_rong: number;
  kho_in_dai: number;
  kho_in_rong: number;
  dai_tp: number;
  rong_tp: number;
  hieu_suat: number;
}

// --- Phiếu tính giá (PERSISTED costing tickets) — master/detail của "Tính giá" ---
// Mô hình MỚI theo THÀNH PHẦN: 1 phiếu = nhiều "Thành phần" (mỗi cái = giấy + kỹ thuật in +
// màu + gia công sau in). List item 2 tầng (sản phẩm + số thành phần); detail lồng nested.
export interface PhieuTinhGiaListItem {
  id: number;
  ma: string;
  ten_san_pham: string;
  loai_san_pham_id: number | null;
  kho_thanh_pham: string | null;
  so_luong: number;
  gia_von_don: number;
  tong_gia_von: number;
  ktv: string | null;
  so_thanh_phan: number;
  ngay: string | null;
}
export interface PhieuTinhGiaListOut {
  items: PhieuTinhGiaListItem[];
  total: number;
}

/** 1 dòng gia công sau in (finishing) thuộc 1 thành phần. */
export interface ThanhPhamOut {
  id: number;
  thanh_phan_id: number;
  thu_tu: number;
  cong_doan_id: number | null;
  ten: string;
  don_gia: number;
  so_luong: number;
  bu_hao: boolean;
  so_mat: number;
  so_vi_tri: number;
  dien_tich: number;
  nha_cung_cap: string | null;
  ghi_chu: string | null;
}

/** 1 thành phần giấy (paper component): giấy + kỹ thuật in + màu + list gia công. */
export interface ThanhPhanOut {
  id: number;
  phieu_id: number;
  thu_tu: number;
  loai_thanh_phan: string;
  ten: string;
  kho_thanh_pham: string | null; // nhãn hiển thị tự do
  dai_thanh_pham: number; // ③ khổ thành phẩm (mm)
  rong_thanh_pham: number; // ③
  kho_mo_rong: string | null;
  tay_gap: string | null;
  so_to_per_sp: number;
  so_luong: number; // SL đặt của sản phẩm này (0 = lấy SL mặc định phiếu)
  loai_san_pham_id: number | null; // loại SP của sản phẩm này
  // Giấy in
  giay_id: number | null;
  kho_nguyen: string | null; // ① nhãn hiển thị
  don_gia_giay: number;
  don_gia_don_vi: string; // "to" | "tan"
  nguon_giay: string; // "cong_ty" | "khach"
  bu_hao_so_to: number;
  chua_xen: number;
  chua_tay_ke: number;
  chua_nhip: number;
  chua_duoi: number;
  chua_ca_gay: number;
  // Kỹ thuật in
  co_in: boolean;
  che_ban_loai: string | null;
  che_ban_don_gia: number;
  quy_cach_in: string; // "mot_mat" | "hai_mat" | "tu_tro"
  kho_in_dai: number; // ② khổ tờ in (mm)
  kho_in_rong: number; // ②
  so_con: number; // ④ con/tờ (override khi con_auto=false)
  con_auto: boolean; // true: engine tự bình bài
  may_id: number | null;
  don_gia_cong_in: number; // mực GỘP trong đây
  // Màu in (gộp — chỉ số màu mỗi mặt)
  so_mau_a: number;
  so_mau_b: number;
  gia_von_tp: number;
  thanh_phams: ThanhPhamOut[];
}

/** Detail đầy đủ 1 phiếu — `result` tái dùng TinhGiaPreviewOut (engine dict 4 nhóm). */
export interface PhieuTinhGiaOut {
  id: number;
  ma: string;
  ten_san_pham: string;
  kho_thanh_pham: string | null;
  loai_san_pham_id: number | null;
  so_luong: number;
  tong_gia_von: number;
  gia_von_don: number;
  result: TinhGiaPreviewOut | null;
  warnings: string[] | null;
  ktv: string | null;
  ghi_chu: string | null;
  thanh_phans: ThanhPhanOut[];
  created_at: string | null;
  updated_at: string | null;
}

/** Input 1 dòng gia công — tất cả optional (BE tự đổ mặc định). */
export interface ThanhPhamIn {
  cong_doan_id?: number | null;
  ten?: string;
  don_gia?: number;
  so_luong?: number;
  bu_hao?: boolean;
  so_mat?: number;
  so_vi_tri?: number;
  dien_tich?: number;
  nha_cung_cap?: string | null;
  ghi_chu?: string | null;
}
/** Input 1 thành phần — mọi field optional + list gia công. */
export interface ThanhPhanIn {
  loai_thanh_phan?: string;
  ten?: string;
  kho_thanh_pham?: string | null;
  dai_thanh_pham?: number;
  rong_thanh_pham?: number;
  kho_mo_rong?: string | null;
  tay_gap?: string | null;
  so_to_per_sp?: number;
  so_luong?: number; // SL đặt của sản phẩm này (0 = SL mặc định phiếu)
  loai_san_pham_id?: number | null; // loại SP của sản phẩm này
  giay_id?: number | null;
  kho_nguyen?: string | null;
  don_gia_giay?: number;
  don_gia_don_vi?: string;
  nguon_giay?: string;
  bu_hao_so_to?: number;
  chua_xen?: number;
  chua_tay_ke?: number;
  chua_nhip?: number;
  chua_duoi?: number;
  chua_ca_gay?: number;
  co_in?: boolean;
  che_ban_loai?: string | null;
  che_ban_don_gia?: number;
  quy_cach_in?: string;
  kho_in_dai?: number;
  kho_in_rong?: number;
  so_con?: number;
  con_auto?: boolean;
  may_id?: number | null;
  don_gia_cong_in?: number;
  so_mau_a?: number;
  so_mau_b?: number;
  thanh_phams?: ThanhPhamIn[];
}
/** Field khởi tạo phiếu (tất cả optional — BE auto `ma`). */
export interface PhieuTinhGiaCreate {
  ten_san_pham?: string;
  kho_thanh_pham?: string | null;
  loai_san_pham_id?: number | null;
  so_luong?: number;
  ghi_chu?: string | null;
  thanh_phans?: ThanhPhanIn[];
}
/** PUT: REPLACE-ALL con — BE tự tính lại + snapshot. */
export type PhieuTinhGiaUpdate = PhieuTinhGiaCreate;

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
  pending_approval: number;
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
  phieu_tinh_gia_id: number | null;
  phieu_tinh_gia_ma: string | null;
  valid_until: string | null;
  status: string;
  cancel_reason: string | null;
  payment_terms: string | null;
  delivery_terms: string | null;
  delivery_address: string | null;
  contact_name_snapshot: string | null;
  contact_phone_snapshot: string | null;
  contact_title_snapshot: string | null;
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
  // BG-2 — báo giá đặc thù (GĐ duyệt trước khi gửi khách). `margin_pct` null nếu người xem không có
  // quyền duyệt đặc thù (không rò biên cho Sales).
  exception_required: boolean;
  exception_status: "none" | "pending" | "approved" | "rejected" | "stale";
  exception_cleared: boolean;
  exceptions: { key: string; label: string }[];
  exception_note: string | null;
  margin_pct: number | null;
  // Ai SOẠN (người duyệt biết báo giá của NV nào) + ai ĐÃ DUYỆT/từ chối (NV biết ai xử lý).
  salesperson_id?: number | null;
  salesperson_name?: string | null;
  exception_decision?: "approved" | "rejected" | null;
  exception_decided_by_name?: string | null;
  exception_decided_at?: string | null;
}

export interface QuotationInput {
  customer_id: number | null;
  /** BG-1 (nguồn MỚI): 1 Phiếu tính giá (PTG) → 1 báo giá. */
  phieu_tinh_gia_id?: number | null;
  estimate_id?: number | null;
  selected_option_ids?: number[] | null;
  /** Đường đa phiếu (cũ): mỗi pick = 1 phiếu tính giá + option đã tick. */
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

/** Một điều kiện "đơn đặc thù" đang bật (A2) — nhãn định tính, an toàn cho mọi vai. */
export interface OrderException {
  key: string;   // high_value | low_margin | below_cost
  label: string;
}

/** ③→④ gate (F3). deposit_paid=null + deposit_available=false while SEAM-04 (Payment) is TREO.
 *  A2: thêm khối "đơn đặc thù" — Giám đốc duyệt mới chốt được. */
export interface OrderGate {
  total: number;
  total_payment: number;        // tổng GỒM VAT — base tính cọc (số khách phải trả)
  min_deposit_pct: number;
  deposit_required: number;
  deposit_paid: number | null;
  deposit_available: boolean;
  deposit_shortfall: number;
  quotation_approved: boolean;
  all_lines_priced: boolean;
  // A2 — đơn đặc thù (GĐ duyệt).
  exception_required: boolean;
  exception_status: "none" | "pending" | "approved" | "rejected" | "stale";
  exception_cleared: boolean;
  exceptions: OrderException[];
  exception_note: string | null;
  margin_pct: number | null;    // số nhạy cảm — null nếu người xem không có quyền duyệt đặc thù
  can_confirm: boolean;
}

/** Một bản duyệt/từ chối "đơn đặc thù" (A2) — chỉ GĐ xem (chứa số biên/giá vốn). */
export interface OrderApproval {
  id: number;
  order_id: number;
  decision: string;             // approved | rejected
  triggers_json: string[] | null;
  order_total: number;
  order_subtotal: number;
  order_cost: number | null;
  margin_pct_snapshot: number | null;
  min_margin_pct: number | null;
  high_value_threshold: number | null;
  note: string | null;
  decided_by: number | null;
  decided_at: string;
}

export interface OrderApprovalListOut {
  items: OrderApproval[];
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

/** Khoản thu của đơn (cọc/đợt) — SEAM-04 deposit (feat-048). */
export interface Payment {
  id: number;
  order_id: number;
  customer_id: number | null;
  kind: string;
  direction: string;
  amount: number;
  method: string;
  paid_at: string;
  voucher_no: string | null;
  note: string | null;
}

export interface PaymentListOut {
  items: Payment[];
  deposit_total: number;
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

export type MaterialGroup = "paper" | "ink" | "film" | "glue" | "packaging" | "auxiliary";

export interface MaterialCostRow {
  id: number;
  material_id?: number;
  price_unit: string;
  unit_price: number;
  supplier: string | null;
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
  default_shift_id: number | null;
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
  payroll_group: string | null;
  pay_grade_key: string | null;
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
  payroll_group?: string | null;
  pay_grade_key?: string | null;
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

// --- "Hồ sơ của tôi" (self-service, nhân viên thường) ---
export interface MyProfile {
  has_employee: boolean;
  employee: EmployeeDetail | null;
}
export interface MyContactInput {
  phone?: string | null;
  email?: string | null;
  current_address?: string | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
}

// Yêu cầu cập nhật hồ sơ (NV đề nghị → HCNS duyệt).
export interface UpdateRequest {
  id: number;
  employee_id: number;
  employee_name: string | null;
  changes: Record<string, string | number | null>;
  reason: string | null;
  status: string;
  decision_note: string | null;
  created_at: string;
}
export interface UpdateRequestInput {
  changes: Record<string, string | number | null>;
  reason?: string | null;
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

export interface AttendancePreview {
  locations_configured: boolean;
  within_range: boolean;
  distance_m: number | null;
  meters_out: number | null;   // còn cách bao nhiêu mét mới vào vùng (0 nếu đã trong)
  nearest_name: string | null;
  radius_m: number | null;
  next_action: string | null;  // "in" | "out"
  message: string;
}

export interface MyShift {
  id: number;
  name: string;
  start_time: string;   // "HH:MM"
  end_time: string;
  is_overnight: boolean;
  night_shift: boolean;
}

export interface TodaySummary {
  first_in: string | null;   // "HH:MM"
  last_out: string | null;
  cong: number | null;       // công dự kiến hôm nay theo ca
  reason: string | null;     // lý do khi công chưa đủ (thiếu chấm RA / vào trễ / về sớm…)
  late: boolean;
  early: boolean;
  ot_minutes: number;
}

export interface AttendanceStatus {
  has_employee: boolean;
  employee_name: string | null;
  next_action: string | null;
  last_check: AttendanceLog | null;
  locations_configured: boolean;
  shift: MyShift | null;         // ca mặc định của NV (nếu đã gán)
  today: TodaySummary | null;    // tóm tắt "Hôm nay của tôi"
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
  leave: string | null;  // tên loại nghỉ (nếu ngày nghỉ đã duyệt) HOẶC tên ngày lễ
  leave_paid: boolean;   // nghỉ có lương (P) hay không (KL)
  holiday?: boolean;     // ngày nghỉ lễ hưởng lương (cộng 1 công tự động)
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
  total_leave: number;
  total_hours: number;
  total_cong: number | null;
}

// --- Nghỉ phép (leave) ---
export interface LeaveType {
  id: number;
  name: string;
  is_paid: boolean;
  annual_quota: number;
  is_active: boolean;
  note: string | null;
}

export interface LeaveTypeInput {
  name: string;
  is_paid?: boolean;
  annual_quota?: number;
  note?: string | null;
  is_active?: boolean;
}

export interface LeaveRequest {
  id: number;
  employee_id: number;
  employee_name: string | null;
  leave_type_id: number | null;
  leave_type_name: string | null;
  is_paid: boolean | null;
  start_date: string;
  end_date: string;
  days: number;
  reason: string | null;
  status: string;
  decided_by: number | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string | null;
}

export interface LeaveRequestInput {
  leave_type_id: number;
  start_date: string;
  end_date: string;
  reason?: string | null;
}

export interface LeaveQuota {
  leave_type_id: number;
  name: string;
  annual_quota: number;
  used: number;       // ngày làm việc đã dùng + đang chờ (năm dương lịch)
  remaining: number;
}

export interface MyLeave {
  has_employee: boolean;
  employee_name: string | null;
  items: LeaveRequest[];
  quotas: LeaveQuota[];
}

export interface LeaveSummary {
  /** Số đơn chờ duyệt trong scope; null nếu người gọi không có quyền duyệt (ẩn badge). */
  pending_in_scope: number | null;
  /** Số đơn của tôi vừa được quyết mà tôi chưa xem → chuông Topbar. */
  my_decided_unseen: number;
}

export interface LeaveCalendarDay { status: string; leave_type_name: string; is_paid: boolean; }
export interface LeaveCalendarEmp { employee_id: number; employee_name: string; days: Record<string, LeaveCalendarDay>; }
export interface LeaveCalendar { year: number; month: number; days_in_month: number; employees: LeaveCalendarEmp[]; }

// --- Lương (module `luong`, Phase 1) ----------------------------------------
export interface PayrollParams {
  standard_cong_default: number;
  probation_ratio: number;
  bhxh_rate: number;
  bhyt_rate: number;
  bhtn_rate: number;
  deduction_self: number;
  deduction_dependent: number;
  chuyen_can_default: number;
  standard_hours_per_day: number;
  ot_multiplier: number;
  night_pct: number;
  bh_base_cap: number;
  bhtn_base_cap: number;
}
export interface SalaryRule {
  id: number;
  payroll_group: string;
  pay_grade_key: string | null;
  seniority_band: string | null;
  gender: string | null;
  monthly_amount: number;
  chuyen_can: number | null;
  effective_from: string | null;
  is_active: boolean;
  note: string | null;
}
export interface SalaryRuleInput {
  payroll_group: string;
  pay_grade_key?: string | null;
  seniority_band?: string | null;
  gender?: string | null;
  monthly_amount: number;
  chuyen_can?: number | null;
  effective_from?: string | null;
  is_active?: boolean;
  note?: string | null;
}
export interface EmployeeSalary {
  id: number;
  employee_id: number;
  effective_from: string;
  amount_mode: string;
  base_amount: number | null;
  insurance_base: number | null;
  allowance: number;
  note: string | null;
  created_at: string;
}
export interface EmployeeSalaryInput {
  effective_from: string;
  amount_mode: string;
  base_amount?: number | null;
  insurance_base?: number | null;
  allowance?: number;
  note?: string | null;
}
export interface EmployeeSalaries {
  employee_id: number;
  employee_name: string | null;
  items: EmployeeSalary[];
}
export interface SalaryPreview {
  employee_id: number;
  monthly: number;
  source: string;
  chuyen_can: number;
  allowance: number;
  insurance_base: number;
}
export interface SalaryAdvance {
  id: number;
  employee_id: number;
  employee_name: string | null;
  period_year: number;
  period_month: number;
  advance_date: string;
  amount: number;
  reason: string | null;
  status: string;
  decision_note: string | null;
  created_at: string;
}
export interface SalaryAdvanceInput {
  employee_id: number;
  period_year: number;
  period_month: number;
  advance_date: string;
  amount: number;
  reason?: string | null;
}
export interface MyAdvances {
  has_employee: boolean;
  items: SalaryAdvance[];
}
export interface PayrollPeriod {
  id: number;
  year: number;
  month: number;
  status: string;
  standard_cong: number;
  locked_at: string | null;
  paid_at: string | null;
  paid_by: number | null;
}
export interface PayrollLine {
  id: number;
  employee_id: number;
  employee_code: string | null;
  employee_name: string | null;
  department_name: string | null;
  payroll_group: string | null;
  bank_account: string | null;
  bank_name: string | null;
  is_probation: boolean;
  actual_cong: number;
  standard_cong: number;
  monthly_salary: number;
  luong_cong: number;
  chuyen_can: number;
  allowance: number;
  khoan: number;
  ot_minutes: number;
  ot_pay: number;
  night_days: number;
  night_pay: number;
  vi_pham: number;
  other_bonus: number;
  gross: number;
  insurance_base: number;
  bhxh: number;
  pit: number;
  pit_manual: boolean;
  pit_taxable: number;
  advance_total: number;
  net_pay: number;
  note: string | null;
}
export interface PayrollLineInput {
  vi_pham?: number | null;
  other_bonus?: number | null;
  pit?: number | null;
  pit_manual?: boolean | null;
  monthly_override?: number | null;
  note?: string | null;
}
export interface PitBracket {
  id: number;
  seq: number;
  up_to: number | null;
  rate: number;
}
export interface PitBracketInput {
  seq: number;
  up_to?: number | null;
  rate: number;
}
export interface PayrollTable {
  period: PayrollPeriod | null;
  lines: PayrollLine[];
}
export interface MyPayslip {
  has_employee: boolean;
  employee_name: string | null;
  period: PayrollPeriod | null;
  line: PayrollLine | null;
}

// --- Lương khoán (nhịp 2) ---------------------------------------------------
export interface PieceRate {
  id: number;
  group_name: string;
  code: string | null;
  name: string;
  unit: string;
  unit_price: number;
  note: string | null;
  is_active: boolean;
}
export interface PieceRateInput {
  group_name: string;
  code?: string | null;
  name: string;
  unit: string;
  unit_price: number;
  note?: string | null;
  is_active?: boolean;
}
export interface PieceBatch {
  id: number;
  year: number;
  month: number;
  group_name: string;
  leader_employee_id: number | null;
  leader_pct: number;
  min_guarantee: number;
  over_target: number;
  over_bonus_pct: number;
  note: string | null;
  status: string;
  locked_at: string | null;
}
export interface PieceBatchConfig {
  leader_employee_id?: number | null;
  leader_pct?: number | null;
  min_guarantee?: number | null;
  over_target?: number | null;
  over_bonus_pct?: number | null;
  note?: string | null;
}
export interface PieceEntry {
  id: number;
  batch_id: number;
  piece_rate_id: number | null;
  work_name: string;
  unit: string;
  unit_price: number;
  quantity: number;
  amount: number;
  note: string | null;
}
export interface PieceEntryInput {
  piece_rate_id?: number | null;
  work_name?: string | null;
  unit?: string | null;
  unit_price?: number | null;
  quantity: number;
  note?: string | null;
}
export interface PieceShare {
  id: number;
  batch_id: number;
  employee_id: number;
  employee_name: string | null;
  weight: number;
  amount: number;
  note: string | null;
}
export interface PieceSheetMeta {
  revenue: number;
  total: number;
  leader_cut: number;
  pool: number;
  valid: boolean;
  no_shares: boolean;
  zero_weight: boolean;
  leader_no_share: boolean;
}
export interface PieceSheet {
  batch: PieceBatch | null;
  entries: PieceEntry[];
  shares: PieceShare[];
  meta: PieceSheetMeta | null;
}

export interface CongDoanLite {
  id: number;
  ma: string;
  ten: string;
  khoan_ghi_theo: string;
}

// Phiếu sản lượng công đoạn (Pha 5b)
export interface ProductionOutput {
  id: number;
  production_order_id: number;
  cong_doan: string;
  ghi_theo: string;
  year: number;
  month: number;
  group_name: string | null;
  employee_id: number | null;
  may_id: number | null;
  piece_rate_id: number | null;
  work_name: string;
  unit: string;
  unit_price: number;
  quantity: number;
  amount: number;
  defect_qty: number;
  defect_cause: string | null;
  defect_deduction: number;
  net_amount: number;
  tinh_khoan: boolean;
  work_date: string | null;
  note: string | null;
}
export interface ProductionOutputInput {
  production_order_id: number;
  cong_doan: string;
  year: number;
  month: number;
  group_name?: string | null;
  employee_id?: number | null;
  piece_rate_id?: number | null;
  work_name?: string | null;
  unit?: string | null;
  unit_price?: number | null;
  quantity: number;
  defect_qty?: number;
  defect_cause?: string | null;
  may_id?: number | null;
  tinh_khoan?: boolean | null;
  work_date?: string | null;
  note?: string | null;
}
export interface DefectReportRow {
  scope: string;
  employee_id: number | null;
  group_name: string | null;
  quantity: number;
  defect_qty: number;
  deduction: number;
  defect_rate: number;
}

export interface Timesheet {
  year: number;
  month: number;
  days_in_month: number;
  standard_cong?: number | null;   // công chuẩn động của tháng (số ngày làm việc theo lịch)
  holidays?: HolidayMark[];        // ngày nghỉ lễ hưởng lương trong tháng
  rows: TimesheetRow[];
}

// --- Chốt công tháng (kỳ công) ---
export interface AttendancePeriod {
  year: number;
  month: number;
  status: "draft" | "locked";
  locked_at: string | null;
  locked_by: number | null;
  line_count: number;
  employee_count: number;
  hanging_days: number;      // ngày treo (thiếu chấm RA) — xử trước khi Chốt
  pending_leaves: number;    // đơn nghỉ phép chưa duyệt của tháng
  pending_adjusts: number;   // yêu cầu chỉnh công chưa duyệt
  payroll_locked: boolean;   // kỳ lương tháng này đã chốt → không mở lại kỳ công
}

// --- Lịch làm việc & Ngày lễ (calendar) ---
export interface HolidayMark {
  day: number;
  date: string;   // ISO "YYYY-MM-DD"
  name: string;
}

export interface WorkCalendarConfig {
  works_mon: boolean;
  works_tue: boolean;
  works_wed: boolean;
  works_thu: boolean;
  works_fri: boolean;
  works_sat: boolean;
  works_sun: boolean;
  updated_at: string;
}
export type WorkCalendarConfigInput = Partial<Omit<WorkCalendarConfig, "updated_at">>;

export interface SpecialDay {
  id: number;
  day: string;      // ISO date
  kind: "off" | "work";
  name: string;
  is_paid: boolean;
  note: string | null;
}
export interface SpecialDayInput {
  day: string;
  kind: "off" | "work";
  name: string;
  is_paid?: boolean;
  note?: string | null;
}
export interface SpecialDaysOut {
  year: number;
  items: SpecialDay[];
  paid_off_count: number;   // số ngày nghỉ lễ hưởng lương đã khai trong năm
  statutory_paid: number;   // mức luật (11) — cảnh báo nếu paid_off_count < mức này
}
export interface CalendarDayCell {
  day: number;
  date: string;
  weekday: number;   // Mon=0..Sun=6
  kind: "work" | "weekend" | "holiday" | "makeup";
  name: string | null;
  is_working: boolean;
}
export interface CalendarMonth {
  year: number;
  month: number;
  working_days: number;
  paid_holiday_count: number;
  days: CalendarDayCell[];
  holidays: { date: string; name: string | null; is_paid: boolean }[];
}

export interface DayPunch {
  id: number;
  time: string;              // "HH:MM"
  check_type: string;        // in | out
  is_manual: boolean;
  adjust_reason: string | null;
  fault_party: string | null;
  distance_m: number | null;
}

export interface DayDetail {
  employee_id: number;
  employee_name: string;
  date: string;              // "YYYY-MM-DD"
  shift_name: string | null;
  cong: number | null;
  reason: string | null;
  punches: DayPunch[];
}

export interface AdjustInput {
  employee_id: number;
  date: string;              // "YYYY-MM-DD"
  check_type: string;        // in | out
  time: string;              // "HH:MM"
  reason: string;
  fault_party: string | null;
}

export interface TodayKpi {
  present_now: number;
  missing_out: number;
  late_today: number;
  pending_requests: number;
}

export interface AdjustRequest {
  id: number;
  employee_id: number;
  employee_name: string | null;
  work_date: string;
  check_type: string;
  suggested_time: string | null;
  reason: string;
  fault_party: string | null;
  status: string;            // pending | approved | rejected | cancelled
  decided_at: string | null;
  decision_note: string | null;
  decided_by_name: string | null;
}

export interface RequestAdjustInput {
  date: string;
  check_type: string;
  suggested_time: string | null;
  reason: string;
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

// --- Kho P0: tồn dựa trên Material (StockLot + StockMove) --------------------
export interface StockBalanceRow {
  material_id: number;
  warehouse_id: number;
  lot_id: number | null;
  on_hand: number;
  available: number;
  value: number;
  unit: string;
}

// --- Cỗ máy chứng từ kho (spec-13) ------------------------------------------
export interface KhoVoucherType {
  id: number;
  code: string;
  name: string;
  voucher_group: string;
  stock_effect: string;
  require_src_wh: boolean;
  require_dst_wh: boolean;
  require_approval: boolean;
  sync_misa: boolean;
  is_active: boolean;
}
export interface KhoItemStatus {
  id: number;
  code: string;
  name: string;
  count_on_hand: boolean;
  count_available: boolean;
  allow_issue: boolean;
  is_system: boolean;
  is_active: boolean;
}
export interface VoucherLineInput {
  material_id: number;
  quantity: number;
  uom?: string | null;
  lot_id?: number | null;
  location?: string | null;
  dest_location?: string | null;
  status_id?: number | null;
  unit_cost?: number | null;
  note?: string | null;
}
export interface VoucherLineRow extends VoucherLineInput {
  id: number;
}
export interface VoucherInput {
  voucher_type_id: number;
  doc_date?: string | null;
  partner_kind?: string | null;
  partner_ref?: string | null;
  src_warehouse_id?: number | null;
  dst_warehouse_id?: number | null;
  ref_type?: string | null;
  ref_id?: number | null;
  reason?: string | null;
  note?: string | null;
  lines: VoucherLineInput[];
}
export interface VoucherRow {
  id: number;
  code: string;
  voucher_type_id: number;
  doc_date: string | null;
  partner_kind: string | null;
  partner_ref: string | null;
  src_warehouse_id: number | null;
  dst_warehouse_id: number | null;
  reason: string | null;
  note: string | null;
  status: string;
  created_by_user_id: number | null;
  created_by_name: string | null;
  approved_at: string | null;
  created_at: string;
  lines: VoucherLineRow[];
}
export interface VoucherAttachment {
  id: number;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_by: number | null;
  uploaded_at: string | null;
}
export interface ProductionOrderRow {
  id: number;
  code: string;
  order_id: number | null;
  contract_no: string | null;
  customer_id: number | null;
  customer_name: string | null;
  product_id: number | null;
  product_name: string | null;
  quantity: number | null;
  order_date: string | null;
  delivery_request_date: string | null;
  doc_date: string | null;
  due_date: string | null;
  status: string;
  order_kind: string;
  parent_order_id: number | null;
  parent_code: string | null;
  bu_reason: string | null;
  tech_note_print: string | null;
  tech_note_finishing: string | null;
  note: string | null;
  created_by_user_id: number | null;
  created_by_name: string | null;
  updated_by_user_id: number | null;
  updated_by_name: string | null;
  created_at: string;
  updated_at: string | null;
}
export interface ProductionAttachment {
  id: number;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_by: number | null;
  uploaded_at: string | null;
}
export interface ProductionOrderListOut {
  items: ProductionOrderRow[];
  total: number;
  page: number;
  size: number;
}
export interface ProductionOrderOption {
  id: number;
  code: string;
  label: string;
}
export interface ProductionOrderInput {
  order_id?: number | null;
  contract_no?: string | null;
  customer_id?: number | null;
  customer_name?: string | null;
  product_id?: number | null;
  product_name?: string | null;
  quantity?: number | null;
  order_date?: string | null;
  delivery_request_date?: string | null;
  doc_date?: string | null;
  due_date?: string | null;
  order_kind?: string;
  parent_order_id?: number | null;
  bu_reason?: string | null;
  tech_note_print?: string | null;
  tech_note_finishing?: string | null;
  note?: string | null;
}
export interface StockLotRow {
  id: number;
  code: string;
  material_id: number;
  warehouse_id: number;
  location: string | null;
  ownership: string;
  owner_customer_id: number | null;
  order_id: number | null;
  unit_cost: number | null;
  supplier: string | null;
  received_date: string | null;
  expiry_date: string | null;
  note: string | null;
  is_active: boolean;
  qty_on_hand: number;
}
export interface StockLotInput {
  material_id: number;
  warehouse_id: number;
  location?: string | null;
  ownership?: string;
  owner_customer_id?: number | null;
  supplier?: string | null;
  received_date?: string | null;
  expiry_date?: string | null;
  note?: string | null;
  is_active?: boolean;
}
export interface StockMoveRow {
  id: number;
  material_id: number;
  warehouse_id: number;
  lot_id: number | null;
  qty_delta: number;
  unit: string;
  move_type: string;
  reason: string | null;
  note: string | null;
  created_at: string;
}
export interface StockMoveInput {
  material_id: number;
  warehouse_id: number;
  lot_id?: number | null;
  quantity: number;
  input_uom?: string | null;
  move_type: string;
  reason?: string | null;
  note?: string | null;
}
export interface StockListOut<T> {
  items: T[];
  total: number;
}
export interface KhoMaterialOption {
  id: number;
  code: string;
  name: string;
  unit: string;
}
export interface NxtRow {
  material_id: number;
  warehouse_id: number;
  unit: string;
  opening: number;
  in_qty: number;
  out_qty: number;
  closing: number;
  opening_value: number;
  in_value: number;
  out_value: number;
  closing_value: number;
}
export interface NxtReportOut {
  items: NxtRow[];
  total: number;
  date_from: string;
  date_to: string;
}

// --- Thẻ kho / Sổ chi tiết vật tư -------------------------------------------
export interface LedgerRow {
  move_id: number;
  created_at: string;
  move_type: string;
  reason: string | null;
  note: string | null;
  lot_id: number | null;
  warehouse_id: number;
  qty_in: number;
  qty_out: number;
  balance: number;
  unit_cost: number;
  value: number;
}
export interface LedgerOut {
  material_id: number;
  unit: string;
  opening: number;
  closing: number;
  total_in: number;
  total_out: number;
  opening_value: number;
  closing_value: number;
  items: LedgerRow[];
  total: number;
  date_from: string | null;
  date_to: string | null;
}

// --- Ngưỡng tồn tối thiểu + cảnh báo tồn thấp -------------------------------
export interface MinLevelRow {
  id: number;
  material_id: number;
  warehouse_id: number;
  min_qty: number;
  note: string | null;
}
export interface LowStockRow {
  material_id: number;
  warehouse_id: number;
  min_qty: number;
  on_hand: number;
  shortfall: number;
  below: boolean;
  note: string | null;
}
export interface LocationStockRow {
  warehouse_id: number;
  location: string;
  material_id: number;
  on_hand: number;
}

// --- Kiểm kê (spec-13 C) ----------------------------------------------------
export interface CountLineRow {
  id: number;
  material_id: number;
  lot_id: number | null;
  system_qty: number;
  counted_qty: number | null;
  defective_qty: number | null;
  damaged_qty: number | null;
  unit: string | null;
  note: string | null;
  diff: number | null;
}
export interface CountLineInput {
  line_id?: number | null;
  material_id?: number | null;
  lot_id?: number | null;
  counted_qty: number | null;
  defective_qty?: number | null;
  damaged_qty?: number | null;
  note?: string | null;
}
export interface CountRow {
  id: number;
  code: string;
  warehouse_id: number;
  status: string;
  participants: string | null;
  note: string | null;
  created_by_name: string | null;
  posted_by_name: string | null;
  posted_at: string | null;
  created_at: string;
  lines: CountLineRow[];
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

// --- Thu mua ----------------------------------------------------------------
export type SupplierStatus = "active" | "inactive";

export interface SupplierRow {
  id: number;
  name: string;
  tax_code: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  contact_name: string | null;
  supplier_group: string | null;
  payment_terms: string | null;
  status: SupplierStatus;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplierInput {
  name: string;
  tax_code: string;
  phone: string;
  email: string;
  address: string;
  contact_name: string;
  supplier_group: string;
  payment_terms?: string | null;
  status?: SupplierStatus;
  note?: string | null;
}

export interface SupplierListOut {
  items: SupplierRow[];
  total: number;
  page: number;
  size: number;
}

export type PurchaseRequestStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "purchased"
  | "received"
  | "cancelled";

export type DepartmentPurchaseRequestStatus =
  | "open"
  | "pending_approval"
  | "in_purchase"
  | "done"
  | "cancelled";

export type DepartmentPurchaseSourceType =
  | "kinh_doanh"
  | "kho"
  | "san_xuat"
  | "cong_nghe"
  | "gia_cong_ngoai"
  | "khac";

export interface PurchaseRequestLineInput {
  item_name: string;
  unit: string;
  quantity: number;
  expected_unit_price: number;
  discount_percent: number;
  vat_percent: number;
  note?: string | null;
}

export interface DepartmentPurchaseRequestLineInput {
  item_name: string;
  unit: string;
  quantity: number;
  note?: string | null;
}

export interface DepartmentPurchaseRequestInput {
  source_type: DepartmentPurchaseSourceType;
  related_document_type?: string | null;
  related_document_code?: string | null;
  purpose: string;
  needed_date: string;
  note?: string | null;
  lines: DepartmentPurchaseRequestLineInput[];
}

export interface PurchaseRequestInput {
  supplier_id: number | null;
  source_request_ids: number[];
  purpose: string;
  needed_date: string;
  expected_receipt_date?: string | null;
  note?: string | null;
  lines: PurchaseRequestLineInput[];
}

export interface PurchaseRequestLineOut {
  id: number;
  item_name: string;
  unit: string;
  quantity: number;
  expected_unit_price: number;
  discount_percent: number;
  discount_amount: number;
  vat_percent: number;
  vat_amount: number;
  line_total: number;
  note: string | null;
}

export interface DepartmentPurchaseRequestLineOut {
  id: number;
  item_name: string;
  unit: string;
  quantity: number;
  expected_unit_price: number;
  line_total: number;
  note: string | null;
}

export interface DepartmentPurchaseRequestRow {
  id: number;
  code: string;
  status: DepartmentPurchaseRequestStatus;
  source_type: DepartmentPurchaseSourceType;
  requesting_department_id: number | null;
  requesting_department_name: string | null;
  requested_by_user_id: number | null;
  requested_by_name: string | null;
  related_document_type: string | null;
  related_document_code: string | null;
  purpose: string;
  needed_date: string;
  note: string | null;
  created_at: string;
  updated_at: string;
  total_estimate: number;
  lines: DepartmentPurchaseRequestLineOut[];
}

export interface DepartmentPurchaseRequestListOut {
  items: DepartmentPurchaseRequestRow[];
  total: number;
  page: number;
  size: number;
}

export interface PurchaseRequestSourceOut {
  id: number;
  department_request_id: number;
  code: string;
  status: DepartmentPurchaseRequestStatus | null;
  source_type: DepartmentPurchaseSourceType | null;
  purpose: string | null;
  needed_date: string | null;
  requesting_department_name: string | null;
  requested_by_name: string | null;
}

export interface PurchaseRequestRow {
  id: number;
  code: string;
  status: PurchaseRequestStatus;
  supplier_id: number | null;
  supplier_name: string | null;
  purpose: string | null;
  needed_date: string | null;
  expected_receipt_date: string | null;
  created_by_user_id: number | null;
  created_by_name: string | null;
  submitted_at: string | null;
  approved_by_user_id: number | null;
  approved_by_name: string | null;
  approved_at: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
  total_estimate: number;
  pending_amount: number;
  paid_amount: number;
  receipt_received_amount: number;
  outstanding_amount: number;
  available_amount: number;
  payment_status: "unpaid" | "partial" | "paid";
  payment_voucher_count: number;
  sources: PurchaseRequestSourceOut[];
  lines: PurchaseRequestLineOut[];
}

export interface PurchaseRequestListOut {
  items: PurchaseRequestRow[];
  total: number;
  page: number;
  size: number;
}

export type PaymentVoucherType = "cash" | "bank_transfer";
export type PaymentStage = "advance" | "partial" | "final" | "other";
export type PaymentVoucherStatus = "waiting_payment" | "paid" | "cancelled";

export interface BankAccountInput {
  account_holder: string;
  account_number: string;
  bank_name: string;
  bank_branch: string;
  currency: string;
  is_default: boolean;
  is_active: boolean;
  note?: string | null;
}

export interface CompanyBankAccountRow extends BankAccountInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierBankAccountInput extends BankAccountInput {
  supplier_id: number;
}

export interface SupplierBankAccountRow extends SupplierBankAccountInput {
  id: number;
  supplier_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentVoucherBaseInput {
  voucher_type: PaymentVoucherType;
  payment_stage: PaymentStage;
  voucher_date: string;
  planned_payment_date?: string | null;
  amount: number;
  currency: string;
  exchange_rate: number;
  content: string;
  invoice_number?: string | null;
  invoice_date?: string | null;
  contract_number?: string | null;
  company_bank_account_id?: number | null;
  supplier_bank_account_id?: number | null;
  cash_recipient_name?: string | null;
  cash_recipient_address?: string | null;
  cash_recipient_identity?: string | null;
  bank_fee_bearer?: "payer" | "beneficiary" | "shared" | null;
  note?: string | null;
}

export interface PaymentVoucherInput extends PaymentVoucherBaseInput {
  purchase_request_id: number;
}

export interface PaymentVoucherRow {
  id: number;
  code: string;
  purchase_request_id: number;
  purchase_request_code: string;
  purchase_request_total: number | null;
  purchase_paid_amount: number | null;
  purchase_created_by_name: string | null;
  receipt_received_amount: number;
  receipt_pending_amount: number;
  attachment_count: number;
  source_request_codes: string[];
  supplier_id: number | null;
  supplier_name: string;
  supplier_tax_code: string | null;
  supplier_address: string | null;
  voucher_type: PaymentVoucherType;
  payment_stage: PaymentStage;
  status: PaymentVoucherStatus;
  voucher_date: string;
  planned_payment_date: string | null;
  amount: number;
  amount_vnd: number;
  currency: string;
  exchange_rate: number;
  content: string;
  invoice_number: string | null;
  invoice_date: string | null;
  contract_number: string | null;
  company_bank_account_id: number | null;
  supplier_bank_account_id: number | null;
  cash_recipient_name: string | null;
  cash_recipient_address: string | null;
  cash_recipient_identity: string | null;
  bank_fee_bearer: "payer" | "beneficiary" | "shared" | null;
  bank_reference: string | null;
  company_account_holder: string | null;
  company_account_number: string | null;
  company_bank_name: string | null;
  company_bank_branch: string | null;
  beneficiary_account_holder: string | null;
  beneficiary_account_number: string | null;
  beneficiary_bank_name: string | null;
  beneficiary_bank_branch: string | null;
  created_by_user_id: number | null;
  created_by_name: string | null;
  paid_by_user_id: number | null;
  paid_by_name: string | null;
  paid_at: string | null;
  cancelled_by_user_id: number | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentVoucherListOut {
  items: PaymentVoucherRow[];
  total: number;
  page: number;
  size: number;
  /** Tổng tiền (VND) trên TOÀN BỘ kết quả khớp bộ lọc — mọi trang. */
  total_paid_amount: number;
  total_waiting_amount: number;
  total_receipt_received_amount: number;
}

export interface PaymentVoucherAttachment {
  id: number;
  payment_voucher_id: number;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_by: number | null;
  uploaded_at: string | null;
}

export type PaymentReceiptStatus = "waiting_receipt" | "received" | "cancelled";

export interface PaymentReceiptInput {
  payer_name: string;
  receipt_method: PaymentVoucherType;
  receipt_date: string;
  amount: number;
  exchange_rate?: number | null;
  content: string;
  company_bank_account_id?: number | null;
  note?: string | null;
}

export interface PaymentReceiptRow {
  id: number;
  code: string;
  payment_voucher_id: number;
  payment_voucher_code: string;
  purchase_request_id: number;
  purchase_request_code: string;
  supplier_name: string;
  payer_name: string;
  receipt_method: PaymentVoucherType;
  status: PaymentReceiptStatus;
  receipt_date: string;
  amount: number;
  amount_vnd: number;
  currency: string;
  exchange_rate: number;
  content: string;
  company_bank_account_id: number | null;
  company_account_holder: string | null;
  company_account_number: string | null;
  company_bank_name: string | null;
  company_bank_branch: string | null;
  bank_reference: string | null;
  created_by_user_id: number | null;
  created_by_name: string | null;
  received_by_user_id: number | null;
  received_by_name: string | null;
  received_at: string | null;
  cancelled_by_user_id: number | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  note: string | null;
  attachment_count: number;
  created_at: string;
  updated_at: string;
}

export interface PaymentReceiptAttachment {
  id: number;
  payment_receipt_id: number;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_by: number | null;
  uploaded_at: string | null;
}

export interface PaymentReceiptListOut {
  items: PaymentReceiptRow[];
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
    createUser(
      token: string, name: string, username: string, departmentId: number, password?: string | null,
    ): Promise<UserRow & { initial_password: string }> {
      return authed<UserRow & { initial_password: string }>("/api/users", token, {
        method: "POST",
        body: JSON.stringify({
          name, username, department_id: departmentId,
          password: password && password.trim() ? password.trim() : undefined,
        }),
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
      if (params.tag) qs.set("tag", params.tag);
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
    /** Check trùng tức thời trên form (#8) — soft warn, không chặn. */
    checkDuplicate(
      token: string,
      params: { tax_code?: string; name?: string; email?: string; exclude_id?: number },
    ): Promise<DuplicateWarn[]> {
      const qs = new URLSearchParams();
      if (params.tax_code) qs.set("tax_code", params.tax_code);
      if (params.name) qs.set("name", params.name);
      if (params.email) qs.set("email", params.email);
      if (params.exclude_id != null) qs.set("exclude_id", String(params.exclude_id));
      return authed<DuplicateWarn[]>(`/api/customers/check-duplicate?${qs}`, token);
    },
    // --- người liên hệ (#10–#11) ---
    contacts(token: string, id: number): Promise<{ items: CustomerContact[] }> {
      return authed<{ items: CustomerContact[] }>(`/api/customers/${id}/contacts`, token);
    },
    addContact(token: string, id: number, input: CustomerContactInput): Promise<CustomerContact> {
      return authed<CustomerContact>(`/api/customers/${id}/contacts`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateContact(
      token: string,
      id: number,
      contactId: number,
      input: CustomerContactInput,
    ): Promise<CustomerContact> {
      return authed<CustomerContact>(`/api/customers/${id}/contacts/${contactId}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    deleteContact(token: string, id: number, contactId: number): Promise<void> {
      return authed<void>(`/api/customers/${id}/contacts/${contactId}`, token, {
        method: "DELETE",
      });
    },
    // --- địa chỉ giao hàng (#9) ---
    addresses(token: string, id: number): Promise<{ items: CustomerAddress[] }> {
      return authed<{ items: CustomerAddress[] }>(`/api/customers/${id}/addresses`, token);
    },
    addAddress(token: string, id: number, input: CustomerAddressInput): Promise<CustomerAddress> {
      return authed<CustomerAddress>(`/api/customers/${id}/addresses`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateAddress(
      token: string,
      id: number,
      addressId: number,
      input: CustomerAddressInput,
    ): Promise<CustomerAddress> {
      return authed<CustomerAddress>(`/api/customers/${id}/addresses/${addressId}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    deleteAddress(token: string, id: number, addressId: number): Promise<void> {
      return authed<void>(`/api/customers/${id}/addresses/${addressId}`, token, {
        method: "DELETE",
      });
    },
    // --- nhãn thủ công (#7) ---
    tagLabels(token: string): Promise<string[]> {
      return authed<string[]>("/api/customers/tags", token);
    },
    tags(token: string, id: number): Promise<{ items: { id: number; label: string }[] }> {
      return authed<{ items: { id: number; label: string }[] }>(
        `/api/customers/${id}/tags`,
        token,
      );
    },
    addTag(token: string, id: number, label: string): Promise<{ id: number; label: string }> {
      return authed<{ id: number; label: string }>(`/api/customers/${id}/tags`, token, {
        method: "POST",
        body: JSON.stringify({ label }),
      });
    },
    deleteTag(token: string, id: number, tagId: number): Promise<void> {
      return authed<void>(`/api/customers/${id}/tags/${tagId}`, token, { method: "DELETE" });
    },
    // --- chăm sóc (#20/#27/#28) ---
    careEvents(token: string, id: number): Promise<{ items: CareEvent[] }> {
      return authed<{ items: CareEvent[] }>(`/api/customers/${id}/care`, token);
    },
    addCareEvent(
      token: string,
      id: number,
      input: { kind: string; note: string; happened_at?: string | null },
    ): Promise<CareEvent> {
      return authed<CareEvent>(`/api/customers/${id}/care`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    careTasks(token: string, id: number): Promise<CareTasksOut> {
      return authed<CareTasksOut>(`/api/customers/${id}/care-tasks`, token);
    },
    addCareTask(
      token: string,
      id: number,
      input: { note: string; due_date: string; assignee_user_id?: number | null },
    ): Promise<CareTask> {
      return authed<CareTask>(`/api/customers/${id}/care-tasks`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    setCareTaskStatus(
      token: string,
      id: number,
      taskId: number,
      input: { status: string; log_kind?: string | null; log_note?: string | null },
    ): Promise<CareTask> {
      return authed<CareTask>(`/api/customers/${id}/care-tasks/${taskId}/status`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    /** Panel "Cần chăm sóc": việc đến hạn/quá hạn trong scope của tôi. */
    careFollowups(token: string): Promise<{ items: FollowupRow[] }> {
      return authed<{ items: FollowupRow[] }>("/api/customers/care-followups", token);
    },
    // --- tài liệu đính kèm (#21) ---
    attachments(token: string, id: number): Promise<{ items: CustomerAttachment[] }> {
      return authed<{ items: CustomerAttachment[] }>(`/api/customers/${id}/attachments`, token);
    },
    uploadAttachment(
      token: string,
      id: number,
      file: File,
      docKind: string,
    ): Promise<CustomerAttachment> {
      const form = new FormData();
      form.append("file", file);
      form.append("doc_kind", docKind);
      return authed<CustomerAttachment>(`/api/customers/${id}/attachments`, token, {
        method: "POST",
        body: form,
      });
    },
    deleteAttachment(token: string, id: number, attachmentId: number): Promise<void> {
      return authed<void>(`/api/customers/${id}/attachments/${attachmentId}`, token, {
        method: "DELETE",
      });
    },
    // --- import / export danh bạ (#23) ---
    /** Xuất danh bạ CSV (blob URL, bearer-aware — mirror orderCsvBlobUrl). */
    async exportCsvBlobUrl(token: string): Promise<string> {
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/customers/export.csv`, {
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
      return URL.createObjectURL(await resp.blob());
    },
    /** File mẫu import (blob URL). */
    async importTemplateBlobUrl(token: string): Promise<string> {
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/customers/import-template.csv`, {
          credentials: "include",
          cache: "no-store",
          headers: authHeader(bearer),
        });
      let resp = await doFetch(token);
      if (resp.status === 401) {
        const fresh = await refreshAccessToken();
        if (fresh) resp = await doFetch(fresh);
      }
      if (!resp.ok) throw new ApiError(`Download failed (${resp.status}).`, resp.status);
      return URL.createObjectURL(await resp.blob());
    },
    /** Import CSV — dryRun=true chỉ xem trước; false mới ghi. */
    importCsv(token: string, file: File, dryRun: boolean): Promise<ImportResultOut> {
      const form = new FormData();
      form.append("file", file);
      form.append("dry_run", dryRun ? "true" : "false");
      return authed<ImportResultOut>("/api/customers/import", token, {
        method: "POST",
        body: form,
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
    /** Gán ca mặc định (an toàn — chỉ đụng default_shift_id). Dùng cho panel Gán ca ở Chấm công. */
    setShift(token: string, id: number, shiftId: number | null): Promise<{ ok: boolean; employee_id: number; default_shift_id: number | null }> {
      return authed(`/api/employees/${id}/shift`, token, {
        method: "PUT",
        body: JSON.stringify({ default_shift_id: shiftId }),
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
    // --- "Hồ sơ của tôi" (self-service) ---
    me(token: string): Promise<MyProfile> {
      return authed<MyProfile>("/api/employees/me", token);
    },
    updateMe(token: string, input: MyContactInput): Promise<MyProfile> {
      return authed<MyProfile>("/api/employees/me", token, { method: "PUT", body: JSON.stringify(input) });
    },
    myEvents(token: string): Promise<{ items: EmployeeEvent[] }> {
      return authed<{ items: EmployeeEvent[] }>("/api/employees/me/events", token);
    },
    myAttachments(token: string): Promise<{ items: EmployeeAttachment[] }> {
      return authed<{ items: EmployeeAttachment[] }>("/api/employees/me/attachments", token);
    },
    // Yêu cầu cập nhật hồ sơ (NV đề nghị → HCNS duyệt)
    createMyRequest(token: string, input: UpdateRequestInput): Promise<UpdateRequest> {
      return authed<UpdateRequest>("/api/employees/me/update-requests", token, { method: "POST", body: JSON.stringify(input) });
    },
    myRequests(token: string): Promise<{ items: UpdateRequest[] }> {
      return authed<{ items: UpdateRequest[] }>("/api/employees/me/update-requests", token);
    },
    updateRequests(token: string, status?: string): Promise<{ items: UpdateRequest[] }> {
      const s = status ? `?status=${encodeURIComponent(status)}` : "";
      return authed<{ items: UpdateRequest[] }>(`/api/employees/update-requests${s}`, token);
    },
    approveRequest(token: string, id: number, note?: string): Promise<UpdateRequest> {
      return authed<UpdateRequest>(`/api/employees/update-requests/${id}/approve`, token, { method: "POST", body: JSON.stringify({ note: note ?? null }) });
    },
    rejectRequest(token: string, id: number, note?: string): Promise<UpdateRequest> {
      return authed<UpdateRequest>(`/api/employees/update-requests/${id}/reject`, token, { method: "POST", body: JSON.stringify({ note: note ?? null }) });
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
    /** Dry-run geofence (không ghi log) cho card chấm "sống". */
    preview(token: string, latitude: number, longitude: number): Promise<AttendancePreview> {
      return authed<AttendancePreview>("/api/attendance/me/preview", token, {
        method: "POST",
        body: JSON.stringify({ latitude, longitude }),
      });
    },
    myLogs(token: string): Promise<{ items: AttendanceLog[] }> {
      return authed<{ items: AttendanceLog[] }>("/api/attendance/me/logs", token);
    },
    /** Bảng công tháng CỦA CHÍNH NV (self-service, không cần quyền module). */
    myTimesheet(token: string, year: number, month: number): Promise<Timesheet> {
      const qs = new URLSearchParams({ year: String(year), month: String(month) });
      return authed<Timesheet>(`/api/attendance/me/timesheet?${qs.toString()}`, token);
    },
    /** "Ô biết nói": punch thật + công của 1 NV trong 1 ngày (HR, theo scope). */
    day(token: string, employeeId: number, date: string): Promise<DayDetail> {
      const qs = new URLSearchParams({ employee_id: String(employeeId), date });
      return authed<DayDetail>(`/api/attendance/day?${qs.toString()}`, token);
    },
    /** Chấm bù / sửa: thêm 1 punch điều chỉnh tay (cần quyền nhan_su.adjust). */
    adjust(token: string, input: AdjustInput): Promise<DayDetail> {
      return authed<DayDetail>("/api/attendance/adjust", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** Xóa 1 punch điều chỉnh tay (hoàn tác chấm bù). */
    deleteManualLog(token: string, logId: number, employeeId: number, date: string): Promise<DayDetail> {
      const qs = new URLSearchParams({ employee_id: String(employeeId), date });
      return authed<DayDetail>(`/api/attendance/logs/${logId}?${qs.toString()}`, token, { method: "DELETE" });
    },
    /** KPI giám sát hôm nay (HR, theo scope). */
    kpi(token: string): Promise<TodayKpi> {
      return authed<TodayKpi>("/api/attendance/kpi", token);
    },
    // --- Yêu cầu chỉnh công ---
    createAdjustRequest(token: string, input: RequestAdjustInput): Promise<AdjustRequest> {
      return authed<AdjustRequest>("/api/attendance/me/adjust-request", token, {
        method: "POST", body: JSON.stringify(input),
      });
    },
    myAdjustRequests(token: string): Promise<{ items: AdjustRequest[] }> {
      return authed<{ items: AdjustRequest[] }>("/api/attendance/me/adjust-requests", token);
    },
    cancelAdjustRequest(token: string, id: number): Promise<AdjustRequest> {
      return authed<AdjustRequest>(`/api/attendance/me/adjust-requests/${id}/cancel`, token, { method: "POST" });
    },
    listAdjustRequests(token: string, status = "pending"): Promise<{ items: AdjustRequest[] }> {
      return authed<{ items: AdjustRequest[] }>(`/api/attendance/adjust-requests?status=${status}`, token);
    },
    approveAdjustRequest(token: string, id: number, input: { time?: string | null; fault_party?: string | null; note?: string | null }): Promise<AdjustRequest> {
      return authed<AdjustRequest>(`/api/attendance/adjust-requests/${id}/approve`, token, {
        method: "POST", body: JSON.stringify(input),
      });
    },
    rejectAdjustRequest(token: string, id: number, note: string): Promise<AdjustRequest> {
      return authed<AdjustRequest>(`/api/attendance/adjust-requests/${id}/reject`, token, {
        method: "POST", body: JSON.stringify({ note }),
      });
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
    // --- Chốt công tháng (kỳ công) ---
    period(token: string, year: number, month: number): Promise<AttendancePeriod> {
      return authed<AttendancePeriod>(`/api/attendance/period?year=${year}&month=${month}`, token);
    },
    lockPeriod(token: string, year: number, month: number): Promise<AttendancePeriod> {
      return authed<AttendancePeriod>("/api/attendance/period/lock", token,
        { method: "POST", body: JSON.stringify({ year, month }) });
    },
    reopenPeriod(token: string, year: number, month: number): Promise<AttendancePeriod> {
      return authed<AttendancePeriod>("/api/attendance/period/reopen", token,
        { method: "POST", body: JSON.stringify({ year, month }) });
    },
  },

  // --- Nghỉ phép (nhan_su) --------------------------------------------------
  leaves: {
    types(token: string): Promise<{ items: LeaveType[] }> {
      return authed<{ items: LeaveType[] }>("/api/leaves/types", token);
    },
    createType(token: string, input: LeaveTypeInput): Promise<LeaveType> {
      return authed<LeaveType>("/api/leaves/types", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateType(token: string, id: number, input: LeaveTypeInput): Promise<LeaveType> {
      return authed<LeaveType>(`/api/leaves/types/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deleteType(token: string, id: number): Promise<void> {
      return authed<void>(`/api/leaves/types/${id}`, token, { method: "DELETE" });
    },
    me(token: string): Promise<MyLeave> {
      return authed<MyLeave>("/api/leaves/me", token);
    },
    create(token: string, input: LeaveRequestInput): Promise<LeaveRequest> {
      return authed<LeaveRequest>("/api/leaves", token, { method: "POST", body: JSON.stringify(input) });
    },
    cancel(token: string, id: number): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/${id}/cancel`, token, { method: "POST" });
    },
    list(token: string, status?: string): Promise<{ items: LeaveRequest[] }> {
      const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
      return authed<{ items: LeaveRequest[] }>(`/api/leaves${suffix}`, token);
    },
    approve(token: string, id: number, note?: string): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/${id}/approve`, token, { method: "POST", body: JSON.stringify({ note: note ?? null }) });
    },
    reject(token: string, id: number, note: string): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/${id}/reject`, token, { method: "POST", body: JSON.stringify({ note }) });
    },
    /** Số đơn chờ duyệt (nuôi badge sidebar). pending_in_scope=null nếu không có quyền duyệt. */
    summary(token: string): Promise<LeaveSummary> {
      return authed<LeaveSummary>("/api/leaves/summary", token);
    },
    bulkApprove(token: string, ids: number[]): Promise<{ done: number[]; skipped: number[] }> {
      return authed<{ done: number[]; skipped: number[] }>("/api/leaves/bulk-approve", token, { method: "POST", body: JSON.stringify({ ids }) });
    },
    bulkReject(token: string, ids: number[], note: string): Promise<{ done: number[]; skipped: number[] }> {
      return authed<{ done: number[]; skipped: number[] }>("/api/leaves/bulk-reject", token, { method: "POST", body: JSON.stringify({ ids, note }) });
    },
    calendar(token: string, year: number, month: number): Promise<LeaveCalendar> {
      return authed<LeaveCalendar>(`/api/leaves/calendar?year=${year}&month=${month}`, token);
    },
    /** NV xác nhận đã xem kết quả các đơn của mình (đóng chuông Topbar). */
    markSeen(token: string): Promise<void> {
      return authed<void>("/api/leaves/mark-seen", token, { method: "POST" });
    },
  },

  // --- Lịch làm việc & Ngày lễ (nhan_su) ------------------------------------
  calendar: {
    getConfig(token: string): Promise<WorkCalendarConfig> {
      return authed<WorkCalendarConfig>("/api/calendar/config", token);
    },
    updateConfig(token: string, input: WorkCalendarConfigInput): Promise<WorkCalendarConfig> {
      return authed<WorkCalendarConfig>("/api/calendar/config", token, { method: "PUT", body: JSON.stringify(input) });
    },
    specialDays(token: string, year: number): Promise<SpecialDaysOut> {
      return authed<SpecialDaysOut>(`/api/calendar/special-days?year=${year}`, token);
    },
    createSpecialDay(token: string, input: SpecialDayInput): Promise<SpecialDay> {
      return authed<SpecialDay>("/api/calendar/special-days", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateSpecialDay(token: string, id: number, input: SpecialDayInput): Promise<SpecialDay> {
      return authed<SpecialDay>(`/api/calendar/special-days/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deleteSpecialDay(token: string, id: number): Promise<void> {
      return authed<void>(`/api/calendar/special-days/${id}`, token, { method: "DELETE" });
    },
    month(token: string, year: number, month: number): Promise<CalendarMonth> {
      return authed<CalendarMonth>(`/api/calendar/month?year=${year}&month=${month}`, token);
    },
  },

  // --- Lương (module `luong`, Phase 1) --------------------------------------
  luong: {
    getParams(token: string): Promise<PayrollParams> {
      return authed<PayrollParams>("/api/luong/params", token);
    },
    updateParams(token: string, input: Partial<PayrollParams>): Promise<PayrollParams> {
      return authed<PayrollParams>("/api/luong/params", token, { method: "PUT", body: JSON.stringify(input) });
    },
    rules(token: string): Promise<{ items: SalaryRule[] }> {
      return authed<{ items: SalaryRule[] }>("/api/luong/rules", token);
    },
    createRule(token: string, input: SalaryRuleInput): Promise<SalaryRule> {
      return authed<SalaryRule>("/api/luong/rules", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateRule(token: string, id: number, input: SalaryRuleInput): Promise<SalaryRule> {
      return authed<SalaryRule>(`/api/luong/rules/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deleteRule(token: string, id: number): Promise<void> {
      return authed<void>(`/api/luong/rules/${id}`, token, { method: "DELETE" });
    },
    salaries(token: string, employeeId: number): Promise<EmployeeSalaries> {
      return authed<EmployeeSalaries>(`/api/luong/salaries/${employeeId}`, token);
    },
    salaryPreview(token: string, employeeId: number): Promise<SalaryPreview> {
      return authed<SalaryPreview>(`/api/luong/salaries/${employeeId}/preview`, token);
    },
    setSalary(token: string, employeeId: number, input: EmployeeSalaryInput): Promise<EmployeeSalary> {
      return authed<EmployeeSalary>(`/api/luong/salaries/${employeeId}`, token, { method: "POST", body: JSON.stringify(input) });
    },
    deleteSalary(token: string, salaryId: number): Promise<void> {
      return authed<void>(`/api/luong/salaries/item/${salaryId}`, token, { method: "DELETE" });
    },
    advances(token: string, year: number, month: number, status?: string): Promise<{ items: SalaryAdvance[] }> {
      const s = status ? `&status=${encodeURIComponent(status)}` : "";
      return authed<{ items: SalaryAdvance[] }>(`/api/luong/advances?year=${year}&month=${month}${s}`, token);
    },
    createAdvance(token: string, input: SalaryAdvanceInput): Promise<SalaryAdvance> {
      return authed<SalaryAdvance>("/api/luong/advances", token, { method: "POST", body: JSON.stringify(input) });
    },
    approveAdvance(token: string, id: number, note?: string): Promise<SalaryAdvance> {
      return authed<SalaryAdvance>(`/api/luong/advances/${id}/approve`, token, { method: "POST", body: JSON.stringify({ note: note ?? null }) });
    },
    rejectAdvance(token: string, id: number, note?: string): Promise<SalaryAdvance> {
      return authed<SalaryAdvance>(`/api/luong/advances/${id}/reject`, token, { method: "POST", body: JSON.stringify({ note: note ?? null }) });
    },
    cancelAdvance(token: string, id: number): Promise<SalaryAdvance> {
      return authed<SalaryAdvance>(`/api/luong/advances/${id}/cancel`, token, { method: "POST" });
    },
    myAdvances(token: string): Promise<MyAdvances> {
      return authed<MyAdvances>("/api/luong/advances/me", token);
    },
    periods(token: string): Promise<{ items: PayrollPeriod[] }> {
      return authed<{ items: PayrollPeriod[] }>("/api/luong/periods", token);
    },
    table(token: string, year: number, month: number): Promise<PayrollTable> {
      return authed<PayrollTable>(`/api/luong/table?year=${year}&month=${month}`, token);
    },
    generate(token: string, year: number, month: number): Promise<PayrollTable> {
      return authed<PayrollTable>("/api/luong/generate", token, { method: "POST", body: JSON.stringify({ year, month }) });
    },
    updateLine(token: string, id: number, input: PayrollLineInput): Promise<PayrollLine> {
      return authed<PayrollLine>(`/api/luong/lines/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    pitBrackets(token: string): Promise<{ items: PitBracket[] }> {
      return authed<{ items: PitBracket[] }>("/api/luong/pit-brackets", token);
    },
    createPitBracket(token: string, input: PitBracketInput): Promise<PitBracket> {
      return authed<PitBracket>("/api/luong/pit-brackets", token, { method: "POST", body: JSON.stringify(input) });
    },
    updatePitBracket(token: string, id: number, input: PitBracketInput): Promise<PitBracket> {
      return authed<PitBracket>(`/api/luong/pit-brackets/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deletePitBracket(token: string, id: number): Promise<void> {
      return authed<void>(`/api/luong/pit-brackets/${id}`, token, { method: "DELETE" });
    },
    lock(token: string, year: number, month: number): Promise<PayrollPeriod> {
      return authed<PayrollPeriod>("/api/luong/lock", token, { method: "POST", body: JSON.stringify({ year, month }) });
    },
    reopen(token: string, year: number, month: number): Promise<PayrollPeriod> {
      return authed<PayrollPeriod>("/api/luong/reopen", token, { method: "POST", body: JSON.stringify({ year, month }) });
    },
    pay(token: string, year: number, month: number, note?: string): Promise<PayrollPeriod> {
      return authed<PayrollPeriod>("/api/luong/pay", token, { method: "POST", body: JSON.stringify({ year, month, note: note ?? null }) });
    },
    unpay(token: string, year: number, month: number, note?: string): Promise<PayrollPeriod> {
      return authed<PayrollPeriod>("/api/luong/unpay", token, { method: "POST", body: JSON.stringify({ year, month, note: note ?? null }) });
    },
    /** Xuất bảng lương / file chuyển khoản .xlsx — fetch as blob (bearer + refresh-aware). */
    async xlsxBlobUrl(token: string, kind: "table" | "bank", year: number, month: number): Promise<string> {
      const path = kind === "bank" ? "bank.xlsx" : "export.xlsx";
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/luong/${path}?year=${year}&month=${month}`, {
          credentials: "include", cache: "no-store", headers: authHeader(bearer),
        });
      let resp = await doFetch(token);
      if (resp.status === 401) {
        const fresh = await refreshAccessToken();
        if (fresh) resp = await doFetch(fresh);
      }
      if (!resp.ok) throw new ApiError(`Export failed (${resp.status}).`, resp.status);
      return URL.createObjectURL(await resp.blob());
    },
    myPayslip(token: string): Promise<MyPayslip> {
      return authed<MyPayslip>("/api/luong/payslip/me", token);
    },
    // --- Lương khoán (nhịp 2) ---
    khoanRates(token: string): Promise<{ items: PieceRate[] }> {
      return authed<{ items: PieceRate[] }>("/api/luong/khoan/rates", token);
    },
    createKhoanRate(token: string, input: PieceRateInput): Promise<PieceRate> {
      return authed<PieceRate>("/api/luong/khoan/rates", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateKhoanRate(token: string, id: number, input: PieceRateInput): Promise<PieceRate> {
      return authed<PieceRate>(`/api/luong/khoan/rates/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deleteKhoanRate(token: string, id: number): Promise<void> {
      return authed<void>(`/api/luong/khoan/rates/${id}`, token, { method: "DELETE" });
    },
    khoanBatches(token: string, year: number, month: number): Promise<{ items: PieceBatch[] }> {
      return authed<{ items: PieceBatch[] }>(`/api/luong/khoan/batches?year=${year}&month=${month}`, token);
    },
    khoanSheet(token: string, year: number, month: number, group: string): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/sheet?year=${year}&month=${month}&group_name=${encodeURIComponent(group)}`, token);
    },
    openKhoanSheet(token: string, year: number, month: number, group: string): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/sheet?year=${year}&month=${month}&group_name=${encodeURIComponent(group)}`, token, { method: "POST" });
    },
    updateKhoanConfig(token: string, batchId: number, cfg: PieceBatchConfig): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/batches/${batchId}/config`, token, { method: "PUT", body: JSON.stringify(cfg) });
    },
    addKhoanEntry(token: string, batchId: number, input: PieceEntryInput): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/batches/${batchId}/entries`, token, { method: "POST", body: JSON.stringify(input) });
    },
    updateKhoanEntry(token: string, entryId: number, input: { quantity?: number; unit_price?: number; note?: string | null }): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/entries/${entryId}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deleteKhoanEntry(token: string, entryId: number): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/entries/${entryId}`, token, { method: "DELETE" });
    },
    setKhoanShare(token: string, batchId: number, input: { employee_id: number; weight: number; note?: string | null }): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/batches/${batchId}/shares`, token, { method: "POST", body: JSON.stringify(input) });
    },
    deleteKhoanShare(token: string, shareId: number): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/shares/${shareId}`, token, { method: "DELETE" });
    },
    khoanLockSheet(token: string, batchId: number): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/batches/${batchId}/lock`, token, { method: "POST" });
    },
    khoanReopenSheet(token: string, batchId: number): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/batches/${batchId}/reopen`, token, { method: "POST" });
    },
    khoanSyncOutputs(token: string, batchId: number): Promise<PieceSheet> {
      return authed<PieceSheet>(`/api/luong/khoan/batches/${batchId}/sync-outputs`, token, { method: "POST" });
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
    getPhieu(token: string, id: number, qty?: number): Promise<PhieuTinhGiaPrintOut> {
      const s = qty ? `?qty=${qty}` : "";
      return authed<PhieuTinhGiaPrintOut>(`/api/costings/${id}/phieu${s}`, token);
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

  // --- Tính giá thành (engine MỚI) — preview 4 nhóm, không lưu ---------------
  tinhGia: {
    preview(token: string, body: TinhGiaPreviewIn): Promise<TinhGiaPreviewOut> {
      return authed<TinhGiaPreviewOut>("/api/tinh-gia/preview", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    binhBai(token: string, body: BinhBaiIn): Promise<BinhBaiOut> {
      return authed<BinhBaiOut>("/api/tinh-gia/binh-bai", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
  },

  // --- Phiếu tính giá (persisted) — master/detail của "Tính giá" -------------
  phieuTinhGia: {
    list(
      token: string,
      params: { q?: string } = {},
    ): Promise<PhieuTinhGiaListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PhieuTinhGiaListOut>(`/api/phieu-tinh-gia${suffix}`, token);
    },
    get(token: string, id: number): Promise<PhieuTinhGiaOut> {
      return authed<PhieuTinhGiaOut>(`/api/phieu-tinh-gia/${id}`, token);
    },
    create(token: string, body: PhieuTinhGiaCreate): Promise<PhieuTinhGiaOut> {
      return authed<PhieuTinhGiaOut>("/api/phieu-tinh-gia", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    update(token: string, id: number, body: PhieuTinhGiaUpdate): Promise<PhieuTinhGiaOut> {
      return authed<PhieuTinhGiaOut>(`/api/phieu-tinh-gia/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/phieu-tinh-gia/${id}`, token, { method: "DELETE" });
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
    /** BG-1: báo giá ĐANG HIỆU LỰC của 1 Phiếu tính giá (màn PTG quyết Tạo mới / Mở cái có sẵn). */
    byPhieu(token: string, phieuId: number): Promise<{ quote_id: number | null; quote_number: string | null }> {
      return authed(`/api/quotations/by-phieu/${phieuId}`, token);
    },
    /** PTG đổi số → đồng bộ sang báo giá đang hiệu lực (Phương án A). Nháp = cập nhật tại chỗ;
     *  đã chốt = tạo phiên bản mới. Trả mode để màn PTG báo cho người dùng. */
    resyncFromPhieu(
      token: string,
      phieuId: number,
    ): Promise<{ quote_id: number; quote_number: string; mode: "draft_synced" | "new_version" }> {
      return authed(`/api/quotations/resync-from-ptg/${phieuId}`, token, { method: "POST" });
    },
    /** Badge nav: số báo giá 'Chờ duyệt' trong phạm vi — chỉ ai có quyền duyệt đặc thù mới >0. */
    pendingApprovalCount(token: string): Promise<{ count: number }> {
      return authed(`/api/quotations/pending-approval-count`, token);
    },
    /** BG-2: GĐ DUYỆT / TỪ CHỐI báo giá đặc thù → mở khóa "gửi khách". */
    recordApproval(
      token: string,
      id: number,
      body: { decision: "approved" | "rejected"; note?: string | null },
    ): Promise<QuotationDetail> {
      return authed<QuotationDetail>(`/api/quotations/${id}/approval`, token, {
        method: "POST",
        body: JSON.stringify(body),
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
    /** Ghi CỌC (kind=deposit) → mở khóa cổng chốt ③→④. Trả về đơn kèm gate đã cập nhật. */
    recordDeposit(
      token: string,
      id: number,
      body: { amount: number; method: string; note?: string | null },
    ): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/payments`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    payments(token: string, id: number): Promise<PaymentListOut> {
      return authed<PaymentListOut>(`/api/orders/${id}/payments`, token);
    },
    /** A2: GĐ DUYỆT / TỪ CHỐI "đơn đặc thù" → mở khóa cổng chốt. Trả về đơn kèm gate cập nhật. */
    recordApproval(
      token: string,
      id: number,
      body: { decision: "approved" | "rejected"; note?: string | null },
    ): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/approval`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    approvals(token: string, id: number): Promise<OrderApprovalListOut> {
      return authed<OrderApprovalListOut>(`/api/orders/${id}/approvals`, token);
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

  // --- Thu mua --------------------------------------------------------------
  suppliers: {
    list(
      token: string,
      params: { q?: string; status?: string | null; supplier_group?: string | null; sort?: string; page?: number; size?: number } = {},
    ): Promise<SupplierListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.supplier_group) qs.set("supplier_group", params.supplier_group);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<SupplierListOut>(`/api/suppliers${suffix}`, token);
    },
    create(token: string, input: SupplierInput): Promise<SupplierRow> {
      return authed<SupplierRow>("/api/suppliers", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: SupplierInput): Promise<SupplierRow> {
      return authed<SupplierRow>(`/api/suppliers/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    toggleActive(token: string, id: number): Promise<SupplierRow> {
      return authed<SupplierRow>(`/api/suppliers/${id}/toggle-active`, token, {
        method: "PATCH",
      });
    },
  },

  departmentPurchaseRequests: {
    list(
      token: string,
      params: { q?: string; status?: string | null; source_type?: string | null; sort?: string; page?: number; size?: number } = {},
    ): Promise<DepartmentPurchaseRequestListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.source_type) qs.set("source_type", params.source_type);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<DepartmentPurchaseRequestListOut>(`/api/department-purchase-requests${suffix}`, token);
    },
    get(token: string, id: number): Promise<DepartmentPurchaseRequestRow> {
      return authed<DepartmentPurchaseRequestRow>(`/api/department-purchase-requests/${id}`, token);
    },
    create(token: string, input: DepartmentPurchaseRequestInput): Promise<DepartmentPurchaseRequestRow> {
      return authed<DepartmentPurchaseRequestRow>("/api/department-purchase-requests", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    cancel(token: string, id: number, reason: string | null): Promise<DepartmentPurchaseRequestRow> {
      return authed<DepartmentPurchaseRequestRow>(`/api/department-purchase-requests/${id}/cancel`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },
  },

  purchaseRequests: {
    list(
      token: string,
      params: { q?: string; status?: string | null; supplier_id?: number | null; sort?: string; page?: number; size?: number } = {},
    ): Promise<PurchaseRequestListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.supplier_id !== undefined && params.supplier_id !== null)
        qs.set("supplier_id", String(params.supplier_id));
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PurchaseRequestListOut>(`/api/purchase-requests${suffix}`, token);
    },
    get(token: string, id: number): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}`, token);
    },
    create(token: string, input: PurchaseRequestInput): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>("/api/purchase-requests", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: PurchaseRequestInput): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/purchase-requests/${id}`, token, { method: "DELETE" });
    },
    submit(token: string, id: number): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/submit`, token, { method: "POST" });
    },
    approve(token: string, id: number): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/approve`, token, { method: "POST" });
    },
    reject(token: string, id: number, reason: string | null): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/reject`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },
    markPurchased(token: string, id: number): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/mark-purchased`, token, { method: "POST" });
    },
    markReceived(token: string, id: number): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/mark-received`, token, { method: "POST" });
    },
    cancel(token: string, id: number, reason: string | null): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/cancel`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },
  },

  // --- Kế toán: duyệt mua hàng, Phiếu chi / UNC ---------------------------
  accounting: {
    inbox(
      token: string,
      params: { q?: string; status?: string | null; supplier_id?: number | null; sort?: string; page?: number; size?: number } = {},
    ): Promise<PurchaseRequestListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.supplier_id != null) qs.set("supplier_id", String(params.supplier_id));
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PurchaseRequestListOut>(`/api/accounting/inbox${suffix}`, token);
    },
    companyAccounts(token: string, activeOnly = false): Promise<CompanyBankAccountRow[]> {
      return authed<CompanyBankAccountRow[]>(
        `/api/accounting/company-bank-accounts?active_only=${activeOnly}`,
        token,
      );
    },
    createCompanyAccount(token: string, input: BankAccountInput): Promise<CompanyBankAccountRow> {
      return authed<CompanyBankAccountRow>("/api/accounting/company-bank-accounts", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateCompanyAccount(token: string, id: number, input: BankAccountInput): Promise<CompanyBankAccountRow> {
      return authed<CompanyBankAccountRow>(`/api/accounting/company-bank-accounts/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    toggleCompanyAccount(token: string, id: number): Promise<CompanyBankAccountRow> {
      return authed<CompanyBankAccountRow>(`/api/accounting/company-bank-accounts/${id}/toggle-active`, token, {
        method: "PATCH",
      });
    },
    supplierAccounts(
      token: string,
      supplierId?: number | null,
      activeOnly = false,
    ): Promise<SupplierBankAccountRow[]> {
      const qs = new URLSearchParams();
      if (supplierId != null) qs.set("supplier_id", String(supplierId));
      qs.set("active_only", String(activeOnly));
      return authed<SupplierBankAccountRow[]>(
        `/api/accounting/supplier-bank-accounts?${qs.toString()}`,
        token,
      );
    },
    createSupplierAccount(token: string, input: SupplierBankAccountInput): Promise<SupplierBankAccountRow> {
      return authed<SupplierBankAccountRow>("/api/accounting/supplier-bank-accounts", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateSupplierAccount(
      token: string,
      id: number,
      input: SupplierBankAccountInput,
    ): Promise<SupplierBankAccountRow> {
      return authed<SupplierBankAccountRow>(`/api/accounting/supplier-bank-accounts/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    toggleSupplierAccount(token: string, id: number): Promise<SupplierBankAccountRow> {
      return authed<SupplierBankAccountRow>(`/api/accounting/supplier-bank-accounts/${id}/toggle-active`, token, {
        method: "PATCH",
      });
    },
    vouchers(
      token: string,
      params: {
        q?: string;
        status?: string | null;
        voucher_type?: string | null;
        supplier_id?: number | null;
        purchase_request_id?: number | null;
        sort?: string;
        page?: number;
        size?: number;
      } = {},
    ): Promise<PaymentVoucherListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.voucher_type) qs.set("voucher_type", params.voucher_type);
      if (params.supplier_id != null) qs.set("supplier_id", String(params.supplier_id));
      if (params.purchase_request_id != null)
        qs.set("purchase_request_id", String(params.purchase_request_id));
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PaymentVoucherListOut>(`/api/accounting/payment-vouchers${suffix}`, token);
    },
    voucher(token: string, id: number): Promise<PaymentVoucherRow> {
      return authed<PaymentVoucherRow>(`/api/accounting/payment-vouchers/${id}`, token);
    },
    createVoucher(token: string, input: PaymentVoucherInput): Promise<PaymentVoucherRow> {
      return authed<PaymentVoucherRow>("/api/accounting/payment-vouchers", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateVoucher(token: string, id: number, input: PaymentVoucherInput): Promise<PaymentVoucherRow> {
      return authed<PaymentVoucherRow>(`/api/accounting/payment-vouchers/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    approveAndCreateVoucher(
      token: string,
      purchaseRequestId: number,
      input: PaymentVoucherBaseInput,
    ): Promise<PaymentVoucherRow> {
      return authed<PaymentVoucherRow>(
        `/api/accounting/purchase-requests/${purchaseRequestId}/approve-and-create-voucher`,
        token,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    markVoucherPaid(token: string, id: number, bankReference: string | null): Promise<PaymentVoucherRow> {
      return authed<PaymentVoucherRow>(`/api/accounting/payment-vouchers/${id}/mark-paid`, token, {
        method: "POST",
        body: JSON.stringify({ bank_reference: bankReference }),
      });
    },
    cancelVoucher(token: string, id: number, reason: string): Promise<PaymentVoucherRow> {
      return authed<PaymentVoucherRow>(`/api/accounting/payment-vouchers/${id}/cancel`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },
    receipts(
      token: string,
      params: {
        q?: string;
        status?: string | null;
        payment_voucher_id?: number | null;
        sort?: string;
        page?: number;
        size?: number;
      } = {},
    ): Promise<PaymentReceiptListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.payment_voucher_id != null)
        qs.set("payment_voucher_id", String(params.payment_voucher_id));
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PaymentReceiptListOut>(`/api/accounting/payment-receipts${suffix}`, token);
    },
    createReceipt(
      token: string,
      voucherId: number,
      input: PaymentReceiptInput,
    ): Promise<PaymentReceiptRow> {
      return authed<PaymentReceiptRow>(
        `/api/accounting/payment-vouchers/${voucherId}/receipts`,
        token,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    updateReceipt(
      token: string,
      id: number,
      input: PaymentReceiptInput,
    ): Promise<PaymentReceiptRow> {
      return authed<PaymentReceiptRow>(`/api/accounting/payment-receipts/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    markReceiptReceived(
      token: string,
      id: number,
      bankReference: string | null,
    ): Promise<PaymentReceiptRow> {
      return authed<PaymentReceiptRow>(
        `/api/accounting/payment-receipts/${id}/mark-received`,
        token,
        { method: "POST", body: JSON.stringify({ bank_reference: bankReference }) },
      );
    },
    cancelReceipt(token: string, id: number, reason: string): Promise<PaymentReceiptRow> {
      return authed<PaymentReceiptRow>(`/api/accounting/payment-receipts/${id}/cancel`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },
    receiptAttachments(
      token: string,
      receiptId: number,
    ): Promise<{ items: PaymentReceiptAttachment[] }> {
      return authed<{ items: PaymentReceiptAttachment[] }>(
        `/api/accounting/payment-receipts/${receiptId}/attachments`,
        token,
      );
    },
    uploadReceiptAttachment(
      token: string,
      receiptId: number,
      file: File,
    ): Promise<PaymentReceiptAttachment> {
      const form = new FormData();
      form.append("file", file);
      return authed<PaymentReceiptAttachment>(
        `/api/accounting/payment-receipts/${receiptId}/attachments`,
        token,
        { method: "POST", body: form },
      );
    },
    deleteReceiptAttachment(
      token: string,
      receiptId: number,
      attachmentId: number,
    ): Promise<void> {
      return authed<void>(
        `/api/accounting/payment-receipts/${receiptId}/attachments/${attachmentId}`,
        token,
        { method: "DELETE" },
      );
    },
    voucherAttachments(
      token: string,
      voucherId: number,
    ): Promise<{ items: PaymentVoucherAttachment[] }> {
      return authed<{ items: PaymentVoucherAttachment[] }>(
        `/api/accounting/payment-vouchers/${voucherId}/attachments`,
        token,
      );
    },
    uploadVoucherAttachment(
      token: string,
      voucherId: number,
      file: File,
    ): Promise<PaymentVoucherAttachment> {
      const form = new FormData();
      form.append("file", file);
      return authed<PaymentVoucherAttachment>(
        `/api/accounting/payment-vouchers/${voucherId}/attachments`,
        token,
        { method: "POST", body: form },
      );
    },
    deleteVoucherAttachment(
      token: string,
      voucherId: number,
      attachmentId: number,
    ): Promise<void> {
      return authed<void>(
        `/api/accounting/payment-vouchers/${voucherId}/attachments/${attachmentId}`,
        token,
        { method: "DELETE" },
      );
    },
  },

  // --- Kho P0: tồn dựa trên Material -----------------------------------------
  kho: {
    materialOptions(token: string, q?: string): Promise<KhoMaterialOption[]> {
      const s = q ? `?q=${encodeURIComponent(q)}` : "";
      return authed<KhoMaterialOption[]>(`/api/kho/material-options${s}`, token);
    },
    // --- kiểm kê ---
    listCounts(token: string, params: { status?: string | null } = {}): Promise<{ items: CountRow[]; total: number }> {
      const s = params.status ? `?status=${params.status}` : "";
      return authed<{ items: CountRow[]; total: number }>(`/api/kho/counts${s}`, token);
    },
    getCount(token: string, id: number): Promise<CountRow> {
      return authed<CountRow>(`/api/kho/counts/${id}`, token);
    },
    createCount(token: string, input: { warehouse_id: number; participants?: string | null; material_group?: string | null; note?: string | null }): Promise<CountRow> {
      return authed<CountRow>("/api/kho/counts", token, { method: "POST", body: JSON.stringify(input) });
    },
    setCounts(token: string, id: number, lines: CountLineInput[]): Promise<CountRow> {
      return authed<CountRow>(`/api/kho/counts/${id}/lines`, token, { method: "PUT", body: JSON.stringify({ lines }) });
    },
    postCount(token: string, id: number): Promise<CountRow> {
      return authed<CountRow>(`/api/kho/counts/${id}/post`, token, { method: "POST" });
    },
    cancelCount(token: string, id: number): Promise<CountRow> {
      return authed<CountRow>(`/api/kho/counts/${id}/cancel`, token, { method: "POST" });
    },
    nxtReport(
      token: string,
      params: { from: string; to: string; material_id?: number | null; warehouse_id?: number | null },
    ): Promise<NxtReportOut> {
      const qs = new URLSearchParams({ from: params.from, to: params.to });
      if (params.material_id != null) qs.set("material_id", String(params.material_id));
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      return authed<NxtReportOut>(`/api/kho/reports/nxt?${qs.toString()}`, token);
    },
    ledgerReport(
      token: string,
      params: {
        material_id: number;
        warehouse_id?: number | null;
        lot_id?: number | null;
        from?: string | null;
        to?: string | null;
      },
    ): Promise<LedgerOut> {
      const qs = new URLSearchParams({ material_id: String(params.material_id) });
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      if (params.lot_id != null) qs.set("lot_id", String(params.lot_id));
      if (params.from) qs.set("from", params.from);
      if (params.to) qs.set("to", params.to);
      return authed<LedgerOut>(`/api/kho/reports/ledger?${qs.toString()}`, token);
    },
    listMinLevels(token: string, warehouseId?: number | null): Promise<StockListOut<MinLevelRow>> {
      const qs = new URLSearchParams();
      if (warehouseId != null) qs.set("warehouse_id", String(warehouseId));
      return authed<StockListOut<MinLevelRow>>(`/api/kho/min-levels?${qs.toString()}`, token);
    },
    upsertMinLevel(
      token: string,
      body: { material_id: number; warehouse_id: number; min_qty: number; note?: string | null },
    ): Promise<MinLevelRow> {
      return authed<MinLevelRow>(`/api/kho/min-levels`, token, { method: "PUT", body: JSON.stringify(body) });
    },
    deleteMinLevel(token: string, levelId: number): Promise<void> {
      return authed<void>(`/api/kho/min-levels/${levelId}`, token, { method: "DELETE" });
    },
    lowStock(
      token: string,
      params: { warehouse_id?: number | null; only_below?: boolean } = {},
    ): Promise<StockListOut<LowStockRow>> {
      const qs = new URLSearchParams();
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      if (params.only_below === false) qs.set("only_below", "false");
      return authed<StockListOut<LowStockRow>>(`/api/kho/reports/low-stock?${qs.toString()}`, token);
    },
    byLocation(
      token: string,
      params: { warehouse_id?: number | null; material_id?: number | null } = {},
    ): Promise<StockListOut<LocationStockRow>> {
      const qs = new URLSearchParams();
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      if (params.material_id != null) qs.set("material_id", String(params.material_id));
      return authed<StockListOut<LocationStockRow>>(`/api/kho/reports/by-location?${qs.toString()}`, token);
    },
    stock(
      token: string,
      params: { material_id?: number | null; warehouse_id?: number | null } = {},
    ): Promise<StockListOut<StockBalanceRow>> {
      const qs = new URLSearchParams();
      if (params.material_id != null) qs.set("material_id", String(params.material_id));
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      const s = qs.toString() ? `?${qs.toString()}` : "";
      return authed<StockListOut<StockBalanceRow>>(`/api/kho/stock${s}`, token);
    },
    createMove(token: string, input: StockMoveInput): Promise<StockMoveRow> {
      return authed<StockMoveRow>("/api/kho/moves", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    listMoves(
      token: string,
      params: { material_id?: number | null; warehouse_id?: number | null; page?: number; size?: number } = {},
    ): Promise<StockListOut<StockMoveRow>> {
      const qs = new URLSearchParams();
      if (params.material_id != null) qs.set("material_id", String(params.material_id));
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      if (params.size) qs.set("size", String(params.size));
      const s = qs.toString() ? `?${qs.toString()}` : "";
      return authed<StockListOut<StockMoveRow>>(`/api/kho/moves${s}`, token);
    },
    lots(
      token: string,
      params: { material_id?: number | null; warehouse_id?: number | null; size?: number } = {},
    ): Promise<StockListOut<StockLotRow>> {
      const qs = new URLSearchParams();
      if (params.material_id != null) qs.set("material_id", String(params.material_id));
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      if (params.size) qs.set("size", String(params.size));
      const s = qs.toString() ? `?${qs.toString()}` : "";
      return authed<StockListOut<StockLotRow>>(`/api/kho/lots${s}`, token);
    },
    createLot(token: string, input: StockLotInput): Promise<StockLotRow> {
      return authed<StockLotRow>("/api/kho/lots", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    removeLot(token: string, id: number): Promise<void> {
      return authed<void>(`/api/kho/lots/${id}`, token, { method: "DELETE" });
    },
    // --- cỗ máy chứng từ ---
    voucherTypes(token: string): Promise<{ items: KhoVoucherType[] }> {
      return authed<{ items: KhoVoucherType[] }>("/api/kho/voucher-types", token);
    },
    createVoucherType(token: string, input: Omit<KhoVoucherType, "id">): Promise<KhoVoucherType> {
      return authed<KhoVoucherType>("/api/kho/voucher-types", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateVoucherType(token: string, id: number, input: Omit<KhoVoucherType, "id">): Promise<KhoVoucherType> {
      return authed<KhoVoucherType>(`/api/kho/voucher-types/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    removeVoucherType(token: string, id: number): Promise<void> {
      return authed<void>(`/api/kho/voucher-types/${id}`, token, { method: "DELETE" });
    },
    itemStatuses(token: string): Promise<{ items: KhoItemStatus[] }> {
      return authed<{ items: KhoItemStatus[] }>("/api/kho/item-statuses", token);
    },
    createItemStatus(token: string, input: Omit<KhoItemStatus, "id" | "is_system">): Promise<KhoItemStatus> {
      return authed<KhoItemStatus>("/api/kho/item-statuses", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateItemStatus(token: string, id: number, input: Omit<KhoItemStatus, "id" | "is_system">): Promise<KhoItemStatus> {
      return authed<KhoItemStatus>(`/api/kho/item-statuses/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    removeItemStatus(token: string, id: number): Promise<void> {
      return authed<void>(`/api/kho/item-statuses/${id}`, token, { method: "DELETE" });
    },
    listVouchers(
      token: string,
      params: {
        status?: string | null;
        voucher_type_id?: number | null;
        warehouse_id?: number | null;
        partner_ref?: string | null;
        created_by_user_id?: number | null;
        page?: number;
        size?: number;
      } = {},
    ): Promise<{ items: VoucherRow[]; total: number }> {
      const qs = new URLSearchParams();
      if (params.status) qs.set("status", params.status);
      if (params.voucher_type_id != null) qs.set("voucher_type_id", String(params.voucher_type_id));
      if (params.warehouse_id != null) qs.set("warehouse_id", String(params.warehouse_id));
      if (params.partner_ref) qs.set("partner_ref", params.partner_ref);
      if (params.created_by_user_id != null) qs.set("created_by_user_id", String(params.created_by_user_id));
      if (params.size) qs.set("size", String(params.size));
      const s = qs.toString() ? `?${qs.toString()}` : "";
      return authed<{ items: VoucherRow[]; total: number }>(`/api/kho/vouchers${s}`, token);
    },
    getVoucher(token: string, id: number): Promise<VoucherRow> {
      return authed<VoucherRow>(`/api/kho/vouchers/${id}`, token);
    },
    createVoucher(token: string, input: VoucherInput): Promise<VoucherRow> {
      return authed<VoucherRow>("/api/kho/vouchers", token, { method: "POST", body: JSON.stringify(input) });
    },
    submitVoucher(token: string, id: number): Promise<VoucherRow> {
      return authed<VoucherRow>(`/api/kho/vouchers/${id}/submit`, token, { method: "POST" });
    },
    approveVoucher(token: string, id: number): Promise<VoucherRow> {
      return authed<VoucherRow>(`/api/kho/vouchers/${id}/approve`, token, { method: "POST" });
    },
    cancelVoucher(token: string, id: number): Promise<VoucherRow> {
      return authed<VoucherRow>(`/api/kho/vouchers/${id}/cancel`, token, { method: "POST" });
    },
    voucherAttachments(token: string, id: number): Promise<{ items: VoucherAttachment[] }> {
      return authed<{ items: VoucherAttachment[] }>(`/api/kho/vouchers/${id}/attachments`, token);
    },
    uploadVoucherAttachment(token: string, id: number, file: File): Promise<VoucherAttachment> {
      const form = new FormData();
      form.append("file", file);
      return authed<VoucherAttachment>(`/api/kho/vouchers/${id}/attachments`, token, { method: "POST", body: form });
    },
    deleteVoucherAttachment(token: string, id: number, attachmentId: number): Promise<void> {
      return authed<void>(`/api/kho/vouchers/${id}/attachments/${attachmentId}`, token, { method: "DELETE" });
    },
  },

  // --- Sản xuất: Lệnh sản xuất (LSX) ---------------------------------------
  production: {
    listOrders(
      token: string,
      params: { q?: string; status?: string; order_kind?: string; page?: number; size?: number } = {},
    ): Promise<ProductionOrderListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.order_kind) qs.set("order_kind", params.order_kind);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const s = qs.toString() ? `?${qs.toString()}` : "";
      return authed<ProductionOrderListOut>(`/api/san-xuat/orders${s}`, token);
    },
    orderOptions(token: string, q?: string, includeAll = false): Promise<ProductionOrderOption[]> {
      const qs = new URLSearchParams();
      if (q) qs.set("q", q);
      if (includeAll) qs.set("include_all", "true");
      const s = qs.toString() ? `?${qs.toString()}` : "";
      return authed<ProductionOrderOption[]>(`/api/san-xuat/orders/options${s}`, token);
    },
    getOrder(token: string, id: number): Promise<ProductionOrderRow> {
      return authed<ProductionOrderRow>(`/api/san-xuat/orders/${id}`, token);
    },
    createOrder(token: string, input: ProductionOrderInput): Promise<ProductionOrderRow> {
      return authed<ProductionOrderRow>("/api/san-xuat/orders", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateOrder(token: string, id: number, input: ProductionOrderInput): Promise<ProductionOrderRow> {
      return authed<ProductionOrderRow>(`/api/san-xuat/orders/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    closeOrder(token: string, id: number, toStatus: "done" | "cancelled" | "open"): Promise<ProductionOrderRow> {
      return authed<ProductionOrderRow>(`/api/san-xuat/orders/${id}/close?to_status=${toStatus}`, token, { method: "POST" });
    },
    orderAttachments(token: string, id: number): Promise<{ items: ProductionAttachment[] }> {
      return authed<{ items: ProductionAttachment[] }>(`/api/san-xuat/orders/${id}/attachments`, token);
    },
    uploadOrderAttachment(token: string, id: number, file: File): Promise<ProductionAttachment> {
      const form = new FormData();
      form.append("file", file);
      return authed<ProductionAttachment>(`/api/san-xuat/orders/${id}/attachments`, token, { method: "POST", body: form });
    },
    deleteOrderAttachment(token: string, id: number, attachmentId: number): Promise<void> {
      return authed<void>(`/api/san-xuat/orders/${id}/attachments/${attachmentId}`, token, { method: "DELETE" });
    },
  },

  // --- Công đoạn (danh mục, lite cho dropdown) -----------------------------
  congDoan: {
    list(token: string): Promise<{ items: CongDoanLite[] }> {
      return authed<{ items: CongDoanLite[] }>("/api/cong-doan?size=500", token);
    },
  },

  // --- Phiếu sản lượng công đoạn (Pha 5b) ----------------------------------
  sanLuong: {
    listByOrder(token: string, orderId: number): Promise<{ items: ProductionOutput[] }> {
      return authed<{ items: ProductionOutput[] }>(`/api/san-luong/outputs?order_id=${orderId}`, token);
    },
    create(token: string, input: ProductionOutputInput): Promise<ProductionOutput> {
      return authed<ProductionOutput>("/api/san-luong/outputs", token, { method: "POST", body: JSON.stringify(input) });
    },
    update(token: string, id: number, input: Partial<ProductionOutputInput>): Promise<ProductionOutput> {
      return authed<ProductionOutput>(`/api/san-luong/outputs/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/san-luong/outputs/${id}`, token, { method: "DELETE" });
    },
    defectReport(token: string, year: number, month: number): Promise<{ items: DefectReportRow[] }> {
      return authed<{ items: DefectReportRow[] }>(`/api/san-luong/defect-report?year=${year}&month=${month}`, token);
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
