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
  // Inline ảnh (data:/blob:) — vd ảnh QC chụp tại xưởng nhúng base64 — trả nguyên, KHÔNG ghép BASE_URL.
  if (/^(https?:|data:|blob:)/i.test(path)) return path;
  return `${BASE_URL}${path}`;
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
    // 422 của FastAPI trả `detail` là MẢNG `{loc, msg}`, không phải chuỗi. Trước 15/08/2026 nhánh
    // này không tồn tại ⇒ mọi lỗi kiểm dữ liệu của CẢ APP rơi về câu chung "Request failed (422)."
    // Không nói trường nào sai thì người dùng chỉ biết bấm lại, còn người sửa code phải dựng lại
    // thân request rồi bắn thử từng cái để đoán — đã mất hai lượt vì đúng chỗ này.
    if (Array.isArray(detail) && detail.length > 0) {
      const doc = (it: unknown): string | null => {
        const o = it as { loc?: unknown; msg?: unknown };
        if (typeof o?.msg !== "string") return null;
        // `loc` = ["body", "<trường>", <chỉ số>, ...] — bỏ "body", còn lại là đường dẫn tới ô sai.
        const duong = Array.isArray(o.loc)
          ? o.loc.filter((x) => x !== "body" && x !== "query" && x !== "path").join(" › ")
          : "";
        return duong ? `${duong}: ${o.msg}` : o.msg;
      };
      const ds = detail.map(doc).filter((x): x is string => x !== null);
      if (ds.length > 0) {
        // Cắt ở 3: một form sai chục ô thì banner dài hơn cả form. Ba cái đầu đủ để biết đi đâu sửa.
        return ds.slice(0, 3).join(" · ") + (ds.length > 3 ? ` (+${ds.length - 3} lỗi nữa)` : "");
      }
    }
  } catch {
    /* non-JSON error body */
  }
  return null;
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

/** Khuôn CHUNG của mọi endpoint danh sách có phân trang.
 *
 *  `total` = tổng dòng KHỚP BỘ LỌC trên toàn bảng, KHÁC `items.length` (số dòng của trang đang
 *  xem). Chân bảng phải in `total`; in `items.length` thì màn nào cũng báo "Tổng 20". */
export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

/** Dựng chuỗi query, BỎ QUA ô rỗng (`undefined` / `null` / chuỗi rỗng).
 *
 *  Vì sao phải bỏ: gửi `?q=` (rỗng) lên là backend nhận chuỗi rỗng chứ không phải "không lọc" —
 *  tuỳ endpoint mà ra bảng trắng. Trả về "" khi không có ô nào, để nối thẳng vào path được.
 *
 *  ⚠ Đừng đổi tên thành `qs`: trong file này `qs` đang là tên BIẾN CỤC BỘ ở hàng chục hàm
 *  (`const qs = new URLSearchParams()`), đặt trùng là người đọc sau tưởng hai thứ là một. */
function qs(params?: Record<string, string | number | boolean | undefined | null>): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    sp.set(key, String(value));
  }
  const text = sp.toString();
  return text ? `?${text}` : "";
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

// --- Real-time luồng gửi duyệt (SSE) ----------------------------------------
// EventSource gốc KHÔNG set được header Authorization → dùng fetch + ReadableStream để đọc SSE có
// Bearer. Tự reconnect (kèm refresh token khi 401). Sự kiện chỉ là tín hiệu nhẹ; số chính xác lấy
// qua notifySummary(). Trả hàm đóng kết nối (gọi khi logout/unmount).

export interface QuoteNotifySummary {
  pending_approval_count: number;
  my_decided_unseen: number;
}

export interface AdvanceNotifySummary {
  pending_approval_count: number;
}

/** Badge Thu mua. Ba số đã lọc theo phạm vi người gọi ở SERVER — FE chỉ việc cộng.
 *  `dot_giao_qua_han` là số CÔNG NỢ: server trả 0 cho người không có `ke_toan:read`, nên đừng
 *  thêm luật che ở đây (hai nơi cùng giữ một luật là hai nơi lệch nhau). */
export interface PurchaseNotifySummary {
  ycmh_cho_lap_phieu: number;
  pmh_bi_tu_choi: number;
  dot_giao_qua_han: number;
}

export type ModuleNotificationChannel = "thu_mua" | "ke_toan";

export interface ModuleNotificationSummary {
  thu_mua: number;
  ke_toan: number;
}

export type QuoteEvent =
  | { type: "quote_decision"; quote_id: number; code: string; decision: "approved" | "rejected" }
  | { type: "quote_pending_changed"; code?: string }
  // Đơn hàng bán dùng CHUNG kênh hub (bám logic SSE báo giá): quyết định duyệt/đủ cọc gửi riêng
  // người soạn; 'pending_changed' là tín hiệu danh sách chờ đổi → refetch notify-summary theo vai.
  // `order_decision` đã gỡ cùng luồng duyệt đơn đặc thù (backend không publish nữa).
  | { type: "order_deposit_ok"; code: string }
  | { type: "order_pending_changed"; code?: string }
  // Lịch hẹn chăm sóc (redesign-lich-hen-cham-soc): ticker đẩy "care_due" khi tới giờ hẹn,
  // "care_assigned" khi giao hẹn cho người khác — gửi riêng người phụ trách.
  | { type: "care_due"; customer: string; customer_id: number; note: string }
  | { type: "care_assigned"; customer: string; customer_id: number; note: string }
  // Phiếu bảo trì tới ngày (ticker `bao_tri_reminders.py`): gửi riêng người NHẬN việc, phiếu chưa
  // ai nhận thì gửi mọi tài khoản có quyền sửa `ky_thuat_may` (tổ sửa chữa).
  | { type: "bao_tri_due"; phieu_id: number; ma: string; may: string; goi: string; qua_han: boolean }
  // Tạm ứng lương: NV gửi đề nghị → 'pending_changed' (người duyệt refetch badge); kế toán
  // duyệt/từ chối → 'decision' gửi riêng nhân viên đề nghị.
  | { type: "advance_pending_changed"; code?: string }
  | { type: "advance_decision"; code?: string; decision: "approved" | "rejected" }
  // Phiếu tăng ca: NV gửi/hủy → 'ot_pending_changed' (người duyệt refetch badge); tổ trưởng
  // duyệt/từ chối → 'ot_decision' đẩy riêng cho nhân viên nộp phiếu.
  | { type: "ot_pending_changed"; code?: string }
  | { type: "ot_decision"; code?: string; decision: "approved" | "rejected" }
  // Phiếu đi muộn / về sớm / nghỉ nửa buổi: cùng luồng với tăng ca (tổ trưởng duyệt), bảng riêng.
  | { type: "el_pending_changed"; code?: string }
  | { type: "el_decision"; code?: string; decision: "approved" | "rejected" }
  // Quản lý đổi ca của một người → đẩy RIÊNG cho chính người đó (5 đường: lưới phân ca, panel
  // Gán ca, gán hàng loạt, sửa hồ sơ, gỡ mốc). `count` = số thay đổi trong lần lưu đó.
  | { type: "shift_changed"; count?: number }
  // Sản xuất (Lát 1) dùng CHUNG kênh hub — tín hiệu NHẸ để hộp việc tổ refetch + "ting". Số chính
  // xác lấy qua to-badges/inbox (đã lọc scope server-side). `lenh_sx_routing` = có lệnh mới PHÁT
  // vào các tổ `to_ids`; `lenh_sx_assigned` = 1 thợ được gán (đích danh tới user).
  | { type: "lenh_sx_routing"; form_id?: number; lenh_ids?: number[]; to_ids: number[] }
  | { type: "lenh_sx_assigned"; lenh_id: number; to_id: number | null }
  | { type: "lenh_sx_phat"; form_id: number; lenh_ids: number[] }
  | { type: "lenh_sx_duyet_mau"; lenh_id: number }
  | { type: "lenh_sx_ban_giao"; lenh_id: number; ban_giao_id: number; to_nhan_id: number | null }
  | { type: "lenh_sx_qc_loi"; lenh_id: number; qc_id: number; to_bi_quy_id: number | null }
  // Handoff Đơn → bàn Kế hoạch SX: đơn chốt 'bắn xuống' hàng chờ; Sale đổi gấp/lưu ý SAU chốt →
  // bàn kế hoạch "ting" (badge nhảy). Nội dung chính xác FE refetch hàng chờ / detail.
  | { type: "order_ordered"; code?: string; order_id: number }
  | { type: "order_sx_hint_changed"; code?: string; order_id: number; is_rush: boolean }
  // Kế hoạch tạo/sửa/xoá lệnh sản xuất → hàng chờ + bước "Sản xuất" ở Đơn hàng cập nhật ngay.
  | { type: "lsx_changed"; order_id: number }
  // Bài ghép tạo/sửa/xoá → hàng chờ ghép + danh sách bài ghép cập nhật ngay (không cần refresh).
  | { type: "bai_ghep_changed" }
  // Xếp lịch: đưa vào/gỡ kế hoạch · gán máy-ca-giờ · khóa → bàn Xếp lịch + badge cập nhật ngay.
  | { type: "xep_lich_changed" }
  // Chốt (thông tin) → báo KẾ TOÁN "đơn chờ ghi cọc" (popup module Phiếu thu). amount = cần thu.
  | { type: "order_deposit_needed"; code?: string; order_id: number; amount: number }
  // Thu mua / Kế toán: tín hiệu NHẸ (danh sách đổi) → refetch badge Thu mua. Backend đã broadcast
  // sẵn hai event này từ mọi đường ghi (`_notify_purchase_changed` / `_notify_accounting_changed`),
  // đợt này chỉ NỐI vào — không mở kênh SSE thứ hai.
  | { type: "purchase_changed"; code?: string | null }
  | { type: "accounting_changed"; code?: string | null }
  | { type: "department_purchase_request_created"; code?: string | null; actor_user_id?: number | null }
  | { type: "sales_invoice_created"; code?: string | null; invoice_id?: number; invoice_number?: string | null }
  | { type: "sales_invoice_cancelled"; code?: string | null; invoice_id?: number; invoice_number?: string | null }
  | { type: "sales_invoice_receipt_created"; code?: string | null; invoice_id?: number; receipt_code?: string | null }
  | { type: "sales_invoice_created"; code?: string | null; invoice_id?: number; invoice_number?: string | null }
  | { type: "sales_invoice_cancelled"; code?: string | null; invoice_id?: number; invoice_number?: string | null }
  | { type: "sales_invoice_receipt_created"; code?: string | null; invoice_id?: number; receipt_code?: string | null }
  | { type: "purchase_pending_approval"; code?: string | null; actor_user_id?: number | null }
  | {
      type: "purchase_decision";
      code?: string | null;
      decision: "approved" | "rejected";
      actor_user_id?: number | null;
      recipient_user_id?: number | null;
    }
  | { type: "purchase_delivery_created"; code?: string | null; seq_no?: number | null; actor_user_id?: number | null }
  | { type: "purchase_delivery_updated"; code?: string | null; seq_no?: number | null; actor_user_id?: number | null }
  | { type: "purchase_delivery_deleted"; code?: string | null; seq_no?: number | null; actor_user_id?: number | null }
  | { type: "purchase_invoice_updated"; code?: string | null; actor_user_id?: number | null }
  | {
      type: "payment_voucher_created";
      code?: string | null;
      voucher_code?: string | null;
      actor_user_id?: number | null;
      recipient_user_id?: number | null;
    }
  | {
      type: "payment_voucher_cancelled";
      code?: string | null;
      voucher_code?: string | null;
      actor_user_id?: number | null;
      recipient_user_id?: number | null;
    }
  // Kho (spec-kho-de-nghi §10): `stock_request` = tin đích danh có sẵn câu chữ để toast;
  // `stock_request_pending_changed` = tín hiệu NHẸ (danh sách chờ đổi) → chỉ refetch badge.
  | { type: "stock_request"; code?: string; message: string; loai?: "NHAP" | "XUAT" }
  | {
      type: "stock_request_pending_changed";
      code?: string;
      loai?: "NHAP" | "XUAT";
      nguoi_tao_id?: number;
      nguoi_tao_ten?: string | null;
      bo_phan_ten?: string | null;
    }
  // `notification_new` = có thông báo mới vào chuông → FE refetch list + badge chuông.
  | { type: "notification_new" };

// --- Trung tâm thông báo (chuông Topbar) -------------------------------------
export interface AppNotification {
  id: number;
  loai: string;
  tieu_de: string;
  noi_dung: string | null;
  /** Đích điều hướng: 'kho_inbox' (Hộp yêu cầu) · 'kho_mine' (màn Yêu cầu). NULL = không nhảy. */
  link_loai: string | null;
  link_id: number | null;
  read_at: string | null;
  da_doc: boolean;
  created_at: string;
}

export interface NotificationList {
  items: AppNotification[];
  unread: number;
}

// --- Lệnh sản xuất (LSX) — bàn Kế hoạch sản xuất ------------------------------
// Job (đơn) → Part (lệnh) → Operation (công đoạn). Mỗi DÒNG ĐƠN = 1 lệnh, ngang hàng.
export type LsxTrangThai =
  | "nhap"
  | "cho_bo_sung"
  | "san_sang"
  | "da_lap_ke_hoach"   // đã sinh dòng xếp lịch (≈ Firm Planned) — routing khóa
  | "da_phat_hanh";     // đã phát hành xuống xưởng (≈ Released)
export type LsxDonVi = "to_nguyen" | "to" | "cai" | "kem" | "bai";
/** Loại bước = tài nguyên mà bước chiếm khi lên lịch. */
export type LsxLoaiBuoc = "may" | "to" | "thue_ngoai";



/** Nhãn + màu của loại bước. `tone` map sang class `.khsx-lb--{tone}` trong ke-hoach-sx.css. */
export const LSX_LOAI_BUOC_META: Record<LsxLoaiBuoc, { label: string; tone: string; hint: string }> = {
  may: { label: "Máy", tone: "may", hint: "Chiếm máy — có thanh trên lịch máy" },
  to: { label: "Tổ", tone: "to", hint: "Tổ lao động làm tay — chiếm nhân công, không chiếm máy" },
  thue_ngoai: { label: "Thuê ngoài", tone: "ngoai", hint: "Nhà gia công làm — không chiếm máy nội bộ" },
};

/** Đơn vị bốn chặng của lệnh đang xét — xem `pages/lsxBuoc.donViChuoi`. Khai lại hình dạng tối
 *  thiểu ở đây để `client.ts` không phải import ngược từ `pages/`. */
export interface DonViNhan { to: string; tp: string; tay: string; toNguyen: string }
const DV_TRONG: DonViNhan = { to: "", tp: "", tay: "", toNguyen: "" };

/** Nhãn checklist: chuỗi cố định, hoặc HÀM khi câu cần gọi tên đơn vị của chính lệnh đó. */
type NhanMa = string | ((dv: DonViNhan) => string);

/** Mã checklist "thiếu gì" → nhãn hiển thị (server trả mã, FE dịch). CHẶN nút Sẵn sàng.
 *
 *  Bốn câu nhắc tới ĐƠN VỊ là HÀM, không phải chuỗi (12/08/2026): tên đơn vị do xưởng đặt trong
 *  danh mục, viết cứng "tờ in → con" thì lệnh khai `to_chay`/`sp_xong` đọc lên là hai chữ KHÔNG
 *  tồn tại trên màn hình — người dùng đi tìm không thấy. Không đọc được đơn vị (routing chưa khai)
 *  thì hàm tự lùi về câu chung, KHÔNG bịa tên. */
export const LSX_THIEU_LABELS: Record<string, NhanMa> = {
  khong_co_ptg: "Chưa có bài tính giá",
  thieu_giay: "Thiếu loại giấy",
  thieu_kho: "Thiếu kích thước",
  thieu_routing: "Chưa có công đoạn",
  thieu_ngay_giao: "Thiếu ngày giao",
  thieu_to_may: "Có công đoạn chưa gán tổ / máy",
  thieu_ncc: "Công đoạn thuê ngoài chưa có nhà gia công",
  thieu_tg_thue_ngoai: "Công đoạn thuê ngoài chưa có ngày gửi / nhận",
  // Hệ số quy đổi nay do server suy, không ai khai — chỉ thiếu NGUỒN của nó mới là lỗi thật.
  // Ba cầu, ba nguồn KHÁC NHAU: đổi mức lấy Con/tờ, xả giấy lấy số mảnh xả, còn sách thì lấy
  // số trang / trang mỗi tay (KHÔNG dùng con/tờ) — nên lệnh sách thiếu ở chỗ khác lệnh tờ rời.
  thieu_con_tren_to: (dv) =>
    dv.to && dv.tp
      ? `Chưa khai Con/tờ — có công đoạn đổi ${dv.to} → ${dv.tp}`
      : "Chưa khai Con/tờ — có công đoạn đổi cách đếm",
  thieu_manh_xa: (dv) =>
    dv.toNguyen && dv.to
      ? `Chưa có số mảnh xả — có công đoạn đổi ${dv.toNguyen} → ${dv.to}`
      : "Chưa có số mảnh xả — có công đoạn xả giấy",
  thieu_trang_moi_tay: (dv) =>
    dv.tay && dv.tp
      ? `Chưa khai Số trang / Trang mỗi tay — có công đoạn đổi ${dv.tay} → ${dv.tp}`
      : "Chưa khai Số trang / Trang mỗi tay — có công đoạn gom tay thành cuốn",
};

/** Cảnh báo MỀM — chỉ tô màu, không chặn lưu và không chặn Sẵn sàng. */
export const LSX_CANH_BAO_LABELS: Record<string, NhanMa> = {
  ra_lon_hon_vao: "Có công đoạn ra nhiều hơn vào",
  dut_chuyen: "Đứt chuyền — bước sau đòi nhiều hơn bước trước giao",
  vuot_han_giao: "Tổng thời gian dẫn vượt hạn giao khách",
  khac_bai_tinh_gia: "Routing đã đổi so với bài tính giá",
  may_khong_hop_kho: (dv) => `Khổ ${dv.to || "tờ in"} vượt khổ tối đa của máy`,
  // Chuỗi 3 đơn vị (tờ nguyên → tờ in → tờ thành phẩm) — kiểm trên các bước CÓ đơn vị, bước
  // không chạm giấy (chế bản) đứng ngoài.
  // Bước khai đơn vị hợp lệ nhưng KHÔNG nằm trên dòng giấy (vd `lượt → lượt`): nó rơi khỏi chuỗi
  // bù hao nên số lượng đứng im ở 0 và hao của nó biến mất khỏi số giấy — phải nói ra.
  buoc_ngoai_dong_giay: "Có công đoạn khai đơn vị ngoài dòng giấy — số lượng và bù hao của nó không được tính",
  cap_don_vi_sai: "Có công đoạn khai đơn vị đi ngược dòng giấy",
  dut_don_vi: "Chuỗi đứt đơn vị — bước sau ăn đơn vị khác bước trước nhả",
  lech_sl_don: "Bước cuối ra khác số lượng đơn đặt",
};

/** Mã → câu, đã thế tên đơn vị của CHÍNH lệnh đang xét. Mã lạ ⇒ trả mã trần (thà thấy mã còn hơn
 *  nuốt mất). `dv` bỏ trống ⇒ câu lùi về bản chung, không có tên đơn vị nào. */
export function nhanMa(
  bang: Record<string, NhanMa>, ma: string, dv?: DonViNhan | null,
): string {
  const n = bang[ma];
  if (n === undefined) return ma;
  return typeof n === "function" ? n(dv || DV_TRONG) : n;
}

// --- Bài ghép (print gang) — gom công đoạn in nhiều LSX chạy chung 1 tờ --------
export type BaiGhepTrangThai = "nhap" | "san_sang";

/** Checklist CHẶN "sẵn sàng xếp lịch" (server trả mã, FE dịch). */
export const BAI_GHEP_THIEU_LABELS: Record<string, string> = {
  thieu_thanh_vien: "Cần ít nhất 2 lệnh",
  thieu_giay: "Chưa chọn giấy chạy chung",
  thieu_kho_in: "Chưa có khổ tờ in chung",
  thieu_ups: "Có thành viên chưa khai số con/tờ",
  // Chưa gộp bước nào = N lệnh rời, chưa phải bài ghép. Đây là trạng thái MẶC ĐỊNH của bài mới
  // tạo, nên thiếu nhãn là ai mở bài cũng thấy chữ mã trần.
  thieu_buoc_chung: "Chưa gộp bước nào — chọn bước cùng công đoạn ở các lệnh rồi bấm Gộp",
  thieu_ke_hoach_buoc_chung: "Lượt chạy chung chưa có tổ / máy / năng suất",
  thieu_so_to: "Chưa tính được số tờ",
};

/** Cảnh báo MỀM — chỉ tô màu, không chặn. Chỉ còn tín hiệu về TRẠNG THÁI đơn/lệnh.
 *
 *  ĐÃ BỎ `khac_giay` / `khac_so_mau` / `khac_so_mat` / `bai_thua`: điều kiện gộp chỉ là cùng công
 *  đoạn, còn quy cách thì người dùng có nghiệp vụ đó — máy không phán hộ. Bảng "Kiểm tương thích"
 *  vẫn bày đủ giá trị để người tự so, và `fill_pct` vẫn hiện dưới dạng con số. */
export const BAI_GHEP_CANH_BAO_LABELS: Record<string, string> = {
  co_gap: "Có lệnh GẤP trong bài",
  lech_han: "Hạn giao các lệnh lệch nhau xa",
  thanh_vien_khong_san_sang: "Có lệnh không còn sẵn sàng",
  don_huy: "Có lệnh thuộc đơn đã huỷ",
};

/** Mức tương thích 1 thuộc tính giữa các thành viên → nhãn + tone (class `.bghep-muc--{tone}`). */
export const BAI_GHEP_MUC_META: Record<string, { label: string; tone: string }> = {
  phu_hop: { label: "Phù hợp", tone: "ok" },
  can_xac_nhan: { label: "Cần xác nhận", tone: "warn" },
  khong_phu_hop: { label: "Không phù hợp", tone: "bad" },
};

export interface HangChoGhepItem {
  lsx_id: number; ma: string; ten: string | null;
  so_luong_dat: number; don_vi_tinh: string | null; so_con: number;
  han_hoan_thanh_sx: string | null; is_rush: boolean;
  order_id: number | null; customer_name: string | null;
  giay_id: number | null; giay_ten: string | null; gsm: number | null;
  so_mau_a: number | null; so_mau_b: number | null; quy_cach_in: string | null;
  /** TẬP mã mực mỗi mặt — hai lệnh cùng nhãn "4/1" vẫn có thể khác bộ bản. */
  muc_a: string[]; muc_b: string[];
  kho_tp: string | null; kho_in: string | null;
}
export interface HangChoGhepOut { items: HangChoGhepItem[]; total: number }

export interface BaiGhepListItem {
  id: number; ma: string; trang_thai: BaiGhepTrangThai; so_lsx: number;
  giay_ten: string | null; kho_in: string | null;
  so_to_tot: number; tong_to: number; han_in_muon_nhat: string | null; so_canh_bao: number;
}
export interface BaiGhepListOut { items: BaiGhepListItem[]; total: number }

export interface BaiGhepThanhVien {
  thanh_vien_id: number; lsx_id: number; lsx_ma: string | null; lsx_ten: string | null;
  so_luong_dat: number; don_vi_tinh: string | null; is_rush: boolean; trang_thai_lsx: string | null;
  so_con_tren_to: number; san_luong_du_kien: number; du: number;
  /** Bước gộp CUỐI CÙNG của lệnh = điểm toả. null = lệnh chưa gộp bước nào. */
  toa_step_key: string | null;
  /** Số tờ lệnh THẬT SỰ cần — đã gồm hao các bước riêng, khác `ceil(SL đặt / con)`. */
  nhu_cau_to: number;
  du_to: number;
  phan_giay_to: number; ty_le_giay: number;
  /** D3: gợi ý con/tờ — tối đa theo khổ (ước lượng) + gợi ý cân sản lượng để giảm dư. 0 = không có. */
  con_toi_da: number; con_goi_y: number;
  giay_id: number | null; giay_ten: string | null;
  so_mau_a: number | null; so_mau_b: number | null; quy_cach_in: string | null;
  muc_a: string[]; muc_b: string[];
  kho_tp: string | null; han_hoan_thanh_sx: string | null;
}
/** Sơ đồ bài ghép — routing ĐẦY ĐỦ từng lệnh + các bước NGƯỜI khai là chạy chung.
 *  DẪN XUẤT ở server, không lưu cạnh: hình tụ-rồi-toả rơi ra từ phép co nút. */
export interface BaiGhepSoDoNode {
  step_key: string; ten: string; nhom: string | null; loai_buoc: LsxLoaiBuoc; thu_tu: number;
  /** Khoá điều kiện gộp: chỉ các bước CÙNG công đoạn mới gộp được với nhau. */
  cong_doan_id: number | null;
  /** Khác null = bước này đang bị một bước chung ĐÈ (thẻ chung mới là nơi hiện số/tổ/máy). */
  gop_step_key: string | null;
  to_ten: string | null; may_ten: string | null; nha_cung_cap: string | null;
  tong_phut: number; chiem_may_phut: number;
  /** Dải nhanh–chậm nhất theo tốc độ tối đa / tối thiểu của máy (= TB nếu chưa khai dải). */
  chiem_may_phut_min: number; chiem_may_phut_max: number;
  phu_thuoc_step_keys: string[];
  /** Sau điểm toả là số LƯỢT ĐI (bài chạy bấy nhiêu tờ thì bước này thật sự nhận/ra bấy nhiêu);
   *  trước đó là lượt về của chính lệnh. null ở bước ngoài dòng giấy (chế bản đếm kẽm). */
  so_luong_vao: number | null; so_luong_ra: number | null;
  don_vi_vao: string | null; don_vi_ra: string | null; hao_hut: number | null;
}
/** Một lượt chạy CHUNG — thẻ trải ngang, nhánh tụ vào trái và toả ra phải. */
export interface BaiGhepSoDoBuocChung {
  step_key: string; ten: string; nhom: string | null; cong_doan_id: number | null;
  loai_buoc: LsxLoaiBuoc; thu_tu: number;
  /** `false` = bước chế bản (chung BẢN/kẽm), KHÔNG trên dòng giấy → thẻ ẩn số tờ vào/ra. */
  tren_giay: boolean;
  /** Số của CẢ LƯỢT. Đơn vị lấy từ khai báo công đoạn — bước bế nhả `cai` thì `so_luong_ra` đếm con. */
  so_luong_vao: number; so_luong_ra: number;
  don_vi_vao: string | null; don_vi_ra: string | null;
  /** `ra` quy về ĐƠN VỊ VÀO + hệ số đã dùng — cùng bộ số `bu_hao_chi_tiet` của tính giá. Thiếu hai
   *  số này thì dòng đổi đơn vị đọc lên vô lý ("20.500 tờ → 2.050 cuốn" mà không nói 10 tờ = 1 cuốn). */
  he_so_quy_doi: number; so_luong_ra_quy: number | null;
  /** Hao đếm ĐÚNG MỘT LẦN cho cả lượt, ở ĐƠN VỊ VÀO — thứ mất trên máy là tờ, không phải con. */
  hao_hut: number; hao_hut_pct: number;
  /** Chuỗi đứt đơn vị / thiếu hệ số — phải lộ ra, đừng lặng lẽ chạy hệ số 1. */
  canh_bao_don_vi: string[];
  /** T3: cảnh báo mềm máy không hợp công đoạn (sai loại / vượt khổ-màu-gsm). */
  may_khong_hop: string[];
  /** T3: nhóm máy (loai_may) làm được công đoạn này — FE lọc dropdown máy theo đây. [] = không ràng buộc. */
  nhom_may_cho_phep: string[];
  /** Đã khai gì đó cho lượt chung chưa → tách ra là mất. Cờ THẬT của server, đừng dò chuỗi `thieu`. */
  da_lap_ke_hoach: boolean;
  /** ID + TÊN: `<select>` cần id để chọn đúng, nhãn cần tên. Chỉ có tên là form phải lấy tên làm
   *  `value` rồi so chuỗi với id — tổ đã gán vẫn hiện "— chọn tổ —". */
  department_id: number | null; to_ten: string | null;
  may_id: number | null; may_ten: string | null;
  nha_cung_cap: string | null;
  tong_phut: number; chiem_may_phut: number;
  chiem_may_phut_min: number; chiem_may_phut_max: number;
  /** Giá trị NGƯỜI đã khai — form mồi lại từ đây, không thì mở drawer là ô trống rồi lưu đè mất. */
  so_nhan_cong: number;
  nang_suat: number | null; don_vi_nang_suat: string | null;
  /** Dẫn xuất từ tốc độ máy; `setup_phut` kế thừa từ máy. Ô gõ được duy nhất là
   *  `phat_sinh_phut` ("Thời gian khác"). `cho_phut`/`di_chuyen_phut` đã bỏ. */
  chay_phut: number | null;
  setup_phut: number; phat_sinh_phut: number;
  so_luot_chay: number;
  /** Khoán của lượt chung — cùng hợp đồng với bước lệnh: phần GHIM (đầu việc đã chọn) + danh
   *  sách chọn được của TỔ đang gán + phần DẪN XUẤT (SL quy đổi · tiền · diễn giải). */
  khoan_rate_id: number | null;
  khoan_ten: string | null;
  khoan_don_vi: string | null;
  khoan_don_gia: number | null;
  /** Định mức (năng suất · số người) chỉ có khi công đoạn đã nối đầu việc đó — nên phần ấy là
   *  TUỲ CHỌN, đừng khai đủ `LsxDauViecOption` rồi đọc bừa. */
  khoan_chon_duoc: (Pick<LsxDauViecOption, "id" | "ten" | "don_vi" | "don_gia"> &
    Partial<LsxDauViecOption>)[];
  khoan_sl: number | null;
  khoan_don_vi_sl: string | null;
  khoan_tien: number | null;
  khoan_dien_giai: string | null;
  khoan_thieu: string[];
  khoan_ly_do: string | null;
  vat_tus: { vat_tu_id: number; ma: string; ten: string; don_vi: string; so_luong: number }[];
  /** Gia công ngoài (DỰ KIẾN) — bước chung thuê ngoài thì cả bài đi MỘT phiếu, MỘT nhà cung cấp. */
  sl_gui: number | null; ngay_gui_dk: string | null;
  van_chuyen_ngay: number | null; gia_cong_ngay: number | null; ngay_nhan_dk: string | null;
  hao_hut_cho_phep: number | null; don_gia_gia_cong: number | null;
  yeu_cau_ky_thuat: string | null;
  ghi_chu: string | null; ma_bai_ghep: string | null;
  /** Lệnh nào bị đè + ghi chú kỹ thuật của lệnh đó (GOM, không đè). */
  thanh_vien: { lsx_id: number; lsx_ma: string | null; lsx_step_key: string;
                ghi_chu_ky_thuat: string | null }[];
  thieu: string[];
}
export interface BaiGhepSoDoNhanh {
  thanh_vien_id: number; lsx_id: number; lsx_ma: string | null; lsx_ten: string | null;
  customer_name: string | null; han_hoan_thanh_sx: string | null; is_rush: boolean;
  /** Chỉ số màu của nhánh — FE map sang bảng màu, để ba đơn hàng cạnh nhau không lẫn. */
  mau: number;
  so_con_tren_to: number;
  toa_step_key: string | null;
  nhu_cau_to: number; du: number; san_luong_du_kien: number;
  /** Dư TỜ ngay tại điểm toả — khác dư con ở cuối chuỗi. */
  du_to: number;
  /** Phần giấy lệnh này gánh, chia theo CON. Tờ dùng chung nên không có "tờ của lệnh nào" —
   *  chia được là CHI PHÍ giấy, theo diện tích chiếm trên tờ. */
  phan_giay_to: number; ty_le_giay: number;
  /** Routing ĐẦY ĐỦ của lệnh, theo thứ tự. Bước đã gộp mang `gop_step_key`, không biến mất. */
  buoc: BaiGhepSoDoNode[];
}
export interface BaiGhepSoDo {
  bai_ghep: {
    id: number; ma: string; trang_thai: string;
    may_id: number | null; may_ten: string | null;
    giay_id: number | null; giay_ten: string | null;
    kho_in_dai: number | null; kho_in_rong: number | null;
    hao_hut_setup: number | null; hao_hut_chay: number | null;
    so_to_tot: number; tong_to: number; fill_pct: number | null;
    /** Hao đề xuất của các lượt chung, tách setup/chạy vì hai thứ áp khác nhau. */
    hao_de_xuat: number; hao_setup_de_xuat: number; hao_chay_de_xuat: number;
    /** Giấy phải LĨNH KHO = tờ in + hao. Khác `so_to_tot` (tờ in). */
    to_nguyen_can: number;
    so_buoc_chung: number;
  };
  nhanh: BaiGhepSoDoNhanh[];
  gop: BaiGhepSoDoBuocChung[];
  /** Tiền nhiệm NGOÀI bài (vd ruột sách cùng đơn) → node bóng mờ. */
  ngoai: { step_key: string; ten: string; lsx_ma: string | null }[];
}

export interface BaiGhepSoTo {
  so_to_tot: number; tong_to: number; fill_pct: number | null; han_in_muon_nhat: string | null;
  /** Hao của các lượt chạy chung (tách setup/chạy), và giấy phải lĩnh kho (= tờ in + hao). */
  hao_de_xuat: number; hao_setup_de_xuat: number; hao_chay_de_xuat: number;
  /** T1: hao THẬT đang áp (tôn trọng khai tay/khai 0) + tỷ lệ hao/tốt (cảnh báo makeready nuốt sản lượng). */
  hao_ap_dung: number; ty_le_hao: number;
  /** T4: breakdown hao đề xuất per bước chung — để tooltip "Giấy lĩnh kho" nối tổng với thẻ. */
  hao_theo_buoc: { ten: string; hao: number }[];
  to_nguyen_can: number; so_buoc_chung: number;
  rows: { thanh_vien_id: number; lsx_id: number; can: number; con: number; co_gop: boolean;
          toa_step_key: string | null;
          nhu_cau_to: number; du_to: number; san_luong_du_kien: number; du: number }[];
}

/** Kế hoạch của lượt chạy chung. Số lượng/hao/thời lượng KHÔNG có ở đây — chúng là dẫn xuất. */
export interface BaiGhepBuocChungBody {
  department_id?: number | null; may_id?: number | null; loai_buoc?: LsxLoaiBuoc;
  /** Đầu việc khoán ghim theo ID (0/null = bỏ chọn). Ảnh chụp đơn giá do SERVER chụp — client
   *  không gửi `khoan_json` thô, kẻo đơn giá bịa chảy thẳng vào phiếu lương. */
  so_nhan_cong?: number; piece_rate_id?: number | null;
  nang_suat?: number | null; don_vi_nang_suat?: string | null;
  /** Ô DUY NHẤT còn gõ được (2026-08-04): chuẩn bị + tốc độ kế thừa SỐNG từ máy đang gán. */
  phat_sinh_phut?: number; so_luot_chay?: number;
  ghi_chu?: string | null;
  vat_tus?: { vat_tu_id: number; so_luong: number }[];
  nha_cung_cap?: string | null; sl_gui?: number | null; ngay_gui_dk?: string | null;
  van_chuyen_ngay?: number | null; gia_cong_ngay?: number | null; ngay_nhan_dk?: string | null;
  hao_hut_cho_phep?: number | null; don_gia_gia_cong?: number | null;
  yeu_cau_ky_thuat?: string | null;
}
/** `step_key → gộp thêm vào được không, không thì vì sao` (kiểm TRƯỚC khi cho bấm Gộp). */
export interface BaiGhepUngVienGop {
  ung_vien: Record<string, { gop_duoc: boolean; ly_do: string | null }>;
}
export interface BaiGhepTuongThichRow { thuoc_tinh: string; gia_tri: (string | null)[]; muc: string }
export interface BaiGhepTuongThich { thanh_vien: { lsx_id: number }[]; rows: BaiGhepTuongThichRow[] }
export interface BaiGhepDetail {
  id: number; ma: string; trang_thai: BaiGhepTrangThai;
  giay_id: number | null; giay_ten: string | null;
  kho_in_dai: number | null; kho_in_rong: number | null;
  may_id: number | null; may_ten: string | null;
  /** `null` = CHƯA KHAI (bài dùng hao máy đề xuất) · `0` = khai "chạy đúng số, không bù". */
  hao_hut_setup: number | null; hao_hut_chay: number | null; ghi_chu: string | null;
  thanh_vien: BaiGhepThanhVien[];
  so_to: BaiGhepSoTo;
  tuong_thich: BaiGhepTuongThich;
  thieu: string[]; canh_bao: string[];
}
export interface BaiGhepUpdateBody {
  giay_id?: number | null; kho_in_dai?: number | null; kho_in_rong?: number | null;
  /** Gửi `null` = xoá khai báo (quay về hao máy đề xuất); gửi `0` = khai "không bù hao". */
  may_id?: number | null; hao_hut_setup?: number | null; hao_hut_chay?: number | null;
  ghi_chu?: string | null;
}

// --- Xếp lịch công đoạn — bàn xếp lịch (máy + giờ) của Kế hoạch sản xuất -------
// Routing đã "sẵn sàng" → đưa vào kế hoạch (khóa routing) → gán máy/tổ/NCC + ca + giờ; hệ tính giờ
// kết thúc + độ dư + nhãn nguy cơ + cờ xung đột. Số DẪN XUẤT tính lúc đọc ở server (không lưu cột).
export type XepLichNguon = "lsx" | "in_ghep";
/** Nhãn nguy cơ trễ do server chấm (theo độ dư so hạn). FE dịch qua NguyCoTreChip. */
export type XepLichRuiRo =
  | "an_toan"
  | "sap_toi_han"
  | "nguy_co_tre"
  | "da_tre"
  | "chua_co_han";

/** 1 nguồn trong order-pool "Chờ xếp": LSX độc lập hoặc bài ghép đã sẵn sàng, chưa đưa vào kế hoạch. */
export interface XepLichHangChoItem {
  nguon: XepLichNguon;
  id: number;
  ma: string;
  ten: string | null;
  so_cong_doan: number;
  is_rush: boolean;
  han_hoan_thanh_sx: string | null;
}
export interface XepLichHangChoOut { items: XepLichHangChoItem[]; total: number }

/** 1 dòng lịch = 1 công đoạn cần xếp (hoặc lần in chung của bài ghép). Mọi số dẫn xuất đã tính sẵn. */
export interface XepLichRow {
  id: number;
  nguon: XepLichNguon;
  lsx_id: number | null;
  bai_ghep_id: number | null;
  lsx_ma: string | null;         // in_ghep → mã bài ghép
  cong_doan_ten: string | null;  // in_ghep → "In chung"
  loai_buoc: LsxLoaiBuoc | null;
  so_luong_vao: number | null;
  don_vi_vao: string | null;
  // Tài nguyên gán (record-only: máy đề xuất, người quyết)
  may_id: number | null;
  may_ten: string | null;
  department_id: number | null;
  department_ten: string | null;
  nha_cung_cap: string | null;
  work_shift_id: number | null;
  // Lịch (ISO datetime "giờ nhà máy") + dẫn xuất
  som_nhat: string | null;
  muon_nhat: string | null;
  start_at: string | null;
  finish_at: string | null;
  chiem_may_phut: number;
  /** Dải nhanh–chậm nhất — Gantt vẽ RÂU ở đuôi thanh (thanh đặt theo TB). */
  chiem_may_phut_min: number; chiem_may_phut_max: number;
  tong_phut: number;
  // Breakdown chiếm máy (Gantt vẽ thanh 2 đoạn setup+chạy). Vệ sinh/rửa mực đã bỏ khỏi hệ.
  setup_phut: number;
  chay_phut: number;
  theo_may: boolean;                     // thời lượng tính LẠI theo tốc độ máy đang gán (HM3) vs snapshot
  canh_bao_thoi_luong: string | null;    // may_chua_toc_do | don_vi_lech — vì sao không tính-theo-máy được
  slack_ngay: number | null;
  nhan_rui_ro: XepLichRuiRo | null;
  // Trạng thái
  trang_thai: string;            // cho_xep | da_xep
  is_locked: boolean;
  co_xung_dot: boolean;
  blocked_reason: string | null; // thieu_may | thieu_thoi_luong | cho_tien_de | …
  // Kiểm khả năng máy (HM4) — soft, KHÔNG chặn. Từ 2026-08-09 CHỈ CÒN KIỂM KHỔ: số màu thì thợ
  // chạy 2 lượt là qua, còn khoảng gsm ở danh mục máy phần lớn chưa khai đúng nên nó loại nhầm.
  can_xac_nhan: boolean;
  ly_do_xac_nhan: string[];      // kho_vuot_may
  is_rush: boolean;
  // --- Đợt 2 ---
  // (`can_dung_cu` + `khuon_be_id` đã gỡ 16/08/2026 cùng hai detector khuôn — xem mg `0203`.)
  so_nhan_cong: number | null;
  so_nhan_cong_toi_thieu: number | null;
  /** Khoá GOM việc cùng loại (giấy · khổ · bộ mực). "Tự xếp" sắp theo khoá này trong cùng mức ưu
   *  tiên để việc cùng setup nằm liền nhau. null = chưa đủ quy cách ⇒ không gom với ai. */
  gom_key: string | null;
}
export interface XepLichRowListOut { items: XepLichRow[]; total: number }

/** Gán tài nguyên/giờ cho 1 dòng — CHỈ gửi field cần sửa (router `exclude_unset`). */
export interface XepLichGanBody {
  may_id?: number | null;
  department_id?: number | null;
  nha_cung_cap?: string | null;
  work_shift_id?: number | null;
  start_at?: string | null;
}
/** 1 dòng trong gán-loạt (bulk) — kèm id dòng. */
export type XepLichGanLoatRow = XepLichGanBody & { id: number };

/** Một khoảng giờ có mức dùng người KHÔNG ĐỔI trong một tổ (mục I) — nền để Gantt tô lane.
 *  Cùng nguồn với detector `qua_tai_to`: Gantt tô đỏ chỗ nào thì cửa phát hành chặn đúng chỗ đó. */
export interface XepLichTaiToKhoang {
  department_id: number;
  department_ten: string | null;
  start: string;
  finish: string;
  dung: number;
  quan_so: number;
  qua_tai: boolean;
  dong_ids: number[];
}

/** Người thuộc khối SX nhưng gắn ở TẦNG GIỮA — không nằm trong tổ lá nào (mục I). */
export interface XepLichNguoiTangGiua {
  department_id: number;
  department_ten: string;
  so_nguoi: number;
}
export interface XepLichTaiToOut {
  items: XepLichTaiToKhoang[];
  tang_giua: XepLichNguoiTangGiua[];
}

/** Quân số + quỹ giờ-người của một TỔ trong một ngày (mục I).
 *  `tu_tinh` = suy từ hồ sơ nhân sự trừ phép đã duyệt; `so_nguoi` = số ĐANG DÙNG (gõ đè nếu có). */
export interface XepLichQuanSo {
  department_id: number;
  ngay: string;
  so_nguoi: number;
  tu_tinh: number;
  go_de: boolean;
  ly_do: string | null;
  gio_ca: number;
  quy_gio_nguoi: number;
}

/** Một ô của bảng tuần (mục J): một tài nguyên × một tuần. Tính lúc đọc, không lưu gì. */
export interface XepLichTuanO {
  tuan: string;
  iso_tuan: number;
  loai: "may" | "to";
  /** Máy gom theo NHÓM ⇒ `res_id` null, dùng `nhom`. Tổ thì `res_id` = id phòng ban. */
  res_id: number | null;
  nhom: string | null;
  ten: string;
  can_gio: number;
  kha_dung_gio: number;
  pct: number;
  mau: "xanh" | "vang" | "do";
}
export interface XepLichKeHoachTuan {
  tu: string;
  so_tuan: number;
  items: XepLichTuanO[];
}

/** Một dòng trong bảng xem trước "Chèn lệnh gấp" (G1) — *giờ cũ → giờ mới*. */
export interface XepLichChenDong {
  id: number;
  lsx_ma: string | null;
  cong_doan_ten: string | null;
  may_id: number | null;
  may_ten: string | null;
  cu: string | null;
  moi: string | null;
  finish_moi: string | null;
  /** Chính việc đang chèn — UI tô khác để phân biệt với việc BỊ đẩy. */
  la_viec_chen: boolean;
  tre_han: boolean;
  /** Mã lệnh/bài mà dòng này sẽ ĐÈ lên sau khi dời — chỉ cảnh báo, KHÔNG đẩy tiếp (đúng một tầng). */
  dung_do: string[];
  is_locked: boolean;
}

/** Kết quả mô phỏng chèn — CHƯA ghi gì; UI áp bằng `ganLoat` khi người dùng bấm Lưu. */
export interface XepLichChen {
  dong_id: number;
  may_id: number;
  start_at: string | null;
  finish_at: string | null;
  chiem_may_phut: number;
  /** `gap_khoa` = dừng lan vì gặp dòng đã khóa. null = lan hết tự nhiên (khe trống nuốt vừa). */
  chan: string | null;
  rows: XepLichChenDong[];
}

/** Một MÁY ứng viên trong bảng gợi ý — tên máy · khe sớm nhất · GIỜ XONG · cờ khổ.
 *
 *  Sắp theo `finish`, KHÔNG theo `khe_trong`: tốc độ khai theo từng máy nên máy rảnh sớm hơn chưa
 *  chắc xong sớm hơn. `chiem_may_phut` tính lại theo chính máy này. */
export interface XepLichGoiYMay {
  may_id: number;
  may_ten: string | null;
  khe_trong: string | null;
  finish: string | null;
  chiem_may_phut: number;
  /** Khổ giấy vượt khổ máy — vẫn liệt kê (xếp cuối) chứ không giấu: máy đề xuất, người quyết. */
  khong_hop_kho: boolean;
  /** Việc liền trước trên máy này cùng giấy · khổ · bộ mực (mục E) — đổi việc gần như khỏi canh
   *  lại máy. Tiêu chí PHỤ khi hoà giờ xong. */
  cung_gom: boolean;
}

/** Gợi ý xếp (chỉ đọc): máy trống sớm nhất + kết thúc nếu xếp + hạn lùi còn kịp giao. */
export interface XepLichGoiY {
  may_id: number | null;
  khe_trong: string | null;
  finish_neu_xep: string | null;
  han_lui: string | null;
  /** Top 3 máy làm được công đoạn, sắp theo GIỜ XONG. Chạy CẢ KHI dòng chưa gán máy — lúc đó bốn
   *  field trên đều rỗng vì chúng bám "máy đang gán". */
  goi_y_may: XepLichGoiYMay[];
}

/** Nền lịch máy cho Gantt: khoảng LÀM VIỆC theo ca của xưởng + vùng KHÓA máy (bảo trì/khóa). */
export interface XepLichLichKhoang { start: string; finish: string }
export interface XepLichVungKhoa {
  start: string; finish: string; ly_do: string | null;
  /** `chan` = máy nghỉ · `mo_them` = máy chạy thêm ngoài ca (mục G3). Hai chuyện NGƯỢC nhau nên
   *  Gantt vẽ khác màu — cùng màu là đọc ngược ý. */
  kieu: XepLichKieuKhoang;
}
export interface XepLichLichNen {
  may_id: number;
  khoang_lam: XepLichLichKhoang[];
  khoang_khoa: XepLichVungKhoa[];
}

/** Xem-trước-ảnh-hưởng khi kéo-thả (đợt 4 — endpoint `/xem-truoc`, KHÔNG commit). Khớp `XemTruocOut`. */
export interface XepLichPreviewBody { may_id?: number | null; start_at: string }
export interface XepLichPreviewDayDoi {
  id: number; cong_doan_ten: string | null; som_nhat: string | null;  // sớm-nhất MỚI sau khi bị đẩy
}
export interface XepLichPreview {
  finish_at: string | null;
  chiem_may_phut: number;
  chiem_may_phut_min: number; chiem_may_phut_max: number;
  setup_phut: number;
  chay_phut: number;
  theo_may: boolean;
  xung_dot_ids: number[];              // id dòng đã xếp sẽ chồng giờ trên máy này
  day_doi: XepLichPreviewDayDoi[];     // bước sau bị đẩy
  han_hoan_thanh_moi: string | null;
  nhan_rui_ro: XepLichRuiRo | null;
  can_xac_nhan: boolean;               // máy có thể không kham nổi (khổ/số màu/định lượng) — cảnh báo, không chặn
  ly_do_xac_nhan: string[];
}

/** Kiểu khoảng giờ RIÊNG của một máy (mục G3) — cùng hình dạng dữ liệu, khác DẤU:
 *  `chan` máy không chạy · `mo_them` máy chạy thêm ngoài ca ("tối thứ Tư máy in 2 chạy thêm 3 tiếng"). */
export type XepLichKieuKhoang = "chan" | "mo_them";

/** 1 khoảng giờ riêng của máy (nghỉ hoặc chạy thêm) — CRUD + Gantt overlay. */
export interface XepLichVungKhoaItem {
  id: number;
  may_id: number;
  start: string;
  finish: string;
  ly_do: string;   // bao_tri | hong_hoc | nghi | khac
  kieu: XepLichKieuKhoang;
  note: string | null;
}
export interface XepLichVungKhoaListOut { items: XepLichVungKhoaItem[] }
export interface XepLichVungKhoaIn {
  tu: string; den: string; ly_do?: string; kieu?: XepLichKieuKhoang; note?: string | null;
}

// --- Vấn đề kế hoạch (xung đột & nguy cơ trễ) — dẫn xuất lúc đọc + state người xử lý ---
export type XepLichSeverity = "chan" | "nghiem_trong" | "cao" | "canh_bao";
export type XepLichVanDeCategory =
  | "trung_may"
  | "de_khoa_may"
  | "sai_tien_nhiem"
  | "thieu_du_lieu"
  | "nguy_co_tre"
  | "may_khong_kham"
  | "qua_tai_may"
  | "han_bai_ghep"
  | "thue_ngoai"
  // --- Đợt 2 (2026-08-09) ---
  // (`trung_khuon` + `khuon_chua_san_sang` đã gỡ 16/08/2026 — xem mg `0203`.)
  | "thieu_vat_tu"           // bảng cân đối báo thiếu — chặn PHÁT HÀNH, không chặn lúc xếp
  | "thieu_nguoi"            // tổ bố trí dưới số người tối thiểu
  // --- Đợt 3 ---
  | "qua_tai_to";            // Σ người các việc cùng lúc trong tổ > quân số có mặt hôm đó
export type XepLichVanDeTrangThai =
  | "moi"
  | "tiep_nhan"
  | "dang_xu_ly"
  | "da_xu_ly"
  | "ngoai_le"
  | "tam_hoan";

export interface XepLichVanDeImpact {
  lsx_ids: number[];
  bai_ghep_ids: number[];
  may_ids: number[];
  dong_ids: number[];
  mas: string[];
}
export interface XepLichVanDeException {
  ly_do: string | null;
  by: number | null;
  expires_at: string | null;
}
export interface XepLichVanDe {
  issue_key: string;
  category: XepLichVanDeCategory;
  severity: XepLichSeverity;
  title: string;
  nguyen_nhan: string | null;
  impacts: XepLichVanDeImpact;
  delay_phut: number | null;
  group_key: string | null;
  // State người xử lý (trộn lúc đọc)
  trang_thai: XepLichVanDeTrangThai;
  assigned_to: number | null;
  note: string | null;
  tai_phat: number;
  mo_lai: boolean;                 // vấn đề tái phát (đã xử lý mà lại dẫn xuất)
  exception: XepLichVanDeException | null;
}
export interface XepLichVanDeSummary {
  chan: number;
  nghiem_trong: number;
  cao: number;
  canh_bao: number;
  ngoai_le: number;
  tong: number;
}
export interface XepLichVanDeListOut {
  items: XepLichVanDe[];
  summary: XepLichVanDeSummary;
  total: number;
}
export interface XepLichVanDeState {
  issue_key: string;
  trang_thai: XepLichVanDeTrangThai;
  assigned_to: number | null;
  note: string | null;
  tai_phat: number;
}
export interface XepLichPhatHanhOut { id: number; ma: string; trang_thai: string }
export interface XepLichSanSangItem {
  nguon: XepLichNguon;
  id: number;
  ma: string;
  blocking: number;
  /** ĐÃ phát hành chưa (G2) — true thì hiện nút "Gỡ phát hành" thay cho "Phát hành". */
  da_phat_hanh: boolean;
}
export interface XepLichSanSangOut { items: XepLichSanSangItem[]; total: number }
export interface XepLichVanDeParams {
  severity?: XepLichSeverity;
  category?: XepLichVanDeCategory;
  trang_thai?: XepLichVanDeTrangThai;
  lsx_id?: number;
  may_id?: number;
}

/** Lý do khóa máy → nhãn hiển thị. */
export const XEP_LICH_KHOA_LABELS: Record<string, string> = {
  bao_tri: "Bảo trì",
  hong_hoc: "Máy hỏng",
  nghi: "Nghỉ",
  khac: "Khác",
};

/** Mã lý do bị chặn (`blocked_reason`) → nhãn hiển thị (server trả mã, FE dịch). */
export const XEP_LICH_BLOCKED_LABELS: Record<string, string> = {
  thieu_may: "Chưa gán máy / tổ",
  thieu_thoi_luong: "Chưa khai năng suất — không tính được thời lượng",
  cho_tien_de: "Chờ bước trước xếp / xong",
};

/** Kiểm khả năng máy (HM4) — mã lý do `ly_do_xac_nhan` → nhãn (máy đề xuất, người quyết; KHÔNG chặn). */
export const XEP_LICH_XAC_NHAN_LABELS: Record<string, string> = {
  kho_vuot_may: "Khổ tờ in vượt khổ máy",
  so_mau_vuot_units: "Số màu vượt số đầu mực máy",
  gsm_ngoai_khoang: "Định lượng giấy ngoài dải máy",
};

/** Cảnh báo thời lượng (HM3) — vì sao KHÔNG tính-theo-máy được (số đang là snapshot bước). */
export const XEP_LICH_CANH_BAO_TL_LABELS: Record<string, string> = {
  may_chua_toc_do: "Máy chưa khai tốc độ — thời lượng theo snapshot bước",
  don_vi_lech: "Đơn vị máy/bước lệch — thời lượng theo snapshot bước",
};

export interface HangChoItem {
  order_id: number;
  order_no: string;
  customer_name: string | null;
  sale_name: string | null;
  delivery_committed_date: string | null;
  is_rush: boolean;
  production_note: string | null;
  san_xuat_released_at: string | null;
  so_dong: number;
  so_dong_co_lsx: number;
}
export interface HangChoOut { items: HangChoItem[]; total: number }

export interface LsxPreviewRouting {
  thu_tu: number; ten: string; nhom: string | null;
  /** Cùng bộ mã với `LsxCongDoan.loai_buoc` — thay cờ `thue_ngoai` cũ, để màn "lệnh dự kiến"
   *  và màn lệnh đã tạo hiển thị giống nhau. */
  loai_buoc: LsxLoaiBuoc;
  department_id: number | null; department_ten: string | null;
  nha_cung_cap: string | null;
}
export interface LsxPreviewLine {
  order_line_id: number;
  ten: string;
  so_luong_dat: number;
  don_vi_tinh: string;
  phieu_thanh_phan_id: number | null;
  ptg_ma: string | null;
  /** Nhãn nhóm — chỉ gom hiển thị; sản xuất vẫn 1 lệnh cho mỗi dòng đơn. */
  nhom: string | null;
  // null = chưa tính được (dòng chưa có bài tính giá) → hiện "—", không phải số 0 thật.
  bu_hao_to: number | null;
  so_to_ke_hoach: number | null;
  so_to_nguyen: number | null;
  so_con: number | null;
  so_kem: number | null;
  so_luot: number | null;
  /** MÃ đơn vị từng chặng dòng giấy của DÒNG NÀY. null = routing không nói tới chặng đó (vd không
   *  có bước xả giấy) ⇒ dùng nhãn mặc định. Tên lấy bằng `tenDonVi(ma)`. */
  don_vi_to: string | null;
  don_vi_to_nguyen: string | null;
  don_vi_tp: string | null;
  don_vi_tay: string | null;
  routing: LsxPreviewRouting[];
  quy_cach: Record<string, unknown> | null;
  thieu: string[];
  /** SL lúc tính giá KHÁC SL đơn (cảnh báo mềm — số dùng thật là của đơn). */
  sl_ptg: number | null;
  lsx_id: number | null;
  lsx_ma: string | null;
}
export interface LsxPreviewOut {
  order_id: number;
  order_no: string;
  customer_name: string | null;
  sale_name: string | null;
  delivery_committed_date: string | null;
  is_rush: boolean;
  production_note: string | null;
  lines: LsxPreviewLine[];
  warnings: string[];
}

/** Khối gia công ngoài (§8) — chỉ có nghĩa khi `loai_buoc = "thue_ngoai"`. */
interface LsxThueNgoaiFields {
  nha_cung_cap: string | null;
  sl_gui: number | null;
  ngay_gui_dk: string | null;
  van_chuyen_ngay: number | null;
  gia_cong_ngay: number | null;
  ngay_nhan_dk: string | null;
  hao_hut_cho_phep: number | null;
  don_gia_gia_cong: number | null;
  yeu_cau_ky_thuat: string | null;
}

/** Sổ THỰC TẾ của bước gia công ngoài + mọi thứ server SUY RA từ nó (không lưu cột).
 *
 * Ghi qua cửa thực thi `api.lsx.giaoNhan`, KHÔNG qua lưu routing — hàng ra cổng lúc lệnh đang
 * chạy, mà lưu routing bị chặn đúng trạng thái đó.
 */
export interface LsxGiaoNhanFields {
  nguoi_giao_id: number | null;
  nguoi_giao_ten: string | null;
  giao_luc: string | null;
  sl_giao_thuc: number | null;
  nguoi_nhan_id: number | null;
  nguoi_nhan_ten: string | null;
  nhan_luc: string | null;
  sl_nhan_thuc: number | null;
  giao_nhan_trang_thai: "chua_gui" | "dang_ngoai" | "da_ve" | null;
  so_hut: number | null;
  hut_vuot_dinh_muc: boolean;
  tien_gia_cong_thuc: number | null;
  qua_han_ngay: number | null;
}

export interface LsxCongDoan extends LsxThueNgoaiFields, LsxGiaoNhanFields {
  id: number; step_key: string; thu_tu: number; cong_doan_id: number | null;
  ten: string; nhom: string | null; loai_buoc: LsxLoaiBuoc; bat_buoc: boolean;
  department_id: number | null; department_ten: string | null;
  may_id: number | null; may_ten: string | null;
  /** Hai CỜ đọc từ danh mục Công đoạn — quyết định bước có hỏi khuôn không; `tooling_type` còn là
   *  chiều lọc thứ hai của ô chọn dao. Năm field `khuon_be_*` là ẢNH CHỤP server ghép sẵn để bày
   *  cho thợ (mã · tên · SỐ KỆ · tình trạng · ngày về) — màn khỏi phải tra danh mục Khuôn. */
  requires_tooling: boolean; tooling_type: string | null;
  khuon_be_id: number | null;
  khuon_be_ma: string | null;
  khuon_be_ten: string | null;
  khuon_be_so_ke: string | null;
  khuon_be_tinh_trang: string | null;
  khuon_be_ngay_ve: string | null;
  // Đơn vị VÀO ≠ RA là chuyện thường ở bế/xén — hệ số quy đổi nối hai đầu.
  so_luong_vao: number; so_luong_ra: number;
  don_vi_vao: string; don_vi_ra: string; he_so_quy_doi: number;
  /** Bước có nằm trên DÒNG GIẤY không (server quyết theo cờ trạm của danh mục Đơn vị — FE không
   *  tự suy từ mã được). `false` ⇒ số lượng KHÔNG tự tính và bù hao không cộng vào số giấy. */
  tren_dong_giay: boolean;
  hao_hut: number; hao_hut_pct: number; ty_le_hao_hut: number; so_luot_chay: number;
  so_nhan_cong: number; so_nhan_cong_tieu_chuan: number; so_nhan_cong_toi_da: number | null;
  /** Mốc thứ ba của định mức nhân lực — khai báo, chưa vào công thức thời lượng. */
  so_nhan_cong_toi_thieu?: number | null;
  // `setup_phut` + `chay_phut` là số DẪN XUẤT (chuẩn bị + tốc độ kế thừa từ máy);
  // `phat_sinh_phut` = ô "Thời gian khác", thứ DUY NHẤT còn gõ được (2026-08-04).
  setup_phut: number; nang_suat: number | null; don_vi_nang_suat: string | null;
  chay_phut: number | null;
  phat_sinh_phut: number;
  // derived: chiếm máy theo tốc độ TB (Gantt đặt lịch) + dải nhanh/chậm nhất của máy.
  chiem_may_phut: number; chiem_may_phut_min: number; chiem_may_phut_max: number;
  tong_phut: number;
  thoi_luong_dien_giai: Record<string, unknown>;
  phu_thuoc_step_keys: string[];
  /** `tu_dong` = dòng máy bung khi chọn công việc khoán (mg 0191) ⇒ lần bung sau thay được.
   *  false = người tự thêm / đã sửa số ⇒ máy chừa ra. */
  vat_tus: { id: number; vat_tu_id: number; vat_tu_ma: string; vat_tu_ten: string;
             don_vi: string; so_luong: number; tu_dong?: boolean }[];
  ghi_chu: string | null;
  // --- Khoán theo đầu việc: phần GHIM (đã chọn) + phần DẪN XUẤT (server tính lúc đọc) ---
  khoan_rate_id: number | null;
  khoan_ten: string | null;
  khoan_don_vi: string | null;
  khoan_don_gia: number | null;
  /** Đầu việc chọn được cho bước (theo tổ + công đoạn) — server đã áp luật "ưu tiên dòng khai riêng". */
  khoan_chon_duoc: LsxDauViecOption[];
  /** Lượng TÍNH SẴN cho mọi vật tư theo bước này — chọn món nào ở drawer là điền số ngay.
   *  Món chưa tính ra được thì KHÔNG có trong mảng ⇒ để ô trống cho người khai, không đoán. */
  vat_tu_goi_y: { vat_tu_id: number; so_luong: number; dien_giai: string | null }[];
  /** Số ĐÚNG RA phải là theo danh mục HIỆN TẠI, chỉ có khi KHÁC số đã lưu. null = không lệch.
   *  Lệnh là ảnh chụp nên server không tự đè — màn gạch số cũ rồi mời bấm Lưu. */
  so_luong_vao_moi: number | null;
  so_luong_ra_moi: number | null;
  khoan_sl: number | null;
  khoan_don_vi_sl: string | null;
  khoan_tien: number | null;
  /** Cách tính hiện nguyên văn để người đọc kiểm bằng mắt: "241 tờ × 86 × 65 = … × 150 đ/m²". */
  khoan_dien_giai: string | null;
  khoan_thieu: string[];
  khoan_ly_do: string | null;
}
export interface LsxCongDoanBody extends Partial<LsxThueNgoaiFields> {
  /** Đầu việc khoán: id để ghim · 0/null = bỏ chọn · KHÔNG gửi field = giữ mặc định của server. */
  piece_rate_id?: number | null;
  step_key?: string; thu_tu?: number; cong_doan_id?: number | null; ten?: string; nhom?: string | null;
  loai_buoc?: LsxLoaiBuoc; bat_buoc?: boolean;
  department_id?: number | null; may_id?: number | null;
  /** Con dao của bước (`khuon_be.id`). null = bỏ gán. */
  khuon_be_id?: number | null;
  so_luong_vao?: number; so_luong_ra?: number;
  don_vi_vao?: string; don_vi_ra?: string; he_so_quy_doi?: number;
  hao_hut?: number; hao_hut_pct?: number; so_luot_chay?: number; so_nhan_cong?: number;
  /** Ba mốc định mức nhân lực — kế thừa từ đầu việc nhưng sửa được tại bước. */
  so_nhan_cong_toi_thieu?: number; so_nhan_cong_tieu_chuan?: number; so_nhan_cong_toi_da?: number;
  setup_phut?: number; nang_suat?: number | null; don_vi_nang_suat?: string | null;
  phat_sinh_phut?: number;
  phu_thuoc_step_keys?: string[];
  vat_tus?: { vat_tu_id: number; so_luong: number }[];
  ghi_chu?: string | null;
}
export interface LsxPhuThuocOption {
  lsx_id: number; lsx_ma: string; nhom: string | null; step_key: string; ten_buoc: string; thu_tu: number;
}
/** Tổng thời gian dẫn cả lệnh — DẪN XUẤT ở server, không lưu cột. */
export interface LsxLeadTime {
  tong_phut: number;
  chiem_may_phut: number;
  chiem_may_phut_min: number; chiem_may_phut_max: number;
  so_ngay: number;              // quy ước 8h/ngày, chưa trừ nghỉ lễ
  ngay_du_kien_xong: string | null;
  ngay_con_lai: number | null;  // tới hạn giao khách; âm = đã trễ
}
/** 1 dòng GỢI Ý của phép tính ngược — chưa ghi DB. */
export interface LsxTinhNguocRow {
  id: number; thu_tu: number; ten: string;
  so_luong_vao: number; so_luong_ra: number;
  don_vi_vao: string; don_vi_ra: string;
}
export interface LsxTinhNguocOut { rows: LsxTinhNguocRow[]; so_to_ke_hoach: number }
/** Bộ mặc định khi ĐỔI bước sang công đoạn khác. KHÔNG có SL vào/ra — số đó thuộc CHUỖI
 *  (bước trước giao bao nhiêu thì bước này nhận bấy nhiêu), không thuộc công đoạn. */
export interface LsxBuocMacDinh {
  cong_doan_id: number; ten: string; nhom: string | null;
  department_id: number | null;
  don_vi_vao: string; don_vi_ra: string; he_so_quy_doi: number;
  setup_phut: number;
}
export interface LsxDauViecOption {
  id: number; ten: string; don_vi: string; don_gia: number;
  /** Ba mức năng suất khai ở định mức đầu việc — TB là số chảy vào công thức, min/max chỉ ra
   *  khoảng nhanh–chậm (null = chưa khai dải). */
  nang_suat_nguoi_gio: number;
  nang_suat_nguoi_gio_min?: number | null; nang_suat_nguoi_gio_max?: number | null;
  /** `so_nguoi_toi_thieu` mới là KHAI BÁO — chưa vào công thức thời lượng. */
  so_nguoi_toi_thieu?: number;
  so_nguoi_tieu_chuan: number; so_nguoi_toi_da: number;
  /** `is_default` GỠ 12/08/2026 (mg 0190): đầu việc điền sẵn nay chỉ suy từ "công đoạn có đúng
   *  MỘT đầu việc", không còn cờ khai ở danh mục. */
  don_vi_nang_suat: string | null;
  /** VẬT TƯ đầu việc này tiêu thụ, ĐÃ tính số cho đúng bước đang mở (nền BOM, mg 0191). Chỉ có khi
   *  đọc lệnh — đường đổi tổ (`dau-viec-options`) không có bước nên trả rỗng. */
  vat_tus?: {
    vat_tu_id: number; ma: string; ten: string; don_vi: string;
    so_luong: number; dien_giai?: string | null;
  }[];
  /** Vật tư khai ở danh mục nhưng KHÔNG quy đổi được sang đơn vị của nó — máy không đoán, chỉ nói
   *  thiếu gì để người kế hoạch tự thêm. */
  canh_bao_vat_tu?: string[];
}
export interface LsxListItem {
  id: number; ma: string; loai: string; ten: string; trang_thai: LsxTrangThai;
  /** Nhãn nhóm của dòng đơn — cho biết lệnh "Bìa" thuộc "Catalogue A4 - 32 trang". */
  nhom: string | null;
  order_id: number; order_no: string | null; customer_name: string | null;
  so_luong_dat: number; don_vi_tinh: string; so_to_ke_hoach: number;
  han_giao_khach: string | null; han_hoan_thanh_sx: string | null;
  is_rush: boolean; to_dau_ten: string | null; so_cong_doan: number;
  /** MÃ đơn vị chặng TỜ IN của lệnh này (server đọc từ routing). Bảng liệt kê nhiều lệnh, mỗi lệnh
   *  có thể đếm bằng đơn vị xưởng tự đặt — nên đơn vị đi theo DÒNG, không nằm ở tiêu đề cột.
   *  Tên lấy bằng `tenDonVi(ma)`; null = lệnh chưa có bước nào trên dòng giấy. */
  don_vi_to: string | null;
}
export interface LsxListOut { items: LsxListItem[]; total: number }
export interface LsxDetail {
  id: number; ma: string; loai: string; lsx_goc_id: number | null; ten: string;
  /** Nhãn nhóm đọc sống từ dòng đơn — luôn đúng hiện tại, khác `quy_cach_json` là ảnh chụp. */
  nhom: string | null;
  trang_thai: LsxTrangThai;
  order_id: number; order_line_id: number; order_no: string | null;
  customer_name: string | null; customer_po_no: string | null; sale_name: string | null;
  quote_version_id: number | null; quote_number: string | null; quote_version_number: number | null;
  phieu_thanh_phan_id: number | null; ptg_id: number | null; ptg_ma: string | null;
  so_luong_dat: number; don_vi_tinh: string;
  so_to_ke_hoach: number; so_to_nguyen: number; so_con: number;
  /** MÃ đơn vị bốn chặng dòng giấy — SERVER chấm (`dong_giay.don_vi_chuoi`), client chỉ tra TÊN.
   *  Đừng suy lại ở FE: bản chép tay thứ hai đã từng cùng sai với bản server ở chặng `tay`.
   *  null = routing không nói tới chặng đó ⇒ hiện mỗi con số, không bịa nhãn. */
  don_vi_to: string | null;
  don_vi_to_nguyen: string | null;
  don_vi_tp: string | null;
  don_vi_tay: string | null;
  ban_giao_at: string | null; han_giao_khach: string | null; han_hoan_thanh_sx: string | null;
  is_rush: boolean;
  quy_cach_json: Record<string, unknown> | null;
  may_id: number | null; may_ten: string | null;
  nguoi_phu_trach_id: number | null; nguoi_phu_trach_ten: string | null;
  ghi_chu: string | null; created_at: string; updated_at: string;
  cong_doans: LsxCongDoan[];
  /** Hai rổ TÁCH BẠCH: `thieu` chặn nút Sẵn sàng; `canh_bao` chỉ tô màu. */
  thieu: string[];
  canh_bao: string[];
  lead_time: LsxLeadTime | null;
  /** Công thợ khoán DỰ KIẾN cả lệnh = Σ bước quy đổi được. Là số SÀN: bước chưa chọn đầu việc
   *  hoặc thiếu số để quy đổi thì không góp vào. */
  khoan_tien_tong: number;
  /** Chừa tách chiều do server tính (`chua_theo_chieu`) — đừng cộng lại ở FE. */
  chua_dai: number;
  chua_rong: number;
  /** Lệnh đang ghép chung tờ với ai. `null` = in riêng. Khi có, THÔNG SỐ TỜ (máy in, giấy, khổ
   *  tờ in, số con) do BÀI quyết — sửa ở màn lệnh không có tác dụng. */
  bai_ghep: LsxBaiGhep | null;
}
export interface LsxBaiGhep {
  id: number; ma: string; trang_thai: string;
  may_id: number | null; may_ten: string | null;
  giay_id: number | null; kho_in_dai: number | null; kho_in_rong: number | null;
  so_con_tren_to: number;
  /** `lsx_step_key → bước chung đang ĐÈ lên nó`. Màn lệnh phải nói được CẢ HAI số ("bài cấp
   *  1.480 tờ · phần lệnh này 987 tờ"), không thì người sửa máy ở đây mà không biết máy thật
   *  nằm ở bài. Không còn `buoc_in_step_key`: bài gộp cả CTP/cán/bế, không riêng bước in. */
  buoc_bi_de: Record<string, {
    gop_step_key: string; ten: string;
    to_ten: string | null; may_ten: string | null;
    so_luong_vao: number; so_luong_ra: number; hao_hut: number;
  }>;
}
export interface LsxUpdateBody {
  ten?: string; so_luong_dat?: number; don_vi_tinh?: string;
  so_to_ke_hoach?: number; so_to_nguyen?: number; so_con?: number;
  han_hoan_thanh_sx?: string | null; is_rush?: boolean;
  may_id?: number | null;
  nguoi_phu_trach_id?: number | null; ghi_chu?: string | null;
  quy_cach?: LsxQuyCachBody;
}
/** THÔNG SỐ (nguyên nhân) kế hoạch sửa được trên lệnh. HỆ QUẢ — số kẽm, số lượt, số mảnh xả,
 *  số tờ — server tính lại từ đúng bộ này; gửi lên cũng bị bỏ. */
export interface LsxQuyCachBody {
  giay_id?: number | null;
  nguon_giay?: string;
  kho_nguyen_dai?: number; kho_nguyen_rong?: number;
  kho_in_dai?: number; kho_in_rong?: number;
  dai_thanh_pham?: number; rong_thanh_pham?: number;
  quy_cach_in?: string;
  muc_a?: string[]; muc_b?: string[];
  so_trang?: number; trang_moi_tay?: number;
  bleed_mm?: number; khe_cat_mm?: number;
  con_auto?: boolean;
}
/** Các số MÁY TỰ TÍNH ứng với bộ thông số đang gõ — chưa lưu. */
export interface LsxQuyCachXemTruoc {
  doi: string[];
  so_con: number; so_kem: number; kem_moi_tay: number; so_manh_xa: number;
  so_to_per_sp: number; so_to_ke_hoach: number; so_to_nguyen: number; so_luot: number;
  so_mau_a: number; so_mau_b: number; so_mau_pha: number;
}
export interface LsxActivity { at: string; actor_name: string | null; action: string; detail: string }

export function connectQuoteEvents(token: string, onEvent: (e: QuoteEvent) => void): () => void {
  let closed = false;
  let controller: AbortController | null = null;
  let current = token;

  async function loop(): Promise<void> {
    while (!closed) {
      controller = new AbortController();
      const ctl = controller;
      // Watchdog: backend gửi event hoặc ": ping" ít nhất mỗi 20s. Im lặng > 50s = kết nối CHẾT
      // NGẦM (nửa-mở qua proxy / zombie uvicorn --reload trên Windows) mà `reader.read()` treo mãi
      // không báo lỗi → abort để rơi vào catch → reconnect. Nhờ vậy SSE TỰ LÀNH, không cần F5.
      let watchdog: ReturnType<typeof setTimeout> | undefined;
      const kick = () => {
        if (watchdog) clearTimeout(watchdog);
        watchdog = setTimeout(() => ctl.abort(), 50_000);
      };
      try {
        kick();
        const resp = await fetch(`${BASE_URL}/api/quotations/events`, {
          headers: { ...authHeader(current), Accept: "text/event-stream" },
          credentials: "include",
          cache: "no-store",
          signal: controller.signal,
        });
        if (resp.status === 401) {
          const fresh = await refreshAccessToken();
          if (fresh) { current = fresh; continue; }  // thử lại ngay với token mới
          break;                                     // session chết → dừng
        }
        if (!resp.ok || !resp.body) throw new Error(`SSE ${resp.status}`);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (!closed) {
          const { value, done } = await reader.read();
          if (done) break;
          kick();  // có byte (event hoặc ping) → gia hạn watchdog: kết nối còn sống
          buf += decoder.decode(value, { stream: true });
          let sep: number;
          while ((sep = buf.indexOf("\n\n")) >= 0) {
            const frame = buf.slice(0, sep);
            buf = buf.slice(sep + 2);
            const data = frame
              .split("\n")
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).trim())
              .join("\n");
            if (!data) continue;  // heartbeat/comment (": ping")
            try { onEvent(JSON.parse(data) as QuoteEvent); } catch { /* bỏ frame hỏng */ }
          }
        }
      } catch {
        /* lỗi mạng/stream/abort-do-watchdog → reconnect sau backoff */
      } finally {
        if (watchdog) clearTimeout(watchdog);
      }
      if (closed) break;
      await new Promise((r) => setTimeout(r, 3000));  // backoff trước khi reconnect
    }
  }

  void loop();
  return () => { closed = true; controller?.abort(); };
}

// --- RBAC admin shapes ------------------------------------------------------

export type Scope = "own" | "department" | "all";

export interface ModuleDef {
  /** Những "việc" ĐÃ XÁC MINH là chết ở màn này (`["update","delete",…]`) — ma trận tắt sẵn +
   *  khoá + hover cảnh báo đúng mấy ô đó. Mặc định coi mọi ô còn sống: thà để thừa một ô vô hại
   *  còn hơn khoá nhầm một ô đang dùng. */
  viec_chet?: string[];
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
  /** Ảnh của trưởng phòng — phải do server trả, FE chỉ biết ảnh của chính người đang đăng nhập. */
  head_avatar_url?: string | null;
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
  /** Bộ nguyên tắc lương của phòng (Pha 1). */
  salary_mechanism?: SalaryMechanism;
  probation_ratio?: number;
  has_piece_work?: boolean;
  /** Đánh dấu khối SẢN XUẤT (spec §13.1). Effective tính theo cây ở FE (self hoặc tổ tiên tick). */
  la_san_xuat?: boolean;
  /** Đánh dấu khối KINH DOANH (mg 0181) — cùng luật kế thừa cây con. Nền cho danh sách
   *  "NV phụ trách" ở màn Khách hàng; chưa tick phòng nào thì backend lùi về quy tắc theo quyền. */
  la_kinh_doanh?: boolean;
}

/** Cơ chế ra mức lương của một phòng ban (Pha 1). */
export type SalaryMechanism =
  | "cung"
  | "bac_tho"
  | "tham_nien"
  | "tham_nien_gioi_tinh";

export interface DepartmentSalaryPolicy {
  salary_mechanism: SalaryMechanism;
  probation_ratio: number;
  has_piece_work?: boolean;
}

/** A tier in the org-level catalog (spec-06 / PBI-4009). */
export interface UnitLevel {
  id: number;
  name: string;
  rank: number;
  head_title: string;
}

/** A staff member of a department (PBI-4001 detail panel). */
/** Nhân sự của một phòng — một dòng = một HỒ SƠ (Đ2), kèm tài khoản nếu có.
 *  `user_id`/`username` null = chưa có tài khoản đăng nhập (công nhân xưởng): vẫn thuộc
 *  phòng và vẫn chuyển phòng được, chỉ là không gán vai trò được. */
export interface DepartmentMember {
  employee_id: number;
  code?: string | null;
  name: string;
  position?: string | null;
  status: string;
  user_id?: number | null;
  username?: string | null;
  role_name?: string | null;
  is_active?: boolean | null;
  is_head: boolean;
  /** Ảnh lấy từ `users.avatar_url`. Null = chưa có tài khoản, hoặc có mà chưa tải ảnh. */
  avatar_url?: string | null;
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
  avatar_url?: string | null;
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
  /** nhan_su — SỬA được nhóm field lương/BHXH của hồ sơ (STK · số sổ BHXH · MST · nhóm lương ·
   *  `pit_mode`). Thiếu quyền: backend LẶNG LẼ bỏ các field đó khỏi bản ghi, KHÔNG 403 ⇒ UI
   *  phải đọc lại kết quả rồi mới dám báo "đã đổi". */
  can_edit_salary: boolean;
  can_adjust: boolean;
  /** A2: don_hang_ban — GĐ duyệt "đơn đặc thù" (chỉ Giám đốc). */
  can_approve_exception: boolean;
  /** khach_hang — thiết lập điều khoản tín dụng khách (hạn mức + điều khoản thanh toán). */
  can_set_credit_terms: boolean;
  can_record_deposit: boolean;
  can_assign_work: boolean;
  can_record_output: boolean;
  can_handover: boolean;
  /** kho — quyền chi tiết module Kho (spec-kho-de-nghi §9.1) + ghi sổ (SoD). */
  can_request: boolean;
  can_view_stock: boolean;
  can_view_cost: boolean;
  can_view_log: boolean;
  can_set_threshold: boolean;
  can_post: boolean;
  /** kho — KHÓA KỲ (chốt sổ) + Báo cáo kho kế toán + export MISA. */
  can_close_book: boolean;
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

export interface RoleTemplate {
  key: string;
  label: string;
  mo_ta: string;
  /** Ma trận ĐẦY ĐỦ (mọi module) — áp mẫu là THAY SẠCH, không trộn với quyền cũ của vai. */
  permissions: PermissionRow[];
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
  can_edit_salary: boolean;
  can_adjust: boolean;
  can_approve_exception: boolean;
  can_set_credit_terms: boolean;
  can_record_deposit: boolean;
  can_assign_work: boolean;
  can_record_output: boolean;
  can_handover: boolean;
  /** kho — quyền chi tiết module Kho (spec-kho-de-nghi §9.1) + ghi sổ (SoD). */
  can_request: boolean;
  can_view_stock: boolean;
  can_view_cost: boolean;
  can_view_log: boolean;
  can_set_threshold: boolean;
  can_post: boolean;
  /** kho — KHÓA KỲ (chốt sổ) + Báo cáo kho kế toán + export MISA. */
  can_close_book: boolean;
}

// --- Khách hàng (CRM), spec-06 v2 -------------------------------------------

/** Loại KH (redesign spec-06 v2): cá nhân (ẩn MST) / công ty (hiện MST). */
export type CustomerKind = "ca_nhan" | "cong_ty";

export interface CustomerRow {
  id: number;
  code: string;
  name: string;
  customer_kind: CustomerKind;
  tax_code: string | null;
  phone: string | null;
  email?: string | null;
  address?: string | null;
  contact_name?: string | null;
  credit_limit: number;
  sale_user_id: number | null;
  sale_name: string | null;
  created_at?: string | null;
  /** Công nợ chỉ-đọc: null + no_ar_module=true until Công nợ (SEAM-16) is built. */
  receivable: number | null;
  no_ar_module: boolean;
  /** Derived from real orders (số THẬT; redesign spec-06 v2 bỏ tier). */
  revenue_12m: number;
  orders_total: number;
  last_order_at: string | null;
  /** Chính sách tài chính (ai cũng xem; sửa qua /financial, gate set_credit_terms). */
  /** Số ngày công nợ tối đa (net terms, kể từ ngày xuất HĐ). null = chưa đặt hạn ngày. */
  payment_term_days?: number | null;
  discount_min_pct?: number | null;
  discount_max_pct?: number | null;
  margin_min_pct?: number | null;
  margin_max_pct?: number | null;
  /** Nhãn thủ công (#7) — sales gán tay. */
  tags?: string[];
}

/** List header KPI strip — rolled up over the whole scoped book from real orders. */
export interface CustomerKpis {
  total_customers: number;
  new_this_month: number;
  avg_order_value: number;
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
/** 1 dòng "Thông số in thường đặt" — gom từ phiếu tính giá gắn báo giá của khách. */
export interface PrintSpec {
  key: "giay" | "mau" | "gia_cong" | "kho" | string;
  label: string;
  value: string;
  pct: number;
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
  months: MonthPoint[];
  product_mix: ProductSlice[];
  heatmap: HeatCell[];
  has_data: boolean;
  print_specs: PrintSpec[];
  print_specs_phieu: number;
  receivable: ReceivableCard;
}
export interface OrderLineBrief {
  description: string;
  line_total: number;
}
export interface OrderHistoryRow {
  id: number;
  order_no: string;
  status: string;
  order_kind: string;
  summary: string;
  /** Từng dòng kèm TIỀN THẬT. Khối "Sản phẩm mua nhiều nhất" cộng theo đây — trước 16/08/2026
   *  chỉ có `summary` (chuỗi nối) nên nó phải chia đều tổng đơn cho số dấu phẩy, xếp sai hạng.
   *  Đơn cũ có thể trả mảng rỗng; `gopTienTheoSanPham` lùi về đếm số đơn, KHÔNG bịa tiền. */
  lines: OrderLineBrief[];
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
  repeat_freq: string;        // none | day | week | month (lịch lặp)
  repeat_interval: number;    // mỗi N đơn vị
  repeat_until: string | null;
  series_id: number | null;
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

/** 1 lần hẹn trên LỊCH (redesign-lich-hen-cham-soc); task_id=null ⇒ lần ẢO (tương lai chưa materialize). */
export interface CareOccurrence {
  task_id: number | null;
  series_id: number | null;   // id hẹn-đầu-chuỗi để thao tác
  note: string;
  due_date: string;
  status: "open" | "done" | "cancelled";
  is_virtual: boolean;
  repeat_freq: string;
  remind_level: number;
  overdue_days: number;
  assignee_user_id: number | null;
  assignee_name: string | null;
  is_event: boolean;    // true = tương tác ĐÃ GHI (CareEvent) hiện trên lịch
  kind: string | null;  // hình thức khi is_event (goi_dien/nhan_tin/…)
}

export interface CareCalendarOut {
  items: CareOccurrence[];
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
  /** Vai trò + phòng, để hộp chọn hiện 2 tầng: "Lê Sale Một" / "NV Sales · Kinh doanh". */
  vai_tro?: string | null;
  phong_ban?: string | null;
  /** `false` = KHÔNG đủ tư cách nhận khách mới (ngoài khối Kinh doanh / tài khoản đã khoá) nhưng
   *  vẫn đang giữ khách trong tầm nhìn ⇒ hộp LỌC hiện, ô GÁN ẩn. */
  co_the_gan?: boolean;
  /** Số khách người này đang phụ trách trong tầm nhìn của người xem. */
  so_kh?: number;
}

/** Form Thêm/Sửa — THÔNG TIN ĐỊNH DANH (redesign spec-06 v2). Không đụng tài chính. */
export interface CustomerInput {
  name: string;
  customer_kind: CustomerKind;
  tax_code: string | null;
  phone?: string | null;
  email: string | null;
  address: string | null;
  contact_name?: string | null;
  sale_user_id: number | null;
}

/** Chính sách tài chính — endpoint /financial (gate set_credit_terms). Ghi đầy đủ nhóm. */
export interface CustomerFinancialInput {
  credit_limit: number;
  /** Số ngày công nợ tối đa (net terms, kể từ ngày xuất HĐ). null = chưa đặt hạn ngày. */
  payment_term_days?: number | null;
  discount_min_pct?: number | null;
  discount_max_pct?: number | null;
  margin_min_pct?: number | null;
  margin_max_pct?: number | null;
}

/** Một ghi chú tự do của team về khách (tab Ghi chú). */
export interface CustomerNote {
  id: number;
  body: string;
  pinned: boolean;
  created_at: string;
  updated_at?: string | null;
  /** Đã sửa nội dung (ghim không tính). */
  edited: boolean;
  author_name?: string | null;
}

export interface CustomerListParams {
  q?: string;
  sale?: number | null;
  /** Lọc "Chưa gán ai" — khách chưa có NV phụ trách. Đè lên `sale` khi bật. */
  chua_gan?: boolean;
  followup?: boolean;
  tag?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

export interface EnumOption {
  value: string;
  label: string;
}

// Phiếu tính giá 4 nhóm — snake_case y hệt JSON trả về. (Nguồn cũ `estimate_to_phieu` đã xoá ở
// Đợt 5; hai type này giờ do engine đang chạy nuôi — xem PhieuTinhGiaDetailView.)
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
/** Số [Hiện] read-only của 1 thành phần (từ result.meta.components) — soi số cho người lập phiếu. */
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
  to_dau_vao: number;
  to_sau_in: number;
  bu_hao_auto?: number; // Σ bù hao công đoạn — engine đi NGƯỢC từ cuối chuỗi lên
  bu_hao_chi_tiet?: BuHaoBuoc[]; // phân rã: bước nào ăn bao nhiêu tờ (thứ tự xuôi)
  so_trang?: number; // số trang nội dung của 1 sản phẩm (người dùng khai)
  trang_moi_tay?: number; // số trang mỗi tay gấp
  so_to_per_sp?: number; // số bài in — DẪN XUẤT: so_trang / trang_moi_tay
  to_ra_cuoi?: number; // tờ ra khỏi bước cuối chuỗi
  so_tp_ra?: number; // thành phẩm thật sự có = to_ra_cuoi × con/tờ
  /** Σ phí khuôn của sản phẩm này — khoản MỘT LẦN, nhưng ĐÃ NẰM TRONG `gia_von_tp` (và do đó
   *  trong `gia_von_don`). Số này chỉ để BÀY RA cho người đọc biết trong giá vốn có bao nhiêu
   *  tiền dao — ĐỪNG cộng nó vào tổng lần nữa. */
  phi_khuon?: number;
  /** Phân rã theo bước: bước nào con dao nào bao nhiêu tiền. */
  phi_khuon_dong?: { ten: string; loai: string | null; thanh_tien: number }[];
  bu_hao_tay?: number; // ô "+ Bù thêm" đã bỏ → engine luôn trả 0
  hao_tay?: number; // ô "− Hao" đã bỏ → engine luôn trả 0
}
/** 1 bước trong chuỗi ngược: số tờ vào — ra — hao của chính bước đó. */
export interface BuHaoBuoc {
  /** KHÓA ghép với dòng tiền `groups.cong_doan[].buoc_idx` — cùng là chỉ số bước trong chuỗi.
   *  Optional vì backend đời cũ (chưa restart) không gửi; thiếu thì panel chỉ mất phần tiền. */
  buoc_idx?: number;
  ten: string;
  nhom?: string | null; // prepress|print|finishing — UI neo "Tờ sau in" vào bước in
  dv_vao?: LsxDonVi | null; // đơn vị VÀO / RA của bước — khác nhau = bước đổi đơn vị
  dv_ra?: LsxDonVi | null;
  vao: number;
  ra: number;
  ra_quy?: number; // `ra` quy về ĐƠN VỊ VÀO — ra_quy + hao = vao
  he_so?: number; // hệ số quy đổi đã dùng (1 nếu bước không đổi đơn vị)
  hao: number; // đo bằng ĐƠN VỊ VÀO
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

/** Bình bài live (POST /api/tinh-gia/binh-bai) — mm; chua_mm = chừa gộp (cm) × 10. */
export interface BinhBaiIn {
  kho_in_dai: number;
  kho_in_rong: number;
  dai_thanh_pham: number;
  rong_thanh_pham: number;
  /** Chừa GỘP — trừ đều mỗi chiều. Dùng khi KHÔNG tách chiều (đường cũ). */
  chua_mm?: number;
  /** Chừa TÁCH CHIỀU (ưu tiên hơn `chua_mm`): dài ← nhíp giấy + đuôi; rộng ← lề hông ×2. */
  chua_dai_mm?: number;
  chua_rong_mm?: number;
  /** Hoặc gửi CHỪA THÔ — server tự tách chiều (`chua_theo_chieu`): `chua_nhip` là ô đè của phiếu,
   *  ba cái sau là thông số danh mục MÁY. Nơi gọi đừng tự cộng: cộng tay ở màn thứ hai chính là
   *  chỗ đẻ ra sơ đồ 105 con trong khi phiếu ra 99. */
  chua_nhip?: number;
  nhip_giay_mm?: number;
  le_hong_mm?: number;
  duoi_thang_mau_mm?: number;
  bleed_mm?: number;
  khe_cat_mm?: number;
}
export interface BinhBaiOut {
  con: number;
  cols: number;
  rows: number;
  rotated: boolean;
  usable_dai: number;
  usable_rong: number;
  /** Chừa engine ĐÃ trừ, theo từng chiều — FE vẽ sơ đồ theo số này, đừng tự tính lại. */
  chua_dai: number;
  chua_rong: number;
  /** Kích thước 1 con ĐÃ cộng bleed (= thành phẩm + 2×bleed). */
  piece_dai: number;
  piece_rong: number;
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
  /** Phí làm khuôn của CHÍNH bước này — khoản MỘT LẦN (không nhân SL), nhưng engine CÓ cộng vào
   *  `gia_von_tp`, nên khi chia ra đ/sản phẩm thì đơn nhỏ gánh nặng hơn đơn lớn. Đó là đánh đổi đã
   *  chọn 15/08/2026 để báo giá chỉ còn MỘT dòng — đừng "sửa" bằng cách rút nó ra khỏi giá vốn.
   *  0 = dùng lại dao cũ. Chỉ có nghĩa ở bước mà công đoạn nguồn cần dao lưu kho (bế / ép nhũ). */
  phi_khuon: number;
}

/** 1 thành phần giấy (paper component): giấy + kỹ thuật in + màu + list gia công. */
export interface ThanhPhanOut {
  id: number;
  phieu_id: number;
  thu_tu: number;
  loai_thanh_phan: string;
  ten: string;
  dai_thanh_pham: number; // ③ khổ thành phẩm (mm)
  rong_thanh_pham: number; // ③
  /** Nhãn gộp dòng khi báo giá (ruột + bìa 1 cuốn gõ giống nhau). Không vào công thức giá. */
  nhom_bao_gia: string | null;
  so_to_per_sp: number; // DẪN XUẤT (server ghi) = so_trang / trang_moi_tay
  so_trang: number; // số trang nội dung của 1 sản phẩm (tờ rời = 1)
  trang_moi_tay: number; // số trang mỗi tay gấp (tờ rời = 1)
  so_luong: number; // SL đặt của sản phẩm này (0 = lấy SL mặc định phiếu)
  don_vi_tinh: string; // ĐVT sản phẩm (text tự do, mặc định "cái") → chảy sang Báo giá
  loai_san_pham_id: number | null; // loại SP của sản phẩm này
  // Giấy in
  giay_id: number | null;
  kho_nguyen: string | null; // ① nhãn hiển thị
  kho_nguyen_dai: number; // ① khổ giấy nguyên dài (mm) — đè danh mục khi > 0
  kho_nguyen_rong: number; // ①
  don_gia_giay: number;
  don_gia_don_vi: string; // "to" | "tan"
  nguon_giay: string; // "cong_ty" | "khach"
  /** Đè nhíp giấy của MÁY (0 = theo danh mục máy). Lề hông · đuôi · xén · cả gáy đã bỏ khỏi
   *  phiếu — chừa tờ in khai một lần ở danh mục Máy. */
  chua_nhip: number;
  /** Tràn lề MỖI CẠNH con (0 = không tràn lề) — con để bình = thành phẩm + 2×bleed. */
  bleed_mm: number;
  /** Khe giữa 2 con kề nhau (0 = bình sát, cắt chung nhát). n con chỉ có n−1 khe. */
  khe_cat_mm: number;
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
  /** TẬP mã mực mỗi mặt — nguồn sự thật của số kẽm. `C`/`M`/`Y`/`K` là process, mã khác là pha.
   *  Phải là tập chứ không phải số: tự trở/trở nhíp chung một bộ bản nên kẽm = `|A ∪ B|`. */
  muc_a: string[];
  muc_b: string[];
  /** DẪN XUẤT của hai tập trên, server chốt: process mỗi mặt + số mực pha phân biệt cả hai mặt. */
  so_mau_a: number;
  so_mau_b: number;
  so_mau_pha: number;
  ghi_chu_ky_thuat: string | null; // note KỸ THUẬT/SX theo sản phẩm → drawer lệnh
  gia_von_tp: number;
  thanh_phams: ThanhPhamOut[];
  vat_tus: VatTuLineOut[];
}

/** 1 dòng vật tư in ấn thêm (mực/màng/keo…) → Nguyên vật liệu. */
export interface VatTuLineOut {
  id: number;
  thanh_phan_id: number;
  thu_tu: number;
  vat_tu_id: number | null;
  ten: string;
  don_gia: number;
  so_luong: number;
  ghi_chu: string | null;
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

/** 1 dòng nhật ký hoạt động của phiếu tính giá — ai làm gì · khi nào. */
export interface PtgActivity {
  action: string;
  actor_name: string | null;
  detail: string;
  at: string;
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
  phi_khuon?: number;
}
/** Input 1 thành phần — mọi field optional + list gia công. */
export interface ThanhPhanIn {
  loai_thanh_phan?: string;
  ten?: string;
  dai_thanh_pham?: number;
  rong_thanh_pham?: number;
  nhom_bao_gia?: string | null;
  so_trang?: number; // số trang nội dung (số bài in do server dẫn xuất, không gửi)
  trang_moi_tay?: number;
  so_luong?: number; // SL đặt của sản phẩm này (0 = SL mặc định phiếu)
  don_vi_tinh?: string | null; // ĐVT sản phẩm (text tự do)
  loai_san_pham_id?: number | null; // loại SP của sản phẩm này
  giay_id?: number | null;
  kho_nguyen?: string | null;
  kho_nguyen_dai?: number;
  kho_nguyen_rong?: number;
  don_gia_giay?: number;
  don_gia_don_vi?: string;
  nguon_giay?: string;
  chua_nhip?: number;
  bleed_mm?: number;
  khe_cat_mm?: number;
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
  muc_a?: string[];
  muc_b?: string[];
  // Ba số này server tính lại từ tập mực rồi ghi đè — gửi lên chỉ để phiếu cũ chưa khai mực
  // không mất số. Đừng dựa vào chúng để tính gì ở client.
  so_mau_a?: number;
  so_mau_b?: number;
  so_mau_pha?: number;
  ghi_chu_ky_thuat?: string | null; // note KỸ THUẬT/SX theo sản phẩm → drawer lệnh
  thanh_phams?: ThanhPhamIn[];
  vat_tus?: VatTuLineIn[];
}
/** Input 1 dòng vật tư thêm — optional (BE kéo công thức + giá từ danh mục). */
export interface VatTuLineIn {
  vat_tu_id?: number | null;
  ten?: string;
  don_gia?: number;
  so_luong?: number;
  ghi_chu?: string | null;
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
  approved: number;
  sent: number;
  accepted: number;
  rejected: number;
  expired: number;
  converted_to_order: number;
  cancelled: number;
  need_action: number;
}

/** 1 dòng nhật ký tương tác của báo giá (feed Hoạt động) — ai làm gì, khi nào. */
export interface QuotationActivity {
  action: string;
  actor_name: string | null;
  detail: string;
  at: string;
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
  total_cost?: number | null;   // giá vốn khóa (so sánh phiên bản)
  subtotal?: number | null;     // giá bán chưa VAT
  discount?: number | null;     // chiết khấu
  created_at: string;
  change_reason?: string | null;
}

export interface QuoteItemDetail {
  id: number;
  line_no: number;
  product_type: string;
  product_name: string;
  product_spec_text: string | null;
  /** Diễn giải quy cách in dưới tên SP — mỗi dòng = 1 gạch đầu dòng. Bung từ tính giá, sửa được. */
  dien_giai: string | null;
  /** Nhãn nhóm gộp KHI IN: các dòng cùng nhãn (ruột + bìa 1 cuốn) in ra khách thành 1 dòng. */
  nhom: string | null;
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
  /** Khách chốt một phần: true = khách ưng (kéo lên đơn), false = không lấy. Chỉ có nghĩa khi báo giá đã accepted. */
  accepted: boolean;
}

/** Tài liệu đính kèm NỘI BỘ của báo giá (file khách gửi / mẫu thiết kế / ảnh tham khảo). */
export interface QuoteAttachment {
  id: number;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_at: string;
}

export interface QuotationDetail {
  id: number;
  code: string;
  version: number;
  customer_id: number | null;
  customer: CustomerDisplay | null;
  phieu_tinh_gia_id: number | null;
  phieu_tinh_gia_ma: string | null;
  valid_until: string | null;
  status: string;
  cancel_reason: string | null;
  /** Điều khoản in ra phiếu — mỗi dòng = 1 điều khoản (bản in tự đánh số). */
  terms_text: string | null;
  /** ĐC giao: chỉ-đọc trên báo giá (auto-fill từ hồ sơ khách, không in). */
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
  // Đơn hàng bán đã lập từ báo giá này (đơn hủy không tính) → FE ẩn "Tạo đơn", hiện "Xem đơn hàng".
  order_id?: number | null;
  order_no?: string | null;
}

export interface QuotationInput {
  customer_id: number | null;
  /** BG-1: 1 Phiếu tính giá (PTG) → 1 báo giá. Nguồn DUY NHẤT (đường Estimate đã gỡ ở Đợt 5). */
  phieu_tinh_gia_id?: number | null;
  /** Gói biên áp chung khi tạo (per dòng chỉnh sau). */
  margin_percent?: number | null;
  valid_until: string | null;
  /** Điều khoản in ra phiếu (mỗi dòng = 1 điều khoản); bỏ trống → backend điền bộ mặc định. */
  terms_text?: string | null;
  // Ghi chú đối ngoại/nội bộ đã BỎ khỏi UI — optional để tương thích payload cũ.
  customer_note?: string | null;
  internal_note?: string | null;
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
  /** Diễn giải quy cách in dưới tên SP. BE dump đủ field → không gửi = XOÁ; luôn echo giá trị cũ. */
  dien_giai?: string | null;
}

export interface QuotationUpdateInput {
  customer_id: number | null;
  valid_until: string | null;
  /** Điều khoản in ra phiếu (mỗi dòng = 1 điều khoản); bỏ trống → backend điền bộ mặc định. */
  terms_text?: string | null;
  // Ghi chú đối ngoại/nội bộ đã BỎ khỏi UI — vẫn optional để tương thích payload cũ.
  customer_note?: string | null;
  internal_note?: string | null;
  items: QuoteItemUpdateInput[] | null;
}

export interface QuotationEnumsOut {
  statuses: EnumOption[];
}

export interface QuotationListParams {
  q?: string;
  status?: string | null;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Nhân sự · Hồ sơ nhân sự (nhan_su), lát #1 -----------------------------

export type EmployeeStatus = "probation" | "active" | "on_leave" | "suspended" | "resigned";

/** Cách tính thuế TNCN của MỘT người (chốt chủ 27/07/2026 — `employees.pit_mode`).
 *  Ba trạng thái nên dùng chuỗi, không nhồi 2 cờ Boolean (nhồi là mở chỗ để lệch). */
export type PitMode = "luy_tien" | "khau_tru_10" | "cam_ket_08";
/** Nhãn + giải thích ngắn cho dropdown "Cách tính thuế TNCN". `warn` = câu cảnh báo hiện
 *  trong ConfirmDialog TRƯỚC khi lưu (đổi nhánh là đổi TIỀN THUẾ của người đó). */
export const PIT_MODE_META: Record<PitMode, { label: string; hint: string }> = {
  luy_tien: {
    label: "Luỹ tiến từng phần",
    hint: "HĐ từ 3 tháng trở lên: tính theo bảng thuế luỹ tiến + giảm trừ gia cảnh.",
  },
  khau_tru_10: {
    label: "Khấu trừ 10% tại nguồn",
    hint: "HĐ dưới 3 tháng / thời vụ / thực tập: KHÔNG áp giảm trừ gia cảnh.",
  },
  cam_ket_08: {
    label: "Có cam kết 08/CK-TNCN",
    hint: "Cả năm chưa tới ngưỡng chịu thuế ⇒ không khấu trừ thuế TNCN.",
  },
};
export const PIT_MODE_ORDER: PitMode[] = ["luy_tien", "khau_tru_10", "cam_ket_08"];

/** Nhóm lương (`employees.payroll_group`) — trục tra bảng thang bậc (`salary_rate_rules`).
 *  KHÔNG quyết định mức lương của người: mức lương khai ở Lương → Lương nhân viên, và khoản
 *  thu nhập gán theo TỪNG NGƯỜI (không có mức mặc định theo nhóm — chốt chủ 27/07/2026). */
export const PAYROLL_GROUPS: { key: string; label: string }[] = [
  { key: "van_phong", label: "Khối văn phòng" },
  { key: "to_in", label: "Tổ In (theo bậc thợ)" },
  { key: "san_xuat", label: "Tổ sản xuất (dán · bồi · bế · thành phẩm…)" },
];
/** Nhóm lạ (dữ liệu cũ / nhóm tự khai) vẫn phải đọc được — không nuốt thành "—". */
export function payrollGroupLabel(key: string | null | undefined): string {
  if (!key) return "— chưa gán —";
  return PAYROLL_GROUPS.find((g) => g.key === key)?.label ?? key;
}

export interface EmployeeRow {
  id: number;
  code: string;
  full_name: string;
  department_id: number | null;
  department_name: string | null;
  position: string | null;
  /** Bậc tay nghề kiểu CŨ (chữ tự gõ). Chỉ còn là đường ĐỌC dữ liệu cũ — hồ sơ mới khai qua
   *  `job_grade_id`; đổi bậc thì đi qua transition chứ không ghi thẳng field này nữa. */
  job_grade: string | null;
  /** Bậc tay nghề theo DANH MỤC (`job_grades`) — nguồn sự thật hiện tại. */
  job_grade_id: number | null;
  job_grade_name: string | null;
  status: string;
  hire_date: string | null;
  probation_end_date: string | null;
  user_id: number | null;
  account_username: string | null;
  role_name: string | null;
  photo_url: string | null;
  default_shift_id: number | null;
  created_at: string | null;
}

export interface EmployeeShiftAssignment {
  id: number;
  employee_id: number;
  shift_id: number | null;
  effective_from: string;
  effective_to: string | null;
  is_current: boolean;
  created_at: string;
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
  /** Cách tính thuế TNCN. `null` = người xem KHÔNG có `nhan_su:view_salary` (backend che
   *  cùng nhóm field lương/BHXH) — KHÔNG phải "chưa khai", đừng gửi lại null (422). */
  pit_mode: PitMode | null;
  bank_account: string | null;
  bank_name: string | null;
  default_shift_id: number | null;
  payroll_group: string | null;
  pay_grade_key: string | null;
  resign_date: string | null;
  resign_reason: string | null;
  note: string | null;
  /** Thâm niên đã có TRƯỚC khi vào làm (tháng) — cộng với thời gian từ `hire_date` mới ra
   *  thâm niên tổng. Bỏ vế này là tính hụt với người chuyển từ nơi khác sang. */
  prior_seniority_months?: number;
  /** Trưởng bộ phận. CHỈ `/api/employees/me` điền (màn HCNS để null — tránh N+1). */
  department_head_name?: string | null;
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

/** Một bậc tay nghề trong danh mục (`job_grades`). Bậc chỉ để KHAI — không mang tiền, không
 *  hệ số; `seq` nhỏ = bậc cao (Bậc 1 cao nhất). */
export interface JobGrade {
  id: number;
  code: string;
  name: string;
  seq: number;
  is_active: boolean;
  note: string | null;
}

export interface EmployeeMeta {
  /** `la_san_xuat` là cờ HIỆU LỰC — backend đã leo cây cha-con, FE không phải tự suy. */
  departments: { id: number; name: string; la_san_xuat: boolean }[];
  unlinked_users: { id: number; username: string; name: string }[];
  /** Vai trò để gán cho tài khoản. Role thuộc ĐÚNG 1 phòng ban → lọc theo phòng của hồ sơ. */
  roles: { id: number; name: string; department_id: number }[];
}

export interface EmployeeAccountInput {
  username: string;
  password: string;
  name?: string | null;
  role_id?: number | null;
}

export interface EmployeeInitialSalaryInput {
  effective_from?: string | null;
  /** Lương cơ bản (đóng BH) — mức đóng BHXH/BHYT/BHTN bám số này. */
  luong_vi_tri: number;
  luong_trach_nhiem?: number;
  /** "Lương trả 1 lần" (đợt 1) — mức điền sẵn khi lập phiếu thanh toán lương đợt 1. */
  luong_dot_1?: number;
  allowance?: number;
  phu_cap_ca?: number;
  phu_cap_tham_nien?: number;
  chuyen_can?: number;
  /** BH đóng ở nơi khác → công ty chỉ đóng TNLĐ-BNN (không trừ BHXH/BHYT/BHTN của NV). */
  insurance_elsewhere?: boolean;
  /** Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn. */
  union_member?: boolean;
  /** % hoa hồng của NV kinh doanh — PHÂN SỐ (0.05 = 5%), backend chặn `le=1`. CHỈ ĐỂ KHAI:
   *  engine lương KHÔNG tự cộng số này vào bảng lương. */
  commission_pct?: number;
  note?: string | null;
}

export interface EmployeeInput {
  full_name: string;
  department_id: number | null;
  position?: string | null;
  /** Bậc tay nghề — CHỈ gửi được lúc TẠO hồ sơ. `PUT /api/employees/{id}` cố tình bỏ qua field
   *  này; đổi bậc sau đó phải đi qua `transition` để còn sinh mốc quá trình công tác. */
  job_grade_id?: number | null;
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
  /** Cách tính thuế TNCN — chỉ ghi được khi actor có `nhan_su:edit_salary`; thiếu quyền thì
   *  backend BỎ QUA field này (không 403). Gửi null = 422 (schema có pattern). */
  pit_mode?: PitMode;
  bank_account?: string | null;
  bank_name?: string | null;
  default_shift_id?: number | null;
  payroll_group?: string | null;
  pay_grade_key?: string | null;
  note?: string | null;
  /** Thâm niên đã có TRƯỚC khi vào làm (tháng) — chỉ gửi lúc TẠO hồ sơ. */
  prior_seniority_months?: number;
  account?: EmployeeAccountInput | null;
  initial_salary?: EmployeeInitialSalaryInput | null;
}

export interface EmployeeTransitionInput {
  kind: string;
  effective_date?: string | null;
  note?: string | null;
  new_department_id?: number | null;
  new_job_grade?: string | null;
  /** Bậc tay nghề mới theo danh mục. ⚠ Với `kind: "transfer"` backend XOÁ bậc khi field này
   *  vắng mặt (bậc tổ cũ không mang sang tổ mới) — muốn giữ thì phải gửi id. */
  new_job_grade_id?: number | null;
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

/** Số ký tự tối đa của các ô hồ sơ NV được ĐỀ NGHỊ đổi — khớp `String(n)` trong
 *  `backend/app/models/employee.py`. Chỉ để chặn sớm + cảnh báo tại chỗ; BE vẫn là cổng thật
 *  (đo lại đúng độ dài cột khi gửi VÀ khi duyệt). Thiếu bảng này thì người gõ 44 ký tự vào ô
 *  30 ký tự vẫn gửi được, và người DUYỆT mới là người lãnh lỗi. */
export const EMPLOYEE_FIELD_MAXLEN: Record<string, number> = {
  full_name: 255,
  national_id: 20,
  national_id_place: 255,
  permanent_address: 500,
  bank_account: 30,
  bank_name: 100,
};

// Yêu cầu cập nhật hồ sơ (NV đề nghị → HCNS duyệt).
export interface UpdateRequest {
  id: number;
  employee_id: number;
  employee_name: string | null;
  changes: Record<string, string | number | null>;
  /** Giá trị hồ sơ ĐANG mang của đúng các field trong `changes` — BE điền cho hàng đợi duyệt
   *  của HCNS (rỗng ở các endpoint "của tôi": màn đó đã cầm sẵn hồ sơ người xem). */
  current?: Record<string, string | number | null>;
  reason: string | null;
  /** pending | approved | rejected | cancelled (`cancelled` = NV tự rút lại). */
  status: string;
  decision_note: string | null;
  /** Lúc HCNS quyết — hoặc lúc chính NV rút lại đề nghị. */
  decided_at: string | null;
  decided_by_name: string | null;
  created_at: string;
}
export interface UpdateRequestInput {
  changes: Record<string, string | number | null>;
  reason?: string | null;
}
/** Một TRANG đề nghị của chính NV. `dem` đếm trên TOÀN BỘ hồ sơ (không phải trang đang xem) —
 *  badge "N chờ duyệt" và số trên pill lọc phải đọc `dem`, đừng đếm lại từ `items`. */
export interface MyUpdateRequestsPage {
  items: UpdateRequest[];
  total: number;
  page: number;
  size: number;
  dem: Record<string, number>;
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
  ot_mode?: boolean;           // lượt vừa chấm thuộc phiên TĂNG CA
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
  ot_mode?: boolean;           // lượt kế tiếp thuộc phiên TĂNG CA
  message: string;
}

export interface MyShift {
  id: number;
  name: string;
  start_time: string;   // "HH:MM"
  end_time: string;
  is_overnight: boolean;
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
  ot_mode?: boolean;             // lượt kế tiếp thuộc phiên TĂNG CA → đổi nhãn nút
  can_check: boolean;
  check_block_reason: string | null;
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
  /** Hệ số ca đêm (1.3 = +30%) cho giờ rơi 22h–06h trong ca — chỉ ca qua đêm. */
  night_multiplier: number;
  grace_minutes: number;
  /** Phụ cấp cơm khai theo ca (đ). Đợt 1: lưu/phơi; engine chưa dùng. */
  meal_allowance: number;
  /** Phụ cấp ca khai theo ca (đ), áp ca ngày/đêm. Đợt 1: lưu/phơi; engine chưa dùng. */
  shift_allowance: number;
  is_active: boolean;
  note: string | null;
}

export interface WorkShiftInput {
  name: string;
  start_time: string;
  end_time: string;
  is_overnight?: boolean;
  night_multiplier?: number;
  grace_minutes?: number;
  meal_allowance?: number;
  shift_allowance?: number;
  note?: string | null;
  is_active?: boolean;
}

export interface TimesheetDay {
  shift_id?: number | null;
  shift_name?: string | null;
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
  planned_off?: boolean; // ngày nghỉ theo lịch phân ca (dấu kế hoạch, không sinh hệ số)
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
  /** TRONG ĐÓ `total_leave`: số ngày nghỉ CÓ lương (trả theo lương vị trí) — đừng cộng thêm. */
  paid_leave_days?: number;
  /** Công THIẾU nhưng có đơn nghỉ theo giờ đã duyệt — KHÔNG nằm trong `total_cong`
   *  (tiền công vẫn trừ), chỉ để Lương giữ nguyên phụ cấp chuyên cần. */
  excused_cong?: number;
  total_hours: number;
  total_cong: number | null;
}

// --- Lưới phân ca tháng (shift plan) ----------------------------------------
// Ô trống = KẾ THỪA ca mặc định; lưới chỉ dùng để ĐÈ ngày khác thường.
// `source` cho biết ca đến từ đâu: day = khai tay trên lưới · assign = mốc ca mặc định ·
// default = cache `default_shift_id` · none = chưa có ca.
export interface ShiftPlanCell {
  shift_id: number | null;
  source: "day" | "assign" | "default" | "none";
  is_off: boolean;
  /** Nghỉ phép ĐÃ DUYỆT — lớp phủ CHỈ ĐỂ XEM, đọc thẳng từ phiếu, không nằm trong bảng ca.
   *  Khác hẳn `is_off` (dấu kế hoạch người dùng tự tô, không ra tiền). Huỷ phiếu là dấu tự hết. */
  leave_name?: string | null;
  leave_paid?: boolean | null;
}

export interface ShiftPlanDay {
  day: number;
  date: string;                       // YYYY-MM-DD
  weekday: number;                    // Mon=0 … Sun=6
  is_working: boolean;
  special_kind: "off" | "work" | "off1x" | null;
  name: string | null;
}

export interface ShiftPlanRow {
  employee_id: number;
  employee_code: string | null;
  employee_name: string;
  department_id: number | null;
  no_default: boolean;                // cả tháng không có ca nào → UI cảnh báo
  days: Record<string, ShiftPlanCell>;
}

export interface ShiftPlanMonth {
  year: number;
  month: number;
  days_in_month: number;
  locked: boolean;                    // kỳ công đã chốt → lưới read-only
  calendar: ShiftPlanDay[];
  shifts: WorkShift[];
  rows: ShiftPlanRow[];
}

export interface ShiftPlanPatchItem {
  employee_id: number;
  work_date: string;                  // YYYY-MM-DD
  action: "set" | "off" | "inherit";  // set = gán ca · off = nghỉ · inherit = xoá ô
  shift_id?: number | null;           // bắt buộc khi action="set"
}

export interface ShiftPlanReject {
  employee_id: number | null;
  date: string;
  reason: string;
}

export interface ShiftPlanSaveOut {
  saved: number;
  cleared: number;
  rejected: ShiftPlanReject[];
  /** Số ô THỰC SỰ đổi (lưu lại y nguyên không tính) — nuôi banner sau khi Lưu. */
  changed: number;
  notified: number;
  /** NV chưa có tài khoản đăng nhập ⇒ không có chỗ nhận thông báo. Nói thẳng, đừng nuốt. */
  not_notified: number;
}

// --- Lịch sử thay đổi ca (chủ 28/07/2026) ---
/** `day` = tô đè MỘT ngày trên lưới · `base` = ca nền, áp từ ngày hiệu lực TRỞ VỀ SAU. */
export type ShiftChangeKind = "day" | "base";
/** Thao tác đến từ màn nào — dùng để hiện chip "Gỡ mốc" tách khỏi "Ca nền". */
export type ShiftChangeOrigin = "grid" | "base_panel" | "base_bulk" | "profile" | "base_remove";
export interface ShiftChange {
  id: number;
  employee_id: number;
  employee_name: string | null;
  employee_code: string | null;
  kind: ShiftChangeKind;
  origin: ShiftChangeOrigin;
  action: "set" | "off" | "inherit" | "remove";
  /** `day` → ngày công bị đổi. `base` → ngày BẮT ĐẦU HIỆU LỰC. Đừng đọc lẫn hai nghĩa này. */
  apply_date: string;
  shift_id_before: number | null;
  shift_name_before: string | null;
  shift_id_after: number | null;
  shift_name_after: string | null;
  is_off_before: boolean;
  is_off_after: boolean;
  /** `day`: trước đó ô đang KẾ THỪA ca nền (chưa ai khai tay ngày này). */
  inherited_before: boolean;
  actor_user_id: number | null;
  actor_name: string | null;
  created_at: string;
  /** false = NV không có tài khoản ⇒ chưa báo được cho ai. */
  notified: boolean;
  seen: boolean;
}
export interface AttendanceNotify {
  unseen_shift_changes: number;
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

// --- Tăng ca (module `tang_ca`) ---------------------------------------------
// `from_minute`/`to_minute` = phút tính từ 00:00 của NGÀY CÔNG; > 1440 nghĩa là đã sang hôm sau
// (vd 03:00 hôm sau = 1620). Cùng trục với cách bảng công gom ca qua đêm.
export interface OvertimeRequest {
  id: number;
  employee_id: number;
  employee_name: string | null;
  work_date: string;
  from_minute: number;
  to_minute: number;
  minutes: number;
  reason: string | null;
  status: string;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string | null;
}
export interface OvertimeInput {
  work_date: string;
  from_minute: number;
  to_minute: number;
  reason?: string | null;
}
export interface OvertimeForInput extends OvertimeInput {
  employee_id: number;
}
export interface MyOvertime {
  has_employee: boolean;
  employee_name: string | null;
  items: OvertimeRequest[];
  /** Tổng phiếu của tôi trên TOÀN BẢNG — không phải `items.length` (đó là số dòng của trang). */
  total: number;
  page: number;
  size: number;
}
export interface OvertimeSummary {
  pending_in_scope: number | null;
  my_decided_unseen: number;
}
export interface OvertimeBulkResult {
  done: number[];
  skipped: number[];
}

// --- Đi muộn / về sớm / nghỉ nửa buổi (module `di_muon`) ---------------------
// Phiếu CHẤM CÔNG ngoại lệ, KHÔNG phải đơn nghỉ phép: 1 phiếu/ngày, tổ trưởng duyệt, khai
// khoảng VẮNG MẶT (`from_minute`→`to_minute`, phút từ 00:00 ngày công, KHÔNG qua nửa đêm).
// `leave_type_id` khác null = người tạo tick "trừ vào phép năm" ⇒ tiêu `leave_cong` ngày phép
// (làm tròn lên 0,5) và phần vắng VẪN được trả lương. Null = mất công phần vắng, quỹ phép nguyên.
export interface LateEarlyRequest {
  id: number;
  employee_id: number;
  employee_name: string | null;
  work_date: string;
  from_minute: number;
  to_minute: number;
  minutes: number;
  leave_type_id: number | null;
  leave_type_name: string | null;
  leave_cong: number;
  reason: string | null;
  status: string;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string | null;
}
export interface LateEarlyInput {
  work_date: string;
  from_minute: number;
  to_minute: number;
  reason?: string | null;
  /** Tick "trừ vào phép năm" → id loại nghỉ; bỏ tick → null. */
  leave_type_id?: number | null;
}
export interface LateEarlyForInput extends LateEarlyInput {
  employee_id: number;
}
export interface MyLateEarly {
  has_employee: boolean;
  employee_name: string | null;
  items: LateEarlyRequest[];
}
export interface LateEarlySummary {
  pending_in_scope: number | null;
  my_decided_unseen: number;
}
export interface LateEarlyBulkResult {
  done: number[];
  skipped: number[];
}
/** Thợ trong tầm + danh mục ca, gác bằng `di_muon:approve`. Tồn tại vì vai "Tổ trưởng SX"
 *  KHÔNG có module `nhan_su` ⇒ `/api/employees` và `/api/attendance/shifts` đều 403 với họ. */
export interface LateEarlyRoster {
  employees: { id: number; code: string | null; full_name: string;
               department: string | null; default_shift_id: number | null }[];
  shifts: { id: number; name: string; start_minute: number; end_minute: number;
            is_overnight: boolean }[];
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
  /** Số dư phép năm — trả ĐỦ, KHÔNG bị phân trang (màn Chấm công đọc đúng ô này). */
  quotas: LeaveQuota[];
  /** Tổng đơn của tôi trên TOÀN BẢNG — không phải `items.length`. */
  total: number;
  page: number;
  size: number;
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
  /** Phía NGƯỜI SỬ DỤNG LAO ĐỘNG — KHÔNG trừ vào lương NV, chỉ để tính chi phí công ty. */
  bhxh_rate_er: number;
  bhyt_rate_er: number;
  bhtn_rate_er: number;
  cong_doan_rate: number;
  /** Tỷ lệ TNLĐ-BNN công ty chịu (mẫu 0.5%=0.005) — khi NV có BH đóng ở nơi khác. */
  tnld_bnn_rate: number;
  deduction_self: number;
  deduction_dependent: number;
  /** Nhánh `khau_tru_10`: thuế = tỷ lệ này × thu nhập chịu thuế (mẫu 0.10 = 10%), chỉ khấu
   *  trừ khi thu nhập ≥ `pit_flat_threshold`. Hai số đổi theo luật ⇒ ĐỪNG viết cứng vào UI. */
  pit_flat_rate: number;
  pit_flat_threshold: number;
  /** Trần khấu trừ kỷ luật (Điều 102 BLLĐ) — mức LUẬT, mặc định 0.30.
   *  `0` = TẮT trần: ghi phạt bao nhiêu trừ bấy nhiêu (thực nhận vẫn có sàn 0). */
  phat_cap_pct: number;
  /** SỐ NGÀY nghỉ không lương trong tháng để MIỄN đóng BHXH tháng đó — mức LUẬT (QĐ 595 Đ42.4),
   *  mặc định 14. `0` = TẮT luật: tháng nào cũng trừ BHXH. Đây là số NGÀY, không phải tỷ lệ. */
  bhxh_mien_tu_so_ngay: number;
  /** Ngưỡng CÔNG của một ngày để hưởng TRỌN cơm + phụ cấp của ca hôm đó (0,5 = nghỉ nửa buổi
   *  vẫn được hưởng). Cố ý không chia theo tỷ lệ — một suất ăn là có hoặc không. */
  phu_cap_ca_min_cong: number;
  chuyen_can_default: number;
  standard_hours_per_day: number;
  ot_multiplier: number;
  ot_multiplier_restday: number;
  ot_multiplier_holiday: number;
  restday_work_multiplier: number;
  holiday_work_multiplier: number;
  night_pct: number;
  /** Cộng dồn tăng ca đêm (Đ98.3) — mặc định 0.2 = +20%. Khai được ở Cấu hình lương. */
  ot_night_extra_pct: number;
  bh_base_cap: number;
  bhtn_base_cap: number;
  /** DORMANT — trần tạm ứng đã gỡ (2026-07-24). Backend vẫn trả field; FE không còn dùng. */
  advance_max_pct: number;
  /** Số NGÀY CÔNG tối đa 1 NV được tự xin chỉnh công trong 1 tháng. 0 = không giới hạn. */
  adjust_max_per_month: number;  /** Suất cơm TĂNG CA: ngưỡng phút/ngày (chỉ áp NGÀY LÀM VIỆC) và tiền một suất.
   *  `com_tang_ca_muc = 0` ⇒ TẮT tính năng. */
  com_tang_ca_nguong_phut: number;
  com_tang_ca_muc: number;
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
  effective_to?: string | null;
  is_current?: boolean;
  amount_mode: string;
  base_amount: number | null;
  /** Mức HỢP ĐỒNG riêng của NV — mức nền = vị trí + trách nhiệm. */
  luong_vi_tri: number;
  luong_trach_nhiem: number;
  /** Lương trả 1 lần (đợt 1) — số điền sẵn khi tạo phiếu "thanh toán lương đợt 1". */
  luong_dot_1?: number;
  /** Mức đóng BH khai riêng (dormant — engine bám luong_vi_tri). */
  insurance_base: number | null;
  /** 3 khoản PHỤ CẤP KHAI TAY — số cố định, engine cộng phẳng, KHÔNG tự tính gì. */
  allowance: number; // phụ cấp KHÁC (gộp)
  phu_cap_ca?: number;
  phu_cap_tham_nien?: number;
  chuyen_can: number;
  /** BH đóng ở nơi khác → công ty chỉ đóng TNLĐ-BNN (prefill checkbox Sửa lương). */
  insurance_elsewhere?: boolean;
  /** Đoàn viên công đoàn → mới bị trừ đoàn phí (prefill checkbox Sửa lương). */
  union_member?: boolean;
  /** Có áp giảm trừ bản thân khi tính TNCN không. Mặc định BẬT; tắt khi người này đã đăng ký
   *  giảm trừ bản thân ở nơi làm việc khác (luật cho đăng ký ở ĐÚNG MỘT nơi). */
  apply_self_deduction?: boolean;
  /** % hoa hồng NV kinh doanh — PHÂN SỐ (0.05 = 5%). Chỉ để khai, engine không tự cộng. */
  commission_pct?: number;
  note: string | null;
  created_at: string;
  created_by?: number | null;
  /** Tên người điều chỉnh (nhật ký "ai sửa"). */
  actor_name?: string | null;
}
export interface EmployeeSalaryInput {
  effective_from: string;
  amount_mode: string;
  base_amount?: number | null;
  /** Gõ riêng 2 ô mức hợp đồng của chính NV — khai thì amount_mode tự thành 'manual'. */
  luong_vi_tri?: number;
  luong_trach_nhiem?: number;
  /** Lương trả 1 lần (đợt 1) — mức trả trong 1 lần, dùng để điền sẵn phiếu đợt 1. */
  luong_dot_1?: number;
  /** 3 khoản phụ cấp KHAI TAY của riêng NV — gõ một lần, tháng nào cũng cộng đúng số này. */
  allowance?: number; // phụ cấp KHÁC (gộp)
  phu_cap_ca?: number;
  phu_cap_tham_nien?: number;
  /** Chuyên cần của riêng NV (0 = dùng mức của tổ). */
  chuyen_can?: number;
  /** BH đóng ở nơi khác → công ty chỉ đóng TNLĐ-BNN (không trừ BHXH/BHYT/BHTN của NV). */
  insurance_elsewhere?: boolean;
  /** Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn. */
  union_member?: boolean;
  /** Áp giảm trừ bản thân khi tính TNCN (mặc định true). Bỏ tích khi người này đã đăng ký
   *  giảm trừ bản thân ở nơi làm việc khác. */
  apply_self_deduction?: boolean;
  /** % hoa hồng NV kinh doanh — PHÂN SỐ (0.05 = 5%), backend chặn `le=1`. */
  commission_pct?: number;
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
  phu_cap_ca: number;
  phu_cap_tham_nien: number;
  insurance_base: number;
  luong_vi_tri: number;
  luong_trach_nhiem: number;
}
export interface SalaryAdvance {
  id: number;
  code: string | null;
  employee_id: number;
  employee_name: string | null;
  department_name: string | null;
  bank_account: string | null;
  bank_name: string | null;
  period_year: number;
  period_month: number;
  advance_date: string;
  amount: number;
  reason: string | null;
  /** tam_ung (mặc định) | luong_dot_1 (thanh toán lương đợt 1). */
  kind: string;
  status: string;
  decision_note: string | null;
  created_at: string;
}

export interface MyAdvanceInput {
  period_year: number;
  period_month: number;
  advance_date: string;
  amount: number;
  reason?: string | null;
  /** tam_ung (mặc định) | luong_dot_1 (tự xin phiếu thanh toán lương đợt 1). */
  kind?: string;
}
export interface SalaryAdvanceInput {
  employee_id: number;
  period_year: number;
  period_month: number;
  advance_date: string;
  amount: number;
  reason?: string | null;
  /** tam_ung (mặc định) | luong_dot_1 (phiếu thanh toán lương đợt 1). */
  kind?: string;
}
export interface MyAdvances {
  has_employee: boolean;
  items: SalaryAdvance[];
  /** Mức "Lương trả 1 lần" hiện hành — điền sẵn khi NV tự xin phiếu đợt 1 (0 = chưa khai). */
  luong_dot_1: number;
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
  /** CỬA SỔ xem phiếu của NLĐ. `cong_bo_luc` = mốc MỞ (`null` = chưa công bố);
   *  `dong_phieu_luc` = mốc ĐÓNG (`null` = mở không thời hạn).
   *  NV thấy phiếu khi `cong_bo_luc <= bây giờ < dong_phieu_luc`. Mở lại kỳ ⇒ cả hai về `null`. */
  cong_bo_luc?: string | null;
  dong_phieu_luc?: string | null;
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
  /** TRONG ĐÓ `luong_cong`: phần trả cho NGÀY NGHỈ PHÉP (chỉ tính lương vị trí, không có
   *  lương trách nhiệm). TUYỆT ĐỐI KHÔNG cộng lại vào tổng thu — cùng idiom với
   *  `phu_cap_tham_nien ⊂ allowance`. Cộng nhầm là SAI TIỀN LƯƠNG. */
  luong_ngay_phep?: number;
  /** Số công phép CÓ lương đã được trả trong `luong_ngay_phep`. */
  paid_leave_cong?: number;
  /** Công thiếu nhưng có đơn nghỉ theo giờ đã duyệt (được miễn phạt, giữ chuyên cần). */
  excused_cong?: number;
  chuyen_can: number;
  /** TỔNG phụ cấp tháng — ĐÃ GỒM 3 dòng dưới. Render 3 dòng thì ĐỪNG cộng thêm số này.
   *  Phụ cấp CA (`ca_pay`/`night_pay`) là khoản RIÊNG, KHÔNG nằm trong `allowance`. */
  allowance: number;
  phu_cap_tham_nien?: number;
  /** Phần còn lại = allowance − thâm niên (backend tính). */
  phu_cap_khac?: number;
  khoan: number;
  ot_minutes: number;
  ot_pay: number;
  night_days: number;
  /** ⚠️ NGƯNG từ 03/08/2026 — luôn 0 ở kỳ mới. Trước là phụ cấp CA khai tay per-người (cộng
   *  phẳng). `ca_pay` là alias, CÙNG một số, đừng cộng 2 lần. Kỳ CŨ đã chốt vẫn còn số ở đây. */
  night_pay: number;
  ca_pay?: number;
  /** Cơm ca = `work_shifts.meal_allowance` × số ngày THỰC LÀM ca đó (ngày đủ ngưỡng công). */
  meal_allowance_pay?: number;
  /** Cơm TĂNG CA — dòng riêng, không gộp cơm ca (hai luật khác nhau, một ngày ăn cả hai được). */
  com_tang_ca_pay?: number;
  /** Phụ cấp ca = `work_shifts.shift_allowance` × số ngày THỰC LÀM ca đó. Tách riêng khỏi cơm vì
   *  tiền ăn giữa ca có trần miễn thuế riêng. */
  shift_allowance_pay?: number;
  /** Premium CA ĐÊM theo giờ (giờ 22h–06h × hệ số + tăng ca đêm) — tự tính từ chấm công, DÒNG RIÊNG. */
  night_premium_pay?: number;
  vi_pham: number;
  /**
   * Khoản DANH MỤC của dòng lương (snapshot Tầng 3) — phiếu lương in TỪNG DÒNG từ đây.
   * ⚠️ `source: "employee"` ĐÃ nằm trong `allowance`; tách thành dòng riêng thì phải trừ khỏi
   * "Phụ cấp khác". `source: "line"` nằm NGOÀI `allowance`, cộng thẳng.
   */
  components?: LineComponent[];
  /** 6 cột dưới đây NGỪNG GHI từ 28/07/2026 (thưởng khai qua `components`). Kỳ cũ vẫn có số. */
  other_bonus: number;
  thuong_5s: number;
  thuong_doanh_so: number;
  thuong_thanh_tich: number;
  phep_nam: number;
  tra_dong_phuc: number;
  dieu_chinh_luong: number;
  di_tre: number;
  /** True = HCNS sửa tay ô "Đi trễ" (phạt tự động không đè); False = tự động từ chấm công. */
  di_tre_manual: boolean;
  dt_vuot_troi: number;
  phat_bien_ban: number;
  phat_5s_dong_phuc: number;
  gross: number;
  insurance_base: number;
  /** TỔNG bảo hiểm NV đóng (10.5%) — số đã đóng băng lúc tính lương. */
  bhxh: number;
  /** Tách 3 khoản cho phiếu lương (nhãn đã kèm tỷ lệ). Tổng 3 dòng == `bhxh`. Rỗng ở đường xuất Excel. */
  insurance_lines?: { label: string; amount: number }[];
  cong_doan: number;
  pit: number;
  pit_manual: boolean;
  /** Thu nhập TÍNH thuế của kỳ (đã trừ bảo hiểm + giảm trừ gia cảnh) — số thuế bấm trên số này.
   *  KHÔNG phải "tổng thu nhập chịu thuế"; backend không snapshot số đó (PRD §3.3). */
  pit_taxable: number;
  /** Tổng phần thu nhập ĐƯỢC MIỄN thuế của kỳ = tăng ca + ca đêm + Σ khoản danh mục
   *  `is_taxable = false`. Snapshot lúc tính lương — đổi cờ hôm nay không làm lệch kỳ cũ. */
  thu_nhap_mien_thue: number;
  advance_total: number;
  /** Tổng "thanh toán lương đợt 1" đã duyệt của kỳ — dòng RIÊNG, KHÔNG gộp vào advance_total. */
  luong_dot_1_total: number;
  net_pay: number;
  note: string | null;
}
export interface PayrollLineInput {
  // ⚠️ CỐ Ý KHÔNG CÓ 6 ô thưởng cũ (`thuong_5s`, `other_bonus`…): từ 28/07/2026 thưởng khai qua
  // danh mục (`addLineComponent`) để cờ "Chịu thuế" là quy tắc chung. Backend cũng đã bỏ chúng
  // khỏi `LineUpdateIn` — thêm lại ở đây chỉ tạo field gửi đi rồi bị bỏ qua trong im lặng.
  vi_pham?: number | null;
  pit?: number | null;
  pit_manual?: boolean | null;
  /** False = đưa phạt trễ VỀ TỰ ĐỘNG (tính lại từ chấm công); None = giữ nguyên. */
  di_tre_manual?: boolean | null;
  monthly_override?: number | null;
  note?: string | null;
  dieu_chinh_luong?: number | null;   // cho phép ±
  di_tre?: number | null;
  dt_vuot_troi?: number | null;
  phat_bien_ban?: number | null;
  phat_5s_dong_phuc?: number | null;
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
// Bảng phạt đi trễ / về sớm (toàn công ty, sửa được) — mirror biểu thuế TNCN.
// `up_to_minute` null = bậc cao nhất (∞, trên 1 giờ); `amount` = tiền phạt/lần (đồng).
export interface LatePenaltyBracket {
  id: number;
  seq: number;
  up_to_minute: number | null;
  amount: number;
}
export interface LatePenaltyBracketInput {
  seq: number;
  up_to_minute?: number | null;
  amount: number;
}

// --- Cấu hình lương: thành phần lương theo BỘ PHẬN (Tab 2) ------------------
// PRD v2.1: chỉ còn 3 khoản khai theo TỔ. Phụ cấp (ca · thâm niên) đã chuyển sang KHAI TAY ở
// từng NV (`employee_salaries`), thưởng KPI xoá hẳn 29/07/2026; gửi key cũ lên BE giờ ăn 422.
export type SalaryComponentKey =
  | "chuyen_can"
  | "luong_khoan"
  | "tang_ca";
export interface DeptComponent {
  component_key: SalaryComponentKey;
  is_enabled: boolean;
  /** null = bật nhưng CHƯA khai mức → 0 đ (không còn mức mặc định công ty để rơi xuống). */
  value: number | null;
  /** Bộ phận đã khai riêng dòng này chưa. */
  is_set: boolean;
  /** LEGACY — danh mục phụ cấp cấp công ty đã gỡ, BE luôn trả mặc định. */
  company_enabled: boolean;
  company_value: number | null;
  company_unit: string | null;
}
export interface DeptComponentInput {
  component_key: SalaryComponentKey;
  is_enabled: boolean;
  value?: number | null;
}
export interface DeptComponents {
  department_id: number;
  items: DeptComponent[];
}

// --- Danh mục khoản thu nhập & thu nhập chịu thuế TNCN (chốt chủ 2026-07-27) ---
// Trước đây mọi phụ cấp gộp vào MỘT ô `allowance` nên engine không biết khoản nào miễn thuế →
// thu thừa TNCN. Giờ mỗi khoản một dòng danh mục, có cờ `is_taxable` bật/tắt tại chỗ.
export type ComponentKind = "thu" | "tru";
export interface PayrollComponent {
  id: number;
  code: string;
  name: string;
  /** `thu` = cộng vào tổng lương · `tru` = khấu trừ. */
  kind: ComponentKind;
  /** Ô tích "Chịu thuế" — false = KHÔNG tính vào thu nhập chịu thuế TNCN. */
  is_taxable: boolean;
  in_insurance_base: boolean;
  sort_order: number;
  is_active: boolean;
  note: string | null;
  /** Số NHÂN VIÊN đang được gán khoản này (hồ sơ — Tầng 2). */
  employee_count: number;
  /** Số KỲ LƯƠNG đã có khoản này (Tầng 3). Đếm KỲ chứ không đếm dòng: 100 dòng cùng một
   *  tháng vẫn là MỘT kỳ. Một trong hai số > 0 ⇒ xoá cứng bị chặn, chỉ ngừng áp dụng được. */
  period_count: number;
}
export interface PayrollComponentInput {
  name: string;
  kind?: ComponentKind;
  is_taxable?: boolean;
  in_insurance_base?: boolean;
  sort_order?: number;
  note?: string | null;
}
/** Sửa TỪNG PHẦN — field nào bỏ qua thì backend giữ nguyên. */
export interface PayrollComponentPatch {
  name?: string;
  kind?: ComponentKind;
  is_taxable?: boolean;
  in_insurance_base?: boolean;
  sort_order?: number;
  is_active?: boolean;
  note?: string | null;
}
/** Kết quả DELETE — nói rõ việc VỪA XẢY RA. `deactivated` = chỉ ngừng áp dụng, KHÔNG xoá:
 *  báo "đã xoá" trong trường hợp này là nói sai việc vừa làm. */
export interface PayrollComponentDeleteResult {
  deleted: boolean;
  deactivated: boolean;
  employee_count: number;
  period_count: number;
  /** Câu backend đã viết sẵn — màn hình hiện NGUYÊN VĂN, không tự chế lại. */
  message: string;
}
/** NV còn được gán một khoản ĐÃ NGỪNG ÁP DỤNG — lương vẫn trả đủ, danh sách này chỉ để HCNS
 *  chủ động gỡ. Backend trả rỗng khi khoản còn đang bật. */
export interface ComponentHolders {
  component_id: number;
  component_name: string;
  items: { employee_id: number; code: string; full_name: string }[];
}
/** Gán MỘT khoản cho NHIỀU người trong một thao tác (chủ 28/07/2026). */
export interface BulkAssignInput {
  amount: number;
  note?: string | null;
  /** Chọn cụ thể. Bỏ trống + `all_active: true` = tất cả NV ĐANG LÀM VIỆC trong phạm vi. */
  employee_ids?: number[];
  all_active?: boolean;
  /** ⚠️ Bật = ĐÈ mức riêng đã khai cho từng người, KHÔNG hoàn tác được. Mặc định tắt. */
  overwrite?: boolean;
}
export interface BulkAssignResult {
  assigned: number;            // thêm mới
  overwritten: number;         // đã ĐÈ mức riêng — hiện riêng, đừng gộp vào `assigned`
  skipped_existing: number;    // đã có mức riêng, không đè
  skipped_out_of_scope: number;
  total: number;
}

/** Khoản ĐANG GÁN cho một NV (Tầng 2). Chỉ trả khoản CÓ TIỀN — không phải cả danh mục. */
export interface ComponentValue {
  component_id: number;
  code: string;
  name: string;
  kind: ComponentKind;
  /** Kế thừa từ danh mục gốc (Tầng 1) — CHỈ ĐỌC, không sửa được ở tầng này. */
  is_taxable: boolean;
  amount: number;
  note: string | null;
  /** false = danh mục đã NGỪNG ÁP DỤNG nhưng người này còn giữ ⇒ bật cảnh báo đỏ.
   *  Tiền VẪN được trả (chốt của chủ) — không tự cắt lương ai. */
  is_active: boolean;
}
export interface ComponentValueInput {
  component_id: number;
  /** null = GỠ khoản khỏi người này (kỳ sau không trả nữa). */
  amount: number | null;
  note?: string | null;
}

/** Tầng 3 — khoản trên MỘT dòng bảng lương. `source`: `employee` = chép từ hồ sơ (sửa ở
 *  Lương → Lương nhân viên) · `line` = thêm tay, CHỈ có ở kỳ này, không lặp sang tháng sau. */
export interface LineComponent {
  id: number;
  component_id: number;
  code: string;
  name: string;
  kind: ComponentKind;
  is_taxable: boolean;
  amount: number;
  note: string | null;
  source: "employee" | "line";
  /** HCNS đã sửa tay số tiền CHO RIÊNG KỲ NÀY. Hồ sơ nhân viên KHÔNG đổi — tháng sau tự về mức
   *  cũ. Dòng đã đè được miễn khỏi lượt ghi đè của "Tính lại". */
  da_de_tay?: boolean;
}
export interface LineComponentInput {
  component_id: number;
  amount: number;
  note?: string | null;
}
export interface LineComponentPatch {
  amount?: number;
  note?: string | null;
}

export interface PayrollTable {
  period: PayrollPeriod | null;
  lines: PayrollLine[];
  /** Vì sao CHƯA chốt được bảng lương — `null` = chốt được. Máy chủ soạn sẵn CÂU CHỮ (kỳ công
   *  chưa chốt · bảng lương cũ hơn ảnh chụp · …) và đã tính cả mốc miễn trừ. ĐỪNG tự suy lại luật
   *  ở đây: số lý do còn tăng, suy lại là nút sáng mà bấm vào ăn lỗi — hoặc tệ hơn, tắt nút của
   *  tháng thật ra chốt được. Xem `PayrollService.ly_do_chua_chot_duoc`. */
  chan_chot_ly_do?: string | null;
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
  department_id: number | null;
  code: string | null;
  name: string;
  unit: string;
  unit_price: number;
  note: string | null;
  is_active: boolean;
}
/** Một bậc thưởng/phạt TỔ TRƯỞNG theo tỷ lệ hàng lỗi của tổ (chủ 29/07/2026).
 *
 *  Tra: bậc ĐẦU TIÊN có `tỷ lệ lỗi ≤ up_to_defect_pct` thắng; `null` = bậc "trở lên" (∞), đúng
 *  MỘT bậc và phải nằm cuối. `rate_pct` DƯƠNG = thưởng · ÂM = phạt, tính trên TỔNG TIỀN KHOÁN
 *  của tổ. ⚠️ Engine CHƯA áp — tổng khoán hiện luôn = 0 vì chưa có nguồn sản lượng. */
export interface LeaderBracket {
  id: number;
  department_id: number;
  seq: number;
  up_to_defect_pct: number | null;
  rate_pct: number;
  note: string | null;
}
export interface LeaderBracketInput {
  up_to_defect_pct: number | null;
  rate_pct: number;
  note?: string | null;
}
export interface LeaderBracketsOut {
  department_id: number;
  /** Ngưỡng SẢN LƯỢNG của tổ trong kỳ để được xét thưởng/phạt. `0` = không gác.
   *  Dưới ngưỡng ⇒ không thưởng không phạt, bất kể tỷ lệ lỗi — vì làm quá ít thì tỷ lệ lỗi vô
   *  nghĩa (hỏng 2 tờ trên 20 tờ đã là 10%). Đi CÙNG GÓI với `items`: màn chỉ có một nút Lưu.
   *  ⚠️ Đây là SỐ LƯỢNG, khác hẳn con số mà % thưởng/phạt nhân lên (đó là TIỀN khoán của tổ).
   *  Con số trần, KHÔNG kèm đơn vị (chủ chốt "Đơn vị bỏ đi"). */
  min_output_qty: number;
  items: LeaderBracket[];
}

export interface PieceRateInput {
  group_name: string;
  department_id?: number | null;
  code?: string | null;
  name: string;
  unit: string;
  unit_price: number;
  note?: string | null;
  is_active?: boolean;
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
  /** Lượt bấm ghi vào SAU khi kỳ đã chốt. Chấm công GPS cố ý KHÔNG bị chặn (chặn thợ bấm
   *  giờ là họ đứng ở cổng bấm mãi không xong, nhất là ca đêm qua nửa đêm) nên chỉ đánh
   *  dấu: ảnh chụp không có mấy lượt này, Bảng lương cũng không ⇒ >0 là phải chốt lại kỳ. */
  phat_sinh_sau_chot?: number;
  pending_leaves: number;    // đơn nghỉ phép chưa duyệt của tháng
  /** Phiếu đi muộn/về sớm chưa duyệt — CHẶN chốt công y như đơn nghỉ: snapshot đóng băng lúc
   *  chốt, phiếu duyệt sau đó không vào được nữa ⇒ NLĐ vẫn ăn phạt dù đã xin phép đúng luật. */
  pending_late_early: number;
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
  kind: "off" | "work" | "off1x";   // off1x = nghỉ, đi làm chỉ lương chính 1× (không hệ số)
  name: string;
  is_paid: boolean;
  note: string | null;
}
export interface SpecialDayInput {
  day: string;
  kind: "off" | "work" | "off1x";
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
  /** Có khi NV có phiếu TC đã duyệt (trong ngày) nhưng chưa có cặp chấm tăng ca → FE nhắc + nút 1 chạm. */
  ot_suggestion?: { from_time: string; to_time: string } | null;
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

/** Hạn mức chỉnh công THÁNG HIỆN TẠI. `limit = 0` ⇒ không giới hạn (`remaining` là null).
 *  `days` = các ngày công ĐÃ tính lượt — gửi thêm đơn cho chính ngày đó KHÔNG tốn lượt mới. */
export interface AdjustQuota {
  year: number;
  month: number;
  limit: number;
  used: number;
  remaining: number | null;
  days: string[];
}
export interface MyAdjustRequests {
  items: AdjustRequest[];
  quota: AdjustQuota | null;
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
// --- Thu mua ----------------------------------------------------------------
export type SupplierStatus = "active" | "inactive";

export interface SupplierItemRow {
  id: number;
  supplier_id: number;
  /** Mặt hàng gốc dòng này bán. null = thứ ngoài danh mục vật tư (dịch vụ, gia công) —
   *  vẫn khai được, chỉ không vào bảng so giá. */
  hang_loai: HangLoai | null;
  hang_id: number | null;
  item_name: string;
  unit: string;
  unit_price: number;
  vat_percent: number;
  /** Mặt hàng còn bán không. Ô chọn NCC ở form phiếu mua lọc theo cờ này — ngưng bán thì không
   *  mời nữa, vì backend cũng chặn đặt mới. */
  is_active: boolean;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplierItemInput {
  hang_loai?: HangLoai | null;
  hang_id?: number | null;
  item_name: string;
  unit: string;
  unit_price: number;
  vat_percent?: number;
  note?: string | null;
}

/** 1 NCC trong bảng SO GIÁ của một mặt hàng. */
export interface SoGiaRow {
  supplier_id: number;
  supplier_name: string;
  supplier_item_id: number;
  unit: string;
  unit_price: number;
  vat_percent: number;
  /** Giá quy về ĐƠN VỊ GỐC — cột duy nhất so được giữa các NCC. null = không quy đổi được
   *  (xem `ly_do`); dòng đó xếp cuối, đừng xếp hạng nó. */
  gia_quy_doi: number | null;
  gia_quy_doi_vat: number | null;
  dien_giai: string | null;
  ly_do: string | null;
}

export interface SoGiaOut {
  hang_loai: HangLoai;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  don_vi_goc: string | null;
  don_vi_goc_ten: string | null;
  items: SoGiaRow[];
}

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
  /** HẠN MỨC công nợ (VNĐ). `0` = KHÔNG đặt hạn mức ⇒ không bao giờ báo vượt. */
  credit_limit: number;
  /** ĐỊNH MỨC = số NGÀY cho nợ kể từ ngày giao. `0` = trả ngay · `null` = CHƯA ĐẶT hạn (đợt giao
      của NCC này không vào cột Quá hạn). Hai thứ khác nhau, đừng ép null thành 0. */
  credit_days: number | null;
  status: SupplierStatus;
  note: string | null;
  created_at: string;
  updated_at: string;
  items: SupplierItemRow[];
}

export interface SupplierItemCatalogRow {
  item_name: string;
  unit: string;
  supplier_count: number;
  min_unit_price: number;
}

/** Một mặt hàng ĐỌC ĐƯỢC từ file Excel — chưa vào DB, mới chỉ nạp vào form. */
export interface SupplierItemImportRow {
  item_name: string;
  unit: string;
  unit_price: number;
  vat_percent: number;
  note: string | null;
}

export interface SupplierItemImportError {
  /** Số dòng trong file EXCEL (đã tính dòng tiêu đề) — mở file là nhảy đúng chỗ. */
  row: number;
  message: string;
}

/** Dòng hỏng KHÔNG huỷ dòng lành ⇒ `items` và `errors` cùng có mặt. */
export interface SupplierItemImportOut {
  items: SupplierItemImportRow[];
  errors: SupplierItemImportError[];
  total_rows: number;
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
  /** Hạn mức công nợ (VNĐ) — `0` = chưa đặt hạn mức. */
  credit_limit?: number;
  /** Số ngày cho nợ — `0` = trả ngay · `null` = chưa đặt hạn. */
  credit_days?: number | null;
  status?: SupplierStatus;
  note?: string | null;
  items?: SupplierItemInput[];
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
  /** Có ≥1 đợt giao nhưng tổng thực nhận CHƯA đủ số đặt — trạng thái SUY RA từ đợt giao. */
  | "partially_received"
  | "received"
  | "cancelled";

export type DepartmentPurchaseRequestStatus =
  | "open"
  | "pending_approval"
  | "in_purchase"
  | "done"
  | "cancelled";

export type DepartmentPurchaseWorkflowStatus =
  | DepartmentPurchaseRequestStatus
  | "drafting"
  | "needs_correction";

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
  /** Dòng YCMH đẻ ra dòng này — nền cho "tình trạng từng sản phẩm" ở chi tiết yêu cầu. */
  department_request_line_id?: number | null;
}

// --- Công nợ phải trả ------------------------------------------------------
// KHÔNG có bảng công nợ dưới DB: mọi số dưới đây SUY RA từ phiếu mua + phiếu chi lúc gọi API.

export interface PayableSupplierRow {
  supplier_id: number | null;
  supplier_name: string;
  /** Số đơn CÒN NỢ. Đơn đã trả xong không đếm ở đây. */
  order_count: number;
  /** Nợ đã QUÁ HẠN trả (theo hạn của từng đợt giao) và phần chưa tới hạn. Cộng lại = `total_due`. */
  overdue_amount: number;
  no_han_amount: number;
  /** `0` = NCC chưa đặt hạn mức ⇒ không bao giờ báo vượt. */
  credit_limit: number;
  /** `0` = trả ngay · `null` = chưa đặt hạn ⇒ đợt giao của NCC này không vào cột Quá hạn. */
  credit_days: number | null;
  /** Cảnh báo MỀM: chỉ gắn cờ, không chặn lập/duyệt phiếu ở đâu cả (Đ6). */
  vuot_han_muc: boolean;
  vuot_bao_nhieu: number;
  /** Tiền ĐÃ CHI trong kỳ. NCC trả hết vẫn giữ được dòng nhờ số này. */
  paid_in_period: number;
  total_due: number;
}

export interface PayablesSummary {
  items: PayableSupplierRow[];
  total: number;
  page: number;
  size: number;
  pages: number;
  total_due: number;
  overdue_amount: number;
  paid_in_period: number;
  vuot_han_muc_count: number;
  period_months: number;
  as_of: string;
}

/** Một khoản CÒN NỢ — thường là một ĐỢT GIAO chưa trả hết.
 *
 * Phiếu cũ (lập trước 06/08/2026, không theo dõi theo đợt) hiện ở mức PHIẾU: `delivery_id` null,
 * `chua_dat_han` true. Không có hạn trả nên không bao giờ vào cột Quá hạn — vì thế nó phải nổi
 * lên ĐẦU danh sách chứ không được chìm. */
export interface PayableItemRow {
  purchase_request_id: number;
  code: string;
  status: PurchaseRequestStatus;
  delivery_id: number | null;
  seq_no: number | null;
  delivery_date: string | null;
  due_date: string | null;
  chua_dat_han: boolean;
  overdue_days: number;
  invoice_number: string | null;
  invoice_date: string | null;
  amount: number;
  /** CHỈ đếm tiền trả ĐÍCH DANH đợt này — cột này phải khớp sao kê NCC theo từng đợt. */
  paid: number;
  /** Phần CỌC của cả đơn chiếu xuống đợt này (giao trước bù trước). Tách khỏi `paid` vì không ai
   *  trả riêng cho đợt này số đó — nhưng `con_no` đã trừ CẢ HAI. */
  coc_bu: number;
  con_no: number;
}

/** Một khoản ĐẶT CỌC / ứng trước cho CẢ ĐƠN — không thuộc đợt giao nào. */
export interface PayableCocRow {
  purchase_request_id: number;
  code: string;
  status: PurchaseRequestStatus;
  amount: number;
  /** Phần cọc đã chiếu xuống các đợt của chính đơn này, và phần còn dôi ra. */
  da_dung: number;
  con_du: number;
}

/** ✅ Một LẦN CHI trong kỳ. Cộng lại đúng bằng cột "Đã trả". */
export interface PayablePaidRow {
  voucher_id: number;
  code: string;
  doc_no: string | null;
  voucher_type: string;
  payment_stage: PaymentStage | null;
  delivery_id: number | null;
  /** Số đợt (1, 2, 3…). null = phiếu đặt cọc, hoặc đơn không theo đợt. */
  delivery_seq_no: number | null;
  purchase_request_id: number;
  purchase_code: string;
  amount: number;
  invoice_number: string | null;
  invoice_date: string | null;
  has_attachment: boolean;
  paid_date: string;
  /** Người LẬP phiếu chi — "ai cho tiền ra" phải đọc được ngay tại dòng. */
  created_by_user_id: number | null;
  created_by_name: string | null;
}

export interface PayablesDetail {
  supplier_id: number;
  supplier_name: string;
  credit_limit: number;
  credit_days: number | null;
  vuot_han_muc: boolean;
  vuot_bao_nhieu: number;
  /** Từng ĐỢT GIAO còn nợ, đã sắp theo hạn trả — đợt `chua_dat_han` nằm ĐẦU danh sách. */
  items: PayableItemRow[];
  /** Cọc/ứng trước của cả đơn — hiện thành dòng riêng, KHÔNG cộng vào `paid` của đợt nào. */
  coc_chung: PayableCocRow[];
  coc_chung_amount: number;
  paid: PayablePaidRow[];
  period_months: number;
  /** true = rổ "đã chi" đang hiện TOÀN BỘ lịch sử, không còn cắt theo kỳ. */
  all_history: boolean;
  total_due: number;
  overdue_amount: number;
  paid_in_period: number;
  as_of: string;
}

// --- Công nợ phải thu ------------------------------------------------------
export interface ReceivableCustomerRow {
  customer_id: number | null;
  customer_name: string;
  invoice_count: number;
  invoiced_amount: number;
  received_amount: number;
  total_due: number;
  overdue_amount: number;
  no_han_amount: number;
  credit_limit: number;
  payment_term_days: number | null;
  vuot_han_muc: boolean;
  vuot_bao_nhieu: number;
  received_in_period: number;
}

export interface ReceivablesSummary {
  items: ReceivableCustomerRow[];
  total: number;
  page: number;
  size: number;
  pages: number;
  total_due: number;
  overdue_amount: number;
  received_in_period: number;
  vuot_han_muc_count: number;
  period_months: number;
  as_of: string;
}

export interface ReceivableItemRow {
  invoice_id: number;
  invoice_symbol: string | null;
  invoice_number: string;
  invoice_date: string;
  order_id: number;
  order_code: string;
  customer_id: number | null;
  customer_name: string;
  due_date: string | null;
  chua_dat_han: boolean;
  overdue_days: number;
  amount: number;
  direct_received_amount: number;
  deposit_offset_amount: number;
  received_amount: number;
  remaining_amount: number;
}

export interface ReceivableReceiptRow {
  receipt_id: number;
  code: string;
  doc_no: string | null;
  order_id: number | null;
  order_code: string | null;
  source_type: PaymentReceiptSource;
  sales_invoice_id: number | null;
  sales_invoice_number: string | null;
  applied_to: "deposit_offset" | "sales_invoice";
  receipt_method: PaymentVoucherType;
  amount: number;
  receipt_date: string;
  payer_name: string;
  bank_reference: string | null;
  created_by_name: string | null;
}

export interface SalesInvoiceInput {
  order_id: number;
  invoice_symbol: string;
  invoice_number: string;
  invoice_date: string;
  /** Omit to invoice the full remaining value of the order. */
  amount_vnd?: number | null;
}

export interface SalesInvoiceRow {
  id: number;
  order_id: number;
  order_code: string;
  customer_id: number | null;
  customer_name: string;
  invoice_symbol: string | null;
  invoice_number: string;
  invoice_date: string;
  amount_vnd: number;
  payment_term_days_snapshot: number | null;
  due_date: string | null;
  status: "issued" | "cancelled";
  direct_received_amount: number;
  deposit_offset_amount: number;
  received_amount: number;
  remaining_amount: number;
  created_by_user_id: number | null;
  created_by_name: string | null;
  created_at: string;
  cancelled_by_user_id: number | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
}

export interface SalesInvoiceListOut {
  order_id: number;
  order_code: string;
  order_total: number;
  invoiced_amount: number;
  uninvoiced_amount: number;
  deposit_received: number;
  items: SalesInvoiceRow[];
}

export interface ReceivablesDetail {
  customer_id: number;
  customer_name: string;
  credit_limit: number;
  payment_term_days: number | null;
  vuot_han_muc: boolean;
  vuot_bao_nhieu: number;
  items: ReceivableItemRow[];
  paid: ReceivableReceiptRow[];
  period_months: number;
  all_history: boolean;
  total_due: number;
  overdue_amount: number;
  received_in_period: number;
  as_of: string;
}

/** Dòng hàng ĐÃ GÁN nhà cung cấp — chỉ dùng cho đường tạo cả mẻ. */
export interface PurchaseRequestBatchLineInput extends PurchaseRequestLineInput {
  supplier_id: number;
}

export interface PurchaseRequestBatchInput {
  source_request_ids: number[];
  /** Ô GỘP "Nội dung / mục đích" (07/08/2026). `purpose`/`note` là đường CŨ, server còn nối lại
   *  để client chưa cập nhật không gãy — giao diện mới chỉ gửi `content`. */
  content: string;
  purpose?: string | null;
  needed_date: string;
  expected_receipt_date?: string | null;
  note?: string | null;
  lines: PurchaseRequestBatchLineInput[];
}

export interface DepartmentPurchaseRequestLineInput {
  /** MẶT HÀNG GỐC của dòng — chọn từ danh mục Giấy + Vật tư khác, KHÔNG gõ tay. Thiếu cặp này
   *  thì phiếu mua sinh ra sau đó phải ghép bằng tên, mà ghép trượt thì im lặng sai. */
  hang_loai?: HangLoai | null;
  hang_id?: number | null;
  item_name: string;
  unit: string;
  quantity: number;
  note?: string | null;
  /** UI-only (KHÔNG gửi API): dòng lấy từ mặt hàng Kho đã có → khoá Tên + ĐVT, bỏ qua canh danh
   *  mục NCC. Payload gửi đi pick field tường minh nên cờ này không lọt lên backend. */
  locked?: boolean;
}

export interface DepartmentPurchaseRequestInput {
  source_type?: DepartmentPurchaseSourceType | null;
  related_document_type?: string | null;
  related_document_code?: string | null;
  /** Ô GỘP "Nội dung / mục đích" — xem `PurchaseRequestBatchInput.content`. */
  content: string;
  purpose?: string | null;
  needed_date: string;
  note?: string | null;
  lines: DepartmentPurchaseRequestLineInput[];
}

export interface PurchaseRequestInput {
  supplier_id: number | null;
  source_request_ids: number[];
  /** Ô GỘP "Nội dung / mục đích" — xem `PurchaseRequestBatchInput.content`. */
  content: string;
  purpose?: string | null;
  needed_date: string;
  expected_receipt_date?: string | null;
  note?: string | null;
  lines: PurchaseRequestLineInput[];
}

/** Khai số thực nhận cho một dòng. `null` = xoá khai báo, quay về "nhận đủ". */
export interface ReceivedLineInput {
  line_id: number;
  received_quantity: number | null;
}

export interface PurchaseRequestLineOut {
  id: number;
  item_name: string;
  unit: string;
  quantity: number;
  /** `null` = chưa khai lúc nhận hàng ⇒ hiểu là nhận đủ `quantity`. */
  received_quantity: number | null;
  expected_unit_price: number;
  discount_percent: number;
  discount_amount: number;
  vat_percent: number;
  vat_amount: number;
  line_total: number;
  note: string | null;
  /** Liên kết mặt hàng gốc (mg 0174) — Nhập kho từ đợt giao auto-điền vật tư. Null = chỉ tên chữ. */
  hang_loai: HangLoai | null;
  hang_id: number | null;
  hang_ma: string | null;
  hang_ten: string | null;
}

/** Một dòng yêu cầu đã vào phiếu nào, của NCC nào, tới đâu rồi. */
export interface LineFulfilment {
  purchase_request_id: number;
  purchase_code: string;
  purchase_status: PurchaseRequestStatus;
  supplier_name: string | null;
  ordered_quantity: number;
  ordered_unit: string;
  /** null = chưa khai lúc nhận hàng ⇒ hiểu là nhận đủ `ordered_quantity`. */
  received_quantity: number | null;
}

export interface DepartmentPurchaseRequestLineOut {
  id: number;
  hang_loai: HangLoai | null;
  hang_id: number | null;
  item_name: string;
  unit: string;
  quantity: number;
  expected_unit_price: number;
  line_total: number;
  note: string | null;
  /** null = dòng CHƯA vào phiếu nào, HOẶC phiếu lập trước 05/08/2026 (chưa có nối dòng ↔ dòng).
      Hai ca đó phải hiện khác nhau — xem `DepartmentPurchaseRequestRow.purchase_requests`. */
  fulfilment: LineFulfilment | null;
}

/** Một lần đổi trạng thái của YCMH/PMH. */
export interface StatusHistoryRow {
  id: number;
  /** null = dòng ĐẦU TIÊN (lúc phiếu sinh ra), chưa có trạng thái trước đó. */
  from_status: string | null;
  to_status: string;
  /** `may` = hệ TỰ suy ra (vd. giao đủ hàng ⇒ "đã nhận"), lúc đó không có người đứng tên. */
  source: "nguoi" | "may";
  changed_by_name: string | null;
  reason: string | null;
  created_at: string;
}

/** Một mốc trong lịch sử Đơn mua hàng: đổi trạng thái hoặc thao tác trên một đợt giao. */
export interface PurchaseActivityRow {
  id: string;
  event_type: "status" | "delivery_created" | "delivery_updated" | "delivery_deleted" | "invoice_assigned";
  title: string;
  detail: string | null;
  actor_name: string | null;
  source: "nguoi" | "may" | null;
  from_status: string | null;
  to_status: string | null;
  reason: string | null;
  created_at: string;
}

export interface DepartmentRequestPurchaseRow {
  id: number;
  code: string;
  status: PurchaseRequestStatus;
  supplier_name: string | null;
}

export interface DepartmentPurchaseRequestRow {
  id: number;
  code: string;
  status: DepartmentPurchaseRequestStatus;
  workflow_status: DepartmentPurchaseWorkflowStatus;
  source_type: DepartmentPurchaseSourceType;
  requesting_department_id: number | null;
  requesting_department_name: string | null;
  requested_by_user_id: number | null;
  requested_by_name: string | null;
  related_document_type: string | null;
  related_document_code: string | null;
  /** Ô GỘP "Nội dung / mục đích". `purpose`/`note` giữ lại cho phiếu CŨ, đừng hiện thêm. */
  content: string | null;
  purpose: string;
  needed_date: string;
  note: string | null;
  /** Lý do TỪ CHỐI / HUỶ — tách khỏi nội dung để lý do của người duyệt không đè lời người khai. */
  reject_reason: string | null;
  status_history: StatusHistoryRow[];
  created_at: string;
  updated_at: string;
  total_estimate: number;
  lines: DepartmentPurchaseRequestLineOut[];
  /** Phiếu mua sinh ra từ yêu cầu này — luôn có, kể cả khi `fulfilment` theo dòng còn rỗng. */
  purchase_requests: DepartmentRequestPurchaseRow[];
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
  /** Ô GỘP "Nội dung / mục đích" của YCMH. `purpose` là bản CẮT 500 ký tự, chỉ dùng cho phiếu cũ. */
  content: string | null;
  purpose: string | null;
  needed_date: string | null;
  requesting_department_name: string | null;
  requested_by_name: string | null;
}

/** Một dòng hàng của MỘT đợt giao. Cố ý KHÔNG có cột tiền: tiền của đợt suy từ đơn giá đã chốt
 *  trên phiếu mua, mở ô tiền ở đây là đẻ nguồn sự thật thứ hai. */
export interface PurchaseDeliveryLineRow {
  id: number;
  purchase_request_line_id: number;
  item_name: string;
  unit: string;
  quantity: number;
  note: string | null;
}

export interface PurchaseDeliveryRow {
  id: number;
  /** Đợt 1, 2, 3… trong phạm vi PHIẾU MUA — không phải dãy số toàn hệ. */
  seq_no: number;
  /** Liên thông Kho: đợt đã sinh yêu cầu NHẬP (chưa hủy) chưa → nút "Nhập kho" đổi "Đã nhập kho". */
  da_nhap_kho: boolean;
  stock_request_id: number | null;
  stock_request_ma: string | null;
  delivery_date: string;
  due_date: string | null;
  /** true = NCC chưa khai số ngày cho nợ ⇒ đợt này KHÔNG BAO GIỜ vào cột Quá hạn. Màn hình phải
      đẩy nó lên đầu kèm badge, không để chìm — im lặng ở đây là một món nợ không ai canh. */
  chua_dat_han: boolean;
  /** NHIỀU đợt cùng số = cùng MỘT hoá đơn. */
  invoice_number: string | null;
  invoice_date: string | null;
  note: string | null;
  /** Thành tiền của đợt — MÁY TÍNH từ số lượng × đơn giá/CK/VAT đã chốt trên phiếu.
   *  Không ai gõ tay (chủ chốt 07/08/2026, đảo lại quyết định 06/08). */
  amount: number;
  /** Tiền trả ĐÍCH DANH đợt này. */
  paid_amount: number;
  /** Cọc của cả đơn chiếu xuống đợt này. */
  coc_bu: number;
  /** Còn nợ của RIÊNG đợt = amount − paid_amount − coc_bu. Đây là TRẦN lập phiếu chi cho đợt. */
  con_no: number;
  /** Ai ghi đợt này, lúc nào — đợt giao đẻ ra công nợ nên phải truy được người khai. */
  created_by_name: string | null;
  created_at: string | null;
  lines: PurchaseDeliveryLineRow[];
}

/** `hop_dong` = file của cả phiếu mua · các loại còn lại thường gắn vào một đợt giao. */
export type PurchaseAttachmentKind =
  | "hop_dong"
  | "hoa_don"
  | "bien_ban_giao"
  | "khac";

export interface PurchaseAttachmentRow {
  id: number;
  /** null = tài liệu của cả PHIẾU MUA (hợp đồng), khác null = của một đợt giao. */
  delivery_id: number | null;
  kind: PurchaseAttachmentKind;
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_by_name: string | null;
  uploaded_at: string;
}

export interface PurchaseDeliveryLineInput {
  purchase_request_line_id: number;
  quantity: number;
  note?: string | null;
}

export interface PurchaseDeliveryInput {
  delivery_date: string;
  due_date?: string | null;
  invoice_number?: string | null;
  invoice_date?: string | null;
  note?: string | null;
  /** `null`/bỏ trống khi SỬA = giữ nguyên các dòng hàng, chỉ đổi phần đầu đợt. */
  lines?: PurchaseDeliveryLineInput[] | null;
}

/** Gán MỘT hoá đơn cho NHIỀU đợt — ca NCC giao 3 đợt rồi mới xuất một hoá đơn chung. */
export interface PurchaseInvoiceAssignInput {
  delivery_ids: number[];
  invoice_number?: string | null;
  invoice_date?: string | null;
}

export interface PurchaseContractInput {
  contract_number?: string | null;
  /** Cọc DỰ KIẾN — chỉ để đối chiếu, KHÔNG vào công thức công nợ (cọc thật là phiếu chi). */
  deposit_expected: number;
}

/** Hạn mức công nợ của NCC so với nợ hiện tại — CẢNH BÁO MỀM, không chặn gì (Đ6). */
export interface SupplierCredit {
  credit_limit: number;
  credit_days: number | null;
  no_hien_tai: number;
  vuot_han_muc: boolean;
  vuot_bao_nhieu: number;
}

export interface PurchaseRequestRow {
  id: number;
  code: string;
  status: PurchaseRequestStatus;
  supplier_id: number | null;
  supplier_name: string | null;
  /** Ô GỘP "Nội dung / mục đích". `purpose`/`note` giữ lại cho phiếu CŨ, đừng hiện thêm. */
  content: string | null;
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
  /** Lý do TỪ CHỐI / HUỶ — tách khỏi nội dung để lý do của người duyệt không đè lời người khai. */
  reject_reason: string | null;
  status_history: StatusHistoryRow[];
  /** Lịch sử đầy đủ của đơn, gồm đổi trạng thái và các đợt giao. */
  activity_history: PurchaseActivityRow[];
  created_at: string;
  updated_at: string;
  contract_number: string | null;
  /** Cọc DỰ KIẾN — chỉ để nhắc, KHÔNG vào công thức công nợ. */
  deposit_expected: number;
  total_estimate: number;
  /** Giá trị hàng THỰC NHẬN. Bằng `total_estimate` chừng nào chưa ai khai thiếu. */
  received_total: number;
  /** Giá trị hàng ĐÃ VỀ (Σ các đợt giao) — số đẻ ra công nợ. Chưa giao đợt nào thì = 0. */
  gia_tri_da_giao: number;
  paid_amount: number;
  receipt_received_amount: number;
  /** Đã chi RÒNG = phiếu chi đã chi − phiếu thu đã thu. */
  net_paid: number;
  /** = CÔNG NỢ của phiếu, và cũng là trần lập phiếu chi THANH TOÁN. */
  outstanding_amount: number;
  /** Trần lập phiếu ĐẶT CỌC — theo giá trị đơn đặt, vì cọc là chi khi hàng chưa về. */
  tran_dat_coc: number;
  /** Phiếu ĐẶT CỌC đã lập cho đơn này — dùng để CẢNH BÁO khi sắp lập phiếu cọc thứ hai.
   *  Cảnh báo chứ không chặn: ứng thêm là ca có thật, và mỗi lần tiền rời két phải có chứng từ
   *  riêng (sửa phiếu cũ lên số to hơn là làm phiếu không khớp lần chi thật). */
  coc_da_lap: { code: string; doc_no: string | null; amount: number; voucher_date: string }[];
  coc_da_chi: number;
  payment_status: "unpaid" | "partial" | "paid";
  payment_voucher_count: number;
  sources: PurchaseRequestSourceOut[];
  lines: PurchaseRequestLineOut[];
  deliveries: PurchaseDeliveryRow[];
  attachments: PurchaseAttachmentRow[];
}

export interface PurchaseRequestListOut {
  items: PurchaseRequestRow[];
  total: number;
  page: number;
  size: number;
}

export type PaymentVoucherType = "cash" | "bank_transfer";
export type PaymentStage = "advance" | "partial" | "final" | "other";
export type PaymentVoucherSource =
  | "purchase_request"
  | "internal_expense"
  | "customer_refund"
  | "other";
/** BỎ HẲN `waiting_payment` từ 06/08/2026 (Đ1): lập phiếu chi = tiền ĐÃ RA, phiếu sinh ra đã là
 *  `paid`. Migration đã chuyển mọi phiếu "chờ chi" cũ thành `paid` (có dấu trong `note`). */
export type PaymentVoucherStatus = "paid" | "cancelled";

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

export interface CompanyBankAccountInput extends BankAccountInput {
  use_for_receipts: boolean;
  use_for_payments: boolean;
}

export interface CompanyBankAccountRow extends CompanyBankAccountInput {
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

export interface PaymentVoucherAccountsInput {
  /** Định khoản in trên mẫu ("242, 1331" / "1111") — nhập tay, không bắt buộc. */
  debit_account?: string | null;
  credit_account?: string | null;
}

export interface PaymentVoucherBaseInput extends PaymentVoucherAccountsInput {
  source_type?: PaymentVoucherSource | null;
  voucher_type: PaymentVoucherType;
  payment_stage: PaymentStage;
  /** Đợt giao mà phiếu này trả cho. BẮT BUỘC với phiếu thanh toán khi đơn CÓ đợt giao; phải để
      trống với phiếu đặt cọc (cọc là tiền chi khi hàng chưa về nên chưa có đợt nào để gắn). */
  delivery_id?: number | null;
  voucher_date: string;
  /** DORMANT từ 06/08/2026: hạn trả nay thuộc về ĐỢT GIAO, phiếu chi là tiền đã ra nên không có
      hạn. Giữ khoá để phiếu cũ không vỡ — đừng bày lại thành ô nhập. */
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
  beneficiary_account_holder?: string | null;
  beneficiary_account_number?: string | null;
  beneficiary_bank_name?: string | null;
  beneficiary_bank_branch?: string | null;
  bank_fee_bearer?: "payer" | "beneficiary" | "shared" | null;
  note?: string | null;
}

export interface PaymentVoucherInput extends PaymentVoucherBaseInput {
  purchase_request_id?: number | null;
}

export interface PaymentVoucherRow {
  id: number;
  code: string;
  /** Số IN trên mẫu 02-TT (PC00445) — khác `code` (mã tra cứu nội bộ). */
  doc_no: string | null;
  debit_account: string | null;
  credit_account: string | null;
  source_type: PaymentVoucherSource;
  purchase_request_id: number | null;
  purchase_request_code: string;
  purchase_request_total: number | null;
  purchase_paid_amount: number | null;
  purchase_created_by_name: string | null;
  receipt_received_amount: number;
  receipt_pending_amount: number;
  attachment_count: number;
  /** null = phiếu ĐẶT CỌC, hoặc phiếu cũ lập trước khi có khái niệm đợt giao. */
  delivery_id: number | null;
  delivery_seq_no: number | null;
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
  /** DORMANT từ 06/08/2026: không còn phiếu "chờ chi" nên số này luôn 0. Đừng hiện lên màn. */
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
export type PaymentReceiptSource =
  | "purchase_refund"
  | "order_deposit"
  | "sales_invoice"
  | "other";

export interface PaymentReceiptInput extends PaymentVoucherAccountsInput {
  payer_name: string;
  /** Ô "Địa chỉ" của mẫu 01-TT — không bắt buộc. */
  payer_address?: string | null;
  receipt_method: PaymentVoucherType;
  receipt_date: string;
  amount: number;
  exchange_rate?: number | null;
  content: string;
  company_bank_account_id?: number | null;
  bank_reference?: string | null;
  note?: string | null;
}

export interface PaymentReceiptRow {
  id: number;
  code: string;
  /** Số IN trên mẫu 01-TT (PT00027). */
  doc_no: string | null;
  source_type: PaymentReceiptSource;
  payment_voucher_id: number | null;
  payment_voucher_code: string | null;
  purchase_request_id: number | null;
  purchase_request_code: string | null;
  supplier_name: string | null;
  order_id: number | null;
  order_code: string | null;
  customer_name: string | null;
  sales_invoice_id: number | null;
  sales_invoice_number: string | null;
  payer_name: string;
  payer_address: string | null;
  debit_account: string | null;
  credit_account: string | null;
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

// --- Đơn hàng bán (redesign-don-hang-ban.md) --------------------------------
export interface OrderLineOut {
  id: number;
  description: string;
  qty: number;
  don_vi_tinh: string;   // ĐVT dòng (kéo từ báo giá / gõ tay)
  unit_price_snapshot: number | null;
  vat_pct_estimate: number;
  line_total: number | null;
  cost_snapshot: number | null;
  phieu_thanh_phan_id: number | null;
  /** Nhãn nhóm gộp KHI IN xác nhận đơn — copy từ dòng báo giá, khớp bản khách đã nhận. */
  nhom: string | null;
}
export interface AttachmentOut {
  id: number;
  url: string;
  file_name: string | null;
  content_type: string | null;
  uploaded_at: string;
}
export interface OrderDepositReceipt {
  id: number;
  code: string;
  doc_no: string | null;
  amount: number;
  receipt_method: string;   // cash | bank_transfer
  status: string;           // received (V5: lập là đã thu)
  receipt_date: string | null;
  created_at: string;
}
export interface OrderDepositReceiptInput {
  receipt_method: string;   // cash | bank_transfer
  amount: number;
  receipt_date?: string | null;
  note?: string | null;
  company_bank_account_id?: number | null;
}
export interface OrderApprovalOut {
  id: number;
  decision: string;
  triggers_json: string[] | null;
  note: string | null;
  decided_by: number | null;
  decided_by_name: string | null;
  decided_at: string;
  order_total: number;
  order_subtotal: number;
  order_cost: number | null;
  margin_pct_snapshot: number | null;
}
/** Phiếu thu 01-TT của đơn (nguồn cọc thật, dùng chung quyển sổ PT kế toán). */
export interface OrderReceiptOut {
  id: number;
  code: string;
  doc_no: string | null;
  receipt_method: string;          // cash | bank_transfer
  amount: number;
  status: string;                  // waiting_receipt | received | cancelled
  receipt_date: string | null;
  content: string | null;
  bank_reference: string | null;
  payer_name: string | null;
  debit_account: string | null;
  credit_account: string | null;
  created_by_name: string | null;
  attachments: AttachmentOut[];
}
export interface OrderReceiptInput {
  receipt_method: string;          // cash | bank_transfer
  amount: number;
  receipt_date: string;
  content?: string | null;
  bank_reference?: string | null;
  company_bank_account_id?: number | null;
  note?: string | null;
  mark_received?: boolean;
}
export interface OrderRow {
  id: number;
  order_no: string;
  customer_id: number | null;
  customer_name: string | null;
  quotation_id: number | null;
  quotation_code: string | null;
  /** DORMANT: chỉ còn 'bao_gia' cho đơn MỚI; đơn 'nhap_tay' cũ trong DB vẫn trả ra giá trị này. */
  source_type: string;
  order_kind: string;
  status: string;
  is_rush: boolean;
  cost_basis: string;
  total: number | null;
  total_with_vat: number;
  deposit_pct: number | null;
  deposit_required: number;
  deposit_received: number;
  deposit_ok: boolean;
  delivery_committed_date: string | null;
  sale_user_id: number | null;
  sale_name: string | null;
  created_at: string;
  ordered_at: string | null;
}
export interface OrderListOut {
  items: OrderRow[];
  total: number;
  page: number;
  size: number;
}
export interface OrderDetail extends OrderRow {
  quotation_version: number | null;
  quotation_effective_from: string | null;
  parent_order_id: number | null;
  parent_order_no: string | null;
  customer_po_no: string | null;
  delivery_address: string | null;
  delivery_contact_name: string | null;
  delivery_contact_phone: string | null;
  delivery_note: string | null;
  production_note: string | null;
  vat_pct_estimate: number;
  lines: OrderLineOut[];
  order_cost: number | null;
  margin_pct: number | null;
  cancel_reason: string | null;
  cancel_fault: string | null;
  deposits: OrderDepositReceipt[];   // V5: phiếu thu cọc THẬT (PaymentReceipt nguồn đơn)
  consent_attachments: AttachmentOut[];
  can_confirm: boolean;
  confirm_blockers: string[];
  quote_expired: boolean;   // Việc 4: báo giá nguồn hết hạn → bật nút "Gia hạn báo giá"
  san_xuat_released_at: string | null;  // Sale "Chuyển xuống SX" → vào hàng chờ Kế hoạch (NULL=chưa)
}
export interface OrderStatsOut {
  all: number;
  draft: number;
  ordered: number;
  cancelled: number;
  awaiting_deposit: number;
  deposit_shortfall: number;
  ordered_value: number;
}
/** Đơn CHỈ sinh từ báo giá khách đã đồng ý — `quotation_id` bắt buộc, không còn nhánh nhập tay. */
export interface OrderCreateInput {
  quotation_id: number;
  order_kind?: string;
  parent_order_id?: number | null;
  deposit_pct?: number | null;
  customer_po_no?: string | null;
  delivery_committed_date?: string | null;
  delivery_address?: string | null;
  delivery_contact_name?: string | null;
  delivery_contact_phone?: string | null;
  delivery_note?: string | null;
  production_note?: string | null;
  is_rush?: boolean;
}
export interface OrderUpdateInput {
  deposit_pct?: number | null;
  customer_po_no?: string | null;
  delivery_committed_date?: string | null;
  delivery_address?: string | null;
  delivery_contact_name?: string | null;
  delivery_contact_phone?: string | null;
  delivery_note?: string | null;
  production_note?: string | null;
  is_rush?: boolean | null;
}
export interface OrderNotifySummary {
  action_count: number;
  /** Luôn 0 — luồng duyệt đã gỡ; backend vẫn trả khoá để client cũ không vỡ. */
  approval_pending: number;
  deposit_pending: number;
  ready_to_confirm: number;
}
export interface OrderEnumOption {
  value: string;
  label: string;
}
export interface OrderEnumsOut {
  statuses: OrderEnumOption[];
}
export interface OrderActivity {
  at: string;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  detail: string;
}
export interface OrderListParams {
  q?: string;
  status?: string;
  order_kind?: string;
  view_scope?: string;
  sort?: string;
  page?: number;
  size?: number;
}

/** 1 nhãn trong KHO nhãn khách + số khách đang mang nó.
 *
 *  `so_khach` có sẵn trong danh sách để hộp thoại xoá hỏi được bằng SỐ THẬT ("3 khách đang mang
 *  nhãn này") thay vì "bạn có chắc không" — không phải gọi thêm vòng nào lúc bấm xoá. */
export interface KhoNhanRow {
  id: number;
  label: string;
  so_khach: number;
}

// --- Khuôn (danh mục dùng chung — chứa cả khuôn bế lẫn khuôn ép nhũ) --------
// Tên bảng + module quyền vẫn là `khuon_be`; chỉ nhan đề màn đổi thành "Khuôn" (16/08/2026).
export interface KhuonBeRow {
  id: number;
  ma: string;
  ten: string;
  /** Khách đặt con dao — chiều lọc chính của ô chọn dao ở bước lệnh. */
  khach_hang_id: number | null;
  khach_hang_ten: string | null;
  /** `khuon_be` | `khuon_ep` — CÙNG bộ mã với `cong_doan.tooling_type` để lọc bằng phép so thẳng. */
  loai: string | null;
  so_ke: string | null;
  tinh_trang: string;
  ngay_ve_du_kien: string | null;
  active: boolean;
}

/** 1 con dao chọn được cho bước của một lệnh — server đã lọc theo khách của lệnh. */
export interface KhuonChonDuoc {
  id: number;
  ma: string;
  ten: string;
  /** null = dao khai trước mg 0205, chưa ai phân loại — VẪN hiện ở mọi bước, giấu đi là bắt
   *  người ta đi làm lại con dao đang nằm trên kệ. */
  loai: string | null;
  so_ke: string | null;
  tinh_trang: string;
  ngay_ve_du_kien: string | null;
}

// (`LichChayRow` — 1 lệnh trong bảng lịch chạy Máy × Ngày — đã gỡ 16/08/2026: tàn dư của lớp
//  SX-thực-thi đời cũ, khai ra mà KHÔNG nơi nào import. Bảng lịch chạy nay là `XepLichCongDoan`.)

// 1 công đoạn routing GỐC của ấn phẩm (đọc từ Tính giá) — KHÔNG có đơn giá (cô lập thương mại).
export interface RoutingGocRow {
  thu_tu: number;
  cong_doan_id: number | null;
  ten: string;
  nha_cung_cap: string | null;
  ghi_chu: string | null;
}
// 1 vật tư thêm của ấn phẩm (vecni bóng/mờ · cán màng…) — tên + ghi chú, không giá.
export interface VatTuGocRow {
  ten: string;
  ghi_chu: string | null;
}
// Chi tiết ĐẦY ĐỦ ấn phẩm cho DRAWER (mirror phiếu công đoạn) — CHỈ KỸ THUẬT (đã lọc sạch giá).
// Giá trị HIỆU LỰC = báo giá + override tại lệnh. editable = mở từ lệnh NHÁP (được sửa quy cách).
export interface AnPhamChiTiet {
  phieu_thanh_phan_id: number;
  lenh_item_id: number | null;
  editable: boolean;
  overridden: string[]; // các field đã override so với báo giá
  // nhận dạng / thành phẩm
  ten: string;
  loai_thanh_phan: string;
  dai_thanh_pham: number;
  rong_thanh_pham: number;
  so_to_per_sp: number;
  so_luong: number;
  don_vi_tinh: string;
  // giấy (đã resolve tên + chủng loại)
  giay_id: number | null;
  giay_ten: string | null;
  chung_loai_ten: string | null;
  gsm: number | null;
  kho_nguyen: string | null;
  kho_nguyen_dai: number;
  kho_nguyen_rong: number;
  nguon_giay: string;
  // in & màu
  co_in: boolean;
  che_ban_loai: string | null;
  quy_cach_in: string;
  kho_in_dai: number;
  kho_in_rong: number;
  so_con: number;
  con_auto: boolean;
  may_id: number | null;
  so_mau_a: number;
  so_mau_b: number;
  so_kem: number;
  // số lượng (engine snapshot — null nếu phiếu chưa tính)
  so_luong_can: number | null;
  so_to_thuc_te: number | null;
  so_to_sau_in: number | null;
  so_to_nguyen: number | null;
  con_tren_to: number | null;
  bu_hao_auto: number | null;
  // note kỹ thuật theo sản phẩm + vật tư + routing
  ghi_chu_ky_thuat: string | null;
  vat_tu: VatTuGocRow[];
  routing: RoutingGocRow[];
}
// Handoff (§5.1): đơn đã chốt CHỜ lên kế hoạch — kèm ngữ cảnh để kế hoạch cấu hình.
export interface HangChoAnPham {
  phieu_thanh_phan_id: number | null;
  description: string;
  qty: number;
  don_vi_tinh: string;
  spec_tom_tat: string; // quy cách rút gọn (khổ TP · số màu · giấy) — kỹ thuật, không giá
}
export interface HangChoDon {
  order_id: number;
  order_no: string;
  khach: string | null;
  is_rush: boolean;
  delivery_committed_date: string | null;
  production_note: string | null;
  an_pham: HangChoAnPham[];
}
export interface LenhSXListParams {
  order_id?: number;
  trang_thai?: string;
  page?: number;
  size?: number;
}
/** 1 dòng xếp bài khi tạo tờ (ghép) — số con NHẬP TAY (máy chỉ ghi). */
export interface GhepPlacementInput {
  lenh_sx_id: number;
  so_con: number;
}
/** Tạo 1 TỜ IN + xếp bài. Giấy/khổ/màu là ẢNH CHỤP (người kế hoạch tự nhìn PTG rồi nhập). */
export interface GhepInput {
  giay_id?: number | null;
  giay_label?: string | null;
  kho_in_dai?: number;
  kho_in_rong?: number;
  so_mau?: number;
  may_id?: number | null;
  so_to_chay?: number;
  so_kem?: number;
  placements: GhepPlacementInput[];
}

// --- Kho: đề nghị · phiếu · lô · ngưỡng tồn (spec-kho-de-nghi) ---------------
// Mọi trường TIỀN (`don_gia`, `thanh_tien`, `gia_von`, `don_gia_nhap`) và `ton_kha_dung`
// là `null` khi người gọi thiếu quyền — backend XÓA số khỏi response chứ không chỉ ẩn cột,
// nên UI chỉ cần dò null để quyết định ẩn ô/cột.

export type StockRequestKind = "NHAP" | "XUAT";

export type StockRequestStatus =
  | "draft"
  | "pending"
  | "approved"
  | "received"
  | "preparing"
  | "partial"
  | "done"
  | "rejected"
  | "cancelled";

export type StockPriority = "binh_thuong" | "gap";

/** Đèn tín hiệu 4 mức (bỏ "sắp hết/cận tồn") — KHÔNG kèm con số nên ai cũng nhận được. */
export type StockLevel = "du_ton" | "du" | "can_mua" | "het";

export type StockVoucherStatus = "draft" | "posted" | "cancelled";

export interface StockRequestLine {
  id: number;
  /** MẶT HÀNG GỐC — cặp trỏ danh mục Giấy / Vật tư khác. Không còn hàng gõ tay (siết 2026-08-08). */
  hang_loai: HangLoai;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  /** Ảnh minh hoạ mặt hàng (từ danh mục) — form phiếu nhập hiện + cho gắn/đổi ảnh ngay khi nhập. */
  hang_anh: string | null;
  /** Nhãn nhóm ("Giấy" / "Vật tư khác") — chip phân biệt hai nguồn khi tên gần giống. */
  hang_nhom: string | null;
  /** "Xin cho lệnh nào" (mg 0175). Cả hai null = xin lặt vặt, không thuộc lệnh nào — hợp lệ.
   *  Có giá trị thì bảng cân đối vật tư trừ phần đã cấp vào ĐÚNG dòng nhu cầu của lệnh đó. */
  lsx_id: number | null;
  bai_ghep_id: number | null;
  lsx_ma: string | null;
  bai_ghep_ma: string | null;
  /** Đơn vị NGƯỜI ĐỀ NGHỊ chọn; mọi `sl_*` của dòng theo đơn vị này. */
  dvt: string;
  /** Số quy về ĐƠN VỊ GỐC + câu diễn giải — dòng nhắc "10 ram ≈ 419,25 kg" dưới ô SL.
   *  `canh_bao_dv` khác null = không đổi được (kèm nguyên văn lý do), FE phải chặn lưu. */
  don_vi_goc: string | null;
  sl_quy_doi: number | null;
  quy_doi_dien_giai: string | null;
  canh_bao_dv: string | null;
  sl_de_nghi: number;
  sl_duyet: number;
  sl_da_ung: number;
  sl_con_lai: number;
  /** Đơn giá NHẬP người đề nghị khai — phiếu kế thừa (kho chỉ đọc). Null với đề nghị XUẤT. */
  don_gia: number | null;
  /** Kho phản hồi: lý do kho cấp/nhập thiếu so với còn phải cấp (nếu có). */
  ly_do_thieu: string | null;
  ghi_chu: string | null;
  muc_ton: StockLevel | null;
  /** CHỈ có khi `can_view_stock`; thiếu quyền → null. */
  ton_kha_dung: number | null;
}

export interface StockRequest {
  id: number;
  ma: string;
  loai: StockRequestKind;
  nguoi_tao_id: number;
  nguoi_tao_ten: string | null;
  bo_phan_id: number | null;
  bo_phan_ten: string | null;
  kho_id: number | null;
  kho_ten: string | null;
  ngay_can: string | null;
  uu_tien: StockPriority;
  ghi_chu: string | null;
  /** Mã loại nhập/xuất kho (MISA) người tạo gõ ở yêu cầu — Báo cáo kho dùng để export. */
  loai_kho: string | null;
  trang_thai: StockRequestStatus;
  nguoi_duyet_id: number | null;
  nguoi_duyet_ten: string | null;
  duyet_luc: string | null;
  ly_do_tu_choi: string | null;
  /** Lý do KHO hủy đề nghị (hủy phiếu → đề nghị "Đã hủy"). Hiện ở mục "Đã hủy". */
  ly_do_huy: string | null;
  // Id phiếu ĐANG CHỜ GHI SỔ (nếu có) → đổi nút "Lập phiếu" thành "Xem phiếu", chống tạo trùng.
  open_voucher_id: number | null;
  created_at: string;
  /** Lần đổi gần nhất (tạo/cấp/hoàn tất/hủy) — xếp yêu cầu vừa có phản hồi lên đầu. */
  updated_at: string;
  lines: StockRequestLine[];
}

export interface StockRequestPage {
  items: StockRequest[];
  total: number;
}

export interface StockRequestListParams {
  q?: string | null;
  loai?: StockRequestKind | null;
  trang_thai?: StockRequestStatus[];
  kho_id?: number | null;
  page?: number;
  size?: number;
}

export interface StockRequestLineInput {
  // Mặt hàng BẮT BUỘC chọn từ danh mục gốc — không còn đường gõ tên tự do.
  hang_loai: HangLoai;
  hang_id: number;
  /** Xin CHO LỆNH NÀO (mg 0175) — bỏ trống được (xin lặt vặt). Server kiểm id có thật. */
  lsx_id?: number | null;
  bai_ghep_id?: number | null;
  dvt: string;
  sl_de_nghi: number;
  /** Đơn giá NHẬP người đề nghị khai (chỉ đề nghị NHẬP), theo `dvt`. Phiếu kế thừa; kho không sửa. */
  don_gia?: number | null;
  ghi_chu?: string | null;
}

export interface StockRequestInput {
  loai: StockRequestKind;
  /** Kho KHÔNG chọn ở đề nghị nữa — quyết ở bước lập phiếu. Giữ optional cho tương thích. */
  kho_id?: number | null;
  /** Số đề nghị tự nhập; bỏ trống → hệ thống tự sinh. */
  ma?: string | null;
  ngay_can?: string | null;
  uu_tien?: StockPriority;
  ghi_chu?: string | null;
  /** Mã loại nhập/xuất kho (MISA) — người tạo gõ tay; báo cáo dùng để export. */
  loai_kho?: string | null;
  /** Nguồn đợt giao đơn mua (chỉ khi tạo từ nút "Nhập kho" ở đợt) — chặn nhập trùng. */
  purchase_delivery_id?: number | null;
  lines: StockRequestLineInput[];
}

export interface StockRequestUpdateInput {
  ngay_can?: string | null;
  uu_tien?: StockPriority;
  ghi_chu?: string | null;
  loai_kho?: string | null;
  lines?: StockRequestLineInput[];
}

/** Báo cáo kho (kế toán) — 1 dòng hàng của 1 phiếu đã ghi sổ. docs/spec-bao-cao-kho.md */
export interface BaoCaoKhoRow {
  voucher_id: number;
  ngay_ghi_so: string | null;
  ngay_ct: string | null;
  so_ct: string;
  loai: StockRequestKind;
  loai_kho: string | null;
  ma_hang: string | null;
  ten_hang: string | null;
  dvt: string | null;
  so_luong: number;
  don_gia: number | null;
  thanh_tien: number | null;
  kho_id: number | null;
  kho_ten: string | null;
}

export interface BaoCaoKhoPage {
  items: BaoCaoKhoRow[];
  total: number;
}

export interface BaoCaoKhoParams {
  tu?: string | null;
  den?: string | null;
  kho_id?: number | null;
  loai?: StockRequestKind | null;
  /** Tìm số CT / mã hàng / tên hàng — để "lọc gì = xuất nấy" (cả bảng lẫn file). */
  q?: string | null;
}

/** Khóa/mở kỳ kế toán kho — 1 thao tác trên KHOẢNG ngày. kho_id null = toàn kho. Append-only = lịch sử. */
export interface KhoKhoaSoRow {
  id: number;
  kho_id: number | null;
  kho_ten: string | null;
  tu_ngay: string;
  den_ngay: string;
  hanh_dong: "khoa" | "mo";
  nguoi_khoa_ten: string | null;
  khoa_luc: string | null;
  ten: string | null;
}

export interface KhoKhoaSoInput {
  kho_id?: number | null;
  tu_ngay: string;
  den_ngay: string;
  hanh_dong: "khoa" | "mo";
  /** Tên kỳ — chỉ gửi khi khóa; trùng tên kỳ đang khóa khác thì backend chặn. */
  ten?: string | null;
}

/** 1 kỳ CÒN đang khóa (đã gộp khoảng liền mạch) — cho tab "Kỳ đã khóa". */
export interface KhoaSoKyRow {
  kho_id: number | null;
  kho_ten: string | null;
  tu_ngay: string;
  den_ngay: string;
  khoa_luc: string | null;
  ten: string | null;
}

/** Ô chọn vật tư khi lập đề nghị — 4 trường tối thiểu, KHÔNG có giá. */
export interface StockMaterialOption {
  id: number;
  code: string | null;
  name: string | null;
  unit: string | null;
  don_vi_phu?: string | null;
  he_so_quy_doi?: number | null;
}

/** Loại mặt hàng gốc — hai danh mục, hai dãy id riêng nên luôn đi theo CẶP với `hang_id`. */
export type HangLoai = "giay" | "vat_tu";

// --- Kế hoạch vật tư: bảng CÂN ĐỐI -----------------------------------------
// ⚠️ KHÔNG có trường tiền nào ở đây, và đừng thêm: bảng mở cho vai Kế hoạch SX, còn giá vốn lô
// hàng thuộc quyền Kho/Kế toán (`view_cost`).

/** Màu của một dòng cân đối. `khong_ro` = KHÔNG quy đổi được đơn vị ⇒ máy chưa đánh giá được —
 *  cố ý tách khỏi `xam` ("đã cấp đủ"), vì dán nhãn đủ lên dòng chưa ai tính nổi là nói ngược. */
export type CanDoiMau = "xam" | "xanh" | "vang" | "do" | "khong_ro";

export interface CanDoiDong {
  /** `vat_tu` = so tồn · `cong_cu` = khuôn bế, KHÔNG so tồn (chỉ hỏi sẵn sàng đúng lúc chưa). */
  loai: "vat_tu" | "cong_cu";
  lsx_id: number | null;
  bai_ghep_id: number | null;
  ma: string;
  ten_viec: string | null;
  ngay_can: string | null;
  /** true = bước CHƯA xếp lịch ⇒ ngày cần là mốc SUY (hạn SX − tổng thời gian dẫn). Phải hiện
   *  khác mốc thật, không thì người dùng tin vào một con số chưa ai chốt. */
  moc_tam: boolean;
  /** Mọi số theo ĐƠN VỊ GỐC của mặt hàng. null ở dòng công cụ. */
  nhu_cau: number | null;
  /** Hai đơn vị cùng lúc: "2.961 tờ ≈ 116 kg". */
  nhu_cau_hien_thi: string;
  da_cap: number | null;
  /** CHỈ LÀ NHÃN — hàng chưa ra khỏi kho thì tồn vẫn còn, không vào phép trừ nào. */
  dang_linh: number | null;
  con_phai_co: number | null;
  con_lai_sau: number | null;
  /** Phần thiếu RIÊNG của dòng (không phải luỹ kế) — tick nhiều dòng rồi cộng vẫn đúng. */
  thieu: number | null;
  trang_thai: CanDoiMau;
  /** Hạn chót phải đặt = ngày cần − số ngày kiểm nhập. Không còn trừ "số ngày NCC giao" (ô đó đã
   *  bỏ 10/08/2026 — khai tay là số đoán). */
  han_dat: string | null;
  dat_muon: boolean;
  canh_bao: string[];
  ly_do_canh_bao: string | null;
}

export interface CanDoiNhom {
  loai_nhom: "vat_tu" | "cong_cu";
  hang_loai: string;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  don_vi_goc: string | null;
  ton: number | null;
  tong_can: number | null;
  so_dong_do: number;
  /** Số dòng KHÔNG đánh giá được. Bộ lọc "chỉ mặt hàng đang thiếu" GIỮ LẠI nhóm có số này > 0. */
  so_dong_khong_ro: number;
  khuon_tinh_trang: string | null;
  khuon_ngay_ve: string | null;
  dong: CanDoiDong[];
}

/** Lệnh/bài KHÔNG cân đối được — hiện thẳng ra thay vì im lặng bỏ. */
export interface CanDoiBoQua {
  ma: string;
  ly_do: string;
}

export interface CanDoiOut {
  items: CanDoiNhom[];
  bo_qua: CanDoiBoQua[];
}

/** Khoá của một dòng trên bảng — đủ để server tìm lại và TỰ tính phần thiếu. */
export interface CanDoiKhoaDong {
  hang_loai: HangLoai;
  hang_id: number;
  lsx_id: number | null;
  bai_ghep_id: number | null;
}

/** 1 dòng trong picker mặt hàng (gộp Giấy + Vật tư khác). KHÔNG có giá. */
export interface MatHangOption {
  hang_loai: HangLoai;
  hang_id: number;
  nhom: string;
  ma: string;
  ten: string;
  don_vi_goc: string | null;
}

/** 1 đơn vị dùng được cho mặt hàng đang chọn. `he_so_ve_goc` = 1 đơn vị này bằng bao nhiêu
 *  đơn vị gốc — nhân với số người dùng gõ ra số sẽ vào tồn. */
export interface DonViDungDuoc {
  ma: string;
  ten: string;
  he_so: number;
  he_so_ve_goc: number;
  la_goc: boolean;
  dien_giai: string;
}

export interface DonViCuaMatHang {
  hang_loai: HangLoai;
  hang_id: number;
  ma: string;
  ten: string;
  don_vi_goc: string | null;
  don_vi_goc_ten: string | null;
  ds: DonViDungDuoc[];
  /** Vì sao `ds` rỗng — UI hiện nguyên câu này thay vì im lặng khoá ô. */
  ly_do: string | null;
}

export interface StockVoucherLine {
  id: number;
  request_line_id: number;
  hang_loai: HangLoai;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  dvt: string | null;
  lot_id: number | null;
  ma_lo: string | null;
  /** SL đề nghị gốc của dòng (đọc-nối) — đối chiếu "đề nghị vs thực nhận/xuất". null = không nối được. */
  sl_de_nghi: number | null;
  so_luong: number;
  /** Số đã quy về đơn vị gốc — số THẬT SỰ chạy vào lô/tồn. */
  sl_goc: number | null;
  don_vi_goc: string | null;
  ghi_chu: string | null;
  don_gia: number | null;
  thanh_tien: number | null;
}

export interface StockVoucher {
  id: number;
  ma: string;
  loai: StockRequestKind;
  request_id: number;
  request_ma: string | null;
  /** Loại phiếu (tự do) người tạo gõ ở yêu cầu — hiện trên phiếu + list. */
  loai_kho: string | null;
  kho_id: number;
  kho_ten: string | null;
  ngay: string;
  nguoi_lap_id: number;
  nguoi_lap_ten: string | null;
  /** Chuỗi trách nhiệm từ đề nghị gốc: ai đề nghị · ai duyệt. */
  nguoi_de_nghi_ten: string | null;
  nguoi_duyet_ten: string | null;
  /** Người GHI SỔ (duyệt/chốt phiếu) — chỉ có sau khi đã ghi sổ. */
  nguoi_ghi_so_ten: string | null;
  nguoi_giao_nhan: string | null;
  ghi_chu: string | null;
  trang_thai: StockVoucherStatus;
  ghi_so_luc: string | null;
  created_at: string;
  lines: StockVoucherLine[];
  /** Tổng giá vốn — chỉ có khi `can_view_cost`. */
  gia_von: number | null;
}

export interface StockVoucherPage {
  items: StockVoucher[];
  total: number;
}

export interface StockVoucherAttachment {
  id: number;
  stock_voucher_id: number;
  file_name: string;
  /** Đường dẫn tải (mount /static). Tải xuống = origin + file_url. */
  file_url: string;
  file_type: string | null;
  uploaded_by: number | null;
  uploaded_at: string;
}

export interface StockVoucherListParams {
  q?: string | null;
  loai?: StockRequestKind | null;
  trang_thai?: StockVoucherStatus | null;
  request_id?: number | null;
  kho_id?: number | null;
  page?: number;
  size?: number;
}

export interface StockVoucherLineInput {
  /** Mặt hàng KẾ THỪA từ dòng đề nghị (kho không đổi được) nên phiếu chỉ gửi `request_line_id`. */
  request_line_id: number;
  so_luong: number;
  /** Phiếu NHẬP: giá của lô sắp tạo. Phiếu XUẤT: bỏ qua (giá lấy đích danh từ lô). */
  don_gia?: number | null;
  /** Phiếu XUẤT: bắt buộc. Phiếu NHẬP: bỏ qua (lô sinh ra lúc ghi sổ). */
  lot_id?: number | null;
  /** Lý do cấp/nhập THIẾU (khi SL < còn phải cấp) — bắt buộc nếu thiếu; ghi vào đề nghị. */
  ly_do?: string | null;
  ghi_chu?: string | null;
  /** Phiếu NHẬP: vị trí cất lô (kệ/ô) — thủ kho khai; ghi sổ chép sang lô. */
  vi_tri?: string | null;
}

export interface StockVoucherInput {
  request_id: number;
  kho_id: number;
  /** Số phiếu tự nhập; bỏ trống → hệ thống tự sinh. */
  ma?: string | null;
  ngay?: string | null;
  nguoi_giao_nhan?: string | null;
  ghi_chu?: string | null;
  lines: StockVoucherLineInput[];
}

export interface StockLot {
  id: number;
  ma_lo: string;
  hang_loai: HangLoai;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  /** Ảnh minh hoạ mặt hàng (từ danh mục). Màn Tồn kho gom theo mặt hàng nên chép sẵn vào lô. */
  hang_anh: string | null;
  /** ĐƠN VỊ GỐC — `sl_ban_dau`/`sl_con_lai` của lô đều theo đơn vị này. */
  dvt: string | null;
  kho_id: number;
  vi_tri: string | null;
  ngay_nhap: string;
  ncc: string | null;
  sl_ban_dau: number;
  sl_con_lai: number;
  hsd: string | null;
  trang_thai: string;
  /** Phiếu NHẬP đã tạo ra lô — hiển thị lô THEO MÃ PHIẾU (link mở phiếu). Null với tồn đầu kỳ. */
  voucher_id: number | null;
  voucher_ma: string | null;
  /** Chỉ có khi `can_view_cost` — thủ kho chọn lô mà không thấy giá. */
  don_gia_nhap: number | null;
  /** SL đề nghị đã sinh ra lô (đọc-nối). Không phải tiền → luôn có. null = lô đầu kỳ / không nối được. */
  sl_de_nghi: number | null;
}

export interface StockAllocationLine {
  lot_id: number;
  ma_lo: string;
  ngay_nhap: string;
  hsd: string | null;
  sl_con_lai: number;
  so_luong: number;
  don_gia_nhap: number | null;
}

export interface StockAllocation {
  lines: StockAllocationLine[];
  /** > 0 = kho không đủ hàng cho số cần cấp. */
  thieu: number;
}

export interface StockThreshold {
  id: number;
  hang_loai: HangLoai;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  kho_id: number;
  nguong_ton: number;
  nguong_can_ton: number | null;
  nguong_toi_da: number | null;
  canh_bao: boolean;
}

/** 1 dòng phiếu XUẤT đã ghi sổ của mã hàng — theo dõi xuất riêng với nhập (lô). */
export interface StockMaterialXuatRow {
  ngay: string;
  voucher_id: number;
  voucher_ma: string | null;
  lot_id: number | null;
  ma_lo: string | null;
  /** SL đề nghị đã sinh ra dòng xuất (đọc-nối). Không phải tiền → luôn có. null = không nối được. */
  sl_de_nghi: number | null;
  so_luong: number;
  /** Giá vốn đích danh của lô đã xuất — chỉ có khi `can_view_cost`. */
  don_gia: number | null;
}

/** Lịch sử 1 mã hàng tại 1 kho: NHẬP = các lô (cả đã hết) · XUẤT = dòng phiếu xuất. */
export interface StockMaterialHistory {
  hang_loai: HangLoai;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  dvt: string | null;
  on_hand: number;
  nhap: StockLot[];
  xuat: StockMaterialXuatRow[];
}

export interface StockThresholdInput {
  hang_loai: HangLoai;
  hang_id: number;
  kho_id: number;
  nguong_ton: number;
  /** Bỏ trống → backend tự suy ra = nguong_ton × 1.3. */
  nguong_can_ton?: number | null;
  nguong_toi_da?: number | null;
  canh_bao?: boolean;
}

// --- Nội quy công ty --------------------------------------------------------

export interface NoiQuyRecord {
  id: number;
  code: string;
  name: string;
  file_name: string;
  file_url: string;
  file_type: string;
  file_size: number;
  note: string | null;
  uploaded_by_user_id: number;
  uploaded_by_name: string;
  uploaded_at: string;
}

/** Tải một file nhị phân về dạng blob URL, tự làm mới token khi 401. */
async function blobUrl(path: string, token: string): Promise<string> {
  const doFetch = (bearer: string) =>
    fetch(`${BASE_URL}${path}`, {
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
      salary: DepartmentSalaryPolicy | null = null,
    ): Promise<Department> {
      return authed<Department>("/api/departments", token, {
        method: "POST",
        body: JSON.stringify({
          name,
          description,
          parent_id: parentId,
          level_id: levelId,
          ...(salary ?? {}),
        }),
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
      salary: DepartmentSalaryPolicy | null = null,
      laSanXuat: boolean = false,
      /** Cờ khối Kinh doanh. `undefined` = KHÔNG gửi ⇒ backend giữ nguyên — luồng đổi trưởng
       *  phòng không được âm thầm gỡ khối Kinh doanh của phòng. */
      laKinhDoanh?: boolean,
    ): Promise<Department> {
      return authed<Department>(`/api/departments/${id}`, token, {
        method: "PUT",
        body: JSON.stringify({
          name,
          head_user_id: headUserId,
          description,
          level_id: levelId,
          parent_id: parentId,
          ...(salary ?? {}),
          la_san_xuat: laSanXuat,
          ...(laKinhDoanh === undefined ? {} : { la_kinh_doanh: laKinhDoanh }),
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
    // `createUser` ĐÃ GỠ: mọi tài khoản phải thuộc một hồ sơ nhân viên → tạo tài khoản
    // qua Hồ sơ nhân sự (`api.employees.create` kèm `account`, hoặc `api.employees.linkAccount`).
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
    /** Bulk điều chuyển NHÂN SỰ sang phòng khác — theo hồ sơ, nên người chưa có tài khoản
     *  cũng chuyển được; mỗi lần chuyển ghi Quá trình công tác + gỡ vai trò cũ. */
    transferStaff(
      token: string,
      employeeIds: number[],
      targetDepartmentId: number,
    ): Promise<{ transferred: number }> {
      return authed<{ transferred: number }>("/api/departments/transfer", token, {
        method: "POST",
        body: JSON.stringify({
          employee_ids: employeeIds,
          target_department_id: targetDepartmentId,
        }),
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
    /** Bảng VAI MẪU — bộ quyền dựng sẵn cho các vai điển hình (đợt 6).
     *  CHỈ ĐỌC: giao diện điền vào ma trận đang mở, người dùng xem lại rồi mới bấm Lưu. */
    roleTemplates(token: string): Promise<RoleTemplate[]> {
      return authed<RoleTemplate[]>("/api/roles/templates", token);
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
      if (params.chua_gan) qs.set("chua_gan", "true");
      else if (params.sale != null) qs.set("sale", String(params.sale));
      if (params.followup) qs.set("followup", "true");
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
    /** Sửa CHÍNH SÁCH TÀI CHÍNH (hạn mức + điều khoản + rào chiết khấu/biên) — endpoint
     *  riêng, gate `set_credit_terms`. Trả detail (customer + receivable card). */
    updateFinancial(
      token: string,
      id: number,
      input: CustomerFinancialInput,
    ): Promise<CustomerDetailOut> {
      return authed<CustomerDetailOut>(`/api/customers/${id}/financial`, token, {
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
    // --- kho nhãn dùng chung (thêm / xoá nhãn — 16/08/2026) ---
    // ĐỪNG nhầm với `tagLabels` ngay trên: cái đó trả nhãn ĐÃ ĐƯỢC GÁN cho khách nào đó (nguồn của
    // ô lọc), còn đây là kho nhãn CÓ THỂ gán — nhãn vừa tạo, chưa ai mang, chỉ có ở đây.
    tagKho(token: string): Promise<{ items: KhoNhanRow[] }> {
      return authed<{ items: KhoNhanRow[] }>("/api/customers/tag-kho", token);
    },
    themNhanKho(token: string, label: string): Promise<KhoNhanRow> {
      return authed<KhoNhanRow>("/api/customers/tag-kho", token, {
        method: "POST",
        body: JSON.stringify({ label }),
      });
    },
    /** Xoá nhãn khỏi kho VÀ gỡ khỏi mọi khách đang mang. Trả số khách bị gỡ. */
    xoaNhanKho(token: string, nhanId: number): Promise<{ so_khach_da_go: number }> {
      return authed<{ so_khach_da_go: number }>(`/api/customers/tag-kho/${nhanId}`, token, {
        method: "DELETE",
      });
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
    careCalendar(token: string, id: number, from: string, to: string): Promise<CareCalendarOut> {
      return authed<CareCalendarOut>(
        `/api/customers/${id}/care-calendar?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        token,
      );
    },
    actOnOccurrence(
      token: string,
      id: number,
      headId: number,
      from: string,
      to: string,
      input: {
        action: "complete" | "cancel" | "reschedule";
        occurrence_date?: string | null;
        new_due?: string | null;
        log_kind?: string | null;
        log_note?: string | null;
      },
    ): Promise<CareCalendarOut> {
      return authed<CareCalendarOut>(
        `/api/customers/${id}/care-tasks/${headId}/occurrence?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        token,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    addCareTask(
      token: string,
      id: number,
      input: {
        note: string;
        due_date: string;
        assignee_user_id?: number | null;
        repeat_freq?: string;
        repeat_interval?: number;
        repeat_until?: string | null;
      },
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
    // --- ghi chú tự do (tab Ghi chú) ---
    notes(token: string, id: number): Promise<{ items: CustomerNote[] }> {
      return authed<{ items: CustomerNote[] }>(`/api/customers/${id}/notes`, token);
    },
    addNote(token: string, id: number, body: string): Promise<CustomerNote> {
      return authed<CustomerNote>(`/api/customers/${id}/notes`, token, {
        method: "POST",
        body: JSON.stringify({ body }),
      });
    },
    updateNote(
      token: string,
      id: number,
      noteId: number,
      input: { body?: string; pinned?: boolean },
    ): Promise<CustomerNote> {
      return authed<CustomerNote>(`/api/customers/${id}/notes/${noteId}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    deleteNote(token: string, id: number, noteId: number): Promise<void> {
      return authed<void>(`/api/customers/${id}/notes/${noteId}`, token, {
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
    /** Danh sách nhân sự ra .xlsx THẬT (blob URL). Máy chủ lấy TRỌN theo phạm vi quyền + đúng
     *  bộ lọc đang chọn — không phụ thuộc trang đang xem, không cắt ở 200 người. */
    exportXlsxBlobUrl(
      token: string,
      params: { q?: string; status?: string | null; department_id?: number | null; sort?: string } = {},
    ): Promise<string> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.department_id != null) qs.set("department_id", String(params.department_id));
      if (params.sort) qs.set("sort", params.sort);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return blobUrl(`/api/employees/export.xlsx${suffix}`, token);
    },
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
    /** Danh mục bậc tay nghề. Mặc định chỉ lấy bậc ĐANG BẬT — form khai chỉ được chọn bậc
     *  còn dùng; muốn xem cả bậc đã tắt thì `active_only: false`. */
    jobGrades(token: string, params: { active_only?: boolean } = {}): Promise<{ items: JobGrade[] }> {
      const qs = params.active_only === false ? "?active_only=false" : "?active_only=true";
      return authed<{ items: JobGrade[] }>(`/api/employees/bac-tay-nghe${qs}`, token);
    },
    /** Thêm bậc ngay trong form khai (khỏi bắt sang màn khác rồi quay lại mất dữ liệu đang gõ).
     *  Trùng tên → 400 kèm câu tiếng Việt của backend, hiện thẳng dưới ô nhập. */
    createJobGrade(token: string, input: { name: string }): Promise<JobGrade> {
      return authed<JobGrade>("/api/employees/bac-tay-nghe", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
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
    setShift(token: string, id: number, shiftId: number | null, effectiveFrom: string): Promise<{ ok: boolean; employee_id: number; default_shift_id: number | null; assignment_id: number; effective_from: string }> {
      return authed(`/api/employees/${id}/shift`, token, {
        method: "PUT",
        body: JSON.stringify({ default_shift_id: shiftId, effective_from: effectiveFrom }),
      });
    },
    /** Đặt CA NỀN cho nhiều NV trong MỘT request (nút "Đặt ca nền" ở màn Phân ca tháng).
     *  Ca nền áp dụng từ `effectiveFrom` trở về sau cho MỌI tháng — khác với tô ca trên
     *  lưới (chỉ đúng ngày đã tô). */
    setShiftBulk(token: string, employeeIds: number[], shiftId: number | null, effectiveFrom: string):
      Promise<{ updated: number; adjusted: number; failed: { employee_id: number; reason: string }[] }> {
      return authed("/api/employees/shift/bulk", token, {
        method: "PUT",
        body: JSON.stringify({ employee_ids: employeeIds, default_shift_id: shiftId, effective_from: effectiveFrom }),
      });
    },
    shiftHistory(token: string, id: number): Promise<{ employee_id: number; items: EmployeeShiftAssignment[] }> {
      return authed<{ employee_id: number; items: EmployeeShiftAssignment[] }>(`/api/employees/${id}/shift-history`, token);
    },
    /** Gỡ một mốc ca nền gán nhầm — không có đường này thì mốc sai là vĩnh viễn. */
    deleteShiftAssignment(token: string, id: number, assignmentId: number): Promise<void> {
      return authed<void>(`/api/employees/${id}/shift-history/${assignmentId}`, token, { method: "DELETE" });
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
    /** Cắt trang Ở MÁY CHỦ (`page`/`size`) + lọc theo trạng thái. Trả kèm `dem` cho pill lọc. */
    myRequests(token: string, opts?: { status?: string; page?: number; size?: number }): Promise<MyUpdateRequestsPage> {
      const qs = new URLSearchParams();
      if (opts?.status) qs.set("status", opts.status);
      qs.set("page", String(opts?.page ?? 1));
      qs.set("size", String(opts?.size ?? 10));
      return authed<MyUpdateRequestsPage>(`/api/employees/me/update-requests?${qs}`, token);
    },
    /** NV tự rút lại đề nghị của mình khi HCNS chưa xử lý. Dòng vẫn còn (status `cancelled`). */
    cancelMyRequest(token: string, id: number): Promise<UpdateRequest> {
      return authed<UpdateRequest>(`/api/employees/me/update-requests/${id}/cancel`, token, { method: "POST" });
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
    /** Cấp tài khoản MỚI cho hồ sơ đã có — đường chính (mọi tài khoản sinh ra từ một hồ sơ). */
    createAccount(
      token: string,
      id: number,
      input: { username: string; password: string; role_id?: number | null },
    ): Promise<EmployeeDetail> {
      return authed<EmployeeDetail>(`/api/employees/${id}/account`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** Liên kết một tài khoản CÓ SẴN — chỉ dùng để dọn tài khoản mồ côi cũ. */
    linkAccount(token: string, id: number, userId: number): Promise<EmployeeDetail> {
      return authed<EmployeeDetail>(`/api/employees/${id}/account`, token, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
    },
    // `unlinkAccount` ĐÃ GỠ: gỡ liên kết = đẻ ra tài khoản mồ côi (vi phạm luật "mọi tài
    // khoản thuộc một hồ sơ"). Chặn một người = KHÓA tài khoản (`api.rbac.setUserActive`).
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
    myAdjustRequests(token: string): Promise<MyAdjustRequests> {
      return authed<MyAdjustRequests>("/api/attendance/me/adjust-requests", token);
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
    /** Nhật ký chấm công — 100 lượt gần nhất. `q` tìm theo TÊN hoặc MÃ nhân viên và chạy ở
     *  SERVER: lọc ở client chỉ tìm trong 100 lượt đã tải, mà 100 lượt của cả xưởng chưa hết nửa
     *  ngày ⇒ gõ tên ai cũng dễ ra "không tìm thấy" dù họ vẫn đi làm. */
    logs(
      token: string,
      employeeId?: number,
      q?: string,
      tuNgay?: string,
      denNgay?: string,
    ): Promise<{ items: AttendanceLog[] }> {
      const qs = new URLSearchParams();
      if (employeeId != null) qs.set("employee_id", String(employeeId));
      if (q && q.trim()) qs.set("q", q.trim());
      // Khoảng NGÀY VN, trọn hai đầu. Có lọc ngày thì server tự nới trần dòng.
      if (tuNgay) qs.set("tu_ngay", tuNgay);
      if (denNgay) qs.set("den_ngay", denNgay);
      const suffix = qs.toString() ? `?${qs}` : "";
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
    // --- Lưới phân ca tháng (shift plan) ---
    shiftPlan(token: string, year: number, month: number, departmentId?: number | null): Promise<ShiftPlanMonth> {
      const qs = new URLSearchParams({ year: String(year), month: String(month) });
      if (departmentId != null) qs.set("department_id", String(departmentId));
      return authed<ShiftPlanMonth>(`/api/attendance/shift-plan?${qs.toString()}`, token);
    },
    /** Lưu hàng loạt (tối đa 2000 ô/request) — ô sai trả về trong `rejected`, KHÔNG bị nuốt. */
    saveShiftPlan(token: string, year: number, month: number, items: ShiftPlanPatchItem[]): Promise<ShiftPlanSaveOut> {
      return authed<ShiftPlanSaveOut>("/api/attendance/shift-plan", token,
        { method: "PUT", body: JSON.stringify({ year, month, cells: items }) });
    },
    // --- Lịch sử thay đổi ca + hộp thư của NV (chủ 28/07/2026) ---
    /** Lịch sử đổi ca cho HCNS — CẢ ô lưới (`kind=day`) lẫn ca nền (`kind=base`).
     *  Bỏ `kind` = xem cả hai. Lọc theo scope người gọi ở backend. */
    shiftChanges(token: string, opts: { year?: number; month?: number; employeeId?: number; kind?: ShiftChangeKind } = {}): Promise<{ items: ShiftChange[] }> {
      const qs = new URLSearchParams();
      if (opts.year) qs.set("year", String(opts.year));
      if (opts.month) qs.set("month", String(opts.month));
      if (opts.employeeId != null) qs.set("employee_id", String(opts.employeeId));
      if (opts.kind) qs.set("kind", opts.kind);
      return authed<{ items: ShiftChange[] }>(`/api/attendance/shift-changes?${qs.toString()}`, token);
    },
    /** Hộp thư "ca của tôi vừa bị đổi" — mọi NV có tài khoản đều gọi được.
     *  `unseen: true` = chỉ tin CHƯA ĐỌC (khối báo ở màn Công của tôi; lấy cả tin đã đọc thì
     *  khối đó bám đầu màn vĩnh viễn). */
    myShiftChanges(token: string, opts: { unseen?: boolean } = {}): Promise<{ items: ShiftChange[] }> {
      const qs = opts.unseen ? "?unseen=true" : "";
      return authed<{ items: ShiftChange[] }>(`/api/attendance/my-shift-changes${qs}`, token);
    },
    markShiftChangesSeen(token: string): Promise<AttendanceNotify> {
      return authed<AttendanceNotify>("/api/attendance/my-shift-changes/seen", token, { method: "POST" });
    },
    /** Số nuôi badge — SSE đẩy `shift_changed` thì gọi lại hàm này. */
    notifySummary(token: string): Promise<AttendanceNotify> {
      return authed<AttendanceNotify>("/api/attendance/notify-summary", token);
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

  // --- Trung tâm thông báo (chuông) -----------------------------------------
  notifications: {
    list(token: string, limit = 30): Promise<NotificationList> {
      return authed(`/api/notifications?limit=${limit}`, token);
    },
    markRead(token: string, id: number): Promise<void> {
      return authed(`/api/notifications/${id}/read`, token, { method: "POST" });
    },
    markAllRead(token: string): Promise<void> {
      return authed("/api/notifications/read-all", token, { method: "POST" });
    },
  },

  // --- Tăng ca (tang_ca) ----------------------------------------------------
  overtime: {
    mine(token: string, params?: { page?: number; size?: number }): Promise<MyOvertime> {
      return authed<MyOvertime>(`/api/overtime/me${qs(params)}`, token);
    },
    createMine(token: string, input: OvertimeInput): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>("/api/overtime/me", token,
        { method: "POST", body: JSON.stringify(input) });
    },
    updateMine(token: string, id: number, input: OvertimeInput): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/${id}`, token,
        { method: "PUT", body: JSON.stringify(input) });
    },
    createFor(token: string, input: OvertimeForInput): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>("/api/overtime", token,
        { method: "POST", body: JSON.stringify(input) });
    },
    /** `statusFilter` giữ ĐÚNG tên tham số backend (`status_filter`), đừng đổi thành `status`. */
    list(token: string, params?: {
      statusFilter?: string; employeeId?: number; page?: number; size?: number;
    }): Promise<Paged<OvertimeRequest>> {
      return authed<Paged<OvertimeRequest>>(`/api/overtime${qs({
        status_filter: params?.statusFilter,
        employee_id: params?.employeeId,
        page: params?.page,
        size: params?.size,
      })}`, token);
    },
    approve(token: string, id: number, note?: string): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/${id}/approve`, token,
        { method: "POST", body: JSON.stringify({ note: note ?? null }) });
    },
    reject(token: string, id: number, note: string): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/${id}/reject`, token,
        { method: "POST", body: JSON.stringify({ note }) });
    },
    cancel(token: string, id: number): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/${id}/cancel`, token, { method: "POST" });
    },
    bulkApprove(token: string, ids: number[]): Promise<OvertimeBulkResult> {
      return authed<OvertimeBulkResult>("/api/overtime/bulk-approve", token,
        { method: "POST", body: JSON.stringify({ ids }) });
    },
    bulkReject(token: string, ids: number[], note: string): Promise<OvertimeBulkResult> {
      return authed<OvertimeBulkResult>("/api/overtime/bulk-reject", token,
        { method: "POST", body: JSON.stringify({ ids, note }) });
    },
    summary(token: string): Promise<OvertimeSummary> {
      return authed<OvertimeSummary>("/api/overtime/summary", token);
    },
    markSeen(token: string): Promise<void> {
      return authed<void>("/api/overtime/mark-seen", token, { method: "POST" });
    },
  },

  // --- Đi muộn / về sớm / nghỉ nửa buổi (di_muon) ---------------------------
  // Cùng khuôn với `overtime` (tổ trưởng duyệt) nhưng BẢNG RIÊNG: phiếu này không bao giờ
  // lẫn vào Nghỉ phép, và không sinh tiền tăng ca.
  lateEarly: {
    mine(token: string): Promise<MyLateEarly> {
      return authed<MyLateEarly>("/api/late-early/me", token);
    },
    createMine(token: string, input: LateEarlyInput): Promise<LateEarlyRequest> {
      return authed<LateEarlyRequest>("/api/late-early/me", token,
        { method: "POST", body: JSON.stringify(input) });
    },
    updateMine(token: string, id: number, input: LateEarlyInput): Promise<LateEarlyRequest> {
      return authed<LateEarlyRequest>(`/api/late-early/${id}`, token,
        { method: "PUT", body: JSON.stringify(input) });
    },
    createFor(token: string, input: LateEarlyForInput): Promise<LateEarlyRequest> {
      return authed<LateEarlyRequest>("/api/late-early", token,
        { method: "POST", body: JSON.stringify(input) });
    },
    list(token: string, statusFilter?: string): Promise<{ items: LateEarlyRequest[] }> {
      const q = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : "";
      return authed<{ items: LateEarlyRequest[] }>(`/api/late-early${q}`, token);
    },
    approve(token: string, id: number, note?: string): Promise<LateEarlyRequest> {
      return authed<LateEarlyRequest>(`/api/late-early/${id}/approve`, token,
        { method: "POST", body: JSON.stringify({ note: note ?? null }) });
    },
    reject(token: string, id: number, note: string): Promise<LateEarlyRequest> {
      return authed<LateEarlyRequest>(`/api/late-early/${id}/reject`, token,
        { method: "POST", body: JSON.stringify({ note }) });
    },
    cancel(token: string, id: number): Promise<LateEarlyRequest> {
      return authed<LateEarlyRequest>(`/api/late-early/${id}/cancel`, token, { method: "POST" });
    },
    bulkApprove(token: string, ids: number[]): Promise<LateEarlyBulkResult> {
      return authed<LateEarlyBulkResult>("/api/late-early/bulk-approve", token,
        { method: "POST", body: JSON.stringify({ ids }) });
    },
    bulkReject(token: string, ids: number[], note: string): Promise<LateEarlyBulkResult> {
      return authed<LateEarlyBulkResult>("/api/late-early/bulk-reject", token,
        { method: "POST", body: JSON.stringify({ ids, note }) });
    },
    roster(token: string): Promise<LateEarlyRoster> {
      return authed<LateEarlyRoster>("/api/late-early/roster", token);
    },
    summary(token: string): Promise<LateEarlySummary> {
      return authed<LateEarlySummary>("/api/late-early/summary", token);
    },
    markSeen(token: string): Promise<void> {
      return authed<void>("/api/late-early/mark-seen", token, { method: "POST" });
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
    /** Không truyền `params` = trang 1, cỡ 20. Màn Chấm công gọi kiểu đó và chỉ đọc `quotas`
     *  (số dư phép năm) — `quotas` KHÔNG bị phân trang nên vẫn đúng. */
    me(token: string, params?: { page?: number; size?: number }): Promise<MyLeave> {
      return authed<MyLeave>(`/api/leaves/me${qs(params)}`, token);
    },
    create(token: string, input: LeaveRequestInput): Promise<LeaveRequest> {
      return authed<LeaveRequest>("/api/leaves", token, { method: "POST", body: JSON.stringify(input) });
    },
    cancel(token: string, id: number): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/${id}/cancel`, token, { method: "POST" });
    },
    list(token: string, params?: {
      status?: string; employeeId?: number; page?: number; size?: number;
    }): Promise<Paged<LeaveRequest>> {
      return authed<Paged<LeaveRequest>>(`/api/leaves${qs({
        status: params?.status,
        // Lọc theo 1 nhân viên chạy Ở MÁY CHỦ (từ 09/08/2026). Trước đây lọc ở client trên mảng
        // đã tải — sang phân trang thì đơn của người đó rơi ngoài trang là màn báo "chưa có đơn".
        employee_id: params?.employeeId,
        page: params?.page,
        size: params?.size,
      })}`, token);
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
    createMyAdvance(token: string, input: MyAdvanceInput): Promise<SalaryAdvance> {
      return authed<SalaryAdvance>("/api/luong/advances/me", token, { method: "POST", body: JSON.stringify(input) });
    },
    advanceNotifySummary(token: string): Promise<AdvanceNotifySummary> {
      return authed<AdvanceNotifySummary>("/api/luong/advances/notify-summary", token);
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
    // --- Tầng 3: khoản PHÁT SINH trên một dòng lương (thưởng nóng) ---
    // Khoản gán ở HỒ SƠ được trả LẶP LẠI mọi tháng; khoản ở đây CHỈ có ở kỳ này. Mỗi thao tác
    // backend tính lại NGAY dòng lương đó ⇒ số tổng của dòng đổi sau mỗi lệnh.
    lineComponents(token: string, lineId: number): Promise<{ items: LineComponent[] }> {
      return authed<{ items: LineComponent[] }>(`/api/luong/lines/${lineId}/components`, token);
    },
    addLineComponent(token: string, lineId: number, input: LineComponentInput): Promise<LineComponent> {
      return authed<LineComponent>(`/api/luong/lines/${lineId}/components`, token, { method: "POST", body: JSON.stringify(input) });
    },
    /** Chỉ sửa được dòng `source: "line"` — dòng chép từ hồ sơ backend chặn (nói rõ chỗ sửa). */
    updateLineComponent(token: string, rowId: number, patch: LineComponentPatch): Promise<LineComponent> {
      return authed<LineComponent>(`/api/luong/lines/components/${rowId}`, token, { method: "PUT", body: JSON.stringify(patch) });
    },
    deleteLineComponent(token: string, rowId: number): Promise<void> {
      return authed<void>(`/api/luong/lines/components/${rowId}`, token, { method: "DELETE" });
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
    // --- Bảng phạt đi trễ / về sớm (toàn công ty) — mirror pit-brackets ---
    latePenaltyBrackets(token: string): Promise<{ items: LatePenaltyBracket[] }> {
      return authed<{ items: LatePenaltyBracket[] }>("/api/luong/late-penalty-brackets", token);
    },
    createLatePenaltyBracket(token: string, input: LatePenaltyBracketInput): Promise<LatePenaltyBracket> {
      return authed<LatePenaltyBracket>("/api/luong/late-penalty-brackets", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateLatePenaltyBracket(token: string, id: number, input: LatePenaltyBracketInput): Promise<LatePenaltyBracket> {
      return authed<LatePenaltyBracket>(`/api/luong/late-penalty-brackets/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    deleteLatePenaltyBracket(token: string, id: number): Promise<void> {
      return authed<void>(`/api/luong/late-penalty-brackets/${id}`, token, { method: "DELETE" });
    },
    // --- Cấu hình lương: thành phần lương theo bộ phận (Tab 2) ---
    deptComponents(token: string, deptId: number): Promise<DeptComponents> {
      return authed<DeptComponents>(`/api/luong/dept-components/${deptId}`, token);
    },
    setDeptComponents(token: string, deptId: number, items: DeptComponentInput[]): Promise<DeptComponents> {
      return authed<DeptComponents>(`/api/luong/dept-components/${deptId}`, token, { method: "PUT", body: JSON.stringify({ items }) });
    },
    // --- Danh mục khoản thu nhập (Cấu hình lương, tab "Danh mục khoản thu nhập") ---
    components: {
      /** Cả khoản ĐÃ NGƯNG DÙNG cũng trả — màn cấu hình cần hiện để bật lại được. */
      list(token: string): Promise<{ items: PayrollComponent[] }> {
        return authed<{ items: PayrollComponent[] }>("/api/luong/components", token);
      },
      create(token: string, input: PayrollComponentInput): Promise<PayrollComponent> {
        return authed<PayrollComponent>("/api/luong/components", token, { method: "POST", body: JSON.stringify(input) });
      },
      update(token: string, id: number, patch: PayrollComponentPatch): Promise<PayrollComponent> {
        return authed<PayrollComponent>(`/api/luong/components/${id}`, token, { method: "PUT", body: JSON.stringify(patch) });
      },
      /** Chưa có số liệu ⇒ xoá hẳn. Đã dùng ⇒ chỉ NGỪNG ÁP DỤNG — ĐỌC `message` rồi hiện
       *  NGUYÊN VĂN, đừng tự chế câu báo. */
      remove(token: string, id: number): Promise<PayrollComponentDeleteResult> {
        return authed<PayrollComponentDeleteResult>(`/api/luong/components/${id}`, token, { method: "DELETE" });
      },
      /** NV còn giữ khoản này khi khoản ĐÃ ngừng áp dụng — nuôi cảnh báo "còn N người đang gán". */
      holders(token: string, id: number): Promise<ComponentHolders> {
        return authed<ComponentHolders>(`/api/luong/components/${id}/holders`, token);
      },
      /** Khoản ĐANG GÁN của 1 NV — CHỈ trả khoản có tiền khác 0, không phải cả danh mục.
       *  Muốn dựng dropdown "thêm khoản" thì lấy `components.list` rồi trừ đi tập này. */
      employeeValues(token: string, employeeId: number): Promise<{ items: ComponentValue[] }> {
        return authed<{ items: ComponentValue[] }>(`/api/luong/components/employee/${employeeId}`, token);
      },
      /** `amount: null` ⇒ GỠ khoản khỏi người này. Chỉ nhận `component_id` CÓ SẴN trong danh
       *  mục — không có đường đẻ khoản mới từ hồ sơ nhân viên (quy trình 2 bước). */
      setEmployeeValues(token: string, employeeId: number, items: ComponentValueInput[]): Promise<{ items: ComponentValue[] }> {
        return authed<{ items: ComponentValue[] }>(`/api/luong/components/employee/${employeeId}`, token, { method: "PUT", body: JSON.stringify({ items }) });
      },
      /** Ai đang được gán khoản này + mức bao nhiêu — cho modal gán hàng loạt XEM TRƯỚC ai bị
       *  bỏ qua / ai bị đổi từ bao nhiêu sang bao nhiêu. Khác `holders` (chỉ khoản đã tắt). */
      employeeAmounts(token: string, id: number): Promise<{ component_id: number; items: { employee_id: number; amount: number; note: string | null }[] }> {
        return authed<{ component_id: number; items: { employee_id: number; amount: number; note: string | null }[] }>(`/api/luong/components/${id}/employee-amounts`, token);
      },
      /** Rải MỘT khoản cho NHIỀU người trong một thao tác.
       *
       *  ⚠️ `overwrite` MẶC ĐỊNH FALSE và phải giữ vậy: bật lên là xoá mức riêng đã khai cho
       *  từng người, không có đường hoàn tác. Chỉ gửi `true` khi người dùng CHỦ ĐỘNG tích ô. */
      bulkAssign(token: string, id: number, input: BulkAssignInput): Promise<BulkAssignResult> {
        return authed<BulkAssignResult>(`/api/luong/components/${id}/bulk-assign`, token, { method: "POST", body: JSON.stringify(input) });
      },
    },
    /** Phát phiếu lương theo CỬA SỔ. `luc` trống = mở NGAY; `den` trống = mở không thời hạn. */
    congBo(token: string, year: number, month: number, luc?: string | null, den?: string | null): Promise<PayrollPeriod> {
      return authed<PayrollPeriod>("/api/luong/cong-bo", token, { method: "POST", body: JSON.stringify({ year, month, luc: luc ?? null, den: den ?? null }) });
    },
    thuHoi(token: string, year: number, month: number): Promise<PayrollPeriod> {
      return authed<PayrollPeriod>("/api/luong/thu-hoi", token, { method: "POST", body: JSON.stringify({ year, month }) });
    },
    /** Trả một khoản đã đè tay về đúng mức đang khai ở hồ sơ NV. `null` = khoản đã bị gỡ khỏi hồ sơ. */
    boDeComponent(token: string, rowId: number): Promise<LineComponent | null> {
      return authed<LineComponent | null>(`/api/luong/lines/components/${rowId}/bo-de`, token, { method: "POST" });
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
    khoanRates(token: string, departmentId?: number | null): Promise<{ items: PieceRate[] }> {
      const q = departmentId != null ? `?department_id=${departmentId}` : "";
      return authed<{ items: PieceRate[] }>(`/api/luong/khoan/rates${q}`, token);
    },
    /** Gợi ý cho ô "Đơn vị" = mồi mặc định ∪ đơn vị nhà máy ĐÃ dùng.
     *  ⚠️ KHÔNG phải whitelist — gõ đơn vị ngoài danh sách này vẫn lưu bình thường. */
    khoanUnits(token: string): Promise<{ items: string[] }> {
      return authed<{ items: string[] }>("/api/luong/khoan/units", token);
    },
    /** Bậc thưởng/phạt TỔ TRƯỞNG theo tỷ lệ hàng lỗi — mỗi tổ một bộ riêng. */
    leaderBrackets(token: string, departmentId: number): Promise<LeaderBracketsOut> {
      return authed<LeaderBracketsOut>(`/api/luong/khoan/leader-brackets?department_id=${departmentId}`, token);
    },
    /** Thay CẢ BỘ mốc của một tổ + ngưỡng sản lượng. Mảng rỗng = tổ không áp thưởng/phạt. */
    setLeaderBrackets(token: string, departmentId: number, items: LeaderBracketInput[],
                      minOutputQty = 0): Promise<LeaderBracketsOut> {
      return authed<LeaderBracketsOut>("/api/luong/khoan/leader-brackets", token, {
        method: "PUT",
        body: JSON.stringify({
          department_id: departmentId, items, min_output_qty: minOutputQty,
        }),
      });
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
  },

  // --- Tính giá thành — chỉ còn bình bài live; tính giá vốn đi qua phiếu (phieuTinhGia) ---
  tinhGia: {
    binhBai(token: string, body: BinhBaiIn): Promise<BinhBaiOut> {
      return authed<BinhBaiOut>("/api/tinh-gia/binh-bai", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    /** Xem-trước LIVE: chạy engine thật trên phiếu CHƯA lưu → result đầy đủ (không ghi DB). */
    preview(token: string, body: PhieuTinhGiaCreate): Promise<TinhGiaPreviewOut> {
      return authed<TinhGiaPreviewOut>("/api/tinh-gia/preview", token, {
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
    /** Nhật ký hoạt động THẬT (ai làm gì · khi nào) của phiếu tính giá này. */
    activity(token: string, id: number): Promise<{ items: PtgActivity[] }> {
      return authed<{ items: PtgActivity[] }>(`/api/phieu-tinh-gia/${id}/activity`, token);
    },
  },

  // --- Lệnh sản xuất (LSX) — bàn Kế hoạch sản xuất ---------------------------
  lsx: {
    /** Đơn Sale đã "Chuyển xuống sản xuất" mà còn dòng chưa lên lệnh. */
    hangCho(token: string): Promise<HangChoOut> {
      return authed<HangChoOut>("/api/lsx/hang-cho", token);
    },
    /** Danh sách lệnh DỰ KIẾN của 1 đơn — dẫn xuất tại chỗ, chưa ghi DB. */
    preview(token: string, orderId: number): Promise<LsxPreviewOut> {
      return authed<LsxPreviewOut>(`/api/lsx/preview/${orderId}`, token);
    },
    /** Xác nhận tạo lệnh cho các dòng đã tick. */
    tao(token: string, orderId: number, orderLineIds: number[]): Promise<LsxListOut> {
      return authed<LsxListOut>(`/api/lsx/tao/${orderId}`, token, {
        method: "POST",
        body: JSON.stringify({ order_line_ids: orderLineIds }),
      });
    },
    list(token: string, params: { order_id?: number; trang_thai?: string; q?: string } = {}): Promise<LsxListOut> {
      const qs = new URLSearchParams();
      if (params.order_id) qs.set("order_id", String(params.order_id));
      if (params.trang_thai) qs.set("trang_thai", params.trang_thai);
      if (params.q) qs.set("q", params.q);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<LsxListOut>(`/api/lsx${suffix}`, token);
    },
    get(token: string, id: number): Promise<LsxDetail> {
      return authed<LsxDetail>(`/api/lsx/${id}`, token);
    },
    phuThuocOptions(token: string, id: number): Promise<LsxPhuThuocOption[]> {
      return authed<LsxPhuThuocOption[]>(`/api/lsx/${id}/phu-thuoc-options`, token);
    },
    /** Dao chọn được cho lệnh này — server đã lọc theo KHÁCH của lệnh (chiều lọc đắt nhất), và
     *  gác bằng quyền `lenh_san_xuat.read` nên không cần cấp thêm quyền vào danh mục Khuôn.
     *  Lọc tiếp theo LOẠI của từng bước làm ở màn: danh sách đã rút còn vài dòng. */
    khuonChonDuoc(token: string, id: number): Promise<KhuonChonDuoc[]> {
      return authed<KhuonChonDuoc[]>(`/api/lsx/${id}/khuon-chon-duoc`, token);
    },
    /** Nhánh "làm dao mới" — KHÔNG gửi khách: server lấy từ chính lệnh, khỏi lệch. */
    taoKhuonChoLenh(
      token: string, id: number,
      body: { ten: string; loai: string | null; ngay_ve_du_kien: string },
    ): Promise<KhuonChonDuoc> {
      return authed<KhuonChonDuoc>(`/api/lsx/${id}/khuon-moi`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    /** Ghi nhận THỰC TẾ hàng gia công ngoài đi/về. Cửa riêng — chạy được cả khi lệnh đã lập
     *  kế hoạch, vì hàng ra cổng đúng lúc lệnh đang chạy. */
    giaoNhan(
      token: string, id: number, buocId: number,
      body: { su_kien: "giao" | "nhan"; nguoi_id?: number | null; luc?: string | null; so_luong?: number | null },
    ): Promise<LsxDetail> {
      return authed<LsxDetail>(`/api/lsx/${id}/buoc/${buocId}/giao-nhan`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    dauViecOptions(
      token: string, id: number, congDoanId: number, departmentId: number,
    ): Promise<LsxDauViecOption[]> {
      const q = new URLSearchParams({
        cong_doan_id: String(congDoanId), department_id: String(departmentId),
      });
      return authed<LsxDauViecOption[]>(`/api/lsx/${id}/dau-viec-options?${q}`, token);
    },
    update(token: string, id: number, body: LsxUpdateBody): Promise<LsxDetail> {
      return authed<LsxDetail>(`/api/lsx/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
    },
    /** REPLACE-ALL routing của LỆNH (không đụng phiếu tính giá, không ảnh hưởng lệnh khác).
     *  `lyDo` chỉ gửi khi routing đã lệch bài tính giá — server ghép vào nhật ký (§10). */
    saveRouting(
      token: string, id: number, congDoans: LsxCongDoanBody[], lyDo?: string,
    ): Promise<LsxDetail> {
      return authed<LsxDetail>(`/api/lsx/${id}/routing`, token, {
        method: "PUT",
        body: JSON.stringify({ cong_doans: congDoans, ly_do: lyDo || null }),
      });
    },
    /** Sửa thông số này thì các số máy tự tính ra bao nhiêu? CHỈ ĐỌC — server chạy đúng đường của
     *  nút Lưu rồi rollback. Có nó để màn lệnh khỏi chép công thức engine sang JS (hai bản công
     *  thức = màn hiện một số, DB lưu số khác). */
    xemTruocQuyCach(token: string, id: number, qc: LsxQuyCachBody): Promise<LsxQuyCachXemTruoc> {
      return authed<LsxQuyCachXemTruoc>(`/api/lsx/${id}/xem-truoc-quy-cach`, token, {
        method: "POST",
        body: JSON.stringify(qc),
      });
    },
    /** Gợi ý SL vào/ra cho cả chuỗi, chạy ngược từ SL thành phẩm. CHỈ ĐỌC — không ghi gì. */
    tinhNguoc(token: string, id: number): Promise<LsxTinhNguocOut> {
      return authed<LsxTinhNguocOut>(`/api/lsx/${id}/tinh-nguoc`, token);
    },
    /** Dữ liệu trung tính khi ĐỔI công đoạn (tổ phụ trách · đơn vị · chuẩn bị).
     *  Loại bước và tài nguyên là quyết định riêng của KHSX. */
    macDinhBuoc(token: string, id: number, congDoanId: number): Promise<LsxBuocMacDinh> {
      return authed<LsxBuocMacDinh>(`/api/lsx/${id}/mac-dinh-buoc/${congDoanId}`, token);
    },
    setTrangThai(token: string, id: number, trangThai: LsxTrangThai): Promise<LsxDetail> {
      return authed<LsxDetail>(`/api/lsx/${id}/trang-thai`, token, {
        method: "POST",
        body: JSON.stringify({ trang_thai: trangThai }),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`/api/lsx/${id}`, token, { method: "DELETE" });
    },
    activity(token: string, id: number): Promise<{ items: LsxActivity[] }> {
      return authed<{ items: LsxActivity[] }>(`/api/lsx/${id}/activity`, token);
    },
  },

  // --- Bài ghép (print gang) — gom công đoạn in nhiều LSX chạy chung 1 tờ ----
  baiGhep: {
    /** LSX sẵn sàng, có công đoạn in, chưa thuộc bài ghép nào. */
    hangCho(token: string, params: { giay_id?: number; q?: string } = {}): Promise<HangChoGhepOut> {
      const qs = new URLSearchParams();
      if (params.giay_id) qs.set("giay_id", String(params.giay_id));
      if (params.q) qs.set("q", params.q);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<HangChoGhepOut>(`/api/bai-ghep/hang-cho${suffix}`, token);
    },
    list(token: string): Promise<BaiGhepListOut> {
      return authed<BaiGhepListOut>("/api/bai-ghep", token);
    },
    get(token: string, id: number): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}`, token);
    },
    tao(token: string, lsxIds: number[]): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>("/api/bai-ghep", token, {
        method: "POST", body: JSON.stringify({ lsx_ids: lsxIds }),
      });
    },
    update(token: string, id: number, body: BaiGhepUpdateBody): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}`, token, {
        method: "PUT", body: JSON.stringify(body),
      });
    },
    themThanhVien(token: string, id: number, lsxIds: number[]): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}/thanh-vien`, token, {
        method: "POST", body: JSON.stringify({ lsx_ids: lsxIds }),
      });
    },
    suaThanhVien(
      token: string, id: number, tvId: number, soConTrenTo: number,
    ): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}/thanh-vien/${tvId}`, token, {
        method: "PUT", body: JSON.stringify({ so_con_tren_to: soConTrenTo }),
      });
    },
    soDo(token: string, id: number): Promise<BaiGhepSoDo> {
      return authed<BaiGhepSoDo>(`/api/bai-ghep/${id}/so-do`, token);
    },

    // --- Gộp / tách bước chạy chung (cửa ghi của lớp đè) --------------------
    /** Gộp N bước CÙNG công đoạn ở N lệnh thành một lượt chạy chung. */
    gop(token: string, id: number, stepKeys: string[]): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}/gop`, token, {
        method: "POST", body: JSON.stringify({ step_keys: stepKeys }),
      });
    },
    /** Tách lượt chung → mỗi lệnh lấy lại bước và số của chính nó (gốc chưa từng bị sửa). */
    tach(token: string, id: number, gangStepKey: string): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(
        `/api/bai-ghep/${id}/gop/${encodeURIComponent(gangStepKey)}`, token, { method: "DELETE" },
      );
    },
    /** Lập kế hoạch cho lượt chung: một tổ, một máy, một kíp, một bộ vật tư. */
    luuBuocChung(
      token: string, id: number, gangStepKey: string, body: BaiGhepBuocChungBody,
    ): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(
        `/api/bai-ghep/${id}/gop/${encodeURIComponent(gangStepKey)}`, token,
        { method: "PUT", body: JSON.stringify(body) },
      );
    },
    /** Đang chọn các bước này thì gộp thêm được bước nào — hỏi TRƯỚC khi cho bấm Gộp. */
    ungVienGop(token: string, id: number, stepKeys: string[]): Promise<BaiGhepUngVienGop> {
      return authed<BaiGhepUngVienGop>(`/api/bai-ghep/${id}/ung-vien-gop`, token, {
        method: "POST", body: JSON.stringify({ step_keys: stepKeys }),
      });
    },
    boThanhVien(token: string, id: number, tvId: number): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}/thanh-vien/${tvId}`, token, { method: "DELETE" });
    },
    setTrangThai(token: string, id: number, trangThai: BaiGhepTrangThai): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}/trang-thai`, token, {
        method: "POST", body: JSON.stringify({ trang_thai: trangThai }),
      });
    },
    remove(token: string, id: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/bai-ghep/${id}`, token, { method: "DELETE" });
    },
    activity(token: string, id: number): Promise<{ items: LsxActivity[] }> {
      return authed<{ items: LsxActivity[] }>(`/api/bai-ghep/${id}/activity`, token);
    },
  },

  // --- Kế hoạch vật tư — bảng cân đối "cần · có · thiếu · bao giờ phải đặt" ---
  keHoachVatTu: {
    canDoi(
      token: string,
      params: { q?: string; chi_thieu?: boolean } = {},
    ): Promise<CanDoiOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.chi_thieu) qs.set("chi_thieu", "true");
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<CanDoiOut>(`/api/ke-hoach-vat-tu/can-doi${suffix}`, token);
    },
    /** Gộp các dòng đã tick thành MỘT yêu cầu mua bộ phận. Server tự tính lại phần thiếu —
     *  client CỐ Ý không gửi số lượng (bản chụp trên màn có thể đã cũ). */
    deNghiMua(
      token: string,
      dong: CanDoiKhoaDong[],
      ghiChu?: string | null,
    ): Promise<{ id: number; code: string }> {
      return authed<{ id: number; code: string }>("/api/ke-hoach-vat-tu/de-nghi-mua", token, {
        method: "POST",
        body: JSON.stringify({ dong, ghi_chu: ghiChu ?? null }),
      });
    },
  },

  // --- Xếp lịch công đoạn — bàn xếp lịch (máy + giờ) của Kế hoạch sản xuất ----
  xepLich: {
    /** Order-pool "Chờ xếp": LSX độc lập + bài ghép đã sẵn sàng, CHƯA đưa vào kế hoạch. */
    hangCho(token: string): Promise<XepLichHangChoOut> {
      return authed<XepLichHangChoOut>("/api/xep-lich/hang-cho", token);
    },
    /** Bảng dòng lịch (đã đưa vào kế hoạch). `may_id`/`q` lọc phía server; màn dùng lọc client-side. */
    dong(token: string, params: { may_id?: number; q?: string } = {}): Promise<XepLichRowListOut> {
      const qs = new URLSearchParams();
      if (params.may_id) qs.set("may_id", String(params.may_id));
      if (params.q) qs.set("q", params.q);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<XepLichRowListOut>(`/api/xep-lich/dong${suffix}`, token);
    },
    duaVaoLsx(token: string, lsxId: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/xep-lich/dua-vao/lsx/${lsxId}`, token, { method: "POST" });
    },
    duaVaoBaiGhep(token: string, baiGhepId: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/xep-lich/dua-vao/bai-ghep/${baiGhepId}`, token, { method: "POST" });
    },
    goLsx(token: string, lsxId: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/xep-lich/lsx/${lsxId}`, token, { method: "DELETE" });
    },
    goBaiGhep(token: string, baiGhepId: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/xep-lich/bai-ghep/${baiGhepId}`, token, { method: "DELETE" });
    },
    /** Gán 1 dòng — chỉ gửi field cần sửa. Trả về dòng đã tính lại (finish/xung đột/trạng thái). */
    gan(token: string, dongId: number, body: XepLichGanBody): Promise<XepLichRow> {
      return authed<XepLichRow>(`/api/xep-lich/dong/${dongId}/gan`, token, {
        method: "PUT", body: JSON.stringify(body),
      });
    },
    /** Mức dùng người của từng tổ theo khoảng giờ — Gantt tô nền lane tổ theo đây (mục I).
     *  `tang_giua` = người thuộc khối SX chưa gắn tổ lá nào; họ KHÔNG vào quỹ giờ-người của tổ
     *  nào cả, nên phải hiện dòng nhắc, không thì quỹ hụt mà không ai biết vì sao. */
    taiTo(token: string): Promise<XepLichTaiToOut> {
      return authed<XepLichTaiToOut>("/api/xep-lich/to/tai", token);
    },
    /** Quân số + quỹ giờ-người của một tổ trong một ngày (mục I). */
    quanSo(token: string, deptId: number, ngay: string): Promise<XepLichQuanSo> {
      return authed<XepLichQuanSo>(`/api/xep-lich/to/${deptId}/quan-so?ngay=${ngay}`, token);
    },
    /** Gõ đè quân số một ngày. `soNguoi = null` = BỎ gõ đè, quay về số tự tính. */
    datQuanSo(token: string, deptId: number, ngay: string, soNguoi: number | null, lyDo: string) {
      return authed<XepLichQuanSo>(`/api/xep-lich/to/${deptId}/quan-so`, token, {
        method: "PUT", body: JSON.stringify({ ngay, so_nguoi: soNguoi, ly_do: lyDo }),
      });
    },
    /** Tải theo TUẦN của từng máy / tổ (mục J). `tu` = ngày bất kỳ trong tuần đầu. */
    keHoachTuan(token: string, tu: string, soTuan = 4): Promise<XepLichKeHoachTuan> {
      return authed<XepLichKeHoachTuan>(
        `/api/xep-lich/ke-hoach-tuan?tu=${tu}&so_tuan=${soTuan}`, token,
      );
    },
    /** Xem trước CHÈN lệnh gấp vào máy tại một mốc giờ (G1) — CHỈ ĐỌC, chưa ghi gì.
     *  Áp thật bằng `ganLoat` với đúng các dòng trong `rows` khi người dùng bấm Lưu. */
    chen(token: string, dongId: number, body: { may_id?: number | null; tai: string }): Promise<XepLichChen> {
      return authed<XepLichChen>(`/api/xep-lich/dong/${dongId}/chen`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Gán hàng loạt (bulk) — mỗi dòng kèm id + field cần sửa. */
    ganLoat(token: string, rows: XepLichGanLoatRow[]): Promise<XepLichRowListOut> {
      return authed<XepLichRowListOut>("/api/xep-lich/dong/gan-loat", token, {
        method: "PUT", body: JSON.stringify({ rows }),
      });
    },
    khoa(token: string, dongId: number, khoa: boolean): Promise<XepLichRow> {
      return authed<XepLichRow>(`/api/xep-lich/dong/${dongId}/khoa`, token, {
        method: "POST", body: JSON.stringify({ khoa }),
      });
    },
    moKhoa(token: string, dongId: number): Promise<XepLichRow> {
      return authed<XepLichRow>(`/api/xep-lich/dong/${dongId}/mo-khoa`, token, { method: "POST" });
    },
    goiY(token: string, dongId: number): Promise<XepLichGoiY> {
      return authed<XepLichGoiY>(`/api/xep-lich/dong/${dongId}/goi-y`, token);
    },
    /** Nền lịch máy (khoảng làm-việc theo ca + vùng khóa) cho Gantt vẽ nền + curtains. `tu`/`den` = YYYY-MM-DD. */
    lichNen(token: string, mayId: number, tu: string, den: string): Promise<XepLichLichNen> {
      const qs = new URLSearchParams({ tu, den });
      return authed<XepLichLichNen>(`/api/xep-lich/may/${mayId}/lich-nen?${qs.toString()}`, token);
    },
    /** Xem-trước-ảnh-hưởng khi kéo (đợt 4) — KHÔNG commit; trả xung đột + bước bị đẩy + nguy cơ trễ. */
    preview(token: string, dongId: number, body: XepLichPreviewBody): Promise<XepLichPreview> {
      return authed<XepLichPreview>(`/api/xep-lich/dong/${dongId}/xem-truoc`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Mọi khoảng khóa máy (mọi máy) giao [tu, den] — Gantt overlay nền bảo trì. `tu`/`den`=YYYY-MM-DD. */
    vungKhoaRange(token: string, tu: string, den: string): Promise<XepLichVungKhoaListOut> {
      const qs = new URLSearchParams({ tu, den });
      return authed<XepLichVungKhoaListOut>(`/api/xep-lich/vung-khoa?${qs.toString()}`, token);
    },
    /** Tạo khoảng khóa 1 máy (bảo trì/hỏng/nghỉ). */
    taoVungKhoa(token: string, mayId: number, body: XepLichVungKhoaIn): Promise<XepLichVungKhoaItem> {
      return authed<XepLichVungKhoaItem>(`/api/xep-lich/may/${mayId}/vung-khoa`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    xoaVungKhoa(token: string, pid: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/xep-lich/vung-khoa/${pid}`, token, { method: "DELETE" });
    },

    // --- Vấn đề kế hoạch (xung đột & nguy cơ trễ) + phát hành ---------------
    /** Danh sách xung đột & nguy cơ trễ (dẫn xuất) + tổng hợp theo mức. */
    vanDe(token: string, params: XepLichVanDeParams = {}): Promise<XepLichVanDeListOut> {
      const qs = new URLSearchParams();
      if (params.severity) qs.set("severity", params.severity);
      if (params.category) qs.set("category", params.category);
      if (params.trang_thai) qs.set("trang_thai", params.trang_thai);
      if (params.lsx_id) qs.set("lsx_id", String(params.lsx_id));
      if (params.may_id) qs.set("may_id", String(params.may_id));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<XepLichVanDeListOut>(`/api/xep-lich/van-de${suffix}`, token);
    },
    /** LSX/bài ghép đã lập kế hoạch + số xung đột CHẶN còn lại (0 = phát hành được). */
    sanSangPhatHanh(token: string): Promise<XepLichSanSangOut> {
      return authed<XepLichSanSangOut>("/api/xep-lich/san-sang-phat-hanh", token);
    },
    vanDeTiepNhan(token: string, issueKey: string): Promise<XepLichVanDeState> {
      return authed<XepLichVanDeState>("/api/xep-lich/van-de/tiep-nhan", token, {
        method: "POST", body: JSON.stringify({ issue_key: issueKey }),
      });
    },
    vanDeGiao(token: string, issueKey: string, userId: number): Promise<XepLichVanDeState> {
      return authed<XepLichVanDeState>("/api/xep-lich/van-de/giao", token, {
        method: "POST", body: JSON.stringify({ issue_key: issueKey, user_id: userId }),
      });
    },
    vanDeGhiChu(token: string, issueKey: string, note: string): Promise<XepLichVanDeState> {
      return authed<XepLichVanDeState>("/api/xep-lich/van-de/ghi-chu", token, {
        method: "POST", body: JSON.stringify({ issue_key: issueKey, note }),
      });
    },
    vanDeDanhDauXuLy(token: string, issueKey: string): Promise<XepLichVanDeState> {
      return authed<XepLichVanDeState>("/api/xep-lich/van-de/danh-dau-xu-ly", token, {
        method: "POST", body: JSON.stringify({ issue_key: issueKey }),
      });
    },
    vanDeTamHoan(token: string, issueKey: string): Promise<XepLichVanDeState> {
      return authed<XepLichVanDeState>("/api/xep-lich/van-de/tam-hoan", token, {
        method: "POST", body: JSON.stringify({ issue_key: issueKey }),
      });
    },
    /** Duyệt ngoại lệ (cần quyền PHÁT). `expiresAt`=ISO hoặc null (không hạn). */
    vanDeNgoaiLe(token: string, issueKey: string, lyDo: string, expiresAt: string | null = null): Promise<XepLichVanDeState> {
      return authed<XepLichVanDeState>("/api/xep-lich/van-de/ngoai-le", token, {
        method: "POST", body: JSON.stringify({ issue_key: issueKey, ly_do: lyDo, expires_at: expiresAt }),
      });
    },
    /** Phát hành kế hoạch (Released) — gate 0 xung đột Chặn. Cần quyền PHÁT. */
    phatHanhLsx(token: string, lsxId: number): Promise<XepLichPhatHanhOut> {
      return authed<XepLichPhatHanhOut>(`/api/xep-lich/phat-hanh/lsx/${lsxId}`, token, { method: "POST" });
    },
    phatHanhBaiGhep(token: string, baiGhepId: number): Promise<XepLichPhatHanhOut> {
      return authed<XepLichPhatHanhOut>(`/api/xep-lich/phat-hanh/bai-ghep/${baiGhepId}`, token, { method: "POST" });
    },
    /** Gỡ phát hành (G2) — BẮT BUỘC có lý do, ghi thẳng vào AuditLog.
     *  Lệnh đã xuống xưởng mà hệ chưa có lớp thực thi ⇒ nó không biết thợ chạy tới đâu; thứ duy
     *  nhất còn lại là vết ai-gỡ-lúc-nào-vì-sao. Lý do đi qua QUERY vì DELETE có body hay bị
     *  client/proxy nuốt im lặng. */
    goPhatHanhLsx(token: string, lsxId: number, lyDo: string): Promise<XepLichPhatHanhOut> {
      const qs = `?ly_do=${encodeURIComponent(lyDo)}`;
      return authed<XepLichPhatHanhOut>(`/api/xep-lich/phat-hanh/lsx/${lsxId}${qs}`, token, { method: "DELETE" });
    },
    goPhatHanhBaiGhep(token: string, baiGhepId: number, lyDo: string): Promise<XepLichPhatHanhOut> {
      const qs = `?ly_do=${encodeURIComponent(lyDo)}`;
      return authed<XepLichPhatHanhOut>(`/api/xep-lich/phat-hanh/bai-ghep/${baiGhepId}${qs}`, token, { method: "DELETE" });
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
      body: { to_status: string; cancel_reason?: string | null; row_version?: number | null; accepted_item_ids?: number[] | null },
    ): Promise<QuotationDetail> {
      return authed<QuotationDetail>(`/api/quotations/${id}/transition`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    requote(token: string, id: number, change_reason: string): Promise<QuotationDetail> {
      return authed<QuotationDetail>(`/api/quotations/${id}/requote`, token, {
        method: "POST",
        body: JSON.stringify({ change_reason }),
      });
    },
    /** Feed Hoạt động — nhật ký tương tác THẬT (ai làm gì) của báo giá này. */
    activity(token: string, id: number): Promise<{ items: QuotationActivity[] }> {
      return authed(`/api/quotations/${id}/activity`, token);
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
    /** Real-time luồng gửi duyệt: số 'chờ tôi duyệt' + số quyết định (cho báo giá của tôi) chưa xem. */
    notifySummary(token: string): Promise<QuoteNotifySummary> {
      return authed(`/api/quotations/notify-summary`, token);
    },
    /** Người soạn xác nhận đã xem các quyết định duyệt/từ chối → đóng badge/toast phía Sale. */
    markDecisionsSeen(token: string): Promise<{ ok: boolean }> {
      return authed(`/api/quotations/decisions/seen`, token, { method: "POST" });
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
    // --- Tài liệu đính kèm nội bộ (file khách gửi / mẫu thiết kế / ảnh tham khảo) ---
    attachments(token: string, id: number): Promise<{ items: QuoteAttachment[] }> {
      return authed<{ items: QuoteAttachment[] }>(`/api/quotations/${id}/attachments`, token);
    },
    uploadAttachment(token: string, id: number, file: File): Promise<QuoteAttachment> {
      const form = new FormData();
      form.append("file", file);
      return authed<QuoteAttachment>(`/api/quotations/${id}/attachments`, token, {
        method: "POST",
        body: form,
      });
    },
    deleteAttachment(token: string, id: number, attachmentId: number): Promise<void> {
      return authed<void>(`/api/quotations/${id}/attachments/${attachmentId}`, token, {
        method: "DELETE",
      });
    },
  },

  orders: {
    list(token: string, params: OrderListParams = {}): Promise<OrderListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.order_kind) qs.set("order_kind", params.order_kind);
      if (params.view_scope) qs.set("view_scope", params.view_scope);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<OrderListOut>(`/api/orders${suffix}`, token);
    },
    enums(token: string): Promise<OrderEnumsOut> {
      return authed<OrderEnumsOut>("/api/orders/enums", token);
    },
    notifySummary(token: string): Promise<OrderNotifySummary> {
      return authed<OrderNotifySummary>("/api/orders/notify-summary", token);
    },
    get(token: string, id: number): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}`, token);
    },
    create(token: string, input: OrderCreateInput): Promise<OrderDetail> {
      return authed<OrderDetail>("/api/orders", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: OrderUpdateInput): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    /** Sale đổi hint sản xuất (gấp / lưu ý SX) SAU khi đã chốt — đường hẹp (update() khóa nháp).
     *  Realtime → bàn Kế hoạch SX "ting". Field bỏ trống = giữ nguyên. */
    updateProductionHint(
      token: string, id: number, input: { is_rush?: boolean; production_note?: string },
    ): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/production-hint`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** Sale "Chuyển xuống sản xuất" — đơn đã chốt (đủ cọc) → vào hàng chờ Kế hoạch. Idempotent. */
    releaseProduction(token: string, id: number): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/release-production`, token, { method: "POST" });
    },
    activity(token: string, id: number): Promise<{ items: OrderActivity[] }> {
      return authed(`/api/orders/${id}/activity`, token);
    },
    /** V5: Kế toán lập phiếu thu cọc THẬT từ đơn (tạo PaymentReceipt received, gắn order_id). */
    addDepositReceipt(token: string, orderId: number, input: OrderDepositReceiptInput): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${orderId}/deposit-receipts`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    // `submit` / `approve` / `reject` đã XOÁ cùng luồng duyệt đơn đặc thù (3 route backend cũng gỡ).
    confirm(token: string, id: number): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/confirm`, token, { method: "POST" });
    },
    /** Việc 4: gia hạn báo giá nguồn +30 ngày (gỡ blocker hết-hạn ở cổng chốt). Quyền `update`. */
    extendQuote(token: string, id: number): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/extend-quote`, token, { method: "POST" });
    },
    cancel(token: string, id: number, reason: string, fault: string | null): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/cancel`, token, {
        method: "POST",
        body: JSON.stringify({ reason, fault }),
      });
    },
    stats(token: string, viewScope?: string): Promise<OrderStatsOut> {
      return authed<OrderStatsOut>(`/api/orders/stats${viewScope ? `?view_scope=${viewScope}` : ""}`, token);
    },
    uploadConsent(token: string, id: number, file: File): Promise<OrderDetail> {
      const form = new FormData();
      form.append("file", file);
      return authed<OrderDetail>(`/api/orders/${id}/attachments`, token, { method: "POST", body: form });
    },
    deleteConsent(token: string, id: number, attachmentId: number): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/attachments/${attachmentId}`, token, { method: "DELETE" });
    },
  },
  // --- Khuôn bế (danh mục — đọc để gán vào lệnh có bế) ----------------------
  khuonBe: {
    list(token: string, params: { q?: string; active?: boolean } = {}): Promise<{ items: KhuonBeRow[] }> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.active != null) qs.set("active", String(params.active));
      const s = qs.toString();
      return authed<{ items: KhuonBeRow[] }>(`/api/khuon-be${s ? `?${s}` : ""}`, token);
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
    itemCatalog(token: string): Promise<{ items: SupplierItemCatalogRow[] }> {
      return authed<{ items: SupplierItemCatalogRow[] }>("/api/supplier-items/catalog", token);
    },
    /** File mẫu bảng giá vật tư (blob URL). */
    itemsTemplateBlobUrl(token: string): Promise<string> {
      return blobUrl("/api/suppliers/items/template.xlsx", token);
    },
    /** Bảng giá HIỆN CÓ của đúng NCC đang mở (blob URL). */
    itemsExportBlobUrl(token: string, id: number): Promise<string> {
      return blobUrl(`/api/suppliers/${id}/items/export.xlsx`, token);
    },
    /** ĐỌC file .xlsx → mặt hàng + lỗi từng dòng. KHÔNG ghi DB: người dùng xem rồi bấm
     *  "Lưu nhà cung cấp" mới vào sổ. */
    itemsImport(token: string, file: File): Promise<SupplierItemImportOut> {
      const form = new FormData();
      form.append("file", file);
      return authed<SupplierItemImportOut>("/api/suppliers/items/import", token, {
        method: "POST",
        body: form,
      });
    },
  },

  moduleNotifications: {
    summary(token: string): Promise<ModuleNotificationSummary> {
      return authed<ModuleNotificationSummary>("/api/module-notifications/summary", token);
    },
    markRead(token: string, channel: ModuleNotificationChannel): Promise<void> {
      return authed<void>(`/api/module-notifications/${channel}/mark-read`, token, {
        method: "POST",
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
    canCreate(token: string): Promise<{ can_create: boolean }> {
      return authed<{ can_create: boolean }>("/api/department-purchase-requests/can-create", token);
    },
    create(token: string, input: DepartmentPurchaseRequestInput): Promise<DepartmentPurchaseRequestRow> {
      return authed<DepartmentPurchaseRequestRow>("/api/department-purchase-requests", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    update(token: string, id: number, input: DepartmentPurchaseRequestInput): Promise<DepartmentPurchaseRequestRow> {
      return authed<DepartmentPurchaseRequestRow>(`/api/department-purchase-requests/${id}`, token, {
        method: "PUT",
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
      params: {
        q?: string;
        status?: string | null;
        supplier_id?: number | null;
        created_from?: string | null;
        created_to?: string | null;
        needed_from?: string | null;
        needed_to?: string | null;
        expected_receipt_from?: string | null;
        expected_receipt_to?: string | null;
        deposit_status?: string | null;
        sort?: string;
        page?: number;
        size?: number;
      } = {},
    ): Promise<PurchaseRequestListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.supplier_id !== undefined && params.supplier_id !== null)
        qs.set("supplier_id", String(params.supplier_id));
      if (params.created_from) qs.set("created_from", params.created_from);
      if (params.created_to) qs.set("created_to", params.created_to);
      if (params.needed_from) qs.set("needed_from", params.needed_from);
      if (params.needed_to) qs.set("needed_to", params.needed_to);
      if (params.expected_receipt_from)
        qs.set("expected_receipt_from", params.expected_receipt_from);
      if (params.expected_receipt_to)
        qs.set("expected_receipt_to", params.expected_receipt_to);
      if (params.deposit_status) qs.set("deposit_status", params.deposit_status);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PurchaseRequestListOut>(`/api/purchase-requests${suffix}`, token);
    },
    get(token: string, id: number): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}`, token);
    },
    // Badge sidebar "Mua hàng". Rẻ (COUNT ở DB) nên gọi lại được sau mỗi sự kiện SSE.
    notifySummary(token: string): Promise<PurchaseNotifySummary> {
      return authed<PurchaseNotifySummary>("/api/purchase-requests/notify-summary", token);
    },
    create(token: string, input: PurchaseRequestInput): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>("/api/purchase-requests", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** Tách phiếu theo NCC: mỗi dòng mang `supplier_id`, backend nhóm lại rồi đẻ N phiếu TRONG
     *  MỘT LẦN. Đừng gọi `create` nhiều lần — phiếu đầu giữ chỗ yêu cầu nguồn, lần sau bị chặn. */
    createBatch(
      token: string,
      input: PurchaseRequestBatchInput,
    ): Promise<{ items: PurchaseRequestRow[]; total: number }> {
      return authed<{ items: PurchaseRequestRow[]; total: number }>(
        "/api/purchase-requests/batch",
        token,
        { method: "POST", body: JSON.stringify(input) },
      );
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
    markReceived(
      token: string,
      id: number,
      lines: ReceivedLineInput[] = [],
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/mark-received`, token, {
        method: "POST",
        body: JSON.stringify({ lines }),
      });
    },
    /** Sửa số thực nhận SAU khi đã nhận (NCC giao nhiều đợt). Đòi quyền duyệt ở server. */
    updateReceivedQuantities(
      token: string,
      id: number,
      lines: ReceivedLineInput[],
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/received-quantities`, token, {
        method: "PUT",
        body: JSON.stringify({ lines }),
      });
    },
    /** Lùi "Đã nhận hàng" về "Đã mua". Bắt buộc có lý do; server chặn nếu đã có phiếu chi ĐÃ CHI. */
    undoReceived(token: string, id: number, reason: string): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/undo-received`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },
    cancel(token: string, id: number, reason: string | null): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/cancel`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },

    // --- Đợt giao ---------------------------------------------------------
    // Mọi endpoint dưới đây trả về NGUYÊN phiếu mua sau khi sửa (không phải riêng đợt): trạng thái
    // phiếu, công nợ và trần lập phiếu chi đều đổi theo đợt giao, nên trả nửa vời là màn hình cầm
    // số cũ. Cứ thay cả dòng bằng kết quả.

    /** Ghi một đợt giao mới. Chỉ chạy khi phiếu ở "Đã mua" / "Giao một phần". */
    createDelivery(
      token: string,
      id: number,
      input: PurchaseDeliveryInput,
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/deliveries`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** Sửa đợt giao. Bỏ `lines` = giữ nguyên dòng hàng, chỉ đổi ngày/hạn/hoá đơn.
     *  Server CHẶN nếu đợt đã có phiếu chi gắn vào — tiền đã ra thì không đổi số hàng dưới chân. */
    updateDelivery(
      token: string,
      id: number,
      deliveryId: number,
      input: PurchaseDeliveryInput,
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(
        `/api/purchase-requests/${id}/deliveries/${deliveryId}`,
        token,
        { method: "PUT", body: JSON.stringify(input) },
      );
    },
    deleteDelivery(
      token: string,
      id: number,
      deliveryId: number,
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(
        `/api/purchase-requests/${id}/deliveries/${deliveryId}`,
        token,
        { method: "DELETE" },
      );
    },
    /** Gán MỘT hoá đơn cho NHIỀU đợt cùng lúc — gõ lại số ba lần là hệ hiểu thành ba hoá đơn. */
    assignInvoice(
      token: string,
      id: number,
      input: PurchaseInvoiceAssignInput,
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/invoice`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** "Đóng đơn (không giao nữa)" — chốt số thực nhận = số đã giao. Bắt lý do; server đòi
     *  `thu_mua:approve` vì nó cắt phần hàng chưa về ra khỏi công nợ. */
    close(token: string, id: number, reason: string): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/close`, token, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
    },
    /** Số hợp đồng + cọc dự kiến. Tách khỏi `update` vì hợp đồng thường ký SAU khi phiếu đã duyệt. */
    updateContract(
      token: string,
      id: number,
      input: PurchaseContractInput,
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(`/api/purchase-requests/${id}/contract`, token, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },
    supplierCredit(token: string, id: number): Promise<SupplierCredit> {
      return authed<SupplierCredit>(
        `/api/purchase-requests/${id}/supplier-credit`,
        token,
      );
    },
    /** Đính ảnh/PDF (≤10 MB). `deliveryId` bỏ trống = tài liệu của cả phiếu (hợp đồng). */
    uploadAttachment(
      token: string,
      id: number,
      file: File,
      kind: PurchaseAttachmentKind = "khac",
      deliveryId?: number | null,
    ): Promise<PurchaseRequestRow> {
      const qs = new URLSearchParams({ kind });
      if (deliveryId != null) qs.set("delivery_id", String(deliveryId));
      const form = new FormData();
      form.append("file", file);
      return authed<PurchaseRequestRow>(
        `/api/purchase-requests/${id}/attachments?${qs.toString()}`,
        token,
        { method: "POST", body: form },
      );
    },
    deleteAttachment(
      token: string,
      id: number,
      attachmentId: number,
    ): Promise<PurchaseRequestRow> {
      return authed<PurchaseRequestRow>(
        `/api/purchase-requests/${id}/attachments/${attachmentId}`,
        token,
        { method: "DELETE" },
      );
    },
  },

  // --- Kế toán: duyệt mua hàng, Phiếu chi / UNC ---------------------------
  accounting: {
    inbox(
      token: string,
      params: {
        q?: string;
        status?: string | null;
        supplier_id?: number | null;
        created_from?: string | null;
        created_to?: string | null;
        needed_from?: string | null;
        needed_to?: string | null;
        expected_receipt_from?: string | null;
        expected_receipt_to?: string | null;
        deposit_status?: string | null;
        sort?: string;
        page?: number;
        size?: number;
      } = {},
    ): Promise<PurchaseRequestListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.supplier_id != null) qs.set("supplier_id", String(params.supplier_id));
      if (params.created_from) qs.set("created_from", params.created_from);
      if (params.created_to) qs.set("created_to", params.created_to);
      if (params.needed_from) qs.set("needed_from", params.needed_from);
      if (params.needed_to) qs.set("needed_to", params.needed_to);
      if (params.expected_receipt_from)
        qs.set("expected_receipt_from", params.expected_receipt_from);
      if (params.expected_receipt_to)
        qs.set("expected_receipt_to", params.expected_receipt_to);
      if (params.deposit_status) qs.set("deposit_status", params.deposit_status);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PurchaseRequestListOut>(`/api/accounting/inbox${suffix}`, token);
    },
    /** Công nợ phải trả gom theo NCC. Không phân trang — cắt trang là ra TỔNG sai.
        `q` lọc ở SERVER: NCC đã trả hết và im lặng lâu thì không có dòng nào để lọc phía màn. */
    payables(
      token: string,
      params: { q?: string; filter?: string; page?: number; size?: number } = {},
    ): Promise<PayablesSummary> {
      const qs = new URLSearchParams();
      if (params.q?.trim()) qs.set("q", params.q.trim());
      if (params.filter && params.filter !== "all") qs.set("filter", params.filter);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PayablesSummary>(`/api/accounting/payables${suffix}`, token);
    },
    /** `allHistory` bỏ mốc kỳ cho rổ "đã chi" — nút "Xem lịch sử cũ hơn". Chỉ nới cho MỘT NCC. */
    payablesDetail(
      token: string,
      supplierId: number,
      allHistory = false,
    ): Promise<PayablesDetail> {
      const suffix = allHistory ? "?all_history=true" : "";
      return authed<PayablesDetail>(`/api/accounting/payables/${supplierId}${suffix}`, token);
    },
    receivables(
      token: string,
      params: { q?: string; filter?: string; page?: number; size?: number } = {},
    ): Promise<ReceivablesSummary> {
      const qs = new URLSearchParams();
      if (params.q?.trim()) qs.set("q", params.q.trim());
      if (params.filter && params.filter !== "all") qs.set("filter", params.filter);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<ReceivablesSummary>(`/api/accounting/receivables${suffix}`, token);
    },
    receivablesDetail(
      token: string,
      customerId: number,
      allHistory = false,
    ): Promise<ReceivablesDetail> {
      const suffix = allHistory ? "?all_history=true" : "";
      return authed<ReceivablesDetail>(`/api/accounting/receivables/${customerId}${suffix}`, token);
    },
    salesInvoices(token: string, orderId: number): Promise<SalesInvoiceListOut> {
      return authed<SalesInvoiceListOut>(
        `/api/accounting/sales-invoices?order_id=${orderId}`,
        token,
      );
    },
    createSalesInvoice(
      token: string,
      input: SalesInvoiceInput,
    ): Promise<SalesInvoiceRow> {
      return authed<SalesInvoiceRow>("/api/accounting/sales-invoices", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    cancelSalesInvoice(
      token: string,
      invoiceId: number,
      reason: string,
    ): Promise<SalesInvoiceRow> {
      return authed<SalesInvoiceRow>(
        `/api/accounting/sales-invoices/${invoiceId}/cancel`,
        token,
        { method: "POST", body: JSON.stringify({ reason }) },
      );
    },
    createSalesInvoiceReceipt(
      token: string,
      invoiceId: number,
      input: PaymentReceiptInput,
    ): Promise<PaymentReceiptRow> {
      return authed<PaymentReceiptRow>(
        `/api/accounting/sales-invoices/${invoiceId}/receipts`,
        token,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    companyAccounts(
      token: string,
      activeOnly = false,
      usage?: "receive" | "pay" | null,
    ): Promise<CompanyBankAccountRow[]> {
      const qs = new URLSearchParams();
      qs.set("active_only", String(activeOnly));
      if (usage) qs.set("usage", usage);
      return authed<CompanyBankAccountRow[]>(
        `/api/accounting/company-bank-accounts?${qs.toString()}`,
        token,
      );
    },
    createCompanyAccount(token: string, input: CompanyBankAccountInput): Promise<CompanyBankAccountRow> {
      return authed<CompanyBankAccountRow>("/api/accounting/company-bank-accounts", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateCompanyAccount(token: string, id: number, input: CompanyBankAccountInput): Promise<CompanyBankAccountRow> {
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
        source_type?: PaymentVoucherSource | null;
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
      if (params.source_type) qs.set("source_type", params.source_type);
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
    // ĐÃ GỠ 07/08/2026 — `updateVoucher`. Phiếu chi phát hành ra là tiền đã rời két, không
    // sửa; endpoint PUT bên server cũng đã gỡ. Sai thì `cancelVoucher` rồi lập phiếu mới.
    // ĐÃ GỠ 06/08/2026 — `markVoucherPaid()` (`POST .../mark-paid`). Lập phiếu chi NAY LÀ hành vi
    // chi tiền, không còn khoảng "chờ chi" ở giữa để mà xác nhận (Đ1). Endpoint đã bị gỡ khỏi
    // backend; gọi lại là 404.
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
        source_type?: PaymentReceiptSource | null;
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
      if (params.source_type) qs.set("source_type", params.source_type);
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
    createOtherReceipt(token: string, input: PaymentReceiptInput): Promise<PaymentReceiptRow> {
      return authed<PaymentReceiptRow>(`/api/accounting/payment-receipts`, token, {
        method: "POST",
        body: JSON.stringify(input),
      });
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

  // --- Sản xuất: Lệnh sản xuất (LSX) ---------------------------------------

  // --- Công đoạn (danh mục, lite cho dropdown) -----------------------------
  congDoan: {
    // size ≤ 200 — router chặn `le=200`, gửi 500 là 422 (đừng nâng lại).
    list(token: string): Promise<{ items: CongDoanLite[] }> {
      return authed<{ items: CongDoanLite[] }>("/api/cong-doan?size=200", token);
    },
  },

  // --- Kho: đề nghị · phiếu nhập/xuất · ngưỡng tồn (spec-kho-de-nghi) -------
  // Gom 3 prefix `/api/kho/de-nghi`, `/api/kho/phieu`, `/api/kho/nguong-ton` vào một
  // namespace vì chúng là MỘT luồng (đề nghị → phiếu → lô). Khai báo kho (`/api/kho`) vẫn
  // đi qua `crud()` của rebuildCatalog — đó là danh mục, không phải chứng từ.
  /** DANH MỤC GỐC — hai cửa Kho + NCC dùng chung để chọn mặt hàng và chọn đơn vị.
   *  Thay `kho.deNghi.vatTu` cũ (đọc bảng `materials` riêng của kho). */
  matHang: {
    tim(
      token: string,
      q?: string | null,
      size = 20,
      chiCoNhaCungCap = false,
    ): Promise<MatHangOption[]> {
      const qs = new URLSearchParams({ size: String(size) });
      if (q) qs.set("q", q);
      if (chiCoNhaCungCap) qs.set("chi_co_nha_cung_cap", "true");
      return authed<MatHangOption[]>(`/api/vat-lieu-kho/mat-hang?${qs.toString()}`, token);
    },
    /** Đơn vị gốc + mọi đơn vị đổi được — danh sách TỰ THÍCH NGHI theo từng mặt hàng. */
    donVi(token: string, hangLoai: HangLoai, hangId: number): Promise<DonViCuaMatHang> {
      return authed<DonViCuaMatHang>(
        `/api/vat-lieu-kho/mat-hang/${hangLoai}/${hangId}/don-vi`, token,
      );
    },
    /** Các NCC bán mặt hàng này, giá đã quy về đơn vị gốc — rẻ nhất đứng đầu. */
    soGia(token: string, hangLoai: HangLoai, hangId: number): Promise<SoGiaOut> {
      const qs = new URLSearchParams({ hang_loai: hangLoai, hang_id: String(hangId) });
      return authed<SoGiaOut>(`/api/supplier-items/so-gia?${qs.toString()}`, token);
    },
    /** Gắn/đổi ẢNH minh hoạ mặt hàng (chỉ vai có quyền sửa danh mục dm_giay/dm_vat_tu). */
    uploadAnh(token: string, hangLoai: HangLoai, hangId: number, file: File): Promise<{ anh_url: string | null }> {
      const form = new FormData();
      form.append("file", file);
      return authed<{ anh_url: string | null }>(
        `/api/vat-lieu-kho/${hangLoai}/${hangId}/anh`, token, { method: "POST", body: form },
      );
    },
    /** Gỡ ảnh minh hoạ mặt hàng. */
    xoaAnh(token: string, hangLoai: HangLoai, hangId: number): Promise<{ anh_url: string | null }> {
      return authed<{ anh_url: string | null }>(
        `/api/vat-lieu-kho/${hangLoai}/${hangId}/anh`, token, { method: "DELETE" },
      );
    },
  },

  kho: {
    deNghi: {
      /** Số yêu cầu ĐÃ DUYỆT chờ kho lập phiếu (badge Nhập/Xuất, việc của thủ kho) + phản hồi kho cho
       *  yêu cầu CỦA TÔI mà tôi chưa mở xem: `done_unseen` (Hoàn tất) + `fail_unseen` (Không thành).
       *  Badge người tạo = done_unseen + fail_unseen. */
      counts(
        token: string,
      ): Promise<{ nhap: number; xuat: number; done_unseen: number; fail_unseen: number }> {
        return authed("/api/kho/de-nghi/counts", token);
      },
      /** NGƯỜI TẠO mở xem 1 yêu cầu của mình → đánh dấu đã xem → hạ badge/số đỏ đúng yêu cầu đó. */
      markSeen(token: string, id: number): Promise<void> {
        return authed(`/api/kho/de-nghi/${id}/seen`, token, { method: "POST" });
      },
      list(token: string, params: StockRequestListParams = {}): Promise<StockRequestPage> {
        const qs = new URLSearchParams();
        if (params.q) qs.set("q", params.q);
        if (params.loai) qs.set("loai", params.loai);
        // `trang_thai` là list ở backend → lặp param, KHÔNG nối bằng dấu phẩy.
        for (const s of params.trang_thai ?? []) qs.append("trang_thai", s);
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.page) qs.set("page", String(params.page));
        if (params.size) qs.set("size", String(params.size));
        const suffix = qs.toString() ? `?${qs.toString()}` : "";
        return authed<StockRequestPage>(`/api/kho/de-nghi${suffix}`, token);
      },
      get(token: string, id: number, khoId?: number | null): Promise<StockRequest> {
        const suffix = khoId != null ? `?kho_id=${khoId}` : "";
        return authed<StockRequest>(`/api/kho/de-nghi/${id}${suffix}`, token);
      },
      create(token: string, body: StockRequestInput): Promise<StockRequest> {
        return authed<StockRequest>("/api/kho/de-nghi", token, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
      update(token: string, id: number, body: StockRequestUpdateInput): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}`, token, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      },
      submit(token: string, id: number): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}/trinh-duyet`, token, { method: "POST" });
      },
      /** `approved_qty`: line_id → SL duyệt. Gửi cho MỌI dòng (0 = không duyệt dòng đó). */
      approve(token: string, id: number, approvedQty: Record<number, number>): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}/duyet`, token, {
          method: "POST",
          body: JSON.stringify({ approved_qty: approvedQty }),
        });
      },
      reject(token: string, id: number, lyDo: string): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}/tu-choi`, token, {
          method: "POST",
          body: JSON.stringify({ ly_do: lyDo }),
        });
      },
      cancel(token: string, id: number): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}/huy`, token, { method: "POST" });
      },
      /** Kho HỦY đề nghị (quyết định KHÔNG lập phiếu) — kèm lý do; gác `create`. */
      cancelByKho(token: string, id: number, lyDo: string): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}/huy-kho`, token, {
          method: "POST",
          body: JSON.stringify({ ly_do: lyDo }),
        });
      },
      /** Kho bấm "Tiếp nhận" (gác bằng `create`, không phải `approve` — kho không duyệt). */
      receive(token: string, id: number): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}/tiep-nhan`, token, { method: "POST" });
      },
      prepare(token: string, id: number): Promise<StockRequest> {
        return authed<StockRequest>(`/api/kho/de-nghi/${id}/chuan-bi`, token, { method: "POST" });
      },
      /** Gợi ý SL từ lịch sử đề nghị của bộ phận; `so_luong === null` = chưa đủ dữ liệu. */
      goiYSoLuong(
        token: string, hangLoai: HangLoai, hangId: number,
      ): Promise<{ so_luong: number | null }> {
        const qs = new URLSearchParams({ hang_loai: hangLoai, hang_id: String(hangId) });
        return authed<{ so_luong: number | null }>(
          `/api/kho/de-nghi/goi-y/so-luong?${qs.toString()}`, token,
        );
      },
    },

    phieu: {
      list(token: string, params: StockVoucherListParams = {}): Promise<StockVoucherPage> {
        const qs = new URLSearchParams();
        if (params.q) qs.set("q", params.q);
        if (params.loai) qs.set("loai", params.loai);
        if (params.trang_thai) qs.set("trang_thai", params.trang_thai);
        if (params.request_id != null) qs.set("request_id", String(params.request_id));
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.page) qs.set("page", String(params.page));
        if (params.size) qs.set("size", String(params.size));
        const suffix = qs.toString() ? `?${qs.toString()}` : "";
        return authed<StockVoucherPage>(`/api/kho/phieu${suffix}`, token);
      },
      get(token: string, id: number): Promise<StockVoucher> {
        return authed<StockVoucher>(`/api/kho/phieu/${id}`, token);
      },
      create(token: string, body: StockVoucherInput): Promise<StockVoucher> {
        return authed<StockVoucher>("/api/kho/phieu", token, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
      /** Ghi sổ — điểm DUY NHẤT tồn kho thay đổi; sau đó phiếu không sửa được nữa. */
      ghiSo(token: string, id: number): Promise<StockVoucher> {
        return authed<StockVoucher>(`/api/kho/phieu/${id}/ghi-so`, token, { method: "POST" });
      },
      /** Hủy phiếu nháp — BẮT BUỘC lý do; đề nghị chuyển "Đã hủy" kèm lý do (kết thúc). */
      huy(token: string, id: number, lyDo: string): Promise<StockVoucher> {
        return authed<StockVoucher>(`/api/kho/phieu/${id}/huy`, token, {
          method: "POST",
          body: JSON.stringify({ ly_do: lyDo }),
        });
      },
      /** Sửa VỊ TRÍ cất lô (kệ/ô) — từ drawer Lịch sử của sản phẩm. Quyền `create` (thủ kho). */
      suaViTriLo(
        token: string,
        lotId: number,
        viTri: string | null,
      ): Promise<{ id: number; vi_tri: string | null }> {
        return authed<{ id: number; vi_tri: string | null }>(
          `/api/kho/phieu/lo/${lotId}/vi-tri`,
          token,
          { method: "PATCH", body: JSON.stringify({ vi_tri: viTri }) },
        );
      },
      /** Gợi ý lấy hàng từ lô nào (FEFO → FIFO). `thieu` > 0 = kho không đủ hàng. */
      goiYLo(
        token: string,
        params: { hang_loai: HangLoai; hang_id: number; kho_id: number; so_luong: number },
      ): Promise<StockAllocation> {
        // `so_luong` ở ĐƠN VỊ GỐC — lô lưu theo đơn vị đó, gửi số theo đơn vị người khai là lệch.
        const qs = new URLSearchParams({
          hang_loai: params.hang_loai,
          hang_id: String(params.hang_id),
          kho_id: String(params.kho_id),
          so_luong: String(params.so_luong),
        });
        return authed<StockAllocation>(`/api/kho/phieu/lo/goi-y?${qs.toString()}`, token);
      },
      danhSachLo(
        token: string,
        params: { hang_loai?: HangLoai | null; hang_id?: number | null; kho_id?: number | null; con_hang?: boolean },
      ): Promise<StockLot[]> {
        const qs = new URLSearchParams();
        if (params.hang_loai && params.hang_id != null) {
          qs.set("hang_loai", params.hang_loai);
          qs.set("hang_id", String(params.hang_id));
        }
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        qs.set("con_hang", String(params.con_hang ?? true));
        return authed<StockLot[]>(`/api/kho/phieu/lo/danh-sach?${qs.toString()}`, token);
      },
      /** Lịch sử Nhập (lô) + Xuất (dòng phiếu xuất đã ghi sổ) của 1 mã hàng tại 1 kho. */
      lichSuVatTu(
        token: string,
        hangLoai: HangLoai,
        hangId: number,
        khoId: number,
      ): Promise<StockMaterialHistory> {
        const qs = new URLSearchParams({ kho_id: String(khoId) });
        return authed<StockMaterialHistory>(
          `/api/kho/phieu/mat-hang/${hangLoai}/${hangId}/lich-su?${qs.toString()}`,
          token,
        );
      },
      /** Mã QR đã ký cho tem dán kệ (in tem CẦN đăng nhập). FE nhúng vào link `#s=<token>`. */
      qrToken(
        token: string,
        khoId: number,
        hangLoai: HangLoai,
        hangId: number,
      ): Promise<{ token: string }> {
        const qs = new URLSearchParams({ kho_id: String(khoId) });
        return authed<{ token: string }>(
          `/api/kho/phieu/mat-hang/${hangLoai}/${hangId}/qr-token?${qs.toString()}`,
          token,
        );
      },
      // --- Đính kèm hóa đơn/chứng từ gốc (ảnh hoặc PDF, ≤10MB) ---
      attachments(token: string, id: number): Promise<{ items: StockVoucherAttachment[] }> {
        return authed<{ items: StockVoucherAttachment[] }>(`/api/kho/phieu/${id}/attachments`, token);
      },
      uploadAttachment(token: string, id: number, file: File): Promise<StockVoucherAttachment> {
        const form = new FormData();
        form.append("file", file);
        return authed<StockVoucherAttachment>(`/api/kho/phieu/${id}/attachments`, token, {
          method: "POST",
          body: form,
        });
      },
      deleteAttachment(token: string, id: number, attachmentId: number): Promise<void> {
        return authed<void>(`/api/kho/phieu/${id}/attachments/${attachmentId}`, token, {
          method: "DELETE",
        });
      },
      /** Xuất Excel báo cáo tồn kho chi tiết (kế toán) — fetch as blob (bearer + refresh-aware). */
      async exportXlsxBlobUrl(token: string, khoId?: number | null, conHang = true): Promise<string> {
        const qs = new URLSearchParams();
        if (khoId != null) qs.set("kho_id", String(khoId));
        qs.set("con_hang", String(conHang));
        const doFetch = (bearer: string) =>
          fetch(`${BASE_URL}/api/kho/phieu/lo/export.xlsx?${qs.toString()}`, {
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
    },

    nguongTon: {
      list(token: string): Promise<StockThreshold[]> {
        return authed<StockThreshold[]>("/api/kho/nguong-ton", token);
      },
      upsert(token: string, body: StockThresholdInput): Promise<StockThreshold> {
        return authed<StockThreshold>("/api/kho/nguong-ton", token, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      },
    },

    /** Báo cáo kho (kế toán) — sổ nhập-xuất + khóa kỳ + export MISA. Cần quyền close_book. */
    baoCao: {
      dong(token: string, params: BaoCaoKhoParams = {}): Promise<BaoCaoKhoPage> {
        const qs = new URLSearchParams();
        if (params.tu) qs.set("tu", params.tu);
        if (params.den) qs.set("den", params.den);
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.loai) qs.set("loai", params.loai);
        if (params.q) qs.set("q", params.q);
        const q = qs.toString();
        return authed<BaoCaoKhoPage>(`/api/kho/bao-cao/dong${q ? `?${q}` : ""}`, token);
      },
      khoaSo(token: string): Promise<KhoKhoaSoRow[]> {
        return authed<KhoKhoaSoRow[]>("/api/kho/khoa-so", token);
      },
      /** Các kỳ CÒN đang khóa (đã gộp khoảng) — cho tab "Kỳ đã khóa". */
      ky(token: string): Promise<KhoaSoKyRow[]> {
        return authed<KhoaSoKyRow[]>("/api/kho/khoa-so/ky", token);
      },
      setKhoaSo(token: string, body: KhoKhoaSoInput): Promise<KhoKhoaSoRow> {
        return authed<KhoKhoaSoRow>("/api/kho/khoa-so", token, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
      /** Xuất Excel báo cáo kho theo mẫu MISA (nhập/xuất) — fetch as blob (bearer + refresh-aware). */
      async exportXlsxBlobUrl(
        token: string,
        loai: StockRequestKind,
        params: Omit<BaoCaoKhoParams, "loai"> = {},
      ): Promise<string> {
        const qs = new URLSearchParams();
        qs.set("loai", loai);
        if (params.tu) qs.set("tu", params.tu);
        if (params.den) qs.set("den", params.den);
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.q) qs.set("q", params.q);
        const doFetch = (bearer: string) =>
          fetch(`${BASE_URL}/api/kho/bao-cao/export.xlsx?${qs.toString()}`, {
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
    },
  },

  /** Endpoint CÔNG KHAI — tra kho khi quét tem QR (KHÔNG đăng nhập, KHÔNG giá vốn). */
  public: {
    khoScan(scanToken: string): Promise<PublicScan> {
      const qs = new URLSearchParams({ t: scanToken });
      return request<PublicScan>(`/api/public/kho-scan?${qs.toString()}`);
            },
    },

  // --- Danh mục tài liệu nội quy: chỉ Xem / Thêm / Xóa ----------------------
  noiQuy: {
    /** `q` tìm ở MÁY CHỦ (mã / tên / tên file / ghi chú / người upload) — trước 09/08/2026 lọc
     *  ở client trên trọn bảng, nay bảng đã phân trang nên lọc client chỉ soi được 1 trang. */
    list(token: string, params?: { q?: string; page?: number; size?: number }):
      Promise<Paged<NoiQuyRecord>> {
      return authed<Paged<NoiQuyRecord>>(`/api/noi-quy${qs(params)}`, token);
    },
    create(token: string, input: { name: string; note?: string; file: File }): Promise<NoiQuyRecord> {
      const form = new FormData();
      form.append("name", input.name);
      form.append("note", input.note ?? "");
      form.append("file", input.file);
      return authed<NoiQuyRecord>("/api/noi-quy", token, {
        method: "POST",
        body: form,
      });
    },
    delete(token: string, recordId: number): Promise<void> {
      return authed<void>(`/api/noi-quy/${recordId}`, token, {
        method: "DELETE",
      });
    },
  },

};

/** Dữ liệu tra kho CÔNG KHAI (quét tem QR). KHÔNG có trường tiền (giá vốn/đơn giá). */
export interface PublicScanLot {
  ma_lo: string | null;
  ngay_nhap: string;
  hsd: string | null;
  vi_tri: string | null;
  sl_con_lai: number;
}

/** 1 lần nhập/xuất gần đây (công khai — KHÔNG có tiền). */
export interface PublicScanMove {
  loai: string; // NHAP / XUAT
  ngay: string | null;
  so_ct: string;
  so_luong: number;
}

export interface PublicScan {
  material_code: string | null;
  material_name: string | null;
  dvt: string | null;
  kho_ten: string | null;
  on_hand: number;
  /** Đường ảnh CÔNG KHAI (`/api/public/vat-lieu-anh?t=…`, serve bằng token QR). null = chưa có ảnh. */
  anh_url: string | null;
  lots: PublicScanLot[];
  history: PublicScanMove[];
}

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
