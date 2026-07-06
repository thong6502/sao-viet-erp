# Spec — Hồ sơ nhân sự (module `nhan_su`, lát #1)

> Phân hệ HCNS · Nhân sự. Đây là lát cắt **#1** của module `nhan_su` (§16/§38/§39
> `DOMAIN_NHA_MAY_IN.md`): **Hồ sơ nhân viên**. Các lát sau (Hợp đồng LĐ, Chấm công &
> Ca kíp, Nghỉ phép, Lương) dùng chung `module_key` `nhan_su` / thêm `luong`.

## 0. Phạm vi

**Trong lát #1**
- 3 bảng: `employees`, `employee_events` (Quá trình công tác), `employee_attachments`.
- Màn **Danh sách** (KPI + tìm/lọc/sắp/phân trang, scope theo phòng) + **Trang hồ sơ**
  (tab **Thông tin · Quá trình công tác · Đính kèm · Nhật ký**).
- **Wizard** thêm NV (5 bước) + **dialog** Đổi trạng thái / Điều chuyển / Nâng bậc (sinh
  `employee_event`) + **nối/tạo tài khoản** login.

**Ngoài lát #1 (làm sau)**
- Hợp đồng LĐ, Chấm công/Ca kíp, Nghỉ phép, Lương (khoán).
- Scope `own` (NV tự xem hồ sơ mình) — lát này chỉ `department`/`all` cho HCNS.
- Các tab "chưa có phân hệ" (Chấm công/Lương/HĐ) — chưa render.

## 1. Data model
Xem `DB_SCHEMA.md` mục `employees` / `employee_events` / `employee_attachments`.
Điểm chốt:
- `code` = `NV###` tự sinh (max+1, không tái dùng), read-only.
- `user_id` **UNIQUE nullable** = nối login 1–1 tùy chọn.
- `national_id` / `social_insurance_no` **indexed, KHÔNG unique** → check trùng **mềm**.
- 3 bảng đều mới → `create_all` tự tạo (cả local lẫn live), **không** đụng `db_migrations.py`.

## 2. Vòng đời trạng thái (state machine)
Đổi giai đoạn KHÔNG sửa cột trực tiếp — đi qua **transition** (ghi `employee_event`, có
`effective_date`):

| From → To | event_type | Ràng buộc |
|---|---|---|
| probation → active | `confirmed` | effective_date |
| active ⇄ on_leave | `leave_start` / `leave_end` | ghi chú loại nghỉ |
| (active/probation/on_leave) → suspended | `suspended` | note |
| bất kỳ → resigned | `resigned` | **resign_date + resign_reason bắt buộc**; sau đó khóa sửa |
| resigned → active | `reinstated` | tuyển lại |
| (đổi department) | `transferred` | effective_date, from→to phòng |
| (đổi job_grade) | `promoted` | from→to bậc |

Chặn chuyển tiếp vô lý (vd resigned→active phải qua `reinstated`, không nhảy thẳng).

## 3. API (`/api/employees`, gate `require_permission('nhan_su', <action>)`)

| Method · Path | Action | Việc |
|---|---|---|
| `GET /api/employees` | read | List: scope + q + lọc(phòng/trạng thái/có-TK) + sort + phân trang + KPIs |
| `GET /api/employees/meta` | read | Dropdown: phòng ban, users chưa gắn NV |
| `POST /api/employees` | create | Tạo NV → cấp `NV###` + event `hired` + (tùy chọn) tạo user; trả cảnh báo trùng CCCD/BHXH |
| `GET /api/employees/{id}` | read | Chi tiết hồ sơ |
| `PUT /api/employees/{id}` | update | Sửa hồ sơ (KHÔNG đổi status/dept/grade ở đây) |
| `POST /api/employees/{id}/transitions` | update | Đổi trạng thái/điều chuyển/nâng bậc → ghi event |
| `GET /api/employees/{id}/events` | read | Quá trình công tác |
| `GET /api/employees/{id}/activity` | read | Nhật ký (audit lọc theo NV) |
| `GET/POST /api/employees/{id}/attachments` · `DELETE …/{aid}` | read/update | Liệt kê / upload (multipart) / xóa file |
| `POST /api/employees/{id}/account` · `DELETE` | update | Nối/tạo · gỡ tài khoản login |

Quy tắc service: họ tên non-blank · CCCD/BHXH trùng = **cảnh báo mềm** (vẫn lưu) · status &
event_type trong enum · `user_id` set phải tồn tại + chưa gắn NV khác (UNIQUE + báo lỗi thân
thiện) · mỗi create/update/transition ghi `audit_logs` (target `employee:<id>`).

## 4. Wizard Thêm (5 bước)
1. **Định danh & việc làm** (bắt buộc: họ tên · phòng · ngày vào; status mặc định *Thử việc*
   → hiện `probation_end_date` gợi ý +2 tháng).
2. **Cá nhân** (+ cảnh báo trùng CCCD inline).
3. **BHXH / TNCN** (+ bậc thợ).
4. **Đính kèm** (upload HĐ/CCCD/bằng cấp).
5. **Tài khoản** (tùy chọn) → **Xem lại → Lưu**.

Lưu ⇒ cấp mã · tạo `employees` · **tự ghi event `hired`** (effective_date = ngày vào) ·
(nếu tick) tạo `users` + gắn `user_id` · ghi audit · chuyển tới trang hồ sơ.

## 5. RBAC
- `module_key = 'nhan_su'`; seed thêm `("nhan_su","Nhân sự")` vào `MODULES` + cấp **W**
  (RCU) cho vai trò **Trưởng phòng HCNS**.
- Scope lát #1: `department` / `all` (HCNS). Sửa BHXH/bậc/trạng thái đều dưới `update` của `nhan_su`.

## 6. Seam & ‹chờ SVN›
- `employees` = **provider sẵn** cho **SEAM-19** (đóng khi Tài xế build; chưa làm gì thêm giờ).
- ‹mặc định, xác nhận sau›: prefix `NV###`, thang **bậc thợ**.

## 7. File
- BE: `models/employee.py` · `repositories/employee_repo.py` · `services/employee_service.py`
  · `schemas/employee.py` · `routers/employees.py` + wiring `deps.py` + include `main.py`
  + seed + `DB_SCHEMA.md` (3 mục) + `tests/test_employees_api.py`.
- FE: `pages/NhanSuPage.tsx` + `nhan-su.css` + đăng ký `Sidebar.tsx`/`App.tsx`/`auth/permissions.tsx`
  (tái dùng `Timeline`, `StatusTabs`, `Field`, `Select`, `ConfirmDialog`, `Button`, `api/client.ts`).
