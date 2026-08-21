"""Chạy schema (create_all + migration) RỜI KHỎI app — để deploy migrate TRƯỚC khi thay container.

Vì sao tồn tại (chốt 2026-08-09): migration vẫn chạy trong lifespan của app (`main.py`), nhưng nếu
CHỈ có đường đó thì migration lỗi ⇒ container MỚI chết ⇒ mà container cũ thì `docker compose up -d`
đã thay rồi ⇒ mất dịch vụ. Staging chết 21 giờ đúng theo đường này: migration 0171 raise, app không
khởi động nổi, `docker compose ps` vẫn đẹp nên Actions xanh.

Deploy nay gọi file này bằng **container tạm** (`docker compose run --rm backend python -m
app.migrate`) trước bước `up -d`. Migration lỗi thì script deploy dừng tại đó và **app cũ vẫn đang
phục vụ** — không ai mất gì ngoài một lần deploy đỏ.

Chạy hai lần vô hại: mỗi bước đã ghi id vào `schema_migrations` nên lượt sau là no-op. Nhờ vậy
lifespan của app vẫn gọi `run_migrations` như cũ, không phải sửa gì ở đó.

CỐ Ý KHÔNG làm ở đây: `ensure_storage_ready` (MinIO chết không được phép chặn migration), seed dữ
liệu, ticker SSE. File này chỉ lo SCHEMA.
"""
from __future__ import annotations

from .db import SessionLocal, init_db
from .db_migrations import run_migrations


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        run_migrations(db)
    finally:
        db.close()
    print("migration OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
