# Sao Việt Nhật ERP

Nền tảng ERP full-stack: **xác thực (JWT)** + **phân quyền (RBAC)** — bộ khung để các module
nghiệp vụ cắm vào sau. Backend FastAPI phân tầng, frontend React + Vite, chạy SQLite (dev) hoặc
PostgreSQL (prod) trên cùng một tầng dữ liệu.

> Dự án được phát triển theo **vòng lặp GAN 3 vai** (Planner · Generator · Evaluator). Nếu bạn
> làm việc bằng AI agent, đọc [AGENTS.md](AGENTS.md) trước.

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
> tự). Backend sẽ **từ chối khởi động** nếu secret còn để mặc định — xem [docs/SECURITY.md](docs/SECURITY.md).

## Kiểm thử

```bash
./init.ps1       # Windows
./init.sh        # Unix / CI
```

Lệnh xác minh chuẩn duy nhất — chạy `pytest` + `compileall` (hiện **78 passed**).

## Chạy với PostgreSQL (Docker)

Mặc định là SQLite (zero-config). Để dùng PostgreSQL:

```bash
cp .env.example .env       # chỉnh secrets nếu cần
docker compose up -d       # Postgres + backend API (:8000)
```

Backend tự tạo bảng (`create_all`) + seed admin lúc khởi động; frontend vẫn chạy bằng `./dev`.
Chi tiết tầng dữ liệu và lựa chọn SQLite ⇄ Postgres: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Cấu hình (`.env`)

Secrets nạp từ `.env` (đã gitignore — **không commit**). Mỗi tầng một file, kèm `*.env.example`
làm mẫu; `./setup` tự tạo nếu chưa có:

| File | Dùng cho |
|---|---|
| `.env` | `docker compose` (Postgres + backend) |
| `backend/.env` | backend chạy local (`JWT_SECRET`, `DATABASE_URL`, seed) |
| `frontend/.env` | `VITE_API_BASE_URL` — **công khai**, không để secret |

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Kiến trúc, phân tầng, domain map |
| [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md) | Từ điển dữ liệu — mọi bảng/cột |
| [docs/SECURITY.md](docs/SECURITY.md) | Chính sách secrets & dữ liệu không tin cậy |
| [docs/UI_DESIGN.md](docs/UI_DESIGN.md) | Hệ design (tokens, components, UI states) |
| [docs/product-specs/](docs/product-specs/) | Spec từng đợt: `spec-01` auth · `spec-02` RBAC · `spec-03` hardening |
| [AGENTS.md](AGENTS.md) · [QUICKSTART.md](QUICKSTART.md) | Quy trình phát triển bằng GAN loop |
