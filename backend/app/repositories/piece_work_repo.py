"""Thưởng/phạt tổ trưởng data access (module `luong`).

⚠️ CRUD bảng `piece_rates` KHÔNG còn ở đây — từ 17/08/2026 bảng đó là danh mục "Công việc khoán"
và đi qua `repositories/cong_viec_khoan_repo.CongViecKhoanRepository` (nền `CatalogRepo`). File này
chỉ còn bảng bậc thưởng/phạt tổ trưởng.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.piece_work import PieceLeaderBonusBracket


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

    # ⚠️ `get_leader_settings` / `upsert_leader_settings` GỠ 04/09/2026 cùng bảng
    # `piece_leader_bonus_settings` (mg `0262`): khoảng sản lượng nay nằm ngay trên từng dòng bậc
    # (`sl_tu`/`sl_den`), không cần một cửa chặn riêng ở bảng thứ hai.

    def commit(self) -> None:
        self.db.commit()
