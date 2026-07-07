"""Tính giá (Costing) business logic — spec-08-tinh-gia.

Framework-agnostic: raises domain errors the router maps to HTTP. Enforces the spec's
LÀM-NGAY rules (F1/F2):
  - qty_final required and > 0 (§A1; edge case: ≤0/trống → chặn);
  - ≥1 phương án giấy on create; each pieces_per_sheet > 0; grain_locked bool;
  - a costing header + its paper options + operations persist in ONE transaction;
  - every create/update/delete audits;
  - the **parallel geometry suggestion** for số con/khổ is a PURE calculation (usable area /
    piece area) — no seam needed; the xoay branch is dropped when grain_locked (§31a/§31 L782);
    pieces=0 / khổ quá nhỏ → suggestion 0, NEVER a divide-by-zero (edge case).

Cost numbers (giá vốn, số tờ, số pass, đơn giá) are DEFERRED to feat-040..042 behind
SEAM-07..12; this module never fabricates them. `ready` is only allowed when the inputs the
downstream engine needs are present — at P0 (SEAM-07/09/10 not built) the service keeps a
costing in `draft` unless the Planner explicitly forces `ready` on independent fields.
"""
from __future__ import annotations

import math

from ..models.costing import (
    COSTING_STATUSES,
    EXECUTION_MODES,
    STATUS_DRAFT,
    STATUS_READY,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.costing_repo import (
    CostingInput,
    CostingRepository,
    OperationInput,
    PaperOptionInput,
)
from ..services import costing_ports


class CostingError(Exception):
    """Base for costing domain errors."""


class CostingValidationError(CostingError):
    """A field failed validation (qty_final ≤ 0, pieces_per_sheet ≤ 0, bad enum…)."""


class CostingNotFound(CostingError):
    """No costing with that id."""


class CostingInUse(CostingError):
    """The costing is referenced by a consumer (Báo giá) and cannot be deleted.

    No consumer exists at P0 (bao_gia not built, no reverse FK yet), so this is not raised
    today — it is the named hook the delete guard will use once Báo giá references costings
    (spec-08 F8)."""


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def suggest_pieces_per_sheet(
    *,
    sheet_w: float,
    sheet_h: float,
    piece_w: float,
    piece_h: float,
    grain_locked: bool,
    gripper_cm: float = 0.0,
    edge_trim_cm: float = 0.0,
    bleed_cm: float = 0.0,
    gutter_cm: float = 0.0,
) -> int:
    """Pure geometry suggestion for số con/khổ (§31a). Fits the piece rectangle into the
    sheet in both orientations and returns the better count; when `grain_locked` the rotated
    (xoay) branch is dropped (§31 L782). Returns 0 (never divides by zero) when any dimension
    is ≤0 or the piece is larger than the sheet — the caller shows an explicit warning.

    #4 — trừ nhíp (gripper, 1 cạnh nạp) + xén mép (2 cạnh); cộng bleed (2 cạnh) + gutter giữa con
    (§31a). Bốn tham số mặc định 0 ⇒ trùng ⌊W/w⌋·⌊H/h⌋ cũ (mirror pricing_engine).

    This is a naive grid fit, NOT a nesting optimiser — good enough for a parallel hint next to
    the manually-entered value (which stays authoritative)."""
    if sheet_w <= 0 or sheet_h <= 0 or piece_w <= 0 or piece_h <= 0:
        return 0

    usable_w = sheet_w - gripper_cm - 2 * edge_trim_cm
    usable_h = sheet_h - 2 * edge_trim_cm
    pw = piece_w + 2 * bleed_cm + gutter_cm
    ph = piece_h + 2 * bleed_cm + gutter_cm
    if usable_w <= 0 or usable_h <= 0 or pw <= 0 or ph <= 0:
        return 0

    def grid(sw: float, sh: float, a: float, b: float) -> int:
        cols = math.floor(sw / a)
        rows = math.floor(sh / b)
        return max(0, cols) * max(0, rows)

    straight = grid(usable_w, usable_h, pw, ph)
    if grain_locked:
        return straight
    rotated = grid(usable_w, usable_h, ph, pw)
    return max(straight, rotated)


class CostingService:
    def __init__(
        self,
        costings: CostingRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.costings = costings
        self.audit = audit

    # --- validation helpers -------------------------------------------------

    @staticmethod
    def _validate_qty_final(qty_final) -> int:
        if not isinstance(qty_final, int) or isinstance(qty_final, bool):
            raise CostingValidationError("Số lượng cần giao phải là số nguyên.")
        if qty_final <= 0:
            raise CostingValidationError("Số lượng cần giao phải lớn hơn 0.")
        return qty_final

    @staticmethod
    def _validate_status(status: str | None) -> str:
        s = (status or STATUS_DRAFT).strip() or STATUS_DRAFT
        if s not in COSTING_STATUSES:
            raise CostingValidationError("Trạng thái không hợp lệ.")
        return s

    def _validate_paper_options(
        self, raw_options: list[dict]
    ) -> list[PaperOptionInput]:
        if not raw_options:
            raise CostingValidationError(
                "Cần ít nhất 1 phương án giấy."
            )
        out: list[PaperOptionInput] = []
        for idx, o in enumerate(raw_options, start=1):
            pieces = o.get("pieces_per_sheet")
            if not isinstance(pieces, int) or isinstance(pieces, bool):
                raise CostingValidationError(
                    f"Phương án giấy {idx}: số con/khổ phải là số nguyên."
                )
            if pieces <= 0:
                raise CostingValidationError(
                    f"Phương án giấy {idx}: số con/khổ phải lớn hơn 0."
                )
            sheet_w = self._num(o.get("sheet_w"), idx, "khổ tờ rộng", non_negative=True)
            sheet_h = self._num(o.get("sheet_h"), idx, "khổ tờ cao", non_negative=True)

            paper_id = o.get("sheet_paper_master_id")
            if paper_id is not None and (not isinstance(paper_id, int) or isinstance(paper_id, bool)):
                raise CostingValidationError(
                    f"Phương án giấy {idx}: giấy không hợp lệ."
                )

            def _opt_int(key: str, label: str):
                v = o.get(key)
                if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
                    raise CostingValidationError(f"Phương án giấy {idx}: {label} không hợp lệ.")
                return v

            out.append(
                PaperOptionInput(
                    sheet_paper_master_id=paper_id,
                    sheet_w=sheet_w,
                    sheet_h=sheet_h,
                    pieces_per_sheet=pieces,
                    grain_locked=bool(o.get("grain_locked", False)),
                    selected=bool(o.get("selected", False)),
                )
            )
        return out

    def _validate_operations(self, raw_ops: list[dict]) -> list[OperationInput]:
        out: list[OperationInput] = []
        for idx, o in enumerate(raw_ops, start=1):
            name = _clean(o.get("name"))
            if not name:
                raise CostingValidationError(
                    f"Công đoạn {idx}: tên công đoạn là bắt buộc."
                )
            mode = (o.get("execution_mode") or "").strip()
            if mode not in EXECUTION_MODES:
                raise CostingValidationError(
                    f"Công đoạn {idx}: hình thức thực hiện không hợp lệ."
                )
            sequence = o.get("sequence")
            sequence = idx - 1 if not isinstance(sequence, int) or isinstance(sequence, bool) else sequence
            out.append(
                OperationInput(name=name, execution_mode=mode, sequence=sequence)
            )
        return out

    @staticmethod
    def _num(value, idx: int, label: str, *, non_negative: bool = False) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise CostingValidationError(
                f"Phương án giấy {idx}: {label} phải là số."
            ) from None
        if non_negative and v < 0:
            raise CostingValidationError(
                f"Phương án giấy {idx}: {label} không được âm."
            )
        return v

    # --- product read (SEAM-11) --------------------------------------------

    def read_product(self, product_id: int) -> dict:
        """Read a product + cấu phần for Khối A/B via the SEAM-11 port, which RAISES
        NotImplementedError until Sản phẩm exposes ProductRead — the router turns that into
        an explicit "Sản phẩm chưa sẵn sàng" state (never fabricated specs)."""
        # SEAM-11: chờ san_pham (ProductRead)
        return costing_ports.get_product_for_costing(product_id)

    # --- reads --------------------------------------------------------------

    def list_costings(
        self,
        *,
        q: str | None = None,
        product_id: int | None = None,
        status: str | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ):
        return self.costings.list(
            q=q, product_id=product_id, status=status, sort=sort, page=page, size=size
        )

    def get_costing(self, costing_id: int):
        costing = self.costings.get_by_id(costing_id)
        if costing is None:
            raise CostingNotFound("Không tìm thấy phương án tính giá.")
        return costing

    # --- writes -------------------------------------------------------------

    def create_costing(
        self,
        *,
        product_id: int | None,
        qty_final: int,
        note: str | None,
        status: str | None,
        paper_options: list[dict],
        operations: list[dict],
        actor,
    ):
        qty_final = self._validate_qty_final(qty_final)
        status = self._validate_status(status)
        papers = self._validate_paper_options(paper_options)
        ops = self._validate_operations(operations or [])
        if product_id is not None and (not isinstance(product_id, int) or isinstance(product_id, bool)):
            raise CostingValidationError("Sản phẩm không hợp lệ.")

        data = CostingInput(
            product_id=product_id,
            qty_final=qty_final,
            status=status,
            note=_clean(note),
            paper_options=papers,
            operations=ops,
        )
        costing = self.costings.create(data)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_costing",
            target=f"costing:{costing.id}",
            detail=f"{costing.code} (SP={product_id}, SL={qty_final}, {len(papers)} phương án giấy)",
        )
        return costing

    def update_costing(
        self,
        *,
        costing_id: int,
        product_id: int | None,
        qty_final: int,
        note: str | None,
        status: str | None,
        paper_options: list[dict],
        operations: list[dict],
        actor,
    ):
        costing = self.get_costing(costing_id)
        qty_final = self._validate_qty_final(qty_final)
        status = self._validate_status(status)
        papers = self._validate_paper_options(paper_options)
        ops = self._validate_operations(operations or [])
        if product_id is not None and (not isinstance(product_id, int) or isinstance(product_id, bool)):
            raise CostingValidationError("Sản phẩm không hợp lệ.")

        data = CostingInput(
            product_id=product_id,
            qty_final=qty_final,
            status=status,
            note=_clean(note),
            paper_options=papers,
            operations=ops,
        )
        costing = self.costings.update(costing, data)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_costing",
            target=f"costing:{costing.id}",
            detail=f"{costing.code} (SP={product_id}, SL={qty_final}, {len(papers)} phương án giấy)",
        )
        return costing

    def delete_costing(self, *, costing_id: int, actor) -> None:
        costing = self.get_costing(costing_id)
        # SEAM (Báo giá chưa build): no reverse FK exists yet, so there is nothing to block
        # on. Once bao_gia references a costing, check that here → CostingInUse (spec-08 F8).
        code = costing.code
        self.costings.delete(costing)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_costing",
            target=f"costing:{costing_id}",
            detail=code,
        )
