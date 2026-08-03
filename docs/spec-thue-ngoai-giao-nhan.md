# SPEC — THUÊ NGOÀI: GHI NHẬN GIAO – NHẬN THỰC TẾ

> Bước gia công ngoài hiện **chỉ có sổ dự kiến**, không trường nào ghi *đã xảy ra*. Hàng ra khỏi
> cổng không có tên người: lúc trễ không truy được, lúc thiếu không ai nhận.
> Anh em với `spec-cong-doan.md`, `spec-bai-ghep-dag.md`.

---

## 1. Vấn đề

Khối gia công ngoài của một bước lệnh đang có: `nha_cung_cap`, `sl_gui`, `ngay_gui_dk`,
`ngay_nhan_dk`, `van_chuyen_ngay`, `gia_cong_ngay`, `hao_hut_cho_phep`, `don_gia_gia_cong`,
`yeu_cau_ky_thuat`. **Toàn bộ là kế hoạch.**

Có sẵn đúng một cột `nguoi_giao_nhan_id`, chưa từng lên UI. Và một cột thì không tả nổi nghiệp vụ,
vì **giao và nhận là hai sự kiện**: khác ngày, khác người, khác số lượng.

Gửi 1.050 tờ đi cán màng, hai hôm sau nhận về 1.032 — 18 tờ đó là hao trong định mức hay bên kia
làm hỏng? Không có chỗ ghi thì không có gì để đối chiếu với `hao_hut_cho_phep`.

---

## 2. Quyết định nghiệp vụ đã chốt

| Câu hỏi | Trả lời |
|---|---|
| Một bước có gửi làm **nhiều chuyến** không? | **Không** → ghi thẳng vào bước, không đẻ bảng |
| Người giao/nhận là ai? | **Nhân viên hệ thống, có tài khoản** → FK `users`, không gõ tên tự do |
| Ai được bấm xác nhận? | **Ai có quyền sửa lệnh** → không thêm bit quyền, truy trách nhiệm bằng AuditLog |

---

## 3. Mô hình dữ liệu

`lsx_cong_doan` — **rename 1 cột + thêm 5 cột**. Không bảng mới.

| Field | Kiểu | Mô tả |
|---|---|---|
| `nguoi_giao_id` | int FK `users` | **rename** từ `nguoi_giao_nhan_id` — ai mang hàng ra cổng |
| `giao_luc` | datetime | Ngày giờ giao **thực** |
| `sl_giao_thuc` | numeric | Số **thực** gửi |
| `nguoi_nhan_id` | int FK `users` | Ai nhận hàng về |
| `nhan_luc` | datetime | Ngày giờ nhận **thực** |
| `sl_nhan_thuc` | numeric | Số **thực** nhận |

Rename an toàn: cột cũ chưa bao giờ lên UI nên chắc chắn toàn NULL. Thêm cột thứ ba rồi để cột cũ
chết là tệ hơn.

### 3.1 KHÔNG thêm gì nữa

| Thứ | Vì sao không |
|---|---|
| Cột số hỏng / thiếu | Dẫn xuất `= sl_giao_thuc − sl_nhan_thuc` |
| Cột trạng thái | Dẫn xuất (xem 3.2) |
| Bảng nhiều chuyến | Đã chốt: không gửi nhiều chuyến |
| Cột tiền gia công thực | Dẫn xuất `= sl_nhan_thuc × don_gia_gia_cong` |

### 3.2 Trạng thái là dẫn xuất

| Điều kiện | Trạng thái |
|---|---|
| `giao_luc` trống | **Chưa gửi** |
| có `giao_luc`, chưa `nhan_luc` | **Đang ở ngoài** |
| đủ hai | **Đã về** |

---

## 4. Cửa ghi riêng — điểm sống còn

```
POST /api/lsx/{lsx_id}/buoc/{buoc_id}/giao-nhan
```

**Không đi qua guard** *"Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi sửa"*.

Giao hàng ra ngoài xảy ra **lúc lệnh đang chạy**, tức sau khi đã lập kế hoạch — mà cả `update` lẫn
`replace_routing` đều chặn cứng ở trạng thái đó. Nhét 6 trường này vào `LsxBuocIn` là **ghi không
nổi đúng lúc cần ghi nhất**, hoặc tệ hơn: bắt kế hoạch gỡ lịch cả lệnh chỉ để ghi một dòng
*"đã giao 1.050 tờ lúc 14h"*.

Đây là ranh giới đã chốt của dự án: **màn lệnh nháp là CẤU HÌNH, lệnh đang chạy là THỰC THI** —
hai thứ không dùng chung cửa ghi.

### 4.1 Quyền và nhật ký

- Quyền: tái dùng quyền sửa lệnh sẵn có. Không thêm vai, không thêm bit.
- Mỗi lần xác nhận ghi `AuditLog`: action `lsx_gia_cong_giao` / `lsx_gia_cong_nhan`,
  `target = lsx_cong_doan:{id}`, detail có **tên người + số lượng**.
- Sửa lại sau đó cũng ghi nhật ký, **không xoá vết cũ** — đó là chỗ truy trách nhiệm.

---

## 5. Luồng UI

### 5.1 Lệnh còn nháp

Kế hoạch khai dự kiến như hiện tại: nhà gia công, SL gửi, ngày gửi/nhận, hao cho phép, đơn giá.
Không đổi gì.

### 5.2 Tới ngày gửi, lệnh đã phát hành

Drawer bước → khối **Thực tế giao – nhận** (ngay dưới khối Gia công ngoài hiện có) →
nút **[Xác nhận đã giao]** → mini-form **đã điền sẵn**:

| Ô | Điền sẵn |
|---|---|
| Người giao | mình đang đăng nhập |
| Giờ giao | bây giờ |
| SL gửi | số gửi dự kiến |

Khác thì sửa, không thì bấm Lưu — **hai click**.

### 5.3 Bước đổi trạng thái ngay

Trên bảng danh sách và trên node DAG hiện badge *"Đang ở ngoài · gửi 30/7 · hẹn về 1/8"*.

Bấm badge → mở drawer **neo thẳng tới khối giao–nhận** (dùng lại cơ chế neo `sec-` sẵn có trong
drawer). Badge chỉ để **nhìn và nhảy** — một cửa ghi duy nhất, không đẻ đường ghi thứ hai.

### 5.4 Hàng về

**[Xác nhận đã nhận]** — điền sẵn SL = số đã giao. Người nhận sửa xuống 1.032 nếu thiếu → hệ nói
ngay tại chỗ: *"Hụt 18 tờ, định mức cho phép 10"*, và tiền gia công thực tự tính lại theo số nhận.

### 5.5 Sau khi đã về

Hai nút thu thành một dòng tóm tắt:

> *Anh A giao 1.050 lúc 30/7 14:20 · Chị B nhận 1.032 lúc 1/8 09:10*

kèm nút **[Sửa]** nhỏ.

---

## 6. Tín hiệu — máy nêu, người quyết

| Điều kiện | Nhãn |
|---|---|
| Quá `ngay_nhan_dk` mà chưa có `nhan_luc` | **"Đang ở ngoài, quá hạn N ngày"** (đỏ) |
| `sl_giao_thuc − sl_nhan_thuc` > `hao_hut_cho_phep` | **"Hụt 18 tờ, định mức cho phép 10"** |
| Có `nhan_luc` mà trống `giao_luc` | Dữ liệu ngược — nhắc nhẹ |

**Detector *"thuê ngoài thiếu/trễ"* của module Xung đột chuyển sang xét số thực** thay vì ngày dự
kiến. Một bộ luật, không đẻ bộ thứ hai — đúng cái bệnh đang có ở phần cảnh báo routing (BE có
`canh_bao_cua`, FE lại tự viết `loiDong`).

---

## 7. KHÔNG làm

- **Không** đưa nút giao/nhận sang màn Xếp lịch. Điều độ chỉ nhìn trạng thái và bấm link sang
  lệnh. Hai cửa ghi cho cùng một sự kiện là mầm lệch dữ liệu.
- **Không** tạo màn "Theo dõi gia công ngoài" riêng. Gộp vào bước lệnh — đó là chỗ người ta đã ở.

---

## 8. Kèm theo

Rename + thêm cột → phải viết `backend/app/db_migrations.py` **và** cập nhật `docs/DB_SCHEMA.md`
cùng lúc, không thì guard test đỏ.
