# HƯỚNG DẪN SỬ DỤNG SAO VIỆT NHẬT ERP

## Nhân sự & Lương · Thu mua · Kế toán

**Phiên bản:** 2.0
**Ngày cập nhật:** 05/08/2026
**Đối tượng sử dụng:** Ban giám đốc, Hành chính nhân sự, bộ phận Thu mua, Kế toán và các phòng ban phát sinh nhu cầu mua hàng.

> Tài liệu này hướng dẫn thao tác theo đúng phiên bản hệ thống hiện tại. Menu và nút thao tác chỉ xuất hiện khi tài khoản được cấp đúng quyền.

## 1. Bắt đầu sử dụng

### 1.1. Đăng nhập và menu

1. Mở địa chỉ hệ thống do đơn vị triển khai cung cấp.
2. Nhập tên đăng nhập và mật khẩu.
3. Chọn chức năng trên menu bên trái.
4. Nếu không thấy một menu hoặc nút thao tác, liên hệ Quản trị viên để kiểm tra quyền.

### 1.2. Quy ước chung

- Dấu sao **(*)** màu đỏ là thông tin bắt buộc.
- Các mã như `NV...`, `YCMH-...`, `PMH-...`, `PC-...` được hệ thống tự sinh và dùng để truy vết.
- Không sử dụng nút quay lại của trình duyệt khi đang nhập một biểu mẫu dài; hãy dùng nút **Hủy**, **Trước**, **Tiếp** hoặc **Đóng** trên màn hình.
- Khi hệ thống báo lỗi, đọc nội dung màu đỏ và sửa đúng trường được nhắc trước khi lưu lại.
- Nhiều màn (Thu mua, Kế toán) chỉ cho xem/sửa dữ liệu **trong đúng phạm vi của tài khoản** — xem mục 3.1b. Nhận thông báo "Không tìm thấy phiếu" không có nghĩa là phiếu không tồn tại, có thể là phiếu ngoài phạm vi được xem.

### 1.3. Vai trò tham gia

| Vai trò | Công việc chính |
|---|---|
| Giám đốc/Quản trị | Tạo cơ cấu phòng ban, tổ; cấp quyền; có thể kiểm tra toàn bộ dữ liệu; là người **duyệt PMH** mặc định trong dữ liệu khởi tạo. |
| Hành chính nhân sự | Tạo hồ sơ, khai thông tin hợp đồng, xếp bậc, điều chỉnh lương theo ngày hiệu lực. |
| Trưởng bộ phận | Phối hợp xác nhận vị trí, tổ, ca làm và mức/bậc công việc. |
| Nhân viên phòng ban | Tạo Yêu cầu mua hàng của phòng ban, chỉ nhập nhu cầu và số lượng; **sửa/hủy được YCMH do chính mình tạo** khi còn ở trạng thái Chờ Thu mua xử lý. |
| Nhân viên mua hàng | Lập PMH có giá, giảm giá và VAT; đi mua và nhận hàng. **Không duyệt.** Chỉ thao tác được với **phiếu do chính mình lập**. |
| Trưởng bộ phận mua hàng | Như Nhân viên mua hàng, nhưng thao tác được với **phiếu của cả phòng Thu mua**, không chỉ của riêng mình. **Không duyệt** (mặc định trong dữ liệu khởi tạo). |
| Người có quyền duyệt Thu mua | **Duyệt hoặc từ chối PMH.** Thao tác này nằm ở màn Kế toán, nhưng quyền gác là quyền Thu mua (`thu_mua:approve`) — mặc định chỉ Giám đốc có, phải cấp thêm nếu muốn người khác duyệt. |
| Kế toán được cấp quyền | Lập Phiếu chi, xác nhận đã chi, theo dõi công nợ, in và đính kèm chứng từ. Nhìn thấy **toàn bộ** PMH công ty (không bị giới hạn theo người/phòng) để lập phiếu chi cho bất kỳ đơn nào. |

> **Người lập phiếu không được duyệt phiếu của chính mình** — kể cả giám đốc. Giám đốc tự lập PMH
> thì phải người khác duyệt. Chốt này nằm ở tầng nghiệp vụ, cấp thêm quyền cũng không lách được.

## 2. Nhân sự và lương

### 2.1. Luồng nghiệp vụ chuẩn

1. Tạo **Phòng ban/Tổ**.
2. Khai **thang bậc của tổ** nếu đơn vị có phân loại tay nghề hoặc cấp công việc (chỉ để phân loại — xem lưu ý ở 2.3).
3. Khai **Ca làm việc** kèm mức phụ cấp cơm/phụ cấp ca của từng ca (xem 2.7 và 2.8).
4. Tạo **hồ sơ nhân viên** và khai mức lương riêng theo hợp đồng.
5. Gán ca làm việc có ngày hiệu lực.
6. Khi tăng lương, thay hợp đồng, chuyển tổ hoặc nâng bậc, tạo một mốc mới theo ngày hiệu lực.
7. Cuối kỳ: kiểm tra công, tạo bảng lương, soát, chốt và xuất dữ liệu.

### 2.2. Tạo phòng ban và tổ

Menu: **Nhân sự & Lương → Phòng ban**.

1. Chọn **Thêm phòng ban/Tổ**.
2. Nhập tên, mã và đơn vị cha nếu đây là tổ trực thuộc một phòng.
3. Lưu lại và kiểm tra đơn vị xuất hiện đúng vị trí trong cây tổ chức.

> Nên tạo đúng cấp quản lý trước khi nhập nhân viên. Việc chuyển phòng/tổ sau này sẽ được ghi thành một mốc trong quá trình công tác.

### 2.3. Khai thang bậc của tổ

Menu: **Nhân sự & Lương → Lương → Cấu hình lương → Bậc lương & KPI**.

1. Chọn phòng/tổ cần cấu hình.
2. Chọn **Thêm bậc**.
3. Nhập thứ tự bậc, tên bậc, khung lương tối thiểu/tối đa và điều kiện thăng bậc nếu có.
4. Lưu bậc.

**Nguyên tắc quan trọng:** bậc lương chỉ dùng để phân loại và đối chiếu khung, hiện **cảnh báo mềm** nếu mức lương thật nằm ngoài khung nhưng vẫn cho lưu. Bậc **không** tự quyết định tiền lương của nhân viên. Hai người cùng bậc có thể có hai mức lương khác nhau theo hợp đồng.

> 🔴 **Mã bậc chuẩn hoá (`pay_grade_key`) và bảng "Quy tắc lương theo bậc" (`/api/luong/rules`) không dùng để tính tiền.** API còn sống, khai được, nhưng engine tính lương **không đọc** hai chỗ này — mọi quy tắc khai ở đó nằm chết trong DB. Đừng dựng thêm màn hoặc kỳ vọng chúng ảnh hưởng phiếu lương.

### 2.4. Tạo hồ sơ nhân viên kèm lương ban đầu

Menu: **Nhân sự & Lương → Hồ sơ nhân sự → Thêm nhân viên**.

#### Bước 1 - Định danh và việc làm

- Nhập họ tên, phòng/tổ, ngày vào làm, trạng thái thử việc/chính thức và chức danh.
- Mã nhân viên do hệ thống tự sinh.

#### Bước 2 - Cá nhân

- Nhập ngày sinh, giới tính, CCCD, địa chỉ, điện thoại và các thông tin cá nhân cần quản lý.

#### Bước 3 - Lương & BHXH

Nếu tài khoản có quyền khai lương, nhập:

- **Bậc/mức công việc:** chọn bậc thuộc đúng tổ của nhân viên; chỉ để phân loại.
- **Lương vị trí:** bắt buộc và phải lớn hơn 0. Đây cũng chính là **mức đóng bảo hiểm** — hệ thống không còn ô "Mức đóng bảo hiểm" riêng.
- **Lương trách nhiệm:** nhập theo hợp đồng nếu có.
- **Thưởng chuyên cần:** mức riêng của nhân viên; để 0 nếu không có.
- **Phụ cấp thâm niên và phụ cấp khác (gộp):** nhập theo thỏa thuận, cộng phẳng vào lương, không chia theo công.

Hệ thống hiển thị **Mức nền theo hợp đồng = Lương vị trí + Lương trách nhiệm**. Nếu mức này nằm ngoài khung của bậc đã chọn, hệ thống cảnh báo để kiểm tra nhưng vẫn cho lưu.

Với nhân viên **Thử việc**, bảng lương tính 80% mức lương riêng trước khi áp công và phụ cấp; nhân viên thử việc **chưa đóng** các khoản bảo hiểm bắt buộc.

> ⚠️ Bước này **không còn ô "Phụ cấp ca"**. Tiền cơm/phụ cấp ca đã chuyển sang tự tính theo ca thực làm — xem mục 2.8. Cũng không còn ô "Nhóm lương/Bậc lương" (`payroll_group`/`pay_grade_key`) — hai trường này đã bị bỏ khỏi màn vì không ảnh hưởng tới tiền lương.
>
> **Danh mục khoản thu nhập** (chịu thuế/miễn thuế, ví dụ trang phục, tiền nhà, đi lại…) **không gán được ở bước này**. Gán khoản cho từng người làm ở **Lương → Lương nhân viên → Sửa lương → "+ Thêm khoản thu nhập"** sau khi đã tạo hồ sơ — xem mục 2.9.

#### Bước 4 - Đính kèm

- Tải lên hợp đồng, CCCD, hồ sơ bảo hiểm hoặc tài liệu liên quan nếu có.

#### Bước 5 - Tài khoản

- Có thể cấp tài khoản đăng nhập và vai trò ngay khi tạo hồ sơ.
- Công nhân không sử dụng hệ thống có thể để chưa cấp tài khoản.
- Chọn **Lưu & xem hồ sơ** để hoàn tất.

### 2.5. Điều chỉnh lương và giữ lịch sử

Menu: **Nhân sự & Lương → Lương → Lương nhân viên → Thiết lập lương**.

1. Tìm nhân viên theo tên hoặc mã.
2. Chọn **Thiết lập lương**.
3. Nhập **Hiệu lực từ**.
4. Điều chỉnh lương vị trí, lương trách nhiệm, bậc, chuyên cần và phụ cấp.
5. Chọn **Lưu điều chỉnh**.

Ô **"Phụ cấp ca"** trên màn này giờ mang nhãn **"Phụ cấp ca (đã ngưng)"**, hiện chỉ để đọc — không còn ra tiền từ 03/08/2026, đừng cố sửa số ở đây. Muốn đổi mức cơm/phụ cấp ca thật, vào **Chấm công → Ca làm việc** (mục 2.8).

| Cách nhập ngày | Kết quả |
|---|---|
| Chọn đúng ngày của một mốc đã có | Sửa mốc đó, không tạo bản trùng ngày. |
| Chọn một ngày hiệu lực mới | Tạo phiên bản mới và giữ nguyên lịch sử cũ. |
| Chọn ngày trước ngày vào làm | Hệ thống từ chối. |

**Ví dụ:** Nhân viên có lương 8.000.000 đồng từ 01/01/2026. Tăng lên 9.000.000 đồng từ 01/07/2026 thì phải tạo mốc 01/07/2026. Khi xem kỳ tháng 5, hệ thống vẫn dùng 8.000.000 đồng; kỳ tháng 7 dùng mức mới.

### 2.6. Chuyển tổ và nâng bậc

Tại chi tiết hồ sơ nhân viên:

- Chọn **Điều chuyển phòng/tổ** để chọn tổ mới, bậc thuộc tổ mới và ngày hiệu lực.
- Chọn **Nâng bậc/Chức danh** để chọn bậc mới, chức danh mới và ngày hiệu lực.

Khi chuyển tổ hoặc nâng bậc, hệ thống tạo mốc lịch sử mới và **giữ nguyên tiền lương hiện tại**. Nếu hợp đồng quy định thay đổi tiền, thực hiện thêm một lần **Điều chỉnh lương** với cùng ngày hiệu lực.

Nếu tổ mới chưa có thang bậc, hệ thống giữ nguyên tiền và để nhân viên ở trạng thái chưa xếp bậc.

### 2.7. Gán ca làm việc

Ca được gán theo **ngày hiệu lực**, không cần gán lại từng ngày. Khi đổi ca, tạo lần gán mới từ ngày bắt đầu áp dụng. Dữ liệu cũ vẫn dùng ca có hiệu lực tại thời điểm quá khứ.

### 2.8. Tiền cơm và phụ cấp ca — khai THEO TỪNG CA, tự cộng theo công thực làm

> ⚠️ Mục này đổi hai lần liên tiếp trong tháng 7-8/2026, đọc kỹ để khỏi làm theo cách cũ:
> **không phải** mức cố định 25.000đ/50.000đ áp chung toàn công ty (cách cũ trước 20/07), **cũng không phải**
> số khai tay theo từng người trong hồ sơ lương (cách áp dụng 20/07–02/08). Từ **03/08/2026**, mỗi
> **ca làm việc** tự khai mức cơm và mức phụ cấp riêng của ca đó.

**Khai mức:** Menu **Nhân sự & Lương → Chấm công → tab "Ca làm việc"**, chọn **Sửa** một ca. Mỗi ca có 2 ô riêng:

- **Phụ cấp cơm (đ):** mặc định 25.000đ khi tạo ca mới, sửa được theo từng ca.
- **Phụ cấp ca (đ):** mặc định 50.000đ khi tạo ca mới, sửa được theo từng ca.

**Cách tính vào lương:** với mỗi ca một nhân viên có làm trong tháng, hệ đếm số ngày công của ca đó đạt từ **0,5 công trở lên** (ngưỡng này khai được ở **Cấu hình lương → tab "Cơ chế lương theo bộ phận" → khối "Áp dụng toàn công ty"**). Ngày nào đạt ngưỡng thì được cộng **trọn vẹn** mức của ca đó — **không chia tỷ lệ theo công thực tế**, vì đây là suất ăn/suất ca, có hoặc không, không có nửa suất.

```
Tiền cơm      = Σ (mức Phụ cấp cơm của ca) × (số ngày đạt ngưỡng công của ca đó)
Phụ cấp ca    = Σ (mức Phụ cấp ca của ca)   × (số ngày đạt ngưỡng công của ca đó)
```

Người làm hai ca khác nhau trong tháng thì cộng dồn theo từng ca đã làm; người làm hai ca trong **cùng một ngày** (ca gãy) tính theo dữ liệu chấm công của từng ca như bình thường.

Cả hai khoản đều được **miễn thuế TNCN toàn bộ**, không áp trần luật (ví dụ trần 730.000đ/tháng của tiền ăn ca theo luật) — đây là chốt cố ý của doanh nghiệp, không phải thiếu sót.

Ô "Phụ cấp ca" cũ trong hồ sơ lương từng người **đã ngưng dùng** — xem ghi chú ở mục 2.5.

### 2.9. Danh mục khoản thu nhập — khoản nào chịu thuế TNCN, khoản nào miễn

Trước đây mọi phụ cấp khác (trang phục, tiền nhà, đi lại…) gộp chung một ô và bị tính thuế hết. Nay có danh mục riêng để phân biệt khoản chịu thuế và khoản miễn thuế.

**Quản lý danh mục** (thêm/xoá/bật-tắt loại khoản): Menu **Nhân sự & Lương → Lương → Cấu hình lương → tab "Danh mục khoản thu nhập"**.

- Mỗi khoản có: tên, loại **Thu** (cộng vào lương) hoặc **Trừ** (khấu trừ), cờ **Chịu thuế / Miễn thuế**, thứ tự hiển thị.
- Khoản **chưa từng dùng ở kỳ lương nào** thì xoá hẳn được. Khoản **đã dùng rồi** không xoá cứng được, chỉ chuyển **Ngưng dùng** — biến mất khỏi form nhập mới nhưng phiếu lương kỳ cũ vẫn giữ nguyên số.
- Đổi cờ Chịu thuế/Miễn thuế chỉ ảnh hưởng kỳ **tính từ đó về sau**; kỳ đã chốt giữ nguyên số cũ.
- Có màn gán hàng loạt khoản cho nhiều nhân viên cùng lúc (lọc theo tổ).

**Gán khoản cho từng người:** Menu **Nhân sự & Lương → Lương → Lương nhân viên → Sửa lương → "+ Thêm khoản thu nhập"**. Mỗi dòng khoản đã gán hiện badge **Chịu thuế** hoặc **Miễn thuế** ngay cạnh số tiền để dễ kiểm tra.

> Danh mục này **không có mặt ở Hồ sơ nhân sự** — đây là chốt cố ý, tránh hai chỗ khai cùng một khoản. Gán/sửa khoản thu nhập của một người luôn thực hiện ở màn **Lương nhân viên**.

### 2.10. Chuyên cần

Khai riêng cho từng nhân viên ở hồ sơ lương (mục 2.4/2.5). Tổ chỉ còn công tắc bật/tắt loại chuyên cần, mức tiền vẫn khai theo từng người, không khai = 0đ.

Tính theo kiểu **trừ dần** khi có ngày nghỉ trong tháng:

```
Tỷ lệ hưởng = max(0, 1 − 0,5 × số ngày nghỉ trong tháng)
```

Ví dụ mức chuẩn 300.000đ: nghỉ 0,5 ngày → còn 75% = 225.000đ; nghỉ 1 ngày → còn 50% = 150.000đ; nghỉ từ 2 ngày trở lên → mất hết.

### 2.11. Tăng ca và lương khoán — loại trừ nhau

Mỗi tổ chỉ bật được **một trong hai**: **Tăng ca** (tính theo giờ làm thêm thật) hoặc **Lương khoán** (tính theo sản lượng). Bật khoán sẽ tự tắt tăng ca của tổ đó.

> 🔴 **Tiền khoán theo sản lượng hiện luôn = 0đ.** Đơn giá khoán khai được ở Cấu hình lương → "Cơ chế lương theo bộ phận", nhưng hệ thống **chưa có nguồn dữ liệu sản lượng** để tính ra tiền (chờ nối với Lệnh sản xuất). Tổ nào đang bật khoán (ví dụ tổ Kho) thì người trong tổ đó **mất cả tăng ca lẫn khoán** — chỉ còn lương công. Trước khi chạy lương cho tổ có bật khoán, kiểm tra kỹ và cân nhắc tạm tắt khoán nếu tổ đó thực tế đang cần trả tăng ca.

### 2.12. Chốt kỳ công và chốt kỳ lương — hai lần khoá khác ý nghĩa

**Khoá 1 — Chốt kỳ công:** chụp Bảng công tháng thành ảnh đóng băng; lương đọc ảnh này chứ không đọc số đang sống. Bị chặn nếu còn đơn treo (nghỉ phép/đi trễ-về sớm/chỉnh công) chưa duyệt.

**Khoá 2 — Chốt kỳ lương:** bảng lương đi qua ba trạng thái Nháp → Đã chốt → Đã chi.

> ⚠️ **Mở lại kỳ công bị chặn khi kỳ lương đã "Đã chốt" HOẶC đã "Đã chi"** — trước đây hệ chỉ chặn khi "Đã chốt", nên có kẽ hở: lương đã phát tiền thật rồi mà bảng công phía sau vẫn sửa được. Nay:
> - Kỳ lương **Đã chi**: thông báo *"Kỳ lương tháng này ĐÃ CHI — tiền đã phát, không mở lại kỳ công."*
> - Kỳ lương **Đã chốt** (chưa chi): thông báo *"Kỳ lương tháng này đã chốt — không mở lại kỳ công."*
>
> Muốn sửa sai sót của một kỳ đã chi: **Hủy đã chi** kỳ lương → **Mở lại** kỳ lương → lúc đó kỳ công mới mở lại được. Nếu không muốn lùi cả kỳ, xử bằng truy lĩnh/khấu trừ ở kỳ sau.

## 3. Thu mua

### 3.1. Luồng tổng quát

**Phòng ban tạo YCMH không có giá → Thu mua lập PMH có giá → Người có quyền duyệt Thu mua duyệt (thao tác ở màn Kế toán) → Thu mua đi mua và nhận hàng → Kế toán lập Phiếu chi → theo dõi Công nợ.**

Mã YCMH được gắn vào PMH để truy ngược từ Phiếu chi về đúng nhu cầu ban đầu.

> Nút **Duyệt / Từ chối không nằm ở màn Mua hàng** — màn đó chỉ còn Xem · In · Sửa · Gửi duyệt · Huỷ · Xoá. Người duyệt thao tác ở `Kế toán → Kế toán thu mua → Đơn mua hàng`, nhưng bản thân quyền Duyệt/Từ chối là quyền **Thu mua** (`thu_mua:approve`), tách hẳn khỏi quyền lập Phiếu chi (`ke_toan:create`) — xem mục 4.1. Đường "duyệt và lập phiếu chi trong một cú bấm" đã **gỡ hẳn**, không còn tồn tại dưới bất kỳ hình thức nào.

### 3.1b. Phạm vi nhìn thấy và thao tác trên phiếu mua hàng — MỚI

Không phải ai có quyền `thu_mua:update` cũng đụng được vào mọi phiếu. Phạm vi áp dụng cho **cả xem lẫn sửa/gửi duyệt/huỷ/xoá/đánh dấu đã mua/đã nhận/sửa số nhận/lùi trạng thái**:

| Vai trò | Thấy và thao tác được với phiếu nào |
|---|---|
| Nhân viên mua hàng | Chỉ phiếu **do chính mình lập** |
| Trưởng bộ phận mua hàng | Phiếu của **cả phòng Thu mua** (mọi nhân viên cùng phòng) |
| Kế toán | **Toàn bộ** phiếu công ty |
| Người không thuộc hai module Thu mua/Kế toán | Coi như mức chặt nhất — chỉ phiếu của chính mình |

Gọi thẳng một phiếu ngoài phạm vi (kể cả biết đúng mã/ID) chỉ nhận được **"Không tìm thấy phiếu"** — hệ thống cố ý không phân biệt "không tồn tại" với "không có quyền", để không lộ thông tin cho người ngoài phạm vi. Đây là chốt vá ngày 05/08/2026: trước đó chỉ đường xem bị giới hạn phạm vi, còn sửa/xoá/gửi duyệt/đánh dấu nhận hàng thì gọi thẳng theo ID vẫn được dù phiếu không phải của mình.

### 3.2. Khai nhà cung cấp

Menu: **Thu mua → Nhà cung cấp → Thêm nhà cung cấp**.

Các trường bắt buộc:

- Tên nhà cung cấp.
- Nhóm nhà cung cấp.
- Mã số thuế.
- Người liên hệ.
- Số điện thoại.
- Email.
- Địa chỉ.

> Điều khoản thanh toán và ghi chú là thông tin bổ sung. Nhà cung cấp ngừng hợp tác có thể chuyển sang trạng thái không hoạt động; nhà cung cấp này không được chọn khi lập PMH mới.

#### 🔴 Bắt buộc: khai danh mục mặt hàng của nhà cung cấp

Mỗi nhà cung cấp phải khai **họ bán những gì** — tên mặt hàng, đơn vị tính, đơn giá, VAT.

Không khai thì **lập PMH sẽ bị chặn**, báo *"Nhà cung cấp này không bán …"*. Đây là chốt cố ý, ngăn
chọn nhầm nhà cung cấp không bán món đó.

Danh mục này còn dùng để máy **tự gợi ý nhà cung cấp rẻ nhất** cho từng dòng hàng khi lập phiếu.

### 3.3. Phòng ban tạo Yêu cầu mua hàng

Menu: **Thu mua → Yêu cầu mua hàng → Tạo yêu cầu mua**.

1. Chọn nguồn/bộ phận phát sinh.
2. Nhập ngày cần hàng và mục đích.
3. Thêm ít nhất một dòng vật tư.
4. Mỗi dòng chỉ nhập tên vật tư, đơn vị tính, số lượng và ghi chú nếu có.
5. Lưu yêu cầu.

YCMH **không nhập đơn giá, giảm giá hoặc VAT**. Giá do Thu mua làm việc với nhà cung cấp và nhập ở PMH.

**Sửa/Huỷ YCMH của mình:** người tạo có thể **Sửa** yêu cầu khi còn ở trạng thái **Chờ Thu mua xử lý**. **Huỷ** thực hiện được bởi người tạo hoặc tài khoản có quyền huỷ chung, cũng chỉ khi còn **Chờ Thu mua xử lý**.

**Xem tình trạng từng dòng vật tư:** mở chi tiết một yêu cầu, bảng vật tư có thêm cột **Nhà cung cấp** và **Tình trạng** cho từng dòng — dòng nào đã nhận, dòng nào còn chờ duyệt, dòng nào bị từ chối cần lập lại, có cảnh báo khi giao thiếu so với số đặt. Bên dưới là danh sách các phiếu mua đã lập.

Yêu cầu tạo **trước ngày 05/08/2026** sẽ hiện *"Chưa rõ"* ở cột này — hệ cố ý không đoán mò theo tên hàng cho dữ liệu cũ, vì đoán trượt thì hiện sai mà không ai biết.

### 3.4. Thu mua lập Phiếu mua hàng

Menu: **Thu mua → Mua hàng**.

1. Tại danh sách chờ xử lý, chọn **đúng MỘT** YCMH. *(Một phiếu mua chỉ gắn được một yêu cầu.)*
2. Chọn **Tạo phiếu mua từ yêu cầu**. Các dòng hàng tự đổ ra từ yêu cầu.
3. Kiểm cột **Nhà cung cấp của từng dòng** — máy đã tự gán sẵn nơi **rẻ nhất** (gợi ý tối đa 5 nhà cung cấp đang hoạt động có bán mặt hàng đó, xếp theo giá tăng dần kèm VAT). Dòng nào chưa ai
   bán thì để trống và ô chọn sẽ nói rõ.
4. Nhập ngày cần hàng, ngày dự kiến nhận hàng nếu có và mục đích. Ngày dự kiến nhận hàng chỉ cần **từ hôm nay trở đi**, không bắt buộc phải sau ngày cần hàng — nhận sớm hơn dự kiến là điều mong muốn, không phải lỗi.
5. Với từng dòng, nhập **đơn giá, giảm giá (%), thuế GTGT (%)**.
6. Xem khối **"Sẽ tạo N phiếu"** — nó báo trước YCMH sẽ tách ra mấy phiếu và tổng tiền mỗi phiếu, trước khi bấm Lưu.
7. Lưu. Phiếu ở trạng thái **Nháp**.
8. Chọn **Gửi duyệt** để chuyển sang **Chờ duyệt**.

#### Ba điều cần nhớ khi lập phiếu

**① Nhà cung cấp gán theo TỪNG DÒNG, không phải cho cả phiếu.** Yêu cầu chứa hàng của hai nơi thì
khi lưu sẽ ra **hai phiếu**, mỗi phiếu một nhà cung cấp. Vì một phiếu mua là thoả thuận với **một**
nhà cung cấp. Gọi lệnh tạo phiếu hai lần cho cùng một yêu cầu **không làm được** — lần đầu đã giữ chỗ yêu cầu nguồn, lần hai bị chặn; phải dùng đúng đường tạo theo lô ở bước 6.

**② Thu mua KHÔNG sửa được Vật tư · Đơn vị tính · Số lượng.** Đó là con số bộ phận đã xin. Thu mua
chỉ quyết mua ở đâu và giá bao nhiêu.

**③ Không có nút thêm dòng / xoá dòng.** Muốn đổi danh mục hàng thì bộ phận sửa yêu cầu.

Công thức từng dòng:

1. Tiền hàng = Số lượng × Đơn giá.
2. Tiền giảm giá = Tiền hàng × Giảm giá (%).
3. Tiền tính thuế = Tiền hàng − Tiền giảm giá.
4. Tiền VAT = Tiền tính thuế × VAT (%).
5. Thành tiền = Tiền tính thuế + Tiền VAT.

### 3.5. Trạng thái cần hiểu

| PMH | Ý nghĩa và thao tác tiếp theo |
|---|---|
| Nháp | Thu mua được sửa/xóa và gửi duyệt (chỉ phiếu do mình lập, hoặc cả phòng nếu là trưởng bộ phận). |
| Chờ duyệt | Người duyệt đang xem xét (ở màn Kế toán → Đơn mua hàng). |
| Từ chối | Thu mua sửa lại và gửi duyệt lần nữa, hoặc lập phiếu khác. |
| Đã duyệt | Được phép mua và lập chứng từ thanh toán. |
| Đã mua | Đã đặt/mua, chờ hàng về. |
| Đã nhận | Hàng đã về. **Đây là mốc phát sinh CÔNG NỢ.** |
| Đã hủy | Không tiếp tục xử lý. |

**Huỷ phiếu:** người **không có** quyền duyệt chỉ huỷ được **phiếu Nháp do chính mình lập**. Phiếu đã gửi duyệt (Chờ duyệt trở đi) chỉ người **có quyền duyệt** mới huỷ được — vì đó là quyết định vượt khỏi tay thu mua thường. PMH đã có chứng từ thanh toán đang chờ hoặc đã chi thì **không được hủy** dù ai thao tác.

#### Trạng thái của YÊU CẦU thì suy từ các phiếu con

Một yêu cầu tách thành nhiều phiếu, các phiếu chạy lệch nhịp. Trạng thái yêu cầu **luôn lấy theo
phần chậm nhất**:

```
Chờ mua  <  Chờ duyệt  <  Đang mua  <  Xong
```

Nên duyệt **một** phiếu trong hai thì yêu cầu **vẫn Chờ duyệt** — không phải lỗi. Chỉ khi mọi phần
đã về hàng, yêu cầu mới **Xong**.

Phiếu **bị từ chối** hoặc **đã huỷ** kéo yêu cầu về **Chờ mua**, để thu mua lập phiếu khác cho phần
đó. Hệ tự tính lại trạng thái yêu cầu ở **mọi** thao tác chạm tới phiếu con (gửi duyệt, duyệt, từ chối, đã mua, đã nhận, lùi đã nhận, huỷ, xoá) — không chỉ lúc nhận hàng như trước — nên trạng thái yêu cầu luôn khớp đúng tiến độ thật của từng phiếu, kể cả khi một phiếu bị từ chối rồi lập lại phiếu khác cho đúng phần hàng đó.

### 3.6. Nhận hàng và khai SỐ THỰC NHẬN

Phiếu ở trạng thái **Đã mua** → bấm **Đã nhận**.

Hệ mở hộp liệt kê các dòng hàng, ô số lượng **đã điền sẵn bằng số đã đặt**:

- Hàng về **đủ** → bấm Xác nhận luôn, không phải gõ gì.
- Hàng về **thiếu** → sửa con số xuống.

> **Vì sao phải khai:** công nợ và trần lập phiếu chi đều tính theo **số thực nhận**. Nhà cung cấp
> giao 800/1000 tờ mà hệ vẫn ghi đủ 1000 thì kế toán **chi thừa tiền thật**.

Không được khai **nhiều hơn** số đặt. Nhận dư thật thì sửa đơn rồi duyệt lại, vì khai vống lên là
chi vượt giá trị giám đốc đã duyệt mà không qua duyệt lần nữa.

**Giao nhiều đợt:** đợt 1 khai 600, đợt 2 về thì bấm **Sửa số nhận** và sửa lên 1000. Thao tác này
cần **quyền duyệt** vì nó đổi số nợ đã ghi trên màn kế toán, và không được hạ số xuống dưới phần đã chi/đang chờ chi.

### 3.7. Lùi lại khi bấm nhầm "Đã nhận hàng"

Bấm nhầm là **đẻ ra một món nợ** trên bàn kế toán. Ở phiếu đã nhận có nút **Lùi đã nhận**:

- Cần **quyền duyệt** — không phải việc nhân viên tự quyết
- **Bắt buộc ghi lý do**, lưu vào nhật ký
- Phiếu quay về **Đã mua**, yêu cầu nguồn rời khỏi *Xong*, món nợ biến mất khỏi màn Công nợ

**Bị chặn nếu đơn đã có Phiếu chi ĐÃ CHI** — tiền rời két rồi thì không quay lại khai *"chưa nhận
hàng"*. Phiếu mới ở trạng thái *Chờ chi* thì vẫn lùi được.

### 3.8. In PMH

Chọn **In phiếu** tại cột Thao tác của PMH. Nếu trình duyệt không mở bản in, hãy cho phép cửa sổ bật lên (pop-up) cho địa chỉ hệ thống.

## 4. Kế toán

### 4.1. Quyền sử dụng

Không phân biệt cứng "kế toán trưởng" hay "kế toán thường". Quản trị viên cấp quyền theo người/vai trò:

- **Xem:** thấy danh sách và chi tiết chứng từ.
- **Lập Phiếu chi:** tạo chứng từ chi từ PMH đã duyệt — quyền `ke_toan:create`.
- **Xác nhận đã chi:** xác nhận tiền thực tế đã xuất.
- **Hủy chứng từ chờ chi:** hủy chứng từ chưa thanh toán.
- **In/xuất chứng từ:** in phiếu.

> ⚠️ **Nút Duyệt/Từ chối PMH ở màn Kế toán → Đơn mua hàng thực chất là quyền của module Thu mua
> (`thu_mua:approve`), KHÔNG phải quyền kế toán.** Người chỉ được cấp quyền kế toán (`ke_toan:*`) sẽ
> **không** thấy nút Duyệt/Từ chối trên màn này dù đứng ở đúng màn — chỉ thấy nút **Lập phiếu chi**.
> Muốn một kế toán viên cũng duyệt được PMH thì phải cấp thêm quyền `thu_mua:approve` cho họ, y hệt
> như cấp cho người bên phòng Thu mua. Tách hai quyền này cố ý để kế toán không tự duyệt khoản chi
> rồi tự viết phiếu chi cho chính khoản đó.
>
> Kế toán **không có quyền duyệt** vẫn thấy đủ danh sách và trạng thái PMH (kế toán luôn thấy toàn bộ phiếu công ty, không giới hạn phạm vi — mục 3.1b), chỉ không thấy nút Duyệt.

**Chưa có vai "Kế toán" nào được tạo sẵn.** Trên hệ mới, quản trị viên phải tự tạo vai và cấp
quyền ở màn Phân quyền; nếu không thì chỉ giám đốc vào được các màn kế toán.

### 4.2. Duyệt PMH và lập Phiếu chi — HAI BƯỚC, HAI QUYỀN KHÁC NHAU

Menu: **Kế toán → Kế toán thu mua → Đơn mua hàng**.

Mặc định màn này lọc **"Tất cả"** trạng thái (trước đây từng mặc định lọc "Chờ duyệt" khiến kế toán tưởng chưa có gì để lập phiếu chi). Đơn **Nháp** không xuất hiện ở đây.

**Bước 1 — Duyệt** *(người có quyền `thu_mua:approve`, mặc định là Giám đốc)*

1. Chọn PMH đang *Chờ duyệt*, kiểm nhà cung cấp, YCMH nguồn, dòng hàng, giảm giá, VAT, tổng tiền.
2. Chọn **Duyệt**, hoặc **Từ chối** kèm lý do.

**Bước 2 — Lập Phiếu chi** *(người có quyền `ke_toan:create`)*

Chỉ PMH **đã duyệt** trở lên (Đã duyệt/Đã mua/Đã nhận) và còn giá trị chưa lập phiếu mới hiện nút **Lập phiếu chi**.

> Đơn nào nhà cung cấp **giao thiếu** thì dưới *Tổng PMH* có thêm dòng **"Thực nhận …"**. Trần lập
> phiếu chi bám con số thực nhận, không bám tổng đơn.

### 4.3. Hiểu các đợt thanh toán

Giả sử tổng PMH là **4.500.000 đồng**:

| Đợt thanh toán | Khi dùng | Ví dụ số tiền |
|---|---|---:|
| Tạm ứng/Đặt cọc | Chi trước khi nhận đủ hàng hoặc trước khi nhà cung cấp thực hiện. | 1.500.000 |
| Thanh toán một phần | Trả một phần công nợ, vẫn còn số tiền phải trả. | 2.000.000 |
| Thanh toán cuối | Khoản chi làm số còn lại của PMH về 0. | 4.500.000 nếu chưa chi; hoặc 2.500.000 nếu đã chi 2.000.000. |
| Khác | Trường hợp đặc biệt không thuộc ba nhóm trên; cần ghi rõ nội dung. | Theo thực tế |

Nếu số tiền bằng đúng phần còn được lập, hãy chọn **Thanh toán cuối**. Nếu chi một nửa trước, lập phiếu thứ nhất là **Tạm ứng/Đặt cọc** hoặc **Thanh toán một phần**; khi chi nửa còn lại, lập phiếu thứ hai và chọn **Thanh toán cuối**.

Hệ thống không cho tổng các Phiếu chi đang chờ và đã chi vượt quá tổng PMH sau khi trừ các khoản đã thu hồi.

### 4.4. Lập và xác nhận Phiếu chi

Khi lập Phiếu chi, nhập:

- Đợt thanh toán.
- **Ngày chứng từ** và **Hạn trả tiền** — cả hai **bắt buộc**.
- Số tiền nguyên tệ, loại tiền và tỷ giá.
- Nội dung chi.
- Người nhận tiền, địa chỉ và giấy tờ nếu chi tiền mặt.
- Số hóa đơn, ngày hóa đơn, số hợp đồng nếu có.
- Tài khoản Nợ/Có nếu cần in trên chứng từ.
- Ghi chú và tệp đính kèm.

Sau khi lưu, Phiếu chi ở trạng thái **Chờ chi**. Trạng thái này có nghĩa là Kế toán đã lập chứng từ nhưng tiền chưa nhất thiết rời quỹ.

Khi đã giao tiền/chuyển tiền thực tế, chọn **Xác nhận đã chi**. Phiếu chuyển sang **Đã chi** và không còn được sửa/hủy như phiếu chờ.

#### Hạn trả tiền — vì sao bắt buộc

Cột **Quá hạn** ở màn Công nợ so `hạn trả < hôm nay`. Phiếu **không có hạn** thì **không bao giờ**
rơi vào cột đó — kế toán nhìn bảng thấy *Quá hạn 0đ* rồi yên tâm trong khi có phiếu trễ cả tháng.

Phiếu cũ lỡ tạo thiếu hạn sẽ mang badge **`Chưa đặt hạn`** và bị đẩy lên đầu danh sách.

#### Bốn luật về ngày

| Trường hợp | |
|---|---|
| Ngày chứng từ ở **tương lai** | ❌ chặn |
| Ngày hoá đơn ở **tương lai** | ❌ chặn |
| Hạn trả **trước** ngày chứng từ | ❌ chặn |
| Ngày ở **quá khứ** | ✅ **cho phép** |

> Quá khứ là hợp lệ và cần thiết: chi tiêu phát sinh 28/7 mà hoá đơn về 5/8 thì phiếu phải mang
> ngày **28/7** mới vào đúng kỳ kế toán. Hạn trả quá khứ cũng vậy — nhập bù khoản đã trễ thì giữ
> đúng ngày để nó hiện đỏ ngay; ép sang tương lai là **làm giả nợ**.

#### Số hoá đơn — quan trọng khi giao nhiều đợt

Mục **Chứng từ tham chiếu** có ô *Số hoá đơn* + *Ngày hoá đơn*. Một đơn giao ba đợt thì lập ba phiếu
chi, mỗi phiếu mang số hoá đơn riêng và **hạn trả riêng**. Không có số hoá đơn thì ba dòng trên màn
Công nợ trông y hệt nhau, không biết dòng nào là đợt nào.

### 4.5. Ủy nhiệm chi

Chức năng tạo mới **Ủy nhiệm chi đang tạm ẩn** trong phiên bản hiện tại. Các UNC cũ vẫn hiển thị và in đúng loại chứng từ. Khi doanh nghiệp bật lại chức năng, cần khai tài khoản ngân hàng công ty và tài khoản thụ hưởng của nhà cung cấp trước khi lập UNC.

### 4.6. Chứng từ đính kèm và in phiếu

- Có thể đính kèm ảnh hóa đơn, biên nhận hoặc PDF.
- Chứng từ đã chi nhưng chưa có tệp sẽ được nhắc **Thiếu chứng từ**.
- Chọn **In phiếu** ở danh sách Phiếu chi; không cần lặp nút in trong panel chi tiết.
- Nếu bản in không mở, cho phép pop-up trên trình duyệt.

### 4.7. Phiếu thu hoàn ứng

Khi tiền đã chi không sử dụng hết, tại Phiếu chi đã chi chọn **Lập Phiếu thu**.

1. Nhập người nộp tiền và số tiền nộp lại.
2. Chọn tiền mặt hoặc chuyển về tài khoản công ty — chuyển khoản thì phải nhập **mã giao dịch /
   số báo có**.
3. Lưu Phiếu thu → **Đã thu** ngay. Chỉ lập phiếu khi tiền đã thực về; không còn bước
   *Xác nhận đã thu* (bỏ 27/08/2026). Lập nhầm thì **Hủy** (bắt nhập lý do) rồi lập lại.

Số đã thu làm giảm số tiền chi ròng của PMH và mở lại hạn mức được phép lập Phiếu chi. Tổng Phiếu thu không được vượt số đã chi của Phiếu chi nguồn.

### 4.8. Công nợ phải trả

Menu: **Kế toán → Kế toán thu mua → Công nợ phải trả**.

Màn này là một **bảng thật + drawer chi tiết**, nhưng bên trong **không có bảng dữ liệu nào lưu công
nợ** — mọi con số được cộng lại từ PMH và phiếu chi ngay lúc mở màn. Không ai gõ tay sửa được, nên nó không bao giờ lệch với chứng từ.

#### Bốn ô số đầu màn

**Tổng phải trả** · **Quá hạn** · **Chưa vào sổ** · **Đã trả (3 tháng)**

Kèm các pill lọc nhanh: **Tất cả** · **Quá hạn** · **Sắp tới hạn 7 ngày** · **Chưa lập phiếu**.

#### Bảng chính — theo từng nhà cung cấp

Cột: Nhà cung cấp · Đơn còn nợ · Chưa vào sổ · Chờ chi · Quá hạn · Đã trả (kỳ) · Tổng còn nợ. Bấm vào **bất kỳ số nào** trong bảng sẽ mở **drawer chi tiết** đúng nhà cung cấp và đúng rổ vừa bấm.

#### Một đồng tiền đi qua bốn chặng

| Chặng | Chuyện gì | Cột |
|---|---|---|
| 1 | Đơn đã duyệt, **hàng chưa về** | *chưa ở đâu cả* — chưa nợ ai |
| 2 | Hàng về rồi, **chưa lập phiếu chi** | **Chưa vào sổ** |
| 3 | Đã lập phiếu, **tiền chưa ra** | **Chờ chi** |
| 4 | Bấm *Đã chi*, **tiền rời két** | **Đã trả (3 tháng)** |

**Chặng 2 + 3 = Tổng còn nợ.**

Đặt hàng thì chưa nợ ai — nên đơn đã duyệt mà hàng chưa về **không hiện ở màn này**. Đó là đúng, không phải sót.

> Cột **"Chưa vào sổ"** là lý do màn này tồn tại: hàng đã về mà kế toán chưa kịp lập phiếu thì món
> nợ đó vẫn phải hiện. Không có nó thì bảng sạch bong trong khi đang nợ — nhìn tưởng không nợ ai,
> tới lúc nhà cung cấp gọi đòi mới biết.

#### Drawer chi tiết — ba khối

Bấm vào tên hoặc số của một nhà cung cấp mở drawer, có 3 khối:

| Khối | Nội dung |
|---|---|
| 🔴 **Hàng đã nhận, chưa lập phiếu** | Có nút **Lập phiếu chi**, nhảy thẳng sang đúng đơn đó |
| 🟡 **Đã lập phiếu, chờ chi** | Cột Hoá đơn · Hạn trả · badge *Quá hạn N ngày* / *Chưa đặt hạn* |
| ✅ **Đã trả (3 tháng)** | Từng **lần trả** — ngày · phiếu · hoá đơn · đơn nguồn · số tiền; gập/mở, phân trang 10 dòng |

Mọi con số trên bảng đều **bấm được**, mở thẳng vào đúng khối đó.

#### Làm sao biết đã trả hết nợ một nhà cung cấp

Họ **vẫn nằm trên bảng** với *Tổng còn nợ* **0đ**, kèm nhãn **Đã trả hết** và số tiền đã trả làm
bằng chứng — chứ không biến mất.

Nhà cung cấp đã im lặng hơn 3 tháng thì gõ tên vào **ô tìm** là vẫn ra (ô tìm lọc trên toàn bộ nhà cung cấp, kể cả không nợ gì); trong đó có nút **Xem lịch
sử cũ hơn** để mở toàn bộ, không bị giới hạn 3 tháng.

> **Kỳ 3 tháng chỉ cắt phần ĐÃ TRẢ.** Nợ chưa trả **không bao giờ rơi** — đơn nợ từ năm ngoái hôm
> nay vẫn hiện đủ.

#### 🔴 Khi màn báo lỗi

Tải hỏng thì bốn ô hiện **`—`** kèm banner đỏ, **không bao giờ hiện `0đ`**.

Lý do: *"0đ"* và *"hết nợ"* nhìn giống hệt nhau. Nếu màn hỏng mà vẫn hiện 0đ thì người xem tin là đã
trả hết trong khi thực tế đang nợ. Thấy `0đ` **kèm câu "Không còn nợ nhà cung cấp nào — chốt lúc …"**
mới là hết nợ thật.

Đối chiếu công nợ với nhà cung cấp hiện làm **thủ công**: đặt bảng "Đã trả" cạnh sao kê nhà cung cấp để soát từng dòng — hệ thống chưa có chức năng xuất báo cáo đối chiếu riêng.

### 4.9. Truy vết chứng từ

Chuỗi truy vết chuẩn:

**YCMH phòng ban → PMH Thu mua → Phiếu chi Kế toán → Phiếu thu hoàn ứng (nếu có).**

Khi kiểm tra một khoản chi, đối chiếu tối thiểu:

- Mã Phiếu chi.
- Mã PMH nguồn.
- Mã YCMH nguồn.
- Nhà cung cấp.
- Người tạo PMH, người duyệt và thời điểm duyệt.
- Tổng PMH, đã chi, đang chờ chi, đã thu lại và số còn được lập.

## 5. Các lỗi thường gặp

### Không thấy menu hoặc nút thao tác

Tài khoản chưa có quyền. Quản trị viên cần cấp đúng quyền đọc/tạo/sửa/duyệt/xác nhận trạng thái cho vai trò.

### Không lưu được nhân viên ở bước Lương & BHXH

Kiểm tra Lương vị trí phải lớn hơn 0, bậc phải thuộc đúng tổ và ngày hiệu lực không trước ngày vào làm.

### Đổi bậc nhưng tiền lương không đổi

Đây là hành vi đúng. Bậc chỉ để phân loại. Nếu hợp đồng đổi tiền, vào **Lương nhân viên** và tạo điều chỉnh có cùng ngày hiệu lực.

### Sửa "Phụ cấp ca" ở Lương nhân viên mà lương không đổi

Đây là hành vi đúng. Ô đó đã **ngưng dùng** từ 03/08/2026, chỉ để đọc. Muốn đổi tiền cơm/phụ cấp ca thật, sửa ở **Chấm công → Ca làm việc → Sửa ca**.

### YCMH không có ô đơn giá

Đúng nghiệp vụ. Phòng ban chỉ yêu cầu số lượng; Thu mua nhập giá tại PMH.

### PMH không hủy được

PMH đã nhận hàng, đã hủy hoặc đã có Phiếu chi đang chờ/đã chi thì không thể hủy. Ngoài ra, phiếu đã gửi duyệt chỉ người **có quyền duyệt** mới huỷ được — nhân viên thường không huỷ được phiếu đã ở trạng thái Chờ duyệt trở đi.

### Mở một phiếu mua hàng theo đúng mã nhưng báo "Không tìm thấy"

Kiểm tra phạm vi tài khoản: nhân viên mua hàng chỉ thấy phiếu do chính mình lập; trưởng bộ phận thấy cả phòng Thu mua. Phiếu do đồng nghiệp khác lập, ngoài phạm vi của mình, sẽ luôn báo "Không tìm thấy" dù phiếu có tồn tại thật.

### Không chọn được Thanh toán cuối

Số tiền phải bằng đúng phần còn được lập của PMH. Kiểm tra các Phiếu chi trước đó và khoản hoàn ứng đã xác nhận.

### Phiếu đã lập nhưng chưa được tính là đã chi

Phiếu đang ở trạng thái **Chờ chi**. Chỉ khi bấm **Xác nhận đã chi**, hệ thống mới ghi nhận tiền đã thực sự xuất.

### Duyệt một phiếu rồi mà yêu cầu vẫn "Chờ duyệt"

Đúng, không phải lỗi. Yêu cầu tách thành nhiều phiếu; trạng thái lấy theo **phần chậm nhất**. Mở
chi tiết yêu cầu xem cột **Tình trạng** để biết dòng nào đang kẹt.

### Đơn đã duyệt nhưng không thấy ở màn Công nợ

Đúng. Hàng chưa về thì **chưa nợ ai**. Bấm *Đã nhận hàng* xong nó mới hiện.

### Không lập được Phiếu chi bằng tổng đơn

Nhà cung cấp giao thiếu. Trần lập phiếu bám **giá trị thực nhận**, không bám tổng đơn. Xem dòng
*"Thực nhận …"* ngay dưới Tổng PMH.

### Không lưu được Phiếu chi

Kiểm ba chỗ: **Hạn trả tiền** bỏ trống, ngày chứng từ/hoá đơn đặt ở **tương lai**, hoặc hạn trả đặt
**trước** ngày chứng từ.

### Không thấy nút Duyệt/Từ chối dù đang ở màn Kế toán → Đơn mua hàng

Tài khoản chỉ có quyền kế toán (`ke_toan:*`), chưa có quyền Thu mua (`thu_mua:approve`). Hai quyền này tách riêng — xem mục 4.1. Cấp thêm `thu_mua:approve` nếu muốn người này cũng duyệt được PMH.

### Không thấy màn Kế toán dù là kế toán

Chưa có vai nào được cấp quyền module kế toán. Quản trị viên phải tạo vai và tick quyền ở màn Phân
quyền — hệ **không** tạo sẵn vai "Kế toán".

### Mở lại kỳ công bị chặn dù kỳ lương chưa "Đã chốt"

Kiểm lại: nếu kỳ lương đã ở trạng thái **Đã chi**, việc chặn là đúng — tiền đã phát không được sửa công phía sau. Muốn sửa, Hủy đã chi rồi Mở lại kỳ lương trước, hoặc xử bằng truy lĩnh/khấu trừ kỳ sau.

## 6. Danh sách kiểm tra trước khi nghiệm thu

- Cây phòng ban/tổ đúng cơ cấu thực tế.
- Mỗi nhân viên thuộc đúng tổ và có ngày vào làm đúng.
- Mỗi nhân viên có mức lương riêng; bậc không tự thay tiền.
- Tăng lương tạo mốc ngày hiệu lực mới và xem lại được lịch sử cũ.
- Chuyển tổ/nâng bậc không làm thay đổi tiền ngoài ý muốn.
- Mức **Phụ cấp cơm / Phụ cấp ca của từng ca** (Chấm công → Ca làm việc) đã được doanh nghiệp xác nhận hoặc sửa lại — mặc định 25.000đ/50.000đ chỉ áp cho ca mới tạo.
- Ngưỡng công tối thiểu để hưởng phụ cấp ca/cơm (mặc định 0,5 công) đúng chính sách doanh nghiệp.
- Danh mục khoản thu nhập gắn đúng cờ Chịu thuế/Miễn thuế cho từng khoản (trang phục, tiền nhà, đi lại…).
- Tổ có bật "Làm khoán" đã được chủ động xác nhận chấp nhận mất tăng ca (vì tiền khoán hiện = 0).
- Nhà cung cấp có đủ bảy trường bắt buộc **và đã khai danh mục mặt hàng**.
- YCMH chỉ có số lượng, không có giá.
- PMH truy được về **đúng một** YCMH nguồn.
- Yêu cầu có hàng của hai nhà cung cấp thì ra **hai** phiếu.
- Thành tiền PMH tính đúng giảm giá và VAT.
- Ai duyệt PMH thì đã được cấp riêng quyền `thu_mua:approve`; ai lập Phiếu chi có quyền `ke_toan:create` — không phải cùng một quyền.
- Không thể chi vượt **giá trị thực nhận** của PMH.
- Phạm vi thấy/sửa phiếu mua hàng của từng vai trò (nhân viên/trưởng bộ phận/kế toán) đã cấp đúng.
- Màn Công nợ hiện `—` (không phải `0đ`) khi tải hỏng.
- Phiếu chi và PMH in được, không xuất hiện phần chữ ký thừa theo mẫu đã chốt.

---

### Đầu mối hỗ trợ

Quản trị viên hệ thống của doanh nghiệp. Khi báo lỗi, cung cấp mã chứng từ, ảnh màn hình, thời điểm thao tác và tên tài khoản để tra cứu nhanh.
