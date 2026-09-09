// API — Tài sản cố định & Công cụ dụng cụ (kế toán). Dùng chung `authed` của client.ts.
//
// KHÔNG có ô tài khoản kế toán ở bất kỳ đâu trong module này, và cũng không có ô định khoản
// riêng. Định khoản là việc của phần mềm kế toán bên ngoài; cần nhớ thì gõ vào ô `ghi_chu` của
// tài sản như mọi thứ khác. Đừng thêm ô tài khoản "cho tiện", cũng đừng đẻ lại ô định khoản
// riêng — hai ô ghi chú mà hệ không đọc ô nào thì người nhập chỉ còn cách đoán gõ vào đâu.
//
// KHÔNG có kỳ chốt (chốt 08/09/2026: "nó chỉ theo dõi khấu hao thôi"). Hao mòn lũy kế là số máy
// chủ TÍNH từ lịch của từng tài sản tới hết tháng trước; bảng của một tháng cũng tính tại chỗ —
// không có nút Tính, không Chốt, không Mở lại.
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
// `da_giam` / `ghi_giam` chỉ còn ở DỮ LIỆU CŨ: chủ bỏ nghiệp vụ ghi giảm 08/09/2026 — món bán,
// hỏng, không dùng nữa thì XOÁ khỏi sổ. Giữ nhãn để dòng cũ vẫn đọc được.
export const NHAN_TRANG_THAI: Record<string, string> = {
  dang_dung: "Đang dùng",
  da_giam: "Đã ghi giảm",
};
// `nang_cap` là tên mã; màn hình gọi là "Sửa chữa lớn" (chủ 08/09/2026: "nâng cấp thực chất là
// sửa chữa" — chỉ sửa chữa làm máy tốt hơn / dùng lâu hơn mới cộng vào nguyên giá).
export const NHAN_BIEN_DONG: Record<string, string> = {
  dieu_chuyen: "Điều chuyển",
  nang_cap: "Sửa chữa lớn",
  ghi_giam: "Ghi giảm",
};
export const NHAN_NGUON_VAO: Record<string, string> = {
  ghi_tang: "Mua mới / ghi tăng",
  dau_ky: "Số dư đầu kỳ",
};
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
  co_so_trich: number;
  nguon_vao: string;
  /** Chỉ `dau_ky`: số mang sang lúc lên phần mềm — gốc của mọi con số, không đổi sau khi lưu. */
  hao_mon_dau_ky: number;
  thang_da_trich_dau_ky: number;
  bo_phan_id: number | null;
  bo_phan_ten: string | null;
  /** Người quản lý = một nhân viên của bộ phận đang giữ (08/09/2026). `null` = chưa gán. */
  nguoi_quan_ly_id: number | null;
  /** Tên chụp từ hồ sơ nhân viên; dòng cũ có thể là chữ tự gõ. */
  nguoi_quan_ly: string | null;
  /** Cột còn trong DB, form không hỏi nữa (bỏ 08/09/2026). */
  vi_tri: string | null;
  so_hoa_don: string | null;
  /** Như `vi_tri`. */
  nha_cung_cap: string | null;
  ghi_chu: string | null;
  trang_thai: string;
  ngay_giam: string | null;
  /** Hao mòn lũy kế máy chủ TÍNH từ lịch, tới hết tháng `luy_ke_den`. Không ai chốt, không ai cộng. */
  hao_mon_luy_ke: number;
  /** "YYYY-MM" — tháng cuối đã gộp vào `hao_mon_luy_ke` (= tháng trước tháng hiện tại). */
  luy_ke_den: string;
  /** Nguyên giá − hao mòn lũy kế. */
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
  created_at: string | null;
}

/** Một tháng trong lịch khấu hao của một tài sản. */
export interface KhauHaoDong {
  nam: number;
  thang: number;
  muc_trich: number;
  luy_ke: number;
  con_lai: number;
}

export interface TaiSanChiTiet extends TaiSanRow {
  chi_phi: ChiPhi[];
  bien_dong: BienDong[];
  /** Phần lịch đã vào lũy kế (tới hết tháng trước). Phần sắp tới xem `duKien`. */
  khau_hao: KhauHaoDong[];
}

/** Một chuyện của tháng: nhãn ngắn (chip trên bảng) + câu đầy đủ (tooltip / ngăn chi tiết). */
export interface SuKien {
  /** `dau` | `dau_ky` | `nang_cap` | `bot` | `giam` | `chuyen` | `cuoi` — tô màu chip theo đây. */
  loai: string;
  nhan: string;
  chi_tiet: string;
}

export interface DongDuKien {
  nam: number;
  thang: number;
  muc_trich: number;
  luy_ke: number;
  /** Tháng ghi giảm = 0 (món đã ra khỏi sổ; giá trị lúc bỏ nằm trong sự kiện `giam`). */
  con_lai: number;
  su_kien: SuKien[];
  /** Các câu `chi_tiet` nối bằng "; " — chỗ nào chỉ cần một chuỗi. */
  dien_giai: string | null;
}

/** Một nhân viên đang làm của bộ phận — để chọn làm người quản lý. */
export interface NhanVienChon {
  id: number;
  code: string;
  full_name: string;
}

export interface HangBangThang {
  tai_san_id: number;
  ma: string;
  ten: string;
  loai: string;
  /** Lô CCDC còn mấy cái (TSCĐ = 1). */
  so_luong: number;
  bo_phan_ten: string | null;
  nguyen_gia: number;
  muc_trich: number;
  luy_ke: number;
  /** Tháng ghi giảm = 0 (món đã ra khỏi sổ). */
  con_lai: number;
  su_kien: SuKien[];
  /** Các câu `chi_tiet` nối bằng "; " (cột Diễn giải trên Excel); null nếu tháng bình thường. */
  dien_giai: string | null;
}

/** Bảng khấu hao một tháng — tính tại chỗ từ sổ, không có trạng thái chốt/mở. */
export interface BangThang {
  nam: number;
  thang: number;
  tong_muc_trich: number;
  items: HangBangThang[];
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
  /** Lịch khấu hao trọn đời của một tài sản — đã qua lẫn sắp tới, mỗi tháng một dòng. */
  duKien(token: string, id: number): Promise<DongDuKien[]> {
    return authed<DongDuKien[]>(`${P}/${id}/du-kien`, token);
  },
  /** Một cửa cho hai chứng từ điều chuyển · nâng cấp (`loai` quyết định ô bắt buộc). */
  bienDong(token: string, id: number, body: Record<string, unknown>): Promise<BienDong> {
    return authed<BienDong>(`${P}/${id}/bien-dong`, token, {
      method: "POST", body: JSON.stringify(body),
    });
  },

  /** Nhân viên đang làm của một bộ phận — đi qua quyền `tai_san.read`, không cần `nhan_su`. */
  nhanVienBoPhan(token: string, boPhanId: number): Promise<NhanVienChon[]> {
    return authed<NhanVienChon[]>(`${P}/nhan-vien?bo_phan_id=${boPhanId}`, token);
  },

  // ---- Bảng khấu hao tháng ----
  /** Bảng của một tháng, máy chủ tính tại chỗ từ sổ. Hỏi lại lúc nào cũng ra đúng một số. */
  bangThang(token: string, nam: number, thang: number): Promise<BangThang> {
    return authed<BangThang>(`${P}/thang/${nam}/${thang}`, token);
  },
  /** Tải .xlsx bảng khấu hao tháng. Trả blob URL — nơi gọi tự `revokeObjectURL` sau khi bấm tải. */
  async excelThang(token: string, nam: number, thang: number): Promise<string> {
    const resp = await fetch(`${BASE_URL}${P}/thang/${nam}/${thang}/excel`, {
      credentials: "include",
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (resp.status === 401) {
      // `refreshAccessToken` nằm private trong client.ts. Token hết hạn đúng lúc bấm Xuất là hiếm
      // — nói thẳng để họ tải lại trang, hơn là im lặng trả về file 0 byte.
      throw new ApiError("Phiên đăng nhập đã hết hạn. Tải lại trang rồi xuất lại.", 401);
    }
    if (!resp.ok) throw new ApiError(`Xuất Excel thất bại (${resp.status}).`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },
};
