"""Máy thiết bị — service: CRUD + validate (§8).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.

"""
from __future__ import annotations

from decimal import Decimal

from ..models.may_thiet_bi import MayThietBi, NhomMay, la_nhom_khoa
from ..repositories.may_thiet_bi_repo import MayThietBiRepository, NhomMayRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)


class MayThietBiError(CatalogError):
    pass


class MayThietBiValidationError(MayThietBiError, CatalogValidationError):
    pass


class MayThietBiDuplicate(MayThietBiError, CatalogDuplicate):
    pass


class MayThietBiNotFound(MayThietBiError, CatalogNotFound):
    pass


def _f(v, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


class MayThietBiService(CatalogService):
    LOAI = "may_thiet_bi"
    E_NOT_FOUND = MayThietBiNotFound
    E_DUPLICATE = MayThietBiDuplicate
    E_VALIDATION = MayThietBiValidationError
    MSG_NOT_FOUND = "Không tìm thấy máy."
    MSG_DUPLICATE = "Mã máy đã tồn tại."

    def __init__(self, repo: MayThietBiRepository, audit=None) -> None:
        super().__init__(repo, audit)

    # -- validate (§8) --
    def _validate(self, data: dict, obj: MayThietBi | None = None) -> None:
        if not (data.get("ma") or "").strip():
            raise MayThietBiValidationError("Mã máy không được trống.")
        if not (data.get("ten") or "").strip():
            raise MayThietBiValidationError("Tên máy không được trống.")
        if not (data.get("loai_may") or "").strip():
            raise MayThietBiValidationError("Nhóm máy không được để trống.")
        kmaxd, kmaxr = data.get("kho_max_dai"), data.get("kho_max_rong")
        kmind, kminr = data.get("kho_min_dai"), data.get("kho_min_rong")
        if kmind and kmaxd and kmind > kmaxd:
            raise MayThietBiValidationError("Khổ min (dài) > khổ max. [E-MAY-KHO]")
        if kminr and kmaxr and kminr > kmaxr:
            raise MayThietBiValidationError("Khổ min (rộng) > khổ max. [E-MAY-KHO]")

        toc_do = data.get("toc_do")
        dvtd = data.get("don_vi_toc_do")
        if toc_do is not None and _f(toc_do) <= 0:
            raise MayThietBiValidationError("Tốc độ phải > 0. [E-MAY-SPEED]")
        # Dải tốc độ: chỉ kiểm những ô ĐÃ khai. Không ép khai đủ ba — khai mỗi trung bình là
        # trường hợp thường gặp nhất, bắt điền đủ chỉ tổ làm người ta gõ số bừa cho qua.
        td_min, td_max = data.get("toc_do_min"), data.get("toc_do_max")
        for nhan, v in (("tối thiểu", td_min), ("tối đa", td_max)):
            if v is not None and _f(v) <= 0:
                raise MayThietBiValidationError(f"Tốc độ {nhan} phải > 0. [E-MAY-SPEED]")
        if td_min is not None and td_max is not None and _f(td_min) > _f(td_max):
            raise MayThietBiValidationError(
                "Tốc độ tối thiểu > tối đa. [E-MAY-SPEED-RANGE]")
        if toc_do is not None:
            if td_min is not None and _f(td_min) > _f(toc_do):
                raise MayThietBiValidationError(
                    "Tốc độ tối thiểu > tốc độ trung bình. [E-MAY-SPEED-RANGE]")
            if td_max is not None and _f(td_max) < _f(toc_do):
                raise MayThietBiValidationError(
                    "Tốc độ tối đa < tốc độ trung bình. [E-MAY-SPEED-RANGE]")
        _ = dvtd  # đơn vị tốc độ khớp loai_may — cảnh báo mềm, không chặn ở MVP.

    # -- reads --
    def dem_theo_loai(self, **kw) -> dict[str, int]:
        """Số máy theo loại — cho tab lọc của màn Thiết bị (xem repo)."""
        return self.repo.dem_theo_loai(**kw)

    def gan_ten_don_vi(self, items) -> None:
        """Điền TÊN đơn vị tốc độ cho cả trang bằng MỘT truy vấn.

        Bảng máy chỉ lưu MÃ (`to_gio`, `m_phut`) mà mã không đọc được thành lời. Gán ở server
        chứ không để frontend tự tra — cùng lý do đã chốt cho Giấy · Vật tư
        (`vat_lieu_kho_service.gan_ten_don_vi`) và Công đoạn: bảng nhãn cứng ở FE sớm muộn lệch
        với danh mục, và xưởng đổi tên đơn vị thì cả hai chỗ phải đổi theo.

        ⚠️ Field `don_vi_toc_do_ten` PHẢI có mặt trong `schemas.may_thiet_bi.MayThietBiRow`, nếu
        không Pydantic nuốt im lặng và FE nhận `undefined` mà chẳng có lỗi nào.
        """
        ten = self.repo.don_vi_ten()
        for it in items:
            ma = (getattr(it, "don_vi_toc_do", None) or "").strip().lower()
            it.don_vi_toc_do_ten = ten.get(ma) if ma else None


# --- Danh mục NHÓM MÁY -------------------------------------------------------


class NhomMayService:
    """Danh sách tên được phép chọn ở ô "Nhóm máy". KHÔNG phải khoá ngoại — xem docstring
    `models.may_thiet_bi.NhomMay`.

    KHÔNG dùng `CatalogService`: bảng này không có cột `ma`, không có `update`, và `create` nhận
    một CHUỖI chứ không phải dict. Ép vào nền chỉ để "cho đồng bộ" là đẻ ra ba cờ mà mỗi cờ đúng
    một nơi dùng.
    """

    def __init__(self, repo: NhomMayRepository) -> None:
        self.repo = repo

    def list(self) -> list[NhomMay]:
        return self.repo.list_active()

    def create(self, ten: str) -> NhomMay:
        ten = (ten or "").strip()
        if not ten:
            raise MayThietBiValidationError("Tên nhóm máy không được trống.")
        if len(ten) > 60:
            raise MayThietBiValidationError("Tên nhóm máy tối đa 60 ký tự.")
        cu = self.repo.find_by_ten(ten)
        if cu is not None:
            # Nhóm bị ẩn trước đó thì BẬT LẠI thay vì báo trùng — người dùng gõ đúng tên đó nghĩa
            # là họ muốn nó có mặt, chứ không quan tâm nó từng bị gỡ.
            if not cu.active:
                return self.repo.bat_lai(cu)
            raise MayThietBiDuplicate("Nhóm máy đã tồn tại.")
        return self.repo.create(ten)

    def dem_may_dung(self, ten: str) -> int:
        return self.repo.dem_may_dung(ten)

    def dem_cong_doan_cho_phep(self, ten: str) -> int:
        return self.repo.dem_cong_doan_cho_phep(ten)

    def delete(self, nhom_id: int) -> None:
        row = self.repo.get(nhom_id)
        if row is None:
            raise MayThietBiNotFound("Không tìm thấy nhóm máy.")
        if la_nhom_khoa(row.ten):
            raise MayThietBiValidationError(
                f"“{row.ten}” là nhóm hệ thống — cả bình bài và tính giá bám vào nó, "
                "không xoá được."
            )
        ly_do = []
        if (n := self.dem_may_dung(row.ten)) > 0:
            ly_do.append(f"{n} máy đang thuộc nhóm này")
        if (m := self.dem_cong_doan_cho_phep(row.ten)) > 0:
            ly_do.append(f"{m} công đoạn khai nhóm này ở ô “Máy làm được công đoạn này”")
        if ly_do:
            raise MayThietBiValidationError(
                f"Không xóa được nhóm “{row.ten}” — còn: {' · '.join(ly_do)}."
            )
        self.repo.delete(row)
