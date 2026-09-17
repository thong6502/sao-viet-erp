"""Repository — danh mục XE giao hàng và MỨC KHOÁN KM.

Cả hai đều nằm trên nền `CatalogRepo` (CRUD + tìm + phân trang dùng chung với 12 màn danh mục kia),
chỉ khác phần khai cột.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.xe import MucKhoanKm, MucKhoanKmBac, Xe
from .catalog_base import CatalogRepo


class XeRepository(CatalogRepo):
    model = Xe
    fields = ("ten", "tai_trong", "muc_khoan_km_id", "ghi_chu", "active")
    commit_on_write = False   # `XeService` chốt sau khi đã ghi nhật ký — xem `catalog_base`
    # Không có `ma_prefix`: mã xe LÀ BIỂN SỐ, người khai gõ tay. Mã tự sinh ở đây là vô nghĩa.

    def co_xe_dang_dung(self) -> bool:
        """Đã khai chiếc xe nào còn dùng chưa?

        `DeliveryService` dùng cờ này để quyết định có ĐÒI ô Xe lúc đóng chuyến hay không: danh
        mục còn trống mà đã đòi thì ngày triển khai, lúc chưa ai kịp khai xe, mọi chuyến đang chạy
        đều không đóng được. Khai chiếc đầu tiên = bật luật.
        """
        return bool(self.db.execute(
            select(func.count()).select_from(Xe).where(Xe.active.is_(True))
        ).scalar_one())

    def dem_theo_muc(self, muc_id: int) -> int:
        """Số xe đang ăn một mức — để màn cấu hình nói "mức này 3 xe đang dùng" trước khi sửa giá."""
        return int(self.db.execute(
            select(func.count()).select_from(Xe).where(Xe.muc_khoan_km_id == muc_id)
        ).scalar_one() or 0)


class MucKhoanKmRepository:
    """MỨC khoán km — repo THƯỜNG, cố ý KHÔNG dựng trên `CatalogRepo`.

    Nền danh mục xoay quanh cột `ma` (chuẩn hoá mã, tra theo mã, gợi ý mã kế tiếp, sắp theo mã).
    Mức thì khoá nghiệp vụ là CÁI TÊN ("Xe 2 tấn") — nhét thêm một cột `ma` chạy số chỉ để vừa
    khuôn là đẻ ra một mã không ai đọc, rồi màn nào cũng phải hiện nó.

    Mức cũng KHÔNG phải một màn "Cấu hình danh mục": nó là cấu hình CHUNG, sống ở sub-tab riêng
    *Khoán km giao hàng* trong Cấu hình lương (14/09/2026) — sửa giá là việc kế toán, và mức không
    thuộc về phòng ban nào.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, muc_id: int) -> MucKhoanKm | None:
        return self.db.get(MucKhoanKm, muc_id)

    def find_by_ten(self, ten: str) -> MucKhoanKm | None:
        """Tra theo tên, KHÔNG phân biệt hoa/thường — chặn khai "Xe 2 tấn" hai lần."""
        ten = (ten or "").strip()
        if not ten:
            return None
        return self.db.execute(
            select(MucKhoanKm).where(func.lower(MucKhoanKm.ten) == ten.lower())
        ).scalars().first()

    def list(self, *, active: bool | None = None) -> list[MucKhoanKm]:
        """Mọi mức, sắp theo TÊN. Bảng vài dòng, người dùng tự đặt tên nên tự biết thứ tự."""
        q = select(MucKhoanKm)
        if active is not None:
            q = q.where(MucKhoanKm.active.is_(active))
        return list(self.db.execute(q.order_by(MucKhoanKm.ten.asc())).scalars().all())

    def create(self, **fields) -> MucKhoanKm:
        row = MucKhoanKm(**fields)
        self.db.add(row)
        self.db.flush()
        return row

    def update(self, muc: MucKhoanKm, **fields) -> MucKhoanKm:
        for k, v in fields.items():
            setattr(muc, k, v)
        self.db.flush()
        return muc

    def delete(self, muc: MucKhoanKm) -> None:
        # Xoá bậc TƯỜNG MINH dù FK đã `ondelete=CASCADE`: SQLite (DB test) không bật khoá ngoại
        # nên không cascade — dựa vào FK thì test xanh mà bậc mồ côi vẫn nằm lại.
        self.db.execute(MucKhoanKmBac.__table__.delete().where(MucKhoanKmBac.muc_id == muc.id))
        self.db.delete(muc)
        self.db.flush()

    # --- Bảng bậc của mức -----------------------------------------------------------------------
    # Nằm ở repo MỨC chứ không ở repo Giao hàng (14/09/2026): bậc thuộc về mức, mức là cấu hình
    # chung — không còn dính dáng gì tới phòng ban hay tới chuyến giao.
    def bac_cua(self, muc_id: int) -> list[MucKhoanKmBac]:
        """Bảng bậc của một MỨC, xếp theo `seq`. Bậc `up_to_km IS NULL` (∞) luôn ở cuối."""
        return list(self.db.execute(
            select(MucKhoanKmBac)
            .where(MucKhoanKmBac.muc_id == muc_id)
            .order_by(MucKhoanKmBac.seq)
        ).scalars().all())

    def ghi_lai_bac(self, muc_id: int, rows: list[dict]) -> None:
        """Xoá sạch rồi ghi mới — bảng bậc là một khối, sửa cả cụm chứ không từng dòng.

        Vế xoá khoá theo `muc_id`: sai chỗ này là lưu bậc cho một mức thì quét sạch bậc của mọi
        mức khác.
        """
        self.db.execute(MucKhoanKmBac.__table__.delete().where(MucKhoanKmBac.muc_id == muc_id))
        for i, r in enumerate(rows, start=1):
            self.db.add(MucKhoanKmBac(
                muc_id=muc_id, seq=i, up_to_km=r.get("up_to_km"), don_gia=r["don_gia"],
            ))
        self.db.flush()

    def tra_don_gia(self, muc_id: int | None, km: int) -> float | None:
        """Đơn giá của bậc mà `km` rơi vào, trong bảng bậc của MỨC.

        None = không có mức, hoặc mức chưa khai bậc nào. Từ 14/09/2026 cả hai ca đó đều bị CHẶN
        từ trước khi tới đây (xe bắt buộc có mức; lên đơn bằng mức rỗng bị chặn) — None chỉ còn
        lọt tới với chuyến CŨ chạy trước khi có tính năng.

        Bậc đầu tiên (theo seq) có `km ≤ up_to_km` thắng; `up_to_km IS NULL` là bậc ∞ nên luôn
        khớp — miễn nó đứng cuối, mà `ghi_lai_bac` đánh seq theo thứ tự người dùng xếp và service
        đã kiểm cấu trúc trước khi ghi.
        """
        if muc_id is None:
            return None
        rows = self.bac_cua(muc_id)
        if not rows:
            return None
        for b in rows:
            if b.up_to_km is None or int(km) <= b.up_to_km:
                return float(b.don_gia)
        # Không có bậc ∞ và km vượt mọi trần: dùng bậc cao nhất — thà trả hơn là trả 0 âm thầm.
        return float(rows[-1].don_gia)
