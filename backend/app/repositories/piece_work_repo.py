"""Thưởng/phạt tổ trưởng data access (module `luong`).

⚠️ CRUD bảng `piece_rates` KHÔNG còn ở đây — từ 17/08/2026 bảng đó là danh mục "Công việc khoán"
và đi qua `repositories/cong_viec_khoan_repo.CongViecKhoanRepository` (nền `CatalogRepo`). File này
chỉ còn hai bảng mốc thưởng/phạt tổ trưởng.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.piece_work import (
    PieceLeaderBonusBracket,
    PieceLeaderBonusSetting,
)


class PieceWorkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Bậc thưởng/phạt tổ trưởng theo tỷ lệ hàng lỗi (chủ 29/07/2026) ------

    def list_leader_brackets(self, department_id: int) -> list[PieceLeaderBonusBracket]:
        return list(self.db.execute(
            select(PieceLeaderBonusBracket)
            .where(PieceLeaderBonusBracket.department_id == department_id)
            .order_by(PieceLeaderBonusBracket.seq)
        ).scalars())

    def replace_leader_brackets(self, department_id: int, rows: list[dict]) -> None:
        """Thay CẢ BỘ mốc của một tổ trong MỘT transaction.

        Xoá-ghi-lại thay vì sửa từng dòng: bảng mốc là một khối logic (phải tăng dần, đúng một
        bậc ∞ ở cuối) — sửa lẻ từng dòng thì giữa chừng bảng ở trạng thái không hợp lệ.
        ⚠️ CHỈ đụng đúng `department_id` này; tổ khác không được suy suyển."""
        self.db.execute(
            delete(PieceLeaderBonusBracket).where(
                PieceLeaderBonusBracket.department_id == department_id
            )
        )
        for r in rows:
            self.db.add(PieceLeaderBonusBracket(department_id=department_id, **r))
        self.db.commit()

    # --- Ngưỡng tối thiểu để xét thưởng/phạt (chủ 30/07/2026) ----------------

    def get_leader_settings(self, department_id: int) -> PieceLeaderBonusSetting | None:
        """`None` = tổ chưa khai ngưỡng ⇒ không gác. Khác hẳn ngưỡng = 0 về mặt ý định, nhưng cùng
        hành vi, nên tầng service quy cả hai về 0."""
        return self.db.execute(
            select(PieceLeaderBonusSetting).where(
                PieceLeaderBonusSetting.department_id == department_id
            )
        ).scalars().first()

    def upsert_leader_settings(self, department_id: int, *,
                               min_output_qty: float) -> PieceLeaderBonusSetting:
        """Mỗi tổ đúng MỘT dòng (`department_id` UNIQUE) — có thì sửa, chưa có thì tạo."""
        s = self.get_leader_settings(department_id)
        if s is None:
            s = PieceLeaderBonusSetting(department_id=department_id,
                                        min_output_qty=min_output_qty)
            self.db.add(s)
        else:
            s.min_output_qty = min_output_qty
        self.db.commit()
        self.db.refresh(s)
        return s

    def commit(self) -> None:
        self.db.commit()
