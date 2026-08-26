// In PHIẾU CHI / UNC theo mẫu 02-TT (tách từ pages/PaymentVouchersPage.tsx).
import type { PaymentVoucherRow } from "../../../api/client";
import { printTT200 } from "../../../utils/printTT200";
import { SOURCE_LABELS, STAGE_LABELS } from "./shared/list-constants";

/** In Phiếu chi theo mẫu 02-TT. UNC cũng dùng mẫu này (chốt nghiệp vụ), chỉ ghi thêm
 *  dòng thông tin chuyển khoản. */
export function printVoucher(row: PaymentVoucherRow): boolean {
  const isBank = row.voucher_type === "bank_transfer";
  return printTT200({
    kind: "chi",
    docNo: row.doc_no,
    docDate: row.voucher_date,
    debitAccount: row.debit_account,
    creditAccount: row.credit_account,
    personName: isBank ? row.beneficiary_account_holder || row.supplier_name : row.cash_recipient_name,
    personAddress: isBank ? row.supplier_address : row.cash_recipient_address,
    reason: row.content,
    extraLines: [
      { label: "Nguồn chi", value: SOURCE_LABELS[row.source_type] ?? row.source_type },
      { label: "Đợt thanh toán", value: STAGE_LABELS[row.payment_stage] },
      ...(isBank
        ? [
            {
              label: "Hình thức",
              value: `Chuyển khoản — trích TK ${row.company_account_number ?? "—"} tại ${row.company_bank_name ?? "—"} → TK thụ hưởng ${row.beneficiary_account_number ?? "—"} tại ${row.beneficiary_bank_name ?? "—"}`,
            },
          ]
        : []),
      ...(row.invoice_number ? [{ label: "Hóa đơn", value: row.invoice_number }] : []),
      ...(row.bank_reference ? [{ label: "Mã giao dịch", value: row.bank_reference }] : []),
    ],
    amount: row.amount,
    amountVnd: row.amount_vnd,
    currency: row.currency,
    exchangeRate: row.exchange_rate,
    attachmentCount: row.attachment_count,
    cancelled: row.status === "cancelled",
  });
}
