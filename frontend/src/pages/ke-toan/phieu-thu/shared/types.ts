// Kiểu dùng chung của màn Phiếu thu (tách từ pages/PaymentReceiptDialog.tsx).
import type {
  PaymentReceiptRow,
  PaymentVoucherRow,
} from "../../../../api/client";

export interface PaymentReceiptDialogProps {
  /** Phiếu chi gốc (đã chi) — nguồn người nộp, currency/tỷ giá và hạn mức còn được thu. */
  voucher: PaymentVoucherRow;
  receipt?: PaymentReceiptRow | null;
  onClose: () => void;
  onSaved: (receipt: PaymentReceiptRow) => void;
}
