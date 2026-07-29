"""Service — Phiếu nhập/xuất kho: ứng theo đề nghị, phân bổ lô, ghi sổ, giá vốn.

docs/spec-kho-de-nghi.md §5–§6. Bốn luật cứng sống ở đây:

1. **Không có đề nghị đã duyệt thì không lập được phiếu** (§5).
2. **Không cho ứng vượt `sl_duyet`** — muốn thêm phải đề nghị mới (BRD §2.5 b8).
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

# Đính kèm phiếu kho: bytes dưới <backend>/static/kho/<voucher_id>/ (cùng gốc mount /static
# của main.py) — /static public nên giới hạn loại + cỡ file. Mirror accounting_service.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
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
    def __init__(self, vouchers, requests, lots, materials, sequence, request_service,
                 material_service=None) -> None:
        self.vouchers = vouchers
        self.requests = requests
        self.lots = lots
        self.materials = materials
        self.sequence = sequence
        self.request_service = request_service
        # Tạo mã cho HÀNG MỚI ngay khi lập/ghi sổ phiếu (không tạo eager ở FE). None → tính năng
        # tạo-mới tắt (chỉ chấp nhận mã có sẵn) — router luôn truyền vào nên nhánh này chỉ là chốt an toàn.
        self.material_service = material_service

    def _create_new_material(self, user, rl):
        """Tạo sản phẩm mới (loại hang_khac, mã tự sinh HH###) từ khai báo TRÊN ĐỀ NGHỊ: tên
        (`ten_tu_do`), ĐVT (`dvt`), QUY ĐỔI (`don_vi_phu`/`he_so_quy_doi`) — kho KHÔNG khai lại.
        Tên trùng hàng đã có → dùng luôn mã cũ, khỏi chặn cứng lúc ghi sổ."""
        from ..services.material_service import MaterialDuplicate

        if self.material_service is None:
            raise StockVoucherError("Chưa cấu hình tạo sản phẩm mới ở phiếu.")
        name = (getattr(rl, "ten_tu_do", None) or "").strip()
        unit = (rl.dvt or "").strip() or "cái"
        dvp = (getattr(rl, "don_vi_phu", None) or "").strip() or None
        hs = getattr(rl, "he_so_quy_doi", None)
        hs_val = float(hs) if (dvp and hs and float(hs) > 0) else None
        try:
            return self.material_service.create_material(
                name=name, material_type="hang_khac", unit=unit, actor=user,
                don_vi_phu=dvp, he_so_quy_doi=hs_val,
            )
        except MaterialDuplicate:
            existing = self.materials.find_by_name(name)
            if existing is not None:
                return existing
            raise StockVoucherError(
                f"Tên vật tư '{name}' đã tồn tại — chọn mã có sẵn thay vì tạo mới."
            )

    # --- Lập phiếu ----------------------------------------------------------

    def create(self, *, user, request_id: int, kho_id: int, lines: list[dict],
               ngay: date | None = None, ma: str | None = None, **header) -> StockVoucher:
        req = self.requests.get_with_lines(request_id)
        if req is None:
            raise StockVoucherError("Không tìm thấy đề nghị.")
        # Luật 1: mọi phiếu phải ứng theo một đề nghị ĐÃ DUYỆT.
        if req.trang_thai not in REQUEST_FULFILLABLE:
            raise StockVoucherError(
                "Chỉ lập phiếu cho đề nghị đã duyệt (và chưa hoàn tất)."
            )
        if not lines:
            raise StockVoucherError("Phiếu phải có ít nhất 1 dòng.")

        loai = req.loai
        if loai not in VOUCHER_KINDS:
            raise StockVoucherError("Loại đề nghị không hợp lệ.")

        lines_by_id = {ln.id: ln for ln in req.lines}
        prepared: list[dict] = []
        # Cộng dồn theo dòng đề nghị để chặn cả trường hợp 1 phiếu có nhiều dòng cùng ứng
        # vào một dòng đề nghị (phân bổ nhiều lô) — kiểm từng dòng lẻ sẽ lọt.
        wanted: dict[int, float] = {}
        # Lý do CẤP/NHẬP THIẾU theo từng dòng đề nghị (kho phản hồi). Lấy từ dòng phiếu đầu có lý do.
        ly_do_by_rl: dict[int, str] = {}
        # Dòng HÀNG MỚI chưa có mã: (chỉ số trong `prepared`, dòng đề nghị `rl`). TẠO SẢN PHẨM SAU
        # khi mọi kiểm tra đã qua (repo.create commit ngay) → phiếu lỗi thì không rác danh mục.
        to_create: list[tuple[int, object]] = []

        for ln in lines:
            rl = lines_by_id.get(ln.get("request_line_id"))
            if rl is None:
                raise StockVoucherError("Dòng phiếu không thuộc đề nghị đã chọn.")
            qty = float(ln.get("so_luong") or 0)
            if qty <= 0:
                raise StockVoucherError("Số lượng trên phiếu phải lớn hơn 0.")
            wanted[rl.id] = wanted.get(rl.id, 0.0) + qty
            ld = (ln.get("ly_do") or "").strip()
            if ld and rl.id not in ly_do_by_rl:
                ly_do_by_rl[rl.id] = ld

            # Hàng đã có mã (đề nghị đã có, hoặc kho CHỌN mã có sẵn). None = hàng mới chờ tạo.
            mat_id = rl.material_id if rl.material_id is not None else ln.get("material_id")

            item = {
                "request_line_id": rl.id,
                "material_id": mat_id,
                "so_luong": qty,
                "ghi_chu": ln.get("ghi_chu"),
            }
            if loai == VOUCHER_NHAP:
                # Giá của lô sắp tạo = ĐƠN GIÁ KHAI Ở ĐỀ NGHỊ (người đề nghị nhập). Kho KHÔNG sửa
                # giá — bỏ qua `don_gia` client gửi. Lô chưa tồn tại nên `lot_id` trống tới ghi sổ.
                item["don_gia"] = int(rl.don_gia or 0)
                if mat_id is None:
                    # Hàng mới: TÊN + ĐVT + QUY ĐỔI lấy từ ĐỀ NGHỊ (rl). Tạo mã ở lượt sau (sau validate).
                    if not (rl.ten_tu_do or "").strip():
                        raise StockVoucherError(
                            "Hàng mới trên đề nghị chưa có tên vật tư — không tạo được mã."
                        )
                    to_create.append((len(prepared), rl))
            else:
                if mat_id is None:
                    raise StockVoucherError(
                        f"Hàng \"{rl.ten_tu_do or ''}\" chưa có mã — không xuất được hàng chưa nhập."
                    )
                lot = self._require_lot(ln.get("lot_id"), mat_id, kho_id)
                item["lot_id"] = lot.id
            prepared.append(item)

        # Luật 2: không ứng vượt số đã duyệt. + Cấp/nhập THIẾU (SL < còn phải cấp) phải có LÝ DO.
        for rl_id, qty in wanted.items():
            rl = lines_by_id[rl_id]
            con_lai = float(rl.sl_duyet) - float(rl.sl_da_ung)
            if qty > con_lai + 1e-9:
                raise StockVoucherError(
                    "Ứng vượt số đã duyệt. Muốn cấp thêm thì phải tạo đề nghị mới."
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

        # Validate xong → giờ mới TẠO sản phẩm mới + set mã về dòng đề nghị (đề nghị + lô trỏ mã thật).
        for idx, rl in to_create:
            mat = self._create_new_material(user, rl)
            prepared[idx]["material_id"] = mat.id
            rl.material_id = mat.id

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
        # Đã lập phiếu (nháp) → đề nghị rời "Cần cấp" sang "Đang cấp" (Đang chuẩn bị).
        self.request_service.mark_in_progress(req)
        return voucher

    def _require_lot(self, lot_id, material_id: int, kho_id: int):
        if not lot_id:
            raise StockVoucherError(
                "Phiếu xuất phải chọn lô — giá vốn tính đích danh theo lô."
            )
        lot = self.lots.get(lot_id)
        if lot is None:
            raise StockVoucherError("Không tìm thấy lô.")
        if lot.material_id != material_id:
            raise StockVoucherError("Lô đã chọn không thuộc mã hàng của dòng đề nghị.")
        if lot.kho_id != kho_id:
            raise StockVoucherError("Lô đã chọn không nằm trong kho xuất.")
        return lot

    # --- Ghi sổ -------------------------------------------------------------

    def post(self, voucher_id: int, user=None):
        """Ghi sổ phiếu: NHẬP tạo lô mới, XUẤT trừ lô; rồi cộng `sl_da_ung` về đề nghị.
        `user` = người ghi sổ (lưu vào `nguoi_ghi_so_id` để hiện "ai duyệt/ghi sổ phiếu").

        Đây là điểm DUY NHẤT tồn kho thay đổi. Chạy trong 1 transaction: kiểm hết mọi
        điều kiện trước, ghi sau — để không có phiếu nào ghi được nửa vời.
        """
        v = self.vouchers.get_with_lines(voucher_id)
        if v is None:
            raise StockVoucherError("Không tìm thấy phiếu.")
        if v.trang_thai != VOUCHER_DRAFT:
            raise StockVoucherError("Chỉ ghi sổ được phiếu đang ở trạng thái Nháp.")

        req = self.requests.get_with_lines(v.request_id)
        if req is None:
            raise StockVoucherError("Không tìm thấy đề nghị của phiếu.")
        lines_by_id = {ln.id: ln for ln in req.lines}

        # --- Pha 1: kiểm tra toàn bộ, chưa ghi gì ---
        wanted: dict[int, float] = {}
        for ln in v.lines:
            wanted[ln.request_line_id] = wanted.get(ln.request_line_id, 0.0) + float(ln.so_luong)
        for rl_id, qty in wanted.items():
            rl = lines_by_id.get(rl_id)
            if rl is None:
                raise StockVoucherError("Dòng phiếu trỏ vào đề nghị khác.")
            con_lai = float(rl.sl_duyet) - float(rl.sl_da_ung)
            if qty > con_lai + 1e-9:
                raise StockVoucherError("Ứng vượt số đã duyệt — không ghi sổ được.")

        if v.loai == VOUCHER_XUAT:
            # Gộp theo lô: 2 dòng cùng ăn một lô thì phải cộng lại mới biết có đủ không.
            per_lot: dict[int, float] = {}
            for ln in v.lines:
                if not ln.lot_id:
                    raise StockVoucherError("Dòng xuất thiếu lô.")
                per_lot[ln.lot_id] = per_lot.get(ln.lot_id, 0.0) + float(ln.so_luong)
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
                material = self.materials.get_by_id(ln.material_id)
                code = getattr(material, "code", None) or str(ln.material_id)
                lot = self.lots.create(
                    ma_lo=self.lots.next_ma_lo(code, v.ngay),
                    material_id=ln.material_id,
                    voucher_id=v.id,
                    kho_id=v.kho_id,
                    ngay_nhap=v.ngay,
                    don_gia_nhap=int(ln.don_gia or 0),
                    sl_ban_dau=float(ln.so_luong),
                    sl_con_lai=float(ln.so_luong),
                )
                ln.lot_id = lot.id
        else:
            for ln in v.lines:
                self.lots.consume(self.lots.get(ln.lot_id), float(ln.so_luong))

        for rl_id, qty in wanted.items():
            rl = lines_by_id[rl_id]
            rl.sl_da_ung = float(rl.sl_da_ung) + qty

        v.trang_thai = VOUCHER_POSTED
        v.ghi_so_luc = datetime.now(timezone.utc)
        if user is not None:
            v.nguoi_ghi_so_id = user.id
        v = self.vouchers.save(v)
        # Đề nghị tự chuyển Hoàn tất / Đã cấp một phần + đẩy realtime cho người đề nghị.
        self.request_service.refresh_fulfillment(req)
        return v

    def cancel(self, voucher_id: int):
        """Hủy phiếu khi CÒN NHÁP. Phiếu đã ghi sổ không hủy được — muốn sửa thì lập phiếu
        điều chỉnh (BRD §1.5: chứng từ đã ghi không sửa trực tiếp)."""
        v = self.vouchers.get(voucher_id)
        if v is None:
            raise StockVoucherError("Không tìm thấy phiếu.")
        if v.trang_thai != VOUCHER_DRAFT:
            raise StockVoucherError(
                "Phiếu đã ghi sổ không hủy được — hãy lập phiếu điều chỉnh."
            )
        v.trang_thai = VOUCHER_CANCELLED
        v = self.vouchers.save(v)
        # Không còn phiếu active nào cho đề nghị + chưa ứng gì → đề nghị về "Cần cấp" (cấp lại).
        req = self.requests.get_with_lines(v.request_id)
        if req is not None:
            rows, _ = self.vouchers.list(request_id=req.id)
            if not any(x.trang_thai != VOUCHER_CANCELLED for x in rows):
                self.request_service.revert_if_untouched(req)
        return v

    # --- Gợi ý phân bổ lô ----------------------------------------------------

    def suggest_allocation(
        self, material_id: int, kho_id: int, qty: float
    ) -> tuple[list[dict], float]:
        """Gợi ý lấy `qty` từ những lô nào (FEFO → FIFO): `(dòng phân bổ, số còn thiếu)`.

        Chỉ là GỢI Ý: thủ kho sửa được, vì BRD §3.19 chốt giá xuất đích danh — người cầm
        hàng mới biết lô nào đang ở đầu kệ. Không đủ hàng thì trả phần lấy được kèm
        `thieu` > 0 để UI báo thiếu thay vì âm thầm cấp non.
        """
        remaining = float(qty)
        out: list[dict] = []
        for lot in self.lots.issuable_lots(material_id, kho_id):
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
                unit = int(ln.don_gia or 0)
            else:
                lot = self.lots.get(ln.lot_id) if ln.lot_id else None
                unit = int(lot.don_gia_nhap or 0) if lot else 0
            total += int(round(unit * float(ln.so_luong)))
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
        token = secrets.token_hex(4)
        dest_dir = _STATIC_DIR / _ATTACHMENT_SUBDIR / str(v.id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / f"{token}_{safe_name}").write_bytes(data)
        row = StockVoucherAttachment(
            stock_voucher_id=v.id,
            file_name=safe_name,
            file_url=f"/static/{_ATTACHMENT_SUBDIR}/{v.id}/{token}_{safe_name}",
            file_type=content_type,
            uploaded_by=getattr(actor, "id", None),
        )
        return self._attachment_out(self.vouchers.save_attachment(row))

    def delete_attachment(self, voucher_id: int, attachment_id: int, *, actor) -> None:
        self._voucher_or_raise(voucher_id)
        att = self.vouchers.get_attachment(attachment_id)
        if att is None or att.stock_voucher_id != voucher_id:
            raise StockVoucherError("Không tìm thấy file đính kèm.")
        try:
            (_STATIC_DIR.parent / att.file_url.lstrip("/")).unlink(missing_ok=True)
        except OSError:
            pass  # gỡ file đĩa best-effort — row vẫn phải xóa
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
