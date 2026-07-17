// Trang "Kho hàng → <một kho>" — MODULE KHO TỰ CHỨA (hệ Material + sổ cái). Mỗi kho quản lý
// riêng: tồn của kho + Phiếu nhập/xuất kho (đầy đủ nháp→duyệt→ghi sổ, kho khóa sẵn) + Điều chỉnh
// nhanh + danh sách phiếu của chính kho này. Điều chuyển giữa 2 kho vẫn ở mục "Phiếu kho" tổng.
// Gate `kho`.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type StockBalanceRow,
  type KhoMaterialOption,
  type KhoVoucherType,
  type KhoItemStatus,
  type VoucherRow,
  type WarehouseRow,
  type MaterialRow,
  type MinLevelRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { VoucherDetail } from "./StockVoucherPage";
import { MaterialForm, MaterialsCatalogPage } from "./MaterialsCatalogPage";
import { StockRequestPanel } from "./StockRequestPanel";
import { toast } from "../components/Toast";
import { markOwnPurchaseRequest } from "../lib/realtimeFlags";
import { exportXlsx, matchMaterial } from "../lib/xlsxImport";
import { downloadMaterialTemplate, parseMaterialFile } from "../lib/materialsXlsx";
import "./master-data.css";

const V_STATUS_LABEL: Record<string, string> = {
  draft: "Nháp", pending: "Chờ duyệt", posted: "Đã ghi sổ", cancelled: "Đã hủy",
};
// Màu badge theo trạng thái phiếu kho (đồng bộ tab Đề nghị).
const V_STATUS_CLS: Record<string, string> = {
  draft: "md-page__status-badge--draft",
  pending: "md-page__status-badge--pending",
  posted: "md-page__status-badge--posted",
  cancelled: "md-page__status-badge--cancelled",
};

export function WarehouseItemsPage({
  initialWarehouseId = null,
}: {
  initialWarehouseId?: number | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("kho", "create");
  const canApprove = can("kho", "approve");
  const showCost = can("kho", "manage_price");

  // Kho đang mở lấy từ MENU SIDEBAR (nav id "kho-hang:<id>"); component remount theo key.
  const selectedWid = initialWarehouseId;

  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [types, setTypes] = useState<KhoVoucherType[]>([]);
  const [statuses, setStatuses] = useState<KhoItemStatus[]>([]);
  const [stockRows, setStockRows] = useState<StockBalanceRow[]>([]);
  const [voucherRows, setVoucherRows] = useState<VoucherRow[]>([]);
  const [minLevels, setMinLevels] = useState<MinLevelRow[]>([]); // ngưỡng min/cận-min theo vật tư
  const [tonQ, setTonQ] = useState(""); // tìm kiếm bảng Tồn kho (mã/tên vật tư)
  const [tonAlert, setTonAlert] = useState<"" | "below" | "near" | "warn" | "ok">(""); // lọc theo cảnh báo tồn
  const [tonPage, setTonPage] = useState(1);
  const [tonPageSize, setTonPageSize] = useState(20);
  const [selMats, setSelMats] = useState<Set<number>>(new Set()); // vật tư tick để tạo YCMH
  const [mrOpen, setMrOpen] = useState(false); // dialog tạo yêu cầu mua hàng
  const [tonImp, setTonImp] = useState<{ ok: number; errs: string[] } | null>(null); // kết quả import tồn
  const [tonImporting, setTonImporting] = useState(false);
  const tonFileRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [detail, setDetail] = useState<VoucherRow | null>(null); // xem chi tiết phiếu (từ popup phiếu liên quan)
  // Vật tư đang mở popup "phiếu liên quan" (click từ bảng tồn).
  const [matVouchers, setMatVouchers] = useState<StockBalanceRow | null>(null);
  // Sửa hồ sơ vật tư ngay từ bảng tồn (nút "Sửa" trên dòng).
  const [editMat, setEditMat] = useState<MaterialRow | null>(null);
  async function openEditMat(materialId: number) {
    if (!token) return;
    try { setEditMat(await api.materials.get(token, materialId)); }
    catch { /* thiếu quyền / không tải được → bỏ qua */ }
  }
  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const typeById = useMemo(() => new Map(types.map((t) => [t.id, t])), [types]);
  const levelByMat = useMemo(() => new Map(minLevels.map((l) => [l.material_id, l])), [minLevels]);
  // Mức cảnh báo tồn của 1 vật tư: 'below' (đỏ) / 'near' (vàng) / null (đủ).
  function alertLevel(materialId: number, onHand: number): "below" | "near" | null {
    const lv = levelByMat.get(materialId);
    if (!lv) return null;
    if (onHand < lv.min_qty) return "below";
    if (lv.near_min_qty > lv.min_qty && onHand < lv.near_min_qty) return "near";
    return null;
  }
  const selectedWh = warehouses.find((w) => w.id === selectedWid) ?? null;
  const [tab, setTab] = useState<"ton" | "denghi" | "phieudn" | "danhmuc">("ton"); // Tồn kho / Đề nghị / Phiếu từ đề nghị / Danh mục

  useEffect(() => {
    if (!token) return;
    api.kho.voucherTypes(token).then((r) => setTypes(r.items)).catch(() => {});
    api.kho.itemStatuses(token).then((r) => setStatuses(r.items)).catch(() => {});
    api.warehouses
      .list(token, { size: 200, sort: "code" })
      .then((r) => setWarehouses(r.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
      });
  }, [token, selectedWid]);

  const load = useCallback(() => {
    if (!token || selectedWid == null) {
      setStockRows([]);
      setVoucherRows([]);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      api.kho.stock(token, { warehouse_id: selectedWid }),
      api.kho.listVouchers(token, { warehouse_id: selectedWid, size: 100 }),
      api.kho.materialOptions(token, undefined, selectedWid),
      api.kho.listMinLevels(token, selectedWid),
    ])
      .then(([st, vs, mats, lv]) => {
        setStockRows(st.items);
        setVoucherRows(vs.items);
        setMaterials(mats);
        setMinLevels(lv.items);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được dữ liệu kho.");
      })
      .finally(() => setLoading(false));
  }, [token, selectedWid]);

  useEffect(() => {
    load();
  }, [load]);

  // Import tồn đầu kỳ từ Excel (đủ cột như Danh mục + cột SL): vật tư chưa có → tự tạo hồ sơ,
  // rồi ghi bút toán 'tồn đầu kỳ'. Có 1 dòng lỗi → không import gì (all-or-nothing).
  async function importTon(file: File) {
    if (!token || selectedWid == null) return;
    setTonImporting(true); setTonImp(null); setError(null);
    try {
      const { rows, errs } = await parseMaterialFile(file, selectedWid, { withQty: true, existing: materials });
      if (rows.length === 0 && errs.length === 0) { setError("File trống hoặc chưa có dòng dữ liệu."); setTonImporting(false); return; }
      if (errs.length > 0) { setTonImp({ ok: 0, errs }); setTonImporting(false); return; }
      // Mọi dòng hợp lệ → tạo vật tư (nếu chưa có) + ghi tồn đầu kỳ.
      let ok = 0, created = 0; const createErrs: string[] = [];
      for (const p of rows) {
        try {
          let matId = matchMaterial(materials, p.code, p.name)?.id ?? null;
          if (matId == null) { const m = await api.materials.create(token, p.payload); matId = m.id; created++; }
          await api.kho.createMove(token, {
            material_id: matId, warehouse_id: selectedWid, lot_id: null,
            quantity: p.qty as number, input_uom: p.unit || null,
            move_type: "ton_dau_ky", reason: "Import tồn đầu kỳ (Excel)", note: p.payload.note,
          });
          // Ngưỡng tồn / tồn báo sớm (nếu có trong file) → ghi vào min_levels.
          if (p.minQty != null || p.nearQty != null) {
            await api.kho.upsertMinLevel(token, { material_id: matId, warehouse_id: selectedWid, min_qty: p.minQty ?? 0, near_min_qty: p.nearQty ?? 0 });
          }
          ok++;
        } catch (e) { createErrs.push(`Dòng ${p.rowNum} (${p.name}): ${e instanceof ApiError ? e.message : "lỗi"}`); }
      }
      setTonImp({ ok, errs: createErrs });
      if (ok > 0) { load(); toast(`✓ Đã nhập tồn đầu kỳ cho ${ok} vật tư${created ? ` (tạo mới ${created})` : ""}`, "success"); }
    } catch {
      setError("Không đọc được file. Hãy dùng đúng file mẫu (.xlsx).");
    } finally {
      setTonImporting(false);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Kho hàng (403).
        </div>
      </main>
    );
  }

  const noWarehouses = warehouses.length === 0;
  // Cột: [tick nếu canCreate] Vật tư · Lô · Tồn · Ngưỡng tồn · [Giá trị] · ĐVT · [Sửa nếu canCreate]
  const stockCols = 5 + (showCost ? 1 : 0) + (canCreate ? 2 : 0);
  function toggleSel(id: number) {
    setSelMats((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  // Vật tư đã tick → dữ liệu cho dialog tạo yêu cầu mua (gợi ý SL = thiếu so với tồn tối thiểu).
  const selItems = stockRows
    .filter((r) => selMats.has(r.material_id))
    .map((r) => {
      const m = matById.get(r.material_id);
      const lv = levelByMat.get(r.material_id);
      return {
        material_id: r.material_id,
        code: m?.code ?? `#${r.material_id}`,
        name: m?.name ?? "",
        unit: r.unit || m?.unit || "",
        onHand: r.on_hand,
        min: lv?.min_qty ?? 0,
      };
    });

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kho</p>
        <h1 className="md-page__title">
          {selectedWh ? `${selectedWh.code} · ${selectedWh.name}` : "Kho hàng"}
        </h1>
        <p className="md-page__sub">
          Quản lý riêng từng kho: tồn hiện có + phiếu nhập/xuất kho (kho khóa sẵn) + điều chỉnh.
          Điều chuyển giữa 2 kho làm ở mục <strong>Phiếu kho</strong>.
        </p>
      </header>

      {noWarehouses ? (
        <div className="banner banner--warn" role="status">
          Chưa có kho nào được cấu hình. Vui lòng nhờ admin thêm kho ở{" "}
          <strong>Cấu hình danh mục → Cấu hình kho hàng</strong> trước.
        </div>
      ) : selectedWid == null ? (
        <div className="md-page__prompt">
          <p>
            Chọn một kho ở menu bên trái (mục <strong>Tồn kho</strong>) để quản lý tồn và phiếu
            của kho đó.
          </p>
        </div>
      ) : (
        <>
          <div className="md-page__toolbar">
            <span className="md-page__muted" style={{ fontSize: 13 }}>
              Lập phiếu nhập/xuất ở tab <strong>Đề nghị</strong> (từ đề nghị đã duyệt).
            </span>
          </div>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          {/* Tab: Tồn kho | Phiếu kho | Danh mục (vật tư của riêng kho này). */}
          <div style={{ display: "flex", gap: 22, borderBottom: "1px solid var(--rule)", marginBottom: 12 }}>
            {([["ton", "Tồn kho"], ["denghi", "Đề nghị"], ["phieudn", "Phiếu từ đề nghị"], ["danhmuc", "Danh mục"]] as const).map(([k, label]) => (
              <button key={k} type="button" onClick={() => setTab(k)}
                style={{ padding: "9px 2px", background: "none", border: "none", cursor: "pointer",
                  fontSize: 14, borderBottom: tab === k ? "2px solid var(--rust)" : "2px solid transparent",
                  fontWeight: tab === k ? 700 : 500, color: tab === k ? "var(--ink)" : "var(--ash)" }}>
                {label}
              </button>
            ))}
          </div>

          {tab === "ton" ? (() => {
            const kw = tonQ.trim().toLowerCase();
            const shown = stockRows.filter((r) => {
              if (kw) {
                const m = matById.get(r.material_id);
                if (!(m && `${m.code} ${m.name}`.toLowerCase().includes(kw))) return false;
              }
              if (tonAlert) {
                const lvl = alertLevel(r.material_id, r.on_hand);
                if (tonAlert === "below" && lvl !== "below") return false;
                if (tonAlert === "near" && lvl !== "near") return false;
                if (tonAlert === "warn" && lvl == null) return false;
                if (tonAlert === "ok" && lvl != null) return false;
              }
              return true;
            });
            const tonPages = Math.max(1, Math.ceil(shown.length / tonPageSize));
            const tonCur = Math.min(tonPage, tonPages);
            const pageRows = shown.slice((tonCur - 1) * tonPageSize, tonCur * tonPageSize);
            return (
            <>
              <div className="md-page__toolbar" style={{ marginBottom: 10 }}>
                <input className="input" placeholder="Tìm mã / tên vật tư…" value={tonQ}
                  onChange={(e) => { setTonQ(e.target.value); setTonPage(1); }} style={{ minWidth: 220, flex: "1 1 220px" }} />
                <select className="input" value={tonAlert} onChange={(e) => { setTonAlert(e.target.value as typeof tonAlert); setTonPage(1); }} style={{ minWidth: 150 }}>
                  <option value="">— Tất cả tồn —</option>
                  <option value="warn">Có cảnh báo</option>
                  <option value="below">Thiếu hàng</option>
                  <option value="near">Sắp hết</option>
                  <option value="ok">Đủ hàng</option>
                </select>
                <div className="md-page__toolbar-spacer" />
                <span className="md-page__muted" style={{ marginRight: 6 }}>{shown.length} vật tư</span>
                <Button variant="ghost" onClick={() => {
                  const headers = ["Mã", "Tên vật tư", "Lô", "Tồn kho", "Ngưỡng tồn", "Tồn báo sớm", ...(showCost ? ["Giá trị tồn"] : []), "Đơn vị"];
                  const rows = shown.map((r) => {
                    const mm = matById.get(r.material_id);
                    const lv = levelByMat.get(r.material_id);
                    return [mm?.code ?? `#${r.material_id}`, mm?.name ?? "", r.lot_id ?? "", r.on_hand,
                      lv && lv.min_qty > 0 ? lv.min_qty : "", lv && lv.near_min_qty > 0 ? lv.near_min_qty : "",
                      ...(showCost ? [r.value] : []), r.unit ?? ""];
                  });
                  exportXlsx(`ton-kho-${selectedWh?.code ?? "kho"}.xlsx`, headers, rows, "TonKho");
                }}>⭱ Xuất Excel</Button>
                {canCreate && (
                  <>
                    <Button variant="ghost" onClick={() => downloadMaterialTemplate("mau-ton-dau-ky.xlsx", { withQty: true })}>⭳ Tải mẫu Excel</Button>
                    <Button variant="ghost" loading={tonImporting} onClick={() => tonFileRef.current?.click()}>⭱ Import tồn (Excel)</Button>
                    <input ref={tonFileRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) importTon(f); e.target.value = ""; }} />
                  </>
                )}
              </div>
              {tonImp && (
                <div className="banner" role="status" style={{ background: tonImp.errs.length ? "#fdf6e3" : "#dcecdc", color: tonImp.errs.length ? "#8a5a00" : "#244a2e", border: "1px solid rgba(0,0,0,.08)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span>✓ Đã nhập tồn cho <b>{tonImp.ok}</b> vật tư{tonImp.errs.length ? `, ${tonImp.errs.length} dòng lỗi` : ""}.</span>
                    <div className="md-page__toolbar-spacer" />
                    <button type="button" onClick={() => setTonImp(null)} style={{ background: "none", border: "none", cursor: "pointer" }}>✕</button>
                  </div>
                  {tonImp.errs.length > 0 && (
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 140, overflowY: "auto", fontSize: 13 }}>
                      {tonImp.errs.slice(0, 30).map((m, i) => <li key={i}>{m}</li>)}
                      {tonImp.errs.length > 30 && <li>… và {tonImp.errs.length - 30} dòng nữa</li>}
                    </ul>
                  )}
                </div>
              )}
              {canCreate && selMats.size > 0 && (
                <div className="banner" style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                  <span>Đã chọn <b>{selMats.size}</b> vật tư để đề nghị mua</span>
                  <div className="md-page__toolbar-spacer" />
                  <Button variant="ghost" onClick={() => setSelMats(new Set())}>Bỏ chọn</Button>
                  <Button variant="primary" onClick={() => setMrOpen(true)}>+ Tạo yêu cầu mua</Button>
                </div>
              )}
            <div className="card md-page__tablewrap md-page__tablewrap--scroll">
              <table className="md-page__table">
                <thead>
                  <tr>
                    {canCreate && (
                      <th style={{ width: 34 }}>
                        <input type="checkbox" aria-label="Chọn tất cả"
                          checked={shown.length > 0 && shown.every((r) => selMats.has(r.material_id))}
                          onChange={(e) => setSelMats(e.target.checked ? new Set(shown.map((r) => r.material_id)) : new Set())} />
                      </th>
                    )}
                    <th>Vật tư</th><th>Lô</th>
                    <th style={{ textAlign: "right" }}>Tồn kho</th>
                    <th style={{ textAlign: "right" }}>Ngưỡng tồn</th>
                    {showCost && <th style={{ textAlign: "right" }}>Giá trị tồn</th>}
                    <th>Đơn vị</th>
                    {canCreate && <th></th>}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={stockCols} className="md-page__status">Đang tải...</td></tr>
                  ) : shown.length === 0 ? (
                    <tr><td colSpan={stockCols} className="md-page__empty">{stockRows.length === 0 ? `Kho này chưa có tồn. ${canCreate ? "Bấm “Phiếu nhập kho”." : ""}` : "Không có vật tư khớp lọc."}</td></tr>
                  ) : (
                    pageRows.map((r, i) => {
                      const m = matById.get(r.material_id);
                      const lvl = alertLevel(r.material_id, r.on_hand);
                      const rowBg = lvl === "below" ? "#fbeaea" : lvl === "near" ? "#fdf6e3" : undefined;
                      return (
                        <tr key={i} className="md-page__row" style={{ background: rowBg }} onClick={() => setMatVouchers(r)} title="Xem phiếu liên quan vật tư này">
                          {canCreate && (
                            <td onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" aria-label="Chọn vật tư"
                                checked={selMats.has(r.material_id)} onChange={() => toggleSel(r.material_id)} />
                            </td>
                          )}
                          <td>
                            <strong>{m ? m.code : `#${r.material_id}`}</strong>{m && <span className="md-page__muted"> · {m.name}</span>}
                            {lvl === "below" && <span className="md-page__status-badge md-page__status-badge--rejected" style={{ marginLeft: 8 }} title="Tồn đã dưới mức tối thiểu — cần nhập bổ sung">Thiếu hàng</span>}
                            {lvl === "near" && <span className="md-page__status-badge md-page__status-badge--pending" style={{ marginLeft: 8 }} title="Tồn đang gần chạm mức tối thiểu — nên chuẩn bị nhập">Sắp hết</span>}
                          </td>
                          <td>{r.lot_id ?? <span className="md-page__muted">—</span>}</td>
                          <td style={{ textAlign: "right", fontWeight: 600, color: lvl === "below" ? "var(--signal)" : undefined }}>{r.on_hand.toLocaleString("vi-VN")}</td>
                          <td style={{ textAlign: "right" }}>
                            {(() => {
                              const mn = levelByMat.get(r.material_id);
                              if (!mn || !(mn.min_qty > 0)) return <span className="md-page__muted">—</span>;
                              return mn.min_qty.toLocaleString("vi-VN");
                            })()}
                          </td>
                          {showCost && <td style={{ textAlign: "right" }}>{r.value.toLocaleString("vi-VN")} đ</td>}
                          <td>{r.unit || <span className="md-page__muted">—</span>}</td>
                          {canCreate && (
                            <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                              <button type="button" className="btn btn--ghost" style={{ padding: "2px 10px" }}
                                title="Sửa hồ sơ vật tư" onClick={() => openEditMat(r.material_id)}>Sửa</button>
                            </td>
                          )}
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            {shown.length > 0 && (
              <div className="md-page__pager" style={{ marginTop: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="md-page__muted">Hiển thị</span>
                  <select className="input" style={{ width: 72 }} value={tonPageSize}
                    onChange={(e) => { setTonPageSize(Number(e.target.value)); setTonPage(1); }}>
                    {[20, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <span className="md-page__muted">dòng · Trang {tonCur}/{tonPages}</span>
                </div>
                {tonPages > 1 && (
                  <div className="md-page__pager-btns">
                    <Button variant="ghost" onClick={() => setTonPage((p) => Math.max(1, p - 1))} disabled={tonCur <= 1}>‹ Trước</Button>
                    <Button variant="ghost" onClick={() => setTonPage((p) => Math.min(tonPages, p + 1))} disabled={tonCur >= tonPages}>Sau ›</Button>
                  </div>
                )}
              </div>
            )}
            </>
            );
          })() : tab === "denghi" ? (
            /* Đề nghị nhập/xuất kho — bước trước phiếu kho (song song, không bắt buộc). */
            selectedWh ? (
              <StockRequestPanel
                view="requests"
                warehouse={selectedWh}
                warehouses={warehouses}
                materials={materials}
                voucherTypes={types}
                statuses={statuses}
                canApprove={canApprove}
                canCreate={canCreate}
                onFulfilled={() => load()}
              />
            ) : null
          ) : tab === "phieudn" ? (
            /* Phiếu nhập/xuất lập TỪ đề nghị — tab riêng (dễ phân quyền sau này). */
            selectedWh ? (
              <StockRequestPanel
                view="vouchers"
                warehouse={selectedWh}
                warehouses={warehouses}
                materials={materials}
                voucherTypes={types}
                statuses={statuses}
                canApprove={canApprove}
                canCreate={canCreate}
                onFulfilled={() => load()}
              />
            ) : null
          ) : tab === "danhmuc" ? (
            /* Danh mục vật tư CỦA RIÊNG kho này — tạo mới sẽ tự gán vào kho đang xem. */
            <MaterialsCatalogPage embedded warehouseId={selectedWh?.id ?? null} onChanged={() => load()} />
          ) : null}
        </>
      )}

      {detail && (
        <VoucherDetail
          voucher={detail}
          types={types}
          warehouses={warehouses}
          materials={materials}
          statuses={statuses}
          canApprove={canApprove}
          canCreate={canCreate}
          onClose={() => setDetail(null)}
          onChanged={() => {
            setDetail(null);
            load();
          }}
        />
      )}
      {matVouchers && (
        <MaterialVouchersDialog
          material={matById.get(matVouchers.material_id) ?? null}
          materialId={matVouchers.material_id}
          alert={{
            level: alertLevel(matVouchers.material_id, matVouchers.on_hand),
            onHand: matVouchers.on_hand,
            lv: levelByMat.get(matVouchers.material_id) ?? null,
          }}
          vouchers={voucherRows.filter((v) =>
            v.lines.some((l) => l.material_id === matVouchers.material_id),
          )}
          typeById={typeById}
          onOpenVoucher={(v) => { setMatVouchers(null); setDetail(v); }}
          onClose={() => setMatVouchers(null)}
        />
      )}
      {/* Tạo yêu cầu mua hàng (YCMH) từ các vật tư đã tick ở Tồn kho. */}
      {mrOpen && selectedWh && (
        <PurchaseRequestDialog
          warehouse={selectedWh}
          items={selItems}
          onClose={() => setMrOpen(false)}
          onCreated={(code) => {
            setMrOpen(false);
            setSelMats(new Set());
            markOwnPurchaseRequest(); // đừng bắn toast "có YCMH mới" cho chính người vừa tạo
            toast(`✓ Đã gửi yêu cầu mua ${code}`, "success");
          }}
        />
      )}
      {/* Sửa hồ sơ vật tư (tên, đơn vị, thuộc tính…) ngay từ bảng tồn. */}
      {editMat && (
        <MaterialForm
          material={editMat}
          canUpdate={canCreate}
          onClose={() => setEditMat(null)}
          onSaved={() => { setEditMat(null); load(); }}
        />
      )}
    </main>
  );
}

// Popup "phiếu liên quan 1 vật tư" — mở khi bấm 1 dòng ở bảng Tồn kho. Lọc các phiếu của kho
// có dòng chứa vật tư này; hiện số lượng vật tư đó trên từng phiếu. Bấm phiếu → chi tiết phiếu.
function MaterialVouchersDialog({
  material,
  materialId,
  alert,
  vouchers,
  typeById,
  onOpenVoucher,
  onClose,
}: {
  material: KhoMaterialOption | null;
  materialId: number;
  alert?: { level: "below" | "near" | null; onHand: number; lv: MinLevelRow | null };
  vouchers: VoucherRow[];
  typeById: Map<number, KhoVoucherType>;
  onOpenVoucher: (v: VoucherRow) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [statusF, setStatusF] = useState("");
  const [typeF, setTypeF] = useState("");

  // Các loại phiếu có mặt trong danh sách (cho dropdown lọc).
  const typeOpts = useMemo(() => {
    const ids = Array.from(new Set(vouchers.map((v) => v.voucher_type_id)));
    return ids.map((id) => ({ id, name: typeById.get(id)?.name ?? `#${id}` }));
  }, [vouchers, typeById]);

  const shown = useMemo(() => vouchers.filter((v) =>
    (!q.trim() ||
      v.code.toLowerCase().includes(q.trim().toLowerCase()) ||
      (v.partner_ref ?? "").toLowerCase().includes(q.trim().toLowerCase())) &&
    (!statusF || v.status === statusF) &&
    (!typeF || String(v.voucher_type_id) === typeF),
  ), [vouchers, q, statusF, typeF]);

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 820, width: "94%", maxHeight: "88vh", display: "flex", flexDirection: "column" }}>
        <div className="md-page__dialog-head">
          <h2>
            Phiếu liên quan · {material ? `${material.code} · ${material.name}` : `#${materialId}`}
          </h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body" style={{ overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}>
          {/* Cảnh báo tồn ngay đầu phiếu liên quan — đỏ (dưới min) / vàng (sắp min). */}
          {alert?.level === "below" && (
            <div style={{ background: "#fbeaea", color: "#8a1f1f", border: "1px solid #e6b8b8", borderRadius: 6, padding: "8px 12px", marginBottom: 10, fontSize: 13.5 }}>
              ⚠️ <b>Thiếu hàng</b> — tồn {alert.onHand.toLocaleString("vi-VN")}
              {alert.lv ? `, dưới mức tối thiểu ${alert.lv.min_qty.toLocaleString("vi-VN")}` : ""}. Cần nhập bổ sung.
            </div>
          )}
          {alert?.level === "near" && (
            <div style={{ background: "#fdf6e3", color: "#8a5a00", border: "1px solid #e8d9a8", borderRadius: 6, padding: "8px 12px", marginBottom: 10, fontSize: 13.5 }}>
              ⚠️ <b>Sắp hết</b> — tồn {alert.onHand.toLocaleString("vi-VN")}
              {alert.lv ? `, gần chạm mức tối thiểu ${alert.lv.min_qty.toLocaleString("vi-VN")}` : ""}. Nên chuẩn bị nhập.
            </div>
          )}
          <div className="md-page__toolbar" style={{ marginTop: 0 }}>
            <input className="input" placeholder="Tìm mã phiếu / đối tượng…" value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="input" value={typeF} onChange={(e) => setTypeF(e.target.value)}>
              <option value="">— Tất cả loại phiếu —</option>
              {typeOpts.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <select className="input" value={statusF} onChange={(e) => setStatusF(e.target.value)}>
              <option value="">— Tất cả trạng thái —</option>
              <option value="draft">Nháp</option>
              <option value="pending">Chờ duyệt</option>
              <option value="posted">Đã ghi sổ</option>
              <option value="cancelled">Đã hủy</option>
            </select>
            <div className="md-page__toolbar-spacer" />
            <span className="md-page__muted">{shown.length}/{vouchers.length} phiếu</span>
          </div>
          <div className="md-page__tablewrap" style={{ marginTop: 8, overflowY: "auto", maxHeight: "60vh", flex: 1 }}>
            <table className="md-page__table">
              <thead>
                <tr>
                  <th>Mã phiếu</th>
                  <th>Loại phiếu</th>
                  <th>Đối tượng</th>
                  <th style={{ textAlign: "right" }}>SL vật tư</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {vouchers.length === 0 ? (
                  <tr><td colSpan={5} className="md-page__empty">Chưa có phiếu nào chứa vật tư này.</td></tr>
                ) : shown.length === 0 ? (
                  <tr><td colSpan={5} className="md-page__empty">Không có phiếu khớp bộ lọc.</td></tr>
                ) : (
                  shown.map((v) => {
                    const t = typeById.get(v.voucher_type_id);
                    const qty = v.lines
                      .filter((l) => l.material_id === materialId)
                      .reduce((s, l) => s + Number(l.quantity), 0);
                    return (
                      <tr key={v.id} className="md-page__row" onClick={() => onOpenVoucher(v)}>
                        <td className="md-page__mono">{v.code}</td>
                        <td>{t ? t.name : `#${v.voucher_type_id}`}</td>
                        <td>{v.partner_ref || <span className="md-page__muted">—</span>}</td>
                        <td style={{ textAlign: "right" }}>{qty.toLocaleString("vi-VN")}</td>
                        <td>
                          <span className={`md-page__status-badge ${V_STATUS_CLS[v.status] ?? "md-page__status-badge--draft"}`}>
                            {V_STATUS_LABEL[v.status] ?? v.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Tạo YÊU CẦU MUA HÀNG (YCMH) từ các vật tư đã tick ở Tồn kho — gửi sang module Mua hàng.
function PurchaseRequestDialog({
  warehouse,
  items,
  onClose,
  onCreated,
}: {
  warehouse: WarehouseRow;
  items: { material_id: number; code: string; name: string; unit: string; onHand: number; min: number }[];
  onClose: () => void;
  onCreated: (code: string) => void;
}) {
  const { token } = useAuth();
  const today = new Date().toISOString().slice(0, 10);
  const [purpose, setPurpose] = useState(`Bổ sung tồn kho ${warehouse.code}`);
  const [neededDate, setNeededDate] = useState(today);
  const [note, setNote] = useState("");
  const [qty, setQty] = useState<Record<number, string>>(() => {
    const o: Record<number, string> = {};
    for (const it of items) {
      const suggest = it.min > it.onHand ? Math.ceil(it.min - it.onHand) : 1;
      o[it.material_id] = String(suggest);
    }
    return o;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!token || saving) return;
    setError(null);
    const lines = items
      .map((it) => ({
        item_name: `${it.code} · ${it.name}`.trim(),
        unit: it.unit || "cái",
        quantity: Number(qty[it.material_id]) || 0,
        note: null as string | null,
      }))
      .filter((l) => l.quantity > 0);
    if (lines.length === 0) return setError("Cần ít nhất 1 vật tư có SL cần mua > 0.");
    if (!purpose.trim()) return setError("Nhập mục đích.");
    if (!neededDate) return setError("Chọn ngày cần.");
    setSaving(true);
    try {
      const r = await api.departmentPurchaseRequests.create(token, {
        source_type: "kho",
        related_document_type: "kho",
        related_document_code: warehouse.code,
        purpose: purpose.trim(),
        needed_date: neededDate,
        note: note.trim() || null,
        lines,
      });
      onCreated(r.code);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Tạo yêu cầu mua thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 760, width: "94%", maxHeight: "88vh", display: "flex", flexDirection: "column" }}>
        <div className="md-page__dialog-head">
          <h2>Tạo yêu cầu mua hàng · {items.length} vật tư</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body" style={{ overflowY: "auto" }}>
          <div className="md-page__form-grid">
            <label className="field md-page__form-wide">
              <span className="field__label">Mục đích *</span>
              <input className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Ngày cần *</span>
              <input className="input" type="date" value={neededDate} onChange={(e) => setNeededDate(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Bộ phận</span>
              <input className="input" value={`Kho · ${warehouse.code}`} disabled />
            </label>
            <label className="field md-page__form-wide">
              <span className="field__label">Ghi chú</span>
              <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
          </div>

          <div className="md-page__tablewrap" style={{ marginTop: 8 }}>
            <table className="md-page__table">
              <thead>
                <tr><th>Vật tư</th><th style={{ textAlign: "right" }}>Tồn</th><th style={{ width: 130 }}>SL cần mua *</th><th style={{ width: 70 }}>ĐVT</th></tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.material_id}>
                    <td><strong>{it.code}</strong> <span className="md-page__muted">· {it.name}</span></td>
                    <td style={{ textAlign: "right" }}>{it.onHand.toLocaleString("vi-VN")}</td>
                    <td>
                      <input className="input" type="number" min="0" step="0.001"
                        value={qty[it.material_id] ?? ""}
                        onChange={(e) => setQty((o) => ({ ...o, [it.material_id]: e.target.value }))} />
                    </td>
                    <td>{it.unit || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 10 }}>{error}</div>}
        </div>
        <div className="md-page__dialog-actions">
          <Button variant="ghost" onClick={onClose}>Hủy</Button>
          <Button variant="primary" onClick={submit} loading={saving}>Tạo yêu cầu mua</Button>
        </div>
      </div>
    </div>
  );
}
