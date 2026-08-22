# CÔNG THỨC TÍNH LƯƠNG — NHÀ MÁY IN SAO VIỆT NHẬT

**Tài liệu nghiệp vụ nội bộ · Bản chuẩn đối chiếu với engine đang chạy**
Người soạn: Kế toán trưởng · Cập nhật theo code ngày 07/08/2026

> **Cách đọc tài liệu này.** Mọi neo `file:line` trong bài đều tính từ thư mục `backend/app/` (ví dụ `payroll_service.py:820` = `backend/app/services/payroll_service.py` dòng 798). Frontend ghi rõ đường dẫn đầy đủ.
>
> Tài liệu này mô tả **engine đang chạy**, không mô tả luật. Chỗ nào engine làm khác luật, tôi ghi thẳng ở **Phần 13**. Chỗ nào code chưa làm, tôi ghi là **CHƯA CÓ** — không tô hồng.
>
> Có **hai đường tính lương** trong hệ: nút **"Tính lại bảng lương"** (`generate` → `_compute`) và nút **"Sửa 1 ô"** (`update_line`). Hai đường phải ra cùng một số. Chỗ nào chúng đang lệch nhau, tôi liệt kê ở **Phần 14** — đó là **lỗi phải sửa**, khác hẳn Phần 13.

---

## MỤC LỤC

| Phần | Nội dung |
|---|---|
| 0 | Bảy nguyên tắc bất di bất dịch |
| 1 | Bản đồ một dòng lương — thứ tự máy chạy |
| 2 | CÔNG — công chuẩn, công thực, off1x, có đơn, phép |
| 3 | Mức nền tháng & hệ số thử việc |
| 4 | Lương theo công · Chuyên cần · Phụ cấp |
| 5 | Tăng ca · Ca đêm · Cơm ca |
| 6 | Khoán sản lượng |
| 7 | GROSS — liệt kê đầy đủ |
| 8 | BHXH · BHYT · BHTN · Đoàn phí |
| 9 | Thuế TNCN |
| 10 | Phạt kỷ luật & trần 30% Điều 102 |
| 11 | Tạm ứng · Lương đợt 1 · Khoản trừ danh mục · THỰC NHẬN |
| 12 | **Hai ví dụ số chạy trọn vẹn** |
| 13 | **Những chỗ engine làm KHÁC thông lệ — đừng sửa bừa** |
| 14 | Lỗi đã biết — PHẢI sửa (không phải chính sách) |
| 15 | Bảng tra tham số cấu hình |

---

# 0. BẢY NGUYÊN TẮC BẤT DI BẤT DỊCH

1. **Mẫu số luôn là CÔNG CHUẨN của tháng**, không bao giờ là công thực. Công chuẩn động theo lịch từng tháng — tháng 2 có thể 24, tháng khác 27.
2. **Làm dôi công không ra thêm tiền ở `lương theo công`.** Phần dôi chỉ được trả qua premium ngày lễ / ngày nghỉ tuần trong cụm tăng ca.
3. **Khoán là CỘNG THÊM**, không thay thế lương công (chủ chốt 22/07/2026).
4. **Mức đóng bảo hiểm bám `lương vị trí`**, không bám tổng mức nền, không prorate theo công.
5. **Tiền tăng ca + ca đêm + cơm ca miễn TNCN toàn bộ**, không trần.
6. **Trần khấu trừ 30% (Điều 102 BLLĐ) chỉ kẹp phạt kỷ luật + trừ lỗi khoán.** BHXH, thuế, đoàn phí, tạm ứng, khoản trừ danh mục **nằm ngoài trần**, trừ hết.
7. **Có hai sàn 0**: một ở gross, một ở thực nhận. Tiền thiếu **biến mất**, hệ thống **không ghi nợ**, **không chuyển kỳ sau**.

---

# 1. BẢN ĐỒ MỘT DÒNG LƯƠNG — THỨ TỰ MÁY CHẠY

Đường "Tính lại bảng lương": `PayrollService.generate` (`payroll_service.py:1119-1298`) → `_compute` (`:793-1113`).

| Bước | Việc | Neo |
|---|---|---|
| B0 | Tính **công chuẩn `std`** cho cả kỳ (lịch → `standard_cong_default` → 26). Ghi vào `payroll_periods.standard_cong`. Kỳ không còn DRAFT ⇒ ném `PayrollLocked` | `:1132-1149` |
| B1 | Nạp dữ liệu chung: `pay_on` = **ngày cuối tháng**, bảng công (snapshot nếu kỳ công đã chốt, ngược lại tính live), bảng ca, tạm ứng/lương đợt 1 đã duyệt, mức lương hiệu lực, khoán + trừ lỗi khoán, biểu thuế, bảng phạt trễ, tập tổ khoán | `:1151-1173` |
| B2 | Mỗi NV: resolve **trạng thái + bộ phận TẠI KỲ**; bỏ NV đã nghỉ việc không còn công/khoán/dòng; **giữ nguyên các ô HCNS gõ tay**; tính lại phạt trễ nếu chưa khoá tay | `:1180-1200` |
| B3 | Mức nền → `eff_monthly = monthly × hệ số thử việc`, `eff_vi_tri` | `:809-828` |
| B4 | `daily_rate = eff_monthly / std` → **lương theo công** (công LÀM lấp trần trước, công PHÉP lấy phần dư) | `:820-832` |
| B5 | **Chuyên cần** trừ dần | `:833-837` |
| B6 | **Phụ cấp** khai tay + thâm niên + khoản danh mục hồ sơ; tách riêng khoản phát sinh kỳ, khoản trừ, khoản miễn thuế | `:838-861` |
| B7 | **Tăng ca** + premium lễ/CN + tiền ngày off1x (= 0 nếu tổ khoán hoặc tắt tăng ca) | `:863-901` |
| B8 | `night_pay = 0` → **cơm ca + phụ cấp ca** theo ca thực làm → **premium ca đêm theo giờ** | `:902-947` |
| B9 | Thưởng chi tiết + phép năm + trả đồng phục + điều chỉnh lương → **`gross_pre`** | `:950-960` |
| B10 | Số ngày không lương → **BHXH** (4 nhánh) → **đoàn phí công đoàn** | `:962-1025` |
| B11 | Làm tròn `gross_pre`, `bhxh` → **TNCN** | `:1027-1040` |
| B12 | **Trần phạt 30%** → `gross = max(0, gross_pre − phạt hiệu lực)` | `:1042-1053` |
| B13 | Về `generate`: giữ TNCN gõ tay nếu có → **thực nhận** → ghi dòng lương → snapshot khoản danh mục | `:1235-1292` |

**Đường "Sửa 1 ô"** (`update_line`, `:1428-1560`) **KHÔNG chạy lại B3–B10**. Nó dựng lại `gross_pre` **từ các cột đã lưu trên dòng** (`:1508-1515`) rồi lặp B11–B13. Đây là nguồn gốc mọi lệch số ở Phần 14.

---

# 2. CÔNG

## 2.1. Công chuẩn tháng (`std`)

**Công thức**
```
std = số NGÀY LÀM VIỆC THỰC của tháng theo Lịch chung
    = đếm ngày d trong tháng có is_working_day(d) = ĐÚNG

is_working_day(d):
   d là ngày đặc biệt kind = 'work' (làm bù)      → ĐÚNG
   d là ngày đặc biệt kind = 'off' hoặc 'off1x'   → SAI
   còn lại                                         → theo cấu hình TUẦN LÀM VIỆC (T2..CN bật/tắt)

Chưa cấu hình lịch (trả 0/None) → std = payroll_params.standard_cong_default (mặc định 26)
Vẫn ≤ 0                        → std = 26,0 cứng trong code
```

**Lấy số ở đâu** — Bảng ngày đặc biệt (`special_days`) + `work_calendar_config` (cột T2..CN) · `payroll_params.standard_cong_default` (Numeric(6,2), mặc định cột DB = 26) · snapshot ghi vào `payroll_periods.standard_cong` và `payroll_lines.standard_cong`.

**Khi nào KHÔNG áp dụng** — Không có ngoại lệ. Tính **MỘT lần cho cả kỳ**, dùng chung cho mọi nhân viên. **Không** cá biệt hoá theo người, **không** trừ theo ngày vào/nghỉ việc giữa tháng. Chỉ ghi đè `period.standard_cong` khi kỳ còn DRAFT.

**Neo** — `payroll_service.py:1132-1139` (chọn std + 2 nấc fallback), `:1140-1149` · `attendance_service.py:1559-1564` · `calendar_service.py:108-116`, `:118-129`, `:131-137`.

**Bẫy**

| # | Bẫy | Hậu quả |
|---|---|---|
| 1 | Công chuẩn **ĐỘNG theo tháng** | Cùng một người, cùng số giờ tăng ca, hai tháng ra hai số tiền khác nhau — **không phải lỗi** |
| 2 | Ngày `off1x` **KHÔNG** được đếm vào công chuẩn | Mẫu số không tăng dù có người đi làm hôm đó |
| 3 | `std` lấy theo **Lịch chung**, không theo ca/bộ phận | Tổ chạy ca 3 vẫn dùng chung mẫu số |
| 4 | `float(standard_cong) or 1.0` (`:820`) | `std = 0` **âm thầm thành 1** ⇒ cả tháng lương nổ theo đơn giá 1 công = cả tháng lương |
| 5 | Ô "công chuẩn" **đã gỡ khỏi màn Cấu hình lương** (chỉ còn API `PUT` nhận) | Đây chỉ là lưới dự phòng, đừng đi tìm ô đó trên giao diện |

---

## 2.2. Công thực (`actual_cong`) — tử số của lương theo công

**Công thức**
```
actual_cong = Σ công NGÀY ĐI LÀM
            + Σ công NGÀY LỄ hưởng lương
            + Σ công NGÀY PHÉP có lương
            + Σ công HOÀN do phiếu giờ có tick "trừ phép"
            − Σ công ngày off1x

công 1 ngày đi làm = (số phút làm nằm trong khung ca) ÷ (số phút chuẩn của ca)
                     làm tròn 2 chữ số, TỐI ĐA 1,00
   · vào trễ ≤ dung sai ca ⇒ coi như đúng giờ
   · thiếu chấm RA ca chính ⇒ 0 công (ngày treo)

công ngày lễ  = 1,0   (0 nếu có đơn nghỉ KHÔNG lương phủ lên lễ)
công ngày phép = 1,0 nếu đơn có lương, 0 nếu không lương
```

**Lấy số ở đâu** — Lượt bấm vào/ra (`attendance_logs`) + `work_shifts` (giờ bắt đầu/kết thúc, dung sai, cờ qua đêm) · đơn nghỉ phép · phiếu đi muộn–về sớm · Lịch chung. **Nguồn đọc:** kỳ công đã CHỐT → snapshot `attendance_period_lines.total_cong`; chưa chốt → tính LIVE.

**Khi nào KHÔNG áp dụng** — NV không có ca nào và không phép/lễ ⇒ `total_cong = None` ⇒ Lương đọc thành **0,0 công**. Hệ thống **không** tự quy đổi lượt bấm thành nguyên công. NV nghỉ việc mà không có công/khoán/dòng lương thì bị bỏ khỏi bảng lương.

**Neo** — `payroll_service.py:1203` · `attendance_service.py:1518-1553` (snapshot vs live), `:1192`, `:1265`, `:1283`, `:1238`, `:1326`, `:141-144`.

**Bẫy**

1. `actual_cong` **ĐÃ GỒM** ngày lễ hưởng lương và ngày phép có lương — đừng cộng thêm lần nữa. Cũng vì thế hai loại này **không** bị đếm là "nghỉ không lương" ở luật BHXH 14 ngày.
2. `actual_cong` **CÓ THỂ > std** (đi làm CN/lễ). Phần dôi bị trần cắt ở bước tính tiền.
3. Công `off1x` **đã bị TRỪ** khỏi `actual_cong` nên không tự nhiên bằng tổng cột ngày trên lưới chấm công.
4. Chốt công rồi thì Lương đọc **SNAPSHOT** — sửa chấm công sau đó **không đổi số** cho tới khi mở lại kỳ công.

---

## 2.3. `plain_cong` — ngày nghỉ loại `off1x`

**Công thức**
```
Với mỗi ngày d thuộc nhóm off1x mà NV CÓ chấm công:
    plain_cong  += công(d)
    actual_cong −= công(d)        ← LOẠI KHỎI BASE ngay tại Chấm công

Sang Lương, tiền phần này KHÔNG đi qua lương-theo-công mà trả riêng, KHÔNG trần, trong cụm tăng ca:
    tiền_off1x = đơn_giá_ngày × plain_cong × 1,0     (hệ số 1× — KHÔNG premium)

Khi xét luật BHXH 14 ngày thì CỘNG TRẢ LẠI:
    ngày_không_lương = max(0, std − actual_cong − plain_cong)
```

**Lấy số ở đâu** — `special_days.kind = 'off1x'` · `attendance_period_lines.plain_cong` khi chốt công.

**Khi nào KHÔNG áp dụng** — Chỉ ngày `kind = 'off1x'`. Thứ tự nhánh là if/elif: **off1x xét TRƯỚC ngày lễ và ngày nghỉ tuần** ⇒ ngày off1x không bao giờ rơi vào nhóm lễ/nghỉ tuần. Ngày off1x **không** bị phạt đi trễ/về sớm tự động.

**Neo** — `attendance_service.py:1198-1202`, `:1063`, `:1068`, `:1214`, `:1255` · `payroll_service.py:895-900`, `:962-971` · `calendar_service.py:148-152`.

**Bẫy**

1. Vì bị loại khỏi `actual_cong` nên công off1x **không lấp trần** ⇒ người làm off1x được trả **trọn 1×** kể cả khi đã đủ công chuẩn. **Đây là chủ ý.**
2. Tiền off1x nằm **TRONG cột "tăng ca"** trên phiếu lương, không có cột riêng — kế toán nhìn cột tăng ca thấy tiền dù NV không tăng ca giờ nào.
3. **Tổ khoán (`has_piece_work`) hoặc tổ TẮT "tăng ca" ⇒ tiền off1x MẤT SẠCH** (`payroll_service.py:881-885`).

---

## 2.4. `excused_cong` — công thiếu nhưng CÓ ĐƠN (chỉ nuôi chuyên cần)

> **Bản này đã sửa theo đối chiếu code — bản trích ban đầu thiếu 3 điều kiện tiên quyết.**

**Công thức**
```
Ngày có phiếu đi muộn/về sớm ĐÃ DUYỆT (hl phút xin) mà KHÔNG tick "trừ phép":
    gap = max(0, 1 − công(d))       nếu hl ≥ số phút thiếu thật
        = hl / số phút cửa sổ ca     nếu ngược lại
    excused_cong += gap

excused_cong KHÔNG cộng vào actual_cong (KHÔNG ra tiền công) — chỉ vào tỷ lệ chuyên cần.
```

**Ba điều kiện tiên quyết — thiếu một là bằng 0:**

| # | Điều kiện | Neo |
|---|---|---|
| 1 | Ngày đó **PHẢI CÓ CHẤM CÔNG** và NV **PHẢI CÓ CA** hôm đó | `attendance_service.py:1148`, `:1170` |
| 2 | Ngày đó **KHÔNG** phải ngày lễ, **KHÔNG** off1x, **KHÔNG** có đơn phép nguyên ngày | `:1214` |
| 3 | Phiếu giờ trùng ngày đã có đơn phép nguyên ngày đã bị gỡ khỏi danh sách từ trước | `:1042-1045` |

**Hệ quả cho kế toán:** ngày **chỉ có phiếu giờ đã duyệt mà KHÔNG bấm vào/ra buổi nào** thì **không sinh `excused_cong`** — mất **cả tiền công LẪN chuyên cần**, dù đã xin phép. Đây là chỗ công nhân cãi nhau nhiều nhất.

**Khi nào KHÔNG áp dụng** — Phiếu **CÓ tick "trừ phép"** đi nhánh khác: công được **HOÀN** vào `actual_cong` + `paid_leave_cong`, **không** sinh `excused_cong` (tránh bù hai lần).

**Neo** — `attendance_service.py:1222-1246` · `payroll_service.py:833-837`, `:1220`.

**Bẫy** — Có đơn thì **GIỮ chuyên cần** nhưng **VẪN MẤT tiền công** phần vắng. Hai thứ tách nhau. `gap` bị kẹp theo công thiếu THẬT nên khai khống phút không đúc ra công ảo.

---

## 2.5. Công ngày phép có lương (`paid_leave_cong`)

**Công thức**
```
phép         = max(0, min(công phép đầu vào, actual_cong))
làm          = actual_cong − phép
công_làm_trả = min(làm, std)                          ← công LÀM lấp trần TRƯỚC
công_phép_trả= min(phép, max(0, std − công_làm_trả))  ← công PHÉP lấy phần DƯ

lương_ngày_phép = (lương_vị_trí_hiệu_lực / std) × công_phép_trả
```

**Lấy số ở đâu** — Số ngày phép nguyên ngày có lương + phần công hoàn lẻ do phiếu giờ trừ phép (0,5…) từ Chấm công · `lương_vị_trí_hiệu_lực` = lương vị trí × hệ số thử việc.

**Khi nào KHÔNG áp dụng** — **Ngày nghỉ phép năm CHỈ trả LƯƠNG VỊ TRÍ, KHÔNG có lương trách nhiệm** (chốt 27/07/2026). Hồ sơ cũ chỉ khai `base_amount` thì coi cả cục là lương vị trí, nếu không ngày phép ra 0 đồng.

**Neo** — `payroll_service.py:130-153` (`_luong_cong_split`), `:827-832`, `:1070-1071` · `attendance_service.py:1310`.

**Bẫy** — `lương_ngày_phép` là số **"TRONG ĐÓ"** của lương theo công. Phiếu lương hiện dòng riêng nhưng **TUYỆT ĐỐI không cộng lại vào gross**. Thứ tự lấp trần (làm trước, phép sau) là cố ý: người đi làm dôi công không bị trừ hai lần.

---

# 3. MỨC NỀN THÁNG & HỆ SỐ THỬ VIỆC

## 3.1. Mức nền tháng

**Công thức**
```
mức_nền = lương_vị_trí + lương_trách_nhiệm            (nguồn = 'employee')
        = base_amount    nếu cả hai ô trên = 0 và có base_amount   (fallback dữ liệu cũ)
        = 0                                            (chưa khai gì)

mức_nền_hiệu_lực     = mức_nền     × hệ_số_thử_việc
lương_vị_trí_hiệu_lực = (lương_vị_trí nếu nguồn='employee', ngược lại mức_nền) × hệ_số_thử_việc
```

**Lấy số ở đâu** — `employee_salaries.luong_vi_tri` / `.luong_trach_nhiem` / `.base_amount`. **Bản ghi hiệu lực = `effective_from` lớn nhất ≤ NGÀY CUỐI THÁNG**; hoà ngày thì `id` lớn hơn thắng.

**Khi nào KHÔNG áp dụng** — Không khai lương ⇒ mức nền = 0 ⇒ lương công = 0, **không báo lỗi**, dòng lương vẫn tạo. Nhánh bậc/quy tắc lương (`payroll_rules`) **ĐÃ BỎ** khỏi đường tính mức nền.

**Neo** — `payroll_service.py:618-631`, `:814-818`, `:827-828`, `:1154`, `:1161`.

**Bẫy**

1. **Tra mức lương theo NGÀY CUỐI THÁNG, không phải ngày 01.** Đổi lương giữa tháng thì **cả tháng ăn mức MỚI**, không chia đôi theo ngày hiệu lực.
2. Mức đóng BHXH luôn bám `lương_vị_trí`, **không** bám mức nền. Cột `employee_salaries.insurance_base` đã **dormant** — engine không đọc (`models/payroll.py:271`).

## 3.2. Hệ số thử việc

**Công thức**
```
hệ_số = payroll_params.probation_ratio   nếu trạng thái TẠI KỲ = 'thử việc'
      = 1,0                              ngược lại
```
Mặc định công ty: **0,80** (Điều 26 BLLĐ tối thiểu 85% — xem Phần 13).

**Áp vào ĐÚNG 2 số gốc:** `mức_nền_hiệu_lực` và `lương_vị_trí_hiệu_lực`.
⇒ lan xuống: lương theo công, lương ngày phép, đơn giá ngày, đơn giá giờ ⇒ tăng ca, premium lễ/CN, tiền off1x, premium ca đêm.

**KHÔNG áp vào:** chuyên cần · phụ cấp khác · phụ cấp thâm niên · khoán · cơm ca/phụ cấp ca · mọi khoản thưởng · khoản danh mục.

**Ngoài ra thử việc:** BHXH = 0 và đoàn phí = 0.

**Khi nào KHÔNG áp dụng** — Trạng thái lấy theo **LỊCH SỬ tại ngày cuối tháng**, không phải trạng thái hiện tại của hồ sơ. Tính lại kỳ cũ vẫn ra đúng số cũ.

**Neo** — `payroll_service.py:809-818`, `:827-828`, `:976-978`, `:1024-1025`, `:576-591`, `:1181` · `models/payroll.py:101-104`.

**Bẫy** — Thử việc **vẫn hưởng đủ 100%** chuyên cần, phụ cấp, cơm ca, thưởng. Chỉ phần lương theo công và tăng ca bị ×80%. **Không có khoản nào bị cấm hẳn** với thử việc trong engine.

---

# 4. LƯƠNG THEO CÔNG · CHUYÊN CẦN · PHỤ CẤP

## 4.1. Lương theo công

**Công thức**
```
đơn_giá_ngày = mức_nền_hiệu_lực / std

lương_theo_công = đơn_giá_ngày × công_làm_trả
                + (lương_vị_trí_hiệu_lực / std) × công_phép_trả

công_làm_trả = min(actual_cong − công_phép, std)
```

**Diễn giải đúng** (bản trích ban đầu nói thiếu — đây là bản đã sửa):

> Làm **ĐỦ hoặc DÔI** công ⇒ nhận **nguyên lương tháng**, **TRỪ phần ngày phép chỉ được tính theo LƯƠNG VỊ TRÍ**. Nghĩa là nếu có lương trách nhiệm > 0 và trong tháng có nghỉ phép, tổng lương công sẽ **THẤP HƠN** mức nền tháng.
> Làm **THIẾU** công ⇒ prorate theo tỷ lệ công thực / công chuẩn.

**Lấy số ở đâu** — Mức nền hiệu lực · `payroll_periods.standard_cong` · công thực + công phép từ Chấm công.

**Khi nào KHÔNG áp dụng** — Không có ngoại lệ. **Mẫu số LUÔN là công chuẩn**, không bao giờ chia cho công thực. Trần `std` áp cho **tổng** (công làm + công phép).

**Neo** — `payroll_service.py:820-832`, `:130-153`, `:1067`, `:1461-1479`.

**Bẫy**

1. **Dôi công KHÔNG ra thêm tiền ở đây.** Thưởng cho ngày lễ/CN đi bằng premium trong cụm tăng ca. Nếu tổ **TẮT tăng ca** thì đi làm lễ/CN chỉ được base 1× đã nằm trong lương công.
2. Tổng các cột đã làm tròn **không nhất thiết bằng gross** (gross làm tròn ở tổng). Lệch vài đồng là bình thường.
3. ⚠️ **Đường "Sửa 1 ô" với ô mức tháng gõ tay KHÔNG nhân hệ số thử việc** — xem Phần 14, lỗi #1.

---

## 4.2. Chuyên cần

**Công thức**
```
số_ngày_nghỉ = max(0, std − (actual_cong + excused_cong))
tỷ_lệ        = max(0, 1 − 0,5 × số_ngày_nghỉ)
chuyên_cần   = mức_chuyên_cần_của_NV × tỷ_lệ
```

**Bảng nấc (std = 26):**

| Công (actual + có đơn) | Số ngày nghỉ | Tỷ lệ | Ví dụ mức 300.000đ |
|---|---|---|---|
| 26,0 | 0 | 100% | 300.000 |
| 25,5 | 0,5 | 75% | 225.000 |
| 25,0 | 1,0 | 50% | 150.000 |
| 24,5 | 1,5 | 25% | 75.000 |
| ≤ 24,0 | ≥ 2,0 | 0% | 0 |

**Lấy số ở đâu** — `employee_salaries.chuyen_can` (đ/tháng — **NƠI DUY NHẤT khai tiền**) · Công tắc bật/tắt theo TỔ: bảng **`department_salary_components`** (`models/payroll.py:227`), cột `component_key = 'chuyen_can'` + `is_enabled`. Chưa khai dòng nào ⇒ **mặc định BẬT**.

> **Sửa so với bản trích:** bảng công tắc tên là `department_salary_components`, **KHÔNG** phải `payroll_dept_components`.

**Khi nào KHÔNG áp dụng** — Tổ TẮT chuyên cần ⇒ 0 đ dù NV có khai tiền. Mức tiền cấp TỔ và `payroll_params.chuyen_can_default` đã **dormant** — chưa khai ở hồ sơ NV = 0 đ. **Không** nhân hệ số thử việc.

**Neo** — `payroll_service.py:122-127`, `:833-837`, `:593-606`, `:303-308`, `:1073`.

**Bẫy**

1. **Bậc 0,5 ngày ⇒ mất 25%.** Nghỉ 2 ngày là **mất sạch**, không giảm tuyến tính.
2. Đi làm dôi công **không** được cộng thêm chuyên cần (trần tỷ lệ 1,0).
3. `excused_cong` được bù vào **tử số RIÊNG cho chuyên cần** ⇒ chuyên cần đủ mà tiền công vẫn thiếu.

---

## 4.3. Phụ cấp khai tay + khoản danh mục — trả PHẲNG

**Công thức**
```
thâm_niên  = employee_salaries.phu_cap_tham_nien
khoản_thu_hồ_sơ = Σ khoản danh mục gán ở HỒ SƠ NV có loại ≠ 'trừ'

phụ_cấp (cột allowance) = employee_salaries.allowance + thâm_niên + khoản_thu_hồ_sơ

khoản_thu_phát_sinh_kỳ  = Σ khoản danh mục PHÁT SINH riêng kỳ, loại ≠ 'trừ'
                          → CỘNG THẲNG vào gross, KHÔNG vào cột allowance

khoản_trừ (cả 2 nguồn)  = Σ khoản loại 'trừ'  → trừ ở THỰC NHẬN, không vào gross
```

**Lấy số ở đâu** — `employee_salaries.allowance`, `.phu_cap_tham_nien` · Mức tiền khoản danh mục **CHỈ có MỘT nơi: `employee_salary_components.amount`** gán trực tiếp cho từng NV.

> **Sửa so với bản trích:** **KHÔNG tồn tại "mức mặc định theo nhóm lương"**. Bảng danh mục `payroll_components` chỉ giữ mã/tên/loại/cờ chịu thuế/cờ vào gốc BH — **không có cột số tiền mặc định**. Docstring `_components_for` (`payroll_service.py:512`) viết "mặc định nhóm lương" là **chữ CŨ còn sót, đừng tin**.

**Khi nào KHÔNG áp dụng** — Dòng khoản có `amount` = 0 hoặc rỗng thì **bị bỏ qua** (`:523`). Khoản danh mục đã **ngừng áp dụng** (`is_active = false`) mà NV còn giữ thì **VẪN TRẢ**.

**CỘNG PHẲNG:** không prorate theo công, không nhân hệ số thử việc, không vào gốc tính tăng ca.

**Neo** — `payroll_service.py:838-861`, `:511-541`, `:1074`, `:1088`, `:1060` · `payroll_component_repo.py:101-105`.

**Bẫy**

1. `phu_cap_tham_nien` là số **"TRONG ĐÓ"** của `allowance` — phiếu hiện dòng riêng, **đừng cộng lại**.
2. **Hai danh sách khoản danh mục PHẢI để riêng**: khoản hồ sơ vào `allowance`, khoản phát sinh **KHÔNG** — gộp lại là "Tính lại rồi sửa một ô" **cộng đôi tiền**.
3. Cột `employee_salaries.phu_cap_ca` **đã NGƯNG dùng từ 03/08/2026** — khai bao nhiêu cũng không ra tiền.
4. **Phụ cấp TRÁCH NHIỆM không nằm ở đây** — nó là `lương_trách_nhiệm` trong mức nền nên **CÓ prorate theo công**.

---

## 4.4. Thưởng, phép năm, trả đồng phục, điều chỉnh lương

**Công thức**
```
thu_nhập_thêm = thưởng_5S + thưởng_doanh_số + thưởng_thành_tích
              + phép_năm + trả_đồng_phục + điều_chỉnh_lương
(cộng thẳng vào gross; điều_chỉnh_lương cộng ĐẠI SỐ nên có thể ÂM)
```

**Lấy số ở đâu** — 6 cột trên `payroll_lines`, HCNS nhập tay ở màn Sửa lương. `generate()` **GIỮ NGUYÊN** các ô này của dòng đã có (preserve, không tính lại).

**Ô nào còn sửa tay được?** (bản đã sửa — bản trích ban đầu nói sai)

> **6 cột THƯỞNG cũ** (`thuong_5s` · `thuong_doanh_so` · `thuong_thanh_tich` · `phep_nam` · `tra_dong_phuc` · `other_bonus`) **bị chặn ghi mới — CỐ Ý bỏ khỏi schema** từ 28/07/2026. Thưởng mới khai qua **KHOẢN DANH MỤC phát sinh**.
> **Ô THU duy nhất còn sửa tay trên bảng lương là `dieu_chinh_luong`.** Các ô còn lại `update_line` nhận được đều là **PHẠT** hoặc **thuế/mức tháng**: `vi_pham`, `pit`, `pit_manual`, `di_tre`, `di_tre_manual`, `dt_vuot_troi`, `phat_bien_ban`, `phat_5s_dong_phuc`, `monthly_override`, `note`.
> Cột thưởng cũ **vẫn được CỘNG** để kỳ đã chốt giữ nguyên số.

**Khi nào KHÔNG áp dụng** — Cộng PHẲNG: không prorate, không hệ số thử việc, không phụ thuộc bộ phận. **Tất cả là thu nhập CHỊU THUẾ.**

**Neo** — `payroll_service.py:950-952`, `:1091-1096`, `:1175-1178`, `:1192`, `:1428-1436`, `:1446-1451` · `schemas/payroll.py:476-493` · `models/payroll.py:432-438`.

**Bẫy**

1. `phep_nam` (cột **TAY**) **KHÁC HẲN** `lương_ngày_phép` (tự tính, ⊂ lương theo công). Trùng tên trong đầu kế toán là **cộng đôi tiền phép**.
2. `dieu_chinh_luong` âm **KHÔNG bị trần 30%** (nó nằm ở vế thu nhập, không phải vế phạt) — trừ bao nhiêu ra bấy nhiêu, chỉ chặn bởi sàn gross ≥ 0. **Số âm ở ô này còn GIẢM LUÔN thu nhập chịu thuế TNCN và NỚI trần phạt.**

---

## 4.5. Hoa hồng kinh doanh — **ĐÃ NỐI VÀO ENGINE** (21/08/2026)

Trước 21/08/2026 mục này ghi "engine không tính hoa hồng". **Nay đã tính.**

```
Hoa hồng(NV, kỳ) = Σ   hoá_đơn.amount_vnd × tỷ_lệ_trước_VAT(đơn) × orders.commission_pct(đơn)
                  hoá đơn `issued`, `invoice_date` trong kỳ, đơn có `sale_user_id` = NV

tỷ_lệ_trước_VAT(đơn) = Σ line_total  /  Σ line_total × (100 + vat_pct_estimate)/100
                     = 1.0 nếu đơn không có VAT hoặc chưa có số
```

**Hai điểm chủ chốt KHÁC spec `redesign-luong-kinh-doanh.md` §4.6** — cả hai đều đổi SỐ TIỀN:

| | Spec §4.6 | **Đang chạy** | Vì sao |
|---|---|---|---|
| Mốc sinh hoa hồng | lúc **thu được tiền** (Σ phiếu thu) | lúc **ra công nợ phải thu** (hoá đơn `issued`) | chủ chốt 21/08/2026: *"Ra công nợ phải thu là có hoa hồng"* |
| Gốc tính | dòng 149 ghi `Σ payments × %` (tức **có VAT**) | **trước VAT**, quy đổi theo tỷ lệ | VAT là tiền thu hộ nhà nước — trả hoa hồng trên đó là trả trên tiền không phải của công ty. (Spec tự mâu thuẫn: dòng 259 của nó ghi "mặc định trước VAT".) |

⚠️ **Hệ quả phải biết:** hoa hồng trả **TRƯỚC** khi tiền về. Khách nợ xấu thì tiền đã chi rồi, đòi lại phải qua kỳ lương sau. Muốn quay về mốc "thu được tiền" thì sửa **DUY NHẤT** `HoaHongService._moc_phat_sinh` — cả engine chỉ đọc qua đó.

**% lấy ở đâu.** `orders.commission_pct` được **CHỤP** vào đơn lúc **CHỐT đơn**, lấy từ `employee_salaries.commission_pct` đang hiệu lực của chính người sales. Chụp chứ không đọc-sống: đổi % cho người ta từ tháng sau **KHÔNG** được sửa ngược hoa hồng đơn đã chốt tháng trước.

⚠️ `orders.commission_pct` **không phơi ra API lẫn giao diện** — chỉ hệ thống ghi. Cố ý (chủ chốt 21/08/2026): cho sale gõ % trên chính đơn mình bán là để người ta **tự viết phiếu lương của mình**. % chỉ khai được ở **hồ sơ lương**, tức do nhân sự đặt chứ không phải người hưởng đặt. Hệ quả: đơn chốt xong là % **đóng băng vĩnh viễn**, sai thì bù bằng khoản *"Thu nhập khác"*, không nắn ngược được.

**Tiền hiện ở đâu.** Là **khoản danh mục** mã `hoa_hong_kd`, nguồn `auto`, **KHÔNG** phải một cột mới trên `payroll_lines`. Đi qua danh mục để cờ *"Chịu thuế"* là quy tắc khai được — cột kiểu cũ (`thuong_doanh_so`) đã bị chặn ghi mới từ 28/07/2026 đúng vì lý do đó. Mặc định `is_taxable=true`, `in_insurance_base=false`.

**Nguồn `auto` — nguồn khoản THỨ BA**, không dùng lại hai nguồn cũ:

| Nguồn | Khi "Tính lại" | Vào `allowance`? | Vì sao hoa hồng không dùng được |
|---|---|---|---|
| `employee` | bị ghi đè | **có** | vào `allowance` là sai cột, và nguồn của nó là hồ sơ NV chứ không phải kỳ |
| `line` | **giữ nguyên** | không | sai hẳn: số hoa hồng phải chạy theo hoá đơn mới phát sinh |
| **`auto`** | **xoá sạch rồi ghi lại** | không | đúng cả hai vế |

⚠️ Lượt xoá-ghi-lại **CHỈ** được đụng `source='auto'`. Quét lố sang `line` là xoá mất thưởng nóng HCNS thêm tay; sang `employee` là mất khoản hồ sơ — cả hai đều mất tiền của người lao động mà không một thông báo nào.

**Không gõ tay được.** Backend chặn cả sửa lẫn gỡ dòng `auto` (câu báo chỉ sang đơn hàng, không chỉ sang "Lương nhân viên" — hoa hồng không nằm ở đó). Giao diện để dòng này ở dạng chỉ đọc kèm nhãn *"Hệ tự tính"*. Cho sửa tay thì lần "Tính lại" sau xoá sạch âm thầm; giữ số tay lại thì hoa hồng ngừng chạy theo hoá đơn mới — sai kiểu ngược lại.

**Cột "Thưởng"** của bảng lương + file xuất cộng `source ∈ {line, auto}`. Bỏ `auto` ra là tiền nằm trong cột "Tổng" mà không cột nào giải thích được.

**Neo** — `services/hoa_hong_service.py` (toàn bộ: `_moc_phat_sinh:49` · `_ty_le_truoc_vat:67` · `hoa_hong_ky:85`) · `payroll_service.py:566` (`_hoa_hong_rows`), `:1367` (gọi trong vòng `generate`), `:1449` (ghi snapshot) · `order_service.py:112` (`_pct_hoa_hong_cua_sale`), `:672` (chụp lúc chốt) · `models/order.py:148` · migration `0227_hoa_hong_kinh_doanh`.

**Test canh** — `tests/test_hoa_hong_kinh_doanh.py` (22 test: công thức, hoá đơn từng phần, hoá đơn huỷ/ngoài kỳ, đơn người khác, % âm, chống cộng đôi khi tính lại, không nuốt thưởng nóng, chặn gõ tay, file xuất) · `tests/test_hoa_hong_sale.py` (ô khai % và mốc hiệu lực).

---

# 5. TĂNG CA · CA ĐÊM · CƠM CA

## 5.1. Đơn giá GIỜ — gốc nhân mọi hệ số

**Công thức**
```
lương_vị_trí_hiệu_lực = lương_vị_trí × hệ_số_thử_việc
đơn_giá_ngày_OT       = lương_vị_trí_hiệu_lực ÷ std
đơn_giá_giờ           = đơn_giá_ngày_OT ÷ standard_hours_per_day     (mặc định 8)
```

**Guard** (bản đã sửa — bản trích ban đầu **SAI**):

> `std = 0` → **ép thành 1,0** (`payroll_service.py:820`).
> `standard_hours_per_day = 0` hoặc chưa khai → **ép thành 8** (`payroll_service.py:873`, toán tử `or 8`). **Đơn giá giờ KHÔNG BAO GIỜ bằng 0 vì lý do này** — nhánh `else 0.0` ở `:874` là code chết. API cũng chặn không cho khai ≤ 0 (`schemas/payroll.py:28`).

**Khi nào KHÔNG áp dụng** — Áp cho **MỌI** khoản tăng ca + ca đêm. Mẫu số là **công CHUẨN của kỳ**, không phải công thực làm.

**Neo** — `payroll_service.py:817-821`, `:873-874`, `:1132-1139`.

**Bẫy**

1. ⚠️ **ĐỔI 12/08/2026 — gốc tính OT nay CHỈ là LƯƠNG VỊ TRÍ.** Trước đó là `vị trí + trách nhiệm`. Chủ chốt: *"tiền tăng ca tính trên lương cơ bản thôi, không có tiền trách nhiệm"*, và xác nhận **premium ca đêm + premium làm ngày nghỉ/lễ giảm CẢ** (ba khoản dùng chung đơn giá). Vẫn KHÔNG gồm phụ cấp / chuyên cần / cơm ca. **`luong_cong` KHÔNG đổi** — lương theo công vẫn ăn mức nền đầy đủ. Riêng ngày `off1x` cũng giữ mức nền: nó là lương CHÍNH của ngày đó, không phải premium.
2. Thử việc bị nhân 0,8 vào **cả đơn giá tăng ca** — tăng ca của thử việc rẻ hơn 20%.
3. `std` động theo tháng ⇒ tháng ít ngày làm việc thì **đơn giá giờ CAO hơn**. Cùng người, cùng số giờ OT, hai tháng ra hai số — **không phải lỗi**.
4. Đường "Tính lại" tính lại `std` mỗi lần bấm rồi đồng bộ ngược vào kỳ; đường "Sửa 1 ô" đọc `payroll_lines.standard_cong` đã lưu (`:1466`).

---

## 5.2. Bảng hệ số tăng ca / làm ngày nghỉ — ĐẦY ĐỦ

| Tham số | Mặc định | Áp cho | Khai ở |
|---|---|---|---|
| `ot_multiplier` | **1,5** | Giờ TĂNG CA ngày thường | Cấu hình lương (1 ≤ x ≤ 5) |
| `ot_multiplier_restday` | **2,0** | Giờ TĂNG CA ngày nghỉ hàng tuần | Cấu hình lương |
| `ot_multiplier_holiday` | **3,0** | Giờ TĂNG CA ngày lễ | Cấu hình lương |
| `restday_work_multiplier` | **2,0** | LÀM nguyên công ngày nghỉ tuần — **chỉ trả phần chênh (2−1) = 1,0×**; cộng 1× gốc trong `luong_cong` ⇒ **tổng 2×** | Cấu hình lương |
| `holiday_work_multiplier` | **3,0** | LÀM nguyên công ngày lễ — trả **TRỌN 3,0×** (⚠️ KHÔNG trừ 1, khác ngày nghỉ tuần — sửa 17/08/2026); cộng 1× tiền ngày lễ Đ112 trong `luong_cong` ⇒ **tổng 4×** | Cấu hình lương |
| — (ngày `off1x`) | **1,0** | Làm ngày off1x — trả **trọn 1×, KHÔNG trần, KHÔNG premium** | Cứng trong code |
| `night_multiplier` (**per-CA**) | **1,3** | Giờ đêm 22h–06h **TRONG ca**, chỉ ca qua đêm — **chỉ trả phần chênh 0,3×** | Danh mục Ca (`work_shifts`) |
| `night_pct` | **0,30** | Phần đêm của giờ **TĂNG CA** ban đêm | Cấu hình lương |
| `ot_night_extra_pct` | **0,20** | Nhân với **hệ số LÀM loại ngày** cho tăng ca đêm | Cấu hình lương |
| `standard_hours_per_day` | **8** | Mẫu số ra đơn giá giờ | Cấu hình lương (> 0) |

**Tổng hệ số cho 1 GIỜ TĂNG CA BAN ĐÊM (cấu hình mặc định):**

| Loại ngày | Vế tăng ca (cột "Tăng ca") | Vế đêm (cột "Premium ca đêm") | **TỔNG** |
|---|---|---|---|
| Ngày thường | 1,5 | 0,3 + 0,2×1,0 = 0,5 | **2,0 → 200%** |
| Ngày nghỉ tuần | 2,0 | 0,3 + 0,2×2,0 = 0,7 | **2,7 → 270%** |
| Ngày lễ | 3,0 | 0,3 + 0,2×3,0 = 0,9 | **3,9 → 390%** |

---

## 5.3. Tiền tăng ca + premium ngày nghỉ/lễ (cột `ot_pay`)

**Công thức**
```
giờ_OT_thường = max(0, phút_OT_TỔNG − phút_OT_lễ − phút_OT_nghỉ_tuần) ÷ 60

ot_pay = đơn_giá_giờ × ( giờ_OT_thường     × 1,5
                       + phút_OT_nghỉ_tuần/60 × 2,0
                       + phút_OT_lễ/60        × 3,0 )
       + đơn_giá_ngày × ( công_lễ       × max(0, 3,0 − 1)
                        + công_nghỉ_tuần × max(0, 2,0 − 1)
                        + công_off1x    × 1,0 )
```

> **Sửa so với bản trích:** (a) `phút_OT` lưu trên bảng công là **TỔNG đã gồm cả lễ + CN + đêm**, phải **TRỪ NGƯỢC** mới ra giờ OT thường — ai tưởng nó là OT thường sẽ tính **dư tiền OT lễ/CN một lần nữa**; (b) premium bị **kẹp sàn 0**: phải viết `max(0, hệ số − 1)`, không phải `(hệ số − 1)`. Khai hệ số < 1 ở Cấu hình lương thì code cho 0, công thức sai sẽ cho số **ÂM ăn bớt lương**.

**Lấy số ở đâu** — Phút OT / phút OT lễ / phút OT nghỉ tuần / công lễ / công nghỉ tuần / công off1x: từ `attendance_period_lines` (snapshot khi kỳ công đã chốt) hoặc tính LIVE.

**Khi nào KHÔNG áp dụng — QUAN TRỌNG**
```
ot_pay = 0 (bỏ TOÀN BỘ khối trên, KỂ CẢ premium lễ/CN và tiền ngày off1x) khi:
    departments.has_piece_work = TRUE  (tổ khoán)
  HOẶC bộ phận TẮT khoản 'tang_ca' ở Cấu hình lương
```
`payroll_service.py:881-885`.

**Neo** — `payroll_service.py:875-901`.

**Bẫy**

1. ✅ **HAI BẢN VÁ 17/08/2026 — đọc kỹ, hai loại ngày nay dùng HAI công thức KHÁC NHAU, cố ý.**
   **(a) mg 0204 — công lễ/CN KHÔNG còn đi qua trần** `min(công làm, công chuẩn)` (`special_cong` trong `_luong_cong_split`). Trước đó ai đã đủ công chuẩn rồi mới làm thêm thì phần gốc 1× bị trần nuốt.
   **(b) ngày lễ ăn TRỌN hệ số**, nghỉ tuần vẫn ăn `hệ số − 1`:

   | Loại ngày | Gốc trong `luong_cong` | Premium ở `ot_pay` | Tổng | Căn cứ |
   |---|---|---|---|---|
   | Nghỉ tuần (CN) | 1× | `(2 − 1)` = 1× | **2×** | Đ98.1.b — nghỉ CN ở nhà KHÔNG có lương, nên 1× gốc là tiền trả cho việc ĐI LÀM |
   | Ngày lễ | 1× | **`3` trọn** = 3× | **4×** | Đ98.1.c *"ít nhất 300% **chưa kể** tiền lương ngày lễ"* — 1× gốc chính là tiền ngày lễ Đ112, người đó hưởng dù nghỉ ở nhà |

   ⚠️ Cho ngày lễ ăn `hệ số − 1` là trả **THIẾU 1×**; cho nghỉ tuần ăn trọn hệ số là trả **THỪA 1×**. **ĐỪNG "dọn" cho hai dòng giống nhau.**
   Phần gốc ăn đơn giá **MỨC NỀN**, premium ăn đơn giá **lương vị trí** (chốt 12/08/2026) — hai đơn giá khác nhau, đừng gộp. Test canh: `test_cong_le_cn_khong_bi_tran_cong_nuot_goc` (5 case, có cả đối chứng CN).
2. **Tăng ca rơi vào ngày off1x tính hệ số NGÀY THƯỜNG 1,5**, không phải 2,0/3,0.
3. `ot_pay` tắt nhưng **premium ca đêm VẪN CHẠY** — tổ khoán làm đêm vẫn có tiền đêm (số lẻ vô nghĩa 0,5×).

---

## 5.4. Giờ tăng ca lấy từ chấm công — vai trò của PHIẾU

**Công thức**
```
Ghép phiên bấm trong NGÀY CÔNG:
   phiên 0        = CA CHÍNH  (giờ vào đầu tiên, giờ ra ca chính) → tính CÔNG
   phiên 1 trở đi = TĂNG CA                                        → tính OT

giờ_bắt_đầu_OT = giờ VÀO của phiên 1
giờ_kết_thúc_OT = giờ RA của phiên CUỐI          ← KHÔNG phải phiên 1

OT_từ  = max(giờ_bắt_đầu_OT, phiếu.từ_phút)
OT_đến = min(giờ_kết_thúc_OT, phiếu.đến_phút)
phút_OT(ngày) = max(0, OT_đến − OT_từ)

Không có phiếu duyệt      ⇒ cửa sổ = (0,0) ⇒ phút_OT = 0
Thiếu cặp chấm phiên TC   ⇒ phút_OT = 0
```

> **Sửa so với bản trích:** giờ kết thúc OT là **giờ RA của phiên CUỐI** (`sessions[-1][1]`), không phải phiên 1. **Hệ quả tiền bạc:** ai bấm ra–vào từ 3 lần trở lên trong buổi tăng ca thì **khe nghỉ giữa các phiên tăng ca VẪN được tính tiền**. Chỉ khe giữa "ra ca chính" và "vào tăng ca" là không tính.

**Cửa gác lúc BẤM MÁY** (bản đã sửa):

> Sau khi đã ra ca chính, chấm vào lại **khi VẪN CÒN TRONG khung giờ ca** thì **KHÔNG cần phiếu**. **Chỉ khi đã QUÁ giờ tan ca** mới bắt buộc có phiếu duyệt phủ giờ đó, và còn được nới thêm `CHECK_OUT_GRACE_HOURS` (`attendance_service.py:574`, `:581`).
> Đây chỉ là cửa gác lúc bấm máy — **tiền tăng ca vẫn luôn bị kẹp bởi phiếu** (`:187-189`).

**Ràng buộc phiếu tăng ca** — ba luật, kiểm ở `OvertimeService._validate_window` (dùng chung TẠO + SỬA):
1. **Độ dài một phiếu** ≤ `payroll_params.ot_max_minutes_per_day` (mặc định 720 = 12h, Đ107.1). Trước 17/08/2026 viết cứng, nay khai được.
2. **Tối đa 1 phiếu còn hiệu lực / ngày** · `đến_phút ≤ 2880` (phủ được ca đêm sang hôm sau).
3. ✅ **TRẦN THÁNG (mới 17/08/2026, mg 0206)** — Σ phút phiếu **chờ duyệt + đã duyệt** trong tháng ≤ `payroll_params.ot_max_minutes_per_month`. **CHẶN CỨNG, KHÔNG có đường vượt** (chủ chốt). `0` = TẮT và là **mặc định** ⇒ deploy không chặn ai; chủ bật bằng cách gõ 2400 (40h) ở Cấu hình lương.
   - Phiếu **chờ duyệt CŨNG chiếm chỗ** — không thế thì gửi 10 phiếu vào 10 ngày rồi duyệt lần lượt là qua trần sạch. Từ chối/hủy **trả chỗ ngay**, không job nền, không bảng sổ cái.
   - Đếm theo **PHIẾU** (đã cấp phép), không phải giờ đã bấm máy. Giờ thực **luôn ≤** giờ phiếu vì `compute_day_cong` lấy GIAO của phiên chấm với cửa sổ phiếu ⇒ chặn theo phiếu sai về phía AN TOÀN.
   - **KHÔNG có trần theo NĂM** (200/300h Đ107) — chủ bỏ 17/08/2026. Ghi ở Phần "việc không làm".
   - Số dư đọc qua `GET /api/overtime/tran-thang?employee_id&year&month`. Test: `test_overtime_api.py::test_tran_thang_*` (4 bài).

**Khi nào KHÔNG áp dụng** — Không có phiếu ⇒ **VẪN đủ công ca chính**, chỉ **không ra tiền tăng ca**.

**Neo** — `attendance_service.py:176-189`, `:1047-1056`, `:1156-1159` · `overtime_service.py:4-6`, `:109-116`.

**Bẫy**

1. **GIAO HAI CHIỀU**: về sớm hơn phiếu ⇒ trả theo THỰC; làm quá phiếu ⇒ **KẸP TRẦN theo phiếu**. Giờ TC nằm **ngoài** khung phiếu = **0đ** dù có bấm máy.
2. **BẮT BUỘC 2 CẶP bấm**: ra ca chính rồi vào lại. Ai ở lại làm tiếp mà **không chấm ra ca chính** thì phút OT = 0 — **mất trắng tiền tăng ca**, bảng công chỉ hiện "ngày treo".
3. `phút_OT_thô` (độ dài phiên TC thô) **có** tính nhưng **không ra tiền** — chỉ để đối chiếu duyệt vs thực.

---

## 5.5. `night_pay` — ĐÃ NGƯNG, luôn = 0

```
night_pay = 0,0   (hằng số, không còn công thức)
```

Trước 03/08/2026 = `employee_salaries.phu_cap_ca` (số phẳng gõ tay ở hồ sơ lương). **Đường đó đã TẮT.** Cột `payroll_lines.night_pay` giữ lại vì kỳ lương CŨ đã chốt còn số trong đó, và số cũ **vẫn được miễn thuế**.

**Neo** — `payroll_service.py:902-906` · `models/payroll.py:417-421`.

**ĐỪNG NHẦM hai cột:**

| Cột | Là gì | Trạng thái |
|---|---|---|
| `night_pay` | Phụ cấp ca **KHAI TAY per-người** (số phẳng/tháng) | **ĐÃ CHẾT = 0** — thay bằng cơm ca + phụ cấp ca theo CA THỰC LÀM |
| `night_premium_pay` | Tiền ca đêm **TỰ TÍNH THEO GIỜ** từ chấm công | **ĐANG SỐNG** |

**Bật lại `night_pay` mà không tắt khối cơm/phụ cấp ca = TRẢ TIỀN HAI LẦN.**

---

## 5.6. Phụ cấp CƠM CA + PHỤ CẤP CA (theo ca thực làm)

**Công thức**
```
Với mỗi CA c mà NV có đi làm:
   số_ngày(c) = đếm số ngày làm ca c có công(ngày) ≥ phu_cap_ca_min_cong   (mặc định 0,5)

tiền_cơm_ca   = Σ_c  work_shifts.meal_allowance(c)  × số_ngày(c)      (mặc định 25.000đ/ngày)
tiền_phụ_cấp_ca = Σ_c work_shifts.shift_allowance(c) × số_ngày(c)      (mặc định 50.000đ/ngày)
```

**Hưởng TRỌN suất hoặc KHÔNG** — cố ý không nhân theo tỷ lệ công.

**Lấy số ở đâu** — Danh sách {ca → công từng ngày} từ Chấm công (đóng băng ở `attendance_period_lines.ca_lam_json` khi chốt công) · `work_shifts.meal_allowance` / `.shift_allowance` · `payroll_params.phu_cap_ca_min_cong`.

**Khi nào KHÔNG áp dụng** — Chỉ đếm ngày **CÓ ĐI LÀM**. Nghỉ phép / nghỉ lễ **không có suất**. Ca đã xoá khỏi danh mục → bỏ qua, không đoán mức. **KHÔNG** bị tắt bởi cờ tổ khoán, **KHÔNG** bị tắt bởi cờ tăng ca.

**Neo** — `payroll_service.py:908-934`, `:1083-1084` · `attendance_service.py:1286-1299`.

**Bẫy**

1. **ALL-OR-NOTHING**: đi muộn 15 phút (công 0,97) vẫn ăn **TRỌN 25.000đ**, không ra 24.250đ.
2. Tên là "phụ cấp ca" nhưng áp cho **MỌI ca** (ngày lẫn đêm), không riêng ca đêm.
3. **MIỄN TNCN TOÀN BỘ, KHÔNG áp trần 730.000đ/tháng** (chốt 04/08/2026 — xem Phần 13).
4. Nếu chủ khai **ngưỡng = 0** thì ngày treo (công 0) **vẫn được suất**.
5. Đường phụ cấp ca **per-người** (ô gõ tay ở hồ sơ lương) đã TẮT cùng lượt bật khối này. Cột cũ vẫn còn trong DB nên nhìn hồ sơ vẫn thấy số — **đừng bật lại**.

---

## 5.7. Premium CA ĐÊM theo giờ (`night_premium_pay`) — hai phần

**Công thức**
```
night_premium_pay = (A) đơn_giá_giờ × phút_đêm_có_trọng_số ÷ 60
                  + (B) đơn_giá_giờ × [ giờ_OT_đêm_thường     × (0,30 + 0,20 × 1,0)
                                      + giờ_OT_đêm_nghỉ_tuần × (0,30 + 0,20 × 2,0)
                                      + giờ_OT_đêm_lễ        × (0,30 + 0,20 × 3,0) ]

Tại tầng Chấm công:
  phút_đêm_có_trọng_số = Σ_ngày [ phút đêm 22h–06h TRONG ca × max(0, night_multiplier − 1) ]
  ⚠️ CHỈ cộng cho ca có is_overnight = TRUE
  cửa sổ đêm = 22:00–06:00, lặp theo trục tuyến tính (k = −1, 0, 1)
```

> **Sửa so với bản trích:** phần (A) **CHỈ tính cho ca qua đêm** (`is_overnight = TRUE`), và trọng số là **`max(0, night_multiplier − 1)`**, không phải chính `night_multiplier`. Ca NGÀY dù có giờ rơi vào 22h–06h thì **phần (A) = 0**. Phần (B) — tăng ca đêm — vẫn tính cho **MỌI ca**.

**Lấy số ở đâu** — `work_shifts.night_multiplier` (per-CA, mặc định 1,3) · `payroll_params.night_pct` (0,30) · `payroll_params.ot_night_extra_pct` (0,20) · hệ số nhân với `ot_night_extra_pct` là **`restday_work_multiplier` / `holiday_work_multiplier`** (hệ số LÀM ngày nghỉ), **KHÔNG** phải `ot_multiplier_restday/holiday`.

**Khi nào KHÔNG áp dụng** — Cả hai phần **KHÔNG** bị tắt bởi cờ tổ khoán, **KHÔNG** bị tắt bởi cờ tăng ca của bộ phận.

**Neo** — `payroll_service.py:936-947` · `attendance_service.py:1247-1258`, `:203-217`.

**Bẫy**

1. `phút_đêm_có_trọng_số` **KHÔNG phải số phút đêm thô** — nó **ĐÃ nhân (hệ số − 1)** ở tầng Chấm công. Engine chỉ nhân đơn giá giờ. Ai đọc tên tưởng là phút rồi nhân hệ số lần nữa là **TRẢ GẤP ĐÔI**.
   *Ví dụ:* 8h đêm, ca hệ số 1,3 → 480 × 0,3 = **144 "phút"** → đơn giá 125.000đ/h × 144/60 = **300.000đ**.
2. Ca đêm dùng `night_multiplier` **per-CA** (1,3); tăng ca đêm dùng `night_pct` (0,3) ở tham số chung — **HAI tham số khác nhau**, sửa một cái không đổi cái kia.
3. Phần (B) dùng `restday_work_multiplier` / `holiday_work_multiplier`, **không** dùng `ot_multiplier_restday/holiday`. Mặc định trùng số 2/3 nên không lộ; chủ chỉnh lệch nhau là ra số khác ngay.
4. Tiền một giờ OT đêm nằm ở **HAI DÒNG phiếu lương khác nhau**. Kế toán soi riêng cột "Tăng ca" sẽ thấy thiếu 25% và tưởng engine tính sai.

---

## 5.8. Ca qua NỬA ĐÊM — trục thời gian & ngày công

**Công thức**
```
mốc_kết_thúc = giờ_kết_thúc_ca + 1440 phút   nếu ca qua đêm; ngược lại = giờ_kết_thúc_ca
cửa_sổ_ca    = mốc_kết_thúc − giờ_bắt_đầu_ca

Ánh xạ mọi mốc lên trục tuyến tính: lin(m) = m + 1440 × (số ngày lệch so với NGÀY CÔNG)

NGÀY CÔNG của một lượt bấm (giờ VN):
   ca đêm VÀ (giờ bấm ≤ giờ kết thúc ca) → ngày lịch − 1
   ngược lại                              → ngày lịch

công = min(1,00 ; làm tròn 2 chữ số của (số phút làm ÷ cửa_sổ_ca))
```

**Neo** — `attendance_service.py:155-168`, `:227-233`, `:208-212`, `:345-354`.

**Bẫy**

1. **NGÀY CÔNG của ca đêm = ngày VÀO ca.** Toàn bộ phân loại lễ / nghỉ tuần / off1x bám ngày này ⇒ **ca đêm 30/04 kéo sang 01/05 tính hệ số theo 30/04**. OT của ca đêm thứ Bảy kéo sang rạng sáng Chủ nhật vẫn tính hệ số **NGÀY THƯỜNG**.
2. Hàm tính giờ đêm lặp k ∈ {−1, 0, 1} — **MỘT công thức cho mọi ca**. Nhánh "trong ngày" cũ tính **HỤT** phần 00:00–06:00 hôm sau; **đừng viết lại nhánh đó**.
3. Giờ đêm **TRONG ca** bị kẹp trần ở mốc kết thúc ca để loại phần OT ra — nếu không thì giờ OT đêm được tính **hai lần**.
4. Cửa sổ ca ≤ 0 ⇒ trả 0 hết + đánh dấu ngày lỗi.

---

# 6. KHOÁN SẢN LƯỢNG

## 6.1. Trạng thái thật — nói thẳng

> **Cột `khoan` trên bảng lương hiện LUÔN = 0 cho MỌI nhân viên.**
> Lý do **KHÔNG phải "chờ Lệnh sản xuất"**, mà là **nguồn sản lượng thật đã bị GỠ khỏi hệ**:
>
> - `deps.py:441-445` — khởi tạo `PieceWorkService(piece)` với tham số nguồn sản lượng **bỏ trống** ⇒ = None. Comment ngay tại đó: *"Nguồn sản lượng đã gỡ → khoán-theo-sản-lượng bỏ."*
> - `khoan_map` và `defect_map` mở đầu bằng `if nguồn is None: return {}` (`piece_work_service.py:241-242`, `:254-255`) ⇒ **trả rỗng, KHÔNG raise, KHÔNG log**.
> - Bảng/repo `production_outputs` **không còn model lẫn router**. Chỉ còn dấu vết ở `db_migrations.py:1853-1891` và `backend/scripts/seed_review_luong.py` (script này import module không tồn tại ⇒ **chạy là ImportError**).
> - `update_line` **không nhận tham số `khoan`** ⇒ HCNS cũng **không gõ tay được**.

**Cái đang chờ Lệnh SX là phần KHÁC**: tiền khoán **DỰ KIẾN** ở bước lệnh đã chạy và ra số thật, nhưng đó là **số kế hoạch, không chảy sang bảng lương**.

## 6.2. Đơn giá khoán — nơi khai + luật khớp

**Công thức** (bản đã sửa — bản trích ban đầu **SAI**, thiếu một lớp lọc)
```
Lớp 1 — theo TỔ:
   đầu_việc_khớp(tổ) = { r ∈ piece_rates | r.is_active AND r.department_id = tổ }

Lớp 2 — theo CÔNG ĐOẠN (whitelist):
   đầu_việc_chọn_được(bước lệnh)
     = { r ∈ đầu_việc_khớp | r.id ∈ danh sách liên kết `cong_doan_dau_viec` của công đoạn đó }

Tự điền khi lập lệnh:
   có ĐÚNG MỘT dòng liên kết is_default = true   → lấy dòng đó
   ngược lại nếu chỉ có 1 đầu việc khớp          → lấy nó
   còn lại                                        → để trống, bắt người chọn
```

> **Luật khớp theo CÔNG ĐOẠN KHÔNG bị gỡ — nó chỉ CHUYỂN CHỖ**: từ cột chết `piece_rates.cong_doan` sang bảng liên kết **`cong_doan_dau_viec`** (`models/cong_doan.py:146-202`), kèm năng suất + số người + cờ mặc định.
> **Hệ quả tiền bạc:** công đoạn **CHƯA khai dòng định mức nào** ⇒ danh sách rỗng ⇒ **bước KHÔNG chọn được đầu việc nào** (khoán dự kiến = 0), dù tổ khai đầy bảng giá. Ghi đè bằng API cũng bị chặn (`lsx_service.py:2126-2127`).
> Comment ở `lsx_service.py:1709` ("= mọi đơn giá của TỔ") là **comment CŨ, đừng tin**.

**Neo** — `models/piece_work.py:42-64` · `piece_work_service.py:31-45` · `lsx_service.py:612-616`, `:623-629`, `:2126-2127`.

**Bẫy**

1. Cột `piece_rates.cong_doan` là **CỘT CHẾT** — không đọc ở đâu nữa nhưng vẫn còn trong DB.
2. `unit` lưu **CHỮ hiển thị** ('m²' chứ không phải 'm2'); người dùng gõ đơn vị ngoài danh sách gợi ý vẫn lưu ⇒ hai dòng cùng nghĩa có thể khác chuỗi.
3. `department_id` cho phép rỗng: đơn giá cũ chưa gắn tổ sẽ **KHÔNG BAO GIỜ khớp** bước nào.

## 6.3. Tiền khoán theo người (khi có nguồn sản lượng)

```
tiền_1_phiếu = làm_tròn( max(0, sản_lượng × đơn_giá − trừ_lỗi) )   ← làm tròn TỪNG PHIẾU
khoán(NV)    = Σ tiền_1_phiếu của NV trong kỳ
```
Chỉ cộng phiếu có cờ **tính khoán** và **có gán nhân viên**.

**Bẫy** — **Sàn 0 áp TỪNG PHIẾU, không phải cả kỳ**: phiếu lỗ nặng bị kẹp về 0 nhưng phiếu khác vẫn cộng đủ ⇒ tổng kỳ **KHÁC** `max(0, Σ(SL×giá) − Σ trừ lỗi)`.

**Neo** — `piece_work_service.py:233-248`.

## 6.4. Khoán vào bảng lương — CỘNG THÊM

```
gross = ... + KHOÁN + ...
payroll_lines.khoan = làm_tròn(tiền khoán của NV trong kỳ)
```

**Cộng PHẲNG và VÔ ĐIỀU KIỆN:** không nhân hệ số thử việc, không prorate theo công, không bị chặn trần công. Engine **không hề đọc cờ `luong_khoan`** ở bước cộng tiền.

**Bẫy**

1. Khoán **CHỊU TNCN** — nó **không** nằm trong thu nhập miễn thuế, khác hẳn tăng ca / ca đêm / cơm ca.
2. Khoán **KHÔNG vào mức đóng BHXH** và **KHÔNG vào đơn giá giờ tăng ca**.
3. HCNS **không thể gõ tay** tiền khoán ở màn Sửa lương.

**Neo** — `payroll_service.py:957-960`, `:1075`, `:1206`, `:1209` · `models/payroll.py:413`.

## 6.5. Loại trừ KHOÁN ⟷ TĂNG CA

```
nếu (tổ có has_piece_work = TRUE) HOẶC (khoản 'tang_ca' của tổ bị TẮT):
      ot_pay = 0        ← nuốt CẢ premium lễ/CN và CẢ tiền ngày off1x
ngược lại: tính bình thường (xem 5.3)
```

**Quyết định theo TỔ** (phòng ban tại thời điểm trả lương), **không** theo từng người và **không** theo việc người đó thực sự có tiền khoán hay không.

**Chốt hai đầu** — Bật `luong_khoan` ở Cấu hình lương ⇒ **ép tắt `tang_ca`** (khoán THẮNG) **và ghi ngược** `departments.has_piece_work` để tránh 2 nguồn sự thật. FE cũng ép ngay ở nút gạt.

**Neo** — `payroll_service.py:881-885`, `:332-338`, `:348-356`, `:274-282` · `frontend/src/pages/CauHinhLuongTab.tsx:907-921`.

**Bẫy — NẶNG NHẤT HIỆN NAY**

> ⚠️ `ot_pay` bị ép 0 dựa trên **cờ TỔ**, trong khi cột khoán **luôn = 0** vì không có nguồn sản lượng.
> ⇒ **Nhân viên tổ khoán đang MẤT tiền tăng ca mà KHÔNG được bù đồng khoán nào.**
> **Bật cờ `has_piece_work` cho một tổ ngay lúc này = CẮT TĂNG CA của cả tổ.**

Bẫy phụ:
- `night_premium_pay` **vẫn được trả** ⇒ giờ OT đêm của tổ khoán chỉ được **0,5×** thay vì 2,0×.
- **Hở một chiều**: sửa cờ `has_piece_work` ở màn **Phòng ban** **KHÔNG** ghi gì vào bảng khoản lương; chỉ chiều Cấu hình lương mới ghi ngược.
- Tổ chưa khai dòng nào: `tang_ca` mặc định **BẬT**, `luong_khoan` mặc định soi `departments.has_piece_work`.
- Cờ `luong_khoan` **không điều khiển việc cộng tiền khoán** — nó chỉ (a) hiện card "Đơn giá khoán" ở FE, (b) qua `has_piece_work` mà **tắt tăng ca**. Hai hệ quả rất lệch nhau trên cùng một nút gạt.

## 6.6. Thưởng/phạt TỔ TRƯỞNG theo tỷ lệ hàng lỗi — **ĐÃ CODE, CHƯA NỐI**

```
nếu sản_lượng dưới ngưỡng min_output_qty → 0
ngược lại: tiền = làm_tròn( tổng_khoán_tổ × tỷ_lệ_bậc / 100 )
bậc trúng = bậc ĐẦU TIÊN có tỷ_lệ_hàng_lỗi ≤ up_to_defect_pct (bậc cuối để trống = ∞)
```
Tỷ lệ **DƯƠNG = thưởng, ÂM = phạt**.

**Trạng thái:** **KHÔNG CÓ AI GỌI** từ `PayrollService`. Khai bậc trên UI **không ra đồng nào**. Màn khai có banner nói thẳng — **đừng gỡ banner đó**.

**Neo** — `piece_work_service.py:161-218` · `models/piece_work.py:68-147`.

## 6.7. Tiền khoán DỰ KIẾN ở Lệnh sản xuất — KHÔNG chảy vào lương

```
khoán_SL   = quy_đổi(số lượng VÀO của bước, đơn vị vào → đơn vị đơn giá, theo quy cách)
khoán_tiền = làm_tròn(khoán_SL × đơn giá đã ghim)
tổng lệnh  = Σ khoán_tiền các bước
```
*Ví dụ thật:* 241 tờ × 86cm × 65cm = 134,72 m² × 150 đ/m² = **20.208 đ**.

**Điều kiện tính** — Bước đã chọn đầu việc, ảnh chụp đầu việc có đủ đơn vị + đơn giá, **và** đầu việc phải thuộc whitelist công đoạn + tổ.

> **Sửa so với bản trích:** ảnh chụp đầu việc (`khoan_json`) **KHÔNG chỉ có 4 khoá** {mã, tên, đơn vị, đơn giá}. Khi công đoạn có dòng định mức, nó còn ghim: năng suất người-giờ (+min/max), đơn vị năng suất, số người tối thiểu/tiêu chuẩn/tối đa. **Ghi đè bằng đúng 4 khoá là XOÁ định mức ⇒ vỡ năng suất/thời lượng của bước.**
> Cũng sửa: hằng `PRICING_BASIS` **vẫn còn sống** ở `models/cong_doan.py:52` (pricing_basis của công đoạn bên tính giá) — migration 0138 chỉ drop `piece_rates.cong_doan_mas` + `piece_rates.tinh_theo`. **Đừng ghi là đã gỡ.**

**Bẫy** — Nhìn thấy "Công thợ dự kiến" có số mà bảng lương ra 0 là **ĐÚNG THIẾT KẾ hiện tại**, không phải bug. Ảnh chụp ghim có chủ ý — xưởng lên giá khoán sau **không được xê dịch lệnh đã phát**.

**Neo** — `lsx_service.py:670-698`, `:604-621`, `:1751` · `quy_doi_service.py:403-419` · `docs/spec-luong.md:92-107`.

---

# 7. GROSS — LIỆT KÊ ĐẦY ĐỦ

**Công thức**
```
gross_trước_phạt = lương_theo_công          (ĐÃ GỒM lương ngày phép)
                 + chuyên_cần
                 + phụ_cấp                  (phụ cấp khác + thâm niên + khoản danh mục HỒ SƠ thu)
                 + khoán
                 + tăng_ca                  (giờ OT + premium lễ/CN + tiền off1x 1×)
                 + night_pay                (LUÔN = 0 từ 03/08/2026)
                 + premium_ca_đêm
                 + thưởng_khác/hoa_hồng     (nhập tay, đã chặn ghi mới)
                 + tiền_cơm_ca + tiền_phụ_cấp_ca
                 + thu_nhập_thêm            (5S + doanh số + thành tích + phép năm + trả đồng phục + điều chỉnh ±)
                 + khoản_thu_phát_sinh_kỳ

gross = max(0, làm_tròn(gross_trước_phạt) − phạt_hiệu_lực)
```

**KHÔNG có trong gross:**

| Khoản | Lý do |
|---|---|
| `lương_ngày_phép` | ⊂ lương theo công |
| `phu_cap_tham_nien` | ⊂ phụ cấp |
| Khoản danh mục loại **TRỪ** | Trừ ở THỰC NHẬN, cố ý không gộp vào trần 30% |
| Tạm ứng, lương đợt 1 | Trừ ở THỰC NHẬN |
| BHXH, đoàn phí, TNCN | Trừ ở THỰC NHẬN |

**Neo** — `payroll_service.py:950-960`, `:1027`, `:1042-1053`, `:1101` · đường "Sửa 1 ô" phải khớp 1-1: `:1503-1516`, `:1540-1556`.

**Bẫy**

1. `gross_trước_phạt` được làm tròn **MỘT LẦN trên tổng** rồi mới trừ phạt ⇒ **tổng các cột đã làm tròn riêng có thể lệch gross vài đồng**. Bình thường.
2. ⚠️ `update_line` **dựng lại `gross_trước_phạt` bằng tay từ các cột đã lưu**. Thêm số hạng mới vào `_compute` mà quên thêm ở đó là **"Sửa 1 ô" ăn mất tiền NLĐ trong im lặng**. Bệnh này **đã tái phát 3 lần** (với `ca_mien`, `khoan_defect`, `component_deduct`).

---

# 8. BHXH · BHYT · BHTN · ĐOÀN PHÍ

## 8.1. Bảng tỷ lệ bảo hiểm — ĐẦY ĐỦ

| Khoản | **NLĐ trừ vào lương** | Chủ SDLĐ (khai để tham chiếu — **KHÔNG trừ NV**) | Trần đóng |
|---|---|---|---|
| BHXH | **8%** | 17,5% | `bh_base_cap` = **50.600.000đ** (= 20 × mức tham chiếu 2,53tr, từ 01/7/2026) |
| BHYT | **1,5%** | 3% | `bh_base_cap` = 50.600.000đ |
| BHTN | **1%** | 1% | `bhtn_base_cap` = **106.200.000đ** (= 20 × LTT vùng I 5,31tr, từ 01/1/2026) |
| TNLĐ–BNN | — | 0,5% | — |
| **Tổng NLĐ** | **10,5%** | 21,5% + 0,5% | |

> ⚠️ **Bốn ô tỷ lệ phía CHỦ (`bhxh_rate_er`, `bhyt_rate_er`, `bhtn_rate_er`, `tnld_bnn_rate`) ở màn Cấu hình lương trông y như các ô khác nhưng SỬA CHÚNG KHÔNG LÀM ĐỔI MỘT ĐỒNG NÀO** trên bảng lương. Engine không đọc. Phép nhân duy nhất là ở **frontend** (`LuongPage.tsx:3001`) để hiện chi phí TNLĐ-BNN cho nhóm "BH đóng nơi khác".
> **Không có cột nào trên `payroll_lines` lưu phần công ty đóng** ⇒ **KHÔNG xuất được báo cáo tổng chi phí BH của công ty từ dữ liệu bảng lương.** Nói thẳng: chưa có.

**Neo** — `models/payroll.py:106-119`, `:141-145` · `payroll_service.py:242-247`.

## 8.2. Mức đóng bảo hiểm (`insurance_base`)

```
insurance_base = lương_vị_trí + lương_trách_nhiệm      (= mức_nền, nguyên mức tháng)
```
**KHÔNG** × hệ số thử việc · **KHÔNG** × (công thực / công chuẩn) · **KHÔNG** cộng phụ cấp nào.

⚠️ **ĐỔI 12/08/2026** — trước đó chỉ `lương_vị_trí`. Bảng lương thật của công ty xác nhận: BH bắt buộc `1.102.080 ÷ 10,5% = 10.496.000`, và đoàn phí `52.480 ÷ 0,5%` ra **cùng con số** ⇒ cả hai bám mức nền đầy đủ. Áp cho **cả ba nhánh** (đóng bình thường · BH nơi khác · nghỉ ≥ ngưỡng) để đoàn phí không ra hai mức.

**Neo** — `payroll_service.py:1004-1012`, `:1102`.

**Bẫy**

1. **KHÔNG prorate**: người đi làm 3/26 công vẫn đóng BH trên **FULL** lương vị trí (chỉ thoát nếu rơi vào luật ≥14 ngày).
2. ~~Chỉ `lương_vị_trí`~~ — **đã đảo 12/08/2026**. Nay mức đóng BH **bằng đúng mức nền tính lương**. Ai có lương trách nhiệm bị trừ BHXH **nhiều hơn trước**: trách nhiệm 2tr ⇒ mất thêm ~210.000đ/tháng.
3. Hồ sơ **CŨ** chỉ khai `base_amount` ⇒ `lương_vị_trí` = 0 ⇒ **BHXH = 0 VÀ đoàn phí = 0** mà bảng lương vẫn ra tiền bình thường, **KHÔNG cảnh báo**.
4. Cột `employee_salaries.insurance_base` (khai mức đóng riêng) vẫn còn trong DB + API nhưng engine **ĐÃ THÔI ĐỌC** (`models/payroll.py:271`). Gõ ô đó **không đổi được gì**.
5. Cờ `payroll_components.in_insurance_base` ("khoản này cộng vào gốc đóng BH") tồn tại trong model/schema/FE nhưng **KHÔNG có chỗ nào trong engine đọc nó** — bật lên **không có tác dụng**.
6. `insurance_base` + `bhxh` trên dòng lương bị **ĐÓNG BĂNG** lúc "Tính lại". `update_line` **không tính lại hai cột này**, kể cả khi HCNS sửa tay mức tháng. **Sửa lương vị trí ở hồ sơ mà không bấm "Tính lại" thì mức đóng BH trên bảng lương vẫn là số cũ.**

## 8.3. Bảo hiểm phía người lao động (cột `bhxh`)

```
gốc_BH   = min(insurance_base, 50.600.000)   nếu trần > 0, ngược lại = insurance_base
gốc_BHTN = min(insurance_base, 106.200.000)  nếu trần > 0, ngược lại = insurance_base

bhxh = gốc_BH × (8% + 1,5%) + gốc_BHTN × 1%
```

**Hai trần áp RIÊNG, KHÔNG dùng chung.** Gõ **0** vào ô trần **KHÔNG phải "miễn đóng"** mà là **"bỏ trần, đóng trên toàn bộ lương"**.

*Ví dụ lương vị trí 60tr:* BHXH+BHYT tính trên 50,6tr, BHTN tính trên **nguyên 60tr** ⇒ 50.600.000 × 9,5% + 60.000.000 × 1% = 4.807.000 + 600.000 = **5.407.000đ**.

**Neo** — `payroll_service.py:1013-1018`, `:1028` · test chốt số `tests/test_luong_api.py:237-253`.

**Bẫy**

1. **TÊN CỘT ĐÁNH LỪA**: cột `payroll_lines.bhxh` là **TỔNG CẢ BA** (BHXH + BHYT + BHTN), không phải riêng BHXH 8%.
2. **Có CHỖ TÍNH THỨ HAI** (bổ sung so với bản trích): `routers/payroll.py:204-224` tách `bhxh` thành 3 dòng cho **phiếu lương**:
   ```
   dòng BHXH = làm_tròn( min(insurance_base, bh_base_cap) × 8% )
   dòng BHYT = làm_tròn( min(insurance_base, bh_base_cap) × 1,5% )
   dòng BHTN = bhxh − dòng BHXH − dòng BHYT        ← DỒN PHẦN DƯ, không phải phép nhân
   ```
   Hai hệ quả: (a) 3 dòng **luôn cộng đúng bằng** `bhxh` (cố ý); (b) **sau khi kỳ đã chốt mà ai đó sửa tỷ lệ/trần ở Cấu hình lương thì phiếu lương kỳ CŨ đổi số hai dòng đầu và toàn bộ sai lệch dồn hết vào dòng BHTN — có thể ra số vô lý, kể cả ÂM**, trong khi tổng trừ và thực nhận không đổi.
3. FE màn Sửa lương hiện 3 dòng làm tròn RIÊNG nên tổng hiển thị có thể **lệch ≤ 2đ** so với engine.
4. `bhxh` bị trừ khi tính thu nhập **tính** thuế TNCN và nằm trong mẫu số trần phạt Điều 102 ⇒ **sai mức đóng BH là sai lây cả thuế lẫn trần phạt**.

## 8.4. Bốn nhánh BHXH — theo đúng thứ tự ưu tiên

| # | Nhánh | Điều kiện | `insurance_base` | `bhxh` | Đoàn phí |
|---|---|---|---|---|---|
| 1 | **THỬ VIỆC** | trạng thái tại kỳ = thử việc | **0** | **0** | **0** |
| 2 | **BH đóng nơi khác** | `employee_salaries.insurance_elsewhere` = true | = lương vị trí | **0** | **VẪN TRỪ** |
| 3 | **Nghỉ không lương ≥ N ngày** | `ngưỡng > 0` **VÀ** `ngày_không_lương ≥ ngưỡng` (mặc định 14, QĐ 595 Đ42.4) | = lương vị trí | **0** | **VẪN TRỪ** |
| 4 | Nhánh thường | còn lại | = lương vị trí | theo công thức 8.3 | theo 8.5 |

```
ngày_không_lương = max(0, std − actual_cong − plain_cong)
```
So sánh là **≥** (đúng bằng ngưỡng là đã miễn). **Không làm tròn** trước khi so — nghỉ 13,5 ngày thì **chưa** miễn với ngưỡng 14.

**Neo** — `payroll_service.py:962-973`, `:975-1018`.

**Bẫy**

1. Nhánh 1 là **nhánh DUY NHẤT** đặt `insurance_base = 0`. Đọc phiếu thấy "mức đóng 20tr, BHXH 0đ" thì đó là nhánh 2 hoặc 3, **không phải lỗi**.
2. ⚠️ Vế **`ngưỡng > 0` là hàng rào SỐNG CÒN**: bỏ nó ra thì `ngày_không_lương ≥ 0` **LUÔN ĐÚNG** ⇒ **CẢ XƯỞNG mất sạch BHXH** mà bảng lương trông vẫn bình thường. Khai ngưỡng = 0 nghĩa là **TẮT LUẬT**, không phải miễn cho mọi người.
3. Nhánh 3 phủ luôn **người VÀO/NGHỈ VIỆC GIỮA THÁNG** (ít công) — vào việc ngày 20 là **tự động không đóng BHXH tháng đó**.
4. Phải **cộng lại `plain_cong`**, nếu quên thì người **đi làm ngày off1x** bị đếm nhầm là nghỉ không lương và **mất BHXH oan**.
5. TNLĐ-BNN mà công ty chịu cho nhóm "BH nơi khác" **chỉ hiển thị ở màn Sửa lương**; engine **không ghi vào bảng lương** ⇒ không tổng hợp ra báo cáo được.

## 8.5. Đoàn phí công đoàn

```
đoàn_phí = 0                              nếu THỬ VIỆC hoặc KHÔNG phải đoàn viên
         = làm_tròn(insurance_base × cong_doan_rate)   còn lại
```

**Lấy số ở đâu** — `employee_salaries.union_member` (Boolean, **mặc định FALSE — opt-in từng người**, chủ chốt 21/07/2026) · `payroll_params.cong_doan_rate` (**MẶC ĐỊNH 0** — chủ phải tự khai; mẫu 0,5% = 0.005).

**Có giảm thuế không** — ⚠️ **ĐỔI 12/08/2026: CÓ.** Đoàn phí nay **giảm thu nhập TÍNH thuế**, đi y hệt BHXH: vừa là vế trừ trong công thức thuế, vừa là tiền thật trừ vào **THỰC NHẬN**. Hai vai khác nhau, không phải trừ hai lần. Trước đó chỉ trừ vào thực nhận.

> Ghi để khỏi bàn lại: TT 111/2013 Đ9 **không** liệt đoàn phí vào danh sách giảm trừ (chỉ có giảm trừ gia cảnh · bảo hiểm bắt buộc & hưu trí tự nguyện · từ thiện–nhân đạo–khuyến học). Đây là **cố ý làm theo cách công ty hạch toán**, không phải nhầm.

**Neo** — `payroll_service.py:1020-1025`, `:1243`, `:480`.

**Bẫy**

1. Đoàn phí tính trên `insurance_base` **GỐC, KHÔNG kẹp trần**: mức nền 60tr thì đoàn phí tính trên 60tr trong khi BHXH chỉ tính trên 50,6tr.
2. **Đóng đoàn phí ở CẢ hai nhánh miễn BHXH** — tháng không đóng BHXH vẫn mất đoàn phí.
3. `cong_doan_rate` mặc định **0** ⇒ chưa khai thì kể cả đoàn viên cũng ra 0đ.
4. ~~**LỆCH HAI ĐƯỜNG** — Phần 14 lỗi #3~~ ✅ **ĐÃ VÁ 12/08/2026** cùng đợt A: `update_line` nay kiểm cả cờ đoàn viên, và khối đoàn phí đã **dời lên TRƯỚC** khối TNCN (bắt buộc, vì thuế nay đọc đoàn phí). Test canh: `test_A4_sua_mot_o_va_tinh_lai_ra_CUNG_SO_THUE` · `test_A5_khong_phai_doan_vien_thi_sua_dong_khong_lam_doan_phi_song_lai`.

---

# 9. THUẾ THU NHẬP CÁ NHÂN

## 9.1. Thu nhập CHỊU thuế

```
thu_nhập_chịu_thuế = max(0, gross_trước_phạt
                            − tăng_ca
                            − night_pay
                            − premium_ca_đêm
                            − khoản_danh_mục_miễn_thuế
                            − (tiền_cơm_ca + tiền_phụ_cấp_ca) )

thu_nhập_miễn_thuế = tăng_ca + night_pay + premium_ca_đêm
                   + khoản_danh_mục_miễn_thuế + tiền_cơm_ca + tiền_phụ_cấp_ca
```

**Áp cho CẢ BA nhánh `pit_mode`** — tính TRƯỚC khi rẽ nhánh.

**Neo** — `payroll_service.py:454-455`, `:1034-1040`, `:1062-1065`.

**Năm khoản MIỄN — liệt kê đầy đủ:**

| # | Khoản | Ghi chú |
|---|---|---|
| 1 | **Tiền tăng ca** (`ot_pay`) | Miễn **toàn bộ**, không trần |
| 2 | `night_pay` | Luôn = 0 với kỳ mới; kỳ cũ vẫn được miễn |
| 3 | **Premium ca đêm** (`night_premium_pay`) | Miễn cả phần `night_pct` lẫn phần cộng dồn OT đêm |
| 4 | **Khoản danh mục có cờ "không chịu thuế"** | Seed mặc định 4 khoản: **trang phục, trợ cấp nhà ở, hỗ trợ đi lại, tiền cơm**. Khoản khác (điện thoại, xăng xe…) **CHỊU** thuế |
| 5 | **Cơm ca + phụ cấp ca** | Miễn toàn bộ, **KHÔNG áp trần 730.000đ/tháng** |

**KHÔNG miễn:** mọi khoản thưởng (5S, doanh số, thành tích, phép năm, trả đồng phục, điều chỉnh, thưởng khác) và **KHOÁN**.

**Bẫy**

1. Thu nhập chịu thuế tính trên gross **TRƯỚC** khấu trừ kỷ luật, còn cột `gross` lưu là **SAU** phạt ⇒ **thu nhập chịu thuế có thể LỚN HƠN gross**. Không phải lỗi.
2. Tiền phạt, đoàn phí, tạm ứng, lương đợt 1, khoản danh mục loại trừ **KHÔNG giảm** thu nhập chịu thuế.
3. Khoản danh mục dùng **SNAPSHOT trên dòng lương**, không đọc danh mục sống ⇒ đổi cờ "Chịu thuế" hôm nay **KHÔNG sửa số của kỳ cũ** (cố ý). Ngược lại, sửa cờ rồi mà chưa bấm "Tính lại" thì kỳ hiện tại vẫn giữ cách tính cũ.
4. `thu_nhập_miễn_thuế` là số **NGƯỢC DÒNG**: đường "Sửa 1 ô" suy ra phần khoản danh mục miễn **bằng phép trừ** từ snapshot này (`:493-494`) chứ không đọc lại danh mục. **Snapshot sai/cũ ⇒ thuế sai ngay**, mà bảng lương vẫn trông bình thường.
5. `chịu_thuế + miễn_thuế` có thể **lệch ≤ 1đ** so với `gross_trước_phạt` (làm tròn khác chỗ).

## 9.2. Giảm trừ gia cảnh

```
giảm_trừ = (deduction_self  nếu apply_self_deduction bật, ngược lại 0)
         + deduction_dependent × số_người_phụ_thuộc
```

| Khoản | Mức 2026 | Nguồn |
|---|---|---|
| Bản thân | **15.500.000 đ/tháng** | `payroll_params.deduction_self` |
| Mỗi người phụ thuộc | **6.200.000 đ/tháng** | `payroll_params.deduction_dependent` |

(NQ 110/2025/UBTVQH15. Migration chỉ nâng mức khi params **còn đúng số cũ** 11.000.000/4.400.000 — admin đã chỉnh tay thì **không đè**.)

**Cờ `apply_self_deduction`** (`employee_salaries`, mặc định **TRUE**): chỉ tắt **giảm trừ BẢN THÂN** (người làm 2 nơi chỉ đăng ký ở một nơi). Giảm trừ **người phụ thuộc KHÔNG phụ thuộc cờ này**. **Tắt cờ là NLĐ mất 15.500.000đ giảm trừ, thuế nhảy vọt.**

**Khi nào KHÔNG áp dụng** — **CHỈ áp cho nhánh luỹ tiến.** Hai nhánh `khau_tru_10` và `cam_ket_08` **return SỚM** trước dòng này ⇒ **không có giảm trừ nào**.

**Neo** — `payroll_service.py:471-474` · `models/payroll.py:121-122`, `:296`.

**Bẫy**

1. **Hệ thống KHÔNG kiểm tra hồ sơ đăng ký người phụ thuộc** — gõ bao nhiêu thì giảm trừ bấy nhiêu.
2. Giảm trừ tính **ĐỦ THÁNG**, không prorate theo số ngày làm/công.
3. Đường "Sửa 1 ô" đọc cờ `apply_self_deduction` theo **mức lương HÔM NAY**, không theo tháng của kỳ lương ⇒ **sửa dòng kỳ CŨ có thể ăn cờ mới**.

## 9.3. Thu nhập TÍNH thuế — nhánh luỹ tiến

```
thu_nhập_tính_thuế = max(0, thu_nhập_chịu_thuế − bhxh − ĐOÀN_PHÍ − giảm_trừ)
```

**`bhxh` = 0 ở 3 nhánh** (bản đã sửa — bản trích ban đầu **thiếu nhánh thử việc**):
1. **NV THỬ VIỆC** (`payroll_service.py:976-978`) — nhánh chạy **trước** cả hai nhánh kia
2. BH đóng nơi khác
3. Nghỉ không lương ≥ ngưỡng (ngưỡng > 0)

⇒ Ba nhóm này **thu nhập tính thuế cao lên tương ứng**.

⚠️ **Vế `ĐOÀN_PHÍ` thêm 12/08/2026** theo bảng lương thật của công ty — xem §8.5.

**Bẫy** — **CHỊU thuế ≠ TÍNH thuế.** Chủ hỏi "tổng mức lương chịu thuế" là số **trước** giảm trừ (`thu_nhap_chiu_thue`). Số dùng để tra biểu thuế là `pit_taxable` — **sau** khi trừ BHXH + giảm trừ. Kẹp sàn 0, **âm bao nhiêu cũng KHÔNG chuyển lỗ sang tháng sau**.

## 9.4. BIỂU THUẾ LUỸ TIẾN — ĐẦY ĐỦ 5 BẬC (biểu THÁNG)

Luật Thuế TNCN 109/2025/QH15, kỳ tính thuế 2026 (biểu cũ 7 bậc **đã bỏ**).

| Bậc | Thu nhập TÍNH thuế / tháng | Thuế suất |
|---|---|---|
| 1 | Đến 10.000.000 đ | **5%** |
| 2 | Trên 10.000.000 đến 30.000.000 đ | **10%** |
| 3 | Trên 30.000.000 đến 60.000.000 đ | **20%** |
| 4 | Trên 60.000.000 đến 100.000.000 đ | **30%** |
| 5 | Trên 100.000.000 đ | **35%** |

**Cách cộng — CỘNG TỪNG BẬC (marginal), KHÔNG dùng biểu rút gọn:**
```
thuế = Σ_bậc [ (min(thu_nhập_tính_thuế, trần_bậc) − trần_bậc_trước) × thuế_suất_bậc ]
```
*Ví dụ 45.000.000:* 10tr×5% + 20tr×10% + 15tr×20% = 500.000 + 2.000.000 + 3.000.000 = **5.500.000đ**.

**Lấy số ở đâu** — Bảng `pit_tax_brackets`, **SỬA ĐƯỢC** ở màn Cấu hình lương. Có **HAI nguồn số giống hệt nhau**: seed thật (`seed.py:1927-1947`) và fallback trong service (`payroll_service.py:92-97`).

**Neo** — `payroll_service.py:176-188`, `:388-406` · `payroll_repo.py:79-80` · `models/payroll.py:460-470`.

**Bẫy** (bản đã sửa)

1. **Luật đổi phải sửa CẢ HAI chỗ** (`seed.py` và `payroll_service.py`) — sửa một chỗ thì DB mới và DB trống ra hai biểu khác nhau.
2. **Xoá BỚT vài bậc thì không mọc lại; xoá SẠCH thì 5 bậc 2026 TỰ TÁI SINH** ngay lần tính lương/mở màn kế tiếp (`:391-394`), không cần restart.
3. `update_pit_bracket` (`:402-406`) **KHÔNG validate gì cả** — sửa thuế suất thành **số ÂM vẫn lưu được**. Chỉ `create_pit_bracket` mới chặn thuế suất < 0.
4. **KHÔNG kiểm trần bậc tăng dần theo thứ tự**: nhập lệch thứ tự làm phép `(min(t,trần) − trần_trước)` ra **ÂM** và **TRỪ BỚT tiền thuế**.
5. Nếu bậc cuối có trần khác rỗng thì thu nhập vượt trần bậc cuối **KHÔNG bị đánh thuế đồng nào**.
6. Đây là **biểu THÁNG**, không phải quyết toán năm. Engine **không cộng dồn 12 tháng**, **không xử lý người vào/nghỉ giữa năm**. Nói thẳng: **chưa có quyết toán năm.**

## 9.5. Ba chế độ thuế (`employees.pit_mode`)

| Chế độ | Áp cho | Công thức | Giảm trừ? | Trừ BHXH? |
|---|---|---|---|---|
| **`luy_tien`** (mặc định) | NV chính thức | Biểu 5 bậc ở 9.4 | **CÓ** | **CÓ** |
| **`khau_tru_10`** | HĐ < 3 tháng / thời vụ / thực tập | `thuế = 10% × chịu_thuế` nếu `chịu_thuế ≥ 2.000.000`, ngược lại 0 | **KHÔNG** | **KHÔNG** |
| **`cam_ket_08`** | Đã làm cam kết 08/CK-TNCN | `thuế = 0` | — | — |

**Cả ba chế độ đều được MIỄN đủ 5 khoản** ở mục 9.1.

**Neo** — `payroll_service.py:457-470`, `:461-462` · `models/employee.py:39-42`, `:206-208`.

**Bẫy nhánh `khau_tru_10`**

1. Ngưỡng so với **TỔNG thu nhập chịu thuế CỦA CẢ DÒNG LƯƠNG THÁNG**, không phải "mỗi lần trả" như luật diễn đạt — trả 2 đợt trong tháng vẫn tính một lần trên tổng.
2. Vượt ngưỡng thì đánh 10% **TOÀN BỘ**, không chỉ phần vượt. Dùng `≥` (đúng bằng 2.000.000 là đã khấu trừ).
3. Vẫn bị trừ BHXH ở thực nhận nhưng **BHXH không giảm được số thuế**.
4. **NV thử việc KHÔNG tự động vào nhánh này** — phải khai `pit_mode` trên hồ sơ.
5. Khai thuế suất = 0 ⇒ thuế 0 **âm thầm**. Khai ngưỡng = 0 ⇒ khấu trừ 10% **từ đồng đầu tiên**.

**Bẫy nhánh `cam_ket_08`**

1. `pit_taxable` trả 0 nhưng `thu_nhap_chiu_thue` **vẫn đầy đủ** ⇒ **báo cáo quyết toán phải lấy `thu_nhap_chiu_thue`**, lấy `pit_taxable` là ra 0 sai bét.
2. Hệ thống **KHÔNG kiểm tra** điều kiện hợp lệ của cam kết (MST, một nơi làm việc, tổng năm dưới ngưỡng) và **KHÔNG cảnh báo** khi vượt ngưỡng giữa năm. **Bật cờ là miễn vô điều kiện.**
3. **Không có hạn hiệu lực theo năm** — bật một lần là năm sau vẫn miễn.

## 9.6. `pit_manual` — ghi đè thuế bằng tay

| Thao tác | Hành vi |
|---|---|
| **Tính lại** (`generate`) | `pit_manual = true` ⇒ **GIỮ số tay**; ngược lại dùng số tự tính |
| **Sửa 1 ô** truyền `pit_manual = false` | Tính lại tự động, **mở khoá** |
| **Sửa 1 ô** truyền `pit` (≠ rỗng) | `pit = làm_tròn(pit)`, `pit_manual = true` |
| **Sửa 1 ô** khi `pit_manual` đang false | Tính lại tự động |

**Chỉ sửa được khi kỳ lương ở trạng thái DRAFT.**

**Neo** — `payroll_service.py:1235-1239`, `:1531-1539`, `:1260`.

**Bẫy**

1. Khi `pit_manual = true`, cột `pit_taxable` **VẪN ghi số TỰ TÍNH** ⇒ hai số không khớp nhau. **Đừng dùng `pit_taxable` để kiểm tra ngược số thuế tay.**
2. **Truyền `pit = 0` cũng là KHOÁ TAY.** Muốn trả về tự động phải truyền `pit_manual = false`, **không phải gõ 0**.
3. Migration 2026 **backfill `pit_manual = TRUE` cho MỌI dòng cũ có `pit > 0`** ⇒ dòng kỳ cũ mặc định **bị khoá tay**, tính lại không đổi số.
4. ⚠️ Số thuế tay **chỉ nới trần phạt ở đường "Sửa 1 ô"** — xem Phần 14, lỗi #2.

---

# 10. PHẠT KỶ LUẬT & TRẦN 30% ĐIỀU 102

## 10.1. Tổng phạt thô

```
tổng_phạt_thô = vi_phạm + đi_trễ + ĐT_vượt_trội + phạt_biên_bản + phạt_5S_đồng_phục
```
**KHÔNG gồm** trừ lỗi khoán, khoản trừ danh mục, tạm ứng.

Cả 5 cột là ô HCNS gõ tay ở màn Sửa lương (**trừ `đi_trễ` mặc định tự tính**). Schema chặn âm (`schemas/payroll.py:482-493`). **Tất cả LƯU RAW** — số đã nhập, không lưu số đã bị kẹp trần.

**Neo** — `payroll_service.py:1045-1046`, `:1542-1543`.

**Bẫy — TÊN CỘT ĐÁNH LỪA**

| Cột | Thực chất |
|---|---|
| `dt_vuot_troi` | "Điện thoại vượt trội" — thu hồi cước vượt định mức, **nhưng bị xếp CHUNG rổ phạt kỷ luật và ăn vào trần 30%** |
| `tra_dong_phuc` | Khoản **THU** (cộng vào lương) — **KHÔNG** phải trừ |
| `phat_5s_dong_phuc` | Khoản **PHẠT** — dễ nhầm với ô trên |

Cột phạt lưu RAW nên **nhìn phiếu thấy phạt 100tr nhưng thực trừ có thể chỉ vài triệu** (do trần).

## 10.2. Phạt đi trễ / về sớm TỰ ĐỘNG

**Công thức** (bản đã sửa — bản trích ban đầu thiếu 4 điều kiện)
```
Với mỗi NGÀY có chấm công, KHÔNG phải ngày lễ / off1x / có đơn phép nguyên ngày:

phút_trễ    = max(0, giờ_vào − (giờ_bắt_đầu_ca + DUNG SAI CA))     ← CÓ dung sai
phút_về_sớm = max(0, giờ_kết_thúc_ca − giờ_ra)                     ← KHÔNG có dung sai
phút_vi_phạm = max(0, phút_trễ + phút_về_sớm − phút_đã_xin_đơn_duyệt)

nếu ngày đó là NGÀY NGHỈ theo Lịch chung → NHÂN ĐÔI SỐ PHÚT trước khi tra bảng

đi_trễ = Σ (mỗi ngày) tra_bảng_bậc(phút_vi_phạm)
```

**Bốn điều kiện làm lệch tiền thật:**

| # | Điều kiện | Hệ quả |
|---|---|---|
| 1 | **BẤT ĐỐI XỨNG DUNG SAI** — phút trễ **đã trừ** dung sai ca (`work_shifts.grace_minutes`, mặc định 5); phút về sớm **KHÔNG có dung sai nào** | **Vào trễ 5 phút = 0đ, nhưng về sớm 5 phút = 20.000đ** |
| 2 | "Ngày nhân đôi" **KHÔNG phải "Chủ nhật"** — là **MỌI ngày không phải ngày làm việc theo Lịch chung** | Xưởng nghỉ thứ 7 thì thứ 7 cũng ×2 phút |
| 3 | **QUÊN CHẤM RA** ⇒ `phút_về_sớm = 0` | Ngày treo chỉ bị phạt phần đi trễ, **không** bị phạt về sớm (dù công = 0) |
| 4 | Chỉ chạy cho ngày **CÓ dữ liệu chấm công** | Ngày vắng trắng **không sinh phạt trễ** |

**Neo** — `attendance_service.py:173`, `:199`, `:1196-1197`, `:1214-1221` · `payroll_service.py:1193-1200`, `:191-201`.

**Khi nào KHÔNG áp dụng** — **CHỈ tự tính khi `di_tre_manual = false`.** HCNS gõ tay ô `đi_trễ` ⇒ khoá tay ⇒ "Tính lại" **không đè**. Gửi `di_tre_manual = false` để đưa về tự động.

## 10.3. Bảng bậc phạt đi trễ — ĐẦY ĐỦ

| Bậc | Số phút vi phạm trong NGÀY | Tiền phạt / NGÀY |
|---|---|---|
| 1 | ≤ 15 phút | **20.000 đ** |
| 2 | ≤ 30 phút | **40.000 đ** |
| 3 | ≤ 60 phút | **100.000 đ** |
| 4 | > 60 phút (trần để trống = ∞) | **150.000 đ** |

Tra bậc **ĐẦU TIÊN** (theo thứ tự) có trần ≥ số phút; hết bậc thì lấy bậc cuối. **Tính 1 lần/ngày vi phạm, KHÔNG nhân theo số phút.**

**Bẫy**

1. **Chủ nhật nhân đôi PHÚT chứ không nhân đôi TIỀN** ⇒ nhảy bậc: trễ 20' ngày thường = 40.000đ; cùng 20' ngày nghỉ → 40' → **100.000đ**.
2. Phạt **theo LẦN/NGÀY**: trễ 5 phút × 10 ngày = **200.000đ**; trễ 50 phút × 1 ngày = **100.000đ**.
3. Bảng **KHÔNG có migration** — chỉ do `create_all` tạo + seed lười khi bảng trống. DB prod cũ chưa ai mở màn cấu hình thì bảng trống, phạt trả **0đ** cho tới lần tính lương đầu tiên.
4. Docstring model `LatePenaltyBracket` (`models/payroll.py:477-478`) ghi *"ENGINE CHƯA áp bảng này"* — **ĐÃ LỖI THỜI, engine đang áp thật.**

## 10.4. Trần khấu trừ Điều 102 BLLĐ (30%)

```
gốc_102       = max(0, gross_trước_phạt − bhxh − thuế_TNCN)
room          = max(0, tỷ_lệ_trần × gốc_102 − trừ_lỗi_khoán)
phạt_hiệu_lực = min(tổng_phạt_thô, room)

gross = max(0, gross_trước_phạt − phạt_hiệu_lực)

Nếu tỷ_lệ_trần ≤ 0 → TẮT TRẦN: phạt_hiệu_lực = tổng_phạt_thô
```
`payroll_params.phat_cap_pct`, mặc định **0,30** (mức LUẬT, không phải chính sách công ty).

**CHỈ kẹp:** 5 cột phạt kỷ luật + trừ lỗi khoán.
**KHÔNG kẹp:** khoản trừ danh mục, tạm ứng, lương đợt 1, BHXH, TNCN, đoàn phí.

**Neo** — `payroll_service.py:156-173`, `:1047-1049`, `:1544-1549`.

**Bẫy**

1. Trần tính trên gross **TRƯỚC phạt và TRƯỚC đoàn phí** — không phải trên số còn lại.
2. **Trừ lỗi khoán ĂN TRƯỚC vào room**: trừ lỗi nhiều thì room còn ít, phạt kỷ luật bị cắt gần hết **dù bảng lương không hiện lý do**.
3. `tỷ_lệ_trần = 0` nghĩa là **TẮT TRẦN**, không phải cấm trừ.
4. ⚠️ **LỆCH HAI ĐƯỜNG khi TNCN gõ tay** — xem Phần 14, lỗi #2.

## 10.5. Phần phạt vượt trần

```
phần_vượt = tổng_phạt_thô − phạt_hiệu_lực  →  BỎ, KHÔNG chuyển sang kỳ sau
```
**Không có bảng/cột nào lưu phần vượt. Không có sổ nợ phạt.**

**Bẫy** — Muốn thu tiếp tháng sau thì HCNS **phải TỰ gõ lại** số dư vào ô phạt kỳ sau — hệ thống không nhắc, không theo dõi. Vì cột phạt lưu RAW và được **preserve** khi Tính lại, **rất dễ thu trùng** nếu HCNS lại gõ thêm.

## 10.6. Trừ lỗi hàng khoán

```
khoán (vào gross)   = Σ_phiếu max(0, SL × đơn giá − trừ_lỗi)   ← trừ lỗi ĐÃ trừ ở đây
trừ_lỗi_khoán (cho trần) = Σ_phiếu trừ_lỗi                      ← KHÔNG kẹp
```
⇒ **Trừ lỗi KHÔNG bị trừ lần thứ hai** ở bảng lương. Nó chỉ **ăn bớt room 30%**.

**Bẫy** — `khoán` có **sàn 0 từng phiếu**, còn `trừ_lỗi_khoán` **không kẹp** ⇒ phần "đã bỏ" vẫn ăn room, **cắt oan phạt kỷ luật hợp lệ**. Hiện tại cả hai luôn rỗng (nguồn sản lượng đã gỡ) nên cửa trần 30% **chưa bao giờ bị khoán bào mòn**.

**Neo** — `piece_work_service.py:233-260` · `payroll_service.py:1308-1314`.

---

# 11. TẠM ỨNG · KHOẢN TRỪ DANH MỤC · THỰC NHẬN

## 11.1. Tạm ứng & Lương đợt 1

```
tạm_ứng      = Σ số tiền phiếu loại 'tam_ung'    , trạng thái ĐÃ DUYỆT, đúng kỳ khai TRÊN PHIẾU
lương_đợt_1  = Σ số tiền phiếu loại 'luong_dot_1', trạng thái ĐÃ DUYỆT, đúng kỳ khai TRÊN PHIẾU
```
Cả hai trừ **THẲNG vào thực nhận**, **KHÔNG** vào trần 30%, **KHÔNG** ảnh hưởng TNCN/BHXH.

**Chỉ phiếu ĐÃ DUYỆT.** Phiếu chờ duyệt / từ chối / đã huỷ ⇒ không trừ. **Không còn trần số tiền tạm ứng** (gỡ 24/07/2026). Cột `payroll_params.advance_max_pct` (0,10) **vẫn còn trên DB nhưng DORMANT** — đừng để kế toán tưởng còn trần 10%.

**Neo** — `payroll_repo.py:281-293` · `payroll_service.py:736-737`, `:1159-1160`, `:1240-1241`, `:1243-1244`.

**Bẫy**

1. Phiếu ứng **khai NHẦM kỳ** ⇒ tiền đã đưa nhưng lương **KHÔNG trừ** — **không có cảnh báo nào**.
2. Duyệt phiếu **sau khi** đã "Tính lại" ⇒ chưa trừ cho tới lần Tính lại kế tiếp. "Sửa 1 ô" dùng lại số đã lưu, **không đọc lại phiếu mới duyệt**.
3. Chiều ngược: **HỦY một phiếu đã duyệt** vẫn được; hủy xong mà chỉ bấm "Sửa 1 ô" thì **số cũ vẫn bị trừ** — phải "Tính lại" mới hoàn.
4. Ứng vượt lương: **sàn 0 nuốt phần dư**, hệ thống **không ghi nợ ở đâu**.

## 11.2. Khoản trừ theo danh mục

```
khoản_trừ = Σ số tiền mọi khoản danh mục loại 'trừ'
            (gộp CẢ hai nguồn: gán ở HỒ SƠ NV + phát sinh riêng kỳ)
          → trừ THẲNG vào THỰC NHẬN
          → KHÔNG vào trần 30%, KHÔNG giảm thu nhập chịu thuế TNCN
```

Đây là **khấu trừ THOẢ THUẬN** (mua đồng phục, trừ tiền cơm, thu hộ…), cố ý tách khỏi rổ kỷ luật Điều 102.

**Neo** — `payroll_service.py:855-857`, `:1057-1060`, `:1243-1244`, `:1487-1490`, `:1553-1556`.

**Bẫy** (bản đã sửa — bản trích ban đầu **SAI**)

> **Phiếu lương CÓ hiện từng dòng khấu trừ danh mục.** `LineOut` mang cả danh sách khoản (`schemas/payroll.py:457`) và phiếu lương in từng dòng vào cột "Trừ" (`frontend/src/pages/LuongPage.tsx:3598`, `:3665`).
> **Cái THIẾU là: không có cột tổng `component_deduct` trên `payroll_lines` và không có field scalar trong `LineOut`** ⇒ **bảng lương (lưới danh sách) không có cột tổng khấu trừ danh mục**.

**Bẫy THẬT phải nhớ:** cột "Trừ" của phiếu lương cộng các **cột phạt RAW** ⇒ **tổng cột "Trừ" KHÔNG khớp (gross − net)** khi phạt bị kẹp trần.

**Bẫy phía THU:** khoản nguồn hồ sơ **đã nằm trong `allowance`**, khoản nguồn phát sinh cộng riêng — **nối hai danh sách lại là CỘNG HAI LẦN**.

## 11.3. THỰC NHẬN

```
gross   = max(0, gross_trước_phạt − phạt_hiệu_lực)                       ← SÀN 0 lần một

net_pay = max(0, gross − bhxh − đoàn_phí − thuế_TNCN
                       − tạm_ứng − lương_đợt_1 − khoản_trừ_danh_mục)     ← SÀN 0 lần hai
```

> **Đếm cho đúng: sau `gross` có ĐÚNG 6 khoản trừ**, và **không khoản nào bị kẹp trần**: BHXH · đoàn phí · TNCN · tạm ứng · lương đợt 1 · khoản trừ danh mục.
> **Đường trừ THỨ BẢY khác chất**: `dieu_chinh_luong` âm — nó cộng **đại số vào `gross_trước_phạt`**, nên **giảm luôn thu nhập chịu thuế TNCN** và **NỚI trần 30%**. Khác hẳn 6 khoản trên.

**Neo** — `payroll_service.py:1053`, `:1243-1244`, `:1264`, `:1550`, `:1553-1556` · `models/payroll.py:455`.

**Bẫy** — **HAI SÀN 0 che mất tiền**: nếu tổng khấu trừ > gross thì phần thiếu **BIẾN MẤT**, không ghi nợ, không chuyển kỳ sau, phiếu lương chỉ hiện 0đ.

---

# 12. HAI VÍ DỤ SỐ CHẠY TRỌN VẸN

## VÍ DỤ 1 — Công nhân sản xuất có tăng ca

**Hồ sơ**

| Mục | Giá trị |
|---|---|
| Nhân viên | Nguyễn Văn Bình — Thợ in offset, tổ In offset |
| Trạng thái | **Chính thức** (không thử việc) |
| Kỳ lương | **08/2026** · Công chuẩn theo lịch **std = 26** |
| Tổ | `has_piece_work` = **TẮT**, khoản `tang_ca` = **BẬT**, `chuyen_can` = **BẬT** |
| Lương vị trí | 7.800.000 · Lương trách nhiệm 0 ⇒ **mức nền 7.800.000** |
| Chuyên cần khai | 300.000 |
| Phụ cấp thâm niên | 200.000 |
| Khoản danh mục hồ sơ | Hỗ trợ đi lại 300.000 (**miễn thuế**) |
| Người phụ thuộc | 0 · Đoàn viên: **CÓ** (`cong_doan_rate` = 0,5%) |
| Ca làm | Ca ngày (không qua đêm), cơm ca **25.000đ/ngày**, phụ cấp ca 0 |

**Dữ liệu chấm công**

| Mục | Số |
|---|---|
| Đi làm ngày thường | 26 ngày đủ công |
| Đi làm thêm 1 Chủ nhật | 1,0 công ⇒ `công_nghỉ_tuần` = 1,0 |
| **Công thực `actual_cong`** | **27,0** |
| Nghỉ phép có lương | 0 |
| Tăng ca ngày thường (có phiếu duyệt phủ đủ) | **20 giờ** = 1.200 phút |
| Trong đó rơi vào khung 22h–06h | **6 giờ** = 360 phút |
| Đi trễ | 2 ngày, mỗi ngày trễ 20 phút (dung sai ca 5 ph ⇒ **15 ph vi phạm/ngày**) |
| Tạm ứng đã duyệt đúng kỳ | 2.000.000 |

### Bước 1 — Đơn giá

| Chỉ tiêu | Tính | Kết quả |
|---|---|---|
| Mức nền hiệu lực | 7.800.000 × 1,0 | 7.800.000 |
| **Đơn giá ngày** | 7.800.000 ÷ 26 | **300.000 đ/công** |
| **Đơn giá giờ** | 300.000 ÷ 8 | **37.500 đ/giờ** |

### Bước 2 — Lương theo công

```
công_phép     = 0
công_làm      = 27,0
công_làm_trả  = min(27,0 ; 26) = 26,0        ← TRẦN CẮT 1 công dôi
lương_theo_công = 300.000 × 26,0 = 7.800.000
```
> Ghi chú: 1 công Chủ nhật dôi ra **không** ra thêm tiền ở đây. Nó được trả qua premium ở bước 4.

### Bước 3 — Chuyên cần + Phụ cấp

```
số_ngày_nghỉ = max(0 ; 26 − (27,0 + 0)) = 0
tỷ_lệ = 1,0  →  chuyên_cần = 300.000 × 1,0 = 300.000

phụ_cấp = 0 (khai tay) + 200.000 (thâm niên) + 300.000 (hỗ trợ đi lại) = 500.000
```

### Bước 4 — Tăng ca + premium

```
giờ_OT_thường = (1.200 − 0 − 0) ÷ 60 = 20 giờ

tăng_ca = 37.500 × 20 × 1,5                          = 1.125.000
        + 300.000 × [ 1,0 × max(0; 2,0 − 1) ]        =   300.000   ← premium làm CN
                                                      -----------
                                                        1.425.000
```

### Bước 5 — Cơm ca + premium ca đêm

```
cơm_ca = 25.000 × 27 ngày present = 675.000
phụ_cấp_ca = 0

premium_ca_đêm:
  (A) ca NGÀY (không qua đêm) ⇒ 0
  (B) 6 giờ OT đêm ngày thường × 37.500 × (0,30 + 0,20 × 1,0)
      = 6 × 37.500 × 0,5 = 112.500
premium_ca_đêm = 112.500
```
> Tổng cho 1 giờ OT đêm = 1,5× (ở cột Tăng ca) + 0,5× (ở cột Premium đêm) = **2,0× = 200%**. Kế toán soi riêng cột "Tăng ca" sẽ thấy thiếu 25% — không phải lỗi.

### Bước 6 — GROSS trước phạt

| Khoản | Số tiền |
|---|---|
| Lương theo công | 7.800.000 |
| Chuyên cần | 300.000 |
| Phụ cấp (khác + thâm niên + danh mục) | 500.000 |
| Khoán | 0 |
| Tăng ca | 1.425.000 |
| `night_pay` | 0 |
| Premium ca đêm | 112.500 |
| Thưởng khác / hoa hồng | 0 |
| Cơm ca | 675.000 |
| Phụ cấp ca | 0 |
| Thưởng chi tiết + điều chỉnh | 0 |
| Khoản phát sinh kỳ | 0 |
| **GROSS TRƯỚC PHẠT** | **10.812.500** |

### Bước 7 — BHXH + Đoàn phí

```
ngày_không_lương = max(0 ; 26 − 27,0 − 0) = 0  <  14   ⇒ ĐÓNG bình thường
insurance_base = lương vị trí = 7.800.000       (KHÔNG phải mức nền)
gốc_BH   = min(7.800.000 ; 50.600.000)  = 7.800.000
gốc_BHTN = min(7.800.000 ; 106.200.000) = 7.800.000

bhxh = 7.800.000 × 9,5%  +  7.800.000 × 1%
     =       741.000     +        78.000     =  819.000

đoàn_phí = 7.800.000 × 0,5% = 39.000
```

Chi tiết 3 dòng trên phiếu lương: BHXH 624.000 · BHYT 117.000 · BHTN 819.000 − 624.000 − 117.000 = **78.000** ✓

### Bước 8 — Thuế TNCN

```
thu_nhập_miễn_thuế = 1.425.000 (tăng ca) + 0 + 112.500 (đêm)
                   + 300.000 (hỗ trợ đi lại) + 675.000 (cơm ca)
                   = 2.512.500

thu_nhập_chịu_thuế = 10.812.500 − 2.512.500 = 8.300.000

giảm_trừ = 15.500.000 (bản thân) + 0 = 15.500.000
thu_nhập_tính_thuế = max(0 ; 8.300.000 − 819.000 − 15.500.000) = max(0 ; −8.019.000) = 0

THUẾ TNCN = 0
```

### Bước 9 — Phạt + trần 30%

```
đi_trễ = 2 ngày × bậc 1 (15 phút ≤ 15) × 20.000 = 40.000
tổng_phạt_thô = 40.000

gốc_102 = max(0 ; 10.812.500 − 819.000 − 0) = 9.993.500
room    = max(0 ; 0,30 × 9.993.500 − 0)     = 2.998.050
phạt_hiệu_lực = min(40.000 ; 2.998.050)     = 40.000     ← chưa chạm trần

GROSS = max(0 ; 10.812.500 − 40.000) = 10.772.500
```

### Bước 10 — THỰC NHẬN

| Dòng | Số tiền |
|---|---|
| GROSS | 10.772.500 |
| − BHXH+BHYT+BHTN | − 819.000 |
| − Đoàn phí | − 39.000 |
| − Thuế TNCN | − 0 |
| − Tạm ứng | − 2.000.000 |
| − Lương đợt 1 | − 0 |
| − Khoản trừ danh mục | − 0 |
| **THỰC NHẬN** | **7.914.500 đ** |

*Kiểm:* 10.772.500 − 819.000 = 9.953.500 → − 39.000 = 9.914.500 → − 2.000.000 = **7.914.500** ✓

---

## VÍ DỤ 2 — Nhân viên văn phòng lương cao, có người phụ thuộc

**Hồ sơ**

| Mục | Giá trị |
|---|---|
| Nhân viên | Trần Thị Mai — Trưởng phòng Kinh doanh |
| Trạng thái | **Chính thức** |
| Kỳ lương | **02/2026** · Công chuẩn theo lịch **std = 24** ← *lưu ý: tháng 2 mẫu số nhỏ hơn* |
| Tổ | Không khoán, tăng ca BẬT (nhưng không có giờ OT) |
| Lương vị trí | 36.000.000 · Lương trách nhiệm 12.000.000 ⇒ **mức nền 48.000.000** |
| Chuyên cần khai | 500.000 |
| Phụ cấp thâm niên | 500.000 |
| Khoản danh mục hồ sơ | Phụ cấp điện thoại 500.000 (**CHỊU thuế**) |
| Khoản danh mục phát sinh kỳ | Thưởng doanh số Q1 **10.000.000** (CHỊU thuế) |
| Khoản danh mục loại **TRỪ** | Trừ tiền đồng phục 400.000 |
| Người phụ thuộc | **2** · `apply_self_deduction` = BẬT |
| Đoàn viên | CÓ (0,5%) |
| Ca làm | Hành chính, cơm ca 25.000đ/ngày, phụ cấp ca 0 |

**Dữ liệu chấm công**

| Mục | Số |
|---|---|
| Đi làm | 21 ngày đủ công |
| Nghỉ **phép năm CÓ lương** | 2 ngày |
| Nghỉ **KHÔNG lương** | 1 ngày |
| **Công thực `actual_cong`** | 21 + 2 = **23,0** |
| Công phép có lương | **2,0** |
| Tăng ca / ca đêm | 0 |
| Phạt | 0 |
| **Lương đợt 1** đã duyệt & đã chi | 15.000.000 |

### Bước 1 — Đơn giá

| Chỉ tiêu | Tính | Kết quả |
|---|---|---|
| Mức nền hiệu lực | 48.000.000 × 1,0 | 48.000.000 |
| **Đơn giá ngày** | 48.000.000 ÷ 24 | **2.000.000 đ/công** |
| Đơn giá ngày phép (theo **lương vị trí**) | 36.000.000 ÷ 24 | **1.500.000 đ/công** |

### Bước 2 — Lương theo công (có ngày phép)

```
phép        = min(2,0 ; 23,0) = 2,0
làm         = 23,0 − 2,0 = 21,0
công_làm_trả  = min(21,0 ; 24) = 21,0
công_phép_trả = min(2,0 ; max(0 ; 24 − 21,0)) = min(2,0 ; 3,0) = 2,0

lương_ngày_phép = 1.500.000 × 2,0                = 3.000.000
lương_theo_công = 2.000.000 × 21,0 + 3.000.000   = 45.000.000
```
> **Chú ý:** dòng "Lương ngày phép 3.000.000" trên phiếu là số **TRONG ĐÓ** của 45.000.000. **Không cộng lại.**
> Cũng chú ý: ngày phép chỉ được **1.500.000/công** (lương vị trí) chứ không phải 2.000.000 — vì **phép năm không có lương trách nhiệm**.

### Bước 3 — Chuyên cần + Phụ cấp

```
số_ngày_nghỉ = max(0 ; 24 − (23,0 + 0)) = 1,0          ← 1 ngày nghỉ KHÔNG lương
tỷ_lệ = max(0 ; 1 − 0,5 × 1,0) = 0,5
chuyên_cần = 500.000 × 0,5 = 250.000                    ← mất 50% vì nghỉ 1 ngày

phụ_cấp = 0 + 500.000 (thâm niên) + 500.000 (điện thoại) = 1.000.000
khoản_thu_phát_sinh_kỳ = 10.000.000 (thưởng doanh số)
```

### Bước 4 — Cơm ca

```
cơm_ca = 25.000 × 21 ngày ĐI LÀM = 525.000
```
> 2 ngày nghỉ phép **không có suất cơm ca** — chỉ đếm ngày present.

### Bước 5 — GROSS trước phạt

| Khoản | Số tiền |
|---|---|
| Lương theo công (gồm 3.000.000 ngày phép) | 45.000.000 |
| Chuyên cần | 250.000 |
| Phụ cấp | 1.000.000 |
| Khoán / Tăng ca / `night_pay` / Premium đêm / Thưởng khác | 0 |
| Cơm ca | 525.000 |
| Phụ cấp ca | 0 |
| Thưởng chi tiết + điều chỉnh | 0 |
| Khoản phát sinh kỳ (thưởng doanh số) | 10.000.000 |
| **GROSS TRƯỚC PHẠT** | **56.775.000** |

### Bước 6 — BHXH + Đoàn phí

```
ngày_không_lương = max(0 ; 24 − 23,0 − 0) = 1,0  <  14  ⇒ ĐÓNG bình thường
insurance_base = lương vị trí = 36.000.000     ← KHÔNG phải 48.000.000
gốc_BH   = min(36.000.000 ; 50.600.000)  = 36.000.000
gốc_BHTN = min(36.000.000 ; 106.200.000) = 36.000.000

bhxh = 36.000.000 × 9,5%  +  36.000.000 × 1%
     =     3.420.000      +      360.000     =  3.780.000

đoàn_phí = 36.000.000 × 0,5% = 180.000     ← tính trên GỐC, không kẹp trần
```

### Bước 7 — Thuế TNCN

```
thu_nhập_miễn_thuế = 0 + 0 + 0 + 0 (khoản danh mục đều CHỊU thuế) + 525.000 (cơm ca)
                   = 525.000

thu_nhập_chịu_thuế = 56.775.000 − 525.000 = 56.250.000

giảm_trừ = 15.500.000 + 6.200.000 × 2 = 15.500.000 + 12.400.000 = 27.900.000

thu_nhập_tính_thuế = max(0 ; 56.250.000 − 3.780.000 − 27.900.000)
                   = 56.250.000 − 3.780.000 = 52.470.000
                   − 27.900.000              = 24.570.000
```

**Tra biểu 5 bậc (cộng từng bậc):**

| Bậc | Phần thu nhập | Thuế suất | Thuế |
|---|---|---|---|
| 1 | 10.000.000 | 5% | 500.000 |
| 2 | 24.570.000 − 10.000.000 = 14.570.000 | 10% | 1.457.000 |
| 3–5 | 0 | — | 0 |
| | | **TỔNG** | **1.957.000 đ** |

### Bước 8 — Phạt + trần

```
tổng_phạt_thô = 0  ⇒  phạt_hiệu_lực = 0
GROSS = max(0 ; 56.775.000 − 0) = 56.775.000
```

### Bước 9 — THỰC NHẬN

| Dòng | Số tiền |
|---|---|
| GROSS | 56.775.000 |
| − BHXH+BHYT+BHTN | − 3.780.000 |
| − Đoàn phí | − 180.000 |
| − Thuế TNCN | − 1.957.000 |
| − Tạm ứng | − 0 |
| − **Lương đợt 1 đã chi** | − 15.000.000 |
| − Khoản trừ danh mục (đồng phục) | − 400.000 |
| **THỰC NHẬN ĐỢT 2** | **35.458.000 đ** |

*Kiểm:* 56.775.000 − 3.780.000 = 52.995.000 → − 180.000 = 52.815.000 → − 1.957.000 = 50.858.000 → − 15.000.000 = 35.858.000 → − 400.000 = **35.458.000** ✓

**Ba điểm cần giải thích cho NV nếu bị hỏi:**
1. Nghỉ **1 ngày không lương** làm mất **50% chuyên cần** (250.000đ), không phải mất 1/24.
2. Mức đóng BH tính trên **36.000.000** (lương vị trí), không phải 48.000.000 — nên số BH thấp hơn kỳ vọng.
3. Cột "Trừ" trên phiếu **không có dòng nào tên "khấu trừ danh mục tổng"** — 400.000đ đồng phục hiện thành **một dòng riêng** trong danh sách khoản.

---

# 13. NHỮNG CHỖ ENGINE ĐANG LÀM KHÁC THÔNG LỆ — PHẢI BIẾT MÀ ĐỪNG SỬA BỪA

Đây là **quyết định đã chốt**, không phải bug. Sửa mà không hỏi chủ là làm sai bảng lương.

| # | Chỗ khác | Thông lệ / Luật | Engine đang làm | Lý do & rủi ro | Neo |
|---|---|---|---|---|---|
| 1 | **Miễn TNCN toàn bộ tiền tăng ca** | ✅ **ĐÚNG LUẬT** — Luật TNCN 109/2025 K8 Đ4 đã XOÁ cụm "phần trả cao hơn"; NĐ 253/2026 Đ26 chỉ đánh thuế phần **VƯỢT MỨC** quy định | Miễn toàn bộ tiền tăng ca | Không còn là rủi ro. ⚠️ Còn thiếu: chưa đếm trần 40h/tháng nên phần VƯỢT trần vẫn được miễn oan | `payroll_service.py` `_auto_pit` |
| 1b | **Tiền ngày off1x CHỊU thuế** (sửa 17/08/2026, mg 0205) | Trả đúng 1×, không hệ số ⇒ là lương ngày thường, không có phần "trả cao hơn" để miễn | Cộng ngược vào thu nhập chịu thuế qua tham số `ot_taxable`; cột `payroll_lines.off1x_pay` | Kế toán chốt 17/08/2026: *"lương thuế chỉ 1 công bình thường"*. Tiền vẫn TRẢ ĐỦ, chỉ đổi phân loại thuế. Test: `test_off1x_chiu_thue_khong_duoc_mien` | `payroll_service.py` `_compute` |
| 2 | **Cơm ca miễn thuế KHÔNG trần 730.000đ/tháng** | Luật trần 730.000đ/tháng cho tiền ăn giữa ca | Miễn toàn bộ | Chốt 04/08/2026. Rủi ro đã ghi ở `docs/prd-thu-nhap-chiu-thue.md §7`. **Muốn áp trần phải sửa code** | `payroll_service.py:928-934` |
| 3 | **Hệ số thử việc 0,80** | Điều 26 BLLĐ tối thiểu **85%** | Mặc định 0,80 | Là **số cấu hình** — sửa bằng màn Cấu hình lương, **KHÔNG sửa code** | `models/payroll.py:102-104` |
| 3b | **Trạng thái “Hết thử việc · chờ xác nhận” VẪN ăn tiền thử việc** (thêm 22/08/2026) | Điều 27 BLLĐ: hết thử việc mà **vẫn làm tiếp** thì đã là chính thức ⇒ đáng lẽ hưởng 100% từ ngày hết hạn | Máy tự đổi trạng thái khi qua Ngày hết thử việc, nhưng `is_probation` vẫn TRUE ⇒ vẫn 80%, vẫn không đóng BHXH, vẫn không trừ đoàn phí. Chỉ HCNS bấm **“Chuyển chính thức”** mới lên nguyên mức | ⚠️ **Chủ chốt 22/08/2026, đã được cảnh báo rủi ro trước khi chọn.** Lý do chủ nêu: chính thức hay không là quyết định của HCNS, máy không được tự quyết. **Rủi ro: trả THIẾU 20% kể từ ngày hết hạn cho tới ngày bấm** — càng để lâu càng nhiều. **ĐỪNG tự “sửa cho đúng luật”** — hỏi chủ trước. Test canh: `test_HET_THU_VIEC_cho_xac_nhan_van_an_tien_THU_VIEC` | `payroll_service._compute` chỗ `is_probation` |
| 4 | **Mức đóng BH KHÔNG prorate theo công** | Thông lệ nhiều nơi tính theo ngày công thực | Đóng trên **FULL lương vị trí** dù đi làm 3/26 công (trừ khi rơi luật ≥14 ngày) | Đúng QĐ 595 | `payroll_service.py:1004-1012` |
| ~~5~~ | ~~**Mức đóng BH chỉ bám `lương vị trí`**~~ — ❌ **KHÔNG CÒN ĐÚNG** | — | Mức đóng BH = **lương cơ bản + lương trách nhiệm** (`monthly`) | Chủ **ĐẢO 12/08/2026**, đối chiếu bảng lương thật: BH 1.102.080 ÷ 10,5% = 10.496.000 = mức nền đầy đủ; đoàn phí 52.480 ÷ 0,5% ra cùng số. ⚠️ Nhãn ô FE *"Lương cơ bản (đóng BH)"* là tàn dư của chốt cũ — đã sửa 17/08/2026 | `payroll_service.py` nhánh `else` của BH |
| ~~6~~ | ~~**Ngày phép năm chỉ trả LƯƠNG VỊ TRÍ**~~ — ✅ **ĐÃ ĐẢO 17/08/2026** | Đ113: nghỉ phép hưởng **nguyên lương** | Nay trả **ĐỦ MỨC NỀN** (cơ bản + trách nhiệm), cùng đơn giá ngày đi làm | Chủ chốt 17/08/2026: *"tiền công 1 ngày là lương cơ bản cộng lương trách nhiệm"*, đảo chốt 27/07. Mỗi ngày phép thêm đúng phần trách nhiệm ÷ công chuẩn. `luong_ngay_phep` giữ tách riêng chỉ để phiếu lương giải thích, KHÔNG còn khác đơn giá. Test: `test_ngay_phep_tra_du_muc_nen` | `payroll_service.py` `_luong_cong_split` |
| 7 | **Đoàn phí tính trên gốc CHƯA kẹp trần BH** | Đoàn phí thường bám mức đóng BHXH (đã kẹp trần) | Tính trên nguyên lương vị trí | Lương 60tr: đoàn phí trên 60tr, BHXH chỉ trên 50,6tr | `payroll_service.py:1025` |
| 8 | **Đoàn phí vẫn trừ ở 2 nhánh miễn BHXH** | — | BH nơi khác / nghỉ ≥14 ngày: BHXH = 0 nhưng đoàn phí **vẫn trừ** | Cố ý, ghi rõ ở `:980-982` | `payroll_service.py:979-1003` |
| 9 | **Đoàn phí CÓ giảm thu nhập TÍNH thuế** | TT 111/2013 Đ9 **KHÔNG** liệt đoàn phí vào danh sách giảm trừ | Nằm trong khối giảm trừ cùng BHXH + giảm trừ gia cảnh: `tính thuế = chịu thuế − BHXH − đoàn phí − giảm trừ` | ⚠️ **ĐẢO 12/08/2026** (trước đó không trừ). Chủ chốt theo đúng cách bảng lương công ty hạch toán — khối "Các khoản giảm trừ" trên bảng của kế toán gồm bản thân + NPT + BH + **đoàn phí**, đã dò lại số trên bảng T5/2026. **Cố ý làm khác luật, không phải nhầm.** Lưu ý phân biệt: đoàn phí **KHÔNG** giảm thu nhập **CHỊU** thuế, chỉ giảm thu nhập **TÍNH** thuế | `payroll_service.py` `_auto_pit` |
| 10 | **Công off1x trả TRỌN 1×, KHÔNG lấp trần** | — | Người làm off1x được trả trọn dù đã đủ công chuẩn | **Chủ ý, không phải bug** | `attendance_service.py:1198-1202` |
| 11 | **Phụ trội đêm CHỈ trả cho ca tích “Ca qua đêm”** | Đ98.2 + Đ106: phụ trội ≥30% căn cứ **GIỜ** rơi khung 22h–06h, **không** căn cứ nhãn ca | Ca không tích thì phút đêm bị **bỏ, trả 0đ** — vd ca 14:00–23:00 mất 60 phút đêm | ⚠️ **Chủ chốt 17/08/2026 GIỮ NGUYÊN**, sau khi đã có bản vá và test chứng minh (`assert 0.0 == 37500`). Lý do chủ nêu: quên tích là **lỗi khai ca của HCNS**. **Rủi ro: trả THIẾU lương — người lao động có quyền đòi truy lĩnh, bị đơn là CÔNG TY.** Bộ ca đang chạy chưa ca nào dính. **ĐỪNG tự sửa lại** | `attendance_service.py:1317` |
| 11 | **Dôi công không ra thêm tiền ở lương công** | Thông lệ: làm CN = 200% trên lương ngày | Chỉ trả phần chênh (2−1)=1×, vì 1× coi như đã trong lương công — **nhưng lương công đã bị trần cắt** | Đây là lệch thật với cách kế toán tính tay 200% | `payroll_service.py:822-832`, `:893-894` |
| 12 | **Cơm ca / phụ cấp ca ALL-OR-NOTHING** | Thông lệ có nơi chia theo giờ | Đủ ngưỡng ⇒ trọn suất; dưới ngưỡng ⇒ 0đ | **Cố ý không nhân tỷ lệ** | `payroll_service.py:921` |
| 13 | **Chuyên cần trừ theo bậc 0,5 ngày = −25%** | Thông lệ nhiều nơi giảm tuyến tính | Nghỉ 2 ngày mất **sạch** | Chính sách công ty | `payroll_service.py:122-127` |
| 14 | **Phạt trễ: vào trễ có dung sai, về sớm KHÔNG** | Thông lệ đối xứng | Về sớm 5 phút = 20.000đ; vào trễ 5 phút = 0đ | Bất đối xứng có thật trong code | `attendance_service.py:173`, `:199` |
| 15 | **Miễn phạt chỉ trừ ĐÚNG số phút xin đơn**, không tha cả ngày | Thông lệ: có đơn là tha | Trừ đúng phút | Cố ý — nếu không ai cũng xin 5 phút để thoát phạt | `attendance_service.py:1217` |
| 16 | **Có đơn giờ giữ chuyên cần nhưng VẪN MẤT tiền công** | Thường gộp làm một | Hai thứ tách nhau | `excused_cong` chỉ nuôi chuyên cần | `payroll_service.py:833-837` |
| 17 | **Trừ lỗi khoán ăn vào room 30% dù đã trừ trong tiền khoán** | — | Không trừ hai lần, nhưng **bào mòn trần phạt** | Cố ý gộp chung trần Đ102 | `payroll_service.py:172` |
| 18 | **Khoản trừ danh mục KHÔNG vào trần 30%** | — | Trừ thẳng vào net | Cố ý: đây là khấu trừ **thoả thuận**, không phải kỷ luật | `payroll_service.py:1057-1060` |
| 19 | **Phần phạt vượt trần BỎ, không dồn kỳ sau** | Thông lệ: treo nợ | Mất luôn | Không có sổ nợ phạt. HCNS phải tự gõ lại | `payroll_service.py:156-159` |
| 20 | **Hai sàn 0 (gross & net)** | — | Tiền thiếu **biến mất**, không ghi nợ | Cố ý để không in phiếu lương số âm | `payroll_service.py:1053`, `:1243` |
| 21 | **Tra mức lương theo NGÀY CUỐI THÁNG** | Thông lệ: chia đôi theo ngày hiệu lực | Cả tháng ăn mức MỚI | Cố ý cho đơn giản | `payroll_service.py:1154`, `:1161` |
| 22 | **Ca đêm phân loại ngày theo NGÀY VÀO CA** | Thông lệ: theo ngày lịch của từng giờ | Ca đêm 30/04 sang 01/05 vẫn tính hệ số 30/04 | Cố ý, một công thức cho mọi ca | `attendance_service.py:227-233` |
| 23 | **`khau_tru_10` so ngưỡng trên TỔNG THÁNG** | Luật diễn đạt "mỗi lần trả" | Trả 2 đợt vẫn tính một lần trên tổng | Đã biết | `payroll_service.py:463-470` |
| 24 | **`cam_ket_08` miễn VÔ ĐIỀU KIỆN, không hạn năm** | Luật đòi MST + một nơi làm + dưới ngưỡng | Bật cờ là miễn | **Rủi ro tuân thủ** — không có cảnh báo, không có hạn hiệu lực | `payroll_service.py:461-462` |
| 25 | **Không có quyết toán năm** | — | Engine chỉ tính biểu THÁNG, không cộng dồn 12 tháng, không xử lý người vào/nghỉ giữa năm | **Nói thẳng: CHƯA CÓ** | — |
| 26 | **Ảnh chụp đầu việc khoán ghim cứng** | — | Xưởng lên giá sau **không được xê dịch** lệnh đã phát | Cố ý | `piece_work_service.py:48-56` |

---

# 14. LỖI ĐÃ BIẾT — PHẢI SỬA (KHÔNG PHẢI CHÍNH SÁCH)

Khác hẳn Phần 13. Đây là chỗ **hai đường tính ra hai số** hoặc luật bị áp sai. Kế toán phải biết để **không tin số sau khi bấm "Sửa 1 ô"**.

| # | Lỗi | Kích hoạt khi nào | Hậu quả tiền | Bản vá đúng | Neo |
|---|---|---|---|---|---|
| **1** | **"Sửa 1 ô" với mức tháng gõ tay KHÔNG nhân hệ số thử việc** | NV **thử việc** + HCNS sửa ô mức tháng | Lương theo công bị **đội lên 1/0,8 = +25%** (vì `monthly_salary` lưu mức **TRƯỚC** hệ số) | Nhân `probation_ratio` vào `monthly_override` như `_compute` làm ở `:818` | `payroll_service.py:1465-1475` vs `:818` |
| ~~**1b**~~ | ~~**`vi_tri_rate` suy ngược từ `luong_ngay_phep / paid_leave_cong` cũ**~~ — ✅ **TỰ HẾT 17/08/2026** | ~~Sửa mức tháng cho NV có ngày phép~~ | ~~Đổi mức tháng KHÔNG đổi đơn giá ngày phép~~ | Ngày phép nay ăn CÙNG mức nền ⇒ không còn đơn giá riêng để suy ngược. Đã gỡ hẳn `vi_tri_rate` và tham số `eff_vi_tri` khỏi `_luong_cong_split` | `payroll_service.py` `update_line` |
| **2** | **Trần phạt 30% dùng HAI số thuế khác nhau** | `pit_manual = true` **VÀ** phạt chạm trần | "Tính lại" dùng **thuế TỰ TÍNH** (`:1047` truyền `pit_auto`); "Sửa 1 ô" dùng **thuế TAY** (`:1545`) ⇒ **cùng một dòng, hai nút, ra hai gross/net khác nhau** | Thống nhất: cả hai dùng số thuế **hiệu lực** | `payroll_service.py:1047` vs `:1545` |
| **3** | **"Sửa 1 ô" tính lại đoàn phí mà QUÊN kiểm cờ đoàn viên** | NV **không phải đoàn viên** + `cong_doan_rate > 0` | "Tính lại" ra 0đ; **mọi thao tác trên dòng** (sửa ô, **thêm/xoá khoản phát sinh** — vì `_recompute_line` gọi thẳng `update_line`) làm đoàn phí **sống lại** và trừ khỏi thực nhận | `ln.cong_doan = 0 if (ln.is_probation or not union_member) else ...` — mirror vế `is_union` ở `:1024-1025` | `payroll_service.py:1528-1529` vs `:1024-1025`; `:1421-1426` |
| **4** | **`insurance_base` + `bhxh` bị đóng băng** | Sửa lương vị trí ở hồ sơ, không bấm "Tính lại" | Mức đóng BH trên bảng lương **vẫn là số cũ** | Hoặc tính lại, hoặc chặn `update_line` khi mức lương đã đổi | `payroll_service.py:1428-1432` |
| **5** | **`update_pit_bracket` không validate gì** | Sửa bậc thuế trên UI | Nhập **thuế suất ÂM** vẫn lưu; **trần bậc lệch thứ tự** làm thuế cộng sai, có thể ra số âm | Validate `rate ≥ 0` + `up_to` tăng dần theo `seq` | `payroll_service.py:402-406` |
| **6** | **3 dòng BH trên phiếu lương tính lại theo tham số HIỆN TẠI** | Sửa tỷ lệ/trần BH sau khi kỳ đã chốt | Hai dòng đầu đổi số, **sai lệch dồn hết vào dòng BHTN** — có thể ra số vô lý, kể cả **ÂM** | Snapshot tỷ lệ lên dòng lương | `routers/payroll.py:204-224` |
| ~~**7**~~ | ~~**Tổ khoán mất tăng ca mà không có khoán bù**~~ — ✅ **ĐÃ SỬA 17/08/2026** | ~~Tổ nào đang bật `has_piece_work`~~ | ~~`ot_pay = 0`, mất cả premium lễ/CN và tiền off1x~~ | Chủ chốt **"Tổ khoán VẪN CÓ tăng ca"** (đảo chốt 22/07). Đã **GỠ vế `has_piece_work`** khỏi cả `ot_pay` lẫn suất cơm tăng ca, và **gỡ luật loại trừ Khoán ⟷ Tăng ca** ở `set_dept_components` + nút gạt FE. Nay chỉ còn MỘT cổng: công tắc `tang_ca` của bộ phận. Test: `test_to_khoan_VAN_CO_tang_ca` | `payroll_service.py` `_compute` |
| **8** | **`has_piece_work` hở một chiều** | Sửa cờ ở màn **Phòng ban** | Không ghi gì vào bảng khoản lương ⇒ hai nguồn sự thật lệch nhau | Đồng bộ hai chiều | `routers/rbac.py:189` |
| ~~**10**~~ | ~~**Trần công nuốt phần gốc 1× của ngày lễ/CN**~~ — ✅ **ĐÃ SỬA 17/08/2026 (mg 0204)** | ~~`công thực > công chuẩn` + có đi làm lễ/CN~~ | ~~52/67 người có công CN trong bảng T5/2026 bị hụt tổng **34.712.346đ/tháng**; nhận 1× thay vì 2× (lễ 2× thay vì 3×)~~ | Cột `payroll_lines.special_cong` + `_luong_cong_split(special_cong=…)` cho công lễ/CN **ra ngoài trần**; `update_line` đọc cột để hai đường tính ra cùng số | `payroll_service.py` `_luong_cong_split` · `:1584` |
| **9** | **Thưởng/phạt tổ trưởng theo % hàng lỗi CHƯA NỐI** | Khai bậc trên UI | **Không ra đồng nào.** Banner cảnh báo trên màn khai đang nói đúng — **đừng gỡ banner** | Nối `leader_bonus_amount` vào `PayrollService` khi có nguồn sản lượng | `piece_work_service.py:200-218` |
| **10** | **`seed_review_luong.py` import module không tồn tại** | Chạy script seed | **ImportError ngay lập tức** | Gỡ script hoặc gỡ import `production_output` | `backend/scripts/seed_review_luong.py:30`, `:39` |
| **11** | **Docstring `LatePenaltyBracket` ghi "ENGINE CHƯA áp bảng này"** | Đọc code | **LỖI THỜI** — engine đang áp thật, đọc nhầm là tưởng phạt trễ chưa chạy | Sửa docstring | `models/payroll.py:477-478` |
| **12** | **Docstring `_components_for` ghi "mặc định nhóm lương"** | Đọc code | **CHỮ CŨ CÒN SÓT** — không tồn tại mức mặc định theo nhóm lương | Sửa docstring | `payroll_service.py:512` |
| **13** | **Comment `lsx_service.py:1709` ghi "= mọi đơn giá của TỔ"** | Đọc code | Sai — còn lớp lọc whitelist công đoạn | Sửa comment | `lsx_service.py:1709` |
| **14** | **Bảng `late_penalty_brackets` không có migration** | DB prod cũ chưa ai mở màn Cấu hình lương | Bảng trống ⇒ phạt trễ trả **0đ** cho tới lần tính lương đầu tiên (lúc đó mới seed lười) | Thêm migration + seed | `payroll_service.py:416-424` |

### Nguyên tắc phòng bệnh cho đội code

> `_compute` (`:957-960`) và `update_line` (`:1508-1515`) **PHẢI khớp 1-1**. Thêm bất kỳ số hạng thu/chi nào vào một chỗ mà quên chỗ kia = **"Sửa 1 ô" ăn mất tiền người lao động trong im lặng**, bảng lương vẫn trông bình thường.
> Bệnh này **đã tái phát 3 lần** (với `ca_mien`, `khoan_defect`, `component_deduct`). Lần thứ 4 sẽ đến nếu không có test canh.

---

# 15. BẢNG TRA THAM SỐ CẤU HÌNH

## 15.1. Tham số khai ở màn **Cấu hình lương** (`payroll_params`)

| Tham số | Mặc định | Ý nghĩa | Ghi chú |
|---|---|---|---|
| `standard_cong_default` | 26 | Công chuẩn dự phòng | **Ô đã GỠ khỏi màn**, API vẫn nhận |
| `standard_hours_per_day` | 8 | Giờ chuẩn/ngày → đơn giá giờ | API chặn ≤ 0; code ép `or 8` |
| `probation_ratio` | **0,80** | Hệ số thử việc | Luật tối thiểu 85% |
| `bhxh_rate` / `bhyt_rate` / `bhtn_rate` | 0,08 / 0,015 / 0,01 | **NLĐ** — tổng 10,5% | Trừ thật |
| `bhxh_rate_er` / `bhyt_rate_er` / `bhtn_rate_er` | 0,175 / 0,03 / 0,01 | Chủ SDLĐ | ⚠️ **DORMANT** — engine không đọc |
| `tnld_bnn_rate` | 0,005 | TNLĐ-BNN chủ chịu | ⚠️ **DORMANT** — chỉ FE hiển thị |
| `bh_base_cap` | **50.600.000** | Trần BHXH + BHYT | 0 = **TẮT trần** |
| `bhtn_base_cap` | **106.200.000** | Trần BHTN (riêng) | 0 = **TẮT trần** |
| `bhxh_mien_tu_so_ngay` | **14** | Nghỉ không lương ≥ N ngày ⇒ không đóng BHXH | ⚠️ **0 = TẮT LUẬT**, không phải miễn cả xưởng |
| `cong_doan_rate` | **0** | Đoàn phí | Chủ phải tự khai (mẫu 0,005) |
| `deduction_self` | **15.500.000** | Giảm trừ bản thân/tháng | NQ 110/2025 |
| `deduction_dependent` | **6.200.000** | Giảm trừ mỗi NPT/tháng | NQ 110/2025 |
| `pit_flat_rate` | 0,10 | Khấu trừ phẳng nhánh `khau_tru_10` | Khai được ở màn Cấu hình lương từ 08/08/2026. 0 ⇒ thuế 0 (màn cảnh báo mềm, vẫn lưu) |
| `pit_flat_threshold` | **2.000.000** | Ngưỡng khấu trừ 10% | Khai được ở màn Cấu hình lương từ 08/08/2026. 0 ⇒ khấu trừ từ đồng đầu |
| `ot_multiplier` | 1,5 | OT ngày thường | 1 ≤ x ≤ 5 |
| `ot_multiplier_restday` | 2,0 | OT ngày nghỉ tuần | 1 ≤ x ≤ 5 |
| `ot_multiplier_holiday` | 3,0 | OT ngày lễ | 1 ≤ x ≤ 5 |
| `restday_work_multiplier` | 2,0 | LÀM nguyên công ngày nghỉ tuần | Chỉ trả phần chênh |
| `holiday_work_multiplier` | 3,0 | LÀM nguyên công ngày lễ | Chỉ trả phần chênh |
| `night_pct` | 0,30 | Phần đêm của **tăng ca đêm** | Khác `night_multiplier` |
| `ot_night_extra_pct` | 0,20 | Nhân với hệ số LÀM loại ngày | |
| `phu_cap_ca_min_cong` | **0,5** | Ngưỡng công để hưởng cơm ca / phụ cấp ca | ⚠️ Khai 0 ⇒ ngày treo cũng có suất |
| `phat_cap_pct` | **0,30** | Trần khấu trừ Điều 102 | ⚠️ **0 = TẮT TRẦN** |
| `chuyen_can_default` | — | ⚠️ **DORMANT** | Mức chuyên cần chỉ khai ở hồ sơ NV |
| `advance_max_pct` | 0,10 | ⚠️ **DORMANT** — trần tạm ứng đã gỡ 24/07/2026 | |

## 15.2. Tham số khai ở nơi KHÁC

| Tham số | Nơi khai | Mặc định | Ý nghĩa |
|---|---|---|---|
| `work_shifts.meal_allowance` | Danh mục **Ca làm việc** | 25.000 | Cơm ca / ngày |
| `work_shifts.shift_allowance` | Danh mục **Ca làm việc** | 50.000 | Phụ cấp ca / ngày |
| `work_shifts.night_multiplier` | Danh mục **Ca làm việc** | **1,3** | Hệ số giờ đêm **trong ca** (chỉ ca qua đêm) |
| `work_shifts.grace_minutes` | Danh mục **Ca làm việc** | 5 | Dung sai vào trễ (**không** áp cho về sớm) |
| `departments.has_piece_work` | Phòng ban **hoặc** Cấu hình lương | false | ⚠️ Bật = **cắt tăng ca cả tổ** |
| `department_salary_components.is_enabled` | Cấu hình lương theo tổ | (chưa khai = BẬT) | Công tắc `chuyen_can`, `tang_ca`, `luong_khoan` |
| `employee_salaries.luong_vi_tri` | Hồ sơ lương NV | — | Gốc lương **và** gốc đóng BH |
| `employee_salaries.luong_trach_nhiem` | Hồ sơ lương NV | — | Vào mức nền, **KHÔNG** vào gốc BH, **KHÔNG** vào ngày phép |
| `employee_salaries.chuyen_can` | Hồ sơ lương NV | 0 | **NƠI DUY NHẤT** khai tiền chuyên cần |
| `employee_salaries.union_member` | Hồ sơ lương NV | **false** | Opt-in đoàn viên |
| `employee_salaries.apply_self_deduction` | Hồ sơ lương NV | **true** | Tắt = mất 15.500.000đ giảm trừ |
| `employee_salaries.insurance_elsewhere` | Hồ sơ lương NV | false | BH đóng nơi khác ⇒ BHXH = 0, đoàn phí **vẫn trừ** |
| `employees.pit_mode` | Hồ sơ NV | `luy_tien` | 3 chế độ thuế |
| `employees.dependents_count` | Hồ sơ NV | 0 | ⚠️ **Không kiểm tra hồ sơ đăng ký NPT** |
| `employee_salaries.commission_pct` | Hồ sơ lương NV | 0 | ⚠️ **CHỈ KHAI — engine KHÔNG đọc** |
| `employee_salaries.insurance_base` | Hồ sơ lương NV | — | ⚠️ **DORMANT** — engine không đọc |
| `employee_salaries.phu_cap_ca` | Hồ sơ lương NV | — | ⚠️ **NGƯNG từ 03/08/2026** |
| `payroll_components.in_insurance_base` | Danh mục khoản lương | — | ⚠️ **DORMANT** — không chỗ nào đọc |
| `employee_salary_components.amount` | Hồ sơ lương NV | — | **NƠI DUY NHẤT** khai tiền khoản danh mục |
| `pit_tax_brackets` | Cấu hình lương | 5 bậc 2026 | Xoá sạch ⇒ **tự tái sinh** |
| `late_penalty_brackets` | Cấu hình lương | 4 bậc | Không có migration, seed lười |

## 15.3. Danh sách cột DORMANT / ĐÃ CHẾT — đừng khai, đừng tin

| Cột / Tham số | Nhìn thấy ở | Thực tế |
|---|---|---|
| `employee_salaries.commission_pct` | Hồ sơ lương | Khai % bao nhiêu cũng **không ra một đồng** |
| `employee_salaries.insurance_base` | Hồ sơ lương | Engine **không đọc**, mức đóng luôn = lương vị trí |
| `employee_salaries.phu_cap_ca` | Hồ sơ lương | `night_pay` ép = 0 từ 03/08/2026 |
| `payroll_params.bhxh_rate_er` / `bhyt_rate_er` / `bhtn_rate_er` | Cấu hình lương | Chỉ để tham chiếu, **không nhân ra tiền** |
| `payroll_params.tnld_bnn_rate` | Cấu hình lương | Chỉ FE hiển thị cho nhóm BH nơi khác |
| `payroll_params.chuyen_can_default` | — | Không dùng |
| `payroll_params.advance_max_pct` | — | Trần tạm ứng đã gỡ |
| `payroll_components.in_insurance_base` | Danh mục khoản | Bật lên **không có tác dụng gì** |
| `piece_rates.cong_doan` | DB | **CỘT CHẾT** — luật khớp đã chuyển sang `cong_doan_dau_viec` |
| `payroll_lines.night_pay` | Phiếu lương | Luôn 0 với kỳ mới; giữ để kỳ cũ còn số |
| 6 cột thưởng cũ (`thuong_5s`, `thuong_doanh_so`, `thuong_thanh_tich`, `phep_nam`, `tra_dong_phuc`, `other_bonus`) | Phiếu lương | **Chặn ghi mới** — khai qua khoản danh mục phát sinh |
| `payroll_rules` (bậc/quy tắc lương) | DB | Đã bỏ khỏi đường tính mức nền |
| `piece_leader_bonus_brackets` / `_settings` | Màn khai | **Chưa nối** — khai không ra tiền |
| `production_outputs` | Migration cũ | **Không còn model/repo/router** |

---

## PHỤ LỤC A — Ba cột dễ nhầm nhất trên phiếu lương

| Nhìn thấy | Đừng nhầm với | Sự thật |
|---|---|---|
| **"Lương ngày phép"** (`luong_ngay_phep`) | **"Phép năm"** (`phep_nam`) | Cột đầu **tự tính, ⊂ lương theo công** — **KHÔNG cộng lại**. Cột sau là **ô gõ tay**, cộng thẳng vào gross. Trùng tên trong đầu = **cộng đôi tiền phép** |
| **"Tăng ca"** (`ot_pay`) | Tiền tăng ca thuần | Cột này còn chứa **premium làm lễ/CN** và **tiền ngày off1x 1×**. NV không tăng ca giờ nào vẫn có thể thấy tiền |
| **"Premium ca đêm"** (`night_premium_pay`) | **"Phụ cấp ca"** (`night_pay`) | Cột đầu **tự tính theo giờ, ĐANG SỐNG**. Cột sau là **số phẳng gõ tay, ĐÃ CHẾT = 0** |
| **"BHXH"** (`bhxh`) | Riêng BHXH 8% | Là **TỔNG CẢ BA**: BHXH 8% + BHYT 1,5% + BHTN 1% = 10,5% |
| **"Thu nhập chịu thuế"** | **"Thu nhập tính thuế"** | Cột đầu = **TRƯỚC** giảm trừ (chủ hỏi "tổng lương chịu thuế" là số này). Cột sau = **SAU** khi trừ BHXH + giảm trừ, là số duy nhất tra biểu thuế |
| **"Phụ cấp thâm niên"** | Một khoản riêng | Là số **"TRONG ĐÓ"** của cột Phụ cấp — **đừng cộng lại** |
| **"Trả đồng phục"** (`tra_dong_phuc`) | **"Phạt 5S/đồng phục"** (`phat_5s_dong_phuc`) | Cột đầu là khoản **THU** (cộng lương). Cột sau là khoản **PHẠT** |
| **"ĐT vượt trội"** (`dt_vuot_troi`) | Một khoản thu hồi thường | Bị xếp **chung rổ phạt kỷ luật** và **ăn vào trần 30%** |

## PHỤ LỤC B — Checklist trước khi chốt kỳ lương

**Kiểm dữ liệu đầu vào**
- [ ] Kỳ **chấm công** đã chốt chưa? (Chốt rồi thì Lương đọc snapshot — sửa chấm công sau đó không đổi số)
- [ ] Công chuẩn `std` tháng này bằng bao nhiêu? Có khớp lịch không? (**≠ 26 là bình thường**)
- [ ] Ngày lễ / ngày `off1x` / ngày làm bù đã khai đủ vào Lịch chung chưa?
- [ ] Có tổ nào đang bật `has_piece_work` không? ⇒ **Cả tổ đó đang mất tăng ca mà không có khoán bù** (lỗi #7 Phần 14)

**Kiểm hồ sơ**
- [ ] NV mới có khai `luong_vi_tri` chưa? (Chỉ khai `base_amount` ⇒ **BHXH = 0 và đoàn phí = 0 âm thầm**)
- [ ] NV đổi lương giữa tháng: nhớ **cả tháng ăn mức MỚI**, không chia đôi
- [ ] Cờ `union_member` / `apply_self_deduction` / `insurance_elsewhere` / `pit_mode` đã đúng chưa?
- [ ] `dependents_count` có chứng từ đăng ký NPT không? (**Hệ thống không kiểm**)

**Kiểm phiếu**
- [ ] Phiếu **tăng ca** đã duyệt đủ chưa? (Không phiếu ⇒ **0đ tăng ca** dù có bấm máy)
- [ ] Phiếu **tạm ứng / lương đợt 1** khai đúng `period_year/month` chưa? (**Khai nhầm kỳ = tiền đã đưa mà lương không trừ, không cảnh báo**)
- [ ] Phiếu ứng nào mới duyệt/mới huỷ sau lần "Tính lại" gần nhất? ⇒ **Phải bấm "Tính lại"**, "Sửa 1 ô" không đọc lại

**Sau khi bấm "Tính lại"**
- [ ] Dòng nào có `pit_manual` = true? ⇒ Thuế **không đổi** dù tính lại; và **trần phạt của dòng đó khác nhau giữa hai nút** (lỗi #2)
- [ ] Dòng nào có `di_tre_manual` = true? ⇒ Phạt trễ không tự tính lại
- [ ] NV **không phải đoàn viên** mà cột đoàn phí > 0? ⇒ Ai đó đã bấm "Sửa 1 ô" trên dòng đó (lỗi #3) — **bấm "Tính lại" để xoá về 0**
- [ ] NV **thử việc** mà HCNS có sửa ô mức tháng? ⇒ **Lương công đội +25%** (lỗi #1) — kiểm tay
- [ ] Cột "Tăng ca" có tiền mà NV không tăng ca giờ nào? ⇒ Là premium lễ/CN hoặc tiền ngày off1x — **đúng**
- [ ] Tổng các cột phạt ≠ (gross_trước_phạt − gross)? ⇒ Phạt **đã chạm trần 30%**, phần vượt **mất luôn**, không dồn kỳ sau

**Trước khi chi**
- [ ] Có dòng nào `net_pay = 0` mà gross > 0? ⇒ **Sàn 0 đã nuốt tiền**, hệ thống **không ghi nợ** — kiểm tay trước khi giải thích với NLĐ
- [ ] Có dòng nào `thu_nhap_chiu_thue > gross`? ⇒ **Đúng**, vì thuế tính trên gross **trước** phạt

---

*Hết tài liệu. Mọi thay đổi công thức phải cập nhật đồng thời `_compute` và `update_line`, cập nhật `docs/DB_SCHEMA.md` nếu thêm cột, và viết migration vào `db_migrations.py` — `create_all` chỉ TẠO bảng, KHÔNG ALTER.*
