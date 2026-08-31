// Kiểu dữ liệu riêng của màn Mua hàng (tách từ pages/PurchaseRequestsPage.tsx).
import type {
  DepartmentPurchaseWorkflowStatus,
  HangLoai,
  PurchaseDeliveryRow,
  PurchaseRequestInput,
  PurchaseRequestLineInput,
  PurchaseRequestRow,
  PurchaseRequestStatus,
} from "../../../../api/client";

export type StatusFilter = "all" | PurchaseRequestStatus;
export type SourceStatusFilter = "all" | DepartmentPurchaseWorkflowStatus;
export type DepositFilter = "all" | "none" | "unpaid" | "partial" | "enough";

/** Hai tab con của màn Mua hàng (chốt 08/08/2026).
 *
 * Trước đó hai bảng XẾP DỌC trong cùng một màn: đo thật ở 1440×900 (vùng nhìn 843px) thì dòng đầu
 * của bảng phiếu mua bắt đầu ở y≈812 — người dùng chỉ thấy 34% một dòng, và mỗi yêu cầu mới ở
 * bảng trên lại đẩy bảng dưới xuống thêm 68px (5 yêu cầu chờ là bảng phiếu biến mất hẳn).
 * Tách tab để mỗi bảng có nguyên khung nhìn. ĐỪNG gộp lại thành một trang cuộn dọc. */
export type PurchaseTab = "yeu-cau" | "phieu";

/** Dòng hàng trong FORM — mang thêm NCC của riêng nó.
 *
 * Một phiếu mua là thoả thuận với MỘT nhà cung cấp, nhưng một yêu cầu thường chứa hàng của nhiều
 * nơi. Nên NCC gán ở DÒNG, rồi lúc gửi mới nhóm lại thành N phiếu. Ô "Nhà cung cấp" ở đầu phiếu
 * chỉ còn dùng cho chế độ SỬA (phiếu đã tồn tại thì nó vốn đã thuộc về một NCC). */
export type FormLine = PurchaseRequestLineInput & {
  supplier_id?: number | null;
  /** Dòng YCMH đẻ ra dòng này — gửi lên để chi tiết yêu cầu hiện được tình trạng từng sản phẩm. */
  department_request_line_id?: number | null;
  /** Liên kết mặt hàng gốc (mg 0174) — form SỬA phải đọc lại từ phiếu, không thì lưu đè thành rỗng. */
  hang_loai?: HangLoai | null;
  hang_id?: number | null;
};

export type FormState = Omit<PurchaseRequestInput, "lines"> & { lines: FormLine[] };

export type ChaoGia = {
  supplier_id: number;
  supplier_name: string;
  unit_price: number;
  vat_percent: number;
  unit: string;
};

/** Một file hoá đơn ĐANG CHỜ tải lên. `url` là `blob:` để xem trước — rỗng với PDF (thẻ `<img>`
 *  không dựng được PDF, ô đó hiện icon thay vì ảnh) nên đừng cấp URL để rồi không dùng. */
export type AnhCho = { file: File; url: string };

/** Bảng xem trước "sẽ tạo mấy phiếu" — gom dòng theo NCC (memo `phieuSeTao` ở shell). */
export type PhieuSeTao = { ten: string; soDong: number; tien: number };

// --- Kiểu của các hộp thoại mở từ shell -------------------------------------
// Shell vẫn khai `useState<null | {...}>` bằng kiểu viết thẳng (giữ nguyên chú thích tại chỗ);
// mấy tên dưới đây là CÙNG hình dạng đó, để component con khai prop mà khỏi chép lại cả khối.

export type ReasonModalState = {
  kind: "cancel";
  row: PurchaseRequestRow;
  reason: string;
  error: string | null;
};

export type ReceiveModalState = {
  row: PurchaseRequestRow;
  mode: "receive" | "edit";
};

export type DeliveryModalState = {
  row: PurchaseRequestRow;
  delivery: PurchaseDeliveryRow | null;
};

export type DeletingDeliveryState = {
  row: PurchaseRequestRow;
  delivery: PurchaseDeliveryRow;
};

export type CloseModalState = {
  row: PurchaseRequestRow;
  reason: string;
  error: string | null;
};
