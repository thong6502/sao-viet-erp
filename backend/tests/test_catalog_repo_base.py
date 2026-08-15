"""Nền `CatalogRepo` — lưới chặn cho phần thân CRUD mà 7 repo danh mục nay dùng CHUNG.

Gộp thân hàm lại thì một lỗi ở nền là hỏng cả bảy màn cùng lúc, nên bốn thứ dễ vỡ nhất được
đóng đinh ở đây:

  1. `next_ma()` đổi cách lọc (Python → SQL `LIKE`) mà mã kế tiếp phải RA Y HỆT bản cũ.
  2. Hoa/thường của mã: `kho_hang` viết HOA, `don_vi_do` viết thường — nền phải giữ ĐÚNG cả hai
     chiều (ghi và tra), đừng "đồng bộ" về một kiểu.
  3. `extra_conds()` — bộ lọc riêng của từng màn còn ăn.
  4. Trần `size` — client gõ `?size=99999` không kéo được cả bảng về.

⚠️ `lower()` của SQLite chỉ hạ được A–Z (Postgres hạ đủ Unicode), nên dữ liệu thử ở đây tránh
chữ HOA có dấu — đỏ vì engine test thì không nói lên điều gì về code.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — đăng ký metadata mọi bảng
from app.db import Base
from app.models.kho_hang import KhoHang
from app.repositories.bu_hao_repo import BuHaoRepository
from app.repositories.don_vi_do_repo import DonViDoRepository
from app.repositories.kho_hang_repo import KhoHangRepository
from app.repositories.khuon_be_repo import KhuonBeRepository


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _next_ma_kieu_cu(db, model, prefix: str) -> str:
    """BẢN CŨ của `next_ma` (trước 15/08/2026): kéo TOÀN BỘ cột `ma` về Python rồi mới regex.

    Giữ nguyên ở đây làm MỐC SO SÁNH — bản mới lọc `LIKE` ngay ở SQL, và test dưới bắt hai bản
    phải trả cùng một mã trên mọi bộ dữ liệu xấu.
    """
    rx = re.compile(rf"^{prefix}(\d+)$")
    mx = 0
    for ma in db.execute(select(model.ma)).scalars():
        m = rx.match((ma or "").strip().upper())
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{prefix}{mx + 1:04d}"


# ── 1. next_ma: đổi cách lọc, KHÔNG đổi kết quả ─────────────────────────────────
@pytest.mark.parametrize("dat_them,mong", [
    ([], "KHO-0001"),                                          # bảng trống
    (["KHO-0001", "KHO-0002"], "KHO-0003"),                    # liên tục
    (["KHO-0001", "KHO-0009"], "KHO-0010"),                    # có khoảng trống → chỉ TĂNG
    (["KHO-0012", "KHO-0003"], "KHO-0013"),                    # không phụ thuộc thứ tự chèn
    (["kho-0007"], "KHO-0008"),                                # mã lỡ viết thường vẫn phải kể
    (["KHO-A1", "KHO-", "KHOX-0099"], "KHO-0001"),             # đuôi không phải số → bỏ qua
    (["KB-0500", "VT-0300"], "KHO-0001"),                      # tiền tố khác → không lây số
    (["KHO-0004", "KB-0900", "kho-0011", "KHO-x"], "KHO-0012"),  # trộn đủ kiểu
])
def test_next_ma_giong_het_ban_cu(dat_them, mong):
    db = _db()
    for i, ma in enumerate(dat_them):
        db.add(KhoHang(ma=ma, ten=f"Kho {i}"))
    db.commit()

    repo = KhoHangRepository(db)
    assert repo.next_ma() == mong
    # Và quan trọng hơn: TRÙNG với bản cũ trên đúng bộ dữ liệu này.
    assert repo.next_ma() == _next_ma_kieu_cu(db, KhoHang, "KHO-")


def test_next_ma_ke_ca_hang_da_xoa_mem():
    """Xóa mềm giữ `ma` (unique) trong DB → mã đó vẫn KẸT, không được cấp lại cho kho mới."""
    db = _db()
    db.add(KhoHang(ma="KHO-0001", ten="Kho cũ", active=False))
    db.commit()
    assert KhoHangRepository(db).next_ma() == "KHO-0002"


def test_next_ma_loc_o_sql_chu_khong_keo_ca_cot_ve():
    """Câu SQL của `next_ma` phải mang `LIKE 'KHO-%'`.

    Đây là lý do đợt B5 đụng vào hàm này: bản cũ `SELECT ma FROM kho_hang` rồi lọc trong Python,
    tức là mỗi lần thêm một kho là tải cả danh mục về chỉ để lấy một con số.
    """
    db = _db()
    db.add(KhoHang(ma="KHO-0001", ten="Kho 1"))
    db.commit()

    cau: list[str] = []
    event.listen(db.get_bind(), "before_cursor_execute",
                 lambda conn, cur, sql, *a: cau.append(sql))
    KhoHangRepository(db).next_ma()

    doc_ma = [s for s in cau if "FROM kho_hang" in s]
    assert doc_ma, f"không thấy câu đọc kho_hang: {cau}"
    assert all("LIKE" in s.upper() for s in doc_ma), f"còn câu quét cả cột: {doc_ma}"


def test_next_ma_bao_loi_khi_danh_muc_khai_ma_tay():
    """Bù hao không có tiền tố mã tự sinh — gọi `next_ma` là lập trình sai, phải nổ rõ ràng."""
    with pytest.raises(NotImplementedError):
        BuHaoRepository(_db()).next_ma()


# ── 2. Hoa/thường của mã: mỗi danh mục một quy ước, nền giữ nguyên cả hai ────────
def test_kho_hang_ghi_va_tra_ma_bang_chu_hoa():
    db = _db()
    repo = KhoHangRepository(db)
    obj = repo.create({"ma": "  kho-0042  ", "ten": "Kho giấy"})
    assert obj.ma == "KHO-0042", "mã kho phải được đưa về chữ HOA khi ghi"
    assert repo.find_by_ma("kho-0042").id == obj.id, "tra mã phải bỏ qua hoa/thường"
    assert repo.find_by_ma("KHO-0042").id == obj.id
    assert repo.find_by_ma("   ") is None


def test_don_vi_do_ghi_va_tra_ma_bang_chu_thuong():
    """ĐỐI XỨNG với kho hàng, và cố ý NGƯỢC chiều.

    Mã đơn vị nằm nguyên dưới dạng chữ thường trong dữ liệu sống (`cong_doan.don_vi_vao/ra`,
    công thức tính giá, `giay.don_vi_gia`) — đưa sang HOA là vỡ mọi chỗ so mã. Bản kế hoạch B5
    từng ghi rằng repo này "ghi lower nhưng tìm bằng upper, tự mâu thuẫn"; đọc code thì không
    phải, cả hai chiều đều `lower()`. Test này khoá lại để không ai "sửa" nhầm.
    """
    db = _db()
    repo = DonViDoRepository(db)
    obj = repo.create({"ma": "  KG  ", "ten": "Ki-lô-gam"})
    assert obj.ma == "kg", "mã đơn vị phải được đưa về chữ THƯỜNG khi ghi"
    assert repo.find_by_ma("KG").id == obj.id
    assert repo.find_by_ma("kg").id == obj.id


def test_update_giu_nguyen_cot_khong_gui_len():
    """Khoá VẮNG trong `data` thì cột cũ phải còn — không thì sửa mỗi cái tên là xoá trắng ghi chú."""
    db = _db()
    repo = KhoHangRepository(db)
    obj = repo.create({"ma": "KHO-0001", "ten": "Kho A", "vi_tri": "Tầng 1", "ghi_chu": "cũ"})
    repo.update(obj, {"ten": "Kho B"})
    assert obj.ten == "Kho B" and obj.vi_tri == "Tầng 1" and obj.ghi_chu == "cũ"


# ── 3. extra_conds: bộ lọc riêng của từng màn ───────────────────────────────────
def test_extra_conds_loc_theo_tinh_trang_khuon():
    db = _db()
    repo = KhuonBeRepository(db)
    repo.create({"ma": "KB-0001", "ten": "Khuon hop A", "tinh_trang": "dang_dung"})
    repo.create({"ma": "KB-0002", "ten": "Khuon hop B", "tinh_trang": "hong"})

    rows, total = repo.list(tinh_trang="hong")
    assert total == 1 and rows[0].ma == "KB-0002"
    assert repo.list()[1] == 2, "không truyền `tinh_trang` thì phải thấy cả hai"


def test_tim_kiem_an_ca_cot_rieng_cua_khuon():
    """`search_fields` của khuôn bế gồm cả KHÁCH HÀNG và SỐ KỆ — người ta nhớ khuôn của ai,
    hiếm khi nhớ mã KB-####."""
    db = _db()
    repo = KhuonBeRepository(db)
    repo.create({"ma": "KB-0001", "ten": "Khuon hop", "khach_hang": "Cty Minh Long",
                 "so_ke": "K3-05"})
    repo.create({"ma": "KB-0002", "ten": "Khuon tui", "khach_hang": "Cty Hoa Sen"})

    assert repo.list(q="minh long")[1] == 1
    assert repo.list(q="k3-05")[1] == 1
    assert repo.list(q="khuon")[1] == 2


def test_facets_va_bang_dung_chung_mot_bo_loc():
    """Số trên tab và số dòng trong bảng cùng đi qua `_loc_q` — không được nói hai chuyện."""
    db = _db()
    repo = KhuonBeRepository(db)
    repo.create({"ma": "KB-0001", "ten": "Khuon hop", "khach_hang": "Minh Long",
                 "tinh_trang": "dang_dung"})
    repo.create({"ma": "KB-0002", "ten": "Khuon tui", "khach_hang": "Hoa Sen",
                 "tinh_trang": "hong"})

    assert repo.dem_theo_tinh_trang(q="minh long") == {"dang_dung": 1}
    assert sum(repo.dem_theo_tinh_trang().values()) == repo.list()[1]


# ── 4. Trần size + phân trang ───────────────────────────────────────────────────
def test_size_bi_kep_va_phan_trang_o_may_chu():
    db = _db()
    repo = KhoHangRepository(db)
    for i in range(1, 6):
        repo.create({"ma": f"KHO-{i:04d}", "ten": f"Kho {i}"})

    rows, total = repo.list(page=1, size=2)
    assert len(rows) == 2 and total == 5, "`total` là tổng THẬT, không phải len(items)"
    assert [r.ma for r in rows] == ["KHO-0001", "KHO-0002"]
    assert [r.ma for r in repo.list(page=3, size=2)[0]] == ["KHO-0005"]

    # Trần 200: gõ `?size=99999` không kéo được cả bảng về.
    assert len(repo.list(size=99999)[0]) == 5
    assert repo.list(size=99999)[1] == 5
    assert len(repo.list(page=0, size=0)[0]) == 1, "page/size <= 0 bị nâng về 1"


def test_don_vi_do_xep_theo_ho_roi_moi_toi_ma():
    """`order_cols` của đơn vị là `(ho, ma)` — bảng phải gom `kg · g · tấn` liền nhau."""
    db = _db()
    repo = DonViDoRepository(db)
    repo.create({"ma": "to", "ten": "To", "ho": "so_luong"})
    repo.create({"ma": "kg", "ten": "Ki lo", "ho": "khoi_luong"})
    repo.create({"ma": "g", "ten": "Gam", "ho": "khoi_luong"})

    assert [r.ma for r in repo.list()[0]] == ["g", "kg", "to"]
    assert repo.list(ho="KHOI_LUONG")[1] == 2, "lọc theo họ không phân biệt hoa/thường"
