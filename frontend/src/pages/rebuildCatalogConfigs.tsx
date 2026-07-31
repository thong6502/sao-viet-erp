// Config 6 danh mục rebuild cho RebuildCatalogPage. Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id),
// `default` (prefill khi tạo), `jsonKey` (lưu lồng vào fields_theo_loai).
// Enum hiển thị bằng thuật ngữ in ấn thuần Việt — dùng chung 1 bảng nhãn cho cả dropdown lẫn cột.
import type { CatalogConfig } from "./RebuildCatalogPage";
import { QuyDoiCuaDonVi } from "./QuyDoiCuaDonVi";

// ── Bảng nhãn thuần Việt (in ấn) — 1 nguồn cho options + column render ──────────
type Lbls = Record<string, string>;
const mapOpt = (m: Lbls) => Object.entries(m).map(([value, label]) => ({ value, label }));
const lbl = (m: Lbls) => (v: unknown) => (v == null || v === "" ? "—" : (m[String(v)] ?? String(v)));

export const STRUCTURAL: Lbls = { flat: "Tờ phẳng", multipage: "Nhiều trang", box: "Hộp", label: "Tem / nhãn" };
export const BOX_SUB: Lbls = { folding_carton: "Hộp giấy gấp", corrugated: "Thùng carton sóng", rigid: "Hộp cứng" };
export const COVER: Lbls = { tu_bia: "Bìa tự thân (cùng ruột)", bia_roi: "Bìa rời (giấy khác)" };
export const BINDING: Lbls = { ghim: "Đóng ghim", keo: "Vào keo", khau: "Khâu chỉ" };

const NHOM_CD: Lbls = { prepress: "Chế bản", print: "In", finishing: "Gia công sau in", other: "Dịch vụ khác" };

// Đơn vị đếm của công đoạn. Dòng giấy chảy MỘT CHIỀU qua ba đơn vị, đổi ở hai chỗ:
//   tờ nguyên ──(xả)──▶ tờ in ──(bế/xén)──▶ tờ thành phẩm
// Hệ số quy đổi KHÔNG khai ở đây — phiếu tính giá đã có con/tờ và số mảnh xả.
// Ba mức của DÒNG GIẤY — hết. Bước không chạm giấy (chế bản) thì để TRỐNG ô đơn vị, chứ không
// đẻ thêm lựa chọn cho nó: trống = "không nằm trên dòng giấy", engine bỏ qua khi tính bù hao.
const DON_VI_CD: Lbls = {
  to_nguyen: "Tờ nguyên (giấy to)",
  to: "Tờ in",
  cai: "Tờ thành phẩm (con)",
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
    // Hiện ngay trên list để nhìn ra máy nào CHƯA khai tốc độ — không phải bấm vào từng cái.
    // Máy chưa có số thì lệnh sản xuất bỏ trống thời gian chạy, Gantt sau này vẽ thanh rỗng.
    { key: "toc_do", label: "Tốc độ",
      render: (r) => (r.toc_do ? `${Number(r.toc_do).toLocaleString("vi-VN")} tờ/giờ` : "—") },
  ],
  // Lọc theo Nhóm máy. `dynamic` vì ô này gõ TỰ DO: nhóm chủ xưởng tự đặt vẫn có tab riêng,
  // không bị rơi ra ngoài như khi khai cứng 5 giá trị gợi ý.
  facet: {
    key: "loai_may",
    values: [
      { value: "Máy in", label: "Máy in" },
      { value: "In ngoài", label: "In ngoài" },
      { value: "Cán màng / UV", label: "Cán màng / UV" },
      { value: "Bồi", label: "Bồi" },
      { value: "Bế", label: "Bế" },
    ],
    dynamic: true,
  },
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
    // ── Chừa trên TỜ GIẤY (khác nhíp kẽm ở trên) → engine tính giá trừ khi bình bài ────────────
    { key: "nhip_giay_mm", label: "Nhíp giấy (mm)", type: "number", group: "Chừa tờ in",
      showIf: (f) => isMayIn(f.loai_may),
      hint: "Cạnh máy KẸP TỜ GIẤY, thường 8–12 mm. KHÁC nhíp kẽm (~44mm) ở trên — trừ vào chiều DÀI tờ in" },
    { key: "le_hong_mm", label: "Lề hông (mm)", type: "number", group: "Chừa tờ in",
      showIf: (f) => isMayIn(f.loai_may),
      hint: "Trừ MỖI BÊN chiều rộng tờ in" },
    { key: "duoi_thang_mau_mm", label: "Đuôi + thanh màu (mm)", type: "number", group: "Chừa tờ in",
      showIf: (f) => isMayIn(f.loai_may),
      hint: "Cuối tờ, trừ vào chiều DÀI" },
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
    // ── Tốc độ & thời gian → nuôi thẳng thời lượng bước ở Lệnh sản xuất ───────
    { key: "toc_do", label: "Tốc độ chạy (tờ/giờ)", type: "number", group: "Tốc độ & thời gian",
      hint: "Tính theo LƯỢT qua máy — in 2 mặt thì mỗi tờ chạy 2 lượt. Bỏ trống thì lệnh sản xuất để trống thời gian chạy." },
    { key: "thoi_gian_rua_muc", label: "Thời gian rửa mực (phút)", type: "number", group: "Tốc độ & thời gian",
      showIf: (f) => isMayIn(f.loai_may),
      hint: "Vệ sinh máy sau khi in xong — cộng vào thời gian chiếm máy" },
    // ── Ghi chú ────────────────────────────────────────────────────────────────
    { key: "ghi_chu", label: "Ghi chú 1", type: "text", group: "Ghi chú" },
    { key: "ghi_chu_2", label: "Ghi chú 2", type: "text", group: "Ghi chú" },
  ],
  // Xưởng CHỈ in offset tờ → không có ô chọn đơn vị tốc độ, hệ tự ghi `to_gio`. Bày dropdown 5 lựa
  // chọn (m²/cuộn/mét…) chỉ tạo cơ hội chọn nhầm rồi thắc mắc sao lệnh SX vẫn trống năng suất.
  transformSubmit: (body) => ({
    ...body,
    don_vi_toc_do: body.toc_do ? "to_gio" : null,
  }),
};

export const CFG_CONG_DOAN: CatalogConfig = {
  title: "Công đoạn",
  subtitle: "",
  showCount: false,
  prefix: "/api/cong-doan",
  facet: { key: "nhom", values: mapOpt(NHOM_CD) },
  columns: [
    { key: "nhom", label: "Giai đoạn", render: (r) => lbl(NHOM_CD)(r.nhom) },
    // Nhìn ra ngay bước nào ĐỔI ĐƠN VỊ, và bước nào để trống (không nằm trên dòng giấy).
    { key: "don_vi_vao", label: "Đơn vị", render: (r) =>
        `${lbl(DON_VI_CD)(r.don_vi_vao)} → ${lbl(DON_VI_CD)(r.don_vi_ra)}` },
    { key: "kieu_bu_hao", label: "Bù hao", render: (r) =>
        r.kieu_bu_hao === "co_dinh" ? `Cố định ${r.so_to_bu_hao ?? 50} tờ` : lbl(KIEU_BU_HAO)(r.kieu_bu_hao ?? "khong") },
    // Nhìn ra công đoạn nào chưa khai số cho Lệnh sản xuất (giống cột Tốc độ bên màn Máy).
    { key: "setup_time", label: "Chuẩn bị",
      render: (r) => (Number(r.setup_time) > 0 ? `${Number(r.setup_time)} phút` : "—") },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "—") },
  ],
  fields: [
    { key: "nhom", label: "Giai đoạn", type: "select", required: true, group: "Thông tin", options: mapOpt(NHOM_CD) },
    { key: "department_id", label: "Phòng ban / Tổ phụ trách", type: "ref", refPrefix: "/api/cong-doan/phong-ban", group: "Thông tin",
      hint: "Tổ/bộ phận sẽ nhận việc công đoạn này khi phát lệnh sản xuất" },

    // ── Số nuôi thẳng thời lượng bước ở Lệnh sản xuất (giá trị MẶC ĐỊNH, kế hoạch sửa được) ────
    { key: "setup_time", label: "Thời gian chuẩn bị (phút)", type: "number", group: "Lệnh sản xuất",
      hint: "Canh máy trước khi chạy — tính MỘT LẦN cho cả lệnh, không nhân theo số lượng" },
    { key: "may_id", label: "Máy mặc định", type: "ref", refPrefix: "/api/may-thiet-bi", group: "Lệnh sản xuất",
      hint: "Bung lệnh là tự gán máy này. Bỏ trống thì bước in vẫn lấy máy đã chọn ở phiếu tính giá." },
    { key: "nang_suat", label: "Năng suất mỗi giờ", type: "number", group: "Lệnh sản xuất",
      hint: "Đơn vị đi theo đầu vào của bước: chế bản = kẽm/giờ · in, cán, bế = tờ/giờ · dán, đóng gói = con/giờ. Bước có máy thì lấy tốc độ máy — ô này dành cho việc LÀM TAY." },

    // CHỈ TÍNH THEO CÔNG THỨC: đã bỏ ô 'Cách tính giá' / 'Đơn giá' / 'Bậc kích thước'.
    // Đơn giá nhập per-phiếu (mỗi dòng phiếu tính giá tự mang don_gia); công đoạn chỉ khai CÔNG THỨC.
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá" },
    // ── Đơn vị đứng TRƯỚC Bù hao: nó quyết định bù hao được tra theo số gì (tờ hay con) ────────
    { key: "don_vi_vao", label: "Đơn vị đầu vào", type: "select", group: "Đơn vị",
      options: mapOpt(DON_VI_CD), default: "to",
      hint: "Bước này NHẬN VÀO cái gì. Bù hao khai ở dưới cũng tính theo đơn vị này. Để TRỐNG nếu bước không chạm giấy (chế bản) — engine sẽ bỏ nó khỏi dòng giấy." },
    { key: "don_vi_ra", label: "Đơn vị đầu ra", type: "select", group: "Đơn vị",
      options: mapOpt(DON_VI_CD), default: "to",
      hint: "Khác đầu vào = bước ĐỔI ĐƠN VỊ (bế: tờ in → tờ thành phẩm · xả giấy: tờ nguyên → tờ in). Hệ số quy đổi lấy từ phiếu tính giá (con/tờ, số mảnh xả) — không khai ở đây." },
    { key: "kieu_bu_hao", label: "Bù hao", type: "select", group: "Bù hao", options: mapOpt(KIEU_BU_HAO), default: "khong" },
    { key: "bu_hao_id", label: "Mã bù hao (gõ để tìm)", type: "ref-search", refPrefix: "/api/bu-hao", group: "Bù hao",
      showIf: (f) => f.kieu_bu_hao === "tra_bang",
      hint: "Gõ mã / tên bù hao để tìm (vd 3-4 → In 3-4 màu) — engine tra bậc theo số lượng" },
    { key: "so_to_bu_hao", label: "Số tờ cộng cố định", type: "number", group: "Bù hao", default: 50,
      showIf: (f) => f.kieu_bu_hao === "co_dinh",
      hint: "Mặc định 50; bế nổi / dán móc đáy = 30" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Thông tin" },
  ],
  // CHỈ TÍNH THEO CÔNG THỨC: công đoạn luôn ở chế độ sản lượng + basis 'per_other' (giá phẳng/công
  // thức) để backend không chặn E-CD-BASIS. Dọn run_rate/size_tiers (đơn giá nay nhập per-phiếu).
  transformSubmit: (body) => {
    body.che_do_tinh = "theo_san_luong";
    body.pricing_basis = "per_other";
    body.run_rate = null;
    body.size_tiers = [];
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
  subtitle: "Từng loại giấy cụ thể — thuộc 1 Chủng loại giấy. Khai định lượng + đơn giá theo cân (đ/kg); khổ giấy nhập ở phiếu tính giá.",
  prefix: "/api/vat-lieu-kho/giay",
  softDelete: true,
  hasVersions: false,
  facet: KHO_FACET,
  columns: [
    { key: "gsm", label: "Định lượng", render: (r) => `${r.gsm} g/m²` },
    { key: "don_vi_gia", label: "ĐVT", render: (r) => lbl(DV_GIA_GIAY)(r.don_vi_gia) },
    { key: "don_gia", label: "Đơn giá (đ/kg)", render: (r) => (Number(r.don_gia) ? Number(r.don_gia).toLocaleString("vi-VN") : "—") },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "—") },
  ],
  fields: [
    { key: "chung_loai_giay_id", label: "Chủng loại giấy", type: "ref", required: true,
      refPrefix: "/api/vat-lieu-kho/chung-loai-giay", group: "Phân loại" },
    { key: "gsm", label: "Định lượng (g/m²)", type: "number", required: true, group: "Thông số" },
    { key: "don_vi_gia", label: "ĐVT", type: "select", group: "Thông số", options: mapOpt(DV_GIA_GIAY), default: "kg" },
    // Đơn giá theo cân — CHỐT CỨNG ở danh mục (engine lấy thẳng, phiếu không sửa).
    { key: "don_gia", label: "Đơn giá (đ/kg)", type: "number", group: "Giá", hint: "Đơn giá theo ĐVT đã chọn (mặc định đ/kg)" },
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
  ],
};

export const CFG_VAT_TU: CatalogConfig = {
  title: "Vật tư in ấn",
  subtitle: "Mực, bản kẽm, hoá chất, màng, keo… — mã · tên · ĐVT · công thức · ghi chú.",
  prefix: "/api/vat-lieu-kho/vat-tu-in-an",
  columns: [
    { key: "don_vi_gia", label: "ĐVT", render: (r) => lbl(DV_GIA_VAT_TU)(r.don_vi_gia) },
    { key: "don_gia", label: "Đơn giá", render: (r) => (Number(r.don_gia) ? Number(r.don_gia).toLocaleString("vi-VN") : "—") },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "—") },
  ],
  fields: [
    { key: "don_vi_gia", label: "Đơn vị tính (ĐVT)", type: "select", group: "Giá", options: mapOpt(DV_GIA_VAT_TU) },
    // Đơn giá chốt ở danh mục — engine phơi thành biến `don_gia` (+ don_gia_kg/m²) cho công thức vật tư.
    { key: "don_gia", label: "Đơn giá", type: "number", group: "Giá", hint: "Đơn giá theo ĐVT đã chọn — dùng làm biến don_gia trong công thức" },
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Giá" },
  ],
};

// Khai báo kho — master data NHẸ (chỉ tên / vị trí / ghi chú). Kho tạo ở đây tự đổ
// ra navbar (mục "Kho hàng"). Mã KHO-xxxx tự gợi ý (suggestNextCode). Xóa mềm để giữ dấu vết.
export const CFG_KHO_HANG: CatalogConfig = {
  title: "Kho hàng",
  subtitle: "Khai báo kho (tên · vị trí · ghi chú). Kho tạo ở đây tự hiện dưới mục “Kho hàng” trên thanh điều hướng.",
  prefix: "/api/kho",
  softDelete: true,
  autoCode: true,          // mã KHO-#### sinh ngầm ở backend, ẩn ô nhập mã
  columns: [
    { key: "vi_tri", label: "Vị trí", render: (r) => (r.vi_tri ? String(r.vi_tri) : "—") },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "—") },
  ],
  fields: [
    { key: "vi_tri", label: "Vị trí kho", type: "text", group: "Thông tin",
      hint: "Nơi đặt kho, vd: Tầng 1 — xưởng A" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Thông tin" },
  ],
};

// Tình trạng khuôn bế — record-only (con người phán, máy chỉ ghi nhận).
export const TINH_TRANG_KHUON: Lbls = { dang_dung: "Đang dùng", hong: "Hỏng", thanh_ly: "Thanh lý" };

// Ngày ISO (yyyy-mm-dd) → dd/mm/yyyy để đọc; rỗng → "—".
const fmtDate = (v: unknown): string => {
  const s = String(v ?? "").slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "—";
};

// Khai báo KHUÔN BẾ — master data NHẸ, khai TAY. Mỗi khuôn làm riêng cho hình bế của 1
// ấn phẩm; đơn lặp lại thì lôi khuôn cũ ra dùng. Chỉ đủ để TÌM LẠI: số kệ (vị trí lưu) +
// tình trạng. Ref ấn phẩm/khách hàng đấu sau. Mã KB-#### tự sinh; xóa mềm giữ dấu vết.
export const CFG_KHUON_BE: CatalogConfig = {
  title: "Khuôn bế",
  subtitle: "Khai báo nơi lưu trữ khuôn bế (số kệ · ngày làm · tình trạng). Mỗi khuôn làm riêng cho 1 ấn phẩm — đơn lặp lại lôi khuôn cũ ra dùng.",
  prefix: "/api/khuon-be",
  softDelete: true,
  autoCode: true,          // mã KB-#### sinh ngầm ở backend, ẩn ô nhập mã
  facet: { key: "tinh_trang", values: mapOpt(TINH_TRANG_KHUON) },
  columns: [
    { key: "khach_hang", label: "Khách hàng", render: (r) => (r.khach_hang ? String(r.khach_hang) : "—") },
    { key: "so_ke", label: "Số kệ", render: (r) => (r.so_ke ? String(r.so_ke) : "—") },
    { key: "ngay_lam_khuon", label: "Ngày làm", render: (r) => fmtDate(r.ngay_lam_khuon) },
    { key: "tinh_trang", label: "Tình trạng", render: (r) => lbl(TINH_TRANG_KHUON)(r.tinh_trang) },
  ],
  fields: [
    { key: "khach_hang", label: "Khách hàng", type: "text", group: "Thông tin",
      hint: "Khai tay tên khách; nối danh mục khách hàng ở bản sau" },
    { key: "so_ke", label: "Số kệ / vị trí lưu", type: "text", group: "Lưu trữ",
      hint: "Nơi cất khuôn, vd: Kệ B3 — xưởng sau in" },
    { key: "ngay_lam_khuon", label: "Ngày làm khuôn", type: "date", group: "Lưu trữ" },
    { key: "tinh_trang", label: "Tình trạng", type: "select", group: "Lưu trữ",
      options: mapOpt(TINH_TRANG_KHUON), default: "dang_dung" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Lưu trữ" },
  ],
};

// ── Đơn vị & quy đổi ─────────────────────────────────────────────────────────────
// Ba bước, không hơn: tạo đơn vị A, tạo đơn vị B, khai "1 A = n B". Mọi khái niệm khác (loại đo,
// đơn vị chuẩn, ngày hiệu lực) là chuyện nội bộ — không phơi ra màn khai.
export const CFG_DON_VI: CatalogConfig = {
  title: "Đơn vị & quy đổi",
  prefix: "/api/don-vi",
  softDelete: true,
  // Tạo xong giữ drawer mở để khai quy đổi ngay — khối quy đổi phải có id mới gắn vào được.
  moLaiSauKhiTao: true,
  columns: [
    {
      key: "quy_doi_text",
      label: "Quy đổi",
      render: (r) => {
        const raw = r.quy_doi_text ? String(r.quy_doi_text).trim() : "";
        if (!raw || raw === "Chưa khai quy đổi") {
          return <span className="rc__chip-muted">Chưa khai báo</span>;
        }
        const parts = raw.split(" · ").map((p) => p.trim()).filter(Boolean);
        return (
          <div className="rc__formula-chips">
            {parts.map((p, i) => {
              const isDynamic = p.includes("dinh_luong") || p.includes("dai") || p.includes("rong") || p.includes("so_con") || p.includes("×");
              return (
                <span key={i} className={`rc__formula-pill ${isDynamic ? "rc__formula-pill--dynamic" : ""}`}>
                  {p}
                </span>
              );
            })}
          </div>
        );
      },
    },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "—") },
  ],
  fields: [
    { key: "ghi_chu", label: "Ghi chú", type: "text" },
  ],
  // Quy đổi khai NGAY TẠI ĐÂY, dưới ô Ghi chú — một chỗ nhập, không màn thứ hai.
  renderExtra: (_form, existing) => <QuyDoiCuaDonVi donVi={existing} />,
};

export const REBUILD_CONFIGS: Record<string, CatalogConfig> = {
  "loai-san-pham": CFG_LOAI_SAN_PHAM,
  "khai-bao-kho": CFG_KHO_HANG,
  "may-thiet-bi": CFG_MAY,
  "cong-doan": CFG_CONG_DOAN,
  "bu-hao": CFG_BU_HAO,
  "don-vi": CFG_DON_VI,
  "chung-loai-giay": CFG_CHUNG_LOAI_GIAY,
  "giay": CFG_GIAY,
  "vat-tu-in-an": CFG_VAT_TU,
  "khuon-be": CFG_KHUON_BE,
};
