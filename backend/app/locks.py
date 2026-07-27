"""Khoá chống chạy trùng — cho vài thao tác mà bấm hai lần ra hai kết quả khác nhau.

Chỗ dùng: `Tự xếp lịch` (gán loạt) và `Phát hành lệnh`. Hai người cùng bấm, hoặc một người
double-click, thì lần sau phải bị chặn thay vì chen vào giữa lần trước.

Không có `REDIS_URL` → no-op (test + máy dev 1 worker: không có ai để mà tranh). Có Redis →
`SET NX PX`, nên khoá đúng cả khi chạy nhiều uvicorn worker.

TTL để khoá tự tan nếu tiến trình giữ khoá chết giữa chừng — không bao giờ kẹt vĩnh viễn.
"""
from __future__ import annotations

import secrets
from contextlib import contextmanager

from .config import settings

_PREFIX = "svn:lock:"
_DEFAULT_TTL_MS = 30_000

# Chỉ xoá khoá nếu giá trị đúng của mình — tránh xoá nhầm khoá người khác vừa lấy sau khi
# khoá của mình đã hết hạn.
_UNLOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

_client = None


class LockBusy(Exception):
    """Ai đó đang chạy đúng việc này. Router dịch thành 409."""


def _redis():
    global _client
    if not settings.redis_url:
        return None
    if _client is None:
        import redis  # import trễ: không có Redis thì khỏi cần thư viện

        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


@contextmanager
def lock(name: str, *, ttl_ms: int = _DEFAULT_TTL_MS):
    """Giữ khoá `name` trong khối `with`. Không lấy được → raise `LockBusy`."""
    client = _redis()
    if client is None:
        yield
        return

    key = f"{_PREFIX}{name}"
    token = secrets.token_hex(8)
    try:
        acquired = client.set(key, token, nx=True, px=ttl_ms)
    except Exception:
        # Redis hỏng KHÔNG được chặn nghiệp vụ — chạy như lúc chưa có khoá.
        yield
        return

    if not acquired:
        raise LockBusy(name)
    try:
        yield
    finally:
        try:
            client.eval(_UNLOCK_LUA, 1, key, token)
        except Exception:
            pass  # khoá sẽ tự hết hạn theo TTL
