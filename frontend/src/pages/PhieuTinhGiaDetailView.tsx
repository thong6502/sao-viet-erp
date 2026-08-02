// DETAIL của "Tính giá" — GIÁ VỐN theo SẢN LƯỢNG, KHÔNG hệ số (redesign-tinh-gia.md).
// 1 phiếu = nhiều "Thành phần" giấy; mỗi thành phần = Giấy ① + Kỹ thuật in ② + Màu + Gia công.
// UI: LIST (bám RebuildCatalogPage: badge + row + Sửa/Xóa) + DRAWER (.rc-drawer*) sửa 1 thành phần,
// trong drawer có SƠ ĐỒ BÌNH BÀI live. Auto + override giữ nguyên. "Tính giá" = update(id) (BE
// replace-all + tính lại + snapshot) → refresh từ Out. LƯU = TÍNH.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import {
  api,
  ApiError,
  LSX_DON_VI_LABELS,
  type PhieuTinhGiaOut,
  type PhieuTinhGiaColOut,
  type PtgActivity,
  type ThanhPhanIn,
  type ThanhPhanOut,
  type ThanhPhamOut,
  type VatTuLineOut,
  type TinhGiaComponentMeta,
  type TinhGiaPreviewOut,
} from "../api/client";
import { congDoan, giay, loaiSanPham, mayThietBi, vatTu, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ImpositionDiagram } from "./ImpositionDiagram";
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
const vtName = (r: Row): string => `${r.ma ? String(r.ma) + " · " : ""}${String(r.ten)}`;
const numOf = (v: unknown): number => (typeof v === "number" ? v : Number(v) || 0);

/** Số BÀI IN = số trang ÷ trang mỗi tay — dẫn xuất y hệt engine (`thanh_phan_engine`), FE chỉ
 *  hiện lại cho người khai thấy ngay, không gửi lên. */
const soBaiIn = (c: { so_trang: number; trang_moi_tay: number }): number =>
  Math.max(1, Math.ceil((c.so_trang || 1) / (c.trang_moi_tay || 1)));

/** Chừa TÁCH THEO CHIỀU — khớp `chua_theo_chieu` của engine (đừng để hai bên lệch nhau).
 *
 *  · DÀI  ← nhíp GIẤY (cạnh nạp, 1 đầu) + đuôi/thanh màu
 *  · RỘNG ← lề hông ×2 (hai bên)
 *
 * Nguồn là DANH MỤC MÁY; phiếu chỉ còn một ô đè `chua_nhip`. Không chọn máy → chừa 0 cả hai chiều.
 * `gripper_mm` là nhíp KẼM — KHÔNG dùng ở đây (dùng nhầm là hụt 14-19% số con). */
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
// riêng ở đây, dùng thẳng `LSX_DON_VI_LABELS` (một nguồn cho cả danh mục · lệnh SX · tính giá).
const dvNgan = (v: string | null | undefined) => (v ? (LSX_DON_VI_LABELS[v] ?? v) : "");

const FORMULA_UNIT: Record<string, string> = {
  to_nguyen: "tờ", to_dau_vao: "tờ", so_to: "tờ",
  don_gia: "đ", don_gia_kg: "đ/kg", don_gia_luot: "đ/lượt", don_gia_kem: "đ/kẽm",
  dinh_luong: "gsm", dai_nguyen: "cm", rong_nguyen: "cm",
  so_mat: "mặt", so_kem: "kẽm", so_luong: "cái",
};
// Tên hàm toán (max/min/ceil/floor/round) — GIỮ NGUYÊN trong diễn giải, không humanize như biến.
const MATH_FN = new Set(["max", "min", "ceil", "floor", "round"]);
function humanizeFormula(s: string): string {
  if (!s) return s;
  // Chỉ match token biến-thế-số dạng name(SỐ) — inner chỉ gồm chữ số/dấu . , khoảng trắng.
  // Nhờ vậy KHÔNG "nuốt" lời gọi hàm max(so_kem(4) × …) (inner của hàm có chữ + toán tử).
  return s.replace(/([a-zA-Z_][a-zA-Z0-9_]*)\(([\d.,\s]*)\)/g, (m, name: string, val: string) => {
    if (MATH_FN.has(name)) return m;   // giữ nguyên vd max(380.000, 999.000)
    const unit = FORMULA_UNIT[name];
    const v = val.trim();
    return unit ? `${v} ${unit}` : v;
  });
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
  nguon_giay: string; // cong_ty | khach
  bu_hao_so_to: number;
  hao_so_to: number;
  tinh_bu_hao_cd: boolean; // bật/tắt tính bù hao công đoạn tự
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
  // Màu (gộp)
  so_mau_a: number;
  so_mau_b: number;
  so_mau_pha: number;
  ghi_chu_ky_thuat: string; // Lưu ý SX / ghi chú kỹ thuật theo sản phẩm → drawer lệnh SX
  gia_von_tp: number; // read-only từ lần tính gần nhất
  thanh_phams: EditableFinishing[];
  vat_tus: EditableVatTu[];
}

function blankVatTu(ten = "", vat_tu_id: number | null = null): EditableVatTu {
  return { uid: nextUid(), vat_tu_id, ten, don_gia: 0, so_luong: 0, ghi_chu: "" };
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
    bu_hao_so_to: 0,
    hao_so_to: 0,
    tinh_bu_hao_cd: true,
    chua_nhip: 0,
    bleed_mm: 0,
    khe_cat_mm: 0,
    quy_cach_in: "mot_mat",
    kho_in_dai: 0,
    kho_in_rong: 0,
    so_con: 1,
    con_auto: true,
    may_id: null,
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
    bu_hao_so_to: c.bu_hao_so_to ?? 0,
    hao_so_to: c.hao_so_to ?? 0,
    tinh_bu_hao_cd: c.tinh_bu_hao_cd ?? true,
    chua_nhip: c.chua_nhip ?? 0,
    bleed_mm: c.bleed_mm ?? 0,
    khe_cat_mm: c.khe_cat_mm ?? 0,
    quy_cach_in: c.quy_cach_in ?? "mot_mat",
    kho_in_dai: c.kho_in_dai ?? 0,
    kho_in_rong: c.kho_in_rong ?? 0,
    so_con: c.so_con ?? 1,
    con_auto: c.con_auto ?? true,
    may_id: c.may_id ?? null,
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
    bu_hao_so_to: c.bu_hao_so_to,
    hao_so_to: c.hao_so_to,
    tinh_bu_hao_cd: c.tinh_bu_hao_cd,
    chua_nhip: c.chua_nhip,
    bleed_mm: c.bleed_mm,
    khe_cat_mm: c.khe_cat_mm,
    quy_cach_in: c.quy_cach_in,
    kho_in_dai: c.kho_in_dai,
    kho_in_rong: c.kho_in_rong,
    so_con: c.so_con,
    con_auto: c.con_auto,
    may_id: c.may_id,
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
  soLuong: number,
  khoThanhPham: string,
  sanPhams: { ten: string; soLuong: number; dvt: string }[],
): PhieuTinhGia {
  const now = new Date();
  return {
    header: {
      soPhieu,
      ngayLap: now.toLocaleDateString("vi-VN"),
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
                ? humanizeFormula((val ?? "").toString())  // bản in cũng dễ đọc: "2.000 đ × 283 tờ"
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

function NumField({
  label,
  value,
  onChange,
  min = 0,
  step,
  opt,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min?: number;
  step?: string;
  opt?: string;
  suffix?: string;
}) {
  return (
    <label className="tg-field">
      <span className="tg-microlabel">
        {label}
        {opt ? <span className="tg-microlabel__opt">{opt}</span> : null}
      </span>
      <div className={suffix ? "tg-suffixwrap" : undefined}>
        <input
          className="tg-input tg-input--num"
          type="number"
          min={min}
          step={step}
          value={value}
          onChange={(e) => onChange(Math.max(min, Number(e.target.value)))}
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
  id: number;
  onBack: () => void;
  // BG-3: điều hướng sang Báo giá (openQuoteId đã wired ở AppShell). Không truyền → ẩn nút báo giá.
  navigate?: (pageId: string, params?: { openQuoteId?: number }) => void;
}) {
  const { token } = useAuth();
  const [quoting, setQuoting] = useState(false);

  // --- Danh mục nguồn ---
  const [loaiSPs, setLoaiSPs] = useState<Row[]>([]);
  const [giays, setGiays] = useState<Row[]>([]);
  const [mays, setMays] = useState<Row[]>([]);
  const [congDoans, setCongDoans] = useState<Row[]>([]);
  const [vatTus, setVatTus] = useState<Row[]>([]);

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
  // Bình bài NGHỊCH: uid → true khi gõ Số con mà KHÔNG xếp được đúng N trong khổ giấy nguyên.

  // --- Kết quả ---
  const [result, setResult] = useState<TinhGiaPreviewOut | null>(null);
  const [warnList, setWarnList] = useState<string[]>([]);
  // Nhật ký hoạt động THẬT (ai làm gì · khi nào) — nhiều người cùng sửa 1 phiếu.
  const [acts, setActs] = useState<PtgActivity[]>([]);
  const [showAllActs, setShowAllActs] = useState(false); // UI-only: "Xem tất cả"
  const [loading, setLoading] = useState(true);
  const [calcing, setCalcing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const applyOut = useCallback((out: PhieuTinhGiaOut) => {
    setMa(out.ma);
    setKtv(out.ktv);
    setNgay(out.created_at ? out.created_at.slice(0, 10) : null);
    setTongGiaVon(out.tong_gia_von);
    setKhoThanhPham(out.kho_thanh_pham ?? "");
    setLoaiSPId(out.loai_san_pham_id ?? "");
    setComps((out.thanh_phans ?? []).map(fromComponent));
    setResult(out.result);
    setWarnList(out.result?.warnings ?? out.warnings ?? []);
  }, []);

  // Nạp nhật ký hoạt động của phiếu (mới→cũ) từ backend.
  const loadActs = useCallback(() => {
    if (!token) return;
    api.phieuTinhGia
      .activity(token, id)
      .then((r) => setActs(r.items))
      .catch(() => setActs([]));
  }, [token, id]);

  // Nạp 4 danh mục 1 lần.
  useEffect(() => {
    if (!token) return;
    loaiSanPham.list(token).then((r) => setLoaiSPs(r.items)).catch(() => setLoaiSPs([]));
    giay.list(token).then((r) => setGiays(r.items)).catch(() => setGiays([]));
    mayThietBi.list(token).then((r) => setMays(r.items)).catch(() => setMays([]));
    congDoan.list(token).then((r) => setCongDoans(r.items)).catch(() => setCongDoans([]));
    vatTu.list(token).then((r) => setVatTus(r.items)).catch(() => setVatTus([]));
  }, [token]);

  // Nạp phiếu.
  useEffect(() => {
    if (!token) return;
    let alive = true;
    setLoading(true);
    setErr(null);
    api.phieuTinhGia
      .get(token, id)
      .then((out) => {
        if (alive) {
          applyOut(out);
          loadActs();
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
  // (Bản cũ copy `gripper_mm` = nhíp KẼM ~44mm vào `chua_nhip` làm chừa GIẤY rồi trừ cả hai
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
  const removeFin = useCallback((cuid: string, fuid: string) => {
    setComps((cs) =>
      cs.map((c) =>
        c.uid === cuid ? { ...c, thanh_phams: c.thanh_phams.filter((f) => f.uid !== fuid) } : c,
      ),
    );
  }, []);

  const addVt = useCallback((cuid: string, vat_tu_id: number | null = null, ten = "") => {
    setComps((cs) =>
      cs.map((c) =>
        c.uid === cuid ? { ...c, vat_tus: [...c.vat_tus, blankVatTu(ten, vat_tu_id)] } : c,
      ),
    );
  }, []);
  const removeVt = useCallback((cuid: string, vuid: string) => {
    setComps((cs) =>
      cs.map((c) =>
        c.uid === cuid ? { ...c, vat_tus: c.vat_tus.filter((v) => v.uid !== vuid) } : c,
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
      ma: c.so_mau_a, mb: c.so_mau_b, mp: c.so_mau_pha, bu: c.bu_hao_so_to, hao: c.hao_so_to,
      tbh: c.tinh_bu_hao_cd,
      ch: c.chua_nhip,
      bl: c.bleed_mm, ke: c.khe_cat_mm,
      gid: c.giay_id, may: c.may_id, cds: c.thanh_phams.map((f) => f.cong_doan_id),
    });
  }, [editingComp, phieuSL]);
  useEffect(() => {
    if (!token || !editingComp) {
      setEditMeta(null);
      return;
    }
    const snapshot = editingComp;
    const h = window.setTimeout(() => {
      api.tinhGia
        .preview(token, { so_luong: phieuSL, thanh_phans: [toThanhPhanIn(snapshot)] })
        .then((r) => setEditMeta(r.meta?.components?.[0] ?? null))
        .catch(() => {});
    }, 300);
    return () => window.clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewSig, token]);

  // "Tính giá" = LƯU + TÍNH LẠI (BE) → refresh từ Out.
  const calc = useCallback(() => {
    if (!token) return;
    setCalcing(true);
    setErr(null);
    api.phieuTinhGia
      .update(token, id, {
        kho_thanh_pham: khoThanhPham.trim() || null,
        loai_san_pham_id: loaiSPId === "" ? null : loaiSPId,
        thanh_phans: comps.map(toThanhPhanIn),
      })
      .then((out) => {
        applyOut(out);
        loadActs(); // phản ánh ngay dòng "Cập nhật phiếu" vừa ghi.
      })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tính được giá. Thử lại."))
      .finally(() => setCalcing(false));
  }, [token, id, khoThanhPham, loaiSPId, comps, applyOut, loadActs]);

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
    if (!token || !navigate) return;
    setQuoting(true);
    setErr(null);
    try {
      const q = await api.quotations.create(token, {
        phieu_tinh_gia_id: id, customer_id: null, valid_until: null,
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
    let slPhieu = 0;
    for (const node of danhSachHienThi) {
      if (node.kind === "don") {
        const t = (node.comp.ten || "").trim();
        if (t) names.push(t);
        slPhieu += slCua(node.comp);
      } else {
        names.push(node.ten);
        slPhieu += slCua(node.members[0]);
      }
    }
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
    return toPhieu(result, ma || "(chưa lưu)", tenAnPham, slPhieu, khoThanhPham, sanPhams);
  }, [result, ma, khoThanhPham, comps, danhSachHienThi, phieuSL]);

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
  const loaiLabelOf = useCallback(
    (c: EditableComponent): string => {
      if (c.loai_san_pham_id != null) {
        const sp = loaiSPById.get(c.loai_san_pham_id);
        if (sp?.ten) return String(sp.ten);
      }
      return loaiTpLabel(c.loai_thanh_phan);
    },
    [loaiSPById],
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

  return (
    <main className="rdx-cost tg-page">
      {/* ---------- HEAD ---------- */}
      <header className="tg-head">
        <div className="tg-head__lead">
          <button type="button" className="tg-back" onClick={onBack}>
            <BackIcon /> Danh sách
          </button>
          <div className="eyebrow tg-head__eyebrow">
            <LockIcon /> Giá vốn nội bộ
          </div>
          <div className="tg-head__titlerow">
            <h1 className="tg-head__title">{ma || "Phiếu tính giá"}</h1>
          </div>
        </div>
        <div className="tg-head__actions">
          <Button variant="accent" onClick={calc} loading={calcing} disabled={!token || loading}>
            Tính giá
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
              disabled={!token || loading}
              title="Tạo / mở báo giá từ phiếu tính giá này"
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
                                <span className="badge neutral"><span className="d" />{loaiLabelOf(c)}</span>
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
                                {node.members.length} sản phẩm · gộp 1 dòng khi báo giá
                              </span>
                            </td>
                            <td />
                            <td className="num mono">{slNhom > 0 ? fmt(slNhom) : "—"}</td>
                            <td className="num strong">
                              {tongVon > 0 ? `${fmt(tongVon)} đ` : "—"}
                            </td>
                            <td className="num rust-num">
                              {tongVon > 0 && slNhom > 0
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
                                        <span className="derive">{humanizeFormula(val)}</span>
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
                <div className="irow"><span className="k">Mã phiếu</span><span className="v mono">{ma || "—"}</span></div>
                <div className="irow"><span className="k">KTV</span><span className="v">{ktv ?? "—"}</span></div>
                <div className="irow"><span className="k">Ngày lập</span><span className="v">{ngay ? new Date(ngay).toLocaleDateString("vi-VN") : "—"}</span></div>
                <div className="irow">
                  <span className="k">Trạng thái</span>
                  <span className="v">
                    {result && result.grand_total > 0 ? (
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
                  <p className="tg-empty__sub" style={{ margin: "4px 0" }}>Chưa có hoạt động.</p>
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

            {warnList.length > 0 ? (
              <section className="tg-warn" role="status">
                <div className="tg-warn__title">Lưu ý ({warnList.length})</div>
                <ul className="tg-warn__list">
                  {warnList.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </section>
            ) : null}
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
          vatTus={vatTus}
          liveMeta={editMeta}
          phieuSL={phieuSL}
          onClose={closeEditor}
          onRemove={() => {
            removeComp(editing.uid);
            setEditingUid(null);
            setPendingCalc(true);  // xóa xong → tính lại sau khi comps cập nhật (tránh closure cũ)
          }}
          patchComp={patchComp}
          onPickLoaiSP={onPickLoaiSPForComp}
          onPickGiay={onPickGiay}
          onPickMay={onPickMay}
          addFin={addFin}
          removeFin={removeFin}
          addVt={addVt}
          removeVt={removeVt}
        />
      ) : null}

      {/* ---------- Phiếu in (chỉ hiện khi @media print) ---------- */}
      {phieu ? (
        <div className="tg-print-only">
          <PhieuTinhGiaPrint data={phieu} />
        </div>
      ) : null}
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
  vatTus,
  liveMeta,
  phieuSL,
  onClose,
  onRemove,
  patchComp,
  onPickLoaiSP,
  onPickGiay,
  onPickMay,
  addFin,
  removeFin,
  addVt,
  removeVt,
}: {
  comp: EditableComponent;
  idx: number;
  loaiSPs: Row[];
  giays: Row[];
  mays: Row[];
  congDoans: Row[];
  vatTus: Row[];
  liveMeta: TinhGiaComponentMeta | null;
  phieuSL: number;
  onClose: () => void;
  onRemove: () => void;
  patchComp: (uid: string, patch: Partial<EditableComponent>) => void;
  onPickLoaiSP: (uid: string, pid: number | "") => void;
  onPickGiay: (uid: string, gid: number | null) => void;
  onPickMay: (uid: string, mid: number | null) => void;
  addFin: (cuid: string, cong_doan_id?: number | null, ten?: string, insertIndex?: number | null) => void;
  removeFin: (cuid: string, fuid: string) => void;
  addVt: (cuid: string, vat_tu_id?: number | null, ten?: string) => void;
  removeVt: (cuid: string, vuid: string) => void;
}) {
  // uid của sản phẩm đang mở trợ lý "tính số khuôn từ số trang" (mỗi lúc chỉ 1 popover).
  const [calcUid, setCalcUid] = useState<string | null>(null);
  // Bung phân rã bù hao: bước nào trong chuỗi ăn bao nhiêu tờ. Mặc định thu gọn.
  const [moPhanRa, setMoPhanRa] = useState(false);
  // "Tờ sau in" là tờ tốt ra khỏi bước IN — neo vào đúng bước đó để không phải đoán con số ở đâu ra.
  const buocIn = liveMeta?.bu_hao_chi_tiet?.find((b) => b.nhom === "print") ?? null;
  const chuaCh = chuaTheoChieu(c, c.may_id ? mays.find((x) => x.id === c.may_id) : null);
  // Ô này chọn MÁY IN — engine lấy khổ giấy máy nhận + vùng in + nhíp giấy để bình bài. Máy bế,
  // máy bồi sóng, máy cán màng KHÔNG có mấy thông số đó, đổ vào chỉ tổ chọn nhầm (chúng thuộc
  // chuỗi công đoạn, không thuộc ô này). Danh mục đặt tên loại khác đi mà lọc ra rỗng thì hiện
  // lại tất — thà thừa còn hơn khoá người dùng không chọn được gì.
  const mayIn = useMemo(() => {
    const loc = mays.filter((m) => /(^|\W)in(\W|$)/i.test(String(m.loai_may ?? "")));
    return loc.length > 0 ? loc : mays;
  }, [mays]);
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
                  <input
                    className="tg-input"
                    type="text"
                    value={c.ten}
                    placeholder="VD Thân hộp / Ruột / Bìa"
                    onChange={(e) => patchComp(c.uid, { ten: e.target.value })}
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
                  <input
                    className="tg-input"
                    type="text"
                    value={c.don_vi_tinh}
                    placeholder="cái / tờ / cuốn / hộp…"
                    onChange={(e) => patchComp(c.uid, { don_vi_tinh: e.target.value })}
                  />
                </label>
                {/* Gộp dòng khi báo giá KHÔNG có ô ở đây: nó là quan hệ giữa các dòng, thao tác
                    nằm ở bảng "Sản phẩm trong phiếu" (tick nhiều dòng → gõ tên nhóm 1 lần). */}
                <label className="tg-field tg-span-12">
                  <span className="tg-microlabel">
                    Loại sản phẩm <span className="tg-microlabel__opt">tự bung công đoạn mặc định</span>
                  </span>
                  <select
                    className="tg-input"
                    value={c.loai_san_pham_id ?? ""}
                    onChange={(e) =>
                      onPickLoaiSP(c.uid, e.target.value === "" ? "" : Number(e.target.value))
                    }
                  >
                    <option value="">— Chọn loại sản phẩm —</option>
                    {loaiSPs.map((s) => (
                      <option key={s.id} value={s.id}>
                        {rowLabel(s)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="tg-span-6">
                      <NumField
                        label="Dài chi tiết phẳng"
                        value={c.dai_thanh_pham}
                        onChange={(n) => patchComp(c.uid, { dai_thanh_pham: n })}
                        suffix="mm"
                      />
                    </div>
                    <div className="tg-span-6">
                      <NumField
                        label="Rộng chi tiết phẳng"
                        value={c.rong_thanh_pham}
                        onChange={(n) => patchComp(c.uid, { rong_thanh_pham: n })}
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
                    suffix="mm"
                  />
                </div>
                <div className="tg-span-6">
                  <NumField
                    label="Khe cắt giữa con"
                    value={c.khe_cat_mm}
                    onChange={(n) => patchComp(c.uid, { khe_cat_mm: n })}
                    opt="0 = bình sát, cắt chung nhát"
                    suffix="mm"
                  />
                </div>
              </div>
            </section>

            {/* ---- GIẤY IN ---- */}
            <section className="rc-sec">
              <div className="rc-sec__title">
                <span className="tg-step-badge">2</span> Giấy in
              </div>
              <div className="tg-grid">
                <label className="tg-field tg-span-8">
                  <span className="tg-microlabel">Loại giấy</span>
                  <select
                    className="tg-input"
                    value={c.giay_id ?? ""}
                    onChange={(e) => onPickGiay(c.uid, e.target.value === "" ? null : Number(e.target.value))}
                  >
                    <option value="">— Chọn giấy —</option>
                    {giays.map((g) => (
                      <option key={g.id} value={g.id}>
                        {rowLabel(g)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="tg-field tg-span-4">
                  <span className="tg-microlabel">Nguồn giấy</span>
                  <Seg
                    ariaLabel="Nguồn giấy"
                    value={c.nguon_giay}
                    onChange={(v) => patchComp(c.uid, { nguon_giay: v })}
                    options={[
                      { val: "cong_ty", label: "Công ty" },
                      { val: "khach", label: "Khách cấp" },
                    ]}
                  />
                </div>
                <div className="tg-span-3">
                  <NumField
                    label="Dài nguyên"
                    value={c.kho_nguyen_dai}
                    onChange={(n) => patchComp(c.uid, { kho_nguyen_dai: n })}
                    suffix="mm"
                  />
                </div>
                <div className="tg-span-3">
                  <NumField
                    label="Rộng nguyên"
                    value={c.kho_nguyen_rong}
                    onChange={(n) => patchComp(c.uid, { kho_nguyen_rong: n })}
                    suffix="mm"
                  />
                </div>
                <div className="tg-field tg-span-6">
                  <span className="tg-microlabel">
                    Đơn giá giấy <span className="tg-microlabel__opt">theo danh mục</span>
                  </span>
                  <div className="tg-readout" style={{ minHeight: "36px", display: "flex", alignItems: "center" }}>
                    {(() => {
                      const g = c.giay_id ? giays.find((x) => x.id === c.giay_id) : null;
                      if (!g) return "— chọn giấy để lấy giá —";
                      const u = g.don_vi_gia;
                      const uL =
                        u === "tan" ? "tấn" : u === "kg" ? "kg" : u === "ram" ? "ram" : u === "cai" ? "cái" : "tờ";
                      return `${fmt(numOf(g.don_gia))} đ / ${uL}`;
                    })()}
                  </div>
                  {c.nguon_giay === "khach" && (
                    <span className="tg-hint" style={{ marginTop: "-4px" }}>Khách cấp giấy — không tính tiền giấy.</span>
                  )}
                </div>
              </div>
            </section>

            {/* ---- KỸ THUẬT IN & MÀU IN ---- */}
            <section className="rc-sec">
              <div className="rc-sec__title">
                <span className="tg-step-badge">3</span> Kỹ thuật in &amp; Màu in
              </div>
              <div className="tg-grid">
                <label className="tg-field tg-span-8">
                  <span className="tg-microlabel">
                    Máy in <span className="tg-microlabel__opt">→ khổ tờ in</span>
                  </span>
                  <select
                    className="tg-input"
                    value={c.may_id ?? ""}
                    onChange={(e) => onPickMay(c.uid, e.target.value === "" ? null : Number(e.target.value))}
                  >
                    <option value="">— Không chọn —</option>
                    {mayIn.map((m) => (
                      <option key={m.id} value={m.id}>
                        {rowLabel(m)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="tg-field tg-span-4">
                  <span className="tg-microlabel">Quy cách in</span>
                  <Seg
                    ariaLabel="Quy cách in"
                    value={c.quy_cach_in}
                    onChange={(v) => patchComp(c.uid, { quy_cach_in: v })}
                    options={[
                      { val: "mot_mat", label: "1 mặt" },
                      { val: "hai_mat", label: "AB" },
                      { val: "tu_tro", label: "Tự trở" },
                      { val: "tro_nhip", label: "Trở nhíp" },
                    ]}
                  />
                </div>
                <div className="tg-span-3">
                  <NumField
                    label="Khổ tờ in dài"
                    value={c.kho_in_dai}
                    onChange={(n) => patchComp(c.uid, { kho_in_dai: n })}
                    suffix="mm"
                  />
                </div>
                <div className="tg-span-3">
                  <NumField
                    label="Khổ tờ in rộng"
                    value={c.kho_in_rong}
                    onChange={(n) => patchComp(c.uid, { kho_in_rong: n })}
                    suffix="mm"
                  />
                </div>
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
                <div className={c.quy_cach_in === "hai_mat" ? "tg-span-6" : "tg-span-12"}>
                  <NumField
                    label="Số màu mặt A"
                    value={c.so_mau_a}
                    step="1"
                    onChange={(n) => patchComp(c.uid, { so_mau_a: n })}
                  />
                </div>
                {c.quy_cach_in === "hai_mat" && (
                  <div className="tg-span-6">
                    <NumField
                      label="Số màu mặt B"
                      value={c.so_mau_b}
                      step="1"
                      onChange={(n) => patchComp(c.uid, { so_mau_b: n })}
                    />
                  </div>
                )}
                {/* Màu pha = mực riêng, chạy 1 đơn vị máy riêng → CỘNG THÊM bản kẽm.
                    Ô "Số màu mặt A/B" ở trên là màu PROCESS, không gồm màu pha. */}
                <div className="tg-span-12">
                  <NumField
                    label="Màu pha (Pantone)"
                    value={c.so_mau_pha}
                    step="1"
                    onChange={(n) => patchComp(c.uid, { so_mau_pha: n })}
                    opt="cộng thêm kẽm · 0 = chỉ in màu process"
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
                {c.thanh_phams.map((f, fIdx) => (
                  <div key={f.uid} className="tg-timeline-item">
                    <span className="tg-chip">
                      <span className="tg-chip__name">
                        {f.ten || "(công đoạn)"}
                      </span>
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
                    {fIdx < c.thanh_phams.length - 1 && (
                      <div className="tg-timeline-arrow-wrap">
                        <select
                          className="tg-timeline-select-arrow"
                          title="Chèn công đoạn vào giữa"
                          value=""
                          onChange={(e) => {
                            const v = e.target.value;
                            if (!v) return;
                            const insertIdx = fIdx + 1;
                            if (v === "__blank") {
                              addFin(c.uid, null, "", insertIdx);
                            } else {
                              const cd = congDoans.find((x) => String(x.id) === v);
                              addFin(c.uid, cd ? cd.id : null, cd ? cdName(cd) : "", insertIdx);
                            }
                          }}
                        >
                          <option value="">➔</option>
                          {congDoans.map((cd) => (
                            <option key={cd.id} value={cd.id}>
                              {cdName(cd)}
                            </option>
                          ))}
                          <option value="__blank">+ Tự nhập…</option>
                        </select>
                      </div>
                    )}
                  </div>
                ))}
                <select
                  className="tg-chip-add"
                  aria-label="Thêm công đoạn"
                  value=""
                  style={{ marginLeft: c.thanh_phams.length > 0 ? "8px" : "0" }}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (!v) return;
                    if (v === "__blank") {
                      addFin(c.uid);
                    } else {
                      const cd = congDoans.find((x) => String(x.id) === v);
                      addFin(c.uid, cd ? cd.id : null, cd ? cdName(cd) : "");
                    }
                  }}
                >
                  <option value="">+ Thêm công đoạn…</option>
                  {congDoans.map((cd) => (
                    <option key={cd.id} value={cd.id}>
                      {cdName(cd)}
                    </option>
                  ))}
                  <option value="__blank">+ Tự nhập…</option>
                </select>
              </div>

            </section>

            {/* ---- VẬT TƯ THÊM (mực/màng/keo → NGUYÊN VẬT LIỆU) ---- */}
            <section className="rc-sec">
              <div className="rc-sec__title">
                <span className="tg-step-badge">5</span> Vật tư thêm
              </div>
              <div className="tg-chipgrid">
                {c.vat_tus.length === 0 && (
                  <p className="tg-chipgrid__empty" style={{ margin: "6px 0" }}>
                    Thêm vật tư (mực…) — engine thế biến vào công thức của vật tư, hệt giấy.
                  </p>
                )}
                {c.vat_tus.map((v) => (
                  <span key={v.uid} className="tg-chip">
                    <span className="tg-chip__name">{v.ten || "(vật tư)"}</span>
                    <button
                      type="button"
                      className="tg-chip__x"
                      aria-label="Xóa vật tư"
                      title="Xóa khỏi phiếu"
                      onClick={() => removeVt(c.uid, v.uid)}
                    >
                      <CloseIcon />
                    </button>
                  </span>
                ))}
                <select
                  className="tg-chip-add"
                  aria-label="Thêm vật tư"
                  value=""
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!val) return;
                    if (val === "__blank") {
                      addVt(c.uid);
                    } else {
                      const m = vatTus.find((x) => String(x.id) === val);
                      addVt(c.uid, m ? m.id : null, m ? vtName(m) : "");
                    }
                  }}
                >
                  <option value="">+ Thêm vật tư…</option>
                  {vatTus.map((m) => (
                    <option key={m.id} value={m.id}>
                      {vtName(m)}
                    </option>
                  ))}
                  <option value="__blank">+ Tự nhập…</option>
                </select>
              </div>
            </section>
          </div>

          {/* Cột phải: Trực quan hóa và Số liệu ước lượng */}
          <div className="rc-modal__right-col">
            {/* SƠ ĐỒ BÌNH BÀI CARD */}
            <div className="tg-imp-card">
              <div className="tg-imp-card__title">Sơ đồ bình bài live</div>
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
              />
            </div>

            {/* SỐ TỜ (tính LIVE qua /preview) + ô Bù / Hao nhập tay */}
            <div className="tg-sheetbox">
              <div className="tg-sheetbox__title">
                Số tờ <span className="tg-sheetbox__hint">tự tính · engine thật</span>
              </div>
              <div className="tg-sheetrow">
                <span>Thành phẩm cần</span>
                <b>{liveMeta ? `${fmt(liveMeta.so_luong)} ${c.don_vi_tinh || "cái"}` : "…"}</b>
              </div>
              <div className="tg-sheetrow">
                <span className="tg-sheetrow__stack">
                  = Tờ in cần (chưa hao)
                  {liveMeta && liveMeta.con > 0 && (
                    <em className="tg-sheetrow__derive">
                      ⌈{fmt(liveMeta.so_luong)}
                      {(liveMeta.so_trang ?? 1) > 1 ? ` × ${fmt(liveMeta.so_trang ?? 1)} trang` : ""}
                      {" ÷ "}
                      {fmt(liveMeta.con)} con/tờ⌉
                    </em>
                  )}
                </span>
                <b>{liveMeta ? `${fmt(liveMeta.to_net)} tờ` : "…"}</b>
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
                    <b>{fmt(liveMeta?.bu_hao_auto ?? 0)} tờ</b>
                    <ChevronIcon open={moPhanRa} />
                  </button>
                ) : (
                  <b>{liveMeta ? `${fmt(liveMeta.bu_hao_auto ?? 0)} tờ` : "…"}</b>
                )}
              </div>
              {moPhanRa && (liveMeta?.bu_hao_chi_tiet?.length ?? 0) > 0 && (
                <ul className="tg-sheetbreak">
                  {liveMeta!.bu_hao_chi_tiet!.map((b, i) => {
                    const doiTiLe = b.dv_vao !== b.dv_ra && !!b.he_so && b.he_so !== 1;
                    const coHao = b.hao > 0;
                    const dvV = dvNgan(b.dv_vao);
                    const dvR = dvNgan(b.dv_ra);
                    const heSoText = doiTiLe
                      ? (b.he_so! < 1 ? `${fmt(1 / b.he_so!)} ${dvV} = 1 ${dvR}` : `1 ${dvV} = ${fmt(b.he_so!)} ${dvR}`)
                      : null;
                    const haoText = coHao
                      ? `cần ${fmt(b.ra_quy ?? 0)} ${dvV} tốt + ${fmt(b.hao)} hao = ${fmt(b.vao)} ${dvV}`
                      : null;

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
              <div className="tg-sheetrow tg-sheetrow--input">
                <span>+ Bù thêm</span>
                <input
                  className="tg-sheetinput"
                  type="number"
                  min={0}
                  step={1}
                  value={c.bu_hao_so_to}
                  onChange={(e) =>
                    patchComp(c.uid, { bu_hao_so_to: Math.max(0, Math.round(Number(e.target.value) || 0)) })
                  }
                />
              </div>
              <div className="tg-sheetrow tg-sheetrow--total">
                <span>= Tờ vào máy</span>
                <b>{liveMeta ? `${fmt(liveMeta.to_dau_vao)} tờ` : "…"}</b>
              </div>
              <div className="tg-sheetrow tg-sheetrow--total">
                <span className="tg-sheetrow__stack">
                  = Tờ sau in
                  {liveMeta && (
                    <em className="tg-sheetrow__derive">
                      {buocIn ? `tờ tốt ra khỏi "${buocIn.ten}"` : "chuỗi chưa có bước in → giữ tờ vào máy"}
                    </em>
                  )}
                </span>
                <b>{liveMeta ? `${fmt(liveMeta.to_sau_in)} tờ` : "…"}</b>
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
                        ⌈{fmt(liveMeta.to_dau_vao)} ÷ {fmt(liveMeta.so_manh_xa)} tờ in/tờ nguyên⌉
                      </em>
                    ) : null;
                  })()}
                </span>
                <b>{liveMeta ? `${fmt(liveMeta.to_nguyen)} tờ` : "…"}</b>
              </div>
              <div className="tg-sheetbox__foot">
                {liveMeta
                  ? `${fmt(liveMeta.con)} con/tờ · ${fmt(liveMeta.so_kem)} kẽm`
                  : "Nhập đủ khổ + số lượng để tính"}
              </div>
            </div>
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
