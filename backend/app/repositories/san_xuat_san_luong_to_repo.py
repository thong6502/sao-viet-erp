"""Data-access cho tab SẢN LƯỢNG của Bàn tổ (spec 2026-09-14 §6, sửa 18/09/2026 §7.3b).

Đọc MẺ (`san_xuat_batch`) theo PHẠM VI TỔ của người xem. Mẻ có đúng MỘT chủ — tổ của bước
(`san_xuat_cong_viec.department_id`) — nên bảng chia hai mục:

  · **mẻ của tổ** — chủ mẻ thuộc phạm vi đang xem (số của mẻ vào dòng tổng);
  · **khách** — chủ mẻ ở tổ khác, nhưng có người của tổ mình trong mẻ (KHÔNG vào dòng tổng).

⚠️ 18/09/2026 (mg `0322`): mọi truy vấn bản chia (`san_xuat_phan_bo` / `_dong`) gỡ hẳn cùng tầng
chia sản lượng — `_dong_cua_toi`, `dong_chia`, `batch_co_ban_chia`, `tong_cua_toi` không còn nguồn.
"Ai có mặt trong mẻ" nay suy lúc đọc từ KHOẢNG THAM GIA + HỖ TRỢ CHÉO đã xác nhận (xem
`services/san_xuat/nguoi_trong_me.py`); ở đây chỉ cần cùng luật đó viết bằng SQL để LỌC mẻ khách.

Lọc ngày theo GIỜ BẮT ĐẦU MẺ (UTC thật, service quy khoảng ngày giờ xưởng ra hai mốc UTC). Gom theo
nguồn LỆNH/BÀI GHÉP cùng luật bàn tổ (`SanXuatRepository._khoa_lenh_cols`), cắt trang + cộng tổng ở
SQL — kéo cả tháng mẻ về rồi cộng bằng Python là mỗi lần mở tab đọc cả bảng.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import NamedTuple

from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from ..models.bai_ghep import BaiGhep
from ..models.department import Department
from ..models.employee import Employee
from ..models.lsx import Lsx
from ..models.san_xuat import SanXuatCongViec
from ..models.san_xuat_phan_bo import HT_XAC_NHAN, SanXuatHoTro
from ..models.san_xuat_san_luong import SanXuatBatch
from ..models.san_xuat_thuc_thi import SanXuatKhoangThamGia

# Mốc thay cho khoảng tham gia CÒN MỞ — cùng hằng với `nguoi_trong_me._XA`, phải đổi cùng nhau.
_XA = datetime(2999, 1, 1, tzinfo=timezone.utc)


class CuaSoGiup(NamedTuple):
    """Một thỏa thuận hỗ trợ chéo đã xác nhận, ngày làm đã quy ra `[tu, den)` UTC thật."""

    cong_viec_id: int
    employee_id: int
    department_id: int | None
    tu: datetime
    den: datetime


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
    def _co_nguoi_cua_to(
        to_ids: set[int], employee_id: int | None = None, giup: Sequence[CuaSoGiup] = (),
    ):
        """Mẻ có ít nhất một người của `to_ids` CÓ MẶT — CÙNG hai nguồn với `nguoi_trong_me`:

        1. giao khoảng tham gia với cửa sổ mẻ: chạm nhau đúng một mốc KHÔNG tính, khoảng còn mở kéo
           tới `_XA`;
        2. hỗ trợ chéo đã xác nhận (`giup`, xem `ho_tro_trong_khoang`): cùng công việc và giờ bắt
           đầu mẻ rơi trong NGÀY xưởng của thỏa thuận. Service quy ngày ra hai mốc UTC — repo không
           tự đổi giờ xưởng.

        Tổ của người đọc ở `employees.department_id` (tổ GỐC), vì đây chính là câu hỏi "người của tổ
        tôi có đi làm ở mẻ này không".
        """
        dk = [
            SanXuatKhoangThamGia.cong_viec_id == SanXuatBatch.cong_viec_id,
            Employee.department_id.in_(to_ids),
            SanXuatKhoangThamGia.bat_dau < SanXuatBatch.ket_thuc,
            func.coalesce(SanXuatKhoangThamGia.ket_thuc, _XA) > SanXuatBatch.bat_dau,
        ]
        if employee_id is not None:
            dk.append(SanXuatKhoangThamGia.employee_id == employee_id)
        co_khoang = exists(
            select(SanXuatKhoangThamGia.id)
            .join(Employee, Employee.id == SanXuatKhoangThamGia.employee_id)
            .where(*dk)
        )
        cua_so = {
            (g.cong_viec_id, g.tu, g.den) for g in giup
            if g.department_id in to_ids and (employee_id is None or g.employee_id == employee_id)
        }
        if not cua_so:
            return co_khoang
        return or_(co_khoang, *(
            and_(SanXuatBatch.cong_viec_id == cv_id, SanXuatBatch.bat_dau >= tu,
                 SanXuatBatch.bat_dau < den)
            for cv_id, tu, den in sorted(cua_so)
        ))

    def ho_tro_trong_khoang(
        self, to_ids: set[int], tu_ngay: date, den_ngay: date,
    ) -> list[tuple[int, int, int | None, date]]:
        """(công việc, người, tổ GỐC của người, ngày làm) của các thỏa thuận hỗ trợ chéo ĐÃ XÁC NHẬN
        mà người thuộc `to_ids` sang giúp, ngày làm trong `[tu_ngay, den_ngay]` (ngày xưởng).

        Người sang giúp không có khoảng tham gia — ô "Giao người" chỉ bày người trong tổ — nên
        không có nguồn này thì tổ của họ không bao giờ thấy mẻ khách (§7.3b)."""
        if not to_ids:
            return []
        return [
            (r.cong_viec_id, r.employee_id, r.department_id, r.ngay_lam_viec)
            for r in self.db.execute(
                select(SanXuatHoTro.cong_viec_id, SanXuatHoTro.employee_id,
                       Employee.department_id, SanXuatHoTro.ngay_lam_viec)
                .join(Employee, Employee.id == SanXuatHoTro.employee_id)
                .where(Employee.department_id.in_(to_ids),
                       SanXuatHoTro.trang_thai == HT_XAC_NHAN,
                       SanXuatHoTro.ngay_lam_viec >= tu_ngay,
                       SanXuatHoTro.ngay_lam_viec <= den_ngay)
            ).all()
        ]

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

    def _pham_vi(self, tron: set[int], rieng: set[int], employee_id: int | None,
                 giup: Sequence[CuaSoGiup] = ()):
        """Mẻ lọt phạm vi = mẻ của tổ trong phạm vi, HOẶC mẻ tổ khác có người của mình trong đó.
        None = không thấy gì.

        Nhánh `rieng` (công nhân, quyền chỉ "Của tôi") siết thêm: phải có CHÍNH người đó trong mẻ —
        thợ không được xem mẻ của người khác cùng tổ (§12.3).
        """
        nhanh = []
        if tron:
            nhanh.append(SanXuatCongViec.department_id.in_(tron))
            nhanh.append(self._co_nguoi_cua_to(tron, giup=giup))
        if rieng and employee_id is not None:
            nhanh.append(and_(
                or_(SanXuatCongViec.department_id.in_(rieng),
                    self._co_nguoi_cua_to(rieng, employee_id, giup)),
                self._co_nguoi_cua_to(rieng | tron, employee_id, giup),
            ))
        if not nhanh:
            return None
        return nhanh[0] if len(nhanh) == 1 else or_(*nhanh)

    # --- trang lệnh ---------------------------------------------------------------------------
    def trang_nguon(
        self, *, tron: set[int], rieng: set[int], employee_id: int | None,
        tu: datetime, den: datetime, tim: str | None, trang: int, co_trang: int,
        giup: Sequence[CuaSoGiup] = (),
    ) -> tuple[list[tuple[str, int | None]], int]:
        """Một trang khoá nguồn (loại, id), mới hoạt động gần nhất lên đầu, + tổng số nguồn."""
        pv = self._pham_vi(tron, rieng, employee_id, giup)
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
        employee_id: int | None, tu: datetime, den: datetime, giup: Sequence[CuaSoGiup] = (),
    ) -> list[tuple[SanXuatBatch, SanXuatCongViec]]:
        """Mọi mẻ (kèm công việc) của các nguồn trong trang, cùng phạm vi + khoảng ngày."""
        pv = self._pham_vi(tron, rieng, employee_id, giup)
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

    # --- tổng của CẢ bộ lọc (không chỉ trang) -------------------------------------------------
    def tong_cua_to(
        self, *, tron: set[int], tu: datetime, den: datetime, tim: str | None,
    ) -> list[tuple[str, float, float, int]]:
        """(đơn vị, tổng tốt, tổng hỏng, số mẻ) của MẺ CỦA TỔ — gộp theo ĐƠN VỊ, không cộng lẫn.

        Chỉ đếm mẻ mà tổ trong phạm vi LÀ CHỦ. Mẻ khách để riêng và không cộng, nên cộng tổng của
        cả 8 tổ ra đúng sản lượng xưởng, không mẻ nào bị tính hai lượt (§7.3b luật 1).
        """
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

    def quy_cach_lenh(self, lsx_ids: set[int]) -> dict[int, dict]:
        """`{lsx_id: quy_cach_json}` — bù khoá cho ảnh chụp đời cũ của công việc."""
        if not lsx_ids:
            return {}
        return {i: qc or {} for i, qc in self.db.execute(
            select(Lsx.id, Lsx.quy_cach_json).where(Lsx.id.in_(lsx_ids)))}

    def ten_nhan_vien(self, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}
        return dict(self.db.execute(select(Employee.id, Employee.full_name).where(Employee.id.in_(ids))).all())

    def ten_to(self, ids: set[int]) -> dict[int, str]:
        """Tên tổ cho NHÃN "(tổ bế)" — kể cả tổ NGOÀI phạm vi người xem, vì nhãn chỉ nói người đó
        từ đâu sang, không mở thêm dữ liệu nào của tổ ấy."""
        if not ids:
            return {}
        return dict(self.db.execute(
            select(Department.id, Department.name).where(Department.id.in_(ids))
        ).all())
