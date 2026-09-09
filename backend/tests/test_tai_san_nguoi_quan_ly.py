"""Người quản lý tài sản = MỘT NHÂN VIÊN của bộ phận đang giữ (chủ chốt 08/09/2026).

"Chọn bộ phận sử dụng rồi thì người quản lý phải lấy nhân viên trong bộ phận đó chứ sao lại
nhập tay." Máy chủ kiểm: người khác bộ phận → lỗi; đổi bộ phận (sửa / điều chuyển) mà không chọn
người mới → bỏ trống. Tên chụp sang `nguoi_quan_ly` để bảng đọc thẳng.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.employee import STATUS_RESIGNED, Employee
from app.models.tai_san import LOAI_TSCD
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.service import TaiSanService, TaiSanValidationError


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    to_in = Department(name="To In", code="PB801")
    to_be = Department(name="To Be", code="PB802")
    db.add_all([to_in, to_be])
    db.commit()
    a = Employee(code="NV801", full_name="Nguyen Van A", department_id=to_in.id)
    b = Employee(code="NV802", full_name="Tran Thi B", department_id=to_be.id)
    c = Employee(code="NV803", full_name="Le Van C (da nghi)", department_id=to_in.id,
                 status=STATUS_RESIGNED)
    db.add_all([a, b, c])
    db.commit()
    return db, TaiSanService(TaiSanRepository(db)), to_in, to_be, a, b


def _komori(svc, **over):
    return svc.ghi_tang(dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120, ngay_su_dung=date(2026, 3, 10),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 3_300_000_000}], **over,
    ))


def test_ghi_tang_gan_nguoi_quan_ly_theo_bo_phan():
    db, svc, to_in, to_be, a, b = _moi_truong()
    t = _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=a.id)
    assert t.nguoi_quan_ly_id == a.id
    assert t.nguoi_quan_ly == "Nguyen Van A"                   # tên chụp từ hồ sơ


def test_nguoi_khac_bo_phan_bi_chan():
    db, svc, to_in, to_be, a, b = _moi_truong()
    with pytest.raises(TaiSanValidationError):
        _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=b.id)


def test_chua_chon_bo_phan_thi_khong_chon_duoc_nguoi():
    db, svc, to_in, to_be, a, b = _moi_truong()
    with pytest.raises(TaiSanValidationError):
        _komori(svc, nguoi_quan_ly_id=a.id)


def test_nhan_vien_khong_ton_tai():
    db, svc, to_in, to_be, a, b = _moi_truong()
    with pytest.raises(TaiSanValidationError):
        _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=999)


def test_sua_doi_bo_phan_khong_chon_nguoi_moi_thi_bo_trong():
    db, svc, to_in, to_be, a, b = _moi_truong()
    t = _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=a.id)
    svc.sua(t.id, {"bo_phan_id": to_be.id})
    db.refresh(t)
    assert t.bo_phan_id == to_be.id
    assert t.nguoi_quan_ly_id is None and t.nguoi_quan_ly is None


def test_sua_doi_bo_phan_kem_nguoi_moi():
    db, svc, to_in, to_be, a, b = _moi_truong()
    t = _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=a.id)
    svc.sua(t.id, {"bo_phan_id": to_be.id, "nguoi_quan_ly_id": b.id})
    db.refresh(t)
    assert (t.nguoi_quan_ly_id, t.nguoi_quan_ly) == (b.id, "Tran Thi B")
    with pytest.raises(TaiSanValidationError):
        svc.sua(t.id, {"nguoi_quan_ly_id": a.id})            # A thuộc Tổ In, tài sản đang ở Tổ Bế


def test_sua_chi_doi_ten_khong_dung_nguoi_quan_ly():
    db, svc, to_in, to_be, a, b = _moi_truong()
    t = _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=a.id)
    svc.sua(t.id, {"ten": "May in Komori (doi ten)"})
    db.refresh(t)
    assert t.nguoi_quan_ly_id == a.id


def test_dieu_chuyen_chon_nguoi_cua_bo_phan_moi():
    db, svc, to_in, to_be, a, b = _moi_truong()
    t = _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=a.id)
    svc.dieu_chuyen(t.id, ngay=date(2026, 9, 1), bo_phan_moi_id=to_be.id, nguoi_quan_ly_id=b.id)
    db.refresh(t)
    assert (t.bo_phan_id, t.nguoi_quan_ly_id, t.nguoi_quan_ly) == (to_be.id, b.id, "Tran Thi B")


def test_dieu_chuyen_khong_chon_nguoi_thi_bo_trong():
    db, svc, to_in, to_be, a, b = _moi_truong()
    t = _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=a.id)
    svc.dieu_chuyen(t.id, ngay=date(2026, 9, 1), bo_phan_moi_id=to_be.id)
    db.refresh(t)
    assert t.nguoi_quan_ly_id is None and t.nguoi_quan_ly is None


def test_dieu_chuyen_nguoi_cua_bo_phan_cu_bi_chan():
    db, svc, to_in, to_be, a, b = _moi_truong()
    t = _komori(svc, bo_phan_id=to_in.id, nguoi_quan_ly_id=a.id)
    with pytest.raises(TaiSanValidationError):
        svc.dieu_chuyen(t.id, ngay=date(2026, 9, 1), bo_phan_moi_id=to_be.id, nguoi_quan_ly_id=a.id)


def test_danh_sach_nhan_vien_bo_phan_chi_nguoi_dang_lam():
    db, svc, to_in, to_be, a, b = _moi_truong()
    assert [e.id for e in svc.nhan_vien_bo_phan(to_in.id)] == [a.id]     # C đã nghỉ thì không
    assert [e.id for e in svc.nhan_vien_bo_phan(to_be.id)] == [b.id]


# --- HTTP ---------------------------------------------------------------------------------


def test_api_chon_nguoi_quan_ly(client, seed_credentials):
    from app.db import SessionLocal
    from app.repositories.rbac_repo import DepartmentRepository

    r = client.post("/api/auth/login", json=seed_credentials)
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    db = SessionLocal()
    try:
        sx = DepartmentRepository(db).get_by_name("Sản xuất")
        kt = DepartmentRepository(db).get_by_name("Kế toán")
        nv = Employee(code="NVTS01", full_name="Pham Van Quan Ly", department_id=sx.id)
        db.add(nv)
        db.commit()
        nv_id, sx_id, kt_id = nv.id, sx.id, kt.id
    finally:
        db.close()

    ds = client.get(f"/api/tai-san/nhan-vien?bo_phan_id={sx_id}", headers=h).json()
    assert any(x["id"] == nv_id and x["full_name"] == "Pham Van Quan Ly" for x in ds)
    assert client.get("/api/tai-san/nhan-vien", headers=h).status_code == 422   # thiếu bộ phận

    ts = client.post("/api/tai-san", headers=h, json={
        "ten": "May in Komori 4 mau", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-03-10", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 3300000000}],
        "bo_phan_id": sx_id, "nguoi_quan_ly_id": nv_id,
    })
    assert ts.status_code == 201, ts.text
    assert ts.json()["nguoi_quan_ly_id"] == nv_id
    assert ts.json()["nguoi_quan_ly"] == "Pham Van Quan Ly"

    # người của bộ phận khác → 422 nói rõ vì sao
    r = client.put(f"/api/tai-san/{ts.json()['id']}", headers=h,
                   json={"bo_phan_id": kt_id, "nguoi_quan_ly_id": nv_id})
    assert r.status_code == 422 and "không thuộc bộ phận" in r.json()["detail"]

    # đổi bộ phận mà không chọn người mới → bỏ trống
    r = client.put(f"/api/tai-san/{ts.json()['id']}", headers=h, json={"bo_phan_id": kt_id})
    assert r.status_code == 200, r.text
    assert r.json()["nguoi_quan_ly_id"] is None and r.json()["nguoi_quan_ly"] is None
