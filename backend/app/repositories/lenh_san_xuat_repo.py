"""Data access — Kế hoạch & Lệnh sản xuất (P0), spec `docs/spec-ke-hoach-san-xuat.md`.

Tầng DUY NHẤT chạm DB cho các bảng KẾ HOẠCH của module (`lenh_sx · lenh_item · print_form ·
gang_placement · routing_step`). KHÔNG nghiệp vụ ở đây (cổng phát AND, suy trạng thái… nằm ở
`LenhSanXuatService`). SQL qua bound-param SQLAlchemy (không nối chuỗi).

Đọc NỀN từ PTG + Đơn (KHÔNG chép): `PhieuThanhPhan` (quy cách/số con/máy), `PhieuThanhPham`
(routing theo `thu_tu` → `cong_doan_id`), `OrderLine.phieu_thanh_phan_id` (cầu đơn ↔ ấn phẩm).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.cong_doan import CongDoan
from ..models.customer import Customer
from ..models.lenh_san_xuat import (
    LENH_NHAP,
    PF_CHO_GHEP,
    GangPlacement,
    LenhItem,
    LenhSanXuat,
    PrintForm,
    RoutingStep,
)
from ..models.order import STATUS_ORDERED, Order, OrderLine
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
        to_id: int | None, ten: str = "",
    ) -> RoutingStep:
        step = RoutingStep(
            lenh_sx_id=lenh_sx_id, thu_tu=thu_tu, cong_doan_id=cong_doan_id,
            to_id=to_id, ten=ten,
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
