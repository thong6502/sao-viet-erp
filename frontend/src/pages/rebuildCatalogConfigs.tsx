// Config 6 danh mục rebuild cho RebuildCatalogPage. Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id).
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

const LOAI_MAY: Lbls = {
  press_offset_sheet: "In offset tờ rời", press_offset_web: "In offset cuộn", press_digital: "In kỹ thuật số",
  press_flexo_label: "In flexo (tem nhãn)", press_gravure: "In ống đồng", wide_format: "In khổ lớn",
  prepress_ctp: "Ghi kẽm CTP", finishing: "Máy gia công sau in", thue_ngoai: "Thuê ngoài", other: "Khác",
};
const TRANG_THAI_MAY: Lbls = { active: "Đang chạy", maintenance: "Bảo trì", retired: "Ngừng dùng" };
const KHOA_CLASS: Lbls = { "52": "Khổ 52", "74": "Khổ 74", "79": "Khổ 79", "102": "Khổ 102", custom: "Khổ khác" };

const NHOM_CD: Lbls = { prepress: "Chế bản", print: "In", finishing: "Gia công sau in" };
const CHE_DO: Lbls = { theo_gio: "Theo giờ máy", theo_san_luong: "Theo sản lượng" };
const PRICING_BASIS: Lbls = {
  per_sheet: "Theo tờ in", per_ram: "Theo ram (500 tờ)", per_1000_luot: "Theo 1.000 lượt",
  per_m2: "Theo m²", per_pass: "Theo lượt in", per_book: "Theo cuốn", per_number: "Theo con/số",
};
const TOOLING: Lbls = { khuon_be: "Khuôn bế", khuon_ep: "Khuôn ép (nhũ/nổi)", kem: "Kẽm" };

const THO: Lbls = { canh_dai: "Thớ dọc (canh dài)", canh_ngan: "Thớ ngang (canh ngắn)" };
const DV_GIA_GIAY: Lbls = { kg: "Theo kg", ram: "Theo ram", to: "Theo tờ" };
const LOAI_MUC: Lbls = { process: "Process (CMYK)", pantone: "Pha Pantone", special: "Đặc biệt (nhũ/UV)" };

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
    { key: "imposition_rule_id", label: "Quy tắc bình bài", type: "ref", refPrefix: "/api/quy-tac-binh-bai",
      group: "Dàn khuôn & công đoạn", hint: "Cách dàn khuôn — bao nhiêu con lên 1 tờ in" },
    { key: "routing_template", label: "Chuỗi công đoạn mặc định", type: "ref-multi", refPrefix: "/api/cong-doan",
      group: "Dàn khuôn & công đoạn", hint: "Các bước sản xuất, theo đúng thứ tự chạy" },
  ],
};

export const CFG_MAY: CatalogConfig = {
  title: "Thiết bị & Máy in",
  subtitle: "Máy = trung tâm chi phí (đơn giá giờ máy) + thông số năng lực (khổ / nhíp / số đơn vị in).",
  prefix: "/api/may-thiet-bi",
  facet: { key: "loai_may", values: [
    { value: "press_offset_sheet", label: "Offset tờ" }, { value: "press_digital", label: "Kỹ thuật số" },
    { value: "prepress_ctp", label: "Ghi kẽm" }, { value: "finishing", label: "Sau in" },
    { value: "thue_ngoai", label: "Thuê ngoài" }] },
  columns: [
    { key: "loai_may", label: "Loại máy", render: (r) => lbl(LOAI_MAY)(r.loai_may) },
    { key: "khoa_class", label: "Khổ (giá kẽm)", render: (r) => lbl(KHOA_CLASS)(r.khoa_class) },
    { key: "trang_thai", label: "Trạng thái", render: (r) => (
      <span className={`rc-pill ${r.trang_thai === "active" ? "rc-pill--on" : "rc-pill--off"}`}>{lbl(TRANG_THAI_MAY)(r.trang_thai)}</span>) },
  ],
  fields: [
    { key: "loai_may", label: "Loại máy", type: "select", required: true, group: "Nhận diện", options: mapOpt(LOAI_MAY) },
    { key: "trang_thai", label: "Trạng thái", type: "select", group: "Nhận diện", options: mapOpt(TRANG_THAI_MAY) },
    { key: "khoa_class", label: "Lớp khổ (tra giá kẽm)", type: "select", group: "Nhận diện", options: mapOpt(KHOA_CLASS) },
    { key: "kho_max_dai", label: "Khổ in max — dài (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "kho_max_rong", label: "Khổ in max — rộng (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "kho_min_dai", label: "Khổ in min — dài (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "kho_min_rong", label: "Khổ in min — rộng (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "gripper_mm", label: "Nhíp — chừa đầu (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "so_units", label: "Số đơn vị in (màu)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "von_dau_tu", label: "Vốn đầu tư (đ)", type: "number", group: "Chi phí giờ máy" },
    { key: "nam_khau_hao", label: "Số năm khấu hao", type: "number", group: "Chi phí giờ máy" },
    { key: "gio_lam_nam", label: "Giờ chạy / năm", type: "number", group: "Chi phí giờ máy" },
    { key: "availability_pct", label: "Tỉ lệ máy sẵn sàng %", type: "number", group: "Chi phí giờ máy" },
    { key: "productivity_pct", label: "Hiệu suất chạy máy %", type: "number", group: "Chi phí giờ máy" },
    { key: "luong_gio", label: "Lương / giờ (đ)", type: "number", group: "Chi phí giờ máy" },
    { key: "so_nhan_cong", label: "Số nhân công đứng máy", type: "number", group: "Chi phí giờ máy" },
    { key: "cong_suat_kW", label: "Công suất điện (kW)", type: "number", group: "Chi phí giờ máy" },
    { key: "don_gia_dien", label: "Đơn giá điện (đ/kWh)", type: "number", group: "Chi phí giờ máy" },
    { key: "toc_do", label: "Tốc độ (tờ/giờ)", type: "number", group: "Tốc độ & lãi" },
    { key: "markup_pct", label: "Tỉ lệ lãi máy %", type: "number", group: "Tốc độ & lãi" },
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

export const CFG_GIAY: CatalogConfig = {
  title: "Kho · Giấy nguyên",
  subtitle: "Tờ giấy nguyên (khổ mua) — engine tính giá đọc để pha khổ & tính số tờ.",
  prefix: "/api/vat-lieu-kho/giay",
  facet: KHO_FACET,
  columns: [
    { key: "gsm", label: "Định lượng" },
    { key: "kho", label: "Khổ (mm)", render: (r) => `${r.kho_rong}×${r.kho_dai}` },
    { key: "don_gia", label: "Đơn giá", render: (r) => `${vnd(r.don_gia)}/${lbl({ kg: "kg", ram: "ram", to: "tờ" })(r.don_vi_gia)}` },
    { key: "ton", label: "Tồn", render: (r) => vnd(r.ton) },
  ],
  fields: [
    { key: "kho_dai", label: "Khổ dài (mm)", type: "number", required: true, group: "Khổ & định lượng" },
    { key: "kho_rong", label: "Khổ rộng (mm)", type: "number", required: true, group: "Khổ & định lượng" },
    { key: "gsm", label: "Định lượng (g/m²)", type: "number", required: true, group: "Khổ & định lượng" },
    { key: "caliper_micron", label: "Độ dày (µm)", type: "number", group: "Khổ & định lượng", hint: "cho gáy sách / bù creep" },
    { key: "tho", label: "Thớ giấy", type: "select", group: "Khổ & định lượng", options: mapOpt(THO) },
    { key: "don_vi_gia", label: "Tính giá theo", type: "select", group: "Giá & tồn", options: mapOpt(DV_GIA_GIAY) },
    { key: "don_gia", label: "Đơn giá (đ)", type: "number", group: "Giá & tồn" },
    { key: "ton", label: "Tồn kho", type: "number", group: "Giá & tồn" },
  ],
};

export const CFG_MUC: CatalogConfig = {
  title: "Kho · Mực",
  subtitle: "Mực in — engine tính chi phí mực theo độ phủ.",
  prefix: "/api/vat-lieu-kho/muc",
  columns: [
    { key: "loai_muc", label: "Loại", render: (r) => lbl(LOAI_MUC)(r.loai_muc) },
    { key: "don_gia", label: "Đơn giá (/1.000 lượt)", render: (r) => vnd(r.don_gia) },
  ],
  fields: [
    { key: "loai_muc", label: "Loại mực", type: "select", group: "Thông số", options: mapOpt(LOAI_MUC) },
    { key: "ma_pantone", label: "Mã Pantone", type: "text", group: "Thông số", hint: "khi là mực pha Pantone" },
    { key: "don_gia", label: "Đơn giá (đ / 1.000 lượt)", type: "number", group: "Giá" },
  ],
};

export const CFG_BAN_KEM: CatalogConfig = {
  title: "Kho · Bản kẽm",
  subtitle: "Bản kẽm — giá tra theo lớp khổ máy, nuôi dòng chi phí kẽm khi tính giá.",
  prefix: "/api/vat-lieu-kho/ban-kem",
  columns: [
    { key: "khoa_class", label: "Khổ máy", render: (r) => lbl(KHOA_CLASS)(r.khoa_class) },
    { key: "don_gia_kem", label: "Giá / bản", render: (r) => vnd(r.don_gia_kem) },
    { key: "ton", label: "Tồn", render: (r) => vnd(r.ton) },
  ],
  fields: [
    { key: "khoa_class", label: "Lớp khổ máy", type: "select", required: true, group: "Thông số", options: mapOpt(KHOA_CLASS) },
    { key: "don_gia_kem", label: "Đơn giá / bản (đ)", type: "number", group: "Giá" },
    { key: "ton", label: "Tồn kho", type: "number", group: "Giá" },
  ],
};

export const REBUILD_CONFIGS: Record<string, CatalogConfig> = {
  "loai-san-pham": CFG_LOAI_SAN_PHAM,
  "may-thiet-bi": CFG_MAY,
  "cong-doan": CFG_CONG_DOAN,
  "vl-giay": CFG_GIAY,
  "vl-muc": CFG_MUC,
  "vl-ban-kem": CFG_BAN_KEM,
};
