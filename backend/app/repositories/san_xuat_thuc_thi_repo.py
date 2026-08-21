"""Data-access cho lát THỰC THI của Thực hiện sản xuất (Giai đoạn 2 — §7 phân công/phiên chạy).

Giữ đúng tầng: mọi truy vấn/ghi DB của phân công · phiên chạy · khoảng tham gia gom ở đây; service
`services/san_xuat/thuc_thi.py` chỉ điều phối + kiểm luật. Tách khỏi `san_xuat_repo.py` (nền nhóm &
phát hành) để mỗi file một mối bận tâm.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.employee import STATUS_RESIGNED, Employee
from ..models.san_xuat import SanXuatCongViec
from ..models.san_xuat_thuc_thi import (
    PC_HOAT_DONG,
    SanXuatKhoangThamGia,
    SanXuatPhanCong,
    SanXuatPhienChay,
)


class SanXuatThucThiRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Đọc công việc + nhân viên ----------------------------------------------------------
    def cong_viec(self, cong_viec_id: int) -> SanXuatCongViec | None:
        return self.db.get(SanXuatCongViec, cong_viec_id)

    def nhan_vien(self, employee_id: int) -> Employee | None:
        return self.db.get(Employee, employee_id)

    def nhan_vien_cua_to(self, team_id: int) -> list[Employee]:
        """Nhân viên CÒN LÀM thuộc một tổ (để đổ danh chọn ở ô "Giao người"). Bỏ người đã nghỉ."""
        return list(
            self.db.scalars(
                select(Employee)
                .where(
                    Employee.department_id == team_id,
                    Employee.status != STATUS_RESIGNED,
                )
                .order_by(Employee.full_name)
            )
        )

    def nhan_vien_ho_tro_ung_vien(
        self, team_ids: set[int], tru_team_id: int
    ) -> list[Employee]:
        """Ứng viên HỖ TRỢ CHÉO (§9): thợ CÒN LÀM ở tổ SX KHÁC — người của các tổ trong `team_ids`
        trừ tổ đang thực hiện. Tổ gốc của họ suy từ `department_id`."""
        pool = {t for t in team_ids if t != tru_team_id}
        if not pool:
            return []
        return list(
            self.db.scalars(
                select(Employee)
                .where(
                    Employee.department_id.in_(pool),
                    Employee.status != STATUS_RESIGNED,
                )
                .order_by(Employee.full_name)
            )
        )

    # --- Phân công (roster) -----------------------------------------------------------------
    def phan_cong_hoat_dong(self, cong_viec_id: int) -> list[SanXuatPhanCong]:
        return list(
            self.db.scalars(
                select(SanXuatPhanCong)
                .where(
                    SanXuatPhanCong.cong_viec_id == cong_viec_id,
                    SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
                )
                .order_by(SanXuatPhanCong.id)
            )
        )

    def phan_cong(self, phan_cong_id: int) -> SanXuatPhanCong | None:
        return self.db.get(SanXuatPhanCong, phan_cong_id)

    def phan_cong_hoat_dong_cua(
        self, cong_viec_id: int, employee_id: int
    ) -> SanXuatPhanCong | None:
        return self.db.scalars(
            select(SanXuatPhanCong).where(
                SanXuatPhanCong.cong_viec_id == cong_viec_id,
                SanXuatPhanCong.employee_id == employee_id,
                SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
            )
        ).first()

    # --- Phiên chạy -------------------------------------------------------------------------
    def phien_dang_mo(self, cong_viec_id: int) -> SanXuatPhienChay | None:
        """Phiên còn mở (ket_thuc IS NULL) của một công việc — nhiều nhất MỘT theo bất biến."""
        return self.db.scalars(
            select(SanXuatPhienChay).where(
                SanXuatPhienChay.cong_viec_id == cong_viec_id,
                SanXuatPhienChay.ket_thuc.is_(None),
            )
        ).first()

    def so_phien(self, cong_viec_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count(SanXuatPhienChay.id)).where(
                    SanXuatPhienChay.cong_viec_id == cong_viec_id
                )
            )
            or 0
        )

    def cong_viec_co_phien(self, cv_ids: set[int]) -> set[int]:
        """Tập công việc (trong `cv_ids`) đã có ≥1 phiên chạy = ĐÃ BẮT ĐẦU (§4.3: chỉ cập-nhật /
        thu-hồi được việc CHƯA bắt đầu). Một truy vấn cho cả gói, không lặp từng việc."""
        if not cv_ids:
            return set()
        rows = self.db.execute(
            select(SanXuatPhienChay.cong_viec_id)
            .where(SanXuatPhienChay.cong_viec_id.in_(cv_ids))
            .distinct()
        ).scalars()
        return set(rows)

    def cac_phien(self, cong_viec_id: int) -> list[SanXuatPhienChay]:
        return list(
            self.db.scalars(
                select(SanXuatPhienChay)
                .where(SanXuatPhienChay.cong_viec_id == cong_viec_id)
                .order_by(SanXuatPhienChay.so_thu_tu)
            )
        )

    def phien_theo_cong_viec(
        self, cv_ids: set[int]
    ) -> dict[int, list[SanXuatPhienChay]]:
        """Phiên chạy của CẢ GÓI công việc, gom theo `cong_viec_id` — một truy vấn cho lớp
        thực-tế trên timeline (§5.1), không N+1. Mỗi list giữ thứ tự `so_thu_tu`."""
        if not cv_ids:
            return {}
        rows = self.db.scalars(
            select(SanXuatPhienChay)
            .where(SanXuatPhienChay.cong_viec_id.in_(cv_ids))
            .order_by(SanXuatPhienChay.cong_viec_id, SanXuatPhienChay.so_thu_tu)
        )
        out: dict[int, list[SanXuatPhienChay]] = {}
        for p in rows:
            out.setdefault(p.cong_viec_id, []).append(p)
        return out

    # --- Khoảng tham gia --------------------------------------------------------------------
    def khoang_mo_cua_nguoi(self, employee_id: int) -> SanXuatKhoangThamGia | None:
        """Khoảng tham gia còn MỞ của một người ở BẤT KỲ công việc nào — hàng rào luật §7.1
        (không hai khoảng chồng giờ)."""
        return self.db.scalars(
            select(SanXuatKhoangThamGia).where(
                SanXuatKhoangThamGia.employee_id == employee_id,
                SanXuatKhoangThamGia.ket_thuc.is_(None),
            )
        ).first()

    def khoang_mo_cua_phien(self, phien_chay_id: int) -> list[SanXuatKhoangThamGia]:
        return list(
            self.db.scalars(
                select(SanXuatKhoangThamGia).where(
                    SanXuatKhoangThamGia.phien_chay_id == phien_chay_id,
                    SanXuatKhoangThamGia.ket_thuc.is_(None),
                )
            )
        )

    def khoang_mo_cua_nguoi_o_cong_viec(
        self, cong_viec_id: int, employee_id: int
    ) -> SanXuatKhoangThamGia | None:
        return self.db.scalars(
            select(SanXuatKhoangThamGia).where(
                SanXuatKhoangThamGia.cong_viec_id == cong_viec_id,
                SanXuatKhoangThamGia.employee_id == employee_id,
                SanXuatKhoangThamGia.ket_thuc.is_(None),
            )
        ).first()

    def cac_khoang(self, cong_viec_id: int) -> list[SanXuatKhoangThamGia]:
        return list(
            self.db.scalars(
                select(SanXuatKhoangThamGia)
                .where(SanXuatKhoangThamGia.cong_viec_id == cong_viec_id)
                .order_by(SanXuatKhoangThamGia.id)
            )
        )

    # --- Ghi --------------------------------------------------------------------------------
    def add(self, obj) -> None:
        self.db.add(obj)

    def flush(self) -> None:
        self.db.flush()

    def dong_khoang(self, khoang: SanXuatKhoangThamGia, moc: datetime) -> None:
        khoang.ket_thuc = moc
