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

/** Tạm ẨN màn Bài ghép — 10/09/2026 (yêu cầu SVN).
 *  Bật lại: đổi thành true, không cần sửa gì khác.
 *
 *  CHỈ ẩn ĐƯỜNG VÀO ở giao diện: mục menu "Bài ghép", badge hàng chờ ghép, ô quyền `bai_ghep_2`
 *  trong ma trận Vai trò & Quyền, và nút trỏ chéo từ màn Xếp lịch. Dữ liệu · API
 *  `/api/bai-ghep-2` · dòng `role_permissions` đã cấp GIỮ NGUYÊN — bài ghép cũ vẫn là nguồn của
 *  engine xếp lịch, vẫn hiện thành thanh trên Gantt y như trước.
 *
 *  Ẩn menu là khoá luôn route: `MODULES_BY_NAV_ID` dựng từ `NAV` của Sidebar, mất mục thì
 *  AppShell coi `bai-ghep-2` là màn không có quyền. Vì vậy phải ẩn cả nút trỏ chéo ở Xếp lịch,
 *  không thì bấm vào ăn màn chặn.
 */
export const BAI_GHEP_ENABLED = false;

/** Tạm ẨN màn Xếp lịch công đoạn 2 — 10/09/2026 (yêu cầu SVN), thay bằng "Xếp lịch 3".
 *  Bật lại: đổi thành true, không cần sửa gì khác.
 *
 *  Màn 3 xếp ở cấp LỆNH SẢN XUẤT: người dùng đặt MỘT giờ bắt đầu cho cả lệnh, hệ tự cộng giờ
 *  chạy từng bước + nghỉ giữa ca + ngoài ca ra ngày kết thúc. Màn 2 xếp từng công đoạn — cùng một
 *  việc nhưng bắt gán tay từng bước, nên hai màn mở cùng lúc chỉ làm người dùng phân vân.
 *
 *  CHỈ ẩn ĐƯỜNG VÀO ở giao diện. Bảng `xep_lich_cong_doan` · API `/api/xep-lich-2` · quyền
 *  `xep_lich_2` GIỮ NGUYÊN: lệnh đang xếp dở ở màn 2 vẫn chạy, và bốn chỗ tiêu thụ lịch (giữ chỗ
 *  vật tư · bảng cân đối · cột Trạng thái màn Máy · thẻ việc bàn tổ) vẫn đọc được cả hai nguồn.
 *
 *  Ẩn menu là khoá luôn route (`MODULES_BY_NAV_ID` dựng từ `NAV`) — nên phải ẩn cả nút trỏ chéo
 *  tới màn 2, không thì bấm vào ăn màn chặn.
 */
export const XEP_LICH_2_ENABLED = false;
