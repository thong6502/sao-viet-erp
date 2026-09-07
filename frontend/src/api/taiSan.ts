// API — Tài sản cố định & Công cụ dụng cụ (kế toán). Dùng chung `authed` của client.ts.
//
// KHÔNG có ô tài khoản kế toán ở bất kỳ đâu trong module này. Định khoản là việc của phần mềm kế
// toán bên ngoài; ở đây kế toán tự gõ vào ô `ghi_chu_hach_toan` (vd "211 / 6274 - tổ In") và ô đó
// đi thẳng ra cột cuối của file Excel bảng khấu hao. Đừng thêm ô tài khoản "cho tiện" — bỏ ô ghi
// chú đi thì cả module mất lý do tồn tại ở dạng này.
import { authed, ApiError } from "./client";

const P = "/api/tai-san";

// BASE_URL của client.ts KHÔNG được export nên đường tải file phải tự dựng lại y hệt. Sửa ở
// client.ts thì sửa cả đây (một dòng, và chỉ đường xuất Excel dùng tới).
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

// --- Nhãn: khai MỘT chỗ, bảng · dialog · tab đọc chung -----------------------------------------
export const NHAN_LOAI: Record<string, string> = {
  tscd: "Tài sản cố định",
  ccdc: "Công cụ dụng cụ",
};
export const NHAN_TRANG_THAI: Record<string, string> = {
  dang_dung: "Đang dùng",
  da_giam: "Đã ghi giảm",
};
export const NHAN_BIEN_DONG: Record<string, string> = {
  dieu_chuyen: "Điều chuyển",
  nang_cap: "Nâng cấp",
  ghi_giam: "Ghi giảm",
};
export const NHAN_NGUON_VAO: Record<string, string> = {
  ghi_tang: "Mua mới / ghi tăng",
  dau_ky: "Số dư đầu kỳ",
};
export const NHAN_TRANG_THAI_KY: Record<string, string> = {
  mo: "Đang mở",
  da_chot: "Đã chốt",
};
/** Lý do ghi giảm — danh sách gợi ý, người dùng vẫn gõ được câu khác. */
export const LY_DO_GHI_GIAM = [
  "Thanh lý",
  "Nhượng bán",
  "Mất",
  "Hỏng không sửa được",
  "Góp vốn",
] as const;

/** Ngưỡng TSCĐ theo TT 45/2013 — CẢNH BÁO MỀM thôi, không chặn: ngưỡng do Bộ Tài chính đổi, mà
 *  phần mềm chặn cứng thì đúng ngày nó đổi là kế toán không ghi được tài sản nào. */
export const NGUONG_TSCD = 30_000_000;

// --- Kiểu dữ liệu ------------------------------------------------------------------------------

export interface ChiPhi {
  id: number;
  dien_giai: string;
  so_tien: number;
}

export interface TaiSanRow {
  id: number;
  ma: string;
  ten: string;
  loai: string;
  so_luong: number;
  don_gia: number | null;
  nguyen_gia: number;
  so_thang: number;
  so_thang_con: number;
  ngay_su_dung: string;
  moc_tu_ngay: string;
  hao_mon_luy_ke: number;
  co_so_trich: number;
  nguon_vao: string;
  bo_phan_id: number | null;
  bo_phan_ten: string | null;
  nguoi_quan_ly: string | null;
  vi_tri: string | null;
  so_hoa_don: string | null;
  nha_cung_cap: string | null;
  ghi_chu_hach_toan: string | null;
  ghi_chu: string | null;
  trang_thai: string;
  ngay_giam: string | null;
  /** Nguyên giá − hao mòn lũy kế (chốt tại kỳ đã chốt gần nhất). */
  con_lai: number;
}

export interface BienDong {
  id: number;
  loai: string;
  ngay: string;
  so_tien: number | null;
  bo_phan_moi_id: number | null;
  so_thang_con_lai: number | null;
  so_luong_giam: number | null;
  ly_do: string | null;
  ghi_chu_hach_toan: string | null;
  created_at: string | null;
}

export interface KhauHaoDong {
  ky_nam: number;
  ky_thang: number;
  muc_trich: number;
  luy_ke: number;
  con_lai: number;
}

export interface TaiSanChiTiet extends TaiSanRow {
  chi_phi: ChiPhi[];
  bien_dong: BienDong[];
  khau_hao: KhauHaoDong[];
  /** Giá bán − giá trị còn lại của chứng từ ghi giảm mới nhất. `null` = chưa khai giá bán. */
  chenh_lech_thanh_ly: number | null;
}

export interface DongDuKien {
  nam: number;
  thang: number;
  muc_trich: number;
  luy_ke: number;
  con_lai: number;
}

export interface Ky {
  ky_nam: number;
  ky_thang: number;
  trang_thai: string;
  ngay_chot: string | null;
}

export interface HangBangKy {
  tai_san_id: number;
  ma: string;
  ten: string;
  loai: string;
  bo_phan_ten: string | null;
  nguyen_gia: number;
  muc_trich: number;
  luy_ke: number;
  con_lai: number;
  ghi_chu_hach_toan: string | null;
}

export interface BangKy {
  nam: number;
  thang: number;
  trang_thai: string;
  tong_muc_trich: number;
  items: HangBangKy[];
}

export interface KiemKeDong {
  id: number;
  tai_san_id: number | null;
  ma: string | null;
  ten: string | null;
  ket_qua: string | null;
  ten_phat_hien: string | null;
  tinh_trang: string | null;
  ghi_chu: string | null;
}

export interface KiemKeRow {
  id: number;
  ma: string;
  ngay: string;
  bo_phan_id: number | null;
  trang_thai: string;
  ghi_chu: string | null;
}

export interface KiemKeChiTiet extends KiemKeRow {
  dong: KiemKeDong[];
}

export interface KetQuaKiemKe {
  /** Có trong sổ, đi kiểm không thấy. */
  thieu: KiemKeDong[];
  /** Thấy ở xưởng, không có trong sổ. */
  thua: KiemKeDong[];
}

export interface DanhSach<T> {
  items: T[];
  total: number;
}

function qs(params: Record<string, unknown>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : "";
}

export const taiSanApi = {
  // ---- Sổ tài sản ----
  /** Lọc + phân trang Ở MÁY CHỦ. Đừng kéo hết về rồi `filter` trên mảng: sổ tài sản của xưởng in
   *  vài trăm dòng, lọc trong JS là qua trang thứ hai số liệu bắt đầu sai mà không ai báo. */
  danhSach(token: string, params: Record<string, unknown> = {}): Promise<DanhSach<TaiSanRow>> {
    return authed<DanhSach<TaiSanRow>>(`${P}${qs(params)}`, token);
  },
  chiTiet(token: string, id: number): Promise<TaiSanChiTiet> {
    return authed<TaiSanChiTiet>(`${P}/${id}`, token);
  },
  /** Ghi tăng (mua mới) HOẶC nạp số dư đầu kỳ — phân biệt bằng `nguon_vao` trong body. */
  ghiTang(token: string, body: Record<string, unknown>): Promise<TaiSanRow> {
    return authed<TaiSanRow>(P, token, { method: "POST", body: JSON.stringify(body) });
  },
  sua(token: string, id: number, body: Record<string, unknown>): Promise<TaiSanRow> {
    return authed<TaiSanRow>(`${P}/${id}`, token, { method: "PUT", body: JSON.stringify(body) });
  },
  xoa(token: string, id: number): Promise<void> {
    return authed<void>(`${P}/${id}`, token, { method: "DELETE" });
  },
  /** Bảng khấu hao DỰ KIẾN của một tài sản — xem trước, chưa ghi sổ kỳ nào. */
  duKien(token: string, id: number): Promise<DongDuKien[]> {
    return authed<DongDuKien[]>(`${P}/${id}/du-kien`, token);
  },
  /** Một cửa cho cả ba chứng từ điều chuyển · nâng cấp · ghi giảm (`loai` quyết định ô bắt buộc). */
  bienDong(token: string, id: number, body: Record<string, unknown>): Promise<BienDong> {
    return authed<BienDong>(`${P}/${id}/bien-dong`, token, {
      method: "POST", body: JSON.stringify(body),
    });
  },

  // ---- Kỳ khấu hao ----
  dsKy(token: string): Promise<Ky[]> {
    return authed<Ky[]>(`${P}/ky`, token);
  },
  /** ĐỌC bảng kỳ đã tính (không tính lại) — kỳ chưa tính thì trả bảng rỗng. */
  bangKy(token: string, nam: number, thang: number): Promise<BangKy> {
    return authed<BangKy>(`${P}/ky/${nam}/${thang}/bang`, token);
  },
  /** TÍNH LẠI kỳ: xoá dòng cũ rồi ghi lại. Bấm bao nhiêu lần cũng ra một kết quả — `hao_mon_luy_ke`
   *  của tài sản KHÔNG nhúc nhích cho tới lúc chốt kỳ. */
  tinhKy(token: string, nam: number, thang: number): Promise<BangKy> {
    return authed<BangKy>(`${P}/ky/${nam}/${thang}/tinh`, token, { method: "POST" });
  },
  chotKy(token: string, nam: number, thang: number): Promise<Ky> {
    return authed<Ky>(`${P}/ky/${nam}/${thang}/chot`, token, { method: "POST" });
  },
  moKy(token: string, nam: number, thang: number): Promise<Ky> {
    return authed<Ky>(`${P}/ky/${nam}/${thang}/mo`, token, { method: "POST" });
  },
  /** Tải .xlsx bảng khấu hao kỳ. Trả blob URL — nơi gọi tự `revokeObjectURL` sau khi bấm tải. */
  async excelKy(token: string, nam: number, thang: number): Promise<string> {
    const resp = await fetch(`${BASE_URL}${P}/ky/${nam}/${thang}/excel`, {
      credentials: "include",
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (resp.status === 401) {
      // `refreshAccessToken` nằm private trong client.ts. Người dùng vừa bấm Tính xong mới bấm
      // Xuất nên token hết hạn đúng lúc này là hiếm — nói thẳng để họ tải lại trang, hơn là im lặng
      // trả về file 0 byte.
      throw new ApiError("Phiên đăng nhập đã hết hạn. Tải lại trang rồi xuất lại.", 401);
    }
    if (!resp.ok) throw new ApiError(`Xuất Excel thất bại (${resp.status}).`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },

  // ---- Kiểm kê ----
  dsKiemKe(token: string, params: Record<string, unknown> = {}): Promise<DanhSach<KiemKeRow>> {
    return authed<DanhSach<KiemKeRow>>(`${P}/kiem-ke${qs(params)}`, token);
  },
  chiTietKiemKe(token: string, dotId: number): Promise<KiemKeChiTiet> {
    return authed<KiemKeChiTiet>(`${P}/kiem-ke/${dotId}`, token);
  },
  /** Tạo đợt = BUNG SẴN một dòng cho mỗi tài sản đang dùng trong phạm vi. Người kiểm chỉ tick. */
  taoDotKiemKe(token: string, body: Record<string, unknown>): Promise<KiemKeChiTiet> {
    return authed<KiemKeChiTiet>(`${P}/kiem-ke`, token, {
      method: "POST", body: JSON.stringify(body),
    });
  },
  ghiKetQua(
    token: string, dotId: number, dongId: number, body: Record<string, unknown>,
  ): Promise<KiemKeChiTiet> {
    return authed<KiemKeChiTiet>(`${P}/kiem-ke/${dotId}/dong/${dongId}`, token, {
      method: "PUT", body: JSON.stringify(body),
    });
  },
  themPhatHien(token: string, dotId: number, body: Record<string, unknown>): Promise<KiemKeChiTiet> {
    return authed<KiemKeChiTiet>(`${P}/kiem-ke/${dotId}/phat-hien`, token, {
      method: "POST", body: JSON.stringify(body),
    });
  },
  /** Kết thúc đợt (KHÔNG mở lại được) → trả về hai danh sách thiếu / thừa. */
  ketThucKiemKe(token: string, dotId: number): Promise<KetQuaKiemKe> {
    return authed<KetQuaKiemKe>(`${P}/kiem-ke/${dotId}/ket-thuc`, token, { method: "POST" });
  },
};
