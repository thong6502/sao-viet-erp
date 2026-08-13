import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountInput,
  type CompanyBankAccountRow,
  type SupplierBankAccountInput,
  type SupplierBankAccountRow,
  type SupplierRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./accounting.css";

type AccountTab = "company" | "supplier";
type AccountRow = CompanyBankAccountRow | SupplierBankAccountRow;
type AccountForm = CompanyBankAccountInput;

function isCompanyAccount(row: AccountRow): row is CompanyBankAccountRow {
  return "use_for_receipts" in row;
}

function emptyAccount(): AccountForm {
  return {
    account_holder: "",
    account_number: "",
    bank_name: "",
    bank_branch: "",
    currency: "VND",
    is_default: false,
    is_active: true,
    use_for_receipts: true,
    use_for_payments: true,
    note: null,
  };
}

export function AccountingBankAccountsPage() {
  const { token } = useAuth();
  const can = useCan();
  // Khoá RIÊNG của màn Tài khoản ngân hàng (tách 10/08/2026). TK của nhà cung cấp là dữ liệu
  // gốc của NCC nên người quản danh mục NCC cũng sửa được — cùng luật với máy chủ.
  const canManageCompany = can("tk_ngan_hang", "update");
  const canManageSupplier =
    can("tk_ngan_hang", "update") || can("nha_cung_cap", "update");
  const [tab] = useState<AccountTab>("company");
  const [companyRows, setCompanyRows] = useState<CompanyBankAccountRow[]>([]);
  const [supplierRows, setSupplierRows] = useState<SupplierBankAccountRow[]>(
    [],
  );
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [supplierFilter, setSupplierFilter] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AccountRow | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<AccountForm>(emptyAccount());
  const [formSupplierId, setFormSupplierId] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api.accounting.companyAccounts(token, false),
      api.accounting.supplierAccounts(token, supplierFilter, false),
      api.suppliers.list(token, {
        status: "active",
        sort: "name",
        page: 1,
        size: 200,
      }),
    ])
      .then(([company, supplier, supplierList]) => {
        setCompanyRows(company);
        setSupplierRows(supplier);
        setSuppliers(supplierList.items);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được tài khoản ngân hàng.",
        ),
      )
      .finally(() => setLoading(false));
  }, [token, supplierFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo<AccountRow[]>(
    () => (tab === "company" ? companyRows : supplierRows),
    [tab, companyRows, supplierRows],
  );
  const canManage = tab === "company" ? canManageCompany : canManageSupplier;

  function openCreate() {
    setEditing(null);
    setForm(emptyAccount());
    setFormSupplierId(
      tab === "supplier" ? (supplierFilter ?? suppliers[0]?.id ?? null) : null,
    );
    setModalOpen(true);
  }

  function openEdit(row: AccountRow) {
    setEditing(row);
    setForm({
      account_holder: row.account_holder,
      account_number: row.account_number,
      bank_name: row.bank_name,
      bank_branch: row.bank_branch,
      currency: row.currency,
      is_default: false,
      is_active: row.is_active,
      use_for_receipts: isCompanyAccount(row) ? row.use_for_receipts : false,
      use_for_payments: isCompanyAccount(row) ? row.use_for_payments : false,
      note: row.note,
    });
    setFormSupplierId("supplier_id" in row ? row.supplier_id : null);
    setModalOpen(true);
  }

  function closeModal() {
    setEditing(null);
    setForm(emptyAccount());
    setFormSupplierId(null);
    setModalOpen(false);
    const dialog = document.activeElement as HTMLElement | null;
    dialog?.blur();
  }

  function cleanForm(): AccountForm {
    return {
      account_holder: form.account_holder.trim(),
      account_number: form.account_number.trim(),
      bank_name: form.bank_name.trim(),
      bank_branch: form.bank_branch.trim(),
      currency: form.currency.trim().toUpperCase(),
      is_default: false,
      is_active: form.is_active,
      use_for_receipts: form.use_for_receipts,
      use_for_payments: form.use_for_payments,
      note: form.note?.trim() || null,
    };
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!token || busy) return;
    const payload = cleanForm();
    if (
      !payload.account_holder ||
      !payload.account_number ||
      !payload.bank_name ||
      !payload.bank_branch
    ) {
      setError(
        "Chủ tài khoản, số tài khoản, ngân hàng và chi nhánh đều bắt buộc.",
      );
      return;
    }
    if (tab === "supplier" && !formSupplierId) {
      setError("Vui lòng chọn nhà cung cấp.");
      return;
    }
    if (
      tab === "company" &&
      !payload.use_for_receipts &&
      !payload.use_for_payments
    ) {
      setError("Tài khoản công ty phải dùng để thu, để chi hoặc cả hai.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (tab === "company") {
        if (editing)
          await api.accounting.updateCompanyAccount(token, editing.id, payload);
        else await api.accounting.createCompanyAccount(token, payload);
      } else {
        const supplierPayload: SupplierBankAccountInput = {
          account_holder: payload.account_holder,
          account_number: payload.account_number,
          bank_name: payload.bank_name,
          bank_branch: payload.bank_branch,
          currency: payload.currency,
          is_default: false,
          is_active: payload.is_active,
          note: payload.note,
          supplier_id: formSupplierId!,
        };
        if (editing)
          await api.accounting.updateSupplierAccount(
            token,
            editing.id,
            supplierPayload,
          );
        else await api.accounting.createSupplierAccount(token, supplierPayload);
      }
      closeModal();
      load();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không lưu được tài khoản ngân hàng.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function toggle(row: AccountRow) {
    if (!token) return;
    setBusy(true);
    try {
      if ("supplier_id" in row)
        await api.accounting.toggleSupplierAccount(token, row.id);
      else await api.accounting.toggleCompanyAccount(token, row.id);
      load();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không đổi được trạng thái tài khoản.",
      );
    } finally {
      setBusy(false);
    }
  }

  function createForCurrentTab() {
    openCreate();
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">Tài khoản ngân hàng</h1>
        <p className="md-page__sub">
          Quản lý tài khoản ngân hàng công ty dùng để thu/chi chuyển khoản và
          tài khoản thụ hưởng của nhà cung cấp.
        </p>
      </header>
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}
      {/* <div className="acct-tabs" role="tablist">
        <button
          className={tab === "company" ? "is-active" : ""}
          onClick={() => setTab("company")}
        >
          Tài khoản công ty
        </button>
        <button
          className={tab === "supplier" ? "is-active" : ""}
          onClick={() => setTab("supplier")}
        >
          Tài khoản nhà cung cấp
        </button>
      </div> */}
      <section className="acct-toolbar">
        {tab === "supplier" ? (
          <select
            className="input acct-toolbar__select"
            value={supplierFilter ?? ""}
            onChange={(event) =>
              setSupplierFilter(
                event.target.value ? Number(event.target.value) : null,
              )
            }
          >
            <option value="">Tất cả nhà cung cấp</option>
            {suppliers.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        ) : (
          <div />
        )}
        {canManage && (
          <Button variant="primary" onClick={createForCurrentTab}>
            Thêm tài khoản
          </Button>
        )}
      </section>
      <section className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              {tab === "supplier" && <th>Nhà cung cấp</th>}
              <th>Chủ tài khoản</th>
              <th>Số tài khoản</th>
              <th>Ngân hàng</th>
              <th>Chi nhánh</th>
              <th>Loại tiền</th>
              {tab === "company" && <th>Mục đích</th>}
              <th>Trạng thái</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={8}>Đang tải...</td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={8}>Chưa có tài khoản ngân hàng.</td>
              </tr>
            )}
            {!loading &&
              rows.map((row) => {
                const company = isCompanyAccount(row) ? row : null;
                return (
                  <tr key={`${tab}-${row.id}`}>
                    {tab === "supplier" && (
                      <td>
                        {"supplier_name" in row ? row.supplier_name : "—"}
                      </td>
                    )}
                    <td>
                      <strong>{row.account_holder}</strong>
                    </td>
                    <td>{row.account_number}</td>
                    <td>{row.bank_name}</td>
                    <td>{row.bank_branch}</td>
                    <td>{row.currency}</td>
                    {tab === "company" && (
                      <td>
                        <div className="acct-purpose-tags">
                          {company?.use_for_receipts && <span>Thu</span>}
                          {company?.use_for_payments && <span>Chi</span>}
                        </div>
                      </td>
                    )}
                    <td>
                      <span
                        className={`acct-voucher-status acct-voucher-status--${
                          row.is_active ? "paid" : "cancelled"
                        }`}
                      >
                        {row.is_active ? "Hoạt động" : "Ngừng dùng"}
                      </span>
                    </td>
                    <td>
                      <div className="acct-actions acct-actions--compact">
                        {canManage && (
                          <>
                            <Button
                              variant="ghost"
                              onClick={() => openEdit(row)}
                            >
                              Sửa
                            </Button>
                            <Button
                              variant="ghost"
                              disabled={busy}
                              onClick={() => toggle(row)}
                            >
                              {row.is_active ? "Ngừng dùng" : "Bật lại"}
                            </Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </section>

      {modalOpen && (
        <div className="acct-modal" role="dialog" aria-modal="true">
          <form className="acct-modal__box" onSubmit={save}>
            <header className="acct-modal__head">
              <h2>{editing ? "Sửa tài khoản" : "Thêm tài khoản"}</h2>
              <button
                type="button"
                className="acct-modal__x"
                onClick={closeModal}
              >
                ×
              </button>
            </header>
            <div className="acct-modal__body">
              {tab === "supplier" && (
                <label className="acct-field">
                  <span>
                    Nhà cung cấp <b>*</b>
                  </span>
                  <select
                    className="input"
                    value={formSupplierId ?? ""}
                    onChange={(event) =>
                      setFormSupplierId(
                        event.target.value ? Number(event.target.value) : null,
                      )
                    }
                  >
                    <option value="">Chọn nhà cung cấp</option>
                    {suppliers.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="acct-form-grid acct-form-grid--2">
                <label className="acct-field">
                  <span>
                    Chủ tài khoản <b>*</b>
                  </span>
                  <input
                    autoFocus
                    className="input"
                    value={form.account_holder}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        account_holder: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="acct-field">
                  <span>
                    Số tài khoản <b>*</b>
                  </span>
                  <input
                    className="input"
                    value={form.account_number}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        account_number: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="acct-field">
                  <span>
                    Ngân hàng <b>*</b>
                  </span>
                  <input
                    className="input"
                    value={form.bank_name}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        bank_name: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="acct-field">
                  <span>
                    Chi nhánh <b>*</b>
                  </span>
                  <input
                    className="input"
                    value={form.bank_branch}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        bank_branch: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="acct-field">
                  <span>Loại tiền</span>
                  <input
                    className="input"
                    maxLength={3}
                    value={form.currency}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        currency: event.target.value.toUpperCase(),
                      }))
                    }
                  />
                </label>
              </div>
              <div className="acct-checks">
                <label>
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        is_active: event.target.checked,
                      }))
                    }
                  />{" "}
                  Đang hoạt động
                </label>
                {tab === "company" && (
                  <>
                    <label>
                      <input
                        type="checkbox"
                        checked={form.use_for_receipts}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            use_for_receipts: event.target.checked,
                          }))
                        }
                      />{" "}
                      Dùng để thu
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={form.use_for_payments}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            use_for_payments: event.target.checked,
                          }))
                        }
                      />{" "}
                      Dùng để chi
                    </label>
                  </>
                )}
              </div>
              <label className="acct-field">
                <span>Ghi chú</span>
                <textarea
                  className="input acct-textarea"
                  value={form.note ?? ""}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      note: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
            <footer className="acct-modal__foot">
              <Button type="button" variant="ghost" onClick={closeModal}>
                Hủy
              </Button>
              <Button type="submit" variant="accent" loading={busy}>
                Lưu tài khoản
              </Button>
            </footer>
          </form>
        </div>
      )}
    </main>
  );
}
