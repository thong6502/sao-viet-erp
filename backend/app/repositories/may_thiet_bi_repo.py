"""Repository — Máy thiết bị. CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.don_vi_do import DonViDo
from ..models.may_thiet_bi import MayThietBi, NhomMay
from .catalog_base import CatalogRepo

# Field client được phép gán (ma chuẩn hoá riêng; id/created/updated do server quản).
# Dọn 11/08/2026: chỉ còn cột CÓ Ô NHẬP trên form Máy. Xem docstring `models/may_thiet_bi.py`
# cho danh sách đã gỡ và lý do.
ASSIGNABLE = (
    "ten", "loai_may", "hang_san_xuat", "model", "so_seri", "ghi_chu",
    "toc_do", "toc_do_min", "toc_do_max", "don_vi_toc_do", "cong_thuc_luong",
    "makeready_time_default",
    "so_nhan_cong",
    "kho_max_dai", "kho_max_rong", "kho_min_dai", "kho_min_rong",
    "kho_kem_dai", "kho_kem_rong", "vung_in_dai", "vung_in_rong", "gripper_mm", "nhip_giay_mm",
    "le_hong_mm", "duoi_thang_mau_mm",
    "fields_theo_loai", "active",
)


class MayThietBiRepository(CatalogRepo):
    model = MayThietBi
    fields = ASSIGNABLE
    commit_on_write = False   # `MayThietBiService` chốt sau khi ghi nhật ký — xem `catalog_base`
    # `active` (mg `0202`, 15/08/2026) = máy CÒN DÙNG hay đã thanh lý. Khác `machine_unavailable_
    # periods` — chỗ đó khai máy dừng TẠM theo khoảng thời gian, và Xếp lịch vẫn đọc nó như cũ.

    def extra_conds(self, *, loai_may: str | None = None, **_) -> list:
        return [MayThietBi.loai_may == loai_may] if loai_may else []

    def all_ids(self) -> list[int]:
        """Id của MỌI máy — cột "Trạng thái" của màn Thiết bị hỏi trạng thái cả danh mục một lượt.

        Trước 15/08/2026 câu `select()` này nằm thẳng trong `routers/may_thiet_bi.trang_thai`.
        """
        return [int(i) for i in self.db.execute(select(MayThietBi.id)).scalars()]

    def dem_theo_loai(self, *, q: str | None = None,
                      active: bool | None = None) -> dict[str, int]:
        """Số máy của TỪNG loại — số hiện trên tab lọc của màn Thiết bị.

        Cố ý KHÔNG áp điều kiện `loai_may`: tab nào cũng phải khoe số của nó, kể cả tab đang
        không được chọn. `q` thì CÓ áp — đang tìm "KOMORI" mà tab vẫn khoe số cả danh mục là
        nói dối. Một câu GROUP BY thay cho cách cũ (màn kéo cả bảng về rồi tự đếm trong JS).

        `active` cũng CÓ áp (mg `0202`): đang xem "mục đã ngừng" mà tab vẫn khoe số của máy còn
        dùng thì bảng một đằng, số trên tab một nẻo — y như `khuon_be_repo.dem_theo_tinh_trang`.
        """
        stmt = select(MayThietBi.loai_may, func.count()).group_by(MayThietBi.loai_may)
        loc = self._loc_q(q)
        if loc is not None:
            stmt = stmt.where(loc)
        if active is not None:
            stmt = stmt.where(MayThietBi.active.is_(active))
        # Máy CHƯA khai loại gom vào khoá rỗng "" thay vì bị loại: màn cộng các số này ra tổng
        # cho tab "Tất cả", bỏ nhóm khuyết đi là tab đó hụt số mà không ai biết vì sao.
        return {(str(loai).strip() if loai is not None else ""): int(n)
                for loai, n in self.db.execute(stmt)}

    def don_vi_ten(self) -> dict[str, str]:
        """`{mã đơn vị: tên}` cho CẢ danh mục Đơn vị — một truy vấn cho cả trang, không N+1.

        Cùng cách `cong_doan_repo.don_vi_ten()` làm. Bảng máy chỉ lưu MÃ đơn vị tốc độ (`to_gio`,
        `m_phut`) mà mã không đọc được thành lời; tên phải tra ở danh mục Đơn vị.
        """
        return {
            (ma or "").strip().lower(): ten
            for ma, ten in self.db.execute(select(DonViDo.ma, DonViDo.ten)).all()
        }


class NhomMayRepository:
    """Danh mục NHÓM MÁY — bảng phẳng, KHÔNG kế thừa `CatalogRepo`.

    `nhom_may` không có cột `ma` (khoá nghiệp vụ là chính `ten`, unique) nên nền danh mục — vốn
    xoay quanh mã + `next_ma` + chuẩn hoá hoa/thường — không áp vào được. Ở đây chỉ cần bốn câu
    truy vấn, gom về repo để `NhomMayService` thôi truy DB thẳng.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, nhom_id: int) -> NhomMay | None:
        return self.db.get(NhomMay, nhom_id)

    def list_active(self) -> list[NhomMay]:
        return list(self.db.execute(
            select(NhomMay).where(NhomMay.active.is_(True)).order_by(NhomMay.ten)
        ).scalars())

    def find_by_ten(self, ten: str) -> NhomMay | None:
        return self.db.execute(select(NhomMay).where(NhomMay.ten == ten)).scalars().first()

    def create(self, ten: str) -> NhomMay:
        row = NhomMay(ten=ten)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def bat_lai(self, row: NhomMay) -> NhomMay:
        row.active = True
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, row: NhomMay) -> None:
        self.db.delete(row)
        self.db.commit()

    def dem_may_dung(self, ten: str) -> int:
        return int(self.db.execute(
            select(func.count()).select_from(MayThietBi).where(MayThietBi.loai_may == ten)
        ).scalar_one())

    def dem_cong_doan_cho_phep(self, ten: str) -> int:
        """Số công đoạn có tên nhóm này trong `nhom_may_cho_phep`.

        Cột đó là JSON list TÊN nhóm — không query bằng SQL cho mọi phương ngữ nên lọc trong
        Python; bảng công đoạn nhỏ (vài chục dòng).
        """
        from ..models.cong_doan import CongDoan

        return sum(
            1 for cd in self.db.execute(select(CongDoan)).scalars()
            if isinstance(cd.nhom_may_cho_phep, list) and ten in cd.nhom_may_cho_phep
        )
