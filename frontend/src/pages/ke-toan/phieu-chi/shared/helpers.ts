// Hàm dùng chung của màn Phiếu chi (tách từ pages/PaymentVoucherDialog.tsx).
import type {
  PaymentVoucherBaseInput,
  PaymentVoucherRow,
  PurchaseRequestRow,
} from "../../../../api/client";

export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

export function optional(value?: string | null): string | null {
  const cleaned = (value ?? "").trim();
  return cleaned || null;
}

/** Đợt giao CÒN NỢ đầu tiên — gợi ý mặc định khi lập phiếu thanh toán.
 *
 *  Dùng `con_no` (đã trừ cả tiền trả đích danh lẫn cọc bù) chứ không tự trừ tay: đợt được cọc phủ
 *  hết thì không còn gì để trả, chọn sẵn nó là mời người dùng gõ một số rồi ăn lỗi. */
export function dotGoiY(purchase: PurchaseRequestRow): number | null {
  const con_no = purchase.deliveries.filter((d) => d.con_no > 0);
  const nguon = con_no.length ? con_no : purchase.deliveries;
  return nguon[0]?.id ?? null;
}

/** Còn nợ của một đợt — cũng chính là TRẦN lập phiếu chi thanh toán cho đợt đó. */
export function conNoDot(purchase: PurchaseRequestRow, deliveryId: number | null): number {
  if (deliveryId == null) return purchase.outstanding_amount;
  return purchase.deliveries.find((d) => d.id === deliveryId)?.con_no ?? 0;
}

/** Số tiền điền sẵn cho phiếu ĐẶT CỌC.
 *
 * Ưu tiên **cọc dự kiến** thu mua đã khai trên phiếu mua — đó là con số đã thoả thuận với NCC và
 * đã qua duyệt, kế toán không phải đi hỏi lại.
 *
 * Chưa khai (bằng 0) thì lấy **nửa giá trị đơn** (chủ chốt 06/08/2026) — mức cọc thông thường, để
 * kế toán có sẵn một số hợp lý mà sửa, thay vì đối diện ô trống hoặc bị điền nguyên giá trị đơn
 * (điền nguyên đơn là mời người ta bấm Lưu và ứng trước 100%).
 *
 * Luôn kẹp trong trần đặt cọc — gợi ý mà vượt trần thì bấm Lưu là ăn lỗi ngay. */
/** Nội dung đơn để nhét vào nội dung phiếu chi. Phiếu CŨ chưa có ô gộp ⇒ lấy `purpose`. */
export function moTaDon(purchase: PurchaseRequestRow): string {
  return (purchase.content ?? purchase.purpose ?? "").trim();
}

export function cocGoiY(purchase: PurchaseRequestRow): number {
  const mong_muon =
    purchase.deposit_expected > 0
      ? purchase.deposit_expected
      : Math.round(purchase.total_estimate / 2);
  return Math.min(mong_muon, purchase.tran_dat_coc);
}

export function initialForm(
  purchase: PurchaseRequestRow,
  voucher?: PaymentVoucherRow | null,
): PaymentVoucherBaseInput {
  if (voucher) {
    return {
      voucher_type: voucher.voucher_type,
      payment_stage: voucher.payment_stage,
      delivery_id: voucher.delivery_id,
      voucher_date: voucher.voucher_date,
      planned_payment_date: voucher.planned_payment_date,
      amount: voucher.amount,
      currency: voucher.currency,
      exchange_rate: voucher.exchange_rate,
      content: voucher.content,
      invoice_number: voucher.invoice_number,
      invoice_date: voucher.invoice_date,
      contract_number: voucher.contract_number,
      company_bank_account_id: voucher.company_bank_account_id,
      supplier_bank_account_id: voucher.supplier_bank_account_id,
      beneficiary_account_holder: voucher.beneficiary_account_holder,
      beneficiary_account_number: voucher.beneficiary_account_number,
      beneficiary_bank_name: voucher.beneficiary_bank_name,
      beneficiary_bank_branch: voucher.beneficiary_bank_branch,
      cash_recipient_name: voucher.cash_recipient_name,
      cash_recipient_address: voucher.cash_recipient_address,
      cash_recipient_identity: voucher.cash_recipient_identity,
      bank_fee_bearer: voucher.bank_fee_bearer ?? "payer",
      debit_account: voucher.debit_account,
      credit_account: voucher.credit_account,
      note: voucher.note,
    };
  }
  // Chưa có đợt giao nào ⇒ hàng chưa về ⇒ đây chỉ có thể là tiền ĐẶT CỌC. Có đợt rồi thì mặc định
  // là THANH TOÁN, gắn sẵn đợt còn nợ và điền sẵn số công nợ.
  const chuaCoDot = purchase.deliveries.length === 0;
  return {
    voucher_type: "cash",
    payment_stage: chuaCoDot ? "advance" : "final",
    delivery_id: chuaCoDot ? null : dotGoiY(purchase),
    voucher_date: isoToday(),
    // DORMANT: hạn trả đã chuyển lên đợt giao, phiếu chi không còn hạn.
    planned_payment_date: null,
    amount: chuaCoDot
      ? cocGoiY(purchase)
      : conNoDot(purchase, dotGoiY(purchase)),
    currency: "VND",
    exchange_rate: 1,
    content: `Thanh toán ${purchase.code}${
      moTaDon(purchase) ? ` - ${moTaDon(purchase)}` : ""
    }`.slice(0, 500),
    invoice_number: null,
    invoice_date: null,
    contract_number: null,
    company_bank_account_id: null,
    supplier_bank_account_id: null,
    beneficiary_account_holder: purchase.supplier_name ?? "",
    beneficiary_account_number: null,
    beneficiary_bank_name: null,
    beneficiary_bank_branch: null,
    cash_recipient_name: purchase.supplier_name ?? "",
    cash_recipient_address: null,
    cash_recipient_identity: null,
    bank_fee_bearer: "payer",
    debit_account: null,
    credit_account: null,
    note: null,
  };
}
