"""Imposition Type Repository — master data access.

Version-chain (spec E): a `code` identifies a FAMILY of imposition types; each edit of a
type already used in a báo giá snapshot creates a new row with the same `code` and a higher
`version`. Unique is (code, version). The "current" row of a family is the highest version
whose effective window covers the lookup date (effective_to NULL = open). The pricing engine
resolves by code (fallback name) at the calc date via :meth:`resolve_active`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session
from ..models.imposition_type import ImpositionType

_SORTABLE = {
    "code": ImpositionType.code,
    "name": ImpositionType.name,
    "sides": ImpositionType.sides,
    "priority": ImpositionType.priority,
    "created_at": ImpositionType.created_at,
}


def _effective_at(at_date: date):
    """Rows whose effective window covers `at_date` (NULL bounds = open)."""
    return and_(
        or_(ImpositionType.effective_from.is_(None), ImpositionType.effective_from <= at_date),
        or_(ImpositionType.effective_to.is_(None), ImpositionType.effective_to > at_date),
    )


class ImpositionTypeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, item_id: int) -> ImpositionType | None:
        return self.db.execute(
            select(ImpositionType).where(ImpositionType.id == item_id)
        ).scalars().first()

    def find_by_code_any_version(self, code: str) -> ImpositionType | None:
        """Any row of a code family (highest version) — for duplicate check on create."""
        code = (code or "").strip()
        if not code:
            return None
        return self.db.execute(
            select(ImpositionType)
            .where(func.upper(ImpositionType.code) == code.upper())
            .order_by(ImpositionType.version.desc())
        ).scalars().first()

    def max_version_for_code(self, code: str) -> int:
        val = self.db.execute(
            select(func.max(ImpositionType.version)).where(
                func.upper(ImpositionType.code) == (code or "").strip().upper()
            )
        ).scalar()
        return int(val or 0)

    def find_by_name(self, name: str) -> ImpositionType | None:
        """Highest-version row matching a name — kept for the engine's name fallback."""
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(ImpositionType)
            .where(func.lower(ImpositionType.name) == name.lower())
            .order_by(ImpositionType.version.desc())
        ).scalars().first()

    def resolve_active(
        self, *, code: str | None = None, name: str | None = None, at_date: date
    ) -> ImpositionType | None:
        """Resolve the current row for the pricing engine: by code first, then name,
        picking the effective-at-`at_date` row with the highest version."""
        if code and code.strip():
            row = self.db.execute(
                select(ImpositionType)
                .where(func.upper(ImpositionType.code) == code.strip().upper())
                .where(_effective_at(at_date))
                .order_by(ImpositionType.version.desc())
            ).scalars().first()
            if row:
                return row
        if name and name.strip():
            row = self.db.execute(
                select(ImpositionType)
                .where(func.lower(ImpositionType.name) == name.strip().lower())
                .where(_effective_at(at_date))
                .order_by(ImpositionType.version.desc())
            ).scalars().first()
            if row:
                return row
        return None

    def versions_of(self, code: str, exclude_id: int | None = None) -> list[ImpositionType]:
        """All rows (every version) of a code family — for the history view + overlap check."""
        rows = self.db.execute(
            select(ImpositionType)
            .where(func.upper(ImpositionType.code) == (code or "").strip().upper())
            .order_by(ImpositionType.version.desc())
        ).scalars()
        return [r for r in rows if exclude_id is None or r.id != exclude_id]

    def list(
        self,
        *,
        q: str | None = None,
        code: str | None = None,
        is_active: bool | None = None,
        current_only: bool = False,
        sort: str = "priority",
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ImpositionType], int]:
        conditions = []
        if code:
            conditions.append(func.upper(ImpositionType.code) == code.strip().upper())
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(ImpositionType.name).like(like),
                    func.lower(ImpositionType.code).like(like),
                )
            )
        if is_active is not None:
            conditions.append(ImpositionType.is_active == is_active)
        if current_only:
            # Only the live version of each family (superseded rows have effective_to in the past).
            conditions.append(_effective_at(date.today()))

        base = select(ImpositionType)
        count_stmt = select(func.count()).select_from(ImpositionType)

        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "priority"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, ImpositionType.priority)
        # Secondary sort by code so families group; tie-break by id.
        base = base.order_by(direction(col), ImpositionType.code.asc(), ImpositionType.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    def create(self, *, code: str, version: int = 1, **fields) -> ImpositionType:
        item = ImpositionType(code=code.strip().upper(), version=version, **fields)
        self.db.add(item)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return item

    def update(self, item: ImpositionType, **fields) -> ImpositionType:
        for k, v in fields.items():
            setattr(item, k, v)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return item

    def supersede_and_create_version(
        self, base_item: ImpositionType, *, effective_from: date, **fields
    ) -> ImpositionType:
        """Version-chain: close the current row (effective_to = today, deactivate) and insert a
        new row with the same code, version+1, effective_from = today, carrying `fields`."""
        new_version = self.max_version_for_code(base_item.code) + 1
        base_item.effective_to = effective_from
        base_item.is_active = False
        new_item = ImpositionType(
            code=base_item.code,
            version=new_version,
            effective_from=effective_from,
            **fields,
        )
        self.db.add(new_item)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_item

    def increment_used_count(self, item: ImpositionType, by: int = 1, commit: bool = True) -> None:
        item.used_count = int(item.used_count or 0) + by
        if commit:
            self.db.commit()

    def delete(self, item: ImpositionType) -> None:
        self.db.delete(item)
        self.db.commit()
