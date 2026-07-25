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

export type QuoteEvent =
  | { type: "quote_decision"; quote_id: number; code: string; decision: "approved" | "rejected" }
  | { type: "quote_pending_changed"; code?: string }
  // Đơn hàng bán dùng CHUNG kênh hub (bám logic SSE báo giá): quyết định duyệt/đủ cọc gửi riêng
  // người soạn; 'pending_changed' là tín hiệu danh sách chờ đổi → refetch notify-summary theo vai.
  | { type: "order_decision"; code: string; decision: "approved" | "rejected" }
  | { type: "order_deposit_ok"; code: string }
  | { type: "order_pending_changed"; code?: string }
  // Lịch hẹn chăm sóc (redesign-lich-hen-cham-soc): ticker đẩy "care_due" khi tới giờ hẹn,
  // "care_assigned" khi giao hẹn cho người khác — gửi riêng người phụ trách.
  | { type: "care_due"; customer: string; customer_id: number; note: string }
  | { type: "care_assigned"; customer: string; customer_id: number; note: string }
  // Tạm ứng lương: NV gửi đề nghị → 'pending_changed' (người duyệt refetch badge); kế toán
  // duyệt/từ chối → 'decision' gửi riêng nhân viên đề nghị.
  | { type: "advance_pending_changed"; code?: string }
  | { type: "advance_decision"; code?: string; decision: "approved" | "rejected" }
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
  | { type: "order_deposit_needed"; code?: string; order_id: number; amount: number };

// --- Lệnh sản xuất (LSX) — bàn Kế hoạch sản xuất ------------------------------
// Job (đơn) → Part (lệnh) → Operation (công đoạn). Mỗi DÒNG ĐƠN = 1 lệnh, ngang hàng.
export type LsxTrangThai =
  | "nhap"
  | "cho_bo_sung"
  | "san_sang"
  | "da_lap_ke_hoach"   // đã sinh dòng xếp lịch (≈ Firm Planned) — routing khóa
  | "da_phat_hanh";     // đã phát hành xuống xưởng (≈ Released)
export type LsxDonVi = "to" | "cai" | "kem" | "bai";
/** Loại bước = bước CHIẾM cái gì khi lên Gantt (`bai_ghep` khai sẵn, pha sau mới sinh). */
export type LsxLoaiBuoc = "may" | "to" | "thue_ngoai" | "cho" | "kcs" | "xa_to" | "bai_ghep";
export type LsxDonViNangSuat = "to_gio" | "cai_gio" | "kem_gio" | "bai_gio";

export const LSX_DON_VI_LABELS: Record<string, string> = {
  to: "tờ", cai: "con", kem: "kẽm", bai: "bài",
};

/** Nhãn + màu của loại bước. `tone` map sang class `.khsx-lb--{tone}` trong ke-hoach-sx.css. */
export const LSX_LOAI_BUOC_META: Record<LsxLoaiBuoc, { label: string; tone: string; hint: string }> = {
  may: { label: "Máy", tone: "may", hint: "Chiếm máy — có thanh trên lịch máy" },
  to: { label: "Tổ", tone: "to", hint: "Tổ lao động làm tay — chiếm nhân công, không chiếm máy" },
  thue_ngoai: { label: "Thuê ngoài", tone: "ngoai", hint: "Nhà gia công làm — không chiếm máy nội bộ" },
  cho: { label: "Chờ", tone: "cho", hint: "Chờ kỹ thuật (khô mực/khô keo) — chỉ đẩy lịch, không chiếm gì" },
  kcs: { label: "KCS", tone: "kcs", hint: "Kiểm tra — chiếm tổ" },
  xa_to: { label: "Xả tờ", tone: "xa", hint: "Chia bán thành phẩm — chiếm máy xén" },
  bai_ghep: { label: "Bài ghép", tone: "ghep", hint: "Chạy chung ở bài ghép (chưa dùng ở bản này)" },
};

/** Mã checklist "thiếu gì" → nhãn hiển thị (server trả mã, FE dịch). CHẶN nút Sẵn sàng. */
export const LSX_THIEU_LABELS: Record<string, string> = {
  khong_co_ptg: "Chưa có bài tính giá",
  thieu_giay: "Thiếu loại giấy",
  thieu_kho: "Thiếu kích thước",
  thieu_routing: "Chưa có công đoạn",
  thieu_ngay_giao: "Thiếu ngày giao",
  thieu_khuon: "Chưa gán khuôn bế",
  thieu_to_may: "Có công đoạn chưa gán tổ / máy",
  thieu_ncc: "Công đoạn thuê ngoài chưa có nhà gia công",
  thieu_tg_thue_ngoai: "Công đoạn thuê ngoài chưa có ngày gửi / nhận",
  thieu_he_so: "Đổi đơn vị nhưng chưa khai hệ số quy đổi",
};

/** Cảnh báo MỀM — chỉ tô màu, không chặn lưu và không chặn Sẵn sàng. */
export const LSX_CANH_BAO_LABELS: Record<string, string> = {
  ra_lon_hon_vao: "Có công đoạn ra nhiều hơn vào",
  dut_chuyen: "Đứt chuyền — bước sau đòi nhiều hơn bước trước giao",
  vuot_han_giao: "Tổng thời gian dẫn vượt hạn giao khách",
  khac_bai_tinh_gia: "Routing đã đổi so với bài tính giá",
  may_khong_hop_kho: "Khổ tờ in vượt khổ tối đa của máy",
};

// --- Bài ghép (print gang) — gom công đoạn in nhiều LSX chạy chung 1 tờ --------
export type BaiGhepTrangThai = "nhap" | "san_sang";

/** Checklist CHẶN "sẵn sàng xếp lịch" (server trả mã, FE dịch). */
export const BAI_GHEP_THIEU_LABELS: Record<string, string> = {
  thieu_thanh_vien: "Cần ít nhất 2 lệnh",
  thieu_giay: "Chưa chọn giấy chạy chung",
  thieu_kho_in: "Chưa có khổ tờ in chung",
  thieu_ups: "Có thành viên chưa khai số con/tờ",
  thieu_so_to: "Chưa tính được số tờ",
};

/** Cảnh báo MỀM — chỉ tô màu, không chặn. */
export const BAI_GHEP_CANH_BAO_LABELS: Record<string, string> = {
  khac_giay: "Thành viên khác loại giấy",
  khac_so_mau: "Thành viên khác số màu",
  khac_so_mat: "Thành viên khác số mặt / kiểu trở",
  co_gap: "Có lệnh GẤP trong bài",
  lech_han: "Hạn giao các lệnh lệch nhau xa",
  thanh_vien_khong_san_sang: "Có lệnh không còn sẵn sàng",
  don_huy: "Có lệnh thuộc đơn đã huỷ",
  bai_thua: "Bài thưa — nhiều chỗ trống, phí giấy",
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
  giay_id: number | null; giay_ten: string | null;
  so_mau_a: number | null; so_mau_b: number | null; quy_cach_in: string | null;
  kho_tp: string | null; han_hoan_thanh_sx: string | null;
}
export interface BaiGhepSoTo {
  so_to_tot: number; tong_to: number; fill_pct: number | null; han_in_muon_nhat: string | null;
  rows: { thanh_vien_id: number; lsx_id: number; can: number; con: number;
          san_luong_du_kien: number; du: number }[];
}
export interface BaiGhepTuongThichRow { thuoc_tinh: string; gia_tri: (string | null)[]; muc: string }
export interface BaiGhepTuongThich { thanh_vien: { lsx_id: number }[]; rows: BaiGhepTuongThichRow[] }
export interface BaiGhepDetail {
  id: number; ma: string; trang_thai: BaiGhepTrangThai;
  giay_id: number | null; giay_ten: string | null;
  kho_in_dai: number | null; kho_in_rong: number | null;
  may_id: number | null; may_ten: string | null;
  hao_hut_setup: number; hao_hut_chay: number; ghi_chu: string | null;
  thanh_vien: BaiGhepThanhVien[];
  so_to: BaiGhepSoTo;
  tuong_thich: BaiGhepTuongThich;
  thieu: string[]; canh_bao: string[];
}
export interface BaiGhepUpdateBody {
  giay_id?: number | null; kho_in_dai?: number | null; kho_in_rong?: number | null;
  may_id?: number | null; hao_hut_setup?: number; hao_hut_chay?: number; ghi_chu?: string | null;
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
  tong_phut: number;
  // Breakdown chiếm máy (Gantt vẽ thanh 2 đoạn setup+chạy; vệ sinh gộp cuối).
  setup_phut: number;
  chay_phut: number;
  ve_sinh_phut: number;
  theo_may: boolean;                     // thời lượng tính LẠI theo tốc độ máy đang gán (HM3) vs snapshot
  canh_bao_thoi_luong: string | null;    // may_chua_toc_do | don_vi_lech — vì sao không tính-theo-máy được
  slack_ngay: number | null;
  nhan_rui_ro: XepLichRuiRo | null;
  // Trạng thái
  trang_thai: string;            // cho_xep | da_xep
  is_locked: boolean;
  co_xung_dot: boolean;
  blocked_reason: string | null; // thieu_may | thieu_thoi_luong | cho_tien_de | …
  // Kiểm khả năng máy (HM4) — soft, KHÔNG chặn (khổ/số màu/định lượng vượt spec máy đang gán).
  can_xac_nhan: boolean;
  ly_do_xac_nhan: string[];      // kho_vuot_may | so_mau_vuot_units | gsm_ngoai_khoang
  is_rush: boolean;
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

/** Gợi ý xếp (chỉ đọc): máy trống sớm nhất + kết thúc nếu xếp + hạn lùi còn kịp giao. */
export interface XepLichGoiY {
  may_id: number | null;
  khe_trong: string | null;
  finish_neu_xep: string | null;
  han_lui: string | null;
}

/** Nền lịch máy cho Gantt: khoảng LÀM VIỆC theo ca của xưởng + vùng KHÓA máy (bảo trì/khóa). */
export interface XepLichLichKhoang { start: string; finish: string }
export interface XepLichVungKhoa { start: string; finish: string; ly_do: string | null }
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
  setup_phut: number;
  chay_phut: number;
  ve_sinh_phut: number;
  theo_may: boolean;
  xung_dot_ids: number[];              // id dòng đã xếp sẽ chồng giờ trên máy này
  day_doi: XepLichPreviewDayDoi[];     // bước sau bị đẩy
  han_hoan_thanh_moi: string | null;
  nhan_rui_ro: XepLichRuiRo | null;
  can_xac_nhan: boolean;               // máy có thể không kham nổi (khổ/số màu/định lượng) — cảnh báo, không chặn
  ly_do_xac_nhan: string[];
}

/** 1 khoảng khóa máy (bảo trì/hỏng/nghỉ) — CRUD + Gantt overlay. */
export interface XepLichVungKhoaItem {
  id: number;
  may_id: number;
  start: string;
  finish: string;
  ly_do: string;   // bao_tri | hong_hoc | nghi | khac
  note: string | null;
}
export interface XepLichVungKhoaListOut { items: XepLichVungKhoaItem[] }
export interface XepLichVungKhoaIn { tu: string; den: string; ly_do?: string; note?: string | null }

// --- Vấn đề kế hoạch (xung đột & nguy cơ trễ) — dẫn xuất lúc đọc + state người xử lý ---
export type XepLichSeverity = "chan" | "nghiem_trong" | "cao" | "canh_bao";
export type XepLichVanDeCategory =
  | "trung_may"
  | "de_khoa_may"
  | "sai_tien_nhiem"
  | "gang_thieu_xa_to"
  | "thieu_du_lieu"
  | "nguy_co_tre"
  | "may_khong_kham";
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
export interface XepLichSanSangItem { nguon: XepLichNguon; id: number; ma: string; blocking: number }
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
  bu_hao_to: number;
  so_to_ke_hoach: number;
  so_to_nguyen: number;
  so_con: number;
  so_kem: number;
  so_luot: number;
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
  nguoi_giao_nhan_id: number | null;
}

export interface LsxCongDoan extends LsxThueNgoaiFields {
  id: number; thu_tu: number; cong_doan_id: number | null;
  ten: string; nhom: string | null; loai_buoc: LsxLoaiBuoc; bat_buoc: boolean;
  department_id: number | null; department_ten: string | null;
  may_id: number | null; may_ten: string | null; may_thay_the_ids: number[];
  // Đơn vị VÀO ≠ RA là chuyện thường ở bế/xén — hệ số quy đổi nối hai đầu.
  so_luong_vao: number; so_luong_ra: number;
  don_vi_vao: string; don_vi_ra: string; he_so_quy_doi: number;
  hao_hut: number; hao_hut_pct: number; ty_le_hao_hut: number; so_luot_chay: number;
  so_nhan_cong: number;
  setup_phut: number; nang_suat: number | null; don_vi_nang_suat: string | null;
  chay_phut: number | null;   // null = để máy tính từ năng suất
  ve_sinh_phut: number; cho_phut: number; di_chuyen_phut: number;
  // derived: chiếm máy ĂN capacity; tổng thêm chờ + di chuyển (KHÔNG ăn capacity)
  chiem_may_phut: number; tong_phut: number;
  dieu_kien_json: string[];
  nguoi_giao_nhan_ten: string | null;
  ghi_chu: string | null;
}
export interface LsxCongDoanBody extends Partial<LsxThueNgoaiFields> {
  thu_tu?: number; cong_doan_id?: number | null; ten?: string; nhom?: string | null;
  loai_buoc?: LsxLoaiBuoc; bat_buoc?: boolean;
  department_id?: number | null; may_id?: number | null; may_thay_the_ids?: number[];
  so_luong_vao?: number; so_luong_ra?: number;
  don_vi_vao?: string; don_vi_ra?: string; he_so_quy_doi?: number;
  hao_hut?: number; hao_hut_pct?: number; so_luot_chay?: number; so_nhan_cong?: number;
  setup_phut?: number; nang_suat?: number | null; don_vi_nang_suat?: string | null;
  chay_phut?: number | null;
  ve_sinh_phut?: number; cho_phut?: number; di_chuyen_phut?: number;
  dieu_kien_json?: string[];
  ghi_chu?: string | null;
}
/** Tổng thời gian dẫn cả lệnh — DẪN XUẤT ở server, không lưu cột. */
export interface LsxLeadTime {
  tong_phut: number;
  chiem_may_phut: number;
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
  cong_doan_id: number; ten: string; nhom: string | null; loai_buoc: LsxLoaiBuoc;
  department_id: number | null; may_id: number | null;
  don_vi_vao: string; don_vi_ra: string; he_so_quy_doi: number;
  setup_phut: number; nang_suat: number | null; don_vi_nang_suat: string | null;
  ve_sinh_phut: number;
}
export interface LsxListItem {
  id: number; ma: string; loai: string; ten: string; trang_thai: LsxTrangThai;
  order_id: number; order_no: string | null; customer_name: string | null;
  so_luong_dat: number; don_vi_tinh: string; so_to_ke_hoach: number;
  han_giao_khach: string | null; han_hoan_thanh_sx: string | null;
  is_rush: boolean; to_dau_ten: string | null; so_cong_doan: number;
}
export interface LsxListOut { items: LsxListItem[]; total: number }
export interface LsxDetail {
  id: number; ma: string; loai: string; lsx_goc_id: number | null; ten: string;
  trang_thai: LsxTrangThai;
  order_id: number; order_line_id: number; order_no: string | null;
  customer_name: string | null; customer_po_no: string | null; sale_name: string | null;
  quote_version_id: number | null; quote_number: string | null; quote_version_number: number | null;
  phieu_thanh_phan_id: number | null; ptg_id: number | null; ptg_ma: string | null;
  so_luong_dat: number; don_vi_tinh: string; bu_hao_to: number;
  so_to_ke_hoach: number; so_to_nguyen: number; so_con: number;
  ban_giao_at: string | null; han_giao_khach: string | null; han_hoan_thanh_sx: string | null;
  is_rush: boolean;
  quy_cach_json: Record<string, unknown> | null;
  khuon_be_id: number | null; khuon_be_ten: string | null;
  may_id: number | null; may_ten: string | null;
  nguoi_phu_trach_id: number | null; nguoi_phu_trach_ten: string | null;
  ghi_chu: string | null; created_at: string; updated_at: string;
  cong_doans: LsxCongDoan[];
  /** Hai rổ TÁCH BẠCH: `thieu` chặn nút Sẵn sàng; `canh_bao` chỉ tô màu. */
  thieu: string[];
  canh_bao: string[];
  lead_time: LsxLeadTime | null;
}
export interface LsxUpdateBody {
  ten?: string; so_luong_dat?: number; don_vi_tinh?: string; bu_hao_to?: number;
  so_to_ke_hoach?: number; so_to_nguyen?: number; so_con?: number;
  han_hoan_thanh_sx?: string | null; is_rush?: boolean;
  khuon_be_id?: number | null; may_id?: number | null;
  nguoi_phu_trach_id?: number | null; ghi_chu?: string | null;
}
export interface LsxActivity { at: string; actor_name: string | null; action: string; detail: string }

export function connectQuoteEvents(token: string, onEvent: (e: QuoteEvent) => void): () => void {
  let closed = false;
  let controller: AbortController | null = null;
  let current = token;

  async function loop(): Promise<void> {
    while (!closed) {
      controller = new AbortController();
      try {
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
        /* lỗi mạng/stream → reconnect sau backoff */
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
  /** Bộ nguyên tắc lương của phòng (Pha 1). */
  salary_mechanism?: SalaryMechanism;
  probation_ratio?: number;
  has_piece_work?: boolean;
  /** Đánh dấu khối SẢN XUẤT (spec §13.1). Effective tính theo cây ở FE (self hoặc tổ tiên tick). */
  la_san_xuat?: boolean;
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
  has_piece_work: boolean;
}

/** Một dòng mức lương trong "bảng lương của phòng" (Pha 1, lát 2). */
export interface DepartmentSalaryRow {
  id: number;
  department_id: number;
  label: string;
  apply_by: SalaryMechanism;
  pay_grade_key?: string | null;
  seniority_band?: string | null;
  gender?: string | null;
  luong_vi_tri: number;
  luong_trach_nhiem: number;
  phu_cap: number;
  chuyen_can: number;
  sort_order: number;
  is_active: boolean;
}

export interface DepartmentSalaryRowInput {
  label: string;
  apply_by: SalaryMechanism;
  pay_grade_key?: string | null;
  seniority_band?: string | null;
  gender?: string | null;
  luong_vi_tri: number;
  luong_trach_nhiem: number;
  phu_cap: number;
  chuyen_can: number;
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
  /** khach_hang — thiết lập điều khoản tín dụng khách (hạn mức + điều khoản thanh toán). */
  can_set_credit_terms: boolean;
  can_record_deposit: boolean;
  can_assign_work: boolean;
  can_record_output: boolean;
  can_handover: boolean;
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
  can_set_credit_terms: boolean;
  can_record_deposit: boolean;
  can_assign_work: boolean;
  can_record_output: boolean;
  can_handover: boolean;
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
  to_dau_vao: number;
  to_sau_in: number;
  bu_hao_auto?: number; // Σ bù hao công đoạn tự tra (theo số tờ cần in)
  bu_hao_tay?: number; // số bù nhập tay (cộng thêm)
  hao_tay?: number; // số hao nhập tay (trừ bớt)
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

/** Bình bài NGHỊCH (POST /api/tinh-gia/binh-bai-nghich) — số con ĐÚNG N → khổ tờ in ít phế nhất.
 *  Yêu cầu khổ giấy nguyên > 0 (caller KHÔNG gọi khi nguyên trống). con=0 = không xếp được đúng N. */
export interface BinhBaiNghichIn {
  con: number;
  dai_thanh_pham: number;
  rong_thanh_pham: number;
  chua_mm: number;
  kho_nguyen_dai: number;
  kho_nguyen_rong: number;
  kho_may_dai?: number;
  kho_may_rong?: number;
}
export interface BinhBaiNghichOut {
  con: number;          // 0 = không xếp được đúng N mà lọt tờ nguyên
  kho_in_dai: number;
  kho_in_rong: number;
  rows: number;
  cols: number;
  rotated: boolean;
  so_to_in: number;     // số tờ in xả được từ 1 tờ giấy nguyên
  hieu_suat: number;
  util_pct: number;     // % diện tích tờ nguyên thành thành phẩm
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
  bu_hao_so_to: number;
  hao_so_to: number;
  tinh_bu_hao_cd: boolean;
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
  don_vi_tinh?: string | null; // ĐVT sản phẩm (text tự do)
  loai_san_pham_id?: number | null; // loại SP của sản phẩm này
  giay_id?: number | null;
  kho_nguyen?: string | null;
  kho_nguyen_dai?: number;
  kho_nguyen_rong?: number;
  don_gia_giay?: number;
  don_gia_don_vi?: string;
  nguon_giay?: string;
  bu_hao_so_to?: number;
  hao_so_to?: number;
  tinh_bu_hao_cd?: boolean;
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
  total_cost?: number | null;   // giá vốn khóa (so sánh phiên bản)
  subtotal?: number | null;     // giá bán chưa VAT
  discount?: number | null;     // chiết khấu
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
  /** Khách chốt một phần: true = khách ưng (kéo lên đơn), false = không lấy. Chỉ có nghĩa khi báo giá đã accepted. */
  accepted: boolean;
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
  /** BG-1 (nguồn MỚI): 1 Phiếu tính giá (PTG) → 1 báo giá. */
  phieu_tinh_gia_id?: number | null;
  estimate_id?: number | null;
  selected_option_ids?: number[] | null;
  /** Đường đa phiếu (cũ): mỗi pick = 1 phiếu tính giá + option đã tick. */
  picks?: QuotePick[] | null;
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
  role_name: string | null;
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
  /** Vai trò để gán cho tài khoản. Role thuộc ĐÚNG 1 phòng ban → lọc theo phòng của hồ sơ. */
  roles: { id: number; name: string; department_id: number }[];
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
  cong_doan_rate: number;
  deduction_self: number;
  deduction_dependent: number;
  chuyen_can_default: number;
  standard_hours_per_day: number;
  ot_multiplier: number;
  ot_multiplier_restday: number;
  ot_multiplier_holiday: number;
  restday_work_multiplier: number;
  holiday_work_multiplier: number;
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
  source_salary_row_id: number | null;
  insurance_base: number | null;
  allowance: number;
  chuyen_can: number;
  note: string | null;
  created_at: string;
}
export interface EmployeeSalaryInput {
  effective_from: string;
  amount_mode: string;
  base_amount?: number | null;
  /** Trỏ 1 dòng bảng lương của tổ → engine đọc sống (amount_mode tự thành 'dept_row'). */
  source_salary_row_id?: number | null;
  insurance_base?: number | null;
  /** Phụ cấp của riêng NV (mỗi người mỗi khác). */
  allowance?: number;
  /** Chuyên cần của riêng NV (mỗi người mỗi khác). */
  chuyen_can?: number;
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
  thuong_5s: number;
  thuong_doanh_so: number;
  thuong_thanh_tich: number;
  phep_nam: number;
  tra_dong_phuc: number;
  dieu_chinh_luong: number;
  di_tre: number;
  dt_vuot_troi: number;
  phat_bien_ban: number;
  phat_5s_dong_phuc: number;
  gross: number;
  insurance_base: number;
  bhxh: number;
  cong_doan: number;
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
  thuong_5s?: number | null;
  thuong_doanh_so?: number | null;
  thuong_thanh_tich?: number | null;
  phep_nam?: number | null;
  tra_dong_phuc?: number | null;
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

export interface PaymentVoucherAccountsInput {
  /** Định khoản in trên mẫu ("242, 1331" / "1111") — nhập tay, không bắt buộc. */
  debit_account?: string | null;
  credit_account?: string | null;
}

export interface PaymentVoucherBaseInput extends PaymentVoucherAccountsInput {
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
  /** Số IN trên mẫu 02-TT (PC00445) — khác `code` (mã tra cứu nội bộ). */
  doc_no: string | null;
  debit_account: string | null;
  credit_account: string | null;
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
  note?: string | null;
}

export interface PaymentReceiptRow {
  id: number;
  code: string;
  /** Số IN trên mẫu 01-TT (PT00027). */
  doc_no: string | null;
  payment_voucher_id: number;
  payment_voucher_code: string;
  purchase_request_id: number;
  purchase_request_code: string;
  supplier_name: string;
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
  source_type: string;
  order_kind: string;
  order_nature: string;
  status: string;
  is_rush: boolean;
  approval_state: string;
  needs_approval: boolean;
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
  invoice_entity_name: string | null;
  invoice_entity_tax_code: string | null;
  vat_pct_estimate: number;
  lines: OrderLineOut[];
  order_cost: number | null;
  margin_pct: number | null;
  cancel_reason: string | null;
  cancel_fault: string | null;
  deposits: OrderDepositReceipt[];   // V5: phiếu thu cọc THẬT (PaymentReceipt nguồn đơn)
  approvals: OrderApprovalOut[];
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
  pending_approval: number;
  awaiting_deposit: number;
  deposit_shortfall: number;
  ordered_value: number;
}
export interface OrderLineInput {
  description?: string;
  qty: number;
  don_vi_tinh?: string | null;   // ĐVT (text tự do); bỏ trống → "cái"
  unit_price?: number | null;
  vat_pct?: number;
}
export interface OrderCreateInput {
  source_type: string;
  quotation_id?: number | null;
  order_kind?: string;
  parent_order_id?: number | null;
  order_nature?: string;
  customer_id?: number | null;
  lines?: OrderLineInput[];
  vat_pct_estimate?: number;
  deposit_pct?: number | null;
  customer_po_no?: string | null;
  delivery_committed_date?: string | null;
  delivery_address?: string | null;
  delivery_contact_name?: string | null;
  delivery_contact_phone?: string | null;
  delivery_note?: string | null;
  production_note?: string | null;
  invoice_entity_name?: string | null;
  invoice_entity_tax_code?: string | null;
  is_rush?: boolean;
}
export interface OrderUpdateInput {
  order_nature?: string | null;
  deposit_pct?: number | null;
  customer_po_no?: string | null;
  delivery_committed_date?: string | null;
  delivery_address?: string | null;
  delivery_contact_name?: string | null;
  delivery_contact_phone?: string | null;
  delivery_note?: string | null;
  production_note?: string | null;
  invoice_entity_name?: string | null;
  invoice_entity_tax_code?: string | null;
  is_rush?: boolean | null;
}
export interface OrderNotifySummary {
  action_count: number;
  approval_pending: number;
  deposit_pending: number;
  ready_to_confirm: number;
}
export interface OrderEnumOption {
  value: string;
  label: string;
}
export interface OrderEnumsOut {
  source_types: OrderEnumOption[];
  order_natures: OrderEnumOption[];
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
  approval_state?: string;
  view_scope?: string;
  sort?: string;
  page?: number;
  size?: number;
}

// --- Khuôn bế (danh mục dùng chung) ---------------------------------------
export interface KhuonBeRow {
  id: number;
  ma: string;
  ten: string;
  khach_hang: string | null;
  so_ke: string | null;
  tinh_trang: string;
  active: boolean;
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
        }),
      });
    },
    /** Departments that would be deleted with this one's branch (spec-05 confirm). */
    departmentSubtree(token: string, id: number): Promise<DepartmentSubtreeRow[]> {
      return authed<DepartmentSubtreeRow[]>(`/api/departments/${id}/subtree`, token);
    },
    /** Bảng lương của phòng (Pha 1, lát 2). */
    listSalaryRows(token: string, deptId: number): Promise<DepartmentSalaryRow[]> {
      return authed<DepartmentSalaryRow[]>(
        `/api/departments/${deptId}/salary-rows`,
        token,
      );
    },
    createSalaryRow(
      token: string,
      deptId: number,
      input: DepartmentSalaryRowInput,
    ): Promise<DepartmentSalaryRow> {
      return authed<DepartmentSalaryRow>(
        `/api/departments/${deptId}/salary-rows`,
        token,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    updateSalaryRow(
      token: string,
      rowId: number,
      input: DepartmentSalaryRowInput,
    ): Promise<DepartmentSalaryRow> {
      return authed<DepartmentSalaryRow>(
        `/api/departments/salary-rows/${rowId}`,
        token,
        { method: "PUT", body: JSON.stringify(input) },
      );
    },
    deleteSalaryRow(token: string, rowId: number): Promise<void> {
      return authed<void>(`/api/departments/salary-rows/${rowId}`, token, {
        method: "DELETE",
      });
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
    /** Dòng bảng lương của tổ — cho form thêm NV chọn mức (gác quyền nhân sự). */
    salaryRows(token: string, deptId: number): Promise<DepartmentSalaryRow[]> {
      return authed<DepartmentSalaryRow[]>(`/api/employees/meta/salary-rows/${deptId}`, token);
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
    /** Dòng bảng lương của tổ — cho SalaryModal chọn/sửa mức theo dòng tổ (gác quyền lương). */
    salaryRows(token: string, deptId: number): Promise<DepartmentSalaryRow[]> {
      return authed<DepartmentSalaryRow[]>(`/api/luong/salary-rows/${deptId}`, token);
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
  },

  // --- Tính giá thành — chỉ còn bình bài live; tính giá vốn đi qua phiếu (phieuTinhGia) ---
  tinhGia: {
    binhBai(token: string, body: BinhBaiIn): Promise<BinhBaiOut> {
      return authed<BinhBaiOut>("/api/tinh-gia/binh-bai", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    /** Bình bài NGHỊCH: số con ĐÚNG N → khổ tờ in ít phế nhất (xả từ tờ giấy nguyên). */
    binhBaiNghich(token: string, body: BinhBaiNghichIn): Promise<BinhBaiNghichOut> {
      return authed<BinhBaiNghichOut>("/api/tinh-gia/binh-bai-nghich", token, {
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
    /** Gợi ý SL vào/ra cho cả chuỗi, chạy ngược từ SL thành phẩm. CHỈ ĐỌC — không ghi gì. */
    tinhNguoc(token: string, id: number): Promise<LsxTinhNguocOut> {
      return authed<LsxTinhNguocOut>(`/api/lsx/${id}/tinh-nguoc`, token);
    },
    /** Bộ mặc định khi ĐỔI một bước sang công đoạn khác (loại bước · tổ · máy · đơn vị · chuẩn bị ·
     *  năng suất). Luật nằm ở backend — client chỉ áp kết quả, KHÔNG tự tính lại. */
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
    suaThanhVien(token: string, id: number, tvId: number, soConTrenTo: number): Promise<BaiGhepDetail> {
      return authed<BaiGhepDetail>(`/api/bai-ghep/${id}/thanh-vien/${tvId}`, token, {
        method: "PUT", body: JSON.stringify({ so_con_tren_to: soConTrenTo }),
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
    goPhatHanhLsx(token: string, lsxId: number): Promise<XepLichPhatHanhOut> {
      return authed<XepLichPhatHanhOut>(`/api/xep-lich/phat-hanh/lsx/${lsxId}`, token, { method: "DELETE" });
    },
    goPhatHanhBaiGhep(token: string, baiGhepId: number): Promise<XepLichPhatHanhOut> {
      return authed<XepLichPhatHanhOut>(`/api/xep-lich/phat-hanh/bai-ghep/${baiGhepId}`, token, { method: "DELETE" });
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
  },

  orders: {
    list(token: string, params: OrderListParams = {}): Promise<OrderListOut> {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.status) qs.set("status", params.status);
      if (params.order_kind) qs.set("order_kind", params.order_kind);
      if (params.approval_state) qs.set("approval_state", params.approval_state);
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
    submit(token: string, id: number): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/submit`, token, { method: "POST" });
    },
    approve(token: string, id: number, note: string | null): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/approve`, token, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
    },
    reject(token: string, id: number, note: string): Promise<OrderDetail> {
      return authed<OrderDetail>(`/api/orders/${id}/reject`, token, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
    },
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

  // --- Sản xuất: Lệnh sản xuất (LSX) ---------------------------------------

  // --- Công đoạn (danh mục, lite cho dropdown) -----------------------------
  congDoan: {
    // size ≤ 200 — router chặn `le=200`, gửi 500 là 422 (đừng nâng lại).
    list(token: string): Promise<{ items: CongDoanLite[] }> {
      return authed<{ items: CongDoanLite[] }>("/api/cong-doan?size=200", token);
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
