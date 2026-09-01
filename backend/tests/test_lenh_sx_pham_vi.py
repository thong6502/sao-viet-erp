"""Phạm vi hai màn chỉ-đọc bám `orders.sale_user_id` — KHÁC `routers/lsx.py` (bám
`lsx.nguoi_phu_trach_id`). Ba mức: own · department (cả cây con) · all. Lệnh của đơn KHÔNG
có sale phụ trách chỉ hiện với `all`. Lệnh CHƯA phát hành không bao giờ hiện."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.department import Department
from app.models.lsx import TT_DA_PHAT_HANH, TT_SAN_SANG, Lsx
from app.models.order import Order, OrderLine
from app.models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from app.models.user import User
from app.services.lenh_sx import pham_vi

# `db`/`admin` tái dùng nguyên bản từ bàn xếp lịch (kéo theo seed_all) — khỏi tự seed lại,
# xem tests/test_san_xuat_thuc_thi.py:43-51 cho cách import tương tự.
from tests.test_san_xuat_board import admin, db  # noqa: F401

MODULE = "lenh_san_xuat"


class _Authz:
    def __init__(self, scope: str) -> None:
        self._scope = scope

    def scope_for(self, user, module_key: str):  # noqa: ARG002
        return self._scope


# --- Dàn cảnh: cây phòng ban + user Sale ---------------------------------------------------
@pytest.fixture
def _phong_kd(db) -> tuple[Department, Department]:
    """Phòng KD cha + 1 team con — cây phòng ban dùng để kiểm scope `department` thấy CẢ CÂY
    CON, không chỉ đúng một phòng."""
    cha = Department(name="Phòng KD (test phạm vi)", code="PKD-PV")
    db.add(cha)
    db.flush()
    con = Department(name="Team KD A (test phạm vi)", code="TKDA-PV", parent_id=cha.id)
    db.add(con)
    db.flush()
    return cha, con


@pytest.fixture
def _phong_khac(db) -> Department:
    """Phòng KHÔNG nằm trong cây `_phong_kd` — dùng để chứng minh scope `department` không
    tràn sang nhánh khác."""
    d = Department(name="Phòng khác (test phạm vi)", code="PKHAC-PV")
    db.add(d)
    db.flush()
    return d


@pytest.fixture
def tp_kinh_doanh(db, _phong_kd) -> User:
    """Trưởng phòng KD — đứng ở phòng CHA, scope `department` của người này phải thấy cả
    team con bên dưới."""
    cha, _con = _phong_kd
    u = User(username="tpkd_pv", name="Trưởng phòng KD (test PV)", password_hash="x",
             department_id=cha.id)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def sale_a(db, _phong_kd) -> User:
    """Sale nằm ở TEAM CON của `tp_kinh_doanh` — phải lọt vào phạm vi `department` của TP."""
    _cha, con = _phong_kd
    u = User(username="sale_a_pv", name="Sale A (test PV)", password_hash="x",
             department_id=con.id)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def sale_b(db) -> User:
    """Sale KHÁC, không thuộc cây `_phong_kd` — dùng làm đối chứng cho scope `own`."""
    u = User(username="sale_b_pv", name="Sale B (test PV)", password_hash="x")
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def sale_phong_khac(db, _phong_khac) -> User:
    """Sale thuộc phòng KHÔNG liên quan — scope `department` của `tp_kinh_doanh` không được
    thấy người này."""
    u = User(username="sale_phongkhac_pv", name="Sale phòng khác (test PV)", password_hash="x",
             department_id=_phong_khac.id)
    db.add(u)
    db.commit()
    return u


# --- Dàn cảnh: đơn + lệnh sản xuất ----------------------------------------------------------
def _don_va_dong(db, order_no: str, sale_user_id: int | None) -> tuple[Order, OrderLine]:
    o = Order(order_no=order_no, sale_user_id=sale_user_id)
    o.lines.append(OrderLine(description="Dòng test phạm vi", qty=1))
    db.add(o)
    db.flush()
    return o, o.lines[0]


@pytest.fixture
def lenh_cua(db):
    """Factory: 1 lệnh ĐÃ PHÁT HÀNH của đơn do `sale` phụ trách bán. Gọi lại với cùng một
    `sale` trong một test trả về ĐÚNG lệnh cũ (khỏi đẻ trùng đơn/mã)."""
    da_tao: dict[int, int] = {}

    def _tao(sale: User) -> int:
        if sale.id in da_tao:
            return da_tao[sale.id]
        o, line = _don_va_dong(db, f"DH-PV-{sale.id}", sale.id)
        lsx = Lsx(
            ma=f"LSX-PV-{sale.id}", order_id=o.id, order_line_id=line.id,
            trang_thai=TT_DA_PHAT_HANH,
        )
        db.add(lsx)
        db.commit()
        da_tao[sale.id] = lsx.id
        return lsx.id

    return _tao


@pytest.fixture
def lenh_nhap(db) -> int:
    """Lệnh CHƯA phát hành (`san_sang` — đủ điều kiện xếp lịch nhưng chưa thả xuống xưởng).
    Hai màn chỉ-đọc chỉ nói về việc đã phát hành nên trạng thái này không bao giờ được hiện,
    bất kể phạm vi rộng hẹp thế nào."""
    o, line = _don_va_dong(db, "DH-PV-NHAP", None)
    lsx = Lsx(ma="LSX-PV-NHAP", order_id=o.id, order_line_id=line.id, trang_thai=TT_SAN_SANG)
    db.add(lsx)
    db.commit()
    return lsx.id


@pytest.fixture
def lenh_khong_sale(db) -> int:
    """Lệnh ĐÃ PHÁT HÀNH của một đơn KHÔNG có người bán (`sale_user_id IS NULL`) — chủ ý
    không gán bừa cho ai, nên chỉ scope `all` mới thấy."""
    o, line = _don_va_dong(db, "DH-PV-KHONG-SALE", None)
    lsx = Lsx(
        ma="LSX-PV-KHONG-SALE", order_id=o.id, order_line_id=line.id,
        trang_thai=TT_DA_PHAT_HANH,
    )
    db.add(lsx)
    db.commit()
    return lsx.id


# --- Tests -----------------------------------------------------------------------------------
def test_own_chi_thay_lenh_cua_don_minh_phu_trach(db, sale_a, sale_b, lenh_cua):
    ids = pham_vi.sale_ids_theo_pham_vi(db, sale_a, _Authz(SCOPE_OWN), MODULE)
    assert ids == {sale_a.id}
    # Tạo dữ liệu TRƯỚC khi truy vấn — thứ tự ngược (truy vấn rồi mới tạo) sẽ luôn ra tập rỗng
    # bất kể cài đặt đúng hay sai, vì `db.execute` chạy ngay tại chỗ gọi, không trễ tới lúc assert.
    id_cua_a = lenh_cua(sale_a)
    id_cua_b = lenh_cua(sale_b)
    stmt = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), ids)
    thay = {r.id for r in db.execute(stmt).scalars()}
    assert id_cua_a in thay
    assert id_cua_b not in thay


def test_department_thay_ca_cay_con(db, tp_kinh_doanh, sale_a, sale_phong_khac):
    ids = pham_vi.sale_ids_theo_pham_vi(db, tp_kinh_doanh, _Authz(SCOPE_DEPARTMENT), MODULE)
    assert sale_a.id in ids
    assert sale_phong_khac.id not in ids


def test_all_tra_none(db, admin):
    assert pham_vi.sale_ids_theo_pham_vi(db, admin, _Authz(SCOPE_ALL), MODULE) is None


def test_thieu_khai_scope_ve_own(db, sale_a):
    """`scope_for` không trả gì (thiếu khai ở role_permissions) → lùi về hẹp nhất (`own`),
    KHÔNG phải rỗng (khoá hết) và KHÔNG phải `None` (`None` nghĩa là "thấy tất cả" — ngược hẳn
    chủ ý "mở nhầm tệ hơn khoá nhầm").

    Nói rõ giới hạn của bài này: với cấu trúc if/elif hiện tại, `or SCOPE_OWN` là chữ THỪA —
    mọi giá trị `scope` không khớp `ALL`/`DEPARTMENT` đều rơi xuống `return {user.id}` dù có
    nó hay không, nên xoá riêng token đó test vẫn xanh. Cái bài này thật sự canh là RỦI RO
    THẬT: ai tái cấu trúc nhánh rẽ để "thiếu khai" hoá thành `ALL`/`DEPARTMENT` sẽ đỏ ngay."""
    ids = pham_vi.sale_ids_theo_pham_vi(db, sale_a, _Authz(None), MODULE)
    assert ids == {sale_a.id}


def test_scope_rong_cung_ve_own(db, sale_a):
    """Chuỗi rỗng cũng là một dạng "thiếu khai" (falsy) — cùng nhánh `or SCOPE_OWN`, cùng luật
    lùi về hẹp nhất như `None`."""
    ids = pham_vi.sale_ids_theo_pham_vi(db, sale_a, _Authz(""), MODULE)
    assert ids == {sale_a.id}


def test_lenh_chua_phat_hanh_khong_bao_gio_hien(db, lenh_nhap):
    stmt = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), None)
    thay = {r.id for r in db.execute(stmt).scalars()}
    assert lenh_nhap not in thay


def test_don_khong_co_sale_chi_hien_voi_all(db, sale_a, lenh_khong_sale):
    stmt_all = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), None)
    assert lenh_khong_sale in {r.id for r in db.execute(stmt_all).scalars()}
    stmt_own = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), {sale_a.id})
    assert lenh_khong_sale not in {r.id for r in db.execute(stmt_own).scalars()}


def test_ngoai_pham_vi_nem_403(db, sale_a, sale_b, lenh_cua):
    lsx = db.get(Lsx, lenh_cua(sale_b))
    with pytest.raises(HTTPException) as e:
        pham_vi.chan_ngoai_pham_vi(db, lsx, {sale_a.id})
    assert e.value.status_code == 403


def test_ngoai_pham_vi_lenh_khong_ton_tai_nem_404(db, sale_a):
    """`lsx is None` (id gõ bừa, không có lệnh nào khớp) → 404, KHÔNG phải 403 — người dùng cần
    biết là "không có lệnh này" chứ không phải "có nhưng không thuộc phần việc của bạn"."""
    with pytest.raises(HTTPException) as e:
        pham_vi.chan_ngoai_pham_vi(db, None, {sale_a.id})
    assert e.value.status_code == 404


def test_ngoai_pham_vi_lenh_chua_phat_hanh_nem_404(db, sale_a, lenh_nhap):
    """Lệnh có thật nhưng CHƯA phát hành → cũng 404, không phải 403: hai màn chỉ-đọc này không
    biết tới lệnh chưa phát hành nên coi như "không có", bất kể ai hỏi. Khoá riêng nhánh này để
    ai gộp nhầm với nhánh 403 (xoá điều kiện `trang_thai != TT_DA_PHAT_HANH`) sẽ bị bắt ngay."""
    lsx = db.get(Lsx, lenh_nhap)
    with pytest.raises(HTTPException) as e:
        pham_vi.chan_ngoai_pham_vi(db, lsx, {sale_a.id})
    assert e.value.status_code == 404


def test_trong_pham_vi_all_khong_nem_gi(db, sale_a, lenh_cua):
    """`sale_ids is None` (scope `all`) → cho qua thẳng, không cần tra `Order.sale_user_id`."""
    lsx = db.get(Lsx, lenh_cua(sale_a))
    pham_vi.chan_ngoai_pham_vi(db, lsx, None)  # không raise gì cả
