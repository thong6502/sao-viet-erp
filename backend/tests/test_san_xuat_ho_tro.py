"""Thực hiện sản xuất — HỖ TRỢ CHÉO (§9), bản sau khi gỡ tầng chia sản lượng (18/09/2026).

Phiếu hỗ trợ nay thuần là VẾT "người tổ nào sang giúp tổ nào, ngày nào, công đoạn nào" — không còn
tỷ lệ phần trăm, không còn trần tổng ≤ 100% (mg 0322). Luật còn lại soi thẳng ở tầng service:
cần xác nhận của CẢ HAI bên — mỗi bên là người giữ quyền Xác nhận sản lượng TRỌN tổ đó; một người
giữ quyền trọn cả hai tổ thì đề xuất là đủ luôn; cùng tổ thì chặn; huỷ giữ dòng đổi trạng thái.

Tách từ `test_san_xuat_phan_bo.py` (xoá cùng engine chia; bản cũ còn ở git HEAD).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.department import Department
from app.models.role import SCOPE_OWN
from app.models.san_xuat_phan_bo import SanXuatHoTro
from app.services.san_xuat import board, ho_tro
from tests.quyen_to_fixtures import cap_quyen_to
from tests.san_xuat_me_fixtures import NGAY, canh_me, tao_user

# Fixtures + helper luồng thật (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _canh_ho_tro(db, orders, lsx_svc, admin, customer):
    """Tổ thực hiện (vai admin đủ quyền) + tổ gốc (`u_goc` đủ quyền, admin không có gì) + một người
    hỗ trợ thuộc tổ gốc."""
    to_th, cv, _batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-TH")
    u_goc = tao_user(db, "to_truong_goc")
    to_goc = Department(name="Tổ Gốc", code="TO-GOC", la_san_xuat=True, has_piece_work=True)
    db.add(to_goc)
    db.flush()
    cap_quyen_to(db, u_goc, to_goc)
    emp = _emp(db, to_goc, "NV-GOC-1", ten="Thợ Hỗ Trợ")
    db.commit()
    return to_th, cv, to_goc, u_goc, emp


def test_de_xuat_roi_hai_ben_xac_nhan_thanh_confirmed(db, orders, lsx_svc, admin, customer):
    to_th, cv, to_goc, u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)

    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY,
    )
    assert r["trang_thai"] == "pending_both"          # admin chỉ đứng được cho bên thực hiện
    assert r["to_goc_id"] == to_goc.id and r["to_thuc_hien_id"] == to_th.id
    assert "ty_le_phan_tram" not in r                 # phiếu thôi mang tỷ lệ chia

    # Còn chờ ⇒ chỉ báo bên CHƯA xác nhận (tổ gốc), không báo lại người vừa đề xuất.
    assert r["notify_user_ids"] == [u_goc.id]
    assert r["su_kien"] == "de_xuat" and r["ho_ten"] == "Thợ Hỗ Trợ" and r["to_goc_ten"] == "Tổ Gốc"

    r2 = ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r["ho_tro_id"])
    assert r2["trang_thai"] == "confirmed"            # đủ xác nhận của hai bên
    # Đủ hai bên ⇒ báo người giữ Xác nhận sản lượng trọn tổ ở CẢ HAI tổ, trừ chính người vừa bấm.
    assert r2["notify_user_ids"] == [admin.id]


def test_hai_nguoi_cung_giup_mot_cong_doan_khong_con_tran_ty_le(db, orders, lsx_svc, admin, customer):
    """Trần "tổng tỷ lệ ≤ 100%" gỡ cùng ô tỷ lệ — bao nhiêu người sang giúp cũng xác nhận được."""
    _to_th, cv, to_goc, u_goc, emp1 = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    emp2 = _emp(db, to_goc, "NV-GOC-2", ten="Thợ Hỗ Trợ 2")
    db.commit()
    for e in (emp1, emp2):
        r = ho_tro.de_xuat_ho_tro(
            db, user=admin, cong_viec_id=cv.id, employee_id=e.id, ngay_lam_viec=NGAY,
        )
        assert ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r["ho_tro_id"])["trang_thai"] == "confirmed"


def test_to_cho_muon_thay_loi_moi_tren_ban_cua_minh(db, orders, lsx_svc, admin, customer):
    """Tổ GỐC (cho mượn người) không xem được công đoạn của tổ kia — lời mời phải hiện ở hộp "Chờ tổ
    bạn xác nhận" trên bàn của CHÍNH tổ gốc + badge menu; bên đề xuất không thấy lại nó ở hộp."""
    to_th, cv, to_goc, u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id,
        ngay_lam_viec=NGAY, mo_ta="Thiếu người ca sáng",
    )
    hop = board.cho_xac_nhan(db, u_goc, team_id=to_goc.id)
    assert [(h["id"], h["cho_ben_goc"], h["cho_ben_thuc_hien"]) for h in hop["ho_tro"]] == [
        (r["ho_tro_id"], True, False)
    ]
    assert hop["ho_tro"][0]["ten_cong_doan"] == cv.ten_cong_doan
    # Công đoạn thuộc tổ kia, không có dòng nào trên bàn tổ gốc để gắn chấm đỏ ⇒ bàn liệt kê riêng.
    assert hop["ho_tro"][0]["tren_ban"] is False
    assert hop["ho_tro"][0]["to_thuc_hien_ten"] == to_th.name
    assert {t["id"]: t["so_cho_xac_nhan"] for t in board.teams(db, u_goc, None)}[to_goc.id] == 1
    assert board.cho_xac_nhan(db, admin, team_id=to_th.id)["ho_tro"] == []

    ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r["ho_tro_id"])
    assert board.cho_xac_nhan(db, u_goc, team_id=to_goc.id)["ho_tro"] == []


def test_bam_xac_nhan_lai_ben_da_dung_ten_bi_bao_va_nut_theo_co(db, orders, lsx_svc, admin, customer):
    """Bên thực hiện đã đứng tên lúc đề xuất: drawer không bật nút Xác nhận cho họ (vẫn huỷ được),
    và gọi thẳng thì bị báo rõ chứ không trả "đã xác nhận" mà không đổi gì."""
    _to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY,
    )
    dong = board.chi_tiet_cong_viec(db, admin, None, cong_viec_id=cv.id)["ho_tro"]
    assert [(d["id"], d["co_the_xac_nhan"], d["co_the_huy"]) for d in dong] == [
        (r["ho_tro_id"], False, True)
    ]
    assert all("ty_le_phan_tram" not in d for d in dong)
    ver = db.get(SanXuatHoTro, r["ho_tro_id"]).version
    with pytest.raises(ValueError, match="đã xác nhận"):
        ho_tro.xac_nhan_ho_tro(db, user=admin, ho_tro_id=r["ho_tro_id"])
    db.rollback()
    assert db.get(SanXuatHoTro, r["ho_tro_id"]).version == ver


def test_de_xuat_cung_to_bi_chan(db, orders, lsx_svc, admin, customer):
    to_th, cv, _batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-CUNG")
    noi_bo = _emp(db, to_th, "NV-NOI-BO")             # người ĐÃ thuộc tổ thực hiện
    db.commit()
    with pytest.raises(ValueError):
        ho_tro.de_xuat_ho_tro(
            db, user=admin, cong_viec_id=cv.id, employee_id=noi_bo.id, ngay_lam_viec=NGAY,
        )


def test_mot_nguoi_mot_ngay_mot_cong_doan_chi_mot_phieu(db, orders, lsx_svc, admin, customer):
    _to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    ho_tro.de_xuat_ho_tro(db, user=admin, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY)
    with pytest.raises(ValueError, match="đã có thỏa thuận hỗ trợ"):
        ho_tro.de_xuat_ho_tro(
            db, user=admin, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY,
        )


def test_khong_co_xac_nhan_tron_to_o_ben_nao_khong_de_xuat_duoc(db, orders, lsx_svc, admin, customer):
    """Tài khoản lạ, người chỉ có Xác nhận sản lượng phạm vi "Của tôi", người có Thực hiện lệnh mà
    thiếu Xác nhận — không ai đứng được cho bên nào nên không đề xuất được."""
    to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    xn_own = tao_user(db, "xn_own_th")
    cap_quyen_to(db, xn_own, to_th, scope=SCOPE_OWN, viec=("confirm_output",))
    chi_chay = tao_user(db, "chi_chay_th")
    cap_quyen_to(db, chi_chay, to_th, viec=("run_order",))
    db.commit()
    for u in (SimpleNamespace(id=admin.id + 99_999), xn_own, chi_chay):
        with pytest.raises(PermissionError):
            ho_tro.de_xuat_ho_tro(
                db, user=u, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY,
            )


def test_quyen_tron_ca_hai_to_de_xuat_la_xac_nhan_luon(db, orders, lsx_svc, admin, customer):
    """Người có Xác nhận sản lượng `all` ở nút cha chung của hai tổ đứng được cho CẢ HAI bên — đề
    xuất xong là `confirmed`, khỏi chờ ai."""
    to_th, cv, to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    xuong = Department(name="Xưởng Hỗ Trợ", code="XUONG-HT", la_san_xuat=True)
    db.add(xuong)
    db.flush()
    to_th.parent_id = to_goc.parent_id = xuong.id
    quan_doc = tao_user(db, "quan_doc_ht")
    cap_quyen_to(db, quan_doc, xuong, viec=("confirm_output",))
    db.commit()

    r = ho_tro.de_xuat_ho_tro(
        db, user=quan_doc, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY,
    )
    assert r["trang_thai"] == "confirmed"
    ht = db.get(SanXuatHoTro, r["ho_tro_id"])
    assert ht.xac_nhan_goc_by_id == quan_doc.id and ht.xac_nhan_thuc_hien_by_id == quan_doc.id


def test_huy_ho_tro_doi_trang_thai(db, orders, lsx_svc, admin, customer):
    _to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY,
    )
    r2 = ho_tro.huy_ho_tro(db, user=admin, ho_tro_id=r["ho_tro_id"], ly_do="Đổi kế hoạch")
    assert r2["trang_thai"] == "cancelled"
    # Huỷ xong thì đề xuất lại được (bản cũ không còn "sống").
    r3 = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id, ngay_lam_viec=NGAY,
    )
    assert r3["trang_thai"] == "pending_both"


def test_moc_tu_client_quy_gio_tuong_ve_utc_that():
    """Ô `datetime-local` gửi chuỗi KHÔNG offset ⇒ Pydantic dựng datetime NAIVE = giờ TƯỜNG xưởng.
    `moc_tu_client` phải đọc nó như giờ địa phương rồi quy về UTC thật; mốc ĐÃ kèm offset thì giữ
    nguyên thời điểm."""
    from datetime import datetime, timezone

    from app.services.attendance_service import VN_TZ
    from app.services.gio_xuong import moc_tu_client

    naive = datetime(2026, 9, 11, 21, 47)
    assert moc_tu_client(naive) == naive.astimezone().astimezone(timezone.utc)
    assert moc_tu_client(naive).tzinfo is timezone.utc

    aware = datetime(2026, 9, 11, 21, 47, tzinfo=VN_TZ)
    assert moc_tu_client(aware) == aware
    assert moc_tu_client(None) is None
