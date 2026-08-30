"""Repository Lệnh sản xuất (LSX) — mọi truy vấn DB của module Kế hoạch SX nằm ở đây.

Hàng chờ = đơn đã CHỐT + Sale đã bấm "Chuyển xuống sản xuất" (`orders.san_xuat_released_at`) và
còn dòng chưa lên lệnh. Không có cột trạng thái "đã tiếp nhận" — đơn tự rời hàng chờ khi mọi dòng
đã có LSX.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from ..models.lsx import LOAI_MOI, Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from ..models.order import STATUS_ORDERED, Order, OrderLine
from .catalog_base import SIZE_TRAN


class LsxRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------

    def get(self, lsx_id: int) -> Lsx | None:
        return self.db.execute(
            select(Lsx).where(Lsx.id == lsx_id).options(
                selectinload(Lsx.cong_doans).selectinload(LsxCongDoan.vat_tus),
                selectinload(Lsx.cong_doans).selectinload(LsxCongDoan.phu_thuoc),
            )
        ).scalar_one_or_none()

    def _dieu_kien(
        self,
        *,
        order_id: int | None = None,
        trang_thai: str | None = None,
        q: str | None = None,
        owner_ids: set[int] | None = None,
    ) -> list:
        """Bộ lọc dùng CHUNG cho `list` và `dem_theo_trang_thai`, để số dòng trong bảng và số
        trên tab không bao giờ nói hai chuyện khác nhau (cùng lý do như `catalog_base._loc_q`)."""
        conds = []
        if order_id is not None:
            conds.append(Lsx.order_id == order_id)
        if trang_thai:
            # Nhận NHIỀU trạng thái ngăn bằng dấu phẩy: tab "Nháp" của màn kế hoạch gửi
            # `nhap,cho_bo_sung` (hai cái nay chung một mặt), gửi một mã lẻ vẫn chạy như cũ.
            ma_tt = [t.strip() for t in trang_thai.split(",") if t.strip()]
            conds.append(Lsx.trang_thai.in_(ma_tt))
        if q:
            like = f"%{q.strip()}%"
            conds.append(or_(Lsx.ma.ilike(like), Lsx.ten.ilike(like)))
        if owner_ids is not None:
            conds.append(
                or_(Lsx.nguoi_phu_trach_id.in_(owner_ids), Lsx.created_by.in_(owner_ids))
            )
        return conds

    def list(self, *, page: int = 1, size: int = 50, **kw) -> tuple[list[Lsx], int]:
        """`(dòng của TRANG này, TỔNG số dòng khớp lọc)` — cùng khuôn `catalog_base.list`.

        LIMIT ở đây là bắt buộc chứ không phải tối ưu cho vui: `selectinload(cong_doans)` nhân
        theo số dòng trả về, nên không cắt trang thì 100.000 lệnh kéo theo ~400.000 dòng bước —
        đo ngày 18/08/2026 thấy endpoint không trả nổi kết quả trong 300 giây.
        """
        conds = self._dieu_kien(**kw)
        base = select(Lsx).options(selectinload(Lsx.cong_doans))
        dem = select(func.count()).select_from(Lsx)
        for c in conds:
            base = base.where(c)
            dem = dem.where(c)
        total = self.db.execute(dem).scalar_one()
        page, size = max(1, page), max(1, min(size, SIZE_TRAN))
        # `id` là chốt phụ: lệnh sinh cùng một lượt có `created_at` bằng nhau, thiếu chốt phụ thì
        # thứ tự đổi giữa hai lượt gọi ⇒ dòng nhảy qua lại giữa các trang.
        base = base.order_by(Lsx.created_at.desc(), Lsx.id.desc())
        return list(self.db.execute(base.offset((page - 1) * size).limit(size)).scalars()), total

    def dem_theo_trang_thai(self, **kw) -> dict[str, int]:
        """Số lệnh của TỪNG trạng thái, cùng bộ lọc nhưng BỎ `trang_thai`.

        Bỏ chính bộ lọc trạng thái là cố ý: tab đang không được chọn vẫn phải khoe số của nó
        (đúng ghi chú `facets` ở `routers/catalog_base`). Khoá `all` = tổng mọi trạng thái.
        """
        conds = self._dieu_kien(**{**kw, "trang_thai": None})
        stmt = select(Lsx.trang_thai, func.count()).group_by(Lsx.trang_thai)
        for c in conds:
            stmt = stmt.where(c)
        out = {tt: n for tt, n in self.db.execute(stmt).all()}
        out["all"] = sum(out.values())
        return out

    def cho_mrp(self, *, trang_thai: tuple[str, ...], include_ids: set[int]) -> list[Lsx]:
        """Mọi lệnh mà kế hoạch vật tư phải tính — KHÔNG cắt trang, và đó là cố ý.

        MRP cân giấy cho cả kho: cắt trang ở đây là âm thầm tính THIẾU vật tư, nên hàm này đứng
        riêng thay vì mượn `list()` (trần `SIZE_TRAN` của `list` sẽ chặt mất phần đuôi mà không
        ai hay). Cái đẩy được xuống SQL thì vẫn đẩy: lọc trạng thái chạy ở DB chứ không kéo cả
        bảng về rồi vứt bằng Python.
        """
        dk = Lsx.trang_thai.in_(trang_thai)
        if include_ids:
            # Lệnh được gọi đích danh (đang mở trên màn) phải có mặt dù trạng thái nào.
            dk = or_(dk, Lsx.id.in_(include_ids))
        return list(
            self.db.execute(
                select(Lsx)
                .options(selectinload(Lsx.cong_doans))
                .where(dk)
                .order_by(Lsx.created_at.desc(), Lsx.id.desc())
            ).scalars()
        )

    def theo_ids(self, ids: set[int]) -> list[Lsx]:
        """Đúng những lệnh được gọi tên — KHÔNG kèm bộ lọc trạng thái.

        `cho_mrp` luôn OR thêm `trang_thai IN TRANG_THAI_TINH` (đúng cho MRP toàn xưởng) nên nó
        KHÔNG dùng được cho đường "nhu cầu của MỘT công việc": mỗi lần mở form đề nghị cấp vật tư
        sẽ kéo về mọi lệnh còn sống. Đây là đường hẹp cho đúng ca đó.
        """
        ids = {int(i) for i in (ids or set()) if i}
        if not ids:
            return []
        return list(
            self.db.execute(
                select(Lsx)
                .options(selectinload(Lsx.cong_doans))
                .where(Lsx.id.in_(ids))
                .order_by(Lsx.created_at.desc(), Lsx.id.desc())
            ).scalars()
        )

    def by_order_lines(self, order_line_ids: list[int]) -> dict[int, Lsx]:
        """order_line_id → LSX 'sản xuất mới' đã tạo (nguồn của guard chống sinh trùng)."""
        if not order_line_ids:
            return {}
        rows = self.db.execute(
            select(Lsx).where(
                Lsx.order_line_id.in_(order_line_ids), Lsx.loai == LOAI_MOI
            )
        ).scalars()
        return {r.order_line_id: r for r in rows}

    def orders_ban_giao(self, *, page: int = 1, size: int = 50) -> tuple[list[Order], int]:
        """Đơn đã chốt + đã chuyển xuống SX mà CÒN nợ lệnh (kèm dòng đơn), mới nhất trước.

        Điều kiện "còn dòng chưa lên lệnh" nằm trong SQL chứ không lọc bằng Python sau khi kéo
        toàn bộ lịch sử đơn hàng về kèm mọi dòng đơn — cách cũ làm endpoint không trả nổi kết
        quả ở quy mô thật.
        """
        # Viết bằng MỘT TẬP ID (union) chứ không phải `or_(EXISTS…, NOT EXISTS…)` ngay trong WHERE:
        # dạng OR làm Postgres ước lượng chi phí ~1.000.000, vượt `jit_above_cost` nên nó bật JIT
        # và đốt 470 ms biên dịch cho một câu chỉ chạy 80 ms (đo 18/08/2026 trên 20.000 đơn).
        # Cùng một tập id dùng cho CẢ đếm lẫn lấy trang — hai câu không thể nói hai chuyện khác nhau.
        don_khac = aliased(Order)
        con_no = (
            select(OrderLine.order_id)
            .where(
                ~select(Lsx.id)
                .where(Lsx.order_line_id == OrderLine.id, Lsx.loai == LOAI_MOI)
                .exists()
            )
            .union(
                # Đơn KHÔNG có dòng nào vẫn nằm lại hàng chờ — đúng hành vi của bộ lọc Python cũ
                # (`if so_dong and so_co >= so_dong`). Bỏ vế này là âm thầm giấu mất loại đơn ấy.
                select(don_khac.id).where(
                    ~select(OrderLine.id).where(OrderLine.order_id == don_khac.id).exists()
                )
            )
            .subquery()
        )
        conds = (
            Order.status == STATUS_ORDERED,
            Order.san_xuat_released_at.is_not(None),
            Order.id.in_(select(con_no.c.order_id)),
        )
        total = self.db.execute(select(func.count()).select_from(Order).where(*conds)).scalar_one()
        page, size = max(1, page), max(1, min(size, SIZE_TRAN))
        # `lines` chỉ nạp cho các đơn CỦA TRANG (≤ size đơn), đủ để đếm dòng-đã-lên-lệnh mà không
        # kéo theo cả bảng dòng đơn.
        rows = self.db.execute(
            select(Order)
            .where(*conds)
            .options(selectinload(Order.lines))
            .order_by(Order.san_xuat_released_at.desc(), Order.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).scalars()
        return list(rows), total

    def count_by_order(self, order_ids: list[int]) -> dict[int, int]:
        """order_id → số LSX đã tạo (để biết đơn còn nợ lệnh hay không)."""
        if not order_ids:
            return {}
        rows = self.db.execute(
            select(Lsx.order_id, func.count())
            .where(Lsx.order_id.in_(order_ids))
            .group_by(Lsx.order_id)
        ).all()
        return {oid: n for oid, n in rows}

    def order_with_lines(self, order_id: int) -> Order | None:
        return self.db.execute(
            select(Order).where(Order.id == order_id).options(selectinload(Order.lines))
        ).scalar_one_or_none()

    def order_lines(self, order_id: int) -> list[OrderLine]:
        return list(
            self.db.execute(
                select(OrderLine).where(OrderLine.order_id == order_id).order_by(OrderLine.id)
            ).scalars()
        )

    # --- writes --------------------------------------------------------------

    def add(self, lsx: Lsx) -> Lsx:
        self.db.add(lsx)
        self.db.flush()
        return lsx

    def delete(self, lsx: Lsx) -> None:
        self.db.delete(lsx)
        self.db.flush()

    def sync_cong_doans(self, lsx: Lsx, rows: list[LsxCongDoan]) -> None:
        """Đồng bộ tại chỗ để giữ PK bước cho dòng lịch và cạnh phụ thuộc."""
        keep = {r.id for r in rows if r.id is not None}
        for old in list(lsx.cong_doans):
            if old.id not in keep:
                lsx.cong_doans.remove(old)
        for i, row in enumerate(rows):
            row.thu_tu = i
            if row not in lsx.cong_doans:
                lsx.cong_doans.append(row)
        self.db.flush()

    def phu_thuoc_toi_buoc(self, step_ids: set[int]) -> list[LsxCongDoanPhuThuoc]:
        if not step_ids:
            return []
        return list(self.db.execute(
            select(LsxCongDoanPhuThuoc).where(LsxCongDoanPhuThuoc.buoc_truoc_id.in_(step_ids))
        ).scalars())

    def commit(self) -> None:
        self.db.commit()
