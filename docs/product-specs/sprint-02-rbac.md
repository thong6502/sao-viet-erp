# Sprint 02 — RBAC: Phòng ban · Vai trò · Phân quyền (CRUD + Phạm vi dữ liệu)

## Goal

Dựng nền phân quyền cho hệ thống ERP nhà máy in: mỗi nhân viên có **1 tài khoản**,
thuộc **1 phòng ban**, giữ **1 vai trò** (vai trò định nghĩa riêng cho từng phòng).
Mỗi vai trò quy định, theo từng **module**: được làm gì (**CRUD** = Xem/Thêm/Sửa/Xóa)
và được thấy dữ liệu của ai (**Phạm vi** = Của tôi / Cả phòng / Tất cả). Việc cấp tài
khoản tách vai theo tổ chức: **HR** gán phòng ban, **trưởng phòng** gán vai trò,
**Admin/GĐ** định nghĩa khuôn vai trò.

> Yêu cầu bắt buộc ngay từ đầu: *"NV Sales chỉ thấy khách của mình"* → phạm vi dữ liệu
> là một phần của bản phát hành này, không hoãn lại.

## Mô hình & sở hữu (ai làm gì)

```text
Phòng ban ─chứa─► Vai trò ─gán cho─► Tài khoản  (1 người = 1 vai trò)

Mỗi Vai trò, theo từng Module:
   • CRUD   : Xem / Thêm / Sửa / Xóa        (được làm thao tác gì)
   • Phạm vi: Của tôi / Cả phòng / Tất cả   (được thấy dữ liệu của ai)

   HR           → tạo tài khoản + gán PHÒNG BAN + xử lý nghỉ việc (khóa)
   Trưởng phòng → gán VAI TRÒ (chỉ trong các vai trò của phòng mình)
   Admin/GĐ     → định nghĩa khuôn vai trò (CRUD + Phạm vi) cho từng phòng
```

- **Của tôi** = bản ghi có *người phụ trách = chính mình*.
- **Cả phòng** = bản ghi có *người phụ trách cùng phòng với mình*.
- **Tất cả** = không giới hạn.

## Data model (entities)

- **Department (phòng ban)**: `id`, `name`, `head_user_id` (người đứng đầu — nullable).
- **Role (vai trò)**: `id`, `name`, `department_id` (vai trò thuộc đúng 1 phòng).
- **RolePermission**: `role_id`, `module_key`, `can_read`, `can_create`, `can_update`,
  `can_delete`, `scope` ∈ {`own`, `department`, `all`}. Một dòng / (vai trò × module).
- **User (tài khoản)** — mở rộng model auth sprint-01: thêm `department_id`, `role_id`
  (đúng 1), `is_active`. (Đăng nhập vẫn dùng cơ chế JWT của sprint-01.)
- **Module**: danh mục module hệ thống — là **dữ liệu seed, mở rộng dần** (không phải đổi
  cấu trúc). Giai đoạn này **chỉ phủ 2 phòng Kinh doanh + Hành chính nhân sự**:
  - Kinh doanh: `dashboard`, `khach_hang`, `don_hang_ban`, `bao_gia`, `tinh_gia_thanh`,
    `san_pham`, `hop_dong`
  - Quản trị / HCNS: `phong_ban`, `vai_tro`, `nguoi_dung`, `activity_log`
  > Module của các phòng khác (`san_xuat`, `kho`, `thu_mua`, …) **thêm vào danh mục khi
  > phòng đó lên hệ thống** — chỉ là thêm dòng dữ liệu, không sửa schema.
- **AuditLog**: `id`, `actor_user_id`, `action`, `target`, `detail`, `created_at` —
  ghi lại mọi thay đổi gán phòng / gán vai trò / sửa khuôn quyền / khóa tài khoản.

> Phạm vi dữ liệu cần mỗi bản ghi nghiệp vụ mang **người phụ trách + phòng**. Module
> Khách hàng (CRM) đã bắt buộc trường "Người phụ trách", nên tầng kiểm quyền dựng ở
> sprint này; *hiệu lực lọc "Của tôi/Cả phòng" hiển thị đầy đủ khi module Khách hàng ra đời*
> (sprint CRM). Sprint này verify tầng kiểm quyền + các màn quản trị.

## Screens

- **Quản lý Vai trò (Roles)** — danh sách vai trò theo phòng + **ma trận quyền**: mỗi
  dòng là một module với toggle Xem/Thêm/Sửa/Xóa và ô chọn **Phạm vi**; nút Lưu / Hủy.
  (Đúng layout ảnh tham chiếu RBAC, có thêm cột Phạm vi.)
- **Quản lý Phòng ban (Departments)** — danh sách phòng, các vai trò trong phòng, và
  người đứng đầu phòng.
- **Quản lý Người dùng (Users)** — HR tạo tài khoản + gán phòng; trưởng phòng gán vai
  trò (chỉ thấy vai trò của phòng mình); khóa/mở tài khoản.
- **Activity Log** — nhật ký các thay đổi phân quyền (chỉ xem).

## Features

- Phòng ban: tạo/sửa/xóa; đặt người đứng đầu phòng.
- Vai trò theo phòng: tạo/sửa/xóa; khuôn quyền = ma trận (CRUD + Phạm vi) trên mọi module.
- Tài khoản: HR tạo + gán phòng; trưởng phòng gán đúng 1 vai trò trong phòng; khóa tài khoản.
- **Tầng kiểm quyền (backend)**: mọi API kiểm tra vai trò của người gọi cho
  (module, action) trước khi cho phép; thiếu quyền → `403`.
- **Lọc theo phạm vi (backend)**: truy vấn danh sách tự lọc theo `scope` của vai trò
  (own → theo người phụ trách; department → theo phòng; all → không lọc).
- **Sidebar/menu theo quyền (frontend)**: chỉ hiện module mà vai trò có quyền Xem.
- Seed khởi tạo: tài khoản **Admin/GĐ** (toàn quyền, scope = all) — kế thừa seed admin
  sprint-01; vai trò **HR** (quản lý người dùng + phòng ban); một số vai trò mẫu phòng KD
  (Trưởng phòng KD = cả phòng, NV Sales = của tôi).
- Vai trò **mặc định tối thiểu (chỉ Xem)** cho nhân viên mới khi trưởng phòng chưa gán.
- Ghi **AuditLog** cho mọi lần gán phòng / gán vai trò / sửa khuôn quyền / khóa tài khoản.

## Logic / flow

1. **HR tạo nhân viên mới** → nhập thông tin + chọn **phòng ban** → lưu → tài khoản
   nhận **vai trò mặc định tối thiểu (chỉ Xem)**, trạng thái hoạt động.
2. **Trưởng phòng** mở Người dùng (lọc phòng mình) → chọn nhân viên → **gán vai trò**
   (danh sách chỉ gồm vai trò của phòng mình) → lưu → ghi AuditLog → quyền có hiệu lực
   ở lần gọi/đăng nhập kế tiếp.
3. **Admin/GĐ định nghĩa vai trò**: mở Vai trò → chọn phòng → tạo/sửa vai trò → bật/tắt
   CRUD + chọn Phạm vi theo từng module → Lưu → ghi AuditLog.
4. **Người dùng đăng nhập** → backend nạp vai trò + khuôn quyền; **sidebar chỉ hiện**
   module có quyền Xem.
5. **Gọi API bị thiếu quyền** (vd NV Sales gọi xóa khách) → `403`, frontend báo
   "Bạn không có quyền thực hiện thao tác này".
6. **Lọc phạm vi**: NV Sales (scope = own) mở danh sách → chỉ thấy bản ghi mình phụ
   trách; Trưởng phòng (department) thấy cả phòng; GĐ (all) thấy tất cả.
7. **Nghỉ việc**: HR/GĐ **khóa tài khoản** → người đó không đăng nhập được; bàn giao dữ
   liệu phụ trách xử lý ở luồng CRM-05 (sprint CRM).

## System statuses

- **Chưa đăng nhập / phiên hết hạn** — `401`, đưa về Login (cơ chế sprint-01).
- **Đã đăng nhập nhưng thiếu quyền** — `403` với thông báo ngôn ngữ thường + lối thoát
  (về trang được phép), không phải stack/JSON thô.
- **Backend lỗi / không truy cập được** — thông báo dễ hiểu + Retry; không bao giờ màn trắng.

## Edge cases

- **Trưởng phòng cố gán vai trò của phòng khác** → bị chặn; danh sách chỉ có vai trò
  phòng mình.
- **Xóa vai trò đang được gán cho người dùng** → chặn, yêu cầu chuyển người sang vai trò
  khác trước (không để tài khoản mất vai trò).
- **Xóa/đổi phòng của người dùng** → vai trò cũ (thuộc phòng cũ) không còn hợp lệ → tự
  hạ về vai trò mặc định tối thiểu của phòng mới, chờ trưởng phòng mới gán.
- **Phòng chưa có người đứng đầu** → HR/GĐ giữ tạm quyền gán vai trò cho phòng đó.
- **Tự nâng quyền**: trưởng phòng **không** sửa được khuôn quyền (chỉ Admin/GĐ), nên
  không thể tự cấp quyền cao hơn.
- **Người dùng bị khóa** vẫn còn token cũ → request kế tiếp bị từ chối (kiểm `is_active`).
- **Đầu vào lạ / dài bất thường** → xử lý như dữ liệu, ORM/tham số ràng buộc (không nối SQL).

## Validation & UI states (per màn)

> Mỗi màn có dữ liệu/hành động phải xử lý đủ: **trống / đang tải / lỗi / thành công**
> (docs/UI_DESIGN.md), không bao giờ màn trắng hay đứng hình.

### Quản lý Vai trò

- Tên vai trò: **bắt buộc**, **duy nhất trong cùng phòng** (trùng → báo lỗi inline, không lưu).
- Phải gắn đúng 1 phòng ban; mỗi dòng module phải có 1 giá trị Phạm vi hợp lệ (own/department/all).
- Trống: phòng chưa có vai trò → panel "Chưa có vai trò" + nút Tạo. Đang tải ma trận: skeleton.
- Lỗi lưu (mạng/5xx): banner lỗi + Retry, không mất các toggle đang chỉnh.
- Chỉ Admin/GĐ vào được màn này; người khác → `403` + đưa về nơi được phép.

### Quản lý Phòng ban

- Tên phòng: **bắt buộc**, **duy nhất**. Người đứng đầu: chọn từ user thuộc phòng đó.
- Trống: chưa có phòng → empty state + nút Tạo. Xóa phòng còn vai trò/người dùng → chặn kèm lý do.

### Quản lý Người dùng

- Tạo tài khoản (HR): họ tên + email **bắt buộc**, email **đúng định dạng + duy nhất**;
  phòng ban **bắt buộc**. Mật khẩu khởi tạo theo cơ chế sprint-01.
- Gán vai trò (trưởng phòng): dropdown **chỉ** liệt kê vai trò của phòng người dùng; rỗng
  nếu phòng chưa định nghĩa vai trò (gợi ý nhờ Admin tạo).
- Double-submit (tạo/gán) → nút khóa + loading; không tạo trùng / không gán trùng.
- Lọc rỗng (không có user khớp) → "Không có người dùng" thay vì bảng trống không lời.

### Activity Log

- Trống: "Chưa có hoạt động". Đang tải: skeleton. Lỗi tải: thông báo + Retry.

## Acceptance criteria

> Tiêu chí UI là các khẳng định quan sát được trên trình duyệt (snapshot/text/state),
> xác nhận TRÊN NỀN `./init.sh` / `./init.ps1` xanh (pytest + compileall).

- `init.ps1` / `init.sh` pass: `python -m pytest` (gồm test RBAC) + `compileall`.
- Một API có bảo vệ: người dùng có quyền → `200`; người dùng **thiếu** quyền cho
  (module, action) → `403`; chưa đăng nhập → `401`.
- Lọc phạm vi (test backend): với cùng tập dữ liệu có `người phụ trách`/`phòng`, vai trò
  `own` chỉ trả bản ghi của chính mình; `department` trả cả phòng; `all` trả tất cả.
- Màn **Vai trò**: snapshot hiện ma trận module × (Xem/Thêm/Sửa/Xóa + Phạm vi); bật/tắt
  một quyền rồi Lưu → tải lại vẫn giữ đúng trạng thái.
- **Validation**: tạo vai trò trùng tên trong cùng phòng → lỗi inline, không lưu; tạo phòng
  trùng tên → lỗi; tạo user thiếu email/họ tên/phòng hoặc email sai định dạng/trùng →
  highlight trường lỗi, không tạo.
- **Trạng thái rỗng/lỗi**: phòng chưa có vai trò → empty state có nút Tạo (không phải bảng
  trống); lỗi lưu (5xx/mạng) → banner + Retry, các toggle đang chỉnh không mất.
- Màn **Người dùng**: HR tạo tài khoản + gán phòng → người dùng xuất hiện với vai trò
  mặc định tối thiểu; trưởng phòng gán vai trò → danh sách vai trò **chỉ** gồm vai trò
  phòng đó; sau gán, vai trò người dùng cập nhật.
- **Menu theo quyền**: tài khoản chỉ có quyền Xem Dashboard → sidebar chỉ hiện Dashboard
  (không hiện Khách hàng/Đơn hàng…).
- **Khóa tài khoản**: sau khi khóa, đăng nhập/`/me` của tài khoản đó bị từ chối.
- **AuditLog**: mỗi lần gán phòng / gán vai trò / sửa khuôn quyền / khóa tài khoản tạo
  đúng 1 dòng log (actor, action, target, thời gian).
- Console sạch lỗi suốt hành trình; chỉ các call mong đợi với status mong đợi.

## Out-of-scope

- **Nhiều vai trò / người** (sprint này: đúng 1 vai trò/người). Người kiêm nhiệm → tạo
  một vai trò riêng.
- **Vai trò dùng chung nhiều phòng / phân cấp "không cao hơn cấp mình"** (sprint này:
  trưởng phòng chỉ giới hạn theo phòng, chưa theo bậc).
- **Ngày hiệu lực / lịch sử có thời hạn** của việc gán (áp dụng tức thời).
- **Bàn giao khách khi nghỉ việc** (luồng CRM-05) và toàn bộ dữ liệu Khách hàng/Đơn hàng
  — thuộc sprint CRM; sprint này chỉ dựng tầng quyền + phạm vi để CRM tiêu thụ.
- **Các phòng/module ngoài Kinh doanh + Hành chính nhân sự** (Sản xuất, Kho, Thu mua…):
  chỉ thêm vào danh mục module (seed) khi phòng đó lên hệ thống — không thuộc sprint này.
- SSO / 2FA / quên mật khẩu / tự đăng ký.

## Failure states

- Thiếu quyền (`403`) → thông báo "Bạn không có quyền thực hiện thao tác này" + đưa về
  nơi được phép; không lộ chi tiết kỹ thuật.
- Xóa vai trò/phòng đang được dùng → chặn kèm lý do ("còn N người dùng/vai trò"), gợi ý
  chuyển trước.
- Backend lỗi/không truy cập được → thông báo dễ hiểu + Retry; thao tác gán không tạo
  hiệu ứng phụ trùng lặp khi thử lại.
- Tài khoản bị khóa cố thao tác → từ chối nhất quán (`401`/`403`), đưa về Login.
