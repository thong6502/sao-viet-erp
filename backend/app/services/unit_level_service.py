"""Unit-level catalog business logic (Danh mục cấp đơn vị, spec-06 / PBI-4009).

Admin declares the organizational tiers (Khối, Phòng, Tổ, …): each has a unique name,
a unique rank (cao→thấp), and the head's title. Framework-agnostic: raises domain
errors the router maps to HTTP, dedups name + rank, blocks deleting a level still used
by a department, and writes an audit row on every change.
"""
from __future__ import annotations

from ..models.unit_level import UnitLevel
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.rbac_repo import DepartmentRepository, UnitLevelRepository


class UnitLevelError(Exception):
    """Base for unit-level domain errors."""


class UnitLevelNameTaken(UnitLevelError):
    """Another level already uses that name."""


class UnitLevelRankTaken(UnitLevelError):
    """Another level already uses that rank (order)."""


class UnitLevelNotFound(UnitLevelError):
    """No unit level with that id."""


class UnitLevelInUse(UnitLevelError):
    """The level is still assigned to one or more departments — deletion is blocked."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"Không thể xóa: còn {count} đơn vị đang dùng cấp này. "
            "Hãy đổi cấp của các đơn vị đó trước."
        )


class UnitLevelService:
    def __init__(
        self,
        levels: UnitLevelRepository,
        departments: DepartmentRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.levels = levels
        self.departments = departments
        self.audit = audit

    def list_levels(self) -> list[UnitLevel]:
        return self.levels.list_all()

    def create(
        self, *, name: str, rank: int, head_title: str, actor_id: int | None
    ) -> UnitLevel:
        name = name.strip()
        head_title = (head_title or "").strip()
        if self.levels.get_by_name(name) is not None:
            raise UnitLevelNameTaken("Tên cấp đã tồn tại")
        if self.levels.get_by_rank(rank) is not None:
            raise UnitLevelRankTaken("Thứ tự cấp đã được dùng")
        level = self.levels.create(name=name, rank=rank, head_title=head_title)
        self.audit.create(
            actor_user_id=actor_id,
            action="create_unit_level",
            target=f"level:{level.id}",
            detail=f"{name} (rank={rank}, head={head_title})",
        )
        return level

    def update(
        self, *, level_id: int, name: str, rank: int, head_title: str, actor_id: int | None
    ) -> UnitLevel:
        level = self.levels.get_by_id(level_id)
        if level is None:
            raise UnitLevelNotFound("Không tìm thấy cấp đơn vị")
        name = name.strip()
        head_title = (head_title or "").strip()
        clash_name = self.levels.get_by_name(name)
        if clash_name is not None and clash_name.id != level_id:
            raise UnitLevelNameTaken("Tên cấp đã tồn tại")
        clash_rank = self.levels.get_by_rank(rank)
        if clash_rank is not None and clash_rank.id != level_id:
            raise UnitLevelRankTaken("Thứ tự cấp đã được dùng")
        self.levels.update(level, name=name, rank=rank, head_title=head_title)
        self.audit.create(
            actor_user_id=actor_id,
            action="update_unit_level",
            target=f"level:{level_id}",
            detail=f"{name} (rank={rank}, head={head_title})",
        )
        return level

    def delete(self, *, level_id: int, actor_id: int | None) -> None:
        level = self.levels.get_by_id(level_id)
        if level is None:
            raise UnitLevelNotFound("Không tìm thấy cấp đơn vị")
        in_use = self.departments.count_by_level(level_id)
        if in_use > 0:
            raise UnitLevelInUse(in_use)
        name = level.name
        self.levels.delete(level)
        self.audit.create(
            actor_user_id=actor_id,
            action="delete_unit_level",
            target=f"level:{level_id}",
            detail=name,
        )
