// Hằng dùng chung của màn Tăng ca (tách từ pages/TangCaPage.tsx).
/** Cỡ trang chuẩn toàn hệ (prd-dong-bo-ui-thu-mua-nhan-su §2). */
export const PAGE_SIZE = 20;

/** Cỡ mẻ nạp danh sách thợ cho dropdown "Tạo hộ thợ".
 *
 *  200 = TRẦN `size` của `GET /api/employees` (`routers/employees.py`). Trước 09/08/2026 chỗ này
 *  gọi `api.employees.list(token, {})` không truyền gì, mà endpoint đó mặc định `size=20` ⇒ ô
 *  chọn thợ chỉ có 20 người đầu, tổ trưởng không tìm thấy thợ của mình mà cũng không biết vì sao. */
export const EMPLOYEE_PICKER_SIZE = 200;

export const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  cancelled: "Đã hủy",
};

/** Còn ≥ 8h thì thoải mái, dưới 8h là sắp hết, 0 là hết sạch. 8h = đúng một ca. */
export const TRAN_NGUONG_VANG = 480;
