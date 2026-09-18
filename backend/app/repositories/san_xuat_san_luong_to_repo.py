"""Data-access cho tab SẢN LƯỢNG của Bàn tổ (spec 2026-09-14 §6).

Đọc mẻ (`san_xuat_batch`) + bản chia (`san_xuat_phan_bo` / `_dong`) theo PHẠM VI TỔ của người xem:

  · tổ thấy TRỌN (`tron`) — mọi mẻ của công việc thuộc tổ, số tốt/hỏng của mẻ + dòng chia từng người;
  · tổ chỉ thấy CỦA TÔI (`rieng`) — chỉ dòng chia ĐÃ CHỐT của chính nhân viên người xem (bản nháp
    còn đổi theo chấm công, công nhân chưa được xem — §12.3).

Lọc ngày theo GIỜ BẮT ĐẦU MẺ (UTC thật, service quy khoảng ngày giờ xưởng ra hai mốc UTC). Gom theo
nguồn LỆNH/BÀI GHÉP cùng luật bàn tổ (`SanXuatRepository._khoa_lenh_cols`), cắt trang + cộng tổng ở
SQL — kéo cả tháng mẻ về rồi cộng bằng Python là mỗi lần mở tab đọc cả bảng.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from ..models.bai_ghep import BaiGhep
from ..models.employee import Employee
from ..models.lsx import Lsx
from ..models.san_xuat import SanXuatCongViec
from ..models.san_xuat_phan_bo import PB_DA_CHOT, SanXuatPhanBo, SanXuatPhanBoDong
from ..models.san_xuat_san_luong import SanXuatBatch


def _khoa_nguon():
    """(loại, id) nguồn của công việc — bài ghép THẮNG lệnh, y hệt bàn tổ."""
    co_bg = SanXuatCongViec.bai_ghep_id.is_not(None)
    return (
        case((co_bg, literal("bai_ghep")), else_=literal("lsx")),
        case((co_bg, SanXuatCongViec.bai_ghep_id), else_=SanXuatCongViec.lsx_id),
    )


class SanXuatSanLuongToRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- điều kiện dùng chung ----------------------------------------------------------------
    @staticmethod
    def _dong_cua_toi(employee_id: int, rieng: set[int]):
        """Dòng chia ĐÃ CHỐT của chính mình thuộc phạm vi `rieng` — theo tổ của công việc, hoặc tổ
        GỐC ghi trên dòng hỗ trợ chéo (thợ đi hỗ trợ tổ khác vẫn thấy phần của mình)."""
        return and_(
            SanXuatPhanBoDong.employee_id == employee_id,
            SanXuatPhanBo.trang_thai == PB_DA_CHOT,
            or_(
                SanXuatCongViec.department_id.in_(rieng),
                SanXuatPhanBoDong.department_id.in_(rieng),
            ),
        )

    def _dk_chung(self, tu: datetime, den: datetime, tim: str | None) -> list:
        dk = [SanXuatBatch.bat_dau >= tu, SanXuatBatch.bat_dau < den]
        kw = (tim or "").strip()
        if kw:
            mau = f"%{kw}%"
            dk.append(or_(
                Lsx.ma.ilike(mau), Lsx.ten.ilike(mau), BaiGhep.ma.ilike(mau), BaiGhep.ten.ilike(mau),
            ))
        return dk

    @staticmethod
    def _nen(*cot):
        return (
            select(*cot)
            .select_from(SanXuatBatch)
            .join(SanXuatCongViec, SanXuatBatch.cong_viec_id == SanXuatCongViec.id)
            .outerjoin(Lsx, SanXuatCongViec.lsx_id == Lsx.id)
            .outerjoin(BaiGhep, SanXuatCongViec.bai_ghep_id == BaiGhep.id)
        )

    def _pham_vi(self, tron: set[int], rieng: set[int], employee_id: int | None):
        """Mẻ lọt phạm vi: thuộc tổ trọn, HOẶC có dòng chia đã chốt của mình trong phạm vi riêng.
        None = không thấy gì."""
        nhanh = []
        if tron:
            nhanh.append(SanXuatCongViec.department_id.in_(tron))
        if rieng and employee_id is not None:
            nhanh.append(exists(
                select(SanXuatPhanBoDong.id)
                .join(SanXuatPhanBo, SanXuatPhanBoDong.phan_bo_id == SanXuatPhanBo.id)
                .where(SanXuatPhanBo.batch_id == SanXuatBatch.id,
                       self._dong_cua_toi(employee_id, rieng))
            ))
        if not nhanh:
            return None
        return nhanh[0] if len(nhanh) == 1 else or_(*nhanh)

    # --- trang lệnh ---------------------------------------------------------------------------
    def trang_nguon(
        self, *, tron: set[int], rieng: set[int], employee_id: int | None,
        tu: datetime, den: datetime, tim: str | None, trang: int, co_trang: int,
    ) -> tuple[list[tuple[str, int | None]], int]:
        """Một trang khoá nguồn (loại, id), mới hoạt động gần nhất lên đầu, + tổng số nguồn."""
        pv = self._pham_vi(tron, rieng, employee_id)
        if pv is None:
            return [], 0
        loai, nid = _khoa_nguon()
        moi_nhat = func.max(SanXuatBatch.bat_dau)
        nhom = (
            self._nen(loai.label("loai"), nid.label("nid"), moi_nhat.label("moi"))
            .where(pv, *self._dk_chung(tu, den, tim))
            .group_by(loai, nid)
        )
        tong = self.db.scalar(select(func.count()).select_from(nhom.subquery())) or 0
        rows = self.db.execute(
            nhom.order_by(moi_nhat.desc(), nid).limit(co_trang).offset((trang - 1) * co_trang)
        ).all()
        return [(r.loai, r.nid) for r in rows], int(tong)

    def me_cua_nguon(
        self, khoa: list[tuple[str, int | None]], *, tron: set[int], rieng: set[int],
        employee_id: int | None, tu: datetime, den: datetime,
    ) -> list[tuple[SanXuatBatch, SanXuatCongViec]]:
        """Mọi mẻ (kèm công việc) của các nguồn trong trang, cùng phạm vi + khoảng ngày."""
        pv = self._pham_vi(tron, rieng, employee_id)
        if pv is None or not khoa:
            return []
        bg_ids = {i for l, i in khoa if l == "bai_ghep" and i is not None}
        lsx_ids = {i for l, i in khoa if l == "lsx" and i is not None}
        theo_nguon = []
        if bg_ids:
            theo_nguon.append(SanXuatCongViec.bai_ghep_id.in_(bg_ids))
        if lsx_ids:
            theo_nguon.append(and_(SanXuatCongViec.bai_ghep_id.is_(None),
                                   SanXuatCongViec.lsx_id.in_(lsx_ids)))
        if any(i is None for _, i in khoa):
            theo_nguon.append(and_(SanXuatCongViec.bai_ghep_id.is_(None),
                                   SanXuatCongViec.lsx_id.is_(None)))
        return [
            (b, cv) for b, cv in self.db.execute(
                select(SanXuatBatch, SanXuatCongViec)
                .join(SanXuatCongViec, SanXuatBatch.cong_viec_id == SanXuatCongViec.id)
                .where(pv, or_(*theo_nguon),
                       SanXuatBatch.bat_dau >= tu, SanXuatBatch.bat_dau < den)
                .order_by(SanXuatBatch.bat_dau, SanXuatBatch.id)
            ).all()
        ]

    def dong_chia(self, batch_ids: set[int]) -> list[tuple[int, str, str | None, SanXuatPhanBoDong]]:
        """(batch_id, trạng thái bản chia, đơn vị trả lương, dòng) của các mẻ."""
        if not batch_ids:
            return []
        return [
            (r[0], r[1], r[2], r[3]) for r in self.db.execute(
                select(SanXuatPhanBo.batch_id, SanXuatPhanBo.trang_thai,
                       SanXuatPhanBo.don_vi_tra_luong, SanXuatPhanBoDong)
                .join(SanXuatPhanBo, SanXuatPhanBoDong.phan_bo_id == SanXuatPhanBo.id)
                .where(SanXuatPhanBo.batch_id.in_(batch_ids))
                .order_by(SanXuatPhanBoDong.id)
            ).all()
        ]

    def batch_co_ban_chia(self, batch_ids: set[int]) -> set[int]:
        if not batch_ids:
            return set()
        return set(self.db.scalars(
            select(SanXuatPhanBo.batch_id).where(SanXuatPhanBo.batch_id.in_(batch_ids))
        ))

    # --- tổng của CẢ bộ lọc (không chỉ trang) -------------------------------------------------
    def tong_tron(
        self, *, tron: set[int], tu: datetime, den: datetime, tim: str | None,
    ) -> list[tuple[str, float, float, int]]:
        """(đơn vị, tổng tốt, tổng hỏng, số mẻ) của phần thấy trọn — gộp theo ĐƠN VỊ, không cộng lẫn."""
        if not tron:
            return []
        rows = self.db.execute(
            self._nen(SanXuatBatch.don_vi, func.sum(SanXuatBatch.tot), func.sum(SanXuatBatch.hong),
                      func.count(SanXuatBatch.id))
            .where(SanXuatCongViec.department_id.in_(tron), *self._dk_chung(tu, den, tim))
            .group_by(SanXuatBatch.don_vi)
            .order_by(SanXuatBatch.don_vi)
        ).all()
        return [(dv, float(t or 0), float(h or 0), int(n or 0)) for dv, t, h, n in rows]

    def tong_cua_toi(
        self, *, tron: set[int], rieng: set[int], employee_id: int | None, tu: datetime,
        den: datetime, tim: str | None,
    ) -> list[tuple[str | None, float]]:
        """(đơn vị trả lương, tổng đã chốt) phần của chính mình trong phạm vi riêng — trừ mẻ của tổ
        đã thấy trọn (mẻ đó hiện số tổ, không hiện "phần của tôi", tổng phải khớp dòng)."""
        if not rieng or employee_id is None:
            return []
        dk = [self._dong_cua_toi(employee_id, rieng), *self._dk_chung(tu, den, tim)]
        if tron:
            dk.append(or_(SanXuatCongViec.department_id.is_(None),
                          SanXuatCongViec.department_id.not_in(tron)))
        rows = self.db.execute(
            self._nen(SanXuatPhanBo.don_vi_tra_luong, func.sum(SanXuatPhanBoDong.so_luong_tra_luong))
            .join(SanXuatPhanBo, SanXuatPhanBo.batch_id == SanXuatBatch.id)
            .join(SanXuatPhanBoDong, SanXuatPhanBoDong.phan_bo_id == SanXuatPhanBo.id)
            .where(*dk)
            .group_by(SanXuatPhanBo.don_vi_tra_luong)
            .order_by(SanXuatPhanBo.don_vi_tra_luong)
        ).all()
        return [(dv, float(t or 0)) for dv, t in rows]

    # --- nhãn ---------------------------------------------------------------------------------
    def nhan_nguon(self, khoa: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], tuple[str, str]]:
        ket: dict[tuple[str, int | None], tuple[str, str]] = {}
        lsx_ids = {i for l, i in khoa if l == "lsx" and i is not None}
        bg_ids = {i for l, i in khoa if l == "bai_ghep" and i is not None}
        if lsx_ids:
            for i, ma, ten in self.db.execute(select(Lsx.id, Lsx.ma, Lsx.ten).where(Lsx.id.in_(lsx_ids))):
                ket[("lsx", i)] = (ma or "", ten or "")
        if bg_ids:
            for i, ma, ten in self.db.execute(
                select(BaiGhep.id, BaiGhep.ma, BaiGhep.ten).where(BaiGhep.id.in_(bg_ids))
            ):
                ket[("bai_ghep", i)] = (ma or "", ten or "")
        return ket

    def ten_nhan_vien(self, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}
        return dict(self.db.execute(select(Employee.id, Employee.full_name).where(Employee.id.in_(ids))).all())
