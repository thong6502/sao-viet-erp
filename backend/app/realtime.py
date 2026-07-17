"""Cập nhật tức thời cho module Kho qua SSE (Server-Sent Events).

Cách làm: mỗi kết nối SSE định kỳ (~1.5s) tính một "chữ ký" nhẹ của dữ liệu kho
(số lượng + updated_at mới nhất của đề nghị & phiếu). Khi chữ ký đổi (có tạo/sửa/xóa/
duyệt ở BẤT KỲ đâu) thì đẩy sự kiện → client tải lại ngay. Không phải gắn publish vào
từng endpoint; đúng cho dev-scale (1 worker). Nhiều worker/nhiều node thì cần Redis pub/sub.
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import func
from starlette.concurrency import run_in_threadpool


def _kho_signature(warehouse_id: int | None = None) -> str:
    """Chữ ký trạng thái kho — đổi khi có thay đổi đề nghị hoặc phiếu (session riêng, ngắn).
    Lọc theo warehouse_id để chỉ báo đổi cho ĐÚNG kho đang mở (đỡ refresh chéo giữa các kho)."""
    from .db import SessionLocal
    from .models.stock_request import StockRequest
    from .models.warehouse_voucher import StockVoucher

    db = SessionLocal()
    try:
        rq = db.query(func.count(StockRequest.id), func.max(StockRequest.updated_at))
        if warehouse_id is not None:
            rq = rq.filter(StockRequest.warehouse_id == warehouse_id)
        rc, rm = rq.one()
        vq = db.query(func.count(StockVoucher.id), func.max(StockVoucher.updated_at))
        if warehouse_id is not None:
            vq = vq.filter(
                (StockVoucher.src_warehouse_id == warehouse_id)
                | (StockVoucher.dst_warehouse_id == warehouse_id)
            )
        vc, vm = vq.one()
        return f"{rc}|{rm}|{vc}|{vm}"
    finally:
        db.close()


def _ycmh_open_count() -> int:
    """Số YÊU CẦU MUA HÀNG (YCMH) đang chờ thu mua xử lý (status='open') — badge + toast 'mới'."""
    from .db import SessionLocal
    from .models.purchase import DPR_OPEN, DepartmentPurchaseRequest

    db = SessionLocal()
    try:
        return db.query(func.count(DepartmentPurchaseRequest.id)).filter(
            DepartmentPurchaseRequest.status == DPR_OPEN
        ).scalar() or 0
    finally:
        db.close()


async def ycmh_event_stream():
    """Generator SSE: đẩy số YCMH chờ xử lý khi đổi (tạo mới/duyệt/hủy) → badge + toast realtime."""
    last: int | None = None
    yield "retry: 3000\n\n"
    idle = 0
    while True:
        n = await run_in_threadpool(_ycmh_open_count)
        if n != last:
            last = n
            idle = 0
            yield f"data: {json.dumps({'open': n})}\n\n"
        else:
            idle += 1
            if idle >= 12:
                idle = 0
                yield ": ping\n\n"
        await asyncio.sleep(1.5)


async def kho_event_stream(warehouse_id: int | None = None):
    """Generator SSE: đẩy sự kiện khi chữ ký đổi; ping định kỳ giữ kết nối."""
    last: str | None = None
    yield "retry: 3000\n\n"  # trình duyệt tự kết nối lại sau 3s nếu rớt
    idle = 0
    while True:
        sig = await run_in_threadpool(_kho_signature, warehouse_id)
        if sig != last:
            last = sig
            idle = 0
            yield f"data: {json.dumps({'sig': sig})}\n\n"
        else:
            idle += 1
            if idle >= 12:  # ~18s không đổi → gửi comment ping chống timeout proxy
                idle = 0
                yield ": ping\n\n"
        await asyncio.sleep(1.5)
