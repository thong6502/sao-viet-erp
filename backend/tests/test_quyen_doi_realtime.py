"""Đổi quyền ⇒ đẩy `quyen_doi` qua SSE tới đúng người đang giữ bộ quyền đó.

Máy chủ gác quyền bằng DB ở mỗi request, nhưng giao diện chỉ hỏi bộ quyền một lần lúc vào phiên:
thiếu cú đẩy này thì người bị rút quyền vẫn thấy menu cũ, người được cấp thì phải F5.

Mỗi bài kiểm cả ĐÚNG NGƯỜI (không đẩy nhầm sang người khác vai) lẫn ĐẨY SAU COMMIT: hàm giả của
`hub.publish` tự mở phiên DB mới đọc lại — thấy dữ liệu cũ nghĩa là giao diện hỏi lại quyền cũng
chỉ nhận về bộ quyền cũ.
"""
from __future__ import annotations

import pytest

from app import realtime
from app.db import SessionLocal
from app.models.user import User
from app.repositories.rbac_repo import RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _h(client) -> dict[str, str]:
    token = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _role_id_cua(user_id: int) -> int | None:
    db = SessionLocal()
    try:
        return db.get(User, user_id).role_id
    finally:
        db.close()


def _make_user(username: str, dept_id: int, role_id: int | None) -> int:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept_id, role_id=role_id, is_active=True)
        return u.id
    finally:
        db.close()


@pytest.fixture
def da_day(monkeypatch):
    """Ghi lại `(user_id, role_id lúc đẩy)` cho mỗi sự kiện `quyen_doi`."""
    ra: list[tuple[int, int | None]] = []

    def gia(uid, ev):
        if ev.get("type") == "quyen_doi":
            ra.append((uid, _role_id_cua(uid)))

    monkeypatch.setattr(realtime.hub, "publish", gia)
    return ra


def _phong_va_vai(client, h, ten: str) -> tuple[int, int, int]:
    dept = client.post("/api/departments", json={"name": ten}, headers=h).json()
    vai_a = client.post("/api/roles", json={"name": f"{ten} A", "department_id": dept["id"]},
                        headers=h).json()
    vai_b = client.post("/api/roles", json={"name": f"{ten} B", "department_id": dept["id"]},
                        headers=h).json()
    return dept["id"], vai_a["id"], vai_b["id"]


def test_luu_ma_tran_day_toi_moi_nguoi_giu_vai_va_chi_ho(client, monkeypatch):
    h = _h(client)
    dept, vai_a, vai_b = _phong_va_vai(client, h, "QD Ma trận")
    giu_1 = _make_user("qd-mt-1", dept, vai_a)
    giu_2 = _make_user("qd-mt-2", dept, vai_a)
    _make_user("qd-mt-3", dept, vai_b)

    # Ghi lại `(user_id, Xem khách hàng lúc đẩy)` — phiên DB khác đọc được quyền mới thì giao diện
    # hỏi lại cũng thấy quyền mới.
    ra: list[tuple[int, bool]] = []

    def gia(uid, ev):
        if ev.get("type") != "quyen_doi":
            return
        db = SessionLocal()
        try:
            p = RoleRepository(db).get_permission(vai_a, "khach_hang")
            ra.append((uid, bool(p and p.can_read)))
        finally:
            db.close()

    monkeypatch.setattr(realtime.hub, "publish", gia)

    rows = client.get(f"/api/roles/{vai_a}/permissions", headers=h).json()
    next(r for r in rows if r["module_key"] == "khach_hang")["can_read"] = True
    resp = client.put(f"/api/roles/{vai_a}/permissions", json={"permissions": rows}, headers=h)
    assert resp.status_code == 200

    # Đúng hai người giữ vai A, người vai B không bị làm phiền.
    assert sorted(ra) == sorted([(giu_1, True), (giu_2, True)])


def test_gan_vai_mot_nguoi_day_sau_khi_da_ghi(client, da_day):
    h = _h(client)
    dept, vai_a, _ = _phong_va_vai(client, h, "QD Gán đơn")
    uid = _make_user("qd-gan-1", dept, None)

    resp = client.put(f"/api/users/{uid}/role", json={"role_id": vai_a}, headers=h)
    assert resp.status_code == 200
    assert da_day == [(uid, vai_a)]


def test_gan_vai_hang_loat_day_tung_nguoi(client, da_day):
    h = _h(client)
    dept, vai_a, _ = _phong_va_vai(client, h, "QD Gán loạt")
    u1 = _make_user("qd-loat-1", dept, None)
    u2 = _make_user("qd-loat-2", dept, None)

    resp = client.post("/api/departments/assign-role",
                       json={"user_ids": [u1, u2], "role_id": vai_a}, headers=h)
    assert resp.status_code == 200
    assert sorted(da_day) == sorted([(u1, vai_a), (u2, vai_a)])


def test_doi_phong_go_vai_thi_day_doi_ten_thi_khong(client, da_day):
    h = _h(client)
    dept, vai_a, _ = _phong_va_vai(client, h, "QD Đổi phòng")
    dich = client.post("/api/departments", json={"name": "QD Đổi phòng đích"}, headers=h).json()
    uid = _make_user("qd-doi-phong", dept, vai_a)

    ten = client.put(f"/api/users/{uid}", json={"name": "Chỉ đổi tên", "department_id": dept},
                     headers=h)
    assert ten.status_code == 200
    assert da_day == []   # quyền không đổi ⇒ không làm phiền

    doi = client.put(f"/api/users/{uid}", json={"name": "Chỉ đổi tên", "department_id": dich["id"]},
                     headers=h)
    assert doi.status_code == 200
    assert da_day == [(uid, None)]


def test_dieu_chuyen_nhan_su_go_vai_thi_day(client, da_day):
    h = _h(client)
    dept, vai_a, _ = _phong_va_vai(client, h, "QD Điều chuyển")
    dich = client.post("/api/departments", json={"name": "QD Điều chuyển đích"}, headers=h).json()
    emp = client.post("/api/employees", json={
        "full_name": "QD Người Đi", "department_id": dept, "hire_date": "2024-01-15",
        "probation_end_date": "2025-12-31",
        "account": {"username": "qd-dieu-chuyen", "password": "password123", "role_id": vai_a},
    }, headers=h)
    assert emp.status_code == 201, emp.text
    e = emp.json()["employee"]

    resp = client.post("/api/departments/transfer",
                       json={"employee_ids": [e["id"]], "target_department_id": dich["id"]},
                       headers=h)
    assert resp.status_code == 200
    assert da_day == [(e["user_id"], None)]
