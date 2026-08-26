// Hằng dùng chung của màn Phiếu chi (tách từ pages/PaymentVoucherDialog.tsx).
import type { PaymentStage } from "../../../../api/client";

/** Hôm nay dạng `yyyy-mm-dd` — trần cho ngày chứng từ và ngày hoá đơn (không cho chọn tương lai). */
export const HOM_NAY = new Date().toISOString().slice(0, 10);

export const STAGE_LABELS: Record<PaymentStage, string> = {
  advance: "Tạm ứng / đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
};
