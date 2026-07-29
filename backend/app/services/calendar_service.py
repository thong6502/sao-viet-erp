"""Lịch làm việc & Ngày lễ — nghiệp vụ (Pha 1, module `nhan_su`).

Nguồn sự thật DUY NHẤT cho câu hỏi "ngày này có làm việc không / công chuẩn tháng này bao
nhiêu / ngày này có phải lễ không". Chấm công + Nghỉ phép + Lương gọi chung service này thay
cho hardcode T7/CN rải rác.

Quy tắc `is_working_day(d)`:
  1. Nếu d là ngày đặc biệt 'work' (làm bù) → LÀM.
  2. Nếu d là ngày đặc biệt 'off' (nghỉ lễ) → NGHỈ.
  3. Còn lại → theo cấu hình tuần (works_mon..works_sun).

Hiệu năng: nạp special_days theo NĂM đúng một lần vào cache trong instance (service scope theo
request → FastAPI chia sẻ 1 instance/request), nên `working_days_between` gọi trong vòng lặp
quota của Nghỉ phép KHÔNG sinh N+1. Mọi mutation xóa cache.
"""
from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta

from ..models.work_calendar import (
    KIND_OFF,
    KIND_OFF1X,
    KIND_WORK,
    SPECIAL_KINDS,
    SpecialDay,
    WorkCalendarConfig,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.calendar_repo import CalendarRepository

# Thứ trong tuần (Mon=0..Sun=6) → tên cột config.
_WEEKDAY_COL = ("works_mon", "works_tue", "works_wed", "works_thu", "works_fri", "works_sat", "works_sun")
_WORKS_FIELDS = _WEEKDAY_COL

# Số ngày nghỉ lễ hưởng lương tối thiểu/năm (điều 112 BLLĐ 2019) — để cảnh báo "chưa đủ".
STATUTORY_PAID_HOLIDAYS = 11


class CalendarError(Exception):
    """Base cho lỗi lịch."""


class CalendarValidationError(CalendarError):
    """Dữ liệu vào không hợp lệ."""


class CalendarNotFound(CalendarError):
    """Không tìm thấy ngày đặc biệt."""


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class CalendarService:
    def __init__(self, calendar: CalendarRepository, audit: AuditLogRepository) -> None:
        self.calendar = calendar
        self.audit = audit
        self._config: WorkCalendarConfig | None = None
        self._special_by_year: dict[int, dict[date, SpecialDay]] = {}

    def _invalidate(self) -> None:
        self._config = None
        self._special_by_year = {}

    # --- config (tuần làm việc) --------------------------------------------

    def get_config(self) -> WorkCalendarConfig:
        if self._config is None:
            c = self.calendar.get_config()
            if c is None:
                c = self.calendar.create_config()  # mặc định T2–T7 làm, CN nghỉ
            self._config = c
        return self._config

    def update_config(self, *, actor, **works) -> WorkCalendarConfig:
        data = {k: bool(v) for k, v in works.items() if k in _WORKS_FIELDS and v is not None}
        if not data:
            raise CalendarValidationError("Không có thay đổi nào.")
        c = self.get_config()
        merged = {f: (data[f] if f in data else getattr(c, f)) for f in _WORKS_FIELDS}
        if not any(merged.values()):
            raise CalendarValidationError("Tuần làm việc phải có ít nhất một ngày làm.")
        from datetime import datetime, timezone
        data["updated_at"] = datetime.now(timezone.utc)
        c = self.calendar.update_config(c, **data)
        self._config = c
        working = [_vn_weekday_label(i) for i, f in enumerate(_WORKS_FIELDS) if merged[f]]
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="update_calendar_config",
                          target="work_calendar_config", detail="Ngày làm: " + ", ".join(working))
        return c

    # --- tra cứu lõi -------------------------------------------------------

    def _special_for(self, d: date) -> SpecialDay | None:
        year = d.year
        if year not in self._special_by_year:
            self._special_by_year[year] = {s.day: s for s in self.calendar.list_by_year(year)}
        return self._special_by_year[year].get(d)

    def _weekday_works(self, d: date) -> bool:
        return bool(getattr(self.get_config(), _WEEKDAY_COL[d.weekday()]))

    def is_working_day(self, d: date) -> bool:
        """Ngày d có phải NGÀY LÀM VIỆC không (đã tính lễ + làm bù + cấu hình tuần)."""
        sp = self._special_for(d)
        if sp is not None:
            if sp.kind == KIND_WORK:
                return True
            if sp.kind in (KIND_OFF, KIND_OFF1X):   # off1x cũng là ngày NGHỈ
                return False
        return self._weekday_works(d)

    def working_days_between(self, start: date, end: date) -> int:
        """Số NGÀY LÀM VIỆC trong [start, end] (loại cuối tuần theo config + loại lễ, cộng làm bù).
        Đơn vị TRỪ hạn mức phép năm của Nghỉ phép."""
        if end < start:
            return 0
        n = 0
        d = start
        while d <= end:
            if self.is_working_day(d):
                n += 1
            d = d + timedelta(days=1)
        return n

    def standard_working_days(self, year: int, month: int) -> int:
        """Số ngày làm việc thực của tháng (công chuẩn động — Pha 1 chưa dùng cho Lương,
        để sẵn cho FE xem trước + Pha 4)."""
        if not (1 <= month <= 12):
            raise CalendarValidationError("Tháng phải trong 1–12.")
        last = _cal.monthrange(year, month)[1]
        return self.working_days_between(date(year, month, 1), date(year, month, last))

    def special_days_in_range(self, start: date, end: date) -> list[SpecialDay]:
        return self.calendar.list_in_range(start, end)

    def paid_holidays_in_month(self, year: int, month: int) -> list[SpecialDay]:
        """Ngày nghỉ lễ HƯỞNG LƯƠNG trong tháng — Chấm công cộng công lễ (nhịp 2)."""
        last = _cal.monthrange(year, month)[1]
        return [s for s in self.calendar.list_in_range(date(year, month, 1), date(year, month, last))
                if s.kind == KIND_OFF and s.is_paid]

    def plain_days_in_month(self, year: int, month: int) -> list[SpecialDay]:
        """Ngày nghỉ 'off1x' trong tháng — nghỉ KHÔNG lương; ai đi làm được trả 1× (không hệ số)."""
        last = _cal.monthrange(year, month)[1]
        return [s for s in self.calendar.list_in_range(date(year, month, 1), date(year, month, last))
                if s.kind == KIND_OFF1X]

    # --- CRUD ngày đặc biệt ------------------------------------------------

    def list_special_days(self, year: int) -> list[SpecialDay]:
        return self.calendar.list_by_year(year)

    def paid_off_count(self, year: int) -> int:
        return sum(1 for s in self.calendar.list_by_year(year) if s.kind == KIND_OFF and s.is_paid)

    @staticmethod
    def _validate_special(day, kind, name):
        if day is None:
            raise CalendarValidationError("Cần chọn ngày.")
        kind = (kind or KIND_OFF)
        if kind not in SPECIAL_KINDS:
            raise CalendarValidationError("Loại ngày không hợp lệ.")
        name = (name or "").strip()
        if not name:
            raise CalendarValidationError("Tên ngày là bắt buộc.")
        return day, kind, name

    def create_special_day(self, *, actor, day: date, kind: str = KIND_OFF, name: str,
                           is_paid: bool = True, note: str | None = None) -> SpecialDay:
        day, kind, name = self._validate_special(day, kind, name)
        if self.calendar.get_by_day(day) is not None:
            raise CalendarValidationError(f"Ngày {day.isoformat()} đã được khai.")
        # off1x = nghỉ KHÔNG lương (chỉ ai đi làm mới có 1× cho ngày đó) → ép is_paid False.
        is_paid = False if kind == KIND_OFF1X else bool(is_paid)
        s = self.calendar.create(day=day, kind=kind, name=name,
                                 is_paid=is_paid, note=_clean(note))
        self._invalidate()
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="create_special_day",
                          target=f"special_day:{s.id}", detail=f"{day.isoformat()} {kind} {name}")
        return s

    def update_special_day(self, *, actor, special_id: int, day: date, kind: str = KIND_OFF,
                           name: str, is_paid: bool = True, note: str | None = None) -> SpecialDay:
        s = self.calendar.get(special_id)
        if s is None:
            raise CalendarNotFound("Không tìm thấy ngày đặc biệt.")
        day, kind, name = self._validate_special(day, kind, name)
        clash = self.calendar.get_by_day(day)
        if clash is not None and clash.id != s.id:
            raise CalendarValidationError(f"Ngày {day.isoformat()} đã được khai.")
        is_paid = False if kind == KIND_OFF1X else bool(is_paid)
        s = self.calendar.update(s, day=day, kind=kind, name=name,
                                 is_paid=is_paid, note=_clean(note))
        self._invalidate()
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="update_special_day",
                          target=f"special_day:{s.id}", detail=f"{day.isoformat()} {kind} {name}")
        return s

    def delete_special_day(self, *, actor, special_id: int) -> None:
        s = self.calendar.get(special_id)
        if s is None:
            raise CalendarNotFound("Không tìm thấy ngày đặc biệt.")
        detail = f"{s.day.isoformat()} {s.kind} {s.name}"
        self.calendar.delete(s)
        self._invalidate()
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="delete_special_day",
                          target=f"special_day:{special_id}", detail=detail)

    # --- lịch tháng cho FE + Chấm công -------------------------------------

    def _day_kind(self, d: date) -> tuple[str, str | None]:
        """(kind, name) cho hiển thị: work | weekend | holiday | makeup."""
        sp = self._special_for(d)
        if sp is not None:
            if sp.kind == KIND_WORK:
                return "makeup", sp.name
            if sp.kind == KIND_OFF:
                return "holiday", sp.name
        return ("work", None) if self._weekday_works(d) else ("weekend", None)

    def month_calendar(self, year: int, month: int) -> dict:
        """Hình LỊCH công ty của 1 tháng cho FE xem trước + Chấm công tô màu.
        (KHÁC Bảng công tháng của Chấm công — cái đó theo từng NV.)"""
        if not (1 <= month <= 12):
            raise CalendarValidationError("Tháng phải trong 1–12.")
        last = _cal.monthrange(year, month)[1]
        days = []
        working = 0
        holidays = []
        for dd in range(1, last + 1):
            d = date(year, month, dd)
            kind, name = self._day_kind(d)
            is_working = kind in ("work", "makeup")
            if is_working:
                working += 1
            if kind == "holiday":
                sp = self._special_for(d)
                holidays.append({"date": d.isoformat(), "name": name,
                                 "is_paid": bool(sp.is_paid) if sp else True})
            days.append({"day": dd, "date": d.isoformat(), "weekday": d.weekday(),
                         "kind": kind, "name": name, "is_working": is_working})
        return {"year": year, "month": month, "working_days": working,
                "paid_holiday_count": self.paid_off_count(year), "days": days, "holidays": holidays}


def _vn_weekday_label(idx: int) -> str:
    return ("T2", "T3", "T4", "T5", "T6", "T7", "CN")[idx]
