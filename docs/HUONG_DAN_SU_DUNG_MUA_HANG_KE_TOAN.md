# Hướng dẫn sử dụng — Mua hàng & Kế toán (Phiếu chi · Phiếu thu)

> Tài liệu dành cho **người dùng cuối** (kế toán, thu mua, quản lý) — hướng dẫn thao tác
> trên màn hình, không cần biết kỹ thuật. Đọc theo thứ tự từ trên xuống là làm được.

**Đăng nhập:** mở trình duyệt vào địa chỉ hệ thống → nhập **tên đăng nhập** + **mật khẩu**.
Nếu quên mật khẩu, nhờ người phụ trách Nhân sự/Quản trị đặt lại. Menu bên trái chỉ hiện những
mục mà tài khoản của bạn **được cấp quyền** xem — nếu thiếu mục nào là do chưa có quyền (xem
[Phần 6 — Phân quyền](#phần-6--phân-quyền-ai-làm-được-gì)).

---

## Mục lục

1. [Bức tranh tổng thể — luồng tiền đi và về](#phần-1--bức-tranh-tổng-thể)
2. [Thu mua — Tạo yêu cầu & lập phiếu mua hàng](#phần-2--thu-mua)
3. [Kế toán — Duyệt & lập Phiếu chi / UNC](#phần-3--kế-toán--phiếu-chi--unc)
4. [Kế toán — Phiếu thu (thu lại tiền thừa)](#phần-4--phiếu-thu)
5. [Tài khoản ngân hàng (bắt buộc cho Ủy nhiệm chi)](#phần-5--tài-khoản-ngân-hàng)
6. [Phân quyền — ai làm được gì](#phần-6--phân-quyền-ai-làm-được-gì)
7. [Câu hỏi thường gặp & xử lý sự cố](#phần-7--câu-hỏi-thường-gặp)

---

## Phần 1 — Bức tranh tổng thể

Toàn bộ quy trình đi theo một chiều, mỗi bước tạo ra một loại phiếu:

```
  PHÒNG BAN                 THU MUA                    KẾ TOÁN
 ┌──────────┐            ┌──────────────┐         ┌──────────────────┐
 │  YCMH    │  gộp 1..n  │     PMH       │  duyệt  │  Phiếu chi (PC)  │
 │ Yêu cầu  │ ─────────► │ Phiếu mua    │ ──────► │  hoặc UNC        │
 │ mua hàng │            │ hàng (có giá)│         │  (chi tiền ra)   │
 └──────────┘            └──────────────┘         └────────┬─────────┘
  chưa có giá             có giá/VAT                        │ nếu tiền thừa
                                                            ▼
                                                   ┌──────────────────┐
                                                   │   Phiếu thu (PT) │
                                                   │  (tiền quay về)  │
                                                   └──────────────────┘
```

**Giải thích bằng lời thường:**
- **YCMH (Yêu cầu mua hàng):** phòng ban báo "tôi cần mua vật tư này" — chưa có giá.
- **PMH (Phiếu mua hàng):** bộ phận Thu mua gom một hoặc nhiều YCMH lại, điền nhà cung cấp,
  đơn giá, VAT → gửi Kế toán duyệt.
- **Phiếu chi (PC) / Ủy nhiệm chi (UNC):** Kế toán duyệt PMH rồi xuất tiền — **PC** là chi
  tiền mặt, **UNC** là chuyển khoản ngân hàng.
- **Phiếu thu (PT):** khi tiền chi ra tiêu không hết (ví dụ tạm ứng 10 triệu, mua hết 8,5
  triệu), phần thừa 1,5 triệu nhân viên nộp lại → lập Phiếu thu để ghi nhận tiền về.

**Nguyên tắc vàng luôn được hệ thống tự kiểm:**
- Tổng tiền các Phiếu chi của một PMH **không vượt** tổng tiền PMH.
- Tổng tiền các Phiếu thu **không vượt** số tiền đã chi của phiếu chi gốc.
- Tiền **đã thu** về sẽ **mở lại hạn mức** để chi tiếp cho PMH đó nếu cần.

---

## Phần 2 — Thu mua

### 2.1. Tạo Yêu cầu mua hàng (YCMH)

Menu: **Thu mua → Yêu cầu mua hàng** → nút **“+ Tạo yêu cầu mua”**.

1. Chọn **Bộ phận phát sinh** (Kinh doanh / Kho / Sản xuất…).
2. Nhập **Ngày cần hàng**, **Mục đích**.
3. Thêm các **dòng vật tư**: tên vật tư, đơn vị tính, số lượng. *(YCMH không nhập giá — giá do
   Thu mua điền ở bước sau.)*
4. Bấm **Lưu**. Phiếu ở trạng thái **“Chờ Thu mua xử lý”**.

### 2.2. Lập Phiếu mua hàng (PMH)

Menu: **Thu mua → Mua hàng**.

1. Ở bảng phía trên, **tích chọn** một hoặc nhiều YCMH cần gom (cùng một nhà cung cấp).
2. Bấm **“Tạo phiếu mua hàng”**.
3. Điền: **Nhà cung cấp**, **Ngày cần hàng**, **Ngày dự kiến nhận hàng** *(không bắt buộc)*,
   **Mục đích**.
4. Với mỗi dòng hàng: nhập **Đơn giá**, **Giảm giá (%)**, **VAT (%)** — hệ thống tự tính thành tiền.
5. Bấm **Lưu** → PMH ở trạng thái **Nháp**.
6. Bấm **Gửi duyệt** → PMH chuyển sang **Chờ duyệt** và nằm trong hộp thư Kế toán.

**Vòng đời PMH:** Nháp → Chờ duyệt → **Đã duyệt** → Đã mua → **Đã nhận**.
Lưu ý: PMH **đã có phiếu chi** thì **không hủy được** (phải hủy phiếu chi trước).

---

## Phần 3 — Kế toán — Phiếu chi / UNC

### 3.1. Duyệt PMH và lập chứng từ

Menu: **Kế toán → Yêu cầu mua hàng** (đây là hộp thư PMH Thu mua gửi sang, mặc định lọc
“Chờ duyệt”).

1. Chọn một PMH → xem chi tiết bên phải (nhà cung cấp, các dòng hàng, tổng tiền).
2. Bấm **“Duyệt & lập chứng từ”** để vừa duyệt PMH vừa xuất phiếu chi ngay, **hoặc** **“Từ
   chối”** (phải nhập lý do).
3. Nếu chỉ muốn duyệt trước, chi sau: sau khi PMH “Đã duyệt”, vào lại phiếu và bấm **“Lập
   Phiếu chi/UNC”**.

### 3.2. Điền phiếu chi

Trong ô lập chứng từ:

- **Chọn loại:** *Phiếu chi* (tiền mặt) hoặc *Ủy nhiệm chi* (chuyển khoản).
- **Đợt thanh toán:** Tạm ứng/đặt cọc · Thanh toán một phần · Thanh toán cuối · Khác. Hệ
  thống tự gợi ý “Thanh toán cuối” khi số tiền bằng đúng phần còn lại.
- **Số tiền, nội dung chi.**
- Nếu là **Phiếu chi**: nhập **Người nhận tiền** (người đi mua/nhà cung cấp).
- Nếu là **Ủy nhiệm chi**: chọn **Tài khoản trích nợ** (của công ty) và **Tài khoản thụ
  hưởng** (của nhà cung cấp). *(Cần khai báo trước — xem [Phần 5](#phần-5--tài-khoản-ngân-hàng).)*
- **Chứng từ đã mua:** có thể chọn sẵn ảnh hóa đơn/PDF để đính kèm ngay (hoặc bổ sung sau).
- Bấm **Lập chứng từ**.

> **Chi nhiều đợt:** một PMH có thể có nhiều phiếu chi (tạm ứng → bổ sung → quyết toán). Hệ
> thống hiển thị “Còn được lập” để bạn biết chi thêm được bao nhiêu. Các phiếu chi cùng một
> PMH được **gom nhóm** với nhau trên danh sách; **dải nhóm** ghi sẵn **“Đã chi: X / Tổng PMH: Y”**
> nên không phải cộng tay.

### 3.3. Xác nhận đã chi

Sau khi thực sự xuất tiền: chọn phiếu → bấm **“Xác nhận đã chi”**.
- Với **UNC** phải nhập **Mã giao dịch / số báo nợ**.
- Phiếu chuyển trạng thái **Đã chi** và trở thành chứng từ bất biến (không sửa/hủy được nữa).

### 3.4. Chi bổ sung

Trên một phiếu **Đã chi** còn hạn mức, bấm **“Chi bổ sung”** để lập tiếp một phiếu chi khác
cho cùng PMH (số tiền mặc định = phần còn lại).

### 3.5. Đính kèm hóa đơn/chứng từ

Ở panel chi tiết phiếu chi có khối **“Chứng từ đính kèm”**:
- Bấm **Thêm ảnh hóa đơn / PDF** để tải lên (ảnh hiện thu nhỏ, PDF hiện dạng liên kết 📎).
- Đính được **cả sau khi đã chi** (vì hóa đơn thường về sau khi đi mua). Chỉ giới hạn: mỗi
  file ≤ 10 MB, chỉ nhận ảnh hoặc PDF, tối đa 20 file/phiếu.
- Phiếu **Đã chi mà chưa có ảnh** sẽ hiện badge đỏ **“Thiếu chứng từ”** để nhắc bổ sung.

### 3.6. In phiếu (mẫu Bộ Tài chính)

Bấm **“In phiếu”** → mở cửa sổ khổ A4 in đúng **Mẫu số 02 - TT** (ban hành theo Thông tư
200/2014/TT-BTC): đầy đủ tên/địa chỉ công ty, Quyển số, **Số phiếu (PC00445)**, Nợ/Có, số tiền
bằng chữ, 5 ô ký (Giám đốc · Kế toán trưởng · Thủ quỹ · Người lập phiếu · Người nhận tiền) và
dòng “Đã nhận đủ số tiền”. Ủy nhiệm chi cũng dùng mẫu này, có thêm dòng thông tin chuyển khoản.
Phiếu đã hủy vẫn in được, có đóng dấu chìm **ĐÃ HỦY**.
*(Không mở được → trình duyệt chặn pop-up, cho phép rồi thử lại.)*

**Hai loại “số” trên phiếu — đừng nhầm:**

| | Ví dụ | Dùng để |
|---|---|---|
| **Số phiếu** (in trên chứng từ) | `PC00445` · `PT00027` | Ghi sổ, lưu chứng từ giấy — chạy liên tục, không trùng |
| **Mã tra cứu** (trên màn hình) | `PC-260713-XFHI` | Tìm nhanh trong hệ thống |

Ô tìm kiếm nhận **cả hai** — gõ `PC00445` hay mã dài đều ra đúng phiếu.

**Ô Nợ / Có:** khi lập phiếu có mục **“Định khoản (in trên phiếu)”** — gõ tay số tài khoản
(vd Nợ `242, 1331` · Có `1111`). Để trống thì phiếu in ra chỗ đó là dấu chấm để viết tay.

---

## Phần 4 — Phiếu thu

Dùng khi **tiền chi ra không tiêu hết**, người đi mua nộp lại phần thừa.

### 4.1. Lập phiếu thu

Trên một **Phiếu chi đã chi** (menu **Kế toán → Phiếu chi / UNC**): bấm **“Lập phiếu thu”**.

1. **Người nộp tiền:** hệ thống tự điền tên người phụ trách mua (người lập PMH) — sửa lại được.
   **Địa chỉ người nộp** cũng tự điền từ phiếu chi (ô này in trên mẫu 01-TT).
2. **Số tiền:** để trống, **tự nhập** đúng số tiền thừa (ví dụ 1.500.000đ). Dòng “Còn được
   thu” hiển thị mức tối đa cho phép.
3. **Hình thức:** *Nhập quỹ tiền mặt* hoặc *Về TK ngân hàng công ty*.
4. **Định khoản Nợ / Có** (tùy chọn — in trên phiếu, vd Nợ `1111` · Có `141`).
5. **Mã giao dịch / số báo có** — bắt buộc khi thu *Về TK ngân hàng* (đây là số dò sao kê).
6. **Nội dung, ngày thu.** Bấm **Lập phiếu thu** → số phiếu `PT00027`, trạng thái **Đã thu** ngay.

### 4.2. Quản lý phiếu thu

Menu: **Kế toán → Phiếu thu** — danh sách mọi phiếu thu.
- **Lập phiếu là ĐÃ THU** (đổi 27/08/2026). Trước đây phiếu ra ở trạng thái *Chờ thu* rồi phải bấm
  thêm **Xác nhận đã thu**; nay bỏ bước đó — chỉ lập phiếu khi tiền đã thực về, nên tiền cộng lại
  “Còn được lập” của PMH **ngay lúc lập**. Quên bấm nút xác nhận từng làm công nợ báo mình đã trả
  nhiều hơn thực tế. Giờ mọi nguồn phiếu thu và cả phiếu chi chung một luật.
  *(Nút **Xác nhận đã thu** chỉ còn hiện với phiếu CŨ lỡ nằm lại ở trạng thái Chờ thu.)*
- **Sửa:** không còn. Phiếu đã ghi nhận tiền thì **Hủy** (bắt nhập lý do) rồi **lập lại** —
  sửa thẳng số tiền đang được trừ vào công nợ là đổi sổ mà không để lại vết.
- **Hủy:** làm được ở mọi trạng thái, trừ phiếu đã hủy rồi.
- **Đính kèm ảnh minh chứng đã thu** và **In phiếu**: thao tác **y hệt phiếu chi** (Phần 3.5 và
  3.6); bản in theo **Mẫu số 01 - TT** (ô ký: Giám đốc · Kế toán trưởng · **Người nộp tiền** ·
  Người lập phiếu · Thủ quỹ). Phiếu **Đã thu mà chưa có ảnh** cũng hiện badge **“Thiếu chứng từ”**.

### 4.3. Truy vết qua lại

- Trên Phiếu chi: dòng **“Đã thu … · chờ thu …”** bấm được → nhảy sang trang Phiếu thu lọc
  đúng phiếu đó.
- Trên Phiếu thu: mã **Phiếu chi nguồn** bấm được → quay lại Phiếu chi.

---

## Phần 5 — Tài khoản ngân hàng

Bắt buộc khai báo **trước khi** lập Ủy nhiệm chi hoặc thu qua ngân hàng.

Menu: **Kế toán → Tài khoản ngân hàng**.
- **Tài khoản công ty:** chủ TK, số TK, ngân hàng, chi nhánh, loại tiền. Đặt một TK **mặc định**.
- **Tài khoản nhà cung cấp:** khai theo từng nhà cung cấp (dùng làm bên thụ hưởng khi chuyển khoản).
- Có thể **Bật/Tắt hoạt động** một tài khoản; tài khoản đã tắt không chọn được khi lập chứng từ.

---

## Phần 6 — Phân quyền: ai làm được gì

### 6.1. Ba khái niệm cần nắm

| Khái niệm | Nghĩa |
|---|---|
| **Phòng ban** | Cây tổ chức (Khối → Phòng → Tổ). Mỗi nhân viên thuộc một phòng. |
| **Vai trò** | Chức danh **trong một phòng** (vd “Kế toán thanh toán”). Mỗi người giữ **một** vai trò. |
| **Quyền** | Mỗi vai trò được bật/tắt từng quyền cho từng chức năng: **Xem · Thêm · Sửa · Xóa** + các quyền riêng (Duyệt, Xác nhận đã chi…). |
| **Phạm vi dữ liệu** | Với dữ liệu có chủ: **Của tôi** (chỉ mình) / **Cả phòng** (mình + cấp dưới) / **Tất cả**. |

> Menu chỉ hiện chức năng mà vai trò **được Xem**. Nút thao tác (Duyệt, Chi, In…) chỉ hiện khi
> có đúng quyền tương ứng. **Backend luôn kiểm lại** — không thể lách bằng cách đoán đường link.

### 6.2. Tạo/sửa vai trò và cấp quyền

Việc này làm ở **Quản lý hệ thống → Phòng ban** (cần quyền *Sửa ma trận phân quyền* — thường
là Giám đốc/Quản trị).

1. Chọn **phòng** (vd “Kế toán”) ở danh sách bên trái.
2. Khu **“Vai trò trong phòng”**: bấm **“+ Thêm vai trò”**, đặt tên (vd *Kế toán thanh toán*).
3. Trong **ma trận quyền**, với từng chức năng tick các ô cần bật (bảng gợi ý bên dưới), chọn
   **Phạm vi dữ liệu** nếu có. Bấm **Lưu**.
4. Sửa quyền sau này: bấm vào **tên vai trò** để mở lại ma trận.
5. **Gán vai trò cho nhân viên:** trong cùng trang Phòng ban, ở danh sách nhân sự, chọn vai
   trò cho từng người (cần quyền *Gán vai trò*).

### 6.3. Bảng quyền gợi ý cho quy trình Mua hàng — Kế toán

**Chức năng “Thu mua” (module Thu mua):**

| Vai trò | Xem | Thêm | Sửa | Xóa |
|---|:---:|:---:|:---:|:---:|
| Nhân viên thu mua | ✔ | ✔ | ✔ | ✔ |
| Kế toán (chỉ tra cứu YCMH) | ✔ | | | |

**Chức năng “Kế toán” (module Kế toán) — các quyền riêng:**

| Quyền | Cho phép làm gì | Vai trò nên bật |
|---|---|:---:|
| **Xem** | Thấy menu + xem mọi phiếu chi/thu, tài khoản ngân hàng | Mọi vai trò kế toán |
| **Duyệt PMH & lập Phiếu chi/UNC** | Duyệt PMH, lập/sửa phiếu chi, **lập/sửa phiếu thu**, đính kèm/xóa ảnh | Kế toán thanh toán |
| **Xác nhận đã chi** | Chỉ còn dùng cho phiếu thu CŨ nằm lại ở trạng thái Chờ thu — phiếu mới lập ra đã là “đã chi” / “đã thu” | Kế toán thanh toán (hoặc kế toán trưởng) |
| **Hủy chứng từ** | Hủy phiếu chi/phiếu thu (bắt nhập lý do) | Kế toán trưởng |
| **In / xuất chứng từ** | Nút “In phiếu” | Mọi vai trò kế toán |
| **Sửa** (Tài khoản ngân hàng) | Thêm/sửa tài khoản ngân hàng công ty | Kế toán trưởng |

> **Gợi ý cấu hình thực tế:** tạo 2 vai trò trong phòng Kế toán —
> **“Kế toán thanh toán”** (Xem + Duyệt & lập + Xác nhận đã chi + In) và **“Kế toán trưởng”**
> (thêm Hủy + Sửa tài khoản ngân hàng). Nhân viên chỉ tra cứu thì tạo vai trò chỉ có **Xem**.

### 6.4. Ai được duyệt / chi / thu (tóm tắt)

- **Duyệt PMH** và **lập Phiếu chi/UNC/Phiếu thu:** người có quyền *Duyệt PMH & lập Phiếu chi/UNC*.
- **Xác nhận đã chi / đã thu:** người có quyền *Xác nhận đã chi*.
- **Hủy chứng từ đang chờ:** người có quyền *Hủy chứng từ chờ chi*.
- **In:** người có quyền *In / xuất chứng từ*.

Mọi thao tác đổi quyền/duyệt/chi/thu đều được ghi vào **Nhật ký** (Quản lý hệ thống → Nhật ký):
ai làm, lúc nào.

---

## Phần 7 — Câu hỏi thường gặp

**“Bạn không có quyền truy cập mục này (403)”.**
Vai trò của bạn chưa được cấp quyền **Xem** chức năng đó → nhờ Quản trị bật quyền (Phần 6.2).
Nếu vừa được đổi menu/quyền, **bấm F5** (tải lại trang) một lần.

**Không thấy menu Phiếu thu / Phiếu chi.**
Cần quyền **Xem** module Kế toán. Hiện mặc định chỉ tài khoản Giám đốc/Admin có sẵn — hãy tạo
vai trò kế toán và gán cho nhân viên (Phần 6).

**Badge đỏ “Thiếu chứng từ” là gì?**
Nhắc rằng phiếu đã chi/đã thu nhưng **chưa đính kèm ảnh** hóa đơn/biên nhận. Đính ảnh vào là
badge tự biến mất — không chặn nghiệp vụ, chỉ nhắc nhở.

**Bấm “In phiếu” không thấy gì.**
Trình duyệt đang **chặn pop-up**. Cho phép pop-up cho địa chỉ hệ thống rồi bấm lại.

**Không lập được phiếu thu / báo “vượt quá phần còn được thu”.**
Tổng tiền thu không được vượt số **đã chi** của phiếu gốc. Kiểm lại dòng “Còn được thu”.

**Không hủy được PMH.**
PMH đã có phiếu chi (đang chờ hoặc đã chi) thì phải xử lý phiếu chi trước.

**Sửa phiếu chi/thu đã xác nhận được không?**
Không. Phiếu **đã chi / đã thu** là chứng từ bất biến. Cần điều chỉnh thì lập phiếu bù tương ứng
(ví dụ chi sai → lập phiếu thu thu lại; thu thiếu → lập phiếu thu bổ sung).

---

*Tài liệu này mô tả thao tác trên giao diện. Khi hệ thống cập nhật thêm chức năng, tài liệu sẽ
được bổ sung tương ứng.*
