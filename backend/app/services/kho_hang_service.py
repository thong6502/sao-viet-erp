"""Danh mục Kho hàng — service CRUD (chỉ khai báo, validate nhẹ)."""
from __future__ import annotations

from ..repositories.kho_hang_repo import KhoHangRepository


class KhoHangError(Exception):
    pass


class KhoHangValidationError(KhoHangError):
    pass


class KhoHangDuplicate(KhoHangError):
    pass


class KhoHangNotFound(KhoHangError):
    pass


class KhoHangService:
    def __init__(self, repo: KhoHangRepository) -> None:
        self.repo = repo

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
            return self.repo.update(dup, {**data, "active": True})
        return self.repo.create(data)

    def update(self, item_id: int, data: dict):
        obj = self.get(item_id)
        self._validate(data)
        if (data.get("ma") or "").strip():          # mã bất biến, nhưng nếu có gửi thì canh trùng
            dup = self.repo.find_by_ma(data["ma"])
            if dup is not None and dup.id != obj.id:
                raise KhoHangDuplicate("Mã kho đã tồn tại.")
        return self.repo.update(obj, data)

    def delete(self, item_id: int) -> None:
        self.repo.delete(self.get(item_id))
