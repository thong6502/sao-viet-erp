"""Activity-log read logic: the most recent audit rows with the actor's name
resolved for display. Read-only — audit rows are written by the other services."""
from __future__ import annotations

from ..repositories.audit_repo import AuditLogRepository
from ..repositories.user_repo import UserRepository


class ActivityService:
    def __init__(self, audit: AuditLogRepository, users: UserRepository) -> None:
        self.audit = audit
        self.users = users

    def list_recent(self, limit: int = 100) -> list[dict]:
        names: dict[int, str | None] = {}
        rows: list[dict] = []
        for entry in self.audit.list_recent(limit):
            actor_name = None
            if entry.actor_user_id is not None:
                if entry.actor_user_id not in names:
                    u = self.users.get_by_id(entry.actor_user_id)
                    names[entry.actor_user_id] = u.name if u else None
                actor_name = names[entry.actor_user_id]
            rows.append(
                {
                    "id": entry.id,
                    "actor_user_id": entry.actor_user_id,
                    "actor_name": actor_name,
                    "action": entry.action,
                    "target": entry.target,
                    "detail": entry.detail,
                    "created_at": entry.created_at,
                }
            )
        return rows
