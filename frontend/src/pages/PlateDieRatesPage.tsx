import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type PlateDieRateRow,
  type PlateDieRateInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 15;

const PLATE_TYPES = [
  { value: "ban_kem_offset", label: "Bản kẽm Offset" },
  { value: "khuon_be", label: "Khuôn bế" },
  { value: "khuon_ep_kim", label: "Khuôn ép kim" },
];

const TECHNOLOGIES = [
  { value: "offset", label: "In Offset" },
  { value: "flexo", label: "In Flexo" },
  { value: "be", label: "Gia công Bế" },
  { value: "ep_kim", label: "Gia công Ép kim" },
];

const UNITS = [
  { value: "ban", label: "Bản kẽm" },
  { value: "bo", label: "Bộ khuôn" },
  { value: "cm2", label: "Centimét vuông (cm2)" },
];

export function PlateDieRatesPage() {
  const { token } = useAuth();
  
  const [rows, setRows] = useState<PlateDieRateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [plateTypeFilter, setPlateTypeFilter] = useState("");
  const [techFilter, setTechFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "close">(null);
  const [selected, setSelected] = useState<PlateDieRateRow | null>(null);
  const [deleting, setDeleting] = useState<PlateDieRateRow | null>(null);

  // Form states
  const [plateType, setPlateType] = useState("ban_kem_offset");
  const [technology, setTechnology] = useState("offset");
  const [unit, setUnit] = useState("ban");
  const [unitPrice, setUnitPrice] = useState("");
  const [setupFee, setSetupFee] = useState("0");
  const [minCharge, setMinCharge] = useState("0");
  const [reusable, setReusable] = useState(false);
  const [effectiveFrom, setEffectiveFrom] = useState("");
  
  const [effectiveTo, setEffectiveTo] = useState("");

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    
    const is_active = statusFilter === "active" ? true : statusFilter === "inactive" ? false : null;
    
    api.plateDieRates
      .list(token, {
        plate_type: plateTypeFilter || null,
        technology: techFilter || null,
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
        else setError("Không tải được bảng giá khuôn/bản kẽm.");
      })
      .finally(() => setLoading(false));
  }, [token, plateTypeFilter, techFilter, statusFilter, page]);

  useEffect(() => {
    load();
  }, [load]);

  function handleCreateClick() {
    setPlateType("ban_kem_offset");
    setTechnology("offset");
    setUnit("ban");
    setUnitPrice("");
    setSetupFee("0");
    setMinCharge("0");
    setReusable(false);
    setEffectiveFrom(new Date().toISOString().split("T")[0]);
    setMode("create");
  }

  async function handleCreateSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);

    const price = Number(unitPrice);
    if (isNaN(price) || price < 0) {
      setError("Đơn giá không hợp lệ.");
      return;
    }

    const payload: PlateDieRateInput = {
      plate_type: plateType,
      technology,
      unit,
      unit_price: price,
      setup_fee: Number(setupFee) || 0,
      min_charge: Number(minCharge) || 0,
      reusable,
      effective_from: effectiveFrom,
    };

    try {
      await api.plateDieRates.create(token, payload);
      setMode(null);
      setPage(1);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi thêm đơn giá khuôn/bản.");
    }
  }

  function handleCloseClick(row: PlateDieRateRow) {
    setSelected(row);
    setEffectiveTo(new Date().toISOString().split("T")[0]);
    setMode("close");
  }

  async function handleCloseSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !selected) return;
    setError(null);

    try {
      await api.plateDieRates.close(token, selected.id, effectiveTo);
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
      await api.plateDieRates.remove(token, deleting.id);
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
          Bạn không có quyền xem danh mục Bảng giá Khuôn & Bản (403).
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
            <h1 className="md-page__title">Bảng giá Khuôn & Bản kẽm</h1>
            <p className="md-page__sub">Quản lý đơn giá chế bản kẽm offset, khuôn bế, khuôn ép kim và cliché</p>
          </div>
          <Button variant="primary" onClick={handleCreateClick}>
            + Thêm khuôn/bản mới
          </Button>
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
            value={plateTypeFilter}
            onChange={(e) => { setPlateTypeFilter(e.target.value); setPage(1); }}
            aria-label="Lọc loại khuôn/bản"
          >
            <option value="">-- Tất cả khuôn/bản --</option>
            {PLATE_TYPES.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>

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
            Không tìm thấy dòng đơn giá khuôn/bản nào.
          </div>
        ) : (
          <table className="md-page__table">
            <thead>
              <tr>
                <th>Loại khuôn/bản</th>
                <th>Công nghệ gia công</th>
                <th>Đơn vị tính</th>
                <th>Đơn giá</th>
                <th>Phí Setup</th>
                <th>Phí tối thiểu (Min)</th>
                <th>Tái sử dụng</th>
                <th>Áp dụng từ</th>
                <th>Áp dụng đến</th>
                <th>Trạng thái</th>
                <th style={{ width: "120px" }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="md-page__price">
                    {PLATE_TYPES.find((p) => p.value === row.plate_type)?.label || row.plate_type}
                  </td>
                  <td>
                    {TECHNOLOGIES.find((t) => t.value === row.technology)?.label || row.technology}
                  </td>
                  <td>{UNITS.find((u) => u.value === row.unit)?.label || row.unit}</td>
                  <td className="md-page__price">{row.unit_price.toLocaleString()}đ</td>
                  <td>{row.setup_fee.toLocaleString()}đ</td>
                  <td>{row.min_charge.toLocaleString()}đ</td>
                  <td>
                    <span className={row.reusable ? "md-page__tag-calc" : "md-page__muted"}>
                      {row.reusable ? "Có" : "Không"}
                    </span>
                  </td>
                  <td>{row.effective_from}</td>
                  <td>{row.effective_to || <span className="md-page__muted">Vô hạn</span>}</td>
                  <td>
                    <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                      {row.is_active ? "Đang chạy" : "Đã đóng/Chưa chạy"}
                    </span>
                  </td>
                  <td className="md-page__actions-col">
                    {row.is_active && (
                      <button
                        type="button"
                        className="btn btn--secondary md-page__rowbtn"
                        onClick={() => handleCloseClick(row)}
                      >
                        Đóng giá
                      </button>
                    )}
                    {row.effective_from > todayStr && (
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
              ))}
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
              <h2>Thêm Cấu Hình Khuôn & Bản Kẽm Mới</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <div className="md-page__form-grid">
                <div>
                  <label className="label">Loại khuôn/bản</label>
                  <select
                    className="input select"
                    value={plateType}
                    onChange={(e) => setPlateType(e.target.value)}
                    required
                  >
                    {PLATE_TYPES.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">Công nghệ gia công</label>
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
                  <label className="label">Đơn giá khuôn/bản (VNĐ)</label>
                  <input
                    type="number"
                    className="input"
                    value={unitPrice}
                    onChange={(e) => setUnitPrice(e.target.value)}
                    placeholder="VD: 120000"
                    required
                    min="0"
                  />
                </div>

                <div>
                  <label className="label">Phí setup cố định (VNĐ)</label>
                  <input
                    type="number"
                    className="input"
                    value={setupFee}
                    onChange={(e) => setSetupFee(e.target.value)}
                    placeholder="VD: 20000"
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
                    placeholder="VD: 50000"
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

                <div className="md-page__toggle-wrap">
                  <input
                    type="checkbox"
                    id="reusable"
                    checked={reusable}
                    onChange={(e) => setReusable(e.target.checked)}
                  />
                  <label htmlFor="reusable">Có thể tái sử dụng cho đơn hàng sau</label>
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
              <p>Bạn đang dừng hiệu lực đơn giá áp dụng cho <strong>{selected.plate_type} - {selected.technology}</strong>.</p>
              
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
