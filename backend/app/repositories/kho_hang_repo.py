"""Repository — Danh mục Kho hàng. CRUD + tìm theo mã/tên + sinh mã tự động."""
from __future__ import annotations

from sqlalchemy import func, select

from ..models.kho_hang import KhoHang
from ..models.stock_lot import StockLot
from ..models.stock_request import REQUEST_FULFILLABLE, StockRequest
from ..models.stock_voucher import VOUCHER_DRAFT, StockVoucher
from .catalog_base import CatalogRepo


class KhoHangRepository(CatalogRepo):
    model = KhoHang
    fields = ("ten", "vi_tri", "ghi_chu", "active")
    ma_prefix = "KHO-"
    commit_on_write = False   # `KhoHangService` chốt sau khi đã ghi nhật ký — xem `catalog_base`

    def dem_rang_buoc(self, kho_id: int) -> dict[str, int]:
        """Ba con số CHẶN xoá một kho: lô còn tồn · phiếu chờ ghi sổ · đề nghị đang xử lý.

        Ba câu `select()` này trước 15/08/2026 nằm trong `kho_hang_service._blockers` và chạy qua
        `self.repo.db` — service tự truy DB là đi vòng qua tầng repo, và ba model kho lọt vào
        import của service.

        Phiếu ĐÃ ghi sổ (lịch sử) KHÔNG kể — xóa mềm giữ nguyên FK để tra cứu.
        """
        def _dem(model, *conds) -> int:
            return int(self.db.execute(
                select(func.count()).select_from(model).where(*conds)
            ).scalar_one())

        return {
            "lo_con_ton": _dem(StockLot, StockLot.kho_id == kho_id, StockLot.sl_con_lai > 0),
            "phieu_cho_ghi_so": _dem(StockVoucher, StockVoucher.kho_id == kho_id,
                                     StockVoucher.trang_thai == VOUCHER_DRAFT),
            "de_nghi_dang_xu_ly": _dem(StockRequest, StockRequest.kho_id == kho_id,
                                       StockRequest.trang_thai.in_(REQUEST_FULFILLABLE)),
        }
