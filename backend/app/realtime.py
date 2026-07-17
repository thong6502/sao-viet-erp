"""Real-time nội bộ (SSE) — gộp 2 cơ chế:

1) EventHub in-process (luồng "gửi duyệt"): đẩy IN-PROCESS theo **1 uvicorn worker** — mọi kết nối
   SSE chung 1 tiến trình nên 1 dict trong RAM là đủ, KHÔNG cần Redis. Scale >1 worker thì thay
   `publish/broadcast` bằng Postgres LISTEN/NOTIFY — API của hub giữ nguyên.
   An toàn luồng: endpoint SYNC chạy trong threadpool → mọi thao tác đẩy được lịch qua
   `loop.call_soon_threadsafe`. `set_loop()` gọi 1 lần lúc startup (main.py).

2) Chữ ký kho / đếm YCMH (module Kho + Mua hàng): mỗi kết nối SSE định kỳ (~1.5s) tính một "chữ ký"
   nhẹ; khi đổi (tạo/sửa/xóa/duyệt ở bất kỳ đâu) thì đẩy → client tải lại ngay. Dùng cho dev-scale.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import func
from starlette.concurrency import run_in_threadpool


class EventHub:
    def __init__(self) -> None:
        # user_id -> tập hàng đợi (1 người có thể mở nhiều tab).
        self._subs: dict[int, set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # --- phía SSE endpoint (chạy trên loop) -----------------------------------
    def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.setdefault(user_id, set()).add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        subs = self._subs.get(user_id)
        if subs is not None:
            subs.discard(q)
            if not subs:
                self._subs.pop(user_id, None)

    # --- phía publisher (có thể chạy trong threadpool → schedule lên loop) -----
    def publish(self, user_id: int, event: dict[str, Any]) -> None:
        """Đẩy 1 sự kiện tới MỌI kết nối của 1 người dùng."""
        self._schedule(lambda: self._put(self._subs.get(user_id, ()), event))

    def broadcast(self, event: dict[str, Any]) -> None:
        """Đẩy 1 sự kiện tới MỌI kết nối đang mở (dùng cho tín hiệu 'danh sách chờ duyệt đổi')."""
        def deliver() -> None:
            for qs in list(self._subs.values()):
                self._put(qs, event)
        self._schedule(deliver)

    # --- nội bộ ---------------------------------------------------------------
    @staticmethod
    def _put(queues, event: dict[str, Any]) -> None:
        for q in list(queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Người nhận quá chậm/đứt: bỏ sự kiện — badge tự lành qua notify-summary khi reconnect.
                pass

    def _schedule(self, fn) -> None:
        loop = self._loop
        if loop is None:
            return  # chưa có loop (test/headless) → no-op, không vỡ luồng nghiệp vụ
        try:
            loop.call_soon_threadsafe(fn)
        except RuntimeError:
            # loop đã đóng (đang shutdown) → bỏ qua.
            pass


# Singleton dùng chung toàn app.
hub = EventHub()


# ============================================================================
# Module Kho + Mua hàng — SSE theo "chữ ký" (không gắn publish vào từng endpoint).
# ============================================================================
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
