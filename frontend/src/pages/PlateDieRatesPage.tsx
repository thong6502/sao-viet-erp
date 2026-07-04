import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import {
  ApiError,
  api,
  type PlateDieRateRow,
  type PlateDieRateInput,
  type MachineRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const KEM_TYPE = "ban_kem_offset";
const DIE_TYPES = [
  { value: "khuon_be", label: "Khuôn bế", tech: "be" },
  { value: "khuon_ep_kim", label: "Khuôn ép kim", tech: "ep_kim" },
  { value: "khuon_dap_noi", label: "Khuôn dập nổi", tech: "dap_noi" },
  { value: "khuon_khac", label: "Khuôn khác", tech: "be" },
];
const DIE_LABEL: Record<string, string> = Object.fromEntries(DIE_TYPES.map((d) => [d.value, d.label]));
const KEM_KINDS = [
  { value: "ctp", label: "CTP" },
  { value: "ps", label: "PS" },
  { value: "thuong", label: "Kẽm thường" },
];
const TECH_LABEL: Record<string, string> = {
  offset: "In Offset", flexo: "In Flexo", be: "Bế", ep_kim: "Ép kim", dap_noi: "Dập nổi",
};
const PRICING_METHODS = [
  { value: "fixed", label: "Cố định" },
  { value: "area", label: "Theo diện tích (cm²)" },
  { value: "perimeter", label: "Theo chu vi (mét dao)" },
  { value: "size_tier", label: "Theo bậc kích thước" },
  { value: "manual", label: "Nhập tay" },
];
const PM_LABEL: Record<string, string> = Object.fromEntries(PRICING_METHODS.map((p) => [p.value, p.label]));
const REUSE_METHODS = [
  { value: "zero", label: "Không tính phí (0đ)" },
  { value: "maintenance_fee", label: "Phí bảo trì khuôn" },
  { value: "manual", label: "Nhập tay" },
];

const money = (n: number | null | undefined) => (n == null ? "—" : `${n.toLocaleString("vi-VN")}đ`);
const num = (s: string) => { const n = Number(s); return Number.isFinite(n) ? n : 0; };
const today = () => new Date().toISOString().split("T")[0];

export function PlateDieRatesPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<"kem" | "khuon">("kem");
  const [rows, setRows] = useState<PlateDieRateRow[]>([]);
  const [machines, setMachines] = useState<MachineRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [currentOnly, setCurrentOnly] = useState(true);

  const [formRow, setFormRow] = useState<PlateDieRateRow | null | undefined>(undefined); // undefined=closed, null=create, row=version
  const [closing, setClosing] = useState<PlateDieRateRow | null>(null);
  const [effectiveTo, setEffectiveTo] = useState("");
  const [deleting, setDeleting] = useState<PlateDieRateRow | null>(null);
  const [historyOf, setHistoryOf] = useState<PlateDieRateRow | null>(null);

  const machineName = useCallback((id: number) => machines.find((m) => m.id === id)?.name ?? `#${id}`, [machines]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    const is_active = statusFilter === "active" ? true : statusFilter === "inactive" ? false : null;
    api.plateDieRates
      .list(token, { q: q || null, is_active, current_only: currentOnly, size: 200 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được bảng giá kẽm/khuôn.");
      })
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, currentOnly]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!token) return;
    api.machines.list(token, { size: 200 }).then((r) => setMachines(r.items)).catch(() => {});
  }, [token]);

  const shown = useMemo(
    () => rows.filter((r) => (tab === "kem" ? r.plate_type === KEM_TYPE : r.plate_type !== KEM_TYPE)),
    [rows, tab],
  );

  async function handleClone(row: PlateDieRateRow) {
    if (!token) return;
    try { await api.plateDieRates.clone(token, row.id); load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Không sao chép được."); }
  }
  async function handleClose(e: FormEvent) {
    e.preventDefault();
    if (!token || !closing) return;
    try { await api.plateDieRates.close(token, closing.id, effectiveTo); setClosing(null); load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Không đóng được."); }
  }
  async function handleDelete() {
    if (!token || !deleting) return;
    try { await api.plateDieRates.remove(token, deleting.id); setDeleting(null); load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Không xóa được."); setDeleting(null); }
  }

  if (forbidden) {
    return <div className="md-page"><div className="banner banner--error">Bạn không có quyền xem Đơn giá kẽm & khuôn (403).</div></div>;
  }
  const todayStr = today();

  return (
    <div className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Đơn giá kẽm & khuôn</h1>
        <p className="md-page__sub">Đơn giá chế bản kẽm offset (theo máy) và khuôn bế / ép kim / dập nổi (theo cách tính).</p>
      </header>

      {/* Tabs */}
      <div className="md-page__tabbar" style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {(["kem", "khuon"] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)}
            className={`btn ${tab === t ? "btn--primary" : "btn--ghost"}`}>
            {t === "kem" ? "Đơn giá kẽm" : "Đơn giá khuôn"}
          </button>
        ))}
      </div>

      {error && <div className="banner banner--error" role="alert"><span>{error}</span>
        <button type="button" className="btn btn--ghost" onClick={() => { setError(null); load(); }}>Tải lại</button></div>}

      {/* Toolbar */}
      <div className="md-page__toolbar">
        <input className="input md-page__filter" placeholder="Tìm mã / tên…" value={q}
          onChange={(e) => setQ(e.target.value)} style={{ width: 220 }} />
        <div className="md-page__filter">
          <select className="input select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Lọc trạng thái">
            <option value="">-- Trạng thái --</option>
            <option value="active">Đang chạy</option>
            <option value="inactive">Đã đóng / tương lai</option>
          </select>
        </div>
        <div className="md-page__toggle-wrap" style={{ padding: "0 8px" }}>
          <input type="checkbox" id="pd-current" checked={currentOnly} onChange={(e) => setCurrentOnly(e.target.checked)} />
          <label htmlFor="pd-current">Chỉ bản hiện hành</label>
        </div>
        <div className="md-page__toolbar-spacer" />
        <Button variant="primary" onClick={() => setFormRow(null)}>
          + Thêm {tab === "kem" ? "bảng giá kẽm" : "bảng giá khuôn"}
        </Button>
      </div>

      {/* Table */}
      <div className="card md-page__tablewrap">
        {loading ? (
          <div style={{ padding: 40, textAlign: "center" }}>Đang tải…</div>
        ) : shown.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center" }} className="md-page__muted">Chưa có bảng giá nào.</div>
        ) : tab === "kem" ? (
          <table className="md-page__table">
            <thead><tr>
              <th>Mã</th><th>Tên</th><th>Loại kẽm</th><th>Khổ kẽm (mm)</th><th>Máy áp dụng</th>
              <th>Đơn giá/bản</th><th>NCC</th><th>Áp dụng từ</th><th>Trạng thái</th><th className="md-page__actions-col">Thao tác</th>
            </tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td className="md-page__mono">{r.code}</td>
                  <td><strong>{r.name}</strong></td>
                  <td>{KEM_KINDS.find((k) => k.value === r.plate_kind)?.label ?? <span className="md-page__muted">—</span>}</td>
                  <td>{r.plate_width_mm && r.plate_height_mm ? `${r.plate_width_mm}×${r.plate_height_mm}` : <span className="md-page__muted">—</span>}</td>
                  <td>{!r.machine_ids || r.machine_ids.length === 0
                    ? <span className="md-page__muted">Mọi máy</span>
                    : <div className="md-page__tag-group">{r.machine_ids.map((id) => <span key={id} className="md-page__tag-tech">{machineName(id)}</span>)}</div>}</td>
                  <td className="md-page__price">{money(r.unit_price)}</td>
                  <td>{r.supplier ?? <span className="md-page__muted">—</span>}</td>
                  <td>{r.effective_from}</td>
                  <td><StatusBadge r={r} /></td>
                  <td className="md-page__actions-col"><RowActions r={r} todayStr={todayStr}
                    onVersion={() => setFormRow(r)} onClone={() => handleClone(r)}
                    onHistory={() => setHistoryOf(r)} onClose={() => { setClosing(r); setEffectiveTo(todayStr); }}
                    onDelete={() => setDeleting(r)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="md-page__table">
            <thead><tr>
              <th>Mã</th><th>Tên</th><th>Loại khuôn</th><th>Công đoạn</th><th>Cách tính</th>
              <th>Đơn giá</th><th>Min</th><th>Dùng lại</th><th>Áp dụng từ</th><th>Trạng thái</th><th className="md-page__actions-col">Thao tác</th>
            </tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td className="md-page__mono">{r.code}</td>
                  <td><strong>{r.name}</strong></td>
                  <td><span className="md-page__tag-calc">{DIE_LABEL[r.plate_type] ?? r.plate_type}</span></td>
                  <td>{TECH_LABEL[r.technology] ?? r.technology}</td>
                  <td>{PM_LABEL[r.pricing_method] ?? r.pricing_method}</td>
                  <td className="md-page__price">
                    {r.pricing_method === "area" ? `${money(r.unit_price_area)}/cm²`
                      : r.pricing_method === "perimeter" ? `${money(r.unit_price_perimeter)}/m`
                      : money(r.unit_price)}
                  </td>
                  <td>{money(r.min_charge)}</td>
                  <td><span className={r.reusable ? "md-page__tag-calc" : "md-page__muted"}>{r.reusable ? "Có" : "Không"}</span></td>
                  <td>{r.effective_from}</td>
                  <td><StatusBadge r={r} /></td>
                  <td className="md-page__actions-col"><RowActions r={r} todayStr={todayStr}
                    onVersion={() => setFormRow(r)} onClone={() => handleClone(r)}
                    onHistory={() => setHistoryOf(r)} onClose={() => { setClosing(r); setEffectiveTo(todayStr); }}
                    onDelete={() => setDeleting(r)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {formRow !== undefined && (
        <PlateDieForm tab={tab} existing={formRow} machines={machines}
          onClose={() => setFormRow(undefined)} onSaved={() => { setFormRow(undefined); load(); }} />
      )}

      {closing && (
        <div className="md-page__overlay"><form className="card md-page__dialog md-page__dialog--sm" onSubmit={handleClose}>
          <div className="md-page__dialog-head"><h2>Đóng hiệu lực: {closing.code}</h2>
            <button type="button" className="md-page__close" onClick={() => setClosing(null)}>×</button></div>
          <div className="md-page__dialog-body">
            <label className="field"><span className="field__label">Ngày kết thúc hiệu lực (không gồm ngày này)</span>
              <input type="date" className="input" value={effectiveTo} onChange={(e) => setEffectiveTo(e.target.value)} required /></label>
            <div className="md-page__dialog-actions">
              <Button variant="ghost" type="button" onClick={() => setClosing(null)}>Hủy</Button>
              <Button variant="danger" type="submit">Xác nhận đóng</Button>
            </div>
          </div>
        </form></div>
      )}

      {deleting && (
        <div className="md-page__overlay"><div className="card md-page__dialog md-page__dialog--sm">
          <div className="md-page__dialog-head"><h2>Xác nhận xóa</h2>
            <button type="button" className="md-page__close" onClick={() => setDeleting(null)}>×</button></div>
          <div className="md-page__dialog-body">
            <p>Xóa bảng giá tương lai <strong>{deleting.code}</strong>? (Chỉ xóa được bản chưa hiệu lực.)</p>
            <div className="md-page__dialog-actions">
              <Button variant="ghost" onClick={() => setDeleting(null)}>Hủy</Button>
              <Button variant="danger" onClick={handleDelete}>Xác nhận xóa</Button>
            </div>
          </div>
        </div></div>
      )}

      {historyOf && <HistoryDialog row={historyOf} onClose={() => setHistoryOf(null)} />}
    </div>
  );
}

function StatusBadge({ r }: { r: PlateDieRateRow }) {
  return <span className={`md-page__status-badge ${r.is_active && !r.effective_to ? "is-active" : "is-inactive"}`}>
    {r.effective_to ? "Đã đóng" : r.is_active ? "Đang chạy" : "Tạm ngưng"}
  </span>;
}

function RowActions({ r, todayStr, onVersion, onClone, onHistory, onClose, onDelete }: {
  r: PlateDieRateRow; todayStr: string;
  onVersion: () => void; onClone: () => void; onHistory: () => void; onClose: () => void; onDelete: () => void;
}) {
  return (
    <>
      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={onVersion}>Tạo version</button>
      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={onClone}>Sao chép</button>
      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={onHistory}>Lịch sử</button>
      {r.is_active && !r.effective_to && (
        <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={onClose}>Đóng</button>
      )}
      {r.effective_from > todayStr && (
        <button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={onDelete}>Xóa</button>
      )}
    </>
  );
}

const sectionHead: CSSProperties = {
  margin: "18px 0 8px", fontSize: 13, fontWeight: 700, textTransform: "uppercase",
  letterSpacing: ".04em", color: "var(--text-muted, #64748b)",
};

function PlateDieForm({ tab, existing, machines, onClose, onSaved }: {
  tab: "kem" | "khuon"; existing: PlateDieRateRow | null; machines: MachineRow[];
  onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const isVersion = existing != null;

  const [code, setCode] = useState(existing?.code ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [plateType, setPlateType] = useState(existing?.plate_type ?? (tab === "kem" ? KEM_TYPE : "khuon_be"));
  const [technology, setTechnology] = useState(existing?.technology ?? (tab === "kem" ? "offset" : "be"));
  const [unit] = useState(existing?.unit ?? (tab === "kem" ? "ban" : "bo"));
  const [plateKind, setPlateKind] = useState(existing?.plate_kind ?? "ctp");
  const [plateW, setPlateW] = useState(existing?.plate_width_mm ? String(existing.plate_width_mm) : "");
  const [plateH, setPlateH] = useState(existing?.plate_height_mm ? String(existing.plate_height_mm) : "");
  const [machineIds, setMachineIds] = useState<number[]>(existing?.machine_ids ?? []);
  const [unitPrice, setUnitPrice] = useState(existing ? String(existing.unit_price) : "");
  const [setupFee, setSetupFee] = useState(existing ? String(existing.setup_fee) : "0");
  const [minCharge, setMinCharge] = useState(existing ? String(existing.min_charge) : "0");
  const [pricingMethod, setPricingMethod] = useState(existing?.pricing_method ?? "fixed");
  const [priceArea, setPriceArea] = useState(existing ? String(existing.unit_price_area) : "0");
  const [pricePerimeter, setPricePerimeter] = useState(existing ? String(existing.unit_price_perimeter) : "0");
  const [maxCharge, setMaxCharge] = useState(existing?.max_charge != null ? String(existing.max_charge) : "");
  const [reusable, setReusable] = useState(existing?.reusable ?? false);
  const [reuseMethod, setReuseMethod] = useState(existing?.reuse_price_method ?? "zero");
  const [maintenanceFee, setMaintenanceFee] = useState(existing ? String(existing.maintenance_fee) : "0");
  const [supplier, setSupplier] = useState(existing?.supplier ?? "");
  const [leadTime, setLeadTime] = useState(existing ? String(existing.lead_time_days) : "0");
  const [transportFee, setTransportFee] = useState(existing ? String(existing.transport_fee) : "0");
  const [moq, setMoq] = useState(existing ? String(existing.moq) : "0");
  const [effectiveFrom, setEffectiveFrom] = useState(today());

  // Test box
  const [tColors, setTColors] = useState("4");
  const [tSets, setTSets] = useState("1");
  const [tForms, setTForms] = useState("1");
  const [tArea, setTArea] = useState("120");
  const [tPerim, setTPerim] = useState("2");

  const [saving, setSaving] = useState(false);
  const [vErr, setVErr] = useState<string | null>(null);

  function toggleMachine(id: number) {
    setMachineIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  // Test results
  const kemPieces = num(tColors) * num(tSets) * num(tForms);
  const kemCost = kemPieces * num(unitPrice);
  const dieCost = useMemo(() => {
    let c = 0;
    if (pricingMethod === "area") c = num(tArea) * num(priceArea);
    else if (pricingMethod === "perimeter") c = num(tPerim) * num(pricePerimeter);
    else c = num(unitPrice);
    const mn = num(minCharge);
    if (c < mn) c = mn;
    if (maxCharge && c > num(maxCharge)) c = num(maxCharge);
    return c;
  }, [pricingMethod, tArea, priceArea, tPerim, pricePerimeter, unitPrice, minCharge, maxCharge]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setVErr(null);
    if (!isVersion && !code.trim()) { setVErr("Mã bảng giá không được trống."); return; }
    if (!name.trim()) { setVErr("Tên bảng giá không được trống."); return; }
    const payload: PlateDieRateInput = {
      code: code.trim() || undefined,
      name: name.trim(),
      plate_type: plateType,
      technology,
      unit,
      unit_price: num(unitPrice),
      setup_fee: num(setupFee),
      min_charge: num(minCharge),
      effective_from: effectiveFrom,
      is_active: true,
    };
    if (tab === "kem") {
      payload.plate_kind = plateKind;
      payload.plate_width_mm = plateW ? num(plateW) : null;
      payload.plate_height_mm = plateH ? num(plateH) : null;
      payload.machine_ids = machineIds.length ? machineIds : null;
      payload.pricing_method = "fixed";
    } else {
      payload.pricing_method = pricingMethod;
      payload.unit_price_area = num(priceArea);
      payload.unit_price_perimeter = num(pricePerimeter);
      payload.max_charge = maxCharge ? num(maxCharge) : null;
      payload.reusable = reusable;
      payload.reuse_price_method = reusable ? reuseMethod : null;
      payload.maintenance_fee = num(maintenanceFee);
      payload.supplier = supplier.trim() || null;
      payload.lead_time_days = num(leadTime);
      payload.transport_fee = num(transportFee);
      payload.moq = num(moq);
    }
    setSaving(true);
    try {
      if (isVersion && existing) await api.plateDieRates.createVersion(token, existing.id, payload);
      else await api.plateDieRates.create(token, payload);
      onSaved();
    } catch (err) {
      setVErr(err instanceof ApiError ? err.message : "Lưu thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay">
      <form className="card md-page__dialog" style={{ maxWidth: 720 }} onSubmit={submit}>
        <div className="md-page__dialog-head">
          <h2>{isVersion ? `Tạo version mới: ${existing?.code}` : (tab === "kem" ? "Thêm bảng giá kẽm" : "Thêm bảng giá khuôn")}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>×</button>
        </div>
        <div className="md-page__dialog-body">
          {/* Khối 1 — chung */}
          <div style={sectionHead}>1 · Thông tin chung</div>
          <div className="md-page__form-grid">
            <label className="field"><span className="field__label">Mã bảng giá {isVersion ? "" : "*"}</span>
              <input className="input" value={code} disabled={isVersion} onChange={(e) => setCode(e.target.value)}
                placeholder={tab === "kem" ? "VD: PLATE_102_CTP" : "VD: DIE_BOX_STD"} /></label>
            <label className="field"><span className="field__label">Tên bảng giá *</span>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
            {tab === "khuon" && (
              <>
                <label className="field"><span className="field__label">Loại khuôn</span>
                  <select className="input select" value={plateType} onChange={(e) => {
                    setPlateType(e.target.value);
                    const d = DIE_TYPES.find((x) => x.value === e.target.value);
                    if (d) setTechnology(d.tech);
                  }}>
                    {DIE_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                  </select></label>
                <label className="field"><span className="field__label">Công đoạn áp dụng</span>
                  <select className="input select" value={technology} onChange={(e) => setTechnology(e.target.value)}>
                    {["be", "ep_kim", "dap_noi"].map((t) => <option key={t} value={t}>{TECH_LABEL[t]}</option>)}
                  </select></label>
              </>
            )}
            {tab === "kem" && (
              <label className="field"><span className="field__label">Loại kẽm</span>
                <select className="input select" value={plateKind} onChange={(e) => setPlateKind(e.target.value)}>
                  {KEM_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select></label>
            )}
          </div>

          {tab === "kem" ? (
            <>
              {/* Kẽm — khổ + máy + đơn giá */}
              <div style={sectionHead}>2 · Khổ kẽm & máy áp dụng</div>
              <div className="md-page__form-grid">
                <label className="field"><span className="field__label">Khổ kẽm rộng (mm)</span>
                  <input className="input" type="number" value={plateW} onChange={(e) => setPlateW(e.target.value)} placeholder="VD: 605" /></label>
                <label className="field"><span className="field__label">Khổ kẽm dài (mm)</span>
                  <input className="input" type="number" value={plateH} onChange={(e) => setPlateH(e.target.value)} placeholder="VD: 745" /></label>
              </div>
              <div className="field">
                <span className="field__label">Máy áp dụng (bỏ trống = mọi máy)</span>
                <div className="md-page__toggle-wrap" style={{ gap: 16, flexWrap: "wrap" }}>
                  {machines.length === 0 && <span className="md-page__muted">Chưa có máy.</span>}
                  {machines.map((m) => (
                    <label key={m.id} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      <input type="checkbox" checked={machineIds.includes(m.id)} onChange={() => toggleMachine(m.id)} /> {m.name}
                    </label>
                  ))}
                </div>
              </div>
              <div style={sectionHead}>3 · Đơn giá</div>
              <div className="md-page__form-grid">
                <label className="field"><span className="field__label">Đơn giá 1 bản kẽm (đ) *</span>
                  <input className="input" type="number" min="0" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} placeholder="VD: 100000" /></label>
                <label className="field"><span className="field__label">Phí setup (đ)</span>
                  <input className="input" type="number" min="0" value={setupFee} onChange={(e) => setSetupFee(e.target.value)} /></label>
                <label className="field"><span className="field__label">Phí tối thiểu (đ)</span>
                  <input className="input" type="number" min="0" value={minCharge} onChange={(e) => setMinCharge(e.target.value)} /></label>
                <label className="field"><span className="field__label">Nhà cung cấp</span>
                  <input className="input" value={supplier} onChange={(e) => setSupplier(e.target.value)} /></label>
              </div>
              {/* Test kẽm */}
              <div style={sectionHead}>Test tiền kẽm</div>
              <div className="card" style={{ padding: 14, background: "var(--surface-2, #f8fafc)" }}>
                <div className="md-page__form-grid">
                  <label className="field"><span className="field__label">Số màu</span>
                    <input className="input" type="number" value={tColors} onChange={(e) => setTColors(e.target.value)} /></label>
                  <label className="field"><span className="field__label">Số bộ kẽm</span>
                    <input className="input" type="number" value={tSets} onChange={(e) => setTSets(e.target.value)} /></label>
                  <label className="field"><span className="field__label">Số form/tay</span>
                    <input className="input" type="number" value={tForms} onChange={(e) => setTForms(e.target.value)} /></label>
                </div>
                <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.7 }}>
                  Số bản kẽm = {tColors} × {tSets} × {tForms} = <strong>{kemPieces} bản</strong><br />
                  Tiền kẽm = {kemPieces} × {money(num(unitPrice))} = <strong style={{ fontSize: 15 }}>{money(kemCost)}</strong>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Khuôn — cách tính */}
              <div style={sectionHead}>2 · Cách tính giá khuôn</div>
              <div className="md-page__form-grid">
                <label className="field"><span className="field__label">Cách tính</span>
                  <select className="input select" value={pricingMethod} onChange={(e) => setPricingMethod(e.target.value)}>
                    {PRICING_METHODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                  </select></label>
                {(pricingMethod === "fixed" || pricingMethod === "size_tier" || pricingMethod === "manual") && (
                  <label className="field"><span className="field__label">Đơn giá cố định (đ)</span>
                    <input className="input" type="number" min="0" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} placeholder="VD: 800000" /></label>
                )}
                {pricingMethod === "area" && (
                  <label className="field"><span className="field__label">Đơn giá theo diện tích (đ/cm²)</span>
                    <input className="input" type="number" min="0" value={priceArea} onChange={(e) => setPriceArea(e.target.value)} placeholder="VD: 2000" /></label>
                )}
                {pricingMethod === "perimeter" && (
                  <label className="field"><span className="field__label">Đơn giá theo chu vi (đ/mét dao)</span>
                    <input className="input" type="number" min="0" value={pricePerimeter} onChange={(e) => setPricePerimeter(e.target.value)} placeholder="VD: 50000" /></label>
                )}
                <label className="field"><span className="field__label">Phí tối thiểu (đ)</span>
                  <input className="input" type="number" min="0" value={minCharge} onChange={(e) => setMinCharge(e.target.value)} /></label>
                <label className="field"><span className="field__label">Phí tối đa (đ, tùy chọn)</span>
                  <input className="input" type="number" min="0" value={maxCharge} onChange={(e) => setMaxCharge(e.target.value)} /></label>
              </div>

              {/* Dùng lại */}
              <div style={sectionHead}>3 · Dùng lại khuôn cũ</div>
              <div className="md-page__toggle-wrap"><input type="checkbox" id="pd-reuse" checked={reusable} onChange={(e) => setReusable(e.target.checked)} />
                <label htmlFor="pd-reuse">Cho phép dùng lại khuôn cũ</label></div>
              {reusable && (
                <div className="md-page__form-grid" style={{ marginTop: 8 }}>
                  <label className="field"><span className="field__label">Khi dùng lại, tính phí</span>
                    <select className="input select" value={reuseMethod} onChange={(e) => setReuseMethod(e.target.value)}>
                      {REUSE_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </select></label>
                  {reuseMethod === "maintenance_fee" && (
                    <label className="field"><span className="field__label">Phí bảo trì khuôn (đ)</span>
                      <input className="input" type="number" min="0" value={maintenanceFee} onChange={(e) => setMaintenanceFee(e.target.value)} /></label>
                  )}
                </div>
              )}

              {/* NCC */}
              <div style={sectionHead}>4 · Nhà cung cấp</div>
              <div className="md-page__form-grid">
                <label className="field"><span className="field__label">Nhà cung cấp</span>
                  <input className="input" value={supplier} onChange={(e) => setSupplier(e.target.value)} /></label>
                <label className="field"><span className="field__label">Lead time (ngày)</span>
                  <input className="input" type="number" min="0" value={leadTime} onChange={(e) => setLeadTime(e.target.value)} /></label>
                <label className="field"><span className="field__label">Phí vận chuyển (đ)</span>
                  <input className="input" type="number" min="0" value={transportFee} onChange={(e) => setTransportFee(e.target.value)} /></label>
                <label className="field"><span className="field__label">MOQ</span>
                  <input className="input" type="number" min="0" value={moq} onChange={(e) => setMoq(e.target.value)} /></label>
              </div>

              {/* Test khuôn */}
              <div style={sectionHead}>Test tiền khuôn</div>
              <div className="card" style={{ padding: 14, background: "var(--surface-2, #f8fafc)" }}>
                {pricingMethod === "area" && (
                  <label className="field"><span className="field__label">Diện tích ép (cm²)</span>
                    <input className="input" type="number" value={tArea} onChange={(e) => setTArea(e.target.value)} /></label>
                )}
                {pricingMethod === "perimeter" && (
                  <label className="field"><span className="field__label">Chu vi dao (mét)</span>
                    <input className="input" type="number" value={tPerim} onChange={(e) => setTPerim(e.target.value)} /></label>
                )}
                <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.7 }}>
                  Cách tính: <strong>{PM_LABEL[pricingMethod]}</strong><br />
                  {pricingMethod === "area" && <>Công thức: max({tArea} × {money(num(priceArea))}, min {money(num(minCharge))})<br /></>}
                  {pricingMethod === "perimeter" && <>Công thức: max({tPerim} × {money(num(pricePerimeter))}, min {money(num(minCharge))})<br /></>}
                  Tiền khuôn = <strong style={{ fontSize: 15 }}>{money(dieCost)}</strong>
                </div>
              </div>
            </>
          )}

          {/* Hiệu lực */}
          <div style={sectionHead}>Hiệu lực</div>
          <label className="field" style={{ maxWidth: 240 }}>
            <span className="field__label">Áp dụng từ ngày *</span>
            <input className="input" type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} required />
          </label>

          {vErr && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{vErr}</div>}
          <div className="md-page__dialog-actions">
            <Button variant="ghost" type="button" onClick={onClose}>Hủy</Button>
            <Button variant="primary" type="submit" loading={saving}>{isVersion ? "Lưu version mới" : "Lưu bảng giá"}</Button>
          </div>
        </div>
      </form>
    </div>
  );
}

function HistoryDialog({ row, onClose }: { row: PlateDieRateRow; onClose: () => void }) {
  const { token } = useAuth();
  const [items, setItems] = useState<PlateDieRateRow[] | null>(null);
  useEffect(() => {
    if (!token) return;
    api.plateDieRates.history(token, row.id).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, row.id]);
  return (
    <div className="md-page__overlay"><div className="card md-page__dialog" style={{ maxWidth: 620 }}>
      <div className="md-page__dialog-head"><h2>Lịch sử giá: {row.code}</h2>
        <button type="button" className="md-page__close" onClick={onClose}>×</button></div>
      <div className="md-page__dialog-body">
        {!items ? <p className="md-page__muted">Đang tải…</p> : (
          <table className="md-page__table"><thead><tr>
            <th>Đơn giá</th><th>Áp dụng từ</th><th>Đến</th><th>Trạng thái</th>
          </tr></thead><tbody>
            {items.map((v) => (
              <tr key={v.id}>
                <td className="md-page__price">{v.pricing_method === "area" ? `${money(v.unit_price_area)}/cm²` : v.pricing_method === "perimeter" ? `${money(v.unit_price_perimeter)}/m` : money(v.unit_price)}</td>
                <td>{v.effective_from}</td>
                <td>{v.effective_to ?? <span className="md-page__muted">Vô hạn</span>}</td>
                <td><StatusBadge r={v} /></td>
              </tr>
            ))}
          </tbody></table>
        )}
        <div className="md-page__dialog-actions"><Button variant="ghost" onClick={onClose}>Đóng</Button></div>
      </div>
    </div></div>
  );
}
