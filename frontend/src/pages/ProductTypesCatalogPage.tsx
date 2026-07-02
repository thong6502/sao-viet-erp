import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type ProductTypeCatalogRow,
  type ProductTypeCatalogInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

// Phải khớp CALCULATION_STRATEGIES ở model (sheet/page/area/roll/box/book) — trước đây lệch
// (thừa item_based/other vô hiệu, thiếu box/roll/book → hộp/cuộn/sách hiện raw + tạo bị 422).
const CALC_STRATEGIES = [
  { value: "sheet_based", label: "Theo khổ tờ (Sheet-based)" },
  { value: "page_based", label: "Theo số trang (Page-based)" },
  { value: "area_based", label: "Theo diện tích m2 (Area-based)" },
  { value: "box_based", label: "Theo hộp (Box-based)" },
  { value: "roll_based", label: "Theo cuộn (Roll-based)" },
  { value: "book_based", label: "Theo cuốn sách (Book-based)" },
];

const STAGE_FIELDS = [
  { value: "gsm", label: "Định lượng (GSM)" },
  { value: "finished_w", label: "Khổ rộng TP (cm)" },
  { value: "finished_h", label: "Khổ cao TP (cm)" },
  { value: "finished_d", label: "Khổ sâu/dày TP (cm)" },
  { value: "page_count", label: "Số trang" },
  { value: "binding_type", label: "Kiểu đóng gáy" },
  { value: "sides", label: "Số mặt in" },
];

// Khớp OP_TYPES của trang Công đoạn (domain §5); trước thiếu dan_hop dù seed hộp/túi dùng nó.
const OP_TYPES = [
  { value: "in", label: "In ấn" },
  { value: "can_mang", label: "Cán màng" },
  { value: "be", label: "Bế hình / Đột" },
  { value: "boi", label: "Bồi" },
  { value: "ep_kim", label: "Ép kim / Nhũ" },
  { value: "dap_noi", label: "Dập nổi / chìm" },
  { value: "uv", label: "UV định hình" },
  { value: "gap", label: "Gấp nếp" },
  { value: "dong_cuon", label: "Đóng cuốn" },
  { value: "dan_hop", label: "Dán hộp" },
  { value: "xen", label: "Xén" },
  { value: "dong_goi", label: "Đóng gói" },
];

// Khớp VALID_MATERIAL_TYPES ở product_type_catalog_service (backend từ chối type ngoài tập này).
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

const TECH_TYPES = [
  { value: "offset", label: "In Offset" },
  { value: "digital", label: "In Kỹ thuật số" },
  { value: "large_format", label: "In Khổ lớn" },
  { value: "flexo", label: "In Flexo" },
];

export function ProductTypesCatalogPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<ProductTypeCatalogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<ProductTypeCatalogRow | null>(null);
  const [deleting, setDeleting] = useState<ProductTypeCatalogRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.productTypesCatalog
      .list(token)
      .then((res) => {
        setRows(res.items);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được cấu hình loại sản phẩm.");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.productTypesCatalog.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được cấu hình.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Loại sản phẩm (403).
        </div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Loại sản phẩm</h1>
        <p className="md-page__sub">
          Định nghĩa các loại sản phẩm, chiến lược tính giá và các trường thuộc tính kỹ thuật bắt buộc tương ứng.
        </p>
      </header>

      <div className="md-page__toolbar">
        <div className="md-page__toolbar-spacer" />
        <Button
          variant="primary"
          onClick={() => {
            setEditing(null);
            setMode("create");
          }}
        >
          + Tạo loại sản phẩm
        </Button>
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" onClick={() => load()}>
            Tải lại
          </button>
        </div>
      )}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã loại SP</th>
              <th>Tên hiển thị</th>
              <th>Chiến lược tính giá</th>
              <th>Thuộc tính yêu cầu</th>
              <th>Hỗ trợ công nghệ</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="md-page__status" role="status">
                  Đang tải dữ liệu...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="md-page__empty">
                  Chưa có cấu hình loại sản phẩm nào.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="md-page__row" onClick={() => { setEditing(row); setMode("edit"); }}>
                  <td className="md-page__mono">{row.product_type}</td>
                  <td><strong>{row.name}</strong></td>
                  <td>
                    <span className="md-page__tag-calc">
                      {CALC_STRATEGIES.find((s) => s.value === row.calculation_strategy)?.label ?? row.calculation_strategy}
                    </span>
                  </td>
                  <td>
                    <div className="md-page__tag-group">
                      {row.required_fields?.map((f) => (
                        <span key={f} className="md-page__tag">
                          {STAGE_FIELDS.find((x) => x.value === f)?.label ?? f}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <div className="md-page__tag-group">
                      {row.compatible_technologies?.map((t) => (
                        <span key={t} className="md-page__tag-tech">
                          {TECH_TYPES.find((x) => x.value === t)?.label ?? t}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                      {row.is_active ? "Đang chạy" : "Tạm ngưng"}
                    </span>
                  </td>
                  <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="btn btn--ghost md-page__rowbtn"
                      onClick={() => { setEditing(row); setMode("edit"); }}
                    >
                      Sửa
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
              ))
            )}
          </tbody>
        </table>
      </div>

      {mode && (
        <ProductTypeFormDialog
          existing={editing}
          onClose={() => { setMode(null); setEditing(null); }}
          onSaved={() => { setMode(null); setEditing(null); load(); }}
        />
      )}

      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head">
              <h2>Xác nhận xóa</h2>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa cấu hình loại sản phẩm <strong>{deleting.name}</strong> ({deleting.product_type})?</p>
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

function ProductTypeFormDialog({
  existing,
  onClose,
  onSaved,
}: {
  existing: ProductTypeCatalogRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [productType, setProductType] = useState(existing?.product_type ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [strategy, setStrategy] = useState(existing?.calculation_strategy ?? "sheet_based");
  const [reqFields, setReqFields] = useState<string[]>(existing?.required_fields ?? []);
  const [defOps, setDefOps] = useState<string[]>(existing?.default_operations ?? []);
  const [allowMats, setAllowMats] = useState<string[]>(existing?.allowed_materials ?? []);
  const [techs, setTechs] = useState<string[]>(existing?.compatible_technologies ?? []);
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  function toggleItem(list: string[], setList: (l: string[]) => void, val: string) {
    if (list.includes(val)) {
      setList(list.filter((x) => x !== val));
    } else {
      setList([...list, val]);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setValidationError(null);

    if (!productType.trim()) {
      setValidationError("Mã loại sản phẩm không được trống.");
      return;
    }
    if (!name.trim()) {
      setValidationError("Tên loại sản phẩm không được trống.");
      return;
    }

    const payload: ProductTypeCatalogInput = {
      product_type: productType.trim(),
      name: name.trim(),
      calculation_strategy: strategy,
      required_fields: reqFields,
      default_operations: defOps,
      allowed_materials: allowMats,
      compatible_technologies: techs,
      is_active: isActive,
    };

    setSaving(true);
    try {
      if (isEdit && existing) {
        await api.productTypesCatalog.update(token, existing.id, payload);
      } else {
        await api.productTypesCatalog.create(token, payload);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) {
        setValidationError(err.message);
      } else {
        setValidationError("Lưu thất bại. Vui lòng kiểm tra lại.");
      }
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Chỉnh sửa loại SP: ${existing?.name}` : "Tạo loại sản phẩm mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Mã loại sản phẩm *</span>
              <input
                className="input"
                placeholder="VD: flyer"
                value={productType}
                onChange={(e) => setProductType(e.target.value)}
                disabled={isEdit}
              />
            </label>
            <label className="field">
              <span className="field__label">Tên hiển thị *</span>
              <input
                className="input"
                placeholder="VD: Tờ rơi quảng cáo"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">Chiến lược tính giá</span>
              <select className="input" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                {CALC_STRATEGIES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field__label">Trạng thái hoạt động</span>
              <div className="md-page__toggle-wrap">
                <input
                  type="checkbox"
                  id="pt-active-check"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                />
                <label htmlFor="pt-active-check">Kích hoạt hoạt động</label>
              </div>
            </label>
          </div>

          <div className="md-page__choices-group">
            <div className="md-page__choices">
              <span className="field__label">Các trường bắt buộc nhập</span>
              <div className="md-page__checkboxes">
                {STAGE_FIELDS.map((f) => (
                  <label key={f.value} className="md-page__checkbox-label">
                    <input
                      type="checkbox"
                      checked={reqFields.includes(f.value)}
                      onChange={() => toggleItem(reqFields, setReqFields, f.value)}
                    />
                    <span>{f.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="md-page__choices">
              <span className="field__label">Công đoạn mặc định</span>
              <div className="md-page__checkboxes">
                {OP_TYPES.map((o) => (
                  <label key={o.value} className="md-page__checkbox-label">
                    <input
                      type="checkbox"
                      checked={defOps.includes(o.value)}
                      onChange={() => toggleItem(defOps, setDefOps, o.value)}
                    />
                    <span>{o.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="md-page__choices">
              <span className="field__label">Vật liệu được phép</span>
              <div className="md-page__checkboxes">
                {MAT_TYPES.map((m) => (
                  <label key={m.value} className="md-page__checkbox-label">
                    <input
                      type="checkbox"
                      checked={allowMats.includes(m.value)}
                      onChange={() => toggleItem(allowMats, setAllowMats, m.value)}
                    />
                    <span>{m.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="md-page__choices">
              <span className="field__label">Công nghệ in tương thích</span>
              <div className="md-page__checkboxes">
                {TECH_TYPES.map((t) => (
                  <label key={t.value} className="md-page__checkbox-label">
                    <input
                      type="checkbox"
                      checked={techs.includes(t.value)}
                      onChange={() => toggleItem(techs, setTechs, t.value)}
                    />
                    <span>{t.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          {validationError && (
            <div className="banner banner--error" role="alert">
              {validationError}
            </div>
          )}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu cấu hình</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
