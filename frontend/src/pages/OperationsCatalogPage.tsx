import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type OperationCatalogRow,
  type OperationCatalogInput,
  type OperationCatalogRateInput,
  type OperationCatalogRateRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

const OP_TYPES = [
  { value: "in", label: "In ấn (Printing)" },
  { value: "can_mang", label: "Cán màng (Lamination)" },
  { value: "be", label: "Bế hình / Đột (Die-cutting)" },
  { value: "gap", label: "Gấp nếp / Cấn (Folding)" },
  { value: "dong_cuon", label: "Đóng cuốn (Binding)" },
  { value: "dong_goi", label: "Đóng gói (Packaging)" },
  { value: "other", label: "Gia công khác" },
];

export function OperationsCatalogPage() {
  const { token } = useAuth();

  const [rows, setRows] = useState<OperationCatalogRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort] = useState("code");
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit" | "rates">(null);
  const [selected, setSelected] = useState<OperationCatalogRow | null>(null);
  const [deleting, setDeleting] = useState<OperationCatalogRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.operations
      .list(token, {
        q: q.trim() || undefined,
        operation_type: typeFilter || null,
        sort,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục công đoạn.");
      })
      .finally(() => setLoading(false));
  }, [token, q, typeFilter, sort, page]);

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
      await api.operations.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được công đoạn.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Công đoạn gia công (403).
        </div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Công đoạn gia công</h1>
        <p className="md-page__sub">
          Quản lý toàn bộ danh mục công đoạn thành phẩm (cán màng, cấn gấp, bế, đóng cuốn, đóng gói...) và biểu giá.
        </p>
      </header>

      <div className="md-page__toolbar">
        <form className="md-page__search" onSubmit={onSearch}>
          <input
            className="input"
            placeholder="Tìm theo tên / mã công đoạn..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Button type="submit" variant="ghost">Tìm</Button>
        </form>

        <select
          className="input md-page__filter"
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
        >
          <option value="">Tất cả loại công đoạn</option>
          {OP_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        <div className="md-page__toolbar-spacer" />
        <Button
          variant="primary"
          onClick={() => { setSelected(null); setMode("create"); }}
        >
          + Tạo công đoạn mới
        </Button>
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
              <th>Mã công đoạn</th>
              <th>Tên công đoạn</th>
              <th>Loại gia công</th>
              <th>Đơn vị tính</th>
              <th>Gia công ngoài (Outsource)</th>
              <th>Đơn giá chạy</th>
              <th>Phí tối thiểu (Min charge)</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="md-page__status">Đang tải dữ liệu...</td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="md-page__empty">Không tìm thấy công đoạn nào.</td>
              </tr>
            ) : (
              rows.map((row) => {
                const activeRate = row.rates.find((r) => r.effective_to === null);
                return (
                  <tr key={row.id} className="md-page__row" onClick={() => { setSelected(row); setMode("edit"); }}>
                    <td className="md-page__mono">{row.code}</td>
                    <td><strong>{row.name}</strong></td>
                    <td>{OP_TYPES.find((t) => t.value === row.operation_type)?.label ?? row.operation_type}</td>
                    <td>{row.unit}</td>
                    <td>
                      <span className={`md-page__status-badge ${row.allow_outsource ? "is-active" : "is-inactive"}`}>
                        {row.allow_outsource ? "Cho phép" : "Không"}
                      </span>
                    </td>
                    <td>
                      {activeRate ? (
                        <span className="md-page__price">
                          {activeRate.run_rate.toLocaleString("vi-VN")} đ/{row.unit}
                        </span>
                      ) : (
                        <span className="md-page__danger-text">Chưa cấu hình</span>
                      )}
                    </td>
                    <td>
                      {activeRate ? (
                        <span className="md-page__price">
                          {activeRate.min_charge.toLocaleString("vi-VN")} đ
                        </span>
                      ) : (
                        <span className="md-page__muted">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                        {row.is_active ? "Kích hoạt" : "Đã ẩn"}
                      </span>
                    </td>
                    <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => { setSelected(row); setMode("edit"); }}
                      >
                        Sửa
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => { setSelected(row); setMode("rates"); }}
                      >
                        Biểu giá
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger"
                        onClick={() => setDeleting(row)}
                      >
                        Xóa
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng số: {total} công đoạn · Trang {page}/{totalPages}
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

      {/* Create / Edit Dialog */}
      {(mode === "create" || mode === "edit") && (
        <OperationFormDialog
          existing={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Operation Rates Dialog */}
      {mode === "rates" && selected && (
        <OperationRatesDialog
          operation={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Delete Confirmation */}
      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head">
              <h2>Xác nhận xóa công đoạn</h2>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa vĩnh viễn công đoạn <strong>{deleting.name}</strong> ({deleting.code})?</p>
              <div className="md-page__dialog-actions">
                <Button variant="ghost" onClick={() => setDeleting(null)}>Hủy</Button>
                <Button variant="danger" onClick={handleDelete}>Xác nhận xóa</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function OperationFormDialog({
  existing,
  onClose,
  onSaved,
}: {
  existing: OperationCatalogRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [name, setName] = useState(existing?.name ?? "");
  const [opType, setOpType] = useState(existing?.operation_type ?? "can_mang");
  const [unit, setUnit] = useState(existing?.unit ?? "m2");
  const [allowOutsource, setAllowOutsource] = useState(existing?.allow_outsource ?? false);
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    if (!name.trim()) return setError("Tên công đoạn không được trống.");
    if (!unit.trim()) return setError("Đơn vị tính không được trống.");

    const payload: OperationCatalogInput = {
      name: name.trim(),
      operation_type: opType,
      unit: unit.trim(),
      allow_outsource: allowOutsource,
      is_active: isActive,
    };

    setSaving(true);
    try {
      if (isEdit && existing) {
        await api.operations.update(token, existing.id, payload);
      } else {
        await api.operations.create(token, payload);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu công đoạn thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog md-page__dialog--sm card">
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Sửa công đoạn: ${existing?.code}` : "Tạo công đoạn gia công mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <label className="field">
            <span className="field__label">Tên công đoạn gia công *</span>
            <input
              className="input"
              placeholder="VD: Cán màng mờ 1 mặt"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="field__label">Phân loại công đoạn</span>
            <select className="input" value={opType} onChange={(e) => setOpType(e.target.value)} disabled={isEdit}>
              {OP_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field__label">Đơn vị đo lường *</span>
            <input
              className="input"
              placeholder="VD: m2, luot, to, cai"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="field__label">Tùy chọn gia công</span>
            <div className="md-page__toggle-wrap">
              <input
                type="checkbox"
                id="op-outsource-check"
                checked={allowOutsource}
                onChange={(e) => setAllowOutsource(e.target.checked)}
              />
              <label htmlFor="op-outsource-check">Cho phép Outsource ngoài</label>
            </div>
            <div className="md-page__toggle-wrap">
              <input
                type="checkbox"
                id="op-active-check"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <label htmlFor="op-active-check">Kích hoạt hoạt động</label>
            </div>
          </label>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu công đoạn</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function OperationRatesDialog({
  operation,
  onClose,
  onSaved,
}: {
  operation: OperationCatalogRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();

  const [rates, setRates] = useState<OperationCatalogRateRow[]>([]);
  const [setupFee, setSetupFee] = useState("0");
  const [runRate, setRunRate] = useState("");
  const [laborRate, setLaborRate] = useState("0");
  const [minCharge, setMinCharge] = useState("0");
  const [speed, setSpeed] = useState("0");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().split("T")[0]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRates = useCallback(() => {
    if (!token) return;
    api.operations
      .get(token, operation.id)
      .then((res) => setRates(res.rates))
      .catch(() => setError("Không tải được biểu giá."));
  }, [token, operation.id]);

  useEffect(() => {
    loadRates();
  }, [loadRates]);

  async function handleAddRate(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    const rr = Number(runRate);
    if (!runRate.trim() || rr < 0) return setError("Vui lòng nhập đơn giá chạy máy hợp lệ.");

    const payload: OperationCatalogRateInput = {
      setup_fee: Number(setupFee) || 0,
      run_rate: rr,
      labor_rate: Number(laborRate) || 0,
      min_charge: Number(minCharge) || 0,
      speed: Number(speed) || 0,
      effective_from: effectiveFrom,
    };

    setSaving(true);
    try {
      await api.operations.addRate(token, operation.id, payload);
      setRunRate("");
      loadRates();
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu đơn giá mới thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>Quản lý đơn giá công đoạn: {operation.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <form className="md-page__rates-form" onSubmit={handleAddRate}>
            <h3 className="md-page__section-title">Thiết lập đơn giá gia công mới</h3>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Phí setup cố định (đ)</span>
                <input
                  className="input"
                  type="number"
                  value={setupFee}
                  onChange={(e) => setSetupFee(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Đơn giá chạy chạy máy (đ/{operation.unit}) *</span>
                <input
                  className="input"
                  type="number"
                  placeholder="VD: 3500"
                  value={runRate}
                  onChange={(e) => setRunRate(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Đơn giá nhân công (đ)</span>
                <input
                  className="input"
                  type="number"
                  value={laborRate}
                  onChange={(e) => setLaborRate(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Phí tối thiểu / job (đ)</span>
                <input
                  className="input"
                  type="number"
                  value={minCharge}
                  onChange={(e) => setMinCharge(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Tốc độ chạy máy (đv/h)</span>
                <input
                  className="input"
                  type="number"
                  value={speed}
                  onChange={(e) => setSpeed(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Ngày hiệu lực *</span>
                <input
                  className="input"
                  type="date"
                  value={effectiveFrom}
                  onChange={(e) => setEffectiveFrom(e.target.value)}
                />
              </label>
              <div className="md-page__field-btn-align md-page__form-wide">
                <Button type="submit" variant="primary" loading={saving}>Áp dụng đơn giá</Button>
              </div>
            </div>
          </form>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="md-page__costs-history">
            <h3 className="md-page__section-title">Lịch sử biểu giá</h3>
            <div className="md-page__tablewrap">
              <table className="md-page__table">
                <thead>
                  <tr>
                    <th>Phí setup (đ)</th>
                    <th>Giá chạy (đ/{operation.unit})</th>
                    <th>Giá nhân công (đ)</th>
                    <th>Cước tối thiểu (đ)</th>
                    <th>Tốc độ (đv/h)</th>
                    <th>Từ ngày</th>
                    <th>Đến ngày</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="md-page__empty">Chưa có biểu giá lịch sử nào.</td>
                    </tr>
                  ) : (
                    rates.map((r) => {
                      const isActive = r.effective_to === null;
                      return (
                        <tr key={r.id}>
                          <td>{r.setup_fee.toLocaleString("vi-VN")} đ</td>
                          <td><strong>{r.run_rate.toLocaleString("vi-VN")} đ</strong></td>
                          <td>{r.labor_rate.toLocaleString("vi-VN")} đ</td>
                          <td>{r.min_charge.toLocaleString("vi-VN")} đ</td>
                          <td>{r.speed ? `${r.speed.toLocaleString("vi-VN")} đv/h` : "—"}</td>
                          <td>{r.effective_from}</td>
                          <td>{r.effective_to ?? <span className="md-page__status-badge is-active">Hiện hành</span>}</td>
                          <td>
                            {isActive ? (
                              <span className="md-page__status-badge is-active">Đang áp dụng</span>
                            ) : (
                              <span className="md-page__muted">Hết hạn</span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
