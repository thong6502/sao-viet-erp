"""Service — Phiếu nhập/xuất kho: ứng theo yêu cầu, phân bổ lô, ghi sổ, giá vốn.

docs/spec-kho-de-nghi.md §5–§6. Bốn luật cứng sống ở đây:

1. **Không có yêu cầu đã duyệt thì không lập được phiếu** (§5).
2. **Không cho ứng vượt `sl_duyet`** — muốn thêm phải yêu cầu mới (BRD §2.5 b8).
3. **Nhập = tạo lô mới, mỗi lần nhập một lô riêng với giá riêng** (§6). Không gộp lô.
4. **Xuất phải chỉ định lô**; ăn nhiều lô thì tách nhiều dòng, mỗi dòng một giá vốn.

Chỉ khi phiếu chuyển sang `posted` thì tồn mới đổi — phiếu nháp không đụng gì tới kho.
"""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

from ..models.document_sequence import (
    SEQ_DOC_TYPE_STOCK_VOUCHER_IN,
    SEQ_DOC_TYPE_STOCK_VOUCHER_OUT,
)
from ..models.stock_request import REQUEST_FULFILLABLE
from ..models.stock_voucher import (
    VOUCHER_CANCELLED,
    VOUCHER_DRAFT,
    VOUCHER_KINDS,
    VOUCHER_NHAP,
    VOUCHER_POSTED,
    VOUCHER_XUAT,
    StockVoucher,
    StockVoucherAttachment,
)

from ..repositories.kho_khoa_so_repo import KhoKhoaSoRepository
from ..storage import get_storage, key_from_url, url_from_key

# Đính kèm phiếu kho: byte đi qua storage.py (LocalStorage <backend>/static hoặc MinIO) rồi phục vụ
# qua /api/files/<key> (đăng nhập mới đọc) — KHÔNG dùng mount /static (đã gỡ vì lộ file). key = "kho/<id>/..".
_ATTACHMENT_SUBDIR = "kho"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_VOUCHER = 20


def _safe_attachment_name(file_name: str | None) -> str:
    """Chặn traversal (kể cả Windows "\\") + thay ký tự cấm; cắt 180 ký tự."""
    name = Path((file_name or "file").replace("\\", "/")).name
    return re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)[:180].strip(" .") or "file"


class StockVoucherError(Exception):
    """Lỗi nghiệp vụ phiếu kho — router dịch thành HTTP 400."""


class StockVoucherService:
    def __init__(self, vouchers, requests, lots, sequence, request_service, hang,
                 giu_cho=None) -> None:
        self.vouchers = vouchers
        self.requests = requests
        self.lots = lots
        self.sequence = sequence
        self.request_service = request_service
        # `GiuChoService` — TUỲ CHỌN (17/08/2026). Vắng thì kho chạy y như trước: mọi chỗ dựng
        # service cũ không phải sửa, và test kho không phải kéo theo cả bảng cân đối.
        #
        # Có mặt thì kho gánh thêm hai việc:
        #   · XUẤT — không cho lấn vào phần lệnh khác đang giữ (`kiem_xuat`);
        #   · GHI SỔ — xuất xong thì nhả phần giữ tương ứng, nhập xong thì tự nhặt thêm cho lệnh
        #     đang chờ (`tieu_thu` / `nhat_them`).
        self.giu_cho = giu_cho
        # `VatLieuKhoService` — tra danh mục gốc + quy đổi đơn vị.
        #
        # GỠ 2026-08-08: `materials` + `material_service` + `_create_new_material()`. Phiếu từng tự
        # đẻ mặt hàng mới (mã HH###) khi dòng đề nghị là hàng gõ tay. Nay siết: mọi thứ nhập kho
        # phải có sẵn trong danh mục Giấy / Vật tư khác, nên cửa đẻ hàng đó đóng hẳn.
        self.hang = hang

    def _assert_period_open(self, kho_id, ngay) -> None:
        """Chặn GHI SỔ vào KỲ ĐÃ KHÓA (kế toán chốt sổ, spec-bao-cao-kho §6). Mốc = NGÀY HẠCH TOÁN
        = ngày ghi sổ (= hôm nay khi post); khóa xét theo KHOẢNG đã khóa (toàn kho hoặc kho này)."""
        if kho_id is None or ngay is None:
            return
        if KhoKhoaSoRepository(self.vouchers.db).is_locked(kho_id, ngay):
            raise StockVoucherError(
                f"Kỳ kế toán chứa ngày {ngay.strftime('%d/%m/%Y')} đã khóa sổ — "
                f"không thao tác được phiếu này."
            )

    def _quy_doi(self, rl, qty: float) -> dict:
        """Số trên phiếu (theo `dvt` của dòng đề nghị) → số theo ĐƠN VỊ GỐC để ghi vào lô."""
        from .vat_lieu_kho_service import VatLieuKhoError

        try:
            return self.hang.quy_ve_goc(rl.hang_loai, rl.hang_id, rl.dvt, qty)
        except VatLieuKhoError as e:
            raise StockVoucherError(str(e)) from None

    # --- Lập phiếu ----------------------------------------------------------

    def create(self, *, user, request_id: int, kho_id: int, lines: list[dict],
               ngay: date | None = None, ma: str | None = None, **header) -> StockVoucher:
        req = self.requests.get_with_lines(request_id)
        if req is None:
            raise StockVoucherError("Không tìm thấy yêu cầu.")
        # Luật 1: mọi phiếu phải ứng theo một yêu cầu ĐÃ DUYỆT.
        if req.trang_thai not in REQUEST_FULFILLABLE:
            raise StockVoucherError(
                "Chỉ lập phiếu cho yêu cầu đã duyệt (và chưa hoàn tất)."
            )
        if not lines:
            raise StockVoucherError("Phiếu phải có ít nhất 1 dòng.")
        # Lập phiếu NHÁP chưa vào sổ → không xét khóa kỳ ở đây (chỉ xét lúc GHI SỔ).

        loai = req.loai
        if loai not in VOUCHER_KINDS:
            raise StockVoucherError("Loại yêu cầu không hợp lệ.")

        lines_by_id = {ln.id: ln for ln in req.lines}
        prepared: list[dict] = []
        # Cộng dồn theo dòng yêu cầu để chặn cả trường hợp 1 phiếu có nhiều dòng cùng ứng
        # vào một dòng yêu cầu (phân bổ nhiều lô) — kiểm từng dòng lẻ sẽ lọt.
        wanted: dict[int, float] = {}
        # Lý do CẤP/NHẬP THIẾU theo từng dòng yêu cầu (kho phản hồi). Lấy từ dòng phiếu đầu có lý do.
        ly_do_by_rl: dict[int, str] = {}

        for ln in lines:
            rl = lines_by_id.get(ln.get("request_line_id"))
            if rl is None:
                raise StockVoucherError("Dòng phiếu không thuộc yêu cầu đã chọn.")
            qty = float(ln.get("so_luong") or 0)
            if qty <= 0:
                raise StockVoucherError("Số lượng trên phiếu phải lớn hơn 0.")
            wanted[rl.id] = wanted.get(rl.id, 0.0) + qty
            ld = (ln.get("ly_do") or "").strip()
            if ld and rl.id not in ly_do_by_rl:
                ly_do_by_rl[rl.id] = ld

            # Mặt hàng KẾ THỪA từ dòng đề nghị, kho không đổi được: đề nghị đã duyệt là khoá, đổi
            # mặt hàng ở phiếu tức là cấp thứ khác với thứ người ta duyệt.
            hang = (rl.hang_loai, rl.hang_id)
            # Chốt hệ số quy đổi NGAY LÚC NÀY (xem `StockVoucherLine.sl_goc`).
            qd = self._quy_doi(rl, qty)

            item = {
                "request_line_id": rl.id,
                "hang_loai": hang[0],
                "hang_id": hang[1],
                "so_luong": qty,
                "sl_goc": qd["sl_goc"],
                "ghi_chu": ln.get("ghi_chu"),
                # Vị trí cất lô — CHỈ phiếu NHẬP; ghi sổ chép sang lô. XUẤT không tạo lô → None.
                "vi_tri": ((ln.get("vi_tri") or "").strip() or None) if loai == VOUCHER_NHAP else None,
            }
            if loai == VOUCHER_NHAP:
                # Giá của lô sắp tạo = ĐƠN GIÁ KHAI Ở YÊU CẦU (người yêu cầu nhập). Kho KHÔNG sửa
                # giá — bỏ qua `don_gia` client gửi. Lô chưa tồn tại nên `lot_id` trống tới ghi sổ.
                item["don_gia"] = int(rl.don_gia or 0)
            else:
                lot = self._require_lot(ln.get("lot_id"), hang, kho_id)
                item["lot_id"] = lot.id
            prepared.append(item)

        # Luật 2: không ứng vượt số đã duyệt. + Cấp/nhập THIẾU (SL < còn phải cấp) phải có LÝ DO.
        for rl_id, qty in wanted.items():
            rl = lines_by_id[rl_id]
            con_lai = float(rl.sl_duyet) - float(rl.sl_da_ung)
            if qty > con_lai + 1e-9:
                raise StockVoucherError(
                    "Ứng vượt số đã duyệt. Muốn cấp thêm thì phải tạo yêu cầu mới."
                )
            if qty < con_lai - 1e-9:
                ld = ly_do_by_rl.get(rl_id)
                if not ld:
                    raise StockVoucherError(
                        f"Cấp ít hơn số còn phải cấp ({qty:g}/{con_lai:g}) — phải nhập LÝ DO."
                    )
                rl.ly_do_thieu = ld  # kho phản hồi: vì sao cấp thiếu
            else:
                rl.ly_do_thieu = None  # cấp đủ đợt này → xoá lý do thiếu cũ (nếu có)

        doc_type = (
            SEQ_DOC_TYPE_STOCK_VOUCHER_IN if loai == VOUCHER_NHAP
            else SEQ_DOC_TYPE_STOCK_VOUCHER_OUT
        )
        # Số phiếu tự nhập (tuỳ chọn): chuẩn hoá HOA, chặn trùng. Bỏ trống → hệ thống tự sinh.
        ma_clean = (ma or "").strip().upper() or None
        if ma_clean is not None:
            if self.vouchers.get_by_ma(ma_clean) is not None:
                raise StockVoucherError(f"Số phiếu '{ma_clean}' đã tồn tại.")
        else:
            ma_clean = self.sequence.generate_flat_code(doc_type)
        voucher = self.vouchers.create(
            ma=ma_clean, loai=loai, request_id=req.id, nguoi_lap_id=user.id,
            kho_id=kho_id, ngay=ngay or date.today(), lines=prepared, **header
        )
        # Đã lập phiếu (nháp) → yêu cầu rời "Cần cấp" sang "Đang cấp" (Đang chuẩn bị).
        self.request_service.mark_in_progress(req)
        return voucher

    def _require_lot(self, lot_id, hang: tuple[str, int], kho_id: int):
        if not lot_id:
            raise StockVoucherError(
                "Phiếu xuất phải chọn lô — giá vốn tính đích danh theo lô."
            )
        lot = self.lots.get(lot_id)
        if lot is None:
            raise StockVoucherError("Không tìm thấy lô.")
        if (lot.hang_loai, lot.hang_id) != tuple(hang):
            raise StockVoucherError("Lô đã chọn không thuộc mặt hàng của dòng đề nghị.")
        if lot.kho_id != kho_id:
            raise StockVoucherError("Lô đã chọn không nằm trong kho xuất.")
        return lot

    # --- Ghi sổ -------------------------------------------------------------

    def post(self, voucher_id: int, user=None):
        """Ghi sổ phiếu: NHẬP tạo lô mới, XUẤT trừ lô; rồi cộng `sl_da_ung` về yêu cầu.
        `user` = người ghi sổ (lưu vào `nguoi_ghi_so_id` để hiện "ai duyệt/ghi sổ phiếu").

        Đây là điểm DUY NHẤT tồn kho thay đổi. Chạy trong 1 transaction: kiểm hết mọi
        điều kiện trước, ghi sau — để không có phiếu nào ghi được nửa vời.
        """
        v = self.vouchers.get_with_lines(voucher_id)
        if v is None:
            raise StockVoucherError("Không tìm thấy phiếu.")
        if v.trang_thai != VOUCHER_DRAFT:
            raise StockVoucherError("Chỉ ghi sổ được phiếu đang ở trạng thái Nháp.")
        # Ghi sổ = ghi vào SỔ với ngày hạch toán = HÔM NAY → chặn nếu kỳ hôm nay đã khóa.
        self._assert_period_open(v.kho_id, date.today())

        req = self.requests.get_with_lines(v.request_id)
        if req is None:
            raise StockVoucherError("Không tìm thấy yêu cầu của phiếu.")
        lines_by_id = {ln.id: ln for ln in req.lines}

        # --- Pha 1: kiểm tra toàn bộ, chưa ghi gì ---
        wanted: dict[int, float] = {}
        for ln in v.lines:
            wanted[ln.request_line_id] = wanted.get(ln.request_line_id, 0.0) + float(ln.so_luong)
        for rl_id, qty in wanted.items():
            rl = lines_by_id.get(rl_id)
            if rl is None:
                raise StockVoucherError("Dòng phiếu trỏ vào yêu cầu khác.")
            con_lai = float(rl.sl_duyet) - float(rl.sl_da_ung)
            if qty > con_lai + 1e-9:
                raise StockVoucherError("Ứng vượt số đã duyệt — không ghi sổ được.")

        if v.loai == VOUCHER_XUAT:
            # Gộp theo lô: 2 dòng cùng ăn một lô thì phải cộng lại mới biết có đủ không.
            # Cộng theo `sl_goc`: lô lưu ở ĐƠN VỊ GỐC, còn `so_luong` ở đơn vị người ta khai.
            # So hai thang khác nhau là cho xuất âm mà không hay (xuất "10 ram" khỏi lô 100 kg).
            per_lot: dict[int, float] = {}
            for ln in v.lines:
                if not ln.lot_id:
                    raise StockVoucherError("Dòng xuất thiếu lô.")
                per_lot[ln.lot_id] = per_lot.get(ln.lot_id, 0.0) + float(ln.sl_goc)
            for lot_id, qty in per_lot.items():
                lot = self.lots.get(lot_id)
                if lot is None:
                    raise StockVoucherError("Không tìm thấy lô của dòng xuất.")
                if qty > float(lot.sl_con_lai) + 1e-9:
                    raise StockVoucherError(
                        f"Lô {lot.ma_lo} chỉ còn {float(lot.sl_con_lai):g} — không đủ để xuất. "
                        "Kho không cho xuất âm."
                    )

            # Cửa thứ hai (17/08/2026): không lấn vào phần LỆNH KHÁC đang giữ chỗ.
            #
            # Kiểm trên TỔNG theo mặt hàng, không theo lô: giữ chỗ cố ý không neo lô nào (kho vẫn
            # nhập-trước-xuất-trước). Kiểm ở đây chứ không ở lúc lập phiếu — lập phiếu là nháp, còn
            # ghi sổ mới là lúc hàng thật rời kho, và giữa hai mốc đó tồn tự do có thể đã đổi.
            if self.giu_cho is not None:
                for (hang, chu), sl in self._gom_theo_hang_va_chu_the(v, lines_by_id).items():
                    loi = self.giu_cho.kiem_xuat(
                        hang=hang, so_luong=sl, lsx_id=chu[0], bai_ghep_id=chu[1])
                    if loi:
                        raise StockVoucherError(loi)

        # --- Pha 2: ghi ---
        if v.loai == VOUCHER_NHAP:
            for ln in v.lines:
                mh = self.hang.get(ln.hang_loai, ln.hang_id)
                sl_goc = float(ln.sl_goc)
                # Đơn giá khai theo ĐƠN VỊ NGƯỜI NHẬP (đ/ram), lô lưu theo đơn vị gốc (đ/kg) —
                # quy theo đúng tỉ lệ của chính dòng này: 1.020.000 đ/ram ÷ 41,93 kg/ram ≈ 24.325 đ/kg.
                gia_goc = round(float(ln.don_gia or 0) * float(ln.so_luong) / sl_goc) if sl_goc else 0
                lot = self.lots.create(
                    ma_lo=self.lots.next_ma_lo(mh.ma, v.ngay),
                    hang_loai=ln.hang_loai,
                    hang_id=ln.hang_id,
                    voucher_id=v.id,
                    kho_id=v.kho_id,
                    ngay_nhap=v.ngay,
                    don_gia_nhap=gia_goc,
                    sl_ban_dau=sl_goc,
                    sl_con_lai=sl_goc,
                    vi_tri=ln.vi_tri,
                )
                ln.lot_id = lot.id
        else:
            for ln in v.lines:
                self.lots.consume(self.lots.get(ln.lot_id), float(ln.sl_goc))

        for rl_id, qty in wanted.items():
            rl = lines_by_id[rl_id]
            rl.sl_da_ung = float(rl.sl_da_ung) + qty

        # --- Pha 3: báo cho GIỮ CHỖ (17/08/2026) ---
        #
        # XUẤT ⇒ phần giữ của chính lệnh đó HOÁ THÀNH phần đã cấp, nhả khỏi bảng giữ chỗ. Không nhả
        # là đếm hai lần: tồn đã giảm khi ghi sổ, mà chỗ giữ vẫn trừ tiếp vào tồn tự do ⇒ mọi lệnh
        # khác báo thiếu oan.
        #
        # NHẬP ⇒ hàng vừa vào kho, gọi `nhat_them` để lệnh nào đang bật công tắc mà còn thiếu thì
        # được bù NGAY. Đây là toàn bộ ý nghĩa của "bật = đăng ký, không phải chụp một lần" —
        # không ai phải nhớ quay lại bấm đúng lúc hàng nhập.
        if self.giu_cho is not None:
            if v.loai == VOUCHER_XUAT:
                for (hang, chu), sl in self._gom_theo_hang_va_chu_the(v, lines_by_id).items():
                    if chu != (None, None):
                        self.giu_cho.tieu_thu(hang=hang, so_luong=sl,
                                              lsx_id=chu[0], bai_ghep_id=chu[1])
            else:
                self.giu_cho.nhat_them()

        v.trang_thai = VOUCHER_POSTED
        v.ghi_so_luc = datetime.now(timezone.utc)
        if user is not None:
            v.nguoi_ghi_so_id = user.id
        v = self.vouchers.save(v)
        # Yêu cầu tự chuyển Hoàn tất / Đã cấp một phần + đẩy realtime cho người yêu cầu.
        self.request_service.refresh_fulfillment(req)
        return v

    @staticmethod
    def _gom_theo_hang_va_chu_the(v, lines_by_id: dict) -> dict[tuple, float]:
        """`{((hang_loai, hang_id), (lsx_id, bai_ghep_id)): Σ sl_goc}` của phiếu.

        Gộp theo ĐƠN VỊ GỐC (`sl_goc`) vì giữ chỗ đếm bằng đơn vị gốc — so `so_luong` (đơn vị người
        khai) với chỗ giữ là so hai thang khác nhau, đúng bẫy mà cửa kiểm lô ngay trên đã dặn.

        Chủ thể lấy từ DÒNG YÊU CẦU: phiếu kho không tự biết xuất cho lệnh nào, `stock_request_lines`
        mới là chỗ khai.
        """
        ra: dict[tuple, float] = {}
        for ln in v.lines:
            rl = lines_by_id.get(ln.request_line_id)
            khoa = (
                (ln.hang_loai, ln.hang_id),
                (getattr(rl, "lsx_id", None), getattr(rl, "bai_ghep_id", None)),
            )
            ra[khoa] = ra.get(khoa, 0.0) + float(ln.sl_goc)
        return ra

    def cancel(self, voucher_id: int, ly_do: str):
        """Hủy phiếu khi CÒN NHÁP — BẮT BUỘC lý do; yêu cầu chuyển 'Đã hủy' kèm lý do (KẾT THÚC,
        không cấp lại). Phiếu đã ghi sổ không hủy được — muốn sửa thì lập phiếu điều chỉnh
        (BRD §1.5: chứng từ đã ghi không sửa trực tiếp)."""
        v = self.vouchers.get(voucher_id)
        if v is None:
            raise StockVoucherError("Không tìm thấy phiếu.")
        if v.trang_thai != VOUCHER_DRAFT:
            raise StockVoucherError(
                "Phiếu đã ghi sổ không hủy được — hãy lập phiếu điều chỉnh."
            )
        # Hủy phiếu NHÁP chưa vào sổ → không xét khóa kỳ (phiếu đã ghi sổ vốn không hủy được).
        v.trang_thai = VOUCHER_CANCELLED
        v = self.vouchers.save(v)
        # Không còn phiếu active nào cho yêu cầu → yêu cầu chuyển 'Đã hủy' kèm lý do (kết thúc).
        # Còn phiếu ĐÃ GHI SỔ (đã cấp một phần) → giữ nguyên trạng thái, không đóng yêu cầu.
        req = self.requests.get_with_lines(v.request_id)
        if req is not None:
            rows, _ = self.vouchers.list(request_id=req.id)
            if not any(x.trang_thai != VOUCHER_CANCELLED for x in rows):
                self.request_service.cancel_by_kho(req, ly_do)
        return v

    def set_lot_vi_tri(self, lot_id: int, vi_tri: str | None):
        """Thủ kho sửa VỊ TRÍ cất lô (kệ/ô) trong kho — người cầm hàng quản vị trí vật lý."""
        lot = self.lots.set_vi_tri(lot_id, (vi_tri or "").strip() or None)
        if lot is None:
            raise StockVoucherError("Không tìm thấy lô.")
        return lot

    # --- Gợi ý phân bổ lô ----------------------------------------------------

    def suggest_allocation(
        self, hang: tuple[str, int], kho_id: int, qty: float
    ) -> tuple[list[dict], float]:
        """Gợi ý lấy `qty` (ĐƠN VỊ GỐC) từ những lô nào (FEFO → FIFO): `(dòng phân bổ, còn thiếu)`.

        Chỉ là GỢI Ý: thủ kho sửa được, vì BRD §3.19 chốt giá xuất đích danh — người cầm
        hàng mới biết lô nào đang ở đầu kệ. Không đủ hàng thì trả phần lấy được kèm
        `thieu` > 0 để UI báo thiếu thay vì âm thầm cấp non.
        """
        remaining = float(qty)
        out: list[dict] = []
        for lot in self.lots.issuable_lots(hang, kho_id):
            if remaining <= 0:
                break
            take = min(remaining, float(lot.sl_con_lai))
            out.append({
                "lot_id": lot.id,
                "ma_lo": lot.ma_lo,
                "ngay_nhap": lot.ngay_nhap,
                "hsd": lot.hsd,
                "sl_con_lai": float(lot.sl_con_lai),
                "so_luong": take,
                "don_gia_nhap": int(lot.don_gia_nhap or 0),
            })
            remaining -= take
        return out, max(0.0, round(remaining, 2))

    # --- Giá vốn ------------------------------------------------------------

    def cost_of(self, voucher: StockVoucher) -> int:
        """Giá vốn phiếu. NHẬP dùng `don_gia` trên dòng; XUẤT lấy giá ĐÍCH DANH của lô.

        Router chỉ gọi khi người dùng có `can_view_cost` — thiếu quyền thì không những ẩn
        cột mà còn không tính, để số không lọt ra qua response.
        """
        total = 0
        for ln in voucher.lines:
            if voucher.loai == VOUCHER_NHAP:
                # NHẬP: đơn giá và số lượng CÙNG ở đơn vị người khai — nhân thẳng, khỏi quy đổi.
                total += int(round(int(ln.don_gia or 0) * float(ln.so_luong)))
            else:
                # XUẤT: giá của lô theo ĐƠN VỊ GỐC nên phải nhân với `sl_goc`, không phải
                # `so_luong` — nhân nhầm là giá vốn lệch đúng bằng hệ số quy đổi.
                lot = self.lots.get(ln.lot_id) if ln.lot_id else None
                unit = int(lot.don_gia_nhap or 0) if lot else 0
                total += int(round(unit * float(ln.sl_goc)))
        return total

    # --- Đính kèm hóa đơn/chứng từ gốc (mirror accounting) ------------------
    def _voucher_or_raise(self, voucher_id: int) -> StockVoucher:
        v = self.vouchers.get(voucher_id)
        if v is None:
            raise StockVoucherError("Không tìm thấy phiếu.")
        return v

    def list_attachments(self, voucher_id: int) -> list[dict]:
        self._voucher_or_raise(voucher_id)
        return [self._attachment_out(r) for r in self.vouchers.list_attachments(voucher_id)]

    def add_attachment(self, voucher_id: int, *, actor, file_name: str | None,
                       content_type: str | None, data: bytes) -> dict:
        v = self._voucher_or_raise(voucher_id)
        if v.trang_thai == VOUCHER_CANCELLED:
            raise StockVoucherError("Phiếu đã hủy — không đính kèm thêm.")
        ct = (content_type or "").lower()
        if not (ct.startswith("image/") or ct == "application/pdf"):
            raise StockVoucherError("Chỉ nhận ảnh (image/*) hoặc PDF.")
        if not data:
            raise StockVoucherError("Tệp rỗng.")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise StockVoucherError("Tệp vượt quá 10 MB.")
        if len(self.vouchers.list_attachments(v.id)) >= MAX_ATTACHMENTS_PER_VOUCHER:
            raise StockVoucherError(
                f"Mỗi phiếu tối đa {MAX_ATTACHMENTS_PER_VOUCHER} file đính kèm."
            )
        safe_name = _safe_attachment_name(file_name)
        key = f"{_ATTACHMENT_SUBDIR}/{v.id}/{secrets.token_hex(4)}_{safe_name}"
        get_storage().save(key, data, content_type)
        row = StockVoucherAttachment(
            stock_voucher_id=v.id,
            file_name=safe_name,
            file_url=url_from_key(key),  # "/api/files/kho/<id>/.." — đọc qua router có đăng nhập
            file_type=content_type,
            uploaded_by=getattr(actor, "id", None),
        )
        return self._attachment_out(self.vouchers.save_attachment(row))

    def delete_attachment(self, voucher_id: int, attachment_id: int, *, actor) -> None:
        self._voucher_or_raise(voucher_id)
        att = self.vouchers.get_attachment(attachment_id)
        if att is None or att.stock_voucher_id != voucher_id:
            raise StockVoucherError("Không tìm thấy file đính kèm.")
        key = key_from_url(att.file_url)
        if key:
            get_storage().delete(key)  # best-effort; row vẫn phải xoá dù file đã mất
        self.vouchers.delete_attachment(att)

    @staticmethod
    def _attachment_out(row: StockVoucherAttachment) -> dict:
        return {
            "id": row.id,
            "stock_voucher_id": row.stock_voucher_id,
            "file_name": row.file_name,
            "file_url": row.file_url,
            "file_type": row.file_type,
            "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at,
        }
