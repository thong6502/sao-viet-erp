# Quyền theo tổ · Tab Sản lượng trên Bàn tổ — Bản chốt

Chốt 14/09/2026 qua buổi bàn với chủ dự án ("lưu thông tin trên vào file mới rồi làm luôn").

## Mục tiêu cuối

Bàn tổ có tab **Sản lượng**, lọc từ ngày – đến ngày, xem theo LSX. Trưởng cấp nào thấy sản lượng của
cấp đó + mọi cấp trực thuộc (tới từng thành viên); cá nhân chỉ thấy của mình. Mọi phần dưới đây là để
"ai thấy gì / làm được gì" ở Bàn tổ do **ma trận phân quyền** quyết, đi đúng theo cây trong module
Phòng ban (vd Phòng sản xuất → Tổ in → Nhóm in máy 2 màu).

## 1. Dòng quyền sinh theo tổ

- Mỗi nút thuộc khối sản xuất trong Phòng ban (kể cả cấp gom) sinh **một dòng** trong nhóm
  "Tổ sản xuất" của ma trận phân quyền, thụt lề theo cây.
- Dòng gắn theo **id phòng ban**, tự tạo / đổi tên / xoá theo phòng ban.
- Mỗi dòng: **Xem · Phạm vi · 4 quyền chi tiết**. Không có cột Thao tác (4 quyền chi tiết thay nó).

## 2. Phạm vi — tính từ VỊ TRÍ NGƯỜI XEM, trong VÙNG của dòng

Vùng của dòng = tổ đó + mọi đơn vị trực thuộc.

- **Của tôi** — chỉ của mình.
- **Cả phòng** — phòng mình đang thuộc + các đơn vị trực thuộc của phòng mình (phần nằm trong vùng).
- **Tất cả** — toàn bộ vùng của dòng, dù mình ở nấc nào.

Phạm vi áp cho cả XEM lẫn 4 quyền chi tiết. Một người có nhiều dòng chồng nhau → lấy phần RỘNG nhất.

Ví dụ trên dòng "Tổ in" (cây Sản xuất → Tổ in → Nhóm in máy 2 màu):

| Phạm vi | A thuộc Nhóm 2 màu (nấc cuối) | B thuộc Tổ in |
|---|---|---|
| Của tôi | chỉ phần của A | chỉ phần của B |
| Cả phòng | Nhóm 2 màu + nhóm dưới nó | Tổ in + Nhóm 2 màu + mọi nhóm của Tổ in |
| Tất cả | toàn bộ Tổ in | toàn bộ Tổ in |

Cấp dòng Tổ in phạm vi Cả phòng cho người Tổ cắt → không thấy gì (phòng họ không nằm trong vùng).

## 3. Bốn quyền chi tiết

| Quyền | Gồm |
|---|---|
| Thực hiện lệnh | giao/rút người; bắt đầu, tạm dừng, đổi máy, kết thúc, báo sự cố; nhận/trả khuôn; ghi mẻ + lô đầu vào |
| Xác nhận sản lượng | chia sản lượng (tính, chốt, mở lại, bù trừ, loại trừ chấm công); bàn giao/nhận; hỗ trợ chéo |
| KCS | kiểm, ghi lỗi + ảnh, sửa kết quả, phản hồi lỗi, đóng thiếu nhóm |
| Kho | đề nghị vật tư, xác nhận nhận vật tư, yêu cầu nhập kho, phân loại + xác nhận BTP |

## 4. Vai mẫu (điền sẵn trên dòng của tổ mà vai thuộc về — chỉ là mặc định, quản trị sửa được)

- **Tổ trưởng**: Xem + Cả phòng + bật cả 4.
- **Công nhân**: Xem + Của tôi, không quyền chi tiết.

## 5. Bàn tổ chuyển sang hỏi quyền theo tổ

- Menu tổ = các tổ mình thấy được, thụt lề theo cây; bàn của cấp gom gộp việc + sản lượng của các tổ
  trực thuộc.
- Thao tác do 4 quyền chi tiết + phạm vi quyết. **Bỏ luật cứng "phải đứng tên trưởng tổ".**
- Thông báo real-time gửi người có quyền tương ứng trên tổ đó.
- Ô "Kế hoạch sản xuất" thôi gác Bàn tổ; gỡ 3 quyền chi tiết cũ (Gán việc · Ghi sản lượng · Bàn giao/nhận).

## 6. Tab Sản lượng

- Lọc: từ ngày – đến ngày (mặc định đầu tháng → hôm nay) · Đơn vị (nút trong vùng thấy được) · tìm LSX.
- Bảng mở tầng: LSX → công đoạn (tốt, hỏng, đơn vị) → người (đã chốt, tạm tính, nhãn hỗ trợ chéo).
  Phạm vi Của tôi: không có tầng người, số là phần của mình.
- Ngày = ngày bắt đầu mẻ theo giờ xưởng. Không cộng lẫn đơn vị. Tách đã chốt / tạm tính.
- Lọc, phân trang, cộng tổng ở máy chủ; tự tải lại theo sự kiện đẩy (SSE).

## 7. Chuyển dữ liệu

- Vai theo tổ hiện có → dòng của đúng tổ đó (tổ trưởng: Cả phòng + 4 quyền; thợ: Của tôi).
- Vai đang có phạm vi Tất cả ở Kế hoạch sản xuất → dòng gốc "Sản xuất", Tất cả.
- Migration + cập nhật `docs/DB_SCHEMA.md`.

## Thứ tự làm

1. Dòng quyền theo tổ + 4 quyền chi tiết + chuyển dữ liệu.
2. Bàn tổ + mọi thao tác chuyển sang hỏi quyền theo tổ.
3. Tab Sản lượng.
