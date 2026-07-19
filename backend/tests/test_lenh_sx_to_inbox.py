"""Hộp việc TỔ (Lát 1) — VERIFY THẬT: navbar theo scope · inbox 2 tầng · gán/bỏ gán · cổng quyền.

Kiểm luồng "phát → tổ thấy việc → gán thợ → thợ thấy việc mình":
  - `GET /api/lenh-sx/to` LỌC theo scope: admin (all) thấy mọi tổ SX; thợ (own) chỉ thấy tổ mình.
  - `GET /api/lenh-sx/to/{id}/inbox` 2 tầng THEO QUYỀN: có `can_assign_work`/scope rộng → view=full
    (mọi lệnh đang chạy ghé tổ) + `can_assign`; ngược lại → view=assigned (chỉ lệnh được gán).
  - `POST/DELETE /routing/{step}/assign` gate `assign_work`: admin (không có) → 403; tổ trưởng → 200.
  - Gán thợ → thợ (view assigned) mới thấy lệnh; bỏ gán → không còn thấy.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.models.employee import STATUS_ACTIVE
from app.models.lenh_san_xuat import LENH_DANG_CHAY, LenhSanXuat, RoutingStep
from app.models.may_thiet_bi import MayThietBi
from app.models.order import Order
from app.models.role import Role
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password


def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _login(client, username: str, pw: str = "pw123456") -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": username, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _mk_to(name: str) -> int:
    """1 TỔ khối sản xuất (la_san_xuat=True) — để navbar/inbox nhận."""
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        d = depts.create(name=name)
        depts.set_la_san_xuat(d, True)
        return d.id
    finally:
        db.close()


def _seed_dang_chay(to_id: int, suffix: str) -> tuple[int, int]:
    """1 đơn + 1 LỆNH đang chạy (đã phát) + 1 bước routing thuộc `to_id`. Trả (lenh_id, step_id)."""
    db = SessionLocal()
    try:
        order = Order(order_no=f"DH-TO-{suffix}", status="ordered")
        db.add(order)
        db.flush()
        lenh = LenhSanXuat(order_id=order.id, trang_thai=LENH_DANG_CHAY)
        db.add(lenh)
        db.flush()
        step = RoutingStep(lenh_sx_id=lenh.id, thu_tu=1, cong_doan_id=None, to_id=to_id, ten="Bế & Xén")
        db.add(step)
        db.commit()
        return lenh.id, step.id
    finally:
        db.close()


def _mk_user(username: str, role_name: str, dept_id: int) -> int:
    """User (login được, pw pw123456) + hồ sơ NV gắn tổ (để hiện trong danh sách gán). Trả user_id."""
    db = SessionLocal()
    try:
        role = db.execute(select(Role).where(Role.name == role_name)).scalars().first()
        assert role is not None, f"Chưa seed vai {role_name!r}"
        users = UserRepository(db)
        u = users.create(username=username, name=username, password_hash=hash_password("pw123456"))
        users.set_assignment(u, department_id=dept_id, role_id=role.id, is_active=True)
        uid = u.id
        emp_repo = EmployeeRepository(db)
        emp = emp_repo.create(
            full_name=username, department_id=dept_id, status=STATUS_ACTIVE, hire_date=date.today(),
        )
        emp_repo.update(emp, user_id=uid)
        return uid
    finally:
        db.close()


def test_to_inbox_full_shows_dang_chay(client):
    h = _admin(client)
    to_id = _mk_to("Tổ Bế A")
    lenh_id, step_id = _seed_dang_chay(to_id, "A")

    d = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h).json()
    assert d["view"] == "full"           # admin scope=all → giám sát → thấy FULL
    assert d["can_assign"] is False       # admin KHÔNG có can_assign_work
    it = next(x for x in d["items"] if x["lenh_id"] == lenh_id)
    assert any(s["step_id"] == step_id and s["is_mine"] for s in it["steps"])  # bước của tổ = is_mine


def test_navbar_to_scoped(client):
    h = _admin(client)
    to_a = _mk_to("Tổ Nav A")
    to_b = _mk_to("Tổ Nav B")
    # admin (scope all) thấy MỌI tổ SX
    ids_admin = {t["id"] for t in client.get("/api/lenh-sx/to", headers=h).json()["items"]}
    assert {to_a, to_b} <= ids_admin

    # thợ tổ A (scope own) CHỈ thấy tổ mình, không thấy tổ B
    _mk_user("tho_a", "Thợ SX", to_a)
    h_tho = _login(client, "tho_a")
    ids_tho = {t["id"] for t in client.get("/api/lenh-sx/to", headers=h_tho).json()["items"]}
    assert to_a in ids_tho and to_b not in ids_tho


def test_assign_requires_permission(client):
    h = _admin(client)
    to_id = _mk_to("Tổ Bế B")
    _, step_id = _seed_dang_chay(to_id, "B")
    # admin có read (thấy) nhưng KHÔNG có assign_work → gán bị chặn 403
    r = client.post(f"/api/lenh-sx/routing/{step_id}/assign", json={"user_ids": [1]}, headers=h)
    assert r.status_code == 403, r.text


def test_assign_and_worker_scoped_view(client):
    _admin(client)  # kích hoạt seed (roles SX)
    to_id = _mk_to("Tổ Bế C")
    lenh_id, step_id = _seed_dang_chay(to_id, "C")
    tho_uid = _mk_user("tho_c", "Thợ SX", to_id)
    _mk_user("tt_c", "Tổ trưởng SX", to_id)
    h_tt = _login(client, "tt_c")

    # Tổ trưởng: view full + can_assign
    d = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h_tt).json()
    assert d["view"] == "full" and d["can_assign"] is True

    # Gán thợ vào bước → 200, assignee hiện trong inbox
    r = client.post(f"/api/lenh-sx/routing/{step_id}/assign", json={"user_ids": [tho_uid]}, headers=h_tt)
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1
    d2 = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h_tt).json()
    st = next(s for it in d2["items"] if it["lenh_id"] == lenh_id for s in it["steps"] if s["step_id"] == step_id)
    assert any(a["user_id"] == tho_uid for a in st["assignees"])

    # Thợ đăng nhập: view=assigned, thấy lệnh (vì đã được gán)
    h_tho = _login(client, "tho_c")
    dt = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h_tho).json()
    assert dt["view"] == "assigned" and dt["can_assign"] is False
    assert any(it["lenh_id"] == lenh_id for it in dt["items"])

    # Bỏ gán → thợ KHÔNG còn thấy lệnh
    ud = client.delete(f"/api/lenh-sx/routing/{step_id}/assign/{tho_uid}", headers=h_tt)
    assert ud.status_code == 200, ud.text
    dt2 = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h_tho).json()
    assert all(it["lenh_id"] != lenh_id for it in dt2["items"])


def _mk_may(ma: str, ten: str, loai: str = "Cán màng / UV") -> int:
    """1 máy finishing (loai_may = chữ Việt như data thật). Trả may_id."""
    db = SessionLocal()
    try:
        m = MayThietBi(ma=ma, ten=ten, loai_may=loai, trang_thai="active")
        db.add(m)
        db.commit()
        return m.id
    finally:
        db.close()


def _set_lenh(lenh_id: int, **fields) -> None:
    db = SessionLocal()
    try:
        lenh = db.get(LenhSanXuat, lenh_id)
        for k, v in fields.items():
            setattr(lenh, k, v)
        db.commit()
    finally:
        db.close()


def test_step_may_ca_record_and_surface(client):
    """1.12 tổ xếp máy/ca cho bước (record-only) + ③④ surface khuôn/lịch/máy in chảy xuống hộp tổ."""
    _admin(client)  # kích hoạt seed vai SX
    to_id = _mk_to("Tổ Cán A")
    lenh_id, step_id = _seed_dang_chay(to_id, "MC")
    _mk_user("tt_mc", "Tổ trưởng SX", to_id)
    h_tt = _login(client, "tt_mc")
    may_id = _mk_may("MC-T1", "Máy cán màng KL-01")
    # điều độ gán máy IN + ngày chạy cho LỆNH → phải chảy read-only xuống hộp tổ
    _set_lenh(lenh_id, may_id=may_id, ngay_chay=date(2026, 7, 15))

    # tổ trưởng xếp máy finishing + ca cho bước → 200
    r = client.put(f"/api/lenh-sx/routing/{step_id}/may-ca",
                   json={"may_id": may_id, "ca": "Ca 2"}, headers=h_tt)
    assert r.status_code == 200, r.text

    d = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h_tt).json()
    it = next(x for x in d["items"] if x["lenh_id"] == lenh_id)
    # surface item (③④, read-only): keys có mặt + may_in_label resolve + ngày chạy chảy xuống
    assert "khuon_be_label" in it and "can_khuon" in it
    assert it["may_in_label"] == "Máy cán màng KL-01"
    assert str(it["ngay_chay"]).startswith("2026-07-15")
    # bước phản ánh máy/ca đã xếp (+ nhãn máy resolve)
    st = next(s for s in it["steps"] if s["step_id"] == step_id)
    assert st["may_id"] == may_id and st["may_label"] == "Máy cán màng KL-01" and st["ca"] == "Ca 2"

    # ca rỗng = gỡ ca (record-only, không chặn)
    r2 = client.put(f"/api/lenh-sx/routing/{step_id}/may-ca",
                    json={"may_id": may_id, "ca": ""}, headers=h_tt)
    assert r2.status_code == 200, r2.text
    d2 = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h_tt).json()
    st2 = next(s for x in d2["items"] if x["lenh_id"] == lenh_id
               for s in x["steps"] if s["step_id"] == step_id)
    assert st2["ca"] is None and st2["may_id"] == may_id


def test_step_may_ca_requires_permission(client):
    """Gate assign_work: admin có read nhưng KHÔNG assign_work → xếp máy/ca bị chặn 403."""
    h = _admin(client)
    to_id = _mk_to("Tổ Cán B")
    _, step_id = _seed_dang_chay(to_id, "MC2")
    r = client.put(f"/api/lenh-sx/routing/{step_id}/may-ca",
                   json={"may_id": None, "ca": "Ca 1"}, headers=h)
    assert r.status_code == 403, r.text


def _add_step(lenh_id: int, thu_tu: int, to_id: int, ten: str) -> int:
    """Thêm 1 bước routing vào lệnh (để test bàn giao giữa 2 tổ). Trả step_id."""
    db = SessionLocal()
    try:
        step = RoutingStep(lenh_sx_id=lenh_id, thu_tu=thu_tu, cong_doan_id=None, to_id=to_id, ten=ten)
        db.add(step)
        db.commit()
        return step.id
    finally:
        db.close()


def test_san_luong_cong_don(client):
    """Lát 2 — ghi sản lượng CỘNG DỒN nhiều đợt → tổng Σ đúng; đơn vị bản ghi mới nhất."""
    _admin(client)  # kích hoạt seed vai SX
    to_id = _mk_to("Tổ SL A")
    lenh_id, step_id = _seed_dang_chay(to_id, "SL")
    _mk_user("tt_sl", "Tổ trưởng SX", to_id)
    h_tt = _login(client, "tt_sl")

    assert client.post(f"/api/lenh-sx/routing/{step_id}/san-luong",
                       json={"so_dat": 1000, "so_hong": 20, "don_vi": "to"}, headers=h_tt).status_code == 200
    assert client.post(f"/api/lenh-sx/routing/{step_id}/san-luong",
                       json={"so_dat": 500, "so_hong": 5, "don_vi": "con"}, headers=h_tt).status_code == 200

    d = client.get(f"/api/lenh-sx/to/{to_id}/inbox", headers=h_tt).json()
    st = next(s for it in d["items"] if it["lenh_id"] == lenh_id
              for s in it["steps"] if s["step_id"] == step_id)
    assert st["san_luong"] == {"so_dat": 1500, "so_hong": 25, "don_vi": "con"}


def test_san_luong_requires_permission(client):
    """Gate record_output: admin KHÔNG có → ghi sản lượng bị chặn 403."""
    h = _admin(client)
    to_id = _mk_to("Tổ SL B")
    _, step_id = _seed_dang_chay(to_id, "SL2")
    r = client.post(f"/api/lenh-sx/routing/{step_id}/san-luong", json={"so_dat": 10}, headers=h)
    assert r.status_code == 403, r.text


def test_ban_giao_hai_con_dau_lech(client):
    """Lát 2 — bàn giao 2 con dấu: tổ giao khai → tổ nhận thấy cho_nhan → xác nhận LỆCH (không chặn) →
    cho_nhan hết + xác nhận lần 2 = 409. Bước giao hiện da_giao Σ."""
    _admin(client)
    to_giao = _mk_to("Tổ Giao")
    to_nhan = _mk_to("Tổ Nhận")
    lenh_id, step1 = _seed_dang_chay(to_giao, "BG")
    step2 = _add_step(lenh_id, 2, to_nhan, "Bế")
    _mk_user("tt_giao", "Tổ trưởng SX", to_giao)
    _mk_user("tt_nhan", "Tổ trưởng SX", to_nhan)
    h_giao = _login(client, "tt_giao")
    h_nhan = _login(client, "tt_nhan")

    rg = client.post(f"/api/lenh-sx/routing/{step1}/ban-giao",
                     json={"so_giao": 1000, "don_vi": "to"}, headers=h_giao)
    assert rg.status_code == 200, rg.text
    bg_id = rg.json()["ban_giao_id"]

    # tổ nhận thấy phiếu chờ nhận trên bước của mình
    dn = client.get(f"/api/lenh-sx/to/{to_nhan}/inbox", headers=h_nhan).json()
    st2 = next(s for it in dn["items"] if it["lenh_id"] == lenh_id
               for s in it["steps"] if s["step_id"] == step2)
    assert st2["cho_nhan"] and st2["cho_nhan"]["ban_giao_id"] == bg_id and st2["cho_nhan"]["so_giao"] == 1000

    # xác nhận nhận LỆCH 990 (không chặn)
    rn = client.post(f"/api/lenh-sx/ban-giao/{bg_id}/nhan",
                     json={"so_nhan": 990, "ly_do_lech": "rơi vãi"}, headers=h_nhan)
    assert rn.status_code == 200, rn.text

    dn2 = client.get(f"/api/lenh-sx/to/{to_nhan}/inbox", headers=h_nhan).json()
    st2b = next(s for it in dn2["items"] if it["lenh_id"] == lenh_id
                for s in it["steps"] if s["step_id"] == step2)
    assert st2b["cho_nhan"] is None   # đã xác nhận → hết chờ

    # xác nhận lần 2 → 409
    r409 = client.post(f"/api/lenh-sx/ban-giao/{bg_id}/nhan", json={"so_nhan": 990}, headers=h_nhan)
    assert r409.status_code == 409, r409.text

    # bước giao hiện đã giao Σ 1000
    dg = client.get(f"/api/lenh-sx/to/{to_giao}/inbox", headers=h_giao).json()
    st1 = next(s for it in dg["items"] if it["lenh_id"] == lenh_id
               for s in it["steps"] if s["step_id"] == step1)
    assert st1["da_giao"] == 1000


def test_ban_giao_requires_permission(client):
    """Gate handover: admin KHÔNG có → bàn giao bị chặn 403."""
    h = _admin(client)
    to_id = _mk_to("Tổ Giao B")
    _, step_id = _seed_dang_chay(to_id, "BG2")
    r = client.post(f"/api/lenh-sx/routing/{step_id}/ban-giao", json={"so_giao": 5}, headers=h)
    assert r.status_code == 403, r.text
