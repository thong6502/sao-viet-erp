"""Tệp đính kèm của lệnh sản xuất — /api/lsx/{id}/dinh-kem.

Bám mẫu đính kèm báo giá (storage + đọc lại qua /api/files có kiểm quyền + vết ở Nhật ký), thêm:
  - nhiều tệp, kể cả trùng tên, không đè nhau;
  - người tải do máy chủ chốt từ tài khoản, trả kèm tên để màn hiện;
  - chặn tệp chạy được (.exe/.bat…) — tệp đi xuống xưởng, không phải chỗ phát phần mềm;
  - xoá lệnh thì dọn luôn tệp trong kho (CASCADE chỉ xoá dòng, không xoá object).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.lsx import Lsx
from app.models.order import STATUS_CANCELLED, Order, OrderLine
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password

MAX_BYTES = 50 * 1024 * 1024


def _login(client, username="admin", password="admin123") -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _tao_lsx(order_status: str = "ordered") -> int:
    """Lệnh tối thiểu: đơn + dòng đơn + lệnh. Đính kèm không đọc routing/quy cách nên khỏi dựng."""
    db = SessionLocal()
    try:
        n = db.query(Lsx).count() + 1
        order = Order(order_no=f"DH-DK-{n:04d}", status=order_status)
        db.add(order)
        db.flush()
        line = OrderLine(order_id=order.id, description="Hộp giấy", qty=500)
        db.add(line)
        db.flush()
        lsx = Lsx(ma=f"LSX-DK-{n:04d}", ten="Hộp giấy", order_id=order.id, order_line_id=line.id)
        db.add(lsx)
        db.commit()
        return lsx.id
    finally:
        db.close()


def _huy_don(lsx_id: int) -> None:
    db = SessionLocal()
    try:
        lsx = db.get(Lsx, lsx_id)
        db.get(Order, lsx.order_id).status = STATUS_CANCELLED
        db.commit()
    finally:
        db.close()


def _tai_len(client, h, lsx_id, name="maket.pdf", data=b"%PDF-noi-dung", ctype="application/pdf"):
    return client.post(f"/api/lsx/{lsx_id}/dinh-kem", files={"file": (name, data, ctype)}, headers=h)


def _ds(client, h, lsx_id) -> list[dict]:
    r = client.get(f"/api/lsx/{lsx_id}/dinh-kem", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _nhat_ky(client, h, lsx_id) -> list[dict]:
    return client.get(f"/api/lsx/{lsx_id}/activity", headers=h).json()["items"]


def _user(username: str, *, doc: bool, sua: bool) -> None:
    """Người dùng có (hoặc không có) ô Sản xuất — chứng minh gate đọc/sửa có tác dụng."""
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name("Kế toán")
        roles = RoleRepository(db)
        role = roles.create(name=f"Vai {username}", department_id=dept.id)
        if doc or sua:
            roles.set_permission(role_id=role.id, module_key="san_xuat", can_read=doc,
                                 can_update=sua, scope=SCOPE_ALL)
        users = UserRepository(db)
        u = users.create(username=username, name=username, password_hash=hash_password("matkhau123"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
    finally:
        db.close()


# --- vòng đời ------------------------------------------------------------------

def test_tai_nhieu_tep_xem_tai_ve_roi_xoa(client):
    h = _login(client)
    lsx_id = _tao_lsx()
    assert _ds(client, h, lsx_id) == []

    a = _tai_len(client, h, lsx_id, "maket.pdf", b"%PDF-maket")
    b = _tai_len(client, h, lsx_id, "anh-mau.png", b"PNG-mau", "image/png")
    assert a.status_code == 201, a.text
    assert b.status_code == 201, b.text
    ta = a.json()
    assert ta["ten_tep"] == "maket.pdf"
    assert ta["content_type"] == "application/pdf"
    assert ta["kich_thuoc"] == len(b"%PDF-maket")
    assert ta["nguoi_tai_ten"]  # server chốt từ tài khoản, không để trống
    assert ta["file_url"].startswith(f"/api/files/san-xuat/lsx/{lsx_id}/")

    items = _ds(client, h, lsx_id)
    assert {i["ten_tep"] for i in items} == {"maket.pdf", "anh-mau.png"}

    got = client.get(ta["file_url"])
    assert got.status_code == 200 and got.content == b"%PDF-maket"

    # Màn Nhật ký hệ thống gom mọi lệnh về một chỗ ⇒ câu phải tự nói lệnh nào; tên tệp có dấu cách
    # nên bọc ngoặc để không dính vào chữ đứng trước.
    ma = client.get(f"/api/lsx/{lsx_id}", headers=h).json()["ma"]
    them = [x for x in _nhat_ky(client, h, lsx_id) if x["action"] == "lsx_dinh_kem_them"]
    assert len(them) == 2
    assert f"Lệnh {ma}: đính kèm tệp “maket.pdf”" in {x["detail"] for x in them}

    d = client.delete(f"/api/lsx/{lsx_id}/dinh-kem/{ta['id']}", headers=h)
    assert d.status_code == 204, d.text
    assert [i["ten_tep"] for i in _ds(client, h, lsx_id)] == ["anh-mau.png"]
    assert client.get(ta["file_url"]).status_code == 404  # object đã dọn khỏi kho
    xoa = [x for x in _nhat_ky(client, h, lsx_id) if x["action"] == "lsx_dinh_kem_xoa"]
    assert [x["detail"] for x in xoa] == [f"Lệnh {ma}: xoá tệp đính kèm “maket.pdf”"]


def test_hai_tep_trung_ten_khong_de_nhau(client):
    h = _login(client)
    lsx_id = _tao_lsx()
    a = _tai_len(client, h, lsx_id, "maket.pdf", b"ban-1").json()
    b = _tai_len(client, h, lsx_id, "maket.pdf", b"ban-2").json()
    assert a["file_url"] != b["file_url"]
    assert client.get(a["file_url"]).content == b"ban-1"
    assert client.get(b["file_url"]).content == b"ban-2"


def test_xoa_lenh_don_luon_tep_trong_kho(client):
    h = _login(client)
    lsx_id = _tao_lsx()
    url = _tai_len(client, h, lsx_id).json()["file_url"]
    r = client.delete(f"/api/lsx/{lsx_id}", headers=h)
    assert r.status_code == 200, r.text
    assert client.get(url).status_code == 404


# --- chặn ---------------------------------------------------------------------

def test_tep_rong_bi_chan(client):
    h = _login(client)
    assert _tai_len(client, h, _tao_lsx(), data=b"").status_code == 400


def test_tep_qua_50mb_bi_chan(client):
    h = _login(client)
    lsx_id = _tao_lsx()
    r = _tai_len(client, h, lsx_id, "catalog.pdf", b"\0" * (MAX_BYTES + 1))
    assert r.status_code == 413, r.text
    assert _ds(client, h, lsx_id) == []


def test_tep_dung_50mb_van_nhan(client):
    h = _login(client)
    r = _tai_len(client, h, _tao_lsx(), "catalog.pdf", b"\0" * MAX_BYTES)
    assert r.status_code == 201, r.text


def test_tep_chay_duoc_bi_chan(client):
    h = _login(client)
    lsx_id = _tao_lsx()
    for ten in ("cai-dat.exe", "chay.BAT", "lenh.ps1"):
        r = _tai_len(client, h, lsx_id, ten, b"MZ", "application/octet-stream")
        assert r.status_code == 415, (ten, r.text)
    assert _ds(client, h, lsx_id) == []


def test_don_huy_van_xem_nhung_khong_them_xoa(client):
    h = _login(client)
    lsx_id = _tao_lsx()
    tep = _tai_len(client, h, lsx_id).json()
    _huy_don(lsx_id)
    assert len(_ds(client, h, lsx_id)) == 1
    assert _tai_len(client, h, lsx_id).status_code == 409
    assert client.delete(f"/api/lsx/{lsx_id}/dinh-kem/{tep['id']}", headers=h).status_code == 409


def test_khong_xoa_duoc_tep_cua_lenh_khac(client):
    h = _login(client)
    la, lb = _tao_lsx(), _tao_lsx()
    tep = _tai_len(client, h, la).json()
    assert client.delete(f"/api/lsx/{lb}/dinh-kem/{tep['id']}", headers=h).status_code == 404
    assert len(_ds(client, h, la)) == 1


def test_lenh_khong_ton_tai_tra_404(client):
    h = _login(client)
    assert client.get("/api/lsx/999999/dinh-kem", headers=h).status_code == 404
    assert _tai_len(client, h, 999999).status_code == 404


# --- quyền --------------------------------------------------------------------

def test_chi_quyen_doc_thi_xem_duoc_nhung_khong_them_xoa(client):
    admin = _login(client)
    lsx_id = _tao_lsx()
    tep = _tai_len(client, admin, lsx_id).json()
    _user("chi-doc-sx", doc=True, sua=False)
    h = _login(client, "chi-doc-sx", "matkhau123")
    assert len(_ds(client, h, lsx_id)) == 1
    assert client.get(tep["file_url"]).status_code == 200
    assert _tai_len(client, h, lsx_id).status_code == 403
    assert client.delete(f"/api/lsx/{lsx_id}/dinh-kem/{tep['id']}", headers=h).status_code == 403


def test_khong_co_quyen_san_xuat_thi_khong_xem_duoc(client):
    admin = _login(client)
    lsx_id = _tao_lsx()
    tep = _tai_len(client, admin, lsx_id).json()
    _user("khong-sx", doc=False, sua=False)
    h = _login(client, "khong-sx", "matkhau123")
    assert client.get(f"/api/lsx/{lsx_id}/dinh-kem", headers=h).status_code == 403
    assert client.get(tep["file_url"]).status_code == 403


# --- migration (DB dev/prod dựng trước ngày có bảng) ------------------------------------------

def test_migration_tao_bang_tren_db_cu_va_chay_lai_khong_loi():
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import Session

    from app.db_migrations import _migrate_lsx_dinh_kem

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE lsx (id INTEGER PRIMARY KEY, ma VARCHAR(30))"))
        cn.execute(text("INSERT INTO lsx (id, ma) VALUES (1, 'LSX26-0001')"))
    for _ in range(2):  # lần hai phải no-op
        with Session(engine) as db:
            _migrate_lsx_dinh_kem(db)

    ins = inspect(engine)
    assert {c["name"] for c in ins.get_columns("lsx_dinh_kem")} == {
        "id", "lsx_id", "ten_tep", "file_url", "content_type", "kich_thuoc", "nguoi_tai_id", "tai_luc",
    }
    assert "ix_lsx_dinh_kem_lsx_id" in {i["name"] for i in ins.get_indexes("lsx_dinh_kem")}
    with engine.begin() as cn:
        cn.execute(text("INSERT INTO lsx_dinh_kem (lsx_id, ten_tep, file_url, tai_luc) "
                        "VALUES (1, 'a.pdf', '/api/files/x', CURRENT_TIMESTAMP)"))
        assert cn.execute(text("SELECT kich_thuoc FROM lsx_dinh_kem")).scalar() == 0
