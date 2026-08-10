"""Danh mục Kho hàng — service CRUD (chỉ khai báo, validate nhẹ)."""
from __future__ import annotations

from sqlalchemy import func, select

from ..models.stock_lot import StockLot
from ..models.stock_request import REQUEST_FULFILLABLE, StockRequest
from ..models.stock_voucher import VOUCHER_DRAFT, StockVoucher
from ..repositories.kho_hang_repo import KhoHangRepository
from . import nhat_ky_danh_muc as nk


class KhoHangError(Exception):
    pass


class KhoHangValidationError(KhoHangError):
    pass


class KhoHangDuplicate(KhoHangError):
    pass


class KhoHangNotFound(KhoHangError):
    pass


class KhoHangInUse(KhoHangError):
    """Kho còn tồn / phiếu chờ ghi sổ / đề nghị đang xử lý → chặn xóa."""
    pass


class KhoHangService:
    def __init__(self, repo: KhoHangRepository, audit=None) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(self, data: dict) -> None:
        if not (data.get("ten") or "").strip():
            raise KhoHangValidationError("Tên kho không được trống.")

    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise KhoHangNotFound("Không tìm thấy kho.")
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def create(self, data: dict, created_by: int | None = None):
        self._validate(data)
        # Mã sinh NGẦM: UI không cho gõ mã tay. Nếu không truyền mã → tự cấp KHO-####
        # trên mọi hàng (kể cả xóa mềm) nên luôn là mã mới, không đụng ai.
        if not (data.get("ma") or "").strip():
            data = {**data, "ma": self.repo.next_ma()}
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None:
            # Trùng với kho ĐANG hoạt động = trùng thật → chặn.
            if dup.active:
                raise KhoHangDuplicate("Mã kho đã tồn tại.")
            # Trùng với kho ĐÃ XÓA MỀM (chỉ xảy ra khi mã truyền tay qua API) → tái dùng
            # đúng chỗ: ghi đè dữ liệu mới + bật lại active, không đẻ hàng rác.
            obj = self.repo.update(dup, {**data, "active": True})
            nk.ghi_tao(self.audit, actor_id=created_by, loai="kho_hang", obj=obj)
            return obj
        obj = self.repo.create(data)
        nk.ghi_tao(self.audit, actor_id=created_by, loai="kho_hang", obj=obj)
        return obj

    def update(self, item_id: int, data: dict, actor_id: int | None = None):
        obj = self.get(item_id)
        self._validate(data)
        if (data.get("ma") or "").strip():          # mã bất biến, nhưng nếu có gửi thì canh trùng
            dup = self.repo.find_by_ma(data["ma"])
            if dup is not None and dup.id != obj.id:
                raise KhoHangDuplicate("Mã kho đã tồn tại.")
        truoc = nk.anh_chup(obj)
        obj = self.repo.update(obj, data)
        nk.ghi_sua(self.audit, actor_id=actor_id, loai="kho_hang", obj=obj, truoc=truoc)
        return obj

    def _blockers(self, obj) -> list[str]:
        """Lý do CHẶN xóa: lô còn tồn / phiếu chờ ghi sổ / đề nghị đang xử lý.
        Phiếu ĐÃ ghi sổ (lịch sử) KHÔNG chặn — xóa mềm giữ nguyên FK để tra cứu."""
        db = self.repo.db
        out: list[str] = []
        ton = db.execute(
            select(func.count()).select_from(StockLot)
            .where(StockLot.kho_id == obj.id, StockLot.sl_con_lai > 0)
        ).scalar_one()
        if ton:
            out.append(f"{ton} lô còn tồn")
        draft = db.execute(
            select(func.count()).select_from(StockVoucher)
            .where(StockVoucher.kho_id == obj.id, StockVoucher.trang_thai == VOUCHER_DRAFT)
        ).scalar_one()
        if draft:
            out.append(f"{draft} phiếu chờ ghi sổ")
        pending = db.execute(
            select(func.count()).select_from(StockRequest)
            .where(StockRequest.kho_id == obj.id, StockRequest.trang_thai.in_(REQUEST_FULFILLABLE))
        ).scalar_one()
        if pending:
            out.append(f"{pending} đề nghị đang xử lý")
        return out

    def delete_blockers(self, item_id: int) -> list[str]:
        return self._blockers(self.get(item_id))

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        obj = self.get(item_id)
        blockers = self._blockers(obj)
        if blockers:
            raise KhoHangInUse("Không xóa được — kho đang dùng: " + "; ".join(blockers) + ".")
        # XÓA MỀM: giữ FK cho lịch sử phiếu đã ghi sổ; create() sẽ tái dùng nếu trùng mã.
        nk.ghi_xoa(self.audit, actor_id=actor_id, loai="kho_hang", obj=obj)
        self.repo.update(obj, {"active": False})
