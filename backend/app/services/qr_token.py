"""Ký / kiểm mã QR tra kho CÔNG KHAI — HMAC stateless (không lưu DB, không đổi schema).

Tem QR dán kệ trỏ tới trang tra kho công khai (không đăng nhập). Để không ai đoán id tuần
tự (`#kho=2&sp=18`) mà xem trộm tồn/vị trí toàn kho trên internet, mã nhúng trong QR là
`payload.chu_ky`:
  - payload = "kho_id:material_id"
  - chu_ky  = HMAC-SHA256(khoá QR, payload)  (khoá QR dẫn xuất từ jwt_secret + domain-sep)
Chỉ tem in ra TỪ hệ thống mới có chữ ký hợp lệ; đổi id → chữ ký sai → 404. Không tiết lộ giá.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from ..config import settings

# Domain separation: khoá QR dẫn xuất từ jwt_secret nhưng KHÁC mục đích ký JWT.
_QR_CONTEXT = b"kho-scan-qr-v1"
# 12 byte (96-bit) chữ ký — đủ chống giả mạo cho dữ liệu tồn kho nội bộ, giữ QR gọn.
_SIG_BYTES = 12


def _key() -> bytes:
    return hmac.new(settings.jwt_secret.encode(), _QR_CONTEXT, hashlib.sha256).digest()


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_scan(kho_id: int, material_id: int) -> str:
    """Sinh mã QR (đưa vào link `#s=<mã>`) cho 1 vật tư ở 1 kho."""
    payload = f"{kho_id}:{material_id}".encode()
    sig = hmac.new(_key(), payload, hashlib.sha256).digest()[:_SIG_BYTES]
    return f"{_b64u(payload)}.{_b64u(sig)}"


def verify_scan(token: str) -> tuple[int, int] | None:
    """Kiểm mã QR → (kho_id, material_id) nếu chữ ký hợp lệ; None nếu sai/hỏng."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64u_decode(payload_b64)
        expected = hmac.new(_key(), payload, hashlib.sha256).digest()[:_SIG_BYTES]
        if not hmac.compare_digest(expected, _b64u_decode(sig_b64)):
            return None
        kho_s, mat_s = payload.decode().split(":", 1)
        return int(kho_s), int(mat_s)
    except (ValueError, TypeError):
        return None
