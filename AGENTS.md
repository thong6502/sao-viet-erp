# AGENTS.md — Sao Việt Nhật ERP (SVN)

ERP in offset đa phân hệ, full-stack. Chi tiết vận hành: README.md. Bản đồ tài liệu ở cuối file này.
progress.md ĐÃ CŨ (dừng ở RBAC) — ĐỪNG tin nó để biết trạng thái hiện tại;

## Kiến trúc (đừng đặt sai tầng)

- Backend phân tầng `routers → services → repositories → DB`. Logic nghiệp vụ nằm ở services;
  router chỉ điều phối; truy vấn DB chỉ trong repositories. Engine tính giá ở services.
- DB: SQLite `backend/dev.db` (dev) / PostgreSQL 16 (prod) — CHUNG một tầng SQLAlchemy.

## Xác minh — LỆNH DUY NHẤT

- Sửa route/schema backend → RESTART uvicorn (ở đây KHÔNG hot-reload đáng tin).

## Bẫy kỹ thuật — sai là vỡ DB thật (BẮT BUỘC nhớ)

- KHÔNG có Alembic. `create_all` chỉ TẠO bảng, KHÔNG ALTER. Thêm/đổi cột phải viết vào
  `backend/app/db_migrations.py` thì DB live/prod mới nhận; dev thì drop `backend/dev.db` để tạo lại.
- Cột Boolean: server_default phải là `false`/`true` (Python bool), KHÔNG phải `"0"`/`"1"` —
  chuỗi "0"/"1" chạy SQLite nhưng VỠ khi Postgres create_all trên DB trắng.
- `docs/DB_SCHEMA.md` có guard test: mọi bảng/cột trong model phải được ghi vào đó, nếu không
  `init` FAIL. Thêm cột → cập nhật DB_SCHEMA.md cùng lúc.

## Nguyên tắc sản phẩm

- **Gửi/thông báo NỘI BỘ = REAL-TIME.** Mọi việc gửi giữa người dùng trong hệ thống (trình duyệt
  báo giá, duyệt/từ chối, giao việc, nhắc hạn…) phải tới người nhận NGAY — badge tự nhảy + toast
  tức thì, KHÔNG bắt họ refresh hay đổi màn mới thấy. Ưu tiên ĐẨY (SSE): hiện đẩy in-process theo
  1 uvicorn worker; nếu scale >1 worker thì chuyển publish sang Postgres LISTEN/NOTIFY.

## Triển khai

- Live: <https://svn.superbai.io> — GitHub Actions → Docker Compose VPS. Push `main` = TỰ DEPLOY.
- Repo private thuộc `thonglv111`: cần `gh auth switch --user thonglv111` mới fetch/push được.
- Commit/push CHỈ khi mình yêu cầu.

