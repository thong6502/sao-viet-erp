// Hàm dùng chung của màn Phiếu thu
// (tách từ pages/PaymentReceiptDialog.tsx + pages/PaymentReceiptsPage.tsx).
import type {
  PaymentReceiptInput,
  PaymentReceiptRow,
  PaymentVoucherRow,
} from "../../../../api/client";

export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

export function optional(value?: string | null): string | null {
  const cleaned = (value ?? "").trim();
  return cleaned || null;
}

export function initialForm(
  voucher: PaymentVoucherRow,
  receipt?: PaymentReceiptRow | null,
): PaymentReceiptInput {
  if (receipt) {
    return {
      payer_name: receipt.payer_name,
      payer_address: receipt.payer_address,
      receipt_method: receipt.receipt_method,
      receipt_date: receipt.receipt_date,
      amount: receipt.amount,
      exchange_rate: receipt.exchange_rate,
      content: receipt.content,
      company_bank_account_id: receipt.company_bank_account_id,
      debit_account: receipt.debit_account,
      credit_account: receipt.credit_account,
      note: receipt.note,
    };
  }
  return {
    // Người nộp = người phụ trách mua (người lập PMH); thiếu thì rơi về
    // người nhận tiền mặt trên phiếu chi. KHÔNG dùng tên công ty NCC.
    payer_name:
      voucher.purchase_created_by_name || voucher.cash_recipient_name || "",
    // Mẫu 01-TT có ô Địa chỉ — suy sẵn từ phiếu chi, sửa được.
    payer_address: voucher.cash_recipient_address ?? voucher.supplier_address,
    receipt_method: "cash",
    receipt_date: isoToday(),
    debit_account: null,
    credit_account: null,
    // Để trống bắt kế toán tự gõ số thực nộp (ca phổ biến là thu tiền thừa,
    // không phải thu trọn) — "Còn được thu" hiện ở dải tổng quan để đối chiếu.
    amount: 0,
    exchange_rate: voucher.exchange_rate,
    content: `Thu hồi tiền thừa ${voucher.code}`,
    company_bank_account_id: null,
    note: null,
  };
}

// --- Thêm từ pages/PaymentReceiptsPage.tsx --------------------------------------
// `isoToday` và `optional` ở trên vốn được KHAI HAI LẦN, byte-identical, ở cả
// PaymentReceiptDialog.tsx lẫn PaymentReceiptsPage.tsx — nay dùng chung một bản.

export function methodText(row: PaymentReceiptRow): string {
  return row.receipt_method === "bank_transfer"
    ? "Về TK ngân hàng"
    : "Nhập quỹ tiền mặt";
}

export function sourceLabel(row: PaymentReceiptRow): string {
  if (row.source_type === "order_deposit") return "Cọc đơn bán";
  if (row.source_type === "sales_invoice") return "Thu hóa đơn";
  if (row.source_type === "other") return "Thu khác";
  return "Thu hoàn phiếu chi";
}

export function sourceCode(row: PaymentReceiptRow): string | null {
  if (row.source_type === "order_deposit") return row.order_code;
  if (row.source_type === "sales_invoice") return row.sales_invoice_number;
  if (row.source_type === "purchase_refund") return row.payment_voucher_code;
  return null;
}

export function sourceName(row: PaymentReceiptRow): string {
  if (row.source_type === "order_deposit") return row.customer_name || "Khách hàng";
  if (row.source_type === "sales_invoice") return row.customer_name || "Khách hàng";
  if (row.source_type === "purchase_refund") return row.supplier_name || "Nhà cung cấp";
  return row.payer_name;
}
