# Spec-05 — Quản lý Phòng ban: mã tự sinh, mô tả, cây đơn vị & xoá theo nhánh

> Actor: **Admin, HCNS** (người có quyền trên module `phong_ban`).
> Mở rộng phần Phòng ban đã có ở spec-02 (feat-008). Gồm PBI-4002 (Tạo), PBI-4003 (Sửa),
> PBI-4005 (Xoá có chặn).

## Goal

Là HCNS/Admin, tôi muốn tạo/sửa/xoá phòng ban (đơn vị) một cách an toàn — có **mã phòng tự sinh
duy nhất**, **mô tả**, tổ chức theo **cây cha–con**, và khi xoá thì xoá cả nhánh con nhưng **không
làm mất nhân sự** — để cơ cấu tổ chức luôn đúng và truy vết được.

## Screens

- **Quản lý Phòng ban (danh sách/cây)** — danh sách phòng ban kèm **mã** + tên (+ mô tả); thể hiện quan hệ cha–con.
- **Tạo phòng ban** — form: tên (bắt buộc, không trùng), mô tả (tuỳ chọn), **chọn phòng cha (tuỳ chọn)**; ô **mã hiển thị chỉ-đọc** ("(tự sinh)" trước khi lưu; mã thật `PB###` hiện sau khi tạo).
- **Sửa phòng ban** — form: sửa tên (không trùng) + mô tả; **mã chỉ hiển thị, không sửa**.
- **Xoá phòng ban** — hộp xác nhận liệt kê **toàn bộ đơn vị trong nhánh sẽ bị xoá**; chặn nếu nhánh còn nhân sự.

## Features

### PBI-4002 — Tạo phòng ban
- Tên **bắt buộc**, **không trùng** → trùng thì báo lỗi **ngay tại ô nhập** (inline, không submit).
- Hệ thống **tự sinh mã phòng duy nhất**, hiển thị **chỉ-đọc**, người dùng không nhập.
- **Mô tả** tuỳ chọn.
- Tạo xong **hiện trong danh sách kèm mã**.
- **Ghi nhật ký** (AuditLog: create_department).

### PBI-4003 — Sửa phòng ban
- Sửa **tên** (không trùng) và **mô tả**.
- **Mã** chỉ hiển thị, **không cho sửa**.
- Lưu xong **cập nhật ngay** trong danh sách.
- **Ghi nhật ký** (update_department).

### PBI-4005 — Xoá phòng ban (có chặn)
- Xoá một đơn vị sẽ **xoá cả nhánh con** (đệ quy toàn bộ subtree).
- Trước khi xoá **hiển thị xác nhận kèm danh sách các đơn vị sẽ bị xoá**.
- **Chặn xoá nếu trong nhánh còn nhân sự** (user thuộc bất kỳ đơn vị nào trong nhánh) → nêu rõ lý do
  ("phải chuyển người đi trước", liệt kê đơn vị còn người).
- **Vai trò thuộc các đơn vị trong nhánh bị xoá theo** (khi không còn ai giữ — đã đảm bảo vì đã chặn nếu còn người).
- **Ghi nhật ký từng đơn vị bị xoá** (mỗi đơn vị một dòng delete_department).

## Logic / flow

1. HCNS vào **Quản lý Phòng ban**, thấy danh sách/cây có mã + tên (+ mô tả).
2. **Tạo:** mở form → nhập tên (+ mô tả, + cân nhắc chọn cha); mã hiện chỗ chỉ-đọc; nhập tên trùng →
   lỗi inline tại ô tên; Lưu hợp lệ → tạo + sinh mã → xuất hiện trong danh sách kèm mã; ghi nhật ký.
3. **Sửa:** mở form của một phòng → mã chỉ hiển thị; sửa tên (không trùng) + mô tả → Lưu → danh sách cập
   nhật ngay; ghi nhật ký.
4. **Xoá:** bấm xoá một đơn vị → hộp xác nhận liệt kê **mọi đơn vị trong nhánh** sẽ bị xoá → nếu nhánh
   còn nhân sự thì **chặn** + nêu lý do; nếu không, xác nhận → xoá cả nhánh (đơn vị + vai trò của chúng);
   ghi một dòng nhật ký cho **từng** đơn vị bị xoá.

## System statuses

- **Mất kết nối / lỗi mạng** — báo lỗi chung, giữ form, cho thử lại.
- **Phiên hết hạn** — silent refresh (feat-016); hỏng thì về Login.
- **Backend 5xx** — "Có lỗi xảy ra, vui lòng thử lại sau"; không tự logout.

## Edge cases

- **Tên trống / chỉ khoảng trắng** — chặn, báo lỗi tại ô nhập (không submit).
- **Tên trùng** (tạo hoặc sửa) — lỗi inline tại ô tên; không lưu.
- **Mã** — không bao giờ do người dùng nhập/sửa; đảm bảo **duy nhất** kể cả khi tạo nhiều nhanh (chống đụng).
- **Xoá nhánh sâu nhiều cấp** — gom đệ quy đúng toàn bộ subtree (không sót, không lặp).
- **Chặn xoá** — chỉ cần một đơn vị bất kỳ trong nhánh còn ≥1 nhân sự là chặn cả thao tác.
- **Double-submit** — nút Lưu/Xoá disable khi đang chạy.
- **Phòng cha bị xoá** — con của nó cũng phải biến mất khỏi danh sách ngay.

## Acceptance criteria

> Xác minh trên `./init.ps1` green + browser-validate.

1. **Tạo:** tên bắt buộc + không trùng (trùng → lỗi ngay tại ô nhập, không gọi tạo); mã tự sinh **duy nhất**
   hiển thị chỉ-đọc (người dùng không nhập được); mô tả tuỳ chọn; tạo xong phòng xuất hiện trong danh sách
   **kèm mã**; có dòng AuditLog create_department.
2. **Sửa:** sửa được tên (không trùng) + mô tả; ô **mã** chỉ đọc; lưu xong danh sách cập nhật ngay; có
   AuditLog update_department.
3. **Xoá:** hộp xác nhận liệt kê **đầy đủ** các đơn vị trong nhánh sẽ bị xoá; nếu nhánh còn nhân sự → **chặn**
   + nêu lý do (đơn vị nào còn người); nếu xoá được → toàn bộ đơn vị trong nhánh **và** vai trò của chúng bị
   xoá; có **một AuditLog cho mỗi** đơn vị bị xoá.
4. Trạng thái **đang tải** + **báo lỗi** đầy đủ; mất mạng cho thử lại.
5. Người **không có quyền** trên `phong_ban` (read để xem; create/update/delete cho thao tác tương ứng) bị
   từ chối **403**.
6. `./init.ps1` passed (pytest + compileall, gồm DB_SCHEMA guard cho cột/bảng mới); console browser sạch.

## Out-of-scope

- Di chuyển/ghép phòng ban (re-parent) sau khi tạo — chỉ chọn cha **lúc tạo**.
- Đổi mã phòng thủ công.
- Khôi phục (undo) phòng đã xoá.
- Chuyển nhân sự hàng loạt (chỉ nêu lý do chặn; việc chuyển người dùng luồng feat-009).

## Failure states

- **Tên trùng** → lỗi inline tại ô tên, giữ form.
- **Xoá khi nhánh còn người** → 409 + thông báo nêu rõ đơn vị còn nhân sự; không xoá gì.
- **Lưu/Xoá lỗi server** → giữ nguyên trạng thái, báo lỗi, cho thử lại.
- **Thiếu quyền** → 403 "Bạn không có quyền thực hiện thao tác này".

## Resolved decisions (Planner, 2026-06-30)

1. **Cây cha–con:** thêm cột `parent_id` (FK self → `departments.id`, nullable, index) cho `departments`.
   Form **Tạo** cho chọn **phòng cha (tuỳ chọn)**; không chọn → phòng gốc (parent_id null). Re-parent
   (đổi cha sau khi tạo) **ngoài phạm vi** spec này.
2. **Mã phòng:** sinh **tuần tự `PB` + số zero-pad** (`PB001`, `PB002`, …), duy nhất, chỉ-đọc, hệ thống
   sinh — người dùng không nhập/sửa. Sinh dựa trên số phòng hiện có/sequence + đảm bảo không đụng (unique).
3. **Đổi hành vi xoá (feat-008):** delete cũ chặn khi còn **vai trò HOẶC người**. PBI-4005 đổi thành: xoá
   theo **nhánh**, **chỉ chặn khi trong nhánh còn người**; **vai trò trong nhánh bị xoá theo**. Cập nhật
   `department_service.delete` + các test feat-008 liên quan.
