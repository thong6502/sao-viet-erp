// Config 6 danh mục rebuild cho RebuildCatalogPage. Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id),
// `default` (prefill khi tạo), `jsonKey` (lưu lồng vào fields_theo_loai).
// Enum hiển thị bằng thuật ngữ in ấn thuần Việt — dùng chung 1 bảng nhãn cho cả dropdown lẫn cột.
import { useEffect, useState } from "react";
import type { CatalogConfig, ColumnDef } from "./RebuildCatalogPage";
import type { Row } from "../api/rebuildCatalog";
import { authed } from "../api/client";
import { useAuth } from "../auth/useAuth";

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
    { key: "routing_template", label: "Chuỗi công đoạn mặc định", type: "ref-multi", refPrefix: "/api/cong-doan",
      group: "Công đoạn mặc định", hint: "Các bước sản xuất, theo đúng thứ tự chạy" },
  ],
};

// ── Máy: nhãn phụ + điều kiện hiện field theo loại máy ──────────────────────────
const DON_VI_TOC_DO: Lbls = {
  to_gio: "tờ/giờ", m2_gio: "m²/giờ", cuon_gio: "cuộn/giờ", luot_gio: "lượt/giờ", met_gio: "mét/giờ",
};
const FINISHING_SUB: Lbls = {
  guillotine: "Máy xén", buckle_folder: "Máy gấp (buckle)", knife_folder: "Máy gấp dao",
  saddle_stitcher: "Đóng ghim yên ngựa", perfect_binder: "Vào keo", wireo: "Lò xo (wire-o)",
  laminator: "Cán màng", die_cutter: "Máy bế", foil_press: "Ép nhũ", uv_coater: "Phủ UV",
};
const NGUON_BHR: Lbls = {
  nhap_truc_tiep: "Gõ thẳng đơn giá giờ (đã biết sẵn)",
  dung_tu_von: "Để hệ thống tính từ vốn & chi phí",
};
const DV_GIA_NGOAI: Lbls = { per_to: "đ / tờ", per_m2: "đ / m²", per_sp: "đ / sản phẩm" };
const CONG_NGHE_DIG: Lbls = { toner: "Toner (tính theo click)", inkjet_production: "Inkjet (tính theo mực/m²)" };

type F = Record<string, unknown>;
const isOffsetSheet = (f: F) => f.loai_may === "press_offset_sheet";
const isPress = (f: F) => String(f.loai_may ?? "").startsWith("press_") || f.loai_may === "wide_format";
const isThueNgoai = (f: F) => f.loai_may === "thue_ngoai";
const coChiPhiGio = (f: F) => !isThueNgoai(f);       // thuê ngoài = cost center ảo, không có BHR
const bhrTuVon = (f: F) => coChiPhiGio(f) && (f.nguon_bhr ?? "dung_tu_von") !== "nhap_truc_tiep";
const coUnits = (f: F) =>
  ["press_offset_sheet", "press_offset_web", "press_flexo_label"].includes(String(f.loai_may));

// ── Preview BHR sống trong drawer (gọi POST /bhr-preview, debounce) ─────────────
function BhrPreview({ form }: { form: Record<string, unknown> }) {
  const { token } = useAuth();
  const [res, setRes] = useState<{ BHR: number; don_gia_ban_gio: number; breakdown: Record<string, number> } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const depKey = JSON.stringify(form);
  useEffect(() => {
    if (!token || isThueNgoai(form) || !form.loai_may) { setRes(null); setMsg(null); return; }
    const t = setTimeout(() => {
      authed<{ BHR: number; don_gia_ban_gio: number; breakdown: Record<string, number> }>(
        "/api/may-thiet-bi/bhr-preview", token,
        { method: "POST", body: JSON.stringify(form) },
      )
        .then((r) => { setRes(r); setMsg(null); })
        .catch((e) => { setRes(null); setMsg(e instanceof Error ? e.message : "Không tính được."); });
    }, 600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, depKey]);
  if (isThueNgoai(form) || !form.loai_may) return null;
  return (
    <section className="rc-sec" style={{ marginTop: "var(--sp-4)" }}>
      <div className="rc-sec__title">Đơn giá giờ máy (BHR) — xem trước</div>
      {msg ? (
        <span className="rc-field__hint">{msg}</span>
      ) : res ? (
        <div>
          <strong style={{ fontSize: "15px" }}>≈ {vnd(res.BHR)} đ/giờ</strong>
          {res.don_gia_ban_gio > res.BHR && (
            <span className="rc-field__hint" style={{ marginLeft: "8px" }}>
              · giá bán giờ (đã markup): {vnd(res.don_gia_ban_gio)} đ/giờ
            </span>
          )}
          <div className="rc-field__hint" style={{ marginTop: "4px" }}>
            {Object.entries(res.breakdown).filter(([, v]) => v > 0)
              .map(([k, v]) => `${k.replace(/_gio$/, "").replace(/_/g, " ")}: ${vnd(v)}`).join(" · ") || "Chưa nhập chi phí nào — BHR = 0."}
          </div>
          {res.BHR <= 0 && (
            <div className="rc-field__hint" style={{ color: "var(--signal, #8a1f1f)" }}>
              ⚠ BHR = 0 — máy này sẽ tính 0 đ tiền công khi báo giá theo giờ.
            </div>
          )}
        </div>
      ) : (
        <span className="rc-field__hint">Đang tính…</span>
      )}
    </section>
  );
}

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
  renderExtra: (form) => <BhrPreview form={form} />,
  fields: [
    // ── Nhận diện ───────────────────────────────────────────────────────────────
    { key: "loai_may", label: "Loại máy", type: "select", required: true, group: "Nhận diện",
      options: mapOpt(LOAI_MAY), hint: "Quyết định các ô bên dưới hiện ra" },
    { key: "trang_thai", label: "Trạng thái", type: "select", group: "Nhận diện",
      options: mapOpt(TRANG_THAI_MAY), default: "active", hint: "Chỉ máy Đang chạy mới được chọn khi báo giá" },
    { key: "finishing_subtype", label: "Loại máy gia công", type: "select", group: "Nhận diện",
      options: mapOpt(FINISHING_SUB), showIf: (f) => f.loai_may === "finishing" },
    { key: "hang_san_xuat", label: "Hãng sản xuất", type: "text", group: "Nhận diện",
      hint: "VD: Heidelberg, Komori, RMGT…" },
    { key: "model", label: "Model", type: "text", group: "Nhận diện" },
    { key: "khoa_class", label: "Lớp khổ (tra giá kẽm)", type: "select", group: "Nhận diện",
      options: mapOpt(KHOA_CLASS), showIf: isOffsetSheet,
      hint: "BẮT BUỘC để tính tiền kẽm — để trống thì báo giá sẽ tính kẽm 0 đ" },
    // ── Khổ & năng lực (chỉ máy in) ────────────────────────────────────────────
    { key: "kho_max_dai", label: "Khổ in max — dài (mm)", type: "number", group: "Khổ & năng lực", showIf: isPress },
    { key: "kho_max_rong", label: "Khổ in max — rộng (mm)", type: "number", group: "Khổ & năng lực", showIf: isPress },
    { key: "kho_min_dai", label: "Khổ in min — dài (mm)", type: "number", group: "Khổ & năng lực", showIf: isPress },
    { key: "kho_min_rong", label: "Khổ in min — rộng (mm)", type: "number", group: "Khổ & năng lực", showIf: isPress },
    { key: "gripper_mm", label: "Nhíp — chừa đầu (mm)", type: "number", group: "Khổ & năng lực",
      showIf: isOffsetSheet, default: 12, hint: "Mép giấy máy kẹp kéo tờ, không in được. Offset thường 10–12 mm" },
    { key: "so_units", label: "Số đơn vị in (màu)", type: "number", group: "Khổ & năng lực",
      showIf: coUnits, hint: "Máy 4 màu = 4. Quyết định số lượt in mỗi tờ" },
    { key: "toc_do", label: "Tốc độ chạy máy", type: "number", group: "Khổ & năng lực", showIf: coChiPhiGio },
    { key: "don_vi_toc_do", label: "Đơn vị tốc độ", type: "select", group: "Khổ & năng lực",
      options: mapOpt(DON_VI_TOC_DO), showIf: coChiPhiGio, default: "to_gio" },
    // ── In 2 mặt & bù hao (offset tờ rời) ──────────────────────────────────────
    { key: "cho_phep_tu_tro", label: "Cho phép tự trở", type: "checkbox", group: "In 2 mặt & bù hao",
      showIf: isOffsetSheet, default: true, hint: "In 2 mặt bằng 1 bộ kẽm (lật chồng giấy)" },
    { key: "co_tro_mat", label: "Máy trở mặt (perfector)", type: "checkbox", group: "In 2 mặt & bù hao",
      showIf: isOffsetSheet, hint: "In 2 mặt trong 1 lượt chạy" },
    { key: "units_truoc", label: "Units mặt trước", type: "number", group: "In 2 mặt & bù hao",
      showIf: (f) => isOffsetSheet(f) && !!f.co_tro_mat, hint: "Perfector 4/4 = 4 + 4" },
    { key: "units_sau", label: "Units mặt sau", type: "number", group: "In 2 mặt & bù hao",
      showIf: (f) => isOffsetSheet(f) && !!f.co_tro_mat },
    { key: "bu_hao_canh_may_per_mau", label: "Tờ canh máy mỗi màu", type: "number", group: "In 2 mặt & bù hao",
      showIf: isOffsetSheet, default: 100,
      hint: "Tờ hao để canh chỉnh mỗi màu/mặt, thường 100–150. Có CIP3 giảm còn một nửa. Để trống = 100" },
    { key: "bu_hao_chay_pct", label: "Hao khi chạy %", type: "number", group: "In 2 mặt & bù hao",
      showIf: isOffsetSheet, default: 2, hint: "% tờ hỏng trong lúc chạy sản lượng. Để trống = 2%" },
    { key: "ho_tro_cip3", label: "Có CIP3 (chốt mực tự động)", type: "checkbox", group: "In 2 mặt & bù hao",
      showIf: isOffsetSheet },
    // ── Chi phí giờ máy (BHR) — trừ thuê ngoài ─────────────────────────────────
    { key: "nguon_bhr", label: "Cách khai đơn giá giờ", type: "select", group: "Chi phí giờ máy",
      options: mapOpt(NGUON_BHR), showIf: coChiPhiGio, default: "dung_tu_von",
      hint: "Đã thuộc lòng đơn giá giờ máy? Chọn gõ thẳng cho nhanh" },
    { key: "don_gia_gio_BHR", label: "Đơn giá giờ máy (đ/giờ)", type: "number", group: "Chi phí giờ máy",
      showIf: (f) => coChiPhiGio(f) && f.nguon_bhr === "nhap_truc_tiep",
      hint: "VD máy offset 74 cũ: 500.000–900.000 đ/giờ" },
    { key: "von_dau_tu", label: "Vốn đầu tư (đ)", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon,
      hint: "Giá mua máy gồm cả lắp đặt" },
    { key: "gia_tri_thu_hoi", label: "Giá trị thu hồi (đ)", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, hint: "Bán thanh lý được bao nhiêu khi hết khấu hao — trừ khỏi khấu hao" },
    { key: "nam_khau_hao", label: "Số năm khấu hao", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, default: 8 },
    { key: "lai_von_pct", label: "Lãi vốn %/năm", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon,
      hint: "Lãi vay/chi phí vốn mua máy — máy trả góp thì đây là tiền thật, đừng bỏ trống" },
    { key: "gio_lam_nam", label: "Giờ chạy / năm", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, default: 2000, hint: "1 ca ≈ 2.000 giờ/năm; 2 ca ≈ 4.000" },
    { key: "availability_pct", label: "Tỉ lệ máy sẵn sàng %", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, default: 85, hint: "Trừ giờ hỏng + bảo trì. Không rõ để 85" },
    { key: "productivity_pct", label: "Tỉ lệ giờ có việc %", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, default: 85, hint: "Phần giờ máy thực sự chạy việc tính tiền được. Không rõ để 85" },
    { key: "luong_gio", label: "Lương / giờ 1 người (đ)", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon },
    { key: "luong_burden_pct", label: "Phụ cấp + BHXH %", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, default: 30, hint: "Cộng thêm trên lương cơ bản, thường 25–40%" },
    { key: "so_nhan_cong", label: "Số nhân công đứng máy", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, default: 1, hint: "Máy trở mặt lớn có thể 2–3 người" },
    { key: "cong_suat_kW", label: "Công suất điện (kW)", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon },
    { key: "don_gia_dien", label: "Đơn giá điện (đ/kWh)", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon },
    { key: "bao_hiem_nam", label: "Bảo hiểm máy (đ/năm)", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon },
    { key: "dien_tich_san_m2", label: "Diện tích chiếm sàn (m²)", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, hint: "Để phân bổ tiền thuê mặt bằng" },
    { key: "don_gia_thue_m2_nam", label: "Thuê mặt bằng (đ/m²/năm)", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon },
    { key: "bao_tri_gio", label: "Bảo trì (đ/giờ)", type: "number", group: "Chi phí giờ máy", showIf: bhrTuVon },
    { key: "overhead_gio", label: "Chi phí gián tiếp khác (đ/giờ)", type: "number", group: "Chi phí giờ máy",
      showIf: bhrTuVon, hint: "CHỈ phần chưa kê ở trên — đừng nhập lại điện/lương/bảo trì kẻo tính trùng" },
    { key: "markup_pct", label: "Markup giá bán giờ máy %", type: "number", group: "Chi phí giờ máy",
      showIf: coChiPhiGio, hint: "Chỉ dùng cho giá bán giờ tham khảo — LÃI báo giá nhập ở màn Tính giá, đừng nhập trùng" },
    // ── Thuê ngoài (cost center ảo) ────────────────────────────────────────────
    { key: "nha_cung_cap", label: "Nhà cung cấp", type: "text", group: "Thuê ngoài", showIf: isThueNgoai },
    { key: "don_gia", label: "Đơn giá NCC", type: "number", group: "Thuê ngoài",
      showIf: isThueNgoai, jsonKey: "fields_theo_loai" },
    { key: "don_vi_gia", label: "Tính giá theo", type: "select", group: "Thuê ngoài",
      options: mapOpt(DV_GIA_NGOAI), showIf: isThueNgoai, jsonKey: "fields_theo_loai" },
    { key: "min_charge", label: "Thu tối thiểu (đ)", type: "number", group: "Thuê ngoài",
      showIf: isThueNgoai, jsonKey: "fields_theo_loai", hint: "Sàn mỗi lần gửi gia công dù số lượng ít" },
    { key: "lead_time_ngay", label: "Thời gian trả hàng (ngày)", type: "number", group: "Thuê ngoài",
      showIf: isThueNgoai, jsonKey: "fields_theo_loai" },
    { key: "markup_ngoai_pct", label: "Markup trên giá NCC %", type: "number", group: "Thuê ngoài",
      showIf: isThueNgoai, jsonKey: "fields_theo_loai" },
    // ── Kỹ thuật số (giá click / mực) ──────────────────────────────────────────
    { key: "cong_nghe", label: "Công nghệ", type: "select", group: "Kỹ thuật số",
      options: mapOpt(CONG_NGHE_DIG), showIf: (f) => f.loai_may === "press_digital",
      jsonKey: "fields_theo_loai", default: "toner" },
    { key: "click_mono", label: "Giá click đen trắng (đ/mặt)", type: "number", group: "Kỹ thuật số",
      showIf: (f) => f.loai_may === "press_digital" && (f.cong_nghe ?? "toner") === "toner",
      jsonKey: "fields_theo_loai" },
    { key: "click_mau", label: "Giá click màu (đ/mặt)", type: "number", group: "Kỹ thuật số",
      showIf: (f) => f.loai_may === "press_digital" && (f.cong_nghe ?? "toner") === "toner",
      jsonKey: "fields_theo_loai" },
    { key: "min_click", label: "Click tối thiểu / đơn", type: "number", group: "Kỹ thuật số",
      showIf: (f) => f.loai_may === "press_digital" && (f.cong_nghe ?? "toner") === "toner",
      jsonKey: "fields_theo_loai" },
    { key: "don_gia_muc_per_m2", label: "Đơn giá mực (đ/m²)", type: "number", group: "Kỹ thuật số",
      showIf: (f) => f.loai_may === "press_digital" && f.cong_nghe === "inkjet_production",
      jsonKey: "fields_theo_loai" },
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
