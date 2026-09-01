"""Tách lần chạy công đoạn (docs/spec-thuc-te-vs-ke-hoach.md §1.3, §2.4).

Bất biến xương sống của cả file: TỔNG số lượng các phân đoạn LUÔN bằng số lượng dòng gốc. Mọi
đường vào (tách, tách tiếp, gộp) đều phải giữ nó — lệch một tờ ở đây là lệch cả bảng cân đối vật
tư lẫn định mức khoán.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.db import Base, SessionLocal, engine
from app.models.don_vi_do import DonViDo
from app.models.lsx import LB_TO, LsxCongDoan
from app.models.xep_lich import NGUON_IN_GHEP, NGUON_LSX, TT_CHO_XEP, XepLichCongDoan

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    """Schema trắng, KHÔNG seed: cả file chỉ đụng `xep_lich_cong_doan` và luật tách/gộp thuần —
    kéo cả bộ danh mục vào chỉ làm mỗi test chậm thêm vài giây."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_dong_moi_mac_dinh_la_mot_phan_doan_duy_nhat(db):
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=1, source_thu_tu=0,
                        loai_buoc="may", trang_thai=TT_CHO_XEP)
    db.add(d)
    db.commit()
    db.refresh(d)
    assert d.phan_doan_so == 1
    assert d.phan_doan_tong == 1
    assert d.goc_dong_id is None
    assert d.so_luong is None      # None = "cả bước", KHÁC hẳn với 0


def test_migration_0253_co_trong_danh_sach():
    from app.db_migrations import MIGRATIONS
    assert any(ma == "0253_xep_lich_phan_doan" for ma, _fn in MIGRATIONS)


# ============================ Task 2 — luật tách / gộp =====================================
def _dong_goc(db, tong=10000.0) -> XepLichCongDoan:
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_id=None, lsx_cong_doan_id=77, source_thu_tu=0,
                        loai_buoc="may", trang_thai=TT_CHO_XEP,
                        start_at=_T0, finish_at=_T0 + timedelta(hours=5), so_luong=tong)
    db.add(d)
    db.commit()
    return d


def test_tach_hai_phan_giu_tong_va_danh_so(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])

    assert [float(d.so_luong) for d in ra] == [6000.0, 4000.0]
    assert [d.phan_doan_so for d in ra] == [1, 2]
    assert {d.phan_doan_tong for d in ra} == {2}
    assert ra[0].id == g.id                 # phân đoạn ĐẦU giữ id gốc → không mất neo ngoài
    assert ra[0].goc_dong_id is None
    assert ra[1].goc_dong_id == g.id
    assert sum(float(d.so_luong) for d in ra) == 10000.0


def test_tach_giu_nguyen_neo_cong_doan_va_khong_dong_step_key(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[5000, 5000])
    assert {d.lsx_cong_doan_id for d in ra} == {77}
    assert {d.source_thu_tu for d in ra} == {0}


def test_phan_doan_sau_khong_thua_ke_gio_cua_goc(db):
    """Tách xong, phân đoạn 2 trở đi phải CHỜ XẾP — thừa kế giờ của gốc là tự nhân đôi chỗ máy."""
    from app.models.xep_lich import TT_CHO_XEP as _CHO
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    assert ra[1].start_at is None and ra[1].finish_at is None
    assert ra[1].trang_thai == _CHO


def test_tach_lech_tong_thi_chan(db):
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    with pytest.raises(XepLich2Error) as e:
        P.tach(db, dong_id=g.id, cac_phan=[6000, 3000])
    assert "tổng" in str(e.value).lower()


def test_tach_phai_it_nhat_hai_phan_va_moi_phan_duong(db):
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    with pytest.raises(XepLich2Error):
        P.tach(db, dong_id=g.id, cac_phan=[10000])
    with pytest.raises(XepLich2Error):
        P.tach(db, dong_id=g.id, cac_phan=[10000, 0])


def test_tach_dong_da_khoa_thi_chan(db):
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    g.is_locked = True
    db.commit()
    with pytest.raises(XepLich2Error) as e:
        P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    assert "khóa" in str(e.value).lower()


def test_gop_tra_ve_mot_dong_giu_tong(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    P.tach(db, dong_id=g.id, cac_phan=[6000, 3000, 1000])
    lai = P.gop(db, dong_id=g.id)
    assert lai.id == g.id
    # Gộp xong là TRỌN bước ⇒ `so_luong` về NULL đúng nghĩa cột. Giữ lại con số cứng 10.000 là đẻ
    # nguồn số thứ hai: đơn hạ xuống 8.000 thì tầng thực thi vẫn cỡ việc theo 10.000.
    assert lai.so_luong is None
    assert lai.phan_doan_so == 1 and lai.phan_doan_tong == 1
    assert P.cac_phan_doan(db, lai) == [lai]


def test_ty_le_dung_cho_ca_dong_chua_tach(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    assert P.ty_le_trong_cum(g, P.cac_phan_doan(db, g)) == 1.0
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    cum = P.cac_phan_doan(db, ra[0])
    assert P.ty_le_trong_cum(ra[0], cum) == pytest.approx(0.6)
    assert P.ty_le_trong_cum(ra[1], cum) == pytest.approx(0.4)


# ============================ Task 3 — thời lượng theo tỉ lệ ==============================
def test_sl_tinh_nhan_ty_le_phan_doan():
    """Phân đoạn 60% thì SL đưa vào engine thời lượng cũng phải là 60% — không đụng công thức.

    Soi ở mức HÀM: dựng lệnh thật chỉ để nhân một số là phí, mà chỗ dễ sai lại đúng là phép nhân
    này (nhân vào `chiem_may_phut` sau khi tính sẽ nhân CẢ thời gian chuẩn bị máy — sai hẳn:
    chuẩn bị máy KHÔNG chia theo sản lượng, mỗi lần chạy đều phải canh lại).
    """
    from app.services.xep_lich_service import _nhan_sl_tinh

    assert _nhan_sl_tinh((10000.0, "tờ", "10.000 tờ"), 0.6) == (6000.0, "tờ", "10.000 tờ")
    assert _nhan_sl_tinh(None, 0.6) is None
    assert _nhan_sl_tinh((10000.0, "tờ", ""), 1.0) == (10000.0, "tờ", "")


# ================== Vá sau rà soát: tổng · vết · làm tròn · dòng không tách được ==========
def test_tach_khi_so_luong_null_lay_tong_tu_buoc(db):
    """Dòng lịch THẬT luôn có `so_luong` NULL — không nơi nào trong hệ ghi cột đó lúc sinh dòng.

    Chặn ở đây thì nút Tách không bao giờ bấm được trên dữ liệu thật; tổng phải suy từ SL VÀO của
    chính bước mà dòng đang neo.
    """
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_theo_buoc(db, so_luong=None)
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    assert [float(d.so_luong) for d in ra] == [6000.0, 4000.0]


def test_tach_uu_tien_tong_buoc_truyen_vao(db):
    """`tong_buoc` là tổng NGƯỜI BẤM đang nhìn thấy — thắng số đọc lại từ bước, để hai bên không
    chia theo hai con số khác nhau."""
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_theo_buoc(db, so_luong=None)
    ra = P.tach(db, dong_id=g.id, cac_phan=[5000, 3000], tong_buoc=8000)
    assert [float(d.so_luong) for d in ra] == [5000.0, 3000.0]


def test_tach_khong_ra_noi_tong_thi_chan(db):
    """Không `so_luong`, không `tong_buoc`, bước cũng không có SL vào ⇒ chia theo số bịa là sai."""
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db, tong=None)
    with pytest.raises(XepLich2Error) as e:
        P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    assert "số lượng" in str(e.value).lower()


def test_tach_khong_tu_commit(db):
    """`tach` chỉ `flush`: vết audit ở tầng service phải nằm CÙNG một commit với việc tách.

    Tự commit trong đây thì audit lỗi sau đó ⇒ dòng đã tách vĩnh viễn mà không một dòng vết nào.
    """
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    moi_id = ra[1].id
    db.rollback()
    assert db.get(XepLichCongDoan, moi_id) is None
    assert float(db.get(XepLichCongDoan, g.id).so_luong) == 10000.0


def test_created_by_cua_phan_doan_moi_la_nguoi_bam_tach(db):
    """Vết "ai đẻ ra dòng này" phải chỉ vào người BẤM TÁCH, không phải người đưa lệnh vào kế hoạch."""
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    g.created_by = 1
    db.commit()
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000], actor=SimpleNamespace(id=7))
    assert ra[1].created_by == 7


def test_gop_mat_dong_goc_thi_chan(db):
    """Mất bản ghi gốc thì `cum[0]` là phân đoạn 2 — gộp im lặng sẽ nuốt mất phần đầu (10.000→4.000)."""
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    sau_id = ra[1].id
    db.delete(g)
    db.commit()
    with pytest.raises(XepLich2Error):
        P.gop(db, dong_id=sau_id)


def test_tach_lam_tron_khop_cot_ba_chu_so(db):
    """Cột là `NUMERIC(18,3)`: kiểm bất biến trên float rồi lưu 3 chữ số là để tổng trôi một tờ."""
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[3333.3333, 3333.3333, 3333.3334])
    phan = [float(d.so_luong) for d in ra]
    assert all(round(p, 3) == p for p in phan)
    assert sum(phan) == 10000.0


def test_tach_dong_in_ghep_cu_thi_chan(db):
    """In ghép kiểu CŨ (trước mg 0151, chưa neo bước chung) đi nhánh thời lượng riêng, KHÔNG qua
    `_sl_tinh` ⇒ tách ra hai phần thì mỗi phần vẫn ăn trọn thời lượng, máy bị đặt gấp đôi."""
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    d = XepLichCongDoan(nguon=NGUON_IN_GHEP, bai_ghep_id=5, bai_ghep_cong_doan_id=None,
                        source_thu_tu=0, loai_buoc="may", trang_thai=TT_CHO_XEP, so_luong=10000)
    db.add(d)
    db.commit()
    with pytest.raises(XepLich2Error) as e:
        P.tach(db, dong_id=d.id, cac_phan=[6000, 4000])
    assert "in ghép" in str(e.value).lower()


# ============================ Task 4 — hai route tách / gộp ==============================
def _buoc_to(db, *, so_luong_vao=10000.0) -> LsxCongDoan:
    """Bước TỔ tính RA giờ thật: 10.000 tờ ÷ (1.000 tờ/người-giờ × 1 người) × 60 = 600 phút.

    Chọn bước TỔ chứ không phải bước MÁY vì nó chỉ cần đúng MỘT dòng đơn vị trong danh mục (cùng
    đơn vị ⇒ quy đổi hệ số 1); bước máy còn đòi máy khai tốc độ + đơn vị tốc độ + cầu quy đổi,
    dựng thêm ngần ấy chỉ để ra cùng một con số.
    """
    if db.query(DonViDo).filter(DonViDo.ma == "to").first() is None:
        db.add(DonViDo(ma="to", ten="tờ", ho="to"))
    b = LsxCongDoan(
        lsx_id=9_999, thu_tu=0, ten="Dán hộp", loai_buoc=LB_TO,
        so_luong_vao=so_luong_vao, don_vi_vao="to",
        nang_suat=1000, so_nhan_cong=1, so_nhan_cong_tieu_chuan=1,
        khoan_json={"don_vi": "to"},
    )
    db.add(b)
    db.commit()
    return b


def _dong_theo_buoc(db, *, so_luong=10000.0, start=None) -> XepLichCongDoan:
    """Dòng lịch neo vào một bước TỔ tính được giờ — dùng cho mọi test đụng tới thời lượng."""
    b = _buoc_to(db)
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=b.id, source_thu_tu=0,
                        loai_buoc=LB_TO, trang_thai=TT_CHO_XEP, start_at=start, so_luong=so_luong)
    db.add(d)
    db.commit()
    return d


def _svc(db):
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.xep_lich_2_repo import XepLich2Repository
    from app.services.xep_lich_2 import XepLich2Service

    return XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))


def _phut(d) -> float:
    from app.services.xep_lich_service import _aware

    return (_aware(d.finish_at) - _aware(d.start_at)).total_seconds() / 60.0


def test_tach_va_gop_viet_lai_finish_at(db):
    """`finish_at` là cột PERSIST — đổi số lượng mà không viết lại là bộ dò `trung_may` đọc sai
    khoảng máy: tách xong thanh vẫn dài như cũ (khoá máy DƯ), gộp lại thì thanh ngắn hơn việc thật
    (hai lệnh chồng nhau ngoài xưởng mà không ai la)."""
    svc = _svc(db)
    g = _dong_theo_buoc(db, start=_T0)
    svc.tach_dong(dong_id=g.id, cac_phan=[6000, 4000], actor=None)
    assert _phut(g) == 360.0                     # 6.000 tờ, không phải 10.000
    svc.gop_dong(dong_id=g.id, actor=None)
    assert _phut(g) == 600.0


def test_tach_dong_tra_view_ca_cum(db):
    svc = _svc(db)
    g = _dong_theo_buoc(db)
    cum = svc.tach_dong(dong_id=g.id, cac_phan=[6000, 4000], actor=None)
    assert [v["phan_doan_so"] for v in cum] == [1, 2]
    assert [float(v["so_luong"]) for v in cum] == [6000.0, 4000.0]
    assert {v["phan_doan_tong"] for v in cum} == {2}


def test_view_phoi_sl_vao_cua_buoc_ke_ca_khi_dong_chua_tach(db):
    """Nút Tách trên màn bật/tắt theo `so_luong_buoc`, KHÔNG theo `so_luong`.

    Dòng chưa tách gần như luôn có `so_luong` NULL (không nơi nào ghi cột đó lúc sinh dòng) — view
    chỉ phơi mỗi `so_luong` thì màn đọc ra "bước chưa biết số lượng" và nút Tách xám vĩnh viễn,
    trong khi chính bước vẫn khai đủ 10.000.
    """
    svc = _svc(db)
    d = _dong_theo_buoc(db, so_luong=None)
    v = svc.dong_view(d)
    assert v["so_luong"] is None
    assert v["so_luong_buoc"] == 10000.0
    # Tách xong mỗi thanh mang phần việc RIÊNG, còn tổng của bước vẫn là MỘT con số chung — đó là
    # thứ hộp thoại đem ra đối chiếu "còn lại bao nhiêu".
    cum = svc.tach_dong(dong_id=d.id, cac_phan=[6000, 4000], actor=None)
    assert [x["so_luong"] for x in cum] == [6000.0, 4000.0]
    assert {x["so_luong_buoc"] for x in cum} == {10000.0}


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _dong_qua_app() -> int:
    """Dựng dòng lịch bằng session của CHÍNH app.

    KHÔNG dùng fixture `db` của file này chung với fixture `client`: cả hai đều `drop_all` +
    `create_all`, xài lẫn là xoá schema ngay dưới chân test.
    """
    s = SessionLocal()
    try:
        return _dong_theo_buoc(s).id
    finally:
        s.close()


def test_route_tach_va_gop_day_sse(client):
    """Mọi mutation của bàn xếp lịch đều phải đẩy SSE (§12.11) — tách/gộp không ngoại lệ."""
    import app.routers.xep_lich_2 as R

    h = _headers(client)
    dong_id = _dong_qua_app()
    ban_tin: list = []
    goc_broadcast = R.hub.broadcast
    R.hub.broadcast = lambda m: ban_tin.append(m)
    try:
        r = client.post(f"/api/xep-lich-2/dong/{dong_id}/tach",
                        json={"cac_phan": [6000, 4000]}, headers=h)
        assert r.status_code == 200, r.text
        assert [float(d["so_luong"]) for d in r.json()["dong"]] == [6000.0, 4000.0]
        r2 = client.post(f"/api/xep-lich-2/dong/{dong_id}/gop", headers=h)
        assert r2.status_code == 200, r2.text
        assert r2.json()["dong"]["so_luong"] is None      # gộp xong = trọn bước
        assert r2.json()["dong"]["phan_doan_tong"] == 1
    finally:
        R.hub.broadcast = goc_broadcast
    assert len(ban_tin) >= 2


def test_route_tach_lech_tong_tra_400(client):
    h = _headers(client)
    dong_id = _dong_qua_app()
    r = client.post(f"/api/xep-lich-2/dong/{dong_id}/tach",
                    json={"cac_phan": [6000, 3000]}, headers=h)
    assert r.status_code == 400


def test_route_tach_doi_quyen_sua_lich(client):
    """Tách/gộp là cùng quyền SỬA LỊCH — không đẻ quyền mới, và không để ngỏ cho khách vãng lai."""
    dong_id = _dong_qua_app()
    r = client.post(f"/api/xep-lich-2/dong/{dong_id}/tach", json={"cac_phan": [6000, 4000]})
    assert r.status_code in (401, 403)
