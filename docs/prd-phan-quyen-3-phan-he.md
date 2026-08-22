# PRD — Phân quyền lại: Thu mua · Kế toán · Nhân sự & Lương

**Nguồn**: file `review Phân quyền lần 1.xlsx` của tester (3 sheet) + đối chiếu code ngày 10/08/2026.
**Phạm vi**: ĐÚNG ba phân hệ trên (chủ chốt 10/08/2026). Các phân hệ khác giữ nguyên, làm sau theo
cùng khuôn này.
**Chốt kiểu chia quyền**: **THEO TAB** — chủ chốt 10/08/2026: *"có các tab gì trong các module phải
cấp quyền mới thao tác được… cứ cấp quyền là được phép"*.

---

## 0. Tester tìm ra 5 nhóm bệnh, không phải 90 lỗi rời

Đọc kỹ ba sheet thì 90+ dòng ghi chú quy về đúng 5 gốc:

| # | Bệnh | Dẫn chứng nguyên văn từ file |
|---|---|---|
| 1 | **Không cấp quyền vẫn xem được** | *"Hệ thống trống không cấp quyền hiện đang cho xem"* · *"Mục Yêu cầu mua hàng tự động hiển thị ngay cả khi không cấp quyền"* · bật Dashboard thì *Hồ sơ của tôi* tự hiện |
| 2 | **Phạm vi không có tác dụng** | *"Phạm vi của tôi nhưng xem được tất cả"* — lặp ở **7 phân hệ**: Thu mua, Kế toán, Kho, Cấu hình danh mục ×5, Phòng ban |
| 3 | **Cấp Xem nhưng vẫn thao tác được** | *"Tại thao tác cho xem nhưng vẫn cho sử dụng button thêm và xóa"* — **11 màn**. Tăng ca: *"user vẫn thực hiện được chức năng gửi phiếu, sửa, hủy phiếu"* |
| 4 | **Có màn nhưng không có ô để bật** | *"Trang Mua hàng và Nhà cung cấp không nằm trong phân quyền nên không biết bật ở đâu"* · *"bật phân quyền vật liệu & giá không thấy có gì hiện ra hết"* |
| 5 | **Bật một ô, hiện ra một chùm** | Bật Kho hàng ⇒ hiện thêm Chủng loại giấy, Giấy, Vật tư in ấn, Khai báo kho · *"Khi bật xem thì tất cả các chức năng trong mục kế toán đều hiển thị"* |

### 0.1 Ba nguyên nhân gốc

1. **Không có "cấm mặc định".** Một số màn nằm trong danh sách *ai đăng nhập cũng vào*; một số
   endpoint chỉ đòi đăng nhập. Đúng ra phải ngược lại: **không có ô quyền = không vào**, tự phục vụ
   là ngoại lệ **có tên rõ ràng**.
2. **Ma trận không phủ hết màn.** 34 màn nhưng chỉ ~20 ô. Chỗ thiếu thì đi mượn ô của module khác —
   Mua hàng mượn Kho, Chấm công mượn Nhân sự, Lương mượn **phạm vi** của Nhân sự. Người cấp quyền
   không thể đoán ra.
3. **Chặn sai tầng.** Nhóm 3 là ẩn nút mà máy chủ vẫn nhận lệnh ghi; nhóm 2 là máy chủ nhận tham số
   phạm vi nhưng **không lọc dữ liệu theo nó**.

### 0.2 ĐỢT 0 — đã dựng lại từng ca bằng test thật (10/08/2026)

Không tin cả tester lẫn suy đoán của mình. Dựng vai mới với đúng bộ quyền cần thử, gọi thẳng API,
đọc kết quả. Probe nằm ở `backend/tests/test_probe_dot0.py` (**tạm, xoá sau khi đọc xong**).

| Ca của tester | Kết quả đo | Kết luận |
|---|---|---|
| *"Phạm vi của tôi nhưng xem được tất cả"* | Admin thấy 1 phiếu · người scope `own` thấy **0** | ✅ **KHÔNG tái hiện** — Thu mua LỌC ĐÚNG |
| *"Cho xem nhưng vẫn thêm/xoá được"* | Thêm NCC · gửi phiếu tăng ca · gửi đơn nghỉ đều **403** | ✅ **Máy chủ chặn đúng** |
| *"Phải set trưởng phòng mới có full chức năng"* | Vai chỉ có ô *Duyệt*, KHÔNG làm trưởng phòng ⇒ vào được cả *Duyệt đơn* lẫn *Lịch nghỉ* | ✅ **KHÔNG có quyền ngầm** — tester nhầm với việc gán VAI |
| *"Không cấp quyền vẫn xem được"* | Vai trống trơn gọi 9 endpoint: **7 chặn 403**, **2 vào được** | 🔴 **TÁI HIỆN — đúng 2 chỗ** |
| *Chốt kỳ công không giới hạn phạm vi* (tôi tự nêu 09/08) | Người scope `own` **chốt được**, ảnh chụp ra **2 dòng thuộc 2 phòng ban** | 🔴 **XÁC NHẬN — mìn chờ có thật** |

#### Hai cửa thật sự hở

| Màn | Vai trống trơn |
|---|---|
| **Yêu cầu mua hàng** (`/api/department-purchase-requests`) | 🔴 vào được |
| **Nội quy công ty** (`/api/noi-quy`) | 🔴 vào được |
| Phiếu mua hàng · Nhà cung cấp · Đơn mua hàng · Phiếu chi · Công nợ phải trả · Hồ sơ nhân sự · Loại nghỉ | ✅ chặn 403 |

#### ⚠️ Đính chính bản nháp đầu

Bản nháp trình chủ lúc đầu ghi *"Thu mua KHÔNG lọc phạm vi"*. **SAI.** Tôi đọc `list_purchase_requests`
trong khung 30 dòng và không thấy `actor`, trong khi nó nằm ở **dòng cuối** lời gọi
(`routers/purchases.py:350` — `actor=user`). Test thật đã bác bỏ.

Đây đúng là lý do đợt 0 tồn tại: **đọc lướt code rồi kết luận là cách nhanh nhất để giao dev đi sửa
thứ không hỏng.**

### 0.3 Quy mô thật sau khi đo — nhẹ hơn bản nháp nhiều

| Việc | Mức | Ghi chú |
|---|---|---|
| Đóng 2 cửa hở (Yêu cầu mua hàng · Nội quy) | 🔴 thật, **nhỏ** | Vài dòng |
| **Chốt kỳ công không giới hạn phạm vi** | 🔴 thật, **nguy hiểm nhất** | Đã xác nhận bằng test |
| Ẩn nút khi chỉ có quyền Xem — 11 màn | 🟠 **giao diện**, KHÔNG phải bảo mật | Bấm vào nhận 403: khó chịu, trông như hỏng, nhưng **không rò dữ liệu, không rò quyền ghi** |
| Tách 38 ô theo tab | 🟠 việc chính | |
| Bảng vai mẫu | 🟢 | |

**Hai việc bản nháp xếp là "đỏ, nặng nhất" — phạm vi không lọc và chặn ghi ở máy chủ — KHÔNG TỒN
TẠI.** Giữ nguyên bản nháp là giao dev đi sửa hai thứ đang chạy đúng.

---

## 1. Ba luật xuyên suốt

**Luật 1 — Không có ô nào bật thì không vào được.** Bỏ hẳn danh sách "ai đăng nhập cũng thấy".
Tự phục vụ trở thành **một ô nhìn thấy được**, không phải luật ngầm.

**Luật 2 — Xem và Thao tác là hai ô khác nhau, và chặn ở MÁY CHỦ.**
Ẩn nút chỉ là lịch sự với người dùng. Hàng rào thật nằm ở endpoint.

**Luật 3 — Phạm vi phải lọc thật, và phải có test.**
Mỗi ô có phạm vi ⇒ endpoint tương ứng BẮT BUỘC có test *người phạm vi hẹp thấy ít hơn người phạm vi
rộng*. Khuôn đã có: test badge Thu mua và test xuất Excel nhân sự (làm 08-09/08/2026).

---

## 2. THU MUA — 6 ô · ✅ **XONG 10/08/2026**

Ba màn nay là **ba khoá module riêng**, mỗi khoá có ô Xem / Thêm / Sửa / Xoá + phạm vi độc lập:

| Khoá | Màn | Gác những gì |
|---|---|---|
| `yeu_cau_mua_hang` | Yêu cầu mua hàng | Xem danh sách + chi tiết · Tạo · Sửa · Huỷ |
| `thu_mua` | Mua hàng (giữ nguyên khoá cũ) | Tab *Yêu cầu chờ xử lý* + tab *Phiếu mua hàng* · lập phiếu · đợt giao · hoá đơn |
| `nha_cung_cap` | Nhà cung cấp | Danh mục NCC · Bảng giá vật tư · Nhập/Xuất Excel |

Giữ nguyên khoá `thu_mua` cho màn Mua hàng là **cố ý**: đổi khoá thì mọi hàng `role_permissions` đang
có trỏ vào hư không — mất quyền hàng loạt mà không ai báo.

**Hai đường tắt đã bị gỡ** ở màn *Yêu cầu mua hàng* (đây mới là gốc của bệnh "quyền không ăn khớp"):

1. **Mượn quyền màn khác** — trước đây bật `thu_mua/can_request` là mở luôn cửa lập yêu cầu. Nhìn ma
   trận quyền không đoán ra được.
2. **Quyền ngầm theo chức danh** — ai đang là **trưởng phòng** (`departments.head_user_id`) thì tự
   động lập được yêu cầu chi tiền, **không có ô nào để tắt**, và đổi trưởng phòng là quyền tự chuyển
   người theo. Đúng chỗ chủ chốt nói *"gán trưởng phòng là có mấy quyền — bỏ, phải cấp quyền mới
   thao tác"*.

Nay chỉ còn **một** câu hỏi: *vai này có ô **Yêu cầu mua hàng · Thêm** không?*

**Lệnh chuyển đổi dữ liệu `0177_tach_module_thu_mua`** — bắt buộc, vì tách khoá mà không sao chép là
sáng hôm sau kế toán/thu mua mất sạch quyền:

| Bước | Làm gì |
|---|---|
| 1 | Thêm 2 khoá mới vào danh mục module (thiếu là bước 2 vỡ khoá ngoại) |
| 2 | **Sao chép nguyên** mọi hàng quyền `thu_mua` sang 2 khoá mới — đủ 37 cờ + phạm vi |
| 3 | **Cấp bù** `yeu_cau_mua_hang` (Xem/Thêm/Sửa, phạm vi *cả phòng*) cho vai của **trưởng phòng đang tại vị** — bù đúng cái quyền ngầm vừa gỡ, nhưng từ nay **hiện trên ma trận và gỡ được** |

Chạy lại không đẻ hàng trùng. Có bộ test riêng `test_migration_0177_tach_thu_mua.py` (3 test) — vì
`drop_all/create_all` của fixture test **không chạy migration**, sai SQL ở đây thì test API vẫn xanh
mà DB thật vỡ. Đã kiểm bằng đột biến: bỏ bước 3 ⇒ 1 test đỏ; đánh rơi `scope` khi sao chép ⇒ 3 test đỏ.

**Đã kiểm**: danh sách phiếu mua **LỌC PHẠM VI ĐÚNG** (§0.2) — không phải sửa.

**Test giữ hàng rào**: `test_ba_man_thu_mua_gac_bang_ba_khoa_doc_lap` (cấp đúng một màn ⇒ hai màn kia
403) · `test_khong_co_quyen_thi_khong_lap_duoc_yeu_cau_mua_hang` (tài khoản chỉ đăng nhập ⇒ 403 cả ba
đường tạo/sửa/huỷ).

---

## 3. KẾ TOÁN — 6 màn · ✅ **XONG 10/08/2026**

| Khoá | Màn | Ô quyền |
|---|---|---|
| `ke_toan` (giữ khoá cũ) | Đơn mua hàng | Xem |
| `phieu_chi` | Phiếu chi / UNC | Xem · **Lập phiếu** ⚠️ · Huỷ · In-xuất |
| `phieu_thu` | Phiếu thu | Xem · **Lập phiếu** ⚠️ · Xác nhận đã thu · Huỷ · In-xuất |
| `cong_no_phai_tra` | Công nợ phải trả | Xem |
| `cong_no_phai_thu` | Công nợ phải thu | Xem |
| `tk_ngan_hang` | Tài khoản ngân hàng | Xem · Thao tác |

Bệnh #5 của tester (*bật Xem là hiện hết mọi chức năng kế toán*) tan: `can_read` nay chỉ mở **một**
màn. Duyệt PMH vẫn nằm ở `thu_mua · approve` — cố ý, để kế toán không tự duyệt khoản chi rồi tự viết
phiếu chi.

### Chỗ khác 0177: PHẢI ÁNH XẠ ĐỘNG TỪ

Khoá cũ dùng `can_approve` làm **cờ vạn năng** cho *lập phiếu chi* · *lập phiếu thu* · *gán chứng
từ* — nhìn ma trận tưởng là quyền duyệt, thật ra là quyền cho tiền ra. Khoá mới gọi đúng tên:
**LẬP phiếu = cột Thêm** (`can_create`).

Vì đổi tên động từ nên migration `0178_tach_module_ke_toan` **không được sao chép nguyên xi**:

| Đích | Lấy từ |
|---|---|
| `phieu_chi.can_create` · `phieu_thu.can_create` | `can_create` **HOẶC** `can_approve` cũ |
| `tk_ngan_hang.can_update` | `can_update` **HOẶC** `can_approve` cũ (TK nhà cung cấp trước gác bằng `approve`) |
| mọi cờ + phạm vi còn lại | chép nguyên |

Sai một trong hai chiều đều hỏng, và hỏng theo hai kiểu khác nhau:
- **Chép nguyên xi** ⇒ kế toán mở màn ra mà không bấm được nút nào.
- **Ánh xạ vống lên** ("cứ có `ke_toan` là được lập phiếu") ⇒ mở cửa cho tiền ra, tệ hơn cái đang sửa.

Có test cho **cả hai** chiều, kiểm bằng đột biến: bỏ ánh xạ ⇒ đỏ · ánh xạ vống ⇒ đỏ · rơi phạm vi ⇒
4 test đỏ.

### Đóng nốt cửa hở còn sót

`yeu-cau-mua-hang` vẫn nằm trong danh sách "ai đăng nhập cũng thấy" của thanh bên — máy chủ đã chặn
từ lát Thu mua nhưng menu vẫn hiện cho cả công ty. Đã gỡ. Danh sách đó giờ chỉ còn *Nội quy công ty*.

### Test giữ hàng rào

`test_phan_quyen_ke_toan_api.py` — cấp Xem đúng một màn ⇒ **năm màn kia 403** (chạy chéo đủ 6×5 cặp);
Xem không kéo theo Lập ở Phiếu chi · Phiếu thu · Tài khoản ngân hàng.

---

## 4. NHÂN SỰ & LƯƠNG — ✅ **XONG 10/08/2026**

| Khoá | Màn | Ô quyền |
|---|---|---|
| `self_service` | Tự phục vụ (xuyên màn) | Xem — **bật sẵn cho mọi vai mới** |
| `nhan_su` (giữ khoá) | Hồ sơ nhân sự | Xem · Thêm/Sửa/Xoá · Vòng đời · Điều chuyển · Xem-Sửa lương · Duyệt YC cập nhật · Xuất Excel |
| `cham_cong` | Chấm công | Xem · **Cấu hình** · **Chấm bù** ⚠️ · **Chốt kỳ** ⚠️ |
| `nghi_phep` | Nghỉ phép | Xem · **Duyệt** ⚠️ · Quản loại nghỉ |
| `tang_ca` | Tăng ca | Xem · **Duyệt** ⚠️ |
| `di_muon` | Đi muộn / về sớm | Xem · **Duyệt** ⚠️ |
| `luong` | Lương | Xem · Sửa · **Chốt bảng lương** ⚠️ · Duyệt tạm ứng · Cấu hình · Xuất |
| `noi_quy` | Nội quy công ty | Xem (**bật sẵn cho mọi vai mới**) · Thêm · Xoá |
| `phong_ban` | Phòng ban | Xem · Thao tác (gồm Đặt trưởng phòng) |

### Bốn thứ đổi, mỗi thứ vá một bệnh

**1. Tự phục vụ thành ô thật.** 34 endpoint `/me` của 6 router trước đây chỉ đòi ĐĂNG NHẬP —
luật ngầm, không có ô nào để tắt. Đây là gốc của cái tester ghi ở Tăng ca: *"phân quyền xem
nhưng user vẫn gửi, sửa, huỷ phiếu được"* — bệnh không nằm ở `tang_ca` mà ở đường `/me` không gác gì.
Nay `RoleRepository.O_MAC_DINH` bật sẵn ô này (và `noi_quy`) cho **mọi vai mới**, nên không ai mất
việc hằng ngày; khác ở chỗ quản trị **gỡ được**.

**2. Màn Chấm công tách khoá riêng.** Trước dùng chung `nhan_su`: cấp quyền xem hồ sơ là mở luôn
bảng công cả công ty.

**3. Chốt kỳ công tách khỏi Chấm bù** (`can_lock` ≠ `can_adjust`). Một cú bấm chụp ảnh bảng công
TOÀN CÔNG TY thành số liệu chốt; *Mở lại kỳ* thì xoá sạch ảnh chụp đó. Cộng với hàng rào phạm vi
đã vá ở đợt 1, nay muốn chốt kỳ phải có **ô riêng + phạm vi cả công ty**.

**4. Ba tab cấu hình khoá cả ĐƯỜNG ĐỌC.** Trước: giao diện ẩn tab nhưng máy chủ chỉ đòi `read`,
nên vai chỉ-xem gọi thẳng API là đọc được toạ độ + bán kính mọi điểm chấm công và lưới phân ca cả
tháng. Nay `/attendance/locations`, `/attendance/shift-plan`, `/calendar/config`,
`/calendar/special-days` đòi ô **Cấu hình chấm công**.

**5. Lương thôi mượn phạm vi của Nhân sự** — `payroll._scope_for` nay đọc phạm vi của chính khoá
`luong`. Migration chép phạm vi `nhan_su` sang `luong` để giữ nguyên hành vi hôm nay.

### Lệch so với bản PRD đầu — nói rõ

- PRD tách *Bảng công tháng · Xem* và *Nhật ký chấm công · Xem* thành **hai** ô. Đang gộp làm một
  (`cham_cong · Xem`), vì tách thêm phải **đẻ một cột boolean mới trong DB** cho đúng một tab.
  Muốn tách thật thì nói, làm sau được.
- *Yêu cầu chỉnh công · Duyệt* dùng chung ô **Chấm bù** (`can_adjust`) — duyệt một yêu cầu chỉnh
  công chính là chấm bù, chỉ khác chỗ ai bấm nút.

### ⚠️ Hệ quả phải xử lý trước khi lên prod

Tài khoản **chưa gán vai trò** nay không tự chấm công được nữa (không vai = không ô nào, giống mọi
module khác). Đo trên DB dev: **1 tài khoản** có hồ sơ NV mà chưa gán vai. Đếm trên prod:

```sql
SELECT u.username, e.full_name FROM users u
JOIN employees e ON e.user_id = u.id
WHERE u.is_active AND u.role_id IS NULL;
```

Gán vai cho những người này (màn *Hồ sơ nhân sự* → tab *Tài khoản & Quyền*) trước khi deploy.

### Test giữ hàng rào

`test_phan_quyen_nhan_su_luong_api.py` — 8 test: vai mới có sẵn Tự phục vụ · gỡ ô là chặn cả 6
đường `/me` lẫn đường ghi · `nhan_su` không mở được bảng công và ngược lại · chỉ-xem không đọc được
cấu hình · chấm bù không chốt được kỳ · Lương có phạm vi riêng · Nội quy gỡ được.

Migration `0179` có 6 test riêng, kiểm bằng đột biến: bỏ ánh xạ `adjust→lock` ⇒ đỏ · ánh xạ vống ⇒
đỏ · bỏ chép phạm vi Lương ⇒ đỏ · bỏ cấp Tự phục vụ + Nội quy ⇒ 2 đỏ.

---

## 4-cũ. Bản kế hoạch chi tiết (giữ để đối chiếu) — 24 ô

### 4.1 Tự phục vụ — 1 ô, cấp cho mọi vai

| Ô | Mở tab nào |
|---|---|
| **Tự phục vụ** | *Chấm công của tôi* · *Công của tôi* · *Phiếu đi muộn của tôi* · *Đơn nghỉ của tôi* · *Phiếu tăng ca của tôi* · *Phiếu lương của tôi* · *Tạm ứng của tôi* |

Đây chính là chỗ đang **không gác gì**. Biến thành một ô nhìn thấy được: bật thì thợ tự chấm công,
tắt thì không. Vẫn giữ ba hàng rào cũ (phải có hồ sơ NV nối tài khoản · phải trong bán kính điểm
chấm công · phải đúng khung giờ ca) — chúng chống lạm dụng, không phải chống truy cập.

### 4.2 Chấm công — 6 ô

| Ô | Mở tab / nút nào |
|---|---|
| Bảng công tháng · Xem | Tab *Bảng công tháng* |
| Nhật ký chấm công · Xem | Tab *Nhật ký chấm công* |
| **Chấm bù / sửa công** ⚠️ | Sửa lượt bấm · chấm bù |
| **Chốt kỳ công** ⚠️🔴 | Nút *Chốt kỳ* · *Mở lại kỳ* |
| Yêu cầu chỉnh công · Duyệt | Tab *Yêu cầu chỉnh công* |
| Cấu hình chấm công | Tab *Điểm chấm công* + *Khai ca* + *Lịch & Ngày lễ* |

Ba tab cấu hình gộp một ô vì cùng một việc: khai hạ tầng chấm công.

**Hai lỗi đã biết của nhóm này** (báo chủ 09/08/2026):
- ~~**Chốt kỳ công KHÔNG giới hạn phạm vi**~~ — ✅ **ĐÃ VÁ 10/08/2026** (đợt 1). Trước đó: người
  scope `own` chốt được, ảnh chụp ra 2 dòng thuộc 2 phòng ban. Nay chặn ở
  `_chan_neu_khong_toan_cong_ty`. Ghi lại để hiểu vì sao có hàng rào đó, đừng gỡ. (Lỗi cũ ở `routers/attendance.py:557-574` không truyền scope;
  `attendance_service.py:1415` gọi `monthly_timesheet(year, month)` trần). Một cú bấm đóng băng đầu
  vào lương **toàn nhà máy**; *Mở lại kỳ* thì xoá sạch số liệu chốt. Hôm nay chưa nổ vì chỉ Giám đốc
  và TP HCNS có quyền, cả hai phạm vi cả công ty — **nổ vào đúng ngày phân quyền hẹp lại**.
- **Ba tab cấu hình ẩn ở giao diện nhưng máy chủ chỉ đòi quyền Xem** — cấp quyền Nhân sự mức chỉ-xem
  thì người đó không thấy tab, nhưng đọc được toạ độ + bán kính mọi điểm chấm công, lưới phân ca cả
  tháng, lịch sử đổi ca. Đường ghi gác đúng, chỉ đường đọc hở.

### 4.3 Nghỉ phép — 3 ô

| Ô | Mở tab nào |
|---|---|
| Xem đơn của tổ / phòng | Danh sách đơn |
| **Duyệt** ⚠️ | Tab *Duyệt đơn* **và** tab *Lịch nghỉ* |
| Quản danh mục loại nghỉ | Tab *Loại nghỉ* |

Giữ chốt 29/07/2026: **tổ trưởng duyệt đơn trong tổ mình**, không đụng danh mục loại nghỉ.

### 4.4 Tăng ca — 2 ô · Xem · **Duyệt** ⚠️
Tester bắt: *"phân quyền xem nhưng user vẫn gửi, sửa, huỷ phiếu được"* ⇒ Luật 2.

### 4.5 Đi muộn / về sớm — 2 ô · Xem · **Duyệt** ⚠️
Gồm cả *nghỉ nửa buổi* — cùng một loại phiếu, không tách.

### 4.6 Lương — 5 ô

| Ô | Mở tab / nút nào |
|---|---|
| Bảng lương · Xem | Tab *Bảng lương* |
| Lương nhân viên · Xem & sửa | Tab *Lương nhân viên* + tab *Khoán* |
| **Chốt bảng lương** ⚠️ | Nút chốt kỳ lương |
| Tạm ứng · **Duyệt** ⚠️ | Tab *Tạm ứng* |
| Cấu hình lương | Tab *Cấu hình lương* (3 tab con) |

**BỎ HẲN việc Lương mượn phạm vi của Nhân sự.** Lương có phạm vi riêng. Hiện cấp quyền Lương mà quên
cấp Nhân sự thì người đó tụt về *chỉ mình* — không ai đoán ra được.

### 4.7 Ba màn còn lại — 7 ô

| Màn | Ô |
|---|---|
| Hồ sơ nhân sự | Xem · Thao tác vòng đời (vào/nghỉ/điều chuyển) · Xuất Excel |
| Phòng ban | Xem · Thao tác (gồm *Đặt trưởng phòng*) |
| Nội quy công ty | Xem · Thao tác — hiện đang hiện với **mọi người** |

---

## 5.1 ĐỢT 4 — kết quả, và một lỗ hổng tìm thêm được

**Chốt bảng lương** nay là ô `luong · can_lock` riêng, **và** kèm hàng rào phạm vi cả công ty.

**Lỗ hổng đo được 10/08/2026 — cùng khuôn sai với Chốt kỳ công, ở phân hệ khác.** Bốn endpoint
`/luong/lock`, `/reopen`, `/pay`, `/unpay` dùng chung ô `can_lock` và **không kiểm phạm vi**. Dựng
vai phạm vi `own` rồi bấm: kỳ lương chuyển `locked`, bấm tiếp chuyển `paid` — tức tuyên bố **đã trả
tiền cho toàn bộ người lao động**. Kỳ lương là MỘT bản ghi cho cả công ty (`payroll_periods` khoá
theo năm+tháng) nên không có khái niệm "chốt phần của tổ mình".

**Ô thứ 5, không có trong kế hoạch ban đầu**: *Đánh dấu đã chi lương* (`can_manage_status`) tách
khỏi *Chốt*. Chốt = số đã tính xong; Đã chi = **tiền đã ra tới tay người lao động**, và nó khoá luôn
kỳ (muốn mở lại phải huỷ đã chi trước). Ngoài đời hai người: người tính lương chốt số, kế toán mới
xác nhận đã trả. Gộp một ô thì ai chốt được là tự tuyên bố đã trả — không còn ai đối chiếu.

Migration `0180` ánh xạ `can_manage_status = can_lock` cũ để không ai mất việc. 4 đột biến đều bị
bắt: gỡ hàng rào phạm vi ⇒ đỏ · gộp lại một ô ⇒ đỏ · migration vống lên ⇒ đỏ · migration không ánh
xạ ⇒ đỏ.

### 5.2 Tách "Nhật ký chấm công · Xem" (chủ chốt duyệt 11/08/2026)

Đây là chỗ §4 đã ghi là *lệch so với PRD*; chủ chốt trả lời **"tách ra luôn không sao"** nên đã làm
thật: thêm cột `role_permissions.can_view_log` (migration `0181` + `DB_SCHEMA.md`).

Vì sao đáng một cột DB: **Bảng công tháng** là số công đã tổng hợp; **Nhật ký** là *từng lượt bấm*
kèm giờ và toạ độ của từng người, cả xưởng — ai đi sớm về muộn hôm nào, đọc là biết. Người cần xem
công để tính lương không đương nhiên cần đọc dấu chân từng người.

Migration ánh xạ `can_view_log = can_read` của `cham_cong` — cột mới mặc định `false`, không ánh xạ
là sáng hôm sau tab Nhật ký trắng trơn với tất cả mọi người, kể cả HCNS.

*Yêu cầu chỉnh công · Duyệt* giữ nguyên dùng chung ô **Chấm bù** — chủ chốt xác nhận: duyệt một yêu
cầu chỉnh công chính là chấm bù, chỉ khác ai bấm nút.

---

## 5. Bốn việc LUÔN tách ô riêng

Dù chia theo tab hay theo màn, bốn việc này không bao giờ gộp chung với quyền sửa:

| Việc | Vì sao |
|---|---|
| **Duyệt đơn mua hàng** | Mở đường cho tiền ra |
| **Lập phiếu chi** | Tiền rời két |
| **Chốt kỳ công** | Đóng băng đầu vào lương, khó gỡ |
| **Chốt bảng lương** | Chốt số trả cho người lao động |

---

## 6. Thứ tự làm

| Đợt | Việc | Vì sao đứng đây |
|---|---|---|
| ~~0~~ | ~~Dựng lại các ca của tester~~ | ✅ **XONG 10/08/2026** — xem §0.2 |
| ~~1~~ | ~~Vá **chốt kỳ công không giới hạn phạm vi**~~ | ✅ **XONG 10/08/2026.** *Chốt kỳ* và *Mở lại kỳ* nay đòi phạm vi **cả công ty**; phạm vi tổ/phòng nhận 403 kèm câu chỉ đường. Có test chính thức `test_chot_ky_cong_doi_pham_vi_toan_cong_ty`, đã kiểm bằng đột biến (gỡ hàng rào ⇒ test đỏ) |
| ~~2~~ | ~~Đóng 2 cửa hở: **Yêu cầu mua hàng** · **Nội quy công ty**~~ | ✅ **XONG 10/08/2026** — cả hai đã có ô riêng; danh sách "ai đăng nhập cũng thấy" nay **RỖNG** |
| ~~3~~ | ~~Tách ô theo §2-§4 + đóng cửa mặc định (Luật 1)~~ | ✅ **XONG 10/08/2026** — Thu mua (§2) · Kế toán (§3) · Nhân sự & Lương (§4) |
| ~~4~~ | ~~⚠️ Tách 4 việc nguy hiểm ra ô riêng~~ | ✅ **XONG 10-11/08/2026** — Duyệt đơn mua hàng (`thu_mua·approve`) · Lập phiếu chi (`phieu_chi·create`) · Chốt kỳ công (`cham_cong·lock`) · Chốt bảng lương (`luong·lock`). **Thêm ô thứ 5 không có trong kế hoạch**: *Đánh dấu đã chi lương* (`luong·manage_status`) — xem §5.1 |
| ~~5~~ | ~~🟠 Ẩn nút "xem mà thấy nút"~~ | ✅ **XONG 11/08/2026** — xem §5.3 |
| ~~6~~ | ~~**Bảng vai mẫu**~~ | ✅ **XONG 11/08/2026** — 5 mẫu, xem §6.1 |

**Tổng 38 ô** cho ba phân hệ.

### Cái giá phải trả, nói trước

Chia theo tab thì cấp quyền cho một vai mới mất khoảng **10–15 phút** thay vì 3 phút. Bù bằng **bảng
vai mẫu** ở đợt 5: chọn mẫu → ra sẵn bộ quyền → chỉnh vài ô nếu cần.

Nếu bỏ đợt 5 thì rủi ro có thật: ma trận dài, người ta cấp bừa cho xong, **còn lỏng hơn hiện tại**.

### 5.3 ĐỢT 5 — ẩn nút khi không có ô

Máy chủ đã chặn từ các đợt trước; đây là phần giao diện: đừng bày nút rồi để người dùng bấm xong mới
ăn 403 — nhìn như hệ thống hỏng chứ không như "anh không có quyền".

**Soi lại bằng máy** thay vì tin danh sách "11 màn" của tester: quét 15 màn của ba phân hệ, tìm nút
hành động không có lá chắn quyền ở trên. Phần lớn báo động là giả (nút "Hủy" của hộp thoại, nút đổi
tab, nút xoá dòng trong form đã gác ở cửa vào). Thật sự phải sửa **hai nhóm**:

**Nhóm A — nút TỰ PHỤC VỤ.** Từ đợt 3 `self_service` là ô quyền thật, tắt được; giao diện chưa hề
hỏi ô đó nên vai bị gỡ vẫn thấy đủ nút. Thêm hook `useSelfService()` rồi gác:

| Màn | Ẩn khi không có ô |
|---|---|
| Chấm công | tab *Chấm công của tôi* · *Công của tôi* · *Đi muộn/về sớm* (tab này vẫn hiện với người DUYỆT) |
| Tăng ca | tab *Phiếu của tôi* + nút *+ Gửi phiếu* |
| Nghỉ phép | tab *Đơn của tôi* |
| Lương | tab *Phiếu lương của tôi* · *Tạm ứng của tôi* |
| Hồ sơ của tôi | nút *Sửa* · *+ Gửi đề nghị* · *Cần đổi tên?* |

**Nhóm B — nút thao tác trên dữ liệu người khác.** Màn *Mua hàng*: mọi người xem đơn đều thấy
*Sửa đợt giao* / *Xoá đợt giao* — nay gác `ghiDuoc` (= quyền sửa + đơn đang ở trạng thái ghi được).
Nút *Nhập kho* gác `kho:request`.

**Một lỗi tự gây rồi tự bắt**: ban đầu gác *Nhập kho* bằng `kho:create`. Sai — nút đó nhảy sang tab
**Đề nghị** của màn Kho, mà bộ phận mua hàng có `request` chứ không có `create`; gác nhầm là giấu nút
của chính người cần dùng nó nhiều nhất. Đã đổi về `kho:request`.

**Nghiệm thu trên hệ thống thật**: dựng một vai bị gỡ ô Tự phục vụ → đăng nhập → 4 màn Chấm công ·
Nghỉ phép · Tăng ca · Lương **không còn nút tự phục vụ nào**; đăng nhập lại bằng tài khoản có ô →
đủ cả 4 màn. Hai chiều đều đo, không chỉ chiều "đã ẩn".

---

## 6.1 ĐỢT 6 — Bảng vai mẫu

Năm mẫu, hiện thành một dãy nút ngay trên ma trận quyền (màn *Phòng ban → Vai trò & Quyền*), cả ở
form THÊM vai lẫn SỬA vai:

| Mẫu | Cấp gì | Cố ý KHÔNG cấp |
|---|---|---|
| **Công nhân** | Tự phục vụ + nội quy + tự gửi đơn nghỉ / tăng ca / đi muộn, tất cả phạm vi *chỉ mình* | mọi thứ khác |
| **Tổ trưởng** | Công nhân + xem bảng công & nhật ký của tổ, duyệt đơn của tổ, đề nghị vật tư, lập YCMH | **Chấm bù · Chốt kỳ công** |
| **HCNS** | Hồ sơ nhân sự, chấm công toàn công ty (chấm bù + chốt kỳ), duyệt đơn, tính & **chốt bảng lương** | **Đánh dấu đã chi lương** |
| **Kế toán** | Đơn mua hàng (xem), phiếu chi, phiếu thu, công nợ, TK ngân hàng, **đánh dấu đã chi lương** | **Duyệt đơn mua hàng · Chốt bảng lương** |
| **Thu mua** | Phiếu mua, nhà cung cấp + bảng giá, yêu cầu mua hàng | **Duyệt phiếu mua của chính mình** |

Ba cột "cố ý KHÔNG cấp" chính là chỗ mẫu **dạy lại luật tách vai** cho người cấp quyền: HCNS chốt
SỐ, kế toán xác nhận TIỀN ĐÃ RA; ai đề xuất chi tiền thì không được là người đồng ý chi. Có test
giữ đúng ba điều đó — sửa mẫu cho "tiện" là test đỏ.

**Chỉ đọc.** `GET /api/roles/templates` (gác `vai_tro:read`) trả ma trận ĐẦY ĐỦ; giao diện điền vào
bảng đang mở, quản trị xem lại rồi mới bấm Lưu — vẫn đi qua `PUT /roles/{id}/permissions` gác
`vai_tro:manage_permissions` như cũ. Chọn nhầm mẫu không hỏng gì vì chưa Lưu thì chưa có gì đổi.

### Hai lỗi tìm được nhờ làm đợt này

**1. Áp mẫu GỠ MẤT hai ô mặc định.** Ma trận mẫu là bản đầy đủ và giao diện thay sạch, nên khoá nào
mẫu không khai sẽ về TẮT — kể cả *Tự phục vụ* và *Nội quy*. Áp mẫu "Công nhân" cho một vai thợ là
**thợ hết tự chấm công được**. Tìm ra khi soi giao diện thật, không phải từ test (test ban đầu còn
khẳng định điều ngược lại). Đã ép hai ô đó luôn bật ở `role_service.role_templates()` — ép một chỗ
chứ không bắt từng mẫu tự khai, vì thêm mẫu thứ sáu là quên.

**2. Cột `can_view_log` chưa nối hết đường ống.** Thêm ở model + repo + `rbac_service` + giao diện
nhưng thiếu ở **schema API** và `role_service`: quản trị tick ô "Xem Nhật ký chấm công", bấm Lưu,
không lỗi gì cả — mở lại thì ô vẫn tắt. Đã nối, và thêm guard
`test_moi_cot_quyen_deu_di_het_duong_ong_len_API` đối chiếu MỌI cột boolean của `role_permissions`
với ba chặng máy chủ. Thêm cột quyền mới mà quên nối là test đỏ ngay.

---

## 7. Cách nghiệm thu

- [ ] Tạo một vai **trống trơn** → đăng nhập → **không vào được màn nào** trong ba phân hệ.
- [ ] Bật đúng một ô *Xem* của một tab → **chỉ tab đó hiện**, các tab khác vẫn ẩn.
- [ ] Có *Xem* mà không có *Thao tác* → nút ẩn **và** gọi thẳng API vẫn bị chặn (kiểm bằng công cụ,
      không kiểm bằng mắt).
- [ ] Phạm vi *chỉ mình* → số dòng thấy được **ít hơn** người phạm vi *cả công ty*, ở **mọi** danh
      sách của ba phân hệ.
- [ ] Người không có ô *Chốt kỳ công* → không bấm được, và gọi thẳng API cũng không được.
- [ ] Người có ô *Chốt kỳ công* phạm vi *cả tổ* → chỉ chốt được kỳ của tổ mình.
