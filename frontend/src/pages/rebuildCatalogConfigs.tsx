// Config 10 danh mục cho RebuildCatalogPage (xem REBUILD_CONFIGS cuối file). Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id),
// `default` (prefill khi tạo), `jsonKey` (lưu lồng vào fields_theo_loai).
// Enum hiển thị bằng thuật ngữ in ấn thuần Việt — dùng chung 1 bảng nhãn cho cả dropdown lẫn cột.
import { useEffect, useState, type ReactNode } from "react";
import type { CatalogConfig, ChuanBiKhoanRow } from "./RebuildCatalogPage";
import { ClockIcon, tongChuanBi } from "./RebuildCatalogPage";
import { nhanDonViTocDo } from "./danh-muc/fields/DonViTocDo";
import { nhanTramDai, tramOptions } from "./tenDonVi";
import { NHOM_CONG_DOAN, ngay, ngayGio } from "./keHoachSxShared";
import { QuyDoiCuaDonVi } from "./QuyDoiCuaDonVi";
import { KhoViTriPanel } from "./KhoViTriPanel";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { CodeLink } from "../components/CodeLink";
import { useCan } from "../auth/permissions";
import { useDieuHuongDanhMuc } from "./danh-muc/dieuHuong";
import { ApiError, assetUrl, authed } from "../api/client";
import { crud, trangThaiMay, type Row, type TrangThaiMay } from "../api/rebuildCatalog";

// ── Bảng nhãn thuần Việt (in ấn) — 1 nguồn cho options + column render ──────────
type Lbls = Record<string, string>;
const mapOpt = (m: Lbls) => Object.entries(m).map(([value, label]) => ({ value, label }));
const lbl = (m: Lbls) => (v: unknown) => (v == null || v === "" ? "" : (m[String(v)] ?? String(v)));


// DỜI sang `keHoachSxShared.tsx` (02/09/2026) — màn "Hồ sơ lệnh sản xuất" cần đúng bốn nhãn này
// cho ô lọc Nhóm công đoạn, mà import ngược file này thì kéo cả bộ máy 13 màn danh mục theo.
// Bí danh cục bộ giữ nguyên để 3 chỗ dùng bên dưới không phải đổi.
const NHOM_CD: Lbls = NHOM_CONG_DOAN;

// Dụng cụ DÙNG CHUNG mà bước phải mượn từ kho khuôn — khớp `cong_doan.TOOLING_TYPE` ở backend
// (service chặn giá trị ngoài danh sách). "Bản kẽm" đã gỡ 16/08/2026: kẽm là vật tư tiêu hao,
// không có dòng nào trong kho khuôn để trỏ tới — xem lý do đầy đủ ở `models/cong_doan.TOOLING_TYPE`.
const TOOLING_TYPE: Lbls = {
  khuon_be: "Khuôn bế",
  khuon_ep: "Khuôn ép kim",
  khung_lua: "Khung lụa",
};

/** Ba chip khuôn ép kim chỉ hiện ở bước khai `Loại khuôn = Khuôn ép kim`.
 *
 *  Nguồn số của chúng là ba ô Dài/Rộng/Số khuôn ở phiếu tính giá, mà phiếu CHỈ hỏi ba ô đó cho
 *  bước `khuon_ep` (đổi chủ 06/09/2026 — trước là bước khung lụa). Bày chip ở bước khuôn bế hay
 *  khung lụa là mời người ta gõ vào thứ mãi mãi bằng 0 rồi công thức ra 0đ không báo gì.
 *
 *  Ẩn CHỈ ở khâu hiển thị (xem `FormulaField`): công thức cũ lỡ dùng vẫn hợp lệ và vẫn tính y như
 *  trước, không bị gạch đỏ, không bị chặn lưu. */
const CHIP_KHUON = ["dai_khuon", "rong_khuon", "so_khuon"];
const AN_CHIP_KHUON = (form: Record<string, unknown>) =>
  form.requires_tooling && String(form.tooling_type ?? "") === "khuon_ep" ? [] : CHIP_KHUON;

// 5 CHẶNG của dòng giấy — nhãn lấy từ `/api/don-vi/tram` (hằng `models/don_vi_do.TRAM_NHAN`),
// màn này KHÔNG giữ bản sao nữa. Bảng cứng `TRAM_DONG_GIAY` từng nằm đây GỠ 09/09/2026: nó là
// bảng nhãn THỨ HAI cho cùng 5 mã, nên một bước Đóng gói hiện "Con → Thành phẩm" ở màn này mà
// "20.000 con → 20.000 cái" ở phiếu tính giá — hai màn đọc hai bảng khác nhau. Nhãn nạp cùng
// chuyến với danh mục Đơn vị (`useNapTenDonVi`, gọi ở `danh-muc/CatalogListPage`), xem `tenDonVi.ts`.
//
// Tờ giấy đổi cách đếm đúng 5 lần, chảy MỘT CHIỀU:
//   tờ nguyên ──(số mảnh xả)──▶ tờ in ──(con/tờ)──▶ con ──▶ thành phẩm
//                                     └─(gấp)────▶ tay sách ──(bắt tay/vào keo)──▶ thành phẩm
// `con` KHÁC `thành phẩm`: sách gấp tay thì nhiều tờ mới gom thành MỘT cuốn. Hệ số các cầu này
// SUY ở `_he_so_cau` từ quy cách lệnh, không khai tay.
//
// Đây là menu ĐÓNG thật: engine chạy chuỗi bù hao theo đúng 5 mức này, thêm mức thứ 6 là phải khai
// cả hệ số cầu của nó trong code — nên nó KHÔNG mở ra danh mục Đơn vị & quy đổi (nơi có kg, ram,
// thùng… của kho và mua hàng). Trước 06/09/2026 hai ô đó là picker vào danh mục, còn "chặng nào"
// thì khai gián tiếp bằng cờ `don_vi_do.tram_dong_giay`; cờ ấy đã gỡ khỏi màn Đơn vị.

/** Cặp chặng "vào → ra" cho Ô DANH SÁCH: cắt phần trong ngoặc để lọt bề ngang cột (`Tờ nguyên
 *  (giấy mua về)` → `Tờ nguyên`), nhãn đủ nằm ở `title` khi rê chuột. Mã lạ (giá trị cũ còn sót)
 *  thì hiện NGUYÊN mã, đừng nuốt — nuốt là người ta tưởng bước không chạm giấy. */
const tramNgan = (v: unknown) => {
  const s = String(v ?? "").trim();
  if (!s) return "—";
  return (nhanTramDai(s) ?? s).replace(/\s*\(.*$/, "");
};
const tramVaoRa = (vao: unknown, ra: unknown) => {
  const co = (x: unknown) => x != null && x !== "";
  if (!co(vao) && !co(ra)) return "—";
  const day = [vao, ra].map((x) => (co(x) ? (nhanTramDai(String(x)) ?? String(x)) : "—")).join(" → ");
  return <span title={day}>{`${tramNgan(vao)} → ${tramNgan(ra)}`}</span>;
};

// Cách công đoạn góp bù hao — trỏ 1 mã bù hao (tra bảng theo SL), hoặc cộng cố định.
const KIEU_BU_HAO: Lbls = {
  khong: "Không bù hao",
  tra_bang: "Tra bảng theo mã bù hao",
  co_dinh: "Cộng cố định (số tờ)",
};


// GỠ 2026-08-08: `DV_GIA_GIAY` / `DV_GIA_VAT_TU` — hai danh sách đơn vị CỨNG. Đơn vị giờ chọn từ
// danh mục Đơn vị & quy đổi (`/api/don-vi`), là NGUỒN DUY NHẤT dùng chung cho Kho · NCC · khoán ·
// tính giá. Thêm đơn vị = khai ở màn Đơn vị, không phải sửa code rồi build lại.

/** Ô ĐVT của mặt hàng gốc: gõ để tìm trong danh mục Đơn vị, lưu MÃ (`kg`, `to`…) chứ không lưu id
 *  — quy đổi làm việc trên mã. Bỏ trống = chưa chọn (bảng hiện badge "Chưa chọn đơn vị").
 *  Đơn vị đã NGỪNG DÙNG bị `locConDung` (CatalogDrawer) gạt khỏi menu — lọc ở đây bằng
 *  `active: true` thì hàng cũ đang trỏ vào đơn vị vừa ngừng mở ra thấy TRỐNG, bấm Lưu là mất mã. */
const F_DON_VI = {
  type: "ref-search-ma" as const,
  refPrefix: "/api/don-vi",
  hint: "Gõ mã / tên đơn vị để tìm…",
};

/** Chưa chọn đơn vị là trạng thái THẬT (hàng cũ có mã lạ bị xoá trắng) — phải nhìn ra ngay ở bảng,
 *  vì thiếu nó thì kho không nhập được mặt hàng đó.
 *  Hiện TÊN (`don_vi_ten` server gán) chứ không hiện mã: `kem` không ai đoán ra "bản kẽm". */
const dvCell = (r: Row) => {
  const ma = r.don_vi_gia ? String(r.don_vi_gia) : "";
  if (!ma) return <span className="badge-sem badge-sem--muted">Chưa chọn đơn vị</span>;
  return <span className="rc__formula-pill">{r.don_vi_ten ? String(r.don_vi_ten) : ma}</span>;
};


export const CFG_LOAI_SAN_PHAM: CatalogConfig = {
  title: "Loại sản phẩm",
  moduleQuyen: "dm_loai_san_pham",
  enableImport: true,
  prefix: "/api/loai-san-pham",
  nhatKyLoai: "loai_san_pham",
  // Xoá MỀM: nút "Xóa" hỏi server "còn ai dùng không" rồi tự chọn kết cục — chưa ai dùng thì
  // xoá hẳn, còn nơi dùng thì chỉ ngừng dùng. Mục đã ngừng xem lại ở công tắc trên dải lọc.
  softDelete: true,
  columns: [
    {
      key: "routing_template",
      label: "Chuỗi công đoạn mặc định",
      render: (r) => {
        const arr = (r.routing_template ?? []) as unknown[];
        if (!Array.isArray(arr) || arr.length === 0) {
          return <span style={{ color: "var(--ash, #8a8577)", fontSize: "12.5px" }}>Chưa khai báo</span>;
        }
        return (
          <div className="rc__formula-chips">
            <span className="badge-sem badge-sem--rust">
              {arr.length} bước sản xuất
            </span>
          </div>
        );
      },
    },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "routing_template", label: "Chuỗi công đoạn mặc định", type: "ref-multi", refPrefix: "/api/cong-doan",
      group: "Công đoạn mặc định", hint: "Các bước sản xuất, theo đúng thứ tự chạy" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
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

// Form MỞ (phẳng): mọi ô luôn hiện, không phân loại cứng. Chủ xưởng tự đặt "Nhóm máy"
// (chữ tự do) rồi nhập khổ kẽm / nhíp / khổ giấy / vùng in / ghi chú.
// Nhãn đơn vị tốc độ DỜI sang `fields/DonViTocDo` (08/09/2026): bảng "Máy chạy được công đoạn này"
// của drawer Công đoạn nay cũng bày đơn vị của máy, hai bản sao là hai màn nói lệch nhau.

export const CFG_MAY: CatalogConfig = {
  title: "Thiết bị & Máy móc",
  moduleQuyen: "dm_thiet_bi",
  enableClone: true,
  enableImport: true,
  // Máy có cột `active` từ 15/08/2026 (mg `0202`) ⇒ vào được luật xoá chung: còn dùng ở lệnh /
  // công đoạn thì NGỪNG DÙNG, khai nhầm thì xoá hẳn. Trước đó màn này chỉ có xoá cứng.
  softDelete: true,
  prefix: "/api/may-thiet-bi",
  nhatKyLoai: "may_thiet_bi",
  columns: [
    { key: "loai_may", label: "Nhóm máy", render: (r) => (r.loai_may ? String(r.loai_may) : "") },
    // Cột "Khổ máy & Vùng in" + "Chừa lề tờ in" ĐÃ ẨN (04/09/2026): mọi ô đổ ra hai cột này đã
    // rút khỏi form khai, để lại cột thì bảng chỉ còn bày số cũ mà không ai sửa được ở đâu nữa.
    { key: "toc_do", label: "Tốc độ & Chuẩn bị",
      render: (r) => {
        const nSpeed = r.toc_do ? `${Number(r.toc_do).toLocaleString("vi-VN")} ${nhanDonViTocDo(r)}` : null;
        const box = (r.fields_theo_loai ?? {}) as Record<string, unknown>;
        const khoan = box.chuan_bi_khoan as ChuanBiKhoanRow[] | undefined;
        const tongKhoan = Array.isArray(khoan) && khoan.length > 0 ? tongChuanBi(khoan) : 0;
        const totalMakeready = tongKhoan > 0 ? tongKhoan : (Number(r.makeready_time_default) || 0);

        if (!nSpeed && !totalMakeready) return "";
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "2px", fontSize: "12.5px" }}>
            {nSpeed && <div style={{ fontWeight: 600 }}>{nSpeed}</div>}
            {totalMakeready > 0 && (
              <div style={{ fontSize: "12px", color: "var(--rust, #c5400a)", fontWeight: 500, display: "flex", alignItems: "center" }}>
                <ClockIcon size={12} /> Chuẩn bị: {totalMakeready} phút
              </div>
            )}
          </div>
        );
      }
    },
    // Trạng thái LÚC NÀY — dẫn xuất từ sự cố + vùng khoá + lệnh đang chạy (`loadExtra` bên dưới).
    // Cố ý KHÔNG đẻ lại cột `trang_thai` trên máy: cột đó từng có và bị gỡ 11/08/2026 vì là ô khai
    // tay không ai vào sửa, nên máy đang nằm vẫn hiện "đang hoạt động".
    { key: "trang_thai", label: "Trạng thái",
      render: (_r, extra) => {
        // `undefined` = CHƯA BIẾT (đang nạp / nạp hỏng). Nói "Rảnh" lúc đó là bịa — cái máy đang
        // hỏng cũng sẽ hiện Rảnh cho tới khi API về.
        if (extra === undefined) {
          return <span className="rc-tt rc-tt--chua-biet" title="Đang lấy trạng thái máy…">—</span>;
        }
        const tt = extra as TrangThaiMay | null;
        const kieu = tt?.trang_thai ?? "ranh";
        return (
          <span className={`rc-tt rc-tt--${kieu}`}>
            {/* Chấm + CHỮ, không chỉ dựa màu — xưởng có người phân biệt màu kém, mà đây đúng là
                thứ họ cần đọc nhanh nhất. */}
            <span className="rc-tt__dot" aria-hidden="true" />
            <span className="rc-tt__body">
              {/* Fallback phải KHỚP `NHAN[TT_RANH]` bên backend (`services/may_trang_thai.py`):
                  máy rảnh không có mặt trong map nên nhãn của nó chỉ tồn tại ở đây. */}
              <span className="rc-tt__nhan">{tt?.nhan ?? "Xếp được"}</span>
              {tt?.chi_tiet && <span className="rc-tt__chi-tiet">{tt.chi_tiet}</span>}
            </span>
          </span>
        );
      } },
  ],
  loadExtra: (token) => trangThaiMay(token),
  // Lọc theo Nhóm máy — hàng tab lấy thẳng từ DANH MỤC nhóm máy (`/api/nhom-may`), đúng cái
  // nguồn đổ ra mấy con chip trong drawer. Trước 22/08/2026 chỗ này liệt kê CỨNG 5 tên: nhóm chủ
  // xưởng tự đặt chỉ hiện sau khi đã có máy thuộc về nó (tab sinh từ số đếm), còn 5 tên cứng thì
  // treo mãi kể cả khi đã gỡ khỏi danh mục. `dynamic` vẫn giữ: máy cũ mang tên nhóm không còn
  // trong danh mục vẫn phải có lối lọc tới, không được rơi khỏi hàng tab.
  facet: { key: "loai_may", source: "/api/nhom-may", dynamic: true },
  // `nhanTabCongThuc` GỠ cùng ô "Cách đo lượng" (06/09/2026): màn Máy không còn ô công thức nào
  // nên tab công thức tự biến mất, giữ nhãn lại là nhãn của một tab không tồn tại.
  // Khai máy vẫn chia 3 tab theo việc: cuộn một mạch thì khối Lịch bảo trì nằm tít dưới đáy,
  // ai vào sửa chu kỳ cũng phải lướt hết phần vận hành.
  tabsKhai: [
    { id: "chung", label: "Thông tin chung", groups: ["Thông tin chung"] },
    { id: "ky-thuat", label: "Thông số kỹ thuật",
      groups: ["Tốc độ & Vận hành", "Ghi chú"] },
    { id: "bao-tri", label: "Lịch bảo trì", groups: ["Bảo trì định kỳ"] },
  ],
  fields: [
    // ── Nhóm máy (chữ gợi ý + tự do) ──────────────────────────────────────────
    // ── 1. Thông tin chung ──────────────────────────────────────────────────
    { key: "loai_may", label: "Nhóm máy", type: "nhom_may", required: true, group: "Thông tin chung",
      refPrefix: "/api/nhom-may" },
    // Nhận diện tài sản — cột đã có sẵn trong DB (chỉ chưa bày ra form).
    { key: "hang_san_xuat", label: "Hãng sản xuất", type: "text", group: "Thông tin chung" },
    { key: "model", label: "Model", type: "text", group: "Thông tin chung" },
    { key: "so_seri", label: "Số seri", type: "text", group: "Thông tin chung" },
    // Khổ kẽm · Vùng in max · Chừa lề tờ in · Khổ giấy min/max ĐÃ ẨN (04/09/2026): mấy số này chỉ
    // phục vụ bình bài THEO MÁY ở phiếu tính giá, mà ô "Máy in" của phiếu cũng vừa ẩn cùng đợt.
    // Cột DB + engine giữ nguyên (phiếu cũ đã gắn máy vẫn tính đúng), chỉ không bày ra form nữa.
    // ── 2. Tốc độ & Năng suất vận hành ───────────────────────────────────────
    { key: "toc_do", label: "Tốc độ trung bình", type: "number", group: "Tốc độ & Vận hành" },
    // Dải tốc độ BÀY LẠI (08/09/2026). Lần ẩn trước (04/09/2026) đi kèm lời "dải tốc độ chỉ để
    // khai, không nối vào công thức nào" — nay KHÔNG còn đúng: `lsxBuoc.ts`, `lsx_service` và
    // `xep_lich_service` đều đọc hai số này để ra khoảng nhanh–chậm ("Biên độ tốc độ máy" ở drawer
    // bước, râu Gantt). Ẩn ô mà engine vẫn đọc ⇒ người khai thấy một khoảng 130h–312h không biết
    // từ đâu ra và không có cửa nào sửa. Chưa khai thì cả ba mức bằng nhau, không vẽ khoảng.
    { key: "toc_do_min", label: "Tốc độ tối thiểu", type: "number", group: "Tốc độ & Vận hành" },
    { key: "toc_do_max", label: "Tốc độ tối đa", type: "number", group: "Tốc độ & Vận hành" },
    { key: "don_vi_toc_do", label: "Đơn vị tốc độ", type: "don_vi_toc_do",
      refPrefix: "/api/don-vi", refParams: { size: 200 },
      group: "Tốc độ & Vận hành", default: "to_gio" },
    // Ô "Cách đo lượng theo đơn vị tốc độ" ĐÃ GỠ (06/09/2026): cách đo nay khai theo CẶP (công
    // đoạn × máy) ở drawer Công đoạn — cùng một máy chạy hai công đoạn thì đo khác nhau.
    // Ô "Số người vận hành tiêu chuẩn" ĐÃ GỠ (06/09/2026, mg `0270`): kíp nay khai MỘT chỗ duy
    // nhất là định mức đầu việc của công đoạn, và mọi loại bước lệnh đều điền sẵn từ đó.
    // Ô "Ca làm việc của máy này" ĐÃ BỎ (2026-08-10): máy là thiết bị, bàn xếp lịch cho chạy
    // LIÊN TỤC (chỉ dừng vì ngày nghỉ/lễ + vùng khoá máy). Ca là chuyện của người và khai một chỗ
    // ở Nhân sự → Ca kíp; tăng ca thì cứ xếp việc vào giờ đó, khỏi sửa danh mục máy.
    // Ô "Thời gian rửa mực" ĐÃ BỎ (2026-08-04): vệ sinh/rửa mực gỡ khỏi hệ, engine xếp lịch
    // thôi cộng vào thời gian chiếm máy. Cột DB giữ dormant — đừng khai lại ô này.
    { key: "_chuan_bi_kieu", label: "Thời gian chuẩn bị", type: "select", group: "Tốc độ & Vận hành",
      default: "trong",
      options: [
        { value: "trong", label: "Để trống — chưa khai" },
        { value: "tong", label: "Điền tổng — gõ thẳng một số" },
        { value: "khoan", label: "Theo từng khoản — máy tự cộng" },
      ] },
    { key: "makeready_time_default", label: "Tổng thời gian chuẩn bị (phút)", type: "number",
      group: "Tốc độ & Vận hành",
      showIf: (f) => f._chuan_bi_kieu === "tong" },
    { key: "chuan_bi_khoan", label: "Các khoản chuẩn bị", type: "chuan_bi_khoan",
      group: "Tốc độ & Vận hành", jsonKey: "fields_theo_loai",
      showIf: (f) => f._chuan_bi_kieu === "khoan" },
    // ── 6. Bảo trì định kỳ (lưu lồng trong fields_theo_loai — KHÔNG cột mới, KHÔNG migration) ─
    { key: "lich_bao_tri", label: "Lịch bảo trì định kỳ", type: "lich_bao_tri",
      group: "Bảo trì định kỳ", jsonKey: "fields_theo_loai" },
    // ── 7. Ghi chú ───────────────────────────────────────────────────────────
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
  ],
  // Đơn vị tốc độ là Ô CHỌN 2 giá trị, không suy từ `loai_may`: nhóm máy ở đây là CHỮ TỰ DO
  // ("Máy in", "Bế", "Cán màng / UV"…) nên suy theo nó là đoán, mà đoán sai thì lệnh SX lặng lẽ
  // bỏ qua tốc độ. Chỉ bày 2 lựa chọn đang dùng thật (tờ/giờ · kẽm/giờ), không đổ hết 5 đơn vị.
  // Kiểu chuẩn bị KHÔNG có cột riêng — SUY từ dữ liệu đã lưu. Thêm cột "kiểu" là đẻ trạng thái
  // thứ hai có thể đá nhau với chính dữ liệu (kiểu="khoản" mà danh sách rỗng thì tin ai?).
  deriveInitial: (existing) => {
    const box = (existing?.fields_theo_loai ?? {}) as Record<string, unknown>;
    const khoan = box.chuan_bi_khoan;
    const co_khoan = Array.isArray(khoan) && khoan.length > 0;
    const co_tong = existing?.makeready_time_default != null && existing.makeready_time_default !== "";
    return { _chuan_bi_kieu: co_khoan ? "khoan" : co_tong ? "tong" : "trong" };
  },
  transformSubmit: (body, form, existing) => {
    const out: Record<string, unknown> = {
      ...body,
      // Đơn vị đi theo BẤT KỲ ô tốc độ nào có số, không riêng ô trung bình: khai mỗi dải
      // nhanh–chậm mà đơn vị bị xoá thì lệnh SX coi như lệch đơn vị và bỏ qua tốc độ trong im lặng.
      don_vi_toc_do: (body.toc_do || body.toc_do_min || body.toc_do_max)
        ? (body.don_vi_toc_do || "to_gio") : null,
    };
    // Ô CHỈ ĐỂ UI, không có cột — gửi lên là 422.
    delete out._chuan_bi_kieu;

    // Đổi kiểu phải DỌN kiểu cũ. Form chỉ gửi field ĐANG HIỆN, mà backend gán từng phần
    // (`if k in data`) ⇒ không dọn thì số cũ nằm lại: chuyển "tổng 30" sang "để trống" vẫn còn 30,
    // và `deriveInitial` lần sau đọc được nó rồi lật ngược kiểu về "tổng".
    const kieu = form._chuan_bi_kieu;
    // ⚠️ Nền phải là JSON CŨ của bản ghi, không phải {}: ở kiểu "tổng"/"trống" thì ô các-khoản bị
    // ẩn nên `body.fields_theo_loai` không tồn tại — dựng lại từ số 0 là XOÁ SẠCH các khoá khác
    // của cột này (thông số riêng của máy web/digital/flexo… đều nằm trong đó).
    const box = {
      ...((existing?.fields_theo_loai as Record<string, unknown>) ?? {}),
      ...((out.fields_theo_loai as Record<string, unknown>) ?? {}),
    };
    if (kieu === "khoan") {
      const rows = (Array.isArray(box.chuan_bi_khoan) ? box.chuan_bi_khoan : []) as ChuanBiKhoanRow[];
      // Tổng do MÁY cộng — đây là số Xếp lịch đọc. Nguồn chân lý vẫn là một cột duy nhất.
      out.makeready_time_default = tongChuanBi(rows) || null;
    } else {
      box.chuan_bi_khoan = [];
      if (kieu === "trong") out.makeready_time_default = null;
    }
    out.fields_theo_loai = box;
    return out;
  },
};

export const CFG_CONG_DOAN: CatalogConfig = {
  title: "Công đoạn",
  moduleQuyen: "dm_cong_doan",
  enableClone: true,
  enableImport: true,
  prefix: "/api/cong-doan",
  nhatKyLoai: "cong_doan",
  // Xoá MỀM: nút "Xóa" hỏi server "còn ai dùng không" rồi tự chọn kết cục — chưa ai dùng thì
  // xoá hẳn, còn nơi dùng thì chỉ ngừng dùng. Mục đã ngừng xem lại ở công tắc trên dải lọc.
  softDelete: true,
  // Drawer chỉ còn MỘT ô công thức (`cong_thuc_gia`) — ô "Công thức sản lượng ra" GỠ 18/09/2026
  // (mg `0324`). Ô còn lại tự khai `nhanTab` nên KHÔNG cần nhãn tab gộp `nhanTabCongThuc`.
  facet: { key: "nhom", values: mapOpt(NHOM_CD) },
  // Hai tab khai (18/09/2026): "Thông tin" gom mọi nhóm cũ, "Vật tư" là bảng vật tư + công thức
  // định mức của từng món (mg `0316`). Nhóm nào không liệt kê thì drawer tự dồn vào tab đầu.
  tabsKhai: [
    { id: "info", label: "Thông tin", groups: ["Thông tin"] },
    { id: "khoan", label: "Khoán", groups: ["Khoán"] },
    { id: "vat-tu", label: "Vật tư", groups: ["Vật tư"] },
  ],
  // Bề rộng đo theo chữ dài nhất đang có (18/09/2026, bảng 1150px): Giai đoạn "Gia công sau in"
  // 97px · Đơn vị "Con → Thành phẩm" 122 · Bù hao "Tra bảng theo mã bù hao" 158 · Ràng buộc
  // "Cần khuôn ép kim" 112, còn Tên dài nhất chỉ "Cắt thành phẩm" 105. Để mặc định (Tên 24%,
  // Ghi chú 22%) thì bốn cột kia chỉ còn 92px, đọc ra "Gia côn…" / "Tra bản…". Ghi chú không
  // khai ⇒ ăn phần còn lại; chữ dài cắt "…", rê chuột xem đủ.
  widthMa: "10%",
  widthTen: "12%",
  columns: [
    { key: "nhom", label: "Giai đoạn", width: "11%", render: (r) => lbl(NHOM_CD)(r.nhom) },
    // Nhìn ra ngay bước nào ĐỔI CHẶNG, và bước nào để trống (không nằm trên dòng giấy).
    // Nhãn lấy từ `/api/don-vi/tram` — CÙNG nguồn mà ô chọn trong drawer dùng. Trước 08/09/2026 cột này đọc
    // `don_vi_vao_ten` server gán, mà server tra mã chặng vào danh mục Đơn vị & quy đổi: cùng một
    // bước hiện "con → cái" ở danh sách nhưng "Con (mảnh bế ra) → Thành phẩm" trong drawer.
    // Chưa khai thì hiện "—", đúng nghĩa "bước không chạm giấy", chứ không bịa tên.
    { key: "don_vi_vao", label: "Đơn vị", width: "12%", render: (r) => tramVaoRa(r.don_vi_vao, r.don_vi_ra) },
    { key: "kieu_bu_hao", label: "Bù hao", width: "15%", render: (r) =>
        r.kieu_bu_hao === "co_dinh" ? `Cố định ${r.so_to_bu_hao ?? 50} tờ` : lbl(KIEU_BU_HAO)(r.kieu_bu_hao ?? "khong") },
    // Nhìn ra công đoạn nào chưa khai số cho Lệnh sản xuất (giống cột Tốc độ bên màn Máy).
    // Ba thứ ĐI CÙNG NHAU ở một cột vì chúng cùng trả lời "bước này ăn bao nhiêu thời gian, và có
    // vướng dụng cụ không" — tách ba cột thì bảng dài mà vẫn phải đọc cả ba mới hiểu.
    { key: "requires_tooling", label: "Ràng buộc", width: "13%",
      render: (r) => {
        if (!r.requires_tooling) return "";
        const chuDayDu = `Cần ${lbl(TOOLING_TYPE)(r.tooling_type).toLowerCase()}`;
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "12px" }}>
            {!!r.requires_tooling && (
              <span className="rc__formula-pill" title={chuDayDu}>
                {chuDayDu}
              </span>
            )}
          </div>
        );
      } },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "nhom", label: "Giai đoạn", type: "select", required: true, group: "Thông tin", options: mapOpt(NHOM_CD) },
    // NHIỀU tổ (18/09/2026, mg `0312`): "Cán màng mờ" do tổ Cán lẫn tổ Thành phẩm làm. Bước lệnh CHỌN
    // MỘT trong các tổ này; tổ bấm chọn ĐẦU TIÊN là tổ mặc định lúc lên lệnh.
    { key: "department_ids", label: "Phòng ban / Tổ phụ trách", type: "to-multi", refPrefix: "/api/cong-doan/phong-ban",
      group: "Thông tin", nhanDau: "mặc định",
      hint: "Chọn được nhiều tổ — lệnh sản xuất chọn một trong số này cho từng bước. Tổ chọn đầu tiên là tổ mặc định." },
    { key: "khoan", label: "", type: "khoan-cong-doan", refPrefix: "/api/don-vi", group: "Khoán" },

    // ── Nguồn nuôi thẳng thời lượng bước ở Lệnh sản xuất ──────────────────────────────────────
    { key: "requires_tooling", label: "Bước này cần khuôn", type: "checkbox",
      group: "Khuôn & dụng cụ",},
    { key: "tooling_type", label: "Loại khuôn", type: "select", group: "Khuôn & dụng cụ",
      options: mapOpt(TOOLING_TYPE), showIf: (f) => !!f.requires_tooling },
    // Bảng "Đầu việc và định mức của tổ" GỠ 18/09/2026 (mg `0320`) — công đoạn là CÔNG NGHỆ, việc
    // của tổ khai ở danh mục Công việc khoán. Vật tư (nền BOM) chuyển sang tab "Vật tư" bên dưới.
    { key: "vat_tus", label: "Vật tư công đoạn tiêu thụ", type: "vat-tu-cong-doan", group: "Vật tư" },
    // Chặn gán máy SAI LOẠI ở bài ghép (vd Ghi kẽm CTP không cho máy Bế). Lưu mảng TÊN nhóm máy.
    { key: "nhom_may_cho_phep", label: "Máy làm được công đoạn này", type: "nhom_may-multi",
      refPrefix: "/api/nhom-may", group: "Lệnh sản xuất" },
    // Máy CỤ THỂ + công thức của riêng từng cặp (06/09/2026). Hàng tick ngay trên chỉ còn là bộ
    // lọc cho bảng này; luật chặn gán máy ở bước đọc DANH SÁCH này khi công đoạn có khai.
    { key: "may_lam_duoc", label: "Máy chạy được công đoạn này", type: "may-cua-cong-doan",
      // `size` phải ≤ 200: khung danh mục chung chặn trần ở `catalog_base.py` (`le=200`). Xin 500
      // thì router trả 422 và ô chọn máy rỗng IM LẶNG — không báo lỗi gì cho người dùng thấy.
      // Máy ngừng dùng do `locConDung` gạt, KHÔNG lọc bằng `active: true`: lọc ở query thì máy
      // ngừng đang nằm sẵn trong bảng dưới mất tên, chỉ còn `#id`.
      refPrefix: "/api/may-thiet-bi", refParams: { size: 200 },
      group: "Lệnh sản xuất" },

    // CHỈ TÍNH THEO CÔNG THỨC: đã bỏ ô 'Cách tính giá' / 'Đơn giá' / 'Bậc kích thước'.
    // Đơn giá nhập per-phiếu (mỗi dòng phiếu tính giá tự mang don_gia); công đoạn chỉ khai CÔNG THỨC.
    //
    // `to_dau_vao`/`to_sau_in` không còn chip ở đây — từ 03/09/2026 hai biến bị ẩn ở MỌI ô công
    // thức (`AN_MOI_O` trong `fields/FormulaField.tsx`), không riêng công đoạn nữa.
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá",
      nhanTab: "Công thức tính giá", an: AN_CHIP_KHUON },
    // ── Đơn vị đứng TRƯỚC Bù hao: nó quyết định bù hao được tra theo số gì (tờ hay con) ────────
    // MENU ĐÓNG 5 TRẠM của dòng giấy (06/09/2026). Hai ô này KHÔNG còn trỏ vào danh mục Đơn vị &
    // quy đổi: danh mục đó phục vụ kho/mua hàng (kg, ram, thùng…), mời hết vào đây thì người khai
    // chọn được `kg` cho một bước in — sai mà không ai chặn. Câu hỏi ở đây hẹp hơn nhiều: bước này
    // đứng ở CHẶNG NÀO của tờ giấy? Chỉ có đúng 5 chặng, và engine bù hao chỉ biết 5 cầu giữa
    // chúng (`CAU_TRAM` bên backend) — thêm chặng thứ 6 là phải sửa code chứ không phải khai danh mục.
    // Để TRỐNG cả hai = bước NGOÀI dòng giấy (ghi kẽm, đóng thùng…): không dính chuỗi bù hao của
    // giấy; đơn vị + số của nó do người lập lệnh TỰ KHAI ở drawer bước lệnh.
    { key: "don_vi_vao", label: "Đơn vị đầu vào", type: "select", options: tramOptions,
      group: "Đơn vị", default: "to",
      hint: "Để trống = bước không nằm trên dòng giấy (ghi kẽm, đóng thùng…). Trống thì phải trống CẢ HAI ô." },
    { key: "don_vi_ra", label: "Đơn vị đầu ra", type: "select", options: tramOptions,
      group: "Đơn vị", default: "to",
      hint: "Chảy một chiều: tờ nguyên → tờ in → con / tay sách → thành phẩm. Không đi ngược." },
    // GỠ 18/09/2026 (mg `0324`): "Công thức sản lượng ra" + "Đơn vị sản lượng" của bước ngoài dòng
    // giấy (cùng `he_so_ngoai_dong` đã ngưng từ 20/08) — số của bước ấy nay khai tay ở bước lệnh.
    { key: "kieu_bu_hao", label: "Bù hao", type: "select", group: "Bù hao", options: mapOpt(KIEU_BU_HAO), default: "khong" },
    { key: "bu_hao_id", label: "Mã bù hao (gõ để tìm)", type: "ref-search", refPrefix: "/api/bu-hao", group: "Bù hao",
      showIf: (f) => f.kieu_bu_hao === "tra_bang" },
    { key: "so_to_bu_hao", label: "Số lượng cộng cố định", type: "number", group: "Bù hao", default: 50,
      showIf: (f) => f.kieu_bu_hao === "co_dinh" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Thông tin" },
  ],
  // CHỈ TÍNH THEO CÔNG THỨC: công đoạn luôn ở chế độ sản lượng + basis 'per_other' (giá phẳng/công
  // thức) để backend không chặn E-CD-BASIS. Dọn run_rate/size_tiers (đơn giá nay nhập per-phiếu).
  transformSubmit: (body) => {
    body.department_ids = Array.isArray(body.department_ids) ? body.department_ids : [];
    // Vắng khoá = server GIỮ nguyên — nhưng drawer luôn mở với đủ danh sách, nên gửi mảng rỗng là
    // đúng ý "đã gỡ hết" chứ không phải "không đụng tới".
    body.vat_tus = body.vat_tus ?? [];
    const khoan = body.khoan && typeof body.khoan === "object"
      ? body.khoan as Record<string, unknown> : {};
    const phatSinh = Array.isArray(khoan.viec_phat_sinh) ? khoan.viec_phat_sinh : [];
    const coCauHinh = !!String(khoan.unit ?? "").trim()
      || (khoan.unit_price !== null && khoan.unit_price !== undefined && khoan.unit_price !== "")
      || !!String(khoan.cong_thuc_khoan ?? "").trim()
      || phatSinh.length > 0;
    body.khoan = coCauHinh ? { ...khoan, viec_phat_sinh: phatSinh } : null;
    // Bỏ tick "cần khuôn" thì ô Loại dụng cụ bị `showIf` ẩn ⇒ không nằm trong body ⇒ backend giữ
    // giá trị cũ. Xoá thẳng ở đây, không thì công đoạn hiện "không cần khuôn" mà vẫn đeo nhãn
    // "Khuôn bế" trong dữ liệu.
    body.requires_tooling = !!body.requires_tooling;
    if (!body.requires_tooling) body.tooling_type = null;
    body.che_do_tinh = "theo_san_luong";
    body.pricing_basis = "per_other";
    body.run_rate = null;
    body.size_tiers = [];
    return body;
  },
};

export const CFG_BU_HAO: CatalogConfig = {
  title: "Bù hao",
  moduleQuyen: "dm_bu_hao",
  enableImport: true,
  prefix: "/api/bu-hao",
  nhatKyLoai: "bu_hao",
  // Xoá MỀM: nút "Xóa" hỏi server "còn ai dùng không" rồi tự chọn kết cục — chưa ai dùng thì
  // xoá hẳn, còn nơi dùng thì chỉ ngừng dùng. Mục đã ngừng xem lại ở công tắc trên dải lọc.
  softDelete: true,
  columns: [
    {
      key: "bac",
      label: "Bậc số lượng & Mức bù hao",
      render: (r) => {
        const arr = (r.bac ?? []) as { sl_tu?: number; sl_den?: number | null; den_cm?: number | null; gia_tri?: number; don_gia?: number; don_vi?: string }[];
        if (!Array.isArray(arr) || arr.length === 0) {
          return <span style={{ color: "var(--ash, #8a8577)", fontSize: "12.5px" }}>Chưa khai báo</span>;
        }
        return (
          <div className="rc__formula-chips">
            {arr.slice(0, 3).map((item, idx) => {
              const cap = item.sl_den ?? item.den_cm;
              const capStr = cap != null && cap > 0 ? `≤${Number(cap).toLocaleString("vi-VN")}` : `>${Number(item.sl_tu ?? 0).toLocaleString("vi-VN")}`;
              const val = item.gia_tri ?? item.don_gia ?? 0;
              const unitStr = item.don_vi === "pct" || item.don_vi === "%" ? "%" : " tờ";
              return (
                <span key={idx} className="rc__formula-pill">
                  {capStr}: {val}{unitStr}
                </span>
              );
            })}
            {arr.length > 3 && (
              <span className="badge-sem badge-sem--muted">+{arr.length - 3} bậc</span>
            )}
          </div>
        );
      },
    },
    { key: "so_bac", label: "Số bậc", render: (r) => `${Array.isArray(r.bac) ? r.bac.length : 0} bậc` },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "bac", label: "Bậc số lượng → giá trị (tờ / %)", type: "bands", group: "Bậc số lượng" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Bậc số lượng" },
  ],
};


export const CFG_CHUNG_LOAI_GIAY: CatalogConfig = {
  title: "Chủng loại giấy",
  moduleQuyen: "dm_chung_loai_giay",
  enableImport: true,
  prefix: "/api/vat-lieu-kho/chung-loai-giay",
  nhatKyLoai: "chung_loai_giay",
  // Xoá MỀM: nút "Xóa" hỏi server "còn ai dùng không" rồi tự chọn kết cục — chưa ai dùng thì
  // xoá hẳn, còn nơi dùng thì chỉ ngừng dùng. Mục đã ngừng xem lại ở công tắc trên dải lọc.
  softDelete: true,
  columns: [
    { key: "mo_ta", label: "Mô tả", render: (r) => (r.mo_ta ? String(r.mo_ta) : "") },
  ],
  fields: [
    { key: "mo_ta", label: "Mô tả", type: "text", group: "Thông số" },
  ],
};

/** Giấy này bán/đếm theo CÂN hay theo TỜ — câu hỏi quyết định cả hai công thức điền sẵn dưới đây.
 *
 *  ĐVT chưa chọn (ô đó không có `default`, mở drawer ra là trống) thì coi như theo CÂN: giấy ở
 *  đây bán theo cân, ô đơn giá ngay trên cũng ghi đ/kg. Chọn ĐVT xong thì công thức tự đổi lại.
 *  Cùng tập mã với nhánh dự phòng bên `thanh_phan_engine.py`. */
const giayTheoCan = (donViGia: unknown): boolean => {
  const dv = String(donViGia ?? "");
  return !dv || dv === "kg" || dv === "tan";
};

/** Công thức TIỀN giấy điền sẵn cho mặt hàng mới.
 *
 *  Theo CÂN thì tiền = khối lượng × đ/kg, mà khối lượng phải dựng lại từ định lượng × khổ tờ × số
 *  tờ. Đếm theo TỜ thì đơn giá đã là tiền một tờ — nhân thêm định lượng và diện tích nữa là lệch
 *  hàng chục lần, và phiếu vẫn ra một con số trông hợp lý nên không ai soi ra. */
const congThucGiaGiay = (donViGia: unknown): string =>
  (giayTheoCan(donViGia)
    ? "dinh_luong * dai_nguyen * rong_nguyen * to_nguyen * don_gia_giay"
    : "don_gia_giay * to_nguyen");

/** Công thức ĐỊNH MỨC điền sẵn — cùng phép đếm, nhưng dừng trước đơn giá: ô này trả lời "một lệnh
 *  ăn bao nhiêu giấy" cho bảng cân đối vật tư, và tuyệt đối không được nhắc tới tiền.
 *
 *  Số nó trả về đi so với TỒN KHO, mà kho cộng dồn theo ĐVT gốc của mặt hàng — nên giấy đếm theo
 *  tờ thì định mức cũng phải ra tờ, không ra kg. Chuỗi theo cân là chuỗi mg `0197` đã backfill cho
 *  giấy bán theo cân (`_CT_LUONG_GIAY_CAN` ở `seed_rebuild.py`). */
const congThucLuongGiay = (donViGia: unknown): string =>
  (giayTheoCan(donViGia) ? "dinh_luong * dai_nguyen * rong_nguyen * to_nguyen" : "to_nguyen");

export const CFG_GIAY: CatalogConfig = {
  title: "Giấy",
  moduleQuyen: "dm_giay",
  enableClone: true,
  enableImport: true,
  prefix: "/api/vat-lieu-kho/giay",
  nhatKyLoai: "giay",
  softDelete: true,
  columns: [
    { key: "gsm", label: "Định lượng", render: (r) => `${r.gsm} g/m²` },
    { key: "don_vi_gia", label: "ĐVT", render: (r) => dvCell(r) },
    { key: "don_gia", label: "Đơn giá (đ/kg)", render: (r) => (Number(r.don_gia) ? Number(r.don_gia).toLocaleString("vi-VN") : "") },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "chung_loai_giay_id", label: "Chủng loại giấy", type: "ref", required: true,
      refPrefix: "/api/vat-lieu-kho/chung-loai-giay", group: "Phân loại" },
    { key: "gsm", label: "Định lượng (g/m²)", type: "number", required: true, group: "Thông số" },
    // Đơn vị GỐC: tồn kho cộng dồn theo đơn vị này. Giấy để `kg` thì kho đếm theo cân; muốn đếm
    // theo tờ thì chọn `tờ` — cặp cố định "1 ram = 500 tờ" chạy sẵn, không cần khai khổ.
    { key: "don_vi_gia", label: "ĐVT", ...F_DON_VI, group: "Thông số" },
    // Đơn giá theo cân — CHỐT CỨNG ở danh mục (engine lấy thẳng, phiếu không sửa).
    { key: "don_gia", label: "Đơn giá (đ/kg)", type: "number", group: "Giá", hint: "Đơn giá theo ĐVT đã chọn (mặc định đ/kg)" },
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá",
      nhanTab: "Công thức tính giá", an: AN_CHIP_KHUON,
      // ĐIỀN SẴN khi thêm mới (11/09/2026), sửa/xoá được. Trước đó ô này để trống và engine âm
      // thầm chạy đúng hai chuỗi dưới đây làm dự phòng — thứ đang tính tiền giấy mà người khai
      // không nhìn thấy ở đâu cả. Hai chuỗi phải khớp nhánh dự phòng bên
      // `thanh_phan_engine.py`: sửa một bên thì sửa cả hai.
      macDinhTheo: (f) => congThucGiaGiay(f.don_vi_gia) },
    // Ô thứ hai ra LƯỢNG, không ra tiền — MỞ LẠI 07/09/2026 sau khi ẩn một ngày (06/09/2026), và
    // đổi tên thành "Công thức tính định mức": chữ "lượng" đứng cạnh ô "tính giá" không nói được
    // nó trả lời câu gì, còn "định mức" là chữ xưởng vẫn dùng cho "một lệnh ăn bao nhiêu giấy".
    // Cùng chữ đó ở cột Excel danh mục Giấy và ở nhãn nhật ký (`nhat_ky_danh_muc`) — một ô thì
    // một tên, không để ba màn gọi ba kiểu.
    //
    // Nó là thứ DUY NHẤT còn đổi được tờ → kg cho bảng cân đối vật tư sau khi gỡ cặp quy đổi động
    // (mg 0198); mg 0197 đã điền sẵn cho giấy bán theo cân. `loaiO: "quy_doi"` ⇒ chip có
    // `sl_vao`/`sl_ra` và KHÔNG có đơn giá — ô này không được phép nhắc tới tiền.
    { key: "cong_thuc_luong", label: "Công thức tính định mức", type: "formula", loaiO: "quy_doi",
      group: "Giá", nhanTab: "Công thức tính định mức",
      macDinhTheo: (f) => congThucLuongGiay(f.don_vi_gia)},
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
    // NVL thay thế (mục 5 "Bảng định mức", mg 0239) — tra cứu/gợi ý khi thiếu giấy, MỘT CHIỀU.
    { key: "thay_the_ids", label: "Giấy thay thế", type: "self-ref-multi",
      refPrefix: "/api/vat-lieu-kho/giay", group: "Ghi chú",
      hint: "Giấy khác dùng thay được món này khi thiếu hàng. Chỉ để tra cứu, không tự suy chiều ngược lại." },
  ],
};

export const CFG_VAT_TU: CatalogConfig = {
  title: "Vật tư khác",
  moduleQuyen: "dm_vat_tu",
  enableClone: true,
  enableImport: true,
  prefix: "/api/vat-lieu-kho/vat-tu-in-an",
  nhatKyLoai: "vat_tu",
  // Vật tư khác nay KHÔNG còn ô công thức nào trong drawer (06/09/2026): ô giá ẩn từ trước, ô
  // lượng chuyển về từng dòng vật tư của đầu việc trong drawer Công đoạn — nên bỏ luôn nhãn tab.
  // Xoá MỀM: nút "Xóa" hỏi server "còn ai dùng không" rồi tự chọn kết cục — chưa ai dùng thì
  // xoá hẳn, còn nơi dùng thì chỉ ngừng dùng. Mục đã ngừng xem lại ở công tắc trên dải lọc.
  softDelete: true,
  columns: [
    { key: "don_vi_gia", label: "ĐVT", render: (r) => dvCell(r) },
    // Cột "Đơn giá" ĐÃ ẨN 09/09/2026 — xem khối chú thích ở `fields` bên dưới.
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    // Quy cách đóng gói (đơn vị đóng gói + hệ số) ĐÃ BỎ 10/08/2026: khai quy đổi ở hai nơi là bắt
    // người dùng nhớ luật vô ích. Cần "1 thùng keo = 20 kg" thì khai thẳng đơn vị đó trong danh
    // mục Đơn vị & quy đổi rồi chọn ở ô ĐVT — một nơi duy nhất cho mọi quy đổi.
    { key: "don_vi_gia", label: "Đơn vị tính (ĐVT)", ...F_DON_VI, group: "Thông số" },
    // ẨN KHỎI UI 09/09/2026 — cùng lối đã làm với `cong_thuc_gia`: giấu ô, GIỮ NGUYÊN cột DB,
    // dữ liệu cũ và mọi đường engine. Hai thứ bị giấu ở màn này:
    //
    //   · `don_gia` — cả ô trong drawer LẪN cột trong bảng. Cột `vat_tu_in_an.don_gia` còn
    //     nguyên, engine vẫn phơi biến `don_gia` cho công thức vật tư (`thanh_phan_engine` /
    //     `tinh_gia_service`), Excel nhập/xuất vẫn mang cột này — chỉ là không khai/không xem
    //     bằng tay ở đây nữa.
    //   · `thay_the_ids` ("Vật tư thay thế", mục 5 "Bảng định mức", mg 0239) — quan hệ MỘT CHIỀU
    //     để tra cứu khi thiếu hàng. API `/api/vat-lieu-kho/vat-tu-in-an` vẫn nhận và trả nó.
    //
    // Cần mở lại thì thêm về đúng chỗ này:
    //   { key: "don_gia", label: "Đơn giá", type: "number", group: "Giá",
    //     hint: "Đơn giá theo ĐVT đã chọn — dùng làm biến don_gia trong công thức" },
    //   { key: "thay_the_ids", label: "Vật tư thay thế", type: "self-ref-multi",
    //     refPrefix: "/api/vat-lieu-kho/vat-tu-in-an", group: "Ghi chú", hint: "..." },
    // và trả cột `don_gia` vào `columns`. Ô của GIẤY (CFG_GIAY) GIỮ NGUYÊN — giấy chốt đơn giá/kg
    // ở danh mục là luật riêng của nó, đừng gỡ theo.
    //
    // Ô "cong_thuc_gia" (công thức ra TIỀN cho dòng vật tư trên phiếu tính giá) ĐÃ ẨN từ trước.
    // Ô "Công thức tính lượng" ĐÃ GỠ (06/09/2026): định mức khai theo TỪNG DÒNG vật tư trong đầu
    // việc của công đoạn.
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
  ],
};

// THÀNH PHẨM — cùng bảng `vat_tu_in_an` với Vật tư khác, chia nhau bằng `order_line_id`
// (docs/prd-thanh-pham.md §3). Menu + ô quyền riêng, nhưng KHÔNG phải `hang_loai` thứ ba: với
// kho thành phẩm vẫn là "vat_tu", nên luồng nhập kho · lập phiếu · trừ tồn không sửa gì.
export const CFG_THANH_PHAM: CatalogConfig = {
  title: "Thành phẩm",
  moduleQuyen: "dm_thanh_pham",
  enableImport: true,
  prefix: "/api/vat-lieu-kho/thanh-pham",
  nhatKyLoai: "thanh_pham",
  // KHÔNG khai tay (chủ 18/09/2026: "bỏ nút thêm thành phẩm đi") — dòng chỉ do chốt đơn sinh ra.
  // 19/08–18/09/2026 từng nới cho Bán hàng khai trước món khách sắp đặt. Nhập Excel vẫn còn để SỬA
  // hàng loạt; mã mới trong file bị máy chủ báo lỗi đúng dòng (`_chan_tao_tay`).
  // KHÔNG cho Xóa: dòng có thể đang có lô tồn hoặc phiếu đã ghi sổ, xoá là làm mồ côi. Cả hai
  // đều chặn song song ở máy chủ, không chỉ giấu nút.
  khongTaoTay: true,
  khongXoa: true,
  softDelete: true,
  columns: [
    // Ô CHỌN "Khách hàng" ĐÃ GỠ HẲN (chủ 21/08/2026: "khách hàng mình lưu làm gì, mình không
    // dùng tới — thành phẩm này là một cái tên hàng mới, nêu chưa khai để tái sử dụng, tránh
    // phình lên"). Thành phẩm KHÔNG thuộc về ai: hai khách đặt cùng tên dùng CHUNG một dòng, công
    // tắc chia hai màn là cột `la_thanh_pham` (mg 0228) do repo tự đóng dấu.
    //
    // HIỆN LẠI dạng CHỈ ĐỌC 17/09/2026 (chủ: "hiển thị hết đi" — màn thiếu so với thứ bảng lưu):
    // đơn + khách ĐẶT LẦN ĐẦU là vết nguồn gốc máy ghi lúc chốt đơn, không phải chủ, không ai sửa.
    // Bề rộng khai đủ cho cả bảng (Mã 14 + Tên 24 + Hành động 8 là của trang) — cộng quá 100% thì
    // `table-layout: fixed` co mọi cột lệch nhau.
    { key: "don_vi_gia", label: "ĐVT", width: "8%", render: (r) => dvCell(r) },
    // 11%: nhãn "ĐƠN ĐẦU TIÊN" cần ~121px mới đứng một dòng (đo ở bảng 1150px, lúc sidebar mở).
    { key: "order_no", label: "Đơn đầu tiên", width: "11%", render: (r) => <MaDon r={r} ngan /> },
    { key: "customer_ten", label: "Khách đặt lần đầu", width: "16%",
      render: (r) => (r.customer_ten ? String(r.customer_ten) : "") },
    { key: "created_at", label: "Ngày khai", width: "9%",
      render: (r) => ngay(r.created_at as string | null) },
    { key: "ghi_chu", label: "Ghi chú", width: "10%",
      render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "don_vi_gia", label: "Đơn vị tính (ĐVT)", ...F_DON_VI, group: "Thông số",
      hint: "Lấy theo đơn vị trên dòng đơn hàng — sửa nếu kho đếm bằng đơn vị khác" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
  ],
  renderChiDoc: (r) => <NguonGocThanhPham r={r} />,
};

/** "DH002" · "Khai tay" · hoặc đơn đã mất khỏi hệ thống (soft-ref, không FK). `ngan` = chữ cho ô
 *  bảng hẹp; drawer dùng câu đầy đủ. */
function donDauTien(r: Row, ngan: boolean): ReactNode {
  if (r.order_no) return String(r.order_no);
  if (r.order_id != null) return ngan ? `#${r.order_id}` : `Đơn #${r.order_id} — không còn trong hệ thống`;
  return ngan
    ? <span className="badge-sem badge-sem--muted">Khai tay</span>
    : "Khai tay trên danh mục — không từ đơn nào";
}

/** Mã đơn BẤM ĐƯỢC → mở luôn drawer đơn ở màn Đơn hàng bán (cùng đường Báo giá / Phiếu thu đang
 *  dùng). Chữ thường khi: đơn đã mất · không quyền đọc đơn (link dẫn vào màn cấm là mời bấm để ăn
 *  lỗi) · màn không có đường điều hướng (dựng trong test). */
function MaDon({ r, ngan }: { r: Row; ngan: boolean }) {
  const navigate = useDieuHuongDanhMuc();
  const can = useCan();
  const chu = donDauTien(r, ngan);
  if (!r.order_no || r.order_id == null || !navigate || !can("don_hang_ban", "read")) return <>{chu}</>;
  return (
    <CodeLink code={String(r.order_no)} title={`Mở đơn ${r.order_no}`}
      onOpen={() => navigate("don-hang-ban", { openOrderId: Number(r.order_id) })} />
  );
}

/** Khối CHỈ ĐỌC cuối tab khai báo của Thành phẩm: thứ bảng lưu mà không ai gõ tay. */
function NguonGocThanhPham({ r }: { r: Row }) {
  const khach = r.customer_ten
    ? [r.customer_ma, r.customer_ten].filter(Boolean).map(String).join(" · ")
    : r.customer_id != null ? `Khách #${r.customer_id} — không còn trong hệ thống` : "—";
  const anh = assetUrl(r.anh_url as string | null);
  const o = (nhan: string, giaTri: string, goiY?: string) => (
    <label className={`rc-field${goiY ? " rc-field--full" : ""}`}>
      <span className="rc-field__label">{nhan}</span>
      <div className="rc-input-wrapper rc-input-wrapper--ro">
        <input className="rc-input" value={giaTri} readOnly />
      </div>
      {goiY && <span className="rc-field__hint">{goiY}</span>}
    </label>
  );
  return (
    <section className="rc-card-section" style={{ padding: "16px 20px" }}>
      <div className="rc-card-section__title">Nguồn gốc &amp; trạng thái</div>
      <div className="rc-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: "12px 16px" }}>
        {r.order_no ? (
          // `div` chứ không `label` như `o()`: label chuyển cú bấm vào nút đầu tiên bên trong, bấm
          // trúng chữ "Đơn hàng đầu tiên" cũng bị đá sang màn đơn.
          <div className="rc-field">
            <span className="rc-field__label">Đơn hàng đầu tiên</span>
            <div className="rc-input-wrapper rc-input-wrapper--ro">
              <span className="rc-input" style={{ display: "block" }}><MaDon r={r} ngan={false} /></span>
            </div>
          </div>
        ) : o("Đơn hàng đầu tiên", String(donDauTien(r, false)))}
        {o("Trạng thái", r.active === false ? "Đã ngừng dùng" : "Đang dùng")}
        {o("Khách đặt lần đầu", khach,
          "Chỉ để tra nguồn gốc — khách khác đặt cùng tên hàng vẫn dùng chung dòng này.")}
        {o("Ngày khai", ngayGio(r.created_at as string | null))}
        {o("Sửa lần cuối", ngayGio(r.updated_at as string | null))}
        {anh && (
          <div className="rc-field rc-field--full">
            <span className="rc-field__label">Ảnh minh hoạ</span>
            <a href={anh} target="_blank" rel="noreferrer" style={{ alignSelf: "flex-start" }}>
              <img src={anh} alt={String(r.ten)} style={{
                maxWidth: 160, maxHeight: 160, objectFit: "cover", borderRadius: 8,
                border: "1px solid var(--rule-soft, #e8e3d3)",
              }} />
            </a>
          </div>
        )}
      </div>
    </section>
  );
}

// Xóa kho KHÔNG dùng luồng ẩn-mềm mặc định: kho là gốc của lô/phiếu/yêu cầu nên phải CHẶN nếu còn
// dính, và bắt gõ mã xác nhận (thao tác nặng). Gọi /delete-check để soi rồi mới cho xóa qua DELETE
// (backend xóa mềm + tự chặn lần nữa). Chỉ role có quyền kho:delete mới thấy nút Xóa.
function KhoDeleteDialog({ row, token, onClose, onDone }: {
  row: Row; token: string; onClose: () => void; onDone: () => void;
}) {
  const [checking, setChecking] = useState(true);
  const [blockers, setBlockers] = useState<string[]>([]);
  const [confirmMa, setConfirmMa] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    authed<{ can_delete: boolean; blockers: string[] }>(`/api/kho/${row.id}/delete-check`, token)
      .then((r) => { if (alive) setBlockers(r.blockers); })
      .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : "Không kiểm tra được kho."); })
      .finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, [row.id, token]);

  const blocked = blockers.length > 0;
  const maOk = confirmMa.trim().toUpperCase() === row.ma.trim().toUpperCase();

  async function doDelete() {
    setBusy(true); setErr(null);
    try {
      await crud("/api/kho").remove(token, row.id);
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không xóa được kho.");
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      danger
      busy={busy}
      error={err}
      title={<>Xóa kho “{row.ten}”</>}
      confirmLabel="Xóa kho"
      confirmDisabled={checking || blocked || !maOk}
      hideConfirm={checking || blocked}
      onCancel={onClose}
      onConfirm={doDelete}
    >
      {checking ? (
        <p className="kho-del__muted">Đang kiểm tra kho…</p>
      ) : blocked ? (
        <div className="kho-del__block">
          <p className="kho-del__warn">Không thể xóa — kho đang được dùng:</p>
          <ul className="kho-del__list">
            {blockers.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
          <p className="kho-del__muted">Hãy xử lý xong tồn / phiếu / yêu cầu của kho này rồi mới xóa.</p>
        </div>
      ) : (
        <div className="kho-del__ok">
          <p>Kho <b>{row.ma}</b> sẽ được <b>xóa</b> — lịch sử phiếu đã ghi sổ vẫn giữ nguyên.</p>
          <label className="kho-del__field">
            <span>Gõ lại mã <b>{row.ma}</b> để xác nhận xóa</span>
            <input
              className="kho-del__input"
              value={confirmMa}
              onChange={(e) => setConfirmMa(e.target.value)}
              placeholder={row.ma}
              autoFocus
            />
          </label>
        </div>
      )}
    </ConfirmDialog>
  );
}

// Khai báo kho — master data NHẸ (chỉ tên / vị trí / ghi chú). Kho tạo ở đây tự đổ
// ra navbar (mục "Kho hàng"). Mã KHO-xxxx tự gợi ý (suggestNextCode). Xóa mềm để giữ dấu vết.
export const CFG_KHO_HANG: CatalogConfig = {
  title: "Kho hàng",             // danh từ ở nút/lọc: "Thêm kho hàng", "Lọc kho hàng"
  heading: "Khai báo kho",       // H1 khớp menu "Khai báo kho"
  moduleQuyen: "dm_kho_hang",
  enableImport: true,
  prefix: "/api/kho",
  nhatKyLoai: "kho_hang",
  softDelete: true,
  autoCode: true,          // mã KHO-#### sinh ngầm ở backend, ẩn ô nhập mã
  columns: [
    { key: "vi_tri", label: "Vị trí", render: (r) => (r.vi_tri ? String(r.vi_tri) : "") },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "vi_tri", label: "Vị trí kho", type: "text", group: "Thông tin"},
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Thông tin" },
  ],
  // Tab thứ 2 trong drawer: khai DANH SÁCH vị trí cất (kệ/ô) của kho — để lập lô/phiếu chọn dropdown
  // thay vì gõ tay. Dùng lại điểm mở rộng `renderExtra` (như bảng quy đổi của Đơn vị). `moLaiSauKhiTao`
  // giữ drawer mở sau khi TẠO kho để khai vị trí ngay (panel cần id, tạo mới chưa có).
  nhanTabCongThuc: "Vị trí kho",
  moLaiSauKhiTao: true,
  renderExtra: (_form, existing) => <KhoViTriPanel kho={existing} />,
  renderDeleteDialog: (row, ctx) => <KhoDeleteDialog row={row} {...ctx} />,
};

// Tình trạng khuôn — record-only (con người phán, máy chỉ ghi nhận).
// `dang_dat_lam` (mg 0177): dao CHƯA có trong tay — thuê ngoài chưa về, hoặc xưởng đang tự làm.
// Đi kèm NGÀY CÓ KHUÔN (dự kiến): bước dùng dao ở Lệnh sản xuất hiện ngày đó để người xếp việc
// biết chờ tới bao giờ. Không có nó thì "đang đặt làm" chỉ là một chữ.
// Loại dao — CÙNG bộ mã với `TOOLING_TYPE` của công đoạn (ô chọn dao ở bước lệnh lọc bằng phép so
// thẳng hai giá trị, lệch bộ mã là lọc ra rỗng).
export const LOAI_KHUON: Lbls = {
  khuon_be: "Khuôn bế",
  khuon_ep: "Khuôn ép kim",
  khung_lua: "Khung lụa",
};

export const TINH_TRANG_KHUON: Lbls = {
  dang_dung: "Đang dùng",
  dang_dat_lam: "Đang đặt làm",
  hong: "Hỏng",
  thanh_ly: "Thanh lý",
};

// Khai báo KHUÔN BẾ — master data NHẸ, khai TAY. Mỗi khuôn làm riêng cho hình bế của 1
// ấn phẩm; đơn lặp lại thì lôi khuôn cũ ra dùng. Chỉ đủ để TÌM LẠI: số kệ (vị trí lưu) +
// tình trạng. Ref ấn phẩm/khách hàng đấu sau. Mã KB-#### tự sinh; xóa mềm giữ dấu vết.
export const CFG_KHUON_BE: CatalogConfig = {
  // Nhan đề "Khuôn" (18/09/2026, trước đó "Khuôn & khung" từ 04/09/2026) — màn vẫn chứa khuôn bế,
  // khuôn ép kim và khung lụa, chip LOẠI bên dưới tách chúng ra. `prefix`, `nhatKyLoai` và
  // `moduleQuyen` GIỮ NGUYÊN chuỗi `khuon_be`, xem cảnh báo ngay dưới.
  title: "Khuôn",
  // ⚠️ `khuon_be` KHÔNG có tiền tố `dm_` như 9 màn kia — đây là chuỗi ĐANG NẰM TRONG bảng
  // `role_permissions` của DB thật (khớp `components/Sidebar.tsx`). Đổi cho "nhất quán" là mọi vai
  // mất sạch quyền màn này.
  moduleQuyen: "khuon_be",
  enableImport: true,
  prefix: "/api/khuon-be",
  nhatKyLoai: "khuon_be",
  softDelete: true,
  autoCode: true,          // mã KB-#### sinh ngầm ở backend, ẩn ô nhập mã
  // Chip theo LOẠI (chủ đổi 18/09/2026, trước đó chip theo tình trạng). Tình trạng + khách xuống
  // bảng Lọc nâng cao — ba tiêu chí ghép VÀ, đều lọc ở máy chủ (`routers/khuon_be.py`: `loc` +
  // `loc_them`). Đổi `key` ở đây là phải đổi cả tên tham số bên đó.
  facet: { key: "loai", values: mapOpt(LOAI_KHUON) },
  locNangCao: [
    // `size: 200` = trần của nền danh mục, cùng lý do với ô Khách hàng trong drawer bên dưới.
    { key: "khach_hang_id", label: "Khách hàng", type: "ref-search", refPrefix: "/api/customers",
      refParams: { size: 200 } },
    { key: "tinh_trang", label: "Tình trạng", type: "select", options: mapOpt(TINH_TRANG_KHUON) },
    // Khớp CHỨA ở máy chủ (`khuon_be_repo.extra_conds`): số kệ gõ tự do, người tìm chỉ nhớ "B3".
    { key: "so_ke", label: "Số kệ", type: "text", placeholder: "Vd: B3" },
  ],
  // Ô tìm quét cả tên khách + số kệ (`khuon_be_repo._loc_q`) — nói ra, không thì chẳng ai thử.
  timGoiY: "Tìm mã / tên / khách / số kệ…",
  columns: [
    { key: "khach_hang_ten", label: "Khách hàng",
      render: (r) => (r.khach_hang_ten ? String(r.khach_hang_ten) : "") },
    { key: "loai", label: "Loại", render: (r) => (r.loai ? lbl(LOAI_KHUON)(r.loai) : "") },
    { key: "so_ke", label: "Số kệ", render: (r) => (r.so_ke ? String(r.so_ke) : "") },
    // 🔴 Cột "Ngày có khuôn" ĐÃ GỠ (mg `0293`, 10/09/2026) — kho khuôn nay KHÔNG còn ô ngày nào.
    // Ngày dự kiến không cắm vào phép tính nào (xem `docs/DB_SCHEMA.md` mục `khuon_be`), chỉ bắt
    // người khai bịa một con số rồi để đó lạc hậu. "Đang đặt làm" ở cột Tình trạng là đủ.
    { key: "tinh_trang", label: "Tình trạng", render: (r) => lbl(TINH_TRANG_KHUON)(r.tinh_trang) },
  ],
  fields: [
    // Hai ô này là HAI CHIỀU LỌC của ô chọn dao ở bước lệnh sản xuất. Khai đủ thì người cấu hình
    // lệnh mở ra chỉ thấy vài con dao đúng khách, đúng loại; bỏ trống thì họ phải lội cả kho.
    // `size: 200` = trần của nền danh mục. Mặc định chỉ lấy trang đầu, mà ô chọn khách thiếu dòng
    // thì người ta tưởng chưa có khách đó rồi bỏ trống — đúng thứ làm chiều lọc này vô dụng.
    { key: "khach_hang_id", label: "Khách hàng", type: "ref", refPrefix: "/api/customers",
      refParams: { size: 200 }, group: "Nhận diện" },
    { key: "loai", label: "Loại", type: "select", group: "Nhận diện",
      options: mapOpt(LOAI_KHUON) },
    { key: "so_ke", label: "Số kệ / vị trí lưu", type: "text", group: "Lưu trữ" },
    // Ô ngày đi kèm ĐÃ GỠ cùng mg `0293`: tình trạng là thứ DUY NHẤT kho khuôn nói về "dao đã có
    // trong tay chưa", và nó có người chịu trách nhiệm cập nhật — khác hẳn một ngày khai một lần.
    { key: "tinh_trang", label: "Tình trạng", type: "select", group: "Lưu trữ",
      options: mapOpt(TINH_TRANG_KHUON), default: "dang_dung"},
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Lưu trữ" },
  ],
};

// ── Đơn vị & quy đổi ─────────────────────────────────────────────────────────────
// Ba bước, không hơn: tạo đơn vị A, tạo đơn vị B, khai "1 A = n B". Mọi khái niệm khác (loại đo,
// đơn vị chuẩn, ngày hiệu lực) là chuyện nội bộ — không phơi ra màn khai.
export const CFG_DON_VI: CatalogConfig = {
  title: "Đơn vị & quy đổi",
  moduleQuyen: "dm_don_vi",
  enableImport: true,
  prefix: "/api/don-vi",
  nhatKyLoai: "don_vi_do",
  softDelete: true,
  // Tạo xong giữ drawer mở để khai quy đổi ngay — khối quy đổi phải có id mới gắn vào được.
  moLaiSauKhiTao: true,
  columns: [
    {
      key: "quy_doi_text",
      label: "Quy đổi",
      // Loại của từng mảnh do SERVER trả (`quy_doi_chips`), màn này chỉ tô màu. Bản trước tự tách
      // `quy_doi_text` rồi đoán loại bằng cách dò tên biến ghi cứng — mà server đã đổi mã biến sang
      // nhãn tiếng Việt trước khi trả, nên "bài in = Tờ vào máy + 2000" hiện xám như một hệ số.
      render: (r) => {
        const chips = Array.isArray(r.quy_doi_chips)
          ? (r.quy_doi_chips as { text?: string; loai?: string }[])
          : [];
        if (chips.length === 0) {
          return <span className="badge-sem badge-sem--muted">Chưa khai báo</span>;
        }
        return (
          <div className="rc__formula-chips">
            {chips.map((c, i) => (
              <span
                key={i}
                // Mảnh "là công thức" nói bằng RUST — accent DUY NHẤT của app. Bản trước dùng
                // `--dynamic` tô #1d4ed8, tức dựng thêm một accent xanh thứ hai chỉ cho một cột.
                className={c.loai === "cong_thuc" ? "badge-sem badge-sem--rust" : "rc__formula-pill"}
              >
                {c.text}
              </span>
            ))}
          </div>
        );
      },
    },
    // Cột "Lưu ý" (`canh_bao`) GỠ 18/09/2026 theo chủ: phần lớn dòng chỉ lặp lại "Chưa khai" mà
    // cột Quy đổi đã nói. Server vẫn trả `canh_bao`, chỉ màn này thôi hiện.
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "ghi_chu", label: "Ghi chú", type: "text" },
    // GỠ 06/09/2026: ô "Trạm trên dòng giấy". Nó là lớp trung gian cho một thứ không cần trung
    // gian — dòng giấy có ĐÚNG 5 chặng đóng cứng trong engine, cờ này chỉ cho phép ĐỔI TÊN chặng
    // chứ không thêm được chặng thứ 6. Đổi lại, ai khai đơn vị (kho, mua hàng) cũng phải hiểu
    // dòng giấy để không gắn nhầm cờ. Nay 5 chặng nằm thẳng ở ô Đơn vị vào/ra của màn Công đoạn —
    // hỏi đúng người, đúng lúc. Danh mục đơn vị giữ NGUYÊN mọi dòng (kg · ram · thùng · m²…),
    // chỉ mất cái cờ. Cột `don_vi_do.tram_dong_giay` còn trong DB nhưng không ai đọc nữa.
  ],
  // Quy đổi khai NGAY TẠI ĐÂY, dưới ô Ghi chú — một chỗ nhập, không màn thứ hai.
  renderExtra: (_form, existing) => <QuyDoiCuaDonVi donVi={existing} />,
};

export const CFG_XE: CatalogConfig = {
  title: "Xe giao hàng",
  moduleQuyen: "dm_xe",
  enableImport: true,
  prefix: "/api/xe",
  nhatKyLoai: "xe",
  // Khoá nghiệp vụ của xe LÀ BIỂN SỐ. Gọi nó là "Mã" + điền sẵn "MA-0001" thì người khai gõ biển
  // số vào ô Tên rồi để nguyên mã tự sinh — đã dính đúng lỗi đó ngay lần khai đầu tiên.
  nhanMa: "Biển số",
  khongGoiYMa: true,
  // Xoá MỀM: xe bán đi vẫn phải giữ tên cho những chuyến nó đã chạy — xoá hẳn là làm mồ côi
  // `delivery_trips.vehicle_id` của cả lịch sử.
  softDelete: true,
  columns: [
    { key: "tai_trong", label: "Tải trọng", render: (r) =>
        r.tai_trong != null ? `${Number(r.tai_trong).toLocaleString("vi-VN")} tấn` : "" },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    // MỨC KHOÁN KM — ô quan trọng nhất của màn này: nó quyết định xe chạy một chuyến ra bao nhiêu
    // tiền. BẮT BUỘC từ 14/09/2026 (máy chủ chặn): trước đó để trống được và xe trống âm thầm ăn
    // đơn giá phẳng của phòng mà không màn nào hiện số đó. Mức tạo ở Cấu hình lương → Khoán km
    // giao hàng.
    // ⚠️ `hint` của ô `ref-search` được `CatalogDrawer` dùng LÀM PLACEHOLDER — viết dài là cả câu
    // hướng dẫn tràn vào trong ô, trông như đã nhập sẵn. Giữ ngắn đúng một dòng.
    { key: "muc_khoan_km_id", label: "Mức khoán km", type: "ref-search",
      refPrefix: "/api/giao-hang/muc-khoan-km", required: true, group: "Thông tin",
      hint: "Chọn mức…" },
    { key: "tai_trong", label: "Tải trọng (tấn)", type: "number", group: "Thông tin",
      hint: "Chỉ để đối chiếu — giá km do MỨC ở trên quyết." },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Thông tin" },
  ],
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
  "thanh-pham": CFG_THANH_PHAM,
  "khuon-be": CFG_KHUON_BE,
  "xe": CFG_XE,
};
