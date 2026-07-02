import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type NormRow,
  type NormInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 15;

const NORM_KEYS = [
  { value: "yield_rate", label: "Tỷ lệ thành phẩm (Yield Rate)" },
  { value: "running_waste_pct", label: "Tỷ lệ hao hụt chạy bài (Running Waste %)" },
  { value: "makeready_per_color_side", label: "Hao hụt Setup (Makeready per color/side)" },
  // #10 — bù hao theo công đoạn (gắn với Công đoạn/operation_key); engine đọc key này cho từng CĐ.
  { value: "waste_pct_of_operation", label: "Tỷ lệ bù hao công đoạn (Waste % per operation)" },
];

export function NormsCatalogPage() {
  const { token } = useAuth();
  
  const [rows, setRows] = useState<NormRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [normKeyFilter, setNormKeyFilter] = useState("");
  const [productTypeFilter, setProductTypeFilter] = useState("");
  const [machineFilter, setMachineFilter] = useState("");
  const [operationFilter, setOperationFilter] = useState("");
  const [onlyCurrent, setOnlyCurrent] = useState(true);

  // References
  const [productTypes, setProductTypes] = useState<{ product_type: string; name: string }[]>([]);
  const [machines, setMachines] = useState<{ id: number; name: string }[]>([]);
  const [operations, setOperations] = useState<{ id: number; name: string; code: string }[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "close">(null);
  const [selected, setSelected] = useState<NormRow | null>(null);
  const [deleting, setDeleting] = useState<NormRow | null>(null);

  // Form states
  const [normKey, setNormKey] = useState("yield_rate");
  const [value, setValue] = useState("");
  const [productType, setProductType] = useState("");
  const [machineId, setMachineId] = useState("");
  const [operationId, setOperationId] = useState("");
  const [operationKey, setOperationKey] = useState("");
  const [qtyMin, setQtyMin] = useState("");
  const [qtyMax, setQtyMax] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [note, setNote] = useState("");
  
  // Context dynamic fields (e.g. colors, sides)
  const [contextColors, setContextColors] = useState("");
  const [contextSides, setContextSides] = useState("");

  const [effectiveTo, setEffectiveTo] = useState("");

  const loadReferences = useCallback(() => {
    if (!token) return;
    
    // Product types
    api.productTypesCatalog.list(token, { page: 1, size: 200 })
      .then((res) => setProductTypes(res.items))
      .catch(() => {});

    // Machines
    api.machines.list(token, { page: 1, size: 200 })
      .then((res) => setMachines(res.items))
      .catch(() => {});

    // Operations
    api.operations.list(token, { page: 1, size: 200 })
      .then((res) => setOperations(res.items))
      .catch(() => {});
  }, [token]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);

    api.norms
      .list(token, {
        norm_key: normKeyFilter || null,
        product_type: productTypeFilter || null,
        machine_id: machineFilter ? Number(machineFilter) : null,
        operation_id: operationFilter ? Number(operationFilter) : null,
        only_current: onlyCurrent,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục định mức & hao hụt.");
      })
      .finally(() => setLoading(false));
  }, [token, normKeyFilter, productTypeFilter, machineFilter, operationFilter, onlyCurrent, page]);

  useEffect(() => {
    load();
    loadReferences();
  }, [load, loadReferences]);

  function handleCreateClick() {
    setNormKey("yield_rate");
    setValue("");
    setProductType("");
    setMachineId("");
    setOperationId("");
    setOperationKey("");
    setQtyMin("");
    setQtyMax("");
    setContextColors("");
    setContextSides("");
    setNote("");
    setEffectiveFrom(new Date().toISOString().split("T")[0]);
    setMode("create");
  }

  async function handleCreateSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);

    const valNum = Number(value);
    if (isNaN(valNum) || valNum < 0) {
      setError("Giá trị định mức không hợp lệ.");
      return;
    }

    if (operationId && operationKey) {
      setError("Chỉ được nhập một trong hai: Công đoạn hệ thống hoặc từ khóa công đoạn.");
      return;
    }

    // Build context dictionary
    const context: Record<string, any> = {};
    if (contextColors) context.colors = Number(contextColors);
    if (contextSides) context.sides = Number(contextSides);

    const payload: NormInput = {
      norm_key: normKey,
      value: valNum,
      product_type: productType || null,
      machine_id: machineId ? Number(machineId) : null,
      operation_id: operationId ? Number(operationId) : null,
      operation_key: operationKey || null,
      qty_min: qtyMin ? Number(qtyMin) : null,
      qty_max: qtyMax ? Number(qtyMax) : null,
      context: Object.keys(context).length > 0 ? context : null,
      effective_from: effectiveFrom,
      note: note || null,
    };

    try {
      await api.norms.create(token, payload);
      setMode(null);
      setPage(1);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi thêm định mức.");
    }
  }

  function handleCloseClick(row: NormRow) {
    setSelected(row);
    setEffectiveTo(new Date().toISOString().split("T")[0]);
    setMode("close");
  }

  async function handleCloseSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !selected) return;
    setError(null);

    try {
      await api.norms.close(token, selected.id, effectiveTo);
      setMode(null);
      setSelected(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi đóng định mức.");
    }
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    setError(null);
    try {
      await api.norms.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi xóa định mức.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <div className="md-page">
        <div className="banner banner--error">
          Bạn không có quyền xem danh mục Định mức & Bù hao (403).
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
            <h1 className="md-page__title">Định mức & Bù hao hao hụt</h1>
            <p className="md-page__sub">Quản lý tỷ lệ thành phẩm, hao hụt chạy bài và setup theo sản phẩm/máy/công đoạn</p>
          </div>
          <Button variant="primary" onClick={handleCreateClick}>
            + Thêm quy tắc định mức
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
        <div className="md-page__filter" style={{ width: "240px" }}>
          <select
            className="input select"
            value={normKeyFilter}
            onChange={(e) => { setNormKeyFilter(e.target.value); setPage(1); }}
            aria-label="Lọc loại định mức"
          >
            <option value="">-- Tất cả mã định mức --</option>
            {NORM_KEYS.map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </select>
        </div>

        <div className="md-page__filter">
          <select
            className="input select"
            value={productTypeFilter}
            onChange={(e) => { setProductTypeFilter(e.target.value); setPage(1); }}
            aria-label="Lọc loại sản phẩm"
          >
            <option value="">-- Tất cả loại sản phẩm --</option>
            {productTypes.map((p) => (
              <option key={p.product_type} value={p.product_type}>{p.name}</option>
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
            value={operationFilter}
            onChange={(e) => { setOperationFilter(e.target.value); setPage(1); }}
            aria-label="Lọc công đoạn"
          >
            <option value="">-- Tất cả công đoạn --</option>
            {operations.map((o) => (
              <option key={o.id} value={o.id}>{o.name} ({o.code})</option>
            ))}
          </select>
        </div>

        <div className="md-page__toggle-wrap" style={{ padding: "0 var(--sp-2)" }}>
          <input
            type="checkbox"
            id="onlyCurrent"
            checked={onlyCurrent}
            onChange={(e) => { setOnlyCurrent(e.target.checked); setPage(1); }}
          />
          <label htmlFor="onlyCurrent">Chỉ xem bản ghi hiện hành</label>
        </div>
      </div>

      {/* Grid table */}
      <div className="card md-page__tablewrap">
        {loading ? (
          <div style={{ padding: "40px", textAlign: "center" }}>Đang tải định mức...</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center" }} className="md-page__muted">
            Không tìm thấy định mức nào.
          </div>
        ) : (
          <table className="md-page__table">
            <thead>
              <tr>
                <th>Mã định mức</th>
                <th>Giá trị</th>
                <th>Sản phẩm</th>
                <th>Máy in</th>
                <th>Công đoạn</th>
                <th>Số lượng tối thiểu/tối đa</th>
                <th>Tham số Context</th>
                <th>Áp dụng từ</th>
                <th>Áp dụng đến</th>
                <th>Trạng thái</th>
                <th style={{ width: "120px" }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const pType = productTypes.find((p) => p.product_type === row.product_type);
                const machine = machines.find((m) => m.id === row.machine_id);
                const op = operations.find((o) => o.id === row.operation_id);
                
                let valDisplay = row.value.toString();
                if (row.norm_key === "yield_rate") {
                  valDisplay = `${(row.value * 100).toFixed(0)}%`;
                } else if (row.norm_key === "running_waste_pct") {
                  valDisplay = `${(row.value * 100).toFixed(1)}%`;
                } else {
                  valDisplay = `${row.value} tờ/màu/mặt`;
                }

                return (
                  <tr key={row.id}>
                    <td className="md-page__mono">
                      {NORM_KEYS.find((k) => k.value === row.norm_key)?.label || row.norm_key}
                    </td>
                    <td className="md-page__price" style={{ fontSize: "16px" }}>
                      {valDisplay}
                    </td>
                    <td>{pType ? pType.name : <span className="md-page__muted">Tất cả</span>}</td>
                    <td>{machine ? <span className="md-page__tag-tech">{machine.name}</span> : <span className="md-page__muted">Tất cả</span>}</td>
                    <td>
                      {op ? (
                        <span>{op.name}</span>
                      ) : row.operation_key ? (
                        <span className="md-page__mono">Key: {row.operation_key}</span>
                      ) : (
                        <span className="md-page__muted">Tất cả</span>
                      )}
                    </td>
                    <td>
                      {row.qty_min === null && row.qty_max === null ? (
                        <span className="md-page__muted">Mọi số lượng</span>
                      ) : (
                        <span>
                          {row.qty_min ?? 0} → {row.qty_max ?? "∞"}
                        </span>
                      )}
                    </td>
                    <td>
                      {row.context ? (
                        <div className="md-page__tag-group">
                          {Object.entries(row.context).map(([k, v]) => (
                            <span className="md-page__tag" key={k}>{k}: {String(v)}</span>
                          ))}
                        </div>
                      ) : (
                        <span className="md-page__muted">Không</span>
                      )}
                    </td>
                    <td>{row.effective_from}</td>
                    <td>{row.effective_to || <span className="md-page__muted">Vô hạn</span>}</td>
                    <td>
                      <span className={`md-page__status-badge ${row.effective_to === null || row.effective_to > todayStr ? "is-active" : "is-inactive"}`}>
                        {(row.effective_to === null || row.effective_to > todayStr) ? "Hữu hiệu" : "Hết hạn"}
                      </span>
                    </td>
                    <td className="md-page__actions-col">
                      {(row.effective_to === null || row.effective_to > todayStr) && (
                        <button
                          type="button"
                          className="btn btn--secondary md-page__rowbtn"
                          onClick={() => handleCloseClick(row)}
                        >
                          Đóng định mức
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
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="md-page__pager">
          <span>Tổng số: <strong>{total}</strong> quy tắc định mức</span>
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
              <h2>Tạo Quy Tắc Định Mức / Bù Hao Mới</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <div className="md-page__form-grid">
                <div>
                  <label className="label">Loại định mức</label>
                  <select
                    className="input select"
                    value={normKey}
                    onChange={(e) => setNormKey(e.target.value)}
                    required
                  >
                    {NORM_KEYS.map((k) => (
                      <option key={k.value} value={k.value}>{k.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">
                    {normKey === "makeready_per_color_side" ? "Giá trị hao hụt (Tờ bù hao)" : "Giá trị tỷ lệ (VD: 0.98 cho 98%)"}
                  </label>
                  <input
                    type="number"
                    step="0.001"
                    className="input"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    placeholder={normKey === "makeready_per_color_side" ? "VD: 25" : "VD: 0.03"}
                    required
                    min="0"
                  />
                </div>

                <div>
                  <label className="label">Loại sản phẩm (Để trống nếu áp dụng chung)</label>
                  <select
                    className="input select"
                    value={productType}
                    onChange={(e) => setProductType(e.target.value)}
                  >
                    <option value="">-- Áp dụng chung --</option>
                    {productTypes.map((p) => (
                      <option key={p.product_type} value={p.product_type}>{p.name}</option>
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
                    <option value="">-- Áp dụng chung --</option>
                    {machines.map((m) => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">Công đoạn hệ thống (Chọn một trong hai)</label>
                  <select
                    className="input select"
                    value={operationId}
                    onChange={(e) => { setOperationId(e.target.value); if(e.target.value) setOperationKey(""); }}
                  >
                    <option value="">-- Tất cả công đoạn --</option>
                    {operations.map((o) => (
                      <option key={o.id} value={o.id}>{o.name} ({o.code})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="label">Từ khóa công đoạn tự do (Fallback key)</label>
                  <input
                    type="text"
                    className="input"
                    value={operationKey}
                    onChange={(e) => { setOperationKey(e.target.value); if(e.target.value) setOperationId(""); }}
                    placeholder="VD: dong_cuon, gap_toa"
                  />
                </div>

                <div>
                  <label className="label">Số lượng đặt hàng tối thiểu (qty_min)</label>
                  <input
                    type="number"
                    className="input"
                    value={qtyMin}
                    onChange={(e) => setQtyMin(e.target.value)}
                    placeholder="VD: 500 (Để trống nếu không lọc)"
                    min="0"
                  />
                </div>

                <div>
                  <label className="label">Số lượng đặt hàng tối đa (qty_max)</label>
                  <input
                    type="number"
                    className="input"
                    value={qtyMax}
                    onChange={(e) => setQtyMax(e.target.value)}
                    placeholder="VD: 5000 (Để trống nếu không lọc)"
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

                <div>
                  <label className="label">Ghi chú / Note</label>
                  <input
                    type="text"
                    className="input"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Lý do áp dụng / Diễn giải"
                  />
                </div>
              </div>

              {/* Context dynamic details */}
              <div style={{ borderTop: "1px solid var(--rule-soft)", paddingTop: "var(--sp-4)" }}>
                <h3 style={{ fontSize: "14px", fontWeight: "bold", marginBottom: "var(--sp-2)" }}>Tham số bổ sung (Context Match)</h3>
                <div className="md-page__form-grid">
                  <div>
                    <label className="label">Số màu in (colors)</label>
                    <input
                      type="number"
                      className="input"
                      value={contextColors}
                      onChange={(e) => setContextColors(e.target.value)}
                      placeholder="VD: 4"
                      min="1"
                    />
                  </div>

                  <div>
                    <label className="label">Số mặt in (sides)</label>
                    <input
                      type="number"
                      className="input"
                      value={contextSides}
                      onChange={(e) => setContextSides(e.target.value)}
                      placeholder="VD: 2"
                      min="1"
                    />
                  </div>
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

      {/* Dialog: Close Norm */}
      {mode === "close" && selected && (
        <div className="md-page__overlay">
          <form className="card md-page__dialog md-page__dialog--sm" onSubmit={handleCloseSubmit}>
            <div className="md-page__dialog-head">
              <h2>Đóng Hiệu Lực Định Mức</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn đang dừng hiệu lực quy tắc định mức <strong>{selected.norm_key}</strong>.</p>
              
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
              <h2>Xác Nhận Xóa Định Mức</h2>
              <button type="button" className="md-page__close" onClick={() => setDeleting(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa định mức tương lai này? Thao tác này sẽ xóa vĩnh viễn quy tắc khỏi hệ thống.</p>
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
