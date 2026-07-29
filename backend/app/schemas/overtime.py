"""Pydantic models cho API Phiếu tăng ca (module `tang_ca`).

`from_minute`/`to_minute` = phút tính từ 00:00 của NGÀY CÔNG (không phải giờ đồng hồ thuần) —
vượt nửa đêm thì > 1440 (vd 03:00 hôm sau = 1620). Cùng trục với `compute_day_cong`.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

_MAX_MINUTE = 2 * 1440


class OvertimeRequestIn(BaseModel):
    """NV tự gửi phiếu (POST /api/overtime/me)."""

    work_date: date
    from_minute: int = Field(ge=0, le=_MAX_MINUTE)
    to_minute: int = Field(ge=0, le=_MAX_MINUTE)
    reason: str | None = Field(default=None, max_length=500)


class OvertimeRequestForIn(OvertimeRequestIn):
    """Tổ trưởng tạo HỘ cho thợ (POST /api/overtime) — duyệt luôn, khỏi thêm một bước."""

    employee_id: int


class OvertimeDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class OvertimeRejectIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class OvertimeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None    # router điền
    work_date: date
    from_minute: int
    to_minute: int
    minutes: int = 0                    # router điền = to_minute − from_minute (số phút được duyệt)
    reason: str | None = None
    status: str
    decided_by: int | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    created_at: datetime | None = None


class OvertimeRequestsOut(BaseModel):
    items: list[OvertimeRequestOut]


class MyOvertimeOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    items: list[OvertimeRequestOut] = []


class OvertimeBulkIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class OvertimeBulkRejectIn(BaseModel):
    ids: list[int] = Field(min_length=1)
    note: str = Field(min_length=1, max_length=500)


class OvertimeBulkResultOut(BaseModel):
    done: list[int]
    skipped: list[int]


class OvertimeSummaryOut(BaseModel):
    # Số phiếu CHỜ DUYỆT trong scope người gọi (badge sidebar). None nếu không có quyền duyệt.
    pending_in_scope: int | None = None
    # Số phiếu CỦA TÔI vừa được quyết mà tôi chưa xem → chuông Topbar.
    my_decided_unseen: int = 0
