// DETAIL của "Tính giá" — GIÁ VỐN theo SẢN LƯỢNG, KHÔNG hệ số (redesign-tinh-gia.md).
// 1 phiếu = nhiều "Thành phần" giấy; mỗi thành phần = Giấy ① + Kỹ thuật in ② + Màu + Gia công.
// UI: LIST (bám RebuildCatalogPage: badge + row + Sửa/Xóa) + DRAWER (.rc-drawer*) sửa 1 thành phần,
// trong drawer có SƠ ĐỒ BÌNH BÀI live. Auto + override giữ nguyên. "Tính giá" = update(id) (BE
// replace-all + tính lại + snapshot) → refresh từ Out. LƯU = TÍNH.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  type PhieuTinhGiaOut,
  type PhieuTinhGiaColOut,
  type ThanhPhanIn,
  type ThanhPhanOut,
  type ThanhPhamOut,
  type TinhGiaComponentMeta,
  type TinhGiaPreviewOut,
} from "../api/client";
import { congDoan, giay, loaiSanPham, mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { DarkSummaryPanel } from "../components/DarkSummaryPanel";
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
const numOf = (v: unknown): number => (typeof v === "number" ? v : Number(v) || 0);

const LOAI_TP: Record<string, string> = {
  to_roi: "Tờ rời",
  than: "Thân",
  nap: "Nắp",
  bia: "Bìa",
  ruot: "Ruột",
  phu_kien: "Phụ kiện",
};
const loaiTpLabel = (v: string): string => LOAI_TP[v] ?? v;

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
interface EditableComponent {
  uid: string;
  loai_thanh_phan: string;
  ten: string;
  // Thành phẩm ③
  kho_thanh_pham: string; // nhãn tự do
  dai_thanh_pham: number; // mm
  rong_thanh_pham: number; // mm
  kho_mo_rong: string;
  tay_gap: string;
  so_to_per_sp: number;
  so_luong: number; // SL đặt của SP này (0 = lấy SL mặc định phiếu)
  loai_san_pham_id: number | null; // loại SP của sản phẩm này
  // Giấy ①
  giay_id: number | null;
  kho_nguyen: string;
  don_gia_giay: number;
  don_gia_don_vi: string; // to | tan
  nguon_giay: string; // cong_ty | khach
  bu_hao_so_to: number;
  chua_xen: number;
  chua_tay_ke: number;
  chua_nhip: number;
  chua_duoi: number;
  chua_ca_gay: number;
  // Kỹ thuật in ②
  co_in: boolean;
  che_ban_loai: string;
  che_ban_don_gia: number;
  quy_cach_in: string; // mot_mat | hai_mat | tu_tro
  kho_in_dai: number; // mm
  kho_in_rong: number; // mm
  so_con: number; // ④
  con_auto: boolean;
  may_id: number | null;
  don_gia_cong_in: number;
  // Màu (gộp)
  so_mau_a: number;
  so_mau_b: number;
  gia_von_tp: number; // read-only từ lần tính gần nhất
  thanh_phams: EditableFinishing[];
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
    kho_thanh_pham: "",
    dai_thanh_pham: 0,
    rong_thanh_pham: 0,
    kho_mo_rong: "",
    tay_gap: "",
    so_to_per_sp: 1,
    so_luong: 0,
    loai_san_pham_id: null,
    giay_id: null,
    kho_nguyen: "",
    don_gia_giay: 0,
    don_gia_don_vi: "to",
    nguon_giay: "cong_ty",
    bu_hao_so_to: 0,
    chua_xen: 0,
    chua_tay_ke: 0,
    chua_nhip: 0,
    chua_duoi: 0,
    chua_ca_gay: 0,
    co_in: true,
    che_ban_loai: "",
    che_ban_don_gia: 0,
    quy_cach_in: "mot_mat",
    kho_in_dai: 0,
    kho_in_rong: 0,
    so_con: 1,
    con_auto: true,
    may_id: null,
    don_gia_cong_in: 0,
    so_mau_a: 0,
    so_mau_b: 0,
    gia_von_tp: 0,
    thanh_phams: [],
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
function fromComponent(c: ThanhPhanOut): EditableComponent {
  return {
    uid: nextUid(),
    loai_thanh_phan: c.loai_thanh_phan ?? "to_roi",
    ten: c.ten ?? "",
    kho_thanh_pham: c.kho_thanh_pham ?? "",
    dai_thanh_pham: c.dai_thanh_pham ?? 0,
    rong_thanh_pham: c.rong_thanh_pham ?? 0,
    kho_mo_rong: c.kho_mo_rong ?? "",
    tay_gap: c.tay_gap ?? "",
    so_to_per_sp: c.so_to_per_sp ?? 1,
    so_luong: c.so_luong ?? 0,
    loai_san_pham_id: c.loai_san_pham_id ?? null,
    giay_id: c.giay_id ?? null,
    kho_nguyen: c.kho_nguyen ?? "",
    don_gia_giay: c.don_gia_giay ?? 0,
    don_gia_don_vi: c.don_gia_don_vi ?? "to",
    nguon_giay: c.nguon_giay ?? "cong_ty",
    bu_hao_so_to: c.bu_hao_so_to ?? 0,
    chua_xen: c.chua_xen ?? 0,
    chua_tay_ke: c.chua_tay_ke ?? 0,
    chua_nhip: c.chua_nhip ?? 0,
    chua_duoi: c.chua_duoi ?? 0,
    chua_ca_gay: c.chua_ca_gay ?? 0,
    co_in: c.co_in ?? true,
    che_ban_loai: c.che_ban_loai ?? "",
    che_ban_don_gia: c.che_ban_don_gia ?? 0,
    quy_cach_in: c.quy_cach_in ?? "mot_mat",
    kho_in_dai: c.kho_in_dai ?? 0,
    kho_in_rong: c.kho_in_rong ?? 0,
    so_con: c.so_con ?? 1,
    con_auto: c.con_auto ?? true,
    may_id: c.may_id ?? null,
    don_gia_cong_in: c.don_gia_cong_in ?? 0,
    so_mau_a: c.so_mau_a ?? 0,
    so_mau_b: c.so_mau_b ?? 0,
    gia_von_tp: c.gia_von_tp ?? 0,
    thanh_phams: (c.thanh_phams ?? []).map(fromFinishing),
  };
}

function toThanhPhanIn(c: EditableComponent): ThanhPhanIn {
  return {
    loai_thanh_phan: c.loai_thanh_phan,
    ten: c.ten,
    kho_thanh_pham: c.kho_thanh_pham.trim() || null,
    dai_thanh_pham: c.dai_thanh_pham,
    rong_thanh_pham: c.rong_thanh_pham,
    kho_mo_rong: c.kho_mo_rong.trim() || null,
    tay_gap: c.tay_gap.trim() || null,
    so_to_per_sp: c.so_to_per_sp,
    so_luong: c.so_luong,
    loai_san_pham_id: c.loai_san_pham_id,
    giay_id: c.giay_id,
    kho_nguyen: c.kho_nguyen.trim() || null,
    don_gia_giay: c.don_gia_giay,
    don_gia_don_vi: c.don_gia_don_vi,
    nguon_giay: c.nguon_giay,
    bu_hao_so_to: c.bu_hao_so_to,
    chua_xen: c.chua_xen,
    chua_tay_ke: c.chua_tay_ke,
    chua_nhip: c.chua_nhip,
    chua_duoi: c.chua_duoi,
    chua_ca_gay: c.chua_ca_gay,
    co_in: c.co_in,
    che_ban_loai: c.che_ban_loai.trim() || null,
    che_ban_don_gia: c.che_ban_don_gia,
    quy_cach_in: c.quy_cach_in,
    kho_in_dai: c.kho_in_dai,
    kho_in_rong: c.kho_in_rong,
    so_con: c.so_con,
    con_auto: c.con_auto,
    may_id: c.may_id,
    don_gia_cong_in: c.don_gia_cong_in,
    so_mau_a: c.so_mau_a,
    so_mau_b: c.so_mau_b,
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
  };
}

// Số kẽm client-side (khi chưa tính): (màu A + B) × số tờ/SP. Tự trở & 1 mặt chỉ tính mặt A.
function soKemOf(c: EditableComponent): number {
  const kemMau = c.quy_cach_in === "hai_mat" ? c.so_mau_a + c.so_mau_b : c.so_mau_a;
  return kemMau * Math.max(c.so_to_per_sp, 1);
}

// Engine (snake_case) → phiếu in (chuỗi format sẵn).
function toPhieu(
  res: TinhGiaPreviewOut,
  soPhieu: string,
  tenAnPham: string,
  soLuong: number,
  khoThanhPham: string,
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
      dvt: "Tờ",
    },
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
            out[c.key] = isNumCol(c) ? vnd(val as number) : (val ?? "").toString();
          }
          return out;
        }),
        subtotalLabel: `Cộng nhóm ${g.idx}`,
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

// Dải số [Hiện] read-only — soi sản lượng đã chốt sau khi Tính (meta) + ước lượng trước tính.
function HienStrip({ meta, comp }: { meta: TinhGiaComponentMeta | undefined; comp: EditableComponent }) {
  const items: { k: string; v: string; hint?: string }[] = [
    { k: "Con/tờ ④", v: meta ? fmt(meta.con) : fmt(comp.so_con) },
    { k: "Tờ in NET", v: meta ? fmt(meta.to_net) : "—" },
    { k: "Tờ in GROSS", v: meta ? fmt(meta.to_gross) : "—" },
    { k: "Tờ nguyên", v: meta ? fmt(meta.to_nguyen) : "—" },
    { k: "Số kẽm", v: meta ? fmt(meta.so_kem) : fmt(soKemOf(comp)) },
    { k: "Số lượt", v: meta ? fmt(meta.so_luot) : "—" },
  ];
  return (
    <div className="tg-hien" aria-label="Số liệu tự tính">
      {items.map((it) => (
        <div className="tg-hien__item" key={it.k}>
          <span className="tg-hien__k">{it.k}</span>
          <span className="tg-hien__v">{it.v}</span>
        </div>
      ))}
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

  // --- Header phiếu đã lưu ---
  const [ma, setMa] = useState("");
  const [ktv, setKtv] = useState<string | null>(null);
  const [ngay, setNgay] = useState<string | null>(null);
  const [tongGiaVon, setTongGiaVon] = useState<number | null>(null);

  // --- Form ---
  const [loaiSPId, setLoaiSPId] = useState<number | "">("");
  const [tenAnPham, setTenAnPham] = useState("");
  const [khoThanhPham, setKhoThanhPham] = useState("");
  const [qty, setQty] = useState(0);
  const [comps, setComps] = useState<EditableComponent[]>([]);
  const [editingUid, setEditingUid] = useState<string | null>(null);

  // --- Kết quả ---
  const [result, setResult] = useState<TinhGiaPreviewOut | null>(null);
  const [warnList, setWarnList] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [calcing, setCalcing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const applyOut = useCallback((out: PhieuTinhGiaOut) => {
    setMa(out.ma);
    setKtv(out.ktv);
    setNgay(out.created_at ? out.created_at.slice(0, 10) : null);
    setTongGiaVon(out.tong_gia_von);
    setTenAnPham(out.ten_san_pham ?? "");
    setKhoThanhPham(out.kho_thanh_pham ?? "");
    setLoaiSPId(out.loai_san_pham_id ?? "");
    setQty(out.so_luong ?? 0);
    setComps((out.thanh_phans ?? []).map(fromComponent));
    setResult(out.result);
    setWarnList(out.result?.warnings ?? out.warnings ?? []);
  }, []);

  // Nạp 4 danh mục 1 lần.
  useEffect(() => {
    if (!token) return;
    loaiSanPham.list(token).then((r) => setLoaiSPs(r.items)).catch(() => setLoaiSPs([]));
    giay.list(token).then((r) => setGiays(r.items)).catch(() => setGiays([]));
    mayThietBi.list(token).then((r) => setMays(r.items)).catch(() => setMays([]));
    congDoan.list(token).then((r) => setCongDoans(r.items)).catch(() => setCongDoans([]));
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
        if (alive) applyOut(out);
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
  }, [token, id, applyOut]);

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
            const fins = routing
              .map((cid) => congDoans.find((cd) => cd.id === cid))
              .filter((cd): cd is Row => !!cd && String(cd.nhom) === "finishing")
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

  // Chọn giấy → khổ nguyên ① (nhãn) + đơn giá + đơn vị; nếu khổ in ② còn trống thì lấy khổ giấy
  // (in thẳng, không xả) để bình bài có số ngay.
  const onPickGiay = useCallback(
    (uid: string, gid: number | null) => {
      setComps((cs) =>
        cs.map((c) => {
          if (c.uid !== uid) return c;
          if (gid === null) return { ...c, giay_id: null };
          const g = giays.find((x) => x.id === gid);
          if (!g) return { ...c, giay_id: gid };
          const kd = numOf(g.kho_dai);
          const kr = numOf(g.kho_rong);
          const patch: Partial<EditableComponent> = {
            giay_id: gid,
            kho_nguyen: kd && kr ? `${kr}×${kd}` : c.kho_nguyen,
          };
          if (c.don_gia_giay === 0 && typeof g.don_gia === "number") patch.don_gia_giay = g.don_gia;
          if (g.don_vi_gia === "tan") patch.don_gia_don_vi = "tan";
          if (!c.kho_in_dai && kd) patch.kho_in_dai = kd;
          if (!c.kho_in_rong && kr) patch.kho_in_rong = kr;
          return { ...c, ...patch };
        }),
      );
    },
    [giays],
  );

  // Chọn máy → khổ tờ in ② (kho_max) + gợi ý chừa nhíp (gripper). Giữ con_auto để bình bài lại.
  const onPickMay = useCallback(
    (uid: string, mid: number | null) => {
      setComps((cs) =>
        cs.map((c) => {
          if (c.uid !== uid) return c;
          if (mid === null) return { ...c, may_id: null };
          const m = mays.find((x) => x.id === mid);
          if (!m) return { ...c, may_id: mid };
          const patch: Partial<EditableComponent> = { may_id: mid, con_auto: true };
          const kd = numOf(m.kho_max_dai);
          const kr = numOf(m.kho_max_rong);
          if (kd) patch.kho_in_dai = kd;
          if (kr) patch.kho_in_rong = kr;
          const grip = numOf(m.gripper_mm);
          if (grip && c.chua_nhip === 0) patch.chua_nhip = grip; // gripper_mm đã là mm (thống nhất mm)
          return { ...c, ...patch };
        }),
      );
    },
    [mays],
  );

  const patchFin = useCallback(
    (cuid: string, fuid: string, patch: Partial<EditableFinishing>) => {
      setComps((cs) =>
        cs.map((c) =>
          c.uid === cuid
            ? { ...c, thanh_phams: c.thanh_phams.map((f) => (f.uid === fuid ? { ...f, ...patch } : f)) }
            : c,
        ),
      );
    },
    [],
  );
  const addFin = useCallback((cuid: string) => {
    setComps((cs) =>
      cs.map((c) => (c.uid === cuid ? { ...c, thanh_phams: [...c.thanh_phams, blankFinishing()] } : c)),
    );
  }, []);
  const removeFin = useCallback((cuid: string, fuid: string) => {
    setComps((cs) =>
      cs.map((c) =>
        c.uid === cuid ? { ...c, thanh_phams: c.thanh_phams.filter((f) => f.uid !== fuid) } : c,
      ),
    );
  }, []);

  // Backfill khổ tờ in ② từ GIẤY cho SP đã lưu (có giay_id nhưng kho_in=0) → in thẳng khổ giấy,
  // bình bài + sơ đồ chạy ngay khi mở phiếu, không bắt chọn lại giấy/máy.
  useEffect(() => {
    if (giays.length === 0) return;
    setComps((cs) => {
      let changed = false;
      const next = cs.map((c) => {
        if (!c.giay_id || (c.kho_in_dai && c.kho_in_rong)) return c;
        const g = giays.find((x) => x.id === c.giay_id);
        if (!g) return c;
        const kd = numOf(g.kho_dai);
        const kr = numOf(g.kho_rong);
        if (!kd || !kr) return c;
        changed = true;
        return {
          ...c,
          kho_in_dai: c.kho_in_dai || kd,
          kho_in_rong: c.kho_in_rong || kr,
          kho_nguyen: c.kho_nguyen || `${kr}×${kd}`,
        };
      });
      return changed ? next : cs;
    });
  }, [giays, comps.length]);

  // ---- Bình bài LIVE: gọi /binh-bai (debounce) → đổ so_con cho thành phần con_auto ----
  // Chữ ký loại trừ so_con để patch kết quả KHÔNG tự kích lại (tránh vòng lặp).
  const binhBaiSig = useMemo(
    () =>
      JSON.stringify(
        comps.map((c) => ({
          u: c.uid,
          a: c.con_auto,
          kd: c.kho_in_dai,
          kr: c.kho_in_rong,
          d: c.dai_thanh_pham,
          r: c.rong_thanh_pham,
          ch: c.chua_xen + c.chua_tay_ke + c.chua_nhip + c.chua_duoi + c.chua_ca_gay,
        })),
      ),
    [comps],
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
      ch: number;
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
            chua_mm: x.ch,
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

  // "Tính giá" = LƯU + TÍNH LẠI (BE) → refresh từ Out.
  const calc = useCallback(() => {
    if (!token) return;
    setCalcing(true);
    setErr(null);
    api.phieuTinhGia
      .update(token, id, {
        ten_san_pham: tenAnPham,
        kho_thanh_pham: khoThanhPham.trim() || null,
        loai_san_pham_id: loaiSPId === "" ? null : loaiSPId,
        so_luong: qty,
        thanh_phans: comps.map(toThanhPhanIn),
      })
      .then(applyOut)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tính được giá. Thử lại."))
      .finally(() => setCalcing(false));
  }, [token, id, tenAnPham, khoThanhPham, loaiSPId, qty, comps, applyOut]);

  // BG-3: từ phiếu tính giá → mở báo giá (1 PTG → 1 BG). Chưa có → tạo. ĐÃ CÓ → ĐỒNG BỘ số mới
  // của PTG sang báo giá (Phương án A): nháp cập nhật tại chỗ, đã chốt tạo phiên bản mới; rồi mở.
  async function openOrCreateQuote() {
    if (!token || !navigate) return;
    setQuoting(true);
    setErr(null);
    try {
      const existing = await api.quotations.byPhieu(token, id);
      let quoteId = existing.quote_id;
      if (quoteId == null) {
        const q = await api.quotations.create(token, {
          phieu_tinh_gia_id: id, customer_id: null, valid_until: null,
          payment_terms: null, delivery_terms: null, delivery_address: null,
          customer_note: null, internal_note: null,
        });
        quoteId = q.id;
      } else {
        // Đã có báo giá → kéo giá vốn/SL mới nhất từ PTG sang trước khi mở (nháp: tại chỗ; đã
        // chốt: phiên bản mới). Trang Báo giá hiển thị số mới + badge phiên bản là tín hiệu.
        const r = await api.quotations.resyncFromPhieu(token, id);
        quoteId = r.quote_id;
      }
      navigate("bao-gia", { openQuoteId: quoteId });
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

  const phieu = useMemo(
    () => (result ? toPhieu(result, ma || "(chưa lưu)", tenAnPham, qty, khoThanhPham) : null),
    [result, ma, tenAnPham, qty, khoThanhPham],
  );

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
      ...result.groups.map((g) => ({ label: `Nhóm ${g.idx} · ${g.name}`, value: `${fmt(g.subtotal)} đ` })),
      { label: "Tổng giá vốn", value: `${fmt(result.grand_total)} đ`, total: true },
    ];
  }, [result]);

  const summaryNote: ReactNode = (
    <>
      <LockIcon />
      <span>
        Giá vốn nội bộ, chưa cộng lợi nhuận. Markup &amp; giá bán ở module <b>Báo giá</b>.
      </span>
    </>
  );

  const editing = comps.find((c) => c.uid === editingUid) ?? null;
  const editingIdx = editing ? comps.findIndex((c) => c.uid === editingUid) : -1;

  return (
    <main className="tg-page">
      {/* ---------- HEAD ---------- */}
      <header className="tg-head">
        <div className="tg-head__lead">
          <button type="button" className="tg-back" onClick={onBack}>
            <BackIcon /> Danh sách
          </button>
          <div className="tg-head__titlerow">
            <h1 className="tg-head__title">{ma || "Phiếu tính giá"}</h1>
          </div>
          <p className="tg-head__sub">
            <span className="tg-mono">{ma || "—"}</span> · {tenAnPham || "—"}
          </p>
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
            {/* --- Card: Thông tin ấn phẩm --- */}
            <section className="canvas tg-card">
              <div className="tg-card__head">
                <h2 className="tg-card__title">Thông tin ấn phẩm</h2>
              </div>
              <div className="tg-card__body">
                <div className="tg-grid">
                  <label className="tg-field tg-field--full">
                    <span className="tg-microlabel">
                      Tên phiếu / khách <span className="tg-microlabel__opt">hiển thị trên phiếu</span>
                    </span>
                    <input
                      className="tg-input"
                      type="text"
                      value={tenAnPham}
                      placeholder="Tên phiếu hoặc tên khách hàng"
                      onChange={(e) => setTenAnPham(e.target.value)}
                    />
                  </label>
                  <NumField
                    label="SL mặc định"
                    opt="cho SP chưa nhập SL"
                    value={qty}
                    onChange={setQty}
                  />
                </div>
              </div>
            </section>

            {/* --- Card: DANH SÁCH SẢN PHẨM (list + drawer) --- */}
            <section className="canvas tg-card">
              <div className="tg-card__head">
                <h2 className="tg-card__title">Sản phẩm trong phiếu</h2>
                <span className="tg-pill">{comps.length} sản phẩm</span>
              </div>
              <div className="tg-complist">
                {comps.length === 0 ? (
                  <div className="tg-empty tg-empty--sm">
                    <p className="tg-empty__title">Chưa có sản phẩm</p>
                    <p className="tg-empty__sub">
                      Bấm “Thêm sản phẩm”, rồi chọn loại sản phẩm trong drawer để tự bung cấu hình.
                    </p>
                  </div>
                ) : (
                  <div className="tg-complist__wrap">
                    <table className="rc__table tg-complist__tbl">
                      <thead>
                        <tr>
                          <th style={{ width: "48px" }}>#</th>
                          <th>Tên</th>
                          <th>Loại</th>
                          <th className="tg-num">SL</th>
                          <th className="tg-num">Khổ ③ D×R</th>
                          <th className="tg-num">Giá vốn</th>
                          <th className="tg-num">Đơn giá</th>
                          <th className="rc__actcol" style={{ width: "148px" }}>
                            Hành động
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {comps.map((c, i) => {
                          const meta = metaByIdx.get(i);
                          const sl = meta ? meta.so_luong : c.so_luong || qty;
                          const thieu =
                            !c.giay_id || c.dai_thanh_pham <= 0 || c.rong_thanh_pham <= 0;
                          return (
                            <tr key={c.uid} className="rc__row" onClick={() => setEditingUid(c.uid)}>
                              <td className="rc__nowrap">
                                <span className="rc__code-badge">{i + 1}</span>
                              </td>
                              <td className="rc__name">
                                <span className="tg-complist__ten">{c.ten || "(chưa đặt tên)"}</span>
                                {thieu && (
                                  <span
                                    className="tg-warn-chip"
                                    title="Chưa đủ khổ thành phẩm ③ hoặc chưa chọn giấy — số con/giá vốn chưa chính xác."
                                  >
                                    <WarnIcon /> thiếu khổ/giấy
                                  </span>
                                )}
                              </td>
                              <td>
                                <span className="tg-complist__loai">{loaiLabelOf(c)}</span>
                              </td>
                              <td className="tg-num tg-mono">{sl > 0 ? fmt(sl) : "—"}</td>
                              <td className="tg-num rc__nowrap">
                                {c.dai_thanh_pham > 0 && c.rong_thanh_pham > 0
                                  ? `${fmt(c.dai_thanh_pham)}×${fmt(c.rong_thanh_pham)}`
                                  : "—"}
                              </td>
                              <td className="tg-num">
                                {c.gia_von_tp > 0 ? `${fmt(c.gia_von_tp)} đ` : "—"}
                              </td>
                              <td className="tg-num">
                                {meta && meta.gia_von_don > 0 ? `${fmt(meta.gia_von_don)} đ` : "—"}
                              </td>
                              <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                                <button
                                  type="button"
                                  className="rc__link-btn"
                                  onClick={() => setEditingUid(c.uid)}
                                  title="Sửa sản phẩm"
                                >
                                  <EditIcon />
                                  <span>Sửa</span>
                                </button>
                                <button
                                  type="button"
                                  className="rc__link-btn rc__link-btn--danger"
                                  onClick={() => removeComp(c.uid)}
                                  title="Xóa sản phẩm"
                                >
                                  <TrashIcon />
                                  <span>Xóa</span>
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
                <button type="button" className="tg-add tg-complist__add" onClick={addComp}>
                  <PlusIcon /> Thêm sản phẩm
                </button>
              </div>
            </section>

            {/* --- Chi tiết dòng giá vốn (gọn — panel phải đã hiện 4 nhóm) --- */}
            {result ? (
              <details className="canvas tg-card tg-costdetails">
                <summary className="tg-costdetails__sum">
                  <span className="tg-card__title">Chi tiết dòng giá vốn (A · B · C · D)</span>
                  <ChevronIcon open={false} />
                </summary>
                <div className="tg-cost">
                  {result.groups.map((g) => (
                    <div className="tg-cost__grp" key={g.idx}>
                      <div className="tg-cost__grphead">
                        <span className="tg-cost__idx">{g.idx}</span>
                        {g.name}
                      </div>
                      <div className="tg-cost__scroll">
                        <table className="tg-cost__tbl">
                          <thead>
                            <tr>
                              {g.columns.map((col) => (
                                <th key={col.key} className={headClass(col) || undefined}>
                                  {col.label}
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
                                  {g.columns.map((col) => (
                                    <td key={col.key} className={cellClass(col) || undefined}>
                                      {cellValue(r[col.key])}
                                    </td>
                                  ))}
                                </tr>
                              ))
                            )}
                            <tr className="tg-cost__sub">
                              <td colSpan={g.columns.length}>
                                <div className="tg-cost__subrow">
                                  <span>Cộng nhóm {g.idx}</span>
                                  <span className="tg-num">{fmt(g.subtotal)} đ</span>
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
                </div>
              </details>
            ) : (
              <section className="canvas tg-card">
                <div className="tg-empty">
                  <CalcIcon />
                  <p className="tg-empty__title">Chưa có kết quả</p>
                  <p className="tg-empty__sub">
                    Cấu hình sản phẩm rồi bấm <b>Tính giá</b> để xem bảng 4 nhóm (Giấy · Công in ·
                    Chế bản · Gia công).
                  </p>
                </div>
              </section>
            )}
          </div>

          {/* ============ RIGHT (sticky) ============ */}
          <aside className="tg-side">
            <DarkSummaryPanel
              label="Tổng giá vốn (nội bộ)"
              amount={grand == null ? null : fmt(grand)}
              unit="đ"
              sub={perPiece == null ? undefined : `≈ ${fmt(perPiece)} đ · đơn giá bình quân`}
              note={summaryNote}
              rows={summaryRows}
            />

            <section className="canvas tg-info">
              <div className="tg-info__title">Phiếu này</div>
              <dl className="tg-info__list">
                <div className="tg-info__row">
                  <dt>Mã phiếu</dt>
                  <dd className="tg-mono">{ma || "—"}</dd>
                </div>
                <div className="tg-info__row">
                  <dt>KTV</dt>
                  <dd>{ktv ?? "—"}</dd>
                </div>
                <div className="tg-info__row">
                  <dt>Ngày lập</dt>
                  <dd>{ngay ? new Date(ngay).toLocaleDateString("vi-VN") : "—"}</dd>
                </div>
                <div className="tg-info__row">
                  <dt>Giá vốn tổng</dt>
                  <dd className="tg-num">{tongGiaVon == null ? "—" : `${fmt(tongGiaVon)} đ`}</dd>
                </div>
                <div className="tg-info__row">
                  <dt>Số sản phẩm</dt>
                  <dd className="tg-num">{fmt(comps.length)}</dd>
                </div>
                {tongSoLuong > 0 ? (
                  <div className="tg-info__row">
                    <dt>Tổng SL</dt>
                    <dd className="tg-num">{fmt(tongSoLuong)}</dd>
                  </div>
                ) : null}
              </dl>
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

      {/* ---------- DRAWER: sửa 1 thành phần ---------- */}
      {editing ? (
        <ComponentDrawer
          comp={editing}
          idx={editingIdx}
          meta={metaByIdx.get(editingIdx)}
          loaiSPs={loaiSPs}
          giays={giays}
          mays={mays}
          congDoans={congDoans}
          onClose={() => setEditingUid(null)}
          onRemove={() => {
            removeComp(editing.uid);
            setEditingUid(null);
          }}
          patchComp={patchComp}
          onPickLoaiSP={onPickLoaiSPForComp}
          onPickGiay={onPickGiay}
          onPickMay={onPickMay}
          patchFin={patchFin}
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
    </main>
  );
}

// ================= DRAWER: sửa 1 thành phần (bám .rc-drawer*) =================
function ComponentDrawer({
  comp: c,
  idx,
  meta,
  loaiSPs,
  giays,
  mays,
  congDoans,
  onClose,
  onRemove,
  patchComp,
  onPickLoaiSP,
  onPickGiay,
  onPickMay,
  patchFin,
  addFin,
  removeFin,
}: {
  comp: EditableComponent;
  idx: number;
  meta: TinhGiaComponentMeta | undefined;
  loaiSPs: Row[];
  giays: Row[];
  mays: Row[];
  congDoans: Row[];
  onClose: () => void;
  onRemove: () => void;
  patchComp: (uid: string, patch: Partial<EditableComponent>) => void;
  onPickLoaiSP: (uid: string, pid: number | "") => void;
  onPickGiay: (uid: string, gid: number | null) => void;
  onPickMay: (uid: string, mid: number | null) => void;
  patchFin: (cuid: string, fuid: string, patch: Partial<EditableFinishing>) => void;
  addFin: (cuid: string) => void;
  removeFin: (cuid: string, fuid: string) => void;
}) {
  const isToRoi = c.loai_thanh_phan === "to_roi";
  const chuaTong = c.chua_xen + c.chua_tay_ke + c.chua_nhip + c.chua_duoi + c.chua_ca_gay;
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
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer rc-drawer--wide" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">Sản phẩm {idx + 1}</div>
            <h2 className="rc-drawer__title">{c.ten || loaiTpLabel(c.loai_thanh_phan)}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <CloseIcon />
          </button>
        </header>

        <div className="rc-drawer__body">
          {/* ---- SẢN PHẨM & KHỔ ③ ---- */}
          <section className="rc-sec">
            <div className="rc-sec__title">Sản phẩm &amp; khổ thành phẩm ③</div>
            <div className="tg-grid">
              <label className="tg-field">
                <span className="tg-microlabel">Tên sản phẩm</span>
                <input
                  className="tg-input"
                  type="text"
                  value={c.ten}
                  placeholder="VD Thân hộp / Ruột / Bìa"
                  onChange={(e) => patchComp(c.uid, { ten: e.target.value })}
                />
              </label>
              <NumField
                label="Số lượng"
                opt="0 = SL mặc định phiếu"
                value={c.so_luong}
                step="1"
                onChange={(n) => patchComp(c.uid, { so_luong: Math.max(0, n) })}
              />
              <label className="tg-field">
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
              <label className="tg-field">
                <span className="tg-microlabel">Kiểu cấu trúc</span>
                <select
                  className="tg-input"
                  value={c.loai_thanh_phan}
                  onChange={(e) => patchComp(c.uid, { loai_thanh_phan: e.target.value })}
                >
                  <option value="to_roi">Tờ rời</option>
                  <option value="than">Thân</option>
                  <option value="nap">Nắp</option>
                  <option value="bia">Bìa</option>
                  <option value="ruot">Ruột</option>
                  <option value="phu_kien">Phụ kiện</option>
                </select>
              </label>
              <NumField
                label="Dài thành phẩm ③"
                value={c.dai_thanh_pham}
                onChange={(n) => patchComp(c.uid, { dai_thanh_pham: n })}
                suffix="mm"
              />
              <NumField
                label="Rộng thành phẩm ③"
                value={c.rong_thanh_pham}
                onChange={(n) => patchComp(c.uid, { rong_thanh_pham: n })}
                suffix="mm"
              />
              {!isToRoi && (
                <>
                  <label className="tg-field">
                    <span className="tg-microlabel">Tay gấp</span>
                    <input
                      className="tg-input"
                      type="text"
                      value={c.tay_gap}
                      placeholder="VD gấp đôi / gấp ba"
                      onChange={(e) => patchComp(c.uid, { tay_gap: e.target.value })}
                    />
                  </label>
                  <NumField
                    label="Số tờ / SP"
                    value={c.so_to_per_sp}
                    min={1}
                    step="1"
                    onChange={(n) => patchComp(c.uid, { so_to_per_sp: Math.max(1, n) })}
                  />
                </>
              )}
            </div>
          </section>

          {/* ---- GIẤY IN ① ---- */}
          <section className="rc-sec">
            <div className="rc-sec__title">Giấy in ①</div>
            <div className="tg-grid">
              <label className="tg-field">
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
              <label className="tg-field">
                <span className="tg-microlabel">
                  Khổ nguyên ① <span className="tg-microlabel__opt">rộng×dài</span>
                </span>
                <input
                  className="tg-input"
                  type="text"
                  value={c.kho_nguyen}
                  placeholder="VD 790×1090"
                  onChange={(e) => patchComp(c.uid, { kho_nguyen: e.target.value })}
                />
              </label>
              <NumField
                label="Đơn giá giấy"
                value={c.don_gia_giay}
                onChange={(n) => patchComp(c.uid, { don_gia_giay: n })}
              />
              <div className="tg-field">
                <span className="tg-microlabel">Đơn vị giá</span>
                <Seg
                  ariaLabel="Đơn vị giá giấy"
                  value={c.don_gia_don_vi}
                  onChange={(v) => patchComp(c.uid, { don_gia_don_vi: v })}
                  options={[
                    { val: "to", label: "Tờ" },
                    { val: "tan", label: "Tấn" },
                  ]}
                />
              </div>
              <div className="tg-field tg-field--full">
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
                {c.nguon_giay === "khach" && (
                  <span className="tg-hint">Khách cấp giấy — không tính tiền giấy.</span>
                )}
              </div>
              <NumField
                label="Bù hao (số tờ in)"
                opt="cộng thêm"
                value={c.bu_hao_so_to}
                step="1"
                onChange={(n) => patchComp(c.uid, { bu_hao_so_to: n })}
              />
            </div>

            <details className="tg-collapse">
              <summary className="tg-collapse__sum">
                Chừa giấy — xén · tay kê · nhíp · đuôi · cà gáy (mm)
              </summary>
              <div className="tg-chua">
                {(
                  [
                    ["chua_xen", "Xén"],
                    ["chua_tay_ke", "Tay kê"],
                    ["chua_nhip", "Nhíp"],
                    ["chua_duoi", "Đuôi"],
                    ["chua_ca_gay", "Cà gáy"],
                  ] as const
                ).map(([key, lbl]) => (
                  <NumField
                    key={key}
                    label={lbl}
                    step="1"
                    value={c[key]}
                    onChange={(n) => patchComp(c.uid, { [key]: n })}
                  />
                ))}
              </div>
            </details>
          </section>

          {/* ---- KỸ THUẬT IN ② + SƠ ĐỒ BÌNH BÀI ---- */}
          <section className="rc-sec">
            <div className="rc-sec__title">Kỹ thuật in ②</div>
            <div className="tg-grid">
              <label className="tg-field">
                <span className="tg-microlabel">
                  Máy in <span className="tg-microlabel__opt">→ khổ tờ in</span>
                </span>
                <select
                  className="tg-input"
                  value={c.may_id ?? ""}
                  onChange={(e) => onPickMay(c.uid, e.target.value === "" ? null : Number(e.target.value))}
                >
                  <option value="">— Không chọn —</option>
                  {mays.map((m) => (
                    <option key={m.id} value={m.id}>
                      {rowLabel(m)}
                    </option>
                  ))}
                </select>
              </label>
              <div className="tg-field">
                <span className="tg-microlabel">Có in?</span>
                <button
                  type="button"
                  aria-pressed={c.co_in}
                  className={`tg-toggle${c.co_in ? " tg-toggle--on" : ""}`}
                  onClick={() => patchComp(c.uid, { co_in: !c.co_in })}
                >
                  {c.co_in ? "Có in" : "Không in"}
                </button>
              </div>
              <NumField
                label="Khổ tờ in ② dài"
                value={c.kho_in_dai}
                onChange={(n) => patchComp(c.uid, { kho_in_dai: n })}
                suffix="mm"
              />
              <NumField
                label="Khổ tờ in ② rộng"
                value={c.kho_in_rong}
                onChange={(n) => patchComp(c.uid, { kho_in_rong: n })}
                suffix="mm"
              />
              <div className="tg-field tg-field--full">
                <span className="tg-microlabel">Quy cách in</span>
                <Seg
                  ariaLabel="Quy cách in"
                  value={c.quy_cach_in}
                  onChange={(v) => patchComp(c.uid, { quy_cach_in: v })}
                  options={[
                    { val: "mot_mat", label: "1 mặt" },
                    { val: "hai_mat", label: "2 mặt" },
                    { val: "tu_tro", label: "Tự trở" },
                  ]}
                />
              </div>
              {/* Số con ④ — auto bình bài, sửa đè được */}
              <div className="tg-field">
                <span className="tg-microlabel">
                  Số con ④
                  {c.con_auto ? (
                    canBinhBai ? (
                      <span className="tg-tag tg-tag--auto">
                        <AutoIcon /> tự bình bài
                      </span>
                    ) : (
                      <span className="tg-tag tg-tag--todo">nhập khổ ③ + chọn giấy/máy để tự tính</span>
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
              </div>
              <label className="tg-field">
                <span className="tg-microlabel">Chế bản (loại)</span>
                <input
                  className="tg-input"
                  type="text"
                  value={c.che_ban_loai}
                  placeholder="VD CTP ghi kẽm"
                  onChange={(e) => patchComp(c.uid, { che_ban_loai: e.target.value })}
                />
              </label>
              <NumField
                label="Chế bản (đơn giá / kẽm)"
                value={c.che_ban_don_gia}
                onChange={(n) => patchComp(c.uid, { che_ban_don_gia: n })}
              />
              <NumField
                label="Đơn giá công in"
                opt="mực gộp / 1000 lượt"
                value={c.don_gia_cong_in}
                onChange={(n) => patchComp(c.uid, { don_gia_cong_in: n })}
              />
            </div>

            {/* SƠ ĐỒ BÌNH BÀI LIVE */}
            <div className="tg-field tg-field--full tg-imp-wrap">
              <span className="tg-microlabel">
                Sơ đồ bình bài <span className="tg-microlabel__opt">tờ in ② → con ③, khớp engine</span>
              </span>
              <ImpositionDiagram
                khoInDai={c.kho_in_dai}
                khoInRong={c.kho_in_rong}
                daiTP={c.dai_thanh_pham}
                rongTP={c.rong_thanh_pham}
                chuaMm={chuaTong}
              />
            </div>
          </section>

          {/* ---- MÀU IN ---- */}
          <section className="rc-sec">
            <div className="rc-sec__title">Màu in</div>
            <div className="tg-grid">
              <NumField
                label="Số màu mặt A"
                value={c.so_mau_a}
                step="1"
                onChange={(n) => patchComp(c.uid, { so_mau_a: n })}
              />
              <NumField
                label="Số màu mặt B"
                opt={c.quy_cach_in === "hai_mat" ? undefined : "chỉ tính khi in 2 mặt"}
                value={c.so_mau_b}
                step="1"
                onChange={(n) => patchComp(c.uid, { so_mau_b: n })}
              />
            </div>
          </section>

          {/* ---- [Hiện] số liệu tự tính ---- */}
          <section className="rc-sec">
            <div className="rc-sec__title">Số liệu tự tính (read-only)</div>
            <HienStrip meta={meta} comp={c} />
          </section>

          {/* ---- GIA CÔNG SAU IN ---- */}
          <section className="rc-sec">
            <div className="rc-sec__title">Gia công sau in</div>
            <div className="tg-fin-scroll">
              <table className="tg-fin">
                <thead>
                  <tr>
                    <th className="tg-fin__cd">Công đoạn</th>
                    <th className="tg-num">Đơn giá</th>
                    <th className="tg-num">SL (trống=SL SP)</th>
                    <th className="tg-num">Số mặt</th>
                    <th className="tg-num">Số vị trí</th>
                    <th className="tg-num">Diện tích</th>
                    <th>NCC (thuê ngoài)</th>
                    <th>Ghi chú</th>
                    <th aria-label="Xóa" />
                  </tr>
                </thead>
                <tbody>
                  {c.thanh_phams.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="tg-fin__empty">
                        Chưa có công đoạn gia công.
                      </td>
                    </tr>
                  ) : (
                    c.thanh_phams.map((f) => (
                      <tr key={f.uid}>
                        <td className="tg-fin__cd">
                          <select
                            className="tg-input tg-input--sm"
                            aria-label="Công đoạn"
                            value={f.cong_doan_id ?? ""}
                            onChange={(e) => {
                              const cid = e.target.value === "" ? null : Number(e.target.value);
                              const cd = congDoans.find((x) => x.id === cid);
                              patchFin(c.uid, f.uid, {
                                cong_doan_id: cid,
                                ten: cd ? cdName(cd) : f.ten,
                              });
                            }}
                          >
                            <option value="">— Chọn / tự nhập —</option>
                            {congDoans.map((cd) => (
                              <option key={cd.id} value={cd.id}>
                                {cdName(cd)}
                              </option>
                            ))}
                          </select>
                          <input
                            className="tg-input tg-input--sm tg-fin__ten"
                            type="text"
                            aria-label="Tên công đoạn"
                            value={f.ten}
                            placeholder="Tên công đoạn"
                            onChange={(e) => patchFin(c.uid, f.uid, { ten: e.target.value })}
                          />
                        </td>
                        <td>
                          <input
                            className="tg-input tg-input--sm tg-input--num"
                            type="number"
                            min={0}
                            aria-label="Đơn giá"
                            value={f.don_gia}
                            onChange={(e) =>
                              patchFin(c.uid, f.uid, { don_gia: Math.max(0, Number(e.target.value)) })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="tg-input tg-input--sm tg-input--num"
                            type="number"
                            min={0}
                            aria-label="Số lượng"
                            value={f.so_luong}
                            onChange={(e) =>
                              patchFin(c.uid, f.uid, { so_luong: Math.max(0, Number(e.target.value)) })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="tg-input tg-input--sm tg-input--num"
                            type="number"
                            min={0}
                            aria-label="Số mặt"
                            value={f.so_mat}
                            onChange={(e) =>
                              patchFin(c.uid, f.uid, { so_mat: Math.max(0, Number(e.target.value)) })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="tg-input tg-input--sm tg-input--num"
                            type="number"
                            min={0}
                            aria-label="Số vị trí"
                            value={f.so_vi_tri}
                            onChange={(e) =>
                              patchFin(c.uid, f.uid, { so_vi_tri: Math.max(0, Number(e.target.value)) })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="tg-input tg-input--sm tg-input--num"
                            type="number"
                            min={0}
                            step="0.01"
                            aria-label="Diện tích"
                            value={f.dien_tich}
                            onChange={(e) =>
                              patchFin(c.uid, f.uid, { dien_tich: Math.max(0, Number(e.target.value)) })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="tg-input tg-input--sm"
                            type="text"
                            aria-label="Nhà cung cấp"
                            value={f.nha_cung_cap}
                            placeholder="NCC"
                            onChange={(e) => patchFin(c.uid, f.uid, { nha_cung_cap: e.target.value })}
                          />
                        </td>
                        <td>
                          <input
                            className="tg-input tg-input--sm"
                            type="text"
                            aria-label="Ghi chú"
                            value={f.ghi_chu}
                            placeholder="Ghi chú"
                            onChange={(e) => patchFin(c.uid, f.uid, { ghi_chu: e.target.value })}
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="tg-icon-btn tg-icon-btn--danger"
                            aria-label="Xóa công đoạn"
                            title="Xóa công đoạn"
                            onClick={() => removeFin(c.uid, f.uid)}
                          >
                            <TrashIcon />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <button type="button" className="tg-add tg-add--sm" onClick={() => addFin(c.uid)}>
              <PlusIcon /> Thêm công đoạn
            </button>
          </section>
        </div>

        <footer className="rc-drawer__foot">
          <Button type="button" variant="ghost" onClick={onRemove}>
            Xóa sản phẩm
          </Button>
          <Button type="button" variant="primary" onClick={onClose}>
            Xong
          </Button>
        </footer>
      </aside>
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

const EditIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
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
