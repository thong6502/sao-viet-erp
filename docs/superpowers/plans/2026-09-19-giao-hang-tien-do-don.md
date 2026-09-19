# Giao hàng làm lại + Thanh tiến độ đơn — kế hoạch (19/09/2026)

Thiết kế đã chốt qua trao đổi 19/09/2026. Bỏ ý 4 (chuông/toast báo Sales) — chủ chốt "không cần
thiết"; drawer đơn vẫn tự làm mới im lặng khi có SSE (nguyên tắc real-time).

## Luật nghiệp vụ

1. **Giao được** (mỗi cụm bán) = kho ĐÃ NHẬN từ lệnh của CHÍNH đơn này − đã giao − đang giữ; gộp
   theo mã TP (hai cụm cùng tên = một mã), kẹp bởi còn phải giao và tồn thật của mã. "Kho đã nhận"
   đọc từ dòng yêu cầu NHẬP có nguồn công đoạn KCS (`san_xuat_cong_viec_id`) và `lsx_id` thuộc đơn —
   KHÔNG đọc tồn chung của mã (hai đơn trùng tên dùng chung một mã).
   Chặn ở máy chủ lúc tạo yêu cầu; lúc gửi yêu cầu xuất kho kiểm lại tồn thật, thiếu thì chặn.
2. **Đang giữ**: yêu cầu giữ phần chưa giao khi: chưa có chuyến · chuyến đang chạy (kể cả đang
   trả hàng) · chuyến giao thiếu mà phiếu nhập trả về chưa ghi sổ. Chuyến đã huỷ / thất bại đã nhận
   lại / giao thiếu đã nhận lại ⇒ nhả.
3. **Trạng thái yêu cầu (dẫn xuất)**: `cho_len_ke_hoach` · `dang_thuc_hien` · `da_giao_du` ·
   `giao_thieu` · `that_bai` · `chuyen_da_huy` · `da_huy`. Yêu cầu có chuyến đã huỷ được huỷ
   (không kẹt vì unique index mg 0229). Giữ luật một yêu cầu một chuyến.
4. **Trả hàng**: ghi kết quả thất bại / giao thiếu ⇒ máy tự lập yêu cầu NHẬP trả về (kho đã xuất).
   THỦ KHO lập + ghi sổ phiếu nhập như mọi hàng; ghi sổ ⇒ chuyến `dang_tra_hang` → `da_tra_hang`.
   Bỏ nút "Kho đã nhận lại" của tài xế (endpoint giữ lại nhưng chỉ còn là đường cũ cho chuyến trước
   bản này chưa có yêu cầu nhập).
5. **Huỷ đơn** bị chặn khi còn yêu cầu đang giữ hàng / chuyến đang chạy (nối `chan_huy_don_...`).
6. **Phiếu giao hàng in theo yêu cầu** (số của yêu cầu / số khách thực nhận của chuyến), không theo đơn.

## Backend

- `delivery_service`: `_dang_giu`, `con_phai_giao`, `trang_thai_yeu_cau`, `giao_duoc_theo_cum`,
  `tao_yeu_cau` (kẹp giao được), `huy_yeu_cau` (cho huỷ khi chuyến đã huỷ), `gui_yeu_cau_xuat_kho`
  (kiểm tồn), `ghi_ket_qua` (tự lập yêu cầu nhập trả về), `kho_da_ghi_so_tra_hang` (hook).
- `routers/kho_voucher.post_voucher`: gọi hook khi phiếu nhập thuộc yêu cầu có `delivery_trip_id`.
- `services/don_hang_tien_do.py` + `GET /api/orders/{id}/tien-do`: mỗi cụm {đặt, SX %, bước hiện
  tại, dự kiến xong, lệnh, kho đề nghị/đã nhận, đã giao, đang giữ, giao được}; cấp đơn: 6 bước,
  trễ so hạn cam kết + lý do; danh sách yêu cầu kèm chuyến.
- `OrderService.cancel` gọi chặn huỷ.

## Frontend

- `DonHangBanPage`: thanh 6 bước (Chốt · Cọc · Sản xuất · Nhập kho · Giao hàng · Hóa đơn), mini bar
  + tóm tắt, dòng cảnh báo trễ; bấm SX / Nhập kho / Giao ⇒ thanh xếp chồng từng sản phẩm. Gỡ khối
  Giao hàng cũ phía trên; bước Giao hàng = danh sách yêu cầu (trạng thái, chuyến, in phiếu, sửa/huỷ
  khi chưa có chuyến) + form tạo yêu cầu kẹp giao được.
- `GiaoHangPage`: đổi kế hoạch / huỷ chuyến cho chuyến chưa lấy hàng; bỏ "Kho đã nhận lại", hiện
  "chờ kho nhận lại" / "kho đã nhận lại".
- `DeliveryNotePrint` theo yêu cầu.

## Xác minh

pytest nhắm file giao hàng + test mới; `npx tsc`; vitest file đụng; restart BE; đi lại luồng thật
trên trình duyệt: tạo yêu cầu (bị kẹp) → lên chuyến → xuất kho → giao thiếu → thủ kho nhận lại →
giao được tăng lại.
