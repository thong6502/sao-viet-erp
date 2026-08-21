"""Phạm vi ở màn Yêu cầu mua hàng phải LỌC THẬT (vá 11/08/2026).

⚠️ LỖ HỔNG ĐÃ ĐO ĐƯỢC — chủ chốt phát hiện khi test tay, dựng lại bằng số:

    ca đo                                   own    department   all
    vai chỉ có `yeu_cau_mua_hang`             1          1        2
    vai có THÊM khoá `thu_mua`                2          2        2      ← rò

Hai gốc khác nhau, vá cả hai:

1. `_sees_all_department_requests` mở cửa cho bất kỳ vai nào CÓ dòng quyền `thu_mua`, **không xét
   phạm vi** (`scope_for(...) is not None`). Ai được cấp màn Mua hàng — dù `own` — là ô chọn phạm
   vi ở màn này thành vô nghĩa. Người test đang làm Thu mua nên chắc chắn dính.
2. Phạm vi `own` không có nhánh lọc riêng, rơi xuống dùng chung nhánh lọc theo PHÒNG ⇒ thấy luôn
   yêu cầu của đồng nghiệp cùng phòng.

Để so sánh: màn **Mua hàng** (`/api/purchase-requests`) lọc đúng từ đầu — đo được 0/1/2. Nên đây
là lỗi riêng của màn YCMH, không phải bệnh chung của cơ chế phạm vi.
"""

from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

from .test_purchases_api import (  # noqa: F401  (auth_headers/token là fixture, phải import)
    _create_department_request,
    _create_purchase_request,
    _supplier,
    auth_headers,
    token,
)


def _vai(ten: str, phong: str, khoa: str, pham_vi: str, them: tuple = (), **co) -> dict:
    """Tài khoản có ĐÚNG một khoá chính (kèm vài khoá phụ phạm vi `all` nếu cần)."""
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name(phong)
        roles, users = RoleRepository(db), UserRepository(db)
        r = roles.create(name=f"Vai {ten}", department_id=dept.id)
        roles.set_permission(role_id=r.id, module_key=khoa, scope=pham_vi, can_read=True, **co)
        for k in them:
            roles.set_permission(role_id=r.id, module_key=k, scope="all",
                                 can_read=True, can_create=True, can_update=True)
        u = users.create(username=ten, name=ten, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=r.id, is_active=True)
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()


def _dung_hai_yeu_cau_hai_phong(client) -> None:
    """Hai người ở HAI phòng, mỗi người gửi một yêu cầu."""
    a = _vai("pv-ycmh-sx", "Sản xuất", "yeu_cau_mua_hang", "all",
             can_create=True, can_update=True)
    b = _vai("pv-ycmh-kd", "Kinh doanh", "yeu_cau_mua_hang", "all",
             can_create=True, can_update=True)
    _create_department_request(client, a)
    _create_department_request(client, b)


def _dem(client, headers) -> tuple[int, list[str]]:
    j = client.get("/api/department-purchase-requests", headers=headers).json()
    return j["total"], sorted({x.get("requesting_department_name") for x in j["items"]})


def test_pham_vi_ycmh_loc_that_theo_tung_muc(client, auth_headers):
    _dung_hai_yeu_cau_hai_phong(client)
    assert _dem(client, auth_headers)[0] == 2, "admin phải thấy cả hai yêu cầu"

    # `own` = ĐÚNG của mình. Người xem chưa gửi yêu cầu nào ⇒ 0 — dù cùng phòng với một người gửi.
    so, _ = _dem(client, _vai("pv-xem-own", "Sản xuất", "yeu_cau_mua_hang", "own"))
    assert so == 0, f"phạm vi `own` thấy {so} dòng — đang lọc theo PHÒNG chứ không theo người gửi"

    so, phong = _dem(client, _vai("pv-xem-dept", "Sản xuất", "yeu_cau_mua_hang", "department"))
    assert (so, phong) == (1, ["Sản xuất"]), f"phạm vi `department` sai: {so} dòng · {phong}"

    so, phong = _dem(client, _vai("pv-xem-all", "Sản xuất", "yeu_cau_mua_hang", "all"))
    assert so == 2 and phong == ["Kinh doanh", "Sản xuất"]


def test_co_them_khoa_thu_mua_khong_pha_pham_vi_cua_man_nay(client, auth_headers):
    """Đây là ca chủ chốt báo: cấp thêm màn Mua hàng là ô phạm vi ở màn này thành vô nghĩa.

    Ô của MÀN NÀO thì màn đó nghe — không khoá nào được đè lên."""
    _dung_hai_yeu_cau_hai_phong(client)

    for pham_vi, mong_doi in (("own", 0), ("department", 1)):
        chi_ycmh = _vai(f"pv2-chi-{pham_vi}", "Sản xuất", "yeu_cau_mua_hang", pham_vi)
        them_tm = _vai(f"pv2-them-{pham_vi}", "Sản xuất", "yeu_cau_mua_hang", pham_vi,
                       them=("thu_mua",))

        so1, _ = _dem(client, chi_ycmh)
        so2, phong2 = _dem(client, them_tm)
        assert so1 == mong_doi, f"`{pham_vi}` (chỉ YCMH) thấy {so1} dòng, cần {mong_doi}"
        assert so2 == mong_doi, (
            f"`{pham_vi}` + khoá `thu_mua` thấy {so2} dòng ({phong2}) — khoá khác vẫn đè lên "
            f"phạm vi của chính màn này"
        )


def test_man_mua_hang_van_loc_dung_nhu_cu(client, auth_headers):
    """Đối chứng: màn Mua hàng KHÔNG dính lỗi trên — giữ test để đừng vá nhầm sang đây."""
    ncc = _supplier(client, auth_headers, name="NCC Pham Vi PMH")
    la = _vai("pv-pmh-sx", "Sản xuất", "thu_mua", "all",
              can_create=True, can_update=True, can_request=True,
              them=("nha_cung_cap", "yeu_cau_mua_hang", "dm_giay_vat_tu"))
    lb = _vai("pv-pmh-kd", "Kinh doanh", "thu_mua", "all",
              can_create=True, can_update=True, can_request=True,
              them=("nha_cung_cap", "yeu_cau_mua_hang", "dm_giay_vat_tu"))
    _create_purchase_request(client, la, ncc["id"])
    _create_purchase_request(client, lb, ncc["id"])

    def dem(headers) -> int:
        return client.get("/api/purchase-requests", headers=headers).json()["total"]

    assert dem(auth_headers) == 2
    assert dem(_vai("pv-pmh-own", "Sản xuất", "thu_mua", "own")) == 0
    assert dem(_vai("pv-pmh-dept", "Sản xuất", "thu_mua", "department")) == 1
    assert dem(_vai("pv-pmh-all", "Sản xuất", "thu_mua", "all")) == 2
