"""Máy thiết bị — service: CRUD + validate (§8).

🔴 `compute_bhr` / `compute_bhr_preview` (đơn giá giờ máy giá vốn) ĐÃ GỠ 11/08/2026 cùng cả khối
cột BHR: form Máy chưa bao giờ có ô nhập cho chúng và không engine giá nào gọi ⇒ luôn chạy trên
dữ liệu rỗng. Xem docstring `models/may_thiet_bi.py`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from ..models.may_thiet_bi import MayThietBi, NhomMay
from ..repositories.may_thiet_bi_repo import MayThietBiRepository
from . import nhat_ky_danh_muc as nk


class MayThietBiError(Exception):
    pass


class MayThietBiValidationError(MayThietBiError):
    pass


class MayThietBiDuplicate(MayThietBiError):
    pass


class MayThietBiNotFound(MayThietBiError):
    pass


def _f(v, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


class MayThietBiService:
    def __init__(self, repo: MayThietBiRepository, audit=None) -> None:
        self.repo = repo
        self.audit = audit

    # -- validate (§8) --
    def _validate(self, data: dict, *, self_id: int | None = None) -> None:
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
        gr, minr = data.get("gripper_mm"), data.get("kho_min_rong")
        if gr and minr and gr >= minr:
            raise MayThietBiValidationError("Nhíp (gripper) ≥ khổ min (rộng). [E-MAY-NHIP]")

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
    def get(self, may_id: int) -> MayThietBi:
        m = self.repo.get(may_id)
        if m is None:
            raise MayThietBiNotFound("Không tìm thấy máy.")
        return m

    def list(self, **kw):
        return self.repo.list(**kw)

    def dem_theo_loai(self, **kw) -> dict[str, int]:
        """Số máy theo loại — cho tab lọc của màn Thiết bị (xem repo)."""
        return self.repo.dem_theo_loai(**kw)

    # -- writes --
    def create(self, data: dict, actor_id: int | None = None) -> MayThietBi:
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise MayThietBiDuplicate("Mã máy đã tồn tại.")
        m = self.repo.create(data)
        nk.ghi_tao(self.audit, actor_id=actor_id, loai="may_thiet_bi", obj=m)
        return m

    def update(self, may_id: int, data: dict, actor_id: int | None = None) -> MayThietBi:
        m = self.get(may_id)
        self._validate(data, self_id=m.id)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != m.id:
            raise MayThietBiDuplicate("Mã máy đã tồn tại.")
        truoc = nk.anh_chup(m)
        m = self.repo.update(m, data)
        nk.ghi_sua(self.audit, actor_id=actor_id, loai="may_thiet_bi", obj=m, truoc=truoc)
        return m

    def delete(self, may_id: int, actor_id: int | None = None) -> None:
        m = self.get(may_id)
        nk.ghi_xoa(self.audit, actor_id=actor_id, loai="may_thiet_bi", obj=m)
        self.repo.delete(m)


# --- Danh mục NHÓM MÁY -------------------------------------------------------


class NhomMayService:
    """Danh sách tên được phép chọn ở ô "Nhóm máy". KHÔNG phải khoá ngoại — xem docstring
    `models.may_thiet_bi.NhomMay`."""

    def __init__(self, db) -> None:
        self.db = db

    def list(self) -> list[NhomMay]:
        return list(
            self.db.execute(
                select(NhomMay).where(NhomMay.active.is_(True)).order_by(NhomMay.ten)
            ).scalars()
        )

    def _tim_theo_ten(self, ten: str) -> NhomMay | None:
        return self.db.execute(select(NhomMay).where(NhomMay.ten == ten)).scalars().first()

    def create(self, ten: str) -> NhomMay:
        ten = (ten or "").strip()
        if not ten:
            raise MayThietBiValidationError("Tên nhóm máy không được trống.")
        if len(ten) > 60:
            raise MayThietBiValidationError("Tên nhóm máy tối đa 60 ký tự.")
        cu = self._tim_theo_ten(ten)
        if cu is not None:
            # Nhóm bị ẩn trước đó thì BẬT LẠI thay vì báo trùng — người dùng gõ đúng tên đó nghĩa
            # là họ muốn nó có mặt, chứ không quan tâm nó từng bị gỡ.
            if not cu.active:
                cu.active = True
                self.db.commit()
                self.db.refresh(cu)
                return cu
            raise MayThietBiDuplicate("Nhóm máy đã tồn tại.")
        row = NhomMay(ten=ten)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def dem_may_dung(self, ten: str) -> int:
        return int(self.db.execute(
            select(func.count()).select_from(MayThietBi).where(MayThietBi.loai_may == ten)
        ).scalar_one())

    def delete(self, nhom_id: int) -> None:
        row = self.db.get(NhomMay, nhom_id)
        if row is None:
            raise MayThietBiNotFound("Không tìm thấy nhóm máy.")
        # 🔴 CHẶN khi còn máy dùng. Bảng này không phải FK nên DB không tự giữ — xoá mù là để lại
        # máy mang tên nhóm không còn tồn tại, và không chỗ nào báo.
        n = self.dem_may_dung(row.ten)
        if n > 0:
            raise MayThietBiValidationError(
                f"Còn {n} máy đang thuộc nhóm “{row.ten}” — đổi nhóm cho các máy đó trước đã."
            )
        self.db.delete(row)
        self.db.commit()
