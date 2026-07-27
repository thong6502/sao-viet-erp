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

## Chạy với Docker (Postgres / Redis / MinIO)

Mặc định là SQLite + ghi file xuống đĩa (zero-config, `./dev` là đủ). Chỉ dùng Docker khi cần
hạ tầng thật.

Dự án có **một file compose duy nhất**: `docker-compose.prod.yml`. Mỗi service mang một
`profile` riêng, nên **`docker compose up` trần sẽ dựng 0 container** — phải liệt kê profile:

```bash
cp .env.example .env
# chỉ Redis + MinIO cho backend chạy ngoài container (cách hay dùng nhất khi dev)
docker compose -f docker-compose.prod.yml --profile redis --profile minio up -d
# thêm Postgres + backend trong container
docker compose -f docker-compose.prod.yml --profile db --profile redis --profile minio --profile backend up -d --build
```

Rồi trỏ backend vào: `REDIS_URL=redis://127.0.0.1:6380/0`, `MINIO_ENDPOINT=http://127.0.0.1:9010`
(console MinIO: <http://127.0.0.1:9002>). Bỏ hai biến này là quay về in-process + ghi đĩa.

Backend tự tạo bảng (`create_all`) + seed admin lúc khởi động; frontend vẫn chạy bằng `./dev`.
Chi tiết profile, `.env.prod`/`.env.stg` và luồng deploy: `docs/spec-ha-tang-redis-minio.md`.

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
