"""Data-access cho module Thực hiện sản xuất (Giai đoạn 1: nhóm & phát hành).

Giữ đúng tầng: mọi truy vấn/ghi DB của module gom ở đây; service chỉ điều phối. Gồm HAI nhóm:

  · ĐỒ THỊ LIÊN THÔNG — đọc quan hệ có sẵn (bài ghép ↔ thành viên, phụ thuộc chéo giữa LSX,
    cùng nhóm đơn hàng, routing, thời gian đã xếp) để tính thành phần liên thông + dựng snapshot.
  · GHI SNAPSHOT — upsert nhóm/thành viên + tạo gói/phiên bản/công việc/phụ thuộc.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.bai_ghep import BaiGhep, BaiGhepThanhVien
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from ..models.department import Department
from ..models.employee import Employee
from ..models.lsx import Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from ..models.machine import Machine
from ..models.order import OrderLine
from ..models.san_xuat import (
    CV_HOAN_THANH,
    GOI_DANG_PHAT_HANH,
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatNhom,
    SanXuatNhomLsx,
    SanXuatPhienBan,
    SanXuatPhuThuoc,
)
from ..models.san_xuat_kcs import SanXuatKcsTieuChi, SanXuatKcsTieuChiCongDoan
from ..models.xep_lich import XepLichCongDoan


class SanXuatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ================= ĐỒ THỊ LIÊN THÔNG =================

    def bai_ghep_ids_cua_lsx(self, lsx_ids: set[int]) -> set[int]:
        """Bài ghép nào có thành viên nằm trong tập LSX này."""
        if not lsx_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepThanhVien.bai_ghep_id).where(
                BaiGhepThanhVien.lsx_id.in_(lsx_ids)
            )
        ).scalars()
        return set(rows)

    def thanh_vien_so_con(self, bg_ids: set[int]) -> dict[int, int]:
        """`lsx_id → so_con_tren_to` của thành viên trong tập bài ghép — tỷ lệ toả sản lượng khi
        điểm toả tách batch chung thành sản lượng riêng từng LSX (§ điểm toả)."""
        if not bg_ids:
            return {}
        rows = self.db.execute(
            select(BaiGhepThanhVien.lsx_id, BaiGhepThanhVien.so_con_tren_to).where(
                BaiGhepThanhVien.bai_ghep_id.in_(bg_ids)
            )
        ).all()
        return {lsx_id: int(con or 0) for lsx_id, con in rows}

    def lsx_ids_cua_bai_ghep(self, bg_ids: set[int]) -> set[int]:
        """Toàn bộ LSX thành viên của các bài ghép này."""
        if not bg_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepThanhVien.lsx_id).where(
                BaiGhepThanhVien.bai_ghep_id.in_(bg_ids)
            )
        ).scalars()
        return set(rows)

    def cross_lsx_dep_neighbors(self, lsx_ids: set[int]) -> set[int]:
        """LSX nối với tập này qua cạnh phụ thuộc CHÉO (hai bước thuộc hai LSX khác nhau)."""
        edges = self._cross_lsx_edges_all()
        out: set[int] = set()
        for a, b in edges:
            if a in lsx_ids:
                out.add(b)
            if b in lsx_ids:
                out.add(a)
        return out

    def _cross_lsx_edges_all(self) -> list[tuple[int, int]]:
        """Mọi cạnh phụ thuộc chéo dưới dạng (lsx_truoc_id, lsx_sau_id), chỉ giữ cạnh KHÁC LSX."""
        Truoc = LsxCongDoan.__table__.alias("bt")
        Sau = LsxCongDoan.__table__.alias("bs")
        rows = self.db.execute(
            select(Truoc.c.lsx_id, Sau.c.lsx_id)
            .select_from(
                LsxCongDoanPhuThuoc.__table__
                .join(Truoc, LsxCongDoanPhuThuoc.buoc_truoc_id == Truoc.c.id)
                .join(Sau, LsxCongDoanPhuThuoc.buoc_sau_id == Sau.c.id)
            )
        ).all()
        return [(a, b) for (a, b) in rows if a != b]

    def cross_lsx_edges_chi_tiet(self, lsx_ids: set[int]) -> list[tuple[LsxCongDoan, LsxCongDoan]]:
        """Cạnh phụ thuộc chéo (buoc_truoc, buoc_sau) mà CẢ HAI bước thuộc LSX trong tập — dùng
        dựng snapshot bước ghép. Chỉ giữ cạnh nối hai LSX khác nhau (§3.2)."""
        rows = self.db.execute(
            select(LsxCongDoanPhuThuoc.buoc_truoc_id, LsxCongDoanPhuThuoc.buoc_sau_id)
        ).all()
        out: list[tuple[LsxCongDoan, LsxCongDoan]] = []
        for truoc_id, sau_id in rows:
            truoc = self.db.get(LsxCongDoan, truoc_id)
            sau = self.db.get(LsxCongDoan, sau_id)
            if truoc is None or sau is None:
                continue
            if truoc.lsx_id == sau.lsx_id:
                continue
            if truoc.lsx_id in lsx_ids and sau.lsx_id in lsx_ids:
                out.append((truoc, sau))
        return out

    def same_group_lsx(self, lsx_ids: set[int]) -> set[int]:
        """LSX cùng (order_id, nhom) với bất kỳ LSX nào trong tập — nhóm thành phẩm nối chúng
        thành một khối phát hành (§3.1). Dòng không có `nhom` KHÔNG kéo theo LSX khác."""
        if not lsx_ids:
            return set()
        keys = self._group_keys_of(lsx_ids)
        labelled = {(oid, nhom) for (oid, nhom) in keys if nhom is not None}
        if not labelled:
            return set()
        out: set[int] = set()
        rows = self.db.execute(
            select(Lsx.id, Lsx.order_id, OrderLine.nhom)
            .join(OrderLine, Lsx.order_line_id == OrderLine.id)
            .where(OrderLine.nhom.is_not(None))
        ).all()
        for lid, oid, nhom in rows:
            if (oid, nhom) in labelled:
                out.add(lid)
        return out

    def _group_keys_of(self, lsx_ids: set[int]) -> set[tuple[int, str | None]]:
        rows = self.db.execute(
            select(Lsx.order_id, OrderLine.nhom)
            .join(OrderLine, Lsx.order_line_id == OrderLine.id)
            .where(Lsx.id.in_(lsx_ids))
        ).all()
        return {(oid, nhom) for (oid, nhom) in rows}

    def nguon_nhom_cua_lsx(self, lsx_id: int) -> tuple[int, int, str | None, str] | None:
        """(order_id, order_line_id, nhom, description) của một LSX; None nếu thiếu dòng đơn."""
        row = self.db.execute(
            select(Lsx.order_id, Lsx.order_line_id, OrderLine.nhom, OrderLine.description)
            .join(OrderLine, Lsx.order_line_id == OrderLine.id)
            .where(Lsx.id == lsx_id)
        ).first()
        return tuple(row) if row is not None else None

    def routing_steps(self, lsx_id: int) -> list[LsxCongDoan]:
        return list(
            self.db.execute(
                select(LsxCongDoan)
                .where(LsxCongDoan.lsx_id == lsx_id)
                .order_by(LsxCongDoan.thu_tu, LsxCongDoan.id)
            ).scalars()
        )

    def bai_ghep_cong_doans(self, bg_id: int) -> list[BaiGhepCongDoan]:
        return list(
            self.db.execute(
                select(BaiGhepCongDoan)
                .where(BaiGhepCongDoan.bai_ghep_id == bg_id)
                .order_by(BaiGhepCongDoan.thu_tu, BaiGhepCongDoan.id)
            ).scalars()
        )

    def step_keys_da_ghep(self, bg_id: int) -> set[str]:
        """`lsx_step_key` của các bước LSX đã bị gộp vào bước dùng chung của bài ghép — để KHỎI
        đẻ công việc trùng cho bước đó ở tầng LSX (§3.3: một bài ghép = một bản ghi thực hiện)."""
        cd_ids = [
            cd.id for cd in self.bai_ghep_cong_doans(bg_id)
        ]
        if not cd_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.lsx_step_key).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id.in_(cd_ids)
            )
        ).scalars()
        return set(rows)

    def covered_step_keys_of_cd(self, bai_ghep_cong_doan_id: int) -> set[str]:
        """`lsx_step_key` mà MỘT bước dùng chung của bài ghép gộp lại (để nối phụ thuộc về đúng
        công việc dùng chung)."""
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.lsx_step_key).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id == bai_ghep_cong_doan_id
            )
        ).scalars()
        return set(rows)

    def lsx_ids_covered_by_cd(self, bai_ghep_cong_doan_id: int) -> set[int]:
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.lsx_id).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id == bai_ghep_cong_doan_id
            )
        ).scalars()
        return set(rows)

    def thoi_gian_lsx_step(self, lsx_cong_doan_id: int) -> tuple[int | None, object, object]:
        row = self.db.execute(
            select(XepLichCongDoan.may_id, XepLichCongDoan.start_at, XepLichCongDoan.finish_at)
            .where(XepLichCongDoan.lsx_cong_doan_id == lsx_cong_doan_id)
        ).first()
        return tuple(row) if row is not None else (None, None, None)

    def thoi_gian_bg_step(self, bai_ghep_cong_doan_id: int) -> tuple[int | None, object, object]:
        row = self.db.execute(
            select(XepLichCongDoan.may_id, XepLichCongDoan.start_at, XepLichCongDoan.finish_at)
            .where(XepLichCongDoan.bai_ghep_cong_doan_id == bai_ghep_cong_doan_id)
        ).first()
        return tuple(row) if row is not None else (None, None, None)

    def kcs_department_ids(self) -> set[int]:
        rows = self.db.execute(
            select(Department.id).where(Department.is_kcs.is_(True))
        ).scalars()
        return set(rows)

    def checklist_theo_cong_doan(self, cong_doan_ids: set[int]) -> dict[int, list[SanXuatKcsTieuChi]]:
        """{cong_doan_id: [tiêu chí active, sort thu_tu rồi id]} — MỘT truy vấn cho cả gói phát hành."""
        if not cong_doan_ids:
            return {}
        rows = self.db.execute(
            select(SanXuatKcsTieuChiCongDoan.cong_doan_id, SanXuatKcsTieuChi)
            .join(SanXuatKcsTieuChi, SanXuatKcsTieuChi.id == SanXuatKcsTieuChiCongDoan.tieu_chi_id)
            .where(
                SanXuatKcsTieuChiCongDoan.cong_doan_id.in_(cong_doan_ids),
                SanXuatKcsTieuChi.active.is_(True),
            )
            .order_by(SanXuatKcsTieuChi.thu_tu, SanXuatKcsTieuChi.id)
        ).all()
        out: dict[int, list[SanXuatKcsTieuChi]] = {}
        for cd_id, tc in rows:
            out.setdefault(cd_id, []).append(tc)
        return out

    # ================= GHI SNAPSHOT =================

    def get_nhom(self, order_id: int, khoa: str) -> SanXuatNhom | None:
        return self.db.execute(
            select(SanXuatNhom).where(
                SanXuatNhom.order_id == order_id, SanXuatNhom.khoa == khoa
            )
        ).scalar_one_or_none()

    def add(self, obj):
        self.db.add(obj)
        return obj

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def member_of_lsx(self, lsx_id: int) -> SanXuatNhomLsx | None:
        return self.db.execute(
            select(SanXuatNhomLsx).where(SanXuatNhomLsx.lsx_id == lsx_id)
        ).scalar_one_or_none()

    def goi_hien_tai_cua(
        self, lsx_ids: set[int], bai_ghep_ids: set[int]
    ) -> SanXuatGoiPhatHanh | None:
        """Gói phát hành đang hiệu lực có công việc trỏ tới bất kỳ LSX/bài ghép nào trong tập —
        để KHỎI đẻ gói trùng khi tái phát hành (versioning cập nhật §4.3 làm ở lát sau)."""
        conds = []
        if lsx_ids:
            conds.append(SanXuatCongViec.lsx_id.in_(lsx_ids))
        if bai_ghep_ids:
            conds.append(SanXuatCongViec.bai_ghep_id.in_(bai_ghep_ids))
        if not conds:
            return None
        from sqlalchemy import or_

        return self.db.execute(
            select(SanXuatGoiPhatHanh)
            .join(SanXuatCongViec, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
            .where(SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH, or_(*conds))
            .limit(1)
        ).scalar_one_or_none()

    def cong_viec_cua_goi(self, goi_id: int) -> list[SanXuatCongViec]:
        """Mọi công việc của một gói (không lọc phiên bản) — §4.3 chia đã/chưa bắt đầu để cập nhật."""
        return list(
            self.db.execute(
                select(SanXuatCongViec)
                .where(SanXuatCongViec.goi_id == goi_id)
                .order_by(SanXuatCongViec.id)
            ).scalars()
        )

    # ================= ĐÓNG NHÓM THÀNH PHẨM (§16) =================

    def nhom(self, nhom_id: int) -> SanXuatNhom | None:
        return self.db.get(SanXuatNhom, nhom_id)

    def cong_viec(self, cong_viec_id: int) -> SanXuatCongViec | None:
        """Một công việc theo id — router dùng để lần ra `nhom_id` khi bắn chốt-chặn đóng nhóm."""
        return self.db.get(SanXuatCongViec, cong_viec_id)

    def cong_viec_hien_tai_cua_nhom(self, nhom_id: int) -> list[SanXuatCongViec]:
        """Công việc SỐNG của nhóm — bỏ gói đã thu hồi. Đây là tập việc mà cổng đóng nhóm §16 soi.

        KHÔNG lọc thêm `phien_ban_so == version_hien_tai`: "Phát hành cập nhật" (§4.3) SỬA TRỰC
        TIẾP dòng `SanXuatCongViec` đã có (không đẻ dòng mới), chỉ bump `phien_ban_so` cho việc
        CHƯA bắt đầu; việc đã bắt đầu giữ nguyên dòng với `phien_ban_so` cũ. Lọc bằng nhau ở đây
        từng khiến việc đã chạy trước lần cập nhật bị rớt khỏi xét đóng nhóm — cùng một dòng, cùng
        đang sống, không phải bản "cũ bị thay thế"."""
        return list(
            self.db.execute(
                select(SanXuatCongViec)
                .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
                .where(
                    SanXuatCongViec.nhom_id == nhom_id,
                    SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
                )
                .order_by(SanXuatCongViec.id)
            ).scalars()
        )

    # ================= ĐỌC BÀN THỰC HIỆN TẠI TỔ (§11, §18 /work-items) =================

    def cong_viec_cua_to(
        self, department_ids: set[int], *, chi_chua_xong: bool = False
    ) -> list[SanXuatCongViec]:
        """Công việc ĐÃ PHÁT HÀNH mà tổ (`department_id`) phải làm — timeline bàn tổ. Chỉ đọc gói
        đang hiệu lực (bỏ gói đã thu hồi). Sắp theo giờ dự kiến (chưa xếp giờ dồn cuối), rồi id."""
        if not department_ids:
            return []
        q = (
            select(SanXuatCongViec)
            .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
            .where(
                SanXuatCongViec.department_id.in_(department_ids),
                SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
            )
        )
        if chi_chua_xong:
            q = q.where(SanXuatCongViec.trang_thai != CV_HOAN_THANH)
        rows = list(self.db.execute(q).scalars())
        rows.sort(key=lambda cv: (cv.du_kien_bat_dau is None, cv.du_kien_bat_dau, cv.id))
        return rows

    def dem_cho_lam_theo_to(self, department_ids: set[int]) -> dict[int, int]:
        """Số việc CHƯA XONG mỗi tổ (badge navbar §2.1) — chỉ đếm gói đang hiệu lực."""
        if not department_ids:
            return {}
        from sqlalchemy import func

        rows = self.db.execute(
            select(SanXuatCongViec.department_id, func.count(SanXuatCongViec.id))
            .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
            .where(
                SanXuatCongViec.department_id.in_(department_ids),
                SanXuatCongViec.trang_thai != CV_HOAN_THANH,
                SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
            )
            .group_by(SanXuatCongViec.department_id)
        ).all()
        return {dept_id: n for dept_id, n in rows if dept_id is not None}

    def lsx_nhan(self, lsx_ids: set[int]) -> dict[int, tuple[str, str]]:
        """{lsx_id: (mã, tên)} để gắn nhãn công việc — không có thì bỏ khỏi map."""
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(Lsx.id, Lsx.ma, Lsx.ten).where(Lsx.id.in_(lsx_ids))
        ).all()
        return {lid: (ma, ten) for lid, ma, ten in rows}

    def bai_ghep_nhan(self, bg_ids: set[int]) -> dict[int, tuple[str, str]]:
        if not bg_ids:
            return {}
        rows = self.db.execute(
            select(BaiGhep.id, BaiGhep.ma, BaiGhep.ten).where(BaiGhep.id.in_(bg_ids))
        ).all()
        return {bid: (ma, ten) for bid, ma, ten in rows}

    def may_nhan(self, may_ids: set[int]) -> dict[int, str]:
        if not may_ids:
            return {}
        rows = self.db.execute(
            select(Machine.id, Machine.name).where(Machine.id.in_(may_ids))
        ).all()
        return {mid: name for mid, name in rows}

    def nhom_nhan(self, nhom_ids: set[int]) -> dict[int, str]:
        """{nhom_id: nhãn nhóm thành phẩm} — ưu tiên `nhom_label`, rồi `ten`, rồi `khoa`."""
        if not nhom_ids:
            return {}
        rows = self.db.execute(
            select(SanXuatNhom.id, SanXuatNhom.nhom_label, SanXuatNhom.ten, SanXuatNhom.khoa)
            .where(SanXuatNhom.id.in_(nhom_ids))
        ).all()
        return {nid: (lbl or ten or khoa) for nid, lbl, ten, khoa in rows}

    def nhan_vien_nhan(self, emp_ids: set[int]) -> dict[int, tuple[str, int | None]]:
        """{employee_id: (họ tên, user_id)} — nhãn cho roster/khoảng tham gia của drawer thực thi.
        `user_id is None` = nhân viên không có tài khoản (vẫn giao + tính lương, §6)."""
        if not emp_ids:
            return {}
        rows = self.db.execute(
            select(Employee.id, Employee.full_name, Employee.user_id).where(
                Employee.id.in_(emp_ids)
            )
        ).all()
        return {eid: (ten, uid) for eid, ten, uid in rows}

    def to_ten_nhan(self, dept_ids: set[int]) -> dict[int, str]:
        """{department_id: tên tổ/phòng} — nhãn cho tổ gốc/tổ thực hiện của thỏa thuận hỗ trợ (§9)."""
        if not dept_ids:
            return {}
        rows = self.db.execute(
            select(Department.id, Department.name).where(Department.id.in_(dept_ids))
        ).all()
        return {did: name for did, name in rows}
