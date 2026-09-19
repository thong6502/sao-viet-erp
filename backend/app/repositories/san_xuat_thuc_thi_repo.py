"""Data-access cho lát THỰC THI của Thực hiện sản xuất (Giai đoạn 2 — §7 phân công/phiên chạy).

Giữ đúng tầng: mọi truy vấn/ghi DB của phân công · phiên chạy · khoảng tham gia gom ở đây; service
`services/san_xuat/thuc_thi.py` chỉ điều phối + kiểm luật. Tách khỏi `san_xuat_repo.py` (nền nhóm &
phát hành) để mỗi file một mối bận tâm.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.bai_ghep_cong_doan import BaiGhepCongDoan
from ..models.cong_doan import CongDoan
from ..models.employee import STATUS_RESIGNED, Employee
from ..models.lsx import LsxCongDoan
from ..models.may_thiet_bi import MayThietBi
from ..models.san_xuat import CV_PHAT_HANH, CV_TAM_DUNG, SanXuatCongViec
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

    def cong_viec_mo_theo_khuon(self, khuon_id: int) -> list[SanXuatCongViec]:
        """Việc CHƯA xong mà ảnh chụp khuôn trỏ con dao `khuon_id` — để lật chữ tình trạng trong
        ảnh chụp khi dao về. Việc đã xong bỏ qua: nó đã qua cổng nhận khuôn, chip đọc "đã nhận"."""
        from ..models.san_xuat import CV_HOAN_THANH

        return list(self.db.scalars(
            select(SanXuatCongViec).where(
                SanXuatCongViec.khuon_json["id"].as_integer() == khuon_id,
                SanXuatCongViec.trang_thai != CV_HOAN_THANH,
            )
        ))

    def cong_doan_cua_viec(self, cv: SanXuatCongViec) -> CongDoan | None:
        """Công đoạn DANH MỤC đứng sau công việc, đi qua bước kế hoạch (bài ghép hoặc lệnh).

        None khi bước nguồn đã mất (replace_routing tái sinh id) hoặc bước chưa chọn công đoạn.
        """
        buoc = None
        if cv.bai_ghep_cong_doan_id is not None:
            buoc = self.db.get(BaiGhepCongDoan, cv.bai_ghep_cong_doan_id)
        elif cv.lsx_cong_doan_id is not None:
            buoc = self.db.get(LsxCongDoan, cv.lsx_cong_doan_id)
        cd_id = getattr(buoc, "cong_doan_id", None)
        return self.db.get(CongDoan, cd_id) if cd_id else None

    def may_con_dung(self) -> list[MayThietBi]:
        """Máy còn dùng (`active`) theo mã — tập gốc cho ô "Đổi máy" trước khi lọc theo công đoạn."""
        return list(self.db.scalars(
            select(MayThietBi).where(MayThietBi.active.is_(True)).order_by(MayThietBi.ma)
        ))

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

    def viec_dang_chay_cua_nhieu(self, employee_ids: set[int]) -> dict[int, SanXuatCongViec]:
        """{employee_id: công việc người đó ĐANG CHẠY} — suy từ khoảng tham gia còn mở, cùng nguồn
        với hàng rào "không hai khoảng chồng giờ" (§7.1). Người không chạy gì thì vắng khỏi map."""
        if not employee_ids:
            return {}
        rows = self.db.execute(
            select(SanXuatKhoangThamGia.employee_id, SanXuatCongViec)
            .join(SanXuatCongViec, SanXuatCongViec.id == SanXuatKhoangThamGia.cong_viec_id)
            .where(
                SanXuatKhoangThamGia.employee_id.in_(employee_ids),
                SanXuatKhoangThamGia.ket_thuc.is_(None),
            )
            .order_by(SanXuatKhoangThamGia.bat_dau)
        ).all()
        ra: dict[int, SanXuatCongViec] = {}
        for eid, cv in rows:
            ra.setdefault(eid, cv)
        return ra

    def viec_cho_cua_nhieu(self, employee_ids: set[int]) -> dict[int, list[SanXuatCongViec]]:
        """{employee_id: các việc người đó đang CÓ TÊN trong tổ mà việc chưa chạy hoặc đang tạm
        dừng} — giao trước để xếp người, chưa phải bận. Việc tạm dừng xếp trước (người đó đang dở
        việc ấy), rồi việc chưa chạy theo giờ dự kiến. Người không có việc nào thì vắng khỏi map."""
        if not employee_ids:
            return {}
        rows = self.db.execute(
            select(SanXuatPhanCong.employee_id, SanXuatCongViec)
            .join(SanXuatCongViec, SanXuatCongViec.id == SanXuatPhanCong.cong_viec_id)
            .where(
                SanXuatPhanCong.employee_id.in_(employee_ids),
                SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
                SanXuatCongViec.trang_thai.in_((CV_PHAT_HANH, CV_TAM_DUNG)),
            )
            .order_by(
                SanXuatCongViec.trang_thai != CV_TAM_DUNG,
                SanXuatCongViec.du_kien_bat_dau.is_(None),
                SanXuatCongViec.du_kien_bat_dau,
                SanXuatCongViec.id,
            )
        ).all()
        ra: dict[int, list[SanXuatCongViec]] = {}
        for eid, cv in rows:
            ra.setdefault(eid, []).append(cv)
        return ra

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

    def nhan_vien_theo_user(self, user_id: int) -> Employee | None:
        """Hồ sơ nhân viên của một tài khoản — thợ mở bàn tổ thì lọc việc theo hồ sơ này."""
        return self.db.scalars(
            select(Employee).where(Employee.user_id == user_id)
        ).first()

    def cong_viec_ids_duoc_giao(
        self, employee_id: int, cong_viec_ids: set[int]
    ) -> set[int]:
        """Trong tập công việc đưa vào, những việc nhân viên này CÒN đang được giao (§7.1).

        Một truy vấn cho cả bàn tổ — không hỏi từng dòng."""
        if not cong_viec_ids:
            return set()
        return set(
            self.db.scalars(
                select(SanXuatPhanCong.cong_viec_id).where(
                    SanXuatPhanCong.cong_viec_id.in_(cong_viec_ids),
                    SanXuatPhanCong.employee_id == employee_id,
                    SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
                )
            )
        )

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
