"""Data-access cho lát KCS — kiểm tra chất lượng (Giai đoạn 5, §13).

Giữ đúng tầng: mọi truy vấn/ghi DB của batch kiểm tra · lỗi · ảnh bằng chứng gom ở đây; service
`services/san_xuat/kcs.py` chỉ điều phối + kiểm luật. Số dẫn xuất (đếm ảnh, lỗi còn chờ) TÍNH LÚC
ĐỌC bằng các hàm ở đây — không cache cột (precedent `san_xuat_san_luong_repo`).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.san_xuat import SanXuatCongViec
from ..models.san_xuat_kcs import (
    KCS_LOAI_ROUTING,
    TN_CHO,
    SanXuatKcsBatch,
    SanXuatKcsLoi,
    SanXuatKcsLoiAnh,
)
from ..models.san_xuat_ly_do import SanXuatLyDo
from ..models.san_xuat_san_luong import BG_DIEU_CHINH, BG_XAC_NHAN, SanXuatBanGiao


class SanXuatKcsRepository:
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

    def ly_do(self, ly_do_id: int) -> SanXuatLyDo | None:
        return self.db.get(SanXuatLyDo, ly_do_id)

    def nhan_ly_do(self, ids: set[int]) -> dict[int, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.scalars(select(SanXuatLyDo).where(SanXuatLyDo.id.in_(ids)))
        return {r.id: r.ten for r in rows}

    # --- Batch kiểm tra (§13.1) --------------------------------------------------------------
    def kcs_batch(self, kcs_batch_id: int) -> SanXuatKcsBatch | None:
        return self.db.get(SanXuatKcsBatch, kcs_batch_id)

    def cac_kcs_batch(self, cong_viec_id: int) -> list[SanXuatKcsBatch]:
        return list(
            self.db.scalars(
                select(SanXuatKcsBatch)
                .where(SanXuatKcsBatch.cong_viec_id == cong_viec_id)
                .order_by(SanXuatKcsBatch.bat_dau, SanXuatKcsBatch.id)
            )
        )

    def kcs_batch_theo_nhom(self, nhom_id: int) -> list[SanXuatKcsBatch]:
        """Mọi batch KCS của một nhóm thành phẩm — dùng cho nền nhập kho + đóng nhóm (§14, §16)."""
        return list(
            self.db.scalars(
                select(SanXuatKcsBatch)
                .where(SanXuatKcsBatch.nhom_id == nhom_id)
                .order_by(SanXuatKcsBatch.bat_dau, SanXuatKcsBatch.id)
            )
        )

    # --- Lỗi (§13.2) -------------------------------------------------------------------------
    def loi(self, loi_id: int) -> SanXuatKcsLoi | None:
        return self.db.get(SanXuatKcsLoi, loi_id)

    def cac_loi(self, kcs_batch_id: int) -> list[SanXuatKcsLoi]:
        return list(
            self.db.scalars(
                select(SanXuatKcsLoi)
                .where(SanXuatKcsLoi.kcs_batch_id == kcs_batch_id)
                .order_by(SanXuatKcsLoi.id)
            )
        )

    def cac_loi_nhieu(self, kcs_batch_ids: list[int]) -> dict[int, list[SanXuatKcsLoi]]:
        if not kcs_batch_ids:
            return {}
        rows = self.db.scalars(
            select(SanXuatKcsLoi)
            .where(SanXuatKcsLoi.kcs_batch_id.in_(kcs_batch_ids))
            .order_by(SanXuatKcsLoi.id)
        )
        out: dict[int, list[SanXuatKcsLoi]] = {}
        for l in rows:
            out.setdefault(l.kcs_batch_id, []).append(l)
        return out

    def loi_cho_to(self, department_id: int) -> list[SanXuatKcsLoi]:
        """Lỗi ĐANG CHỜ phản hồi mà một tổ bị yêu cầu nhận trách nhiệm (hộp thư tổ phụ trách §13.2)."""
        return list(
            self.db.scalars(
                select(SanXuatKcsLoi)
                .where(
                    SanXuatKcsLoi.to_chiu_id == department_id,
                    SanXuatKcsLoi.trang_thai == TN_CHO,
                )
                .order_by(SanXuatKcsLoi.id)
            )
        )

    def co_loi_chua_tra_loi(self, nhom_id: int) -> bool:
        """Còn lỗi KCS CHỜ phản hồi trong một nhóm thành phẩm → chặn đóng đủ nhóm (§16)."""
        row = self.db.scalar(
            select(SanXuatKcsLoi.id)
            .join(SanXuatKcsBatch, SanXuatKcsLoi.kcs_batch_id == SanXuatKcsBatch.id)
            .where(SanXuatKcsBatch.nhom_id == nhom_id, SanXuatKcsLoi.trang_thai == TN_CHO)
            .limit(1)
        )
        return row is not None

    # --- Ảnh bằng chứng (§13.2) --------------------------------------------------------------
    def anh(self, anh_id: int) -> SanXuatKcsLoiAnh | None:
        return self.db.get(SanXuatKcsLoiAnh, anh_id)

    def anh_cua_loi(self, loi_id: int) -> list[SanXuatKcsLoiAnh]:
        return list(
            self.db.scalars(
                select(SanXuatKcsLoiAnh)
                .where(SanXuatKcsLoiAnh.loi_id == loi_id)
                .order_by(SanXuatKcsLoiAnh.id)
            )
        )

    def anh_cua_loi_nhieu(self, loi_ids: list[int]) -> dict[int, list[SanXuatKcsLoiAnh]]:
        if not loi_ids:
            return {}
        rows = self.db.scalars(
            select(SanXuatKcsLoiAnh)
            .where(SanXuatKcsLoiAnh.loi_id.in_(loi_ids))
            .order_by(SanXuatKcsLoiAnh.id)
        )
        out: dict[int, list[SanXuatKcsLoiAnh]] = {}
        for a in rows:
            out.setdefault(a.loi_id, []).append(a)
        return out

    def dem_anh(self, loi_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count(SanXuatKcsLoiAnh.id)).where(SanXuatKcsLoiAnh.loi_id == loi_id)
            )
            or 0
        )

    # --- Tổng số lượng (KCS kiêm nhiệm, mg 0250) ----------------------------------------------
    def tong_ban_giao_xac_nhan(self, cong_viec_id: int) -> float:
        """Tổng đã bàn giao TỚI công việc này ở trạng thái confirmed/adjusted (§11.2) — `proposed`
        chưa chốt nên KHÔNG tính vào lượng có thể kiểm (mục 4)."""
        return float(
            self.db.scalar(
                select(func.coalesce(func.sum(SanXuatBanGiao.so_luong), 0)).where(
                    SanXuatBanGiao.dich_cong_viec_id == cong_viec_id,
                    SanXuatBanGiao.trang_thai.in_((BG_XAC_NHAN, BG_DIEU_CHINH)),
                )
            )
            or 0
        )

    def tong_kcs_routing_da_ghi(self, cong_viec_id: int) -> float:
        """Tổng `so_luong_nhan` của mọi batch KCS loại routing đã ghi cho công việc này (nhiều đợt,
        mục 2) — dùng để chặn TỔNG các đợt vượt số đã bàn giao (mục 3)."""
        return float(
            self.db.scalar(
                select(func.coalesce(func.sum(SanXuatKcsBatch.so_luong_nhan), 0)).where(
                    SanXuatKcsBatch.cong_viec_id == cong_viec_id,
                    SanXuatKcsBatch.loai == KCS_LOAI_ROUTING,
                )
            )
            or 0
        )
