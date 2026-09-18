"""Thực hiện sản xuất — Giai đoạn 2 mặt GHI: phân công · phiên chạy · khoảng tham gia (§7.1–§7.2).

Soi tầng service `services/san_xuat/thuc_thi.py` (nơi chứa LUẬT), không qua HTTP:
  · phân công snapshot cờ lương khoán từ `departments.has_piece_work`; bước nội bộ chỉ nhận khoán;
  · CỔNG GHI theo DÒNG QUYỀN THEO TỔ (mg 0302): phải có quyền Thực hiện lệnh trên tổ của công việc —
    dòng `all` ở nút cha ghi được tổ con, `department` chỉ phủ cây con của phòng mình, `own` chỉ ghi
    được việc ĐANG giao cho mình; có Xem mà thiếu Thực hiện lệnh thì bị chặn. `head_user_id` không
    còn cho quyền gì;
  · bắt đầu cần ≥1 thợ khoán, bắt đầu/kết thúc TRỄ cần lý do, một người không hai khoảng chồng giờ;
  · tạm dừng/kết thúc đóng phiên + mọi khoảng tham gia; version chống bấm trùng.

Một test API cuối chứng minh cổng router: admin seed (Giám đốc) không có dòng quyền theo tổ nào →
403; cấp Thực hiện lệnh ở một tổ thì qua cổng router.

Tái dùng luồng thật (đơn → SX → sẵn sàng → phát hành vào một tổ) từ test bàn tổ.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.department import Department
from app.models.employee import Employee
from app.models.role import SCOPE_DEPARTMENT, SCOPE_OWN
from app.models.user import User
from app.models.san_xuat import (
    BUOC_MAY,
    BUOC_TO,
    CV_DANG_CHAY,
    CV_HOAN_THANH,
    CV_TAM_DUNG,
    SanXuatCongViec,
)
from app.models.san_xuat_thuc_thi import (
    PC_DA_RUT,
    PC_HOAT_DONG,
    PHIEN_KET_THUC,
    PHIEN_TAM_DUNG,
    SanXuatKhoangThamGia,
    SanXuatPhanCong,
    SanXuatPhienChay,
)
from app.models.employee import STATUS_RESIGNED
from app.services.san_xuat import board, thuc_thi
from tests.quyen_to_fixtures import cap_quyen_to

# Fixtures luồng thật + helper phát hành vào một tổ (kéo theo cả cây fixture xếp lịch).
from tests.test_san_xuat_board import (  # noqa: F401
    _authz,
    _phat_hanh_vao_to,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


# --- Dàn cảnh dùng chung --------------------------------------------------------------------
def _to_khoan(db, admin, ma="TO-TT") -> Department:
    """Tổ sản xuất bật lương khoán, vai của admin được bật đủ quyền trên dòng tổ (để qua cổng ghi).

    `name` khai theo `ma` — `name` UNIQUE nên test gọi hàm này NHIỀU LẦN (2 tổ khác nhau trong
    cùng một test) phải truyền `ma` khác nhau, không thì đụng UNIQUE constraint."""
    d = Department(
        name=f"Tổ Thực Thi {ma}", code=ma, la_san_xuat=True,
        has_piece_work=True,
    )
    db.add(d)
    db.flush()
    cap_quyen_to(db, admin, d)
    return d


def _to_cong_nhat(db, ma="TO-CN") -> Department:
    d = Department(name="Tổ Công Nhật", code=ma, la_san_xuat=True, has_piece_work=False)
    db.add(d)
    db.flush()
    return d


def _emp(db, dept, ma, ten="Thợ", user_id=None) -> Employee:
    e = Employee(code=ma, full_name=ten, department_id=dept.id, user_id=user_id)
    db.add(e)
    db.flush()
    return e


def _cvs(db, to) -> list[SanXuatCongViec]:
    return (
        db.query(SanXuatCongViec)
        .filter_by(department_id=to.id)
        .order_by(SanXuatCongViec.id)
        .all()
    )


def _gan_giay_len_buoc(db, cv, *, dvt=None) -> None:
    """Gắn dòng GIẤY lên bước của công việc — từ 08/09/2026 đó là đường DUY NHẤT giấy vào nhu cầu.

    Trước đây bảng cân đối tự suy giấy từ `quy_cach_json.giay_id`, nên mọi fixture có quy cách là
    tự nhiên có nhu cầu giấy. Nay người lập kế hoạch phải chọn giấy ở khối vật tư của BƯỚC, và
    fixture phải làm đúng việc đó thì đường "tổ xin giấy" mới còn dữ liệu để chạy.

    Số lượng ghi bằng ĐVT GỐC của chính loại giấy, đúng như `LsxService._luong_vat_tu` ghi: tính
    ra kg trước (`so_to_nguyen × 0,08385` — một tờ 65×86 định lượng 150) rồi quy sang gốc bằng hệ
    số của DANH MỤC, không gõ cứng 1000 — giấy seed bán theo TẤN nên gõ cứng là lệch nghìn lần.
    Lệnh nào chưa có số tờ thì lấy 100 kg: các bài dùng helper này soi luật đề nghị/khoá/quyền,
    không soi con số giấy.

    `dvt` ép đơn vị ghi trên dòng (vd `"to"`) và ghi thẳng SỐ TỜ. Đây là trạng thái thật chứ không
    phải mẹo: `don_vi_snapshot` là ẢNH CHỤP lúc lưu bước, danh mục đổi ĐVT sau đó thì dòng cũ vẫn
    giữ đơn vị cũ — và đó là ca duy nhất còn để `dvt` khác `dvt_goc` ở tầng lệnh.
    """
    from app.models.lsx import Lsx, LsxCongDoanVatTu
    from app.models.vat_lieu_kho import GiayNguyen
    from app.repositories.don_vi_do_repo import DonViDoRepository
    from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from app.services.vat_lieu_kho_service import VatLieuKhoService

    lsx = db.get(Lsx, cv.lsx_id) if cv.lsx_id else None
    giay_id = (getattr(lsx, "quy_cach_json", None) or {}).get("giay_id") if lsx else None
    if not giay_id or not cv.lsx_cong_doan_id:
        return
    g = db.get(GiayNguyen, int(giay_id))
    if g is None:
        return
    kg = round(float(lsx.so_to_nguyen or 0) * 0.08385, 3) or 100.0
    hang = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    he_so_kg = next(
        (d["he_so_ve_goc"] for d in hang.don_vi_cua_mat_hang("giay", g.id)["ds"]
         if d["ma"] == "kg"), 1.0
    )
    don_vi = dvt or g.don_vi_gia or "kg"
    so_luong = ((float(lsx.so_to_nguyen or 0) or 1_000.0) if dvt
                else round(kg * float(he_so_kg or 1.0), 6))
    # GHI ĐÈ nếu bước đã có dòng giấy. Chuỗi fixture xếp lịch (`_hai_lsx_san_sang` → …
    # `_khai_giay_len_buoc_in`) cũng khai giấy lên bước In để lệnh giữ chỗ được, nên tới đây bước
    # thường ĐÃ có dòng — `db.add` thêm lần nữa là vỡ UNIQUE `(bước, hang_loai, hang_id)`. Ghi đè
    # chứ không bỏ qua: các bài dưới cần ĐÚNG số/ĐVT mà helper này đặt.
    cu = (
        db.query(LsxCongDoanVatTu)
        .filter_by(lsx_cong_doan_id=cv.lsx_cong_doan_id, hang_loai="giay", vat_tu_id=g.id)
        .first()
    )
    if cu is not None:
        cu.don_vi_snapshot = don_vi
        cu.so_luong = so_luong
    else:
        db.add(LsxCongDoanVatTu(
            lsx_cong_doan_id=cv.lsx_cong_doan_id, hang_loai="giay", vat_tu_id=g.id,
            vat_tu_ma_snapshot=g.ma, vat_tu_ten_snapshot=g.ten,
            don_vi_snapshot=don_vi, so_luong=so_luong,
            thu_tu=0, tu_dong=False,
        ))
    db.commit()


def _mot_cv(db, orders, lsx_svc, admin, customer, *, ma="TO-TT", giay_o_buoc=True, dvt_giay=None):
    """Một tổ khoán + một công việc BUOC_MAY không hạn dự kiến (khỏi vướng luật trễ)."""
    to = _to_khoan(db, admin, ma=ma)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv = _cvs(db, to)[0]
    cv.loai_buoc = BUOC_MAY
    cv.du_kien_bat_dau = None
    cv.du_kien_ket_thuc = None
    db.commit()
    if giay_o_buoc:
        _gan_giay_len_buoc(db, cv, dvt=dvt_giay)
    return to, cv


def _mo_khoang(db, cv):
    return db.query(SanXuatKhoangThamGia).filter_by(cong_viec_id=cv.id, ket_thuc=None).all()


# --- Phân công (§7.1) -----------------------------------------------------------------------
def test_phan_cong_snapshot_co_khoan_va_tiep_nhan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-1", user_id=None)     # thợ khoán, KHÔNG tài khoản
    truoc = cv.version

    res = thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)

    assert res["cong_viec_id"] == cv.id
    assert res["version"] == truoc + 1            # version bật để chống bấm trùng
    assert res["notify_user_id"] is None          # không tài khoản → không đẩy thông báo
    pcs = db.query(SanXuatPhanCong).filter_by(cong_viec_id=cv.id, trang_thai=PC_HOAT_DONG).all()
    assert len(pcs) == 1 and pcs[0].la_luong_khoan is True


def test_phan_cong_bao_notify_khi_co_tai_khoan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    u = User(username="tho_tt_2", name="Thợ Có Tài Khoản", password_hash="x")
    db.add(u)
    db.flush()
    e = _emp(db, to, "NV-TT-2", user_id=u.id)      # thợ CÓ tài khoản → phải đẩy thông báo
    res = thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    assert res["notify_user_id"] == u.id


def test_buoc_noi_bo_chi_nhan_tho_khoan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    cv.loai_buoc = BUOC_TO
    db.commit()
    cn = _emp(db, _to_cong_nhat(db), "NV-CN-1")    # tổ không khoán
    with pytest.raises(ValueError, match="là người công nhật — bước nội bộ không nhận người công nhật") as loi:
        thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=cn.id)
    assert "khoán" not in str(loi.value)                   # tổ không cần nghe chữ "khoán"


def test_khong_giao_trung_mot_nguoi(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-3")
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    with pytest.raises(ValueError):
        thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)


# --- Cổng ghi theo dòng quyền của tổ (mg 0302) ---------------------------------------------
def _user(db, username, dept=None) -> User:
    u = User(username=username, name=username, password_hash="x",
             department_id=dept.id if dept is not None else None)
    db.add(u)
    db.flush()
    return u


def test_gate_nguoi_khong_co_dong_quyen_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-4")
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)   # tài khoản không tồn tại → không dòng quyền nào
    with pytest.raises(PermissionError):
        thuc_thi.phan_cong(db, user=nguoi_la, cong_viec_id=cv.id, employee_id=e.id)


def test_gate_co_xem_thieu_thuc_hien_lenh_bi_chan(db, orders, lsx_svc, admin, customer):
    """Xem + Xác nhận sản lượng trọn tổ vẫn KHÔNG giao người được — giao/rút người là việc của quyền
    Thực hiện lệnh. Đứng tên trưởng tổ cũng không bù được ô quyền còn thiếu."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-XEM")
    u = _user(db, "chi_xem_tt", to)
    cap_quyen_to(db, u, to, viec=("confirm_output",))
    to.head_user_id = u.id
    db.commit()
    with pytest.raises(PermissionError, match="Thực hiện lệnh"):
        thuc_thi.phan_cong(db, user=u, cong_viec_id=cv.id, employee_id=e.id)


def test_gate_own_chi_ghi_viec_dang_giao_cho_minh(db, orders, lsx_svc, admin, customer):
    """Phạm vi "Của tôi": ghi được việc mình ĐANG được giao (hồ sơ nhân viên nối `user_id`, phân công
    hoạt động); việc khác cùng tổ bị chặn; bị rút khỏi việc thì mất luôn quyền ghi trên việc đó."""
    to = _to_khoan(db, admin, ma="TO-OWN")
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv1, cv2 = _cvs(db, to)[:2]
    for cv in (cv1, cv2):
        cv.loai_buoc = BUOC_MAY
        cv.du_kien_bat_dau = None
    u = _user(db, "tho_own_tt", to)
    cap_quyen_to(db, u, to, scope=SCOPE_OWN, viec=("run_order",))
    ban_than = _emp(db, to, "NV-OWN-1", user_id=u.id)
    phu = _emp(db, to, "NV-OWN-2")
    db.commit()
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv1.id, employee_id=ban_than.id)

    res = thuc_thi.phan_cong(db, user=u, cong_viec_id=cv1.id, employee_id=phu.id)  # việc của mình
    assert res["cong_viec_id"] == cv1.id
    with pytest.raises(PermissionError, match="Thực hiện lệnh"):                   # việc người khác
        thuc_thi.phan_cong(db, user=u, cong_viec_id=cv2.id, employee_id=phu.id)

    pc = db.query(SanXuatPhanCong).filter_by(cong_viec_id=cv1.id, employee_id=ban_than.id).one()
    thuc_thi.go_phan_cong(db, user=admin, phan_cong_id=pc.id, ly_do="Đổi người")
    with pytest.raises(PermissionError):                                           # hết được giao
        thuc_thi.go_phan_cong(
            db, user=u,
            phan_cong_id=db.query(SanXuatPhanCong).filter_by(
                cong_viec_id=cv1.id, employee_id=phu.id).one().id,
        )


def _xuong_cha(db, ma, *con) -> Department:
    """Nút cấp gom của khối Sản xuất, treo các tổ `con` bên dưới."""
    x = Department(name=f"Xưởng {ma}", code=ma, la_san_xuat=True)
    db.add(x)
    db.flush()
    for d in con:
        d.parent_id = x.id
    db.flush()
    return x


def test_gate_dong_all_o_nut_cha_ghi_duoc_to_con(db, orders, lsx_svc, admin, customer):
    """Luật cũ "cấp trên scope rộng KHÔNG ghi đè tổ con" đã gỡ: vùng của dòng = nút + cây con, nên
    người có Thực hiện lệnh `all` ở XƯỞNG ghi được việc của tổ con dù không đứng ở tổ đó."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CON-ALL")
    xuong = _xuong_cha(db, "XUONG-ALL", to)
    quan_doc = _user(db, "quan_doc_tt", xuong)
    cap_quyen_to(db, quan_doc, xuong, viec=("run_order",))
    e = _emp(db, to, "NV-CON-ALL")
    db.commit()

    res = thuc_thi.phan_cong(db, user=quan_doc, cong_viec_id=cv.id, employee_id=e.id)
    assert res["cong_viec_id"] == cv.id


def test_gate_department_duoi_nut_chi_ghi_cay_con_cua_minh(db, orders, lsx_svc, admin, customer):
    """Dòng `department` ở xưởng, người đứng ở tổ B (dưới nút) → trọn tổ B, còn tổ A cùng xưởng thì
    không có gì."""
    to_a = _to_khoan(db, admin, ma="TO-DEP-A")
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to_a.id)
    cv_a, cv_b = _cvs(db, to_a)[:2]
    to_b = _to_cong_nhat(db, ma="TO-DEP-B")
    xuong = _xuong_cha(db, "XUONG-DEP", to_a, to_b)
    for cv in (cv_a, cv_b):
        cv.loai_buoc = BUOC_MAY
    cv_b.department_id = to_b.id                         # snapshot tổ thực hiện của việc thứ hai
    u = _user(db, "to_b_dep_tt", to_b)
    cap_quyen_to(db, u, xuong, scope=SCOPE_DEPARTMENT, viec=("run_order",))
    e = _emp(db, to_b, "NV-DEP-B")
    db.commit()

    assert thuc_thi.phan_cong(db, user=u, cong_viec_id=cv_b.id, employee_id=e.id)["cong_viec_id"]
    with pytest.raises(PermissionError, match="Thực hiện lệnh"):
        thuc_thi.phan_cong(db, user=u, cong_viec_id=cv_a.id, employee_id=e.id)


def test_version_lech_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-5")
    with pytest.raises(ValueError):
        thuc_thi.phan_cong(
            db, user=admin, cong_viec_id=cv.id, employee_id=e.id,
            expected_version=cv.version + 5,
        )


# --- Phiên chạy (§7.2) ----------------------------------------------------------------------
def test_bat_dau_can_it_nhat_mot_khoan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError, match="^Cần giao ít nhất 1 thợ mới bắt đầu được.$"):   # chưa giao ai
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)

    cn = _emp(db, _to_cong_nhat(db), "NV-CN-2")             # chỉ công nhật → chưa đủ
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=cn.id)
    with pytest.raises(ValueError, match="^Người đang giao đều là công nhật — cần thêm ít nhất 1 thợ") as loi:
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    assert "khoán" not in str(loi.value)

    khoan = _emp(db, to, "NV-K-1")                          # thêm thợ khoán → mở được
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=khoan.id)
    # Roster 2 người > định mức seed (1) → §7.1 đòi lý do lệch số người; test này soi luật khoán.
    res = thuc_thi.bat_dau(
        db, user=admin, cong_viec_id=cv.id, ly_do_so_nguoi="Ghép thêm công nhật hỗ trợ",
    )

    assert res["trang_thai"] == CV_DANG_CHAY
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).all()
    assert len(phien) == 1 and phien[0].ket_thuc is None
    assert len(_mo_khoang(db, cv)) == 2                     # mở khoảng cho cả roster


def test_bat_dau_tre_khong_hoi_ly_do(db, orders, lsx_svc, admin, customer):
    """Luật "bắt đầu trễ phải nêu lý do" đã GỠ (16/09/2026, chủ xưởng chốt): lệch giờ đọc thẳng từ
    mốc thực tế so với dự kiến, không bắt thợ gõ thêm."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    cv.du_kien_bat_dau = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-2").id)

    res = thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    assert res["trang_thai"] == CV_DANG_CHAY


def test_tiep_tuc_sau_tam_dung_khong_hoi_ly_do_tre(db, orders, lsx_svc, admin, customer):
    """Tiếp tục đi chung đường với Bắt đầu. Bắt đầu đúng giờ, tạm dừng có lý do, lúc bấm Tiếp tục thì
    giờ dự kiến bắt đầu dĩ nhiên đã qua — không được đòi "lý do bắt đầu trễ"."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-2B").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    thuc_thi.tam_dung(db, user=admin, cong_viec_id=cv.id, ly_do="Hết giấy")
    cv.du_kien_bat_dau = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()

    res = thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    assert res["trang_thai"] == CV_DANG_CHAY


def _dat_dinh_muc_so_nguoi(db, cv, n: int) -> None:
    """Gán số người dự kiến (chốt lúc phát hành) vào dinh_muc_json — gán lại cả dict để SA bắt dirty."""
    cv.dinh_muc_json = {**(cv.dinh_muc_json or {}), "so_nhan_cong_tieu_chuan": n}
    db.commit()


def test_bat_dau_lech_so_nguoi_bat_buoc_ly_do(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    _dat_dinh_muc_so_nguoi(db, cv, 2)                     # dự kiến 2 người
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-LSN-1").id)

    with pytest.raises(ValueError):                       # thực tế 1 ≠ dự kiến 2, thiếu lý do → chặn
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    res = thuc_thi.bat_dau(
        db, user=admin, cong_viec_id=cv.id, ly_do_so_nguoi="Một thợ nghỉ đột xuất",
    )
    assert res["trang_thai"] == CV_DANG_CHAY
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.ly_do_so_nguoi == "Một thợ nghỉ đột xuất"


def test_bat_dau_khop_so_nguoi_khong_can_ly_do(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    _dat_dinh_muc_so_nguoi(db, cv, 1)                     # dự kiến 1 người
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-LSN-2").id)

    # Khớp số người: khỏi lý do; lý do thừa (nếu có) KHÔNG được ghi lại.
    res = thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id, ly_do_so_nguoi="thừa")
    assert res["trang_thai"] == CV_DANG_CHAY
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.ly_do_so_nguoi is None


def test_mot_nguoi_khong_hai_khoang_chong_gio(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cvs = _cvs(db, to)
    cv1, cv2 = cvs[0], cvs[1]
    for cv in (cv1, cv2):
        cv.loai_buoc = BUOC_MAY
        cv.du_kien_bat_dau = None
    db.commit()
    e = _emp(db, to, "NV-DUP")

    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv1.id, employee_id=e.id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv1.id)             # e có khoảng mở ở cv1
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv2.id, employee_id=e.id)  # cv2 chưa chạy → ok
    with pytest.raises(ValueError):
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv2.id)         # chồng giờ → chặn


def test_tam_dung_dong_phien_va_khoang(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-3").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)

    with pytest.raises(ValueError):
        thuc_thi.tam_dung(db, user=admin, cong_viec_id=cv.id, ly_do="")   # thiếu lý do
    res = thuc_thi.tam_dung(db, user=admin, cong_viec_id=cv.id, ly_do="Hết giấy")

    assert res["trang_thai"] == CV_TAM_DUNG
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.ket_thuc is not None
    assert phien.loai_dong == PHIEN_TAM_DUNG and phien.ly_do == "Hết giấy"
    assert len(_mo_khoang(db, cv)) == 0                                # khoảng đóng theo


def test_ket_thuc_hoan_thanh_dong_phien(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-4").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)

    res = thuc_thi.ket_thuc(db, user=admin, cong_viec_id=cv.id)
    assert res["trang_thai"] == CV_HOAN_THANH
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.loai_dong == PHIEN_KET_THUC and phien.ket_thuc is not None
    assert len(_mo_khoang(db, cv)) == 0


def test_ket_thuc_tre_khong_hoi_ly_do(db, orders, lsx_svc, admin, customer):
    """Luật "kết thúc trễ phải nêu lý do" đã GỠ cùng lúc với bắt đầu trễ (16/09/2026)."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-5").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    cv.du_kien_ket_thuc = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    res = thuc_thi.ket_thuc(db, user=admin, cong_viec_id=cv.id)
    assert res["trang_thai"] == CV_HOAN_THANH
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.loai_dong == PHIEN_KET_THUC and phien.ly_do is None


def test_go_phan_cong_dong_khoang_dang_mo(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-K-7")
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    pc = db.query(SanXuatPhanCong).filter_by(cong_viec_id=cv.id, employee_id=e.id).first()

    thuc_thi.go_phan_cong(db, user=admin, phan_cong_id=pc.id, ly_do="Đổi người")

    db.refresh(pc)
    assert pc.trang_thai == PC_DA_RUT and pc.ly_do_rut == "Đổi người"
    con_mo = db.query(SanXuatKhoangThamGia).filter_by(
        cong_viec_id=cv.id, employee_id=e.id, ket_thuc=None
    ).count()
    assert con_mo == 0


# --- Nguồn danh cho ô "Giao người" (board.nhan_vien_chon) -----------------------------------
def test_nhan_vien_chon_liet_ke_to_khoan_bo_nghi(db, orders, lsx_svc, admin, customer):
    to, _cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    con = _emp(db, to, "NV-CH-1", ten="Còn Làm")
    _emp(db, to, "NV-CH-9", ten="Đã Nghỉ").status = STATUS_RESIGNED
    _emp(db, _to_cong_nhat(db, ma="TO-CN-X"), "NV-KHAC-1")  # tổ khác → không lọt
    db.commit()

    res = board.nhan_vien_chon(db, admin, _authz(db), team_id=to.id)
    assert res["team_id"] == to.id
    ids = [r["id"] for r in res["nhan_vien"]]
    assert con.id in ids                                   # người còn làm có mặt
    assert all(r["full_name"] != "Đã Nghỉ" for r in res["nhan_vien"])  # đã nghỉ bị loại
    assert all(r["la_luong_khoan"] is True for r in res["nhan_vien"])  # tổ khoán → cả tổ khoán
    assert res["nhan_vien"][0]["co_tai_khoan"] is False    # thợ không tài khoản


def test_nhan_vien_chon_to_cong_nhat_khong_khoan(db, orders, lsx_svc, admin, customer):
    to, _cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT-CN")
    to.has_piece_work = False                              # biến tổ này thành công nhật
    _emp(db, to, "NV-CN-2")
    db.commit()
    res = board.nhan_vien_chon(db, admin, _authz(db), team_id=to.id)
    assert res["nhan_vien"] and all(r["la_luong_khoan"] is False for r in res["nhan_vien"])


def test_nhan_vien_chon_ngoai_pham_vi_bi_chan(db, orders, lsx_svc, admin, customer):
    """Phạm vi đọc tính từ DÒNG QUYỀN của vai, không từ `head_user_id`: người chỉ có Xem ở tổ
    ngoài thì không đổ được danh chọn của `to` — kể cả khi đứng tên trưởng tổ `to` (luật "tổ trưởng
    kiêm nhiệm thấy mọi tổ mình đứng tên" đã gỡ cùng mô hình cũ)."""
    to, _cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    from tests.test_san_xuat_board import _to_moi
    ngoai = _to_moi(db, "Tổ Ngoài TT", "TO-NG-TT", quyen_admin=False)
    u = _user(db, "nguoi_to_ngoai_tt", ngoai)
    cap_quyen_to(db, u, ngoai)
    to.head_user_id = u.id
    db.commit()

    assert board.nhan_vien_chon(db, u, _authz(db), team_id=ngoai.id)["team_id"] == ngoai.id
    with pytest.raises(PermissionError):
        board.nhan_vien_chon(db, u, _authz(db), team_id=to.id)


# --- Cổng router: không có Thực hiện lệnh ở tổ nào → 403 ------------------------------------
def test_api_khong_co_thuc_hien_lenh_o_to_nao_403(client):
    """Admin seed (Giám đốc) KHÔNG có bypass và DB test không có dòng `to_sx_*` nào ⇒
    `require_quyen_to("run_order")` chặn ngay ở router. Cấp Thực hiện lệnh ở một tổ thì qua cổng
    router — công việc id 1 không có nên rơi xuống lỗi nghiệp vụ 400, không còn 403."""
    from app.db import SessionLocal

    tok = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]
    goi = dict(json={"employee_id": 1}, headers={"Authorization": f"Bearer {tok}"})

    resp = client.post("/api/san-xuat/work-items/1/phan-cong", **goi)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Bạn không có quyền thực hiện thao tác này"

    s = SessionLocal()
    try:
        d = Department(name="Tổ API Thực Thi", code="TO-API-TT", la_san_xuat=True)
        s.add(d)
        s.flush()
        cap_quyen_to(s, s.query(User).filter(User.username == "admin").one(), d,
                     viec=("run_order",))
        s.commit()
    finally:
        s.close()
    resp = client.post("/api/san-xuat/work-items/1/phan-cong", **goi)
    assert resp.status_code == 400, resp.text


# --- Cổng KHUÔN/KHUNG ở bàn tổ (chốt 04/09/2026) --------------------------------------------
def _cv_co_khuon(db, orders, lsx_svc, admin, customer, *, ma="TO-KHUON"):
    """Một công việc đã phát hành, có ảnh chụp khuôn, đủ một thợ khoán để qua luật §7.1."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.khuon_json = {"id": 1, "ma": "KB-0001", "ten": "Dao bế hộp A", "loai": "khuon_be",
                     "so_ke": "Kệ A3", "tinh_trang": "dang_dung"}
    db.commit()
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, f"NV-{ma}").id)
    return cv


def test_chua_nhan_khuon_thi_khong_bat_dau_duoc(db, orders, lsx_svc, admin, customer):
    """Điểm chặn DUY NHẤT của luật 'bế phải có khuôn mới làm được'. Trước điểm này — xếp lịch, kéo
    thả, phát hành — máy không cản gì cả, vì không mốc nào ở kho khuôn đủ tin để chặn ai (và từ
    mg `0293` thì kho khuôn cũng không còn ô ngày nào)."""
    cv = _cv_co_khuon(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError, match="Chưa nhận khuôn"):
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)


def test_tich_nhan_khuon_roi_thi_bat_dau_duoc(db, orders, lsx_svc, admin, customer):
    cv = _cv_co_khuon(db, orders, lsx_svc, admin, customer, ma="TO-KHUON-2")
    thuc_thi.nhan_khuon(db, user=admin, cong_viec_id=cv.id)
    assert cv.khuon_nhan_luc is not None and cv.khuon_nhan_by_id == admin.id
    res = thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    assert res["trang_thai"] == CV_DANG_CHAY


def test_buoc_khong_can_khuon_khong_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-KHONG-KHUON")
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-KK").id)
    assert cv.khuon_json is None
    res = thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    assert res["trang_thai"] == CV_DANG_CHAY


def test_tra_khuon_khong_chan_gi(db, orders, lsx_svc, admin, customer):
    cv = _cv_co_khuon(db, orders, lsx_svc, admin, customer, ma="TO-KHUON-3")
    thuc_thi.nhan_khuon(db, user=admin, cong_viec_id=cv.id)
    thuc_thi.tra_khuon(db, user=admin, cong_viec_id=cv.id)
    assert cv.khuon_tra_luc is not None


# --- Tích nhận khuôn lật tình trạng dao (16/09/2026) ----------------------------------------
def _dao(db, tinh_trang: str, ma: str = "KB-9001"):
    from app.models.khuon_be import KhuonBe

    k = KhuonBe(ma=ma, ten="Hộp bánh mang đi 4 ngăn", loai="khuon_be", so_ke="Kệ B2",
                tinh_trang=tinh_trang)
    db.add(k)
    db.flush()
    return k


def _chup(k) -> dict:
    return {"id": k.id, "ma": k.ma, "ten": k.ten, "loai": k.loai, "so_ke": k.so_ke,
            "tinh_trang": k.tinh_trang}


def test_nhan_khuon_lat_dao_dang_dat_lam_sang_dang_dung(db, orders, lsx_svc, admin, customer):
    """Dao "làm mới" vào kho ở `dang_dat_lam`; tổ cầm được nó trong tay là bằng chứng dao đã về.
    Không lật thì nó mang chữ "đang đặt làm" mãi — lệnh sau dùng lại dao vẫn báo chưa về."""
    from app.models.audit import AuditLog

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAO-1")
    k = _dao(db, "dang_dat_lam")
    cv.khuon_json = _chup(k)
    db.commit()

    thuc_thi.nhan_khuon(db, user=admin, cong_viec_id=cv.id)
    db.refresh(k)
    db.refresh(cv)

    assert k.tinh_trang == "dang_dung"
    assert cv.khuon_json["tinh_trang"] == "dang_dung"
    vet = db.query(AuditLog).filter_by(action="dm_sua", target=f"khuon_be:{k.id}").one()
    assert vet.actor_user_id == admin.id
    assert "Tình trạng Đang đặt làm → Đang dùng" in vet.detail


def test_nhan_khuon_khong_hoi_sinh_dao_hong(db, orders, lsx_svc, admin, customer):
    """Tình trạng là phán xét của người: dao đã báo hỏng / thanh lý thì một cú tích nhận không được
    lật ngược nó. Chỉ `dang_dat_lam` mới lật."""
    from app.models.audit import AuditLog

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAO-2")
    k = _dao(db, "hong", ma="KB-9002")
    cv.khuon_json = _chup(k)
    db.commit()

    thuc_thi.nhan_khuon(db, user=admin, cong_viec_id=cv.id)
    db.refresh(k)
    db.refresh(cv)

    assert k.tinh_trang == "hong"
    assert cv.khuon_json["tinh_trang"] == "hong"
    assert db.query(AuditLog).filter_by(target=f"khuon_be:{k.id}").count() == 0


def test_nhan_khuon_cap_nhat_anh_chup_viec_khac_cung_dao(db, orders, lsx_svc, admin, customer):
    """Việc KHÁC trỏ cùng con dao (lệnh khác, chưa ai nhận) đang in chip "đang đặt làm" theo ảnh
    chụp lúc phát hành. Dao đã về thì chip đó cũng phải thôi nói sai."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAO-3")
    khac = next(c for c in _cvs(db, to) if c.id != cv.id)
    k = _dao(db, "dang_dat_lam", ma="KB-9003")
    cv.khuon_json = _chup(k)
    khac.khuon_json = _chup(k)
    db.commit()

    thuc_thi.nhan_khuon(db, user=admin, cong_viec_id=cv.id)
    db.refresh(khac)

    assert khac.khuon_json["tinh_trang"] == "dang_dung"
    assert khac.khuon_nhan_luc is None        # nhận ở việc này không phải là nhận ở việc kia
