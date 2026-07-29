"""Real-time event hub (SSE) — luồng "gửi duyệt" nội bộ đẩy tức thì.

Nguyên tắc sản phẩm (CLAUDE.md): gửi/thông báo NỘI BỘ phải REAL-TIME.

Hai chế độ, chọn theo `REDIS_URL`, API của hub giữ nguyên nên mọi chỗ gọi `publish/broadcast`
không phải sửa dòng nào:

  - **Không có Redis** (test, máy dev): đẩy IN-PROCESS: mọi kết nối SSE nằm chung 1 tiến trình
    nên 1 dict trong RAM là đủ. Ràng buộc: đúng **1 uvicorn worker**.
  - **Có Redis**: `publish/broadcast` bắn lên channel `svn:events`, mỗi worker `SUBSCRIBE` rồi
    bơm vào subscriber cục bộ của mình → chạy được **nhiều worker**. Redis chớp tắt thì rơi về
    đẩy cục bộ (người cùng worker vẫn nhận) và tự nối lại.

An toàn luồng: endpoint SYNC của FastAPI chạy trong threadpool, KHÔNG phải thread của event loop.
`asyncio.Queue` không thread-safe → mọi thao tác đẩy được lịch qua `loop.call_soon_threadsafe` để
chạy trên loop. `set_loop()` gọi 1 lần lúc startup (main.py). Nếu chưa có loop (vd test) → no-op.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

# Mọi worker cùng nghe một channel; `user_id = None` nghĩa là broadcast.
CHANNEL = "svn:events"

# Redis chết thì thử lại sau ngần này giây — đừng để mất hẳn kênh đẩy chỉ vì một cú chớp mạng.
_RECONNECT_DELAY = 2.0


class EventHub:
    def __init__(self) -> None:
        # user_id -> tập hàng đợi (1 người có thể mở nhiều tab).
        self._subs: dict[int, set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis: Any = None
        # Giữ tham chiếu task đang bay, nếu không Python có thể thu gom giữa chừng.
        self._pending: set[asyncio.Task] = set()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def connect_redis(self, url: str) -> None:
        """Bật chế độ pub/sub. Gọi lúc startup khi có REDIS_URL (main.py)."""
        import redis.asyncio as redis  # import trễ: không có Redis thì khỏi cần thư viện

        self._redis = redis.from_url(url, decode_responses=True)

    @property
    def uses_redis(self) -> bool:
        return self._redis is not None

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
        self._dispatch(user_id, event)

    def broadcast(self, event: dict[str, Any]) -> None:
        """Đẩy 1 sự kiện tới MỌI kết nối đang mở (tín hiệu 'danh sách chờ duyệt đổi')."""
        self._dispatch(None, event)

    # --- nội bộ ---------------------------------------------------------------
    def _dispatch(self, user_id: int | None, event: dict[str, Any]) -> None:
        if self._redis is None:
            self._schedule(lambda: self._deliver_local(user_id, event))
            return
        self._schedule(lambda: self._spawn(self._publish_redis(user_id, event)))

    def _deliver_local(self, user_id: int | None, event: dict[str, Any]) -> None:
        """Bơm vào subscriber của CHÍNH tiến trình này (chạy trên loop)."""
        if user_id is None:
            for qs in list(self._subs.values()):
                self._put(qs, event)
        else:
            self._put(self._subs.get(user_id, ()), event)

    async def _publish_redis(self, user_id: int | None, event: dict[str, Any]) -> None:
        payload = json.dumps({"user_id": user_id, "event": event}, default=str)
        try:
            await self._redis.publish(CHANNEL, payload)
        except Exception:
            # Redis hỏng: ít nhất người dùng cùng worker vẫn nhận được — đẩy cục bộ bù.
            self._deliver_local(user_id, event)

    async def run_redis_bridge(self) -> None:
        """Task nền: nghe channel rồi bơm vào subscriber cục bộ. Chạy suốt vòng đời app.

        Sự kiện do CHÍNH worker này publish cũng quay về qua đây — một đường giao duy nhất,
        không phải phân nhánh 'của mình' / 'của worker khác'.
        """
        while True:
            pubsub = None
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        payload = json.loads(message["data"])
                    except (ValueError, TypeError):
                        continue  # rác trên channel không được làm chết cầu nối
                    self._deliver_local(payload.get("user_id"), payload.get("event") or {})
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(_RECONNECT_DELAY)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

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
