// Mô hình 1 BƯỚC routing đang được sửa trên màn (dùng chung bảng + drawer).
//
// Tách riêng khỏi cả hai để không vòng import, và để chỗ nào cũng nhìn cùng một hình dạng dòng.
// Mọi ô số giữ dạng CHUỖI: ô trống ("") khác 0 — trống nghĩa là "chưa khai, dùng gợi ý", còn 0 là
// người dùng cố tình khai bằng 0. Ép sang number quá sớm sẽ xoá mất sự khác nhau đó.
import { tenDonVi } from "./tenDonVi";
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
  /** Hai cờ dụng cụ đọc từ danh mục Công đoạn — CHỈ ĐỌC, không gửi lên. Chúng quyết định bước có
   *  hỏi khuôn không, và `tooling_type` là chiều lọc thứ hai của ô chọn dao.
   *  `khuon_be_id` là thứ người cấu hình lệnh chọn; bốn field còn lại là ảnh chụp để bày cho thợ. */
  requires_tooling: boolean;
  tooling_type: string | null;
  khuon_be_id: number | null;
  khuon_be_ma: string | null;
  khuon_be_ten: string | null;
  khuon_be_so_ke: string | null;
  khuon_be_tinh_trang: string | null;
  khuon_be_ngay_ve: string | null;
  // số lượng & hao hụt
  so_luong_vao: string;
  so_luong_ra: string;
  don_vi_vao: string;
  don_vi_ra: string;
  /** Bước có nằm trên DÒNG GIẤY không — CHỈ ĐỌC, server quyết theo cờ trạm của danh mục Đơn vị.
   *  `false` ⇒ số lượng không tự tính ngược, bù hao không cộng vào số giấy (drawer nói tại chỗ). */
  tren_dong_giay: boolean;
  /** Bước ngoài dòng giấy thiếu cầu quy đổi vào→ra ở module Đơn vị & quy đổi ⇒ câu lỗi (server
   *  tính lúc đọc). null = ổn. Có lỗi thì `so_luong_vao` = 0 và drawer bày banner đỏ. CHỈ ĐỌC. */
  loi_quy_doi: string | null;
  /** Diễn giải công thức SỐ RA cho bước ngoài dòng ("Số bản kẽm = 5 bản kẽm"; server tính lúc
   *  đọc). null với bước trên dòng giấy. CHỈ ĐỌC. */
  san_luong_dien_giai: string | null;
  he_so_quy_doi: string;
  hao_hut: string;
  hao_hut_pct: string;
  so_luot_chay: string;
  // năng suất & thời gian (phút)
  so_nhan_cong: string;
  /** Ba mốc định mức nhân lực — KẾ THỪA từ đầu việc khoán nhưng SỬA ĐƯỢC tại bước. */
  so_nhan_cong_toi_thieu: number | null;
  so_nhan_cong_tieu_chuan: number;
  so_nhan_cong_toi_da: number | null;
  nang_suat: string;
  don_vi_nang_suat: string;
  /** Ô DUY NHẤT còn gõ được ở tab Thời gian ("Thời gian khác"). `setup_phut`/`chay_phut` kế thừa
   *  từ máy — số hiển thị lấy từ `thoi_luong_dien_giai` (server tính), không ô nào ghi ngược. */
  phat_sinh_phut: string;
  thoi_luong_dien_giai: Record<string, unknown>;
  /** Lượng tính sẵn cho mọi vật tư (server tính theo bước) — READ-ONLY, không gửi lên.
   *  `so_luong: null` = chưa tính được, `ly_do` nói vì sao và chỉ chỗ khai công thức. */
  vat_tu_goi_y: {
    vat_tu_id: number;
    so_luong: number | null;
    dien_giai: string | null;
    ly_do: string | null;
  }[];
  /** Số tính lại theo danh mục HIỆN TẠI khi lệch số đã lưu — READ-ONLY, không gửi lên. */
  so_luong_vao_moi: number | null;
  so_luong_ra_moi: number | null;
  phu_thuoc_step_keys: string[];
  /** `tu_dong` = dòng MÁY bung khi chọn công việc khoán ⇒ lần bung sau thay được. Người tự thêm
   *  hoặc đã sửa số thì về `false` và máy chừa ra — không thì đổi công việc khoán là mất số vừa gõ. */
  vat_tus: { vat_tu_id: number; vat_tu_ma: string; vat_tu_ten: string; don_vi: string;
             so_luong: string; tu_dong: boolean }[];
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
  /** Dải năng suất của định mức — chỉ để hiện khoảng nhanh–chậm, null = chưa khai. */
  nang_suat_nguoi_gio_min?: number | null;
  nang_suat_nguoi_gio_max?: number | null;
  /** Khai báo, chưa vào công thức — xem `cong_doan_dau_viec.so_nguoi_toi_thieu`. */
  so_nguoi_toi_thieu?: number;
  so_nguoi_tieu_chuan?: number;
  so_nguoi_toi_da?: number;
  don_vi_nang_suat?: string | null;
  /** VẬT TƯ đầu việc này tiêu thụ, ĐÃ tính số cho đúng bước đang mở (nền BOM, mg 0191). Server
   *  quy đổi từ số lượng vào của bước sang đơn vị của vật tư — client chỉ việc bung ra. */
  vat_tus?: {
    vat_tu_id: number; ma: string; ten: string; don_vi: string;
    so_luong: number; dien_giai?: string | null;
  }[];
  /** Vật tư khai ở danh mục nhưng chưa quy đổi được — nói thiếu gì, KHÔNG đoán số. */
  canh_bao_vat_tu?: string[];
}


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
    requires_tooling: !!cd.requires_tooling,
    tooling_type: cd.tooling_type ?? null,
    khuon_be_id: cd.khuon_be_id ?? null,
    khuon_be_ma: cd.khuon_be_ma ?? null,
    khuon_be_ten: cd.khuon_be_ten ?? null,
    khuon_be_so_ke: cd.khuon_be_so_ke ?? null,
    khuon_be_tinh_trang: cd.khuon_be_tinh_trang ?? null,
    khuon_be_ngay_ve: cd.khuon_be_ngay_ve ?? null,
    so_luong_vao: s(cd.so_luong_vao),
    so_luong_ra: s(cd.so_luong_ra),
    don_vi_vao: cd.don_vi_vao || "to",
    don_vi_ra: cd.don_vi_ra || cd.don_vi_vao || "to",
    // Server cũ chưa gửi cờ ⇒ coi như TRÊN dòng giấy: im lặng đúng với hành vi trước đây, hơn là
    // đột nhiên dán chú giải "ngoài dòng giấy" lên mọi bước.
    tren_dong_giay: cd.tren_dong_giay !== false,
    loi_quy_doi: cd.loi_quy_doi ?? null,
    san_luong_dien_giai: cd.san_luong_dien_giai ?? null,
    he_so_quy_doi: s(cd.he_so_quy_doi),
    hao_hut: s(cd.hao_hut),
    hao_hut_pct: s(cd.hao_hut_pct),
    so_luot_chay: s(cd.so_luot_chay),
    so_nhan_cong: s(cd.so_nhan_cong),
    so_nhan_cong_toi_thieu: cd.so_nhan_cong_toi_thieu ?? null,
    so_nhan_cong_tieu_chuan: cd.so_nhan_cong_tieu_chuan ?? 1,
    so_nhan_cong_toi_da: cd.so_nhan_cong_toi_da,
    nang_suat: s(cd.nang_suat),
    don_vi_nang_suat: cd.don_vi_nang_suat ?? "",
    phat_sinh_phut: s(cd.phat_sinh_phut),
    thoi_luong_dien_giai: cd.thoi_luong_dien_giai ?? {},
    vat_tu_goi_y: cd.vat_tu_goi_y ?? [],
    so_luong_vao_moi: cd.so_luong_vao_moi ?? null,
    so_luong_ra_moi: cd.so_luong_ra_moi ?? null,
    phu_thuoc_step_keys: cd.phu_thuoc_step_keys ?? [],
    vat_tus: (cd.vat_tus ?? []).map((v) => ({
      ...v, so_luong: String(v.so_luong), tu_dong: Boolean(v.tu_dong),
    })),
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
    requires_tooling: false, tooling_type: null, khuon_be_id: null, khuon_be_ma: null,
    khuon_be_ten: null, khuon_be_so_ke: null, khuon_be_tinh_trang: null, khuon_be_ngay_ve: null,
    so_luong_vao: "", so_luong_ra: "", don_vi_vao: "to", don_vi_ra: "to",
    tren_dong_giay: true, loi_quy_doi: null, san_luong_dien_giai: null, he_so_quy_doi: "",
    hao_hut: "", hao_hut_pct: "", so_luot_chay: "", so_nhan_cong: "",
    nang_suat: "", don_vi_nang_suat: "", phat_sinh_phut: "",
    so_nhan_cong_toi_thieu: null, so_nhan_cong_tieu_chuan: 1, so_nhan_cong_toi_da: null,
    thoi_luong_dien_giai: {},
    vat_tu_goi_y: [], so_luong_vao_moi: null, so_luong_ra_moi: null,
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
      khuon_be_id: r.khuon_be_id,
      so_luong_vao: n(r.so_luong_vao),
      so_luong_ra: n(r.so_luong_ra),
      don_vi_vao: r.don_vi_vao,
      don_vi_ra: r.don_vi_ra,
      he_so_quy_doi: on(r.he_so_quy_doi),
      hao_hut: on(r.hao_hut),
      hao_hut_pct: on(r.hao_hut_pct),
      so_luot_chay: on(r.so_luot_chay),
      so_nhan_cong: on(r.so_nhan_cong),
      // Ba mốc định mức: gửi lên để số người kế hoạch sửa tay không bị server kéo lại theo
      // danh mục. Bước Máy/Thuê ngoài không có định mức tổ nên bỏ qua.
      ...(r.loai_buoc === "to"
        ? {
            so_nhan_cong_toi_thieu: r.so_nhan_cong_toi_thieu ?? undefined,
            so_nhan_cong_tieu_chuan: r.so_nhan_cong_tieu_chuan || undefined,
            so_nhan_cong_toi_da: r.so_nhan_cong_toi_da ?? undefined,
          }
        : {}),
      // Ô trống = để máy tính từ năng suất (KHÔNG phải 0 phút).
      phat_sinh_phut: on(r.phat_sinh_phut),
      phu_thuoc_step_keys: r.phu_thuoc_step_keys,
      vat_tus: r.vat_tus.map((v) => ({
        vat_tu_id: v.vat_tu_id, so_luong: n(v.so_luong), tu_dong: v.tu_dong,
      })),
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

/** Lỗi/nghi vấn của RIÊNG 1 dòng routing — chỉ TÔ MÀU, không chặn lưu.
 *
 * Ở đây (chứ không ở `LsxRoutingTable`) vì nó thuần `EditRow` → chuỗi, không dính React: cùng chỗ
 * với `toEdit`/`toBody`/`thoiLuong`, và test được mà không phải dựng cả bảng.
 *
 *
 * Cảnh báo giả nguy hiểm hơn là không có cảnh báo: nó dạy người dùng bỏ qua cả cột, nên lúc đứt
 * thật cũng chẳng ai nhìn.
 *
 * Nay lọc bằng CỜ `tren_dong_giay` — server suy từ `don_vi_do.tram_dong_giay`, FE không tự đoán từ
 * mã. Bước ngoài dòng giấy đo khối lượng việc của RIÊNG nó (kẽm đếm bản, đóng thùng đếm thùng);
 * đem thước đó so với thước dòng giấy là so hai thứ không liên quan.
 *
 * Vẫn so bằng MÃ đơn vị chứ không bằng trạm: giữa hai bước liền nhau trên dòng giấy, giấy không
 * đổi cách đếm — mọi nhịp đổi trạm (`tờ → tay`) xảy ra BÊN TRONG một bước, giữa `vào` và `ra` của
 * chính nó. Bởi vậy luật cầu giữa các trạm (`CAU_TRAM`) không cần có mặt ở client, và KHÔNG được
 * chép sang đây — xem bài học ở `donViChuoi` phía dưới.
 */
export function loiDong(rows: EditRow[], i: number): string[] {
  const r = rows[i];
  const out: string[] = [];
  const vao = n(r.so_luong_vao);
  const ra = n(r.so_luong_ra);
  if (r.don_vi_vao === r.don_vi_ra && vao > 0 && ra > vao) out.push("ra nhiều hơn vào");
  // KHÔNG kiểm `he_so <= 1` nữa: hệ số nay do server suy, và 1 là HỢP LỆ ở cả hai cầu
  // (1 tờ nguyên ra 1 tờ in là chuyện thường). Luật cũ bắt oan đúng ca đó.
  if (r.loai_buoc === "thue_ngoai") {
    if (!r.nha_cung_cap.trim()) out.push("chưa có nhà gia công");
    if (!r.ngay_gui_dk || !r.ngay_nhan_dk) out.push("chưa có ngày gửi / nhận");
  } else if (r.department_id == null && r.may_id == null) {
    out.push("chưa gán tổ / máy");
  }
  if (r.tren_dong_giay && r.don_vi_vao) {
    const truoc = rows
      .slice(0, i)
      .reverse()
      .find((x) => x.tren_dong_giay && x.don_vi_vao && x.don_vi_ra);
    if (truoc && truoc.don_vi_ra !== r.don_vi_vao) out.push("đứt đơn vị");
  }
  if (i > 0 && r.ten && rows[i - 1].ten === r.ten) out.push("trùng bước trước");
  return out;
}

/** Preview tức thời trong drawer trước khi lưu.
 *
 * Backend vẫn tính lại và chốt snapshot khi lưu. Bản preview này dùng đúng các đầu vào đang hiện
 * trên form để người lập kế hoạch không phải lưu mù rồi mở lại mới biết thời gian thay đổi ra sao.
 */
export interface MayTinhGio {
  tocDo?: number | null;
  tocDoMin?: number | null;
  tocDoMax?: number | null;
  donViTocDo?: string | null;
  chuanBiPhut?: number | null;
  chuanBiKhoan?: { ten?: string; phut?: number }[];
}

/** Bộ số TỐI THIỂU để tính lại thời lượng. `EditRow` của bước lệnh khớp sẵn; bước chung của bài
 *  ghép dựng được từ dữ liệu của nó. Nới kiểu ở đây để HAI màn xài CHUNG một công thức, thay vì
 *  màn bài ghép chép phép tính lần thứ hai (hai bản công thức = hai đường lệch nhau lúc sửa). */
export type ThoiLuongInput = Pick<
  EditRow,
  | "loai_buoc"
  | "so_luot_chay"
  | "so_nhan_cong"
  | "so_nhan_cong_toi_da"
  | "so_nhan_cong_tieu_chuan"
  | "nang_suat"
  | "phat_sinh_phut"
  | "thoi_luong_dien_giai"
  | "don_vi_vao"
  | "so_luong_vao"
>;

export function thoiLuongLive(r: ThoiLuongInput, may?: MayTinhGio | null): Record<string, unknown> {
  const f = (v: string | number | null | undefined): number => {
    const x = Number(v ?? 0);
    return Number.isFinite(x) ? x : 0;
  };
  const tron = (v: number): number => Math.round(v * 100) / 100;
  const dgServer = (r.thoi_luong_dien_giai ?? {}) as Record<string, unknown>;
  // SL đưa vào phép chia là số ĐÃ QUY ĐỔI về đơn vị của tốc độ — server tính (chỉ nó có bảng cặp
  // quy đổi) rồi gửi kèm trong `thoi_luong_dien_giai.so_luong_vao`. Bản preview KHÔNG dựng lại
  // phép quy đổi: công thức thì được phép có hai bản, bảng quy đổi thì không.
  const daQuyDoi = dgServer.phuong_phap !== "chua_quy_doi" && dgServer.so_luong_vao != null;
  const vao = daQuyDoi ? Number(dgServer.so_luong_vao) || 0 : 0;
  const luot = Math.max(Math.trunc(f(r.so_luot_chay)) || 1, 1);
  const nguoiKeHoach = Math.max(Math.trunc(f(r.so_nhan_cong)) || 1, 1);
  const canhBao: string[] = [];

  // Số của MÁY ĐANG CHỌN trên form (`may`) — KHÔNG đợi server. Đổi máy trong drawer là chuẩn bị
  // + thời gian chạy phải nhảy ngay; chỉ khi bấm Lưu mới ghi DB. Không truyền `may` (bảng chưa
  // nạp xong danh mục) thì rơi về diễn giải server đã trả — vẫn hơn là ra 0.
  const numOf = (k: string): number => Number(dgServer[k] ?? 0) || 0;
  const coMay = may != null;
  const setup = coMay ? (r.loai_buoc === "may" ? f(may?.chuanBiPhut) : 0) : numOf("setup_phut");
  const khac = f(r.phat_sinh_phut);
  const khoanChuanBi = coMay
    ? (r.loai_buoc === "may" ? (may?.chuanBiKhoan ?? []) : [])
    : (Array.isArray(dgServer.chuan_bi_khoan) ? dgServer.chuan_bi_khoan : []);

  let phuongPhap: string = r.loai_buoc;
  let nangSuatCoSo = 0;       // năng suất/tốc độ GỐC (Tổ: theo đầu người; Máy: tốc độ máy)
  let nangSuatHieuDung = 0;   // đã nhân kíp chuẩn với bước Tổ
  let nguoiTinh: number | null = null;
  let chay = 0;
  let chayNhanh = 0;
  let chayCham = 0;

  if (r.loai_buoc === "to") {
    // Bước TỔ = SL vào ÷ (năng suất khoán × SỐ NGƯỜI TIÊU CHUẨN) × 60. Năng suất khai theo ĐẦU
    // NGƯỜI nên kíp chuẩn N người chạy nhanh gấp N (chốt 20/08/2026). Số người tiêu chuẩn SỬA ĐƯỢC
    // trong drawer ⇒ phải tính LIVE. Ba mức năng suất (min/tb/max) ghim trong `khoan_json` ở SERVER;
    // client không giữ min/max nên co giãn khoảng server đã tính theo TỶ LỆ chay_live/chay_server —
    // kíp chuẩn là hệ số ĐỀU trên cả ba mức nên tỷ lệ này tái tạo đúng khoảng khi đổi người hoặc SL.
    const ns = f(r.nang_suat);
    const nguoiTC = Math.max(Math.trunc(f(r.so_nhan_cong_tieu_chuan)) || 1, 1);
    nangSuatCoSo = ns;
    nangSuatHieuDung = ns * nguoiTC;
    nguoiTinh = nguoiTC;
    const chayServer = numOf("chay_phut");
    chay = nangSuatHieuDung > 0 && vao > 0 ? (vao / nangSuatHieuDung) * 60 : chayServer;
    const tyLe = chayServer > 0 && chay > 0 ? chay / chayServer : 1;
    chayNhanh = (numOf("chay_phut_min") || chay) * tyLe;   // năng suất CAO ⇒ chạy nhanh ⇒ nhỏ nhất
    chayCham = (numOf("chay_phut_max") || chay) * tyLe;
    if (ns <= 0) phuongPhap = "thieu_nang_suat";
  } else if (r.loai_buoc === "may") {
    // Công thức chốt 2026-08-04: SL vào × 60 ÷ tốc độ × số lượt.
    const tocDo = coMay ? f(may?.tocDo) : numOf("toc_do");
    const tocDoMax = coMay ? f(may?.tocDoMax) : numOf("toc_do_max");
    const tocDoMin = coMay ? f(may?.tocDoMin) : numOf("toc_do_min");
    const chayVoi = (v: number): number => (v > 0 && vao > 0 ? (vao * 60) / v * luot : 0);
    nangSuatCoSo = tocDo;
    nangSuatHieuDung = tocDo;
    chay = chayVoi(tocDo);
    chayNhanh = tocDoMax > 0 ? chayVoi(tocDoMax) : chay;   // tốc độ TỐI ĐA ⇒ thời lượng nhỏ nhất
    chayCham = tocDoMin > 0 ? chayVoi(tocDoMin) : chay;
    if (tocDo <= 0) phuongPhap = "thieu_nang_suat";
  }
  // Chưa quy đổi được SL vào sang đơn vị tốc độ ⇒ không có giờ chạy, và nói đúng chỗ phải đi khai.
  // Thắng mọi lý do khác: có tốc độ mà không biết bước nhận bao nhiêu THEO ĐƠN VỊ ĐÓ thì phép chia
  // vô nghĩa (chủ 15/08/2026 — ca `500 kg/h` nhận số tờ).
  if (r.loai_buoc !== "thue_ngoai" && !daQuyDoi) {
    phuongPhap = "chua_quy_doi";
    chay = chayNhanh = chayCham = 0;
    canhBao.push(
      "Chưa quy đổi được số lượng vào sang đơn vị của tốc độ nên không tính được thời gian chạy. " +
      "Khai cầu quy đổi (hoặc công thức cho đơn vị đó) ở Cấu hình danh mục → Đơn vị & quy đổi."
    );
  } else if (phuongPhap === "thieu_nang_suat") {
    canhBao.push("Máy đang gán chưa khai tốc độ (hoặc bước chưa gán máy) nên không tính được thời gian chạy.");
  }

  const chiemTaiNguyen = khac + setup + chay;
  return {
    phuong_phap: phuongPhap,
    // Số + đơn vị ĐÃ QUY ĐỔI (thứ thật sự đem chia); số/đơn vị gốc của bước đi kèm để câu diễn
    // giải nói được cả hai chặng — cùng hình dạng server trả.
    so_luong_vao: tron(vao),
    don_vi_vao: (dgServer.don_vi_vao as string | null) ?? r.don_vi_vao,
    so_luong_vao_goc: dgServer.so_luong_vao_goc ?? f(r.so_luong_vao),
    don_vi_vao_goc: (dgServer.don_vi_vao_goc as string | null) ?? r.don_vi_vao,
    quy_doi_dien_giai: dgServer.quy_doi_dien_giai ?? null,
    nguon_nang_suat: r.loai_buoc === "to" ? "dau_viec" : (r.loai_buoc === "may" ? "may" : null),
    nang_suat_co_so: nangSuatCoSo > 0 ? tron(nangSuatCoSo) : null,
    nang_suat_hieu_dung: nangSuatHieuDung > 0 ? tron(nangSuatHieuDung) : null,
    so_luot_chay: r.loai_buoc === "may" ? luot : null,
    so_nhan_cong_ke_hoach: r.loai_buoc === "thue_ngoai" ? null : nguoiKeHoach,
    so_nhan_cong_tieu_chuan: r.loai_buoc === "thue_ngoai" ? null : r.so_nhan_cong_tieu_chuan,
    so_nhan_cong_toi_da: r.loai_buoc === "to" ? r.so_nhan_cong_toi_da : null,
    // Bước TỔ nhân kíp chuẩn vào công thức (chốt 20/08/2026) ⇒ "số người tính" = số người tiêu chuẩn.
    so_nhan_cong_tinh: nguoiTinh,
    setup_phut: tron(setup),
    chuan_bi_khoan: khoanChuanBi,
    phat_sinh_phut: tron(khac),
    chay_phut: tron(chay),
    chay_phut_min: tron(chayNhanh),
    chay_phut_max: tron(chayCham),
    toc_do: coMay ? (may?.tocDo ?? null) : (dgServer.toc_do ?? null),
    toc_do_min: coMay ? (may?.tocDoMin ?? null) : (dgServer.toc_do_min ?? null),
    toc_do_max: coMay ? (may?.tocDoMax ?? null) : (dgServer.toc_do_max ?? null),
    co_dai_toc_do: tron(chayNhanh) !== tron(chayCham),
    chiem_tai_nguyen_phut: tron(chiemTaiNguyen),
    // Chờ kỹ thuật GỠ 13/08/2026 ⇒ tổng bằng đúng phần chiếm tài nguyên.
    tong_phut: tron(chiemTaiNguyen),
    canh_bao: canhBao,
  };
}

/** Thời lượng bước cho bảng/thẻ. `chiemMin`/`chiemMax` = cùng công thức với tốc độ tối đa /
 *  tối thiểu của máy; máy chưa khai dải thì cả ba bằng nhau (`coDai` = false). */
export function thoiLuong(r: EditRow, may?: MayTinhGio | null): {
  chay: number; chiemMay: number; tong: number;
  chiemMin: number; chiemMax: number; coDai: boolean;
} {
  const d = thoiLuongLive(r, may);
  const co_dinh = Number(d.phat_sinh_phut ?? 0) + Number(d.setup_phut ?? 0);
  return {
    chay: Number(d.chay_phut ?? 0),
    chiemMay: Number(d.chiem_tai_nguyen_phut ?? 0),
    tong: Number(d.tong_phut ?? 0),
    chiemMin: co_dinh + Number(d.chay_phut_min ?? d.chay_phut ?? 0),
    chiemMax: co_dinh + Number(d.chay_phut_max ?? d.chay_phut ?? 0),
    coDai: Boolean(d.co_dai_toc_do),
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

/** Mã đơn vị → TÊN trong danh mục (`to` → "tờ"). Chưa nạp xong / mã lạ ⇒ trả mã trần.
 *  Không còn bảng nhãn cứng — xem `tenDonVi.ts`. */
export function nhanDonVi(dv: string | null | undefined): string {
  return dv ? tenDonVi(dv) ?? dv : "";
}

export interface DonViChuoi {
  /** Chặng TỜ IN — thứ bước in đếm. */
  to: string;
  /** Chặng THÀNH PHẨM — đầu ra của bước đổi mức cuối. */
  tp: string;
  /** Chặng GIỮA (tay sách) — chỉ có khi chuỗi đổi mức từ 2 lần trở lên. "" = không có. */
  tay: string;
  /** Chặng TỜ NGUYÊN. Routing KHÔNG có bước xả giấy ⇒ tờ nguyên đếm bằng chính đơn vị tờ in
   *  (không xả thì một tờ nguyên đúng là một tờ in), nên trả luôn `to` — KHÔNG bịa chữ khác. */
  toNguyen: string;
}

/** Hình dạng SERVER gửi mã bốn chặng — `LsxDetail` và mỗi dòng "lệnh dự kiến" đều có bộ này. */
export interface MaDonViChuoi {
  don_vi_to?: string | null;
  don_vi_tp?: string | null;
  don_vi_tay?: string | null;
  don_vi_to_nguyen?: string | null;
}

/** MÃ bốn chặng (server) → TÊN bốn chặng (danh mục).
 *
 *  LUẬT SUY CHẶNG NẰM Ở SERVER, đúng một bản: `services/dong_giay.don_vi_chuoi`. Hàm này chỉ dịch
 *  mã sang tên. Trước 12/08/2026 frontend giữ bản chép tay thứ hai của cùng luật đó — và cả hai
 *  bản đã CÙNG SAI y hệt nhau ở chặng "tay" (lấy bước đổi mức đầu tiên, vốn là bước xả giấy chứ
 *  không phải bước gấp). Hai bản cùng luật không giúp bắt lỗi, chỉ nhân đôi chỗ phải sửa.
 *
 *  Hai lối lùi ở đây là DẪN XUẤT chứ không phải nhãn bịa:
 *   · `tp` rỗng → ĐVT của chính sản phẩm (người dùng khai ở đơn/phiếu).
 *   · `toNguyen` rỗng → dùng `to`: routing không có bước xả thì một tờ nguyên đúng là một tờ in.
 *  Ngoài hai lối đó, chặng nào server không nói thì trả RỖNG — nơi gọi hiện mỗi con số. Nhãn khối
 *  đã nói CHẶNG ("Vào máy" · "Giấy nguyên") nên rỗng cũng không mất nghĩa.
 */
export function donViChuoi(src: MaDonViChuoi, dvSanPham?: string | null): DonViChuoi {
  const to = nhanDonVi(src.don_vi_to);
  return {
    to,
    tp: nhanDonVi(src.don_vi_tp) || dvSanPham || "",
    tay: nhanDonVi(src.don_vi_tay),
    toNguyen: nhanDonVi(src.don_vi_to_nguyen) || to,
  };
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
