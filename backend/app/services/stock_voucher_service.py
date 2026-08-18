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
    def __init__(self, vouchers, requests, lots, sequence, request_service, hang) -> None:
        self.vouchers = vouchers
        self.requests = requests
        self.lots = lots
        self.sequence = sequence
        self.request_service = request_service
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
        # ĐIỀU CHUYỂN: phiếu KẾ THỪA cờ từ yêu cầu — cả phiếu XUẤT nguồn (tự lập) lẫn phiếu NHẬP đích
        # (kho đích lập từ yêu cầu điều chuyển) đều bật `dieu_chuyen` để báo cáo gắn nhãn + loại khỏi
        # tổng mua/bán. Nhập/xuất thường: yêu cầu `dieu_chuyen=False` → phiếu cũng false. mig 0203.
        header.setdefault("dieu_chuyen", bool(getattr(req, "dieu_chuyen", False)))
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

    def _apply_post(self, v: StockVoucher, user=None) -> StockRequest:
        """Ghi sổ MỘT phiếu vào tồn — KHÔNG commit (chỉ mutate + flush qua repo). Tách ra để GHÉP
        nhiều phiếu (điều chuyển: xuất nguồn + nhập đích) vào MỘT giao dịch. Trả yêu cầu gốc để
        caller gọi `refresh_fulfillment` sau khi commit. Kiểm hết điều kiện TRƯỚC, ghi SAU."""
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

        v.trang_thai = VOUCHER_POSTED
        v.ghi_so_luc = datetime.now(timezone.utc)
        if user is not None:
            v.nguoi_ghi_so_id = user.id
        return req

    def post(self, voucher_id: int, user=None):
        """Ghi sổ phiếu — điểm DUY NHẤT tồn kho đổi. Chạy trong 1 transaction.

        ĐIỀU CHUYỂN (mô hình 2 yêu cầu): phiếu XUẤT nguồn được tạo NHÁP lúc ấn điều chuyển, CHƯA trừ
        tồn. Khi kho đích ghi sổ phiếu NHẬP → ghi sổ LUÔN phiếu xuất nguồn (draft) trong CÙNG một
        giao dịch: **trừ nguồn RỒI cộng đích cùng một nhịp** (không trừ trước lúc chưa ghi sổ)."""
        v = self.vouchers.get_with_lines(voucher_id)
        if v is None:
            raise StockVoucherError("Không tìm thấy phiếu.")
        if v.trang_thai != VOUCHER_DRAFT:
            raise StockVoucherError("Chỉ ghi sổ được phiếu đang ở trạng thái Nháp.")

        dest_req = self.requests.get_with_lines(v.request_id)
        # Phiếu XUẤT nguồn của điều chuyển KHÔNG ghi sổ riêng — nó tự ghi sổ khi kho đích nhập.
        if (dest_req is not None and getattr(dest_req, "dieu_chuyen", False)
                and v.loai == VOUCHER_XUAT):
            raise StockVoucherError(
                "Phiếu xuất điều chuyển tự ghi sổ khi kho đích nhập — không ghi sổ riêng."
            )

        # ĐIỀU CHUYỂN: phiếu NHẬP đích ghi sổ → ghép phiếu XUẤT nguồn (draft) vào cùng giao dịch.
        src_v: StockVoucher | None = None
        if (dest_req is not None and getattr(dest_req, "dieu_chuyen", False)
                and v.loai == VOUCHER_NHAP and getattr(dest_req, "xuat_voucher_id", None)):
            cand = self.vouchers.get_with_lines(dest_req.xuat_voucher_id)
            if cand is None or cand.trang_thai == VOUCHER_CANCELLED:
                raise StockVoucherError(
                    "Phiếu xuất nguồn của điều chuyển không còn — không nhập kho đích được."
                )
            if cand.trang_thai == VOUCHER_DRAFT:
                src_v = cand  # sẽ ghi sổ CÙNG LÚC (trừ nguồn); đã posted thì bỏ qua (nguồn đã trừ).

        src_req = self._apply_post(src_v, user) if src_v is not None else None  # trừ nguồn
        req = self._apply_post(v, user)                                          # cộng đích
        self.vouchers.db.commit()  # MỘT commit → trừ nguồn + cộng đích cùng nhịp (atomic)
        self.vouchers.db.refresh(v)
        # Yêu cầu tự chuyển Hoàn tất / Đã cấp một phần + đẩy realtime (vế xuất nguồn im lặng).
        if src_req is not None:
            self.request_service.refresh_fulfillment(src_req)
        self.request_service.refresh_fulfillment(req)
        return v

    # --- Điều chuyển kho (tái dùng nhập/xuất — spec-dieu-chuyen-kho) ---------

    def dieu_chuyen(self, *, user, kho_nguon_id: int, kho_den_id: int,
                    items: list[dict], ghi_chu: str | None = None) -> dict:
        """Ấn ĐIỀU CHUYỂN 1 HAY NHIỀU mặt hàng kho nguồn → kho đích (option A: trừ nguồn NGAY).

        Gộp CẢ danh sách vào MỘT nhịp, tái dùng TRỌN cơ chế nhập/xuất:
          1) MỘT yêu cầu XUẤT nội bộ ở nguồn (nhiều dòng) + MỘT phiếu XUẤT (FIFO đích danh mỗi mặt
             hàng) + GHI SỔ → trừ tồn nguồn, chốt GIÁ VỐN BÌNH QUÂN từng mặt hàng.
          2) MỘT yêu cầu NHẬP ở đích (yêu cầu điều chuyển, nhiều dòng) mang kho nguồn + phiếu xuất +
             đơn giá từng dòng = giá vốn chốt → kho đích lập MỘT phiếu nhập (đơn giá khoá).
        Trả `{yeu_cau, phieu_xuat, gia_von}` (gia_von = tổng giá vốn điều chuyển)."""
        if kho_nguon_id == kho_den_id:
            raise StockVoucherError("Kho nguồn và kho đích phải khác nhau.")
        if not items:
            raise StockVoucherError("Chưa chọn mặt hàng để điều chuyển.")

        # (1) Duyệt từng mặt hàng: đơn vị gốc + FIFO đích danh ở nguồn + giá vốn bình quân.
        # Điều chuyển theo ĐƠN VỊ GỐC (spec §13) → dòng yêu cầu lấy dvt = đơn vị gốc, hệ số quy đổi
        # = 1: số trên phiếu = số vào lô, giá vốn (đ/gốc) khớp thẳng.
        prepared: list[dict] = []
        seen: set[tuple[str, int]] = set()
        for it in items:
            hang_loai, hang_id = it["hang_loai"], int(it["hang_id"])
            key = (hang_loai, hang_id)
            if key in seen:
                raise StockVoucherError("Một mặt hàng chỉ được điều chuyển 1 dòng — gộp số lượng lại.")
            seen.add(key)
            qty = float(it.get("so_luong") or 0)
            if qty <= 0:
                raise StockVoucherError("Số lượng điều chuyển phải lớn hơn 0.")
            dv = self.hang.don_vi_cua_mat_hang(hang_loai, hang_id)
            dvt_goc = dv.get("don_vi_goc")
            ten = dv.get("ten") or "Mặt hàng"
            if not dvt_goc:
                raise StockVoucherError(f"“{ten}” chưa khai đơn vị tính — không điều chuyển được.")
            alloc, thieu = self.suggest_allocation(key, kho_nguon_id, qty)
            if thieu > 1e-9:
                raise StockVoucherError(
                    f"“{ten}”: kho nguồn không đủ tồn để điều chuyển (thiếu {thieu:g} {dvt_goc})."
                )
            tong_tien = sum(float(a["so_luong"]) * int(a["don_gia_nhap"] or 0) for a in alloc)
            prepared.append({
                "hang_loai": hang_loai, "hang_id": hang_id, "dvt_goc": dvt_goc,
                "qty": qty, "alloc": alloc, "gia_von": int(round(tong_tien / qty)) if qty else 0,
            })

        # Điều chuyển rồi sẽ ghi sổ ở kho nguồn (lúc đích nhập) → chặn SỚM nếu kỳ nguồn đã khóa sổ
        # (kiểm lại lúc ghi sổ trong `_apply_post`).
        self._assert_period_open(kho_nguon_id, date.today())

        # (2) MỘT yêu cầu XUẤT nội bộ ở nguồn (im lặng) — mỗi mặt hàng 1 dòng.
        src_req = self.request_service.create_dieu_chuyen(
            user=user, loai=VOUCHER_XUAT, kho_id=kho_nguon_id, ghi_chu=ghi_chu, notify=False,
            lines=[
                {"hang_loai": p["hang_loai"], "hang_id": p["hang_id"],
                 "dvt": p["dvt_goc"], "sl_de_nghi": p["qty"]}
                for p in prepared
            ],
        )
        # Nối dòng yêu cầu ↔ mặt hàng theo CẶP (hang_loai, hang_id) — không dựa thứ tự (bền hơn).
        src_by_hang = {(rl.hang_loai, rl.hang_id): rl for rl in src_req.lines}
        xuat_lines: list[dict] = []
        for p in prepared:
            rl = src_by_hang[(p["hang_loai"], p["hang_id"])]
            for a in p["alloc"]:
                xuat_lines.append({
                    "request_line_id": rl.id, "so_luong": float(a["so_luong"]),
                    "lot_id": a["lot_id"],
                })
        # Phiếu xuất nguồn để NHÁP — CHƯA trừ tồn. Nó tự ghi sổ (trừ nguồn) khi kho đích ghi sổ
        # phiếu nhập (xem `post`): trừ nguồn RỒI cộng đích cùng một nhịp, không trừ trước.
        xuat = self.create(
            user=user, request_id=src_req.id, kho_id=kho_nguon_id, ghi_chu=ghi_chu, lines=xuat_lines,
        )

        # (3) MỘT yêu cầu NHẬP ở đích = yêu cầu điều chuyển (THẤY ĐƯỢC): đơn giá từng dòng = giá vốn
        # chốt → phiếu nhập đích khoá đơn giá; kho nguồn + phiếu xuất để truy cặp đi–đến.
        dest_req = self.request_service.create_dieu_chuyen(
            user=user, loai=VOUCHER_NHAP, kho_id=kho_den_id,
            kho_nguon_id=kho_nguon_id, xuat_voucher_id=xuat.id, ghi_chu=ghi_chu, notify=True,
            lines=[
                {"hang_loai": p["hang_loai"], "hang_id": p["hang_id"], "dvt": p["dvt_goc"],
                 "sl_de_nghi": p["qty"], "don_gia": p["gia_von"]}
                for p in prepared
            ],
        )
        tong_gia_von = sum(int(round(p["gia_von"] * p["qty"])) for p in prepared)
        return {"yeu_cau": dest_req, "phieu_xuat": xuat, "gia_von": tong_gia_von}

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
        # ĐIỀU CHUYỂN: KHÔNG hủy riêng vế xuất nguồn (nó gắn cặp với yêu cầu điều chuyển ở đích;
        # hủy riêng sẽ làm kho đích không nhập được). Vế xuất nguồn cũng đã ẩn khỏi mọi list.
        req0 = self.requests.get(v.request_id)
        if req0 is not None and getattr(req0, "dieu_chuyen", False) and v.loai == VOUCHER_XUAT:
            raise StockVoucherError(
                "Phiếu xuất điều chuyển không hủy riêng — nó gắn với yêu cầu điều chuyển ở kho đích."
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
