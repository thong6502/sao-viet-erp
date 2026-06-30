# Spec-04 — Hồ sơ & Cài đặt cá nhân (User Profile & Settings)

## Goal

Cho phép người dùng đã đăng nhập xem và tự chỉnh sửa thông tin cá nhân (tên hiển thị, avatar, mật khẩu) thông qua một widget ở cuối sidebar, mà không cần rời khỏi trang đang dùng.

## Screens

- **User Widget (bottom sidebar)** — avatar thu nhỏ + tên đăng nhập + nút mở menu; luôn hiển thị ở cuối sidebar khi đã đăng nhập.
- **Profile Dropdown / Popover** — mở ra khi bấm widget, liệt kê 4 mục: Thông tin tài khoản · Đổi tên · Đổi avatar · Đổi mật khẩu + nút Đăng xuất ở cuối.
- **Thông tin tài khoản** — panel/modal chỉ đọc: avatar lớn, tên hiển thị, tên đăng nhập, phòng ban, vai trò, ngày tạo.
- **Đổi tên** — form 1 trường (tên hiển thị mới), validate không trống và ≤ 100 ký tự.
- **Đổi avatar** — upload ảnh (JPG/PNG, ≤ 2 MB), xem preview trước khi lưu, có nút xoá avatar về mặc định.
- **Đổi mật khẩu** — form 3 trường: mật khẩu hiện tại · mật khẩu mới · xác nhận mật khẩu mới; đổi xong vô hiệu mọi phiên cũ và trả về Login.

## Features

- **Widget sidebar** — avatar hình tròn (fallback chữ cái đầu tên nếu chưa có ảnh) + tên đăng nhập; bấm mở Dropdown.
- **Dropdown menu** — 4 mục + Đăng xuất; bấm ra ngoài thì đóng.
- **Thông tin tài khoản** — đọc từ `GET /api/auth/me` (đã có), hiển thị đầy đủ trường.
- **Đổi tên** — `PATCH /api/users/me` `{ name }` → cập nhật ngay trên widget + header không cần reload.
- **Đổi avatar** — `POST /api/users/me/avatar` (multipart) → lưu file, trả URL; `DELETE /api/users/me/avatar` để xoá về mặc định; avatar hiển thị cập nhật ngay trên widget.
- **Đổi mật khẩu** — `POST /api/auth/change-password` `{ current_password, new_password }` → backend bcrypt-verify → hash mới → bump `token_version` → revoke tất cả refresh token → 204 → frontend logout về Login.

## Logic / flow

> Luồng chính:

1. Người dùng nhìn thấy avatar + tên mình ở **cuối sidebar** (luôn hiển thị).
2. Bấm widget → **Dropdown** mở ra với 4 mục + Đăng xuất.
3. Chọn **Thông tin tài khoản** → panel mở, hiển thị toàn bộ thông tin chỉ đọc.
4. Chọn **Đổi tên** → form 1 trường; nhập tên mới → Lưu → `PATCH /api/users/me` → widget cập nhật tên ngay; thông báo thành công.
5. Chọn **Đổi avatar** → dialog upload; chọn file → xem preview → Lưu → `POST /api/users/me/avatar` → widget cập nhật ảnh ngay; hoặc bấm Xoá avatar → `DELETE /api/users/me/avatar` → về fallback chữ cái.
6. Chọn **Đổi mật khẩu** → form 3 trường; client validate → `POST /api/auth/change-password` → 204 → frontend xóa token + cookie → chuyển về Login với thông báo "Đổi mật khẩu thành công. Vui lòng đăng nhập lại."

## System statuses

- **Mất kết nối / lỗi mạng** — hiển thị thông báo lỗi chung, giữ nguyên form, cho phép thử lại.
- **Phiên hết hạn giữa chừng** — silent refresh (feat-016) tự xử lý; nếu refresh hỏng thì chuyển về Login.
- **Backend lỗi 5xx** — hiển thị "Có lỗi xảy ra, vui lòng thử lại sau"; không tự logout.

## Edge cases

- **Chưa có avatar** — widget hiển thị fallback hình tròn màu accent, chữ cái đầu của tên.
- **Ảnh vượt 2 MB hoặc sai định dạng** — client validate trước upload, không gửi request.
- **Tên mới trùng tên cũ** — vẫn cho lưu (không cần block).
- **Mật khẩu mới trùng mật khẩu hiện tại** — backend từ chối 400 "Mật khẩu mới phải khác mật khẩu hiện tại."
- **Mật khẩu mới không khớp xác nhận** — client validate, không gửi request.
- **Double-submit** — nút Lưu disable khi đang loading.
- **Dropdown mở khi sidebar thu nhỏ** — Dropdown vẫn hiển thị đúng (không bị che).

## Acceptance criteria

> Xác minh trên `./init.ps1` green + browser-validate.

**Widget & Dropdown**
- Widget hiển thị ở cuối sidebar sau khi đăng nhập; có avatar (hoặc fallback chữ cái) + tên đăng nhập.
- Bấm widget → Dropdown mở với 4 mục + Đăng xuất.
- Bấm ra ngoài Dropdown → đóng.

**Thông tin tài khoản**
- Mở panel → hiển thị đủ: avatar, tên hiển thị, tên đăng nhập, phòng ban, vai trò, ngày tạo.

**Đổi tên**
- Submit tên hợp lệ → `PATCH /api/users/me` 200 → widget cập nhật tên ngay (không reload).
- Submit tên trống → lỗi client, không gửi request.

**Đổi avatar**
- Chọn ảnh hợp lệ → preview hiển thị → Lưu → `POST /api/users/me/avatar` 200 → widget cập nhật ảnh ngay.
- Chọn file > 2 MB hoặc không phải JPG/PNG → lỗi client, không gửi request.
- Bấm Xoá avatar → `DELETE /api/users/me/avatar` 204 → widget về fallback chữ cái.

**Đổi mật khẩu**
- Submit đúng mật khẩu hiện tại + mật khẩu mới hợp lệ → 204 → chuyển về Login với thông báo thành công.
- Submit sai mật khẩu hiện tại → 400 → hiển thị "Mật khẩu hiện tại không đúng"; giữ form.
- Mật khẩu mới trùng cũ → 400 → hiển thị lỗi phù hợp.
- Sau khi đổi mật khẩu, access token cũ bị từ chối (401); refresh token cũ bị từ chối (401).
- `./init.ps1` passed (pytest + compileall).
- Console browser sạch.

## Out-of-scope

- Quên mật khẩu / reset qua email.
- Admin đặt lại mật khẩu cho user khác.
- Đổi ngôn ngữ / theme (spec riêng).
- Thông báo (notification) từ hệ thống.
- Lịch sử mật khẩu (không tái sử dụng N mật khẩu gần nhất).

## Failure states

- **Sai mật khẩu hiện tại** → 400; form giữ nguyên, cho nhập lại.
- **Mật khẩu mới quá yếu** (validate server-side) → 422; message chỉ rõ tiêu chí thiếu.
- **Upload avatar lỗi server** → thông báo lỗi, giữ nguyên ảnh cũ.
- **PATCH tên lỗi server** → thông báo lỗi, giữ nguyên tên cũ.
