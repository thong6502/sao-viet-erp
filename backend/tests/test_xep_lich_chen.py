"""G1 — chèn lệnh gấp & đẩy: bốn luật của `chen_xem_truoc`.

Kiểm bằng đơn vị NHỎ (`_chen_bang` không đụng tới): các luật ở đây đều là chuyện thứ tự và lượng
lùi, không phải chuyện dựng DTO. Bốn luật, mỗi luật một test — vì mỗi cái sai một kiểu khác nhau:

1. Chèn tại ranh giới, KHÔNG cắt đôi việc đang xếp.
2. Việc sau lùi VỪA ĐỦ hết chồng lấn; khe trống nuốt vừa thì DỪNG LAN (không lùi cứng).
3. Đúng MỘT tầng: lệnh bị đẩy thì cả chuỗi của nó lùi chừng ấy, nhưng không lan sang lệnh thứ ba.
4. Gặp dòng đã KHÓA thì dừng và nói ra (`chan == "gap_khoa"`).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.lsx import LsxCongDoan
from app.repositories.xep_lich_repo import XepLichRepository
from app.services.xep_lich_service import XepLichValidationError

from .test_xep_lich_service import (  # noqa: F401 — fixture dùng chung
    _hai_lsx_san_sang, _in_step, admin, bg_svc, customer, db, lsx_svc, orders, xl_svc,
)


def _utc(h: int, m: int = 0, ngay: int = 27) -> datetime:
    return datetime(2026, 7, ngay, h, m, tzinfo=timezone.utc)


@pytest.fixture()
def hai_dong(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Hai lệnh trên CÙNG một máy: A và B mỗi lệnh một bước In, cộng một bước "In gấp" ở lệnh A.

    Máy `_may_in` khai makeready 30 + 5000 tờ/h ⇒ 2500 tờ = 30 chuẩn bị + 30 chạy = **60 phút**.
    Số tròn để kỳ vọng đọc được bằng mắt.

    Bước "In gấp" phải thêm TRƯỚC `dua_vao_lsx` — dòng lịch chỉ sinh lúc đưa lệnh vào kế hoạch, thêm
    sau thì không có dòng nào để chèn.
    """
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)  # loại nhiễu nghỉ lễ
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for lsx in (a, b):
        s = _in_step(db, lsx.id)
        s.so_luong_vao, s.chay_phut, s.so_luot_chay = 2500, None, 1
    may_id = _in_step(db, a.id).may_id
    db.add(LsxCongDoan(
        lsx_id=a.id, thu_tu=9, ten="In gấp", nhom="print", loai_buoc="may",
        may_id=may_id, so_luong_vao=2500, don_vi_vao="to", don_vi_ra="to",
    ))
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    xl_svc.dua_vao_lsx(lsx_id=b.id, actor=admin)
    repo = XepLichRepository(db)
    dong_a = [d for d in repo.by_lsx(a.id) if d.source_thu_tu != 9]
    chen = next(d for d in repo.by_lsx(a.id) if d.source_thu_tu == 9)
    return {
        "a": a, "b": b,
        "may_id": may_id,
        "dong_a": dong_a[0],
        "dong_b": repo.by_lsx(b.id)[0],
        "dong_chen": chen,
    }


def _giay(dt) -> tuple[int, int]:
    return (dt.hour, dt.minute)


def test_chen_khong_cat_doi_viec_dang_xep(db, xl_svc, admin, hai_dong):
    """Mốc chèn rơi vào GIỮA việc A ⇒ nhích tới lúc A xong, không xẻ ngang A."""
    may_id = hai_dong["may_id"]
    xl_svc.gan(dong_id=hai_dong["dong_a"].id,
               patch={"may_id": may_id, "start_at": _utc(8)}, actor=admin)   # A: 08:00→09:00

    res = xl_svc.chen_xem_truoc(dong_id=hai_dong["dong_chen"].id, may_id=may_id, tai=_utc(8, 30))

    assert _giay(res["start_at"]) == (9, 0), "phải nhích tới ranh giới sau của A, không cắt đôi A"
    # A đứng yên: nó chạy xong TRƯỚC mốc chèn nên không liên quan.
    assert hai_dong["dong_a"].id not in [r["id"] for r in res["rows"]]


def test_khe_trong_nuot_vua_thi_dung_lan(db, xl_svc, admin, hai_dong):
    """Ví dụ trong plan: A xong 09:00, B bắt đầu 10:00, chèn việc 60 phút vào 09:00 ⇒ B KHÔNG lùi.

    Lùi cứng bằng thời lượng việc chèn sẽ đẩy oan B đi một tiếng dù khe trống vừa khít.
    """
    may_id = hai_dong["may_id"]
    xl_svc.gan(dong_id=hai_dong["dong_a"].id,
               patch={"may_id": may_id, "start_at": _utc(8)}, actor=admin)    # A: 08:00→09:00
    xl_svc.gan(dong_id=hai_dong["dong_b"].id,
               patch={"may_id": may_id, "start_at": _utc(10)}, actor=admin)   # B: 10:00→11:00

    res = xl_svc.chen_xem_truoc(dong_id=hai_dong["dong_chen"].id, may_id=may_id, tai=_utc(9))

    assert _giay(res["start_at"]) == (9, 0)
    day = [r for r in res["rows"] if not r["la_viec_chen"]]
    assert day == [], "khe trống 09:00–10:00 nuốt vừa việc 60 phút ⇒ không việc nào phải lùi"


def test_viec_sau_lui_vua_du_het_chong_lan(db, xl_svc, admin, hai_dong):
    """Không có khe: B bắt đầu ngay khi A xong ⇒ B lùi ĐÚNG bằng phần chồng lấn, không hơn."""
    may_id = hai_dong["may_id"]
    xl_svc.gan(dong_id=hai_dong["dong_a"].id,
               patch={"may_id": may_id, "start_at": _utc(8)}, actor=admin)    # A: 08:00→09:00
    xl_svc.gan(dong_id=hai_dong["dong_b"].id,
               patch={"may_id": may_id, "start_at": _utc(9)}, actor=admin)    # B: 09:00→10:00

    res = xl_svc.chen_xem_truoc(dong_id=hai_dong["dong_chen"].id, may_id=may_id, tai=_utc(9))

    moi_b = next(r["moi"] for r in res["rows"] if r["id"] == hai_dong["dong_b"].id)
    assert _giay(moi_b) == (10, 0), "B lùi đúng 60 phút (hết chồng lấn), không lùi thừa"
    assert res["chan"] is None


def test_gap_dong_da_khoa_thi_dung_va_noi_ra(db, xl_svc, admin, hai_dong):
    """Khóa là người đã chốt — máy tự dời qua là phá. Dừng tại đó và trả cờ `gap_khoa`."""
    may_id = hai_dong["may_id"]
    xl_svc.gan(dong_id=hai_dong["dong_a"].id,
               patch={"may_id": may_id, "start_at": _utc(8)}, actor=admin)
    xl_svc.gan(dong_id=hai_dong["dong_b"].id,
               patch={"may_id": may_id, "start_at": _utc(9)}, actor=admin)
    xl_svc.khoa(dong_id=hai_dong["dong_b"].id, khoa=True, actor=admin)

    res = xl_svc.chen_xem_truoc(dong_id=hai_dong["dong_chen"].id, may_id=may_id, tai=_utc(9))

    assert res["chan"] == "gap_khoa"
    assert hai_dong["dong_b"].id not in [r["id"] for r in res["rows"]], "dòng đã khóa KHÔNG bị dời"


def test_chen_khong_ghi_gi_vao_db(db, xl_svc, admin, hai_dong):
    """Xem trước là NHÁP: thoát ra là mất. Ghi thật chỉ đi qua `gan_loat` khi người dùng bấm Lưu."""
    may_id = hai_dong["may_id"]
    xl_svc.gan(dong_id=hai_dong["dong_a"].id,
               patch={"may_id": may_id, "start_at": _utc(8)}, actor=admin)
    xl_svc.gan(dong_id=hai_dong["dong_b"].id,
               patch={"may_id": may_id, "start_at": _utc(9)}, actor=admin)
    truoc = {d.id: d.start_at for d in xl_svc.repo.list_dong()}

    xl_svc.chen_xem_truoc(dong_id=hai_dong["dong_b"].id, may_id=may_id, tai=_utc(8, 30))

    db.expire_all()
    sau = {d.id: d.start_at for d in xl_svc.repo.list_dong()}
    assert sau == truoc


def test_chua_tinh_duoc_thoi_luong_thi_bao_ro(db, xl_svc, admin, hai_dong, monkeypatch):
    """Máy chưa khai tốc độ ⇒ không hứa nổi giờ nào; báo thẳng chứ đừng chèn vào một mốc bịa."""
    monkeypatch.setattr(xl_svc, "_chiem_tren_may", lambda dong, may_id: 0.0)
    with pytest.raises(XepLichValidationError):
        xl_svc.chen_xem_truoc(dong_id=hai_dong["dong_b"].id,
                              may_id=hai_dong["may_id"], tai=_utc(9))
