// Trang Phiếu kho — cỗ máy chứng từ (spec-13). Một khung phiếu cho mọi nghiệp vụ; hành vi
// (chiều tồn, kho nguồn/đích, duyệt) lấy từ loại phiếu. Nháp → Nộp → (Duyệt) → Ghi sổ. Gate `kho`.
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type VoucherRow,
  type VoucherLineInput,
  type VoucherInput,
  type VoucherAttachment,
  type ProductionOrderOption,
  type KhoVoucherType,
  type KhoItemStatus,
  type KhoMaterialOption,
  type WarehouseRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ProductionOrderForm } from "./ProductionOrdersPage";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import "./master-data.css";

const STATUS_LABEL: Record<string, string> = {
  draft: "Nháp", pending: "Chờ duyệt", posted: "Đã ghi sổ", cancelled: "Đã hủy",
};

export function StockVoucherPage({ fixedTypeId = null }: { fixedTypeId?: number | null }) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("kho", "create");
  const canApprove = can("kho", "approve");

  const [rows, setRows] = useState<VoucherRow[]>([]);
  const [types, setTypes] = useState<KhoVoucherType[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [statuses, setStatuses] = useState<KhoItemStatus[]>([]);
  const [statusF, setStatusF] = useState("");
  const [typeF, setTypeF] = useState<number | null>(null);
  const [partnerF, setPartnerF] = useState(""); // lọc NCC/đối tượng (client)
  const [createdByF, setCreatedByF] = useState(""); // lọc người nhập theo tên (client)
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<VoucherRow | null>(null);

  const typeById = useMemo(() => new Map(types.map((t) => [t.id, t])), [types]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);
  const fixedType = fixedTypeId != null ? typeById.get(fixedTypeId) : null;

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.kho.listVouchers(token, {
      status: statusF || undefined,
      voucher_type_id: fixedTypeId ?? typeF,
      size: 100,
    })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh sách phiếu.");
      })
      .finally(() => setLoading(false));
  }, [token, statusF, typeF, fixedTypeId]);

  // Danh sách người nhập (từ dữ liệu đã tải) cho dropdown lọc.
  const creators = useMemo(
    () => Array.from(new Set(rows.map((v) => v.created_by_name).filter(Boolean))) as string[],
    [rows],
  );
  // Lọc phía client: NCC (chứa) + người nhập (đúng tên).
  const shownRows = useMemo(
    () => rows.filter((v) =>
      (!partnerF.trim() || (v.partner_ref ?? "").toLowerCase().includes(partnerF.trim().toLowerCase())) &&
      (!createdByF || v.created_by_name === createdByF)),
    [rows, partnerF, createdByF],
  );

  useEffect(() => {
    if (!token) return;
    api.kho.voucherTypes(token).then((r) => setTypes(r.items)).catch(() => {});
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => setWarehouses(r.items)).catch(() => {});
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.kho.itemStatuses(token).then((r) => setStatuses(r.items)).catch(() => {});
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">Bạn không có quyền truy cập Phiếu kho (403).</div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kho · Chứng từ</p>
        <h1 className="md-page__title">{fixedType ? fixedType.name : "Phiếu kho"}</h1>
        <p className="md-page__sub">
          {fixedType
            ? `Danh sách phiếu "${fixedType.name}" và tạo phiếu mới loại này. Nộp → (duyệt nếu cần) → ghi sổ.`
            : "Một khung phiếu cho mọi nghiệp vụ. Loại phiếu quyết định chiều tồn + kho nguồn/đích + duyệt."}
        </p>
      </header>

      <div className="md-page__toolbar">
        <select className="input" value={statusF} onChange={(e) => setStatusF(e.target.value)}>
          <option value="">— Tất cả trạng thái —</option>
          <option value="draft">Nháp</option>
          <option value="pending">Chờ duyệt</option>
          <option value="posted">Đã ghi sổ</option>
          <option value="cancelled">Đã hủy</option>
        </select>
        {!fixedType && (
          <select className="input" value={typeF ?? ""} onChange={(e) => setTypeF(e.target.value ? Number(e.target.value) : null)}>
            <option value="">— Tất cả loại phiếu —</option>
            {types.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
          </select>
        )}
        <select className="input" value={createdByF} onChange={(e) => setCreatedByF(e.target.value)}>
          <option value="">— Tất cả người nhập —</option>
          {creators.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input className="input" placeholder="Lọc theo NCC/đối tượng…" value={partnerF} onChange={(e) => setPartnerF(e.target.value)} />
        <div className="md-page__toolbar-spacer" />
        {canCreate && <Button variant="primary" onClick={() => setCreating(true)}>+ Tạo phiếu</Button>}
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr><th>Mã phiếu</th><th>Loại phiếu</th><th>Kho</th><th>Nhập từ</th><th>Người nhập</th><th>Số dòng</th><th>Trạng thái</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="md-page__status">Đang tải...</td></tr>
            ) : shownRows.length === 0 ? (
              <tr><td colSpan={7} className="md-page__empty">{rows.length === 0 ? "Chưa có phiếu. Bấm “Tạo phiếu”." : "Không có phiếu khớp bộ lọc."}</td></tr>
            ) : (
              shownRows.map((v) => {
                const t = typeById.get(v.voucher_type_id);
                const src = v.src_warehouse_id ? whById.get(v.src_warehouse_id)?.code : null;
                const dst = v.dst_warehouse_id ? whById.get(v.dst_warehouse_id)?.code : null;
                return (
                  <tr key={v.id} className="md-page__row" onClick={() => setDetail(v)}>
                    <td className="md-page__mono">{v.code}</td>
                    <td>{t ? t.name : `#${v.voucher_type_id}`}</td>
                    <td>{[src, dst].filter(Boolean).join(" → ") || <span className="md-page__muted">—</span>}</td>
                    <td>{v.partner_ref || <span className="md-page__muted">—</span>}</td>
                    <td>{v.created_by_name || <span className="md-page__muted">—</span>}</td>
                    <td>{v.lines.length}</td>
                    <td>
                      <span className={`md-page__status-badge ${v.status === "posted" ? "is-active" : "is-inactive"}`}>
                        {STATUS_LABEL[v.status] ?? v.status}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {creating && (
        <VoucherForm types={types} warehouses={warehouses} materials={materials} statuses={statuses}
          lockedTypeId={fixedTypeId}
          onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(); }} />
      )}
      {detail && (
        <VoucherDetail voucher={detail} types={types} warehouses={warehouses} materials={materials} statuses={statuses}
          canApprove={canApprove} canCreate={canCreate}
          onClose={() => setDetail(null)} onChanged={() => { setDetail(null); load(); }} />
      )}
    </main>
  );
}

const EMPTY_LINE: VoucherLineInput = { material_id: 0, quantity: 0 };

// --- Cấu hình form theo LOẠI phiếu (BRD Module Kho §2) ----------------------
// Mỗi nghiệp vụ nhập/xuất có đối tượng, chứng từ gốc và cột dòng khác nhau. Khai báo
// ở đây thay vì viết cứng từng form: map theo mã phiếu, fallback theo chiều tồn.
type PartnerKind = "ncc" | "khach" | "lsx" | "bo_phan" | "may";
interface VoucherFieldSpec {
  partnerKind: PartnerKind | null; // null = không có khối đối tượng (vd chuyển kho)
  partnerLabel: string;
  partnerPlaceholder: string;
  refLabel: string | null; // chứng từ gốc; null = ẩn
  refType: string | null; // lưu vào ref_type
  refPlaceholder: string;
  showCost: boolean; // cột Đơn giá (giá vốn nhập) — chỉ nhập mua
  showStatus: boolean; // cột Trạng thái hàng (KCS) — phiếu nhập
  showOnHand: boolean; // cột SL tồn (đối chiếu khi xuất)
  qtyLabel: string;
}

const SPEC_BY_CODE: Record<string, VoucherFieldSpec> = {
  // §2.2 — nhập NVL mua từ nhà cung cấp: đối tượng NCC, chứng từ = PO, có giá vốn + KCS.
  "NK-NVL": { partnerKind: "ncc", partnerLabel: "Nhà cung cấp", partnerPlaceholder: "VD: Cty Giấy An Bình",
    refLabel: "Số PO / phiếu giao", refType: "po", refPlaceholder: "VD: PO-2026-014",
    showCost: true, showStatus: true, showOnHand: false, qtyLabel: "SL thực nhận" },
  // Nhập giấy khách gửi: đối tượng KHÁCH, hàng khách gửi → KHÔNG ghi giá trị tồn (§1.5).
  "NK-GK": { partnerKind: "khach", partnerLabel: "Khách hàng (chủ giấy)", partnerPlaceholder: "VD: Cty ABC",
    refLabel: "Số đơn hàng / LSX", refType: "order", refPlaceholder: "VD: DH-1234",
    showCost: false, showStatus: true, showOnHand: false, qtyLabel: "SL thực nhận" },
  // §2.3 — nhập thành phẩm sau sản xuất: đối tượng LSX/đơn hàng, không nhập giá vốn (giá thành hệ thống).
  "NK-XUONG": { partnerKind: "lsx", partnerLabel: "LSX / Đơn hàng", partnerPlaceholder: "VD: LSX-2026-088",
    refLabel: "Phiếu bàn giao", refType: "lsx", refPlaceholder: "VD: BG-090",
    showCost: false, showStatus: true, showOnHand: false, qtyLabel: "SL bàn giao" },
  // §2.11 — xuất giao khách hàng: đối tượng KHÁCH, chứng từ đơn hàng, đối chiếu SL tồn.
  "XK-KH": { partnerKind: "khach", partnerLabel: "Khách hàng", partnerPlaceholder: "VD: Cty ABC",
    refLabel: "Số đơn hàng", refType: "order", refPlaceholder: "VD: DH-1234",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" },
  // Xuất trả nhà cung cấp: đối tượng NCC, tham chiếu phiếu nhập gốc.
  "XK-NCC": { partnerKind: "ncc", partnerLabel: "Nhà cung cấp (trả)", partnerPlaceholder: "VD: Cty Giấy An Bình",
    refLabel: "Phiếu nhập gốc", refType: "po", refPlaceholder: "VD: NK-...",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL trả" },
  // §2.5 — xuất NVL cho sản xuất theo LSX (gồm giấy + vật tư khác). LSX là đối tượng.
  "XK-SX": { partnerKind: "lsx", partnerLabel: "LSX", partnerPlaceholder: "VD: LSX-2026-088",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" },
  // §2.7 — nhập trả vật tư thừa từ SX: đối tượng LSX + tham chiếu phiếu xuất gốc; có trạng thái (đạt/lỗi).
  "NK-TRA": { partnerKind: "lsx", partnerLabel: "LSX", partnerPlaceholder: "VD: LSX-2026-088",
    refLabel: "Phiếu xuất gốc", refType: "xuat_goc", refPlaceholder: "VD: XK-...",
    showCost: false, showStatus: true, showOnHand: false, qtyLabel: "SL trả" },
  // §2.8 — cấp phát vật tư tiêu hao/CCDC nội bộ: đối tượng bộ phận/tổ nhận.
  "XK-CCDC": { partnerKind: "bo_phan", partnerLabel: "Bộ phận / tổ nhận", partnerPlaceholder: "VD: Tổ In 1",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL cấp" },
  // §2.9 — xuất phụ tùng/bảo trì cho máy: đối tượng máy/thiết bị + lý do bảo trì.
  "XK-BT": { partnerKind: "may", partnerLabel: "Máy / thiết bị", partnerPlaceholder: "VD: Máy in Komori #1",
    refLabel: "Lệnh / lý do bảo trì", refType: "bao_tri", refPlaceholder: "VD: Thay trục cao su",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" },
  // §2.14 — xuất hủy/thanh lý: không có đối tượng; lý do ghi ở Diễn giải. Bắt buộc chọn hàng còn tồn.
  "XK-HUY": { partnerKind: null, partnerLabel: "Đối tượng", partnerPlaceholder: "",
    refLabel: "Lý do hủy / thanh lý", refType: "huy", refPlaceholder: "VD: Hàng lỗi không sửa được",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL hủy" },
};

function specForType(vt: KhoVoucherType | undefined): VoucherFieldSpec {
  if (vt && SPEC_BY_CODE[vt.code]) return SPEC_BY_CODE[vt.code];
  // Fallback theo chiều tồn cho loại phiếu tự tạo.
  if (vt?.stock_effect === "tang")
    return { partnerKind: "ncc", partnerLabel: "Nhập từ (NCC/đối tượng)", partnerPlaceholder: "VD: Cty Giấy An Bình",
      refLabel: "Chứng từ gốc", refType: null, refPlaceholder: "Số PO / phiếu giao…",
      showCost: true, showStatus: true, showOnHand: false, qtyLabel: "Số lượng" };
  if (vt?.stock_effect === "giam")
    return { partnerKind: "bo_phan", partnerLabel: "Giao cho (bộ phận/khách)", partnerPlaceholder: "VD: Tổ In / Cty ABC",
      refLabel: "Chứng từ gốc", refType: null, refPlaceholder: "LSX / đơn hàng…",
      showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" };
  // Chuyển kho / khác: không có đối tượng.
  return { partnerKind: null, partnerLabel: "Đối tượng", partnerPlaceholder: "",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "Số lượng" };
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Điền sẵn form từ 1 Lệnh sản xuất (LSX) — dùng khi "sinh phiếu kho từ phiếu sản xuất". */
export interface VoucherPrefillLsx {
  id: number; code: string;
  customerName?: string | null; productName?: string | null; quantity?: number | null;
}

export function VoucherForm({
  types, warehouses, materials, statuses,
  lockedWarehouse = null, restrictEffect = null, lockedTypeId = null, prefillLsx = null, onClose, onSaved,
}: {
  types: KhoVoucherType[]; warehouses: WarehouseRow[]; materials: KhoMaterialOption[];
  statuses: KhoItemStatus[];
  /** Nếu set: khóa kho nguồn/đích theo kho này (dùng cho phiếu trong 1 kho cụ thể). */
  lockedWarehouse?: WarehouseRow | null;
  /** Nếu set: chỉ cho chọn loại phiếu có chiều tồn này (tang=nhập, giam=xuất, chuyen_vi_tri=chuyển kho). */
  restrictEffect?: "tang" | "giam" | "chuyen_vi_tri" | null;
  /** Nếu set: khóa cứng vào 1 loại phiếu (menu phiếu theo loại). */
  lockedTypeId?: number | null;
  /** Nếu set: sinh phiếu từ 1 LSX — điền sẵn đối tượng + gắn ref_id + hiện panel LSX read-only. */
  prefillLsx?: VoucherPrefillLsx | null;
  onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const shownTypes = useMemo(
    () => {
      // Chỉ cho tạo phiếu bằng loại đang bật (is_active); loại đã gộp/ẩn không hiện.
      const active = types.filter((t) => t.is_active !== false);
      if (lockedTypeId != null) return active.filter((t) => t.id === lockedTypeId);
      if (restrictEffect) return active.filter((t) => t.stock_effect === restrictEffect);
      return active;
    },
    [types, restrictEffect, lockedTypeId],
  );
  const [typeId, setTypeId] = useState<number | null>(lockedTypeId ?? shownTypes[0]?.id ?? null);
  const [docDate, setDocDate] = useState(todayISO());
  const [srcWh, setSrcWh] = useState<number | null>(null);
  const [dstWh, setDstWh] = useState<number | null>(null);
  const [partner, setPartner] = useState(""); // NCC / khách / LSX / bộ phận — theo loại phiếu
  const [docRef, setDocRef] = useState(""); // chứng từ gốc (PO / LSX / đơn hàng)
  const [reason, setReason] = useState("");
  const [lines, setLines] = useState<VoucherLineInput[]>([{ ...EMPTY_LINE }]);
  const [onHand, setOnHand] = useState<Record<number, number>>({}); // SL tồn theo vật tư (kho nguồn)
  const [files, setFiles] = useState<File[]>([]); // chứng từ đính kèm (tải lên sau khi tạo phiếu)
  const [lsxOptions, setLsxOptions] = useState<ProductionOrderOption[]>([]);
  const [lsxId, setLsxId] = useState<number | null>(null); // LSX đã chọn (ref_id)
  const [quickLsx, setQuickLsx] = useState(false); // mở modal tạo LSX nhanh
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const vt = shownTypes.find((t) => t.id === typeId);
  const spec = specForType(vt);
  const isLsx = spec.partnerKind === "lsx";

  // Nạp danh sách LSX đang mở khi loại phiếu tham chiếu LSX (nhập thành phẩm / xuất NVL).
  useEffect(() => {
    if (!token || !isLsx) return;
    api.production.orderOptions(token).then(setLsxOptions).catch(() => {});
  }, [token, isLsx]);

  function pickLsx(id: number | null) {
    setLsxId(id);
    const opt = lsxOptions.find((o) => o.id === id);
    setPartner(opt ? opt.code : "");
  }

  // Sinh phiếu từ LSX: điền sẵn đối tượng (LSX hoặc khách) + đưa LSX vào danh sách chọn.
  useEffect(() => {
    if (!prefillLsx) return;
    if (isLsx) {
      setLsxId(prefillLsx.id);
      setPartner(prefillLsx.code);
      setLsxOptions((os) => os.some((o) => o.id === prefillLsx.id) ? os
        : [{ id: prefillLsx.id, code: prefillLsx.code, label: `${prefillLsx.code}${prefillLsx.productName ? ` · ${prefillLsx.productName}` : ""}` }, ...os]);
    } else if (spec.partnerKind === "khach") {
      setPartner(prefillLsx.customerName ?? "");
    }
  }, [prefillLsx, isLsx, spec.partnerKind]);
  const needSrc = vt?.require_src_wh || vt?.stock_effect === "giam" || vt?.stock_effect === "chuyen_vi_tri";
  const needDst = vt?.require_dst_wh || vt?.stock_effect === "tang" || vt?.stock_effect === "chuyen_vi_tri";
  // Kho khóa sẵn: nhập → khóa đích; xuất → khóa nguồn; CHUYỂN KHO (cần cả 2) → khóa NGUỒN,
  // để đích cho người dùng chọn.
  const isTransfer = needSrc && needDst;
  const lockSrc = !!lockedWarehouse && needSrc;
  const lockDst = !!lockedWarehouse && needDst && !isTransfer;
  const effSrc = lockSrc ? lockedWarehouse!.id : srcWh;
  const effDst = lockDst ? lockedWarehouse!.id : dstWh;

  // SL tồn: nạp tồn kho nguồn cho các vật tư đã chọn (phiếu xuất/chuyển). Đổi kho → nạp lại.
  const matKey = lines.map((l) => l.material_id).filter(Boolean).join(",");
  useEffect(() => {
    if (!token || !spec.showOnHand || !effSrc) { setOnHand({}); return; }
    const ids = Array.from(new Set(matKey.split(",").filter(Boolean).map(Number)));
    if (!ids.length) { setOnHand({}); return; }
    let alive = true;
    Promise.all(ids.map((id) =>
      api.kho.stock(token, { material_id: id, warehouse_id: effSrc })
        .then((r) => [id, r.items.reduce((s, x) => s + (x.on_hand ?? 0), 0)] as const)
        .catch(() => [id, 0] as const),
    )).then((pairs) => { if (alive) setOnHand(Object.fromEntries(pairs)); });
    return () => { alive = false; };
  }, [token, spec.showOnHand, effSrc, matKey]);

  function setLine(i: number, patch: Partial<VoucherLineInput>) {
    setLines((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  }
  function pickMaterial(i: number, mid: number) {
    const avail = statuses.find((s) => s.code === "AVAILABLE");
    setLine(i, { material_id: mid, status_id: spec.showStatus ? (avail?.id ?? null) : null });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);
    if (!typeId) return setError("Chọn loại phiếu.");
    if (needSrc && !effSrc) return setError("Loại phiếu này cần Kho nguồn.");
    if (needDst && !effDst) return setError("Loại phiếu này cần Kho đích.");
    if (isLsx && !lsxId) return setError("Chọn Lệnh sản xuất (LSX). Chưa có thì bấm “+ Tạo nhanh”.");
    if (spec.partnerKind && !isLsx && !partner.trim()) return setError(`Cần nhập ${spec.partnerLabel}.`);
    const valid = lines.filter((l) => l.material_id && Number(l.quantity) > 0);
    if (!valid.length) return setError("Cần ít nhất 1 dòng (vật tư + số lượng > 0).");

    const payload: VoucherInput = {
      voucher_type_id: typeId,
      doc_date: docDate || null,
      src_warehouse_id: needSrc ? effSrc : null,
      dst_warehouse_id: needDst ? effDst : null,
      partner_kind: spec.partnerKind && partner.trim() ? spec.partnerKind : null,
      partner_ref: partner.trim() || null,
      // LSX → FK cứng (ref_id). Sinh phiếu từ LSX luôn gắn ref bất kể loại phiếu.
      ref_type: prefillLsx ? "lsx" : (isLsx ? "lsx" : (docRef.trim() ? spec.refType : null)),
      ref_id: prefillLsx ? prefillLsx.id : (isLsx ? lsxId : null),
      note: docRef.trim() || null, // chứng từ gốc (PO/đơn hàng) — text tự do
      reason: reason.trim() || null,
      lines: valid.map((l) => ({
        material_id: l.material_id, quantity: Number(l.quantity),
        uom: l.uom?.trim() || null,
        status_id: spec.showStatus ? (l.status_id ?? null) : null,
        unit_cost: spec.showCost && l.unit_cost != null && String(l.unit_cost) !== "" ? Number(l.unit_cost) : null,
        note: l.note?.trim() || null,
      })),
    };
    setSaving(true);
    try {
      const created = await api.kho.createVoucher(token, payload);
      // Tải chứng từ đính kèm lên phiếu vừa tạo (nếu có).
      if (files.length) {
        try {
          for (const f of files) await api.kho.uploadVoucherAttachment(token, created.id, f);
        } catch {
          // Phiếu đã lưu nháp — chỉ báo phần đính kèm lỗi, mở lại phiếu để thử lại.
          setError("Phiếu đã lưu (nháp) nhưng có file đính kèm tải lên thất bại. Mở phiếu để đính kèm lại.");
          setSaving(false);
          return;
        }
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu phiếu thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 940, width: "94%" }}>
        <div className="md-page__dialog-head">
          <h2>{prefillLsx ? `Tạo phiếu ${vt ? vt.name : "kho"} từ LSX` : `Tạo phiếu kho${vt ? ` · ${vt.name}` : ""}`}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {prefillLsx && (
            <div className="md-page__wh-badge" style={{ display: "block", margin: "0 0 14px", padding: "10px 12px" }}>
              <div className="md-page__muted" style={{ marginBottom: 4 }}>Theo phiếu sản xuất</div>
              <div><strong className="md-page__mono">{prefillLsx.code}</strong>
                {prefillLsx.customerName ? ` · ${prefillLsx.customerName}` : ""}</div>
              {prefillLsx.productName && <div style={{ fontSize: 13 }}>Ấn phẩm: {prefillLsx.productName}
                {prefillLsx.quantity != null ? ` · SL: ${prefillLsx.quantity}` : ""}</div>}
            </div>
          )}
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Loại phiếu *</span>
              {lockedTypeId != null ? (
                <div className="md-page__wh-badge" style={{ margin: 0 }}>
                  <strong>{vt?.name ?? shownTypes[0]?.name}</strong>
                </div>
              ) : (
                <select className="input" value={typeId ?? ""} onChange={(e) => setTypeId(Number(e.target.value))}>
                  {shownTypes.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
                </select>
              )}
            </label>
            <label className="field">
              <span className="field__label">Ngày phiếu</span>
              <input className="input" type="date" value={docDate} onChange={(e) => setDocDate(e.target.value)} />
            </label>
            {needSrc && (
              <label className="field">
                <span className="field__label">Kho nguồn *</span>
                {lockSrc ? (
                  <div className="md-page__wh-badge" style={{ margin: 0 }}>
                    <span className="md-page__mono">{lockedWarehouse!.code}</span>
                    <strong>{lockedWarehouse!.name}</strong>
                  </div>
                ) : (
                  <select className="input" value={srcWh ?? ""} onChange={(e) => setSrcWh(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— Chọn —</option>
                    {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
                  </select>
                )}
              </label>
            )}
            {needDst && (
              <label className="field">
                <span className="field__label">Kho đích *</span>
                {lockDst ? (
                  <div className="md-page__wh-badge" style={{ margin: 0 }}>
                    <span className="md-page__mono">{lockedWarehouse!.code}</span>
                    <strong>{lockedWarehouse!.name}</strong>
                  </div>
                ) : (
                  <select className="input" value={dstWh ?? ""} onChange={(e) => setDstWh(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— Chọn kho đích —</option>
                    {warehouses.filter((w) => w.id !== lockedWarehouse?.id).map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
                  </select>
                )}
              </label>
            )}
            {isLsx ? (
              <label className="field">
                <span className="field__label">{spec.partnerLabel} *</span>
                <div style={{ display: "flex", gap: 8 }}>
                  <select className="input" style={{ flex: 1 }} value={lsxId ?? ""} onChange={(e) => pickLsx(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— Chọn LSX —</option>
                    {lsxOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                  <Button type="button" variant="ghost" onClick={() => setQuickLsx(true)}>+ Tạo nhanh</Button>
                </div>
              </label>
            ) : spec.partnerKind ? (
              <label className="field">
                <span className="field__label">{spec.partnerLabel} *</span>
                <input className="input" placeholder={spec.partnerPlaceholder} value={partner} onChange={(e) => setPartner(e.target.value)} />
              </label>
            ) : null}
            {spec.refLabel && (
              <label className="field">
                <span className="field__label">{spec.refLabel}</span>
                <input className="input" placeholder={spec.refPlaceholder} value={docRef} onChange={(e) => setDocRef(e.target.value)} />
              </label>
            )}
            <label className="field md-page__form-wide">
              <span className="field__label">Diễn giải / Lý do</span>
              <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
            <div className="field md-page__form-wide">
              <span className="field__label">Đính kèm (hóa đơn, PO, phiếu giao…)</span>
              <input
                className="input"
                type="file"
                multiple
                onChange={(e) => {
                  const picked = Array.from(e.target.files ?? []);
                  if (picked.length) setFiles((fs) => [...fs, ...picked]);
                  e.target.value = ""; // cho phép chọn lại cùng file
                }}
              />
              {files.length > 0 && (
                <ul className="md-page__filelist">
                  {files.map((f, i) => (
                    <li key={i}>
                      <span className="md-page__file-name">📎 {f.name}</span>
                      <button type="button" className="md-page__file-x" onClick={() => setFiles((fs) => fs.filter((_, k) => k !== i))}>✕</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="md-page__lines-head">
            <strong>Dòng hàng</strong>
            <Button type="button" variant="ghost" onClick={() => setLines((ls) => [...ls, { ...EMPTY_LINE }])}>+ Thêm dòng</Button>
          </div>
          <div className="md-page__tablewrap" style={{ marginTop: 0 }}>
            <table className="md-page__table">
              <thead>
                <tr>
                  <th>Vật tư</th>
                  {spec.showOnHand && <th>SL tồn</th>}
                  <th>{spec.qtyLabel}</th>
                  <th>Đơn vị</th>
                  {spec.showCost && <th>Đơn giá</th>}
                  {spec.showStatus && <th>Trạng thái</th>}
                  <th>Ghi chú</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l, i) => {
                  const bal = l.material_id ? onHand[l.material_id] : undefined;
                  const over = spec.showOnHand && bal != null && Number(l.quantity) > bal;
                  return (
                  <tr key={i}>
                    <td>
                      <select className="input" value={l.material_id || ""} onChange={(e) => pickMaterial(i, Number(e.target.value))}>
                        <option value="">— Chọn —</option>
                        {materials.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
                      </select>
                    </td>
                    {spec.showOnHand && (
                      <td className="md-page__mono" style={over ? { color: "var(--danger, #c0392b)", fontWeight: 600 } : undefined}>
                        {l.material_id ? (bal != null ? bal : "…") : "—"}
                      </td>
                    )}
                    <td><input className="input" type="number" step="0.001" style={{ width: 100 }} value={l.quantity || ""} onChange={(e) => setLine(i, { quantity: Number(e.target.value) })} /></td>
                    <td><input className="input" placeholder="ream/kg…" style={{ width: 90 }} value={l.uom ?? ""} onChange={(e) => setLine(i, { uom: e.target.value })} /></td>
                    {spec.showCost && (
                      <td><input className="input" type="number" step="1" placeholder="đ/đơn vị" style={{ width: 110 }} value={l.unit_cost ?? ""} onChange={(e) => setLine(i, { unit_cost: e.target.value ? Number(e.target.value) : null })} /></td>
                    )}
                    {spec.showStatus && (
                      <td>
                        <select className="input" value={l.status_id ?? ""} onChange={(e) => setLine(i, { status_id: e.target.value ? Number(e.target.value) : null })}>
                          {statuses.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                      </td>
                    )}
                    <td><input className="input" placeholder="Ghi chú" style={{ minWidth: 120 }} value={l.note ?? ""} onChange={(e) => setLine(i, { note: e.target.value })} /></td>
                    <td><button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={() => setLines((ls) => ls.length > 1 ? ls.filter((_, k) => k !== i) : ls)}>✕</button></td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {spec.showOnHand && lines.some((l) => l.material_id && onHand[l.material_id] != null && Number(l.quantity) > onHand[l.material_id]) && (
            <p className="md-page__muted" style={{ marginTop: 6, color: "var(--danger, #c0392b)" }}>
              ⚠ Có dòng xuất vượt tồn kho nguồn — sẽ bị chặn khi ghi sổ.
            </p>
          )}
          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu phiếu (nháp)</Button>
          </div>
        </form>
      </div>
      {quickLsx && (
        <ProductionOrderForm
          onClose={() => setQuickLsx(false)}
          onSaved={(created) => {
            setQuickLsx(false);
            const opt: ProductionOrderOption = { id: created.id, code: created.code, label: `${created.code}${created.product_name ? ` · ${created.product_name}` : ""}` };
            setLsxOptions((os) => [opt, ...os]);
            setLsxId(created.id);
            setPartner(created.code);
          }}
        />
      )}
    </div>
  );
}

// Định dạng ngày/số cho màn chi tiết.
function fmtDate(s: string | null): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  return d && m && y ? `${d}/${m}/${y}` : s;
}
function fmtDateTime(s: string | null): string {
  if (!s) return "—";
  const dt = new Date(s);
  return isNaN(dt.getTime()) ? s : dt.toLocaleString("vi-VN");
}
function fmtNum(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 3 });
}
function escHtml(v: unknown): string {
  return String(v ?? "—").replace(/[&<>]/g, (c) => (c === "&" ? "&amp;" : c === "<" ? "&lt;" : "&gt;"));
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 12, padding: "5px 0", fontSize: 14, alignItems: "baseline" }}>
      <span className="md-page__muted" style={{ textAlign: "right" }}>{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function VoucherDetail({
  voucher, types, warehouses, materials, statuses = [], canApprove, canCreate, onClose, onChanged,
}: {
  voucher: VoucherRow; types: KhoVoucherType[]; warehouses: WarehouseRow[]; materials: KhoMaterialOption[];
  statuses?: KhoItemStatus[];
  canApprove: boolean; canCreate: boolean; onClose: () => void; onChanged: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canPrice = can("kho", "manage_price");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = types.find((x) => x.id === voucher.voucher_type_id);
  const spec = specForType(t);
  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const statusById = useMemo(() => new Map(statuses.map((s) => [s.id, s.name])), [statuses]);
  const whLabel = (id: number | null) => {
    if (!id) return null;
    const w = warehouses.find((x) => x.id === id);
    return w ? `${w.code} · ${w.name}` : `#${id}`;
  };
  const khoText = [whLabel(voucher.src_warehouse_id), whLabel(voucher.dst_warehouse_id)].filter(Boolean).join("  →  ") || "—";

  // Chứng từ đính kèm — thêm/xóa khi phiếu còn Nháp/Chờ duyệt.
  const [atts, setAtts] = useState<VoucherAttachment[]>([]);
  const [attBusy, setAttBusy] = useState(false);
  const canEditAtt = canCreate && (voucher.status === "draft" || voucher.status === "pending");
  const loadAtts = useCallback(() => {
    if (!token) return;
    api.kho.voucherAttachments(token, voucher.id).then((r) => setAtts(r.items)).catch(() => {});
  }, [token, voucher.id]);
  useEffect(() => { loadAtts(); }, [loadAtts]);

  async function onUploadFiles(list: FileList | null) {
    if (!token || !list || !list.length) return;
    setAttBusy(true); setError(null);
    try { for (const f of Array.from(list)) await api.kho.uploadVoucherAttachment(token, voucher.id, f); loadAtts(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Tải file thất bại."); }
    finally { setAttBusy(false); }
  }
  async function onDeleteAtt(aid: number) {
    if (!token) return;
    setAttBusy(true); setError(null);
    try { await api.kho.deleteVoucherAttachment(token, voucher.id, aid); loadAtts(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Xóa file thất bại."); }
    finally { setAttBusy(false); }
  }

  const showCost = spec.showCost && canPrice;
  const totalQty = voucher.lines.reduce((s, l) => s + Number(l.quantity), 0);
  const totalValue = voucher.lines.reduce((s, l) => s + Number(l.quantity) * Number(l.unit_cost || 0), 0);

  // In phiếu kho: logo cty + thông tin phiếu + bảng sản phẩm + ô ký. Ảnh dùng URL tuyệt đối để
  // cửa sổ in (about:blank) tải được. In sau khi ảnh/DOM load xong (body onload).
  function onPrint() {
    const w = window.open("", "_blank", "width=880,height=1000");
    if (!w) return;
    const logoAbs = new URL(logoUrl, window.location.href).href;
    const info: [string, string][] = [
      ["Mã số", escHtml(voucher.code)],
      ["Loại phiếu", escHtml(t?.name ?? voucher.voucher_type_id)],
      ["Ngày phiếu", fmtDate(voucher.doc_date)],
      ["Kho", escHtml(khoText)],
      [spec.partnerKind ? spec.partnerLabel : "Đối tượng", escHtml(voucher.partner_ref)],
      ...(spec.refLabel ? [[spec.refLabel, escHtml(voucher.note)] as [string, string]] : []),
      ["Người nhập", escHtml(voucher.created_by_name)],
      ["Ngày tạo", fmtDateTime(voucher.created_at)],
      ...(voucher.approved_at ? [["Ngày duyệt", fmtDateTime(voucher.approved_at)] as [string, string]] : []),
      ...(voucher.reason ? [["Diễn giải", escHtml(voucher.reason)] as [string, string]] : []),
    ];
    const lineRows = voucher.lines.map((l, i) => {
      const m = matById.get(l.material_id);
      const val = Number(l.quantity) * Number(l.unit_cost || 0);
      return `<tr>
        <td class="c">${i + 1}</td>
        <td>${escHtml(m ? `${m.code} · ${m.name}` : `#${l.material_id}`)}</td>
        <td>${escHtml(l.uom || "—")}</td>
        <td class="r">${fmtNum(Number(l.quantity))}</td>
        ${showCost ? `<td class="r">${l.unit_cost != null ? fmtNum(Number(l.unit_cost)) : "—"}</td><td class="r">${l.unit_cost != null ? fmtNum(val) : "—"}</td>` : ""}
        ${spec.showStatus ? `<td>${escHtml(l.status_id != null ? statusById.get(l.status_id) ?? "—" : "—")}</td>` : ""}
        <td>${escHtml(l.note || "—")}</td>
      </tr>`;
    }).join("");
    const colspanBeforeQty = 3; // #, tên, ĐVT
    w.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>${escHtml(voucher.code)}</title>
<style>
  * { font-family: 'Segoe UI', Arial, sans-serif; box-sizing: border-box; }
  body { margin: 28px; color: #1a1a1a; }
  .head { display: flex; align-items: center; gap: 14px; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 16px; }
  .head img { height: 52px; }
  .company { font-size: 17px; font-weight: 700; }
  .company small { display: block; font-weight: 400; color: #666; font-size: 12px; }
  h1 { font-size: 19px; text-align: center; margin: 6px 0 2px; text-transform: uppercase; }
  .sub { text-align: center; color: #444; margin-bottom: 16px; font-size: 13px; }
  table.info { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
  table.info td { padding: 4px 8px; font-size: 13px; vertical-align: top; }
  table.info td.k { width: 150px; color: #555; }
  table.info td.v { font-weight: 600; }
  table.lines { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  table.lines th, table.lines td { border: 1px solid #bbb; padding: 6px 8px; font-size: 13px; }
  table.lines th { background: #f2f0ec; text-align: left; }
  td.r, th.r { text-align: right; } td.c, th.c { text-align: center; width: 34px; }
  tfoot td { font-weight: 700; }
  .sign { display: flex; justify-content: space-around; margin-top: 44px; text-align: center; font-size: 13px; }
  .sign div { width: 30%; }
  @media print { body { margin: 12mm; } }
</style></head>
<body onload="window.print()" onafterprint="window.close()">
  <div class="head">
    <img src="${logoAbs}" alt="logo">
    <div class="company">CÔNG TY SAO VIỆT NHẬT<small>Phiếu kho</small></div>
  </div>
  <h1>${escHtml(t?.name ?? "Phiếu kho")}</h1>
  <div class="sub">Số: <strong>${escHtml(voucher.code)}</strong> · Trạng thái: ${escHtml(STATUS_LABEL[voucher.status] ?? voucher.status)}</div>
  <table class="info"><tbody>
    ${info.map(([k, v]) => `<tr><td class="k">${k}</td><td class="v">${v}</td></tr>`).join("")}
  </tbody></table>
  <table class="lines">
    <thead><tr>
      <th class="c">#</th><th>Tên sản phẩm</th><th>ĐVT</th><th class="r">${escHtml(spec.qtyLabel)}</th>
      ${showCost ? `<th class="r">Đơn giá</th><th class="r">Thành tiền</th>` : ""}
      ${spec.showStatus ? `<th>Trạng thái</th>` : ""}
      <th>Ghi chú</th>
    </tr></thead>
    <tbody>${lineRows}</tbody>
    <tfoot><tr>
      <td colspan="${colspanBeforeQty}">Tổng cộng</td>
      <td class="r">${fmtNum(totalQty)}</td>
      ${showCost ? `<td></td><td class="r">${fmtNum(totalValue)}</td>` : ""}
      ${spec.showStatus ? `<td></td>` : ""}
      <td></td>
    </tr></tfoot>
  </table>
  <div class="sign">
    <div>Người lập phiếu<br><br><br>………………</div>
    <div>Thủ kho<br><br><br>………………</div>
    <div>Kế toán / Duyệt<br><br><br>………………</div>
  </div>
</body></html>`);
    w.document.close();
  }

  async function act(fn: () => Promise<VoucherRow>) {
    if (!token || busy) return;
    setBusy(true); setError(null);
    try { await fn(); onChanged(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Thao tác thất bại."); setBusy(false); }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 960, width: "94%" }}>
        <div className="md-page__dialog-head">
          <h2>Chi tiết phiếu {voucher.code}</h2>
          <span className={`md-page__status-badge ${voucher.status === "posted" ? "is-active" : "is-inactive"}`} style={{ marginLeft: 10 }}>
            {STATUS_LABEL[voucher.status] ?? voucher.status}
          </span>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 28, alignItems: "start" }}>
            {/* Khối đối tượng — nhãn theo loại phiếu (NCC / Khách hàng / LSX / Bộ phận) */}
            <section>
              <h3 className="md-page__section-title">{spec.partnerKind ? spec.partnerLabel : "Đối tượng"}</h3>
              {voucher.partner_ref ? (
                <div style={{ fontSize: 17, fontWeight: 600, margin: "6px 0" }}>{voucher.partner_ref}</div>
              ) : (
                <p className="md-page__muted" style={{ margin: "6px 0" }}>— Nội bộ / không có đối tượng —</p>
              )}
              {voucher.reason && <DetailRow label="Diễn giải" value={voucher.reason} />}
            </section>

            {/* Thông tin phiếu */}
            <section>
              <h3 className="md-page__section-title">Thông tin phiếu #{voucher.id}</h3>
              <DetailRow label="Mã số" value={<span className="md-page__mono">{voucher.code}</span>} />
              <DetailRow label="Loại phiếu" value={t?.name ?? voucher.voucher_type_id} />
              {spec.refLabel && <DetailRow label={spec.refLabel} value={voucher.note || "—"} />}
              <DetailRow label="Ngày phiếu" value={fmtDate(voucher.doc_date)} />
              <DetailRow label="Kho" value={khoText} />
              <DetailRow label="Người nhập" value={voucher.created_by_name || "—"} />
              <DetailRow label="Ngày tạo" value={fmtDateTime(voucher.created_at)} />
              {voucher.approved_at && <DetailRow label="Ngày duyệt" value={fmtDateTime(voucher.approved_at)} />}
            </section>
          </div>

          <h3 className="md-page__section-title" style={{ marginTop: 20 }}>Sản phẩm</h3>
          <div className="md-page__tablewrap" style={{ marginTop: 4 }}>
            <table className="md-page__table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th>
                  <th>Tên sản phẩm</th>
                  <th>ĐVT</th>
                  <th style={{ textAlign: "right" }}>{spec.qtyLabel}</th>
                  {showCost && <th style={{ textAlign: "right" }}>Đơn giá</th>}
                  {showCost && <th style={{ textAlign: "right" }}>Thành tiền</th>}
                  {spec.showStatus && <th>Trạng thái</th>}
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {voucher.lines.map((l, i) => {
                  const m = matById.get(l.material_id);
                  return (
                    <tr key={l.id}>
                      <td>{i + 1}</td>
                      <td>{m ? `${m.code} · ${m.name}` : `#${l.material_id}`}</td>
                      <td>{l.uom || "—"}</td>
                      <td style={{ textAlign: "right" }}>{fmtNum(Number(l.quantity))}</td>
                      {showCost && <td style={{ textAlign: "right" }}>{l.unit_cost != null ? fmtNum(Number(l.unit_cost)) : "—"}</td>}
                      {showCost && <td style={{ textAlign: "right" }}>{l.unit_cost != null ? fmtNum(Number(l.quantity) * Number(l.unit_cost)) : "—"}</td>}
                      {spec.showStatus && <td>{l.status_id != null ? statusById.get(l.status_id) ?? "—" : "—"}</td>}
                      <td>{l.note || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3} style={{ fontWeight: 600 }}>Tổng cộng</td>
                  <td style={{ textAlign: "right", fontWeight: 600 }}>{fmtNum(totalQty)}</td>
                  {showCost && <td />}
                  {showCost && <td style={{ textAlign: "right", fontWeight: 600 }}>{fmtNum(totalValue)}</td>}
                  <td colSpan={(spec.showStatus ? 1 : 0) + 1} />
                </tr>
              </tfoot>
            </table>
          </div>

          <h3 className="md-page__section-title" style={{ marginTop: 20 }}>Đính kèm (chứng từ)</h3>
          {atts.length === 0 ? (
            <p className="md-page__muted" style={{ margin: "4px 0" }}>Chưa có file đính kèm.</p>
          ) : (
            <ul className="md-page__filelist">
              {atts.map((a) => (
                <li key={a.id}>
                  <a className="md-page__file-name" href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer">📎 {a.file_name}</a>
                  {canEditAtt && <button type="button" className="md-page__file-x" disabled={attBusy} onClick={() => onDeleteAtt(a.id)}>✕</button>}
                </li>
              ))}
            </ul>
          )}
          {canEditAtt && (
            <input className="input" type="file" multiple disabled={attBusy} style={{ marginTop: 6 }}
              onChange={(e) => { onUploadFiles(e.target.files); e.target.value = ""; }} />
          )}

          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onPrint}>🖨 In phiếu</Button>
            <div style={{ flex: 1 }} />
            {voucher.status === "draft" && canCreate && (
              <>
                <Button variant="danger" onClick={() => act(() => api.kho.cancelVoucher(token!, voucher.id))} loading={busy}>Hủy phiếu</Button>
                <Button variant="primary" onClick={() => act(() => api.kho.submitVoucher(token!, voucher.id))} loading={busy}>Nộp phiếu</Button>
              </>
            )}
            {voucher.status === "pending" && (
              <>
                {canCreate && <Button variant="danger" onClick={() => act(() => api.kho.cancelVoucher(token!, voucher.id))} loading={busy}>Hủy</Button>}
                {canApprove && <Button variant="primary" onClick={() => act(() => api.kho.approveVoucher(token!, voucher.id))} loading={busy}>Duyệt & ghi sổ</Button>}
              </>
            )}
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
