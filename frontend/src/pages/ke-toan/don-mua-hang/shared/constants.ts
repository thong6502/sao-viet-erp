// Hằng dùng chung của màn Đơn mua hàng (Kế toán) — tách từ pages/AccountingPurchaseInboxPage.tsx.
import type {
  PaymentVoucherRow,
  PurchaseRequestStatus,
} from "../../../../api/client";

export const PAGE_SIZE = 20;

export const STATUS_META: Record<
  PurchaseRequestStatus,
  { label: string; tone: string }
> = {
  draft: { label: "Nháp", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  approved: { label: "Đã duyệt", tone: "approved" },
  rejected: { label: "Từ chối", tone: "rejected" },
  purchased: { label: "Đang mua", tone: "purchased" },
  partially_received: { label: "Giao một phần", tone: "partial" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

export const PAYMENT_META = {
  unpaid: { label: "Chưa thanh toán", tone: "unpaid" },
  partial: { label: "Thanh toán một phần", tone: "partial" },
  paid: { label: "Đã thanh toán", tone: "paid" },
} as const;

export const VOUCHER_TYPE_LABEL: Record<PaymentVoucherRow["voucher_type"], string> = {
  cash: "Phiếu chi",
  bank_transfer: "UNC",
};

export const PAYMENT_STAGE_LABEL: Record<PaymentVoucherRow["payment_stage"], string> = {
  advance: "Đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
};

export const VOUCHER_STATUS_LABEL: Record<PaymentVoucherRow["status"], string> = {
  paid: "Đã chi",
  cancelled: "Đã hủy",
};
