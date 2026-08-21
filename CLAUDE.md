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
- TRƯỚC KHI ghi file: hiện nội dung trong chat và chờ mình xác nhận.
- Tính năng mới → GỘP vào màn/luồng đang có, ĐỪNG dựng màn/loại/luồng riêng. Không rõ gộp vào
  đâu thì HỎI trước, đừng tự tạo mới.
- Làm UI theo 2 BƯỚC, 2 AGENT KHÁC NHAU:
  1. Agent SOI & THIẾT KẾ: đánh giá UI hiện tại TRƯỚC (soi bằng `ui-ux-pro-max`) — UI cũ nhiều
     chỗ xấu/chưa đúng ý, ĐỪNG bê nguyên; rồi chốt design. Màn MỚI → bám pattern màn đã ưng
     (list badge + pill + drawer, kiểu RebuildCatalogPage) cho nhất quán. Màn CŨ → soi kỹ, sửa
     chỗ dở, đừng chép lỗi cũ.
  2. Agent BUILD (KHÁC agent soi): dựng UI theo design đã chốt. Khi giao phải truyền ĐỦ ngữ cảnh
     (design đã chốt + luật + dữ liệu + ràng buộc), đừng quăng task cụt.
- UI/UX: ít thao tác + gợi ý rule-based từ data sẵn có; đừng thêm khối UI vô nghĩa; đừng đánh đổi
  chất lượng dữ liệu để bớt click.

## Chống over-engineer (rút từ vụ 13/08/2026 — đọc trước khi định "dọn dẹp" cái gì)

Bối cảnh: mình kêu màn Đơn vị có HAI khối công thức nhìn như trùng nhau. Việc cần làm là sửa MÀN
(2 file FE). Claude đi rút cột `don_vi_quy_doi.cong_thuc` khỏi 11 file backend — trong khi cột đó
có 4 dòng đang chạy và 3 nơi đang ăn (tiền khoán · kế hoạch vật tư · BOM). Kết quả: 3 lần lỗi dây
chuyền, lần cuối làm màn Lệnh sản xuất 500 (`_doc_cap` đổi 4→3 phần tử, `_dong_tren_duong` vẫn
đọc `[3]`). Phải hoàn tác toàn bộ.

- **Sửa ĐÚNG TẦNG được kêu.** Kêu về UI thì sửa UI. Muốn đụng schema/engine phải nói lý do và chờ
  duyệt — "cho nhất quán" KHÔNG phải lý do.
- **Trước khi gọi cái gì là "thừa": đếm dữ liệu thật (`count(*)`) + grep nơi gọi.** Không có số thì
  không được dùng chữ "thừa". (Vụ "chờ kỹ thuật" cùng ngày làm ĐÚNG thứ tự này: 0/24 · 0/10 · 0/14
  ⇒ xoá an toàn. Vụ này làm ngược ⇒ vỡ.)
- **Tách "ngưng dùng" khỏi "xoá đi".** Làm cái ĐẢO ĐƯỢC trước (đổi UI, ngưng đẻ dòng mới) rồi DỪNG.
  Cái không đảo được (rút cột, sửa engine) chờ lượt sau, chờ mình gật.
- **Test in ra rỗng = CHƯA CHẠY, không phải xanh.** Không thấy dòng `N passed` thì đừng xây tiếp.
  (Ba lần `pytest` sai thư mục in ra rỗng, bị đọc nhầm thành pass.)
- **Ngưỡng hỏi tính bằng ĐỘ KHÓ GỠ, không phải độ phân vân.** Trên 3 file, hoặc đụng thứ có dữ liệu
  sống → hỏi. Còn lại tự quyết, đừng hỏi lại câu mình đã trả lời.

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
- docs/spec-*.md — spec từng phân hệ (tính giá, công đoạn, máy, sản phẩm, lương, nhân sự, bình bài).
