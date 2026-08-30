// Config 10 danh mục cho RebuildCatalogPage (xem REBUILD_CONFIGS cuối file). Field có `group` (section drawer),
// `showIf` (ẩn/hiện theo kiểu), `ref`/`ref-multi` (chọn theo TÊN thay vì gõ id),
// `default` (prefill khi tạo), `jsonKey` (lưu lồng vào fields_theo_loai).
// Enum hiển thị bằng thuật ngữ in ấn thuần Việt — dùng chung 1 bảng nhãn cho cả dropdown lẫn cột.
import { useEffect, useState } from "react";
import type { CatalogConfig, ChuanBiKhoanRow } from "./RebuildCatalogPage";
import { ClockIcon, isMayIn, tongChuanBi } from "./RebuildCatalogPage";
import { nhanTo } from "./danh-muc/nhanTo";
import { QuyDoiCuaDonVi } from "./QuyDoiCuaDonVi";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ApiError, authed } from "../api/client";
import { crud, trangThaiMay, type Row, type TrangThaiMay } from "../api/rebuildCatalog";

// ── Bảng nhãn thuần Việt (in ấn) — 1 nguồn cho options + column render ──────────
type Lbls = Record<string, string>;
const mapOpt = (m: Lbls) => Object.entries(m).map(([value, label]) => ({ value, label }));
const lbl = (m: Lbls) => (v: unknown) => (v == null || v === "" ? "" : (m[String(v)] ?? String(v)));


const NHOM_CD: Lbls = { prepress: "Chế bản", print: "In", finishing: "Gia công sau in", other: "Dịch vụ khác" };

// Dụng cụ DÙNG CHUNG mà bước phải mượn từ kho khuôn — khớp `cong_doan.TOOLING_TYPE` ở backend
// (service chặn giá trị ngoài danh sách). "Bản kẽm" đã gỡ 16/08/2026: kẽm là vật tư tiêu hao,
// không có dòng nào trong kho khuôn để trỏ tới — xem lý do đầy đủ ở `models/cong_doan.TOOLING_TYPE`.
const TOOLING_TYPE: Lbls = {
  khuon_be: "Khuôn bế",
  khuon_ep: "Khuôn ép nhũ / dập nổi",
  khung_lua: "Khung lụa",
};

// NHÃN đọc cho mã đơn vị hay gặp ở công đoạn — KHÔNG còn là danh sách chọn (11/08/2026).
//
// Ô đơn vị vào/ra nay là picker vào danh mục Đơn vị & quy đổi (`F_DON_VI`): xưởng khai đơn vị nào
// thì công đoạn chọn được đơn vị đó, khỏi sửa code. Trước đây đây là 5 mã CỨNG phải khớp
// `cong_doan.DON_VI_DONG_GIAY` bên backend — chính nó bắt bước ghi kẽm phải bỏ trống ô đơn vị.
//
// Năm mã đầu là TRẠM trên dòng giấy (backend đánh cờ `don_vi_do.tram_dong_giay`), chảy một chiều:
//   tờ nguyên ──(số mảnh xả)──▶ tờ in ──(con/tờ)──▶ con ──▶ thành phẩm
//                                     └─(gấp)────▶ tay sách ──(bắt tay/vào keo)──▶ thành phẩm
// `con` KHÁC `thành phẩm`: sách gấp tay thì nhiều tờ mới gom thành MỘT cuốn. Hệ số các cầu này
// SUY ở `_he_so_cau` từ quy cách lệnh, không khai tay.
//

// 5 TRẠM của dòng giấy — ô chọn ở màn Đơn vị, khớp `models/don_vi_do.TRAM_DONG_GIAY` bên backend
// (service chặn giá trị lạ). Đây là menu ĐÓNG thật sự: engine chạy chuỗi bù hao theo đúng 5 mức
// này, thêm mức thứ 6 là phải khai cả hệ số cầu của nó trong code.
const TRAM_DONG_GIAY: Lbls = {
  to_nguyen: "Tờ nguyên (giấy mua về)",
  to: "Tờ in",
  con: "Con (mảnh bế ra)",
  tay: "Tay sách",
  cai: "Thành phẩm",
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
 *  `active: true` — không lọc thì picker mời cả đơn vị đã ngừng dùng, chọn xong bấm Lưu mới ăn lỗi. */
const F_DON_VI = {
  type: "ref-search-ma" as const,
  refPrefix: "/api/don-vi",
  refParams: { active: true },
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
// Nhãn đơn vị tốc độ ở BẢNG DANH SÁCH: server đã tra sẵn tên thật (`don_vi_toc_do_ten`, xem
// `may_thiet_bi_service.gan_ten_don_vi`) nên chỉ việc đọc.
//
function nhanDonViTocDo(r: Row): string {
  const ten = String(r.don_vi_toc_do_ten ?? "").trim();
  if (ten) return `${ten}/h`;
  const ma = String(r.don_vi_toc_do ?? "").trim();
  if (!ma) return "";
  return `${ma.endsWith("_gio") ? ma.slice(0, -4) : ma}/h`;
}

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
    { key: "thong_so_kho", label: "Khổ máy & Vùng in",
      render: (r) => {
        // `Row` là bản ghi động (`unknown` mọi field) nên phải ép chuỗi trước khi render, và guard
        // phải ép Boolean — `unknown && JSX` không phải ReactNode.
        const so = (v: unknown) => (v == null || v === "" ? "?" : String(v));
        const isMayInType = isMayIn(String(r.loai_may ?? ""));
        const hasKhoMax = Boolean(r.kho_max_rong || r.kho_max_dai);
        const hasKem = isMayInType && Boolean(r.kho_kem_rong || r.kho_kem_dai);
        const hasVungIn = isMayInType && Boolean(r.vung_in_rong || r.vung_in_dai);
        if (!hasKhoMax && !hasKem && !hasVungIn) return "";
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "2px", fontSize: "12.5px" }}>
            {hasKhoMax && (
              <div>
                <span style={{ fontWeight: 600 }}>{so(r.kho_max_rong)}×{so(r.kho_max_dai)}</span>
                <span style={{ fontSize: "11px", color: "var(--ash, #8a8577)", marginLeft: "4px" }}>(giấy max)</span>
              </div>
            )}
            {hasKem && (
              // Kẽm + Vùng in TÁCH 2 dòng riêng (trước gộp 1 dòng nối "•") — cột chỉ ~87px,
              // nối chung dễ vỡ dòng giữa số làm chiều cao hàng nhảy lung tung giữa các máy.
              <div style={{ fontSize: "11px", color: "var(--charcoal, #374151)" }}>Kẽm: {so(r.kho_kem_rong)}×{so(r.kho_kem_dai)}</div>
            )}
            {hasVungIn && (
              <div style={{ fontSize: "11px", color: "var(--charcoal, #374151)" }}>In: {so(r.vung_in_rong)}×{so(r.vung_in_dai)}</div>
            )}
          </div>
        );
      }
    },
    { key: "chua_le", label: "Chừa lề tờ in",
      render: (r) => {
        if (!isMayIn(String(r.loai_may ?? ""))) return "";
        const parts = [];
        if (r.nhip_giay_mm) parts.push(`Nhíp ${r.nhip_giay_mm}mm`);
        if (r.le_hong_mm) parts.push(`Lề ${r.le_hong_mm}mm`);
        if (r.duoi_thang_mau_mm) parts.push(`Đuôi ${r.duoi_thang_mau_mm}mm`);
        if (parts.length === 0) return "";
        // MỖI phần một dòng riêng (trước nối "•" chung 1 dòng) — cột chỉ ~87px, 3 phần nối
        // chung dễ vỡ dòng giữa số làm chiều cao hàng nhảy lung tung giữa các máy.
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "1px", fontSize: "11.5px", color: "var(--charcoal, #4b5563)", lineHeight: "1.4" }}>
            {parts.map((p) => <div key={p}>{p}</div>)}
          </div>
        );
      }
    },
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
              <div style={{ fontSize: "11.5px", color: "var(--rust, #c5400a)", fontWeight: 500, display: "flex", alignItems: "center" }}>
                <ClockIcon size={12} /> Chuẩn bị: {totalMakeready} phút
              </div>
            )}
          </div>
        );
      }
    },
    { key: "so_nhan_cong", label: "Kíp chuẩn",
      render: (r) => `${Math.max(1, Math.ceil(Number(r.so_nhan_cong) || 1))} người` },
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
  // Ô công thức duy nhất của màn Máy ra LƯỢNG (theo đơn vị tốc độ), không ra tiền — nhãn tab mặc
  // định "Công thức tính giá" sẽ mời gõ sai thứ vào đó.
  nhanTabCongThuc: "Cách đo lượng",
  // Khai máy là form DÀI (7 nhóm). Cuộn một mạch thì khối Lịch bảo trì nằm tít dưới đáy, ai vào
  // sửa chu kỳ cũng phải lướt qua cả đống ô khổ giấy không liên quan. Chia 3 tab theo việc.
  tabsKhai: [
    { id: "chung", label: "Thông tin chung", groups: ["Thông tin chung"] },
    { id: "ky-thuat", label: "Thông số kỹ thuật",
      groups: ["Khổ kẽm & Vùng in", "Thông số chừa lề tờ in", "Khổ giấy máy nhận",
               "Tốc độ & Vận hành", "Ghi chú"] },
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
    // ── 2. Khổ kẽm & Vùng in (chỉ Máy in) ───────────────────────────────────
    { key: "kho_kem_rong", label: "Khổ kẽm — rộng (mm)", type: "number", group: "Khổ kẽm & Vùng in",
      showIf: (f) => isMayIn(f.loai_may) },
    { key: "kho_kem_dai", label: "Khổ kẽm — dài (mm)", type: "number", group: "Khổ kẽm & Vùng in",
      showIf: (f) => isMayIn(f.loai_may) },
    { key: "vung_in_rong", label: "Vùng in max — rộng (mm)", type: "number", group: "Khổ kẽm & Vùng in",
      showIf: (f) => isMayIn(f.loai_may) },
    { key: "vung_in_dai", label: "Vùng in max — dài (mm)", type: "number", group: "Khổ kẽm & Vùng in",
      showIf: (f) => isMayIn(f.loai_may) },
    // ── 3. Thông số chừa lề tờ in (chỉ Máy in) ─────────────────────────────
    { key: "nhip_giay_mm", label: "Nhíp giấy (mm)", type: "number", group: "Thông số chừa lề tờ in",
      showIf: (f) => isMayIn(f.loai_may) },
    { key: "le_hong_mm", label: "Lề hông (mm)", type: "number", group: "Thông số chừa lề tờ in",
      showIf: (f) => isMayIn(f.loai_may) },
    { key: "duoi_thang_mau_mm", label: "Đuôi + thanh màu (mm)", type: "number", group: "Thông số chừa lề tờ in",
      showIf: (f) => isMayIn(f.loai_may) },
    // ── 4. Khổ giấy máy nhận ─────────────────────────────────────────────────
    { key: "kho_min_rong", label: "Khổ giấy min — rộng (mm)", type: "number", group: "Khổ giấy máy nhận" },
    { key: "kho_min_dai", label: "Khổ giấy min — dài (mm)", type: "number", group: "Khổ giấy máy nhận" },
    { key: "kho_max_rong", label: "Khổ giấy max — rộng (mm)", type: "number", group: "Khổ giấy máy nhận" },
    { key: "kho_max_dai", label: "Khổ giấy max — dài (mm)", type: "number", group: "Khổ giấy máy nhận" },
    // ── 5. Tốc độ & Năng suất vận hành ───────────────────────────────────────
    { key: "toc_do", label: "Tốc độ trung bình", type: "number", group: "Tốc độ & Vận hành" },
    { key: "don_vi_toc_do", label: "Đơn vị tốc độ", type: "don_vi_toc_do",
      refPrefix: "/api/don-vi", refParams: { active: true, size: 200 },
      group: "Tốc độ & Vận hành", default: "to_gio" },
    // Ô ra LƯỢNG, KHÔNG ra tiền và KHÔNG ra giờ: nó chỉ trả lời "bước này bằng bao nhiêu <đơn vị
    // tốc độ>", rồi engine mới chia tốc độ ra phút. Đứng ngay dưới ô Đơn vị tốc độ vì đó là đơn vị
    // nó phải ra. `loaiO: "quy_doi"` ⇒ chip có `sl_vao`/`sl_ra` và KHÔNG có đơn giá — ô này không
    // được phép nhắc tới tiền.
    { key: "cong_thuc_luong", label: "Cách đo lượng theo đơn vị tốc độ", type: "formula",
      loaiO: "quy_doi", group: "Tốc độ & Vận hành",
      hint: "Bỏ trống = hệ tự quy đổi. vd máy đo m²/giờ: sl_vao * dai_in * rong_in · máy 5 màu chạy 2 lượt: sl_vao * so_mau / 5" },
    { key: "toc_do_min", label: "Tốc độ tối thiểu", type: "number", group: "Tốc độ & Vận hành" },
    { key: "toc_do_max", label: "Tốc độ tối đa", type: "number", group: "Tốc độ & Vận hành" },
    { key: "so_nhan_cong", label: "Số người vận hành tiêu chuẩn", type: "number", required: true,
      default: 1, group: "Tốc độ & Vận hành" },
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
      don_vi_toc_do: body.toc_do ? (body.don_vi_toc_do || "to_gio") : null,
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
  // Màn này có HAI ô công thức, một ra TIỀN một ra LƯỢNG ⇒ TÁCH hai tab riêng: mỗi ô tự khai
  // `nhanTab` của nó (Công thức tính giá ↔ Công thức sản lượng ra), nên KHÔNG dùng nhãn tab gộp
  // `nhanTabCongThuc` — nhét chung một tab là mời gõ nhầm công thức tiền vào ô ra lượng.
  facet: { key: "nhom", values: mapOpt(NHOM_CD) },
  columns: [
    { key: "nhom", label: "Giai đoạn", render: (r) => lbl(NHOM_CD)(r.nhom) },
    // Nhìn ra ngay bước nào ĐỔI ĐƠN VỊ, và bước nào để trống (không nằm trên dòng giấy).
    // Tên đọc từ DANH MỤC (server gán) — không có bảng nhãn thứ hai trong code. Chưa khai đơn vị
    // thì hiện "—", đúng nghĩa "bước không chạm giấy", chứ không bịa tên.
    { key: "don_vi_vao", label: "Đơn vị", render: (r) => {
        const vao = r.don_vi_vao_ten ?? r.don_vi_vao;
        const ra = r.don_vi_ra_ten ?? r.don_vi_ra;
        return vao || ra ? `${String(vao ?? "—")} → ${String(ra ?? "—")}` : "—";
      } },
    { key: "kieu_bu_hao", label: "Bù hao", render: (r) =>
        r.kieu_bu_hao === "co_dinh" ? `Cố định ${r.so_to_bu_hao ?? 50} tờ` : lbl(KIEU_BU_HAO)(r.kieu_bu_hao ?? "khong") },
    // Nhìn ra công đoạn nào chưa khai số cho Lệnh sản xuất (giống cột Tốc độ bên màn Máy).
    // Ba thứ ĐI CÙNG NHAU ở một cột vì chúng cùng trả lời "bước này ăn bao nhiêu thời gian, và có
    // vướng dụng cụ không" — tách ba cột thì bảng dài mà vẫn phải đọc cả ba mới hiểu.
    { key: "dau_viec_dinh_muc", label: "Ràng buộc",
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
    { key: "department_id", label: "Phòng ban / Tổ phụ trách", type: "ref", refPrefix: "/api/cong-doan/phong-ban", group: "Thông tin" },

    // ── Nguồn nuôi thẳng thời lượng bước ở Lệnh sản xuất ──────────────────────────────────────
    { key: "requires_tooling", label: "Bước này cần khung, khuôn", type: "checkbox",
      group: "Khuôn & dụng cụ",},
    { key: "tooling_type", label: "Loại khuôn", type: "select", group: "Khuôn & dụng cụ",
      options: mapOpt(TOOLING_TYPE), showIf: (f) => !!f.requires_tooling },
    { key: "dau_viec_dinh_muc", label: "Đầu việc và định mức của tổ", type: "dau-viec-dinh-muc",
      refPrefix: "/api/cong-doan/dau-viec", group: "Lệnh sản xuất" },
    // Chặn gán máy SAI LOẠI ở bài ghép (vd Ghi kẽm CTP không cho máy Bế). Lưu mảng TÊN nhóm máy.
    { key: "nhom_may_cho_phep", label: "Máy làm được công đoạn này", type: "nhom_may-multi",
      refPrefix: "/api/nhom-may", group: "Lệnh sản xuất" },

    // CHỈ TÍNH THEO CÔNG THỨC: đã bỏ ô 'Cách tính giá' / 'Đơn giá' / 'Bậc kích thước'.
    // Đơn giá nhập per-phiếu (mỗi dòng phiếu tính giá tự mang don_gia); công đoạn chỉ khai CÔNG THỨC.
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá",
      nhanTab: "Công thức tính giá" },
    // ── Đơn vị đứng TRƯỚC Bù hao: nó quyết định bù hao được tra theo số gì (tờ hay con) ────────
    // Chọn từ DANH MỤC Đơn vị & quy đổi (không còn 5 mã cứng): bước không chạm giấy khai đơn vị
    // THẬT của nó — ghi kẽm `bài in → bản kẽm` — thay vì phải bỏ trống như trước 11/08/2026.
    { key: "don_vi_vao", label: "Đơn vị đầu vào", ...F_DON_VI, group: "Đơn vị", default: "to" },
    { key: "don_vi_ra", label: "Đơn vị đầu ra", ...F_DON_VI, group: "Đơn vị", default: "to" },
    // HỆ SỐ vào→ra KHÔNG còn khai tay ở đây (gỡ `he_so_ngoai_dong` 20/08/2026). Với bước ngoài
    // dòng giấy nó lấy TỪ cầu quy đổi `vào → ra` ở module Đơn vị & quy đổi (vd "1 bài in = 4 bản
    // kẽm") — một nguồn chân lý, không đẻ nguồn thứ hai gõ đè. Thiếu cầu thì bước lệnh báo đỏ chứ
    // không đoán. Trên dòng giấy hệ số vẫn suy từ quy cách LỆNH (con/tờ · mảnh xả · tay).
    // SẢN LƯỢNG RA của bước NGOÀI dòng giấy (mg `0214`): cái này nói bước RA bao nhiêu, còn vế VÀO
    // suy ngược từ RA qua cầu quy đổi + bù hao.
    //
    // Trước 17/08/2026 số này lấy từ công thức của ĐƠN VỊ RA (`don_vi_do.cong_thuc`, đã gỡ) — sai
    // chủ sở hữu: hai công đoạn cùng đo bằng `kem` có thể ra số khác nhau, mà công thức treo ở đơn
    // vị thì cả hai buộc dùng chung.
    //
    // KHÔNG `showIf`: form không biết đơn vị nào là trạm dòng giấy (cờ đó nằm ở danh mục Đơn vị,
    // server giữ), nên đoán ở đây là đoán sai. Engine tự bỏ qua với bước trên dòng giấy — số của
    // chúng đến từ chuỗi bù hao ngược. Hint nói rõ phạm vi thay cho việc ẩn/hiện.
    { key: "cong_thuc_san_luong", label: "Công thức sản lượng ra", type: "formula",
      loaiO: "quy_doi", group: "Đơn vị", nhanTab: "Công thức sản lượng ra",
      hint: "CHỈ cho bước ngoài dòng giấy (ghi kẽm, ép nhũ…). vd Ghi kẽm: so_kem. Bước trên dòng giấy lấy số từ chuỗi bù hao nên khai ở đây không ai đọc." },
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
    body.department_id = body.department_id ?? null;
    body.dau_viec_dinh_muc = body.dau_viec_dinh_muc ?? [];
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

export const CFG_CONG_VIEC_KHOAN: CatalogConfig = {
  title: "Công việc khoán",
  moduleQuyen: "dm_cong_viec_khoan",
  enableClone: true,
  enableImport: true,
  prefix: "/api/cong-viec-khoan",
  nhatKyLoai: "cong_viec_khoan",
  // Xoá MỀM: nút "Xóa" hỏi server "còn ai dùng không" rồi tự chọn kết cục — chưa ai dùng thì xoá
  // hẳn, còn định mức đầu việc / bước lệnh đang trỏ tới thì chỉ ngừng dùng (tiền của lệnh đã phát
  // KHÔNG được xê dịch). Mục đã ngừng xem lại ở công tắc trên dải lọc.
  softDelete: true,
  // Mã do MÁY cấp (`KH-####`) ⇒ ẩn ô Mã lúc tạo. Xưởng gọi việc khoán bằng TÊN ("bế tay", "vào keo
  // gáy vuông"), chưa ai từng gọi bằng mã — bắt gõ mã là thêm một ô không ai đọc lại.
  autoCode: true,
  // Ô công thức của màn này ra LƯỢNG khoán, không ra tiền (tiền = lượng × đơn giá, engine nhân).
  nhanTabCongThuc: "Cách đo lượng",
  // Tab lọc = TỔ. Không khai `values` cứng: tổ do người dùng dựng ở cây tổ chức, mọi giá trị đều
  // đến từ dữ liệu (`dynamic`) — khai cứng là bỏ sót đúng những tổ xưởng mới mở.
  facet: { key: "to", values: [], dynamic: true },
  columns: [
    { key: "group_name", label: "Tổ", render: (r) => nhanTo(r.group_name) },
    // Đơn vị lưu MÃ, hiện TÊN (server gán `don_vi_ten`) — `m2` không ai đọc thành "m²". Mã lạ (dòng
    // cũ mang đơn vị ngoài danh mục) thì hiện nguyên mã kèm dấu hiệu: nó là việc phải sửa, không
    // phải chuyện im lặng bỏ qua.
    { key: "unit", label: "Đơn vị", render: (r) => {
        const ma = r.unit ? String(r.unit) : "";
        if (!ma) return "";
        if (r.don_vi_ten) return <span className="rc__formula-pill">{String(r.don_vi_ten)}</span>;
        return (
          <span className="badge-sem badge-sem--muted" title="Đơn vị này không có trong danh mục Đơn vị & quy đổi">
            {ma}
          </span>
        );
      } },
    { key: "unit_price", label: "Đơn giá",
      render: (r) => (Number(r.unit_price) ? `${Number(r.unit_price).toLocaleString("vi-VN")} đ` : "") },
    { key: "note", label: "Ghi chú", render: (r) => (r.note ? String(r.note) : "") },
  ],
  fields: [
    // Tổ lấy từ CÙNG endpoint với ô "Tổ phụ trách" của Công đoạn — nút LÁ trong khối Sản xuất. Một
    // nguồn thì đầu việc khoán và công đoạn không bao giờ trỏ hai danh sách tổ khác nhau (mà lệch
    // là bước lệnh không tìm thấy đầu việc nào của tổ mình).
    { key: "department_id", label: "Tổ làm việc này", type: "ref",
      refPrefix: "/api/cong-doan/phong-ban", required: true, group: "Thông tin",
      hint: "Bước lệnh của tổ này sẽ chọn được đơn giá vừa khai." },
    { key: "unit", label: "Đơn vị tính khoán", ...F_DON_VI, required: true, group: "Đơn giá" },
    { key: "unit_price", label: "Đơn giá (đ)", type: "number", required: true, group: "Đơn giá",
      hint: "Tiền cho MỘT đơn vị ở trên. Vd bế tay 400 đ/tờ." },
    // Cách đo LƯỢNG mà đơn giá nhân vào. Bỏ trống thì hệ tự quy đổi SL của bước sang đơn vị này
    // bằng cầu quy đổi — chỉ khai khi cầu đó không có, hoặc có mà việc này đo theo cách khác.
    // Ghi chú quan trọng cho người khai: sửa ô này KHÔNG đổi tiền của lệnh đã phát (bước ghim ảnh
    // chụp lúc chọn đầu việc) — nói ra để không ai tưởng vá xong là số cũ tự đúng theo.
    { key: "cong_thuc_luong", label: "Cách đo lượng khoán", type: "formula", loaiO: "quy_doi",
      group: "Đơn giá",
      hint: "Bỏ trống = hệ tự quy đổi. vd khoán đ/cuốn mà bước đếm tay: sl_ra. Lệnh ĐÃ phát giữ cách đo cũ." },
    { key: "note", label: "Ghi chú", type: "text", group: "Thông tin" },
  ],
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
    // Hai ô công thức TÁCH HAI TAB riêng (`nhanTab`): "Tính giá" ra tiền, "Tính lượng" ra lượng —
    // hai câu hỏi khác nhau, đứng chung một tab dễ gõ nhầm công thức tiền vào ô lượng.
    { key: "cong_thuc_gia", label: "Công thức tính giá", type: "formula", group: "Giá",
      nhanTab: "Công thức tính giá" },
    // Ô thứ hai ra LƯỢNG, không ra tiền. Nó là thứ DUY NHẤT còn đổi được tờ → kg cho bảng cân đối
    // vật tư sau khi gỡ cặp quy đổi động (mg 0198); mg 0197 đã điền sẵn cho giấy bán theo cân, tới
    // nay chưa có ô nào để người dùng nhìn thấy hay sửa. `loaiO: "quy_doi"` ⇒ chip có `sl_vao`/
    // `sl_ra` và KHÔNG có đơn giá — ô này không được phép nhắc tới tiền.
    { key: "cong_thuc_luong", label: "Công thức tính lượng", type: "formula", loaiO: "quy_doi",
      group: "Giá", nhanTab: "Công thức tính lượng",
      hint: "vd: dinh_luong * dai_nguyen * rong_nguyen * to_nguyen — ra số kg giấy phải mua" },
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
  // Vật tư CHỈ còn 1 tab công thức, ra LƯỢNG (tiêu hao cho kế hoạch vật tư). Ô "Công thức tính
  // giá" đã ẩn khỏi drawer (xưởng không thêm dòng mực/màng/keo rời vào phiếu tính giá) — nhãn tab
  // đổi cho khớp, đừng để chữ "tính giá" mời người ta gõ công thức tiền vào đây.
  nhanTabCongThuc: "Công thức tính lượng",
  // Xoá MỀM: nút "Xóa" hỏi server "còn ai dùng không" rồi tự chọn kết cục — chưa ai dùng thì
  // xoá hẳn, còn nơi dùng thì chỉ ngừng dùng. Mục đã ngừng xem lại ở công tắc trên dải lọc.
  softDelete: true,
  columns: [
    { key: "don_vi_gia", label: "ĐVT", render: (r) => dvCell(r) },
    { key: "don_gia", label: "Đơn giá", render: (r) => (Number(r.don_gia) ? Number(r.don_gia).toLocaleString("vi-VN") : "") },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    // Quy cách đóng gói (đơn vị đóng gói + hệ số) ĐÃ BỎ 10/08/2026: khai quy đổi ở hai nơi là bắt
    // người dùng nhớ luật vô ích. Cần "1 thùng keo = 20 kg" thì khai thẳng đơn vị đó trong danh
    // mục Đơn vị & quy đổi rồi chọn ở ô ĐVT — một nơi duy nhất cho mọi quy đổi.
    { key: "don_vi_gia", label: "Đơn vị tính (ĐVT)", ...F_DON_VI, group: "Thông số" },
    // Đơn giá chốt ở danh mục — engine phơi thành ĐÚNG MỘT biến `don_gia` cho công thức vật tư
    // (đã quy về đơn vị cơ sở; `don_gia_kg`/`don_gia_m2` gỡ 11/08/2026 vì trùng nghĩa).
    { key: "don_gia", label: "Đơn giá", type: "number", group: "Giá", hint: "Đơn giá theo ĐVT đã chọn — dùng làm biến don_gia trong công thức" },
    // Ô "cong_thuc_gia" (công thức ra TIỀN cho dòng vật tư trên phiếu tính giá) ĐÃ ẨN khỏi drawer
    // theo yêu cầu — cột DB, dữ liệu cũ và đường engine (`thanh_phan_engine`/`tinh_gia_service`)
    // vẫn nguyên; chỉ không cho khai mới ở đây. Cần mở lại thì thêm field formula `cong_thuc_gia`
    // với `nhanTab: "Công thức tính giá"`.
    // Lượng tiêu hao của CHÍNH món này. Đường ưu tiên số 1 của `LsxService._luong_vat_tu`: khai ở
    // đây thì keo thôi ăn ké "cách đo" của đơn vị `kg` — thứ đang dùng chung cho cả mực lẫn keo dù
    // hai món tiêu hao khác hẳn nhau.
    { key: "cong_thuc_luong", label: "Công thức tính lượng", type: "formula", loaiO: "quy_doi",
      group: "Giá",
      hint: "vd: sl_ra * 0.02 — lượng tiêu hao của bước, theo ĐVT đã chọn" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
    // NVL thay thế (mục 5 "Bảng định mức", mg 0239) — tra cứu/gợi ý khi thiếu hàng, MỘT CHIỀU.
    { key: "thay_the_ids", label: "Vật tư thay thế", type: "self-ref-multi",
      refPrefix: "/api/vat-lieu-kho/vat-tu-in-an", group: "Ghi chú",
      hint: "Vật tư khác dùng thay được món này khi thiếu hàng. Chỉ để tra cứu, không tự suy chiều ngược lại." },
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
  // Khai tay ĐƯỢC (nới 19/08/2026) — Bán hàng khai trước một món khách sắp đặt là chuyện thường.
  // Nhưng KHÔNG cho Xóa: dòng có thể đang có lô tồn hoặc phiếu đã ghi sổ, xoá là làm mồ côi;
  // ngừng dùng thì tắt ô Đang dùng. Máy chủ chặn song song, không chỉ giấu nút.
  khongXoa: true,
  softDelete: true,
  columns: [
    // CỘT + Ô "Khách hàng" ĐÃ GỠ HẲN (chủ 21/08/2026: "khách hàng mình lưu làm gì, mình không
    // dùng tới — thành phẩm này là một cái tên hàng mới, nêu chưa khai để tái sử dụng, tránh
    // phình lên"). Thành phẩm KHÔNG thuộc về ai nữa: hai khách đặt cùng tên dùng CHUNG một dòng.
    // Công tắc chia hai màn chuyển sang cột `la_thanh_pham` (mg 0228) — repo tự đóng dấu, người
    // dùng không khai, nên bỏ ô này không làm dòng mới rơi sang màn Vật tư.
    { key: "don_vi_gia", label: "ĐVT", render: (r) => dvCell(r) },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "don_vi_gia", label: "Đơn vị tính (ĐVT)", ...F_DON_VI, group: "Thông số",
      hint: "Lấy theo đơn vị trên dòng đơn hàng — sửa nếu kho đếm bằng đơn vị khác" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Ghi chú" },
  ],
};

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
    { key: "vi_tri", label: "Vị trí kho", type: "text", group: "Thông tin",
      hint: "Nơi đặt kho, vd: Tầng 1 — xưởng A" },
    { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Thông tin" },
  ],
  renderDeleteDialog: (row, ctx) => <KhoDeleteDialog row={row} {...ctx} />,
};

// ── Lý do & lỗi SX (§15) — danh mục thứ 12 ──────────────────────────────────────────────────
// Danh mục CHUẨN HOÁ mọi lý do/lỗi của phân hệ Thực hiện SX: batch hỏng · lỗi KCS · và các lý do
// vận hành (tạm dừng · bắt đầu trễ · điều chỉnh bàn giao · mở lại phân bổ…). Màn Thực hiện SX
// KHÔNG hard-code danh sách nào — mọi ô chọn đổ từ đây, lọc theo `nhom`. 8 nhóm khớp
// `models/san_xuat_ly_do.NHOM_LY_DO` (service chặn giá trị lạ): MENU ĐÓNG thật sự, thêm nhóm mới
// phải khai cả ở backend nên `facet.values` liệt kê CỨNG chứ không `dynamic`.
const NHOM_LY_DO: Lbls = {
  loi: "Lỗi / hỏng",
  tam_dung: "Tạm dừng",
  bat_dau_tre: "Bắt đầu trễ",
  lech_nhan_su: "Lệch nhân sự",
  thieu_vat_tu: "Thiếu vật tư",
  dieu_chinh_ban_giao: "Điều chỉnh bàn giao",
  mo_lai_phan_bo: "Mở lại phân bổ",
  dong_thieu: "Đóng thiếu TP",
};

export const CFG_LY_DO_SAN_XUAT: CatalogConfig = {
  title: "Lý do & lỗi SX",
  moduleQuyen: "dm_ly_do_san_xuat",
  enableImport: true,
  prefix: "/api/san-xuat-ly-do",
  nhatKyLoai: "san_xuat_ly_do",
  // Xoá MỀM ở service (`XOA_MEM`): batch/điều chỉnh bàn giao ghim ID thật, ngừng dùng thì lịch sử
  // vẫn tra ra nhãn. Nút "Xóa" của nền danh mục vì thế rơi về lối an toàn (kiểm-nơi-dùng 404 →
  // chỉ Ngừng dùng), mà backend cũng chỉ soft nên không sợ làm mồ côi FK.
  softDelete: true,
  autoCode: true,          // mã LD-#### sinh ngầm ở backend, ẩn ô nhập mã
  // Tab lọc = NHÓM (dùng-vào-việc-gì). Số trên mỗi tab do server đếm (`facets`).
  facet: { key: "nhom", values: mapOpt(NHOM_LY_DO) },
  columns: [
    { key: "nhom", label: "Nhóm", render: (r) => lbl(NHOM_LY_DO)(r.nhom) },
    { key: "ten", label: "Tên lý do / lỗi", render: (r) => (r.ten ? String(r.ten) : "") },
    { key: "mo_ta", label: "Mô tả", render: (r) => (r.mo_ta ? String(r.mo_ta) : "") },
  ],
  fields: [
    { key: "nhom", label: "Nhóm (dùng vào việc gì)", type: "select", required: true, group: "Thông tin",
      options: mapOpt(NHOM_LY_DO),
      hint: "Ô chọn ở màn Thực hiện SX lọc theo nhóm này: batch hỏng chỉ thấy nhóm “Lỗi / hỏng”, ô điều chỉnh bàn giao chỉ thấy nhóm “Điều chỉnh bàn giao”…" },
    { key: "ten", label: "Tên lý do / lỗi", type: "text", required: true, group: "Thông tin",
      hint: "vd nhóm Lỗi/hỏng: “Nhăn giấy”, “Lem mực”. Nhóm Tạm dừng: “Chờ mực”." },
    { key: "mo_ta", label: "Mô tả (tuỳ chọn)", type: "text", group: "Thông tin" },
    { key: "thu_tu", label: "Thứ tự hiển thị", type: "number", group: "Thông tin", default: 0,
      hint: "Số nhỏ hiện trước trong ô chọn. Để 0 nếu không cần xếp thứ tự." },
  ],
};

// Tình trạng khuôn — record-only (con người phán, máy chỉ ghi nhận).
// `dang_dat_lam` (mg 0177): dao CHƯA có trong tay — thuê ngoài chưa về, hoặc xưởng đang tự làm.
// Đi kèm NGÀY CÓ KHUÔN (dự kiến): bước dùng dao ở Lệnh sản xuất hiện ngày đó để người xếp việc
// biết chờ tới bao giờ. Không có nó thì "đang đặt làm" chỉ là một chữ.
// Loại dao — CÙNG bộ mã với `TOOLING_TYPE` của công đoạn (ô chọn dao ở bước lệnh lọc bằng phép so
// thẳng hai giá trị, lệch bộ mã là lọc ra rỗng).
export const LOAI_KHUON: Lbls = {
  khuon_be: "Khuôn bế",
  khuon_ep: "Khuôn ép nhũ / dập nổi",
};

export const TINH_TRANG_KHUON: Lbls = {
  dang_dung: "Đang dùng",
  dang_dat_lam: "Đang đặt làm",
  hong: "Hỏng",
  thanh_ly: "Thanh lý",
};

// Ngày ISO (yyyy-mm-dd) → dd/mm/yyyy để đọc; rỗng → để trống.
const fmtDate = (v: unknown): string => {
  const s = String(v ?? "").slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
};

// Khai báo KHUÔN BẾ — master data NHẸ, khai TAY. Mỗi khuôn làm riêng cho hình bế của 1
// ấn phẩm; đơn lặp lại thì lôi khuôn cũ ra dùng. Chỉ đủ để TÌM LẠI: số kệ (vị trí lưu) +
// tình trạng. Ref ấn phẩm/khách hàng đấu sau. Mã KB-#### tự sinh; xóa mềm giữ dấu vết.
export const CFG_KHUON_BE: CatalogConfig = {
  // Nhan đề là "Khuôn" (chứa cả khuôn ép nhũ) từ 16/08/2026 — nhưng `prefix`, `nhatKyLoai` và
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
  facet: { key: "tinh_trang", values: mapOpt(TINH_TRANG_KHUON) },
  columns: [
    { key: "khach_hang_ten", label: "Khách hàng",
      render: (r) => (r.khach_hang_ten ? String(r.khach_hang_ten) : "") },
    { key: "loai", label: "Loại", render: (r) => (r.loai ? lbl(LOAI_KHUON)(r.loai) : "") },
    { key: "so_ke", label: "Số kệ", render: (r) => (r.so_ke ? String(r.so_ke) : "") },
    // MỘT ngày duy nhất từ mg `0207` (gộp `ngay_lam_khuon` vào đây) — dao đã có thì là ngày nó
    // về / làm xong, dao đang làm thì là ngày dự kiến. Thêm chữ "dự kiến" cho ca sau để không ai
    // đọc nhầm một con số tương lai thành chuyện đã rồi.
    { key: "ngay_ve_du_kien", label: "Ngày có khuôn",
      render: (r) => (r.tinh_trang === "dang_dat_lam"
        ? `dự kiến ${fmtDate(r.ngay_ve_du_kien)}`
        : fmtDate(r.ngay_ve_du_kien)) },
    { key: "tinh_trang", label: "Tình trạng", render: (r) => lbl(TINH_TRANG_KHUON)(r.tinh_trang) },
  ],
  fields: [
    // Hai ô này là HAI CHIỀU LỌC của ô chọn dao ở bước lệnh sản xuất. Khai đủ thì người cấu hình
    // lệnh mở ra chỉ thấy vài con dao đúng khách, đúng loại; bỏ trống thì họ phải lội cả kho.
    // `size: 200` = trần của nền danh mục. Mặc định chỉ lấy trang đầu, mà ô chọn khách thiếu dòng
    // thì người ta tưởng chưa có khách đó rồi bỏ trống — đúng thứ làm chiều lọc này vô dụng.
    { key: "khach_hang_id", label: "Khách hàng", type: "ref", refPrefix: "/api/customers",
      refParams: { size: 200 }, group: "Nhận diện",
      hint: "Dao làm cho khách nào. Đây là đường tìm chính khi đơn lặp lại — bỏ trống thì lần sau dễ đặt lại con dao đã có." },
    { key: "loai", label: "Loại khuôn", type: "select", group: "Nhận diện",
      options: mapOpt(LOAI_KHUON),
      hint: "Bước “Ép nhũ” chỉ thấy dao ép, bước “Bế” chỉ thấy dao bế." },
    { key: "so_ke", label: "Số kệ / vị trí lưu", type: "text", group: "Lưu trữ",
      hint: "Nơi cất khuôn, vd: Kệ B3 — xưởng sau in. Thợ đọc đúng ô này để đi lấy." },
    { key: "tinh_trang", label: "Tình trạng", type: "select", group: "Lưu trữ",
      options: mapOpt(TINH_TRANG_KHUON), default: "dang_dung" },
    // "Ngày có khuôn" chứ không phải "ngày về": chữ "về" ngầm giả định thuê ngoài, mà xưởng tự làm
    // dao thì không "về" đâu cả — nó làm xong. Một ô, hai đường, một tên trung tính.
    { key: "ngay_ve_du_kien", label: "Ngày có khuôn (dự kiến)", type: "date", group: "Lưu trữ",
      hint: "Thuê ngoài thì là ngày về; xưởng tự làm thì là ngày làm xong. Bắt buộc khi tình trạng là “Đang đặt làm” — bước dùng khuôn ở Lệnh sản xuất hiện ngày này để biết chờ tới bao giờ." },
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
    {
      // `canh_bao` server vẫn trả từ lâu nhưng KHÔNG màn nào hiện — cảnh báo "số cố định đè lên
      // công thức" (thứ để lọt `1 tờ = 1.000 g` vào DB) vì thế mà vô hình. Cho nó một cột.
      key: "canh_bao",
      label: "Lưu ý",
      render: (r) => {
        const ds = Array.isArray(r.canh_bao) ? (r.canh_bao as string[]) : [];
        if (ds.length === 0) return <span style={{ color: "var(--ash-2)" }}>—</span>;
        return (
          <div className="rc__formula-chips">
            {ds.map((c, i) => {
              const shortText = c.length > 28 ? (c.includes(" — ") ? `⚠ ${c.split(" — ")[0]}` : `⚠ ${c.slice(0, 27)}…`) : `⚠ ${c}`;
              return (
                <span key={i} className="badge-sem badge-sem--amber rc__warn-pill" title={c}>
                  {shortText}
                </span>
              );
            })}
          </div>
        );
      },
    },
    { key: "ghi_chu", label: "Ghi chú", render: (r) => (r.ghi_chu ? String(r.ghi_chu) : "") },
  ],
  fields: [
    { key: "ghi_chu", label: "Ghi chú", type: "text" },
    // Cờ TRẠM: thứ duy nhất engine bù hao cần biết về một đơn vị. Năm mã dòng giấy đã gắn sẵn khi
    // cài, nên ô này gần như không ai phải đụng — chỉ dùng khi xưởng đẻ ra một cách gọi mới cho
    // một chặng của tờ giấy. Để trống = ngoài dòng giấy, đúng cho gần hết danh mục.
    // Ô select của RebuildCatalogPage đã tự chèn sẵn một dòng rỗng "—" (= ngoài dòng giấy), nên
    // ĐỪNG khai thêm option rỗng ở đây — hai dòng rỗng chồng nhau, người khai không biết chọn cái nào.
    { key: "tram_dong_giay", label: "Trạm trên dòng giấy", type: "select",
      options: mapOpt(TRAM_DONG_GIAY),
      hint: "Để trống = ngoài dòng giấy (đúng cho gần hết danh mục). Chỉ đặt cho đơn vị đếm chính TỜ GIẤY qua từng chặng — sai một dòng là số giấy của mọi lệnh lệch theo." },
  ],
  // Quy đổi khai NGAY TẠI ĐÂY, dưới ô Ghi chú — một chỗ nhập, không màn thứ hai.
  renderExtra: (_form, existing) => <QuyDoiCuaDonVi donVi={existing} />,
};

export const REBUILD_CONFIGS: Record<string, CatalogConfig> = {
  "loai-san-pham": CFG_LOAI_SAN_PHAM,
  "khai-bao-kho": CFG_KHO_HANG,
  "may-thiet-bi": CFG_MAY,
  "cong-doan": CFG_CONG_DOAN,
  "cong-viec-khoan": CFG_CONG_VIEC_KHOAN,
  "bu-hao": CFG_BU_HAO,
  "don-vi": CFG_DON_VI,
  "chung-loai-giay": CFG_CHUNG_LOAI_GIAY,
  "giay": CFG_GIAY,
  "vat-tu-in-an": CFG_VAT_TU,
  "thanh-pham": CFG_THANH_PHAM,
  "khuon-be": CFG_KHUON_BE,
  "ly-do-san-xuat": CFG_LY_DO_SAN_XUAT,
};
