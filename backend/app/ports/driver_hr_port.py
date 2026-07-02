"""Port the Tài xế (drivers) catalog needs from a module that is NOT built yet.

Per DIP: the *consumer* (Danh mục & Cấu hình · Tài xế) OWNS this interface; the
*provider* (Nhân sự / HCNS, table `employees`) implements it later. Until then the
default implementation is an explicit stub that raises — never a silent fake value
(a fake employee record would let an internal driver look "linked" to a person who
does not exist). See docs/CROSS_MODULE_LINKS.md.

Why a seam and not a plain FK:
  A `drivers.employee_id` FK→employees.id cannot be declared at P0 because the
  `employees` table does not exist yet (DB_SCHEMA has 17 tables, none is
  `employees`) — declaring the constraint now would point at a phantom table and
  break create_all / DDL. So `employee_id` is a nullable Integer, indexed, with NO
  FK constraint (the "FK nullable" seam kind), exactly like customers↔receivable
  reads AR through SEAM-16 instead of modelling an FK. The constraint is added when
  Nhân sự builds `employees` (back-fill = add FK + close seam).

Seam parked here (SEAM-01..18 were claimed by earlier specs, so this driver seam
takes 19; spec-14 Khoản mục chi phí took the next one, 20):
  - SEAM-19  employee resolve (an internal driver may be an HR employee) → Nhân sự (`employees`)
"""
from __future__ import annotations

from typing import Optional, Protocol, TypedDict


class EmployeeRef(TypedDict):
    """Read-only display of the HR employee an internal driver is linked to."""

    id: int
    name: str
    code: str


class DriverEmployeePort(Protocol):
    """Resolve the HR employee behind `drivers.employee_id`. Owned by Tài xế,
    implemented by Nhân sự (module `nhan_su`, table `employees`) once it exists."""

    def get_employee(self, employee_id: int) -> Optional[EmployeeRef]:
        """Return the employee's display ref, or None if the id is unknown. Used to
        show 'Nhân viên: <name>' on an internal driver; NOT for pricing/payroll."""
        ...


# --- Default stub (SEAM placeholder) ----------------------------------------
# This is the "chỗ nối". It MUST raise, not return a fake value.

class _UnimplementedDriverEmployee:
    def get_employee(self, employee_id: int) -> Optional[EmployeeRef]:  # noqa: ARG002
        # SEAM-19: chờ Nhân sự (HCNS · employees)
        raise NotImplementedError("SEAM-19 chưa back-fill")


def default_driver_employee_port() -> DriverEmployeePort:
    """Wired-in default until Nhân sự back-fills SEAM-19."""
    return _UnimplementedDriverEmployee()
