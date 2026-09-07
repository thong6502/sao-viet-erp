# Thiết kế — Module Quản lý Tài sản cố định & Công cụ dụng cụ

Ngày: 07/09/2026 · Trạng thái: đã chốt phạm vi, CHƯA làm code

## 1. Mục tiêu

Thay bảng Excel theo dõi tài sản cố định và công cụ dụng cụ của kế toán bằng một sổ
có tính khấu hao tự động, có khoá kỳ, và giữ được lịch sử biến động của từng tài sản.

Đầu ra chính mỗi tháng: **bảng trích khấu hao và phân bổ** xuất ra Excel để kế toán
nhập sang phần mềm kế toán bên ngoài.

## 2. Phạm vi

Trong phạm vi:

- Sổ tài sản dùng chung cho tài sản cố định (TSCĐ) và công cụ dụng cụ (CCDC).
- Hai cửa vào sổ: nhập số dư đầu kỳ, và ghi tăng khi mua mới.
- Tính khấu hao / phân bổ theo tháng, chốt kỳ khoá số.
- Ba chứng từ biến động: điều chuyển bộ phận, ghi tăng nguyên giá (nâng cấp), ghi giảm.
- Kiểm kê mức tối giản: in danh sách đi đối chiếu tay, nhập lại kết quả thiếu/thừa.
- Báo cáo: sổ tài sản theo bộ phận, bảng trích khấu hao từng kỳ, thẻ tài sản.

**Ngoài phạm vi** (nói rõ để sau này không trôi vào):

- Không nối sang danh mục máy thiết bị của xưởng.
- Không lấy chi phí từ phiếu sửa chữa của module kỹ thuật máy.
- Không có luồng cấp phát – thu hồi CCDC cho tổ trưởng ký nhận.
- Không quét QR, không màn điện thoại.
- Không sinh bút toán, không đụng sổ cái, không có ô tài khoản.
- Không đánh giá lại tài sản, không quản lý hợp đồng thuê tài chính.
- Không tính chi phí máy/giờ cho module tính giá.

## 3. Chỗ ghi tài khoản

Module không biết hệ thống tài khoản. Thay vào đó có ô **Ghi chú hạch toán** dạng chữ
tự do ở hai nơi:

- Trên từng tài sản — kế thừa xuống mọi kỳ khấu hao của tài sản đó.
- Trên từng chứng từ biến động.

Ô này in ra thành một cột trong bảng khấu hao xuất Excel. Kế toán gõ gì tuỳ ý
("211 / 6274 – tổ In", "chi phí về tổ Bế từ tháng 10"), phần mềm chỉ giữ nguyên chuỗi.

## 4. Khái niệm và quy tắc tính

**Loại tài sản** — một ô chọn trên chính tài sản: TSCĐ hoặc CCDC. Không có danh mục
nhóm tài sản; số tháng khấu hao kế toán gõ thẳng, dưới ô có dòng nhắc khung tham khảo
(máy in 7–15 năm, CCDC tối đa 3 năm).

**Nguyên giá** — nhập thành nhiều dòng cấu thành (giá mua, vận chuyển, lắp đặt, chạy
thử), phần mềm cộng lại. Không bắt kế toán cộng ngoài giấy.

**Ngày đưa vào sử dụng** — mốc bắt đầu trích, không phải ngày hoá đơn.

**Mức trích một tháng** = nguyên giá ÷ số tháng khấu hao.

**Tháng đầu tiên** tính theo số ngày sử dụng thực tế trong tháng đó
(mức trích tháng × số ngày dùng ÷ số ngày của tháng). Tháng ghi giảm cũng vậy: trích
tới ngày giảm rồi dừng.

**Kỳ cuối cùng** nhận phần chênh lệch do làm tròn, để tổng lũy kế bằng đúng nguyên giá.

**Điều chuyển giữa tháng**: chi phí trọn tháng đó tính về bộ phận đang giữ tài sản lúc
chốt kỳ, không chia đôi theo ngày.

**Nâng cấp**: nguyên giá cộng thêm, hao mòn lũy kế giữ nguyên, mức trích mới =
(nguyên giá mới − lũy kế) ÷ số tháng còn lại, áp dụng **từ kỳ sau**.

**Ngưỡng cảnh báo**: nguyên giá dưới 30.000.000 mà chọn loại TSCĐ thì cảnh báo mềm và
hỏi có chuyển sang CCDC không — kế toán vẫn quyết được. Ngưỡng để ở tham số hệ thống,
không đóng cứng trong code.

## 5. Luồng nhập liệu

### 5.1. Nhập số dư đầu kỳ

Làm một lần khi mở module, cho tài sản đang dùng dở. Ngoài các ô như ghi tăng, bắt buộc
thêm **số tháng đã trích** và **hao mòn lũy kế** tại ngày cắt sổ. Thiếu hai ô này là
phần mềm tính lại từ đầu và lệch ngay tháng đầu tiên.

Ví dụ: máy dao xén Polar, nguyên giá 450.000.000, dùng từ 01/06/2023, 120 tháng,
cắt sổ 01/01/2026 → đã trích 31 tháng, lũy kế 116.250.000. Phần mềm suy ra còn lại
333.750.000, còn 89 tháng, mỗi tháng 3.750.000.

### 5.2. Ghi tăng

Ví dụ máy in offset Komori 4 màu, mua 10/03/2026:

| Ô nhập | Giá trị |
|---|---|
| Tên, số hoá đơn, nhà cung cấp | Komori 4 màu, HĐ 0001234, … |
| Loại | Tài sản cố định |
| Dòng cấu thành nguyên giá | giá mua 3.200.000.000 · vận chuyển 40.000.000 · lắp đặt chạy thử 60.000.000 |
| Nguyên giá (phần mềm cộng) | 3.300.000.000 |
| Số tháng khấu hao | 120 |
| Ngày đưa vào sử dụng | 10/03/2026 |
| Bộ phận sử dụng, người quản lý, vị trí | Tổ In, … |
| Ghi chú hạch toán | tự do |

Lưu xong: cấp mã tài sản và **hiện ngay bảng khấu hao dự kiến 120 dòng** để soát —
tháng 3/2026 trích 19.516.129 (22 ngày), từ tháng 4 đều 27.500.000.

### 5.3. Chạy khấu hao tháng và chốt kỳ

Kế toán bấm *Tính khấu hao tháng 08/2026*, phần mềm bung bảng:

| Tài sản | Bộ phận | Nguyên giá | Trích tháng này | Lũy kế | Còn lại |
|---|---|---|---|---|---|
| Máy in Komori 4 màu | Tổ In | 3.300.000.000 | 27.500.000 | 157.016.129 | 3.142.983.871 |
| Máy dao xén Polar | Tổ Thành phẩm | 450.000.000 | 3.750.000 | 146.250.000 | 303.750.000 |
| Lô 12 tấm cao su offset | Tổ In | 28.800.000 | 1.200.000 | 2.400.000 | 26.400.000 |

Cột cuối là ghi chú hạch toán. Soát xong → xuất Excel → bấm **Chốt kỳ**.

Kỳ đã chốt thì khoá: không sửa được nguyên giá, ngày sử dụng, số tháng của tài sản có
kỳ nằm trong vùng đã chốt. Sửa ô mô tả và ghi chú thì vẫn được. Muốn đổi số phải mở kỳ
(có ghi vết ai mở, lúc nào) hoặc đi bằng chứng từ biến động.

### 5.4. Điều chuyển bộ phận

Chọn tài sản, bộ phận mới, ngày, lý do, ghi chú. Nguyên giá và lũy kế không đổi; từ kỳ
sau chi phí chảy về bộ phận mới.

### 5.5. Ghi tăng nguyên giá (nâng cấp)

Chỉ dùng khi nâng cấp làm máy chạy nhanh hơn, in đẹp hơn hoặc dùng lâu hơn. Nhập số
tiền và số tháng còn dùng.

Ví dụ lắp bộ sấy UV 180.000.000 cho máy Komori ngày 01/09/2026: nguyên giá thành
3.480.000.000, lũy kế giữ 157.016.129, còn phải trích 3.322.983.871 chia 114 tháng →
từ tháng 9 mức trích **29.148.981**/tháng.

### 5.6. Ghi giảm

Lý do: thanh lý, nhượng bán, mất, hỏng không sửa được, góp vốn. Nhập ngày, lý do,
giá bán (nếu có). Phần mềm trưng giá trị còn lại và chênh lệch để kế toán xử lý, rồi
ngừng trích từ ngày giảm.

Ví dụ máy in 2 màu cũ: nguyên giá 800.000.000, lũy kế 620.000.000, còn 180.000.000,
bán 200.000.000 → chênh +20.000.000.

### 5.7. Công cụ dụng cụ

Khác TSCĐ đúng một chỗ: **nhập theo lô có số lượng và đơn giá**, một phiếu cho cả lô.

Ví dụ 12 tấm cao su offset, đơn giá 2.400.000 → 28.800.000, phân bổ 24 tháng kể từ
01/07/2026 → 1.200.000/tháng.

Ghi giảm được **một phần lô**: tháng 11/2026 một tấm rách. Lúc đó lô đã phân bổ 5 tháng
(6.000.000), còn 22.800.000 cho 12 tấm, mỗi tấm còn 1.900.000. Ghi giảm 1 tấm → số lượng
còn 11, giá trị còn lại 20.900.000, chia 19 tháng còn lại → mức phân bổ mới
1.100.000/tháng.

### 5.8. Kiểm kê (mức tối giản)

Tạo đợt kiểm kê, chọn bộ phận, in danh sách tài sản phải có. Đi đối chiếu bằng tay, về
nhập lại: cái nào không tìm thấy, cái nào có thật mà chưa vào sổ. Kết đợt sinh chứng từ
ghi giảm hoặc ghi tăng bổ sung. Không QR, không màn điện thoại.

## 6. Dữ liệu cần lưu (mức khái niệm)

- **Tài sản**: mã, tên, loại (TSCĐ/CCDC), số lượng, đơn giá, nguyên giá, ngày đưa vào
  sử dụng, số tháng khấu hao, bộ phận, người quản lý, vị trí, ghi chú hạch toán,
  trạng thái (đang dùng / đã giảm), nguồn vào sổ (ghi tăng / đầu kỳ), hao mòn đầu kỳ,
  số tháng đã trích đầu kỳ.
- **Dòng cấu thành nguyên giá**: diễn giải, số tiền.
- **Chứng từ biến động**: loại (điều chuyển / nâng cấp / ghi giảm), ngày, số tiền,
  bộ phận mới, số lượng giảm, lý do, ghi chú hạch toán.
- **Dòng khấu hao theo kỳ**: kỳ (năm–tháng), tài sản, mức trích, lũy kế, còn lại,
  bộ phận, ghi chú.
- **Kỳ kế toán**: kỳ, trạng thái (mở / đã chốt), ngày chốt, người chốt.
- **Đợt kiểm kê** và dòng kiểm kê.

Một bảng chứng từ biến động gánh cả ba nghiệp vụ, không tách ba bảng.

## 7. Phân quyền

Một module quyền `tai_san` với các thao tác: xem, sửa (ghi tăng và chứng từ biến động),
chốt kỳ, mở lại kỳ đã chốt. Chốt kỳ và mở kỳ nên tách riêng cho kế toán trưởng.

## 8. Ca biên cần xử lý đúng

- Ghi tăng ngày cuối tháng → tháng đó vẫn có một dòng trích rất nhỏ, không bỏ.
- Ghi giảm giữa tháng → trích tới ngày giảm rồi dừng, kỳ sau không còn dòng.
- Nâng cấp trong tháng đã chốt → chỉ ảnh hưởng từ kỳ chưa chốt kế tiếp.
- Tài sản đã khấu hao hết vẫn nằm trong sổ với giá trị còn lại bằng 0, không tự biến mất.
- Xoá tài sản chỉ cho phép khi chưa có kỳ nào chốt liên quan; còn lại phải đi ghi giảm.
- Chốt kỳ hai lần, hoặc chốt kỳ khi kỳ trước chưa chốt → chặn.

## 9. Điểm cần kế toán SVN xác nhận trước khi code

1. Tháng đầu tiên tính theo ngày (đúng quy định) hay làm tròn trọn tháng (nhiều nơi làm
   cho gọn)? Bản thiết kế này đang chọn tính theo ngày.
2. Ngưỡng 30.000.000 có giữ làm mốc cảnh báo không, hay xưởng quy định mức khác.
3. Bảng Excel xuất ra cần đúng những cột nào để khớp thói quen đang dùng.
