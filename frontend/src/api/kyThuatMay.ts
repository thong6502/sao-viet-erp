// API — Kỹ thuật máy (Sửa chữa máy + Phiếu bảo trì). Dùng chung `authed` của client.ts.
//
// Chu kỳ bảo trì KHÔNG khai ở màn này: nguồn là gói trong `may_thiet_bi.fields_theo_loai
// .lich_bao_tri` (tab "Lịch bảo trì" màn Thiết bị). Phiếu định kỳ ra đời bằng HAI đường: ticker nền
// tự sinh khi tới hạn, hoặc người dùng bấm một ô KỲ DỰ KIẾN trên màn Lịch (`lich()` +
// `createBaoTri` kèm `goi_id`). Không có đường đẻ hàng loạt.
import { authed } from "./client";

export type LoaiPhieu = "sua_chua" | "bao_tri";

// --- Trạng thái + nhãn: khai MỘT chỗ, cả bảng lẫn drawer lẫn tab đọc chung ---------------------
export const TT_SUA_CHUA = ["cho_sua", "dang_sua", "cho_vat_tu", "da_sua_xong"] as const;
export const NHAN_TT_SUA_CHUA: Record<string, string> = {
  cho_sua: "Chờ sửa",
  dang_sua: "Đang sửa",
  cho_vat_tu: "Chờ vật tư",
  da_sua_xong: "Đã sửa xong",
};
// Bảo trì chỉ có HAI nấc (12/08/2026): chờ làm → xong. Nấc "đang thực hiện" và bước nhận việc đã
// bỏ — ai bấm "Xác nhận đã bảo trì xong" thì chính người đó là người làm.
export const TT_BAO_TRI = ["cho_thuc_hien", "hoan_thanh"] as const;
export const NHAN_TT_BAO_TRI: Record<string, string> = {
  cho_thuc_hien: "Chờ thực hiện",
  hoan_thanh: "Hoàn thành",
};
export const NHAN_MUC_DO: Record<string, string> = {
  nhe: "Nhẹ",
  trung_binh: "Trung bình",
  nghiem_trong: "Nghiêm trọng",
};
export const NHAN_DON_VI_CHU_KY: Record<string, string> = {
  ngay: "ngày", tuan: "tuần", thang: "tháng", nam: "năm",
};

export interface SuaChua {
  id: number;
  ma: string;
  may_id: number;
  bo_phan_hong: string;
  mo_ta: string | null;
  muc_do: string;
  nguoi_bao_id: number | null;
  nguoi_bao_ten: string | null;
  thoi_diem: string | null;
  nguyen_nhan_phuong_an: string | null;
  trang_thai: string;
  hoan_thanh_at: string | null;
  ghi_chu: string | null;
  // dẫn xuất (backend bơm) — KHÔNG gửi lên khi lưu
  may_ma: string | null;
  may_ten: string | null;
  so_anh: number;
  co_anh_sau: boolean;
}

export interface HangMuc {
  id?: string | null;
  ten: string;
  xong: boolean;
  /** "Không áp dụng lần này" — mở cửa đóng phiếu mà không phải tick dối, BẮT BUỘC kèm lý do. */
  bo_qua?: boolean;
  ly_do_bo_qua?: string | null;
}

export interface BaoTri {
  id: number;
  ma: string;
  may_id: number;
  goi_id: string | null;
  goi_ten: string | null;
  chu_ky_so: number | null;
  chu_ky_don_vi: string | null;
  loai: string;
  ngay_ke_hoach: string;
  ngay_ke_hoach_goc: string | null;
  ly_do_doi: string | null;
  hang_muc: HangMuc[] | null;
  /** NGƯỜI LÀM — backend gán từ tài khoản bấm "Xác nhận đã bảo trì xong" (không có bước nhận việc
   *  riêng, phiếu chưa xong không mang tên ai). FE không gửi lên. */
  nguoi_thuc_hien_id: number | null;
  nguoi_thuc_hien: string | null;
  trang_thai: string;
  ngay_hoan_thanh: string | null;
  ghi_chu: string | null;
  // dẫn xuất
  may_ma: string | null;
  may_ten: string | null;
  /** Nhóm máy trong danh mục (`may_thiet_bi.loai_may`) — màn Lịch lọc theo cái này. */
  may_loai: string | null;
  so_anh: number;
  co_anh_sau: boolean;
  qua_han: boolean;
  da_doi: boolean;
}

export interface PhieuListOut<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  /** Số cho dãy tab, đếm Ở DB theo ĐÚNG bộ lọc đang xem (trừ trạng thái) — không phải đếm trang
   *  hiện tại, cũng không phải đếm cả bảng. Riêng bảo trì có thêm 3 khoá dẫn xuất theo ngày:
   *  `qua_han` · `den_hom_nay` · `tuan_nay`. */
  dem: Record<string, number>;
}

export interface Anh {
  id: number;
  loai_phieu: string;
  phieu_id: number;
  giai_doan: "truoc" | "sau";
  file_name: string;
  file_url: string;
  file_type: string | null;
  uploaded_at: string | null;
}


/** Kỳ bảo trì tương lai CHƯA có phiếu — vẽ mờ trên lịch, bấm vào là tạo phiếu thật.
 *  Không lưu ở bảng nào: backend tính lúc đọc từ chu kỳ gói trên máy. */
export interface DuKien {
  may_id: number;
  may_ma: string;
  may_ten: string | null;
  may_loai: string | null;
  goi_id: string | null;
  goi_ten: string | null;
  ngay: string;
  chu_ky_so: number | null;
  chu_ky_don_vi: string | null;
}

export interface LichKq {
  phieu: BaoTri[];
  du_kien: DuKien[];
}

export interface HanGoi {
  goi_id: string | null;
  goi_ten: string | null;
  han: string | null;
  /** phieu | ngay_bat_dau | thieu_chu_ky | thieu_ngay_bat_dau — nói rõ hạn tính từ đâu, hoặc vì
   *  sao KHÔNG tính được (hai lý do là hai ô khác nhau trên form Máy). */
  nguon: string;
  phieu_dang_mo_id: number | null;
}

const P = "/api/ky-thuat-may";

function qs(params: Record<string, unknown>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : "";
}

export const kyThuatMay = {
  // ---- Sửa chữa ----
  // `size` mặc định 20 và LỌC Ở SERVER: trước đây kéo 200 dòng rồi lọc trên mảng ⇒ qua phiếu thứ
  // 201 là bảng âm thầm cắt mất trong khi số trên tab (đếm ở DB) vẫn đúng.
  listSuaChua(token: string, params: Record<string, unknown> = {}): Promise<PhieuListOut<SuaChua>> {
    return authed<PhieuListOut<SuaChua>>(`${P}/sua-chua${qs({ size: 20, ...params })}`, token);
  },
  /** MỘT phiếu. Dùng để nạp lại phiếu đang mở trong drawer — kéo cả danh sách rồi `find` thì phiếu
   *  nằm ngoài trang 1 sẽ không tìm thấy, và cờ `co_anh_sau` đứng im dù ảnh đã tải lên. */
  getSuaChua(token: string, id: number): Promise<SuaChua> {
    return authed<SuaChua>(`${P}/sua-chua/${id}`, token);
  },
  createSuaChua(token: string, body: Record<string, unknown>): Promise<SuaChua> {
    return authed<SuaChua>(`${P}/sua-chua`, token, { method: "POST", body: JSON.stringify(body) });
  },
  updateSuaChua(token: string, id: number, body: Record<string, unknown>): Promise<SuaChua> {
    return authed<SuaChua>(`${P}/sua-chua/${id}`, token, { method: "PUT", body: JSON.stringify(body) });
  },
  trangThaiSuaChua(token: string, id: number, trang_thai: string): Promise<SuaChua> {
    return authed<SuaChua>(`${P}/sua-chua/${id}/trang-thai`, token, {
      method: "POST", body: JSON.stringify({ trang_thai }),
    });
  },
  // KHÔNG có `removeSuaChua`/`removeBaoTri` (12/08/2026): phiếu là vết của việc đã xảy ra, backend
  // cũng không còn endpoint DELETE. Ghi nhầm thì sửa nội dung.

  // ---- Bảo trì ----
  /** `trang_thai` nhận cả 2 giá trị dẫn xuất: `can_lam` (chưa xong) · `qua_han` (trễ ngày). */
  listBaoTri(token: string, params: Record<string, unknown> = {}): Promise<PhieuListOut<BaoTri>> {
    return authed<PhieuListOut<BaoTri>>(`${P}/bao-tri${qs({ size: 20, ...params })}`, token);
  },
  /** MỘT phiếu — xem ghi chú ở `getSuaChua`. */
  getBaoTri(token: string, id: number): Promise<BaoTri> {
    return authed<BaoTri>(`${P}/bao-tri/${id}`, token);
  },
  createBaoTri(token: string, body: Record<string, unknown>): Promise<BaoTri> {
    return authed<BaoTri>(`${P}/bao-tri`, token, { method: "POST", body: JSON.stringify(body) });
  },
  updateBaoTri(token: string, id: number, body: Record<string, unknown>): Promise<BaoTri> {
    return authed<BaoTri>(`${P}/bao-tri/${id}`, token, { method: "PUT", body: JSON.stringify(body) });
  },
  /** Tick một việc con. `bo_qua` = đánh "không áp dụng lần này" (bắt buộc `ly_do` — service chặn). */
  tickHangMuc(
    token: string, id: number, hang_muc_id: string, xong: boolean,
    them?: { bo_qua?: boolean; ly_do?: string },
  ): Promise<BaoTri> {
    return authed<BaoTri>(`${P}/bao-tri/${id}/hang-muc`, token, {
      method: "POST", body: JSON.stringify({ hang_muc_id, xong, ...(them ?? {}) }),
    });
  },
  doiLich(token: string, id: number, ngay_moi: string, ly_do: string): Promise<BaoTri> {
    return authed<BaoTri>(`${P}/bao-tri/${id}/doi-lich`, token, {
      method: "POST", body: JSON.stringify({ ngay_moi, ly_do }),
    });
  },
  trangThaiBaoTri(
    token: string, id: number, trang_thai: string, ngay_hoan_thanh?: string | null,
  ): Promise<BaoTri> {
    return authed<BaoTri>(`${P}/bao-tri/${id}/trang-thai`, token, {
      method: "POST", body: JSON.stringify({ trang_thai, ngay_hoan_thanh: ngay_hoan_thanh ?? null }),
    });
  },
  /** Badge thanh bên: số phiếu tới hạn/quá hạn còn dở. */
  denHan(token: string): Promise<{ total: number; qua_han: number }> {
    return authed<{ total: number; qua_han: number }>(`${P}/bao-tri/den-han`, token);
  },
  /** Lịch tháng: phiếu thật + kỳ dự kiến. Backend chặn khoảng > 1 năm. */
  lich(token: string, tu: string, den: string): Promise<LichKq> {
    return authed<LichKq>(`${P}/bao-tri/lich${qs({ tu, den })}`, token);
  },
  /** Hạn kế tiếp từng gói của MỘT máy — tab "Lịch bảo trì" ở màn Thiết bị đọc cái này. */
  hanCuaMay(token: string, mayId: number): Promise<HanGoi[]> {
    return authed<{ items: HanGoi[] }>(`${P}/bao-tri/han/${mayId}`, token).then((r) => r.items ?? []);
  },

  // ---- Ảnh (dùng chung 2 loại phiếu) ----
  listAnh(token: string, loai: LoaiPhieu, phieuId: number): Promise<Anh[]> {
    return authed<{ items: Anh[] }>(`${P}/${loai}/${phieuId}/anh`, token).then((r) => r.items ?? []);
  },
  uploadAnh(
    token: string, loai: LoaiPhieu, phieuId: number, file: File, giaiDoan: "truoc" | "sau",
  ): Promise<Anh> {
    const form = new FormData();
    form.append("file", file);
    // Trình duyệt tự đặt boundary cho FormData — `authed` đã biết không ép Content-Type JSON.
    return authed<Anh>(`${P}/${loai}/${phieuId}/anh?giai_doan=${giaiDoan}`, token, {
      method: "POST", body: form,
    });
  },
  removeAnh(token: string, anhId: number): Promise<void> {
    return authed<void>(`${P}/anh/${anhId}`, token, { method: "DELETE" });
  },
};
