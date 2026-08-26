// Hằng của MÀN DANH SÁCH Phiếu chi (tách từ pages/PaymentVouchersPage.tsx).
// ⚠️ File này CỐ Ý tách khỏi ./constants.ts: cả hai đều có `STAGE_LABELS` nhưng KHÁC KIỂU —
// bản của hộp lập phiếu là `Record<PaymentStage, string>`, bản dưới đây là `as const`.
// Gộp lại là đổi kiểu của một trong hai, nên giữ hai bản đúng như bản gốc.
import type {
  PaymentVoucherSource,
  PaymentVoucherStatus,
  PaymentVoucherType,
} from "../../../../api/client";

export const PAGE_SIZE = 20;

/** Chỉ còn HAI trạng thái từ 06/08/2026 (Đ1): lập phiếu chi = tiền đã ra. Bậc "Chờ chi" và nút
 *  "Xác nhận đã chi" đã bỏ hẳn — bên nghiệp vụ nói thẳng *"tạo phiếu chi là đã chi tiền rồi còn
 *  công nợ cái gì"*. Phiếu ghi nhận nhầm thì HUỶ (bắt lý do), không lùi về chờ. */
export const STATUS_META: Record<
  PaymentVoucherStatus,
  { label: string; tone: string }
> = {
  paid: { label: "Đã chi", tone: "paid" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

export const STAGE_LABELS = {
  advance: "Tạm ứng / đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
} as const;

export const SOURCE_LABELS: Record<PaymentVoucherSource, string> = {
  purchase_request: "Đơn mua hàng",
  // Phiếu chi lập từ màn Tạm ứng (Lương). Mã nguồn in trên chứng từ là MÃ PHIẾU TẠM ỨNG
  // (TU-…/L1-…) nên tra ngược từ sổ quỹ về phiếu đã duyệt bằng ô tìm kiếm là ra.
  salary_advance: "Tạm ứng lương",
  internal_expense: "Khác",
  customer_refund: "Khác",
  other: "Khác",
};

export const VOUCHER_METHOD_LABELS: Record<PaymentVoucherType, string> = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
};
