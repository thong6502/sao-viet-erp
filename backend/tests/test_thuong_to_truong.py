"""Thưởng/phạt TỔ TRƯỞNG theo chất lượng — nối bảng bậc vào luồng sản xuất (chủ 04/09/2026).

Trước hôm nay `PieceWorkService.leader_bonus_pct/_amount` tính đúng nhưng KHÔNG AI GỌI: bảng bậc
khai xong nằm im, tổ trưởng không nhận đồng nào. File này soi đúng đoạn dây vừa nối:

  · đóng nhóm thành phẩm ⇒ ghi dòng ± cho tổ trưởng, số liệu SNAPSHOT (sản lượng · tiền khoán ·
    số lỗi · tỷ lệ lỗi · % bậc trúng);
  · tỷ lệ lỗi lấy từ PHIẾU KCS, chỉ đếm lỗi tổ đã nhận (`accepted`) hoặc ghi một chiều
    (`recorded`) — `rejected` KHÔNG tính (model KCS ghi rõ "không quy trách nhiệm");
  · ghi MỘT LẦN: gọi lại không đẻ dòng thứ hai, sửa bậc sau đó không nắn số đã ghi;
  · kỳ lương đã khoá ⇒ đẩy sang kỳ mở kế tiếp chứ không ném tiền vào kỳ đã chi;
  · tới bảng lương qua CỘT RIÊNG `payroll_lines.thuong_to_truong` — phải là cột riêng vì phần
    PHẠT âm, mà `khoan_map` sàn mỗi phiếu ở `max(0, …)` nên đi nhờ cột `khoan` là mất tiền phạt.

Dàn cảnh tái dùng nguyên cây fixture của Thực hiện SX (đơn → SX → phát hành → batch KCS).
"""
from __future__ import annotations

from datetime import date

from app.models.payroll import PERIOD_LOCKED, PayrollPeriod
from app.models.piece_work import PieceLeaderBonusBracket
from app.models.employee import Employee
from app.models.san_xuat import CV_HOAN_THANH, NHOM_DONG_DU
from app.models.san_xuat_kcs import TN_CHAP_NHAN, TN_RECORDED, TN_TU_CHOI, SanXuatKcsLoi
from app.models.san_xuat_phan_bo import PB_DA_CHOT, PB_NHAP, SanXuatPhanBo, SanXuatPhanBoDong
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.san_xuat_thuong_to_truong import SanXuatThuongToTruong
from app.models.user import User
from app.repositories.san_xuat_repo import SanXuatRepository
from app.services.san_xuat import dong_nhom, thuong_to_truong

# Fixtures + helper luồng thật (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)
from tests.test_san_xuat_thuc_thi import _emp  # noqa: F401

_NGAY = date.today()

# Bộ bậc mẫu chính là bảng trong docstring của `PieceLeaderBonusBracket`, rút gọn còn khoảng
# 0–5.000 (đủ soi cả thưởng lẫn phạt mà không phải dựng sản lượng lớn).
_BAC_MAU = [
    (0, 5000, 5, 5.0),        # lỗi ≤ 5%  ⇒ +5%
    (0, 5000, None, -5.0),    # lỗi > 5%  ⇒ −5%
]


def _bac(db, department_id: int, rows=_BAC_MAU) -> None:
    for i, (tu, den, tran, pct) in enumerate(rows, start=1):
        db.add(PieceLeaderBonusBracket(
            department_id=department_id, seq=i,
            sl_tu=tu, sl_den=den, up_to_defect_pct=tran, rate_pct=pct,
        ))
    db.flush()


def _phan_bo(db, cv, emp, *, sl, don_gia, trang_thai=PB_DA_CHOT, dept_id=None):
    """Một header phân bổ + một dòng theo người, dựng thẳng ORM.

    Không đi qua `phan_bo.tinh/chot` vì test này soi tầng THƯỞNG, không soi phép chia sản lượng —
    cái đó đã có `test_san_xuat_phan_bo.py` lo. Chỉ cần đúng SHAPE mà repo thưởng đọc."""
    batch = (
        db.query(SanXuatBatch)
        .filter_by(cong_viec_id=cv.id)
        .order_by(SanXuatBatch.id)
        .first()
    )
    assert batch is not None, "dàn cảnh KCS phải để lại batch sản lượng"
    pb = SanXuatPhanBo(
        batch_id=batch.id, cong_viec_id=cv.id, ngay=_NGAY,
        ky_nam=_NGAY.year, ky_thang=_NGAY.month, trang_thai=trang_thai,
        q_tra_luong=sl, don_gia=don_gia,
    )
    db.add(pb)
    db.flush()
    db.add(SanXuatPhanBoDong(
        phan_bo_id=pb.id, employee_id=emp.id,
        department_id=dept_id if dept_id is not None else cv.department_id,
        ngay=_NGAY, so_luong_tra_luong=sl, don_gia=don_gia,
    ))
    db.flush()
    return pb


def _loi(db, res, *, so_luong, to_chiu_id, trang_thai=TN_CHAP_NHAN):
    db.add(SanXuatKcsLoi(
        kcs_batch_id=res["kcs_batch_id"], so_luong=so_luong,
        to_chiu_id=to_chiu_id, trang_thai=trang_thai,
    ))
    db.flush()


def _emp_cua(db, dept, user, ma="NV-TT"):
    """Hồ sơ nhân sự của một tài khoản, TÁI DÙNG nếu seed đã tạo sẵn (`employees.user_id` UNIQUE)."""
    e = db.query(Employee).filter_by(user_id=user.id).first()
    if e is None:
        return _emp(db, dept, ma, ten="Tổ trưởng", user_id=user.id)
    e.department_id = dept.id
    db.flush()
    return e


def _user_khong_ho_so(db, username):
    """Một tài khoản CHƯA có hồ sơ nhân sự — seed đã nối sẵn `admin` nên phải dựng user riêng."""
    u = User(username=username, name="Tổ trưởng chưa nối", password_hash="x")
    db.add(u)
    db.flush()
    return u


def _hoan_thanh_het(db, nhom_id):
    for cv in SanXuatRepository(db).cong_viec_hien_tai_cua_nhom(nhom_id):
        cv.trang_thai = CV_HOAN_THANH
    db.commit()


def _canh(db, orders, lsx_svc, admin, customer, *, sl=5000, don_gia=300, loi=150,
          trang_thai_loi=TN_CHAP_NHAN, bac=_BAC_MAU, ma="TO-TT-THUONG"):
    """Tổ khoán (admin làm tổ trưởng) làm `sl` sản phẩm đơn giá `don_gia`, dính `loi` hàng lỗi."""
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, ma=ma)
    emp = _emp_cua(db, to, admin)
    if bac:
        _bac(db, to.id, bac)
    _phan_bo(db, cv, emp, sl=sl, don_gia=don_gia)
    if loi:
        _loi(db, res, so_luong=loi, to_chiu_id=to.id, trang_thai=trang_thai_loi)
    db.commit()
    return to, cv, res, emp


# --- Phép tính ------------------------------------------------------------------------------
def test_dung_con_so_chu_neu_5000_sp_don_gia_300_loi_3pct(db, orders, lsx_svc, admin, customer):
    """⭐ Ví dụ chủ chốt: lệnh 5.000 sản phẩm, đơn giá khoán 300đ, lỗi 3% ⇒ +5% = **+75.000đ**."""
    to, cv, _res, _emp1 = _canh(db, orders, lsx_svc, admin, customer)

    d = thuong_to_truong.tinh(db, cv.nhom_id)
    assert len(d) == 1, d
    row = d[0]
    assert row["department_id"] == to.id
    assert row["san_luong"] == 5000
    assert row["tien_khoan"] == 1_500_000
    assert row["so_luong_loi"] == 150
    assert row["ty_le_loi"] == 3.0
    assert row["rate_pct"] == 5.0
    assert row["so_tien"] == 75_000


def test_loi_vuot_tran_thi_RA_SO_AM(db, orders, lsx_svc, admin, customer):
    """Bậc phạt phải ra tiền ÂM — nếu ở đâu đó bị kẹp về 0 thì cả nửa bảng bậc thành trang trí."""
    _to, cv, _res, _e = _canh(db, orders, lsx_svc, admin, customer, loi=400)   # 8% > 5%

    row = thuong_to_truong.tinh(db, cv.nhom_id)[0]
    assert row["ty_le_loi"] == 8.0
    assert row["rate_pct"] == -5.0
    assert row["so_tien"] == -75_000


def test_loi_TU_CHOI_khong_tinh_vao_ty_le(db, orders, lsx_svc, admin, customer):
    """`rejected` = tổ từ chối, model KCS ghi rõ "không quy trách nhiệm" — đếm vào là phạt oan."""
    _to, cv, _res, _e = _canh(db, orders, lsx_svc, admin, customer,
                              loi=400, trang_thai_loi=TN_TU_CHOI)

    row = thuong_to_truong.tinh(db, cv.nhom_id)[0]
    assert row["so_luong_loi"] == 0
    assert row["ty_le_loi"] == 0
    assert row["so_tien"] == 75_000


def test_loi_GHI_MOT_CHIEU_van_tinh(db, orders, lsx_svc, admin, customer):
    """`recorded` (KCS kiêm nhiệm ghi thẳng, mg 0250) vẫn là lỗi của tổ — bỏ qua là thủng nửa nguồn."""
    _to, cv, _res, _e = _canh(db, orders, lsx_svc, admin, customer,
                              loi=400, trang_thai_loi=TN_RECORDED)

    assert thuong_to_truong.tinh(db, cv.nhom_id)[0]["rate_pct"] == -5.0


def test_phan_bo_CHUA_CHOT_thi_khong_tinh(db, orders, lsx_svc, admin, customer):
    """Phân bổ nháp thì công nhân còn chưa xem được — lấy nó phát thưởng là chạy trước cả lương."""
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, ma="TO-TT-NHAP")
    emp = _emp_cua(db, to, admin, ma="NV-TT2")
    _bac(db, to.id)
    _phan_bo(db, cv, emp, sl=5000, don_gia=300, trang_thai=PB_NHAP)
    _loi(db, res, so_luong=150, to_chiu_id=to.id)
    db.commit()

    assert thuong_to_truong.tinh(db, cv.nhom_id) == []


def test_to_CHUA_KHAI_BAC_thi_khong_co_dong_va_khong_loi(db, orders, lsx_svc, admin, customer):
    """Kho/KCS… vốn không nằm trong chính sách này — không dòng, không lỗi, không cảnh báo."""
    _to, cv, _res, _e = _canh(db, orders, lsx_svc, admin, customer, bac=None, ma="TO-TT-NOBAC")

    assert thuong_to_truong.tinh(db, cv.nhom_id) == []


# --- Ghi lúc đóng nhóm ----------------------------------------------------------------------
def test_dong_nhom_DU_thi_ghi_dong_thuong(db, orders, lsx_svc, admin, customer):
    """⭐ Lý do cả tính năng tồn tại: đóng nhóm xong là tiền tổ trưởng có VẾT, không phải chờ ai gõ."""
    to, cv, _res, emp = _canh(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)

    ket = dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin, su_kien="test")
    assert ket is not None and ket["trang_thai"] == NHOM_DONG_DU

    rows = db.query(SanXuatThuongToTruong).filter_by(nhom_id=cv.nhom_id).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.department_id == to.id
    assert r.head_user_id == admin.id
    assert r.employee_id == emp.id            # tổ trưởng đã nối hồ sơ nhân sự ⇒ lương nhận được
    assert float(r.san_luong) == 5000
    assert float(r.ty_le_loi) == 3.0
    assert float(r.rate_pct) == 5.0
    assert float(r.so_tien) == 75_000
    assert r.ky_nam == _NGAY.year and r.ky_thang == _NGAY.month
    assert r.ghi_chu is None


def test_ghi_lai_KHONG_de_dong_thu_hai(db, orders, lsx_svc, admin, customer):
    """Idempotent: cổng đóng nhóm là CHỐT CHẶN gọi sau nhiều thao tác — gọi trùng là chuyện thường."""
    _to, cv, _res, _e = _canh(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin)

    thuong_to_truong.ghi(db, nhom_id=cv.nhom_id, actor=admin)
    db.commit()
    assert db.query(SanXuatThuongToTruong).filter_by(nhom_id=cv.nhom_id).count() == 1


def test_sua_bac_SAU_khi_dong_khong_nan_lai_so_da_ghi(db, orders, lsx_svc, admin, customer):
    """Đóng băng như `san_xuat_phan_bo_dong`: bảng lương đã chốt không được đổi khi chủ sửa bậc."""
    to, cv, _res, _e = _canh(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin)

    db.query(PieceLeaderBonusBracket).filter_by(department_id=to.id).delete()
    _bac(db, to.id, [(0, 5000, None, -99.0)])
    db.commit()
    thuong_to_truong.ghi(db, nhom_id=cv.nhom_id, actor=admin)
    db.commit()

    r = db.query(SanXuatThuongToTruong).filter_by(nhom_id=cv.nhom_id).one()
    assert float(r.so_tien) == 75_000


def test_to_truong_CHUA_NOI_ho_so_van_ghi_dong_kem_ghi_chu(db, orders, lsx_svc, admin, customer):
    """Tiền không được bốc hơi im lặng: vẫn có dòng, chỉ là `employee_id` NULL + nói rõ vì sao."""
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, ma="TO-TT-CHUANOI")
    to.head_user_id = _user_khong_ho_so(db, "tt_chua_noi").id   # tổ trưởng KHÔNG có hồ sơ nhân sự
    emp = _emp(db, to, "NV-KHAC", ten="Thợ thường")
    _bac(db, to.id)
    _phan_bo(db, cv, emp, sl=5000, don_gia=300)
    _loi(db, res, so_luong=150, to_chiu_id=to.id)
    db.commit()
    _hoan_thanh_het(db, cv.nhom_id)
    dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin)

    r = db.query(SanXuatThuongToTruong).filter_by(nhom_id=cv.nhom_id).one()
    assert r.employee_id is None
    assert float(r.so_tien) == 75_000
    assert "chưa nối hồ sơ" in (r.ghi_chu or "")


def test_ky_luong_DA_KHOA_thi_day_sang_ky_mo_ke_tiep(db, orders, lsx_svc, admin, customer):
    """Kế toán khoá sổ rồi mà nhóm mới đóng: trả ở kỳ sau (lối bù trừ của §12.3), không mất tiền."""
    _to, cv, _res, _e = _canh(db, orders, lsx_svc, admin, customer)
    db.add(PayrollPeriod(year=_NGAY.year, month=_NGAY.month, status=PERIOD_LOCKED))
    db.commit()
    _hoan_thanh_het(db, cv.nhom_id)
    dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin)

    r = db.query(SanXuatThuongToTruong).filter_by(nhom_id=cv.nhom_id).one()
    sau = (_NGAY.year + 1, 1) if _NGAY.month == 12 else (_NGAY.year, _NGAY.month + 1)
    assert (r.ky_nam, r.ky_thang) == sau
    assert r.ngay == _NGAY                     # ngày đóng vẫn TRUNG THỰC, chỉ kỳ trả là dời
    assert "đã khoá" in (r.ghi_chu or "")


# --- Seam sang bảng lương -------------------------------------------------------------------
def test_repo_theo_ky_chi_tra_dong_CO_NGUOI_NHAN(db, orders, lsx_svc, admin, customer):
    """Dòng chưa nối hồ sơ nhân sự không được lọt vào bảng lương (không biết cộng cho ai)."""
    from app.repositories.thuong_to_truong_repo import ThuongToTruongRepository

    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, ma="TO-TT-KY")
    to.head_user_id = _user_khong_ho_so(db, "tt_ky").id
    emp = _emp(db, to, "NV-LAC", ten="Thợ thường")
    _bac(db, to.id)
    _phan_bo(db, cv, emp, sl=5000, don_gia=300)
    _loi(db, res, so_luong=150, to_chiu_id=to.id)
    db.commit()
    _hoan_thanh_het(db, cv.nhom_id)
    dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin)

    assert ThuongToTruongRepository(db).theo_ky(_NGAY.year, _NGAY.month) == []


# --- Vào bảng lương -------------------------------------------------------------------------
# Khối này đi qua HTTP `/api/luong/generate` (fixture `client`, DB seed riêng) nên KHÔNG dùng
# fixture `db` ở trên. Dòng thưởng dựng thẳng bằng ORM: phần "đóng nhóm sinh ra dòng" đã có các
# test phía trên soi, ở đây chỉ soi ĐOẠN CÒN LẠI — dòng đã có thì bảng lương có cộng đúng không.
from datetime import date as _date  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from tests.test_giao_hang_api import _admin, _tai_xe  # noqa: E402,F401


def _dong_thuong(employee_id: int, so_tien: float, *, ngay: _date) -> None:
    db = SessionLocal()
    try:
        db.add(SanXuatThuongToTruong(
            nhom_id=1, department_id=1, head_user_id=None, employee_id=employee_id,
            ngay=ngay, ky_nam=ngay.year, ky_thang=ngay.month,
            san_luong=5000, tien_khoan=1_500_000, so_luong_loi=150, ty_le_loi=3,
            rate_pct=5 if so_tien >= 0 else -5, so_tien=so_tien,
        ))
        db.commit()
    finally:
        db.close()


def _tinh_luong(client, h, eid: int) -> dict:
    hom_nay = _date.today()
    r = client.post("/api/luong/generate",
                    json={"year": hom_nay.year, "month": hom_nay.month}, headers=h)
    assert r.status_code in (200, 201), r.text
    return next(l for l in r.json()["lines"] if l["employee_id"] == eid)


def test_luong_CONG_thuong_to_truong_vao_dong_va_vao_gross(client):
    """⭐ Đích cuối: tiền thưởng phải RA bảng lương, đúng cột, và cộng vào tổng."""
    h = _admin(client)
    tt = _tai_xe("TT an thuong")
    _dong_thuong(tt, 75_000, ngay=_date.today())

    dong = _tinh_luong(client, h, tt)
    assert dong["thuong_to_truong"] == 75_000, dong["thuong_to_truong"]
    assert dong["gross"] >= 75_000, "thưởng tổ trưởng không vào gross"


def test_luong_GIU_NGUYEN_dau_am_cua_bac_phat(client):
    """⭐ Vì sao phải là CỘT RIÊNG: `khoan_map` sàn mỗi phiếu ở `max(0, …)` nên đi nhờ cột `khoan`
    là phần phạt biến mất im lặng. Cột riêng thì số âm còn nguyên và hiện rõ trên phiếu lương."""
    h = _admin(client)
    tt = _tai_xe("TT bi phat")
    _dong_thuong(tt, -75_000, ngay=_date.today())

    assert _tinh_luong(client, h, tt)["thuong_to_truong"] == -75_000


def test_luong_KY_KHAC_khong_lot_sang(client):
    """Dòng của kỳ khác không được cộng nhầm vào kỳ này (bẫy quen của mọi map theo kỳ)."""
    h = _admin(client)
    tt = _tai_xe("TT ky truoc")
    hom_nay = _date.today()
    truoc = _date(hom_nay.year - 1, hom_nay.month, 1)
    _dong_thuong(tt, 75_000, ngay=truoc)

    assert _tinh_luong(client, h, tt)["thuong_to_truong"] == 0
