"""Auth primitives: password hashing (bcrypt) and JWT encode/decode.

Pure functions with no DB or HTTP knowledge — callable from services. Secrets come
from config/env, never hard-coded (docs/SECURITY.md).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

# bcrypt operates on the first 72 bytes; longer inputs are truncated by the algorithm.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    pw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    # Số vòng lấy từ cấu hình (mặc định 12). `verify_password` đọc số vòng TỪ CHÍNH chuỗi băm
    # nên hạ/nâng cấu hình không làm hỏng mật khẩu đã lưu — xem `Settings.bcrypt_rounds`.
    return bcrypt.hashpw(pw, bcrypt.gensalt(settings.bcrypt_rounds)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# Claim `typ` phân biệt hai loại token cùng ký bằng jwt_secret. Không có nó thì cookie file
# (sống 7 ngày) dùng thay Bearer được → leo quyền. Mỗi decoder chỉ nhận đúng loại của mình.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_FILE = "file"


def _encode(subject: str, token_version: int, *, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "tv": token_version,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str, *, token_type: str) -> dict | None:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    # Token cũ (phát trước khi có `typ`) coi như access — chỉ ảnh hưởng phiên đang mở lúc deploy.
    if claims.get("typ", TOKEN_TYPE_ACCESS) != token_type:
        return None
    return claims


def create_access_token(subject: str, token_version: int = 0) -> str:
    """Issue a signed JWT whose `sub` claim is the user id (as a string).

    `token_version` is embedded as the `tv` claim; the request path rejects a token whose
    `tv` no longer matches the user's current `token_version` (spec-03 hard-revoke).
    """
    return _encode(
        subject,
        token_version,
        token_type=TOKEN_TYPE_ACCESS,
        expires=timedelta(minutes=settings.access_token_expire_minutes),
    )


def decode_access_token(token: str) -> dict | None:
    """Return the JWT claims, or None if the token is invalid/expired/không phải access token."""
    return _decode(token, token_type=TOKEN_TYPE_ACCESS)


def create_file_token(subject: str, token_version: int = 0) -> str:
    """Token đặt trong cookie `file_access` để `<img src>` đọc được /api/files.

    `<img>` do trình duyệt tự phát nên KHÔNG mang được header Bearer, mà access token cố ý chỉ
    nằm trong RAM của tab (frontend/src/auth/AuthContext.tsx). Cookie là đường duy nhất. Sống
    bằng refresh token để không chết giữa phiên; `tv` khiến đổi-mật-khẩu/logout-all giết luôn nó.
    """
    return _encode(
        subject,
        token_version,
        token_type=TOKEN_TYPE_FILE,
        expires=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_file_token(token: str) -> dict | None:
    return _decode(token, token_type=TOKEN_TYPE_FILE)


def generate_refresh_token() -> str:
    """A high-entropy opaque refresh token (the value placed in the httpOnly cookie)."""
    return secrets.token_urlsafe(48)


# Ambiguous characters (0/O/1/l/I) left out so a handed-over temp password is easy to read.
_TEMP_PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def generate_temp_password(length: int = 12) -> str:
    """A readable, high-entropy temporary password shown ONCE on admin reset (spec-08).
    Never stored in plaintext — only its bcrypt hash is persisted."""
    return "".join(secrets.choice(_TEMP_PW_ALPHABET) for _ in range(length))


def hash_refresh_token(raw: str) -> str:
    """SHA-256 hex digest stored in the DB; the plaintext token is never persisted."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
