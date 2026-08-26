"""FastAPI application entrypoint.

Creates the app, applies CORS, mounts routers, and on startup initializes the
schema (create_all) + seeds the admin user. Run with:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import assert_secure_config, settings
from .db import SessionLocal, init_db
from .db_migrations import run_migrations
from .routers import (
    accounting,
    module_notifications,
    auth,
    attendance,
    calendar,
    leaves,
    late_early,
    overtime,
    payroll,
    customers,
    employees,
    files,
    machines,
    operations,
    product_types_catalog,
    purchases,
    noi_quy,
    profile,
    quotations,
    orders,
    rbac,
    may_thiet_bi,
    vat_lieu_kho,
    cong_doan,
    cong_viec_khoan,
    bu_hao,
    don_vi_do,
    bien_cong_thuc,
    kho,
    kho_baocao,
    delivery,
    kho_request,
    kho_voucher,
    public_scan,
    khuon_be,
    loai_san_pham,
    danh_muc_xoa,
    nhat_ky_danh_muc,
    notifications,
    tinh_gia,
    phieu_tinh_gia,
    lsx,
    bai_ghep_2,
    xep_lich_2,
    ke_hoach_vat_tu,
    ky_thuat_may,
    san_xuat,
    san_xuat_ly_do,
    cong_doan_tag,
)
from .seed import seed_all

# File người dùng tải lên KHÔNG còn mount công khai ở /static — chúng đi qua kho file
# (app/storage.py) và chỉ đọc được qua /api/files sau khi kiểm đăng nhập + quyền
# (app/routers/files.py). Mount cũ là lỗ hở: ai có URL là xem được CCCD/hợp đồng/chứng từ.


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Real-time SSE hub: ghim event loop đang chạy để publisher (endpoint sync trong threadpool) đẩy
    # sự kiện an toàn qua call_soon_threadsafe (app/realtime.py).
    from .realtime import hub
    hub.set_loop(asyncio.get_running_loop())
    # Có REDIS_URL → đẩy qua pub/sub, chạy được nhiều worker. Không có → in-process, 1 worker.
    if settings.redis_url:
        hub.connect_redis(settings.redis_url)
    # Refuse to boot in production with an insecure JWT secret (no-op in development).
    assert_secure_config(settings)
    # Tạo bucket MinIO nếu chưa có (no-op khi chạy LocalStorage — test/dev không Docker).
    from .storage import ensure_storage_ready
    ensure_storage_ready()
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
    # Ticker nhắc lịch hẹn chăm sóc real-time (SSE): quét hẹn tới giờ → "ting" người phụ trách.
    # 0 = tắt (test). Chạy nền, huỷ khi shutdown.
    reminder_task: asyncio.Task | None = None
    bao_tri_task: asyncio.Task | None = None
    if settings.care_reminder_seconds > 0:
        from .care_reminders import run_care_reminder_loop
        reminder_task = asyncio.create_task(run_care_reminder_loop(settings.care_reminder_seconds))
        # Nhắc phiếu bảo trì tới hạn — dùng chung công tắc `care_reminder_seconds` (0 = tắt trong
        # test). Quét thưa hơn 10 lần: hẹn khách tính bằng phút, còn bảo trì tính bằng NGÀY, quét
        # dày chỉ tốn vòng lặp chứ không sớm hơn được phút nào.
        from .bao_tri_reminders import run_bao_tri_reminder_loop
        bao_tri_task = asyncio.create_task(
            run_bao_tri_reminder_loop(max(60, settings.care_reminder_seconds * 10))
        )
    # Cầu Redis→SSE: nghe channel chung, bơm sự kiện vào các kết nối của worker này.
    bridge_task: asyncio.Task | None = None
    if hub.uses_redis:
        bridge_task = asyncio.create_task(hub.run_redis_bridge())
    try:
        yield
    finally:
        for task in (reminder_task, bao_tri_task, bridge_task):
            if task is not None:
                task.cancel()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(files.router)
app.include_router(profile.router)
app.include_router(noi_quy.router)
app.include_router(rbac.router)
app.include_router(customers.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(calendar.router)
app.include_router(leaves.router)
app.include_router(overtime.router)
app.include_router(late_early.router)
app.include_router(payroll.router)
app.include_router(quotations.router)
app.include_router(orders.router)
app.include_router(product_types_catalog.router)
app.include_router(purchases.router)
app.include_router(accounting.router)
app.include_router(module_notifications.router)
app.include_router(machines.router)
app.include_router(operations.router)
# Gỡ (2026-07-16): products · plate_die_rates · norms — không màn nào gọi, module quyền đã bỏ
# (migration 0069). Gỡ (2026-08-08, Đợt 5): materials · costings · estimates — cụm tính giá đời cũ
# đã xoá hẳn. Bảng norms/plate_die_rates GIỮ: engine tính giá đang chạy vẫn đọc.
app.include_router(may_thiet_bi.router)
app.include_router(may_thiet_bi.nhom_may_router)   # danh mục Nhóm máy (cùng module quyền)
app.include_router(vat_lieu_kho.router)
app.include_router(cong_doan.router)
app.include_router(cong_viec_khoan.router)     # đơn giá khoán theo tổ (trước ở tab của màn Lương)
app.include_router(san_xuat_ly_do.router)      # danh mục Lý do & lỗi SX (module quyền `dm_ly_do_san_xuat`)
app.include_router(bu_hao.router)
app.include_router(don_vi_do.router)
app.include_router(bien_cong_thuc.router)
# Các router con của Kho phải đăng ký TRƯỚC `kho.router`: kho.router có `/api/kho/{kho_id}`
# (1 đoạn) nên sẽ nuốt `/api/kho/de-nghi` và `/api/kho/nguong-ton` nếu đứng trước —
# FastAPI khớp theo THỨ TỰ đăng ký, không theo độ cụ thể.
app.include_router(delivery.router)
app.include_router(kho_request.router)
app.include_router(kho_voucher.router)
app.include_router(kho_voucher.threshold_router)
# Điều chuyển kho: /api/kho/dieu-chuyen — path RIÊNG, đăng ký TRƯỚC kho.router (path 1 đoạn).
app.include_router(kho_voucher.dieu_chuyen_router)
# Báo cáo kho (kế toán): /api/kho/bao-cao/* + /api/kho/khoa-so — TRƯỚC kho.router (path 1 đoạn).
app.include_router(kho_baocao.router)
app.include_router(notifications.router)
# Router CÔNG KHAI (không auth) — trang tra kho khi quét tem QR. Mã ký HMAC chống dò id.
app.include_router(public_scan.router)
app.include_router(kho.router)
app.include_router(khuon_be.router)
app.include_router(loai_san_pham.router)
app.include_router(nhat_ky_danh_muc.router)   # nhật ký 1 bản ghi — chung cho 11 màn danh mục
app.include_router(danh_muc_xoa.router)       # "còn ai dùng không" — chung cho 9 màn danh mục
app.include_router(tinh_gia.router)
app.include_router(phieu_tinh_gia.router)
app.include_router(lsx.router)
# Màn Bài ghép cũ gỡ 18/08/2026 (mg 0216) — router `/api/bai-ghep` xoá, chỉ còn bản này. ENGINE
# (`services/bai_ghep_service.py` + `repositories/bai_ghep_repo.py`) vẫn là của chung, đừng nhầm
# là code chết: router này chạy trên đó.
app.include_router(bai_ghep_2.router)
app.include_router(xep_lich_2.router)        # Bàn Xếp lịch công đoạn (module quyền `xep_lich_2`; màn cũ `xep_lich` gỡ 19/08/2026)
app.include_router(ke_hoach_vat_tu.router)   # bảng cân đối vật tư (cùng module quyền `san_xuat`)
app.include_router(ky_thuat_may.router)      # sửa chữa + phiếu bảo trì (module quyền `ky_thuat_may`)
app.include_router(san_xuat.router)          # bàn Thực hiện sản xuất tại tổ (cùng module quyền `san_xuat`)
app.include_router(cong_doan_tag.router)     # nhãn gán cho bước công đoạn — dùng chung LSX + Bài ghép (module quyền `san_xuat`)



@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
