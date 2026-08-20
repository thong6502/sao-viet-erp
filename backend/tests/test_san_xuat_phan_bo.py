"""Thực hiện sản xuất — Giai đoạn 4: HỖ TRỢ CHÉO (§9) + PHÂN BỔ SẢN LƯỢNG → lương khoán (§12).

Soi thẳng tầng service (nơi chứa LUẬT), không qua HTTP:
  · Hỗ trợ chéo: tỷ lệ do người nhập, cần HAI tổ trưởng xác nhận, trần tổng ≤ 100% cùng công đoạn +
    ngày; huỷ giữ dòng đổi trạng thái.
  · Phân bổ: quy đổi bản địa↔trả lương ĐỒNG NHẤT; người hỗ trợ nhận đúng tỷ lệ (ghi cho tổ gốc); phần
    còn lại chia theo phút × hệ số bậc ẢNH CHỤP; Σ khớp Q chính xác; thiếu hệ số/trọng số hoặc bàn
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
from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_ly_do import (
    NHOM_MO_LAI_PHAN_BO,
    NHOM_TAM_DUNG,
    SanXuatLyDo,
)
from app.models.san_xuat_san_luong import SanXuatBanGiao, SanXuatBatch
from app.models.san_xuat_thuc_thi import SanXuatKhoangThamGia
from app.models.user import User
from app.repositories.production_output_repo import ProductionOutputRepository
from app.services.attendance_service import VN_TZ
from app.services.san_xuat import ho_tro, phan_bo, san_luong

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


def _ly_do_mo_lai(db, ma="ML-1", ten="Sửa sai sản lượng") -> SanXuatLyDo:
    ld = SanXuatLyDo(ma=ma, nhom=NHOM_MO_LAI_PHAN_BO, ten=ten)
    db.add(ld)
    db.flush()
    return ld


def _khoang(db, cv, emp, bat_dau, ket_thuc, heso) -> SanXuatKhoangThamGia:
    """Khoảng tham gia dựng thẳng với hệ số bậc ẢNH CHỤP (engine đọc để chia trọng số §12.2)."""
    k = SanXuatKhoangThamGia(
        cong_viec_id=cv.id, phien_chay_id=1, employee_id=emp.id,
        bat_dau=bat_dau, ket_thuc=ket_thuc, output_coefficient=heso,
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
    """Tổ khoán (admin làm tổ trưởng) + công việc ĐANG CHẠY có đơn giá + một batch sản lượng tốt."""
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
    """Tổ thực hiện (admin làm tổ trưởng) + tổ gốc (tổ trưởng khác) + một người hỗ trợ thuộc tổ gốc."""
    to_th, cv, _batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-TH")
    u_goc = _user(db, "to_truong_goc")
    to_goc = Department(
        name="Tổ Gốc", code="TO-GOC", la_san_xuat=True,
        has_piece_work=True, head_user_id=u_goc.id,
    )
    db.add(to_goc)
    db.flush()
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
    assert r["trang_thai"] == "pending_both"          # mới xác nhận bên thực hiện (admin)
    assert r["to_goc_id"] == to_goc.id and r["to_thuc_hien_id"] == to_th.id

    r2 = ho_tro.xac_nhan_ho_tro(db, user=u_goc, ho_tro_id=r["ho_tro_id"])
    assert r2["trang_thai"] == "confirmed"            # đủ hai tổ trưởng
    assert set(r2["notify_user_ids"]) == {admin.id, u_goc.id}


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


def test_khong_phai_to_truong_khong_de_xuat_duoc(db, orders, lsx_svc, admin, customer):
    _to_th, cv, _to_goc, _u_goc, emp = _canh_ho_tro(db, orders, lsx_svc, admin, customer)
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        ho_tro.de_xuat_ho_tro(
            db, user=nguoi_la, cong_viec_id=cv.id, employee_id=emp.id,
            ngay_lam_viec=_NGAY, ty_le_phan_tram=10,
        )


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


# --- Phân bổ: chia theo phút × hệ số (§12.2) ------------------------------------------------
def test_tinh_chia_theo_phut_va_he_so(db, orders, lsx_svc, admin, customer):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer)
    e1 = _emp(db, to, "NV-PB-1")
    e2 = _emp(db, to, "NV-PB-2")
    _cham_cong(db, e1)
    _cham_cong(db, e2)
    db.commit()
    # Cùng 60 phút trong cửa sổ batch; e2 hệ số gấp đôi ⇒ nhận nhiều hơn.
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc, heso=1.0)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc, heso=2.0)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    assert kq["can_chot"] is True and kq["so_dong"] == 2
    assert kq["trang_thai"] == "draft"

    dong = phan_bo.SanXuatPhanBoRepository(db).cac_dong(kq["phan_bo_id"])
    tong = sum(float(d.so_luong_tra_luong) for d in dong)
    assert abs(tong - 100.0) < 1e-6                                    # Σ khớp Q chính xác
    theo_nv = {d.employee_id: float(d.so_luong_tra_luong) for d in dong}
    assert theo_nv[e2.id] > theo_nv[e1.id]                             # hệ số cao ⇒ phần lớn hơn


def test_thieu_he_so_chan_chot(db, orders, lsx_svc, admin, customer):
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-HS")
    e = _emp(db, to, "NV-PB-NOHS")
    _cham_cong(db, e)                                                  # có chấm công → cô lập đúng lỗi hệ số
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc, heso=None)       # chưa gán hệ số bậc
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    assert kq["can_chot"] is False and kq["canh_bao"]                  # nháp vẫn ra, nhưng chặn chốt
    with pytest.raises(ValueError):
        phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])


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
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc, heso=1.0)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc, heso=1.0)
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
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc, heso=1.0)
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
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc, heso=1.0)
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
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc, heso=1.0)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc, heso=1.0)
    db.commit()

    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    r = phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    assert r["trang_thai"] == "finalized"

    rows = ProductionOutputRepository(db).list_nguoi_by_period(2026, 8)
    assert rows and all(x.tinh_khoan for x in rows)
    assert abs(sum(x.quantity for x in rows) - 100.0) < 1e-6           # feed đúng tổng Q
    assert all(abs(x.unit_price - 10.0) < 1e-9 for x in rows)          # đơn giá ẢNH CHỤP


# --- §7.3 Thiếu chấm công + loại trừ khỏi lương batch ---------------------------------------
def test_thieu_cham_cong_chan_chot(db, orders, lsx_svc, admin, customer):
    """Tham gia trong cửa sổ batch nhưng KHÔNG có chấm công hợp lệ ⇒ 0 phút hợp lệ ⇒ cờ 'thiếu chấm
    công' nổi, giữ phân bổ ở NHÁP (vẫn ghi nhận sản xuất) và chặn chốt cho tới khi xử lý."""
    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-PB-CC")
    e = _emp(db, to, "NV-PB-CC")                                       # tham gia nhưng KHÔNG chấm công
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc, heso=1.0)
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
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc, heso=1.0)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc, heso=1.0)
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
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc, heso=1.0)
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
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc, heso=1.0)
    db.commit()
    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    return to, cv, batch, e, kq["phan_bo_id"]


def test_mo_lai_can_ly_do_dung_nhom(db, orders, lsx_svc, admin, customer):
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "ML")
    sai = SanXuatLyDo(ma="TD-X", nhom=NHOM_TAM_DUNG, ten="Chờ mực")
    db.add(sai)
    db.flush()
    with pytest.raises(ValueError):
        phan_bo.mo_lai_phan_bo(db, user=admin, phan_bo_id=pb_id, ly_do_id=sai.id)

    dung = _ly_do_mo_lai(db)
    r = phan_bo.mo_lai_phan_bo(db, user=admin, phan_bo_id=pb_id, ly_do_id=dung.id)
    assert r["trang_thai"] == "reopened"


def test_ky_khoa_khong_mo_lai_duoc(db, orders, lsx_svc, admin, customer):
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "KHOA")
    db.add(PayrollPeriod(year=2026, month=8, status=PERIOD_LOCKED))    # kỳ gốc đã khoá
    db.commit()
    dung = _ly_do_mo_lai(db)
    with pytest.raises(ValueError):
        phan_bo.mo_lai_phan_bo(db, user=admin, phan_bo_id=pb_id, ly_do_id=dung.id)


def test_bu_tru_sau_khoa_ky_feed_ky_bu(db, orders, lsx_svc, admin, customer):
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "BT")
    db.add(PayrollPeriod(year=2026, month=8, status=PERIOD_LOCKED))    # kỳ gốc khoá, kỳ 9 còn mở
    db.commit()
    dung = _ly_do_mo_lai(db)

    r = phan_bo.bu_tru(
        db, user=admin, batch_id=batch.id, employee_id=e.id,
        so_luong_tra_luong=-5, ky_bu_nam=2026, ky_bu_thang=9, ly_do_id=dung.id,
        mo_ta="Trừ do đếm dư",
    )
    assert r["ky_bu"] == [2026, 9] and r["so_luong_tra_luong"] == -5

    rows = ProductionOutputRepository(db).list_nguoi_by_period(2026, 9)
    assert any(abs(x.quantity + 5.0) < 1e-6 and x.employee_id == e.id for x in rows)


def test_bu_tru_ky_goc_chua_khoa_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv, batch, e, pb_id = _chot_mot_phan_bo(db, orders, lsx_svc, admin, customer, "BT2")
    dung = _ly_do_mo_lai(db)
    with pytest.raises(ValueError):                                    # kỳ gốc chưa khoá ⇒ mở lại
        phan_bo.bu_tru(
            db, user=admin, batch_id=batch.id, employee_id=e.id,
            so_luong_tra_luong=3, ky_bu_nam=2026, ky_bu_thang=9, ly_do_id=dung.id,
        )
