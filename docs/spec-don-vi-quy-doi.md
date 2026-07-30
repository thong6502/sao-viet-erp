# Đơn vị & quy đổi — module dùng chung

Bảng khoán của xưởng ghi đơn giá theo **m²** (cán/phủ), **tấn** (cắt giấy), **con** (bế), **cuốn**
(đóng sách). Lệnh sản xuất lại đếm **tờ**. Hai bên nói hai đơn vị khác nhau nên không ai nhân ra
tiền được — đó là lý do module này tồn tại. Nó cũng là chỗ cho Kho và Mua hàng dùng về sau (nhập
giấy cân **kg**, thẻ kho đếm **tờ**, NCC báo giá **đ/kg**).

Trước module này, quy đổi bị làm rời rạc ở **4 chỗ**, mỗi chỗ một kiểu: `lsx_cong_doan.he_so_quy_doi`
(tờ→con) · `material.don_vi_phu + he_so_quy_doi` · `stock_request_lines.don_vi_phu + he_so_quy_doi` ·
`basis_qty()` 12 trục của tính giá. Nhiều nguồn hệ số thì sớm muộn lệch nhau, mà lệch ở đây là lệch
**tiền**.

Màn khai: `Cấu hình danh mục → Đơn vị & quy đổi`. Bảng: `don_vi_do` (xem `docs/DB_SCHEMA.md`).
Code: `services/quy_doi_service.py` (hàm THUẦN, không đụng DB — caller nạp danh mục rồi truyền vào).

---

## 1. Hai loại quy đổi — tách rời vì bản chất khác nhau

**Cùng họ — thuần số học.** `doi()`: m² ↔ cm², kg ↔ tấn, ram ↔ tờ. Đúng ở mọi nơi mọi lúc.

**Khác họ — phải có QUY CÁCH của lệnh.** Câu *"1 tờ bằng mấy kg?"* **không có đáp án chung**: tờ
65×86 Ford 70 là 0,039 kg, tờ 79×109 Couché 300 là 0,258 kg. Phải biết khổ + định lượng.

## 2. Mô hình hệ số: một cột, không bảng cặp

Mỗi đơn vị thuộc một **họ quy đổi** (`ho`) và khai `he_so_goc` = có bao nhiêu đơn vị GỐC của họ
trong 1 đơn vị này. Đổi A→B cùng họ = `× he_so_goc(A) / he_so_goc(B)`.

| Họ | Đơn vị (hệ số) |
|---|---|
| `dien_tich` | cm² (1) · m² (10.000) |
| `khoi_luong` | kg (1) · tấn (1.000) · g (0,001) |
| `do_dai` | mét (1) · mm (0,001) |
| `to` | tờ (1) · ram (500) |
| `thanh_pham` | cái (1) · con (1) · cuốn (1) · bộ (1) · hộp (1) |
| `kem` · `bai` · `luot` · `thung` | mỗi họ một đơn vị gốc |

**Vì sao cái · con · cuốn · hộp CHUNG một họ:** bước lệnh gọi đơn vị là `cai`, còn bảng khoán của tổ
gọi "cuốn" (sách) / "hộp" (gỡ hàng) — nhưng đều là **một thành phẩm được đếm**. Tách thành các họ
riêng thì bước "vào keo" (1.000 `cai`) vĩnh viễn không khớp đơn giá 700 đ/cuốn. Đã vỡ thật khi thử.

**Khác họ ⇒ KHÔNG đổi bằng hệ số.** Đây là chốt chống lỗi âm thầm: máy không bao giờ tưởng 1 tờ
bằng 1 con vì hai họ khác nhau.

## 3. Ba cầu qua họ khác (cần quy cách lệnh)

| Cầu | Cần biết | Lấy từ | Dùng cho |
|---|---|---|---|
| tờ → cm² | khổ tờ in | `lsx.quy_cach_json.kho_in_dai/rong` | cán · phủ UV · bồi |
| tờ → kg | khổ + định lượng | thêm `gsm` | tổ cắt (đ/tấn) · kho giấy |
| tờ → cái | con/tờ | `so_con` | bế · xén |

Cầu luôn nhả ra **đơn vị GỐC của họ đích** (cm² · kg · cái), rồi `doi()` đưa tiếp về đơn vị người ta
hỏi (m², tấn). Nhờ vậy thêm đơn vị mới trong họ không phải sửa cầu.

**CỐ Ý không có cầu "con → cuốn ÷ số tay".** Nghe hợp lý nhưng sai bản chất: bước lệnh đếm `cai`
nghĩa là đếm THÀNH PHẨM (1.000 cuốn sách), chia thêm số tay là ra 200 cuốn — sai 5 lần. Số tay chỉ
liên quan tới TỜ IN, đã xử ở `so_to_per_sp` của engine tính giá. Có test canh cầu này khỏi mọc lại.

## 4. Ba quy tắc bắt buộc

1. **Đổi xong phải khoe cách tính**: `241 tờ × 86 cm × 65 cm = 1.347.190 cm² = 134,72 m²`. Người đọc
   kiểm được bằng mắt; số sai thì biết sai ở đâu.
2. **Thiếu biến thì nói THIẾU GÌ, không đoán**: *"Lệnh chưa có định lượng giấy (g/m²) nên không đổi
   được tờ → kg."* Số đoán ra chảy thẳng vào tiền khoán và tồn kho.
3. **Hệ số là tiền**: sửa hệ số ghi `hieu_luc_tu` + AuditLog; khai lệch chuẩn vật lý (1 tấn = 900 kg)
   thì **nhắc đỏ nhưng không chặn** — chủ đã chốt "tất cả khai được".

## 5. Tra cứu theo CẢ mã lẫn tên

`don_vi_map()` đánh chỉ mục cả `ma` ("to") lẫn `ten` ("tờ"), vì hai nơi gọi khác nhau: bảng đơn giá
khoán lưu **chữ hiển thị** người dùng gõ ("m²" — chốt "đơn vị gõ tự do"), bước lệnh dùng **mã**.
Chỉ tra theo mã thì đơn giá 150 đ/m² vĩnh viễn báo *"chưa khai đơn vị"*. Mã luôn thắng tên khi trùng.

## 6. Ai đang dùng

- **Khoán ở Kế hoạch SX** — `lsx_service._khoan_derived()`: SL bước → đơn vị đơn giá → tiền dự kiến.
  Xem `docs/spec-luong.md` mục "Khoán theo đầu việc".
- Kho / Mua hàng: **chưa nối** (module Kho hiện có `material.don_vi_phu` riêng).

## 7. Nợ đã biết — đừng tưởng đã xong

Ba chỗ dưới đây vẫn giữ hệ số riêng, CHƯA hợp nhất vào module. Cả ba **đang chạy đúng và có test
bao**, nên đập ra để nhồi vào module là cách nhanh nhất làm vỡ tính giá — hợp nhất là lát riêng:

- `basis_qty()` — 12 trục quy đổi của engine tính giá (tài liệu: `docs/don-vi-tinh-gia-cong-doan.md`).
- `lsx_cong_doan.he_so_quy_doi` — tờ→con của bước bế (1 tờ → 99 con).
- `material.don_vi_phu` + `stock_request_lines.don_vi_phu` — quy đổi theo TỪNG mặt hàng ("1 thùng keo
  UV = 3 kg" khác "1 thùng mực = ? kg"). Loại này **không thuộc** danh mục chung, nhưng hai bảng đang
  khai trùng nhau thì nên gộp.
