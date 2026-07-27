// Mô hình 1 BƯỚC routing đang được sửa trên màn (dùng chung bảng + drawer).
//
// Tách riêng khỏi cả hai để không vòng import, và để chỗ nào cũng nhìn cùng một hình dạng dòng.
// Mọi ô số giữ dạng CHUỖI: ô trống ("") khác 0 — trống nghĩa là "chưa khai, dùng gợi ý", còn 0 là
// người dùng cố tình khai bằng 0. Ép sang number quá sớm sẽ xoá mất sự khác nhau đó.
import type { LsxCongDoan, LsxCongDoanBody, LsxLoaiBuoc } from "../api/client";

export interface EditRow {
  key: string;
  cong_doan_id: number | null;
  ten: string;
  nhom: string | null;
  loai_buoc: LsxLoaiBuoc;
  bat_buoc: boolean;
  department_id: number | null;
  may_id: number | null;
  may_thay_the_ids: number[];
  // số lượng & hao hụt
  so_luong_vao: string;
  so_luong_ra: string;
  don_vi_vao: string;
  don_vi_ra: string;
  he_so_quy_doi: string;
  hao_hut: string;
  hao_hut_pct: string;
  so_luot_chay: string;
  // năng suất & thời gian (phút)
  so_nhan_cong: string;
  setup_phut: string;
  nang_suat: string;
  don_vi_nang_suat: string;
  chay_phut: string;
  ve_sinh_phut: string;
  cho_phut: string;
  di_chuyen_phut: string;
  dieu_kien_json: string[];
  // gia công ngoài (§8)
  nha_cung_cap: string;
  sl_gui: string;
  ngay_gui_dk: string;
  van_chuyen_ngay: string;
  gia_cong_ngay: string;
  ngay_nhan_dk: string;
  hao_hut_cho_phep: string;
  don_gia_gia_cong: string;
  yeu_cau_ky_thuat: string;
  ghi_chu: string;
}

export const DON_VI: { key: string; label: string }[] = [
  { key: "to", label: "Tờ" },
  { key: "cai", label: "Con" },
  { key: "kem", label: "Kẽm" },
  { key: "bai", label: "Bài" },
];

export const DON_VI_NANG_SUAT: { key: string; label: string }[] = [
  { key: "to_gio", label: "tờ/giờ" },
  { key: "cai_gio", label: "con/giờ" },
  { key: "kem_gio", label: "kẽm/giờ" },
  { key: "bai_gio", label: "bài/giờ" },
];

/** Điều kiện bắt đầu (§4.5) — "công đoạn trước xong" là mặc định nên không có ô riêng. */
export const DIEU_KIEN: { key: string; label: string }[] = [
  { key: "co_vat_tu", label: "Vật tư đã sẵn" },
  { key: "file_duyet", label: "File đã duyệt" },
  { key: "kem_xong", label: "Kẽm đã xuất" },
  { key: "khuon_san_sang", label: "Khuôn đã sẵn sàng" },
  { key: "mau_mau_ky", label: "Mẫu màu đã ký" },
  { key: "nhan_tu_gia_cong", label: "Đã nhận từ nhà gia công" },
];

let seq = 0;
export function newKey(): string {
  seq += 1;
  return `r${seq}`;
}

/** Số → chuỗi cho ô nhập. 0 và null đều thành "" để hiện GỢI Ý ở placeholder. */
function s(v: number | null | undefined): string {
  return v ? String(v) : "";
}

/** Số → chuỗi nhưng GIỮ số 0 (ô người dùng chủ động khai, không có gợi ý). */
function s0(v: number | null | undefined): string {
  return v == null ? "" : String(v);
}

export function toEdit(cd: LsxCongDoan): EditRow {
  return {
    key: newKey(),
    cong_doan_id: cd.cong_doan_id,
    ten: cd.ten,
    nhom: cd.nhom,
    loai_buoc: cd.loai_buoc,
    bat_buoc: cd.bat_buoc,
    department_id: cd.department_id,
    may_id: cd.may_id,
    may_thay_the_ids: cd.may_thay_the_ids ?? [],
    so_luong_vao: s(cd.so_luong_vao),
    so_luong_ra: s(cd.so_luong_ra),
    don_vi_vao: cd.don_vi_vao || "to",
    don_vi_ra: cd.don_vi_ra || cd.don_vi_vao || "to",
    he_so_quy_doi: s(cd.he_so_quy_doi),
    hao_hut: s(cd.hao_hut),
    hao_hut_pct: s(cd.hao_hut_pct),
    so_luot_chay: s(cd.so_luot_chay),
    so_nhan_cong: s(cd.so_nhan_cong),
    setup_phut: s(cd.setup_phut),
    nang_suat: s(cd.nang_suat),
    don_vi_nang_suat: cd.don_vi_nang_suat ?? "",
    chay_phut: s0(cd.chay_phut),
    ve_sinh_phut: s(cd.ve_sinh_phut),
    cho_phut: s(cd.cho_phut),
    di_chuyen_phut: s(cd.di_chuyen_phut),
    dieu_kien_json: cd.dieu_kien_json ?? [],
    nha_cung_cap: cd.nha_cung_cap ?? "",
    sl_gui: s(cd.sl_gui),
    ngay_gui_dk: cd.ngay_gui_dk ?? "",
    van_chuyen_ngay: s(cd.van_chuyen_ngay),
    gia_cong_ngay: s(cd.gia_cong_ngay),
    ngay_nhan_dk: cd.ngay_nhan_dk ?? "",
    hao_hut_cho_phep: s(cd.hao_hut_cho_phep),
    don_gia_gia_cong: s(cd.don_gia_gia_cong),
    yeu_cau_ky_thuat: cd.yeu_cau_ky_thuat ?? "",
    ghi_chu: cd.ghi_chu ?? "",
  };
}

export function emptyRow(): EditRow {
  return {
    key: newKey(), cong_doan_id: null, ten: "", nhom: null, loai_buoc: "may", bat_buoc: true,
    department_id: null, may_id: null, may_thay_the_ids: [],
    so_luong_vao: "", so_luong_ra: "", don_vi_vao: "to", don_vi_ra: "to", he_so_quy_doi: "",
    hao_hut: "", hao_hut_pct: "", so_luot_chay: "", so_nhan_cong: "",
    setup_phut: "", nang_suat: "", don_vi_nang_suat: "", chay_phut: "",
    ve_sinh_phut: "", cho_phut: "", di_chuyen_phut: "", dieu_kien_json: [],
    nha_cung_cap: "", sl_gui: "", ngay_gui_dk: "", van_chuyen_ngay: "", gia_cong_ngay: "",
    ngay_nhan_dk: "", hao_hut_cho_phep: "", don_gia_gia_cong: "", yeu_cau_ky_thuat: "",
    ghi_chu: "",
  };
}

export function n(v: string): number {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

/** Chuỗi rỗng → undefined (bỏ field khỏi payload) để server giữ mặc định thay vì ghi 0. */
function on(v: string): number | undefined {
  return v.trim() === "" ? undefined : n(v);
}

function ot(v: string): string | null {
  return v.trim() === "" ? null : v.trim();
}

export function toBody(rows: EditRow[]): LsxCongDoanBody[] {
  return rows.map((r, i) => {
    const ngoai = r.loai_buoc === "thue_ngoai";
    return {
      thu_tu: i,
      cong_doan_id: r.cong_doan_id,
      ten: r.ten || "Công đoạn",
      nhom: r.nhom,
      loai_buoc: r.loai_buoc,
      bat_buoc: r.bat_buoc,
      // Để TRỐNG tổ → server tự lấy tổ mặc định của công đoạn (không ép khai lại).
      department_id: r.department_id,
      may_id: r.may_id,
      may_thay_the_ids: r.may_thay_the_ids,
      so_luong_vao: n(r.so_luong_vao),
      so_luong_ra: n(r.so_luong_ra),
      don_vi_vao: r.don_vi_vao,
      don_vi_ra: r.don_vi_ra,
      he_so_quy_doi: on(r.he_so_quy_doi),
      hao_hut: on(r.hao_hut),
      hao_hut_pct: on(r.hao_hut_pct),
      so_luot_chay: on(r.so_luot_chay),
      so_nhan_cong: on(r.so_nhan_cong),
      setup_phut: on(r.setup_phut),
      nang_suat: on(r.nang_suat),
      don_vi_nang_suat: ot(r.don_vi_nang_suat),
      // Ô trống = để máy tính từ năng suất (KHÔNG phải 0 phút).
      chay_phut: r.chay_phut.trim() === "" ? null : n(r.chay_phut),
      ve_sinh_phut: on(r.ve_sinh_phut),
      cho_phut: on(r.cho_phut),
      di_chuyen_phut: on(r.di_chuyen_phut),
      dieu_kien_json: r.dieu_kien_json,
      // Khối gia công ngoài chỉ gửi khi bước ĐANG là thuê ngoài — đổi loại bước rồi thì
      // không kéo theo dữ liệu NCC cũ làm checklist hiểu nhầm.
      nha_cung_cap: ngoai ? ot(r.nha_cung_cap) : null,
      sl_gui: ngoai ? on(r.sl_gui) : undefined,
      ngay_gui_dk: ngoai ? ot(r.ngay_gui_dk) : null,
      van_chuyen_ngay: ngoai ? on(r.van_chuyen_ngay) : undefined,
      gia_cong_ngay: ngoai ? on(r.gia_cong_ngay) : undefined,
      ngay_nhan_dk: ngoai ? ot(r.ngay_nhan_dk) : null,
      hao_hut_cho_phep: ngoai ? on(r.hao_hut_cho_phep) : undefined,
      don_gia_gia_cong: ngoai ? on(r.don_gia_gia_cong) : undefined,
      yeu_cau_ky_thuat: ngoai ? ot(r.yeu_cau_ky_thuat) : null,
      ghi_chu: ot(r.ghi_chu),
    };
  });
}

/** Thời lượng 1 bước tính NGAY TRÊN MÁY KHÁCH — bảng phản hồi tức thì khi gõ, không đợi lưu.
 *  Công thức phải khớp `thoi_luong_buoc` ở backend (nguồn chân lý khi lưu). */
export function thoiLuong(r: EditRow): { chay: number; chiemMay: number; tong: number } {
  const setup = n(r.setup_phut);
  const veSinh = n(r.ve_sinh_phut);
  const cho = n(r.cho_phut);
  const diChuyen = n(r.di_chuyen_phut);
  let chay: number;
  if (r.chay_phut.trim() !== "") {
    chay = n(r.chay_phut);            // người kế hoạch gõ đè thì thắng công thức
  } else {
    const ns = n(r.nang_suat);
    const vao = n(r.so_luong_vao);
    const luot = Math.max(n(r.so_luot_chay) || 1, 1);
    const nc = Math.max(n(r.so_nhan_cong) || 1, 1);
    chay = ns > 0 && vao > 0 ? (vao / ns) * 60 * luot / nc : 0;
  }
  const chiemMay = setup + chay + veSinh;
  return { chay, chiemMay, tong: chiemMay + cho + diChuyen };
}

/** "2 giờ 4 phút" — đọc nhanh hơn "124 phút" khi bước dài.
 *
 *  CỐ TÌNH dừng ở GIỜ, không quy ra ngày: "ngày" ở đây sẽ là ngày lịch (24h) trong khi dải tổng
 *  quy ra NGÀY LÀM VIỆC (8h) — hai con số cạnh nhau mà khác gốc thì đọc thành mâu thuẫn
 *  ("10 ngày 8 giờ ≈ 31 ngày làm việc"). Một đơn vị duy nhất, ai cũng hiểu đúng. */
export function phut(v: number): string {
  const m = Math.round(v);
  if (m <= 0) return "—";
  if (m < 60) return `${m} phút`;
  const gio = Math.floor(m / 60);
  const du = m % 60;
  return du ? `${gio} giờ ${du} phút` : `${gio} giờ`;
}
