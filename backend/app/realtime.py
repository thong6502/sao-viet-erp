"""In-process real-time event hub (SSE) — luồng "gửi duyệt" nội bộ đẩy tức thì.

Nguyên tắc sản phẩm (CLAUDE.md): gửi/thông báo NỘI BỘ phải REAL-TIME. Ở đây đẩy IN-PROCESS theo
**1 uvicorn worker** — mọi kết nối SSE nằm chung 1 tiến trình nên 1 dict trong RAM là đủ, KHÔNG cần
Redis/LISTEN-NOTIFY. Nếu sau này scale >1 worker thì thay `publish/broadcast` bằng Postgres
LISTEN/NOTIFY (mỗi worker LISTEN rồi forward vào subscriber cục bộ) — API của hub giữ nguyên.

An toàn luồng: endpoint SYNC của FastAPI chạy trong threadpool, KHÔNG phải thread của event loop.
`asyncio.Queue` không thread-safe → mọi thao tác đẩy được lịch qua `loop.call_soon_threadsafe` để
chạy trên loop. `set_loop()` gọi 1 lần lúc startup (main.py). Nếu chưa có loop (vd test) → no-op.
"""
from __future__ import annotations

import asyncio
from typing import Any


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
