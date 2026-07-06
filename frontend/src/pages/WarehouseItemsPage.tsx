import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type WarehouseItemRow,
  type WarehouseItemInput,
  type WarehouseOption,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

// Module Kho hàng vận hành (spec-kho): nhân viên / trưởng phòng / chức vụ khác CHỌN một kho
// (đã được admin cấu hình) từ dropdown, rồi thêm / sửa mặt hàng NGAY TRONG kho đó.
export function WarehouseItemsPage({
  initialWarehouseId = null,
}: {
  initialWarehouseId?: number | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("kho", "create");
  const canUpdate = can("kho", "update");
  const canDelete = can("kho", "delete");

  // Kho đang mở được chọn từ MENU SIDEBAR (nav id "kho-hang:<id>"); component remount theo
  // key nên chỉ cần đọc từ prop, không cần state.
  const [options, setOptions] = useState<WarehouseOption[]>([]);
  const selectedWid = initialWarehouseId;

  const [rows, setRows] = useState<WarehouseItemRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [selected, setSelected] = useState<WarehouseItemRow | null>(null);
  const [deleting, setDeleting] = useState<WarehouseItemRow | null>(null);

  const selectedWarehouse = options.find((o) => o.id === selectedWid) ?? null;

  useEffect(() => {
    if (!token) return;
    api.warehouseItems
      .options(token)
      .then(setOptions)
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
      });
  }, [token]);

  const load = useCallback(() => {
    if (!token || selectedWid == null) {
      setRows([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    setError(null);
    api.warehouseItems
      .list(token, { warehouse_id: selectedWid, q: q.trim() || undefined, page, size: PAGE_SIZE })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được mặt hàng trong kho.");
      })
      .finally(() => setLoading(false));
  }, [token, selectedWid, q, page]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedWid, page]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.warehouseItems.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được mặt hàng.");
      setDeleting(null);
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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const noWarehouses = options.length === 0;

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kho</p>
        <h1 className="md-page__title">Kho hàng</h1>
        <p className="md-page__sub">
          Chọn một kho (do admin cấu hình) để xem và nhập mặt hàng vào kho đó.
        </p>
      </header>

      {noWarehouses ? (
        <div className="banner banner--warn" role="status">
          Chưa có kho nào được cấu hình. Vui lòng nhờ admin thêm kho ở{" "}
          <strong>Cấu hình danh mục → Cấu hình kho hàng</strong> trước khi nhập mặt hàng.
        </div>
      ) : (
        <>
          {selectedWid == null ? (
            <div className="md-page__prompt">
              <p>
                Chọn một kho ở menu bên trái (mục <strong>Kho hàng</strong>) để xem và nhập mặt
                hàng.
              </p>
            </div>
          ) : (
            <>
              {/* Bước 2: quản lý mặt hàng trong kho đã chọn. */}
              <div className="md-page__toolbar">
                <div className="md-page__wh-badge">
                  <span className="md-page__mono">{selectedWarehouse?.code}</span>
                  <strong>{selectedWarehouse?.name}</strong>
                </div>
                <form className="md-page__search" onSubmit={onSearch}>
                  <input
                    className="input"
                    placeholder="Tìm theo tên mặt hàng..."
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                  />
                  <Button type="submit" variant="ghost">
                    Tìm
                  </Button>
                </form>

                <div className="md-page__toolbar-spacer" />
                {canCreate && (
                  <Button
                    variant="primary"
                    onClick={() => {
                      setSelected(null);
                      setMode("create");
                    }}
                  >
                    + Thêm mặt hàng
                  </Button>
                )}
              </div>

              {error && (
                <div className="banner banner--error" role="alert">
                  {error}
                </div>
              )}

              <div className="card md-page__tablewrap">
                <table className="md-page__table">
                  <thead>
                    <tr>
                      <th>Tên mặt hàng</th>
                      <th>Số lượng</th>
                      <th>Đơn vị</th>
                      <th>Ghi chú</th>
                      <th>Người nhập</th>
                      {(canUpdate || canDelete) && (
                        <th className="md-page__actions-col">Thao tác</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={6} className="md-page__status">
                          Đang tải dữ liệu...
                        </td>
                      </tr>
                    ) : rows.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="md-page__empty">
                          Kho này chưa có mặt hàng. {canCreate ? "Bấm “Thêm mặt hàng”." : ""}
                        </td>
                      </tr>
                    ) : (
                      rows.map((row) => (
                        <tr key={row.id} className="md-page__row">
                          <td>
                            <strong>{row.name}</strong>
                          </td>
                          <td>{row.quantity.toLocaleString("vi-VN")}</td>
                          <td>{row.unit}</td>
                          <td>{row.notes || <span className="md-page__muted">—</span>}</td>
                          <td>
                            {row.created_by_name ?? <span className="md-page__muted">—</span>}
                          </td>
                          {(canUpdate || canDelete) && (
                            <td className="md-page__actions-col">
                              {canUpdate && (
                                <button
                                  type="button"
                                  className="btn btn--ghost md-page__rowbtn"
                                  onClick={() => {
                                    setSelected(row);
                                    setMode("edit");
                                  }}
                                >
                                  Sửa
                                </button>
                              )}
                              {canDelete && (
                                <button
                                  type="button"
                                  className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger"
                                  onClick={() => setDeleting(row)}
                                >
                                  Xóa
                                </button>
                              )}
                            </td>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {!loading && rows.length > 0 && (
                <div className="md-page__pager">
                  <span className="md-page__muted">
                    Tổng số: {total} mặt hàng · Trang {page}/{totalPages}
                  </span>
                  <div className="md-page__pager-btns">
                    <button
                      type="button"
                      className="btn btn--ghost"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      ‹ Trước
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    >
                      Sau ›
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}

      {(mode === "create" || mode === "edit") && selectedWarehouse && (
        <WarehouseItemFormDialog
          existing={selected}
          warehouse={selectedWarehouse}
          onClose={() => {
            setMode(null);
            setSelected(null);
          }}
          onSaved={() => {
            setMode(null);
            setSelected(null);
            load();
          }}
        />
      )}

      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head">
              <h2>Xác nhận xóa mặt hàng</h2>
            </div>
            <div className="md-page__dialog-body">
              <p>
                Bạn có chắc chắn muốn xóa <strong>{deleting.name}</strong> khỏi kho{" "}
                {selectedWarehouse?.code}?
              </p>
              <div className="md-page__dialog-actions">
                <Button variant="ghost" onClick={() => setDeleting(null)}>
                  Hủy
                </Button>
                <Button variant="danger" onClick={handleDelete}>
                  Xác nhận xóa
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function WarehouseItemFormDialog({
  existing,
  warehouse,
  onClose,
  onSaved,
}: {
  existing: WarehouseItemRow | null;
  warehouse: WarehouseOption;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [name, setName] = useState(existing?.name ?? "");
  const [quantity, setQuantity] = useState(existing ? String(existing.quantity) : "");
  const [unit, setUnit] = useState(existing?.unit ?? "cái");
  const [notes, setNotes] = useState(existing?.notes ?? "");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    if (!name.trim()) return setError("Tên mặt hàng không được trống.");
    const qty = Number(quantity);
    if (quantity.trim() === "" || Number.isNaN(qty) || qty < 0)
      return setError("Số lượng phải là số ≥ 0.");

    const payload: WarehouseItemInput = {
      warehouse_id: warehouse.id,
      name: name.trim(),
      quantity: qty,
      unit: unit.trim() || "cái",
      notes: notes.trim() || null,
    };

    setSaving(true);
    try {
      if (isEdit && existing) {
        await api.warehouseItems.update(token, existing.id, payload);
      } else {
        await api.warehouseItems.create(token, payload);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu mặt hàng thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog md-page__dialog--sm card">
        <div className="md-page__dialog-head">
          <h2>
            {isEdit ? "Sửa mặt hàng" : "Thêm mặt hàng"} · {warehouse.code} {warehouse.name}
          </h2>
          <button type="button" className="md-page__close" onClick={onClose}>
            ✕
          </button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <label className="field">
            <span className="field__label">Tên mặt hàng *</span>
            <input
              className="input"
              placeholder="VD: Giấy Couche 150gsm"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Số lượng *</span>
              <input
                className="input"
                type="number"
                min={0}
                step="any"
                placeholder="VD: 100"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">Đơn vị</span>
              <input
                className="input"
                list="wh-units"
                placeholder="VD: cái, thùng, kg, ram"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              />
              <datalist id="wh-units">
                {["cái", "thùng", "kg", "ram", "tờ", "cuộn", "hộp", "mét"].map((u) => (
                  <option key={u} value={u} />
                ))}
              </datalist>
            </label>
          </div>

          <label className="field">
            <span className="field__label">Ghi chú</span>
            <textarea
              className="input"
              rows={2}
              placeholder="Ghi chú (tùy chọn)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>

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
              Lưu
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
