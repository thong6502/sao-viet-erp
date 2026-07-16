/** Tạm ẩn UNC (Ủy nhiệm chi) + TK ngân hàng NHÀ CUNG CẤP — 2026-07 (yêu cầu SVN).
 *  Bật lại: đổi thành true, không cần sửa gì khác.
 *
 *  CHỈ ẩn phần TẠO MỚI. Phiếu UNC cũ vẫn hiện đúng "UNC" ở cột Loại, vẫn sửa được,
 *  panel vẫn còn khối TK trích nợ/thụ hưởng và bản in vẫn có dòng chuyển khoản —
 *  ẩn cả nhánh hiển thị thì UNC cũ rơi về nhánh tiền mặt và IN RA SAI CHỨNG TỪ.
 *
 *  Không liên quan Phiếu thu: `receipt_method = bank_transfer` của phiếu thu dùng
 *  TK ngân hàng CÔNG TY, nên tab "Tài khoản công ty" phải giữ nguyên.
 */
export const UNC_ENABLED = false;

/** Tên màn Phiếu chi — dùng ở menu, tiêu đề màn và chỗ trỏ chéo từ Phiếu thu.
 *  Gom một chỗ để bật lại UNC là đổi đúng `UNC_ENABLED`, không phải đi sửa nhãn. */
export const VOUCHER_PAGE_LABEL = UNC_ENABLED ? "Phiếu chi / UNC" : "Phiếu chi";
