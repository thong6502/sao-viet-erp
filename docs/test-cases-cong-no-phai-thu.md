# Test case Công nợ phải thu

## Mốc phát sinh công nợ — ĐÃ ĐỔI 12/08/2026

**Trước:** công nợ suy từ ĐƠN ĐÃ CHỐT. Đơn vừa chốt, chưa in chưa giao, đã nằm trong "Tổng phải
thu"; cọc khách nộp bị trừ thẳng vào nợ như thể khách đã trả tiền hàng; hạn thanh toán đếm từ
`Ngày giao cam kết` — một cột kế hoạch mà Sale sửa được.

**Nay:** công nợ CHỈ mọc khi kế toán **ghi nhận hóa đơn** (bước ⑤ "Hóa đơn" trong Vòng đời đơn).
Hóa đơn đỏ xuất bên MISA, ở SVN chỉ chép lại số/ký hiệu/ngày.

Hệ quả đã được chốt và chấp nhận: **đơn đã chốt nhưng chưa xuất hóa đơn không tính vào hạn mức
tín dụng nữa.**

## Phạm vi

Màn `Kế toán > Công nợ phải thu` suy ra số liệu từ:

- **Hóa đơn bán** còn hiệu lực (`sales_invoices`, trạng thái `issued`) — một dòng nợ = một hóa đơn.
- Phiếu thu gắn HÓA ĐƠN (`payment_receipts.sales_invoice_id`, trạng thái `received`) — trừ thẳng nợ.
- Cọc gắn ĐƠN (`payment_receipts.order_id`, nguồn `order_deposit`, `received`) — được **cấn trừ**
  FIFO sang các hóa đơn của chính đơn đó theo `(ngày hóa đơn, id)`.
- Hạn mức và số ngày công nợ của khách hàng trong CRM.

Không tính: đơn nháp, đơn đã hủy, đơn đã chốt **chưa có hóa đơn**, hóa đơn đã hủy, phiếu thu không
gắn đơn/hóa đơn.

Công thức một hóa đơn:

```
còn phải thu = amount_vnd − Σ phiếu thu gắn HĐ (received) − phần cọc được cấn trừ
hạn thanh toán = ngày hóa đơn + số ngày công nợ của khách (chốt lúc ghi HĐ)
```

## TC-01: Đơn đã chốt, CHƯA ghi hóa đơn ⇒ chưa có công nợ

1. Tạo khách hàng A, hạn mức 10.000.000đ, số ngày công nợ 7 ngày.
2. Tạo đơn bán cho khách A, tổng gồm VAT 5.000.000đ.
3. Chốt đơn. **Không** ghi hóa đơn.
4. Mở `Kế toán > Công nợ phải thu`.

Kết quả mong đợi:

- Khách A **không** xuất hiện; `Tổng phải thu` không tăng.
- Thẻ hạn mức trên màn `Khách hàng` cũng báo dư nợ 0 (hai màn dùng chung một công thức).
- Mở đơn → tab `Tổng quan & Vòng đời` → bước `Hóa đơn`: badge `CHƯA GHI`, `Chưa xuất HĐ` =
  5.000.000đ, có nút `Ghi nhận hóa đơn`.

## TC-02: Ghi hóa đơn ⇒ công nợ phát sinh, hạn tính từ ngày hóa đơn

1. Dùng đơn ở TC-01, bước `Hóa đơn` → `Ghi nhận hóa đơn`.
2. Ký hiệu `1C26TAA`, số `0000123`, ngày `01/08/2026`, số tiền để nguyên mặc định.
3. Mở `Công nợ phải thu`.

Kết quả mong đợi:

- Khách A xuất hiện, `Tổng phải thu` = 5.000.000đ, cột `HĐ còn nợ` = 1.
- Drawer chi tiết: dòng hóa đơn `0000123`, `Hạn thu` = **08/08/2026** (01/08 + 7 ngày).
- Sửa `Ngày giao cam kết` của đơn sang giá trị khác ⇒ **hạn thu KHÔNG đổi**.

## TC-03: Cọc không phải là trả nợ

1. Tạo khách F, đơn 5.000.000đ, `% cọc` 30%.
2. Chốt đơn, kế toán thu cọc 1.500.000đ ở bước `Cọc`.
3. Mở `Công nợ phải thu` (chưa ghi hóa đơn).
4. Ghi hóa đơn trọn đơn, mở lại `Công nợ phải thu`.

Kết quả mong đợi:

- Bước 3: khách F **chưa** có công nợ (cọc đã vào quỹ nhưng chưa có nợ để trừ).
- Bước 4: `Còn phải thu` = 3.500.000đ; drawer có cột `Cọc cấn trừ` = 1.500.000đ và `Đã thu` = 0.
- Bảng `Phiếu thu đã ghi nhận` hiện phiếu cọc với nhãn `cọc đơn — được cấn trừ`.

## TC-04: Hóa đơn từng phần + trần theo giá trị đơn

1. Đơn 5.000.000đ đã chốt.
2. Ghi hóa đơn 2.000.000đ, rồi ghi tiếp 3.000.000đ.
3. Thử ghi thêm một hóa đơn nữa.

Kết quả mong đợi:

- `Công nợ phải thu` = 5.000.000đ, cột `HĐ còn nợ` = 2.
- Bước `Hóa đơn`: `Chưa xuất HĐ` = 0, badge `ĐÃ GHI ĐỦ`, nút ghi hóa đơn biến mất.
- Bước 3 bị chặn với thông báo vượt giá trị đơn còn được xuất hóa đơn.
- Bỏ trống ô số tiền ⇒ tự lấy trọn phần chưa xuất.

## TC-05: Cọc rải FIFO qua nhiều hóa đơn

1. Đơn 5.000.000đ, thu cọc 2.500.000đ.
2. Ghi HĐ1 ngày 01/08 số tiền 2.000.000đ; HĐ2 ngày 05/08 số tiền 3.000.000đ.

Kết quả mong đợi:

- HĐ1 được cọc phủ hết ⇒ rời khỏi danh sách còn nợ.
- HĐ2 còn nợ 2.500.000đ (nhận 500.000đ cọc thừa).

## TC-06: Thu tiền hóa đơn

1. Hóa đơn 5.000.000đ chưa thu.
2. Lập phiếu thu gắn hóa đơn 2.000.000đ, rồi 3.000.000đ.
3. Thử thu thêm 1đ.

Kết quả mong đợi:

- Sau lần 1: còn phải thu 3.000.000đ.
- Sau lần 2: hóa đơn rời danh sách còn nợ; `Đã thu (3 tháng)` vẫn hiện 5.000.000đ để truy vết.
- Bước 3 bị chặn (thu vượt giá trị hóa đơn).
- Cổng "đủ cọc" của đơn **không** nhích lên vì tiền này (phiếu thu hóa đơn không mang `order_id`).

## TC-07: Hủy hóa đơn

1. Ghi hóa đơn trọn đơn, chưa thu đồng nào → hủy hóa đơn (bắt buộc nhập lý do).
2. Ghi lại hóa đơn, lập một phiếu thu gắn nó → thử hủy hóa đơn.

Kết quả mong đợi:

- Bước 1: công nợ về 0, phần giá trị đó được xuất hóa đơn lại.
- Bước 2: **bị chặn** — "hóa đơn đã có phiếu thu gắn vào, hủy phiếu thu trước".

## TC-08: Quá hạn

1. Khách B, số ngày công nợ 1 ngày.
2. Ghi hóa đơn có ngày cũ hơn hôm nay ít nhất 2 ngày, chưa thu đủ.
3. Mở `Công nợ phải thu`, chọn lọc `Quá hạn`.

Kết quả mong đợi:

- Khách B xuất hiện trong lọc `Quá hạn`; drawer hiện số ngày quá hạn ở dòng hóa đơn.

## TC-09: Chưa đặt hạn công nợ

1. Khách C, không khai số ngày công nợ. Ghi hóa đơn, chưa thu đủ.

Kết quả mong đợi:

- Khách C xuất hiện, **không** bị tính vào `Quá hạn`.
- Dòng có cảnh báo `Chưa đặt số ngày công nợ` / `Chưa đặt hạn`.

## TC-10: Vượt hạn mức

1. Khách D, hạn mức 1.000.000đ. Ghi hóa đơn còn phải thu 2.500.000đ.

Kết quả mong đợi:

- Xuất hiện trong lọc `Vượt hạn mức`, cột hạn mức hiển thị vượt 1.500.000đ.
- ⚠️ Đơn đã chốt **chưa** xuất hóa đơn KHÔNG làm khách chạm hạn mức (khác hành vi cũ — đây là
  hệ quả đã chấp nhận của việc dời mốc).

## TC-11: Không tính đơn nháp / đơn hủy / hóa đơn hủy

1. Đơn nháp chưa chốt; đơn khác đã chốt rồi hủy; một hóa đơn đã hủy.

Kết quả mong đợi:

- Không cái nào làm tăng công nợ phải thu.

## TC-12: Phiếu thu khác không gắn đơn/hóa đơn

1. `Kế toán > Phiếu thu` → tạo phiếu nguồn `Thu khác`.

Kết quả mong đợi:

- Không trừ công nợ của hóa đơn nào; phiếu vẫn xem được ở sổ `Phiếu thu`.

## TC-13: Quyền

1. Vai chỉ có `Xem` trên `Công nợ phải thu`.

Kết quả mong đợi:

- Mở được màn và bước `Hóa đơn`, nhưng **không** thấy nút `Ghi nhận hóa đơn`; gọi API trả 403.
- Vai kế toán (mẫu) ghi và hủy được hóa đơn.

## TC-14: Truy vết

1. Drawer `Công nợ phải thu` → bấm mã đơn ở cột `Đơn`.
2. Bấm mã phiếu thu ở bảng `Phiếu thu đã ghi nhận`.

Kết quả mong đợi:

- Mã đơn mở sang màn `Đơn hàng bán` đúng đơn.
- Mã phiếu thu mở sang màn `Phiếu thu` và lọc đúng phiếu.
- Cột `Gắn vào` phân biệt rõ `thu hóa đơn` với `cọc đơn — được cấn trừ`.

## Lưới tự động

`backend/tests/test_sales_invoices_api.py` phủ TC-01…TC-08, TC-10 (chiều hạn mức) và TC-11 ở mức
service. Vùng này **trước đây không có test nào** — `test_accounting_api.py` chưa từng chạm
receivables.
