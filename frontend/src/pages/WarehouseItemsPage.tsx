// Trang "Kho hàng → <một kho>" — MODULE KHO TỰ CHỨA (hệ Material + sổ cái). Mỗi kho quản lý
// riêng: tồn của kho + Phiếu nhập/xuất kho (đầy đủ nháp→duyệt→ghi sổ, kho khóa sẵn) + Điều chỉnh
// nhanh + danh sách phiếu của chính kho này. Điều chuyển giữa 2 kho vẫn ở mục "Phiếu kho" tổng.
// Gate `kho`.
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type StockBalanceRow,
  type StockLotRow,
  type KhoMaterialOption,
  type KhoVoucherType,
  type KhoItemStatus,
  type VoucherRow,
  type WarehouseRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { VoucherForm, VoucherDetail } from "./StockVoucherPage";
import "./master-data.css";

const V_STATUS_LABEL: Record<string, string> = {
  draft: "Nháp", pending: "Chờ duyệt", posted: "Đã ghi sổ", cancelled: "Đã hủy",
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
  const [fMat, setFMat] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  // Form đang mở: "tang"=nhập, "giam"=xuất, "chuyen_vi_tri"=chuyển kho, null=không.
  const [voucherEffect, setVoucherEffect] = useState<"tang" | "giam" | "chuyen_vi_tri" | null>(null);
  const [moveOpen, setMoveOpen] = useState(false);
  const [detail, setDetail] = useState<VoucherRow | null>(null);
  // Vật tư đang mở popup "phiếu liên quan" (click từ bảng tồn).
  const [matVouchers, setMatVouchers] = useState<StockBalanceRow | null>(null);

  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const typeById = useMemo(() => new Map(types.map((t) => [t.id, t])), [types]);
  const selectedWh = warehouses.find((w) => w.id === selectedWid) ?? null;

  useEffect(() => {
    if (!token) return;
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.kho.voucherTypes(token).then((r) => setTypes(r.items)).catch(() => {});
    api.kho.itemStatuses(token).then((r) => setStatuses(r.items)).catch(() => {});
    api.warehouses
      .list(token, { size: 200, sort: "code" })
      .then((r) => setWarehouses(r.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
      });
  }, [token]);

  const load = useCallback(() => {
    if (!token || selectedWid == null) {
      setStockRows([]);
      setVoucherRows([]);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      api.kho.stock(token, { warehouse_id: selectedWid, material_id: fMat }),
      api.kho.listVouchers(token, { warehouse_id: selectedWid, size: 100 }),
    ])
      .then(([st, vs]) => {
        setStockRows(st.items);
        setVoucherRows(vs.items);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được dữ liệu kho.");
      })
      .finally(() => setLoading(false));
  }, [token, selectedWid, fMat]);

  useEffect(() => {
    load();
  }, [load]);

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
  const stockCols = 5 + (showCost ? 1 : 0);

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
            <select
              className="input"
              value={fMat ?? ""}
              onChange={(e) => setFMat(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— Tất cả vật tư —</option>
              {materials.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.code} · {m.name}
                </option>
              ))}
            </select>
            <div className="md-page__toolbar-spacer" />
            {canCreate && (
              <>
                <Button variant="primary" onClick={() => setVoucherEffect("tang")}>
                  + Phiếu nhập kho
                </Button>
                <Button variant="ghost" onClick={() => setVoucherEffect("giam")}>
                  + Phiếu xuất kho
                </Button>
                <Button variant="ghost" onClick={() => setVoucherEffect("chuyen_vi_tri")}>
                  + Chuyển kho
                </Button>
                <Button variant="ghost" onClick={() => setMoveOpen(true)}>
                  Điều chỉnh
                </Button>
              </>
            )}
          </div>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          {/* Tồn của kho này. Bấm 1 vật tư → popup các phiếu liên quan. */}
          <h2 className="md-page__section-title">Tồn kho</h2>
          <p className="md-page__muted" style={{ marginTop: -4, marginBottom: 8 }}>
            Bấm vào một vật tư để xem các phiếu kho liên quan đến vật tư đó.
          </p>
          <div className="card md-page__tablewrap">
            <table className="md-page__table">
              <thead>
                <tr>
                  <th>Vật tư</th>
                  <th>Lô</th>
                  <th style={{ textAlign: "right" }}>Tồn thực tế</th>
                  <th style={{ textAlign: "right" }}>Khả dụng</th>
                  {showCost && <th style={{ textAlign: "right" }}>Giá trị tồn</th>}
                  <th>Đơn vị</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={stockCols} className="md-page__status">
                      Đang tải...
                    </td>
                  </tr>
                ) : stockRows.length === 0 ? (
                  <tr>
                    <td colSpan={stockCols} className="md-page__empty">
                      Kho này chưa có tồn. {canCreate ? "Bấm “Phiếu nhập kho”." : ""}
                    </td>
                  </tr>
                ) : (
                  stockRows.map((r, i) => {
                    const m = matById.get(r.material_id);
                    return (
                      <tr key={i} className="md-page__row" onClick={() => setMatVouchers(r)} title="Xem phiếu liên quan vật tư này">
                        <td>
                          <strong>{m ? m.code : `#${r.material_id}`}</strong>
                          {m && <span className="md-page__muted"> · {m.name}</span>}
                        </td>
                        <td>{r.lot_id ?? <span className="md-page__muted">—</span>}</td>
                        <td style={{ textAlign: "right" }}>{r.on_hand.toLocaleString("vi-VN")}</td>
                        <td style={{ textAlign: "right", fontWeight: 600 }}>
                          {r.available.toLocaleString("vi-VN")}
                        </td>
                        {showCost && (
                          <td style={{ textAlign: "right" }}>{r.value.toLocaleString("vi-VN")} đ</td>
                        )}
                        <td>{r.unit}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

        </>
      )}

      {voucherEffect && selectedWh && (
        <VoucherForm
          types={types}
          warehouses={warehouses}
          materials={materials}
          statuses={statuses}
          lockedWarehouse={selectedWh}
          restrictEffect={voucherEffect}
          onClose={() => setVoucherEffect(null)}
          onSaved={() => {
            setVoucherEffect(null);
            load();
          }}
        />
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
          vouchers={voucherRows.filter((v) =>
            v.lines.some((l) => l.material_id === matVouchers.material_id),
          )}
          typeById={typeById}
          onOpenVoucher={(v) => { setMatVouchers(null); setDetail(v); }}
          onClose={() => setMatVouchers(null)}
        />
      )}
      {moveOpen && selectedWh && (
        <AdjustDialog
          materials={materials}
          lockedWarehouse={selectedWh}
          onClose={() => setMoveOpen(false)}
          onSaved={() => {
            setMoveOpen(false);
            load();
          }}
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
  vouchers,
  typeById,
  onOpenVoucher,
  onClose,
}: {
  material: KhoMaterialOption | null;
  materialId: number;
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
                          <span className={`md-page__status-badge ${v.status === "posted" ? "is-active" : "is-inactive"}`}>
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

// Điều chỉnh nhanh (ghi thẳng 1 bút toán) — kho khóa sẵn. Chỉ Điều chỉnh (±) / Tồn đầu kỳ;
// nhập/xuất chuẩn đi qua phiếu.
function AdjustDialog({
  materials,
  lockedWarehouse,
  onClose,
  onSaved,
}: {
  materials: KhoMaterialOption[];
  lockedWarehouse: WarehouseRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const [materialId, setMaterialId] = useState<number | null>(materials[0]?.id ?? null);
  const [moveType, setMoveType] = useState("dieu_chinh");
  const [qty, setQty] = useState("");
  const [inputUom, setInputUom] = useState("");
  const [lotId, setLotId] = useState<number | null>(null);
  const [lots, setLots] = useState<StockLotRow[]>([]);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const material = materials.find((m) => m.id === materialId);

  useEffect(() => {
    if (!token || !materialId) {
      setLots([]);
      return;
    }
    api.kho
      .lots(token, { material_id: materialId, warehouse_id: lockedWarehouse.id, size: 200 })
      .then((r) => setLots(r.items))
      .catch(() => setLots([]));
    setLotId(null);
  }, [token, materialId, lockedWarehouse.id]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);
    if (!materialId) return setError("Chọn vật tư.");
    const q = Number(qty);
    if (!q || Number.isNaN(q)) return setError("Số lượng phải khác 0 (có thể âm để giảm).");
    setSaving(true);
    try {
      await api.kho.createMove(token, {
        material_id: materialId,
        warehouse_id: lockedWarehouse.id,
        lot_id: lotId,
        quantity: q,
        input_uom: inputUom.trim() || null,
        move_type: moveType,
        reason: reason.trim() || null,
        note: null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ghi bút toán thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>
            Điều chỉnh tồn · {lockedWarehouse.code} {lockedWarehouse.name}
          </h2>
          <button type="button" className="md-page__close" onClick={onClose}>
            ✕
          </button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Vật tư *</span>
              <select
                className="input"
                value={materialId ?? ""}
                onChange={(e) => setMaterialId(Number(e.target.value))}
              >
                {materials.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.code} · {m.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field__label">Loại *</span>
              <select className="input" value={moveType} onChange={(e) => setMoveType(e.target.value)}>
                <option value="dieu_chinh">Điều chỉnh (±)</option>
                <option value="ton_dau_ky">Tồn đầu kỳ</option>
              </select>
            </label>
            <label className="field">
              <span className="field__label">Lô</span>
              <select
                className="input"
                value={lotId ?? ""}
                onChange={(e) => setLotId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— Không —</option>
                {lots.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.code}
                    {l.supplier ? ` · ${l.supplier}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field__label">Số lượng * (âm = giảm)</span>
              <input
                className="input"
                type="number"
                step="0.001"
                placeholder="VD: -50"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">Đơn vị nhập</span>
              <input
                className="input"
                placeholder={material ? `mặc định: ${material.unit}` : "ream / kg…"}
                value={inputUom}
                onChange={(e) => setInputUom(e.target.value)}
              />
              <small className="md-page__muted">
                Trống = đơn vị tồn ({material?.unit ?? "—"}). Gõ "ream"/"kg" để tự quy đổi.
              </small>
            </label>
            <label className="field md-page__form-wide">
              <span className="field__label">Lý do / Diễn giải</span>
              <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>
          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>
              Hủy
            </Button>
            <Button type="submit" variant="primary" loading={saving}>
              Ghi bút toán
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
