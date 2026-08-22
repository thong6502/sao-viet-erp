# PRD — Nhân sự & Lương (bản tổng hợp theo luật thật nhà máy)

> **Trạng thái:** Thiết kế đã chốt · **chưa triển khai phần [mới]**.
> **Tạo:** 2026-07-21. Gộp toàn bộ luật lương thật chủ cung cấp qua nhiều lượt + trạng thái code hiện tại.
> **Thay thế một phần** `docs/prd-cau-hinh-luong.md` (v1→v4) ở chỗ **chuyên cần** và **phụ cấp ca** — xem §0.
> **Nguồn:** bảng lương thật `BẢNG LƯƠNG T05.2026`, `LƯƠNG CHỈNH NĂM 2026`, và luật vận hành chủ mô tả.
> **Phụ thuộc:** mảng Chấm công (§3) trước đây **gác**, nay mở lại; trên nhánh đã có sẵn `work_shifts` +
> lịch sử gán ca (`employee_shift_assignments`) **đang làm dở** — PRD nối tiếp, không dựng lại. Lương **khoán**
> (Thợ Bế/In) vẫn **gác** (§7).

---

## 0. Quyết định đã chốt (decision log — bản MỚI NHẤT thắng)

| # | Quyết định | Thay thế |
|---|---|---|
| **D1** | **Bậc/loại thợ = chữ ghi chú** trong hồ sơ (bậc mấy, thợ phụ, thâm niên) — KHÔNG quyết định tiền. | v2 (bậc = khung) |
| **D2** | **Lương cơ bản = mức đóng BH.** BHXH/BHYT/BHTN + công đoàn tính trên lương cơ bản. Gõ riêng: lương cơ bản + lương trách nhiệm. | v1/v2 |
| **D3** | **Chuyên cần = số khai PER-NGƯỜI; không khai = 0đ.** Mất TOÀN BỘ khi vi phạm (all-or-nothing): 1 lần **trễ/sớm > 2h** HOẶC **nghỉ không phép** → mất sạch cả tháng. *(Bảo vệ: để trống chuyên cần = tự động 0, không cần luật riêng — D9.)* | ⚠️ v2/v3 "nghỉ nửa ngày −25% trừ dần" (SAI) |
| **D4** | **Phụ cấp khai TRÊN TỪNG CA** (`work_shifts`, form tạo/sửa ca ở màn Chấm công): mỗi ca có **Phụ cấp cơm** (`meal_allowance`) + **Phụ cấp ca** (`shift_allowance` — CHUNG, không khóa "đêm"; ngày hay đêm đều gắn được). NV gán ca nào → máy TỰ CỘNG phụ cấp của ca đó. KHÔNG cấp công ty, KHÔNG per-người. | ⚠️ v3 per-người → thử cấp công ty (đã gỡ) → chốt: **theo CA**; "ca đêm" đổi thành "ca" (chung) |
| **D5** | **Công tính theo GIỜ:** 8 tiếng = 1 công; **6 tiếng = 0,75 công**; cộng giờ **2 ca** (ca gãy) lại. | v-cũ "1 ca = 1 công" |
| **D6** | **Nghỉ bù tăng ca:** nghỉ **buổi sáng** hôm sau = **0,5 công** (có lương); nghỉ **nguyên ngày** = **1 công**. | mới |
| **D7** | **Không cho chấm sớm quá 30 phút** trước giờ vào ca; **phải được gán ca mới chấm được công.** | mới |
| **D8** | ~~Công = giờ làm thực ÷ 8, trừ nghỉ trưa~~ → **ĐÃ BỎ (chủ chốt).** Giữ cách tính hiện tại: **công = thời gian có mặt trong ca ÷ độ dài ca** — trọn ca = 1 công (nghỉ trưa nằm trong ca, không bấm ra nên không cần khai). **KHÔNG thêm ô nghỉ trưa.** | đảo ngược — cách hiện tại là đủ |
| **D9** | **KHÔNG hard-code luật theo loại thợ** (Bế/In/Bảo vệ) — vì tổ sẽ thêm nhiều, hard-code là gãy. Nhận diện "loại thợ" = theo **TỔ** + **cờ cấu hình của tổ** (vd `has_piece_work`), KHÔNG theo nhãn cứng. Hành vi đặc thù gắn vào **config của tổ** hoặc **khai per-người**, không vào code. | mới (nguyên tắc nền) |
| **D10** | **Thâm niên KHAI ĐƯỢC lúc tạo hồ sơ** (số năm đã làm ở nơi khác) → cột `employees.prior_seniority_months`. **Tổng thâm niên = số đã khai + thời gian từ ngày vào làm.** KHÔNG suy thuần từ hire_date (mất khúc trước khi vào). | mới |
| **D11** | **Phạt trễ/sớm: CẤU HÌNH bảng (toàn công ty, sửa được) + MÁY TỰ TÍNH từ chấm công, KHÔNG nhập tay.** Phạt theo TỪNG LẦN (mỗi buổi vi phạm quá dung sai = 1 sự kiện) tra bảng theo số phút. CN ×2 số phút. **CHỈ phạt khi KHÔNG phép** (buổi có đơn xin duyệt thì bỏ qua). Xem §4. | mới — Đợt 2 |

---

## 1. CẤU HÌNH LƯƠNG — Áp dụng toàn công ty

### 1.1 Tham số chung
| Tham số | Trạng thái |
|---|---|
| Giờ công chuẩn / ngày · % lương thử việc | ✅ đã có |
| Công chuẩn / tháng | ✅ ĐỘNG theo Lịch & Ngày lễ (ô khai đã gỡ khỏi Cấu hình lương) |
| Hệ số tăng ca: **ngày thường · ngày nghỉ tuần · ngày lễ** | ✅ đã có |
| Hệ số làm nguyên công: **ngày nghỉ tuần · ngày lễ** | ✅ đã có |

> **Phụ cấp cơm / ca đêm KHÔNG ở đây** — chuyển sang **khai trên từng CA** (§3.1, `work_shifts`) theo D4.

### 1.2 Bậc thang TĂNG CA (từ 01/08/2024) — 🆕 phức tạp nhất
Máy nhìn **giờ RA** của buổi tăng ca (mốc bắt đầu 17h30) để xếp bậc và cộng phụ cấp + nghỉ bù:

| Làm tới | Phụ cấp | Nghỉ bù hôm sau | Công nghỉ bù (D6) |
|---|---|---|---|
| 21h → 23h59 | **+25k** (cơm) | — | — |
| 00h → 1h sáng | **+75k** = 50k ca đêm + 25k cơm | nghỉ **buổi sáng**, có lương | **0,5 công** |
| 6h → 8h sáng | **+125k** = 2×50k ca đêm + 25k cơm | nghỉ **1 ngày**, có lương | **1 công** |

Các mức 25k / 50k **lấy từ §1.1** (cấu hình một lần), không hard-code.

---

## 2. HỒ SƠ NHÂN VIÊN — bước "Thêm nhân viên mới"

| Bước | Trường | Trạng thái |
|---|---|---|
| **1. Định danh & việc làm** | Họ tên · Phòng/Tổ · Ngày vào · Trạng thái (chính thức/thử việc) · Ngày hết thử việc *(khi thử việc)* | ✅ |
| **2. Cá nhân** | Ngày sinh · Giới tính · CCCD · SĐT · Email · Hộ khẩu · Chỗ ở hiện tại · Liên hệ khẩn (tên + SĐT) | ✅ |
| **3. Lương & BHXH** | Lương cơ bản (đóng BH) · Lương trách nhiệm · **Loại/Bậc thợ** (bậc mấy / thợ phụ) · **Thâm niên khi vào** (số năm đã có nơi khác; tổng = khai + từ ngày vào — D10) · Thưởng chuyên cần · Phụ cấp thâm niên · Phụ cấp khác · Số sổ BHXH · MST cá nhân · Người phụ thuộc · Số TK · Ngân hàng | ✅ *(thêm ô Loại/Bậc + Thâm niên; **bỏ ô Phụ cấp ca** — nay khai cấp công ty)* |
| **4. Đính kèm** | **Hợp đồng** + giấy tờ | ✅ |
| **5. Tài khoản** | Tên đăng nhập · Mật khẩu tạm · Vai trò | ✅ |

> **Phụ cấp ca KHÔNG còn là ô per-người** (D4): mức cơm/ca đêm khai **một chỗ ở Cấu hình lương → Áp dụng
> toàn công ty**, máy **tự tính theo ca thực tế** từ chấm công. → gỡ ô "Phụ cấp ca" khỏi wizard + màn Lương
> nhân viên (cột `phu_cap_ca` per-người dựng ở v3/v4 sẽ bỏ khi code).

---

## 3. CHẤM CÔNG & GÁN CA → LƯƠNG

### 3.1 Ca làm việc + gán ca
| Việc | Trạng thái |
|---|---|
| Khai báo **ca làm việc** (tên · giờ vào–ra · qua đêm · dung sai · đang dùng · **phụ cấp cơm** 🆕 · **phụ cấp ca** 🆕 — D4) | ✅ `work_shifts` *(bỏ cờ "ca đêm"; thêm 2 ô phụ cấp)* |
| Gán ca cho nhân viên (lịch sử theo mốc hiệu lực) | ✅ đang làm dở |
| **Gán 2 ca / người** — ca gãy (vd 8h–12h **+** 18h–22h) | 🆕 hiện 1 ca/người |
| Phải **được gán ca** mới chấm được công (D7) | ✅ một phần |

### 3.2 Tính công — GIỮ model hiện tại (D8 đã bỏ hướng ÷8 + nghỉ trưa)
`công ngày = thời gian có mặt trong ca ÷ độ dài ca`, tối đa 1 công/ngày; phần vượt giờ ca = tăng ca.
Có mặt **trọn ca** (vd 8:00–17:00) → **1 công** (nghỉ trưa nằm trong ca, không bấm ra → không cần trừ).
Về sớm/vào trễ → giảm theo tỷ lệ. **KHÔNG thêm ô nghỉ trưa, KHÔNG sửa `compute_day_cong`.**
> Gán **2 ca (ca gãy)** — D5: khi làm, cộng thời gian có mặt của cả 2 ca. Phần này vẫn để Đợt 2 (đụng gán ca).

### 3.3 Luật chấm công
- **Không cho chấm sớm quá 30 phút** trước giờ vào ca (D7).
- **Bôi vàng** — không bấm / bấm thiếu → **không tính công + không tính tăng ca** buổi đó.
- **Bôi xanh (không phép):** nghỉ KP → trừ **gấp đôi** ngày; trễ/sớm KP → trừ tiền phút **+ phạt bảng §4**.
- Trễ/sớm **Chủ Nhật** → **nhân đôi** số phút trễ/sớm.

> ⚠️ Chấm công **đã** biết trễ/sớm (đúng/sai giờ ca) nhưng **chưa lấy SỐ PHÚT** để áp bảng §4, và chưa
> phân biệt **có phép / không phép** (cần nối module Nghỉ phép đã có). Đây là việc [mới] của mảng này.

---

## 4. PHẠT ĐI TRỄ / VỀ SỚM KHÔNG PHÉP — 🆕 (D11 — TỰ TÍNH, không nhập tay)

**Cấu hình (toàn công ty, sửa được)** ở Cấu hình lương → Áp dụng toàn công ty — bảng bậc theo số phút, mặc định:

| Trễ/sớm (quá dung sai ca) | Phạt / lần |
|---|---|
| 1 – 15 phút | 20.000 |
| 16 – 30 phút | 40.000 |
| 31 – 60 phút | 100.000 |
| trên 1 giờ | 150.000 |

**Máy TỰ TÍNH từ chấm công** (KHÔNG nhập tay): đã có giờ vào/ra + ca (giờ vào–ra + **dung sai** `grace_minutes`).
Qua dung sai → tính **số phút trễ / về sớm** mỗi buổi → tra bảng → **phạt theo TỪNG LẦN** (mỗi buổi vi phạm = 1 sự kiện).
**Chủ Nhật ×2 số phút** trước khi tra bảng. Tổng phạt tháng tự cộng vào cụm phạt, chịu **trần 30% Đ102**.

**CHỈ phạt khi KHÔNG phép (D11):** buổi trễ/sớm có **đơn xin được duyệt** thì BỎ QUA. → cần cơ chế
**"có phép trễ/sớm"** (đơn xin đi trễ/về sớm của NV → HCNS duyệt; hoặc HCNS đánh dấu buổi đó "có phép" khi
soát bảng công — có thể dùng lại `attendance_adjust_requests` đã có).

> **Phụ thuộc:** (1) NV phải **được gán ca** (biết giờ ca để tính trễ); (2) chấm công tính + tổng hợp
> **số phút trễ/sớm** (hiện mới có cờ late/early, CHƯA có số phút); (3) cơ chế "có phép trễ/sớm".
> Nằm trên module chấm công — cần nền chấm công ổn trước (xem §11 rủi ro: bug `next_action`/gán ca).

---

## 5. KHÔNG hard-code luật theo loại thợ (nguyên tắc — D9)
Chủ chốt: **đừng gắn luật vào nhãn "Thợ Bế / Thợ In / Bảo vệ" cứng** — tổ sẽ thêm nhiều, hard-code là gãy.
- **Nhận diện loại thợ = theo TỔ** (Thợ Bế = người thuộc Tổ Bế). Hệ thống không có trường "worker type" riêng, chỉ có Phòng/Tổ + ô "Loại/Bậc thợ" (chữ, ghi chú).
- **Hành vi đặc thù gắn vào CẤU HÌNH của tổ** (cờ bật/tắt), không vào code. Cờ **`has_piece_work`** (đã có) đánh dấu tổ ăn khoán → đó là cách biết Thợ Bế/In, thay cho nhãn cứng.
- **Chuyên cần** = số khai **per-người**, không khai = 0đ → **Bảo vệ để trống là tự động không có**, khỏi cần luật "Bảo vệ không chuyên cần".
- Luật khoán của Thợ Bế/In (CN ×2 = 1 công + 1 sản phẩm · **max(sản phẩm, bù lỗ)** · Thợ In bỏ SL ngày CN · Thợ Bế nghỉ có phép vẫn mất chuyên cần) → **§7 (khoán, gác)** — làm khi mở lại khoán, gắn vào cờ tổ chứ không nhãn cứng.

---

## 6. Trạng thái tổng: ĐÃ CÓ / MỚI / PHẢI SỬA
- ✅ **Đã có:** cấu hình toàn công ty (trừ 2 mục cơm/ca đêm) · hồ sơ NV wizard · khai báo ca · gán 1 ca · chấm công GPS · tính trễ/sớm · BHXH trên lương cơ bản · TNCN lũy tiến · trần 30% · kỳ lương 3 trạng thái.
- 🆕 **Mới:** phụ cấp cơm/ca đêm cấu hình + bậc thang tăng ca §1.2 · gán **2 ca** · công **theo giờ** · chặn chấm sớm 30p · **số phút trễ + bảng phạt §4** · phân biệt có/không phép · phụ cấp ca **tự tính**.
- ⚠️ **Phải sửa (nợ):** chuyên cần → theo vi phạm (D3, bỏ "trừ dần") · phụ cấp ca → tự tính (D4, bỏ số cố định).

---

## 7. NGOÀI PHẠM VI (đợt sau)
**Lương khoán** — Thợ Bế/In: CN ×2 sản phẩm, **sản phẩm vs bù lỗ**, sản lượng theo người → cả cụm dính
module **KHOÁN đang gác** (`deps.py` chưa nối nguồn sản lượng → cột Khoán = 0). Làm cùng đợt mở lại khoán.

---

## 8. Phụ thuộc & rủi ro
1. **Phần lõi §1.2/§3/§4 phụ thuộc CHẤM CÔNG** cấp dữ liệu mới (giờ ra tăng ca, số phút trễ, có/không phép,
   2 ca, giờ làm thực). Trước khi chấm công đủ, các khoản này **HR nhập tay** ở "Sửa lương" (ô phạt/phụ cấp đã có).
2. **Gán ca lịch sử** đang làm dở trên nhánh (2 test `test_attendance_reset` đang đỏ vì NV chưa gán ca) →
   cần đồng bộ với việc này, tránh giẫm chân.
3. **Đảo ngược** chuyên cần (D3) + phụ cấp ca (D4) so với code v3/v4 đã dựng → khi code phải gỡ đúng chỗ,
   kèm migration + `docs/DB_SCHEMA.md` (guard test) nếu đổi cột.

---

## 9. Verify (khi code — theo số thật)
`./init.ps1` + `npm run build` xanh. Ca kiểm chứng:
- Công theo giờ: đủ 8h → 1 công; 6h → 0,75 công.
- Tăng ca tới 0-1h sáng → +75k + nghỉ sáng mai tính 0,5 công.
- Trễ 20 phút không phép → trừ tiền 20 phút + phạt 40.000đ (bậc 16–30').
- Chuyên cần: trễ > 2h hoặc nghỉ KP → mất chuyên cần; Bảo vệ luôn 0 chuyên cần.
- Chấm sớm 31 phút trước ca → bị chặn.
