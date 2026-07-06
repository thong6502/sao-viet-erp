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
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

const MAT_TYPES = [
  { value: "paper", label: "Giấy in" },
  { value: "decal", label: "Decal" },
  { value: "pp", label: "PP" },
  { value: "canvas", label: "Vải canvas" },
  { value: "carton", label: "Giấy carton" },
  { value: "film", label: "Film" },
  { value: "formex", label: "Formex" },
  { value: "lamination", label: "Màng cán" },
  { value: "glue", label: "Keo dán" },
  { value: "chemical", label: "Hóa chất / mực" },
];

// Nhóm vật tư (tái thiết kế #2) — trục UI trên material_type.
const MAT_GROUPS = [
  { value: "paper", label: "Giấy" },
  { value: "ink", label: "Mực" },
  { value: "film", label: "Màng" },
  { value: "glue", label: "Keo" },
  { value: "packaging", label: "Bao bì" },
  { value: "auxiliary", label: "Phụ liệu" },
];

// #9 — gợi ý chuẩn hoá danh mục (datalist: gợi ý nhưng vẫn cho nhập khác — domain §4 còn Kraft/art paper).
const PAPER_FAMILIES = ["Ford", "Couche", "Ivory", "Bristol", "Duplex", "Kraft"];
const PAPER_SURFACES = ["bong", "mo", "khong_trang"];
const PRICE_UNITS = ["ram", "kg", "to", "m2", "nghin_luot", "cai", "cuon", "thung"];

export function MaterialsCatalogPage() {
  const { token } = useAuth();
  // CRUD: ẩn nút Thêm/Sửa/Xóa nếu thiếu quyền (view-only: ẩn hẳn, không disable).
  const can = useCan();
  const canCreate = can("dm_giay_vat_tu", "create");
  const canUpdate = can("dm_giay_vat_tu", "update");
  const canDelete = can("dm_giay_vat_tu", "delete");
  // Quyền chi tiết nhóm B: nhân bản + bật/tắt hoạt động (tách khỏi Thêm/Sửa).
  const canClone = can("dm_giay_vat_tu", "clone");
  const canToggleActive = can("dm_giay_vat_tu", "toggle_active");

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

  const [mode, setMode] = useState<null | "create" | "edit" | "clone" | "costs" | "test">(null);
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
        <h1 className="md-page__title">Vật tư & Đơn giá vật tư</h1>
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
        <Button variant="ghost" onClick={() => setMode("test")}>Test tính tiền</Button>
        {canCreate && (
          <Button
            variant="primary"
            onClick={() => { setSelected(null); setMode("create"); }}
          >
            + Tạo vật tư
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
                  <tr
                    key={row.id}
                    className="md-page__row"
                    onClick={canUpdate ? () => { setSelected(row); setMode("edit"); } : undefined}
                    style={canUpdate ? undefined : { cursor: "default" }}
                  >
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
                      {canUpdate && (
                        <button
                          type="button"
                          className="btn btn--ghost md-page__rowbtn"
                          onClick={() => { setSelected(row); setMode("edit"); }}
                        >
                          Sửa
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => { setSelected(row); setMode("costs"); }}
                      >
                        Bảng giá
                      </button>
                      {canClone && row.material_type === "paper" && (
                        <button
                          type="button"
                          className="btn btn--ghost md-page__rowbtn"
                          onClick={() => { setSelected(row); setMode("clone"); }}
                        >
                          Nhân bản
                        </button>
                      )}
                      {canToggleActive && (
                        <button
                          type="button"
                          className={`btn btn--ghost md-page__rowbtn ${row.is_active ? "md-page__rowbtn--danger" : ""}`}
                          onClick={() => handleToggleActive(row)}
                        >
                          {row.is_active ? "Ẩn" : "Hiện"}
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

      {/* Test quy đổi / tính tiền */}
      {mode === "test" && <MaterialTestDialog onClose={() => setMode(null)} />}

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
  // Đổi trạng thái hoạt động của vật tư ĐANG CÓ = quyền chi tiết `toggle_active`
  // (backend cũng chặn) — thiếu quyền thì khóa checkbox khi Sửa; Tạo mới vẫn chọn được.
  const canToggleActive = useCan()("dm_giay_vat_tu", "toggle_active");
  const activeLocked = isEdit && !canToggleActive;

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

  // Tái thiết kế #2 — nhóm + NCC + UoM/quy đổi + field theo nhóm.
  const [group, setGroup] = useState(existing?.material_group ?? "");
  const [defaultSupplier, setDefaultSupplier] = useState(existing?.default_supplier ?? "");
  const [baseUom, setBaseUom] = useState(existing?.base_uom ?? "");
  const [purchaseUom, setPurchaseUom] = useState(existing?.purchase_uom ?? "");
  const [consumptionUom, setConsumptionUom] = useState(existing?.consumption_uom ?? "");
  const [conversionMethod, setConversionMethod] = useState(existing?.conversion_method ?? "");
  const [inkType, setInkType] = useState(existing?.ink_type ?? "");
  const [inkColorSystem, setInkColorSystem] = useState(existing?.ink_color_system ?? "");
  const [inkColorCode, setInkColorCode] = useState(existing?.ink_color_code ?? "");
  const [filmType, setFilmType] = useState(existing?.film_type ?? "");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Preview quy đổi kg/tờ (§9) khi có gsm + khổ.
  const convPreview =
    gsm && widthCm && heightCm
      ? `Kg/tờ = (${widthCm}×${heightCm}/10000) × ${gsm}/1000 = ${(((Number(widthCm) * Number(heightCm)) / 10000) * (Number(gsm) / 1000)).toFixed(4)} kg`
      : "";

  // If paper size rule is violated (short side first), alert in form
  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    if (!name.trim()) return setError("Tên vật tư không được trống.");
    if (!unit.trim()) return setError("Đơn vị tính không được trống.");
    // Giấy PHẢI đủ họ + gsm + khổ: thiếu thì không tính được số con/khổ hay quy đổi tờ↔kg.
    // (Trước đây "Họ giấy *" đánh dấu bắt buộc nhưng không hề validate.)
    if (type === "paper") {
      if (!family.trim()) return setError("Họ giấy không được trống.");
      if (!gsm.trim()) return setError("Định lượng (gsm) không được trống cho giấy.");
      if (!widthCm.trim() || !heightCm.trim()) return setError("Khổ giấy (rộng × dài, cm) không được trống.");
    }
    // #10 — khổ giấy VN nhập theo quy ước CẠNH NGẮN TRƯỚC (rộng ≤ dài), VD 65×86, 79×109.
    if (type === "paper" && widthCm && heightCm && Number(widthCm) > Number(heightCm)) {
      return setError("Khổ giấy nhập cạnh ngắn trước: Khổ rộng phải ≤ Khổ dài (VD: 65×86, 79×109).");
    }

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
      material_group: (group || null) as MaterialInput["material_group"],
      default_supplier: defaultSupplier.trim() || null,
      base_uom: baseUom.trim() || null,
      purchase_uom: purchaseUom.trim() || null,
      consumption_uom: consumptionUom.trim() || null,
      conversion_method: conversionMethod || null,
      ink_type: group === "ink" ? inkType.trim() || null : null,
      ink_color_system: group === "ink" ? inkColorSystem.trim() || null : null,
      ink_color_code: group === "ink" ? inkColorCode.trim() || null : null,
      film_type: group === "film" ? filmType.trim() || null : null,
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
              <span className="field__label">Nhóm vật tư</span>
              <select className="input" value={group} onChange={(e) => setGroup(e.target.value)}>
                <option value="">-- Tự suy từ loại --</option>
                {MAT_GROUPS.map((g) => (
                  <option key={g.value} value={g.value}>{g.label}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field__label">NCC mặc định</span>
              <input className="input" placeholder="VD: NCC Giấy A" value={defaultSupplier} onChange={(e) => setDefaultSupplier(e.target.value)} />
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
                  disabled={activeLocked}
                  onChange={(e) => setIsActive(e.target.checked)}
                />
                <label htmlFor="mat-active-check">Kích hoạt hoạt động</label>
              </div>
              {activeLocked && (
                <span className="md-page__muted">
                  Cần quyền “Bật/tắt hoạt động” để đổi trạng thái.
                </span>
              )}
            </label>

            {/* Paper fields */}
            {type === "paper" && (
              <>
                <label className="field">
                  <span className="field__label">Họ giấy *</span>
                  <input
                    className="input"
                    list="paper-families"
                    placeholder="VD: Couche, Bristol, Ford"
                    value={family}
                    onChange={(e) => setFamily(e.target.value)}
                  />
                  <datalist id="paper-families">
                    {PAPER_FAMILIES.map((f) => <option key={f} value={f} />)}
                  </datalist>
                </label>
                <label className="field">
                  <span className="field__label">Bề mặt</span>
                  <input
                    className="input"
                    list="paper-surfaces"
                    placeholder="VD: bong, mo, khong_trang"
                    value={surface}
                    onChange={(e) => setSurface(e.target.value)}
                  />
                  <datalist id="paper-surfaces">
                    {PAPER_SURFACES.map((s) => <option key={s} value={s} />)}
                  </datalist>
                </label>
                <label className="field">
                  <span className="field__label">Định lượng (gsm) *</span>
                  <input
                    className="input"
                    type="number"
                    value={gsm}
                    onChange={(e) => setGsm(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Khổ rộng (cm) *</span>
                  <input
                    className="input"
                    type="number"
                    placeholder="Cạnh ngắn (VD: 65)"
                    value={widthCm}
                    onChange={(e) => setWidthCm(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Khổ dài/cao (cm) *</span>
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

            {/* Nhóm Mực */}
            {group === "ink" && (
              <>
                <label className="field">
                  <span className="field__label">Loại mực</span>
                  <input className="input" placeholder="offset / uv / pantone" value={inkType} onChange={(e) => setInkType(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Hệ màu</span>
                  <input className="input" placeholder="CMYK / spot" value={inkColorSystem} onChange={(e) => setInkColorSystem(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Mã màu</span>
                  <input className="input" placeholder="C/M/Y/K / Pantone 485C" value={inkColorCode} onChange={(e) => setInkColorCode(e.target.value)} />
                </label>
              </>
            )}

            {/* Nhóm Màng */}
            {group === "film" && (
              <label className="field">
                <span className="field__label">Loại màng</span>
                <input className="input" placeholder="matt / gloss / metalize" value={filmType} onChange={(e) => setFilmType(e.target.value)} />
              </label>
            )}

            {/* Đơn vị & quy đổi */}
            <label className="field">
              <span className="field__label">ĐVT tồn kho</span>
              <input className="input" placeholder="kg / to / cuon" value={baseUom} onChange={(e) => setBaseUom(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">ĐVT mua</span>
              <input className="input" placeholder="kg / ram / cuon" value={purchaseUom} onChange={(e) => setPurchaseUom(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">ĐVT tiêu hao</span>
              <input className="input" placeholder="to / m2 / gram / luot" value={consumptionUom} onChange={(e) => setConsumptionUom(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Cách quy đổi</span>
              <select className="input" value={conversionMethod} onChange={(e) => setConversionMethod(e.target.value)}>
                <option value="">-- Không --</option>
                <option value="gsm_area">kg ↔ tờ (gsm × khổ)</option>
                <option value="ream_500">ram → tờ (1 ram = 500 tờ)</option>
                <option value="area_m2">m² (theo diện tích)</option>
                <option value="none">Không quy đổi</option>
              </select>
            </label>
          </div>

          {convPreview && (
            <div className="md-page__preview">
              <span className="md-page__mono" style={{ fontSize: "13px" }}>{convPreview}</span>
            </div>
          )}

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
    // #10 — khổ giấy nhập cạnh ngắn trước (rộng ≤ dài).
    if (w > h) return setError("Khổ giấy nhập cạnh ngắn trước: Khổ rộng phải ≤ Khổ dài.");

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
  // Cập nhật bảng giá theo mốc = quyền chi tiết `manage_price` (tách khỏi "Sửa").
  const canManagePrice = useCan()("dm_giay_vat_tu", "manage_price");

  const [costs, setCosts] = useState<MaterialCostRow[]>([]);
  const [priceUnit, setPriceUnit] = useState(material.unit);
  const [price, setPrice] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().split("T")[0]);
  // Tái thiết kế #2 — biến thể giá.
  const [supplier, setSupplier] = useState(material.default_supplier ?? "");
  const [priceType, setPriceType] = useState("standard");
  const [qtyFrom, setQtyFrom] = useState("");
  const [qtyTo, setQtyTo] = useState("");
  const [transportFee, setTransportFee] = useState("");
  const [moq, setMoq] = useState("");
  const [leadTime, setLeadTime] = useState("");

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
      supplier: supplier.trim() || null,
      price_type: priceType,
      quantity_from: qtyFrom ? Number(qtyFrom) : null,
      quantity_to: qtyTo ? Number(qtyTo) : null,
      transport_fee: transportFee ? Number(transportFee) : 0,
      moq: moq ? Number(moq) : 0,
      lead_time_days: leadTime ? Number(leadTime) : 0,
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
          {!canManagePrice && (
            <p className="md-page__hint">Bạn không có quyền cập nhật bảng giá.</p>
          )}
          {canManagePrice && (
          <form className="md-page__rates-form" onSubmit={handleAddPrice}>
            <h3 className="md-page__section-title">Cập nhật đơn giá mới</h3>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Đơn vị giá</span>
                <input
                  className="input"
                  list="price-units"
                  placeholder="VD: ram, kg, to"
                  value={priceUnit}
                  onChange={(e) => setPriceUnit(e.target.value)}
                />
                <datalist id="price-units">
                  {PRICE_UNITS.map((u) => <option key={u} value={u} />)}
                </datalist>
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
              <label className="field">
                <span className="field__label">Nhà cung cấp</span>
                <input className="input" placeholder="NCC Giấy A" value={supplier} onChange={(e) => setSupplier(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Loại giá</span>
                <select className="input" value={priceType} onChange={(e) => setPriceType(e.target.value)}>
                  <option value="standard">Giá cost chuẩn</option>
                  <option value="purchase">Giá mua</option>
                  <option value="temporary">Giá tạm tính</option>
                </select>
              </label>
              <label className="field">
                <span className="field__label">Bậc SL từ (số tờ mua)</span>
                <input className="input" type="number" placeholder="trống = mọi SL" value={qtyFrom} onChange={(e) => setQtyFrom(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Bậc SL đến</span>
                <input className="input" type="number" placeholder="trống = ∞" value={qtyTo} onChange={(e) => setQtyTo(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Phí vận chuyển (đ)</span>
                <input className="input" type="number" value={transportFee} onChange={(e) => setTransportFee(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">MOQ</span>
                <input className="input" type="number" value={moq} onChange={(e) => setMoq(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Lead time (ngày)</span>
                <input className="input" type="number" value={leadTime} onChange={(e) => setLeadTime(e.target.value)} />
              </label>
              <div className="md-page__field-btn-align">
                <Button type="submit" variant="primary" loading={saving}>Áp dụng</Button>
              </div>
            </div>
          </form>
          )}

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
                    <th>NCC</th>
                    <th>Bậc SL</th>
                    <th>Từ ngày</th>
                    <th>Đến ngày</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {costs.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="md-page__empty">Chưa có bảng giá lịch sử nào.</td>
                    </tr>
                  ) : (
                    costs.map((c) => {
                      const isActive = c.effective_to === null;
                      return (
                        <tr key={c.id}>
                          <td>{c.price_unit}{c.version > 1 && <span className="md-page__tag"> v{c.version}</span>}</td>
                          <td><strong>{c.unit_price.toLocaleString("vi-VN")} đ</strong></td>
                          <td>{c.supplier || <span className="md-page__muted">—</span>}</td>
                          <td>{c.quantity_from == null && c.quantity_to == null ? <span className="md-page__muted">Mọi SL</span> : `${c.quantity_from ?? 0}–${c.quantity_to ?? "∞"}`}</td>
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

// Test quy đổi + tính tiền vật tư (§9) — gọi /convert và /price-test.
function MaterialTestDialog({ onClose }: { onClose: () => void }) {
  const { token } = useAuth();
  const [priceUnit, setPriceUnit] = useState("kg");
  const [unitPrice, setUnitPrice] = useState("28000");
  const [sheets, setSheets] = useState("500");
  const [gsm, setGsm] = useState("150");
  const [widthCm, setWidthCm] = useState("79");
  const [heightCm, setHeightCm] = useState("109");
  const [impressions, setImpressions] = useState("2400");
  const [transportFee, setTransportFee] = useState("");
  const [result, setResult] = useState<{ total: number; steps: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!token) return;
    setError(null);
    try {
      const res = await api.materials.priceTest(token, {
        price_unit: priceUnit,
        unit_price: Number(unitPrice) || 0,
        sheets: Number(sheets) || 0,
        gsm: gsm ? Number(gsm) : null,
        width_cm: widthCm ? Number(widthCm) : null,
        height_cm: heightCm ? Number(heightCm) : null,
        impressions: Number(impressions) || 0,
        transport_fee: transportFee ? Number(transportFee) : 0,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lỗi khi test.");
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>Test tính tiền vật tư</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Đơn vị giá</span>
              <select className="input" value={priceUnit} onChange={(e) => setPriceUnit(e.target.value)}>
                {PRICE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </label>
            <label className="field"><span className="field__label">Đơn giá</span>
              <input className="input" type="number" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} /></label>
            <label className="field"><span className="field__label">Số tờ mua (giấy)</span>
              <input className="input" type="number" value={sheets} onChange={(e) => setSheets(e.target.value)} /></label>
            <label className="field"><span className="field__label">gsm</span>
              <input className="input" type="number" value={gsm} onChange={(e) => setGsm(e.target.value)} /></label>
            <label className="field"><span className="field__label">Khổ rộng (cm)</span>
              <input className="input" type="number" value={widthCm} onChange={(e) => setWidthCm(e.target.value)} /></label>
            <label className="field"><span className="field__label">Khổ dài (cm)</span>
              <input className="input" type="number" value={heightCm} onChange={(e) => setHeightCm(e.target.value)} /></label>
            <label className="field"><span className="field__label">Lượt in màu (mực)</span>
              <input className="input" type="number" value={impressions} onChange={(e) => setImpressions(e.target.value)} /></label>
            <label className="field"><span className="field__label">Phí vận chuyển</span>
              <input className="input" type="number" value={transportFee} onChange={(e) => setTransportFee(e.target.value)} /></label>
          </div>
          <div style={{ margin: "10px 0" }}>
            <Button type="button" variant="primary" onClick={run}>Tính thử</Button>
          </div>
          {error && <div className="banner banner--error">{error}</div>}
          {result && (
            <div className="md-page__preview">
              {result.steps.map((s, i) => <div key={i} className="md-page__mono" style={{ fontSize: "13px" }}>{s}</div>)}
              <div style={{ marginTop: "6px", fontWeight: "bold" }}>Tổng: <span className="md-page__price">{result.total.toLocaleString("vi-VN")} đ</span></div>
            </div>
          )}
          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
