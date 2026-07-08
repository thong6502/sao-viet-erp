// Config 6 danh mục rebuild cho RebuildCatalogPage. Field có `group` (section trong drawer)
// + `facet` (tab lọc). Render pill/number cho cột. Field lean — đủ dùng; đầy đủ spec là follow-up.
import type { CatalogConfig, ColumnDef } from "./RebuildCatalogPage";
import type { Row } from "../api/rebuildCatalog";

const opt = (...vs: string[]) => vs.map((v) => ({ value: v, label: v }));
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
  subtitle: "Template sản phẩm — gán quy tắc bình bài + routing mặc định + VAT (spec-san-pham).",
  prefix: "/api/loai-san-pham",
  facet: { key: "structural_type", values: [
    { value: "flat", label: "Phẳng" }, { value: "multipage", label: "Nhiều trang" },
    { value: "box", label: "Hộp" }, { value: "label", label: "Tem nhãn" }] },
  columns: [
    { key: "structural_type", label: "Kiểu" },
    { key: "vat_rate", label: "VAT", render: (r) => `${r.vat_rate}%` },
    STATUS_COL,
  ],
  fields: [
    { key: "structural_type", label: "Kiểu cấu trúc", type: "select", required: true, group: "Cấu trúc",
      options: opt("flat", "multipage", "box", "label") },
    { key: "box_sub_type", label: "Loại hộp", type: "select", group: "Cấu trúc",
      options: opt("folding_carton", "corrugated", "rigid"), hint: "khi kiểu = box" },
    { key: "vat_rate", label: "VAT %", type: "select", group: "Thương mại", options: opt("5", "8", "10") },
    { key: "default_so_mat", label: "Số mặt mặc định", type: "number", group: "Thương mại" },
    { key: "has_cover", label: "Có bìa riêng", type: "checkbox", group: "Bìa (nhiều trang)" },
    { key: "cover_type", label: "Kiểu bìa", type: "select", group: "Bìa (nhiều trang)", options: opt("tu_bia", "bia_roi") },
    { key: "default_binding", label: "Đóng mặc định", type: "select", group: "Bìa (nhiều trang)", options: opt("ghim", "keo", "khau") },
    { key: "imposition_rule_id", label: "Quy tắc bình bài (id)", type: "number", group: "Liên kết", hint: "→ Quy tắc bình bài" },
    { key: "routing_template", label: "Routing (list id công đoạn)", type: "json", group: "Liên kết", hint: "vd [2,3,5]" },
  ],
};

export const CFG_MAY: CatalogConfig = {
  title: "Thiết bị & Máy in",
  subtitle: "Máy = cost center (BHR) + spec năng lực (khổ/nhíp/units) — spec-may-thiet-bi.",
  prefix: "/api/may-thiet-bi",
  facet: { key: "loai_may", values: [
    { value: "press_offset_sheet", label: "Offset tờ" }, { value: "press_digital", label: "Digital" },
    { value: "prepress_ctp", label: "CTP" }, { value: "finishing", label: "Sau in" },
    { value: "thue_ngoai", label: "Thuê ngoài" }] },
  columns: [
    { key: "loai_may", label: "Loại máy" },
    { key: "khoa_class", label: "Khổ (kẽm)" },
    { key: "trang_thai", label: "Trạng thái", render: (r) => (
      <span className={`rc-pill ${r.trang_thai === "active" ? "rc-pill--on" : "rc-pill--off"}`}>{String(r.trang_thai)}</span>) },
  ],
  fields: [
    { key: "loai_may", label: "Loại máy", type: "select", required: true, group: "Nhận diện",
      options: opt("press_offset_sheet", "press_offset_web", "press_digital", "press_flexo_label",
        "press_gravure", "wide_format", "prepress_ctp", "finishing", "thue_ngoai", "other") },
    { key: "trang_thai", label: "Trạng thái", type: "select", group: "Nhận diện", options: opt("active", "maintenance", "retired") },
    { key: "khoa_class", label: "Lớp khổ (giá kẽm)", type: "select", group: "Nhận diện", options: opt("52", "74", "79", "102", "custom") },
    { key: "kho_max_dai", label: "Khổ máy max — dài (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "kho_max_rong", label: "Khổ máy max — rộng (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "kho_min_dai", label: "Khổ máy min — dài (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "kho_min_rong", label: "Khổ máy min — rộng (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "gripper_mm", label: "Nhíp (mm)", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "so_units", label: "Số units", type: "number", group: "Khổ & nhíp (bình bài)" },
    { key: "von_dau_tu", label: "Vốn đầu tư (đ)", type: "number", group: "Chi phí BHR" },
    { key: "nam_khau_hao", label: "Năm khấu hao", type: "number", group: "Chi phí BHR" },
    { key: "gio_lam_nam", label: "Giờ làm/năm", type: "number", group: "Chi phí BHR" },
    { key: "availability_pct", label: "Availability %", type: "number", group: "Chi phí BHR" },
    { key: "productivity_pct", label: "Productivity %", type: "number", group: "Chi phí BHR" },
    { key: "luong_gio", label: "Lương/giờ (đ)", type: "number", group: "Chi phí BHR" },
    { key: "so_nhan_cong", label: "Số nhân công", type: "number", group: "Chi phí BHR" },
    { key: "cong_suat_kW", label: "Công suất (kW)", type: "number", group: "Chi phí BHR" },
    { key: "don_gia_dien", label: "Đơn giá điện (đ/kWh)", type: "number", group: "Chi phí BHR" },
    { key: "toc_do", label: "Tốc độ (tờ/giờ)", type: "number", group: "Tốc độ & lãi" },
    { key: "markup_pct", label: "Markup máy %", type: "number", group: "Tốc độ & lãi" },
  ],
};

export const CFG_CONG_DOAN: CatalogConfig = {
  title: "Công đoạn gia công",
  subtitle: "Danh mục thao tác + cách tính giá (spec-cong-doan). Routing per-job = engine.",
  prefix: "/api/cong-doan",
  facet: { key: "nhom", values: [
    { value: "prepress", label: "Chế bản" }, { value: "print", label: "In" }, { value: "finishing", label: "Gia công" }] },
  columns: [
    { key: "nhom", label: "Nhóm" },
    { key: "che_do_tinh", label: "Chế độ" },
    { key: "pricing_basis", label: "Đơn vị" },
    STATUS_COL,
  ],
  fields: [
    { key: "nhom", label: "Nhóm", type: "select", required: true, group: "Phân loại", options: opt("prepress", "print", "finishing") },
    { key: "may_id", label: "Máy (id)", type: "number", group: "Phân loại", hint: "→ Thiết bị & Máy" },
    { key: "che_do_tinh", label: "Chế độ tính", type: "select", group: "Phân loại", options: opt("theo_gio", "theo_san_luong") },
    { key: "pricing_basis", label: "Đơn vị (theo sản lượng)", type: "select", group: "Phân loại",
      options: opt("per_sheet", "per_ram", "per_1000_luot", "per_m2", "per_pass", "per_book", "per_number") },
    { key: "setup_cost", label: "Phí setup (đ)", type: "number", group: "Giá" },
    { key: "run_rate", label: "Đơn giá / đơn vị (đ)", type: "number", group: "Giá" },
    { key: "first_unit_floor", label: "Sàn bậc đầu (đ)", type: "number", group: "Giá", hint: "vd 1.000 lượt đầu" },
    { key: "min_charge", label: "Sàn cả công đoạn (đ)", type: "number", group: "Giá" },
    { key: "requires_tooling", label: "Cần khuôn/kẽm", type: "checkbox", group: "Khuôn & hao" },
    { key: "tooling_type", label: "Loại khuôn", type: "select", group: "Khuôn & hao", options: opt("khuon_be", "khuon_ep", "kem") },
    { key: "spoilage_pct", label: "Hao %", type: "number", group: "Khuôn & hao", hint: "bước in tự ép 0" },
  ],
};

const KHO_FACET = undefined;

export const CFG_GIAY: CatalogConfig = {
  title: "Kho · Giấy nguyên",
  subtitle: "Tờ giấy nguyên (khổ mua) — engine tính giá đọc (spec-tinh-gia §3.1).",
  prefix: "/api/vat-lieu-kho/giay",
  facet: KHO_FACET,
  columns: [
    { key: "gsm", label: "GSM" },
    { key: "kho", label: "Khổ (mm)", render: (r) => `${r.kho_rong}×${r.kho_dai}` },
    { key: "don_gia", label: "Đơn giá", render: (r) => `${vnd(r.don_gia)}/${r.don_vi_gia}` },
    { key: "ton", label: "Tồn", render: (r) => vnd(r.ton) },
  ],
  fields: [
    { key: "kho_dai", label: "Khổ dài (mm)", type: "number", required: true, group: "Khổ & định lượng" },
    { key: "kho_rong", label: "Khổ rộng (mm)", type: "number", required: true, group: "Khổ & định lượng" },
    { key: "gsm", label: "GSM", type: "number", required: true, group: "Khổ & định lượng" },
    { key: "caliper_micron", label: "Độ dày (µm)", type: "number", group: "Khổ & định lượng", hint: "spine/creep" },
    { key: "tho", label: "Thớ", type: "select", group: "Khổ & định lượng", options: opt("canh_dai", "canh_ngan") },
    { key: "don_vi_gia", label: "Đơn vị giá", type: "select", group: "Giá & tồn", options: opt("kg", "ram", "to") },
    { key: "don_gia", label: "Đơn giá (đ)", type: "number", group: "Giá & tồn" },
    { key: "ton", label: "Tồn", type: "number", group: "Giá & tồn" },
  ],
};

export const CFG_MUC: CatalogConfig = {
  title: "Kho · Mực",
  subtitle: "Mực in — mặt hàng Kho engine đọc.",
  prefix: "/api/vat-lieu-kho/muc",
  columns: [
    { key: "loai_muc", label: "Loại" },
    { key: "don_gia", label: "Đơn giá (/1000 lượt)", render: (r) => vnd(r.don_gia) },
  ],
  fields: [
    { key: "loai_muc", label: "Loại mực", type: "select", group: "Thông số", options: opt("process", "pantone", "special") },
    { key: "ma_pantone", label: "Mã Pantone", type: "text", group: "Thông số" },
    { key: "don_gia", label: "Đơn giá (đ/1000 lượt)", type: "number", group: "Giá" },
  ],
};

export const CFG_BAN_KEM: CatalogConfig = {
  title: "Kho · Bản kẽm",
  subtitle: "Bản kẽm — giá tra theo khổ máy (khoa_class), nuôi kem_line.",
  prefix: "/api/vat-lieu-kho/ban-kem",
  columns: [
    { key: "khoa_class", label: "Khổ máy" },
    { key: "don_gia_kem", label: "Giá/bản", render: (r) => vnd(r.don_gia_kem) },
    { key: "ton", label: "Tồn", render: (r) => vnd(r.ton) },
  ],
  fields: [
    { key: "khoa_class", label: "Lớp khổ máy", type: "select", required: true, group: "Thông số", options: opt("52", "74", "79", "102", "custom") },
    { key: "don_gia_kem", label: "Đơn giá / bản (đ)", type: "number", group: "Giá" },
    { key: "ton", label: "Tồn", type: "number", group: "Giá" },
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
