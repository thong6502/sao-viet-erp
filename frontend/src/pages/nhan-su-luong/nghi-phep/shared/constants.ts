// Hằng dùng chung của màn Nghỉ phép (tách từ pages/NghiPhepPage.tsx).
/** Cỡ trang chuẩn toàn hệ (prd-dong-bo-ui-thu-mua-nhan-su §2). Dùng chung cho CẢ BỐN tab —
 *  hai tab đầu phân trang ở MÁY CHỦ, hai tab sau (Lịch nghỉ, Loại nghỉ) phân trang Ở CLIENT.
 *
 *  Vì sao hai tab sau cố ý KHÔNG đẩy lên máy chủ:
 *  • Lịch nghỉ — ba thẻ thống kê ở đầu màn (nhân sự nghỉ / đơn chờ / ngày phép P) và bộ chip lọc
 *    đều tính trên TOÀN BỘ danh sách nhân viên của tháng. Phân trang ở máy chủ là ba con số đó
 *    thành "số của trang", sai với cái tên nó đang mang.
 *  • Loại nghỉ — danh mục cỡ 5-15 dòng, mà endpoint `/api/leaves/types` còn nuôi HAI dropdown
 *    (chọn loại nghỉ khi tạo đơn, và ô "trừ vào phép năm" của phiếu Đi muộn/Về sớm bên màn Chấm
 *    công) cùng một chỗ in tên loại nghỉ ở backend. Cắt trang ở máy chủ = hai dropdown đó mất
 *    lựa chọn mà không báo gì. */
export const PAGE_SIZE = 20;

export const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt", approved: "Đã duyệt", rejected: "Từ chối", cancelled: "Đã hủy",
};
