# Spec — Module Lương (Phase 1: lương thời gian)

Module `luong`. Mục tiêu: bảng lương **thời gian** hàng tháng cho toàn công ty — tự kéo
công từ Chấm công, áp mức lương theo quy tắc/khai báo, trừ tạm ứng + BHXH → thực lĩnh,
chốt kỳ, xuất Excel + file chuyển khoản. Gated cho HCNS/kế toán (module quyền riêng vì nhạy cảm).

Khoán / hoa hồng KD auto / TNCN 7 bậc auto / tách BHXH 2:1:2 = **Phase sau** (không phá vỡ Phase 1).

## Màn hình (5 tab trong 1 trang "Lương")
1. **Bảng lương tháng** — chọn tháng → Tạo (máy điền) → soát ô vàng → Chốt → Xuất Excel + file chuyển khoản.
2. **Lương nhân viên** — Khai báo (gán nhóm/bậc hoặc nhập tay mức riêng + phụ cấp) & Điều chỉnh lương (ngày hiệu lực + lịch sử).
3. **Quy tắc lương** — mức chuẩn theo nhóm/bậc/thâm niên×giới tính (khai 1 lần) + tham số BHXH/giảm trừ/chuyên cần/%thử việc.
4. **Tạm ứng** — ghi ứng nhiều lần/tháng → duyệt → tự cộng dồn → trừ.
5. **Phiếu lương của tôi** — NV tự xem/tải (self-service, như Nghỉ phép).

+ Hồ sơ NV thêm 2 cột: `payroll_group`, `pay_grade_key`. Còn lại tái dùng dữ liệu sẵn có.

## Bảng dữ liệu mới (create_all; 2 cột employees qua migration 0012)
- `payroll_params` — cấu hình (1 dòng): `standard_cong_default`, `probation_ratio`(0.8),
  `bhxh_rate`/`bhyt_rate`/`bhtn_rate` (NV: 0.08/0.015/0.01), `deduction_self`(11tr),
  `deduction_dependent`(4.4tr), `chuyen_can_default`.
- `salary_rate_rules` — bảng chính sách mức: `payroll_group`, `pay_grade_key?`,
  `seniority_band?` (lt1/y1_5/y5_10/gt10), `gender?`, `monthly_amount`, `chuyen_can?`,
  `effective_from`, `is_active`. **Lookup**: khớp cụ thể nhất, `effective_from ≤ kỳ`.
- `employee_salaries` — lương ấn định 1 NV (versioned): `employee_id`, `effective_from`,
  `amount_mode` (rule|manual), `base_amount?` (khi manual), `insurance_base?` (mặc định = mức lương),
  `allowance` (phụ cấp cố định tháng), `note`, `created_by`. Điều chỉnh = thêm bản ghi mới;
  "hiện hành" = `effective_from` lớn nhất ≤ kỳ.
- `salary_advances` — tạm ứng: `employee_id`, `period_year`, `period_month`, `advance_date`,
  `amount`, `reason`, `status` (pending/approved/rejected/cancelled), `decided_by/at`, `created_by`.
- `payroll_periods` — kỳ lương: `year`, `month` (UNIQUE), `status` (draft/locked),
  `standard_cong`, `locked_at/by`, `created_by`.
- `payroll_lines` — dòng lương 1 NV/kỳ (snapshot): `period_id`, `employee_id`, `is_probation`,
  `actual_cong`, `standard_cong`, `monthly_salary`, `luong_cong`, `chuyen_can`, `allowance`,
  `vi_pham` (tay), `other_bonus` (tay: thưởng/hoa hồng), `gross`, `insurance_base`, `bhxh`,
  `pit` (tay), `advance_total`, `net_pay`, `note`.

## Engine (tính 1 dòng lương)
```
mức = employee_salary hiện hành: manual→base_amount; rule→tra salary_rate_rules
      theo (payroll_group, pay_grade_key, seniority_band từ hire_date, gender)
ratio_tv = 0.8 nếu status=probation, ngược lại 1.0
actual_cong ← Bảng công tháng (attendance timesheet) của NV
luong_cong  = mức × ratio_tv × (actual_cong / standard_cong)
chuyen_can  = (đủ công: actual_cong ≥ standard_cong) ? mức chuyên cần : 0
gross       = luong_cong + chuyen_can + allowance + other_bonus − vi_pham
insurance_base = employee_salary.insurance_base ?? mức    (KHÔNG prorate theo công)
bhxh        = insurance_base × (bhxh+bhyt+bhtn = 10.5%)
pit         = nhập tay (Phase 1, default 0)
advance_total = Σ tạm ứng đã duyệt của NV trong (year, month)
net_pay (Thực lĩnh) = gross − bhxh − pit − advance_total
```
CT/TV: **một** kỳ/tháng, FE lọc theo `status` hiển thị; thử việc tự ×0.8. Chốt = khóa cả tháng (snapshot).

## Luồng dùng mỗi tháng (3 bước)
Chọn tháng → **Tạo bảng lương** (máy kéo công + mức + tạm ứng → điền hết) → soát ô vàng
(vi phạm / thưởng / lương cấp cao / pit) → **Chốt** → Xuất Excel + file chuyển khoản.

## Ngoài phạm vi Phase 1 (để sau)
Lương khoán theo tổ (cần Sản xuất cho sản lượng) · hoa hồng KD auto · TNCN lũy tiến 7 bậc auto ·
tách LCB/TN/PC (2:1:2 / 2:2:1) auto · vi phạm có danh mục/workflow.
