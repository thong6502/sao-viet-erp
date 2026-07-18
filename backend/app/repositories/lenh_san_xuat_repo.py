"""Data access — Kế hoạch & Lệnh sản xuất (P0), spec `docs/spec-ke-hoach-san-xuat.md`.

Tầng DUY NHẤT chạm DB cho 6 bảng của module (`lenh_sx · print_form · gang_placement ·
san_luong · ban_giao · qc_defect`). KHÔNG nghiệp vụ ở đây (cổng phát AND, suy trạng thái…
nằm ở `LenhSanXuatService`). SQL qua bound-param SQLAlchemy (không nối chuỗi).

Đọc NỀN từ PTG + Đơn (KHÔNG chép): `PhieuThanhPhan` (quy cách/số con/máy), `PhieuThanhPham`
(routing theo `thu_tu` → `cong_doan_id`), `OrderLine.phieu_thanh_phan_id` (cầu đơn ↔ ấn phẩm).
Một repository / module (theo pattern `accounting_repo`), gom 6 bảng + helper đọc chéo.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.lenh_san_xuat import (
    LENH_NHAP,
    PF_CHO_GHEP,
    QC_CHO,
    BanGiao,
    GangPlacement,
    LenhSanXuat,
    PrintForm,
    QcDefect,
    SanLuong,
)
from ..models.order import OrderLine
from ..models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan


class LenhSanXuatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ================= Lệnh SX =================
    def get_lenh(self, lenh_id: int) -> LenhSanXuat | None:
        return self.db.get(LenhSanXuat, lenh_id)

    def lenh_by_order(self, order_id: int) -> list[LenhSanXuat]:
        return list(
            self.db.execute(
                select(LenhSanXuat)
                .where(LenhSanXuat.order_id == order_id)
                .order_by(LenhSanXuat.id.asc())
            ).scalars()
        )

    def ptp_ids_with_lenh(self, order_id: int) -> set[int]:
        """Tập `phieu_thanh_phan_id` của đơn ĐÃ có lệnh — nền cho bung IDEMPOTENT (không nhân đôi)."""
        rows = self.db.execute(
            select(LenhSanXuat.phieu_thanh_phan_id).where(LenhSanXuat.order_id == order_id)
        ).scalars()
        return {r for r in rows if r is not None}

    def create_lenh(
        self,
        *,
        order_id: int,
        phieu_thanh_phan_id: int | None = None,
        may_id: int | None = None,
        trang_thai: str = LENH_NHAP,
    ) -> LenhSanXuat:
        lenh = LenhSanXuat(
            order_id=order_id,
            phieu_thanh_phan_id=phieu_thanh_phan_id,
            may_id=may_id,
            trang_thai=trang_thai,
        )
        self.db.add(lenh)
        self.db.commit()
        self.db.refresh(lenh)
        return lenh

    def update_lenh(self, lenh: LenhSanXuat, **fields) -> LenhSanXuat:
        for k, v in fields.items():
            setattr(lenh, k, v)
        self.db.commit()
        self.db.refresh(lenh)
        return lenh

    def list_lenh(
        self, *, order_id: int | None = None, trang_thai: str | None = None,
        page: int = 1, size: int = 50,
    ) -> tuple[list[LenhSanXuat], int]:
        conds = []
        if order_id is not None:
            conds.append(LenhSanXuat.order_id == order_id)
        if trang_thai:
            conds.append(LenhSanXuat.trang_thai == trang_thai)
        base = select(LenhSanXuat)
        count_stmt = select(func.count()).select_from(LenhSanXuat)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(LenhSanXuat.id.desc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # ================= Tờ in (print_form) =================
    def get_form(self, form_id: int) -> PrintForm | None:
        return self.db.get(PrintForm, form_id)

    def create_form(self, **fields) -> PrintForm:
        form = PrintForm(trang_thai=fields.pop("trang_thai", PF_CHO_GHEP), **fields)
        self.db.add(form)
        self.db.commit()
        self.db.refresh(form)
        return form

    def update_form(self, form: PrintForm, **fields) -> PrintForm:
        for k, v in fields.items():
            setattr(form, k, v)
        self.db.commit()
        self.db.refresh(form)
        return form

    def delete_form(self, form: PrintForm) -> None:
        # gang_placement có FK ondelete=CASCADE → xoá tờ in kéo theo các dòng xếp bài.
        self.db.delete(form)
        self.db.commit()

    def list_forms(
        self, *, trang_thai: str | None = None, may_id: int | None = None,
        page: int = 1, size: int = 50,
    ) -> tuple[list[PrintForm], int]:
        conds = []
        if trang_thai:
            conds.append(PrintForm.trang_thai == trang_thai)
        if may_id is not None:
            conds.append(PrintForm.may_id == may_id)
        base = select(PrintForm)
        count_stmt = select(func.count()).select_from(PrintForm)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(PrintForm.id.desc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # ================= Xếp bài (gang_placement) =================
    def get_placement(self, placement_id: int) -> GangPlacement | None:
        return self.db.get(GangPlacement, placement_id)

    def add_placement(self, *, print_form_id: int, lenh_sx_id: int, so_con: int) -> GangPlacement:
        pl = GangPlacement(print_form_id=print_form_id, lenh_sx_id=lenh_sx_id, so_con=so_con)
        self.db.add(pl)
        self.db.commit()
        self.db.refresh(pl)
        return pl

    def update_placement(self, placement: GangPlacement, *, so_con: int) -> GangPlacement:
        placement.so_con = so_con
        self.db.commit()
        self.db.refresh(placement)
        return placement

    def delete_placement(self, placement: GangPlacement) -> None:
        self.db.delete(placement)
        self.db.commit()

    def placements_by_form(self, form_id: int) -> list[GangPlacement]:
        return list(
            self.db.execute(
                select(GangPlacement)
                .where(GangPlacement.print_form_id == form_id)
                .order_by(GangPlacement.id.asc())
            ).scalars()
        )

    def placements_by_lenh(self, lenh_id: int) -> list[GangPlacement]:
        return list(
            self.db.execute(
                select(GangPlacement)
                .where(GangPlacement.lenh_sx_id == lenh_id)
                .order_by(GangPlacement.id.asc())
            ).scalars()
        )

    def lenh_on_form(self, form_id: int) -> list[LenhSanXuat]:
        """Mọi LỆNH trên 1 tờ in (join placement) — nền CỔNG PHÁT AND (mọi lệnh phải duyệt mẫu)."""
        return list(
            self.db.execute(
                select(LenhSanXuat)
                .join(GangPlacement, GangPlacement.lenh_sx_id == LenhSanXuat.id)
                .where(GangPlacement.print_form_id == form_id)
                .order_by(LenhSanXuat.id.asc())
            ).scalars()
        )

    def forms_of_lenh(self, lenh_id: int) -> list[PrintForm]:
        """Mọi TỜ IN chứa 1 lệnh (1 lệnh có thể trải >1 tờ) — để đồng bộ trạng thái tờ khi duyệt mẫu."""
        return list(
            self.db.execute(
                select(PrintForm)
                .join(GangPlacement, GangPlacement.print_form_id == PrintForm.id)
                .where(GangPlacement.lenh_sx_id == lenh_id)
                .order_by(PrintForm.id.asc())
            ).scalars()
        )

    # ================= Sản lượng (log) =================
    def add_san_luong(
        self, *, lenh_sx_id: int, cong_doan_id: int | None, to_id: int | None,
        so_dat: int, so_hong: int, nguoi_ghi: int | None,
    ) -> SanLuong:
        row = SanLuong(
            lenh_sx_id=lenh_sx_id, cong_doan_id=cong_doan_id, to_id=to_id,
            so_dat=so_dat, so_hong=so_hong, nguoi_ghi=nguoi_ghi,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def san_luong_by_lenh(self, lenh_id: int) -> list[SanLuong]:
        return list(
            self.db.execute(
                select(SanLuong)
                .where(SanLuong.lenh_sx_id == lenh_id)
                .order_by(SanLuong.id.asc())
            ).scalars()
        )

    def sum_dat(self, lenh_id: int, *, cong_doan_id: int | None = None) -> int:
        """Σ số đạt của 1 lệnh (tuỳ chọn theo 1 công đoạn) — nuôi suy tiến độ / đủ SL."""
        stmt = select(func.coalesce(func.sum(SanLuong.so_dat), 0)).where(
            SanLuong.lenh_sx_id == lenh_id
        )
        if cong_doan_id is not None:
            stmt = stmt.where(SanLuong.cong_doan_id == cong_doan_id)
        return int(self.db.execute(stmt).scalar_one())

    # ================= Bàn giao (giao → xác nhận nhận) =================
    def add_ban_giao(
        self, *, lenh_sx_id: int, cong_doan_tu_id: int | None, cong_doan_toi_id: int | None,
        so_giao: int, to_giao_id: int | None, to_nhan_id: int | None,
    ) -> BanGiao:
        row = BanGiao(
            lenh_sx_id=lenh_sx_id, cong_doan_tu_id=cong_doan_tu_id,
            cong_doan_toi_id=cong_doan_toi_id, so_giao=so_giao,
            to_giao_id=to_giao_id, to_nhan_id=to_nhan_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_ban_giao(self, ban_giao_id: int) -> BanGiao | None:
        return self.db.get(BanGiao, ban_giao_id)

    def ban_giao_by_lenh(self, lenh_id: int) -> list[BanGiao]:
        return list(
            self.db.execute(
                select(BanGiao)
                .where(BanGiao.lenh_sx_id == lenh_id)
                .order_by(BanGiao.id.asc())
            ).scalars()
        )

    def update_ban_giao(self, ban_giao: BanGiao, **fields) -> BanGiao:
        for k, v in fields.items():
            setattr(ban_giao, k, v)
        self.db.commit()
        self.db.refresh(ban_giao)
        return ban_giao

    # ================= QC ghi lỗi (QC nêu → tổ trưởng xác nhận) =================
    def add_qc_defect(
        self, *, lenh_sx_id: int, cong_doan_id: int | None, to_bi_quy_id: int | None,
        anh_url: str | None, mo_ta: str | None, trang_thai: str = QC_CHO,
    ) -> QcDefect:
        row = QcDefect(
            lenh_sx_id=lenh_sx_id, cong_doan_id=cong_doan_id, to_bi_quy_id=to_bi_quy_id,
            anh_url=anh_url, mo_ta=mo_ta, trang_thai=trang_thai,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_qc_defect(self, qc_id: int) -> QcDefect | None:
        return self.db.get(QcDefect, qc_id)

    def qc_by_lenh(self, lenh_id: int) -> list[QcDefect]:
        return list(
            self.db.execute(
                select(QcDefect)
                .where(QcDefect.lenh_sx_id == lenh_id)
                .order_by(QcDefect.id.asc())
            ).scalars()
        )

    def update_qc_defect(self, qc: QcDefect, **fields) -> QcDefect:
        for k, v in fields.items():
            setattr(qc, k, v)
        self.db.commit()
        self.db.refresh(qc)
        return qc

    # ================= Đọc NỀN từ PTG / Đơn (không chép) =================
    def get_phieu_thanh_phan(self, ptp_id: int | None) -> PhieuThanhPhan | None:
        """Ấn phẩm nguồn (quy cách/giấy/khổ/màu/số con/máy) — nền của Lệnh + gợi ý ghép."""
        if ptp_id is None:
            return None
        return self.db.get(PhieuThanhPhan, ptp_id)

    def routing_of_ptp(self, ptp_id: int | None) -> list[PhieuThanhPham]:
        """Routing (finishing) theo `thu_tu` → mỗi bước có `cong_doan_id` (→ tổ qua department_id)."""
        if ptp_id is None:
            return []
        return list(
            self.db.execute(
                select(PhieuThanhPham)
                .where(PhieuThanhPham.thanh_phan_id == ptp_id)
                .order_by(PhieuThanhPham.thu_tu.asc(), PhieuThanhPham.id.asc())
            ).scalars()
        )

    def order_line_for_ptp(self, order_id: int, ptp_id: int | None) -> OrderLine | None:
        """Dòng đơn trỏ ấn phẩm này — lấy SL đặt (`qty`) làm đích 'đủ SL' khi nhập kho thành phẩm."""
        if ptp_id is None:
            return None
        return self.db.execute(
            select(OrderLine)
            .where(OrderLine.order_id == order_id, OrderLine.phieu_thanh_phan_id == ptp_id)
            .limit(1)
        ).scalar_one_or_none()
