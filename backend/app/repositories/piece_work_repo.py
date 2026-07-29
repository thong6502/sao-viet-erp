"""Đơn giá khoán data access — chỉ tầng này chạm DB cho bảng piece_rates."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.piece_work import PieceLeaderBonusBracket, PieceRate


class PieceWorkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- piece_rates --------------------------------------------------------

    def list_rates(self, *, active_only: bool = False,
                   department_id: int | None = None) -> list[PieceRate]:
        stmt = select(PieceRate)
        if active_only:
            stmt = stmt.where(PieceRate.is_active.is_(True))
        if department_id is not None:
            stmt = stmt.where(PieceRate.department_id == department_id)
        return list(self.db.execute(stmt.order_by(PieceRate.group_name, PieceRate.id)).scalars())

    def get_rate(self, rate_id: int) -> PieceRate | None:
        return self.db.get(PieceRate, rate_id)

    def distinct_units(self) -> list[str]:
        """Các đơn vị NHÀ MÁY ĐÃ THỰC SỰ DÙNG — nuôi gợi ý ở ô "Đơn vị" và bước gộp chính tả.

        Gợi ý mọc từ chính dữ liệu người dùng gõ, không phải từ danh sách cứng ai đó đoán trước:
        gõ "mét tới" một lần thì lần sau nó tự nằm trong danh sách."""
        rows = self.db.execute(
            select(PieceRate.unit).where(PieceRate.unit != "").distinct()
        ).scalars()
        return sorted({(u or "").strip() for u in rows if (u or "").strip()})

    def create_rate(self, **f) -> PieceRate:
        r = PieceRate(**f); self.db.add(r); self.db.commit(); self.db.refresh(r); return r

    def update_rate(self, r: PieceRate, **f) -> PieceRate:
        for k, v in f.items():
            setattr(r, k, v)
        self.db.commit(); self.db.refresh(r); return r

    def delete_rate(self, r: PieceRate) -> None:
        self.db.delete(r); self.db.commit()

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

    def commit(self) -> None:
        self.db.commit()
