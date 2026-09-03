"""Đổi máy giữa chừng — bốn luật (§7.2 mở rộng 31/08/2026):

  · Đang CHẠY: đóng phiên máy cũ + mở phiên mới trên máy mới, CÙNG một mốc thời gian.
  · Đang TẠM DỪNG: chỉ đổi máy được phân công, KHÔNG mở phiên (mở khi bấm Tiếp tục).
  · Không bao giờ có hai phiên mở trên cùng một công việc.
  · Giờ máy = tổng khoảng phiên ĐÃ ĐÓNG + phần phiên đang chạy — đổi máy không làm mất giờ cũ.

Điều chỉnh so với brief gốc (31/08/2026): `test_api_doi_may_gate_quyen` KHÔNG khẳng định thẳng
mã 403 — brief giả định "Admin là Giám đốc, KHÔNG có bit `can_assign_work`" nhưng giả định đó
chưa được xác nhận. Điều cần chứng minh thật sự là "đổi máy đi qua ĐÚNG cùng cổng quyền với bắt
đầu": gọi cả `bat-dau` lẫn `doi-may` bằng CÙNG một tài khoản trên CÙNG một công việc rồi so hai
kết luận về quyền (cùng 403, hoặc cùng qua cổng) — không phụ thuộc việc vai admin đang được cấp gì.

REVIEW VÒNG 1 (31/08/2026) — ba khoảng trống bị soi ra:

  · Important 1: bộ test gốc không có kịch bản "chỉ đổi máy (không tạm dừng thật) rồi kết thúc
    trễ" — lỗ hổng gộp `loai_dong=doi_may` chung với `tam_dung` (miễn lý do trễ nhầm) sẽ lọt qua
    hết bốn test cũ vì không test nào gọi `ket_thuc()` sau `doi_may()`.
  · Important 2: bộ test gốc DỰA vào chính lỗ hổng "chưa kiểm máy mới có thật không" — mọi
    `may_id_moi` đều là số bịa (501/502/999/777/778/2). Phải dựng máy THẬT trong `may_thiet_bi`
    rồi chữa lại toàn bộ test cho khớp, cộng hai test chặn (máy không tồn tại/đã ngừng dùng, và
    bước không chạy máy).
  · Important 3: bốn test luật gốc chỉ soi bảng `san_xuat_phien_chay`, không soi
    `san_xuat_khoang_tham_gia` — một vòng lặp đóng/mở khoảng bị bỏ sót hay tra nhầm phiên vẫn
    xanh hết vì roster dàn cảnh chỉ có MỘT người (không thể phát hiện "mất một người").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.department import Department
from app.models.employee import Employee
from app.models.may_thiet_bi import MayThietBi
from app.models.san_xuat import BUOC_MAY, BUOC_TO, CV_DANG_CHAY, CV_TAM_DUNG, SanXuatCongViec
from app.models.san_xuat_thuc_thi import SanXuatKhoangThamGia, SanXuatPhienChay
from app.services.san_xuat import thuc_thi

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)


# --- Dàn cảnh dùng chung (theo mẫu tests/test_san_xuat_thuc_thi.py, dòng 55) -----------------
def _to_khoan(db, admin, ma="TO-DM") -> Department:
    """Tổ sản xuất bật lương khoán, admin làm tổ trưởng — để qua GATE §6 khi gọi service."""
    d = Department(
        name=f"Tổ Đổi Máy {ma}", code=ma, la_san_xuat=True,
        has_piece_work=True, head_user_id=admin.id,
    )
    db.add(d)
    db.flush()
    return d


def _emp(db, dept, ma, ten="Thợ") -> Employee:
    e = Employee(code=ma, full_name=ten, department_id=dept.id)
    db.add(e)
    db.flush()
    return e


def _may(db, ma) -> MayThietBi:
    """Máy THẬT trong danh mục (`active=True` mặc định) — review vòng 1, Important 2: đổi máy
    giờ phải trỏ vào một hàng có thật, không còn nhận số bịa."""
    m = MayThietBi(ma=ma, ten=f"Máy {ma}", loai_may="press_offset_sheet")
    db.add(m)
    db.flush()
    return m


def _mot_cv_dang_chay(
    db, orders, lsx_svc, admin, customer, *,
    ma="TO-DM", may_id: int, loai_buoc: str = BUOC_MAY, so_nguoi: int = 1,
) -> SanXuatCongViec:
    """Một tổ khoán + một công việc, gán `may_id` THẬT, ĐANG CHẠY (1 phiên mở, `so_nguoi` thợ)."""
    to = _to_khoan(db, admin, ma=ma)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv = (
        db.query(SanXuatCongViec)
        .filter_by(department_id=to.id)
        .order_by(SanXuatCongViec.id)
        .first()
    )
    cv.loai_buoc = loai_buoc
    cv.du_kien_bat_dau = None
    cv.du_kien_ket_thuc = None
    cv.may_id = may_id
    db.commit()
    for i in range(so_nguoi):
        e = _emp(db, to, f"NV-{ma}-{i}")
        thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    # `ly_do_so_nguoi` chỉ THỰC SỰ được dùng khi số người dàn cảnh lệch định mức chốt lúc phát
    # hành (xem `bat_dau()`) — truyền sẵn cho an toàn, vô hại với các test `so_nguoi=1` khớp định mức.
    thuc_thi.bat_dau(
        db, user=admin, cong_viec_id=cv.id,
        ly_do_so_nguoi="Dàn cảnh test — số người khác định mức chốt lúc phát hành",
    )
    db.refresh(cv)
    return cv


@pytest.fixture
def to_truong(admin):
    """`_to_khoan` gán admin.id làm `head_user_id` của tổ dàn cảnh — admin CHÍNH là tổ trưởng."""
    return admin


@pytest.fixture
def cac_may(db) -> list[MayThietBi]:
    """Ba máy thật, active mặc định — đủ để đổi máy hai lần liên tiếp mà không quay lại máy cũ."""
    return [_may(db, f"MAY-DM-{i}") for i in range(1, 4)]


@pytest.fixture
def cv_dang_chay(db, orders, lsx_svc, admin, customer, cac_may) -> SanXuatCongViec:
    return _mot_cv_dang_chay(db, orders, lsx_svc, admin, customer, may_id=cac_may[0].id)


@pytest.fixture
def cv_tam_dung(db, orders, lsx_svc, admin, customer, cac_may) -> SanXuatCongViec:
    cv = _mot_cv_dang_chay(db, orders, lsx_svc, admin, customer, ma="TO-DM-TD", may_id=cac_may[0].id)
    thuc_thi.tam_dung(db, user=admin, cong_viec_id=cv.id, ly_do="Tạm dừng để test đổi máy")
    db.refresh(cv)
    return cv


@pytest.fixture
def cv_dang_chay_hai_nguoi(db, orders, lsx_svc, admin, customer, cac_may) -> SanXuatCongViec:
    """Roster 2 người — review vòng 1, Important 3: phải ĐỦ 2 người mới lộ ra bug "mất một người"
    khi đổi máy đóng/mở lại khoảng tham gia."""
    return _mot_cv_dang_chay(
        db, orders, lsx_svc, admin, customer, ma="TO-DM-2NG", may_id=cac_may[0].id, so_nguoi=2,
    )


# --- Bốn luật ---------------------------------------------------------------------------------
def test_doi_may_khi_dang_chay_dong_phien_cu_mo_phien_moi(db, cv_dang_chay, to_truong, cac_may):
    cv = cv_dang_chay
    may_cu = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).one().may_id
    assert may_cu == cac_may[0].id
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv.id, may_id_moi=cac_may[1].id)

    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).order_by(SanXuatPhienChay.so_thu_tu).all()
    assert len(phien) == 2
    assert phien[0].ket_thuc is not None and phien[0].may_id == may_cu
    assert phien[1].ket_thuc is None and phien[1].may_id == cac_may[1].id
    assert phien[0].ket_thuc == phien[1].bat_dau       # không hở, không chồng
    assert cv.trang_thai == CV_DANG_CHAY
    assert cv.may_id == cac_may[1].id


def test_doi_may_khi_tam_dung_khong_mo_phien(db, cv_tam_dung, to_truong, cac_may):
    cv = cv_tam_dung
    truoc = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).count()
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv.id, may_id_moi=cac_may[1].id)
    assert db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).count() == truoc
    assert cv.trang_thai == CV_TAM_DUNG
    assert cv.may_id == cac_may[1].id


def test_khong_bao_gio_hai_phien_mo(db, cv_dang_chay, to_truong, cac_may):
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=cac_may[1].id)
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=cac_may[2].id)
    mo = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv_dang_chay.id, ket_thuc=None).count()
    assert mo == 1


def test_doi_sang_chinh_may_dang_chay_bi_chan(db, cv_dang_chay, to_truong):
    with pytest.raises(ValueError, match="đang chạy"):
        thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=cv_dang_chay.may_id)


# --- Review vòng 1, Important 2: chặn máy không có thật / bước không chạy máy ------------------
def test_doi_may_khong_ton_tai_bi_chan(db, cv_dang_chay, to_truong):
    """`may_id_moi` không có hàng nào trong `may_thiet_bi` — service phải chặn, không tin FE (FE
    chỉ CHE nút chứ không phải cổng thật: tab để lâu vẫn gọi được API này)."""
    with pytest.raises(ValueError, match="không tồn tại|ngừng dùng"):
        thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=999_999)


def test_doi_may_may_ngung_dung_bi_chan(db, cv_dang_chay, to_truong, cac_may):
    """Máy có hàng thật nhưng đã NGỪNG DÙNG (`active=False` — luật xoá chung của danh mục, xem
    comment `MayThietBi.active`) — vẫn phải chặn như máy không tồn tại."""
    cac_may[1].active = False
    db.commit()
    with pytest.raises(ValueError, match="không tồn tại|ngừng dùng"):
        thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=cac_may[1].id)


def test_doi_may_buoc_khong_chay_may_bi_chan(db, orders, lsx_svc, admin, customer, cac_may):
    """Bước chiếm TỔ (`loai_buoc='to'`) không có khái niệm máy — đổi máy trên bước này phải bị
    chặn ngay ở service, kể cả khi gọi thẳng (không qua FE che nút)."""
    cv = _mot_cv_dang_chay(
        db, orders, lsx_svc, admin, customer,
        ma="TO-DM-BUOCTO", may_id=cac_may[0].id, loai_buoc=BUOC_TO,
    )
    with pytest.raises(ValueError, match="không chạy máy"):
        thuc_thi.doi_may(db, user=admin, cong_viec_id=cv.id, may_id_moi=cac_may[1].id)


# --- Review vòng 1, Important 1: đổi máy KHÔNG được tính là "đã có lý do giải thích trễ" -------
def test_ket_thuc_tre_van_bat_buoc_ly_do_khi_chi_co_doi_may(db, cv_dang_chay, to_truong, cac_may):
    """Bug gốc: `doi_may()` từng đóng phiên với `loai_dong=tam_dung` — công việc CHƯA HỀ tạm dừng
    thật, nhưng `ket_thuc()` lại đọc thấy một phiên `tam_dung` có lý do và MIỄN luôn lý do kết
    thúc trễ. Kịch bản: bắt đầu đúng hạn → đổi máy (không tạm dừng thật) → dự kiến kết thúc đã
    qua → `ket_thuc()` không kèm lý do vẫn phải bị chặn."""
    cv = cv_dang_chay
    cv.du_kien_ket_thuc = datetime.now(timezone.utc) - timedelta(minutes=5)  # đặt SAU khi đã bắt đầu
    db.commit()

    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv.id, may_id_moi=cac_may[1].id)

    with pytest.raises(ValueError, match="Kết thúc trễ"):
        thuc_thi.ket_thuc(db, user=to_truong, cong_viec_id=cv.id)


# --- Review vòng 1, Important 3: đổi máy không được làm mất/lệch khoảng tham gia ---------------
def test_doi_may_dang_chay_giu_nguyen_khoang_tham_gia(db, cv_dang_chay_hai_nguoi, to_truong, cac_may):
    """Bốn test luật gốc chỉ soi bảng phiên (`san_xuat_phien_chay`), không soi bảng khoảng tham
    gia của TỪNG NGƯỜI — một vòng lặp bị bỏ sót hay tra nhầm phiên vẫn xanh hết vì trước đây dàn
    cảnh chỉ có MỘT người. Ở đây roster có 2 người: đổi máy phải đóng ĐỦ 2 khoảng cũ và mở ĐỦ 2
    khoảng mới, cùng đúng người, cùng một mốc đóng-mở (không hở giây, không đếm phút hai lần)."""
    cv = cv_dang_chay_hai_nguoi
    phien_cu = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id, ket_thuc=None).one()
    khoang_truoc = (
        db.query(SanXuatKhoangThamGia)
        .filter_by(phien_chay_id=phien_cu.id, ket_thuc=None)
        .all()
    )
    nguoi_cu = {k.employee_id for k in khoang_truoc}
    assert len(nguoi_cu) == 2   # dàn cảnh phải đủ 2 người mới bắt được "mất một người"

    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv.id, may_id_moi=cac_may[1].id)

    phien_moi = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id, ket_thuc=None).one()
    khoang_cu_sau = db.query(SanXuatKhoangThamGia).filter_by(phien_chay_id=phien_cu.id).all()
    khoang_moi = (
        db.query(SanXuatKhoangThamGia)
        .filter_by(phien_chay_id=phien_moi.id, ket_thuc=None)
        .all()
    )

    assert len(khoang_cu_sau) == 2 and all(k.ket_thuc is not None for k in khoang_cu_sau)
    assert len(khoang_moi) == 2
    assert {k.employee_id for k in khoang_moi} == nguoi_cu     # không rơi/thêm người
    moc_dong = {k.ket_thuc for k in khoang_cu_sau}
    moc_mo = {k.bat_dau for k in khoang_moi}
    assert moc_dong == moc_mo and len(moc_dong) == 1           # đóng-mở CÙNG một mốc, không hở giây


# --- Đường dây RBAC: đổi máy đi qua ĐÚNG cùng cổng quyền với Bắt đầu ---------------------------
def test_api_doi_may_gate_quyen(client, seed_credentials):
    r = client.post("/api/auth/login", json=seed_credentials)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r_bat_dau = client.post("/api/san-xuat/work-items/1/bat-dau", json={}, headers=headers)
    r_doi_may = client.post(
        "/api/san-xuat/work-items/1/doi-may", json={"may_id": 2}, headers=headers,
    )
    # Review vòng 1, Minor 4: route phải còn sống — nếu ai lỡ xoá/đổi tên route thì 404, và 404
    # cũng thoả mãn phép so 403-hay-không nên assert dưới KHÔNG tự bắt được lỗi đó.
    assert r_doi_may.status_code != 404, (r_doi_may.status_code, r_doi_may.text)
    # Cùng tài khoản, cùng công việc: hai đường phải cho CÙNG kết luận về quyền (403 hay không),
    # bất kể vai `seed_credentials` đang được cấp bit `can_assign_work` hay không.
    assert (r_bat_dau.status_code == 403) == (r_doi_may.status_code == 403), (
        r_bat_dau.status_code, r_bat_dau.text, r_doi_may.status_code, r_doi_may.text,
    )
