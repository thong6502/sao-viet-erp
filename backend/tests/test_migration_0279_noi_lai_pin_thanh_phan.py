"""Migration `0279` — nối lại pin `phieu_thanh_phan_id` đã chết ở báo giá / đơn / lệnh.

Tới 07/09/2026 lưu lại phiếu tính giá là xoá–chèn lại `phieu_thanh_phan` ⇒ id đổi, mà báo giá và
đơn đã chốt vẫn ôm số cũ. Hậu quả: drawer "Lệnh dự kiến" hiện "—" ở mọi ô kỹ thuật, và chốt đơn bị
chặn ("trỏ tới sản phẩm tính giá đã bị xoá"). Migration dò lại theo TÊN trong ĐÚNG phiếu tính giá
của báo giá đó; lệnh sản xuất thì chép thẳng pin của dòng đơn nguồn.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_noi_lai_pin_thanh_phan


def _engine():
    """PTG 7 có Bìa/Ruột (id 40/41) + hai hàng trùng tên "Tờ rơi"; PTG 9 là phiếu của báo giá KHÁC."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text("CREATE TABLE phieu_thanh_phan (id INTEGER PRIMARY KEY, phieu_id INTEGER, ten TEXT)"))
        con.execute(text("CREATE TABLE quotes (id INTEGER PRIMARY KEY, phieu_tinh_gia_id INTEGER)"))
        con.execute(text("CREATE TABLE quote_versions (id INTEGER PRIMARY KEY, quote_id INTEGER)"))
        con.execute(text(
            "CREATE TABLE quote_items (id INTEGER PRIMARY KEY, quote_version_id INTEGER, "
            "phieu_thanh_phan_id INTEGER, product_name TEXT)"
        ))
        con.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, quotation_id INTEGER)"))
        con.execute(text(
            "CREATE TABLE order_lines (id INTEGER PRIMARY KEY, order_id INTEGER, "
            "phieu_thanh_phan_id INTEGER, description TEXT)"
        ))
        con.execute(text(
            "CREATE TABLE lsx (id INTEGER PRIMARY KEY, order_line_id INTEGER, phieu_thanh_phan_id INTEGER)"
        ))

        for i, phieu, ten in (
            (40, 7, "Bìa sách"), (41, 7, "Ruột sách 192 trang"),
            (42, 7, "Tờ rơi"), (43, 7, "Tờ rơi"),      # trùng tên trong cùng phiếu → không đoán
            (60, 9, "Bìa sách"),                        # cùng tên nhưng thuộc phiếu của báo giá khác
        ):
            con.execute(text("INSERT INTO phieu_thanh_phan (id, phieu_id, ten) VALUES (:i, :p, :t)"),
                        {"i": i, "p": phieu, "t": ten})

        con.execute(text("INSERT INTO quotes (id, phieu_tinh_gia_id) VALUES (1, 7), (2, NULL)"))
        con.execute(text("INSERT INTO quote_versions (id, quote_id) VALUES (10, 1), (20, 2)"))
        con.execute(text("INSERT INTO orders (id, quotation_id) VALUES (100, 1), (200, 2)"))

        qi = [
            (1, 10, 40, "Bìa sách"),                 # pin CÒN SỐNG → không đụng
            (2, 10, 17, "Ruột sách 192 trang"),      # pin chết, tên khớp duy nhất → vá thành 41
            (3, 10, 18, "Tờ rơi"),                   # pin chết, tên khớp 2 hàng → để nguyên
            (4, 10, 19, "Standee"),                  # pin chết, không tên nào khớp → để nguyên
            (5, 20, 21, "Bìa sách"),                 # báo giá không gắn phiếu tính giá → để nguyên
            (6, 10, None, "Hàng gõ tay"),            # không có pin → ngoài phạm vi
        ]
        for id_, ver, pin, ten in qi:
            con.execute(text(
                "INSERT INTO quote_items (id, quote_version_id, phieu_thanh_phan_id, product_name) "
                "VALUES (:i, :v, :p, :t)"
            ), {"i": id_, "v": ver, "p": pin, "t": ten})

        ol = [
            (1, 100, 40, "Bìa sách"),
            (2, 100, 17, "Ruột sách 192 trang"),
            (3, 100, 18, "Tờ rơi"),
            (4, 100, 19, "Standee"),
            (5, 200, 21, "Bìa sách"),
            (6, 100, None, "Hàng gõ tay"),
        ]
        for id_, don, pin, ten in ol:
            con.execute(text(
                "INSERT INTO order_lines (id, order_id, phieu_thanh_phan_id, description) "
                "VALUES (:i, :o, :p, :t)"
            ), {"i": id_, "o": don, "p": pin, "t": ten})

        # Lệnh: 1 pin sống · 2 pin chết theo dòng đơn vá được · 4 pin chết mà dòng đơn cũng chết
        # (→ NULL, thà rỗng còn hơn số ma) · 6 pin chết mà dòng nguồn vốn không có pin (→ NULL).
        for id_, line, pin in ((1, 1, 40), (2, 2, 17), (4, 4, 19), (6, 6, 33)):
            con.execute(text(
                "INSERT INTO lsx (id, order_line_id, phieu_thanh_phan_id) VALUES (:i, :l, :p)"
            ), {"i": id_, "l": line, "p": pin})
    return eng


def _pin(con, bang, id_):
    return con.execute(
        text(f"SELECT phieu_thanh_phan_id FROM {bang} WHERE id = :i"), {"i": id_}
    ).scalar()


def _chay(eng):
    with Session(eng) as db:
        _migrate_noi_lai_pin_thanh_phan(db)


def test_bao_gia_va_don_do_lai_theo_ten_trong_dung_phieu():
    eng = _engine()
    _chay(eng)
    with eng.connect() as con:
        for bang in ("quote_items", "order_lines"):
            assert _pin(con, bang, 1) == 40, bang       # pin sống giữ nguyên
            assert _pin(con, bang, 2) == 41, bang       # pin chết → dò ra đúng "Ruột sách"
            assert _pin(con, bang, 3) == 18, bang       # trùng tên → không đoán
            assert _pin(con, bang, 4) == 19, bang       # không khớp tên nào
            assert _pin(con, bang, 5) == 21, bang       # không biết phiếu nguồn → không mượn PTG khác
            assert _pin(con, bang, 6) is None, bang


def test_lenh_chep_pin_cua_dong_don_nguon():
    eng = _engine()
    _chay(eng)
    with eng.connect() as con:
        assert _pin(con, "lsx", 1) == 40      # pin sống, không đụng
        assert _pin(con, "lsx", 2) == 41      # theo dòng đơn vừa vá
        assert _pin(con, "lsx", 4) == 19      # dòng đơn cũng chết → giữ nguyên số của dòng đơn
        assert _pin(con, "lsx", 6) is None    # dòng đơn không có pin → trả về rỗng


def test_chay_lai_lan_hai_idempotent():
    eng = _engine()
    _chay(eng)
    with eng.connect() as con:
        truoc = [_pin(con, b, i) for b in ("quote_items", "order_lines") for i in range(1, 7)]
        truoc += [_pin(con, "lsx", i) for i in (1, 2, 4, 6)]
    _chay(eng)
    with eng.connect() as con:
        sau = [_pin(con, b, i) for b in ("quote_items", "order_lines") for i in range(1, 7)]
        sau += [_pin(con, "lsx", i) for i in (1, 2, 4, 6)]
    assert sau == truoc


def test_bo_qua_khi_thieu_bang():
    """DB chưa có phân hệ báo giá (bản cũ / test dựng bảng lẻ) → không nổ, chỉ bỏ qua."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text("CREATE TABLE phieu_thanh_phan (id INTEGER PRIMARY KEY, phieu_id INTEGER, ten TEXT)"))
    _chay(eng)
