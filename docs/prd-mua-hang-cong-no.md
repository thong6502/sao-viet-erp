# PRD — Mua hàng · Đợt giao · Phiếu chi · Công nợ NCC

**Ngày chốt:** 06/08/2026 · **Phân hệ:** `thu_mua`, `ke_toan`
**Nguồn:** feedback cuộc họp nghiệp vụ 06/08/2026 + rà soát code hiện trạng.

> Doc này mô tả **trạng thái ĐÍCH**. Chỗ nào code lệch doc thì tin code — nhưng phải sửa doc ngay
> lượt đó, đừng để hai bên nói hai chuyện (bệnh cũ của `DINH_MUC_BU_HAO.md`).

---

## 1. Vì sao phải sửa

Ba lỗi có thật trên hệ đang chạy trước ngày chốt:

**(a) GIẤU NỢ với đơn giao nhiều đợt.** `chua_vao_so` chỉ tính khi cả đơn ở `received`
(`accounting_service.py::_no_cua_phieu`). Đơn giao 1/3 đợt vẫn ở `purchased` ⇒ màn Công nợ hiện
**0đ** trong khi đã nợ thật.

**(b) THỪA NỢ khi bấm "Đã nhận hàng" sớm.** Bấm nhận cho cả đơn lúc mới về 1/3 ⇒ ghi nợ đủ 100%.

**(c) NỢ ẢO do phiếu thu.** Tạm ứng 10tr → mua hết 8,5tr → nộp lại 1,5tr:
`outstanding = 10 − (10 − 1,5) = 1,5tr` "còn nợ NCC" trong khi tiền đã về két
(`purchase_service.py::purchase_money`).

**Gốc chung: hệ không có khái niệm "đợt giao".** `purchase_request_lines.received_quantity` là một
con số cộng dồn — không lịch sử, không ngày, không hóa đơn.

Cộng thêm feedback nghiệp vụ: phiếu chi lập ra là tiền đã ra (không có "chờ chi"), PMH cần hợp đồng
+ cọc, NCC cần hạn mức công nợ.

---

## 2. Bảy quyết định đã chốt

| # | Quyết định |
|---|---|
| **Đ1** | **Bỏ hẳn trạng thái "Chờ chi"** — lập phiếu chi = tiền đã ra. Công nợ chỉ còn *nợ đã phát sinh − đã chi ròng* |
| **Đ2** | **Cọc = một phiếu chi loại "Đặt cọc"**. PMH có ô "cọc dự kiến" chỉ để nhắc; tiền cọc THẬT luôn là chứng từ |
| **Đ2-sửa** | *(chủ chốt cùng ngày)* Cọc là cọc của **CẢ ĐƠN**, **không thuộc đợt giao nào**. Bản đầu phân bổ cọc vào đợt đầu theo kiểu "giao trước trả trước", làm bảng hiện *"đợt 1 đã trả X"* trong khi không ai trả cho riêng đợt đó. Nay cột *Đã trả* của đợt chỉ đếm tiền trả **đích danh** đợt đó; cọc đứng thành **dòng riêng** ở mức đơn. **Cọc dự kiến KHOÁ sau khi duyệt** (con số người duyệt đã đồng ý), và được dùng **điền sẵn** số tiền khi lập phiếu Đặt cọc — chưa khai thì lấy **nửa giá trị đơn** |
| **Đ3** | **Hợp đồng = ảnh/file đính kèm trên PMH** + một ô Số hợp đồng. Không đẻ danh mục, không đẻ màn mới |
| **Đ4** | **Đợt giao khai theo TỪNG DÒNG HÀNG** (số lượng) **VÀ số tiền theo HÓA ĐƠN** (gõ tay) — xem Đ4-sửa |
| **Đ4-sửa** | *(cùng ngày, chủ bác bỏ bản đầu)* Tiền của đợt **KHÔNG tự tính**. NCC xuất hóa đơn với số tiền không suy được từ đơn giá đặt là chuyện thường ⇒ công nợ bám **chứng từ**. Máy chỉ **gợi ý** số tính từ đơn giá; người khai ghi đè được. **Nhưng tổng tiền các đợt KHÔNG được vượt giá trị đơn đã duyệt** — đó là con số giám đốc đã ký |
| **Đ2-sửa2** | *(07/08/2026)* Cọc **CHIẾU XUỐNG** từng đợt thành cột **Cọc bù** riêng, và `con_no` của đợt trừ **cả** `paid` lẫn `coc_bu`. Bản trước để `con_no` nguyên giá trị nên đợt đã đủ tiền vẫn báo nợ kèm nút *Lập phiếu chi* — mời kế toán trả hai lần. Màn Công nợ **gom theo ĐƠN**, mỗi đơn mang cọc của chính nó |
| **Đ2-sửa3** | *(07/08/2026)* Một đơn lập phiếu **Đặt cọc thứ hai** thì **CẢNH BÁO, không chặn**: ứng thêm là ca có thật, và mỗi lần tiền rời két phải là một chứng từ riêng — sửa phiếu cọc cũ lên số to hơn là làm phiếu không khớp lần chi thật |
| **Đ1-sửa** | *(07/08/2026)* Phiếu chi lập rồi thì **KHÔNG SỬA**. *"Đã lập phiếu chứng từ rồi sao lại cho sửa nữa vậy, chỉ cho nó đính kèm tài liệu lên thôi"*. Phiếu phát hành ra là tiền đã rời két — sửa nó là làm tờ giấy ở chỗ NCC khác với bản trong máy. Sai thì **huỷ** (giữ số chứng từ + lý do) rồi lập phiếu mới. Còn sửa được đúng một thứ: **đính kèm tài liệu** |
| **Đ4-sửa2** | *(07/08/2026, đảo lại Đ4-sửa)* Tiền của đợt **QUAY VỀ MÁY TÍNH** từ `số lượng thực nhận × đơn giá đã chốt`. Bỏ hẳn ô "Số tiền theo hóa đơn". Lý do đảo: ô gõ tay đẻ ra đúng cái lệch mà chính chủ bắt được — chi tiết PMH hiện 1.000.000 (số khai) còn ngoài bảng 1.100.000 (số tính), hai con số cho **cùng một đợt**. Cột `purchase_deliveries.amount` thành **DORMANT**: giữ vì không có Alembic, nhưng không đọc và không ghi |
| **Đ5** | NCC: **Hạn mức công nợ** (VNĐ) + **Định mức** = **số ngày cho nợ** |
| **Đ6** | Vượt hạn mức = **cảnh báo mềm**, không chặn ở đâu cả |
| **Đ7** | Phiếu "Chờ chi" cũ → migration **tự chuyển thành "Đã chi"**, có đánh dấu để kế toán rà lại |

Điểm mở đã chốt theo đề xuất: ~~**O1** cọc đối trừ ngay từ đợt giao đầu~~ → **đã bị Đ2-sửa thay
thế**: cọc không thuộc đợt nào cả · **O2** hóa đơn chưa cần số tiền riêng (đã bị Đ4-sửa thay: tiền
cuối cùng quay về máy tính từ số lượng — Đ4 → Đ4-sửa → Đ4-sửa2) · **O3** `credit_days = 0` nghĩa là trả ngay, để trống (NULL) là
chưa đặt hạn ⇒ không báo quá hạn · **O4** có ô Số hợp đồng · **O5** đợt giao không cần mã chứng từ
riêng.

---

## 3. Phạm vi

**Trong đợt này:** đợt giao (header + dòng) · hóa đơn gắn đợt · đính kèm PMH/đợt · cọc dự kiến ·
bỏ trạng thái chờ chi · phiếu chi gắn đợt giao · công thức công nợ mới · hạn trả suy từ đợt giao ·
hạn mức + số ngày cho nợ của NCC · màn Công nợ đổi theo.

**Ngoài đợt này:** phiếu nhập kho thật (đợt giao chỉ **chừa chỗ neo** `stock_voucher_id`) · công nợ
phải thu (AR) · đối trừ AR↔AP (SEAM-18) · danh mục hợp đồng · hạch toán kép (vẫn ở MISA).

---

## 4. Mô hình dữ liệu

### 4.1 Bảng MỚI

#### `purchase_deliveries` — Đợt giao

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int PK | |
| `purchase_request_id` | FK `purchase_requests` CASCADE, NOT NULL | |
| `seq_no` | int NOT NULL | Đợt 1, 2, 3… trong phạm vi PMH. **Không** dùng dãy số toàn hệ |
| `delivery_date` | Date NOT NULL | Ngày hàng về — gốc dự phòng khi chưa có ngày hóa đơn |
| `due_date` | Date NULL | Hạn thủ công/dữ liệu cũ. Có ngày hóa đơn thì ưu tiên suy theo hóa đơn |
| `invoice_number` | String(64) NULL | **Nhiều đợt cùng số = cùng MỘT hóa đơn** |
| `invoice_date` | Date NULL | |
| `amount` | BigInteger NULL | **Số tiền theo HÓA ĐƠN**, gõ tay (Đ4-sửa). NULL = chưa khai ⇒ lùi về số máy tính từ đơn giá — vừa là cầu cho đợt cũ, vừa là số form điền sẵn |
| `note` | Text NULL | |
| `stock_voucher_id` | int NULL, **soft ref** | 🔌 chỗ neo Phiếu nhập kho — đợt này luôn NULL |
| `created_by_user_id` | FK `users` SET NULL | |
| `created_at` / `updated_at` | DateTime(tz) | |

UNIQUE `(purchase_request_id, seq_no)`.

#### `purchase_delivery_lines` — Dòng của đợt giao

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int PK | |
| `delivery_id` | FK `purchase_deliveries` CASCADE | |
| `purchase_request_line_id` | FK `purchase_request_lines` RESTRICT | Neo về dòng đặt |
| `quantity` | Numeric(14,2) NOT NULL | Số thực nhận của **riêng đợt này** |
| `note` | Text NULL | |

UNIQUE `(delivery_id, purchase_request_line_id)` — một đợt không khai một mặt hàng hai dòng.

> **Không có cột tiền ở DÒNG** — tiền nằm ở ĐẦU đợt (`purchase_deliveries.amount`), vì hóa đơn ghi
> một số tổng chứ không tách theo mặt hàng. Dòng chỉ giữ **số lượng**, dùng để suy trạng thái nhận
> hàng và để biết đợt nào về món gì.
>
> Bản đầu định để máy tự tính tiền từ đơn giá; chủ bác bỏ cùng ngày: *"cứ có hóa đơn là có công nợ,
> cho nó điền, mình không cần tự tính đâu"*. Công nợ bám **chứng từ** — vì chứng từ mới là thứ đem
> đi đối chiếu với NCC. Đổi lại phải giữ **trần tổng ≤ giá trị đơn đã duyệt**
> (`_chan_tong_dot_vuot_don`), nếu không thì công nợ phình lên bằng một con số không ai ký.

#### `purchase_attachments` — Ảnh/file của mua hàng

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int PK | |
| `purchase_request_id` | FK CASCADE, NOT NULL | |
| `delivery_id` | FK `purchase_deliveries` CASCADE, NULL | **NULL = file của cả PMH** (hợp đồng) |
| `kind` | String(24) | `hop_dong` · `hoa_don` · `bien_ban_giao` · `khac` |
| `file_name` / `file_url` / `file_type` | | mirror `payment_voucher_attachments` |
| `uploaded_by` / `uploaded_at` | | |

Bytes vào `mua-hang/<purchase_request_id>/`.

> ⚠️ **BẮT BUỘC thêm `"mua-hang" → "thu_mua"` vào `_PREFIX_PERMISSION` (`routers/files.py`).**
> Bảng đó **fail-MỞ**: tiền tố không có trong bảng thì chỉ cần đăng nhập là đọc được file. Quên dòng
> này là hợp đồng NCC lộ cho toàn công ty.

### 4.2 Cột THÊM (phải viết vào `db_migrations.py`)

| Bảng | Cột | Kiểu | Ghi chú |
|---|---|---|---|
| `suppliers` | `credit_limit` | BigInteger default 0 | Hạn mức công nợ. `0` = không đặt |
| `suppliers` | `credit_days` | Integer NULL | Số ngày cho nợ. `0` = trả ngay · NULL = chưa đặt hạn |
| `purchase_requests` | `deposit_expected` | BigInteger default 0 | Cọc **dự kiến** — chỉ để nhắc, KHÔNG vào công thức |
| `purchase_requests` | `contract_number` | String(64) NULL | Số hợp đồng (O4) |
| `payment_vouchers` | `delivery_id` | Integer NULL, **soft ref** | Phiếu chi trả cho đợt nào. NULL = cọc / chi chung |

### 4.3 Cột thành DORMANT (giữ nguyên, thôi đọc)

| Cột | Vì sao |
|---|---|
| `payment_vouchers.planned_payment_date` | Hạn trả chuyển lên đợt giao; phiếu = đã chi thì không còn "hạn trả" |
| `payment_vouchers.contract_number` | Hợp đồng chuyển lên PMH |
| `purchase_request_lines.received_quantity` | Thành số **dẫn xuất** — xem §5.1 |

Không xoá cột: dự án không có Alembic, và xoá là mất dữ liệu đơn cũ.

---

## 5. Công thức tiền — MỘT nguồn duy nhất

Toàn bộ nằm trong `purchase_money()` (`services/purchase_service.py`), vẫn dùng chung cho màn Mua
hàng **và** màn Công nợ. Hai bên tự cộng lấy là hai bên lệch.

### 5.1 Số thực nhận — có cầu tương thích ngược

```
qty_thuc_nhan(dòng):
    PMH CÓ ≥1 đợt giao  →  Σ purchase_delivery_lines.quantity của dòng đó
    ngược lại (đơn cũ)  →  received_quantity ?? quantity          ← y hệt luật cũ
```

> **KHÔNG backfill dữ liệu cũ.** Cùng nếp "NULL = phiếu lập trước ngày X" đã dùng khắp module.
> Đơn cũ giữ nguyên từng đồng sau khi lên bản mới.

### 5.2 Giá trị đã giao

```
gia_tri_dot_giao(đợt):
    đợt CÓ khai tiền  →  purchase_deliveries.amount           ← SỐ TRÊN HOÁ ĐƠN (Đ4-sửa)
    chưa khai         →  Σ (SL nhận × đơn giá/CK/VAT)         ← số máy tính, cũng là số form gợi ý

gia_tri_da_giao(PMH):
    có đợt giao  →  Σ gia_tri_dot_giao          ← hàng về tới đâu, nợ tới đó
    không có     →  received_total nếu status == received, ngược lại 0   ← luật cũ
```

**Trần:** `Σ gia_tri_dot_giao ≤ total` (giá trị đơn đã duyệt) — chặn cứng ở
`_chan_tong_dot_vuot_don`, gọi ở mọi mốc thêm/sửa/xoá đợt. Hoá đơn cao hơn đơn thì sửa đơn rồi
duyệt lại, không nhét chênh lệch vào đợt giao.

> `received_total` (giá trị theo ĐƠN GIÁ) và `gia_tri_da_giao` (tổng HOÁ ĐƠN) nay là **hai số khác
> nhau**. Công nợ bám số thứ hai. Đừng lẫn — màn hình hiện cả hai để đối chiếu.

### 5.3 Đã chi ròng · Công nợ

```
da_chi_rong = Σ phiếu chi ĐÃ CHI (gồm cả phiếu Đặt cọc)
            − Σ phiếu thu ĐÃ THU (tiền chi ra tiêu không hết, nộp về)

cong_no = max(0, gia_tri_da_giao − da_chi_rong)
```

Đây đúng công thức bên nghiệp vụ nói — *nợ − cọc − đã trả* — vì cọc đã nằm trong `da_chi_rong`.

**Cọc KHÔNG thuộc đợt nào** (Đ2-sửa). Màn Công nợ bóc một phiếu thành hai phần:

```
giá trị đợt = Σ (SL nhận × đơn giá/CK/VAT đã chốt)   ← MÁY TÍNH, không ai gõ (Đ4-sửa2)

cọc chung  = Σ phiếu chi KHÔNG gắn đợt (Đặt cọc / ứng trước)
           − Σ phiếu thu đã thu
           + phần trả THỪA của từng đợt

mỗi đợt:   paid   = Σ phiếu chi có delivery_id trỏ ĐÚNG đợt đó
           coc_bu = phần cọc chung chiếu xuống, GIAO TRƯỚC BÙ TRƯỚC
           con_no = giá trị đợt − paid − coc_bu

total_due  = Σ con_no                          ← luôn khớp `outstanding_amount`
```

**`paid` và `coc_bu` là hai cột khác nhau, cố ý** (Đ2-sửa · Đ2-sửa2):
- `paid` phải khớp sao kê NCC **theo từng đợt** ⇒ chỉ đếm tiền trả đích danh đợt đó.
- `coc_bu` là cọc của cả đơn chiếu xuống — không ai trả riêng cho đợt này số đó.
- **`con_no` trừ CẢ HAI.** Để `con_no` nguyên giá trị (bản 06/08 sáng) thì đợt đã đủ tiền vẫn hiện
  "còn nợ" kèm nút *Lập phiếu chi* — mời kế toán trả lần thứ hai.

Phần trả thừa chảy ngược vào cọc chung để tổng không bao giờ lệch. **Quá hạn** dùng thẳng `con_no`
đã bù cọc — cọc đã trả rồi thì phần đó không còn bị tính là trễ.

Kiểm lại ba lỗi §1:

| Ca | Kết quả mới |
|---|---|
| (a) giao 1/3, đợt 1 trị giá 4tr, chưa chi | công nợ **4tr** ✅ (trước: 0đ) |
| (b) chưa giao đợt nào | công nợ **0đ** ✅ dù ai bấm gì |
| (c) cọc 10tr · giao 8,5tr · thu về 1,5tr | `8,5 − (10 − 1,5)` = **0đ** ✅ |

### 5.4 Trần lập phiếu chi

| Loại phiếu | Trần |
|---|---|
| **Đặt cọc / ứng trước** (`advance`) | `max(0, giá trị đơn đặt − da_chi_rong)` — cho ứng trước khi hàng về |
| **Thanh toán** gắn đợt | **CÒN NỢ CỦA CHÍNH ĐỢT ĐÓ** |
| **Thanh toán** không gắn đợt (đơn cũ) | `cong_no` của cả đơn |

> ⚠️ **Trần thanh toán phải theo ĐỢT, đừng nới về mức đơn** (lỗi 07/08/2026). Bản trước lấy công nợ
> cả đơn, nên kế toán chọn *Đợt 2* rồi gõ 75tr cho một đợt trị giá 35tr vẫn qua — 40tr thừa chảy vào
> rổ cọc chung rồi lặng lẽ trả hộ *Đợt 1*, xoá sổ món nợ 50tr khỏi màn Công nợ mà không ai bấm gì.
> Đúng bệnh GIẤU NỢ mà cả phân hệ này sinh ra để chữa, chỉ khác đường vào.
>
> Một lần chuyển khoản cho nhiều đợt ⇒ lập nhiều phiếu, mỗi phiếu một đợt. Đó cũng là thứ đem đi
> đối chiếu sao kê NCC được.

Trần tuyệt đối mọi lúc: `da_chi_rong ≤ giá trị đơn đặt`.

### 5.5 Quá hạn

```
hạn trả của đợt = (invoice_date + suppliers.credit_days)
                  ?? due_date
                  ?? (delivery_date + suppliers.credit_days)
                  → NULL nếu credit_days NULL và due_date NULL   (chưa đặt hạn)
quá hạn         = đợt đã giao · có hạn trả · hạn trả < hôm nay · PMH còn nợ > 0
```

Số quá hạn quy về **đợt giao**, không quy về phiếu chi nữa. Đợt **chưa có hạn** không vào cột Quá
hạn nên phải **đẩy lên ĐẦU danh sách** kèm badge "Chưa đặt hạn" — giữ nguyên nếp chống giấu nợ đang
có ở màn Công nợ.

### 5.6 Hạn mức NCC (cảnh báo mềm — Đ6)

```
no_hien_tai(NCC) = Σ cong_no các PMH của NCC đó
vuot_han_muc     = credit_limit > 0 AND no_hien_tai > credit_limit
```

Hiện ở: hồ sơ NCC · dòng NCC trên màn Công nợ (pill đỏ + số vượt) · nhắc khi duyệt PMH mới cho NCC
đó. **Không chặn** bất cứ đâu.

---

## 6. Luồng & trạng thái

### 6.1 Trạng thái PMH — thêm một bậc, và SUY RA thay vì gõ

```
draft → pending_approval → approved → purchased ──▶ partially_received ──▶ received
                     └──▶ rejected                          (đóng đơn) ──────┘
                                          cancelled
```

| Trạng thái | Điều kiện (suy từ đợt giao) |
|---|---|
| `purchased` | đã đánh dấu đã mua, **chưa có đợt giao nào** |
| `partially_received` | có ≥1 đợt, tổng thực nhận **chưa đủ** số đặt |
| `received` | tổng thực nhận **đủ** số đặt, **HOẶC** người bấm "Đóng đơn" |

**"Đóng đơn (không giao nữa)"** — nút mới cho ca NCC giao thiếu rồi thôi. Bắt lý do, quyền
`thu_mua:approve`, vào nhật ký. Chốt số thực nhận = số đã giao.

`undo_received` đổi nghĩa thành **"Mở lại đơn"**: `received → partially_received` (hoặc `purchased`
nếu chưa có đợt nào). Giữ nguyên luật chặn khi đã có phiếu chi đã chi.

### 6.2 Suy trạng thái YCMH

Thêm `partially_received` vào thang bậc ở **bậc 2** — cùng bậc `approved`/`purchased` ⇒ YCMH hiện
"Đang mua". Chưa giao xong thì chưa `done`. Thuật toán min/max hiện có **không đổi**.

### 6.3 Ghi đợt giao

- Quyền `thu_mua:update`. Chỉ ghi được khi PMH ở `purchased` / `partially_received`.
- Không cho khai vượt số còn lại của dòng đặt (`quantity − Σ đã giao các đợt khác`).
- **Sửa/xoá đợt giao bị CHẶN nếu đã có phiếu chi gắn vào đợt đó** — tiền đã ra thì không được đổi
  số hàng dưới chân nó.

### 6.4 Phiếu chi

- Lập ra là `paid` ngay (`paid_at` = lúc lập, `paid_by` = người lập). Bỏ nút "Đã chi" và toàn bộ
  đường `waiting_payment`.
- Bắt buộc chọn **loại**: `Đặt cọc` (không gắn đợt) hoặc `Thanh toán` (**bắt buộc chọn đợt giao**).
- **KHÔNG SỬA** phiếu đã lập (Đ1-sửa) — endpoint `PUT` đã gỡ hẳn. Sai thì huỷ rồi lập lại.
- `cancelled` giữ nguyên — dùng cho ghi nhận nhầm; bắt lý do; chặn nếu đã có phiếu thu gắn vào.
- `voucher_date` = ngày tiền ra. Vẫn cho ngày quá khứ (hóa đơn về muộn), vẫn chặn ngày tương lai.
- `planned_payment_date` thôi bắt buộc (hạn trả đã chuyển lên đợt giao).

---

## 7. Màn hình — gộp vào màn đang có, không đẻ màn mới

**Phiếu mua hàng · drawer chi tiết** — thêm 2 khối:

1. **Hợp đồng & chứng từ**: ô *Số hợp đồng* · ô *Cọc dự kiến* · vùng thả ảnh hợp đồng.
2. **Các đợt giao**: bảng `Đợt · Ngày giao · Hàng nhận (thu gọn) · Thành tiền · Hóa đơn · Hạn trả ·
   Đã trả`. Nút *Ghi đợt giao*. Dòng tổng: **Đã giao X · Đã chi Y · Còn nợ Z**.
   Form ghi đợt: khai **số lượng từng dòng hàng** + ô **Số tiền theo hóa đơn** (điền sẵn số tính
   theo đơn giá, sửa được). Lệch với số theo đơn giá thì hiện ngay tại chỗ nhập — lệch không phải
   lỗi, nhưng lệch mà không ai thấy thì tới lúc đối chiếu với NCC mới lòi ra.

**Màn Công nợ phải trả** — bỏ cột 🟡 *Chờ chi*, còn: **Còn nợ · Quá hạn · Đã trả (3 tháng)** + pill
**Vượt hạn mức** khi có. Drawer NCC hiện hạn mức / đã nợ / còn được nợ, rồi danh sách **đợt giao còn
nợ** (thay danh sách đơn), sắp theo hạn trả, đợt chưa có hạn lên đầu.

**Hồ sơ NCC**: 2 ô mới — *Hạn mức công nợ (VNĐ)* · *Số ngày cho nợ*.

Bám UI_DESIGN.md: pill `r99` + chấm, KPI dạng dải pill (không phải 4 thẻ), bảng theo spec `.rdx-`,
cột số dùng `--ff-num`.

---

## 8. Quyền

| Việc | Quyền |
|---|---|
| Ghi/sửa/xoá đợt giao, đính kèm PMH | `thu_mua:update` |
| Đóng đơn / Mở lại đơn | `thu_mua:approve` + bắt lý do |
| Lập / huỷ phiếu chi | `ke_toan:approve` (giữ nguyên) |
| Đặt hạn mức + số ngày cho nợ của NCC | `thu_mua:update` |
| Đọc file `mua-hang/*` | `thu_mua` (qua `_PREFIX_PERMISSION`) |

---

## 9. Migration & tương thích ngược

| # | Việc | Ghi chú |
|---|---|---|
| M1 | 3 bảng mới | `create_all` lo — **bắt buộc export ở `models/__init__.py`** |
| M2 | `ADD COLUMN` ×5 (§4.2) | viết tay vào `db_migrations.py` |
| M3 | **`waiting_payment` → `paid`** | `paid_at = voucher_date`, `paid_by = created_by`, nối vào `note`: `[MIGRATION 06/08/2026] Tự chuyển từ Chờ chi — kế toán rà lại` |
| M4 | Thêm `partially_received` vào hằng trạng thái + thang bậc YCMH | không đụng dữ liệu |
| M5 | Cập nhật `docs/DB_SCHEMA.md` **cùng commit** | thiếu là `./init.ps1` đỏ, deploy bị chặn |
| M6 | Thêm `"mua-hang"` vào `_PREFIX_PERMISSION` | **bảo mật**, xem §4.1 |

**Không backfill đợt giao** — PMH cũ không có đợt nào ⇒ rơi vào nhánh luật cũ §5.1/§5.2 ⇒ số tiền
không đổi một đồng.

> ⚠️ **Rủi ro đã biết của M3** (chủ chấp nhận 06/08/2026): phiếu thực sự CHƯA chi cũng bị ghi nhận
> là đã chi ⇒ công nợ tụt thấp hơn thật đúng bằng số đó. Vì thế migration **đánh dấu vào `note` từng
> phiếu** để lần ngược được, và kế toán rà lại sau khi lên bản.

---

## 10. Test bắt buộc

1. Đơn 3 đợt, giao đợt 1 → công nợ = đúng giá trị đợt 1 (chống lỗi **a**)
2. Chưa giao đợt nào → công nợ 0đ dù trạng thái gì (chống lỗi **b**)
3. Cọc 10tr / giao 8,5tr / thu về 1,5tr → công nợ **0đ** (chống lỗi **c**)
4. PMH cũ không có đợt giao → mọi con tiền **y hệt trước migration**
5. Trần: chi vượt `cong_no` bị chặn; chi cọc vượt giá trị đơn bị chặn
6. Sửa/xoá đợt đã có phiếu chi → chặn
7. 3 đợt cùng một số hóa đơn → gom đúng thành 1 hóa đơn
8. Vượt hạn mức → có cờ, nhưng duyệt PMH **vẫn qua** (Đ6)
8b. **Tiền đợt theo hóa đơn** (Đ4-sửa): khai 1,5tr cho đợt máy tính 1,1tr → công nợ = 1,5tr;
    bỏ trống ô tiền → lùi về số máy tính; tổng các đợt vượt giá trị đơn → **chặn** (cả ca cộng dồn)
9. Trạng thái: giao đủ → `received`; "Đóng đơn" → `received` + chốt số; YCMH lên `done` đúng lúc
10. Migration M3 chạy 2 lần vẫn đúng (idempotent)

---

## 11. Việc doc này KHÔNG giải quyết

- **Phiếu nhập kho** — đợt giao và phiếu nhập kho là *cùng một sự kiện vật lý*. Cột
  `stock_voucher_id` đã chừa sẵn; khi build Kho ↔ Mua hàng thì nối vào đó, đừng đẻ khái niệm thứ ba.
- **Công nợ phải thu (AR)** và **đối trừ AR↔AP** — SEAM-16 / SEAM-18 còn treo.
- **Hóa đơn có số tiền riêng** lệch với tổng các đợt (VAT làm tròn, chiết khấu cuối kỳ) — khi cần thì
  thêm bảng `purchase_invoices`, đừng nhét thêm cột vào đợt giao.
