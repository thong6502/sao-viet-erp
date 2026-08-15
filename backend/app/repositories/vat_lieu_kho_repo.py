"""Repository — Danh mục Giấy & Vật tư (chủng loại giấy / giấy / vật tư in ấn). CRUD generic."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.vat_lieu_kho import ChungLoaiGiay, GiayGiaVersion, GiayNguyen, VatTuInAn
from .catalog_base import CatalogRepo

# Các trường "ảnh chụp" của 1 phiên bản giá giấy (khớp cột GiayGiaVersion + GiayNguyen).
VERSION_SNAPSHOT = ("kho_dai", "kho_rong", "gsm", "caliper_micron", "tho",
                    "don_vi_gia", "don_gia", "gia_thi_truong")


# Cả ba tắt `commit_on_write`: `VatLieuKhoService` chốt SAU khi đã ghi nhật ký, để audit nổ thì
# bản ghi cũng không lọt vào DB (xem `services/catalog_base`).
class _ChungLoaiGiayRepo(CatalogRepo):
    model = ChungLoaiGiay
    fields = ("ten", "mo_ta", "active")
    commit_on_write = False


class _GiayRepo(CatalogRepo):
    model = GiayNguyen
    fields = ("ten", "chung_loai_giay_id", "gsm", "caliper_micron",
              "tho", "don_vi_gia", "don_gia", "gia_thi_truong", "kho_tinh_gia", "ghi_chu",
              "active", "cong_thuc_gia", "cong_thuc_luong")
    commit_on_write = False


class _VatTuRepo(CatalogRepo):
    model = VatTuInAn
    fields = ("ten", "don_vi_gia", "don_gia", "ghi_chu", "active", "cong_thuc_gia",
              "cong_thuc_luong")
    commit_on_write = False


_REPOS = {
    "chung_loai_giay": _ChungLoaiGiayRepo,
    "giay": _GiayRepo,
    "vat_tu": _VatTuRepo,
}


class VatLieuKhoRepository:
    """Ba danh mục một cửa — nơi gọi truyền `kind` thay vì cầm ba repo riêng.

    KHÔNG kế thừa `CatalogRepo`: nền đó buộc MỘT model cho cả lớp, còn ở đây model đổi theo
    TỪNG lời gọi (router `_make_crud` sinh CRUD cho ba đường `/chung-loai-giay`, `/giay`,
    `/vat-tu-in-an`). Nên lớp này giữ nguyên chữ ký có `kind` và ủy quyền xuống ba repo con —
    phần thân CRUD vẫn dùng chung một bản ở `catalog_base`, không chép lại lần thứ ba.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._con: dict[str, CatalogRepo] = {k: cls(db) for k, cls in _REPOS.items()}

    def _r(self, kind: str) -> CatalogRepo:
        if kind not in self._con:
            raise ValueError(f"loại danh mục không hợp lệ: {kind}")
        return self._con[kind]

    def get(self, kind: str, item_id: int):
        return self._r(kind).get(item_id)

    def by_ids(self, kind: str, ids) -> list:
        """Nạp NHIỀU bản ghi trong 1 query — kho serialize cả trang nên tra lẻ là N+1."""
        model = self._r(kind).model
        ids = [int(i) for i in set(ids or []) if i]
        if not ids:
            return []
        return list(self.db.execute(select(model).where(model.id.in_(ids))).scalars())

    def find_by_ma(self, kind: str, ma: str):
        return self._r(kind).find_by_ma(ma)

    def list(self, kind: str, *, q: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50):
        return self._r(kind).list(q=q, active=active, page=page, size=size)

    def create(self, kind: str, data: dict):
        return self._r(kind).create(data)

    def update(self, obj, kind: str, data: dict):
        return self._r(kind).update(obj, data)

    def set_anh(self, obj, url: str | None):
        """Ghi RIÊNG `anh_url` (ảnh minh hoạ) — không đụng ma/tên nên không qua `update`/validate."""
        obj.anh_url = url
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj) -> None:
        """Chỉ `flush()` — nơi gọi chốt bằng `chot_giao_dich()` sau khi đã ghi nhật ký."""
        self.db.delete(obj)
        self.db.flush()

    def chot_giao_dich(self) -> None:
        """Chốt giao dịch cho `VatLieuKhoService` — nó làm chủ giao dịch của ba danh mục này.

        Có mặt để service KHÔNG phải với tay vào `repo.db` mà commit (trước 15/08/2026
        `add_giay_version` gọi thẳng `self.repo.db.commit()`).
        """
        self.db.commit()

    # -- Phiên bản giá giấy (lịch sử) --
    def has_versions(self, giay_id: int) -> bool:
        return self.db.execute(
            select(GiayGiaVersion.id).where(GiayGiaVersion.giay_id == giay_id).limit(1)
        ).first() is not None

    def list_versions(self, giay_id: int):
        return list(self.db.execute(
            select(GiayGiaVersion).where(GiayGiaVersion.giay_id == giay_id)
            .order_by(GiayGiaVersion.version_no.desc())
        ).scalars())

    def create_version(self, giay_id: int, fields: dict, *, ngay_hieu_luc=None,
                       ghi_chu: str | None = None, created_by: int | None = None):
        # Bỏ cờ hiện hành ở các version cũ.
        for v in self.db.execute(
            select(GiayGiaVersion).where(
                GiayGiaVersion.giay_id == giay_id, GiayGiaVersion.is_current.is_(True))
        ).scalars():
            v.is_current = False
        next_no = (self.db.execute(
            select(func.max(GiayGiaVersion.version_no)).where(GiayGiaVersion.giay_id == giay_id)
        ).scalar() or 0) + 1
        obj = GiayGiaVersion(giay_id=giay_id, version_no=next_no, is_current=True,
                             ngay_hieu_luc=ngay_hieu_luc, ghi_chu=ghi_chu, created_by=created_by)
        for k in VERSION_SNAPSHOT:
            if k in fields and fields[k] is not None:
                setattr(obj, k, fields[k])
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
