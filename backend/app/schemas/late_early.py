"""Pydantic models cho API Phiếu đi muộn / về sớm / nghỉ nửa buổi (module `di_muon`).

`from_minute`/`to_minute` = phút tính từ 00:00 của NGÀY CÔNG — cùng trục với `compute_day_cong`.
`leave_type_id` khác None = tick "Trừ vào phép năm": tiêu `leave_cong` ngày phép (làm tròn 0,5)
và phần vắng VẪN được trả theo lương vị trí. None = mất công phần vắng, quỹ phép không đụng.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

_MAX_MINUTE = 2 * 1440


class LateEarlyRequestIn(BaseModel):
    """NV tự gửi phiếu (POST /api/late-early/me)."""

    work_date: date
    from_minute: int = Field(ge=0, le=_MAX_MINUTE)
    to_minute: int = Field(ge=0, le=_MAX_MINUTE)
    reason: str | None = Field(default=None, max_length=500)
    # None = không trừ phép năm (mất công phần vắng).
    leave_type_id: int | None = None


class LateEarlyRequestForIn(LateEarlyRequestIn):
    """Tổ trưởng khai HỘ cho thợ (POST /api/late-early) — duyệt luôn, khỏi thêm một bước."""

    employee_id: int


class LateEarlyDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class LateEarlyRejectIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class LateEarlyRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None    # router điền
    work_date: date
    from_minute: int
    to_minute: int
    minutes: int = 0                    # router điền = to_minute − from_minute
    leave_type_id: int | None = None
    leave_type_name: str | None = None  # router điền
    leave_cong: float = 0               # số ngày phép bị trừ (0 nếu không trừ)
    reason: str | None = None
    status: str
    decided_by: int | None = None
    decided_by_name: str | None = None  # router điền
    decided_at: datetime | None = None
    decision_note: str | None = None
    created_at: datetime | None = None


class LateEarlyRequestsOut(BaseModel):
    items: list[LateEarlyRequestOut]


class MyLateEarlyOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    items: list[LateEarlyRequestOut] = []


class LateEarlyBulkIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class LateEarlyBulkRejectIn(BaseModel):
    ids: list[int] = Field(min_length=1)
    note: str = Field(min_length=1, max_length=500)


class LateEarlyBulkResultOut(BaseModel):
    done: list[int]
    skipped: list[int]


class LateEarlyRosterEmpOut(BaseModel):
    id: int
    code: str | None = None
    full_name: str
    department: str | None = None
    default_shift_id: int | None = None


class LateEarlyRosterShiftOut(BaseModel):
    id: int
    name: str
    start_minute: int
    end_minute: int
    is_overnight: bool = False


class LateEarlyRosterOut(BaseModel):
    """Danh sách thợ + danh mục ca TRONG TẦM của người duyệt.

    Tồn tại vì vai "Tổ trưởng SX" có `di_muon:approve` nhưng KHÔNG có module `nhan_su` ⇒
    `/api/employees` và `/api/attendance/shifts` đều 403 với họ. Cho họ `nhan_su:read` chỉ để
    đổ được cái dropdown là nới quá tay (mở luôn hồ sơ nhân sự); endpoint này trả đúng thứ cần."""
    employees: list[LateEarlyRosterEmpOut] = []
    shifts: list[LateEarlyRosterShiftOut] = []


class LateEarlySummaryOut(BaseModel):
    # Số phiếu CHỜ DUYỆT trong scope người gọi (badge sidebar). None nếu không có quyền duyệt.
    pending_in_scope: int | None = None
    # Số phiếu CỦA TÔI vừa được quyết mà tôi chưa xem → chuông Topbar.
    my_decided_unseen: int = 0
