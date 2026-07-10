// Trang Kiểm kê (spec-13 C). Tạo đợt → chốt tồn hệ thống → nhập thực đếm → duyệt sinh
// điều chỉnh tồn tự động. Gate `kho`; duyệt gate `kho:approve`.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError, api,
  type CountRow, type CountLineRow, type KhoMaterialOption, type WarehouseRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import "./master-data.css";

const STATUS_LABEL: Record<string, string> = { open: "Đang đếm", posted: "Đã ghi sổ", cancelled: "Đã hủy" };
// Nhóm vật tư (khớp MATERIAL_GROUPS backend) cho phạm vi kiểm kê theo nhóm.
const MATERIAL_GROUPS: { value: string; label: string }[] = [
  { value: "paper", label: "Giấy" },
  { value: "ink", label: "Mực" },
  { value: "film", label: "Màng/Film" },
  { value: "glue", label: "Keo" },
  { value: "packaging", label: "Bao bì" },
  { value: "auxiliary", label: "Vật tư phụ" },
];

function escHtml(v: unknown): string {
  return String(v ?? "—").replace(/[&<>]/g, (c) => (c === "&" ? "&amp;" : c === "<" ? "&lt;" : "&gt;"));
}
function fmtNum(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("vi-VN", { maximumFractionDigits: 3 });
}

export function KhoKiemKePage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("kho", "create");
  const canApprove = can("kho", "approve");

  const [rows, setRows] = useState<CountRow[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [newWh, setNewWh] = useState<number | null>(null);
  const [participants, setParticipants] = useState("");
  const [groupF, setGroupF] = useState("");

  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.kho.listCounts(token).then((r) => setRows(r.items))
      .catch((e) => { if (e instanceof ApiError && e.isForbidden) setForbidden(true); else setError("Không tải được danh sách kiểm kê."); })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => { setWarehouses(r.items); setNewWh(r.items[0]?.id ?? null); }).catch(() => {});
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function createCount() {
    if (!token || !newWh) return;
    try {
      const c = await api.kho.createCount(token, { warehouse_id: newWh, participants: participants.trim() || null, material_group: groupF || null });
      setParticipants("");
      load();
      setDetailId(c.id);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Không tạo được đợt."); }
  }

  if (forbidden) {
    return <main className="md-page"><div className="banner banner--error" role="alert">Bạn không có quyền truy cập Kiểm kê (403).</div></main>;
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kho · Vận hành</p>
        <h1 className="md-page__title">Kiểm kê kho</h1>
        <p className="md-page__sub">
          Tạo đợt → hệ thống chốt tồn → nhập số thực đếm → duyệt: tự sinh điều chỉnh đưa tồn về khớp thực tế.
        </p>
      </header>

      <div className="md-page__toolbar">
        {canCreate && (
          <>
            <select className="input" value={newWh ?? ""} onChange={(e) => setNewWh(e.target.value ? Number(e.target.value) : null)}>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
            </select>
            <select className="input" value={groupF} onChange={(e) => setGroupF(e.target.value)} title="Phạm vi: cả kho hoặc 1 nhóm hàng">
              <option value="">— Cả kho (mọi nhóm) —</option>
              {MATERIAL_GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
            </select>
            <input className="input" placeholder="Người/ban tham gia…" style={{ minWidth: 180 }} value={participants} onChange={(e) => setParticipants(e.target.value)} />
            <Button variant="primary" onClick={createCount}>+ Tạo đợt kiểm kê</Button>
          </>
        )}
      </div>
      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead><tr><th>Mã đợt</th><th>Kho</th><th>Số dòng</th><th>Trạng thái</th></tr></thead>
          <tbody>
            {loading ? <tr><td colSpan={4} className="md-page__status">Đang tải...</td></tr>
              : rows.length === 0 ? <tr><td colSpan={4} className="md-page__empty">Chưa có đợt kiểm kê.</td></tr>
              : rows.map((c) => (
                <tr key={c.id} className="md-page__row" onClick={() => setDetailId(c.id)}>
                  <td className="md-page__mono">{c.code}</td>
                  <td>{whById.get(c.warehouse_id)?.code ?? `#${c.warehouse_id}`}</td>
                  <td>{c.lines.length}</td>
                  <td><span className={`md-page__status-badge ${c.status === "posted" ? "is-active" : "is-inactive"}`}>{STATUS_LABEL[c.status] ?? c.status}</span></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {detailId != null && (
        <CountDetail countId={detailId} materials={materials} warehouses={warehouses} canApprove={canApprove} canCreate={canCreate}
          onClose={() => setDetailId(null)} onChanged={load} />
      )}
    </main>
  );
}

function CountDetail({
  countId, materials, warehouses, canApprove, canCreate, onClose, onChanged,
}: {
  countId: number; materials: KhoMaterialOption[]; warehouses: WarehouseRow[];
  canApprove: boolean; canCreate: boolean; onClose: () => void; onChanged: () => void;
}) {
  const { token } = useAuth();
  const [count, setCount] = useState<CountRow | null>(null);
  const [counted, setCounted] = useState<Record<number, string>>({});
  const [defective, setDefective] = useState<Record<number, string>>({});
  const [damaged, setDamaged] = useState<Record<number, string>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);

  const load = useCallback(() => {
    if (!token) return;
    api.kho.getCount(token, countId).then((c) => {
      setCount(c);
      const m: Record<number, string> = {}, dfc: Record<number, string> = {}, dmg: Record<number, string> = {}, nt: Record<number, string> = {};
      c.lines.forEach((l) => {
        m[l.id] = l.counted_qty != null ? String(l.counted_qty) : "";
        dfc[l.id] = l.defective_qty != null ? String(l.defective_qty) : "";
        dmg[l.id] = l.damaged_qty != null ? String(l.damaged_qty) : "";
        nt[l.id] = l.note ?? "";
      });
      setCounted(m); setDefective(dfc); setDamaged(dmg); setNotes(nt);
    }).catch(() => setError("Không tải được đợt."));
  }, [token, countId]);
  useEffect(() => { load(); }, [load]);

  if (!count) return null;
  const editable = count.status === "open";
  const whCode = warehouses.find((w) => w.id === count.warehouse_id)?.code;

  async function saveCounts() {
    if (!token || busy) return;
    setBusy(true); setError(null);
    const num = (v: string | undefined) => (v != null && v !== "" ? Number(v) : null);
    try {
      await api.kho.setCounts(token, countId, count!.lines.map((l) => ({
        line_id: l.id, counted_qty: num(counted[l.id]),
        defective_qty: num(defective[l.id]), damaged_qty: num(damaged[l.id]),
        note: notes[l.id]?.trim() || null,
      })));
      load(); onChanged();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Lưu thất bại."); }
    finally { setBusy(false); }
  }
  async function act(fn: () => Promise<CountRow>) {
    if (!token || busy) return;
    setBusy(true); setError(null);
    try { await fn(); load(); onChanged(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Thao tác thất bại."); }
    finally { setBusy(false); }
  }

  function diffOf(l: CountLineRow): number | null {
    const c = counted[l.id];
    if (c === "" || c == null) return null;
    return Number(c) - l.system_qty;
  }

  // In "Biên bản kiểm kê" — logo cty + thông tin đợt + bảng chênh lệch + ô ký. In số ĐÃ LƯU.
  function onPrint() {
    if (!count) return;
    const w = window.open("", "_blank", "width=960,height=1000");
    if (!w) return;
    const logoAbs = new URL(logoUrl, window.location.href).href;
    const rows = count.lines.map((l, i) => {
      const m = matById.get(l.material_id);
      const dv = l.counted_qty != null ? l.counted_qty - l.system_qty : null;
      return `<tr>
        <td class="c">${i + 1}</td>
        <td>${escHtml(m ? `${m.code} · ${m.name}` : `#${l.material_id}`)}</td>
        <td class="r">${fmtNum(l.system_qty)}</td>
        <td class="r">${fmtNum(l.counted_qty)}</td>
        <td class="r" style="font-weight:600;${dv != null && dv !== 0 ? (dv < 0 ? "color:#c0392b" : "color:#217a3b") : ""}">${dv == null ? "—" : (dv > 0 ? "+" : "") + fmtNum(dv)}</td>
        <td class="r">${fmtNum(l.defective_qty)}</td>
        <td class="r">${fmtNum(l.damaged_qty)}</td>
        <td>${escHtml(l.note || "—")}</td>
      </tr>`;
    }).join("");
    const info: [string, string][] = [
      ["Mã đợt", escHtml(count.code)],
      ["Kho", escHtml(whCode ? `${whCode}` : count.warehouse_id)],
      ["Người/ban tham gia", escHtml(count.participants)],
      ["Người lập", escHtml(count.created_by_name)],
      ["Ngày lập", new Date(count.created_at).toLocaleString("vi-VN")],
      ...(count.posted_at ? [["Người duyệt", escHtml(count.posted_by_name)] as [string, string], ["Ngày duyệt", new Date(count.posted_at).toLocaleString("vi-VN")] as [string, string]] : []),
    ];
    w.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Biên bản kiểm kê ${escHtml(count.code)}</title>
<style>
  * { font-family: 'Segoe UI', Arial, sans-serif; box-sizing: border-box; }
  body { margin: 24px; color: #1a1a1a; }
  .head { display: flex; align-items: center; gap: 14px; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 14px; }
  .head img { height: 50px; } .company { font-size: 16px; font-weight: 700; }
  h1 { font-size: 18px; text-align: center; margin: 4px 0 12px; text-transform: uppercase; }
  table.info { width: 100%; border-collapse: collapse; margin-bottom: 14px; }
  table.info td { padding: 3px 8px; font-size: 13px; } table.info td.k { width: 160px; color: #555; } table.info td.v { font-weight: 600; }
  table.l { width: 100%; border-collapse: collapse; }
  table.l th, table.l td { border: 1px solid #bbb; padding: 5px 7px; font-size: 12.5px; }
  table.l th { background: #f2f0ec; text-align: left; }
  td.r, th.r { text-align: right; } td.c, th.c { text-align: center; width: 30px; }
  .sign { display: flex; justify-content: space-around; margin-top: 40px; text-align: center; font-size: 13px; }
  .sign div { width: 30%; }
  @media print { body { margin: 10mm; } }
</style></head>
<body onload="window.print()" onafterprint="window.close()">
  <div class="head"><img src="${logoAbs}"><div class="company">CÔNG TY SAO VIỆT NHẬT</div></div>
  <h1>Biên bản kiểm kê kho</h1>
  <table class="info"><tbody>${info.map(([k, v]) => `<tr><td class="k">${k}</td><td class="v">${v}</td></tr>`).join("")}</tbody></table>
  <table class="l"><thead><tr>
    <th class="c">#</th><th>Vật tư</th><th class="r">Tồn hệ thống</th><th class="r">Thực đếm</th><th class="r">Chênh lệch</th><th class="r">Kém PC</th><th class="r">Mất PC</th><th>Lý do</th>
  </tr></thead><tbody>${rows}</tbody></table>
  <div class="sign"><div>Ban kiểm kê<br><br><br>………………</div><div>Thủ kho<br><br><br>………………</div><div>Kế toán<br><br><br>………………</div></div>
</body></html>`);
    w.document.close();
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 1040, width: "96%" }}>
        <div className="md-page__dialog-head">
          <h2>Kiểm kê {count.code} · {STATUS_LABEL[count.status] ?? count.status}{whCode ? ` · ${whCode}` : ""}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          {count.participants && <p className="md-page__muted" style={{ marginTop: 0 }}>Người/ban tham gia: <strong>{count.participants}</strong></p>}
          <div className="md-page__tablewrap">
            <table className="md-page__table">
              <thead><tr>
                <th>Vật tư</th><th>Lô</th>
                <th style={{ textAlign: "right" }}>Tồn hệ thống</th>
                <th style={{ textAlign: "right" }}>Thực đếm</th>
                <th style={{ textAlign: "right" }}>Chênh lệch</th>
                <th style={{ textAlign: "right" }}>Kém PC</th>
                <th style={{ textAlign: "right" }}>Mất PC</th>
                <th>Lý do chênh lệch</th>
              </tr></thead>
              <tbody>
                {count.lines.length === 0 ? (
                  <tr><td colSpan={8} className="md-page__empty">Kho trống — không có tồn để kiểm.</td></tr>
                ) : count.lines.map((l) => {
                  const d = diffOf(l);
                  const m = matById.get(l.material_id);
                  return (
                    <tr key={l.id}>
                      <td><strong>{m ? m.code : `#${l.material_id}`}</strong>{m && <span className="md-page__muted"> · {m.name}</span>}</td>
                      <td>{l.lot_id ?? <span className="md-page__muted">—</span>}</td>
                      <td style={{ textAlign: "right" }}>{l.system_qty.toLocaleString("vi-VN")}</td>
                      <td style={{ textAlign: "right" }}>
                        {editable ? (
                          <input className="input" type="number" step="0.001" style={{ width: 90, textAlign: "right" }}
                            value={counted[l.id] ?? ""} onChange={(e) => setCounted((s) => ({ ...s, [l.id]: e.target.value }))} />
                        ) : (l.counted_qty != null ? l.counted_qty.toLocaleString("vi-VN") : "—")}
                      </td>
                      <td style={{ textAlign: "right", fontWeight: 600, color: d == null ? undefined : d < 0 ? "var(--signal)" : d > 0 ? "var(--moss-deep)" : undefined }}>
                        {d == null ? "—" : (d > 0 ? "+" : "") + d.toLocaleString("vi-VN")}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {editable ? (
                          <input className="input" type="number" step="0.001" style={{ width: 72, textAlign: "right" }}
                            value={defective[l.id] ?? ""} onChange={(e) => setDefective((s) => ({ ...s, [l.id]: e.target.value }))} />
                        ) : fmtNum(l.defective_qty)}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {editable ? (
                          <input className="input" type="number" step="0.001" style={{ width: 72, textAlign: "right" }}
                            value={damaged[l.id] ?? ""} onChange={(e) => setDamaged((s) => ({ ...s, [l.id]: e.target.value }))} />
                        ) : fmtNum(l.damaged_qty)}
                      </td>
                      <td>
                        {editable ? (
                          <input className="input" style={{ minWidth: 140 }} placeholder={d ? "Bắt buộc khi lệch" : ""}
                            value={notes[l.id] ?? ""} onChange={(e) => setNotes((s) => ({ ...s, [l.id]: e.target.value }))} />
                        ) : (l.note || <span className="md-page__muted">—</span>)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onPrint}>🖨 In biên bản</Button>
            <div style={{ flex: 1 }} />
            {editable && canCreate && (
              <>
                <Button variant="danger" onClick={() => act(() => api.kho.cancelCount(token!, countId))} loading={busy}>Hủy đợt</Button>
                <Button variant="ghost" onClick={saveCounts} loading={busy}>Lưu số đếm</Button>
              </>
            )}
            {editable && canApprove && (
              <Button variant="primary" onClick={async () => { await saveCounts(); act(() => api.kho.postCount(token!, countId)); }} loading={busy}>
                Duyệt & điều chỉnh tồn
              </Button>
            )}
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
