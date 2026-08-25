// Hằng số dùng chung của màn Mua hàng (tách từ pages/PurchaseRequestsPage.tsx).
import type {
  DepartmentPurchaseWorkflowStatus,
  PurchaseRequestStatus,
} from "../../../../api/client";

export const PAGE_SIZE = 20;
export const SOURCE_PAGE_SIZE = 20;

export const STATUS_META: Record<
  PurchaseRequestStatus,
  { label: string; tone: string }
> = {
  draft: { label: "Nháp", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  approved: { label: "Đã duyệt", tone: "approved" },
  rejected: { label: "Từ chối", tone: "rejected" },
  purchased: { label: "Đang mua", tone: "purchased" },
  // Bậc SUY RA từ đợt giao: có ≥1 đợt nhưng tổng thực nhận chưa đủ số đặt. Không ai gõ tay được
  // trạng thái này — nó đổi theo đợt giao, và phần hàng đã về đã đẻ ra công nợ.
  partially_received: { label: "Giao một phần", tone: "partial" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

/** Hai trạng thái GHI ĐƯỢC đợt giao — khớp `_TRANG_THAI_GHI_DOT` bên service. */
export const GHI_DOT_DUOC: PurchaseRequestStatus[] = ["purchased", "partially_received"];

export const SOURCE_STATUS_META: Record<
  DepartmentPurchaseWorkflowStatus,
  { label: string; tone: string }
> = {
  open: { label: "Chờ Thu mua xử lý", tone: "draft" },
  drafting: { label: "Thu mua đang lập đơn", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  needs_correction: { label: "Cần Thu mua chỉnh sửa", tone: "rejected" },
  in_purchase: { label: "Đang mua", tone: "pending" },
  done: { label: "Hoàn tất", tone: "received" },
  partially_cancelled: { label: "Hủy một phần", tone: "partial" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

/** Số NCC hiện trong ô chọn của mỗi dòng. Đủ để so giá mà không biến ô chọn thành danh bạ. */
export const SO_NCC_GOI_Y = 5;

export const ATTACHMENT_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
];
