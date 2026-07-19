"""Data access — Kế hoạch & Lệnh sản xuất (P0), spec `docs/spec-ke-hoach-san-xuat.md`.

Tầng DUY NHẤT chạm DB cho các bảng KẾ HOẠCH của module (`lenh_sx · lenh_item · print_form ·
gang_placement · routing_step · routing_step_assignment`). KHÔNG nghiệp vụ ở đây (cổng phát AND,
suy trạng thái, chọn scope… nằm ở `LenhSanXuatService`). SQL qua bound-param SQLAlchemy.

Đọc NỀN từ PTG + Đơn (KHÔNG chép): `PhieuThanhPhan` (quy cách/số con/máy), `PhieuThanhPham`
(routing theo `thu_tu` → `cong_doan_id`), `OrderLine.phieu_thanh_phan_id` (cầu đơn ↔ ấn phẩm).
"""
from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ..models.cong_doan import CongDoan
from ..models.customer import Customer
from ..models.employee import Employee
from ..models.lenh_san_xuat import (
    LENH_DANG_CHAY,
    LENH_NHAP,
    PF_CHO_GHEP,
    BanGiao,
    GangPlacement,
    LenhItem,
    LenhSanXuat,
    PrintForm,
    RoutingStep,
    RoutingStepAssignment,
    SanLuong,
)
from ..models.order import STATUS_ORDERED, Order, OrderLine
from ..models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan
from ..models.user import User


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
        han_giao_khach=None,
    ) -> LenhSanXuat:
        lenh = LenhSanXuat(
            order_id=order_id,
            phieu_thanh_phan_id=phieu_thanh_phan_id,
            may_id=may_id,
            trang_thai=trang_thai,
            han_giao_khach=han_giao_khach,
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

    def lenh_by_trang_thai(self, statuses: list[str]) -> list[LenhSanXuat]:
        """Lệnh theo tập trạng thái (④ lịch chạy: nhap + dang_chay). FE tự xếp `thu_tu_chay` trong từng ô."""
        if not statuses:
            return []
        return list(
            self.db.execute(
                select(LenhSanXuat)
                .where(LenhSanXuat.trang_thai.in_(statuses))
                .order_by(LenhSanXuat.id.asc())
            ).scalars()
        )

    # ================= Bài con (lenh_item) — 1 lệnh ôm nhiều ấn phẩm =================
    def create_lenh_item(
        self, *, lenh_sx_id: int, phieu_thanh_phan_id: int | None,
        order_line_id: int | None = None, thu_tu: int = 0,
    ) -> LenhItem:
        row = LenhItem(
            lenh_sx_id=lenh_sx_id, phieu_thanh_phan_id=phieu_thanh_phan_id,
            order_line_id=order_line_id, thu_tu=thu_tu,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def items_of_lenh(self, lenh_id: int) -> list[LenhItem]:
        return list(
            self.db.execute(
                select(LenhItem)
                .where(LenhItem.lenh_sx_id == lenh_id)
                .order_by(LenhItem.thu_tu.asc(), LenhItem.id.asc())
            ).scalars()
        )

    def get_lenh_item(self, item_id: int) -> LenhItem | None:
        return self.db.get(LenhItem, item_id)

    def update_lenh_item(self, item: LenhItem, **fields) -> LenhItem:
        for k, v in fields.items():
            setattr(item, k, v)
        self.db.commit()
        self.db.refresh(item)
        return item

    def ptp_ids_in_order(self, order_id: int) -> set[int]:
        """Ptp đã thuộc lệnh nào của đơn (UNION bài con `lenh_item` + cột đại diện `lenh_sx`) — nền
        idempotent / chặn PICK trùng ấn phẩm. Bao cả lệnh cũ (chưa có bài con) qua cột đại diện."""
        rep = self.db.execute(
            select(LenhSanXuat.phieu_thanh_phan_id).where(LenhSanXuat.order_id == order_id)
        ).scalars()
        items = self.db.execute(
            select(LenhItem.phieu_thanh_phan_id)
            .join(LenhSanXuat, LenhSanXuat.id == LenhItem.lenh_sx_id)
            .where(LenhSanXuat.order_id == order_id)
        ).scalars()
        return {r for r in rep if r is not None} | {r for r in items if r is not None}

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

    # ================= Routing step (routing riêng mỗi lệnh — §13.2) =================
    def cong_doan_by_id(self, cong_doan_id: int | None) -> CongDoan | None:
        """Công đoạn danh mục — để snapshot tổ (`department_id`) + tên khi copy/sửa routing."""
        if cong_doan_id is None:
            return None
        return self.db.get(CongDoan, cong_doan_id)

    def create_routing_step(
        self, *, lenh_sx_id: int, thu_tu: int, cong_doan_id: int | None,
        to_id: int | None, ten: str = "", ghi_chu: str | None = None,
        quy_cach: str | None = None,
    ) -> RoutingStep:
        step = RoutingStep(
            lenh_sx_id=lenh_sx_id, thu_tu=thu_tu, cong_doan_id=cong_doan_id,
            to_id=to_id, ten=ten, ghi_chu=ghi_chu, quy_cach=quy_cach,
        )
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        return step

    def routing_by_lenh(self, lenh_id: int) -> list[RoutingStep]:
        return list(
            self.db.execute(
                select(RoutingStep)
                .where(RoutingStep.lenh_sx_id == lenh_id)
                .order_by(RoutingStep.thu_tu.asc(), RoutingStep.id.asc())
            ).scalars()
        )

    def get_routing_step(self, step_id: int) -> RoutingStep | None:
        return self.db.get(RoutingStep, step_id)

    def update_routing_step(self, step: RoutingStep, **fields) -> RoutingStep:
        for k, v in fields.items():
            setattr(step, k, v)
        self.db.commit()
        self.db.refresh(step)
        return step

    def delete_routing_step(self, step: RoutingStep) -> None:
        self.db.delete(step)
        self.db.commit()

    def max_thu_tu(self, lenh_id: int) -> int:
        """Thứ tự lớn nhất trong routing của lệnh — để thêm bước vào cuối."""
        return int(self.db.execute(
            select(func.coalesce(func.max(RoutingStep.thu_tu), 0))
            .where(RoutingStep.lenh_sx_id == lenh_id)
        ).scalar_one())

    # ================= Gán thợ + hộp việc tổ (Lát 1) =================
    def assign_worker(self, *, step_id: int, user_id: int, by: int | None) -> RoutingStepAssignment:
        """Gán 1 thợ vào 1 bước routing. IDEMPOTENT: đã gán → trả bản ghi cũ (không nhân đôi)."""
        existing = self.db.execute(
            select(RoutingStepAssignment).where(
                RoutingStepAssignment.routing_step_id == step_id,
                RoutingStepAssignment.user_id == user_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = RoutingStepAssignment(routing_step_id=step_id, user_id=user_id, assigned_by=by)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def unassign_worker(self, *, step_id: int, user_id: int) -> None:
        row = self.db.execute(
            select(RoutingStepAssignment).where(
                RoutingStepAssignment.routing_step_id == step_id,
                RoutingStepAssignment.user_id == user_id,
            )
        ).scalar_one_or_none()
        if row is not None:
            self.db.delete(row)
            self.db.commit()

    def assignees_of_steps(self, step_ids: list[int]) -> dict[int, list[int]]:
        """{routing_step_id: [user_id...]} cho tập bước (1 truy vấn) — nuôi thẻ routing ở hộp tổ."""
        if not step_ids:
            return {}
        out: dict[int, list[int]] = {}
        for sid, uid in self.db.execute(
            select(RoutingStepAssignment.routing_step_id, RoutingStepAssignment.user_id)
            .where(RoutingStepAssignment.routing_step_id.in_(step_ids))
            .order_by(RoutingStepAssignment.id.asc())
        ):
            out.setdefault(sid, []).append(uid)
        return out

    def lenh_of_to(self, to_ids: list[int]) -> list[LenhSanXuat]:
        """Lệnh ĐANG CHẠY có ≥1 bước routing thuộc tổ trong `to_ids` (hộp tổ trưởng — FULL). distinct
        vì 1 lệnh có thể có nhiều bước cùng tổ."""
        if not to_ids:
            return []
        return list(self.db.execute(
            select(LenhSanXuat)
            .join(RoutingStep, RoutingStep.lenh_sx_id == LenhSanXuat.id)
            .where(LenhSanXuat.trang_thai == LENH_DANG_CHAY, RoutingStep.to_id.in_(to_ids))
            .order_by(LenhSanXuat.id.desc())
            .distinct()
        ).scalars())

    def lenh_assigned_to(self, *, user_id: int, to_ids: list[int]) -> list[LenhSanXuat]:
        """Lệnh ĐANG CHẠY có bước (thuộc tổ trong `to_ids`) mà `user_id` ĐƯỢC GÁN (hộp việc thợ)."""
        if not to_ids:
            return []
        return list(self.db.execute(
            select(LenhSanXuat)
            .join(RoutingStep, RoutingStep.lenh_sx_id == LenhSanXuat.id)
            .join(RoutingStepAssignment, RoutingStepAssignment.routing_step_id == RoutingStep.id)
            .where(
                LenhSanXuat.trang_thai == LENH_DANG_CHAY,
                RoutingStep.to_id.in_(to_ids),
                RoutingStepAssignment.user_id == user_id,
            )
            .order_by(LenhSanXuat.id.desc())
            .distinct()
        ).scalars())

    def count_lenh_by_to(self, to_ids: list[int]) -> dict[int, int]:
        """{to_id: số lệnh đang chạy có bước thuộc tổ} — badge navbar (view FULL tổ trưởng/giám sát)."""
        if not to_ids:
            return {}
        rows = self.db.execute(
            select(RoutingStep.to_id, func.count(distinct(RoutingStep.lenh_sx_id)))
            .join(LenhSanXuat, LenhSanXuat.id == RoutingStep.lenh_sx_id)
            .where(LenhSanXuat.trang_thai == LENH_DANG_CHAY, RoutingStep.to_id.in_(to_ids))
            .group_by(RoutingStep.to_id)
        )
        return {tid: int(c) for tid, c in rows if tid is not None}

    def count_assigned_by_to(self, *, user_id: int, to_ids: list[int]) -> dict[int, int]:
        """{to_id: số lệnh thợ được gán ở tổ} — badge navbar (view thợ)."""
        if not to_ids:
            return {}
        rows = self.db.execute(
            select(RoutingStep.to_id, func.count(distinct(RoutingStep.lenh_sx_id)))
            .join(LenhSanXuat, LenhSanXuat.id == RoutingStep.lenh_sx_id)
            .join(RoutingStepAssignment, RoutingStepAssignment.routing_step_id == RoutingStep.id)
            .where(
                LenhSanXuat.trang_thai == LENH_DANG_CHAY,
                RoutingStep.to_id.in_(to_ids),
                RoutingStepAssignment.user_id == user_id,
            )
            .group_by(RoutingStep.to_id)
        )
        return {tid: int(c) for tid, c in rows if tid is not None}

    # ================= Sản lượng + bàn giao (Lát 2 — thực thi) =================
    def create_san_luong(
        self, *, lenh_id: int, step_id: int, to_id: int | None,
        so_dat: int, so_hong: int, don_vi: str, ghi_chu: str | None, nguoi_ghi: int | None,
    ) -> SanLuong:
        row = SanLuong(
            lenh_sx_id=lenh_id, routing_step_id=step_id, to_id=to_id,
            so_dat=so_dat, so_hong=so_hong, don_vi=don_vi, ghi_chu=ghi_chu, nguoi_ghi=nguoi_ghi,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def san_luong_totals(self, step_ids: list[int]) -> dict[int, dict]:
        """{routing_step_id: {so_dat, so_hong, don_vi}} — tổng CỘNG DỒN per bước (đơn vị = bản ghi mới nhất)."""
        if not step_ids:
            return {}
        out: dict[int, dict] = {}
        for sid, dat, hong in self.db.execute(
            select(
                SanLuong.routing_step_id,
                func.coalesce(func.sum(SanLuong.so_dat), 0),
                func.coalesce(func.sum(SanLuong.so_hong), 0),
            ).where(SanLuong.routing_step_id.in_(step_ids)).group_by(SanLuong.routing_step_id)
        ):
            out[sid] = {"so_dat": int(dat), "so_hong": int(hong), "don_vi": "to"}
        for sid, dv in self.db.execute(
            select(SanLuong.routing_step_id, SanLuong.don_vi)
            .where(SanLuong.routing_step_id.in_(step_ids)).order_by(SanLuong.id.asc())
        ):
            if sid in out:
                out[sid]["don_vi"] = dv   # asc → giữ đơn vị của bản ghi MỚI NHẤT
        return out

    def create_ban_giao(
        self, *, lenh_id: int, tu_step_id: int | None, toi_step_id: int | None,
        to_giao: int | None, to_nhan: int | None, so_giao: int, don_vi: str, nguoi_giao: int | None,
    ) -> BanGiao:
        row = BanGiao(
            lenh_sx_id=lenh_id, tu_step_id=tu_step_id, toi_step_id=toi_step_id,
            to_giao=to_giao, to_nhan=to_nhan, so_giao=so_giao, don_vi=don_vi, nguoi_giao=nguoi_giao,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_ban_giao(self, bg_id: int) -> BanGiao | None:
        return self.db.get(BanGiao, bg_id)

    def update_ban_giao(self, bg: BanGiao, **fields) -> BanGiao:
        for k, v in fields.items():
            setattr(bg, k, v)
        self.db.commit()
        self.db.refresh(bg)
        return bg

    def ban_giao_out_totals(self, step_ids: list[int]) -> dict[int, int]:
        """{tu_step_id: Σ số đã GIAO đi từ bước} — hiện 'đã giao X'."""
        if not step_ids:
            return {}
        rows = self.db.execute(
            select(BanGiao.tu_step_id, func.coalesce(func.sum(BanGiao.so_giao), 0))
            .where(BanGiao.tu_step_id.in_(step_ids)).group_by(BanGiao.tu_step_id)
        )
        return {sid: int(s) for sid, s in rows if sid is not None}

    def ban_giao_in_pending(self, step_ids: list[int]) -> dict[int, BanGiao]:
        """{toi_step_id: bàn giao ĐẾN chưa xác nhận (cũ nhất)} — nuôi nút 'Xác nhận nhận'."""
        if not step_ids:
            return {}
        out: dict[int, BanGiao] = {}
        for bg in self.db.execute(
            select(BanGiao)
            .where(BanGiao.toi_step_id.in_(step_ids), BanGiao.nhan_at.is_(None))
            .order_by(BanGiao.id.desc())
        ).scalars():
            out[bg.toi_step_id] = bg   # desc → last-write = id nhỏ nhất = phiếu cũ nhất
        return out

    def workers_in_to(self, to_id: int) -> list[tuple[int, str, str | None]]:
        """Thợ (Employee có `user_id`) thuộc 1 tổ — để tổ trưởng gán: (user_id, tên, chức vụ)."""
        rows = self.db.execute(
            select(Employee.user_id, Employee.full_name, Employee.position)
            .where(Employee.department_id == to_id, Employee.user_id.isnot(None))
            .order_by(Employee.full_name.asc())
        )
        return [(uid, name, pos) for uid, name, pos in rows]

    def user_display_names(self, user_ids: list[int]) -> dict[int, str]:
        """Tên hiển thị theo user_id (assignees) — ưu tiên hồ sơ NV (`full_name`), lùi `User.name`."""
        if not user_ids:
            return {}
        names: dict[int, str] = {}
        for uid, full in self.db.execute(
            select(Employee.user_id, Employee.full_name)
            .where(Employee.user_id.in_(user_ids), Employee.full_name.isnot(None))
        ):
            if uid is not None and full:
                names[uid] = full
        missing = [u for u in user_ids if u not in names]
        if missing:
            for uid, name in self.db.execute(
                select(User.id, User.name).where(User.id.in_(missing))
            ):
                names[uid] = name
        return names

    # ================= Đọc NỀN từ PTG / Đơn (không chép) =================
    def get_phieu_thanh_phan(self, ptp_id: int | None) -> PhieuThanhPhan | None:
        """Ấn phẩm nguồn (quy cách/giấy/khổ/màu/số con/máy) — nền của Lệnh + gợi ý ghép."""
        if ptp_id is None:
            return None
        return self.db.get(PhieuThanhPhan, ptp_id)

    def phieu_thanh_phan_by_ids(self, ids: list[int]) -> dict[int, PhieuThanhPhan]:
        """Ấn phẩm theo tập id (1 truy vấn) — nuôi quy cách rút gọn cho sổ hàng chờ (tránh N+1)."""
        if not ids:
            return {}
        rows = self.db.execute(
            select(PhieuThanhPhan).where(PhieuThanhPhan.id.in_(ids))
        ).scalars()
        return {r.id: r for r in rows}

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

    def order_line_by_id(self, order_line_id: int | None) -> OrderLine | None:
        """Dòng đơn theo id (bài con giữ `order_line_id` → đọc SL đích SỐNG, không chép)."""
        if order_line_id is None:
            return None
        return self.db.get(OrderLine, order_line_id)

    # ================= Handoff: đơn chốt CHỜ lên kế hoạch (§5.1) =================
    def covered_ptp_ids(self) -> set[int]:
        """Tập ptp ĐÃ thuộc lệnh nào (union đại diện `lenh_sx` + bài con `lenh_item`) — GLOBAL. Mỗi
        ptp duy nhất theo dòng đơn nên set global đủ để lọc 'ấn phẩm chưa lên lệnh' ở sổ hàng chờ."""
        rep = self.db.execute(
            select(LenhSanXuat.phieu_thanh_phan_id).where(LenhSanXuat.phieu_thanh_phan_id.isnot(None))
        ).scalars()
        items = self.db.execute(
            select(LenhItem.phieu_thanh_phan_id).where(LenhItem.phieu_thanh_phan_id.isnot(None))
        ).scalars()
        return {r for r in rep if r is not None} | {r for r in items if r is not None}

    def orders_waiting_for_planning(self) -> list[Order]:
        """Đơn ĐÃ CHỐT (+ Sale đã 'Chuyển xuống SX') còn ≥1 ấn phẩm CHƯA lên lệnh — sổ hàng chờ để kế
        hoạch PICK. 'Chưa lên lệnh' = ptp KHÔNG nằm trong `lenh_sx`/`lenh_item` → pick DẦN: đơn ở lại
        tới khi MỌI ấn phẩm đã lên lệnh. Dòng nhập tay (ptp NULL) không tính. Gấp lên đầu."""
        rep_covered = select(LenhSanXuat.phieu_thanh_phan_id).where(
            LenhSanXuat.phieu_thanh_phan_id.isnot(None)
        )
        item_covered = select(LenhItem.phieu_thanh_phan_id).where(
            LenhItem.phieu_thanh_phan_id.isnot(None)
        )
        have_uncovered = (
            select(OrderLine.order_id)
            .where(
                OrderLine.phieu_thanh_phan_id.isnot(None),
                OrderLine.phieu_thanh_phan_id.notin_(rep_covered),
                OrderLine.phieu_thanh_phan_id.notin_(item_covered),
            )
            .distinct()
            .scalar_subquery()
        )
        return list(self.db.execute(
            select(Order)
            .where(
                Order.status == STATUS_ORDERED,
                Order.san_xuat_released_at.isnot(None),  # chỉ đơn Sale ĐÃ "Chuyển xuống SX"
                Order.id.in_(have_uncovered),
            )
            .order_by(Order.is_rush.desc(), Order.id.desc())
        ).scalars())

    def order_lines_by_order_ids(self, order_ids: list[int]) -> list[OrderLine]:
        """Dòng của 1 tập đơn (1 truy vấn) — nuôi ngữ cảnh ấn phẩm cho hàng chờ (tránh N+1)."""
        if not order_ids:
            return []
        return list(self.db.execute(
            select(OrderLine)
            .where(OrderLine.order_id.in_(order_ids))
            .order_by(OrderLine.id.asc())
        ).scalars())

    def customer_names_by_ids(self, ids: list[int]) -> dict[int, str]:
        """Tên khách theo id (1 truy vấn) — bám khuôn batch của `order_repo.list()`."""
        if not ids:
            return {}
        return {
            cid: name
            for cid, name in self.db.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(ids))
            )
        }
