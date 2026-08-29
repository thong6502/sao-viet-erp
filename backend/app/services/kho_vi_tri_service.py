"""Service — VỊ TRÍ cất của kho (`kho_vi_tri`).

Luật nhẹ: kho phải tồn tại; mã vị trí không trống; không trùng mã TRONG cùng kho (dòng đã xoá mềm
cùng mã → BẬT LẠI thay vì đẻ dòng mới, tránh đụng UNIQUE). Truy DB chỉ qua repo; router chỉ điều phối.
"""
from __future__ import annotations

from ..models.kho_hang import KhoViTri
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.kho_vi_tri_repo import KhoViTriRepository


class KhoViTriError(Exception):
    """Lỗi nghiệp vụ vị trí kho (đế cho các lỗi cụ thể)."""


class KhoViTriKhoNotFound(KhoViTriError):
    pass


class KhoViTriNotFound(KhoViTriError):
    pass


class KhoViTriValidationError(KhoViTriError):
    pass


class KhoViTriDuplicate(KhoViTriError):
    pass


class KhoViTriService:
    def __init__(
        self,
        repo: KhoViTriRepository,
        kho_repo: KhoHangRepository,
        audit: AuditLogRepository | None = None,
    ) -> None:
        self.repo = repo
        self.kho_repo = kho_repo
        self.audit = audit

    def _ensure_kho(self, kho_id: int):
        kho = self.kho_repo.get(kho_id)
        if kho is None or not getattr(kho, "active", True):
            raise KhoViTriKhoNotFound("Không tìm thấy kho.")
        return kho

    def list(self, kho_id: int) -> list[KhoViTri]:
        self._ensure_kho(kho_id)
        return self.repo.list_by_kho(kho_id, chi_active=True)

    def create(self, kho_id: int, ma: str, ghi_chu: str | None, actor_id: int | None) -> KhoViTri:
        self._ensure_kho(kho_id)
        ma = (ma or "").strip()
        if not ma:
            raise KhoViTriValidationError("Tên vị trí không được trống.")
        ghi_chu = (ghi_chu or "").strip() or None

        san_co = self.repo.find_by_ma(kho_id, ma)
        if san_co is not None:
            if san_co.active:
                raise KhoViTriDuplicate("Vị trí này đã có trong kho.")
            obj = self.repo.reactivate(san_co, ghi_chu)   # cùng mã, đã xoá mềm → bật lại
        else:
            obj = self.repo.create(kho_id, ma, ghi_chu)

        self.repo.db.commit()
        self.repo.db.refresh(obj)
        if self.audit is not None:
            self.audit.create(
                actor_user_id=actor_id, action="kho_vi_tri_create",
                target=f"kho:{kho_id}", detail=ma,
            )
        return obj

    def delete(self, vi_tri_id: int, actor_id: int | None) -> None:
        obj = self.repo.get(vi_tri_id)
        if obj is None or not obj.active:
            raise KhoViTriNotFound("Không tìm thấy vị trí.")
        self.repo.soft_delete(obj)
        self.repo.db.commit()
        if self.audit is not None:
            self.audit.create(
                actor_user_id=actor_id, action="kho_vi_tri_delete",
                target=f"kho:{obj.kho_id}", detail=obj.ma,
            )
