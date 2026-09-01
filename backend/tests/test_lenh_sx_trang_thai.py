"""Trạng thái tổng hợp — MỘT trạng thái chính cho bảng, nhiều cờ phụ cho badge.

Thứ tự ưu tiên khi một lệnh dính nhiều thứ cùng lúc (chốt 31/08/2026): Cảnh báo ăn trước Đang
SX. Điều độ quét bảng để TÌM chỗ tắc — lệnh vừa chạy vừa có sự cố mà xếp vào "Đang SX" thì nó
biến mất khỏi tầm mắt đúng lúc cần nhìn nhất.

TÁM FIXTURE của brief KHÔNG có sẵn ở đâu trong repo (đã grep) — dựng hết ở đây trên khuôn
`_dung_lenh` của Task 7 (đơn → PTG → LSX → sửa routing → `release.phat_hanh`), rồi ĐẶT TAY dữ
liệu thực thi (KCS · yêu cầu nhập kho · dòng giao · yêu cầu sửa chữa) đúng như các service ghi.

BA CHỖ CỐ Ý LÀM LỆCH để bài test còn phân biệt được (bài học Task 6 & 7):
  · `lsx.id` vs `order_line_id` — hai bảng id tự tăng ĐỘC LẬP, trên DB test trắng chúng trôi
    song song và bằng nhau. `_don_nen()` tiêu một `order_lines.id` mồi trước mỗi fixture: không
    có nó thì `giao_cua()` và `giao[lsx_id]` cho cùng kết quả, và bài "giao hết" hết canh gì.
  · `du_kien_bat_dau` vs `BAY_GIO` — mọi fixture đẩy lịch lệch hẳn `BAY_GIO`, không để trùng.
  · `su_co` vs `tam_dung` — fixture sự cố giữ công việc ĐANG CHẠY (báo "Vẫn chạy"), fixture tạm
    dừng KHÔNG có sự cố nào. Trộn hai thứ vào một fixture thì hai cờ không tách được.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.delivery import (
    LAN_GIAO_CO_HANG_DEN_TAY, LG_THANH_CONG, LG_THAT_BAI, DeliveryRequest,
    DeliveryRequestLine, DeliveryTrip, DeliveryTripLine,
)
from app.models.department import Department
from app.models.employee import Employee
from app.models.kho_hang import KhoHang
from app.models.ky_thuat_may import (
    TT_YC_CHO_TIEP_NHAN, TT_YC_DA_TAO_PHIEU, TT_YC_TU_CHOI, YeuCauSuaChua,
)
from app.models.lsx import Lsx, LsxCongDoan
from app.models.order import Order, OrderLine
from app.models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG
from app.models.san_xuat_kcs import (
    KCS_DAT, KCS_DAT_MOT_PHAN, KCS_KHONG_DAT, SanXuatKcsBatch,
)
from app.models.san_xuat_kho import (
    YC_CHO_KHO, YC_DA_NHAP, YC_HUY, SanXuatKhoHang, SanXuatNhapKhoYc,
)
from app.models.san_xuat_thuc_thi import PHIEN_KET_THUC, SanXuatPhienChay
from app.services.lenh_sx import boi_canh, trang_thai
from app.services.san_xuat import kcs, kho, release

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _hai_lsx_san_sang, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)
# Khuôn dựng lệnh + đọc công việc của Task 7 — plain function, không phải fixture.
from tests.test_lenh_sx_tien_do import (
    BAY_GIO as _BAY_GIO_TIEN_DO, _cong_viec, _cv_ghep, _dung_lenh,
)
# Dàn cảnh KCS THẬT (đơn → SX → phát hành vào tổ khoán → batch KCS qua service).
from tests.test_san_xuat_kcs import _batch

BAY_GIO = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)

# `_dung_lenh` dựng lịch quanh MỐC CỦA NÓ. Hai mốc lệch nhau là mọi con số sàn/trễ hạn ở đây
# lệch theo mà không ai thấy — chốt bằng một assert thay vì một dòng chú thích.
assert BAY_GIO == _BAY_GIO_TIEN_DO

_HAN_XA = date(2026, 12, 31)      # hạn còn rất xa ⇒ `tre_han` phải trả False vì lý do THẬT
_T0 = BAY_GIO - timedelta(hours=4)
_T1 = BAY_GIO - timedelta(hours=3)

_dem_mo = 0


def _don_nen(db) -> None:
    """Dọn nền TRƯỚC mỗi lần `_dung_lenh` — hai việc, hai lý do khác nhau.

    1. Tiêu một `order_lines.id` mồi để `lsx.id` KHÔNG còn trùng `order_line_id`. `Lsx` và
       `OrderLine` là hai bảng id tự tăng ĐỘC LẬP, mà `_hai_lsx_san_sang` luôn sinh đúng 2 dòng ở
       cả hai bảng ⇒ trên DB test trắng hai chuỗi trôi song song và `lsx.id == order_line_id` LUÔN
       đúng (Task 6 đã đo). Để vậy thì `bc.giao_cua(lsx_id)` và `bc.giao[lsx_id]` trả CÙNG một
       thứ, và bài "giao hết" không phân biệt được cách tra đúng với cách tra sai.
    2. Nhường lại TÊN TỔ. `_dung_lenh` (Task 7) tạo tổ với tên cứng "Tổ Tiến độ", mà
       `departments.name`/`.code` là UNIQUE — bài nào cần từ hai lệnh trở lên sẽ nổ
       `IntegrityError` ở lần dựng thứ hai. Đổi tên tổ CŨ chứ không xoá: công việc đã phát hành
       neo `department_id`, không neo tên, nên lệnh dựng trước không đổi gì.
    """
    global _dem_mo
    _dem_mo += 1
    don = Order(order_no=f"DH-TT8-MOI-{_dem_mo}")
    db.add(don)
    db.flush()
    db.add(OrderLine(order_id=don.id))
    for d in db.query(Department).filter(Department.name == "Tổ Tiến độ").all():
        d.name = f"Tổ Tiến độ {_dem_mo}"
        d.code = f"TO-TIEN-DO-{_dem_mo}"
    db.commit()


def _aware_utc(dt: datetime) -> datetime:
    """SQLite trả datetime NAIVE — ép aware UTC trước khi so với `BAY_GIO` (bẫy tái phát của repo)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _tt(db, lsx_id):
    return trang_thai.trang_thai_chinh(boi_canh.nap(db, [lsx_id]), lsx_id, BAY_GIO)


def _co(db, lsx_id, **kw):
    return trang_thai.co_canh_bao(boi_canh.nap(db, [lsx_id]), lsx_id, BAY_GIO, **kw)


def _dat_han(db, lsx_id, han=_HAN_XA) -> None:
    db.get(Lsx, lsx_id).han_hoan_thanh_sx = han
    db.commit()


def _xong(db, cv) -> None:
    """Đóng một công việc ĐÚNG NHƯ PRODUCTION: `completed` + MỘT PHIÊN ĐÃ ĐÓNG.

    LUẬT FIXTURE (Vòng sửa 1): đặt tay `cv.trang_thai = 'completed'` mà không đẻ phiên nào là một
    thế giới không tồn tại — `thuc_thi.ket_thuc:396-406` đóng phiên đang mở rồi mới đặt `completed`,
    và phiên đó do `bat_dau` mở ra trước. Hôm nay `tien_do.du_kien_xong` ĐỌC `bc.phien` (thang ba
    bậc cho lệnh đã xong), nên fixture nói dối sẽ đẩy bài test sang nhánh 2 mà không ai biết.

    Mốc phiên bám mốc KẾ HOẠCH của chính bước đó; bước không có mốc thì lùi về hai giờ trước
    `BAY_GIO` (vẫn là quá khứ — phiên đã đóng không thể kết thúc ở tương lai).
    """
    bd = cv.du_kien_bat_dau or (BAY_GIO - timedelta(hours=3))
    kt = cv.du_kien_ket_thuc or (BAY_GIO - timedelta(hours=2))
    # KẸP về quá khứ: một phiên ĐÃ ĐÓNG không thể kết thúc ở tương lai (`thuc_thi.ket_thuc` ghi
    # `now`). Fixture nào có lịch kế hoạch nằm ở tương lai mà không kẹp sẽ đẻ ra mốc đó, và
    # `_moc_da_xong` bậc 1 sẽ trả một mốc xong TƯƠNG LAI cho một lệnh đã đóng.
    kt = min(_aware_utc(kt), BAY_GIO)
    bd = min(_aware_utc(bd), kt)
    cv.trang_thai = CV_HOAN_THANH
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1, bat_dau=bd, ket_thuc=kt,
        loai_dong=PHIEN_KET_THUC,
    ))
    db.commit()


def _dang_chay(db, cv, bat_dau=None) -> None:
    """Đặt một công việc ĐANG CHẠY đúng như production: `running` + MỘT PHIÊN CÒN MỞ.

    `thuc_thi.bat_dau` là đường ghi `running` DUY NHẤT và nó luôn `add(phien)` với `ket_thuc=None`.
    Đặt tay mỗi cột trạng thái là dựng một thế giới không tồn tại — và từ Vòng sửa 2 thì phiên MỞ
    là thứ load-bearing: `tien_do.du_kien_xong` đọc `bc.phien` để quyết mốc xong của lệnh.
    """
    bd = bat_dau or cv.du_kien_bat_dau or (BAY_GIO - timedelta(hours=1))
    cv.trang_thai = CV_DANG_CHAY
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1, bat_dau=min(_aware_utc(bd), BAY_GIO), ket_thuc=None,
    ))
    db.commit()


def _kcs_batch(db, cv_id, *, nhan, dat, khong_dat, ket_luan) -> SanXuatKcsBatch:
    """Một batch KCS đúng khuôn `kcs.tao_batch_kcs` ghi ra (§13.1): số nhận = đạt + không đạt,
    kết luận suy từ số, neo `cong_viec_id` của công việc KCS."""
    kb = SanXuatKcsBatch(
        cong_viec_id=cv_id, bat_dau=_T0, ket_thuc=_T1,
        so_luong_nhan=nhan, so_luong_dat=dat, so_luong_khong_dat=khong_dat,
        don_vi="cái", ket_luan=ket_luan,
    )
    db.add(kb)
    db.commit()
    return kb


def _nhap_kho_yc(db, lsx_id, kb, *, yeu_cau, xac_nhan, trang_thai_yc) -> SanXuatNhapKhoYc:
    """Một yêu cầu nhập kho thành phẩm đúng khuôn `kho.tao_yeu_cau_nhap_thanh_pham` ghi ra.

    `hang.lsx_id = None` là CỐ Ý và đúng production: registry THÀNH PHẨM neo theo (đơn, nhóm), và
    `kho._get_or_create_hang` được gọi với `lsx_id=None` cứng (`services/san_xuat/kho.py:132`).
    Đặt `lsx_id=lsx_id` ở đây cho "dễ xanh" là dựng một fixture nói dối — cầu thật đi qua
    `kcs_batch → cong_viec → lsx`, và đó là cầu bài test này phải soi.
    """
    lsx = db.get(Lsx, lsx_id)
    hang = SanXuatKhoHang(
        ma=f"HSX-T8-{kb.id}", loai_hang="thanh_pham", order_id=lsx.order_id,
        lsx_id=None, cong_doan_ref_id=None, ten="Thành phẩm", don_vi="cái",
    )
    db.add(hang)
    db.flush()
    yc = SanXuatNhapKhoYc(
        kcs_batch_id=kb.id, hang_id=hang.id, order_id=lsx.order_id,
        so_luong_yeu_cau=yeu_cau, so_luong_xac_nhan=xac_nhan, don_vi="cái",
        trang_thai=trang_thai_yc,
    )
    db.add(yc)
    db.commit()
    return yc


def _giao(db, lsx_id, qty, *, ma="YCGH-T8") -> DeliveryRequestLine:
    """Một YÊU CẦU giao — mới là lời hứa, hàng CHƯA đi. Không đẻ chuyến nào."""
    lsx = db.get(Lsx, lsx_id)
    req = DeliveryRequest(code=ma, order_id=lsx.order_id, ngay_can_giao=date(2026, 9, 10))
    db.add(req)
    db.flush()
    line = DeliveryRequestLine(request_id=req.id, order_line_id=lsx.order_line_id, qty=qty)
    db.add(line)
    db.commit()
    return line


def _tai_xe(db) -> Employee:
    e = db.query(Employee).filter_by(code="NV-GIAO-T8").one_or_none()
    if e is None:
        e = Employee(code="NV-GIAO-T8", full_name="Tài xế T8")
        db.add(e)
        db.flush()
    return e


def _chuyen(db, line: DeliveryRequestLine, qty, *, ket_qua=LG_THANH_CONG, lan=1) -> DeliveryTrip:
    """Một LẦN GIAO có kết quả — nơi số THỰC NHẬN sống (`delivery_trip_lines.qty_giao`).

    Yêu cầu giao KHÔNG tự cộng vào "đã giao": `delivery_repo.da_giao_theo_dong:123-138` chỉ cộng
    qua chuyến trong `LAN_GIAO_CO_HANG_DEN_TAY`. Fixture phải đi đúng đường đó.

    DÒNG HÀNG chỉ đẻ khi chuyến CÓ HÀNG ĐẾN TAY, đúng như production: `delivery_service` gọi
    `_ghi_dong_thuc_nhan` (`:858`) CHỈ trong nhánh `thanh_cong`/`giao_thieu`; nhánh thất bại đi
    thẳng sang lý do + hướng xử lý, không ghi dòng nào. Bản Vòng sửa 1 đẻ dòng cho mọi kết quả —
    fixture nói dối (Vòng sửa 2, mục G).

    KHÔNG có cửa sau nào để đẻ dòng hàng cho chuyến ngoài tập ấy. Vòng sửa 3 đã rà: đường ghi
    `delivery_trip_lines` là DUY NHẤT (`delivery_repo.add_trip_line:169` ← `_ghi_dong_thuc_nhan`
    ← `ghi_ket_qua:833` đòi `dang_giao` rồi đóng ngay sang `thanh_cong`/`giao_thieu`), và không
    chuyển trạng thái nào đưa chuyến ĐÃ CÓ dòng hàng ra khỏi tập đó. Muốn thêm chuyến ngoài tập
    thì đừng kèm dòng hàng — kèm là dựng một thế giới không tồn tại.
    """
    trip = DeliveryTrip(
        request_id=line.request_id, lan_thu=lan, employee_id=_tai_xe(db).id,
        gio_lay_hang=BAY_GIO - timedelta(hours=6), gio_du_kien_giao=BAY_GIO - timedelta(hours=4),
        trang_thai=ket_qua,
    )
    db.add(trip)
    db.flush()
    if ket_qua in LAN_GIAO_CO_HANG_DEN_TAY:
        db.add(DeliveryTripLine(trip_id=trip.id, order_line_id=line.order_line_id, qty_giao=qty))
    db.commit()
    return trip


def _giao_xong(db, lsx_id, qty, *, ma="YCGH-T8", ket_qua=LG_THANH_CONG) -> DeliveryRequestLine:
    """Yêu cầu giao + chuyến ĐÃ CÓ KẾT QUẢ — khách thực nhận `qty`."""
    line = _giao(db, lsx_id, qty, ma=ma)
    _chuyen(db, line, qty, ket_qua=ket_qua)
    return line


def _su_co(db, lsx_id, cv_id, *, tt=TT_YC_CHO_TIEP_NHAN, ma="YC-T8-1") -> YeuCauSuaChua:
    """Một yêu cầu sửa chữa đúng khuôn `san_xuat/su_co.bao_su_co` ghi ra: neo `lsx_id = cv.lsx_id`
    + `cong_viec_id` (`services/san_xuat/su_co.py:118-120`), `may_dung` = có dừng SX hay không."""
    yc = YeuCauSuaChua(
        ma=ma, may_id=9_001, cong_viec_id=cv_id, lsx_id=lsx_id,
        bo_phan_hong="Cụm cấp giấy", muc_do="trung_binh", may_dung=False, trang_thai=tt,
    )
    db.add(yc)
    db.commit()
    return yc


def _ba_buoc_xong_tru_kcs(db, orders, lsx_svc, admin, customer) -> tuple[int, list]:
    """Lệnh 3 bước: CTP · In (cả hai ĐÃ XONG) · KCS cuối (chưa xong). Trả `(lsx_id, cvs)`.

    Lịch đẩy về QUÁ KHỨ để `du_kien_bat_dau` không trùng `BAY_GIO` — đúng cặp giá trị từng che
    lỗi ở Task 7.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In offset", 360, 5_000), ("KCS cuối", 30, 5_000)],
        bat_dau_lech=timedelta(days=-1),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    _xong(db, cvs[1])
    cvs[2].la_kcs = True
    cvs[2].la_kcs_cuoi = True
    db.commit()
    _dat_han(db, lsx_id)
    return lsx_id, cvs


def _da_qua_kcs(db, orders, lsx_svc, admin, customer, *, dat, khong_dat, ket_luan):
    """Như trên nhưng bước KCS ĐÃ ĐÓNG và đã có một batch kết luận. Trả `(lsx_id, cvs, batch)`."""
    lsx_id, cvs = _ba_buoc_xong_tru_kcs(db, orders, lsx_svc, admin, customer)
    _xong(db, cvs[2])
    db.commit()
    kb = _kcs_batch(db, cvs[2].id, nhan=dat + khong_dat, dat=dat, khong_dat=khong_dat,
                    ket_luan=ket_luan)
    return lsx_id, cvs, kb


# --- 8 fixture của brief ------------------------------------------------------------------------
@pytest.fixture
def lenh_dang_chay(db, orders, lsx_svc, admin, customer) -> int:
    """Đã phát hành, CTP xong, In đang chạy. KHÔNG cảnh báo nào — và hạn đặt CÒN XA chứ không để
    trống: hạn NULL làm `tre_han` trả False mà không hề chạy qua luật nào."""
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In offset", 360, 5_000)],
        bat_dau_lech=timedelta(hours=-2),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    _dang_chay(db, cvs[1])
    _dat_han(db, lsx_id)
    return lsx_id


@pytest.fixture
def lenh_dang_chay_co_su_co(db, orders, lsx_svc, admin, customer) -> int:
    """Đang chạy + MỘT sự cố chưa tiếp nhận, báo kiểu "Vẫn chạy" (công việc KHÔNG tạm dừng).

    Giữ công việc ở `running` là chủ ý: nếu fixture này cũng tạm dừng luôn thì cờ `su_co` và cờ
    `tam_dung` cùng bật, và bài "sự cố ăn trước Đang SX" hoá ra chỉ canh cờ tạm dừng.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In offset", 360, 5_000)],
        bat_dau_lech=timedelta(hours=-2),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    _dang_chay(db, cvs[1])
    _dat_han(db, lsx_id)
    _su_co(db, lsx_id, cvs[1].id)
    return lsx_id


@pytest.fixture
def lenh_tam_dung(db, orders, lsx_svc, admin, customer) -> int:
    """Công việc `paused`, KHÔNG có sự cố nào — để cờ `tam_dung` đứng một mình."""
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In offset", 360, 5_000)],
        bat_dau_lech=timedelta(hours=-2),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    cvs[1].trang_thai = CV_TAM_DUNG
    db.commit()
    _dat_han(db, lsx_id)
    return lsx_id


@pytest.fixture
def lenh_dang_kcs(db, orders, lsx_svc, admin, customer) -> int:
    """Mọi bước SX đã xong, còn bước KCS cuối chưa đóng và chưa có batch nào."""
    lsx_id, _cvs = _ba_buoc_xong_tru_kcs(db, orders, lsx_svc, admin, customer)
    return lsx_id


@pytest.fixture
def lenh_kcs_dat_chua_nhap(db, orders, lsx_svc, admin, customer) -> int:
    """KCS đóng, batch kết luận ĐẠT 5.000 — nhưng chưa có yêu cầu nhập kho nào."""
    lsx_id, _cvs, _kb = _da_qua_kcs(db, orders, lsx_svc, admin, customer,
                                    dat=5_000, khong_dat=0, ket_luan=KCS_DAT)
    return lsx_id


@pytest.fixture
def lenh_da_nhap_kho(db, orders, lsx_svc, admin, customer) -> int:
    """KCS đạt + kho ĐÃ XÁC NHẬN NHẬN đủ 5.000, chưa có dòng giao nào."""
    lsx_id, _cvs, kb = _da_qua_kcs(db, orders, lsx_svc, admin, customer,
                                   dat=5_000, khong_dat=0, ket_luan=KCS_DAT)
    _nhap_kho_yc(db, lsx_id, kb, yeu_cau=5_000, xac_nhan=5_000, trang_thai_yc=YC_DA_NHAP)
    return lsx_id


@pytest.fixture
def lenh_giao_het(db, orders, lsx_svc, admin, customer) -> int:
    """Như trên + chuyến giao THÀNH CÔNG phủ ĐỦ `so_luong_dat` của lệnh."""
    lsx_id, _cvs, kb = _da_qua_kcs(db, orders, lsx_svc, admin, customer,
                                   dat=5_000, khong_dat=0, ket_luan=KCS_DAT)
    _nhap_kho_yc(db, lsx_id, kb, yeu_cau=5_000, xac_nhan=5_000, trang_thai_yc=YC_DA_NHAP)
    _giao_xong(db, lsx_id, db.get(Lsx, lsx_id).so_luong_dat)
    return lsx_id


@pytest.fixture
def lenh_kcs_khong_dat(db, orders, lsx_svc, admin, customer) -> int:
    """Batch KCS kết luận KHÔNG ĐẠT toàn bộ ⇒ không có số đạt nào để đẻ tồn giao được."""
    lsx_id, _cvs, _kb = _da_qua_kcs(db, orders, lsx_svc, admin, customer,
                                    dat=0, khong_dat=5_000, ket_luan=KCS_KHONG_DAT)
    return lsx_id


# --- 9 bài của brief ------------------------------------------------------------------------------
def test_dang_chay_ra_dang_sx(db, lenh_dang_chay):
    assert _tt(db, lenh_dang_chay) == trang_thai.TAB_DANG_SX


def test_su_co_chua_dong_an_truoc_dang_sx(db, lenh_dang_chay_co_su_co):
    assert _tt(db, lenh_dang_chay_co_su_co) == trang_thai.TAB_CANH_BAO


def test_tam_dung_ra_canh_bao(db, lenh_tam_dung):
    assert _tt(db, lenh_tam_dung) == trang_thai.TAB_CANH_BAO


def test_toi_kcs_ra_kcs(db, lenh_dang_kcs):
    assert _tt(db, lenh_dang_kcs) == trang_thai.TAB_KCS


def test_kcs_dat_chua_nhap_kho_ra_cho_nhap_kho(db, lenh_kcs_dat_chua_nhap):
    assert _tt(db, lenh_kcs_dat_chua_nhap) == trang_thai.TAB_CHO_NHAP_KHO


def test_co_ton_chua_giao_ra_san_sang_giao(db, lenh_da_nhap_kho):
    assert _tt(db, lenh_da_nhap_kho) == trang_thai.TAB_SAN_SANG_GIAO


def test_giao_het_ra_hoan_thanh(db, lenh_giao_het):
    assert _tt(db, lenh_giao_het) == trang_thai.TAB_HOAN_THANH


def test_kcs_khong_dat_khong_tao_ton_giao_duoc(db, lenh_kcs_khong_dat):
    assert _tt(db, lenh_kcs_khong_dat) != trang_thai.TAB_SAN_SANG_GIAO


def test_co_phu_van_hien_du(db, lenh_dang_chay_co_su_co):
    co = trang_thai.co_canh_bao(boi_canh.nap(db, [lenh_dang_chay_co_su_co]),
                                lenh_dang_chay_co_su_co, BAY_GIO)
    assert "su_co" in co


# --- Bổ sung A: hằng + cờ đúng TẬP đã chốt, không hơn không kém ------------------------------------
def test_dung_sau_tab_va_nam_co(db):
    """Sáu tab · năm cờ. Đẻ thêm một ô là FE phải đoán chỗ hiện nó."""
    assert len(trang_thai.TAB_CHINH) == 6
    assert len(set(trang_thai.TAB_CHINH)) == 6
    assert set(trang_thai.CO_CANH_BAO) == {
        "su_co", "tam_dung", "tre_han", "kcs_khong_dat", "thieu_vat_tu"
    }


def test_moi_tab_deu_la_gia_tri_tra_ve_that(db, lenh_dang_chay, lenh_dang_chay_co_su_co,
                                            lenh_dang_kcs, lenh_kcs_dat_chua_nhap,
                                            lenh_da_nhap_kho, lenh_giao_het):
    """Sáu fixture ⇒ sáu tab KHÁC NHAU. Một cài đặt gộp hai nhánh (vd. bỏ hẳn `TAB_CHO_NHAP_KHO`)
    vẫn qua được từng bài lẻ ở trên nếu bài kia dùng fixture khác; bài này chặn đường đó."""
    ra = [_tt(db, i) for i in (lenh_dang_chay, lenh_dang_chay_co_su_co, lenh_dang_kcs,
                               lenh_kcs_dat_chua_nhap, lenh_da_nhap_kho, lenh_giao_het)]
    assert len(set(ra)) == 6, ra
    assert set(ra) == set(trang_thai.TAB_CHINH), ra


def test_canh_bao_an_truoc_ca_ba_tab_khau_sau(db, lenh_dang_kcs, lenh_kcs_dat_chua_nhap,
                                              lenh_da_nhap_kho):
    """Cảnh báo ăn trước KHÔNG chỉ Đang SX, mà cả KCS · Chờ nhập kho · Sẵn sàng giao.

    Bài này bổ sung sau NGHI THỨC ĐỘT BIẾN: hạ nhánh `co_canh_bao` xuống dưới ba nhánh khâu sau
    mà cả bộ vẫn XANH — mọi fixture cảnh báo đều đang đứng ở khâu SX, nên chỉ cặp
    "Cảnh báo vs Đang SX" có lưới. Ở đây gắn một sự cố CÒN MỞ vào ba lệnh đã đi xa hơn: điều độ
    phải thấy chúng ở tab Cảnh báo, không phải nằm im trong tab của khâu.
    """
    for lsx_id in (lenh_dang_kcs, lenh_kcs_dat_chua_nhap, lenh_da_nhap_kho):
        truoc = _tt(db, lsx_id)
        _su_co(db, lsx_id, _cong_viec(db, lsx_id)[1].id, ma=f"YC-T8-UT-{lsx_id}")
        assert _co(db, lsx_id) == ["su_co"]
        assert _tt(db, lsx_id) == trang_thai.TAB_CANH_BAO, (lsx_id, truoc)


# --- Bổ sung B: cờ tách bạch, không dính chùm -----------------------------------------------------
def test_su_co_khong_keo_theo_tam_dung(db, lenh_dang_chay_co_su_co):
    """Báo sự cố kiểu "Vẫn chạy" ⇒ ĐÚNG một cờ `su_co`. Cả hai cờ cùng bật nghĩa là một trong hai
    đang đọc nhầm nguồn."""
    assert _co(db, lenh_dang_chay_co_su_co) == ["su_co"]


def test_tam_dung_khong_keo_theo_su_co(db, lenh_tam_dung):
    assert _co(db, lenh_tam_dung) == ["tam_dung"]


def test_nam_co_cung_bat_giu_dung_thu_tu_co_canh_bao(db, orders, lsx_svc, admin, customer):
    """Một lệnh dính CẢ NĂM cờ ⇒ list trả về đúng thứ tự `CO_CANH_BAO`.

    Vòng sửa 1 — Q5. Mọi bài khác chỉ có MỘT cờ bật, nên thứ tự badge không có lưới ở đâu cả: đảo
    hai nhánh trong `co_canh_bao` là cả bộ vẫn xanh, còn FE thì đổi thứ tự badge giữa hai lần tải
    mà không ai biết vì sao. Docstring module hứa "THEO THỨ TỰ `CO_CANH_BAO`" — đây là chỗ giữ lời.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In offset", 360, 5_000), ("KCS giữa chừng", 30, 5_000)],
        bat_dau_lech=timedelta(hours=-2),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    cvs[1].trang_thai = CV_TAM_DUNG          # cờ 2
    cvs[2].la_kcs = True                     # `tao_batch_kcs:110` chỉ ghi được lên bước `la_kcs`
    db.commit()
    _su_co(db, lsx_id, cvs[1].id, ma="YC-T8-NAM")                                       # cờ 1
    _dat_han(db, lsx_id, date(2026, 8, 1))                                              # cờ 3
    _kcs_batch(db, cvs[2].id, nhan=5_000, dat=0, khong_dat=5_000, ket_luan=KCS_KHONG_DAT)  # cờ 4

    co = _co(db, lsx_id, den_vat_tu={lsx_id: "do"})                                     # cờ 5
    assert co == list(trang_thai.CO_CANH_BAO), co
    bc = boi_canh.nap(db, [lsx_id])
    assert trang_thai.trang_thai_chinh(
        bc, lsx_id, BAY_GIO, den_vat_tu={lsx_id: "do"}) == trang_thai.TAB_CANH_BAO


def test_lenh_sach_khong_co_co_nao(db, lenh_dang_chay):
    """Tiền đề của mọi bài ưu tiên: fixture nền phải THẬT SỰ sạch cờ, không phải sạch vì luật nào
    đó chưa chạy. Hạn đã đặt (còn xa) nên `tre_han` có chạy và trả False vì lý do thật."""
    assert db.get(Lsx, lenh_dang_chay).han_hoan_thanh_sx is not None
    assert _co(db, lenh_dang_chay) == []


def test_su_co_da_tu_choi_khong_con_la_canh_bao(db, lenh_dang_chay_co_su_co):
    """`tu_choi` = không phải hỏng / báo trùng / xử lý tại chỗ ⇒ đóng thật, cờ phải TẮT."""
    yc = db.query(YeuCauSuaChua).filter_by(lsx_id=lenh_dang_chay_co_su_co).one()
    yc.trang_thai = TT_YC_TU_CHOI
    db.commit()
    assert _co(db, lenh_dang_chay_co_su_co) == []
    assert _tt(db, lenh_dang_chay_co_su_co) == trang_thai.TAB_DANG_SX


def test_su_co_da_tao_phieu_khong_con_giuong_co(db, lenh_dang_chay_co_su_co):
    """Đã sinh phiếu sửa chữa ⇒ tổ kỹ thuật đã cầm việc; trạng thái ĐÓNG của phiếu nằm ở
    `ky_thuat_sua_chua`, bảng mà `BoiCanh` không nạp. Lấy `da_tao_phieu` làm cờ thì mọi lệnh từng
    hỏng máy nằm ở tab Cảnh báo VĨNH VIỄN — chốt luật hẹp (`TT_YC_DANG_MO`) bằng một bài."""
    yc = db.query(YeuCauSuaChua).filter_by(lsx_id=lenh_dang_chay_co_su_co).one()
    yc.trang_thai = TT_YC_DA_TAO_PHIEU
    db.commit()
    assert _co(db, lenh_dang_chay_co_su_co) == []


# --- Bổ sung C: trễ hạn đi qua `tien_do`, và `xong` truyền vào được dùng ---------------------------
def test_tre_han_ra_canh_bao(db, lenh_dang_chay):
    """Cùng một lệnh sạch, chỉ kéo hạn về quá khứ ⇒ nhảy sang Cảnh báo. Không fixture riêng: đổi
    đúng MỘT biến thì mới biết chắc biến đó là nguyên nhân."""
    assert _tt(db, lenh_dang_chay) == trang_thai.TAB_DANG_SX
    _dat_han(db, lenh_dang_chay, date(2026, 8, 1))
    assert _co(db, lenh_dang_chay) == ["tre_han"]
    assert _tt(db, lenh_dang_chay) == trang_thai.TAB_CANH_BAO


def test_dung_moc_xong_ben_goi_truyen_vao(db, lenh_dang_chay):
    """Màn 200 lệnh tính `du_kien_xong` MỘT lần rồi truyền lại — nếu `co_canh_bao` bỏ qua tham số
    đó mà tự tính, trang phải duyệt đường găng 400 lượt. Truyền một mốc quá khứ ⇒ phải ra TRỄ."""
    _dat_han(db, lenh_dang_chay, date(2026, 8, 1))
    bc = boi_canh.nap(db, [lenh_dang_chay])
    assert trang_thai.co_canh_bao(bc, lenh_dang_chay, BAY_GIO, xong=None) == []
    assert trang_thai.co_canh_bao(
        bc, lenh_dang_chay, BAY_GIO, xong=BAY_GIO + timedelta(days=30)) == ["tre_han"]


# --- Bổ sung D: KCS — không đạt là cảnh báo, đạt-một-phần là chuyện thường -------------------------
def test_kcs_khong_dat_ra_canh_bao_kem_co(db, lenh_kcs_khong_dat):
    assert _tt(db, lenh_kcs_khong_dat) == trang_thai.TAB_CANH_BAO
    assert _co(db, lenh_kcs_khong_dat) == ["kcs_khong_dat"]


def test_dat_mot_phan_khong_phai_canh_bao(db, orders, lsx_svc, admin, customer):
    """In offset luôn có tờ hỏng — `dat_mot_phan` là ca THƯỜNG. Coi nó là cảnh báo thì gần như mọi
    lệnh đều đeo cờ và tab Cảnh báo hết tác dụng lọc."""
    lsx_id, _cvs, kb = _da_qua_kcs(db, orders, lsx_svc, admin, customer,
                                   dat=4_800, khong_dat=200, ket_luan=KCS_DAT_MOT_PHAN)
    _nhap_kho_yc(db, lsx_id, kb, yeu_cau=4_800, xac_nhan=4_800, trang_thai_yc=YC_DA_NHAP)
    assert _co(db, lsx_id) == []
    assert _tt(db, lsx_id) == trang_thai.TAB_SAN_SANG_GIAO


# --- Bổ sung E: kho — "chờ nhập" vs "đã có tồn" tách theo SỐ ĐÃ XÁC NHẬN ---------------------------
def test_yeu_cau_chua_duoc_kho_nhan_van_la_cho_nhap_kho(db, orders, lsx_svc, admin, customer):
    """Đã lập yêu cầu nhưng kho chưa nhận món nào (`so_luong_xac_nhan = 0`) ⇒ vẫn CHỜ NHẬP KHO.
    Đọc "có yêu cầu" thay vì "đã xác nhận" là báo sẵn-sàng-giao cho hàng còn nằm ở tổ."""
    lsx_id, _cvs, kb = _da_qua_kcs(db, orders, lsx_svc, admin, customer,
                                   dat=5_000, khong_dat=0, ket_luan=KCS_DAT)
    _nhap_kho_yc(db, lsx_id, kb, yeu_cau=5_000, xac_nhan=0, trang_thai_yc=YC_CHO_KHO)
    assert _tt(db, lsx_id) == trang_thai.TAB_CHO_NHAP_KHO


def test_yeu_cau_da_huy_khong_tinh_la_co_ton(db, orders, lsx_svc, admin, customer):
    """KCS huỷ phần chưa nhận để phân loại lại (§14.1) — yêu cầu `huy` KHÔNG được đếm là tồn."""
    lsx_id, _cvs, kb = _da_qua_kcs(db, orders, lsx_svc, admin, customer,
                                   dat=5_000, khong_dat=0, ket_luan=KCS_DAT)
    _nhap_kho_yc(db, lsx_id, kb, yeu_cau=5_000, xac_nhan=0, trang_thai_yc=YC_HUY)
    assert _tt(db, lsx_id) == trang_thai.TAB_CHO_NHAP_KHO


def test_kcs_giua_chuoi_khong_phai_dang_o_kcs(db, orders, lsx_svc, admin, customer):
    """Bước KCS GIỮA chuỗi chưa đóng KHÔNG có nghĩa lệnh "đang ở KCS" — bước In vẫn đang chạy.

    Bổ sung sau NGHI THỨC ĐỘT BIẾN: vế "mọi bước không-KCS đã xong" của `_dang_o_kcs` trước đó
    không có lưới nào (mọi fixture đều đặt KCS ở cuối chuỗi). Bỏ vế đó thì lệnh này rời tab Đang
    SX sang tab KCS, tức là giấu một lệnh đang chạy máy khỏi đúng tab điều độ nhìn.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("KCS giữa chừng", 30, 5_000), ("In offset", 360, 5_000)],
        bat_dau_lech=timedelta(hours=-2),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    cvs[1].la_kcs = True                    # KCS giữa chuỗi, CHƯA đóng
    db.commit()
    _dang_chay(db, cvs[2])                   # In vẫn đang chạy ⇒ lệnh vẫn ở khâu SX
    _dat_han(db, lsx_id)
    assert _co(db, lsx_id) == []
    assert _tt(db, lsx_id) == trang_thai.TAB_DANG_SX


def test_thieu_so_luong_dat_thi_khong_phai_hoan_thanh(db, lenh_giao_het):
    """`so_luong_dat` = 0 ⇒ KHÔNG có số cam kết nào để phủ.

    Bổ sung sau NGHI THỨC ĐỘT BIẾN: cửa `dat <= 0` của `_da_giao_het` trước đó không có lưới. Coi
    "0 ≥ 0" là giao xong thì mọi lệnh thiếu dữ liệu rơi thẳng vào tab Hoàn thành — biến mất khỏi
    mọi tab điều hành mà không ai bấm gì.
    """
    assert _tt(db, lenh_giao_het) == trang_thai.TAB_HOAN_THANH
    db.get(Lsx, lenh_giao_het).so_luong_dat = 0
    db.commit()
    assert _tt(db, lenh_giao_het) == trang_thai.TAB_SAN_SANG_GIAO


def test_giao_thieu_van_la_san_sang_giao(db, lenh_da_nhap_kho):
    """Giao MỘT PHẦN chưa phải xong: còn hàng trong kho thì lệnh vẫn nằm ở Sẵn sàng giao."""
    dat = db.get(Lsx, lenh_da_nhap_kho).so_luong_dat
    assert dat > 1
    _giao_xong(db, lenh_da_nhap_kho, dat - 1)
    assert _tt(db, lenh_da_nhap_kho) == trang_thai.TAB_SAN_SANG_GIAO


def test_giao_het_doc_dung_dong_cua_lenh_khong_phai_dong_trung_id(db, lenh_giao_het):
    """`giao` khoá theo `order_line_id`; `lsx.id` trùng khoảng giá trị nên `giao[lsx_id]` trả
    NHẦM dòng của lệnh khác mà không nổ. Chốt tiền đề hai id đã LỆCH — không có `_don_nen()` thì
    bài này xanh cả khi cài đặt tra nhầm khoá."""
    lsx = db.get(Lsx, lenh_giao_het)
    assert lsx.id != lsx.order_line_id, "hai id lại trùng — bài này hết phân biệt được hai cách tra"
    assert _tt(db, lenh_giao_het) == trang_thai.TAB_HOAN_THANH


def test_hoan_thanh_an_truoc_canh_bao(db, lenh_giao_het):
    """Lệnh đã giao hết mà quá hạn SX thì vẫn là HOÀN THÀNH, không phải Cảnh báo.

    Cảnh báo sinh ra để điều độ TÌM CHỖ TẮC; lệnh đã ra khỏi nhà máy không còn chỗ nào để tắc.
    Hạn 01/08 trong khi mốc xong THẬT (phiên đã đóng) là 30/08 ⇒ lệnh này trễ thật, cờ `tre_han`
    đúng — nhưng nó vẫn phải nằm ở tab Hoàn thành.
    """
    _dat_han(db, lenh_giao_het, date(2026, 8, 1))
    assert "tre_han" in _co(db, lenh_giao_het)
    assert _tt(db, lenh_giao_het) == trang_thai.TAB_HOAN_THANH


def test_hoan_thanh_an_truoc_canh_bao_ke_ca_khi_con_su_co(db, lenh_giao_het):
    """Lưới THỨ HAI cho cùng luật, KHÔNG đi qua `tre_han`.

    Vòng sửa 1 sửa `tien_do.du_kien_xong` để lệnh đã xong không còn bật `tre_han` vô cớ. Nếu lưới
    duy nhất của luật này dựa vào `tre_han`, một ngày nào đó chỉnh mốc trong fixture là lưới bốc
    hơi mà không ai biết. Sự cố còn treo là cờ độc lập với mọi mốc thời gian: hàng đã tới tay
    khách thì việc sửa máy là chuyện của tổ kỹ thuật, không phải chỗ tắc trên bảng lệnh.
    """
    _su_co(db, lenh_giao_het, _cong_viec(db, lenh_giao_het)[1].id, ma="YC-T8-HT")
    assert _co(db, lenh_giao_het) == ["su_co"]
    assert _tt(db, lenh_giao_het) == trang_thai.TAB_HOAN_THANH


def test_yeu_cau_giao_du_so_nhung_chua_co_chuyen_khong_phai_hoan_thanh(db, lenh_da_nhap_kho):
    """Lập yêu cầu giao đủ số KHÔNG phải là đã giao (Vòng sửa 1 — P3).

    `delivery_request_lines.qty` là số YÊU CẦU; số thực nhận nằm ở `delivery_trip_lines.qty_giao`
    và chỉ tính qua chuyến trong `LAN_GIAO_CO_HANG_DEN_TAY`. Đếm `qty` là báo "Hoàn thành" cho
    hàng vẫn đang nằm trong kho.
    """
    dat = db.get(Lsx, lenh_da_nhap_kho).so_luong_dat
    _giao(db, lenh_da_nhap_kho, dat)                       # yêu cầu đủ số, KHÔNG có chuyến nào
    assert _tt(db, lenh_da_nhap_kho) == trang_thai.TAB_SAN_SANG_GIAO


def test_chuyen_that_bai_khong_tinh_la_da_giao(db, lenh_da_nhap_kho):
    """Xe chạy rồi mà khách không nhận ⇒ vẫn còn hàng phải giao.

    Chuyến thất bại KHÔNG có dòng hàng nào (production không ghi — xem `_chuyen`), nên bài này
    canh đúng một điều: có chuyến rồi thì cũng không được lấy `DeliveryRequestLine.qty` ra cộng.
    """
    dat = db.get(Lsx, lenh_da_nhap_kho).so_luong_dat
    _giao_xong(db, lenh_da_nhap_kho, dat, ket_qua=LG_THAT_BAI)
    assert db.query(DeliveryTripLine).count() == 0, "chuyến hỏng mà vẫn đẻ dòng hàng — fixture sai"
    assert _tt(db, lenh_da_nhap_kho) == trang_thai.TAB_SAN_SANG_GIAO


# --- Bổ sung F: cờ vật tư đọc LẠI đèn của `lsx_tong_quan`, không tính lại --------------------------
def test_thieu_vat_tu_lay_tu_den_truyen_vao(db, lenh_dang_chay):
    """Đèn vật tư là số ĐẮT (một lượt `can_doi()` cho cả trang) nên bên gọi đọc một lần rồi truyền
    vào. Không truyền ⇒ cờ KHÔNG được đoán bừa."""
    assert _co(db, lenh_dang_chay) == []
    assert _co(db, lenh_dang_chay, den_vat_tu={lenh_dang_chay: "do"}) == ["thieu_vat_tu"]
    assert _co(db, lenh_dang_chay, den_vat_tu={lenh_dang_chay: "vang"}) == []
    assert _co(db, lenh_dang_chay, den_vat_tu={}) == []
    assert _tt(db, lenh_dang_chay) == trang_thai.TAB_DANG_SX
    bc = boi_canh.nap(db, [lenh_dang_chay])
    assert trang_thai.trang_thai_chinh(
        bc, lenh_dang_chay, BAY_GIO, den_vat_tu={lenh_dang_chay: "do"}
    ) == trang_thai.TAB_CANH_BAO


def test_den_vat_tu_theo_lo_doc_lai_lsx_tong_quan(db, lenh_dang_chay):
    """Hàm cầu phải trả đúng `{lsx_id: mức}` của `lsx_tong_quan.tong_quan` — gọi MỘT lần cho cả lô
    (gọi từng lệnh là đẻ lại đúng N+1 mà Task 6 sinh ra để chặn)."""
    from app.services import lsx_tong_quan

    den = trang_thai.den_vat_tu_theo_lo(db, [lenh_dang_chay])
    assert set(den) == {lenh_dang_chay}
    goc = lsx_tong_quan.tong_quan(db, [lenh_dang_chay])[0]["den"]["vat_tu"]["muc"]
    assert den[lenh_dang_chay] == goc


# --- Bổ sung G: bước bị BÀI GHÉP phủ vẫn phải giương cờ --------------------------------------------
@pytest.fixture
def lenh_ca_ghep_tam_dung(db, orders, lsx_svc, admin, customer) -> int:
    """Ca in GHÉP đang TẠM DỪNG, còn hai bước riêng của lệnh thì không.

    Bước bị bài ghép phủ không đẻ công việc riêng — nó nằm ở công việc CHUNG (`lsx_id IS NULL`).
    Đọc `bc.cong_viec[lsx_id]` thay vì `cong_viec_du` thì lệnh này báo "Đang SX" trong khi máy in
    đang đứng, và đứng IM LẶNG. Đây đúng là lỗi Nghiêm trọng của Task 7, ở một tầng khác.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In ghép", 360, 5_000), ("Cắt thành phẩm", 30, 5_000)],
        ghep=[1], bat_dau_lech=timedelta(days=-2),
    )
    _xong(db, _cong_viec(db, lsx_id)[0])
    _cv_ghep(db, lsx_id).trang_thai = CV_TAM_DUNG
    db.commit()
    _dat_han(db, lsx_id)
    return lsx_id


def test_ca_ghep_tam_dung_van_ra_canh_bao(db, lenh_ca_ghep_tam_dung):
    bc = boi_canh.nap(db, [lenh_ca_ghep_tam_dung])
    # Tiền đề: không bước RIÊNG nào của lệnh đang tạm dừng — nếu có, bài này xanh cả khi cài đặt
    # bỏ qua công việc ghép, và hết canh gì.
    rieng = bc.cong_viec[lenh_ca_ghep_tam_dung]
    assert len(rieng) == 2, "bước bị ghép phủ vẫn đẻ công việc riêng — tiền đề hỏng"
    assert all(cv.trang_thai != CV_TAM_DUNG for cv in rieng)

    assert _co(db, lenh_ca_ghep_tam_dung) == ["tam_dung"]
    assert _tt(db, lenh_ca_ghep_tam_dung) == trang_thai.TAB_CANH_BAO


def test_su_co_bao_tren_ca_ghep_van_ve_duoc_lenh(db, orders, lsx_svc, admin, customer):
    """Sự cố báo trên bước bị BÀI GHÉP phủ vẫn phải giương cờ cho lệnh nằm trên tờ in ấy.

    Bổ sung sau NGHI THỨC ĐỘT BIẾN của Vòng sửa 1: bỏ vế `cong_viec_id IN cv_ids` của câu 10
    (`boi_canh`) mà cả bộ vẫn XANH — không bài nào dựng sự cố trên công việc GHÉP.

    `su_co.bao_su_co:120` neo `lsx_id = cv.lsx_id`, mà công việc ghép có `lsx_id IS NULL`, nên
    đường "khoá theo lsx_id" hụt HOÀN TOÀN: máy in đứng vì hỏng mà không lệnh nào trong ca đeo cờ,
    và đứng IM LẶNG. Đường về duy nhất là qua `cong_viec_id`.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In ghép", 360, 5_000), ("Cắt thành phẩm", 30, 5_000)],
        ghep=[1], bat_dau_lech=timedelta(hours=-2),
    )
    _xong(db, _cong_viec(db, lsx_id)[0])
    cv_ghep = _cv_ghep(db, lsx_id)
    assert cv_ghep.lsx_id is None, "công việc ghép phải có lsx_id NULL — tiền đề hỏng"
    # Ghi ĐÚNG như `bao_su_co`: `cong_viec_id` của công việc GHÉP, `lsx_id` = `cv.lsx_id` = NULL.
    db.add(YeuCauSuaChua(
        ma="YC-T8-GHEP", may_id=9_002, cong_viec_id=cv_ghep.id, lsx_id=None,
        bo_phan_hong="Đầu phun mực", muc_do="cao", may_dung=False,
        trang_thai=TT_YC_CHO_TIEP_NHAN,
    ))
    db.commit()
    _dat_han(db, lsx_id)

    assert _co(db, lsx_id) == ["su_co"]
    assert _tt(db, lsx_id) == trang_thai.TAB_CANH_BAO


def test_su_co_khong_ghep_chi_ve_lenh_dung_MOT_lan(db, lenh_dang_chay_co_su_co):
    """Sự cố trên bước RIÊNG khớp CẢ HAI vế của câu 10 ⇒ phải khử trùng, chỉ vào map một lần.

    Vòng sửa 2 — mục C. Bỏ khử trùng ở `boi_canh` mà cả hai file test vẫn xanh: mọi bài khác chỉ
    hỏi "có sự cố không" (`any(...)`), mà `any` không phân biệt một với hai. Đếm mới phân biệt
    được — và số đếm ấy là thứ màn hồ sơ sẽ hiện ra ("2 sự cố" cho một sự cố duy nhất).
    """
    bc = boi_canh.nap(db, [lenh_dang_chay_co_su_co])
    ds = bc.su_co[lenh_dang_chay_co_su_co]
    # Tiền đề: sự cố này khớp cả hai vế — neo lsx_id VÀ neo cong_viec_id của một bước riêng.
    assert len(ds) == 1, [(y.id, y.lsx_id, y.cong_viec_id) for y in ds]
    assert ds[0].lsx_id == lenh_dang_chay_co_su_co and ds[0].cong_viec_id is not None
    assert len({y.id for y in ds}) == 1


# --- Bổ sung I: batch KCS GIỮA CHỪNG không được lái tab (Vòng sửa 1 — Nghiêm trọng 1) -------------
def test_batch_kcs_giua_chung_khong_keo_ra_khoi_dang_sx(db, orders, lsx_svc, admin, customer):
    """Kiểm tra GIỮA CHỪNG đẻ batch đạt, nhưng máy in vẫn đang chạy ⇒ lệnh vẫn ở Đang SX.

    `kcs.tao_batch_kcs:110` chỉ đòi `cv.la_kcs`, KHÔNG đòi bước cuối — nên bất kỳ chốt kiểm giữa
    chuyền nào cũng đẻ số đạt. Cộng số đó vào cửa "chờ nhập kho" thì lệnh bị đẩy sang một tab mà
    kho sẽ KHÔNG BAO GIỜ nhận hàng (yêu cầu nhập kho chỉ sinh từ batch của KCS cuối) — lệnh kẹt
    ở đó vĩnh viễn, không có đường tự thoát.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("KCS giữa chừng", 30, 5_000), ("In offset", 360, 5_000)],
        bat_dau_lech=timedelta(hours=-2),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    cvs[1].la_kcs = True                    # KCS giữa chuyền — KHÔNG phải `la_kcs_cuoi`
    _xong(db, cvs[1])
    db.commit()
    _dang_chay(db, cvs[2])                   # In vẫn đang chạy
    _kcs_batch(db, cvs[1].id, nhan=5_000, dat=5_000, khong_dat=0, ket_luan=KCS_DAT)
    _dat_han(db, lsx_id)

    assert not cvs[1].la_kcs_cuoi, "tiền đề hỏng — bước giữa chuyền không được là KCS cuối"
    assert _co(db, lsx_id) == []
    assert _tt(db, lsx_id) == trang_thai.TAB_DANG_SX


def test_batch_kcs_giua_chung_khong_lai_tab_du_may_da_ngung(db, orders, lsx_svc, admin, customer):
    """Cùng luật, nhưng KHÔNG có vế "máy còn chạy" đỡ hộ — đây mới là lưới của bộ lọc `la_kcs_cuoi`.

    Bổ sung sau NGHI THỨC ĐỘT BIẾN của Vòng sửa 1: gỡ `if cv.la_kcs_cuoi` khỏi `_so_kcs_dat_cuoi`
    mà bài trên vẫn XANH, vì ở đó bước In còn `running` nên cửa `_sx_da_xong` chặn trước. Hai thay
    đổi cùng nằm trong một nhánh thì phải có hai bài, không thì một trong hai không có lưới.

    Ở đây mọi bước máy ĐÃ XONG, chốt kiểm GIỮA CHUYỀN đã đóng và đẻ 5.000 đạt, còn KCS CUỐI thì
    chưa kiểm gì. Lệnh đang ở KCS. Đếm cả batch giữa chuyền là đẩy nó sang Chờ nhập kho — nơi kho
    sẽ không bao giờ nhận hàng, vì yêu cầu nhập kho chỉ sinh từ batch của KCS cuối.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In offset", 360, 5_000),
              ("KCS giữa chừng", 30, 5_000), ("KCS cuối", 30, 5_000)],
        bat_dau_lech=timedelta(days=-1),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    _xong(db, cvs[1])
    cvs[2].la_kcs = True
    _xong(db, cvs[2])
    cvs[3].la_kcs = True
    cvs[3].la_kcs_cuoi = True               # chưa đóng, chưa có batch nào
    db.commit()
    _kcs_batch(db, cvs[2].id, nhan=5_000, dat=5_000, khong_dat=0, ket_luan=KCS_DAT)
    _dat_han(db, lsx_id)

    assert not cvs[2].la_kcs_cuoi
    assert cvs[3].trang_thai != CV_HOAN_THANH
    assert _co(db, lsx_id) == []
    assert _tt(db, lsx_id) == trang_thai.TAB_KCS


def test_con_may_dang_chay_thi_chua_phai_cho_nhap_kho(db, orders, lsx_svc, admin, customer):
    """KCS cuối đã chốt được một phần ĐẠT nhưng một nhánh SX song song CÒN CHẠY ⇒ vẫn Đang SX.

    Bổ sung sau NGHI THỨC ĐỘT BIẾN của Vòng sửa 1: bỏ vế `_sx_da_xong` khỏi `_kcs_dat_cho_nhap`
    mà cả bộ vẫn XANH — mọi fixture khác đều đã xong hết bước máy trước khi KCS đẻ batch.

    Ca thật: Ruột in xong và KCS kiểm trước phần ruột, còn Bìa vẫn đang cán. Điều độ CẦN thấy
    lệnh này ở tab Đang SX vì vẫn còn máy phải chạy; đẩy nó sang Chờ nhập kho là giấu một việc
    chưa làm xong khỏi đúng tab người ta nhìn để đốc thúc.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In ruột", 240, 5_000),
              ("Cán bìa", 180, 5_000), ("KCS cuối", 30, 5_000)],
        canh=[(0, 1), (0, 2), (1, 3), (2, 3)],
        bat_dau_lech=timedelta(hours=-6),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    _xong(db, cvs[1])
    cvs[3].la_kcs = True
    cvs[3].la_kcs_cuoi = True
    db.commit()
    _dang_chay(db, cvs[2])                   # Bìa VẪN đang cán
    _kcs_batch(db, cvs[3].id, nhan=2_000, dat=2_000, khong_dat=0, ket_luan=KCS_DAT)
    _dat_han(db, lsx_id)

    assert _co(db, lsx_id) == []
    assert _tt(db, lsx_id) == trang_thai.TAB_DANG_SX


def test_kho_nhan_mot_phan_ma_may_con_chay_van_la_dang_sx(db, orders, lsx_svc, admin, customer):
    """Kho ĐÃ NHẬN 2.000 nhưng máy in còn chạy ⇒ vẫn Đang SX, không phải Sẵn sàng giao.

    Vòng sửa 2 — mục B. `_co_ton_thanh_pham` đứng TRÊN hai nhánh vừa được thêm cửa "sản xuất đã
    xong" ở vòng trước mà chính nó lại không có cửa đó. Tồn từng phần là chi tiết của màn hồ sơ;
    lấy nó làm cớ đổi tab là để một lệnh còn phải chạy máy biến khỏi tầm mắt điều độ.
    """
    _don_nen(db)
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("KCS giữa chừng", 30, 5_000), ("In offset", 360, 5_000)],
        bat_dau_lech=timedelta(hours=-2),
    )
    cvs = _cong_viec(db, lsx_id)
    _xong(db, cvs[0])
    cvs[1].la_kcs = True
    _xong(db, cvs[1])
    db.commit()
    _dang_chay(db, cvs[2])                   # In VẪN đang chạy
    kb = _kcs_batch(db, cvs[1].id, nhan=2_000, dat=2_000, khong_dat=0, ket_luan=KCS_DAT)
    _nhap_kho_yc(db, lsx_id, kb, yeu_cau=2_000, xac_nhan=2_000, trang_thai_yc=YC_DA_NHAP)
    _dat_han(db, lsx_id)

    bc = boi_canh.nap(db, [lsx_id])
    # Tiền đề: kho THẬT SỰ đã nhận — nếu không, bài này xanh vì lý do khác hẳn.
    assert [float(y.so_luong_xac_nhan) for y in bc.nhap_kho_yc[lsx_id]] == [2_000.0]
    assert _co(db, lsx_id) == []
    assert _tt(db, lsx_id) == trang_thai.TAB_DANG_SX


def test_co_hang_dat_cho_nhap_an_truoc_tab_kcs(db, orders, lsx_svc, admin, customer):
    """Bước KCS CUỐI chưa đóng nhưng đã chốt được một phần ĐẠT ⇒ Chờ nhập kho, không phải KCS.

    Vòng sửa 1 — M-D: hai nhánh này trước đó đảo chỗ cho nhau mà cả bộ vẫn xanh. Luật là KHÂU XA
    NHẤT: có hàng đạt nằm chờ kho là đã đi xa hơn "đang kiểm".
    """
    lsx_id, cvs = _ba_buoc_xong_tru_kcs(db, orders, lsx_svc, admin, customer)
    _dang_chay(db, cvs[2])                   # KCS cuối CHƯA đóng
    _kcs_batch(db, cvs[2].id, nhan=3_000, dat=3_000, khong_dat=0, ket_luan=KCS_DAT)

    assert cvs[2].la_kcs and cvs[2].la_kcs_cuoi
    assert _tt(db, lsx_id) == trang_thai.TAB_CHO_NHAP_KHO


# --- Bổ sung J: NHÓM nhiều lệnh — kho nhận là sự thật cấp NHÓM (Vòng sửa 1 — Nghiêm trọng 2) ------
def _buoc_routing(db, lsx_id):
    return (
        db.query(LsxCongDoan)
        .filter(LsxCongDoan.lsx_id == lsx_id)
        .order_by(LsxCongDoan.thu_tu, LsxCongDoan.id)
        .all()
    )


@pytest.fixture
def nhom_hai_lenh(db, orders, lsx_svc, admin, customer) -> tuple[int, int]:
    """Một NHÓM thành phẩm gồm HAI lệnh cùng nhãn — đúng ca "Ruột + Bìa → Kỷ yếu" của spec.

    Chỉ lệnh THÂN CHÍNH kết thúc bằng bước KCS. `snapshot.danh_dau_kcs_cuoi:137-171` chỉ đánh
    `la_kcs_cuoi` cho MỘT ứng viên mỗi nhóm, nên lệnh còn lại không có bước KCS nào ⇒ nó không có
    đường tự lập yêu cầu nhập kho; hàng của nó đi kèm hàng của thân chính.

    Tổ KCS để `head_user_id = admin` vì `kcs.tao_batch_kcs`/`kho.*` đều qua `thuc_thi._gate:63`
    (chỉ tổ trưởng đúng tổ). Trả `(than_chinh, phu)`.
    """
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.get(OrderLine, a.order_line_id).nhom = "Kỷ yếu"
    db.get(OrderLine, b.order_line_id).nhom = "Kỷ yếu"
    to_kcs = Department(
        name="KCS Nhóm T8", code="KCS-NHOM-T8", is_kcs=True, la_san_xuat=True,
        head_user_id=admin.id,
    )
    db.add(to_kcs)
    db.flush()
    _buoc_routing(db, a.id)[-1].department_id = to_kcs.id
    db.commit()

    release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()
    return a.id, b.id


def _nhom_qua_kcs_vao_kho(db, admin, than: int, *, so_luong=100) -> int:
    """Chạy ĐÚNG service: batch KCS trên bước KCS-cuối của thân chính → yêu cầu nhập kho → kho
    xác nhận nhận. Trả `yc_id`."""
    cv = [c for c in _cong_viec(db, than) if c.la_kcs_cuoi]
    assert len(cv) == 1, "nhóm phải có đúng một bước KCS-cuối — tiền đề hỏng"
    cv = cv[0]
    cv.don_vi_vao = cv.don_vi_ra = "cái"
    db.commit()
    _dang_chay(db, cv)                    # `tao_batch_kcs` chỉ ghi cho công việc đã khởi động
    rb = kcs.tao_batch_kcs(
        db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
        so_luong_nhan=so_luong, so_luong_dat=so_luong, so_luong_khong_dat=0,
    )
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=so_luong)
    k = KhoHang(ma="KHO-TP-NHOM", ten="Kho thành phẩm nhóm")
    db.add(k)
    db.flush()
    kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=so_luong, kho_id=k.id)
    return yc["yc_id"]


def test_lenh_phu_trong_nhom_cung_thay_hang_da_nhap_kho(db, nhom_hai_lenh, admin):
    """Kho nhận hàng của NHÓM ⇒ MỌI lệnh thành viên phải đọc được, không riêng thân chính.

    Yêu cầu nhập kho neo `(order_id, nhom_id)` (`kho.py:123-137`) chứ không neo lệnh. Cầu duy
    nhất qua batch KCS chỉ về được thân chính, nên lệnh phụ có `nhap_kho_yc` RỖNG VĨNH VIỄN — nó
    không bao giờ rời `dang_sx` dù hàng đã nằm trong kho.
    """
    than, phu = nhom_hai_lenh
    yc_id = _nhom_qua_kcs_vao_kho(db, admin, than)

    bc = boi_canh.nap(db, [than, phu])
    assert [y.id for y in bc.nhap_kho_yc[than]] == [yc_id]
    assert [y.id for y in bc.nhap_kho_yc[phu]] == [yc_id]

    # NHƯNG đọc được yêu cầu KHÔNG có nghĩa là đã sẵn sàng giao: lệnh phụ chưa chạy bước nào.
    # (Vòng sửa 2 — bản trước của bài này chốt thẳng `san_sang_giao`, tức là CHỐT một hành vi sai:
    # một lệnh chưa ai đụng vào mà nằm ở tab Sẵn sàng giao.)
    _dat_han(db, phu)
    assert trang_thai.trang_thai_chinh(bc, phu, BAY_GIO) == trang_thai.TAB_DANG_SX

    # Đóng nốt sản xuất của lệnh phụ ⇒ lúc này mới sẵn sàng, và đó chính là chỗ cầu nhóm có ích:
    # lệnh phụ không có batch KCS nào của riêng nó, hàng nó nằm trong lô kho của NHÓM.
    for cv in _cong_viec(db, phu):
        _xong(db, cv)
    bc2 = boi_canh.nap(db, [than, phu])
    assert trang_thai.trang_thai_chinh(bc2, phu, BAY_GIO) == trang_thai.TAB_SAN_SANG_GIAO


# --- Bổ sung H: chuỗi kho THẬT — fixture đặt tay không được nói dối --------------------------------
def test_chuoi_kho_that_noi_duoc_ve_lenh(db, orders, lsx_svc, admin, customer):
    """Chạy ĐÚNG service kho (`tao_yeu_cau_nhap_thanh_pham` → `kho_xac_nhan_nhap`) rồi soi bối cảnh.

    Bài này là LƯỚI CHỐNG FIXTURE NÓI DỐI: mọi fixture khác đặt tay `SanXuatNhapKhoYc`, nên nếu
    cầu nối thật giữa yêu cầu nhập kho và lệnh bị đứt, chỉ có bài này đỏ. Nó ĐÃ đỏ một lần: registry
    thành phẩm luôn có `lsx_id IS NULL` (`kho.py:127`) nên cầu cũ `hang.lsx_id` không bao giờ nối
    được — xem báo cáo Task 8.
    """
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, nhan=100, dat=100, khong_dat=0)
    lsx_id = cv.lsx_id
    assert lsx_id is not None
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=100)
    k = KhoHang(ma="KHO-TP-T8", ten="Kho thành phẩm T8")
    db.add(k)
    db.flush()
    kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=100, kho_id=k.id)

    hang = db.get(SanXuatKhoHang, yc["hang_id"])
    assert hang.lsx_id is None, "registry thành phẩm đổi cách neo — đọc lại kho.py trước khi tin"

    bc = boi_canh.nap(db, [lsx_id])
    assert [y.id for y in bc.nhap_kho_yc[lsx_id]] == [yc["yc_id"]]
    assert float(bc.nhap_kho_yc[lsx_id][0].so_luong_xac_nhan) == 100
