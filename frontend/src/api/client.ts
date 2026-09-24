// API client — the ONLY module that knows backend URLs, request/response shapes,
// and error mapping (docs/ARCHITECTURE.md). Components/hooks call these functions,
// never fetch() directly.

// Hình dạng kết quả nhập Excel là CHUNG cho mọi màn (13 danh mục + Hồ sơ nhân sự) nên khai một
// chỗ ở `rebuildCatalog`. `import type` ⇒ TS xoá lúc build, không đẻ vòng import lúc chạy.
import type { ImportExcelOut } from "./rebuildCatalog";

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
    /** `detail` THÔ đã parse từ thân lỗi (chuỗi | mảng 422 | object). Đa số màn chỉ cần `message`,
     *  nhưng vài endpoint trả detail dạng OBJECT có cấu trúc (vd Xếp lịch 2 khi CHẶN đặt lịch:
     *  `{loai:"chan_dat_lich", van_de:[...]}`) — giữ bản thô để nơi gọi bóc được danh sách vấn đề,
     *  phân biệt với 409 khoá-lạc-quan (detail là CHUỖI). */
    readonly detail?: unknown,
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
    const { text, raw } = await safeDetail(resp);
    throw new ApiError(text ?? `Request failed (${resp.status}).`, resp.status, raw);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

async function safeDetail(resp: Response): Promise<{ text: string | null; raw: unknown }> {
  try {
    const body = await resp.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return { text: detail, raw: detail };
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
        const text =
          ds.slice(0, 3).join(" · ") + (ds.length > 3 ? ` (+${ds.length - 3} lỗi nữa)` : "");
        return { text, raw: detail };
      }
    }
    // Object detail có cấu trúc (vd `{loai, van_de}`): không dựng được câu ngắn ⇒ text = null (nơi
    // gọi tự bóc `raw`), nhưng VẪN trả `raw` để không mất dữ liệu.
    return { text: null, raw: detail };
  } catch {
    /* non-JSON error body */
  }
  return { text: null, raw: undefined };
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

let refreshInFlight: Promise<LoginResponse | null> | null = null;
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

/** Khoá Web Locks dùng chung mọi tab cùng origin. */
const REFRESH_LOCK = "svn-auth-refresh";

/** Đổi refresh cookie lấy phiên mới — ĐƯỜNG DUY NHẤT gọi `/api/auth/refresh`.
 *
 *  Máy chủ xoay token mỗi lượt và coi token cũ bị dùng lại là bị trộm ⇒ thu hồi CẢ HỌ token, người
 *  dùng văng ra màn đăng nhập. Hai lượt mang cùng một cookie bay song song là đủ dính: StrictMode
 *  chạy effect khôi phục phiên hai lần, lượt khôi phục đè lên lượt làm mới vì 401, hai tab hết hạn
 *  access token cùng lúc. DB dev ngày 14/09/2026 có 5 họ token bị giết đúng kiểu này. Nên:
 *    · trong một tab: mọi nơi gọi dùng chung một promise đang bay;
 *    · giữa các tab: xếp hàng qua Web Locks — tab sau chạy khi cookie đã là token mới.
 *  Trả `null` khi máy chủ TỪ CHỐI refresh token (đã báo `onSessionEnded`). Lỗi TẠM (xem
 *  `hetPhienThat`) thì promise REJECT với chính lỗi đó, phiên giữ nguyên để nơi gọi thử lại. */
export function refreshSession(): Promise<LoginResponse | null> {
  if (!refreshInFlight) {
    const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
    const goi = () => api.refresh();
    // `await` để gỡ tầng Promise lồng: kiểu của `locks.request` là Promise<T> với T = Promise<...>.
    const chay = async (): Promise<LoginResponse> =>
      locks ? await locks.request(REFRESH_LOCK, goi) : goi();
    refreshInFlight = chay()
      .then((res) => {
        onAccessToken(res.access_token);
        return res;
      })
      .catch((err: unknown) => {
        if (!hetPhienThat(err)) throw err;
        onSessionEnded();
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/** Lượt /refresh hỏng vì máy chủ TRẢ LỜI từ chối (4xx: cookie thiếu/hết hạn/bị thu hồi/dùng lại)
 *  mới là hết phiên. Không tới được máy chủ (status 0 — BE đang khởi động lại, rớt mạng), 5xx,
 *  408, 429 là lỗi tạm: cookie vẫn nguyên. Trước đây bắt MỌI lỗi thành hết phiên ⇒ tải lại trang
 *  đúng lúc restart BE là văng ra màn đăng nhập dù phiên còn sống. */
function hetPhienThat(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  return err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429;
}

function refreshAccessToken(): Promise<string | null> {
  return refreshSession().then((res) => res?.access_token ?? null);
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
  // Yêu cầu báo máy hỏng (20/08/2026), đẩy HAI CHIỀU:
  //   • `_moi` → mọi tài khoản trong tổ sửa chữa: có người vừa báo máy hỏng.
  //   • `_ket_qua` → RIÊNG người đã gửi lời báo: đã lập phiếu, hay bị từ chối vì lý do gì. Nhận
  //     được sự kiện này nghĩa là mình chính là người gửi ⇒ chỗ dùng KHÔNG gác thêm quyền.
  | {
      type: "ky_thuat_yeu_cau_moi"; id: number; ma: string;
      may: string; may_ten: string | null; bo_phan_hong: string;
      muc_do: string; may_dung: boolean;
      nguoi_bao: string | null; bo_phan: string | null;
    }
  | {
      type: "ky_thuat_yeu_cau_ket_qua"; id: number; ma: string;
      ket_qua: "da_tao_phieu" | "tu_choi";
      phieu_id: number | null; phieu_ma: string | null;
      ly_do: string | null; boi: string | null;
    }
  // Tạm ứng lương: NV gửi đề nghị → 'pending_changed' (người duyệt refetch badge); kế toán
  // duyệt/từ chối → 'decision' gửi riêng nhân viên đề nghị.
  | { type: "advance_pending_changed"; code?: string }
  | { type: "advance_decision"; code?: string; decision: "approved" | "rejected" }
  // Phiếu tăng ca: NV gửi/hủy → 'ot_pending_changed' (người duyệt refetch badge); tổ trưởng
  // duyệt/từ chối → 'ot_decision' đẩy riêng cho nhân viên nộp phiếu.
  | { type: "ot_pending_changed"; code?: string }
  | {
      type: "ot_decision";
      code?: string;
      // huy_dong_y / huy_giu_nguyen = người duyệt quyết yêu cầu XIN HỦY phiếu đã duyệt (23/09/2026).
      decision: "approved" | "rejected" | "cancelled" | "huy_dong_y" | "huy_giu_nguyen";
    }
  // Nghỉ phép (23/09/2026 — trước đó không đẩy gì): gửi đơn / xin hủy / rút lại → người duyệt tải lại
  // badge; quyết định về đơn → đẩy riêng cho người đứng tên đơn.
  | { type: "leave_pending_changed"; code?: string }
  | {
      type: "leave_decision";
      code?: string;
      decision: "approved" | "rejected" | "cancelled" | "huy_dong_y" | "huy_rut_ngan" | "huy_giu_nguyen";
    }
  // Phiếu đi muộn / về sớm / nghỉ nửa buổi: cùng luồng với tăng ca (tổ trưởng duyệt), bảng riêng.
  | { type: "el_pending_changed"; code?: string }
  // Yêu cầu chỉnh công (E7, 08/09/2026): gửi/huỷ → người duyệt refetch; duyệt/từ chối → đẩy đúng NV.
  | { type: "adjust_pending_changed"; code?: string }
  | { type: "adjust_decision"; code?: string; decision: "approved" | "rejected" }
  | { type: "el_decision"; code?: string; decision: "approved" | "rejected" }
  // Quản lý đổi ca của một người → đẩy RIÊNG cho chính người đó (5 đường: lưới phân ca, panel
  // Gán ca, gán hàng loạt, sửa hồ sơ, gỡ mốc). `count` = số thay đổi trong lần lưu đó.
  | { type: "shift_changed"; count?: number }
  // Quyền của CHÍNH người nhận vừa đổi (lưu ma trận vai của họ · gán/gỡ vai · đổi phòng). Không
  // mang nội dung quyền — nhận là hỏi lại `/api/auth/permissions`.
  | { type: "quyen_doi" }
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
  // Thêm/xoá tệp đính kèm của một lệnh — chỉ màn chi tiết đúng lệnh đó tải lại danh sách tệp.
  | { type: "lsx_dinh_kem_changed"; lsx_id: number }
  // Bài ghép tạo/sửa/xoá → hàng chờ ghép + danh sách bài ghép cập nhật ngay (không cần refresh).
  | { type: "bai_ghep_changed" }
  // Xếp lịch (cấp LỆNH): đặt/dời/bỏ mốc · phát hành · thu hồi → bàn Xếp lịch + badge cập nhật
  // ngay. Trước 18/09/2026 đây là HAI kênh (`xep_lich_changed` của bàn theo công đoạn +
  // `xep_lich_3_changed` của bàn cấp lệnh); bàn kia xoá rồi nên gộp về một.
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
  // Giao hàng (20/08/2026): đẩy ĐÍCH DANH cho tài xế của chuyến. Tài xế đang ở kho hoặc trên
  // đường, không ngồi canh màn hình — bắt họ F5 để biết "kho soạn xong chưa" là bắt đoán.
  | {
      type: "giao_hang_chuyen";
      /** `phan_chuyen` | `doi_gio` | `gui_kho` | `kho_xong` — `kho_xong` là mốc tài xế lên đường. */
      viec: string;
      trip_id: number;
      request_code?: string | null;
      khach?: string | null;
      ma_phieu?: string | null;
      message: string;
    }
  // Yêu cầu / chuyến giao đổi (mọi thao tác ghi của module giao hàng) — tín hiệu NHẸ để drawer đơn
  // và màn Giao hàng đang mở tự tải lại, không toast.
  | { type: "giao_hang_changed" }
  // `notification_new` = có thông báo mới vào chuông → FE refetch list + badge chuông.
  | { type: "notification_new" }
  // Thực hiện sản xuất (module `san_xuat`): `san_xuat_cong_viec_changed` = tín hiệu bàn tổ đổi
  // (badge tổ nhảy + bàn đang mở refetch); `san_xuat_duoc_giao_viec` = đẩy đích danh tới người vừa
  // được giao (toast cá nhân, nếu có tài khoản).
  | {
      type: "san_xuat_cong_viec_changed";
      team_id?: number | null;
      cong_viec_id?: number | null;
      trang_thai?: string | null;
    }
  | { type: "san_xuat_duoc_giao_viec"; cong_viec_id?: number | null }
  // Việc GIỮA HAI TỔ (bàn giao §11 · hỗ trợ chéo §9): `*_changed` broadcast để bàn đang mở + badge
  // tươi; `san_xuat_ban_giao` / `san_xuat_ho_tro` đẩy ĐÍCH DANH tới người cần biết (trừ người bấm),
  // mang sẵn nhãn để toast nói được việc gì. `su_kien`: de_xuat | sua | xac_nhan | dieu_chinh | huy.
  | { type: "san_xuat_ban_giao_changed"; team_ids?: number[]; ban_giao_id?: number | null; trang_thai?: string | null }
  | {
      type: "san_xuat_ban_giao";
      ban_giao_id?: number | null;
      trang_thai?: string | null;
      su_kien?: string | null;
      nguon_ten?: string | null;
      dich_ten?: string | null;
      so_luong?: number | null;
      don_vi?: string | null;
    }
  | { type: "san_xuat_ho_tro_changed"; cong_viec_id?: number | null; ho_tro_id?: number | null; trang_thai?: string | null }
  | {
      type: "san_xuat_ho_tro";
      ho_tro_id?: number | null;
      trang_thai?: string | null;
      su_kien?: string | null;
      ho_ten?: string | null;
      ten_cong_doan?: string | null;
      to_goc_ten?: string | null;
      to_thuc_hien_ten?: string | null;
    }
  // KCS theo lệnh (mg 0306) · kho §14 · đóng nhóm §16/§13.3. `*_changed` = tín hiệu NHẸ broadcast
  // để panel/hộp đang mở refetch (quoteTick lo); `san_xuat_kcs_ket_qua` / `san_xuat_kho` = đẩy ĐÍCH
  // DANH tới người cần biết → toast cá nhân. `san_xuat_nhom_dong` = nhóm thành phẩm đã đóng, báo Sale
  // + Kế hoạch SX. `trang_thai` mang enum backend (kho: cho_kho/nhap_mot_phan/da_nhap/huy · nhóm:
  // closed_full/closed_short).
  | {
      type: "san_xuat_kcs_changed";
      cong_viec_id?: number | null;
      kcs_batch_id?: number | null;
      loi_id?: number | null;
      team_id?: number | null;
      lsx_id?: number | null;
    }
  | {
      /** KCS vừa kiểm một công đoạn của tổ — đẩy tới người Xác nhận sản lượng trọn tổ đó. */
      type: "san_xuat_kcs_ket_qua";
      team_id?: number | null;
      cong_viec_id?: number | null;
      loi_id?: number | null;
      lsx_ma?: string | null;
      ten_cong_doan?: string | null;
      /** Có = lỗi của công đoạn này bị KCS bắt ở bước sau (tên bước bắt); `so_loi` là phần quy về. */
      phat_hien_o?: string | null;
      don_vi?: string | null;
      so_dat?: number | null;
      so_loi?: number | null;
      nguoi_kiem?: string | null;
    }
  // Yêu cầu NHẬP thành phẩm từ KCS đổi (KCS vừa gửi / kho ghi sổ). `trang_thai` = trạng thái yêu cầu
  // kho (`approved` | `partial` | `done` | `cancelled`…). `_changed` broadcast để màn KCS / hồ sơ lệnh
  // tải lại; `san_xuat_kho` đẩy đích danh người KCS đã gửi khi kho ghi sổ.
  | {
      type: "san_xuat_kho_changed";
      cong_viec_id?: number | null;
      request_id?: number | null;
      ma?: string | null;
      trang_thai?: string | null;
    }
  | {
      type: "san_xuat_kho";
      cong_viec_id?: number | null;
      request_id?: number | null;
      ma?: string | null;
      trang_thai?: string | null;
    }
  | {
      type: "san_xuat_nhom_dong";
      nhom_id?: number | null;
      order_id?: number | null;
      trang_thai?: string | null;
      kieu?: string | null;
    }
  // Đề nghị cấp vật tư của MỘT công đoạn vừa đổi (tạo/sửa lần đề nghị — `services/san_xuat/
  // vat_tu_de_nghi.py`). Backend `hub.broadcast` gửi cho MỌI kết nối, KHÔNG theo phạm vi, nên hai
  // cổng lọc nằm hết ở FE (xem AppShell): gác quyền đọc `san_xuat` trước khi toast, và chỉ nạp
  // lại drawer khi `cong_viec_id` trùng việc đang mở. Payload đúng HAI khoá, không hơn.
  | { type: "san_xuat_vat_tu_de_nghi_changed"; cong_viec_id: number }
  // Bảng giữ chỗ vật tư (Kế hoạch vật tư) đổi — bật/tắt/nhặt thêm/chuyển kho/đối soát — gửi
  // BROADCAST (không riêng ai), chỉ để báo "tự tải lại", không mang state.
  | { type: "ke_hoach_vat_tu_thay_doi" };

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
  thue_ngoai: { label: "Thuê ngoài", tone: "ngoai", hint: "Nhà gia công làm — khai máy của họ trong danh mục Máy; nhập liệu y hệt bước máy, chỉ không sinh tiền khoán" },
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
  // Bước cần dụng cụ lưu kho (bế · ép nhũ · khung lụa) mà chưa trỏ con dao nào. Đứng NGANG HÀNG
  // với thiếu nhà gia công — cùng một danh sách, người dùng không phải học luật mới.
  thieu_khuon: "Có công đoạn cần khuôn / khung mà chưa chọn",
  // Bước Máy/Tổ giao cho một tổ chưa khai công việc khoán nào (18/09/2026, spec §5.4): thợ mở bàn
  // tổ ra không có việc nào để ghi mẻ ⇒ cả lệnh đứng ở tổ đó. Thuê ngoài miễn.
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
  khac_giay: "Giấy của bài lệch giấy đang khai ở một thành viên",
  buoc_chung_thieu_thanh_vien: "Bước dùng chung chưa gộp đủ mọi thành viên trong bài",
  thieu_buoc_chung_tren_giay: "Chưa có bước dùng chung nào nằm trên dòng giấy (điểm toả)",
  vuot_con_toi_da: "Số con/tờ vượt khả năng khổ tờ ghép",
  vuot_dien_tich: "Diện tích thành phẩm vượt quá tờ ghép",
};

/** Cảnh báo MỀM — chỉ tô màu, không chặn. Chỉ còn tín hiệu về TRẠNG THÁI đơn/lệnh.
 *
 *  ĐÃ BỎ `khac_giay` / `khac_so_mau` / `khac_so_mat` / `bai_thua`: điều kiện gộp chỉ là cùng công
 *  đoạn, còn quy cách thì người dùng có nghiệp vụ đó — máy không phán hộ. Bảng "Kiểm tương thích"
 *  (bảng máy tự kết luận Phù hợp / Cần xác nhận) cũng đã gỡ 17/08/2026: giấy · mực · số mặt · khổ
 *  TP của từng thành viên nằm sẵn trong bảng thành viên để người tự so. */
export const BAI_GHEP_CANH_BAO_LABELS: Record<string, string> = {
  co_gap: "Có lệnh GẤP trong bài",
  lech_han: "Hạn giao các lệnh lệch nhau xa",
  thanh_vien_khong_san_sang: "Có lệnh không còn sẵn sàng",
  don_huy: "Có lệnh thuộc đơn đã huỷ",
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
export interface HangChoGhepOut {
  items: HangChoGhepItem[];
  total: number;
  /** Số lệnh KHỚP MỌI BỘ LỌC nhưng bị giấu vì đang giữ chỗ vật tư.
   *
   *  Lệnh đang giữ chỗ không hiện ở hàng chờ ghép — nhưng biến mất im lặng thì người ghép đi tìm
   *  một mã cụ thể sẽ không phân biệt nổi ba lý do: chưa sẵn sàng · là ruột sách · đang giữ chỗ.
   *  Chỉ lý do thứ ba là thứ họ tự gỡ được, nên phải nói ra. */
  so_giu_cho: number;
}

export interface BaiGhepListItem {
  id: number; ma: string; trang_thai: BaiGhepTrangThai; so_lsx: number;
  giay_ten: string | null; kho_in: string | null;
  so_to_tot: number; tong_to: number; han_in_muon_nhat: string | null; so_canh_bao: number;
  /** 0 = chưa gộp bước nào ⇒ mới là N lệnh rời, chưa thành bài ghép. Server vẫn luôn trả (schema
   *  `BaiGhepListItem` có sẵn), chỉ là type này quên khai. */
  so_buoc_chung: number;
  /** Giấy phải LĨNH KHO = tờ in + hao lượt chung — khác `so_to_tot` (tờ in). */
  to_nguyen_can: number;
  hao_de_xuat: number;
}
export interface BaiGhepListOut { items: BaiGhepListItem[]; total: number }

export interface BaiGhepThanhVien {
  thanh_vien_id: number; lsx_id: number; lsx_ma: string | null; lsx_ten: string | null;
  customer_name: string | null;
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
  /** `id` của bai_ghep_cong_doan — dùng NEO NHÃN (TagPicker). Ổn định như `step_key`. */
  id: number;
  step_key: string; ten: string; nhom: string | null; cong_doan_id: number | null;
  loai_buoc: LsxLoaiBuoc; thu_tu: number;
  /** `false` = bước chế bản (chung BẢN/kẽm), KHÔNG trên dòng giấy → thẻ ẩn số tờ vào/ra. */
  tren_giay: boolean;
  /** Số của CẢ LƯỢT. Đơn vị lấy từ khai báo công đoạn — bước bế nhả `cai` thì `so_luong_ra` đếm con. */
  so_luong_vao: number; so_luong_ra: number;
  don_vi_vao: string | null; don_vi_ra: string | null;
  /* `san_luong_dien_giai` + `loi_quy_doi` GỠ 18/09/2026 (mg `0324`) cùng công thức sản lượng ra
     của công đoạn — bước ngoài dòng giấy không còn số ở cấp bài. */
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
  /** Tổ phụ trách khai ở danh mục Công đoạn — ô TỔ của lượt chung chỉ mời các tổ này (tổ đang
   *  gán lệch vẫn hiện để không mất dấu). [] = công đoạn chưa khai tổ, không giới hạn. */
  to_chon_duoc: number[];
  /** Đã khai gì đó cho lượt chung chưa → tách ra là mất. Cờ THẬT của server, đừng dò chuỗi `thieu`. */
  da_lap_ke_hoach: boolean;
  /** ID + TÊN: `<select>` cần id để chọn đúng, nhãn cần tên. Chỉ có tên là form phải lấy tên làm
   *  `value` rồi so chuỗi với id — tổ đã gán vẫn hiện "— chọn tổ —". */
  department_id: number | null; to_ten: string | null;
  may_id: number | null; may_ten: string | null;
  nha_cung_cap: string | null;
  tong_phut: number; chiem_may_phut: number;
  chiem_may_phut_min: number; chiem_may_phut_max: number;
  /** SỐ GIỜ KẾ HOẠCH của lượt chung loại TỔ — ô gõ tay, mặc định 0 (mg `0319`), cùng hợp đồng
   *  với bước lệnh. Kíp chuẩn + năng suất chép từ đầu việc GỠ 18/09/2026 (mg `0320`, `0321`). */
  so_gio_ke_hoach: number;
  /** Dẫn xuất từ tốc độ máy; `setup_phut` kế thừa từ máy. Ô gõ được duy nhất là
   *  `phat_sinh_phut` ("Thời gian khác"). `cho_phut`/`di_chuyen_phut` đã bỏ. */
  chay_phut: number | null;
  setup_phut: number; phat_sinh_phut: number;
  /** Bóc tách thời lượng y như bước lệnh (thay giấy · thay kẽm · tra dầu · công thức chạy) —
   *  cùng một `thoi_luong_buoc()` sinh ra. Có nó thì drawer nói được VÌ SAO ra số phút đó. */
  thoi_luong_dien_giai: Record<string, unknown>;
  so_luot_chay: number;
  /* Đầu việc ghim ở lượt chung (`khoan_rate_id` · `khoan_ten` · `khoan_chon_duoc`) GỠ 18/09/2026
     (mg `0320`): việc khoán chọn LÚC GHI MẺ ở bàn tổ, không chọn ở kế hoạch. */
  vat_tus: { vat_tu_id: number; ma: string; ten: string; don_vi: string; so_luong: number;
             nguon_so_luong: string }[];
  /** Lượng TÍNH SẴN cho mọi vật tư theo lượt chung — cùng hợp đồng với bước lệnh. Món chưa tính
   *  ra được vẫn có mặt (`so_luong: null`) kèm `ly_do` chỉ chỗ khai công thức. */
  vat_tu_goi_y: { vat_tu_id: number; so_luong: number | null;
                  dien_giai: string | null; ly_do: string | null }[];
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
  /** Số giờ kế hoạch của lượt chung loại TỔ — số thập phân ≥ 0, để 0 là hợp lệ (mg `0319`). */
  so_gio_ke_hoach?: number | null;
  /** Ô DUY NHẤT còn gõ được (2026-08-04): chuẩn bị + tốc độ kế thừa SỐNG từ máy đang gán. */
  phat_sinh_phut?: number; so_luot_chay?: number;
  ghi_chu?: string | null;
  vat_tus?: { vat_tu_id: number; so_luong: number; nguon_so_luong?: string }[];
  nha_cung_cap?: string | null; sl_gui?: number | null; ngay_gui_dk?: string | null;
  van_chuyen_ngay?: number | null; gia_cong_ngay?: number | null; ngay_nhan_dk?: string | null;
  hao_hut_cho_phep?: number | null; don_gia_gia_cong?: number | null;
  yeu_cau_ky_thuat?: string | null;
}
/** `step_key → gộp thêm vào được không, không thì vì sao` (kiểm TRƯỚC khi cho bấm Gộp). */
export interface BaiGhepUngVienGop {
  ung_vien: Record<string, { gop_duoc: boolean; ly_do: string | null }>;
}
export interface BaiGhepDetail {
  id: number; ma: string; trang_thai: BaiGhepTrangThai;
  giay_id: number | null; giay_ten: string | null;
  /** Quy cách CẢ TỜ GHÉP — server tính lúc đọc: định lượng + khổ tờ mua về lấy thẳng danh mục
   *  giấy, mực/kẽm là HỢP tập của mọi thành viên (chung tờ = chung một bộ bản). */
  gsm: number | null; kho_nguyen_dai: number | null; kho_nguyen_rong: number | null;
  quy_cach_in: string | null; quy_cach_in_lech: boolean;
  muc_a: string[]; muc_b: string[];
  so_mau_a: number; so_mau_b: number; so_mau_pha: number; so_kem: number;
  kho_in_dai: number | null; kho_in_rong: number | null;
  may_id: number | null; may_ten: string | null;
  /** `null` = CHƯA KHAI (bài dùng hao máy đề xuất) · `0` = khai "chạy đúng số, không bù". */
  hao_hut_setup: number | null; hao_hut_chay: number | null; ghi_chu: string | null;
  thanh_vien: BaiGhepThanhVien[];
  so_to: BaiGhepSoTo;
  thieu: string[]; canh_bao: string[];
}
export interface BaiGhepUpdateBody {
  giay_id?: number | null; kho_in_dai?: number | null; kho_in_rong?: number | null;
  /** Gửi `null` = xoá khai báo (quay về hao máy đề xuất); gửi `0` = khai "không bù hao". */
  may_id?: number | null; hao_hut_setup?: number | null; hao_hut_chay?: number | null;
  ghi_chu?: string | null;
}

/** Metadata riêng của Bài ghép 2. Các phép tính/routing vẫn dùng chung engine Bài ghép. */
export interface BaiGhep2Meta {
  ten: string;
  han_hoan_thanh_sx: string | null;
  is_rush: boolean;
  nguoi_phu_trach_id: number | null;
  nguoi_phu_trach_ten?: string | null;
}
export interface BaiGhep2ListItem extends BaiGhepListItem, BaiGhep2Meta {}
export interface BaiGhep2ListOut { items: BaiGhep2ListItem[]; total: number }
export interface BaiGhep2Detail extends BaiGhepDetail, BaiGhep2Meta {}
export interface BaiGhep2UpdateBody extends BaiGhepUpdateBody {
  ten?: string;
  han_hoan_thanh_sx?: string | null;
  is_rush?: boolean;
  nguoi_phu_trach_id?: number | null;
}
export interface BaiGhep2NguoiPhuTrachOption { id: number; ten: string }

export interface BaiGhep2VatTuDong {
  pham_vi: "bai_ghep" | "lsx";
  lsx_id: number | null;
  bai_ghep_id: number | null;
  buoc_id: number | null;
  gang_step_key?: string | null;
  ma: string;
  ten_viec: string | null;
  nhu_cau: number;
  nhu_cau_hien_thi: string;
}
export interface BaiGhep2VatTuNhom {
  loai_nhom: string;
  hang_loai: string;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  don_vi_goc: string | null;
  tong_can: number;
  dong: BaiGhep2VatTuDong[];
}
export interface BaiGhep2VatTuHieuLuc {
  bai_ghep_id: number;
  items: BaiGhep2VatTuNhom[];
}
export interface BaiGhep2Activity {
  at: string | null;
  actor: string | null;
  action: string;
  detail: string | null;
}

// ============================ Xếp lịch (cấp LỆNH SẢN XUẤT) ============================
// Bàn xếp lịch DUY NHẤT của hệ: một dòng = một lệnh, người dùng chỉ đặt GIỜ BẮT ĐẦU, hệ trả ngày
// kết thúc. Không gán máy / gán tổ / xung đột — bàn theo công đoạn (`xep_lich_2`, `Xl2*`) làm việc
// đó, và đã xoá hẳn 18/09/2026 cùng router + màn.

/** Một đoạn máy CHẠY liền mạch — khối đậm bên trong thanh Gantt. Khoảng hở giữa hai đoạn là nghỉ
 *  giữa ca / ngoài ca / ngày nghỉ, không phải máy rảnh. */
export interface XlDoan {
  tu: string;
  den: string;
  buoc_index: number;
}

/** Một quãng lệnh THẬT SỰ chạy (theo phiên chạy của tổ), đã gộp phần các bước chồng giờ nhau. */
export interface XlDoanThucTe {
  tu: string;
  den: string;
}

/** Phần LỊCH dùng chung giữa dòng Gantt và panel chi tiết. `bat_dau_at` rỗng = lệnh chưa xếp. */
export interface XlLich {
  bat_dau_at: string | null;
  ket_thuc: string | null;
  chay_phut: number;
  /** Nghỉ giữa ca + ngoài ca + ngày nghỉ. Trả lời đúng câu người dùng hỏi khi nhìn thanh:
   *  "vì sao nó dài hơn giờ chạy?". Tổng thanh = `chay_phut` + số này. */
  nghi_ngoai_ca_phut: number;
  doan: XlDoan[];
  ghi_chu: string[];
  updated_at: string | null;
}

/** Một dòng trên bàn Gantt = MỘT lệnh sản xuất. `da_doi`/`thong_bao` CHỈ có ở phản hồi của PUT. */
export interface XlDong extends XlLich {
  lsx_id: number;
  ma: string;
  ten: string;
  customer_name: string | null;
  trang_thai: string;
  is_rush: boolean;
  so_luong_dat: number;
  don_vi_tinh: string | null;
  so_to_ke_hoach: number;
  so_con: number;
  han_hoan_thanh_sx: string | null;
  han_giao_khach: string | null;
  may_ten: string | null;
  /** Mép thanh của lệnh ĐÃ CHẠY DỞ — `null` khi lệnh chưa vào việc.
   *  Thanh vẽ từ `thuc_bat_dau_lenh ?? bat_dau_at` tới `ket_thuc_thuc_te ?? ket_thuc`; đoạn
   *  `thuc_bat_dau_lenh → bat_dau_at` là phần đã chạy, KHOÁ không kéo được. `bat_dau_at` vẫn là
   *  con số duy nhất kéo-thả ghi xuống. */
  thuc_bat_dau_lenh: string | null;
  ket_thuc_thuc_te: string | null;
  /** Các quãng lệnh THẬT SỰ chạy bên trong đoạn `thuc_bat_dau_lenh → bat_dau_at`. Cả đoạn đó là
   *  "đã vào việc rồi NẰM CHỜ": tô một tông "đã chạy" cho cả 5 ngày trong khi máy chạy 13 phút là
   *  bàn nói dối. Vẽ nền CHỜ cho cả đoạn rồi chồng các quãng này lên. */
  doan_thuc_te: XlDoanThucTe[];
  da_doi?: boolean | null;
  thong_bao?: string | null;
}

export interface XlLien {
  dong: XlDong[];
  tong: number;
  /** Ngày KHÔNG làm việc trong đúng cửa sổ vừa hỏi (YYYY-MM-DD): lễ, ngày làm bù, cấu hình tuần
   *  của xưởng. ĐỪNG tự suy "T7 + CN" — xưởng này khai làm thứ 7, đoán kiểu đó tô sai ngay cột
   *  đầu tiên, còn lễ với làm bù thì không có đường nào đoán. */
  ngay_nghi: string[];
}

/** Thẻ hàng chờ — lệnh đủ điều kiện xếp mà CHƯA có mốc. */
export interface XlThe {
  lsx_id: number;
  ma: string;
  ten: string;
  customer_name: string | null;
  han_hoan_thanh_sx: string | null;
  han_giao_khach: string | null;
  is_rush: boolean;
  so_to_ke_hoach: number;
  so_luong_dat: number;
  don_vi_tinh: string | null;
  chay_phut: number;
  so_buoc: number;
}

export interface XlHangCho {
  dong: XlThe[];
  tong: number;
}

/** Dòng bảng công đoạn trong panel. HAI CHẾ ĐỘ, cắt bằng `trang_thai`:
 *   · `null` — lệnh CHƯA phát hành: không có mốc bước (màn cấp LỆNH, chưa có gì để so).
 *   · có giá trị — lệnh ĐÃ phát hành: `ke_hoach_*` so với `thuc_*`, chênh nằm ở `lech_phut`.
 *  `mau_index` mã hoá THỨ TỰ bước (sắc độ khối), không mã hoá loại. */
export interface XlCongDoan {
  id: number;
  thu_tu: number;
  ten: string;
  loai_buoc: string | null;
  /** Máy ĐANG GIAO CHẠY nếu lệnh đã phát hành, không thì máy kế hoạch — `may_nguon` nói rõ nguồn
   *  nào. Xưởng đổi máy thì `may_ke_hoach_ten` giữ tên máy kế hoạch để đối chiếu. Số giờ tính
   *  theo máy ĐANG CHẠY (tốc độ treo ở cặp công đoạn × máy). */
  may_id: number | null;
  may_ten: string | null;
  may_nguon: "thuc_thi" | "ke_hoach" | null;
  may_ke_hoach_ten: string | null;
  to_ten: string | null;
  /** `null` = kế hoạch CHƯA khai, KHÁC 0. Đừng in "0 tờ" cho ô chưa điền. */
  so_luong_vao: number | null;
  /** `don_vi_vao` là MÃ (`to`, `con`); in `don_vi_vao_ten` cho người đọc, đừng in mã thô. */
  don_vi_vao: string | null;
  don_vi_vao_ten: string | null;
  /** Số NGƯỜI tiêu chuẩn của bước — không phải mã kíp trực. */
  so_nguoi_chuan: number;
  chay_phut: number;
  /** `chua_quy_doi` = không tính được giờ; `canh_bao` là câu nói rõ thiếu gì (server phát). */
  phuong_phap: string | null;
  canh_bao: string | null;
  /** Lớp phụ thuộc; `song_song` = còn bước khác cùng lớp (bảng bày 1→N nhưng chúng không chặn
   *  nhau). Bàn cấp lệnh vẫn TRẢI TUẦN TỰ — chip chỉ nói thật, không đổi cách trải. */
  lop: number;
  song_song: boolean;
  thue_ngoai_ngay: number | null;
  mau_index: number;
  /** Trạng thái thẻ việc dưới xưởng. `null` ⇔ lệnh chưa phát hành ⇒ cả khối dưới đều `null`. */
  trang_thai: "released" | "running" | "paused" | "completed" | null;
  /** Mốc KẾ HOẠCH của bước (bản đã phát hành xuống xưởng). */
  ke_hoach_bat_dau: string | null;
  ke_hoach_ket_thuc: string | null;
  /** Mốc phiên chạy ĐẦU TIÊN; `null` = tổ chưa bấm Bắt đầu bao giờ. */
  thuc_bat_dau: string | null;
  /** Chỉ có khi bước đã ĐÓNG — đang chạy thì chưa có mốc xong để nói. */
  thuc_ket_thuc: string | null;
  /** Chênh mốc KẾT THÚC, phút. DƯƠNG = xong muộn, ÂM = xong sớm. Server tính trên mốc gốc —
   *  ĐỪNG trừ `thuc_ket_thuc - ke_hoach_ket_thuc` ở đây để dựng lại. */
  lech_phut: number | null;
}

export interface XlChiTiet extends XlLich {
  lsx_id: number;
  ma: string;
  ten: string;
  trang_thai: string;
  is_rush: boolean;
  customer_name: string | null;
  order_no: string | null;
  customer_po_no: string | null;
  sale_name: string | null;
  so_luong_dat: number;
  don_vi_tinh: string | null;
  so_to_ke_hoach: number;
  so_to_nguyen: number;
  so_con: number;
  han_hoan_thanh_sx: string | null;
  han_giao_khach: string | null;
  nguoi_phu_trach_ten: string | null;
  luu_y_gui_xuong: string | null;
  /** Quy cách đọc từ ảnh chụp lúc tạo lệnh — khoá có thể trống. Trống thì BỎ ô, đừng in `null`. */
  giay: string | null;
  kho_in: string | null;
  so_mau: string | null;
  so_kem: string | null;
  // `so_nguoi_tong` GỠ 18/09/2026 (mg `0321`) cùng kíp chuẩn của bước.
  cong_doans: XlCongDoan[];
  /** Mốc xong TÍNH LẠI theo việc đã xảy ra — bước xong sớm kéo lùi, xong muộn đẩy ra. `null` ⇔
   *  `co_thuc_te=false` (lệnh chưa phát hành): khi đó panel bày MỘT số như trước.
   *  `ket_thuc` (từ `XlLich`) vẫn là mốc theo KẾ HOẠCH — hai số cố ý bày cạnh nhau. */
  ket_thuc_thuc_te: string | null;
  /** `ket_thuc_thuc_te - ket_thuc`, phút. DƯƠNG = thực tế đang kéo lệnh muộn hơn kế hoạch. */
  lech_ket_thuc_phut: number | null;
  co_thuc_te: boolean;
  /** Mốc CẢ LỆNH thật sự vào việc. KHÔNG đổi khi dời mốc — thứ dời được chỉ là PHẦN CÒN LẠI. */
  thuc_bat_dau_lenh: string | null;
  so_buoc_xong: number;
  so_buoc: number;
}

/** Một bước trong bảng so sánh hai phiên bản lịch. `a` là phiên bản NHỎ hơn (server tự sắp). */
export interface XlSoSanhDong {
  cong_viec_id: number;
  ten: string;
  phan_doan_so: number;
  phan_doan_tong: number;
  a: { may_ten: string | null; bat_dau: string | null; ket_thuc: string | null };
  b: { may_ten: string | null; bat_dau: string | null; ket_thuc: string | null };
  doi_gio: boolean;
  doi_may: boolean;
}

export interface XlSoSanh {
  lsx_id: number;
  a: number;
  b: number;
  dong: XlSoSanhDong[];
}

/** Một mốc trong lịch sử phiên bản gói phát hành (§4.3). `so`=1 là phát hành gốc; các số sau là mỗi
 *  lần Phát hành cập nhật (`loai="cap_nhat"`), kèm lý do. */
export interface XlGoiPhienBan {
  so: number;
  loai: string;
  ly_do: string | null;
  phat_hanh_by_id: number | null;
  luc: string | null;
}

/** Trạng thái gói phát hành của một LSX/bài ghép (§4.3): còn Phát hành cập nhật / Thu hồi được không +
 *  số việc đã/chưa bắt đầu + lịch sử phiên bản. `co_goi=false` ⇒ chưa phát hành (các field khác vắng). */
export interface XlGoiPhatHanh {
  co_goi: boolean;
  goi_id?: number;
  ma?: string;
  trang_thai?: string;
  version_hien_tai?: number;
  so_cong_viec?: number;
  so_da_bat_dau?: number;
  so_chua_bat_dau?: number;
  cho_phep_cap_nhat?: boolean;
  cho_phep_thu_hoi?: boolean;
  phien_bans?: XlGoiPhienBan[];
}

/** Kết quả một lần Phát hành cập nhật (§4.3): tái chụp bao nhiêu việc, giữ nguyên bao nhiêu, huỷ bao
 *  nhiêu phân công/hỗ trợ để tổ xác nhận lại. */
export interface XlCapNhatOut {
  goi_id: number;
  ma: string;
  version_hien_tai: number;
  so_cong_viec_cap_nhat: number;
  so_giu_nguyen: number;
  so_huy_phan_cong: number;
  so_huy_ho_tro: number;
  /** Số việc KHÔNG cập nhật được vì bước đã tách thêm / gộp lại sau phát hành: không còn lần chạy
   *  tương ứng để lấy giờ + máy. Chúng giữ nguyên snapshot cũ — muốn khớp lại phải thu hồi gói. */
  so_lech_phan_doan: number;
}


// --- Thực hiện sản xuất (module `san_xuat`) — bàn của TỔ ----------------------
// Mirror ĐÚNG `schemas/san_xuat.py` (Pydantic nuốt field lạ IM LẶNG — thêm/bớt field phải đi cả
// hai đầu). datetime serialize thành chuỗi ISO ⇒ dùng `string | null`. KHÔNG có mốc chạy thật trên
// WorkItem (mức bàn) — so kế-hoạch↔thực-tế nằm ở drawer (phien_chay + khoang_tham_gia).
export interface SxTeam {
  id: number;
  ten: string;
  ma: string;
  /** Phòng ban có cờ "Tổ KCS" (`is_kcs`) — thành viên là người KCS. */
  la_kcs: boolean;
  /** Độ sâu của nút trong cây khối sản xuất (0 = gốc) — menu thụt lề theo số này. */
  cap: number;
  /** Vai của NGƯỜI ĐANG XEM ở nút này, không phải thuộc tính của tổ: mức Xem của dòng quyền
   *  `to_sx_<id>` là "Của tôi" thì `true`. Bật băng "Sản lượng của tôi" theo cờ này, đừng tự suy
   *  ở FE. */
  la_tho: boolean;
  /** Mức của người đang xem trên CHÍNH nút này theo từng việc (`read`/`run_order`/
   *  `confirm_output`/`warehouse` → "all" | "own"); thiếu khoá = không có quyền đó. */
  quyen: Partial<Record<SxViecTo, "all" | "own">>;
  so_viec_cho: number;
  /** Bàn giao đến + thỏa thuận hỗ trợ chéo đang chờ tổ trong vùng xác nhận (người xem giữ Xác nhận
   *  sản lượng trọn tổ) — cộng vào badge menu cùng `so_viec_cho`. */
  so_cho_xac_nhan: number;
}
/** Ba quyền chi tiết của dòng quyền theo tổ + Xem. Ô "KCS" (`qc`) GỠ ở mg 0306: người KCS là
 *  thành viên phòng ban `is_kcs`, kiểm được mọi tổ — xem `useKcs()`. */
export type SxViecTo = "read" | "run_order" | "confirm_output" | "warehouse";

export interface SxTeamsOut {
  teams: SxTeam[];
}

/** Một người có mặt trong mẻ. `to_ten` CHỈ có khi người đó không thuộc tổ chủ mẻ — nhãn
 *  "(Tổ bế)" để biết ngay ai là người nhà, ai sang giúp (spec 2026-09-18 §7.3b). */
export interface SxMeNguoi { employee_id: number; ho_ten: string; to_ten?: string | null }

/** "CÁC MẺ TÔI THAM GIA" trong tháng (spec 2026-09-18 §7.5). Mỗi dòng mang sản lượng của CẢ MẺ
 *  kèm danh sách người — không "phần của tôi", không số phút, không tiền: tầng chia sản lượng đã
 *  gỡ (mg 0322). `employee_id` null = tài khoản chưa nối hồ sơ nhân sự. */
export interface SxMeCuaToi {
  batch_id: number;
  bat_dau: string | null;
  ket_thuc: string | null;
  lsx_ma: string | null;
  ten_cong_doan: string;
  /** Ảnh chụp tên việc khoán lúc ghi; null = mẻ ghi trước 18/09/2026. */
  viec_khoan_ten: string | null;
  tot: number;
  hong: number;
  don_vi: string | null;
  nguoi_tham_gia: SxMeNguoi[];
}
export interface SxSanLuongCuaToi {
  nam: number;
  thang: number;
  employee_id: number | null;
  me: SxMeCuaToi[];
  so_me: number;
}

/** Tab SẢN LƯỢNG của bàn tổ (spec 2026-09-14 §6, sửa 2026-09-18 §7.3b). Ngày = ngày BẮT ĐẦU mẻ
 *  theo giờ xưởng; mọi số đi theo ĐƠN VỊ, không cộng lẫn. Mẻ có MỘT chủ: tổ khác có người trong mẻ
 *  thấy mẻ ấy ở mục khách (`la_khach`) — cùng con số, KHÔNG vào dòng tổng. KHÔNG có ô tiền. */
export interface SxSlTotHong { don_vi: string | null; tot: number; hong: number }
export interface SxSlMe {
  batch_id: number;
  ngay: string | null;
  bat_dau: string | null;
  ket_thuc: string | null;
  viec_khoan_ten: string | null;
  tot: number;
  hong: number;
  don_vi: string | null;
  nguoi: SxMeNguoi[];
  /** Việc phát sinh của mẻ (ảnh chụp lúc ghi) — chỉ để bày, KHÔNG cộng vào sản lượng. */
  phat_sinh: SxSlPhatSinh[];
}
export interface SxSlPhatSinh {
  ten: string | null;
  so_luong: number;
  don_vi: string | null;
  don_vi_ten: string | null;
}
export interface SxSlCongDoan {
  cong_viec_id: number;
  ten_cong_doan: string;
  to_id: number | null;
  to_ten: string;
  /** Mẻ của TỔ KHÁC mà có người của tổ đang xem — mục "đi làm ở tổ khác", không cộng tổng. */
  la_khach: boolean;
  so_me: number;
  san_luong: SxSlTotHong[];
  me: SxSlMe[];
}
export interface SxSlKho { dai: number; rong: number }
export interface SxSlQuyCach {
  giay: string | null;
  dinh_luong: number | null;
  to_nguyen: SxSlKho | null;
  to_in: SxSlKho | null;
  con: SxSlKho | null;
}
export interface SxSlLenh {
  nguon_loai: "lsx" | "bai_ghep";
  nguon_id: number | null;
  ma: string;
  ten: string;
  so_me: number;
  ngay_dau: string | null;
  ngay_cuoi: string | null;
  /** Giấy + ba khổ (mm) — cùng thẻ quy cách ở bàn tổ. */
  quy_cach: SxSlQuyCach | null;
  /** Chỉ gồm MẺ CỦA TỔ — mẻ khách không vào đây. */
  san_luong: SxSlTotHong[];
  cong_doan: SxSlCongDoan[];
}
export interface SxSanLuongTo {
  team_id: number;
  tu: string;
  den: string;
  to_id: number | null;
  trang: number;
  co_trang: number;
  tong_lenh: number;
  co_pham_vi_tron: boolean;
  co_pham_vi_rieng: boolean;
  cac_to: { id: number; ten: string; cap: number }[];
  tong: (SxSlTotHong & { so_me: number })[];
  lenh: SxSlLenh[];
  cap_nhat_luc: string | null;
}
export interface SxSanLuongToLoc {
  team_id: number;
  tu?: string;
  den?: string;
  to_id?: number | null;
  tim?: string;
  trang?: number;
  co_trang?: number;
}

export interface SxWorkItem {
  id: number;
  /** Tổ THẬT của việc — bàn nút cha gộp việc của nhiều tổ con, thao tác theo tổ lấy id ở đây. */
  department_id: number | null;
  goi_id: number;
  phien_ban_so: number;
  nguon_loai: string;          // "lsx" | "bai_ghep" | ""
  nguon_ma: string;
  nguon_ten: string;
  /** Khách của lệnh; bài ghép = khách các lệnh thành viên nối " · ". null = lệnh không có đơn/khách. */
  khach_hang?: string | null;
  nhom_id: number | null;      // id nhóm thành phẩm (khoá cho panel Kho §14 + checklist đóng §16)
  nhom: string;                // nhãn nhóm thành phẩm
  ten_cong_doan: string;
  nhom_cong_doan: string | null;
  loai_buoc: string;           // "may" | "to" | "thue_ngoai"
  /** Công đoạn cuối của nhóm thành phẩm — KCS kiểm đạt ở đây mới được đề nghị nhập kho. */
  la_kcs_cuoi: boolean;
  /** Dấu KCS trên thẻ việc (mg 0306): số lần KCS đã kiểm công đoạn này + Σ đạt / Σ lỗi. */
  kcs_so_lan: number;
  kcs_dat: number;
  kcs_loi: number;
  may: string;
  may_id: number | null;       // máy HIỆN TẠI — dựng ô chọn "Đổi máy" (§7.2 mở rộng)
  du_kien_bat_dau: string | null;
  du_kien_ket_thuc: string | null;
  nhan_luc?: string | null;    // lúc việc tới tay tổ (phát hành tạo thẻ việc) — mốc để lọc/tra
  so_luong_vao: number | null;
  so_luong_ra: number | null;  // mục tiêu của bước — đã có sẵn, KHÔNG đẻ khoá `muc_tieu_ra` thứ hai
  /** Đơn vị BẢN ĐỊA của bước — cũng là đơn vị mặc định của ô Ghi mẻ. Bước ngoài dòng giấy chỉ có
   *  đơn vị khi người lập lệnh tự khai ở bước; không khai thì trống. */
  don_vi_vao: string | null;
  don_vi_ra: string | null;
  /** Bước NGOÀI dòng giấy (ghi kẽm đếm bản, đóng thùng đếm thùng): vào = ra nên cột "SL vào → ra"
   *  hiện MỘT số. Ảnh chụp lúc phát hành — FE KHÔNG suy lại được từ mã đơn vị. */
  ngoai_dong: boolean;
  // `sl_dien_giai` GỠ 18/09/2026 (mg `0324`) cùng công thức sản lượng ra của công đoạn.
  /** Phút CHẠY của thẻ (đã chia theo phần sản lượng của phân đoạn). Ba số bằng nhau ⇒ máy chưa
   *  khai dải tốc độ, UI bỏ phần trong ngoặc. null = lệnh phát hành trước 10/09/2026. */
  chay_phut: number | null;
  chay_phut_min: number | null;
  chay_phut_max: number | null;
  /** DẶN DÒ của kế hoạch (ô "Ghi chú kỹ thuật cho thợ" của bước), chụp lúc phát hành. */
  ghi_chu: string | null;
  /** THẺ QUY CÁCH rút gọn — tổ trưởng không có quyền `lsx` nên không mở nổi hồ sơ lệnh. */
  quy_cach: SxQuyCachThe | null;
  /** Lượng tổ THẬT SỰ nhận được (bàn giao đã xác nhận về bước này). null = không ai giao tới
   *  (bước đầu chuỗi lấy vật tư từ kho) — KHÁC hẳn với 0. */
  thuc_nhan: number | null;
  /** Tổng sản lượng TỐT đã ghi ở bước này. */
  da_lam: number | null;
  /** Mốc chấm THỰC — `so_luong_ra` đã rút theo tỉ lệ thực nhận; kế hoạch ở trên không bị đè. */
  muc_tieu: number | null;
  /** max(mục tiêu − đã làm, 0). null khi bước không khai mục tiêu — KHÁC hẳn với 0. */
  con_thieu: number | null;
  trang_thai: string;          // "released" | "running" | "paused" | "completed"
  dinh_muc_vat_tu: SxVatTuDinhMuc[]; // định mức vật tư đóng băng lúc phát hành — KHÁC vật tư (phiếu xuất) ở drawer
  thuc_te: SxThucTeKhoang[];   // lớp thực-tế đè lên thanh kế hoạch (§5.1); phiên mở → ket_thuc=null
  /** Nhà gia công — ảnh chụp lúc phát hành, nuôi chip "Ngoài · <nơi làm>" ở mọi màn xưởng. */
  nha_cung_cap: string | null;
  /** Con dao/khung của bước — ảnh chụp lúc phát hành. `null` = bước không dùng dụng cụ.
   *  Có khuôn mà `khuon_da_nhan = false` ⇒ nút Bắt đầu bị BE chặn (cổng khuôn, 04/09/2026). */
  khuon: SxKhuonChip | null;
  khuon_da_nhan: boolean;
  khuon_da_tra: boolean;
  /** Người xem giữ Thực hiện lệnh trên việc này (máy chủ tính theo dòng quyền tổ, mức "Của tôi" chỉ
   *  bật trên việc đang giao cho mình) — nút chạy nhanh trên dòng bảng hiện theo cờ này. */
  chay_duoc: boolean;
}
/** Quy cách in RÚT GỌN đi theo thẻ việc (mg `0290`) — 8 dòng đủ để đứng máy, không phải bản sao
 *  của `lsx.quy_cach_json`. Khoá nào không có số thì server BỎ HẲN (không gửi `null`), nên UI chỉ
 *  vẽ những dòng thật sự có. Khổ đã ghép sẵn thành chuỗi mm ("640 × 450") ở server. */
export interface SxQuyCachThe {
  giay?: string;
  dinh_luong?: number;     // gsm
  kho_nguyen?: string;     // khổ giấy nguyên (tờ mua về), chuỗi mm
  kho_in?: string;         // KHÔNG có = khổ tờ in 0 × 0 ⇒ in thẳng khổ giấy nguyên
  kho_tp?: string;
  /** Mã cách in của lệnh (`mot_mat` · `hai_mat` · `tu_tro` · `tro_nhip`) — nhãn qua `nhanCachIn`. */
  cach_in?: string;
  /** Mực TỪNG MẶT, đã chuẩn hoá (C/M/Y/K + mã Pantone). Bài ghép = hợp mực các lệnh thành viên. */
  muc_a?: string[];
  muc_b?: string[];
  so_mat?: number;
  so_mau?: number;
  so_kem?: number;
  so_con?: number;
  so_luong?: number;
  ghi_chu_ky_thuat?: string;
}
/** Ảnh chụp khuôn đủ để vẽ chip — KHÔNG phải bản sao của danh mục Khuôn & khung. */
export interface SxKhuonChip {
  ma: string | null;
  ten: string | null;
  so_ke: string | null;
  tinh_trang: string | null;
}
/** Một dòng định mức vật tư của bước (đóng băng lúc phát hành). */
export interface SxVatTuDinhMuc {
  vat_tu_id: number | null;
  ma: string | null;
  ten: string | null;
  don_vi: string | null;
  so_luong: number | null;
}
/** Một phiên chạy thực tế để vẽ overlay; `ket_thuc=null` = đang chạy (kéo tới "bây giờ"). */
export interface SxThucTeKhoang {
  bat_dau: string;
  ket_thuc: string | null;
}
/** MỘT lệnh SX (hoặc bài ghép) trên bàn tổ — bản ghi của bàn kể từ 11/09/2026.
 *
 *  Đơn vị VIỆC vẫn là CÔNG ĐOẠN: `cong_viec` là các bước tổ thật sự bấm Bắt đầu / Ghi sản lượng,
 *  giữ nguyên `SxWorkItem`. Lệnh chỉ là ĐẦU MỤC bọc ngoài để tổ trưởng biết công đoạn này thuộc
 *  lệnh nào. Bài ghép là MỘT dòng, không xé theo lệnh thành viên. */
/** Một BƯỚC trên dải routing của thẻ lệnh — chuỗi công đoạn đầy đủ, kể cả bước của tổ khác.
 *  `cong_viec_id` chỉ có ở bước của CHÍNH tổ mình: bước tổ khác là chỉ-đọc, không mở drawer. */
export interface SxRoutingBuoc {
  thu_tu: number;
  step_key: string | null;
  ten_cong_doan: string;
  to_id: number | null;
  to_ten: string | null;
  la_cua_toi: boolean;
  la_kcs_cuoi: boolean;
  trang_thai: string;
  phan_doan_tong: number;
  chay_chung: boolean;
  ke_hoach: number | null;
  thuc_te: number;
  don_vi: string | null;
  da_giao_sang_toi: number | null;   // bước NGUỒN đã giao sang tổ đang xem
  da_nhan: number | null;            // bước CỦA TỔ đang xem đã nhận được
  cong_viec_id: number | null;
}
export interface SxLenhNhom {
  nguon_loai: string;          // "lsx" | "bai_ghep"
  nguon_ma: string;
  nguon_ten: string;
  khach_hang?: string | null;
  lsx_id: number | null;
  bai_ghep_id: number | null;
  som_nhat: string | null;     // giờ dự kiến sớm nhất trong các bước CỦA TỔ NÀY; null = chưa xếp
  muon_nhat: string | null;
  nhan_luc?: string | null;    // lúc tổ nhận việc sớm nhất của lệnh
  so_viec: number;
  digest: { released: number; running: number; paused: number; completed: number };
  routing?: SxRoutingBuoc[];   // chuỗi công đoạn đầy đủ; rỗng khi lệnh chỉ có một bước
  cong_viec: SxWorkItem[];
}
/** Vị trí trang + tổng số LỆNH (không phải tổng số bước) — đơn vị trang của bàn tổ là LỆNH, nhờ
 *  vậy một lệnh không bao giờ bị xé đôi qua hai trang. */
export interface SxTrang {
  trang: number;
  co_trang: number;
  tong: number;
}
export interface SxWorkItemsOut {
  team_id: number;
  nhom: string;                // "lenh" | "phang"
  trang?: SxTrang | null;      // chỉ có ở nhom="lenh"
  lenh?: SxLenhNhom[];         // chỉ có ở nhom="lenh"
  cong_viec?: SxWorkItem[];    // chỉ có ở nhom="phang" — hình CŨ, Gantt không phải sửa
}

/** Tình trạng người ở ô chọn giao việc / hỗ trợ chéo (BE `services/san_xuat/tinh_trang_nguoi`).
 *  `ly_do_nghi` ("Nghỉ dài hạn"/"Đang đình chỉ") và `nghi_phep` trùng ngày ⇒ máy chủ CHẶN;
 *  `dang_chay` ⇒ cảnh báo (chặn khi việc đích đang chạy); `viec_cho` chỉ để biết. */
export interface SxTinhTrangNguoi {
  ly_do_nghi: string | null;
  /** Đơn nghỉ phép ĐÃ DUYỆT, ngày "YYYY-MM-DD" gồm cả hai đầu. */
  nghi_phep: { tu: string; den: string }[];
  dang_chay: { cong_viec_id: number; ma: string | null; ten_cong_doan: string; to_ten: string | null } | null;
  /** Việc người đó CÓ TÊN trong tổ mà chưa chạy (`released`) / đang tạm dừng (`paused`) — tạm dừng trước. */
  viec_cho: {
    cong_viec_id: number; ma: string | null; ten_cong_doan: string; to_ten: string | null;
    trang_thai: "released" | "paused";
  }[];
}
export interface SxNhanVienChon extends SxTinhTrangNguoi {
  id: number;
  code: string | null;
  full_name: string;
  la_luong_khoan: boolean;
  co_tai_khoan: boolean;
}
export interface SxNhanVienChonListOut {
  team_id: number;
  /** Ngày XƯỞNG máy chủ xét nghỉ phép — so `nghi_phep` với ngày này, không lấy giờ trình duyệt. */
  hom_nay: string;
  nhan_vien: SxNhanVienChon[];
}

/** Ứng viên mời HỖ TRỢ CHÉO (§9) — thợ tổ khác, kèm nhãn tổ gốc. */
export interface SxHoTroUngVien extends SxTinhTrangNguoi {
  id: number;
  code: string | null;
  full_name: string;
  to_id: number | null;
  to_ten: string | null;
}
export interface SxHoTroUngVienListOut {
  team_id: number;
  hom_nay: string;
  nhan_vien: SxHoTroUngVien[];
}

/** Việc chờ tổ bấm trên một bàn tổ — việc GIỮA HAI TỔ mà bên tổ mình phải bấm (chấm đỏ trên dòng
 *  công đoạn + ô "chờ xác nhận" của bàn). */
export interface SxChoXacNhanBanGiao {
  id: number;
  nguon_cong_viec_id: number;
  nguon_ten: string;
  nguon_to_ten: string | null;
  dich_cong_viec_id: number;
  dich_ten: string;
  dich_to_ten: string | null;
  lsx_ma: string | null;
  so_luong: number;
  don_vi: string;
  de_xuat_luc: string | null;
  version: number;
  /** Công đoạn nằm trên bàn đang xem ⇒ chấm đỏ trên dòng + xác nhận trong ngăn chi tiết; `false`
   *  (thường là tổ cho mượn người) ⇒ liệt kê riêng khi bật ô "chờ xác nhận". */
  tren_ban: boolean;
}
export interface SxChoXacNhanHoTro {
  id: number;
  cong_viec_id: number;
  ten_cong_doan: string;
  lsx_ma: string | null;
  ho_ten: string;
  to_goc_ten: string | null;
  to_thuc_hien_ten: string | null;
  ngay_lam_viec: string;
  mo_ta: string | null;
  /** Bên đang chờ CHÍNH người xem: tổ cho mượn người (gốc) / tổ đang làm (thực hiện). */
  cho_ben_goc: boolean;
  cho_ben_thuc_hien: boolean;
  version: number;
  /** Công đoạn nằm trên bàn đang xem ⇒ chấm đỏ trên dòng + xác nhận trong ngăn chi tiết; `false`
   *  (thường là tổ cho mượn người) ⇒ liệt kê riêng khi bật ô "chờ xác nhận". */
  tren_ban: boolean;
}
/** Một lỗi KCS báo về tổ mà tổ chưa bấm "Đã xem" (KCS theo lệnh, mg 0306). Thông báo MỘT CHIỀU:
 *  không nhận / từ chối, không chặn gì. */
export interface SxChoXacNhanKcsLoi {
  loi_id: number;
  kcs_batch_id: number;
  cong_viec_id: number | null;
  to_id: number | null;
  ten_cong_doan: string;
  /** Bước KCS bắt lỗi khi lỗi quy về công đoạn trước; null = bắt ngay tại công đoạn này. */
  phat_hien_o?: string | null;
  lsx_ma: string | null;
  mo_ta: string | null;
  so_luong: number;
  don_vi: string | null;
  nguoi_kiem: string | null;
  luc: string | null;
  so_anh: number;
  version: number;
  /** Công đoạn nằm trên bàn đang xem ⇒ chấm đỏ trên dòng + xác nhận trong ngăn chi tiết; `false`
   *  (thường là tổ cho mượn người) ⇒ liệt kê riêng khi bật ô "chờ xác nhận". */
  tren_ban: boolean;
}
export interface SxChoXacNhan {
  team_id: number;
  ban_giao: SxChoXacNhanBanGiao[];
  ho_tro: SxChoXacNhanHoTro[];
  kcs_loi: SxChoXacNhanKcsLoi[];
}

/** Kết quả một lệnh ghi — đủ để cập nhật thanh + version lạc quan. */
export interface SxLenhKetQua {
  cong_viec_id: number;
  department_id: number | null;
  trang_thai: string;
  version: number;
}

/** Như `SxLenhKetQua` + con trỏ sang yêu cầu sửa chữa vừa gửi — để toast nói được
 *  "đã gửi YC-0042 tới tổ sửa chữa" thay vì một câu chung chung. */
export interface SxSuCoKetQua extends SxLenhKetQua {
  yeu_cau_id: number;
  yeu_cau_ma: string;
}

export interface SxPhanCongItem {
  id: number;
  employee_id: number;
  ho_ten: string;
  la_luong_khoan: boolean;
  co_tai_khoan: boolean;
  /** Ảnh tài khoản; null = chưa có tài khoản hoặc chưa đặt ảnh → vẽ chữ cái đầu. */
  avatar_url?: string | null;
  trang_thai: string;          // "active" | "removed"
}
export interface SxPhienChay {
  id: number;
  so_thu_tu: number;
  may_id: number | null;       // máy CHẠY TRONG PHIÊN NÀY — có thể khác phiên trước nếu đã đổi máy
  may_ten: string | null;
  bat_dau: string;
  ket_thuc: string | null;
  loai_dong: string | null;    // "tam_dung" | "doi_may" | "ket_thuc"
  ly_do_bat_dau_tre: string | null;
  ly_do: string | null;
}
export interface SxKhoangThamGia {
  id: number;
  phien_chay_id: number;
  employee_id: number;
  ho_ten: string;
  avatar_url?: string | null;
  bat_dau: string;
  ket_thuc: string | null;
}
// --- Giai đoạn 3: sản lượng · bàn giao · vật tư -------------------------------------------
export interface SxLotVao {
  id: number;
  nguon_batch_id: number | null;   // mẻ đầu ra của công đoạn trước
  so_luong: number;
  don_vi: string | null;
}
export interface SxBatch {
  id: number;
  bat_dau: string;
  ket_thuc: string;
  tong: number;
  tot: number;
  hong: number;
  don_vi: string | null;
  mo_ta_loi: string | null;
  ghi_chu: string | null;
  version: number;
  /** Máy ĐÃ CHẠY mẻ này — lấy từ PHIÊN chạy, không phải `may_id` hiện tại của công việc: đổi máy
   *  giữa chừng thì mỗi mẻ một máy. `null` = bước không dùng máy hoặc phiên chưa ghi máy. */
  may_ten: string | null;
  ca_ten: string | null;          // null = mẻ chạy NGOÀI mọi ca đã khai (một câu trả lời thật)
  so_nguoi: number;
  su_co: SxMeSuCo[];              // các lần dừng máy rơi vào cửa sổ mẻ
  /** Người có mặt trong mẻ — CHỈ danh sách, không số phút, không phần chia (spec 2026-09-18 §7.3:
   *  "ghi nhận thế thôi, đừng có chia bất cứ gì"). */
  nguoi_tham_gia: SxNguoiThamGiaBatch[];
  lot_vao: SxLotVao[];
  /** Mẻ đã đi theo một lần bàn giao chưa — form bàn giao chỉ liệt kê mẻ chưa giao. */
  da_ban_giao: boolean;
  /** CÔNG VIỆC KHOÁN của mẻ — ảnh chụp tên · ĐVT · đơn giá lúc ghi (§7.1). `viec_khoan_id` null =
   *  mẻ ghi trước 18/09/2026 ⇒ bày "chưa khai việc khoán", không đoán hộ. */
  viec_khoan_id: number | null;
  viec_khoan_ten: string | null;
  viec_khoan_don_vi: string | null;
  viec_khoan_don_vi_ten: string | null;
  viec_khoan_don_gia: number | null;
  /** Việc phát sinh đã ghi — KHÔNG cộng vào sản lượng. */
  phat_sinh: SxMePhatSinh[];
  /** Băng "Danh mục đã đổi so với lúc ghi mẻ" (§7.2b) — rỗng = còn khớp. */
  danh_muc_doi: SxMeDanhMucDoi[];
}
export interface SxMePhatSinh {
  id: number;
  phat_sinh_id: number;
  so_luong: number;
  ten: string | null;
  don_vi: string | null;
  don_vi_ten: string | null;
  don_gia: number | null;
}
/** Một ô lệch của băng mẻ. `mat` = dòng đã bị xoá khỏi danh mục — mẻ GIỮ ảnh chụp. */
export interface SxMeDanhMucDoi {
  truong: string;
  nhan: string;
  cu: string | null;
  moi: string | null;
  mat: boolean;
}
/** Một công việc khoán của tổ cho form Ghi mẻ: đơn giá · ĐVT · ghi chú + việc phát sinh. KHÔNG có
 *  thành tiền — bàn tổ không nhân gì. */
export interface SxViecPhatSinhChon {
  id: number; ten: string; don_gia: number; don_vi: string; don_vi_ten: string | null;
}
/** Cấu hình Khoán cố định của công đoạn. Không có thao tác chọn nguồn trong lúc ghi mẻ. */
export interface SxKhoanCongDoan {
  id: number;
  ten: string;
  don_gia: number;
  don_vi: string;
  don_vi_ten: string | null;
  phat_sinh: SxViecPhatSinhChon[];
}
export interface SxNguoiThamGiaBatch {
  employee_id: number;
  ho_ten: string;
  /** Tên tổ GỐC — chỉ có khi người này không thuộc tổ chủ mẻ (sang giúp qua hỗ trợ chéo). */
  to_ten?: string | null;
}
export interface SxMeSuCo {
  bat_dau: string | null;
  ket_thuc: string | null;
  ly_do: string | null;
}
export interface SxSanLuong {
  tong_tot: number;
  da_giao: number;
  batches: SxBatch[];
  /** Mốc chấm THỰC của bước — `so_luong_ra` đã rút theo tỉ lệ thực nhận; null khi bước không khai. */
  muc_tieu: number | null;
  /** Lượng bước này thật sự nhận được. null = không ai bàn giao tới — KHÁC hẳn với 0. */
  thuc_nhan: number | null;
  /** max(mục tiêu − tổng tốt, 0). null khi không có mục tiêu — KHÁC hẳn với 0. */
  con_thieu: number | null;
  don_vi: string | null;
}
export interface SxBanGiao {
  id: number;
  doi_tac_cong_viec_id: number | null;
  doi_tac_ten: string;
  cung_to: boolean;
  so_luong: number;
  don_vi: string;
  trang_thai: string;          // proposed | confirmed | adjusted
  khong_nhat_quan: boolean;
  version: number;
  batch_ids: number[];         // các mẻ của công đoạn nguồn đi theo lần giao này
  /** Ai đề xuất / ai xác nhận, lúc nào — hai bên thấy như nhau; tên từ tài khoản đã thao tác. */
  nguoi_de_xuat: string | null;
  de_xuat_luc: string | null;
  nguoi_xac_nhan: string | null;
  xac_nhan_luc: string | null;   // null = chưa xác nhận
  dieu_chinh: SxBanGiaoDieuChinh[];   // cũ → mới
}
/** Một lần điều chỉnh số đã xác nhận (§11.3). */
export interface SxBanGiaoDieuChinh {
  so_luong_truoc: number;
  so_luong_sau: number;
  mo_ta: string | null;
  khong_nhat_quan: boolean;      // lúc đó giảm dưới lượng công đoạn sau đã dùng
  nguoi: string | null;
  luc: string | null;
}
/** CHẶNG SAU theo routing lệnh — đích bàn giao hợp lệ duy nhất. Nhiều dòng khi bước sau tách lần
 *  chạy ("lần k/N") hoặc routing rẽ nhánh; rỗng = bước cuối lệnh — không bàn giao, thành phẩm vào kho qua KCS. */
export interface SxBanGiaoChangSau {
  cong_viec_id: number;
  ten_cong_doan: string;
  to_id: number | null;
  to_ten: string | null;
  du_kien_bat_dau: string | null;
  phan_doan_so: number;
  phan_doan_tong: number;
  loai_buoc: string;
  nha_cung_cap: string | null;
  trang_thai: string;
}
/** Một công đoạn TRƯỚC theo routing (từng lần chạy) — khối "Công đoạn trước" của tab Nhận. Kế
 *  hoạch/thực tế theo `don_vi` (đơn vị ra của nó); đã giao theo `don_vi_giao`. */
export interface SxCongDoanTruoc {
  cong_viec_id: number;
  ten_cong_doan: string;
  phan_doan_so: number;
  phan_doan_tong: number;
  to_ten: string | null;
  /** Bước trước cùng tổ + cùng lệnh: không cổng, không cần bàn giao (`dau_vao.cung_to_cung_lsx`). */
  cung_to: boolean;
  trang_thai: string;
  ke_hoach: number | null;
  don_vi: string | null;
  thuc_te: number;
  da_giao: number;
  da_xac_nhan: number;
  cho_xac_nhan: number;
  don_vi_giao: string | null;
}
/** Trần Σ số làm được = số đã nhận × hệ số quy đổi — máy chủ chặn mẻ vượt trần. */
export interface SxTranGhi {
  toi_da: number;
  da_nhan: number;
  he_so: number;
  don_vi_nhan: string;
  nguon_ten: string;
  /** Nguồn cùng tổ ⇒ `da_nhan` là SẢN LƯỢNG bước trước, không phải số đã bàn giao. */
  cung_to: boolean;
  da_ghi: number;
  con_ghi_duoc: number;
}
export interface SxVatTuNhan {
  voucher_id: number;
  ma: string;
  da_nhan: boolean;
  xac_nhan_luc: string | null;
}

// --- Đề nghị cấp vật tư theo công đoạn (spec-de-nghi-cap-vat-tu-cong-doan §6) -------------
// Khối `vat_tu_cap` TÁCH HẲN với `vat_tu` ở trên: `vat_tu` là các phiếu kho ĐÃ ghi sổ chờ tổ xác
// nhận NHẬN; `vat_tu_cap` là các LẦN tổ ĐỀ NGHỊ + bản đối chiếu kế hoạch/yêu cầu/thực xuất.
/** Một dòng nhu cầu KẾ HOẠCH của công đoạn (MRP). `_goc` = thang đơn vị gốc của danh mục. */
export interface SxVatTuCapKeHoach {
  hang_loai: string;
  hang_id: number;
  ten: string;
  dvt: string;
  sl: number;
  dvt_goc: string;
  sl_goc: number;
}
/** Một dòng CỦA RIÊNG một lần đề nghị — dùng điền sẵn form "Sửa đề nghị".
 *  KHÔNG lẫn với `SxVatTuCapDoiChieu.sl_yeu_cau` (cộng dồn qua MỌI lần). */
export interface SxVatTuCapDong {
  hang_loai: string;
  hang_id: number;
  ten: string;
  dvt: string;
  dvt_goc: string;
  sl_ke_hoach: number;
  sl_ke_hoach_goc: number;
  sl_yeu_cau: number;
  sl_yeu_cau_goc: number;
  ly_do_chenh_lech: string | null;
}
/** Một LẦN tổ gửi đề nghị. `loai`: "lan_dau" | "bo_sung". `stock_request_*` null khi mọi dòng = 0
 *  (tổ xác nhận không cần cấp ⇒ không đẻ yêu cầu kho). */
export interface SxVatTuCapLan {
  id: number;
  lan_so: number;
  loai: string;
  can_luc: string;
  stock_request_id: number | null;
  stock_request_ma: string | null;
  stock_request_trang_thai: string | null;
  created_by_id: number | null;
  updated_by_id: number | null;
  created_at: string;
  updated_at: string;
  dongs: SxVatTuCapDong[];
}
/** Một mặt hàng trong bản đối chiếu — số CỘNG DỒN qua mọi lần đề nghị. */
export interface SxVatTuCapDoiChieu {
  hang_loai: string;
  hang_id: number;
  ten: string;
  dvt: string;
  dvt_goc: string;
  sl_ke_hoach: number;
  sl_ke_hoach_goc: number;
  sl_yeu_cau: number;
  sl_yeu_cau_goc: number;
  sl_thuc_xuat: number;
  lech_ke_hoach: number;
  lech_thuc_te: number;
  cac_ly_do: { lan_so: number; ly_do: string }[];
}
export interface SxVatTuCap {
  ke_hoach: SxVatTuCapKeHoach[];
  cac_de_nghi: SxVatTuCapLan[];
  doi_chieu: SxVatTuCapDoiChieu[];
  /** Có giá trị ⇒ hiện nút "Sửa đề nghị" trỏ đúng lần đó; null ⇒ ẩn nút Sửa. */
  de_nghi_co_the_sua_id: number | null;
  /** true ⇒ hiện nút "Gửi đề nghị bổ sung". Loại trừ nhau với `de_nghi_co_the_sua_id`. */
  co_the_tao_bo_sung: boolean;
  /** true ⇒ kế hoạch lấy theo đường lùi từ LSX (trước 31/08/2026) — UI phải nói rõ. */
  du_lieu_cu: boolean;
}
export interface SxVatTuDeNghiDongIn {
  hang_loai: string;
  hang_id: number;
  dvt: string;
  sl_yeu_cau: number;
  ly_do_chenh_lech: string | null;
}
export interface SxVatTuDeNghiIn {
  /** GIỜ cần (ISO datetime), không phải ngày: kho soạn theo ca. */
  can_luc: string;
  lines: SxVatTuDeNghiDongIn[];
}
export interface SxVatTuDeNghiKetQua {
  de_nghi_id: number;
  stock_request_id: number | null;
  lan_so?: number;
}

// --- Giai đoạn 4: hỗ trợ chéo · phân bổ sản lượng → lương khoán ---------------------------
export interface SxHoTro {
  id: number;
  employee_id: number;
  ho_ten: string;
  to_goc_id: number | null;
  to_goc_ten: string | null;
  to_thuc_hien_id: number | null;
  to_thuc_hien_ten: string | null;
  ngay_lam_viec: string;
  trang_thai: string;          // pending_both | confirmed | cancelled
  mo_ta: string | null;
  da_xac_nhan_goc: boolean;
  da_xac_nhan_thuc_hien: boolean;
  /** Người đang xem bấm được gì trên CHÍNH dòng này — máy chủ tính theo quyền trọn tổ ở từng bên. */
  co_the_xac_nhan: boolean;
  co_the_huy: boolean;
  version: number;
}

export interface SxWorkItemChiTiet {
  cong_viec: SxWorkItem;
  trang_thai: string;
  version: number;
  /** Người đang xem làm được việc nào TRÊN CHÍNH công việc này (tổ của nó + mức own chỉ khi việc
   *  đang giao cho mình) — nút ghi trong drawer bật/tắt theo đây. */
  quyen: Partial<Record<Exclude<SxViecTo, "read">, boolean>>;
  /** Mức của từng quyền đó ở tổ của việc ("all" | "own"; thiếu khoá = không được cấp). Nút tắt vì
   *  "Của tôi" mà việc chưa giao cho mình thì drawer nói đúng lý do đó, không bảo đi xin quyền. */
  quyen_muc: Partial<Record<Exclude<SxViecTo, "read">, "all" | "own">>;
  khoan?: SxKhoanCongDoan | null;
  phan_cong: SxPhanCongItem[];
  phien_chay: SxPhienChay[];
  khoang_tham_gia: SxKhoangThamGia[];
  san_luong: SxSanLuong;
  ban_giao_di: SxBanGiao[];
  ban_giao_den: SxBanGiao[];
  /** Công đoạn trước theo routing; rỗng = công đoạn đầu lệnh. */
  cong_doan_truoc: SxCongDoanTruoc[];
  /** null = không trần (đầu lệnh, hệ số 0, hoặc nguồn giao khác đơn vị vào). */
  tran_ghi: SxTranGhi | null;
  /** Tên công đoạn trước chưa giao được gì sang — khác rỗng thì chưa bắt đầu được. */
  thieu_dau_vao: string[];
  ban_giao_chang_sau: SxBanGiaoChangSau[];
  vat_tu: SxVatTuNhan[];
  vat_tu_cap: SxVatTuCap;
  ho_tro: SxHoTro[];
}

// --- Kết quả các mặt GHI G3/G4 (đủ để cập nhật lạc quan; drawer refetch để lấy chi tiết) ---
export interface SxKetQuaNhanh {
  lsx_id: number;
  so_luong: number;
  don_vi: string;
  ban_giao_id: number | null;
}
export interface SxSanLuongKetQua {
  cong_viec_id: number;
  department_id: number | null;
  trang_thai: string;
  version: number;
  batch_id?: number | null;
  ket_qua_lsx?: SxKetQuaNhanh[];
}
export interface SxBanGiaoKetQua {
  ban_giao_id: number;
  trang_thai_ban_giao: string;
  so_luong: number;
  khong_nhat_quan: boolean;
  version: number;
  nguon_cong_viec_id: number;
  dich_cong_viec_id: number | null;
  nguon_department_id: number | null;
  dich_department_id: number | null;
}
export interface SxVatTuNhanKetQua {
  voucher_id: number;
  department_id: number;
}
export interface SxHoTroKetQua {
  ho_tro_id: number;
  cong_viec_id: number;
  to_goc_id: number | null;
  to_thuc_hien_id: number | null;
  trang_thai: string;
  notify_user_ids: number[];
}

// Body các mặt GHI (§7). `expected_version` = khoá lạc quan; `ly_do` của tạm-dừng BẮT BUỘC.
export interface SxPhanCongIn { employee_id: number; expected_version?: number | null }
export interface SxGoPhanCongIn { ly_do?: string | null; expected_version?: number | null }
export interface SxBatDauIn { expected_version?: number | null }
export interface SxDoiMayIn { may_id: number; ly_do?: string | null; expected_version?: number | null }
/** Một máy trong ô "Đổi máy": chỉ máy làm được công đoạn của việc, kèm tình trạng LÚC NÀY — cùng
 *  nguồn cột Trạng thái màn Thiết bị (`services/may_trang_thai.py`), nhãn dựng sẵn ở máy chủ. */
export interface SxMayDoi {
  id: number;
  ma: string;
  ten: string | null;
  loai_may: string | null;
  /** ranh | co_phieu_sua | dang_chay | bao_tri | may_dung | khoa */
  trang_thai: string;
  nhan: string;
  chi_tiet: string | null;
}
export interface SxMayDoiOut {
  items: SxMayDoi[];
  /** true = danh sách đã bị công đoạn thu hẹp; false = công đoạn chưa khai máy, đang hiện mọi máy. */
  theo_cong_doan: boolean;
}
export interface SxTamDungIn { ly_do: string; expected_version?: number | null }
export interface SxKetThucIn { expected_version?: number | null }
/** Báo sự cố tại tổ (31/08/2026) → ghi thẳng vào hộp thư "Báo máy hỏng" của tổ sửa chữa.
 *  KHÔNG có ô "máy": server lấy đúng máy của công việc đang chạy. `mo_ta` bắt buộc khi
 *  `dung_san_xuat` (mốc mất giờ máy của lệnh). `muc_do` lấy từ `NHAN_MUC_DO` của kyThuatMay. */
export interface SxSuCoIn {
  bo_phan_hong: string;
  mo_ta?: string | null;
  muc_do: string;
  dung_san_xuat: boolean;
  expected_version?: number | null;
}

// Body G3/G4
export interface SxLotVaoIn {
  nguon_batch_id: number;
  so_luong: number;
  don_vi?: string | null;
}
export interface SxBatchIn {
  bat_dau: string;
  ket_thuc: string;
  tong: number;
  tot: number;
  hong?: number;
  don_vi?: string | null;
  mo_ta_loi?: string | null;
  ghi_chu?: string | null;
  lot_vao?: SxLotVaoIn[];
  /** Việc phát sinh đã làm trong mẻ — KHÔNG cộng vào sản lượng. */
  phat_sinh?: { phat_sinh_id: number; so_luong: number }[];
}
export interface SxBanGiaoDeXuatIn {
  dich_cong_viec_id: number;           // một trong các chặng sau theo routing
  don_vi?: string | null;
  batch_ids?: number[];                // mẻ đi theo lần giao (bắt buộc khi còn mẻ chưa giao)
}                                      // số lượng máy chủ tự tính = tổng tốt của mẻ chọn
/** Sửa lần giao còn chờ xác nhận = đặt lại danh sách mẻ; số lượng tính lại theo mẻ. */
export interface SxBanGiaoSuaIn { batch_ids: number[]; expected_version?: number | null }
export interface SxBanGiaoXacNhanIn { expected_version?: number | null }
export interface SxBanGiaoDieuChinhIn { so_luong_sau: number; mo_ta?: string | null; expected_version?: number | null }
export interface SxVatTuXacNhanIn { voucher_id: number; department_id: number; ghi_chu?: string | null }
export interface SxHoTroDeXuatIn { employee_id: number; ngay_lam_viec: string; mo_ta?: string | null }
export interface SxHoTroXacNhanIn { expected_version?: number | null }
export interface SxHoTroHuyIn { ly_do?: string | null; expected_version?: number | null }

// ── KCS theo LỆNH (mg 0306, docs/design-kcs-theo-lenh.md) ─────────────────────
// Mirror `schemas/san_xuat.py` (Kcs*Out). MỘT kiểu kiểm duy nhất: KCS mở lệnh → bấm công đoạn →
// ghi Số đạt / Số lỗi. Không trừ số, không đổi trạng thái công việc.
export interface SxKcsAnh {
  id: number;
  file_name: string;
  file_url: string;
  file_type?: string | null;
}
export type SxKcsKetLuan = "dat" | "dat_mot_phan" | "khong_dat";
/** Trạng thái gửi kho suy từ các yêu cầu nhập kho neo vào lần kiểm — "khong_ap_dung" cho công đoạn
 *  không phải công đoạn cuối của nhóm. */
export type SxKcsTrangThaiGuiKho = "chua_gui" | "dang_cho" | "da_nhap" | "khong_ap_dung";
/** Một dòng snapshot tiêu chí checklist KCS (chụp lúc phát hành LSX) — xem `kcs_tieu_chi_json`. */
export interface SxKcsChiTietTieuChi {
  tieu_chi_id?: number | null;
  ma?: string | null;
  ten?: string | null;
  huong_dan?: string | null;
  bat_buoc: boolean;
  thu_tu: number;
}
export interface SxKcsChecklistKetQuaIn {
  thu_tu: number;
  dat: boolean;
  ghi_chu?: string | null;
}
/** Phần LỖI của một lần kiểm. `da_xem_luc` null = tổ bị kiểm chưa bấm "Đã xem". */
export interface SxKcsLanKiemLoi {
  id: number;
  mo_ta: string | null;
  so_luong: number;
  don_vi: string | null;
  to_chiu_id: number | null;
  to_chiu_ten?: string | null;
  /** Công đoạn CHỊU lỗi — khác công đoạn của lần kiểm khi KCS quy lỗi về bước trước. */
  cong_doan_id?: number | null;
  cong_doan_ten?: string | null;
  da_xem_luc: string | null;
  nguoi_xem: string | null;
  anh: SxKcsAnh[];
}
/** Một lần kiểm đã ghi — người kiểm là tài khoản đã bấm lưu (server chốt). */
export interface SxKcsLanKiem {
  id: number;
  /** Công đoạn được kiểm — nơi KCS bắt lỗi. */
  cong_viec_id?: number | null;
  cong_doan_ten?: string | null;
  nguoi_kiem: string | null;
  luc: string | null;
  so_dat: number;
  so_loi: number;
  don_vi: string | null;
  ket_luan: SxKcsKetLuan;
  /** Kết quả tick `[{thu_tu, dat, ghi_chu}]`, khớp theo `thu_tu` với checklist của công đoạn. */
  checklist: SxKcsChecklistKetQuaIn[];
  ghi_chu: string | null;
  version: number;
  loi: SxKcsLanKiemLoi[];
}
/** Mục "Kết quả KCS" của một công đoạn (drawer bàn tổ) — lần kiểm mới nhất trước. */
export interface SxKcsCongViec {
  cong_viec_id: number;
  la_kcs_cuoi: boolean;
  /** Chỉ công đoạn cuối: số tốt tổ ghi, KCS đạt, đã đề nghị nhập kho (công đoạn giữa không có "đạt"). */
  cuoi?: { tot: number; dat: number; da_de_nghi_kho: number; don_vi: string | null } | null;
  checklist: SxKcsChiTietTieuChi[];
  lan_kiem: SxKcsLanKiem[];
  /** Lần kiểm ở bước SAU có lỗi quy về công đoạn này — mỗi lần chỉ mang lỗi của công đoạn này. */
  lan_kiem_buoc_sau?: SxKcsLanKiem[];
}
export interface SxKcsCuoiTomTat {
  /** Σ tốt tổ đã ghi ở công đoạn cuối — trần của số được đề nghị nhập kho. */
  tot: number;
  dat: number;
  da_yeu_cau: number;
  con_gui_kho: number;
}
export interface SxKcsLenhItem {
  lsx_id: number;
  ma: string;
  ten: string;
  khach: string | null;
  nhom_ma: string | null;
  nhom_trang_thai: string | null;
  so_cong_doan: number;
  so_da_kiem: number;
  so_loi: number;
  cuoi: SxKcsCuoiTomTat | null;
}
export interface SxKcsLenhList {
  items: SxKcsLenhItem[];
  tong: number;
  trang: number;
  co_trang: number;
}
export interface SxKcsLenhDau {
  id: number;
  ma: string;
  ten: string;
  khach: string | null;
  nhom_id: number | null;
  nhom_ma: string | null;
  nhom_trang_thai: string | null;
}
/** Một công đoạn trong chuỗi của lệnh — tổ, trạng thái chạy, tốt/hỏng tổ đã ghi, các lần kiểm. */
export interface SxKcsCongDoan {
  cong_viec_id: number;
  ten: string;
  phan_doan_so: number;
  phan_doan_tong: number;
  to_id: number | null;
  to_ten: string;
  /** `released` | `running` | `paused` | `completed` (enum công việc). */
  trang_thai: string;
  tot: number;
  hong: number;
  don_vi: string | null;
  la_kcs_cuoi: boolean;
  checklist: SxKcsChiTietTieuChi[];
  so_lan_kiem: number;
  tong_dat: number;
  tong_loi: number;
  /** Σ đã đề nghị nhập kho (yêu cầu còn hiệu lực), quy về đơn vị của công đoạn. */
  da_yeu_cau_kho: number;
  /** Chỉ công đoạn cuối: min(Σ đạt, Σ tốt) − đã đề nghị — > 0 thì bày nút "Tạo yêu cầu nhập kho". */
  con_gui_kho: number;
  /** Chỉ công đoạn cuối: các dòng yêu cầu NHẬP thật (DNN…) đã gửi — số theo đơn vị của món. */
  yeu_cau_kho: SxKcsYeuCauKho[];
  lan_kiem: SxKcsLanKiem[];
  /** Lỗi KCS bắt ở bước sau mà quy về công đoạn này — gộp theo bước bắt; đơn vị là của bước đó. */
  loi_buoc_sau?: { phat_hien_o: string; don_vi: string | null; so_luong: number }[];
  /** Số kế hoạch đầu ra của công đoạn (đơn vị `don_vi`). */
  so_luong_ra: number | null;
  /** Tên máy của bước (null với bước nội bộ tổ / chưa gán máy). */
  may: string | null;
  /** Dặn dò kỹ thuật kế hoạch ghi cho bước. */
  ghi_chu_ky_thuat: string | null;
  /** Ảnh chụp quy cách lúc phát hành — cùng thẻ với ngăn bàn tổ. */
  quy_cach: SxQuyCachThe | null;
  /** Mẻ tổ đã ghi, mới nhất trước. */
  me: SxKcsMe[];
}
/** Một mẻ tổ đã ghi, bày trong form kiểm KCS — `so_luong` là số làm được. */
export interface SxKcsMe {
  id: number;
  bat_dau: string | null;
  ket_thuc: string | null;
  so_luong: number;
  don_vi: string | null;
  viec: string | null;
  nguoi_ghi: string | null;
  nguoi: string[];
}
/** Một dòng yêu cầu NHẬP kho thành phẩm sinh từ công đoạn cuối. `trang_thai` là trạng thái yêu cầu
 *  kho: `approved` (chờ kho) · `preparing` · `partial` · `done` · `cancelled` · `rejected`. */
export interface SxKcsYeuCauKho {
  request_id: number;
  ma: string;
  trang_thai: string;
  sl_de_nghi: number;
  sl_da_nhan: number;
  don_vi: string | null;
  tao_luc: string | null;
}
export interface SxKcsChuoiCongDoan {
  lsx: SxKcsLenhDau;
  cong_doan: SxKcsCongDoan[];
}
export interface SxKcsKiemIn {
  /** Bỏ trống = máy chủ tự suy: đạt = phần tổ đã làm mà chưa kiểm − số lỗi (form KCS chỉ gõ lỗi). */
  so_dat?: number | null;
  so_loi: number;
  checklist?: SxKcsChecklistKetQuaIn[] | null;
  ghi_chu?: string | null;
  /** Bắt buộc khi `so_loi > 0`, kèm ≥1 ảnh trong `files`. */
  loi_mo_ta?: string | null;
  files?: File[];
  /** Lỗi theo DÒNG — mỗi dòng quy về một công đoạn (null = công đoạn đang kiểm). Có thì thay
   *  `loi_mo_ta` + `files`; `so_loi` phải bằng Σ các dòng. */
  loi?: SxKcsDongLoiIn[];
  /** Lệnh KCS đang mở — máy chủ kiểm công đoạn chịu lỗi thuộc cùng lệnh, đứng trước. */
  lsx_id?: number | null;
}
export interface SxKcsDongLoiIn {
  cong_viec_id: number | null;
  so_luong: number;
  mo_ta: string;
  files: File[];
}
export interface SxKcsKiemKetQua {
  kcs_batch_id: number;
  loi_id: number | null;
  cong_viec_id: number;
  department_id: number | null;
  lsx_id: number | null;
  nhom_id: number | null;
  ten_cong_doan: string;
  so_dat: number;
  so_loi: number;
  ket_luan: SxKcsKetLuan;
  version: number;
  /** Phần lỗi quy về công đoạn đứng trước — đã báo tổ đó. */
  bao_loi_nguon?: { cong_viec_id: number; department_id: number | null; ten_cong_doan: string; so_loi: number }[];
}
export interface SxKcsDaXemKetQua {
  loi_id: number;
  kcs_batch_id: number;
  cong_viec_id: number | null;
  department_id: number | null;
  da_xem_luc: string | null;
  nguoi_xem: string | null;
  version: number;
}
export interface SxKcsDieuChinhIn {
  so_luong_dat: number;
  so_luong_khong_dat: number;
  checklist_ket_qua?: SxKcsChecklistKetQuaIn[] | null;
  ghi_chu?: string | null;
  expected_version: number;
}
export interface SxKcsDieuChinhKetQua {
  kcs_batch_id: number;
  cong_viec_id: number;
  so_luong_nhan: number;
  so_luong_dat: number;
  so_luong_khong_dat: number;
  ket_luan: SxKcsKetLuan;
  version: number;
}
export interface SxKcsBaoCaoTheoNgayRow {
  ngay: string;
  tong_nhan: number;
  tong_dat: number;
  tong_loi: number;
}
export interface SxKcsBaoCaoCongDoanRow {
  ten_cong_doan: string;
  tong_so_luong: number;
}
export interface SxKcsBaoCaoToRow {
  to_id: number;
  ten: string;
  tong_so_luong: number;
}
/** Một dòng bảng "Kết quả đã ghi" — MỘT lần kiểm, đã áp đúng filter+scope của báo cáo. */
export interface SxKcsBaoCaoLichSuRow {
  kcs_batch_id: number;
  cong_viec_id: number;
  thoi_diem?: string | null;
  so_luong_dat: number;
  so_luong_khong_dat: number;
  don_vi: string;
  nguon_ma: string;
  nguon_ten: string;
  ten_cong_doan: string;
  nguoi_ghi?: string | null;
  trang_thai_gui_kho: SxKcsTrangThaiGuiKho;
}
/** Một công đoạn cho ô lọc dashboard KCS (`GET /kcs/cong-doan`) — chỉ mã/tên/giai đoạn. */
export interface SxKcsCongDoanLoc {
  id: number;
  ma: string;
  ten: string;
  nhom?: string | null;
}
export interface SxKcsBaoCao {
  tong_luot: number;
  tong_nhan: number;
  tong_dat: number;
  tong_loi: number;
  ty_le_dat?: number | null;
  theo_ngay: SxKcsBaoCaoTheoNgayRow[];
  cong_doan: SxKcsBaoCaoCongDoanRow[];
  to: SxKcsBaoCaoToRow[];
  lich_su: SxKcsBaoCaoLichSuRow[];
}
export interface SxKcsBaoCaoParams {
  tu?: string | null;
  den?: string | null;
  lsx_id?: number | null;
  tu_khoa?: string | null;
  cong_doan_id?: number | null;
}

// ── Nhập kho thành phẩm: yêu cầu NHẬP thật của kho ────────────────────────────
export interface SxNhapKhoTpDong {
  hang_id: number;
  ma_hang: string;
  ten_hang: string;
  dvt: string | null;
  sl_de_nghi: number;
  /** Giá bán lấy từ đơn (đ / đơn vị món) — null khi dòng đơn chưa có thành tiền. */
  don_gia_ban: number | null;
}
/** "Tạo yêu cầu nhập kho" trên công đoạn cuối — MỘT yêu cầu NHẬP của kho thật (mã DNN…). `so_luong`
 *  theo đơn vị ra của công đoạn (số KCS vừa gửi); `dong[].sl_de_nghi` theo đơn vị của món thành phẩm. */
export interface SxNhapKhoYcKetQua {
  request_id: number;
  ma: string;
  cong_viec_id: number;
  so_luong: number;
  don_vi: string | null;
  dong: SxNhapKhoTpDong[];
}
// ── G5: Đóng nhóm §16 + đóng thiếu §13.3 ─────────────────────────────────────
export interface SxDongNhomDieuKienItem {
  ma: string;
  ten: string;
  dat: boolean;
  chi_tiet: string;
}
export interface SxDongNhomDieuKien {
  nhom_id: number;
  order_id?: number | null;
  trang_thai: string;
  version: number;
  du_dong_du: boolean;
  du_dong_thieu: boolean;
  dieu_kien: SxDongNhomDieuKienItem[];
  /** Mức NHÓM: Σ so_luong_ra của các công việc KCS cuối (mọi phân đoạn). null khi không bước KCS cuối
   *  nào khai số — lúc đó điều kiện `dat_muc_tieu` chưa đạt, nhóm chỉ đóng thiếu được. */
  muc_tieu: number | null;
  /** Σ số KCS ĐẠT của chính các công việc KCS cuối đó — cổng đóng ĐỦ so số này với `muc_tieu`. */
  da_dat: number | null;
  /** max(muc_tieu − da_dat, 0). Không có đơn vị ở mức nhóm (nhiều bước có thể khác đơn vị). */
  con_thieu: number | null;
}
/* `SxThuongToTruong` GỠ 11/09/2026 (mg `0297`): bảng `san_xuat_thuong_to_truong` và chuỗi ghi
   thưởng lúc ĐÓNG NHÓM đã xoá — thưởng/phạt tổ trưởng là TIỀN, mà sản xuất thôi giữ tiền. Bảng bậc
   `piece_leader_bonus_brackets` và cột lương `thuong_to_truong` cũng GỠ 13/09/2026 (mg `0300`). */
export interface SxDongThieuIn {
  expected_version?: number | null;
}
export interface SxDongNhomKetQua {
  nhom_id: number;
  order_id?: number | null;
  trang_thai: string;
  kieu: "du" | "thieu";
  version: number;
}


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
  san_pham_tom_tat?: string | null;
}
export interface HangChoOut {
  items: HangChoItem[];
  /** TỔNG đơn còn nợ lệnh trên MÁY CHỦ, không phải số dòng của trang. */
  total: number;
  page: number;
  size: number;
}

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
  /** Ý ĐỊNH của sale về khuôn, chép từ phiếu tính giá lúc dựng lệnh + câu nhắc khi nó LỆCH với con
   *  dao kế hoạch đã chốt (`khuon_lech = null` là không lệch). Nhắc chứ không chặn. */
  khuon_nguon: "co_san" | "lam_moi" | null;
  khuon_phi: number;
  khuon_lech: string | null;
  // Đơn vị VÀO ≠ RA là chuyện thường ở bế/xén — hệ số quy đổi nối hai đầu.
  so_luong_vao: number; so_luong_ra: number;
  don_vi_vao: string; don_vi_ra: string; he_so_quy_doi: number;
  /** Bước có nằm trên DÒNG GIẤY không (server quyết theo cờ trạm của danh mục Đơn vị — FE không
   *  tự suy từ mã được). `false` ⇒ số lượng KHÔNG tự tính và bù hao không cộng vào số giấy. */
  tren_dong_giay: boolean;
  /* `don_vi_san_luong` · `loi_quy_doi` · `san_luong_dien_giai` GỠ 18/09/2026 (mg `0324`) cùng
     công thức sản lượng ra của công đoạn — bước ngoài dòng giấy nay là số tự khai ở bước. */
  hao_hut: number; hao_hut_pct: number; ty_le_hao_hut: number; so_luot_chay: number;
  /** SỐ GIỜ KẾ HOẠCH của bước TỔ — ô gõ tay, mặc định 0 (mg `0319`). Bước máy luôn 0. Kíp chuẩn
   *  + năng suất chép từ đầu việc GỠ 18/09/2026 (mg `0320`, `0321`). */
  so_gio_ke_hoach: number;
  // `setup_phut` + `chay_phut` là số DẪN XUẤT (chuẩn bị + tốc độ kế thừa từ máy);
  // `phat_sinh_phut` = ô "Thời gian khác".
  setup_phut: number;
  chay_phut: number | null;
  phat_sinh_phut: number;
  // derived: chiếm máy theo tốc độ TB (Gantt đặt lịch) + dải nhanh/chậm nhất của máy.
  chiem_may_phut: number; chiem_may_phut_min: number; chiem_may_phut_max: number;
  tong_phut: number;
  thoi_luong_dien_giai: Record<string, unknown>;
  phu_thuoc_step_keys: string[];
  /** `tu_dong` = dòng máy bung khi chọn công việc khoán (mg 0191) ⇒ lần bung sau thay được.
   *  false = người tự thêm / đã sửa số ⇒ máy chừa ra. */
  /** `hang_loai` nói món nằm ở DANH MỤC nào: `"giay"` = NVL chính người lập lệnh tự chọn,
   *  `"vat_tu"` = mực/keo/màng. `vat_tu_id` là id TRONG danh mục đó ⇒ so sánh phải đi theo CẶP,
   *  Giấy #7 và Vật tư #7 là hai món khác nhau (08/09/2026). */
  vat_tus: { id: number; hang_loai?: "giay" | "vat_tu"; vat_tu_id: number; vat_tu_ma: string;
             vat_tu_ten: string; don_vi: string; so_luong: number; tu_dong?: boolean }[];
  ghi_chu: string | null;
  /* Đầu việc ghim ở bước (`khoan_rate_id` · `khoan_ten` · `khoan_chon_duoc`) GỠ 18/09/2026 (mg
     `0320`): việc khoán chọn LÚC GHI MẺ ở bàn tổ, lọc theo tổ của bước. */
  /** Lượng TÍNH SẴN cho mọi vật tư theo bước này — chọn món nào ở drawer là điền số ngay.
   *  Món chưa tính ra được vẫn CÓ trong mảng với `so_luong: null` + `ly_do` chỉ chỗ khai công
   *  thức ⇒ ô để trống cho người khai (không đoán), nhưng người dùng biết vì sao nó trống. */
  vat_tu_goi_y: {
    hang_loai?: "giay" | "vat_tu";
    vat_tu_id: number;
    so_luong: number | null;
    dien_giai: string | null;
    ly_do: string | null;
  }[];
  /** Số ĐÚNG RA phải là theo danh mục HIỆN TẠI, chỉ có khi KHÁC số đã lưu. null = không lệch.
   *  Lệnh là ảnh chụp nên server không tự đè — màn gạch số cũ rồi mời bấm Lưu. */
  so_luong_vao_moi: number | null;
  so_luong_ra_moi: number | null;
}
export interface LsxCongDoanBody extends Partial<LsxThueNgoaiFields> {
  step_key?: string; thu_tu?: number; cong_doan_id?: number | null; ten?: string; nhom?: string | null;
  /* `bat_buoc` GỠ 07/09/2026 — server không nhận nữa, mọi bước routing đều bắt buộc (mg 0275). */
  loai_buoc?: LsxLoaiBuoc;
  department_id?: number | null; may_id?: number | null;
  /** Con dao của bước (`khuon_be.id`). null = bỏ gán. */
  khuon_be_id?: number | null;
  so_luong_vao?: number; so_luong_ra?: number;
  don_vi_vao?: string; don_vi_ra?: string; he_so_quy_doi?: number;
  hao_hut?: number; hao_hut_pct?: number; so_luot_chay?: number;
  /** Số giờ kế hoạch của bước TỔ — số thập phân ≥ 0, để 0 là hợp lệ (mg `0319`). */
  so_gio_ke_hoach?: number;
  setup_phut?: number;
  phat_sinh_phut?: number;
  phu_thuoc_step_keys?: string[];
  /** Bỏ trống `hang_loai` là server hiểu `"vat_tu"` — giữ đúng nghĩa client cũ. */
  vat_tus?: { hang_loai?: "giay" | "vat_tu"; vat_tu_id: number; so_luong: number }[];
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
  /** Tổ MẶC ĐỊNH (tổ đầu danh sách) + cả danh sách tổ phụ trách công đoạn để ô tổ chọn trong đó. */
  department_id: number | null;
  department_ids: number[];
  don_vi_vao: string; don_vi_ra: string; he_so_quy_doi: number;
  /** Cặp đơn vị trên có nằm trên DÒNG GIẤY không — server quyết theo cờ trạm của danh mục Đơn vị.
   *  Phải áp CÙNG LÚC với hai ô đơn vị: cờ là thuộc tính của cặp đơn vị, không phải của dòng. */
  tren_dong_giay: boolean;
  /** Cờ DỤNG CỤ của công đoạn mới — ô chọn khuôn của bước lọc kho theo `tooling_type`, mà client
   *  không suy ra được nó từ tên. Áp cùng lúc, nếu không thì bước vừa đổi sang công đoạn cần
   *  khung lụa vẫn bày dao BẾ. */
  requires_tooling: boolean;
  tooling_type: string | null;
  setup_phut: number;
  /** GỢI Ý máy của công đoạn mới — chỉ có số khi công đoạn khai ĐÚNG MỘT máy còn dùng. Client chỉ
   *  áp khi dòng đang TRỐNG máy: máy người dùng đã chọn không bị đổi. */
  may_id_goi_y: number | null;
}
/** Giờ chạy của MỘT bước theo bộ số ĐANG SỬA trên drawer — server tính THỬ rồi vứt, không ghi
 *  DB. Phần tiền công gỡ 11/09/2026. */
export interface LsxXemTruocBuoc {
  step_key: string;
  may_id: number | null;
  chiem_may_phut: number;
  thoi_luong_dien_giai: Record<string, unknown>;
}
/** DÒNG CHẢY của MỘT bước NẾU đổi/chèn công đoạn — server chạy đúng đường Lưu routing rồi
 *  rollback. Khớp `step_key` client gửi lên (kể cả khoá tạm `r{n}` của bước mới chèn). */
export interface LsxXemTruocRoutingBuoc {
  step_key: string;
  so_luong_vao: number; so_luong_ra: number;
  don_vi_vao: string | null; don_vi_ra: string | null; he_so_quy_doi: number;
  hao_hut: number; hao_hut_pct: number;
  tren_dong_giay: boolean;
}
/** 1 bước trong payload xem-trước routing — chỉ trường chuỗi ngược cần, không mang vật tư/khoán. */
export interface LsxXemTruocRoutingRow {
  step_key?: string | null; thu_tu?: number | null; cong_doan_id?: number | null;
  ten?: string | null; nhom?: string | null; loai_buoc?: string | null;
  department_id?: number | null; may_id?: number | null;
}

/* `LsxDauViecOption` GỠ 18/09/2026 (mg `0320`) cùng ô "Đầu việc thợ làm" của bước và endpoint
   `dau-viec-options`. */
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
export interface LsxListOut {
  items: LsxListItem[];
  /** TỔNG lệnh khớp bộ lọc trên MÁY CHỦ — không phải `items.length` (chỉ là 1 trang). */
  total: number;
  page: number;
  size: number;
  /** trạng thái → số lệnh, tính với CÙNG bộ lọc nhưng BỎ lọc trạng thái, nên tab đang không
   *  được chọn vẫn khoe đúng số của nó. Khoá `all` = tổng mọi trạng thái. */
  facets: Record<string, number>;
}
/** Nguồn hai ô lọc "Đơn hàng" / "Khách hàng" — chỉ gồm đơn ĐANG có lệnh. */
export interface LsxBoLocOut {
  orders: { id: number; order_no: string; customer_id: number | null; customer_name: string | null }[];
  customers: { id: number; name: string }[];
}
/** Một chấm trên hàng đèn tổng quan của bảng lệnh (Đợt 1 redesign 18/08/2026).
 *  `ok` = **không vẽ chấm** — 20 lệnh × 3 chấm mà đa số xanh thì mắt không bắt được cái đỏ. */
export interface LsxDenItem {
  muc: "do" | "vang" | "ok";
  chu: string;
  /** Bấm chấm là tới thẳng chỗ sửa. `null` khi `ok`. */
  nhay: { man: string; id: number } | null;
}
/** Bốn thứ bảng lệnh CHƯA nói. Hạn cố ý không có đèn: cột `Hạn` đã tô màu và cột `CĐ` đã đỏ khi
 *  lệnh chưa có công đoạn. */
export interface LsxDen {
  vat_tu: LsxDenItem;
  may_gio: LsxDenItem;
  nguoi: LsxDenItem;
  /** Lệnh còn giữ số của lần bung, danh mục Công đoạn nay đã khác. Luôn VÀNG — giữ số cũ không
   *  chặn gì cả, chỉ là số đã cũ. Sửa ngay trong màn lệnh nên không có chỗ `nhay` riêng. */
  danh_muc: LsxDenItem;
}
export interface LsxTongQuanOut {
  items: { lsx_id: number; slack_ngay: number | null; den: LsxDen }[];
}
export interface LsxDetail {
  id: number; ma: string; loai: string; lsx_goc_id: number | null; ten: string;
  /** Nhãn nhóm đọc sống từ dòng đơn — luôn đúng hiện tại, khác `quy_cach_json` là ảnh chụp. */
  nhom: string | null;
  trang_thai: LsxTrangThai;
  order_id: number; order_line_id: number; order_no: string | null;
  /** Trạng thái ĐƠN gắn với lệnh — dùng để ẩn tab Công đoạn khi đơn đã hủy. */
  order_status: string | null;
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
  /** "Lưu ý sản xuất (gửi xưởng)" đọc SỐNG từ đơn hàng — nguồn DUY NHẤT của ô lưu ý thợ thấy. */
  luu_y_gui_xuong: string | null;
  cong_doans: LsxCongDoan[];
  /** Mã CHẶN nút "Sẵn sàng lập kế hoạch" (dịch bằng `LSX_THIEU_LABELS`). Rổ cảnh báo mềm
   *  `canh_bao` đã gỡ cả hai đầu 25/08/2026 — không màn nào hiện nó. */
  thieu: string[];
  lead_time: LsxLeadTime | null;
  /* `khoan_tien_tong` (Σ "Công thợ dự kiến" của lệnh) GỠ 11/09/2026. */
  /** Chừa tách chiều do server tính (`chua_theo_chieu`) — đừng cộng lại ở FE. */
  chua_dai: number;
  chua_rong: number;
  /** Lệnh đang ghép chung tờ với ai. `null` = in riêng. Khi có, THÔNG SỐ TỜ (máy in, giấy, khổ
   *  tờ in, số con) do BÀI quyết — sửa ở màn lệnh không có tác dụng. */
  bai_ghep: LsxBaiGhep | null;
  /** Lệnh đang GIỮ CHỖ vật tư ⇒ server chặn sửa số lượng / quy cách / routing và xoá lệnh, chặn
   *  CẢ bản xem trước. Màn lệnh phải khoá bảng routing và nói đường lùi ngay từ đầu — không thì
   *  sửa xong mới ăn 409 lúc bấm Lưu, còn xem-trước 409 im lặng làm số trên bảng đứng im. */
  giu_cho_bat: boolean;
  /** Danh mục Công đoạn đã đổi sau lần lệnh này lấy số. `null` = còn khớp, KHÔNG hiện băng. */
  danh_muc_doi?: DanhMucDoiOut | null;
}
/** Một dòng vật tư lệch. Để trống một bên tuỳ rổ: rổ THÊM chưa có số cũ, rổ BỎ không còn số mới. */
export interface DanhMucDoiVatTu {
  hang_loai?: "giay" | "vat_tu";
  vat_tu_id: number; ma: string | null; ten: string | null; don_vi: string | null;
  so_luong_cu: number | null; so_luong_moi: number | null;
}
export interface DanhMucDoiBuoc {
  buoc_id: number; step_key: string | null; thu_tu: number; ten: string;
  /* Ba khoá KHOÁN (`khoan` · `khoan_chua_chon` · `khoan_mo_coi`) GỠ 18/09/2026 (mg `0320`): bước
     thôi ghim đầu việc. Băng còn VẬT TƯ của công đoạn và MÁY bị gỡ khỏi công đoạn. */
  vat_tu_them: DanhMucDoiVatTu[];
  /** Bước đang có mà danh mục không còn bung. CHỈ BÁO — nút cập nhật không xoá dòng nào. */
  vat_tu_bo: DanhMucDoiVatTu[];
  vat_tu_lech: DanhMucDoiVatTu[];
  may_canh_bao: string | null;
}
/** Danh mục Công đoạn đã đổi sau lúc lệnh chụp ảnh. `null` khi lệnh còn khớp hết danh mục.
 *
 *  Server so NỘI DUNG (dựng lại ảnh "nếu bung bây giờ" rồi đối chiếu), KHÔNG so `updated_at` như
 *  băng cùng loại ở phiếu tính giá — công thức khoán/định mức nằm ở bảng con không có cột thời
 *  gian. `co_the_cap_nhat=false` ⇒ nút cập nhật khoá, `ly_do_khoa` là câu nói vì sao. */
export interface DanhMucDoiOut {
  so_buoc: number; co_the_cap_nhat: boolean; ly_do_khoa: string | null; buocs: DanhMucDoiBuoc[];
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
/** Tệp gắn vào CẢ lệnh. `nguoi_tai_ten` do máy chủ chốt từ tài khoản người tải. */
export interface LsxDinhKem {
  id: number;
  ten_tep: string;
  file_url: string;
  content_type: string | null;
  kich_thuoc: number;
  nguoi_tai_ten: string | null;
  tai_luc: string;
}

/** Tệp của MỘT lệnh nhìn từ Bàn tổ (chỉ đọc). Công việc bài ghép thì mỗi lệnh thành viên một nhóm. */
export interface SxTepLenhNhom {
  lsx_id: number;
  lsx_ma: string;
  lsx_ten: string | null;
  items: LsxDinhKem[];
}

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
  /** Dòng quyền THEO TỔ (`to_sx_<id>`, mg 0302): phòng ban mà dòng gắn vào + cấp trong cây khối
   *  sản xuất (gốc = 0, để thụt lề) + cờ KCS. Module tĩnh để trống. */
  department_id?: number | null;
  cap?: number;
  la_kcs?: boolean;
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
  /** Phòng có lương khoán theo sản lượng. */
  has_piece_work?: boolean;
  /** Đánh dấu khối SẢN XUẤT (spec §13.1). Effective tính theo cây ở FE (self hoặc tổ tiên tick). */
  la_san_xuat?: boolean;
  /** Đánh dấu khối KINH DOANH (mg 0181) — cùng luật kế thừa cây con. Nền cho danh sách
   *  "NV phụ trách" ở màn Khách hàng; chưa tick phòng nào thì backend lùi về quy tắc theo quyền. */
  la_kinh_doanh?: boolean;
  la_giao_hang?: boolean;
  /** Tổ IN (mg 0304) — thợ in ăn khoán: ngày CN / lễ đi làm không có công gốc, trả hết ở phần thêm. */
  la_to_in?: boolean;
  /** Khoán km giao hàng (mg 0231) — chỉ có nghĩa khi `la_giao_hang` bật. Đơn giá là số TÀI XẾ
   *  ĐƯỢC HƯỞNG, không phải cước cả xe. Hai ô % bắt buộc cộng đúng 100 (máy chủ chặn). */
  don_gia_km?: number;
  pct_tai_xe?: number;
  pct_phu_xe?: number;
  /** Đánh dấu tổ KCS đích danh (§3.1, §14) — KHÔNG kế thừa cây con. Gate phát hành bài ghép
   *  yêu cầu bước KCS cuối nằm ở một phòng có cờ này. */
  is_kcs?: boolean;
}

export interface DepartmentSalaryPolicy {
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
/** Một người trong nhóm dùng chung (khối Kinh doanh). */
export interface NhomDungChungThanhVien {
  user_id: number;
  ho_ten: string;
  username: string;
}

/** Nhóm DÙNG CHUNG dữ liệu — hai người cùng nhóm thì phạm vi "Của tôi" của họ ở bốn màn
 *  Tính giá · Báo giá · Đơn hàng · Khách hàng được hiểu là "của tôi + của người cùng nhóm". */
export interface NhomDungChung {
  id: number;
  ten: string;
  thanh_viens: NhomDungChungThanhVien[];
  created_at?: string | null;
}

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
  /** Dòng quyền theo tổ (mg 0302) — ba quyền chi tiết của Bàn tổ, đi cùng phạm vi của dòng. Ô KCS
   *  (`can_qc`) GỠ ở mg 0306. */
  can_run_order?: boolean;
  can_confirm_output?: boolean;
  can_warehouse?: boolean;
  /** cham_cong (mg 0194) — MỘT Ô = MỘT TAB. Xem `PermissionMatrix` để biết ô nào mở tab nào. */
  can_view_timesheet?: boolean;
  can_approve_late_early?: boolean;
  can_manage_locations?: boolean;
  can_manage_shifts?: boolean;
  can_manage_calendar?: boolean;
  /** luong (mg 0195) — tab Bảng lương tháng, tách khỏi cột Xem. */
  can_view_payroll_table?: boolean;
  can_manage_salary_profiles?: boolean;
  can_manage_piece_rates?: boolean;
  can_manage_leave_types?: boolean;
  /** giao_hang (mg 0199) — tab Lên kế hoạch + tab Nhân viên giao hàng. */
  can_plan?: boolean;
  can_view_drivers?: boolean;
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
  /** Phần điền vào dòng quyền theo tổ CỦA PHÒNG mà vai thuộc về (Tổ trưởng / Công nhân) — giao
   *  diện tự gắn vào `to_sx_<phòng đang mở>`. `null` = mẫu không đụng dòng tổ. */
  quyen_to_cua_vai?: Omit<PermissionRow, "module_key"> | null;
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
  /** Dòng quyền theo tổ (mg 0302) — ba quyền chi tiết của Bàn tổ, đi cùng phạm vi của dòng. Ô KCS
   *  (`can_qc`) GỠ ở mg 0306. */
  can_run_order?: boolean;
  can_confirm_output?: boolean;
  can_warehouse?: boolean;
  /** cham_cong (mg 0194) — MỘT Ô = MỘT TAB. Xem `PermissionMatrix` để biết ô nào mở tab nào. */
  can_view_timesheet?: boolean;
  can_approve_late_early?: boolean;
  can_manage_locations?: boolean;
  can_manage_shifts?: boolean;
  can_manage_calendar?: boolean;
  /** luong (mg 0195) — tab Bảng lương tháng, tách khỏi cột Xem. */
  can_view_payroll_table?: boolean;
  can_manage_salary_profiles?: boolean;
  can_manage_piece_rates?: boolean;
  can_manage_leave_types?: boolean;
  /** giao_hang (mg 0199) — tab Lên kế hoạch + tab Nhân viên giao hàng. */
  can_plan?: boolean;
  can_view_drivers?: boolean;
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
  markup_min_pct?: number | null;
  markup_max_pct?: number | null;
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

/** Một dòng KHÔNG ghi được. Còn một dòng lỗi thì CẢ FILE không ghi gì.
 *
 *  `dong` là số dòng THẬT trên sheet Excel (tính cả dòng tiêu đề) — người dùng đang nhìn file
 *  trong Excel, nói "dòng 7" thì họ bấm Ctrl+G tới đúng dòng 7. */
export interface NhapExcelLoi {
  dong: number;
  cot: string;
  ly_do: string;
}

/** Cảnh báo MỀM — VẪN ghi: trùng MST / tên / email (§34: không chặn), gỡ Sale phụ trách, đổi cùng
 *  lúc tên lẫn MST (nghi trỏ nhầm khách). */
export interface NhapExcelCanhBao {
  dong: number;
  ly_do: string;
}

/** Một ô sẽ đổi trên một khách ĐÃ CÓ (nhập lại file Xuất Excel, 17/09/2026). `cu`/`moi` đã là chữ
 *  người đọc (tên Sale, "Công ty", "5.000.000") — chuỗi rỗng là ô trống. */
export interface NhapExcelThayDoi {
  dong: number;
  ma: string;
  ten: string;
  cot: string;
  cu: string;
  moi: string;
}

/** Kết quả một lượt nhập Excel (#23; thay đường CSV cũ 11/09/2026).
 *
 *  `preview` và `commit` trả CÙNG hình dạng — khác đúng ở `da_ghi`. Xem trước chạy y hệt lượt ghi
 *  rồi rollback, nên con số ở đây là con số THẬT. Dòng có Mã KH là sửa (`cap_nhat`), không đổi gì
 *  thì không đụng tới (`khong_doi`). */
export interface NhapExcelOut {
  hop_le: boolean;
  tong_dong: number;
  tao_moi: number;
  cap_nhat: number;
  khong_doi: number;
  da_ghi: boolean;
  /** Có ô tài chính đã điền / đã sửa nhưng người nhập không có quyền ⇒ đã bỏ qua đúng mấy cột đó. */
  bo_qua_tai_chinh: boolean;
  loi: NhapExcelLoi[];
  canh_bao: NhapExcelCanhBao[];
  thay_doi: NhapExcelThayDoi[];
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
  markup_min_pct?: number | null;
  markup_max_pct?: number | null;
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
  /** Phí giao hàng của sản phẩm này — khoản MỘT LẦN cho cả sản lượng. CŨNG đã nằm trong
   *  `gia_von_tp` (một dòng của nhóm kết quả `giao_hang`), nên ĐỪNG cộng lại lần nữa. */
  phi_giao_hang?: number;
  /** Σ chi phí khác của sản phẩm này — cũng ĐÃ nằm trong `gia_von_tp`, đừng cộng lại. */
  chi_phi_khac?: number;
  /** Phân rã từng khoản lẻ: tên người dùng gõ + số tiền. */
  chi_phi_khac_dong?: { ten: string; thanh_tien: number }[];
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
  /** Σ SL CÁC SẢN PHẨM bên trong phiếu (BE tính lại) — không phải ô SL mặc định ở đầu phiếu.
   *  Đây là số mà `gia_von_don` đang chia, nên SL × giá vốn/đơn = tổng giá vốn. */
  so_luong: number;
  gia_von_don: number;
  tong_gia_von: number;
  ktv: string | null;
  so_thanh_phan: number;
  /** Tên các sản phẩm BÊN TRONG phiếu, đúng thứ tự khai. Cột "Sản phẩm" rơi về đây khi ô tên ở
   *  đầu phiếu bỏ trống (ô đó là chữ tự do, không ai bắt buộc gõ). */
  ten_thanh_phans: string[];
  ngay: string | null;
}
export interface PhieuTinhGiaListOut {
  items: PhieuTinhGiaListItem[];
  total: number;
}
/** Đếm cho thanh tab — độc lập trang/tìm kiếm hiện tại. */
export interface PhieuTinhGiaStatsOut {
  all: number;
  draft: number;
  calculated: number;
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
  /** Khuôn có sẵn hay làm mới — sale trả lời ở phiếu tính giá (chốt 04/09/2026). `null` = chưa
   *  chọn (phiếu cũ), engine giữ nguyên lời nhắc. Kế hoạch đọc lại để biết ý định của sale. */
  khuon_nguon: "co_san" | "lam_moi" | null;
  /** Ba ô riêng của bước khuôn ép kim (`tooling_type = "khuon_ep"`) — kích thước/số
   *  lượng khuôn, TÁCH BIỆT với `phi_khuon`: không tự tính ra tiền, chỉ bơm vào công thức của
   *  CHÍNH công đoạn đó. Đổi chủ từ bước khung lụa 06/09/2026 (khung lụa nay chỉ còn `phi_khuon`). */
  dai_khuon: number;
  rong_khuon: number;
  so_khuon: number;
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
  /** ĐVT của CẢ NHÓM gộp khi in cho khách (chọn từ danh mục Đơn vị & quy đổi, lưu TÊN).
   *  null = dòng gộp lấy ĐVT của dòng đầu nhóm như trước. */
  dvt_nhom: string | null;
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
  phi_giao_hang: number; // ⑤ phí giao hàng — khoản MỘT LẦN, ĐÃ nằm trong `gia_von_tp`
  gia_von_tp: number;
  thanh_phams: ThanhPhamOut[];
  vat_tus: VatTuLineOut[];
  /** ⑥ Chi phí khác — các khoản lẻ tự khai (làm kẽm ngoài, phí thiết kế…). Mỗi dòng MỘT LẦN cho
   *  cả sản lượng, ĐÃ nằm trong `gia_von_tp`. */
  chi_phi_khacs: ChiPhiKhacOut[];
}

/** 1 dòng chi phí khác — cặp (tên tự gõ, số tiền). Không trỏ danh mục, không công thức. */
export interface ChiPhiKhacOut {
  id: number;
  thanh_phan_id: number;
  thu_tu: number;
  ten: string;
  so_tien: number;
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
  /** CHỈ có ở bản RÚT GỌN (vai thiếu `tinh_gia_thanh:view_cost`): tên + tổng tiền từng rổ, không
   *  kèm dòng nào. Vai đủ quyền đọc ba rổ từ `result.groups` nên BE không trả field này. */
  nhom_tong?: { ten: string; tong: number }[];
  ktv: string | null;
  ghi_chu: string | null;
  thanh_phans: ThanhPhanOut[];
  created_at: string | null;
  updated_at: string | null;
  /** Danh mục (công đoạn · giấy · máy · vật tư · bù hao) mà phiếu đang dùng đã lệch SAU lần tính
   *  gần nhất. null = phiếu còn khớp danh mục. Chỉ để NHẮC — số trong phiếu vẫn là ảnh chụp cũ
   *  cho tới khi người lập bấm "Tính giá". Ba rổ tách riêng: `ten` đổi cấu hình · `ngung` bị
   *  ngừng dùng (không chọn lại được) · `xoa` đã xoá hẳn khỏi danh mục (phải thay bước). */
  danh_muc_doi: { luc: string; ten: string[]; ngung?: string[]; xoa?: string[] } | null;
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
  khuon_nguon?: "co_san" | "lam_moi" | null;
  dai_khuon?: number;
  rong_khuon?: number;
  so_khuon?: number;
}
/** Input 1 thành phần — mọi field optional + list gia công. */
export interface ThanhPhanIn {
  loai_thanh_phan?: string;
  ten?: string;
  dai_thanh_pham?: number;
  rong_thanh_pham?: number;
  nhom_bao_gia?: string | null;
  dvt_nhom?: string | null; // ĐVT của cả nhóm gộp (null = lấy ĐVT dòng đầu nhóm)
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
  /** ⑤ Phí giao hàng: TỔNG tiền chở cho toàn bộ sản lượng của sản phẩm này — khoản MỘT LẦN,
   *  cộng thẳng vào giá vốn (⇒ chịu markup ở Báo giá). 0 = không thu. */
  phi_giao_hang?: number;
  thanh_phams?: ThanhPhamIn[];
  vat_tus?: VatTuLineIn[];
  /** ⑥ Chi phí khác: khoản lẻ MỘT LẦN (làm kẽm ngoài, phí thiết kế…) — cộng thẳng vào giá vốn
   *  như `phi_giao_hang`. Dòng 0đ vẫn lưu (để gõ tiếp) nhưng server không đẻ dòng tiền. */
  chi_phi_khacs?: ChiPhiKhacIn[];
}
/** Input 1 dòng chi phí khác — tên gõ tay + số tiền, cả hai optional. */
export interface ChiPhiKhacIn {
  ten?: string;
  so_tien?: number;
}
/** 1 dòng gợi ý Sản phẩm tái bản — nhẹ, chỉ đủ hiển thị danh sách chọn. */
export interface SanPhamTaiBanGoiY {
  id: number;
  ten: string;
  updated_at: string;
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
  /** Ảnh minh họa in ở cột "Hình ảnh minh họa" của bản gửi khách. Thuộc CẢ CỤM cùng tên: mọi
   *  dòng trong cụm mang cùng URL, đặt/xóa ở dòng nào cũng ghi cho cả cụm. null = chưa có ảnh. */
  anh_minh_hoa: string | null;
  quantity: number;
  /** ĐVT THẬT của phần này ("cái" cho tấm bìa) — thứ mọi màn không gộp hiển thị. */
  unit: string;
  /** ĐVT của CỤM khi bản in gộp ruột + bìa thành 1 dòng ("cuốn"). null = không gộp / cụm chưa
   *  chọn đơn vị riêng ⇒ dòng gộp lấy ĐVT của dòng đầu cụm như cũ. */
  dvt_nhom: string | null;
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

/** Kết quả đặt ảnh minh họa: URL vừa gắn + các dòng đã nhận nó (cả cụm cùng tên). */
export interface QuoteItemImage {
  anh_minh_hoa: string;
  item_ids: number[];
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
  /** ĐC giao + người nhận: Sale chọn tay ở báo giá (dropdown danh bạ/điểm giao của khách); đơn
   *  hàng KẾ THỪA nguyên các giá trị này khi chốt đơn, không sửa lại được. */
  delivery_address: string | null;
  contact_name_snapshot: string | null;
  contact_phone_snapshot: string | null;
  contact_title_snapshot: string | null;
  contact_email_snapshot: string | null;
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
  // BG-2 — báo giá đặc thù (GĐ duyệt trước khi gửi khách). `markup_pct` = lợi nhuận / GIÁ VỐN —
  // ĐÚNG con số ô "Markup %" trong bảng dòng, không phải biên trên giá bán.
  exception_required: boolean;
  exception_status: "none" | "pending" | "approved" | "rejected" | "stale";
  exception_cleared: boolean;
  exceptions: { key: string; label: string }[];
  exception_note: string | null;
  markup_pct: number | null;
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
  /** ĐC giao + người nhận — chọn từ danh bạ/điểm giao của khách. BE overwrite trực tiếp (không giữ
   *  field cũ khi bỏ trống) → luôn echo giá trị hiện có ở mọi lần gọi update. */
  delivery_address?: string | null;
  contact_name_snapshot?: string | null;
  contact_phone_snapshot?: string | null;
  contact_title_snapshot?: string | null;
  contact_email_snapshot?: string | null;
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

/** `probation_ended` = đã qua Ngày hết thử việc, CHỜ HCNS bấm "Chuyển chính thức" (máy tự đặt).
 *  Vẫn ăn lương thử việc cho tới lúc bấm — chỉ trạng thái đổi, tiền không đổi. */
export type EmployeeStatus =
  | "probation" | "probation_ended" | "active" | "on_leave" | "suspended" | "resigned";

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

export interface EmployeeRow {
  id: number;
  code: string;
  full_name: string;
  department_id: number | null;
  department_name: string | null;
  position: string | null;
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
  resign_date: string | null;
  resign_reason: string | null;
  note: string | null;
  /** Thâm niên đã có TRƯỚC khi vào làm (tháng) — cộng với thời gian từ `hire_date` mới ra
   *  thâm niên tổng. Bỏ vế này là tính hụt với người chuyển từ nơi khác sang. */
  prior_seniority_months?: number;
  /** Trưởng bộ phận. CHỈ `/api/employees/me` điền (màn HCNS để null — tránh N+1). */
  department_head_name?: string | null;
  /** Ca NỀN đang hiệu lực HÔM NAY (mốc tương lai chưa tính) — chỉ `GET /api/employees/{id}` điền. */
  current_shift_id?: number | null;
  current_shift_name?: string | null;
}

export interface EmployeeKpis {
  total: number;
  active: number;
  probation: number;
  /** Đã hết thử việc, chờ HCNS xác nhận chính thức. */
  probation_ended: number;
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
  /** MỨC ĐÓNG BHXH khai riêng của NGƯỜI NÀY (16/09/2026) — BHXH 8% + BHYT 1,5% + BHTN 1%
   *  tính trên số này; đoàn phí công đoàn vẫn theo mức nền. Bắt buộc ở cả hai form nhập. */
  insurance_base?: number;
  /** "Lương trả 1 lần" (đợt 1) — mức điền sẵn khi lập phiếu thanh toán lương đợt 1. */
  luong_dot_1?: number;
  allowance?: number;
  /** Hai ô ĐÃ NGƯNG (ca 03/08/2026 · thâm niên 07/09/2026) — nhận cho tương thích, engine không trả. */
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
  new_position?: string | null;
  resign_reason?: string | null;
}

export interface EmployeeListParams {
  q?: string;
  department_id?: number | null;
  status?: string | null;
  has_account?: boolean | null;
  /** Thử việc hết trong 30 ngày tới — lọc ở MÁY CHỦ, đếm trùng với KPI `probation_ending_soon`. */
  ending_soon?: boolean;
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
  /** Nghỉ giữa ca "HH:MM" (07/09/2026) — null cả hai = ca không khai nghỉ. Khung tính công =
   *  (ra − vào) − nghỉ; ca 7:30–16:30 nghỉ 11:30–12:30 ⇒ mẫu số 480' (nửa buổi = 0,5 công). */
  break_start_time: string | null;
  break_end_time: string | null;
  /** Phụ cấp cơm khai theo ca (đ) — Lương cộng trọn mức cho mỗi ngày làm ca đạt ngưỡng công. */
  meal_allowance: number;
  /** Phụ cấp ca khai theo ca (đ), áp ca ngày/đêm — cùng luật ngày làm ca đạt ngưỡng (tiền cục
   *  theo ca: ca đêm 77k/đêm, ca tới sáng 125k… khai ở đây). */
  shift_allowance: number;
  is_active: boolean;
  /**
   * Ca CHẠY DƯỚI XƯỞNG: Xếp lịch lấy đúng các ca này làm giờ làm của xưởng — khung giờ được phép
   * đặt việc VÀ mẫu số tính % tải máy. Ca văn phòng (Hành chính 08:00–17:00) tắt cờ: vẫn chấm công
   * bình thường, chỉ thôi tính vào lịch xưởng.
   */
  ca_san_xuat: boolean;
  note: string | null;
}

export interface WorkShiftsList {
  items: WorkShift[];
  /** Giờ công chuẩn / ngày (Cấu hình lương) — mọi ca phải làm đúng số này khi `ca_khop_gio_chuan`. */
  gio_cong_chuan?: number | null;
  ca_khop_gio_chuan?: boolean;
}

export interface WorkShiftInput {
  name: string;
  start_time: string;
  end_time: string;
  is_overnight?: boolean;
  night_multiplier?: number;
  grace_minutes?: number;
  /** Nghỉ giữa ca — cả hai hoặc không cái nào (null = bỏ nghỉ). */
  break_start_time?: string | null;
  break_end_time?: string | null;
  meal_allowance?: number;
  shift_allowance?: number;
  note?: string | null;
  is_active?: boolean;
  /** Ca chạy dưới xưởng SX — nuôi khung giờ Xếp lịch + mẫu số % tải máy. Bỏ trống = bật. */
  ca_san_xuat?: boolean;
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
  /** Có phiếu TC đã duyệt (ngày đã qua) mà KHÔNG có cặp bấm tăng ca ⇒ chốt là 0 phút TC (07/09/2026). */
  ot_thieu_cap?: boolean;
  night: boolean;
  leave: string | null;  // tên loại nghỉ (nếu ngày nghỉ đã duyệt) HOẶC tên ngày lễ
  leave_paid: boolean;   // nghỉ có lương (P) hay không (KL)
  holiday?: boolean;     // ngày nghỉ lễ hưởng lương (cộng 1 công tự động)
  /** LOẠI NGÀY khi CÓ ĐI LÀM — ba cờ `holiday`/`restday`/`plain` loại trừ nhau (thứ tự
   *  `plain > holiday > restday`, khớp nhánh tính tiền bên Lương). Ô lịch cần chúng để nói
   *  "→ tính N công"; không có cờ thì ngày Chủ nhật đi làm hiện y hệt ngày thường. */
  restday?: boolean;     // ngày NGHỈ TUẦN (CN) có đi làm → tiền ×`he_so_ngay.nghi_tuan`
  // Lễ rơi ĐÚNG ngày nghỉ tuần có đi làm → ×`he_so_ngay.le_nghi_tuan` (cả `holiday` lẫn `restday`
  // cùng bật, vì tiền cộng cả hai chế độ).
  le_nghi_tuan?: boolean;
  plain?: boolean;       // ngày `off1x` có đi làm → 1× phẳng, KHÔNG hệ số
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
  /** Công ĐẶC BIỆT trong tháng — nguồn của cột "Công đặc biệt". `holiday_cong`/`restday_cong`
   *  là TẬP CON của `total_cong`; riêng `plain_cong` đã bị trừ ra (Lương trả riêng, 1× phẳng). */
  holiday_cong?: number;
  restday_cong?: number;
  plain_cong?: number;
  total_hours: number;
  total_cong: number | null;
}

/** Hệ số công theo LOẠI NGÀY, đọc từ Cấu hình lương — để màn hình khỏi viết cứng số.
 *  ⚠️ Lễ và Chủ nhật CỐ Ý khác nhau: lễ = 1 (tiền lễ Đ112) + hệ số làm lễ ⇒ mặc định 4×;
 *  Chủ nhật = đúng hệ số nghỉ tuần ⇒ mặc định 2×. Đừng "dọn" cho giống nhau. */
export interface HeSoNgay {
  /** Ngày lễ đi làm — TỔNG (khách chốt 15/09/2026: 300%, không còn 1 + 3 = 4×). */
  le: number;
  nghi_tuan: number;
  /** Lễ rơi ĐÚNG ngày nghỉ tuần: cộng cả hai chế độ (200% + 300% = 500%). */
  le_nghi_tuan: number;
  off1x: number;
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
  /** Chỉ có sau PUT đổi cờ có-lương khi còn đơn đã duyệt ở kỳ chưa chốt công (C16, 08/09/2026). */
  canh_bao?: string | null;
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
  /** Yêu cầu hủy MỚI NHẤT của phiếu (23/09/2026) — `trang_thai === "cho"` ⇒ "Đang xin hủy". */
  yeu_cau_huy?: YeuCauHuy | null;
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
/** Số dư TRẦN GIỜ LÀM THÊM THÁNG (Điều 107 BLLĐ) — nuôi dải bộ đếm trên modal tạo/sửa phiếu.
 *
 *  `ap_tran = false` ⇒ công ty chưa bật trần ⇒ FE **ẩn cả khối**, đừng bày ô vô nghĩa.
 *  Đếm theo PHIẾU (chờ duyệt + đã duyệt), KHÔNG phải giờ đã bấm máy — phiếu chờ duyệt
 *  vẫn GIỮ CHỖ. Mọi số là PHÚT; UI quy ra giờ ("40h" / "8h30").
 *  KHÔNG có trần theo NĂM — chủ đã bỏ (17/08/2026). */
export interface TranThangOut {
  ap_tran: boolean;
  tran_phut: number;
  da_dung_phut: number;
  /** null khi `ap_tran = false` (không có trần thì không có "còn lại"). */
  con_lai_phut: number | null;
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
/** Thợ trong tầm của người duyệt tăng ca — nuôi dropdown "Tạo hộ thợ" (E8, 08/09/2026). */
export interface OvertimeRoster {
  employees: { id: number; code: string | null; full_name: string; department: string | null }[];
}

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
  /** Yêu cầu hủy MỚI NHẤT của đơn (23/09/2026) — `trang_thai === "cho"` ⇒ "Đang xin hủy". */
  yeu_cau_huy?: YeuCauHuy | null;
}

/** Yêu cầu HỦY đơn nghỉ / phiếu tăng ca ĐÃ DUYỆT (chủ chốt 23/09/2026): người lao động chỉ XIN,
 *  ai có quyền duyệt thì quyết. Đơn gốc vẫn hiệu lực tới khi được đồng ý. */
export interface YeuCauHuy {
  id: number;
  loai: "nghi_phep" | "tang_ca";
  request_id: number;
  ly_do: string;
  trang_thai: "cho" | "dong_y" | "giu_nguyen" | "rut_lai";
  /** Người duyệt / HCNS hủy thẳng, không qua bước xin. */
  truc_tiep: boolean;
  /** Đơn nghỉ đang dở: hủy từ ngày này, giữ các ngày trước (`YYYY-MM-DD`). */
  huy_tu_ngay: string | null;
  /** `end_date` gốc của đơn nghỉ trước khi được rút ngắn. */
  den_ngay_cu: string | null;
  ly_do_quyet: string | null;
  created_at: string | null;
  decided_at: string | null;
  decided_by_name: string | null;
}
export interface XinHuyChoDuyet<T> {
  yeu_cau: YeuCauHuy;
  don: T;
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
  pending?: number;   // phần đang chờ duyệt nằm trong `used` (C5b, 08/09/2026)
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

export interface LeaveCalendarDay {
  status: string; leave_type_name: string; is_paid: boolean;
  /** Đơn đã duyệt đang có yêu cầu hủy chờ quyết — vẫn là ngày nghỉ, chỉ gắn dấu (23/09/2026). */
  dang_xin_huy?: boolean;
}
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
  /** Ca phải khớp giờ công chuẩn: khai ca (giờ ra − giờ vào − nghỉ giữa ca) ≠ số trên thì không cho lưu. */
  ca_khop_gio_chuan?: boolean;
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
  /** TRẦN GIỜ LÀM THÊM THÁNG (Đ107) — số PHÚT tối đa MỘT người trong MỘT tháng, `0` = TẮT trần.
   *  Backend CHẶN CỨNG khi vượt: không có đường vượt, không quyền đặc biệt. Ô nhập trên UI theo
   *  GIỜ (40h = 2400) — nhớ ×60 lúc lưu, ÷60 lúc đọc. KHÔNG có trần theo NĂM. */
  ot_max_minutes_per_month: number;
  /** Độ dài tối đa của MỘT phiếu tăng ca, tính bằng PHÚT (Đ107.1, mặc định 720 = 12h). */
  ot_max_minutes_per_day: number;
}
export interface EmployeeSalary {
  id: number;
  employee_id: number;
  effective_from: string;
  effective_to?: string | null;
  is_current?: boolean;
  base_amount: number | null;
  /** Mức HỢP ĐỒNG riêng của NV — mức nền = vị trí + trách nhiệm. */
  luong_vi_tri: number;
  luong_trach_nhiem: number;
  /** Lương trả 1 lần (đợt 1) — số điền sẵn khi tạo phiếu "thanh toán lương đợt 1". */
  luong_dot_1?: number;
  /** Mức đóng BH khai riêng (dormant — engine bám luong_vi_tri). */
  insurance_base: number | null;
  /** Phụ cấp KHAI TAY — số cố định, engine cộng phẳng, KHÔNG tự tính gì. */
  allowance: number; // phụ cấp KHÁC (gộp)
  /** Hai ô ĐÃ NGƯNG (ca 03/08/2026 · thâm niên 07/09/2026): giữ số cũ để tra, engine không trả. */
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
  base_amount?: number | null;
  /** Gõ riêng 2 ô mức hợp đồng của chính NV — mức nền = vị trí + trách nhiệm. */
  luong_vi_tri?: number;
  luong_trach_nhiem?: number;
  /** MỨC ĐÓNG BHXH khai riêng của NGƯỜI NÀY (16/09/2026) — BHXH 8% + BHYT 1,5% + BHTN 1%
   *  tính trên số này; đoàn phí công đoàn vẫn theo mức nền. Bắt buộc ở cả hai form nhập. */
  insurance_base?: number;
  /** Lương trả 1 lần (đợt 1) — mức trả trong 1 lần, dùng để điền sẵn phiếu đợt 1. */
  luong_dot_1?: number;
  /** Phụ cấp KHÁC khai tay của riêng NV — gõ một lần, tháng nào cũng cộng đúng số này. */
  allowance?: number; // phụ cấp KHÁC (gộp)
  /** Hai ô ĐÃ NGƯNG (ca 03/08/2026 · thâm niên 07/09/2026) — FE chỉ chép lại số cũ, engine không trả. */
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
  /** Hai ô đã ngưng (ca · thâm niên) — số hồ sơ, không ra tiền. */
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
  /** Tháng SỚM NHẤT còn lập phiếu được (`YYYY-MM`) = liền sau kỳ lương đã chốt/đã chi muộn nhất.
   *  NV không có quyền đọc `/periods` nên server trả kèm ở đây. FE đặt làm `min` của ô chọn kỳ
   *  ⇒ **kỳ đã chốt không chọn được nữa**. `null` (server cũ) ⇒ lùi về mốc 12 tháng mặc định. */
  ky_min_chon_duoc?: string | null;
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
  /** Công ngày LỄ + NGHỈ TUẦN có đi làm (⊂ `actual_cong`) — gốc của hệ số Đ98.1.b/c. */
  special_cong?: number;
  /** TRONG ĐÓ của `ot_pay`: tiền ngày `off1x` (trả 1× phẳng). Đừng cộng lại vào tổng. */
  off1x_pay?: number;
  /** CHẾ ĐỘ KHOÁN (14/09/2026, chụp lúc Tính lại): tổ bật Lương khoán / sản lượng hoặc tổ Giao hàng
   *  ⇒ KHÔNG có tiền tăng ca (làm thêm giờ đã trả qua tiền khoán); vẫn có cơm tăng ca + phần thêm làm
   *  nguyên ngày CN/lễ. Màn hình dùng để nói vì sao có giờ tăng ca mà tiền tăng ca = 0. */
  che_do_khoan?: boolean;
  /** Người này thuộc tổ bật cờ **Bộ phận Giao hàng** (chụp lúc Tính lại). Từ 16/09/2026 tổ Giao hàng
   *  ăn luật RIÊNG trong chế độ khoán: CÓ tiền giờ tăng ca, và tiền đó nằm trong vế thời gian đem so
   *  với khoán km (PRD bù lỗ §00.10) — nên màn hình phải tách được họ khỏi thợ khoán sản lượng. */
  la_giao_hang?: boolean;
  /** LƯƠNG BÙ LỖ (tổ khoán sản xuất, 14/09/2026, chụp lúc Tính lại): số bù lỗ theo công đã đem so
   *  với tiền khoán — lương sản lượng = MAX(khoán, bù lỗ). `null` = dòng không thuộc luật này.
   *  Khi có số, `luong_cong` là PHẦN BÙ THÊM cho đủ bù lỗ (0 nếu khoán cao hơn) — đừng in nó là
   *  "lương theo công". */
  bu_lo_theo_cong?: number | null;
  /** true = khoán thấp hơn bù lỗ theo công, tháng này đang trả bù lỗ. */
  lay_bu_lo?: boolean;
  /** Công ngày lễ nghỉ hưởng lương của người ăn khoán / tài xế — trả RIÊNG, ngoài khoán, CÓ trong
   *  `gross` (15/09/2026). 0 với người công nhật: lễ của họ nằm sẵn trong `luong_cong`. */
  luong_ngay_le?: number;
  /** Số công ngày lễ nghỉ hưởng lương của kỳ — để phiếu / bảng lương ghi "N ngày" cạnh tiền lễ. */
  le_nghi_cong?: number;
  /** Phụ cấp đi theo công (15/09/2026): số tháng đã khai (ô Phụ cấp khác + khoản hồ sơ) và số công
   *  hưởng — `allowance` = phu_cap_thang ÷ công chuẩn × cong_phu_cap. null = kỳ cũ (cộng phẳng). */
  phu_cap_thang?: number | null;
  cong_phu_cap?: number | null;
  /** Công thiếu nhưng có đơn nghỉ theo giờ đã duyệt (được miễn phạt, giữ chuyên cần). */
  excused_cong?: number;
  chuyen_can: number;
  /** TỔNG phụ cấp tháng — ĐÃ GỒM 3 dòng dưới. Render 3 dòng thì ĐỪNG cộng thêm số này.
   *  Phụ cấp CA (`ca_pay`/`night_pay`) là khoản RIÊNG, KHÔNG nằm trong `allowance`. */
  allowance: number;
  /** NGƯNG 07/09/2026 — kỳ mới luôn 0; chỉ kỳ cũ còn số (phiếu in dòng "(đã ngưng)"). */
  phu_cap_tham_nien?: number;
  /** Có công mà mức lương = 0 — chưa khai ở Lương nhân viên (router điền; chốt kỳ bị chặn). */
  chua_khai_luong?: boolean;
  /** Chưa khai ô "Mức đóng BHXH" ở mốc lương hiện hành (16/09/2026) — đang tạm đóng theo mức nền. */
  chua_khai_muc_bh?: boolean;
  /** Phần còn lại = allowance − thâm niên (backend tính). */
  phu_cap_khac?: number;
  khoan: number;
  /** Khoán km giao hàng (mg 0231) — CỘNG THÊM vào gross, không phải "trong đó" của khoản nào.
   *  Là CỘT chứ không phải khoản danh mục: tiền engine tự tính đứng cùng nhà với `khoan`. */
  khoan_km?: number;
  /** Hoa hồng KD — cột riêng (07/09/2026), máy tự tính theo hoá đơn, cộng thẳng vào gross, chịu thuế. */
  hoa_hong?: number;
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
  /** Nợ tạm ứng dồn kỳ (07/09/2026): kỳ trước mang sang / kỳ này chưa trừ hết chuyển kỳ sau. */
  no_ung_ky_truoc?: number;
  no_ung_chuyen_ky_sau?: number;
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

/** CHỈ TIÊU NGÀY của tổ lương khoán / sản lượng (16/09/2026): tiền sản lượng MỘT thợ phải làm ra
 *  trong MỘT công. Mỗi dòng là một mốc "áp dụng từ ngày". CHƯA nối vào tính lương. */
export interface ChiTieuNgay {
  id: number;
  department_id: number;
  /** `YYYY-MM-DD` */
  ap_dung_tu: string;
  /** đ/công */
  so_tien: number;
  ghi_chu: string | null;
  updated_at: string | null;
}
export interface ChiTieuNgayList {
  department_id: number;
  /** Mốc đang hiệu lực HÔM NAY; null = chưa khai, hoặc mọi mốc đều áp dụng từ ngày tương lai. */
  hien_hanh: ChiTieuNgay | null;
  /** Mới nhất đứng đầu. */
  items: ChiTieuNgay[];
}
export interface ChiTieuNgayInput {
  ap_dung_tu: string;
  so_tien: number;
  ghi_chu?: string | null;
}

/** Tổ trưởng ăn gì trên sản lượng tổ (19/09/2026): không áp dụng · ăn thưởng · ăn chia. */
export type ToTruongCheDo = "khong" | "thuong" | "chia";
/** Một MỐC chế độ tổ trưởng của tổ khoán — CHƯA nối vào tính lương. */
export interface ToTruongMoc {
  id: number;
  department_id: number;
  /** `YYYY-MM-DD` */
  ap_dung_tu: string;
  che_do: ToTruongCheDo;
  /** % trên sản lượng tổ (5 = 5%); `khong` là 0. */
  ty_le: number;
  ghi_chu: string | null;
  updated_at: string | null;
}
export interface ToTruongList {
  department_id: number;
  /** Mốc đang hiệu lực HÔM NAY; null = chưa khai, hoặc mọi mốc đều áp dụng từ ngày tương lai. */
  hien_hanh: ToTruongMoc | null;
  /** Mới nhất đứng đầu. */
  items: ToTruongMoc[];
}
export interface ToTruongInput {
  ap_dung_tu: string;
  che_do: ToTruongCheDo;
  ty_le: number;
  ghi_chu?: string | null;
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
  sort_order?: number;
  note?: string | null;
}
/** Sửa TỪNG PHẦN — field nào bỏ qua thì backend giữ nguyên. */
export interface PayrollComponentPatch {
  name?: string;
  kind?: ComponentKind;
  is_taxable?: boolean;
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
 *  Lương → Lương nhân viên) · `line` = thêm tay, CHỈ có ở kỳ này, không lặp sang tháng sau ·
 *  `auto` = HỆ TỰ TÍNH (hoa hồng KD, theo hoá đơn bán trong kỳ) — backend CHẶN sửa/gỡ, giao diện
 *  phải để ở dạng chỉ đọc, và số bị ghi lại mỗi lần "Tính lại". */
export interface LineComponent {
  id: number;
  component_id: number;
  code: string;
  name: string;
  kind: ComponentKind;
  is_taxable: boolean;
  amount: number;
  note: string | null;
  /** `auto` chỉ còn ở dữ liệu trước 07/09/2026 (hoa hồng nay là cột `hoa_hong`). */
  source: "employee" | "line" | "auto";
  /** HCNS đã sửa tay số tiền CHO RIÊNG KỲ NÀY. Hồ sơ nhân viên KHÔNG đổi — tháng sau tự về mức
   *  cũ. Dòng đã đè được miễn khỏi lượt ghi đè của "Tính lại". */
  da_de_tay?: boolean;
}
export interface KhoanKmChuyen {
  trip_id: number;
  ngay: string | null;
  km: number;
  don_gia_km: number;
  /** Vai trò trong CHUYẾN ĐÓ, không phải chức danh của người. */
  vai_tro: "tai_xe" | "phu_xe";
  /** % được hưởng của chuyến. Đi một mình = 100, không phải `pct_tai_xe`. */
  pct: number;
  thanh_tien: number;
}

export interface KhoanKmChiTiet {
  items: KhoanKmChuyen[];
  tong: number;
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
  /** Cảnh báo (không chặn) trước khi chốt — người thực lĩnh 0 vì trừ nợ, người còn nợ chuyển kỳ. */
  canh_bao_chot?: string | null;
}
/** Một kỳ NLĐ tra lại được. CHỈ nhãn tháng — không kèm tiền. */
export interface KyXemDuoc {
  year: number;
  month: number;
  /** null = mở không thời hạn. */
  dong_phieu_luc: string | null;
}

/** Kỳ mới nhất NLĐ CHƯA xem được, kèm lý do — để màn thôi nói "chưa có kỳ lương nào". */
export interface ChoPhat {
  year: number;
  month: number;
  tinh_trang: "chua_phat" | "hen_gio" | "da_dong";
  /** Chỉ có nghĩa khi `tinh_trang = "hen_gio"`. */
  mo_luc: string | null;
}

export interface MyPayslip {
  has_employee: boolean;
  employee_name: string | null;
  period: PayrollPeriod | null;
  line: PayrollLine | null;
  /** Các kỳ tra lại được, mới → cũ. Rỗng = không có phiếu nào đang mở. */
  ky_xem_duoc: KyXemDuoc[];
  cho_phat: ChoPhat | null;
}

/** Một HẠNG MỤC KIỂM của MỘT công đoạn (danh mục Tiêu chí KCS sau mg `0285`). */
export interface KcsHangMuc {
  id: number;
  ma: string;
  cong_doan_id: number;
  ten: string;
  huong_dan: string | null;
  bat_buoc: boolean;
  thu_tu: number;
  active: boolean;
}
/** Thân ghi — KHÔNG có `ma` (server cấp `KM####`). */
export interface KcsHangMucBody {
  cong_doan_id: number;
  ten: string;
  huong_dan?: string | null;
  bat_buoc: boolean;
  thu_tu: number;
  active: boolean;
}
export interface KcsKhaiBaoCongDoan {
  cong_doan_id: number;
  ma: string;
  ten: string;
  hang_muc: KcsHangMuc[];
}
export interface KcsKhaiBaoGiaiDoan {
  /** Mã giai đoạn = `cong_doan.nhom`; "" = công đoạn chưa khai giai đoạn. */
  nhom: string;
  cong_doan: KcsKhaiBaoCongDoan[];
}
/** Công đoạn ĐANG DÙNG chưa khai hạng mục — ô chọn "Khai báo công đoạn kiểm tra mới".
 *  Server đã lọc + xếp theo mã, trả chung trong `khaiBao` để màn khỏi kéo cả `/api/cong-doan`. */
export interface KcsCongDoanChon {
  id: number;
  ma: string;
  ten: string;
  /** Mã giai đoạn = `cong_doan.nhom`; "" = chưa khai giai đoạn. */
  nhom: string;
}
export interface KcsKhaiBao {
  giai_doan: KcsKhaiBaoGiaiDoan[];
  cong_doan_chon: KcsCongDoanChon[];
}

export interface CongDoanLite {
  id: number;
  ma: string;
  ten: string;
  /** GIAI ĐOẠN (`cong_doan.nhom`): prepress · print · finishing · other. Màn khai báo hạng mục
   *  kiểm KCS lọc ô chọn công đoạn theo giai đoạn người dùng vừa chọn — nhãn ở `NHOM_CONG_DOAN`
   *  (`pages/keHoachSxShared.tsx`). Rỗng = công đoạn chưa khai giai đoạn. */
  nhom?: string | null;
  khoan_ghi_theo: string;
  /** Nhóm máy (loai_may) làm được công đoạn — checkbox "Máy làm được công đoạn này" ở danh mục.
   *  Drawer routing lệnh SX lọc dropdown MÁY theo đây; null/rỗng = không giới hạn (hiện tất cả).
   *  `/api/cong-doan` (CongDoanRow) đã trả sẵn, không cần đổi backend. */
  nhom_may_cho_phep?: string[] | null;
  /** MÁY cụ thể chạy được công đoạn + công thức giờ/giá của riêng từng cặp (06/09/2026).
   *  Hàng tick `nhom_may_cho_phep` ở trên nay chỉ là BỘ LỌC cho bảng này.
   *  Hình dạng viết thẳng ở đây, không import: file này cố ý không phụ thuộc module nào —
   *  bản đặt tên là `MayCongDoanRow` trong `pages/danh-muc/types.ts`. */
  may_lam_duoc?: { may_id: number; cong_thuc_gio?: string | null;
                   cong_thuc_gia?: string | null }[] | null;
  /** Các TỔ phụ trách công đoạn (nhiều tổ, 18/09/2026, mg `0312`) — tổ đầu là tổ mặc định. Ô tổ
   *  của bước lệnh chỉ mời các tổ này. Rỗng = công đoạn chưa khai tổ, không giới hạn. */
  department_ids?: number[] | null;
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
  he_so_ngay?: HeSoNgay;           // hệ số công theo loại ngày (từ Cấu hình lương)
  rows: TimesheetRow[];
}

/** Một phiếu TC đã duyệt (ngày đã qua) mà không có cặp bấm tăng ca — cảnh báo trước khi chốt. */
export interface OtThieuCap {
  employee_id: number;
  employee_name: string;
  date: string;              // "YYYY-MM-DD"
  from_time: string;
  to_time: string;
  /** MÃ tình trạng — băng cảnh báo tách "bù được 1 chạm" với "phải chấm bù ca chính trước"
   *  (10/09/2026). `thieu_cap` = nút Xác nhận TC làm được; `khong_cham` = ngày trắng lượt bấm,
   *  bù được nhưng phải xác nhận riêng; `treo` = thiếu RA ca chính, phải chấm bù trước. */
  ma?: "thieu_cap" | "khong_cham" | "treo";
  ly_do: string;
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
  /** Đổi ca nền / ô lưới có hiệu lực trong tháng, ghi SAU khi kỳ đã chốt (B8, 08/09/2026): ảnh chụp
   *  tính theo ca cũ ⇒ phải mở lại kỳ, chốt lại, Tính lại. */
  doi_ca_nen_sau_chot?: number;
  pending_leaves: number;    // đơn nghỉ phép chưa duyệt của tháng
  /** Phiếu đi muộn/về sớm chưa duyệt — CHẶN chốt công y như đơn nghỉ: snapshot đóng băng lúc
   *  chốt, phiếu duyệt sau đó không vào được nữa ⇒ NLĐ vẫn ăn phạt dù đã xin phép đúng luật. */
  pending_late_early: number;
  /** Phiếu TĂNG CA chưa duyệt — chặn từ 15/08/2026. Sót nó là ngõ cụt: chốt xong thì duyệt cũng
   *  bị chặn, mà không duyệt thì không có tiền tăng ca; gỡ ra phải mở lại cả kỳ công. */
  pending_overtime?: number;
  /** Phiếu TC đã duyệt (ngày đã qua) mà KHÔNG có cặp bấm — CẢNH BÁO, không chặn chốt (07/09/2026). */
  ot_thieu_cap?: number;
  ot_thieu_cap_list?: OtThieuCap[];
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
  /** Công chuẩn LƯƠNG = working_days + lễ hưởng lương (B1 08/09/2026) — số Bảng lương đang chia. */
  cong_chuan_luong?: number;
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
  /** Có khi NV có phiếu TC đã duyệt (trong ngày) nhưng chưa có cặp chấm tăng ca → FE nhắc + nút 1 chạm.
   *  `kieu`: `bu_cap` (đã ra ca chính trước giờ phiếu ⇒ thêm cặp VÀO/RA TC) hay `tach_phien` (thợ chỉ
   *  bấm 2 lượt ⇒ thêm RA ca chính + VÀO TC, lượt RA thật thành RA TC). `*_next_day` = mốc sang hôm sau. */
  ot_suggestion?: {
    from_time: string;
    to_time: string;
    from_next_day?: boolean;
    to_next_day?: boolean;
    kieu?: "bu_cap" | "tach_phien";
  } | null;
  punches: DayPunch[];
}

// --- Xác nhận tăng ca theo phiếu (07/09/2026) ---
export interface OtConfirmPunch {
  time: string;
  check_type: string;
  next_day: boolean;
}
export interface OtConfirmCandidate {
  ticket_id: number;
  employee_id: number;
  employee_code: string | null;
  employee_name: string;
  department_id: number | null;
  date: string;
  from_time: string;
  to_time: string;
  from_next_day: boolean;
  to_next_day: boolean;
  /** thieu_cap (xác nhận được) | da_co | treo | khong_cham | chua_gan_ca */
  tinh_trang: "thieu_cap" | "da_co" | "treo" | "khong_cham" | "chua_gan_ca";
  /** `chi_cap_tc` = ngày trắng lượt bấm: chỉ sinh CẶP TĂNG CA theo phiếu, ngày đó không có công
   *  ca chính ⇒ phải xác nhận riêng (`cho_phep_ngay_trang`). */
  kieu: "bu_cap" | "tach_phien" | "chi_cap_tc" | null;
  punches: OtConfirmPunch[];
}
export interface OtConfirmCandidates {
  date: string;
  items: OtConfirmCandidate[];
}
export interface OtConfirmInput {
  date: string;
  employee_ids: number[];
  reason?: string | null;
  /** Giờ RA tăng ca thực tế — chỉ có nghĩa khi xác nhận MỘT người kiểu `bu_cap`. */
  to_time?: string | null;
  to_next_day?: boolean;
  /** HCNS đã xác nhận riêng cho người KHÔNG bấm lượt nào cả ngày: chỉ sinh cặp TĂNG CA theo phiếu,
   *  chấp nhận ngày đó không có công ca chính. Thiếu cờ thì những người ấy bị bỏ qua. */
  cho_phep_ngay_trang?: boolean;
}
export interface OtConfirmResult {
  done: { employee_id: number; employee_name: string; kieu: string; punches: OtConfirmPunch[] }[];
  skipped: { employee_id: number; employee_name: string | null; reason: string }[];
}

export interface AdjustInput {
  employee_id: number;
  date: string;              // "YYYY-MM-DD"
  check_type: string;        // in | out
  time: string;              // "HH:MM"
  /** Giờ rơi SANG HÔM SAU (ca đêm quên RA 06:00; tăng ca vắt nửa đêm) — 07/09/2026. */
  next_day?: boolean;
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
  suggested_next_day?: boolean;
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
  /** Giờ gợi ý rơi sang hôm sau (ca đêm quên bấm RA sáng). */
  suggested_next_day?: boolean;
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
  /** 1 đơn vị NCC bán bằng bao nhiêu ĐƠN VỊ GỐC của mặt hàng. `null` = không quy đổi được —
   *  KHÔNG được coi là 1: hệ số 1 sai thì giá sai mà không ai thấy dòng lỗi nào. */
  he_so_ve_goc: number | null;
  /** Đơn giá quy về đ/đơn-vị-gốc = `unit_price ÷ he_so_ve_goc`. Con số DUY NHẤT so ngang được
   *  giữa các NCC báo theo đơn vị khác nhau (1.020.000đ/ram vs 24.500đ/kg).
   *  `null` = chưa quy đổi được ⇒ xếp CUỐI kèm lý do, đừng lặng lẽ dùng giá thô. */
  gia_quy_doi: number | null;
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
  /** Tên có dấu của đơn vị NCC bán ("thùng", "cái") để hiển thị; null = trùng mã / không tra được. */
  unit_ten: string | null;
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

  /** SAO ĐÁNH GIÁ — máy tự tính từ phiếu mua hàng, KHÔNG ai chấm tay.
   *
   *  Mốc hẹn là `needed_date` (Ngày cần hàng) của phiếu; giao đủ đúng/sớm hẹn = 5 sao, trễ 1–3
   *  ngày = 4, 4–7 = 3, 8–14 = 2, trên 14 = 1. Đơn chưa giao đủ mà đã quá hẹn thì tính trễ tới
   *  hôm nay. Trung bình toàn bộ lịch sử.
   *
   *  ⚠️ `null` = **Chưa đánh giá** (chưa có đơn nào đủ điều kiện), KHÔNG phải 0 sao. Giao diện
   *  phải hiện chữ "Chưa đánh giá" chứ đừng vẽ 5 ngôi sao rỗng — thang sao thấp nhất là 1, nên
   *  0 không bao giờ là một giá trị hợp lệ. Vẽ 0 là vu oan cho NCC mới. */
  rating: number | null;
  /** Số đơn ĐƯỢC TÍNH vào trung bình — không phải tổng số đơn của NCC. */
  rating_count: number;
  on_time_count: number;
  late_count: number;
  /** Trễ trung bình tính TRÊN CÁC ĐƠN TRỄ. `null` = chưa trễ đơn nào. */
  avg_late_days: number | null;
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
  | "needs_correction"
  /** Có món bị bỏ nhưng CHƯA bỏ hết (mg 0233). Đè lên nhãn tiến độ; tiến độ phần còn lại nằm ở
      `progress_status`. Bỏ hết món thì `status` = `cancelled`, không phải trạng thái này. */
  | "partially_cancelled";

export type DepartmentPurchaseSourceType =
  | "kinh_doanh"
  | "kho"
  | "san_xuat"
  | "cong_nghe"
  | "gia_cong_ngoai"
  | "khac";

export interface PurchaseRequestLineInput {
  /** Mặt hàng gốc (mg 0174). Gửi lên thì server tôn trọng; bỏ trống thì nó kế thừa từ dòng YCMH. */
  hang_loai?: HangLoai | null;
  hang_id?: number | null;
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

/** Một RỔ TUỔI NỢ. Sáu rổ: chưa tới hạn · trễ 1–7 · 8–15 · 16–30 · 31–60 · >60 ngày.
 *  Mốc do server giữ (`AGING_BUCKETS`) — đừng gõ lại số ngày ở giao diện. */
export interface AgingBucket {
  key: string;
  label: string;
  amount: number;
  count: number;
}

/** Rổ tuổi của MỘT nhà cung cấp / khách hàng — dạng bảng tra theo khoá rổ. */
export interface AgingCell {
  amount: number;
  count: number;
}

/** MỘT dòng của SỔ TỔNG HỢP CÔNG NỢ theo kỳ (docs/prd-bao-cao-cong-no.md §5.1).
 *
 *  ĐỪNG nhầm với `PayablesSummary`/`ReceivablesSummary`: hai kiểu kia là ảnh chụp TẠI HÔM NAY để
 *  đi đòi nợ. Kiểu này là sổ theo kỳ — đầu kỳ · phát sinh · cuối kỳ, khoảng ngày tự chọn.
 *
 *  Số ÂM không bao giờ xuất hiện: âm thì server đã đẩy sang cột bên kia (luật sổ Nợ/Có). */
export interface CongNoDong {
  /** `null` = dòng gom các khoản KHÔNG truy được về khách/NCC nào. Không cho bấm vào. */
  doi_tuong_id: number | null;
  /** Mã khách/NCC. `null` = chưa đặt mã ⇒ không đối chiếu mã với MISA được. */
  ma: string | null;
  ten: string;
  /** `131` (phải thu) hoặc `331` (phải trả). */
  tk: string;
  dau_no: number;
  dau_co: number;
  ps_no: number;
  ps_co: number;
  cuoi_no: number;
  cuoi_co: number;
  /** 6 rổ tuổi của RIÊNG đối tượng này, tính trên dư cuối kỳ TẠI `den_ngay`. */
  aging: Record<string, AgingCell>;
}

export interface CongNoTong {
  so_dong: number;
  dau_no: number;
  dau_co: number;
  ps_no: number;
  ps_co: number;
  cuoi_no: number;
  cuoi_co: number;
}

export interface BaoCaoCongNo {
  tk: string;
  tieu_de: string;
  /** Nhãn hai cột đầu do SERVER nói ("Mã khách hàng" vs "Mã nhà cung cấp") — một component dùng
   *  cho cả hai báo cáo, đừng gõ lại nhãn ở giao diện. */
  nhan_ma: string;
  nhan_ten: string;
  tu_ngay: string;
  den_ngay: string;
  items: CongNoDong[];
  tong: CongNoTong;
  /** Dải rổ tuổi TOÀN MÀN, có nhãn sẵn. Tính TẠI `den_ngay` — KHÁC dải ở màn Công nợ, cái đó
   *  luôn neo vào hôm nay. Đây là lý do báo cáo kỳ cũ in lại vẫn ra đúng con số cũ. */
  aging: AgingBucket[];
}

/** Một chứng từ trong sổ chi tiết. `no`/`co` là số của CHÍNH chứng từ đó, `luy_ke_*` là số dư
 *  SAU khi ghi nó — đúng khuôn sổ chi tiết công nợ của kế toán. */
export interface SoChiTietDong {
  ngay: string;
  /** Giờ ghi nhận (ISO). Phiếu chi/thu = lúc tiền chạy, còn lại = lúc nhập vào hệ. Ngày nghiệp vụ
   *  không có giờ, nên đây là thứ duy nhất tách được thứ tự các chứng từ cùng ngày. */
  luc: string | null;
  /** `hoa_don` · `phieu_thu` · `dot_giao` · `phieu_chi` · `hoan_tien`. */
  loai: string;
  so_ct: string;
  dien_giai: string;
  no: number;
  co: number;
  luy_ke_no: number;
  luy_ke_co: number;
}

/** SỔ CHI TIẾT CÔNG NỢ của MỘT đối tượng (PRD §5.1) — mở khi bấm một dòng ở sổ tổng hợp.
 *
 *  `cuoi_no`/`cuoi_co` LUÔN khớp ô "Dư cuối kỳ" của chính đối tượng đó bên sổ tổng hợp: hai bên
 *  đọc chung một luồng chứng từ ở server, và có test đối chiếu canh. */
export interface SoChiTietCongNo {
  tk: string;
  tieu_de: string;
  doi_tuong_id: number | null;
  ma: string | null;
  ten: string;
  tu_ngay: string;
  den_ngay: string;
  dau_no: number;
  dau_co: number;
  dong: SoChiTietDong[];
  ps_no: number;
  ps_co: number;
  cuoi_no: number;
  cuoi_co: number;
}

export interface CongNoKyRow {
  tu_ngay: string;
  den_ngay: string;
  ten: string | null;
  /** Khóa TRỌN khoảng — mọi ngày trong kỳ đều đang khóa. */
  da_khoa: boolean;
  /** Khóa MỘT PHẦN. Ba trạng thái chứ không phải hai — xem `CongNoKhoaSoTrangThai`. */
  khoa_mot_phan: boolean;
  /** Kỳ đang chạy (chứa hôm nay) ⇒ `den_ngay` dừng ở hôm nay, không phải cuối tháng. */
  dang_dien_ra: boolean;
  /** Mở lại được không. CHỈ kỳ mới nhất mở được: kỳ chốt sau lấy số dư đầu kỳ từ kỳ này, mở
   *  ngược là số của kỳ sau sai theo mà không có gì báo. */
  co_the_mo: boolean;
  khoa_luc: string | null;
}

/** Trạng thái khóa của MỘT khoảng bất kỳ.
 *
 *  Trước 04/09/2026 màn báo cáo tự suy bằng cách dò `congNoKyList` rồi so BẰNG ĐÚNG hai đầu ngày;
 *  kỳ báo cáo 01/09–04/09 không đời nào khớp kỳ tháng 01/09–30/09 nên luôn ra "chưa khóa", bấm
 *  khóa xong không thấy gì đổi. Giờ hỏi thẳng server đúng kỳ đang xem. */
export interface CongNoKhoaSoTrangThai {
  tu_ngay: string;
  den_ngay: string;
  da_khoa: boolean;
  khoa_mot_phan: boolean;
}

export interface CongNoKhoaSoRow {
  id: number;
  tu_ngay: string;
  den_ngay: string;
  hanh_dong: string;
  nguoi_khoa_ten: string | null;
  khoa_luc: string;
  ten: string | null;
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
  /** Rổ tuổi TOÀN MÀN. Tổng 5 rổ trễ luôn đúng bằng `overdue_amount`. */
  aging: AgingBucket[];
  period_months: number;
  as_of: string;
}

/** Một khoản CÒN NỢ — thường là một ĐỢT GIAO chưa trả hết.
 *
 * Phiếu cũ (lập trước 06/08/2026, không theo dõi theo đợt) hiện ở mức PHIẾU: `delivery_id` null,
 * `chua_dat_han` true. Không có hạn trả nên không bao giờ vào cột Quá hạn — vì thế nó phải nổi
 * lên ĐẦU danh sách chứ không được chìm. */
/** Một mặt hàng trong đợt giao — chỉ để bày trong popup "hàng đã nhận" ở Công nợ phải trả. */
export interface PayableDeliveryLineRow {
  item_name: string;
  /** MÃ đơn vị (`cai`); tên hiển thị ("cái") tra qua `tenDonVi()`. */
  unit: string;
  quantity: number;
  /** Đơn giá đã chốt trên phiếu mua (04/09/2026). */
  unit_price: number;
  /** Thành tiền THẬT của dòng trong đợt này — sau chiết khấu/VAT, và KHÔNG tính phần rơi vào
   *  `du`. Không phải `quantity × unit_price`. */
  thanh_tien: number;
  /** Phần giao VƯỢT số đặt, tính 0đ. > 0 = NCC giao nhiều hơn đơn đặt cho dòng này. */
  du: number;
}

export interface PayableHoaDonFile {
  id: number;
  file_name: string;
  file_url: string;
  file_type: string | null;
}

export interface PayableItemRow {
  purchase_request_id: number;
  code: string;
  status: PurchaseRequestStatus;
  /** Hàng của đợt. RỖNG với dòng "cả đơn" — phiếu cũ không theo dõi theo đợt nên không có hàng
   *  nào quy về được; màn hình phải KHÔNG cho bấm mở popup ở dòng đó. */
  lines: PayableDeliveryLineRow[];
  delivery_id: number | null;
  seq_no: number | null;
  delivery_date: string | null;
  due_date: string | null;
  chua_dat_han: boolean;
  overdue_days: number;
  /** Khoá rổ tuổi (vd "d31_60") — CHỈ có khi overdue_days > 0. Server chụp sẵn bằng cùng hàm
   *  dùng cho dải phân tuổi tổng, để một đợt không hiện hai mức khẩn khác nhau ở hai màn. */
  aging_bucket: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  /** File hoá đơn/biên bản đã đính kèm cho đợt này (04/09/2026). RỖNG = chưa ai upload ảnh —
   *  KHÁC với `invoice_number` trống (số có thể đã ghi tay mà chưa có ảnh). Upload vẫn đi qua
   *  Thu mua lúc ghi đợt giao; ở đây chỉ đọc lại. */
  hoa_don_files: PayableHoaDonFile[];
  amount: number;
  /** CHỈ đếm tiền trả ĐÍCH DANH đợt này — cột này phải khớp sao kê NCC theo từng đợt. */
  paid: number;
  /** Phần CỌC của cả đơn chiếu xuống đợt này (giao trước bù trước). Tách khỏi `paid` vì không ai
   *  trả riêng cho đợt này số đó — nhưng `con_no` đã trừ CẢ HAI. */
  coc_bu: number;
  con_no: number;
  /** Đợt đã trả hết — có mặt CHỈ để dò được tiền cọc đi đâu (cọc bù giao-trước-bù-trước nên hay
   *  nuốt trọn đợt sớm). Làm mờ, xếp cuối đơn, không đếm vào rổ tuổi / lời nhắc "chưa đặt hạn". */
  da_tat_toan: boolean;
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
  /** Rổ tuổi của riêng NCC này, dựng từ chính `items`. */
  aging: AgingBucket[];
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
  /** Rổ tuổi của RIÊNG khách này, tra theo khoá rổ. Khách không nợ vẫn đủ 6 khoá = 0. */
  aging: Record<string, AgingCell>;
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
  /** Rổ tuổi TOÀN MÀN. Tổng 5 rổ trễ luôn đúng bằng `overdue_amount`. */
  aging: AgingBucket[];
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
  /** Khoá rổ tuổi — CHỈ có khi `overdue_days > 0`. Server chụp sẵn bằng cùng hàm dùng cho dải
   *  tổng, để một hoá đơn không hiện hai mức khẩn khác nhau ở hai màn. */
  aging_bucket: string | null;
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
  /** Rổ tuổi của riêng khách này, dựng từ chính `items`. */
  aging: AgingBucket[];
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
  /** Chỉ lúc TẠO (từ Kế hoạch vật tư): yêu cầu này mua cho lệnh/bài nào. Server lưu lại để "Ngày
   *  cần" của lệnh đọc ngược từ `needed_date` — sửa phiếu sau đó không đụng tới. */
  nguon_lenh?: CanDoiKhoaDong[];
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
  /** Dòng YCMH đẻ ra dòng này (mg 0174b) — form SỬA cần đọc lại để gửi đúng liên kết. */
  department_request_line_id: number | null;
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
  /** Khác null = MÓN NÀY đã bị bỏ khỏi yêu cầu (mg 0233). Vẫn hiện trong danh sách, gạch ngang
      kèm lý do — xoá khỏi màn là người xem tưởng mình nhớ nhầm. */
  cancelled_at: string | null;
  cancelled_by_name: string | null;
  cancel_reason: string | null;
  /** Luật "bỏ được không" do MÁY CHỦ chốt. false + `cancel_block_reason` ⇒ vẫn bày nút, khoá lại
      và in đúng câu đó (đừng ẩn nút — khoá và nói lý do). Chỉ nói về tình trạng MÓN; quyền của
      người đang xem thì màn hình tự AND thêm. */
  can_cancel: boolean;
  cancel_block_reason: string | null;
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
  /** Nhãn TIẾN ĐỘ thuần, không bị "Huỷ một phần" che — in thành dòng chữ nhỏ dưới huy hiệu. */
  progress_status: DepartmentPurchaseWorkflowStatus;
  cancelled_line_count: number;
  active_line_count: number;
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
  /** SL THỰC NHẬN của đợt. Từ 28/08/2026 ĐƯỢC PHÉP vượt số đặt (NCC giao thêm, giá giữ nguyên). */
  quantity: number;
  /** Phần của `quantity` có sinh tiền. Server chia LUỸ KẾ theo thứ tự đợt, lấp phần tính tiền
   *  trước — xem `phan_bo_du_dot` bên backend. */
  quantity_tinh_tien: number;
  /** Phần DƯ, giá 0đ. `quantity_tinh_tien + quantity_du === quantity`.
   *  PHẢI hiện ra chứ đừng chỉ hiện tổng: hệ không biết phần dư có thật là hàng tặng hay không,
   *  nên phải để người đọc bắt được ca NCC thực ra CÓ tính tiền phần dư. */
  quantity_du: number;
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
  /** NGÀY CHỐT CÔNG NỢ do NCC báo cho ĐƠN (YYYY-MM-DD). Hạn trả MỌI đợt của đơn = ngày này +
   *  số ngày cho nợ của NCC. `null` = chưa báo ⇒ hạn lùi về luật cũ (ngày hoá đơn + số ngày). */
  debt_cutoff_date?: string | null;
  /** Cọc DỰ KIẾN — chỉ để đối chiếu, KHÔNG vào công thức công nợ (cọc thật là phiếu chi). */
  deposit_expected: number;
}

/** Hạn mức công nợ của NCC so với nợ hiện tại — CẢNH BÁO MỀM, không chặn gì (Đ6). */
export interface SupplierCredit {
  /** Điều khoản thanh toán (chữ tự do). `null` = NCC chưa khai. */
  payment_terms: string | null;
  /** `0` = KHÔNG đặt hạn mức ⇒ không bao giờ báo vượt. Đừng đọc thành "hạn mức 0đ". */
  credit_limit: number;
  /** `null` = chưa đặt hạn (đợt giao không vào cột Quá hạn) · `0` = TRẢ NGAY. Hai ca khác hẳn
   *  nhau, đừng gộp — xem chú thích ở form khai NCC (`SupplierInfoTab`). */
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
  /** NGÀY CHỐT CÔNG NỢ NCC báo cho đơn. Hạn trả MỌI đợt = ngày này + số ngày cho nợ của NCC —
   *  đồng hồ chạy từ mốc CHỐT, không phải từ ngày hoá đơn. `null` = chưa báo. */
  debt_cutoff_date: string | null;
  /** Chụp `credit_days` của NCC — để suy hạn trả ngay tại ô gõ ngày chốt. `null` = NCC chưa khai. */
  supplier_credit_days: number | null;
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
  /** Phiếu chi lập TỪ một phiếu tạm ứng lương đã duyệt (18/08/2026). Số tiền + người nhận do
   *  backend lấy thẳng từ phiếu tạm ứng, payload gửi lên bị bỏ qua. */
  | "salary_advance"
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
  /** Phiếu TẠM ỨNG LƯƠNG nguồn. Truyền id này thì `source_type` tự thành `salary_advance`, còn
   *  `amount` + `cash_recipient_name` gửi lên BỊ BỎ QUA — backend lấy số tiền và tên nhân viên
   *  của chính phiếu tạm ứng, để phiếu chi không lệch số đã duyệt. */
  salary_advance_id?: number | null;
}

/** MỘT đợt giao được chọn để trả trong lượt thanh toán gộp (04/09/2026). */
export interface VoucherBatchItem {
  purchase_request_id: number;
  delivery_id: number;
}

/** Thanh toán NHIỀU đợt giao — của CÙNG một nhà cung cấp — trong MỘT lượt.
 *
 *  Cố ý KHÔNG có `amount`/`delivery_id`/`payment_stage` ở đây: batch LUÔN trả HẾT từng đợt đã
 *  chọn (server tự tính đúng số còn nợ tại thời điểm lập), không trả một phần — và luôn là
 *  phiếu THANH TOÁN, không phải đặt cọc. `content` bỏ trống thì mỗi phiếu tự đặt câu riêng. */
export interface VoucherBatchInput extends PaymentVoucherAccountsInput {
  items: VoucherBatchItem[];
  voucher_type: PaymentVoucherType;
  voucher_date: string;
  currency?: string;
  exchange_rate?: number;
  content?: string | null;
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
}

export interface VoucherBatchResult {
  vouchers: PaymentVoucherRow[];
  total_amount: number;
}

/** Những ô kế toán THẬT SỰ khai khi lập phiếu chi từ một phiếu tạm ứng lương đã duyệt.
 *  Cố tình KHÔNG có `cash_recipient_name`: backend điền tên từ hồ sơ nhân viên. */
export interface SalaryAdvanceVoucherInput {
  salary_advance_id: number;
  /** Số tiền của CHÍNH phiếu tạm ứng. Vẫn phải gửi vì schema đòi `amount > 0`, nhưng backend GHI
   *  ĐÈ bằng số của phiếu tạm ứng — gửi số khác chỉ tự lừa mình, phiếu chi vẫn ra số đã duyệt. */
  amount: number;
  voucher_type: PaymentVoucherType;
  /** YYYY-MM-DD. Backend từ chối ngày ở TƯƠNG LAI (422). */
  voucher_date: string;
  content: string;
  note?: string | null;
  /** Hai ô của mẫu 02-TT tiền mặt (người nhận ký tại quỹ khai địa chỉ + CCCD). Không bắt buộc;
   *  chuyển khoản thì bỏ trống vì tài khoản thụ hưởng đã là bằng chứng nhận tiền. */
  cash_recipient_address?: string | null;
  cash_recipient_identity?: string | null;
  /** CHỈ khi `voucher_type = "bank_transfer"`. Backend bắt buộc đủ tài khoản trích nợ + tên/số
   *  tài khoản/ngân hàng thụ hưởng, thiếu một ô là 422 — tiền mặt thì bỏ trống hết. */
  company_bank_account_id?: number | null;
  beneficiary_account_holder?: string | null;
  beneficiary_account_number?: string | null;
  beneficiary_bank_name?: string | null;
  beneficiary_bank_branch?: string | null;
  bank_fee_bearer?: "payer" | "beneficiary" | "shared" | null;
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
  /** Phiếu tạm ứng lương nguồn — chỉ có giá trị khi `source_type = salary_advance`.
   *  Một phiếu tạm ứng chỉ gắn ĐÚNG MỘT phiếu chi (UNIQUE ở DB). */
  salary_advance_id: number | null;
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
  don_vi_tinh: string;   // ĐVT THẬT của phần này (kéo từ báo giá / gõ tay)
  dvt_nhom: string | null;   // ĐVT của cụm khi in gộp ("cuốn") — xem `QuoteItem.dvt_nhom`
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

/** 1 nhãn đã gán cho một BƯỚC công đoạn (LSX / Bài ghép). */
export interface CongDoanTagRow {
  id: number;
  label: string;
}

/** 1 nhãn trong KHO nhãn công đoạn + số BƯỚC đang mang nó (để hỏi trước khi xoá — như `KhoNhanRow`
 *  của khách, chỉ khác `so_khach` → `so_buoc`). */
export interface KhoNhanBuocRow {
  id: number;
  label: string;
  so_buoc: number;
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
  /** `khuon_be` | `khuon_ep` | `khung_lua` — CÙNG bộ mã với `cong_doan.tooling_type` để lọc bằng
   *  phép so thẳng. */
  loai: string | null;
  so_ke: string | null;
  tinh_trang: string;
  active: boolean;
}

/** 1 con dao chọn được cho bước của một lệnh — server đã lọc theo khách của lệnh. */
export interface KhuonChonDuoc {
  id: number;
  ma: string;
  ten: string;
  /** `khuon_be` | `khuon_ep` | `khung_lua` — CÙNG bộ mã với `cong_doan.tooling_type`.
   *  null = dao khai trước mg 0205, chưa ai phân loại — VẪN hiện ở mọi bước, giấu đi là bắt
   *  người ta đi làm lại con dao đang nằm trên kệ. */
  loai: string | null;
  so_ke: string | null;
  tinh_trang: string;
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
  /** Kho đã CHỐT thực xuất bao nhiêu (điều chỉnh phiếu xuất). Null = kho CHƯA điều chỉnh lần
   *  nào — khác hẳn 0 (đã chốt là không xuất gì). Có giá trị → hiện "thực xuất N / yêu cầu M"
   *  thay vì "còn thiếu". */
  sl_chot_thuc_xuat: number | null;
  /** Đơn giá NHẬP người đề nghị khai — phiếu kế thừa (kho chỉ đọc). Null với đề nghị XUẤT.
   *  Mọi trường TIỀN của dòng (`don_gia`, `gia_goc`, `don_gia_ban`) chỉ có khi `kho:view_cost` —
   *  người tạo yêu cầu cũng không ngoại lệ; thiếu quyền → null. */
  don_gia: number | null;
  /** Dòng thành phẩm KCS gửi nhập: `don_gia` luôn 0, giá gốc thật đọc ở lô sau khi kế toán kho gõ.
   *  `gia_goc` null = "Chưa có giá gốc" (chưa nhập lô nào, hoặc còn lô 0 đ). */
  tu_kcs: boolean;
  gia_goc: number | null;
  /** Tiền gốc đã nhập = Σ giá × SL từng đợt đã ghi sổ (không phải `gia_goc` × SL — giá bình quân
   *  đã làm tròn nhân ngược lệch tổng các phiếu). Null cùng lúc với `gia_goc`. */
  tien_goc: number | null;
  /** Giá bán theo đơn hàng (chỉ để đọc, không vào sổ) + số đơn đi kèm. */
  don_gia_ban: number | null;
  don_ban_ma: string | null;
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
  /** ĐIỀU CHUYỂN KHO: yêu cầu NHẬP đích có `kho_nguon_id` ⇒ là YÊU CẦU ĐIỀU CHUYỂN
   *  (nhãn "Điều chuyển từ «kho_nguon_ten»", phiếu nhập KHOÁ đơn giá). `xuat_voucher_id` =
   *  phiếu xuất nguồn đã ghi sổ (truy cặp đi–đến). */
  dieu_chuyen: boolean;
  kho_nguon_id: number | null;
  kho_nguon_ten: string | null;
  xuat_voucher_id: number | null;
  /** Yêu cầu SINH TỪ đề nghị cấp vật tư công đoạn — ba trường đều null với yêu cầu kho THƯỜNG
   *  (không do sản xuất lập), khỏi phải phân nhánh ở FE. */
  /** GIỜ cần thật (từ đề nghị sản xuất). `ngay_can` chỉ có DATE nên không diễn đạt được ca chiều. */
  can_luc: string | null;
  san_xuat_cong_viec_id: number | null;
  san_xuat_cong_doan_ten: string | null;
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
  /** true = CHỈ yêu cầu điều chuyển (tab Điều chuyển) · false = nhập/xuất thường · bỏ = không lọc. */
  dieu_chuyen?: boolean | null;
  /** Lọc theo NGÀY CẦN (ngay_can) — ISO yyyy-mm-dd. */
  ngay_can_tu?: string | null;
  ngay_can_den?: string | null;
  /** Lọc theo NGÀY TẠO (created_at) — ISO yyyy-mm-dd. */
  tao_tu?: string | null;
  tao_den?: string | null;
  /** Thứ tự: "id" = mới tạo trước (mặc định) · "updated" = vừa đổi trước (Hộp yêu cầu). */
  order?: "id" | "updated";
  page?: number;
  size?: number;
}

/** Query-string các bộ lọc yêu cầu kho — dùng chung cho `list` + `tabCounts` (KHÔNG gồm page/size). */
function stockRequestQS(params: StockRequestListParams): URLSearchParams {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.loai) qs.set("loai", params.loai);
  // `trang_thai` là list ở backend → lặp param, KHÔNG nối bằng dấu phẩy.
  for (const s of params.trang_thai ?? []) qs.append("trang_thai", s);
  if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
  if (params.dieu_chuyen != null) qs.set("dieu_chuyen", String(params.dieu_chuyen));
  if (params.ngay_can_tu) qs.set("ngay_can_tu", params.ngay_can_tu);
  if (params.ngay_can_den) qs.set("ngay_can_den", params.ngay_can_den);
  if (params.tao_tu) qs.set("tao_tu", params.tao_tu);
  if (params.tao_den) qs.set("tao_den", params.tao_den);
  return qs;
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
  /** Hạn sử dụng của lô dòng này (ISO yyyy-mm-dd) — từ stock_lots.hsd. */
  han_su_dung: string | null;
  /** ĐIỀU CHUYỂN nội bộ: gắn nhãn "điều chuyển" + LOẠI khỏi tổng mua/bán ở Tổng quan. */
  dieu_chuyen: boolean;
}

export interface BaoCaoKhoPage {
  items: BaoCaoKhoRow[];
  total: number;
}

/** Bộ lọc funnel theo CỘT (giống bảng đang xem) — để "xuất Excel" = đúng bảng, không kéo thừa dòng
 *  đã bị lọc cột. Khoảng BAO GỒM hai đầu; để trống = không chặn. */
export interface BaoCaoFunnel {
  ct_from?: string | null;   // Ngày CT từ (yyyy-mm-dd)
  ct_to?: string | null;
  sl_from?: number | null;   // Số lượng
  sl_to?: number | null;
  dg_from?: number | null;   // Đơn giá / đơn giá vốn
  dg_to?: number | null;
  tt_from?: number | null;   // Thành tiền / tiền vốn
  tt_to?: number | null;
}

export interface BaoCaoKhoParams extends BaoCaoFunnel {
  tu?: string | null;
  den?: string | null;
  kho_id?: number | null;
  loai?: StockRequestKind | null;
  /** Tìm số CT / mã hàng / tên hàng — để "lọc gì = xuất nấy" (cả bảng lẫn file). */
  q?: string | null;
}

/** Đắp 8 tham số funnel (nếu có) vào query — dùng chung cho 2 endpoint export báo cáo kho. */
function setFunnelQs(qs: URLSearchParams, f: BaoCaoFunnel): void {
  if (f.ct_from) qs.set("ct_from", f.ct_from);
  if (f.ct_to) qs.set("ct_to", f.ct_to);
  if (f.sl_from != null) qs.set("sl_from", String(f.sl_from));
  if (f.sl_to != null) qs.set("sl_to", String(f.sl_to));
  if (f.dg_from != null) qs.set("dg_from", String(f.dg_from));
  if (f.dg_to != null) qs.set("dg_to", String(f.dg_to));
  if (f.tt_from != null) qs.set("tt_from", String(f.tt_from));
  if (f.tt_to != null) qs.set("tt_to", String(f.tt_to));
}

/** Báo cáo kho — 1 dòng điều chuyển đã ghi sổ (Xuất tại kho → Nhập tại kho). */
export interface BaoCaoChuyenKhoRow {
  voucher_id: number;
  ngay_ghi_so: string | null;
  ngay_ct: string | null;
  so_ct: string;
  ma_hang: string | null;
  ten_hang: string | null;
  dvt: string | null;
  so_luong: number;
  don_gia_von: number | null;
  tien_von: number | null;
  kho_xuat_ten: string | null;
  kho_nhap_ten: string | null;
  /** ID kho nguồn/đích — để Sổ Chuyển kho tô màu + ổ khóa theo kỳ đã khóa (như Nhập/Xuất). */
  kho_xuat_id: number | null;
  kho_nhap_id: number | null;
  dien_giai: string | null;
}

export interface BaoCaoChuyenKhoPage {
  items: BaoCaoChuyenKhoRow[];
  total: number;
}

export interface BaoCaoChuyenKhoParams extends BaoCaoFunnel {
  tu?: string | null;
  den?: string | null;
  kho_id?: number | null;
  q?: string | null;
}

/** 1 dòng Nhập-Xuất-Tồn theo kỳ (bình quân gia quyền cuối kỳ) của 1 mặt hàng tại 1 kho. */
export interface BaoCaoNXTRow {
  kho_id: number | null;
  kho_ten: string | null;
  hang_loai: string;
  hang_id: number;
  ma_hang: string | null;
  ten_hang: string | null;
  hang_nhom: string | null;
  dvt: string | null;
  dau_sl: number;
  // Bốn ô GIÁ TRỊ về null khi vai không có ô "Xem giá thành" của Kho — xem `_an_tien` bên
  // `routers/kho_baocao.py`. Số lượng vẫn đủ, chỉ tiền là trống.
  dau_gt: number | null;
  nhap_sl: number;
  nhap_gt: number | null;
  xuat_sl: number;
  xuat_gt: number | null;
  cuoi_sl: number;
  cuoi_gt: number | null;
  don_gia_bq: number | null;
}

export interface BaoCaoNXTPage {
  items: BaoCaoNXTRow[];
  total: number;
  tu: string | null;
  den: string | null;
  /** Kỳ này ĐÃ tính giá (có snapshot chốt) chưa. false = đang tạm tính live. */
  da_tinh: boolean;
  /** Kỳ này (theo ngày cuối) đã khóa sổ chưa — đã khóa thì không tính lại. */
  da_khoa: boolean;
  /** `den` rơi GIỮA một kỳ ĐÃ TÍNH (chốt ở ngày khác): mốc chốt + tên kỳ đó. Khi có, bảng vẫn
   *  hiện Giá trị cuối kỳ nhưng là số TẠM TÍNH tới `den` (khác số đã chốt). */
  ky_da_tinh_den: string | null;
  ky_da_tinh_ten: string | null;
}

export interface BaoCaoNXTParams {
  tu: string;
  den: string;
  kho_id?: number | null;
  q?: string | null;
}

export interface TinhGiaKyInput {
  tu: string;
  den: string;
  ten?: string | null;
  kho_id?: number | null;
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

/** 1 lần XUẤT EXCEL báo cáo kho — cho tab "Lịch sử thao tác". */
export interface KhoExportLog {
  thoi_diem: string;
  hanh_dong: string;            // "export" (xuất Excel) | "tinh_gia" (tính giá kỳ)
  loai: string;                 // "Nhập kho" / "Xuất kho" / "Chuyển kho" / "Tính giá kỳ"
  pham_vi: string;              // loại · kho
  khoang_ngay: string | null;
  ten_ky: string | null;        // tên kỳ nếu khoảng ngày trùng kỳ đã khóa; "Toàn bộ" nếu ko lọc ngày
  nguoi_ten: string | null;
}

/** 1 kỳ CÒN đang khóa (đã gộp khoảng liền mạch) — cho tab "Kỳ đã khóa". */
export interface KhoaSoKyRow {
  kho_id: number | null;
  kho_ten: string | null;
  tu_ngay: string;
  den_ngay: string;
  khoa_luc: string | null;
  ten: string | null;
  /** (Kỳ TOÀN KHO) tên các kho đã MỞ RIÊNG trong kỳ này → hiển thị "Toàn kho — trừ: …". */
  mien_tru?: string[];
}

/** 1 kỳ ĐÃ TÍNH GIÁ (có snapshot) — cho tab "Kỳ đã tính". */
export interface KyDaTinh {
  tu_ngay: string;
  den_ngay: string;
  ten: string | null;
  so_mat_hang: number;
  so_kho: number;
  tong_gt_cuoi: number;
  tinh_luc: string;
  da_khoa: boolean;
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
 *  cố ý tách khỏi `xam` ("đã cấp đủ"), vì dán nhãn đủ lên dòng chưa ai tính nổi là nói ngược.
 *  Không còn `ve_muon` (18/09/2026): hệ không suy ngày cần nên không có mốc nào để chê hàng về muộn. */
export type CanDoiMau = "xam" | "xanh" | "vang" | "do" | "khong_ro";

/** Trạng thái GIỮ CHỖ 5 mức — khác `CanDoiMau` (3 mức trung tính gộp lại): ở đây tách được "đã
 *  giữ" khỏi "có thể giữ nhưng chưa bật" khỏi "đã cấp thật". */
export type TrangThaiGiu = "khong_ro" | "thieu" | "co_the_giu" | "da_giu" | "da_cap";

export interface CanDoiDong {
  /** `vat_tu` = so tồn · `cong_cu` = khuôn bế, KHÔNG so tồn (chỉ hỏi sẵn sàng đúng lúc chưa). */
  loai: "vat_tu" | "cong_cu";
  lsx_id: number | null;
  bai_ghep_id: number | null;
  /** Bước tiêu thụ — phần thứ NĂM của khoá dòng. Một lệnh có nhiều công đoạn và mỗi công đoạn khai
   *  vật tư riêng, nên cùng một món ở hai bước là HAI dòng; thiếu nó thì hai dòng trùng khoá và
   *  yêu cầu mua ra đúng một nửa số cần. Phải gửi lại y nguyên ở `CanDoiKhoaDong`. */
  buoc_id: number | null;
  ma: string;
  /** Lệnh có cờ GẤP — CHỈ ĐỂ BÀY. Máy không xếp ưu tiên, không cướp chỗ; người lập kế hoạch nhìn
   *  rồi tự quyết. */
  is_rush: boolean;
  ten_viec: string | null;
  /** "Ngày cần hàng" người lập gõ trên yêu cầu mua đã lập cho lệnh/bài này (sớm nhất) — đọc ngược,
   *  KHÔNG suy. Chưa lập yêu cầu mua nào (vd tồn đủ) ⇒ `null`, hiện trống. */
  ngay_can: string | null;
  /** Khách của lệnh. Dòng BÀI GHÉP gom nhiều lệnh: một khách thì là tên, nhiều khách thì server
   *  trả thẳng chuỗi `"3 khách"` — FE in nguyên, không tự diễn giải. */
  khach_ten: string | null;
  /** Hạn giao KHÁCH — khác hạn nội bộ mà bảng dùng xếp thứ tự ăn tồn. */
  han_giao_khach: string | null;
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
  /** [MỚI 30/08/2026] Giữ chỗ gộp theo (chủ thể, mặt hàng) — KHÔNG phải phần riêng của dòng khi
   *  cùng chủ thể ăn cùng món ở nhiều bước. */
  da_giu_kho: number | null;
  da_giu_dang_ve: number | null;
  co_the_giu_kho: number | null;
  co_the_giu_dang_ve: number | null;
  trang_thai_giu: TrangThaiGiu | null;
  nguon_dang_ve: { purchase_request_line_id: number; ma_pmh: string | null; so_luong: number }[] | null;
  canh_bao: string[];
  ly_do_canh_bao: string | null;
}

/** Một phiếu ĐANG CHẠY của mặt hàng — chỉ đủ để GỌI TÊN, không mang số lượng, không mang tiền.
 *
 *  Trả lời câu *"cái nào đang yêu cầu mua"*: trước đó ba tình huống rất khác nhau (chưa ai mua ·
 *  đã đề nghị chờ duyệt · đã duyệt mà NCC chưa hẹn ngày) đều vẽ ĐỎ giống hệt, nên người dùng bấm
 *  Mua chồng lên phiếu đã có. */
export interface PhieuMuaTom {
  /** `PMH-…` (phiếu của thu mua) hoặc `YCMH-…` (đề nghị của bộ phận). */
  ma: string;
  /** Hai chuỗi khác nhau, tra ở hai màn khác nhau, nên phải phân biệt được. */
  loai: "pmh" | "ycmh";
  /** Trạng thái THÔ (`pending_approval`, `approved`, `open`, `in_purchase`…). Dịch ở FE để đổi
   *  chữ khỏi phải đụng backend. */
  trang_thai: string;
  /** Chỉ PMH đã hẹn ngày mới có. `null` = đã có người lo nhưng chưa hứa được ngày nào. */
  ngay_ve: string | null;
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
  /** Phiếu đang chạy của mặt hàng, xếp CHẮC → LỎNG (đã duyệt có ngày về đứng đầu). Treo ở NHÓM
   *  chứ không ở dòng: phiếu mua không biết lệnh nào, nó chỉ biết mua món gì. */
  phieu_mua: PhieuMuaTom[];
  dong: CanDoiDong[];
}

/** `bo_qua` (lệnh/bài không cân đối được) GỠ 23/09/2026 — chưa khai vật tư thì vắng mặt, không
 *  cảnh báo; cửa chặn nằm ở xếp lịch. */
export interface CanDoiOut {
  items: CanDoiNhom[];
  /** Số lệnh giữ lâu chưa vào kế hoạch — toàn xưởng, không theo `q` (cùng nghĩa `TheoLenhOut`). */
  so_giu_lau: number;
}

/** Khoá của một dòng trên bảng — đủ để server tìm lại và TỰ tính phần thiếu.
 *
 *  ⚠️ NĂM phần tử, phải khớp `_khoa_dong()` bên `services/ke_hoach_vat_tu_service.py`. Lệch một
 *  phần tử là server tra không ra dòng nào và MỌI lần bấm "Đề nghị mua" trả 400 với câu lỗi chỉ
 *  sai đường ("tải lại bảng" — tải lại vẫn lỗi). */
export interface CanDoiKhoaDong {
  hang_loai: HangLoai;
  hang_id: number;
  lsx_id: number | null;
  bai_ghep_id: number | null;
  buoc_id: number | null;
}

/** Bản NHÁP của yêu cầu mua, tính từ các dòng đã tick — server CHƯA ghi gì.
 *
 *  Dùng để mở form "Tạo yêu cầu mua hàng" đã điền sẵn: nội dung · từng dòng vật tư đã gộp theo
 *  mặt hàng · lệnh nguồn. Người dùng gõ NGÀY CẦN HÀNG rồi tự bấm Lưu — yêu cầu chỉ sinh ra lúc đó. */
export interface DeNghiMuaXemTruoc {
  related_document_type: string;
  related_document_code: string;
  /** Luôn `null` (18/09/2026): hệ không suy ngày cần — để trống cho người lập tự gõ. */
  needed_date: string | null;
  noi_dung: string;
  lines: {
    hang_loai: HangLoai;
    hang_id: number;
    item_name: string;
    unit: string;
    quantity: number;
  }[];
  /** Khoá các dòng đã tick — form gửi nguyên văn vào `nguon_lenh` lúc Lưu. */
  nguon: CanDoiKhoaDong[];
}

/** Một MẶT HÀNG mà một lệnh/bài cần — đã gộp mọi công đoạn của lệnh đó. */
export interface TheoLenhHang {
  hang_loai: HangLoai;
  hang_id: number;
  hang_ma: string | null;
  hang_ten: string | null;
  don_vi_goc: string | null;
  /** Theo ĐƠN VỊ GỐC, đã trừ phần kho cấp rồi. */
  can: number;
  thieu: number;
  dang_giu: number;
  /** [MỚI 30/08/2026] Tách nguồn phần đã giữ + trạng thái giữ 6 mức — xem `TrangThaiGiu`. */
  da_giu_kho: number;
  da_giu_dang_ve: number;
  co_the_giu_kho: number;
  co_the_giu_dang_ve: number;
  trang_thai_giu: TrangThaiGiu;
  /** Mã PMH cụ thể đang góp cho `da_giu_dang_ve` — để hiện "đang bám đơn nào". */
  nguon_dang_ve: { purchase_request_line_id: number; ma_pmh: string | null; so_luong: number }[];
  /** >1 nghĩa là con số trên đã GỘP nhiều công đoạn — hiện ra để không ai tưởng đó là một bước. */
  so_buoc: number;
  /** Màu NẶNG NHẤT trong các bước. Thẻ chỉ hiện được một màu. */
  trang_thai: CanDoiMau;
  /** Ngày cần hàng trên yêu cầu mua đã lập cho lệnh này mua món này (sớm nhất). Chưa mua ⇒ `null`. */
  ngay_can: string | null;
  /** Bao nhiêu lệnh/bài KHÁC đang thiếu chính món này — câu *"nhả ra thì ai đỡ"* của hộp xác nhận.
   *  Server đếm trên TOÀN BỘ bảng, trước mọi bộ lọc. */
  so_lenh_khac_thieu: number;
  /** MỌI phiếu đang chạy của món (kể cả YCMH chưa duyệt, kể cả PMH chưa hẹn ngày), xếp CHẮC →
   *  LỎNG — "ai đang lo món này". */
  phieu_mua: PhieuMuaTom[];
  /** Khoá 5 phần của TỪNG dòng đỏ — gửi thẳng vào `deNghiMua`. Cố ý không gộp về một khoá cho
   *  mỗi mặt hàng: một lệnh ăn cùng món ở hai công đoạn là hai dòng, gộp là mua một nửa. */
  khoa_do: CanDoiKhoaDong[];
}

/** Một thẻ = MỘT lệnh (hoặc bài ghép) — cách nhìn *"lệnh này chạy được chưa"*. */
export interface TheoLenhRow {
  lsx_id: number | null;
  bai_ghep_id: number | null;
  ma: string;
  is_rush: boolean;
  /** Ngày cần hàng SỚM NHẤT trên các yêu cầu mua đã lập cho lệnh. Lệnh không phải mua ⇒ `null`. */
  ngay_can: string | null;
  /** Khách + hạn giao khách — xem `CanDoiDong.khach_ten` / `.han_giao_khach`. */
  khach_ten: string | null;
  han_giao_khach: string | null;
  /** Còn giữ chỗ nhưng ĐÃ RƠI khỏi bảng cân đối (lệnh bị kéo về nháp…). Vẫn trừ vào tồn tự do của
   *  mọi người khác, nên phải bày ra để có đường nhả. */
  ngoai_pham_vi: boolean;

  bat: boolean;
  /** Giữ đủ 100% ⇒ cửa xếp lịch mở. Đây là điều kiện DUY NHẤT của cửa đó. */
  du: boolean;
  khong_ro: boolean;
  /** Ngày sớm nhất được xếp bước tiêu thụ — `null` khi mọi phần đều là hàng có thật trong kho. */
  xep_som_nhat: string | null;
  da_xep_lich: boolean;
  giu_tu: string | null;
  so_ngay_giu: number | null;
  /** Đã bật · giữ quá ngưỡng · mà chưa hề đưa vào kế hoạch. Máy CHỈ BÀY, KHÔNG tự nhả. */
  giu_lau_chua_chay: boolean;

  so_mat_hang: number;
  so_thieu: number;
  so_khong_ro: number;
  hang: TheoLenhHang[];
}

export interface TheoLenhOut {
  items: TheoLenhRow[];
  /** Đếm trên TOÀN BỘ danh sách, không phải phần đang lọc. */
  so_giu_lau: number;
}

// --- Hồ sơ lệnh sản xuất (module `lenh_san_xuat`) — màn TRA CỨU, chỉ đọc -----
// Mirror ĐÚNG `backend/app/schemas/lenh_san_xuat.py`. Bẫy Pydantic của repo: service trả `dict`,
// router khai `response_model` ⇒ trường không có trong schema bị NUỐT IM LẶNG (FE nhận
// `undefined`, không lỗi, không cảnh báo). Nên đừng khai thêm trường nào ở đây mà bên kia không
// có — và thêm thật thì phải đi hết chuỗi `danh_sach._dong()` → schema → type này.
//
// KHÔNG MỘT TRƯỜNG TIỀN NÀO (`don_gia`/`gia_von`/`thanh_tien`/`luong_khoan`/`chi_phi`) — ràng
// buộc cứng của cả module, có bài canh `test_khong_lo_tien` giữ ở máy chủ.

/** 6 trạng thái CHÍNH của một lệnh (`services/lenh_sx/trang_thai.TAB_CHINH`). Chuỗi khoá đi
 *  thẳng ra URL (`?tab=`) nên nó là HỢP ĐỒNG — đừng đổi cho "dễ đọc". */
export type LsxTheoDoiTrangThai =
  | "dang_sx" | "canh_bao" | "kcs" | "cho_nhap_kho" | "san_sang_giao" | "hoan_thanh";

/** Tab thứ bảy của màn — "tất cả", KHÔNG phải một trạng thái. */
export type LsxTheoDoiTab = "tat_ca" | LsxTheoDoiTrangThai;

export type LsxTheoDoiCanhBao =
  | "su_co" | "tam_dung" | "tre_han" | "kcs_khong_dat" | "thieu_vat_tu";

/** MỘT đốt trên dải công đoạn của một dòng bảng lệnh (`danh_sach.chang()` phía máy chủ).
 *  Một bước bị tách nhiều lần chạy vẫn gộp về MỘT đốt, và đúng một đốt mang `hien_tai`. */
export interface LenhSxChang {
  ten: string;
  nhom: string | null;
  /** `xong` · `chay` · `dung` · `cho` — hợp đồng với hằng `CHANG_*` của backend và với lớp
   *  `.hslsx__chang--*` bên CSS. Khai `string` chứ không union: giá trị lạ phải hiện ra thành
   *  đốt trung tính chứ không làm gãy cả bảng. */
  trang_thai: string;
  hien_tai: boolean;
}

export interface LenhSxItem {
  id: number;
  ma: string;
  ten: string | null;
  khach_hang: string | null;
  /** CÓ trả về nhưng màn danh sách KHÔNG dùng: bấm tên khách để nhảy sang màn Khách hàng đòi
   *  quyền `khach_hang`, mà vai QC / tổ trưởng không có ⇒ bày link ra là mời ăn 403 giữa luồng. */
  khach_hang_id: number | null;
  sale: string | null;
  so_luong_dat: number;
  don_vi_tinh: string | null;
  /** Số đã giao THẬT (`delivery_trip_lines.qty_giao`), không phải số yêu cầu giao. */
  da_giao: number;
  is_rush: boolean;
  buoc_hien_tai: string | null;
  nhom_cong_doan: string | null;
  may: string | null;
  /** TÊN người đang được giao ở đúng bước đang hiện, theo THỨ TỰ GIAO (cắt từ cuối là an toàn). */
  nguoi: string[];
  /** Cả chuỗi công đoạn của lệnh, sắp theo giờ dự kiến bắt đầu — nguồn của dải chặng trong hàng.
   *  Có thể RỖNG (lệnh chưa phát hành gói / routing rỗng): đừng vẽ đốt giả, hiện gạch "–". */
  chang: LenhSxChang[];
  tien_do_pct: number;
  /** `true` = phần trăm đo bằng THỜI LƯỢNG kế hoạch vì bước chưa khai sản lượng. Phải ra tới mặt
   *  màn: 40% "đo được" và 40% "ước tính" là hai mức tin cậy khác hẳn nhau. */
  tien_do_uoc_tinh: boolean;
  /** Giờ máy đã chạy. ĐỪNG CỘNG qua nhiều lệnh: một lượt in ghép 3 lệnh được đếm đủ cho cả 3. */
  gio_may: number;
  /** `date` (không có giờ) ⇒ format bằng `ngay()`, KHÔNG `ngayGio()`. */
  han_hoan_thanh_sx: string | null;
  /** `date`, cùng luật với `han_hoan_thanh_sx`. */
  han_giao_khach: string | null;
  /** `datetime` ⇒ `ngayGio()`. `null` = máy chủ CỐ Ý im vì có bước thiếu thời lượng. */
  du_kien_xong: string | null;
  trang_thai: LsxTheoDoiTrangThai;
  canh_bao: LsxTheoDoiCanhBao[];
}

export interface LenhSxListOut {
  items: LenhSxItem[];
  /** Tổng SAU cả `tab` — chỉ dùng cho Pager. Con số cạnh tiêu đề là `dem_theo_tab.tat_ca`. */
  total: number;
  page: number;
  page_size: number;
  /** FACET của tập ĐÃ LỌC, KHÔNG bị chính `tab` đang chọn lọc lại: bấm sang tab khác thì bảy con
   *  số đứng yên, chỉ đổi ô tìm / bộ lọc mới làm chúng đổi. Cấm đếm lại từ `items`. */
  dem_theo_tab: Partial<Record<LsxTheoDoiTab, number>>;
}

export interface LenhSxSummaryOut {
  dang_sx: number;
  cong_doan_xong_hom_nay: number;
  du_kien_tre: number;
  /** `null` = CHƯA kiểm lô nào hôm nay, khác hẳn `0` = kiểm rồi và trượt sạch. UI phải hiện "—". */
  ty_le_kcs_dat_hom_nay: number | null;
}

export interface LenhSxMayLoc {
  id: number;
  ma: string | null;
  ten: string | null;
  /** Số LỆNH đang dính máy này trong phạm vi người gọi — ca in ghép phục vụ 2 lệnh thì đếm 2. */
  so_lenh: number;
}

export interface LenhSxBoLocOut {
  may: LenhSxMayLoc[];
}

export interface LenhSxDanhSachParams {
  tab?: LsxTheoDoiTab;
  q?: string;
  page?: number;
  page_size?: number;
  nhom_cong_doan?: string;
  may_id?: number;
  uu_tien?: "gap" | "binh_thuong";
  /** CHỈ gửi khi bật. Không có nấc "chỉ lệnh không trễ" — không ai hỏi câu đó. */
  tre?: boolean;
  tu_ngay?: string;
  den_ngay?: string;
}

// --- Hồ sơ MỘT lệnh (Task 10 dựng API, Task 12 dựng màn) ---------------------
// 13 khối lồng nhau. Bẫy Pydantic ở đây nguy hơn hẳn màn danh sách: thiếu một trường trong MỘT
// khối con thì 12 khối kia vẫn ra bình thường — FE nhận `undefined` ở đúng một ô và không ai
// thấy lỗi. Mirror ĐÚNG `backend/app/schemas/lenh_san_xuat.py`, đừng thêm trường phía này.
// KHÔNG MỘT TRƯỜNG TIỀN NÀO — cùng ràng buộc cứng của cả module.

export interface LenhSxThongTin {
  id: number;
  ma: string;
  ten: string | null;
  loai: string | null;
  order_id: number | null;
  order_no: string | null;
  order_line_id: number | null;
  khach_hang: string | null;
  khach_hang_id: number | null;
  sale: string | null;
  so_luong_dat: number;
  don_vi_tinh: string | null;
  is_rush: boolean;
  /** `date` ⇒ `ngay()`. */
  han_hoan_thanh_sx: string | null;
  /** `date` ⇒ `ngay()`. */
  han_giao_khach: string | null;
  ban_giao_at: string | null;
  ghi_chu: string | null;
  tao_luc: string | null;
}

export interface LenhSxTienDo {
  phan_tram: number;
  /** `true` = đo bằng THỜI LƯỢNG kế hoạch vì bước chưa khai sản lượng. Phải ra tới mặt màn. */
  uoc_tinh: boolean;
  gio_may: number;
  du_kien_xong: string | null;
  trang_thai: LsxTheoDoiTrangThai;
  canh_bao: LsxTheoDoiCanhBao[];
  buoc_hien_tai: string | null;
  buoc_hien_tai_cong_viec_id: number | null;
  nhom_cong_doan: string | null;
  may: string | null;
  nguoi: string[];
  /** Số đã giao của RIÊNG dòng đơn lệnh này — khác `giao_hang.da_giao` (cấp NHÓM). */
  da_giao: number;
}

/** Ảnh chụp thông số kỹ thuật từ phiếu tính giá. Khoá thiếu (lệnh cũ) ⇒ `null` ⇒ UI hiện "—",
 *  KHÔNG đổi sang 0: 0 kẽm và "chưa khai số kẽm" là hai chuyện. */
export interface LenhSxThongSo {
  giay_ten: string | null;
  dinh_luong: number | null;
  kho_nguyen_dai: number | null;
  kho_nguyen_rong: number | null;
  kho_in_dai: number | null;
  kho_in_rong: number | null;
  dai_thanh_pham: number | null;
  rong_thanh_pham: number | null;
  quy_cach_in: string | null;
  so_mau_a: number | null;
  so_mau_b: number | null;
  muc_a: string[];
  muc_b: string[];
  so_trang: number | null;
  trang_moi_tay: number | null;
  so_kem: number | null;
  so_manh_xa: number | null;
  loai_san_pham: string | null;
  ghi_chu_ky_thuat: string | null;
  so_con: number;
  so_to_ke_hoach: number;
  so_to_nguyen: number;
  don_vi_tinh: string | null;
}

export interface LenhSxRoutingNode {
  id: number;
  thu_tu: number;
  /** Đường DÀI NHẤT từ bước gốc tới bước này — KHÔNG phải `thu_tu`. Hai bước cùng `lop` là hai
   *  bước chạy SONG SONG được; vẽ theo `thu_tu` là bịa ra một chuỗi tuần tự không tồn tại. */
  lop: number;
  phu_thuoc: number[];
  ten: string | null;
  nhom: string | null;
  loai_buoc: string | null;
  bat_buoc: boolean;
  nha_cung_cap: string | null;
  cong_viec_id: number | null;
  /** Bước do một ca in GHÉP đảm nhiệm: trạng thái/máy/người là của CẢ CA, không riêng lệnh này. */
  la_buoc_ghep: boolean;
  la_buoc_hien_tai: boolean;
  /** `released` | `running` | `paused` | `completed`; `null` = bước chưa có công việc. */
  trang_thai: string | null;
  may: string | null;
  to: string | null;
  nguoi: string[];
  du_kien_bat_dau: string | null;
  du_kien_ket_thuc: string | null;
  hoan_thanh_luc: string | null;
  so_luong_vao: number;
  so_luong_ra: number;
  don_vi_vao: string | null;
  don_vi_ra: string | null;
  /** Công đoạn nguồn CÓ ĐÒI khuôn/khung — khác hẳn "đã trỏ dao nào". Bật mà `khuon_be_ma` rỗng
   *  chính là thế "cần dao mà chưa chốt", thứ đang chặn ở cửa Sẵn sàng lập kế hoạch. */
  can_khuon: boolean;
  khuon_da_nhan: boolean;
  khuon_be_ma: string | null;
  khuon_be_ten: string | null;
  khuon_be_so_ke: string | null;
  khuon_be_tinh_trang: string | null;
}

export interface LenhSxRouting {
  nodes: LenhSxRoutingNode[];
  /** Cặp `[bước trước, bước sau]` bằng id node. */
  canh: number[][];
}

export interface LenhSxVatTuDong {
  /** `lsx` = vật tư của chính lệnh · `bai_ghep` = giấy của cả tờ in ghép mà lệnh là thành viên.
   *  Cả hai đều là vật tư THẬT của lệnh, nhưng người đi lĩnh phải biết mình lĩnh cho ai. */
  pham_vi: string;
  ma: string | null;
  ten_viec: string | null;
  buoc_id: number | null;
  hang_loai: string | null;
  hang_id: number | null;
  hang_ma: string | null;
  hang_ten: string | null;
  don_vi_goc: string | null;
  ton: number | null;
  nhu_cau: number | null;
  nhu_cau_hien_thi: string | null;
  da_cap: number | null;
  dang_linh: number | null;
  con_phai_co: number | null;
  thieu: number | null;
  /** Cùng thang màu với bảng cân đối Kế hoạch vật tư (`CanDoiMau`). */
  trang_thai: string | null;
  ngay_can: string | null;
}

export interface LenhSxVatTuMuc {
  /** Mọi dòng của bước đang làm đều `xanh`/`xam`. Không dòng nào ⇒ `true` (không có gì để thiếu). */
  du: boolean;
  dong: LenhSxVatTuDong[];
}

/** `bo_qua` GỠ 23/09/2026 cùng lúc với `CanDoiOut.bo_qua` — ba mục dưới là toàn bộ khối vật tư. */
export interface LenhSxVatTu {
  hien_tai: LenhSxVatTuMuc;
  canh_bao_sau: LenhSxVatTuDong[];
  da_cap: LenhSxVatTuDong[];
}

export interface LenhSxNhanLucBuoc {
  cong_viec_id: number;
  buoc_id: number | null;
  ten_viec: string | null;
  to: string | null;
  may: string | null;
  nguoi: string[];
}

export interface LenhSxNhanLucSuKien {
  /** `giao_nguoi` · `rut_nguoi` · `doi_may`. */
  loai: string;
  luc: string;
  cong_viec_id: number | null;
  ten_viec: string | null;
  nguoi: string | null;
  /** Chỉ có ở `doi_may` — và đó là vết DUY NHẤT của lần đổi máy (`cong_viec.may_id` chỉ nhớ máy
   *  cuối cùng). */
  may_cu: string | null;
  may_moi: string | null;
  ly_do: string | null;
}

export interface LenhSxNhanLuc {
  hien_tai: LenhSxNhanLucBuoc[];
  /** Giữ CẢ người đã bị RÚT — hồ sơ là chỗ trả lời "ai từng làm việc này", bảng thì không. */
  lich_su: LenhSxNhanLucSuKien[];
}

export interface LenhSxSanLuongBatch {
  id: number;
  cong_viec_id: number;
  ten_viec: string | null;
  la_buoc_ghep: boolean;
  bat_dau: string | null;
  ket_thuc: string | null;
  tong: number;
  tot: number;
  hong: number;
  don_vi: string | null;
  mo_ta_loi: string | null;
}

export interface LenhSxSanLuong {
  tong: number;
  tot: number;
  hong: number;
  batch: LenhSxSanLuongBatch[];
}

export interface LenhSxKcsBatch {
  id: number;
  cong_viec_id: number;
  ten_viec: string | null;
  la_buoc_ghep: boolean;
  la_kcs_cuoi: boolean;
  ket_thuc: string | null;
  so_luong_nhan: number;
  so_luong_dat: number;
  so_luong_khong_dat: number;
  don_vi: string | null;
  /** `dat` | `dat_mot_phan` | `khong_dat`. */
  ket_luan: string | null;
  ghi_chu: string | null;
}

export interface LenhSxKcs {
  tong_nhan: number;
  tong_dat: number;
  tong_khong_dat: number;
  /** `null` = CHƯA kiểm cái nào, khác hẳn `0` = kiểm rồi và trượt sạch. */
  ty_le_dat: number | null;
  batch: LenhSxKcsBatch[];
}

export interface LenhSxPhieuSua {
  id: number;
  ma: string;
  /** `cho_sua` | `dang_sua` | `cho_vat_tu` | `da_sua_xong`. */
  trang_thai: string | null;
  nguyen_nhan_phuong_an: string | null;
  hoan_thanh_at: string | null;
}

export interface LenhSxSuCo {
  id: number;
  ma: string;
  cong_viec_id: number | null;
  ten_viec: string | null;
  may: string | null;
  bo_phan_hong: string | null;
  mo_ta: string | null;
  /** `nhe` | `trung_binh` | `nghiem_trong`. */
  muc_do: string | null;
  may_dung: boolean;
  nguoi_bao: string | null;
  thoi_diem: string | null;
  /** `cho_tiep_nhan` | `da_tao_phieu` | `tu_choi`. */
  trang_thai: string | null;
  ly_do_tu_choi: string | null;
  /** Phiếu sửa sinh ra từ yêu cầu này. `null` khi chưa ai tiếp nhận — KHÔNG phải lỗi. */
  phieu: LenhSxPhieuSua | null;
}

/** Một dòng yêu cầu NHẬP kho thành phẩm (kho thật). `id` = id dòng; số theo đơn vị của món. */
export interface LenhSxKhoYeuCau {
  id: number;
  request_id: number | null;
  /** Mã yêu cầu nhập (DNN…) — bấm mở ở Yêu cầu nhập xuất. */
  ma: string | null;
  hang_id: number | null;
  so_luong_yeu_cau: number;
  /** Kho đã nhận (Σ phiếu nhập đã ghi sổ). */
  so_luong_xac_nhan: number;
  con_lai: number;
  don_vi: string | null;
  /** Trạng thái yêu cầu kho: `approved` · `preparing` · `partial` · `done` · `cancelled` · `rejected`. */
  trang_thai: string | null;
  tao_luc: string | null;
  /** Lúc phiếu nhập ghi sổ muộn nhất. */
  xac_nhan_luc: string | null;
}

export interface LenhSxKho {
  /** SỐ, không phải cờ: `1` thì số của nhóm CHÍNH LÀ số của lệnh (cộng thoải mái); `3` thì cộng
   *  qua ba lệnh của một trang là nhân số thật lên gấp ba. `0` = lệnh chưa vào nhóm nào. */
  so_lenh_trong_nhom: number;
  yeu_cau: LenhSxKhoYeuCau[];
}

/** MỘT dòng điền sẵn của form giao hàng = một cặp (mặt hàng × kho), vì phiếu xuất đi từ MỘT kho. */
export interface LenhSxGiaoHangHang {
  hang_id: number;
  ma: string | null;
  ten: string | null;
  quy_cach: string | null;
  don_vi: string | null;
  kho_id: number | null;
  kho_ten: string | null;
  /** Tồn THẬT của cặp này, CHƯA trừ đã giao. Để đối chiếu với kho. */
  so_luong: number;
  /** TRẦN được phép ghi vào phiếu (đã trừ đã giao). `null` khi `khong_tinh_duoc`. */
  so_toi_da: number | null;
  /** `true` ⇒ không dựng được ánh xạ mặt hàng ⇄ dòng đơn ⇒ chưa biết trần. Ô TRỐNG CÓ LÝ DO,
   *  KHÔNG phải 0: hàng vẫn còn trong kho, chỉ là hệ chưa biết chắc đã giao bao nhiêu của riêng
   *  món này. UI phải cảnh báo, đừng tự điền `so_luong` vào chỗ trần. */
  khong_tinh_duoc: boolean;
}

export interface LenhSxGiaoHang {
  nhom_id: number | null;
  order_id: number | null;
  order_line_ids: number[];
  so_lenh_trong_nhom: number;
  hang: LenhSxGiaoHangHang[];
  /** Số CẤP NHÓM (mọi mặt hàng, mọi dòng đơn) — để đối chiếu, KHÔNG phải để lập phiếu. */
  da_nhap_kho: number;
  da_giao: number;
  co_the_giao: boolean;
  /** Nhóm có nhiều đơn vị khác nhau ⇒ con số tổng KHÔNG có nghĩa; UI phải im nó đi. */
  don_vi_lech: boolean;
}

export interface LenhSxTimeline {
  loai: string;
  luc: string;
  /** Có thể trống: vài đường ghi không lưu ai bấm (batch KCS). Bịa tên vào đó tệ hơn để trống. */
  nguoi: string | null;
  noi_dung: string;
  cong_viec_id: number | null;
  ten_viec: string | null;
}

export interface LenhSxHoSoOut {
  thong_tin: LenhSxThongTin;
  tien_do: LenhSxTienDo;
  thong_so: LenhSxThongSo;
  routing: LenhSxRouting;
  vat_tu: LenhSxVatTu;
  nhan_luc: LenhSxNhanLuc;
  san_luong: LenhSxSanLuong;
  su_co: LenhSxSuCo[];
  kcs: LenhSxKcs;
  kho: LenhSxKho;
  giao_hang: LenhSxGiaoHang;
  /** Sắp TĂNG DẦN theo mốc máy chủ. KHÔNG có sự kiện giao hàng (nguồn có, cố ý chưa nối —
   *  `ho_so._timeline`); số đã giao nằm ở khối `giao_hang`. */
  timeline: LenhSxTimeline[];
  /** Đọc từ `san_xuat_goi_phat_hanh.version_hien_tai`. `null` khi lệnh chưa có công việc nào
   *  (chưa từng được phát hành) — KHÔNG mặc định 1. */
  phien_ban: number | null;
}

// --- Theo dõi sản xuất (module `theo_doi_san_xuat`, Task 15-17) --------------
// Bàn CHỈ ĐỌC cho điều độ viên: 4 góc nhìn (Kanban · Theo máy · Theo ca · Gantt) trên cùng MỘT
// thanh lọc dùng chung (8 tham số, khai một chỗ ở `_thanh_loc` phía máy chủ). Mirror ĐÚNG
// `backend/app/schemas/theo_doi_san_xuat.py` — đừng thêm trường phía này (đọc, không tính lại).
//
// KHÔNG MỘT SỐ TIỀN NÀO, cùng luật với cả gói `lenh_sx`.

/** MỘT ô chọn trong thanh lọc. `ten` là mặt ĐỌC (tiếng Việt có dấu) — `id` chỉ để SO KHỚP, gán
 *  thẳng vào tham số lọc cùng tên. `id` LUÔN là chuỗi (kể cả facet có cột số ở DB, xem docstring
 *  `BoLocMucOut` phía máy chủ) — nơi gọi tự ép `Number(...)` khi tham số đích là số. */
export interface TdsxBoLocMuc {
  id: string;
  ten: string;
}

/** Ô chọn MÁY — vừa là nguồn ô lọc vừa là KHUNG LANE của `/theo-may` (một mục có thể lọc ra lane
 *  rỗng, và rỗng là câu trả lời đúng). `co_viec` là GỢI Ý hiển thị, KHÔNG phải bộ lọc. */
export interface TdsxBoLocMayMuc extends TdsxBoLocMuc {
  ngung_dung: boolean;
  co_viec: boolean;
}

export interface TdsxBoLocOut {
  may: TdsxBoLocMayMuc[];
  cong_nhan: TdsxBoLocMuc[];
  cong_doan: TdsxBoLocMuc[];
  nhom_cong_doan: TdsxBoLocMuc[];
  /** Nguồn ô chọn Ca của tab "Theo ca" (Task 18b) — `/kanban` và `/theo-may` KHÔNG nhận `ca_id`,
   *  màn này (17b) không dựng ô Ca từ danh sách này. */
  ca: TdsxBoLocMuc[];
  trang_thai_viec: TdsxBoLocMuc[];
  uu_tien: TdsxBoLocMuc[];
  khach_hang: TdsxBoLocMuc[];
}

/** Tám tham số lọc DÙNG CHUNG cho cả bốn góc nhìn (`router._thanh_loc`). `cong_doan_id` có ở máy
 *  chủ nhưng bản thiết kế đã duyệt (task-17-thiet-ke.md §3) không dựng ô riêng cho nó — "Nhóm CĐ"
 *  đã đủ cho màn này — nên field đó CỐ Ý không xuất hiện ở đây (18b có cần thì thêm). */
export interface TdsxThanhLocParams {
  q?: string;
  khach_hang_id?: number;
  may_id?: number;
  nhom_cong_doan?: string;
  cong_nhan_id?: number;
  trang_thai_viec?: string;
  uu_tien?: "gap" | "binh_thuong";
}

/** MỘT cột của board Kanban. `key` là chuỗi để khớp thẳng `TdsxKanbanCard.cot` — so sánh KHÔNG
 *  được ép kiểu số ở một bên. */
export interface TdsxKanbanCot {
  key: string;
  ten: string;
}

export interface TdsxKanbanMeta {
  cot: TdsxKanbanCot[];
}

/** NHÃN đi theo một bước: loại bước (+ nơi gia công) và khuôn/khung của nó.
 *  MỘT kiểu dùng chung cho Kanban · Theo máy · Theo ca — mỗi màn tự suy lấy là nhãn đứt giữa
 *  đường, đúng lỗi mà đợt 04/09/2026 vá. Vẽ bằng `<ChipLoaiBuoc>` + `<ChipKhuon>`. */
export interface TdsxNhanBuoc {
  loai_buoc: string | null;
  nha_cung_cap: string | null;
  khuon_ma: string | null;
  khuon_so_ke: string | null;
  khuon_tinh_trang: string | null;
  khuon_da_nhan: boolean;
}

/** MỘT công việc đang `running`/`paused` của lệnh — hiện thành chip TRONG card (routing rẽ nhánh
 *  không tách thẻ). `may` KHÔNG BAO GIỜ `null` (máy chưa gán/đã xoá đều có nhãn riêng). */
export interface TdsxKanbanChip {
  cong_viec_id: number;
  ten: string | null;
  trang_thai: string;
  may: string;
  nguoi: string[];
  nhan: TdsxNhanBuoc | null;
}

/** MỘT lệnh = MỘT card, bất kể routing rẽ bao nhiêu nhánh. `cot` là bước sớm nhất còn dang dở. */
export interface TdsxKanbanCard {
  lsx_id: number;
  ma: string;
  ten: string | null;
  khach_hang: string | null;
  so_luong_dat: number;
  is_rush: boolean;
  /** `date` ⇒ format bằng `ngay()`, KHÔNG `ngayGio()`. */
  han_hoan_thanh_sx: string | null;
  cot: string;
  buoc_hien_tai: string | null;
  chip_dang_chay: TdsxKanbanChip[];
}

export interface TdsxKanbanOut {
  cards: TdsxKanbanCard[];
}

/** MỘT lệnh mà một block Theo máy đang gánh — cặp `(lsx_id, ma)`: `ma` là mặt ĐỌC, `lsx_id` là
 *  KHOÁ mở hồ sơ. Một block có ≥2 phần tử (ca ghép) ⇒ bày danh sách cho chọn, CẤM lấy phần tử đầu. */
export interface TdsxLsxThamChieu {
  lsx_id: number;
  ma: string;
}

/** MỘT công việc trong lane của MỘT máy — có thể ghép phục vụ nhiều lệnh (`lsx.length >= 2`).
 *  Mốc `du_kien_*` là KẾ HOẠCH của CẢ công việc, không phải khoảng máy này thật sự bận. */
export interface TdsxMayLaneBlock {
  cong_viec_id: number;
  ten: string | null;
  trang_thai: string;
  lsx: TdsxLsxThamChieu[];
  du_kien_bat_dau: string | null;
  du_kien_ket_thuc: string | null;
  nguoi: string[];
  nhan: TdsxNhanBuoc | null;
}

/** MỘT lane. `may_id: null` là lane "Chưa xếp máy" — LUÔN có mặt kể cả rỗng. `blocks: []` là một
 *  CÂU TRẢ LỜI ("máy này đang trống"), không phải thiếu dữ liệu — vẽ lane rỗng tử tế, đừng ẩn. */
export interface TdsxMayLane {
  may_id: number | null;
  ten: string;
  ngung_dung: boolean;
  blocks: TdsxMayLaneBlock[];
}

export interface TdsxTheoMayOut {
  lanes: TdsxMayLane[];
}

// --- Theo ca (Task 18b) -----------------------------------------------------------------------
/** MỘT công việc trong một ca. `lsx` cùng kiểu và cùng ý nghĩa với `TdsxMayLaneBlock.lsx`: một
 *  công việc GHÉP phục vụ nhiều lệnh nên đây là DANH SÁCH — 1 phần tử thì bấm mở thẳng hồ sơ, từ 2
 *  trở lên thì bày popover cho người dùng chọn (C123), CẤM đoán lấy phần tử đầu. */
export interface TdsxCaViec {
  cong_viec_id: number;
  ten: string | null;
  trang_thai: string;
  may_id: number | null;
  may: string;
  lsx: TdsxLsxThamChieu[];
  du_kien_bat_dau: string | null;
  /** Mốc bắt đầu phiên chạy ĐẦU TIÊN (giờ xưởng); `null` = chưa chạy. Việc đã chạy được máy chủ
   *  xếp vào ca theo giờ chạy thật, chưa chạy thì theo kế hoạch (16/09/2026). */
  bat_dau_thuc_te: string | null;
  /** `"som"`/`"tre"`: ngày đang xem nằm trước/sau ngày kế hoạch, hoặc (`"tre"`) quá giờ bắt đầu dự
   *  kiến mà chưa chạy. */
  lech_lich: "som" | "tre" | null;
  nguoi: string[];
  nhan: TdsxNhanBuoc | null;
}

/** MỘT ca của ngày đang xem. `id: null` là rổ "Ngoài ca" (LUÔN đứng CUỐI khi không lọc `ca_id`).
 *  `bat_dau_phut`/`ket_thuc_phut`: phút trong ngày (0-1439), `null` cho rổ "Ngoài ca". `qua_nua_dem`
 *  là CỜ nhận diện ca đêm — CẤM dò theo `ten` (Ruling C116: xưởng khác gọi ca đêm là "Ca tối"/
 *  "Ca C"). */
export interface TdsxCa {
  id: number | null;
  ten: string;
  bat_dau_phut: number | null;
  ket_thuc_phut: number | null;
  qua_nua_dem: boolean;
  viec: TdsxCaViec[];
}

/** Bốn hành vi của `ca_id` (Ruling C134, task-18b-brief.md) ra BỐN hình dạng KHÁC NHAU của `ca`:
 *  vắng mặt ⇒ mọi ca thật + rổ "Ngoài ca"; id một ca thật ⇒ mảng 1 phần tử đúng ca đó (có thể
 *  `viec: []`); `"ngoai_ca"` ⇒ mảng 1 phần tử đúng rổ "Ngoài ca" (có thể `viec: []`); id lạ/ca đã
 *  xoá ⇒ mảng RỖNG `ca: []` — ba ca đầu KHÁC ca cuối, FE phải nói hai câu khác nhau. */
export interface TdsxTheoCaOut {
  ca: TdsxCa[];
}

/** Tám tham số lọc chung + hai tham số riêng của `/theo-ca`. `ca_id` là CHUỖI ở tầng FE (số dạng
 *  chuỗi để chọn một ca thật, hoặc sentinel `"ngoai_ca"`) — server tự ép kiểu Union tương ứng. */
export interface TdsxTheoCaParams extends TdsxThanhLocParams {
  ngay?: string;
  ca_id?: string;
}

// --- Gantt tổng thể (Task 18b) -----------------------------------------------------------------
/** MỘT dòng = MỘT LỆNH (Ruling C118), KHÔNG phải một công việc. `du_kien_bat_dau`/`du_kien_ket_thuc`
 *  CÙNG `null` ⇒ "chưa đủ dữ liệu" — TUYỆT ĐỐI không tự vẽ một thanh bịa (docstring `GanttRowOut`
 *  phía máy chủ). */
export interface TdsxGanttRow {
  lsx_id: number;
  ma: string;
  ten: string | null;
  khach_hang: string | null;
  /** `date` ⇒ format bằng `ngay()`, KHÔNG `ngayGio()`. */
  han_hoan_thanh_sx: string | null;
  du_kien_bat_dau: string | null;
  du_kien_ket_thuc: string | null;
}

export interface TdsxGanttOut {
  rows: TdsxGanttRow[];
  total: number;
  page: number;
  page_size: number;
}

/** Tám tham số lọc chung + phân trang. KHÔNG có `ca_id` — một dòng Gantt gộp nhiều ca, lọc ở thang
 *  đó vô nghĩa (Ruling C134). */
export interface TdsxGanttParams extends TdsxThanhLocParams {
  page?: number;
  page_size?: number;
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
  /** Thành phẩm KCS mà lô CHƯA CÓ giá gốc ⇒ 0 ở hai số trên là "chưa biết" — ghi "Chưa có giá gốc".
   *  Luôn false khi thiếu quyền xem giá. */
  chua_gia_goc?: boolean;
  /** Nguồn hàng (lệnh / đơn / khách, đọc ở lô gốc) — dòng xuất gộp lô nhiều đơn thì nối ", ". */
  lsx_ma?: string | null;
  order_ma?: string | null;
  khach_hang?: string | null;
  /** Giá bán của đơn (đ/đvt dòng), chỉ tham khảo. null khi thiếu quyền xem giá. */
  don_gia_ban?: number | null;
  /** Hạn sử dụng của lô dòng này (ISO yyyy-mm-dd) — BE trả để hiện trên phiếu (điều chuyển). */
  hsd?: string | null;
  /** Vị trí cất lô (kệ/ô) — phiếu điều chuyển hiện/khai per-lô. null = chưa khai. */
  vi_tri?: string | null;
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
  /** ĐIỀU CHUYỂN: true cho cả phiếu xuất nguồn lẫn phiếu nhập đích — FE/báo cáo gắn nhãn. */
  dieu_chuyen: boolean;
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
  /** Phiếu NHẬP: hạn sử dụng của lô (ISO yyyy-mm-dd, tuỳ chọn). Tách hạn = nhiều dòng; phần dư
   *  không hạn để null. */
  hsd?: string | null;
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

/** 1 mặt hàng cần điều chuyển. `so_luong` theo ĐƠN VỊ GỐC của mặt hàng. */
export interface DieuChuyenItemInput {
  hang_loai: HangLoai;
  hang_id: number;
  so_luong: number;
  /** Vị trí cất ở KHO ĐÍCH (kệ/ô) — tuỳ chọn, khai lúc ấn; áp cho mọi lô của mặt hàng. */
  vi_tri?: string | null;
}

/** Ấn ĐIỀU CHUYỂN 1 hay NHIỀU mặt hàng kho nguồn → kho đích (gộp vào MỘT yêu cầu điều chuyển). */
export interface DieuChuyenInput {
  kho_nguon_id: number;
  kho_den_id: number;
  items: DieuChuyenItemInput[];
  ghi_chu?: string | null;
}

/** Kết quả ấn điều chuyển: MỘT yêu cầu điều chuyển (NHẬP đích, nhiều dòng) + phiếu xuất nguồn đã ghi sổ. */
export interface DieuChuyenResult {
  yeu_cau_id: number;
  yeu_cau_ma: string;
  phieu_xuat_id: number;
  phieu_xuat_ma: string;
  kho_nguon_id: number;
  kho_den_id: number;
  so_dong: number;
  /** Tổng giá vốn điều chuyển — null nếu thiếu `can_view_cost`. */
  gia_von: number | null;
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
  /** ĐƠN VỊ GỐC — `dvt` = MÃ (to/cai…) cho logic/quy đổi; `dvt_ten` = TÊN có dấu (tờ/cái) để hiển thị. */
  dvt: string | null;
  dvt_ten: string | null;
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
  /** ĐƠN VỊ của `sl_de_nghi` (đơn vị người xin) — có thể khác `dvt` gốc của lô; ghi rõ ở cột SL yêu cầu. */
  dvt_yeu_cau?: string | null;
  /** Lô sinh từ phiếu ĐIỀU CHUYỂN (nhận về) — lịch sử mặt hàng xếp vào tab "Chuyển kho" riêng. */
  dieu_chuyen?: boolean;
  /** NGUỒN LÔ đọc ở lô gốc (sống qua điều chuyển). `tu_kcs` = thành phẩm nhập từ KCS — giá gốc 0 cho
   *  tới khi kế toán kho gõ. `don_gia_ban` chỉ có khi `can_view_cost`. */
  lo_goc_id?: number | null;
  lsx_ma?: string | null;
  order_ma?: string | null;
  khach_hang?: string | null;
  don_gia_ban?: number | null;
  tu_kcs?: boolean;
}

export interface StockAllocationLine {
  lot_id: number;
  ma_lo: string;
  ngay_nhap: string;
  hsd: string | null;
  sl_con_lai: number;
  so_luong: number;
  don_gia_nhap: number | null;
  /** Nguồn lô thành phẩm (đơn / khách) — trống với giấy, vật tư. */
  order_ma?: string | null;
  khach_hang?: string | null;
  /** Xuất cho Giao hàng mà lô thuộc đơn khác cùng khách: "Lô này sản xuất cho đơn DH…". */
  canh_bao?: string | null;
}

/** Kết quả sửa giá gốc: hệ quy về lô GỐC, `so_lo` = số lô trong họ (gốc + lô sinh qua điều chuyển). */
export interface GiaGocKetQua {
  lot_id: number;
  ma_lo: string;
  don_gia_cu: number;
  don_gia: number;
  don_gia_nhap: number;
  so_lo: number;
}

/** Một lô GỐC thành phẩm nhập từ KCS — báo cáo "Thành phẩm chưa có giá gốc". */
export interface ThanhPhamChuaGiaGocRow {
  lot_id: number;
  ma_lo: string;
  ngay_nhap: string;
  kho_id: number;
  kho_ten: string | null;
  hang_id: number;
  ma_hang: string | null;
  ten_hang: string | null;
  dvt: string | null;
  dvt_ten: string | null;
  so_luong_nhap: number;
  /** Giá gốc hiện tại (0 = chưa có). */
  don_gia: number;
  /** Giá bán lấy từ đơn hàng (null = không lần ra đơn). */
  don_gia_ban: number | null;
  lsx_ma: string | null;
  order_ma: string | null;
  khach_hang: string | null;
  /** Còn lại cộng mọi lô trong họ (mọi kho). */
  sl_con_lai: number;
  don_vi_goc_ten: string | null;
  so_lo: number;
}

export interface ThanhPhamChuaGiaGocPage {
  items: ThanhPhamChuaGiaGocRow[];
  total: number;
  page: number;
  size: number;
  /** Lựa chọn cho ô lọc nâng cao — chỉ kho/khách có lô, bất kể bộ lọc đang áp. */
  cac_kho: { id: number; ten: string | null }[];
  cac_khach: { id: number; ten: string | null }[];
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

/** 1 lần ĐIỀU CHỈNH phiếu xuất — cho "Lịch sử điều chỉnh" trong drawer phiếu. */
export interface DieuChinhLichSu {
  thoi_diem: string;
  nguoi_ten: string | null;
  bo_phan_ten: string | null;
  chi_tiet: string | null;
  ly_do: string | null;
}

/** 1 VỊ TRÍ cất (kệ/ô) đã khai của một kho — danh sách để khai lô chọn dropdown. */
export interface KhoViTriRow {
  id: number;
  kho_id: number;
  ma: string;
  ghi_chu: string | null;
  active: boolean;
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
  /** ĐƠN VỊ của `sl_de_nghi` (đơn vị người xin) — có thể khác đơn vị gốc; ghi rõ ở cột SL yêu cầu. */
  dvt_yeu_cau?: string | null;
  so_luong: number;
  /** Giá vốn đích danh của lô đã xuất — chỉ có khi `can_view_cost`. */
  don_gia: number | null;
  /** Dòng xuất thuộc phiếu ĐIỀU CHUYỂN (chuyển đi) — lịch sử mặt hàng xếp vào tab "Chuyển kho". */
  dieu_chuyen?: boolean;
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

/** Gọi một endpoint trả nhị phân, tự làm mới token khi 401. Tách khỏi `blobUrl` để chỗ cần ĐỌC
 *  THÊM header của response (vd. `blobUrlComTen` đọc `Content-Disposition`) không phải chép lại
 *  logic retry 401 lần thứ hai. */
async function fetchNhiPhan(path: string, token: string): Promise<Response> {
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
  return resp;
}

/** Tải một file nhị phân về dạng blob URL, tự làm mới token khi 401. */
export async function blobUrl(path: string, token: string): Promise<string> {
  const resp = await fetchNhiPhan(path, token);
  return URL.createObjectURL(await resp.blob());
}

/** Tách tên file khỏi header `Content-Disposition` (`inline; filename="..."` hoặc `attachment; …`).
 *  Không có header, hoặc dạng lạ không khớp, trả `null` — nơi gọi tự lùi về tên dự phòng. Không cần
 *  lo dạng `filename*=` (UTF-8 encoded, RFC 5987): phía backend phát tên đã sanitize thuần ASCII
 *  (`_ten_file` ở `backend/app/services/lenh_sx/phieu_cong_nghe.py`), không có ký tự cần encode. */
export function tenFileTuHeader(header: string | null): string | null {
  if (!header) return null;
  const m = /filename="?([^";]+)"?/i.exec(header);
  return m ? m[1].trim() : null;
}

/** Như `blobUrl`, nhưng bọc `Blob` vào `File` (mang `.name`) trước khi tạo object URL. Tên lấy từ
 *  `Content-Disposition` của response; header thiếu/lạ thì lùi về `tenDuPhong`.
 *
 *  ⚠️ N28 (đặt tên file đúng lúc "Lưu") — ruling C109 sau lượt rà vòng 1, ĐỌC KỸ TRƯỚC KHI DÙNG
 *  Ở CHỖ MỚI: bọc `File` chỉ đổi được tên "Lưu" khi đối tượng blob được TIÊU THỤ bằng thẻ
 *  `<a download={ten}>` — đó là nơi `.name`/tham số `download` thật sự quyết định tên gợi ý.
 *  `phieuCongNghePdf()` (bên dưới) KHÔNG dùng `<a download>` — nó `window.open(url, "_blank")` mở
 *  thẳng blob URL trong trình xem PDF built-in của Chromium, và trình xem đó dựng tên "Lưu" từ
 *  CHÍNH đoạn UUID trong `blob:<origin>/<uuid>`, không đọc `File.name` — nên với đường
 *  `window.open`, hàm này KHÔNG đóng được N28 (vẫn ra tên uuid như trước khi sửa). Trước đây
 *  docstring ở đây dẫn `frontend/src/lib/anhNen.ts` làm "tiền lệ" — SAI: file đó bọc `File` để ĐI
 *  UPLOAD (tên đi vào `FormData`, một cơ chế khác hẳn). Đã gỡ câu dẫn sai đó.
 *
 *  Vẫn giữ hàm này (không revert về `blobUrl` trần) vì: (a) là chỗ SẴN SÀNG cho đường tải PDF/ảnh
 *  khác trong repo TIÊU THỤ bằng `<a download>` sau này (nếu có) — hiện tại `blobUrlComTen` có
 *  ĐÚNG MỘT người gọi (`phieuCongNghePdf` bên dưới), và mọi `<a download>` thật đang có trong repo
 *  đã tự gán `a.download = "<tên>"` nên `File.name` không có tác dụng gì thêm ở đó; (b) tự nó
 *  không làm hỏng gì so với `blobUrl` — cùng lắm là bọc dư một lớp `File` vô hại khi trình duyệt
 *  bỏ qua `.name`. */
export async function blobUrlComTen(
  path: string,
  token: string,
  tenDuPhong: string,
): Promise<string> {
  const resp = await fetchNhiPhan(path, token);
  const ten = tenFileTuHeader(resp.headers.get("Content-Disposition")) ?? tenDuPhong;
  const blob = await resp.blob();
  return URL.createObjectURL(new File([blob], ten, { type: blob.type }));
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

  /** Current user's readable modules + full CRUD matrix (spec-09 action gating). `kcs` /
   *  `truong_kcs` = thành viên / người đứng đầu một phòng ban "Tổ KCS" (mg 0306) — không phải ô
   *  quyền của vai. */
  myAccess(
    token: string,
  ): Promise<{ modules: string[]; permissions: ModuleCapability[]; kcs?: boolean; truong_kcs?: boolean }> {
    return authed<{ modules: string[]; permissions: ModuleCapability[]; kcs?: boolean; truong_kcs?: boolean }>(
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
      /** Cờ bộ phận Giao hàng. Cùng luật `undefined` = KHÔNG gửi ⇒ backend giữ nguyên. */
      laGiaoHang?: boolean,
      /** Ba ô khoán km. Cùng luật `undefined` = KHÔNG gửi ⇒ giữ nguyên: luồng chỉ sửa tên phòng
       *  mà gửi kèm 0 là âm thầm xoá đơn giá, tháng sau tài xế nhận 0 đồng km. */
      khoanKm?: { don_gia_km?: number; pct_tai_xe?: number; pct_phu_xe?: number },
      /** Cờ tổ KCS đích danh. Cùng luật `undefined` = KHÔNG gửi ⇒ backend giữ nguyên. */
      isKcs?: boolean,
      /** Cờ Tổ in (mg 0304). Cùng luật `undefined` = KHÔNG gửi ⇒ backend giữ nguyên. */
      laToIn?: boolean,
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
          ...(laGiaoHang === undefined ? {} : { la_giao_hang: laGiaoHang }),
          ...(khoanKm ?? {}),
          ...(isKcs === undefined ? {} : { is_kcs: isKcs }),
          ...(laToIn === undefined ? {} : { la_to_in: laToIn }),
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
    /** Một tài khoản (tab Tài khoản của hồ sơ) — khỏi kéo cả danh sách về rồi lọc. */
    user(token: string, userId: number): Promise<UserRow> {
      return authed<UserRow>(`/api/users/${userId}`, token);
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
    userActivity(token: string, userId: number, limit?: number): Promise<AuditRow[]> {
      const suffix = limit ? `?limit=${limit}` : "";
      return authed<AuditRow[]>(`/api/users/${userId}/activity${suffix}`, token);
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
    /** Nhân bản vai trò: vai MỚI với ma trận quyền chép y nguyên vai gốc.
     *  Bỏ `name` = máy chủ tự đặt "«tên gốc» (bản sao)"; bỏ `departmentId` = cùng phòng vai gốc.
     *  Gác bằng `phong_ban:create` + `phong_ban:manage_permissions` (nó bê cả bộ quyền). */
    duplicateRole(
      token: string,
      roleId: number,
      opts?: { name?: string; departmentId?: number },
    ): Promise<Role> {
      return authed<Role>(`/api/roles/${roleId}/duplicate`, token, {
        method: "POST",
        body: JSON.stringify({
          name: opts?.name ?? null,
          department_id: opts?.departmentId ?? null,
        }),
      });
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

  // --- Nhóm dùng chung (khối Kinh doanh) -------------------------------------
  // Gác bằng `phong_ban:manage_permissions` — gộp nhóm là cho người này thấy dữ liệu của người
  // kia, cùng loại với cấp quyền.
  nhomDungChung: {
    list(token: string): Promise<NhomDungChung[]> {
      return authed<NhomDungChung[]>("/api/nhom-dung-chung", token);
    },
    create(token: string, ten: string, userIds: number[]): Promise<NhomDungChung> {
      return authed<NhomDungChung>("/api/nhom-dung-chung", token, {
        method: "POST",
        body: JSON.stringify({ ten, user_ids: userIds }),
      });
    },
    /** `userIds` là THAY TOÀN BỘ danh sách thành viên; bỏ qua = chỉ đổi tên. */
    update(
      token: string,
      id: number,
      data: { ten?: string; userIds?: number[] },
    ): Promise<NhomDungChung> {
      return authed<NhomDungChung>(`/api/nhom-dung-chung/${id}`, token, {
        method: "PATCH",
        body: JSON.stringify({
          ...(data.ten === undefined ? {} : { ten: data.ten }),
          ...(data.userIds === undefined ? {} : { user_ids: data.userIds }),
        }),
      });
    },
    remove(token: string, id: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/nhom-dung-chung/${id}`, token, {
        method: "DELETE",
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
        fetch(`${BASE_URL}/api/customers/xuat-excel`, {
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
    /** File mẫu .xlsx (blob URL) — RỖNG, chỉ dòng tiêu đề.
     *
     *  Mẫu do CHÍNH hệ xuất ra nên cột luôn khớp; đổi cấu hình thì tải lại mẫu là có cột mới.
     *  Sáu cột chính sách tài chính chỉ có mặt với người có quyền `set_credit_terms`. */
    async mauExcelBlobUrl(token: string): Promise<string> {
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/customers/mau-excel`, {
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
    /** Nhập .xlsx — mỗi dòng một khách MỚI, CẢ FILE là một giao dịch.
     *
     *  `mode="preview"` chạy y hệt `commit` rồi rollback, nên con số xem trước là con số THẬT —
     *  không phải một bản kiểm sơ bộ dễ dãi hơn, thứ khiến người dùng bấm Xác nhận rồi mới ăn lỗi. */
    importExcel(token: string, file: File, mode: "preview" | "commit"): Promise<NhapExcelOut> {
      const form = new FormData();
      form.append("file", file);
      return authed<NhapExcelOut>(`/api/customers/import-excel?mode=${mode}`, token, {
        method: "POST",
        body: form,
      });
    },
  },

  // --- Nhãn công đoạn (bước LSX / Bài ghép) — LOGIC y hệt nhãn khách hàng ở trên,
  // chỉ đổi "khách" → "một bước" (cặp buoc_loai + buoc_id). Kho nhãn dùng CHUNG hai loại bước.
  congDoanTag: {
    /** Nhãn đã gán cho một bước. `buocLoai` ∈ {"lsx","bai_ghep"}. */
    list(token: string, buocLoai: string, buocId: number): Promise<{ items: CongDoanTagRow[] }> {
      return authed<{ items: CongDoanTagRow[] }>(
        `/api/cong-doan-tags/${buocLoai}/${buocId}`,
        token,
      );
    },
    add(token: string, buocLoai: string, buocId: number, label: string): Promise<CongDoanTagRow> {
      return authed<CongDoanTagRow>(`/api/cong-doan-tags/${buocLoai}/${buocId}`, token, {
        method: "POST",
        body: JSON.stringify({ label }),
      });
    },
    remove(token: string, buocLoai: string, buocId: number, tagId: number): Promise<void> {
      return authed<void>(`/api/cong-doan-tags/${buocLoai}/${buocId}/${tagId}`, token, {
        method: "DELETE",
      });
    },
    // --- kho nhãn dùng chung (giống `customers.tagKho` — nhãn CÓ THỂ gán) ---
    kho(token: string): Promise<{ items: KhoNhanBuocRow[] }> {
      return authed<{ items: KhoNhanBuocRow[] }>("/api/cong-doan-tags/kho", token);
    },
    themNhanKho(token: string, label: string): Promise<KhoNhanBuocRow> {
      return authed<KhoNhanBuocRow>("/api/cong-doan-tags/kho", token, {
        method: "POST",
        body: JSON.stringify({ label }),
      });
    },
    /** Xoá nhãn khỏi kho VÀ gỡ khỏi mọi bước đang mang. Trả số bước bị gỡ. */
    xoaNhanKho(token: string, nhanId: number): Promise<{ so_buoc_da_go: number }> {
      return authed<{ so_buoc_da_go: number }>(`/api/cong-doan-tags/kho/${nhanId}`, token, {
        method: "DELETE",
      });
    },
  },

  // --- Nhân sự · Hồ sơ nhân sự (nhan_su), lát #1 ----------------------------
  employees: {
    /** Danh sách nhân sự ra .xlsx THẬT (blob URL). Máy chủ lấy TRỌN theo phạm vi quyền + đúng
     *  bộ lọc đang chọn — không phụ thuộc trang đang xem, không cắt ở 200 người. */
    exportXlsxBlobUrl(
      token: string,
      params: Omit<EmployeeListParams, "page" | "size"> = {},
    ): Promise<string> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.department_id != null) qs.set("department_id", String(params.department_id));
      if (params.has_account != null) qs.set("has_account", String(params.has_account));
      if (params.ending_soon) qs.set("ending_soon", "true");
      if (params.sort) qs.set("sort", params.sort);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return blobUrl(`/api/employees/export.xlsx${suffix}`, token);
    },
    /** File MẪU để nạp dữ liệu ban đầu: đúng tiêu đề của file xuất, không kèm ai, cộng sheet
     *  Hướng dẫn liệt kê tên phòng/tổ · bậc · ca hợp lệ. Ai nhập được là tải được. */
    mauNhapBlobUrl(token: string): Promise<string> {
      return blobUrl("/api/employees/mau-nhap.xlsx", token);
    },
    /** Nhập hồ sơ từ .xlsx. `preview` chạy y hệt `commit` rồi rollback ⇒ con số xem trước là
     *  con số THẬT. Trả CÙNG hình dạng với nhập Excel danh mục (`ImportExcelOut`). */
    importExcel(token: string, file: File, mode: "preview" | "commit"): Promise<ImportExcelOut> {
      const form = new FormData();
      form.append("file", file);
      return authed<ImportExcelOut>(`/api/employees/import-excel?mode=${mode}`, token, {
        method: "POST",
        body: form,
      });
    },
    list(token: string, params: EmployeeListParams = {}): Promise<EmployeeListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.department_id != null) qs.set("department_id", String(params.department_id));
      if (params.status) qs.set("status", params.status);
      if (params.has_account != null) qs.set("has_account", String(params.has_account));
      if (params.ending_soon) qs.set("ending_soon", "true");
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
    /** Xác nhận TC theo phiếu (07/09/2026): phiếu đã duyệt của ngày + tình trạng cặp bấm, theo scope Chấm bù. */
    otConfirmCandidates(token: string, date: string, departmentId?: number | null): Promise<OtConfirmCandidates> {
      const qs = new URLSearchParams({ date });
      if (departmentId != null) qs.set("department_id", String(departmentId));
      return authed<OtConfirmCandidates>(`/api/attendance/ot-confirm?${qs.toString()}`, token);
    },
    /** Sinh cặp bấm tay theo phiếu cho các NV thiếu cặp — ai không thiếu thì máy bỏ qua có lý do. */
    otConfirm(token: string, input: OtConfirmInput): Promise<OtConfirmResult> {
      return authed<OtConfirmResult>("/api/attendance/ot-confirm", token, {
        method: "POST", body: JSON.stringify(input),
      });
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
    approveAdjustRequest(token: string, id: number, input: { time?: string | null; next_day?: boolean | null; fault_party?: string | null; note?: string | null }): Promise<AdjustRequest> {
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
    /** Xuất bảng công tháng ra .xlsx — fetch as a blob (bearer + refresh-aware).
     *  Bản .csv cũ đã bỏ 09/09/2026: ô ngày không ra công/giờ in chữ "có" và tăng ca không hiện. */
    async timesheetExcelBlobUrl(token: string, year: number, month: number, departmentId?: number | null,
                                q?: string | null): Promise<string> {
      const qs = new URLSearchParams({ year: String(year), month: String(month) });
      if (departmentId != null) qs.set("department_id", String(departmentId));
      // `q` = ô tìm tên/mã trên màn: file xuất ra phải đúng thứ đang thấy, không phải cả xưởng.
      if (q && q.trim()) qs.set("q", q.trim());
      const doFetch = (bearer: string) =>
        fetch(`${BASE_URL}/api/attendance/timesheet.xlsx?${qs.toString()}`, {
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
    /** Danh sách ca + mẫu số đang áp (Giờ công chuẩn / ngày, luật "ca phải khớp" — 07/09/2026). */
    shifts(token: string): Promise<WorkShiftsList> {
      return authed<WorkShiftsList>("/api/attendance/shifts", token);
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
    /** `thang` = `YYYY-MM`, lọc theo tháng NGÀY TẠO phiếu (23/09/2026). Mới tạo nhất lên đầu. */
    mine(token: string, params?: { page?: number; size?: number; thang?: string }): Promise<MyOvertime> {
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
      /** `YYYY-MM` — tháng NGÀY TẠO phiếu. */
      thang?: string;
    }): Promise<Paged<OvertimeRequest>> {
      return authed<Paged<OvertimeRequest>>(`/api/overtime${qs({
        status_filter: params?.statusFilter,
        employee_id: params?.employeeId,
        thang: params?.thang,
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
    /** Hủy THẲNG. Phiếu ĐÃ DUYỆT chỉ người duyệt hủy được và phải có `lyDo` (23/09/2026). */
    cancel(token: string, id: number, lyDo?: string): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/${id}/cancel`, token,
        { method: "POST", body: JSON.stringify({ ly_do: lyDo ?? null }) });
    },
    // --- Xin hủy phiếu ĐÃ DUYỆT (23/09/2026) ---
    xinHuy(token: string, id: number, lyDo: string): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/${id}/xin-huy`, token,
        { method: "POST", body: JSON.stringify({ ly_do: lyDo }) });
    },
    rutLaiXinHuy(token: string, ycId: number): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/xin-huy/${ycId}/rut-lai`, token, { method: "POST" });
    },
    /** `dongY=false` (giữ nguyên) phải có `ghiChu`. */
    quyetXinHuy(token: string, ycId: number, dongY: boolean, ghiChu?: string): Promise<OvertimeRequest> {
      return authed<OvertimeRequest>(`/api/overtime/xin-huy/${ycId}/quyet`, token,
        { method: "POST", body: JSON.stringify({ dong_y: dongY, ghi_chu: ghiChu ?? null }) });
    },
    xinHuyChoDuyet(token: string): Promise<{ items: XinHuyChoDuyet<OvertimeRequest>[] }> {
      return authed<{ items: XinHuyChoDuyet<OvertimeRequest>[] }>("/api/overtime/xin-huy", token);
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
    /** Số dư trần giờ làm thêm THÁNG (Đ107). `employeeId` bỏ trống = của chính người gọi;
     *  `excludeId` = id phiếu ĐANG SỬA để nó không tự đếm chính nó. */
    tranThang(token: string, params: {
      year: number; month: number; employeeId?: number | null; excludeId?: number | null;
    }): Promise<TranThangOut> {
      return authed<TranThangOut>(`/api/overtime/tran-thang${qs({
        year: params.year,
        month: params.month,
        employee_id: params.employeeId,
        exclude_id: params.excludeId,
      })}`, token);
    },
    markSeen(token: string): Promise<void> {
      return authed<void>("/api/overtime/mark-seen", token, { method: "POST" });
    },
    /** Thợ trong tầm để tạo hộ — KHÔNG dùng `/api/employees` (tổ trưởng không có module nhân sự). */
    roster(token: string): Promise<OvertimeRoster> {
      return authed<OvertimeRoster>("/api/overtime/roster", token);
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
    /** `thang` = `YYYY-MM`, lọc theo tháng NGÀY TẠO đơn (23/09/2026). Mới tạo nhất lên đầu. */
    me(token: string, params?: { page?: number; size?: number; thang?: string }): Promise<MyLeave> {
      return authed<MyLeave>(`/api/leaves/me${qs(params)}`, token);
    },
    create(token: string, input: LeaveRequestInput): Promise<LeaveRequest> {
      return authed<LeaveRequest>("/api/leaves", token, { method: "POST", body: JSON.stringify(input) });
    },
    /** Hủy THẲNG. Đơn ĐÃ DUYỆT chỉ người duyệt hủy được và phải có `lyDo` (23/09/2026). */
    cancel(token: string, id: number, lyDo?: string): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/${id}/cancel`, token,
        { method: "POST", body: JSON.stringify({ ly_do: lyDo ?? null }) });
    },
    // --- Xin hủy đơn ĐÃ DUYỆT (23/09/2026) ---
    xinHuy(token: string, id: number, lyDo: string): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/${id}/xin-huy`, token,
        { method: "POST", body: JSON.stringify({ ly_do: lyDo }) });
    },
    rutLaiXinHuy(token: string, ycId: number): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/xin-huy/${ycId}/rut-lai`, token, { method: "POST" });
    },
    /** `dongY=false` (giữ nguyên) phải có `ghiChu`. */
    quyetXinHuy(token: string, ycId: number, dongY: boolean, ghiChu?: string): Promise<LeaveRequest> {
      return authed<LeaveRequest>(`/api/leaves/xin-huy/${ycId}/quyet`, token,
        { method: "POST", body: JSON.stringify({ dong_y: dongY, ghi_chu: ghiChu ?? null }) });
    },
    xinHuyChoDuyet(token: string): Promise<{ items: XinHuyChoDuyet<LeaveRequest>[] }> {
      return authed<{ items: XinHuyChoDuyet<LeaveRequest>[] }>("/api/leaves/xin-huy", token);
    },
    list(token: string, params?: {
      status?: string; employeeId?: number; page?: number; size?: number;
      /** `YYYY-MM` — tháng NGÀY TẠO đơn. */
      thang?: string;
    }): Promise<Paged<LeaveRequest>> {
      return authed<Paged<LeaveRequest>>(`/api/leaves${qs({
        status: params?.status,
        thang: params?.thang,
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
    /** Bảng đối chiếu khoán km của một dòng lương — từng chuyến giao đã sinh ra tiền.
     *  `tong` PHẢI khớp cột "Khoán km"; lệch là một trong hai bên tính sai. */
    chiTietKhoanKm(token: string, lineId: number): Promise<KhoanKmChiTiet> {
      return authed<KhoanKmChiTiet>(`/api/luong/lines/${lineId}/khoan-km`, token);
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
    // --- Cấu hình lương: chỉ tiêu ngày của tổ khoán / sản lượng (chưa nối vào tính lương) ---
    chiTieuNgay(token: string, deptId: number): Promise<ChiTieuNgayList> {
      return authed<ChiTieuNgayList>(`/api/luong/khoan/chi-tieu-ngay/${deptId}`, token);
    },
    /** Cùng tổ + CÙNG ngày áp dụng ⇒ sửa số của mốc đó (không đẻ mốc trùng ngày). */
    khaiChiTieuNgay(token: string, deptId: number, input: ChiTieuNgayInput): Promise<ChiTieuNgayList> {
      return authed<ChiTieuNgayList>(`/api/luong/khoan/chi-tieu-ngay/${deptId}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    xoaChiTieuNgay(token: string, deptId: number, mucId: number): Promise<ChiTieuNgayList> {
      return authed<ChiTieuNgayList>(`/api/luong/khoan/chi-tieu-ngay/${deptId}/${mucId}`, token, { method: "DELETE" });
    },
    // --- Tổ trưởng ăn thưởng / ăn chia theo sản lượng tổ (19/09/2026) — chưa nối vào lương ---
    toTruong(token: string, deptId: number): Promise<ToTruongList> {
      return authed<ToTruongList>(`/api/luong/khoan/to-truong/${deptId}`, token);
    },
    /** Cùng tổ + CÙNG ngày áp dụng ⇒ sửa mốc đó (không đẻ mốc trùng ngày). */
    khaiToTruong(token: string, deptId: number, input: ToTruongInput): Promise<ToTruongList> {
      return authed<ToTruongList>(`/api/luong/khoan/to-truong/${deptId}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    xoaToTruong(token: string, deptId: number, mucId: number): Promise<ToTruongList> {
      return authed<ToTruongList>(`/api/luong/khoan/to-truong/${deptId}/${mucId}`, token, { method: "DELETE" });
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
    /** Bỏ trống `ky` ⇒ kỳ mới nhất đang mở (hành vi cũ). Truyền vào ⇒ tra lại tháng đó —
     *  máy chủ vẫn lọc theo cửa sổ công bố nên tháng chưa phát trả về rỗng. */
    myPayslip(token: string, ky?: { year: number; month: number }): Promise<MyPayslip> {
      const q = ky ? `?year=${ky.year}&month=${ky.month}` : "";
      return authed<MyPayslip>(`/api/luong/payslip/me${q}`, token);
    },
  },

  // --- Giao hàng (module `giao_hang`) ---------------------------------------
  // Ba nhóm đường: yêu cầu (Bán hàng) · kế hoạch + chuyến (Giao hàng) · đề nghị xuất (Kho).
  // Đường của kho gác bằng ô `kho`, KHÔNG phải ô `giao_hang` — kho không cần cấp thêm ô nào.
  giaoHang: {
    conPhaiGiao(token: string, orderId: number): Promise<ConPhaiGiao> {
      return authed<ConPhaiGiao>(`/api/giao-hang/orders/${orderId}/con-phai-giao`, token);
    },
    requests(token: string, opts?: { orderId?: number; choLenKeHoach?: boolean; page?: number; size?: number }): Promise<{ items: DeliveryRequest[]; total: number }> {
      const q = new URLSearchParams();
      if (opts?.orderId != null) q.set("order_id", String(opts.orderId));
      if (opts?.choLenKeHoach) q.set("cho_len_ke_hoach", "true");
      if (opts?.page != null) q.set("page", String(opts.page));
      if (opts?.size != null) q.set("size", String(opts.size));
      const s = q.toString();
      return authed<{ items: DeliveryRequest[]; total: number }>(`/api/giao-hang/requests${s ? `?${s}` : ""}`, token);
    },
    request(token: string, id: number): Promise<DeliveryRequestDetail> {
      return authed<DeliveryRequestDetail>(`/api/giao-hang/requests/${id}`, token);
    },
    createRequest(token: string, input: DeliveryRequestInput): Promise<DeliveryRequest> {
      return authed<DeliveryRequest>("/api/giao-hang/requests", token, { method: "POST", body: JSON.stringify(input) });
    },
    updateRequest(token: string, id: number, input: Partial<DeliveryRequestInput>): Promise<DeliveryRequest> {
      return authed<DeliveryRequest>(`/api/giao-hang/requests/${id}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    cancelRequest(token: string, id: number, lyDo: string): Promise<DeliveryRequest> {
      return authed<DeliveryRequest>(`/api/giao-hang/requests/${id}/huy`, token, { method: "POST", body: JSON.stringify({ ly_do: lyDo }) });
    },

    trips(token: string, opts?: { dangChay?: boolean; page?: number; size?: number }): Promise<{ items: DeliveryTrip[]; total: number }> {
      const q = new URLSearchParams();
      if (opts?.dangChay) q.set("dang_chay", "true");
      if (opts?.page != null) q.set("page", String(opts.page));
      if (opts?.size != null) q.set("size", String(opts.size));
      const s = q.toString();
      return authed<{ items: DeliveryTrip[]; total: number }>(`/api/giao-hang/trips${s ? `?${s}` : ""}`, token);
    },
    plan(token: string, input: PlanInput): Promise<{ trip: DeliveryTrip; canh_bao: string[] }> {
      return authed<{ trip: DeliveryTrip; canh_bao: string[] }>("/api/giao-hang/plans", token, { method: "POST", body: JSON.stringify(input) });
    },
    updatePlan(token: string, tripId: number, input: Partial<PlanInput>): Promise<{ trip: DeliveryTrip; canh_bao: string[] }> {
      return authed<{ trip: DeliveryTrip; canh_bao: string[] }>(`/api/giao-hang/plans/${tripId}`, token, { method: "PUT", body: JSON.stringify(input) });
    },
    cancelPlan(token: string, tripId: number, lyDo: string): Promise<DeliveryTrip> {
      return authed<DeliveryTrip>(`/api/giao-hang/plans/${tripId}/huy`, token, { method: "POST", body: JSON.stringify({ ly_do: lyDo }) });
    },
    /** Chuyến ĐẦU của một lượt xe phải kèm số đồng hồ lúc xe rời kho (PRD khoán km §14). Trả về
     *  `canh_bao` (vd "xe chạy ngoài sổ N km") — không chặn, chỉ để người bấm biết. */
    batDauGiao(token: string, tripId: number, input?: { so_dong_ho_xuat_phat?: number }): Promise<DeliveryTrip> {
      return authed<DeliveryTrip>(`/api/giao-hang/trips/${tripId}/bat-dau-giao`, token, {
        method: "POST", ...(input ? { body: JSON.stringify(input) } : {}),
      });
    },
    ghiKetQua(token: string, tripId: number, input: KetQuaInput): Promise<DeliveryTrip> {
      return authed<DeliveryTrip>(`/api/giao-hang/trips/${tripId}/ket-qua`, token, { method: "POST", body: JSON.stringify(input) });
    },
    /** Lượt CHƯA về kho của một xe — ô Lượt xe lúc lên đơn giao hàng. */
    luotXeMo(token: string, vehicleId: number): Promise<{ items: LuotXeMo[] }> {
      return authed<{ items: LuotXeMo[] }>(`/api/giao-hang/luot-xe?vehicle_id=${vehicleId}`, token);
    },
    /** Tài xế ghi số đồng hồ lúc xe về tới kho ⇒ đóng lượt, máy tính km chặng về kho. */
    veKho(token: string, luotId: number, input: { so_dong_ho: number; xac_nhan_km_lon?: boolean }): Promise<VeKhoKetQua> {
      return authed<VeKhoKetQua>(`/api/giao-hang/luot-xe/${luotId}/ve-kho`, token, { method: "POST", body: JSON.stringify(input) });
    },
    /** Tab "Đơn giao hàng" gom theo LƯỢT XE — mỗi lượt MỘT khối (đủ các điểm), chuyến lẻ một khối.
     *  Trang hoá theo KHỐI ở máy chủ nên một lượt không bị cắt đôi qua hai trang. */
    bangGiao(token: string, opts?: { page?: number; size?: number }): Promise<BangGiaoPage> {
      const q = new URLSearchParams();
      if (opts?.page != null) q.set("page", String(opts.page));
      if (opts?.size != null) q.set("size", String(opts.size));
      const s = q.toString();
      return authed<BangGiaoPage>(`/api/giao-hang/bang-giao${s ? `?${s}` : ""}`, token);
    },
    /** Lên đơn NHIỀU yêu cầu vào MỘT lượt xe bằng một lần bấm (chủ chốt 18/09/2026). Mỗi yêu cầu
     *  vẫn một chuyến, một phiếu xuất kho; một yêu cầu hỏng là cả lô không lưu. */
    lenLuot(token: string, input: LenLuotInput): Promise<LenLuotKetQua> {
      return authed<LenLuotKetQua>("/api/giao-hang/luot-xe", token, { method: "POST", body: JSON.stringify(input) });
    },
    /** Cả lượt nhìn một chỗ — các điểm theo thứ tự chặng + số đếm để biết bày nút cả lượt nào. */
    luotXe(token: string, luotId: number): Promise<LuotXeChiTiet> {
      return authed<LuotXeChiTiet>(`/api/giao-hang/luot-xe/${luotId}`, token);
    },
    /** Mỗi chuyến của lượt MỘT phiếu yêu cầu xuất kho — gửi cả lượt một lần. */
    guiXuatKhoCaLuot(token: string, luotId: number, ghiChu?: string | null): Promise<CaLuotKetQua> {
      return authed<CaLuotKetQua>(`/api/giao-hang/luot-xe/${luotId}/yeu-cau-xuat-kho`, token, {
        method: "POST", body: JSON.stringify({ ghi_chu: ghiChu || null }),
      });
    },
    daLayHangCaLuot(token: string, luotId: number): Promise<CaLuotKetQua> {
      return authed<CaLuotKetQua>(`/api/giao-hang/luot-xe/${luotId}/da-lay-hang`, token, { method: "POST" });
    },
    /** Xe rời kho với mọi chuyến đã lấy hàng; số đồng hồ xuất phát ghi MỘT lần cho cả lượt. */
    batDauGiaoCaLuot(token: string, luotId: number, input?: { so_dong_ho_xuat_phat?: number }): Promise<CaLuotKetQua> {
      return authed<CaLuotKetQua>(`/api/giao-hang/luot-xe/${luotId}/bat-dau-giao`, token, {
        method: "POST", ...(input ? { body: JSON.stringify(input) } : {}),
      });
    },
    daTraHang(token: string, tripId: number): Promise<DeliveryTrip> {
      return authed<DeliveryTrip>(`/api/giao-hang/trips/${tripId}/da-tra-hang`, token, { method: "POST" });
    },

    /** Xem trước dòng sẽ gửi kho — suy ra từ yêu cầu giao, không sửa được. */
    hangCanXuat(token: string, tripId: number): Promise<HangCanXuat[]> {
      return authed<HangCanXuat[]>(`/api/giao-hang/plans/${tripId}/hang-can-xuat`, token);
    },
    /** Gửi YÊU CẦU XUẤT KHO thật — chứng từ của KHO, không phải loại riêng của Giao hàng.
     *  Hàng ra khỏi kho phải có phiếu kho; giao khách không ngoại lệ (chủ chốt 19/08/2026). */
    guiYeuCauXuatKho(token: string, tripId: number, input: YeuCauXuatKhoInput): Promise<YeuCauKho> {
      return authed<YeuCauKho>(`/api/giao-hang/plans/${tripId}/yeu-cau-xuat-kho`, token, { method: "POST", body: JSON.stringify(input) });
    },
    /** File MINH CHỨNG của chuyến — ảnh/PDF. Hàng đi kèm hoá đơn: trước lúc đi đính hoá đơn cho
     *  tài xế cầm theo, giao xong chụp lại tờ khách đã ký. Đính được ở bất kỳ lúc nào. */
    dinhKemChuyen(token: string, tripId: number): Promise<{ items: DinhKemChuyen[] }> {
      return authed<{ items: DinhKemChuyen[] }>(`/api/giao-hang/trips/${tripId}/dinh-kem`, token);
    },
    themDinhKemChuyen(token: string, tripId: number, file: File): Promise<DinhKemChuyen> {
      const form = new FormData();
      form.append("file", file);
      return authed<DinhKemChuyen>(`/api/giao-hang/trips/${tripId}/dinh-kem`, token, {
        method: "POST", body: form,
      });
    },
    xoaDinhKemChuyen(token: string, tripId: number, attachmentId: number): Promise<void> {
      return authed<void>(`/api/giao-hang/trips/${tripId}/dinh-kem/${attachmentId}`, token, {
        method: "DELETE",
      });
    },

    /** Tài xế TỰ bấm khi đã cầm được hàng. Trước đây do kho bấm — đổi 19/08/2026. */
    daLayHang(token: string, tripId: number): Promise<DeliveryTrip> {
      return authed<DeliveryTrip>(`/api/giao-hang/trips/${tripId}/da-lay-hang`, token, { method: "POST" });
    },

    /** Tài xế CHỌN ĐƯỢC khi phân công — gác bằng ô Lên kế hoạch, KHÔNG phải `nhan_su`. */
    taiXeChon(token: string): Promise<{ items: DeliveryDriverPick[] }> {
      return authed<{ items: DeliveryDriverPick[] }>("/api/giao-hang/tai-xe-chon", token);
    },
    /** % chia tiền một chuyến cho kíp xe. Bảng BẬC cấp phòng đã gỡ 12/09/2026 — mọi xe ăn
     *  theo MỨC; % thì giữ vì nó là luật khác: đơn giá quyết một chuyến bao nhiêu tiền, % quyết
     *  chia cho mấy người. */
    khoanKmPct(token: string, deptId: number): Promise<KhoanKmPct> {
      return authed<KhoanKmPct>(`/api/giao-hang/departments/${deptId}/khoan-km-pct`, token);
    },
    saveKhoanKmPct(token: string, deptId: number, body: KhoanKmPct): Promise<KhoanKmPct> {
      return authed<KhoanKmPct>(`/api/giao-hang/departments/${deptId}/khoan-km-pct`, token,
        { method: "PUT", body: JSON.stringify(body) });
    },
    /** Mọi MỨC khoán km + bảng bậc + số xe đang dùng mức đó. */
    mucKhoanKm(token: string): Promise<{ items: MucKm[] }> {
      return authed<{ items: MucKm[] }>("/api/giao-hang/muc-khoan-km", token);
    },
    taoMucKhoanKm(token: string, body: MucKmInput): Promise<{ items: MucKm[] }> {
      return authed<{ items: MucKm[] }>("/api/giao-hang/muc-khoan-km", token,
        { method: "POST", body: JSON.stringify(body) });
    },
    /** Chỉ gửi ô muốn đổi — ô KHÔNG gửi thì máy chủ giữ nguyên (đổi tên không làm mất ghi chú). */
    suaMucKhoanKm(token: string, id: number, body: Partial<MucKmInput>): Promise<{ items: MucKm[] }> {
      return authed<{ items: MucKm[] }>(`/api/giao-hang/muc-khoan-km/${id}`, token,
        { method: "PUT", body: JSON.stringify(body) });
    },
    /** Máy chủ CHẶN nếu còn xe đang ăn mức — lỗi mang số xe, hiện thẳng cho người dùng. */
    xoaMucKhoanKm(token: string, id: number): Promise<{ items: MucKm[] }> {
      return authed<{ items: MucKm[] }>(`/api/giao-hang/muc-khoan-km/${id}`, token,
        { method: "DELETE" });
    },
    /** Lưu bảng bậc của MỘT mức — cấu hình chung, không theo phòng ban (14/09/2026). Mảng RỖNG
     *  bị máy chủ chặn khi mức còn xe đang ăn. */
    saveKmBracketsMuc(token: string, mucId: number, items: KmBracket[]): Promise<{ items: MucKm[] }> {
      return authed<{ items: MucKm[] }>(`/api/giao-hang/muc-khoan-km/${mucId}/bac`, token,
        { method: "PUT", body: JSON.stringify({ items }) });
    },
    /** `thang` dạng `YYYY-MM` — chỉ đổi hai cột THÁNG. Cột "hôm nay" và trạng thái luôn là
     *  bây giờ, không đổi theo tháng đang xem. */
    nhanVien(token: string, opts?: { ngay?: string; thang?: string }): Promise<{ items: DeliveryDriver[] }> {
      const q = new URLSearchParams();
      if (opts?.ngay) q.set("ngay", opts.ngay);
      if (opts?.thang) q.set("thang", opts.thang);
      const s = q.toString();
      return authed<{ items: DeliveryDriver[] }>(`/api/giao-hang/nhan-vien${s ? `?${s}` : ""}`, token);
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
      params: { q?: string; status?: string; sort?: string; page?: number; size?: number } = {},
    ): Promise<PhieuTinhGiaListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.sort) qs.set("sort", params.sort);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<PhieuTinhGiaListOut>(`/api/phieu-tinh-gia${suffix}`, token);
    },
    stats(token: string): Promise<PhieuTinhGiaStatsOut> {
      return authed<PhieuTinhGiaStatsOut>("/api/phieu-tinh-gia/stats", token);
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
    /** Gợi ý Sản phẩm tái bản theo tên — dùng chung toàn hệ thống, không lọc theo khách hàng. */
    timSanPhamTaiBan(token: string, q: string, size = 20): Promise<SanPhamTaiBanGoiY[]> {
      const qs = new URLSearchParams({ q, size: String(size) });
      return authed<SanPhamTaiBanGoiY[]>(`/api/phieu-tinh-gia/san-pham-tai-ban?${qs.toString()}`, token);
    },
    /** Cấu hình kỹ thuật đầy đủ (dạng ThanhPhanIn) của 1 mẫu tái bản. */
    chiTietSanPhamTaiBan(token: string, id: number): Promise<ThanhPhanIn> {
      return authed<ThanhPhanIn>(`/api/phieu-tinh-gia/san-pham-tai-ban/${id}`, token);
    },
  },

  // --- Lệnh sản xuất (LSX) — bàn Kế hoạch sản xuất ---------------------------
  lsx: {
    /** Đơn Sale đã "Chuyển xuống sản xuất" mà còn dòng chưa lên lệnh. */
    hangCho(token: string, params: { page?: number; size?: number } = {}): Promise<HangChoOut> {
      const qs = new URLSearchParams();
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<HangChoOut>(`/api/lsx/hang-cho${suffix}`, token);
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
    list(
      token: string,
      params: {
        order_id?: number; customer_id?: number; trang_thai?: string; q?: string;
        page?: number; size?: number;
      } = {},
    ): Promise<LsxListOut> {
      const qs = new URLSearchParams();
      if (params.order_id) qs.set("order_id", String(params.order_id));
      if (params.customer_id) qs.set("customer_id", String(params.customer_id));
      if (params.trang_thai) qs.set("trang_thai", params.trang_thai);
      if (params.q) qs.set("q", params.q);
      if (params.page) qs.set("page", String(params.page));
      if (params.size) qs.set("size", String(params.size));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<LsxListOut>(`/api/lsx${suffix}`, token);
    },
    /** Đơn / khách để đổ vào hai ô lọc của bảng lệnh. KHÔNG truyền `order_id`/`customer_id`:
     *  danh sách chọn phải đứng yên khi đang lọc, không thì chọn xong là hết đường đổi. */
    boLoc(token: string, params: { trang_thai?: string; q?: string } = {}): Promise<LsxBoLocOut> {
      const qs = new URLSearchParams();
      if (params.trang_thai) qs.set("trang_thai", params.trang_thai);
      if (params.q) qs.set("q", params.q);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<LsxBoLocOut>(`/api/lsx/bo-loc${suffix}`, token);
    },
    /** Hàng 3 đèn cho ĐÚNG các lệnh đang hiện trên bảng. Gọi RỜI sau `list`: bên trong máy chủ
     *  chạy engine cân đối vật tư + bộ dò vấn đề cho cả bàn xếp lịch. Bảng lệnh phải hiện ngay,
     *  đèn nhảy vào sau. ĐỪNG gọi lại khi chỉ gõ ô tìm — `loadLenhs` chạy lại mỗi 250ms. */
    tongQuan(token: string, ids: number[]): Promise<LsxTongQuanOut> {
      if (!ids.length) return Promise.resolve({ items: [] });
      return authed<LsxTongQuanOut>(`/api/lsx/tong-quan?ids=${ids.join(",")}`, token);
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
      body: { ten: string; loai: string | null },
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
    /** Bộ số đang sửa trên drawer thì bước chạy bao nhiêu phút? CHỈ ĐỌC.
     *
     *  Có cửa này vì SL vào phải quy đổi sang ĐƠN VỊ ĐÍCH của máy mà bảng cầu quy đổi chỉ nằm ở
     *  backend. Thiếu nó thì form phải bấm "Lưu công đoạn" mới thấy số đổi (20/08/2026).
     *
     *  Gửi mọi thứ đang sửa: máy · loại bước · số lượt · SỐ GIỜ KẾ HOẠCH (bước tổ, mg `0319`).
     *  `pieceRateId` GỠ 18/09/2026 cùng ô đầu việc của bước. */
    xemTruocBuoc(
      token: string, id: number, stepKey: string,
      dang: { mayId?: number | null; loaiBuoc?: string | null;
              soLuotChay?: number | null; soGioKeHoach?: number | null;
              soLuongVao?: number | null; soLuongRa?: number | null;
              congDoanId?: number | null; donViVao?: string | null } = {},
    ): Promise<LsxXemTruocBuoc> {
      const q = new URLSearchParams({ step_key: stepKey });
      if (dang.mayId != null) q.set("may_id", String(dang.mayId));
      if (dang.loaiBuoc) q.set("loai_buoc", dang.loaiBuoc);
      if (dang.soLuotChay != null) q.set("so_luot_chay", String(dang.soLuotChay));
      if (dang.soGioKeHoach != null) q.set("so_gio_ke_hoach", String(dang.soGioKeHoach));
      // Hai ô số lượng gửi cả khi bằng 0 — ô TRỐNG là 0 thật, không phải "không có ý kiến".
      if (dang.soLuongVao != null) q.set("so_luong_vao", String(dang.soLuongVao));
      if (dang.soLuongRa != null) q.set("so_luong_ra", String(dang.soLuongRa));
      if (dang.congDoanId != null) q.set("cong_doan_id", String(dang.congDoanId));
      if (dang.donViVao) q.set("don_vi_vao", dang.donViVao);
      return authed<LsxXemTruocBuoc>(`/api/lsx/${id}/xem-truoc-buoc?${q}`, token);
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
    /** Lấy lại số MỚI NHẤT của danh mục Công đoạn cho CẢ lệnh (khoán + định mức vật tư).
     *  Không xoá dòng vật tư nào và không đụng số nhân công đã sắp — xem `dong_bo_danh_muc`. */
    dongBoDanhMuc(token: string, id: number): Promise<LsxDetail> {
      return authed<LsxDetail>(`/api/lsx/${id}/dong-bo-danh-muc`, token, { method: "POST" });
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
    /** Đổi/chèn công đoạn thì số VÀO–RA + đơn vị cả chuỗi ra bao nhiêu? CHỈ ĐỌC — server chạy
     *  đúng đường Lưu routing rồi rollback (giống đổi máy gọi thời lượng). Có nó để số nhảy ngay,
     *  khỏi bấm Lưu, mà không cần chép công thức chuỗi ngược sang JS. */
    xemTruocRouting(
      token: string, id: number, congDoans: LsxXemTruocRoutingRow[],
    ): Promise<{ cong_doans: LsxXemTruocRoutingBuoc[] }> {
      return authed<{ cong_doans: LsxXemTruocRoutingBuoc[] }>(
        `/api/lsx/${id}/xem-truoc-routing`, token, {
          method: "POST",
          body: JSON.stringify({ cong_doans: congDoans }),
        });
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
    // --- Tệp đính kèm của lệnh: mỗi tệp một request để tệp lỗi không kéo cả mẻ lỗi theo ---
    dinhKem(token: string, id: number): Promise<{ items: LsxDinhKem[] }> {
      return authed<{ items: LsxDinhKem[] }>(`/api/lsx/${id}/dinh-kem`, token);
    },
    taiDinhKem(token: string, id: number, file: File): Promise<LsxDinhKem> {
      const form = new FormData();
      form.append("file", file);
      return authed<LsxDinhKem>(`/api/lsx/${id}/dinh-kem`, token, { method: "POST", body: form });
    },
    xoaDinhKem(token: string, id: number, dinhKemId: number): Promise<void> {
      return authed<void>(`/api/lsx/${id}/dinh-kem/${dinhKemId}`, token, { method: "DELETE" });
    },
  },

  // --- Bài ghép 2 — cùng tài nguyên/engine, API và quyền độc lập trong giai đoạn nghiệm thu. ---
  baiGhep2: {
    nguoiPhuTrachOptions(token: string): Promise<{ items: BaiGhep2NguoiPhuTrachOption[] }> {
      return authed<{ items: BaiGhep2NguoiPhuTrachOption[] }>("/api/bai-ghep-2/nguoi-phu-trach-options", token);
    },
    hangCho(token: string, params: { q?: string } = {}): Promise<HangChoGhepOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<HangChoGhepOut>(`/api/bai-ghep-2/hang-cho${suffix}`, token);
    },
    list(token: string): Promise<BaiGhep2ListOut> {
      return authed<BaiGhep2ListOut>("/api/bai-ghep-2", token);
    },
    get(token: string, id: number): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(`/api/bai-ghep-2/${id}`, token);
    },
    tao(token: string, lsxIds: number[]): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>("/api/bai-ghep-2", token, {
        method: "POST", body: JSON.stringify({ lsx_ids: lsxIds }),
      });
    },
    update(token: string, id: number, body: BaiGhep2UpdateBody): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(`/api/bai-ghep-2/${id}`, token, {
        method: "PUT", body: JSON.stringify(body),
      });
    },
    themThanhVien(token: string, id: number, lsxIds: number[]): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(`/api/bai-ghep-2/${id}/thanh-vien`, token, {
        method: "POST", body: JSON.stringify({ lsx_ids: lsxIds }),
      });
    },
    suaThanhVien(token: string, id: number, tvId: number, soConTrenTo: number): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(`/api/bai-ghep-2/${id}/thanh-vien/${tvId}`, token, {
        method: "PUT", body: JSON.stringify({ so_con_tren_to: soConTrenTo }),
      });
    },
    boThanhVien(token: string, id: number, tvId: number): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(`/api/bai-ghep-2/${id}/thanh-vien/${tvId}`, token, { method: "DELETE" });
    },
    soDo(token: string, id: number): Promise<BaiGhepSoDo> {
      return authed<BaiGhepSoDo>(`/api/bai-ghep-2/${id}/so-do`, token);
    },
    gop(token: string, id: number, stepKeys: string[]): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(`/api/bai-ghep-2/${id}/gop`, token, {
        method: "POST", body: JSON.stringify({ step_keys: stepKeys }),
      });
    },
    tach(token: string, id: number, gangStepKey: string): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(
        `/api/bai-ghep-2/${id}/gop/${encodeURIComponent(gangStepKey)}`, token, { method: "DELETE" },
      );
    },
    luuBuocChung(
      token: string, id: number, gangStepKey: string, body: BaiGhepBuocChungBody,
    ): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(
        `/api/bai-ghep-2/${id}/gop/${encodeURIComponent(gangStepKey)}`, token,
        { method: "PUT", body: JSON.stringify(body) },
      );
    },
    ungVienGop(token: string, id: number, stepKeys: string[]): Promise<BaiGhepUngVienGop> {
      return authed<BaiGhepUngVienGop>(`/api/bai-ghep-2/${id}/ung-vien-gop`, token, {
        method: "POST", body: JSON.stringify({ step_keys: stepKeys }),
      });
    },
    vatTuHieuLuc(token: string, id: number): Promise<BaiGhep2VatTuHieuLuc> {
      return authed<BaiGhep2VatTuHieuLuc>(`/api/bai-ghep-2/${id}/vat-tu-hieu-luc`, token);
    },
    setTrangThai(token: string, id: number, trangThai: BaiGhepTrangThai): Promise<BaiGhep2Detail> {
      return authed<BaiGhep2Detail>(`/api/bai-ghep-2/${id}/trang-thai`, token, {
        method: "POST", body: JSON.stringify({ trang_thai: trangThai }),
      });
    },
    remove(token: string, id: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/bai-ghep-2/${id}`, token, { method: "DELETE" });
    },
    activity(token: string, id: number): Promise<{ items: BaiGhep2Activity[] }> {
      return authed<{ items: BaiGhep2Activity[] }>(`/api/bai-ghep-2/${id}/activity`, token);
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
      neededDate?: string | null,
    ): Promise<{ id: number; code: string }> {
      return authed<{ id: number; code: string }>("/api/ke-hoach-vat-tu/de-nghi-mua", token, {
        method: "POST",
        body: JSON.stringify({ dong, ghi_chu: ghiChu ?? null, needed_date: neededDate ?? null }),
      });
    },
    /** Tính trước yêu cầu mua từ các dòng đã tick — KHÔNG ghi gì. Trả đúng bộ dữ liệu để đổ vào
     *  form "Tạo yêu cầu mua hàng"; yêu cầu chỉ thật sự sinh ra khi người dùng bấm Lưu ở form đó. */
    xemTruocDeNghiMua(
      token: string,
      dong: CanDoiKhoaDong[],
      ghiChu?: string | null,
    ): Promise<DeNghiMuaXemTruoc> {
      return authed<DeNghiMuaXemTruoc>("/api/ke-hoach-vat-tu/de-nghi-mua/xem-truoc", token, {
        method: "POST",
        body: JSON.stringify({ dong, ghi_chu: ghiChu ?? null }),
      });
    },
    /** CÙNG bảng cân đối, xoay theo LỆNH — "lệnh này chạy được chưa" thay vì "còn thiếu gì". */
    theoLenh(
      token: string,
      params: { q?: string; chi_can_lo?: boolean; chi_giu_lau?: boolean } = {},
    ): Promise<TheoLenhOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.chi_can_lo) qs.set("chi_can_lo", "true");
      if (params.chi_giu_lau) qs.set("chi_giu_lau", "true");
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return authed<TheoLenhOut>(`/api/ke-hoach-vat-tu/theo-lenh${suffix}`, token);
    },
    /** Bật/tắt giữ chỗ. Trả về THẺ ĐÃ CẬP NHẬT của chính chủ thể đó — màn chỉ việc thay tại chỗ,
     *  khỏi gọi lại cả danh sách (giữa hai lời gọi người dùng sẽ nhìn thấy một thẻ nói dối). */
    giuCho(
      token: string,
      bat: boolean,
      chu: { lsx_id?: number | null; bai_ghep_id?: number | null },
    ): Promise<TheoLenhRow> {
      return authed<TheoLenhRow>(
        `/api/ke-hoach-vat-tu/giu-cho/${bat ? "bat" : "tat"}`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            lsx_id: chu.lsx_id ?? null,
            bai_ghep_id: chu.bai_ghep_id ?? null,
          }),
        },
      );
    },
  },

  // --- Hồ sơ lệnh sản xuất (module `lenh_san_xuat`) — bàn TRA CỨU, không ghi -
  // Ba đường ĐỌC, không một đường ghi nào — và đừng thêm: màn này cố ý không có nút ghi (tạo/sửa
  // lệnh vẫn ở Kế hoạch sản xuất, module `san_xuat`). Phạm vi dữ liệu do MÁY CHỦ gắn từ token;
  // không có tham số nào cho client tự nới, gửi thêm cũng bị bỏ qua.
  lenhSanXuat: {
    /** 4 thẻ KPI. KHÔNG nhận tham số lọc — luôn là TOÀN PHẠM VI của token, nên số ở đây và số
     *  trên tab không bao giờ khớp, và đó là đúng (màn phải nói ra điều đó). */
    summary(token: string): Promise<LenhSxSummaryOut> {
      return authed<LenhSxSummaryOut>("/api/lenh-san-xuat/summary", token);
    },
    /** Nguồn ô lọc Máy — chỉ máy CÓ THẬT trong tập lệnh của người gọi.
     *
     *  KHÔNG mượn `/api/may-thiet-bi`: bên đó gác `dm_thiet_bi:read` hoặc `tinh_gia_thanh:read`,
     *  mà vai QC — vai đứng ở màn này nhiều nhất — không có ô nào trong hai ô ấy ⇒ 403. */
    boLoc(token: string): Promise<LenhSxBoLocOut> {
      return authed<LenhSxBoLocOut>("/api/lenh-san-xuat/bo-loc", token);
    },
    /** MỘT trang bảng. Lọc + đếm tab + cắt trang đều Ở MÁY CHỦ — không `rows.filter`, không
     *  `rows.slice`, không đếm tab từ `items` (trang chỉ cầm 50 dòng trên một tập cả trăm). */
    danhSach(token: string, params: LenhSxDanhSachParams = {}): Promise<LenhSxListOut> {
      return authed<LenhSxListOut>(
        `/api/lenh-san-xuat${qs({
          tab: params.tab,
          q: params.q,
          page: params.page,
          page_size: params.page_size,
          nhom_cong_doan: params.nhom_cong_doan,
          may_id: params.may_id,
          uu_tien: params.uu_tien,
          // `qs` bỏ qua `undefined`/`null`/`""` — nên `tre: false` vẫn được gửi. Người gọi phải
          // truyền `undefined` khi tắt công tắc, không phải `false` (đó là "chỉ lệnh KHÔNG trễ").
          tre: params.tre,
          tu_ngay: params.tu_ngay,
          den_ngay: params.den_ngay,
        })}`,
        token,
      );
    },
    /** HỒ SƠ một lệnh — 13 khối trong MỘT lượt gọi (`LenhSxHoSoOut`).
     *
     *  404 = màn này không có lệnh nào như thế (không tồn tại, hoặc chưa phát hành);
     *  403 = lệnh CÓ thật nhưng ngoài phạm vi người gọi. Hai mã vì hai câu khác nhau — mặt đọc
     *  phải nói đúng câu tương ứng, đừng gộp thành một lời "không xem được". */
    hoSo(token: string, lsxId: number): Promise<LenhSxHoSoOut> {
      return authed<LenhSxHoSoOut>(`/api/lenh-san-xuat/${lsxId}`, token);
    },

    /** PHIẾU CÔNG NGHỆ A4 — tờ giấy tổ mang xuống xưởng. Trả blob URL vì endpoint đòi Bearer:
     *  `window.open` thẳng vào đường dẫn là mở một tab KHÔNG có token và ăn 401.
     *
     *  N28 (ruling C109): dùng `blobUrlComTen` thay `blobUrl` trần — đọc kỹ docstring của nó TRƯỚC
     *  KHI tưởng chỗ này đã "sửa xong" tên file lúc Lưu. Vẫn `window.open`, KHÔNG đổi sang
     *  `<a download>`: nút này phục vụ "mở lên bấm in", đổi thành tải-về là hỏng đúng việc nút sinh
     *  ra để làm. Hệ quả: N28 **CHƯA đóng** trên đường này — Chromium vẫn gợi ý tên uuid lúc Lưu
     *  trong trình xem PDF built-in, y như trước khi có `blobUrlComTen`. Tên dự phòng ở đây chỉ có
     *  tác dụng cho những đường TIÊU THỤ blob khác qua `<a download>` sau này (nếu có).
     *
     *  Tải phiếu KHÔNG làm tăng `phien_ban` — đây là đọc, không phải phát hành lại. */
    phieuCongNghePdf(token: string, lsxId: number): Promise<string> {
      return blobUrlComTen(
        `/api/lenh-san-xuat/${lsxId}/phieu-cong-nghe.pdf`,
        token,
        `phieu-cong-nghe-${lsxId}.pdf`,
      );
    },
  },

  // --- Theo dõi sản xuất (module `theo_doi_san_xuat`) — bàn TRA CỨU, không ghi ----------------
  // Bốn góc nhìn (Kanban · Theo máy · Theo ca · Gantt) trên MỘT thanh lọc chung. Phạm vi dữ liệu
  // do MÁY CHỦ gắn từ token — không tham số nào cho client tự nới.
  //
  // CẤM gọi `/api/lenh-san-xuat/bo-loc` thay `boLoc` dưới đây: hai endpoint gác HAI ô quyền khác
  // nhau, và repo đã có sẵn vết thương đúng kiểu đó (`LenhSxBoLocOut.boLoc` ở trên).
  theoDoiSanXuat: {
    /** Khung cột Kanban — DANH MỤC công đoạn + cột "Khác" cố định đứng CUỐI (máy chủ đã sắp).
     *  Nạp CÙNG NHỊP với `kanban()` (đừng cache riêng): danh mục công đoạn đổi giữa hai lượt gọi
     *  thì card trỏ vào cột không còn tồn tại và rơi câm vào "Khác". */
    meta(token: string): Promise<TdsxKanbanMeta> {
      return authed<TdsxKanbanMeta>("/api/theo-doi-san-xuat/meta", token);
    },
    /** Nguồn thanh lọc CHUNG của cả bốn tab — endpoint RIÊNG, gác đúng `theo_doi_san_xuat:read`. */
    boLoc(token: string): Promise<TdsxBoLocOut> {
      return authed<TdsxBoLocOut>("/api/theo-doi-san-xuat/bo-loc", token);
    },
    /** MỘT card mỗi lệnh đã phát hành, ĐÃ áp thanh lọc ở máy chủ. Dựng lại literal (thay vì
     *  `qs(params)` thẳng) — khuôn `danhSach()` ở trên: `params` là một INTERFACE có tên, TS không
     *  tự suy chữ ký chỉ mục cho nó khi truyền thẳng biến, chỉ literal tươi mới được. */
    kanban(token: string, params: TdsxThanhLocParams = {}): Promise<TdsxKanbanOut> {
      return authed<TdsxKanbanOut>(
        `/api/theo-doi-san-xuat/kanban${qs({
          q: params.q,
          khach_hang_id: params.khach_hang_id,
          may_id: params.may_id,
          nhom_cong_doan: params.nhom_cong_doan,
          cong_nhan_id: params.cong_nhan_id,
          trang_thai_viec: params.trang_thai_viec,
          uu_tien: params.uu_tien,
        })}`,
        token,
      );
    },
    /** MỘT lane mỗi máy CÒN DÙNG (kể cả rỗng) + lane "Chưa xếp máy" — máy chủ sắp "Chưa xếp máy"
     *  đứng CUỐI; FE (component Theo máy) tự đảo lên ĐẦU (Ruling C129, không sửa ở đây).
     *
     *  KHÔNG gửi `tu`/`den`: 17b vẽ "backlog trọn đời" (mọi việc chưa hoàn thành), đúng hành vi
     *  mặc định của máy chủ khi vắng cửa sổ — cửa sổ ngày là việc của một bản sau nếu cần. */
    theoMay(token: string, params: TdsxThanhLocParams = {}): Promise<TdsxTheoMayOut> {
      return authed<TdsxTheoMayOut>(
        `/api/theo-doi-san-xuat/theo-may${qs({
          q: params.q,
          khach_hang_id: params.khach_hang_id,
          may_id: params.may_id,
          nhom_cong_doan: params.nhom_cong_doan,
          cong_nhan_id: params.cong_nhan_id,
          trang_thai_viec: params.trang_thai_viec,
          uu_tien: params.uu_tien,
        })}`,
        token,
      );
    },
    /** Công việc theo TỪNG CA của một ngày xưởng (Task 18b). `ngay` vắng mặt ⇒ máy chủ tự lấy "hôm
     *  nay" theo GIỜ XƯỞNG (không phải giờ UTC của trình duyệt) — FE vẫn nên gửi tường minh để nút
     *  "Hôm nay"/đổi ngày qua lại có một giá trị chắc chắn để hiện, xem `TdsxTheoCa.tsx`. */
    theoCa(token: string, params: TdsxTheoCaParams = {}): Promise<TdsxTheoCaOut> {
      return authed<TdsxTheoCaOut>(
        `/api/theo-doi-san-xuat/theo-ca${qs({
          q: params.q,
          khach_hang_id: params.khach_hang_id,
          may_id: params.may_id,
          nhom_cong_doan: params.nhom_cong_doan,
          cong_nhan_id: params.cong_nhan_id,
          trang_thai_viec: params.trang_thai_viec,
          uu_tien: params.uu_tien,
          ngay: params.ngay,
          ca_id: params.ca_id,
        })}`,
        token,
      );
    },
    /** MỘT trang, MỘT dòng mỗi lệnh (Task 18b, Ruling C118). Lọc + đếm `total` + cắt trang đều Ở
     *  MÁY CHỦ — không `rows.slice`, không `rows.filter`; đổi trang phải gọi lại hàm này. */
    gantt(token: string, params: TdsxGanttParams = {}): Promise<TdsxGanttOut> {
      return authed<TdsxGanttOut>(
        `/api/theo-doi-san-xuat/gantt${qs({
          q: params.q,
          khach_hang_id: params.khach_hang_id,
          may_id: params.may_id,
          nhom_cong_doan: params.nhom_cong_doan,
          cong_nhan_id: params.cong_nhan_id,
          trang_thai_viec: params.trang_thai_viec,
          uu_tien: params.uu_tien,
          page: params.page,
          page_size: params.page_size,
        })}`,
        token,
      );
    },
  },

  // --- Xếp lịch (module `xep_lich`) — bàn cấp LỆNH SẢN XUẤT ------------------
  // Ít đường hơn màn 2 đúng một bậc: KHÔNG có "đưa vào nháp", KHÔNG có `xem-truoc` (xem trước
  // chính là thanh trên lưới), KHÔNG có `kiem-phat-hanh` (màn này không chặn gì hết).
  xepLich: {
    /** Thẻ chờ xếp, lọc + cắt trang Ở MÁY CHỦ. `tong` là SAU lọc, không phải số dòng trả về. */
    hangCho(
      token: string,
      params: { tim?: string; trang?: number; moi_trang?: number } = {},
    ): Promise<XlHangCho> {
      const suffix = qs({
        tim: params.tim?.trim() || undefined,
        trang: params.trang ?? undefined,
        moi_trang: params.moi_trang ?? undefined,
      });
      return authed<XlHangCho>(`/api/xep-lich/hang-cho${suffix}`, token);
    },
    /** Lệnh CHẠM cửa sổ [tu, den] (YYYY-MM-DD). Hai mốc BẮT BUỘC — không có đường trải cả lịch sử. */
    lich(token: string, params: { tu: string; den: string }): Promise<XlLien> {
      return authed<XlLien>(`/api/xep-lich/lich${qs({ tu: params.tu, den: params.den })}`, token);
    },
    /** Panel dưới: thông tin thật của một lệnh + bảng công đoạn. Lệnh chưa xếp vẫn mở được. */
    chiTiet(token: string, lsxId: number): Promise<XlChiTiet> {
      return authed<XlChiTiet>(`/api/xep-lich/lenh/${lsxId}`, token);
    },
    /** So HAI phiên bản lịch đã phát hành, từng bước một. Dữ liệu chỉ có từ 10/09/2026 — phiên
     *  bản cũ hơn đọc ra dòng sống nên bảng sẽ nói "không đổi"; đó là đúng theo dữ liệu còn lại,
     *  không dựng lại được. */
    soSanhPhienBan(token: string, lsxId: number, a: number, b: number): Promise<XlSoSanh> {
      return authed<XlSoSanh>(`/api/xep-lich/lenh/${lsxId}/so-sanh${qs({ a, b })}`, token);
    },
    /** Đặt / dời giờ bắt đầu. `expectedUpdatedAt` là chốt chống ghi đè — bỏ trống khi đặt LẦN ĐẦU
     *  (kéo từ hàng chờ), có thì lệch một giây cũng ném ApiError 409 "người khác vừa dời".
     *  Mốc rơi ngoài giờ chạy KHÔNG bị chặn: server trượt vào đầu khoảng chạy gần nhất rồi trả
     *  `da_doi=true` + `thong_bao` — băng thông báo lấy từ đó, đừng tự đoán lại. */
    datMoc(
      token: string,
      lsxId: number,
      batDauAt: string,
      expectedUpdatedAt?: string | null,
    ): Promise<XlDong> {
      return authed<XlDong>(`/api/xep-lich/lenh/${lsxId}`, token, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bat_dau_at: batDauAt, expected_updated_at: expectedUpdatedAt ?? null }),
      });
    },
    /** Bỏ lịch — thẻ quay lại hàng chờ. Không đụng trạng thái lệnh. */
    xoaMoc(token: string, lsxId: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/xep-lich/lenh/${lsxId}`, token, { method: "DELETE" });
    },
    /** Phát hành xuống xưởng — BẤM LÀ ĐI, không hộp thoại xác nhận, không cửa gác. */
    phatHanh(token: string, lsxId: number): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(`/api/xep-lich/phat-hanh/${lsxId}`, token, { method: "POST" });
    },
    /** Thu hồi phát hành. BẮT gõ lý do (≥3 ký tự) — thiếu thì 400, đã có việc chạy thì 409. */
    thuHoi(token: string, lsxId: number, lyDo: string): Promise<{ ok: boolean }> {
      return authed<{ ok: boolean }>(
        `/api/xep-lich/phat-hanh/${lsxId}${qs({ ly_do: lyDo })}`, token, { method: "DELETE" },
      );
    },
    /** Gói đã thả xuống xưởng còn thu hồi được không (`cho_phep_thu_hoi`), hay chỉ còn đường cập
     *  nhật (`cho_phep_cap_nhat`). Hỏi TRƯỚC khi bày nút — không thì người dùng gõ lý do xong mới
     *  ăn 409. `co_goi=false` ⇒ lệnh chưa phát hành. */
    goiPhatHanh(token: string, lsxId: number): Promise<XlGoiPhatHanh> {
      return authed<XlGoiPhatHanh>(`/api/xep-lich/phat-hanh/${lsxId}/goi`, token);
    },
    /** Đẩy lịch mới xuống xưởng cho phần CHƯA bắt đầu, giữ nguyên việc đã chạy. BẮT gõ lý do
     *  (≥3 ký tự). `so_lech_phan_doan > 0` ⇒ có việc KHÔNG được cập nhật vì lần chạy đã tách/gộp
     *  lại — phải nói ra, đừng nuốt. */
    phatHanhCapNhat(token: string, lsxId: number, lyDo: string): Promise<XlCapNhatOut> {
      return authed<XlCapNhatOut>(`/api/xep-lich/phat-hanh-cap-nhat/${lsxId}`, token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ly_do: lyDo }),
      });
    },
  },

  // --- Thực hiện sản xuất (module `san_xuat`) — bàn của TỔ -------------------
  // Mặt ĐỌC (teams/workItems/chiTiet/nhanVienChon) + mặt GHI (phanCong/rut/batDau/tamDung/ketThuc).
  // Ghi trả `SxLenhKetQua` (version lạc quan). Lỗi: 400 = lệch version/ràng buộc → refetch + toast;
  // 403 = ngoài phạm vi tổ. `teams` một cú gọi ra cả list lẫn badge (`so_viec_cho`).
  sanXuat: {
    /** Danh sách tổ user thấy + badge số việc chờ (navbar + màn). */
    teams(token: string): Promise<SxTeamsOut> {
      return authed<SxTeamsOut>("/api/san-xuat/teams", token);
    },
    /** Nhân viên chọn được cho ô "Giao người" của MỘT tổ (gác `san_xuat:read`, KHÔNG dùng api.employees). */
    nhanVienChon(token: string, teamId: number): Promise<SxNhanVienChonListOut> {
      return authed<SxNhanVienChonListOut>(`/api/san-xuat/teams/${teamId}/nhan-vien`, token);
    },
    /** Ứng viên mời hỗ trợ chéo (§9) — thợ tổ khác. */
    hoTroUngVien(token: string, teamId: number): Promise<SxHoTroUngVienListOut> {
      return authed<SxHoTroUngVienListOut>(`/api/san-xuat/teams/${teamId}/ho-tro-ung-vien`, token);
    },
    /** Việc chờ tổ bấm: bàn giao đến + hỗ trợ chéo chờ bên tổ mình + lỗi KCS chưa xem. 403 nếu
     *  ngoài phạm vi. */
    choXacNhan(token: string, teamId: number): Promise<SxChoXacNhan> {
      return authed<SxChoXacNhan>(`/api/san-xuat/teams/${teamId}/cho-xac-nhan`, token);
    },
    /** Việc đã phát hành của MỘT tổ. 403 nếu tổ ngoài phạm vi.
     *
     *  `nhom="lenh"` (mặc định của BE) trả ĐẦU MỤC LỆNH/BÀI GHÉP kèm phân trang ĐẾM THEO LỆNH —
     *  dùng cho view Thẻ và Danh sách. `nhom="phang"` giữ mảng bước phẳng cho Gantt, kèm cửa sổ
     *  `tuNgay`/`denNgay` để chỉ kéo đúng khoảng đang xem. `choXacNhan` = chỉ lệnh có công đoạn
     *  đang chờ tổ bấm (lọc trước khi cắt trang). */
    workItems(token: string, p: {
      teamId: number;
      nhom?: "lenh" | "phang";
      tim?: string;
      trang?: number;
      coTrang?: number;
      tuNgay?: string;
      denNgay?: string;
      choXacNhan?: boolean;
      /** Lọc nâng cao (view Bảng) — máy chủ lọc TRƯỚC khi cắt trang. */
      trangThai?: string[];
      nhanTu?: string;
      nhanDen?: string;
      sapXep?: "moi_nhan" | "cu_nhan" | "du_kien";
    }): Promise<SxWorkItemsOut> {
      const suffix = qs({
        team_id: p.teamId, nhom: p.nhom, tim: p.tim,
        trang: p.trang, co_trang: p.coTrang, tu_ngay: p.tuNgay, den_ngay: p.denNgay,
        cho_xac_nhan: p.choXacNhan || undefined,
        nhan_tu: p.nhanTu, nhan_den: p.nhanDen, sap_xep: p.sapXep,
      });
      // `trang_thai` là list ở backend → lặp param, KHÔNG nối bằng dấu phẩy.
      const tt = (p.trangThai ?? []).map((s) => `trang_thai=${encodeURIComponent(s)}`).join("&");
      const url = tt ? `${suffix}${suffix ? "&" : "?"}${tt}` : suffix;
      return authed<SxWorkItemsOut>(`/api/san-xuat/work-items${url}`, token);
    },
    /** Luỹ kế sản lượng tháng của CHÍNH mình. KHÔNG truyền `employee_id` — BE luôn suy từ token,
     *  truyền được là ai cũng xem được sản lượng người khác bằng cách đổi một số trên URL. */
    sanLuongCuaToi(token: string, nam: number, thang: number): Promise<SxSanLuongCuaToi> {
      return authed<SxSanLuongCuaToi>(
        `/api/san-xuat/toi/san-luong${qs({ nam, thang })}`, token);
    },
    /** Tab Sản lượng của bàn tổ: lệnh → công đoạn → người; lọc · phân trang · tổng ở máy chủ. */
    sanLuongTo(token: string, loc: SxSanLuongToLoc): Promise<SxSanLuongTo> {
      return authed<SxSanLuongTo>(`/api/san-xuat/san-luong${qs({
        team_id: loc.team_id, tu: loc.tu || undefined, den: loc.den || undefined,
        to_id: loc.to_id ?? undefined, tim: loc.tim?.trim() || undefined,
        trang: loc.trang, co_trang: loc.co_trang,
      })}`, token);
    },
    /** Drawer một công việc: thanh kế hoạch + roster + phiên chạy + khoảng tham gia. */
    chiTiet(token: string, congViecId: number): Promise<SxWorkItemChiTiet> {
      return authed<SxWorkItemChiTiet>(`/api/san-xuat/work-items/${congViecId}`, token);
    },
    /** Tệp Kế hoạch SX đính kèm vào lệnh của công việc — tổ xem/tải, không sửa. Gói thu hồi → 404. */
    tepLenh(token: string, congViecId: number): Promise<SxTepLenhNhom[]> {
      return authed<{ nhom: SxTepLenhNhom[] }>(`/api/san-xuat/work-items/${congViecId}/tep-lenh`, token)
        .then((r) => r.nhom);
    },
    /** Giao MỘT người vào công việc. Lần giao đầu = tổ tiếp nhận. */
    phanCong(token: string, congViecId: number, body: SxPhanCongIn): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/work-items/${congViecId}/phan-cong`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Rút một người khỏi công việc (đóng khoảng tham gia đang mở của họ). */
    rut(token: string, phanCongId: number, body: SxGoPhanCongIn): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/phan-cong/${phanCongId}/rut`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Bắt đầu / tiếp tục chạy: mở phiên mới + khoảng tham gia. Không hỏi lý do gì (kíp chuẩn gỡ ở mg `0321`; sớm/trễ không hỏi). */
    batDau(token: string, congViecId: number, body: SxBatDauIn): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/work-items/${congViecId}/bat-dau`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Tổ xác nhận đã cầm con dao trong tay — thứ DUY NHẤT mở cổng Bắt đầu cho bước cần dụng cụ.
     *  Tích một lần, không gỡ được: gỡ ra thì mốc "ai nói dao đã ở đây, lúc mấy giờ" mất nghĩa. */
    nhanKhuon(token: string, congViecId: number): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/work-items/${congViecId}/nhan-khuon`, token, {
        method: "POST",
      });
    },
    /** Trả dao về kệ — KHÔNG chặn gì, chỉ để hệ thống khỏi mất dấu con dao sau khi nó rời kệ. */
    traKhuon(token: string, congViecId: number): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/work-items/${congViecId}/tra-khuon`, token, {
        method: "POST",
      });
    },
    /** Đổi máy giữa chừng (§7.2 mở rộng 31/08/2026). CHẠY → đóng phiên máy cũ + mở phiên mới
     *  CÙNG mốc (giờ máy cũ không mất); TẠM DỪNG → chỉ đổi máy phân công, không mở phiên. */
    doiMay(token: string, congViecId: number, body: SxDoiMayIn): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/work-items/${congViecId}/doi-may`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Máy đổi sang được cho ô "Đổi máy" + tình trạng từng máy lúc gọi. Gọi mỗi lần mở ô. */
    mayDoi(token: string, congViecId: number): Promise<SxMayDoiOut> {
      return authed<SxMayDoiOut>(`/api/san-xuat/work-items/${congViecId}/may-doi`, token);
    },
    /** Tạm dừng: đóng phiên + khoảng tham gia. `ly_do` BẮT BUỘC. */
    tamDung(token: string, congViecId: number, body: SxTamDungIn): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/work-items/${congViecId}/tam-dung`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Báo sự cố máy ngay tại tổ (31/08/2026): ghi vào hộp thư "Báo máy hỏng" của tổ sửa chữa,
     *  kèm neo về công việc/lệnh. `dung_san_xuat` → công việc chuyển Tạm dừng + đóng phiên máy
     *  trong CÙNG một giao dịch; "Vẫn chạy" → chỉ gửi yêu cầu, đồng hồ máy không dừng. */
    baoSuCo(token: string, congViecId: number, body: SxSuCoIn): Promise<SxSuCoKetQua> {
      return authed<SxSuCoKetQua>(`/api/san-xuat/work-items/${congViecId}/su-co`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Kết thúc: đóng phiên + khoảng tham gia, đánh dấu hoàn thành. Không hỏi lý do sớm/trễ. */
    ketThuc(token: string, congViecId: number, body: SxKetThucIn): Promise<SxLenhKetQua> {
      return authed<SxLenhKetQua>(`/api/san-xuat/work-items/${congViecId}/ket-thuc`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },

    // --- Giai đoạn 3: sản lượng · bàn giao · vật tư ---------------------------------------
    /** Ghi MỘT mẻ sản lượng (tổng = tốt + hỏng; hỏng chỉ ghi kèm mô tả tự do, tuỳ chọn). */
    taoBatch(token: string, congViecId: number, body: SxBatchIn): Promise<SxSanLuongKetQua> {
      return authed<SxSanLuongKetQua>(`/api/san-xuat/work-items/${congViecId}/outputs`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Băng "Danh mục đã đổi" của mẻ (§7.2b): bấm thì ảnh chụp lấy số MỚI. Không bấm = giữ số cũ. */
    capNhatDanhMucMe(token: string, batchId: number): Promise<SxSanLuongKetQua> {
      return authed<SxSanLuongKetQua>(`/api/san-xuat/outputs/${batchId}/cap-nhat-danh-muc`, token, {
        method: "POST", body: JSON.stringify({}),
      });
    },
    /** Thêm một lot đầu vào cho mẻ đã ghi (truy vết §10.3). */
    themLot(token: string, batchId: number, body: SxLotVaoIn): Promise<SxSanLuongKetQua> {
      return authed<SxSanLuongKetQua>(`/api/san-xuat/outputs/${batchId}/inputs`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Đề xuất bàn giao cho chặng sau. Bước cuối lệnh không bàn giao; cùng tổ+LSX = tự xác nhận. */
    deXuatBanGiao(token: string, congViecId: number, body: SxBanGiaoDeXuatIn): Promise<SxBanGiaoKetQua> {
      return authed<SxBanGiaoKetQua>(`/api/san-xuat/work-items/${congViecId}/handovers`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Sửa số lượng đề xuất (chỉ khi còn proposed, gác tổ NGUỒN). */
    suaBanGiao(token: string, banGiaoId: number, body: SxBanGiaoSuaIn): Promise<SxBanGiaoKetQua> {
      return authed<SxBanGiaoKetQua>(`/api/san-xuat/handovers/${banGiaoId}/sua`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Xác nhận đã nhận (gác tổ ĐÍCH). */
    xacNhanBanGiao(token: string, banGiaoId: number, body: SxBanGiaoXacNhanIn): Promise<SxBanGiaoKetQua> {
      return authed<SxBanGiaoKetQua>(`/api/san-xuat/handovers/${banGiaoId}/xac-nhan`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Điều chỉnh số lượng sau khi đã nhận (cần lý do; cờ không-nhất-quán nếu giảm dưới đã tiêu). */
    dieuChinhBanGiao(token: string, banGiaoId: number, body: SxBanGiaoDieuChinhIn): Promise<SxBanGiaoKetQua> {
      return authed<SxBanGiaoKetQua>(`/api/san-xuat/handovers/${banGiaoId}/dieu-chinh`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Xác nhận đã nhận đủ vật tư của một phiếu xuất. */
    xacNhanVatTu(token: string, body: SxVatTuXacNhanIn): Promise<SxVatTuNhanKetQua> {
      return authed<SxVatTuNhanKetQua>(`/api/san-xuat/stock/xac-nhan`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Tổ gửi MỘT lần đề nghị cấp vật tư cho công đoạn (lần đầu hoặc bổ sung). 400 = vi phạm
     *  nghiệp vụ (câu tiếng Việt trong `detail` — hiện NGUYÊN VĂN); 403 = không phải tổ trưởng
     *  đúng tổ; 404 = không thấy công việc. */
    deNghiVatTu(token: string, congViecId: number, body: SxVatTuDeNghiIn): Promise<SxVatTuDeNghiKetQua> {
      return authed<SxVatTuDeNghiKetQua>(`/api/san-xuat/work-items/${congViecId}/material-requests`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Sửa một lần đề nghị CHƯA bị kho lập phiếu. `deNghiId` là id ĐỀ NGHỊ SẢN XUẤT (không phải
     *  id yêu cầu kho — hai không gian id khác nhau). Thân dòng THAY THẾ toàn bộ dòng của lần đó. */
    suaDeNghiVatTu(
      token: string, congViecId: number, deNghiId: number, body: SxVatTuDeNghiIn,
    ): Promise<SxVatTuDeNghiKetQua> {
      return authed<SxVatTuDeNghiKetQua>(
        `/api/san-xuat/work-items/${congViecId}/material-requests/${deNghiId}`, token,
        { method: "PUT", body: JSON.stringify(body) },
      );
    },

    // --- Giai đoạn 4: hỗ trợ chéo · phân bổ ------------------------------------------------
    /** Đề xuất hỗ trợ chéo: một thợ tổ khác làm giúp %; cần 2 tổ trưởng xác nhận. */
    deXuatHoTro(token: string, congViecId: number, body: SxHoTroDeXuatIn): Promise<SxHoTroKetQua> {
      return authed<SxHoTroKetQua>(`/api/san-xuat/work-items/${congViecId}/ho-tro`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Xác nhận thỏa thuận hỗ trợ (mỗi tổ trưởng gật một lần). */
    xacNhanHoTro(token: string, hoTroId: number, body: SxHoTroXacNhanIn): Promise<SxHoTroKetQua> {
      return authed<SxHoTroKetQua>(`/api/san-xuat/ho-tro/${hoTroId}/xac-nhan`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /** Hủy thỏa thuận hỗ trợ. */
    huyHoTro(token: string, hoTroId: number, body: SxHoTroHuyIn): Promise<SxHoTroKetQua> {
      return authed<SxHoTroKetQua>(`/api/san-xuat/ho-tro/${hoTroId}/huy`, token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    /* SÁU API PHÂN BỔ (`tinhPhanBo` · `chotPhanBo` · `moLaiPhanBo` · `buTru` · `loaiTru` ·
       `goLoaiTru`) GỠ 18/09/2026 cùng tầng chia sản lượng (mg `0322`). Sản xuất chỉ GHI NHẬN số
       lượng của mẻ; chia cho từng người là việc của kế toán về sau. */

    // --- KCS theo LỆNH (mg 0306) -----------------------------------------------------------
    /** Danh sách lệnh cho màn KCS — tìm + cắt trang ở máy chủ. Mặc định chỉ nhóm còn mở. */
    kcsLenh(token: string, p: { tim?: string; trang?: number; daDong?: boolean } = {}): Promise<SxKcsLenhList> {
      return authed<SxKcsLenhList>(`/api/san-xuat/kcs/lenh${qs({
        tim: p.tim?.trim() || undefined, trang: p.trang, da_dong: p.daDong || undefined,
      })}`, token);
    },
    /** Chuỗi công đoạn của MỘT lệnh theo thứ tự routing + các lần kiểm. 403 nếu không phải người KCS. */
    kcsChuoiCongDoan(token: string, lsxId: number): Promise<SxKcsChuoiCongDoan> {
      return authed<SxKcsChuoiCongDoan>(`/api/san-xuat/kcs/lenh/${lsxId}`, token);
    },
    /** Mục "Kết quả KCS" của một công đoạn — người KCS xem mọi công đoạn, tổ xem theo phạm vi Xem. */
    kcsCongViec(token: string, congViecId: number): Promise<SxKcsCongViec> {
      return authed<SxKcsCongViec>(`/api/san-xuat/work-items/${congViecId}/kcs`, token);
    },
    /** Ghi MỘT lần kiểm công đoạn — multipart vì lỗi đi kèm ảnh. Tổ chịu = tổ của công đoạn, người
     *  kiểm = tài khoản đăng nhập (server chốt, không gửi lên). */
    kiemCongDoan(token: string, congViecId: number, body: SxKcsKiemIn): Promise<SxKcsKiemKetQua> {
      const fd = new FormData();
      if (body.so_dat != null) fd.append("so_dat", String(body.so_dat));
      fd.append("so_loi", String(body.so_loi));
      if (body.checklist?.length) fd.append("checklist_json", JSON.stringify(body.checklist));
      if (body.ghi_chu) fd.append("ghi_chu", body.ghi_chu);
      if (body.lsx_id != null) fd.append("lsx_id", String(body.lsx_id));
      if (body.loi) {
        // Ảnh của mọi dòng nối liền theo thứ tự dòng; `so_anh` cho máy chủ cắt lại đúng dòng.
        fd.append("loi_json", JSON.stringify(body.loi.map((d) => ({
          cong_viec_id: d.cong_viec_id, so_luong: d.so_luong, mo_ta: d.mo_ta, so_anh: d.files.length,
        }))));
        for (const d of body.loi) for (const f of d.files) fd.append("files", f);
      } else {
        if (body.loi_mo_ta) fd.append("loi_mo_ta", body.loi_mo_ta);
        for (const f of body.files ?? []) fd.append("files", f);
      }
      return authed<SxKcsKiemKetQua>(`/api/san-xuat/kcs/cong-viec/${congViecId}/kiem`, token, {
        method: "POST", body: fd,
      });
    },
    /** Tổ bị báo lỗi bấm "Đã xem" — gác Xác nhận sản lượng trọn tổ đó. */
    daXemLoiKcs(token: string, loiId: number): Promise<SxKcsDaXemKetQua> {
      return authed<SxKcsDaXemKetQua>(`/api/san-xuat/kcs/loi/${loiId}/da-xem`, token, {
        method: "POST",
      });
    },
    /** Điều chỉnh một lần kiểm đã ghi — không xoá, ghi audit trước/sau. */
    dieuChinhKcs(token: string, kcsBatchId: number, body: SxKcsDieuChinhIn): Promise<SxKcsDieuChinhKetQua> {
      return authed<SxKcsDieuChinhKetQua>(`/api/san-xuat/kcs/${kcsBatchId}`, token, {
        method: "PATCH", body: JSON.stringify(body),
      });
    },
    /** "Tạo yêu cầu nhập kho" trên công đoạn cuối nhóm — server tự tính phần đạt chưa gửi (trần =
     *  min(Σ đạt, Σ tốt) − đã đề nghị), không nhận số từ client; đẻ MỘT yêu cầu NHẬP thật (DNN…) chờ kho
     *  nhận ở Hộp yêu cầu. 409 nếu không còn gì để gửi. */
    taoYeuCauNhapKhoCongDoan(token: string, congViecId: number): Promise<SxNhapKhoYcKetQua> {
      return authed<SxNhapKhoYcKetQua>(`/api/san-xuat/kcs/cong-viec/${congViecId}/yeu-cau-nhap-kho`, token, {
        method: "POST",
      });
    },
    /** Danh mục công đoạn cho ô lọc dashboard KCS — đọc dưới quyền Xem theo tổ, không đòi quyền
     *  Danh mục công đoạn như `api.congDoan.list`. */
    kcsCongDoanLoc(token: string): Promise<{ items: SxKcsCongDoanLoc[] }> {
      return authed<{ items: SxKcsCongDoanLoc[] }>(`/api/san-xuat/kcs/cong-doan`, token);
    },
    /** Báo cáo/dashboard KCS theo bộ lọc (§5.7, §6.2) — KPI + 3 biểu đồ. */
    baoCaoKcs(token: string, params: SxKcsBaoCaoParams = {}): Promise<SxKcsBaoCao> {
      return authed<SxKcsBaoCao>(`/api/san-xuat/kcs/bao-cao${qs({ ...params })}`, token);
    },
    /** Xuất Excel báo cáo KCS — CÙNG filter với `baoCaoKcs` (§9 mục 10: cùng lọc phải ra cùng tổng). */
    exportBaoCaoKcsBlobUrl(token: string, params: SxKcsBaoCaoParams = {}): Promise<string> {
      return blobUrl(`/api/san-xuat/kcs/bao-cao/export.xlsx${qs({ ...params })}`, token);
    },

    /* Hộp thư / xác nhận nhập kho thành phẩm riêng của sản xuất GỠ 17/09/2026 — kho nhận ở Hộp yêu
       cầu của module Kho (`api.kho`), như mọi yêu cầu nhập khác. */

    // --- Giai đoạn 5: Đóng nhóm §16 + đóng thiếu §13.3 ------------------------------------
    /* `thuongToTruongNhom()` GỠ 11/09/2026 cùng route `/kho/nhom/{id}/thuong-to-truong`. */
    /** Checklist điều kiện đóng nhóm thành phẩm (đủ / thiếu). */
    dieuKienDongNhom(token: string, nhomId: number): Promise<SxDongNhomDieuKien> {
      return authed<SxDongNhomDieuKien>(`/api/san-xuat/kho/nhom/${nhomId}/dieu-kien-dong`, token);
    },
    /** Trưởng KCS đóng thiếu nhóm kèm lý do (§13.3). */
    dongThieu(token: string, nhomId: number, body: SxDongThieuIn): Promise<SxDongNhomKetQua> {
      return authed<SxDongNhomKetQua>(`/api/san-xuat/kho/nhom/${nhomId}/dong-thieu`, token, {
        method: "POST", body: JSON.stringify(body),
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
    // --- Ảnh minh họa in cho khách (cột "Hình ảnh minh họa" của bản in) ---
    // Gắn theo CỤM: gọi với 1 dòng bất kỳ trong cụm, backend ghi cho mọi dòng cùng tên.
    uploadItemImage(token: string, id: number, itemId: number, file: File): Promise<QuoteItemImage> {
      const form = new FormData();
      form.append("file", file);
      return authed<QuoteItemImage>(`/api/quotations/${id}/items/${itemId}/anh-minh-hoa`, token, {
        method: "POST",
        body: form,
      });
    },
    deleteItemImage(token: string, id: number, itemId: number): Promise<void> {
      return authed<void>(`/api/quotations/${id}/items/${itemId}/anh-minh-hoa`, token, {
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
    /** Tiến độ đơn cho Kinh doanh — SX → Nhập kho → Giao hàng, gộp theo cụm bán (19/09/2026). */
    tienDo(token: string, id: number): Promise<DonTienDo> {
      return authed<DonTienDo>(`/api/orders/${id}/tien-do`, token);
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
      params: {
        q?: string;
        status?: string | null;
        supplier_group?: string | null;
        /** Chỉ lấy NCC có sao trung bình ≥ mức này. NCC "Chưa đánh giá" rơi ra khỏi kết quả. */
        rating_min?: number | null;
        /** `rating` / `-rating` xếp theo sao — NCC chưa đánh giá luôn nằm CUỐI ở cả hai chiều. */
        sort?: string;
        page?: number;
        size?: number;
      } = {},
    ): Promise<SupplierListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.supplier_group) qs.set("supplier_group", params.supplier_group);
      if (params.rating_min != null) qs.set("rating_min", String(params.rating_min));
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
    /** Bỏ MỘT MÓN khỏi yêu cầu, giữ nguyên các món còn lại (mg 0233). Lý do BẮT BUỘC (422 nếu
        trống). Món đang nằm ở đơn mua còn sống → 409 kèm câu chỉ đúng đơn phải xử lý trước. */
    cancelLine(
      token: string,
      id: number,
      lineId: number,
      reason: string,
    ): Promise<DepartmentPurchaseRequestRow> {
      return authed<DepartmentPurchaseRequestRow>(
        `/api/department-purchase-requests/${id}/lines/${lineId}/cancel`,
        token,
        { method: "POST", body: JSON.stringify({ reason }) },
      );
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
      params: {
        q?: string;
        filter?: string;
        /** Khoá rổ tuổi — lọc danh sách theo rổ. Tên tham số PHẢI là `aging_bucket`, hai màn
         *  dùng chung một tên để chép URL qua lại vẫn chạy. */
        aging?: string | null;
        page?: number;
        size?: number;
      } = {},
    ): Promise<PayablesSummary> {
      const qs = new URLSearchParams();
      if (params.q?.trim()) qs.set("q", params.q.trim());
      if (params.filter && params.filter !== "all") qs.set("filter", params.filter);
      if (params.aging) qs.set("aging_bucket", params.aging);
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
      params: {
        q?: string;
        filter?: string;
        /** Khoá rổ tuổi — lọc danh sách theo rổ. Tên tham số PHẢI là `aging_bucket`, hai màn
         *  dùng chung một tên để chép URL qua lại vẫn chạy. */
        aging?: string | null;
        page?: number;
        size?: number;
      } = {},
    ): Promise<ReceivablesSummary> {
      const qs = new URLSearchParams();
      if (params.q?.trim()) qs.set("q", params.q.trim());
      if (params.filter && params.filter !== "all") qs.set("filter", params.filter);
      if (params.aging) qs.set("aging_bucket", params.aging);
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
    /** SỔ TỔNG HỢP CÔNG NỢ theo kỳ. `ben` = "receivables" (131) | "payables" (331). */
    baoCaoCongNo(
      token: string,
      ben: "receivables" | "payables",
      params: { tuNgay: string; denNgay: string; roTuoi?: string | null },
    ): Promise<BaoCaoCongNo> {
      const qs = new URLSearchParams({
        tu_ngay: params.tuNgay,
        den_ngay: params.denNgay,
      });
      if (params.roTuoi) qs.set("aging_bucket", params.roTuoi);
      return authed<BaoCaoCongNo>(
        `/api/accounting/reports/${ben}?${qs.toString()}`,
        token,
      );
    },
    /** SỔ CHI TIẾT CÔNG NỢ của MỘT đối tượng — từng chứng từ + luỹ kế (PRD §5.1).
     *
     *  `doiTuongId = null` KHÔNG phải "lấy tất cả" mà là dòng gom các khoản không truy được về
     *  khách/NCC nào — đúng dòng "(Thu khác…)" / "(Chi khác…)" ở sổ tổng hợp. */
    soChiTietCongNo(
      token: string,
      ben: "receivables" | "payables",
      params: { doiTuongId: number | null; tuNgay: string; denNgay: string },
    ): Promise<SoChiTietCongNo> {
      const qs = new URLSearchParams({
        tu_ngay: params.tuNgay,
        den_ngay: params.denNgay,
      });
      if (params.doiTuongId != null) qs.set("doi_tuong_id", String(params.doiTuongId));
      return authed<SoChiTietCongNo>(
        `/api/accounting/reports/${ben}/so-chi-tiet?${qs.toString()}`,
        token,
      );
    },
    /** File .xlsx đúng khuôn MISA. Phải fetch kèm bearer rồi dựng blob — thẻ `<a href>` trần
     *  không mang token đi được, và cửa này có kiểm quyền. */
    async baoCaoCongNoXlsx(
      token: string,
      ben: "receivables" | "payables",
      params: { tuNgay: string; denNgay: string },
    ): Promise<{ url: string; ten: string }> {
      const qs = new URLSearchParams({
        tu_ngay: params.tuNgay,
        den_ngay: params.denNgay,
      });
      const duong = `${BASE_URL}/api/accounting/reports/${ben}.xlsx?${qs.toString()}`;
      const doFetch = (bearer: string) =>
        fetch(duong, {
          credentials: "include",
          cache: "no-store",
          headers: authHeader(bearer),
        });
      let resp = await doFetch(token);
      if (resp.status === 401) {
        const fresh = await refreshAccessToken();
        if (fresh) resp = await doFetch(fresh);
      }
      if (!resp.ok) throw new ApiError(`Không xuất được file (${resp.status}).`, resp.status);
      // Tên file do SERVER đặt (có kỳ trong tên) — đọc lại từ header thay vì tự bịa ở đây, để
      // hai nơi không đặt hai kiểu tên cho cùng một file.
      const cd = resp.headers.get("content-disposition") ?? "";
      const khop = /filename="([^"]+)"/.exec(cd);
      return {
        url: URL.createObjectURL(await resp.blob()),
        ten: khop ? khop[1] : `tong-hop-cong-no-${ben}.xlsx`,
      };
    },
    /** `phanHe` = "phai_thu" (131) | "phai_tra" (331). Hai sổ ĐỘC LẬP — chốt sổ mua hàng không
     *  được kéo theo sổ bán hàng (sửa 04/09/2026). */
    congNoKyList(token: string, phanHe: "phai_thu" | "phai_tra"): Promise<CongNoKyRow[]> {
      return authed<CongNoKyRow[]>(`/api/accounting/khoa-so/ky?phan_he=${phanHe}`, token);
    },
    /** Khoảng này đang khóa trọn / khóa một phần / chưa khóa? */
    congNoKhoaSoTrangThai(
      token: string,
      params: { tuNgay: string; denNgay: string; phanHe: "phai_thu" | "phai_tra" },
    ): Promise<CongNoKhoaSoTrangThai> {
      const qs = new URLSearchParams({
        tu_ngay: params.tuNgay,
        den_ngay: params.denNgay,
        phan_he: params.phanHe,
      });
      return authed<CongNoKhoaSoTrangThai>(
        `/api/accounting/khoa-so/trang-thai?${qs.toString()}`,
        token,
      );
    },
    congNoKhoaSoHistory(token: string): Promise<CongNoKhoaSoRow[]> {
      return authed<CongNoKhoaSoRow[]>("/api/accounting/khoa-so", token);
    },
    setCongNoKhoaSo(
      token: string,
      payload: {
        /** BẮT BUỘC. Khoá sổ 331 không được kéo theo 131. */
        phan_he: "phai_thu" | "phai_tra";
        tu_ngay: string;
        den_ngay: string;
        hanh_dong: "khoa" | "mo";
        ten?: string | null;
      },
    ): Promise<CongNoKhoaSoRow> {
      return authed<CongNoKhoaSoRow>("/api/accounting/khoa-so", token, {
        method: "POST",
        body: JSON.stringify(payload),
      });
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
    /** MỌI phiếu chi lập từ phiếu tạm ứng lương (kể cả phiếu đã huỷ) — màn Tạm ứng bên Lương
     *  map lại theo `salary_advance_id` để biết dòng nào đã chi.
     *
     *  `GET /api/luong/advances` CHƯA trả cờ "đã có phiếu chi", nên FE phải tự đối chiếu. Đọc
     *  theo trang 200 (trần của backend), tối đa `maxPages` trang: một màn xem theo THÁNG không
     *  đáng gọi hàng chục lượt. Nếu số phiếu vượt trần thì phiếu CŨ NHẤT không có chip — bấm
     *  "Lập phiếu chi" vẫn an toàn vì backend trả 409 kèm mã phiếu chi đã lập.
     *  Cần đúng một lượt gọi: xin backend trả thẳng `payment_voucher_code` trong danh sách tạm ứng. */
    async salaryAdvanceVouchers(token: string, maxPages = 5): Promise<PaymentVoucherRow[]> {
      const rows: PaymentVoucherRow[] = [];
      for (let page = 1; page <= maxPages; page += 1) {
        const resp = await api.accounting.vouchers(token, {
          source_type: "salary_advance",
          sort: "-created_at",
          page,
          size: 200,
        });
        rows.push(...resp.items);
        if (resp.items.length === 0 || rows.length >= resp.total) break;
      }
      return rows;
    },
    createVoucher(token: string, input: PaymentVoucherInput): Promise<PaymentVoucherRow> {
      return authed<PaymentVoucherRow>("/api/accounting/payment-vouchers", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** Thanh toán NHIỀU đợt giao của CÙNG một NCC trong MỘT lượt (04/09/2026). Vẫn ra N phiếu
     *  chi riêng — server lặp lại đúng đường kiểm/lập của `createVoucher` cho từng đợt, batch
     *  chỉ gộp thao tác nhập liệu (hình thức chi + tài khoản/người nhận điền một lần). */
    createVouchersBatch(
      token: string,
      input: VoucherBatchInput,
    ): Promise<VoucherBatchResult> {
      return authed<VoucherBatchResult>("/api/accounting/payment-vouchers/batch", token, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    /** Lập phiếu chi TỪ một phiếu tạm ứng lương ĐÃ DUYỆT (chủ chốt 18/08/2026). Dùng ở tab Tạm ứng
     *  bên màn Lương — kế toán bấm TAY, KHÔNG tự sinh lúc duyệt tạm ứng (từ 04/08/2026 hệ này
     *  tách "người đồng ý chi" khỏi "người viết phiếu chi", đừng gộp lại).
     *
     *  Cùng endpoint với phiếu chi mua hàng, chỉ khác ở `salary_advance_id`. Bốn khoá cứng dưới
     *  đây do luồng quy định, không phải ô cho người dùng chọn:
     *    • `source_type` = salary_advance   • `payment_stage` = other (không có "đợt" nào)
     *    • VND + tỷ giá 1 (lương trả nội tệ)
     *  Phiếu sinh ra là `paid` NGAY — lập phiếu chi = tiền đã ra, không có bước "chờ chi".
     *
     *  Lỗi: 409 = tạm ứng ĐÃ có phiếu chi · 422 = tạm ứng chưa duyệt / thiếu ô / ngày tương lai ·
     *  404 = không tìm thấy. `detail` là câu tiếng Việt đầy đủ — hiện NGUYÊN CÂU cho người dùng. */
    createVoucherFromAdvance(
      token: string,
      input: SalaryAdvanceVoucherInput,
    ): Promise<PaymentVoucherRow> {
      return api.accounting.createVoucher(token, {
        ...input,
        source_type: "salary_advance",
        payment_stage: "other",
        currency: "VND",
        exchange_rate: 1,
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

  // --- Hạng mục kiểm KCS (danh mục, khai theo cây Giai đoạn → Công đoạn → hạng mục) --------
  // Nền CRUD chung `/api/san-xuat-kcs-tieu-chi` (POST "" · PUT /{id} · DELETE /{id}), thêm
  // `GET /khai-bao` trả sẵn ba tầng để màn không phải tự ghép. `ma` server cấp — không gửi.
  kcsHangMuc: {
    khaiBao(token: string): Promise<KcsKhaiBao> {
      return authed<KcsKhaiBao>(
        "/api/san-xuat-kcs-tieu-chi/khai-bao", token,
      );
    },
    tao(token: string, body: KcsHangMucBody): Promise<KcsHangMuc> {
      return authed<KcsHangMuc>("/api/san-xuat-kcs-tieu-chi", token, {
        method: "POST", body: JSON.stringify(body),
      });
    },
    sua(token: string, id: number, body: KcsHangMucBody): Promise<KcsHangMuc> {
      return authed<KcsHangMuc>(`/api/san-xuat-kcs-tieu-chi/${id}`, token, {
        method: "PUT", body: JSON.stringify(body),
      });
    },
    xoa(token: string, id: number): Promise<void> {
      return authed<void>(`/api/san-xuat-kcs-tieu-chi/${id}`, token, { method: "DELETE" });
    },
  },

  // --- Công đoạn (danh mục, lite cho dropdown) -----------------------------
  congDoan: {
    // size ≤ 200 — router chặn `le=200`, gửi 500 là 422 (đừng nâng lại).
    // `active=true` — chỉ đổ công đoạn ĐANG DÙNG vào các ô chọn (tính giá + lệnh SX). Món đã
    // "Ngừng dùng" (active=false) phải BIẾN khỏi dropdown đúng như hộp thoại ngừng-dùng hứa;
    // không truyền cờ này thì backend trả CẢ món đã ngừng (repo lọc `if active is not None`).
    // Bước lệnh SX đang lỡ dùng món đã ngừng vẫn hiện đúng: drawer tự ghim lại option đó.
    list(token: string): Promise<{ items: CongDoanLite[] }> {
      return authed<{ items: CongDoanLite[] }>("/api/cong-doan?size=200&active=true", token);
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
      ): Promise<{ nhap: number; xuat: number; dieu_chuyen: number; done_unseen: number; fail_unseen: number }> {
        return authed("/api/kho/de-nghi/counts", token);
      },
      /** NGƯỜI TẠO mở xem 1 yêu cầu của mình → đánh dấu đã xem → hạ badge/số đỏ đúng yêu cầu đó. */
      markSeen(token: string, id: number): Promise<void> {
        return authed(`/api/kho/de-nghi/${id}/seen`, token, { method: "POST" });
      },
      list(token: string, params: StockRequestListParams = {}): Promise<StockRequestPage> {
        const qs = stockRequestQS(params);
        if (params.order) qs.set("order", params.order);
        if (params.page) qs.set("page", String(params.page));
        if (params.size) qs.set("size", String(params.size));
        const suffix = qs.toString() ? `?${qs.toString()}` : "";
        return authed<StockRequestPage>(`/api/kho/de-nghi${suffix}`, token);
      },
      /** Đếm yêu cầu theo TỪNG trạng thái (cùng bộ lọc list, trừ tab) → FE cộng theo tab cho badge.
       *  `trang_thai` ở đây là TẬP NỀN (vd Hộp yêu cầu truyền INBOX_STATUSES). */
      tabCounts(token: string, params: StockRequestListParams = {}): Promise<Record<string, number>> {
        const qs = stockRequestQS(params);
        const suffix = qs.toString() ? `?${qs.toString()}` : "";
        return authed<Record<string, number>>(`/api/kho/de-nghi/counts-by-status${suffix}`, token);
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
      /** Gợi ý "Kho (xuất từ)" khi lập phiếu XUẤT: kho có nhiều hàng nhất theo thứ tự dòng yêu
       *  cầu. `kho_id === null` = không kho nào còn hàng → FE giữ nguyên kho đang chọn. */
      goiYKho(token: string, id: number): Promise<{ kho_id: number | null }> {
        return authed<{ kho_id: number | null }>(`/api/kho/de-nghi/${id}/goi-y-kho`, token);
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
      /** Ấn ĐIỀU CHUYỂN: server tự XUẤT nguồn (ghi sổ ngay, trừ tồn, chốt giá vốn bình quân) +
       *  tạo YÊU CẦU ĐIỀU CHUYỂN (NHẬP) ở đích. Kho đích lập phiếu nhập (đơn giá khoá) như nhập thường. */
      dieuChuyen(token: string, body: DieuChuyenInput): Promise<DieuChuyenResult> {
        return authed<DieuChuyenResult>("/api/kho/dieu-chuyen", token, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
      /** Ghi sổ — điểm DUY NHẤT tồn kho thay đổi; sau đó phiếu không sửa được nữa. */
      ghiSo(token: string, id: number): Promise<StockVoucher> {
        return authed<StockVoucher>(`/api/kho/phieu/${id}/ghi-so`, token, { method: "POST" });
      },
      /** Điều chỉnh phiếu XUẤT đã ghi sổ khi SX dùng ÍT hơn (xuất 10 → 7): trả phần dư về lô nguồn,
       *  giảm 'đã cấp' của yêu cầu. `lines` = các dòng GIẢM (line_id → số lượng mới). */
      dieuChinhXuat(
        token: string, id: number, lines: { line_id: number; so_luong_moi: number }[], lyDo: string,
      ): Promise<StockVoucher> {
        return authed<StockVoucher>(`/api/kho/phieu/${id}/dieu-chinh-xuat`, token, {
          method: "POST",
          body: JSON.stringify({ lines, ly_do: lyDo }),
        });
      },
      /** Lịch sử điều chỉnh của 1 phiếu xuất (ai · bộ phận · lúc nào · đổi gì) — mới nhất trước. */
      lichSuDieuChinh(token: string, id: number): Promise<DieuChinhLichSu[]> {
        return authed<DieuChinhLichSu[]>(`/api/kho/phieu/${id}/lich-su-dieu-chinh`, token);
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
      /** Sửa GIÁ GỐC thành phẩm từ KCS (gõ trên lô gốc hay lô con đều được — lan cả họ). `view_cost`. */
      suaGiaGoc(token: string, lotId: number, donGia: number): Promise<GiaGocKetQua> {
        return authed<GiaGocKetQua>(`/api/kho/phieu/lo/${lotId}/gia-goc`, token, {
          method: "PATCH",
          body: JSON.stringify({ don_gia: donGia }),
        });
      },
      /** Khai VỊ TRÍ cất lô cho DÒNG phiếu NHẬP còn NHÁP (điều chuyển đích) — trước khi ghi sổ. */
      suaViTriDong(
        token: string,
        voucherId: number,
        lines: { line_id: number; vi_tri: string | null }[],
      ): Promise<{ ok: boolean }> {
        return authed<{ ok: boolean }>(`/api/kho/phieu/${voucherId}/vi-tri`, token, {
          method: "PATCH",
          body: JSON.stringify({ lines }),
        });
      },
      /** Gợi ý lấy hàng từ lô nào (FEFO → FIFO). `thieu` > 0 = kho không đủ hàng. */
      goiYLo(
        token: string,
        params: { hang_loai: HangLoai; hang_id: number; kho_id: number; so_luong: number; request_id?: number | null },
      ): Promise<StockAllocation> {
        // `so_luong` ở ĐƠN VỊ GỐC — lô lưu theo đơn vị đó, gửi số theo đơn vị người khai là lệch.
        const qs = new URLSearchParams({
          hang_loai: params.hang_loai,
          hang_id: String(params.hang_id),
          kho_id: String(params.kho_id),
          so_luong: String(params.so_luong),
        });
        // Yêu cầu xuất do Giao hàng gửi ⇒ máy chủ ưu tiên lô của đúng đơn, bỏ lô của khách khác.
        if (params.request_id != null) qs.set("request_id", String(params.request_id));
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

    /** Điều chuyển kho — thao tác trên CẢ phiếu điều chuyển (vế xuất nguồn + vế nhập đích). */
    dieuChuyen: {
      /** Hủy CẢ phiếu điều chuyển — chỉ khi chưa ghi sổ (đã ghi sổ → 400). Trả 204. */
      huy(token: string, reqId: number, lyDo: string): Promise<void> {
        return authed<void>(`/api/kho/dieu-chuyen/${reqId}/huy`, token, {
          method: "POST",
          body: JSON.stringify({ ly_do: lyDo }),
        });
      },
      /** Từ 1 phiếu điều chuyển (nhập-đích/xuất-nguồn) → id yêu cầu điều chuyển ĐÍCH, để mở mặt tiền
       *  PHIẾU ĐIỀU CHUYỂN. 404 nếu không phải phiếu điều chuyển. */
      byVoucher(token: string, voucherId: number): Promise<{ request_id: number }> {
        return authed<{ request_id: number }>(`/api/kho/dieu-chuyen/by-voucher/${voucherId}`, token);
      },
    },

    /** Vị trí cất (kệ/ô) khai cho TỪNG kho — danh sách để khai lô chọn dropdown thay vì gõ tay.
     *  ĐỌC mở cho vai chọn kho; THÊM/XÓA gác `dm_kho_hang`. */
    viTri: {
      list(token: string, khoId: number): Promise<{ items: KhoViTriRow[] }> {
        return authed<{ items: KhoViTriRow[] }>(`/api/kho/${khoId}/vi-tri`, token);
      },
      create(
        token: string, khoId: number, body: { ma: string; ghi_chu?: string | null },
      ): Promise<KhoViTriRow> {
        return authed<KhoViTriRow>(`/api/kho/${khoId}/vi-tri`, token, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
      remove(token: string, id: number): Promise<void> {
        return authed<void>(`/api/kho/vi-tri/${id}`, token, { method: "DELETE" });
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
      /** Dòng ĐIỀU CHUYỂN đã ghi sổ (Xuất tại kho → Nhập tại kho) — cho tab Chuyển kho. */
      chuyenKho(token: string, params: BaoCaoChuyenKhoParams = {}): Promise<BaoCaoChuyenKhoPage> {
        const qs = new URLSearchParams();
        if (params.tu) qs.set("tu", params.tu);
        if (params.den) qs.set("den", params.den);
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.q) qs.set("q", params.q);
        const q = qs.toString();
        return authed<BaoCaoChuyenKhoPage>(`/api/kho/bao-cao/chuyen-kho${q ? `?${q}` : ""}`, token);
      },
      /** Báo cáo Nhập-Xuất-Tồn theo kỳ (bình quân gia quyền cuối kỳ) — 1 dòng / mặt hàng / kho.
       *  Đầu kỳ = snapshot kỳ trước (đã "Tính giá kỳ"); kỳ chưa tính → da_tinh=false (tạm tính). */
      nxt(token: string, params: BaoCaoNXTParams): Promise<BaoCaoNXTPage> {
        const qs = new URLSearchParams({ tu: params.tu, den: params.den });
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.q) qs.set("q", params.q);
        return authed<BaoCaoNXTPage>(`/api/kho/bao-cao/nxt?${qs.toString()}`, token);
      },
      /** Tính giá kỳ (bình quân) kiểu MISA: chốt tồn cuối kỳ vào snapshot để kỳ sau đọc làm đầu kỳ.
       *  Chạy lại được (đè) tới khi khóa sổ. Không đụng phiếu xuất đích danh. */
      tinhGiaKy(token: string, body: TinhGiaKyInput): Promise<BaoCaoNXTPage> {
        return authed<BaoCaoNXTPage>("/api/kho/bao-cao/tinh-gia-ky", token, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
      khoaSo(token: string): Promise<KhoKhoaSoRow[]> {
        return authed<KhoKhoaSoRow[]>("/api/kho/khoa-so", token);
      },
      /** Lịch sử các lần XUẤT EXCEL báo cáo kho (gộp vào tab "Lịch sử thao tác"). */
      lichSuExport(token: string): Promise<KhoExportLog[]> {
        return authed<KhoExportLog[]>("/api/kho/bao-cao/lich-su-export", token);
      },
      /** Các kỳ CÒN đang khóa (đã gộp khoảng) — cho tab "Kỳ đã khóa". */
      ky(token: string): Promise<KhoaSoKyRow[]> {
        return authed<KhoaSoKyRow[]>("/api/kho/khoa-so/ky", token);
      },
      /** Các kỳ ĐÃ TÍNH GIÁ (có snapshot) — cho tab "Kỳ đã tính". */
      kyDaTinh(token: string): Promise<KyDaTinh[]> {
        return authed<KyDaTinh[]>("/api/kho/bao-cao/ky-da-tinh", token);
      },
      /** Thành phẩm nhập từ KCS theo lô gốc — mặc định chỉ lô CHƯA có giá gốc. Lọc + trang ở máy chủ. */
      thanhPhamChuaGiaGoc(
        token: string,
        p: {
          q?: string; chiChuaGia?: boolean; page?: number; size?: number;
          /** Khoảng NGÀY NHẬP (YYYY-MM-DD), hai đầu đều tính. */
          tu?: string; den?: string; khoId?: number; khachHangId?: number;
        } = {},
      ): Promise<ThanhPhamChuaGiaGocPage> {
        const qs = new URLSearchParams();
        if (p.q) qs.set("q", p.q);
        if (p.chiChuaGia === false) qs.set("chi_chua_gia", "false");
        if (p.tu) qs.set("tu", p.tu);
        if (p.den) qs.set("den", p.den);
        if (p.khoId != null) qs.set("kho_id", String(p.khoId));
        if (p.khachHangId != null) qs.set("khach_hang_id", String(p.khachHangId));
        qs.set("page", String(p.page ?? 1));
        qs.set("size", String(p.size ?? 50));
        return authed<ThanhPhamChuaGiaGocPage>(`/api/kho/bao-cao/thanh-pham-chua-gia-goc?${qs}`, token);
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
        setFunnelQs(qs, params);
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
      /** Xuất Excel ĐIỀU CHUYỂN theo mẫu MISA "Chuyển kho" — fetch as blob (bearer + refresh-aware). */
      async chuyenKhoExportXlsxBlobUrl(
        token: string,
        params: BaoCaoChuyenKhoParams = {},
      ): Promise<string> {
        const qs = new URLSearchParams();
        if (params.tu) qs.set("tu", params.tu);
        if (params.den) qs.set("den", params.den);
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.q) qs.set("q", params.q);
        setFunnelQs(qs, params);
        const doFetch = (bearer: string) =>
          fetch(`${BASE_URL}/api/kho/bao-cao/chuyen-kho/export.xlsx?${qs.toString()}`, {
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
      /** Xuất Excel bảng NHẬP-XUẤT-TỒN (mẫu MISA, gom nhóm theo kho + dòng cộng). */
      async nxtExportXlsxBlobUrl(
        token: string,
        params: { tu: string; den: string; kho_id?: number | null; q?: string },
      ): Promise<string> {
        const qs = new URLSearchParams();
        qs.set("tu", params.tu);
        qs.set("den", params.den);
        if (params.kho_id != null) qs.set("kho_id", String(params.kho_id));
        if (params.q) qs.set("q", params.q);
        const doFetch = (bearer: string) =>
          fetch(`${BASE_URL}/api/kho/bao-cao/nxt/export.xlsx?${qs.toString()}`, {
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

// --- Giao hàng (module `giao_hang`) -----------------------------------------
// HAI TẦNG TRẠNG THÁI: `DeliveryRequest.trang_thai` là HÀM do máy chủ tính (chỉ hai giá trị được
// lưu là `cho_len_ke_hoach`/`da_huy`); `DeliveryTrip.trang_thai` mới là máy trạng thái thật.
// Đừng suy trạng thái yêu cầu ở FE — hai nơi tính là hai nơi lệch.
export type DeliveryRequestStatus =
  | "cho_len_ke_hoach"
  | "dang_thuc_hien"
  | "da_giao_du"
  /** Mọi chuyến đã khép mà chưa giao đủ — Kinh doanh lập yêu cầu mới cho phần còn lại. */
  | "giao_thieu"
  | "that_bai"
  | "chuyen_da_huy"
  | "da_huy";

export type DeliveryTripStatus =
  | "da_len_ke_hoach"
  | "dang_chuan_bi"
  | "da_lay_hang"
  | "dang_giao"
  | "thanh_cong"
  | "giao_thieu"
  | "hen_lai"
  | "that_bai"
  | "dang_tra_hang"
  | "da_tra_hang"
  | "da_huy";

export interface DeliveryRequestLine {
  id: number;
  order_line_id: number;
  qty: number;
  mo_ta: string | null;
  don_vi_tinh: string | null;
  da_giao: number;
  /** Mặt hàng KHO của dòng — Bán hàng chọn một lần lúc lập yêu cầu. */
  hang_loai: string | null;
  hang_id: number | null;
  hang_ten: string | null;
  dvt: string | null;
  /** Cụm bán nhiều dòng (Ruột + Bìa → Kỷ yếu): cùng `cum_khoa` ⇒ giao / nhận cùng một số, form
   *  bày MỘT ô và gửi dòng đầu cụm. Trống = dòng đứng một mình. */
  cum_khoa?: string | null;
  cum_ten?: string | null;
  cum_dvt?: string | null;
}

export interface DeliveryRequest {
  id: number;
  code: string;
  order_id: number;
  order_code: string | null;
  customer_id: number | null;
  customer_name: string | null;
  department_id: number | null;
  ngay_can_giao: string;
  dia_chi: string;
  nguoi_nhan: string | null;
  sdt_nguoi_nhan: string | null;
  ghi_chu: string | null;
  trang_thai: DeliveryRequestStatus;
  ly_do_huy: string | null;
  created_by: number | null;
  created_by_name: string | null;
  created_at: string;
  lines: DeliveryRequestLine[];
  so_lan_giao: number;
  /** Trạng thái Lệnh sản xuất — CHỈ HIỆN cho quản lý tự nhìn, KHÔNG chặn (PRD quyết định #1). */
}

export interface DeliveryTripLine {
  order_line_id: number;
  qty_giao: number;
}

export interface DeliveryTrip {
  id: number;
  request_id: number;
  request_code: string | null;
  order_id: number | null;
  order_code: string | null;
  customer_name: string | null;
  lan_thu: number;
  employee_id: number;
  employee_name: string | null;
  /** Phụ xe — tối đa MỘT người, tuỳ chọn (mg 0231). Vai trò do Ô THẢ NGƯỜI VÀO quyết định,
   *  không phải thuộc tính của người: hôm nay lái, mai đi phụ. */
  phu_xe_employee_id?: number | null;
  phu_xe_name?: string | null;
  vehicle_id?: number | null;
  xe_bien_so?: string | null;
  xe_ten?: string | null;
  gio_lay_hang: string;
  gio_du_kien_giao: string;
  ghi_chu_phan_cong: string | null;
  trang_thai: DeliveryTripStatus;
  km: number | null;
  /** TỔNG km cả các lần giao của yêu cầu (không phải riêng chuyến này) — tab "Đơn giao hàng"
   *  đã gộp theo yêu cầu. */
  tong_km: number;
  thoi_gian_ket_thuc: string | null;
  nguoi_nhan_thuc_te: string | null;
  ly_do_that_bai: string | null;
  huong_xu_ly: string | null;
  ngay_hen_lai: string | null;
  ghi_chu_ket_qua: string | null;
  lines: DeliveryTripLine[];
  /** Mã + trạng thái YÊU CẦU XUẤT KHO của chuyến (chứng từ của kho). null = chưa gửi. */
  yeu_cau_kho_ma: string | null;
  yeu_cau_kho_trang_thai: string | null;
  /** Yêu cầu NHẬP trả hàng về kho (giao thiếu / thất bại) — máy tự lập, thủ kho ghi sổ là xong. */
  tra_hang_ma?: string | null;
  tra_hang_trang_thai?: string | null;
  /** Kho đã LẬP PHIẾU chưa. Suy từ `stock_vouchers`, không phải cột lưu — kho thao tác trên
   *  màn của họ nên trạng thái phải đọc ngược từ sổ kho. */
  kho_da_lap_phieu?: boolean;
  /** Lượt xe của chuyến (PRD khoán km §14). `null` = chuyến ngoài lượt: một ô km như cũ. */
  luot?: LuotXeTrongChuyen | null;
  /** Cảnh báo KHÔNG chặn của thao tác vừa làm (vd "xe chạy ngoài sổ 30 km"). */
  canh_bao?: string[];
}

/** Lượt xe nhìn từ MỘT chuyến. Chuyến trong lượt không gõ km: tài xế ghi SỐ ĐỒNG HỒ lúc xuất
 *  phát, lúc tới từng khách, lúc về kho — máy trừ ra km từng chặng rồi tra đơn giá theo chặng. */
export interface LuotXeTrongChuyen {
  id: number;
  code: string;
  vehicle_id: number;
  ngay: string;
  so_diem: number;
  so_dong_ho_xuat_phat: number | null;
  so_dong_ho_ve_kho: number | null;
  ve_kho_luc: string | null;
  km_ve_kho: number | null;
  /** Số đồng hồ lúc TỚI điểm của chính chuyến này (null = chưa nhập kết quả). */
  so_dong_ho: number | null;
  /** Số lớn nhất đã ghi trong lượt (hoặc số xuất phát) — để nhắc khi nhập số tiếp theo. */
  so_dong_ho_gan_nhat: number | null;
  /** Số cuối đã ghi của xe ở lượt trước — tự điền lúc xuất phát. Chỉ có khi lượt chưa xuất phát. */
  goi_y_xuat_phat: number | null;
  /** Mọi điểm đã có kết quả, lượt chưa về kho ⇒ hiện nút "Về kho". */
  cho_ve_kho: boolean;
  /** Chuyến này là điểm có số đồng hồ lớn nhất — nút "Về kho" đặt ở dòng này. */
  la_diem_cuoi: boolean;
}

/** Một lượt CHƯA về kho của một xe — ô Lượt xe lúc lên đơn. */
export interface LuotXeMo {
  id: number;
  code: string;
  ngay: string;
  so_diem: number;
  tai_xe: string | null;
  da_xuat_phat: boolean;
}

export interface VeKhoKetQua {
  id: number;
  code: string;
  so_dong_ho_ve_kho: number | null;
  km_ve_kho: number | null;
  ve_kho_luc: string | null;
  canh_bao: string[];
}

export interface LenLuotInput {
  request_ids: number[];
  employee_id: number;
  phu_xe_employee_id?: number | null;
  /** Lượt là vòng chạy của MỘT chiếc xe ⇒ bắt buộc. */
  vehicle_id: number;
  gio_lay_hang: string;
  gio_du_kien_giao: string;
  ghi_chu_phan_cong?: string | null;
  /** `"moi"` = lượt mới · id = ghép vào lượt đang mở của cùng xe. */
  luot_xe_id: number | "moi";
}

export interface LenLuotKetQua {
  luot_id: number;
  code: string;
  trips: DeliveryTrip[];
  canh_bao: string[];
}

export interface LuotXeChiTiet {
  id: number;
  code: string;
  ngay: string;
  vehicle_id: number;
  xe_bien_so: string | null;
  xe_ten: string | null;
  so_dong_ho_xuat_phat: number | null;
  so_dong_ho_ve_kho: number | null;
  ve_kho_luc: string | null;
  km_ve_kho: number | null;
  goi_y_xuat_phat: number | null;
  so_dong_ho_gan_nhat: number | null;
  cho_ve_kho: boolean;
  tong_km: number;
  /** Các điểm theo THỨ TỰ CHẶNG (số đồng hồ tăng dần; chưa có số thì xếp cuối). */
  diem: DeliveryTrip[];
  so_cho_gui_kho: number;
  so_cho_lay_hang: number;
  so_cho_bat_dau: number;
  so_dang_giao: number;
}

/** Một KHỐI của tab Đơn giao hàng — đúng MỘT trong hai ô có giá trị. */
export interface BangGiaoItem {
  luot: LuotXeChiTiet | null;
  trip: DeliveryTrip | null;
}

export interface BangGiaoPage {
  items: BangGiaoItem[];
  /** Tổng số KHỐI — để phân trang. */
  total: number;
  /** Tổng số ĐƠN giao (chuyến) — số đếm trên tab / đầu trang. */
  so_don: number;
}

/** Kết quả một thao tác CẢ LƯỢT: số chuyến vừa đi tiếp, mã phiếu kho (nếu có), cảnh báo. */
export interface CaLuotKetQua {
  so_chuyen: number;
  phieu: string[];
  canh_bao: string[];
}

export interface DeliveryHistory {
  id: number;
  tu_trang_thai: string | null;
  den_trang_thai: string;
  nguoi_thao_tac_id: number | null;
  nguoi_thao_tac_name: string | null;
  luc: string;
  ghi_chu: string | null;
  ly_do: string | null;
}

export interface DeliveryRequestDetail {
  request: DeliveryRequest;
  trips: DeliveryTrip[];
  lich_su: DeliveryHistory[];
}

export interface DeliveryRequestInput {
  order_id: number;
  ngay_can_giao: string;
  /** Chỉ HAI ô: dòng đơn nào, bao nhiêu. Ba ô mặt hàng kho gỡ 19/08/2026 — hệ tự khai vào danh
   *  mục Thành phẩm lúc chốt đơn, người lập không chọn gì (docs/prd-thanh-pham.md). */
  lines: {
    order_line_id: number;
    qty: number;
  }[];
  /** Nơi nhận CHỌN từ sổ của khách (19/09/2026) — không có ô gõ tay. `null`/bỏ trống = nơi nhận của
   *  đơn. Lưu ý giao hàng máy chủ tự lấy của đơn. */
  dia_chi_id?: number | null;
  lien_he_id?: number | null;
}

export interface KhoanKmPct {
  pct_tai_xe: number;
  pct_phu_xe: number;
}

export interface MucKm {
  id: number;
  /** Rỗng — ô chọn dùng chung vẽ "mã · tên" nhưng tự giấu phần mã khi rỗng. Mức chỉ có TÊN. */
  ma?: string;
  /** Tên mức — thứ người dùng đọc khi gán cho xe ("Xe 2 tấn"). Không được trùng. */
  ten: string;
  ghi_chu?: string | null;
  active: boolean;
  items: KmBracket[];
  /** SỐ XE đang ăn mức này — màn phải nói trước khi người ta sửa giá: sửa một mức là đổi tiền
   *  của cả nhóm xe, khác hẳn sửa bảng giá của riêng một chiếc. */
  so_xe: number;
}

export interface MucKmInput {
  ten: string;
  ghi_chu?: string | null;
  active?: boolean;
}

export interface KmBracket {
  /** Trần km của bậc; `null` = bậc cao nhất (từ đó trở lên), chỉ một và ở CUỐI. */
  up_to_km: number | null;
  don_gia: number;
}

export interface PlanInput {
  request_id: number;
  employee_id: number;
  /** Gửi `null` khi ĐỔI kế hoạch = GỠ phụ xe; KHÔNG gửi = giữ nguyên. Máy chủ phân biệt hai
   *  trường hợp đó, nên đừng gửi `null` chỉ vì ô đang trống ở màn tạo mới. */
  phu_xe_employee_id?: number | null;
  /** Xe chạy chuyến. TUỲ CHỌN lúc lên kế hoạch, BẮT BUỘC lúc đóng chuyến (máy chủ chặn). */
  vehicle_id?: number | null;
  gio_lay_hang: string;
  gio_du_kien_giao: string;
  kho_id?: number | null;
  ghi_chu_phan_cong?: string | null;
  /** LƯỢT XE (PRD khoán km §14): `"moi"` = lượt mới · id = ghép vào lượt đang mở của CÙNG xe ·
   *  không gửi = chuyến ngoài lượt (một ô km như cũ). Chỉ có nghĩa khi đã chọn xe. */
  luot_xe_id?: number | "moi" | null;
}

export interface KetQuaInput {
  ket_qua: "thanh_cong" | "giao_thieu" | "hen_lai" | "that_bai";
  /** `>= 0`, KHÔNG phải `> 0`: xe chưa lăn bánh mà khách không nghe máy thì 0 km là số THẬT.
   *  Chỉ cho chuyến NGOÀI lượt — chuyến trong lượt gửi `so_dong_ho`, máy tự trừ ra km. */
  km?: number | null;
  /** Số đồng hồ lúc TỚI khách — chuyến trong lượt xe. */
  so_dong_ho?: number | null;
  thoi_gian_ket_thuc?: string | null;
  nguoi_nhan_thuc_te?: string | null;
  ly_do_that_bai?: string | null;
  huong_xu_ly?: "tra_ve" | "cho_giao_lai" | null;
  ngay_hen_lai?: string | null;
  ghi_chu?: string | null;
  so_thuc_nhan?: { order_line_id: number; qty: number }[] | null;
  /** Bật sau khi người dùng đã xem cảnh báo "km lớn bất thường" và khẳng định đúng. */
  xac_nhan_km_lon?: boolean;
  /** Xe đã chạy chuyến — gửi để điền/đổi ngay lúc ghi kết quả. Chuyến khối Giao hàng mà cả
   *  đây lẫn chuyến đều trống thì máy chủ chặn (đơn giá khoán km tra theo mức của xe). */
  vehicle_id?: number | null;
}

/** Một dòng SẼ gửi kho — máy suy ra từ yêu cầu giao, người dùng chỉ xem. */
export interface DinhKemChuyen {
  id: number;
  trip_id: number;
  file_name: string;
  /** Đọc lại qua `/api/files/...` — cần đăng nhập. */
  file_url: string;
  file_type: string | null;
  uploaded_by: number | null;
  uploaded_at: string;
}

export interface HangCanXuat {
  hang_loai: string;
  hang_id: number;
  hang_ten: string | null;
  dvt: string;
  sl_de_nghi: number;
}

export interface YeuCauXuatKhoInput {
  /** CHỈ chọn kho. Dòng hàng suy ra từ yêu cầu giao — không gửi từ đây. */
  /** Để TRỐNG (21/08/2026): thủ kho chọn kho lúc lập phiếu — người gửi không biết hàng
   *  đang nằm kho nào. */
  kho_id?: number | null;
  ngay_can?: string | null;
  ghi_chu?: string | null;
}

export interface YeuCauKho {
  id: number;
  ma: string;
  trang_thai: string;
}

export interface DeliveryDriver {
  employee_id: number;
  ho_ten: string;
  trang_thai: "ranh" | "co_lich" | "dang_giao" | "dang_tra_hang" | "nghi";
  chuyen_dang_thuc_hien: string | null;
  chuyen_ke_tiep: string | null;
  so_chuyen_xong: number;
  tong_km: number;
  /** Trong THÁNG chứa ngày đang xem — để theo dõi định kỳ (20/08/2026). */
  so_chuyen_thang?: number;
  tong_km_thang?: number;
}

export interface DeliveryDriverPick {
  id: number;
  code: string | null;
  full_name: string;
  department: string | null;
  /** Có ô Thao tác của màn Giao hàng chưa. Không có ⇒ họ thấy chuyến nhưng KHÔNG bấm được
   *  "Đã lấy hàng" / nhập kết quả, chuyến tắc ở đó. Phải báo ngay lúc chọn. */
  /** Có tài khoản đăng nhập chưa. Tách khỏi `co_thao_tac` để câu cảnh báo chỉ đúng màn cần
   *  sửa: chưa có tài khoản → màn Người dùng; có rồi mà thiếu ô → màn Vai trò. */
  co_tai_khoan?: boolean;
  co_thao_tac: boolean;
}

export interface ConPhaiGiaoLine {
  order_line_id: number;
  mo_ta: string | null;
  don_vi_tinh: string | null;
  qty_dat: number;
  da_giao: number;
  con_phai_giao: number;
  /** Cụm bán nhiều dòng (Ruột + Bìa → Kỷ yếu): cùng `cum_khoa` ⇒ giao / nhận cùng một số, form
   *  bày MỘT ô và gửi dòng đầu cụm. Trống = dòng đứng một mình. */
  cum_khoa?: string | null;
  cum_ten?: string | null;
  cum_dvt?: string | null;
}

export interface ConPhaiGiao {
  order_id: number;
  da_giao_du: boolean;
  lines: ConPhaiGiaoLine[];
}

// --- Tiến độ đơn (GET /api/orders/{id}/tien-do) ----------------------------
export interface DonTienDoLenh {
  id: number;
  ma: string;
  da_xuong_xuong: boolean;
  pct: number;
  uoc_tinh: boolean;
  xong: boolean;
  buoc_hien_tai: string | null;
  du_kien_xong: string | null;
  trang_thai: string | null;
  canh_bao: string[];
}

export interface DonTienDoCum {
  khoa: string;
  ten: string;
  don_vi: string | null;
  order_line_ids: number[];
  dat: number;
  co_lenh: boolean;
  lenh: DonTienDoLenh[];
  sx_pct: number | null;
  sx_xong: boolean;
  kho_de_nghi: number;
  kho_da_nhan: number;
  cho_kho: number;
  ton_that: number;
  da_giao: number;
  dang_giu: number;
  con_phai_giao: number;
  /** Số Kinh doanh còn lập yêu cầu giao được — chỉ phần KHO ĐÃ NHẬN, trừ đã giao + đang giữ. */
  giao_duoc: number;
}

export interface DonTienDoChuyen {
  id: number;
  trang_thai: DeliveryTripStatus;
  gio_lay_hang: string;
  gio_du_kien_giao: string;
  tai_xe: string | null;
  xe: string | null;
  thoi_gian_ket_thuc: string | null;
  nguoi_nhan_thuc_te: string | null;
  ly_do_that_bai: string | null;
  tra_hang_ma: string | null;
  tra_hang_xong: boolean;
  kho_da_lap_phieu?: boolean;
  so_anh: number;
}

export interface DonTienDoYeuCau {
  id: number;
  code: string;
  ngay_can_giao: string;
  trang_thai: DeliveryRequestStatus;
  ly_do_huy: string | null;
  dia_chi: string;
  nguoi_nhan: string | null;
  sdt_nguoi_nhan: string | null;
  ghi_chu: string | null;
  created_at: string;
  dong: { order_line_id: number; ten: string; qty: number; da_giao: number }[];
  chuyen: DonTienDoChuyen | null;
}

export interface DonTienDo {
  order_id: number;
  han_cam_ket: string | null;
  du_kien_xong: string | null;
  chua_du_du_lieu: boolean;
  tre_ngay: number | null;
  ly_do: string[];
  cum: DonTienDoCum[];
  yeu_cau: DonTienDoYeuCau[];
  noi_nhan: DonNoiNhan;
}

/** Nơi nhận để form yêu cầu giao CHỌN: mặc định của đơn + sổ địa chỉ / người liên hệ của khách. */
export interface DonNoiNhan {
  khach_id: number | null;
  dia_chi: string | null;
  nguoi_nhan: string | null;
  sdt: string | null;
  luu_y: string | null;
  so_dia_chi: { id: number; nhan: string; dia_chi: string; sdt: string | null; mac_dinh: boolean }[];
  lien_he: { id: number; ten: string; chuc_vu: string | null; sdt: string | null; chinh: boolean }[];
}
