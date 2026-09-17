"""Thực hiện sản xuất — Giai đoạn 4: HỖ TRỢ CHÉO (§9) + PHÂN BỔ SẢN LƯỢNG → lương khoán (§12).

Soi thẳng tầng service (nơi chứa LUẬT), không qua HTTP:
  · Hỗ trợ chéo: tỷ lệ do người nhập, cần xác nhận của CẢ HAI bên — mỗi bên là người giữ quyền Xác
    nhận sản lượng TRỌN tổ đó (dòng quyền theo tổ, mg 0302); một người giữ quyền trọn cả hai tổ thì
    đề xuất là đủ luôn; trần tổng ≤ 100% cùng công đoạn + ngày; huỷ giữ dòng đổi trạng thái.
  · Phân bổ: quy đổi bản địa↔trả lương ĐỒNG NHẤT; người hỗ trợ nhận đúng tỷ lệ (ghi cho tổ gốc); phần
    còn lại chia theo phút có mặt hợp lệ; Σ khớp Q chính xác; thiếu trọng số hoặc bàn
    giao không nhất quán ⇒ CHẶN chốt (không chặn ghi); chốt → feed lương; kỳ khoá → bù trừ.
  · Seam lương: `ProductionOutputRepository` chỉ đọc dòng ĐÃ CHỐT + bù trừ đúng kỳ (nháp ⇒ rỗng).

Tái dùng dàn cảnh (đơn → SX → phát hành vào một tổ khoán) từ test thực thi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.attendance import CHECK_IN, CHECK_OUT, AttendanceLog, WorkShift
from app.models.department import Department
from app.models.payroll import PERIOD_LOCKED, PayrollPeriod
from app.models.role import SCOPE_OWN
from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_phan_bo import SanXuatHoTro, SanXuatPhanBo
from app.models.san_xuat_san_luong import SanXuatBanGiao, SanXuatBatch
from app.models.san_xuat_thuc_thi import SanXuatKhoangThamGia
from app.models.user import User
from app.repositories.production_output_repo import ProductionOutputRepository
from app.repositories.san_xuat_phan_bo_repo import SanXuatPhanBoRepository
from app.services.attendance_service import VN_TZ
from app.services.san_xuat import board, ho_tro, phan_bo, san_luong
from tests.quyen_to_fixtures import cap_quyen_to

# Fixtures + helper luồng thật (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    _mot_cv,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
_NGAY = _T0.date()


# --- Dàn cảnh dùng chung --------------------------------------------------------------------
def _user(db, username) -> User:
    u = User(username=username, name=username, password_hash="x")
    db.add(u)
    db.flush()
    return u


def _utc(dt: datetime) -> datetime:
    """SQLite trả cột `DateTime(timezone=True)` về NAIVE — ép nhãn UTC để so thời điểm."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _khoang(db, cv, emp, bat_dau, ket_thuc) -> SanXuatKhoangThamGia:
    """Khoảng tham gia dựng thẳng (engine đọc phút có mặt để chia trọng số §12.2)."""
    k = SanXuatKhoangThamGia(
        cong_viec_id=cv.id, phien_chay_id=1, employee_id=emp.id,
        bat_dau=bat_dau, ket_thuc=ket_thuc,
    )
    db.add(k)
    db.flush()
    return k


def _cham_cong(db, emp, *, ngay=_NGAY, vao_h=8, ra_h=17) -> None:
    """Gán ca hành chính 08:00–17:00 (giờ VN) + một cặp chấm công VÀO/RA phủ trọn cửa sổ batch, để NV
    có 'khoảng có mặt hợp lệ' (§7.3). Không có nó thì phút hợp lệ = 0 ⇒ engine đánh 'thiếu chấm công'
    và chặn chốt — đúng luật, nên mọi test cần CHỐT THÀNH CÔNG phải cấp chấm công thật."""
    ca = db.query(WorkShift).filter_by(name="HC-PB").first()
    if ca is None:
        ca = WorkShift(name="HC-PB", start_minute=480, end_minute=1020, is_overnight=False)
        db.add(ca)
        db.flush()
    emp.default_shift_id = ca.id
    for h, ct in ((vao_h, CHECK_IN), (ra_h, CHECK_OUT)):
        loc = datetime(ngay.year, ngay.month, ngay.day, h, 0, tzinfo=VN_TZ)
        db.add(AttendanceLog(employee_id=emp.id, check_type=ct,
                             checked_at=loc.astimezone(timezone.utc)))
    db.flush()


def _canh_phan_bo(db, orders, lsx_svc, admin, customer, *, tot=100.0, ma="TO-PB"):
    """Tổ khoán (vai admin đủ quyền trên dòng tổ) + công việc ĐANG CHẠY có đơn giá + một batch tốt."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "tờ"
    cv.don_vi_vao = "tờ"
    cv.khoan_json = {"don_gia": 10, "don_vi": "tờ"}
    db.commit()
    r = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=tot, tot=tot,
    )
    batch = db.get(SanXuatBatch, r["batch_id"])
    return to, cv, batch


def _canh_ho_tro(db, orders, lsx_svc, admin, customer):
    """Tổ thực hiện (vai admin đủ quyền) + tổ gốc (`u_goc` đủ quyền, admin không có gì) + một người
    hỗ trợ thuộc tổ gốc."""
    to_th, cv, _batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-TH")
    u_goc = _user(db, "to_truong_goc")
    to_goc = Department(
        name="Tổ Gốc", code="TO-GOC", la_san_xuat=True,
        has_piece_work=True,
    )
    db.add(to_goc)
    db.flush()
    cap_quyen_to(db, u_goc, to_goc)
    emp = _emp(db, to_goc, "NV-GOC-1", ten="Thợ Hỗ Trợ")
    db.commit()
    return to_th, cv, to_goc, u_goc, emp


# --- Hỗ trợ chéo (§9) -----------------------------------------------------------------------
def test_de_xuat_roi_hai_ben_xac_nhan_thanh_confirmed(db, orders, lsx_svc, admin, customer):
    to_th, cv, to_goc, u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)

    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id,
        ngay_lam_viec=_NGAY, ty_le_phan_tram=20,
    )
    assert r["trang_thai"] == "pending_both"          # admin chỉ đứng được cho bên thực hiện
    assert r["to_goc_id"] == to_goc.id and r["to_thuc_hien_id"] == to_th.id

    # Còn chờ ⇒ chỉ báo bên CHƯA xác nhận (tổ gốc), không báo lại người vừa đề xuất.
    assert r["notify_user_ids"] == [u_goc.id]
    assert r["su_kien"] == "de_xuat" and r["ho_ten"] == "Thợ Hỗ Trợ" and r["to_goc_ten"] == "Tổ Gốc"

    r2 = ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r["ho_tro_id"])
    assert r2["trang_thai"] == "confirmed"            # đủ xác nhận của hai bên
    # Đủ hai bên ⇒ báo người giữ Xác nhận sản lượng trọn tổ ở CẢ HAI tổ, trừ chính người vừa bấm.
    assert r2["notify_user_ids"] == [admin.id]


def test_to_cho_muon_thay_loi_moi_tren_ban_cua_minh(db, orders, lsx_svc, admin, customer):
    """Tổ GỐC (cho mượn người) không xem được công đoạn của tổ kia — lời mời phải hiện ở hộp "Chờ tổ
    bạn xác nhận" trên bàn của CHÍNH tổ gốc + badge menu; bên đề xuất không thấy lại nó ở hộp."""
    to_th, cv, to_goc, u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id,
        ngay_lam_viec=_NGAY, ty_le_phan_tram=10, mo_ta="Thiếu người ca sáng",
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
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id,
        ngay_lam_viec=_NGAY, ty_le_phan_tram=10,
    )
    dong = board.chi_tiet_cong_viec(db, admin, None, cong_viec_id=cv.id)["ho_tro"]
    assert [(d["id"], d["co_the_xac_nhan"], d["co_the_huy"]) for d in dong] == [
        (r["ho_tro_id"], False, True)
    ]
    ver = db.get(SanXuatHoTro, r["ho_tro_id"]).version
    with pytest.raises(ValueError, match="đã xác nhận"):
        ho_tro.xac_nhan_ho_tro(db, user=admin, ho_tro_id=r["ho_tro_id"])
    db.rollback()
    assert db.get(SanXuatHoTro, r["ho_tro_id"]).version == ver


def test_de_xuat_cung_to_bi_chan(db, orders, lsx_svc, admin, customer):
    to_th, cv, _batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-CUNG")
    noi_bo = _emp(db, to_th, "NV-NOI-BO")             # người ĐÃ thuộc tổ thực hiện
    db.commit()
    with pytest.raises(ValueError):
        ho_tro.de_xuat_ho_tro(
            db, user=admin, cong_viec_id=cv.id, employee_id=noi_bo.id,
            ngay_lam_viec=_NGAY, ty_le_phan_tram=10,
        )


def test_ty_le_ngoai_khoang_bi_chan(db, orders, lsx_svc, admin, customer):
    _to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    for xau in (0, -5, 150):
        with pytest.raises(ValueError):
            ho_tro.de_xuat_ho_tro(
                db, user=admin, cong_viec_id=cv.id, employee_id=emp.id,
                ngay_lam_viec=_NGAY, ty_le_phan_tram=xau,
            )


def test_khong_co_xac_nhan_tron_to_o_ben_nao_khong_de_xuat_duoc(db, orders, lsx_svc, admin, customer):
    """Tài khoản lạ, người chỉ có Xác nhận sản lượng phạm vi "Của tôi", người có Thực hiện lệnh mà
    thiếu Xác nhận — không ai đứng được cho bên nào nên không đề xuất được."""
    to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    xn_own = _user(db, "xn_own_th")
    cap_quyen_to(db, xn_own, to_th, scope=SCOPE_OWN, viec=("confirm_output",))
    chi_chay = _user(db, "chi_chay_th")
    cap_quyen_to(db, chi_chay, to_th, viec=("run_order",))
    db.commit()
    for u in (SimpleNamespace(id=admin.id + 99_999), xn_own, chi_chay):
        with pytest.raises(PermissionError):
            ho_tro.de_xuat_ho_tro(
                db, user=u, cong_viec_id=cv.id, employee_id=emp.id,
                ngay_lam_viec=_NGAY, ty_le_phan_tram=10,
            )


def test_quyen_tron_ca_hai_to_de_xuat_la_xac_nhan_luon(db, orders, lsx_svc, admin, customer):
    """Người có Xác nhận sản lượng `all` ở nút cha chung của hai tổ đứng được cho CẢ HAI bên — đề
    xuất xong là `confirmed`, khỏi chờ ai."""
    to_th, cv, to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    xuong = Department(name="Xưởng Hỗ Trợ", code="XUONG-HT", la_san_xuat=True)
    db.add(xuong)
    db.flush()
    to_th.parent_id = to_goc.parent_id = xuong.id
    quan_doc = _user(db, "quan_doc_ht")
    cap_quyen_to(db, quan_doc, xuong, viec=("confirm_output",))
    db.commit()

    r = ho_tro.de_xuat_ho_tro(
        db, user=quan_doc, cong_viec_id=cv.id, employee_id=emp.id,
        ngay_lam_viec=_NGAY, ty_le_phan_tram=20,
    )
    assert r["trang_thai"] == "confirmed"
    ht = db.get(SanXuatHoTro, r["ho_tro_id"])
    assert ht.xac_nhan_goc_by_id == quan_doc.id and ht.xac_nhan_thuc_hien_by_id == quan_doc.id


def test_tran_tong_ty_le_vuot_100_bi_chan(db, orders, lsx_svc, admin, customer):
    to_th, cv, to_goc, u_goc, emp1 = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    emp2 = _emp(db, to_goc, "NV-GOC-2", ten="Thợ Hỗ Trợ 2")
    db.commit()

    r1 = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp1.id,
        ngay_lam_viec=_NGAY, ty_le_phan_tram=60,
    )
    ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r1["ho_tro_id"])   # confirmed 60%

    r2 = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp2.id,
        ngay_lam_viec=_NGAY, ty_le_phan_tram=50,
    )
    with pytest.raises(ValueError):                                     # 60 + 50 > 100
        ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r2["ho_tro_id"])


def test_huy_ho_tro_doi_trang_thai(db, orders, lsx_svc, admin, customer):
    _to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=emp.id,
        ngay_lam_viec=_NGAY, ty_le_phan_tram=15,
    )
    r2 = ho_tro.huy_ho_tro(db, user=admin, ho_tro_id=r["ho_tro_id"], ly_do="Đổi kế hoạch")
    assert r2["trang_thai"] == "cancelled"


# --- Phân bổ: chia theo phút có mặt hợp lệ (§12.2) -------------------------------------------
def test_tinh_chia_theo_phut(db, orders, lsx_svc, admin, customer):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer)
    e1 = _emp(db, to, "NV-PB-1")
    e2 = _emp(db, to, "NV-PB-2")
    _cham_cong(db, e1)
    _cham_cong(db, e2)
    db.commit()
    # e1 chỉ đứng nửa đầu mẻ, e2 đứng trọn mẻ ⇒ e2 nhận gấp đôi (không còn nhân hệ số bậc).
    _khoang(db, cv, e1, batch.bat_dau, batch.bat_dau + (batch.ket_thuc - batch.bat_dau) / 2)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    assert kq["can_chot"] is True and kq["so_dong"] == 2
    assert kq["trang_thai"] == "draft"

    dong = phan_bo.SanXuatPhanBoRepository(db).cac_dong(kq["phan_bo_id"])
    tong = sum(float(d.so_luong_tra_luong) for d in dong)
    assert abs(tong - 100.0) < 1e-6                                    # Σ khớp Q chính xác
    theo_nv = {d.employee_id: float(d.so_luong_tra_luong) for d in dong}
    assert abs(theo_nv[e2.id] - 2 * theo_nv[e1.id]) < 0.01             # phút gấp đôi ⇒ phần gấp đôi


def test_khong_ai_tham_gia_chan_chot(db, orders, lsx_svc, admin, customer):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-TRONG")
    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)       # không khoảng nào
    assert kq["can_chot"] is False


# --- Phân bổ: hỗ trợ trước rồi chia phần còn lại (§9.2 × §12.2) ------------------------------
def test_ho_tro_nhan_dung_ty_le_phan_con_lai_chia_theo_phut(db, orders, lsx_svc, admin, customer):
    to_th, cv, to_goc, u_goc, sup = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    batch = db.query(SanXuatBatch).filter_by(cong_viec_id=cv.id).first()
    # Thỏa thuận hỗ trợ 20% đã xác nhận, rơi đúng ngày batch.
    r = ho_tro.de_xuat_ho_tro(
        db, user=admin, cong_viec_id=cv.id, employee_id=sup.id,
        ngay_lam_viec=batch.bat_dau.date(), ty_le_phan_tram=20,
    )
    ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r["ho_tro_id"])
    # Hai thợ tổ thực hiện chia phần còn lại.
    e1 = _emp(db, to_th, "NV-TH-1")
    e2 = _emp(db, to_th, "NV-TH-2")
    _cham_cong(db, e1)
    _cham_cong(db, e2)
    db.commit()
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    assert kq["can_chot"] is True and abs(kq["tong_ty_le_ho_tro"] - 20.0) < 1e-6
    dong = phan_bo.SanXuatPhanBoRepository(db).cac_dong(kq["phan_bo_id"])
    ho_tro_dong = [d for d in dong if d.la_ho_tro]
    con_lai_dong = [d for d in dong if not d.la_ho_tro]
    assert len(ho_tro_dong) == 1
    assert abs(float(ho_tro_dong[0].so_luong_tra_luong) - 20.0) < 1e-6      # 100 × 20%
    assert ho_tro_dong[0].department_id == to_goc.id                        # ghi cho tổ gốc
    assert abs(sum(float(d.so_luong_tra_luong) for d in con_lai_dong) - 80.0) < 1e-6
    assert abs(sum(float(d.so_luong_tra_luong) for d in dong) - 100.0) < 1e-6


# --- Chốt · gate bàn giao không nhất quán · feed lương --------------------------------------
def test_ban_giao_khong_nhat_quan_chan_chot(db, orders, lsx_svc, admin, customer):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-BG")
    e = _emp(db, to, "NV-PB-BG")
    _cham_cong(db, e)                                                  # cô lập gate bàn giao, không dính thiếu chấm công
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.add(SanXuatBanGiao(
        nguon_cong_viec_id=cv.id, so_luong=10, don_vi="tờ", khong_nhat_quan=True,
    ))
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    with pytest.raises(ValueError):                                    # §11.3 chặn tới khi gỡ
        phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])


def test_nhap_chua_chot_khong_feed_luong(db, orders, lsx_svc, admin, customer):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-FEED0")
    e = _emp(db, to, "NV-PB-F0")
    _cham_cong(db, e)
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()
    phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)            # mới NHÁP
    assert ProductionOutputRepository(db).list_nguoi_by_period(2026, 8) == []


def test_chot_roi_feed_luong(db, orders, lsx_svc, admin, customer):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-FEED")
    e1 = _emp(db, to, "NV-PB-F1")
    e2 = _emp(db, to, "NV-PB-F2")
    _cham_cong(db, e1)
    _cham_cong(db, e2)
    db.commit()
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    r = phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    assert r["trang_thai"] == "finalized"

    rows = ProductionOutputRepository(db).list_nguoi_by_period(2026, 8)
    assert rows and all(x.tinh_khoan for x in rows)
    assert abs(sum(x.quantity for x in rows) - 100.0) < 1e-6           # feed đúng tổng Q
    # Đơn giá LUÔN 0 từ 11/09/2026: sản xuất ghi SỐ LƯỢNG, kế toán lương đổi ra tiền.
    assert all(x.unit_price == 0.0 for x in rows)


def test_engine_chia_khong_con_bat_ky_o_tien_nao(db, orders, lsx_svc, admin, customer):
    """Sản xuất ghi SỐ LƯỢNG. Ảnh chụp có đơn giá lẫn `don_gia_hd` thì engine vẫn phải làm như
    không thấy — không khoá tiền nào được lọt xuống dòng chia, và seam lương nhận đơn giá 0.

    Chủ xưởng chốt 11/09/2026: *"bên sản xuất với kế hoạch thì không cần liên quan tới lương khoán
    đâu, đó là việc của kế toán lương, bên sản xuất chỉ ghi nhận số lượng thôi"*.
    """
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-HD")
    cv.khoan_json = {
        "don_gia": 40, "don_vi": "nhịp",
        "cong_thuc": "50000 + don_gia_khoan * sl_ra", "don_gia_hd": 620.0,
    }
    db.commit()
    e = _emp(db, to, "NV-PB-HD")
    _cham_cong(db, e)
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq_tinh = phan_bo._tinh_batch(db, cv, batch, SanXuatPhanBoRepository(db))
    assert not hasattr(kq_tinh, "don_gia")
    assert kq_tinh.dong, "phải có dòng chia để bài này nói được điều gì"
    for d in kq_tinh.dong:
        assert "don_gia" not in d
    # Đơn vị trả lương = đơn vị RA của bước, không phải đơn vị TIỀN của đầu việc ("nhịp").
    assert kq_tinh.don_vi_pay == cv.don_vi_ra

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    rows = ProductionOutputRepository(db).list_nguoi_by_period(2026, 8)
    assert rows
    assert all(x.unit_price == 0.0 for x in rows)
    assert abs(sum(x.quantity for x in rows) - 100.0) < 1e-6


def test_module_phan_bo_khong_con_ham_don_gia():
    assert not hasattr(phan_bo, "_don_gia_don_vi")


def test_don_vi_chia_la_don_vi_RA_cua_buoc(db, orders, lsx_svc, admin, customer):
    """Đơn vị của sản lượng đem chia = đơn vị RA của bước (thứ `batch.tot` đếm), KHÔNG phải đơn vị
    TIỀN của đầu việc.

    Giữ nhãn `nhịp` của đầu việc trong khi số lại đếm theo `tờ` là dán sai đơn vị lên sản lượng —
    tổ trưởng đối chiếu phiếu sẽ không hiểu con số ấy đếm cái gì.
    """
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-DV")
    cv.khoan_json = {"don_gia": 40, "don_vi": "nhịp",
                     "cong_thuc": "50000 + don_gia_khoan * sl_ra", "don_gia_hd": 620.0}
    db.commit()
    e = _emp(db, to, "NV-PB-DV")
    _cham_cong(db, e)
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    header = db.get(SanXuatPhanBo, kq["phan_bo_id"])
    assert header.don_vi_tra_luong == "tờ"


# --- §7.3 Thiếu chấm công + loại trừ khỏi lương batch ---------------------------------------
def test_thieu_cham_cong_chan_chot(db, orders, lsx_svc, admin, customer):
    """Tham gia trong cửa sổ batch nhưng KHÔNG có chấm công hợp lệ ⇒ 0 phút hợp lệ ⇒ cờ 'thiếu chấm
    công' nổi, giữ phân bổ ở NHÁP (vẫn ghi nhận sản xuất) và chặn chốt cho tới khi xử lý."""
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-CC")
    e = _emp(db, to, "NV-PB-CC")                                       # tham gia nhưng KHÔNG chấm công
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    assert kq["can_chot"] is False and kq["canh_bao"]
    assert e.id in kq["thieu_cham_cong"]
    with pytest.raises(ValueError):
        phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])


def test_loai_tru_khoi_luong_go_chan_va_chia_lai(db, orders, lsx_svc, admin, customer):
    """Xác nhận người thiếu chấm công KHỎI lương batch kèm lý do ⇒ cờ chặn của họ tan, phần của họ
    chia lại cho người còn lại, và phân bổ chốt được (§7.3 nhánh 'loại trừ có audit')."""
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-LT")
    e1 = _emp(db, to, "NV-LT-1")                                       # có chấm công
    e2 = _emp(db, to, "NV-LT-2")                                       # thiếu chấm công
    _cham_cong(db, e1)
    db.commit()
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    assert kq["can_chot"] is False and e2.id in kq["thieu_cham_cong"]

    with pytest.raises(ValueError):                                    # lý do rỗng bị chặn
        phan_bo.loai_tru_khoi_phan_bo(
            db, user=admin, batch_id=batch.id, employee_id=e2.id, ly_do="  ",
        )

    r = phan_bo.loai_tru_khoi_phan_bo(
        db, user=admin, batch_id=batch.id, employee_id=e2.id, ly_do="Nghỉ, không chấm công",
    )
    assert r["can_chot"] is True and r["thieu_cham_cong"] == [] and r["loai_tru"] == [e2.id]

    dong = phan_bo.SanXuatPhanBoRepository(db).cac_dong(kq["phan_bo_id"])
    theo_nv = {d.employee_id: float(d.so_luong_tra_luong) for d in dong}
    assert e2.id not in theo_nv                                        # người bị loại không có dòng
    assert abs(theo_nv[e1.id] - 100.0) < 1e-6                          # phần của e2 dồn hết cho e1

    r2 = phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    assert r2["trang_thai"] == "finalized"


def test_go_loai_tru_khoi_phuc_chan(db, orders, lsx_svc, admin, customer):
    """Gỡ loại trừ ⇒ người đó quay lại vòng chia, cờ thiếu chấm công nổi lại; gỡ lần hai (không còn) báo lỗi."""
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-GLT")
    e = _emp(db, to, "NV-GLT")                                         # thiếu chấm công
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    phan_bo.loai_tru_khoi_phan_bo(
        db, user=admin, batch_id=batch.id, employee_id=e.id, ly_do="Loại tạm",
    )
    r = phan_bo.go_loai_tru(db, user=admin, batch_id=batch.id, employee_id=e.id)
    assert r["can_chot"] is False and e.id in r["thieu_cham_cong"] and r["loai_tru"] == []
    with pytest.raises(ValueError):                                    # đã gỡ rồi, không còn để gỡ
        phan_bo.go_loai_tru(db, user=admin, batch_id=batch.id, employee_id=e.id)


# --- Mở lại + bù trừ (§12.3) ----------------------------------------------------------------
def _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, ma):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma=ma)
    e = _emp(db, to, f"NV-{ma}")
    _cham_cong(db, e)
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()
    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    return to, cv, batch, e, kq["phan_bo_id"]


def test_mo_lai_khong_con_doi_ly_do(db, orders, lsx_svc, admin, customer):
    """Danh mục Lý do & lỗi SX ĐÃ GỠ (mg 0288) ⇒ mở lại phân bổ đã chốt không còn phải nêu lý do:
    gọi trần vẫn mở được."""
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "ML")
    r = phan_bo.mo_lai_phan_bo(db, user=admin, phan_bo_id=pb_id)
    assert r["trang_thai"] == "reopened"


def test_ky_khoa_khong_mo_lai_duoc(db, orders, lsx_svc, admin, customer):
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "KHOA")
    db.add(PayrollPeriod(year=2026, month=8, status=PERIOD_LOCKED))    # kỳ gốc đã khoá
    db.commit()
    with pytest.raises(ValueError):
        phan_bo.mo_lai_phan_bo(db, user=admin, phan_bo_id=pb_id)


def test_bu_tru_sau_khoa_ky_feed_ky_bu(db, orders, lsx_svc, admin, customer):
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "BT")
    db.add(PayrollPeriod(year=2026, month=8, status=PERIOD_LOCKED))    # kỳ gốc khoá, kỳ 9 còn mở
    db.commit()

    r = phan_bo.bu_tru(
        db, user=admin, batch_id=batch.id, employee_id=e.id,
        so_luong_tra_luong=-5, ky_bu_nam=2026, ky_bu_thang=9,
        mo_ta="Trừ do đếm dư",
    )
    assert r["ky_bu"] == [2026, 9] and r["so_luong_tra_luong"] == -5

    rows = ProductionOutputRepository(db).list_nguoi_by_period(2026, 9)
    assert any(abs(x.quantity + 5.0) < 1e-6 and x.employee_id == e.id for x in rows)


def test_bu_tru_ky_goc_chua_khoa_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "BT2")
    with pytest.raises(ValueError):                                    # kỳ gốc chưa khoá ⇒ mở lại
        phan_bo.bu_tru(
            db, user=admin, batch_id=batch.id, employee_id=e.id,
            so_luong_tra_luong=3, ky_bu_nam=2026, ky_bu_thang=9,
        )


# --- Thang giờ của cửa sổ mẻ (mg 0298) ------------------------------------------------------
def test_moc_tu_client_quy_gio_tuong_ve_utc_that():
    """Ô `datetime-local` gửi chuỗi KHÔNG offset ⇒ Pydantic dựng datetime NAIVE = giờ TƯỜNG xưởng.

    Dán thẳng nhãn UTC lên đó là lệch đúng bằng offset máy chủ. `moc_tu_client` phải đọc nó như giờ
    địa phương rồi quy về UTC thật; mốc ĐÃ kèm offset thì giữ nguyên thời điểm."""
    from app.services.gio_xuong import moc_tu_client

    naive = datetime(2026, 9, 11, 21, 47)
    assert moc_tu_client(naive) == naive.astimezone().astimezone(timezone.utc)
    assert moc_tu_client(naive).tzinfo is timezone.utc

    aware = datetime(2026, 9, 11, 21, 47, tzinfo=VN_TZ)
    assert moc_tu_client(aware) == aware                     # cùng thời điểm, chỉ đổi nhãn
    assert moc_tu_client(None) is None


def test_me_go_gio_tuong_van_giao_duoc_voi_cham_cong(db, orders, lsx_svc, admin, customer):
    """HỒI QUY 11/09/2026 — mẻ gõ giờ tường KHÔNG được làm cổng §7.3 ra 0 phút.

    Trước mg 0298 cửa sổ mẻ nằm ở thang LỊCH (giờ tường dán nhãn UTC) còn khoảng tham gia và chấm
    công ở UTC THẬT ⇒ giao nhau RỖNG ⇒ cờ `thieu_cham_cong` chặn Chốt dù tổ chấm công đủ."""
    to, cv, _b = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-TZ")
    # 14:00–15:00 giờ VN ngày _NGAY — nằm gọn trong ca HC-PB 08:00–17:00 của `_cham_cong`.
    dau_utc = datetime(_NGAY.year, _NGAY.month, _NGAY.day, 14, 0, tzinfo=VN_TZ).astimezone(timezone.utc)
    cuoi_utc = dau_utc + timedelta(hours=1)
    # Đúng thứ trình duyệt gửi lên: giờ TƯỜNG của máy chủ tại hai mốc ấy, bỏ tzinfo.
    dau_go = dau_utc.astimezone().replace(tzinfo=None)
    cuoi_go = cuoi_utc.astimezone().replace(tzinfo=None)

    r = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=dau_go, ket_thuc=cuoi_go, tong=100.0, tot=100.0,
    )
    batch = db.get(SanXuatBatch, r["batch_id"])
    assert _utc(batch.bat_dau) == dau_utc and _utc(batch.ket_thuc) == cuoi_utc

    e = _emp(db, to, "NV-PB-TZ")
    _cham_cong(db, e)
    db.commit()
    _khoang(db, cv, e, dau_utc, cuoi_utc)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    assert kq["thieu_cham_cong"] == [] and kq["can_chot"] is True
    dong = SanXuatPhanBoRepository(db).cac_dong(kq["phan_bo_id"])
    assert [float(d.phut_thuc_te) for d in dong] == [60.0]
    header = db.get(SanXuatPhanBo, kq["phan_bo_id"])
    assert header.ngay == _NGAY                              # ngày theo giờ xưởng, không phải ngày UTC


def test_nhieu_me_dung_chung_bo_nho_ra_dung_so_va_me_sau_khong_hoi_db(
    db, orders, lsx_svc, admin, customer,
):
    """Drawer tính N mẻ của một công việc bằng MỘT `BoNhoTinhMe` — đo 16/09/2026 mẻ 2 và 3 hỏi lại y
    hệt mẻ 1 (33/70 truy vấn của drawer). Số của từng mẻ phải trùng khi tính riêng, và mẻ sau CÙNG
    NGÀY không được chạm DB lần nào."""
    from sqlalchemy import event

    to, cv, b1 = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-BN")
    cac_me = [b1]
    # b2 16–17h VN còn trong ca HC-PB; b3 17–18h VN ngoài ca ⇒ 0 phút hợp lệ ⇒ nhánh thiếu chấm công.
    for gio in (1, 2):
        r = san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0 + timedelta(hours=gio),
            ket_thuc=_T0 + timedelta(hours=gio + 1), tong=100.0, tot=100.0,
        )
        cac_me.append(db.get(SanXuatBatch, r["batch_id"]))
    e1 = _emp(db, to, "NV-BN-1")
    e2 = _emp(db, to, "NV-BN-2")
    _cham_cong(db, e1)
    _cham_cong(db, e2)
    db.commit()
    _khoang(db, cv, e1, _T0, _T0 + timedelta(hours=3))
    _khoang(db, cv, e2, _T0, _T0 + timedelta(hours=3))
    db.commit()
    phan_bo.loai_tru_khoi_phan_bo(
        db, user=admin, batch_id=cac_me[1].id, employee_id=e2.id, ly_do="Sang tổ khác",
    )

    def _so(kq):
        return (kq.dong, kq.can_chot, kq.canh_bao, kq.thieu_cham_cong, kq.loai_tru, kq.p_percent)

    pb = SanXuatPhanBoRepository(db)
    rieng = [_so(phan_bo._tinh_batch(db, cv, b, pb)) for b in cac_me]
    # Đủ các nhánh thì bài mới nói được gì: chia theo phút, có loại trừ, có thiếu chấm công.
    assert rieng[0][0] and rieng[1][4] == [e2.id] and rieng[2][3] == sorted([e1.id, e2.id])

    bn = phan_bo.BoNhoTinhMe(db, cv, pb, batch_ids=[b.id for b in cac_me])
    chung = [_so(phan_bo._tinh_batch(db, cv, cac_me[0], pb, bn))]
    so_sql: list[str] = []

    def _dem(conn, cursor, statement, *_a):
        so_sql.append(statement)

    eng = db.get_bind()
    event.listen(eng, "before_cursor_execute", _dem)
    try:
        chung += [_so(phan_bo._tinh_batch(db, cv, b, pb, bn)) for b in cac_me[1:]]
    finally:
        event.remove(eng, "before_cursor_execute", _dem)
    assert chung == rieng
    assert so_sql == []


def test_bo_nho_tinh_me_khong_nhan_cong_viec_khac(db, orders, lsx_svc, admin, customer):
    to, cv, b1 = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-BN2")
    pb = SanXuatPhanBoRepository(db)
    bn = phan_bo.BoNhoTinhMe(db, SimpleNamespace(id=cv.id + 999), pb)
    with pytest.raises(ValueError):
        phan_bo._tinh_batch(db, cv, b1, pb, bn)


def test_khoang_co_mat_nap_ca_ca_dai_khop_tra_tung_ngay(db, orders, lsx_svc, admin, customer):
    """`khoang_co_mat_hop_le` nạp ca của cả dải trong hai truy vấn thay vì tra từng ngày — đáp án
    từng ngày phải y `shift_id_on`: trước mốc đầu tiên là chưa có ca (dù `default_shift_id` có),
    ô lưới đè mốc, ô nghỉ trong suốt."""
    from app.models.employee import EmployeeShiftAssignment, EmployeeShiftDay
    from app.repositories.employee_repo import EmployeeRepository

    to, _cv, _b = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-CA")
    e = _emp(db, to, "NV-PB-CA")
    ca_a = WorkShift(name="CA-A-PB", start_minute=480, end_minute=1020, is_overnight=False)
    ca_b = WorkShift(name="CA-B-PB", start_minute=1320, end_minute=360, is_overnight=True)
    db.add_all([ca_a, ca_b])
    db.flush()
    e.default_shift_id = ca_b.id
    db.add(EmployeeShiftAssignment(
        employee_id=e.id, shift_id=ca_a.id, effective_from=_NGAY - timedelta(days=1)))
    db.add(EmployeeShiftDay(employee_id=e.id, work_date=_NGAY, shift_id=ca_b.id, is_off=False))
    db.add(EmployeeShiftDay(
        employee_id=e.id, work_date=_NGAY + timedelta(days=1), shift_id=None, is_off=True))
    db.commit()

    att = phan_bo._attendance(db)

    def _cam(*_a, **_k):
        raise AssertionError("ca phải lấy từ bản nạp sẵn, không tra lẻ từng ngày")

    att.employees.shift_id_on = _cam
    att.khoang_co_mat_hop_le(e, _T0, _T0 + timedelta(hours=1))

    repo = EmployeeRepository(db)
    ngay = [_NGAY + timedelta(days=i) for i in range(-3, 3)]   # [đầu − 2, cuối + 1] quanh _NGAY ± 1
    assert {d: att._shift_id_cache[(e.id, d)] for d in ngay} == {d: repo.shift_id_on(e, d) for d in ngay}
    assert att._shift_id_cache[(e.id, _NGAY - timedelta(days=2))] is None      # trước mốc
    assert att._shift_id_cache[(e.id, _NGAY)] == ca_b.id                        # ô lưới đè mốc
    assert att._shift_id_cache[(e.id, _NGAY + timedelta(days=1))] == ca_a.id    # ô nghỉ trong suốt
