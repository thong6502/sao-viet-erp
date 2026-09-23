"""Tên đăng nhập trùng phải bị chặn — và chặn TRƯỚC khi đẻ ra hồ sơ (23/09/2026).

Lỗi cũ: màn "Thêm nhân viên" khai tài khoản trùng tên ⇒ hồ sơ đã lưu xong rồi mới báo "Tên đăng
nhập đã tồn tại". Màn không nhận được id nên bấm Lưu lại là tạo THÊM một hồ sơ nữa (trùng người).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models import Employee
from app.repositories.rbac_repo import DepartmentRepository

ADMIN = {"username": "admin", "password": "admin123"}


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id() -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name("Hành chính nhân sự").id
    finally:
        db.close()


def _dem(ten: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Employee).filter(Employee.full_name == ten).count()
    finally:
        db.close()


def _tao(client, h, ten: str, username: str):
    return client.post("/api/employees", headers=h, json={
        "full_name": ten, "department_id": _dept_id(), "hire_date": "2026-09-01",
        "probation_end_date": "2026-10-31",
        "account": {"username": username, "password": "secret1"},
    })


def test_tai_khoan_trung_ten_bi_chan_va_khong_de_ho_so(client):
    h = _h(client)
    r = _tao(client, h, "Trùng Tên Một", "admin")
    assert r.status_code == 400, r.text
    assert "đã" in r.json()["detail"]
    assert _dem("Trùng Tên Một") == 0, "báo trùng tên đăng nhập mà hồ sơ vẫn bị tạo"


def test_trung_ten_chi_khac_hoa_thuong_cung_bi_chan(client):
    h = _h(client)
    assert _tao(client, h, "Trùng Hoa", "ADMIN").status_code == 400
    assert _dem("Trùng Hoa") == 0


def test_ten_moi_van_tao_duoc(client):
    h = _h(client)
    r = _tao(client, h, "Tên Mới Tinh", "ten-moi-tinh")
    assert r.status_code == 201, r.text
    assert r.json()["account_username"] == "ten-moi-tinh"
