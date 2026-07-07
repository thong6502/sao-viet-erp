"""Lương khoán (module `luong`, nhịp 2) — nghiệp vụ.

Sổ khoán 1 tổ/kỳ:
  quỹ = Σ(khối lượng × đơn giá)                         [entries nhập tay]
  base = max(quỹ, bù_lỗ)                                [bù lỗ = min đảm bảo]
  thưởng = max(0, quỹ − mốc_vượt) × %thưởng_vượt        [thưởng vượt năng suất]
  tổng = base + thưởng
  tổ_trưởng = tổng × %tổ_trưởng                          [lấy trước]
  pool = tổng − tổ_trưởng  →  chia theo hệ số (weight) từng thành viên
Tiền khoán mỗi NV/kỳ → PieceWorkService.khoan_map → cột `khoan` của payroll_lines.
"""
from __future__ import annotations


class PieceWorkError(Exception):
    pass


class PieceWorkValidationError(PieceWorkError):
    pass


class PieceWorkNotFound(PieceWorkError):
    pass


def _r(x) -> float:
    return float(round(float(x or 0)))


class PieceWorkService:
    def __init__(self, piece, employees) -> None:
        self.piece = piece
        self.employees = employees

    # --- đơn giá khoán ------------------------------------------------------

    def list_rates(self):
        return self.piece.list_rates()

    def create_rate(self, **f):
        if not f.get("group_name"):
            raise PieceWorkValidationError("Thiếu tổ khoán.")
        if not f.get("name"):
            raise PieceWorkValidationError("Thiếu tên công việc.")
        if f.get("unit_price") is None:
            raise PieceWorkValidationError("Thiếu đơn giá.")
        return self.piece.create_rate(**f)

    def update_rate(self, rate_id, **f):
        r = self.piece.get_rate(rate_id)
        if r is None:
            raise PieceWorkNotFound("Không tìm thấy đơn giá.")
        return self.piece.update_rate(r, **{k: v for k, v in f.items() if v is not None})

    def delete_rate(self, rate_id):
        r = self.piece.get_rate(rate_id)
        if r is None:
            raise PieceWorkNotFound("Không tìm thấy đơn giá.")
        self.piece.delete_rate(r)

    # --- sổ khoán (batch) ---------------------------------------------------

    def get_or_create_batch(self, *, year, month, group_name):
        if not group_name:
            raise PieceWorkValidationError("Thiếu tổ khoán.")
        b = self.piece.get_batch_by_ymg(year, month, group_name)
        if b is None:
            b = self.piece.create_batch(year=year, month=month, group_name=group_name)
        return b

    def update_batch(self, batch_id, **f):
        b = self.piece.get_batch(batch_id)
        if b is None:
            raise PieceWorkNotFound("Không tìm thấy sổ khoán.")
        b = self.piece.update_batch(b, **{k: v for k, v in f.items() if v is not None})
        self._recompute(b)
        return b

    def list_batches(self, year, month):
        return self.piece.list_batches(year, month)

    # --- dòng sản lượng -----------------------------------------------------

    def add_entry(self, *, batch_id, piece_rate_id=None, work_name=None, unit=None,
                  unit_price=None, quantity=0, note=None):
        b = self.piece.get_batch(batch_id)
        if b is None:
            raise PieceWorkNotFound("Không tìm thấy sổ khoán.")
        # Lấy snapshot từ đơn giá nếu chọn rate.
        if piece_rate_id:
            rate = self.piece.get_rate(piece_rate_id)
            if rate is None:
                raise PieceWorkNotFound("Không tìm thấy đơn giá.")
            work_name = work_name or rate.name
            unit = unit or rate.unit
            unit_price = unit_price if unit_price is not None else float(rate.unit_price)
        if not work_name or unit_price is None:
            raise PieceWorkValidationError("Cần tên công việc + đơn giá (hoặc chọn từ danh mục).")
        amount = _r(float(unit_price) * float(quantity or 0))
        e = self.piece.create_entry(
            batch_id=batch_id, piece_rate_id=piece_rate_id, work_name=work_name, unit=unit or "khac",
            unit_price=unit_price, quantity=quantity or 0, amount=amount, note=note,
        )
        self._recompute(b)
        return e

    def update_entry(self, entry_id, *, quantity=None, unit_price=None, note=None):
        e = self.piece.get_entry(entry_id)
        if e is None:
            raise PieceWorkNotFound("Không tìm thấy dòng sản lượng.")
        if quantity is not None:
            e.quantity = quantity
        if unit_price is not None:
            e.unit_price = unit_price
        if note is not None:
            e.note = note
        e.amount = _r(float(e.unit_price) * float(e.quantity))
        self.piece.update_entry(e)
        b = self.piece.get_batch(e.batch_id)
        if b is not None:
            self._recompute(b)
        return e

    def delete_entry(self, entry_id):
        e = self.piece.get_entry(entry_id)
        if e is None:
            raise PieceWorkNotFound("Không tìm thấy dòng sản lượng.")
        batch_id = e.batch_id
        self.piece.delete_entry(e)
        b = self.piece.get_batch(batch_id)
        if b is not None:
            self._recompute(b)

    # --- chia về người ------------------------------------------------------

    def set_share(self, *, batch_id, employee_id, weight=1, note=None):
        b = self.piece.get_batch(batch_id)
        if b is None:
            raise PieceWorkNotFound("Không tìm thấy sổ khoán.")
        if self.employees.get_by_id(employee_id) is None:
            raise PieceWorkNotFound("Không tìm thấy nhân viên.")
        s = self.piece.get_share_by_be(batch_id, employee_id)
        if s is None:
            s = self.piece.create_share(batch_id=batch_id, employee_id=employee_id, weight=weight or 1, note=note)
        else:
            s = self.piece.update_share(s, weight=weight or 1, note=note)
        self._recompute(b)
        return s

    def delete_share(self, share_id):
        s = self.piece.get_share(share_id)
        if s is None:
            raise PieceWorkNotFound("Không tìm thấy phần chia.")
        batch_id = s.batch_id
        self.piece.delete_share(s)
        b = self.piece.get_batch(batch_id)
        if b is not None:
            self._recompute(b)

    # --- engine chia quỹ ----------------------------------------------------

    def _distribute(self, batch, entries, shares) -> tuple[dict[int, float], dict]:
        """Trả ({share_id → tiền}, {revenue,total,leader_cut,pool})."""
        revenue = sum(float(e.amount) for e in entries)
        base = max(revenue, float(batch.min_guarantee))
        over_t = float(batch.over_target)
        bonus = max(0.0, revenue - over_t) * float(batch.over_bonus_pct) if over_t > 0 else 0.0
        total = base + bonus
        leader_cut = total * float(batch.leader_pct) if batch.leader_employee_id else 0.0
        pool = total - leader_cut
        sum_w = sum(float(s.weight) for s in shares)
        out: dict[int, float] = {}
        for s in shares:
            amt = pool * (float(s.weight) / sum_w) if sum_w else 0.0
            if batch.leader_employee_id and s.employee_id == batch.leader_employee_id:
                amt += leader_cut
            out[s.id] = _r(amt)
        meta = {"revenue": _r(revenue), "total": _r(total), "leader_cut": _r(leader_cut), "pool": _r(pool)}
        return out, meta

    def _recompute(self, batch) -> None:
        entries = self.piece.list_entries(batch.id)
        shares = self.piece.list_shares(batch.id)
        amounts, _ = self._distribute(batch, entries, shares)
        for s in shares:
            s.amount = amounts.get(s.id, 0.0)
        self.piece.commit()

    def get_sheet(self, *, year, month, group_name) -> dict:
        b = self.piece.get_batch_by_ymg(year, month, group_name)
        if b is None:
            return {"batch": None, "entries": [], "shares": [], "meta": None}
        entries = self.piece.list_entries(b.id)
        shares = self.piece.list_shares(b.id)
        _, meta = self._distribute(b, entries, shares)
        return {"batch": b, "entries": entries, "shares": shares, "meta": meta}

    def khoan_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → tổng tiền khoán} cộng qua mọi sổ khoán của kỳ — cho payroll engine."""
        out: dict[int, float] = {}
        for b in self.piece.list_batches(year, month):
            entries = self.piece.list_entries(b.id)
            shares = self.piece.list_shares(b.id)
            amounts, _ = self._distribute(b, entries, shares)
            for s in shares:
                out[s.employee_id] = out.get(s.employee_id, 0.0) + amounts.get(s.id, 0.0)
        return out
