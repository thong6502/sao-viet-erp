"""Tầng lưu file — cửa DUY NHẤT để mọi module ghi/đọc/xoá file người dùng tải lên.

Trước đây 6 chỗ (avatar, hồ sơ HR, tài liệu KH, đính kèm đơn, phiếu chi, phiếu thu) tự
`open(..., "wb")` xuống `<backend>/static` rồi phục vụ CÔNG KHAI qua mount `/static` — ai có
URL là đọc được scan CCCD / hợp đồng lao động / chứng từ kế toán. Giờ bytes đi qua đây, và
người dùng đọc lại qua `/api/files/...` có kiểm đăng nhập + quyền (`app/routers/files.py`).

Chọn backend theo môi trường, KHÔNG phải cấu hình gì thêm:

  - có `MINIO_ENDPOINT` → `MinioStorage` (S3 API — docker/staging/prod)
  - không có           → `LocalStorage` (`<backend>/static`) cho pytest + máy dev không Docker

Ràng buộc này là cố ý: nhờ nó `./init.ps1` và gate CI chạy offline, không cần dựng service ngoài.

Quy ước khoá: `key` là đường dẫn TƯƠNG ĐỐI, không mang tiền tố route —
`"hr/12/ab12cd34_cccd.jpg"`. Cột `file_url` trong DB lưu `url_from_key(key)`, tức
`"/api/files/hr/12/ab12cd34_cccd.jpg"`.
"""
from __future__ import annotations

import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

from .config import settings

# Gốc đĩa của LocalStorage — giữ nguyên <backend>/static để máy dev không phải dọn gì.
LOCAL_ROOT = Path(__file__).resolve().parents[1] / "static"

# Tiền tố route phục vụ file. Đổi hằng này là đổi luôn giá trị ghi vào cột `file_url`.
URL_PREFIX = "/api/files"

_MAX_NAME_LEN = 180
_CHUNK = 64 * 1024


class StorageFileNotFound(Exception):
    """Không có object/file ứng với key."""


# --- khoá & URL -------------------------------------------------------------


def safe_name(file_name: str | None) -> str:
    """Chặn traversal (kể cả "\\" của Windows) + thay ký tự cấm; cắt 180 ký tự.

    Gộp từ `_safe_name` (order_service) và `_safe_attachment_name` (accounting_service) —
    hai bản trước đây giống hệt nhau từng ký tự.
    """
    name = Path((file_name or "file").replace("\\", "/")).name
    return re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)[:_MAX_NAME_LEN].strip(" .") or "file"


def make_key(subdir: str, owner_id: int | str, file_name: str | None) -> tuple[str, str]:
    """Trả `(key, tên_đã_làm_sạch)`.

    Token ngẫu nhiên đứng trước tên để hai file trùng tên của cùng chủ sở hữu không đè nhau —
    đúng hành vi cũ (`secrets.token_hex(4)`).
    """
    safe = safe_name(file_name)
    return f"{subdir}/{owner_id}/{secrets.token_hex(4)}_{safe}", safe


def url_from_key(key: str) -> str:
    return f"{URL_PREFIX}/{key}"


def key_from_url(url: str | None) -> str | None:
    """Ngược của `url_from_key`. Trả None nếu URL không thuộc kho file của mình."""
    if not url:
        return None
    prefix = f"{URL_PREFIX}/"
    return url[len(prefix):] if url.startswith(prefix) else None


def is_safe_key(key: str) -> bool:
    """Khoá hợp lệ: tương đối, nhiều đoạn, không có `..` / đoạn rỗng / ký tự ổ đĩa.

    Gọi TRƯỚC khi chạm storage (router `/api/files` nhận path từ người dùng).
    """
    if not key or key.startswith("/") or "\\" in key or "\x00" in key:
        return False
    parts = key.split("/")
    return all(p and p not in (".", "..") and ":" not in p for p in parts)


# --- các backend ------------------------------------------------------------


@runtime_checkable
class Storage(Protocol):
    def save(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    def open_stream(self, key: str) -> tuple[Iterator[bytes], int | None, str | None]:
        """`(luồng bytes, cỡ nếu biết, content-type nếu biết)`; raise StorageFileNotFound."""
        ...

    def delete(self, key: str) -> None:
        """Best-effort — không có thì thôi, KHÔNG raise (xoá row mới là việc chính)."""
        ...


class LocalStorage:
    """Ghi thẳng xuống đĩa. Dùng cho pytest + máy dev không chạy Docker."""

    def __init__(self, root: Path = LOCAL_ROOT) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key

    def save(self, key: str, data: bytes, content_type: str | None = None) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def open_stream(self, key: str) -> tuple[Iterator[bytes], int | None, str | None]:
        path = self._path(key)
        if not path.is_file():
            raise StorageFileNotFound(key)

        def gen() -> Iterator[bytes]:
            with path.open("rb") as fh:
                while chunk := fh.read(_CHUNK):
                    yield chunk

        # Đĩa không giữ content-type — router tự đoán theo đuôi file.
        return gen(), path.stat().st_size, None

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass  # file rác vô hại; đừng làm hỏng request chỉ vì dọn dẹp


class MinioStorage:
    """MinIO / S3 qua boto3. Bucket riêng tư — không mở lối vào nào từ ngoài."""

    def __init__(self, *, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self._cached_client = None

    @property
    def _client(self):
        # Import trễ: máy dev / CI không cài boto3 vẫn chạy được đường LocalStorage.
        if self._cached_client is None:
            import boto3
            from botocore.config import Config

            self._cached_client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
            )
        return self._cached_client

    def ensure_bucket(self) -> None:
        """Tạo bucket nếu chưa có — gọi lúc startup, khỏi cần container `mc` riêng."""
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self.bucket)
            except ClientError:
                # Worker khác vừa tạo xong → coi như thành công.
                self._client.head_bucket(Bucket=self.bucket)

    def save(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)

    def open_stream(self, key: str) -> tuple[Iterator[bytes], int | None, str | None]:
        from botocore.exceptions import ClientError

        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NoSuchBucket"):
                raise StorageFileNotFound(key) from None
            raise
        body = obj["Body"]
        return body.iter_chunks(_CHUNK), obj.get("ContentLength"), obj.get("ContentType")

    def delete(self, key: str) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError:
            pass  # giống LocalStorage: dọn dẹp best-effort


# --- lựa chọn backend -------------------------------------------------------


@lru_cache
def get_storage() -> Storage:
    if settings.minio_endpoint:
        return MinioStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
        )
    return LocalStorage()


def ensure_storage_ready() -> None:
    """Chuẩn bị storage lúc startup (tạo bucket). No-op với LocalStorage."""
    store = get_storage()
    if isinstance(store, MinioStorage):
        store.ensure_bucket()
