"""Danh mục Khuôn bế — service CRUD (chỉ khai báo, validate nhẹ)."""
from __future__ import annotations

from ..models.khuon_be import TINH_TRANG
from ..repositories.khuon_be_repo import KhuonBeRepository
from . import nhat_ky_danh_muc as nk


class KhuonBeError(Exception):
    pass


class KhuonBeValidationError(KhuonBeError):
    pass


class KhuonBeDuplicate(KhuonBeError):
    pass


class KhuonBeNotFound(KhuonBeError):
    pass


class KhuonBeService:
    def __init__(self, repo: KhuonBeRepository, audit=None) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(self, data: dict) -> None:
        if not (data.get("ten") or "").strip():
            raise KhuonBeValidationError("Tên khuôn không được trống.")
        tt = data.get("tinh_trang")
        if tt is not None and tt not in TINH_TRANG:
            raise KhuonBeValidationError("Tình trạng khuôn không hợp lệ.")
        # `dang_dat_lam` mà không có ngày về thì bàn lịch không trả lời được câu duy nhất đáng hỏi
        # ("khuôn về KỊP giờ bế chưa?") — nó sẽ phải ĐOÁN, mà đoán ở đây là cho xếp bế vào ngày
        # chưa có khuôn. Bắt khai luôn thay vì để trống rồi im lặng.
        if tt == "dang_dat_lam" and not data.get("ngay_ve_du_kien"):
            raise KhuonBeValidationError(
                "Khuôn đang đặt làm phải khai NGÀY VỀ DỰ KIẾN — bàn xếp lịch cần số này để biết "
                "khuôn có kịp giờ bế không."
            )

    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise KhuonBeNotFound("Không tìm thấy khuôn bế.")
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def dem_theo_tinh_trang(self, **kw) -> dict[str, int]:
        """Số khuôn theo tình trạng — cho tab lọc của màn Khuôn bế (xem repo)."""
        return self.repo.dem_theo_tinh_trang(**kw)

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
            obj = self.repo.update(dup, {**data, "active": True})
            nk.ghi_tao(self.audit, actor_id=created_by, loai="khuon_be", obj=obj)
            return obj
        obj = self.repo.create(data)
        nk.ghi_tao(self.audit, actor_id=created_by, loai="khuon_be", obj=obj)
        return obj

    def update(self, item_id: int, data: dict, actor_id: int | None = None):
        obj = self.get(item_id)
        self._validate(data)
        if (data.get("ma") or "").strip():          # mã bất biến, nhưng nếu có gửi thì canh trùng
            dup = self.repo.find_by_ma(data["ma"])
            if dup is not None and dup.id != obj.id:
                raise KhuonBeDuplicate("Mã khuôn đã tồn tại.")
        truoc = nk.anh_chup(obj)
        obj = self.repo.update(obj, data)
        nk.ghi_sua(self.audit, actor_id=actor_id, loai="khuon_be", obj=obj, truoc=truoc)
        return obj

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        obj = self.get(item_id)
        nk.ghi_xoa(self.audit, actor_id=actor_id, loai="khuon_be", obj=obj)
        self.repo.delete(obj)
