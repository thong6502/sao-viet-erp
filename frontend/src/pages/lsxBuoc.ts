// Mô hình 1 BƯỚC routing đang được sửa trên màn (dùng chung bảng + drawer).
//
// Tách riêng khỏi cả hai để không vòng import, và để chỗ nào cũng nhìn cùng một hình dạng dòng.
// Mọi ô số giữ dạng CHUỖI: ô trống ("") khác 0 — trống nghĩa là "chưa khai, dùng gợi ý", còn 0 là
// người dùng cố tình khai bằng 0. Ép sang number quá sớm sẽ xoá mất sự khác nhau đó.
import { LSX_DON_VI_LABELS } from "../api/client";
import type {
  LsxCongDoan,
  LsxCongDoanBody,
  LsxGiaoNhanFields,
  LsxLoaiBuoc,
} from "../api/client";

export interface EditRow {
  key: string;
  /** Id THẬT của bước ở server — null nếu bước mới thêm chưa lưu. Cần cho các cửa ghi ngoài
   *  routing (vd sổ giao–nhận), vì `key` chỉ là step_key. */
  id: number | null;
  cong_doan_id: number | null;
  ten: string;
  nhom: string | null;
  loai_buoc: LsxLoaiBuoc;
  bat_buoc: boolean;
  department_id: number | null;
  may_id: number | null;
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
  so_nhan_cong_tieu_chuan: number;
  so_nhan_cong_toi_da: number | null;
  setup_phut: string;
  nang_suat: string;
  don_vi_nang_suat: string;
  chay_phut: string;
  ve_sinh_phut: string;
  cho_phut: string;
  di_chuyen_phut: string;
  thoi_luong_dien_giai: Record<string, unknown>;
  phu_thuoc_step_keys: string[];
  vat_tus: { vat_tu_id: number; vat_tu_ma: string; vat_tu_ten: string; don_vi: string; so_luong: string }[];
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
  /** Sổ giao–nhận THỰC TẾ + dẫn xuất — READ-ONLY ở form này. Ghi qua `api.lsx.giaoNhan`, không
   *  đi kèm lưu routing (hàng ra cổng lúc lệnh đang chạy, lưu routing thì bị chặn). */
  giao_nhan: LsxGiaoNhanFields | null;
  // --- khoán theo đầu việc ---
  /** Đầu việc đang chọn (`piece_rates.id`) — người dùng đổi được. */
  khoan_rate_id: number | null;
  /** Danh sách chọn được + diễn giải tiền: READ-ONLY từ server (server áp luật khớp + quy đổi). */
  khoan_chon_duoc: KhoanChon[];
  khoan_dien_giai: string | null;
  khoan_ly_do: string | null;
  /** Đầu việc lúc TẢI về — đổi lựa chọn thì diễn giải cũ hết đúng, phải chờ lưu để server tính lại. */
  khoan_rate_id_luc_tai: number | null;
}

export interface KhoanChon {
  id: number;
  ten: string;
  don_vi: string;
  don_gia: number;
  nang_suat_nguoi_gio?: number;
  so_nguoi_tieu_chuan?: number;
  so_nguoi_toi_da?: number;
  is_default?: boolean;
  don_vi_nang_suat?: string | null;
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
    key: cd.step_key,
    id: cd.id ?? null,
    cong_doan_id: cd.cong_doan_id,
    ten: cd.ten,
    nhom: cd.nhom,
    loai_buoc: cd.loai_buoc,
    bat_buoc: cd.bat_buoc,
    department_id: cd.department_id,
    may_id: cd.may_id,
    so_luong_vao: s(cd.so_luong_vao),
    so_luong_ra: s(cd.so_luong_ra),
    don_vi_vao: cd.don_vi_vao || "to",
    don_vi_ra: cd.don_vi_ra || cd.don_vi_vao || "to",
    he_so_quy_doi: s(cd.he_so_quy_doi),
    hao_hut: s(cd.hao_hut),
    hao_hut_pct: s(cd.hao_hut_pct),
    so_luot_chay: s(cd.so_luot_chay),
    so_nhan_cong: s(cd.so_nhan_cong),
    so_nhan_cong_tieu_chuan: cd.so_nhan_cong_tieu_chuan ?? 1,
    so_nhan_cong_toi_da: cd.so_nhan_cong_toi_da,
    setup_phut: s(cd.setup_phut),
    nang_suat: s(cd.nang_suat),
    don_vi_nang_suat: cd.don_vi_nang_suat ?? "",
    chay_phut: s0(cd.chay_phut),
    ve_sinh_phut: s(cd.ve_sinh_phut),
    cho_phut: s(cd.cho_phut),
    di_chuyen_phut: s(cd.di_chuyen_phut),
    thoi_luong_dien_giai: cd.thoi_luong_dien_giai ?? {},
    phu_thuoc_step_keys: cd.phu_thuoc_step_keys ?? [],
    vat_tus: (cd.vat_tus ?? []).map((v) => ({ ...v, so_luong: String(v.so_luong) })),
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
    giao_nhan: {
      nguoi_giao_id: cd.nguoi_giao_id ?? null,
      nguoi_giao_ten: cd.nguoi_giao_ten ?? null,
      giao_luc: cd.giao_luc ?? null,
      sl_giao_thuc: cd.sl_giao_thuc ?? null,
      nguoi_nhan_id: cd.nguoi_nhan_id ?? null,
      nguoi_nhan_ten: cd.nguoi_nhan_ten ?? null,
      nhan_luc: cd.nhan_luc ?? null,
      sl_nhan_thuc: cd.sl_nhan_thuc ?? null,
      giao_nhan_trang_thai: cd.giao_nhan_trang_thai ?? "chua_gui",
      so_hut: cd.so_hut ?? null,
      hut_vuot_dinh_muc: Boolean(cd.hut_vuot_dinh_muc),
      tien_gia_cong_thuc: cd.tien_gia_cong_thuc ?? null,
      qua_han_ngay: cd.qua_han_ngay ?? null,
    },
    khoan_rate_id: cd.khoan_rate_id ?? null,
    khoan_chon_duoc: cd.khoan_chon_duoc ?? [],
    khoan_dien_giai: cd.khoan_dien_giai ?? null,
    khoan_ly_do: cd.khoan_ly_do ?? null,
    khoan_rate_id_luc_tai: cd.khoan_rate_id ?? null,
  };
}

export function emptyRow(): EditRow {
  return {
    key: newKey(), id: null, cong_doan_id: null, ten: "", nhom: null, loai_buoc: "may",
    bat_buoc: true,
    department_id: null, may_id: null,
    so_luong_vao: "", so_luong_ra: "", don_vi_vao: "to", don_vi_ra: "to", he_so_quy_doi: "",
    hao_hut: "", hao_hut_pct: "", so_luot_chay: "", so_nhan_cong: "",
    setup_phut: "", nang_suat: "", don_vi_nang_suat: "", chay_phut: "",
    so_nhan_cong_tieu_chuan: 1, so_nhan_cong_toi_da: null,
    ve_sinh_phut: "", cho_phut: "", di_chuyen_phut: "", thoi_luong_dien_giai: {},
    phu_thuoc_step_keys: [], vat_tus: [],
    nha_cung_cap: "", sl_gui: "", ngay_gui_dk: "", van_chuyen_ngay: "", gia_cong_ngay: "",
    ngay_nhan_dk: "", hao_hut_cho_phep: "", don_gia_gia_cong: "", yeu_cau_ky_thuat: "",
    ghi_chu: "",
    // Bước mới chưa lưu thì chưa có id để ghi giao–nhận — sổ chỉ mở sau khi lưu routing.
    giao_nhan: null,
    // Bước THÊM TAY chưa biết tổ/công đoạn nên chưa có đầu việc nào để gợi ý; lưu xong server điền.
    khoan_rate_id: null, khoan_chon_duoc: [], khoan_dien_giai: null, khoan_ly_do: null,
    khoan_rate_id_luc_tai: null,
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
      step_key: r.key.startsWith("r") ? undefined : r.key,
      cong_doan_id: r.cong_doan_id,
      ten: r.ten || "Công đoạn",
      nhom: r.nhom,
      loai_buoc: r.loai_buoc,
      bat_buoc: r.bat_buoc,
      // Để TRỐNG tổ → server tự lấy tổ mặc định của công đoạn (không ép khai lại).
      department_id: r.department_id,
      may_id: r.may_id,
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
      // Ô trống = để máy tính từ năng suất (KHÔNG phải 0 phút).
      chay_phut: r.chay_phut.trim() === "" ? null : n(r.chay_phut),
      ve_sinh_phut: on(r.ve_sinh_phut),
      cho_phut: on(r.cho_phut),
      di_chuyen_phut: on(r.di_chuyen_phut),
      phu_thuoc_step_keys: r.phu_thuoc_step_keys,
      vat_tus: r.vat_tus.map((v) => ({ vat_tu_id: v.vat_tu_id, so_luong: n(v.so_luong) })),
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
      // Đầu việc khoán — ba trạng thái khác nhau, đừng gộp:
      //  · đang chọn         → gửi id
      //  · từng có, nay bỏ   → gửi null (người dùng CHỦ Ý bỏ chọn)
      //  · chưa bao giờ có   → KHÔNG gửi field, để server điền mặc định theo tổ + công đoạn
      // Gửi null vô điều kiện thì bước mới thêm tay vĩnh viễn không được điền sẵn.
      ...(r.khoan_rate_id != null || r.khoan_rate_id_luc_tai != null
        ? { piece_rate_id: r.khoan_rate_id }
        : {}),
    };
  });
}

/** Preview tức thời trong drawer trước khi lưu.
 *
 * Backend vẫn tính lại và chốt snapshot khi lưu. Bản preview này dùng đúng các đầu vào đang hiện
 * trên form để người lập kế hoạch không phải lưu mù rồi mở lại mới biết thời gian thay đổi ra sao.
 */
export function thoiLuongLive(r: EditRow): Record<string, unknown> {
  const f = (v: string | number | null | undefined): number => {
    const x = Number(v ?? 0);
    return Number.isFinite(x) ? x : 0;
  };
  const tron = (v: number): number => Math.round(v * 100) / 100;
  const vao = f(r.so_luong_vao);
  const ns = f(r.nang_suat);
  const luot = Math.max(Math.trunc(f(r.so_luot_chay)) || 1, 1);
  const nguoiKeHoach = Math.max(Math.trunc(f(r.so_nhan_cong)) || 1, 1);
  const nguoiToiDa = Math.max(Math.trunc(f(r.so_nhan_cong_toi_da)) || nguoiKeHoach, 1);
  const nguoiTinh = r.loai_buoc === "to" ? Math.min(nguoiKeHoach, nguoiToiDa) : null;
  const coNhapDe = r.chay_phut.trim() !== "";
  const canhBao: string[] = [];
  let phuongPhap: string = r.loai_buoc;
  let nangSuatHieuDung = ns;
  let chay = 0;

  if (coNhapDe) {
    chay = f(r.chay_phut);
    phuongPhap = "nhap_de";
  } else if (r.loai_buoc === "to") {
    nangSuatHieuDung = ns * (nguoiTinh ?? 1);
    chay = nangSuatHieuDung > 0 && vao > 0 ? vao / nangSuatHieuDung * 60 : 0;
    if (ns <= 0) phuongPhap = "thieu_nang_suat";
    if (r.so_nhan_cong_toi_da != null && nguoiKeHoach > nguoiToiDa) {
      canhBao.push("Số người kế hoạch vượt mức tối đa hiệu quả; thời gian chỉ tính theo mức tối đa.");
    }
  } else if (r.loai_buoc === "may") {
    chay = ns > 0 && vao > 0 ? vao * luot / ns * 60 : 0;
    if (ns <= 0) phuongPhap = "thieu_nang_suat";
  } else {
    nangSuatHieuDung = 0;
  }
  if (phuongPhap === "thieu_nang_suat") {
    canhBao.push("Thiếu năng suất hợp lệ; hãy chọn nguồn năng suất hoặc nhập đè thời gian chạy.");
  }

  const setup = f(r.setup_phut);
  const veSinh = f(r.ve_sinh_phut);
  const cho = f(r.cho_phut);
  const diChuyen = f(r.di_chuyen_phut);
  const chiemTaiNguyen = setup + chay + veSinh;
  return {
    phuong_phap: phuongPhap,
    so_luong_vao: tron(vao),
    don_vi_vao: r.don_vi_vao,
    nguon_nang_suat: r.loai_buoc === "to" ? "dau_viec" : (r.loai_buoc === "may" ? "may" : null),
    nang_suat_co_so: ns > 0 ? tron(ns) : null,
    nang_suat_hieu_dung: nangSuatHieuDung > 0 ? tron(nangSuatHieuDung) : null,
    so_luot_chay: r.loai_buoc === "may" ? luot : null,
    so_nhan_cong_ke_hoach: r.loai_buoc === "thue_ngoai" ? null : nguoiKeHoach,
    so_nhan_cong_tieu_chuan: r.loai_buoc === "thue_ngoai" ? null : r.so_nhan_cong_tieu_chuan,
    so_nhan_cong_toi_da: r.loai_buoc === "to" ? r.so_nhan_cong_toi_da : null,
    so_nhan_cong_tinh: nguoiTinh,
    setup_phut: tron(setup),
    chay_phut: tron(chay),
    ve_sinh_phut: tron(veSinh),
    cho_phut: tron(cho),
    di_chuyen_phut: tron(diChuyen),
    chiem_tai_nguyen_phut: tron(chiemTaiNguyen),
    tong_phut: tron(chiemTaiNguyen + cho + diChuyen),
    canh_bao: canhBao,
  };
}

export function thoiLuong(r: EditRow): { chay: number; chiemMay: number; tong: number } {
  const d = thoiLuongLive(r);
  return {
    chay: Number(d.chay_phut ?? 0),
    chiemMay: Number(d.chiem_tai_nguyen_phut ?? 0),
    tong: Number(d.tong_phut ?? 0),
  };
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

/** Mã đơn vị → nhãn người đọc (`to` → "Tờ in", `cai` → "Thành phẩm"…). */
export function nhanDonVi(dv: string | null | undefined): string {
  return dv ? LSX_DON_VI_LABELS[dv] ?? dv : "";
}

/** Câu quy đổi của MỘT bước: `"10 Tờ in = 1 Thành phẩm"`. `null` khi bước không đổi đơn vị.
 *
 *  LẬT LẠI khi hệ số < 1 — đó là ca SÁCH GẤP TAY (10 tờ mới gom thành 1 cuốn → hệ số 0,1). Viết
 *  thẳng `"1 Tờ in = 0,1 Thành phẩm"` thì đúng số nhưng người đọc phải tự nghịch đảo trong đầu.
 *  Bên Tính giá đã lật từ lâu; đây là bản DÙNG CHUNG để bốn màn (tính giá · bảng routing · drawer
 *  bước · thẻ bước chung bài ghép) không mỗi nơi một kiểu. */
export function heSoChu(
  heSo: number | null | undefined,
  dvVao: string | null | undefined,
  dvRa: string | null | undefined,
): string | null {
  const hs = Number(heSo);
  if (!dvVao || !dvRa || dvVao === dvRa || !Number.isFinite(hs) || hs === 1 || hs <= 0) return null;
  const so = (v: number) => v.toLocaleString("vi-VN", { maximumFractionDigits: 4 });
  return hs < 1
    ? `${so(1 / hs)} ${nhanDonVi(dvVao)} = 1 ${nhanDonVi(dvRa)}`
    : `1 ${nhanDonVi(dvVao)} = ${so(hs)} ${nhanDonVi(dvRa)}`;
}
