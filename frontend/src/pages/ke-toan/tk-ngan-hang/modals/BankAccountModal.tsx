// Hộp thêm/sửa TÀI KHOẢN NGÂN HÀNG (tách từ pages/AccountingBankAccountsPage.tsx).
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`) thay `acct-modal`
// nền trắng giữa màn — chủ chốt 26/08/2026: "sao mỗi nơi một màu". Đây là FORM NHẬP LIỆU nên
// đóng AN TOÀN: scrim KHÔNG bắt click, KHÔNG Esc-to-close (tránh mất dữ liệu đang gõ).
import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { SupplierRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import type { AccountForm, AccountRow, AccountTab } from "../shared/types";

export function BankAccountModal({
  tab,
  suppliers,
  formSupplierId,
  setFormSupplierId,
  form,
  setForm,
  editing,
  busy,
  closeModal,
  save,
}: {
  tab: AccountTab;
  suppliers: SupplierRow[];
  formSupplierId: number | null;
  setFormSupplierId: Dispatch<SetStateAction<number | null>>;
  form: AccountForm;
  setForm: Dispatch<SetStateAction<AccountForm>>;
  editing: AccountRow | null;
  busy: boolean;
  closeModal: () => void;
  save: (event: FormEvent) => Promise<void>;
}) {
  return (
    <div className="rc-drawer__scrim" role="presentation">
      <aside
        className="rc-drawer purchase__drawer-780"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={editing ? "Sửa tài khoản" : "Thêm tài khoản"}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Tài khoản ngân hàng</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">
                  {editing ? "Sửa tài khoản" : "Thêm tài khoản"}
                </h2>
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={closeModal}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>{tab === "supplier" ? "Của nhà cung cấp" : "Của công ty"}</span>
          </div>
        </div>
        <form className="purchase__drawer-form" onSubmit={save}>
        <div className="rc-drawer__body">
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
        <div className="purchase__drawer-footer">
          <Button type="button" variant="ghost" onClick={closeModal}>
            Hủy
          </Button>
          <Button type="submit" variant="accent" loading={busy}>
            Lưu tài khoản
          </Button>
        </div>
        </form>
      </aside>
    </div>
  );
}
