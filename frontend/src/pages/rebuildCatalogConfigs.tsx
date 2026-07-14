// Config 6 danh mục rebuild cho RebuildCatalogPage. Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id),
// `default` (prefill khi tạo), `jsonKey` (lưu lồng vào fields_theo_loai).
// Enum hiển thị bằng thuật ngữ in ấn thuần Việt — dùng chung 1 bảng nhãn cho cả dropdown lẫn cột.
import type { CatalogConfig } from "./RebuildCatalogPage";

// ── Bảng nhãn thuần Việt (in ấn) — 1 nguồn cho options + column render ──────────
type Lbls = Record<string, string>;
const mapOpt = (m: Lbls) => Object.entries(m).map(([value, label]) => ({ value, label }));
const lbl = (m: Lbls) => (v: unknown) => (v == null || v === "" ? "—" : (m[String(v)] ?? String(v)));

export const STRUCTURAL: Lbls = { flat: "Tờ phẳng", multipage: "Nhiều trang", box: "Hộp", label: "Tem / nhãn" };
export const BOX_SUB: Lbls = { folding_carton: "Hộp giấy gấp", corrugated: "Thùng carton sóng", rigid: "Hộp cứng" };
export const COVER: Lbls = { tu_bia: "Bìa tự thân (cùng ruột)", bia_roi: "Bìa rời (giấy khác)" };
export const BINDING: Lbls = { ghim: "Đóng ghim", keo: "Vào keo", khau: "Khâu chỉ" };

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
  per_job: "Trọn gói một lần (cả đơn)",
  per_other: "Khác",
};
// Cách công đoạn góp bù hao — trỏ 1 mã bù hao (tra bảng theo SL), hoặc cộng cố định.
const KIEU_BU_HAO: Lbls = {
  khong: "Không bù hao",
  tra_bang: "Tra bảng theo mã bù hao",
  co_dinh: "Cộng cố định (số tờ)",
};

const THO: Lbls = { canh_dai: "Thớ dọc (canh dài)", canh_ngan: "Thớ ngang (canh ngắn)" };
const DV_GIA_GIAY: Lbls = { kg: "KG", cai: "CÁI", ram: "Ram", to: "Tờ", tan: "Tấn" };
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
  columns: [],
  fields: [
    { key: "routing_template", label: "Chuỗi công đoạn mặc định", type: "ref-multi", refPrefix: "/api/cong-doan",
      group: "Công đoạn mặc định", hint: "Các bước sản xuất, theo đúng thứ tự chạy" },
  ],
  deriveInitial: (existing) => ({
    structural_type: existing?.structural_type ?? "flat",
    box_sub_type: existing?.box_sub_type ?? "",
    has_cover: existing?.has_cover ?? false,
    cover_type: existing?.cover_type ?? "",
    default_binding: existing?.default_binding ?? "",
  }),
  transformSubmit: (body, form) => ({
    ...body,
    structural_type: form.structural_type ?? "flat",
    box_sub_type: form.box_sub_type || null,
    has_cover: form.has_cover || false,
    cover_type: form.cover_type || null,
    default_binding: form.default_binding || null,
  }),
};

const isMayIn = (val: unknown) => {
  const s = String(val || "").trim().toLowerCase();
  return s === "máy in" || s === "in ngoài" || s.startsWith("in ") || s.includes("máy in") || s.includes("in offset");
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
    // ── Nhóm máy (chữ gợi ý + tự do) ──────────────────────────────────────────
    { key: "loai_may", label: "Nhóm máy", type: "suggest", required: true, group: "Phân loại",
      options: [
        { value: "Máy in", label: "Máy in" },
        { value: "In ngoài", label: "In ngoài" },
        { value: "Cán màng / UV", label: "Cán màng / UV" },
        { value: "Bồi", label: "Bồi" },
        { value: "Bế", label: "Bế" },
      ],
      hint: "Gợi ý hoặc gõ tự do: Máy in, Cán màng / UV, Bồi, Bế…" },
    // ── Khổ kẽm + nhíp kẽm ─────────────────────────────────────────────────────
    { key: "kho_kem_rong", label: "Khổ kẽm — rộng (mm)", type: "number", group: "Khổ kẽm & vùng in",
      showIf: (f) => isMayIn(f.loai_may),
      hint: "Bản kẽm máy nhận, vd 800*1030 (rộng*dài)" },
    { key: "kho_kem_dai", label: "Khổ kẽm — dài (mm)", type: "number", group: "Khổ kẽm & vùng in",
      showIf: (f) => isMayIn(f.loai_may) },
    { key: "gripper_mm", label: "Nhíp kẽm (mm)", type: "number", group: "Khổ kẽm & vùng in",
      showIf: (f) => isMayIn(f.loai_may),
      hint: "Mép nhíp trên kẽm, vd 44 mm" },
    // ── Vùng in lớn nhất ───────────────────────────────────────────────────────
    { key: "vung_in_rong", label: "Vùng in max — rộng (mm)", type: "number", group: "Khổ kẽm & vùng in",
      showIf: (f) => isMayIn(f.loai_may),
      hint: "Vùng in được lớn nhất, vd 710*1010 (rộng*dài)" },
    { key: "vung_in_dai", label: "Vùng in max — dài (mm)", type: "number", group: "Khổ kẽm & vùng in",
      showIf: (f) => isMayIn(f.loai_may) },
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
    { key: "ten_hien_thi", label: "Tên hiển thị cho sản xuất", type: "text", group: "Thông tin" },
    { key: "nhom", label: "Giai đoạn", type: "select", required: true, group: "Thông tin", options: mapOpt(NHOM_CD) },

    // run_rate — 2 biến thể cùng key: đa số là 'đơn giá / đơn vị', riêng trọn gói là 'tổng tiền'.
    { key: "run_rate", label: "Đơn giá / đơn vị (đ)", type: "number", group: "Giá",
      showIf: (f) => ["sheet", "piece_flat", "area_sides", "position"].includes(String(f._method)),
      hint: "Đơn giá cho 1 đơn vị theo cách tính đã chọn ở trên." },
    { key: "run_rate", label: "Tổng tiền cả đơn (đ)", type: "number", group: "Giá",
      showIf: (f) => f._method === "job",
      hint: "Cả đơn tính 1 lần, máy tự chia ÷ SL. VD khuôn bế 800.000 ÷ 4.000 = 200đ/sp." },
    { key: "size_tiers", label: "Bậc đơn giá theo kích thước", type: "size_tiers", group: "Giá",
      showIf: (f) => f._method === "piece_size",
      hint: "Đơn giá theo cạnh dài thành phẩm (cm). VD dán hộp: ≤20cm=100 · ≤40cm=200 · ≤100cm=800." },

    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá" },
    { key: "kieu_bu_hao", label: "Bù hao", type: "select", group: "Bù hao", options: mapOpt(KIEU_BU_HAO), default: "khong" },
    { key: "bu_hao_id", label: "Mã bù hao (gõ để tìm)", type: "ref-search", refPrefix: "/api/bu-hao", group: "Bù hao",
      showIf: (f) => f.kieu_bu_hao === "tra_bang",
      hint: "Gõ mã / tên bù hao để tìm (vd 3-4 → In 3-4 màu) — engine tra bậc theo số lượng" },
    { key: "so_to_bu_hao", label: "Số tờ cộng cố định", type: "number", group: "Bù hao", default: 50,
      showIf: (f) => f.kieu_bu_hao === "co_dinh",
      hint: "Mặc định 50; bế nổi / dán móc đáy = 30" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Bù hao" },
  ],
  // Suy "Cách tính giá" (_method) từ dữ liệu đã lưu khi mở form sửa. Chỉ 6 cách; kiểu khác → "—".
  deriveInitial: (existing) => {
    if (!existing) return { _method: "sheet" };
    if (existing.che_do_tinh === "theo_gio") return { _method: "" };  // theo giờ đã bỏ khỏi lựa chọn
    const pb = existing.pricing_basis;
    const st = existing.size_tiers;
    const hasSt = Array.isArray(st) && st.length > 0;
    if (pb === "per_sheet") return { _method: "sheet" };
    if (pb === "per_finished_qty") return { _method: hasSt ? "piece_size" : "piece_flat" };
    if (pb === "per_job") return { _method: "job" };
    if (pb === "per_area_sides") return { _method: "area_sides" };
    if (pb === "per_position") return { _method: "position" };
    return { _method: "" };  // basis khác/rỗng → để trống, người dùng chọn lại
  },
  // Map "Cách tính giá" → pricing_basis + dọn ô không dùng. m="" (bản cũ chưa chọn) → không đụng gì.
  transformSubmit: (body, form) => {
    const m = form._method;
    delete body._method;
    const sl = (pb: string) => { body.che_do_tinh = "theo_san_luong"; body.pricing_basis = pb; };
    if (m === "sheet") { sl("per_sheet"); body.size_tiers = []; }
    else if (m === "piece_flat") { sl("per_finished_qty"); body.size_tiers = []; }
    else if (m === "piece_size") { sl("per_finished_qty"); body.run_rate = null; }
    else if (m === "job") { sl("per_job"); body.size_tiers = []; }
    else if (m === "area_sides") { sl("per_area_sides"); body.size_tiers = []; }
    else if (m === "position") { sl("per_position"); body.size_tiers = []; }
    // m === "" : giữ nguyên dữ liệu cũ (không map, không xóa) → bản theo_gio cũ an toàn.
    return body;
  },
};

export const CFG_BU_HAO: CatalogConfig = {
  title: "Bù hao",
  subtitle: "Mỗi mã bù hao = danh sách bậc số lượng → số tờ / %. Công đoạn trỏ mã bù hao để tra bậc theo SL.",
  prefix: "/api/bu-hao",
  columns: [
    { key: "bac", label: "Số bậc", render: (r) => `${Array.isArray(r.bac) ? r.bac.length : 0} bậc` },
  ],
  fields: [
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
  subtitle: "Từng loại giấy cụ thể (khổ mua) — thuộc 1 Chủng loại giấy. Đơn giá nhập ở “Lịch sử giá”.",
  prefix: "/api/vat-lieu-kho/giay",
  softDelete: true,
  hasVersions: true,
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
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá" },
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
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá" },
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
