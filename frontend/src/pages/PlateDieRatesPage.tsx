import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type PlateDieRateRow,
  type PlateDieRateInput,
  type PlateDieUsageEstimate,
  type PlateDieUsageOperation,
  type MachineRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { useCan } from "../auth/permissions";
import "./master-data.css";
import "./imposition-rules.css";
import "./plate-die.css";

// ---------------------------------------------------------------------------
// Hằng số nhãn
// ---------------------------------------------------------------------------
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
const KEM_KIND_LABEL: Record<string, string> = Object.fromEntries(KEM_KINDS.map((k) => [k.value, k.label]));
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
  { value: "manual", label: "Nhập tay lúc lập phiếu" },
];
const EST_STATUS_LABEL: Record<string, string> = {
  draft: "Nháp", calculated: "Đã tính", cancelled: "Đã hủy", converted_to_quote: "Đã lên báo giá",
};

const money = (n: number | null | undefined) => (n == null ? "—" : `${n.toLocaleString("vi-VN")}đ`);
const num = (s: string) => { const n = Number(s); return Number.isFinite(n) ? n : 0; };
const today = () => new Date().toISOString().split("T")[0];

// ---------------------------------------------------------------------------
// Trạng thái vòng đời (4 mức)
// ---------------------------------------------------------------------------
type PdStatus = "running" | "future" | "closed" | "inactive";
function statusOf(r: PlateDieRateRow, todayStr: string): PdStatus {
  if (r.effective_to) return "closed";
  if (r.effective_from > todayStr) return "future";
  if (!r.is_active) return "inactive";
  return "running";
}
const STATUS_META: Record<PdStatus, { label: string; cls: string }> = {
  running: { label: "Đang chạy", cls: "pd-badge--running" },
  future: { label: "Sắp áp dụng", cls: "pd-badge--future" },
  closed: { label: "Hết hiệu lực", cls: "pd-badge--closed" },
  inactive: { label: "Tạm ngừng", cls: "pd-badge--inactive" },
};
const isKem = (r: { plate_type: string }) => r.plate_type === KEM_TYPE;
const isUsed = (r: PlateDieRateRow) => r.used_in_estimates > 0 || r.used_in_operations > 0 || r.used_count > 0;

// ---------------------------------------------------------------------------
// "Phạm vi áp dụng" / "Cách tính" / "Đơn giá" — gom cột
// ---------------------------------------------------------------------------
function scopeParts(r: PlateDieRateRow, machineName: (id: number) => string): string {
  if (isKem(r)) {
    const bits: string[] = [];
    if (r.plate_kind) bits.push(KEM_KIND_LABEL[r.plate_kind] ?? r.plate_kind);
    if (r.plate_width_mm && r.plate_height_mm) bits.push(`${r.plate_width_mm}×${r.plate_height_mm}mm`);
    bits.push(!r.machine_ids || r.machine_ids.length === 0
      ? "Mọi máy"
      : r.machine_ids.map(machineName).join(", "));
    return bits.join(" · ");
  }
  return `${DIE_LABEL[r.plate_type] ?? r.plate_type} · Công đoạn ${TECH_LABEL[r.technology] ?? r.technology}`;
}
function cachTinhText(r: PlateDieRateRow): string {
  return isKem(r) ? "Số bản × đơn giá" : (PM_LABEL[r.pricing_method] ?? r.pricing_method);
}
function donGiaText(r: PlateDieRateRow): string {
  if (isKem(r)) return `${money(r.unit_price)}/bản`;
  if (r.pricing_method === "area") return `${money(r.unit_price_area)}/cm²`;
  if (r.pricing_method === "perimeter") return `${money(r.unit_price_perimeter)}/m`;
  return money(r.unit_price);
}

// ---------------------------------------------------------------------------
// Preview tiền (thuần, mirror pricing_engine)
// ---------------------------------------------------------------------------
function kemPreview(r: { unit_price: number; setup_fee: number; min_charge: number }, colors: number, sets: number, forms: number) {
  const plates = Math.round(colors * sets * forms);
  const run = plates * r.unit_price;
  const withSetup = run + r.setup_fee;
  const minApplied = withSetup < r.min_charge;
  return { plates, run, setup: r.setup_fee, withSetup, min: r.min_charge, minApplied, total: Math.max(withSetup, r.min_charge) };
}
function diePreview(
  r: { pricing_method: string; unit_price: number; unit_price_area: number; unit_price_perimeter: number; min_charge: number; max_charge: number | null; reusable: boolean; reuse_price_method: string | null; maintenance_fee: number },
  areaCm2: number, perimM: number, reuse: boolean,
) {
  if (reuse && r.reusable) {
    const rm = r.reuse_price_method || "zero";
    const reuseCost = rm === "zero" ? 0 : rm === "maintenance_fee" ? r.maintenance_fee : 0;
    return { base: reuseCost, total: reuseCost, minApplied: false, maxApplied: false, isReuse: true, rm };
  }
  let base = 0;
  if (r.pricing_method === "area") base = areaCm2 * r.unit_price_area;
  else if (r.pricing_method === "perimeter") base = perimM * r.unit_price_perimeter;
  else base = r.unit_price;
  let total = base;
  const minApplied = total < r.min_charge;
  if (minApplied) total = r.min_charge;
  const maxApplied = r.max_charge != null && total > r.max_charge;
  if (maxApplied) total = r.max_charge as number;
  return { base, total, minApplied, maxApplied, isReuse: false, rm: null as string | null };
}

// ---------------------------------------------------------------------------
// Cảnh báo xung đột phạm vi (client-side, chỉ xét bản đang mở)
// ---------------------------------------------------------------------------
function kemConflict(a: PlateDieRateRow, b: PlateDieRateRow): boolean {
  const aAll = !a.machine_ids || a.machine_ids.length === 0;
  const bAll = !b.machine_ids || b.machine_ids.length === 0;
  if (aAll && bAll) return true;                 // 2 bản "mọi máy" → engine không rõ chọn bản nào
  if (aAll || bAll) return false;                // 1 specific + 1 generic → specific thắng, OK
  return a.machine_ids!.some((x) => b.machine_ids!.includes(x)); // 2 specific trùng máy
}
function conflictPair(a: PlateDieRateRow, b: PlateDieRateRow): boolean {
  if (a.id === b.id) return false;
  if (a.effective_to || b.effective_to) return false; // chỉ bản đang mở
  if (isKem(a) && isKem(b)) return kemConflict(a, b);
  if (!isKem(a) && !isKem(b)) return a.plate_type === b.plate_type && a.technology === b.technology;
  return false;
}
function computeConflicts(rows: PlateDieRateRow[]): { ids: Set<number>; pairs: [PlateDieRateRow, PlateDieRateRow][] } {
  const ids = new Set<number>();
  const pairs: [PlateDieRateRow, PlateDieRateRow][] = [];
  for (let i = 0; i < rows.length; i++)
    for (let j = i + 1; j < rows.length; j++)
      if (conflictPair(rows[i], rows[j])) { pairs.push([rows[i], rows[j]]); ids.add(rows[i].id); ids.add(rows[j].id); }
  return { ids, pairs };
}

// Gợi ý máy theo khổ kẽm (mm) — khổ kẽm lọt vào máy nào (không tự tick, chỉ nhắc).
function machinesFittingPlate(plateWmm: number, plateHmm: number, machines: MachineRow[]): MachineRow[] {
  if (!(plateWmm > 0 && plateHmm > 0)) return [];
  const w = plateWmm / 10, h = plateHmm / 10; // mm → cm
  return machines.filter((m) => m.machine_type === "offset").filter((m) => {
    if (m.max_width_cm == null || m.max_height_cm == null) return false;
    const mw = m.max_width_cm, mh = m.max_height_cm;
    return (w <= mw && h <= mh) || (h <= mw && w <= mh);
  });
}

type TabKind = "kem" | "khuon";
type StatusTab = "running" | "future" | "closed" | "inactive" | "warning" | "all";
const STATUS_TABS: [StatusTab, string][] = [
  ["running", "Đang chạy"], ["future", "Sắp áp dụng"], ["closed", "Hết hiệu lực"],
  ["inactive", "Tạm ngừng"], ["warning", "⚠ Cảnh báo"], ["all", "Tất cả"],
];

// ---------------------------------------------------------------------------
// Trang danh sách
// ---------------------------------------------------------------------------
export function PlateDieRatesPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<TabKind>("kem");
  const [statusTab, setStatusTab] = useState<StatusTab>("running");
  const can = useCan();
  const canCreate = can("dm_gia_khuon_ban", "create");
  const canUpdate = can("dm_gia_khuon_ban", "update");
  const canDelete = can("dm_gia_khuon_ban", "delete");
  const [rows, setRows] = useState<PlateDieRateRow[]>([]);
  const [machines, setMachines] = useState<MachineRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [q, setQ] = useState("");
  const [machineF, setMachineF] = useState("");
  const [methodF, setMethodF] = useState("");

  const [drawer, setDrawer] = useState<DrawerMode | null>(null);
  const [usageFor, setUsageFor] = useState<PlateDieRateRow | null>(null);
  const [historyOf, setHistoryOf] = useState<PlateDieRateRow | null>(null);
  const [closing, setClosing] = useState<PlateDieRateRow | null>(null);
  const [effectiveTo, setEffectiveTo] = useState("");
  const [deleting, setDeleting] = useState<PlateDieRateRow | null>(null);
  const [menuFor, setMenuFor] = useState<number | null>(null);

  const machineName = useCallback((id: number) => machines.find((m) => m.id === id)?.name ?? `#${id}`, [machines]);
  const todayStr = today();

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.plateDieRates
      .list(token, { current_only: false, size: 200 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được bảng giá kẽm/khuôn.");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!token) return;
    api.machines.list(token, { size: 200 }).then((r) => setMachines(r.items)).catch(() => {});
  }, [token]);

  const { ids: conflictIds, pairs: conflictPairs } = useMemo(() => computeConflicts(rows), [rows]);

  // Máy offset thiếu bảng giá kẽm đang chạy (§13).
  const machinesMissingPlate = useMemo(() => {
    const runningKem = rows.filter((r) => isKem(r) && statusOf(r, todayStr) === "running");
    const hasGeneric = runningKem.some((r) => !r.machine_ids || r.machine_ids.length === 0);
    return machines.filter((m) => m.machine_type === "offset").filter((m) => {
      if (hasGeneric) return false;
      return !runningKem.some((r) => r.machine_ids && r.machine_ids.includes(m.id));
    });
  }, [rows, machines, todayStr]);

  // Lọc theo tab kẽm/khuôn.
  const tabRows = useMemo(
    () => rows.filter((r) => (tab === "kem" ? isKem(r) : !isKem(r))),
    [rows, tab],
  );

  const statusCounts = useMemo(() => {
    const c: Record<StatusTab, number> = { running: 0, future: 0, closed: 0, inactive: 0, warning: 0, all: tabRows.length };
    for (const r of tabRows) {
      c[statusOf(r, todayStr)]++;
      if (conflictIds.has(r.id)) c.warning++;
    }
    return c;
  }, [tabRows, todayStr, conflictIds]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const machineId = machineF ? Number(machineF) : null;
    return tabRows.filter((r) => {
      const st = statusOf(r, todayStr);
      if (statusTab === "warning") { if (!conflictIds.has(r.id)) return false; }
      else if (statusTab !== "all" && st !== statusTab) return false;
      if (machineId && tab === "kem") {
        const applies = !r.machine_ids || r.machine_ids.length === 0 || r.machine_ids.includes(machineId);
        if (!applies) return false;
      }
      if (methodF && tab === "khuon" && r.pricing_method !== methodF) return false;
      if (needle && !(`${r.code} ${r.name}`.toLowerCase().includes(needle))) return false;
      return true;
    });
  }, [tabRows, statusTab, machineF, methodF, q, conflictIds, todayStr, tab]);

  async function handleClone(row: PlateDieRateRow) {
    if (!token) return;
    setMenuFor(null);
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
    return <div className="md-page"><div className="banner banner--error">Bạn không có quyền xem Chi phí chế bản & khuôn (403).</div></div>;
  }

  return (
    <div className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Chi phí chế bản & khuôn</h1>
        <p className="md-page__sub">
          Quản lý đơn giá kẽm CTP, khuôn bế / ép kim / dập nổi dùng trong <strong>phiếu tính giá</strong> và{" "}
          <strong>báo giá</strong>. Bảng giá đã dùng không sửa trực tiếp — đổi giá bằng cách <em>tạo phiên bản mới</em>.
        </p>
      </header>

      {/* Summary cards (§13) */}
      <div className="md-page__stats">
        <div className="card md-page__stat-card">
          <span className="md-page__stat-label">Đang chạy</span>
          <span className="md-page__stat-val">{rows.filter((r) => statusOf(r, todayStr) === "running").length}</span>
        </div>
        <div className="card md-page__stat-card">
          <span className="md-page__stat-label">Sắp áp dụng</span>
          <span className="md-page__stat-val">{rows.filter((r) => statusOf(r, todayStr) === "future").length}</span>
        </div>
        <div
          className={`card md-page__stat-card ${conflictIds.size > 0 ? "md-page__stat-card--warn pd-stat-clickable" : ""}`}
          onClick={() => { if (conflictIds.size > 0) setStatusTab("warning"); }}
        >
          <span className="md-page__stat-label">Có cảnh báo</span>
          <span className="md-page__stat-val">{conflictIds.size}</span>
        </div>
        <div className={`card md-page__stat-card ${machinesMissingPlate.length > 0 ? "md-page__stat-card--warn" : ""}`}>
          <span className="md-page__stat-label">Thiếu bảng giá kẽm cho máy</span>
          <span className="md-page__stat-val">{machinesMissingPlate.length}</span>
          {machinesMissingPlate.length > 0 && (
            <span className="md-page__note" style={{ fontSize: 11 }}>{machinesMissingPlate.map((m) => m.name).join(", ")}</span>
          )}
        </div>
      </div>

      {error && <div className="banner banner--error" role="alert"><span>{error}</span>
        <button type="button" className="btn btn--ghost" onClick={() => { setError(null); load(); }}>Tải lại</button></div>}

      {/* Tabs kẽm / khuôn */}
      <div className="ir-tabs">
        {([["kem", "Kẽm in offset"], ["khuon", "Khuôn gia công"]] as [TabKind, string][]).map(([k, label]) => (
          <button key={k} type="button" className={`ir-tab${tab === k ? " ir-tab--active" : ""}`}
            onClick={() => { setTab(k); setMachineF(""); setMethodF(""); }}>
            {label}
            <span className="ir-tab__count">{rows.filter((r) => (k === "kem" ? isKem(r) : !isKem(r))).length}</span>
          </button>
        ))}
      </div>

      {/* Toolbar: search + filter + segmented trạng thái + tạo */}
      <div className="md-page__toolbar">
        <div className="md-page__search">
          <input className="input" placeholder="Tìm mã / tên bảng giá…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {tab === "kem" ? (
          <select className="input md-page__filter" value={machineF} onChange={(e) => setMachineF(e.target.value)} aria-label="Lọc theo máy">
            <option value="">Mọi máy áp dụng</option>
            {machines.filter((m) => m.machine_type === "offset").map((m) => <option key={m.id} value={m.id}>Áp dụng cho {m.name}</option>)}
          </select>
        ) : (
          <select className="input md-page__filter" value={methodF} onChange={(e) => setMethodF(e.target.value)} aria-label="Lọc cách tính">
            <option value="">Mọi cách tính</option>
            {PRICING_METHODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        )}
        <div className="md-page__toolbar-spacer" />
        {canCreate && (
          <Button variant="primary" onClick={() => { setMenuFor(null); setDrawer({ kind: "create" }); }}>
            + Tạo bảng giá {tab === "kem" ? "kẽm" : "khuôn"}
          </Button>
        )}
      </div>

      <div className="pd-seg" role="tablist" style={{ alignSelf: "flex-start" }}>
        {STATUS_TABS.map(([key, label]) => (
          <button key={key} type="button"
            className={`pd-seg__btn${statusTab === key ? " pd-seg__btn--active" : ""}${key === "warning" ? " pd-seg__btn--warn" : ""}`}
            onClick={() => setStatusTab(key)}>
            {label}<span className="pd-seg__count">{statusCounts[key]}</span>
          </button>
        ))}
      </div>

      {conflictPairs.length > 0 && (statusTab === "warning" || statusTab === "running") && (
        <div className="ir-warn" role="status">
          {conflictPairs.slice(0, 4).map(([a, b], i) => (
            <div key={i}>
              <strong>"{a.name}"</strong> ({a.code}) và <strong>"{b.name}"</strong> ({b.code}) trùng phạm vi áp dụng —
              engine không rõ chọn bảng giá nào. Hãy thu hẹp phạm vi hoặc đóng một bản.
            </div>
          ))}
          {conflictPairs.length > 4 && <div>… và {conflictPairs.length - 4} cặp khác.</div>}
        </div>
      )}

      {/* Bảng */}
      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Bảng giá</th>
              <th>Phạm vi áp dụng</th>
              <th>Cách tính</th>
              <th>Đơn giá</th>
              <th>Hiệu lực</th>
              <th>Đang dùng trong</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="md-page__status" role="status">Đang tải…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={8} className="md-page__empty">Không có bảng giá nào khớp bộ lọc.</td></tr>
            ) : (
              filtered.map((r) => {
                const st = statusOf(r, todayStr);
                const usedCount = isKem(r) ? r.used_in_estimates : r.used_in_operations;
                const usedLabel = isKem(r) ? "phiếu tính giá" : "công đoạn";
                return (
                  <tr key={r.id} className="md-page__row" onClick={() => openRow(r)}>
                    <td>
                      <div><strong>{r.name}</strong></div>
                      <div className="md-page__mono md-page__muted">{r.code}</div>
                    </td>
                    <td><span className="pd-scope">{scopeParts(r, machineName)}</span></td>
                    <td>{cachTinhText(r)}</td>
                    <td><span className="pd-price">{donGiaText(r)}</span></td>
                    <td style={{ fontSize: 12.5 }}>{r.effective_from}{r.effective_to ? ` → ${r.effective_to}` : " → nay"}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {usedCount > 0 ? (
                        <button type="button" className="ir-usage-link" onClick={() => setUsageFor(r)}>{usedCount} {usedLabel}</button>
                      ) : (
                        <span className="ir-usage-zero">0 {usedLabel}</span>
                      )}
                      {conflictIds.has(r.id) && <span className="ir-conflict-flag" title="Trùng phạm vi">⚠</span>}
                    </td>
                    <td><span className={`pd-badge ${STATUS_META[st].cls}`}>{STATUS_META[st].label}</span></td>
                    <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => openRow(r)}>Mở</button>
                      <span className="ir-menu-wrap">
                        <button type="button" className="ir-iconbtn" title="Thao tác khác" aria-haspopup="menu"
                          onClick={() => setMenuFor(menuFor === r.id ? null : r.id)}>⋯</button>
                        {menuFor === r.id && (
                          <>
                            <div style={{ position: "fixed", inset: 0, zIndex: 29 }} onClick={() => setMenuFor(null)} />
                            <div className="ir-menu" role="menu">
                              {canUpdate && (
                                <button type="button" onClick={() => { setMenuFor(null); setDrawer({ kind: "version", row: r }); }}>Tạo phiên bản mới</button>
                              )}
                              {canCreate && (
                                <button type="button" onClick={() => handleClone(r)}>Sao chép thành bảng giá mới</button>
                              )}
                              {st === "running" && canUpdate && (
                                <button type="button" onClick={() => { setMenuFor(null); setClosing(r); setEffectiveTo(todayStr); }}>Tạm ngừng áp dụng (đóng)</button>
                              )}
                              {usedCount > 0 && (
                                <button type="button" onClick={() => { setMenuFor(null); setUsageFor(r); }}>Xem nơi đang dùng</button>
                              )}
                              <button type="button" onClick={() => { setMenuFor(null); setHistoryOf(r); }}>Xem lịch sử</button>
                              {canDelete && r.effective_from > todayStr && !isUsed(r) && (
                                <>
                                  <div className="ir-menu__sep" />
                                  <button type="button" className="danger" onClick={() => { setMenuFor(null); setDeleting(r); }}>Xóa bản chưa hiệu lực</button>
                                </>
                              )}
                            </div>
                          </>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {drawer && (
        <PlateDieDrawer mode={drawer} tab={tab} machines={machines} allRows={rows}
          onClose={() => setDrawer(null)} onSaved={() => { setDrawer(null); load(); }}
          onRequestVersion={(row) => setDrawer({ kind: "version", row })} />
      )}
      {usageFor && <UsageDialog row={usageFor} onClose={() => setUsageFor(null)} />}
      {historyOf && <HistoryDialog row={historyOf} onClose={() => setHistoryOf(null)} />}

      {closing && (
        <div className="md-page__overlay" onClick={() => setClosing(null)}>
          <form className="card md-page__dialog md-page__dialog--sm" onClick={(e) => e.stopPropagation()} onSubmit={handleClose}>
            <div className="md-page__dialog-head"><h2>Tạm ngừng: {closing.code}</h2>
              <button type="button" className="md-page__close" onClick={() => setClosing(null)}>×</button></div>
            <div className="md-page__dialog-body">
              <label className="field"><span className="field__label">Ngày kết thúc hiệu lực (không gồm ngày này)</span>
                <input type="date" className="input" value={effectiveTo} onChange={(e) => setEffectiveTo(e.target.value)} required /></label>
              <div className="md-page__dialog-actions">
                <Button variant="ghost" type="button" onClick={() => setClosing(null)}>Hủy</Button>
                <Button variant="danger" type="submit">Xác nhận đóng</Button>
              </div>
            </div>
          </form>
        </div>
      )}
      {deleting && (
        <div className="md-page__overlay" onClick={() => setDeleting(null)}>
          <div className="card md-page__dialog md-page__dialog--sm" onClick={(e) => e.stopPropagation()}>
            <div className="md-page__dialog-head"><h2>Xác nhận xóa</h2>
              <button type="button" className="md-page__close" onClick={() => setDeleting(null)}>×</button></div>
            <div className="md-page__dialog-body">
              <p>Xóa bảng giá <strong>{deleting.code}</strong>? (Chỉ xóa được bản chưa hiệu lực & chưa dùng.)</p>
              <div className="md-page__dialog-actions">
                <Button variant="ghost" onClick={() => setDeleting(null)}>Hủy</Button>
                <Button variant="danger" onClick={handleDelete}>Xác nhận xóa</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  function openRow(r: PlateDieRateRow) {
    setMenuFor(null);
    setDrawer({ kind: "view", row: r });
  }
}

// ---------------------------------------------------------------------------
// Drawer tạo / phiên bản mới / xem
// ---------------------------------------------------------------------------
type DrawerMode =
  | { kind: "create" }
  | { kind: "version"; row: PlateDieRateRow }
  | { kind: "view"; row: PlateDieRateRow };

function PlateDieDrawer({
  mode, tab, machines, allRows, onClose, onSaved, onRequestVersion,
}: {
  mode: DrawerMode;
  tab: TabKind;
  machines: MachineRow[];
  allRows: PlateDieRateRow[];
  onClose: () => void;
  onSaved: () => void;
  onRequestVersion: (row: PlateDieRateRow) => void;
}) {
  const { token } = useAuth();
  const src = mode.kind === "create" ? null : mode.row;
  const isCreate = mode.kind === "create";
  const isVersion = mode.kind === "version";
  const readOnly = mode.kind === "view";
  const kem = src ? isKem(src) : tab === "kem";

  const [code, setCode] = useState(src?.code ?? "");
  const [name, setName] = useState(isVersion ? src!.name : src?.name ?? "");
  const [plateType, setPlateType] = useState(src?.plate_type ?? (kem ? KEM_TYPE : "khuon_be"));
  const [technology, setTechnology] = useState(src?.technology ?? (kem ? "offset" : "be"));
  const [plateKind, setPlateKind] = useState(src?.plate_kind ?? "ctp");
  const [plateW, setPlateW] = useState(src?.plate_width_mm ? String(src.plate_width_mm) : "");
  const [plateH, setPlateH] = useState(src?.plate_height_mm ? String(src.plate_height_mm) : "");
  const [machineIds, setMachineIds] = useState<number[]>(src?.machine_ids ?? []);
  const [unitPrice, setUnitPrice] = useState(src ? String(src.unit_price) : "");
  const [setupFee, setSetupFee] = useState(src ? String(src.setup_fee) : "0");
  const [minCharge, setMinCharge] = useState(src ? String(src.min_charge) : "0");
  const [pricingMethod, setPricingMethod] = useState(src?.pricing_method ?? "fixed");
  const [priceArea, setPriceArea] = useState(src ? String(src.unit_price_area) : "0");
  const [pricePerimeter, setPricePerimeter] = useState(src ? String(src.unit_price_perimeter) : "0");
  const [maxCharge, setMaxCharge] = useState(src?.max_charge != null ? String(src.max_charge) : "");
  const [reusable, setReusable] = useState(src?.reusable ?? false);
  const [reuseMethod, setReuseMethod] = useState(src?.reuse_price_method ?? "zero");
  const [maintenanceFee, setMaintenanceFee] = useState(src ? String(src.maintenance_fee) : "0");
  const [supplier, setSupplier] = useState(src?.supplier ?? "");
  const [leadTime, setLeadTime] = useState(src ? String(src.lead_time_days) : "0");
  const [transportFee, setTransportFee] = useState(src ? String(src.transport_fee) : "0");
  const [moq, setMoq] = useState(src ? String(src.moq) : "0");
  const [effectiveFrom, setEffectiveFrom] = useState(isVersion ? "" : src?.effective_from ?? today());
  const [showAdv, setShowAdv] = useState(false);

  // Preview inputs
  const [tColors, setTColors] = useState("4");
  const [tSets, setTSets] = useState("1");
  const [tForms, setTForms] = useState("1");
  const [tArea, setTArea] = useState("120");
  const [tPerim, setTPerim] = useState("2");
  const [tReuse, setTReuse] = useState(false);

  const [saving, setSaving] = useState(false);
  const [vErr, setVErr] = useState<string | null>(null);

  const disabled = readOnly;
  const offsetMachines = machines.filter((m) => m.machine_type === "offset");

  // Gợi ý máy theo khổ kẽm (không tự tick).
  const suggested = useMemo(
    () => machinesFittingPlate(num(plateW), num(plateH), machines),
    [plateW, plateH, machines],
  );

  // Cảnh báo trùng phạm vi khi lưu (client-side, so với bản đang mở khác).
  const conflictWith = useMemo(() => {
    const draft: PlateDieRateRow = {
      ...(src ?? ({} as PlateDieRateRow)),
      id: -1, code: code || "__new__", plate_type: plateType, technology,
      machine_ids: kem ? (machineIds.length ? machineIds : null) : null,
      effective_to: null,
    } as PlateDieRateRow;
    return allRows.filter((r) => !r.effective_to && r.code !== (src?.code ?? "") && conflictPair(draft, r));
  }, [allRows, src, code, plateType, technology, machineIds, kem]);

  const kemP = useMemo(() => kemPreview(
    { unit_price: num(unitPrice), setup_fee: num(setupFee), min_charge: num(minCharge) },
    num(tColors), num(tSets), num(tForms),
  ), [unitPrice, setupFee, minCharge, tColors, tSets, tForms]);
  const dieP = useMemo(() => diePreview(
    { pricing_method: pricingMethod, unit_price: num(unitPrice), unit_price_area: num(priceArea),
      unit_price_perimeter: num(pricePerimeter), min_charge: num(minCharge),
      max_charge: maxCharge ? num(maxCharge) : null, reusable, reuse_price_method: reuseMethod, maintenance_fee: num(maintenanceFee) },
    num(tArea), num(tPerim), tReuse,
  ), [pricingMethod, unitPrice, priceArea, pricePerimeter, minCharge, maxCharge, reusable, reuseMethod, maintenanceFee, tArea, tPerim, tReuse]);

  function toggleMachine(id: number) {
    if (disabled) return;
    setMachineIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!token || saving || readOnly) return;
    setVErr(null);
    if (isCreate && !code.trim()) return setVErr("Mã bảng giá không được trống.");
    if (!name.trim()) return setVErr("Tên bảng giá không được trống.");
    if (!effectiveFrom) return setVErr("Chọn ngày áp dụng.");
    const payload: PlateDieRateInput = {
      code: isCreate ? code.trim() : undefined,
      name: name.trim(),
      plate_type: plateType,
      technology,
      unit: kem ? "ban" : pricingMethod === "area" ? "cm2" : pricingMethod === "perimeter" ? "met" : "bo",
      unit_price: num(unitPrice),
      setup_fee: num(setupFee),
      min_charge: num(minCharge),
      effective_from: effectiveFrom,
      is_active: true,
    };
    if (kem) {
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
      if (isVersion && src) await api.plateDieRates.createVersion(token, src.id, payload);
      else await api.plateDieRates.create(token, payload);
      onSaved();
    } catch (err) {
      setVErr(err instanceof ApiError ? err.message : "Lưu thất bại.");
      setSaving(false);
    }
  }

  const title = isCreate ? (kem ? "Tạo bảng giá kẽm" : "Tạo bảng giá khuôn")
    : isVersion ? `Tạo phiên bản mới: ${src?.code}`
    : `Chi tiết: ${src?.name}`;

  return (
    <div className="ir-drawer-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="ir-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="ir-drawer__head">
          <div>
            <h2>{title}</h2>
            <div className="ir-drawer__head-sub">
              {src ? <span className="md-page__mono">{src.code} · từ {src.effective_from}{src.effective_to ? ` → ${src.effective_to}` : ""}</span>
                : "Bảng giá dùng cho engine tính giá"}
            </div>
          </div>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>

        {readOnly && (
          <div className="banner banner--info" role="status" style={{ margin: "12px 24px 0" }}>
            Bảng giá không sửa trực tiếp (giữ số báo giá cũ). Để đổi giá, bấm <strong>Tạo phiên bản mới</strong> với ngày áp dụng mới.
          </div>
        )}
        {isVersion && (
          <div className="banner banner--info" role="status" style={{ margin: "12px 24px 0" }}>
            Tạo <strong>phiên bản mới</strong> của mã {src?.code}; bản đang chạy sẽ tự đóng vào ngày áp dụng mới.
          </div>
        )}

        <div className="ir-drawer__body">
          <div className="ir-split">
            {/* ------- Cột trái: nhập ------- */}
            <div className="ir-split__form">
              <div className="ps-sec" style={{ fontSize: 13, fontWeight: 700, borderBottom: "1px solid var(--rule-soft)", paddingBottom: 4, marginBottom: 8 }}>1 · Thông tin bảng giá</div>
              <div className="md-page__form-grid">
                <label className="field"><span className="field__label">Mã bảng giá {isCreate ? "*" : ""}</span>
                  <input className="input md-page__mono" value={code} disabled={!isCreate}
                    placeholder={kem ? "VD: PLATE_102_CTP" : "VD: DIE_BOX_STD"} onChange={(e) => setCode(e.target.value)} />
                  {!isCreate && <span className="field__hint">Mã không đổi theo phiên bản.</span>}</label>
                <label className="field"><span className="field__label">Tên bảng giá *</span>
                  <input className="input" value={name} disabled={disabled} onChange={(e) => setName(e.target.value)} /></label>
                {kem ? (
                  <label className="field"><span className="field__label">Loại kẽm</span>
                    <select className="input select" value={plateKind} disabled={disabled} onChange={(e) => setPlateKind(e.target.value)}>
                      {KEM_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                    </select></label>
                ) : (
                  <>
                    <label className="field"><span className="field__label">Loại khuôn</span>
                      <select className="input select" value={plateType} disabled={disabled} onChange={(e) => {
                        setPlateType(e.target.value);
                        const d = DIE_TYPES.find((x) => x.value === e.target.value);
                        if (d) setTechnology(d.tech);
                      }}>
                        {DIE_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                      </select></label>
                    <label className="field"><span className="field__label">Công đoạn áp dụng</span>
                      <select className="input select" value={technology} disabled={disabled} onChange={(e) => setTechnology(e.target.value)}>
                        {["be", "ep_kim", "dap_noi"].map((t) => <option key={t} value={t}>{TECH_LABEL[t]}</option>)}
                      </select></label>
                  </>
                )}
              </div>

              {kem ? (
                <>
                  <div className="ps-sec" style={{ fontSize: 13, fontWeight: 700, borderBottom: "1px solid var(--rule-soft)", paddingBottom: 4, margin: "16px 0 8px" }}>2 · Phạm vi áp dụng</div>
                  <div className="md-page__form-grid">
                    <label className="field"><span className="field__label">Khổ kẽm rộng (mm)</span>
                      <input className="input" type="number" value={plateW} disabled={disabled} onChange={(e) => setPlateW(e.target.value)} placeholder="VD: 605" /></label>
                    <label className="field"><span className="field__label">Khổ kẽm dài (mm)</span>
                      <input className="input" type="number" value={plateH} disabled={disabled} onChange={(e) => setPlateH(e.target.value)} placeholder="VD: 745" /></label>
                  </div>
                  <div className="field">
                    <span className="field__label">Máy áp dụng (bỏ trống = mọi máy)</span>
                    <MachineMultiSelect machines={offsetMachines} selected={machineIds} onToggle={toggleMachine} disabled={disabled} />
                    {!disabled && suggested.length > 0 && (
                      <div className="field__hint" style={{ marginTop: 6 }}>
                        Khổ kẽm {num(plateW) / 10}×{num(plateH) / 10}cm hợp {suggested.length} máy: {suggested.map((m) => m.name).join(", ")}.{" "}
                        <button type="button" className="pd-adv-toggle" onClick={() => setMachineIds(Array.from(new Set([...machineIds, ...suggested.map((m) => m.id)])))}>Chọn các máy này</button>
                      </div>
                    )}
                  </div>
                  <div className="ps-sec" style={{ fontSize: 13, fontWeight: 700, borderBottom: "1px solid var(--rule-soft)", paddingBottom: 4, margin: "16px 0 8px" }}>3 · Đơn giá</div>
                  <div className="md-page__form-grid">
                    <label className="field"><span className="field__label">Đơn giá 1 bản kẽm (đ) *</span>
                      <input className="input" type="number" min="0" value={unitPrice} disabled={disabled} onChange={(e) => setUnitPrice(e.target.value)} placeholder="VD: 120000" /></label>
                    <label className="field"><span className="field__label">Phí setup (đ)</span>
                      <input className="input" type="number" min="0" value={setupFee} disabled={disabled} onChange={(e) => setSetupFee(e.target.value)} /></label>
                    <label className="field"><span className="field__label">Phí tối thiểu (đ)</span>
                      <input className="input" type="number" min="0" value={minCharge} disabled={disabled} onChange={(e) => setMinCharge(e.target.value)} /></label>
                  </div>
                </>
              ) : (
                <>
                  <div className="ps-sec" style={{ fontSize: 13, fontWeight: 700, borderBottom: "1px solid var(--rule-soft)", paddingBottom: 4, margin: "16px 0 8px" }}>2 · Cách tính giá</div>
                  <div className="md-page__form-grid">
                    <label className="field"><span className="field__label">Cách tính</span>
                      <select className="input select" value={pricingMethod} disabled={disabled} onChange={(e) => setPricingMethod(e.target.value)}>
                        {PRICING_METHODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                      </select></label>
                    {(pricingMethod === "fixed" || pricingMethod === "size_tier" || pricingMethod === "manual") && (
                      <label className="field"><span className="field__label">Đơn giá cố định (đ)</span>
                        <input className="input" type="number" min="0" value={unitPrice} disabled={disabled} onChange={(e) => setUnitPrice(e.target.value)} placeholder="VD: 800000" /></label>
                    )}
                    {pricingMethod === "area" && (
                      <label className="field"><span className="field__label">Đơn giá theo diện tích (đ/cm²)</span>
                        <input className="input" type="number" min="0" value={priceArea} disabled={disabled} onChange={(e) => setPriceArea(e.target.value)} placeholder="VD: 2000" /></label>
                    )}
                    {pricingMethod === "perimeter" && (
                      <label className="field"><span className="field__label">Đơn giá theo chu vi (đ/mét dao)</span>
                        <input className="input" type="number" min="0" value={pricePerimeter} disabled={disabled} onChange={(e) => setPricePerimeter(e.target.value)} placeholder="VD: 50000" /></label>
                    )}
                    <label className="field"><span className="field__label">Phí tối thiểu (đ)</span>
                      <input className="input" type="number" min="0" value={minCharge} disabled={disabled} onChange={(e) => setMinCharge(e.target.value)} /></label>
                    <label className="field"><span className="field__label">Phí tối đa (đ, tùy chọn)</span>
                      <input className="input" type="number" min="0" value={maxCharge} disabled={disabled} onChange={(e) => setMaxCharge(e.target.value)} /></label>
                  </div>

                  <div className="ps-sec" style={{ fontSize: 13, fontWeight: 700, borderBottom: "1px solid var(--rule-soft)", paddingBottom: 4, margin: "16px 0 8px" }}>3 · Dùng lại khuôn cũ</div>
                  <div className="md-page__toggle-wrap"><input type="checkbox" id="pd-reuse" checked={reusable} disabled={disabled} onChange={(e) => setReusable(e.target.checked)} />
                    <label htmlFor="pd-reuse">Cho phép dùng lại khuôn cũ</label></div>
                  {reusable && (
                    <div className="md-page__form-grid" style={{ marginTop: 8 }}>
                      <label className="field"><span className="field__label">Khi dùng lại, tính phí</span>
                        <select className="input select" value={reuseMethod} disabled={disabled} onChange={(e) => setReuseMethod(e.target.value)}>
                          {REUSE_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                        </select></label>
                      {reuseMethod === "maintenance_fee" && (
                        <label className="field"><span className="field__label">Phí bảo trì khuôn (đ)</span>
                          <input className="input" type="number" min="0" value={maintenanceFee} disabled={disabled} onChange={(e) => setMaintenanceFee(e.target.value)} /></label>
                      )}
                    </div>
                  )}
                </>
              )}

              {/* Nâng cao — NCC/lead/MOQ/vận chuyển (§9) */}
              <div style={{ marginTop: 16 }}>
                <button type="button" className="pd-adv-toggle" onClick={() => setShowAdv((v) => !v)}>
                  {showAdv ? "▾" : "▸"} Nâng cao — Nhà cung cấp / lead time / MOQ
                </button>
                {showAdv && (
                  <div className="md-page__form-grid" style={{ marginTop: 8 }}>
                    <label className="field"><span className="field__label">Nhà cung cấp</span>
                      <input className="input" value={supplier} disabled={disabled} onChange={(e) => setSupplier(e.target.value)} /></label>
                    <label className="field"><span className="field__label">Lead time (ngày)</span>
                      <input className="input" type="number" min="0" value={leadTime} disabled={disabled} onChange={(e) => setLeadTime(e.target.value)} /></label>
                    <label className="field"><span className="field__label">Phí vận chuyển (đ)</span>
                      <input className="input" type="number" min="0" value={transportFee} disabled={disabled} onChange={(e) => setTransportFee(e.target.value)} /></label>
                    <label className="field"><span className="field__label">MOQ</span>
                      <input className="input" type="number" min="0" value={moq} disabled={disabled} onChange={(e) => setMoq(e.target.value)} /></label>
                  </div>
                )}
              </div>

              <div className="ps-sec" style={{ fontSize: 13, fontWeight: 700, borderBottom: "1px solid var(--rule-soft)", paddingBottom: 4, margin: "16px 0 8px" }}>4 · Hiệu lực</div>
              <label className="field" style={{ maxWidth: 240 }}>
                <span className="field__label">Áp dụng từ ngày *</span>
                <input className="input" type="date" value={effectiveFrom} disabled={disabled} onChange={(e) => setEffectiveFrom(e.target.value)} required />
              </label>

              {conflictWith.length > 0 && !disabled && (
                <div className="ir-warn" role="status" style={{ marginTop: 12 }}>
                  Trùng phạm vi với <strong>{conflictWith.map((r) => `${r.name} (${r.code})`).join(", ")}</strong> — engine sẽ không rõ chọn bảng giá nào. Cân nhắc thu hẹp phạm vi hoặc đóng bản kia.
                </div>
              )}
              {vErr && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{vErr}</div>}
            </div>

            {/* ------- Cột phải: preview ------- */}
            <div className="ir-split__aside">
              <div className="ir-panel">
                <span className="ir-panel__title">{kem ? "Preview tiền kẽm" : "Preview tiền khuôn"}</span>
                {kem ? (
                  <>
                    <div className="md-page__form-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <label className="field"><span className="field__label">Số màu</span>
                        <input className="input" type="number" value={tColors} onChange={(e) => setTColors(e.target.value)} /></label>
                      <label className="field"><span className="field__label">Số bộ kẽm</span>
                        <input className="input" type="number" value={tSets} onChange={(e) => setTSets(e.target.value)} /></label>
                      <label className="field"><span className="field__label">Số form/tay</span>
                        <input className="input" type="number" value={tForms} onChange={(e) => setTForms(e.target.value)} /></label>
                    </div>
                    <div className="pd-preview-sep" />
                    <div className="pd-preview-row"><span>Số bản kẽm = {num(tColors)}×{num(tSets)}×{num(tForms)}</span><strong>{kemP.plates} bản</strong></div>
                    <div className="pd-preview-row pd-preview-row--muted"><span>Tiền bản × đơn giá</span><span>{money(kemP.run)}</span></div>
                    {kemP.setup > 0 && <div className="pd-preview-row pd-preview-row--muted"><span>+ Phí setup</span><span>{money(kemP.setup)}</span></div>}
                    {kemP.minApplied && <div className="pd-preview-row pd-preview-row--clamp"><span>Sàn phí tối thiểu</span><span>{money(kemP.min)}</span></div>}
                    <div className="pd-preview-sep" />
                    <div className="pd-preview-row"><span className="pd-preview-total">{money(kemP.total).replace("đ", "")}<small>đ</small></span></div>
                  </>
                ) : (
                  <>
                    {reusable && (
                      <div className="md-page__toggle-wrap"><input type="checkbox" id="pd-test-reuse" checked={tReuse} onChange={(e) => setTReuse(e.target.checked)} />
                        <label htmlFor="pd-test-reuse">Dùng lại khuôn cũ</label></div>
                    )}
                    {!tReuse && pricingMethod === "area" && (
                      <label className="field"><span className="field__label">Diện tích ép (cm²)</span>
                        <input className="input" type="number" value={tArea} onChange={(e) => setTArea(e.target.value)} /></label>
                    )}
                    {!tReuse && pricingMethod === "perimeter" && (
                      <label className="field"><span className="field__label">Chu vi dao (mét)</span>
                        <input className="input" type="number" value={tPerim} onChange={(e) => setTPerim(e.target.value)} /></label>
                    )}
                    <div className="pd-preview-sep" />
                    <div className="pd-preview-row pd-preview-row--muted"><span>Cách tính</span><span>{dieP.isReuse ? `Dùng lại (${REUSE_METHODS.find((m) => m.value === dieP.rm)?.label ?? dieP.rm})` : PM_LABEL[pricingMethod]}</span></div>
                    <div className="pd-preview-row pd-preview-row--muted"><span>Tiền tạm tính</span><span>{money(dieP.base)}</span></div>
                    {dieP.minApplied && <div className="pd-preview-row pd-preview-row--clamp"><span>Sàn phí tối thiểu</span><span>{money(num(minCharge))}</span></div>}
                    {dieP.maxApplied && <div className="pd-preview-row pd-preview-row--clamp"><span>Trần phí tối đa</span><span>{money(num(maxCharge))}</span></div>}
                    <div className="pd-preview-sep" />
                    <div className="pd-preview-row"><span className="pd-preview-total">{money(dieP.total).replace("đ", "")}<small>đ</small></span></div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="ir-drawer__foot">
          <div />
          <div className="ir-drawer__foot-right">
            {readOnly ? (
              <>
                <Button type="button" variant="ghost" onClick={onClose}>Đóng</Button>
                {src && <Button type="button" variant="primary" onClick={() => onRequestVersion(src)}>Tạo phiên bản mới</Button>}
              </>
            ) : (
              <>
                <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
                <Button type="button" variant="primary" loading={saving} onClick={() => submit()}>
                  {isVersion ? "Lưu phiên bản mới" : "Lưu và kích hoạt"}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MachineMultiSelect({ machines, selected, onToggle, disabled }: {
  machines: MachineRow[]; selected: number[]; onToggle: (id: number) => void; disabled?: boolean;
}) {
  const [needle, setNeedle] = useState("");
  const shown = machines.filter((m) => m.name.toLowerCase().includes(needle.trim().toLowerCase()));
  const sel = new Set(selected);
  return (
    <div className="ir-ms">
      <div className="ir-ms__bar">
        <span aria-hidden>🔍</span>
        <input className="ir-ms__search" placeholder="Tìm máy…" value={needle} disabled={disabled} onChange={(e) => setNeedle(e.target.value)} />
        <span className="ir-ms__count" style={{ margin: 0 }}>{selected.length ? `Đã chọn ${selected.length}` : "Mọi máy"}</span>
      </div>
      <div className="ir-ms__list">
        {shown.length === 0 ? <div className="ir-ms__empty">Không có máy nào.</div>
          : shown.map((m) => (
            <label key={m.id} className="ir-ms__opt">
              <input type="checkbox" checked={sel.has(m.id)} disabled={disabled} onChange={() => onToggle(m.id)} />
              {m.name}
              {m.max_width_cm != null && <span className="md-page__muted" style={{ fontSize: 11 }}> ({m.max_width_cm}×{m.max_height_cm})</span>}
            </label>
          ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// "Xem nơi đang dùng" — kẽm → phiếu; khuôn → công đoạn
// ---------------------------------------------------------------------------
function UsageDialog({ row, onClose }: { row: PlateDieRateRow; onClose: () => void }) {
  const { token } = useAuth();
  const [ests, setEsts] = useState<PlateDieUsageEstimate[]>([]);
  const [ops, setOps] = useState<PlateDieUsageOperation[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const kem = isKem(row);

  useEffect(() => {
    if (!token) return;
    api.plateDieRates.usage(token, row.id)
      .then((r) => { setEsts(r.estimates); setOps(r.operations); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được."))
      .finally(() => setLoading(false));
  }, [token, row.id]);

  return (
    <div className="md-page__overlay" role="dialog" onClick={onClose}>
      <div className="md-page__dialog card" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="md-page__dialog-head">
          <h2>Nơi đang dùng: {row.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <p className="md-page__note">
            <span className="md-page__mono">{row.code}</span> — {kem ? "các phiếu tính giá dùng kẽm này" : "các công đoạn gắn khuôn này"}. Vì đã dùng nên đổi giá phải qua phiên bản mới.
          </p>
          {loading ? <p className="md-page__status">Đang tải…</p>
            : err ? <div className="banner banner--error">{err}</div>
            : kem ? (
              ests.length === 0 ? <p className="md-page__empty">Chưa có phiếu tính giá nào.</p> : (
                <table className="md-page__table">
                  <thead><tr><th>Số phiếu</th><th>Sản phẩm</th><th>Trạng thái</th><th>Ngày tạo</th></tr></thead>
                  <tbody>{ests.map((e) => (
                    <tr key={e.id}>
                      <td className="md-page__mono">{e.estimate_number}</td>
                      <td>{e.product_name}</td>
                      <td>{EST_STATUS_LABEL[e.status] ?? e.status}</td>
                      <td style={{ fontSize: 12 }}>{new Date(e.created_at).toLocaleDateString("vi-VN")}</td>
                    </tr>
                  ))}</tbody>
                </table>
              )
            ) : (
              ops.length === 0 ? <p className="md-page__empty">Chưa có công đoạn nào.</p> : (
                <table className="md-page__table">
                  <thead><tr><th>Mã</th><th>Công đoạn</th><th>Loại</th></tr></thead>
                  <tbody>{ops.map((o) => (
                    <tr key={o.id}><td className="md-page__mono">{o.code}</td><td>{o.name}</td><td>{TECH_LABEL[o.operation_type] ?? o.operation_type}</td></tr>
                  ))}</tbody>
                </table>
              )
            )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lịch sử phiên bản
// ---------------------------------------------------------------------------
function HistoryDialog({ row, onClose }: { row: PlateDieRateRow; onClose: () => void }) {
  const { token } = useAuth();
  const [items, setItems] = useState<PlateDieRateRow[] | null>(null);
  useEffect(() => {
    if (!token) return;
    api.plateDieRates.history(token, row.id).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, row.id]);
  const todayStr = today();
  return (
    <div className="md-page__overlay" role="dialog" onClick={onClose}>
      <div className="md-page__dialog card" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="md-page__dialog-head"><h2>Lịch sử giá: {row.code}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button></div>
        <div className="md-page__dialog-body">
          {!items ? <p className="md-page__muted">Đang tải…</p> : (
            <table className="md-page__table">
              <thead><tr><th>Đơn giá</th><th>Áp dụng từ</th><th>Đến</th><th>Trạng thái</th></tr></thead>
              <tbody>{items.map((v) => (
                <tr key={v.id}>
                  <td className="pd-price">{donGiaText(v)}</td>
                  <td>{v.effective_from}</td>
                  <td>{v.effective_to ?? <span className="md-page__muted">Vô hạn</span>}</td>
                  <td><span className={`pd-badge ${STATUS_META[statusOf(v, todayStr)].cls}`}>{STATUS_META[statusOf(v, todayStr)].label}</span></td>
                </tr>
              ))}</tbody>
            </table>
          )}
          <div className="md-page__dialog-actions"><Button variant="ghost" onClick={onClose}>Đóng</Button></div>
        </div>
      </div>
    </div>
  );
}
