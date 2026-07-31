# Sao Việt Nhật ERP

Nền tảng ERP full-stack: **xác thực (JWT)** + **phân quyền (RBAC)** — bộ khung để các module
nghiệp vụ cắm vào sau. Backend FastAPI phân tầng, frontend React + Vite, chạy SQLite (dev) hoặc
PostgreSQL (prod) trên cùng một tầng dữ liệu.

## Tính năng

- **Đăng nhập JWT** — access token ngắn hạn + refresh token trong httpOnly cookie (tự xoay
  vòng); phiên tự gia hạn nền, người dùng không bị văng giữa chừng.
- **Phân quyền (RBAC)** — phòng ban · vai trò (riêng từng phòng) · ma trận quyền CRUD + phạm vi
  dữ liệu (Của tôi / Cả phòng / Tất cả).
- **Quản trị** — màn hình Người dùng · Phòng ban · Vai trò · Nhật ký hoạt động.
- **Bảo mật** — hash bcrypt, thu hồi token tức thì (`token_version`), logout server-side, guard
  chặn JWT secret yếu ở production, ghi audit log.

## Công nghệ

| Lớp | Công nghệ |
|---|---|
| Frontend | React 18 · Vite 5 · TypeScript (SPA, cổng `5173`) |
| Backend | FastAPI (Python), phân tầng `routes → services → repositories → DB` (cổng `8000`) |
| Database | SQLite (dev/test) · PostgreSQL 16 qua Docker (prod) — chung tầng SQLAlchemy |
| Auth | JWT (access token + refresh cookie) · bcrypt |

## Bắt đầu nhanh

**Yêu cầu:** Python 3.10+ · Node.js 18+ (khuyến nghị 20/22) · Docker *(tùy chọn — chỉ khi dùng PostgreSQL)*.

```bash
# 1) Cài đặt: deps backend + frontend, tạo .env từ mẫu nếu thiếu
./setup.ps1      # Windows / PowerShell
./setup.sh       # Unix / macOS

# 2) Chạy backend (:8000) + frontend (:5173) cùng lúc
./dev.ps1        # Windows
./dev.sh         # Unix
```

Mở **http://localhost:5173** rồi đăng nhập bằng tài khoản seed sẵn (đăng nhập bằng **tên đăng nhập**):

| Tên đăng nhập | Mật khẩu |
|---|---|
| `admin` | `admin123` |

API docs tự sinh khi backend chạy: **http://localhost:8000/docs**.

> **Trước khi deploy thật:** đặt `APP_ENV=production` và một `JWT_SECRET` ngẫu nhiên (≥ 32 ký
> tự). Backend sẽ **từ chối khởi động** nếu secret còn để mặc định.

## Kiểm thử

```bash
./init.ps1       # Windows
./init.sh        # Unix / CI
```

Lệnh xác minh chuẩn duy nhất — chạy `pytest` + `compileall` (hiện **308 passed**).

## Đổi schema — bẫy làm đỏ CI nhiều nhất

Dự án **không có Alembic**. `create_all` chỉ TẠO bảng mới, **không ALTER** bảng đã có. Mỗi lần
đụng vào model phải làm đủ ba việc, trong **cùng một commit**:

1. **Bảng mới** → export ở `backend/app/models/__init__.py`. Quên là `create_all` không thấy bảng.
2. **Thêm/đổi cột của bảng đã có** → viết hàm trong `backend/app/db_migrations.py` rồi đăng ký vào
   `MIGRATIONS`. DB live/prod chỉ nhận cột mới qua đường này; máy dev thì xoá `backend/dev.db`
   cho tạo lại cũng được.
3. **Ghi vào [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md)** — mọi bảng và **mọi cột** phải có mặt.

Việc thứ 3 có test canh (`backend/tests/test_schema_documented.py`): thiếu một cột là gate
`Build & test` đỏ và **deploy bị chặn**, dù toàn bộ test khác xanh. Kiểm trước khi push:

```bash
cd backend && python -m pytest tests/test_schema_documented.py -q
```

Thêm bảng thì chép khung sẵn ở mục *"Template for a new table"* cuối `DB_SCHEMA.md`.

> **Đừng đánh lại số migration.** Trong `MIGRATIONS` có nhiều dãy số song song trùng nhau (`0113`
> xuất hiện ở cả dãy lương, dãy kho lẫn dãy tính giá) — đó là chủ ý, vì khoá thật trong bảng
> `schema_migrations` là **cả chuỗi id**. Đổi id của migration đã chạy là DB sẽ chạy lại nó.

## Chạy với Docker (Postgres / Redis / MinIO)

**Một file compose duy nhất** (`docker-compose.yml`) và **một lệnh duy nhất** cho mọi môi trường:

```bash
docker compose up -d --build
```

Dựng service nào là do `COMPOSE_PROFILES` trong `.env` quyết — không phải gõ `--profile`.

**Máy dev** (`COMPOSE_PROFILES=db,redis,minio`): chỉ dựng hạ tầng. Không có `caddy` nên **không
đụng gì tới chứng chỉ**. Backend + frontend chạy ngoài bằng `./dev` để giữ hot-reload:

```bash
cp .env.example .env
docker compose up -d
./dev
```

`backend/.env` đã trỏ sẵn vào ba container đó (`127.0.0.1:5433` Postgres, `:6380` Redis,
`:9010` MinIO — console MinIO ở <http://127.0.0.1:9002>). Comment ba biến hạ tầng trong
`backend/.env` là quay về SQLite + ghi đĩa, không cần Docker.

**Triển khai** (`COMPOSE_PROFILES=db,redis,minio,backend,web,caddy`): cùng lệnh trên, dựng full
stack kèm TLS. Chỉ cần dán nội dung env của môi trường đó vào `.env` trước.

Backend tự tạo bảng (`create_all`) + seed admin lúc khởi động.
Chi tiết profile, cổng và luồng deploy: `docs/spec-ha-tang-redis-minio.md`.

## Cấu hình (`.env`)

Secrets nạp từ `.env` (đã gitignore — **không commit**). Mỗi tầng một file:

| File | Dùng cho |
|---|---|
| `.env` | `docker compose` — chép từ `.env.example` rồi điền (xem khối "TRIỂN KHAI THẬT" trong đó) |
| `backend/.env` | backend chạy local qua `./dev` (`JWT_SECRET`, `DATABASE_URL`, seed) |
| `frontend/.env` | `VITE_API_BASE_URL` — **công khai**, không để secret |

Ba file phục vụ ba đối tượng khác nhau (compose · backend-trên-máy · bundle FE) và có khoá
trùng tên nhưng khác nghĩa — **đừng gộp**. `backend/app/config.py` cố ý trỏ `env_file` bằng
đường dẫn tuyệt đối tới `backend/.env` để `.env` của compose không lọt vào cấu hình app.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md) | Từ điển dữ liệu — mọi bảng/cột |
| [docs/DOMAIN_NHA_MAY_IN.md](docs/DOMAIN_NHA_MAY_IN.md) | Cẩm nang domain nhà máy in offset |
| [docs/CROSS_MODULE_LINKS.md](docs/CROSS_MODULE_LINKS.md) | Context Map — sổ mối nối chéo phân hệ (seam) |
