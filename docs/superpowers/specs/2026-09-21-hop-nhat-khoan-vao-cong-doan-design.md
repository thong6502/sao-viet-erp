# Hợp nhất Khoán vào Công đoạn

Ngày chốt thiết kế: 21/09/2026

## 1. Mục tiêu

Bỏ module danh mục **Công việc khoán** độc lập và đưa cấu hình khoán vào chính
drawer **Công đoạn**. Mỗi công đoạn có tối đa một cấu hình khoán chính. Khi ghi
mẻ, hệ thống tự lấy cấu hình của công đoạn thay vì yêu cầu thợ chọn một công
việc khoán trong danh sách của tổ.

Thiết kế phải giữ nguyên dữ liệu lịch sử của các mẻ đã ghi theo mô hình cũ và
không tự suy đoán quan hệ giữa Công việc khoán cũ với Công đoạn.

## 2. Các quyết định đã chốt

- Mọi công đoạn luôn có tab **Khoán**.
- Mỗi công đoạn có tối đa một cấu hình khoán chính.
- Tổ áp dụng lấy từ danh sách tổ phụ trách của công đoạn; không khai tổ lần hai
  trong tab Khoán.
- Công thức khoán được nhập và lưu nhưng chưa được thực thi ở bất kỳ luồng nào.
- Khi ghi mẻ, thợ không còn chọn Công việc khoán. Hệ thống tự lấy cấu hình của
  công đoạn đang thực hiện.
- Việc phát sinh được khai theo công đoạn, được chọn khi ghi mẻ và không cộng
  vào sản lượng chính.
- Dữ liệu Công việc khoán cũ không được tự ghép sang Công đoạn.
- Tab Khoán dùng chung quyền và nhật ký với Công đoạn.
- Dùng một bảng cấu hình khoán quan hệ 1–1 với Công đoạn, không đưa các cột
  khoán trực tiếp vào bảng Công đoạn và không tái sử dụng mô hình Công việc
  khoán cũ cho dữ liệu mới.

## 3. Giao diện Công đoạn

Thứ tự tab trong drawer Công đoạn:

1. Thông tin
2. Khoán
3. Vật tư
4. Công thức tính giá
5. Nhật ký

Tab **Khoán** luôn hiển thị và gồm ba khối.

### 3.1. Đơn giá

- Đơn vị tính khoán
- Đơn giá

Đơn vị lấy từ danh mục Đơn vị & quy đổi. Đơn giá cho phép bằng `0` nhưng không
được âm.

### 3.2. Công thức khoán

Hiển thị ô nhập công thức theo kiểu nhập công thức đang có trong hệ thống. Giá
trị được lưu để dùng về sau nhưng hiện tại không tham gia tính sản lượng hoặc
tiền khoán. Giao diện phải ghi rõ: **Đang lưu cấu hình, chưa áp dụng tính tự
động**.

### 3.3. Việc phát sinh

Cho phép thêm, sửa, xóa nhiều dòng. Mỗi dòng gồm:

- Tên việc
- Đơn giá
- Đơn vị tính

Ví dụ: `Thay kẽm · 100.000 đ / bản kẽm`.

Drawer chỉ có một nút **Lưu thay đổi**. Thông tin Công đoạn và cấu hình Khoán
được lưu trong cùng một giao dịch. Nếu phần Khoán không hợp lệ thì không lưu dở
phần Thông tin.

## 4. Trạng thái và luật kiểm tra

Không thêm công tắc “Áp dụng khoán”. Trạng thái được xác định từ dữ liệu:

- Đơn vị, đơn giá, công thức đều trống và không có việc phát sinh: công đoạn
  chưa cấu hình khoán.
- Khi người dùng nhập bất kỳ dữ liệu nào trong tab Khoán: bắt buộc có đủ đơn vị
  tính khoán và đơn giá chính.
- Công thức và danh sách việc phát sinh là tùy chọn.
- Không cho lưu việc phát sinh nếu cấu hình khoán chính chưa đầy đủ.

Luật cho việc phát sinh:

- Tên không được trống.
- Đơn vị phải có trong danh mục Đơn vị & quy đổi.
- Đơn giá phải từ `0` trở lên.
- Tên không được trùng trong cùng một công đoạn sau khi chuẩn hóa hoa/thường và
  khoảng trắng.

Nếu người dùng xóa trắng toàn bộ nội dung rồi lưu, hệ thống hiểu là gỡ cấu hình
khoán khỏi công đoạn. Nếu chỉ xóa một phần khiến cấu hình thiếu đơn vị hoặc đơn
giá, hệ thống chặn lưu, chuyển về tab Khoán và chỉ đúng trường lỗi.

## 5. Mô hình dữ liệu mới

### 5.1. Cấu hình khoán công đoạn

Tạo bảng cấu hình khoán quan hệ 1–1 với Công đoạn. Mỗi dòng chứa tối thiểu:

- Khóa chính
- Công đoạn, có ràng buộc duy nhất để một công đoạn chỉ có tối đa một cấu hình
- Mã đơn vị tính khoán
- Đơn giá
- Công thức khoán, có thể rỗng
- Các mốc tạo và cập nhật nếu mẫu bảng hiện hành yêu cầu

Việc “chưa cấu hình” được biểu diễn bằng việc không có dòng cấu hình, không dùng
một dòng có các trường rỗng.

### 5.2. Việc phát sinh công đoạn

Tạo bảng con của cấu hình khoán, mỗi dòng chứa tối thiểu:

- Khóa chính
- Khóa cấu hình khoán công đoạn
- Tên việc
- Mã đơn vị
- Đơn giá
- Thứ tự hiển thị

### 5.3. Dữ liệu mẻ

Mẻ mới phải có đường truy nguyên tới cấu hình khoán công đoạn nếu cần đối chiếu,
đồng thời tiếp tục lưu ảnh chụp:

- Tên công đoạn hoặc nhãn khoán cần hiển thị
- Đơn vị khoán
- Đơn giá khoán
- Từng việc phát sinh đã chọn, số lượng, tên, đơn vị và đơn giá

Ảnh chụp là nguồn hiển thị và tính lịch sử. Thay đổi danh mục sau này không tự
sửa ảnh chụp của mẻ.

## 6. Luồng ghi mẻ mới

1. Người dùng mở form ghi mẻ của một công việc sản xuất.
2. Máy chủ xác định Công đoạn từ công việc sản xuất; không tin một mã công đoạn
   hoặc cấu hình khoán do client tự gửi.
3. Hệ thống nạp cấu hình khoán hiện hành của Công đoạn.
4. Nếu đã cấu hình, giao diện hiện đơn vị và đơn giá chính dưới dạng thông tin cố
   định, đồng thời cho chọn các việc phát sinh và nhập số lượng.
5. Nếu chưa cấu hình, form vẫn cho ghi sản lượng bình thường, không hiện phần
   việc phát sinh và không phát sinh tiền khoán.
6. Khi lưu, máy chủ kiểm lại cấu hình hiện hành và chụp dữ liệu vào mẻ trong
   cùng giao dịch.

Số lượng việc phát sinh phải lớn hơn `0`. Một việc phát sinh không được chọn hai
lần trong cùng mẻ và phải thuộc đúng cấu hình khoán của Công đoạn đó.

Tiền việc phát sinh được xác định riêng theo `số lượng × đơn giá phát sinh`.
Số lượng phát sinh không cộng vào sản lượng chính của mẻ. Quy tắc tính tiền
khoán chính hiện hành được giữ nguyên; thay đổi này chỉ thay nguồn cấu hình từ
Công việc khoán sang Công đoạn. Công thức khoán chưa được gọi.

## 7. Ảnh chụp và thay đổi danh mục

- Mẻ giữ đơn vị và đơn giá tại thời điểm ghi.
- Sửa hoặc gỡ cấu hình Khoán không làm thay đổi mẻ cũ.
- Tiếp tục hỗ trợ cảnh báo **Danh mục đã đổi** khi ảnh chụp khác cấu hình hiện
  hành.
- Nếu hệ thống đang có thao tác chủ động **Cập nhật theo danh mục**, thao tác này
  được chuyển sang đọc cấu hình Khoán của Công đoạn; không tự cập nhật ngầm.
- Nếu cấu hình nguồn đã bị gỡ, mẻ vẫn hiển thị từ ảnh chụp và có thể báo cấu
  hình nguồn không còn tồn tại.

## 8. Dữ liệu và tương thích lịch sử

Không tự ghép các dòng Công việc khoán cũ sang Công đoạn vì quan hệ hiện tại là
nhiều công việc theo tổ và không có khóa 1–1 đáng tin cậy.

- Giữ bảng Công việc khoán cũ và bảng việc phát sinh cũ ở mức cần thiết để đọc,
  đối chiếu và hiển thị mẻ lịch sử.
- Mẻ lịch sử tiếp tục dùng khóa nguồn cũ và ảnh chụp cũ.
- Mẻ mới chỉ dùng cấu hình Khoán của Công đoạn.
- Không cho tạo hoặc sửa cấu hình theo mô hình Công việc khoán cũ sau khi chuyển
  đổi.
- Không xóa dữ liệu cũ trong migration này.

## 9. API và giao dịch

API đọc Công đoạn trả thêm khối `khoan`, có thể rỗng. Khối này gồm đơn vị, đơn
giá, công thức và danh sách việc phát sinh.

API tạo/sửa Công đoạn nhận cùng khối `khoan`:

- Khối trống hoàn toàn biểu thị chưa cấu hình hoặc yêu cầu gỡ cấu hình hiện có.
- Khối có dữ liệu phải qua toàn bộ luật kiểm tra ở mục 4.
- Việc lưu Công đoạn, cấu hình Khoán, các việc phát sinh và nhật ký dùng chung
  một giao dịch.

Các API tạo/sửa/xóa Công việc khoán độc lập được gỡ khỏi luồng công khai. Đường
đọc nội bộ cần cho lịch sử có thể được giữ trong repository/service tương thích,
không tiếp tục xuất hiện như một module nghiệp vụ.

## 10. Quyền và nhật ký

- Người có quyền xem Công đoạn được xem tab Khoán.
- Người có quyền thêm/sửa Công đoạn được thêm/sửa/gỡ cấu hình Khoán.
- Gỡ module quyền `Công việc khoán` khỏi ma trận phân quyền và dữ liệu seed.
- Không tạo quyền con riêng cho tab Khoán.
- Nhật ký của Công đoạn ghi được thay đổi đơn vị, đơn giá, công thức và thao tác
  thêm/sửa/xóa việc phát sinh.
- Nhật ký không ghi công thức là đã được áp dụng vì hiện chưa có engine thực thi.

## 11. Phạm vi triển khai

- Gỡ Công việc khoán khỏi menu Cấu hình danh mục.
- Gỡ màn danh sách và drawer độc lập của module cũ.
- Thêm tab Khoán vào drawer Công đoạn.
- Mở rộng API, schema và service Công đoạn để quản lý cấu hình Khoán.
- Đổi form và service ghi mẻ sang tự lấy cấu hình theo Công đoạn.
- Chuyển phần đối chiếu/cập nhật ảnh chụp của mẻ mới sang nguồn Công đoạn.
- Viết migration tương thích SQLite và PostgreSQL.
- Cập nhật `docs/DB_SCHEMA.md` cùng thay đổi model.
- Gỡ quyền và catalog registry của Công việc khoán độc lập.

## 12. Ngoài phạm vi

- Không xây engine thực thi công thức khoán.
- Không tự tính lại mẻ cũ.
- Không tự ghép dữ liệu Công việc khoán cũ với Công đoạn.
- Không làm một màn hoặc luồng Khoán riêng mới.
- Chưa thêm cột hoặc bộ lọc Khoán vào danh sách Công đoạn.
- Không thay đổi cách chia tiền khoán cho người lao động ngoài việc đổi nguồn cấu
  hình của mẻ.

## 13. Tiêu chí nghiệm thu

1. Mọi Công đoạn đều có tab Khoán.
2. Công đoạn chưa khai Khoán vẫn lưu và ghi mẻ bình thường.
3. Cấu hình thiếu đơn vị hoặc đơn giá bị chặn với lỗi rõ ràng.
4. Một Công đoạn chỉ có tối đa một cấu hình khoán.
5. Ghi mẻ không còn chọn Công việc khoán; đơn giá lấy đúng từ Công đoạn.
6. Việc phát sinh chỉ lấy từ đúng Công đoạn và số lượng phải lớn hơn `0`.
7. Mẻ mới giữ ảnh chụp giá; sửa giá sau đó không đổi mẻ cũ.
8. Mẻ lịch sử theo mô hình cũ vẫn xem được đầy đủ.
9. Công thức khoán lưu được nhưng không được thực thi.
10. Nhật ký Công đoạn ghi được thay đổi trong tab Khoán.
11. Quyền Công đoạn kiểm soát cả tab Khoán; quyền module cũ không còn.
12. Migration chạy đúng trên SQLite và PostgreSQL, model khớp `docs/DB_SCHEMA.md`.
13. Lệnh xác minh duy nhất của dự án chạy đạt sau khi triển khai.

## 14. Các ca kiểm thử bắt buộc

- Tạo và sửa Công đoạn khi tab Khoán để trống.
- Tạo cấu hình có đơn giá bằng `0`.
- Chặn đơn giá âm, thiếu đơn vị hoặc thiếu đơn giá.
- Thêm, sửa, xóa và đổi thứ tự việc phát sinh.
- Chặn việc phát sinh trùng tên hoặc thiếu trường.
- Gỡ toàn bộ cấu hình Khoán bằng cách xóa trắng tab.
- Ghi mẻ cho Công đoạn chưa cấu hình Khoán.
- Ghi mẻ cho Công đoạn đã cấu hình, có và không có việc phát sinh.
- Chặn việc phát sinh không thuộc Công đoạn hoặc có số lượng không hợp lệ.
- Sửa đơn giá sau khi ghi mẻ và xác nhận ảnh chụp cũ không đổi.
- Đối chiếu và cập nhật theo danh mục bằng thao tác chủ động.
- Đọc mẻ lịch sử còn trỏ Công việc khoán cũ.
- Kiểm tra quyền xem/sửa Công đoạn áp dụng cho tab Khoán.
- Kiểm tra quyền và menu Công việc khoán cũ đã biến mất.
- Kiểm tra rollback toàn bộ giao dịch khi phần Khoán lưu lỗi.
