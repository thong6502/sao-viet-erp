"""Phiếu tăng ca data access — tầng DUY NHẤT chạm DB cho `overtime_requests`.
Không chứa luật nghiệp vụ (những thứ đó ở `OvertimeService`)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models.employee import Employee
from ..models.overtime import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    OvertimeRequest,
)
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from .org_scope import dept_subtree_ids

_DECIDED = (STATUS_APPROVED, STATUS_REJECTED)
_LIVE = (STATUS_PENDING, STATUS_APPROVED)


class OvertimeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- CRUD ---------------------------------------------------------------

    def create_request(self, **fields) -> OvertimeRequest:
        r = OvertimeRequest(**fields)
        self.db.add(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    def get_request(self, request_id: int) -> OvertimeRequest | None:
        return self.db.get(OvertimeRequest, request_id)

    def update_request(self, r: OvertimeRequest, **fields) -> OvertimeRequest:
        for key, value in fields.items():
            setattr(r, key, value)
        self.db.commit()
        self.db.refresh(r)
        return r

    def list_by_employee(self, employee_id: int, *, limit: int = 100,
                         offset: int = 0) -> list[OvertimeRequest]:
        return list(
            self.db.execute(
                select(OvertimeRequest)
                .where(OvertimeRequest.employee_id == employee_id)
                .order_by(OvertimeRequest.work_date.desc(), OvertimeRequest.id.desc())
                .limit(limit)
                .offset(offset)
            ).scalars()
        )

    def count_by_employee(self, employee_id: int) -> int:
        """Tổng phiếu của 1 NV — nuôi chân phân trang tab "Phiếu của tôi". COUNT ở DB, đừng
        `len(list_by_employee())`: hàm kia đang bị `limit` cắt nên đếm ra số của TRANG."""
        return int(self.db.execute(
            select(func.count(OvertimeRequest.id))
            .where(OvertimeRequest.employee_id == employee_id)
        ).scalar_one())

    # --- scope-aware reads (own = phiếu của mình theo Employee.user_id; department =
    #     phiếu của phòng/tổ mình + cây con; all = tất cả). `overtime_requests` KHÔNG có cột
    #     user/phòng nên phải JOIN employees — giống hệt leave_repo. ---------------------

    def _scope_condition(self, *, scope: str, actor):
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_OWN:
            return Employee.user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            dept_ids = dept_subtree_ids(self.db, actor.department_id)
            if not dept_ids:
                return Employee.user_id == actor.id
            return Employee.department_id.in_(dept_ids)
        raise ValueError(f"Unknown scope: {scope!r}")

    def _scoped_filters(self, stmt, *, scope: str, actor, status: str | None,
                        employee_id: int | None):
        """Bộ lọc DÙNG CHUNG cho `list_scoped` và `count_scoped` — hai hàm lọc lệch nhau thì
        `total` ở chân bảng không mở ra xem được (báo 30, lật hết trang chỉ thấy 12)."""
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        if status is not None:
            stmt = stmt.where(OvertimeRequest.status == status)
        if employee_id is not None:
            stmt = stmt.where(OvertimeRequest.employee_id == employee_id)
        return stmt

    def list_scoped(self, *, scope: str, actor, status: str | None = None,
                    employee_id: int | None = None, limit: int = 200,
                    offset: int = 0) -> list[OvertimeRequest]:
        stmt = select(OvertimeRequest).join(Employee, OvertimeRequest.employee_id == Employee.id)
        stmt = self._scoped_filters(stmt, scope=scope, actor=actor, status=status,
                                    employee_id=employee_id)
        stmt = stmt.order_by(
            OvertimeRequest.status.asc(), OvertimeRequest.work_date.desc(), OvertimeRequest.id.desc()
        ).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars())

    def count_scoped(self, *, scope: str, actor, status: str | None = None,
                     employee_id: int | None = None) -> int:
        """Tổng phiếu trong phạm vi + bộ lọc — chân phân trang tab "Duyệt phiếu"."""
        stmt = (
            select(func.count(OvertimeRequest.id))
            .select_from(OvertimeRequest)
            .join(Employee, OvertimeRequest.employee_id == Employee.id)
        )
        stmt = self._scoped_filters(stmt, scope=scope, actor=actor, status=status,
                                    employee_id=employee_id)
        return int(self.db.execute(stmt).scalar_one())

    def count_pending_scoped(self, *, scope: str, actor) -> int:
        """Số phiếu ĐANG CHỜ DUYỆT trong scope người gọi — nuôi badge sidebar (COUNT ở DB)."""
        stmt = (
            select(func.count(OvertimeRequest.id))
            .select_from(OvertimeRequest)
            .join(Employee, OvertimeRequest.employee_id == Employee.id)
            .where(OvertimeRequest.status == STATUS_PENDING)
        )
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return int(self.db.execute(stmt).scalar_one())

    def count_my_unseen(self, employee_id: int) -> int:
        """Số phiếu của NV đã ĐƯỢC QUYẾT mà NV chưa xem — nuôi chuông Topbar."""
        stmt = select(func.count(OvertimeRequest.id)).where(
            OvertimeRequest.employee_id == employee_id,
            OvertimeRequest.status.in_(_DECIDED),
            OvertimeRequest.seen_by_employee_at.is_(None),
        )
        return int(self.db.execute(stmt).scalar_one())

    def mark_my_seen(self, employee_id: int) -> None:
        self.db.execute(
            update(OvertimeRequest)
            .where(
                OvertimeRequest.employee_id == employee_id,
                OvertimeRequest.status.in_(_DECIDED),
                OvertimeRequest.seen_by_employee_at.is_(None),
            )
            .values(seen_by_employee_at=datetime.now(timezone.utc))
        )
        self.db.commit()

    # --- nguồn cho Bảng công tháng -----------------------------------------

    def approved_in_range(self, start: date, end: date) -> list[OvertimeRequest]:
        """Phiếu ĐÃ DUYỆT có `work_date` trong [start, end] — Bảng công dùng để chặn TRẦN tiền
        tăng ca theo phiếu (phần giờ vượt ca nằm ngoài phiếu không ra tiền)."""
        return list(
            self.db.execute(
                select(OvertimeRequest).where(
                    OvertimeRequest.status == STATUS_APPROVED,
                    OvertimeRequest.work_date >= start,
                    OvertimeRequest.work_date <= end,
                )
            ).scalars()
        )

    def live_for_day(self, employee_id: int, work_date: date, *,
                     exclude_id: int | None = None) -> list[OvertimeRequest]:
        """Phiếu còn hiệu lực (chờ duyệt hoặc đã duyệt) của 1 NV trong 1 ngày công — nền cho luật
        'tối đa 1 phiếu/ngày'. `exclude_id` để đường SỬA không tự đếm chính phiếu đang sửa."""
        stmt = select(OvertimeRequest).where(
            OvertimeRequest.employee_id == employee_id,
            OvertimeRequest.work_date == work_date,
            OvertimeRequest.status.in_(_LIVE),
        )
        if exclude_id is not None:
            stmt = stmt.where(OvertimeRequest.id != exclude_id)
        return list(self.db.execute(stmt).scalars())
