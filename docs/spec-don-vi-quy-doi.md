# Đơn vị & quy đổi — module dùng chung

Bảng khoán của xưởng ghi đơn giá theo **m²** (cán/phủ), **tấn** (cắt giấy), **con** (bế), **cuốn**
(đóng sách). Lệnh sản xuất lại đếm **tờ**. Hai bên nói hai đơn vị khác nhau nên không ai nhân ra
tiền được — đó là lý do module này tồn tại. Nó cũng là chỗ cho Kho và Mua hàng dùng về sau (nhập
giấy cân **kg**, thẻ kho đếm **tờ**, NCC báo giá **đ/kg**).

Trước module này, quy đổi bị làm rời rạc ở **4 chỗ**, mỗi chỗ một kiểu: `lsx_cong_doan.he_so_quy_doi`
(tờ→con) · `material.don_vi_phu + he_so_quy_doi` · `stock_request_lines.don_vi_phu + he_so_quy_doi` ·
`basis_qty()` 12 trục của tính giá.

Màn khai: `Cấu hình danh mục → Đơn vị & quy đổi` — **MỘT chỗ nhập duy nhất**. Bảng liệt kê đơn vị;
mở một đơn vị ra thì cuối drawer là khối **"Quy đổi của \<đơn vị\>"** (`pages/QuyDoiCuaDonVi.tsx`)
liệt kê mọi cặp liên quan, sửa/xoá/thêm ngay tại đó. Không có màn "danh sách cặp" riêng: người ta
nghĩ *"đơn vị tấn đổi ra được gì"*, chứ không nghĩ *"danh sách các cặp"* — và hai mục sidebar tên
gần trùng nhau ("Đơn vị & quy đổi" / "Quy đổi đơn vị") thì không ai đoán được vào đâu làm gì.

Bốn điều khối đó phải giữ:

- **Hai chiều tách bạch, không trộn.** Khối *"Khai ở đây"* = đơn vị này ở vế TRÁI, sửa/xoá/thêm
  ngay. Khối *"Đơn vị khác đổi về X"* = đơn vị này ở vế PHẢI, cặp do đơn vị kia khai → **chỉ đọc**,
  ghi rõ *"khai ở tấn"*, muốn sửa thì mở đơn vị đó. Trộn chung thì mở kg lại thấy "1 g = 0,001 kg"
  nằm giữa danh sách "quy đổi của kg", mà ô sửa đang giữ số theo chiều ngược — đọc một đằng sửa
  một nẻo. Câu luôn in theo chiều ĐÃ KHAI (lật ra chiều ngược thì số thành 0,001, đọc mệt hơn).
- **Công thức soạn bằng đúng trình soạn của Công đoạn** (`FormulaField`, tái dùng với bộ biến
  riêng): chip biến bấm-để-chèn, dịch nghĩa tiếng Việt ngay dưới ô gõ, nút toán tử, mẫu 1-click,
  báo đỏ biến lạ ngay lúc gõ. Ô chữ trơ trọi thì người khai phải nhớ tên biến — không ai nhớ.
- **Mỗi dòng lưu NGAY** khi bấm Lưu, không chờ nút "Lưu thay đổi" của drawer — gộp chung thì sửa ba
  dòng lưu một phát, hỏng một dòng là không biết hai dòng kia ra sao.
- **Tạo đơn vị mới xong thì drawer Ở LẠI** (`moLaiSauKhiTao`) để khai quy đổi tiếp — khối quy đổi
  cần id mới gắn được, đóng phắt là bắt người ta đi tìm lại dòng vừa tạo.
- **Ô "Thử quy đổi"** ngay trong khối: gõ số lượng + khổ + định lượng, thấy liền câu diễn giải.
  Khai công thức mà không thử được thì không ai dám khai.

Bảng: `don_vi_do` + `don_vi_quy_doi` (xem `docs/DB_SCHEMA.md`). Code: `services/quy_doi_service.py`
(hàm THUẦN, không đụng DB — caller nạp danh mục rồi truyền vào).

---

## 1. Mô hình: ba bước, không hơn

> Tạo đơn vị `tấn` · tạo đơn vị `kg` · khai **1 tấn = 1.000 kg**.

Hết. Không có "nhóm", không có "đơn vị chuẩn", không có "hệ số về đơn vị gốc". Hai đơn vị đổi được
cho nhau **khi và chỉ khi** có đường cặp nối chúng.

Bản đầu tiên của module làm theo kiểu "mỗi loại đo có một đơn vị chuẩn, các đơn vị khác khai bằng
bao nhiêu cái chuẩn" — đúng về máy (không mâu thuẫn được, một cột số) nhưng chủ mở form ra không
hiểu đang điền gì: *"cái ô loại đo là cái đéo gì"*. Người ta nghĩ theo CẶP, nên lưu theo cặp.

**Cạnh đi hai chiều.** Khai `1 tấn = 1.000 kg` là đủ để đổi ngược `kg → tấn`. Khai thêm dòng
`kg → tấn` bị chặn (trùng cặp) — hai dòng nói cùng một chuyện thì sớm muộn lệch nhau.

**Cặp chưa khai thẳng thì dò đường.** Hỏi `tấn → g` mà chỉ có `tấn→kg` và `kg→g` thì máy nhân dồn
dọc đường (BFS, ít chặng nhất → sai số nhân dồn ít nhất) và nói rõ đã đi qua đâu:
`2 tấn × 1.000.000 = 2.000.000 g (qua tấn → kg → g)`.

## 2. Chặn cặp mâu thuẫn

Đã có `1 tấn = 1.000 kg` và `1 kg = 1.000 g`; khai thêm `1 tấn = 999.000 g` thì **từ chối lưu**, kèm
câu chỉ thẳng chỗ lệch:

> *Lệch với quy đổi đã khai: theo đường tan → kg → g thì 1 tan = 1.000.000 g, còn bạn đang khai
> 999.000. Sửa lại cho khớp, hoặc sửa cặp cũ trước.*

Chủ chốt **chặn** (2026-07-30) thay vì chỉ cảnh báo: số quy đổi chảy thẳng vào tiền khoán và tồn
kho: lệch mà im lặng thì lúc phát hiện đã trả lương sai mấy tháng. So sánh bằng sai số **tương đối**
(1e-6) vì hệ số trải từ 0,001 tới 1.000.000 — tuyệt đối thì hoặc quá chặt với số nhỏ, hoặc quá lỏng
với số lớn.

Sửa hệ số của một cặp thì bỏ qua CHÍNH nó khi dò đường, không thì nó tự mâu thuẫn với bản cũ của
mình và không sửa nổi.

## 3. Quy đổi ĐỘNG — hệ số là công thức

Câu *"1 tờ bằng mấy kg"* **không có đáp án chung**: tờ 65×86 Ford 70 là 0,039 kg còn tờ 79×109
Couché 300 là 0,258 kg. Nhưng nó **tính được** từ khổ + định lượng, nên vẫn là một dòng khai được —
chỗ điền hệ số nhận công thức thay cho con số:

```
1 tờ = 0,002                        ram     ← số, đúng mọi lúc
1 tờ = dinh_luong * dai * rong      kg      ← ĐỘNG, số ra tuỳ giấy đang chạy
1 tờ = dai * rong                   m²
1 tờ = so_con                       cái
```

Ba dòng động đó trước 2026-07-31 nằm **cứng trong code** (`quy_doi_service.CAU`) nên xưởng không sửa
được; giờ là ba dòng seed, thêm/sửa như mọi dòng khác. Không cần dòng riêng cho tờ → cm²: đi tiếp
bằng cặp `m² = 10.000 cm²` đã khai.

**Biến do NƠI GỌI bơm vào** (`ngu_canh()`), danh mục không tự đoán — đây là chốt 2026-07-31:

| Biến | Nghĩa | Đơn vị |
|---|---|---|
| `dai` · `rong` | khổ của **tờ đang đếm** | m (nhận cả `kho_in_dai/rong` mm của lệnh) |
| `dinh_luong` | định lượng giấy | kg/m² (= gsm ÷ 1.000) |
| `so_con` | số con trên tờ | — |

Tên biến là **vai trò**, không phải tên cột của giấy: tờ **nguyên** (mua về, 79×109) và tờ **in**
(đã pha, 65×86) khác khổ nên khác cân, mà chỉ nơi gọi mới biết bước này đang đếm tờ nào. Mua giấy
đưa khổ nguyên, bước chạy máy đưa khổ in — một dòng khai phục vụ cả hai, diễn giải in rõ đã lấy số
nào. Bộ từ vựng trùng với công thức công đoạn (`thanh_phan_engine`), khỏi hai nghĩa cho một chữ.

**Chiều ngược tự có.** Động hay tĩnh thì kết quả cuối vẫn là MỘT số nhân, nên kg → tờ là chia; đi
vòng vẫn nhân dồn dọc đường như cũ.

**Thiếu biến thì cạnh đó coi như không tồn tại** — thà không đổi được còn hơn đổi bằng số đoán. Máy
dò lại đường với giả định "đủ biến" chỉ để biết mà nói cho đúng: *"Chưa biết định lượng giấy nên
không đổi được tờ → kg"*, thay vì đổ cho người dùng là chưa khai cặp.

**Dòng động KHÔNG bị chặn mâu thuẫn lúc khai**: chưa có giấy nào để thay biến thì không so được với
đường hằng. Kiểm nó là lúc dùng, qua diễn giải. Chặn mâu thuẫn (§2) chỉ áp cho dòng SỐ.

**CỐ Ý không có dòng "con → cuốn ÷ số tay".** Nghe hợp lý nhưng sai bản chất: bước lệnh đếm `cai`
nghĩa là đếm THÀNH PHẨM (1.000 cuốn sách), chia thêm số tay là ra 200 cuốn — sai 5 lần. Số tay chỉ
liên quan tới TỜ IN, đã xử ở `so_to_per_sp` của engine tính giá. Có test canh khỏi mọc lại.

### Ranh giới: đơn vị hay mặt hàng?

| Loại | Ví dụ | Ở đâu |
|---|---|---|
| Hằng, đúng mọi thứ | 1 tấn = 1.000 kg | danh mục đơn vị |
| **Suy ra được** từ thuộc tính hệ thống đã có | 1 tờ = f(khổ, định lượng) kg | danh mục đơn vị, dòng **động** |
| Phải gõ tay riêng từng mặt hàng | 1 thùng keo UV = 3 kg | hồ sơ vật tư (`material.don_vi_phu`) |

Phép thử một câu: **hai người khai hai số khác nhau cho cùng cặp đơn vị mà cả hai đều đúng → nó
thuộc mặt hàng.** "1 tờ mấy kg" tưởng rơi vào ô đó, nhưng không — nó *suy ra được*, chỉ là hệ số
biết tính.

## 4. Hai quy tắc hiển thị

**Đổi xong phải khoe cách tính**: `241 tờ × 86 cm × 65 cm = 1.347.190 cm² = 134,72 m²`. Người đọc
kiểm được bằng mắt; số sai thì biết sai ở đâu.

**Thiếu dữ liệu thì nói THIẾU GÌ, không đoán**: *"Lệnh chưa có định lượng giấy (g/m²) nên không đổi
được tờ → kg."* · *"Chưa khai quy đổi giữa bản kẽm và tờ."* Số đoán ra chảy thẳng vào tiền lương.

Câu quy đổi trên bảng đọc **từ chính dòng đang xem**, vế trái luôn là số nguyên: dòng `m²` ghi
`1 m² = 10.000 cm²`, dòng `cm²` ghi `10.000 cm² = 1 m²` (không phải `1 cm² = 0,0001 m²`), dòng `kg`
ghi `1 kg = 1.000 g · 1.000 kg = 1 tấn`. Trước đó hai dòng khác nhau hiện y hệt một câu nên không
đọc được.

**Không phơi chữ của máy ra cho người dùng.** Cặp quy đổi có mã (`con → cai`) và tên
(`1 con = 1 cái`) đều do server ghép lại từ hai đơn vị + hệ số, nên form ẩn cả ô Mã lẫn ô Tên và
bảng bỏ cột Mã (cờ `autoLabel` của `RebuildCatalogPage`) — bày ra một chuỗi máy sinh rồi bảo người
ta sửa là bắt họ đoán mình đang xem cái gì. Dropdown chọn đơn vị chỉ hiện TÊN (`refNameOnly`): mã
đơn vị hầu hết là chính cái tên bỏ dấu nên "con · con" chỉ tổ rối; nơi mã CÓ nghĩa (`CD-0003 · Cán
màng`, `BRISTOL · Bristol`) vẫn giữ nguyên "mã · tên".

**Đơn vị nghề phải tự giải nghĩa.** Người ngoài nhà in mở danh sách ra thấy `con`, `bài in`, `lượt`
thì không đoán nổi đang đếm gì, nên `_DON_VI_SEED` mang sẵn một câu giải nghĩa đổ vào cột Ghi chú
("con — sản phẩm rời bế/xén ra từ tờ in, 1 tờ ra nhiều con"). Seed chỉ điền vào dòng đang TRỐNG ghi
chú, không đè chữ người dùng tự ghi. Đơn vị ai cũng biết (kg · mét · cm²) để trống — viết thừa cũng
là một kiểu ồn.

## 5. Ai đang dùng

- **Khoán ở Kế hoạch SX** — `lsx_service._khoan_derived()`: SL bước → đơn vị đơn giá → tiền dự kiến.
  Xem `docs/spec-luong.md` mục "Khoán theo đầu việc".
- Kho / Mua hàng: **chưa nối** (module Kho hiện có `material.don_vi_phu` riêng).

## 6. Nợ đã biết — đừng tưởng đã xong

- `basis_qty()` — 12 trục quy đổi của engine tính giá (`docs/don-vi-tinh-gia-cong-doan.md`).
- `lsx_cong_doan.he_so_quy_doi` — tờ→con của bước bế (1 tờ → 99 con).
- `material.don_vi_phu` + `stock_request_lines.don_vi_phu` — quy đổi theo TỪNG mặt hàng ("1 thùng keo
  UV = 3 kg"). Loại này **không thuộc** danh mục chung, nhưng hai bảng đang khai trùng nhau thì nên gộp.
- `don_vi_do.he_so_goc` — cột chết của mô hình cũ, giữ để không mất dữ liệu; xoá được sau khi chắc
  không ai đọc.

Cả ba cái đầu **đang chạy đúng và có test bao**, nên đập ra để nhồi vào module là cách nhanh nhất làm
vỡ tính giá — hợp nhất là lát riêng.
