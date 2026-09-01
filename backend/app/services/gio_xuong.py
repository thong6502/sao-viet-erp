"""Đồng hồ XƯỞNG — MỘT quy ước giờ duy nhất để so mốc KẾ HOẠCH với mốc THỰC TẾ.

Trong repo có HAI thang giờ, và đây là chỗ chúng gặp nhau:

  · **Lịch** — `xep_lich_cong_doan.start_at/finish_at`, và bản chép của nó sang
    `san_xuat_cong_viec.du_kien_bat_dau/du_kien_ket_thuc` (`san_xuat/snapshot.py`) — lưu GIỜ TƯỜNG
    của nhà máy rồi dán nhãn `timezone.utc`. Xem `xep_lich_service._gio_xuong()` để biết vì sao cả
    module xếp lịch chọn quy ước đó (phút ca, `_naive()` cho FE…).
  · **Thực thi** — `san_xuat_phien_chay.bat_dau/ket_thuc` do `san_xuat/thuc_thi._moc()` ghi, là UTC
    THẬT.

Trừ thẳng hai bên là sai đúng bằng offset múi giờ máy chủ (VN: 7 tiếng), và luôn sai theo chiều
KHOAN DUNG — báo ÍT trễ hơn thực tế, rồi bị `max(..., 0)` kẹp thành 0 nên không lộ ra thành lỗi mà
thành "không có gì bất thường". (Phát hiện 01/09/2026: cảnh báo "vào việc muộn" chỉ kêu khi muộn
quá 8 tiếng.) Trước khi so, đưa mốc UTC thật về thang giờ xưởng bằng `ve_gio_xuong()`.

KHÔNG hardcode +7: lấy đúng múi của máy chủ, để máy chủ đặt múi khác vẫn đúng.
"""
from __future__ import annotations

from datetime import datetime, timezone


def gio_xuong() -> datetime:
    """Bây giờ theo ĐỒNG HỒ XƯỞNG — giờ tường máy chủ, dán nhãn UTC. Cùng quy ước với
    `xep_lich_service._gio_xuong()`."""
    return datetime.now().replace(tzinfo=timezone.utc)


def ve_gio_xuong(dt: datetime | None) -> datetime | None:
    """Đưa một mốc UTC THẬT về thang giờ xưởng để so được với `du_kien_*`.

    Mốc naive được coi là UTC thật — cột `DateTime(timezone=True)` trên SQLite trả về naive, còn
    trên Postgres trả về aware; cả hai đường đều ra cùng kết quả.
    """
    if dt is None:
        return None
    d = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return d.astimezone().replace(tzinfo=timezone.utc)


def lich_hien_thi(dt: datetime | None) -> datetime | None:
    """Khuôn TRẢ RA cho mốc thang LỊCH (`du_kien_bat_dau/ket_thuc`, `can_luc`…): bỏ tzinfo để
    serialize dạng wall-clock giờ nhà máy — giống `xep_lich_service._naive`.

    Giá trị trong DB vốn đã là giờ tường dán nhãn UTC; để nguyên nhãn thì Postgres trả
    `+00:00`, FE `new Date(iso)` dịch thêm +7h (bàn Xếp lịch hiện 18:34, bàn tổ hiện 01:34 hôm
    sau). CHỈ cho ĐẦU RA, không cho tính toán.
    """
    return dt.replace(tzinfo=None) if dt is not None else None


def thuc_te_hien_thi(dt: datetime | None) -> datetime | None:
    """Khuôn TRẢ RA cho mốc THỰC THI (`san_xuat_phien_chay.bat_dau`, batch, bàn giao, xác nhận…),
    thứ mà `thuc_thi._moc()` ghi bằng UTC THẬT.

    Đưa về thang giờ xưởng rồi bỏ nhãn, để FE nhận CÙNG một thang với `du_kien_*`: thanh thực-tế
    và thanh kế hoạch trên cùng một Gantt phải đo bằng một cây thước (`gantt-time.wallMinutes`
    đọc thành phần ISO, không dịch múi — trả UTC thật vào đó là thanh thực-tế lùi 7 tiếng).
    """
    return lich_hien_thi(ve_gio_xuong(dt))
