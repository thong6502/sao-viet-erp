"""Phiếu đi muộn / về sớm / nghỉ nửa buổi — tầng DUY NHẤT chạm DB cho `late_early_requests`.
Không chứa luật nghiệp vụ (những thứ đó ở `LateEarlyService`). Chép khuôn `overtime_repo`."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from ..models.employee import Employee
from ..models.late_early import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    LateEarlyRequest,
)
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from .org_scope import dept_subtree_ids

_DECIDED = (STATUS_APPROVED, STATUS_REJECTED)
_LIVE = (STATUS_PENDING, STATUS_APPROVED)


class LateEarlyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- CRUD ---------------------------------------------------------------

    def create_request(self, **fields) -> LateEarlyRequest:
        r = LateEarlyRequest(**fields)
        self.db.add(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    def get_request(self, request_id: int) -> LateEarlyRequest | None:
        return self.db.get(LateEarlyRequest, request_id)

    def update_request(self, r: LateEarlyRequest, **fields) -> LateEarlyRequest:
        for key, value in fields.items():
            setattr(r, key, value)
        self.db.commit()
        self.db.refresh(r)
        return r

    def list_by_employee(self, employee_id: int, *, limit: int = 100) -> list[LateEarlyRequest]:
        return list(
            self.db.execute(
                select(LateEarlyRequest)
                .where(LateEarlyRequest.employee_id == employee_id)
                .order_by(LateEarlyRequest.work_date.desc(), LateEarlyRequest.id.desc())
                .limit(limit)
            ).scalars()
        )

    # --- scope-aware reads (own = phiếu của mình theo Employee.user_id; department =
    #     phiếu của phòng/tổ mình + cây con; all = tất cả). Bảng KHÔNG có cột user/phòng nên
    #     phải JOIN employees — giống hệt overtime_repo / leave_repo. --------------------

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

    def list_scoped(self, *, scope: str, actor, status: str | None = None,
                    limit: int = 200) -> list[LateEarlyRequest]:
        stmt = select(LateEarlyRequest).join(Employee, LateEarlyRequest.employee_id == Employee.id)
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        if status is not None:
            stmt = stmt.where(LateEarlyRequest.status == status)
        # CHỜ DUYỆT lên đầu — đó là việc phải làm. KHÔNG sort `status.asc()`: theo bảng chữ cái
        # nó ra approved → cancelled → pending → rejected, chôn việc cần làm vào GIỮA bảng.
        stmt = stmt.order_by(
            case((LateEarlyRequest.status == STATUS_PENDING, 0), else_=1),
            LateEarlyRequest.work_date.desc(), LateEarlyRequest.id.desc(),
        ).limit(limit)
        return list(self.db.execute(stmt).scalars())

    def count_pending_scoped(self, *, scope: str, actor) -> int:
        """Số phiếu ĐANG CHỜ DUYỆT trong scope người gọi — nuôi badge sidebar (COUNT ở DB)."""
        stmt = (
            select(func.count(LateEarlyRequest.id))
            .select_from(LateEarlyRequest)
            .join(Employee, LateEarlyRequest.employee_id == Employee.id)
            .where(LateEarlyRequest.status == STATUS_PENDING)
        )
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return int(self.db.execute(stmt).scalar_one())

    def count_my_unseen(self, employee_id: int) -> int:
        """Số phiếu của NV đã ĐƯỢC QUYẾT mà NV chưa xem — nuôi chuông Topbar."""
        stmt = select(func.count(LateEarlyRequest.id)).where(
            LateEarlyRequest.employee_id == employee_id,
            LateEarlyRequest.status.in_(_DECIDED),
            LateEarlyRequest.seen_by_employee_at.is_(None),
        )
        return int(self.db.execute(stmt).scalar_one())

    def mark_my_seen(self, employee_id: int) -> None:
        self.db.execute(
            update(LateEarlyRequest)
            .where(
                LateEarlyRequest.employee_id == employee_id,
                LateEarlyRequest.status.in_(_DECIDED),
                LateEarlyRequest.seen_by_employee_at.is_(None),
            )
            .values(seen_by_employee_at=datetime.now(timezone.utc))
        )
        self.db.commit()

    # --- nguồn cho Bảng công tháng + quỹ phép -------------------------------

    def approved_in_range(self, start: date, end: date) -> list[LateEarlyRequest]:
        """Phiếu ĐÃ DUYỆT có `work_date` trong [start, end] — Bảng công dùng để (a) MIỄN PHẠT
        đúng số phút đã xin, (b) hoàn công + trả lương phần vắng khi phiếu có trừ phép."""
        return list(
            self.db.execute(
                select(LateEarlyRequest).where(
                    LateEarlyRequest.status == STATUS_APPROVED,
                    LateEarlyRequest.work_date >= start,
                    LateEarlyRequest.work_date <= end,
                )
            ).scalars()
        )

    def count_pending_in_range(self, start: date, end: date) -> int:
        """Số phiếu CÒN CHỜ DUYỆT có `work_date` trong [start, end] — guard chốt công.

        Chốt công khi còn phiếu treo là mất tiền THẬT: snapshot đóng băng theo trạng thái lúc
        chốt, phiếu duyệt sau đó không vào được nữa ⇒ người lao động vẫn bị phạt đi trễ và mất
        chuyên cần dù đã xin phép đúng luật."""
        return self.db.execute(
            select(func.count()).select_from(LateEarlyRequest).where(
                LateEarlyRequest.status == STATUS_PENDING,
                LateEarlyRequest.work_date >= start,
                LateEarlyRequest.work_date <= end,
            )
        ).scalar_one()

    def live_for_day(self, employee_id: int, work_date: date, *,
                     exclude_id: int | None = None) -> list[LateEarlyRequest]:
        """Phiếu còn hiệu lực (chờ duyệt hoặc đã duyệt) của 1 NV trong 1 ngày công — nền cho luật
        'tối đa 1 phiếu/ngày'. `exclude_id` để đường SỬA không tự đếm chính phiếu đang sửa."""
        stmt = select(LateEarlyRequest).where(
            LateEarlyRequest.employee_id == employee_id,
            LateEarlyRequest.work_date == work_date,
            LateEarlyRequest.status.in_(_LIVE),
        )
        if exclude_id is not None:
            stmt = stmt.where(LateEarlyRequest.id != exclude_id)
        return list(self.db.execute(stmt).scalars())

    def leave_cong_used(self, employee_id: int, leave_type_id: int, year: int) -> float:
        """Σ ngày phép đã bị TRỪ bởi phiếu đi muộn/về sớm (approved + pending) trong năm dương lịch.

        Quỹ phép năm phải cộng cả kênh này, nếu không người ta xin nửa buổi có trừ phép thoải mái
        mà số dư phép không hề giảm."""
        stmt = select(func.coalesce(func.sum(LateEarlyRequest.leave_cong), 0)).where(
            LateEarlyRequest.employee_id == employee_id,
            LateEarlyRequest.leave_type_id == leave_type_id,
            LateEarlyRequest.status.in_(_LIVE),
            func.extract("year", LateEarlyRequest.work_date) == year,
        )
        return float(self.db.execute(stmt).scalar_one() or 0)
