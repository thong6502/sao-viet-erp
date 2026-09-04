"""Truy vấn cho THƯỞNG/PHẠT TỔ TRƯỞNG theo chất lượng (§8 nối tiếp phân bổ sản lượng).

Ba nguồn số, ba câu gom riêng — cố ý KHÔNG join chung một câu: sản lượng đến từ phân bổ đã chốt,
lỗi đến từ phiếu KCS, còn bậc thưởng đến từ danh mục lương. Gộp lại là mất khả năng nói "tổ này
có sản lượng nhưng chưa có lỗi nào" (LEFT JOIN rỗng trông y hệt 0 lỗi thật).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.employee import Employee
from ..models.san_xuat import SanXuatCongViec
from ..models.san_xuat_kcs import TN_CHAP_NHAN, TN_RECORDED, SanXuatKcsBatch, SanXuatKcsLoi
from ..models.san_xuat_phan_bo import PB_DA_CHOT, SanXuatPhanBo, SanXuatPhanBoDong
from ..models.san_xuat_thuong_to_truong import SanXuatThuongToTruong

# Lỗi ĐƯỢC quy trách nhiệm cho tổ. `pending` = tổ chưa phản hồi (cổng đóng nhóm §16 đã chặn, nên
# tới bước này không còn); `rejected` = tổ từ chối, model KCS ghi rõ "không quy trách nhiệm".
TRANG_THAI_LOI_TINH = (TN_CHAP_NHAN, TN_RECORDED)


class ThuongToTruongRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Đầu vào (1): sản lượng + tiền khoán của từng tổ trong nhóm ---------------------------
    def san_luong_theo_to(self, nhom_id: int) -> dict[int, tuple[float, float]]:
        """{department_id → (tổng sản lượng trả lương, tổng tiền khoán)} của MỘT nhóm thành phẩm.

        CHỈ đọc dòng thuộc header `finalized` — y hệt `ProductionOutputRepository`: phân bổ chưa
        chốt thì công nhân còn chưa xem được, lấy nó tính thưởng là chạy trước cả lương.

        Gom theo `SanXuatPhanBoDong.department_id` (tổ của DÒNG) chứ không theo tổ của công việc:
        phần người hỗ trợ chéo ghi cho TỔ GỐC (§9.2), và tiền khoán của họ cũng chảy về tổ gốc —
        thưởng tổ trưởng phải bám cùng một trục, nếu không hai bảng nói hai con số khác nhau.
        """
        stmt = (
            select(
                SanXuatPhanBoDong.department_id,
                func.sum(SanXuatPhanBoDong.so_luong_tra_luong),
                func.sum(SanXuatPhanBoDong.so_luong_tra_luong * SanXuatPhanBoDong.don_gia),
            )
            .join(SanXuatPhanBo, SanXuatPhanBoDong.phan_bo_id == SanXuatPhanBo.id)
            .join(SanXuatCongViec, SanXuatPhanBo.cong_viec_id == SanXuatCongViec.id)
            .where(
                SanXuatCongViec.nhom_id == nhom_id,
                SanXuatPhanBo.trang_thai == PB_DA_CHOT,
                SanXuatPhanBoDong.department_id.is_not(None),
            )
            .group_by(SanXuatPhanBoDong.department_id)
        )
        return {
            int(dept): (float(sl or 0), float(tien or 0))
            for dept, sl, tien in self.db.execute(stmt)
        }

    # --- Đầu vào (2): số lượng lỗi KCS quy cho từng tổ ----------------------------------------
    def loi_theo_to(self, nhom_id: int) -> dict[int, float]:
        """{department_id → tổng số lượng hàng lỗi} mà KCS chỉ đích danh tổ đó chịu, trong nhóm.

        `to_chiu_id` do KCS gán, KHÔNG suy từ vị trí phiếu — nên lỗi phát hiện ở công đoạn sau vẫn
        quy đúng về tổ gây ra. Lỗi chưa gán tổ (`to_chiu_id` NULL) không rơi vào tổ nào."""
        stmt = (
            select(SanXuatKcsLoi.to_chiu_id, func.sum(SanXuatKcsLoi.so_luong))
            .join(SanXuatKcsBatch, SanXuatKcsLoi.kcs_batch_id == SanXuatKcsBatch.id)
            .where(
                SanXuatKcsBatch.nhom_id == nhom_id,
                SanXuatKcsLoi.to_chiu_id.is_not(None),
                SanXuatKcsLoi.trang_thai.in_(TRANG_THAI_LOI_TINH),
            )
            .group_by(SanXuatKcsLoi.to_chiu_id)
        )
        return {int(dept): float(sl or 0) for dept, sl in self.db.execute(stmt)}

    # --- Tổ trưởng ---------------------------------------------------------------------------
    def employee_cua_user(self, user_id: int) -> Employee | None:
        """Hồ sơ nhân sự của một tài khoản. NULL = tổ trưởng chưa được nối `employees.user_id`."""
        return self.db.scalars(
            select(Employee).where(Employee.user_id == user_id).limit(1)
        ).first()

    # --- Dòng thưởng -------------------------------------------------------------------------
    def cua_nhom(self, nhom_id: int) -> list[SanXuatThuongToTruong]:
        return list(
            self.db.scalars(
                select(SanXuatThuongToTruong)
                .where(SanXuatThuongToTruong.nhom_id == nhom_id)
                .order_by(SanXuatThuongToTruong.department_id)
            )
        )

    def cua_nhom_va_to(self, nhom_id: int, department_id: int) -> SanXuatThuongToTruong | None:
        return self.db.scalars(
            select(SanXuatThuongToTruong).where(
                SanXuatThuongToTruong.nhom_id == nhom_id,
                SanXuatThuongToTruong.department_id == department_id,
            )
        ).first()

    def theo_ky(self, year: int, month: int) -> list[SanXuatThuongToTruong]:
        """Mọi dòng thưởng/phạt rơi vào một kỳ lương — nguồn của cột `payroll_lines.thuong_to_truong`."""
        return list(
            self.db.scalars(
                select(SanXuatThuongToTruong).where(
                    SanXuatThuongToTruong.ky_nam == year,
                    SanXuatThuongToTruong.ky_thang == month,
                    SanXuatThuongToTruong.employee_id.is_not(None),
                )
            )
        )

    def add(self, obj: SanXuatThuongToTruong) -> SanXuatThuongToTruong:
        self.db.add(obj)
        return obj
