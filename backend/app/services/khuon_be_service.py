"""Danh mục Khuôn bế — service CRUD (chỉ khai báo, validate nhẹ)."""
from __future__ import annotations

from ..models.khuon_be import TINH_TRANG
from ..repositories.khuon_be_repo import KhuonBeRepository


class KhuonBeError(Exception):
    pass


class KhuonBeValidationError(KhuonBeError):
    pass


class KhuonBeDuplicate(KhuonBeError):
    pass


class KhuonBeNotFound(KhuonBeError):
    pass


class KhuonBeService:
    def __init__(self, repo: KhuonBeRepository) -> None:
        self.repo = repo

    def _validate(self, data: dict) -> None:
        if not (data.get("ten") or "").strip():
            raise KhuonBeValidationError("Tên khuôn không được trống.")
        tt = data.get("tinh_trang")
        if tt is not None and tt not in TINH_TRANG:
            raise KhuonBeValidationError("Tình trạng khuôn không hợp lệ.")

    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise KhuonBeNotFound("Không tìm thấy khuôn bế.")
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def create(self, data: dict, created_by: int | None = None):
        self._validate(data)
        # Mã sinh NGẦM: UI không cho gõ mã tay. Không truyền mã → tự cấp KB-#### trên mọi
        # hàng (kể cả xóa mềm) nên luôn là mã mới, không đụng ai.
        if not (data.get("ma") or "").strip():
            data = {**data, "ma": self.repo.next_ma()}
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None:
            # Trùng khuôn ĐANG hoạt động = trùng thật → chặn.
            if dup.active:
                raise KhuonBeDuplicate("Mã khuôn đã tồn tại.")
            # Trùng khuôn ĐÃ XÓA MỀM (chỉ khi mã truyền tay qua API) → tái dùng đúng hàng:
            # ghi đè dữ liệu mới + bật lại active, không đẻ hàng rác.
            return self.repo.update(dup, {**data, "active": True})
        return self.repo.create(data)

    def update(self, item_id: int, data: dict):
        obj = self.get(item_id)
        self._validate(data)
        if (data.get("ma") or "").strip():          # mã bất biến, nhưng nếu có gửi thì canh trùng
            dup = self.repo.find_by_ma(data["ma"])
            if dup is not None and dup.id != obj.id:
                raise KhuonBeDuplicate("Mã khuôn đã tồn tại.")
        return self.repo.update(obj, data)

    def delete(self, item_id: int) -> None:
        self.repo.delete(self.get(item_id))
