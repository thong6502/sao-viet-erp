# GAN App — Auth Foundation

Ứng dụng web full-stack được dựng theo **vòng lặp GAN 3 vai** (xem [AGENTS.md](AGENTS.md) /
[QUICKSTART.md](QUICKSTART.md)). Spec hiện tại: **khung dự án + đăng nhập** (seeded-user JWT login).

| Lớp | Công nghệ |
|---|---|
| Frontend | React 18 + Vite 5 + **TypeScript** (SPA, cổng `5173`) |
| Backend | **FastAPI** (Python), phân tầng `routes → services → repositories → DB` (cổng `8000`) |
| Database | **SQLite** (local/test) · **PostgreSQL 16** qua Docker (prod/dev) — chung một tầng SQLAlchemy |
| Auth | JWT bearer token, mật khẩu hash bằng **bcrypt** |

---

## Yêu cầu môi trường

- **Python** 3.10+ · **Node.js** 18+ (khuyến nghị 20/22) · **Docker** + Docker Compose (chỉ cần khi chạy Postgres)

---

## Chạy nhanh (local, dùng SQLite — không cần Docker)

Cài dependencies **một phát** (cài backend + frontend, tạo `.env` nếu thiếu):

```powershell
./setup.ps1     # Windows / PowerShell
./setup.sh      # Unix / macOS
```

Hoặc làm thủ công:

```powershell
python -m pip install -r backend/requirements.txt   # backend
cd frontend; npm install; cd ..                     # frontend
```

Mở **2 cửa sổ** terminal ở thư mục gốc dự án:

```powershell
# Cửa sổ 1 — Backend API (:8000)
cd backend
python -m uvicorn app.main:app --port 8000
```

```powershell
# Cửa sổ 2 — Frontend SPA (:5173)
cd frontend
npm run dev
```

Rồi mở 👉 **http://localhost:5173**

### Tài khoản demo (seed sẵn)

| Email | Mật khẩu |
|---|---|
| `admin@example.com` | `admin123` |

> Đây là creds dev mặc định — **đổi `JWT_SECRET` và mật khẩu seed** trước khi deploy thật.

Dừng server: **Ctrl + C** trong cửa sổ tương ứng.

---

## Chạy với PostgreSQL (Docker)

```powershell
# 1) Tạo file .env từ mẫu (đã gitignore)
cp .env.example .env

# 2) Khởi động Postgres trong Docker
docker compose up -d db          # Postgres lên cổng 5432

# 3a) Cách A — backend chạy local trỏ vào Postgres:
#     mở backend\.env, đổi sang dòng DATABASE_URL=postgresql+psycopg2://...
cd backend; python -m uvicorn app.main:app --port 8000

# 3b) Cách B — chạy cả stack trong Docker:
docker compose up -d             # Postgres + backend (cổng 8000)
```

Backend tự `create_all` (tạo bảng) + seed admin lúc khởi động. Frontend vẫn chạy bằng `npm run dev`.

---

## Kiểm thử / Verify

Lệnh xác minh chuẩn duy nhất (chạy `pytest` + `compileall`):

```powershell
./init.ps1     # Windows / PowerShell
./init.sh      # Unix / macOS / CI
```

Phải **PASS** (hiện tại `11 passed`): smoke test của template + test auth + guard schema-doc.

---

## API

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/health` | Health check → `{"status":"ok"}` |
| `POST` | `/api/auth/login` | Body `{email, password}` → `{access_token, token_type, user}` (sai creds → `401`) |
| `GET` | `/api/auth/me` | Header `Authorization: Bearer <token>` → user hiện tại (thiếu/sai token → `401`) |

Tài liệu tự sinh khi backend chạy: **http://localhost:8000/docs**

---

## Cấu trúc dự án

```
backend/
  app/
    main.py            # FastAPI app, CORS, lifespan (create_all + seed)
    config.py          # cấu hình từ env (.env)
    db.py              # engine/session/Base (SQLite ⇄ Postgres)
    security.py        # bcrypt + JWT
    deps.py            # DI: db → repo → service, current-user
    models/            # ORM (bảng `users`)
    schemas/           # Pydantic (request/response)
    repositories/      # tầng DUY NHẤT chạm DB
    services/          # business logic (auth)
    routers/           # HTTP routes (auth)
    seed.py            # seed admin
  tests/               # pytest (auth + schema guard)
  Dockerfile · requirements.txt · .env.example
frontend/
  src/
    api/client.ts      # tầng DUY NHẤT biết URL backend
    auth/              # AuthContext + useAuth (token, /me)
    components/        # Button, Field
    pages/             # LoginPage, DashboardPage
    styles/            # tokens.css (design tokens), global.css
  index.html · vite.config.ts · tsconfig.json · .env.example
docker-compose.yml     # db (Postgres) + backend
docs/                  # ARCHITECTURE, UI_DESIGN, DB_SCHEMA, EVALUATION, specs...
init.ps1 / init.sh     # lệnh verify chuẩn
```

---

## Biến môi trường

Mỗi nơi có một `*.env.example` mẫu (file `.env` thật bị gitignore — **không commit secrets**):

- **Root `.env`** — cho `docker compose` (Postgres creds, JWT, seed admin).
- **`backend/.env`** — cho backend chạy local (`DATABASE_URL`, JWT, seed).
- **`frontend/.env`** — `VITE_API_BASE_URL` (mặc định `http://localhost:8000`).

---

## Database & Schema

- DB chỉ có một bảng ở spec này: **`users`**.
- **Mọi schema được ghi tại [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md)** (ý nghĩa từng cột, khóa, index).
  Một test guard ([backend/tests/test_schema_documented.py](backend/tests/test_schema_documented.py))
  bắt `init` đỏ nếu model có bảng/cột chưa được ghi trong doc → schema và tài liệu không lệch nhau.
- Chưa dùng Alembic (cố ý ở spec-01); schema dựng bằng `create_all`.

---

## Tài liệu thêm

| File | Nội dung |
|---|---|
| [AGENTS.md](AGENTS.md) | Router chỉ dẫn cho agent (luồng, quy tắc, "xong" là gì) |
| [QUICKSTART.md](QUICKSTART.md) | Đường nhanh chạy vòng lặp GAN |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Kiến trúc, layer model, domain map |
| [docs/UI_DESIGN.md](docs/UI_DESIGN.md) | Hệ design (tokens, components, UI states) |
| [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md) | Từ điển dữ liệu (schema) |
| [docs/product-specs/spec-01-auth.md](docs/product-specs/spec-01-auth.md) | Spec hiện tại |
| [progress.md](progress.md) | Nhật ký tiến độ |
