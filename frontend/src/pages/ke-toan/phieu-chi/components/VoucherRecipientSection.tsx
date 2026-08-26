// Khối THÔNG TIN NGƯỜI NHẬN (tiền mặt) hoặc THÔNG TIN CHUYỂN KHOẢN (UNC)
// (tách từ pages/PaymentVoucherDialog.tsx).
import type {
  CompanyBankAccountRow,
  PaymentVoucherBaseInput,
} from "../../../../api/client";

export function VoucherRecipientSection({
  form,
  set,
  loadingAccounts,
  companyAccounts,
  selectCompanyAccount,
}: {
  form: PaymentVoucherBaseInput;
  set: <K extends keyof PaymentVoucherBaseInput>(
    key: K,
    value: PaymentVoucherBaseInput[K],
  ) => void;
  loadingAccounts: boolean;
  companyAccounts: CompanyBankAccountRow[];
  selectCompanyAccount: (value: string) => void;
}) {
  return (
    <>
    {form.voucher_type === "cash" ? (
      <section className="acct-form-section">
        <h3>Thông tin người nhận tiền</h3>
        <div className="acct-form-grid acct-form-grid--3">
          <label className="acct-field">
            <span>
              Người nhận <b>*</b>
            </span>
            <input
              className="input"
              value={form.cash_recipient_name ?? ""}
              onChange={(e) => set("cash_recipient_name", e.target.value)}
            />
          </label>
          <label className="acct-field">
            <span>Địa chỉ</span>
            <input
              className="input"
              value={form.cash_recipient_address ?? ""}
              onChange={(e) =>
                set("cash_recipient_address", e.target.value)
              }
            />
          </label>
          <label className="acct-field">
            <span>CCCD/Giấy tờ</span>
            <input
              className="input"
              value={form.cash_recipient_identity ?? ""}
              onChange={(e) =>
                set("cash_recipient_identity", e.target.value)
              }
            />
          </label>
        </div>
      </section>
    ) : (
      <section className="acct-form-section">
        <h3>Thông tin chuyển khoản</h3>
        {!loadingAccounts && !companyAccounts.length && (
            <div className="banner banner--warn">
              Chưa có tài khoản công ty dùng để chi. Hãy khai báo trong
              mục Tài khoản ngân hàng trước khi lập UNC.
            </div>
          )}
        <div className="acct-form-grid acct-form-grid--3">
          <label className="acct-field">
            <span>
              Tài khoản trích nợ <b>*</b>
            </span>
            <select
              className="input"
              value={form.company_bank_account_id ?? ""}
              onChange={(e) => selectCompanyAccount(e.target.value)}
              disabled={loadingAccounts}
            >
              <option value="">Chọn tài khoản công ty</option>
              {companyAccounts.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.bank_name} · {row.account_number} · {row.currency}
                </option>
              ))}
            </select>
          </label>
          <label className="acct-field">
            <span>
              Tên chủ tài khoản <b>*</b>
            </span>
            <input
              className="input"
              value={form.beneficiary_account_holder ?? ""}
              onChange={(e) =>
                set(
                  "beneficiary_account_holder",
                  e.target.value,
                )
              }
            />
          </label>
          <label className="acct-field">
            <span>
              Số tài khoản thụ hưởng <b>*</b>
            </span>
            <input
              className="input"
              inputMode="numeric"
              value={form.beneficiary_account_number ?? ""}
              onChange={(e) =>
                set("beneficiary_account_number", e.target.value)
              }
            />
          </label>
          <label className="acct-field">
            <span>
              Ngân hàng thụ hưởng <b>*</b>
            </span>
            <input
              className="input"
              value={form.beneficiary_bank_name ?? ""}
              onChange={(e) => set("beneficiary_bank_name", e.target.value)}
            />
          </label>
        </div>
        <div className="acct-form-grid acct-form-grid--3">
          <label className="acct-field">
            <span>Chi nhánh</span>
            <input
              className="input"
              value={form.beneficiary_bank_branch ?? ""}
              onChange={(e) => set("beneficiary_bank_branch", e.target.value)}
            />
          </label>
          <label className="acct-field">
            <span>Bên chịu phí</span>
            <select
              className="input"
              value={form.bank_fee_bearer ?? "payer"}
              onChange={(e) =>
                set(
                  "bank_fee_bearer",
                  e.target.value as "payer" | "beneficiary" | "shared",
                )
              }
            >
              <option value="payer">Công ty trả</option>
              <option value="beneficiary">Người thụ hưởng trả</option>
              <option value="shared">Chia sẻ phí</option>
            </select>
          </label>
        </div>
      </section>
    )}
    </>
  );
}
