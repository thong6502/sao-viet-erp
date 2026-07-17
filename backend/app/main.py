"""FastAPI application entrypoint.

Creates the app, applies CORS, mounts routers, and on startup initializes the
schema (create_all) + seeds the admin user. Run with:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import assert_secure_config, settings
from .db import SessionLocal, init_db
from .db_migrations import run_migrations
from .routers import (
    accounting,
    auth,
    attendance,
    calendar,
    leaves,
    payroll,
    costings,
    estimates,
    customers,
    employees,
    machines,
    materials,
    operations,
    warehouses,
    warehouse_items,
    kho_stock,
    kho_voucher,
    kho_count,
    product_types_catalog,
    purchases,
    profile,
    quotations,
    orders,
    rbac,
    may_thiet_bi,
    vat_lieu_kho,
    cong_doan,
    bu_hao,
    loai_san_pham,
    tinh_gia,
    phieu_tinh_gia,
)
from .seed import seed_all

# Uploaded files (e.g. avatars, spec-04) live under <backend>/static and are served
# read-only at /static. Created up-front so the StaticFiles mount never errors on a
# fresh checkout.
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Real-time SSE hub: ghim event loop đang chạy để publisher (endpoint sync trong threadpool) đẩy
    # sự kiện an toàn qua call_soon_threadsafe (app/realtime.py). Chỉ đúng khi 1 uvicorn worker.
    from .realtime import hub
    hub.set_loop(asyncio.get_running_loop())
    # Refuse to boot in production with an insecure JWT secret (no-op in development).
    assert_secure_config(settings)
    # create_all + idempotent seed (RBAC catalog/roles + admin). Alembic is a later spec.
    init_db()
    db = SessionLocal()
    try:
        # create_all never ALTERs existing tables; run tracked additive migrations so the
        # persistent prod DB picks up new columns before seed/queries touch them.
        run_migrations(db)
        seed_all(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(rbac.router)
app.include_router(customers.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(calendar.router)
app.include_router(leaves.router)
app.include_router(payroll.router)
app.include_router(costings.router)
app.include_router(estimates.router)
app.include_router(quotations.router)
app.include_router(orders.router)
app.include_router(product_types_catalog.router)
app.include_router(purchases.router)
app.include_router(accounting.router)
app.include_router(materials.router)
app.include_router(machines.router)
app.include_router(operations.router)
app.include_router(warehouses.router)
app.include_router(warehouse_items.router)
app.include_router(kho_stock.router)
app.include_router(kho_voucher.router)
app.include_router(kho_count.router)
# Gỡ (2026-07-16): products · plate_die_rates · norms — không màn nào gọi, module quyền đã bỏ
# (migration 0069). Bảng + repo GIỮ: engine tính giá vẫn đọc norms/plate_die_rates.
app.include_router(may_thiet_bi.router)
app.include_router(vat_lieu_kho.router)
app.include_router(cong_doan.router)
app.include_router(bu_hao.router)
app.include_router(loai_san_pham.router)
app.include_router(tinh_gia.router)
app.include_router(phieu_tinh_gia.router)



@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
