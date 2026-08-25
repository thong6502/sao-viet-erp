// Hàm dùng chung của màn Tài khoản ngân hàng (tách từ pages/AccountingBankAccountsPage.tsx).
import type { CompanyBankAccountRow } from "../../../../api/client";
import type { AccountForm, AccountRow } from "./types";

export function isCompanyAccount(row: AccountRow): row is CompanyBankAccountRow {
  return "use_for_receipts" in row;
}

export function emptyAccount(): AccountForm {
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
