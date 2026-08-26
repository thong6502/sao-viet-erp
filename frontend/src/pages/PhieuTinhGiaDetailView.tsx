// DETAIL của "Tính giá" — GIÁ VỐN theo SẢN LƯỢNG, KHÔNG hệ số (redesign-tinh-gia.md).
// 1 phiếu = nhiều "Thành phần" giấy; mỗi thành phần = Giấy ① + Kỹ thuật in ② + Màu + Gia công.
// UI: LIST (bám RebuildCatalogPage: badge + row + Sửa/Xóa) + DRAWER (.rc-drawer*) sửa 1 thành phần,
// trong drawer có SƠ ĐỒ BÌNH BÀI live. Auto + override giữ nguyên. "Tính giá" = create (lần đầu,
// khi phiếu còn nháp) hoặc update(pid) — BE replace-all + tính lại + snapshot → refresh từ Out.
// LƯU = TÍNH, và phiếu KHÔNG vào DB cho tới lần lưu đầu tiên (chống phiếu rỗng bỏ lại).
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import {
  api,
  ApiError,
  type PhieuTinhGiaOut,
  type PhieuTinhGiaColOut,
  type PhieuTinhGiaGroupOut,
  type PtgActivity,
  type ThanhPhanIn,
  type ThanhPhanOut,
  type ThanhPhamOut,
  type VatTuLineOut,
  type TinhGiaComponentMeta,
  type TinhGiaPreviewOut,
} from "../api/client";
import { congDoan, donViDo, giay, loaiSanPham, mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { MucInHang } from "../components/MucIn";
import { Select, type SelectOption } from "../components/Select";
import { ThanhPhamGoiY } from "../components/ThanhPhamGoiY";
import { ImpositionDiagram } from "./ImpositionDiagram";
import { heSoChu, nhanDonVi } from "./lsxBuoc";
import { useNapTenDonVi } from "./tenDonVi";
// Nhãn ĐƠN VỊ của biến công thức lấy từ TỪ ĐIỂN BIẾN (`/api/bien-cong-thuc`), không khai lại ở đây —
// xem ghi chú chỗ `humanizeFormula`.
import { traBien, useBienCongThuc, type TraBien } from "./RebuildCatalogPage";
import { HAM_TOAN, catToken, laSo, laToanTu } from "./danh-muc/formulaTokens";
import { PhieuTinhGiaPrint, type PhieuTinhGia, type PhieuTinhGiaColumn } from "./PhieuTinhGiaPrint";
import "./rebuild-catalog.css";
import "./tinh-gia.css";

// ------------------------------- Helpers -------------------------------
const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";

const vnd = (v: number | string | null | undefined): string =>
  typeof v === "number" ? v.toLocaleString("vi-VN") : (v ?? "").toString();

const rowLabel = (r: Row): string => `${r.ma ? `${r.ma} · ` : ""}${r.ten}`;
const cdName = (r: Row): string => (r.ten_hien_thi ? String(r.ten_hien_thi) : String(r.ten));

/** Lựa chọn cho một ô danh mục: BỎ mục đã ngừng dùng, nhưng GIỮ lại đúng mục phiếu đang dùng
 *  (kèm chữ "ngừng dùng"). Bỏ hẳn cả mục đang dùng thì mở phiếu cũ ra ô tự về rỗng, người lập
 *  phiếu tưởng phần mềm nuốt mất dữ liệu — cùng luật với ô ĐVT ngay bên cạnh. */
function optsConDung(rows: Row[], dangDung: number | null): SelectOption<string>[] {
  return rows
    .filter((r) => r.active !== false || r.id === dangDung)
    .map((r) => ({
      value: String(r.id),
      label: r.active === false ? `${rowLabel(r)} (ngừng dùng)` : rowLabel(r),
    }));
}

/** Kể tên vài mục rồi gộp phần đuôi — băng nhắc dài quá thì không ai đọc hết. */
const keTen = (ds: string[], toi = 4): string =>
  ds.slice(0, toi).join(" · ") + (ds.length > toi ? ` · +${ds.length - toi} mục nữa` : "");
const numOf = (v: unknown): number => (typeof v === "number" ? v : Number(v) || 0);

/** Số BÀI IN = số trang ÷ trang mỗi tay — dẫn xuất y hệt engine (`thanh_phan_engine`), FE chỉ
 *  hiện lại cho người khai thấy ngay, không gửi lên. */
const soBaiIn = (c: { so_trang: number; trang_moi_tay: number }): number =>
  Math.max(1, Math.ceil((c.so_trang || 1) / (c.trang_moi_tay || 1)));

/** SÁCH (gấp tay) hay TỜ RỜI? Cùng một tiêu chí `la_gap_tay` của engine — `trang mỗi tay > 1`,
 *  không cần thêm cờ nào. Sách thì tờ in được gấp NGUYÊN TỜ thành một tay, không cắt rời, nên
 *  "số con" vô nghĩa: engine đã không dùng nó tính giá (`cau_to_sang_cai` rẽ nhánh `1/so_tay`),
 *  UI cũng đừng hỏi. */
const laSach = (c: { trang_moi_tay: number }): boolean => (c.trang_moi_tay || 1) > 1;
/** Số vị trí TRANG trên MỘT mặt tờ in. Tay bắt buộc in 2 mặt nên chia đôi. */
const trangMoiMat = (c: { trang_moi_tay: number }): number =>
  Math.max(1, Math.ceil((c.trang_moi_tay || 1) / 2));

// ---------------------------------- MỰC IN ----------------------------------
/** Chuẩn hoá y hệt `tap_muc` của server: viết hoa, gộp khoảng trắng, bỏ trùng, giữ thứ tự. */
const chuanHoaMuc = (v: unknown): string[] => {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const x of v) {
    const ma = String(x ?? "").trim().replace(/\s+/g, " ").toUpperCase();
    if (ma && !out.includes(ma)) out.push(ma);
  }
  return out;
};
/** Dựng tập mực TỪ ba số cũ — cùng luật `tap_muc_tu_so` của server (migration 0154 dùng chung). */
const tapMucCuaComp = (c: {
  muc_a?: string[] | null; muc_b?: string[] | null;
  so_mau_a?: number | null; so_mau_b?: number | null; so_mau_pha?: number | null;
}): { muc_a: string[]; muc_b: string[] } => {
  const a = chuanHoaMuc(c.muc_a);
  const b = chuanHoaMuc(c.muc_b);
  if (a.length || b.length) return { muc_a: a, muc_b: b };
  const proc = ["K", "C", "M", "Y"];
  const nA = Math.max(c.so_mau_a ?? 0, 0);
  const nB = Math.max(c.so_mau_b ?? 0, 0);
  const nPha = Math.max(c.so_mau_pha ?? 0, 0);
  const mk = (n: number, mat: string) => [
    ...proc.slice(0, n),
    ...Array.from({ length: Math.max(n - 4, 0) }, (_, i) => `MỰC ${mat}${i + 5}`),
  ];
  return {
    muc_a: [...mk(nA, "A"), ...Array.from({ length: nPha }, (_, i) => `PHA ${i + 1}`)],
    muc_b: mk(nB, "B"),
  };
};
/** Kẽm cho MỘT tay — bản sao công thức `so_kem_moi_tay` của server, để chip bấm là số nhảy ngay
 *  chứ không đợi vòng /preview. Sai lệch giữa hai bên sẽ lộ ngay ở dòng tổng của engine. */
const soKemMoiTay = (muc_a: string[], muc_b: string[], quyCach: string): number => {
  if (quyCach === "mot_mat") return muc_a.length;
  // Tự trở / trở nhíp: hai mặt CHUNG một bộ bản → hợp tập. `max(|A|,|B|)` chỉ đúng khi tập bên
  // ít màu nằm gọn trong bên kia; mặt A CMYK với mặt B 185C phải ra 5 bản, `max` ra 4.
  if (quyCach === "tu_tro" || quyCach === "tro_nhip") {
    return new Set([...muc_a, ...muc_b]).size;
  }
  return muc_a.length + muc_b.length;
};

/** Chừa TÁCH THEO CHIỀU — khớp `chua_theo_chieu` của engine (đừng để hai bên lệch nhau).
 *
 *  · DÀI  ← nhíp GIẤY (cạnh nạp, 1 đầu) + đuôi/thanh màu
 *  · RỘNG ← lề hông ×2 (hai bên)
 *
 * Nguồn là DANH MỤC MÁY; phiếu chỉ còn một ô đè `chua_nhip`. Không chọn máy → chừa 0 cả hai chiều.
 * Chỉ lấy nhíp GIẤY — mép nhíp trên BẢN KẼM (~44mm) là chuyện khác, dùng nhầm là hụt 14-19% số con. */
function chuaTheoChieu(
  c: { chua_nhip: number },
  may: Row | null | undefined,
): { dai: number; rong: number } {
  const nhip = c.chua_nhip || numOf(may?.nhip_giay_mm);
  return { dai: nhip + numOf(may?.duoi_thang_mau_mm), rong: numOf(may?.le_hong_mm) * 2 };
}

const LOAI_TP: Record<string, string> = {
  to_roi: "Tờ rời",
  than: "Thân",
  nap: "Nắp",
  bia: "Bìa",
  ruot: "Ruột",
  phu_kien: "Phụ kiện",
};
const loaiTpLabel = (v: string): string => LOAI_TP[v] ?? v;

// Nhật ký hoạt động: action (audit backend) → [glyph, nhãn tiếng Việt].
const PTG_ACT_META: Record<string, [string, string]> = {
  create_ptg: ["+", "Lập phiếu tính giá"],
  update_ptg: ["✎", "Cập nhật phiếu"],
  delete_ptg: ["✕", "Xoá phiếu"],
};

// Ngày + giờ cho feed Hoạt động ("ai làm gì · khi nào").
function fmtActDateTime(v: string | null): string {
  if (!v) return "—";
  const dt = new Date(v);
  return isNaN(dt.getTime())
    ? "—"
    : dt.toLocaleString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

let _uid = 0;
const nextUid = (): string => `u${++_uid}`;

// Số cột engine trả kind "number"/"money"; formula giữ riêng.
function isNumCol(c: PhieuTinhGiaColOut): boolean {
  return c.align === "right" || c.kind === "num" || c.kind === "number" || c.kind === "money";
}
function cellClass(c: PhieuTinhGiaColOut): string {
  const cls: string[] = [];
  if (c.kind === "formula") cls.push("tg-formula");
  else if (isNumCol(c)) cls.push("tg-num");
  if (c.align === "center") cls.push("tg-center");
  return cls.join(" ");
}
function headClass(c: PhieuTinhGiaColOut): string {
  const cls: string[] = [];
  if (isNumCol(c)) cls.push("tg-num");
  if (c.align === "center") cls.push("tg-center");
  return cls.join(" ");
}
function cellValue(v: string | number | null): string {
  if (v == null || v === "") return "";
  return typeof v === "number" ? v.toLocaleString("vi-VN") : String(v);
}

// Engine trả công thức thế số dạng "don_gia(2.000) × to_nguyen(334)" (tên biến + giá trị).
// Đổi sang diễn giải người-đọc-được "2.000 đ × 334 tờ": bỏ tên biến, gắn đơn vị.
// Token lạ → chỉ giữ giá trị. Không match gì → trả nguyên chuỗi (an toàn).
// Đơn vị bước ở bảng phân rã bù hao PHẢI đọc y hệt tên đã khai trong danh mục Công đoạn — người
// lập phiếu đối chiếu hai màn với nhau, nhãn lệch một chữ là mất dấu. Nên KHÔNG khai bộ nhãn
// riêng ở đây. `nhanDonVi` nay đọc TÊN từ chính danh mục Đơn vị (xem `pages/tenDonVi.ts`), nên
// xưởng đổi tên là cả ba màn đổi theo — không còn bảng nhãn cứng nào để lệch.
const dvNgan = nhanDonVi;

/** Số + đơn vị ở cột phải khối "Số tờ tự tính".
 *
 *  TÁCH HAI PHẦN (12/08/2026) vì tên đơn vị nay do XƯỞNG đặt trong danh mục — có thể là "tờ" mà
 *  cũng có thể là "TỜ CHẠY MÁY". Gộp thành một chuỗi `<b>` thì cả cụm cùng cỡ 17px đậm, tên dài
 *  nuốt mất con số và đẩy vỡ hàng. Tách ra: SỐ giữ cỡ lớn và không bao giờ xuống dòng, ĐƠN VỊ nhỏ
 *  hơn, nhạt hơn, tự xuống dòng khi hết chỗ — dài bao nhiêu cũng đọc được con số trước tiên. */
function SoDv({ so, dv }: { so: string; dv?: string | null }) {
  return (
    <b className="tg-val">
      <i className="tg-val__so">{so}</i>
      {dv ? <i className="tg-val__dv">{dv}</i> : null}
    </b>
  );
}

/** Một dòng tiền đã đọc ra khỏi `groups[].rows` (kiểu thô `Record<string, string|number|null>`).
 *
 *  HAI công thức, không phải một: `congThucGoc` là thứ người ta khai trong danh mục (`to_dau_vao *
 *  so_mat * 350`), `congThuc` là bản engine đã thế số. Panel hiện cả hai — bản gốc trả lời "tính
 *  bằng gì", bản thế số trả lời "ra số nào". */
export interface DongTien {
  ten: string;
  tien: number;
  congThuc: string;
  congThucGoc: string;
}

/** `"to_dau_vao * so_mat * 350"` → `"Tờ vào máy × Số mặt in × 350"`.
 *
 *  Dùng chung bộ cắt token của màn danh mục — bản thứ hai là bản sớm muộn lệch một ký tự. Tên hàm
 *  toán giữ nguyên; biến lạ (từ điển chưa nạp, hoặc mã đã gỡ) cũng giữ nguyên mã thay vì nuốt đi:
 *  thấy `to_qua_buoc` lù lù còn biết mà đi sửa, chứ mất tiêu thì công thức đọc lên thiếu một vế. */
function dienGiaiFormula(raw: string, tra: TraBien): string {
  if (!raw) return "";
  const dau: Record<string, string> = { "*": "×", "/": "÷", "-": "−" };
  return catToken(raw)
    .map((t) => {
      if (laToanTu(t)) return dau[t] ?? t;
      if (laSo(t) || /^\s+$/.test(t)) return t;
      if ((HAM_TOAN as readonly string[]).includes(t)) return t;
      return tra(t)?.nhan ?? t;
    })
    .join("");
}

function _so(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function _chuoi(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** Dòng tiền của từng công đoạn, GIỮ THỨ TỰ ROUTING như engine trả về. Khối "Giá vốn" liệt kê
 *  theo mảng này; `tienTheoBuoc` bên dưới là cùng dữ liệu nhưng tra theo khóa, cho thẻ số tờ. */
function dongCongDoan(groups: PhieuTinhGiaGroupOut[] | null): DongTien[] {
  const grp = groups?.find((g) => g.idx === "cong_doan");
  const ra: DongTien[] = [];
  for (const r of grp?.rows ?? []) {
    const tien = _so(r.thanh_tien);
    if (tien === null) continue;
    // Dòng PHÍ KHUÔN nằm chung nhóm `cong_doan` nhưng KHÔNG phải một bước chạy máy — nó có khối
    // riêng bên dưới. Để lẫn vào đây thì "Công đoạn · 6 bước" đếm thành 8 và Σ cộng đôi.
    if (r.loai === "khuon") continue;
    // `ten` mang tiền tố tên sản phẩm (`_pre`) — ở đây đang đứng TRONG sản phẩm đó rồi, lặp lại
    // tên nó ở mọi dòng chỉ tổ đẩy con số ra khỏi tầm mắt.
    ra.push({
      ten: _chuoi(r.ten).split(" · ").pop() ?? "",
      tien,
      congThuc: _chuoi(r.cong_thuc),
      congThucGoc: _chuoi(r.cong_thuc_goc),
    });
  }
  return ra;
}

/** Hai dòng dưới một khoản tiền: DIỄN GIẢI (tính bằng gì) rồi THAY SỐ (ra số nào).
 *
 *  Một dòng thế số đứng trơ thì đọc lên là "5.200 × 2 × 350" — không biết 5.200 là tờ vào máy hay
 *  tờ nguyên, mà hai số đó khác nhau và đều có mặt trên màn. Có dòng tên biến ở trên mới kiểm được. */
function HaiDongCongThuc({ d, tra }: { d: DongTien; tra: TraBien }) {
  const goc = dienGiaiFormula(d.congThucGoc, tra);
  const so = d.congThuc ? humanizeFormula(d.congThuc, tra) : "";
  if (!goc && !so) return null;
  return (
    <>
      {goc && <em className="tg-sheetrow__derive">{goc}</em>}
      {so && <em className="tg-sheetrow__derive tg-sheetrow__derive--so">= {so}</em>}
    </>
  );
}

/** Các dòng PHÍ KHUÔN — engine gắn cờ `loai: "khuon"` trong chính nhóm `cong_doan`.
 *
 *  Tiền dao NẰM TRONG giá vốn (chốt 15/08/2026, gộp cho báo giá gọn) nhưng vẫn tách ra thành khối
 *  riêng trên màn: nó là khoản MỘT LẦN, xếp lẫn với sáu bước chạy máy thì người đọc tưởng nó cũng
 *  co giãn theo sản lượng như mấy dòng kia. */
function dongKhuon(groups: PhieuTinhGiaGroupOut[] | null): DongTien[] {
  const grp = groups?.find((g) => g.idx === "cong_doan");
  const ra: DongTien[] = [];
  for (const r of grp?.rows ?? []) {
    if (r.loai !== "khuon") continue;
    const tien = _so(r.thanh_tien);
    if (tien === null) continue;
    ra.push({
      ten: _chuoi(r.ten).split(" · ").slice(1).join(" · ") || _chuoi(r.ten),
      tien,
      congThuc: _chuoi(r.cong_thuc),
      congThucGoc: "",
    });
  }
  return ra;
}

/** Tiền của TỪNG BƯỚC, tra theo `buoc_idx` — khóa do engine phát ra ở CẢ hai danh sách
 *  (`groups.cong_doan[].buoc_idx` và `bu_hao_chi_tiet[].buoc_idx`).
 *
 *  KHÔNG ghép bằng tên: hai bên không cùng độ dài (chế bản có tiền nhưng không chạm tờ nên vắng
 *  mặt bên kia) và tên bên tiền đã bị gắn tiền tố tên sản phẩm. Ghép bằng tên thì hôm nào xưởng
 *  đổi tên một công đoạn là tiền rơi khỏi thẻ mà KHÔNG có lỗi nào báo.
 *
 *  Backend chưa restart (route cũ, không có `buoc_idx`) ⇒ map rỗng ⇒ thẻ chỉ hiện số tờ như cũ,
 *  không vỡ. Ở đây KHÔNG suy ra tiền bằng vị trí để "đỡ trống" — thà thiếu còn hơn gán nhầm tiền
 *  của bước này sang bước khác. */
function tienTheoBuoc(groups: PhieuTinhGiaGroupOut[] | null): Map<number, DongTien> {
  const out = new Map<number, DongTien>();
  const grp = groups?.find((g) => g.idx === "cong_doan");
  for (const r of grp?.rows ?? []) {
    const key = _so(r.buoc_idx);
    const tien = _so(r.thanh_tien);
    if (key === null || tien === null) continue;
    out.set(key, {
      ten: _chuoi(r.ten), tien,
      congThuc: _chuoi(r.cong_thuc), congThucGoc: _chuoi(r.cong_thuc_goc),
    });
  }
  return out;
}

/** Dòng NVL tách theo cờ `loai` engine gắn — giấy đứng riêng, mực/màng/keo gom lại. */
function nvlTheoLoai(groups: PhieuTinhGiaGroupOut[] | null): { giay: DongTien[]; vatTu: DongTien[] } {
  const ra: { giay: DongTien[]; vatTu: DongTien[] } = { giay: [], vatTu: [] };
  const grp = groups?.find((g) => g.idx === "nvl");
  for (const r of grp?.rows ?? []) {
    const tien = _so(r.thanh_tien);
    if (tien === null) continue;
    const dong: DongTien = {
      ten: _chuoi(r.ten), tien,
      congThuc: _chuoi(r.cong_thuc), congThucGoc: _chuoi(r.cong_thuc_goc),
    };
    if (r.loai === "giay") ra.giay.push(dong);
    else if (r.loai === "vat_tu") ra.vatTu.push(dong);
  }
  return ra;
}


// Tên hàm toán (max/min/ceil/floor/round) — GIỮ NGUYÊN trong diễn giải, không humanize như biến.
const MATH_FN = new Set(["max", "min", "ceil", "floor", "round"]);

/** `"don_gia_giay(32.000) × to_nguyen(210)"` → `"32.000 đ × 210 tờ"`.
 *
 *  `tra` là bản tra từ điển biến (`traBien(useBienCongThuc())`). Từ điển chưa nạp xong ⇒ `tra` trả
 *  undefined ⇒ hiện số trần, KHÔNG bịa đơn vị. */
function humanizeFormula(s: string, tra: TraBien): string {
  if (!s) return s;
  // Chỉ match token biến-thế-số dạng name(SỐ) — inner chỉ gồm chữ số/dấu . , khoảng trắng.
  // Nhờ vậy KHÔNG "nuốt" lời gọi hàm max(so_kem(4) × …) (inner của hàm có chữ + toán tử).
  return s.replace(/([a-zA-Z_][a-zA-Z0-9_]*)\(([\d.,\s]*)\)/g, (m, name: string, val: string) => {
    if (MATH_FN.has(name)) return m;   // giữ nguyên vd max(380.000, 999.000)
    const unit = tra(name)?.don_vi;
    const v = val.trim();
    return unit ? `${v} ${unit}` : v;
  });
}

/** Loại dụng cụ ĐƯỢC PHÉP mang phí khuôn → nhãn hiện cạnh tên bước.
 *
 *  Phải khớp `thanh_phan_engine.TOOLING_CO_PHI` bên backend — lệch là màn hiện ô mà engine bỏ số,
 *  hoặc ngược lại. `kem` (bản kẽm) CỐ Ý VẮNG: nó là vật tư tiêu hao, mỗi bài phơi mới, và tiền nó
 *  đã nằm trong công thức của bước chế bản (`so_kem × đơn giá`) — cho ô nữa là tính hai lần. */
const DAO_CO_PHI: Record<string, string> = {
  khuon_be: "khuôn bế",
  khuon_ep: "khuôn ép nhũ / dập nổi",
};

/** Bước này có cần dao lưu kho không → trả NHÃN loại dao, hoặc `null` nếu không hỏi phí.
 *
 *  Đọc CỜ từ danh mục Công đoạn (`requires_tooling` + `tooling_type`), KHÔNG đoán theo tên bước —
 *  tên là chữ người dùng gõ, đổi lúc nào không ai báo. Dòng tự nhập (không gắn danh mục) thì không
 *  có cờ nào để đọc ⇒ không hỏi phí. */
/** Tên bước để HIỆN. Dòng có gắn danh mục → gọi theo tên SỐNG trong danh mục, nên xưởng đổi tên
 *  một công đoạn là phiếu gọi tên mới ngay (tiền vẫn giữ ảnh chụp — xem băng "Danh mục đã đổi").
 *  Dòng tự nhập (không `cong_doan_id`) mới rơi về tên đã lưu trong phiếu. Cùng luật với engine
 *  (`thanh_phan_engine._ten_buoc`). */
function tenBuoc(f: { cong_doan_id: number | null; ten: string }, congDoans: Row[]): string {
  const cd = f.cong_doan_id == null ? undefined : congDoans.find((x) => x.id === f.cong_doan_id);
  return (cd ? cdName(cd) : "") || f.ten || "";
}

/** Bước này còn khớp danh mục không? `null` = bình thường (hoặc dòng tự nhập, không gắn danh mục).
 *  Hai ca hỏng KHÁC nhau nên phải gọi khác tên: `ngung` = còn trong bảng nhưng đã tắt (chọn lại
 *  không được nữa) · `mat` = xoá hẳn, id trỏ vào hư không. */
function tinhTrangBuoc(
  f: { cong_doan_id: number | null },
  congDoans: Row[],
): "ngung" | "mat" | null {
  if (f.cong_doan_id == null) return null;
  const cd = congDoans.find((x) => x.id === f.cong_doan_id);
  if (!cd) return "mat";
  return cd.active === false ? "ngung" : null;
}

function daoCuaBuoc(f: { cong_doan_id: number | null }, congDoans: Row[]): string | null {
  if (f.cong_doan_id == null) return null;
  const cd = congDoans.find((x) => x.id === f.cong_doan_id);
  if (!cd || !cd.requires_tooling) return null;
  return DAO_CO_PHI[String(cd.tooling_type ?? "")] ?? null;
}

// ------------------------------- Editable model -------------------------------
interface EditableFinishing {
  uid: string;
  cong_doan_id: number | null;
  ten: string;
  don_gia: number;
  so_luong: number;
  bu_hao: boolean;
  so_mat: number;
  so_vi_tri: number;
  dien_tich: number;
  nha_cung_cap: string;
  ghi_chu: string;
  /** Phí làm khuôn của CHÍNH bước này — khoản MỘT LẦN, người dùng gõ nguyên số tiền làm dao (không
   *  nhân SL). Engine CÓ cộng nó vào giá vốn sản phẩm, nên nó vẫn bị chia ra đ/sản phẩm ở dòng
   *  tổng. 0 = dùng lại dao cũ. Chỉ hỏi ở bước có cờ dụng cụ là dao lưu kho (xem `daoCuaBuoc`). */
  phi_khuon: number;
}
interface EditableVatTu {
  uid: string;
  vat_tu_id: number | null;
  ten: string;
  don_gia: number;
  so_luong: number;
  ghi_chu: string;
}
interface EditableComponent {
  uid: string;
  loai_thanh_phan: string;
  ten: string;
  // Thành phẩm ③
  dai_thanh_pham: number; // mm
  rong_thanh_pham: number; // mm
  so_to_per_sp: number; // DẪN XUẤT (server ghi) — chỉ để đọc lại phiếu cũ
  so_trang: number;      // số trang nội dung của 1 sản phẩm (tờ rời = 1)
  trang_moi_tay: number; // số trang mỗi tay gấp (tờ rời = 1)
  so_luong: number; // SL đặt của SP này (0 = lấy SL mặc định phiếu)
  don_vi_tinh: string; // ĐVT sản phẩm (text tự do, mặc định "cái") → chảy sang Báo giá
  // Nhãn GỘP DÒNG KHI BÁO GIÁ: ruột + bìa cùng cuốn gõ giống nhau → báo giá in 1 dòng "quyển
  // sách". Chỉ là lớp trình bày: tính giá vẫn tách dòng, sản xuất vẫn tách lệnh.
  nhom_bao_gia: string;
  loai_san_pham_id: number | null; // loại SP của sản phẩm này
  // Giấy ①
  giay_id: number | null;
  kho_nguyen: string;
  kho_nguyen_dai: number; // ① khổ giấy nguyên dài (mm) — đè danh mục khi > 0
  kho_nguyen_rong: number; // ①
  don_gia_giay: number;
  don_gia_don_vi: string; // kg | to | tan | ram | cai (theo danh mục giấy)
  /** DORMANT từ 2026-08-09 (Đợt 4 · K): ô chọn đã gỡ, engine thôi đọc. FE luôn gửi `cong_ty`.
   *  Giữ field để không phải sửa DTO hai đầu — cột vẫn còn trong DB theo lệ dự án (không drop cột). */
  nguon_giay: string;
  chua_nhip: number; // đè nhíp giấy của máy (0 = theo danh mục Máy)
  bleed_mm: number;
  khe_cat_mm: number;
  // Kỹ thuật in ② — In/kẽm nay là CÔNG ĐOẠN (chuỗi), không còn field cứng ở đây.
  quy_cach_in: string; // mot_mat | hai_mat (AB) | tu_tro | tro_nhip
  kho_in_dai: number; // mm
  kho_in_rong: number; // mm
  so_con: number; // ④
  con_auto: boolean;
  may_id: number | null;
  /** TẬP mã mực mỗi mặt — nguồn sự thật của số kẽm (xem `soKemMoiTay`). */
  muc_a: string[];
  muc_b: string[];
  /** DẪN XUẤT server chốt, giữ để gửi lại nguyên vẹn cho phiếu cũ chưa khai mực. */
  so_mau_a: number;
  so_mau_b: number;
  so_mau_pha: number;
  ghi_chu_ky_thuat: string; // Lưu ý SX / ghi chú kỹ thuật theo sản phẩm → drawer lệnh SX
  gia_von_tp: number; // read-only từ lần tính gần nhất
  thanh_phams: EditableFinishing[];
  vat_tus: EditableVatTu[];
}

function blankFinishing(ten = "", cong_doan_id: number | null = null): EditableFinishing {
  return {
    uid: nextUid(),
    cong_doan_id,
    ten,
    don_gia: 0,
    so_luong: 0,
    bu_hao: false,
    so_mat: 1,
    so_vi_tri: 0,
    dien_tich: 0,
    nha_cung_cap: "",
    ghi_chu: "",
    phi_khuon: 0,
  };
}
function blankComponent(ten = ""): EditableComponent {
  return {
    uid: nextUid(),
    loai_thanh_phan: "to_roi",
    ten,
    dai_thanh_pham: 0,
    rong_thanh_pham: 0,
    so_to_per_sp: 1,
    so_trang: 1,
    trang_moi_tay: 1,
    so_luong: 0,
    don_vi_tinh: "cái",
    nhom_bao_gia: "",
    loai_san_pham_id: null,
    giay_id: null,
    kho_nguyen: "",
    kho_nguyen_dai: 0,
    kho_nguyen_rong: 0,
    don_gia_giay: 0,
    don_gia_don_vi: "to",
    nguon_giay: "cong_ty",
    chua_nhip: 0,
    bleed_mm: 0,
    khe_cat_mm: 0,
    quy_cach_in: "mot_mat",
    kho_in_dai: 0,
    kho_in_rong: 0,
    so_con: 1,
    con_auto: true,
    may_id: null,
    muc_a: ["K"],   // hàng nào cũng chạy đen; 4 màu chỉ cách ba cú bấm
    muc_b: [],
    so_mau_a: 0,
    so_mau_b: 0,
    so_mau_pha: 0,
    ghi_chu_ky_thuat: "",
    gia_von_tp: 0,
    thanh_phams: [],
    vat_tus: [],
  };
}

function fromFinishing(f: ThanhPhamOut): EditableFinishing {
  return {
    uid: nextUid(),
    cong_doan_id: f.cong_doan_id ?? null,
    ten: f.ten ?? "",
    don_gia: f.don_gia ?? 0,
    so_luong: f.so_luong ?? 0,
    bu_hao: !!f.bu_hao,
    so_mat: f.so_mat ?? 1,
    so_vi_tri: f.so_vi_tri ?? 0,
    dien_tich: f.dien_tich ?? 0,
    nha_cung_cap: f.nha_cung_cap ?? "",
    ghi_chu: f.ghi_chu ?? "",
    phi_khuon: f.phi_khuon ?? 0,
  };
}
function fromVatTu(v: VatTuLineOut): EditableVatTu {
  return {
    uid: nextUid(),
    vat_tu_id: v.vat_tu_id ?? null,
    ten: v.ten ?? "",
    don_gia: v.don_gia ?? 0,
    so_luong: v.so_luong ?? 0,
    ghi_chu: v.ghi_chu ?? "",
  };
}
function fromComponent(c: ThanhPhanOut): EditableComponent {
  return {
    uid: nextUid(),
    loai_thanh_phan: c.loai_thanh_phan ?? "to_roi",
    ten: c.ten ?? "",
    dai_thanh_pham: c.dai_thanh_pham ?? 0,
    rong_thanh_pham: c.rong_thanh_pham ?? 0,
    so_to_per_sp: c.so_to_per_sp ?? 1,
    so_trang: c.so_trang ?? 1,
    trang_moi_tay: c.trang_moi_tay ?? 1,
    so_luong: c.so_luong ?? 0,
    don_vi_tinh: c.don_vi_tinh ?? "cái",
    nhom_bao_gia: c.nhom_bao_gia ?? "",
    loai_san_pham_id: c.loai_san_pham_id ?? null,
    giay_id: c.giay_id ?? null,
    kho_nguyen: c.kho_nguyen ?? "",
    kho_nguyen_dai: c.kho_nguyen_dai ?? 0,
    kho_nguyen_rong: c.kho_nguyen_rong ?? 0,
    don_gia_giay: c.don_gia_giay ?? 0,
    don_gia_don_vi: c.don_gia_don_vi ?? "to",
    nguon_giay: c.nguon_giay ?? "cong_ty",
    chua_nhip: c.chua_nhip ?? 0,
    bleed_mm: c.bleed_mm ?? 0,
    khe_cat_mm: c.khe_cat_mm ?? 0,
    quy_cach_in: c.quy_cach_in ?? "mot_mat",
    kho_in_dai: c.kho_in_dai ?? 0,
    kho_in_rong: c.kho_in_rong ?? 0,
    so_con: c.so_con ?? 1,
    con_auto: c.con_auto ?? true,
    may_id: c.may_id ?? null,
    // Phiếu mở từ DB LUÔN có tập mực (migration 0154 backfill hết), nhưng vẫn dựng lại từ ba số
    // khi rỗng — dùng đúng luật của server để client không hiện khác phiếu.
    ...tapMucCuaComp(c),
    so_mau_a: c.so_mau_a ?? 0,
    so_mau_b: c.so_mau_b ?? 0,
    so_mau_pha: c.so_mau_pha ?? 0,
    ghi_chu_ky_thuat: c.ghi_chu_ky_thuat ?? "",
    gia_von_tp: c.gia_von_tp ?? 0,
    thanh_phams: (c.thanh_phams ?? []).map(fromFinishing),
    vat_tus: (c.vat_tus ?? []).map(fromVatTu),
  };
}

function toThanhPhanIn(c: EditableComponent): ThanhPhanIn {
  return {
    loai_thanh_phan: c.loai_thanh_phan,
    ten: c.ten,
    dai_thanh_pham: c.dai_thanh_pham,
    rong_thanh_pham: c.rong_thanh_pham,
    so_trang: c.so_trang,
    trang_moi_tay: c.trang_moi_tay,
    so_luong: c.so_luong,
    don_vi_tinh: c.don_vi_tinh.trim() || "cái",
    nhom_bao_gia: c.nhom_bao_gia.trim() || null,
    loai_san_pham_id: c.loai_san_pham_id,
    giay_id: c.giay_id,
    kho_nguyen: c.kho_nguyen.trim() || null,
    kho_nguyen_dai: c.kho_nguyen_dai,
    kho_nguyen_rong: c.kho_nguyen_rong,
    don_gia_giay: c.don_gia_giay,
    don_gia_don_vi: c.don_gia_don_vi,
    nguon_giay: c.nguon_giay,
    chua_nhip: c.chua_nhip,
    bleed_mm: c.bleed_mm,
    khe_cat_mm: c.khe_cat_mm,
    quy_cach_in: c.quy_cach_in,
    kho_in_dai: c.kho_in_dai,
    kho_in_rong: c.kho_in_rong,
    so_con: c.so_con,
    con_auto: c.con_auto,
    may_id: c.may_id,
    muc_a: c.muc_a,
    muc_b: c.muc_b,
    // Ba số này server tính lại từ tập mực rồi ghi đè — gửi kèm chỉ để không rơi mất khi phiếu
    // chưa từng khai mực.
    so_mau_a: c.so_mau_a,
    so_mau_b: c.so_mau_b,
    so_mau_pha: c.so_mau_pha,
    ghi_chu_ky_thuat: c.ghi_chu_ky_thuat.trim() || null,
    thanh_phams: c.thanh_phams.map((f) => ({
      cong_doan_id: f.cong_doan_id,
      ten: f.ten,
      don_gia: f.don_gia,
      so_luong: f.so_luong,
      bu_hao: f.bu_hao,
      so_mat: f.so_mat,
      so_vi_tri: f.so_vi_tri,
      dien_tich: f.dien_tich,
      nha_cung_cap: f.nha_cung_cap.trim() || null,
      ghi_chu: f.ghi_chu.trim() || null,
      phi_khuon: f.phi_khuon,
    })),
    vat_tus: c.vat_tus.map((v) => ({
      vat_tu_id: v.vat_tu_id,
      ten: v.ten,
      don_gia: v.don_gia,
      so_luong: v.so_luong,
      ghi_chu: v.ghi_chu.trim() || null,
    })),
  };
}


/** Node hiển thị của bảng sản phẩm: 1 nhóm gộp (nhiều dòng) hoặc 1 dòng lẻ. */
type NodeHienThi =
  | { kind: "nhom"; key: string; ten: string; members: EditableComponent[] }
  | { kind: "don"; comp: EditableComponent };


// Engine (snake_case) → phiếu in (chuỗi format sẵn).
function toPhieu(
  res: TinhGiaPreviewOut,
  soPhieu: string,
  tenAnPham: string,
  soLuong: string,
  khoThanhPham: string,
  /** Ngày LẬP PHIẾU (`created_at`), KHÔNG phải hôm nay. Phiếu lập 27/7 mà bản in ghi ngày bấm In
   *  là chứng từ nói sai ngày — ai đối chiếu sổ sách cũng vấp. */
  ngayLap: string | null,
  sanPhams: { ten: string; soLuong: number; dvt: string }[],
  tra: TraBien,
): PhieuTinhGia {
  const now = new Date();
  return {
    header: {
      soPhieu,
      ngayLap: ngayLap ?? "—",
      ngayIn: now.toLocaleString("vi-VN"),
      tenAnPham: tenAnPham || "—",
      soLuong,
      khoThanhPham: khoThanhPham || "—",
    },
    sanPhams,
    noiDung: [],
    groups: res.groups.map((g) => {
      const columns: PhieuTinhGiaColumn[] = g.columns.map((c) => ({
        key: c.key,
        label: c.label,
        align: c.align,
        kind: c.kind === "formula" ? "formula" : isNumCol(c) ? "num" : "text",
      }));
      return {
        idx: g.idx,
        name: g.name,
        columns,
        rows: g.rows.map((r) => {
          const out: Record<string, string | number> = {};
          for (const c of g.columns) {
            const val = r[c.key];
            out[c.key] = isNumCol(c)
              ? vnd(val as number)
              : c.kind === "formula"
                ? humanizeFormula((val ?? "").toString(), tra)  // bản in cũng dễ đọc: "32.000 đ × 210 tờ"
                : (val ?? "").toString();
          }
          return out;
        }),
        subtotalLabel: `Cộng ${g.name}`,
        subtotal: vnd(g.subtotal),
      };
    }),
    grandTotal: vnd(res.grand_total),
    grandNote: "Giá vốn sản xuất · chưa gồm lợi nhuận & VAT",
    chuKy: [
      { role: "Người lập", who: "Bộ phận định giá" },
      { role: "Người duyệt", who: "Trưởng phòng KD" },
      { role: "Giám đốc", who: "Ban giám đốc" },
    ],
  };
}

// ------------------------------- Small building blocks -------------------------------
function Seg({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { val: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  ariaLabel: string;
}) {
  return (
    <div className="tg-seg" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.val}
          type="button"
          aria-pressed={value === o.val}
          className={`tg-seg__btn${value === o.val ? " tg-seg__btn--on" : ""}`}
          onClick={() => onChange(o.val)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Khối MỰC IN — mỗi mặt một hàng chip, số kẽm chốt ở tiêu đề.
 *
 *  Thay ba ô số cũ (mặt A · mặt B · màu pha) vì số kẽm của tự trở là `|A ∪ B|`: con số không
 *  mang đủ thông tin để hợp hai tập. Mặt B hiện CẢ khi tự trở/trở nhíp — bản cũ giấu ô đó đi,
 *  tức coi tự trở là "không có mặt B", trong khi nó chỉ là mặt B không có bản kẽm riêng.
 */
function MucInBlock({
  comp,
  soTay,
  onChange,
}: {
  comp: EditableComponent;
  soTay: number;
  onChange: (patch: Partial<EditableComponent>) => void;
}) {
  const kemMoiTay = soKemMoiTay(comp.muc_a, comp.muc_b, comp.quy_cach_in);
  return (
    <div className="tg-muc">
      <div className="tg-muc__head">
        <span className="tg-microlabel">Mực in</span>
        <span className="tg-muc__kem">
          <b>{kemMoiTay * Math.max(soTay, 1)}</b> kẽm
        </span>
      </div>
      <MucInHang
        mucA={comp.muc_a}
        mucB={comp.muc_b}
        quyCachIn={comp.quy_cach_in}
        onChange={(a, b) => onChange({ muc_a: a, muc_b: b })}
      />
    </div>
  );
}

/** Ô số. `thapPhan` = ô ĐO ĐẠC (mm) — nhận số lẻ.
 *
 *  Khổ in thật hay lẻ nửa ly (name card 88.9×50.8, thư mời letter 215.9×279.4, bìa cộng gáy
 *  3.5mm) nên các ô mm phải nhập được số thực. Ô mm KHÔNG dùng `type="number"`: dấu thập phân
 *  của nó phụ thuộc ngôn ngữ trình duyệt — máy để tiếng Việt gõ "215.9" thì trình duyệt nuốt
 *  dấu chấm, máy để tiếng Anh gõ "215,9" thì nuốt dấu phẩy, và số lẻ còn bị đánh dấu
 *  `stepMismatch` vì step mặc định = 1. Dùng ô chữ + `inputMode="decimal"` (bàn phím điện thoại
 *  vẫn ra bàn số) rồi tự quy dấu phẩy về dấu chấm — gõ kiểu nào cũng ăn.
 */
function NumField({
  label,
  value,
  onChange,
  min = 0,
  step,
  opt,
  suffix,
  thapPhan,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min?: number;
  step?: string;
  opt?: string;
  suffix?: string;
  thapPhan?: boolean;
}) {
  const [valStr, setValStr] = useState<string>(String(value ?? 0));

  useEffect(() => {
    if (Number(valStr) !== value) {
      setValStr(String(value ?? 0));
    }
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Ô mm là ô CHỮ nên chữ cái lọt được vào: lọc ngay tại đây, chỉ giữ số và MỘT dấu thập phân
    // (đã quy phẩy → chấm). Không lọc thì "21a5" nằm lại trên màn tới lúc rời ô mới bật về 0.
    const raw = thapPhan
      ? e.target.value.replace(",", ".").replace(/[^\d.]/g, "").replace(/(\..*)\./g, "$1")
      : e.target.value;
    setValStr(raw);
    if (raw === "") {
      onChange(min);
    } else {
      const parsed = Number(raw);
      if (!isNaN(parsed)) {
        onChange(Math.max(min, parsed));
      }
    }
  };

  const handleBlur = () => {
    const num = Math.max(min, Number(valStr) || min);
    setValStr(String(num));
    onChange(num);
  };

  const handleFocus = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.select();
  };

  return (
    <label className="tg-field">
      <span className="tg-microlabel">
        {label}
        {opt ? <span className="tg-microlabel__opt">{opt}</span> : null}
      </span>
      <div className={suffix ? "tg-suffixwrap" : undefined}>
        <input
          className="tg-input tg-input--num"
          {...(thapPhan
            ? { type: "text", inputMode: "decimal" as const }
            : { type: "number", min, step })}
          value={valStr}
          onChange={handleChange}
          onBlur={handleBlur}
          onFocus={handleFocus}
        />
        {suffix ? <span className="tg-suffix">{suffix}</span> : null}
      </div>
    </label>
  );
}


const KhuonCalcIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M8 6h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h4M8 19h8" />
  </svg>
);


/** Số trang → SỐ BÀI IN. Hai ô này nay ĐƯỢC LƯU (`so_trang` / `trang_moi_tay`): số tờ in của
 *  engine đi thẳng từ số trang, nên mở lại phiếu phải thấy đúng thứ người ta đã khai — trước đây
 *  tính xong là mất, chỉ còn lại kết quả nên không ai biết nó ra từ đâu. Mặc định 1/1 = tờ rời. */
function KhuonCalc({ domId, soTrangDaLuu, moiTayDaLuu, onApply, onClose }: {
  domId: string;
  soTrangDaLuu: number;
  moiTayDaLuu: number;
  onApply: (soTrang: number, moiTay: number) => void;
  onClose: () => void;
}) {
  const [soTrang, setSoTrang] = useState(soTrangDaLuu);
  const [moiTay, setMoiTay] = useState(moiTayDaLuu);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const firstRef = useRef<HTMLInputElement | null>(null);

  // Mở → focus ô đầu; đóng (Esc · bấm ngoài · Dùng · Đóng) → TRẢ focus về nút mở,
  // không để người dùng bàn phím rơi về body mất chỗ đứng.
  useEffect(() => {
    firstRef.current?.focus();
    return () => {
      document.querySelector<HTMLElement>(`[aria-controls="${domId}"]`)?.focus();
    };
  }, [domId]);
  useEffect(() => {
    // Esc bắt ở pha CAPTURE để đóng popover trước, không để drawer cha nuốt mất phím.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("mousedown", onDown);
    };
  }, [onClose]);

  const khuon = soTrang > 0 && moiTay > 0 ? Math.ceil(soTrang / moiTay) : 0;
  const tayDu = moiTay > 0 ? Math.floor(soTrang / moiTay) : 0;
  const du = moiTay > 0 ? soTrang % moiTay : 0;
  const apply = () => {
    if (khuon > 0) onApply(soTrang, moiTay);
  };
  const onEnter = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      apply();
    }
  };

  return (
    <div className="tg-calc" id={domId} ref={boxRef} role="dialog" aria-label="Tính số bài in từ số trang">
      <div className="tg-calc__row">
        <label className="tg-field">
          <span className="tg-microlabel">Số trang</span>
          <input
            ref={firstRef}
            className="tg-input tg-input--num"
            type="number"
            min={0}
            step="1"
            value={soTrang || ""}
            onChange={(e) => setSoTrang(Math.max(0, Number(e.target.value)))}
            onKeyDown={onEnter}
          />
        </label>
        <label className="tg-field">
          <span className="tg-microlabel">Trang mỗi tay</span>
          <input
            className="tg-input tg-input--num"
            type="number"
            min={1}
            step="1"
            value={moiTay || ""}
            onChange={(e) => setMoiTay(Math.max(1, Number(e.target.value)))}
            onKeyDown={onEnter}
          />
        </label>
      </div>
      <div className="tg-chipgrid">
        {[8, 16, 32].map((v) => (
          <button
            key={v}
            type="button"
            className={`tg-chip tg-chip--sm${moiTay === v ? " tg-chip--on" : ""}`}
            aria-pressed={moiTay === v}
            onClick={() => setMoiTay(v)}
          >
            {v} trang
          </button>
        ))}
      </div>
      {/* Kết quả là thứ người ta mở popover để xem → số phải TO nhất, cách tính đứng dưới. */}
      <p className="tg-calc__out" aria-live="polite">
        {khuon > 0 ? (
          <>
            <span className="tg-calc__num">{khuon}</span> bài in
            <span className="tg-calc__how">
              {soTrang} ÷ {moiTay} = {tayDu} tay đủ
              {du > 0 ? ` + 1 tay ${du} trang` : ""}
            </span>
          </>
        ) : (
          <span className="tg-calc__how">Nhập số trang để tính</span>
        )}
      </p>
      <div className="tg-calc__act">
        <button type="button" className="tg-chip" onClick={onClose}>
          Đóng
        </button>
        <button type="button" className="tg-calc__apply" disabled={khuon < 1} onClick={apply}>
          Dùng {khuon > 0 ? khuon : ""}
        </button>
      </div>
    </div>
  );
}


// ------------------------------- Component -------------------------------
export function PhieuTinhGiaDetailView({ id, onBack, navigate }: {
  // null = phiếu NHÁP chưa ghi DB (vừa bấm "Lập phiếu tính giá"). Form chạy đủ — bình bài và số
  // tờ live đều tính không cần id — chỉ LƯU là hoãn tới khi có sản phẩm thật, để không đẻ phiếu rỗng.
  id: number | null;
  onBack: () => void;
  // BG-3: điều hướng sang Báo giá (openQuoteId đã wired ở AppShell). Không truyền → ẩn nút báo giá.
  navigate?: (pageId: string, params?: { openQuoteId?: number }) => void;
}) {
  const { token } = useAuth();
  // Nhãn đơn vị ở bảng phân rã bù hao đọc từ danh mục — nạp một lần cho cả phiên.
  useNapTenDonVi();
  const [quoting, setQuoting] = useState(false);
  // Id THẬT của phiếu: null tới khi lần lưu đầu tiên chạy xong (POST). Từ đó trở đi là PUT.
  const [pid, setPid] = useState<number | null>(id);
  const daLuu = pid != null;

  // --- Danh mục nguồn ---
  const [loaiSPs, setLoaiSPs] = useState<Row[]>([]);
  const [giays, setGiays] = useState<Row[]>([]);
  const [mays, setMays] = useState<Row[]>([]);
  const [congDoans, setCongDoans] = useState<Row[]>([]);
  // Từ điển biến công thức — dùng để lấy nhãn ĐƠN VỊ khi diễn giải công thức đã thế số.
  // Cache theo phiên trong `useBienCongThuc`, nên nhiều màn mở cùng lúc vẫn một lượt gọi.
  const bienCt = useBienCongThuc();
  const traDv = useMemo(() => traBien(bienCt), [bienCt]);

  // --- Header phiếu đã lưu ---
  const [ma, setMa] = useState("");
  const [ktv, setKtv] = useState<string | null>(null);
  const [ngay, setNgay] = useState<string | null>(null);
  const [tongGiaVon, setTongGiaVon] = useState<number | null>(null);

  // --- Form ---
  const [loaiSPId, setLoaiSPId] = useState<number | "">("");
  const [khoThanhPham, setKhoThanhPham] = useState("");
  const [comps, setComps] = useState<EditableComponent[]>([]);
  const [editingUid, setEditingUid] = useState<string | null>(null);
  // Số [Hiện] LIVE của sản phẩm đang mở modal (gọi /preview — engine thật, không ghi DB).
  const [editMeta, setEditMeta] = useState<TinhGiaComponentMeta | null>(null);
  // Hai NHÓM TIỀN (nvl · cong_doan) của chính sản phẩm đang mở — cùng một vòng /preview với
  // `editMeta`, không gọi thêm lần nào. Panel bên phải chạy mạch tiền song song mạch số tờ: mỗi
  // bước hiện tiền của đúng bước đó, chốt lại bằng giá vốn sản phẩm.
  const [editGia, setEditGia] = useState<PhieuTinhGiaGroupOut[] | null>(null);
  // Bình bài NGHỊCH: uid → true khi gõ Số con mà KHÔNG xếp được đúng N trong khổ giấy nguyên.

  // --- Kết quả ---
  const [result, setResult] = useState<TinhGiaPreviewOut | null>(null);
  // Nhật ký hoạt động THẬT (ai làm gì · khi nào) — nhiều người cùng sửa 1 phiếu.
  const [acts, setActs] = useState<PtgActivity[]>([]);
  const [showAllActs, setShowAllActs] = useState(false); // UI-only: "Xem tất cả"
  const [loading, setLoading] = useState(id != null);
  const [calcing, setCalcing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Chặn cửa khi rời phiếu nháp đang có nội dung (chưa lưu → thoát là mất).
  const [hoiThoat, setHoiThoat] = useState(false);
  // Danh mục đã sửa SAU lần tính gần nhất (BE so mốc, xem `danh_muc_doi_sau_khi_tinh`). Mở phiếu
  // là đọc lại ẢNH CHỤP — cố ý, phiếu đã báo cho khách thì không được tự đổi số dưới chân người
  // ta. Nhưng im hẳn cũng sai: đổi tên/cấu hình công đoạn xong mở phiếu thấy y như cũ thì tưởng
  // phần mềm hỏng. Nên nói ra + đưa sẵn nút, còn bấm hay không là quyền người lập phiếu.
  const [danhMucDoi, setDanhMucDoi] = useState<PhieuTinhGiaOut["danh_muc_doi"]>(null);
  // Ba rổ TÁCH RIÊNG vì việc phải làm khác hẳn nhau: sửa cấu hình (tính lại là xong) · ngừng dùng
  // (tính lại vẫn ra số nhưng lần sau không chọn lại được) · xoá hẳn (dòng phiếu trỏ vào hư không,
  // phải thay bước). Gộp cả ba vào một chữ "đã chỉnh sửa" là nói sai việc người dùng vừa làm.
  const dmNgung = danhMucDoi?.ngung ?? [];
  const dmXoa = danhMucDoi?.xoa ?? [];

  const applyOut = useCallback((out: PhieuTinhGiaOut) => {
    setMa(out.ma);
    setKtv(out.ktv);
    setNgay(out.created_at ? out.created_at.slice(0, 10) : null);
    setTongGiaVon(out.tong_gia_von);
    setKhoThanhPham(out.kho_thanh_pham ?? "");
    setLoaiSPId(out.loai_san_pham_id ?? "");
    setComps((out.thanh_phans ?? []).map(fromComponent));
    setResult(out.result);
    // POST/PUT vừa tính lại xong nên BE luôn trả null → bấm "Tính giá" là băng nhắc tự tắt.
    setDanhMucDoi(out.danh_muc_doi ?? null);
  }, []);

  // Nạp nhật ký hoạt động của phiếu (mới→cũ) từ backend. Nhận id tường minh vì ngay sau lần lưu
  // đầu (POST) `pid` chưa kịp vào closure — truyền thẳng id vừa được cấp.
  const loadActs = useCallback((forId: number | null = pid) => {
    if (!token || forId == null) return;
    api.phieuTinhGia
      .activity(token, forId)
      .then((r) => setActs(r.items))
      .catch(() => setActs([]));
  }, [token, pid]);

  // Nạp 4 danh mục. Tách ra hàm riêng vì còn gọi lại khi quay về màn (xem effect ngay dưới).
  const napDanhMuc = useCallback(() => {
    if (!token) return;
    loaiSanPham.list(token).then((r) => setLoaiSPs(r.items)).catch(() => setLoaiSPs([]));
    giay.list(token).then((r) => setGiays(r.items)).catch(() => setGiays([]));
    mayThietBi.list(token).then((r) => setMays(r.items)).catch(() => setMays([]));
    congDoan.list(token).then((r) => setCongDoans(r.items)).catch(() => setCongDoans([]));
  }, [token]);
  useEffect(() => {
    napDanhMuc();
  }, [napDanhMuc]);

  // Sửa/xoá danh mục ở TAB KHÁC (hoặc cửa sổ khác) rồi quay lại tab phiếu ĐANG MỞ: React không tự
  // biết, danh sách trong bộ nhớ vẫn là bản chụp lúc mở phiếu ⇒ ô tìm "Chuỗi công đoạn" còn thấy
  // mục đã xoá, băng nhắc "cần tính lại" cũng không hiện. Nghe `focus`/`visibilitychange` để nạp
  // lại danh mục + hỏi lại BE lời nhắc.
  // ⚠️ CHỈ lấy `danh_muc_doi`, KHÔNG `applyOut(out)`: applyOut ghi đè cả `comps`, quay lại tab là
  // mất sạch chỗ đang gõ dở.
  const moiLamTuoiRef = useRef(0);
  useEffect(() => {
    if (!token) return;
    const lamTuoi = () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - moiLamTuoiRef.current < 3000) return; // chống dội khi focus/visibility cùng bắn
      moiLamTuoiRef.current = now;
      napDanhMuc();
      if (pid != null)
        api.phieuTinhGia
          .get(token, pid)
          .then((out) => setDanhMucDoi(out.danh_muc_doi ?? null))
          .catch(() => {});
    };
    window.addEventListener("focus", lamTuoi);
    document.addEventListener("visibilitychange", lamTuoi);
    return () => {
      window.removeEventListener("focus", lamTuoi);
      document.removeEventListener("visibilitychange", lamTuoi);
    };
  }, [token, pid, napDanhMuc]);

  // Nạp phiếu. id null = phiếu nháp chưa có gì trên server → form rỗng, không gọi API.
  useEffect(() => {
    if (!token || id == null) return;
    let alive = true;
    setLoading(true);
    setErr(null);
    api.phieuTinhGia
      .get(token, id)
      .then((out) => {
        if (alive) {
          applyOut(out);
          loadActs(id);
        }
      })
      .catch((e) => {
        if (alive) setErr(e instanceof ApiError ? e.message : "Không tải được phiếu.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [token, id, applyOut, loadActs]);

  // ---- Chọn loại SP CHO 1 SẢN PHẨM → auto-fill routing công đoạn + tên mặc định ----
  // (Trước đây là handler cấp phiếu; nay theo TỪNG sản phẩm — mỗi SP có loại riêng.)
  const onPickLoaiSPForComp = useCallback(
    (uid: string, pid: number | "") => {
      setComps((cs) =>
        cs.map((c) => {
          if (c.uid !== uid) return c;
          if (pid === "") return { ...c, loai_san_pham_id: null };
          const sp = loaiSPs.find((s) => s.id === pid);
          const patch: Partial<EditableComponent> = { loai_san_pham_id: pid };
          if (sp) {
            const spTen = sp.ten ? String(sp.ten) : "";
            if (spTen && !c.ten.trim()) patch.ten = spTen;
            const routing = Array.isArray(sp.routing_template)
              ? (sp.routing_template as unknown[]).map((x) => Number(x)).filter((n) => !Number.isNaN(n))
              : [];
            // Bung ĐỦ chuỗi công đoạn theo routing Loại SP — KỂ CẢ chế bản/kẽm (prepress) & in (print),
            // KHÔNG lọc bỏ nhóm nào (spec §6: In/Kẽm cũng là công đoạn). Giữ nguyên thứ tự routing.
            const fins = routing
              .map((cid) => congDoans.find((cd) => cd.id === cid))
              .filter((cd): cd is Row => !!cd)
              .map((cd) => blankFinishing(cdName(cd), cd.id));
            if (fins.length > 0) patch.thanh_phams = fins;
          }
          return { ...c, ...patch };
        }),
      );
    },
    [loaiSPs, congDoans],
  );

  // ---- Mutators (immutable, keyed by uid) ----
  const patchComp = useCallback((uid: string, patch: Partial<EditableComponent>) => {
    setComps((cs) => cs.map((c) => (c.uid === uid ? { ...c, ...patch } : c)));
  }, []);
  const removeComp = useCallback((uid: string) => {
    setComps((cs) => cs.filter((c) => c.uid !== uid));
  }, []);
  const addComp = useCallback(() => {
    const c = blankComponent("");
    setComps((cs) => [...cs, { ...c, ten: `Sản phẩm ${cs.length + 1}` }]);
    setEditingUid(c.uid);
  }, []);

  // Chọn giấy → đơn giá + đơn vị (CHỐT CỨNG theo danh mục, read-only). Khổ giấy nguyên KHÔNG còn
  // ở danh mục Giấy → người dùng nhập tay khổ ở phiếu (ô Khổ giấy nguyên ①).
  const onPickGiay = useCallback(
    (uid: string, gid: number | null) => {
      setComps((cs) =>
        cs.map((c) => {
          if (c.uid !== uid) return c;
          if (gid === null) return { ...c, giay_id: null };
          const g = giays.find((x) => x.id === gid);
          if (!g) return { ...c, giay_id: gid };
          // Đổi giấy → đổi giá (không giữ giá cũ) + đồng bộ đơn vị giá theo danh mục.
          return {
            ...c,
            giay_id: gid,
            don_gia_giay: numOf(g.don_gia),
            don_gia_don_vi: (g.don_vi_gia as string) || "kg",
          };
        }),
      );
    },
    [giays],
  );

  // Chọn máy → CHỈ gán may_id. KHÔNG copy thông số máy vào phiếu nữa: engine đọc thẳng
  // `nhip_giay_mm` / `le_hong_mm` / `duoi_thang_mau_mm` từ danh mục máy khi bình bài.
  // (Bản cũ copy mép nhíp BẢN KẼM ~44mm vào `chua_nhip` làm chừa GIẤY rồi trừ cả hai
  //  chiều → hụt 14-19% số con. Các ô `chua_*` giờ chỉ còn là ĐÈ thủ công, trống = theo máy.)
  const onPickMay = useCallback(
    (uid: string, mid: number | null) => {
      setComps((cs) =>
        cs.map((c) =>
          c.uid === uid ? { ...c, may_id: mid, ...(mid === null ? {} : { con_auto: true }) } : c,
        ),
      );
    },
    [],
  );

  const addFin = useCallback((
    cuid: string,
    cong_doan_id: number | null = null,
    ten = "",
    insertIndex: number | null = null
  ) => {
    setComps((cs) =>
      cs.map((c) => {
        if (c.uid !== cuid) return c;
        const newFin = blankFinishing(ten, cong_doan_id);
        const newThanhPhams = [...c.thanh_phams];
        if (insertIndex !== null) {
          newThanhPhams.splice(insertIndex, 0, newFin);
        } else {
          newThanhPhams.push(newFin);
        }
        return { ...c, thanh_phams: newThanhPhams };
      }),
    );
  }, []);
  /** Sửa MỘT dòng công đoạn trong chuỗi của một sản phẩm (hiện chỉ ô Phí khuôn dùng tới). */
  const patchFin = useCallback(
    (cuid: string, fuid: string, patch: Partial<EditableFinishing>) => {
      setComps((cs) =>
        cs.map((c) =>
          c.uid === cuid
            ? {
                ...c,
                thanh_phams: c.thanh_phams.map((f) => (f.uid === fuid ? { ...f, ...patch } : f)),
              }
            : c,
        ),
      );
    },
    [],
  );
  const removeFin = useCallback((cuid: string, fuid: string) => {
    setComps((cs) =>
      cs.map((c) =>
        c.uid === cuid ? { ...c, thanh_phams: c.thanh_phams.filter((f) => f.uid !== fuid) } : c,
      ),
    );
  }, []);

  // ---- Bình bài LIVE: gọi /binh-bai (debounce) → đổ so_con cho thành phần con_auto ----
  // Chữ ký loại trừ so_con để patch kết quả KHÔNG tự kích lại (tránh vòng lặp).
  const binhBaiSig = useMemo(
    () =>
      JSON.stringify(
        comps.map((c) => {
          const ch = chuaTheoChieu(c, c.may_id ? mays.find((x) => x.id === c.may_id) : null);
          return {
            u: c.uid,
            a: c.con_auto,
            kd: c.kho_in_dai,
            kr: c.kho_in_rong,
            d: c.dai_thanh_pham,
            r: c.rong_thanh_pham,
            cd: ch.dai,
            cr: ch.rong,
            bl: c.bleed_mm,
            ke: c.khe_cat_mm,
          };
        }),
      ),
    [comps, mays],
  );
  useEffect(() => {
    if (!token) return;
    const rows = JSON.parse(binhBaiSig) as {
      u: string;
      a: boolean;
      kd: number;
      kr: number;
      d: number;
      r: number;
      cd: number;
      cr: number;
      bl: number;
      ke: number;
    }[];
    const targets = rows.filter((x) => x.a && x.kd > 0 && x.kr > 0 && x.d > 0 && x.r > 0);
    if (targets.length === 0) return;
    const h = window.setTimeout(() => {
      targets.forEach((x) => {
        api.tinhGia
          .binhBai(token, {
            kho_in_dai: x.kd,
            kho_in_rong: x.kr,
            dai_thanh_pham: x.d,
            rong_thanh_pham: x.r,
            chua_dai_mm: x.cd,
            chua_rong_mm: x.cr,
            bleed_mm: x.bl,
            khe_cat_mm: x.ke,
          })
          .then(({ con }) => {
            if (con >= 1)
              setComps((cs) => cs.map((c) => (c.uid === x.u && c.con_auto ? { ...c, so_con: con } : c)));
          })
          .catch(() => {});
      });
    }, 300);
    return () => window.clearTimeout(h);
  }, [binhBaiSig, token]);

  // ---- Số tờ LIVE trong modal: gọi /preview cho SP đang mở (debounce) → editMeta ----
  const phieuSL = result?.meta?.so_luong ?? 0;
  const editingComp = comps.find((c) => c.uid === editingUid) ?? null;
  const previewSig = useMemo(() => {
    if (!editingComp) return "";
    const c = editingComp;
    return JSON.stringify({
      psl: phieuSL,
      sl: c.so_luong,
      kd: c.kho_in_dai, kr: c.kho_in_rong, d: c.dai_thanh_pham, r: c.rong_thanh_pham,
      knd: c.kho_nguyen_dai, knr: c.kho_nguyen_rong,
      ca: c.con_auto, sc: c.so_con, tr: c.so_trang, tmt: c.trang_moi_tay, qc: c.quy_cach_in,
      // Ký theo TẬP mực, không theo ba số dẫn xuất: server ghi đè ba số đó nên chúng không đổi
      // ngay khi bấm chip, ký nhầm vào chúng là preview đứng im trong khi số kẽm đã khác.
      ma: c.muc_a, mb: c.muc_b,
      ch: c.chua_nhip,
      bl: c.bleed_mm, ke: c.khe_cat_mm,
      // Chuỗi công đoạn: ký theo CẢ `phi_khuon`, không chỉ `cong_doan_id`. Thiếu nó thì gõ tiền
      // dao xong chữ ký không đổi ⇒ KHÔNG gọi lại engine ⇒ khối bên phải đứng im, phải bấm Xong
      // rồi mở lại mới thấy. (Σ bên trái vẫn nhảy ngay vì nó cộng từ state, không qua engine —
      // nên hai bên lệch nhau mà nhìn thoáng qua tưởng đã cập nhật.)
      //
      // ⚠️ LUẬT CHUNG: thêm bất kỳ ô nhập nào ảnh hưởng số của engine thì phải khai vào chữ ký này.
      gid: c.giay_id, may: c.may_id,
      cds: c.thanh_phams.map((f) => [f.cong_doan_id, f.phi_khuon]),
    });
  }, [editingComp, phieuSL]);
  useEffect(() => {
    if (!token || !editingComp) {
      setEditMeta(null);
      setEditGia(null);
      return;
    }
    const snapshot = editingComp;
    const h = window.setTimeout(() => {
      api.tinhGia
        .preview(token, { so_luong: phieuSL, thanh_phans: [toThanhPhanIn(snapshot)] })
        .then((r) => {
          setEditMeta(r.meta?.components?.[0] ?? null);
          // `/preview` được gọi với ĐÚNG MỘT sản phẩm nên `groups` đã là của riêng nó — không
          // phải lọc, cũng không cần backend gửi thêm bản sao theo từng sản phẩm.
          setEditGia(r.groups ?? null);
        })
        .catch(() => {});
    }, 300);
    return () => window.clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewSig, token]);

  // "Tính giá" = LƯU + TÍNH LẠI (BE) → refresh từ Out.
  // Phiếu NHÁP (chưa có pid): lần này mới POST — và chỉ POST khi đã có sản phẩm. Phiếu 0 sản phẩm
  // có giá vốn 0, không mang thông tin gì; ghi nó xuống DB chỉ để lại rác + ăn mất một số PTG.
  const calc = useCallback(() => {
    if (!token) return;
    const payload = {
      kho_thanh_pham: khoThanhPham.trim() || null,
      loai_san_pham_id: loaiSPId === "" ? null : loaiSPId,
      thanh_phans: comps.map(toThanhPhanIn),
    };
    if (pid == null && comps.length === 0) {
      setErr("Thêm ít nhất 1 sản phẩm rồi mới tính giá — phiếu trống không được lưu.");
      return;
    }
    setCalcing(true);
    setErr(null);
    const req = pid == null
      ? api.phieuTinhGia.create(token, payload)
      : api.phieuTinhGia.update(token, pid, payload);
    req
      .then((out) => {
        setPid(out.id);
        applyOut(out);
        loadActs(out.id); // phản ánh ngay dòng "Lập phiếu" / "Cập nhật phiếu" vừa ghi.
      })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tính được giá. Thử lại."))
      .finally(() => setCalcing(false));
  }, [token, pid, khoThanhPham, loaiSPId, comps, applyOut, loadActs]);

  // #1 — Sửa sản phẩm XONG (đóng modal: Xong / X / bấm ra ngoài) mà CÓ thay đổi → tự tính lại
  // giá ngay, khỏi bấm "Tính giá" riêng. Chụp snapshot lúc mở để so khi đóng (chỉ tính khi dirty).
  const editSnapRef = useRef<string | null>(null);
  useEffect(() => {
    const c = editingUid ? comps.find((x) => x.uid === editingUid) : null;
    editSnapRef.current = c ? JSON.stringify(toThanhPhanIn(c)) : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingUid]);
  const closeEditor = useCallback(() => {
    const c = comps.find((x) => x.uid === editingUid);
    const now = c ? JSON.stringify(toThanhPhanIn(c)) : null;
    const changed = editSnapRef.current !== null && now !== editSnapRef.current;
    setEditingUid(null);
    if (changed) calc();
  }, [comps, editingUid, calc]);
  // Tính lại HOÃN 1 nhịp sau khi comps đã cập nhật (dùng cho xóa sản phẩm — tránh dùng comps cũ).
  const [pendingCalc, setPendingCalc] = useState(false);
  useEffect(() => {
    if (!pendingCalc) return;
    setPendingCalc(false);
    calc();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingCalc]);

  // BG-3: từ phiếu tính giá → LUÔN tạo 1 phiếu báo giá MỚI (1 PTG → nhiều BG). Không ghi tiếp
  // phiếu cũ; muốn điều chỉnh 1 báo giá đã có thì dùng "Tạo phiên bản mới" TRONG phiếu đó.
  async function openOrCreateQuote() {
    if (!token || !navigate || pid == null) return;
    setQuoting(true);
    setErr(null);
    try {
      const q = await api.quotations.create(token, {
        phieu_tinh_gia_id: pid, customer_id: null, valid_until: null,
        customer_note: null, internal_note: null,
      });
      navigate("bao-gia", { openQuoteId: q.id });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không mở được báo giá cho phiếu này.");
    } finally {
      setQuoting(false);
    }
  }

  const grand = result ? result.grand_total : null;
  // Đơn giá BÌNH QUÂN (nhiều SP khác SL) — ưu tiên meta engine; fallback grand/ΣSL.
  const tongSoLuong = result?.meta?.tong_so_luong ?? 0;
  const perPiece =
    result?.meta?.gia_von_don != null && result.meta.gia_von_don > 0
      ? Math.round(result.meta.gia_von_don)
      : result && tongSoLuong > 0
        ? Math.round(result.grand_total / tongSoLuong)
        : null;

  // Danh sách HIỂN THỊ: các dòng cùng nhóm kéo về nằm cạnh nhau, tại vị trí dòng đầu của nhóm.
  // Dòng lẻ giữ nguyên chỗ. Không đổi thứ tự dữ liệu (`comps`) — chỉ đổi cách bày ra bảng + bản in.
  const [nhomThu, setNhomThu] = useState<Set<string>>(new Set());
  const idxByUid = useMemo(() => {
    const m = new Map<string, number>();
    comps.forEach((c, i) => m.set(c.uid, i));
    return m;
  }, [comps]);
  const danhSachHienThi = useMemo<NodeHienThi[]>(() => {
    const out: NodeHienThi[] = [];
    const viTri = new Map<string, number>();
    for (const c of comps) {
      const nh = c.nhom_bao_gia.trim();
      if (!nh) {
        out.push({ kind: "don", comp: c });
        continue;
      }
      const k = nh.toLowerCase();
      const at = viTri.get(k);
      if (at === undefined) {
        viTri.set(k, out.length);
        out.push({ kind: "nhom", key: k, ten: nh, members: [c] });
      } else {
        (out[at] as { members: EditableComponent[] }).members.push(c);
      }
    }
    return out;
  }, [comps]);

  const phieu = useMemo(() => {
    if (!result) return null;
    // Tên + SL trên bản in tính THEO NHÓM: ruột + bìa của 1 cuốn là MỘT sản phẩm thương mại,
    // nên tên lấy tên nhóm và SL không cộng dồn (5.000 cuốn, không phải 5.000 ruột + 5.000 bìa).
    const slCua = (c: EditableComponent) => (c.so_luong > 0 ? c.so_luong : phieuSL);
    const names: string[] = [];
    // SL gom THEO ĐƠN VỊ TÍNH, không cộng thành một số. Phiếu này có 500 cuốn + 1.000 thẻ; cộng
    // lại ra "1.500" là một con số không đếm được thứ gì — cuốn và thẻ không cùng đơn vị.
    const slTheoDv = new Map<string, number>();
    for (const node of danhSachHienThi) {
      const c = node.kind === "don" ? node.comp : node.members[0];
      if (node.kind === "don") {
        const t = (node.comp.ten || "").trim();
        if (t) names.push(t);
      } else {
        names.push(node.ten);
      }
      const dv = (c.don_vi_tinh || "cái").trim() || "cái";
      slTheoDv.set(dv, (slTheoDv.get(dv) ?? 0) + slCua(c));
    }
    const slPhieu = [...slTheoDv]
      .map(([dv, n]) => `${n.toLocaleString("vi-VN")} ${dv}`)
      .join(" · ") || "—";
    const tenAnPham =
      names.length === 0
        ? "—"
        : names.length <= 3
          ? names.join(", ")
          : `${names.slice(0, 3).join(", ")} +${names.length - 3} SP`;
    const sanPhams = comps.map((c) => ({
      ten: c.ten,
      soLuong: slCua(c), // SL riêng của SP, =0 thì lấy SL mặc định phiếu
      dvt: c.don_vi_tinh,
      nhom: c.nhom_bao_gia.trim() || null,
    }));
    return toPhieu(
      result, ma || "(chưa lưu)", tenAnPham, slPhieu, khoThanhPham,
      ngay ? new Date(ngay).toLocaleDateString("vi-VN") : null,
      sanPhams, traDv,
    );
  }, [result, ma, khoThanhPham, comps, danhSachHienThi, phieuSL, traDv, ngay]);

  // Số [Hiện] chốt từ engine, index theo vị trí thành phần.
  const metaByIdx = useMemo(() => {
    const list = result?.meta?.components ?? [];
    const map = new Map<number, TinhGiaComponentMeta>();
    for (const m of list) map.set(m.idx, m);
    return map;
  }, [result]);

  // Loại SP theo id → nhãn (cho cột "Loại" của list + fallback về loại thành phần cấu trúc).
  const loaiSPById = useMemo(() => {
    const map = new Map<number, Row>();
    for (const s of loaiSPs) map.set(s.id, s);
    return map;
  }, [loaiSPs]);
  /** Nhãn cột "Loại" — `null` = CHƯA chọn loại sản phẩm, để chỗ hiện nói thẳng ra.
   *
   *  Không rơi về `loai_thanh_phan` nữa: màn này không có ô nào cho khai nó, nên mọi sản phẩm
   *  mới đều mang mặc định `to_roi` ⇒ bảng in "Tờ rời" y như đã chọn loại, trong khi thực tế
   *  người lập phiếu chưa chọn gì (lỗi 7, 25/08/2026). Chỉ dùng lại nó cho phiếu cũ có khai
   *  thật (bìa · ruột · thân · nắp…). */
  const loaiLabelOf = useCallback(
    (c: EditableComponent): string | null => {
      if (c.loai_san_pham_id != null) {
        const sp = loaiSPById.get(c.loai_san_pham_id);
        if (sp?.ten) return String(sp.ten);
      }
      const tp = c.loai_thanh_phan;
      return tp && tp !== "to_roi" ? loaiTpLabel(tp) : null;
    },
    [loaiSPById],
  );

  /** Các sản phẩm CHƯA chọn loại — khoá cửa "Báo giá →" lại. Đây là chỗ "ép chọn": loại quyết
   *  định dòng gộp và nhãn đơn vị trên báo giá gửi khách, để trống là in ra sai nhóm. Khoá tại
   *  chỗ + gọi tên sản phẩm còn thiếu, KHÔNG ẩn nút (ẩn thì người dùng tưởng hỏng). Vẫn cho
   *  "Tính giá" bình thường — tính giá vốn không cần loại. */
  const spThieuLoai = useMemo(
    () => comps.filter((c) => loaiLabelOf(c) === null).map((c) => c.ten || "(chưa đặt tên)"),
    [comps, loaiLabelOf],
  );

  const summaryRows = useMemo(() => {
    if (!result) return [];
    return [
      ...result.groups.map((g) => ({ label: g.name, value: `${fmt(g.subtotal)} đ`, total: false })),
      { label: "Tổng giá vốn", value: `${fmt(result.grand_total)} đ`, total: true },
    ];
  }, [result]);

  // --- GỘP DÒNG KHI BÁO GIÁ ---------------------------------------------------
  // Nhóm là quan hệ GIỮA các dòng (ruột + bìa = 1 cuốn) nên thao tác đặt ở LIST: tick 2 dòng,
  // gõ tên 1 lần. Nhét ô nhập vào drawer từng dòng là bắt mở 2 lần + gõ đúng y chữ 2 lần.
  const [chonUids, setChonUids] = useState<Set<string>>(new Set());
  const [tenNhom, setTenNhom] = useState("");
  const nhomDaCo = useMemo(
    () => Array.from(new Set(comps.map((c) => c.nhom_bao_gia.trim()).filter(Boolean))),
    [comps],
  );
  const toggleChon = useCallback((uid: string) => {
    setChonUids((s) => {
      const n = new Set(s);
      if (n.has(uid)) n.delete(uid);
      else {
        n.add(uid);
        // Tick dòng đã có nhóm → điền sẵn tên đó, khỏi gõ lại (và khỏi gõ lệch chính tả).
        setTenNhom((cur) => cur || (comps.find((c) => c.uid === uid)?.nhom_bao_gia.trim() ?? ""));
      }
      return n;
    });
  }, [comps]);
  // Gộp / bỏ gộp TỰ LƯU luôn (hoãn 1 nhịp cho `comps` cập nhật xong rồi mới gọi) — khớp với
  // sửa-trong-drawer và xoá-sản-phẩm; bắt bấm thêm "Tính giá" chỉ để lưu một cái nhãn là vô lý.
  const apDungNhom = useCallback(() => {
    const ten = tenNhom.trim();
    if (!ten) return;
    setComps((cs) => cs.map((c) => (chonUids.has(c.uid) ? { ...c, nhom_bao_gia: ten } : c)));
    setChonUids(new Set());
    setTenNhom("");
    setPendingCalc(true);
  }, [chonUids, tenNhom]);
  const boNhom = useCallback(() => {
    setComps((cs) => cs.map((c) => (chonUids.has(c.uid) ? { ...c, nhom_bao_gia: "" } : c)));
    setChonUids(new Set());
    setTenNhom("");
    setPendingCalc(true);
  }, [chonUids]);

  const editing = comps.find((c) => c.uid === editingUid) ?? null;
  const editingIdx = editing ? comps.findIndex((c) => c.uid === editingUid) : -1;

  // Rời phiếu: nháp đang có sản phẩm mà chưa lưu thì hỏi trước — thoát là mất trắng phần đã nhập
  // (phiếu chưa tồn tại trên server nên không có gì để mở lại).
  const thoat = useCallback(() => {
    if (!daLuu && comps.length > 0) {
      setHoiThoat(true);
      return;
    }
    onBack();
  }, [daLuu, comps.length, onBack]);

  return (
    <main className="rdx-cost tg-page">
      {/* ---------- HEAD ---------- */}
      <header className="tg-head">
        <div className="tg-head__lead">
          <button type="button" className="tg-back" onClick={thoat}>
            <BackIcon /> Danh sách
          </button>
          <div className="eyebrow tg-head__eyebrow">
            <LockIcon /> Giá vốn nội bộ
          </div>
          <div className="tg-head__titlerow">
            <h1 className="tg-head__title">{ma || "Phiếu mới"}</h1>
            {/* Nói thẳng phiếu chưa nằm trong sổ — mã PTG chỉ được cấp khi lưu thật. */}
            {!daLuu && <span className="badge neutral"><span className="d" />Chưa lưu</span>}
          </div>
        </div>
        <div className="tg-head__actions">
          <Button
            variant="accent"
            onClick={calc}
            loading={calcing}
            disabled={!token || loading || (!daLuu && comps.length === 0)}
            title={
              !daLuu && comps.length === 0
                ? "Thêm sản phẩm trước — phiếu trống không được lưu"
                : "Lưu phiếu & tính lại giá vốn"
            }
          >
            {daLuu ? "Tính giá" : "Tính giá & lưu"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => window.print()}
            disabled={!phieu}
            title={phieu ? "In phiếu tính giá" : "Tính giá trước khi in"}
          >
            In phiếu
          </Button>
          {navigate && (
            <Button
              variant="primary"
              onClick={openOrCreateQuote}
              loading={quoting}
              disabled={!token || loading || !daLuu || spThieuLoai.length > 0}
              title={
                !daLuu
                  ? "Tính giá & lưu phiếu trước khi báo giá"
                  : spThieuLoai.length > 0
                    ? `Chọn loại sản phẩm cho: ${keTen(spThieuLoai)} — loại quyết định dòng gộp và nhãn đơn vị trên báo giá.`
                    : "Tạo / mở báo giá từ phiếu tính giá này"
              }
            >
              Báo giá →
            </Button>
          )}
        </div>
      </header>

      {err ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-4)" }}>
          <span>{err}</span>
        </div>
      ) : null}

      {danhMucDoi ? (
        <div
          className={`banner banner--${dmXoa.length ? "error" : "warn"}`}
          role={dmXoa.length ? "alert" : "status"}
          style={{ marginTop: "var(--sp-4)" }}
        >
          <span>
            <b>Danh mục đã đổi sau lần tính {fmtActDateTime(danhMucDoi.luc)}</b> — phiếu đang giữ số
            và tên của lần tính đó.{" "}
            {[
              dmXoa.length ? `Đã xoá khỏi danh mục: ${keTen(dmXoa)}` : "",
              dmNgung.length ? `Đã ngừng dùng: ${keTen(dmNgung)}` : "",
              danhMucDoi.ten.length ? `Đã sửa: ${keTen(danhMucDoi.ten)}` : "",
            ]
              .filter(Boolean)
              .join(". ")}
            .
            {dmXoa.length ? (
              <>
                {" "}
                Mục đã xoá thì tính lại là dòng đó <b>mất cấu hình danh mục</b> — chọn công đoạn/vật
                tư khác thay vào trước khi tính.
              </>
            ) : dmNgung.length ? (
              <>
                {" "}
                Mục ngừng dùng vẫn tính ra số, nhưng lần sau <b>không chọn lại được</b>.
              </>
            ) : null}
          </span>
          <Button variant="secondary" onClick={calc} loading={calcing} disabled={!token}>
            Tính giá lại
          </Button>
        </div>
      ) : null}

      {loading ? (
        <div className="tg-empty" style={{ marginTop: "var(--sp-5)" }}>
          <p className="tg-empty__title">Đang tải phiếu…</p>
        </div>
      ) : (
        <div className="tg-split">
          {/* ============ LEFT ============ */}
          <div className="tg-main">


            {/* --- Panel: DANH SÁCH SẢN PHẨM (list + modal) --- */}
            <section className="panel">
              <div className="panel__hd">
                <h3><GridIcon /> Sản phẩm trong phiếu</h3>
                <span className="tag">{comps.length} sản phẩm</span>
              </div>
              {comps.length === 0 ? (
                <div className="tg-empty tg-empty--sm">
                  <p className="tg-empty__title">Chưa có sản phẩm</p>
                  <p className="tg-empty__sub">
                    Bấm “Thêm sản phẩm”, rồi chọn loại sản phẩm trong drawer để tự bung cấu hình.
                  </p>
                </div>
              ) : (
                <>
                {/* Thanh gộp: chỉ hiện khi có dòng được tick — không chiếm chỗ lúc không dùng. */}
                {chonUids.size > 0 && (
                  <div className="tg-gopbar" role="group" aria-label="Gộp dòng khi báo giá">
                    <span className="tg-gopbar__count">{chonUids.size} dòng đã chọn</span>
                    <input
                      className="tg-input tg-gopbar__input"
                      type="text"
                      list="tg-nhom-goiy"
                      value={tenNhom}
                      placeholder="Tên in ra báo giá, vd Sách hướng dẫn A5"
                      aria-label="Tên nhóm in ra báo giá"
                      onChange={(e) => setTenNhom(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          apDungNhom();
                        }
                      }}
                    />
                    <datalist id="tg-nhom-goiy">
                      {nhomDaCo.map((n) => (
                        <option key={n} value={n} />
                      ))}
                    </datalist>
                    <button
                      type="button"
                      className="tg-chip tg-chip--on"
                      onClick={apDungNhom}
                      disabled={!tenNhom.trim()}
                    >
                      Gộp khi báo giá
                    </button>
                    <button type="button" className="tg-chip" onClick={boNhom}>
                      Bỏ gộp
                    </button>
                  </div>
                )}
                <div className="tg-complist__wrap">
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: "34px" }} aria-label="Chọn để gộp" />
                        <th style={{ width: "44px" }}>#</th>
                        <th>Tên</th>
                        <th>Loại</th>
                        <th className="num">SL</th>
                        <th className="num">Giá vốn</th>
                        <th className="num">Đơn giá</th>
                        <th className="num" style={{ width: "56px" }} aria-label="Hành động" />
                      </tr>
                    </thead>
                    <tbody>
                      {danhSachHienThi.flatMap((node) => {
                        // Dòng SẢN PHẨM THẬT — dùng chung cho dòng lẻ và dòng con trong nhóm.
                        const dongSP = (c: EditableComponent, con: boolean, cuoi = false) => {
                          const i = idxByUid.get(c.uid) ?? 0;
                          const meta = metaByIdx.get(i);
                          // SL hiệu lực từ STATE LOCAL (phản ánh ngay khi sửa; 0 = lấy SL phiếu).
                          const sl = c.so_luong > 0 ? c.so_luong : phieuSL;
                          const thieu =
                            !c.giay_id || c.dai_thanh_pham <= 0 || c.rong_thanh_pham <= 0;
                          return (
                            <tr
                              key={c.uid}
                              className={`prow${con ? " prow--con" : ""}${cuoi ? " prow--conCuoi" : ""}`}
                              onClick={() => setEditingUid(c.uid)}
                            >
                              <td className="prow__pick" onClick={(e) => e.stopPropagation()}>
                                <input
                                  type="checkbox"
                                  checked={chonUids.has(c.uid)}
                                  onChange={() => toggleChon(c.uid)}
                                  aria-label={`Chọn "${c.ten || "sản phẩm"}" để gộp khi báo giá`}
                                />
                              </td>
                              <td className="mono">{i + 1}</td>
                              <td>
                                <span className="pname">{c.ten || "(chưa đặt tên)"}</span>
                                {thieu && (
                                  <span
                                    className="tg-warn-chip"
                                    title="Chưa đủ khổ thành phẩm hoặc chưa chọn giấy — số con/giá vốn chưa chính xác."
                                  >
                                    <WarnIcon /> thiếu khổ/giấy
                                  </span>
                                )}
                              </td>
                              <td>
                                {loaiLabelOf(c) ? (
                                  <span className="badge neutral">
                                    <span className="d" />
                                    {loaiLabelOf(c)}
                                  </span>
                                ) : (
                                  <span
                                    className="tg-warn-chip"
                                    title="Chưa chọn loại sản phẩm — mở sản phẩm để chọn, chuỗi công đoạn mặc định cũng bung theo loại."
                                  >
                                    <WarnIcon /> chưa chọn loại
                                  </span>
                                )}
                              </td>
                              <td className="num mono">{sl > 0 ? fmt(sl) : "—"}</td>
                              <td className="num strong">
                                {c.gia_von_tp > 0 ? `${fmt(c.gia_von_tp)} đ` : "—"}
                              </td>
                              <td className="num rust-num">
                                {meta && meta.gia_von_don > 0 ? `${fmt(meta.gia_von_don)} đ` : "—"}
                              </td>
                              <td className="prow__act" onClick={(e) => e.stopPropagation()}>
                                <button
                                  type="button"
                                  className="tg-icon-btn tg-icon-btn--danger"
                                  onClick={() => removeComp(c.uid)}
                                  title="Xóa sản phẩm"
                                  aria-label="Xóa sản phẩm"
                                >
                                  <TrashIcon />
                                </button>
                              </td>
                            </tr>
                          );
                        };

                        if (node.kind === "don") return [dongSP(node.comp, false)];

                        // --- DẢI NHÓM: đúng con số khách sẽ thấy trên báo giá (tổng + đơn giá/cuốn).
                        const thu = nhomThu.has(node.key);
                        const tongVon = node.members.reduce((s, m) => s + m.gia_von_tp, 0);
                        const slNhom =
                          node.members[0].so_luong > 0 ? node.members[0].so_luong : phieuSL;
                        const dvt = node.members[0].don_vi_tinh || "cái";
                        // Gộp là gộp CHO KHÁCH: bản in ghi 1 dòng, SL lấy phần ĐẦU vì khách mua
                        // 10.000 cuốn chứ không phải 10.000 ruột + 10.000 bìa (`utils/gop-nhom`).
                        // Quy ước đó chỉ đúng khi các phần CÙNG số lượng, nên bản in nay CHỈ gộp
                        // các phần cùng SL (chốt 26/08/2026); lệch thì nó tự tách dòng. Ở đây phải
                        // nói trước con số đó, đừng để tới lúc soạn báo giá mới lộ: dải nhóm hiện
                        // sẽ in ra mấy dòng, và bỏ trống SL/đơn giá vì cả cụm không còn một con số
                        // chung nào cả.
                        const phanSL = node.members.map((m) => ({
                          ten: m.ten || "(chưa đặt tên)",
                          sl: m.so_luong > 0 ? m.so_luong : phieuSL,
                          dvt: (m.don_vi_tinh || "cái").trim(),
                        }));
                        const cumIn = new Set(phanSL.map((x) => x.sl));
                        const lechNhom = cumIn.size > 1;
                        const uids = node.members.map((m) => m.uid);
                        const tickCaNhom = uids.every((u) => chonUids.has(u));
                        return [
                          <tr key={`nh-${node.key}`} className="grouphd">
                            <td className="prow__pick">
                              <input
                                type="checkbox"
                                checked={tickCaNhom}
                                onChange={() =>
                                  setChonUids((s) => {
                                    const n = new Set(s);
                                    if (tickCaNhom) uids.forEach((u) => n.delete(u));
                                    else uids.forEach((u) => n.add(u));
                                    return n;
                                  })
                                }
                                aria-label={`Chọn cả nhóm "${node.ten}"`}
                              />
                            </td>
                            <td>
                              <button
                                type="button"
                                className="grouphd__toggle"
                                aria-expanded={!thu}
                                onClick={() =>
                                  setNhomThu((s) => {
                                    const n = new Set(s);
                                    if (n.has(node.key)) n.delete(node.key);
                                    else n.add(node.key);
                                    return n;
                                  })
                                }
                              >
                                <ChevronIcon open={!thu} />
                              </button>
                            </td>
                            <td>
                              <span className="grouphd__ten">{node.ten}</span>
                              <span className="grouphd__sub">
                                {node.members.length} sản phẩm ·{" "}
                                {lechNhom
                                  ? `in ${cumIn.size} dòng khi báo giá`
                                  : "gộp 1 dòng khi báo giá"}
                              </span>
                              {lechNhom && (
                                <span
                                  className="tg-warn-chip"
                                  title={`Các phần lệch nhau: ${phanSL
                                    .map((x) => `${x.ten} ${fmt(x.sl)} ${x.dvt}`)
                                    .join(
                                      " · ",
                                    )}. Chỉ các phần cùng số lượng mới gộp chung, nên bản gửi khách sẽ in ${
                                    cumIn.size
                                  } dòng cho nhãn này. Sửa SL cho khớp nếu muốn về 1 dòng.`}
                                >
                                  <WarnIcon /> các phần lệch số lượng
                                </span>
                              )}
                            </td>
                            <td />
                            <td className="num mono">
                              {lechNhom ? "—" : slNhom > 0 ? fmt(slNhom) : "—"}
                            </td>
                            <td className="num strong">
                              {tongVon > 0 ? `${fmt(tongVon)} đ` : "—"}
                            </td>
                            <td className="num rust-num">
                              {lechNhom
                                ? "—"
                                : tongVon > 0 && slNhom > 0
                                  ? `${fmt(Math.round(tongVon / slNhom))} đ/${dvt}`
                                  : "—"}
                            </td>
                            <td className="prow__act">
                              <button
                                type="button"
                                className="grouphd__bo"
                                onClick={() =>
                                  setComps((cs) =>
                                    cs.map((c) =>
                                      uids.includes(c.uid) ? { ...c, nhom_bao_gia: "" } : c,
                                    ),
                                  )
                                }
                                title="Bỏ gộp — các dòng lại đứng riêng trên báo giá"
                              >
                                Bỏ gộp
                              </button>
                            </td>
                          </tr>,
                          ...(thu
                            ? []
                            : node.members.map((m, k) =>
                                dongSP(m, true, k === node.members.length - 1),
                              )),
                        ];
                      })}
                    </tbody>
                  </table>
                </div>
                </>
              )}
              <div className="addbtn">
                <button type="button" onClick={addComp}>
                  <PlusIcon /> Thêm sản phẩm
                </button>
              </div>
            </section>

            {/* --- Chi tiết dòng giá vốn (Diễn giải người-đọc-được) --- */}
            {/* Chỉ hiện khi CÒN sản phẩm — xóa hết sản phẩm thì bảng NVL/Công đoạn (result cũ server
                trả về) không còn ý nghĩa, phải về trạng thái rỗng cho khớp panel "Sản phẩm trong phiếu". */}
            {result && comps.length > 0 ? (
              <section className="panel">
                <div className="panel__hd">
                  <h3><RowsIcon /> Chi tiết dòng giá vốn</h3>
                  <span className="tag">Nguyên vật liệu · Công đoạn</span>
                </div>
                {result.groups.map((g, gi) => (
                  <div key={g.idx}>
                    <div className="secttl">
                      <span className="secttl__n">{gi + 1}</span>
                      {g.name}
                    </div>
                    <div className="tg-cost__scroll">
                      <table>
                        <thead>
                          <tr>
                            {g.columns.map((col) => (
                              <th key={col.key} className={headClass(col) || undefined}>
                                {col.kind === "formula" ? "Diễn giải" : col.label}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {g.rows.length === 0 ? (
                            <tr>
                              <td colSpan={g.columns.length} className="tg-cost__none">
                                (không có dòng)
                              </td>
                            </tr>
                          ) : (
                            g.rows.map((r, ri) => (
                              <tr key={ri}>
                                {g.columns.map((col) => {
                                  const val = cellValue(r[col.key]);
                                  return (
                                    <td key={col.key} className={cellClass(col) || undefined}>
                                      {col.kind === "formula" && val ? (
                                        <span className="derive">{humanizeFormula(val, traDv)}</span>
                                      ) : (
                                        val
                                      )}
                                    </td>
                                  );
                                })}
                              </tr>
                            ))
                          )}
                          <tr className="sub">
                            <td colSpan={g.columns.length}>
                              <div className="subrow">
                                <span className="lbl">Cộng {g.name}</span>
                                <span className="val">{fmt(g.subtotal)} đ</span>
                              </div>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
                <div className="tg-cost__grand">
                  <span>Tổng giá vốn</span>
                  <span className="tg-cost__grandval">{fmt(result.grand_total)} đ</span>
                </div>
              </section>
            ) : (
              <section className="panel">
                <div className="tg-empty">
                  <CalcIcon />
                  <p className="tg-empty__title">Chưa có kết quả</p>
                  <p className="tg-empty__sub">
                    Cấu hình sản phẩm rồi bấm <b>Tính giá</b> để xem bảng 2 nhóm (Nguyên vật liệu ·
                    Công đoạn).
                  </p>
                </div>
              </section>
            )}
          </div>

          {/* ============ RIGHT (sticky) ============ */}
          <aside className="tg-side">
            {/* Dark card: TỔNG GIÁ VỐN · nội bộ */}
            <div className="dk">
              <div className="dk__hd">
                <div className="dk__eyebrow"><LockIcon /> Tổng giá vốn · nội bộ</div>
              </div>
              <div className="dk__big">
                {grand == null ? "—" : fmt(grand)}
                <span className="u">đ</span>
              </div>
              {perPiece != null && comps.length <= 1 ? (
                <div className="dk__meta">≈ {fmt(perPiece)} đ · đơn giá bình quân</div>
              ) : tongSoLuong > 0 ? (
                <div className="dk__meta">{fmt(comps.length)} sản phẩm · tổng {fmt(tongSoLuong)} SP</div>
              ) : (
                <div className="dk__meta">Giá vốn sản xuất · chưa gồm lợi nhuận</div>
              )}
              {summaryRows.length > 0 ? (
                <div className="dk__rows">
                  {summaryRows.map((row, i) => (
                    <div key={i} className={`drow${row.total ? " total" : ""}`}>
                      <span className="k">{row.label}</span>
                      <span className="v">{row.value}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>


            {/* Phiếu này */}
            <section className="panel">
              <div className="panel__hd"><h3><FileIcon /> Phiếu này</h3></div>
              <div className="info">
                <div className="irow"><span className="k">Mã phiếu</span><span className="v mono">{ma || "Cấp khi lưu"}</span></div>
                <div className="irow"><span className="k">Người lập</span><span className="v">{ktv ?? "—"}</span></div>
                <div className="irow"><span className="k">Ngày lập</span><span className="v">{ngay ? new Date(ngay).toLocaleDateString("vi-VN") : "—"}</span></div>
                <div className="irow">
                  <span className="k">Trạng thái</span>
                  <span className="v">
                    {!daLuu ? (
                      <span className="badge neutral"><span className="d" />Chưa lưu</span>
                    ) : result && result.grand_total > 0 ? (
                      <span className="badge soft"><span className="d" />Đã tính giá</span>
                    ) : (
                      <span className="badge neutral"><span className="d" />Nháp</span>
                    )}
                  </span>
                </div>
                <div className="irow"><span className="k">Giá vốn tổng</span><span className="v mono">{tongGiaVon == null ? "—" : `${fmt(tongGiaVon)} đ`}</span></div>
                <div className="irow"><span className="k">Số sản phẩm</span><span className="v mono">{fmt(comps.length)}</span></div>
                {tongSoLuong > 0 ? (
                  <div className="irow"><span className="k">Tổng SL</span><span className="v mono">{fmt(tongSoLuong)}</span></div>
                ) : null}
              </div>
            </section>

            {/* Hoạt động — ai làm gì · khi nào (dữ liệu THẬT; empty-state khi chưa có) */}
            <section className="panel">
              <div className="panel__hd">
                <h3><BoltIcon /> Hoạt động</h3>
                {acts.length > 5 ? (
                  <button type="button" className="viewall" onClick={() => setShowAllActs((s) => !s)}>
                    {showAllActs ? "Thu gọn" : `Xem tất cả (${acts.length})`}
                    <ChevronIcon open={showAllActs} />
                  </button>
                ) : null}
              </div>
              {acts.length === 0 ? (
                <div className="tl">
                  <p className="tg-empty__sub" style={{ margin: "4px 0" }}>
                    {daLuu ? "Chưa có hoạt động." : "Nhật ký bắt đầu từ lần lưu đầu tiên."}
                  </p>
                </div>
              ) : (
                <div className="tl scrollbox">
                  {(showAllActs ? acts : acts.slice(0, 5)).map((a, i) => {
                    const label = PTG_ACT_META[a.action]?.[1] ?? a.action;
                    return (
                      <div className={`tlrow${i > 0 ? " mut" : ""}`} key={i}>
                        <span className="tlic"><ActIcon action={a.action} /></span>
                        <div className="tlb">
                          <div className="a">
                            <b>{label}</b>
                            {a.actor_name ? <> — {a.actor_name}</> : null}
                          </div>
                          <div className="m">{fmtActDateTime(a.at)}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Khối "Lưu ý (n)" GỠ 25/08/2026 theo yêu cầu chủ chốt. Engine VẪN sinh cảnh báo và
                BE vẫn lưu `warnings_json` — chỉ thôi bày ở cột phải. Muốn dựng lại thì đọc từ
                `out.result?.warnings ?? out.warnings`. */}
          </aside>
        </div>
      )}

      {/* ---------- POPUP MODAL: sửa 1 thành phần ---------- */}
      {editing ? (
        <ComponentModal
          comp={editing}
          idx={editingIdx}
          loaiSPs={loaiSPs}
          giays={giays}
          mays={mays}
          congDoans={congDoans}
          liveMeta={editMeta}
          liveGia={editGia}
          phieuSL={phieuSL}
          onClose={closeEditor}
          onRemove={() => {
            removeComp(editing.uid);
            setEditingUid(null);
            setPendingCalc(true);  // xóa xong → tính lại sau khi comps cập nhật (tránh closure cũ)
          }}
          patchComp={patchComp}
          patchFin={patchFin}
          onPickLoaiSP={onPickLoaiSPForComp}
          onPickGiay={onPickGiay}
          onPickMay={onPickMay}
          addFin={addFin}
          removeFin={removeFin}
        />
      ) : null}

      {/* ---------- Phiếu in (chỉ hiện khi @media print) ---------- */}
      {phieu ? (
        <div className="tg-print-only">
          <PhieuTinhGiaPrint data={phieu} />
        </div>
      ) : null}

      <DiscardChangesDialog
        open={hoiThoat}
        message="Phiếu này chưa được lưu. Thoát bây giờ là mất phần đã nhập."
        onDiscard={() => {
          setHoiThoat(false);
          onBack();
        }}
        onKeepEditing={() => setHoiThoat(false)}
      />
    </main>
  );
}

// ================= POPUP MODAL: sửa 1 thành phần (bám .rc-modal*) =================
function ComponentModal({
  comp: c,
  idx,
  loaiSPs,
  giays,
  mays,
  congDoans,
  liveMeta,
  liveGia,
  phieuSL,
  onClose,
  onRemove,
  patchComp,
  patchFin,
  onPickLoaiSP,
  onPickGiay,
  onPickMay,
  addFin,
  removeFin,
}: {
  comp: EditableComponent;
  idx: number;
  loaiSPs: Row[];
  giays: Row[];
  mays: Row[];
  congDoans: Row[];
  liveMeta: TinhGiaComponentMeta | null;
  liveGia: PhieuTinhGiaGroupOut[] | null;
  phieuSL: number;
  onClose: () => void;
  onRemove: () => void;
  patchComp: (uid: string, patch: Partial<EditableComponent>) => void;
  patchFin: (cuid: string, fuid: string, patch: Partial<EditableFinishing>) => void;
  onPickLoaiSP: (uid: string, pid: number | "") => void;
  onPickGiay: (uid: string, gid: number | null) => void;
  onPickMay: (uid: string, mid: number | null) => void;
  addFin: (cuid: string, cong_doan_id?: number | null, ten?: string, insertIndex?: number | null) => void;
  removeFin: (cuid: string, fuid: string) => void;
}) {
  // Lấy token tại chỗ thay vì luồn prop qua 16 tham số — ô gợi ý tên sản phẩm cần gọi API
  // danh mục Thành phẩm.
  const { token } = useAuth();

  // Danh mục ĐƠN VỊ TÍNH cho ô ĐVT (chủ 21/08/2026: "lấy theo Đơn vị tính trong danh mục cho họ
  // chọn"). Nạp MỘT lần cho cả khối sản phẩm — mỗi ô tự gọi là mỗi sản phẩm một request.
  // Lưu TÊN ("cái") chứ không lưu mã ("cai"): chuỗi này chảy thẳng sang Báo giá rồi ra
  // `order_lines.don_vi_tinh` và IN LÊN GIẤY. Đổi sang mã là mọi báo giá cũ in ra chữ khác.
  const [dvtOpts, setDvtOpts] = useState<string[]>([]);
  useEffect(() => {
    if (!token) return;
    donViDo
      .list(token, { active: true, size: 200 })
      .then((r) => {
        // Danh mục có cả m² · kg · mm · bản kẽm — đúng cho vật tư, vô nghĩa cho ĐVT sản phẩm.
        // KHÔNG lọc bỏ (danh mục là của chủ, lọc là tự quyết hộ), chỉ ĐẨY LÊN TRƯỚC những họ
        // dùng để BÁN: thành phẩm (cái/hộp/cuốn/bộ/con) · tờ (tờ rơi bán theo tờ) · thùng.
        // Không gom thành optgroup vì họ trong danh mục chỉ có mã thô (`khoi_luong`…), chưa
        // có nhãn hiển thị — bịa nhãn ở đây là đẻ nguồn sự thật thứ hai.
        const uu_tien = ["thanh_pham", "to", "thung"];
        const hang = (ho: string) => {
          const i = uu_tien.indexOf(ho);
          return i < 0 ? uu_tien.length : i;
        };
        const ds = r.items
          .map((d: Row) => ({ ten: String(d.ten ?? ""), ho: String(d.ho ?? "") }))
          .filter((d) => d.ten);
        ds.sort((a, b) => hang(a.ho) - hang(b.ho) || a.ten.localeCompare(b.ten, "vi"));
        setDvtOpts(ds.map((d) => d.ten));
      })
      .catch(() => setDvtOpts([]));
  }, [token]);

  // uid của sản phẩm đang mở trợ lý "tính số khuôn từ số trang" (mỗi lúc chỉ 1 popover).
  const [calcUid, setCalcUid] = useState<string | null>(null);
  // Bung phân rã bù hao: bước nào trong chuỗi ăn bao nhiêu tờ. Mặc định thu gọn.
  const [moPhanRa, setMoPhanRa] = useState(false);
  // "Tờ sau in" là tờ tốt ra khỏi bước IN — neo vào đúng bước đó để không phải đoán con số ở đâu ra.
  const buocIn = liveMeta?.bu_hao_chi_tiet?.find((b) => b.nhom === "print") ?? null;
  // --- Mạch TIỀN (cùng vòng /preview với mạch số tờ) ---
  // Từ điển biến để đổi công thức đã thế số thành chữ đọc được. `useBienCongThuc` cache theo
  // PHIÊN nên gọi ở đây không đẻ thêm request, khỏi phải luồn thêm một prop qua modal.
  const bienCt = useBienCongThuc();
  const tra = useMemo(() => traBien(bienCt), [bienCt]);
  const mapTien = useMemo(() => tienTheoBuoc(liveGia), [liveGia]);
  const dsCongDoan = useMemo(() => dongCongDoan(liveGia), [liveGia]);
  const dsKhuon = useMemo(() => dongKhuon(liveGia), [liveGia]);
  const tienKhuon = useMemo(() => dsKhuon.reduce((s2, d) => s2 + d.tien, 0), [dsKhuon]);
  const nvl = useMemo(() => nvlTheoLoai(liveGia), [liveGia]);
  const tienCongDoan = useMemo(
    () => [...mapTien.values()].reduce((s, d) => s + d.tien, 0), [mapTien],
  );
  const tienNvl = [...nvl.giay, ...nvl.vatTu].reduce((s, d) => s + d.tien, 0);
  // Tổng LẤY TỪ ENGINE (`gia_von_tp`), không tự cộng lại — cộng ở client là đẻ nguồn sự thật thứ
  // hai, rồi hai màn ra hai con số trên cùng một phiếu. Nhưng CÓ đối chiếu: lệch quá 1đ nghĩa là
  // có dòng engine tính mà panel chưa hiện ⇒ nói thẳng ra thay vì để người xem tự cộng rồi ngờ.
  const lechTien = liveMeta
    ? Math.abs(liveMeta.gia_von_tp - (tienNvl + tienCongDoan + tienKhuon))
    : 0;
  // Chưa có số (chưa nhập đủ) hoặc backend đời cũ chưa gửi nhóm tiền ⇒ không dựng khối rỗng.
  const coTien = !!liveMeta
    && (nvl.giay.length > 0 || nvl.vatTu.length > 0
        || dsCongDoan.length > 0 || dsKhuon.length > 0);
  // ĐƠN VỊ CỦA CHÍNH CHUỖI NÀY (12/08/2026) — trước đó khối này gọi cứng "tờ" và "con/tờ", trong
  // khi công đoạn khai `tờ → cái` / `tờ → tay sách`. Hệ quả thấy ngay trên màn: cùng số 99 mà dòng
  // trên ghi "99 con/tờ" còn dòng bù hao ghi "1 tờ = 99 cái" — mà `con` và `cái` là HAI đơn vị khác
  // nhau trong danh mục. Nay đọc từ chuỗi: đầu vào của bước đầu, đầu ra của bước cuối.
  //
  // `dvDauChuoi` cố ý lấy đầu vào của bước ĐẦU TIÊN chứ không tra mã `to`: xưởng khai mã riêng cho
  // chặng tờ in (vd `to_in`) thì dò mã là trượt, còn đọc từ chuỗi thì luôn ra đúng thứ bước đang đếm.
  const chuoiHao = liveMeta?.bu_hao_chi_tiet ?? [];
  const buocDauChuoi = chuoiHao.find((b) => b.dv_vao);
  const dvDauChuoi =
    dvNgan(buocIn?.dv_vao) || dvNgan(buocDauChuoi?.dv_vao) || "tờ";
  // `so_tp` là số THÀNH PHẨM trên một tờ, nên mẫu số phải là đơn vị thành phẩm — lấy ở bước ĐỔI
  // MỨC (dv_ra ≠ dv_vao). Lấy bừa `dv_ra` của bước cuối là sai khi chuỗi KHÔNG có bước đổi mức
  // (bìa sách: In → Cán màng, cả hai `tờ → tờ`) — ra "8 tờ/tờ", vô nghĩa. Không có bước đổi mức
  // thì dùng đơn vị tính của chính sản phẩm, đúng thứ dòng "Thành phẩm cần" đang hiện.
  const buocDoiMuc = [...chuoiHao].reverse().find((b) => b.dv_ra && b.dv_ra !== b.dv_vao);
  const dvCuoiChuoi = dvNgan(buocDoiMuc?.dv_ra) || c.don_vi_tinh || "cái";
  // Bước ĐẦU chuỗi đếm khác bước in ⇒ nó đứng ở chặng TỜ NGUYÊN (bước xả giấy). Không có bước xả
  // thì tờ nguyên chỉ là số suy ra, dùng nhãn mặc định.
  const dvToNguyen =
    buocDauChuoi && buocDauChuoi.dv_vao !== buocIn?.dv_vao
      ? dvNgan(buocDauChuoi.dv_vao) || "tờ nguyên"
      : "tờ nguyên";
  const chuaCh = chuaTheoChieu(c, c.may_id ? mays.find((x) => x.id === c.may_id) : null);
  // Ô này chọn MÁY IN — engine lấy khổ giấy máy nhận + vùng in + nhíp giấy để bình bài. Máy bế,
  // máy bồi sóng, máy cán màng KHÔNG có mấy thông số đó, đổ vào chỉ tổ chọn nhầm (chúng thuộc
  // chuỗi công đoạn, không thuộc ô này). Danh mục đặt tên loại khác đi mà lọc ra rỗng thì hiện
  // lại tất — thà thừa còn hơn khoá người dùng không chọn được gì.
  const mayIn = useMemo(() => {
    const loc = mays.filter((m) => /(^|\W)in(\W|$)/i.test(String(m.loai_may ?? "")));
    return loc.length > 0 ? loc : mays;
  }, [mays]);
  // ---- Lựa chọn cho các ô CÓ TÌM GẦN ĐÚNG ----
  // Bốn danh mục dưới đây dài hàng chục tới hàng trăm dòng; <select> gốc bắt người dùng cuộn hoặc
  // gõ đúng ký tự ĐẦU mới nhảy tới. Đổi sang `Select` (searchable) để gõ mảnh nào cũng ra: "may in
  // nho", "duplex 250", "hop giay" — bỏ dấu, tách từ, không cần đúng thứ tự (xem `utils/timGanDung`).
  // Gom bằng useMemo vì modal render lại theo từng phím gõ ở các ô số bên cạnh.
  const dvtSelOpts = useMemo<SelectOption<string>[]>(() => {
    const ds: SelectOption<string>[] = dvtOpts.map((d) => ({ value: d, label: d }));
    // Giá trị ĐANG DÙNG mà danh mục không có (gõ tay từ trước, hoặc đơn vị vừa bị ngừng) vẫn phải
    // chọn được — nếu không, mở phiếu cũ ra là ĐVT tự nhảy sang đơn vị khác mà không ai báo.
    if (c.don_vi_tinh && !dvtOpts.includes(c.don_vi_tinh))
      ds.unshift({ value: c.don_vi_tinh, label: `${c.don_vi_tinh} (ngoài danh mục)` });
    return ds;
  }, [dvtOpts, c.don_vi_tinh]);
  const loaiSPOpts = useMemo<SelectOption<string>[]>(
    () => [
      { value: "", label: "— Chọn loại sản phẩm —" },
      ...optsConDung(loaiSPs, c.loai_san_pham_id),
    ],
    [loaiSPs, c.loai_san_pham_id],
  );
  const giayOpts = useMemo<SelectOption<string>[]>(
    () => [{ value: "", label: "— Chọn giấy —" }, ...optsConDung(giays, c.giay_id)],
    [giays, c.giay_id],
  );
  const mayOpts = useMemo<SelectOption<string>[]>(
    () => [{ value: "", label: "— Không chọn —" }, ...optsConDung(mayIn, c.may_id)],
    [mayIn, c.may_id],
  );
  // Ô công đoạn là ô HÀNH ĐỘNG (chọn xong thì đẻ chip, ô tự về rỗng) nên không có mục "— Chọn —".
  // LỌC `active`: bấm "Xóa" một công đoạn còn nơi dùng thì hệ chỉ TẮT cờ `active` (xoá hẳn sẽ
  // làm hỏng phiếu/lệnh cũ). Danh sách nạp về cố ý KHÔNG lọc — tên cũ vẫn phải tra được để phiếu
  // cũ gọi đúng tên bước — nhưng ô CHỌN thì phải sạch, không thì công đoạn vừa xoá vẫn mời chọn
  // lại và nằm cạnh bản thay thế cùng tên (lỗi 9, 25/08/2026).
  const cdOpts = useMemo<SelectOption<string>[]>(
    () => [
      ...congDoans
        .filter((cd) => cd.active !== false)
        .map((cd) => ({ value: String(cd.id), label: cdName(cd) })),
      { value: "__blank", label: "+ Tự nhập…" },
    ],
    [congDoans],
  );
  // Một đường thêm chip cho CẢ hai chỗ: mũi tên chèn giữa chuỗi và nút "+ Thêm công đoạn" ở cuối.
  const themCongDoan = (v: string, insertIdx: number | null = null) => {
    if (!v) return;
    if (v === "__blank") {
      addFin(c.uid, null, "", insertIdx);
      return;
    }
    const cd = congDoans.find((x) => String(x.id) === v);
    addFin(c.uid, cd ? cd.id : null, cd ? cdName(cd) : "", insertIdx);
  };

  // Bình bài chỉ tính được khi có ĐỦ khổ thành phẩm ③ + khổ tờ in ② (khổ in tự lấy từ giấy/máy).
  const canBinhBai =
    c.dai_thanh_pham > 0 && c.rong_thanh_pham > 0 && c.kho_in_dai > 0 && c.kho_in_rong > 0;


  // Esc để đóng.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="rc-modal__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="rc-modal" onClick={(e) => e.stopPropagation()}>
        <header className="rc-modal__head">
          <div>
            <div className="rc-modal__kicker">Sản phẩm {idx + 1}</div>
            <h2 className="rc-modal__title">{c.ten || loaiTpLabel(c.loai_thanh_phan)}</h2>
          </div>
          <button type="button" className="rc-modal__x" onClick={onClose} aria-label="Đóng">
            <CloseIcon />
          </button>
        </header>

        <div className="rc-modal__body-grid">
          {/* Cột trái: Giao diện nhập liệu */}
          <div className="rc-modal__left-col">
            {/* ---- SẢN PHẨM & KHỔ ---- */}
            <section className="rc-sec">
              <div className="rc-sec__title">
                <span className="tg-step-badge">1</span> Sản phẩm &amp; khổ chi tiết
              </div>
              <div className="tg-grid">
                <label className="tg-field tg-span-6">
                  <span className="tg-microlabel">Tên sản phẩm</span>
                  {/* GỢI Ý từ danh mục Thành phẩm, KHÔNG ép chọn — gõ tên mới vẫn được.
                      Chọn lại đúng tên cũ thì lúc chốt đơn hệ dùng lại đúng dòng danh mục cũ,
                      không đẻ dòng mới (docs/prd-thanh-pham.md §11). */}
                  <ThanhPhamGoiY
                    token={token ?? ""}
                    value={c.ten}
                    placeholder="VD Thân hộp / Ruột / Bìa"
                    onChange={(ten) => patchComp(c.uid, { ten })}
                  />
                </label>
                <div className="tg-span-3">
                  <NumField
                    label="Số lượng"
                    value={c.so_luong > 0 ? c.so_luong : phieuSL}
                    step="1"
                    onChange={(n) => patchComp(c.uid, { so_luong: Math.max(0, n) })}
                  />
                </div>
                <label className="tg-field tg-span-3">
                  <span className="tg-microlabel">ĐVT</span>
                  <Select
                    options={dvtSelOpts}
                    value={c.don_vi_tinh}
                    onChange={(v) => patchComp(c.uid, { don_vi_tinh: v })}
                    ariaLabel="Đơn vị tính"
                    searchable
                    portal
                    className="tg-input"
                    listClassName="tg-pop"
                  />
                </label>
                {/* Gộp dòng khi báo giá KHÔNG có ô ở đây: nó là quan hệ giữa các dòng, thao tác
                    nằm ở bảng "Sản phẩm trong phiếu" (tick nhiều dòng → gõ tên nhóm 1 lần). */}
                <label className="tg-field tg-span-12">
                  <span className="tg-microlabel">
                    Loại sản phẩm <span className="tg-microlabel__opt">tự bung công đoạn mặc định</span>
                  </span>
                  <Select
                    options={loaiSPOpts}
                    value={c.loai_san_pham_id == null ? "" : String(c.loai_san_pham_id)}
                    onChange={(v) => onPickLoaiSP(c.uid, v === "" ? "" : Number(v))}
                    ariaLabel="Loại sản phẩm"
                    searchable
                    portal
                    className="tg-input"
                    listClassName="tg-pop"
                  />
                </label>
                <div className="tg-span-6">
                      <NumField
                        label="Dài chi tiết phẳng"
                        value={c.dai_thanh_pham}
                        onChange={(n) => patchComp(c.uid, { dai_thanh_pham: n })}
                        thapPhan
                        suffix="mm"
                      />
                    </div>
                    <div className="tg-span-6">
                      <NumField
                        label="Rộng chi tiết phẳng"
                        value={c.rong_thanh_pham}
                        onChange={(n) => patchComp(c.uid, { rong_thanh_pham: n })}
                        thapPhan
                        suffix="mm"
                      />
                    </div>
                    {/* Ô này KHÔNG dùng NumField: cần nút "tính từ số trang" nằm cùng hàng nhãn,
                        và popover trợ lý neo ngay dưới ô (nút phải ở NGOÀI <label>, không thì bấm
                        nút lại kích hoạt label → nhảy focus về input). */}
                    <div className="tg-span-12 tg-field tg-calcwrap">
                      <div className="tg-calcwrap__head">
                        {/* Nhãn phải gọn 1 dòng: ô rộng 186px, thêm chữ là ô nhập tụt xuống,
                            lệch hàng với "Tay gấp" bên cạnh → câu hỏi gợi ý đẩy xuống tg-note. */}
                        <span className="tg-microlabel" id={`khuon-lbl-${c.uid}`}>
                          Số bài in
                        </span>
                        <button
                          type="button"
                          className="tg-calc__open"
                          aria-expanded={calcUid === c.uid}
                          aria-controls={`khuon-calc-${c.uid}`}
                          onClick={() => setCalcUid(calcUid === c.uid ? null : c.uid)}
                        >
                          <KhuonCalcIcon /> tính từ số trang
                        </button>
                      </div>
                      {/* DẪN XUẤT `so_trang / trang_moi_tay` — sửa ở popover, không gõ thẳng vào
                          đây: gõ tay thì server cũng ghi đè lúc tính, thành ô ma. */}
                      <input
                        className="tg-input tg-input--num"
                        type="number"
                        readOnly
                        aria-labelledby={`khuon-lbl-${c.uid}`}
                        value={soBaiIn(c)}
                      />
                      {calcUid === c.uid && (
                        <KhuonCalc
                          domId={`khuon-calc-${c.uid}`}
                          soTrangDaLuu={c.so_trang}
                          moiTayDaLuu={c.trang_moi_tay}
                          onApply={(soTrang, moiTay) => {
                            // LƯU cả hai ô — engine tự chia ra số bài in, không ghi kết quả vào đây.
                            patchComp(c.uid, {
                              so_trang: Math.max(1, soTrang),
                              trang_moi_tay: Math.max(1, moiTay),
                            });
                            setCalcUid(null);
                          }}
                          onClose={() => setCalcUid(null)}
                        />
                      )}
                    </div>
                    {/* Ô "Tay gấp" gỡ 2026-07-29 (đụng nghĩa với "trang mỗi tay" của trợ lý cạnh
                        đây). Cột `tay_gap` — cùng `kho_thanh_pham` / `kho_mo_rong` — nay DROP hẳn
                        ở mig 0144: từ khi gỡ ô nhập thì phiếu mới luôn rỗng, mà bản lệnh vẫn vẽ ra
                        ba dòng "—" làm người đọc tưởng phiếu có khai. */}
                    {/* Số bài in nhân cả tờ giấy LẪN kẽm (gõ nhầm 50 thay vì 7 là kẽm phồng 7 lần)
                        → dòng này LUÔN hiện để nói rõ phải điền GÌ, không chỉ nói hậu quả. */}
                    {/* Chú thích NẰM CẠNH ô (span-8, cùng hàng) chứ không phải dòng dưới cả hàng
                        — dòng dưới thì không biết đang nói về ô nào. */}
                    <p className="tg-note tg-span-12">
                      <b>Mấy bài in khác nhau?</b> In giống nhau cả loạt → 1 (tờ rơi, hộp, name
                      card). Sách 200 trang tay 32 → 7, vì mỗi tay một nội dung khác.
                      {" "}Bấm <b>tính từ số trang</b> để khai — số bài in tự ra.
                      {soBaiIn(c) > 1 ? (
                        <> Đang {c.so_trang} trang ÷ {c.trang_moi_tay} = {soBaiIn(c)} bài
                        → kẽm ×{soBaiIn(c)}.</>
                      ) : null}
                    </p>
                {/* Bleed + khe cắt: cộng vào kích thước con khi bình bài. Hỏi khách/kỹ thuật;
                    không biết thì để 0 — engine bình sát như trước. */}
                <div className="tg-span-6">
                  <NumField
                    label="Bleed (tràn lề)"
                    value={c.bleed_mm}
                    onChange={(n) => patchComp(c.uid, { bleed_mm: n })}
                    opt="mỗi cạnh con · 0 = không tràn lề"
                    thapPhan
                    suffix="mm"
                  />
                </div>
                <div className="tg-span-6">
                  <NumField
                    label="Khe cắt giữa con"
                    value={c.khe_cat_mm}
                    onChange={(n) => patchComp(c.uid, { khe_cat_mm: n })}
                    opt="0 = bình sát, cắt chung nhát"
                    thapPhan
                    suffix="mm"
                  />
                </div>
              </div>
            </section>

            {/* ---- GIẤY NGUYÊN ---- */}
            <section className="rc-sec">
              <div className="rc-sec__title">
                <span className="tg-step-badge">2</span> Giấy nguyên
              </div>
              <div className="tg-grid">
                <label className="tg-field tg-span-6">
                  <span className="tg-microlabel">Loại giấy</span>
                  <Select
                    options={giayOpts}
                    value={c.giay_id == null ? "" : String(c.giay_id)}
                    onChange={(v) => onPickGiay(c.uid, v === "" ? null : Number(v))}
                    ariaLabel="Loại giấy"
                    searchable
                    portal
                    className="tg-input"
                    listClassName="tg-pop"
                  />
                </label>
                {/* GỠ 2026-08-09 (Đợt 4 · K): ô chọn "Nguồn giấy — Công ty / Khách cấp".
                    Công ty luôn cấp giấy, và engine đã thôi đọc cờ đó. Để lại ô mà engine không
                    nghe là tệ hơn không có ô: người tính giá tick "Khách cấp", nhìn thấy nó lưu
                    được, rồi phiếu vẫn tính đủ tiền giấy. */}
                <div className="tg-span-3">
                  <NumField
                    label="Dài nguyên"
                    value={c.kho_nguyen_dai}
                    onChange={(n) => patchComp(c.uid, { kho_nguyen_dai: n })}
                    thapPhan
                    suffix="mm"
                  />
                </div>
                <div className="tg-span-3">
                  <NumField
                    label="Rộng nguyên"
                    value={c.kho_nguyen_rong}
                    onChange={(n) => patchComp(c.uid, { kho_nguyen_rong: n })}
                    thapPhan
                    suffix="mm"
                  />
                </div>
                <div className="tg-field tg-span-6">
                  <div className="tg-readout" style={{ minHeight: "36px", display: "flex", alignItems: "center" }}>
                    {(() => {
                      const g = c.giay_id ? giays.find((x) => x.id === c.giay_id) : null;
                      if (!g) return "— chọn giấy để lấy giá —";
                      // Tên đơn vị đọc từ DANH MỤC, không phải chuỗi ba nhánh khai cứng ở đây —
                      // giấy bán theo đơn vị nào là việc của danh mục, thêm đơn vị mới thì dòng
                      // này tự hiện đúng thay vì rơi hết về "tờ".
                      return `${fmt(numOf(g.don_gia))} đ / ${dvNgan(String(g.don_vi_gia ?? "")) || "—"}`;
                    })()}
                  </div>
                </div>
              </div>
            </section>

            {/* ---- KỸ THUẬT IN & MÀU IN ---- */}
            <section className="rc-sec">
              <div className="rc-sec__title">
                <span className="tg-step-badge">3</span> Kỹ thuật in &amp; Màu in
              </div>
              <div className="tg-grid">
                {/* 7 + 5 chứ không phải 8 + 4: bốn nút quy cách nhồi trong span-4 thì "Tự trở" /
                    "Trở nhíp" gãy làm hai dòng. Tên máy là <select> nên hụt chỗ chỉ bị cắt đuôi. */}
                <label className="tg-field tg-span-7">
                  <span className="tg-microlabel">
                    Máy in <span className="tg-microlabel__opt">→ khổ tờ in</span>
                  </span>
                  <Select
                    options={mayOpts}
                    value={c.may_id == null ? "" : String(c.may_id)}
                    onChange={(v) => onPickMay(c.uid, v === "" ? null : Number(v))}
                    ariaLabel="Máy in"
                    searchable
                    portal
                    className="tg-input"
                    listClassName="tg-pop"
                  />
                </label>
                <div className="tg-field tg-span-5">
                  <span className="tg-microlabel">
                    <span>Quy cách in</span>
                    {/* Lý do "1 mặt" biến mất phải nói ra ngay đây. Trước đó tôi để nút gạch
                        ngang mờ đi: gạch ngang đọc thành "đã bỏ/lỗi thời", không phải "không
                        dùng được cho hàng này", mà lại ăn 1/4 bề ngang làm hai nút kia gãy chữ. */}
                    {laSach(c) && (
                      <span className="tg-tag tg-tag--auto" title="Tay gấp lại thì cả hai mặt tờ đều là trang ruột">
                        sách · in 2 mặt
                      </span>
                    )}
                  </span>
                  <Seg
                    ariaLabel="Quy cách in"
                    value={c.quy_cach_in}
                    onChange={(v) => patchComp(c.uid, { quy_cach_in: v })}
                    options={[
                      ...(laSach(c) ? [] : [{ val: "mot_mat", label: "1 mặt" }]),
                      { val: "hai_mat", label: "AB" },
                      { val: "tu_tro", label: "Tự trở" },
                      { val: "tro_nhip", label: "Trở nhíp" },
                    ]}
                  />
                  {/* Phiếu CŨ đã lỡ lưu "1 mặt" rồi mới khai tay — không nút nào sáng, phải nói
                      rõ vì sao, không thì trông như hỏng. */}
                  {laSach(c) && c.quy_cach_in === "mot_mat" && (
                    <span className="tg-hint" style={{ marginTop: "2px", color: "var(--rust)" }}>
                      Phiếu đang để 1 mặt — chọn lại AB / Tự trở / Trở nhíp.
                    </span>
                  )}
                </div>
                <div className="tg-span-3">
                  <NumField
                    label="Khổ tờ in dài"
                    value={c.kho_in_dai}
                    onChange={(n) => patchComp(c.uid, { kho_in_dai: n })}
                    thapPhan
                    suffix="mm"
                  />
                </div>
                <div className="tg-span-3">
                  <NumField
                    label="Khổ tờ in rộng"
                    value={c.kho_in_rong}
                    onChange={(n) => patchComp(c.uid, { kho_in_rong: n })}
                    thapPhan
                    suffix="mm"
                  />
                </div>
                {/* SÁCH → ô "Số con" biến mất. Nó vẫn được engine tính ngầm (vẽ sơ đồ + kiểm khổ
                    có vừa tờ) nhưng KHÔNG vào tiền giấy, nên hỏi người dùng là hỏi thừa và gây
                    hiểu nhầm "tờ này cắt ra 16 cuốn". Thay bằng con số thật sự có nghĩa. */}
                {laSach(c) ? (
                  <div className="tg-field tg-span-6">
                    <span className="tg-microlabel">
                      <span>Trang mỗi mặt</span>
                      <span
                        className="tg-tag tg-tag--auto"
                        title="Sách gấp nguyên tờ, không cắt rời — không có số con"
                      >
                        <AutoIcon /> theo tay
                      </span>
                    </span>
                    {/* KHÔNG dùng <input readOnly>: nó giống hệt ô "Số màu mặt A" ngay dưới, mời
                        người ta gõ rồi không nhận. Đây là số DẪN XUẤT nên mượn `.tg-readout` —
                        viền nét đứt, đã là ngôn ngữ "máy tự tính" sẵn có của màn này. Phép chia
                        nằm luôn trong ô, khỏi hai dòng chữ nghiêng bên dưới. */}
                    <div className="tg-readout tg-readout--derive">
                      <b className="tg-readout__val">{trangMoiMat(c)}</b>
                      <span className="tg-readout__unit">trang</span>
                      <em className="tg-readout__how">tay {c.trang_moi_tay} ÷ 2 mặt</em>
                    </div>
                  </div>
                ) : (
                <div className="tg-field tg-span-6">
                  <span className="tg-microlabel">
                    <span>Số con</span>
                    {c.con_auto ? (
                      canBinhBai ? (
                        <span className="tg-tag tg-tag--auto">
                          <AutoIcon /> tự bình bài
                        </span>
                      ) : (
                        <span className="tg-tag tg-tag--todo" style={{ fontSize: "9px" }}>nhập khổ để tự tính</span>
                      )
                    ) : (
                      <button
                        type="button"
                        className="tg-revert"
                        onClick={() => patchComp(c.uid, { con_auto: true })}
                        title="Về số tự bình bài"
                      >
                        <RevertIcon /> về auto
                      </button>
                    )}
                  </span>
                  <input
                    className={`tg-input tg-input--num${c.con_auto ? "" : " tg-input--edited"}`}
                    type="number"
                    min={1}
                    value={c.so_con}
                    onChange={(e) =>
                      patchComp(c.uid, {
                        so_con: Math.max(1, Number(e.target.value)),
                        con_auto: false,
                      })
                    }
                  />
                  {!c.con_auto && (
                    <span className="tg-hint" style={{ marginTop: "2px" }}>
                      Đang ĐÈ số con — engine không bình bài lại. Xoá ô để tính tự động.
                    </span>
                  )}
                </div>
                )}
                {/* Ba ô số cũ (mặt A · mặt B · màu pha) đổi thành TẬP MỰC — số kẽm của tự trở là
                    `|A ∪ B|`, không suy được từ con số. Xem `soKemMoiTay`. */}
                <div className="tg-span-12">
                  <MucInBlock
                    comp={c}
                    soTay={soBaiIn(c)}
                    onChange={(p) => patchComp(c.uid, p)}
                  />
                </div>
              </div>
            </section>

            {/* ---- CHUỖI CÔNG ĐOẠN THỰC HIỆN ---- */}
            <section className="rc-sec">
              <div className="rc-sec__title">
                <span className="tg-step-badge">4</span> Chuỗi công đoạn thực hiện
              </div>
              <div className="tg-timeline">
                {c.thanh_phams.length === 0 && (
                  <p className="tg-chipgrid__empty" style={{ margin: "6px 0" }}>
                    Chọn loại sản phẩm để tự bung chuỗi, hoặc thêm công đoạn.
                  </p>
                )}
                {c.thanh_phams.map((f, fIdx) => {
                  const canh = tinhTrangBuoc(f, congDoans);
                  return (
                  <div key={f.uid} className="tg-timeline-item">
                    <span
                      className={`tg-chip${canh ? " tg-chip--canh" : ""}`}
                      title={
                        canh === "mat"
                          ? "Công đoạn này đã bị xóa khỏi danh mục — chọn công đoạn khác thay vào."
                          : canh === "ngung"
                            ? "Công đoạn này đã ngừng dùng — vẫn tính được, nhưng lần sau không chọn lại được."
                            : undefined
                      }
                    >
                      <span className="tg-chip__name">
                        {tenBuoc(f, congDoans) || "(công đoạn)"}
                      </span>
                      {canh ? (
                        <span className="tg-chip__canh">
                          {canh === "mat" ? "đã xóa" : "ngừng dùng"}
                        </span>
                      ) : null}
                      <button
                        type="button"
                        className="tg-chip__x"
                        aria-label="Xóa công đoạn"
                        title="Xóa khỏi chuỗi"
                        onClick={() => removeFin(c.uid, f.uid)}
                      >
                        <CloseIcon />
                      </button>
                    </span>
                    {/* `title` chuyển lên thẻ bọc: `Select` không nhận `title`, mà mũi tên 22px
                        không có chữ nên mất tooltip là mất luôn manh mối "bấm được". */}
                    {fIdx < c.thanh_phams.length - 1 && (
                      <div className="tg-timeline-arrow-wrap" title="Chèn công đoạn vào giữa">
                        <Select
                          options={cdOpts}
                          value=""
                          onChange={(v) => themCongDoan(v, fIdx + 1)}
                          placeholder="➔"
                          ariaLabel="Chèn công đoạn vào giữa"
                          searchable
                          portal
                          className="tg-timeline-select-arrow"
                          listClassName="tg-pop"
                        />
                      </div>
                    )}
                  </div>
                  );
                })}
                <div
                  className="tg-chip-add-wrap"
                  style={{ marginLeft: c.thanh_phams.length > 0 ? "8px" : "0" }}
                >
                  <Select
                    options={cdOpts}
                    value=""
                    onChange={(v) => themCongDoan(v)}
                    placeholder="+ Thêm công đoạn…"
                    ariaLabel="Thêm công đoạn"
                    searchable
                    portal
                    className="tg-chip-add"
                    listClassName="tg-pop"
                  />
                </div>
              </div>

              {/* PHÍ KHUÔN — chỉ mọc khi chuỗi có bước cần dao lưu kho. Chuỗi toàn bước phẳng thì
                  khối này không tồn tại, màn hình không đổi một pixel.

                  Không gắn ô vào chip được: chip chỉ có tên + dấu ×, nhét input vào là vỡ hàng và
                  mất luôn nghĩa "kéo thả thứ tự". Nên tách thành khối con ngay dưới dãy chip. */}
              {(() => {
                const daos = c.thanh_phams
                  .map((f) => ({ f, dao: daoCuaBuoc(f, congDoans) }))
                  .filter((x) => x.dao !== null);
                if (daos.length === 0) return null;
                const tong = daos.reduce((s, x) => s + (Number(x.f.phi_khuon) || 0), 0);
                return (
                  <div className="tg-khuon">
                    <div className="tg-khuon__head">
                      <span className="tg-khuon__title">Phí khuôn</span>
                      <span className="tg-khuon__note">một lần · không chia theo số lượng</span>
                    </div>
                    {daos.map(({ f, dao }) => (
                      <div className="tg-khuon__row" key={f.uid}>
                        <span className="tg-khuon__ten">
                          {tenBuoc(f, congDoans) || "(công đoạn)"}
                          <em>{dao}</em>
                        </span>
                        <div className="tg-khuon__input">
                          <input
                            className="tg-khuon__num"
                            type="number"
                            min={0}
                            step={1000}
                            /* Ô số trần không có <label> nối vào — trình đọc màn hình chỉ đọc
                               "spin button". Ghép tên bước + loại dao thành nhãn. */
                            aria-label={`Phí ${dao} của bước ${tenBuoc(f, congDoans) || "công đoạn"}`}
                            value={f.phi_khuon || ""}
                            placeholder="0"
                            onChange={(e) =>
                              patchFin(c.uid, f.uid, {
                                phi_khuon: Math.max(0, Number(e.target.value) || 0),
                              })
                            }
                          />
                          <small>đ</small>
                        </div>
                      </div>
                    ))}
                    <div className="tg-khuon__foot">
                      {/* Σ cộng SỐNG theo lúc gõ: hai bước có thể dùng chung một con dao, gõ cả hai
                          ô là tính tiền hai lần cho một con — tổng phồng lên thì thấy ngay. */}
                      <span>Σ phí khuôn</span>
                      <b>{fmt(Math.round(tong))} <small>đ</small></b>
                    </div>
                    <p className="tg-khuon__hint">
                      Để trống = dùng lại khuôn cũ, không tính tiền.
                    </p>
                  </div>
                );
              })()}

            </section>

          </div>

          {/* Cột phải: Trực quan hóa và Số liệu ước lượng */}
          <div className="rc-modal__right-col">
            {/* SƠ ĐỒ BÌNH BÀI CARD */}
            <div className="tg-imp-card">
              <div className="tg-imp-card__title">
                {laSach(c) ? "Sơ đồ tay sách live" : "Sơ đồ bình bài live"}
              </div>
              <ImpositionDiagram
                khoInDai={c.kho_in_dai}
                khoInRong={c.kho_in_rong}
                daiTP={c.dai_thanh_pham}
                rongTP={c.rong_thanh_pham}
                chuaMm={0}
                chuaDai={chuaCh.dai}
                chuaRong={chuaCh.rong}
                bleedMm={c.bleed_mm}
                kheCatMm={c.khe_cat_mm}
                soCon={c.so_con}
                trangMoiTay={c.trang_moi_tay}
                dvCon={dvCuoiChuoi}
                dvTo={dvDauChuoi}
              />
            </div>

            {/* SỐ TỜ (tính LIVE qua /preview) + ô Bù / Hao nhập tay */}
            <div className="tg-sheetbox">
              <div className="tg-sheetbox__title">
                Số tờ <span className="tg-sheetbox__hint">tự tính · engine thật</span>
              </div>
              <div className="tg-sheetrow">
                <span>Thành phẩm cần</span>
                {liveMeta
                  ? <SoDv so={fmt(liveMeta.so_luong)} dv={c.don_vi_tinh || "cái"} />
                  : <b className="tg-val">…</b>}
              </div>
              <div className="tg-sheetrow">
                <span className="tg-sheetrow__stack">
                  = Tờ in cần (chưa hao)
                  {/* SÁCH đi đường NHÂN, không phải đường chia: engine gom `so_tay` tờ mới ra 1
                      cuốn (`cau_to_sang_cai` → 1/so_tay), `con` không dính vào. Dòng cũ chia cho
                      `con` chỉ tình cờ ra đúng khi con == trang mỗi tay; đổi tay 16 → 32 là lệch. */}
                  {liveMeta &&
                    ((liveMeta.trang_moi_tay ?? 1) > 1 ? (
                      <em className="tg-sheetrow__derive">
                        {fmt(liveMeta.so_luong)} {c.don_vi_tinh || "cuốn"} ×{" "}
                        {fmt(liveMeta.so_to_per_sp ?? 1)} tay
                      </em>
                    ) : liveMeta.con > 0 ? (
                      <em className="tg-sheetrow__derive">
                        ⌈{fmt(liveMeta.so_luong)}
                        {(liveMeta.so_trang ?? 1) > 1 ? ` × ${fmt(liveMeta.so_trang ?? 1)} trang` : ""}
                        {" ÷ "}
                        {fmt(liveMeta.con)} {dvCuoiChuoi}/{dvDauChuoi}⌉
                      </em>
                    ) : null)}
                </span>
                {liveMeta
                  ? <SoDv so={fmt(liveMeta.to_net)} dv={dvDauChuoi} />
                  : <b className="tg-val">…</b>}
              </div>
              <div className="tg-sheetrow">
                <span>+ Bù hao công đoạn</span>
                {(liveMeta?.bu_hao_chi_tiet?.length ?? 0) > 0 ? (
                  <button
                    type="button"
                    className="tg-sheetdrill"
                    aria-expanded={moPhanRa}
                    title={moPhanRa ? "Thu gọn" : "Xem bước nào ăn bao nhiêu tờ"}
                    onClick={() => setMoPhanRa((v) => !v)}
                  >
                    <SoDv so={fmt(liveMeta?.bu_hao_auto ?? 0)} dv={dvDauChuoi} />
                    <ChevronIcon open={moPhanRa} />
                  </button>
                ) : (
                  liveMeta
                    ? <SoDv so={fmt(liveMeta.bu_hao_auto ?? 0)} dv={dvDauChuoi} />
                    : <b className="tg-val">…</b>
                )}
              </div>
              {moPhanRa && (liveMeta?.bu_hao_chi_tiet?.length ?? 0) > 0 && (
                <ul className="tg-sheetbreak">
                  {liveMeta!.bu_hao_chi_tiet!.map((b, i) => {
                    const coHao = b.hao > 0;
                    const dvV = dvNgan(b.dv_vao);
                    const dvR = dvNgan(b.dv_ra);
                    // Câu quy đổi dùng CHUNG với màn lệnh + bài ghép (`pages/lsxBuoc`) — luật lật
                    // hệ số khi < 1 bắt nguồn từ đây, giữ ba bản chép là ba chỗ để lệch.
                    const heSoText = heSoChu(b.he_so, b.dv_vao, b.dv_ra);
                    const doiTiLe = !!heSoText;
                    const haoText = coHao
                      ? `cần ${fmt(b.ra_quy ?? 0)} ${dvV} tốt + ${fmt(b.hao)} hao = ${fmt(b.vao)} ${dvV}`
                      : null;
                    // Tiền của ĐÚNG bước này. `undefined` = backend chưa gửi khóa ⇒ không hiện gì.
                    const tienBuoc = b.buoc_idx == null ? undefined : mapTien.get(b.buoc_idx);

                    return (
                      <li key={i} className="tg-step-card">
                        <div className="tg-step-card__head">
                          <div className="tg-step-card__title-group">
                            <span className="tg-step-card__ten" title={b.ten}>{b.ten}</span>
                          </div>
                          {coHao && (
                            <span className="tg-hao-pill" title="Bù hao công đoạn này">
                              +{fmt(b.hao)} {dvV}
                            </span>
                          )}
                        </div>
                        <div className="tg-step-card__flow">
                          <span className="tg-step-card__qty">
                            {fmt(b.vao)} <small>{dvV}</small>
                          </span>
                          <span className="tg-step-card__flow-arrow">→</span>
                          <span className="tg-step-card__qty">
                            {fmt(b.ra)} <small>{dvR}</small>
                          </span>
                          {tienBuoc && (
                            <span className="tg-step-card__tien" title={tienBuoc.congThuc || undefined}>
                              {fmt(Math.round(tienBuoc.tien))} <small>đ</small>
                            </span>
                          )}
                        </div>
                        {(doiTiLe || coHao) && (
                          <div className="tg-step-card__details">
                            {heSoText && (
                              <span className="tg-ratio-tag">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/>
                                </svg>
                                <span>{heSoText}</span>
                              </span>
                            )}
                            {haoText && (
                              <span className="tg-math-tag">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M8 7h6"/><path d="M8 11h8"/>
                                </svg>
                                <span>{haoText}</span>
                              </span>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
              {/* GỠ 15/08/2026: ô "+ Bù thêm" — ô nhập tay CUỐI CÙNG của khối này. Nó cộng một
                  con số TỜ vào mọi bước bất kể bước đó đếm bằng gì, nên bước đếm cuốn ra hao ÂM và
                  đơn 500 hoá 600. Nay cả khối số tờ do máy tính hết. Muốn làm dư thì khai bù hao
                  của chính công đoạn ở danh mục — chỗ đó biết đơn vị nên quy ra giấy đúng cầu. */}
              <div className="tg-sheetrow tg-sheetrow--total">
                <span>= Tờ vào máy</span>
                {liveMeta
                  ? <SoDv so={fmt(liveMeta.to_dau_vao)} dv={dvDauChuoi} />
                  : <b className="tg-val">…</b>}
              </div>
              <div className="tg-sheetrow tg-sheetrow--total">
                <span className="tg-sheetrow__stack">
                  = Tờ sau in
                  {liveMeta && (
                    <em className="tg-sheetrow__derive">
                      {buocIn
                        ? `${dvDauChuoi} tốt ra khỏi "${buocIn.ten}"`
                        : `chuỗi chưa có bước in → giữ ${dvDauChuoi} vào máy`}
                    </em>
                  )}
                </span>
                {liveMeta
                  ? <SoDv so={fmt(liveMeta.to_sau_in)} dv={dvDauChuoi} />
                  : <b className="tg-val">…</b>}
              </div>
              <div className="tg-sheetrow tg-sheetrow--total">
                <span className="tg-sheetrow__stack">
                  = Tờ nguyên (giấy to)
                  {/* Chú thích phải bám ĐÚNG nguồn của con số: chuỗi có bước ăn tờ nguyên (bước in)
                      thì engine đọc thẳng số vào của bước đó — nói "to_dau_vao ÷ số mảnh xả" là mô
                      tả một phép tính KHÔNG được dùng, và ra kết quả khác hẳn số đang hiện. */}
                  {(() => {
                    const buocNguyen = liveMeta?.bu_hao_chi_tiet?.find(
                      (b) => b.dv_vao === "to_nguyen",
                    );
                    if (buocNguyen) {
                      return (
                        <em className="tg-sheetrow__derive">
                          {fmt(buocNguyen.ra_quy ?? 0)} tốt + {fmt(buocNguyen.hao)} hao ở
                          {" “"}{buocNguyen.ten}{"”"}
                        </em>
                      );
                    }
                    return liveMeta && liveMeta.so_manh_xa > 0 ? (
                      <em className="tg-sheetrow__derive">
                        ⌈{fmt(liveMeta.to_dau_vao)} ÷ {fmt(liveMeta.so_manh_xa)}{" "}
                        {dvDauChuoi}/{dvToNguyen}⌉
                      </em>
                    ) : null;
                  })()}
                </span>
                {liveMeta
                  ? <SoDv so={fmt(liveMeta.to_nguyen)} dv={dvToNguyen} />
                  : <b className="tg-val">…</b>}
              </div>
              {/* Ẩn "số con" ở ô nhập mà để nó lòi ra ở chân khối thì coi như chưa ẩn. */}
              <div className="tg-sheetbox__foot">
                {liveMeta
                  ? `${
                      (liveMeta.trang_moi_tay ?? 1) > 1
                        ? `${fmt(Math.ceil((liveMeta.trang_moi_tay ?? 2) / 2))} trang/mặt`
                        : `${fmt(liveMeta.con)} ${dvCuoiChuoi}/${dvDauChuoi}`
                    } · ${fmt(liveMeta.so_kem)} kẽm`
                  : "Nhập đủ khổ + số lượng để tính"}
              </div>
            </div>

            {/* GIÁ THÀNH: mạch tiền nối tiếp mạch số tờ ở trên. Cùng một vòng /preview, không
                gọi thêm request nào. Chi tiết TỪNG bước nằm trong phân rã "Bù hao công đoạn" —
                ở đây chỉ chốt tổng, để khối không dài gấp đôi vì lặp lại tên 6 công đoạn. */}
            {liveMeta && (
              <div className="tg-sheetbox tg-sheetbox--tien">
                <div className="tg-sheetbox__title">
                  Giá vốn <span className="tg-sheetbox__hint">sản phẩm này</span>
                </div>
                {/* KHÔNG gộp hai ca này làm một: "engine tính ra 0đ" và "engine có tính mà panel
                    không đọc được dòng" là hai chuyện khác hẳn, mà chỉ có tổng > 0 mới phân biệt
                    được. Nói nhầm ca thì người dùng đi sửa công thức trong khi công thức không sai. */}
                {!coTien && (
                  <div className="tg-sheetbox__foot">
                    {liveMeta.gia_von_tp > 0
                      ? "Chưa tách được từng dòng — máy chủ đang trả bản dữ liệu cũ. Con số tổng vẫn đúng."
                      : "Chưa có dòng tiền nào — kiểm tra ô Công thức tính giá ở danh mục Giấy và danh mục Công đoạn."}
                  </div>
                )}
                {nvl.giay.map((d, i) => (
                  <div className="tg-sheetrow" key={`g${i}`}>
                    <span className="tg-sheetrow__stack">
                      Giấy
                      <HaiDongCongThuc d={d} tra={tra} />
                    </span>
                    <SoDv so={fmt(Math.round(d.tien))} dv="đ" />
                  </div>
                ))}
                {nvl.vatTu.map((d, i) => (
                  <div className="tg-sheetrow" key={`v${i}`}>
                    <span className="tg-sheetrow__stack">
                      {d.ten.split(" · ").pop()}
                      <HaiDongCongThuc d={d} tra={tra} />
                    </span>
                    <SoDv so={fmt(Math.round(d.tien))} dv="đ" />
                  </div>
                ))}
                {dsCongDoan.length > 0 && (
                  <>
                    <div className="tg-sheetrow tg-sheetrow--group">
                      <span>Công đoạn <small>{dsCongDoan.length} bước</small></span>
                      <SoDv so={fmt(Math.round(tienCongDoan))} dv="đ" />
                    </div>
                    {/* Liệt kê ĐỦ từng bước, không gộp: người lập phiếu cần thấy bước nào ăn bao
                        nhiêu để còn thương lượng, và để bắt được bước khai nhầm công thức. Dòng
                        diễn giải là công thức ĐÃ THẾ SỐ — thứ cho phép kiểm lại con số bằng tay. */}
                    {dsCongDoan.map((d, i) => (
                      <div className="tg-sheetrow tg-sheetrow--sub" key={`cd${i}`}>
                        <span className="tg-sheetrow__stack">
                          {d.ten}
                          <HaiDongCongThuc d={d} tra={tra} />
                        </span>
                        <SoDv so={fmt(Math.round(d.tien))} dv="đ" />
                      </div>
                    ))}
                  </>
                )}
                {/* PHÍ KHUÔN — nằm TRONG giá vốn nhưng đứng thành khối riêng, ngay trên dòng tổng.
                    Xếp lẫn với sáu bước chạy máy thì người đọc tưởng nó cũng co giãn theo sản
                    lượng; tách ra kèm chữ "một lần" mới thấy đúng bản chất. */}
                {dsKhuon.length > 0 && (
                  <>
                    <div className="tg-sheetrow tg-sheetrow--group">
                      <span>Phí khuôn <small>một lần</small></span>
                      <SoDv so={fmt(Math.round(tienKhuon))} dv="đ" />
                    </div>
                    {dsKhuon.map((d, i) => (
                      <div className="tg-sheetrow tg-sheetrow--sub" key={`k${i}`}>
                        <span className="tg-sheetrow__stack">
                          {d.ten}
                          {/* Không dùng `HaiDongCongThuc`: dòng khuôn không có công thức gốc, và
                              chuỗi engine trả về đã tự chứa dấu "=" nên thêm "= " nữa là hai dấu
                              bằng trong một câu. Ở đây chỉ cần vế "÷ SL = đ/sp". */}
                          {d.congThuc && (
                            <em className="tg-sheetrow__derive tg-sheetrow__derive--so">{d.congThuc}</em>
                          )}
                        </span>
                        <SoDv so={fmt(Math.round(d.tien))} dv="đ" />
                      </div>
                    ))}
                  </>
                )}
                <div className="tg-sheetrow tg-sheetrow--total">
                  <span className="tg-sheetrow__stack">
                    = Giá vốn sản phẩm
                    {/* Chưa có dòng nào thì dòng hướng dẫn ở trên đã nói rồi — thêm cảnh báo lệch
                        nữa là kêu hai lần cùng một chuyện, mà con số "lệch" khi đó bằng đúng tổng,
                        đọc lên như một lỗi thứ hai. */}
                    {coTien && lechTien > 1 && (
                      <em className="tg-sheetrow__derive">
                        Lệch {fmt(Math.round(lechTien))} đ so với tổng các dòng đang hiện — còn dòng
                        engine tính mà panel chưa liệt kê.
                      </em>
                    )}
                  </span>
                  <SoDv so={fmt(Math.round(liveMeta!.gia_von_tp))} dv="đ" />
                </div>
                <div className="tg-sheetbox__foot">
                  {fmt(Math.round(liveMeta!.gia_von_don))} đ / {c.don_vi_tinh || "cái"}
                </div>
                {/* Dòng "+ Phí khuôn" và "= Tổng chi phí đơn hàng" ở đây đã GỠ 15/08/2026: phí dao
                    nay nằm TRONG giá vốn nên `= Giá vốn sản phẩm` ở trên đã là tổng thật, thêm một
                    dòng tổng nữa là hai con số bằng nhau xếp chồng, đọc lên tưởng thiếu chỗ nào. */}
              </div>
            )}
          </div>
        </div>

        <footer className="rc-modal__foot">
          <Button type="button" variant="ghost" onClick={onRemove}>
            Xóa sản phẩm
          </Button>
          <Button type="button" variant="primary" onClick={onClose}>
            Xong
          </Button>
        </footer>
      </div>
    </div>
  );
}

// ---------- Inline icons (line-icon, stroke=currentColor — KHÔNG emoji) ----------
const LockIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0, marginTop: "1px" }}>
    <rect x="3" y="11" width="18" height="11" rx="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`tg-chev${open ? " tg-chev--open" : ""}`}>
    <path d="m9 18 6-6-6-6" />
  </svg>
);

const CalcIcon = () => (
  <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="tg-empty__icon">
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M8 6h8M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h4M8 18h.01M12 18h.01" />
  </svg>
);

const BackIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m15 18-6-6 6-6" />
  </svg>
);

const PlusIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 5v14M5 12h14" />
  </svg>
);


const CloseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);

const TrashIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6" />
  </svg>
);

const AutoIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 3v4M3 5h4M6 17v4M4 19h4M13 3l2.5 6.5L22 12l-6.5 2.5L13 21l-2.5-6.5L4 12l6.5-2.5z" />
  </svg>
);

const RevertIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5" />
  </svg>
);

const WarnIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <path d="M12 9v4M12 17h.01" />
  </svg>
);

// Panel-header line icons (Lucide-style, stroke currentColor → tô rust qua .panel__hd h3 svg).
const GridIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 10h18M9 4v16" />
  </svg>
);
const RowsIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
  </svg>
);
const FileIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6M9 13h6M9 17h4" />
  </svg>
);
const BoltIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
  </svg>
);
const RefreshIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 12a9 9 0 1 1-3-6.7" />
    <path d="M21 4v5h-5" />
  </svg>
);

// Icon dòng Hoạt động theo action audit (KHÔNG glyph/emoji — SVG nét).
function ActIcon({ action }: { action: string }) {
  if (action === "create_ptg") return <PlusIcon />;
  if (action === "delete_ptg") return <CloseIcon />;
  return <RefreshIcon />;
}
