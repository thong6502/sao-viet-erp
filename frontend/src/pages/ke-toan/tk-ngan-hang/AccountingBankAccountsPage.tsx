// Màn TÀI KHOẢN NGÂN HÀNG — shell (tách từ pages/AccountingBankAccountsPage.tsx).
// Giữ ở đây: state + `load()` + handlers (`openCreate`/`openEdit`/`closeModal`/`cleanForm`/`save`)
// + chỗ mount bảng và hộp thoại.
// ⚠️ Nhánh `tab === "supplier"` CHẾT CỨNG từ bản gốc: `useState("company")` KHÔNG có setter và
// cụm tab đã bị comment out. Giữ nguyên y hệt — đây là PURE MOVE, không phải lượt dọn code chết.
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
  type CompanyBankAccountRow,
  type SupplierBankAccountInput,
  type SupplierBankAccountRow,
  type SupplierRow,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import { Button } from "../../../components/Button";
import { BankAccountTable } from "./components/BankAccountTable";
import { BankAccountModal } from "./modals/BankAccountModal";
import { emptyAccount, isCompanyAccount } from "./shared/helpers";
import type { AccountForm, AccountRow, AccountTab } from "./shared/types";
import "../../accounting.css";
import "../../purchase.css";

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
      <BankAccountTable
        tab={tab}
        loading={loading}
        rows={rows}
        canManage={canManage}
        openEdit={openEdit}
      />

      {modalOpen && (
        <BankAccountModal
          tab={tab}
          suppliers={suppliers}
          formSupplierId={formSupplierId}
          setFormSupplierId={setFormSupplierId}
          form={form}
          setForm={setForm}
          editing={editing}
          busy={busy}
          closeModal={closeModal}
          save={save}
        />
      )}
    </main>
  );
}
