"""Xếp lịch 3 — hàm THUẦN trải thời lượng lên giờ làm việc.

Bám `docs/spec-xep-lich-3.md` §3, §3.1 (ví dụ số), §3.2 (mốc rơi ngoài giờ), §3.3 (thuê ngoài).
Không DB, không ORM: một ca 06:00-14:00, nghỉ cơm 11:00-12:00, T7 + CN nghỉ ⇒ 420 phút chạy/ngày.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services.calendar_service import CalendarService
from app.services.xep_lich_3.trai_lich import BuocVao, trai_lich
from app.services.xep_lich_service import LichXuong


class _Cal(CalendarService):
    """Lịch giả — KHÔNG đụng DB. Đúng lối `test_nghi_giua_ca_xep_lich.py:156`."""

    def __init__(self):
        pass

    def is_working_day(self, d):
        return d.weekday() < 5          # T7 + CN nghỉ


class _Ca:
    """Một dòng `work_shifts` giả: `LichXuong` chỉ đọc ba thuộc tính này."""

    def __init__(self, s, e, od=False):
        self.start_minute, self.end_minute, self.is_overnight = s, e, od


@pytest.fixture
def lich_mot_ca():
    """Dựng thẳng `LichXuong(cal, ca_rows, nghi=...)` như code thật (`xep_lich_service.py:487`)."""
    return LichXuong(_Cal(), [_Ca(6 * 60, 14 * 60)], nghi=((11 * 60, 12 * 60),))


def test_vi_du_so_cua_spec(lich_mot_ca):
    """§3.1: 3 bước = 10h45 chạy, thả T6 11/09/2026 08:00 → xong T2 14/09 12:45.

    Kiểm chéo: T6 từ 08:00 chỉ còn 300 phút chạy; 345 phút còn lại rơi sang T2 (300 phút buổi sáng
    + 45 phút sau bữa cơm) ⇒ 12:45. Đây là HỢP ĐỒNG NGHIỆP VỤ — đỏ thì sửa code, đừng sửa số.
    """
    buoc = [
        BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=345),
        BuocVao(lsx_cong_doan_id=2, thu_tu=2, chay_phut=120),
        BuocVao(lsx_cong_doan_id=3, thu_tu=3, chay_phut=180),
    ]
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), buoc, lich_mot_ca)
    assert kq.bat_dau == datetime(2026, 9, 11, 8, 0)
    assert kq.ket_thuc == datetime(2026, 9, 14, 12, 45)
    assert kq.chay_phut == 645          # 10h45
    assert kq.da_doi is False
    # Mốc từng bước: In xong 06:45, Cán xong 08:45, Bế xong 12:45.
    assert [b.ket_thuc for b in kq.buoc] == [
        datetime(2026, 9, 14, 6, 45),
        datetime(2026, 9, 14, 8, 45),
        datetime(2026, 9, 14, 12, 45),
    ]


def test_moc_roi_vao_gio_nghi_thi_truot_chu_khong_chan(lich_mot_ca):
    """§3.2: thả vào giữa bữa cơm ⇒ trượt tới 12:00 và BÁO, không ném lỗi."""
    buoc = [BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=60)]
    kq = trai_lich(datetime(2026, 9, 11, 11, 30), buoc, lich_mot_ca)
    assert kq.bat_dau == datetime(2026, 9, 11, 12, 0)
    assert kq.da_doi is True


def test_moc_roi_vao_ngay_nghi_thi_truot_sang_dau_ca_ke_tiep(lich_mot_ca):
    buoc = [BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=60)]
    kq = trai_lich(datetime(2026, 9, 12, 9, 0), buoc, lich_mot_ca)   # T7
    assert kq.bat_dau == datetime(2026, 9, 14, 6, 0)                  # T2
    assert kq.da_doi is True


def test_doan_chay_khong_gom_gio_nghi(lich_mot_ca):
    """Thanh hai lớp: tổng các ĐOẠN đúng bằng giờ chạy, khoảng hở là nghỉ/ngoài ca."""
    buoc = [BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=300)]
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), buoc, lich_mot_ca)
    tong = sum((d.den - d.tu).total_seconds() / 60 for d in kq.doan)
    assert tong == pytest.approx(300)
    assert len(kq.doan) == 2                      # bị bữa cơm cắt làm đôi
    assert kq.doan[0].den == datetime(2026, 9, 11, 11, 0)
    assert kq.doan[1].tu == datetime(2026, 9, 11, 12, 0)


def test_doan_cuoi_trung_moc_ket_thuc_cua_buoc(lich_mot_ca):
    """`_cat_doan` và `_cong_gio_lam` phải cho CÙNG một mốc — lệch là thanh vẽ hụt/thừa."""
    buoc = [BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=500)]
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), buoc, lich_mot_ca)
    assert kq.doan[-1].den == kq.ket_thuc


def test_moi_doan_biet_no_thuoc_buoc_nao(lich_mot_ca):
    """Màu khối chạy mã hoá THỨ TỰ bước — mỗi đoạn phải mang chỉ số bước."""
    buoc = [
        BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=60),
        BuocVao(lsx_cong_doan_id=2, thu_tu=2, chay_phut=60),
    ]
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), buoc, lich_mot_ca)
    assert {d.buoc_index for d in kq.doan} == {0, 1}


def test_buoc_theo_THU_TU_khong_theo_thu_tu_list(lich_mot_ca):
    """`routing-dag-thoi-luong`: chuỗi bám `thu_tu`, không bám thứ tự người gọi truyền vào."""
    buoc = [
        BuocVao(lsx_cong_doan_id=9, thu_tu=2, chay_phut=60),
        BuocVao(lsx_cong_doan_id=8, thu_tu=1, chay_phut=60),
    ]
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), buoc, lich_mot_ca)
    assert [b.lsx_cong_doan_id for b in kq.buoc] == [8, 9]


def test_thue_ngoai_chiem_ngay_LICH_khong_tru_ca(lich_mot_ca):
    """§3.3: nhà cung cấp chạy theo lịch của họ — 3 ngày là 3 ngày lịch, kể cả T7/CN."""
    buoc = [
        BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=60),
        BuocVao(lsx_cong_doan_id=2, thu_tu=2, chay_phut=0, thue_ngoai_ngay=3,
                la_thue_ngoai=True),
    ]
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), buoc, lich_mot_ca)
    assert kq.buoc[1].bat_dau == datetime(2026, 9, 11, 9, 0)
    assert kq.buoc[1].ket_thuc == datetime(2026, 9, 14, 9, 0)   # +3 ngày LỊCH, vắt qua T7/CN
    assert kq.chay_phut == 60                                    # bước ngoài KHÔNG tính giờ máy


def test_thue_ngoai_thieu_ngay_thi_chiem_0_va_GHI_CHU(lich_mot_ca):
    """Thiếu ngày gửi/nhận ⇒ chiếm 0 + chú thích. KHÔNG chặn (spec §1: không chặn gì hết)."""
    buoc = [
        BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=60),
        BuocVao(lsx_cong_doan_id=2, thu_tu=2, chay_phut=0, la_thue_ngoai=True),
    ]
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), buoc, lich_mot_ca)
    assert kq.buoc[1].bat_dau == kq.buoc[1].ket_thuc
    assert any("gia công ngoài" in g for g in kq.ghi_chu)


def test_lenh_khong_co_buoc_nao(lich_mot_ca):
    """Routing rỗng: kết thúc = bắt đầu, không nổ."""
    kq = trai_lich(datetime(2026, 9, 11, 8, 0), [], lich_mot_ca)
    assert kq.ket_thuc == kq.bat_dau
    assert kq.doan == []


def test_ba_ca_phu_24_24_thi_thanh_gan_bang_gio_chay():
    """Lưu ý cấu hình ở §3.1: khai đủ 3 ca thì "ngoài ca" ≈ 0 — đó là ĐÚNG, không phải lỗi."""
    lich = LichXuong(_Cal(), [_Ca(360, 840), _Ca(840, 1320), _Ca(1320, 360, True)])
    kq = trai_lich(datetime(2026, 9, 11, 8, 0),
                   [BuocVao(lsx_cong_doan_id=1, thu_tu=1, chay_phut=600)], lich)
    assert kq.ket_thuc == datetime(2026, 9, 11, 18, 0)      # chạy liền mạch 10 tiếng
    assert len(kq.doan) == 1
