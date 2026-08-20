"""Data-access cho lát KHO SẢN XUẤT — registry · lot · yêu cầu nhập kho (Giai đoạn 5, §14).

Giữ đúng tầng: mọi truy vấn/ghi DB của hàng sản xuất gom ở đây; service `services/san_xuat/kho.py`
chỉ điều phối + kiểm luật. Số dẫn xuất (tổng đã yêu cầu, còn được yêu cầu, BTP trả chờ kho) TÍNH
LÚC ĐỌC bằng các hàm ở đây — không cache cột (precedent `san_xuat_kcs_repo`).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.order import Order
from ..models.san_xuat import SanXuatCongViec, SanXuatNhom
from ..models.san_xuat_kcs import SanXuatKcsBatch
from ..models.san_xuat_kho import (
    HANG_BTP,
    PL_NHAP_BTP,
    YC_CHO_KHO,
    YC_HUY,
    YC_MOT_PHAN,
    SanXuatKhoHang,
    SanXuatKhoLot,
    SanXuatNhapKhoYc,
)


class SanXuatKhoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Ghi ---------------------------------------------------------------------------------
    def add(self, obj):
        self.db.add(obj)
        return obj

    def flush(self) -> None:
        self.db.flush()

    def delete(self, obj) -> None:
        self.db.delete(obj)

    # --- Neo lại (gate/đọc) ------------------------------------------------------------------
    def cong_viec(self, cong_viec_id: int) -> SanXuatCongViec | None:
        return self.db.get(SanXuatCongViec, cong_viec_id)

    def nhom(self, nhom_id: int) -> SanXuatNhom | None:
        return self.db.get(SanXuatNhom, nhom_id)

    def order(self, order_id: int) -> Order | None:
        return self.db.get(Order, order_id)

    def kcs_batch(self, kcs_batch_id: int) -> SanXuatKcsBatch | None:
        return self.db.get(SanXuatKcsBatch, kcs_batch_id)

    # --- Registry hàng sản xuất (§14.2) ------------------------------------------------------
    def hang(self, hang_id: int) -> SanXuatKhoHang | None:
        return self.db.get(SanXuatKhoHang, hang_id)

    def tim_hang(
        self,
        *,
        order_id: int,
        loai_hang: str,
        nhom_id: int | None,
        lsx_id: int | None,
        cong_doan_ref_id: int | None,
        quy_cach: str | None,
    ) -> SanXuatKhoHang | None:
        """Tìm registry theo KHÓA DANH TÍNH (đơn, loại, nhóm, LSX, công đoạn nguồn, quy cách) để
        get-or-create — không đẻ trùng danh tính hàng trong một đơn."""
        return self.db.scalar(
            select(SanXuatKhoHang).where(
                SanXuatKhoHang.order_id == order_id,
                SanXuatKhoHang.loai_hang == loai_hang,
                SanXuatKhoHang.nhom_id.is_(nhom_id) if nhom_id is None else SanXuatKhoHang.nhom_id == nhom_id,
                SanXuatKhoHang.lsx_id.is_(lsx_id) if lsx_id is None else SanXuatKhoHang.lsx_id == lsx_id,
                SanXuatKhoHang.cong_doan_ref_id.is_(cong_doan_ref_id)
                if cong_doan_ref_id is None
                else SanXuatKhoHang.cong_doan_ref_id == cong_doan_ref_id,
                SanXuatKhoHang.quy_cach.is_(quy_cach) if quy_cach is None else SanXuatKhoHang.quy_cach == quy_cach,
            ).limit(1)
        )

    def cac_hang_cua_don(self, order_id: int) -> list[SanXuatKhoHang]:
        return list(
            self.db.scalars(
                select(SanXuatKhoHang)
                .where(SanXuatKhoHang.order_id == order_id)
                .order_by(SanXuatKhoHang.id)
            )
        )

    def dem_hang(self) -> int:
        return int(self.db.scalar(select(func.count(SanXuatKhoHang.id))) or 0)

    # --- Lot hàng sản xuất (§14.1, §14.2) ----------------------------------------------------
    def lot(self, lot_id: int) -> SanXuatKhoLot | None:
        return self.db.get(SanXuatKhoLot, lot_id)

    def cac_lot_cua_hang(self, hang_id: int) -> list[SanXuatKhoLot]:
        return list(
            self.db.scalars(
                select(SanXuatKhoLot)
                .where(SanXuatKhoLot.hang_id == hang_id)
                .order_by(SanXuatKhoLot.id)
            )
        )

    def cac_lot_cua_nhom(self, nhom_id: int) -> list[SanXuatKhoLot]:
        return list(
            self.db.scalars(
                select(SanXuatKhoLot)
                .where(SanXuatKhoLot.nhom_id == nhom_id)
                .order_by(SanXuatKhoLot.id)
            )
        )

    def btp_tra_cho_kho(self, nhom_id: int) -> list[SanXuatKhoLot]:
        """Lot BTP đã phân loại `nhập kho BTP` NHƯNG kho CHƯA xác nhận nhận — chặn đóng nhóm (§16)."""
        return list(
            self.db.scalars(
                select(SanXuatKhoLot).where(
                    SanXuatKhoLot.nhom_id == nhom_id,
                    SanXuatKhoLot.loai_hang == HANG_BTP,
                    SanXuatKhoLot.phan_loai == PL_NHAP_BTP,
                    SanXuatKhoLot.kho_xac_nhan.is_(False),
                )
            )
        )

    def co_btp_tra_cho_kho(self, nhom_id: int) -> bool:
        row = self.db.scalar(
            select(SanXuatKhoLot.id).where(
                SanXuatKhoLot.nhom_id == nhom_id,
                SanXuatKhoLot.loai_hang == HANG_BTP,
                SanXuatKhoLot.phan_loai == PL_NHAP_BTP,
                SanXuatKhoLot.kho_xac_nhan.is_(False),
            ).limit(1)
        )
        return row is not None

    # --- Yêu cầu nhập kho thành phẩm (§14.1) -------------------------------------------------
    def yc(self, yc_id: int) -> SanXuatNhapKhoYc | None:
        return self.db.get(SanXuatNhapKhoYc, yc_id)

    def cac_yc_cua_batch(self, kcs_batch_id: int) -> list[SanXuatNhapKhoYc]:
        return list(
            self.db.scalars(
                select(SanXuatNhapKhoYc)
                .where(SanXuatNhapKhoYc.kcs_batch_id == kcs_batch_id)
                .order_by(SanXuatNhapKhoYc.id)
            )
        )

    def cac_yc_cua_nhom(self, nhom_id: int) -> list[SanXuatNhapKhoYc]:
        return list(
            self.db.scalars(
                select(SanXuatNhapKhoYc)
                .where(SanXuatNhapKhoYc.nhom_id == nhom_id)
                .order_by(SanXuatNhapKhoYc.id)
            )
        )

    def tong_yeu_cau_cua_batch(self, kcs_batch_id: int, *, tru_yc_id: int | None = None) -> float:
        """Tổng số ĐÃ yêu cầu (không tính phần đã huỷ) của một batch KCS — trần theo `so_luong_dat`
        (§14.1). `tru_yc_id` loại một yêu cầu khỏi tổng (khi sửa chính nó)."""
        stmt = select(func.coalesce(func.sum(SanXuatNhapKhoYc.so_luong_yeu_cau), 0)).where(
            SanXuatNhapKhoYc.kcs_batch_id == kcs_batch_id,
            SanXuatNhapKhoYc.trang_thai != YC_HUY,
        )
        if tru_yc_id is not None:
            stmt = stmt.where(SanXuatNhapKhoYc.id != tru_yc_id)
        return float(self.db.scalar(stmt) or 0)

    # --- Hộp thư kho: mọi việc còn chờ kho hành động (§14, §17) ------------------------------
    def cac_yc_cho_kho(self) -> list[SanXuatNhapKhoYc]:
        """Yêu cầu nhập kho thành phẩm còn chờ kho xác nhận (chờ / một phần) — hộp thư nhân viên kho."""
        return list(
            self.db.scalars(
                select(SanXuatNhapKhoYc)
                .where(SanXuatNhapKhoYc.trang_thai.in_((YC_CHO_KHO, YC_MOT_PHAN)))
                .order_by(SanXuatNhapKhoYc.id)
            )
        )

    def cac_btp_cho_kho(self) -> list[SanXuatKhoLot]:
        """BTP đã phân loại `nhập kho BTP` còn chờ kho xác nhận nhận — hộp thư nhân viên kho."""
        return list(
            self.db.scalars(
                select(SanXuatKhoLot)
                .where(
                    SanXuatKhoLot.loai_hang == HANG_BTP,
                    SanXuatKhoLot.phan_loai == PL_NHAP_BTP,
                    SanXuatKhoLot.kho_xac_nhan.is_(False),
                )
                .order_by(SanXuatKhoLot.id)
            )
        )
