# Đơn vị tính giá công đoạn

Giải thích 11 **đơn vị tính giá** của công đoạn (màn Cấu hình danh mục → Công đoạn) và cách ra tiền.

Sau khi chọn đơn vị, ô **"Đơn giá / đơn vị"** = tiền cho **1** đơn vị đó (1 tờ / 1 cm² / 1 cái / 1 thùng…).
Máy tự tính **lượng** rồi nhân đơn giá:

```
Tiền công đoạn = đơn_giá × lượng   (+ giá tối thiểu / tiền khuôn nếu có)
```

Ví dụ chung dưới đây: **đơn 10.000 danh thiếp, in 8 con/tờ → 1.250 tờ in**; sách 200 trang × 500 cuốn.

---

## Chia 4 nhóm cho dễ nhớ

### Nhóm 1 — Tính theo TỜ IN (phía máy chạy)

| Đơn vị | Đếm cái gì | Hay dùng cho | Ví dụ |
|---|---|---|---|
| Theo số tờ in | Số tờ giấy chạy qua máy | In offset, cắt xén | 1.250 tờ |
| Theo diện tích tờ in (cm²) | Diện tích 1 tờ × số tờ (1 mặt) | Cán/phủ 1 mặt | 65×86 = 5.590 cm² × 1.250 tờ |
| Theo diện tích (cm²) và số mặt | Diện tích tờ × **số mặt** × số tờ | Cán/phủ/UV 2 mặt | 5.590 × **2 mặt** × 1.250 tờ |

### Nhóm 2 — Tính theo THÀNH PHẨM (sản phẩm cuối)

| Đơn vị | Đếm cái gì | Hay dùng cho | Ví dụ |
|---|---|---|---|
| Theo số lượng thành phẩm | Số sản phẩm cuối | Dán, đánh số, bế theo cái | 10.000 cái |
| Theo diện tích thành phẩm (cm²) | Diện tích 1 sản phẩm × số lượng | Cán/phủ tính theo SP (không phải tờ) | tem 5×8 = 40 cm² × 10.000 |
| Theo số vị trí | Số chỗ gia công × số lượng | Ép kim/dập nổi nhiều chỗ | 2 chỗ × 10.000 = 20.000 vị trí |

### Nhóm 3 — Sách & Đóng gói

| Đơn vị | Đếm cái gì | Hay dùng cho | Ví dụ |
|---|---|---|---|
| Theo số trang sách | Số trang × số cuốn | Vào keo, khâu chỉ, bắt tay | 200 × 500 = 100.000 trang |
| Theo số trang sách chia 4 | (Trang × cuốn) ÷ 4 | Tính theo "tay" (1 tờ gấp 4 trang) | 100.000 ÷ 4 = 25.000 tay |
| Theo bao | Số bao đóng gói | Vô bao, đếm bao | 500 cái/bao → 20 bao |
| Theo thùng | Số thùng | Đóng thùng, bốc xếp | 100 cái/thùng → 100 thùng |

### Nhóm 4 — Khác

| Đơn vị | Nghĩa |
|---|---|
| Khác | Giá **cố định/khoán 1 cục**, không nhân theo lượng (thợ nhập tay). VD 500.000đ/đơn. |

**Chọn nhanh:** máy in/cán → *theo tờ*; cắt/dán/đếm sản phẩm → *theo thành phẩm*; đóng sách →
*theo trang*; đóng gói → *bao/thùng*; khoán → *khác*.

---

## Phụ lục — Công thức `lượng` (engine `routing_engine.basis_qty`)

Ngữ cảnh đơn: `so_to_in_gross` (số tờ in), `so_mat` (số mặt), `dt_to_in_cm2` (dt 1 tờ),
`dt_thanh_pham_cm2` (dt 1 thành phẩm), `so_luong_thanh_pham` (SL), `so_trang`, `so_cuon`,
`so_vi_tri`, `so_bao`, `so_thung`.

| Đơn vị (key) | `lượng` = |
|---|---|
| Theo số tờ in (`per_sheet`) | số tờ in |
| Theo diện tích thành phẩm (`per_finished_area`) | dt_thành_phẩm × SL |
| Theo số lượng thành phẩm (`per_finished_qty`) | SL |
| Theo số trang sách (`per_book_page`) | số trang × số cuốn |
| Theo số vị trí (`per_position`) | số vị trí × SL |
| Theo bao (`per_bag`) | số bao |
| Theo thùng (`per_carton`) | số thùng |
| Theo diện tích (cm²) và số mặt (`per_area_sides`) | dt_tờ × số mặt × số tờ in |
| Theo diện tích tờ in (cm²) (`per_sheet_area`) | dt_tờ × số tờ in |
| Theo số trang sách chia 4 (`per_book_page_q4`) | (số trang × số cuốn) ÷ 4 |
| Khác (`per_other`) | 1 (giá phẳng) |

> **Lưu ý:** bộ 11 đơn vị này thuộc `routing_engine` — **chưa nối vào Báo giá live** (`pricing_engine.py`
> đang chạy dùng danh mục `operations` với 4 đơn vị: tờ / m² / cái / SP). Hiện dùng để chuẩn hoá
> danh mục; khi nối engine mới vào Báo giá thì mỗi công đoạn tự tính theo bảng trên.

---

## Cũng chính bộ này dùng cho LƯƠNG KHOÁN

Bảng đơn giá khoán của tổ (`Lương → Cấu hình lương của tổ`) chọn **một trong các trục trên** ở ô
"Tính theo", để lệnh sản xuất biết đổi SL của bước (tờ / con / kẽm) sang đơn vị của đơn giá (m² / tấn
/ cuốn) rồi ra tiền công dự kiến. Cán / phủ / bồi → *theo diện tích tờ in*; bế → *theo số tờ in*;
đóng cuốn → *theo số lượng thành phẩm*.

Phần quy đổi giữa các đơn vị (1 m² = 10.000 cm², 1 tấn = 1.000 kg, 1 ram = 500 tờ) khai theo CẶP
ở module riêng — xem `docs/spec-don-vi-quy-doi.md`.
