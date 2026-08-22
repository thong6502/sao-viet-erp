# PRD v2 — Màn "Cấu hình lương" (3 tab): gom chính sách lương về một chỗ

> ## ⚠️ CẬP NHẬT 2026-07-20 (v2.2) — CHỦ BỎ HẲN BẬC LƯƠNG + lương vị trí = mức đóng BH.
>
> Chủ đảo tiếp phần bậc lương. **ĐỌC TRƯỚC — đừng dựng lại cái đã gỡ:**
> 1. **BỎ HẲN hệ thống bậc lương.** Bậc chỉ để phân nhóm, KHÔNG quyết định tiền (bảng T05: cùng
>    bậc 2 mà người 20tr người 10,5tr). Bậc về lại free-text `employees.job_grade` — hệ thống
>    KHÔNG quản bậc. Đã DROP `department_salary_rows` + mọi endpoint salary-rows + `pay_grade_row_id`
>    + khung `luong_min/max` + `promotion_condition` + `salary_range_warning` + `reclassify_salary`
>    + `departments.salary_policy_note`. Tab 2 còn **4 khoản**: `kpi` · `chuyen_can` · `luong_khoan` · `tang_ca`.
> 2. **Lương vị trí = lương cơ bản = MỨC ĐÓNG BH.** Engine `insurance_base = luong_vi_tri` (CHỈ
>    vị trí, KHÔNG +trách nhiệm; bỏ field `insurance_base` riêng — để dormant). Số thật T05:
>    vị trí 6.841.000 → BHXH 8% = 547.280. Mức nền = `luong_vi_tri + luong_trach_nhiem` (1 nguồn duy nhất).
> 3. **Bỏ `phu_cap_trach_nhiem` khai tay** (trùng `luong_trach_nhiem` trong mức nền). Còn 3 khoản
>    khai tay theo NV: `phu_cap_ca` (→ `night_pay`, miễn TNCN) · `phu_cap_tham_nien` · `allowance` (khác).
> Migration **`0092_luong_bo_bac_luong`**. `salary_rate_rules` + `/api/luong/rules` + `base_amount`
> giữ DORMANT (endpoint còn nhưng không resolve ra tiền).

> ## ⚠️ CẬP NHẬT 2026-07-20 (v2.1) — CHỦ ĐẢO NGƯỢC C4 + C5 + C6. ĐỌC TRƯỚC KHI LÀM.
>
> Chủ soi màn đã dựng rồi chốt lại: *"Đơn giá ca — bỏ đi, vì khi khai lương rồi thì nó tự chia"*
> và *"Phụ cấp ca, Phụ cấp trách nhiệm, Phụ cấp thâm niên — cho nó khai tay đi, hệ thống không
> cần tính toán, khi nào sửa thì nó sửa"*. Khai theo **TỪNG NGƯỜI** (màn Lương nhân viên), **một
> số cố định** dùng mọi tháng.
>
> | Quyết định | Trạng thái THẬT của code |
> |---|---|
> | **C1** bậc = khung sàn–trần, cảnh báo mềm | ✅ ĐANG DÙNG |
> | **C2** gõ riêng từng ô (vị trí · trách nhiệm) | ✅ ĐANG DÙNG |
> | **C3** chuyên cần TRỪ DẦN, mức khai theo TỔ | ✅ ĐANG DÙNG |
> | **C4** ca đêm = đơn giá của tổ × số lượt | ❌ **ĐÃ BỎ** — phụ cấp ca là 1 số KHAI TAY của NV (`employee_salaries.phu_cap_ca` → `payroll_lines.night_pay`). Bảng `department_shift_rates` + `payroll_line_shifts` đã DROP (migration 0090). §1.4 · §5.3 · §6.1 chỉ còn giá trị lịch sử. |
> | **C5** engine tự tính thâm niên (mức × số kỳ 6 tháng) / cơm (đ/suất × suất) | ❌ **ĐÃ BỎ** — thâm niên + trách nhiệm cũng là số KHAI TAY của NV; hệ thống KHÔNG tính toán gì. |
> | **C6** công ty định nghĩa LOẠI phụ cấp, tổ khai mức | ❌ **ĐÃ BỎ** — bảng `allowance_types` đã DROP (không còn điều khiển gì). Chuỗi ghi đè rút còn **2 cấp: NV → tổ**. |
>
> **Tab 2 giờ chỉ còn 5 khoản theo tổ:** `luong_bac` · `kpi` · `chuyen_can` · `luong_khoan` ·
> `tang_ca`. Bốn khoản phụ cấp (ca · trách nhiệm · thâm niên · **khác**) nằm ở `employee_salaries`,
> engine cộng **PHẲNG**: không prorate theo công, không vào gốc tính tăng ca.
> **Nghiệm thu §12 mục 3 và 6 (cơm 27.000×5, thâm niên tự tính) KHÔNG còn áp dụng**; các mục
> còn lại (đặc biệt **mục 2 — chuyên cần 225.000/150.000/0/250.000**) vẫn giữ nguyên.

> **Trạng thái:** Thiết kế đã chốt 6 quyết định nền · Code v1 đã dựng nhưng **phải sửa theo doc này**.
> **Tạo:** 2026-07-20 (v1) · **Viết lại:** 2026-07-20 (v2) · **Đảo ngược C4/C5/C6:** 2026-07-20 (v2.1).
> **Căn cứ mới của v2 — BẢNG LƯƠNG THẬT của nhà máy** (chủ cung cấp):
> `BẢNG LƯƠNG T05.2026 (duyệt).xlsx` · `LƯƠNG CHỈNH NĂM 2026.xlsx` · `LƯƠNG KHOÁN CÁC BỘ PHẬN.xlsx`.
> **Phạm vi:** MỘT màn cấu hình 3 tab. Không đụng màn Hồ sơ nhân sự, phiếu lương, chấm công.
> **Liên quan:** `docs/spec-luong.md` · `docs/redesign-hcns.md` (Đ3/Đ4 chưa triển khai, PRD này không đụng).

---

## 0. Quyết định nền đã chốt (decision log)

| # | Vấn đề | Quyết định |
|---|---|---|
| **C1** | v1 cho **bậc lương áp tiền cứng** → cùng bậc bắt buộc cùng lương. Sai với thực tế: mỗi người một hợp đồng. | **Bậc = KHUNG sàn–trần, KHÔNG áp tiền.** NV được gán bậc **VÀ** có mức hợp đồng riêng. Ngoài khung chỉ **cảnh báo mềm**, không chặn. Bậc dùng để: xếp loại · xét thăng bậc · đếm số NV · gợi ý mức khi khai người mới. |
| **C2** | Có nên tự tách 40/20/40 từ một số tổng? | **Giữ cách nhập hiện tại — gõ riêng từng ô** (lương vị trí · trách nhiệm · phụ cấp). Không tự tách. |
| **C3** | Engine đang tính chuyên cần **được-ăn-cả-ngã-về-không**; bảng lương thật thì **trừ dần**. | **Trừ dần:** nghỉ 0,5 ngày −25% · nghỉ 1 ngày −50% · nghỉ ≥2 ngày mất hết.<br>Công thức: `tỷ lệ = max(0, 1 − 0,5 × số ngày nghỉ)`. |
| **C4** | Engine tính phụ cấp ca đêm theo **% đơn giá công/ngày**; bảng lương thật trả theo **đơn giá cố định × số lượt**. | **Đơn giá × số lượt**, bảng đơn giá khai **theo tổ**. Bỏ cách tính %. |
| **C5** | Phụ cấp **thâm niên** và **cơm** có trong danh mục nhưng **engine không đọc** → UI ma. | **Bổ sung engine tính thật cả hai.** Thâm niên = mức/6 tháng × số kỳ 6 tháng tính từ ngày vào làm. Cơm = đ/suất × số suất. |
| **C6** | v1 để **công ty đặt mức mặc định**, tổ ghi đè. Thực tế mỗi tổ một khác nên gần như phải ghi đè hết. | **TỔ là nơi khai chính.** Cấp công ty **chỉ định nghĩa LOẠI phụ cấp + đơn vị tính**, KHÔNG áp mức tiền chung. NV vẫn ghi đè được. |

> **Ngoại lệ của C6:** BHXH/BHYT/BHTN · thuế TNCN · công chuẩn · giờ công/ngày · hệ số tăng ca · % thử việc
> **vẫn khai ở cấp công ty** — vì luật bắt buộc thống nhất toàn doanh nghiệp.

---

## 1. Căn cứ thực tế (đọc từ bảng lương đang trả)

### 1.1 Bậc thợ KHÔNG quyết định tiền — bằng chứng
Sheet **TỔ IN** của `LƯƠNG CHỈNH NĂM 2026` ghi bậc thợ ở cột riêng:

| Bậc thợ | Nhân viên | Tổng lương 2026 |
|---|---|---|
| **2** | Trần Y Băng | **20.000.000** |
| **2** | Nguyễn Hữu Đang | **10.500.000** |
| **4** | Nguyễn Văn Tuấn | 14.500.000 |
| **4** | Sẩm Chi Minh | 22.000.000 |
| **5** | Huỳnh Sĩ Đan | 14.500.000 |
| **5** | Huỳnh Quốc Huy | 22.000.000 |

Cùng bậc chênh nhau **gấp đôi** → bậc chỉ là **phân loại tay nghề**, tiền theo **hợp đồng từng người**. Đây là căn cứ của **C1**.

### 1.2 Cấu trúc lương thực tế: 3 ô + chuyên cần riêng
Mọi dòng bảng 2026 đều theo tỷ lệ **vị trí 40% · trách nhiệm 20% · phụ cấp 40%**:

| Nhân viên | Lương vị trí | Trách nhiệm | Phụ cấp | Tổng |
|---|---|---|---|---|
| Lê Quang Sơn (TGĐ) | 16.000.000 | 8.000.000 | 16.000.000 | 40.000.000 |
| Võ Duy Khánh (TT-IN) | 10.000.000 | 5.000.000 | 10.000.000 | 25.000.000 |
| Lê Thị Mai (TT-CẮT) | 5.600.000 | 2.800.000 | 5.600.000 | 14.000.000 |

**Chuyên cần nằm NGOÀI tổng này** (300.000 phổ thông · 500.000 quản lý cấp cao).
Tỷ lệ 40/20/40 là **thói quen khai**, không phải luật hệ thống — nên **C2 giữ gõ tay từng ô**.

### 1.3 Chuyên cần trừ dần — bằng chứng
Sheet **BL CT** (bảng lương T05.2026), công chuẩn 26:

| Nhân viên | Công | Chuyên cần nhận | Mức chuẩn | Tỷ lệ |
|---|---|---|---|---|
| Phạm Thị Ánh | 26 | 300.000 | 300.000 | 100% |
| Đoàn Hồng Hiệp | 25,5 | **225.000** | 300.000 | **75%** |
| Phan Thị Huệ | 25 | **150.000** | 300.000 | **50%** |
| Nguyễn Thị Ninh | 25 | **250.000** | 500.000 | **50%** |
| Trịnh Khắc Thịnh | 23 | **0** | 300.000 | **0%** |

Khớp đúng công thức của **C3**.

### 1.4 Ca đêm / cơm ca là đơn giá cố định — bằng chứng
Sheet **BL CT** hàng 5 khai đơn giá: **ca tới sáng 125.000** · **tài xế trước 6h 50.000** ·
**ca đêm 77.000** · **cơm 21h 27.000**.
Phan Thị Huệ ăn **5 suất cơm 21h** → thành tiền **135.000** = 27.000 × 5. Đây là căn cứ của **C4**.

### 1.5 Những chỗ engine ĐANG ĐÚNG (giữ nguyên)
- **Lương đóng BHXH là số khai riêng**, không suy từ lương vị trí (Phan Thị Huệ: BHXH 6.841.000 > vị trí 5.400.000).
  Engine đã có `insurance_base` ✓
- **BHXH 8%** trên mức đóng: 6.841.000 × 8% = 547.280 ✓
- **Công đoàn 0,5%** trên mức đóng: 6.841.000 × 0,5% = 34.205 ✓
- Công chuẩn ĐỘNG theo lịch từng tháng (không còn cố định 26) ✓ · tăng ca cộng thêm ngoài tổng lương ✓

---

## 2. Vấn đề đang có (vì sao làm màn này)

Cấu hình lương **rải 5 chỗ, trùng lặp** — không ai biết phải sửa ở đâu:

| Nơi | Đang khai gì |
|---|---|
| Phòng ban → tab Lương | `department_salary_rows`: tên mức, cách áp, lương vị trí, lương trách nhiệm |
| Lương → "Quy tắc lương" | 16/18 tham số chung + biểu thuế TNCN (tên tab sai — không còn quy tắc nào) |
| Lương → Lương nhân viên | mức · phụ cấp · chuyên cần · mức đóng BH **theo từng người** |
| Hồ sơ NV → Lương & BHXH | `payroll_group`, `pay_grade_key` — **đã vô dụng** |
| **Chỉ trong DB** | `restday_work_multiplier`, `holiday_work_multiplier` — không có ô nhập |

**Bốn bệnh:**
- **B1 — Chuyên cần khai 3 nơi**, và engine còn lệch: nhánh nhập tay dùng mức mặc định chung, nhánh theo tổ dùng mức riêng → hai người khai cùng kiểu ra hai kết quả.
- **B2 — Phụ cấp 2 nơi, 1 nơi chết:** `department_salary_rows.phu_cap`/`.chuyen_can` engine **không đọc**; phụ cấp thật gộp thành **một số** ở `employee_salaries.allowance`, không tách được loại.
- **B3 — "Nhóm lương / Bậc lương" ở Hồ sơ NV là code chết** nhưng vẫn bắt người dùng chọn.
- **B4 — 2 tham số chỉ sửa được bằng tay trong DB.**

---

## 3. Nguyên tắc thiết kế

- **N1 — Gộp, không dựng màn mới.** Tab "Quy tắc lương" → **"Cấu hình lương"**, 3 tab con.
- **N2 — Một khoản tiền chỉ có MỘT nơi khai.**
- **N3 — Ghi đè: TỔ là chính → NV ghi đè.** Công ty chỉ định nghĩa loại (C6).
- **N4 — Không hồi tố.** Sửa cấu hình chỉ ảnh hưởng kỳ **draft**; kỳ đã chốt/đã chi giữ nguyên số.
- **N5 — Không dạy sai.** Dải công thức trên màn phải phản ánh ĐÚNG engine.
- **N6 — Khớp bảng lương đang trả.** Mọi thay đổi engine phải tái lập được số trong `BẢNG LƯƠNG T05.2026`.

**Quyền:** `luong:view_salary` được xem · `luong:update` được xem và sửa · `luong:read` riêng lẻ **không được xem cấu hình**. Nhân viên vẫn vào được **Phiếu lương của tôi** và **Tạm ứng của tôi** mà không cần quyền xem cấu hình.

---

## 4. Tab 1 — Bậc lương & KPI

**Chip chọn phòng/tổ** phía trên (nguồn `meta.departments`).

**Bảng thang bậc của tổ đang chọn:**

| Cột | Nguồn | Ghi chú |
|---|---|---|
| **Bậc** | `sort_order` | 1, 2, 3… — sửa được |
| **Tên mức** | `label` | "Thợ bậc 1", "Tổ trưởng"… |
| **Khung lương** | **`luong_min` – `luong_max`** (MỚI) | ⚠️ **thay cho 1 số cứng**. Vd bậc 2: 10.000.000 – 20.000.000 |
| **Hệ số** | tự tính, read-only | giữa khung bậc n ÷ giữa khung bậc thấp nhất, 2 số lẻ |
| **Điều kiện thăng bậc** | `promotion_condition` (MỚI) | Văn bản mô tả, vd "≥ 48 tháng · kèm phụ máy" |
| **Số NV** | tự đếm, read-only | số NV đang gán bậc này |
| *(thao tác)* | | Sửa · Xóa (chặn xóa khi Số NV > 0) |

- `+ Thêm bậc` · ô **ghi chú chính sách** của tổ.
- **Điều kiện thăng bậc là VĂN BẢN** — hệ thống không tự thăng bậc, không tự nhắc (giai đoạn này).
- **Khung KHÔNG áp tiền.** Mức thật của từng NV khai ở **Lương nhân viên**; nếu mức nằm ngoài khung của bậc
  → hiện **cảnh báo mềm** ("ngoài khung bậc 2: 10–20tr"), **vẫn lưu được**. Đây là C1.

**Dải "CẤU TRÚC TÍNH LƯƠNG"** (chỉ hiển thị) — ghi đúng engine, **không chép rút gọn từ mẫu**:

```
Lương theo công + Chuyên cần + Phụ cấp + Khoán + Tăng ca + Ca đêm + Thưởng (gồm KPI)
  − Phạt (trần 30%) − BHXH/BHYT/BHTN − Công đoàn − Thuế TNCN − Tạm ứng  =  THỰC LĨNH
```

---

## 5. Tab 2 — Cơ chế lương theo bộ phận

### 5.1 Khối trên — Áp dụng TOÀN CÔNG TY (luật bắt, không tách theo tổ)
Thay thế hẳn `ParamsModal`:

| Tham số | Mặc định | Ghi chú |
|---|---|---|
| ~~Công chuẩn / tháng~~ | — | **ĐÃ GỠ khỏi màn này (2026-07-23)**: tính ĐỘNG theo Chấm công → Lịch & Ngày lễ (tuần làm việc − lễ + làm bù), mỗi tháng một khác — redesign-hcns Đ3/N4 + NĐ145/2020 Đ55 |
| Giờ công chuẩn / ngày | 8 | |
| % lương thử việc | 80% | |
| Hệ số tăng ca — ngày thường | 150% | |
| Hệ số tăng ca — ngày nghỉ tuần | 200% | |
| Hệ số tăng ca — ngày lễ | 300% | |
| **Làm nguyên công ngày nghỉ tuần** | **200%** | ⚠️ hiện **chưa có ô nhập** — bổ sung |
| **Làm nguyên công ngày lễ** | **300%** | ⚠️ hiện **chưa có ô nhập** — bổ sung |

### 5.2 Khối dưới — Theo từng bộ phận
Chip chọn bộ phận → mỗi thành phần **1 dòng: công tắc + ô giá trị + đơn vị**:

| Thành phần | Đơn vị | Ghi chú |
|---|---|---|
| Lương theo bậc | — | hiện khung bậc 1 để tham chiếu |
| **Thưởng năng suất KPI** | đ/tháng (mức trần) | MỚI |
| **Chuyên cần** | đ/tháng | **300.000** phổ thông, **500.000** quản lý cấp cao — mỗi tổ một khác |
| **Phụ cấp trách nhiệm** | đ/tháng | mỗi tổ một khác (C6) |
| **Phụ cấp thâm niên** | đ / 6 tháng | mỗi tổ một khác (C5) |
| Lương khoán / sản lượng | bật/tắt | `has_piece_work` — chỉ phơi cờ sẵn có, tính tiền khoán **tạm gác** (§10) |
| Tăng ca | bật/tắt | |

### 5.3 Bảng ĐƠN GIÁ CA của tổ (MỚI — theo C4)
Mỗi tổ khai bảng đơn giá riêng, engine nhân với **số lượt** trong tháng:

| Loại | Đơn giá thực tế | Đơn vị |
|---|---|---|
| Ca tới sáng | 125.000 | đ / lượt |
| Ca đêm | 77.000 | đ / lượt |
| Cơm ca 21h | 27.000 | đ / suất |
| Tài xế trước 6h sáng | 50.000 | đ / lượt |

Tổ tự thêm/bớt loại. **Thay hẳn** cách tính `số ngày × đơn giá công × 30%` hiện tại.

---

## 6. Tab 3 — Phụ cấp & Bảo hiểm

### 6.1 Danh mục phụ cấp — cấp công ty chỉ ĐỊNH NGHĨA LOẠI (C6)
Mỗi dòng: **tên · mô tả · đơn vị tính · công tắc**. **KHÔNG có cột "mức mặc định công ty"** —
mức tiền khai ở **Tab 2 theo từng tổ**.

| Phụ cấp | Đơn vị | Engine tính thế nào |
|---|---|---|
| Ca đêm / ca tới sáng | đ / lượt | đơn giá của tổ × số lượt (C4) |
| Cơm ca | đ / suất | đơn giá của tổ × số suất (C5) |
| Thâm niên | đ / 6 tháng | mức của tổ × số kỳ 6 tháng từ ngày vào làm (C5) |
| Trách nhiệm | đ / tháng | mức của tổ, cộng phẳng |
| Chuyên cần | đ / tháng | mức của tổ × tỷ lệ trừ dần (C3) |

**Thứ tự ghi đè:** **tổ → nhân viên**. Tắt loại ở cấp công ty = cả hệ thống không dùng khoản đó.

> **Tương thích dữ liệu cũ:** giữ `employee_salaries.allowance` với vai trò **"Phụ cấp khác (gộp)"**;
> các loại trong danh mục cộng **thêm** lên trên. Không đập dữ liệu phụ cấp đang có.

### 6.2 Bảo hiểm bắt buộc — bảng 2 phía
| Khoản | **NSDLĐ (%)** | **NLĐ (%)** |
|---|---|---|
| BHXH | **17,5** *(MỚI)* | 8 |
| BHYT | **3** *(MỚI)* | 1,5 |
| BHTN | **1** *(MỚI)* | 1 |
| **Tổng** | **21,5** | **10,5** |

- Cột **NLĐ** đã có — là khoản **trừ vào lương**, tính trên **mức đóng BH khai riêng** (không phải lương vị trí).
- Cột **NSDLĐ** là MỚI — **KHÔNG trừ vào lương nhân viên**, chỉ để tính chi phí công ty. Phải ghi chú rõ trên màn.
- Kèm **2 mức trần đóng** (BHXH+BHYT 50.600.000 · BHTN 106.200.000) và **đoàn phí công đoàn 0,5%**.
- **Nhân viên thử việc chưa đóng bảo hiểm.**

### 6.3 Thuế TNCN
Giảm trừ bản thân (15.500.000) · giảm trừ người phụ thuộc (6.200.000) · biểu thuế lũy tiến từng phần (sửa/thêm/xóa bậc).

---

## 7. KPI — luồng đầy đủ

1. **Khai mức trần** theo bộ phận ở Tab 2 (vd Kinh doanh 1.700.000 đ/tháng) + bật công tắc.
2. **Nhập % đạt hằng tháng** cho từng NV trong **modal "Sửa lương"** ở tab Bảng lương tháng (không dựng màn KPI riêng).
3. `Thưởng KPI = % đạt × mức trần của bộ phận`, làm tròn đồng. Bộ phận tắt KPI → luôn 0.
4. Cộng vào tổng thu nhập, **chịu thuế TNCN** (khác tăng ca/ca đêm được miễn).
5. **Phiếu lương** hiện 1 dòng riêng — *"Thưởng KPI (85%)"*.

---

## 8. Nghiệp vụ PHẢI GIỮ (engine đang đúng luật)

- Tăng ca tính trên **mức nền** (lương vị trí + trách nhiệm) × % thử việc — không gồm phụ cấp/chuyên cần/khoán.
- **Chặn trần công:** làm dư công không trả dư.
- **Trần khấu trừ 30% (Đ102 BLLĐ)** gộp mọi khoản phạt.
- **BHXH 2 trần riêng** + tính trên **mức đóng khai riêng**.
- **TNCN lũy tiến từng phần** + giảm trừ gia cảnh + **miễn phần tăng ca/ca đêm**.
- Thử việc **không đóng bảo hiểm** · thực lĩnh **sàn 0**.
- Kỳ lương `draft → locked → paid`; **sửa cấu hình không đụng kỳ đã chốt/đã chi**.

> ⚠️ **ĐÃ BỎ khỏi danh sách này:** "chuyên cần đủ công mới được, thiếu là mất hết" — thay bằng **C3 trừ dần**.

---

## 9. Dọn theo (làm cùng pha code)

| Việc | Lý do |
|---|---|
| Phòng ban → tab Lương thành **chỉ đọc + nút "Sửa ở Cấu hình lương"** | Chặn 2 nơi cùng sửa một bảng |
| Hồ sơ NV → **gỡ "Nhóm lương / Bậc lương"** khỏi UI (giữ cột DB) | Đã vô dụng, gây hiểu nhầm (B3) |
| Bỏ 2 cột chết `department_salary_rows.phu_cap` / `.chuyen_can` | Đã thay bằng khai theo tổ (B2) |
| Mở **endpoint ghi thang bậc dưới `/api/luong`** gác `luong:update` | Hiện đường ghi duy nhất gác `phong_ban:update` → người chỉ có `luong:update` bấm Lưu **ăn 403** |
| Vá lệch trần 30% giữa "Tính lại" và "Sửa 1 ô" | 2 đường ra 2 số |

---

## 10. Dữ liệu cần thêm / sửa

**So với v1 (đã dựng) — phần phải SỬA:**
- `department_salary_rows`: **thêm `luong_min`, `luong_max`** (khung — C1); giữ `promotion_condition`.
- `employee_salaries`: **thêm `luong_vi_tri`, `luong_trach_nhiem`** (gõ riêng từng ô — C2) và
  **`pay_grade_row_id`** (bậc, TÁCH khỏi nguồn tiền — hiện `source_salary_row_id` vừa là bậc vừa là nguồn tiền).
- **Bảng mới `department_shift_rates`** — đơn giá ca theo tổ (C4): `department_id`, `key`, `name`, `unit_price`, `is_active`.
- `payroll_lines`: **thêm số lượt từng loại ca** (để tái lập được cột "Thành tiền" của bảng thật).
- `allowance_types`: **bỏ `default_value`** ở cấp công ty (C6) — chỉ còn tên + đơn vị + bật/tắt.

**Đã dựng ở v1, giữ nguyên:** `department_salary_components` · `payroll_params` + 3 tỷ lệ NSDLĐ ·
`payroll_lines.kpi_percent`/`kpi_bonus`.

> ⚠️ **Bắt buộc kèm** migration idempotent trong `backend/app/db_migrations.py` (cột Boolean dùng `false`/`true`,
> **không** `"0"`/`"1"` — vỡ Postgres) **và** cập nhật `docs/DB_SCHEMA.md` (có guard test, thiếu là fail `init`).

**File sẽ đụng:** `models/payroll.py` · `services/payroll_service.py` (`_compute`, `_resolve_salary`,
`_effective_chuyen_can`) · `routers/payroll.py` + `schemas/payroll.py` · FE `CauHinhLuongTab.tsx`,
`LuongPage.tsx`, `luong.css`, `client.ts`.

---

## 11. Ngoài phạm vi & rủi ro

**Ngoài phạm vi:** màn Hồ sơ nhân sự · phiếu lương · chấm công · **lương khoán**.

**🟠 Rủi ro 1 — Chấm công chưa đếm được số lượt ca.** Hiện chấm công chỉ trả **`night_days`** (số ngày ca đêm),
chưa tách được *ca tới sáng · ca đêm · cơm 21h · tài xế trước 6h* như bảng lương thật. **Giai đoạn đầu:
cho nhập tay số lượt** trong modal "Sửa lương"; nối chấm công ở pha sau.

**Lương khoán — CHỦ CHỐT TẠM GÁC (2026-07-20).** Ghi lại để khỏi soi lại: `deps.py:338-342` khởi tạo
`PieceWorkService(piece)` không truyền nguồn sản lượng → cột **Khoán luôn = 0** qua app; bộ phận ăn khoán
còn bị engine tắt luôn tăng ca. Khi mở lại phần khoán thì xử lý cụm này trước.

---

## 12. Tiêu chí nghiệm thu — kiểm bằng SỐ THẬT

1. `./init.ps1` xanh (pytest + compileall) và `npm run build` xanh.
2. **Chuyên cần (C3):** mức 300.000 · 25,5 công → **225.000** · 25 công → **150.000** · 23 công → **0**.
   Mức 500.000 · 25 công → **250.000**.
3. **Ca đêm (C4):** tổ khai cơm 21h 27.000 đ/suất, NV ăn **5 suất** → **135.000**.
4. **Bậc là khung (C1):** cùng bậc 2 (khung 10–20tr), NV A khai **20.000.000**, NV B khai **10.500.000** —
   **cả hai lưu được**, không cảnh báo; khai 25.000.000 thì **cảnh báo mềm nhưng vẫn lưu**.
5. **Phụ cấp theo tổ (C6):** đổi mức chuyên cần ở tổ A không làm đổi tổ B; NV đã ghi đè thì **giữ số riêng**.
6. **Thâm niên + cơm (C5):** ra tiền thật trên phiếu lương, không còn là dòng trang trí.
7. Sửa cấu hình → kỳ **draft** đổi theo; kỳ **đã chốt/đã chi KHÔNG đổi số**.
8. Không còn nơi thứ hai khai chuyên cần hay phụ cấp.
