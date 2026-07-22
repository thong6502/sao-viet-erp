// Drawer chi tiết ẤN PHẨM (dùng chung List "Chờ lên kế hoạch" + Detail lệnh).
// Right slide-in ≤560px (KHÔNG modal 1200px). Tự fetch anPhamChiTiet — backend đã LỌC
// mọi trường giá (cô lập thương mại); ở đây chỉ trình bày quy cách kỹ thuật theo phiếu
// công đoạn (sản phẩm · giấy · in & màu · số lượng · vật tư · routing gốc).
//
// Chế độ SỬA (§13.2): mở từ LỆNH NHÁP (có lenhItemId → backend trả editable=true) thì các
// section quy cách render INPUT — kế thừa báo giá làm mặc định NHƯNG cho OVERRIDE per bài con.
// Mở từ sổ chờ / lệnh đã phát → READ-ONLY như cũ. Override lưu riêng ở bài con (backend lo),
// FE chỉ gửi field ĐỔI. Số kẽm backend tự tính lại theo giá trị hiệu lực (không tự tính ở FE).
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, type AnPhamChiTiet, type QuyCachOverride } from "../api/client";
import { giay as giayCatalog, type Row } from "../api/rebuildCatalog";
import { Select, type SelectOption } from "../components/Select";
import { ToastStack, useToasts } from "./LsxToast";
import "./lenh-san-xuat.css";

// nguon_giay → nhãn người đọc (record-only, không suy diễn thêm).
const NGUON_GIAY: Record<string, string> = {
  cong_ty: "Công ty",
  khach: "Khách",
  khach_hang: "Khách",
};
// quy_cach_in → nhãn mặt in.
const QUY_CACH_IN: Record<string, string> = {
  mot_mat: "1 mặt",
  hai_mat: "AB",
  tu_tro: "tự trở",
  tro_nhip: "trở nhíp",
};
// loai_thanh_phan → nhãn người đọc (fallback giữ giá trị thô nếu chưa map).
const LOAI_THANH_PHAN: Record<string, string> = {
  to_roi: "Tờ rời",
  ruot: "Ruột",
  bia: "Bìa",
  dong_cuon: "Đóng cuốn",
  hop: "Hộp",
};

type SpecItem = { k: string; v: string; sans?: boolean };

function fmt(n: number | null | undefined): string {
  return typeof n === "number" && !isNaN(n) ? n.toLocaleString("vi-VN") : "—";
}
function has(s: string | null | undefined): s is string {
  return typeof s === "string" && s.trim().length > 0;
}

// ---- Chế độ SỬA quy cách (lệnh nháp) ----
// Select cố định cho nguồn giấy / cách in (giá trị = enum backend).
const NGUON_OPTS: SelectOption<string>[] = [
  { value: "cong_ty", label: "Công ty" },
  { value: "khach", label: "Khách" },
];
const QCIN_OPTS: SelectOption<string>[] = [
  { value: "mot_mat", label: "1 mặt" },
  { value: "hai_mat", label: "AB" },
  { value: "tu_tro", label: "tự trở" },
  { value: "tro_nhip", label: "trở nhíp" },
];

// 1 giấy trong danh mục (đủ để chọn override + lọc cùng chủng loại).
interface GiayCat {
  id: number;
  ma: string;
  ten: string;
  gsm: number | null;
  chung_loai_giay_id: number | null;
}
function mapGiay(x: Row): GiayCat {
  return {
    id: x.id,
    ma: x.ma,
    ten: x.ten,
    gsm: x.gsm != null ? Number(x.gsm) : null,
    chung_loai_giay_id: x.chung_loai_giay_id != null ? Number(x.chung_loai_giay_id) : null,
  };
}

// Draft cục bộ = giá trị HIỆU LỰC hiện tại của các field quy cách (khởi tạo từ data).
interface QuyCachDraft {
  giay_id: number | null;
  dai_thanh_pham: number;
  rong_thanh_pham: number;
  kho_thanh_pham: string;
  kho_mo_rong: string;
  tay_gap: string;
  so_to_per_sp: number;
  kho_nguyen_dai: number;
  kho_nguyen_rong: number;
  nguon_giay: string;
  quy_cach_in: string;
  kho_in_dai: number;
  kho_in_rong: number;
  so_con: number;
  con_auto: boolean;
  che_ban_loai: string;
  so_mau_a: number;
  so_mau_b: number;
}
function draftFrom(d: AnPhamChiTiet): QuyCachDraft {
  return {
    giay_id: d.giay_id,
    dai_thanh_pham: d.dai_thanh_pham,
    rong_thanh_pham: d.rong_thanh_pham,
    kho_thanh_pham: d.kho_thanh_pham ?? "",
    kho_mo_rong: d.kho_mo_rong ?? "",
    tay_gap: d.tay_gap ?? "",
    so_to_per_sp: d.so_to_per_sp,
    kho_nguyen_dai: d.kho_nguyen_dai,
    kho_nguyen_rong: d.kho_nguyen_rong,
    nguon_giay: d.nguon_giay,
    quy_cach_in: d.quy_cach_in,
    kho_in_dai: d.kho_in_dai,
    kho_in_rong: d.kho_in_rong,
    so_con: d.so_con,
    con_auto: d.con_auto,
    che_ban_loai: d.che_ban_loai ?? "",
    so_mau_a: d.so_mau_a,
    so_mau_b: d.so_mau_b,
  };
}
// Text override: rỗng → null (gỡ override, kế thừa lại báo giá).
function normText(s: string): string | null {
  const t = s.trim();
  return t === "" ? null : t;
}
// Chỉ gom field ĐỔI so với giá trị hiệu lực (data) → payload PUT quy-cach.
function buildOverride(dr: QuyCachDraft, d: AnPhamChiTiet): QuyCachOverride {
  const o: QuyCachOverride = {};
  if (dr.giay_id !== d.giay_id) o.giay_id = dr.giay_id;
  if (dr.dai_thanh_pham !== d.dai_thanh_pham) o.dai_thanh_pham = dr.dai_thanh_pham;
  if (dr.rong_thanh_pham !== d.rong_thanh_pham) o.rong_thanh_pham = dr.rong_thanh_pham;
  if (normText(dr.kho_thanh_pham) !== (d.kho_thanh_pham ?? null)) o.kho_thanh_pham = normText(dr.kho_thanh_pham);
  if (normText(dr.kho_mo_rong) !== (d.kho_mo_rong ?? null)) o.kho_mo_rong = normText(dr.kho_mo_rong);
  if (normText(dr.tay_gap) !== (d.tay_gap ?? null)) o.tay_gap = normText(dr.tay_gap);
  if (dr.so_to_per_sp !== d.so_to_per_sp) o.so_to_per_sp = dr.so_to_per_sp;
  if (dr.kho_nguyen_dai !== d.kho_nguyen_dai) o.kho_nguyen_dai = dr.kho_nguyen_dai;
  if (dr.kho_nguyen_rong !== d.kho_nguyen_rong) o.kho_nguyen_rong = dr.kho_nguyen_rong;
  if (dr.nguon_giay !== d.nguon_giay) o.nguon_giay = dr.nguon_giay;
  if (dr.quy_cach_in !== d.quy_cach_in) o.quy_cach_in = dr.quy_cach_in;
  if (dr.kho_in_dai !== d.kho_in_dai) o.kho_in_dai = dr.kho_in_dai;
  if (dr.kho_in_rong !== d.kho_in_rong) o.kho_in_rong = dr.kho_in_rong;
  if (dr.so_con !== d.so_con) o.so_con = dr.so_con;
  if (dr.con_auto !== d.con_auto) o.con_auto = dr.con_auto;
  if (normText(dr.che_ban_loai) !== (d.che_ban_loai ?? null)) o.che_ban_loai = normText(dr.che_ban_loai);
  if (dr.so_mau_a !== d.so_mau_a) o.so_mau_a = dr.so_mau_a;
  if (dr.so_mau_b !== d.so_mau_b) o.so_mau_b = dr.so_mau_b;
  return o;
}

// ---- Nhóm quy cách theo phiếu công đoạn (bỏ item rỗng/0) ----
function specsSanPham(d: AnPhamChiTiet): SpecItem[] {
  const out: SpecItem[] = [];
  if (d.loai_thanh_phan)
    out.push({ k: "Loại", v: LOAI_THANH_PHAN[d.loai_thanh_phan] ?? d.loai_thanh_phan, sans: true });
  if (d.dai_thanh_pham > 0 || d.rong_thanh_pham > 0)
    out.push({ k: "Khổ TP", v: `${fmt(d.dai_thanh_pham)}×${fmt(d.rong_thanh_pham)}mm` });
  if (d.so_luong > 0)
    out.push({ k: "SL đặt", v: `${fmt(d.so_luong)} ${d.don_vi_tinh || ""}`.trim(), sans: true });
  if (has(d.kho_mo_rong)) out.push({ k: "Khổ mở rộng", v: d.kho_mo_rong, sans: true });
  return out;
}

function specsGiay(d: AnPhamChiTiet): SpecItem[] {
  const out: SpecItem[] = [];
  // Giấy = ưu tiên tên giấy; lùi chủng loại (+gsm); lùi nữa khổ nguyên (nhãn).
  let giay = "";
  let giayFromChungLoai = false;
  if (has(d.giay_ten)) {
    giay = d.giay_ten;
  } else if (has(d.chung_loai_ten)) {
    giay = d.gsm != null ? `${d.chung_loai_ten} ${fmt(d.gsm)}gsm` : d.chung_loai_ten;
    giayFromChungLoai = true;
  } else if (has(d.kho_nguyen)) {
    giay = d.kho_nguyen;
  }
  if (giay) out.push({ k: "Giấy", v: giay, sans: true });
  // Chủng loại — bỏ nếu đã gộp vào "Giấy" hoặc trùng tên giấy hoặc rỗng.
  if (has(d.chung_loai_ten) && !giayFromChungLoai && d.chung_loai_ten !== d.giay_ten)
    out.push({ k: "Chủng loại", v: d.chung_loai_ten, sans: true });
  // Định lượng — bỏ nếu đã gộp vào "Giấy" (tránh lặp gsm) hoặc null.
  if (d.gsm != null && !giayFromChungLoai) out.push({ k: "Định lượng", v: `${fmt(d.gsm)} gsm` });
  if (d.kho_nguyen_dai > 0 || d.kho_nguyen_rong > 0)
    out.push({ k: "Khổ nguyên", v: `${fmt(d.kho_nguyen_dai)}×${fmt(d.kho_nguyen_rong)}mm` });
  if (d.nguon_giay)
    out.push({ k: "Nguồn giấy", v: NGUON_GIAY[d.nguon_giay] ?? d.nguon_giay, sans: true });
  return out;
}

function specsIn(d: AnPhamChiTiet, mayName: (id: number | null) => string | null): SpecItem[] {
  const out: SpecItem[] = [];
  if (!d.co_in) {
    out.push({ k: "In", v: "Không in", sans: true });
    return out;
  }
  if (has(d.che_ban_loai)) out.push({ k: "Chế bản", v: d.che_ban_loai, sans: true });
  if (d.quy_cach_in)
    out.push({ k: "Cách in", v: QUY_CACH_IN[d.quy_cach_in] ?? d.quy_cach_in, sans: true });
  if (d.kho_in_dai > 0 || d.kho_in_rong > 0)
    out.push({ k: "Khổ tờ in", v: `${fmt(d.kho_in_dai)}×${fmt(d.kho_in_rong)}mm` });
  if (d.so_con > 0)
    out.push({
      k: "Số con/tờ",
      v: `${fmt(d.so_con)}${d.con_auto ? " (tự bình bài)" : ""}`,
      sans: d.con_auto,
    });
  if (d.so_mau_a > 0 || d.so_mau_b > 0) out.push({ k: "Số màu", v: `${d.so_mau_a} / ${d.so_mau_b}` });
  if (d.so_kem > 0) out.push({ k: "Số kẽm", v: fmt(d.so_kem) });
  const may = mayName(d.may_id);
  if (may) out.push({ k: "Máy", v: may, sans: true });
  return out;
}

// ---- Số lượng (engine snapshot) — danh sách dòng, nhấn số mono ----
type QtyRow = { k: string; v: number | null; strong?: boolean };
function qtyRows(d: AnPhamChiTiet): QtyRow[] {
  return [
    { k: "Cần in", v: d.so_luong_can },
    { k: "Bù hao tự", v: d.bu_hao_auto },
    { k: "Bù thêm", v: d.bu_hao_so_to },
    { k: "Tờ vào máy", v: d.so_to_thuc_te, strong: true },
    { k: "Hao", v: d.hao_so_to },
    { k: "Tờ sau in", v: d.so_to_sau_in },
    { k: "Tờ giấy nguyên", v: d.so_to_nguyen, strong: true },
    { k: "Con/tờ", v: d.con_tren_to },
  ].filter((r) => r.v != null);
}

function SpecGrid({ items }: { items: SpecItem[] }) {
  return (
    <div className="lsx-form__spec">
      {items.map((s, i) => (
        <div className="lsx-specitem" key={i}>
          <span className="lsx-specitem__k">{s.k}</span>
          <span className={`lsx-specitem__v${s.sans ? " sans" : ""}`}>{s.v}</span>
        </div>
      ))}
    </div>
  );
}

export function AnPhamDrawer({
  token,
  ptpId,
  lenhItemId,
  ctx,
  cdName,
  mayName,
  onClose,
  onSaved,
}: {
  token: string;
  ptpId: number;
  /** Kèm khi mở từ LỆNH: backend trả giá trị hiệu lực + editable (nháp) → sửa được quy cách. */
  lenhItemId?: number | null;
  ctx?: { orderNo?: string; khach?: string };
  cdName: (id: number | null) => string;
  mayName: (id: number | null) => string | null;
  onClose: () => void;
  /** Gọi sau khi lưu override thành công — cho phép màn lệnh reload panel/side. */
  onSaved?: () => void;
}) {
  const [data, setData] = useState<AnPhamChiTiet | null>(null);
  const [draft, setDraft] = useState<QuyCachDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [giayList, setGiayList] = useState<GiayCat[]>([]);
  const [sameChung, setSameChung] = useState(true); // lọc giấy "cùng chủng loại" (mặc định BẬT)
  const toasts = useToasts();

  // Fetch chi tiết ấn phẩm khi mở / đổi ptp / đổi bài con.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    setData(null);
    setDraft(null);
    api.lenhSanXuat
      .anPhamChiTiet(token, ptpId, lenhItemId)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setDraft(draftFrom(d));
      })
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : "Không tải được chi tiết ấn phẩm."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [token, ptpId, lenhItemId]);

  // Danh mục giấy (chỉ khi sửa được) — để chọn giấy override + lọc cùng chủng loại.
  useEffect(() => {
    if (!token || !data?.editable) return;
    let alive = true;
    giayCatalog
      .list(token)
      .then((r) => alive && setGiayList(r.items.map(mapGiay)))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [token, data?.editable]);

  // Chủng loại của giấy đang chọn (để lọc "cùng chủng loại").
  const curChung = useMemo(() => {
    if (!data || data.giay_id == null) return null;
    return giayList.find((g) => g.id === data.giay_id)?.chung_loai_giay_id ?? null;
  }, [data, giayList]);

  const giayOptions = useMemo<SelectOption<number | null>[]>(() => {
    let list = giayList;
    if (sameChung && curChung != null) {
      const keep = draft?.giay_id ?? null; // luôn giữ lựa chọn hiện tại kể cả khác chủng loại
      list = giayList.filter((g) => g.chung_loai_giay_id === curChung || g.id === keep);
    }
    return [
      { value: null, label: "— Chọn giấy —" },
      ...list.map((g) => ({ value: g.id, label: g.ten, hint: g.gsm != null ? `${g.gsm}gsm` : undefined })),
    ];
  }, [giayList, sameChung, curChung, draft?.giay_id]);

  // Payload field ĐỔI + cờ dirty (bật nút Lưu / Hoàn tác).
  const override = useMemo(() => (data && draft ? buildOverride(draft, data) : {}), [data, draft]);
  const dirty = Object.keys(override).length > 0;
  const ov = (name: string): boolean => !!data?.overridden?.includes(name);
  const upd = <K extends keyof QuyCachDraft>(k: K, v: QuyCachDraft[K]) =>
    setDraft((d) => (d ? { ...d, [k]: v } : d));

  function resetDraft() {
    if (data) setDraft(draftFrom(data));
  }

  async function saveQuyCach() {
    if (!data || data.lenh_item_id == null || saving || !dirty) return;
    setSaving(true);
    try {
      const fresh = await api.lenhSanXuat.suaQuyCach(token, data.lenh_item_id, override);
      setData(fresh);
      setDraft(draftFrom(fresh));
      toasts.ok("Đã lưu quy cách");
      onSaved?.();
    } catch (e) {
      if (e instanceof ApiError && e.isConflict) {
        toasts.err("Lệnh đã phát — không sửa được quy cách nữa.");
      } else {
        toasts.err(e instanceof ApiError ? e.message : "Không lưu được quy cách.");
      }
    } finally {
      setSaving(false);
    }
  }

  // Esc để đóng + khóa cuộn trang nền khi drawer mở.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  const ctxLine = ctx ? [ctx.orderNo, ctx.khach].filter(Boolean).join(" · ") : "";
  const sanPham = data ? specsSanPham(data) : [];
  const giay = data ? specsGiay(data) : [];
  const inMau = data ? specsIn(data, mayName) : [];
  const qty = data ? qtyRows(data) : [];

  return (
    <>
      <div className="lsx-dw__scrim" onClick={onClose} aria-hidden="true" />
      <aside className="lsx-dw" role="dialog" aria-modal="true" aria-label="Chi tiết ấn phẩm">
        <header className="lsx-dw__hd">
          <div className="lsx-dw__hdmain">
            <span className="lsx-dw__kicker">Chi tiết ấn phẩm</span>
            <h2 className="lsx-dw__title">{data?.ten || (loading ? "Đang tải…" : "Ấn phẩm")}</h2>
            {ctxLine ? <span className="lsx-dw__ctx">{ctxLine}</span> : null}
          </div>
          <button type="button" className="lsx-dw__x" onClick={onClose} aria-label="Đóng">
            <XIcon />
          </button>
        </header>

        <div className="lsx-dw__body">
          {loading ? (
            <div className="lsx-dw__msg">Đang tải chi tiết ấn phẩm…</div>
          ) : err ? (
            <div className="banner banner--error" role="alert">
              <span>{err}</span>
              <button
                type="button"
                className="btn btn--ghost"
                style={{ padding: "4px 12px", fontSize: 12 }}
                onClick={() => {
                  setErr(null);
                  setLoading(true);
                  api.lenhSanXuat
                    .anPhamChiTiet(token, ptpId, lenhItemId)
                    .then((d) => {
                      setData(d);
                      setDraft(draftFrom(d));
                    })
                    .catch((e) =>
                      setErr(e instanceof ApiError ? e.message : "Không tải được chi tiết ấn phẩm."),
                    )
                    .finally(() => setLoading(false));
                }}
              >
                Tải lại
              </button>
            </div>
          ) : data ? (
            <>
              {/* Lưu ý SX — khối nổi bật amber, đặt trên cùng (người dùng nhấn mạnh). */}
              {has(data.ghi_chu_ky_thuat) ? (
                <div className="lsx-dw__note">
                  <NoteIcon />
                  <span>
                    <strong>Lưu ý SX:</strong> {data.ghi_chu_ky_thuat}
                  </span>
                </div>
              ) : null}

              {data.editable && draft ? (
                <>
                  {/* ===== Sản phẩm — SỬA (override báo giá) ===== */}
                  <section className="lsx-dw__sec">
                    <span className="lsx-dw__sectitle">
                      <PackageIcon /> Sản phẩm
                    </span>
                    <div className="lsx-dw__form">
                      <EditDim
                        label="Khổ thành phẩm"
                        a={draft.dai_thanh_pham}
                        b={draft.rong_thanh_pham}
                        onA={(v) => upd("dai_thanh_pham", v)}
                        onB={(v) => upd("rong_thanh_pham", v)}
                        overridden={ov("dai_thanh_pham") || ov("rong_thanh_pham")}
                        wide
                      />
                      <EditText label="Khổ TP (nhãn)" value={draft.kho_thanh_pham} onChange={(v) => upd("kho_thanh_pham", v)} overridden={ov("kho_thanh_pham")} />
                      <EditText label="Khổ mở rộng" value={draft.kho_mo_rong} onChange={(v) => upd("kho_mo_rong", v)} overridden={ov("kho_mo_rong")} />
                    </div>
                  </section>

                  {/* ===== Giấy — SỬA (đổi giấy cùng chủng loại khi kho hết) ===== */}
                  <section className="lsx-dw__sec">
                    <span className="lsx-dw__sectitle">
                      <LayersIcon /> Giấy
                    </span>
                    <div className="lsx-dw__form">
                      <div className="lsx-dw__field lsx-dw__field--wide">
                        <FieldLabel
                          label="Giấy"
                          overridden={ov("giay_id")}
                          right={
                            <label className="lsx-dw__toggle">
                              <input type="checkbox" checked={sameChung} onChange={(e) => setSameChung(e.target.checked)} />
                              <span>Chỉ cùng chủng loại</span>
                            </label>
                          }
                        />
                        <Select<number | null>
                          options={giayOptions}
                          value={draft.giay_id}
                          onChange={(v) => upd("giay_id", v)}
                          placeholder="— Chọn giấy —"
                          ariaLabel="Chọn giấy override"
                          portal
                        />
                      </div>
                      <EditDim
                        label="Khổ nguyên"
                        a={draft.kho_nguyen_dai}
                        b={draft.kho_nguyen_rong}
                        onA={(v) => upd("kho_nguyen_dai", v)}
                        onB={(v) => upd("kho_nguyen_rong", v)}
                        overridden={ov("kho_nguyen_dai") || ov("kho_nguyen_rong")}
                        wide
                      />
                      <div className="lsx-dw__field">
                        <FieldLabel label="Nguồn giấy" overridden={ov("nguon_giay")} />
                        <Select<string>
                          options={NGUON_OPTS}
                          value={draft.nguon_giay}
                          onChange={(v) => upd("nguon_giay", v)}
                          placeholder="— Chọn —"
                          ariaLabel="Nguồn giấy"
                          portal
                        />
                      </div>
                    </div>
                  </section>

                  {/* ===== In & màu — SỬA ===== */}
                  <section className="lsx-dw__sec">
                    <span className="lsx-dw__sectitle">
                      <PrinterIcon /> In &amp; màu
                    </span>
                    {data.co_in ? (
                      <div className="lsx-dw__form">
                        <EditText label="Chế bản" value={draft.che_ban_loai} onChange={(v) => upd("che_ban_loai", v)} overridden={ov("che_ban_loai")} />
                        <div className="lsx-dw__field">
                          <FieldLabel label="Cách in" overridden={ov("quy_cach_in")} />
                          <Select<string>
                            options={QCIN_OPTS}
                            value={draft.quy_cach_in}
                            onChange={(v) => upd("quy_cach_in", v)}
                            placeholder="— Chọn —"
                            ariaLabel="Cách in"
                            portal
                          />
                        </div>
                        <EditDim
                          label="Khổ tờ in"
                          a={draft.kho_in_dai}
                          b={draft.kho_in_rong}
                          onA={(v) => upd("kho_in_dai", v)}
                          onB={(v) => upd("kho_in_rong", v)}
                          overridden={ov("kho_in_dai") || ov("kho_in_rong")}
                          wide
                        />
                        <div className="lsx-dw__field">
                          <FieldLabel
                            label="Số con/tờ"
                            overridden={ov("so_con")}
                            right={
                              <label className="lsx-dw__toggle">
                                <input type="checkbox" checked={draft.con_auto} onChange={(e) => upd("con_auto", e.target.checked)} />
                                <span>Tự bình bài</span>
                              </label>
                            }
                          />
                          <input
                            className="lsx-dw__in lsx-dw__in--num"
                            type="number"
                            inputMode="numeric"
                            value={Number.isFinite(draft.so_con) ? String(draft.so_con) : ""}
                            onChange={(e) => upd("so_con", e.target.value === "" ? 0 : Number(e.target.value))}
                            aria-label="Số con trên tờ"
                          />
                        </div>
                        <EditDim
                          label="Số màu (mặt A / B)"
                          a={draft.so_mau_a}
                          b={draft.so_mau_b}
                          onA={(v) => upd("so_mau_a", v)}
                          onB={(v) => upd("so_mau_b", v)}
                          overridden={ov("so_mau_a") || ov("so_mau_b")}
                          sep="/"
                          unit=""
                          wide
                        />
                        <div className="lsx-dw__field">
                          <span className="lsx-dw__flabel">
                            Số kẽm
                            <span className="lsx-dw__auto">tự tính</span>
                          </span>
                          <div className="lsx-dw__ro">{fmt(data.so_kem)}</div>
                        </div>
                      </div>
                    ) : (
                      <div className="lsx-dw__sub">Ấn phẩm không in.</div>
                    )}
                  </section>
                </>
              ) : (
                <>
                  {sanPham.length > 0 ? (
                    <section className="lsx-dw__sec">
                      <span className="lsx-dw__sectitle">
                        <PackageIcon /> Sản phẩm
                      </span>
                      <SpecGrid items={sanPham} />
                    </section>
                  ) : null}

                  {giay.length > 0 ? (
                    <section className="lsx-dw__sec">
                      <span className="lsx-dw__sectitle">
                        <LayersIcon /> Giấy
                      </span>
                      <SpecGrid items={giay} />
                    </section>
                  ) : null}

                  {inMau.length > 0 ? (
                    <section className="lsx-dw__sec">
                      <span className="lsx-dw__sectitle">
                        <PrinterIcon /> In &amp; màu
                      </span>
                      <SpecGrid items={inMau} />
                    </section>
                  ) : null}
                </>
              )}

              {/* Số lượng — engine snapshot; danh sách dòng, số mono tabular. */}
              <section className="lsx-dw__sec">
                <span className="lsx-dw__sectitle">
                  <BoxesIcon /> Số lượng
                </span>
                {data.so_luong_can == null ? (
                  <div className="lsx-dw__sub">Chưa tính giá — chưa có số lượng in</div>
                ) : (
                  <>
                    <div className="lsx-dw__qty">
                      {qty.map((r, i) => (
                        <div
                          className={`lsx-dw__qtyrow${r.strong ? " lsx-dw__qtyrow--strong" : ""}`}
                          key={i}
                        >
                          <span className="k">{r.k}</span>
                          <span className="v">{fmt(r.v)}</span>
                        </div>
                      ))}
                    </div>
                    {/* Snapshot SL không đổi theo override — nhắc số in chốt lại ở khâu sau. */}
                    {data.overridden.length > 0 ? (
                      <p className="lsx-dw__sub">SL theo báo giá — số in chốt lại khi ghép/chạy.</p>
                    ) : null}
                  </>
                )}
              </section>

              {/* Vật tư thêm — vecni bóng/mờ, cán màng… (tên + ghi chú, không giá). */}
              {data.vat_tu.length > 0 ? (
                <section className="lsx-dw__sec">
                  <span className="lsx-dw__sectitle">
                    <DropletIcon /> Vật tư thêm
                  </span>
                  <ul className="lsx-dw__mat">
                    {data.vat_tu.map((m, i) => (
                      <li className="lsx-dw__matrow" key={i}>
                        <span className="lsx-dw__matname">{m.ten}</span>
                        {has(m.ghi_chu) ? <span className="lsx-dw__sub">{m.ghi_chu}</span> : null}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {/* Routing gốc (theo tính giá) — traveler CHỈ ĐỌC. */}
              <section className="lsx-dw__sec">
                <span className="lsx-dw__sectitle">
                  <RouteIcon /> Routing (theo tính giá)
                </span>
                {data.routing.length === 0 ? (
                  <div className="lsx-empty lsx-empty--sm">
                    <p className="lsx-empty__title">Chưa khai công đoạn</p>
                    <p className="lsx-empty__sub">
                      Routing gốc kế thừa từ phiếu tính giá; ấn phẩm này chưa khai công đoạn nào.
                    </p>
                  </div>
                ) : (
                  <ol className="lsx-trav">
                    {data.routing.map((s, i) => {
                      const last = i === data.routing.length - 1;
                      return (
                        <li key={i} className="lsx-trav__step">
                          <div className="lsx-trav__rail">
                            <span className="lsx-trav__node" aria-hidden="true">
                              <span className="lsx-trav__no">{i + 1}</span>
                            </span>
                            {last ? null : <span className="lsx-trav__line" />}
                          </div>
                          <div className="lsx-trav__body">
                            <div className="lsx-trav__top">
                              <span className="lsx-trav__ten">{s.ten || cdName(s.cong_doan_id)}</span>
                            </div>
                            {s.nha_cung_cap ? (
                              <span className="lsx-trav__to">
                                <UsersIcon /> Thuê: {s.nha_cung_cap}
                              </span>
                            ) : null}
                            {s.ghi_chu ? <span className="lsx-dw__sub">{s.ghi_chu}</span> : null}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </section>
            </>
          ) : null}
        </div>

        <footer className="lsx-dw__foot">
          {data?.editable && dirty ? (
            <button type="button" className="btn btn--ghost" onClick={resetDraft} disabled={saving}>
              Hoàn tác
            </button>
          ) : null}
          <div className="lsx-dw__footright">
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Đóng
            </button>
            {data?.editable ? (
              <button
                type="button"
                className="btn btn--primary"
                onClick={saveQuyCach}
                disabled={!dirty || saving}
              >
                {saving ? "Đang lưu…" : "Lưu quy cách"}
              </button>
            ) : null}
          </div>
        </footer>
      </aside>
      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />
    </>
  );
}

// ---------- Chế độ SỬA: field input (label + dấu "đã sửa" override) ----------
function FieldLabel({ label, overridden, right }: { label: string; overridden?: boolean; right?: ReactNode }) {
  const lbl = (
    <span className="lsx-dw__flabel">
      {label}
      {overridden ? <span className="lsx-dw__ovchip">đã sửa</span> : null}
    </span>
  );
  if (!right) return lbl;
  return (
    <div className="lsx-dw__flabelrow">
      {lbl}
      {right}
    </div>
  );
}

function EditText({
  label,
  value,
  onChange,
  overridden,
  wide,
}: {
  label: string;
  value: string;
  onChange: (s: string) => void;
  overridden?: boolean;
  wide?: boolean;
}) {
  return (
    <div className={`lsx-dw__field${wide ? " lsx-dw__field--wide" : ""}`}>
      <FieldLabel label={label} overridden={overridden} />
      <input
        className="lsx-dw__in"
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
      />
    </div>
  );
}

// Cặp số (dài × rộng · số màu A/B) trên 1 dòng.
function EditDim({
  label,
  a,
  b,
  onA,
  onB,
  overridden,
  wide,
  unit = "mm",
  sep = "×",
}: {
  label: string;
  a: number;
  b: number;
  onA: (n: number) => void;
  onB: (n: number) => void;
  overridden?: boolean;
  wide?: boolean;
  unit?: string;
  sep?: string;
}) {
  return (
    <div className={`lsx-dw__field${wide ? " lsx-dw__field--wide" : ""}`}>
      <FieldLabel label={label} overridden={overridden} />
      <div className="lsx-dw__dim">
        <input
          className="lsx-dw__in lsx-dw__in--num"
          type="number"
          inputMode="decimal"
          value={Number.isFinite(a) ? String(a) : ""}
          onChange={(e) => onA(e.target.value === "" ? 0 : Number(e.target.value))}
          aria-label={`${label} 1`}
        />
        <span className="lsx-dw__x2" aria-hidden="true">{sep}</span>
        <input
          className="lsx-dw__in lsx-dw__in--num"
          type="number"
          inputMode="decimal"
          value={Number.isFinite(b) ? String(b) : ""}
          onChange={(e) => onB(e.target.value === "" ? 0 : Number(e.target.value))}
          aria-label={`${label} 2`}
        />
        {unit ? <span className="lsx-dw__unit">{unit}</span> : null}
      </div>
    </div>
  );
}

// ---------- Inline icons (Lucide-style, stroke 1.9, currentColor) ----------
const XIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);
const UsersIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="3.2" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);
const NoteIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M15.5 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L15.5 3Z" />
    <path d="M15 3v5h5M8.5 12.5h7M8.5 16h5" />
  </svg>
);
const PackageIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
    <path d="m3.3 7 8.7 5 8.7-5M12 22V12" />
  </svg>
);
const LayersIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z" />
    <path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65M22 12.65l-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" />
  </svg>
);
const PrinterIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
    <path d="M6 9V2h12v7M6 14h12v8H6z" />
  </svg>
);
const BoxesIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z" />
    <path d="m7 16.5-4.74-2.85M7 16.5l5-3M7 16.5v5.17" />
    <path d="M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z" />
    <path d="m17 16.5-5-3M17 16.5l4.74-2.85M17 16.5v5.17" />
    <path d="M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z" />
    <path d="M12 8 7.26 5.15M12 8l4.74-2.85M12 13.5V8" />
  </svg>
);
const DropletIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7Z" />
  </svg>
);
const RouteIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="6" cy="19" r="3" />
    <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
    <circle cx="18" cy="5" r="3" />
  </svg>
);
