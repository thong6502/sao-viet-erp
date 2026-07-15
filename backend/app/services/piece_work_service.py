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

from datetime import datetime, timezone

from ..models.payroll import PERIOD_DRAFT
from ..models.piece_work import BATCH_DRAFT, BATCH_LOCKED


class PieceWorkError(Exception):
    pass


class PieceWorkValidationError(PieceWorkError):
    pass


class PieceWorkNotFound(PieceWorkError):
    pass


def _r(x) -> float:
    return float(round(float(x or 0)))


class PieceWorkService:
    def __init__(self, piece, employees, payroll=None, audit=None, outputs=None) -> None:
        self.piece = piece
        self.employees = employees
        self.payroll = payroll   # PayrollRepository (chỉ đọc) — đồng bộ khóa kỳ. None → bỏ guard (seed/test).
        self.audit = audit       # AuditLogRepository — ghi nhật ký chốt/mở sổ. None → bỏ qua.
        self.outputs = outputs   # ProductionOutputRepository — nguồn phiếu SL theo tổ (Pha 5b). None → bỏ.

    # --- nhật ký + khóa -----------------------------------------------------

    def _audit(self, actor, action: str, target: str, detail: str) -> None:
        if self.audit is not None:
            self.audit.create(actor_user_id=getattr(actor, "id", None), action=action,
                              target=target, detail=detail)

    def _assert_editable(self, batch) -> None:
        """Cấm sửa sổ khi ĐÃ CHỐT hoặc kỳ lương tháng đó đã khóa (đồng bộ chốt lương)."""
        if batch.status == BATCH_LOCKED:
            raise PieceWorkValidationError("Sổ khoán đã chốt — mở lại sổ trước khi sửa.")
        if self.payroll is not None:
            period = self.payroll.get_period_by_ym(batch.year, batch.month)
            if period is not None and period.status != PERIOD_DRAFT:
                raise PieceWorkValidationError(
                    f"Kỳ lương {int(batch.month)}/{int(batch.year)} đã chốt — "
                    "mở lại kỳ lương trước khi sửa sổ khoán.")

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
        self._assert_editable(b)
        b = self.piece.update_batch(b, **{k: v for k, v in f.items() if v is not None})
        self._recompute(b)
        return b

    def list_batches(self, year, month):
        return self.piece.list_batches(year, month)

    # --- chốt / mở lại sổ ---------------------------------------------------

    def sync_outputs(self, batch) -> None:
        """Materialize phiếu SL theo tổ của (kỳ, tổ) thành dòng `source=phieu` trong sổ (chỉ khi
        sổ còn nháp). Xóa dòng phiếu cũ rồi tạo lại từ production_outputs `tinh_khoan=true` — dòng
        gõ tay (source=manual) giữ nguyên. Đây là điểm 'ghi nhận sản lượng' → 'vào quỹ' tách bạch."""
        if self.outputs is None or batch is None or batch.status == BATCH_LOCKED:
            return
        if not batch.group_name:
            return
        for e in self.piece.list_entries(batch.id):
            if getattr(e, "source", "manual") == "phieu":
                self.piece.delete_entry(e)
        for o in self.outputs.list_by_month_group(batch.year, batch.month, batch.group_name):
            if not o.tinh_khoan:
                continue
            # net-of-trừ-lỗi (5b-2): quỹ tổ giảm phần trừ lỗi; sàn 0 áp ở _distribute (revenue≥0).
            amount = _r(float(o.unit_price) * float(o.quantity) - float(getattr(o, "defect_deduction", 0) or 0))
            self.piece.create_entry(
                batch_id=batch.id, piece_rate_id=o.piece_rate_id, work_name=o.work_name,
                unit=o.unit, unit_price=o.unit_price, quantity=o.quantity, amount=amount,
                note=o.note, source="phieu", production_output_id=o.id,
            )
        self._recompute(batch)

    def lock_sheet(self, batch_id, *, actor=None):
        """Chốt sổ khoán → chảy vào bảng lương. Chặn nếu sổ không hợp lệ (thiếu tổ trưởng/hệ số)."""
        b = self.piece.get_batch(batch_id)
        if b is None:
            raise PieceWorkNotFound("Không tìm thấy sổ khoán.")
        if b.status == BATCH_LOCKED:
            return b
        self.sync_outputs(b)   # materialize phiếu SL vào sổ trước khi chốt (đóng băng số)
        _, meta = self._distribute(b, self.piece.list_entries(b.id), self.piece.list_shares(b.id))
        if not meta["valid"]:
            raise PieceWorkValidationError(
                "Sổ chưa hợp lệ để chốt: " + (
                    "chưa có ai trong danh sách chia." if meta["no_shares"]
                    else "chưa nhập hệ số chia." if meta["zero_weight"]
                    else "tổ trưởng chưa có trong danh sách chia."))
        b = self.piece.update_batch(b, status=BATCH_LOCKED, locked_at=datetime.now(timezone.utc),
                                    locked_by=getattr(actor, "id", None))
        self._audit(actor, "piece_lock", f"piece_batch:{b.id}", f"{b.group_name} {int(b.month)}/{int(b.year)}")
        return b

    def reopen_sheet(self, batch_id, *, actor=None):
        """Mở lại sổ đã chốt — chỉ khi kỳ lương tháng đó chưa chốt."""
        b = self.piece.get_batch(batch_id)
        if b is None:
            raise PieceWorkNotFound("Không tìm thấy sổ khoán.")
        if b.status != BATCH_LOCKED:
            return b
        if self.payroll is not None:
            period = self.payroll.get_period_by_ym(b.year, b.month)
            if period is not None and period.status != PERIOD_DRAFT:
                raise PieceWorkValidationError(
                    f"Kỳ lương {int(b.month)}/{int(b.year)} đã chốt — mở lại kỳ lương trước.")
        b = self.piece.update_batch(b, status=BATCH_DRAFT, locked_at=None, locked_by=None)
        self._audit(actor, "piece_reopen", f"piece_batch:{b.id}", f"{b.group_name} {int(b.month)}/{int(b.year)}")
        return b

    # --- dòng sản lượng -----------------------------------------------------

    def add_entry(self, *, batch_id, piece_rate_id=None, work_name=None, unit=None,
                  unit_price=None, quantity=0, note=None):
        b = self.piece.get_batch(batch_id)
        if b is None:
            raise PieceWorkNotFound("Không tìm thấy sổ khoán.")
        self._assert_editable(b)
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
        b0 = self.piece.get_batch(e.batch_id)
        if b0 is not None:
            self._assert_editable(b0)
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
        b0 = self.piece.get_batch(batch_id)
        if b0 is not None:
            self._assert_editable(b0)
        self.piece.delete_entry(e)
        b = self.piece.get_batch(batch_id)
        if b is not None:
            self._recompute(b)

    # --- chia về người ------------------------------------------------------

    def set_share(self, *, batch_id, employee_id, weight=1, note=None):
        b = self.piece.get_batch(batch_id)
        if b is None:
            raise PieceWorkNotFound("Không tìm thấy sổ khoán.")
        self._assert_editable(b)
        if self.employees.get_by_id(employee_id) is None:
            raise PieceWorkNotFound("Không tìm thấy nhân viên.")
        # GIỮ hệ số 0 (tổ trưởng chỉ ăn %); chỉ None mới về mặc định 1.
        w = 1 if weight is None else weight
        s = self.piece.get_share_by_be(batch_id, employee_id)
        if s is None:
            s = self.piece.create_share(batch_id=batch_id, employee_id=employee_id, weight=w, note=note)
        else:
            s = self.piece.update_share(s, weight=w, note=note)
        self._recompute(b)
        return s

    def delete_share(self, share_id):
        s = self.piece.get_share(share_id)
        if s is None:
            raise PieceWorkNotFound("Không tìm thấy phần chia.")
        batch_id = s.batch_id
        b0 = self.piece.get_batch(batch_id)
        if b0 is not None:
            self._assert_editable(b0)
        self.piece.delete_share(s)
        b = self.piece.get_batch(batch_id)
        if b is not None:
            self._recompute(b)

    # --- engine chia quỹ ----------------------------------------------------

    def _distribute(self, batch, entries, shares) -> tuple[dict[int, float], dict]:
        """Trả ({share_id → tiền}, meta). Bảo toàn tiền: Σ tiền chia == total (khi sổ hợp lệ).

        meta gồm revenue/total/leader_cut/pool + cờ chặn valid/no_shares/zero_weight/leader_no_share
        (sổ không hợp lệ → KHÔNG chảy vào bảng lương, buộc HCNS sửa — quyết định Q2=A).
        """
        # SÀN 0 (5b-2): dòng phiếu có thể net-of-trừ-lỗi âm; kẹp quỹ ≥ 0 → mọi khoản chia đều ≥ 0
        # (không đẩy lương âm — Điều 102 BLLĐ). Bù lỗ vẫn là mức sàn dưới.
        revenue = max(0.0, sum(float(e.amount) for e in entries))
        base = max(revenue, float(batch.min_guarantee))
        over_t = float(batch.over_target)
        bonus = max(0.0, revenue - over_t) * float(batch.over_bonus_pct) if over_t > 0 else 0.0
        total = base + bonus
        has_leader = bool(batch.leader_employee_id)
        # % tổ trưởng tính trên QUỸ THỰC + THƯỞNG, KHÔNG trên phần bù lỗ (Q3=A). Phần bù lỗ
        # (base − revenue) nằm nguyên trong pool → chia hết cho thợ theo hệ số.
        leader_cut = (revenue + bonus) * float(batch.leader_pct) if has_leader else 0.0
        pool = total - leader_cut
        sum_w = sum(float(s.weight) for s in shares)
        leader_share = next((s for s in shares if s.employee_id == batch.leader_employee_id), None) \
            if has_leader else None

        # Cờ chặn (Q2=A): chỉ áp khi CÓ quỹ cần chia (total>0). Sổ tổ thuần theo-người (không quỹ)
        # → total=0 → hợp lệ, chốt được, tiền theo-người cộng riêng ở khoan_map.
        need_split = total > 0
        no_shares = need_split and len(shares) == 0
        zero_weight = need_split and len(shares) > 0 and sum_w == 0
        leader_no_share = need_split and has_leader and leader_share is None
        valid = not (no_shares or zero_weight or leader_no_share)

        out: dict[int, float] = {}
        for s in shares:
            amt = pool * (float(s.weight) / sum_w) if sum_w else 0.0
            if leader_share is not None and s.id == leader_share.id:
                amt += leader_cut
            out[s.id] = _r(amt)
        # Đồng lẻ làm tròn: dồn phần dư vào tổ trưởng (hoặc người hệ số lớn nhất) để Σ == total.
        if valid and out:
            target = leader_share or max(shares, key=lambda s: float(s.weight))
            out[target.id] = _r(out[target.id] + (_r(total) - sum(out.values())))
        meta = {
            "revenue": _r(revenue), "total": _r(total), "leader_cut": _r(leader_cut), "pool": _r(pool),
            "valid": valid, "no_shares": no_shares, "zero_weight": zero_weight,
            "leader_no_share": leader_no_share,
        }
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
        """{employee_id → tổng tiền khoán} — CHỈ cộng sổ ĐÃ CHỐT và HỢP LỆ (Q1 + Q2=A).

        Sổ chưa chốt hoặc còn lỗi (thiếu tổ trưởng/hệ số) KHÔNG chảy vào lương → chống nhập
        khống + chống tiền bốc hơi âm thầm.
        """
        out: dict[int, float] = {}
        for b in self.piece.list_batches(year, month):
            if b.status != BATCH_LOCKED:
                continue
            entries = self.piece.list_entries(b.id)
            shares = self.piece.list_shares(b.id)
            amounts, meta = self._distribute(b, entries, shares)
            if meta["valid"]:
                for s in shares:
                    out[s.employee_id] = out.get(s.employee_id, 0.0) + amounts.get(s.id, 0.0)
            # Nguồn-2 (5b-2): tiền khoán THEO NGƯỜI của tổ này — cộng thẳng, KHÔNG qua quỹ/hệ số
            # (nếu nhồi vào entries sẽ bị chia lại cho cả tổ). Gate bởi cùng khóa sổ tổ (b locked).
            if self.outputs is not None and b.group_name:
                for o in self.outputs.list_nguoi_by_month_group(year, month, b.group_name):
                    if not o.tinh_khoan or not o.employee_id:
                        continue
                    amt = max(0.0, float(o.unit_price) * float(o.quantity) - float(o.defect_deduction or 0))
                    out[o.employee_id] = out.get(o.employee_id, 0.0) + _r(amt)
        return out

    def defect_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → tổng TRỪ LỖI khoán theo NGƯỜI} của các sổ ĐÃ CHỐT — để Lương gộp vào
        trần khấu trừ 30% (Điều 102). Cùng gate sổ tổ đã chốt + phiếu tính khoán như khoan_map."""
        out: dict[int, float] = {}
        if self.outputs is None:
            return out
        for b in self.piece.list_batches(year, month):
            if b.status != BATCH_LOCKED or not b.group_name:
                continue
            for o in self.outputs.list_nguoi_by_month_group(year, month, b.group_name):
                if not o.tinh_khoan or not o.employee_id:
                    continue
                out[o.employee_id] = out.get(o.employee_id, 0.0) + _r(float(o.defect_deduction or 0))
        return out

    def pending_batches(self, year: int, month: int) -> list[dict]:
        """Sổ khoán tháng có TIỀN nhưng chưa vào lương được (chưa chốt / còn lỗi) — cảnh báo mềm."""
        res: list[dict] = []
        for b in self.piece.list_batches(year, month):
            entries = self.piece.list_entries(b.id)
            _, meta = self._distribute(b, entries, self.piece.list_shares(b.id))
            if meta["total"] <= 0:
                continue
            if b.status != BATCH_LOCKED:
                res.append({"group_name": b.group_name, "reason": "chua_chot"})
            elif not meta["valid"]:
                res.append({"group_name": b.group_name, "reason": "loi_chia"})
        return res
