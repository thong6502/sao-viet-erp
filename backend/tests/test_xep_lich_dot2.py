"""ĐỢT 2 — các ca bắt buộc trong phần Verify của plan, phần chưa có test.

Detector `thieu_nguoi` kiểm ở mức HÀM: nó nhận danh sách dòng dạng dict (đúng thứ `danh_sach()`
trả) nên không cần dựng cả luồng đơn → lệnh → xếp lịch cho từng ca. Dựng đủ luồng chỉ để kiểm một
phép so là đổi 3 phút chạy test lấy 0 thông tin.

(7 test của `trung_khuon` + `khuon_chua_san_sang` đã gỡ 16/08/2026 cùng hai detector đó — mg
`0203`. Chúng gác một luật chưa lần nào có dữ liệu để chạy: 0/14 bước từng gán khuôn.)

Ca còn lại (`_top_may` sắp theo giờ xong) phải chạm thật vào engine
nên đi qua fixture chung của `test_xep_lich_service`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.lsx import LsxCongDoan, LsxCongDoanPhuThuoc
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.xep_lich_repo import XepLichRepository
from app.services.xep_lich_service import XepLichService
from app.services.xep_lich_van_de_service import (
    CAT_NGUOI, SEV_CHAN, SEV_LUU_Y, XepLichVanDeService,
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
        "so_nhan_cong": 2, "so_nhan_cong_toi_thieu": 2,
        "loai_buoc": "to", "is_locked": False,
    }
    d.update(kw)
    return d


# ============================ G — số người tối thiểu ============================
def test_thieu_nguoi_la_chan(vd_svc):
    """Bố trí dưới mức tối thiểu = không mở máy được. Khai báo suông thì lịch vẫn hứa xong đúng hạn."""
    out = vd_svc._thieu_nguoi([_dong(loai_buoc="to", so_nhan_cong=1, so_nhan_cong_toi_thieu=3)])
    assert len(out) == 1
    assert out[0]["category"] == CAT_NGUOI
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
    assert out[0]["severity"] == SEV_LUU_Y
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


