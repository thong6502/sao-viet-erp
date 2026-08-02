"""Luồng danh mục tài liệu nội quy: Xem / Thêm / Xóa."""
from __future__ import annotations

import io

from app.db import SessionLocal
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, create_file_token, decode_access_token, hash_password
from tests.test_luong_api import _admin_token, _h


def _staff_token(*, create=False, delete=False) -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)
        dept = depts.get_by_name("Kinh doanh")
        role = roles.get_by_name_and_department("NV Sales", dept.id)
        roles.set_permission(
            role_id=role.id,
            module_key="noi_quy",
            can_read=False,
            can_create=create,
            can_update=False,
            can_delete=delete,
            scope="all",
        )
        user = users.get_by_username("nv-noi-quy")
        if user is None:
            user = users.create(
                username="nv-noi-quy",
                name="Nhân viên nội quy",
                password_hash=hash_password("x"),
            )
        users.set_assignment(user, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(user.id))
    finally:
        db.close()


def _pdf(name="noi-quy.pdf"):
    return {"file": (name, io.BytesIO(b"%PDF-1.4\nnoi quy\n%%EOF"), "application/pdf")}


def _use_file_cookie(client, access_token: str) -> None:
    claims = decode_access_token(access_token)
    client.cookies.clear()
    client.cookies.set("file_access", create_file_token(str(claims["sub"])), path="/api/files")


def _create(client, token, *, name="Nội quy lao động", note="Áp dụng toàn công ty"):
    return client.post(
        "/api/noi-quy",
        data={"name": name, "note": note},
        files=_pdf(),
        headers=_h(token),
    )


def test_tao_ban_ghi_co_ma_nguoi_va_ngay_upload(client):
    token = _admin_token(client)
    response = _create(client, token)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["id"] > 0
    assert row["code"].startswith("NQ-") and len(row["code"].split("-")[-1]) == 4
    assert row["name"] == "Nội quy lao động"
    assert row["note"] == "Áp dụng toàn công ty"
    assert row["file_name"] == "noi-quy.pdf"
    assert row["file_type"] == "application/pdf"
    assert row["uploaded_by_user_id"] > 0
    assert row["uploaded_by_name"]
    assert row["uploaded_at"]

    listed = client.get("/api/noi-quy", headers=_h(token))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [row["id"]]


def test_moi_nhan_vien_dang_nhap_deu_xem_danh_sach_va_mo_file(client):
    admin = _admin_token(client)
    row = _create(client, admin).json()
    viewer = _staff_token()
    _use_file_cookie(client, viewer)

    listed = client.get("/api/noi-quy", headers=_h(viewer))
    assert listed.status_code == 200
    opened = client.get(row["file_url"], headers=_h(viewer))
    assert opened.status_code == 200
    assert opened.headers["content-type"].startswith("application/pdf")


def test_chua_dang_nhap_thi_khong_xem_duoc_noi_quy(client):
    assert client.get("/api/noi-quy").status_code == 401


def test_quyen_them_va_xoa_tach_rieng(client):
    creator = _staff_token(create=True, delete=False)
    made = _create(client, creator, name="An toàn lao động")
    assert made.status_code == 201, made.text
    record_id = made.json()["id"]
    assert client.delete(f"/api/noi-quy/{record_id}", headers=_h(creator)).status_code == 403

    deleter = _staff_token(create=False, delete=True)
    assert _create(client, deleter).status_code == 403
    assert client.delete(f"/api/noi-quy/{record_id}", headers=_h(deleter)).status_code == 204


def test_xoa_ban_ghi_thi_file_cung_bi_go(client):
    admin = _admin_token(client)
    row = _create(client, admin).json()
    assert client.delete(f"/api/noi-quy/{row['id']}", headers=_h(admin)).status_code == 204
    assert client.get(row["file_url"], headers=_h(admin)).status_code == 404
    assert client.get("/api/noi-quy", headers=_h(admin)).json()["items"] == []


def test_chi_nhan_file_trinh_duyet_preview_duoc_va_kiem_chu_ky_file(client):
    token = _admin_token(client)
    png = client.post(
        "/api/noi-quy",
        data={"name": "Sơ đồ thoát hiểm"},
        files={"file": ("so-do.png", io.BytesIO(b"\x89PNG\r\n\x1a\nDATA"), "image/png")},
        headers=_h(token),
    )
    assert png.status_code == 201 and png.json()["file_type"] == "image/png"

    word = client.post(
        "/api/noi-quy",
        data={"name": "File Word"},
        files={"file": ("noi-quy.docx", io.BytesIO(b"PK..."), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=_h(token),
    )
    assert word.status_code == 400 and "PDF" in word.json()["detail"]

    fake = client.post(
        "/api/noi-quy",
        data={"name": "PDF giả"},
        files={"file": ("gia.pdf", io.BytesIO(b"not a pdf"), "application/pdf")},
        headers=_h(token),
    )
    assert fake.status_code == 400


def test_validate_ten_file_rong_va_dung_luong_o_server(client):
    token = _admin_token(client)
    no_name = _create(client, token, name="   ")
    assert no_name.status_code == 400 and "Tên tài liệu" in no_name.json()["detail"]

    empty = client.post(
        "/api/noi-quy",
        data={"name": "Rỗng"},
        files={"file": ("rong.pdf", io.BytesIO(b""), "application/pdf")},
        headers=_h(token),
    )
    assert empty.status_code == 400 and "trống" in empty.json()["detail"]

    too_large = client.post(
        "/api/noi-quy",
        data={"name": "Quá lớn"},
        files={"file": ("lon.pdf", io.BytesIO(b"%PDF-" + b"x" * (20 * 1024 * 1024)), "application/pdf")},
        headers=_h(token),
    )
    assert too_large.status_code == 400 and "20 MB" in too_large.json()["detail"]


def test_khong_co_api_sua_va_co_nhat_ky_them_xoa(client):
    token = _admin_token(client)
    row = _create(client, token).json()
    assert client.patch(
        f"/api/noi-quy/{row['id']}", json={"name": "Không được sửa"}, headers=_h(token)
    ).status_code == 405
    assert client.delete(f"/api/noi-quy/{row['id']}", headers=_h(token)).status_code == 204

    db = SessionLocal()
    try:
        actions = [item.action for item in AuditLogRepository(db).list_recent(10)]
    finally:
        db.close()
    assert "create_noi_quy_record" in actions
    assert "delete_noi_quy_record" in actions


def test_giam_doc_mac_dinh_khong_co_quyen_sua_noi_quy(client):
    client
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)
        dept = depts.get_by_name("Ban giám đốc")
        role = roles.get_by_name_and_department("Giám đốc", dept.id)
        permission = next(
            p for p in roles.permissions_for(role.id) if p.module_key == "noi_quy"
        )
    finally:
        db.close()
    assert permission.can_read and permission.can_create and permission.can_delete
    assert permission.can_update is False
