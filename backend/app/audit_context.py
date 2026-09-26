"""Ai gửi request đang chạy, nhìn từ tầng repository.

Vì sao cần: `audit_logs` muốn ghi IP + thiết bị, nhưng hơn 200 chỗ gọi `AuditLogRepository.create`
nằm rải khắp services — chúng không cầm `Request` và cũng không nên cầm (service là nghiệp vụ,
không phải HTTP). Thay vì thêm một tham số vào 200 chữ ký, một `ContextVar` do middleware đặt ở
đầu mỗi request và repo đọc ở cuối.

Ngoài request (seeder, tác vụ nền, test gọi thẳng service) thì rỗng — đúng nghĩa "việc của máy".
"""
from __future__ import annotations

from contextvars import ContextVar

_IP: ContextVar[str] = ContextVar("audit_ip", default="")
_UA: ContextVar[str] = ContextVar("audit_ua", default="")


def dat(ip: str, user_agent: str) -> tuple:
    """Đặt vết cho request hiện tại; trả token để middleware trả lại trạng thái cũ."""
    return _IP.set(ip[:45]), _UA.set(user_agent[:255])


def tra_lai(tokens: tuple) -> None:
    t_ip, t_ua = tokens
    _IP.reset(t_ip)
    _UA.reset(t_ua)


def hien_tai() -> tuple[str, str]:
    return _IP.get(), _UA.get()
