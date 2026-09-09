"""Gỡ đình chỉ (test luồng 08/09/2026, điểm cấn 1): `unsuspend` trả về ĐÚNG trạng thái trước khi
đình chỉ — thử việc vẫn thử việc, chính thức về chính thức, đang nghỉ dài hạn thì đi làm lại;
mốc `unsuspended` ghi vào Quá trình công tác; không gỡ được khi không đình chỉ."""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository
from tests.test_bien_che_dung_chung_08_09 import _chuyen
from tests.test_luong_api import _admin_token, _h


def _tao(client, h, *, name: str, status: str) -> int:
    db = SessionLocal()
    try:
        did = DepartmentRepository(db).get_by_name("Sản xuất").id
    finally:
        db.close()
    body = {"full_name": name, "department_id": did, "hire_date": "2026-01-05", "gender": "male",
            "status": status}
    if status == "probation":
        body["probation_end_date"] = "2026-12-31"
    r = client.post("/api/employees", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["employee"]["id"]


def _trang_thai(client, h, eid: int) -> str:
    return client.get(f"/api/employees/{eid}", headers=h).json()["status"]


def test_go_dinh_chi_thu_viec_ve_thu_viec(client):
    h = _h(_admin_token(client))
    eid = _tao(client, h, name="Thợ thử việc bị đình chỉ", status="probation")
    assert _chuyen(client, h, eid, "suspend", "2026-09-01").status_code == 200
    assert _trang_thai(client, h, eid) == "suspended"
    r = _chuyen(client, h, eid, "unsuspend", "2026-09-05", note="đã làm rõ")
    assert r.status_code == 200, r.text
    assert _trang_thai(client, h, eid) == "probation"      # KHÔNG "lên chính thức chui"
    ev = client.get(f"/api/employees/{eid}/events", headers=h).json()["items"]
    moc = next(e for e in ev if e["event_type"] == "unsuspended")
    assert moc["from_value"] == "suspended" and moc["to_value"] == "probation"
    assert moc["effective_date"] == "2026-09-05" and moc["note"] == "đã làm rõ"


def test_go_dinh_chi_chinh_thuc_ve_chinh_thuc_va_nghi_dai_han_thi_di_lam_lai(client):
    h = _h(_admin_token(client))
    a = _tao(client, h, name="Chính thức bị đình chỉ", status="active")
    assert _chuyen(client, h, a, "suspend", "2026-09-01").status_code == 200
    assert _chuyen(client, h, a, "unsuspend", "2026-09-02").status_code == 200
    assert _trang_thai(client, h, a) == "active"

    b = _tao(client, h, name="Nghỉ dài hạn bị đình chỉ", status="active")
    assert _chuyen(client, h, b, "leave_start", "2026-08-01").status_code == 200
    assert _chuyen(client, h, b, "suspend", "2026-08-15").status_code == 200
    assert _chuyen(client, h, b, "unsuspend", "2026-09-01").status_code == 200
    assert _trang_thai(client, h, b) == "active"           # gỡ xong là đi làm lại


def test_khong_go_khi_khong_dinh_chi(client):
    h = _h(_admin_token(client))
    eid = _tao(client, h, name="Đang làm bình thường", status="active")
    r = _chuyen(client, h, eid, "unsuspend", "2026-09-01")
    assert r.status_code == 400, r.text
    assert "unsuspend" in r.json()["detail"]
