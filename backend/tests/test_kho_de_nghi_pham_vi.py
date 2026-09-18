"""Phạm vi xem YÊU CẦU KHO (16/09/2026) — hai luật, kiểm bằng HTTP thật.

1. Yêu cầu do CHÍNH MÌNH tạo luôn hiện, bất kể phạm vi. Bàn tổ gắn bộ phận của yêu cầu là TỔ của
   công đoạn (`vat_tu_de_nghi.tao`), không phải phòng người bấm — người ngồi phòng "Sản xuất"
   gửi cho Tổ in từng không thấy yêu cầu của chính mình ở module Kho.
2. Phạm vi `department` = phòng mình + TOÀN BỘ cây con (`org_scope.dept_subtree_ids`), đúng nghĩa
   các module khác và quyền theo tổ đang dùng — quản lý sản xuất thấy yêu cầu của các tổ.

Danh sách, badge đếm theo trạng thái và mở chi tiết phải cùng một luật, không thì badge nói một
đằng, danh sách một nẻo.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.role import SCOPE_DEPARTMENT, SCOPE_OWN
from app.models.stock_request import StockRequest
from app.repositories.rbac_repo import DepartmentRepository
from tests.test_kho_de_nghi import _admin, _login, _mk_kho, _mk_material, _mk_user

_YEU_CAU = dict(can_read=True, can_request=True)


def _phong(name: str, cha: str | None = None) -> int:
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        d = depts.get_by_name(name)
        if d is None:
            parent_id = depts.get_by_name(cha).id if cha else None
            d = depts.create(name=name, parent_id=parent_id)
        return d.id
    finally:
        db.close()


def _tao(client, username: str, *, kho_id: int, mat, bo_phan_id: int | None = None) -> int:
    r = client.post("/api/kho/de-nghi", headers=_login(client, username), json={
        "loai": "XUAT", "kho_id": kho_id,
        "lines": [{"hang_loai": mat[0], "hang_id": mat[1], "dvt": "to", "sl_de_nghi": 3}],
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    if bo_phan_id is not None:
        # Y như Bàn tổ: bộ phận của yêu cầu là tổ của công đoạn, không phải phòng người bấm.
        db = SessionLocal()
        try:
            db.get(StockRequest, rid).bo_phan_id = bo_phan_id
            db.commit()
        finally:
            db.close()
    return rid


def _thay(client, username: str) -> tuple[set[int], int]:
    h = _login(client, username)
    items = client.get("/api/kho/de-nghi", headers=h).json()["items"]
    dem = client.get("/api/kho/de-nghi/counts-by-status", headers=h).json()
    return {x["id"] for x in items}, sum(dem.values())


def _dung_cay(client):
    kho_id = _mk_kho(client, _admin(client))
    mat = _mk_material("GY-PV-1")
    _phong("SX PV")
    _phong("Tổ in PV", cha="SX PV")
    _phong("Tổ bế PV", cha="SX PV")
    _phong("Kinh doanh PV")
    return kho_id, mat


def test_yeu_cau_cua_minh_luon_hien_du_bo_phan_nam_ngoai_pham_vi(client):
    kho_id, mat = _dung_cay(client)
    to_be = _phong("Tổ bế PV")
    _mk_user("pv_tt_in", "Tổ in PV", dict(_YEU_CAU, scope=SCOPE_DEPARTMENT))
    rid = _tao(client, "pv_tt_in", kho_id=kho_id, mat=mat, bo_phan_id=to_be)

    ids, dem = _thay(client, "pv_tt_in")
    assert rid in ids
    assert dem == 1
    h = _login(client, "pv_tt_in")
    assert client.get(f"/api/kho/de-nghi/{rid}", headers=h).status_code == 200


def test_pham_vi_phong_ban_thay_yeu_cau_cua_to_con(client):
    kho_id, mat = _dung_cay(client)
    _mk_user("pv_tho_in", "Tổ in PV", dict(_YEU_CAU, scope=SCOPE_OWN))
    _mk_user("pv_qlsx", "SX PV", dict(_YEU_CAU, scope=SCOPE_DEPARTMENT))
    rid = _tao(client, "pv_tho_in", kho_id=kho_id, mat=mat)

    ids, dem = _thay(client, "pv_qlsx")
    assert rid in ids
    assert dem == 1
    h = _login(client, "pv_qlsx")
    assert client.get(f"/api/kho/de-nghi/{rid}", headers=h).status_code == 200


def test_pham_vi_phong_ban_khong_thay_nhanh_khac(client):
    kho_id, mat = _dung_cay(client)
    _mk_user("pv_tho_in2", "Tổ in PV", dict(_YEU_CAU, scope=SCOPE_OWN))
    _mk_user("pv_kd", "Kinh doanh PV", dict(_YEU_CAU, scope=SCOPE_DEPARTMENT))
    _mk_user("pv_tt_be", "Tổ bế PV", dict(_YEU_CAU, scope=SCOPE_DEPARTMENT))
    rid = _tao(client, "pv_tho_in2", kho_id=kho_id, mat=mat)

    for ai in ("pv_kd", "pv_tt_be"):
        ids, dem = _thay(client, ai)
        assert rid not in ids
        assert dem == 0
        assert client.get(f"/api/kho/de-nghi/{rid}", headers=_login(client, ai)).status_code == 404


def test_pham_vi_cua_toi_van_chi_thay_cua_minh(client):
    kho_id, mat = _dung_cay(client)
    _mk_user("pv_a", "Tổ in PV", dict(_YEU_CAU, scope=SCOPE_OWN))
    _mk_user("pv_b", "Tổ in PV", dict(_YEU_CAU, scope=SCOPE_OWN))
    rid_a = _tao(client, "pv_a", kho_id=kho_id, mat=mat)
    rid_b = _tao(client, "pv_b", kho_id=kho_id, mat=mat)

    ids, dem = _thay(client, "pv_a")
    assert ids == {rid_a}
    assert dem == 1
    assert client.get(f"/api/kho/de-nghi/{rid_b}", headers=_login(client, "pv_a")).status_code == 404


def test_bao_viec_kho_moi_cho_nguoi_xu_ly_o_phong_cha(client):
    """Tín hiệu "việc kho mới" phải tới đúng những người xử lý kho THẤY yêu cầu trong danh sách —
    người phạm vi `department` ở phòng cha của tổ cũng thấy nên cũng phải nhận (badge nhảy ngay)."""
    from app.repositories.rbac_repo import RoleRepository

    _dung_cay(client)
    xu_ly = dict(can_read=True, can_view_stock=True, scope=SCOPE_DEPARTMENT)
    cha = _mk_user("pv_kho_cha", "SX PV", xu_ly)
    tai_to = _mk_user("pv_kho_to", "Tổ in PV", xu_ly)
    nhanh_khac = _mk_user("pv_kho_kd", "Kinh doanh PV", xu_ly)
    to_con_khac = _mk_user("pv_kho_be", "Tổ bế PV", xu_ly)

    db = SessionLocal()
    try:
        nhan = set(RoleRepository(db).kho_notify_user_ids(
            bo_phan_id=_phong("Tổ in PV"), creator_id=None))
    finally:
        db.close()
    assert {cha, tai_to} <= nhan
    assert not {nhanh_khac, to_con_khac} & nhan
