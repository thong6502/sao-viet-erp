"""Data-access cho KCS theo LỆNH (mg `0306`, `docs/design-kcs-theo-lenh.md`).

Giữ đúng tầng: mọi truy vấn/ghi DB của lần kiểm · lỗi · ảnh bằng chứng gom ở đây; service
`services/san_xuat/kcs.py` chỉ điều phối + kiểm luật. Số dẫn xuất (tổng đạt, lỗi chưa xem) TÍNH LÚC
ĐỌC — không cache cột.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from ..models.cong_doan import CongDoan
from ..models.customer import Customer
from ..models.department import Department
from ..models.lsx import Lsx, LsxCongDoan
from ..models.order import Order
from ..models.san_xuat import (
    NHOM_CHO_DIEU_KIEN, NHOM_DANG_SX, SanXuatCongViec, SanXuatNhom, SanXuatNhomLsx,
)
from ..models.san_xuat_kcs import SanXuatKcsBatch, SanXuatKcsLoi, SanXuatKcsLoiAnh
from ..models.user import User


class SanXuatKcsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Ghi ---------------------------------------------------------------------------------
    def add(self, obj):
        self.db.add(obj)
        return obj

    def flush(self) -> None:
        self.db.flush()

    # --- Ai là KCS ---------------------------------------------------------------------------
    def la_thanh_vien_to_kcs(self, user_id: int | None) -> bool:
        """Tài khoản đứng trong một phòng ban có cờ `is_kcs` (cờ đặt đích danh, không kế thừa)."""
        if user_id is None:
            return False
        return self.db.scalar(
            select(User.id)
            .join(Department, Department.id == User.department_id)
            .where(User.id == user_id, Department.is_kcs == true())
            .limit(1)
        ) is not None

    def la_truong_to_kcs(self, user_id: int | None) -> bool:
        """Tài khoản đứng đầu (`head_user_id`) ít nhất một phòng ban `is_kcs`."""
        if user_id is None:
            return False
        return self.db.scalar(
            select(Department.id)
            .where(Department.head_user_id == user_id, Department.is_kcs == true())
            .limit(1)
        ) is not None

    # --- Neo lại (gate/đọc) ------------------------------------------------------------------
    def cong_viec(self, cong_viec_id: int) -> SanXuatCongViec | None:
        return self.db.get(SanXuatCongViec, cong_viec_id)

    def cong_viec_nhieu(self, ids) -> dict[int, SanXuatCongViec]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        return {cv.id: cv for cv in self.db.scalars(
            select(SanXuatCongViec).where(SanXuatCongViec.id.in_(ids))
        )}

    def cong_doan_dang_dung(self) -> list[CongDoan]:
        """Danh mục công đoạn đang dùng, theo mã — nguồn ô lọc "Công đoạn" của dashboard KCS."""
        return list(self.db.execute(
            select(CongDoan).where(CongDoan.active.is_(True)).order_by(CongDoan.ma)
        ).scalars())

    def ten_to(self, department_ids) -> dict[int, str]:
        ids = {i for i in department_ids if i}
        if not ids:
            return {}
        return {did: ten for did, ten in self.db.execute(
            select(Department.id, Department.name).where(Department.id.in_(ids))
        ).all()}

    def ten_nguoi(self, user_ids) -> dict[int, str]:
        ids = {i for i in user_ids if i}
        if not ids:
            return {}
        return {uid: ten for uid, ten in self.db.execute(
            select(User.id, User.name).where(User.id.in_(ids))
        ).all()}

    # --- Lệnh ---------------------------------------------------------------------------------
    def lsx(self, lsx_id: int | None) -> Lsx | None:
        return self.db.get(Lsx, lsx_id) if lsx_id else None

    def ma_lsx_nhieu(self, lsx_ids) -> dict[int, str]:
        ids = {i for i in lsx_ids if i}
        if not ids:
            return {}
        return {i: ma for i, ma in self.db.execute(select(Lsx.id, Lsx.ma).where(Lsx.id.in_(ids))).all()}

    def trang_lenh(
        self, *, tim: str | None, gom_da_dong: bool, offset: int, limit: int
    ) -> tuple[list[int], int]:
        """Trang lệnh cho màn KCS — lệnh ĐÃ vào nhóm thành phẩm (tức đã phát hành), mặc định chỉ
        nhóm còn mở. Tìm theo mã/tên lệnh, mã nhóm, tên khách. Mới nhất lên đầu."""
        q = (
            select(Lsx.id)
            .join(SanXuatNhomLsx, SanXuatNhomLsx.lsx_id == Lsx.id)
            .join(SanXuatNhom, SanXuatNhom.id == SanXuatNhomLsx.nhom_id)
            .outerjoin(Order, Order.id == Lsx.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
        )
        if not gom_da_dong:
            q = q.where(SanXuatNhom.trang_thai.in_((NHOM_DANG_SX, NHOM_CHO_DIEU_KIEN)))
        tim = (tim or "").strip()
        if tim:
            mau = f"%{tim}%"
            q = q.where(or_(
                Lsx.ma.ilike(mau), Lsx.ten.ilike(mau), SanXuatNhom.ma.ilike(mau),
                Customer.name.ilike(mau),
            ))
        tong = int(self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        ids = list(self.db.scalars(q.order_by(Lsx.id.desc()).offset(offset).limit(limit)))
        return ids, tong

    def thu_tu_buoc(self, lsx_ids) -> dict[int, tuple[int, int]]:
        """{lsx_cong_doan.id: (lsx_id, thu_tu)} — xếp chuỗi công đoạn theo đúng thứ tự routing."""
        ids = {i for i in lsx_ids if i}
        if not ids:
            return {}
        return {cid: (lid, tt) for cid, lid, tt in self.db.execute(
            select(LsxCongDoan.id, LsxCongDoan.lsx_id, LsxCongDoan.thu_tu)
            .where(LsxCongDoan.lsx_id.in_(ids))
        ).all()}

    # --- Lần kiểm ----------------------------------------------------------------------------
    def kcs_batch(self, kcs_batch_id: int) -> SanXuatKcsBatch | None:
        return self.db.get(SanXuatKcsBatch, kcs_batch_id)

    def kcs_batch_nhieu(self, ids) -> dict[int, SanXuatKcsBatch]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        return {b.id: b for b in self.db.scalars(
            select(SanXuatKcsBatch).where(SanXuatKcsBatch.id.in_(ids))
        )}

    def cac_kcs_batch(self, cong_viec_id: int) -> list[SanXuatKcsBatch]:
        return list(
            self.db.scalars(
                select(SanXuatKcsBatch)
                .where(SanXuatKcsBatch.cong_viec_id == cong_viec_id)
                .order_by(SanXuatKcsBatch.bat_dau, SanXuatKcsBatch.id)
            )
        )

    def khoa_kcs_cua_cong_viec(self, cong_viec_id: int) -> None:
        """Khoá MỌI lần kiểm của một công đoạn (SELECT … FOR UPDATE) trước khi đọc số gửi kho — hai
        lượt bấm "Tạo yêu cầu nhập kho" song song phải tuần tự, lượt sau đọc thấy yêu cầu lượt trước.
        SQLite bỏ qua FOR UPDATE nhưng tự khoá ghi cả DB nên vẫn tuần tự."""
        self.db.execute(
            select(SanXuatKcsBatch.id)
            .where(SanXuatKcsBatch.cong_viec_id == cong_viec_id)
            .with_for_update()
        ).all()

    def cac_kcs_batch_nhieu(self, cong_viec_ids) -> dict[int, list[SanXuatKcsBatch]]:
        """{cong_viec_id: [lần kiểm]} cho cả chuỗi công đoạn trong MỘT truy vấn."""
        ids = {i for i in cong_viec_ids if i}
        if not ids:
            return {}
        out: dict[int, list[SanXuatKcsBatch]] = {}
        for b in self.db.scalars(
            select(SanXuatKcsBatch)
            .where(SanXuatKcsBatch.cong_viec_id.in_(ids))
            .order_by(SanXuatKcsBatch.bat_dau, SanXuatKcsBatch.id)
        ):
            out.setdefault(b.cong_viec_id, []).append(b)
        return out

    def tong_dat(self, cong_viec_id: int, *, tru_batch_id: int | None = None) -> float:
        """Σ đạt đã ghi cho một công việc (trừ một lần kiểm khi đang điều chỉnh chính nó)."""
        q = select(func.coalesce(func.sum(SanXuatKcsBatch.so_luong_dat), 0)).where(
            SanXuatKcsBatch.cong_viec_id == cong_viec_id
        )
        if tru_batch_id is not None:
            q = q.where(SanXuatKcsBatch.id != tru_batch_id)
        return float(self.db.scalar(q) or 0)

    def tong_kiem_nhieu(self, cong_viec_ids) -> dict[int, tuple[int, float, float]]:
        """{cong_viec_id: (số lần kiểm, Σ đạt, Σ lỗi)} — MỘT truy vấn gộp cho danh sách lệnh."""
        ids = {i for i in cong_viec_ids if i}
        if not ids:
            return {}
        rows = self.db.execute(
            select(
                SanXuatKcsBatch.cong_viec_id,
                func.count(SanXuatKcsBatch.id),
                func.coalesce(func.sum(SanXuatKcsBatch.so_luong_dat), 0),
                func.coalesce(func.sum(SanXuatKcsBatch.so_luong_khong_dat), 0),
            )
            .where(SanXuatKcsBatch.cong_viec_id.in_(ids))
            .group_by(SanXuatKcsBatch.cong_viec_id)
        ).all()
        return {cid: (int(n), float(d or 0), float(l or 0)) for cid, n, d, l in rows}

    # --- Lỗi ---------------------------------------------------------------------------------
    def loi(self, loi_id: int) -> SanXuatKcsLoi | None:
        return self.db.get(SanXuatKcsLoi, loi_id)

    def cac_loi_nhieu(self, kcs_batch_ids) -> dict[int, list[SanXuatKcsLoi]]:
        ids = [i for i in kcs_batch_ids if i]
        if not ids:
            return {}
        out: dict[int, list[SanXuatKcsLoi]] = {}
        for l in self.db.scalars(
            select(SanXuatKcsLoi)
            .where(SanXuatKcsLoi.kcs_batch_id.in_(ids))
            .order_by(SanXuatKcsLoi.id)
        ):
            out.setdefault(l.kcs_batch_id, []).append(l)
        return out

    def loi_chua_xem_nhieu_to(self, department_ids) -> list[SanXuatKcsLoi]:
        """Lỗi KCS gửi tới các tổ này mà tổ chưa bấm "Đã xem" — hộp "Chờ tổ bạn xác nhận"."""
        ids = {i for i in department_ids if i}
        if not ids:
            return []
        return list(
            self.db.scalars(
                select(SanXuatKcsLoi)
                .where(
                    SanXuatKcsLoi.to_chiu_id.in_(ids),
                    SanXuatKcsLoi.phan_hoi_luc.is_(None),
                    # Điều chỉnh về 0 lỗi thì lỗi thôi đòi tổ xem — không giả "đã xem" thay tổ.
                    SanXuatKcsLoi.so_luong > 0,
                )
                .order_by(SanXuatKcsLoi.id)
            )
        )

    # --- Ảnh bằng chứng ----------------------------------------------------------------------
    def anh_cua_loi_nhieu(self, loi_ids) -> dict[int, list[SanXuatKcsLoiAnh]]:
        ids = [i for i in loi_ids if i]
        if not ids:
            return {}
        out: dict[int, list[SanXuatKcsLoiAnh]] = {}
        for a in self.db.scalars(
            select(SanXuatKcsLoiAnh)
            .where(SanXuatKcsLoiAnh.loi_id.in_(ids))
            .order_by(SanXuatKcsLoiAnh.id)
        ):
            out.setdefault(a.loi_id, []).append(a)
        return out
