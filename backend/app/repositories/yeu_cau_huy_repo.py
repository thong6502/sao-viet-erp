"""Yêu cầu hủy đơn nghỉ / phiếu tăng ca đã duyệt — tầng DUY NHẤT chạm DB cho `yeu_cau_huy`.
Không chứa luật nghiệp vụ (ở `LeaveService` / `OvertimeService`)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.employee import Employee
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.yeu_cau_huy import TT_CHO, YeuCauHuy
from .org_scope import dept_subtree_ids


class YeuCauHuyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, **fields) -> YeuCauHuy:
        yc = YeuCauHuy(**fields)
        self.db.add(yc)
        self.db.commit()
        self.db.refresh(yc)
        return yc

    def get(self, yc_id: int) -> YeuCauHuy | None:
        return self.db.get(YeuCauHuy, yc_id)

    def update(self, yc: YeuCauHuy, **fields) -> YeuCauHuy:
        for key, value in fields.items():
            setattr(yc, key, value)
        self.db.commit()
        self.db.refresh(yc)
        return yc

    def get_cho(self, loai: str, request_id: int) -> YeuCauHuy | None:
        """Yêu cầu ĐANG CHỜ của một đơn (service giữ luật tối đa một yêu cầu chờ / đơn)."""
        return self.db.execute(
            select(YeuCauHuy).where(
                YeuCauHuy.loai == loai,
                YeuCauHuy.request_id == request_id,
                YeuCauHuy.trang_thai == TT_CHO,
            ).order_by(YeuCauHuy.id.desc()).limit(1)
        ).scalar_one_or_none()

    def moi_nhat_theo_don(self, loai: str, request_ids) -> dict[int, YeuCauHuy]:
        """Yêu cầu MỚI NHẤT của từng đơn trong `request_ids` — nuôi nhãn "Đang xin hủy" / kết quả
        trên các bảng đơn. Một câu truy vấn cho cả trang, không N+1."""
        ids = {int(i) for i in request_ids or []}
        if not ids:
            return {}
        rows = self.db.execute(
            select(YeuCauHuy)
            .where(YeuCauHuy.loai == loai, YeuCauHuy.request_id.in_(ids))
            .order_by(YeuCauHuy.id.asc())
        ).scalars()
        out: dict[int, YeuCauHuy] = {}
        for yc in rows:
            out[yc.request_id] = yc     # tăng dần theo id ⇒ dòng cuối cùng thắng
        return out

    # --- theo phạm vi người duyệt (JOIN employees — cùng luật với leave_repo/overtime_repo) ---

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

    def list_cho_scoped(self, loai: str, *, scope: str, actor) -> list[YeuCauHuy]:
        """Yêu cầu hủy ĐANG CHỜ trong phạm vi người duyệt — cũ nhất trước (xin trước xử trước)."""
        stmt = (
            select(YeuCauHuy)
            .join(Employee, YeuCauHuy.employee_id == Employee.id)
            .where(YeuCauHuy.loai == loai, YeuCauHuy.trang_thai == TT_CHO)
        )
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return list(self.db.execute(stmt.order_by(YeuCauHuy.id.asc())).scalars())

    def count_cho_scoped(self, loai: str, *, scope: str, actor) -> int:
        """Số yêu cầu hủy đang chờ trong phạm vi — cộng vào badge "chờ duyệt"."""
        stmt = (
            select(func.count(YeuCauHuy.id))
            .select_from(YeuCauHuy)
            .join(Employee, YeuCauHuy.employee_id == Employee.id)
            .where(YeuCauHuy.loai == loai, YeuCauHuy.trang_thai == TT_CHO)
        )
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return int(self.db.execute(stmt).scalar_one())
