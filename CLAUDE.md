# CLAUDE.md — Sao Việt Nhật ERP (SVN)

ERP in offset đa phân hệ, full-stack. Chi tiết vận hành: README.md. Bản đồ tài liệu ở cuối file này.
progress.md ĐÃ CŨ (dừng ở RBAC) — ĐỪNG tin nó để biết trạng thái hiện tại; đọc code + docs/.

## Kiến trúc (đừng đặt sai tầng)

- Backend phân tầng `routers → services → repositories → DB`. Logic nghiệp vụ nằm ở services;
  router chỉ điều phối; truy vấn DB chỉ trong repositories. Engine tính giá ở services.
- DB — CHUNG một tầng SQLAlchemy, nhưng BA nơi khác nhau, đừng nhầm:
  - **dev**: PostgreSQL local `127.0.0.1:5433/svn_erp_local` (xem `backend/.env`). Dòng
    `sqlite:///./dev.db` vẫn còn nhưng ĐANG BỊ COMMENT — `backend/dev.db` không phải DB đang chạy.
  - **prod**: PostgreSQL 16 trên VPS.
  - **test**: `sqlite:///:memory:`, ép ở `backend/tests/conftest.py` TRƯỚC mọi import `app.*`.
    Fixture `db` chạy `drop_all` + `create_all` mỗi test — nhờ dòng ép đó nó không đụng DB thật.
  - `SEED_DEMO=true` trong `.env` ⇒ mỗi lần uvicorn khởi động là seeder ghi dữ liệu demo vào DB dev.

## Xác minh — LỆNH DUY NHẤT

- `./init.ps1` (Windows) = pytest + compileall. Đây là cách verify chuẩn; đừng tự bịa lệnh test khác.
- Sửa route/schema backend → RESTART uvicorn (ở đây KHÔNG hot-reload đáng tin).

## Bẫy kỹ thuật — sai là vỡ DB thật (BẮT BUỘC nhớ)

- KHÔNG có Alembic. `create_all` chỉ TẠO bảng, KHÔNG ALTER. Thêm/đổi cột phải viết vào
  `backend/app/db_migrations.py` thì DB live/prod mới nhận. **Dev cũng là Postgres** (không phải
  file SQLite xoá là xong) nên migration là đường DUY NHẤT — muốn làm lại từ đầu thì phải
  drop/create database `svn_erp_local`, và mất hết dữ liệu demo đang có.
- Cột Boolean: server_default phải là `false`/`true` (Python bool), KHÔNG phải `"0"`/`"1"` —
  chuỗi "0"/"1" chạy SQLite nhưng VỠ khi Postgres create_all trên DB trắng.
- `docs/DB_SCHEMA.md` có guard test: mọi bảng/cột trong model phải được ghi vào đó, nếu không
  `init` FAIL. Thêm cột → cập nhật DB_SCHEMA.md cùng lúc.

## Cách làm việc mình muốn (đọc kỹ — đây là chỗ hay bị sai ý)

- ĐANG BÀN THIẾT KẾ thì CHỈ bàn + viết doc. KHÔNG đụng code/schema cho tới khi mình nói "làm đi".

## Nguyên tắc sản phẩm

- **Gửi/thông báo NỘI BỘ = REAL-TIME.** Mọi việc gửi giữa người dùng trong hệ thống (trình duyệt
  báo giá, duyệt/từ chối, giao việc, nhắc hạn…) phải tới người nhận NGAY — badge tự nhảy + toast
  tức thì, KHÔNG bắt họ refresh hay đổi màn mới thấy. Ưu tiên ĐẨY (SSE): hiện đẩy in-process theo
  1 uvicorn worker; nếu scale >1 worker thì chuyển publish sang Postgres LISTEN/NOTIFY.

## Triển khai

- Live: <https://svn.superbai.io> — GitHub Actions → Docker Compose VPS. Push `main` = TỰ DEPLOY.
- Repo private thuộc `thonglv111`: cần `gh auth switch --user thonglv111` mới fetch/push được.
- Commit/push CHỈ khi mình yêu cầu.

## Bản đồ tài liệu (đọc khi cần, đừng nhồi hết vào đầu)

- docs/DOMAIN_NHA_MAY_IN.md — nghiệp vụ in offset (đọc trước khi động vào tính giá).
- docs/DB_SCHEMA.md — từ điển dữ liệu mọi bảng/cột.
- docs/CONG_THUC_TINH_LUONG.md — TOÀN BỘ công thức lương đang chạy, neo tới `file:line`. Đọc TRƯỚC
  khi sửa engine lương. Phần 13 = chỗ engine cố ý làm khác thông lệ (đừng "sửa" thành đúng luật mà
  không hỏi); Phần 14 = lỗi thật đã biết, kèm bản vá.
- docs/SO_TAY_TINH_LUONG_KE_TOAN.md — CÙNG nội dung đó nhưng cho KẾ TOÁN đọc: gọi bằng tên màn
  hình/tên ô, không một dòng code. Sửa công thức thì phải sửa CẢ HAI file, nếu không hai bên nói
  hai kiểu.
- docs/RBAC_QUYEN_THEO_MODULE.md — bật ô quyền này thì LÀM ĐƯỢC GÌ, theo từng module. Chỉ 4 phân
  hệ của mình (Nhân sự & Lương · Mua hàng · Kế toán · Giao hàng). Nguồn là `PermissionMatrix.tsx`.
- docs/RBAC_VAI_TRO.md — VAI nào đang giữ gì. §4 sinh thẳng từ `seed.ROLES` bằng
  `backend/scripts/xuat_ma_tran_quyen.py` — đừng sửa tay phần đó, chạy lại script.
- docs/prd-thanh-pham.md — danh mục Thành phẩm: chốt đơn là hệ TỰ KHAI hàng của đơn vào danh mục
  để kho nhập/xuất được. §3 giải thích vì sao "menu riêng nhưng CHUNG bảng `vat_tu_in_an`" —
  đừng tách bảng, tách là kéo theo `hang_loai` thứ ba và phải sửa 8 chỗ trong code bên kho.
- docs/spec-*.md — spec từng phân hệ (tính giá, công đoạn, máy, sản phẩm, lương, nhân sự, bình bài).
