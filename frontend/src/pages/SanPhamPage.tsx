// Sản phẩm in (Product catalog) — spec-07. Danh mục SP (list + tìm/lọc) + Tạo/Sửa
// (Khối A đầu SP + Khối B bảng cấu phần) + Xoá. Ô giấy là SEAM-03: khi Danh mục Giấy
// chưa build hiển thị "Danh mục Giấy chưa sẵn sàng" (KHÔNG danh sách giả).
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type ComponentInput,
  type EnumOption,
  type ProductDetailOut,
  type ProductEnumsOut,
  type ProductInput,
  type ProductRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./san-pham.css";

const PAGE_SIZE = 10;
const BINDING_NONE = "none";

function labelOf(options: EnumOption[], value: string | null): string {
  if (!value) return "—";
  return options.find((o) => o.value === value)?.label ?? value;
}

// A component row in the form (all strings for controlled inputs).
interface CompForm {
  key: string;
  component_type: string;
  paper_master_id: string;
  colors_front: string;
  colors_back: string;
  page_count: string;
  finished_w: string;
  finished_h: string;
  bleed: string;
  grain_direction: string;
}

let COMP_KEY = 0;
function newComp(component_type = "body"): CompForm {
  COMP_KEY += 1;
  return {
    key: `c${COMP_KEY}`,
    component_type,
    paper_master_id: "",
    colors_front: "4",
    colors_back: "4",
    page_count: "",
    finished_w: "",
    finished_h: "",
    bleed: "0",
    grain_direction: "",
  };
}

export function SanPhamPage() {
  const { token } = useAuth();

  const [rows, setRows] = useState<ProductRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("code");
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [enums, setEnums] = useState<ProductEnumsOut | null>(null);

  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<ProductDetailOut | null>(null);
  const [deleting, setDeleting] = useState<ProductRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    api.products
      .list(token, {
        q: q.trim() || undefined,
        product_type: typeFilter || null,
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
        else setListError("Không tải được danh mục sản phẩm.");
      })
      .finally(() => setLoading(false));
  }, [token, q, typeFilter, sort, page]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sort, page, typeFilter]);

  useEffect(() => {
    if (!token) return;
    api.products
      .enums(token)
      .then(setEnums)
      .catch(() => setEnums(null));
  }, [token]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  async function openEdit(row: ProductRow) {
    if (!token) return;
    try {
      const detail = await api.products.get(token, row.id);
      setEditing(detail);
      setMode("edit");
    } catch {
      setListError("Không tải được chi tiết sản phẩm.");
    }
  }

  async function confirmDelete() {
    if (!token || !deleting) return;
    const target = deleting;
    try {
      await api.products.remove(token, target.id);
      setDeleting(null);
      // If we deleted the last row on a page, step back a page.
      if (rows.length === 1 && page > 1) setPage((p) => p - 1);
      else load();
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden)
        setListError("Bạn không có quyền xoá sản phẩm.");
      else setListError("Xoá không thành công. Vui lòng thử lại.");
      setDeleting(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (forbidden) {
    return (
      <main className="sp">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Sản phẩm (403).
        </div>
      </main>
    );
  }

  const productTypes = enums?.product_types ?? [];
  const bindingTypes = enums?.binding_types ?? [];

  return (
    <main className="sp">
      <header className="sp__head">
        <p className="eyebrow">Kinh doanh</p>
        <h1 className="sp__title">Sản phẩm in</h1>
        <p className="sp__sub">
          Danh mục sản phẩm dùng lại — loại SP, kiểu đóng, và cấu phần (khổ/giấy/màu/số trang) riêng.
        </p>
      </header>

      <div className="sp__toolbar">
        <form className="sp__search" onSubmit={onSearch} role="search">
          <input
            className="input"
            placeholder="Tìm theo tên / mã…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm sản phẩm"
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>

        <select
          className="input sp__typefilter"
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(1);
          }}
          aria-label="Lọc theo loại sản phẩm"
        >
          <option value="">Tất cả loại SP</option>
          {productTypes.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <div className="sp__toolbar-spacer" />

        <Button
          variant="primary"
          onClick={() => {
            setEditing(null);
            setMode("create");
          }}
        >
          + Tạo sản phẩm
        </Button>
      </div>

      <div className="card sp__tablewrap">
        <table className="sp__table">
          <thead>
            <tr>
              <th>
                <SortBtn label="Mã SP" col="code" sort={sort} onSort={setSort} />
              </th>
              <th>
                <SortBtn label="Tên" col="name" sort={sort} onSort={setSort} />
              </th>
              <th>
                <SortBtn label="Loại SP" col="product_type" sort={sort} onSort={setSort} />
              </th>
              <th>Kiểu đóng</th>
              <th className="sp__num">Số cấu phần</th>
              <th className="sp__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="sp__status" role="status">
                  Đang tải…
                </td>
              </tr>
            ) : listError ? (
              <tr>
                <td colSpan={6} className="sp__status">
                  <div className="banner banner--error" role="alert">
                    <span>{listError}</span>
                    <button type="button" className="btn btn--ghost" onClick={() => load()}>
                      Thử lại
                    </button>
                  </div>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="sp__empty">
                  <p>Chưa có sản phẩm.</p>
                  <Button
                    variant="primary"
                    onClick={() => {
                      setEditing(null);
                      setMode("create");
                    }}
                  >
                    + Tạo sản phẩm
                  </Button>
                </td>
              </tr>
            ) : (
              rows.map((p) => (
                <tr key={p.id} className="sp__row" onClick={() => openEdit(p)}>
                  <td className="sp__mono">{p.code}</td>
                  <td className="sp__name">{p.name}</td>
                  <td>{labelOf(productTypes, p.product_type)}</td>
                  <td>
                    {p.binding_type ? (
                      labelOf(bindingTypes, p.binding_type)
                    ) : (
                      <span className="sp__muted">Không gáy</span>
                    )}
                  </td>
                  <td className="sp__num">{p.component_count}</td>
                  <td className="sp__actions-col" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="btn btn--ghost sp__rowbtn"
                      onClick={() => openEdit(p)}
                    >
                      Sửa
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost sp__rowbtn sp__rowbtn--danger"
                      onClick={() => setDeleting(p)}
                    >
                      Xoá
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && !listError && rows.length > 0 && (
        <div className="sp__pager">
          <span className="sp__muted">
            {total} sản phẩm · trang {page}/{totalPages}
          </span>
          <div className="sp__pager-btns">
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

      {mode && enums && (
        <ProductFormDialog
          enums={enums}
          existing={mode === "edit" ? editing : null}
          onClose={() => {
            setMode(null);
            setEditing(null);
          }}
          onSaved={() => {
            setMode(null);
            setEditing(null);
            if (mode === "create") setPage(1);
            load();
          }}
        />
      )}

      {deleting && (
        <ConfirmDeleteDialog
          product={deleting}
          onCancel={() => setDeleting(null)}
          onConfirm={confirmDelete}
        />
      )}
    </main>
  );
}

// --- Sort header button -----------------------------------------------------

function SortBtn({
  label,
  col,
  sort,
  onSort,
}: {
  label: string;
  col: string;
  sort: string;
  onSort: (s: string) => void;
}) {
  const active = sort === col || sort === `-${col}`;
  const desc = sort === `-${col}`;
  return (
    <button
      type="button"
      className={`sp__sortbtn${active ? " is-active" : ""}`}
      onClick={() => onSort(desc ? col : active ? `-${col}` : col)}
    >
      {label}
      {active && <span aria-hidden="true">{desc ? " ↓" : " ↑"}</span>}
    </button>
  );
}

// --- Create / Edit dialog (Khối A + Khối B) --------------------------------

function ProductFormDialog({
  enums,
  existing,
  onClose,
  onSaved,
}: {
  enums: ProductEnumsOut;
  existing: ProductDetailOut | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [name, setName] = useState(existing?.name ?? "");
  const [productType, setProductType] = useState(
    existing?.product_type ?? enums.product_types[0]?.value ?? "",
  );
  const [binding, setBinding] = useState(existing?.binding_type ?? BINDING_NONE);
  const [note, setNote] = useState(existing?.note ?? "");
  const [comps, setComps] = useState<CompForm[]>(
    existing
      ? existing.components.map((c) => {
          COMP_KEY += 1;
          return {
            key: `e${c.id}-${COMP_KEY}`,
            component_type: c.component_type,
            paper_master_id: c.paper_master_id != null ? String(c.paper_master_id) : "",
            colors_front: String(c.colors_front),
            colors_back: String(c.colors_back),
            page_count: String(c.page_count),
            finished_w: String(c.finished_w),
            finished_h: String(c.finished_h),
            bleed: String(c.bleed),
            grain_direction: c.grain_direction ?? "",
          };
        })
      : [],
  );

  const [saving, setSaving] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // SEAM-03 paper picker state (fetched once; renders "chưa sẵn sàng" when not built).
  const [paperReady, setPaperReady] = useState(false);
  const [paperMsg, setPaperMsg] = useState("Danh mục Giấy chưa sẵn sàng");
  useEffect(() => {
    if (!token) return;
    api.products
      .papers(token)
      .then((p) => {
        setPaperReady(p.available);
        if (!p.available && p.message) setPaperMsg(p.message);
      })
      .catch(() => setPaperReady(false));
  }, [token]);

  const bound = binding !== BINDING_NONE && binding !== "";

  function updateComp(key: string, patch: Partial<CompForm>) {
    setComps((cs) => cs.map((c) => (c.key === key ? { ...c, ...patch } : c)));
    setFormError(null);
  }
  function addComp() {
    setComps((cs) => [...cs, newComp(cs.length === 0 ? "cover" : "body")]);
    setFormError(null);
  }
  function removeComp(key: string) {
    setComps((cs) => cs.filter((c) => c.key !== key));
  }
  function move(key: string, dir: -1 | 1) {
    setComps((cs) => {
      const i = cs.findIndex((c) => c.key === key);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= cs.length) return cs;
      const next = [...cs];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  function validate(): string | null {
    if (!name.trim()) {
      setNameError("Tên sản phẩm là bắt buộc.");
      return "name";
    }
    if (bound && comps.length === 0) {
      return "Sản phẩm có gáy cần ít nhất 1 cấu phần.";
    }
    for (let i = 0; i < comps.length; i++) {
      const c = comps[i];
      const n = i + 1;
      const cf = Number(c.colors_front);
      const cb = Number(c.colors_back);
      if (Number.isNaN(cf) || cf < 0 || cf > 8)
        return `Cấu phần ${n}: số màu mặt trước phải trong khoảng 0..8.`;
      if (Number.isNaN(cb) || cb < 0 || cb > 8)
        return `Cấu phần ${n}: số màu mặt sau phải trong khoảng 0..8.`;
      const pc = Number(c.page_count);
      if (!Number.isInteger(pc) || pc <= 0)
        return `Cấu phần ${n}: số trang phải lớn hơn 0.`;
      if (bound && c.component_type === "body" && pc % 4 !== 0)
        return `Cấu phần ${n}: số trang ruột phải chia hết cho 4 (tay sách 4/8/16/32).`;
      const fw = Number(c.finished_w);
      const fh = Number(c.finished_h);
      if (Number.isNaN(fw) || fw <= 0) return `Cấu phần ${n}: khổ rộng phải lớn hơn 0.`;
      if (Number.isNaN(fh) || fh <= 0) return `Cấu phần ${n}: khổ cao phải lớn hơn 0.`;
      const bl = Number(c.bleed || "0");
      if (Number.isNaN(bl) || bl < 0) return `Cấu phần ${n}: bleed không được âm.`;
    }
    return null;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setNameError(null);
    setFormError(null);
    const problem = validate();
    if (problem === "name") return;
    if (problem) {
      setFormError(problem);
      return;
    }

    const components: ComponentInput[] = comps.map((c, i) => ({
      component_type: c.component_type,
      paper_master_id: c.paper_master_id ? Number(c.paper_master_id) : null,
      colors_front: Number(c.colors_front),
      colors_back: Number(c.colors_back),
      page_count: Number(c.page_count),
      finished_w: Number(c.finished_w),
      finished_h: Number(c.finished_h),
      bleed: Number(c.bleed || "0"),
      grain_direction: c.grain_direction || null,
      sequence: i,
    }));
    const input: ProductInput = {
      name: name.trim(),
      product_type: productType,
      binding_type: bound ? binding : null,
      note: note.trim() || null,
      components,
    };

    setSaving(true);
    try {
      if (isEdit && existing) await api.products.update(token, existing.id, input);
      else await api.products.create(token, input);
      onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) {
        setNameError("Tên sản phẩm đã tồn tại.");
      } else if (err instanceof ApiError && err.isForbidden) {
        setFormError("Bạn không có quyền thực hiện thao tác này.");
      } else if (err instanceof ApiError && err.status === 422) {
        setFormError(err.message);
      } else {
        setFormError("Lưu không thành công. Vui lòng thử lại.");
      }
      setSaving(false);
    }
  }

  const title = isEdit ? `Sửa sản phẩm · ${existing!.code}` : "Tạo sản phẩm";

  return (
    <div className="sp__overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="sp__dialog card">
        <div className="sp__dialog-head">
          <h2>{title}</h2>
          <button type="button" className="sp__close" aria-label="Đóng" onClick={onClose}>
            ✕
          </button>
        </div>

        <form className="sp__dialog-body" onSubmit={onSubmit}>
          {/* Khối A — Product head */}
          <section>
            <h3 className="sp__section-title">Thông tin sản phẩm</h3>
            <div className="sp__form-grid">
              <label className="field">
                <span className="field__label">Mã SP</span>
                <input
                  className="input"
                  value={existing?.code ?? "(tự sinh)"}
                  readOnly
                  disabled
                />
              </label>
              <label className="field">
                <span className="field__label">Tên sản phẩm *</span>
                <input
                  className="input"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setNameError(null);
                  }}
                  aria-invalid={!!nameError}
                />
                {nameError && (
                  <span className="sp__err" role="alert">
                    {nameError}
                  </span>
                )}
              </label>
              <label className="field">
                <span className="field__label">Loại SP</span>
                <select
                  className="input"
                  value={productType}
                  onChange={(e) => setProductType(e.target.value)}
                >
                  {enums.product_types.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Kiểu đóng</span>
                <select
                  className="input"
                  value={binding}
                  onChange={(e) => setBinding(e.target.value)}
                >
                  {enums.binding_types.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field sp__form-wide">
                <span className="field__label">Ghi chú</span>
                <input
                  className="input"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
            </div>
          </section>

          {/* Khối B — Components */}
          <section>
            <div className="sp__section-head">
              <h3 className="sp__section-title">
                Cấu phần {bound && <span className="sp__req">(bắt buộc ≥1)</span>}
              </h3>
              <button type="button" className="btn btn--ghost" onClick={addComp}>
                + Thêm cấu phần
              </button>
            </div>

            {comps.length === 0 ? (
              <p className="sp__muted sp__comp-empty">
                {bound
                  ? "Sản phẩm có gáy cần ít nhất 1 cấu phần."
                  : "SP không gáy có thể không cần cấu phần."}
              </p>
            ) : (
              <div className="sp__comp-list">
                {comps.map((c, i) => (
                  <ComponentEditor
                    key={c.key}
                    comp={c}
                    index={i}
                    total={comps.length}
                    enums={enums}
                    paperReady={paperReady}
                    paperMsg={paperMsg}
                    onChange={(patch) => updateComp(c.key, patch)}
                    onRemove={() => removeComp(c.key)}
                    onMove={(dir) => move(c.key, dir)}
                  />
                ))}
              </div>
            )}
          </section>

          {formError && (
            <div className="banner banner--error" role="alert">
              {formError}
            </div>
          )}

          <div className="sp__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>
              Huỷ
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

function ComponentEditor({
  comp,
  index,
  total,
  enums,
  paperReady,
  paperMsg,
  onChange,
  onRemove,
  onMove,
}: {
  comp: CompForm;
  index: number;
  total: number;
  enums: ProductEnumsOut;
  paperReady: boolean;
  paperMsg: string;
  onChange: (patch: Partial<CompForm>) => void;
  onRemove: () => void;
  onMove: (dir: -1 | 1) => void;
}) {
  return (
    <div className="sp__comp card">
      <div className="sp__comp-head">
        <span className="sp__comp-badge">#{index + 1}</span>
        <select
          className="input sp__comp-type"
          value={comp.component_type}
          onChange={(e) => onChange({ component_type: e.target.value })}
          aria-label={`Loại cấu phần ${index + 1}`}
        >
          {enums.component_types.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <div className="sp__comp-tools">
          <button
            type="button"
            className="btn btn--ghost sp__rowbtn"
            disabled={index === 0}
            onClick={() => onMove(-1)}
            aria-label="Lên"
          >
            ↑
          </button>
          <button
            type="button"
            className="btn btn--ghost sp__rowbtn"
            disabled={index === total - 1}
            onClick={() => onMove(1)}
            aria-label="Xuống"
          >
            ↓
          </button>
          <button
            type="button"
            className="btn btn--ghost sp__rowbtn sp__rowbtn--danger"
            onClick={onRemove}
          >
            Xoá
          </button>
        </div>
      </div>

      <div className="sp__comp-grid">
        <NumField
          label="Màu mặt trước"
          value={comp.colors_front}
          onChange={(v) => onChange({ colors_front: v })}
        />
        <NumField
          label="Màu mặt sau"
          value={comp.colors_back}
          onChange={(v) => onChange({ colors_back: v })}
        />
        <NumField
          label="Số trang"
          value={comp.page_count}
          onChange={(v) => onChange({ page_count: v })}
        />
        <NumField
          label="Khổ rộng (cm)"
          value={comp.finished_w}
          onChange={(v) => onChange({ finished_w: v })}
          step="0.1"
        />
        <NumField
          label="Khổ cao (cm)"
          value={comp.finished_h}
          onChange={(v) => onChange({ finished_h: v })}
          step="0.1"
        />
        <NumField
          label="Bleed (mm)"
          value={comp.bleed}
          onChange={(v) => onChange({ bleed: v })}
          step="0.1"
        />
        <label className="field">
          <span className="field__label">Canh thớ</span>
          <select
            className="input"
            value={comp.grain_direction}
            onChange={(e) => onChange({ grain_direction: e.target.value })}
          >
            <option value="">—</option>
            {enums.grain_directions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        {/* SEAM-03: paper picker — explicit "chưa sẵn sàng" until Danh mục Giấy is built. */}
        <label className="field sp__form-wide">
          <span className="field__label">Giấy</span>
          {paperReady ? (
            <input
              className="input"
              value={comp.paper_master_id}
              onChange={(e) => onChange({ paper_master_id: e.target.value })}
              placeholder="Chọn giấy"
            />
          ) : (
            <div className="sp__paper-seam" role="note">
              <span className="sp__paper-tag">{paperMsg}</span>
              <span className="sp__muted">
                Sẽ chọn được giấy khi phân hệ Danh mục Giấy có sẵn (SEAM-03).
              </span>
            </div>
          )}
        </label>
      </div>
    </div>
  );
}

function NumField({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: string;
}) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      <input
        className="input"
        type="number"
        step={step ?? "1"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

// --- Delete confirm ---------------------------------------------------------

function ConfirmDeleteDialog({
  product,
  onCancel,
  onConfirm,
}: {
  product: ProductRow;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="sp__overlay" role="dialog" aria-modal="true" aria-label="Xoá sản phẩm">
      <div className="sp__dialog sp__dialog--sm card">
        <div className="sp__dialog-head">
          <h2>Xoá sản phẩm</h2>
          <button type="button" className="sp__close" aria-label="Đóng" onClick={onCancel}>
            ✕
          </button>
        </div>
        <div className="sp__dialog-body">
          <p>
            Xoá sản phẩm <strong>{product.code} · {product.name}</strong>? Cấu phần con sẽ bị
            xoá theo. Hành động không thể hoàn tác.
          </p>
          <div className="sp__dialog-actions">
            <Button type="button" variant="ghost" onClick={onCancel}>
              Huỷ
            </Button>
            <Button
              type="button"
              variant="primary"
              loading={busy}
              onClick={() => {
                setBusy(true);
                onConfirm();
              }}
            >
              Xoá
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
