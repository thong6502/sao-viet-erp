"""MỘT định nghĩa "BIÊN CHẾ" cho cả 5 phân hệ (bản rà liên thông 08/09/2026, nhóm gốc 1).

Trước đó chấm công/phép nhìn 2 cột `hire_date`/`resign_date` + phòng ban HIỆN TẠI, còn lương suy
theo `employee_events` tại cuối kỳ. Hai định nghĩa lệch nhau đúng ở ca biên: tuyển lại (tháng trống
giữa hai lần làm bỗng có công lễ + phụ cấp), nghỉ dài hạn / đình chỉ (vẫn bấm giờ ra công, hưởng
công lễ), chấm bù / đơn phép cho ngày sau nghỉ việc, nghỉ đúng ngày lễ (chấm công đếm 1 công lễ,
lương thì không). Từ nay mọi nơi hỏi cùng một câu: *"ngày d, người này có đang làm việc không, ở
phòng nào?"* — và hỏi ĐÚNG MỘT CHỖ này.

Quy ước:
- `resign_date` = NGÀY ĐẦU KHÔNG LÀM (thống nhất A8): ngày đó đã ngoài biên chế.
- "Đang làm" = thử việc · hết thử việc (chờ xác nhận) · chính thức. Nghỉ dài hạn (thai sản, ốm dài,
  không lương dài) và đình chỉ là NGOÀI biên chế: không lương, không công lễ, không bấm giờ — chủ
  chốt 07/09/2026: *"nghỉ dài hạn mặc định không có lương, thế thôi; ai trả cho họ là luồng ngoài"*.
- Trạng thái/phòng tại một ngày dựng lại từ `employee_events` (field `status` / `department`,
  có `effective_date`): trạng thái TRƯỚC sự kiện đầu tiên là `from_value` của nó, sau mỗi sự kiện
  là `to_value`. Không có sự kiện nào của trường đó thì lấy cột hiện tại. Cách này đúng cho cả sự
  kiện đã áp sớm vào cột (dữ liệu cũ) lẫn sự kiện đúng ngày.
"""
from __future__ import annotations

import calendar
from datetime import date

from ..models.employee import (
    STATUS_ACTIVE,
    STATUS_ON_LEAVE,
    STATUS_PROBATION,
    STATUS_PROBATION_ENDED,
    STATUS_RESIGNED,
    STATUS_SUSPENDED,
)

#: Trạng thái được coi là ĐANG LÀM VIỆC (có công, có lương, được bấm giờ).
TRANG_THAI_DANG_LAM = frozenset({STATUS_PROBATION, STATUS_PROBATION_ENDED, STATUS_ACTIVE})


def _gia_tri_tren_ngay(gia_tri_hien_tai, events, field: str, d: date):
    evs = sorted(
        (e for e in (events or [])
         if getattr(e, "field", None) == field and getattr(e, "effective_date", None) is not None),
        key=lambda e: (e.effective_date, e.id or 0),
    )
    if not evs:
        return gia_tri_hien_tai
    # Trước sự kiện đầu tiên: trạng thái "từ" của nó; không ghi thì coi như giá trị hiện tại.
    gia_tri = evs[0].from_value if evs[0].from_value is not None else gia_tri_hien_tai
    for e in evs:
        if e.effective_date <= d:
            if e.to_value is not None:
                gia_tri = e.to_value
        else:
            break
    return gia_tri


def trang_thai_tren_ngay(emp, events, d: date) -> tuple[str, int | None]:
    """(trạng thái, department_id) của `emp` tại ngày `d`, dựng từ `events` (mọi sự kiện của NV)."""
    status = _gia_tri_tren_ngay(emp.status, events, "status", d)
    dept_now = getattr(emp, "department_id", None)
    dept = _gia_tri_tren_ngay(str(dept_now) if dept_now is not None else None, events, "department", d)
    try:
        dept_id = int(dept) if dept not in (None, "", "None") else None
    except (TypeError, ValueError):
        dept_id = dept_now
    return status, dept_id


def trong_bien_che(emp, events, d: date) -> bool:
    """Ngày `d` người này có ĐANG LÀM VIỆC không (đủ điều kiện có công, công lễ, bấm giờ, đơn)."""
    return ly_do_ngoai_bien_che(emp, events, d) is None


def ly_do_ngoai_bien_che(emp, events, d: date) -> str | None:
    """None = trong biên chế. Chuỗi = lý do (đã viết cho người dùng đọc, dùng chung mọi cửa ghi)."""
    ten = getattr(emp, "full_name", None) or "Nhân viên"
    hire = getattr(emp, "hire_date", None)
    if hire is not None and d < hire:
        return f"{ten} chưa vào làm ngày {d:%d/%m/%Y} (ngày vào làm {hire:%d/%m/%Y})."
    resign = getattr(emp, "resign_date", None)
    if resign is not None and d >= resign:
        return f"{ten} đã nghỉ việc từ {resign:%d/%m/%Y} — ngày {d:%d/%m/%Y} ngoài biên chế."
    status, _ = trang_thai_tren_ngay(emp, events, d)
    if status in TRANG_THAI_DANG_LAM:
        return None
    if status == STATUS_ON_LEAVE:
        return (f"{ten} đang nghỉ dài hạn ngày {d:%d/%m/%Y} — không có công/lương; "
                f"HCNS bấm \"Đi làm lại\" ở hồ sơ trước.")
    if status == STATUS_SUSPENDED:
        return f"{ten} đang bị đình chỉ ngày {d:%d/%m/%Y} — không có công/lương."
    if status == STATUS_RESIGNED:
        return f"{ten} đã nghỉ việc — ngày {d:%d/%m/%Y} ngoài biên chế."
    return f"{ten} không ở trạng thái đang làm việc ngày {d:%d/%m/%Y} ({status})."


def trong_bien_che_thang(emp, events, year: int, month: int) -> bool:
    """Có ÍT NHẤT một ngày trong tháng còn biên chế — ai lên Bảng công / có dòng lương."""
    last = calendar.monthrange(year, month)[1]
    return any(trong_bien_che(emp, events, date(year, month, d)) for d in range(1, last + 1))
