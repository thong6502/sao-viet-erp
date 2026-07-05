import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type ClickInkRateRow,
  type ClickInkRateInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 15;

const TECHNOLOGIES = [
  { value: "offset", label: "Offset" },
  { value: "digital", label: "Kỹ thuật số" },
  { value: "large_format", label: "Khổ lớn" },
  { value: "flexo", label: "Flexo" },
];

const COLOR_TYPES = [
  { value: "cmyk", label: "Bốn màu (CMYK)" },
  { value: "grayscale", label: "Trắng đen (Grayscale)" },
  { value: "spot", label: "Màu pha (Spot)" },
  { value: "white", label: "Màu trắng (White)" },
];

const UNITS = [
  { value: "click", label: "Click (Trang in)" },
  { value: "trang", label: "Trang" },
  { value: "m2", label: "Mét vuông (m2)" },
  { value: "ml", label: "Mililít (ml)" },
];

export function ClickInkRatesPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("dm_gia_click", "create");
  const canUpdate = can("dm_gia_click", "update");
  const canDelete = can("dm_gia_click", "delete");

  const [rows, setRows] = useState<ClickInkRateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [techFilter, setTechFilter] = useState("");
  const [machineFilter, setMachineFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  
  const [machines, setMachines] = useState<{ id: number; name: string; machine_type: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "close">(null);
  const [selected, setSelected] = useState<ClickInkRateRow | null>(null);
  const [deleting, setDeleting] = useState<ClickInkRateRow | null>(null);

  // Form states
  const [technology, setTechnology] = useState("digital");
  const [colorType, setColorType] = useState("cmyk");
  const [machineId, setMachineId] = useState("");
  const [unit, setUnit] = useState("click");
  const [unitPrice, setUnitPrice] = useState("");
  const [setupFee, setSetupFee] = useState("0");
  const [minCharge, setMinCharge] = useState("0");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  
  const [effectiveTo, setEffectiveTo] = useState("");

  const loadMachines = useCallback(() => {
    if (!token) return;
    api.machines.list(token, { page: 1, size: 200 })
      .then((res) => setMachines(res.items))
      .catch(() => {});
  }, [token]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    
    const is_active = statusFilter === "active" ? true : statusFilter === "inactive" ? false : null;
    
    api.clickInkRates
      .list(token, {
        technology: techFilter || null,
        machine_id: machineFilter ? Number(machineFilter) : null,
        is_active,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được bảng giá click/mực.");
      })
      .finally(() => setLoading(false));
  }, [token, techFilter, machineFilter, statusFilter, page]);

  useEffect(() => {
    load();
    loadMachines();
  }, [load, loadMachines]);

  function handleCreateClick() {
    setTechnology("digital");
    setColorType("cmyk");
    setMachineId("");
    setUnit("click");
    setUnitPrice("");
    setSetupFee("0");
    setMinCharge("0");
    setEffectiveFrom(new Date().toISOString().split("T")[0]);
    setMode("create");
  }

  async function handleCreateSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);

    const price = Number(unitPrice);
    if (isNaN(price) || price < 0) {
      setError("Đơn giá click không hợp lệ.");
      return;
    }

    const payload: ClickInkRateInput = {
      technology,
      color_type: colorType,
      machine_id: machineId ? Number(machineId) : null,
      unit,
      unit_price: price,
      setup_fee: Number(setupFee) || 0,
      min_charge: Number(minCharge) || 0,
      effective_from: effectiveFrom,
    };

    try {
      await api.clickInkRates.create(token, payload);
      setMode(null);
      setPage(1);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi thêm đơn giá click.");
    }
  }

  function handleCloseClick(row: ClickInkRateRow) {
    setSelected(row);
    setEffectiveTo(new Date().toISOString().split("T")[0]);
    setMode("close");
  }

  async function handleCloseSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !selected) return;
    setError(null);

    try {
      await api.clickInkRates.close(token, selected.id, effectiveTo);
      setMode(null);
      setSelected(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi đóng dòng giá.");
    }
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    setError(null);
    try {
      await api.clickInkRates.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi xóa dòng giá.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <div className="md-page">
        <div className="banner banner--error">
          Bạn không có quyền xem danh mục Bảng giá Click (403).
        </div>
      </div>
    );
  }

  const todayStr = new Date().toISOString().split("T")[0];

  return (
    <div className="md-page">
      <div className="md-page__head">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1 className="md-page__title">Bảng giá Click & Mực</h1>
            <p className="md-page__sub">Quản lý đơn giá click, mực in kỹ thuật số và các công nghệ in khác</p>
          </div>
          {canCreate && (
            <Button variant="primary" onClick={handleCreateClick}>
              + Thêm đơn giá click
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      {/* Filters Toolbar */}
      <div className="md-page__toolbar">
        <div className="md-page__filter">
          <select
            className="input select"
            value={techFilter}
            onChange={(e) => { setTechFilter(e.target.value); setPage(1); }}
            aria-label="Lọc công nghệ"
          >
            <option value="">-- Tất cả công nghệ --</option>
            {TECHNOLOGIES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <div className="md-page__filter">
          <select
            className="input select"
            value={machineFilter}
            onChange={(e) => { setMachineFilter(e.target.value); setPage(1); }}
            aria-label="Lọc máy in"
          >
            <option value="">-- Tất cả máy in --</option>
            {machines.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>

        <div className="md-page__filter">
          <select
            className="input select"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            aria-label="Lọc trạng thái"
          >
            <option value="">-- Tất cả trạng thái --</option>
            <option value="active">Đang hiệu lực</option>
            <option value="inactive">Hết hiệu lực / Tương lai</option>
          </select>
        </div>
      </div>

      {/* Grid table */}
      <div className="card md-page__tablewrap">
        {loading ? (
          <div style={{ padding: "40px", textAlign: "center" }}>Đang tải bảng giá...</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center" }} className="md-page__muted">
            Không tìm thấy dòng đơn giá nào.
          </div>
        ) : (
          <table className="md-page__table">
            <thead>
              <tr>
                <th>Công nghệ</th>
                <th>Loại màu</th>
                <th>Máy in áp dụng</th>
                <th>Đơn vị tính</th>
                <th>Đơn giá click</th>
                <th>Phí Setup</th>
                <th>Phí tối thiểu (Min)</th>
                <th>Áp dụng từ</th>
                <th>Áp dụng đến</th>
                <th>Trạng thái</th>
                <th style={{ width: "120px" }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const machine = machines.find((m) => m.id === row.machine_id);
                return (
                  <tr key={row.id}>
                    <td className="md-page__mono">
                      {TECHNOLOGIES.find((t) => t.value === row.technology)?.label || row.technology}
                    </td>
                    <td>
                      {COLOR_TYPES.find((c) => c.value === row.color_type)?.label || row.color_type}
                    </td>
                    <td>
                      {machine ? (
                        <span className="md-page__tag-tech">{machine.name}</span>
                      ) : (
                        <span className="md-page__muted">Áp dụng chung</span>
                      )}
                    </td>
                    <td>{UNITS.find((u) => u.value === row.unit)?.label || row.unit}</td>
                    <td className="md-page__price">{row.unit_price.toLocaleString()}đ</td>
                    <td>{row.setup_fee.toLocaleString()}đ</td>
                    <td>{row.min_charge.toLocaleString()}đ</td>
                    <td>{row.effective_from}</td>
                    <td>{row.effective_to || <span className="md-page__muted">Vô hạn</span>}</td>
                    <td>
                      <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                        {row.is_active ? "Đang chạy" : "Đã đóng/Chưa chạy"}
                      </span>
                    </td>
                    <td className="md-page__actions-col">
                      {canUpdate && row.is_active && (
                        <button
                          type="button"
                          className="btn btn--secondary md-page__rowbtn"
                          onClick={() => handleCloseClick(row)}
                        >
                          Đóng giá
                        </button>
                      )}
                      {canDelete && row.effective_from > todayStr && (
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
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="md-page__pager">
          <span>Tổng số: <strong>{total}</strong> dòng giá</span>
          <div className="md-page__pager-btns">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Trước
            </Button>
            <span style={{ alignSelf: "center", padding: "0 10px" }}>Trang {page} / {Math.ceil(total / PAGE_SIZE)}</span>
            <Button
              variant="secondary"
              disabled={page * PAGE_SIZE >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              Sau
            </Button>
          </div>
        </div>
      )}

      {/* Dialog: Create */}
      {mode === "create" && (
        <div className="md-page__overlay">
          <form className="card md-page__dialog" onSubmit={handleCreateSubmit}>
            <div className="md-page__dialog-head">
              <h2>Thêm Đơn Giá Click & Mực Mới</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <div className="md-page__form-grid">
                <div>
                  <label className="label">Công nghệ in</label>
                  <select
                    className="input select"
                    value={technology}
                    onChange={(e) => setTechnology(e.target.value)}
                    required
                  >
                    {TECHNOLOGIES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">Loại màu</label>
                  <select
                    className="input select"
                    value={colorType}
                    onChange={(e) => setColorType(e.target.value)}
                    required
                  >
                    {COLOR_TYPES.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">Máy in áp dụng (Để trống nếu áp dụng chung)</label>
                  <select
                    className="input select"
                    value={machineId}
                    onChange={(e) => setMachineId(e.target.value)}
                  >
                    <option value="">-- Áp dụng chung cho công nghệ --</option>
                    {/* lọc theo machine_type (đúng công nghệ), không theo tên máy như trước (máy
                        "Mitsubishi Daiya 4 màu" không chứa chữ "offset" nên trước đây bị ẩn). */}
                    {machines.filter((m) => m.machine_type === technology).map((m) => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">Đơn vị tính</label>
                  <select
                    className="input select"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                    required
                  >
                    {UNITS.map((u) => (
                      <option key={u.value} value={u.value}>{u.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">Đơn giá click (VNĐ)</label>
                  <input
                    type="number"
                    className="input"
                    value={unitPrice}
                    onChange={(e) => setUnitPrice(e.target.value)}
                    placeholder="VD: 250"
                    required
                    min="0"
                  />
                </div>

                <div>
                  <label className="label">Phí setup ban đầu (VNĐ)</label>
                  <input
                    type="number"
                    className="input"
                    value={setupFee}
                    onChange={(e) => setSetupFee(e.target.value)}
                    placeholder="VD: 15000"
                    min="0"
                  />
                </div>

                <div>
                  <label className="label">Phí tối thiểu / Min Charge (VNĐ)</label>
                  <input
                    type="number"
                    className="input"
                    value={minCharge}
                    onChange={(e) => setMinCharge(e.target.value)}
                    placeholder="VD: 5000"
                    min="0"
                  />
                </div>

                <div>
                  <label className="label">Ngày hiệu lực bắt đầu</label>
                  <input
                    type="date"
                    className="input"
                    value={effectiveFrom}
                    onChange={(e) => setEffectiveFrom(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="md-page__dialog-actions">
                <Button variant="secondary" type="button" onClick={() => setMode(null)}>
                  Hủy bỏ
                </Button>
                <Button variant="primary" type="submit">
                  Lưu thiết lập
                </Button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Dialog: Close Rate */}
      {mode === "close" && selected && (
        <div className="md-page__overlay">
          <form className="card md-page__dialog md-page__dialog--sm" onSubmit={handleCloseSubmit}>
            <div className="md-page__dialog-head">
              <h2>Đóng Hiệu Lực Đơn Giá</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn đang dừng hiệu lực đơn giá click áp dụng cho <strong>{selected.technology} - {selected.color_type}</strong>.</p>
              
              <div>
                <label className="label">Ngày kết thúc hiệu lực (Không bao gồm ngày này)</label>
                <input
                  type="date"
                  className="input"
                  value={effectiveTo}
                  onChange={(e) => setEffectiveTo(e.target.value)}
                  required
                />
              </div>

              <div className="md-page__dialog-actions">
                <Button variant="secondary" type="button" onClick={() => setMode(null)}>
                  Hủy bỏ
                </Button>
                <Button variant="danger" type="submit">
                  Xác nhận đóng
                </Button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Dialog: Delete Confirmation */}
      {deleting && (
        <div className="md-page__overlay">
          <div className="card md-page__dialog md-page__dialog--sm">
            <div className="md-page__dialog-head">
              <h2>Xác Nhận Xóa Đơn Giá</h2>
              <button type="button" className="md-page__close" onClick={() => setDeleting(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa dòng giá tương lai này? Thao tác này sẽ xóa vĩnh viễn cấu hình khỏi hệ thống.</p>
              <div className="md-page__dialog-actions">
                <Button variant="secondary" onClick={() => setDeleting(null)}>
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
    </div>
  );
}
