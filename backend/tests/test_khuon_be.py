"""Danh mục Khuôn (khai báo lưu trữ) — CRUD nhẹ + xử lý TRÙNG MÃ do xóa mềm.

Mirror test_kho_hang: mã KB-#### sinh ngầm, xóa mềm giữ `ma` (unique) → create() tái
dùng đúng hàng khi mã trùng thay vì 409. Self-contained in-memory DB.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata mọi bảng
from app.repositories.khuon_be_repo import KhuonBeRepository
from app.services.khuon_be_service import (
    KhuonBeDuplicate,
    KhuonBeService,
    KhuonBeValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, KhuonBeService(KhuonBeRepository(db))


def test_create_and_validate():
    db, svc = _svc()
    k = svc.create(dict(ma="KB-0001", ten="Khuôn hộp bánh A", so_ke="Kệ B3"))
    assert k.id and k.ma == "KB-0001" and k.active is True
    assert k.so_ke == "Kệ B3" and k.tinh_trang == "dang_dung"
    with pytest.raises(KhuonBeValidationError):            # thiếu tên
        svc.create(dict(ma="KB-0002", ten=""))


def test_reject_bad_tinh_trang():
    db, svc = _svc()
    with pytest.raises(KhuonBeValidationError):
        svc.create(dict(ten="Khuôn X", tinh_trang="bay_hoi"))


def test_ma_auto_generated_when_blank():
    db, svc = _svc()
    a = svc.create(dict(ten="Khuôn 1"))                    # không truyền mã → tự sinh
    b = svc.create(dict(ma="", ten="Khuôn 2"))            # mã rỗng cũng tự sinh
    assert a.ma == "KB-0001" and b.ma == "KB-0002"


def test_ma_auto_skips_soft_deleted_gap():
    db, svc = _svc()
    a = svc.create(dict(ten="Khuôn 1"))                    # KB-0001
    b = svc.create(dict(ten="Khuôn 2"))                    # KB-0002
    svc.update(b.id, dict(ten="Khuôn 2", active=False))   # xóa mềm KB-0002
    c = svc.create(dict(ten="Khuôn 3"))                   # phải là KB-0003, KHÔNG tái dùng 0002
    assert a.ma == "KB-0001" and c.ma == "KB-0003"


def test_duplicate_active_blocks():
    db, svc = _svc()
    svc.create(dict(ma="KB-0001", ten="Khuôn A"))
    with pytest.raises(KhuonBeDuplicate):                  # trùng khuôn đang hoạt động → chặn
        svc.create(dict(ma="kb-0001", ten="Khuôn khác"))  # (không phân biệt hoa/thường)


def test_soft_deleted_ma_reused_not_duplicate():
    db, svc = _svc()
    a = svc.create(dict(ma="KB-0001", ten="Khuôn cũ", so_ke="Kệ 1", ghi_chu="cũ"))
    svc.update(a.id, dict(ma="KB-0001", ten="Khuôn cũ", active=False))  # xóa mềm (như UI)

    # Tạo lại đúng mã đã xóa mềm → KHÔNG 409, tái dùng chính hàng đó (cùng id).
    b = svc.create(dict(ma="KB-0001", ten="Khuôn mới", so_ke="Kệ 2", ghi_chu="mới"))
    assert b.id == a.id                                    # cùng 1 hàng, không đẻ hàng rác
    assert b.active is True
    assert b.ten == "Khuôn mới" and b.so_ke == "Kệ 2" and b.ghi_chu == "mới"

    rows, total = svc.list(active=True)                   # chỉ 1 khuôn active, không nhân đôi
    assert total == 1 and rows[0].id == a.id


def _khach(db, code: str, name: str) -> int:
    from app.models.customer import Customer

    k = Customer(code=code, name=name)
    db.add(k)
    db.flush()
    return k.id


def test_search_theo_ten_va_so_ke():
    """Ô tìm quét MÃ · TÊN ấn phẩm · SỐ KỆ."""
    db, svc = _svc()
    svc.create(dict(ten="Khuôn hộp Minh Long", so_ke="Kệ A1"))
    svc.create(dict(ten="Khuôn tem", so_ke="Kệ B2"))
    rows, total = svc.list(q="minh long")
    assert total == 1 and rows[0].ten == "Khuôn hộp Minh Long"
    rows2, total2 = svc.list(q="b2")
    assert total2 == 1 and rows2[0].so_ke == "Kệ B2"


def test_search_theo_ten_khach():
    """Ô tìm quét cả TÊN KHÁCH (chủ yêu cầu 18/09/2026) — qua FK `khach_hang_id`, không phải cột
    chuỗi `khach_hang` cũ (đã gỡ ở mg `0202`). Gõ tên khách ra MỌI khuôn của khách đó, và số trên
    chip đếm theo đúng ô tìm ấy."""
    db, svc = _svc()
    ml = _khach(db, "KH-ML", "Cty Thuc pham Minh Long")
    hh = _khach(db, "KH-HH", "Cty Hai Ha")
    svc.create(dict(ten="Dao hộp bánh", khach_hang_id=ml, loai="khuon_be"))
    svc.create(dict(ten="Khung nhãn", khach_hang_id=ml, loai="khung_lua"))
    svc.create(dict(ten="Dao hộp kẹo", khach_hang_id=hh, loai="khuon_be"))
    svc.create(dict(ten="Khuôn chưa gán khách"))

    rows, total = svc.list(q="minh long")
    assert total == 2 and {r.ten for r in rows} == {"Dao hộp bánh", "Khung nhãn"}
    # Khớp tên khách HOẶC tên khuôn — "cty" chỉ nằm ở tên khách, ra khuôn của cả hai khách.
    assert svc.list(q="cty")[1] == 3
    assert svc.dem_theo_loai(q="minh long") == {"khuon_be": 1, "khung_lua": 1}


def test_chip_loai_dem_theo_loc_nang_cao():
    """Chip lọc theo LOẠI; lọc nâng cao (khách · tình trạng) ghép VÀ với chip.

    Số trên chip đếm DƯỚI lọc nâng cao — lọc khách X rồi mà chip vẫn khoe số của cả kho thì bấm
    vào ra ít hơn số hứa. Nhưng chip KHÔNG tự lọc theo chính nó: router bỏ `loai` ra trước khi đếm.
    """
    db, svc = _svc()
    ml = _khach(db, "KH-ML", "Minh Long")
    hh = _khach(db, "KH-HH", "Hai Ha")
    svc.create(dict(ten="A", khach_hang_id=ml, loai="khuon_be", tinh_trang="dang_dung"))
    svc.create(dict(ten="B", khach_hang_id=ml, loai="khuon_ep", tinh_trang="hong"))
    svc.create(dict(ten="C", khach_hang_id=ml, loai="khuon_be", tinh_trang="hong"))
    svc.create(dict(ten="D", khach_hang_id=hh, loai="khuon_be", tinh_trang="hong"))

    assert svc.dem_theo_loai() == {"khuon_be": 3, "khuon_ep": 1}
    assert svc.dem_theo_loai(khach_hang_id=ml) == {"khuon_be": 2, "khuon_ep": 1}
    assert svc.dem_theo_loai(khach_hang_id=ml, tinh_trang="hong") == {"khuon_be": 1, "khuon_ep": 1}

    rows, total = svc.list(loai="khuon_be", khach_hang_id=ml, tinh_trang="hong")
    assert total == 1 and rows[0].ten == "C"


def test_api_loc_nhieu_tieu_chi(client):
    """Ba bộ lọc đi được qua QUERY STRING của `GET /api/khuon-be`, không chỉ ở tầng service.

    Nền router danh mục ban đầu chỉ mở ĐÚNG MỘT bộ lọc riêng (`loc`); tham số lạ thì FastAPI bỏ
    qua im lặng — bảng không lọc mà cũng không báo lỗi. Test này canh `loc_them` còn được khai.
    """
    from tests.test_danh_muc_http_contract import _admin

    h = _admin(client)
    tao_kh = client.post("/api/customers", json={"name": "ZZ Minh Long"}, headers=h)
    assert tao_kh.status_code == 201, tao_kh.text
    ml = tao_kh.json()["customer"]["id"]
    for ten, loai, tt in (("ZZ Dao A", "khuon_be", "dang_dung"), ("ZZ Dao B", "khuon_be", "hong"),
                          ("ZZ Ép C", "khuon_ep", "hong")):
        r = client.post("/api/khuon-be", headers=h, json={
            "ten": ten, "loai": loai, "tinh_trang": tt, "khach_hang_id": ml})
        assert r.status_code == 201, r.text
    client.post("/api/khuon-be", headers=h, json={"ten": "ZZ Dao lạc", "loai": "khuon_be"})

    r = client.get(f"/api/khuon-be?loai=khuon_be&tinh_trang=hong&khach_hang_id={ml}", headers=h)
    assert r.status_code == 200, r.text
    assert [x["ten"] for x in r.json()["items"]] == ["ZZ Dao B"]
    # Chip loại đếm dưới lọc khách + tình trạng, không dưới chính chip `loai`.
    assert r.json()["facets"] == {"khuon_be": 1, "khuon_ep": 1}
    # Ô tìm theo tên khách.
    tim = client.get("/api/khuon-be?q=minh%20long", headers=h).json()
    assert {x["ten"] for x in tim["items"]} == {"ZZ Dao A", "ZZ Dao B", "ZZ Ép C"}


def test_loc_so_ke_khop_chua(client):
    """Lọc SỐ KỆ khớp CHỨA, không phân hoa thường, ghép VÀ với chip + lọc khác — qua query string.

    Ô số kệ gõ tự do ("Kệ B3 — xưởng sau in"); người tìm chỉ nhớ "b3". Chip loại cũng phải đếm
    dưới lọc kệ, không thì chip hứa 3 mà bấm vào ra 1.
    """
    from tests.test_danh_muc_http_contract import _admin

    h = _admin(client)
    for ten, loai, ke, tt in (("ZZ K1", "khuon_be", "Kệ B3 — xưởng sau in", "dang_dung"),
                              ("ZZ K2", "khuon_ep", "kệ b3 tầng 2", "hong"),
                              ("ZZ K3", "khuon_be", "Kệ B1 — xưởng sau in", "dang_dung"),
                              ("ZZ K4", "khuon_be", None, "dang_dung")):
        r = client.post("/api/khuon-be", headers=h, json={
            "ten": ten, "loai": loai, "so_ke": ke, "tinh_trang": tt})
        assert r.status_code == 201, r.text

    r = client.get("/api/khuon-be?so_ke=B3", headers=h).json()
    assert {x["ten"] for x in r["items"]} == {"ZZ K1", "ZZ K2"}
    assert r["facets"] == {"khuon_be": 1, "khuon_ep": 1}
    r = client.get("/api/khuon-be?so_ke=%20b3%20&loai=khuon_be&tinh_trang=dang_dung", headers=h).json()
    assert [x["ten"] for x in r["items"]] == ["ZZ K1"]
    # Chuỗi trắng = không lọc, KHÔNG phải "kệ rỗng".
    assert client.get("/api/khuon-be?so_ke=%20", headers=h).json()["total"] == 4


def test_loc_va_dem_theo_tinh_trang():
    """Tab lọc của màn Khuôn bế chạy Ở MÁY CHỦ từ 14/08/2026.

    Trước đó màn kéo cả danh mục về rồi lọc + đếm trong JS; nay bảng chỉ cầm 20 dòng nên
    hai việc đó phải nằm đây: `list(tinh_trang=…)` lọc, `dem_theo_tinh_trang()` nuôi số
    trên tab — và số trên tab KHÔNG được đổi theo tab đang chọn.
    """
    db, svc = _svc()
    svc.create(dict(ten="Khuôn A", tinh_trang="dang_dung"))
    svc.create(dict(ten="Khuôn B", tinh_trang="dang_dung"))
    svc.create(dict(ten="Khuôn C", tinh_trang="hong"))

    rows, total = svc.list(tinh_trang="hong")
    assert total == 1 and rows[0].ten == "Khuôn C"

    assert svc.dem_theo_tinh_trang() == {"dang_dung": 2, "hong": 1}
    # Có ô tìm thì số trên tab đi theo ô tìm — tab khoe số cả danh mục là nói dối.
    assert svc.dem_theo_tinh_trang(q="khuôn c") == {"hong": 1}


# --- Nối vào bước lệnh sản xuất (mg 0205, 16/08/2026) ---------------------------


def test_dang_dat_lam_KHONG_con_doi_ngay():
    """🔴 mg `0293` (10/09/2026): ô "Ngày có khuôn (dự kiến)" GỠ HẲN, kèm luôn ràng buộc cứng
    "đang đặt làm thì phải khai ngày" ở `_validate`.

    Ngày đó không cắm vào phép tính nào (cửa sẵn-sàng-lập-kế-hoạch chỉ soi bước đã CHỌN dao chưa,
    xếp lịch/phát hành không đọc), nên nó chỉ bắt người lập lệnh bịa một con số rồi để đó lạc hậu.
    Bài này canh đúng chỗ đó: lưu "đang đặt làm" mà không ngày nào phải ĐI QUA, không ném lỗi.
    """
    db, svc = _svc()
    k = svc.create(dict(ten="Khuôn hộp mới", tinh_trang="dang_dat_lam"))
    db.expire_all()                                   # đọc lại từ DB, không lấy bản trong bộ nhớ
    assert svc.get(k.id).tinh_trang == "dang_dat_lam"
    assert not hasattr(svc.get(k.id), "ngay_ve_du_kien")


def test_khach_va_loai_duoc_luu_va_loc_duoc():
    """Hai chiều lọc của ô chọn dao ở bước lệnh. Không lưu được thì ô chọn bày cả kho."""
    db, svc = _svc()
    a = svc.create(dict(ten="Dao bế hộp A", khach_hang_id=7, loai="khuon_be"))
    svc.create(dict(ten="Dao ép nhũ hộp A", khach_hang_id=7, loai="khuon_ep"))
    svc.create(dict(ten="Dao bế hộp B", khach_hang_id=9, loai="khuon_be"))

    db.expire_all()
    assert svc.get(a.id).khach_hang_id == 7 and svc.get(a.id).loai == "khuon_be"

    # Lọc từng chiều và cả hai chiều.
    assert svc.list(khach_hang_id=7)[1] == 2
    assert svc.list(loai="khuon_be")[1] == 2
    rows, total = svc.list(khach_hang_id=7, loai="khuon_ep")
    assert total == 1 and rows[0].ten == "Dao ép nhũ hộp A"


def test_loai_khong_hop_le_bi_chan():
    db, svc = _svc()
    with pytest.raises(KhuonBeValidationError):
        svc.create(dict(ten="Khuôn lạ", loai="khuon_dap_noi"))


def test_accept_loai_khung_lua():
    """Khung lụa cũng lưu kho dùng lại như khuôn bế (chốt 04/09/2026) — kho phải nhận loại này,
    không thì bước lụa ở lệnh mở ô chọn ra rỗng và bấm 'làm mới' thì service ném 400."""
    db, svc = _svc()
    k = svc.create(dict(ten="Khung lụa hộp bánh A", loai="khung_lua", so_ke="Kệ C1"))
    assert k.loai == "khung_lua"
