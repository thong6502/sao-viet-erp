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

---

## Khoán theo ĐẦU VIỆC (2026-07-30)

Bảng "CÔNG KHOÁN" giấy của xưởng là **danh sách đầu việc + đơn giá**, không phải một giá cho cả tổ:
tổ Cán/Phủ có *"cán bóng · cán mờ · phủ UV nước · UV mờ"* = 150 đ/m² và *"ghép màng metalize"* =
250 đ/m². Khai ở `Lương → Cấu hình lương của tổ → Đơn giá khoán` (bảng `piece_rates`).

**Quan hệ: NHIỀU công đoạn → MỘT đầu việc.** Cán bóng và cán mờ là hai công đoạn khác nhau (khác vật
tư, khác giá BÁN) nhưng với THỢ là một việc (cùng máy, cùng động tác) nên cùng một công khoán. Vì vậy
mỗi dòng đơn giá tick **nhiều** mã công đoạn (`cong_doan_mas`), khỏi nhân thành 4 dòng trùng giá.
Rỗng = áp cho mọi công đoạn của tổ.

**Luật khớp đầu việc với bước lệnh** (`piece_work_service.dau_viec_khop`): cùng TỔ, rồi **ưu tiên dòng
khai đúng mã công đoạn**; không có dòng nào khai riêng thì mới dùng dòng "áp cho mọi công đoạn". Trộn
cả hai thì bảng có 1 dòng chung + 1 dòng riêng sẽ luôn ra 2 kết quả, bước nào cũng phải hỏi người dùng
dù xưởng đã khai rõ.

**Kế hoạch chọn đầu việc ở BƯỚC LỆNH**, không ở phiếu tính giá — lúc tính giá sale chưa biết chạy máy
nào, bế tay hay bế máy. Ô nằm trong khối "Ai làm" của drawer bước (`Kế hoạch SX → lệnh → Công đoạn`);
khớp đúng 1 đầu việc thì máy **điền sẵn**, khớp nhiều (bế máy 250 đ/tờ ≠ bế tay 400 đ/tờ) thì **để
trống + nhắc** — chỉ người biết hôm đó bế bằng gì. Chọn xong GHIM snapshot vào
`lsx_cong_doan.khoan_json`: xưởng lên giá khoán về sau không được xê dịch lệnh đã phát.

**Tiền khoán = SL VÀO của bước → quy đổi sang đơn vị đơn giá → × đơn giá**, tính LÚC ĐỌC (không lưu
cột). Quy đổi qua `services/quy_doi_service.py` — xem `docs/spec-don-vi-quy-doi.md`. Số thật: bước cán
màng của lệnh thẻ nhân viên = `241 tờ × 86 cm × 65 cm = 134,72 m² × 150 đ/m² = 20.208 đ`.

Đếm theo SL VÀO vì **thợ chạy bao nhiêu tờ thì ăn bấy nhiêu**, kể cả 230 tờ bù hao canh máy 4 màu;
hàng lỗi do thợ trừ riêng, không bằng cách hạ số tờ.

### Phạm vi hiện tại — chỉ KẾ HOẠCH

Lát này dừng ở **số dự kiến**: bước hiện dòng ba số, lệnh hiện Σ "Công thợ dự kiến" (là số SÀN — bước
chưa chọn đầu việc thì không góp vào). **Chưa** nối vào cột `khoan` của bảng lương, vì nguồn SẢN LƯỢNG
THẬT đã bị gỡ khỏi hệ (`production_outputs` không còn model/router; `PieceWorkService.khoan_map` luôn
trả rỗng). Dựng lại khâu "tổ trưởng báo sản lượng" là lát riêng, và nó cũng mở luôn
`piece_leader_bonus_brackets` (thưởng/phạt tổ trưởng theo % hàng lỗi) đang treo.

Cũng **chưa** làm: chia tiền trong nhóm (ghi chú Excel: *tổ trưởng lấy 5%, còn lại nhóm tự chia*) —
máy chỉ nên GHI NHẬN con số tổ trưởng báo, không tự chia, vì tỷ lệ do nhóm tự thoả thuận.
