// Config 6 danh mục rebuild cho RebuildCatalogPage. Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id),
// `default` (prefill khi tạo), `jsonKey` (lưu lồng vào fields_theo_loai).
// Enum hiển thị bằng thuật ngữ in ấn thuần Việt — dùng chung 1 bảng nhãn cho cả dropdown lẫn cột.
import type { CatalogConfig, ColumnDef } from "./RebuildCatalogPage";
import type { Row } from "../api/rebuildCatalog";

// ── Bảng nhãn thuần Việt (in ấn) — 1 nguồn cho options + column render ──────────
type Lbls = Record<string, string>;
const mapOpt = (m: Lbls) => Object.entries(m).map(([value, label]) => ({ value, label }));
const lbl = (m: Lbls) => (v: unknown) => (v == null || v === "" ? "—" : (m[String(v)] ?? String(v)));

const STRUCTURAL: Lbls = { flat: "Tờ phẳng", multipage: "Nhiều trang", box: "Hộp", label: "Tem / nhãn" };
const BOX_SUB: Lbls = { folding_carton: "Hộp giấy gấp", corrugated: "Thùng carton sóng", rigid: "Hộp cứng" };
const COVER: Lbls = { tu_bia: "Bìa tự thân (cùng ruột)", bia_roi: "Bìa rời (giấy khác)" };
const BINDING: Lbls = { ghim: "Đóng ghim", keo: "Vào keo", khau: "Khâu chỉ" };
const VAT: Lbls = { "5": "5%", "8": "8%", "10": "10%" };

const NHOM_CD: Lbls = { prepress: "Chế bản", print: "In", finishing: "Gia công sau in" };
const CHE_DO: Lbls = { theo_gio: "Theo giờ máy", theo_san_luong: "Theo sản lượng" };
const PRICING_BASIS: Lbls = {
  per_sheet: "Theo tờ in", per_ram: "Theo ram (500 tờ)", per_1000_luot: "Theo 1.000 lượt",
  per_m2: "Theo m²", per_pass: "Theo lượt in", per_book: "Theo cuốn", per_number: "Theo con/số",
};
const TOOLING: Lbls = { khuon_be: "Khuôn bế", khuon_ep: "Khuôn ép (nhũ/nổi)", kem: "Kẽm" };

const THO: Lbls = { canh_dai: "Thớ dọc (canh dài)", canh_ngan: "Thớ ngang (canh ngắn)" };
const DV_GIA_GIAY: Lbls = { kg: "KG", cai: "CÁI", ram: "Ram", to: "Tờ" };
const BE_MAT: Lbls = { bong: "Bóng", mo: "Mờ", nham: "Nhám" };
const DV_GIA_VAT_TU: Lbls = {
  kg: "KG", lit: "LÍT", ban: "BẢN", cai: "CÁI", bo: "BỘ", thung: "THÙNG",
  nghin_luot: "1.000 lượt", met: "MÉT", m2: "M²", cuon: "CUỘN",
};

const vnd = (v: unknown) => (v == null || v === "" ? "—" : Number(v).toLocaleString("vi-VN"));

const STATUS_COL: ColumnDef = {
  key: "active", label: "Trạng thái",
  render: (r: Row) => (
    <span className={`rc-pill ${r.active === false ? "rc-pill--off" : "rc-pill--on"}`}>
      {r.active === false ? "Tạm ngưng" : "Đang dùng"}
    </span>
  ),
};

export const CFG_LOAI_SAN_PHAM: CatalogConfig = {
  title: "Loại sản phẩm",
  subtitle: "Khuôn mẫu sản phẩm — gán cách dàn khuôn (bình bài) + chuỗi công đoạn mặc định + VAT.",
  prefix: "/api/loai-san-pham",
  facet: { key: "structural_type", values: mapOpt(STRUCTURAL) },
  columns: [
    { key: "structural_type", label: "Kiểu", render: (r) => lbl(STRUCTURAL)(r.structural_type) },
    { key: "vat_rate", label: "VAT", render: (r) => `${r.vat_rate}%` },
    STATUS_COL,
  ],
  fields: [
    { key: "structural_type", label: "Kiểu cấu trúc", type: "select", required: true, group: "Cấu trúc",
      options: mapOpt(STRUCTURAL), hint: "Quyết định các ô bên dưới hiện ra" },
    { key: "box_sub_type", label: "Loại hộp", type: "select", group: "Cấu trúc",
      options: mapOpt(BOX_SUB), showIf: (f) => f.structural_type === "box" },
    { key: "vat_rate", label: "Thuế VAT", type: "select", group: "Thương mại", options: mapOpt(VAT) },
    { key: "default_so_mat", label: "Số mặt in mặc định", type: "number", group: "Thương mại", hint: "1 = in 1 mặt, 2 = in 2 mặt" },
    { key: "has_cover", label: "Có bìa riêng", type: "checkbox", group: "Bìa (nhiều trang)",
      showIf: (f) => f.structural_type === "multipage" },
    { key: "cover_type", label: "Kiểu bìa", type: "select", group: "Bìa (nhiều trang)",
      options: mapOpt(COVER), showIf: (f) => f.structural_type === "multipage" },
    { key: "default_binding", label: "Kiểu đóng gáy", type: "select", group: "Bìa (nhiều trang)",
      options: mapOpt(BINDING), showIf: (f) => f.structural_type === "multipage" },
    { key: "routing_template", label: "Chuỗi công đoạn mặc định", type: "ref-multi", refPrefix: "/api/cong-doan",
      group: "Công đoạn mặc định", hint: "Các bước sản xuất, theo đúng thứ tự chạy" },
  ],
};

// Form MỞ (phẳng): mọi ô luôn hiện, không phân loại cứng. Chủ xưởng tự đặt "Nhóm máy"
// (chữ tự do) rồi nhập khổ kẽm / nhíp / khổ giấy / vùng in / ghi chú.
export const CFG_MAY: CatalogConfig = {
  title: "Thiết bị & Máy in",
  subtitle: "Nhập tự do mọi loại máy (in, cán màng/UV, bồi, bế…). Tự đặt Nhóm máy rồi điền khổ kẽm, nhíp kẽm, khổ giấy, vùng in.",
  prefix: "/api/may-thiet-bi",
  columns: [
    { key: "loai_may", label: "Nhóm máy", render: (r) => (r.loai_may ? String(r.loai_may) : "—") },
    { key: "kho_max", label: "Khổ giấy max (mm)",
      render: (r) => (r.kho_max_rong || r.kho_max_dai ? `${r.kho_max_rong ?? "?"}×${r.kho_max_dai ?? "?"}` : "—") },
  ],
  fields: [
    // ── Nhóm máy (chữ tự do — chỉ để nhóm/lọc, không điều khiển ẩn/hiện) ─────────
    { key: "loai_may", label: "Nhóm máy", type: "text", required: true, group: "Phân loại",
      hint: "Gõ tự do, vd: Máy in, Cán màng, Bồi sóng, Bế…" },
    // ── Khổ kẽm + nhíp kẽm ─────────────────────────────────────────────────────
    { key: "kho_kem_rong", label: "Khổ kẽm — rộng (mm)", type: "number", group: "Khổ kẽm & vùng in",
      hint: "Bản kẽm máy nhận, vd 800*1030 (rộng*dài)" },
    { key: "kho_kem_dai", label: "Khổ kẽm — dài (mm)", type: "number", group: "Khổ kẽm & vùng in" },
    { key: "gripper_mm", label: "Nhíp kẽm (mm)", type: "number", group: "Khổ kẽm & vùng in",
      hint: "Mép nhíp trên kẽm, vd 44 mm" },
    // ── Vùng in lớn nhất ───────────────────────────────────────────────────────
    { key: "vung_in_rong", label: "Vùng in max — rộng (mm)", type: "number", group: "Khổ kẽm & vùng in",
      hint: "Vùng in được lớn nhất, vd 710*1010 (rộng*dài)" },
    { key: "vung_in_dai", label: "Vùng in max — dài (mm)", type: "number", group: "Khổ kẽm & vùng in" },
    // ── Khổ giấy min/max ───────────────────────────────────────────────────────
    { key: "kho_min_rong", label: "Khổ giấy min — rộng (mm)", type: "number", group: "Khổ giấy" },
    { key: "kho_min_dai", label: "Khổ giấy min — dài (mm)", type: "number", group: "Khổ giấy" },
    { key: "kho_max_rong", label: "Khổ giấy max — rộng (mm)", type: "number", group: "Khổ giấy" },
    { key: "kho_max_dai", label: "Khổ giấy max — dài (mm)", type: "number", group: "Khổ giấy" },
    // ── Ghi chú ────────────────────────────────────────────────────────────────
    { key: "ghi_chu", label: "Ghi chú 1", type: "text", group: "Ghi chú" },
    { key: "ghi_chu_2", label: "Ghi chú 2", type: "text", group: "Ghi chú" },
  ],
};

export const CFG_CONG_DOAN: CatalogConfig = {
  title: "Công đoạn gia công",
  subtitle: "Danh mục thao tác + cách tính giá. Chuỗi công đoạn của từng đơn = do Loại sản phẩm gán.",
  prefix: "/api/cong-doan",
  facet: { key: "nhom", values: mapOpt(NHOM_CD) },
  columns: [
    { key: "nhom", label: "Nhóm", render: (r) => lbl(NHOM_CD)(r.nhom) },
    { key: "che_do_tinh", label: "Chế độ", render: (r) => lbl(CHE_DO)(r.che_do_tinh) },
    { key: "pricing_basis", label: "Đơn vị", render: (r) => lbl(PRICING_BASIS)(r.pricing_basis) },
    STATUS_COL,
  ],
  fields: [
    { key: "nhom", label: "Nhóm công đoạn", type: "select", required: true, group: "Phân loại", options: mapOpt(NHOM_CD) },
    { key: "may_id", label: "Máy thực hiện", type: "ref", refPrefix: "/api/may-thiet-bi", group: "Phân loại",
      hint: "Chọn máy đảm nhận công đoạn này" },
    { key: "che_do_tinh", label: "Cách tính giá", type: "select", group: "Phân loại", options: mapOpt(CHE_DO) },
    { key: "pricing_basis", label: "Tính theo đơn vị", type: "select", group: "Phân loại",
      options: mapOpt(PRICING_BASIS), showIf: (f) => f.che_do_tinh === "theo_san_luong" },
    { key: "setup_cost", label: "Phí chuẩn bị / setup (đ)", type: "number", group: "Giá" },
    { key: "run_rate", label: "Đơn giá / đơn vị (đ)", type: "number", group: "Giá" },
    { key: "first_unit_floor", label: "Sàn bậc đầu (đ)", type: "number", group: "Giá", hint: "vd 1.000 lượt đầu tính trọn gói" },
    { key: "min_charge", label: "Sàn cả công đoạn (đ)", type: "number", group: "Giá", hint: "Thu tối thiểu dù ít" },
    { key: "requires_tooling", label: "Cần khuôn / kẽm", type: "checkbox", group: "Khuôn & hao" },
    { key: "tooling_type", label: "Loại khuôn", type: "select", group: "Khuôn & hao",
      options: mapOpt(TOOLING), showIf: (f) => !!f.requires_tooling },
    { key: "spoilage_pct", label: "Hao hụt %", type: "number", group: "Khuôn & hao", hint: "Bù bù hao cho bước sau" },
  ],
};

const KHO_FACET = undefined;

export const CFG_CHUNG_LOAI_GIAY: CatalogConfig = {
  title: "Chủng loại giấy",
  subtitle: "Phân loại giấy (Couché / Ford / Bristol / Ivory / Duplex / Kraft…). Giấy chọn theo đây.",
  prefix: "/api/vat-lieu-kho/chung-loai-giay",
  columns: [
    { key: "be_mat", label: "Bề mặt", render: (r) => lbl(BE_MAT)(r.be_mat) },
    { key: "tho_mac_dinh", label: "Thớ mặc định", render: (r) => lbl(THO)(r.tho_mac_dinh) },
    STATUS_COL,
  ],
  fields: [
    { key: "be_mat", label: "Bề mặt", type: "select", group: "Thông số", options: mapOpt(BE_MAT) },
    { key: "tho_mac_dinh", label: "Thớ mặc định", type: "select", group: "Thông số", options: mapOpt(THO) },
    { key: "mo_ta", label: "Mô tả", type: "text", group: "Thông số" },
  ],
};

export const CFG_GIAY: CatalogConfig = {
  title: "Giấy",
  subtitle: "Từng loại giấy cụ thể (khổ mua) — thuộc 1 Chủng loại giấy.",
  prefix: "/api/vat-lieu-kho/giay",
  facet: KHO_FACET,
  columns: [
    { key: "gsm", label: "Định lượng" },
    { key: "kho", label: "Khổ (mm)", render: (r) => (Number(r.kho_rong) || Number(r.kho_dai) ? `${r.kho_rong}×${r.kho_dai}` : "Cuộn / khổ mở") },
    { key: "don_vi_gia", label: "ĐVT", render: (r) => lbl(DV_GIA_GIAY)(r.don_vi_gia) },
    { key: "don_gia", label: "Giá", render: (r) => vnd(r.don_gia) },
  ],
  fields: [
    { key: "chung_loai_giay_id", label: "Chủng loại giấy", type: "ref", required: true,
      refPrefix: "/api/vat-lieu-kho/chung-loai-giay", group: "Phân loại" },
    { key: "kho_rong", label: "Khổ rộng (mm)", type: "number", group: "Khổ & định lượng", hint: "0 = cuộn / khổ mở" },
    { key: "kho_dai", label: "Khổ dài (mm)", type: "number", group: "Khổ & định lượng", hint: "0 = cuộn / khổ mở" },
    { key: "gsm", label: "Định lượng (g/m²)", type: "number", required: true, group: "Khổ & định lượng" },
    { key: "caliper_micron", label: "Độ dày (µm)", type: "number", group: "Khổ & định lượng", hint: "cho gáy sách / bù creep" },
    { key: "tho", label: "Thớ giấy", type: "select", group: "Khổ & định lượng", options: mapOpt(THO) },
    { key: "don_vi_gia", label: "ĐVT", type: "select", group: "Giá", options: mapOpt(DV_GIA_GIAY) },
    { key: "don_gia", label: "Đơn giá (đ)", type: "number", group: "Giá" },
    { key: "gia_thi_truong", label: "Giá thị trường (đ)", type: "number", group: "Giá", hint: "tham khảo, không bắt buộc" },
    { key: "kho_tinh_gia", label: "Khổ dùng để tính giá?", type: "checkbox", group: "Giá" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Giá" },
  ],
};

export const CFG_VAT_TU: CatalogConfig = {
  title: "Vật tư in ấn",
  subtitle: "Mực, bản kẽm, hoá chất, màng, keo… — mã · tên · ĐVT · giá · ghi chú.",
  prefix: "/api/vat-lieu-kho/vat-tu-in-an",
  columns: [
    { key: "don_vi_gia", label: "ĐVT", render: (r) => lbl(DV_GIA_VAT_TU)(r.don_vi_gia) },
    { key: "don_gia", label: "Giá", render: (r) => vnd(r.don_gia) },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "—") },
    STATUS_COL,
  ],
  fields: [
    { key: "don_vi_gia", label: "Đơn vị tính (ĐVT)", type: "select", group: "Giá", options: mapOpt(DV_GIA_VAT_TU) },
    { key: "don_gia", label: "Giá (đ)", type: "number", group: "Giá" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Giá" },
  ],
};

export const CFG_KHO_GIAY_CHUAN: CatalogConfig = {
  title: "Khổ giấy chuẩn",
  subtitle: "Mỗi dòng = 1 khổ của 1 chủng loại giấy (cm). Khổ dài trống = giấy cuộn / khổ mở 1 chiều.",
  prefix: "/api/vat-lieu-kho/kho-giay-chuan",
  columns: [
    { key: "kho", label: "Khổ (cm)", render: (r) => (r.dai ? `${r.rong}×${r.dai}` : `${r.rong} (cuộn)`) },
    { key: "la_hiem", label: "Loại", render: (r) => (
      <span className={`rc-pill ${r.la_hiem ? "rc-pill--off" : "rc-pill--on"}`}>{r.la_hiem ? "Hiếm" : "Chuẩn"}</span>) },
    STATUS_COL,
  ],
  fields: [
    { key: "chung_loai_giay_id", label: "Chủng loại giấy", type: "ref", required: true,
      refPrefix: "/api/vat-lieu-kho/chung-loai-giay", group: "Phân loại" },
    { key: "rong", label: "Khổ rộng (cm)", type: "number", required: true, group: "Khổ" },
    { key: "dai", label: "Khổ dài (cm)", type: "number", group: "Khổ",
      hint: "Bỏ trống = giấy cuộn / khổ mở (cắt tự do chiều dài)" },
    { key: "la_hiem", label: "Khổ hiếm", type: "checkbox", group: "Khổ",
      hint: "Khổ hiếm → báo thu mua / hỏi giấy trước khi dùng" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Khổ" },
  ],
};

export const REBUILD_CONFIGS: Record<string, CatalogConfig> = {
  "loai-san-pham": CFG_LOAI_SAN_PHAM,
  "may-thiet-bi": CFG_MAY,
  "cong-doan": CFG_CONG_DOAN,
  "chung-loai-giay": CFG_CHUNG_LOAI_GIAY,
  "giay": CFG_GIAY,
  "kho-giay-chuan": CFG_KHO_GIAY_CHUAN,
  "vat-tu-in-an": CFG_VAT_TU,
};
