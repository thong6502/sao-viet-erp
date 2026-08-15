"""Repository — Loại sản phẩm (template). CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from ..models.loai_san_pham import LoaiSanPham
from .catalog_base import CatalogRepo

ASSIGNABLE = (
    "ten", "structural_type", "box_sub_type", "imposition_rule_id",
    "has_cover", "cover_type", "default_binding", "default_stock_class", "routing_template",
    "ghi_chu", "active",
)


class LoaiSanPhamRepository(CatalogRepo):
    model = LoaiSanPham
    fields = ASSIGNABLE
    commit_on_write = False   # `LoaiSanPhamService` chốt sau khi ghi nhật ký — xem `catalog_base`
    # Mã KHAI TAY (service không tự cấp), nhưng quy ước đánh số là `LSP-####` — khai `ma_prefix`
    # để `GET /api/loai-san-pham/ma-goi-y` gợi được mã kế tiếp. Trước 15/08/2026 frontend tự đoán
    # tiền tố này bằng cách dò chuỗi trong URL (`danh-muc/maGoiY.ts`).
    ma_prefix = "LSP-"

    def extra_conds(self, *, structural_type: str | None = None, **_) -> list:
        return [LoaiSanPham.structural_type == structural_type] if structural_type else []
