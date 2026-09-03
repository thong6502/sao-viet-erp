"""Tiến độ KHÔNG đếm số công đoạn — nó là trung bình có TRỌNG SỐ theo thời lượng kế hoạch.

Vì sao: một lệnh có CTP 15 phút và In 6 tiếng; xong CTP mà báo 50% là nói dối điều độ. Bốn
luật: trọng số theo thời lượng · công đoạn đang chạy ăn phần theo sản lượng tốt · thiếu thời
lượng thì chia đều VÀ giương cờ `uoc_tinh` · routing song song đi theo ĐƯỜNG GĂNG.

Và một luật thà im còn hơn đoán: thiếu lịch/mục tiêu/thời lượng ⇒ `du_kien_xong` trả None để
UI hiện "Chưa đủ dữ liệu", KHÔNG bịa ra một mốc giờ.

TÁM FIXTURE của brief KHÔNG có sẵn ở đâu trong repo (đã grep) — dựng hết ở đây, KHÔNG tạo
`Lsx`/`SanXuatCongViec` bằng tay: đi luồng thật đơn → PTG → LSX → (kế hoạch sửa routing) →
`release.phat_hanh`, đúng khuôn `tests/test_lenh_sx_boi_canh.py`. Thứ duy nhất bài test đụng
tay là DỮ LIỆU THỰC THI (thời lượng kế hoạch trên snapshot, batch sản lượng, phiên chạy) — vốn
do xếp lịch/tổ ghi vào ở các pha khác.

BẪY ID SONG SONG (bài học Task 6): `san_xuat_cong_viec.id` và `lsx_cong_doan.id` đều là int tự
tăng, DB test trắng cho hai dãy chạy song song ⇒ bài canh "nối cạnh phụ thuộc qua
`lsx_cong_doan_id`" mất hết ý nghĩa (lấy nhầm khoá vẫn xanh). `_dung_lenh` ĐỐT 30 id
`lsx_cong_doan` cho hai dãy lệch hẳn nhau, và `test_song_song_lay_duong_gang` chốt tiền đề đó
bằng một assert.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
from app.models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from app.models.lsx import LB_MAY, LsxCongDoan, LsxCongDoanPhuThuoc
from app.models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, SanXuatCongViec
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.san_xuat_thuc_thi import PHIEN_KET_THUC, PHIEN_TAM_DUNG, SanXuatPhienChay
from app.services.lenh_sx import boi_canh, tien_do
from app.services.san_xuat import release

from tests.test_san_xuat_board import (  # noqa: F401
    _to_moi, admin, customer, db, lsx_svc, orders,
)
from tests.test_xep_lich_service import _hai_lsx_san_sang

BAY_GIO = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)


# --- Khuôn dựng lệnh --------------------------------------------------------------------------
def _dung_lenh(
    db, orders, lsx_svc, admin, customer, *,
    buoc, canh=None, ghep=None, bat_dau_lech=timedelta(0), lech_buoc=None,
) -> int:
    """Một lệnh ĐÃ PHÁT HÀNH với routing do bài test mô tả. Trả `lsx_id`.

    `buoc` = list `(ten, phut | None, so_luong_ra)`; `phut=None` nghĩa là bước KHÔNG có thời lượng
    kế hoạch (chưa xếp lịch). `canh` = list cặp CHỈ SỐ `(trước, sau)`; None ⇒ chuỗi tuyến tính
    0→1→2… đúng như `LsxService.tao` sinh mặc định.

    `ghep` = list CHỈ SỐ bước bị MỘT công đoạn bài ghép phủ. Những bước đó KHÔNG đẻ công việc
    riêng — cả cụm dùng chung một `SanXuatCongViec` có `lsx_id IS NULL` (`snapshot.dung_cong_viec`).
    Thời lượng gắn cho công việc chung lấy theo bước ĐẦU trong cụm, các bước sau bỏ qua.

    `bat_dau_lech` đẩy mốc `du_kien_bat_dau` của CẢ lệnh ra xa `BAY_GIO`. Mặc định 0 để 8 fixture
    cũ giữ nguyên hành vi — nhưng chính chỗ trùng đó từng che lỗi "bỏ qua mốc bắt đầu kế hoạch",
    nên fixture mới PHẢI lệch.

    `lech_buoc` = `{chỉ số bước: timedelta}` — đẩy riêng MỘT bước ra xa, mô phỏng lịch thật khi
    một khâu phải chờ máy/vật tư: `t0 = max(tiền nhiệm xong, gốc + lệch)`. Đẩy như vậy CASCADE
    xuống các bước sau, đúng cách bàn xếp lịch làm. Đây là thứ duy nhất dựng được ca "sàn của bước
    GIỮA chuỗi vượt hẳn mốc mà tiền nhiệm đẩy tới" — ca mà nhánh Kahn (nhánh chạy thật) mới chạm
    tới, và trước vòng này không bài nào canh.

    Sửa routing ở trạng thái `san_sang` là thao tác THẬT của kế hoạch (routing chỉ bị khoá từ
    `da_lap_ke_hoach` trở đi). Thời lượng kế hoạch gắn SAU phát hành vì fixture không đi qua bàn
    xếp lịch — `thoi_gian_lsx_step`/`thoi_gian_bg_step` trả (None, None, None) nên snapshot ra đời
    với hai mốc rỗng.
    """
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    to = _to_moi(db, "Tổ Tiến độ", "TO-TIEN-DO")

    # ĐỐT id `lsx_cong_doan` (gắn vào lệnh b — lệnh không phát hành) để dãy id của nó lệch hẳn dãy
    # `san_xuat_cong_viec`. Không đốt thì hai dãy trôi song song và mọi bài canh KHOÁ đều vô nghĩa.
    for i in range(30):
        db.add(LsxCongDoan(lsx_id=b.id, thu_tu=900 + i, ten=f"Đốt id {i}"))
    db.flush()

    for cd in db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == a.id).all():
        db.delete(cd)
    db.flush()

    canh = canh if canh is not None else [(k, k + 1) for k in range(len(buoc) - 1)]
    assert all(i < j for i, j in canh), "khuôn này chỉ nhận cạnh đi tới (chỉ số tăng dần)"

    buocs: list[LsxCongDoan] = []
    for i, (ten, _phut, sl_ra) in enumerate(buoc):
        cd = LsxCongDoan(
            lsx_id=a.id, thu_tu=i, ten=ten, nhom="print", department_id=to.id,
            loai_buoc=LB_MAY, so_luong_vao=sl_ra, so_luong_ra=sl_ra,
            don_vi_vao="to", don_vi_ra="to",
        )
        db.add(cd)
        buocs.append(cd)
    db.flush()
    for i, j in canh:
        db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=buocs[i].id, buoc_sau_id=buocs[j].id))
    db.commit()

    # Bài ghép phải tồn tại TRƯỚC khi phát hành: `snapshot.dung_cong_viec` đọc bảng phủ để biết
    # bước nào KHÔNG được đẻ công việc riêng. Dựng sau phát hành là snapshot đã sai từ gốc.
    bg_ids: set[int] = set()
    chung = None
    if ghep:
        sl_ghep = buoc[ghep[0]][2]
        bg = BaiGhep(ma=f"GB-TD-{a.id}", ten="Bài ghép tiến độ")
        db.add(bg)
        db.flush()
        chung = BaiGhepCongDoan(
            bai_ghep_id=bg.id, thu_tu=0, ten="Ca chạy ghép", nhom="print",
            department_id=to.id, loai_buoc=LB_MAY,
            so_luong_vao=sl_ghep, so_luong_ra=sl_ghep, don_vi_vao="to", don_vi_ra="to",
        )
        db.add(chung)
        db.flush()
        db.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=2))
        for i in ghep:
            db.add(BaiGhepCongDoanMap(
                bai_ghep_cong_doan_id=chung.id, lsx_id=a.id, lsx_step_key=buocs[i].step_key,
            ))
        db.commit()
        bg_ids = {bg.id}

    release.phat_hanh(db, lsx_ids={a.id}, bai_ghep_ids=bg_ids, actor=admin)
    db.commit()

    cv_theo_buoc = {
        cv.lsx_cong_doan_id: cv
        for cv in db.query(SanXuatCongViec).filter(SanXuatCongViec.lsx_id == a.id).all()
    }
    cv_chung = (
        db.query(SanXuatCongViec).filter_by(bai_ghep_cong_doan_id=chung.id).one()
        if chung is not None else None
    )
    # Mốc kế hoạch phải NHẤT QUÁN với đồ thị phụ thuộc: bước bắt đầu sau khi MỌI tiền nhiệm xong,
    # hai nhánh song song cùng khởi hành từ bước cha. Cộng dồn tuần tự cho routing rẽ nhánh là
    # dựng ra một lịch mà chính bàn xếp lịch không bao giờ sinh — và khi `du_kien_xong` tôn trọng
    # mốc bắt đầu (sàn), cái lịch bịa đó biến bài canh đường găng thành bài canh phép cộng.
    goc = BAY_GIO + bat_dau_lech
    truoc: dict[int, list[int]] = {}
    for i, j in canh:
        truoc.setdefault(j, []).append(i)
    bat_dau: list[datetime] = []
    ket_thuc: list[datetime] = []
    lech_buoc = lech_buoc or {}
    for i, (_ten, phut, _sl) in enumerate(buoc):
        t0 = max([ket_thuc[p] for p in truoc.get(i, [])] + [goc + lech_buoc.get(i, timedelta(0))])
        bat_dau.append(t0)
        ket_thuc.append(t0 + timedelta(minutes=phut or 0))

    da_gan: set[int] = set()
    for i, ((_ten, phut, _sl), cd) in enumerate(zip(buoc, buocs)):
        cv = cv_chung if (ghep and i in ghep) else cv_theo_buoc[cd.id]
        if cv.id in da_gan:  # cụm bước cùng chung MỘT công việc — chỉ gắn một lần
            continue
        da_gan.add(cv.id)
        if phut is None:
            cv.du_kien_bat_dau = cv.du_kien_ket_thuc = None
        else:
            cv.du_kien_bat_dau = bat_dau[i]
            cv.du_kien_ket_thuc = ket_thuc[i]
    db.commit()
    return a.id


def _cv_ghep(db, lsx_id: int) -> SanXuatCongViec:
    """Công việc CHUNG của bài ghép phủ bước của lệnh này (`lsx_id IS NULL` nên `_cong_viec` không
    thấy). Fixture chỉ dựng đúng một bài ghép nên `.one()` là chốt luôn tiền đề đó."""
    bgcd_ids = [
        m.bai_ghep_cong_doan_id
        for m in db.query(BaiGhepCongDoanMap).filter_by(lsx_id=lsx_id).all()
    ]
    return (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.bai_ghep_cong_doan_id.in_(set(bgcd_ids)))
        .one()
    )


def _cong_viec(db, lsx_id: int) -> list[SanXuatCongViec]:
    """Công việc của lệnh theo ĐÚNG thứ tự routing (snapshot sinh theo `thu_tu`, `id`)."""
    return (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.lsx_id == lsx_id)
        .order_by(SanXuatCongViec.id)
        .all()
    )


def _ghi_batch(db, cong_viec_id: int, tot: float) -> None:
    db.add(SanXuatBatch(
        cong_viec_id=cong_viec_id,
        bat_dau=BAY_GIO - timedelta(hours=2), ket_thuc=BAY_GIO - timedelta(hours=1),
        tong=tot, tot=tot, hong=0, don_vi="to",
    ))
    db.commit()


# --- 8 fixture của brief + 1 fixture phiên đang mở ---------------------------------------------
@pytest.fixture
def lenh_ctp_15p_in_6h(db, orders, lsx_svc, admin, customer) -> int:
    """CTP 15' (XONG) + In 360' (chưa chạy) — tổng 375'. Đúng 15/375 = 4%."""
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("CTP", 15, 5_000), ("In offset", 360, 5_000)])
    cvs = _cong_viec(db, lsx_id)
    cvs[0].trang_thai = CV_HOAN_THANH
    db.commit()
    return lsx_id


@pytest.fixture
def lenh_in_dang_chay_nua_muc_tieu(db, orders, lsx_svc, admin, customer) -> int:
    """Một bước In 360', mục tiêu 10.000 tờ, đã ghi 5.000 tốt ⇒ 50%."""
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("In offset", 360, 10_000)])
    _ghi_batch(db, _cong_viec(db, lsx_id)[0].id, 5_000)
    return lsx_id


@pytest.fixture
def lenh_in_vuot_muc_tieu(db, orders, lsx_svc, admin, customer) -> int:
    """Mục tiêu 10.000 nhưng ghi 25.000 tốt (2 batch) ⇒ 250% nếu không kẹp."""
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("In offset", 360, 10_000)])
    cv = _cong_viec(db, lsx_id)[0]
    _ghi_batch(db, cv.id, 15_000)
    _ghi_batch(db, cv.id, 10_000)
    return lsx_id


@pytest.fixture
def lenh_khong_thoi_luong(db, orders, lsx_svc, admin, customer) -> int:
    """Hai bước, KHÔNG bước nào có thời lượng ⇒ chia đều; bước 1 xong ⇒ 50% + cờ ước tính."""
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("CTP", None, 5_000), ("In offset", None, 5_000)])
    cvs = _cong_viec(db, lsx_id)
    cvs[0].trang_thai = CV_HOAN_THANH
    db.commit()
    return lsx_id


@pytest.fixture
def lenh_chay_2h_dung_1h(db, orders, lsx_svc, admin, customer) -> int:
    """Hai phiên ĐÃ ĐÓNG 08–09h và 10–11h ⇒ chạy 2h, khoảng dừng 09–10h nằm NGOÀI hai phiên."""
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("In offset", 360, 10_000)])
    cv = _cong_viec(db, lsx_id)[0]
    db.add_all([
        SanXuatPhienChay(
            cong_viec_id=cv.id, so_thu_tu=1,
            bat_dau=datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc),
            ket_thuc=datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc),
            loai_dong=PHIEN_TAM_DUNG, ly_do="Kẹt giấy",
        ),
        SanXuatPhienChay(
            cong_viec_id=cv.id, so_thu_tu=2,
            bat_dau=datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc),
            ket_thuc=datetime(2026, 8, 31, 11, 0, tzinfo=timezone.utc),
            loai_dong=PHIEN_KET_THUC,
        ),
    ])
    db.commit()
    return lsx_id


@pytest.fixture
def lenh_phien_dang_mo(db, orders, lsx_svc, admin, customer) -> int:
    """Một phiên CÒN MỞ, bắt đầu trước `BAY_GIO` 2 tiếng — bài canh bẫy naive/aware."""
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("In offset", 360, 10_000)])
    cv = _cong_viec(db, lsx_id)[0]
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1, bat_dau=BAY_GIO - timedelta(hours=2), ket_thuc=None,
    ))
    db.commit()
    return lsx_id


@pytest.fixture
def lenh_hai_nhanh_2h_va_5h(db, orders, lsx_svc, admin, customer) -> int:
    """Chuẩn bị 30' rồi TOẢ hai nhánh song song 120' và 300'.

    Đường găng = 30 + 300 = 330' (5,5h). Cộng dồn cả ba = 450' (7,5h). Nhánh ngắn = 150' (2,5h).
    Ba con số tách bạch để bài test phân biệt được ba cách cài đặt.
    """
    return _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("Chuẩn bị", 30, 5_000), ("Nhánh A", 120, 5_000), ("Nhánh B", 300, 5_000)],
        canh=[(0, 1), (0, 2)],
    )


@pytest.fixture
def lenh_khong_lich(db, orders, lsx_svc, admin, customer) -> int:
    """Có công việc nhưng KHÔNG có thời lượng kế hoạch ⇒ không suy được mốc xong."""
    return _dung_lenh(db, orders, lsx_svc, admin, customer,
                      buoc=[("In offset", None, 10_000)])


@pytest.fixture
def lenh_du_kien_vuot_han(db, orders, lsx_svc, admin, customer) -> int:
    """Còn 480' từ `BAY_GIO` (10:00 UTC) ⇒ xong 18:00 UTC = 01:00 giờ xưởng NGÀY HÔM SAU.

    Hạn SX là 31/08. Theo giờ xưởng (+7) mốc xong rơi vào 01/09 ⇒ TRỄ. Nếu so bằng `.date()` của
    mốc UTC thì vẫn là 31/08 ⇒ báo không trễ — đúng cái bẫy ca đêm mà bài này canh.
    """
    from app.models.lsx import Lsx

    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("In offset", 480, 10_000)])
    db.get(Lsx, lsx_id).han_hoan_thanh_sx = date(2026, 8, 31)
    db.commit()
    return lsx_id


# --- Tiến độ có trọng số -----------------------------------------------------------------------
def test_trong_so_theo_thoi_luong_khong_theo_so_cong_doan(db, lenh_ctp_15p_in_6h):
    """Xong CTP (15') trong tổng 6h15' ⇒ ~4%, KHÔNG phải 50%."""
    bc = boi_canh.nap(db, [lenh_ctp_15p_in_6h])
    pct, uoc = tien_do.phan_tram(bc, lenh_ctp_15p_in_6h)
    assert 3.0 <= pct <= 5.0, pct
    assert pct == pytest.approx(100.0 * 15 / 375), pct  # 15' xong / 375' tổng = 4,0%
    assert uoc is False


def test_cong_doan_dang_chay_an_phan_theo_san_luong(db, lenh_in_dang_chay_nua_muc_tieu):
    bc = boi_canh.nap(db, [lenh_in_dang_chay_nua_muc_tieu])
    pct, _ = tien_do.phan_tram(bc, lenh_in_dang_chay_nua_muc_tieu)
    assert 48.0 <= pct <= 52.0, pct
    assert pct == pytest.approx(50.0), pct  # 5.000 / 10.000 tờ


def test_vuot_muc_tieu_khong_qua_100(db, lenh_in_vuot_muc_tieu):
    bc = boi_canh.nap(db, [lenh_in_vuot_muc_tieu])
    pct, _ = tien_do.phan_tram(bc, lenh_in_vuot_muc_tieu)
    assert pct <= 100.0
    # Chốt cả cận dưới: kẹp phải kẹp về ĐÚNG 100, không phải kẹp nhầm về 0.
    assert pct == pytest.approx(100.0), pct


def test_thieu_thoi_luong_thi_chia_deu_va_giuong_co(db, lenh_khong_thoi_luong):
    bc = boi_canh.nap(db, [lenh_khong_thoi_luong])
    pct, uoc = tien_do.phan_tram(bc, lenh_khong_thoi_luong)
    assert uoc is True
    # Hai bước chia đều, bước 1 xong ⇒ đúng một nửa.
    assert pct == pytest.approx(50.0), pct


# --- Giờ máy ------------------------------------------------------------------------------------
def test_gio_may_loai_tru_thoi_gian_dung(db, lenh_chay_2h_dung_1h):
    bc = boi_canh.nap(db, [lenh_chay_2h_dung_1h])
    gio = tien_do.gio_may(bc, lenh_chay_2h_dung_1h)
    # Trọn khoảng 08–11h là 3h; hai phiên cộng lại đúng 2h — chốt số để phân biệt hai cách tính.
    assert gio == pytest.approx(2.0), gio


def test_gio_may_phien_con_mo_tinh_toi_bay_gio(db, lenh_phien_dang_mo):
    """Phiên chưa đóng đếm tới `bay_gio`. SQLite trả mốc NAIVE, `bay_gio` AWARE — trừ thẳng nổ
    TypeError, nên bài này cũng là bài canh bẫy naive/aware."""
    bc = boi_canh.nap(db, [lenh_phien_dang_mo])
    # Phiên mở lúc `BAY_GIO − 2h`, đếm tới `BAY_GIO` ⇒ đúng 2,0h. Chốt cứng: khoảng 1,9–2,1 nuốt
    # được một cài đặt sai thật (làm tròn/đổi đơn vị lệch vài phút) mà không ai thấy.
    assert tien_do.gio_may(bc, lenh_phien_dang_mo, BAY_GIO) == pytest.approx(2.0)


# --- Dự kiến hoàn thành --------------------------------------------------------------------------
def test_song_song_lay_duong_gang(db, lenh_hai_nhanh_2h_va_5h):
    """Hai nhánh chạy song song 2h và 5h ⇒ dự kiến xong theo nhánh 5h (cộng 30' chuẩn bị).

    Cận TRÊN quan trọng ngang cận dưới: cộng dồn cả ba bước ra 7,5h — cũng thoả cận dưới 4,5h mà
    vẫn là cài đặt SAI. Cận trên 6,5h loại nó ra. Và chốt luôn con số ĐÚNG 330' (30 + 300): khoảng
    4,5–6,5h vẫn lọt một cách sai nữa là "bỏ qua bước tiền nhiệm" (chỉ lấy 300' của nhánh dài).
    """
    cvs = _cong_viec(db, lenh_hai_nhanh_2h_va_5h)
    assert not ({cv.id for cv in cvs} & {cv.lsx_cong_doan_id for cv in cvs}), (
        "hai dãy id trùng khoảng — bài canh nối cạnh qua `lsx_cong_doan_id` mất ý nghĩa"
    )

    bc = boi_canh.nap(db, [lenh_hai_nhanh_2h_va_5h])
    xong = tien_do.du_kien_xong(bc, lenh_hai_nhanh_2h_va_5h, BAY_GIO)
    assert xong is not None
    assert xong >= BAY_GIO + timedelta(hours=4.5), xong
    assert xong <= BAY_GIO + timedelta(hours=6.5), xong
    assert xong == BAY_GIO + timedelta(minutes=330), xong


def test_da_chay_mot_phan_thi_tru_bot_phan_con_lai(db, lenh_in_dang_chay_nua_muc_tieu):
    """Bước 6h đã xong nửa sản lượng ⇒ còn ~3h, không phải 6h."""
    bc = boi_canh.nap(db, [lenh_in_dang_chay_nua_muc_tieu])
    xong = tien_do.du_kien_xong(bc, lenh_in_dang_chay_nua_muc_tieu, BAY_GIO)
    assert xong == BAY_GIO + timedelta(hours=3), xong


def test_thieu_du_lieu_tra_none(db, lenh_khong_lich):
    bc = boi_canh.nap(db, [lenh_khong_lich])
    assert tien_do.du_kien_xong(bc, lenh_khong_lich, BAY_GIO) is None


# --- Trễ hạn --------------------------------------------------------------------------------------
def test_tre_han_khi_du_kien_vuot_han_sx(db, lenh_du_kien_vuot_han):
    bc = boi_canh.nap(db, [lenh_du_kien_vuot_han])
    assert tien_do.tre_han(bc, lenh_du_kien_vuot_han, BAY_GIO) is True


def test_trong_han_thi_khong_tre(db, lenh_du_kien_vuot_han):
    from app.models.lsx import Lsx

    db.get(Lsx, lenh_du_kien_vuot_han).han_hoan_thanh_sx = date(2026, 9, 5)
    db.commit()
    bc = boi_canh.nap(db, [lenh_du_kien_vuot_han])
    assert tien_do.tre_han(bc, lenh_du_kien_vuot_han, BAY_GIO) is False


def test_khong_co_han_thi_khong_tre(db, lenh_du_kien_vuot_han):
    """`han_hoan_thanh_sx` NULL ⇒ không có hạn thì không thể trễ (KHÔNG rơi sang hạn giao khách)."""
    from app.models.lsx import Lsx

    lsx = db.get(Lsx, lenh_du_kien_vuot_han)
    lsx.han_hoan_thanh_sx = None
    lsx.han_giao_khach = date(2020, 1, 1)  # hạn khách quá khứ — vẫn KHÔNG được coi là trễ SX
    db.commit()
    bc = boi_canh.nap(db, [lenh_du_kien_vuot_han])
    assert tien_do.tre_han(bc, lenh_du_kien_vuot_han, BAY_GIO) is False


def test_khong_du_lieu_thi_khong_khang_dinh_tre(db, lenh_khong_lich):
    """Không suy được mốc xong ⇒ không kết luận trễ (thà im còn hơn đoán)."""
    from app.models.lsx import Lsx

    db.get(Lsx, lenh_khong_lich).han_hoan_thanh_sx = date(2020, 1, 1)
    db.commit()
    bc = boi_canh.nap(db, [lenh_khong_lich])
    assert tien_do.tre_han(bc, lenh_khong_lich, BAY_GIO) is False


# ================================================================================================
# VÒNG SỬA 1 — bốn lỗ hổng review chỉ ra
# ================================================================================================

# --- A. Bước bị BÀI GHÉP phủ phải nằm trong mọi phép tính -------------------------------------
@pytest.fixture
def lenh_ghep_giua_chuoi(db, orders, lsx_svc, admin, customer) -> int:
    """Đúng ca reviewer đo: chuỗi 3 bước 60' → 360' (BỊ GHÉP) → 30'.

    Tổng tuần tự 450'. Bỏ rơi công việc ghép thì còn 60+30 = 90' (hụt 80%) — số đó vẫn "hợp lý"
    trên màn hình, đó là lý do lỗi này sống sót qua cả vòng đầu.

    LỊCH ĐÃ TRÔI QUA (`bat_dau_lech` âm) là CHỦ Ý, không phải cho vui: lệnh chạy trễ thì mọi SÀN
    bằng 0 và chỉ còn ĐỒ THỊ quyết định mốc xong. Nếu để lịch ở tương lai, các sàn tự xếp sẵn
    thành đúng đáp số và bài test hoá ra chỉ đọc lại lịch — đã thử, đột biến "bỏ cầu `buoc_phu`"
    lọt qua sạch sẽ. Đây cũng là ca THƯỜNG GẶP nhất ở xưởng.
    """
    return _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In ghép", 360, 5_000), ("Cắt thành phẩm", 30, 5_000)],
        ghep=[1],
        bat_dau_lech=timedelta(days=-2),
    )


@pytest.fixture
def lenh_ghep_co_nhanh_song_song(db, orders, lsx_svc, admin, customer) -> int:
    """Chuỗi 60' → 360'(GHÉP) → 30', kèm nhánh phụ 120' rẽ từ bước đầu.

    Đường găng đúng = 450'. Nếu cạnh CHẠM bước ghép bị bỏ (không bắc cầu `buoc_phu`), đồ thị còn
    mỗi cạnh 0→3: bước ghép và bước cắt thành hai đảo, `max` ra 360'. Nhánh phụ tồn tại chính là
    để `canh` KHÔNG rỗng — chuỗi 3 bước thuần rơi về nhánh "cộng tuần tự" và vô tình vẫn ra 450'.

    Lịch để ở QUÁ KHỨ, cùng lý do với `lenh_ghep_giua_chuoi`: sàn bằng 0 hết thì đáp số hoàn toàn
    do đồ thị quyết, đúng thứ bài này muốn canh.
    """
    return _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[
            ("Chuẩn bị", 60, 5_000), ("In ghép", 360, 5_000),
            ("Cắt thành phẩm", 30, 5_000), ("Nhánh phụ", 120, 5_000),
        ],
        canh=[(0, 1), (1, 2), (0, 3)],
        ghep=[1],
        bat_dau_lech=timedelta(days=-2),
    )


@pytest.fixture
def lenh_moi_buoc_deu_ghep(db, orders, lsx_svc, admin, customer) -> int:
    """MỌI bước của lệnh đều bị một công đoạn ghép phủ ⇒ `cong_viec[lsx_id]` RỖNG.

    Công việc chung có mục tiêu 5.000 tờ, đã ghi 2.000 tốt ⇒ 40%. Bỏ rơi bước ghép thì lệnh này
    hiện 0% vĩnh viễn dù xưởng đang chạy.
    """
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("In ghép", 360, 5_000), ("Cán ghép", 120, 5_000)],
        ghep=[0, 1],
    )
    _ghi_batch(db, _cv_ghep(db, lsx_id).id, 2_000)
    return lsx_id


def test_buoc_ghep_van_nam_trong_duong_gang(db, lenh_ghep_giua_chuoi):
    """Bước ghép có `lsx_id IS NULL` nên `cong_viec[lsx_id]` không thấy nó — nhưng nó là bước NẶNG
    NHẤT của lệnh. Chốt cứng 450', không dùng cận."""
    assert len(_cong_viec(db, lenh_ghep_giua_chuoi)) == 2, (
        "tiền đề hỏng: bước bị ghép phủ vẫn đẻ công việc riêng"
    )
    cv_ghep = _cv_ghep(db, lenh_ghep_giua_chuoi)
    assert cv_ghep.lsx_id is None

    bc = boi_canh.nap(db, [lenh_ghep_giua_chuoi])
    xong = tien_do.du_kien_xong(bc, lenh_ghep_giua_chuoi, BAY_GIO)
    assert xong == BAY_GIO + timedelta(minutes=450), xong


def test_canh_cham_buoc_ghep_khong_duoc_bo(db, lenh_ghep_co_nhanh_song_song):
    """Cạnh nối vào/ra bước ghép phải bắc cầu qua `buoc_phu`. Bỏ cầu ⇒ 360' (nhánh dài rời rạc)."""
    bc = boi_canh.nap(db, [lenh_ghep_co_nhanh_song_song])
    xong = tien_do.du_kien_xong(bc, lenh_ghep_co_nhanh_song_song, BAY_GIO)
    assert xong == BAY_GIO + timedelta(minutes=450), xong


def test_moi_buoc_deu_ghep_van_ra_so_that(db, lenh_moi_buoc_deu_ghep):
    bc = boi_canh.nap(db, [lenh_moi_buoc_deu_ghep])
    assert bc.cong_viec[lenh_moi_buoc_deu_ghep] == [], "tiền đề hỏng: lệnh vẫn còn bước riêng"

    pct, uoc = tien_do.phan_tram(bc, lenh_moi_buoc_deu_ghep)
    assert (pct, uoc) != (0.0, False)
    assert pct == pytest.approx(40.0), pct  # 2.000 / 5.000 tờ của ca ghép
    assert uoc is False


def test_gio_may_dem_du_phien_cua_buoc_ghep(db, lenh_moi_buoc_deu_ghep):
    """Phán quyết C36: phiên của bước ghép đếm ĐỦ cho lệnh, không chia phần. Cũng là bài canh
    `bc.phien` phải TOÀN ÁNH cả trên công việc ghép — thiếu là KeyError, không phải số sai."""
    cv = _cv_ghep(db, lenh_moi_buoc_deu_ghep)
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1,
        bat_dau=BAY_GIO - timedelta(hours=3), ket_thuc=BAY_GIO - timedelta(hours=1),
        loai_dong=PHIEN_KET_THUC,
    ))
    db.commit()

    bc = boi_canh.nap(db, [lenh_moi_buoc_deu_ghep])
    assert tien_do.gio_may(bc, lenh_moi_buoc_deu_ghep, BAY_GIO) == pytest.approx(2.0)


# --- B. `du_kien_xong` phải tôn trọng mốc bắt đầu kế hoạch --------------------------------------
@pytest.fixture
def lenh_bat_dau_sau_hai_ngay(db, orders, lsx_svc, admin, customer) -> int:
    """Bước 480' nhưng lịch xếp cho 2 ngày 3 giờ NỮA — cố ý lệch `bay_gio` (bẫy song song).

    Đúng: xong = BAY_GIO + 2 ngày 11 giờ ⇒ 03/09 giờ xưởng. Bỏ sàn: xong = BAY_GIO + 8h ⇒ 01/09
    giờ xưởng. Hạn đặt đúng 01/09 nên hai cách cho hai kết luận TRÁI NGƯỢC về trễ hạn.
    """
    from app.models.lsx import Lsx

    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("In offset", 480, 10_000)],
        bat_dau_lech=timedelta(days=2, hours=3),
    )
    db.get(Lsx, lsx_id).han_hoan_thanh_sx = date(2026, 9, 1)
    db.commit()
    return lsx_id


def test_du_kien_xong_lui_theo_moc_bat_dau_ke_hoach(db, lenh_bat_dau_sau_hai_ngay):
    cv = _cong_viec(db, lenh_bat_dau_sau_hai_ngay)[0]
    assert cv.du_kien_bat_dau is not None
    assert cv.du_kien_bat_dau.replace(tzinfo=timezone.utc) != BAY_GIO, (
        "fixture lại trùng `bay_gio` — đúng cái bẫy đã che lỗi này ở vòng trước"
    )

    bc = boi_canh.nap(db, [lenh_bat_dau_sau_hai_ngay])
    xong = tien_do.du_kien_xong(bc, lenh_bat_dau_sau_hai_ngay, BAY_GIO)
    # Lùi ĐÚNG bằng khoảng lệch: 2 ngày 3 giờ chờ + 8 giờ chạy.
    assert xong == BAY_GIO + timedelta(days=2, hours=11), xong


def test_tre_han_bat_duoc_lenh_xep_lich_muon(db, lenh_bat_dau_sau_hai_ngay):
    """Hạn 01/09 nằm GIỮA hai mốc: bỏ sàn thì xong 01/09 ⇒ báo không trễ; có sàn thì xong 03/09 ⇒ trễ."""
    bc = boi_canh.nap(db, [lenh_bat_dau_sau_hai_ngay])
    assert tien_do.tre_han(bc, lenh_bat_dau_sau_hai_ngay, BAY_GIO) is True

    # Chốt luôn tiền đề "bỏ sàn thì KHÔNG trễ" — nếu không, bài trên xanh cả khi hạn quá chặt và
    # lỗi sàn vẫn còn nguyên.
    khong_san = BAY_GIO + timedelta(hours=8)
    assert khong_san.astimezone(tien_do.BUSINESS_TZ).date() == date(2026, 9, 1)
    assert tien_do.tre_han(bc, lenh_bat_dau_sau_hai_ngay, BAY_GIO, xong=khong_san) is False


def test_tre_han_dung_ket_qua_ben_goi_truyen_vao(db, lenh_du_kien_vuot_han):
    """`xong` truyền vào phải được DÙNG (màn 200 lệnh tránh duyệt đường găng lần hai). `None` là
    giá trị hợp lệ nghĩa "đã tính, không đủ dữ liệu" — không được lẫn với "chưa tính"."""
    bc = boi_canh.nap(db, [lenh_du_kien_vuot_han])
    assert tien_do.tre_han(bc, lenh_du_kien_vuot_han, BAY_GIO) is True
    # Cùng lệnh, cùng hạn — chỉ khác mốc xong do bên gọi đưa.
    assert tien_do.tre_han(bc, lenh_du_kien_vuot_han, BAY_GIO, xong=BAY_GIO) is False
    assert tien_do.tre_han(bc, lenh_du_kien_vuot_han, BAY_GIO, xong=None) is False


# --- C. Cờ `uoc_tinh` cho bước KHÔNG ĐO ĐƯỢC ---------------------------------------------------
@pytest.fixture
def lenh_buoc_khong_do_duoc(db, orders, lsx_svc, admin, customer) -> int:
    """Bước ghi kẽm `so_luong_ra = 0` (ca THƯỜNG — cột NOT NULL default 0) + bước In đo được."""
    return _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("Ghi kẽm", 60, 0), ("In offset", 360, 10_000)],
    )


def test_buoc_chua_xong_khong_do_duoc_thi_giuong_co(db, lenh_buoc_khong_do_duoc):
    # Cho bước In chạy nửa mục tiêu TRƯỚC khi đo: không có nó thì `pct` bằng 0 dù trọng số tính
    # kiểu nào, và vế thứ hai của bài (cờ KHÔNG được đổi cách tính) hoá ra không canh gì cả.
    _ghi_batch(db, _cong_viec(db, lenh_buoc_khong_do_duoc)[1].id, 5_000)

    bc = boi_canh.nap(db, [lenh_buoc_khong_do_duoc])
    pct, uoc = tien_do.phan_tram(bc, lenh_buoc_khong_do_duoc)
    assert uoc is True, "bước 0% im lặng không phân biệt được với chưa-ai-làm"
    # Cờ chỉ nói "không chắc", KHÔNG được đổi cách tính: trọng số vẫn theo THỜI LƯỢNG thật
    # (0·60 + 0,5·360)/420 ≈ 42,9 %. Chia đều — cách tính của nhánh thiếu-thời-lượng — ra 25 %.
    assert pct == pytest.approx(100.0 * 180 / 420), pct


def test_buoc_da_completed_thi_khong_giuong_co(db, lenh_buoc_khong_do_duoc):
    """Cùng bước đó khi `completed` thì cờ TẮT. Giương ở đây thì mọi lệnh đã xong đều đeo cờ."""
    cvs = _cong_viec(db, lenh_buoc_khong_do_duoc)
    cvs[0].trang_thai = CV_HOAN_THANH
    db.commit()

    bc = boi_canh.nap(db, [lenh_buoc_khong_do_duoc])
    pct, uoc = tien_do.phan_tram(bc, lenh_buoc_khong_do_duoc)
    assert uoc is False
    assert pct == pytest.approx(100.0 * 60 / 420), pct


# --- D. Hai quyết định trước đây không có bài canh ---------------------------------------------
@pytest.fixture
def lenh_tron_co_va_thieu_thoi_luong(db, orders, lsx_svc, admin, customer) -> int:
    """CTP 15' (XONG) + In THIẾU thời lượng. Chia đều ra 50%; theo thời lượng thật ra 4%.

    Fixture cũ đặt CẢ HAI bước thiếu nên chia đều hay không đều cùng ra một số — luật "thiếu MỘT
    bước là chia đều TOÀN BỘ" chưa từng bị bài nào chạm tới."""
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 5_000), ("In offset", None, 5_000)],
    )
    cvs = _cong_viec(db, lsx_id)
    cvs[0].trang_thai = CV_HOAN_THANH
    db.commit()
    return lsx_id


@pytest.fixture
def lenh_mot_buoc_vuot_mot_buoc_chua(db, orders, lsx_svc, admin, customer) -> int:
    """Hai bước THỜI LƯỢNG BẰNG NHAU: A in dư 250% mục tiêu, B chưa chạy.

    Kẹp TỪNG BƯỚC ra (1,0 + 0,0)/2 = 50%. Kẹp TỔNG ra (2,5 + 0,0)/2 = 125% rồi kẹp còn 100%. Hai
    cách cho hai số cách nhau gấp đôi; fixture một-bước cũ không phân biệt được.
    """
    lsx_id = _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("In mặt trước", 180, 10_000), ("In mặt sau", 180, 10_000)],
    )
    _ghi_batch(db, _cong_viec(db, lsx_id)[0].id, 25_000)
    return lsx_id


def test_thieu_mot_buoc_la_chia_deu_toan_bo(db, lenh_tron_co_va_thieu_thoi_luong):
    bc = boi_canh.nap(db, [lenh_tron_co_va_thieu_thoi_luong])
    pct, uoc = tien_do.phan_tram(bc, lenh_tron_co_va_thieu_thoi_luong)
    assert uoc is True
    assert pct == pytest.approx(50.0), pct  # KHÔNG phải 4% (15/375 theo thời lượng thật)


def test_kep_theo_tung_buoc_khong_kep_tong(db, lenh_mot_buoc_vuot_mot_buoc_chua):
    bc = boi_canh.nap(db, [lenh_mot_buoc_vuot_mot_buoc_chua])
    pct, _ = tien_do.phan_tram(bc, lenh_mot_buoc_vuot_mot_buoc_chua)
    assert pct == pytest.approx(50.0), pct  # kẹp tổng sẽ ra 100.0


# ================================================================================================
# VÒNG SỬA 2 — SÀN phải được canh ở ĐÚNG nhánh chạy thật, và nhánh tuần tự phải cộng đúng
# ================================================================================================
@pytest.fixture
def lenh_buoc_giua_cho_ba_ngay(db, orders, lsx_svc, admin, customer) -> int:
    """Chuỗi CÓ CẠNH 60' → 120' → 30', trong đó bước GIỮA phải chờ tới 3 ngày nữa mới có máy.

    Đây là hình dạng routing THẬT: `LsxService.tao` sinh sẵn chuỗi cạnh đầy đủ
    (`lsx_service.py:1526-1528`), nên nhánh Kahn mới là nhánh chạy ngoài đời. Hai fixture bài ghép
    cố ý để lịch quá khứ (mọi sàn = 0) và fixture `lenh_bat_dau_sau_hai_ngay` chỉ có MỘT bước
    (không có cạnh ⇒ không vào Kahn) — nên trước fixture này, phần SÀN trong vòng Kahn KHÔNG có
    bài nào canh: bỏ nó đi mà cả bộ vẫn xanh.

    Đúng: 3 ngày (chờ) + 120' (in) + 30' (cắt) = 4.470'. Bỏ sàn trong Kahn: 60+120+30 = 210'.
    """
    return _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 60, 5_000), ("In offset", 120, 5_000), ("Cắt thành phẩm", 30, 5_000)],
        lech_buoc={1: timedelta(days=3)},
    )


@pytest.fixture
def lenh_hai_buoc_roi_lech_bay_ngay(db, orders, lsx_svc, admin, customer) -> int:
    """Hai bước KHÔNG cạnh: A 60' chạy được ngay, B 30' xếp 7 ngày nữa.

    Kế hoạch gỡ hết cạnh là ca bất thường nhưng có thật (và nhánh chu trình cũng rơi vào đây).
    Đúng: `max(0, 0) + 60`, rồi `max(60, 10.080) + 30` = 10.110' = 7 ngày 30'. Cộng dồn từ SÀN
    NHỎ NHẤT (bản cũ) ra 90' — hụt trọn 7 ngày, và hụt về phía LẠC QUAN.
    """
    return _dung_lenh(
        db, orders, lsx_svc, admin, customer,
        buoc=[("In offset", 60, 5_000), ("Cắt thành phẩm", 30, 5_000)],
        canh=[],
        lech_buoc={1: timedelta(days=7)},
    )


def test_san_co_hieu_luc_trong_vong_kahn(db, lenh_buoc_giua_cho_ba_ngay):
    """Sàn của bước GIỮA vượt hẳn mốc mà tiền nhiệm đẩy tới ⇒ phải đẩy cả đuôi chuỗi theo."""
    bc = boi_canh.nap(db, [lenh_buoc_giua_cho_ba_ngay])
    # Tiền đề: lệnh này CÓ cạnh, tức đi vào nhánh Kahn chứ không rơi về `_tuan_tu`.
    assert bc.phu_thuoc_buoc[lenh_buoc_giua_cho_ba_ngay], "không có cạnh — bài này không chạm Kahn"

    xong = tien_do.du_kien_xong(bc, lenh_buoc_giua_cho_ba_ngay, BAY_GIO)
    assert xong == BAY_GIO + timedelta(days=3, minutes=150), xong


def test_khong_canh_thi_gop_theo_san_tang_dan(db, lenh_hai_buoc_roi_lech_bay_ngay):
    """Nhánh `_tuan_tu`: gộp theo sàn TĂNG DẦN, không cộng từ sàn nhỏ nhất."""
    bc = boi_canh.nap(db, [lenh_hai_buoc_roi_lech_bay_ngay])
    assert bc.phu_thuoc_buoc[lenh_hai_buoc_roi_lech_bay_ngay] == [], (
        "fixture còn cạnh — bài này sẽ đi Kahn chứ không chạm nhánh tuần tự"
    )

    xong = tien_do.du_kien_xong(bc, lenh_hai_buoc_roi_lech_bay_ngay, BAY_GIO)
    assert xong == BAY_GIO + timedelta(days=7, minutes=30), xong


def test_tre_han_khong_bo_sot_khi_buoc_roi_xep_muon(db, lenh_hai_buoc_roi_lech_bay_ngay):
    """Hụt 7 ngày ở `_tuan_tu` kéo theo `tre_han` bỏ sót — chốt luôn vế hậu quả, không chỉ vế số."""
    from app.models.lsx import Lsx

    db.get(Lsx, lenh_hai_buoc_roi_lech_bay_ngay).han_hoan_thanh_sx = date(2026, 9, 3)
    db.commit()

    bc = boi_canh.nap(db, [lenh_hai_buoc_roi_lech_bay_ngay])
    # Cộng từ sàn nhỏ nhất ⇒ xong 31/08 ⇒ báo KHÔNG trễ. Gộp đúng ⇒ xong 07/09 ⇒ TRỄ.
    assert tien_do.tre_han(bc, lenh_hai_buoc_roi_lech_bay_ngay, BAY_GIO) is True
    assert tien_do.tre_han(
        bc, lenh_hai_buoc_roi_lech_bay_ngay, BAY_GIO, xong=BAY_GIO + timedelta(minutes=90)
    ) is False


# --- Vòng sửa 1 (mục C): lệnh KHÔNG CÒN GÌ ĐỂ LÀM có mốc xong QUÁ KHỨ, không phải `bay_gio` ------
def _xong_co_phien(db, cv, bat_dau, ket_thuc) -> None:
    """Đóng một công việc ĐÚNG NHƯ PRODUCTION: `completed` + MỘT PHIÊN ĐÃ ĐÓNG.

    `thuc_thi.ket_thuc` đóng phiên đang mở TRƯỚC rồi mới đặt `completed`, nên trạng thái
    "completed mà không phiên nào" KHÔNG tồn tại ở xưởng. Fixture đặt tay mỗi cột trạng thái sẽ
    lặng lẽ đẩy bài test xuống bậc 2 của thang và bậc 1 mất lưới.
    """
    cv.trang_thai = CV_HOAN_THANH
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1, bat_dau=bat_dau, ket_thuc=ket_thuc,
        loai_dong=PHIEN_KET_THUC,
    ))
    db.commit()


@pytest.fixture
def lenh_da_xong_hom_qua(db, orders, lsx_svc, admin, customer) -> int:
    """Hai bước, cả hai ĐÃ ĐÓNG. Phiên cuối kết thúc 30/08 09:00 UTC = 16:00 giờ xưởng 30/08.

    Lịch kế hoạch nằm hẳn ở HÔM QUA (`bat_dau_lech=-1 ngày`) và mốc PHIÊN lệch hẳn mốc KẾ HOẠCH
    (09:00 vs 17:00 UTC) — hai bậc đầu của thang phải phân biệt được nhau, nếu trùng thì bài bậc 1
    xanh cả khi cài đặt đọc nhầm sang mốc kế hoạch.
    """
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("CTP", 60, 5_000), ("In offset", 360, 5_000)],
                        bat_dau_lech=timedelta(days=-1))
    cvs = _cong_viec(db, lsx_id)
    _xong_co_phien(db, cvs[0], BAY_GIO - timedelta(days=1, hours=3),
                   BAY_GIO - timedelta(days=1, hours=2))
    _xong_co_phien(db, cvs[1], BAY_GIO - timedelta(days=1, hours=2),
                   BAY_GIO - timedelta(days=1, hours=1))
    return lsx_id


def test_lenh_da_xong_lay_moc_phien_dong_cuoi(db, lenh_da_xong_hom_qua):
    """Bậc 1: mốc xong = `max(phien.ket_thuc)` — sự thật ghi được từ xưởng, KHÔNG phải `bay_gio`.

    Bản Task 7 trả đúng `bay_gio` cho mọi lệnh đã xong (mọi `con_lai = 0` ⇒ đường găng 0 phút).
    Con số ấy không những sai, nó còn TRƯỢT thêm một ngày mỗi ngày trôi qua.
    """
    bc = boi_canh.nap(db, [lenh_da_xong_hom_qua])
    xong = tien_do.du_kien_xong(bc, lenh_da_xong_hom_qua, BAY_GIO)
    assert xong == BAY_GIO - timedelta(days=1, hours=1), xong
    assert xong < BAY_GIO


def test_lenh_da_xong_khong_phien_thi_lui_ve_moc_ke_hoach(db, lenh_da_xong_hom_qua):
    """Bậc 2: không phiên đóng nào ⇒ `max(cv.du_kien_ket_thuc)`. Mốc kế hoạch còn hơn không —
    nhưng nó KHÁC mốc phiên, nên hai bậc không thay nhau được."""
    for p in db.query(SanXuatPhienChay).all():
        db.delete(p)
    db.commit()
    bc = boi_canh.nap(db, [lenh_da_xong_hom_qua])
    xong = tien_do.du_kien_xong(bc, lenh_da_xong_hom_qua, BAY_GIO)
    assert xong == BAY_GIO - timedelta(days=1) + timedelta(minutes=420), xong


def test_lenh_da_xong_khong_phien_khong_lich_tra_none(db, orders, lsx_svc, admin, customer):
    """Bậc 3: không phiên, không mốc kế hoạch ⇒ `None` ("chưa đủ dữ liệu"), KHÔNG bịa `bay_gio`."""
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("In offset", None, 5_000)])
    cv = _cong_viec(db, lsx_id)[0]
    cv.trang_thai = CV_HOAN_THANH        # cố ý KHÔNG đẻ phiên: bậc 3 là ca dữ liệu thiếu
    db.commit()
    bc = boi_canh.nap(db, [lsx_id])
    assert tien_do.du_kien_xong(bc, lsx_id, BAY_GIO) is None


def test_lenh_ve_dung_han_khong_con_bao_tre(db, lenh_da_xong_hom_qua):
    """HỆ QUẢ thật của bậc 1 — đây mới là chỗ lỗi Task 7 cắn người dùng.

    Hạn 30/08; lệnh đóng phiên cuối 16:00 giờ xưởng 30/08 ⇒ VỀ ĐÚNG HẠN. Lấy `bay_gio` (31/08)
    làm mốc xong thì lệnh này báo TRỄ vĩnh viễn — dòng đối chứng `xong=BAY_GIO` bên dưới chính là
    hành vi cũ.
    """
    from app.models.lsx import Lsx

    db.get(Lsx, lenh_da_xong_hom_qua).han_hoan_thanh_sx = date(2026, 8, 30)
    db.commit()

    bc = boi_canh.nap(db, [lenh_da_xong_hom_qua])
    assert tien_do.tre_han(bc, lenh_da_xong_hom_qua, BAY_GIO) is False
    assert tien_do.tre_han(bc, lenh_da_xong_hom_qua, BAY_GIO, xong=BAY_GIO) is True


def _dang_chay(db, cv, bat_dau) -> None:
    """Đặt một công việc ĐANG CHẠY đúng như production: `running` + MỘT PHIÊN CÒN MỞ.

    `thuc_thi.bat_dau` là đường ghi `running` duy nhất và nó luôn `add(phien)` với `ket_thuc=None`.
    Đặt tay mỗi cột trạng thái là dựng một trạng thái xưởng không tạo ra được — và từ Vòng sửa 2
    thì phiên MỞ là thứ load-bearing: nó chính là chỗ thang `_moc_da_xong` nhặt nhầm mốc nếu cửa
    vào thang đặt sai.
    """
    cv.trang_thai = CV_DANG_CHAY
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1, bat_dau=bat_dau, ket_thuc=None))
    db.commit()


@pytest.fixture
def lenh_ghi_du_san_luong_quen_bam_xong(db, orders, lsx_svc, admin, customer) -> int:
    """Ca "thợ ghi hết sản lượng rồi QUÊN bấm Kết thúc" — lệnh vẫn ĐANG CHẠY, hạn đã qua.

    CTP đóng hẳn (phiên đóng 28/08 11:00). In offset `running`, phiên còn MỞ, batch đã ghi ĐỦ
    10.000/10.000 ⇒ `_phan_hoan_thanh` = 1.0 (bị kẹp `min(1.0, …)`) ⇒ `con_lai` = 0 dù bước chưa
    đóng. Đây đúng là ca mà cửa `con_lai == 0` của Vòng sửa 1 nuốt mất.
    """
    lsx_id = _dung_lenh(db, orders, lsx_svc, admin, customer,
                        buoc=[("CTP", 60, 10_000), ("In offset", 360, 10_000)],
                        bat_dau_lech=timedelta(days=-3))
    cvs = _cong_viec(db, lsx_id)
    _xong_co_phien(db, cvs[0], BAY_GIO - timedelta(days=3), BAY_GIO - timedelta(days=3, hours=-1))
    _dang_chay(db, cvs[1], BAY_GIO - timedelta(days=3, hours=-1))
    _ghi_batch(db, cvs[1].id, 10_000)
    return lsx_id


def test_ghi_du_san_luong_ma_chua_dong_buoc_van_chua_xong(
        db, lenh_ghi_du_san_luong_quen_bam_xong):
    """Bước chưa `completed` ⇒ KHÔNG được vào thang "đã xong", dù `con_lai` đã bằng 0.

    Vòng sửa 2 — regression của chính Vòng sửa 1. Cửa `con_lai == 0` cho lệnh này vào thang; phiên
    của bước đang chạy còn MỞ nên bậc 1 nhặt mốc phiên của BƯỚC TRƯỚC (28/08 11:00) và trả về đó.
    Cửa đúng là `all(cv.trang_thai == CV_HOAN_THANH)`: lệnh còn trên máy thì mốc xong là "đáng lẽ
    xong rồi" = `bay_gio`, không phải một mốc ba ngày trước.
    """
    bc = boi_canh.nap(db, [lenh_ghi_du_san_luong_quen_bam_xong])
    xong = tien_do.du_kien_xong(bc, lenh_ghi_du_san_luong_quen_bam_xong, BAY_GIO)
    assert xong == BAY_GIO, xong
    # Mốc phiên đóng của BƯỚC TRƯỚC — con số mà bản lỗi trả về. Chốt thẳng để bài không xanh nhầm.
    assert xong != BAY_GIO - timedelta(days=3, hours=-1)


def test_ghi_du_san_luong_ma_chua_dong_buoc_van_bao_tre(
        db, lenh_ghi_du_san_luong_quen_bam_xong):
    """HỆ QUẢ: lệnh trễ hai ngày CÒN TRÊN MÁY phải giữ cờ `tre_han`.

    Bản lỗi trả `du_kien_xong` = 28/08 11:00 (quá khứ) ⇒ `tre_han` False ⇒ lệnh mất badge và rơi
    khỏi tab Cảnh báo. Đúng ca điều độ cần nhìn nhất.
    """
    from app.models.lsx import Lsx

    db.get(Lsx, lenh_ghi_du_san_luong_quen_bam_xong).han_hoan_thanh_sx = date(2026, 8, 29)
    db.commit()

    bc = boi_canh.nap(db, [lenh_ghi_du_san_luong_quen_bam_xong])
    assert tien_do.tre_han(bc, lenh_ghi_du_san_luong_quen_bam_xong, BAY_GIO) is True
