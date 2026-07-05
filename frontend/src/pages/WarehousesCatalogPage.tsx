import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, api, type WarehouseRow, type WarehouseInput } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

// Cấu hình kho hàng (admin): danh mục kho với mã số / tên / mô tả / ghi chú. Về sau module
// "Kho hàng" vận hành (phiếu nhập/xuất) sẽ chọn kho từ danh mục này.
export function WarehousesCatalogPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("dm_kho", "create");
  const canUpdate = can("dm_kho", "update");
  const canDelete = can("dm_kho", "delete");

  const [rows, setRows] = useState<WarehouseRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [selected, setSelected] = useState<WarehouseRow | null>(null);
  const [deleting, setDeleting] = useState<WarehouseRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.warehouses
      .list(token, { q: q.trim() || undefined, sort: "code", page, size: PAGE_SIZE })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục kho hàng.");
      })
      .finally(() => setLoading(false));
  }, [token, q, page]);

  useEffect(() => {
    load();
  }, [load]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.warehouses.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được kho.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Cấu hình kho hàng (403).
        </div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Cấu hình kho hàng</h1>
        <p className="md-page__sub">
          Khai báo danh mục kho (mã số, tên, mô tả, ghi chú). Các kho khai báo ở đây sẽ dùng cho
          module Kho hàng vận hành (phiếu nhập / xuất).
        </p>
      </header>

      <div className="md-page__toolbar">
        <form className="md-page__search" onSubmit={onSearch}>
          <input
            className="input"
            placeholder="Tìm theo tên / mã kho..."
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
            + Tạo kho mới
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
              <th>Mã số</th>
              <th>Tên kho</th>
              <th>Mô tả</th>
              <th>Ghi chú</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
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
                  Chưa có kho nào. Bấm “Tạo kho mới” để thêm.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="md-page__row"
                  style={canUpdate ? undefined : { cursor: "default" }}
                  onClick={
                    canUpdate
                      ? () => {
                          setSelected(row);
                          setMode("edit");
                        }
                      : undefined
                  }
                >
                  <td className="md-page__mono">{row.code}</td>
                  <td>
                    <strong>{row.name}</strong>
                  </td>
                  <td>{row.description || <span className="md-page__muted">—</span>}</td>
                  <td>{row.notes || <span className="md-page__muted">—</span>}</td>
                  <td>
                    <span
                      className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}
                    >
                      {row.is_active ? "Kích hoạt" : "Đã ẩn"}
                    </span>
                  </td>
                  <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
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
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng số: {total} kho · Trang {page}/{totalPages}
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

      {(mode === "create" || mode === "edit") && (
        <WarehouseFormDialog
          existing={selected}
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
              <h2>Xác nhận xóa kho</h2>
            </div>
            <div className="md-page__dialog-body">
              <p>
                Bạn có chắc chắn muốn xóa vĩnh viễn kho <strong>{deleting.name}</strong> (
                {deleting.code})?
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

function WarehouseFormDialog({
  existing,
  onClose,
  onSaved,
}: {
  existing: WarehouseRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    if (!name.trim()) return setError("Tên kho không được trống.");

    const payload: WarehouseInput = {
      name: name.trim(),
      description: description.trim() || null,
      notes: notes.trim() || null,
      is_active: isActive,
    };

    setSaving(true);
    try {
      if (isEdit && existing) {
        await api.warehouses.update(token, existing.id, payload);
      } else {
        await api.warehouses.create(token, payload);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu kho thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog md-page__dialog--sm card">
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Sửa kho: ${existing?.code}` : "Tạo kho mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>
            ✕
          </button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {isEdit && (
            <label className="field">
              <span className="field__label">Mã số</span>
              <input className="input" value={existing?.code ?? ""} disabled readOnly />
            </label>
          )}

          <label className="field">
            <span className="field__label">Tên kho *</span>
            <input
              className="input"
              placeholder="VD: Kho tổng, Kho thành phẩm"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="field__label">Mô tả</span>
            <textarea
              className="input"
              rows={2}
              placeholder="VD: Kho chứa nguyên vật liệu đầu vào"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="field__label">Ghi chú</span>
            <textarea
              className="input"
              rows={2}
              placeholder="Ghi chú nội bộ (tùy chọn)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="field__label">Trạng thái</span>
            <div className="md-page__toggle-wrap">
              <input
                type="checkbox"
                id="wh-active-check"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <label htmlFor="wh-active-check">Kích hoạt kho</label>
            </div>
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
              Lưu kho
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
