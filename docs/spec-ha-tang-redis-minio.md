# Hạ tầng: Redis (pub/sub + khoá) · MinIO (kho file) · CI/CD theo profile

Trạng thái: **đã dựng + verify** trên nhánh `ha-tang-redis-minio`.
Không đổi schema DB — không đụng `db_migrations.py`, không đụng `docs/DB_SCHEMA.md`.

## 1. Vì sao làm

**File.** Trước đây 6 chỗ tự ghi đĩa xuống `backend/static`, phục vụ qua
`app.mount("/static", ...)` — **công khai, không kiểm quyền**. Ai có URL là đọc được scan CCCD,
hợp đồng lao động, chứng từ kế toán. Bản thân comment trong `models/accounting.py` từng ghi
thẳng "public — known-tradeoff". Đây là lý do chính của đợt này; chỗ chứa bytes chỉ là hệ quả.

**Redis.** KHÔNG dùng làm cache — chưa đo được màn nào chậm, và cache trong ERP đổi vài chục ms
lấy rủi ro dữ liệu lệch (giá, tồn, lịch máy) là lỗ vốn. Chỉ dùng hai vai:

- **pub/sub SSE** — gỡ trần "chỉ 1 uvicorn worker" mà `app/realtime.py` đang bị khoá;
- **khoá** chống bấm hai lần ở xếp lịch / phát hành.

## 2. Ràng buộc xuyên suốt

- **Thiếu Redis/MinIO thì app vẫn chạy đúng.** Không có `REDIS_URL` → hub SSE in-process, khoá
  thành no-op. Không có `MINIO_ENDPOINT` → ghi đĩa `backend/static`. Nhờ vậy `pytest` và gate CI
  chạy **offline**, `./init.ps1` không cần dựng service nào.
- **Mọi chỗ gọi `hub.publish/broadcast`** (58 lần, 9 file) không sửa dòng nào — chỉ thay ruột
  `realtime.py`.
- **Frontend không sửa dòng nào** — xem §4.

## 3. Kho file (`app/storage.py`)

Khoá là đường dẫn tương đối: `hr/12/ab12cd34_cccd.jpg`. Cột `file_url` lưu
`url_from_key(key)` = `/api/files/hr/12/ab12cd34_cccd.jpg`.

| Thành phần | Vai trò |
|---|---|
| `LocalStorage` | ghi `backend/static` — pytest + máy dev không Docker |
| `MinioStorage` | boto3 S3; bucket tự tạo lúc startup (không cần container `mc`) |
| `get_storage()` | có `MINIO_ENDPOINT` → MinIO, không → Local |
| `safe_name` / `make_key` | gộp hai bản `_safe_name` + `_safe_attachment_name` trước đây giống hệt nhau |
| `is_safe_key` | chặn `..`, path tuyệt đối, ký tự ổ đĩa, null byte — gọi TRƯỚC khi chạm storage |

Sáu chỗ ghi file giờ đều gọi adapter: avatar (`routers/profile.py`), hồ sơ HR
(`routers/employees.py`), tài liệu KH (`routers/customers.py`), đính kèm đơn
(`services/order_service.py`), phiếu chi + phiếu thu (`services/accounting_service.py`).

## 4. Đóng `/static`, phục vụ qua `/api/files`

**Vì sao xác thực bằng cookie chứ không phải Bearer.** `<img src>` / `<a download>` do trình
duyệt tự phát, **không gắn được header `Authorization`**, mà access token cố ý chỉ nằm trong RAM
của tab (`frontend/src/auth/AuthContext.tsx` — chống XSS). Cookie là đường duy nhất. Hệ đã dùng
cookie sẵn cho refresh token, và `localhost:5173` ↔ `localhost:8000` là **cùng site** (SameSite bỏ
qua port) nên `samesite=lax` chạy cả dev lẫn prod.

- Cookie `file_access`: JWT `{sub, tv, typ:"file", exp}`, `path=/api/files`, httpOnly,
  `secure` khi production, sống bằng `refresh_token_expire_days`.
- Set ở `login` + `refresh`; xoá ở `logout` + `change-password`. Claim `tv` khiến đổi mật khẩu /
  logout-all giết luôn cookie.
- Claim **`typ`** là chốt chặn leo quyền: hai token cùng ký bằng `jwt_secret`, nếu không phân loại
  thì cookie file (sống 7 ngày) dùng thay Bearer được. `decode_access_token` từ chối `typ != access`.

`GET /api/files/{key}` — kiểm cookie → kiểm `is_safe_key` → kiểm quyền theo tiền tố → stream.

| Tiền tố | Quyền cần | | Tiền tố | Quyền cần |
|---|---|---|---|---|
| `hr/` | `nhan_su` | | `don-hang/` | `don_hang_ban` |
| `crm/` | `khach_hang` | | `san-xuat/` | `san_xuat` |
| `ke-toan/`, `ke-toan-thu/` | `ke_toan` | | `avatars/` + còn lại | chỉ cần đăng nhập |

Quyền kiểm **trước** khi chạm storage: thiếu quyền thì 403 kể cả file không tồn tại — 404 sẽ rò rỉ
việc hồ sơ đó có tồn tại hay không.

**Frontend không phải sửa** vì `file_url` lưu thẳng `/api/files/...`, mà `assetUrl()`
(`frontend/src/api/client.ts`) vốn chỉ ghép `BASE_URL` vào path bắt đầu bằng `/`.

## 5. Redis

**`app/realtime.py`** — API `subscribe/unsubscribe/publish/broadcast` giữ nguyên.
Có `REDIS_URL`: đẩy JSON `{"user_id": int|null, "event": {...}}` lên channel `svn:events`; mỗi
worker `SUBSCRIBE` rồi bơm vào subscriber cục bộ. Sự kiện do chính worker này publish cũng quay
về qua đường đó — một lối giao duy nhất. Redis hỏng → rơi về đẩy cục bộ (người cùng worker vẫn
nhận) và tự nối lại sau 2s.

**`app/locks.py`** — `SET NX PX`, nhả bằng Lua so-khớp-token (không xoá nhầm khoá người khác đã
lấy sau khi khoá mình hết hạn). TTL 30s để không kẹt vĩnh viễn nếu tiến trình chết giữa chừng.
Không lấy được → `LockBusy` → router trả **409**. Redis hỏng → chạy như chưa có khoá, KHÔNG chặn
nghiệp vụ. Gắn ở `PUT /api/xep-lich/dong/gan-loat`, `POST /api/xep-lich/phat-hanh/lsx/{id}`,
`POST /api/xep-lich/phat-hanh/bai-ghep/{id}`.

**Chưa tăng số uvicorn worker trong đợt này** — hạ tầng sẵn trước, bật sau, đổi một thứ một lúc.

## 6. Compose + profile

**Một file compose duy nhất** — `docker-compose.prod.yml`. Bản dev `docker-compose.yml` đã bỏ:
nó khai trùng `redis`/`minio` (sửa một bên quên bên kia là lệch), mà dev thật của dự án chạy
`./dev.ps1` (uvicorn + vite trên máy, SQLite) chứ không qua compose. Khi dev cần hạ tầng thật thì
dùng chính file này với `--profile redis --profile minio`.

Mỗi service một profile: `db` · `redis` · `minio` · `backend` · `web` · `caddy`.

> **Bẫy:** service có `profiles:` KHÔNG chạy khi `up` trần. Đã kiểm: `docker compose config
> --services` không kèm profile trả về **rỗng** → `up` trần dựng đúng 0 container. Vì vậy
> `deploy.yml` phải liệt kê đủ 6 profile.

**Bật lẻ tới đâu** (đã thử thật — Compose từ chối cả project nếu service được bật lại
`depends_on` service đang tắt):

| Lệnh | Kết quả |
|---|---|
| `--profile db` / `redis` / `minio` | chạy lẻ được |
| `--profile backend` | phải kèm `db redis minio` (chờ cả 3 healthy) |
| `--profile web` | phải kèm `backend` + 3 cái trên — nginx phân giải `backend` **lúc khởi động** |
| `--profile caddy` | phải kèm `web` + chuỗi trên |

Nói gọn: ba service hạ tầng restart lẻ thoải mái; ba service ứng dụng đi theo chuỗi.

Khác: Redis không bật persistence (chỉ pub/sub + khoá); backend **bỏ volume
`uploads:/app/static`**; cổng lấy hết từ `.env` (`HTTP_PORT`/`HTTPS_PORT`/`REDIS_PORT`/
`MINIO_API_PORT`/`MINIO_CONSOLE_PORT`) để prod và staging chạy chung VPS không đá nhau.

Redis/MinIO publish **chỉ trên `127.0.0.1`**, không ra Internet — có mặt để backend chạy ngoài
container (máy dev) nối được và để soi bucket bằng console. Người dùng KHÔNG bao giờ chạm MinIO
trực tiếp; họ đọc file qua `/api/files`, nên **`Caddyfile` không phải sửa gì**. Cổng mặc định
lệch (6380/9010/9002) vì trên VPS 6379/9001 đã có stack khác chiếm.

Healthcheck MinIO dùng `curl` — đã kiểm `curl` và `mc` đều có trong image `minio/minio` bằng cách
chạy thật, không chép từ trí nhớ.

## 7. File env

**Trong git chỉ có `.env.example`** — bản mẫu duy nhất, chứa mọi khoá kèm khối "TRIỂN KHAI THẬT"
liệt kê đúng những dòng phải đổi. Trên máy đích: `cp .env.example .env` rồi điền.

Đã cân nhắc rồi bỏ phương án commit sẵn `.env.prod`/`.env.stg`: tiện hơn (chỉ cần `cp`), nhưng
secret staging sẽ **nằm vĩnh viễn trong lịch sử git** — xoá ở commit sau cũng không gỡ được, ai
được thêm vào repo về sau đều đọc được. Không đáng đổi. Hai file đó nếu có thì chỉ sống **cục bộ**
trên máy vận hành, và `.gitignore` chặn qua `.env.*`.

`COMPOSE_PROJECT_NAME` trong `.env` ghi đè `name:` của compose — đã kiểm: cùng một file compose,
đổi `.env` là ra `erp-svn` hay `erp-svn-stg`. Nhờ đó staging chạy chung một VPS với production
cũng **không đè container và không dùng chung volume**. Kèm điều kiện: `HTTP_PORT`/`HTTPS_PORT`/
`REDIS_PORT`/`MINIO_API_PORT`/`MINIO_CONSOLE_PORT` phải lệch nhau giữa hai môi trường.

`VITE_API_BASE_URL` cũng lấy từ `.env` (không ghi cứng trong compose nữa). Rỗng = same-origin.
Lưu ý nó được **nướng vào bundle lúc build**, nên đổi giá trị phải `up --build` lại service `web`.

## 8. CI/CD

Gate build/test giữ nguyên (offline). Bước SSH thêm:

1. **Kiểm `.env`** trước khi `up` — thiếu khoá hoặc còn `__DIEN_VAO__` thì dừng ngay kèm hướng
   dẫn. `.env` nằm ngoài git nên `git reset --hard` không đụng tới; thêm khoá mới mà quên cập
   nhật là backend crash-loop.
2. Liệt kê đủ 6 profile khi `up`.
3. **Bỏ `--remove-orphans`** — chạy kèm profiles rất dễ xoá nhầm container của profile đang tắt.

## 9. Đã verify bằng gì

- `./init.ps1` (pytest + compileall) — lệnh verify chuẩn của dự án.
- Test mới: `test_storage.py`, `test_files_api.py`, `test_locks.py`.
- **Chạy thật MinIO + Redis** (Docker Desktop): upload → object nằm đúng trong bucket → đọc lại
  qua `/api/files` đúng bytes → chưa đăng nhập 401 → `/static/...` 404 → `hub.broadcast` ra tới
  channel `svn:events`.
- `docker compose config` với cả `.env.prod` lẫn `.env.stg`; kiểm ma trận profile ở §6.
- `npx tsc --noEmit` + `vite build`.

## 10. Còn nợ

- Chưa tăng `--workers` cho uvicorn (hạ tầng đã sẵn sàng, bật khi cần).
- Cache vẫn **chưa làm** — chờ đo được chỗ chậm thật. Ứng viên duy nhất đáng xét: bảng Xếp lịch +
  Danh sách Xung đột (tính-lúc-đọc, chạy 10 detector mỗi lần mở màn).
- Xoá đính kèm ở `employees` / `customers` chỉ xoá row, **không** gỡ bytes — hành vi này có từ
  trước, giữ nguyên trong đợt này để không lẫn phạm vi.
