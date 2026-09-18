"""Thực hiện sản xuất — Giai đoạn 3 mặt GHI: BÀN GIAO công đoạn (§11.2 · §11.3).

Soi tầng service `services/san_xuat/ban_giao.py` (nơi chứa LUẬT), không qua HTTP:
  · cùng tổ + cùng LSX → tự `confirmed`; khác tổ/LSX → `proposed` rồi bên NHẬN xác nhận;
  · số lượng giao = tổng tốt của MẺ chọn (không gõ tay); sửa MẺ chỉ khi còn `proposed`;
  · xác nhận là quyền Xác nhận sản lượng ở tổ ĐÍCH (dòng quyền theo tổ, mg 0302) — báo tin đẩy cho
    người giữ quyền đó trọn tổ bên kia, trừ người vừa bấm; điều chỉnh đẻ dòng lịch sử, giảm dưới
    lượng đã dùng ⇒ cờ không nhất quán.

`cung_to`/`lsx_id`/`department_id` là các cột SNAPSHOT của công việc — set thẳng trong test để soi
từng nhánh luật, không phụ thuộc số công đoạn mà fixture routing sinh ra. Riêng ĐÍCH bàn giao phải
là chặng sau theo routing (14/09/2026), nên `_hai_cv` khai cạnh phụ thuộc bước nguồn → bước đích.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.department import Department
from app.models.lsx import LsxCongDoan, LsxCongDoanPhuThuoc
from app.models.role import SCOPE_OWN
from app.models.san_xuat import CV_DANG_CHAY, CV_PHAT_HANH, SanXuatCongViec
from app.models.san_xuat_san_luong import (
    BG_DE_XUAT,
    BG_DIEU_CHINH,
    BG_XAC_NHAN,
    SanXuatBanGiao,
    SanXuatBanGiaoBatch,
    SanXuatBanGiaoDieuChinh,
)
from app.models.user import User
from app.repositories.rbac_repo import RoleRepository
from app.repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from app.services.rbac_service import AuthorizationService
from app.services.san_xuat import ban_giao, board, san_luong
from tests.quyen_to_fixtures import cap_quyen_to

from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _cvs,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-BG"):
    """Hai công việc cùng một tổ khoán, cùng ĐANG CHẠY, bước của `cv_dich` là CHẶNG SAU của bước
    `cv_nguon` theo routing (khai cạnh nếu chưa có). Trả (to, cv_nguon, cv_dich, lsx_id)."""
    to = _to_khoan(db, admin, ma=ma)
    a, _b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv1, cv2 = _cvs(db, to)[:2]
    for cv in (cv1, cv2):
        cv.trang_thai = CV_DANG_CHAY
        cv.don_vi_ra = "tờ"
        cv.don_vi_vao = "tờ"
    if not db.query(LsxCongDoanPhuThuoc).filter_by(
        buoc_truoc_id=cv1.lsx_cong_doan_id, buoc_sau_id=cv2.lsx_cong_doan_id
    ).first():
        db.add(LsxCongDoanPhuThuoc(
            buoc_truoc_id=cv1.lsx_cong_doan_id, buoc_sau_id=cv2.lsx_cong_doan_id
        ))
    db.commit()
    return to, cv1, cv2, a.id


def _to_dich(db, ma="TO-BG-DICH") -> tuple[Department, User]:
    u = User(username=f"head_{ma.lower()}", name="Tổ trưởng đích", password_hash="x")
    db.add(u)
    db.flush()
    d = Department(name="Tổ Đích", code=ma, la_san_xuat=True, has_piece_work=True)
    db.add(d)
    db.flush()
    cap_quyen_to(db, u, d)
    return d, u


def _batch(db, admin, cv, *, tot=100, lot_vao=None, t0=_T0):
    return san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=t0, ket_thuc=t0 + timedelta(hours=1),
        tong=tot, tot=tot, lot_vao=lot_vao,
    )["batch_id"]


# --- Đề xuất / tự xác nhận (§11.2) ----------------------------------------------------------
def test_de_xuat_khac_to_cho_xac_nhan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id                          # khác tổ → phải chờ xác nhận
    for ten, kw in (("tho_chay_dich", dict(viec=("run_order",))),
                    ("tho_own_dich", dict(viec=("confirm_output",), scope=SCOPE_OWN))):
        u = User(username=ten, name=ten, password_hash="x", department_id=to_b.id)
        db.add(u)
        db.flush()
        cap_quyen_to(db, u, to_b, **kw)
    db.commit()
    b = _batch(db, admin, cv1, tot=100)

    res = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id,
        batch_ids=[b],
    )
    assert res["trang_thai_ban_giao"] == BG_DE_XUAT
    assert res["so_luong"] == 100                       # = tốt của mẻ, không gõ tay
    # Đẩy cho người giữ Xác nhận sản lượng TRỌN tổ ĐÍCH — người chỉ có Thực hiện lệnh, hay chỉ có
    # Xác nhận ở phạm vi "Của tôi", không phải người xác nhận bàn giao nên không bị báo.
    assert res["notify_user_ids"] == [ub.id]


def test_hop_cho_xac_nhan_cua_to_dich_va_badge(db, orders, lsx_svc, admin, customer):
    """Bàn giao khác tổ chờ nhận hiện ở hộp "Chờ tổ bạn xác nhận" của bàn tổ ĐÍCH và cộng vào badge
    menu — tổ đích không phải đoán mở đúng công đoạn nào. Xác nhận xong thì rời hộp. SSE mang nhãn
    công đoạn để toast của người nhận nói được giao gì."""
    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id
    db.commit()
    b = _batch(db, admin, cv1, tot=100)
    res = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, batch_ids=[b],
    )
    assert res["su_kien"] == "de_xuat"
    assert res["nguon_ten"] == cv1.ten_cong_doan and res["dich_ten"] == cv2.ten_cong_doan

    hop = board.cho_xac_nhan(db, ub, team_id=to_b.id)
    assert [(x["id"], x["dich_cong_viec_id"], x["so_luong"]) for x in hop["ban_giao"]] == [
        (res["ban_giao_id"], cv2.id, 100)
    ]
    # Công đoạn đích nằm trên bàn tổ đích ⇒ chấm đỏ trên dòng đó, không liệt kê riêng.
    assert hop["ban_giao"][0]["tren_ban"] is True
    assert {t["id"]: t["so_cho_xac_nhan"] for t in board.teams(db, ub, None)}[to_b.id] == 1
    assert board.cho_xac_nhan(db, admin, team_id=to.id)["ban_giao"] == []   # tổ nguồn không phải bấm
    # Ô "chờ xác nhận" của bàn đích: chỉ còn lệnh có công đoạn chờ nhận.
    az = AuthorizationService(RoleRepository(db))
    loc = board.work_items(db, ub, az, team_id=to_b.id, cho_xac_nhan=True)
    assert [[w["id"] for w in l["cong_viec"]] for l in loc["lenh"]] == [[cv2.id]]
    assert [w["id"] for w in board.work_items(
        db, ub, az, team_id=to_b.id, nhom="phang", cho_xac_nhan=True)["cong_viec"]] == [cv2.id]

    ban_giao.xac_nhan(db, user=ub, ban_giao_id=res["ban_giao_id"])
    assert board.cho_xac_nhan(db, ub, team_id=to_b.id)["ban_giao"] == []
    assert {t["id"]: t["so_cho_xac_nhan"] for t in board.teams(db, ub, None)}[to_b.id] == 0
    assert board.work_items(db, ub, az, team_id=to_b.id, cho_xac_nhan=True)["lenh"] == []
    assert board.work_items(db, ub, az, team_id=to_b.id)["trang"]["tong"] == 1


def test_cung_to_cung_lsx_tu_xac_nhan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx                        # cùng tổ + cùng LSX → tự confirmed
    db.commit()
    b = _batch(db, admin, cv1, tot=100)

    res = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id,
        batch_ids=[b],
    )
    assert res["trang_thai_ban_giao"] == BG_XAC_NHAN
    assert res["notify_user_ids"] == []                 # không ai phải đợi


def test_so_theo_me_khong_vuot_phan_con_lai(db, orders, lsx_svc, admin, customer):
    """Bàn giao CŨ (trước giao-theo-mẻ) không gắn mẻ: mẻ vẫn hiện chưa giao nhưng số bị chặn ở phần
    còn lại, không giao trùng."""
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx
    b = _batch(db, admin, cv1, tot=50)
    db.add(SanXuatBanGiao(
        nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id, cung_to=True, so_luong=30,
        don_vi="tờ", trang_thai=BG_XAC_NHAN,
    ))
    db.commit()

    res = ban_giao.de_xuat(db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id,
                           batch_ids=[b])
    assert res["so_luong"] == 20


def test_sua_me_chi_khi_proposed(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id
    db.commit()
    b1 = _batch(db, admin, cv1, tot=100)
    b2 = _batch(db, admin, cv1, tot=40, t0=_T0 + timedelta(hours=2))
    chung = dict(db=db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id)
    repo = SanXuatSanLuongRepository(db)
    r = ban_giao.de_xuat(**chung, batch_ids=[b1, b2])
    assert r["so_luong"] == 140

    # Tick nhầm b1 → gỡ ra: số tính lại, b1 thành chưa giao.
    r2 = ban_giao.sua_de_xuat(db, user=admin, ban_giao_id=r["ban_giao_id"], batch_ids=[b2])
    assert r2["so_luong"] == 40 and r2["version"] == r["version"] + 1
    assert repo.batch_da_giao_ids(cv1.id) == {b2}

    # b1 giờ đi theo lần giao khác ⇒ lần giao đầu không lấy lại được; bỏ trống mẻ cũng không được.
    ban_giao.de_xuat(**chung, batch_ids=[b1])
    with pytest.raises(ValueError, match="đã giao rồi"):
        ban_giao.sua_de_xuat(db, user=admin, ban_giao_id=r["ban_giao_id"], batch_ids=[b1, b2])
    with pytest.raises(ValueError, match="Chọn mẻ"):
        ban_giao.sua_de_xuat(db, user=admin, ban_giao_id=r["ban_giao_id"], batch_ids=[])

    ban_giao.xac_nhan(db, user=ub, ban_giao_id=r["ban_giao_id"])
    with pytest.raises(ValueError, match="chưa xác nhận"):  # đã xác nhận → chỉ còn điều chỉnh số
        ban_giao.sua_de_xuat(db, user=admin, ban_giao_id=r["ban_giao_id"], batch_ids=[b2])


def test_xac_nhan_la_quyen_to_dich(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id
    db.commit()
    b = _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id,
        batch_ids=[b],
    )

    with pytest.raises(PermissionError, match="Xác nhận sản lượng"):  # tổ NGUỒN không tự xác nhận
        ban_giao.xac_nhan(db, user=admin, ban_giao_id=r["ban_giao_id"])
    # Ở tổ ĐÍCH mà chỉ có Thực hiện lệnh thì cũng không xác nhận được.
    chi_chay = User(username="chi_chay_dich", name="Chỉ chạy", password_hash="x",
                    department_id=to_b.id)
    db.add(chi_chay)
    db.flush()
    cap_quyen_to(db, chi_chay, to_b, viec=("run_order",))
    db.commit()
    with pytest.raises(PermissionError, match="Xác nhận sản lượng"):
        ban_giao.xac_nhan(db, user=chi_chay, ban_giao_id=r["ban_giao_id"])

    res = ban_giao.xac_nhan(db, user=ub, ban_giao_id=r["ban_giao_id"])
    assert res["trang_thai_ban_giao"] == BG_XAC_NHAN
    assert res["notify_user_ids"] == [admin.id]          # báo ngược người xác nhận ở tổ nguồn


# --- Điều chỉnh (§11.3) ---------------------------------------------------------------------
def test_dieu_chinh_ghi_lich_su_va_co_khong_nhat_quan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx
    db.commit()
    b1 = _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id,
        batch_ids=[b1],
    )
    # Công đoạn sau tiêu thụ 80 (lot trỏ về batch của nguồn) → giảm bàn giao xuống dưới 80 = lệch.
    _batch(db, admin, cv2, tot=80, lot_vao=[{"nguon_batch_id": b1, "so_luong": 80}],
           t0=_T0 + timedelta(hours=3))

    res = ban_giao.dieu_chinh(
        db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=50, mo_ta="Đếm lại thiếu"
    )
    assert res["trang_thai_ban_giao"] == BG_DIEU_CHINH
    assert res["so_luong"] == 50 and res["khong_nhat_quan"] is True
    ls = db.query(SanXuatBanGiaoDieuChinh).filter_by(ban_giao_id=r["ban_giao_id"]).all()
    assert len(ls) == 1 and float(ls[0].so_luong_truoc) == 100 and float(ls[0].so_luong_sau) == 50

    # Nâng lại trên mức đã dùng → hết lệch.
    res2 = ban_giao.dieu_chinh(
        db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=90, mo_ta="Đếm lại đủ"
    )
    assert res2["khong_nhat_quan"] is False


def test_ngan_chi_tiet_ghi_ai_giao_ai_nhan_va_tung_lan_dieu_chinh(db, orders, lsx_svc, admin, customer):
    """Cả tổ giao lẫn tổ nhận đều đọc được ai đề xuất, ai xác nhận, lúc nào, và từng lần điều chỉnh
    (ai, trước → sau, mô tả, lúc). Tên lấy từ tài khoản đã thao tác, không gõ tay."""
    from app.schemas.san_xuat import WorkItemChiTietOut

    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    to_b, ub = _to_dich(db)
    cv2.department_id = to_b.id
    db.commit()
    b = _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id,
                         batch_ids=[b])
    az = AuthorizationService(RoleRepository(db))

    def dong(cv, user, khoa):
        ct = board.chi_tiet_cong_viec(db, user, az, cong_viec_id=cv.id)
        return WorkItemChiTietOut.model_validate(ct).model_dump()[khoa][0]

    cho = dong(cv2, ub, "ban_giao_den")
    assert cho["nguoi_de_xuat"] == admin.name and cho["de_xuat_luc"] is not None
    assert (cho["nguoi_xac_nhan"], cho["xac_nhan_luc"], cho["dieu_chinh"]) == (None, None, [])

    ban_giao.xac_nhan(db, user=ub, ban_giao_id=r["ban_giao_id"])
    ban_giao.dieu_chinh(db, user=ub, ban_giao_id=r["ban_giao_id"], so_luong_sau=95,
                        mo_ta="Đếm lại thiếu 5")
    for cv, user, khoa in ((cv1, admin, "ban_giao_di"), (cv2, ub, "ban_giao_den")):
        g = dong(cv, user, khoa)
        assert (g["nguoi_de_xuat"], g["nguoi_xac_nhan"]) == (admin.name, "Tổ trưởng đích")
        assert g["xac_nhan_luc"] is not None
        assert [(d["so_luong_truoc"], d["so_luong_sau"], d["mo_ta"], d["nguoi"], d["khong_nhat_quan"])
                for d in g["dieu_chinh"]] == [(100, 95, "Đếm lại thiếu 5", "Tổ trưởng đích", False)]
        assert g["dieu_chinh"][0]["luc"] is not None


def test_dieu_chinh_khong_con_doi_ly_do(db, orders, lsx_svc, admin, customer):
    """Danh mục lý do/lỗi ĐÃ GỠ (mg 0288): điều chỉnh bàn giao KHÔNG còn phải nêu lý do."""
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx
    db.commit()
    b = _batch(db, admin, cv1, tot=100)
    r = ban_giao.de_xuat(
        db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id,
        batch_ids=[b],
    )

    res = ban_giao.dieu_chinh(db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=80)
    assert res["so_luong"] == 80


# --- Đích = chặng sau theo routing (14/09/2026) ---------------------------------------------
def test_dich_phai_la_chang_sau_theo_routing(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    b = _batch(db, admin, cv1, tot=100)
    # Chính nó không phải chặng sau của nó.
    with pytest.raises(ValueError, match="không phải chặng sau"):
        ban_giao.de_xuat(
            db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv1.id,
            batch_ids=[b],
        )
    # Còn chặng sau thì không được giao ra ngoài.
    with pytest.raises(ValueError, match="phải giao cho chặng sau"):
        ban_giao.de_xuat(
            db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=None,
            batch_ids=[b],
        )


def test_buoc_cuoi_lenh_khong_ban_giao(db, orders, lsx_svc, admin, customer):
    """Bước cuối của lệnh không có chặng sau ⇒ không bàn giao (giao ra kho đã gỡ 17/09/2026);
    thành phẩm vào kho qua KCS đề nghị nhập kho."""
    to, cv1, _cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    repo = SanXuatSanLuongRepository(db)
    cuoi = next(c for c in _cvs(db, to) if not repo.cong_viec_chang_sau(c))
    cuoi.trang_thai = CV_DANG_CHAY
    cuoi.don_vi_ra = cuoi.don_vi_vao = "tờ"
    db.commit()
    b = _batch(db, admin, cuoi, tot=100)
    for dich in (None, cv1.id):
        with pytest.raises(ValueError, match="Bước cuối của lệnh không bàn giao"):
            ban_giao.de_xuat(
                db, user=admin, nguon_cong_viec_id=cuoi.id, dich_cong_viec_id=dich,
                batch_ids=[b],
            )
    assert db.query(SanXuatBanGiao).count() == 0


def _buoc(db, lsx_id, thu_tu, ten):
    cd = LsxCongDoan(lsx_id=lsx_id, thu_tu=thu_tu, ten=ten, nhom="finishing")
    db.add(cd)
    db.flush()
    return cd


def _viec(db, goi_id, lsx_id, cd, so=1, tong=1):
    cv = SanXuatCongViec(
        goi_id=goi_id, lsx_id=lsx_id, lsx_cong_doan_id=cd.id, step_key=cd.step_key,
        phan_doan_so=so, phan_doan_tong=tong, ten_cong_doan=cd.ten, trang_thai=CV_PHAT_HANH,
    )
    db.add(cv)
    db.flush()
    return cv


def test_chang_sau_theo_canh_roi_theo_thu_tu(db, orders, lsx_svc, admin, customer):
    """Cạnh đi ra thắng thứ tự bảng; bước không khai cạnh lấy bước kế tiếp; bước sau tách lần chạy
    ⇒ trả MỌI lần chạy; bước cuối lệnh ⇒ rỗng."""
    to = _to_khoan(db, admin, ma="TO-CS")
    a, _b, goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    x, y, z = (_buoc(db, a.id, 900 + i, t) for i, t in enumerate(("X", "Y", "Z")))
    cvx, cvy = _viec(db, goi.id, a.id, x), _viec(db, goi.id, a.id, y)
    z1, z2 = _viec(db, goi.id, a.id, z, 1, 2), _viec(db, goi.id, a.id, z, 2, 2)
    db.commit()
    repo = SanXuatSanLuongRepository(db)

    assert [c.id for c in repo.cong_viec_chang_sau(cvx)] == [cvy.id]       # không cạnh → thu_tu
    assert [c.id for c in repo.cong_viec_chang_sau(cvy)] == [z1.id, z2.id]  # hai lần chạy
    assert repo.cong_viec_chang_sau(z1) == []                               # bước cuối lệnh

    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=x.id, buoc_sau_id=z.id))
    db.commit()
    assert [c.id for c in repo.cong_viec_chang_sau(cvx)] == [z1.id, z2.id]  # cạnh thắng thu_tu


# --- Giao theo mẻ (14/09/2026) --------------------------------------------------------------
def test_giao_theo_me(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer)
    cv1.lsx_id = cv2.lsx_id = lsx                        # tự xác nhận để điều chỉnh được
    db.commit()
    b1 = _batch(db, admin, cv1, tot=100)
    b2 = _batch(db, admin, cv1, tot=50, t0=_T0 + timedelta(hours=2))
    chung = dict(db=db, user=admin, nguon_cong_viec_id=cv1.id, dich_cong_viec_id=cv2.id)

    with pytest.raises(ValueError, match="Chọn mẻ"):                 # còn mẻ chưa giao
        ban_giao.de_xuat(**chung)

    r = ban_giao.de_xuat(**chung, batch_ids=[b1])
    assert r["so_luong"] == 100
    link = db.query(SanXuatBanGiaoBatch).filter_by(ban_giao_id=r["ban_giao_id"]).all()
    assert [lk.batch_id for lk in link] == [b1]
    repo = SanXuatSanLuongRepository(db)
    assert repo.batch_da_giao_ids(cv1.id) == {b1}

    with pytest.raises(ValueError, match="đã giao rồi"):               # mẻ không giao hai lần
        ban_giao.de_xuat(**chung, batch_ids=[b1])
    assert ban_giao.de_xuat(**chung, batch_ids=[b2])["so_luong"] == 50

    # Bên nhận đếm thiếu 5 ⇒ điều chỉnh; hết mẻ chưa giao nên phần lẻ 5 giao không cần chọn mẻ.
    ban_giao.dieu_chinh(db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=95)
    r3 = ban_giao.de_xuat(**chung)
    assert r3["so_luong"] == 5
    assert repo.me_cua_ban_giao_nhieu([r["ban_giao_id"], r3["ban_giao_id"]]) == {
        r["ban_giao_id"]: [b1]
    }
    with pytest.raises(ValueError, match="Không còn sản lượng tốt"):
        ban_giao.de_xuat(**chung)


# --- SSE bàn giao: MỘT gói cho cả hai tổ (16/09/2026) -----------------------------------------
@pytest.mark.parametrize(("nguon", "dich", "ky_vong"), [(7, 3, [3, 7]), (5, 5, [5])])
def test_phat_sse_ban_giao_mot_goi_cho_ca_hai_to(monkeypatch, nguon, dich, ky_vong):
    """`broadcast` tới mọi kết nối và mỗi gói bump tick chung ở FE — mỗi tổ một gói là mọi màn
    đang mở nạp lại hai lượt cho một cú bấm."""
    from app.routers import san_xuat as router_sx

    goi: list[dict] = []
    monkeypatch.setattr(router_sx.hub, "broadcast", goi.append)
    monkeypatch.setattr(router_sx.hub, "publish", lambda *a, **k: None)
    router_sx._phat_sse_ban_giao({
        "nguon_department_id": nguon, "dich_department_id": dich,
        "ban_giao_id": 11, "trang_thai_ban_giao": "cho_xac_nhan",
    })
    assert goi == [{"type": "san_xuat_ban_giao_changed", "team_ids": ky_vong,
                    "ban_giao_id": 11, "trang_thai": "cho_xac_nhan"}]
