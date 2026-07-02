import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type MaterialRow,
  type MaterialInput,
  type MaterialCostInput,
  type MaterialCostRow,
  type MaterialListStats,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

const MAT_TYPES = [
  { value: "paper", label: "Giấy in" },
  { value: "decal", label: "Decal" },
  { value: "pp", label: "PP" },
  { value: "canvas", label: "Vải canvas" },
  { value: "carton", label: "Giấy carton" },
  { value: "lamination", label: "Màng cán" },
  { value: "glue", label: "Keo dán" },
  { value: "chemical", label: "Hóa chất / mực" },
];

export function MaterialsCatalogPage() {
  const { token } = useAuth();
  
  const [rows, setRows] = useState<MaterialRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort] = useState("code");
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [stats, setStats] = useState<MaterialListStats | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit" | "clone" | "costs">(null);
  const [selected, setSelected] = useState<MaterialRow | null>(null);
  const [deleting, setDeleting] = useState<MaterialRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.materials
      .list(token, {
        q: q.trim() || undefined,
        material_type: typeFilter || null,
        sort,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
        setStats(res.stats);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục vật liệu.");
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

  async function handleToggleActive(row: MaterialRow) {
    if (!token) return;
    try {
      await api.materials.toggleActive(token, row.id);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.materials.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được vật tư.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Danh mục Vật liệu (403).
        </div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Giấy & Vật tư</h1>
        <p className="md-page__sub">
          Quản lý toàn bộ vật tư sản xuất (Giấy cuộn/tờ, decal, màng cán, keo...) và lịch sử đơn giá nhập kho.
        </p>
      </header>

      {/* Stats Dashboard Grid */}
      {stats && (
        <div className="md-page__stats">
          <div className="card md-page__stat-card">
            <span className="md-page__stat-label">Tổng số vật tư</span>
            <strong className="md-page__stat-val">{stats.total_materials}</strong>
          </div>
          <div className="card md-page__stat-card">
            <span className="md-page__stat-label">Danh mục Giấy</span>
            <strong className="md-page__stat-val">{stats.total_papers}</strong>
          </div>
          <div className="card md-page__stat-card">
            <span className="md-page__stat-label">Vật tư tiêu hao</span>
            <strong className="md-page__stat-val">{stats.total_consumables}</strong>
          </div>
          <div className="card md-page__stat-card md-page__stat-card--warn">
            <span className="md-page__stat-label">Vật tư chưa cấu hình giá</span>
            <strong className="md-page__stat-val">{stats.no_price_count}</strong>
          </div>
          <div className="card md-page__stat-card">
            <span className="md-page__stat-label">Cập nhật giá tháng này</span>
            <strong className="md-page__stat-val">{stats.price_updates_this_month}</strong>
          </div>
        </div>
      )}

      <div className="md-page__toolbar">
        <form className="md-page__search" onSubmit={onSearch}>
          <input
            className="input"
            placeholder="Tìm theo tên / mã vật tư..."
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
          <option value="">Tất cả loại vật tư</option>
          {MAT_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        <div className="md-page__toolbar-spacer" />
        <Button
          variant="primary"
          onClick={() => { setSelected(null); setMode("create"); }}
        >
          + Tạo vật tư
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
              <th>Mã vật tư</th>
              <th>Tên vật tư</th>
              <th>Loại</th>
              <th>Đơn vị</th>
              <th>Thông số kỹ thuật</th>
              <th>Giá hiện hành</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="md-page__status">Đang tải dữ liệu...</td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="md-page__empty">Không tìm thấy vật tư nào.</td>
              </tr>
            ) : (
              rows.map((row) => {
                const currentCost = row.costs.find((c) => c.effective_to === null);
                return (
                  <tr key={row.id} className="md-page__row" onClick={() => { setSelected(row); setMode("edit"); }}>
                    <td className="md-page__mono">{row.code}</td>
                    <td><strong>{row.name}</strong></td>
                    <td>{MAT_TYPES.find((t) => t.value === row.material_type)?.label ?? row.material_type}</td>
                    <td>{row.unit}</td>
                    <td>
                      {row.material_type === "paper" ? (
                        <span className="md-page__specs">
                          {row.paper_family} · {row.gsm}gsm · {row.width_cm}x{row.height_cm}cm
                        </span>
                      ) : (
                        <span className="md-page__specs">
                          {row.thickness_mm ? `${row.thickness_mm}mm ` : ""}
                          {row.default_waste_pct ? `Hao hụt: ${row.default_waste_pct}%` : "—"}
                        </span>
                      )}
                    </td>
                    <td>
                      {currentCost ? (
                        <span className="md-page__price">
                          {currentCost.unit_price.toLocaleString("vi-VN")} đ/{currentCost.price_unit}
                        </span>
                      ) : (
                        <span className="md-page__danger-text">Chưa cấu hình</span>
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
                        onClick={() => { setSelected(row); setMode("costs"); }}
                      >
                        Bảng giá
                      </button>
                      {row.material_type === "paper" && (
                        <button
                          type="button"
                          className="btn btn--ghost md-page__rowbtn"
                          onClick={() => { setSelected(row); setMode("clone"); }}
                        >
                          Nhân bản
                        </button>
                      )}
                      <button
                        type="button"
                        className={`btn btn--ghost md-page__rowbtn ${row.is_active ? "md-page__rowbtn--danger" : ""}`}
                        onClick={() => handleToggleActive(row)}
                      >
                        {row.is_active ? "Ẩn" : "Hiện"}
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
            Tổng số: {total} vật tư · Trang {page}/{totalPages}
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
        <MaterialFormDialog
          existing={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Paper Clone Dialog */}
      {mode === "clone" && selected && (
        <PaperCloneDialog
          source={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Historical Costs Dialog */}
      {mode === "costs" && selected && (
        <MaterialCostsDialog
          material={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Delete Confirmation */}
      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head">
              <h2>Xác nhận xóa</h2>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa vĩnh viễn vật tư <strong>{deleting.name}</strong> ({deleting.code})?</p>
              <div className="banner banner--warn" role="alert">
                <span>Khuyến khích chọn tính năng <strong>Ẩn</strong> thay vì Xóa để bảo toàn lịch sử Tính giá.</span>
              </div>
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

function MaterialFormDialog({
  existing,
  onClose,
  onSaved,
}: {
  existing: MaterialRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [name, setName] = useState(existing?.name ?? "");
  const [type, setType] = useState(existing?.material_type ?? "paper");
  const [unit, setUnit] = useState(existing?.unit ?? "to");
  const [minFee, setMinFee] = useState(existing?.min_fee ? String(existing.min_fee) : "0");
  const [widthCm, setWidthCm] = useState(existing?.width_cm ? String(existing.width_cm) : "");
  const [heightCm, setHeightCm] = useState(existing?.height_cm ? String(existing.height_cm) : "");
  const [gsm, setGsm] = useState(existing?.gsm ? String(existing.gsm) : "");
  const [thickness, setThickness] = useState(existing?.thickness_mm ? String(existing.thickness_mm) : "");
  const [wastePct, setWastePct] = useState(existing?.default_waste_pct ? String(existing.default_waste_pct) : "0");
  const [minPurchase, setMinPurchase] = useState(existing?.min_purchase_qty ? String(existing.min_purchase_qty) : "0");
  const [family, setFamily] = useState(existing?.paper_family ?? "");
  const [surface, setSurface] = useState(existing?.surface ?? "");
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If paper size rule is violated (short side first), alert in form
  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    if (!name.trim()) return setError("Tên vật tư không được trống.");
    if (!unit.trim()) return setError("Đơn vị tính không được trống.");

    const payload: MaterialInput = {
      name: name.trim(),
      material_type: type,
      unit: unit.trim(),
      min_fee: Number(minFee) || 0,
      width_cm: widthCm ? Number(widthCm) : null,
      height_cm: heightCm ? Number(heightCm) : null,
      gsm: gsm ? Number(gsm) : null,
      thickness_mm: thickness ? Number(thickness) : null,
      default_waste_pct: Number(wastePct) || 0,
      min_purchase_qty: Number(minPurchase) || 0,
      paper_family: type === "paper" ? family.trim() : null,
      surface: type === "paper" ? surface.trim() : null,
      is_active: isActive,
    };

    setSaving(true);
    try {
      if (isEdit && existing) {
        await api.materials.update(token, existing.id, payload);
      } else {
        await api.materials.create(token, payload);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu không thành công.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Sửa vật tư: ${existing?.code}` : "Tạo vật tư mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <div className="md-page__form-grid">
            <label className="field md-page__form-wide">
              <span className="field__label">Tên vật tư *</span>
              <input
                className="input"
                placeholder="VD: Couche 150gsm 65x86"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            
            <label className="field">
              <span className="field__label">Loại vật tư</span>
              <select className="input" value={type} onChange={(e) => setType(e.target.value)} disabled={isEdit}>
                {MAT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field__label">Đơn vị quản lý *</span>
              <input
                className="input"
                placeholder="VD: to, kg, m2, cuon"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              />
            </label>

            <label className="field">
              <span className="field__label">Phí tối thiểu (đ)</span>
              <input
                className="input"
                type="number"
                value={minFee}
                onChange={(e) => setMinFee(e.target.value)}
              />
            </label>

            <label className="field">
              <span className="field__label">Số lượng mua tối thiểu</span>
              <input
                className="input"
                type="number"
                value={minPurchase}
                onChange={(e) => setMinPurchase(e.target.value)}
              />
            </label>

            <label className="field">
              <span className="field__label">Tỷ lệ hao hụt (%)</span>
              <input
                className="input"
                type="number"
                value={wastePct}
                onChange={(e) => setWastePct(e.target.value)}
                step="0.1"
              />
            </label>

            <label className="field">
              <span className="field__label">Độ dày (mm)</span>
              <input
                className="input"
                type="number"
                value={thickness}
                onChange={(e) => setThickness(e.target.value)}
                step="0.01"
                placeholder="chỉ dùng nếu cần"
              />
            </label>

            <label className="field">
              <span className="field__label">Trạng thái hoạt động</span>
              <div className="md-page__toggle-wrap">
                <input
                  type="checkbox"
                  id="mat-active-check"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                />
                <label htmlFor="mat-active-check">Kích hoạt hoạt động</label>
              </div>
            </label>

            {/* Paper fields */}
            {type === "paper" && (
              <>
                <label className="field">
                  <span className="field__label">Họ giấy *</span>
                  <input
                    className="input"
                    placeholder="VD: Couche, Bristol, Ford"
                    value={family}
                    onChange={(e) => setFamily(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Bề mặt</span>
                  <input
                    className="input"
                    placeholder="VD: bong, mo, trang"
                    value={surface}
                    onChange={(e) => setSurface(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Định lượng (gsm)</span>
                  <input
                    className="input"
                    type="number"
                    value={gsm}
                    onChange={(e) => setGsm(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Khổ rộng (cm)</span>
                  <input
                    className="input"
                    type="number"
                    placeholder="Cạnh ngắn (VD: 65)"
                    value={widthCm}
                    onChange={(e) => setWidthCm(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Khổ dài/cao (cm)</span>
                  <input
                    className="input"
                    type="number"
                    placeholder="Cạnh dài (VD: 86)"
                    value={heightCm}
                    onChange={(e) => setHeightCm(e.target.value)}
                  />
                </label>
              </>
            )}
          </div>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu vật tư</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PaperCloneDialog({
  source,
  onClose,
  onSaved,
}: {
  source: MaterialRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  
  const [gsm, setGsm] = useState(source.gsm ? String(source.gsm) : "");
  const [widthCm, setWidthCm] = useState(source.width_cm ? String(source.width_cm) : "");
  const [heightCm, setHeightCm] = useState(source.height_cm ? String(source.height_cm) : "");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    const g = Number(gsm);
    const w = Number(widthCm);
    const h = Number(heightCm);
    if (!g || !w || !h) return setError("Các thông số gsm, kích thước không được trống.");

    setSaving(true);
    try {
      await api.materials.clone(token, source.id, { gsm: g, width_cm: w, height_cm: h });
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Nhân bản thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog md-page__dialog--sm card">
        <div className="md-page__dialog-head">
          <h2>Nhân bản giấy: {source.paper_family}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <p className="md-page__sub">Nhân bản giấy từ mẫu gốc, hệ thống sẽ tự động ghép tên.</p>
          
          <label className="field">
            <span className="field__label">Định lượng mới (gsm)</span>
            <input className="input" type="number" value={gsm} onChange={(e) => setGsm(e.target.value)} />
          </label>
          <label className="field">
            <span className="field__label">Khổ rộng mới (cm - cạnh ngắn)</span>
            <input className="input" type="number" value={widthCm} onChange={(e) => setWidthCm(e.target.value)} />
          </label>
          <label className="field">
            <span className="field__label">Khổ dài mới (cm - cạnh dài)</span>
            <input className="input" type="number" value={heightCm} onChange={(e) => setHeightCm(e.target.value)} />
          </label>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Xác nhận nhân bản</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MaterialCostsDialog({
  material,
  onClose,
  onSaved,
}: {
  material: MaterialRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();

  const [costs, setCosts] = useState<MaterialCostRow[]>([]);
  const [priceUnit, setPriceUnit] = useState(material.unit);
  const [price, setPrice] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().split("T")[0]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reload history of rates
  const loadCosts = useCallback(() => {
    if (!token) return;
    api.materials
      .get(token, material.id)
      .then((res) => {
        setCosts(res.costs);
      })
      .catch(() => setError("Không tải được bảng giá."));
  }, [token, material.id]);

  useEffect(() => {
    loadCosts();
  }, [loadCosts]);

  async function handleAddPrice(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    const pr = Number(price);
    if (pr < 0) return setError("Đơn giá không được âm.");
    if (!price.trim()) return setError("Vui lòng điền đơn giá.");

    const payload: MaterialCostInput = {
      price_unit: priceUnit.trim(),
      unit_price: pr,
      effective_from: effectiveFrom,
    };

    setSaving(true);
    try {
      await api.materials.addCost(token, material.id, payload);
      setPrice("");
      loadCosts();
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu bảng giá mới thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>Quản lý lịch sử giá: {material.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          
          <form className="md-page__rates-form" onSubmit={handleAddPrice}>
            <h3 className="md-page__section-title">Cập nhật đơn giá mới</h3>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Đơn vị giá</span>
                <input
                  className="input"
                  placeholder="VD: ram, kg, to"
                  value={priceUnit}
                  onChange={(e) => setPriceUnit(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Đơn giá (đ) *</span>
                <input
                  className="input"
                  type="number"
                  placeholder="VD: 850000"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
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
              <div className="md-page__field-btn-align">
                <Button type="submit" variant="primary" loading={saving}>Áp dụng</Button>
              </div>
            </div>
          </form>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="md-page__costs-history">
            <h3 className="md-page__section-title">Lịch sử điều chỉnh giá</h3>
            <div className="md-page__tablewrap">
              <table className="md-page__table">
                <thead>
                  <tr>
                    <th>Đơn vị tính</th>
                    <th>Đơn giá vốn</th>
                    <th>Từ ngày</th>
                    <th>Đến ngày</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {costs.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="md-page__empty">Chưa có bảng giá lịch sử nào.</td>
                    </tr>
                  ) : (
                    costs.map((c) => {
                      const isActive = c.effective_to === null;
                      return (
                        <tr key={c.id}>
                          <td>{c.price_unit}</td>
                          <td><strong>{c.unit_price.toLocaleString("vi-VN")} đ</strong></td>
                          <td>{c.effective_from}</td>
                          <td>{c.effective_to ?? <span className="md-page__status-badge is-active">Hiện hành</span>}</td>
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
