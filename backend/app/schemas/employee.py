"""Pydantic request/response models for the Hồ sơ nhân sự (nhan_su) API — lát #1.

Field-level constraints here are the first line of validation (422 shape); the service
enforces the domain rules (non-blank name, soft duplicate CCCD/BHXH, legal transitions).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- create / edit ----------------------------------------------------------


class AccountCreateIn(BaseModel):
    """Optional login account to create together with the employee (wizard step 5)."""

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=6, max_length=128)
    name: str | None = Field(default=None, max_length=255)
    role_id: int | None = None


class EmployeeBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    department_id: int | None = None
    position: str | None = Field(default=None, max_length=255)
    job_grade: str | None = Field(default=None, max_length=50)
    hire_date: date | None = None
    probation_end_date: date | None = None
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=8)
    national_id: str | None = Field(default=None, max_length=20)
    national_id_date: date | None = None
    national_id_place: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    permanent_address: str | None = Field(default=None, max_length=500)
    current_address: str | None = Field(default=None, max_length=500)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)
    social_insurance_no: str | None = Field(default=None, max_length=20)
    pit_tax_code: str | None = Field(default=None, max_length=20)
    dependents_count: int = Field(default=0, ge=0)
    bank_account: str | None = Field(default=None, max_length=30)
    bank_name: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000)


class EmployeeCreate(EmployeeBase):
    # New employees default to Thử việc; the API accepts an override for imports.
    status: str = Field(default="probation", max_length=16)
    # Optional: create + link a login account in the same call (wizard "Lưu").
    account: AccountCreateIn | None = None


class EmployeeUpdate(EmployeeBase):
    """Edit hồ sơ. status / department reassignment / job_grade are NOT here — they are
    stage changes done via the transitions endpoint."""


# --- transitions / account --------------------------------------------------


class TransitionIn(BaseModel):
    kind: str = Field(description="confirm|leave_start|leave_end|suspend|resign|reinstate|transfer|promote")
    effective_date: date | None = None
    note: str | None = Field(default=None, max_length=500)
    new_department_id: int | None = None      # transfer
    new_job_grade: str | None = Field(default=None, max_length=50)   # promote
    new_position: str | None = Field(default=None, max_length=255)   # promote
    resign_reason: str | None = Field(default=None, max_length=255)  # resign


class LinkAccountIn(BaseModel):
    user_id: int


# --- responses --------------------------------------------------------------


class DuplicateRef(BaseModel):
    """Points at an existing employee already carrying the submitted CCCD / số BHXH."""

    id: int
    code: str
    full_name: str


class EmployeeRow(BaseModel):
    """A row in the Danh sách nhân viên list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    full_name: str
    department_id: int | None
    department_name: str | None = None
    position: str | None = None
    job_grade: str | None = None
    status: str
    hire_date: date | None = None
    probation_end_date: date | None = None
    user_id: int | None = None
    account_username: str | None = None
    photo_url: str | None = None
    created_at: datetime | None = None


class EmployeeOut(EmployeeRow):
    """Full detail (Thông tin tab). Inherits the row fields + the rest of the hồ sơ."""

    date_of_birth: date | None = None
    gender: str | None = None
    national_id: str | None = None
    national_id_date: date | None = None
    national_id_place: str | None = None
    phone: str | None = None
    email: str | None = None
    permanent_address: str | None = None
    current_address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    social_insurance_no: str | None = None
    pit_tax_code: str | None = None
    dependents_count: int = 0
    bank_account: str | None = None
    bank_name: str | None = None
    resign_date: date | None = None
    resign_reason: str | None = None
    note: str | None = None


class EmployeeKpis(BaseModel):
    """List header KPI strip — rolled up over the whole scoped set."""

    total: int
    active: int
    probation: int
    on_leave: int
    resigned: int
    probation_ending_soon: int  # probation_end_date trong ≤N ngày


class EmployeeListOut(BaseModel):
    items: list[EmployeeRow]
    total: int
    page: int
    size: int
    kpis: EmployeeKpis


class EmployeeCreateOut(BaseModel):
    """Create response: the new employee + optional soft duplicate warnings + created
    account username (if the wizard also created one)."""

    employee: EmployeeOut
    duplicate_national_id: DuplicateRef | None = None
    duplicate_social_insurance: DuplicateRef | None = None
    account_username: str | None = None


class EmployeeUpdateOut(BaseModel):
    employee: EmployeeOut
    duplicate_national_id: DuplicateRef | None = None
    duplicate_social_insurance: DuplicateRef | None = None


class EmployeeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    effective_date: date | None = None
    field: str | None = None
    from_value: str | None = None
    to_value: str | None = None
    note: str | None = None
    actor_user_id: int | None = None
    actor_name: str | None = None
    created_at: datetime | None = None


class EmployeeEventsOut(BaseModel):
    items: list[EmployeeEventOut]


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_kind: str
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime | None = None


class AttachmentsOut(BaseModel):
    items: list[AttachmentOut]


class EmployeeActivityRowOut(BaseModel):
    """One entry in an employee's Nhật ký (from the audit log, target employee:<id>)."""

    action: str
    target: str
    detail: str
    actor_name: str | None = None
    created_at: datetime


class EmployeeActivityOut(BaseModel):
    items: list[EmployeeActivityRowOut]


class DepartmentOption(BaseModel):
    id: int
    name: str


class UserOption(BaseModel):
    id: int
    username: str
    name: str


class EmployeeMetaOut(BaseModel):
    """Dropdown data for the forms: departments + login accounts not yet linked to any NV."""

    departments: list[DepartmentOption]
    unlinked_users: list[UserOption]
