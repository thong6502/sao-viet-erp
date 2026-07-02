"""Enabling point for the Tài xế (drivers) cross-module seam (spec-16-tai-xe).

Source of truth for the seam = the `# SEAM-19` marker in app/ports/driver_hr_port.py
+ the matching skip test here. docs/CROSS_MODULE_LINKS.md is only an index.

NOTE: SEAM-01..18 were already claimed by earlier specs, so this driver seam takes 19
(spec-14 Khoản mục chi phí took the next one, 20).

Back-fill DoD: make the skip test pass against the real `employees` provider, DELETE
the stub, add the real `drivers.employee_id` FK→employees.id, flip ⏳→✅ in the
registry, then remove the skip marker below.
"""
from __future__ import annotations

import pytest

from app.ports.driver_hr_port import default_driver_employee_port


@pytest.mark.skip(reason="SEAM-19 Tài xế cần resolve nhân viên (employee_id) từ Nhân sự (employees) — chưa build")
def test_seam_19_resolve_employee():
    port = default_driver_employee_port()
    # After back-fill: an internal driver linked to a real employee resolves its ref.
    ref = port.get_employee(employee_id=1)
    assert ref is not None and ref["id"] == 1


def test_seam_19_stub_raises():
    """The stub must raise, not silently return a fake employee (would fake a link)."""
    with pytest.raises(NotImplementedError, match="SEAM-19"):
        default_driver_employee_port().get_employee(employee_id=1)
