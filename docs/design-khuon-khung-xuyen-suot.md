# Thiết kế — Khuôn & khung xuyên suốt, và nhãn loại bước xuyên suốt

> Trạng thái: **ĐÃ CHỐT THIẾT KẾ** (04/09/2026) — chốt trong hội thoại với chủ dự án.
> Kế hoạch thi công: `docs/superpowers/plans/2026-09-04-khuon-khung-xuyen-suot.md`.

## 1. Hai vấn đề được đặt ra

**(1) Nhãn loại bước không đi hết đường.** Người lập kế hoạch gán một bước là *Thuê ngoài*
(ô "Loại bước" trong drawer bước). Chip nhãn chỉ hiện ở màn Kế hoạch, hồ sơ lệnh, sơ đồ DAG,
bài ghép và phiếu công nghệ. Từ Xếp lịch trở đi thì mất: Gantt chỉ có lane tím suy ra từ
**tên nhà cung cấp** (bước gán thuê ngoài mà chưa điền nhà gia công thì rơi lane thường),
bàn tổ chỉ gom lane chứ thẻ không mang nhãn, còn KCS / phiếu yêu cầu kho / 4 tab Theo dõi
sản xuất / bảng theo dõi lệnh thì không có gì.

Nguyên nhân gốc: **nhãn không được truyền đi như một dữ liệu**. Mỗi màn tự suy lại từ một thứ
khác nhau — chỗ đọc `loai_buoc`, chỗ đọc `nha_cung_cap`, chỗ không đọc gì. Ba cách suy, ba kết quả.

**(2) Khuôn/khung không thông từ tính giá tới kết thúc lệnh.** Ở phiếu tính giá nó chỉ là một
**ô tiền gõ tay** (`phieu_thanh_pham.phi_khuon`), quy ước ngầm "để trống = dùng dao cũ" nên không
phân biệt được *dùng dao cũ* với *quên nhập*. Ở lệnh sản xuất nó là một **con dao có mã/kệ/tình
trạng** (`lsx_cong_doan.khuon_be_id`), nhưng dữ liệu dao **chỉ được truyền vào drawer bước** — đóng
drawer là bảng công đoạn bên ngoài cũng không thấy gì. Ra tới xếp lịch, phiếu công nghệ, bàn tổ,
theo dõi thì hoàn toàn không có. Hai đường sống song song, không chỗ nào đối chiếu.

## 2. Quyết định của chủ dự án

| # | Quyết định |
|---|---|
| Đ1 | Nhãn gán ở Kế hoạch phải **đi theo bước tới mọi chỗ bước đó xuất hiện**, cho tới khi lệnh hoàn thành. Không phải icon, không phải màu lane. |
| Đ2 | **Khung lụa cũng là đồ lưu kho dùng lại** như khuôn bế → đưa vào chung danh mục. |
| Đ3 | Đổi tên module danh mục thành **"Khuôn & khung"**, thêm ô **phân loại**. |
| Đ4 | **KHÔNG** dùng ngày dự kiến có khuôn để chặn xếp lịch. |
| Đ5 | Thay vào đó: lệnh phát hành xuống xưởng thì phải **nhận đủ khuôn/khung tương ứng** — một **ô tích "đã nhận"** ở bàn tổ. |
| Đ6 | Ngày làm khuôn để **thợ chủ động vào module sửa**; hệ thống chỉ chở thông tin, không đoán, không chặn. |

Giả định đã nêu và chủ dự án không bác: **dao chưa về vẫn cho phát hành lệnh** — vì lệnh còn nhiều
bước chạy trước bế, chặn cả lệnh là giam luôn phần in.

## 3. Nguyên tắc chung cho cả hai chuyện

Thuộc tính của bước khai **một lần** ở nơi có thẩm quyền, rồi **đi theo bước** như một cái chip,
hiện ở mọi màn có mặt bước đó. Màn sau **chỉ đọc và hiện**, không hỏi lại, và tuyệt đối **không tự
suy diễn lại từ dữ liệu khác**.

Hệ quả kỹ thuật: mọi API trả về danh sách bước phải kèm `loai_buoc` + `nha_cung_cap` + khối `khuon`;
frontend có **đúng một** component chip dùng chung, cắm vào mọi màn.

## 4. Danh mục — nền của mọi thứ

### 4.1. Một bộ mã loại dụng cụ DUY NHẤT

Hiện có hai danh sách rời nhau và **đang lệch**:

- `cong_doan.TOOLING_TYPE` = `khuon_be` · `khuon_ep` · `khung_lua`
- `khuon_be.LOAI_KHUON` = `khuon_be` · `khuon_ep`

Bước khung lụa vì thế mở ô chọn ra **rỗng**, bấm "làm dao mới" thì service **ném 400** (loại không
hợp lệ). Chốt: **một hằng số duy nhất** khai ở `models/khuon_be.py`, `cong_doan.py` import lại —
để không bao giờ lệch được nữa.

Bộ mã chốt (5 giá trị):

| Mã | Nhãn |
|---|---|
| `khuon_be` | Khuôn bế |
| `khuon_ep` | Khuôn ép nhũ |
| `khuon_dap_noi` | Khuôn dập nổi |
| `khung_lua` | Khung lụa |
| `khac` | Khác |

### 4.2. Đổi tên module

Nhãn hiển thị **"Khuôn & khung"** ở: cấu hình danh mục (`CFG_KHUON_BE.title`), Sidebar, sổ đăng ký
danh mục backend.

⚠️ **GIỮ NGUYÊN** chuỗi `khuon_be` ở `moduleQuyen`, `prefix` (`/api/khuon-be`), `nhatKyLoai` và tên
bảng. Chuỗi đó đang nằm trong `role_permissions` của DB thật — đổi là mọi vai mất sạch quyền màn này.

## 5. Luồng khuôn/khung — đầu tới cuối

```
Danh mục Công đoạn      → bước này cần dụng cụ loại gì (cờ nguồn, khai một lần)
   ↓
Phiếu tính giá          → "có sẵn hay làm mới?" (làm mới ⇒ mở ô tiền + ngày dự kiến)
   ↓
Chuyển sang Lệnh SX     → ý định của sale đi theo bước
   ↓
Kế hoạch                → trỏ vào CON DAO CỤ THỂ, hoặc đặt làm dao mới
                          + cảnh báo nếu lệch ý định của sale
   ↓
Cửa "Sẵn sàng lập KH"   → bước cần dụng cụ mà chưa trỏ dao ⇒ CHẶN
   ↓
Xếp lịch                → TỰ DO, chỉ mang chip (Đ4)
   ↓
Phát hành               → snapshot dao vào công việc của tổ
   ↓
Phiếu công nghệ         → in MÃ DAO + SỐ KỆ ở dòng bước
   ↓
Bàn tổ                  → tích "đã nhận khuôn" ⇒ mới bấm Bắt đầu được (Đ5)
   ↓
Đóng bước               → tích "đã trả khuôn về kệ" (không chặn)
   ↓
Kết thúc lệnh           → snapshot dao là VẾT: lệnh nào đã dùng dao nào
```

### 5.1. Tính giá — hỏi đúng một câu

Bước nào công đoạn có cờ cần dụng cụ thì khối "Phí khuôn" hiện thêm một lựa chọn hai nhánh:

- **Dùng dao có sẵn** → 0đ, không hỏi thêm.
- **Làm dao mới** → mở ô tiền (đang có) + ô **ngày dự kiến có dao**.

Chưa chọn nhánh nào = **chưa trả lời**, khác hẳn với "đã trả lời là có sẵn". Đây là thay đổi nhỏ
nhưng gỡ đứt gãy lớn nhất: kế hoạch đọc được *ý định của sale* thay vì đoán từ một ô tiền trống.

### 5.2. Kế hoạch — chốt dao thật + cảnh báo lệch ý định

Người kế hoạch trỏ vào con dao cụ thể trong kho, hoặc bấm đặt làm dao mới (đẻ dòng dao ở tình trạng
*đang đặt làm* + ngày có dao). Cả hai đường đã có sẵn.

Thêm: khi ý định của sale **lệch** với việc kế hoạch thực làm — sale báo *có sẵn* mà kế hoạch phải
đặt mới, hoặc ngược lại — hiện một dòng nhắc ngay tại bước. **Máy chỉ nhắc, người quyết** báo lại
sale hay xưởng chịu; nhưng phải nhắc, vì đó là tiền đã trót báo cho khách.

### 5.3. Cửa "Sẵn sàng lập kế hoạch"

Thêm mã thiếu `thieu_khuon`: bước có cờ cần dụng cụ mà `khuon_be_id` còn trống. Đứng ngang hàng với
`thieu_ncc` (thiếu nhà gia công) — cùng một danh sách, người dùng không phải học luật mới.

Cửa này **thoả mãn được** kể cả khi dao chưa về: kế hoạch bấm "đặt làm dao mới" là có `khuon_be_id`.
Nó đòi *đã chốt dao nào*, không đòi *dao đã nằm trên kệ*.

### 5.4. Bàn tổ — chỗ chặn thật DUY NHẤT

Thẻ việc của bước cần dụng cụ có ô tích **"Đã nhận khuôn KB-0123 · kệ A3"**. Tích = dao đang trên
bàn. Ghi ai tích, lúc nào. Chưa tích thì **nút Bắt đầu không bấm được**.

Đi theo đúng khuôn mẫu đã có của `xac_nhan_vat_tu` (§10.1 module Thực hiện sản xuất): tổ trưởng của
đúng tổ mới được tích, ghi audit, một công việc tích một lần.

Kèm ô **"đã trả khuôn về kệ"** lúc đóng bước — **không chặn gì cả**. Không có nó thì dao rời kệ xong
hệ thống mất dấu, lần sau tìm lại phải đi hỏi từng tổ, mà đó đúng là việc kho dao sinh ra để khỏi phải làm.

## 6. Chip — hợp đồng hiển thị

Hai chip, cùng chỗ (cạnh tên bước), cùng kiểu, mọi màn.

**Chip loại bước** — hiện khi `loai_buoc = "thue_ngoai"`, **không phụ thuộc** đã điền nhà gia công:

| Điều kiện | Nội dung | Sắc |
|---|---|---|
| có nhà gia công | `⇗ Ngoài · <tên nhà gia công>` | trung tính |
| chưa có | `⇗ Ngoài · chưa chọn nơi làm` | cảnh báo |

**Chip khuôn** — hiện khi công đoạn nguồn bật cờ cần dụng cụ:

| Điều kiện | Nội dung | Sắc |
|---|---|---|
| chưa trỏ dao | `🔧 chưa chốt khuôn` | đỏ |
| dao `dang_dung` | `🔧 KB-0123 · kệ A3` | xanh |
| dao `dang_dat_lam` | `🔧 KB-0130 · dự kiến 12/09` | vàng |
| đã tích nhận (bàn tổ) | `🔧 KB-0123 · đã nhận` | xanh đậm |

Danh sách **mọi chỗ** phải có chip (rà theo code, để không sót):

1. Phiếu tính giá — dòng công đoạn
2. Kế hoạch SX — **bảng công đoạn** (hiện đang thiếu chip khuôn)
3. Kế hoạch SX — drawer bước
4. Kế hoạch SX — dải tóm tắt luồng
5. Kế hoạch SX — sơ đồ DAG (thẻ node)
6. Bài ghép — form bước chung + canvas DAG
7. Hồ sơ lệnh
8. **Xếp lịch — bảng dòng + thanh Gantt**
9. **Danh sách vấn đề kế hoạch**
10. Phiếu công nghệ (PDF)
11. **Bảng theo dõi lệnh**
12. **Bàn tổ — thẻ việc + drawer**
13. **KCS**
14. **Phiếu yêu cầu kho**
15. **Theo dõi sản xuất — 4 tab**

In đậm = đang thiếu ít nhất một trong hai chip.

## 7. Cái KHÔNG làm

- **Không** chặn xếp lịch theo ngày dự kiến có khuôn (Đ4).
- **Không** chặn phát hành lệnh khi dao chưa về.
- **Không** ràng buộc "một dao không chạy hai chỗ cùng lúc" — đã cân nhắc, để sau nếu xưởng gặp thật.
- **Không** đổi tên bảng / mã quyền / prefix API của danh mục (§4.2).
- **Không** đụng tới `plate_die_rates` (bảng đơn giá kẽm & khuôn) — nó là di sản hệ tính giá đời cũ,
  không engine nào đang tra. Dọn nó là việc riêng, không thuộc phạm vi này.
