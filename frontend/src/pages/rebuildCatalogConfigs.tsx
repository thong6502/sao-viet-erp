// Config 6 danh mục rebuild cho RebuildCatalogPage. Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id),
// `default` (prefill khi tạo), `jsonKey` (lưu lồng vào fields_theo_loai).
// Enum hiển thị bằng thuật ngữ in ấn thuần Việt — dùng chung 1 bảng nhãn cho cả dropdown lẫn cột.
import type { CatalogConfig } from "./RebuildCatalogPage";

// ── Bảng nhãn thuần Việt (in ấn) — 1 nguồn cho options + column render ──────────
type Lbls = Record<string, string>;
const mapOpt = (m: Lbls) => Object.entries(m).map(([value, label]) => ({ value, label }));
const lbl = (m: Lbls) => (v: unknown) => (v == null || v === "" ? "—" : (m[String(v)] ?? String(v)));

const STRUCTURAL: Lbls = { flat: "Tờ phẳng", multipage: "Nhiều trang", box: "Hộp", label: "Tem / nhãn" };
const BOX_SUB: Lbls = { folding_carton: "Hộp giấy gấp", corrugated: "Thùng carton sóng", rigid: "Hộp cứng" };
const COVER: Lbls = { tu_bia: "Bìa tự thân (cùng ruột)", bia_roi: "Bìa rời (giấy khác)" };
const BINDING: Lbls = { ghim: "Đóng ghim", keo: "Vào keo", khau: "Khâu chỉ" };

const NHOM_CD: Lbls = { prepress: "Chế bản", print: "In", finishing: "Gia công sau in" };
const PRICING_BASIS: Lbls = {
  per_sheet: "Theo số tờ in",
  per_finished_area: "Theo diện tích thành phẩm (cm²)",
  per_finished_qty: "Theo số lượng thành phẩm",
  per_book_page: "Theo số trang sách",
  per_position: "Theo số vị trí",
  per_bag: "Theo bao",
  per_carton: "Theo thùng",
  per_area_sides: "Theo diện tích (cm²) và số mặt",
  per_sheet_area: "Theo diện tích tờ in (cm²)",
  per_book_page_q4: "Theo số trang sách chia 4",
  per_other: "Khác",
};
const TRUC_BU_HAO: Lbls = { so_mau: "Theo số màu (giấy in)", so_con: "Theo số con (sóng bồi/bế)" };
// Cách công đoạn góp bù hao — nối tới trục module Bù hao, hoặc cộng cố định.
const KIEU_BU_HAO: Lbls = {
  khong: "Không bù hao",
  theo_so_mau: "Theo số màu (tra bảng)",
  theo_so_con: "Theo số con (tra bảng)",
  co_dinh: "Cộng cố định (số tờ)",
};

const THO: Lbls = { canh_dai: "Thớ dọc (canh dài)", canh_ngan: "Thớ ngang (canh ngắn)" };
const DV_GIA_GIAY: Lbls = { kg: "KG", cai: "CÁI", ram: "Ram", to: "Tờ" };
const BE_MAT: Lbls = { bong: "Bóng", mo: "Mờ", nham: "Nhám" };
const DV_GIA_VAT_TU: Lbls = {
  kg: "KG", lit: "LÍT", ban: "BẢN", cai: "CÁI", bo: "BỘ", thung: "THÙNG",
  nghin_luot: "1.000 lượt", met: "MÉT", m2: "M²", cuon: "CUỘN",
};

const vnd = (v: unknown) => (v == null || v === "" ? "—" : Number(v).toLocaleString("vi-VN"));


export const CFG_LOAI_SAN_PHAM: CatalogConfig = {
  title: "Loại sản phẩm",
  subtitle: "Khuôn mẫu sản phẩm — gán cách dàn khuôn (bình bài) + chuỗi công đoạn mặc định.",
  prefix: "/api/loai-san-pham",
  facet: { key: "structural_type", values: mapOpt(STRUCTURAL) },
  columns: [
    { key: "structural_type", label: "Kiểu", render: (r) => lbl(STRUCTURAL)(r.structural_type) },
  ],
  fields: [
    { key: "structural_type", label: "Kiểu cấu trúc", type: "select", required: true, group: "Cấu trúc",
      options: mapOpt(STRUCTURAL), hint: "Quyết định các ô bên dưới hiện ra" },
    { key: "box_sub_type", label: "Loại hộp", type: "select", group: "Cấu trúc",
      options: mapOpt(BOX_SUB), showIf: (f) => f.structural_type === "box" },
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
  title: "Công đoạn",
  subtitle: "Danh mục thao tác (chế bản · in · sau in) + cách tính giá. Chuỗi công đoạn của từng đơn = do Loại sản phẩm gán.",
  prefix: "/api/cong-doan",
  facet: { key: "nhom", values: mapOpt(NHOM_CD) },
  columns: [
    { key: "nhom", label: "Giai đoạn", render: (r) => lbl(NHOM_CD)(r.nhom) },
    { key: "pricing_basis", label: "Đơn vị tính giá", render: (r) => lbl(PRICING_BASIS)(r.pricing_basis) },
    { key: "kieu_bu_hao", label: "Bù hao", render: (r) =>
        r.kieu_bu_hao === "co_dinh" ? `Cố định ${r.so_to_bu_hao ?? 50} tờ` : lbl(KIEU_BU_HAO)(r.kieu_bu_hao ?? "khong") },
  ],
  fields: [
    { key: "ten_hien_thi", label: "Tên hiển thị cho sản xuất", type: "text", group: "Thông tin",
      hint: "Tên in cho thợ dưới xưởng đọc (bỏ trống = dùng Tên)" },
    { key: "nhom", label: "Giai đoạn", type: "select", required: true, group: "Thông tin", options: mapOpt(NHOM_CD) },
    { key: "pricing_basis", label: "Đơn vị tính giá", type: "select", group: "Giá", options: mapOpt(PRICING_BASIS),
      hint: "Đếm theo cái gì (tờ / m² / cuốn / giờ…)" },
    { key: "run_rate", label: "Đơn giá / đơn vị (đ)", type: "number", group: "Giá" },
    { key: "min_charge", label: "Giá tối thiểu (đ)", type: "number", group: "Giá", hint: "Thu tối thiểu dù ít" },
    { key: "kieu_bu_hao", label: "Bù hao", type: "select", group: "Bù hao", options: mapOpt(KIEU_BU_HAO), default: "khong",
      hint: "In → Theo số màu · Bồi/Bế sóng → Theo số con · Ép kim/UV → Cộng cố định · Ghi kẽm → Không" },
    { key: "so_to_bu_hao", label: "Số tờ cộng cố định", type: "number", group: "Bù hao", default: 50,
      showIf: (f) => f.kieu_bu_hao === "co_dinh",
      hint: "Mặc định 50; bế nổi / dán móc đáy = 30" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Bù hao" },
  ],
};

export const CFG_BU_HAO: CatalogConfig = {
  title: "Bù hao",
  subtitle: "Tra số tờ bù hao theo trục (số màu / số con) × bậc số lượng. Bậc là dữ liệu — thêm/bớt tự do.",
  prefix: "/api/bu-hao",
  facet: { key: "truc", values: mapOpt(TRUC_BU_HAO) },
  columns: [
    { key: "truc", label: "Tra theo", render: (r) => lbl(TRUC_BU_HAO)(r.truc) },
    { key: "dai", label: "Dải", render: (r) => `${r.key_tu}–${r.key_den}` },
    { key: "bac", label: "Số bậc", render: (r) => `${Array.isArray(r.bac) ? r.bac.length : 0} bậc` },
  ],
  fields: [
    { key: "truc", label: "Tra theo trục", type: "select", required: true, group: "Phân loại",
      options: mapOpt(TRUC_BU_HAO), hint: "Số màu (giấy) hay số con (sóng)" },
    { key: "key_tu", label: "Dải: từ", type: "number", group: "Phân loại", hint: "vd 3 (in 3-4 màu → từ 3)" },
    { key: "key_den", label: "Dải: đến", type: "number", group: "Phân loại", hint: "vd 4" },
    { key: "bac", label: "Bậc số lượng → giá trị (tờ / %)", type: "bands", group: "Bậc số lượng" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Bậc số lượng" },
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
  softDelete: true,
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
    { key: "gsm", label: "Định lượng (g/m²)", type: "number", required: true, group: "Thông số" },
    { key: "don_vi_gia", label: "ĐVT", type: "select", group: "Thông số", options: mapOpt(DV_GIA_GIAY) },
    { key: "kho_rong", label: "Khổ rộng (mm)", type: "number", group: "Thông số", hint: "0 = cuộn / khổ mở" },
    { key: "kho_dai", label: "Khổ dài (mm)", type: "number", group: "Thông số", hint: "0 = cuộn / khổ mở" },
    { key: "kho_tinh_gia", label: "Khổ dùng để tính giá?", type: "checkbox", group: "Giá" },
    { key: "gia_thi_truong", label: "Giá thị trường (đ)", type: "number", group: "Giá", hint: "tham khảo; đơn giá bán quản ở Lịch sử giá" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
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
  ],
  fields: [
    { key: "chung_loai_giay_id", label: "Chủng loại giấy", type: "ref", required: true,
      refPrefix: "/api/vat-lieu-kho/chung-loai-giay", group: "Phân loại" },
    { key: "rong", label: "Khổ rộng (cm)", type: "number", required: true, group: "Khổ" },
    { key: "dai", label: "Khổ dài (cm)", type: "number", group: "Khổ",
      hint: "Bỏ trống = giấy cuộn / khổ mở (cắt tự do chiều dài)" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Khổ" },
  ],
};

export const REBUILD_CONFIGS: Record<string, CatalogConfig> = {
  "loai-san-pham": CFG_LOAI_SAN_PHAM,
  "may-thiet-bi": CFG_MAY,
  "cong-doan": CFG_CONG_DOAN,
  "bu-hao": CFG_BU_HAO,
  "chung-loai-giay": CFG_CHUNG_LOAI_GIAY,
  "giay": CFG_GIAY,
  "kho-giay-chuan": CFG_KHO_GIAY_CHUAN,
  "vat-tu-in-an": CFG_VAT_TU,
};
