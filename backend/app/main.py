"""FastAPI application entrypoint.

Creates the app, applies CORS, mounts routers, and on startup initializes the
schema (create_all) + seeds the admin user. Run with:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import assert_secure_config, settings
from .db import SessionLocal, init_db
from .db_migrations import run_migrations
from .routers import (
    auth,
    attendance,
    costings,
    estimates,
    customers,
    employees,
    machines,
    materials,
    operations,
    warehouses,
    warehouse_items,
    orders,
    paper_sizes,
    imposition_types,
    products,
    product_types_catalog,
    profile,
    quotations,
    rbac,
    plate_die_rates,
    norms,
)
from .seed import seed_all

# Uploaded files (e.g. avatars, spec-04) live under <backend>/static and are served
# read-only at /static. Created up-front so the StaticFiles mount never errors on a
# fresh checkout.
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(products.router)
app.include_router(costings.router)
app.include_router(estimates.router)
app.include_router(quotations.router)
app.include_router(orders.router)
app.include_router(product_types_catalog.router)
app.include_router(materials.router)
app.include_router(machines.router)
app.include_router(operations.router)
app.include_router(paper_sizes.router)
app.include_router(imposition_types.router)
app.include_router(warehouses.router)
app.include_router(warehouse_items.router)
app.include_router(plate_die_rates.router)
app.include_router(norms.router)



@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
