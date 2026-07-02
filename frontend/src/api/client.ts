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
}

export interface QuotationListOut {
  items: QuotationRow[];
  total: number;
  page: number;
  size: number;
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
}

export interface QuotationDetail {
  id: number;
  code: string;
  version: number;
  customer_id: number | null;
  customer: CustomerDisplay | null;
  costing_id: number | null;
  cost_von_total: number | null;
  margin: number;
  discount: number;
  total: number | null;
  valid_until: string | null;
  status: string;
  cancel_reason: string | null;
  cancelled_at_state: string | null;
  unit_price_snapshot: Record<string, unknown> | null;
  norm_snapshot: Record<string, unknown> | null;
  price_effective_from: string | null;
  price_effective_to: string | null;
  row_version: number;
  allowed_transitions: string[];
  can_approve: boolean;
  versions: VersionRow[];
}

export interface QuotationInput {
  customer_id: number | null;
  costing_id: number | null;
  cost_von_total: number | null;
  margin: number;
  discount: number;
  valid_until: string | null;
}

export interface QuotationUpdateInput extends QuotationInput {
  row_version: number;
}

export interface QuotationEnumsOut {
  statuses: EnumOption[];
}

/** Tính giá picker state (SEAM-13): available=false + message while the giá-vốn engine is TREO. */
export interface CostingPickerOut {
  available: boolean;
  message: string | null;
  cost_von_total: number | null;
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
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<CustomerListOut>(`/api/customers${suffix}`, token);
    },
    sales(token: string): Promise<SaleOption[]> {
      return authed<SaleOption[]>("/api/customers/sales", token);
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
      body: { sheet_w: number; sheet_h: number; piece_w: number; piece_h: number; grain_locked: boolean },
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
    costing(token: string, costingId: number): Promise<CostingPickerOut> {
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
};
