"""Khoán km giao hàng — MỘT chỗ duy nhất giữ công thức.

Nền: `docs/prd-khoan-km-giao-hang.md`. Đo bảng lương thật T05/2026: tài xế ăn lương chấm công
**cộng** tiền theo km, và phần km (19–22 tr) gấp ~4 lần lương cứng (~5 tr) — tức đây là thu nhập
CHÍNH của họ, trước nay tính tay trên bốn sheet Excel ngoài hệ thống.

Công thức:

    Khoán km(NV, kỳ) = Σ  km(chuyến) × đơn_giá_chụp(chuyến) × phần_của_NV(chuyến)
                       chuyến đã ghi kết quả, ngày kết thúc trong kỳ, NV là tài xế HOẶC phụ xe

    phần_của_NV = tài xế:  pct_tai_xe  nếu chuyến có phụ xe, ngược lại 100%
                  phụ xe:  pct_phu_xe

**Đi một mình ăn 100%** (chủ chốt 24/08/2026). Vì pct_tài_xế + pct_phụ_xe = 100 nên tổng chi cho
một chuyến KHÔNG đổi, chỉ khác chia cho mấy người.

**Đơn giá PHẲNG, không bậc thang.** Sổ giấy hiện tính bậc thang nghịch theo cự ly (18.000 đ/km cho
chặng ≤5 km xuống 3.600 đ/km cho chặng ≥164 km) và tính theo TỪNG CHẶNG. Bám y hệt thì phải ghi
chặng — 521 chặng/tháng, 31% là chặng về kho. Đo thử: đơn giá phẳng 4.330 đ/km cho ra tổng chi cả
tổ Y NGUYÊN, từng người chỉ lệch −6% đến +10% (người chạy đường dài được thêm). Đổi lại bỏ được cả
một tầng dữ liệu, và hết luôn bẫy "cộng km lại rồi mới tra bậc" — cộng gộp hay tách ra đều ra cùng
một số tiền.

**Đọc số CHỤP trên chuyến, không đọc của phòng ban.** `delivery_trips.don_gia_km` / `.pct_*` được
chụp lúc ghi kết quả. Đọc thẳng phòng ban thì chủ chỉnh một con số là bảng lương mọi tháng cũ đổi
theo — đúng bài học `orders.commission_pct` ngày 21/08/2026. Chuyến CŨ (chụp `NULL`) thì bỏ qua:
không tự đẻ tiền ngược cho quá khứ.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import or_, select

from ..models.delivery import LAN_GIAO_CO_HANG_DEN_TAY, LG_THAT_BAI, DeliveryTrip

#: Chuyến ĐÃ CHẠY XONG — có trả tiền km. Gồm cả `that_bai`: xe vẫn lăn bánh, tài xế vẫn đi, khách
#: không nhận không phải lỗi của họ. Bỏ ra là phạt người ta vì một việc họ không quyết được.
#: KHÔNG gồm `dang_tra_hang`/`da_tra_hang`: đó là trạng thái của HÀNG sau `that_bai`, đếm nữa là
#: đếm hai lần cùng một chuyến.
TRANG_THAI_TINH_TIEN = (*LAN_GIAO_CO_HANG_DEN_TAY, LG_THAT_BAI)


def _bien_ky(nam: int, thang: int) -> tuple[datetime, datetime]:
    """Nửa mở [đầu tháng, đầu tháng sau) — tránh bẫy "ngày cuối tháng bị rơi" của `<=` trên ngày."""
    tu = datetime.combine(date(nam, thang, 1), time.min, tzinfo=timezone.utc)
    den = datetime.combine(
        date(nam + (thang == 12), 1 if thang == 12 else thang + 1, 1), time.min, tzinfo=timezone.utc
    )
    return tu, den


class KhoanKmService:
    """Tính tiền khoán km của nhân viên trong một kỳ. KHÔNG ghi gì — chỉ đọc và trả số."""

    def __init__(self, db) -> None:
        self.db = db

    # -- một chuyến chia cho ai bao nhiêu ---------------------------------------------------
    @staticmethod
    def chia_tien(trip) -> dict[int, float]:
        """`{employee_id: tiền}` của MỘT chuyến. Rỗng nếu chuyến chưa đủ dữ liệu để tính."""
        km = trip.km
        gia = trip.don_gia_km
        # `is None` chứ không phải falsy: km = 0 là số THẬT (xe chưa lăn bánh, khách không nghe
        # máy) và đơn giá 0 cũng là "đã chụp, và bằng 0". Dùng `not km` là nuốt mất cả hai.
        if km is None or gia is None:
            return {}
        tong = float(km) * float(gia)
        if tong <= 0:
            return {}

        phu_xe = trip.phu_xe_employee_id
        if not phu_xe:
            # Đi một mình ⇒ 100%, KHÔNG phải pct_tai_xe. Phần của phụ xe không rơi vào túi ai.
            return {trip.employee_id: tong}

        pct_tx = float(trip.pct_tai_xe if trip.pct_tai_xe is not None else 100)
        pct_px = float(trip.pct_phu_xe if trip.pct_phu_xe is not None else 0)
        return {
            trip.employee_id: tong * pct_tx / 100.0,
            phu_xe: tong * pct_px / 100.0,
        }

    # -- cả kỳ -------------------------------------------------------------------------------
    def theo_ky(self, nam: int, thang: int) -> dict[int, float]:
        """`{employee_id: tổng tiền km}` của cả kỳ — nạp MỘT lần cho `generate`.

        Mốc xếp kỳ là `thoi_gian_ket_thuc` (lúc ghi kết quả), không phải `gio_lay_hang`: chuyến
        chạy đêm 31 sang mùng 1 thì tiền thuộc kỳ chuyến ĐÓNG, cùng kỳ với số km được chốt.
        """
        tu, den = _bien_ky(nam, thang)
        rows = self.db.execute(
            select(DeliveryTrip).where(
                DeliveryTrip.trang_thai.in_(TRANG_THAI_TINH_TIEN),
                DeliveryTrip.thoi_gian_ket_thuc >= tu,
                DeliveryTrip.thoi_gian_ket_thuc < den,
            )
        ).scalars().all()

        ra: dict[int, float] = {}
        for t in rows:
            for eid, tien in self.chia_tien(t).items():
                ra[eid] = ra.get(eid, 0.0) + tien
        return ra

    def chi_tiet(self, employee_id: int, nam: int, thang: int) -> list[dict]:
        """Từng chuyến của MỘT người — nuôi bảng đối chiếu cho HCNS.

        HCNS phải soi lại được: km là tài xế TỰ GÕ, khác hẳn hoa hồng (nguồn là hoá đơn kế toán
        đã xuất, đã có người kiểm). Không có bảng này thì khoán km thành tiền tự khai.
        """
        tu, den = _bien_ky(nam, thang)
        rows = self.db.execute(
            select(DeliveryTrip).where(
                DeliveryTrip.trang_thai.in_(TRANG_THAI_TINH_TIEN),
                DeliveryTrip.thoi_gian_ket_thuc >= tu,
                DeliveryTrip.thoi_gian_ket_thuc < den,
                or_(DeliveryTrip.employee_id == employee_id,
                    DeliveryTrip.phu_xe_employee_id == employee_id),
            ).order_by(DeliveryTrip.thoi_gian_ket_thuc)
        ).scalars().all()

        ra = []
        for t in rows:
            tien = self.chia_tien(t).get(employee_id)
            if tien is None:
                continue
            ra.append({
                "trip_id": t.id,
                "ngay": t.thoi_gian_ket_thuc,
                "km": int(t.km or 0),
                "don_gia_km": float(t.don_gia_km or 0),
                "vai_tro": "tai_xe" if t.employee_id == employee_id else "phu_xe",
                "pct": (100.0 if not t.phu_xe_employee_id
                        else float((t.pct_tai_xe if t.employee_id == employee_id
                                    else t.pct_phu_xe) or 0)),
                "thanh_tien": round(tien, 2),
            })
        return ra
