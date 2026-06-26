"""Audit-log data access. The only layer that touches the DB for audit rows."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.audit import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        target: str = "",
        detail: str = "",
    ) -> AuditLog:
        entry = AuditLog(
            actor_user_id=actor_user_id, action=action, target=target, detail=detail
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        return list(
            self.db.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
            ).scalars()
        )

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(AuditLog)).scalar_one()
