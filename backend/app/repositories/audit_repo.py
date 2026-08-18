"""Audit-log data access. The only layer that touches the DB for audit rows."""
from __future__ import annotations

from datetime import datetime, timezone

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

    def create_collapsing(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        target: str,
        detail: str = "",
    ) -> AuditLog:
        """Như `create` nhưng GỘP thao tác lặp liên tiếp: nếu bản ghi MỚI NHẤT của cùng `target`
        trùng cả `action` lẫn actor → CẬP NHẬT thời điểm + chi tiết của nó thay vì thêm dòng mới.
        Dùng cho các thao tác dễ lặp (vd lưu nháp báo giá nhiều lần) để nhật ký không phình vô tận;
        một action KHÁC xen vào giữa sẽ tách thành mục mới. Không dùng cho audit tuân thủ (cần đủ dòng)."""
        latest = self.db.execute(
            select(AuditLog)
            .where(AuditLog.target == target)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None and latest.action == action and latest.actor_user_id == actor_user_id:
            latest.created_at = datetime.now(timezone.utc)
            latest.detail = detail
            self.db.commit()
            self.db.refresh(latest)
            return latest
        return self.create(
            actor_user_id=actor_user_id, action=action, target=target, detail=detail
        )

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        return list(
            self.db.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
            ).scalars()
        )

    def list_by_action(self, action: str, limit: int = 200) -> list[AuditLog]:
        """Audit rows của MỘT loại thao tác (vd ``kho_export``), mới nhất trước — cho màn lịch sử."""
        return list(
            self.db.execute(
                select(AuditLog)
                .where(AuditLog.action == action)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(limit)
            ).scalars()
        )

    def list_by_target(self, target: str, limit: int = 200) -> list[AuditLog]:
        """Audit rows for one entity (e.g. ``customer:42``), newest first — feeds the
        per-record "Nhật ký" timeline."""
        return list(
            self.db.execute(
                select(AuditLog)
                .where(AuditLog.target == target)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(limit)
            ).scalars()
        )

    def list_for_target(self, target: str, limit: int = 50) -> list[AuditLog]:
        """Recent audit rows whose action targeted a given entity (spec-08 per-user activity)."""
        return self.list_by_target(target, limit=limit)

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(AuditLog)).scalar_one()
