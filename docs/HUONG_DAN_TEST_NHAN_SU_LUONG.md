# Hướng dẫn kiểm thử — Nhân sự → Chấm công → Lương

Tài liệu để **người dùng tự bấm theo và đối chiếu**, không cần biết kỹ thuật.
Làm tuần tự là chạy hết một vòng: khai người → chấm công → chốt công → tính lương → chốt → chi.

Mỗi bước có **Kết quả mong đợi**. Đúng thì tích ✅, sai thì ghi số hiệu bước (VD `4.3`) + chụp màn.

> ⚠️ **Đọc mục 11 TRƯỚC KHI báo lỗi.** Có mấy chỗ **đã biết là chưa xong**, ghi rõ ở đó. Báo trùng
> vào những chỗ ấy thì mất công cả hai bên.

---

## 0. Chuẩn bị

### 0.1 Cần bao nhiêu tài khoản

| Vai | Làm gì |
|---|---|
| **Nhân viên thường** | Tự chấm công, xin nghỉ, xin đi muộn, xem phiếu lương của mình |
| **Quản lý nhân sự** | Khai hồ sơ, khai ca, chốt công, duyệt đơn |
| **Kế toán lương** | Tính lương, chốt bảng lương, đánh dấu đã chi |
| **Giám đốc** | Xem tất cả |

Một tài khoản admin làm hết được, **nhưng** phần kiểm quyền (mục 10) bắt buộc phải có tài khoản
nhân viên thường mới thử được.

### 0.2 Khai trước khi test

Vào `Nhân sự & Lương` theo thứ tự này — **sai thứ tự là bước sau không có dữ liệu**:

| # | Vào | Khai gì |
|---|---|---|
| 0.2.1 | **Phòng ban** | Ít nhất 2 phòng ban |
| 0.2.2 | **Chấm công → Khai ca** | Ít nhất 1 ca (VD ca hành chính 08:00–17:00) và 1 ca đêm (VD 22:00–06:00) |
| 0.2.3 | **Chấm công → Lịch & Ngày lễ** | Ngày làm việc trong tuần; thêm 1 ngày lễ |
| 0.2.4 | **Chấm công → Điểm chấm công** | Ít nhất 1 điểm |
| 0.2.5 | **Hồ sơ nhân sự** | Ít nhất 3 người: 1 thử việc, 1 chính thức, 1 ở tổ có tích *Làm khoán* |
| 0.2.6 | **Lương → Cấu hình lương** | Xem qua toàn bộ tham số (mục 8) |
| 0.2.7 | **Lương → Lương nhân viên** | Khai lương cho từng người |

> **Chưa khai ca thì chấm công không ra công.** Đây là chỗ hay quên nhất.

---

## 1. Hồ sơ nhân sự

**Vào:** `Nhân sự & Lương → Hồ sơ nhân sự`

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 1.1 | Thêm nhân viên mới, điền đủ thông tin bắt buộc | Lưu được, hiện trong danh sách |
| 1.2 | Bỏ trống trường bắt buộc | ❌ Bị chặn, báo rõ thiếu gì |
| 1.3 | Đổi trạng thái sang **Thử việc / Chính thức / Nghỉ phép / Tạm đình chỉ / Đã thôi việc** | Đổi được, nhãn màu thay đổi |
| 1.4 | Gán phòng ban + chức danh + ngày vào làm | Lưu được |
| 1.5 | Mở lại hồ sơ vừa sửa | Thông tin đúng như đã lưu |

✅ **Chốt mục 1:** đủ 3 người để test tiếp.

---

## 2. Chấm công hằng ngày

**Vào:** `Nhân sự & Lương → Chấm công`

Màn này có **9 tab**. Ba tab đầu ai cũng thấy, các tab còn lại cần quyền.

### 2.1 Chấm công của tôi

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 2.1.1 | Bấm **Chấm vào** | Ghi nhận giờ vào |
| 2.1.2 | Bấm **Chấm ra** | Ghi nhận giờ ra |
| 2.1.3 | Chấm vào / chấm ra **nhiều lần** trong ngày | ✅ Cho phép — người ra ngoài rồi quay lại là chuyện thường |
| 2.1.4 | Xem lại các lần đã chấm trong ngày | Hiện đủ **tất cả** các lần, không đè lên nhau |

> **Bấm ra bấm vào là SỰ THẬT.** Hệ ghi lại hết, không hỏi tại sao. Việc "được phép làm thêm bao
> nhiêu" là chuyện của phiếu tăng ca, không phải của nút chấm công.

### 2.2 Công của tôi

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 2.2.1 | Mở tab, chọn tháng hiện tại | Hiện lưới ngày trong tháng |
| 2.2.2 | Ngày đã chấm | Có giờ vào/ra + số công |
| 2.2.3 | Ngày nghỉ theo lịch (CN, ngày nghỉ tuần) | Có dấu riêng, **khác** dấu nghỉ phép |
| 2.2.4 | Ngày nghỉ phép đã duyệt | Dấu **khác hẳn** ngày nghỉ theo lịch |
| 2.2.5 | Ngày lễ | Nhãn **Nghỉ lễ** |
| 2.2.6 | Chọn tháng chưa có dữ liệu | Có dòng nhắc, **không** để trắng trơn |

### 2.3 Đi muộn / về sớm / nghỉ nửa buổi

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 2.3.1 | Xin đi muộn cho **hôm nay** | Gửi được |
| 2.3.2 | Xin cho **ngày trong tương lai** | ❌ Bị chặn — chưa tới ngày đó thì chưa biết có muộn hay không |
| 2.3.3 | Quản lý vào duyệt | Duyệt / từ chối được |

---

## 3. Ca làm việc và phân ca

**Vào:** `Chấm công → Khai ca` và lưới phân ca

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 3.1 | Khai một ca mới (giờ vào, giờ ra, giờ nghỉ giữa ca) | Lưu được |
| 3.2 | Khai ca **qua nửa đêm** (VD 22:00 → 06:00) | Lưu được |
| 3.3 | Chấm công theo ca qua nửa đêm | Công tính đúng — **không** bị cắt làm hai ngày |
| 3.4 | Gán **ca nền** cho một người (ca mặc định hằng ngày) | Áp cho mọi ngày chưa phân ca riêng |
| 3.5 | Phân **ca riêng cho một ngày cụ thể** | Ngày đó dùng ca riêng, các ngày khác vẫn ca nền |
| 3.6 | Đặt một ngày là **Nghỉ** | Ô ngày đó để trống hẳn, không tính công |

✅ **Chốt mục 3:** ca nền + ca theo ngày + nghỉ — ba lớp không đè sai nhau.

---

## 4. Nghỉ phép

**Vào:** `Nhân sự & Lương → Nghỉ phép` — 4 tab

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 4.1 | Tab **Đơn của tôi** → tạo đơn xin nghỉ | Gửi được |
| 4.2 | Chọn **đến ngày < từ ngày** | ❌ Bị chặn ngay tại form |
| 4.3 | Tab **Duyệt đơn** (quản lý) | Thấy đơn chờ duyệt, duyệt / từ chối được |
| 4.4 | Sau khi duyệt, xem lại **Công của tôi** | Ngày đó có dấu nghỉ phép |
| 4.5 | Tab **Lịch nghỉ** | Thấy toàn công ty ai nghỉ ngày nào |
| 4.6 | Tab **Loại nghỉ** | Chỉ người có quyền **sửa** mới vào được (không phải quyền duyệt) |

---

## 5. Tăng ca

**Vào:** `Nhân sự & Lương → Tăng ca` — 2 tab

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 5.1 | Tab **Của tôi** → đăng ký tăng ca | Gửi được |
| 5.2 | Tab **Duyệt** | Người có quyền duyệt thấy đơn |
| 5.3 | Duyệt xong, chấm công quá giờ ca | Giờ vượt tính vào tăng ca |
| 5.4 | **Không có phiếu tăng ca** mà vẫn chấm quá giờ | Ca chính **vẫn đủ công** — chỉ phần vượt không được tính tăng ca |

> **Phiếu tăng ca là GIẤY PHÉP + TRẦN**, không phải điều kiện để được tính công. Không có phiếu thì
> mất phần làm thêm, chứ không mất công ca chính.

---

## 6. Bảng công tháng và CHỐT CÔNG

**Vào:** `Chấm công → Bảng công tháng`

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 6.1 | Chọn tháng | Hiện **tất cả** người đang làm trong tháng đó |
| 6.2 | Người mới vào giữa tháng | Vẫn có dòng, công tính từ ngày vào |
| 6.3 | Người đã nghỉ việc giữa tháng | Vẫn có dòng, công tính tới ngày nghỉ |
| 6.4 | Người của phòng ban khác | Có mặt đủ, không sót ai |
| 6.5 | Bấm **Chốt công tháng** | Kỳ công khóa lại |
| 6.6 | Sau khi chốt, thử sửa công | ❌ Không sửa được |
| 6.7 | Bấm **Mở lại kỳ công** | Sửa lại được |

### 6.8 ⭐ Số phải khớp giữa trước và sau khi chốt

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 6.8.1 | Ghi lại tổng công của 2–3 người **trước** khi chốt | |
| 6.8.2 | Bấm **Chốt công tháng** | |
| 6.8.3 | So lại tổng công của đúng mấy người đó | **Y HỆT** — không được nhảy số |

> Đây là chỗ dễ sai âm thầm nhất. Chốt công là chụp ảnh lại số liệu; nếu ảnh khác bản gốc thì mọi
> tính toán lương sau đó đều sai.

---

## 7. Yêu cầu chỉnh công

**Vào:** `Chấm công → Yêu cầu chỉnh công`

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.1 | Nhân viên xin chấm bù cho ngày quên chấm | Gửi được, chọn được lý do (quên chấm / máy hỏng / được duyệt / khác) |
| 7.2 | Xin chỉnh công cho **ngày chưa tới** | ❌ Bị chặn |
| 7.3 | Quản lý duyệt | Công cập nhật lại |

---

## 8. Cấu hình lương

**Vào:** `Nhân sự & Lương → Lương → Cấu hình lương`

Đây là chỗ **mọi con số luật** nằm. Xem qua từng ô, đối chiếu với luật hiện hành.

| # | Kiểm | Kết quả mong đợi |
|---|---|---|
| 8.1 | **Giảm trừ bản thân** | Có ô, sửa được |
| 8.2 | **Giảm trừ mỗi người phụ thuộc** | Có ô, sửa được |
| 8.3 | **Ngưỡng miễn BHXH khi nghỉ không lương từ … ngày** | Có ô. Mặc định **14** (QĐ 595/QĐ-BHXH Đ42.4). Đặt **0** = tắt hẳn quy tắc này |
| 8.4 | Sửa ngưỡng 8.3 rồi tính lại lương | Số BHXH đổi theo |
| 8.5 | **Trần đóng BHXH/BHYT** | Có ô; đặt 0 = tắt trần |
| 8.6 | Sửa một ô rồi chuyển sang tab khác **mà chưa lưu** | Có nhắc "chưa lưu", không mất âm thầm |

> Mọi con số luật đều phải **khai được**, không cắm cứng trong máy. Luật đổi thì sửa ở đây, không
> phải gọi thợ.

---

## 9. ⭐ Bảng lương tháng

**Vào:** `Nhân sự & Lương → Lương → Bảng lương tháng`

### 9.1 Vòng đời một kỳ lương

Bảng lương đi qua **ba trạng thái**, mỗi trạng thái có nút riêng:

| Trạng thái | Nút hiện ra | Nghĩa |
|---|---|---|
| **Nháp** | `↻ Tính lại` · `🔒 Chốt` | Còn sửa được |
| **Đã chốt** | `Mở lại` · `💵 Đã chi` | Số đã khóa, chưa phát tiền |
| **Đã chi** | `↩ Hủy đã chi` | Tiền đã phát |

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.1.1 | Chọn tháng đã **chốt công**, bấm **↻ Tính lại** | Ra bảng lương đủ người |
| 9.1.2 | Sửa một dòng lương | Sửa được (đang là Nháp) |
| 9.1.3 | Bấm **🔒 Chốt** | Không sửa được nữa; nút đổi thành *Mở lại* + *Đã chi* |
| 9.1.4 | Bấm **Mở lại** | Sửa lại được |
| 9.1.5 | Chốt lại rồi bấm **💵 Đã chi** | Đánh dấu đã phát tiền |
| 9.1.6 | Bấm **↩ Hủy đã chi** | Quay về *Đã chốt* |
| 9.1.7 | Bấm **⬇ Xuất Excel** | Tải được file, số trong file khớp số trên màn |

### 9.2 Tìm kiếm và lọc

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.2.1 | Gõ tên nhân viên vào ô tìm | Lọc đúng |
| 9.2.2 | Lọc **Tất cả / Chính thức / Thử việc** | Đúng nhóm |

### 9.3 ⭐ Kiểm tiền — làm kỹ phần này

Chọn **một người có đi làm thật**, mở **Sửa lương** của người đó và đối chiếu:

| # | Kiểm | Kết quả mong đợi |
|---|---|---|
| 9.3.1 | **Lương công** | = đơn giá ngày × số công, khớp Bảng công tháng |
| 9.3.2 | **Tiền cơm** | = số ca thực làm × mức cơm mỗi ca |
| 9.3.3 | **Phụ cấp ca** | = số ca thực làm × mức phụ cấp mỗi ca |
| 9.3.4 | **Tăng ca** | Chỉ tính phần có phiếu tăng ca đã duyệt |
| 9.3.5 | **Tổng thu nhập** | = cộng đủ các khoản trên, **có cả** tiền cơm và phụ cấp ca |
| 9.3.6 | **Thu nhập miễn thuế** | **Có cả** tiền cơm + phụ cấp ca + phụ trội tăng ca/đêm |
| 9.3.7 | Thuế TNCN | Tính trên phần **chịu thuế**, tức đã trừ phần miễn ở 9.3.6 |

> **9.3.5 và 9.3.6 phải đi cùng nhau.** Nếu một khoản được cộng vào tổng thu nhập mà **không** được
> cộng vào phần miễn thuế, thì người lao động bị **đánh thuế oan** lên khoản lẽ ra được miễn. Đây là
> lỗi đã từng có và đã sửa — kiểm lại cho chắc.

### 9.4 Ngày lễ và ngày nghỉ

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.4.1 | Người **không đi làm** ngày lễ | Vẫn hưởng nguyên lương ngày đó |
| 9.4.2 | Người **có đi làm** ngày lễ | Được hưởng thêm theo hệ số ngày lễ |
| 9.4.3 | Người nghỉ **không lương** | Ngày đó không tính công, không tính tiền |

### 9.5 BHXH khi nghỉ không lương dài

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.5.1 | Cho một người nghỉ không lương **ít hơn** ngưỡng ở mục 8.3 | Vẫn đóng BHXH |
| 9.5.2 | Nghỉ không lương **từ ngưỡng trở lên** | **Không** đóng BHXH tháng đó |
| 9.5.3 | Đổi ngưỡng ở Cấu hình lương rồi tính lại | Kết quả đổi theo ngưỡng mới |

### 9.6 Phiếu lương

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.6.1 | Bấm **In phiếu** cho một người | Ra phiếu, số khớp bảng lương |
| 9.6.2 | Phiếu có dòng **tiền cơm** | Hiện đúng số, **không** phải 0đ |
| 9.6.3 | Nhân viên vào tab **Phiếu lương của tôi** | Chỉ thấy phiếu **của mình** |

---

## 10. Phạm vi nhìn — ai thấy gì

| # | Đăng nhập bằng | Vào | Kết quả mong đợi |
|---|---|---|---|
| 10.1 | Nhân viên thường | Lương | Chỉ thấy **Phiếu lương của tôi** + **Tạm ứng của tôi**; **không** thấy Bảng lương tháng |
| 10.2 | Nhân viên thường | Chấm công | Thấy 3 tab đầu; **không** thấy Bảng công tháng / Nhật ký / Khai ca |
| 10.3 | Nhân viên thường | Hồ sơ nhân sự | ❌ Không vào được |
| 10.4 | Quản lý nhân sự | Chấm công | Thấy đủ 9 tab |
| 10.5 | Kế toán lương | Lương | Thấy Bảng lương tháng |
| 10.6 | Nhân viên thường | Phiếu lương | Chỉ ra phiếu của chính mình, **không** xem được của người khác |

> **10.6 là chỗ nhạy cảm nhất.** Lương người khác lộ ra là chuyện lớn — thử kỹ.

---

## 11. 🔴 ĐÃ BIẾT LÀ CHƯA XONG — đừng báo trùng

Mấy chỗ dưới đây **đã rà ra và ghi nhận**, chưa sửa. Gặp thì bỏ qua, **không cần báo**.

| Vấn đề | Hiện tượng nhìn thấy | Trạng thái |
|---|---|---|
| **Tiền khoán luôn = 0** | Khai đơn giá khoán, khai mốc thưởng/phạt tổ trưởng — cột khoán vẫn 0đ | Thiếu nguồn **sản lượng**; chờ Lệnh sản xuất |
| **Tổ có tích "Làm khoán" mất tăng ca** | Người tổ đó làm thêm giờ nhưng cột tăng ca = 0, mà khoán cũng = 0 ⇒ **thiệt hơn tổ thường** | Do hai cái trên cộng lại. Cách chữa tạm: **bỏ tích "Làm khoán"** ở tổ đó |
| **Quy tắc lương theo bậc thợ** | Khai được qua API nhưng **không bao giờ áp dụng** | Chưa có màn, và phần tính đã ngừng dùng |
| **Ô "Loại / Bậc thợ" trong hồ sơ** | Gõ được nhưng **không ra tiền** — chỉ để xem | Chưa có cơ chế chia theo bậc |
| **Điều chỉnh lương ±** | Máy cộng được nhưng **không có ô nhập** trên màn | Thiếu đường vào |

### 🔴 Một con số cần chủ quyết, không phải lỗi

Mỗi ca làm việc đang mặc định **25.000đ tiền cơm + 50.000đ phụ cấp ca**. Người đủ công được cộng
khoảng **1.950.000đ/tháng** từ hai con số này.

Đây là **số mặc định trong máy, chưa ai chốt**. Nó ra tiền thật mỗi kỳ lương. Khi test thấy hai
khoản này, kiểm xem **mức có đúng với thực tế xưởng không** — nếu không thì sửa ở *Cấu hình lương*
hoặc ở khai ca, đừng để nguyên.

---

## 12. Bảng ghi kết quả

| Mục | Nội dung | ✅/❌ | Ghi chú khi sai |
|---|---|---|---|
| 1 | Hồ sơ nhân sự | | |
| 2 | Chấm công hằng ngày | | |
| 3 | Ca làm việc & phân ca | | |
| 4 | Nghỉ phép | | |
| 5 | Tăng ca | | |
| 6 | Bảng công + Chốt công | | |
| 6.8 | Số khớp trước/sau chốt công | | |
| 7 | Yêu cầu chỉnh công | | |
| 8 | Cấu hình lương | | |
| 9.1 | Vòng đời kỳ lương | | |
| 9.3 | Kiểm tiền từng khoản | | |
| 9.4 | Ngày lễ | | |
| 9.5 | BHXH nghỉ không lương | | |
| 9.6 | Phiếu lương | | |
| 10 | Phạm vi nhìn | | |

---

## Phụ lục — mấy chỗ hay tưởng là lỗi mà không phải

| Hiện tượng | Có phải lỗi? | Giải thích |
|---|---|---|
| Chấm vào / chấm ra được nhiều lần một ngày | **Không** | Ra ngoài rồi quay lại là chuyện thường; hệ ghi hết |
| Không có phiếu tăng ca mà ca chính vẫn đủ công | **Không** | Phiếu tăng ca là *giấy phép cho phần làm thêm*, không phải điều kiện tính công ca chính |
| Không xin đi muộn cho ngày mai được | **Không** | Chưa tới ngày thì chưa biết có muộn hay không |
| Tổ có tích "Làm khoán" không có tăng ca | **Không** *(nhưng cần quyết)* | Xem mục 11 |
| Cột khoán bằng 0 | **Không** | Chưa có nguồn sản lượng — mục 11 |
| Sau khi chốt công không sửa được | **Không** | Đúng ý đồ; bấm *Mở lại kỳ công* |
| Nhân viên không thấy Bảng lương tháng | **Không** | Chỉ thấy phiếu của mình |
| **Tổng công nhảy số sau khi chốt công** | 🔴 **CÓ** | Báo ngay — mục 6.8 |
| **Tiền cơm hiện 0đ trên phiếu lương** dù có đi làm | 🔴 **CÓ** | Báo ngay |
| **Tiền cơm/phụ cấp ca bị tính thuế** | 🔴 **CÓ** | Báo ngay — mục 9.3.6 |
| **Nhân viên xem được lương người khác** | 🔴 **CÓ** | Báo ngay — mục 10.6 |
| **Bảng công tháng thiếu người** đang làm | 🔴 **CÓ** | Báo ngay |

---

## Nếu màn không đúng như tài liệu

Kiểm **backend đã khởi động lại chưa**. Sửa xong mà chưa restart thì màn vẫn chạy bản cũ.

Mở PowerShell:

```
netstat -ano | findstr :8000
```

Phải ra **đúng một dòng**. Nhiều dòng = nhiều bản chạy chồng nhau, cùng một thao tác có thể ra kết
quả khác nhau tuỳ lần — báo lại để dọn.
