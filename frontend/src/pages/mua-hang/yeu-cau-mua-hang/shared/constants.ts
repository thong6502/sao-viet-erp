// Hằng số dùng chung của màn Yêu cầu mua hàng (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
import type {
  DepartmentPurchaseSourceType,
  DepartmentPurchaseWorkflowStatus,
  PurchaseRequestStatus,
} from "../../../../api/client";

/** Số dòng mỗi trang. TRƯỚC 08/08/2026 màn này tải cứng 100 dòng và KHÔNG có phân trang: quá 100
 *  yêu cầu là bảng cắt im lặng trong khi ô "Tổng" vẫn hiện đúng — người dùng không có cách nào
 *  biết mình đang thiếu gì. */
export const PAGE_SIZE = 20;

export const SOURCE_TYPE_LABELS: Record<DepartmentPurchaseSourceType, string> = {
  kinh_doanh: "Kinh doanh",
  kho: "Kho",
  san_xuat: "Sản xuất",
  cong_nghe: "Công nghệ",
  gia_cong_ngoai: "Gia công ngoài",
  khac: "Khác",
};

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
  // Tông HỔ PHÁCH, không phải tông "đã hủy" (đỏ/xám): yêu cầu VẪN CÒN SỐNG, chỉ rụng vài món.
  // Dùng chung tông với "Đã hủy" là người đọc lướt tưởng cả phiếu chết, thôi không xử lý nữa.
  partially_cancelled: { label: "Hủy một phần", tone: "partial" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

/** Nhãn trạng thái của một PHIẾU MUA. Dùng chung cho ô tình trạng dòng và danh sách phiếu. */
export const PHIEU_STATUS_META: Record<PurchaseRequestStatus, { label: string; tone: string }> = {
  draft: { label: "Nháp", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  approved: { label: "Đã duyệt", tone: "approved" },
  rejected: { label: "Bị từ chối", tone: "rejected" },
  purchased: { label: "Đã mua", tone: "purchased" },
  partially_received: { label: "Giao một phần", tone: "partial" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};
