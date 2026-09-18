"""Hàng đèn Kế hoạch SX chỉ nạp phần bàn lịch QUANH trang lệnh — mà phải ra y hệt nạp cả bàn.

Trước 18/09/2026 mỗi lần mở bảng lệnh, hàng đèn gọi `XepLichService.danh_sach()` không tham số:
nạp MỌI dòng lịch từng có, dựng DAG + thời lượng cho từng dòng, rồi vứt gần hết vì trang chỉ có
50 lệnh. Lệnh lại không bao giờ rời bàn (vòng đời dừng ở `da_phat_hanh`), nên cái giá đó tăng mãi
theo lịch sử xưởng.

Bản hẹp (`dong_va_van_de(chi_lsx_ids=...)`) chỉ nạp:
  1. dòng của các lệnh CÙNG ĐƠN với trang — DAG công đoạn chỉ nối trong một đơn;
  2. dòng CÙNG MÁY / CÙNG TỔ chồng khoảng giờ với dòng của trang — nguồn của `trung_may`,
     `qua_tai_to`.

Test ở đây giữ hai lời hứa: (a) với lệnh trên trang, dòng + vấn đề của bản hẹp TRÙNG KHÍT bản đầy;
(b) bản hẹp không đụng tới hai cửa nạp cả bàn, và lệnh ở xa không bị kéo vào. Kèm hai thứ lòi ra
khi đo cùng đợt: bàn đầy đủ hết N+1 theo lệnh, và cờ trùng máy hết bỏ sót việc không liền kề.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.models.department import Department
from app.models.lsx import LsxCongDoanPhuThuoc
from app.models.xep_lich import TT_DA_XEP
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.xep_lich_repo import XepLichRepository
from app.services import lsx_tong_quan
from app.services.xep_lich_service import XepLichService
from app.services.xep_lich_van_de_service import KHOA_THEO_DONG, XepLichVanDeService

from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    _in_step,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
    xl_svc,
)

# Đồng hồ xưởng GHIM: `som_nhat` có sàn là "bây giờ", hai lượt gọi cách nhau vài micro-giây là
# hai con số khác nhau — so khít từng dòng thì phải cùng một "bây giờ".
BAY_GIO = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)
T = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _dong_ho_va_lich(monkeypatch):
    monkeypatch.setattr("app.services.xep_lich_service._gio_xuong", lambda: BAY_GIO)
    monkeypatch.setattr("app.services.xep_lich_van_de_service._gio_xuong", lambda: BAY_GIO)
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService.is_working_day", lambda self, d: True
    )
    # Quân số 1 người/tổ, "gõ đè" để khỏi bị coi là chưa khai: hai việc cùng tổ chồng giờ là
    # quá tải ⇒ `qua_tai_to` có cái để bắt.
    monkeypatch.setattr(
        XepLichService, "quan_so_ngay",
        lambda self, dept, ngay, **kw: {"so_nguoi": 1, "go_de": True},
    )


def _dat(db, dong, *, may_id, to_id, tu, phut=60):
    """Đặt thẳng giờ lên dòng — `gan()` tự tính giờ xong theo năng suất, ở đây cần khoảng chồng
    đúng như kịch bản vẽ ra."""
    dong.may_id, dong.department_id = may_id, to_id
    dong.start_at, dong.finish_at = tu, tu + timedelta(minutes=phut)
    dong.trang_thai = TT_DA_XEP


def _dong_in(db, xl_svc, admin, lsx):
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    buoc = _in_step(db, lsx.id)
    return buoc, next(d for d in XepLichRepository(db).by_lsx(lsx.id)
                      if d.lsx_cong_doan_id == buoc.id)


@pytest.fixture
def ban(db, orders, lsx_svc, xl_svc, admin, customer):
    """Ba đơn trên cùng một máy + một tổ:

    - Đơn 1 (L1, L2): L1 là TRANG. Cạnh phụ thuộc L1 → L2 (xuyên lệnh, cùng đơn) ⇒ độ dư của L1
      phụ thuộc L2 — bản hẹp mà quên L2 thì `muon_nhat`/`slack_ngay` của L1 sai.
    - Đơn 2 (M1): chồng giờ L1 trên cùng máy + tổ ⇒ `trung_may` và `qua_tai_to` dính L1.
    - Đơn 3 (N1): hai tuần sau — hàng xóm GIẢ, bản hẹp không được kéo vào.
    """
    l1, l2 = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    m1, _ = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    n1, _ = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    b_l1, d_l1 = _dong_in(db, xl_svc, admin, l1)
    b_l2, d_l2 = _dong_in(db, xl_svc, admin, l2)
    _, d_m1 = _dong_in(db, xl_svc, admin, m1)
    _, d_n1 = _dong_in(db, xl_svc, admin, n1)

    may_id = b_l1.may_id
    to_id = b_l1.department_id or db.query(Department).first().id
    _dat(db, d_l1, may_id=may_id, to_id=to_id, tu=T)
    _dat(db, d_m1, may_id=may_id, to_id=to_id, tu=T + timedelta(minutes=30))
    _dat(db, d_l2, may_id=may_id, to_id=to_id, tu=T + timedelta(hours=3))
    _dat(db, d_n1, may_id=may_id, to_id=to_id, tu=T + timedelta(days=14))
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=b_l1.id, buoc_sau_id=b_l2.id))
    # Hạn L1 xa, hạn L2 gần ⇒ mốc muộn nhất của bước In L1 do L2 quyết (qua cạnh), không do L1.
    l1.han_hoan_thanh_sx = (T + timedelta(days=20)).date()
    l2.han_hoan_thanh_sx = (T + timedelta(days=2)).date()
    db.commit()
    return {"trang": {l1.id}, "l2": d_l2.id, "m1": d_m1.id, "n1": d_n1.id,
            "d_l1": d_l1.id, "han_l2": l2.han_hoan_thanh_sx}


def _cua_trang(issues, trang):
    return sorted(
        (it["issue_key"], it["severity"], tuple(sorted(it["impacts"]["lsx_ids"])),
         tuple(sorted(it["impacts"]["dong_ids"])))
        for it in issues
        if set(it["impacts"]["lsx_ids"]) & trang
        and it["issue_key"].split(":", 1)[0] in KHOA_THEO_DONG
    )


def test_ban_hep_ra_y_het_ban_day_cho_lenh_tren_trang(db, ban):
    trang = ban["trang"]
    rows_day, issues_day = XepLichVanDeService(db).dong_va_van_de()
    rows_hep, issues_hep = XepLichVanDeService(db).dong_va_van_de(chi_lsx_ids=trang)

    day = _cua_trang(issues_day, trang)
    # Kịch bản phải THẬT SỰ có cái để so — không thì 0 == 0 và test xanh vô nghĩa.
    assert {k[0].split(":", 1)[0] for k in day} >= {"trung_may", "qua_tai_to"}
    assert _cua_trang(issues_hep, trang) == day

    def _dong(rows):
        return {r["id"]: r for r in rows if r["lsx_id"] in trang}

    assert _dong(rows_hep) == _dong(rows_day)
    # Mốc muộn nhất của bước In L1 phải do L2 kéo về (qua cạnh cùng đơn) — không thì phép so khít
    # ở trên chưa chứng minh được bản hẹp đã gom đúng lệnh cùng đơn.
    muon = _dong(rows_day)[ban["d_l1"]]["muon_nhat"]
    assert muon is not None and muon.date() <= ban["han_l2"]
    assert _dong(rows_day)[ban["d_l1"]]["co_xung_dot"]


def test_ban_hep_chi_tra_lenh_tren_trang(db, ban):
    rows, issues = XepLichVanDeService(db).dong_va_van_de(chi_lsx_ids=ban["trang"])
    assert {r["lsx_id"] for r in rows} == ban["trang"]
    assert all(set(it["impacts"]["lsx_ids"]) & ban["trang"] for it in issues)


def test_ban_hep_keo_hang_xom_that_bo_hang_xom_xa(db, ban):
    ids = {r.id for r in XepLichRepository(db).dong_quanh(ban["trang"])}
    assert ban["l2"] in ids        # cùng đơn — DAG cần
    assert ban["m1"] in ids        # cùng máy, chồng giờ
    assert ban["n1"] not in ids    # cùng máy nhưng hai tuần sau


def test_hang_den_khong_nap_ca_ban(db, ban, monkeypatch):
    goi: list[str] = []
    monkeypatch.setattr(XepLichRepository, "list_dong",
                        lambda self, **kw: goi.append("list_dong") or [])
    monkeypatch.setattr(XepLichRepository, "rows_da_xep_co_may",
                        lambda self: goi.append("rows_da_xep_co_may") or [])
    out = lsx_tong_quan.tong_quan(db, sorted(ban["trang"]))
    assert goi == []
    # Và đèn máy của L1 vẫn đỏ vì trùng máy với M1 — tức bản hẹp vẫn thấy hàng xóm.
    assert out[0]["den"]["may_gio"]["muc"] == "do"


def test_ban_ca_xuong_so_cau_khong_chay_theo_so_lenh(db, ban, orders, lsx_svc, xl_svc, admin,
                                                     customer):
    """Bàn Xếp lịch đầy đủ (màn Xếp lịch, màn Vấn đề, cửa phát hành) vẫn phải nạp cả bàn — nhưng
    số câu SQL không được chạy theo số lệnh. Trước 18/09/2026 `_sl_tinh` tự `lsx_repo.get` từng
    lệnh (4 câu kéo cả cây routing) dù `_nap_lo` đã nạp sẵn: 1.071 dòng = 4.306 câu, 16 s."""
    def _dem() -> int:
        n = [0]

        def _d(*a, **k):
            n[0] += 1
        eng = db.get_bind()
        event.listen(eng, "before_cursor_execute", _d)
        try:
            db.expire_all()
            XepLichService(db, XepLichRepository(db), AuditLogRepository(db)).danh_sach()
        finally:
            event.remove(eng, "before_cursor_execute", _d)
        return n[0]

    truoc = _dem()
    for lenh in _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer):
        xl_svc.dua_vao_lsx(lsx_id=lenh.id, actor=admin)
    assert _dem() == truoc


def test_co_trung_may_bat_ca_viec_khong_lien_ke(xl_svc):
    """A 8h–12h · B 9h–9h30 · C 10h–11h: C trùng A dù việc liền trước C là B. Bản so cặp liền kề
    (trước 18/09/2026) bỏ sót C — lệch với `trung_may`, vốn so đủ mọi cặp."""
    def _d(id_, tu, den):
        return SimpleNamespace(id=id_, may_id=5, trang_thai=TT_DA_XEP,
                               start_at=datetime(2026, 9, 22, *tu), finish_at=datetime(2026, 9, 22, *den))
    rows = [_d(1, (8, 0), (12, 0)), _d(2, (9, 0), (9, 30)), _d(3, (10, 0), (11, 0)),
            _d(4, (12, 0), (13, 0))]
    assert xl_svc._xung_dot_ids(rows) == {1, 2, 3}


def test_moi_nhom_den_doc_deu_phan_duoc_tren_ban_hep():
    """Hàng đèn đọc nhóm nào thì bộ dò của nhóm đó phải chạy được trên bàn hẹp. Thêm nhóm mới vào
    đèn mà bộ dò của nó cần CẢ BÀN (kiểu `qua_tai_may`: tổng tải 7 ngày của máy) thì test này đỏ
    — phải nghĩ lại phạm vi nạp chứ đừng lặng lẽ nhận số sai."""
    den = (set(lsx_tong_quan.CAT_MAY_DO) | set(lsx_tong_quan.CAT_MAY_VANG)
           | set(lsx_tong_quan.CAT_NGUOI_DO))
    assert den <= set(KHOA_THEO_DONG)
