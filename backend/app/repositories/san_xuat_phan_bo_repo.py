"""Data-access cho lát HỖ TRỢ CHÉO · PHÂN BỔ SẢN LƯỢNG · BÙ TRỪ (Giai đoạn 4, §9 · §12).

Giữ đúng tầng: mọi truy vấn/ghi DB của thỏa thuận hỗ trợ · header/dòng phân bổ · dòng bù trừ gom
ở đây; service `services/san_xuat/ho_tro.py` + `phan_bo.py` chỉ điều phối + kiểm luật. Đọc batch/
khoảng tham gia thì dùng `SanXuatSanLuongRepository` / `SanXuatThucThiRepository` (không lặp lại).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.san_xuat import SanXuatCongViec
from ..models.san_xuat_ly_do import SanXuatLyDo
from ..models.san_xuat_san_luong import SanXuatBanGiao
from ..models.san_xuat_phan_bo import (
    HT_XAC_NHAN,
    PB_DA_CHOT,
    SanXuatHoTro,
    SanXuatPhanBo,
    SanXuatPhanBoBuTru,
    SanXuatPhanBoDong,
    SanXuatPhanBoLoaiTru,
)


class SanXuatPhanBoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Ghi ---------------------------------------------------------------------------------
    def add(self, obj):
        self.db.add(obj)
        return obj

    def flush(self) -> None:
        self.db.flush()

    # --- Công việc + lý do (đọc lại để gate/nối) ---------------------------------------------
    def cong_viec(self, cong_viec_id: int) -> SanXuatCongViec | None:
        return self.db.get(SanXuatCongViec, cong_viec_id)

    def ly_do(self, ly_do_id: int) -> SanXuatLyDo | None:
        return self.db.get(SanXuatLyDo, ly_do_id)

    # --- Thỏa thuận hỗ trợ (§9) --------------------------------------------------------------
    def ho_tro(self, ho_tro_id: int) -> SanXuatHoTro | None:
        return self.db.get(SanXuatHoTro, ho_tro_id)

    def ho_tro_cua_cong_viec(self, cong_viec_id: int) -> list[SanXuatHoTro]:
        """Mọi thỏa thuận hỗ trợ của một công đoạn (mọi trạng thái) — để hiển thị + huỷ khi lịch
        chưa chạy bị phát hành lại (§9.2)."""
        return list(
            self.db.scalars(
                select(SanXuatHoTro)
                .where(SanXuatHoTro.cong_viec_id == cong_viec_id)
                .order_by(SanXuatHoTro.ngay_lam_viec, SanXuatHoTro.id)
            )
        )

    def ho_tro_xac_nhan_trong_pham_vi(
        self, cong_viec_id: int, ngay
    ) -> list[SanXuatHoTro]:
        """Thỏa thuận ĐÃ XÁC NHẬN trong CÙNG phạm vi phân bổ = cùng công đoạn + cùng ngày (§9.1).

        Dùng cho hai việc: (1) kiểm trần tổng tỷ lệ ≤ 100% khi xác nhận thêm; (2) engine phân bổ
        lấy tổng P + danh sách người hỗ trợ của batch rơi vào ngày này."""
        return list(
            self.db.scalars(
                select(SanXuatHoTro)
                .where(
                    SanXuatHoTro.cong_viec_id == cong_viec_id,
                    SanXuatHoTro.ngay_lam_viec == ngay,
                    SanXuatHoTro.trang_thai == HT_XAC_NHAN,
                )
                .order_by(SanXuatHoTro.id)
            )
        )

    # --- Header phân bổ (§12.1: một batch một phân bổ) ---------------------------------------
    def phan_bo(self, phan_bo_id: int) -> SanXuatPhanBo | None:
        return self.db.get(SanXuatPhanBo, phan_bo_id)

    def phan_bo_cua_batch(self, batch_id: int) -> SanXuatPhanBo | None:
        return self.db.scalars(
            select(SanXuatPhanBo).where(SanXuatPhanBo.batch_id == batch_id)
        ).first()

    def phan_bo_cua_cong_viec(self, cong_viec_id: int) -> list[SanXuatPhanBo]:
        return list(
            self.db.scalars(
                select(SanXuatPhanBo)
                .where(SanXuatPhanBo.cong_viec_id == cong_viec_id)
                .order_by(SanXuatPhanBo.ngay, SanXuatPhanBo.id)
            )
        )

    def con_phan_bo_chua_chot(self, cong_viec_id: int) -> bool:
        """Còn phân bổ CHƯA chốt (draft/reopened) của công đoạn — chặn đóng nhóm (§12.3)."""
        row = self.db.scalar(
            select(SanXuatPhanBo.id).where(
                SanXuatPhanBo.cong_viec_id == cong_viec_id,
                SanXuatPhanBo.trang_thai != PB_DA_CHOT,
            ).limit(1)
        )
        return row is not None

    # --- Dòng phân bổ theo người (bảng dẫn xuất) ---------------------------------------------
    def cac_dong(self, phan_bo_id: int) -> list[SanXuatPhanBoDong]:
        return list(
            self.db.scalars(
                select(SanXuatPhanBoDong)
                .where(SanXuatPhanBoDong.phan_bo_id == phan_bo_id)
                .order_by(SanXuatPhanBoDong.id)
            )
        )

    def xoa_dong_cua(self, phan_bo_id: int) -> None:
        """Xoá sạch dòng của một header để SINH LẠI (§12.2: mỗi lần tính/chốt dựng lại toàn bộ)."""
        for dong in self.cac_dong(phan_bo_id):
            self.db.delete(dong)

    # --- Bù trừ sau khoá kỳ (§12.3) ----------------------------------------------------------
    def bu_tru_cua_batch(self, batch_id: int) -> list[SanXuatPhanBoBuTru]:
        return list(
            self.db.scalars(
                select(SanXuatPhanBoBuTru)
                .where(SanXuatPhanBoBuTru.batch_id == batch_id)
                .order_by(SanXuatPhanBoBuTru.id)
            )
        )

    # --- Loại trừ khỏi lương batch (§7.3) ----------------------------------------------------
    def loai_tru_cua_batch(self, batch_id: int) -> list[SanXuatPhanBoLoaiTru]:
        return list(
            self.db.scalars(
                select(SanXuatPhanBoLoaiTru)
                .where(SanXuatPhanBoLoaiTru.batch_id == batch_id)
                .order_by(SanXuatPhanBoLoaiTru.id)
            )
        )

    def loai_tru_ids(self, batch_id: int) -> set[int]:
        """Tập employee_id bị loại khỏi lương của batch — engine bỏ họ khỏi vòng chia trọng số."""
        return set(
            self.db.scalars(
                select(SanXuatPhanBoLoaiTru.employee_id).where(
                    SanXuatPhanBoLoaiTru.batch_id == batch_id
                )
            )
        )

    def loai_tru_cua(self, batch_id: int, employee_id: int) -> SanXuatPhanBoLoaiTru | None:
        return self.db.scalars(
            select(SanXuatPhanBoLoaiTru).where(
                SanXuatPhanBoLoaiTru.batch_id == batch_id,
                SanXuatPhanBoLoaiTru.employee_id == employee_id,
            )
        ).first()

    def go_loai_tru(self, batch_id: int, employee_id: int) -> bool:
        """Gỡ loại trừ = XOÁ dòng. Trả True nếu có dòng để xoá."""
        row = self.loai_tru_cua(batch_id, employee_id)
        if row is None:
            return False
        self.db.delete(row)
        return True

    # --- Gate không-nhất-quán bàn giao (§11.3) -----------------------------------------------
    def co_ban_giao_khong_nhat_quan(self, cong_viec_id: int) -> bool:
        """Công đoạn còn bàn giao ĐI bị đánh dấu không nhất quán (giảm dưới lượng công đoạn sau đã
        dùng) → §11.3 chặn CHỐT phân bổ cho tới khi gỡ."""
        row = self.db.scalar(
            select(SanXuatBanGiao.id).where(
                SanXuatBanGiao.nguon_cong_viec_id == cong_viec_id,
                SanXuatBanGiao.khong_nhat_quan.is_(True),
            ).limit(1)
        )
        return row is not None
