// Kiểu dùng chung của màn Phiếu chi (tách từ pages/PaymentVoucherDialog.tsx).
import type {
  PaymentVoucherRow,
  PurchaseRequestRow,
} from "../../../../api/client";

/** Hai LOẠI phiếu, khác nhau ở ba chỗ: có gắn đợt giao không, trần là số nào, và tiền chi ra khi
 *  hàng đã về hay chưa. Bắt chọn ngay từ đầu thay vì suy từ số tiền — cách cũ (số tiền = trần thì
 *  tự thành "thanh toán cuối") đoán mò, và đoán sai thì backend từ chối sau khi người dùng đã gõ
 *  xong cả form. */
export type LoaiPhieu = "dat_coc" | "thanh_toan";

export interface PaymentVoucherDialogProps {
  purchase: PurchaseRequestRow;
  voucher?: PaymentVoucherRow | null;
  onClose: () => void;
  onSaved: (voucher: PaymentVoucherRow) => void;
}
