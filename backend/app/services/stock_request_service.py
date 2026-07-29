"""Service — Đề nghị kho: vòng đời, duyệt, và mức tồn (spec-kho-de-nghi §3–§4, §7–§8).

Ba luật nghiệp vụ sống ở đây (router chỉ điều phối):

1. **Kho không duyệt.** Duyệt là việc bộ phận đề nghị; kho chỉ tiếp nhận đề nghị đã duyệt.
2. **Đã duyệt là khoá.** Từ `approved` trở đi không sửa được nữa (BRD §1.5).
3. **Đèn tín hiệu thay cho con số.** Người không có `can_view_stock` chỉ nhận 1 trong 5 mức
   (`STOCK_LEVELS`), không bao giờ nhận số tồn thật.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models.document_sequence import (
    SEQ_DOC_TYPE_STOCK_REQUEST_IN,
    SEQ_DOC_TYPE_STOCK_REQUEST_OUT,
)
from ..models.stock_lot import (
    STOCK_ALERT_LEVELS,
    STOCK_CRITICAL,
    STOCK_OK,
    STOCK_OUT,
    STOCK_OVER,
)
from ..models.stock_request import (
    PRIORITIES,
    PRIORITY_NORMAL,
    REQ_APPROVED,
    REQ_CANCELLED,
    REQ_DONE,
    REQ_DRAFT,
    REQ_NHAP,
    REQ_PARTIAL,
    REQ_PENDING,
    REQ_PREPARING,
    REQ_RECEIVED,
    REQ_REJECTED,
    REQUEST_EDITABLE,
    REQUEST_KINDS,
    StockRequest,
)
from ..realtime import hub


class StockRequestError(Exception):
    """Lỗi nghiệp vụ đề nghị kho — router dịch thành HTTP 400/403."""


def stock_level(on_hand: float, threshold) -> str:
    """Quy tồn khả dụng về 1 trong 5 mức (spec §7).

    `threshold` là StockThreshold hoặc None. Chưa khai ngưỡng thì chỉ phân biệt được
    "hết" với "còn" — không bịa cảnh báo cho vật tư chưa ai đặt ngưỡng.
    """
    if on_hand <= 0:
        return STOCK_OUT
    if threshold is None:
        return STOCK_OK
    nguong_ton = float(threshold.nguong_ton or 0)
    toi_da = threshold.nguong_toi_da
    # Bỏ mức "cận tồn" (2026-07-29): chỉ còn Cần mua (≤ ngưỡng tồn) · Dư (> tối đa) · Đủ (giữa).
    if on_hand <= nguong_ton:
        return STOCK_CRITICAL
    if toi_da is not None and on_hand > float(toi_da):
        return STOCK_OVER
    return STOCK_OK


def needs_alert(level: str) -> bool:
    """Mức này có đáng đẩy nhắc cho người có quyền đề nghị không (spec §8)."""
    return level in STOCK_ALERT_LEVELS


class StockRequestService:
    def __init__(self, requests, lots, thresholds, sequence, audit=None) -> None:
        self.requests = requests
        self.lots = lots
        self.thresholds = thresholds
        self.sequence = sequence
        self.audit = audit

    # --- Tạo / sửa ---------------------------------------------------------

    def create(self, *, user, loai: str, lines: list[dict], ma: str | None = None,
               **header) -> StockRequest:
        if loai not in REQUEST_KINDS:
            raise StockRequestError("Loại đề nghị không hợp lệ (chỉ NHAP hoặc XUAT).")
        self._validate_lines(lines)
        if header.get("uu_tien") and header["uu_tien"] not in PRIORITIES:
            raise StockRequestError("Mức ưu tiên không hợp lệ.")
        header.setdefault("uu_tien", PRIORITY_NORMAL)
        # Bộ phận mặc định = bộ phận người tạo, để scope `department` và ô "Bộ phận" trên
        # bản in luôn có dữ liệu mà không bắt người dùng chọn lại.
        header.setdefault("bo_phan_id", user.department_id)

        doc_type = (
            SEQ_DOC_TYPE_STOCK_REQUEST_IN if loai == REQ_NHAP
            else SEQ_DOC_TYPE_STOCK_REQUEST_OUT
        )
        # Số tự nhập (tuỳ chọn): chuẩn hoá HOA, chặn trùng. Bỏ trống → hệ thống tự sinh.
        ma_clean = (ma or "").strip().upper() or None
        if ma_clean is not None:
            if self.requests.get_by_ma(ma_clean) is not None:
                raise StockRequestError(f"Số đề nghị '{ma_clean}' đã tồn tại.")
        else:
            ma_clean = self.sequence.generate_flat_code(doc_type)
        return self.requests.create(
            ma=ma_clean, loai=loai, nguoi_tao_id=user.id, lines=lines, **header
        )

    def update(self, req: StockRequest, *, lines: list[dict] | None = None, **header) -> StockRequest:
        self._require_editable(req)
        if lines is not None:
            self._validate_lines(lines)
            self.requests.replace_lines(req, lines)
        self.requests.update_header(req, header)
        return self.requests.save(req)

    def _validate_lines(self, lines: list[dict]) -> None:
        if not lines:
            raise StockRequestError("Đề nghị phải có ít nhất 1 dòng vật tư.")
        seen: set = set()
        for ln in lines:
            if float(ln.get("sl_de_nghi") or 0) <= 0:
                raise StockRequestError("Số lượng đề nghị phải lớn hơn 0.")
            mid = ln.get("material_id")
            name = (ln.get("ten_tu_do") or "").strip().lower()
            if (mid is None) == (not name):
                raise StockRequestError(
                    "Mỗi dòng phải có ĐÚNG một: mã hàng có sẵn HOẶC tên hàng mới."
                )
            # Dedup: hàng đã có mã theo id, hàng mới theo tên (không trùng trong cùng đề nghị).
            key = ("id", mid) if mid is not None else ("ten", name)
            if key in seen:
                raise StockRequestError(
                    "Một mặt hàng chỉ được xuất hiện 1 dòng — gộp số lượng lại."
                )
            seen.add(key)

    def _require_editable(self, req: StockRequest) -> None:
        if req.trang_thai not in REQUEST_EDITABLE:
            raise StockRequestError(
                "Đề nghị đã duyệt không sửa được. Hãy hủy và tạo đề nghị mới."
            )

    # --- Vòng đời ----------------------------------------------------------

    def submit(self, req: StockRequest) -> StockRequest:
        if req.trang_thai != REQ_DRAFT:
            raise StockRequestError("Chỉ đề nghị ở trạng thái Nháp mới trình duyệt được.")
        req.trang_thai = REQ_PENDING
        req = self.requests.save(req)
        self._notify(req, "Đề nghị chờ duyệt")
        return req

    def approve(self, req: StockRequest, *, approver, approved_qty: dict[int, float] | None = None) -> StockRequest:
        """Duyệt đề nghị. `approved_qty` map line_id → SL duyệt; thiếu thì duyệt nguyên SL đề nghị.

        Người duyệt được cắt bớt số lượng (duyệt 8 khi đề nghị 10) nhưng KHÔNG được duyệt
        nhiều hơn đề nghị — muốn thêm thì bộ phận phải đề nghị lại, để dấu vết luôn khớp
        với cái đã xin.
        """
        if req.trang_thai != REQ_PENDING:
            raise StockRequestError("Chỉ đề nghị đang Chờ duyệt mới duyệt được.")
        if approver.id == req.nguoi_tao_id:
            raise StockRequestError("Không thể tự duyệt đề nghị của chính mình.")

        for line in req.lines:
            qty = float(line.sl_de_nghi)
            if approved_qty and line.id in approved_qty:
                qty = float(approved_qty[line.id])
            if qty < 0:
                raise StockRequestError("Số lượng duyệt không được âm.")
            if qty > float(line.sl_de_nghi):
                raise StockRequestError(
                    "Không duyệt vượt số lượng đề nghị — bộ phận phải đề nghị lại."
                )
            line.sl_duyet = qty

        if all(float(ln.sl_duyet) == 0 for ln in req.lines):
            raise StockRequestError("Duyệt 0 cho tất cả các dòng — hãy Từ chối thay vì duyệt.")

        req.trang_thai = REQ_APPROVED
        req.nguoi_duyet_id = approver.id
        req.duyet_luc = datetime.now(timezone.utc)
        req = self.requests.save(req)
        self._notify(req, "Đề nghị đã được duyệt")
        return req

    def reject(self, req: StockRequest, *, approver, ly_do: str) -> StockRequest:
        if req.trang_thai != REQ_PENDING:
            raise StockRequestError("Chỉ đề nghị đang Chờ duyệt mới từ chối được.")
        if not (ly_do or "").strip():
            raise StockRequestError("Phải nhập lý do từ chối.")
        req.trang_thai = REQ_REJECTED
        req.nguoi_duyet_id = approver.id
        req.duyet_luc = datetime.now(timezone.utc)
        req.ly_do_tu_choi = ly_do.strip()
        req = self.requests.save(req)
        self._notify(req, "Đề nghị bị từ chối")
        return req

    def cancel(self, req: StockRequest) -> StockRequest:
        if req.trang_thai not in REQUEST_EDITABLE:
            raise StockRequestError("Chỉ hủy được đề nghị khi còn Nháp hoặc Chờ duyệt.")
        req.trang_thai = REQ_CANCELLED
        return self.requests.save(req)

    def mark_received(self, req: StockRequest) -> StockRequest:
        """Kho bấm 'Tiếp nhận' — chỉ đổi trạng thái, chưa đụng tồn."""
        if req.trang_thai != REQ_APPROVED:
            raise StockRequestError("Chỉ tiếp nhận được đề nghị đã duyệt.")
        req.trang_thai = REQ_RECEIVED
        req = self.requests.save(req)
        self._notify(req, "Kho đã tiếp nhận đề nghị")
        return req

    def mark_preparing(self, req: StockRequest) -> StockRequest:
        if req.trang_thai not in (REQ_APPROVED, REQ_RECEIVED):
            raise StockRequestError("Đề nghị không ở trạng thái chuẩn bị được.")
        req.trang_thai = REQ_PREPARING
        req = self.requests.save(req)
        self._notify(req, "Kho đang chuẩn bị hàng")
        return req

    def mark_in_progress(self, req: StockRequest) -> StockRequest:
        """LẬP PHIẾU (nháp) cho đề nghị → rời 'Cần cấp' sang 'Đang cấp' (Đang chuẩn bị). Idempotent:
        chỉ đẩy khi còn approved/received; partial/done/preparing giữ nguyên. Gọi từ voucher.create."""
        if req.trang_thai in (REQ_APPROVED, REQ_RECEIVED):
            req.trang_thai = REQ_PREPARING
            req = self.requests.save(req)
            self._notify(req, "Kho đã lập phiếu — đang chuẩn bị")
        return req

    def revert_if_untouched(self, req: StockRequest) -> StockRequest:
        """Hủy phiếu nháp cuối cùng (không còn phiếu active) mà CHƯA ứng gì → về 'Cần cấp'
        (approved) để cấp lại. Đã ứng một phần thì giữ partial. Gọi từ voucher.cancel."""
        any_issued = any(float(ln.sl_da_ung) > 0 for ln in req.lines)
        if not any_issued and req.trang_thai in (REQ_RECEIVED, REQ_PREPARING):
            req.trang_thai = REQ_APPROVED
            req = self.requests.save(req)
            self._notify(req, "Phiếu đã hủy — đề nghị chờ cấp lại")
        return req

    # --- Tồn & đèn tín hiệu -------------------------------------------------

    def levels_for(self, material_ids: list[int], kho_id: int) -> dict[int, str]:
        """Mức tồn (đèn) của từng mã hàng — an toàn để trả cho MỌI vai, kể cả người
        không có `can_view_stock`, vì không kèm con số nào."""
        return self.levels_and_on_hand(material_ids, kho_id)[0]

    def levels_and_on_hand(
        self, material_ids: list[int], kho_id: int
    ) -> tuple[dict[int, str], dict[int, float]]:
        """Trả CẢ mức tồn lẫn tồn khả dụng trong MỘT lượt (2 query) — router cần cả hai, tránh
        gọi `on_hand_map` hai lần."""
        on_hand = self.lots.on_hand_map(material_ids, kho_id)
        th = self.thresholds.map_for(material_ids, kho_id)
        levels = {mid: stock_level(on_hand.get(mid, 0.0), th.get(mid)) for mid in material_ids}
        return levels, on_hand

    def suggest_quantity(self, material_id: int, department_id: int | None) -> float | None:
        """Gợi ý số lượng = trung bình 3 lần đề nghị gần nhất cùng mã hàng + cùng bộ phận.

        Chưa có bảng định mức nên đây là nguồn rule-based duy nhất lấy được từ data sẵn có
        (spec §8). Chưa đủ lịch sử thì trả None — thà không gợi ý còn hơn gợi ý bừa.
        """
        rows, _ = self.requests.list(bo_phan_id=department_id, size=200)
        qtys = [
            float(ln.sl_de_nghi)
            for r in rows for ln in r.lines
            if ln.material_id == material_id
        ][:3]
        if not qtys:
            return None
        return round(sum(qtys) / len(qtys), 2)

    # --- Đẩy realtime -------------------------------------------------------

    def _notify(self, req: StockRequest, message: str) -> None:
        """Đẩy cho người tạo + người duyệt. Nội bộ = REAL-TIME: badge nhảy + toast ngay,
        không bắt ai refresh (nguyên tắc sản phẩm trong CLAUDE.md)."""
        event = {
            "type": "stock_request",
            "request_id": req.id,
            "ma": req.ma,
            "trang_thai": req.trang_thai,
            "message": message,
        }
        for uid in {req.nguoi_tao_id, req.nguoi_duyet_id}:
            if uid:
                hub.publish(uid, event)
        # Người TẠO và người DUYỆT nhận toast có nội dung; còn tổ trưởng chưa duyệt lần nào
        # và thủ kho thì không nằm trong 2 id đó — họ cần badge "có việc mới" nhảy. Broadcast
        # là tín hiệu nhẹ (không kèm dữ liệu), FE nghe rồi tự refetch số đếm; cùng cách làm
        # với `quote_pending_changed` / `order_pending_changed`.
        hub.broadcast({"type": "stock_request_pending_changed", "code": req.ma})

    def notify_low_stock(self, *, user_ids: list[int], material_name: str,
                         level: str, suggest: float | None) -> None:
        """Đẩy thẻ nhắc 'vật tư cần bổ sung' cho người có quyền đề nghị (spec §8).

        Cố tình KHÔNG kèm số tồn — người đề nghị chỉ cần biết "cần bổ sung" và "nên xin bao
        nhiêu"; số tồn thật vẫn nằm trong kho.
        """
        if not needs_alert(level):
            return
        event = {
            "type": "stock_alert",
            "material": material_name,
            "level": level,
            "suggest": suggest,
            "message": f"Vật tư {material_name} cần bổ sung",
        }
        for uid in user_ids:
            hub.publish(uid, event)

    # --- Đồng bộ trạng thái theo tiến độ ứng phiếu ---------------------------

    def refresh_fulfillment(self, req: StockRequest) -> StockRequest:
        """Tính lại trạng thái sau khi 1 phiếu ghi sổ: ứng đủ hết → Hoàn tất, còn dở →
        Đã cấp một phần. Gọi từ `stock_voucher_service` sau khi cộng `sl_da_ung`."""
        if not req.lines:
            return req
        done = all(float(ln.sl_da_ung) >= float(ln.sl_duyet) for ln in req.lines)
        any_issued = any(float(ln.sl_da_ung) > 0 for ln in req.lines)
        if done:
            req.trang_thai = REQ_DONE
        elif any_issued:
            req.trang_thai = REQ_PARTIAL
        req = self.requests.save(req)
        self._notify(req, "Hoàn tất đề nghị" if done else "Kho đã cấp một phần")
        return req
