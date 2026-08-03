"""Nghiệp vụ danh mục tài liệu nội quy."""
from __future__ import annotations

from datetime import datetime, timezone
import secrets
import string

from sqlalchemy.exc import IntegrityError

from ..repositories.audit_repo import AuditLogRepository
from ..repositories.noi_quy_repo import NoiQuyRepository
from ..storage import get_storage, key_from_url, make_key, url_from_key


class NoiQuyError(Exception):
    pass


class NoiQuyValidationError(NoiQuyError):
    pass


class NoiQuyNotFound(NoiQuyError):
    pass


_ALPHABET = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"


def _clean(value: str | None, *, max_length: int, required: bool = False) -> str | None:
    cleaned = " ".join((value or "").split())
    if required and not cleaned:
        raise NoiQuyValidationError("Tên tài liệu là bắt buộc.")
    if len(cleaned) > max_length:
        raise NoiQuyValidationError(f"Nội dung không được vượt quá {max_length} ký tự.")
    return cleaned or None


def _new_code() -> str:
    date_part = datetime.now(timezone.utc).strftime("%y%m%d")
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    return f"NQ-{date_part}-{suffix}"


class NoiQuyService:
    def __init__(self, noi_quy: NoiQuyRepository, audit: AuditLogRepository | None = None) -> None:
        self.noi_quy = noi_quy
        self.audit = audit

    def list_records(self):
        return self.noi_quy.list_all()

    def create_record(
        self,
        *,
        name: str,
        note: str | None,
        file_name: str,
        file_type: str,
        data: bytes,
        actor,
    ):
        clean_name = _clean(name, max_length=200, required=True)
        clean_note = _clean(note, max_length=500)

        for _ in range(8):
            code = _new_code()
            if self.noi_quy.code_exists(code):
                continue
            key, safe_file_name = make_key("noi-quy", code, file_name)
            get_storage().save(key, data, file_type)
            try:
                row = self.noi_quy.create(
                    code=code,
                    name=clean_name,
                    note=clean_note,
                    file_name=safe_file_name,
                    file_url=url_from_key(key),
                    file_type=file_type,
                    file_size=len(data),
                    uploaded_by=actor.id,
                )
            except IntegrityError:
                get_storage().delete(key)
                continue
            if self.audit is not None:
                self.audit.create(
                    actor_user_id=actor.id,
                    action="create_noi_quy_record",
                    target=f"noi_quy_record:{row.id}",
                    detail=f"{row.code} - {row.name}",
                )
            return row
        raise NoiQuyValidationError("Không thể tạo mã tài liệu. Vui lòng thử lại.")

    def delete_record(self, record_id: int, *, actor) -> None:
        row = self.noi_quy.get(record_id)
        if row is None:
            raise NoiQuyNotFound("Không tìm thấy tài liệu nội quy.")
        file_key = key_from_url(row.file_url)
        detail = f"{row.code} - {row.name}"
        self.noi_quy.delete(row)
        if file_key:
            get_storage().delete(file_key)
        if self.audit is not None:
            self.audit.create(
                actor_user_id=actor.id,
                action="delete_noi_quy_record",
                target=f"noi_quy_record:{record_id}",
                detail=detail,
            )
