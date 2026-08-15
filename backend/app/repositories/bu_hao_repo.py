"""Repository — Danh mục Bù hao. CRUD + tìm theo mã/tên."""
from __future__ import annotations

from ..models.bu_hao import BuHao
from .catalog_base import CatalogRepo


class BuHaoRepository(CatalogRepo):
    model = BuHao
    fields = ("ten", "bac", "ghi_chu", "active")
    commit_on_write = False   # `BuHaoService` chốt sau khi đã ghi nhật ký — xem `catalog_base`
    # Không có `ma_prefix`: mã bù hao do người khai tự đặt (BH-GIAY, BH-MANG…), không tự sinh.
