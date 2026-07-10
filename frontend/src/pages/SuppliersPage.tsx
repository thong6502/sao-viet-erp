import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ApiError,
  api,
  type SupplierInput,
  type SupplierRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";
import "./purchase.css";

const PAGE_SIZE = 12;

function emptySupplier(): SupplierInput {
  return {
    name: "",
    tax_code: "",
    phone: "",
    email: "",
    address: "",
    contact_name: "",
    supplier_group: "",
    payment_terms: "",
    status: "active",
    note: "",
  };
}

function fromSupplier(row: SupplierRow): SupplierInput {
  return {
    name: row.name,
    tax_code: row.tax_code ?? "",
    phone: row.phone ?? "",
    email: row.email ?? "",
    address: row.address ?? "",
    contact_name: row.contact_name ?? "",
    supplier_group: row.supplier_group ?? "",
    payment_terms: row.payment_terms ?? "",
    status: row.status,
    note: row.note ?? "",
  };
}

function cleanSupplier(input: SupplierInput): SupplierInput {
  const trimOptional = (v?: string | null) => {
    const s = (v ?? "").trim();
    return s || null;
  };
  return {
    name: (input.name ?? "").trim(),
    tax_code: (input.tax_code ?? "").trim(),
    phone: (input.phone ?? "").trim(),
    email: (input.email ?? "").trim(),
    address: (input.address ?? "").trim(),
    contact_name: (input.contact_name ?? "").trim(),
    supplier_group: (input.supplier_group ?? "").trim(),
    payment_terms: trimOptional(input.payment_terms),
    status: input.status ?? "active",
    note: trimOptional(input.note),
  };
}

const REQUIRED_SUPPLIER_FIELDS: Array<[keyof SupplierInput, string]> = [
  ["name", "Tên nhà cung cấp"],
  ["supplier_group", "Nhóm"],
  ["tax_code", "Mã số thuế"],
  ["contact_name", "Người liên hệ"],
  ["phone", "Số điện thoại"],
  ["email", "Email"],
  ["address", "Địa chỉ"],
];

export function SuppliersPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("thu_mua", "create");
  const canUpdate = can("thu_mua", "update");

  const [rows, setRows] = useState<SupplierRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"all" | "active" | "inactive">("active");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [selected, setSelected] = useState<SupplierRow | null>(null);
  const [form, setForm] = useState<SupplierInput>(emptySupplier());
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.suppliers
      .list(token, {
        q: q.trim() || undefined,
        status: status === "all" ? null : status,
        sort: "name",
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh sách nhà cung cấp.");
      })
      .finally(() => setLoading(false));
  }, [token, q, status, page]);

  useEffect(() => {
    load();
  }, [load]);

  function openCreate() {
    setSelected(null);
    setForm(emptySupplier());
    setFormError(null);
    setMode("create");
  }

  function openEdit(row: SupplierRow) {
    setSelected(row);
    setForm(fromSupplier(row));
    setFormError(null);
    setMode("edit");
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    const payload = cleanSupplier(form);
    const missing = REQUIRED_SUPPLIER_FIELDS.filter(
      ([key]) => !String(payload[key] ?? "").trim(),
    ).map(([, label]) => label);
    if (missing.length > 0) {
      setFormError(`Vui lòng nhập đầy đủ: ${missing.join(", ")}.`);
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      if (mode === "edit" && selected)
        await api.suppliers.update(token, selected.id, payload);
      else await api.suppliers.create(token, payload);
      setMode(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setFormError(err.message);
      else setFormError("Không lưu được nhà cung cấp.");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(row: SupplierRow) {
    if (!token || !canUpdate) return;
    try {
      await api.suppliers.toggleActive(token, row.id);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không đổi được trạng thái nhà cung cấp.");
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Nhà cung cấp (403).
        </div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Thu mua</p>
        <h1 className="md-page__title">Nhà cung cấp</h1>
        <p className="md-page__sub">
          Danh mục đối tác do bộ phận mua hàng quản lý, dùng để chọn vào phiếu
          yêu cầu mua hàng.
        </p>
      </header>

      <div className="md-page__toolbar">
        <form
          className="md-page__search"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            load();
          }}
        >
          <input
            className="input"
            placeholder="Tìm tên, MST, số điện thoại..."
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>
        <select
          className="input purchase__select"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as "all" | "active" | "inactive");
            setPage(1);
          }}
        >
          <option value="active">Đang hợp tác</option>
          <option value="inactive">Ngừng hợp tác</option>
          <option value="all">Tất cả trạng thái</option>
        </select>
        <div className="md-page__toolbar-spacer" />
        {canCreate && (
          <Button variant="primary" onClick={openCreate}>
            + Thêm NCC
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
              <th>Tên nhà cung cấp</th>
              <th>Nhóm</th>
              <th>MST</th>
              <th>Liên hệ</th>
              <th>Thanh toán</th>
              <th>Trạng thái</th>
              {canUpdate && <th className="md-page__actions-col">Thao tác</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="md-page__status">
                  Đang tải dữ liệu...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="md-page__empty">
                  Chưa có nhà cung cấp phù hợp.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="md-page__row"
                  onClick={canUpdate ? () => openEdit(row) : undefined}
                >
                  <td>
                    <strong>{row.name}</strong>
                    {row.address && (
                      <div className="md-page__muted">{row.address}</div>
                    )}
                  </td>
                  <td>
                    {row.supplier_group || (
                      <span className="md-page__muted">—</span>
                    )}
                  </td>
                  <td className="md-page__mono">
                    {row.tax_code || <span className="md-page__muted">—</span>}
                  </td>
                  <td>
                    <div>
                      {row.contact_name || (
                        <span className="md-page__muted">—</span>
                      )}
                    </div>
                    <div className="md-page__muted">
                      {row.phone || row.email || "—"}
                    </div>
                  </td>
                  <td>
                    {row.payment_terms || (
                      <span className="md-page__muted">—</span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`md-purchase__status-badge ${
                        row.status === "active" ? "is-active" : "is-inactive"
                      }`}
                    >
                      {row.status === "active" ? "Hoạt động" : "Tạm ngừng"}
                    </span>
                  </td>
                  {canUpdate && (
                    <td
                      className="md-page__actions-col"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => openEdit(row)}
                      >
                        Sửa
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => toggle(row)}
                      >
                        {row.status === "active" ? "Ngừng" : "Mở"}
                      </button>
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
            Tổng số: {total} NCC · Trang {page}/{totalPages}
          </span>
          <div className="md-page__pager-btns">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Trước
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Sau
            </button>
          </div>
        </div>
      )}

      {mode && (
        <div className="md-page__overlay" role="presentation">
          <div className="card md-page__dialog" role="dialog" aria-modal="true">
            <div className="md-page__dialog-head">
              <h2>
                {mode === "edit" ? "Sửa nhà cung cấp" : "Thêm nhà cung cấp"}
              </h2>
              <button
                type="button"
                className="md-page__close"
                onClick={() => setMode(null)}
              >
                ×
              </button>
            </div>
            <form className="md-page__dialog-body" onSubmit={save}>
              {formError && (
                <div className="banner banner--error" role="alert">
                  {formError}
                </div>
              )}
              <div className="md-page__form-grid">
                <LocalField label="Tên nhà cung cấp" required>
                  <input
                    className="input"
                    required
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </LocalField>
                <LocalField label="Nhóm" required>
                  <input
                    className="input"
                    required
                    value={form.supplier_group ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, supplier_group: e.target.value })
                    }
                    placeholder="paper, ink, outsourcing..."
                  />
                </LocalField>
                <LocalField label="Mã số thuế" required>
                  <input
                    className="input"
                    required
                    value={form.tax_code ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, tax_code: e.target.value })
                    }
                  />
                </LocalField>
                <LocalField label="Người liên hệ" required>
                  <input
                    className="input"
                    required
                    value={form.contact_name ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, contact_name: e.target.value })
                    }
                  />
                </LocalField>
                <LocalField label="Số điện thoại" required>
                  <input
                    className="input"
                    required
                    value={form.phone ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, phone: e.target.value })
                    }
                  />
                </LocalField>
                <LocalField label="Email" required>
                  <input
                    className="input"
                    required
                    type="email"
                    value={form.email ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, email: e.target.value })
                    }
                  />
                </LocalField>
                <LocalField label="Điều khoản thanh toán">
                  <input
                    className="input"
                    value={form.payment_terms ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, payment_terms: e.target.value })
                    }
                    placeholder="Công nợ 30 ngày..."
                  />
                </LocalField>
                <LocalField label="Trạng thái">
                  <select
                    className="input"
                    value={form.status ?? "active"}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        status: e.target.value as "active" | "inactive",
                      })
                    }
                  >
                    <option value="active">Hoạt động</option>
                    <option value="inactive">Tạm ngừng</option>
                  </select>
                </LocalField>
                <LocalField label="Địa chỉ" wide required>
                  <input
                    className="input"
                    required
                    value={form.address ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, address: e.target.value })
                    }
                  />
                </LocalField>
                <LocalField label="Ghi chú" wide>
                  <textarea
                    className="input purchase__textarea"
                    value={form.note ?? ""}
                    onChange={(e) => setForm({ ...form, note: e.target.value })}
                  />
                </LocalField>
              </div>
              <div className="md-page__dialog-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setMode(null)}
                  disabled={saving}
                >
                  Hủy
                </button>
                <Button type="submit" variant="accent" loading={saving}>
                  Lưu
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}

function LocalField({
  label,
  wide = false,
  required = false,
  children,
}: {
  label: string;
  wide?: boolean;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`purchase__field${wide ? " md-page__form-wide" : ""}`}>
      <span>
        {label}
        {required && <span className="purchase__required-star"> *</span>}
      </span>
      {children}
    </label>
  );
}
