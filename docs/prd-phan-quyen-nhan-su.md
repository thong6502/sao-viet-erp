# PRD — Dọn phân quyền nhóm Nhân sự: một ô quyền = một thứ nhìn thấy được

**Nguồn**: chủ chốt 15/08/2026, đối chiếu ảnh chụp màn Vai trò & Quyền + menu bên trái, đo lại code
cùng ngày.
**Phạm vi**: nhóm **Nhân sự** trong ma trận phân quyền, cộng phần gom tab của màn Lương.
**Nguyên văn chủ chốt** (theo thứ tự bàn):
- *"cái tự phục vụ là mặc định ai cũng có luôn đúng không vậy thì không cần cấp quyền"*
- *"Đi muộn / về sớm và Yêu cầu chỉnh công là nó nằm trong module Chấm công mà"*
- *"phải cấp quyền mới cho hiển thị"*
- *"mình chia theo của tôi / cả phòng / tất cả đi nhỉ"*
- *"Bạn định cho hiện bảng lương à, công nhân làm gì có quyền đó đâu"*
- *"ở trong này nhiều tab quá"*
- *"bật thao tác là được thao tác tất cả, nếu bật chi tiết lên nó mới hiện tab lên"*

---

## 0. Luật chung rút ra sau khi bàn

Ba câu này chi phối toàn bộ phần còn lại:

1. **Cột Xem = mở màn + PHẦN CỦA TÔI.** Bấm giờ, xem lịch công của mình, gửi đơn cho mình, xem
   phiếu của mình. Đây KHÔNG phải quyền được ban — ai có mặt trong hệ thống thì phải làm được việc
   của chính mình; chặn nó là chặn người ta đi làm.
2. **Một ô chi tiết = một tab.** Tên ô gọi đúng tên tab. Bật ô thì tab hiện, không bật thì không có.
   Chi tiết luôn là thứ dính tới **người khác** hoặc **dùng chung**.
3. **Cột Thao tác = được GHI tất cả những gì mình đã mở ra.** Một ô cho cả màn, không chẻ nhỏ theo
   từng tab. Nó không tự mở tab nào.
4. **Phạm vi lọc DÒNG, không ẩn TAB.** Đây là chỗ dễ nhầm nhất — xem §3.

Đọc gọn: **Xem = của tôi · Chi tiết = của người khác · Thao tác = được sửa.**

---

## 1. Bệnh đang có

Ma trận nhóm Nhân sự **10 dòng**, menu **7 mục**. Ba dòng không phải màn nào:

| Dòng | Thực chất | Có menu |
|---|---|---|
| Tự phục vụ | phần *"của tôi"* nằm rải trong **4** màn | không |
| Yêu cầu chỉnh công | một **tab** của màn Chấm công | không |
| Đi muộn / về sớm | một **tab** của màn Chấm công | không |

Và việc thật nấp trong chip *"N/N chi tiết"* — phải bấm mở mới thấy, chip chỉ hiện con số. Ô
*"Cấu hình chấm công"* tệ nhất: **bật một ô mở ra ba tab** (Điểm chấm công · Khai ca · Lịch & Ngày lễ)
mà người cấp quyền không có cách nào biết.

---

## 2. Nền móng — ĐÃ LÀM 15/08/2026

**Vá lọc phạm vi màn Lương.** Trước đó đường lấy bảng lương chỉ hỏi *"có ô Xem Lương không"*, trả về
**mọi dòng của kỳ** — cấp ô Xem Lương với phạm vi *Của tôi* thì người đó vẫn đọc được lương cả công
ty, gồm cả giám đốc. Đúng căn bệnh tester ghi ở rà soát lần 1: *"Phạm vi của tôi nhưng xem được tất
cả"*.

Đã kẹp theo phạm vi ở cả 5 đường: bảng lương · xuất Excel bảng lương · xuất file chuyển khoản · xem
khoản phát sinh của một dòng · mọi đường sửa dòng lương. Dùng lại **cùng một nguồn phạm vi** với
Chấm công / Nghỉ phép / Tăng ca.

Không có bước này thì mọi thứ dưới đây đều không an toàn.

---

## 3. Phạm vi lọc DÒNG, không ẩn TAB — và hệ quả

Đo được: cấp ô `Lương` ở phạm vi *Của tôi* thì màn Lương vẫn mở ra **tab Bảng lương** và **tab Tạm
ứng** (chỉ là mỗi tab chỉ còn dòng của chính họ). Ba tab kia đóng vì đòi ô khác.

⇒ **Công nhân KHÔNG được cấp ô Lương, một chút cũng không.** Bảng lương là công cụ quản lý; lọc còn
một dòng vẫn là bảng lương. Phiếu lương của thợ phải đi đường khác — xem §6.

Ba màn còn lại thì phạm vi dùng đúng như hình dung:

| Phạm vi | Chấm công · Nghỉ phép · Tăng ca |
|---|---|
| Của tôi | chỉ dữ liệu của chính mình |
| Cả phòng | phòng mình + các tổ con |
| Tất cả | toàn công ty |

---

## 4. Chốt 1 — Gộp hai khoá vào Chấm công

| Khoá cũ | Thành | Cột dùng |
|---|---|---|
| `yeu_cau_chinh_cong:approve` | ô **Duyệt yêu cầu chỉnh công** | `can_approve` của `cham_cong` (đang trống) |
| `di_muon:approve` | ô **Duyệt phiếu đi muộn / về sớm / nghỉ nửa buổi** | **cột mới** |
| `yeu_cau_chinh_cong:read` | bỏ — tab hiện theo ô Duyệt ở trên | — |

Hai module `di_muon`, `yeu_cau_chinh_cong` **biến mất khỏi danh mục**.

---

## 5. Chốt 2 — Ma trận màn Chấm công: 9 ô chi tiết

**Cột Xem** mở màn + ba tab của chính mình: *Chấm công của tôi* (bấm giờ) · *Công của tôi* (lịch
tháng, bấm ô ngày để gửi yêu cầu chỉnh công) · *Đi muộn / về sớm* (phần tự xin).

⚠️ Ba tab đó **không cần ô CHI TIẾT nào, nhưng vẫn phải được cấp ô Chấm công**. Chúng KHÔNG trùng
nhau: một cái là bản đồ GPS để bấm giờ, một cái là lịch tháng để soi và khiếu nại — khác cả giao
diện lẫn luồng việc.

| Ô chi tiết | Mở ra cái gì | Trạng thái cột |
|---|---|---|
| **Bảng công tháng** | tab *Bảng công tháng* — lưới người × ngày, chứa nút Chốt kỳ | **cột mới** |
| Xem nhật ký chấm công | tab *Nhật ký chấm công* | đã có |
| **Duyệt yêu cầu chỉnh công** | tab *Yêu cầu chỉnh công* | dùng `can_approve` |
| **Duyệt phiếu đi muộn / về sớm / nghỉ nửa buổi** | tab con *Duyệt phiếu* trong tab Đi muộn | **cột mới** |
| **Điểm chấm công** | tab *Điểm chấm công* | **cột mới** |
| **Khai ca** | tab *Khai ca* | **cột mới** |
| **Lịch & Ngày lễ** | tab *Lịch & Ngày lễ* | **cột mới** |
| Chấm bù / sửa công | **nút** trong Bảng công (không phải tab) | đã có |
| Chốt kỳ công / mở lại kỳ ⚠️ | **nút** trong Bảng công (không phải tab) | đã có |

**Bảng công tháng phải là ô riêng** — nó là công cụ quản lý chứa nút Chốt kỳ công, cùng hạng với
Bảng lương bên màn Lương. Thợ mở màn Chấm công để bấm giờ, nhưng không được thấy lưới cả công ty.

Ô *"Cấu hình chấm công"* cũ bị tách thành ba ô gọi đúng tên. **Năm cột cờ mới**, migration ở §8.

**Vai Công nhân**: cấp ô Xem, **không bật ô chi tiết nào** → thấy đúng ba tab của mình.

---

## 5b. Cùng luật đó cho Tăng ca và Nghỉ phép

Hai màn này nhỏ hơn nên áp vào là xong, **không cần cột cờ mới nào**:

| Màn | Cột Xem | Cột Thao tác | Ô chi tiết |
|---|---|---|---|
| **Tăng ca** | tab *Phiếu của tôi* | gửi / sửa / huỷ phiếu của mình | *Duyệt phiếu tăng ca* → tab Duyệt phiếu |
| **Nghỉ phép** | tab *Đơn của tôi* | gửi / huỷ đơn của mình | *Duyệt đơn nghỉ* → tab Duyệt · *Quản danh mục loại nghỉ* |

Hiện hai màn này gác phần "của tôi" bằng ô Tự phục vụ; bỏ ô đó thì chúng về đúng cột Xem và cột
Thao tác của chính dòng mình.

---

## 6. ~~Chốt 3 — Gom tab màn Lương~~ · ĐÃ HUỶ 15/08/2026

> **Không làm nữa** (chủ chốt: *"bỏ cái này đi, không cần thiết"*), và lý do đáng ghi: việc
> **một ô = một tab** làm xong khiến mục này thành thừa.
>
> Bước 4 sinh ra để giải một bài: cấp ô Lương cho thợ thì họ thấy luôn **Bảng lương**. Nay mỗi tab
> có ô riêng, nên cấp thợ ô Lương với **Xem + Thao tác, không bật ô chi tiết nào** là họ chỉ thấy
> đúng *Phiếu lương của tôi* và *Tạm ứng của tôi* — bằng đúng thứ việc dời tab định đạt được, mà
> không phải đụng vào hai file lớn nhất hệ thống.
>
> Ba tab khai-một-lần (Lương nhân viên · Lương khoán · Cấu hình lương) cũng không gom nữa: mỗi cái
> đã có ô riêng nên ai không được cấp thì không thấy, tab không còn chật.

Nội dung cũ giữ lại bên dưới để đọc lại bối cảnh, KHÔNG phải việc còn nợ.

### (lưu trữ) Gom tab màn Lương: 7 → 3

Bảy tab hiện nay là **ba loại việc khác nhau** bị xếp ngang hàng:

| Loại | Tab |
|---|---|
| Việc hàng tháng | Bảng lương · Tạm ứng |
| Khai một lần rồi thôi | Lương nhân viên · Lương khoán · Cấu hình lương |
| Của tôi | Phiếu lương của tôi · Tạm ứng của tôi |

**Sau khi gom — 3 tab:**

1. **Bảng lương** — ô Xem
2. **Tạm ứng** — ô Xem
3. **Thiết lập** — gộp ba tab khai-một-lần, mỗi mục bên trong **giữ nguyên ô quyền của nó**:
   - Lương nhân viên → ô Thao tác
   - Đơn giá khoán → ô Thao tác
   - Tham số lương (hệ số, trần BH, biểu thuế) → ô Xem lương & BHXH

   Tab *Thiết lập* chỉ hiện nếu mở được **ít nhất một** mục bên trong. Không nới lỏng ô nào.

**Hai tab "của tôi" dời sang Hồ sơ của tôi** (§7).

---

## 7. Chốt 4 — Bỏ ô Tự phục vụ · ĐÃ LÀM, trừ phần dời tab

> Phần **bỏ ô `self_service`** đã làm xong: 15 cổng ở 6 router, 4 màn, ma trận, menu Chấm công.
> Phần **dời hai tab "của tôi" sang Hồ sơ của tôi** (điểm 2 dưới đây) **ĐÃ HUỶ** cùng lý do ở §6 —
> hai tab đó ở lại màn Lương và nay đã an toàn nhờ mỗi tab một ô.
>
> Việc còn lại duy nhất: xoá hẳn ba khoá cũ (`self_service`, `di_muon`, `yeu_cau_chinh_cong`) khỏi
> danh mục module — cố ý để lại vài hôm làm đường lui, phòng migration rót thiếu chỗ nào.

`self_service` đang gác phần *"của tôi"* ở bốn màn: Chấm công, Lương, Nghỉ phép, Tăng ca. Nó cắt
ngang bốn màn nên không thể là một dòng ngang hàng với các màn; và nó đã được cấp mặc định cho mọi
vai mới, tức là một ô luôn bật sẵn — ô cấu hình giả.

**Luật mới:**

1. **Dữ liệu của CHÍNH MÌNH là quyền đương nhiên** — không cần ô nào. Gồm cả gửi / sửa / huỷ đơn của
   chính mình.
2. **Phiếu lương của tôi + Tạm ứng của tôi chuyển sang màn Hồ sơ của tôi.** Cổng thật của phiếu lương
   **không phải ô quyền** mà là **HCNS đã công bố phiếu chưa** (nút Công bố + hẹn giờ mở/đóng, dựng
   15/08/2026).
3. **Màn Hồ sơ của tôi hiện với MỌI tài khoản** — hiện đang gác bằng ô `dashboard`; giữ nguyên thì
   thợ mất đường tới dữ liệu của chính mình.
4. Ba tab "của tôi" ở Chấm công / Nghỉ phép / Tăng ca **ở nguyên chỗ cũ** — chúng nằm trong màn mà
   thợ vẫn được cấp (ở phạm vi *Của tôi*), không như màn Lương.

**Kết quả: ma trận nhóm Nhân sự còn đúng 7 dòng = 7 mục menu.**

> Phòng ban · Hồ sơ nhân sự · Chấm công · Nghỉ phép · Tăng ca · Lương · Nội quy công ty

**Sửa vai mẫu "Công nhân"** cho khớp: cấp `cham_cong` · `nghi_phep` · `tang_ca` ở phạm vi *Của tôi*.

### 7b. Bổ sung 18/08/2026 — màn Lương phải vào bằng ô THẬT

Bản PRD trước ghi *"KHÔNG cấp `luong`"* cho vai công nhân. Đúng ở thời điểm đó, vì cột **Xem** của
màn Lương còn mở luôn **Bảng lương tháng**. Sau §6 thì bảng lương đã có ô riêng
(`can_view_payroll_table`) nên căn cứ ấy hết hiệu lực — và giữ nguyên thì sinh ra hai chỗ hở:

1. **Cổng vào màn Lương vẫn là ô ma.** Menu mở khi có `luong` **HOẶC** `self_service`. Ô
   `self_service` cấp sẵn cho mọi vai và đã bị gỡ khỏi bảng phân quyền ⇒ HCNS **tắt ô Lương mà
   người ta vẫn vào được màn**. Một cái cổng không có tay nắm.
2. **Nút bấm ăn 403.** Luật *"ghi là ghi"* bắt xin tạm ứng phải có `luong.can_create`. Đo trên DB
   dev: **17/20 vai** thấy màn Lương mà không có ô Lương ⇒ bày nút ra rồi từ chối.

**Chốt:**

- Menu Lương gác bằng **một ô duy nhất `luong`** — bỏ cửa `self_service` (`Sidebar.tsx`).
- **Cấp sẵn phần *của tôi* cho mọi vai**: `luong` phạm vi *Của tôi*, bật **Xem + Thao tác**.
  KHÔNG `can_view_payroll_table`, KHÔNG `can_view_salary` ⇒ chỉ thấy phiếu lương của chính mình và
  gửi được đề nghị tạm ứng. Làm ĐÔI: migration `0198` cho DB đang chạy + `_luong_self()` trong
  `seed.py` cho vai sinh sau.
- Nút *"Đề nghị tạm ứng" / "Xin lương đợt 1"* ẩn khi không có ô Thao tác, kèm câu giải thích —
  không để nút bày ra rồi 403.

Khác biệt với `self_service` cũ: ô này **nhìn thấy và tắt được** trong bảng phân quyền.

---

## 8. Migration — chỉ thêm, không xoá

```
vai có di_muon.can_approve             → bật cham_cong.<ô duyệt đi muộn>
vai có yeu_cau_chinh_cong.can_approve  → bật cham_cong.can_approve
vai có cham_cong.can_update            → bật cả 3 ô mới: điểm chấm công · khai ca · lịch & ngày lễ
vai có cham_cong.can_read              → bật ô mới: bảng công tháng
                                         (giữ nguyên hiện trạng: ai đang xem được bảng công
                                          thì vẫn xem được sau khi cập nhật)

0198 — vai có self_service.can_read    → rót luong (own) với Xem + Thao tác
       · chưa có dòng luong            → INSERT
       · có dòng luong nhưng TRỐNG TRƠN → UPDATE đúng hai ô đó
                                          (trống trơn = mọi can_* đều false, trên bảng phân quyền
                                           nó hiện y như chưa cấp)
       · có dòng luong đã bật ô nào đó → KHÔNG ĐỤNG (ý của người cấu hình)
       KHÔNG rót can_view_payroll_table / can_view_salary
```

Dòng quyền của hai module cũ **để nguyên tại chỗ**, không xoá trong cùng lần chạy — xoá ở lượt sau,
sau khi chạy thật vài ngày. Migration đã xoá dữ liệu thì không có đường về.

**Không ai mất quyền sau khi cập nhật.** Đây là điều kiện nghiệm thu số 1.

---

## 9. Rủi ro

| Rủi ro | Chặn bằng |
|---|---|
| Migration rót sai ⇒ vai mất quyền mà **không ai biết cho tới lúc cần dùng** | Test đếm số vai có từng quyền **trước và sau** migration |
| Bỏ ô Tự phục vụ nhưng quên mở màn Hồ sơ của tôi ⇒ thợ mất sạch đường vào dữ liệu của mình | Test: tài khoản **không có ô nào** vẫn xem được công + phiếu lương của chính mình |
| Gom tab màn Lương làm rơi một nhánh | Dọn từng tab một, mỗi lần chạy lại bộ test của phân hệ |
| Còn sót khoá mồ côi | Guard sẵn có `test_o_quyen_chet_tu_sinh.py` |
| Màn hỏi ô quyền đã bị gỡ ⇒ cấp quyền rồi mà nút không hiện | Guard sẵn có `test_giao_dien_khop_may_chu.py` |

---

## 10. Nghiệm thu

1. Ma trận nhóm Nhân sự hiện **đúng 7 dòng**, tên và thứ tự trùng khít menu bên trái.
2. Không vai nào mất quyền so với trước khi cập nhật.
3. Tài khoản **không được cấp ô nào**: vẫn xem được công · phiếu lương · đơn của **chính mình** ở
   Hồ sơ của tôi; **không** thấy menu Lương; **không** vào được Bảng lương.
4. Cấp ô Chấm công + bật **đúng một** ô chi tiết ⇒ hiện **đúng một** tab tương ứng, không kèm tab nào
   khác.
5. Màn Lương còn **3 tab**. Người chỉ có ô Xem thấy Bảng lương + Tạm ứng, **không** thấy Thiết lập.
6. Không còn khoá `self_service`, `di_muon`, `yeu_cau_chinh_cong` trong danh mục module.
7. `./init.ps1` xanh.
