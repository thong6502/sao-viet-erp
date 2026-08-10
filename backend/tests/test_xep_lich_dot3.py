"""ĐỢT 3 — quỹ giờ-người của tổ (I) + tầng kế hoạch tuần (J).

Ba chỗ dễ sai nhất, mỗi chỗ một test:
1. Quân số tự tính chỉ đếm người gắn ĐÚNG tổ lá, và trừ phép ĐÃ DUYỆT — người tầng giữa không
   thuộc tổ nào (cộng vào là đếm thừa, lịch hứa năng lực không có thật).
2. Gõ đè THẮNG số tự tính; bỏ gõ đè thì quay về số tự tính (không để lại ảnh chụp cũ).
3. `qua_tai_to` quét theo MỐC, không so từng cặp: 3+3+3 người chồng nhau vẫn vừa quân số 9.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.department import Department
from app.models.employee import STATUS_ACTIVE, STATUS_RESIGNED, Employee
from app.models.leave import STATUS_APPROVED, STATUS_PENDING, LeaveRequest
from app.repositories.audit_repo import AuditLogRepository
from app.services.xep_lich_service import XepLichValidationError
from app.services.xep_lich_van_de_service import CAT_QUA_TAI_TO, SEV_CHAN, XepLichVanDeService

from tests.test_xep_lich_service import (  # noqa: F401 — fixture dùng chung
    _hai_lsx_san_sang, _in_step, admin, bg_svc, customer, db, lsx_svc, orders, xl_svc,
)

NGAY = date(2026, 7, 27)


@pytest.fixture
def vd_svc(db):
    return XepLichVanDeService(db, AuditLogRepository(db))


@pytest.fixture
def to_dan(db):
    """Tổ Dán 4 người: 3 người gắn đúng tổ, 1 người gắn ở tầng giữa (không thuộc tổ nào)."""
    cha = Department(name="Xưởng in Đợt 3", code="XI3", la_san_xuat=True)
    db.add(cha)
    db.flush()
    to = Department(name="Tổ Dán Đợt 3", code="TD3", parent_id=cha.id)
    db.add(to)
    db.flush()
    for i in range(3):
        db.add(Employee(code=f"NV-D3-{i}", full_name=f"Thợ dán {i}",
                        department_id=to.id, status=STATUS_ACTIVE))
    # Người ở TẦNG GIỮA — thuộc "Xưởng in", không thuộc tổ lá nào.
    db.add(Employee(code="NV-D3-GIUA", full_name="Quản đốc",
                    department_id=cha.id, status=STATUS_ACTIVE))
    # Người đã nghỉ việc: không đếm dù còn gắn tổ.
    db.add(Employee(code="NV-D3-OUT", full_name="Đã nghỉ",
                    department_id=to.id, status=STATUS_RESIGNED))
    db.commit()
    return to


def test_quan_so_tu_tinh_chi_dem_nguoi_dung_to_la(db, xl_svc, to_dan):
    """3 người gắn đúng tổ; quản đốc ở tầng giữa và người đã nghỉ KHÔNG được cộng vào."""
    assert xl_svc.quan_so_tu_tinh(to_dan.id, NGAY) == 3


def test_phep_da_duyet_tru_ra_phep_cho_duyet_thi_khong(db, xl_svc, to_dan):
    """Đơn CHỜ DUYỆT chưa phải là vắng mặt — trừ luôn là tự bịa ra một người nghỉ."""
    emp = db.query(Employee).filter(Employee.department_id == to_dan.id,
                                    Employee.status == STATUS_ACTIVE).first()
    db.add(LeaveRequest(employee_id=emp.id, start_date=NGAY, end_date=NGAY,
                        days=1, status=STATUS_PENDING))
    db.commit()
    assert xl_svc.quan_so_tu_tinh(to_dan.id, NGAY) == 3

    don = db.query(LeaveRequest).filter(LeaveRequest.employee_id == emp.id).first()
    don.status = STATUS_APPROVED
    db.commit()
    assert xl_svc.quan_so_tu_tinh(to_dan.id, NGAY) == 2
    # Ngày ngoài khoảng nghỉ thì không trừ.
    assert xl_svc.quan_so_tu_tinh(to_dan.id, NGAY + timedelta(days=5)) == 3


def test_go_de_thang_so_tu_tinh_va_bo_go_de_thi_quay_ve(db, xl_svc, admin, to_dan):
    """Mượn 3 người tổ Bế sang: số thật là 6 dù hồ sơ nói 3. Bỏ gõ đè ⇒ về lại 3, không giữ ảnh cũ."""
    ra = xl_svc.dat_quan_so(department_id=to_dan.id, ngay=NGAY, so_nguoi=6,
                            ly_do="mượn 3 người tổ Bế", actor=admin)
    assert (ra["so_nguoi"], ra["tu_tinh"], ra["go_de"]) == (6, 3, True)

    ra2 = xl_svc.dat_quan_so(department_id=to_dan.id, ngay=NGAY, so_nguoi=None,
                             ly_do="", actor=admin)
    assert (ra2["so_nguoi"], ra2["go_de"]) == (3, False)


def test_go_de_bat_buoc_co_ly_do(db, xl_svc, admin, to_dan):
    """Số đè lên dữ liệu nhân sự mà không nói vì sao thì tháng sau không ai giải thích nổi."""
    with pytest.raises(XepLichValidationError):
        xl_svc.dat_quan_so(department_id=to_dan.id, ngay=NGAY, so_nguoi=6, ly_do="", actor=admin)
    with pytest.raises(XepLichValidationError):
        xl_svc.dat_quan_so(department_id=to_dan.id, ngay=NGAY, so_nguoi=-1,
                           ly_do="âm là vô nghĩa", actor=admin)


def test_quy_gio_nguoi_bang_quan_so_nhan_gio_ca(db, xl_svc, to_dan, monkeypatch):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    q = xl_svc.quy_gio_nguoi(to_dan.id, NGAY)
    assert q["quy_gio_nguoi"] == pytest.approx(q["so_nguoi"] * q["gio_ca"])
    assert q["gio_ca"] > 0, "tổ chưa khai ca riêng ⇒ dùng tập ca chung, không được ra 0 giờ"


# ============================ detector qua_tai_to ============================
def _dong_to(dept_id: int, **kw) -> dict:
    d = {
        "id": 1, "nguon": "lsx", "lsx_id": 1, "bai_ghep_id": None, "lsx_ma": "LSX-0001",
        "cong_doan_ten": "Dán hộp", "may_id": None, "department_id": dept_id,
        "department_ten": "Tổ Dán", "trang_thai": "da_xep",
        "start_at": datetime(2026, 7, 27, 8, tzinfo=timezone.utc),
        "finish_at": datetime(2026, 7, 27, 12, tzinfo=timezone.utc),
        "so_nhan_cong": 2, "loai_buoc": "to", "is_locked": False,
    }
    d.update(kw)
    return d


def test_qua_tai_to_chan_khi_tong_nguoi_vuot_quan_so(db, vd_svc, to_dan):
    """Tổ 3 người mà hai việc cùng lúc đòi 2 + 2 = 4 người → Chặn."""
    rows = [
        _dong_to(to_dan.id, id=1, so_nhan_cong=2),
        _dong_to(to_dan.id, id=2, lsx_ma="LSX-0002", so_nhan_cong=2,
                 start_at=datetime(2026, 7, 27, 9, tzinfo=timezone.utc)),
    ]
    out = vd_svc._qua_tai_to(rows)
    assert len(out) >= 1
    assert out[0]["category"] == CAT_QUA_TAI_TO
    assert out[0]["severity"] == SEV_CHAN


def test_trung_gio_trong_to_KHONG_con_la_xung_dot_neu_du_nguoi(db, vd_svc, to_dan):
    """Đây là điểm khác máy: tổ 3 người chạy song song 2 việc 2+1 người là BÌNH THƯỜNG.

    Đối xử tổ y như máy (chiếm trọn khoảng giờ) sẽ bịa ra xung đột không có thật, rồi người dùng
    học cách bỏ qua báo đỏ — mất luôn giá trị của những báo đỏ thật.
    """
    rows = [
        _dong_to(to_dan.id, id=1, so_nhan_cong=2),
        _dong_to(to_dan.id, id=2, lsx_ma="LSX-0002", so_nhan_cong=1,
                 start_at=datetime(2026, 7, 27, 9, tzinfo=timezone.utc)),
    ]
    assert vd_svc._qua_tai_to(rows) == []


def test_to_CHUA_KHAI_nhan_su_thi_khong_bao_qua_tai(db, vd_svc):
    """Quân số 0 vì CHƯA khai hồ sơ nhân sự ≠ "tổ không có người" — không được chặn.

    Xưởng chưa nhập hồ sơ thì mọi bước tổ sẽ thành Chặn và không phát hành nổi lệnh nào. Chặn vì
    thiếu dữ liệu ở phân hệ KHÁC chính là kiểu báo đỏ dạy người dùng bỏ qua báo đỏ.
    """
    trong = Department(name="Tổ chưa khai NS", code="TCK", la_san_xuat=True)
    db.add(trong)
    db.commit()
    rows = [
        _dong_to(trong.id, id=1, so_nhan_cong=5),
        _dong_to(trong.id, id=2, lsx_ma="LSX-0002", so_nhan_cong=5,
                 start_at=datetime(2026, 7, 27, 9, tzinfo=timezone.utc)),
    ]
    assert vd_svc._qua_tai_to(rows) == []


def test_go_de_0_nguoi_thi_VAN_chan(db, xl_svc, vd_svc, admin):
    """Gõ đè 0 là câu người ta NÓI RA ("cả tổ nghỉ hôm nay") — khác hẳn "chưa khai", nên vẫn chặn."""
    to = Department(name="Tổ nghỉ trọn ngày", code="TNG", la_san_xuat=True)
    db.add(to)
    db.commit()
    xl_svc.dat_quan_so(department_id=to.id, ngay=NGAY, so_nguoi=0,
                       ly_do="cả tổ nghỉ bù", actor=admin)
    assert vd_svc._qua_tai_to([_dong_to(to.id, id=1, so_nhan_cong=1)]) != []


def test_qua_tai_to_quet_theo_MOC_khong_so_tung_cap(db, xl_svc, vd_svc, admin, to_dan):
    """3 việc 3 người chồng nhau từng đôi vẫn vừa quân số 9 — so từng cặp sẽ báo đỏ oan cả ba."""
    xl_svc.dat_quan_so(department_id=to_dan.id, ngay=NGAY, so_nguoi=9,
                       ly_do="huy động cả tổ", actor=admin)
    rows = [
        _dong_to(to_dan.id, id=i, lsx_ma=f"LSX-000{i}", so_nhan_cong=3,
                 start_at=datetime(2026, 7, 27, 8 + i, tzinfo=timezone.utc))
        for i in range(1, 4)
    ]
    assert vd_svc._qua_tai_to(rows) == []


def test_go_de_quan_so_lam_thay_doi_ket_luan_qua_tai(db, xl_svc, vd_svc, admin, to_dan):
    """Mượn người xong thì cái đang Chặn phải TỰ HẾT — không bắt người dùng đi dời việc oan."""
    rows = [
        _dong_to(to_dan.id, id=1, so_nhan_cong=2),
        _dong_to(to_dan.id, id=2, lsx_ma="LSX-0002", so_nhan_cong=2,
                 start_at=datetime(2026, 7, 27, 9, tzinfo=timezone.utc)),
    ]
    assert vd_svc._qua_tai_to(rows) != []
    xl_svc.dat_quan_so(department_id=to_dan.id, ngay=NGAY, so_nguoi=4,
                       ly_do="mượn 1 người tổ Bế", actor=admin)
    assert vd_svc._qua_tai_to(rows) == []


# ============================ J — tầng tuần ============================
def test_ke_hoach_tuan_dem_ca_viec_CHUA_XEP(db, orders, lsx_svc, xl_svc, admin, customer,
                                            monkeypatch):
    """Việc chưa có giờ vẫn phải vào tuần chứa HẠN của nó.

    Chỉ đếm việc đã xếp thì bảng báo "còn rỗng" trong khi hàng chờ đang đầy — đúng cái sai khiến
    người ta nhận thêm đơn rồi vỡ trận.
    """
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.so_luong_vao, step.chay_phut = 2500, None
    lsx.han_hoan_thanh_sx = NGAY + timedelta(days=2)
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)   # có dòng nhưng CHƯA gán giờ

    res = xl_svc.ke_hoach_tuan(tu=NGAY, so_tuan=2)
    o_may = [i for i in res["items"] if i["loai"] == "may" and i["can_gio"] > 0]
    assert o_may, "việc chưa xếp phải rơi vào tuần chứa hạn SX, không được biến mất khỏi bảng"


def test_ke_hoach_tuan_nguong_mau(db, xl_svc):
    """Ngưỡng của plan: ≥100% đỏ · ≥85% vàng · còn lại xanh. Khả dụng 0 mà có việc ⇒ đỏ, không nổ."""
    assert xl_svc._dong_tuan(NGAY, "may", 1, "M1", 80, 100)["mau"] == "xanh"
    assert xl_svc._dong_tuan(NGAY, "may", 1, "M1", 90, 100)["mau"] == "vang"
    assert xl_svc._dong_tuan(NGAY, "may", 1, "M1", 100, 100)["mau"] == "do"
    kiet = xl_svc._dong_tuan(NGAY, "to", 1, "T1", 10, 0)
    assert kiet["mau"] == "do" and kiet["pct"] == 999.0
    assert xl_svc._dong_tuan(NGAY, "to", 1, "T1", 0, 0)["mau"] == "xanh"


# ============================ J — gom theo NHÓM máy ============================
def test_tuan_gom_theo_NHOM_may_khong_theo_may_le(db, orders, lsx_svc, xl_svc, admin, customer,
                                                  monkeypatch):
    """Plan viết *"nhóm Máy in 92/88 giờ · nhóm Bế 60/80"* — gom theo NHÓM, không theo máy lẻ.

    Xưởng có 3 máy in thì câu hỏi thật là "khâu in tuần sau còn chỗ không", chứ không phải "máy in
    số 2 còn chỗ không": việc chuyển giữa các máy cùng nhóm là chuyện thường ngày.
    """
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.so_luong_vao, step.chay_phut = 2500, None
    lsx.han_hoan_thanh_sx = NGAY + timedelta(days=2)
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)

    o_may = [i for i in xl_svc.ke_hoach_tuan(tu=NGAY, so_tuan=2)["items"] if i["loai"] == "may"]
    assert o_may, "phải có dòng máy"
    for o in o_may:
        assert o["res_id"] is None, "dòng máy gom theo nhóm ⇒ không mang id máy lẻ"
        assert o["nhom"], "phải mang TÊN NHÓM để bấm sang Gantt lọc đúng nhóm đó"
        assert o["ten"] == o["nhom"]
