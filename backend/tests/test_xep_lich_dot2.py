"""ĐỢT 2 — các ca bắt buộc trong phần Verify của plan, phần chưa có test.

Ba detector mới (`trung_khuon`, `khuon_chua_san_sang`, `thieu_nguoi`) kiểm ở mức HÀM: chúng nhận
danh sách dòng dạng dict (đúng thứ `danh_sach()` trả) nên không cần dựng cả luồng đơn → lệnh → xếp
lịch cho từng ca. Dựng đủ luồng chỉ để kiểm một phép so giờ là đổi 3 phút chạy test lấy 0 thông tin.

Ca còn lại (`_top_may` sắp theo giờ xong) phải chạm thật vào engine
nên đi qua fixture chung của `test_xep_lich_service`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.khuon_be import KhuonBe
from app.models.lsx import LsxCongDoan, LsxCongDoanPhuThuoc
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.xep_lich_repo import XepLichRepository
from app.services.xep_lich_service import XepLichService
from app.services.xep_lich_van_de_service import (
    CAT_KHUON_CHUA_SAN_SANG, CAT_THIEU_NGUOI, CAT_TRUNG_KHUON, SEV_CANH_BAO, SEV_CHAN,
    XepLichVanDeService,
)

from tests.test_xep_lich_service import (  # noqa: F401 — fixture dùng chung
    _hai_lsx_san_sang, _in_step, admin, bg_svc, customer, db, lsx_svc, orders, xl_svc,
)


@pytest.fixture
def vd_svc(db):
    return XepLichVanDeService(db, AuditLogRepository(db))


def _utc(h: int, m: int = 0) -> datetime:
    return datetime(2026, 7, 27, h, m, tzinfo=timezone.utc)


def _dong(**kw) -> dict:
    """Một dòng lịch tối thiểu, đủ field mà detector đọc."""
    d = {
        "id": 1, "nguon": "lsx", "lsx_id": 1, "bai_ghep_id": None, "lsx_ma": "LSX-0001",
        "cong_doan_ten": "Bế", "may_id": None, "department_id": None,
        "trang_thai": "da_xep", "start_at": _utc(8), "finish_at": _utc(10),
        "can_dung_cu": True, "khuon_be_id": 1,
        "so_nhan_cong": 2, "so_nhan_cong_toi_thieu": 2,
        "loai_buoc": "to", "is_locked": False,
    }
    d.update(kw)
    return d


# ============================ C — khuôn bế dùng chung ============================
def test_trung_khuon_chan_khi_chong_gio(vd_svc):
    """Hai bước cùng một khuôn, chồng giờ → Chặn. Chỉ có MỘT bộ khuôn, hai máy cũng không cứu."""
    rows = [
        _dong(id=1, lsx_id=1, lsx_ma="LSX-0001", may_id=10, start_at=_utc(8), finish_at=_utc(10)),
        _dong(id=2, lsx_id=2, lsx_ma="LSX-0002", may_id=11, start_at=_utc(9), finish_at=_utc(11)),
    ]
    out = vd_svc._trung_khuon(rows)
    assert len(out) == 1
    assert out[0]["category"] == CAT_TRUNG_KHUON
    assert out[0]["severity"] == SEV_CHAN


def test_trung_khuon_bat_ca_buoc_be_giao_cho_TO(vd_svc):
    """Bế TAY (gán tổ, không máy) vẫn phải bị bắt: trục gom là KHUÔN, không phải máy.

    Trước đây detector lọc qua `_da_xep_co_may` nên mọi bước bế thủ công lọt lưới trong im lặng.
    """
    rows = [
        _dong(id=1, lsx_id=1, may_id=None, department_id=5, start_at=_utc(8), finish_at=_utc(10)),
        _dong(id=2, lsx_id=2, may_id=None, department_id=5, start_at=_utc(9), finish_at=_utc(11)),
    ]
    assert len(vd_svc._trung_khuon(rows)) == 1


def test_trung_khuon_bo_qua_khi_khac_khuon_hoac_khong_can_dung_cu(vd_svc):
    khac_khuon = [
        _dong(id=1, khuon_be_id=1, start_at=_utc(8), finish_at=_utc(10)),
        _dong(id=2, khuon_be_id=2, start_at=_utc(9), finish_at=_utc(11)),
    ]
    assert vd_svc._trung_khuon(khac_khuon) == []
    # Bước KHÔNG cần dụng cụ thì trùng giờ là chuyện của máy, không phải của khuôn.
    khong_can = [
        _dong(id=1, can_dung_cu=False, start_at=_utc(8), finish_at=_utc(10)),
        _dong(id=2, can_dung_cu=False, start_at=_utc(9), finish_at=_utc(11)),
    ]
    assert vd_svc._trung_khuon(khong_can) == []


def test_khuon_chua_gan_la_chan(vd_svc):
    assert vd_svc._khuon_chua_san_sang([_dong(khuon_be_id=None)])[0]["severity"] == SEV_CHAN


@pytest.mark.parametrize("tinh_trang", ["hong", "thanh_ly"])
def test_khuon_hong_hoac_thanh_ly_la_chan(db, vd_svc, tinh_trang):
    kb = KhuonBe(ma=f"KB-{tinh_trang[:4]}", ten="Khuôn hộp", tinh_trang=tinh_trang)
    db.add(kb)
    db.commit()
    out = vd_svc._khuon_chua_san_sang([_dong(khuon_be_id=kb.id)])
    assert out[0]["category"] == CAT_KHUON_CHUA_SAN_SANG
    assert out[0]["severity"] == SEV_CHAN


def test_khuon_dat_lam_ve_TRE_la_chan_ve_KIP_chi_canh_bao(db, vd_svc):
    """Ranh giới của luật: khuôn về SAU giờ bắt đầu bế thì chặn, về trước thì chỉ nhắc theo dõi."""
    bat_dau = _utc(8)
    tre = KhuonBe(ma="KB-TRE", ten="Khuôn trễ", tinh_trang="dang_dat_lam",
                  ngay_ve_du_kien=bat_dau.date() + timedelta(days=3))
    kip = KhuonBe(ma="KB-KIP", ten="Khuôn kịp", tinh_trang="dang_dat_lam",
                  ngay_ve_du_kien=bat_dau.date() - timedelta(days=1))
    db.add_all([tre, kip])
    db.commit()

    o_tre = vd_svc._khuon_chua_san_sang([_dong(khuon_be_id=tre.id, start_at=bat_dau)])
    o_kip = vd_svc._khuon_chua_san_sang([_dong(id=2, khuon_be_id=kip.id, start_at=bat_dau)])
    assert o_tre[0]["severity"] == SEV_CHAN
    assert o_kip[0]["severity"] == SEV_CANH_BAO


def test_khuon_dat_lam_chua_co_ngay_ve_la_chan(db, vd_svc):
    """Không biết bao giờ về = KHÔNG đoán là sẽ kịp. Đoán ở đây là hứa với xưởng một ngày không có."""
    kb = KhuonBe(ma="KB-MOMO", ten="Khuôn mơ hồ", tinh_trang="dang_dat_lam", ngay_ve_du_kien=None)
    db.add(kb)
    db.commit()
    assert vd_svc._khuon_chua_san_sang([_dong(khuon_be_id=kb.id)])[0]["severity"] == SEV_CHAN


# ============================ G — số người tối thiểu ============================
def test_thieu_nguoi_la_chan(vd_svc):
    """Bố trí dưới mức tối thiểu = không mở máy được. Khai báo suông thì lịch vẫn hứa xong đúng hạn."""
    out = vd_svc._thieu_nguoi([_dong(loai_buoc="to", so_nhan_cong=1, so_nhan_cong_toi_thieu=3)])
    assert len(out) == 1
    assert out[0]["category"] == CAT_THIEU_NGUOI
    assert out[0]["severity"] == SEV_CHAN


def test_du_nguoi_thi_khong_bao(vd_svc):
    assert vd_svc._thieu_nguoi([_dong(loai_buoc="to", so_nhan_cong=3, so_nhan_cong_toi_thieu=3)]) == []
    # Chưa khai mức tối thiểu thì KHÔNG đoán mức nào cả.
    assert vd_svc._thieu_nguoi([_dong(loai_buoc="to", so_nhan_cong=1, so_nhan_cong_toi_thieu=None)]) == []


# ============================ F — thiếu vật tư ============================
def test_bang_can_doi_loi_thi_BAO_chu_khong_im(vd_svc, monkeypatch):
    """Không kiểm được vật tư mà trả rỗng thì đọc y hệt 'không lệnh nào thiếu' — cửa phát hành mở oan."""
    def _no(*_a, **_k):
        raise RuntimeError("bảng cân đối hỏng")

    monkeypatch.setattr(vd_svc, "_can_doi_vat_tu", _no)
    out = vd_svc._thieu_vat_tu([_dong()])
    assert len(out) == 1
    assert out[0]["severity"] == SEV_CANH_BAO
    assert "không" in out[0]["title"].lower() or "Không" in out[0]["title"]


# ============================ D — gợi ý top-3 theo GIỜ XONG ============================
def test_goi_y_tra_may_sap_theo_gio_xong(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """`goi_y` chạy CẢ KHI dòng chưa gán máy, và bảng máy sắp tăng dần theo `finish`."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.so_luong_vao, step.chay_phut = 2500, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = xl_svc.repo.by_lsx(lsx.id)[0]

    # Bỏ máy đang gán → đúng tình huống "chưa gán máy", chỗ trước đây gợi ý trả rỗng.
    xl_svc.gan(dong_id=dong.id, patch={"may_id": None}, actor=admin)
    res = xl_svc.goi_y(dong_id=dong.id)

    fins = [m["finish"] for m in res["goi_y_may"] if m["finish"]]
    assert fins == sorted(fins), "bảng gợi ý phải sắp theo GIỜ XONG, không theo giờ trống"
    assert len(res["goi_y_may"]) <= 3
    # Máy không hợp khổ vẫn được liệt kê nhưng luôn nằm dưới máy hợp khổ.
    co_kho = [m["khong_hop_kho"] for m in res["goi_y_may"]]
    assert co_kho == sorted(co_kho)


# ============================ B — chờ kỹ thuật không chiếm máy ============================
def test_may_chay_lien_tuc_khong_bi_ca_cat(db, orders, lsx_svc, xl_svc, admin, customer,
                                           monkeypatch):
    """Máy là thiết bị: việc dài hơn một ca vẫn chạy thẳng, KHÔNG bị đẩy sang hôm sau (2026-08-10).

    Trước đây khung mặc định là 8h phẳng 08:00–16:00 nên việc 10h bắt đầu 08:00 bị cắt: 8h hôm nay
    + 2h sáng mai. Nay máy chạy liên tục ⇒ xong 18:00 CÙNG NGÀY. Ca chỉ còn áp cho bước KHÔNG có
    máy (việc tay của tổ) — kiểm luôn ở dưới để không ai lặng lẽ cho tổ chạy 24/24 theo.
    """
    monkeypatch.setattr("app.services.calendar_service.CalendarService.is_working_day",
                        lambda self, d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    # 600 phút máy = 10 giờ: dài hơn ca hành chính 8h, ngắn hơn một ngày.
    step.so_luong_vao, step.chay_phut, step.setup_phut = 1000, 600, 0
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = xl_svc.repo.by_lsx(lsx.id)[0]
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

    r = xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": bat_dau},
                   actor=admin)
    chiem = xl_svc._thoi_luong(dong)["chiem_may_phut"]
    xong = r.finish_at.replace(tzinfo=None)
    assert xong == bat_dau.replace(tzinfo=None) + timedelta(minutes=chiem), (
        "máy chạy liên tục ⇒ giờ xong = giờ bắt đầu + thời lượng, không nhảy ngày"
    )
    assert xong.date() == bat_dau.date(), "việc 10h bắt đầu 08:00 phải xong trong ngày"

    # Bước KHÔNG có máy vẫn đi theo ca chung của xưởng (tập ca rỗng ⇒ 8h phẳng 08:00–16:00).
    lich_to = xl_svc.lich
    assert lich_to is not xl_svc._lich_may(step.may_id)
    khung = lich_to._khung_ngay(date(2026, 7, 27))
    assert sum((e - s).total_seconds() for s, e in khung) == 8 * 3600, (
        "tổ vẫn bị giới hạn theo ca — chỉ MÁY mới chạy liên tục"
    )


