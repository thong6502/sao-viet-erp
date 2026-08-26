// Kiểu dùng chung của màn Tài khoản ngân hàng (tách từ pages/AccountingBankAccountsPage.tsx).
import type {
  CompanyBankAccountInput,
  CompanyBankAccountRow,
  SupplierBankAccountRow,
} from "../../../../api/client";

export type AccountTab = "company" | "supplier";
export type AccountRow = CompanyBankAccountRow | SupplierBankAccountRow;
export type AccountForm = CompanyBankAccountInput;
