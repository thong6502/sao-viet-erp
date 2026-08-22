"""Service — Yêu cầu kho: vòng đời, duyệt, và mức tồn (spec-kho-de-nghi §3–§4, §7–§8).

Ba luật nghiệp vụ sống ở đây (router chỉ điều phối):

1. **Kho không duyệt.** Duyệt là việc bộ phận yêu cầu; kho chỉ tiếp nhận yêu cầu đã duyệt.
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
    REQ_XUAT,
    REQUEST_EDITABLE,
    REQUEST_KINDS,
    StockRequest,
)
from ..realtime import hub
from ..repositories.notification_repo import NotificationRepository
from ..repositories.rbac_repo import DepartmentRepository, RoleRepository
from ..repositories.user_repo import UserRepository


class StockRequestError(Exception):
    """Lỗi nghiệp vụ yêu cầu kho — router dịch thành HTTP 400/403."""


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
    """Mức này có đáng đẩy nhắc cho người có quyền yêu cầu không (spec §8)."""
    return level in STOCK_ALERT_LEVELS


class StockRequestService:
    def __init__(self, requests, lots, thresholds, sequence, audit=None, hang=None) -> None:
        self.requests = requests
        self.lots = lots
        self.thresholds = thresholds
        self.sequence = sequence
        self.audit = audit
        # `VatLieuKhoService` — cửa duy nhất tra danh mục gốc + quy đổi đơn vị. Không có nó thì
        # không siết được (mặt hàng lạ, đơn vị không đổi được vẫn lọt), nên router LUÔN truyền.
        self.hang = hang

    # --- Tạo / sửa ---------------------------------------------------------

    def create(self, *, user, loai: str, lines: list[dict], ma: str | None = None,
               **header) -> StockRequest:
        if loai not in REQUEST_KINDS:
            raise StockRequestError("Loại yêu cầu không hợp lệ (chỉ NHAP hoặc XUAT).")
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
                raise StockRequestError(f"Số yêu cầu '{ma_clean}' đã tồn tại.")
        else:
            ma_clean = self.sequence.generate_flat_code(doc_type)
        req = self.requests.create(
            ma=ma_clean, loai=loai, nguoi_tao_id=user.id, lines=lines, **header
        )
        # BỎ BƯỚC DUYỆT (chủ 06/08/2026): tạo yêu cầu là DUYỆT LUÔN — bộ phận xin là kho cấp ngay,
        # không còn "Chờ duyệt". `approved` cũng là trạng thái KHOÁ (BRD §1.5) nên yêu cầu vừa tạo
        # đã chốt, đúng ý "tạo xong khoá luôn". KHÔNG tái dùng self.approve(): nó chặn tự-duyệt
        # (approver == người tạo) và đòi trạng thái pending — ở đây người tạo CHÍNH là người duyệt,
        # nên set thẳng cho đúng ngữ nghĩa. Mỗi dòng duyệt nguyên số đã xin (sl_duyet = sl_de_nghi).
        for line in req.lines:
            line.sl_duyet = line.sl_de_nghi
        req.trang_thai = REQ_APPROVED
        req.nguoi_duyet_id = user.id
        req.duyet_luc = datetime.now(timezone.utc)
        req = self.requests.save(req)
        # Đẩy real-time để Hộp yêu cầu kho thấy yêu cầu mới ngay (badge nhảy), không bắt F5.
        self._notify(req, "Yêu cầu mới — chờ kho cấp", targeted=False)
        self._notif_kho_moi(req)  # lưu vào chuông thủ kho
        return req

    def create_dieu_chuyen(self, *, user, loai: str, kho_id: int, lines: list[dict],
                           dieu_chuyen: bool = True, kho_nguon_id: int | None = None,
                           xuat_voucher_id: int | None = None, ghi_chu: str | None = None,
                           doc_type: str | None = None, notify: bool = False) -> StockRequest:
        """Tạo yêu cầu cho ĐIỀU CHUYỂN KHO (mô hình 2 yêu cầu — spec-dieu-chuyen-kho §4).

        Nhận NHIỀU dòng (điều chuyển hàng loạt gộp vào 1 yêu cầu). Dùng cho CẢ HAI vế: vế XUẤT ở kho
        nguồn (nội bộ, `notify=False`) và vế NHẬP ở kho đích (yêu cầu điều chuyển thấy được,
        `notify=True`). Tạo là DUYỆT LUÔN (giống `create`): `sl_duyet = sl_de_nghi`, trạng thái
        `approved` để lập phiếu được ngay. `_validate_lines` vẫn chạy (mặt hàng có thật + đơn vị
        quy được về gốc + không trùng mặt hàng)."""
        if loai not in REQUEST_KINDS:
            raise StockRequestError("Loại yêu cầu không hợp lệ (chỉ NHAP hoặc XUAT).")
        self._validate_lines(lines)
        # Vế NHẬP đích (đầu mối "Phiếu điều chuyển") lấy số DC… — caller truyền `doc_type`. Vế XUẤT
        # nguồn (ẩn) giữ mã đề nghị xuất mặc định.
        doc_type = doc_type or (
            SEQ_DOC_TYPE_STOCK_REQUEST_IN if loai == REQ_NHAP
            else SEQ_DOC_TYPE_STOCK_REQUEST_OUT
        )
        req = self.requests.create(
            ma=self.sequence.generate_flat_code(doc_type), loai=loai,
            nguoi_tao_id=user.id, lines=lines,
            bo_phan_id=user.department_id, kho_id=kho_id, ghi_chu=ghi_chu,
            dieu_chuyen=dieu_chuyen, kho_nguon_id=kho_nguon_id, xuat_voucher_id=xuat_voucher_id,
        )
        for ln in req.lines:
            ln.sl_duyet = ln.sl_de_nghi
        req.trang_thai = REQ_APPROVED
        req.nguoi_duyet_id = user.id
        req.duyet_luc = datetime.now(timezone.utc)
        req = self.requests.save(req)
        # Vế NHẬP đích = yêu cầu điều chuyển THẤY ĐƯỢC → báo kho như yêu cầu mới. Vế XUẤT nguồn là
        # bút toán nội bộ (tự lập + ghi sổ ngay) → im lặng, khỏi spam "yêu cầu xuất mới chờ cấp".
        if notify:
            self._notify(req, "Yêu cầu điều chuyển mới — chờ nhập kho", targeted=False)
            self._notif_kho_moi(req)
        return req

    def update(self, req: StockRequest, *, lines: list[dict] | None = None, **header) -> StockRequest:
        self._require_editable(req)
        if lines is not None:
            # Mặt hàng vốn đã có trên đề nghị thì giữ lại được kể cả khi danh mục đã ngừng nó.
            dang_co = {(ln.hang_loai, int(ln.hang_id))
                       for ln in (req.lines or []) if ln.hang_loai and ln.hang_id}
            self._validate_lines(lines, dang_co)
            self.requests.replace_lines(req, lines)
        self.requests.update_header(req, header)
        return self.requests.save(req)

    def _validate_lines(self, lines: list[dict], dang_co: set[tuple] | None = None) -> None:
        """SIẾT (chủ chốt 2026-08-08): mỗi dòng phải trỏ một mặt hàng CÓ THẬT trong danh mục gốc,
        và đơn vị phải đổi được về đơn vị gốc của chính mặt hàng đó.

        Không còn đường "gõ tên hàng mới rồi kho gắn mã sau" — đó là nguồn đẻ mã trùng/tên lệch,
        đúng thứ làm kho và mua hàng không nối được với nhau.
        """
        if not lines:
            raise StockRequestError("Yêu cầu phải có ít nhất 1 dòng vật tư.")
        seen: set = set()
        for ln in lines:
            if float(ln.get("sl_de_nghi") or 0) <= 0:
                raise StockRequestError("Số lượng đề nghị phải lớn hơn 0.")
            loai, hid = ln.get("hang_loai"), ln.get("hang_id")
            if not loai or not hid:
                raise StockRequestError(
                    "Mỗi dòng phải chọn một mặt hàng trong danh mục Giấy / Vật tư khác."
                )
            # Khoá trùng gồm CẢ lệnh/bài (mg 0175): cùng một loại giấy xin cho HAI lệnh khác nhau
            # là hai dòng hợp lệ — gộp lại thì mất luôn thông tin "phần nào cho lệnh nào", mà đó
            # đúng là thứ bảng cân đối cần để trừ đã-cấp vào đúng chỗ.
            key = (loai, int(hid), ln.get("lsx_id"), ln.get("bai_ghep_id"))
            if key in seen:
                raise StockRequestError(
                    "Một mặt hàng cho cùng một lệnh chỉ được xuất hiện 1 dòng — gộp số lượng lại."
                )
            seen.add(key)
            self._kiem_hang_va_don_vi(loai, int(hid), ln.get("dvt"), ln["sl_de_nghi"],
                                      giu_duoc=(loai, int(hid)) in (dang_co or set()))
            self._kiem_lenh(ln.get("lsx_id"), ln.get("bai_ghep_id"))

    def _kiem_lenh(self, lsx_id, bai_ghep_id) -> None:
        """Lệnh / bài ghép được gắn phải CÓ THẬT (mg 0175).

        Cả hai để trống là hợp lệ — xin lặt vặt không thuộc lệnh nào. Nhưng gắn một id KHÔNG tồn
        tại thì phải báo lỗi, tuyệt đối không im lặng bỏ: dòng đó sẽ mãi không khớp lệnh nào trong
        bảng cân đối, và triệu chứng duy nhất là "sao lệnh này cấp rồi mà vẫn báo thiếu".
        """
        co_lsx, co_bg = self.requests.lenh_ton_tai(lsx_id, bai_ghep_id)
        if not co_lsx:
            raise StockRequestError(f"Lệnh sản xuất #{lsx_id} không tồn tại — chọn lại.")
        if not co_bg:
            raise StockRequestError(f"Bài ghép #{bai_ghep_id} không tồn tại — chọn lại.")

    def _kiem_hang_va_don_vi(self, hang_loai: str, hang_id: int, dvt, so_luong,
                             *, giu_duoc: bool = False) -> None:
        """Mặt hàng còn dùng được + đơn vị quy được về gốc. Lỗi trả nguyên văn lý do của danh mục
        (vd "chưa chọn đơn vị tính", "không đổi được từ tờ về kg") để người khai biết sửa ở đâu.

        `giu_duoc` = dòng này vốn đã có trên đề nghị. Mặt hàng ngừng dùng sau khi đề nghị được lập
        thì vẫn phải sửa được đề nghị (đổi số lượng, bỏ bớt dòng khác) — chặn cứng là nhốt luôn
        cái đề nghị đó, không ai gỡ ra được.
        """
        if self.hang is None:
            raise StockRequestError("Thiếu danh mục mặt hàng — không kiểm được dòng đề nghị.")
        from .vat_lieu_kho_service import VatLieuKhoError

        try:
            obj = self.hang.get(hang_loai, hang_id)
            if not getattr(obj, "active", True) and not giu_duoc:
                raise StockRequestError(f"“{obj.ten}” đã ngừng dùng — chọn mặt hàng khác.")
            self.hang.quy_ve_goc(hang_loai, hang_id, dvt, so_luong)
        except VatLieuKhoError as e:
            raise StockRequestError(str(e)) from None

    def _require_editable(self, req: StockRequest) -> None:
        if req.trang_thai not in REQUEST_EDITABLE:
            raise StockRequestError(
                "Yêu cầu đã duyệt không sửa được. Hãy hủy và tạo yêu cầu mới."
            )

    # --- Vòng đời ----------------------------------------------------------

    def submit(self, req: StockRequest) -> StockRequest:
        if req.trang_thai != REQ_DRAFT:
            raise StockRequestError("Chỉ yêu cầu ở trạng thái Nháp mới trình duyệt được.")
        req.trang_thai = REQ_PENDING
        req = self.requests.save(req)
        self._notify(req, "Yêu cầu chờ duyệt")
        return req

    def approve(self, req: StockRequest, *, approver, approved_qty: dict[int, float] | None = None) -> StockRequest:
        """Duyệt yêu cầu. `approved_qty` map line_id → SL duyệt; thiếu thì duyệt nguyên SL yêu cầu.

        Người duyệt được cắt bớt số lượng (duyệt 8 khi yêu cầu 10) nhưng KHÔNG được duyệt
        nhiều hơn yêu cầu — muốn thêm thì bộ phận phải yêu cầu lại, để dấu vết luôn khớp
        với cái đã xin.
        """
        if req.trang_thai != REQ_PENDING:
            raise StockRequestError("Chỉ yêu cầu đang Chờ duyệt mới duyệt được.")
        if approver.id == req.nguoi_tao_id:
            raise StockRequestError("Không thể tự duyệt yêu cầu của chính mình.")

        for line in req.lines:
            qty = float(line.sl_de_nghi)
            if approved_qty and line.id in approved_qty:
                qty = float(approved_qty[line.id])
            if qty < 0:
                raise StockRequestError("Số lượng duyệt không được âm.")
            if qty > float(line.sl_de_nghi):
                raise StockRequestError(
                    "Không duyệt vượt số lượng yêu cầu — bộ phận phải yêu cầu lại."
                )
            line.sl_duyet = qty

        if all(float(ln.sl_duyet) == 0 for ln in req.lines):
            raise StockRequestError("Duyệt 0 cho tất cả các dòng — hãy Từ chối thay vì duyệt.")

        req.trang_thai = REQ_APPROVED
        req.nguoi_duyet_id = approver.id
        req.duyet_luc = datetime.now(timezone.utc)
        req = self.requests.save(req)
        self._notify(req, "Yêu cầu đã được duyệt")
        return req

    def reject(self, req: StockRequest, *, approver, ly_do: str) -> StockRequest:
        if req.trang_thai != REQ_PENDING:
            raise StockRequestError("Chỉ yêu cầu đang Chờ duyệt mới từ chối được.")
        if not (ly_do or "").strip():
            raise StockRequestError("Phải nhập lý do từ chối.")
        req.trang_thai = REQ_REJECTED
        req.nguoi_duyet_id = approver.id
        req.duyet_luc = datetime.now(timezone.utc)
        req.ly_do_tu_choi = ly_do.strip()
        req = self.requests.save(req)
        self._notify(req, "Yêu cầu bị từ chối")
        self._notif_nguoi_tao(req, loai="kho_huy", tieu_de="Yêu cầu bị từ chối")
        return req

    def cancel(self, req: StockRequest) -> StockRequest:
        if req.trang_thai not in REQUEST_EDITABLE:
            raise StockRequestError("Chỉ hủy được yêu cầu khi còn Nháp hoặc Chờ duyệt.")
        req.trang_thai = REQ_CANCELLED
        return self.requests.save(req)

    def mark_received(self, req: StockRequest) -> StockRequest:
        """Kho bấm 'Tiếp nhận' — chỉ đổi trạng thái, chưa đụng tồn."""
        if req.trang_thai != REQ_APPROVED:
            raise StockRequestError("Chỉ tiếp nhận được yêu cầu đã duyệt.")
        req.trang_thai = REQ_RECEIVED
        req = self.requests.save(req)
        self._notify(req, "Kho đã tiếp nhận yêu cầu")
        return req

    def mark_preparing(self, req: StockRequest) -> StockRequest:
        if req.trang_thai not in (REQ_APPROVED, REQ_RECEIVED):
            raise StockRequestError("Yêu cầu không ở trạng thái chuẩn bị được.")
        req.trang_thai = REQ_PREPARING
        req = self.requests.save(req)
        self._notify(req, "Kho đang chuẩn bị hàng")
        return req

    def mark_in_progress(self, req: StockRequest) -> StockRequest:
        """LẬP PHIẾU (nháp) cho yêu cầu → rời 'Cần cấp' sang 'Đang cấp' (Đang chuẩn bị). Idempotent:
        chỉ đẩy khi còn approved/received; partial/done/preparing giữ nguyên. Gọi từ voucher.create."""
        # Vế XUẤT nguồn của điều chuyển: phiếu tự lập + ghi sổ ngay trong 1 nhịp → bỏ qua bước
        # 'đang chuẩn bị' và toast của nó (bút toán nội bộ, không phải việc kho phải theo dõi).
        if getattr(req, "dieu_chuyen", False) and req.loai == REQ_XUAT:
            return req
        if req.trang_thai in (REQ_APPROVED, REQ_RECEIVED):
            req.trang_thai = REQ_PREPARING
            req = self.requests.save(req)
            self._notify(req, "Kho đã lập phiếu — đang chuẩn bị")
        return req

    def cancel_by_kho(self, req: StockRequest, ly_do: str) -> StockRequest:
        """Kho HỦY yêu cầu (hủy phiếu nháp, HOẶC quyết định không lập phiếu) — yêu cầu KẾT THÚC ở
        'Đã hủy' kèm lý do (KHÔNG trả về 'Chờ cấp', không cấp lại). Số đã cấp bởi phiếu ĐÃ GHI SỔ
        trước đó (nếu có) vẫn nằm ở kho — phiếu ghi sổ không đảo; yêu cầu vẫn đóng."""
        if req.trang_thai in (REQ_DONE, REQ_CANCELLED):
            raise StockRequestError("Yêu cầu đã kết thúc — không hủy được.")
        req.trang_thai = REQ_CANCELLED
        req.ly_do_huy = ly_do
        req = self.requests.save(req)  # save() tự cập nhật updated_at = mốc phản hồi cho badge người tạo
        self._notify(req, "Yêu cầu đã bị hủy")
        self._notif_nguoi_tao(req, loai="kho_huy", tieu_de="Yêu cầu đã bị hủy")
        return req

    def revert_if_untouched(self, req: StockRequest) -> StockRequest:
        """Hủy phiếu nháp cuối cùng (không còn phiếu active) mà CHƯA ứng gì → về 'Cần cấp'
        (approved) để cấp lại. Đã ứng một phần thì giữ partial. Gọi từ voucher.cancel."""
        any_issued = any(float(ln.sl_da_ung) > 0 for ln in req.lines)
        if not any_issued and req.trang_thai in (REQ_RECEIVED, REQ_PREPARING):
            req.trang_thai = REQ_APPROVED
            req = self.requests.save(req)
            self._notify(req, "Phiếu đã hủy — yêu cầu chờ cấp lại")
        return req

    # --- Tồn & đèn tín hiệu -------------------------------------------------

    def levels_for(self, hangs: list[tuple[str, int]], kho_id: int) -> dict[tuple[str, int], str]:
        """Mức tồn (đèn) của từng mã hàng — an toàn để trả cho MỌI vai, kể cả người
        không có `can_view_stock`, vì không kèm con số nào."""
        return self.levels_and_on_hand(hangs, kho_id)[0]

    def levels_and_on_hand(
        self, hangs: list[tuple[str, int]], kho_id: int
    ) -> tuple[dict[tuple[str, int], str], dict[tuple[str, int], float]]:
        """Trả CẢ mức tồn lẫn tồn khả dụng trong MỘT lượt (2 query) — router cần cả hai, tránh
        gọi `on_hand_map` hai lần. Khoá là cặp `(hang_loai, hang_id)`."""
        hangs = [tuple(h) for h in hangs]
        on_hand = self.lots.on_hand_map(hangs, kho_id)
        th = self.thresholds.map_for(hangs, kho_id)
        levels = {h: stock_level(on_hand.get(h, 0.0), th.get(h)) for h in hangs}
        return levels, on_hand

    def goi_y_kho_xuat(self, req) -> int | None:
        """Gợi ý "Kho (xuất từ)" khi lập phiếu XUẤT: chọn kho có NHIỀU hàng nhất theo THỨ TỰ
        dòng của yêu cầu — kho nào tồn mặt hàng ĐẦU tiên nhiều nhất thì chọn; hoà thì xét mặt
        hàng thứ 2, thứ 3… (so sánh từ điển). Không kho nào còn lô của các mặt hàng này → None
        (giữ nguyên kho đang chọn, không ép bừa). Chỉ đọc — không đụng tồn."""
        hangs = [(l.hang_loai, int(l.hang_id)) for l in (req.lines or [])
                 if l.hang_loai and l.hang_id]
        if not hangs:
            return None
        by_kho = self.lots.on_hand_by_kho(hangs)
        kho_ids = {k for per in by_kho.values() for k in per}
        if not kho_ids:
            return None

        def vector(kho_id: int) -> tuple[float, ...]:
            return tuple(by_kho.get(h, {}).get(kho_id, 0.0) for h in hangs)

        # Vector tồn theo đúng thứ tự dòng: lớn hơn (so từ điển) = ưu tiên. Hoà tất cả → kho_id
        # nhỏ nhất cho ổn định (−k để max chọn số nhỏ). Toàn 0 ⇒ coi như không gợi ý được.
        best = max(kho_ids, key=lambda k: (vector(k), -k))
        if not any(v > 0 for v in vector(best)):
            return None
        return best

    def suggest_quantity(self, hang: tuple[str, int], department_id: int | None) -> float | None:
        """Gợi ý số lượng = trung bình 3 lần đề nghị gần nhất cùng mặt hàng + cùng bộ phận.

        Chưa có bảng định mức nên đây là nguồn rule-based duy nhất lấy được từ data sẵn có
        (spec §8). Chưa đủ lịch sử thì trả None — thà không gợi ý còn hơn gợi ý bừa.
        """
        rows, _ = self.requests.list(bo_phan_id=department_id, size=200)
        qtys = [
            float(ln.sl_de_nghi)
            for r in rows for ln in r.lines
            if (ln.hang_loai, ln.hang_id) == tuple(hang)
        ][:3]
        if not qtys:
            return None
        return round(sum(qtys) / len(qtys), 2)

    # --- Đẩy realtime -------------------------------------------------------

    def _notify(self, req: StockRequest, message: str, *, targeted: bool = True) -> None:
        """Đẩy real-time (badge nhảy + toast ngay). Kèm `loai` để FE toast đúng chiều nhập/xuất.

        `targeted=False` (dùng lúc TẠO): CHỈ broadcast — mọi người có quyền kho nhận ĐÚNG 1 toast
        "có việc mới"; người tạo (cũng là kho) không nhận thêm toast đích danh → tránh 2 toast trùng.
        `targeted=True` (duyệt/từ chối/hủy/cấp…): thêm tin ĐÍCH DANH cho người tạo + người duyệt.
        Các bước này KHÔNG làm tăng số 'chờ cấp' nên broadcast không toast lại → vẫn 1 toast."""
        if targeted:
            event = {
                "type": "stock_request",
                "request_id": req.id,
                "ma": req.ma,
                "trang_thai": req.trang_thai,
                "loai": req.loai,
                "message": message,
            }
            for uid in {req.nguoi_tao_id, req.nguoi_duyet_id}:
                if uid:
                    hub.publish(uid, event)
        # Tín hiệu 'danh sách chờ đổi' + chiều → FE refetch số đếm; toast "việc mới" khi số TĂNG.
        # ĐẨY THEO PHẠM VI (không broadcast toàn hệ): chỉ tới người XỬ LÝ kho mà PHÒNG của yêu
        # cầu nằm trong scope của họ (all → mọi phòng; department → khớp phòng; own → người tạo).
        # ⇒ "phòng nào thấy phòng đó"; kho trung tâm scope=all vẫn nhận mọi phòng.
        # Kèm TÊN người tạo + PHÒNG BAN để toast "việc mới" nói rõ đến từ ai (thủ kho biết ngay
        # nguồn yêu cầu, không phải mở màn dò).
        db = self.requests.db
        creator = UserRepository(db).get_by_id(req.nguoi_tao_id) if req.nguoi_tao_id else None
        dept = DepartmentRepository(db).get_by_id(req.bo_phan_id) if req.bo_phan_id else None
        signal = {
            "type": "stock_request_pending_changed",
            "code": req.ma, "loai": req.loai, "nguoi_tao_id": req.nguoi_tao_id,
            "nguoi_tao_ten": getattr(creator, "name", None),
            "bo_phan_ten": getattr(dept, "name", None),
        }
        for uid in RoleRepository(db).kho_notify_user_ids(
            bo_phan_id=req.bo_phan_id, creator_id=req.nguoi_tao_id,
        ):
            hub.publish(uid, signal)

    # --- Thông báo lưu vào chuông (trung tâm thông báo) — song song với toast SSE ---------------
    def _notif_kho_moi(self, req: StockRequest) -> None:
        """Lưu thông báo 'yêu cầu mới chờ cấp' cho THỦ KHO trong phạm vi (trừ người tạo) + đẩy SSE
        để badge chuông nhảy ngay. Bấm → mở Hộp yêu cầu tại đúng yêu cầu (link_loai='kho_inbox')."""
        db = self.requests.db
        creator = UserRepository(db).get_by_id(req.nguoi_tao_id) if req.nguoi_tao_id else None
        dept = DepartmentRepository(db).get_by_id(req.bo_phan_id) if req.bo_phan_id else None
        who = " · ".join(x for x in [getattr(creator, "name", None), getattr(dept, "name", None)] if x)
        dir_ = "xuất" if req.loai == REQ_XUAT else "nhập"
        uids = [
            u for u in RoleRepository(db).kho_notify_user_ids(
                bo_phan_id=req.bo_phan_id, creator_id=req.nguoi_tao_id,
            ) if u != req.nguoi_tao_id
        ]
        if not uids:
            return
        NotificationRepository(db).add_many(
            uids, loai="kho_moi",
            tieu_de=f"Yêu cầu {dir_} mới chờ cấp",
            noi_dung=f"{req.ma}{' — ' + who if who else ''}",
            link_loai="kho_inbox", link_id=req.id,
        )
        for uid in uids:
            hub.publish(uid, {"type": "notification_new"})

    def _notif_nguoi_tao(self, req: StockRequest, *, loai: str, tieu_de: str) -> None:
        """Lưu thông báo phản hồi kho cho NGƯỜI TẠO (hoàn tất/hủy/từ chối) + đẩy SSE. Bấm → mở màn
        Yêu cầu tại đúng yêu cầu (link_loai='kho_mine')."""
        if not req.nguoi_tao_id:
            return
        NotificationRepository(self.requests.db).add(
            user_id=req.nguoi_tao_id, loai=loai,
            tieu_de=tieu_de, noi_dung=req.ma,
            link_loai="kho_mine", link_id=req.id,
        )
        hub.publish(req.nguoi_tao_id, {"type": "notification_new"})

    def notify_low_stock(self, *, user_ids: list[int], material_name: str,
                         level: str, suggest: float | None) -> None:
        """Đẩy thẻ nhắc 'vật tư cần bổ sung' cho người có quyền yêu cầu (spec §8).

        Cố tình KHÔNG kèm số tồn — người yêu cầu chỉ cần biết "cần bổ sung" và "nên xin bao
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
        # Vế XUẤT nguồn của điều chuyển: chốt trạng thái (Hoàn tất) nhưng KHÔNG đẩy toast/chuông —
        # người ấn điều chuyển không cần thông báo "yêu cầu xuất đã hoàn tất" cho bút toán nội bộ.
        if getattr(req, "dieu_chuyen", False) and req.loai == REQ_XUAT:
            return req
        self._notify(req, "Hoàn tất yêu cầu" if done else "Kho đã cấp một phần")
        if done:  # chỉ báo chuông khi ĐỦ (hoàn tất); cấp một phần chưa phải kết quả cuối
            self._notif_nguoi_tao(req, loai="kho_hoan_tat", tieu_de="Yêu cầu đã hoàn tất")
        return req
