# PRD — Vá phân quyền vòng 2

**Ngày**: 11/08/2026 · **Nguồn**: chủ chốt test tay trên hệ thống dev, 24 mục
**Tiền đề**: tiếp sau `prd-phan-quyen-3-phan-he.md` (đợt 0→6 đã xong)

---

## 0. Cách đọc tài liệu này

24 mục báo về, đã soi mã và phân thành 4 loại — **không gộp chung**, vì mỗi loại có rủi ro và cách
sửa khác hẳn:

| Loại | Số mục | Nghĩa |
|---|---|---|
| **§1 Lỗi đã xác minh** | 8 | Đã chỉ được ra dòng mã gây lỗi |
| **§2 Thay đổi thiết kế** | 7 (1 treo) | Không phải lỗi — chủ chốt muốn khác đi |
| **§3 Công tắc chết** | 4 | Ô bật cũng không mở thêm gì |
| **§4 Cần dựng lại ca đo** | 3 | Chưa đủ bằng chứng, không đoán |

**Hai mục trong §1 là hồi quy do chính đợt trước gây ra.** Ghi rõ để lần sau không lặp lại.

---

## 1. Lỗi đã xác minh

### 1.1 · 1.8 — Đổi khoá ở máy chủ mà sót giao diện ⚠️ *(hồi quy)*

Đợt trước dời hai ô quyền ở **máy chủ** nhưng quên đổi bên **giao diện**. Hậu quả giống nhau: cấp
quyền rồi mà **nút không hiện**.

| Nút mất | Giao diện đang hỏi | Máy chủ thật sự gác |
|---|---|---|
| *Duyệt* · *Từ chối* (màn Đơn mua hàng — Kế toán) | `thu_mua:approve` | `ke_toan:approve` |
| *Sửa số nhận* · *Mở lại đơn* · *Đóng đơn* (màn Mua hàng) | `thu_mua:approve` | `thu_mua:manage_status` |

Neo: `AccountingPurchaseInboxPage.tsx:98` · `PurchaseRequestsPage.tsx:627`

**Sửa**: đổi hai chỗ. **Chống tái phát**: test đối chiếu — mọi cặp *(màn, ô quyền)* giao diện hỏi
phải là cặp máy chủ thật sự gác; lệch một đầu là test đỏ.

### 1.2 — Nghỉ phép: 1 ô không cấp được, 1 ô không tên, 1 ô chết 🔴

Cả phân hệ Nghỉ phép không có ô nào được đặt tên, nên nhìn ma trận không đoán ra cột nào làm gì:

| Việc thật | Máy chủ đòi | Ma trận đang hiện |
|---|---|---|
| Xem đơn (theo phạm vi) + đọc danh mục loại nghỉ | `read` | Xem ✅ |
| Gửi đơn xin nghỉ | `create` | Thêm — không ai đoán được "Thêm" = xin nghỉ |
| **Thêm / sửa / xoá LOẠI NGHỈ** | `update` | Thao tác — **không nhãn nào nói đây là quản loại nghỉ** |
| **Duyệt / từ chối + Lịch nghỉ** | `approve` | ❌ **không có ô nào để cấp** |
| — | `delete` | Xoá — **ô chết** (xoá loại nghỉ thật ra dùng `update`) |

**a)** `FINE_ACTIONS` không có mục `nghi_phep` ⇒ `can_approve` không ai bật được ⇒ tab *Duyệt đơn*
và *Lịch nghỉ* không bao giờ hiện với ai ngoài admin.
**b)** Quản loại nghỉ núp dưới cột "Thao tác" trần — bật nó là mở danh mục của **cả công ty** mà
người cấp không hề biết.
**c)** Cột *Xoá* là ô chết.

**Sửa**: thêm ô **Duyệt đơn nghỉ phép** (`can_approve`) và ô **Quản danh mục loại nghỉ**
(`can_update`); cột *Xoá* → tắt + disable theo §3.

### 1.3 — Nút *Xuất Excel* không gác gì 🔴

`NhanSuPage.tsx:661` render nút trần, không hỏi quyền. Ô *"Xuất Excel danh sách"* trong ma trận
**chưa bao giờ có tác dụng**. Máy chủ cũng không đòi ô này ⇒ ai xem được hồ sơ là xuất được cả
danh sách ra file.

**Sửa**: gác nút bằng `nhan_su:export` **và** gác endpoint xuất — ẩn nút không thôi chỉ là che mắt.

### 1.4 — Bật *Thao tác* Lương là hiện luôn *Cấu hình lương* 🔴

`canReadConfig = can("luong","view_salary") || can("luong","update")`. Ai sửa được dòng lương thì
tự mở được cấu hình thang bậc, hệ số, thuế — hai mức khác hẳn nhau.

**Sửa**: tab *Cấu hình lương* dùng ô riêng, không ăn ké `update`.

### 1.5 — Chưa bật *Thao tác* vẫn gửi được đơn/phiếu 🔴

Gốc chung của 3 mục báo về (Tự phục vụ · Tăng ca · Nghỉ phép): khoá `self_service` hiện **chỉ dùng
động từ `read`**. Cột *Thao tác* của nó là ô chết nên bật hay không cũng thế.

**Sửa** — chia đôi động từ:

| Ô | Cho làm gì |
|---|---|
| **Xem** (`read`) | Xem công, phiếu lương, đơn của chính mình |
| **Thao tác** (`create`) | **Chấm công** · gửi/sửa/huỷ đơn nghỉ · phiếu tăng ca · xin đi muộn · xin tạm ứng |

⚠️ **Migration bắt buộc**: `self_service.can_create = can_read` cho mọi vai đang có — không thì
sáng hôm sau **cả nhà máy không chấm công được**.

### 1.6 — YCMH: tắt *Thao tác* vẫn thấy nút *Sửa* / *Huỷ* 🔴

Nút chỉ xét *"có phải người tạo không"*, không xét quyền. Máy chủ đã chặn đúng — đây là phần giao
diện.

**Sửa**: điều kiện thành *(người tạo **và** có ô Thao tác)* hoặc *(có ô Huỷ hộ)*.

### 1.7 — Ma trận không hiện 3 ô đã bật 🔴

`get_matrix` (đường **đọc** ma trận) **bỏ sót 3 cột**: `can_view_salary`, `can_edit_salary`,
`can_adjust`. DB lưu đúng, máy chủ chặn đúng, chỉ đường trả về giao diện thiếu ⇒ công tắc luôn
hiện tắt dù đã bật.

Đúng ba ô chủ chốt chỉ: *Xem lương & BHXH* · *Sửa lương & BHXH* · *Chấm bù / sửa công*.

Cùng họ với lỗi `can_view_log` vá hôm trước. Guard cũ **soi chưa đủ sâu**: nó chỉ đếm số lần tên
cột xuất hiện trong `role_service`, nên `can_adjust` (có ở danh sách cờ + `save_matrix`) vẫn lọt dù
thiếu ở `get_matrix`.

**Sửa**: nối 3 cột. **Siết guard**: mọi cột quyền phải có mặt ở **cả** `get_matrix` **lẫn**
`save_matrix`, soi riêng từng hàm; kiểm bằng đột biến.

---

## 2. Thay đổi thiết kế

### 2.1 — Ô *Sửa / đảo trạng thái đơn sau khi nhận hàng* 🟡 **CHỜ TEST RỒI QUYẾT**

Chủ chốt định bỏ vì "bật lên không thấy gì" — nhưng đó là do lỗi §1.8, không phải vì ô vô dụng. Ô
này gác 3 nút, **cả ba đều sửa lại con số đã sinh ra công nợ**: *Sửa số nhận* (đếm sai lúc nhận) ·
*Mở lại đơn* (lỡ bấm đã nhận) · *Đóng đơn* (NCC không giao nữa, chốt nợ theo số đã giao).

§1.8 đã vá (11/08/2026) nên ô này **hiện đúng rồi**. Chưa động gì thêm — chờ chủ chốt test.

**Cách test**:
1. Cấp một vai: *Mua hàng* → **Xem + Thao tác**, và **KHÔNG** tick *Sửa / đảo trạng thái đơn*.
2. Mở một đơn đã ở trạng thái **Đã nhận** → không được thấy *Sửa số nhận*, *Mở lại đơn*; đơn
   **Giao một phần** không được thấy *Đóng đơn*.
3. Tick ô đó lên → ba nút phải hiện.

**Quyết gì**: giữ ô riêng, hay gộp ba nút về ô **Thao tác** của Mua hàng.
Khuyến nghị **giữ riêng** — ai sửa được đơn không đương nhiên nên đảo được số đã vào công nợ.
Nếu bỏ: đổi 3 chỗ kiểm ở `purchase_service` sang `can_update`, gỡ ô khỏi ma trận, thêm migration
đổ `thu_mua.can_manage_status` về `can_update`.

### 2.2 — Tách *Yêu cầu chỉnh công* thành ô riêng

Hiện dùng chung ô *Chấm bù*. Tách thành khoá riêng, **phạm vi chỉ *Cả phòng* / *Tất cả*** — duyệt
yêu cầu của chính mình là vô nghĩa. Migration: chép `cham_cong.can_adjust` sang ô mới.

### 2.3 — Gộp 3 tab cấu hình chấm công thành một ô

*Điểm chấm công* + *Khai ca* + *Lịch & Ngày lễ* → một ô **Cấu hình chấm công**, phạm vi cố định
**Tất cả** (hạ tầng dùng chung, không có khái niệm "của phòng tôi").

### 2.4 — *Đi muộn / về sớm*: chỉ còn ô *Duyệt*

Bỏ cột Xem + Thao tác. Xin phiếu của mình đi bằng ô **Tự phục vụ** (§1.5).

### 2.5 — *Phòng ban* xếp lên trên *Hồ sơ nhân sự* trong ma trận

Cây tổ chức là cái khung chứa hồ sơ, đọc từ trên xuống mới thuận.

### 2.6 — Khoá ô chọn phạm vi ở nơi phạm vi vô nghĩa

| Màn | Phạm vi |
|---|---|
| Hồ sơ nhân sự | **Cả phòng** / **Tất cả** (bỏ *Của tôi*) |
| Yêu cầu chỉnh công | **Cả phòng** / **Tất cả** |
| Nhà cung cấp | **Tất cả**, khoá — danh mục dùng chung |
| Đơn mua hàng (Kế toán) | **Tất cả**, khoá — hộp thư của cả công ty |
| Cấu hình chấm công | **Tất cả**, khoá |
| Tự phục vụ | **Của tôi**, khoá |
| Lương | **Tất cả**, khoá ⚠️ **CHỜ TEST RỒI QUYẾT** |

⚠️ **Riêng Lương — chưa làm, cố ý.** Khoá về *Tất cả* nghĩa là ai có ô Lương đều thấy bảng lương
**toàn công ty**, kể cả HR phụ trách một phòng. Hiện phạm vi Lương **đang có tác dụng thật** (từ
đợt 3, `payroll._scope_for` đọc phạm vi của chính khoá `luong`). Đây là **mở rộng dữ liệu nhạy
cảm**, không phải dọn ô thừa — làm rồi thì khó lùi, vì lúc đó không còn ô nào để siết lại.

**Cách test trước khi quyết**:
1. Dựng vai *HCNS phòng Sản xuất*: ô **Lương → Xem**, phạm vi **Cả phòng**.
2. Đăng nhập bằng vai đó, mở màn **Lương → Bảng lương**, **đếm số dòng**.
3. So với admin (phạm vi *Tất cả*).

**Quyết gì**: nếu số dòng ít hơn admin ⇒ phạm vi Lương đang chạy đúng, và câu hỏi thật là *"nhà máy
có muốn HR một phòng xem lương phòng khác không"*. Nếu bằng nhau ⇒ phạm vi không ăn, đó là **lỗi**
chứ không phải chuyện chọn thiết kế — báo lại để vá như §4.1.

### 2.7 — Xin nghỉ về chung ô Tự phục vụ

Hiện gửi đơn xin nghỉ đòi `nghi_phep:create`, trong khi mọi việc tự phục vụ khác gom về
`self_service:create` (§1.5). Để riêng nghỉ phép một kiểu là đúng cái bệnh "quyền không ăn khớp"
đang dọn.

| Ô | Nghĩa mới |
|---|---|
| `self_service:create` | Xin nghỉ **cho chính mình** |
| `nghi_phep:create` | Tạo đơn **hộ người khác** (HCNS nhập giùm thợ không dùng máy) |

Migration: `nghi_phep.can_create` cũ đổ sang `self_service.can_create`.

---

## 3. Công tắc chết — tắt + disable + hover cảnh báo

*Đơn mua hàng (Kế toán)* · *Công nợ phải trả* · *Công nợ phải thu* — cột **Thao tác**;
*Nghỉ phép* — cột **Xoá**. Không endpoint nào hỏi.

Hover hiện: **"Ô này chưa nối vào chức năng nào — bật cũng không mở thêm gì."**

Làm kiểu **tự sinh**: máy chủ khai cổng nào thì ô đó sống, gỡ cổng thì ô tự chết. Chép tay một
danh sách là ba tháng nữa nó lệch.

> ⚠️ **Mục này CHƯA đóng — xem §10.** Cuối cùng vẫn phải khai tay (suy ngược từ registry đã khoá
> nhầm hàng loạt ô đang dùng, xem `deps.O_CHET_DA_XAC_MINH`), nên module sinh sau đợt E đều lọt.
> Đo lại 12/08/2026: còn **15 ô** ở 8 màn.

---

## 4. Đã đo — kết quả (đợt B, 11/08/2026)

Dựng hai bộ phận, mỗi bên gửi một yêu cầu / lập một phiếu, rồi **đếm số dòng** từng vai thấy được.

| Ca đo | own | department | all |
|---|---|---|---|
| YCMH — vai **chỉ có** `yeu_cau_mua_hang` | 1 | 1 | 2 |
| YCMH — vai **có thêm** `thu_mua` | **2** 🔴 | **2** 🔴 | 2 |
| Mua hàng | 0 ✅ | 1 ✅ | 2 ✅ |

### 4.1 — YCMH rò phạm vi ✅ **TÁI HIỆN ĐƯỢC, ĐÃ VÁ**

Hai gốc khác nhau, vá cả hai:

**a) Lối tắt `thu_mua`.** `_sees_all_department_requests` mở cửa cho bất kỳ vai nào **có dòng
quyền** `thu_mua` — `scope_for(...) is not None` đúng kể cả khi phạm vi là `own`. Ai được cấp màn
Mua hàng là ô chọn phạm vi ở màn YCMH thành vô nghĩa. Người test đang làm Thu mua nên chắc chắn dính.

Lối tắt sinh ra hồi YCMH chưa có khoá riêng (cố ý, có ghi chú hẳn hoi). Từ 10/08 nó có
`yeu_cau_mua_hang` nên lối tắt thành thừa. **Luật nay**: vai có dòng `yeu_cau_mua_hang` thì
**chỉ nghe phạm vi của chính khoá đó**; vai chưa có (DB cũ) mới rơi về luật cũ.

**b) `own` không lọc theo người gửi.** Repo chỉ có cờ `filter_by_department`, nên `own` rơi xuống
dùng chung nhánh lọc theo phòng ⇒ thấy luôn yêu cầu của đồng nghiệp. Thêm tham số
`requested_by_user_id`.

Migration `0183` cấp bù `yeu_cau_mua_hang` phạm vi `all` cho vai đang có `thu_mua`, để bộ phận mua
hàng không mất hộp việc. Đã chạy thử trên Postgres thật rồi rollback: sạch.

Sau khi vá, đo lại đủ 12 ô đều đúng. Kiểm bằng đột biến: trả lại lối tắt ⇒ 1 test đỏ; bỏ lọc theo
người gửi ⇒ 2 test đỏ. Test giữ hàng rào: `test_pham_vi_yeu_cau_mua_hang.py`.

### 4.2 — Mua hàng rò phạm vi ❌ **KHÔNG TÁI HIỆN**

Màn Mua hàng lọc **đúng hoàn toàn**: `own` → 0 · `department` → 1 (cùng phòng) · `all` → 2. Khớp
với kết quả đo ở đợt 0.

Nhiều khả năng chủ chốt thấy YCMH rò (§4.1) rồi tưởng cả hai màn cùng bệnh. Đã thêm test đối chứng
`test_man_mua_hang_van_loc_dung_nhu_cu` để lần sau không vá nhầm sang đây.

### 4.3 — *Xem Nhật ký chấm công* — chờ thử lại

Nhiều khả năng cùng gốc với §1.7 ở chặng khác (đã vá). Cần chủ chốt bật lại và xác nhận.

---

## 5. Giải thích: *Đánh dấu đã chi lương*

Kỳ lương đi qua 3 nấc: **Nháp** → **Đã chốt** → **Đã chi**.

- **Chốt bảng lương** — "số tính xong, không sửa nữa". Việc của người tính lương (HCNS).
- **Đánh dấu đã chi** — "**tiền đã ra tới tay người lao động**". Việc của kế toán, sau khi thật sự
  chuyển khoản. Bấm xong kỳ khoá luôn; muốn mở lại phải huỷ đã chi trước.

Tách hai ô vì ngoài đời là hai người. Gộp một ô thì ai chốt được là **tự tuyên bố đã trả** — không
còn ai đối chiếu.

---

## 6. Thứ tự làm

| Đợt | Việc | Trạng thái |
|---|---|---|
| ~~A~~ | ~~§1.1+1.8 (4 nút mất) · §1.7 (3 công tắc không sáng)~~ | ✅ **XONG 11/08/2026** |
| ~~B~~ | ~~§4.1 · §4.2 đo rò phạm vi~~ | ✅ **XONG** — §4.1 tái hiện & vá, §4.2 bác bỏ |
| ~~C~~ | ~~§1.2 → §1.6 (5 lỗi còn lại)~~ | ✅ **XONG 11/08/2026** |
| ~~D~~ | ~~§2.2 → §2.5, §2.7 + §2.6 (trừ Lương)~~ | ✅ **XONG 11/08/2026** — §2.1 và §2.6-Lương vẫn treo chờ chốt |
| ~~E~~ | ~~§3 công tắc chết~~ | ✅ **XONG 11/08/2026** — làm kiểu tự sinh |

### Đợt D — đã làm gì

| Mục | Vá thế nào | Migration |
|---|---|---|
| §2.2 Tách *Yêu cầu chỉnh công* | Khoá riêng `yeu_cau_chinh_cong` (`read` + `approve`); 3 endpoint đổi khoá | **`0185`** |
| §2.3 Gộp 3 tab cấu hình chấm công | Vốn đã chung ô `cham_cong:update` — không phải sửa. Phạm vi *Tất cả* là tự nhiên: endpoint cấu hình không lọc theo phạm vi | — |
| §2.4 *Đi muộn* chỉ còn ô Duyệt | Danh sách đổi `di_muon:read` → `approve`; ô Xem/Thao tác thành công tắc chết ⇒ đợt E tự khoá | — |
| §2.5 *Phòng ban* lên trên | Dời `phong_ban` từ nhóm *Hệ thống* sang nhóm *Nhân sự*, đứng trước *Hồ sơ nhân sự* | — |
| §2.6 Khoá phạm vi | 7 màn khoá danh sách phạm vi hợp lý; chỉ còn một lựa chọn thì khoá luôn ô chọn. **Trừ Lương** | — |
| §2.7 Xin nghỉ về ô Tự phục vụ | Đã làm ở đợt C cùng §1.5 | `0184` |

`0185` **không cấp bù `di_muon:approve`** cho người đang chỉ có `read` — duyệt phiếu người khác nặng
hơn hẳn quyền xem, tự nâng cấp là mở cửa. Họ vẫn xem phiếu của mình qua ô Tự phục vụ; quản trị muốn
cho ai duyệt thì tick, hiện rõ trên ma trận.

### Đợt E — công tắc chết, làm kiểu tự sinh

Không chép tay danh sách. Mỗi lần `require_permission(...)` / `require_any_permission(...)` chạy lúc
nạp router là ghi vào `deps.O_QUYEN_DUOC_GAC`; `/api/rbac/modules` trả kèm `viec_co_tac_dung`; ma
trận **tắt + khoá + hover cảnh báo** những ô ngoài danh sách.

> *"Ô này chưa nối vào chức năng nào — bật cũng không mở thêm gì."*

Thêm cổng mới ⇒ ô tự sống lại. Gỡ cổng ⇒ ô tự chết. **Không ai phải nhớ cập nhật.**

Chỗ máy chủ hỏi quyền ở tầng service (`authz.can(...)`, không qua cổng router) phải khai tay trong
`O_QUYEN_GAC_O_SERVICE` — và có test đối chiếu với mã nguồn, gỡ `authz.can` mà quên xoá dòng khai
thì đỏ.

Rủi ro của cơ chế tự sinh là **khoá nhầm hàng loạt** nếu registry rỗng hoặc thiếu. `test_o_quyen_chet_tu_sinh.py`
canh đúng chỗ đó: registry phải > 80 cặp, 19 ô đang dùng được phải có mặt, 14 ô đã biết là chết phải
vắng mặt. Kiểm bằng đột biến: registry không ghi gì ⇒ 2 đỏ; khai bừa một ô chết thành sống ⇒ 3 đỏ.

### Đợt C — đã làm gì

| Mục | Vá thế nào | Migration |
|---|---|---|
| §1.2 Nghỉ phép | Thêm ô **Duyệt đơn nghỉ phép** + ô **Quản danh mục loại nghỉ** vào ma trận | — |
| §1.3 Xuất Excel | Endpoint đổi `read` → `export`; giao diện ẩn nút khi chưa cấp | — |
| §1.4 Cấu hình lương | Bỏ `|| canManage` — tab đi theo đúng ô *Xem cấu hình lương* | — |
| §1.5 Tự phục vụ | Tách **Xem** (`read`) / **Thao tác** (`create`); 8 đường ghi ở 6 router đổi sang `create`; xin nghỉ về chung ô này | **`0184`** ⚠️ |
| §1.6 YCMH Sửa/Huỷ | Nút đòi *(người tạo **và** có ô Thao tác)* | — |

⚠️ **`0184` là migration nguy hiểm nhất từ đầu đợt**: cột `self_service.can_create` xưa nay chưa ai
bật (nó vô nghĩa vì khoá chỉ dùng `read`), nên quên ánh xạ `can_create = can_read` là **cả nhà máy
không chấm công được**. Đo trên DB dev: 1 → 19 vai, đúng bằng số vai đang có ô Xem.

Cả `0183` và `0184` đều có test riêng, kiểm bằng đột biến — và chính lần kiểm đó phát hiện **ban
đầu chưa test nào giữ `0184`**: đột biến gỡ ánh xạ vẫn 17 test xanh. Đã bù 5 test.

---

## 7. Nghiệm thu

### 7.1 Đã vá (đợt A · B · C) — chủ chốt test lại

- [ ] Cấp ô *Duyệt / từ chối PMH* ở **Đơn mua hàng (Kế toán)** → nút **Duyệt** / **Từ chối** hiện
- [ ] Bật *Xem lương & BHXH* → Lưu → mở lại, công tắc **vẫn sáng** (tương tự *Sửa lương & BHXH*)
- [ ] Bật *Chấm bù / sửa công* → Lưu → mở lại, công tắc **vẫn sáng**
- [ ] Bật *Xem Nhật ký chấm công* → tab Nhật ký hiện (§4.3 — nghi cùng gốc, cần xác nhận)
- [ ] Cấp *Duyệt đơn nghỉ phép* → tab **Duyệt đơn** và **Lịch nghỉ** hiện
- [ ] Tắt *Thao tác* của **Tự phục vụ** → **không** chấm công được, **không** gửi được đơn nghỉ ·
      phiếu tăng ca · xin đi muộn · xin tạm ứng. Bật lại → làm được
- [ ] Chưa cấp *Xuất Excel danh sách* → nút ẩn **và** gọi thẳng `/api/employees/export.xlsx` bị chặn
- [ ] Bật *Thao tác* của **Lương** → tab *Cấu hình lương* **KHÔNG** tự hiện (phải cấp ô riêng)
- [ ] **YCMH** chọn phạm vi *Của tôi* → chỉ còn yêu cầu **do chính mình gửi**; *Cả phòng* → chỉ
      phòng mình, **kể cả khi vai có thêm ô Mua hàng**
- [ ] Tắt *Thao tác* của **Yêu cầu mua hàng** → nút *Sửa yêu cầu* / *Hủy yêu cầu* biến mất

### 7.2 Chưa làm — chờ chủ chốt test rồi quyết (§2.1 · §2.6-Lương)

- [ ] **§2.1** Vai có *Mua hàng: Xem + Thao tác* nhưng **không** tick *Sửa / đảo trạng thái đơn* →
      ba nút *Sửa số nhận* · *Mở lại đơn* · *Đóng đơn* phải ẩn; tick lên thì hiện.
      **Quyết**: giữ ô riêng hay gộp về ô Thao tác.
- [ ] **§2.6-Lương** Vai *Lương: Xem*, phạm vi *Cả phòng* → **đếm số dòng** bảng lương, so với
      admin. **Quyết**: có khoá phạm vi về *Tất cả* không (đây là mở rộng dữ liệu lương).

### 7.3 Còn lại của đợt D · E

- [ ] §2.2 → §2.5, §2.7 (thay đổi thiết kế không vướng quyết định)
- [ ] §3 — ô đã disable → hover ra đúng câu cảnh báo
- [ ] **§10.2** — dòng *Yêu cầu chỉnh công* chỉ còn **Xem** + **Duyệt** bật được; ba ô
      *Thao tác · Sửa · Xóa* xám (cần restart uvicorn mới thấy)

### 7.4 Chờ chủ chốt gật rồi mới làm

- [ ] **§10.3** — tắt nốt 15 ô chết ở 8 màn còn lại
- [ ] **§9** — Chốt công ⇄ Chốt lương (chủ chốt 12/08/2026: *"làm sau để tôi làm phân quyền cho
      xong đã"*). Quyết trước: chặn ở **Tính lương** hay ở **Chốt lương**
- [ ] **§10.4** — `kho:post` (nợ cũ, ngoài phạm vi 3 phân hệ)

---

## 8. Bài học — hàng rào chống tái phát

Vòng này lộ ra **một khuôn sai lặp 3 lần**: sửa quyền ở một chặng, quên chặng khác. Đường ống có
**5 chặng** — model → repo → `get_matrix` → `save_matrix` → schema API → giao diện — và mỗi lần sót
một chặng khác nhau:

| Lần | Cột | Sót ở chặng |
|---|---|---|
| 1 | `can_view_log` | schema API |
| 2 | `can_adjust`, `can_view_salary`, `can_edit_salary` | `get_matrix` |
| 3 | `ke_toan:approve`, `thu_mua:manage_status` | giao diện |

Hàng rào phải soi **đủ cả 5**, không phải 3 như guard cũ:

1. Mọi cột quyền có mặt ở **cả** `get_matrix` **và** `save_matrix` — soi riêng từng hàm.
2. Mọi cặp *(màn, ô quyền)* giao diện hỏi phải là cặp máy chủ thật sự gác.
3. Cả hai guard kiểm bằng **đột biến**: bỏ một cột/một cặp thì test phải đỏ. Guard không tự chứng
   minh mình có cắn thì cũng chỉ là một dòng xanh vô nghĩa.

---

## 9. Để sau — Chốt công ⇄ Chốt lương 🟡 **NGOÀI PHẠM VI VÒNG PHÂN QUYỀN**

Ghi 12/08/2026 theo yêu cầu chủ chốt: *"ghi vào prd rồi làm sau để tôi làm phân quyền cho xong đã"*.
**KHÔNG đụng tới cho tới khi phân quyền xong.** Toàn bộ phần này đã đo trên mã, không phỏng đoán.

### 9.1 Hiện trạng

Bấm **Chốt kỳ công** = với mỗi NV ghi một dòng vào `attendance_period_lines`, đóng băng **16 con số**
(tổng công · số ngày · phép có lương / không lương · ngày lễ · tổng giờ · phút tăng ca · ngày ca đêm ·
công lễ / nghỉ / thường / nghỉ-có-phép · tăng ca lễ / ngày nghỉ · phụ trội đêm · công theo từng ca).

| Màn | Đọc gì | Neo |
|---|---|---|
| **Bảng công tháng** | `monthly_timesheet()` — **luôn tính LIVE**, chốt hay chưa cũng vậy | `attendance_service.py:1332` |
| **Bảng lương** | `metrics_map()` — kỳ đã chốt thì đọc **ảnh chụp**, chưa chốt thì tính live | `attendance_service.py:1469` |

Vòng khoá hiện có **hở một chiều**:

| Đã có | Chưa có |
|---|---|
| Lương đã chốt / đã chi → **không mở lại được** kỳ công (`reopen_period`) | Công chưa chốt → **vẫn tính & chốt lương bình thường** |

### 9.2 Hai lỗ hổng

**Lỗ 1 — không có màn nào xem được ảnh chụp.** Màn Chấm công chỉ hiện `Khóa băng {N} NV`
(`ChamCongPage.tsx:6294`) — nói *chụp bao nhiêu dòng*, không mở ra xem dòng nào. Hệ quả: sau khi
chốt, ai chấm bù / xoá log thì **Bảng công hiện số mới, Bảng lương giữ số cũ**, và không có đường
đối chiếu ngoài việc đọc thẳng DB. Kế toán hỏi *"sao bảng công 26 mà lương tính 25"* thì chịu.

**Lỗ 2 — chi tiền được trên số công chưa chốt.** Tính lương → chốt lương → chi, mà kỳ công chưa
từng chốt. Lương chạy trên số live, mà số live vẫn sửa được **sau khi tiền đã ra**.

### 9.3 Quyết gì

| | **A. Chặn ở Tính lương** | **B. Chặn ở Chốt lương** ✅ khuyến nghị |
|---|---|---|
| Xem thử quỹ lương giữa tháng | ❌ mất | ✅ vẫn xem được (số nháp) |
| Tiền ra khi công chưa chốt | ❌ chặn | ❌ chặn |
| Ép duyệt sạch đơn treo | ngay từ đầu tháng | tới lúc chốt |
| Test phải sửa | ~30 chỗ gọi `/api/luong/generate` | ~2 chỗ |

B khép kín vòng mà không chặn xem thử: `chốt công → chốt lương → chi tiền`, chiều lùi đã khoá sẵn.

### 9.4 Bốn cái giá — biết trước khi làm

1. **Không phải một điều kiện mà là bốn.** `lock_period` (`attendance_service.py:1402`) chặn nếu tháng
   còn treo: đơn nghỉ phép · phiếu đi muộn/về sớm · yêu cầu chỉnh công. Nên *"phải chốt công trước"*
   thực chất = *"phải duyệt sạch mọi đơn của tháng"*. **Một đơn nghỉ bị quên của người đã nghỉ việc
   cũng chặn bảng lương cả nhà máy.** Đây là điểm cân nặng nhất.
2. **Mất tính thử** — chỉ đúng với phương án A.
3. **Màn Lương hiện KHÔNG biết trạng thái kỳ công** — `LuongPage.tsx` không đọc `period_status`.
   Không nối thì người dùng bấm nút chỉ nhận lỗi đỏ không hiểu vì sao. Phải có băng cảnh báo +
   nút nhảy sang màn Chấm công.
4. **Ngày treo** (bấm vào không bấm ra) **không** chặn chốt công — vẫn lọt vào ảnh chụp.

### 9.5 Khe hở còn lại nếu chọn B

Tính lương lúc 9h → ai đó chấm bù lúc 10h → chốt công 11h → chốt lương 12h: dòng lương vẫn là số
9h. Bịt bằng một câu so ngày — dòng lương sinh **trước** `attendance_periods.locked_at` thì báo
*"Tính lại trước khi chốt"*.

### 9.6 Đụng đâu nếu làm

`payroll_service.lock_period` (`:1469`, thêm guard) · `routers/payroll.py:661` (thông điệp lỗi) ·
`LuongPage.tsx` (đọc `period_status`, băng cảnh báo) · test mới cho cả hai chiều của vòng khoá.
Riêng **Lỗ 1** thì độc lập: cho Bảng công tháng hiện **số đã chụp** khi kỳ đã chốt, kèm nhãn
*"số đã chốt"* + nút xem số live.

---

## 10. Ô chết còn sót — đo lại 12/08/2026

Chủ chốt hỏi *"Thao tác của Yêu cầu chỉnh công tác dụng gì vậy"* → soi ra **không gì cả**, và soi
tiếp thì còn cả loạt ô cùng cảnh. §3 (đợt E) tưởng đã dọn sạch, thực ra chưa: danh sách ô chết
`deps.O_CHET_DA_XAC_MINH` **khai tay**, nên mọi module sinh sau đợt E đều lọt.

### 10.1 Cách đo — bốn nơi, thiếu một là hỏng

Một ô chỉ chết khi **không nơi nào** trong bốn nơi này hỏi tới:

| Nơi | Cú pháp |
|---|---|
| Cổng router | `require_permission("x", "y")` — registry tự gom lúc nạp |
| Tầng service | `authz.can(actor, "x", "y")` |
| Giao diện | `can("x", "y")` · `caps.get("x")?.can_y` |
| **Menu sidebar** | thuộc tính `module: "x"` / `modules: [...]` ⇒ `read` của khoá đó SỐNG |

⚠️ **Nơi thứ tư mới thêm 12/08/2026 và suýt gây lại tai nạn đợt E.** Lượt rà đầu chỉ soi ba nơi
nên kết luận nhầm `dashboard:read` và `dm_giay_vat_tu:read` là ô chết — tắt hai ô đó là **mất luôn
mục Dashboard và Hồ sơ của tôi khỏi menu của mọi vai**. Guard
`test_o_quyen_chet_tu_sinh.py` nay soi đủ bốn, kiểm bằng đột biến (khai bừa `dashboard:read` là
chết ⇒ đỏ).

### 10.2 Đã tắt

| Màn | Ô | Vì sao chết |
|---|---|---|
| **Yêu cầu chỉnh công** | Thao tác · Sửa · Xóa | Màn chỉ có 3 cửa: xem (`read`), duyệt và từ chối (cùng `approve`). Người GỬI yêu cầu đi ô **Tự phục vụ · Thao tác** (`self_service:create`, `attendance.py:716`) |

### 10.3 Chưa tắt — 15 ô, chờ chủ chốt gật

| Màn | Ô chết | Ghi chú đã soi |
|---|---|---|
| Dashboard | Thao tác · Sửa · Xóa | *Xem* SỐNG (sidebar gác 2 mục menu) |
| Nhật ký hoạt động | Thao tác · Sửa · Xóa | log chỉ để đọc |
| Vật liệu & Giá | Thao tác · Sửa · Xóa | màn này ghi bằng quyền **Kho** (`vat_lieu_kho.py` `MODULE = "kho"`); khoá `dm_giay_vat_tu` chỉ còn dùng làm **người đọc dự phòng** của menu YCMH |
| Người dùng | Thao tác · Xóa | không có endpoint tạo/xoá tài khoản — tài khoản sinh theo hồ sơ nhân viên |
| Khách hàng · Báo giá · Đơn hàng bán · Sản xuất | Xóa | không có endpoint xoá bản ghi gốc |

Sửa **một chỗ** (`deps.O_CHET_DA_XAC_MINH`) là cả 15 ô tự tắt + khoá + hover cảnh báo — ma trận đọc
thẳng danh sách đó (`role_service.py:176`). Không migration, không đụng dữ liệu. **Cần restart
uvicorn** thì màn mới thấy.

### 10.4 Nợ cũ, ngoài 3 phân hệ của vòng này

- **`kho:post`** — cổng chỉ tồn tại ở giao diện, ẩn nút *"Tạo & Ghi sổ"*. Không phải ô chết (nó có
  tác dụng thật), nhưng máy chủ không gác ⇒ gọi thẳng API vẫn qua. Ghi vào `CHO_PHEP`.
