// Báo cáo kho. 2 tab: Nhập–Xuất–Tồn (DacTa Table 7) và Thẻ kho (sổ chi tiết vật tư,
// từng lần nhập/xuất kèm tồn lũy kế). Lọc theo kỳ/kho/vật tư; xuất CSV. Gate `kho`.
import { useEffect, useMemo, useState } from "react";
import {
  ApiError, api,
  type NxtRow, type LedgerOut, type LowStockRow,
  type MinLevelRow, type KhoMaterialOption, type WarehouseRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { InfoHint } from "../components/InfoHint";
import { Select, type SelectOption } from "../components/Select";
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

type Tab = "nxt" | "ledger" | "low";

export function KhoBaoCaoPage() {
  const [tab, setTab] = useState<Tab>("nxt");
  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kho · Báo cáo</p>
        <h1 className="md-page__title">Báo cáo kho</h1>
        <p className="md-page__sub">
          Nhập–Xuất–Tồn tổng hợp, thẻ kho chi tiết và cảnh báo tồn thấp.
        </p>
      </header>

      <div className="md-tabs">
        {([
          ["nxt", "Nhập – Xuất – Tồn"],
          ["ledger", "Thẻ kho (chi tiết)"],
          ["low", "Cảnh báo tồn thấp"],
        ] as [Tab, string][]).map(([key, label]) => (
          <button key={key} type="button" className={`md-tab ${tab === key ? "md-tab--active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "nxt" && <NxtReport />}
      {tab === "ledger" && <LedgerReport />}
      {tab === "low" && <LowStockReport />}
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
  // Tìm kiếm (mã/tên vật tư, mã kho) + phân trang phía client.
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);

  useEffect(() => {
    if (!token) return;
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => setWarehouses(r.items)).catch(() => {});
  }, [token]);

  // Tự chạy báo cáo khi vào tab và mỗi khi đổi kỳ/kho/vật tư — không cần bấm nút.
  const run = useMemo(() => () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.kho.nxtReport(token, { from, to, material_id: fMat, warehouse_id: fWh })
      .then((res) => { setRows(res.items); setRan(true); })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được báo cáo."))
      .finally(() => setLoading(false));
  }, [token, from, to, fMat, fWh]);

  useEffect(() => { run(); }, [run]);

  // Lọc theo từ khóa (mã/tên vật tư hoặc mã kho).
  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    if (!kw) return rows;
    return rows.filter((r) => {
      const m = matById.get(r.material_id);
      const w = whById.get(r.warehouse_id);
      return (m?.code ?? "").toLowerCase().includes(kw) ||
        (m?.name ?? "").toLowerCase().includes(kw) ||
        (w?.code ?? "").toLowerCase().includes(kw);
    });
  }, [rows, q, matById, whById]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const curPage = Math.min(page, pages);
  const pageRows = filtered.slice((curPage - 1) * pageSize, curPage * pageSize);

  function exportCsv() {
    const head = ["Ma hang", "Ten hang", "Kho", "Ton dau", "Nhap", "Xuat", "Ton cuoi",
      ...(showCost ? ["Gia tri ton cuoi"] : []), "Don vi"];
    const lines = filtered.map((r) => {
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

  const totals = filtered.reduce((acc, r) => ({
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
        <Button variant="ghost" onClick={run} loading={loading}>↻ Làm mới</Button>
        {filtered.length > 0 && <Button variant="ghost" onClick={exportCsv}>Xuất CSV</Button>}
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {/* Tìm nhanh trong kết quả + tổng số dòng. */}
      <div className="md-page__toolbar" style={{ marginBottom: 10 }}>
        <input className="input" placeholder="Tìm mã / tên vật tư, mã kho…" value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }} style={{ minWidth: 260 }} />
        <div className="md-page__toolbar-spacer" />
        <span className="md-page__muted">{filtered.length} dòng</span>
      </div>

      <div className="card md-page__tablewrap md-page__tablewrap--scroll">
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
              <tr><td colSpan={showCost ? 8 : 7} className="md-page__status">Đang tải báo cáo…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={showCost ? 8 : 7} className="md-page__empty">Không có biến động trong kỳ.</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={showCost ? 8 : 7} className="md-page__empty">Không có dòng khớp từ khóa.</td></tr>
            ) : (
              <>
                {pageRows.map((r, i) => {
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
                  <td colSpan={2}>Tổng cộng ({filtered.length} dòng)</td>
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
      <div className="md-page__pager" style={{ marginTop: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="md-page__muted">Hiển thị</span>
          <select className="input" style={{ width: 72 }} value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
            {[20, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <span className="md-page__muted">dòng · Trang {curPage}/{pages}</span>
        </div>
        {pages > 1 && (
          <div className="md-page__pager-btns">
            <Button variant="ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={curPage <= 1}>‹ Trước</Button>
            <Button variant="ghost" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={curPage >= pages}>Sau ›</Button>
          </div>
        )}
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
  // Tìm kiếm (loại/diễn giải/lô/kho) + phân trang phía client cho các dòng biến động.
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);
  const colSpan = showCost ? 9 : 7; // Thời gian · Loại · Diễn giải · Lô · Nhập · Xuất · Tồn (+ Đơn giá · Giá trị)

  const items = useMemo(() => data?.items ?? [], [data]);
  const fItems = useMemo(() => {
    const kw = q.trim().toLowerCase();
    if (!kw) return items;
    return items.filter((l) =>
      (MOVE_TYPE_LABEL[l.move_type] ?? l.move_type).toLowerCase().includes(kw)
      || (l.reason ?? "").toLowerCase().includes(kw)
      || (l.note ?? "").toLowerCase().includes(kw)
      || String(l.lot_id ?? "").toLowerCase().includes(kw)
      || (whById.get(l.warehouse_id)?.code ?? "").toLowerCase().includes(kw));
  }, [items, q, whById]);
  const pages = Math.max(1, Math.ceil(fItems.length / pageSize));
  const curPage = Math.min(page, pages);
  const pageItems = fItems.slice((curPage - 1) * pageSize, curPage * pageSize);
  const searching = q.trim().length > 0;
  const showOpening = !searching && curPage === 1;  // dòng "Tồn đầu kỳ" chỉ ở trang đầu, không lọc
  const showClosing = !searching && curPage === pages; // dòng "Tồn cuối kỳ" chỉ ở trang cuối, không lọc

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
      .then((d) => { setData(d); setPage(1); setQ(""); })
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

      {/* Tìm nhanh trong các dòng biến động + tổng số dòng. */}
      {data && items.length > 0 && (
        <div className="md-page__toolbar" style={{ marginBottom: 10 }}>
          <input className="input" placeholder="Tìm loại / diễn giải / lô…" value={q}
            onChange={(e) => { setQ(e.target.value); setPage(1); }} style={{ minWidth: 260 }} />
          <div className="md-page__toolbar-spacer" />
          <span className="md-page__muted">{fItems.length} dòng</span>
        </div>
      )}

      <div className="card md-page__tablewrap md-page__tablewrap--scroll">
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
                {showOpening && (
                  <tr style={{ background: "var(--rule-hair)", fontWeight: 600 }}>
                    <td colSpan={6}>Tồn đầu kỳ</td>
                    <td style={{ textAlign: "right" }}>{data.opening.toLocaleString("vi-VN")}</td>
                    {showCost && <td></td>}
                    {showCost && <td style={{ textAlign: "right" }}>{data.opening_value.toLocaleString("vi-VN")} đ</td>}
                  </tr>
                )}
                {items.length === 0 ? (
                  <tr><td colSpan={colSpan} className="md-page__empty">Không có biến động trong kỳ.</td></tr>
                ) : fItems.length === 0 ? (
                  <tr><td colSpan={colSpan} className="md-page__empty">Không có dòng khớp từ khóa.</td></tr>
                ) : pageItems.map((l) => (
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
                {showClosing && items.length > 0 && (
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

      {data && fItems.length > 0 && (
        <div className="md-page__pager" style={{ marginTop: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="md-page__muted">Hiển thị</span>
            <select className="input" style={{ width: 72 }} value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {[20, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <span className="md-page__muted">dòng · Trang {curPage}/{pages}</span>
          </div>
          {pages > 1 && (
            <div className="md-page__pager-btns">
              <Button variant="ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={curPage <= 1}>‹ Trước</Button>
              <Button variant="ghost" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={curPage >= pages}>Sau ›</Button>
            </div>
          )}
        </div>
      )}
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
  const [nNear, setNNear] = useState("");
  const [saving, setSaving] = useState(false);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);
  const matOptions = useMemo<SelectOption<number>[]>(
    () => materials.map((m) => ({ value: m.id, label: m.name, hint: m.code })),
    [materials],
  );

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
      await api.kho.upsertMinLevel(token, { material_id: nMat, warehouse_id: nWh, min_qty: Number(nMin) || 0, near_min_qty: Number(nNear) || 0 });
      setNMat(null); setNMin(""); setNNear("");
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
          <span className="field__label" style={{ margin: 0 }}>Chỉ hiện cảnh báo (min &amp; cận min)</span>
        </label>
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Vật tư</th><th>Kho</th>
              <th style={{ textAlign: "right" }}>Tồn hiện tại</th>
              <th style={{ textAlign: "right" }}>
                Tồn tối thiểu <InfoHint label="Mức tồn thấp nhất cần giữ. Tồn xuống dưới mức này là THIẾU HÀNG (đỏ) — cần nhập bổ sung." />
              </th>
              <th style={{ textAlign: "right" }}>
                Mức báo sớm <InfoHint label="Tồn còn trên mức tối thiểu nhưng đã gần chạm — báo SẮP HẾT (vàng) để chuẩn bị nhập. Để trống nếu không dùng." />
              </th>
              <th>Tình trạng</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="md-page__status">Đang tải...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={7} className="md-page__empty">{onlyBelow ? "Không có vật tư nào cảnh báo. ✓" : "Chưa đặt ngưỡng tồn tối thiểu nào."}</td></tr>
            ) : rows.map((r) => {
              const m = matById.get(r.material_id);
              const lv = levels.find((x) => x.material_id === r.material_id && x.warehouse_id === r.warehouse_id);
              const rowBg = r.level === "below" ? "#fbeaea" : r.level === "near" ? "#fdf6e3" : undefined;
              return (
                <tr key={`${r.material_id}-${r.warehouse_id}`} className="md-page__row" style={{ cursor: "default", background: rowBg }}>
                  <td><strong>{m ? m.code : `#${r.material_id}`}</strong>{m && <span className="md-page__muted"> · {m.name}</span>}</td>
                  <td>{whById.get(r.warehouse_id)?.code ?? `#${r.warehouse_id}`}</td>
                  <td style={{ textAlign: "right", fontWeight: 600, color: r.level === "below" ? "var(--signal)" : undefined }}>{r.on_hand.toLocaleString("vi-VN")}</td>
                  <td style={{ textAlign: "right" }}>{r.min_qty.toLocaleString("vi-VN")}</td>
                  <td style={{ textAlign: "right" }}>{r.near_min_qty ? r.near_min_qty.toLocaleString("vi-VN") : "—"}</td>
                  <td>
                    {r.level === "below" ? (
                      <span className="md-page__status-badge md-page__status-badge--rejected"
                        title="Tồn đã dưới mức tối thiểu — cần nhập bổ sung">
                        Thiếu hàng{r.shortfall ? ` (thiếu ${r.shortfall.toLocaleString("vi-VN")})` : ""}
                      </span>
                    ) : r.level === "near" ? (
                      <span className="md-page__status-badge md-page__status-badge--pending"
                        title="Tồn đang gần chạm mức tối thiểu — nên chuẩn bị nhập">
                        Sắp hết
                      </span>
                    ) : (
                      <span className="md-page__muted">Đủ hàng</span>
                    )}
                  </td>
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
          <p className="field__label" style={{ marginBottom: 10, display: "inline-flex", alignItems: "center", gap: 6 }}>
            Đặt mức tồn cảnh báo cho vật tư
            <InfoHint label="Tồn dưới 'Tồn tối thiểu' → báo Thiếu hàng (đỏ), cần nhập bổ sung. Tồn còn trên tối thiểu nhưng dưới 'Mức báo sớm' → báo Sắp hết (vàng). Bỏ trống Mức báo sớm nếu không cần nhắc trước." />
          </p>
          <div className="md-page__form-grid" style={{ margin: 0 }}>
            <label className="field">
              <span className="field__label">Vật tư</span>
              <Select
                portal
                searchable
                searchPlaceholder="Tìm mã / tên vật tư…"
                placeholder="— Chọn vật tư —"
                ariaLabel="Chọn vật tư"
                value={nMat}
                options={matOptions}
                onChange={(v) => setNMat(v)}
              />
            </label>
            <label className="field">
              <span className="field__label">Kho</span>
              <select className="input" value={nWh ?? ""} onChange={(e) => setNWh(e.target.value ? Number(e.target.value) : null)}>
                <option value="">— Chọn kho —</option>
                {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field__label">Tồn tối thiểu <InfoHint label="Dưới mức này = Thiếu hàng (đỏ), cần nhập bổ sung." /></span>
              <input className="input" type="number" min={0} step="0.001" placeholder="VD: 100"
                value={nMin} onChange={(e) => setNMin(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Mức báo sớm <InfoHint label="Tồn còn trên tối thiểu nhưng dưới mức này = Sắp hết (vàng). Để trống nếu không dùng." /></span>
              <input className="input" type="number" min={0} step="0.001" placeholder="VD: 150 (tùy chọn)"
                value={nNear} onChange={(e) => setNNear(e.target.value)} />
            </label>
          </div>
          <div style={{ marginTop: 10 }}>
            <Button variant="primary" onClick={saveLevel} loading={saving}>Lưu mức cảnh báo</Button>
          </div>
        </div>
      )}
    </>
  );
}

