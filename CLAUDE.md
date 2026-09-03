# CLAUDE.md — Sao Việt Nhật ERP (SVN)

ERP in offset đa phân hệ, full-stack. Chi tiết vận hành: README.md.
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
- Code xong một luồng nghiệp vụ có UI (kể cả chỉ sửa 1 khâu trong luồng nhiều bước) → BẮT BUỘC
  thao tác lại ĐÚNG luồng đó bằng chuột/bàn phím thật trên dev-browser trước khi báo "xong", KHÔNG
  dùng API/curl thay bất kỳ bước nào (kể cả để dựng dữ liệu nhanh cho các bước không phải trọng tâm
  sửa). Nếu vì lý do nào đó buộc phải tắt qua API ở một đoạn, phải tự nói rõ ngay lúc báo cáo —
  đừng đợi hỏi mới thú nhận. Báo cáo phải liệt kê CỤ THỂ đã bấm gì/gõ gì/thấy gì ở từng bước, không
  nói chung chung "đã test UI".

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
