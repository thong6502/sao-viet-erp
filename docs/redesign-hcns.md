# Đại tu phân hệ Hành chính nhân sự (HCNS) — Thiết kế tổng thể

> **Trạng thái:** Bản thiết kế đã chốt 4 quyết định nền · **chưa triển khai code**.
> **Tạo:** 2026-07-12. Dựa trên khảo sát trực tiếp code hiện trạng (models/services/routers/FE + spec) của 6 module HCNS.
> **Phạm vi đại tu:** cả ba mặt — nghiệp vụ tính sai · kiến trúc/liên thông rối · bổ sung chính sách.
> **Module liên quan:** `nhan_su` (hồ sơ · chấm công · nghỉ phép) · `luong` (thời gian + khoán) · `phong_ban` · self-service `/me`.

---

## 0. Quyết định nền đã chốt (decision log)

| # | Vấn đề | Quyết định |
|---|---|---|
| **Đ1** | Một con người bị "xé đôi" giữa tài khoản (`users`) và hồ sơ (`employees`) | **`employees` là gốc.** Tài khoản chỉ là "chìa khóa đăng nhập" trỏ vào 1 hồ sơ; tên/ảnh/phòng **một nguồn** lấy từ hồ sơ. Gỡ trùng tiền tố mã `NV###`. |
| **Đ2** | "Phòng của một người" lưu 2 chỗ; xóa/chuyển phòng chỉ tính `users`, bỏ `employees` → hồ sơ treo | **Phòng tính theo hồ sơ nhân viên.** Đếm phòng, quyền-xem-theo-phòng, xóa/gộp/chuyển phòng đều bám hồ sơ, không để treo. |
| **Đ3** | Bảng công tính lại mỗi lần → sửa chấm công sau khi trả lương làm lệch số | **Có bước "Chốt công tháng"** (đóng băng bản công); Lương đọc bản đã chốt. **Công chuẩn = số ngày làm việc thực của từng tháng** (theo lịch Đ4), không cố định 26. |
| **Đ4** | Mỗi module tự quy ước nghỉ T7/CN bằng hardcode; không có bảng ngày lễ | **Một bảng "Lịch làm việc & Ngày lễ" dùng chung** (ngày lễ âm/dương + cấu hình tuần làm việc) cho Phép/Công/Lương. |

---

## 1. Hiện trạng & điểm đau (vì sao đại tu)

### Bốn "bệnh nền" xuyên suốt
| # | Bệnh nền | Biểu hiện | Chạm module |
|---|---|---|---|
| **B1** | Một con người bị xé làm đôi: `users` và `employees` song song — mỗi bên có phòng, tên, ảnh **riêng**, cùng tiền tố mã `NV###` đánh số độc lập | Sửa tên/ảnh tài khoản không cập nhật hồ sơ NV; "Hồ sơ của tôi" chẻ làm 2 hệ rời | Hồ sơ NV, Hồ sơ của tôi, Phòng ban, RBAC |
| **B2** | Xương sống Chấm công→Lương lệch: công chuẩn hardcode 26; NV **chưa gán ca** = trọn 1 công/ngày, NV **đã gán ca** = trừ theo giờ; timesheet tính lại mỗi lần, không snapshot | Hai người cùng đi làm nhận công khác nhau; số công đổi sau khi đã chốt lương | Chấm công, Lương |
| **B3** | Không có lịch làm việc / ngày lễ dùng chung; hardcode nghỉ T7/CN | Nghỉ trúng lễ vẫn trừ phép; công ngày lễ không tính; lệch nhau mỗi dịp lễ | Nghỉ phép, Chấm công, Lương |
| **B4** | OT + ca đêm bị "treo": Chấm công đo phút OT và cờ ca đêm nhưng Lương không đọc; TNCN 7 bậc & hoa hồng KD nhập tay | Tăng ca = 0 đồng; phụ cấp ca đêm chưa tồn tại | Chấm công, Lương |

### Điểm đau theo module
- **Hồ sơ NV:** quyền `view_salary` chỉ che khi đọc, **không chặn ghi** (PUT vẫn sửa được lương/BHXH) — lỗ hổng; che lương đặt ở router (sai tầng); ngưỡng "sắp hết thử việc" FE 14 ngày ≠ BE 30 ngày.
- **Hồ sơ của tôi:** 2 backend rời (hồ sơ *tài khoản* trên `users` vs hồ sơ *nhân viên* trên `employees`); duyệt yêu cầu đổi hồ sơ không re-validate; danh sách yêu cầu không lọc scope phòng.
- **Phòng ban:** xóa/điều chuyển phòng chỉ đếm `users`, bỏ `employees` → `employees.department_id` mồ côi; trạng thái phòng ("trống") tính sai vì chỉ nhìn user.
- **Chấm công:** tự VÀO/RA theo log gần nhất không reset theo ngày; nghỉ trưa không trừ; quy tắc gom ca viết lặp 3 lần.
- **Nghỉ phép:** 2 bản leave-map (1 bản chết y hệt — rủi ro sửa nhầm); đơn "ngày lịch" nhưng trừ quota "ngày làm việc"; quota giữ chỗ cả đơn `pending`.
- **Lương:** engine không ghi nhật ký (lock/generate/sửa); chưa có chi trả/xuất file chuyển khoản (đã hứa trong spec); BHXH không xét mức trần.
- **Lương khoán:** sản lượng 100% nhập tay (chưa nối Sản xuất); không khóa kỳ (sửa sổ sau chốt → lệch); tiền tổ trưởng có thể "bốc hơi" nếu không nằm trong danh sách chia; Σ hệ số = 0 thì quỹ không chia cho ai.

---

## 2. Sáu nguyên tắc nền (target)
- **N1 — Một con người, một nguồn:** `employees` là hồ sơ gốc. `users` chỉ giữ đăng nhập + vai trò, trỏ vào 1 hồ sơ. Tên/ảnh/phòng hiển thị lấy từ hồ sơ. Gỡ trùng tiền tố mã.
- **N2 — Phòng theo hồ sơ:** "ai thuộc phòng nào", "đếm phòng", quyền xem-theo-phòng bám hồ sơ. Xóa/gộp/chuyển phòng xử lý cả hồ sơ.
- **N3 — Lịch dùng chung:** 1 bảng ngày lễ (âm/dương) + cấu hình tuần làm việc. Phép/Công/Lương hỏi cùng một lịch.
- **N4 — Kỳ & Chốt:** mỗi tháng là một kỳ công; có bước Chốt công (đóng băng) rồi Lương mới đọc. Công chuẩn động theo tháng.
- **N5 — Tách quyền tiền:** *xem lương* và *sửa lương/BHXH* là hai quyền khác nhau, chặn ở tầng nghiệp vụ (không chỉ ẩn trên màn).
- **N6 — Mọi thao tác có nhật ký:** bổ sung nhật ký cho Lương/Khoán; mọi chốt/mở/sửa đều truy được.

## 3. Bản đồ liên thông target
```
 Hồ sơ NV (gốc) ──┬─ phòng/tổ ──▶ cây tổ chức ──▶ quyền xem theo phòng (toàn hệ)
                  ├─ ca mặc định ──▶ Ca làm việc
                  └─ nhóm/bậc lương, giảm trừ ──▶ khóa tra chính sách lương
        │
 Lịch làm việc & Ngày lễ (N3) ──▶ dùng chung cho 3 module dưới
        │
        ▼
 Chấm công ──▶ Bảng công tháng ──▶ [CHỐT] ──▶ Bản công đã khóa ─┐
 Nghỉ phép (đã duyệt) ─(P/KL theo lịch)──────────────────────────┤
                                                                  ▼
                              Lương: mức × (công/công-chuẩn động) + OT + khoán + phụ cấp
                                     − BHXH − TNCN − tạm ứng ──▶ [CHỐT kỳ] ──▶ Chi trả
                                                    ▲
                     Khoán tổ (sản lượng) ──[khóa cùng kỳ]──────┘
```

## 4. Thiết kế từng module (mức nghiệp vụ)

**4.1 Con người & Tổ chức** *(nền — làm trước)*
- Hồ sơ NV là gốc; tài khoản trỏ vào hồ sơ; tên/ảnh/phòng một nguồn.
- Xóa/chuyển phòng: chặn hoặc di dời cả hồ sơ, không để treo; đếm nhân sự phòng theo hồ sơ.
- Tách quyền sửa lương/BHXH khỏi quyền sửa hồ sơ; chặn ở tầng nghiệp vụ.
- Gộp "Hồ sơ của tôi" (tài khoản) và hồ sơ NV của tôi về một màn, một nguồn.

**4.2 Lịch làm việc & Ngày lễ** *(mới — nền)*
- Khai ngày lễ theo năm (âm/dương) + tuần làm việc chuẩn. Một API "ngày này có phải ngày làm việc không / công định mức tháng này" cho 3 module gọi chung.

**4.3 Chấm công & Ca**
- Bỏ bất công "chưa gán ca = trọn công": quy công theo một quy tắc thống nhất (đơn vị công chốt ở §6).
- Reset tự VÀO/RA theo ngày; trừ nghỉ giữa ca nếu cần; gom quy tắc ca (lặp 3 nơi) về một chỗ.
- Thêm kỳ công + nút Chốt (đóng băng); mở khóa có kiểm soát + ghi nhật ký.
- Nối OT & ca đêm thành số chảy được sang Lương.

**4.4 Nghỉ phép**
- Xóa bản leave-map chết (giữ 1 bản duy nhất).
- Dùng Lịch N3: không trừ phép vào ngày lễ; thống nhất đơn vị ngày (hiển thị vs trừ quota).
- Chuẩn hóa quota (thâm niên/cộng dồn — chốt ở §6), duyệt, nửa ngày (nếu cần).

**4.5 Lương (thời gian + khoán)**
- Đọc bản công đã chốt (không tính lại); công chuẩn động.
- Cắm OT + phụ cấp ca đêm; TNCN 7 bậc auto (dùng số người phụ thuộc + giảm trừ đã khai — chốt ở §6); BHXH có mức trần.
- Thêm trạng thái Đã chi + xuất Excel/file chuyển khoản.
- Ghi nhật ký cho generate/lock/sửa.
- Khoán: khóa kỳ đồng bộ với chốt lương; vá lỗi "tiền tổ trưởng bốc hơi" và "Σ hệ số = 0"; nguồn sản lượng (nối Sản xuất hay nhập tay — chốt ở §6).

## 5. Thứ tự triển khai (roadmap)
1. **Pha 0 — Nền người & tổ chức** (N1, N2, N5, gộp Hồ sơ của tôi).
2. **Pha 1 — Lịch & Ngày lễ** (N3).
3. **Pha 2 — Chấm công & Ca + Chốt công** (N4 nửa đầu).
4. **Pha 3 — Nghỉ phép** (dọn bản chết, nối lịch).
5. **Pha 4 — Lương thời gian** (đọc công chốt, OT/ca đêm/BHXH/TNCN, chi trả, nhật ký).
6. **Pha 5 — Lương khoán** (khóa kỳ, vá chia, nguồn sản lượng).

**NỢ Pha 5 (đã build Phần 1 + 5b-1 + 5b-2; còn để pha sau):**

- Phiếu lương khoán TÁCH DÒNG theo-người / theo-tổ — hiện gộp 1 cột "khoán"; tiền theo-người mới hiện ở tab Sản lượng (màn LSX), chưa hiện ở tab Lương khoán.
- Màn BÁO CÁO tỉ lệ hỏng theo thợ/tổ — mới có endpoint `GET /api/san-luong/defect-report`, chưa có màn riêng.
- ĐỐI CHIẾU sản lượng công đoạn với số lượng LSX + giấy xuất kho (cảnh báo mềm chống khai khống) — hoãn từ 5b, chưa làm.

> **Bẫy thực thi (bắt buộc nhớ):** không có Alembic → cột mới phải viết vào `backend/app/db_migrations.py` + cập nhật `docs/DB_SCHEMA.md` (có guard test); Boolean `server_default` phải `true`/`false` (không `"0"`/`"1"`); đổi route/schema phải restart uvicorn. Mỗi pha chạy `./init.ps1` xanh mới đi tiếp.

## 6. Tham số/chính sách cần chốt khi làm từng pha (chưa quyết)
- **Chấm công:** đơn vị công (theo giờ / theo buổi-nửa ca); dung sai đi muộn; OT có duyệt trước? hệ số OT (thường/CN/lễ); phụ cấp ca đêm %; ca xoay theo lịch phân ca?
- **Nghỉ phép:** phép năm mấy ngày + thâm niên? cộng dồn hay mất? nghỉ nửa ngày? loại nào có lương (ốm theo BHXH?); chặn xin ngày quá khứ/báo trước; nhập số dư đầu kỳ.
- **Lương:** BHXH đóng trên lương nào + mức trần; thử việc có đóng? TNCN auto ngay? hoa hồng KD auto từ đơn hàng hay nhập tay; chuyên cần khi nghỉ phép-có-lương.
- **Khoán:** nguồn sản lượng (Sản xuất/nhập tay); hệ số chia dựa gì; % tổ trưởng; "tổ" là phòng cấp dưới hay thực thể riêng.
- **Hồ sơ:** nhóm trường & field bắt buộc; `job_grade` "3/7" vs bậc lương chuẩn hóa — cái nào là nguồn thật; điều chuyển phòng có đổi vai trò tài khoản; ai duyệt yêu cầu đổi hồ sơ.

---
*Khảo sát nguồn: `models/{employee,department,profile_request,attendance,leave,payroll,piece_work}.py` · `services/{employee,department,attendance,leave,payroll,piece_work}_service.py` · routers tương ứng · FE `NhanSuPage/ChamCongPage/NghiPhepPage/LuongPage/HoSoCuaToiPage/DepartmentsPage.tsx` · `docs/spec-luong.md` · `docs/spec-nhan-su-ho-so.md`.*

---

## 7. CHỐT phân quyền HCNS + Kế toán lương (2026-07-15)

> **Trạng thái:** đã chốt thiết kế · **chưa build.**
> **Phạm vi lần này:** CHỈ mảng **HCNS** và **Kế toán liên quan tới lương**. Phía sản xuất (Quản đốc/Kỹ thuật/KCS/Tổ trưởng · đơn giá khoán · sản lượng · phân loại lỗi) **gác lại**, bàn đợt sau.

### 7.1 Nguyên tắc nền
Tách vai **đề xuất ≠ duyệt ≠ nhập ≠ chi**. **HCNS giữ *luật chơi + dấu vết*; Sản xuất giữ *định mức + hiện trường*; Kế toán giữ *khâu chi tiền*.** Không vai nào chạm cả hai đầu.

### 7.2 Vai
| Vai | Xử lý |
|---|---|
| **HCNS** (Trưởng phòng HCNS) | Giữ; **gỡ chi trả + gỡ nhập sản lượng** |
| **Kế toán lương** | **Role MỚI** (phòng Kế toán) — chỉ chi trả lương |
| **GĐ** (Giám đốc) | Thêm quyền **Duyệt chi** (duyệt quỹ = tổng tiền lương cả kỳ) |
| Kỹ thuật, KCS | **Gộp vào Quản đốc** — *deferred (phía sản xuất)* |
| Tổ trưởng | **Gộp vào Sản xuất** — *deferred (phía sản xuất)* |

### 7.3 Vòng đời bảng lương (thêm chặng "Đã duyệt")
```
Draft ─(HCNS: tính + Chốt số)─▶ Locked ─(GĐ: Duyệt chi)─▶ Approved ─(Kế toán: Chi)─▶ Paid
        ◀── Mở lại (HCNS) ──         ◀── Bỏ duyệt (GĐ) ──       ◀── Hủy chi (Kế toán) ──
```
- **GĐ duyệt quỹ = TRONG HỆ** (đã chốt): chưa duyệt thì nút "Chi" của Kế toán **bị khóa**; có dấu vết ai duyệt lúc nào.
- Hiện code chỉ có `draft → locked → paid`; **thêm trạng thái `approved`** vào giữa.

### 7.4 Ma trận quyền (3 vai liên quan)
| Module | **HCNS** | **Kế toán lương** | **GĐ** |
|---|---|---|---|
| `nhan_su` | full + view/edit_salary + adjust *(giữ)* | — | full |
| `nghi_phep` | duyệt tập trung *(giữ)* | self-service | full |
| `luong` | read·create·update·delete·export·manage_price — **KHÔNG approve, KHÔNG pay** | **read + `pay`(mới) + export** | full + **`approve` = Duyệt chi** |
| `san_luong` | **read** *(bỏ create/update)* | — | full |
| `nguoi_dung`/`phong_ban`/`vai_tro` | quản trị / read *(giữ)* | — | full |

→ HCNS mất đúng **2 thứ**: *chi trả* (→ Kế toán) và *nhập sản lượng* (→ read). Kế toán chỉ có **1 quyền mới**: bấm Chi + kéo file chuyển khoản (không sửa được số nào).

### 7.5 Việc kỹ thuật khi build (theo thứ tự)
1. 🔴 **Vá bug `get_matrix`/`save_matrix`** (`role_service.py`): `get_matrix` bỏ sót 3 cờ `can_view_salary`/`can_edit_salary`/`can_adjust` → mỗi lần Lưu ma trận qua UI, 3 cờ này **reset về False**. *Tiên quyết* (không vá thì cột `can_pay` mới cũng dễ dính lỗi y hệt).
2. **Thêm 1 cột `can_pay`** trên `role_permissions` (migration `db_migrations.py` + `DB_SCHEMA.md` + từ-vựng RBAC `rbac_service.py` + toggle FE). *"Duyệt chi" tái dùng `can_approve` đã có sẵn — không cần cột mới.*
3. **Trạng thái `approved`** cho `payroll_periods` + endpoint `POST /api/luong/approve` (GĐ) + re-gate `/pay`,`/unpay` từ `update` → `pay` (Kế toán); `pay` chỉ cho kỳ `approved`.
4. **Bổ sung audit** cho các thao tác HCNS đang KHÔNG ghi nhật ký: `params`, `rules`, `pit-brackets`, `set_salary/delete_salary`, duyệt/từ chối/hủy tạm ứng.
5. **Seed** (`seed.py`): thêm role *"Kế toán lương"* (phòng Kế toán, `luong` read+pay+export); sửa role HCNS (`luong` từ `_full` → bỏ `approve`+`pay`; `san_luong` từ `_full` → `read`).
6. **FE**: thêm toggle `can_pay` (+ vá luôn toggle `can_edit_salary` đang thiếu ở `PermissionMatrix`); nút "Duyệt chi" (GĐ) + khóa nút "Chi" theo trạng thái kỳ/vai.

### 7.6 Đơn giá khoán — hiểu chung (chưa build)
- Chỉ là **bảng giá công việc**: mỗi bộ phận (Dán/In/Bồi/Cắt…) một bảng; **mỗi việc một dòng, một giá** theo đơn vị (đ/hộp, đ/dây…). Biến thể "2 người / 3 người / móc đáy" = **các dòng việc khác nhau, mỗi dòng một giá** — không phải cấu trúc phức tạp.
- Hệ **đã có `piece_rates`** lưu đúng kiểu (1 dòng = 1 việc + 1 giá) — không phải dựng mới cấu trúc.
- Quyền: **Quản đốc đề xuất → GĐ duyệt → HCNS quản bản + lịch sử**. Nên tách thành **module "Đơn giá khoán" riêng** — thuộc **đợt bàn phía sản xuất**.

### 7.7 Còn treo (đã thống nhất gác)
- **Chia lương nội bộ tổ** (`piece_batch_shares`): ai gõ hệ số chia — để **"chưa bàn"**. Tạm thời quyền `luong` vẫn xử được.
- **Module đơn giá khoán + workflow đề xuất/duyệt** và các vai **Quản đốc/Kỹ thuật/KCS/Tổ trưởng** — bàn đợt phía sản xuất.
- **Độ sâu SoD** cho *sản lượng* (bước "Quản đốc xác nhận" + đối chiếu SL↔lệnh SX↔nhập kho) và *phân loại lỗi* (KCS + biên bản ký) — mới ở mức đề xuất, **chưa chốt**.
- **Lỗ hổng Tầng 3** (ghi nhận từ context, chưa quyết): thêm ô *"lao động nặng nhọc–độc hại"* trên hồ sơ; chỗ ghi nhận *tai nạn lao động (TNLĐ)*.
