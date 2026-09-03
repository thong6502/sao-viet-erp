# Nhãn loại bước xuyên suốt + Khuôn & khung theo công đoạn — Thiết kế

**Ngày chốt:** 04/09/2026
**Phạm vi:** Danh mục Khuôn · Phiếu tính giá · Kế hoạch SX (lệnh) · Xếp lịch 2 · Phát hành SX ·
Thực hiện SX (bàn tổ) · KCS · Yêu cầu kho · Theo dõi sản xuất · Phiếu công nghệ · Bảng theo dõi.

---

## 1. Vấn đề

Hai thuộc tính của một bước sản xuất được khai ở màn Kế hoạch rồi **biến mất** trên đường đi xuống
xưởng:

1. **Loại bước** (Máy / Tổ / Thuê ngoài). Chip nhãn chỉ sống ở 5 màn đầu (bảng công đoạn, dải luồng,
   sơ đồ DAG, bài ghép, hồ sơ lệnh, phiếu công nghệ). Từ Xếp lịch trở đi mất hẳn — và chỗ còn dấu
   vết thì lại **suy ngược từ tên nhà cung cấp** (`Xl2Gantt.tsx:967`), nên bước đã gán Thuê ngoài mà
   chưa điền nơi gia công rơi về lane thường.
2. **Khuôn / khung** của bước. Dữ liệu khuôn chỉ được truyền vào *drawer* của bước
   (`LsxRoutingTable.tsx:942`); đóng drawer thì ngay bảng công đoạn bên ngoài cũng không biết bước
   bế đã chốt dao chưa. Xuống xưởng thì phiếu công nghệ in "Số kẽm" nhưng **không in mã dao lẫn số
   kệ** — trong khi thợ cầm tờ giấy đó đi lấy dao.

Hệ quả nghiệp vụ: luật "bế phải có khuôn mới làm được" hiện **không được hệ thống bảo vệ ở bất kỳ
điểm nào**.

## 2. Nguyên tắc chung

> Thuộc tính của bước khai **một lần**, rồi đi theo bước như một **chip** và hiện ở **mọi màn bước
> đó xuất hiện**, cho tới khi lệnh hoàn thành. Màn hạ nguồn chỉ **đọc và hiện**, không hỏi lại,
> không tự suy diễn lại từ dữ liệu khác.

Kéo theo hai hệ quả kỹ thuật bắt buộc:

- Mọi API trả danh sách bước/công việc phải **mang theo** `loai_buoc` + `nha_cung_cap` + khối khuôn.
- Frontend dùng **đúng một component chip** cho mỗi loại nhãn, không màn nào tự vẽ lại.

## 3. Nhãn loại bước

**Nội dung chip** (component `ChipLoaiBuoc`):

| Loại bước | Chữ trên chip | Tone |
|---|---|---|
| `may` | `Máy` | may |
| `to` | `Tổ` | to |
| `thue_ngoai` + có NCC | `Ngoài · <tên NCC>` | ngoai |
| `thue_ngoai` + chưa có NCC | `Ngoài · chưa chọn nơi làm` | canhbao |

Điều kiện hiện chip **chỉ là** `loai_buoc`. Không phụ thuộc đã điền nhà gia công hay chưa — chưa
điền thì chip đổi tone cảnh báo, dữ liệu thiếu tự lộ ra thay vì im lặng.

**Mọi chỗ bước xuất hiện** (đích đến của chip):

| # | Màn / đầu ra | Hiện trạng |
|---|---|---|
| 1 | Phiếu tính giá — dòng công đoạn | chưa có |
| 2 | Kế hoạch — bảng công đoạn | **có** (mẫu gốc) |
| 3 | Kế hoạch — dải luồng + sơ đồ DAG | **có** |
| 4 | Bài ghép — bước chung + DAG | **có** |
| 5 | Hồ sơ lệnh | **có** |
| 6 | Phiếu công nghệ (PDF) | **có** |
| 7 | Xếp lịch 2 — Gantt + bảng dòng | suy sai từ NCC → thay bằng chip |
| 8 | Thực hiện SX — thẻ việc bàn tổ | chưa có |
| 9 | KCS — thẻ / drawer | chưa có |
| 10 | Yêu cầu kho | chưa có |
| 11 | Theo dõi SX — Kanban chip · Theo máy · Theo ca | chưa có |
| 12 | Bảng theo dõi lệnh | chưa có |

Gantt của Theo dõi SX là **một dòng một LỆNH**, không phải một bước — không áp chip.

## 4. Khuôn & khung

### 4.1 Đổi tên module

Danh mục nay chứa cả **khung lụa**, nên nhan đề màn + mục sidebar đổi thành **"Khuôn & khung"**.

⚠️ **Chỉ đổi nhãn hiển thị.** Tên bảng `khuon_be`, `moduleQuyen: "khuon_be"`, `prefix
/api/khuon-be`, `nhatKyLoai` **giữ nguyên** — chuỗi `khuon_be` đang nằm trong `role_permissions`
của DB thật, đổi là mọi vai mất sạch quyền màn này.

### 4.2 Phân loại

`khuon_be.loai` thêm giá trị `khung_lua`. Bộ mã **phải trùng khít** với `cong_doan.TOOLING_TYPE`
(`khuon_be` · `khuon_ep` · `khung_lua`) — ô chọn dao ở bước lệnh lọc bằng phép so thẳng hai giá
trị, lệch một mã là lọc ra rỗng. Đây chính là lỗi khung lụa đang mắc: công đoạn khai được loại đó
nhưng kho không nhận, nên bước lụa mở ô chọn ra rỗng và bấm "làm mới" thì service ném 400.

Nhãn: `Khuôn bế` · `Khuôn ép nhũ / dập nổi` · `Khung lụa`.

### 4.3 Luồng đầu-cuối

```
Danh mục Công đoạn      bước này cần dụng cụ loại gì  (requires_tooling + tooling_type)
        ↓
Phiếu tính giá          "có sẵn" hay "làm mới"?  → làm mới thì mở ô tiền + ngày dự kiến
        ↓
Kế hoạch SX             trỏ con dao cụ thể / bấm đặt làm dao mới
                        nhắc nếu LỆCH ý định của sale
        ↓
Cửa Sẵn sàng lập KH     bước cần dụng cụ mà chưa trỏ dao → thiếu, CHẶN
        ↓
Xếp lịch                TỰ DO — chỉ mang chip, không ràng buộc ngày
        ↓
Phiếu công nghệ         in mã dao + số kệ ở dòng bước
        ↓
Bàn tổ                  tích "Đã nhận khuôn" → mới bấm Bắt đầu được   ← ĐIỂM CHẶN DUY NHẤT
        ↓
Đóng bước               tích "Đã trả khuôn về kệ" (không chặn)
```

**Quyết định đã chốt:** *không* dùng ngày dự kiến có khuôn để chặn xếp lịch. Ngày đó không đủ tin
để chặn ai. Thay vào đó là **xác nhận của người có dao trong tay**, đặt tại điểm giao. Ngày làm
khuôn để **thợ tự vào module Khuôn & khung sửa**; sửa xong chip vàng ở mọi màn đổi theo. Máy không
đoán, không suy, không chặn — chỉ chở thông tin đi.

**Quyết định đã chốt:** dao chưa về **vẫn cho phát hành lệnh** — lệnh còn nhiều bước chạy trước bế,
chặn cả lệnh là giam luôn phần in.

### 4.4 Chip khuôn

Component `ChipKhuon`, ba trạng thái:

| Trạng thái | Chữ trên chip | Tone |
|---|---|---|
| bước cần dụng cụ, chưa trỏ dao | `🔧 chưa chốt khuôn` | đỏ |
| dao `dang_dung` | `🔧 KB-0123 · kệ A3` | xanh |
| dao `dang_dat_lam` | `🔧 KB-0130 · dự kiến 12/09` | vàng |
| (bàn tổ, sau khi tích nhận) | `🔧 KB-0123 · đã nhận` | xanh đậm |

Bước không có `requires_tooling` → không chip. Hiện ở **cùng bộ màn** của §3, cộng thêm bảng công
đoạn ở Kế hoạch (hiện chỉ có trong drawer).

### 4.5 Ý định của sale và cảnh báo lệch

Phiếu tính giá hiện chỉ có ô tiền, quy ước ngầm "để trống = dùng dao cũ" — **không phân biệt được
"dùng dao cũ" với "quên nhập"**. Thêm ô chọn tường minh:

- `khuon_nguon = 'co_san'` → 0đ, không hỏi thêm, engine **không cảnh báo**.
- `khuon_nguon = 'lam_moi'` → mở ô `phi_khuon` (đã có) + ô `khuon_ngay_du_kien` (mới).
- `khuon_nguon = NULL` (chưa chọn) → engine giữ cảnh báo "chưa khai phí khuôn" như hiện nay.

Ý định này **chép sang bước của lệnh** lúc dựng lệnh. Màn Kế hoạch hiện một dòng đọc được:
*"Sale báo: làm khuôn mới, 1.200.000đ, dự kiến 12/09"*.

**Cảnh báo lệch** (nhắc, KHÔNG chặn — máy chỉ ghi nhận, người quyết):

- sale `co_san` mà dao đã trỏ có `tinh_trang = 'dang_dat_lam'`
  → *"Sale báo dùng khuôn có sẵn, nhưng khuôn này đang đặt làm."*
- sale `lam_moi` (phí > 0) mà dao đã trỏ có `tinh_trang = 'dang_dung'`
  → *"Sale đã tính X đồng tiền làm khuôn, nhưng bước này dùng khuôn có sẵn."*

### 4.6 Cửa "Sẵn sàng lập kế hoạch"

Thêm mã thiếu `thieu_khuon`: bước có `requires_tooling` và `tooling_type` thuộc bộ ba dụng cụ lưu
kho mà `khuon_be_id IS NULL`. Đứng ngang hàng với `thieu_ncc` — cùng một danh sách, người dùng
không phải học luật mới.

⚠️ Chú thích cũ trong `_thieu` ghi *"khuôn ra khỏi lệnh hẳn (mg 0203)"* đã lỗi thời — mg `0205` nối
lại rồi. Phải sửa chú thích cùng lúc, không thì lần sau lại có người gỡ điều kiện này ra.

### 4.7 Nhận / trả khuôn tại bàn tổ

Lệnh phát hành xuống xưởng đi kèm **danh sách phải nhận**: vật tư như hiện nay, cộng khuôn/khung
của từng bước có yêu cầu.

- Thẻ việc có khối khuôn + nút **"Đã nhận khuôn"**. Ghi ai tích, lúc nào.
- **Chưa tích thì `bat_dau` từ chối** — điểm chặn duy nhất của toàn bộ luật này.
- Việc xong: nút **"Đã trả khuôn về kệ"**, không chặn gì. Không có nó thì dao rời kệ xong hệ thống
  mất dấu, lần sau tìm lại phải đi hỏi từng tổ — đúng việc kho dao sinh ra để khỏi phải làm.

Khuôn được **chụp** vào công việc lúc phát hành (như `vat_tu_json`), không tra sống: bàn tổ phải
thấy đúng con dao đã chốt lúc phát hành, kể cả khi kế hoạch đổi dao sau đó.

Một bước tách nhiều **phân đoạn** ⇒ mỗi công việc tích riêng: mỗi lần chạy đều cần dao trên bàn.

### 4.8 Vết dùng dao

`san_xuat_cong_viec.khuon_json` giữ lại mã dao sau khi lệnh xong. Đó là vết trả lời hai câu:
lần sau khách đặt lại thì con dao cũ nằm đâu, và dao đã chạy bao nhiêu lần trước khi mòn.

## 5. Thay đổi dữ liệu

| Bảng | Cột mới | Kiểu | Ý nghĩa |
|---|---|---|---|
| `phieu_thanh_pham` | `khuon_nguon` | `String(10)` null | `co_san` / `lam_moi` / NULL |
| `phieu_thanh_pham` | `khuon_ngay_du_kien` | `Date` null | ngày sale dự kiến có khuôn |
| `lsx_cong_doan` | `khuon_nguon` | `String(10)` null | ý định sale, chép từ phiếu |
| `lsx_cong_doan` | `khuon_phi` | `Numeric(18,2)` NOT NULL default 0 | tiền sale đã tính |
| `san_xuat_cong_viec` | `nha_cung_cap` | `String(255)` null | ảnh chụp cho chip |
| `san_xuat_cong_viec` | `khuon_json` | `JSON` null | ảnh chụp dao lúc phát hành |
| `san_xuat_cong_viec` | `khuon_nhan_luc` | `TIMESTAMPTZ` null | mốc tích "đã nhận" |
| `san_xuat_cong_viec` | `khuon_nhan_by_id` | `Integer` null | ai tích |
| `san_xuat_cong_viec` | `khuon_tra_luc` | `TIMESTAMPTZ` null | mốc tích "đã trả" |

Không cột nào cần migration cho `khuon_be.loai` — nó đã là `String(16)`, chỉ nới **danh sách giá
trị hợp lệ** trong code.

⚠️ Boolean nào thêm sau này phải dùng `server_default` là `false`/`true` Python bool, không phải
`"0"`/`"1"` — chuỗi chạy SQLite nhưng vỡ khi Postgres `create_all` trên DB trắng.

## 6. Ngoài phạm vi

- Không đụng cách engine tính tiền khuôn (vẫn đọc `phi_khuon`, vẫn gộp vào giá vốn).
- Không nối `plate_die_rates` (bảng đơn giá kẽm & khuôn) vào engine — nó là di sản hệ A, để nguyên.
- Không dựng lại nhóm "Công cụ" trong Kế hoạch NVL (đã gỡ mg `0203`).
- Không ràng buộc "một dao không chạy hai chỗ cùng lúc" ở xếp lịch.
