"""NGHỈ GIỮA CA — giờ nghỉ của ca là giờ KHÔNG LÀM, cho cả bước máy lẫn bước tổ.

Máy ở xưởng này có người đứng vận hành, nên tới giờ cơm là máy dừng theo người: việc đang chạy dở
tạm nghỉ rồi chạy tiếp, KHÔNG phải làm lại từ đầu và cũng không đẻ thêm lần chạy mới.

Trước 09/09/2026 engine mù chuyện này: `work_shifts.break_start_minute/break_end_minute` chỉ có
chấm công đọc, còn Xếp lịch chạy theo giả định cũ "nghỉ trưa = KHE giữa hai ca liên tiếp"
(`xep_lich_service.LichXuong`). Giả định đó chết từ lúc xưởng khai Ca 1 liền một mạch 06:00–15:00
rồi đẩy giờ nghỉ vào cặp cột break — khe không còn, engine tính 9 tiếng liên tục trong khi màn ca
ghi 8.0 giờ công.

Test ở đây soi HÀM LÁ (không DB) để luật đứng vững độc lập với luồng. Cùng dữ kiện nhưng KHÁC lát
với `test_nghi_giua_ca.py` — file đó soi chấm công (khung tính công của một người), file này soi
xếp lịch (giờ xong · cửa chặn · quỹ giờ máy).
"""
from datetime import datetime, timedelta, timezone

from app.services.xep_lich_2 import constraint as C
from app.services.xep_lich_2 import overlay


def _gio(h: int, m: int = 0, ngay: int = 10) -> datetime:
    return datetime(2026, 9, ngay, h, m, tzinfo=timezone.utc)


# ---------------------------------------------------------------- khoảng nghỉ hiệu lực

def test_ca_ngay_khai_nghi_giua_ca():
    """Ca 1 06:00–15:00 nghỉ 12:00–13:00 (đúng dữ liệu xưởng đang khai)."""
    assert C.doan_nghi_trong_ngay([(360, 900, False, 720, 780)]) == [(720, 780)]


def test_ca_khong_khai_nghi_thi_khong_co_khoang_nao():
    assert C.doan_nghi_trong_ngay([(480, 1020, False, None, None)]) == []


def test_ca_khac_van_lam_thi_khong_tinh_la_nghi():
    """Ca 1 nghỉ 12:00–13:00 nhưng Hành chính 08:00–17:00 vẫn làm ⇒ xưởng KHÔNG nghỉ giờ đó.

    Một mốc chỉ là nghỉ khi MỌI ca đang phủ mốc đó đều đang nghỉ — bằng không vẫn còn người đứng máy.
    """
    ca = [(360, 900, False, 720, 780), (480, 1020, False, None, None)]
    assert C.doan_nghi_trong_ngay(ca) == []


def test_hai_ca_nghi_lech_nhau_chi_lay_phan_giao():
    """Ca 1 nghỉ 12:00–13:00, ca chồng lên nghỉ 12:30–13:30 ⇒ chỉ 12:30–13:00 là cả hai cùng nghỉ."""
    ca = [(360, 900, False, 720, 780), (480, 1020, False, 750, 810)]
    assert C.doan_nghi_trong_ngay(ca) == [(750, 780)]


def test_ca_chieu_qua_nua_dem_nghi_toi():
    """Ca 2 15:00–00:00 nghỉ 18:00–19:00."""
    assert C.doan_nghi_trong_ngay([(900, 1440, False, 1080, 1140)]) == [(1080, 1140)]


def test_ca_dem_nghi_sau_nua_dem():
    """Ca đêm 22:00–06:00 nghỉ 01:00–01:30 — đoạn nghỉ thuộc ĐẦU ngày, không phải đuôi."""
    assert C.doan_nghi_trong_ngay([(1320, 360, True, 60, 90)]) == [(60, 90)]


def test_nghi_khai_ngoai_gio_ca_thi_bo_qua():
    """Khai lỗi (nghỉ 20:00–21:00 của ca 06:00–15:00) không được biến giờ ngoài ca thành nghỉ."""
    assert C.doan_nghi_trong_ngay([(360, 900, False, 1200, 1260)]) == []


# ---------------------------------------------------------------- giờ xong bị đẩy qua nghỉ

NGHI_TRUA = [(720, 780)]   # 12:00–13:00


def test_khong_cham_nghi_thi_giu_nguyen():
    assert C.finish_lien_tuc(_gio(6), 120, NGHI_TRUA) == _gio(8)


def test_viec_vat_qua_nghi_bi_day_dung_do_dai_nghi():
    """4 tiếng từ 10:00 xong 15:00 chứ không phải 14:00 — một tiếng cơm không phải giờ chạy."""
    assert C.finish_lien_tuc(_gio(10), 240, NGHI_TRUA) == _gio(15)


def test_chi_bu_phan_giao_khi_viec_bat_dau_sat_gio_nghi():
    """11:30 chạy 60' ⇒ 30' trước cơm + 30' sau cơm ⇒ xong 13:30."""
    assert C.finish_lien_tuc(_gio(11, 30), 60, NGHI_TRUA) == _gio(13, 30)


def test_bat_dau_trong_gio_nghi_thi_doi_het_nghi_moi_chay():
    """Mốc 12:30 không tiêu phút chạy nào cho tới 13:00."""
    assert C.finish_lien_tuc(_gio(12, 30), 60, NGHI_TRUA) == _gio(14)


def test_viec_dai_nhieu_ngay_an_nhieu_lan_nghi():
    """26 tiếng chạy từ 10:00 vắt qua HAI bữa cơm ⇒ đồng hồ tường 28 tiếng, xong 14:00 hôm sau."""
    assert C.finish_lien_tuc(_gio(10), 26 * 60, NGHI_TRUA) == _gio(14, 0, ngay=11)


def test_viec_dai_chi_bu_dung_so_bua_no_di_qua():
    """20 tiếng từ 10:00 xong 07:00 hôm sau — mới qua MỘT bữa, không được cộng dư bữa thứ hai."""
    assert C.finish_lien_tuc(_gio(10), 20 * 60, NGHI_TRUA) == _gio(7, 0, ngay=11)


def test_khong_khai_nghi_thi_y_nguyen_hanh_vi_cu():
    assert C.finish_lien_tuc(_gio(10), 240) == _gio(14)
    assert C.finish_lien_tuc(_gio(10), 240, []) == _gio(14)


def test_mep_phai_cua_nghi_khong_bi_tinh():
    """Chạy khít tới 12:00 thì xong lúc 12:00, không bị đẩy sang 13:00."""
    assert C.finish_lien_tuc(_gio(10), 120, NGHI_TRUA) == _gio(12)


# ---------------------------------------------------------------- chặn đặt giờ vào bữa cơm

def test_bat_dau_dung_gio_nghi_bi_chan():
    vd = C.trong_gio_nghi(_gio(12, 30), NGHI_TRUA)
    assert vd is not None
    assert vd["muc"] == C.MUC_CHAN_DAT_LICH
    assert vd["ma"] == "nghi_giua_ca"
    assert "12:00" in vd["mo_ta"] and "13:00" in vd["mo_ta"]


def test_bat_dau_dung_mep_het_nghi_thi_qua():
    assert C.trong_gio_nghi(_gio(13), NGHI_TRUA) is None
    assert C.trong_gio_nghi(_gio(12), NGHI_TRUA) is not None    # mép trái là đã nghỉ
    assert C.trong_gio_nghi(_gio(9), NGHI_TRUA) is None
    assert C.trong_gio_nghi(_gio(12, 30), []) is None


# ---------------------------------------------------------------- quỹ giờ & tải máy

def test_quy_gio_ngay_tru_gio_nghi():
    """Ca 1 06:00–15:00 nghỉ một tiếng ⇒ mẫu số đo tải là 480', đúng bằng 8.0 giờ công ở màn ca."""
    ca = [(360, 900, False)]
    assert C.phut_ca_moi_ngay(ca) == 540
    assert C.phut_ca_moi_ngay(ca, NGHI_TRUA) == 480


def test_tai_may_khong_dem_gio_com():
    """Việc 10:00→15:00 chiếm máy 5 tiếng đồng hồ tường nhưng chỉ 4 tiếng là chạy."""
    pl = [(1, _gio(10), _gio(15))]
    ngay = _gio(10).date()
    assert overlay.tai_may(pl, ngay, ngay)[0]["phut_ban"] == 300
    assert overlay.tai_may(pl, ngay, ngay, NGHI_TRUA)[0]["phut_ban"] == 240


def test_tai_may_bo_han_dong_nam_tron_trong_gio_nghi():
    """Không đẻ dòng 0 phút cho việc nằm gọn trong giờ nghỉ (dữ liệu cũ xếp trước khi có luật này)."""
    pl = [(1, _gio(12, 10), _gio(12, 40))]
    ngay = _gio(10).date()
    assert overlay.tai_may(pl, ngay, ngay, NGHI_TRUA) == []


# ---------------------------------------------------------------- lịch xưởng (lát 1)

def test_lich_xuong_tru_nghi_khoi_khung_gio_lam():
    """`LichXuong` là nền tính "Tổng thời gian dẫn" của lệnh — nó cũng phải biết giờ cơm."""
    from app.services.calendar_service import CalendarService
    from app.services.xep_lich_service import LichXuong

    class _Cal(CalendarService):
        def __init__(self):  # không đụng DB
            pass

        def is_working_day(self, d):
            return True

    class _Ca:
        def __init__(self, s, e, od=False):
            self.start_minute, self.end_minute, self.is_overnight = s, e, od

    lich = LichXuong(_Cal(), [_Ca(360, 900)], nghi=NGHI_TRUA)
    khung = lich._khung_ngay(_gio(10).date())
    assert khung == [(_gio(6), _gio(12)), (_gio(13), _gio(15))]
    tong = sum((e - s) // timedelta(minutes=1) for s, e in khung)
    assert tong == 480
