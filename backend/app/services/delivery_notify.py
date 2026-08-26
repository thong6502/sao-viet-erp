"""Báo tài xế khi KHO LẬP PHIẾU — móc duy nhất mà Giao hàng đặt vào luồng của Kho.

Vì sao phải có móc này (chủ chốt 20/08/2026): mốc thật sự làm tài xế lên đường là *"kho soạn
xong hàng"*, mà việc đó xảy ra bên màn Kho. Router phiếu kho không đẩy sự kiện nào, nên Giao hàng
không có gì để nghe ké — không móc thì tài xế phải tự F5 đoán, đoán sai thì hoặc tới sớm ngồi
chờ, hoặc tới muộn.

RANH GIỚI, cố ý giữ hẹp:

* Toàn bộ logic nằm ở ĐÂY, file của Giao hàng. Bên `routers/kho_voucher` chỉ có MỘT dòng gọi,
  bọc `try` — hỏng gửi toast KHÔNG được làm hỏng việc lập phiếu của kho.
* Chỉ ĐỌC dữ liệu kho, không sửa gì, không đổi trạng thái gì của họ.
* Yêu cầu không phải của giao hàng (`delivery_trip_id` rỗng) thì lặng lẽ thôi — mọi phiếu vật tư
  thường đi qua đây, không được sinh tiếng động nào.
"""
from __future__ import annotations

from ..models.delivery import DeliveryTrip
from ..models.employee import Employee
from ..models.stock_request import StockRequest
from ..realtime import hub


def bao_tai_xe_kho_lap_phieu(db, request_id: int | None, ma_phieu: str | None = None) -> None:
    """Kho vừa lập phiếu cho `request_id` ⇒ đẩy cho tài xế của chuyến, nếu có.

    Nuốt mọi lỗi: đây là thông báo, không phải nghiệp vụ. Ném lên là kho lập phiếu xong lại thấy
    màn hình báo đỏ, trong khi phiếu đã ghi đúng.
    """
    try:
        if not request_id:
            return
        req = db.get(StockRequest, int(request_id))
        trip_id = getattr(req, "delivery_trip_id", None)
        if not trip_id:
            return
        trip = db.get(DeliveryTrip, int(trip_id))
        if trip is None:
            return
        emp = db.get(Employee, int(trip.employee_id)) if trip.employee_id else None
        uid = getattr(emp, "user_id", None)
        if not uid:
            return
        hub.publish(int(uid), {
            "type": "giao_hang_chuyen",
            "viec": "kho_xong",
            "trip_id": trip.id,
            "ma_phieu": ma_phieu,
            "message": "Kho đã chuẩn bị xong hàng — bạn tới lấy được rồi.",
        })
    except Exception:
        return
