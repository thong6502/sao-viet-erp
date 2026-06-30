# Product Backlog — Sao Việt Nhật ERP

Backlog sản phẩm phân rã theo Epic → PBI. Mỗi PBI có User Story + tiêu chí nghiệm thu +
mô tả việc cần làm, ánh xạ sang issue trên Jira.

> Cập nhật: 2026-06-30. Nguồn đối chiếu hiện trạng code: `feature_list.json`, `progress.md`.
> Bảng PBI bám đúng board Jira — thêm/bớt PBI thì cập nhật cả hai cho khớp.

## Quy ước

- **Mã PBI**: `PBI-<số epic><thứ tự 3 chữ số>` — EPIC-01 → `PBI-10xx`, EPIC-02 → `PBI-20xx`…
- **Jira**: mã issue (vd `SVN-16`) kèm trạng thái trên board:
  - ✅ Done · 🔵 Đang làm · ⬜ Chưa làm
- **Type**: *Tính năng* (việc người dùng thấy) · *Kỹ thuật* (hạ tầng/quy tắc nền).
- **Note**: hiện trạng so với **code** (Đã có / Một phần / Cần sửa / Mới). **Có thể lệch với
  trạng thái Jira** — ví dụ `PBI-1006` code đã có (feat-012) nhưng Jira còn để *Chưa làm*.
- **Actor**: QTV = Quản trị viên hệ thống · HCNS = Hành chính nhân sự · Trưởng phòng ·
  Giám đốc · Người dùng · Hệ thống.
- **Quyết định nền**: đăng nhập bằng **tên đăng nhập** (không dùng email, không hồ sơ email);
  khôi phục mật khẩu **chỉ qua quản trị viên đặt lại**; không có cờ "buộc đổi mật khẩu".

## Danh mục Epic

| Mã | Jira | Tên epic | Phân hệ | Số PBI | Mức chi tiết |
|---|---|---|---|---|---|
| EPIC-01 | SVN-14 | Xác thực & Phân quyền | (nền tảng) | 10 | ✅ đã chi tiết |
| EPIC-02 | SVN-1 | Quản lý người dùng | Admin | 8 | ✅ đã chi tiết |
| EPIC-03 | — | Quản lý tham số hệ thống | Admin | — | ⬜ chưa |
| EPIC-04 | — | Quản lý phòng ban | Admin | — | ⬜ chưa (có nháp) |
| EPIC-05 | — | Quản lý vai trò (nhóm quyền) | Admin | — | ⬜ chưa (có nháp) |
| EPIC-06 | — | Nhật ký hệ thống (audit log) | Admin | — | ⬜ chưa (có nháp) |
| EPIC-07 | — | Dashboard điều hành | Admin | — | ⬜ chưa (có nháp) |
| EPIC-08 | — | Quản lý danh mục sản phẩm | Kinh doanh | — | ⬜ chưa |
| EPIC-09 | — | Quản lý danh mục khách hàng | Kinh doanh | — | ⬜ chưa |
| EPIC-10 | — | Quản lý danh mục tính giá bán | Kinh doanh | — | ⬜ chưa |
| EPIC-11 | — | Quản lý danh mục chiết khấu | Kinh doanh | — | ⬜ chưa |
| EPIC-12 | — | Quản lý báo giá | Kinh doanh | — | ⬜ chưa |
| EPIC-13 | — | Quản lý đơn hàng bán | Kinh doanh | — | ⬜ chưa |
| EPIC-14 | — | Dashboard & Thống kê kinh doanh | Kinh doanh | — | ⬜ chưa |
| EPIC-15 | — | Thông báo kinh doanh | Kinh doanh | — | ⬜ chưa |

---

## EPIC-01 · Xác thực & Phân quyền *(SVN-14)*

Tầng xác thực + kiểm soát quyền — gói trọn hai spec đã hoàn thành (đăng nhập + siết bảo mật)
cùng phần cốt lõi của RBAC. Phần lớn đã có; chỉ `PBI-1001` cần sửa (đổi sang tên đăng nhập)
và `PBI-1010` là mới.

| PBI ID | Jira | Type | Actor | Tên tính năng | User Story | Acceptance Criteria | Mô tả Task | Phụ thuộc | Note |
|---|---|---|---|---|---|---|---|---|---|
| PBI-1001 | SVN-16 🔵 | Tính năng | Người dùng | Đăng nhập bằng tài khoản nội bộ | Là người dùng, tôi muốn đăng nhập bằng tên đăng nhập và mật khẩu để truy cập hệ thống | 1) nhập tên đăng nhập + mật khẩu, có kiểm tra hợp lệ, trạng thái đang xử lý và báo lỗi; 2) sai thì báo chung "Tên đăng nhập hoặc mật khẩu không đúng", không tiết lộ tài khoản có tồn tại hay không; 3) đúng thì vào màn chính; 4) mật khẩu lưu dạng băm; 5) bỏ trống thì không gửi yêu cầu | Thêm cột tên đăng nhập (duy nhất) vào hồ sơ người dùng; dựng màn đăng nhập; kiểm tra tên đăng nhập + mật khẩu; cấp phiên truy cập; xử lý thông báo lỗi sai | — | **Cần sửa** — hiện đăng nhập bằng email (feat-002/003) |
| PBI-1002 | SVN-15 ✅ | Tính năng | Người dùng | Đăng xuất | Là người dùng, tôi muốn đăng xuất để bảo vệ tài khoản khi không dùng nữa | 1) thu hồi phiên làm mới phía máy chủ và xóa cookie; 2) quay về màn đăng nhập; 3) tải lại vẫn ở màn đăng nhập; 4) gọi đăng xuất khi không còn phiên vẫn an toàn | Nút đăng xuất; gọi máy chủ thu hồi phiên làm mới; xóa cookie; điều hướng về màn đăng nhập | PBI-1001 | **Đã có** (feat-015/016) |
| PBI-1003 | SVN-17 ✅ | Tính năng | Người dùng | Duy trì phiên: khôi phục khi tải lại + tự gia hạn ngầm | Là người dùng, tôi muốn tải lại trang và làm việc liên tục mà không bị văng ra đăng nhập lại | 1) mở/tải lại tự khôi phục phiên; 2) phiên hết hạn thì tự gia hạn ngầm rồi làm tiếp thao tác đang dở; 3) nhiều yêu cầu hết hạn cùng lúc chỉ gia hạn một lần; 4) gia hạn thất bại thì báo "Phiên đã hết hạn, đăng nhập lại" | Lúc mở app gọi khôi phục phiên từ cookie; bắt lỗi hết hạn rồi gia hạn ngầm và thử lại thao tác; gộp nhiều yêu cầu vào một lần gia hạn; thông báo khi gia hạn hỏng | PBI-1001 | **Đã có** (feat-016) |
| PBI-1004 | SVN-18 ✅ | Kỹ thuật | QTV | Phiên truy cập ngắn hạn + thu hồi tức thì | Là quản trị viên, tôi muốn vô hiệu một phiên đăng nhập ngay lập tức để xử lý rủi ro bảo mật | 1) phiên truy cập thời hạn ngắn (mặc định 15 phút); 2) khi thu hồi, mọi phiên truy cập cũ của người dùng đó bị từ chối ngay dù chưa hết hạn; 3) tài khoản bị khóa cũng bị từ chối | Đặt thời hạn phiên truy cập ngắn; thêm số phiên bản phiên vào hồ sơ người dùng; kiểm tra số phiên bản ở mỗi yêu cầu; chức năng nâng số phiên bản để thu hồi | PBI-1001 | **Đã có** (feat-013) |
| PBI-1005 | SVN-19 ✅ | Kỹ thuật | Hệ thống | Xoay vòng phiên làm mới + phát hiện đánh cắp | Là hệ thống, tôi cần xoay vòng phiên làm mới và phát hiện tái sử dụng để chống đánh cắp phiên | 1) mỗi lần gia hạn cấp phiên mới và thu hồi phiên cũ; 2) phiên làm mới chỉ lưu dạng băm; 3) dùng lại phiên đã thu hồi thì khóa cả nhóm phiên; 4) phiên hết hạn bị từ chối | Bảng lưu phiên làm mới (chỉ lưu bản băm); cấp mới + thu hồi cũ mỗi lần gia hạn; nhận diện dùng lại phiên đã thu hồi rồi khóa cả nhóm; dọn phiên hết hạn | PBI-1003 | **Đã có** (feat-014) |
| PBI-1006 | SVN-20 ⬜ | Kỹ thuật | QTV | Bắt buộc khóa bảo mật mạnh trước khi chạy thật | Là quản trị viên, tôi muốn hệ thống không cho chạy bản thật khi khóa bảo mật còn yếu, để không ai giả được vé đăng nhập | 1) khi chạy bản thật, nếu khóa bảo mật trống, để mẫu, hoặc quá ngắn (dưới 32 ký tự) thì dừng khởi động và báo rõ "cần đặt khóa bảo mật mạnh"; 2) khi chạy ở máy thử nghiệm thì vẫn chạy bình thường | Hàm kiểm tra khóa bảo mật lúc khởi động; chặn chạy bản thật nếu khóa trống/mẫu/ngắn; hiện thông báo hướng dẫn đặt khóa mạnh | — | **Đã có** (feat-012) |
| PBI-1007 | SVN-21 ✅ | Kỹ thuật | Hệ thống | Kiểm tra quyền theo vai trò | Là hệ thống, tôi cần kiểm tra quyền theo vai trò trước mỗi thao tác để chặn truy cập trái phép | 1) chưa đăng nhập thì bị từ chối; 2) thiếu quyền thì báo không đủ quyền; 3) tài khoản bị khóa bị từ chối dù còn phiên hợp lệ; 4) dùng lại được cho mọi module | Lớp kiểm tra quyền dùng chung gắn vào từng API; tra quyền của vai trò theo module + hành động; trả lỗi chưa đăng nhập / không đủ quyền / tài khoản khóa | PBI-1001 | **Đã có** (feat-005) |
| PBI-1008 | SVN-24 ✅ | Kỹ thuật | Hệ thống | Giới hạn phạm vi dữ liệu | Là hệ thống, tôi cần giới hạn dữ liệu người dùng thấy theo phạm vi của vai trò | 1) "của tôi" chỉ thấy bản ghi mình phụ trách; 2) "cả phòng" thấy bản ghi cùng phòng ban; 3) "tất cả" không giới hạn; 4) là bộ lọc thuần, dùng lại được cho module sau | Bộ lọc dữ liệu theo phạm vi của vai trò; áp lên truy vấn lấy dữ liệu; viết dạng tái sử dụng cho các module nghiệp vụ sau | PBI-1007 | **Đã có** (feat-006) |
| PBI-1009 | SVN-22 ✅ | Tính năng | Người dùng | Ẩn menu / màn theo quyền | Là người dùng, tôi chỉ muốn thấy mục mình được phép để giao diện gọn và không vào nhầm chỗ cấm | 1) thanh điều hướng chỉ hiện module vai trò được Xem, mục/nhóm rỗng tự ẩn; 2) mở màn không có quyền thì hiện "không có quyền" và đưa về nơi hợp lệ, không để trắng màn | API trả danh sách module được Xem; lọc thanh điều hướng theo quyền + ẩn nhóm rỗng; chặn màn cấm bằng thông báo "không có quyền" và điều hướng về nơi hợp lệ | PBI-1007 | **Đã có** (feat-010) |
| PBI-1010 | SVN-23 ⬜ | Tính năng | Người dùng | Đổi mật khẩu (tự phục vụ) | Là người dùng, tôi muốn tự đổi mật khẩu để giữ an toàn tài khoản | 1) nhập mật khẩu hiện tại + mật khẩu mới, kiểm tra độ mạnh tối thiểu; 2) sai mật khẩu hiện tại thì bị từ chối; 3) đổi xong vô hiệu các phiên cũ; 4) ghi nhật ký | Màn đổi mật khẩu; kiểm tra độ mạnh; cập nhật bản băm; thu hồi phiên cũ; ghi nhật ký | PBI-1001 | **Mới** |

---

## EPIC-02 · Quản lý người dùng *(SVN-1)*

Màn quản trị người dùng: tạo/sửa/khóa tài khoản, gán vai trò, đặt lại mật khẩu, thu hồi phiên.
Đăng nhập bằng tên đăng nhập (không email). 8 PBI — `2001–2007` đã có trên board
(`SVN-25`…`SVN-31`), `2008` chưa tạo issue.

| PBI ID | Jira | Type | Actor | Tên tính năng | User Story | Acceptance Criteria | Mô tả Task | Phụ thuộc | Note |
|---|---|---|---|---|---|---|---|---|---|
| PBI-2001 | SVN-25 ⬜ | Tính năng | QTV / HCNS | Danh sách + tìm kiếm + lọc người dùng | Là HCNS, tôi muốn xem và lọc danh sách người dùng để nhanh tìm đúng tài khoản cần thao tác | 1) bảng hiển thị họ tên, tên đăng nhập, phòng ban, vai trò, trạng thái (Hoạt động/Đã khóa); 2) tìm theo họ tên hoặc tên đăng nhập; 3) lọc theo phòng ban và trạng thái; 4) có phân trang; 5) đủ trạng thái rỗng, đang tải, báo lỗi; 6) người không có quyền Xem người dùng bị từ chối | Màn danh sách + ô tìm kiếm + bộ lọc phòng ban/trạng thái + phân trang; gọi API danh sách; gắn kiểm tra quyền Xem người dùng | EPIC-01, EPIC-04, EPIC-05 | **Một phần** (feat-009). Thiếu tìm kiếm/lọc/phân trang; cột email → tên đăng nhập |
| PBI-2002 | SVN-26 ⬜ | Tính năng | HCNS | Tạo người dùng mới | Là HCNS, tôi muốn tạo tài khoản nhân viên mới để họ đăng nhập được vào hệ thống | 1) bắt buộc họ tên, tên đăng nhập, phòng ban; 2) tên đăng nhập không trùng (trùng thì báo lỗi ngay tại ô nhập); 3) người dùng mới nhận vai trò tối thiểu mặc định; 4) đặt mật khẩu khởi tạo; 5) nhấn gửi nhiều lần không tạo trùng; 6) ghi nhật ký | Form tạo (họ tên, tên đăng nhập, phòng ban); kiểm tra trùng tên đăng nhập; đặt mật khẩu khởi tạo; gán vai trò tối thiểu; chống gửi trùng; ghi nhật ký | EPIC-04 | **Cần sửa** — đã có (feat-009) nhưng theo email |
| PBI-2003 | SVN-27 ⬜ | Tính năng | HCNS / QTV | Sửa thông tin người dùng | Là HCNS, tôi muốn cập nhật họ tên, phòng ban của người dùng để giữ dữ liệu chính xác | 1) sửa được họ tên và phòng ban; tên đăng nhập khóa, không cho đổi; 2) đổi phòng ban thì vai trò cũ thuộc phòng khác bị gỡ và có cảnh báo; 3) ghi nhật ký | Form sửa họ tên + phòng ban (khóa tên đăng nhập); đổi phòng ban thì gỡ vai trò cũ + cảnh báo; ghi nhật ký | PBI-2002 | **Mới** |
| PBI-2004 | SVN-28 ⬜ | Tính năng | Trưởng phòng | Gán / đổi vai trò cho người dùng | Là trưởng phòng, tôi muốn gán vai trò cho nhân viên trong phòng để họ có đúng quyền hạn | 1) danh sách chọn chỉ hiện vai trò đúng phòng ban của người dùng; 2) mỗi người dùng đúng một vai trò; 3) lưu xong cập nhật ngay; 4) ghi nhật ký; 5) người không đủ quyền bị từ chối | Danh sách chọn vai trò lọc theo phòng ban của người dùng; lưu vai trò; gắn kiểm tra quyền; ghi nhật ký | EPIC-05, PBI-2002 | **Đã có** (feat-009) |
| PBI-2005 | SVN-29 ⬜ | Tính năng | HCNS / QTV | Khóa / mở khóa tài khoản | Là HCNS, tôi muốn khóa tài khoản nhân viên đã nghỉ để chặn truy cập ngay lập tức | 1) khi khóa, đăng nhập và lấy thông tin tài khoản bị từ chối tức thì; 2) tài khoản đang giữ phiên hợp lệ vẫn bị chặn; 3) không cho tự khóa chính mình; 4) mở khóa khôi phục truy cập; 5) ghi nhật ký | Nút khóa/mở khóa; chặn tự khóa mình; khi khóa thì chặn đăng nhập + thu hồi phiên; ghi nhật ký | EPIC-01 | **Đã có** (feat-009) |
| PBI-2006 | SVN-30 ⬜ | Tính năng | QTV / HCNS | Đặt lại mật khẩu người dùng | Là HCNS, tôi muốn đặt lại mật khẩu cho người dùng quên mật khẩu để họ truy cập lại được | 1) admin bấm đặt lại → sinh mật khẩu tạm, hiển thị một lần để bàn giao; 2) thu hồi mọi phiên cũ của người dùng; 3) ghi nhật ký | Nút đặt lại; sinh mật khẩu tạm + hiển thị một lần; cập nhật bản băm; thu hồi mọi phiên cũ; ghi nhật ký | EPIC-01 | **Mới**. Tái dùng thu hồi phiên (feat-013/014) |
| PBI-2007 | SVN-31 ⬜ | Kỹ thuật | QTV | Buộc đăng xuất / thu hồi mọi phiên | Là quản trị viên, tôi muốn buộc một người dùng đăng xuất khỏi mọi thiết bị để xử lý sự cố bảo mật | 1) thu hồi toàn bộ phiên làm mới và vô hiệu phiên truy cập của người dùng; 2) người dùng phải đăng nhập lại; 3) ghi nhật ký | Nút thu hồi phiên; gọi thu hồi toàn bộ phiên làm mới + nâng số phiên bản phiên; ghi nhật ký | EPIC-01 | **Hạ tầng đã có** (feat-013/014); thiếu giao diện + đường gọi |
| PBI-2008 | — ⬜ | Tính năng | QTV / HCNS | Xem chi tiết người dùng | Là HCNS, tôi muốn xem toàn bộ thông tin của một người dùng ở một chỗ để nắm nhanh và thao tác đúng | 1) mở từ danh sách hiện hồ sơ đầy đủ: họ tên, tên đăng nhập, phòng ban, vai trò, trạng thái; 2) hiện các phiên đang hoạt động (thiết bị, thời gian) ở dạng chỉ xem và hoạt động gần đây của người này; 3) có nút thao tác theo đúng quyền: gán vai trò, khóa/mở khóa, đặt lại mật khẩu, thu hồi mọi phiên; 4) đủ trạng thái đang tải và báo lỗi; 5) người không có quyền Xem người dùng bị từ chối | Panel/trang chi tiết gộp thông tin + vai trò + danh sách phiên đang hoạt động (chỉ xem) + hoạt động gần đây; gọi API hồ sơ, API phiên, API nhật ký theo người; gắn các nút thao tác kèm kiểm tra quyền | PBI-2001, EPIC-01, EPIC-06 | **Mới**. Gộp dữ liệu sẵn có (hồ sơ + phiên làm mới feat-014 + nhật ký feat-011) |

---

## Còn lại

- **Ý tưởng đã bàn cho EPIC-02 nhưng chưa tạo issue** (để dành, thêm vào board khi cần): Nhập/xuất
  danh sách người dùng · Hồ sơ cá nhân (tự xem/sửa của mình).
- **Gợi ý quy tắc an toàn cho người dùng** (đã nêu, chưa chọn đưa vào board): bảo vệ quản trị viên
  hoạt động cuối cùng · chống dò mật khẩu (tạm khóa sau nhiều lần sai) · ràng buộc khi khóa trưởng
  phòng / người đang phụ trách dữ liệu.
- **EPIC-03 → EPIC-07** (Admin): đã có bản nháp PBI sơ bộ (chưa áp quy ước mới: cột Mô tả Task,
  mã `PBI-N0xx`, AC thuần Việt). Cần rà lại từng epic như EPIC-01/02.
- **EPIC-08 → EPIC-15** (Kinh doanh): mới có tên epic, chưa phân rã. Toàn bộ là tính năng mới
  (chưa có code).
