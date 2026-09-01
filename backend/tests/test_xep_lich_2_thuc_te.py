"""Xếp lịch 2 — LỚP THỰC TẾ đè lên bàn Gantt (docs/spec-thuc-te-vs-ke-hoach.md §2.1).

Chỉ soi tầng hàm `services/xep_lich_2/thuc_te.py`: nó nhận danh sách dòng lịch, trả map tiến độ
thật. Dựng dàn cảnh bằng fixture luồng thật của thực hiện sản xuất (đơn → lệnh → phát hành vào tổ)
rồi tự gắn `xep_lich_cong_doan` trỏ đúng cặp neo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.san_xuat import (
    CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG, SanXuatCongViec,
)
from app.models.san_xuat_thuc_thi import SanXuatPhienChay
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.xep_lich import NGUON_LSX, TT_DA_XEP, XepLichCongDoan
from app.services.san_xuat import release, release_update
from app.services.xep_lich_2.thuc_te import nap_thuc_te

from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _mot_cv, _phat_hanh_vao_to, _to_khoan, admin, customer, db, lsx_svc, orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _thuc(t: datetime) -> datetime:
    """Mốc GIỜ XƯỞNG `t` tương ứng với mốc UTC THẬT nào — đúng cách production ghi:
    `du_kien_*` là giờ tường nhà máy (chép từ `xep_lich_cong_doan`), còn
    `san_xuat_phien_chay.bat_dau/ket_thuc` do `thuc_thi._moc()` ghi bằng UTC thật. Dựng cả hai từ
    CÙNG một hằng như trước là bỏ qua đúng chỗ hai thang gặp nhau — lỗi lệch 7 tiếng chui lọt vì
    thế (phát hiện 01/09/2026). Xem `app/services/gio_xuong.py`.
    """
    return t - (datetime.now().astimezone().utcoffset() or timedelta(0))


def _dong_lich(db, cv) -> XepLichCongDoan:
    """Dòng lịch trỏ đúng bước LSX mà công việc đang neo."""
    d = XepLichCongDoan(
        nguon=NGUON_LSX, lsx_id=cv.lsx_id, lsx_cong_doan_id=cv.lsx_cong_doan_id,
        source_thu_tu=0, loai_buoc="to", trang_thai=TT_DA_XEP,
        start_at=_T0, finish_at=_T0 + timedelta(hours=4),
    )
    db.add(d)
    db.flush()
    return d


def test_chua_chay_thi_khong_co_dong_nao_trong_map(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT1")
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.commit()

    ra = nap_thuc_te(db, [d])
    assert ra[d.id]["trang_thai"] == cv.trang_thai
    assert ra[d.id]["bat_dau_thuc"] is None
    assert ra[d.id]["tong_tot"] == 0.0
    assert ra[d.id]["con_thieu"] == 10000.0


def test_dang_chay_co_batch_thi_tinh_phan_tram_va_con_thieu(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT2")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1, bat_dau=_thuc(_T0 + timedelta(hours=2))))
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0 + timedelta(hours=2),
                        ket_thuc=_T0 + timedelta(hours=3), tong=6000, tot=5800, hong=200,
                        don_vi="tờ"))
    db.commit()

    ra = nap_thuc_te(db, [d])[d.id]
    assert ra["tong_tot"] == 5800.0
    assert ra["tong_hong"] == 200.0
    assert ra["con_thieu"] == 4200.0
    assert ra["phan_tram"] == pytest.approx(58.0)
    assert ra["tre_bat_dau_phut"] == 120


def test_qua_gio_du_kien_ma_van_chay_thi_bao_tre_ket_thuc(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT3")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 100
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1, bat_dau=_thuc(_T0)))
    db.commit()

    ra = nap_thuc_te(db, [d], bay_gio=_T0 + timedelta(hours=7))[d.id]
    assert ra["ket_thuc_thuc"] is None
    assert ra["tre_ket_thuc_phut"] == 180


def test_xong_roi_thi_lay_moc_ket_thuc_phien_cuoi(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT4")
    cv.trang_thai = CV_HOAN_THANH
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 100
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1,
                            bat_dau=_thuc(_T0), ket_thuc=_thuc(_T0 + timedelta(hours=1))))
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=2,
                            bat_dau=_thuc(_T0 + timedelta(hours=2)),
                            ket_thuc=_thuc(_T0 + timedelta(hours=5))))
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=5),
                        tong=100, tot=100, hong=0, don_vi="tờ"))
    db.commit()

    ra = nap_thuc_te(db, [d])[d.id]
    assert ra["bat_dau_thuc"].replace(tzinfo=timezone.utc) == _T0
    assert ra["ket_thuc_thuc"].replace(tzinfo=timezone.utc) == _T0 + timedelta(hours=5)
    assert ra["con_thieu"] == 0.0
    assert ra["tre_ket_thuc_phut"] == 60


def test_bam_goi_dang_hieu_luc_sau_thu_hoi_roi_phat_hanh_lai(db, orders, lsx_svc, admin, customer):
    """Thu-hồi-rồi-phát-hành-lại: gói cũ (đã qua vài lượt "phát hành cập nhật", `phien_ban_so` cao)
    bị thu hồi; gói mới phát hành lại bắt đầu từ `phien_ban_so`=1. `nap_thuc_te` phải bám công việc
    thuộc gói ĐANG HIỆU LỰC, không phải bản có `phien_ban_so` lớn nhất (vòng sửa 1, phát hiện CAO —
    tiền lệ lọc gói hiệu lực: `san_xuat_repo.py:goi_hien_tai_cua`)."""
    to = _to_khoan(db, admin, ma="TO-TT-GOI")
    a, b, _goi1 = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    cv1 = (
        db.query(SanXuatCongViec)
        .filter(
            SanXuatCongViec.department_id == to.id,
            SanXuatCongViec.lsx_cong_doan_id.isnot(None),
        )
        .order_by(SanXuatCongViec.id)
        .first()
    )
    lsx_cd = cv1.lsx_cong_doan_id
    cv1_id = cv1.id
    d = _dong_lich(db, cv1)
    db.commit()

    # Gói 1 qua 2 lượt "phát hành cập nhật" ⇒ phien_ban_so leo lên 3.
    release_update.phat_hanh_cap_nhat(
        db, nguon="lsx", id=a.id, ly_do="Đổi giờ chạy máy.", actor=admin
    )
    release_update.phat_hanh_cap_nhat(
        db, nguon="lsx", id=a.id, ly_do="Đổi máy lần 2.", actor=admin
    )

    # Chưa việc nào bắt đầu ⇒ thu hồi được, rồi phát hành lại ⇒ gói 2 bắt đầu lại từ phien_ban_so=1.
    assert release_update.co_cong_viec_da_bat_dau(db, nguon="lsx", id=a.id) is False
    release_update.thu_hoi_goi(db, nguon="lsx", id=a.id, actor=admin)
    db.commit()
    release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()

    cv2 = (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.lsx_cong_doan_id == lsx_cd, SanXuatCongViec.id != cv1_id)
        .one()
    )
    assert cv1.phien_ban_so == 3  # gói cũ (đã thu hồi) leo version cao hơn
    assert cv2.phien_ban_so == 1  # gói mới bắt đầu lại từ đầu

    ra = nap_thuc_te(db, [d])[d.id]
    assert ra["cong_viec_id"] == cv2.id  # bám gói ĐANG HIỆU LỰC, không phải phien_ban_so lớn nhất


def test_phien_moi_con_mo_giua_nhieu_phien_thi_chua_tinh_ket_thuc(db, orders, lsx_svc, admin, customer):
    """Tổ tạm dừng máy (đóng phiên 1, có `ket_thuc`) rồi chạy tiếp (mở phiên 2, `ket_thuc` NULL) —
    công việc CHƯA xong dù phiên đầu đã có mốc đóng. Guard `con_mo` (vòng sửa 1, phát hiện VỪA)
    phải chặn `max(ket_thuc)` của phiên đã đóng bị hiểu nhầm thành giờ kết thúc thật."""
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT5")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 100
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1,
                            bat_dau=_thuc(_T0), ket_thuc=_thuc(_T0 + timedelta(hours=1))))   # đã đóng
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=2,
                            bat_dau=_thuc(_T0 + timedelta(hours=2))))                  # còn mở
    db.commit()

    ra = nap_thuc_te(db, [d])[d.id]
    assert ra["ket_thuc_thuc"] is None
    assert ra["bat_dau_thuc"].replace(tzinfo=timezone.utc) == _T0


def test_khong_co_cong_viec_thi_khong_co_khoa(db):
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_id=None, lsx_cong_doan_id=999_999,
                        source_thu_tu=0, loai_buoc="may", trang_thai=TT_DA_XEP)
    db.add(d)
    db.commit()
    assert nap_thuc_te(db, [d]) == {}


def test_danh_sach_rong_khong_chay_query(db):
    assert nap_thuc_te(db, []) == {}


def test_ban_lam_viec_mang_theo_lop_thuc_te(db, orders, lsx_svc, admin, customer):
    """`workspace()` phải gắn `thuc_te` vào từng thanh — và MỌI thanh đều có khoá đó (None nếu
    chưa phát hành), để FE khỏi phải phân biệt 'thiếu khoá' với 'chưa chạy'."""
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.xep_lich_2_repo import XepLich2Repository
    from app.services.xep_lich_2 import XepLich2Service

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT5")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 1000
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
                        tong=400, tot=400, hong=0, don_vi="tờ"))
    db.commit()

    svc = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
    ban = svc.workspace(tu=_T0.date(), den=(_T0 + timedelta(days=1)).date())
    thanh = {row["id"]: row for row in ban["dong"]}
    assert "thuc_te" in thanh[d.id]
    assert thanh[d.id]["thuc_te"]["tong_tot"] == 400.0
    assert thanh[d.id]["thuc_te"]["phan_tram"] == pytest.approx(40.0)


def test_thanh_chua_phat_hanh_van_mang_khoa_thuc_te_bang_none(db, orders, lsx_svc, admin, customer):
    """Thanh CHƯA phát hành xuống tổ vẫn phải CÓ khoá `thuc_te`, giá trị `None`.

    Phải đứng ở tầng `workspace()` chứ không phải `nap_thuc_te()`: tầng dưới trả map thưa là ĐÚNG
    thiết kế (`test_khong_co_cong_viec_thi_khong_co_khoa`), còn hợp đồng "mọi thanh đều có khoá"
    chỉ tồn tại ở `_dong_view`. Chỗ dễ vỡ là ai đó gắn khoá có ĐIỀU KIỆN — đúng lối `boc_tach`/
    `muc` đang làm ngay cạnh — và FE (`Xl2Dong.thuc_te` khai bắt buộc) nhận `undefined` im lặng.
    """
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.xep_lich_2_repo import XepLich2Repository
    from app.services.xep_lich_2 import XepLich2Service

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT6")
    d = _dong_lich(db, cv)
    # Thanh thứ hai: cùng lệnh, nhưng trỏ vào một bước KHÔNG có công việc nào đang chạy.
    chua = XepLichCongDoan(
        nguon=NGUON_LSX, lsx_id=cv.lsx_id, lsx_cong_doan_id=999_999,
        source_thu_tu=1, loai_buoc="to", trang_thai=TT_DA_XEP,
        start_at=_T0 + timedelta(hours=5), finish_at=_T0 + timedelta(hours=6),
    )
    db.add(chua)
    db.commit()

    svc = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
    ban = svc.workspace(tu=_T0.date(), den=(_T0 + timedelta(days=1)).date())
    thanh = {row["id"]: row for row in ban["dong"]}
    assert "thuc_te" in thanh[chua.id] and thanh[chua.id]["thuc_te"] is None
    assert thanh[d.id]["thuc_te"] is not None      # thanh có việc vẫn ra dữ liệu như thường


def test_moc_thuc_te_ghi_bang_utc_that_van_do_dung_so_phut_muon(
    db, orders, lsx_svc, admin, customer
):
    """HỢP ĐỒNG HAI ĐỒNG HỒ (phát hiện 01/09/2026). `du_kien_*` là GIỜ XƯỞNG, còn
    `san_xuat_phien_chay.bat_dau` do `thuc_thi._moc()` ghi bằng UTC THẬT. Trước khi vá,
    `nap_thuc_te` trừ thẳng hai thang nên hụt đúng offset máy chủ (VN: 7 tiếng) rồi bị `_phut()`
    kẹp về 0 — cảnh báo "vào việc muộn" chỉ kêu khi muộn quá 8 tiếng, và con số in ra vẫn sai.
    Test này dựng đúng như production ghi nên nó ĐỎ khi lỗi còn."""
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT9")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 100
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    # Tổ trưởng bấm Bắt đầu lúc 11:00 giờ XƯỞNG — muộn 3 tiếng so với mốc 08:00.
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1,
                            bat_dau=_thuc(_T0 + timedelta(hours=3))))
    db.commit()

    ra = nap_thuc_te(db, [d], bay_gio=_T0 + timedelta(hours=3))[d.id]
    assert ra["tre_bat_dau_phut"] == 180
    assert ra["bat_dau_thuc"].replace(tzinfo=timezone.utc) == _T0 + timedelta(hours=3)


def test_tam_dung_khong_bi_doc_thanh_da_xong(db, orders, lsx_svc, admin, customer):
    """`tam_dung()` ĐÓNG phiên đang mở rồi đặt `CV_TAM_DUNG`, nên sau đó không còn phiên nào
    `ket_thuc IS NULL`. Nếu chỉ soi "hết phiên mở" thì việc đang nằm im bị báo cáo là ĐÃ KẾT THÚC:
    thanh Gantt hết đỏ đúng khoảnh khắc hết ca, và `tre_ket_thuc_phut` ngừng tăng suốt thời gian
    việc đứng — đúng lúc điều độ cần thấy nó phình ra."""
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT10")
    cv.trang_thai = CV_TAM_DUNG
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 100
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1, bat_dau=_thuc(_T0),
                            ket_thuc=_thuc(_T0 + timedelta(hours=6))))
    db.commit()

    ra = nap_thuc_te(db, [d], bay_gio=_T0 + timedelta(hours=10))[d.id]
    assert ra["ket_thuc_thuc"] is None       # tạm dừng ≠ xong
    assert ra["tre_ket_thuc_phut"] == 360    # đo tới BÂY GIỜ, không dừng ở mốc bấm tạm dừng
