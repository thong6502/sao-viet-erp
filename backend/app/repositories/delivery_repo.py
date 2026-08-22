"""Repository — Giao hàng (docs/prd-giao-hang.md).

Chỉ truy vấn/ghi DB. Luật nghiệp vụ (chặn vượt số còn phải giao, trùng lịch tài xế, chuyển trạng
thái, sinh đề nghị xuất hàng) nằm ở `services/delivery_service.py`.

Hai truy vấn ở đây là XƯƠNG SỐNG của bản thiết kế, đọc kỹ trước khi "tối ưu":

* `da_giao_theo_dong()` — "đã giao bao nhiêu" tính bằng `SUM` từ `delivery_trip_lines`, KHÔNG đọc
  cột cộng dồn nào. Repo không có Alembic; một cột cộng dồn lệch là không có đường phát hiện.
* `trung_lich()` — hai chuyến của CÙNG một tài xế trùng khi hai khoảng
  `[gio_lay_hang, gio_du_kien_giao]` GIAO NHAU. Định nghĩa nằm đây, một chỗ duy nhất.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models.delivery import (
    LAN_GIAO_CO_HANG_DEN_TAY,
    LAN_GIAO_DANG_CHAY,
    YC_CHO_LEN_KE_HOACH,
    YC_DA_HUY,
    DeliveryRequest,
    DeliveryRequestLine,
    DeliveryStatusHistory,
    DeliveryTrip,
    DeliveryTripAttachment,
    DeliveryTripLine,
)


class DeliveryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Yêu cầu giao hàng --------------------------------------------------------------
    def get_request(self, request_id: int) -> DeliveryRequest | None:
        return self.db.execute(
            select(DeliveryRequest)
            .options(selectinload(DeliveryRequest.lines),
                     selectinload(DeliveryRequest.trips).selectinload(DeliveryTrip.lines))
            .where(DeliveryRequest.id == request_id)
        ).scalar_one_or_none()

    def get_request_by_code(self, code: str) -> DeliveryRequest | None:
        return self.db.execute(
            select(DeliveryRequest).where(DeliveryRequest.code == code)
        ).scalar_one_or_none()

    def create_request(self, **kw) -> DeliveryRequest:
        row = DeliveryRequest(**kw)
        self.db.add(row)
        self.db.flush()
        return row

    def add_request_line(self, request_id: int, order_line_id: int, qty: int, *,
                         hang_loai=None, hang_id=None, dvt=None) -> DeliveryRequestLine:
        row = DeliveryRequestLine(request_id=request_id, order_line_id=order_line_id, qty=qty,
                                  hang_loai=hang_loai, hang_id=hang_id, dvt=dvt)
        self.db.add(row)
        self.db.flush()
        return row

    def list_requests(
        self,
        *,
        order_id: int | None = None,
        department_ids: list[int] | None = None,
        created_by: int | None = None,
        chi_cho_len_ke_hoach: bool = False,
    ) -> list[DeliveryRequest]:
        q = (
            select(DeliveryRequest)
            .options(selectinload(DeliveryRequest.lines),
                     selectinload(DeliveryRequest.trips))
            .order_by(DeliveryRequest.id.desc())
        )
        if order_id is not None:
            q = q.where(DeliveryRequest.order_id == order_id)
        if department_ids is not None:
            q = q.where(DeliveryRequest.department_id.in_(department_ids))
        if created_by is not None:
            q = q.where(DeliveryRequest.created_by == created_by)
        if chi_cho_len_ke_hoach:
            q = q.where(DeliveryRequest.trang_thai == YC_CHO_LEN_KE_HOACH)
        return list(self.db.execute(q).scalars().all())

    def requests_mo_cua_don(self, order_id: int) -> list[DeliveryRequest]:
        """Yêu cầu CHƯA huỷ của một đơn — dùng để chặn đặt vượt số còn phải giao."""
        return list(self.db.execute(
            select(DeliveryRequest)
            .options(selectinload(DeliveryRequest.lines))
            .where(DeliveryRequest.order_id == order_id,
                   DeliveryRequest.trang_thai != YC_DA_HUY)
        ).scalars().all())

    # --- "Đã giao bao nhiêu" — SUM, không phải cột --------------------------------------
    def da_giao_theo_dong(self, order_id: int) -> dict[int, int]:
        """{order_line_id: tổng số khách đã THỰC NHẬN} của cả đơn.

        Cộng từ `delivery_trip_lines` qua các lần `thanh_cong`/`giao_thieu`. Giao thất bại KHÔNG
        cộng (nghiệm thu #7) vì chuyến hỏng không sinh dòng `delivery_trip_lines` nào.
        """
        rows = self.db.execute(
            select(DeliveryTripLine.order_line_id, func.coalesce(func.sum(DeliveryTripLine.qty_giao), 0))
            .join(DeliveryTrip, DeliveryTrip.id == DeliveryTripLine.trip_id)
            .join(DeliveryRequest, DeliveryRequest.id == DeliveryTrip.request_id)
            .where(DeliveryRequest.order_id == order_id,
                   DeliveryTrip.trang_thai.in_(LAN_GIAO_CO_HANG_DEN_TAY))
            .group_by(DeliveryTripLine.order_line_id)
        ).all()
        return {int(r[0]): int(r[1] or 0) for r in rows}

    def da_giao_cua_yeu_cau(self, request_id: int) -> dict[int, int]:
        """{order_line_id: đã thực nhận} nhưng chỉ trong PHẠM VI MỘT yêu cầu.

        Dùng để tính hàng còn phải xuất cho lần giao kế tiếp — `delivery_issue_requests` cố ý
        KHÔNG có bảng dòng riêng nên con số này phải tính ra mỗi lần.
        """
        rows = self.db.execute(
            select(DeliveryTripLine.order_line_id, func.coalesce(func.sum(DeliveryTripLine.qty_giao), 0))
            .join(DeliveryTrip, DeliveryTrip.id == DeliveryTripLine.trip_id)
            .where(DeliveryTrip.request_id == request_id,
                   DeliveryTrip.trang_thai.in_(LAN_GIAO_CO_HANG_DEN_TAY))
            .group_by(DeliveryTripLine.order_line_id)
        ).all()
        return {int(r[0]): int(r[1] or 0) for r in rows}

    # --- Lần giao -----------------------------------------------------------------------
    def get_trip(self, trip_id: int) -> DeliveryTrip | None:
        return self.db.execute(
            select(DeliveryTrip)
            .options(selectinload(DeliveryTrip.lines), selectinload(DeliveryTrip.request))
            .where(DeliveryTrip.id == trip_id)
        ).scalar_one_or_none()

    def create_trip(self, **kw) -> DeliveryTrip:
        row = DeliveryTrip(**kw)
        self.db.add(row)
        self.db.flush()
        return row

    def add_trip_line(self, trip_id: int, order_line_id: int, qty_giao: int) -> DeliveryTripLine:
        row = DeliveryTripLine(trip_id=trip_id, order_line_id=order_line_id, qty_giao=qty_giao)
        self.db.add(row)
        self.db.flush()
        return row

    def trips_cua_yeu_cau(self, request_id: int) -> list[DeliveryTrip]:
        return list(self.db.execute(
            select(DeliveryTrip)
            .options(selectinload(DeliveryTrip.lines))
            .where(DeliveryTrip.request_id == request_id)
            .order_by(DeliveryTrip.lan_thu)
        ).scalars().all())

    def trip_dang_chay(self, request_id: int) -> DeliveryTrip | None:
        """Lần giao còn sống của yêu cầu — nghiệm thu #3 chặn có quá một."""
        return self.db.execute(
            select(DeliveryTrip)
            .where(DeliveryTrip.request_id == request_id,
                   DeliveryTrip.trang_thai.in_(LAN_GIAO_DANG_CHAY))
            .order_by(DeliveryTrip.lan_thu.desc())
        ).scalars().first()

    def lan_thu_ke_tiep(self, request_id: int) -> int:
        cao_nhat = self.db.execute(
            select(func.max(DeliveryTrip.lan_thu)).where(DeliveryTrip.request_id == request_id)
        ).scalar()
        return int(cao_nhat or 0) + 1

    def list_trips(
        self,
        *,
        employee_ids: list[int] | None = None,
        department_ids: list[int] | None = None,
        trang_thai: list[str] | None = None,
    ) -> list[DeliveryTrip]:
        q = (
            select(DeliveryTrip)
            .join(DeliveryRequest, DeliveryRequest.id == DeliveryTrip.request_id)
            .options(selectinload(DeliveryTrip.lines), selectinload(DeliveryTrip.request))
            .order_by(DeliveryTrip.gio_lay_hang.desc(), DeliveryTrip.id.desc())
        )
        if employee_ids is not None:
            q = q.where(DeliveryTrip.employee_id.in_(employee_ids))
        if department_ids is not None:
            q = q.where(DeliveryRequest.department_id.in_(department_ids))
        if trang_thai:
            q = q.where(DeliveryTrip.trang_thai.in_(trang_thai))
        return list(self.db.execute(q).scalars().all())

    def trung_lich(
        self,
        *,
        employee_id: int,
        bat_dau: datetime,
        ket_thuc: datetime,
        bo_qua_trip_id: int | None = None,
    ) -> list[DeliveryTrip]:
        """Chuyến CÒN SỐNG của tài xế có khoảng thời gian GIAO NHAU với `[bat_dau, ket_thuc]`.

        Định nghĩa "trùng" nằm đúng ở đây, một chỗ duy nhất (PRD §6): hai khoảng giao nhau khi
        `bat_dau < ket_thuc_cu` VÀ `ket_thuc > bat_dau_cu`. Chạm mép (giao xong lúc 10:00, lấy
        hàng chuyến sau lúc 10:00) KHÔNG tính là trùng — dùng `<` chứ không `<=`.
        """
        q = (
            select(DeliveryTrip)
            .where(DeliveryTrip.employee_id == employee_id,
                   DeliveryTrip.trang_thai.in_(LAN_GIAO_DANG_CHAY),
                   DeliveryTrip.gio_lay_hang < ket_thuc,
                   DeliveryTrip.gio_du_kien_giao > bat_dau)
            .order_by(DeliveryTrip.gio_lay_hang)
        )
        if bo_qua_trip_id is not None:
            q = q.where(DeliveryTrip.id != bo_qua_trip_id)
        return list(self.db.execute(q).scalars().all())

    # --- Lịch sử trạng thái --------------------------------------------------------------
    def ghi_lich_su(
        self,
        *,
        trip_id: int,
        tu_trang_thai: str | None,
        den_trang_thai: str,
        nguoi_thao_tac_id: int | None,
        ghi_chu: str | None = None,
        ly_do: str | None = None,
    ) -> DeliveryStatusHistory:
        row = DeliveryStatusHistory(
            trip_id=trip_id, tu_trang_thai=tu_trang_thai, den_trang_thai=den_trang_thai,
            nguoi_thao_tac_id=nguoi_thao_tac_id, ghi_chu=ghi_chu, ly_do=ly_do,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def dinh_kem_cua_trip(self, trip_id: int) -> list[DeliveryTripAttachment]:
        return list(self.db.execute(
            select(DeliveryTripAttachment)
            .where(DeliveryTripAttachment.trip_id == trip_id)
            .order_by(DeliveryTripAttachment.id)
        ).scalars().all())

    def get_dinh_kem(self, attachment_id: int) -> DeliveryTripAttachment | None:
        return self.db.get(DeliveryTripAttachment, attachment_id)

    def them_dinh_kem(self, **kw) -> DeliveryTripAttachment:
        row = DeliveryTripAttachment(**kw)
        self.db.add(row)
        self.db.flush()
        return row

    def xoa_dinh_kem(self, row) -> None:
        self.db.delete(row)
        self.db.flush()

    def lich_su_cua_trip(self, trip_id: int) -> list[DeliveryStatusHistory]:
        return list(self.db.execute(
            select(DeliveryStatusHistory)
            .where(DeliveryStatusHistory.trip_id == trip_id)
            .order_by(DeliveryStatusHistory.id)
        ).scalars().all())
