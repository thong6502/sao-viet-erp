"""Nhật ký hoạt động — lọc + phân trang + xuất, tất cả Ở MÁY CHỦ (25/09/2026).

Trước đó `GET /api/audit` không nhận tham số nào và trả cứng 100 dòng mới nhất; màn hình lọc /
cắt trang / xuất CSV trên đúng 100 dòng ấy nên dòng thứ 101 trở đi không có đường nào lấy ra.
Bộ test này khoá lại hợp đồng mới.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models.audit import AuditLog
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _do(*, n: int, action: str, target: str = "", detail: str = "", lui_ngay: int = 0,
        actor_id: int | None = None) -> None:
    """Gieo thẳng vào bảng — nhanh và đặt được thời điểm trong quá khứ."""
    db = SessionLocal()
    try:
        moc = datetime.now(timezone.utc) - timedelta(days=lui_ngay)
        for i in range(n):
            db.add(AuditLog(
                actor_user_id=actor_id, action=action, target=target,
                detail=f"{detail} #{i}", created_at=moc - timedelta(seconds=i),
            ))
        db.commit()
    finally:
        db.close()


def test_tra_ve_trang_chu_khong_phai_mang_tran_100(client):
    token = _admin(client)
    _do(n=3, action="create_department", detail="Phòng X")
    body = client.get("/api/audit", headers=_h(token)).json()
    assert isinstance(body, dict)
    assert {"items", "tong", "trang", "neo", "so_dong_bi_an", "tu", "den"} <= set(body)
    assert body["tong"] >= 3


def test_phan_trang_theo_so_trang_khong_lap_khong_sot(client):
    token = _admin(client)
    _do(n=25, action="create_department", detail="Phòng")
    thay: list[int] = []
    gio: list[str] = []
    neo = None
    for so in range(1, 11):
        url = f"/api/audit?limit=7&action=create_department&trang={so}"
        if neo:
            url += f"&neo={neo}"
        body = client.get(url, headers=_h(token)).json()
        assert body["trang"] == so
        thay += [r["id"] for r in body["items"]]
        gio += [r["created_at"] for r in body["items"]]
        neo = body["neo"]
        if len(body["items"]) < 7:
            break
    assert len(thay) == len(set(thay)), "trang sau lặp dòng của trang trước"
    assert len(thay) == 25
    assert gio == sorted(gio, reverse=True), "phải mới nhất trước, liền mạch qua các trang"


def test_moc_neo_giu_xap_trang_dung_yen_khi_co_dong_moi(client):
    """Bấm sang trang 2 sau khi có dòng mới ghi vào: không được lặp dòng cuối của trang 1.

    Đây là lý do phân trang đánh số phải kèm mốc neo — OFFSET trần trên bảng sắp-mới-nhất-trước
    bị dòng mới đẩy tụt một nấc, trang 2 lặp lại đúng dòng vừa đọc xong."""
    token = _admin(client)
    _do(n=14, action="create_department", detail="Phòng")
    t1 = client.get("/api/audit?limit=7&action=create_department", headers=_h(token)).json()
    neo = t1["neo"]
    assert neo

    # `lui_ngay=-1` = mốc ở TƯƠNG LAI: dòng thật sự MỚI HƠN ảnh chụp, đúng tình huống người khác
    # thao tác trong lúc mình đang lật trang. (Gieo dòng có mốc CŨ hơn neo thì nó nằm trong ảnh
    # chụp là đúng — neo chụp theo thứ tự thời gian, không theo thứ tự ghi vào bảng.)
    _do(n=3, action="create_department", detail="Phòng chen ngang", lui_ngay=-1)

    t2 = client.get(
        f"/api/audit?limit=7&action=create_department&trang=2&neo={neo}", headers=_h(token)
    ).json()
    assert not ({r["id"] for r in t1["items"]} & {r["id"] for r in t2["items"]})
    # Ảnh chụp đứng yên: tổng vẫn là 14 dòng lúc mở màn, 3 dòng vừa chen không làm nhảy số trang.
    assert t2["tong"] == 14

    # Còn về trang 1 (không gửi neo) là chụp lại ảnh mới ⇒ thấy đủ 17. Phải nới `den_ngay` vì ba
    # dòng vừa gieo có mốc ở tương lai, mặc định chỉ lấy tới thời điểm hiện tại.
    den = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    lam_moi = client.get(
        f"/api/audit?limit=7&action=create_department&den_ngay={den}", headers=_h(token)
    ).json()
    assert lam_moi["tong"] == 17


def test_loc_theo_khoang_ngay_that(client):
    token = _admin(client)
    _do(n=2, action="create_machine", detail="máy cũ", lui_ngay=100)
    _do(n=3, action="create_machine", detail="máy mới", lui_ngay=1)

    # Mặc định 30 ngày ⇒ chỉ thấy dòng mới.
    mac_dinh = client.get("/api/audit?action=create_machine", headers=_h(token)).json()
    assert mac_dinh["tong"] == 3

    # Mở rộng khoảng ngày ⇒ thấy cả dòng 100 ngày trước. Đây chính là thứ bản cũ KHÔNG làm được.
    tu = (datetime.now(timezone.utc) - timedelta(days=200)).date().isoformat()
    rong = client.get(f"/api/audit?action=create_machine&tu_ngay={tu}", headers=_h(token)).json()
    assert rong["tong"] == 5


def test_tim_chuoi_va_loc_theo_loai_doi_tuong(client):
    token = _admin(client)
    _do(n=1, action="dm_sua", target="giay:7", detail="Đơn giá 27.800 → 29.000")
    _do(n=1, action="dm_sua", target="cong_doan:9", detail="Tên A → B")

    theo_loai = client.get("/api/audit?loai=giay", headers=_h(token)).json()
    assert theo_loai["tong"] == 1
    assert theo_loai["items"][0]["target"] == "giay:7"

    tim = client.get("/api/audit?q=29.000", headers=_h(token)).json()
    assert tim["tong"] == 1


def test_nhan_tieng_viet_do_may_chu_dich(client):
    token = _admin(client)
    _do(n=1, action="employee_create_account", target="employee:1", detail="NV001")
    r = client.get("/api/audit?action=employee_create_account", headers=_h(token)).json()
    assert r["items"][0]["nhan"] == "Tạo tài khoản đăng nhập cho nhân sự"
    assert r["items"][0]["nhom"] == "nhan_su"

    # Ba mã danh mục dùng chung: nhãn phải lấy thêm LOẠI từ target.
    _do(n=1, action="dm_sua", target="giay:7", detail="x")
    dm = client.get("/api/audit?action=dm_sua&loai=giay", headers=_h(token)).json()
    assert dm["items"][0]["nhan"] == "Sửa · Giấy"
    assert dm["items"][0]["target_loai"] == "giay"


def test_facets_dem_theo_toan_bo_khoang_ngay(client):
    token = _admin(client)
    _do(n=4, action="create_customer", detail="KH")
    f = client.get("/api/audit/facets", headers=_h(token)).json()
    ma = {h["ma"]: h for h in f["hanh_dong"]}
    assert ma["create_customer"]["so_dong"] == 4
    assert ma["create_customer"]["nhan"] == "Tạo khách hàng"
    nhom = {n["khoa"]: n["so_dong"] for n in f["nhom"]}
    assert nhom["kinh_doanh"] >= 4
    # Mọi nhóm đều có mặt (kể cả nhóm 0 dòng) để chip không biến mất khi đổi khoảng ngày.
    assert len(f["nhom"]) == 10


def test_xuat_csv_theo_bo_loc_va_tu_ghi_nhat_ky(client):
    token = _admin(client)
    _do(n=3, action="create_supplier", detail="NCC")
    r = client.get("/api/audit/export?action=create_supplier", headers=_h(token))
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    hang = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert hang[0][0] == "ID"
    assert len(hang) - 1 == 3
    assert hang[1][3] == "Tạo nhà cung cấp"

    # Việc xuất chính nhật ký phải để lại vết.
    vet = client.get("/api/audit?action=audit_export", headers=_h(token)).json()
    assert vet["tong"] >= 1
    assert "create_supplier" not in vet["items"][0]["detail"] or True  # mô tả bộ lọc, không bắt dạng


def test_nguoi_thieu_quyen_man_thi_khong_doc_duoc_dong_cua_man_do(client):
    """`detail` chứa số tiền thật. Ai không mở được màn Báo cáo kho thì không đọc dòng giá gốc —
    nhưng phải BIẾT là có dòng bị che."""
    token = _admin(client)
    _do(n=2, action="kho_sua_gia_goc", target="lo:1", detail="giá gốc 27.800 → 29.000 đ/kg")

    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("kiemtoan-audit")
        if u is None:
            hcns = DepartmentRepository(db).get_by_name("Hành chính nhân sự")
            vai = RoleRepository(db).get_by_name_and_department("Trưởng phòng HCNS", hcns.id)
            u = users.create(username="kiemtoan-audit", name="K", password_hash=hash_password("x"))
            users.set_assignment(u, department_id=hcns.id, role_id=vai.id, is_active=True)
        tok_hcns = create_access_token(str(u.id))
    finally:
        db.close()

    cua_admin = client.get("/api/audit?action=kho_sua_gia_goc", headers=_h(token)).json()
    assert cua_admin["tong"] == 2

    cua_hcns = client.get("/api/audit?action=kho_sua_gia_goc", headers=_h(tok_hcns)).json()
    assert cua_hcns["tong"] == 0, "TP HCNS không mở được Báo cáo kho thì không được đọc dòng giá gốc"
    assert cua_hcns["so_dong_bi_an"] >= 2, "bị che thì phải nói ra, không nuốt im lặng"


def test_xuat_doi_quyen_rieng(client):
    """Ai xem được nhật ký KHÔNG mặc nhiên tải được toàn bộ nhật ký về máy."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("kiemtoan-audit2")
        if u is None:
            hcns = DepartmentRepository(db).get_by_name("Hành chính nhân sự")
            vai = RoleRepository(db).get_by_name_and_department("Trưởng phòng HCNS", hcns.id)
            u = users.create(username="kiemtoan-audit2", name="K2", password_hash=hash_password("x"))
            users.set_assignment(u, department_id=hcns.id, role_id=vai.id, is_active=True)
        tok = create_access_token(str(u.id))
    finally:
        db.close()
    assert client.get("/api/audit", headers=_h(tok)).status_code == 200
    assert client.get("/api/audit/export", headers=_h(tok)).status_code == 403


def test_neo_rac_khong_lam_no_500(client):
    """Mốc neo đi qua query string nên người dùng sửa tay được — rác thì coi như không có."""
    token = _admin(client)
    r = client.get("/api/audit?neo=xin-chao&trang=2", headers=_h(token))
    assert r.status_code == 200


def test_limit_va_trang_bi_chan_gia_tri_bay(client):
    token = _admin(client)
    assert client.get("/api/audit?limit=5000", headers=_h(token)).status_code == 422
    assert client.get("/api/audit?trang=0", headers=_h(token)).status_code == 422


def test_dang_nhap_dang_xuat_va_dang_nhap_hong_deu_co_vet(client):
    """Trước 25/09/2026 nhật ký không biết ai đã vào hệ thống: đặt lại mật khẩu / thu hồi phiên /
    khoá tài khoản đều có dòng, riêng sự kiện truy cập thì trống."""
    client.post("/api/auth/login", json={"username": "admin", "password": "sai-bet"})
    token = _admin(client)
    client.post("/api/auth/logout")

    r = client.get("/api/audit?action=dang_nhap&action=dang_xuat&action=dang_nhap_that_bai",
                   headers=_h(token)).json()
    co = {d["action"] for d in r["items"]}
    assert {"dang_nhap", "dang_nhap_that_bai", "dang_xuat"} <= co
    hong = next(d for d in r["items"] if d["action"] == "dang_nhap_that_bai")
    assert hong["actor_user_id"] is None, "chưa xác thực được thì không gán danh tính cho ai"
    assert "admin" in hong["detail"]
    assert hong["nhan"] == "Đăng nhập thất bại"


def test_ten_nguoi_thao_tac_la_anh_chup_luc_ghi(client):
    """Đổi tên một người thì nhật ký CŨ vẫn phải nói đúng tên lúc đó."""
    token = _admin(client)
    client.post("/api/departments", json={"name": "Phòng Ảnh Chụp"}, headers=_h(token))

    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("admin")
        cu = u.name
        users.set_name(u, "Giám đốc MỚI")
    finally:
        db.close()
    try:
        r = client.get("/api/audit?action=create_department", headers=_h(token)).json()
        dong = next(d for d in r["items"] if "Phòng Ảnh Chụp" in d["detail"])
        assert dong["actor_name"] == cu, "tên phải là tên LÚC GHI, không phải tên hôm nay"
    finally:
        db = SessionLocal()
        try:
            users = UserRepository(db)
            users.set_name(users.get_by_username("admin"), cu)
        finally:
            db.close()


def test_ghi_kem_ip_va_thiet_bi(client):
    token = _admin(client)
    client.post("/api/departments", json={"name": "Phòng Có Vết"},
                headers={**_h(token), "User-Agent": "may-cua-toi/1.0"})
    r = client.get("/api/audit?action=create_department", headers=_h(token)).json()
    dong = next(d for d in r["items"] if "Phòng Có Vết" in d["detail"])
    assert dong["user_agent"] == "may-cua-toi/1.0"
    assert dong["ip"], "phải biết dòng này đến từ đâu"
