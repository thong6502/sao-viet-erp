// Báo cáo kho. 2 tab: Nhập–Xuất–Tồn (DacTa Table 7) và Thẻ kho (sổ chi tiết vật tư,
// từng lần nhập/xuất kèm tồn lũy kế). Lọc theo kỳ/kho/vật tư; xuất CSV. Gate `kho`.
import { useEffect, useMemo, useState } from "react";
import {
  ApiError, api,
  type NxtRow, type LedgerOut, type LowStockRow, type LocationStockRow,
  type MinLevelRow, type KhoMaterialOption, type WarehouseRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

function firstOfMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}
function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const MOVE_TYPE_LABEL: Record<string, string> = {
  ton_dau_ky: "Tồn đầu kỳ", nhap: "Nhập", xuat: "Xuất",
  dieu_chinh: "Điều chỉnh", kiem_ke: "Kiểm kê", chuyen_kho: "Chuyển kho",
};

type Tab = "nxt" | "ledger" | "low" | "location";

export function KhoBaoCaoPage() {
  const [tab, setTab] = useState<Tab>("nxt");
  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kho · Báo cáo</p>
        <h1 className="md-page__title">Báo cáo kho</h1>
        <p className="md-page__sub">
          Nhập–Xuất–Tồn tổng hợp, thẻ kho chi tiết, cảnh báo tồn thấp và tồn theo vị trí.
        </p>
      </header>

      <div className="md-tabs">
        {([
          ["nxt", "Nhập – Xuất – Tồn"],
          ["ledger", "Thẻ kho (chi tiết)"],
          ["low", "Cảnh báo tồn thấp"],
          ["location", "Tồn theo vị trí"],
        ] as [Tab, string][]).map(([key, label]) => (
          <button key={key} type="button" className={`md-tab ${tab === key ? "md-tab--active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "nxt" && <NxtReport />}
      {tab === "ledger" && <LedgerReport />}
      {tab === "low" && <LowStockReport />}
      {tab === "location" && <LocationReport />}
    </main>
  );
}

// --- Tab 1: Nhập – Xuất – Tồn -----------------------------------------------
function NxtReport() {
  const { token } = useAuth();
  const showCost = useCan()("kho", "manage_price"); // DacTa 2.3: chỉ vai trò có quyền thấy tiền
  const [from, setFrom] = useState(firstOfMonth());
  const [to, setTo] = useState(today());
  const [fMat, setFMat] = useState<number | null>(null);
  const [fWh, setFWh] = useState<number | null>(null);
  const [rows, setRows] = useState<NxtRow[]>([]);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ran, setRan] = useState(false);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);

  useEffect(() => {
    if (!token) return;
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => setWarehouses(r.items)).catch(() => {});
  }, [token]);

  function run() {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.kho.nxtReport(token, { from, to, material_id: fMat, warehouse_id: fWh })
      .then((res) => { setRows(res.items); setRan(true); })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được báo cáo."))
      .finally(() => setLoading(false));
  }

  function exportCsv() {
    const head = ["Ma hang", "Ten hang", "Kho", "Ton dau", "Nhap", "Xuat", "Ton cuoi",
      ...(showCost ? ["Gia tri ton cuoi"] : []), "Don vi"];
    const lines = rows.map((r) => {
      const m = matById.get(r.material_id);
      const w = whById.get(r.warehouse_id);
      return [m?.code ?? r.material_id, m?.name ?? "", w?.code ?? r.warehouse_id,
        r.opening, r.in_qty, r.out_qty, r.closing,
        ...(showCost ? [r.closing_value] : []), r.unit].join(",");
    });
    const csv = "﻿" + [head.join(","), ...lines].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `bao-cao-nxt_${from}_${to}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const totals = rows.reduce((acc, r) => ({
    opening: acc.opening + r.opening, in_qty: acc.in_qty + r.in_qty,
    out_qty: acc.out_qty + r.out_qty, closing: acc.closing + r.closing,
    closing_value: acc.closing_value + r.closing_value,
  }), { opening: 0, in_qty: 0, out_qty: 0, closing: 0, closing_value: 0 });

  return (
    <>
      <div className="md-page__toolbar">
        <label className="field" style={{ margin: 0 }}>
          <span className="field__label">Từ ngày</span>
          <input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field" style={{ margin: 0 }}>
          <span className="field__label">Đến ngày</span>
          <input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <select className="input" value={fWh ?? ""} onChange={(e) => setFWh(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Tất cả kho —</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
        </select>
        <select className="input" value={fMat ?? ""} onChange={(e) => setFMat(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Tất cả vật tư —</option>
          {materials.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
        </select>
        <Button variant="primary" onClick={run} loading={loading}>Xem báo cáo</Button>
        {rows.length > 0 && <Button variant="ghost" onClick={exportCsv}>Xuất CSV</Button>}
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Vật tư</th><th>Kho</th>
              <th style={{ textAlign: "right" }}>Tồn đầu</th>
              <th style={{ textAlign: "right" }}>Nhập</th>
              <th style={{ textAlign: "right" }}>Xuất</th>
              <th style={{ textAlign: "right" }}>Tồn cuối</th>
              {showCost && <th style={{ textAlign: "right" }}>Giá trị tồn cuối</th>}
              <th>Đơn vị</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={showCost ? 8 : 7} className="md-page__status">Đang tính...</td></tr>
            ) : !ran ? (
              <tr><td colSpan={showCost ? 8 : 7} className="md-page__empty">Chọn kỳ rồi bấm “Xem báo cáo”.</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={showCost ? 8 : 7} className="md-page__empty">Không có biến động trong kỳ.</td></tr>
            ) : (
              <>
                {rows.map((r, i) => {
                  const m = matById.get(r.material_id);
                  const w = whById.get(r.warehouse_id);
                  return (
                    <tr key={i} className="md-page__row" style={{ cursor: "default" }}>
                      <td><strong>{m ? m.code : `#${r.material_id}`}</strong>{m && <span className="md-page__muted"> · {m.name}</span>}</td>
                      <td>{w ? w.code : `#${r.warehouse_id}`}</td>
                      <td style={{ textAlign: "right" }}>{r.opening.toLocaleString("vi-VN")}</td>
                      <td style={{ textAlign: "right", color: "var(--moss-deep)" }}>{r.in_qty ? "+" + r.in_qty.toLocaleString("vi-VN") : "—"}</td>
                      <td style={{ textAlign: "right", color: "var(--signal)" }}>{r.out_qty ? "−" + r.out_qty.toLocaleString("vi-VN") : "—"}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{r.closing.toLocaleString("vi-VN")}</td>
                      {showCost && <td style={{ textAlign: "right" }}>{r.closing_value.toLocaleString("vi-VN")} đ</td>}
                      <td>{r.unit}</td>
                    </tr>
                  );
                })}
                <tr style={{ borderTop: "2px solid var(--rule)", fontWeight: 700 }}>
                  <td colSpan={2}>Tổng cộng</td>
                  <td style={{ textAlign: "right" }}>{totals.opening.toLocaleString("vi-VN")}</td>
                  <td style={{ textAlign: "right" }}>{totals.in_qty.toLocaleString("vi-VN")}</td>
                  <td style={{ textAlign: "right" }}>{totals.out_qty.toLocaleString("vi-VN")}</td>
                  <td style={{ textAlign: "right" }}>{totals.closing.toLocaleString("vi-VN")}</td>
                  {showCost && <td style={{ textAlign: "right" }}>{totals.closing_value.toLocaleString("vi-VN")} đ</td>}
                  <td></td>
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// --- Tab 2: Thẻ kho (sổ chi tiết) -------------------------------------------
function LedgerReport() {
  const { token } = useAuth();
  const showCost = useCan()("kho", "manage_price");
  const [from, setFrom] = useState(firstOfMonth());
  const [to, setTo] = useState(today());
  const [fMat, setFMat] = useState<number | null>(null);
  const [fWh, setFWh] = useState<number | null>(null);
  const [data, setData] = useState<LedgerOut | null>(null);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);
  const colSpan = showCost ? 8 : 6;

  useEffect(() => {
    if (!token) return;
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => setWarehouses(r.items)).catch(() => {});
  }, [token]);

  function run() {
    if (!token) return;
    if (fMat == null) { setError("Chọn một vật tư để xem thẻ kho."); return; }
    setLoading(true);
    setError(null);
    api.kho.ledgerReport(token, { material_id: fMat, warehouse_id: fWh, from, to })
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được thẻ kho."))
      .finally(() => setLoading(false));
  }

  function exportCsv() {
    if (!data) return;
    const m = matById.get(data.material_id);
    const head = ["Thoi gian", "Loai", "Dien giai", "Lo", "Kho", "Nhap", "Xuat", "Ton",
      ...(showCost ? ["Don gia", "Gia tri"] : [])];
    const rows = [
      ["", "Ton dau ky", "", "", "", "", "", data.opening, ...(showCost ? ["", data.opening_value] : [])].join(","),
      ...data.items.map((l) => [
        new Date(l.created_at).toLocaleString("vi-VN"),
        MOVE_TYPE_LABEL[l.move_type] ?? l.move_type,
        (l.reason ?? l.note ?? "").replace(/,/g, " "),
        l.lot_id ?? "", whById.get(l.warehouse_id)?.code ?? l.warehouse_id,
        l.qty_in || "", l.qty_out || "", l.balance,
        ...(showCost ? [l.unit_cost || "", l.value || ""] : []),
      ].join(",")),
    ];
    const csv = "﻿" + [head.join(","), ...rows].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `the-kho_${m?.code ?? data.material_id}_${from}_${to}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const selMat = fMat != null ? matById.get(fMat) : undefined;

  return (
    <>
      <div className="md-page__toolbar">
        <select className="input" value={fMat ?? ""} onChange={(e) => { setFMat(e.target.value ? Number(e.target.value) : null); setError(null); }}>
          <option value="">— Chọn vật tư * —</option>
          {materials.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
        </select>
        <select className="input" value={fWh ?? ""} onChange={(e) => setFWh(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Tất cả kho —</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
        </select>
        <label className="field" style={{ margin: 0 }}>
          <span className="field__label">Từ ngày</span>
          <input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field" style={{ margin: 0 }}>
          <span className="field__label">Đến ngày</span>
          <input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <Button variant="primary" onClick={run} loading={loading}>Xem thẻ kho</Button>
        {data && data.items.length > 0 && <Button variant="ghost" onClick={exportCsv}>Xuất CSV</Button>}
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {data && (
        <div className="card" style={{ padding: "12px 16px", marginBottom: 12, display: "flex", gap: 24, flexWrap: "wrap" }}>
          <span><strong>{selMat?.code}</strong>{selMat && <span className="md-page__muted"> · {selMat.name}</span>}</span>
          <span className="md-page__muted">Tồn đầu: <strong>{data.opening.toLocaleString("vi-VN")}</strong> {data.unit}</span>
          <span className="md-page__muted">Tổng nhập: <strong style={{ color: "var(--moss-deep)" }}>{data.total_in.toLocaleString("vi-VN")}</strong></span>
          <span className="md-page__muted">Tổng xuất: <strong style={{ color: "var(--signal)" }}>{data.total_out.toLocaleString("vi-VN")}</strong></span>
          <span className="md-page__muted">Tồn cuối: <strong>{data.closing.toLocaleString("vi-VN")}</strong> {data.unit}</span>
          {showCost && <span className="md-page__muted">Giá trị cuối: <strong>{data.closing_value.toLocaleString("vi-VN")} đ</strong></span>}
        </div>
      )}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Thời gian</th><th>Loại</th><th>Diễn giải</th><th>Lô</th>
              <th style={{ textAlign: "right" }}>Nhập</th>
              <th style={{ textAlign: "right" }}>Xuất</th>
              <th style={{ textAlign: "right" }}>Tồn</th>
              {showCost && <th style={{ textAlign: "right" }}>Đơn giá</th>}
              {showCost && <th style={{ textAlign: "right" }}>Giá trị</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={colSpan} className="md-page__status">Đang tải...</td></tr>
            ) : !data ? (
              <tr><td colSpan={colSpan} className="md-page__empty">Chọn vật tư rồi bấm “Xem thẻ kho”.</td></tr>
            ) : (
              <>
                <tr style={{ background: "var(--rule-hair)", fontWeight: 600 }}>
                  <td colSpan={showCost ? 6 : 4}>Tồn đầu kỳ</td>
                  <td style={{ textAlign: "right" }}>{data.opening.toLocaleString("vi-VN")}</td>
                  {showCost && <td style={{ textAlign: "right" }}>{data.opening_value.toLocaleString("vi-VN")} đ</td>}
                </tr>
                {data.items.length === 0 ? (
                  <tr><td colSpan={colSpan} className="md-page__empty">Không có biến động trong kỳ.</td></tr>
                ) : data.items.map((l) => (
                  <tr key={l.move_id} className="md-page__row" style={{ cursor: "default" }}>
                    <td className="md-page__mono" style={{ whiteSpace: "nowrap" }}>{new Date(l.created_at).toLocaleString("vi-VN")}</td>
                    <td>{MOVE_TYPE_LABEL[l.move_type] ?? l.move_type}</td>
                    <td>{l.reason || l.note || <span className="md-page__muted">—</span>}</td>
                    <td>{l.lot_id ?? <span className="md-page__muted">—</span>}</td>
                    <td style={{ textAlign: "right", color: "var(--moss-deep)" }}>{l.qty_in ? "+" + l.qty_in.toLocaleString("vi-VN") : "—"}</td>
                    <td style={{ textAlign: "right", color: "var(--signal)" }}>{l.qty_out ? "−" + l.qty_out.toLocaleString("vi-VN") : "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{l.balance.toLocaleString("vi-VN")}</td>
                    {showCost && <td style={{ textAlign: "right" }}>{l.unit_cost ? l.unit_cost.toLocaleString("vi-VN") : "—"}</td>}
                    {showCost && <td style={{ textAlign: "right" }}>{l.value ? l.value.toLocaleString("vi-VN") : "—"}</td>}
                  </tr>
                ))}
                {data.items.length > 0 && (
                  <tr style={{ borderTop: "2px solid var(--rule)", fontWeight: 700 }}>
                    <td colSpan={4}>Tồn cuối kỳ</td>
                    <td style={{ textAlign: "right" }}>{data.total_in.toLocaleString("vi-VN")}</td>
                    <td style={{ textAlign: "right" }}>{data.total_out.toLocaleString("vi-VN")}</td>
                    <td style={{ textAlign: "right" }}>{data.closing.toLocaleString("vi-VN")}</td>
                    {showCost && <td></td>}
                    {showCost && <td style={{ textAlign: "right" }}>{data.closing_value.toLocaleString("vi-VN")} đ</td>}
                  </tr>
                )}
              </>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// --- Tab 3: Cảnh báo tồn thấp -----------------------------------------------
function LowStockReport() {
  const { token } = useAuth();
  const canUpdate = useCan()("kho", "update");
  const [fWh, setFWh] = useState<number | null>(null);
  const [onlyBelow, setOnlyBelow] = useState(true);
  const [rows, setRows] = useState<LowStockRow[]>([]);
  const [levels, setLevels] = useState<MinLevelRow[]>([]);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Form đặt ngưỡng.
  const [nMat, setNMat] = useState<number | null>(null);
  const [nWh, setNWh] = useState<number | null>(null);
  const [nMin, setNMin] = useState("");
  const [saving, setSaving] = useState(false);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);

  useEffect(() => {
    if (!token) return;
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => {
      setWarehouses(r.items);
      setNWh((w) => w ?? r.items[0]?.id ?? null);
    }).catch(() => {});
  }, [token]);

  const load = useMemo(() => () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api.kho.lowStock(token, { warehouse_id: fWh, only_below: onlyBelow }),
      api.kho.listMinLevels(token, fWh),
    ])
      .then(([low, lv]) => { setRows(low.items); setLevels(lv.items); })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được cảnh báo."))
      .finally(() => setLoading(false));
  }, [token, fWh, onlyBelow]);

  useEffect(() => { load(); }, [load]);

  async function saveLevel() {
    if (!token || nMat == null || nWh == null) { setError("Chọn vật tư, kho và nhập ngưỡng."); return; }
    setSaving(true);
    setError(null);
    try {
      await api.kho.upsertMinLevel(token, { material_id: nMat, warehouse_id: nWh, min_qty: Number(nMin) || 0 });
      setNMat(null); setNMin("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu ngưỡng thất bại.");
    } finally {
      setSaving(false);
    }
  }

  async function removeLevel(id: number) {
    if (!token) return;
    try { await api.kho.deleteMinLevel(token, id); load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Xóa thất bại."); }
  }

  return (
    <>
      <div className="md-page__toolbar">
        <select className="input" value={fWh ?? ""} onChange={(e) => setFWh(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Tất cả kho —</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
        </select>
        <label className="field" style={{ margin: 0, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={onlyBelow} onChange={(e) => setOnlyBelow(e.target.checked)} />
          <span className="field__label" style={{ margin: 0 }}>Chỉ hiện dưới ngưỡng</span>
        </label>
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Vật tư</th><th>Kho</th>
              <th style={{ textAlign: "right" }}>Tồn hiện tại</th>
              <th style={{ textAlign: "right" }}>Ngưỡng min</th>
              <th style={{ textAlign: "right" }}>Thiếu</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="md-page__status">Đang tải...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={6} className="md-page__empty">{onlyBelow ? "Không có vật tư nào dưới ngưỡng. ✓" : "Chưa đặt ngưỡng tồn tối thiểu nào."}</td></tr>
            ) : rows.map((r) => {
              const m = matById.get(r.material_id);
              const lv = levels.find((x) => x.material_id === r.material_id && x.warehouse_id === r.warehouse_id);
              return (
                <tr key={`${r.material_id}-${r.warehouse_id}`} className="md-page__row" style={{ cursor: "default" }}>
                  <td><strong>{m ? m.code : `#${r.material_id}`}</strong>{m && <span className="md-page__muted"> · {m.name}</span>}</td>
                  <td>{whById.get(r.warehouse_id)?.code ?? `#${r.warehouse_id}`}</td>
                  <td style={{ textAlign: "right", fontWeight: 600, color: r.below ? "var(--signal)" : undefined }}>{r.on_hand.toLocaleString("vi-VN")}</td>
                  <td style={{ textAlign: "right" }}>{r.min_qty.toLocaleString("vi-VN")}</td>
                  <td style={{ textAlign: "right", color: "var(--signal)", fontWeight: 600 }}>{r.shortfall ? "−" + r.shortfall.toLocaleString("vi-VN") : "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    {canUpdate && lv && (
                      <button
                        type="button"
                        onClick={() => removeLevel(lv.id)}
                        style={{ background: "none", border: "none", color: "var(--signal)", cursor: "pointer", fontSize: 13 }}
                      >
                        Bỏ ngưỡng
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {canUpdate && (
        <div className="card" style={{ padding: "12px 16px", marginTop: 12 }}>
          <p className="field__label" style={{ marginBottom: 8 }}>Đặt / cập nhật ngưỡng tồn tối thiểu</p>
          <div className="md-page__toolbar" style={{ margin: 0 }}>
            <select className="input" value={nMat ?? ""} onChange={(e) => setNMat(e.target.value ? Number(e.target.value) : null)}>
              <option value="">— Vật tư —</option>
              {materials.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
            </select>
            <select className="input" value={nWh ?? ""} onChange={(e) => setNWh(e.target.value ? Number(e.target.value) : null)}>
              <option value="">— Kho —</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
            </select>
            <input className="input" type="number" min={0} step="0.001" placeholder="Ngưỡng min" style={{ width: 140 }}
              value={nMin} onChange={(e) => setNMin(e.target.value)} />
            <Button variant="primary" onClick={saveLevel} loading={saving}>Lưu ngưỡng</Button>
          </div>
        </div>
      )}
    </>
  );
}

// --- Tab 4: Tồn theo vị trí -------------------------------------------------
function LocationReport() {
  const { token } = useAuth();
  const [fWh, setFWh] = useState<number | null>(null);
  const [fMat, setFMat] = useState<number | null>(null);
  const [rows, setRows] = useState<LocationStockRow[]>([]);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);

  useEffect(() => {
    if (!token) return;
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => setWarehouses(r.items)).catch(() => {});
  }, [token]);

  const load = useMemo(() => () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.kho.byLocation(token, { warehouse_id: fWh, material_id: fMat })
      .then((r) => setRows(r.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được tồn theo vị trí."))
      .finally(() => setLoading(false));
  }, [token, fWh, fMat]);

  useEffect(() => { load(); }, [load]);

  // Sắp theo kho → vị trí để dễ đọc.
  const sorted = useMemo(() => [...rows].sort((a, b) =>
    a.warehouse_id - b.warehouse_id || a.location.localeCompare(b.location)
  ), [rows]);

  return (
    <>
      <div className="md-page__toolbar">
        <select className="input" value={fWh ?? ""} onChange={(e) => setFWh(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Tất cả kho —</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
        </select>
        <select className="input" value={fMat ?? ""} onChange={(e) => setFMat(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Tất cả vật tư —</option>
          {materials.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
        </select>
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Kho</th><th>Vị trí</th><th>Vật tư</th>
              <th style={{ textAlign: "right" }}>Tồn</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4} className="md-page__status">Đang tải...</td></tr>
            ) : sorted.length === 0 ? (
              <tr><td colSpan={4} className="md-page__empty">Chưa có tồn gắn vị trí (lô cần có ô “Vị trí”).</td></tr>
            ) : sorted.map((r, i) => {
              const m = matById.get(r.material_id);
              return (
                <tr key={i} className="md-page__row" style={{ cursor: "default" }}>
                  <td>{whById.get(r.warehouse_id)?.code ?? `#${r.warehouse_id}`}</td>
                  <td className="md-page__mono">{r.location}</td>
                  <td><strong>{m ? m.code : `#${r.material_id}`}</strong>{m && <span className="md-page__muted"> · {m.name}</span>}</td>
                  <td style={{ textAlign: "right", fontWeight: 600 }}>{r.on_hand.toLocaleString("vi-VN")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
