"""Tệp đính kèm của LỆNH hiện xuống Bàn tổ sau khi phát hành.

Kế hoạch SX đính kèm maket/bản vẽ vào lệnh (`/api/lsx/{id}/dinh-kem`, gác module `san_xuat`). Tổ
dưới xưởng KHÔNG có module đó — họ vào bằng quyền theo tổ (mg 0302) — nên đọc qua công việc:
`tep_lenh.tep_cua_cong_viec`, cùng cổng với drawer (`chi_tiet_cong_viec`):
  - tổ ngoài phạm vi Xem → chặn; mức Của tôi thì chỉ việc đang giao cho mình;
  - chỉ gói ĐANG phát hành — thu hồi rồi thì tổ không còn thấy việc, cũng thôi thấy tệp;
  - công việc bài ghép trả tệp của MỌI lệnh thành viên, gom theo lệnh.
Chỉ đọc: thêm/xoá tệp vẫn ở Kế hoạch SX.
"""
from __future__ import annotations

import pytest

from app.models.lsx import Lsx, LsxDinhKem
from app.models.san_xuat import SanXuatCongViec
from app.services.san_xuat import release_update, tep_lenh
from tests.test_san_xuat_board import (
    _authz,
    _ban_phang,
    _emp_id,
    _giao,
    _phat_hanh_vao_to,
    _tho_co_tai_khoan,
    _to_moi,
)
from tests.test_san_xuat_lenh_phan_trang import to_co_bai_ghep_2_lenh  # noqa: F401
from tests.test_xep_lich_service import (  # noqa: F401
    admin,
    bg_svc,
    customer,
    db,
    lsx_svc,
    orders,
)
from tests.test_san_xuat_board_api import _admin_h


def _dinh_kem(db, lsx_id: int, ten: str, admin) -> LsxDinhKem:
    """Dòng tệp như Kế hoạch SX vừa tải lên — ở đây chỉ soi phần ĐỌC nên khỏi ghi object vào kho."""
    row = LsxDinhKem(
        lsx_id=lsx_id, ten_tep=ten, file_url=f"/api/files/san-xuat/lsx/{lsx_id}/ab12cd34_{ten}",
        content_type="application/pdf", kich_thuoc=1234, nguoi_tai_id=admin.id,
    )
    db.add(row)
    db.commit()
    return row


def _viec_cua_lenh(db, to_id: int, lsx_id: int) -> SanXuatCongViec:
    return (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.department_id == to_id, SanXuatCongViec.lsx_id == lsx_id)
        .first()
    )


def test_to_thay_tep_cua_lenh_da_phat_hanh(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    a, b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    _dinh_kem(db, a.id, "maket.pdf", admin)
    _dinh_kem(db, a.id, "ban-ve.pdf", admin)
    _dinh_kem(db, b.id, "cua-lenh-khac.pdf", admin)

    cv = _viec_cua_lenh(db, to.id, a.id)
    nhom = tep_lenh.tep_cua_cong_viec(db, admin, cong_viec_id=cv.id)

    assert [n["lsx_id"] for n in nhom] == [a.id]
    assert nhom[0]["lsx_ma"] == a.ma and nhom[0]["lsx_ten"] == a.ten
    assert sorted(t["ten_tep"] for t in nhom[0]["items"]) == ["ban-ve.pdf", "maket.pdf"]
    t = nhom[0]["items"][0]
    assert set(t) == {
        "id", "ten_tep", "file_url", "content_type", "kich_thuoc", "nguoi_tai_ten", "tai_luc",
    }
    assert t["nguoi_tai_ten"] == admin.name


def test_lenh_chua_co_tep_van_tra_nhom_rong(db, orders, lsx_svc, admin, customer):
    """Tổ cần biết "lệnh này không có tệp" chứ không phải "không tải được"."""
    to = _to_moi(db)
    a, _b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv = _viec_cua_lenh(db, to.id, a.id)
    nhom = tep_lenh.tep_cua_cong_viec(db, admin, cong_viec_id=cv.id)
    assert nhom == [{"lsx_id": a.id, "lsx_ma": a.ma, "lsx_ten": a.ten, "items": []}]


def test_ngoai_pham_vi_to_bi_chan(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    khac = _to_moi(db, ten="Tổ Khác", ma="TO-KHAC", quyen_admin=False)
    a, _b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    _dinh_kem(db, a.id, "maket.pdf", admin)
    nguoi_to_khac = _tho_co_tai_khoan(db, khac, username="tho_to_khac", ma_nv="NV-KHAC",
                                      pham_vi="all")

    cv = _viec_cua_lenh(db, to.id, a.id)
    with pytest.raises(PermissionError):
        tep_lenh.tep_cua_cong_viec(db, nguoi_to_khac, cong_viec_id=cv.id)


def test_tho_chi_xem_tep_tren_viec_duoc_giao(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    tho = _tho_co_tai_khoan(db, to, username="tho_tep", ma_nv="NV-TEP")
    ca_ban = _ban_phang(db, admin, _authz(db), team_id=to.id)["cong_viec"]
    _giao(db, ca_ban[0]["id"], _emp_id(db, tho.id))

    assert tep_lenh.tep_cua_cong_viec(db, tho, cong_viec_id=ca_ban[0]["id"])
    with pytest.raises(PermissionError):
        tep_lenh.tep_cua_cong_viec(db, tho, cong_viec_id=ca_ban[1]["id"])


def test_thu_hoi_goi_thi_to_thoi_thay_tep(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    a, _b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    _dinh_kem(db, a.id, "maket.pdf", admin)
    cv = _viec_cua_lenh(db, to.id, a.id)

    release_update.thu_hoi_goi(db, nguon="lsx", id=a.id, actor=admin)
    db.commit()
    with pytest.raises(ValueError):
        tep_lenh.tep_cua_cong_viec(db, admin, cong_viec_id=cv.id)


def test_cong_viec_khong_ton_tai(db, admin):
    with pytest.raises(ValueError):
        tep_lenh.tep_cua_cong_viec(db, admin, cong_viec_id=987654)


def test_bai_ghep_tra_tep_moi_lenh_thanh_vien(db, admin, to_co_bai_ghep_2_lenh):  # noqa: F811
    to_id = to_co_bai_ghep_2_lenh
    cv = (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.department_id == to_id, SanXuatCongViec.bai_ghep_id.isnot(None))
        .first()
    )
    lenh = db.query(Lsx).order_by(Lsx.ma).all()
    for i, l in enumerate(lenh):
        _dinh_kem(db, l.id, f"maket-{i}.pdf", admin)

    nhom = tep_lenh.tep_cua_cong_viec(db, admin, cong_viec_id=cv.id)
    assert [n["lsx_ma"] for n in nhom] == [l.ma for l in lenh]
    assert [[t["ten_tep"] for t in n["items"]] for n in nhom] == [
        [f"maket-{i}.pdf"] for i in range(len(lenh))
    ]


def test_api_can_dang_nhap(client):
    assert client.get("/api/san-xuat/work-items/1/tep-lenh").status_code == 401


def test_api_cong_viec_khong_ton_tai_404(client):
    from tests.test_san_xuat_board_api import _to_la_sx

    _to_la_sx()
    r = client.get("/api/san-xuat/work-items/987654/tep-lenh", headers=_admin_h(client))
    assert r.status_code == 404


def test_api_tai_khoan_chi_co_quyen_to_doc_duoc_tep(client, db, orders, lsx_svc, admin, customer):
    """Đúng đối tượng của yêu cầu: tài khoản CHỈ có dòng quyền của tổ, không có module `san_xuat`.
    Đường Kế hoạch SX đóng với họ (403), đường qua công việc mở — và tải tệp qua `/api/files` được."""
    from app.models.user import User
    from app.security import hash_password
    from tests.quyen_to_fixtures import cap_quyen_to

    to = _to_moi(db)
    a, _b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    _dinh_kem(db, a.id, "maket.pdf", admin)
    cv = _viec_cua_lenh(db, to.id, a.id)

    u = User(username="to_chi_xem", name="Tổ chỉ xem", password_hash=hash_password("matkhau-123"),
             department_id=to.id)
    db.add(u)
    db.flush()
    cap_quyen_to(db, u, to, viec=())
    db.commit()

    tok = client.post("/api/auth/login", json={"username": "to_chi_xem", "password": "matkhau-123"})
    assert tok.status_code == 200, tok.text
    h = {"Authorization": f"Bearer {tok.json()['access_token']}"}

    assert client.get(f"/api/lsx/{a.id}/dinh-kem", headers=h).status_code == 403
    r = client.get(f"/api/san-xuat/work-items/{cv.id}/tep-lenh", headers=h)
    assert r.status_code == 200, r.text
    nhom = r.json()["nhom"]
    assert [n["lsx_ma"] for n in nhom] == [a.ma]
    assert [t["ten_tep"] for t in nhom[0]["items"]] == ["maket.pdf"]

    from app.storage import get_storage, key_from_url

    url = nhom[0]["items"][0]["file_url"]
    get_storage().save(key_from_url(url), b"%PDF-maket")
    tai = client.get(url)  # cookie tệp do lần đăng nhập ở trên đặt
    assert tai.status_code == 200, tai.text
    assert tai.content == b"%PDF-maket"


def test_moi_to_co_cong_doan_cua_lenh_deu_thay_cung_bo_tep(db, orders, lsx_svc, admin, customer):
    """Tệp theo LỆNH: chuỗi công đoạn của lệnh rải qua nhiều tổ thì tổ nào nhận công đoạn cũng thấy
    đúng một bộ tệp — mỗi người chỉ có quyền ở tổ mình."""
    from app.models.lsx import LsxCongDoan
    from app.services.san_xuat import release
    from tests.test_xep_lich_service import _hai_lsx_san_sang

    to_in = _to_moi(db, ten="Tổ In Tệp", ma="TO-IN-TEP", quyen_admin=False)
    to_be = _to_moi(db, ten="Tổ Bế Tệp", ma="TO-BE-TEP", quyen_admin=False)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id.in_([a.id, b.id])).update(
        {LsxCongDoan.department_id: to_in.id}, synchronize_session=False
    )
    cuoi = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == a.id).order_by(
        LsxCongDoan.thu_tu.desc(), LsxCongDoan.id.desc()
    ).first()
    db.add(LsxCongDoan(lsx_id=a.id, thu_tu=(cuoi.thu_tu or 0) + 1, ten="Bế", nhom="finishing",
                       department_id=to_be.id))
    db.commit()
    release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()
    _dinh_kem(db, a.id, "maket.pdf", admin)
    _dinh_kem(db, a.id, "khuon-be.pdf", admin)

    nguoi_in = _tho_co_tai_khoan(db, to_in, username="nguoi_to_in", ma_nv="NV-IN", pham_vi="all")
    nguoi_be = _tho_co_tai_khoan(db, to_be, username="nguoi_to_be", ma_nv="NV-BE", pham_vi="all")
    viec_in = _viec_cua_lenh(db, to_in.id, a.id)
    viec_be = _viec_cua_lenh(db, to_be.id, a.id)
    assert viec_in and viec_be and viec_in.id != viec_be.id

    def ten(nhom):
        return [(n["lsx_ma"], sorted(t["ten_tep"] for t in n["items"])) for n in nhom]

    mong = [(a.ma, ["khuon-be.pdf", "maket.pdf"])]
    assert ten(tep_lenh.tep_cua_cong_viec(db, nguoi_in, cong_viec_id=viec_in.id)) == mong
    assert ten(tep_lenh.tep_cua_cong_viec(db, nguoi_be, cong_viec_id=viec_be.id)) == mong
