# Spec — Module Thực hiện sản xuất (sau Kế hoạch sản xuất 2 / Xếp lịch 2)

> Bản spec gốc (v2) do chủ dự án chốt. Đây là lớp **thực thi sản xuất tại tổ** đứng sau khâu
> phát hành của Xếp lịch 2, KHÔNG thay màn lập lịch, KHÔNG dựng hệ sản xuất tách rời.
>
> Tài liệu liên quan: `docs/spec-xep-lich-2.md`, `docs/design-xep-lich-2-ui.md`, `docs/DB_SCHEMA.md`,
> `docs/DOMAIN_NHA_MAY_IN.md`.

## Trạng thái triển khai

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| 1 | Nền tổ chức & phát hành (cờ KCS, navbar node lá, nhóm thành phẩm, snapshot phát hành, gói nguyên tử, phiên bản cập nhật lịch) | 🔨 Đang làm — mg 0220: `departments.is_kcs` + `job_grades.output_coefficient` nối 2 màn danh mục (BE + test). Backbone phát hành XONG (6 bảng `san_xuat_*` create_all, `SanXuatRepository`, `component`/`nhom`/`snapshot`/`release`, nối vào cả 2 cửa phát hành, 7 test `test_san_xuat_release.py` xanh): thành phần liên thông, gói+phiên bản+công việc đóng băng, một-bài-ghép-một-công-việc, suy nhóm thành phẩm, đánh KCS-cuối, cửa soi `van_de_phat_hanh`, idempotent mức gói. **Nguồn navbar node lá (BE) XONG**: `services/san_xuat/board.py` (`teams`+`work_items`, scope all/department/own tái dùng module quyền `san_xuat`, KHÔNG đẻ quyền/migration mới), `schemas/san_xuat.py`, `routers/san_xuat.py` (`GET /api/san-xuat/teams` + `/work-items?team_id=`, gác `require_permission("san_xuat","read")`, ngoài phạm vi→403), đã mount trong `main.py`; 7 test `test_san_xuat_board.py` + 4 api `test_san_xuat_board_api.py` xanh, compileall sạch. Còn: **navbar FE** (bơm node lá vào Sidebar), phiên bản cập-nhật-lịch (§4.3), FE (KCS checkbox đã có, hộp thoại phát hành chưa gắn cửa soi) |
| 2 | Khung thực hiện tại tổ (timeline, drawer, phân công, phiên chạy, khoảng tham gia, chấm công/OT, actual overlay) | ✅ BE ĐỌC+GHI + FE "một bàn làm việc" XONG (chờ nghiệm thu cuối) — Đọc: `board.teams`/`work_items`/`chi_tiet_cong_viec` (drawer: roster + phiên chạy + khoảng tham gia; nhãn resolve theo lô) + endpoint picker riêng gác `san_xuat` `GET /teams/{id}/nhan-vien` (KHÔNG mượn `/api/employees` vì nó đòi quyền `nhan_su` → tổ trưởng 403). Ghi: 3 bảng mới create_all `san_xuat_phan_cong`/`san_xuat_phien_chay`/`san_xuat_khoang_tham_gia`, repo + service `services/san_xuat/thuc_thi.py` (snapshot cờ khoán từ `departments.has_piece_work`; bước nội bộ chỉ nhận thợ khoán; GATE §6 chỉ `head_user_id` đúng tổ; bắt đầu cần ≥1 khoán; trễ/tạm dừng bắt buộc lý do; không hai khoảng chồng giờ; version chống bấm trùng; máy chủ + naive/aware). Router 6 endpoint ghi gác `san_xuat:assign_work` + SSE sau commit; KHÔNG migration. **FE**: 5 file `ThucHienSxPage`/`ThsxTimeline`/`ThsxDrawer`/`thsxShared`/`thuc-hien-sx.css` (bám pattern XepLich2, timeline tái dùng `xl2Shared`, KHÔNG kéo-thả), nối `api.sanXuat` (9 method) + AppShell (Kho-pattern: teamList/badge/dynamicItems/render/SSE) + `permissions` (`assign_work`); styleseed **94/100 A**, `npx tsc` sạch. 15 test `test_san_xuat_thuc_thi.py` + 7 board + 4 api xanh. **Khoảng trống chờ pha sau:** (b) §7.3 chấm công-OT dẫn xuất; (c) actual overlay (cần trường mốc thực trên `WorkItemOut`); (d) §7.1 "số người thực tế ≠ dự kiến → lý do" (chờ nguồn số người dự kiến) |
| 3 | Đầu vào, sản lượng & bàn giao (xác nhận vật tư, chọn lot BTP, batch sản lượng, bàn giao, overconsumption) | ✅ BE XONG (chờ FE + nghiệm thu cuối) — 6 bảng mới create_all (`san_xuat_ly_do`, `san_xuat_batch`, `san_xuat_batch_lot_vao`, `san_xuat_ban_giao`, `san_xuat_ban_giao_dieu_chinh`, `san_xuat_vat_tu_nhan`) + repo `san_xuat_san_luong_repo.py`. **Sản lượng** `services/san_xuat/san_luong.py`: batch `tong=tot+hong`, hong>0 bắt nhóm lỗi chuẩn (`nhom='loi'`), chỉ ghi khi cv đã khởi động, GATE §6, `tong_tot` = nền trần bàn giao; lot đầu vào §10.3 (batch công đoạn trước, không trỏ chính mình) + `them_lot`. **Bàn giao** `services/san_xuat/ban_giao.py`: cùng-tổ-cùng-LSX tự `confirmed` (notify None), khác tổ→`proposed`→bên NHẬN xác nhận (gate ĐÍCH, nguồn không tự xác nhận), trần `tong_tot−đã_giao`, sửa chỉ khi `proposed`, điều chỉnh đẻ lịch sử + cờ `khong_nhat_quan` khi giảm dưới lượng đã dùng (§11.3), bắt buộc lý do nhóm `dieu_chinh_ban_giao`. **Vật tư** `services/san_xuat/vat_tu_nhan.py`: xác nhận phiếu XUẤT posted NGUYÊN TRẠNG (§10.1), 1 phiếu/1 lần (`voucher_id` UNIQUE), gate tổ trưởng. **Danh mục Lý do & lỗi SX** = catalog thứ 12 trên màn Cấu hình danh mục (module quyền riêng `dm_ly_do_san_xuat`, mg 0221 chép quyền từ `san_xuat`), KHÔNG đẻ màn mới. Router `san_xuat.py` + schema mặt GHI đã khai (LotVaoIn/BatchIn/BanGiao*/VatTu*). **44 test san_xuat (G1–G3) chạy chung xanh** (9 san_luong + 8 ban_giao + 4 vat_tu_nhan mới) + `test_schema_documented` + `test_catalog_registry` xanh; KHÔNG migration cột (chỉ bảng mới). **Còn: FE drawer** (nhập batch + picker lot đầu vào + UI bàn giao + xác nhận vật tư, gắn vào `ThsxDrawer` chỗ placeholder "Pha sau") + FE cấu hình catalog lý do; qua 2-agent + styleseed + dev-browser |
| 4 | Hỗ trợ & phân bổ (hỗ trợ 2 tổ, hệ số bậc, phân bổ theo batch, chốt/mở lại, nối PieceWork) | ⏳ Chưa bắt đầu |
| 5 | KCS & kho (batch KCS, lỗi+ảnh, trách nhiệm, đóng thiếu, TP/BTP theo đơn, nhập kho một phần, tự đóng nhóm) | ✅ XONG — nền batch/lỗi/ảnh/trách nhiệm + kho BTP/thành phẩm + tự đóng nhóm đã có TRƯỚC module KCS kiêm nhiệm (`services/san_xuat/kcs.py`, `kho.py`; test `test_san_xuat_kcs.py`/`test_san_xuat_kho.py`/`test_san_xuat_dong_nhom.py`/`test_san_xuat_g5_tich_hop.py`). Module **KCS kiêm nhiệm** (mg `0250`, 2026-08-31) sau đó mở rộng thêm luồng ghi song song trên nền này (routing 2 bước + đột xuất 1 bước, checklist, gửi kho một nút, dashboard/Excel) — chi tiết ở §13 (viết lại 2026-08-31) |
| 6 | Real-time & hoàn thiện (SSE toàn sự kiện, badge/toast, audit, chống trùng, test tích hợp) | ⏳ Chưa bắt đầu |

Quy tắc verify: giữa dòng dùng `pytest` nhắm file + `npx tsc`; chạy `./init.ps1` một lần ở cuối cùng.
Migration Postgres gần như không đảo được — thêm/đổi cột phải viết `backend/app/db_migrations.py` +
cập nhật `docs/DB_SCHEMA.md`; Boolean dùng `true/false`.

---

## 1. Mục tiêu tổng thể

Xây thêm lớp **thực hiện sản xuất tại tổ** nối trực tiếp sau khi lệnh được phát hành từ Kế hoạch sản xuất 2:

1. Kế hoạch sản xuất 2 lập lịch và phát hành.
2. Lệnh xuất hiện tại tổ sản xuất tương ứng.
3. Tổ trưởng phân công người thực hiện.
4. Ghi nhận bắt đầu, tạm dừng, tiếp tục, kết thúc và sản lượng thực tế.
5. Theo dõi nguyên vật liệu, bán thành phẩm và bàn giao giữa công đoạn.
6. Phân bổ sản lượng cho từng người theo thời gian thực tế và bậc tay nghề.
7. KCS kiểm tra trước khi tạo yêu cầu nhập kho.
8. Dữ liệu sản lượng đã chốt được đưa vào luồng lương khoán hiện có.

Đây là lớp thực thi của lịch đã phát hành, không thay thế màn lập lịch và không tạo một hệ thống sản xuất tách rời.

---

## 2. Phòng ban, navbar và cờ KCS

### 2.1. Phân hệ sản xuất trên navbar

- Phòng ban có `la_san_xuat = true` được xem là gốc của một khối sản xuất.
- Tất cả node lá nằm bên dưới phòng đó tự động xuất hiện trên navbar thuộc phân hệ Sản xuất.
- Nếu một node con tiếp tục có node trực thuộc thì chỉ các node lá cuối cùng được đưa lên navbar.
- Mỗi node lá dùng chung một khung màn hình thực hiện sản xuất, nhưng dữ liệu được lọc theo tổ và quyền của người đăng nhập.
- Không dựng một loại màn hình riêng cho từng tổ.

### 2.2. Cờ KCS

Bổ sung `departments.is_kcs`.

Quy tắc:

- Chỉ hiển thị công tắc KCS khi phòng/tổ là node lá và đang thuộc hiệu lực của Khối sản xuất.
- Có thể có nhiều tổ KCS trong công ty.
- Khi tắt cờ Khối sản xuất ở một phòng cha, hệ thống cảnh báo và tự xóa cờ KCS của các node con bị mất hiệu lực sản xuất sau khi người dùng xác nhận.
- Khi phát hành lệnh, hệ thống snapshot phòng thực hiện và trạng thái KCS; thay đổi cơ cấu sau đó không làm đổi lệnh đang chạy.
- Một công đoạn được nhận diện là KCS dựa trên snapshot phòng thực hiện, không dựa vào tên có chứa "KCS".
- Mỗi nhóm thành phẩm phải có đúng một công đoạn KCS cuối.
- Có thể có KCS trung gian, nhưng phải phân biệt rõ với KCS cuối.
- Thiếu KCS cuối hoặc có nhiều hơn một KCS cuối sẽ chặn phát hành.
- Quyền "ghi nhận kiểm tra KCS" và quyền "tạo yêu cầu nhập kho" là hai quyền riêng.

---

## 3. Nhóm thành phẩm, LSX và bước ghép

### 3.1. Nhóm thành phẩm

- Tự động tạo `production_group` từ `OrderLine.nhom`.
- Không yêu cầu người dùng nhập lại tên thành phẩm.
- Dòng đơn hàng không có `nhom` tạo thành một nhóm đơn lẻ.
- Kế hoạch sản xuất không được tự ghép hoặc tách lại nhóm.
- Nếu nhóm sai, phải sửa từ nguồn Sale/đơn hàng trước khi phát hành.

Ví dụ DH019:

- "Kỷ yếu 25 năm An Phát" là một nhóm thành phẩm.
- Nhóm có hai phần: Ruột và Bìa.
- Ruột và Bìa vẫn là hai LSX riêng.
- Không tạo LSX thứ ba chỉ để đại diện cho thành phẩm.
- Sau khi ghép, sản lượng thành phẩm cuối thuộc về nhóm "Kỷ yếu 25 năm An Phát".

### 3.2. Công đoạn phụ thuộc và bước ghép

- Chỉ cho phép phụ thuộc chéo giữa các LSX thuộc cùng một nhóm thành phẩm.
- Một công đoạn nhận đầu vào từ LSX khác tự động được xem là **bước ghép**.
- Không cần thêm loại công đoạn "Ghép" riêng.
- Một nhóm có thể có nhiều bước ghép.
- Sau bước ghép đầu tiên, phải xác định một LSX thân chính tiếp tục đi tới KCS cuối.
- Các LSX còn lại chỉ đóng vai trò nhánh cung cấp đầu vào cho thân chính.
- Không tạo nhánh cấp nhóm hoặc LSX thành phẩm giả.

Mỗi cạnh phụ thuộc chéo phải snapshot:

- LSX/công đoạn nguồn.
- LSX/công đoạn đích.
- Tỷ lệ ghép.
- Đơn vị nguồn và đơn vị đích.
- Quy tắc quy đổi.
- Số lượng yêu cầu.

Hệ thống tự gợi ý tỷ lệ từ dữ liệu đơn hàng/bài tính giá; người lập kế hoạch được sửa trước khi phát hành.

Giới hạn sản lượng của bước ghép bằng đầu vào bắt buộc đang có ít nhất sau khi quy đổi.

### 3.3. Bài ghép

- Một Bài ghép dùng chung chỉ tạo một bản ghi thực hiện thực tế.
- Chỉ ghi nhận một lần chạy và một lần sản lượng thực tế cho Bài ghép.
- Sản lượng sau đó được ánh xạ về các LSX nhánh theo cấu hình đã snapshot.
- Không tạo nhiều lần thực hiện trùng nhau cho từng LSX dùng chung Bài ghép.

---

## 4. Phát hành và cập nhật lịch

### 4.1. Gói phát hành nguyên tử

Đơn vị phát hành là một thành phần liên thông gồm:

- Một nhóm thành phẩm.
- Các LSX của nhóm.
- Các phụ thuộc chéo.
- Bài ghép dùng chung của nhóm.
- Những nhóm khác bị liên kết qua cùng Bài ghép đó.

Toàn bộ thành phần liên thông phải phát hành nguyên tử. Không được phát hành một nhánh trong khi nhánh phụ thuộc còn lại chưa sẵn sàng.

Cả màn xếp lịch cũ và Kế hoạch sản xuất 2 phải dùng chung bộ kiểm tra phát hành này.

### 4.2. Snapshot lúc phát hành

Snapshot tối thiểu:

- Nhóm thành phẩm và các dòng đơn hàng.
- Sơ đồ LSX/công đoạn/phụ thuộc.
- Tỷ lệ ghép và quy đổi đơn vị.
- Công đoạn KCS cuối.
- Phòng/tổ thực hiện và trạng thái KCS.
- Máy hoặc nguồn lực.
- Thời gian và ca dự kiến.
- Định mức, đơn vị và `khoan_json`.
- Dữ liệu vật tư liên quan.
- Phiên bản lịch phát hành.

Mỗi công đoạn nội bộ phải có cấu hình lương khoán hợp lệ trước khi phát hành. Công đoạn thuê ngoài được miễn điều kiện này.

### 4.3. Sửa lịch sau phát hành

- Người lập kế hoạch chỉ được sửa thời gian hoặc nguồn lực của công việc chưa bắt đầu.
- Thay đổi được tạo thành bản nháp cập nhật.
- Chỉ có hiệu lực sau thao tác "Phát hành cập nhật".
- Khi cập nhật một công việc chưa bắt đầu, mọi phân công trước và thỏa thuận hỗ trợ của công việc đó bị hủy; các tổ phải xác nhận lại.
- Công việc đã bắt đầu không được đổi lịch, tuyến, tỷ lệ ghép hoặc dữ liệu snapshot.
- Khi bất kỳ công việc nào trong gói đã bắt đầu, không được thu hồi toàn bộ gói phát hành.
- Lịch sử các phiên bản phải được giữ lại đầy đủ.

Không hồi tố module thực hiện sản xuất cho các lệnh cũ. Chỉ các gói phát hành sau khi tính năng được kích hoạt mới đi qua luồng mới.

---

## 5. Màn thực hiện sản xuất của tổ

### 5.1. Bố cục chính

Mỗi tổ có một trang trên navbar với:

- Timeline theo thời gian.
- Lane theo máy đối với công đoạn máy.
- Lane theo năng lực tổ đối với công đoạn thủ công.
- Thanh kế hoạch giữ nguyên vị trí theo phiên bản đã phát hành.
- Lớp thực tế hiển thị đè lên thanh kế hoạch.
- Zoom: Giờ, Ca, Ngày, Tuần.
- Lần đầu mở mặc định ở chế độ Ca; sau đó nhớ chế độ gần nhất của người dùng.
- Drawer chi tiết dùng cho phân công, đầu vào, chạy máy, sản lượng, bàn giao và KCS.
- Không tạo các màn độc lập cho từng thao tác nếu có thể gộp vào drawer của công việc.

Tổ trưởng không được kéo thả để sửa lịch. Sai lệch kế hoạch được phản ánh lại cho bộ phận lập kế hoạch.

### 5.2. Tiếp nhận lệnh

- Không có nút "Nhận lệnh" riêng.
- Lần phân công người đầu tiên được xem là tổ đã tiếp nhận.
- Cho phép phân công trước thời điểm dự kiến.
- Công nhân chỉ được xem công việc được giao, không được sửa dữ liệu sản xuất.

---

## 6. Quyền thao tác

- Chỉ người đang là `department.head_user_id` của chính tổ thực hiện mới được thay đổi dữ liệu thực hiện nội bộ của tổ đó.
- Quản lý cấp trên có phạm vi rộng hơn chỉ được xem, không được thao tác thay tổ trưởng.
- Không có quyền ghi đè mặc định dành cho quản lý cấp cao.
- Nhân viên thuộc chế độ lương khoán mới được phân công vào công đoạn nội bộ.
- Nhân viên không có tài khoản vẫn được phân công và tính lương.
- Nhân viên có tài khoản nhận thông báo giao việc real-time.
- Thực hiện thuê ngoài dùng một quyền riêng, không hard-code cho Kế hoạch sản xuất, Mua hàng hoặc tổ kế tiếp.
- Điều động người hỗ trợ giữa hai tổ cần xác nhận của cả tổ trưởng tổ gốc và tổ trưởng tổ nhận.

---

## 7. Phân công và ghi nhận thời gian thực tế

### 7.1. Phân công

- Tổ trưởng chọn thủ công người thực hiện.
- Không tự động gợi ý hoặc tự phân người trong phiên bản đầu.
- Phải có ít nhất một nhân viên lương khoán được phân công mới được bắt đầu công đoạn.
- Nếu số người thực tế khác số người dự kiến, vẫn được bắt đầu nhưng bắt buộc chọn lý do.
- Một người không được có hai khoảng tham gia sản xuất bị chồng thời gian.

### 7.2. Phiên chạy

Một công việc có thể có nhiều phiên:

1. Bắt đầu.
2. Tạm dừng.
3. Tiếp tục.
4. Kết thúc.

Quy tắc:

- Tạm dừng bắt buộc có lý do.
- Thêm người, rút người hoặc chuyển người sẽ tự đóng/mở khoảng tham gia tương ứng.
- Mốc thời gian lấy từ máy chủ.
- Không backdate.
- Không sửa trực tiếp mốc đã phát sinh.
- Bắt đầu sớm được phép nếu đầu vào và nguồn lực hợp lệ, không bắt buộc lý do.
- Bắt đầu trễ dù bất kỳ khoảng thời gian nào cũng bắt buộc lý do.
- Kết thúc trễ chỉ yêu cầu thêm lý do nếu chưa có lý do tạm dừng giải thích được phần chậm.

### 7.3. Chấm công và tăng ca

Phút thực tế của một người bằng giao của:

- Khoảng người đó tham gia công đoạn.
- Các cặp chấm công IN/OUT thực tế.
- Khoảng tăng ca đã được duyệt nếu thời gian nằm ngoài ca thường.

Quy tắc:

- Dùng phút thực tế thô, không áp dụng grace period hoặc làm tròn của chấm công.
- Thời gian tăng ca chỉ tính phần giao với khoảng tăng ca đã duyệt.
- Ca qua đêm được tính vào ngày công mà ca bắt đầu.

---

## 8. Bậc tay nghề

Bổ sung một hệ số sản lượng toàn cục vào `JobGrade`, ví dụ `output_coefficient`.

- Không tự đoán hệ số cho các bậc tay nghề hiện có.
- Hệ số để trống cho tới khi được người có quyền cấu hình.
- Khi người lao động bắt đầu tham gia, snapshot bậc và hệ số tại thời điểm đó.
- Thay đổi danh mục sau này không viết lại dữ liệu đang chạy hoặc đã hoàn thành.
- Thiếu hệ số không chặn việc ghi nhận sản xuất.
- Thiếu hệ số chặn thao tác chốt phân bổ sản lượng.

---

## 9. Hỗ trợ chéo giữa các tổ

### 9.1. Thỏa thuận hỗ trợ

Mỗi dòng hỗ trợ gồm:

- Người hỗ trợ.
- Tổ gốc.
- Tổ thực hiện.
- Công đoạn.
- Ngày làm việc.
- Tỷ lệ sản lượng.
- Trạng thái xác nhận của hai tổ trưởng.

Tỷ lệ là giá trị nhập theo từng thỏa thuận:

- **7% chỉ là ví dụ.**
- Không hard-code 7%.
- Không dùng 7% làm mặc định.
- Không dùng 7% làm giới hạn.
- Có thể nhập 5%, 7%, 12,5% hoặc tỷ lệ phù hợp thực tế.
- Tổng tỷ lệ hỗ trợ áp vào cùng một phạm vi phân bổ không được vượt 100%.

### 9.2. Cách tính

- Phần hỗ trợ được trừ trước khỏi tổng sản lượng được chấp nhận.
- Người hỗ trợ nhận đúng tỷ lệ đã thỏa thuận.
- Phần đó được ghi nhận cho tổ gốc của người hỗ trợ.
- Tổ thực hiện giữ phần còn lại.
- Cùng một tỷ lệ áp dụng cho sản lượng ghi nhận và quỹ lương khoán.
- Phần hỗ trợ thuộc ngày ghi trên thỏa thuận, không chuyển sang ngày hoàn thành công đoạn.
- Không dùng thời gian thực tế, hệ số tay nghề hoặc chấm công để điều chỉnh phần hỗ trợ.
- Nếu người hỗ trợ không có chấm công, hệ thống cảnh báo nhưng vẫn giữ nguyên phần tỷ lệ đã được hai bên xác nhận.
- Phần còn lại của tổ thực hiện mới được chia theo thời gian thực tế nhân hệ số tay nghề.
- Khi lịch chưa chạy bị phát hành cập nhật, thỏa thuận hỗ trợ bị hủy và phải xác nhận lại.

KCS tự chọn tổ/công đoạn chịu trách nhiệm lỗi. Không tự động quy trách nhiệm chất lượng dựa trên tỷ lệ hỗ trợ.

---

## 10. Nguyên vật liệu và đầu vào

### 10.1. Nguyên vật liệu kho

- Tiếp tục dùng luồng giữ hàng, yêu cầu xuất, phiếu xuất và phiếu trả hiện có.
- Không nhập lại lượng nguyên vật liệu theo từng batch sản lượng.
- Tiêu hao ròng bằng phiếu xuất đã ghi sổ trừ phiếu trả đã ghi sổ.
- Sau khi kho xuất, tổ trưởng nhận vật tư phải xác nhận đã nhận.
- Chỉ số lượng đã được tổ xác nhận mới được xem là khả dụng cho sản xuất.
- Nếu số lượng trên phiếu khác thực nhận, hai bên xử lý thực tế và kho sửa chứng từ trước khi tổ xác nhận.
- Không tạo hai con số đối nghịch "kho giao" và "tổ nhận".

### 10.2. Điều kiện chạy

- Không có đầu vào thực tế đối với công đoạn bắt buộc có đầu vào: được chuẩn bị và phân công nhưng không được bắt đầu.
- Có một phần đầu vào: được chạy nếu tổ trưởng nhập lý do cảnh báo, kể cả khi một số dòng nguyên liệu khác chưa đủ.
- Bước ghép phải có số lượng dương đã xác nhận ở tất cả nhánh đầu vào bắt buộc.
- Vật tư phát sinh thêm dùng luồng yêu cầu xuất bổ sung hiện có.
- Vật tư thừa tạo yêu cầu trả kho.
- Nhóm sản xuất chưa được đóng hoàn toàn cho tới khi kho xác nhận nhận lại vật tư phải trả.

### 10.3. Bán thành phẩm đầu vào

Khi tạo batch sản lượng, tổ trưởng chọn chính xác:

- Lot đầu ra của công đoạn trước.
- Lot BTP liên quan.
- Số lượng sử dụng từ từng lot.

Việc chọn lot tạo được quan hệ truy vết từ nguyên liệu/BTP đầu vào tới batch đầu ra.

---

## 11. Sản lượng và bàn giao công đoạn

### 11.1. Batch sản lượng

Mỗi batch ghi:

- Khoảng thời gian sản xuất.
- Tổng số lượng.
- Số lượng tốt.
- Số lượng hỏng.
- Đơn vị.
- Lot đầu vào đã sử dụng.
- Danh sách người tham gia trong khoảng batch.

Ràng buộc:

`Tổng số lượng = Tốt + Hỏng`

Nếu có số lượng hỏng:

- Bắt buộc chọn nhóm lỗi chuẩn hóa.
- Có thể bổ sung mô tả.
- Không cho nhập một lý do tự do thay thế hoàn toàn danh mục lỗi.

Cho phép nhiều batch một phần trong cùng công đoạn.

### 11.2. Bàn giao

- Hai công đoạn liên tiếp trong cùng tổ tự động chuyển số lượng tốt sang đầu vào công đoạn sau.
- Bàn giao khác tổ hoặc khác LSX cần xác nhận hai bên.
- Người giao đề xuất một số lượng.
- Hai bên kiểm đếm thực tế.
- Nếu chưa đúng, bên giao sửa số đề xuất.
- Bên nhận chỉ xác nhận đúng con số cuối cùng đã thống nhất.
- Không lưu hai số lượng cạnh tranh.

Số lượng đã xác nhận đồng thời là:

- Sản lượng được chấp nhận của công đoạn trước.
- Cơ sở tính lương công đoạn trước.
- Đầu vào khả dụng của công đoạn sau.

### 11.3. Điều chỉnh bàn giao

- Không xóa cứng bàn giao.
- Người nhập sai được tạo điều chỉnh kèm lý do.
- Giữ lịch sử trước và sau điều chỉnh.
- Nếu điều chỉnh giảm thấp hơn số lượng công đoạn sau đã sử dụng, công đoạn sau bị đánh dấu không nhất quán.
- Không cho chốt phân bổ hoặc đóng nhóm khi còn không nhất quán.
- Lỗi phát hiện ở công đoạn sau không tự động trừ sản lượng hoặc tiền lương đã chấp nhận của công đoạn trước.

### 11.4. Tỏa sản lượng bài ghép xuống LSX nhánh (chốt 30/08/2026, CÀI ĐẶT XONG 30/08/2026)

> Chi tiết hoá §3.3: "sản lượng ánh xạ về LSX nhánh theo cấu hình đã snapshot". Mô hình khuôn chung
> ở `docs/spec-bai-ghep-dag.md` §11 quyết định đâu là **điểm tỏa** (bước chung cuối cùng trên chuỗi
> giấy của bài ghép, PERSISTED thành một cạnh `SanXuatPhuThuoc` lúc phát hành — xem §11.5 ở đó);
> mục này nói cơ chế server tự sinh kết quả từng LSX khi ghi batch tại đúng công việc đó.

**Cạnh nguồn của cơ chế tỏa:** `SanXuatPhuThuoc` (`san_xuat.py:251-278`, bảng vốn có sẵn cho phụ
thuộc chéo công-việc↔công-việc) được `dung_diem_toa()` (`services/san_xuat/snapshot.py`, gọi từ
`release.py:phat_hanh` lúc phát hành) ghi thêm một dòng cho mỗi LSX thành viên có điểm toả: nguồn =
công việc điểm toả, đích = bước RIÊNG đầu tiên của chính LSX đó, `ty_le_ghep` = `so_con_tren_to`
snapshot tại lúc phát hành. Mục này chỉ dùng lại cạnh đó, không tạo thêm bảng phụ thuộc nào khác.

**Bảng sổ cái sản lượng nhánh:** `SanXuatKetQuaNhanh` (`models/san_xuat_san_luong.py`, bảng MỚI
`create_all`) — `id`, `batch_id` (FK `san_xuat_batch`, CASCADE), `lsx_id` (FK `lsx`, CASCADE),
`so_luong`, `don_vi`, `ban_giao_id` (FK `san_xuat_ban_giao`, SET NULL, neo bàn giao tự-xác-nhận
tương ứng), `created_at`. CHỈ-THÊM — không có ràng buộc unique `batch_id+lsx_id`; mỗi lần ghi một
batch tại công việc điểm-toả thì đẻ ĐÚNG một dòng mới cho mỗi cạnh toả (không sửa dòng cũ), nên
"kết quả nhánh của một batch" luôn là join theo `batch_id`, "tổng đã toả cho một LSX" là cộng dồn
qua nhiều batch.

**Cơ chế (`_toa_san_luong()`, `services/san_xuat/san_luong.py`, gọi từ `tao_batch()` ngay trước
`db.commit()`):**

- Khi ghi batch cho một công việc: tra `canh_toa_di_tu(cv.id)` — cạnh `SanXuatPhuThuoc` có nguồn là
  chính công việc này. RỖNG với công việc thường (không phải điểm toả) → no-op, hàm không đụng gì —
  an toàn cho mọi batch không phải điểm toả, không cần cờ đánh dấu riêng công việc nào là "điểm
  toả".
- Với mỗi cạnh: `so_luong` nhánh = `tot` của batch × `ty_le_ghep` (làm tròn 3 chữ số thập phân).
  Cạnh nào ra `so_luong <= 0` thì bỏ qua (không sinh dòng rác).
- Mỗi cạnh sinh MỘT dòng `SanXuatKetQuaNhanh` + MỘT dòng `SanXuatBanGiao` **đã ở trạng thái
  `BG_XAC_NHAN`** ngay khi tạo (`de_xuat_by_id`/`xac_nhan_by_id` cùng là actor ghi mẻ, cùng thời
  điểm) — KHÔNG qua vòng đề xuất rồi chờ bên nhận xác nhận như bàn giao thường (§11.2/§11.3): số
  này suy MỘT CHIỀU từ `tot` theo `ty_le_ghep` đã snapshot, không ai có thể "sửa" hay "từ chối" một
  phép nhân, nên vòng thương lượng hai bên là thừa. `ket_qua.ban_giao_id` trỏ ngược lại dòng bàn
  giao này.
- Ví dụ cộng dồn qua nhiều mẻ (LSX A: `ty_le_ghep=1.5`, LSX B: `ty_le_ghep=1.0`, cùng nguồn tờ):
  mẻ `tot=120` tờ → A nhận batch mới +180 con (đã xác nhận), B +120 con; mẻ sau `tot` khác lại sinh
  batch nhánh MỚI, không cộng vào dòng cũ — tổng khả dụng của A/B là tổng các dòng `so_luong` của
  chúng qua mọi batch điểm-toả liên quan.
- Bước chung TRUNG GIAN (chưa tới điểm toả — không có cạnh `SanXuatPhuThuoc`-toả nào xuất phát từ
  nó) thì `canh_toa_di_tu()` trả rỗng, `_toa_san_luong()` là no-op: ghi batch ở đó đi theo đường
  bàn giao thường sang bước chung kế tiếp (`dung_phu_thuoc`, đã có từ trước Task này) — không bị
  cơ chế tỏa ở mục này đụng tới.
- Hoàn thành bước điểm-toả không tự đánh dấu LSX hoàn thành; công đoạn riêng của mỗi LSX nhận từng
  batch nhánh ngay khi được tạo, không chờ cả bài ghép xong.

**Chặn dùng vượt/nhầm phần đã toả (`_chuan_hoa_lot()`, cùng file):** khi một lot đầu vào của batch
đang ghi trỏ `nguon_batch_id` về một batch mà `co_ket_qua_nhanh(nguon.id)` là `true` (tức batch
nguồn LÀ điểm toả, đã tách theo LSX):
- Công việc đang ghi (`dich_cv`) phải THUỘC một LSX có dòng `SanXuatKetQuaNhanh` ứng với
  `nguon.id` — không có thì chặn `"Batch nguồn đã toả theo từng lệnh sản xuất — lệnh này không có
  phần trong đó."` (LSX C không nằm trong bài ghép đó, hoặc bài ghép không toả tới LSX này).
- Tổng đã dùng từ batch nguồn đó của đúng LSX này (`da_dung_nhanh()` — cộng dồn `so_luong` mọi lot
  trỏ `nguon_batch_id` này, qua các batch có `cong_viec.lsx_id` khớp) cộng số lượng lot đang thêm
  không được vượt `so_luong` đã cấp cho LSX đó (dung sai `_EPS`) — vượt thì chặn `"Vượt phần đã
  toả cho lệnh sản xuất này (…)."`. LSX A không thể mượn/dùng vượt phần của chính nó, và không thể
  chạm phần của LSX B dù cùng một batch nguồn.

**API + FE:** `tao_batch()` trả thêm `ket_qua_lsx: [{lsx_id, so_luong, don_vi, ban_giao_id}, …]`
trong response (rỗng nếu không phải điểm toả). Màn Thực hiện sản xuất (`ThsxExecPanels.tsx`) hiện
banner `.thsx-x-toa-banner` ngay sau khi ghi mẻ thành công tại một điểm toả, liệt kê từng LSX đích +
số lượng đã tỏa + nhãn "đã tự bàn giao", có nút đóng. Phía LSX nhận, công việc riêng đầu tiên sau
điểm toả hiện dòng "NHẬN VỀ" ở trạng thái đã xác nhận ngay (không phải "chờ xác nhận") trong khối
Bàn giao — khác các dòng bàn giao thường phải tự tay xác nhận.

---

## 12. Phân bổ sản lượng và lương khoán

### 12.1. Đơn vị phân bổ

Phân bổ theo từng batch sản lượng, không chia một lần cho toàn công đoạn.

Chỉ những người có khoảng tham gia giao với khoảng thời gian của batch mới được tham gia chia phần còn lại của tổ thực hiện.

### 12.2. Công thức

Với một batch có sản lượng trả lương `Q`:

1. Quy đổi sản lượng bản địa của công đoạn sang sản lượng trả lương bằng `khoan_json` đã snapshot.
2. Tính tổng tỷ lệ hỗ trợ đã được xác nhận `P`.
3. Mỗi người hỗ trợ nhận `Q × tỷ lệ của người đó`.
4. Phần của tổ thực hiện là `Q × (1 - P)`.
5. Trọng số của người thuộc tổ thực hiện:

`Trọng số = phút thực tế hợp lệ × hệ số bậc tay nghề đã snapshot`

6. Chia phần còn lại theo tỷ trọng của từng người.
7. Dùng phương pháp phần dư lớn nhất để làm tròn nhưng tổng sau làm tròn vẫn đúng bằng `Q`.

Quy tắc:

- Không cho sửa tay sản lượng từng cá nhân.
- Không cộng trực tiếp các sản lượng khác đơn vị.
- Luôn giữ riêng sản lượng bản địa và sản lượng trả lương đã quy đổi.
- Nếu không có trọng số hợp lệ, không cho chốt phân bổ.
- Không tự động trừ lỗi cá nhân.
- Cơ chế thưởng/phạt tổ trưởng hiện có tiếp tục để không hoạt động trong giai đoạn này.

### 12.3. Trạng thái phân bổ

- Sau khi công đoạn hoàn thành, phân bổ ở trạng thái nháp.
- Tổ trưởng phải chốt riêng.
- Công nhân chỉ xem được kết quả đã chốt.
- Trước khi kỳ lương khóa, tổ trưởng được mở lại với lý do và chốt lại.
- Sau khi kỳ lương đã khóa, không sửa kỳ cũ.
- Điều chỉnh sau khóa được ghi thành dòng bù trừ ở kỳ mở tiếp theo, có tham chiếu batch và kỳ gốc.
- Nhóm thành phẩm không được đóng hoàn toàn nếu còn phân bổ chưa chốt.

`ProductionOutputRepository` phải cung cấp dữ liệu thật cho `PieceWorkService.list_nguoi_by_period(year, month)` theo nhân viên, ngày làm việc, batch và đơn vị trả lương.

---

## 13. KCS

> Mục này viết lại 2026-08-31 cho ĐÚNG code đang chạy sau module **KCS kiêm nhiệm** (mg `0250`, spec
> gốc `docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem.md`). Bản trước đó mô tả một luồng DUY NHẤT
> (routing cố định + Nhận/Từ chối trách nhiệm) — luồng đó vẫn còn TRONG DỮ LIỆU CŨ (§13.9) nhưng
> KHÔNG còn là cách ghi kết quả KCS cho phiếu mới. Từ đây hệ thống có HAI luồng ghi sống song song
> (§13.3) trên nền ba khái niệm cờ khác nhau (§13.1) và một danh mục checklist mới (§13.2).

Một tổ có `departments.is_kcs=true` có thể có HAI cửa làm việc trên CÙNG tổ/quyền/dữ liệu/SSE —
không tạo tổ ảo, không nhân đôi công việc:

- **Sản xuất**: node sidebar `thuc-hien-sx:{teamId}`, nhãn = tên tổ, badge `so_viec_cho`.
- **KCS**: node sidebar `thuc-hien-sx-kcs:{teamId}`, nhãn `KCS · {tên tổ}`, badge `so_viec_kcs_cho`,
  trang riêng `ThucHienKcsPage`/`KcsResultDrawer` (KHÔNG dùng lại Gantt/timeline của trang sản xuất).

Node KCS chỉ hiện khi tổ **đang có việc KCS hoạt động** — xem `co_viec_kcs` ở §13.1, đây KHÔNG đơn
giản là "tổ có `is_kcs=true`".

### 13.1. Ba khái niệm KCS — đừng nhầm

Có BA thứ tên gần giống nhau, mỗi thứ đứng một tầng khác nhau; nhầm tầng là nhầm luôn hành vi:

1. **`Department.is_kcs`** — cột DB tĩnh, khai ở danh mục Phòng ban: tổ có NĂNG LỰC KCS. Không đổi
   theo việc đang chạy. Vai trò thật của cờ này là điều kiện CẤU HÌNH lúc phát hành: một bước routing
   khai `la_kcs=true` chỉ hợp lệ khi tổ thực hiện có `is_kcs=true` — sai thì `services/san_xuat/
   release.py` (luật 5, dòng 164–179) chặn phát hành và chỉ đích danh bước + tên tổ sai cấu hình.
   `is_kcs` KHÔNG trực tiếp quyết định badge hay node sidebar (xem mục 3).
2. **`SanXuatCongViec.la_kcs`** — cột DB, snapshot lúc phát hành: cờ BƯỚC, đánh dấu MỘT công việc cụ
   thể có thuộc "mặt bàn KCS" hay không. Nguồn kế thừa: `CongDoan.la_kcs` (danh mục) → snapshot xuống
   `LsxCongDoan.la_kcs` lúc dựng routing → `BaiGhepCongDoan.la_kcs` lúc gộp bài → `SanXuatCongViec.la_kcs`
   lúc phát hành — KHÔNG suy theo `department_id`/`is_kcs` của tổ thực hiện, đọc thẳng cờ bước đã
   đóng băng. Đây là cờ dùng để lọc `GET /api/san-xuat/work-items?team_id=&mode=production|kcs`:
   `mode=kcs` chỉ trả việc `la_kcs=true`, `mode=production` chỉ trả `la_kcs=false`.
3. **`co_viec_kcs`** — tính ĐỘNG lúc đọc, KHÔNG phải cột DB: tổ có đang có ÍT NHẤT MỘT việc
   `la_kcs=true`, chưa hoàn thành (`trang_thai != hoàn thành`), thuộc gói ĐANG phát hành hay không
   (`SanXuatRepository.to_co_viec_kcs`, `backend/app/repositories/san_xuat_repo.py:409-426`). Đây MỚI
   là cổng sinh node sidebar `KCS · {tổ}` (`frontend/src/components/AppShell.tsx:1071-1082`) — RỘNG
   HƠN badge `so_viec_kcs_cho` (badge còn đòi thêm điều kiện "đã có bàn giao xác nhận tới việc đó
   nhưng chưa ghi batch KCS nào" — `SanXuatRepository.dem_kcs_cho_kiem_theo_to`); `co_viec_kcs` chỉ
   cần tồn tại việc KCS đang hoạt động, kể cả đã ghi đủ mọi đợt — nên node không biến mất ngay sau
   khi KCS ghi xong, chỉ ẩn khi tổ không còn việc KCS nào đang chạy.

Vì release chặn cấu hình sai (mục 1), trong thực tế một việc `la_kcs=true` chỉ rơi vào tổ
`is_kcs=true` — nhưng đó là HỆ QUẢ của gate lúc phát hành, không phải vì badge/node tự đọc `is_kcs`
khi tính toán; cả badge lẫn `co_viec_kcs` đọc thẳng `SanXuatCongViec.la_kcs`, không đụng `is_kcs`.

### 13.2. Danh mục checklist

- `SanXuatKcsTieuChi` (mã, tên, hướng dẫn, `bat_buoc`, thứ tự, `active`, `version`) — một tiêu chí áp
  cho nhiều công đoạn qua bảng nối nhiều-nhiều `SanXuatKcsTieuChiCongDoan` (unique theo cặp tiêu
  chí+công đoạn). Gộp vào màn Cấu hình danh mục hiện có, không tạo màn riêng.
- Bổ sung tiêu chí riêng theo lệnh: `LsxCongDoan.kcs_tieu_chi_bo_sung_json` /
  `BaiGhepCongDoan.kcs_tieu_chi_bo_sung_json` (cộng vào checklist chuẩn của danh mục, không thay).
- `SanXuatCongViec.kcs_tieu_chi_json` là snapshot ĐẦY ĐỦ (danh mục + bổ sung) tại lúc phát hành —
  đổi danh mục sau đó KHÔNG ảnh hưởng phiếu đã phát hành (không đọc sống danh mục khi ghi/xem phiếu
  cũ). Đây là điều kiện kịch bản nghiệm thu "checklist danh mục đổi sau phát hành nhưng phiếu cũ
  không đổi" (plan §9 mục 9).
- Khi ghi kết quả, mọi tiêu chí `bat_buoc=true` trong snapshot phải có MỘT kết quả gửi kèm — khớp
  theo `thu_tu` (khoá ổn định kể cả mục bổ sung không có `tieu_chi_id`); thiếu thì chặn với thông
  báo "Còn tiêu chí kiểm tra bắt buộc chưa ghi kết quả." Luật này DÙNG CHUNG cho cả routing lẫn đột
  xuất (`_validate_checklist_bat_buoc` trong `services/san_xuat/kcs.py`). Không có checklist bắt buộc
  nào trong snapshot (batch cũ trước module này, hoặc bước không phải KCS) thì no-op.
- Mỗi kết quả checklist gửi lên chỉ gồm `thu_tu` + `dat` (boolean) + `ghi_chu` tuỳ chọn
  (`KcsChecklistKetQuaIn`) — ĐƠN GIẢN HƠN bản nháp ban đầu của kế hoạch (không có giá trị thứ ba
  "không áp dụng"; không lặp lại mã/tên tiêu chí trong từng kết quả, tra ngược qua snapshot
  `kcs_tieu_chi_json` của công việc khi cần hiển thị).

### 13.3. Ghi kết quả — routing (hai bước) và đột xuất (một bước)

Hai luồng SỐNG dùng bảng `SanXuatKcsBatch`/`SanXuatKcsLoi` chung, phân biệt bằng `loai` (`routing` |
`dot_xuat`):

**Routing** — công việc `la_kcs=true` đã đứng SẴN trong routing/bài ghép, tách HAI bước gọi API:

1. `POST /api/san-xuat/work-items/{cong_viec_id}/kcs` (`kcs.tao_batch_kcs`) — ghi batch: `bat_dau`,
   `ket_thuc` (FE luôn gửi `= thời điểm hiện tại`, form không hiện ô giờ cho người dùng chọn),
   `so_luong_nhan`, `so_luong_dat`, `so_luong_khong_dat` (`nhan = dat + khong_dat`, kiểm ở service),
   `don_vi`, `ghi_chu`, `checklist_ket_qua`. Chỉ ghi được cho công việc `la_kcs=true` đã bắt đầu
   (`dang_chay`/`tam_dung`/`hoan_thanh`). Tổng các đợt đã ghi (kể cả đợt này) không được vượt tổng
   bàn giao `confirmed`/`adjusted` đã xác nhận tới công việc đó (chỉ áp khi công việc đã có ít nhất
   một dòng bàn giao — công việc chưa nối bàn giao thì chưa có gì để chặn theo).
2. Nếu có Lỗi (`so_luong_khong_dat > 0`): gọi tiếp `POST /api/san-xuat/kcs/{kcs_batch_id}/loi`
   (`kcs.ghi_loi`, multipart) — nhóm lỗi + mô tả + tổ/công đoạn liên đới (tuỳ chọn) + ≥1 ảnh bắt
   buộc. Đây là lệnh RIÊNG, không gộp vào bước 1.

**Đột xuất (kiêm nhiệm, mg `0250`)** — một tổ SX KHÁC kiểm một công việc ĐANG CHẠY/TẠM DỪNG, KHÔNG
cần đứng sẵn trong routing (`cv.la_kcs` có thể `false`), gộp MỘT bước: `POST /api/san-xuat/kcs/dot-xuat`
(`kcs.tao_kiem_dot_xuat`, multipart) nhận `cong_viec_id`, `kcs_department_id` (tổ đi kiểm), số
lượng, checklist, VÀ (nếu `so_luong_khong_dat > 0`) nhóm lỗi + mô tả + tổ chịu + ảnh — tất cả trong
CÙNG một lệnh gọi. Khác routing ở ba điểm cố ý: không đòi `la_kcs`/"đã bắt đầu" mà chỉ đòi
`dang_chay`/`tam_dung` (KHÔNG gồm `hoan_thanh`, khác routing); KHÔNG đẻ kèm `SanXuatBatch` sản lượng
(`batch_id` giữ `NULL`), không đụng `trang_thai`/kho của công việc đích; nhóm lỗi + ảnh bắt buộc NGAY
trong cùng lệnh thay vì tách bước.

Cả hai luồng: `SanXuatBatch` sản lượng nền (routing) có `tot = so_luong_nhan`, `hong = 0` — NĂNG SUẤT
KCS lấy nền theo SỐ NHẬN (đạt + không đạt), không phải chỉ số đạt, để tái dùng nguyên pipeline phân
bổ lương (§12). Batch đột xuất là bản ghi CHẤT LƯỢNG thuần, không tạo batch năng suất, không phân bổ
lương khoán.

**Quyền ghi khác nhau giữa hai luồng** (router gác cùng bit thô `assign_work`, ranh giới thật ở
service): routing (`tao_batch_kcs`/`ghi_loi`) CHỈ tổ trưởng đúng tổ đang chạy việc đó mới ghi được
(`_gate`, cùng gate §6 dùng cho sản xuất — không mở rộng cho mọi thành viên); đột xuất
(`tao_kiem_dot_xuat`) cho phép BẤT KỲ THÀNH VIÊN nào của tổ `kcs_department_id` được chọn, không cần
là trưởng tổ (`_gate_member`).

### 13.4. Lỗi KCS — ghi một chiều, không còn Nhận/Từ chối cho phiếu mới

- Khi `so_luong_khong_dat > 0`: bắt buộc chọn nhóm lỗi từ danh mục `san_xuat_ly_do.nhom="loi"`, bắt
  buộc ≥1 ảnh bằng hệ thống lưu file hiện có; `to_chiu_id` (tổ liên đới) và `cong_doan_ref_id` là
  TUỲ CHỌN vì có thể chưa thống nhất trách nhiệm ngoài đời.
- Mọi `SanXuatKcsLoi` tạo mới đều nhận `trang_thai="recorded"` (`TN_RECORDED`) — MỘT CHIỀU, không
  còn cách nào tạo lỗi ở trạng thái `pending` nữa. Khác hẳn thiết kế trước đây (bản mục 13 cũ mà tài
  liệu này thay thế): KHÔNG có bước tổ bị yêu cầu Chấp nhận/Từ chối cho phiếu mới, không phân xử.
- Nếu có `to_chiu_id`, sau khi ghi hệ thống phát SSE `san_xuat_kcs_changed` VÀ đẩy thông báo MỘT
  CHIỀU tới `head_user_id` của tổ đó ("KCS đã ghi nhận lỗi liên quan tới tổ") — không tạo badge hộp
  thư chờ phản hồi, không nút Nhận/Từ chối cho lỗi mới.
- Endpoint `POST /api/san-xuat/kcs/loi/{loi_id}/phan-hoi` (`kcs.phan_hoi_loi`) VẪN CÒN trong code
  nguyên vẹn, nhưng giờ chỉ có tác dụng với hồ sơ CŨ còn `trang_thai="pending"` (tạo trước mg `0250`)
  — gọi trên một lỗi đã `recorded` sẽ không tìm thấy gì để xử lý vì hàm chỉ nhận `pending`. Không có
  lối vào endpoint này từ `KcsResultDrawer`/`ThucHienKcsPage` (UI mới); hồ sơ `pending`/`accepted`/
  `rejected` cũ chỉ còn hiển thị qua `ThsxKcsPanel` trong drawer màn Thực hiện sản xuất CŨ
  (`ThsxDrawer.tsx`/`ThsxG5.tsx`) — xem §13.9.

### 13.5. Điều chỉnh kết quả

- Chỉ `Department.head_user_id` mới điều chỉnh được — với batch `routing` là tổ trưởng của tổ ĐANG
  CHẠY việc (`cv.department_id`), với batch `dot_xuat` là tổ trưởng của tổ ĐI KIỂM
  (`kcs.kcs_department_id`) — hai gate khác nhau, chọn theo `kcs.loai` (`_gate_dieu_chinh`).
- `PATCH /api/san-xuat/kcs/{kcs_batch_id}` (`kcs.dieu_chinh_ket_qua`) đổi lại Đạt/Không đạt/checklist
  NHƯNG số NHẬN giữ nguyên — `so_luong_dat + so_luong_khong_dat` gửi lên phải khớp đúng
  `so_luong_nhan` hiện có trên batch, không đổi qua điều chỉnh.
- Chặn TUYỆT ĐỐI nếu còn yêu cầu nhập kho của batch CHƯA HUỶ (dù đã kho xác nhận chỉ một phần, hay
  còn chờ kho mà chưa huỷ) — trình tự sửa sai: huỷ phần yêu cầu kho chưa nhận bằng luồng hiện có →
  điều chỉnh kết quả KCS → tạo lại yêu cầu nếu cần.
- Không xoá kết quả KCS. Mọi điều chỉnh ghi audit trước/sau (`san_xuat_kcs_dieu_chinh`) và kiểm
  `expected_version`.

### 13.6. Gửi kho một nút

- `POST /api/san-xuat/kcs/{kcs_batch_id}/yeu-cau-nhap-kho` (`kho.tao_yeu_cau_kho_mot_nut`) — CHỈ cho
  batch `loai=routing` và công việc `la_kcs_cuoi=true`; không nhận số lượng từ client.
- Server tự tính "số đạt chưa gửi" = `kcs_batch.so_luong_dat` − tổng yêu cầu CHƯA HUỶ của batch đó,
  khoá dòng batch (`with_for_update`) TRƯỚC khi đọc số để double-click không tạo hai yêu cầu song
  song. Hết số đạt chưa gửi → `409` (`KhongConSoDuGuiKho`), không phải lỗi chung `400`.
- SSE tới Kho và node KCS sau commit.
- Endpoint thủ công cũ `POST /api/san-xuat/kho/yeu-cau-nhap` (`kho.tao_yeu_cau_nhap_thanh_pham`,
  NHẬN số lượng tuỳ ý từ client, không giới hạn `la_kcs_cuoi`) vẫn còn — dùng cho nhập kho từng
  phần thủ công; nút MỘT-BẤM ở trên là lối đi mới cho KCS cuối, không thay thế endpoint cũ.

### 13.7. Chọn việc để kiểm đột xuất

Không có endpoint "projection" riêng để liệt kê việc đang chạy cho kiểm đột xuất — FE
(`KcsResultDrawer`, mode `dot_xuat`) chọn tổ qua `api.sanXuat.teams()` rồi liệt kê việc SẢN XUẤT của
tổ đó bằng chính `GET /api/san-xuat/work-items?team_id=&mode=production` (endpoint dùng chung với
timeline sản xuất bình thường), người kiểm chọn một việc đang chạy/tạm dừng trong danh sách đó.
Không mở quyền sửa, giao người, ghi sản lượng hay điều khiển công việc đích; không trừ sản lượng,
không giữ lô, không dừng việc, không tạo yêu cầu kho từ batch đột xuất.

### 13.8. Dashboard và Excel

- `GET /api/san-xuat/kcs/bao-cao` (JSON, quyền `read`) và `GET /api/san-xuat/kcs/bao-cao/export.xlsx`
  (quyền `export` riêng — xem báo cáo không cần quyền xuất file) DÙNG CHUNG một hàm lọc hàng
  (`_hang_kcs_theo_scope` trong `services/san_xuat/kcs_bao_cao.py`) — cùng bộ filter luôn trả cùng
  tổng giữa hai kênh (plan §9 mục 10).
- Filter: `tu`, `den`, `kcs_department_id`, `lsx_id`, `tu_khoa`, `cong_doan_id`, `loai`,
  `nhom_loi_id`.
- KPI: tổng lượt, tổng nhận, tổng đạt, tổng lỗi, tỷ lệ đạt = **tổng đạt / tổng nhận** (không phải
  trung bình từng đợt); kèm phân bố theo ngày, xếp hạng nhóm lỗi/công đoạn/tổ nhiều lỗi nhất.
- Excel hai sheet: `Kết quả KCS` (một dòng/kết quả) + `Chi tiết checklist` (một dòng/tiêu chí/kết
  quả) — freeze header, autofilter, giờ theo Asia/Bangkok, số tối đa ba chữ số thập phân, tên file
  `bao-cao-kcs-{tu}_{den}.xlsx` (`toanbo` nếu bỏ trống ngày).

### 13.9. Luồng legacy (trước mg `0250`) — vẫn đọc được, không còn lối vào cho phiếu mới

Trước module kiêm nhiệm, KCS chỉ có MỘT luồng: theo bước routing cố định, mỗi lỗi tạo bản ghi
`trang_thai="pending"` chờ tổ bị yêu cầu trách nhiệm phản hồi Chấp nhận/Từ chối qua
`phan_hoi_loi` — đây là đúng thiết kế mà bản mục 13 trước khi viết lại tài liệu này mô tả.

- Hồ sơ `pending`/`accepted`/`rejected` cũ VẪN đọc và (nếu còn `pending`) VẪN phản hồi được —
  `phan_hoi_loi` không bị xoá, chỉ không còn cách nào tạo dòng `pending` MỚI (§13.4).
- UI mới (`ThucHienKcsPage`/`KcsResultDrawer`) không hiển thị lối Nhận/Từ chối. Hồ sơ cũ chỉ còn xem
  qua `ThsxKcsPanel` trong drawer màn Thực hiện sản xuất CŨ (`ThsxDrawer.tsx`, dùng lại ở
  `ThsxG5.tsx`) — không bị ép người dùng mới đi vào luồng này.
- Màn sản xuất cũ (`ThucHienSxPage`) gọi `work-items?mode=production`, nên việc KCS
  (`la_kcs=true`) không còn xuất hiện trong timeline/danh sách của màn đó nữa — tách hẳn khỏi trải
  nghiệm sản xuất thường.
- `GET /api/san-xuat/work-items/{cong_viec_id}/kcs` (`kcs.chi_tiet_kcs`) là mặt ĐỌC dùng CHUNG cho
  cả batch cũ lẫn mới của một công việc (nguồn cho cả panel drawer cũ lẫn `ThucHienKcsPage`), không
  phân biệt theo module UI đang gọi.

---

## 14. Nhập kho thành phẩm và BTP

### 14.1. Thành phẩm

- KCS được tạo nhiều yêu cầu nhập kho một phần từ các batch đạt.
- Tổng số lượng yêu cầu không được vượt tổng số lượng KCS đã chấp nhận.
- Mỗi batch KCS là một lot thành phẩm logic.
- Kho xác nhận từng phần đã nhận.
- Phần kho đã ghi nhận bị khóa.
- Phần chưa nhận còn được KCS phân loại lại với đầy đủ audit.
- Nếu có sai lệch sau khi kho đã ghi sổ, xử lý bằng nghiệp vụ điều chỉnh kho riêng; không sửa ngược batch KCS.

Danh tính thành phẩm là nhóm sản phẩm của đơn hàng, ví dụ:

`DH019 + Kỷ yếu 25 năm An Phát`

Đây không phải SKU chung tái sử dụng. Thành phẩm chỉ được giao cho đúng nhóm/đơn hàng đó.

### 14.2. BTP

Mở rộng kho bằng một registry hàng sản xuất, gồm hai subtype:

- BTP.
- Thành phẩm theo đơn hàng.

Lot BTP snapshot:

- Đơn hàng.
- Nhóm thành phẩm.
- LSX.
- Công đoạn nguồn.
- Quy cách.
- Số lượng.
- Đơn vị.
- Lot nguồn.

BTP của DH019:

- Chỉ được tái sử dụng trong DH019.
- Không dùng cho đơn hàng khác.
- Không tự dùng cho lần tái bản sau.

BTP dư trước khi đóng nhóm phải được phân loại thành một trong:

- Phế/hỏng.
- Mẫu lưu.
- Nhập kho BTP.

---

## 15. Danh mục lý do và lỗi

Gộp vào màn Cấu hình danh mục hiện có, không tạo màn danh mục mới.

Một danh mục lỗi chuẩn hóa dùng chung cho:

- Sản lượng hỏng tại công đoạn sản xuất.
- Lỗi do KCS phát hiện.

Các lý do vận hành cũng đi qua cơ chế danh mục/config hiện có:

- Tạm dừng.
- Bắt đầu trễ.
- Sai lệch nhân sự.
- Chạy khi vật tư chưa đủ.
- Điều chỉnh bàn giao.
- Mở lại phân bổ.
- Đóng thiếu.
- Các lý do vận hành tương tự.

Không hard-code danh sách lý do trong frontend.

---

## 16. Điều kiện tự động đóng nhóm thành phẩm

Không tạo nút "Hoàn tất nhóm" thủ công.

Nhóm tự động chuyển sang hoàn thành đầy đủ hoặc hoàn thành thiếu khi tất cả điều kiện sau đúng:

- Mọi công đoạn bắt buộc nội bộ hoặc thuê ngoài đã hoàn thành.
- Không còn đầu vào/đầu ra không nhất quán.
- KCS cuối đã phân loại toàn bộ số lượng nhận hoặc đã đóng thiếu.
- Mọi phân bổ sản lượng đã được chốt.
- Mọi yêu cầu nhận trách nhiệm lỗi KCS đã được phản hồi.
- Mọi vật tư hoặc BTP cần trả đã được kho xác nhận nhận.
- Mọi BTP dư đã được phân loại.
- Không có điều chỉnh làm cho công đoạn sau tiêu thụ vượt đầu vào.

Audit phải lưu:

- Sự kiện cuối cùng làm đủ điều kiện đóng nhóm.
- Người gây ra sự kiện đó.
- Thời điểm.
- Hoàn thành đầy đủ hay hoàn thành thiếu.
- Lý do đóng thiếu nếu có.

Trạng thái nhập kho thành phẩm tách biệt với trạng thái đóng nhóm. KCS có thể tạo nhập kho một phần trước khi nhóm hoàn tất.

---

## 17. Real-time

Mọi thay đổi gửi giữa người dùng phải được đẩy bằng SSE ngay sau khi transaction thành công:

- Badge navbar của tổ.
- Timeline của tổ.
- Lớp thực tế trên màn Kế hoạch sản xuất.
- Phân công người.
- Bắt đầu, tạm dừng, tiếp tục và kết thúc.
- Bàn giao.
- Xác nhận nhận vật tư.
- Thỏa thuận hỗ trợ và xác nhận hai bên.
- Batch KCS.
- Lỗi KCS và phản hồi trách nhiệm.
- Yêu cầu nhập kho và xác nhận kho.
- Chốt hoặc mở lại phân bổ.
- Dữ liệu nguồn lương khoán.
- Nhóm tự động đóng.

Triển khai hiện tại tiếp tục dùng SSE in-process với một uvicorn worker. Khi chạy nhiều worker, thay lớp publish bằng PostgreSQL LISTEN/NOTIFY mà không đổi giao diện nghiệp vụ.

---

## 18. API và trạng thái nghiệp vụ

Các API mới gộp dưới `/api/san-xuat`:

- `/teams`: danh sách tổ sản xuất hiệu lực và badge.
- `/groups`: nhóm thành phẩm và trạng thái tổng hợp.
- `/release-packages`: snapshot, phát hành và phiên bản cập nhật.
- `/work-items`: timeline, chi tiết công việc, phân công và phiên chạy.
- `/inputs`: lot đầu vào và lượng sử dụng.
- `/outputs`: batch sản lượng.
- `/handovers`: đề xuất, xác nhận và điều chỉnh bàn giao.
- `/support-agreements`: tạo và xác nhận hỗ trợ hai tổ.
- `/allocations`: xem nháp, chốt và mở lại phân bổ.
- `/kcs`: batch kiểm tra, lỗi và phản hồi trách nhiệm.
- `/stock`: xác nhận vật tư, trả BTP và yêu cầu nhập kho thành phẩm.

Trạng thái chính:

- Công việc: `released → running ↔ paused → completed`.
- Bàn giao: `proposed → confirmed → adjusted`.
- Hỗ trợ: `pending_both → confirmed → cancelled`.
- Phân bổ: `draft → finalized → reopened`; sau khóa lương chỉ tạo adjustment kỳ sau.
- KCS batch: `received → concluded`.
- Nhóm: `in_production → waiting_conditions → closed_full | closed_short`.

Các cờ thiếu vật tư, không nhất quán và chờ xác nhận là trạng thái chặn bổ sung, không tạo bản sao công việc.

Mọi command thay đổi dữ liệu phải:

- Kiểm tra quyền tại service.
- Chạy transaction.
- Có version để chống bấm trùng hoặc cập nhật đồng thời.
- Ghi audit.
- Phát SSE sau commit.

---

## 19. Mô hình dữ liệu

Nhóm bảng cần bổ sung:

### Tổ chức và cấu hình

- `departments.is_kcs`.
- `job_grades.output_coefficient`.

### Nhóm và phát hành

- Nhóm thành phẩm và các dòng thành viên.
- Gói phát hành.
- Phiên bản phát hành/cập nhật.
- Snapshot tuyến công đoạn, phụ thuộc và tỷ lệ ghép.

### Thực hiện sản xuất

- Work item.
- Phiên chạy.
- Phân công/khoảng tham gia.
- Lot đầu vào đã sử dụng.
- Batch đầu ra.
- Bàn giao và lịch sử điều chỉnh.
- Thỏa thuận hỗ trợ và xác nhận hai bên.

### Phân bổ

- Phân bổ batch cho từng nhân viên/ngày công.
- Snapshot hệ số tay nghề.
- Dòng điều chỉnh kỳ lương sau khóa.

### KCS

- Batch kiểm tra.
- Lỗi KCS.
- Ảnh bằng chứng.
- Yêu cầu nhận trách nhiệm và phản hồi.

### Kho sản xuất

- Registry hàng sản xuất.
- Lot BTP/thành phẩm.
- Xác nhận tổ đã nhận vật tư.
- Quan hệ batch KCS với yêu cầu nhập kho.

Mọi bảng nghiệp vụ quan trọng phải có audit fields, version và khóa tham chiếu tới snapshot phát hành.

Do dự án không dùng Alembic:

- Thêm/đổi cột phải có migration trong `backend/app/db_migrations.py`.
- Cập nhật đầy đủ `docs/DB_SCHEMA.md`.
- Boolean dùng `true/false` đúng chuẩn PostgreSQL, không dùng chuỗi `"0"` hoặc `"1"`.

---

## 20. Trình tự triển khai

### Giai đoạn 1 — Nền tổ chức và phát hành

- Cờ KCS.
- Navbar theo node lá sản xuất.
- Nhóm thành phẩm tự động.
- Snapshot phát hành.
- Kiểm tra KCS cuối.
- Gói phát hành nguyên tử.
- Phiên bản cập nhật lịch.

### Giai đoạn 2 — Khung thực hiện tại tổ

- Timeline tổ.
- Drawer công việc.
- Phân công.
- Phiên chạy và khoảng tham gia.
- Chấm công/tăng ca.
- Hiển thị actual overlay trong màn kế hoạch.

### Giai đoạn 3 — Đầu vào, sản lượng và bàn giao

- Xác nhận nhận vật tư.
- Chọn lot BTP đầu vào.
- Batch sản lượng.
- Bàn giao cùng tổ/khác tổ/khác LSX.
- Điều chỉnh và kiểm tra overconsumption.

### Giai đoạn 4 — Hỗ trợ và phân bổ

- Xác nhận hỗ trợ hai tổ.
- Tỷ lệ hỗ trợ tùy biến, không hard-code 7%.
- Hệ số bậc tay nghề.
- Phân bổ theo batch.
- Chốt, mở lại và điều chỉnh kỳ sau.
- Kết nối `PieceWorkService`.

### Giai đoạn 5 — KCS và kho

- Batch KCS.
- Lỗi và ảnh.
- Phản hồi trách nhiệm.
- Đóng thiếu.
- Thành phẩm/BTP theo đơn hàng.
- Nhập kho một phần.
- Tự động đóng nhóm.

### Giai đoạn 6 — Real-time và hoàn thiện

- SSE cho toàn bộ sự kiện.
- Badge/toast.
- Audit và chống cập nhật đồng thời.
- Kiểm thử tích hợp toàn luồng.

Khi triển khai UI phải thực hiện đúng hai bước bằng hai agent khác nhau:

1. Agent thiết kế soi UI hiện có bằng `ui-ux-pro-max` và chốt thiết kế.
2. Agent build khác dựng theo thiết kế đã chốt.

Sau khi dựng, kiểm tra trình duyệt thật và chạy `styleseed-design-review` trước khi kết luận hoàn thành.

---

## 21. Kiểm thử và tiêu chí nghiệm thu

### Phòng ban và quyền

- Node lá dưới phòng có cờ sản xuất xuất hiện đúng trên navbar.
- Node trung gian không xuất hiện.
- Cờ KCS chỉ hiện đúng nơi.
- Tắt cờ sản xuất xử lý đúng KCS con.
- Chỉ tổ trưởng trực tiếp được sửa.
- Quản lý cấp trên chỉ xem.

### Nhóm và bước ghép

- DH019 tạo một nhóm Kỷ yếu gồm LSX Ruột và Bìa.
- Phụ thuộc Bìa sang Ruột biến công đoạn nhận thành bước ghép.
- Không sinh LSX thành phẩm thứ ba.
- Không cho phụ thuộc chéo ngoài nhóm.
- Bước ghép không chạy nếu thiếu một nhánh bắt buộc.
- Bài ghép dùng chung chỉ chạy và ghi sản lượng một lần.
- Gói liên thông phát hành nguyên tử.

### Lịch và phân công

- Phân công đầu tiên được tính là tiếp nhận.
- Cập nhật lịch chưa chạy xóa phân công và hỗ trợ.
- Không sửa lịch công việc đã chạy.
- Không thu hồi gói sau khi một công việc bắt đầu.
- Một người không được chạy hai công việc chồng thời gian.

### Thời gian

- Bắt đầu trễ yêu cầu lý do.
- Bắt đầu sớm hợp lệ.
- Pause bắt buộc lý do.
- Giao ca qua đêm ghi đúng ngày bắt đầu ca.
- Chỉ tính OT nằm trong khoảng được duyệt.
- Phút sản xuất bằng giao của participation và chấm công.

### Vật tư và bàn giao

- Chưa xác nhận nhận vật tư thì không có tồn khả dụng.
- Thiếu một phần được chạy với lý do.
- Không có đầu vào bắt buộc thì không chạy.
- Bàn giao khác tổ cần xác nhận.
- Chỉ có một số lượng thống nhất.
- Điều chỉnh giảm dưới lượng đã dùng tạo trạng thái không nhất quán và chặn đóng.

### Hỗ trợ

- Tỷ lệ 7% hoạt động như một dữ liệu ví dụ.
- Hệ thống cũng nhận các tỷ lệ khác như 5% và 12,5%.
- Không có mặc định 7%.
- Tổng tỷ lệ vượt 100% bị từ chối.
- Người hỗ trợ không chấm công vẫn nhận phần đã xác nhận và phát cảnh báo.
- Tổ thực hiện chỉ chia phần còn lại.

### Phân bổ

- Batch chỉ chia cho người tham gia trong khoảng batch.
- Trọng số đúng bằng phút thực tế nhân hệ số snapshot.
- Làm tròn không làm lệch tổng.
- Thiếu hệ số chặn chốt nhưng không mất dữ liệu sản xuất.
- Mở lại trước khóa lương hoạt động đúng.
- Sau khóa tạo adjustment kỳ tiếp theo.
- `PieceWorkService` nhận đúng sản lượng đã chốt.
- Không cộng sai các đơn vị khác nhau.

### KCS và kho

- Năng suất KCS dùng toàn bộ lượng đã nhận và kết luận, không dùng cỡ mẫu.
- Lỗi bắt buộc ảnh và tổ/công đoạn chịu trách nhiệm.
- Chấp nhận/từ chối trách nhiệm được lưu vĩnh viễn.
- Lỗi chờ phản hồi không chặn nhập kho phần đạt nhưng chặn đóng nhóm.
- Nhập kho nhiều phần không vượt lượng đạt.
- Phần kho đã ghi sổ không sửa ngược.
- BTP chỉ tái sử dụng trong cùng đơn hàng.
- Đóng thiếu gửi thông báo cho Kế hoạch sản xuất và Sale.
- Nhóm tự đóng ngay khi điều kiện cuối cùng được giải quyết.

### Xác minh kỹ thuật

- Route/schema backend thay đổi phải restart uvicorn trước khi kiểm tra.
- UI phải được thao tác trên trình duyệt thật.
- Kiểm tra đầy đủ badge, toast và cập nhật SSE không cần refresh.
- Chạy `styleseed-design-review` trước khi báo UI hoàn thành.

---

## 22. Giới hạn phiên bản đầu

- Không tự động xếp người.
- Không cho tổ trưởng kéo sửa lịch.
- Không tự tạo lệnh sửa hàng hoặc LSX bù.
- Không có cấp quản lý phân xử lỗi KCS.
- Không tự quy trách nhiệm chất lượng theo tỷ lệ hỗ trợ.
- Không hồi tố các lệnh đã phát hành trước ngày kích hoạt.
- Không dùng BTP cho đơn hàng hoặc lần tái bản khác.
- Không cho sửa mốc thời gian thực tế.
- Không tự động khấu trừ lỗi vào sản lượng cá nhân.
- Không thay thế nghiệp vụ chứng từ kho hiện có.
