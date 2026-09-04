"""Migration `0264` + `0265` — tách ĐVT của DÒNG GỘP ra khỏi ĐVT của từng phần.

Cụm "Sách bìa mềm" bán theo *cuốn* nhưng bìa và ruột đo bằng *cái*. Trước `0264` báo giá ghi
"cuốn" lên CẢ HAI dòng con (mẹo để bản in gộp lấy được đơn vị cụm), nên mọi màn không gộp —
tab Thương mại của đơn, drawer Kế hoạch SX, phiếu giao hàng — đọc ra "Bìa sách · 2.000 cuốn".

`0264` chép qua pin `phieu_thanh_phan_id`. `0265` vét nốt các dòng mất pin (lưu lại phiếu tính
giá là xoá–chèn lại thành phần ⇒ id đổi) bằng cách dò theo cặp (nhãn nhóm, tên phần).
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_dvt_nhom_bao_gia_don, _migrate_dvt_nhom_do_theo_ten

NHOM = "Sách bìa mềm 192 trang, khổ 16x24cm"


def _engine():
    """Hình dạng bảng TRƯỚC `0264` — chưa có cột `dvt_nhom` ở quote_items/order_lines."""
    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text(
            "CREATE TABLE phieu_thanh_phan (id INTEGER PRIMARY KEY, ten TEXT, "
            "don_vi_tinh TEXT, nhom_bao_gia TEXT, dvt_nhom TEXT)"
        ))
        con.execute(text(
            "CREATE TABLE quote_items (id INTEGER PRIMARY KEY, phieu_thanh_phan_id INTEGER, "
            "product_name TEXT, unit TEXT, nhom TEXT)"
        ))
        con.execute(text(
            "CREATE TABLE order_lines (id INTEGER PRIMARY KEY, phieu_thanh_phan_id INTEGER, "
            "description TEXT, don_vi_tinh TEXT, nhom TEXT)"
        ))

        # Thành phần CÒN SỐNG của phiếu tính giá: bìa + ruột đều "cái", cụm bán theo "cuốn".
        for i, ten in ((40, "Bìa sách"), (41, "Ruột sách 192 trang")):
            con.execute(text(
                "INSERT INTO phieu_thanh_phan (id, ten, don_vi_tinh, nhom_bao_gia, dvt_nhom) "
                "VALUES (:i, :t, 'cái', :n, 'cuốn')"
            ), {"i": i, "t": ten, "n": NHOM})
        # Thành phần gây NHẬP NHẰNG: cùng nhãn nhóm + cùng tên nhưng đơn vị cụm khác.
        con.execute(text(
            "INSERT INTO phieu_thanh_phan (id, ten, don_vi_tinh, nhom_bao_gia, dvt_nhom) "
            "VALUES (50, 'Tờ rơi kèm', 'tờ', :n, 'bộ')"
        ), {"n": NHOM})
        con.execute(text(
            "INSERT INTO phieu_thanh_phan (id, ten, don_vi_tinh, nhom_bao_gia, dvt_nhom) "
            "VALUES (51, 'Tờ rơi kèm', 'tờ', :n, 'túi')"
        ), {"n": NHOM})

        def them(bang, cot_ten, cot_dvt, rows):
            for id_, tp_id, ten, dvt, nhom in rows:
                con.execute(text(
                    f"INSERT INTO {bang} (id, phieu_thanh_phan_id, {cot_ten}, {cot_dvt}, nhom) "
                    "VALUES (:i, :p, :t, :d, :n)"
                ), {"i": id_, "p": tp_id, "t": ten, "d": dvt, "n": nhom})

        rows = [
            # 1-2: pin CÒN SỐNG → `0264` chép qua pin.
            (1, 40, "Bìa sách", "cuốn", NHOM),
            (2, 41, "Ruột sách 192 trang", "cuốn", NHOM),
            # 3-4: pin CHẾT (id 17/18 đã bị xoá) → chỉ `0265` dò theo tên mới chữa được.
            (3, 17, "Bìa sách", "cuốn", NHOM),
            (4, 18, "Ruột sách 192 trang", "cuốn", NHOM),
            # 5: pin chết + tên khớp 2 thành phần khác `dvt_nhom` → KHÔNG đoán, để nguyên.
            (5, 19, "Tờ rơi kèm", "tờ", NHOM),
            # 6: không có nhãn nhóm → ngoài phạm vi cả hai migration.
            (6, None, "Tờ rơi lẻ", "tờ", None),
        ]
        them("quote_items", "product_name", "unit", rows)
        them("order_lines", "description", "don_vi_tinh", rows)
    return eng


def _doc(con, bang, cot_dvt, id_):
    return con.execute(
        text(f"SELECT {cot_dvt}, dvt_nhom FROM {bang} WHERE id = :i"), {"i": id_}
    ).one()


BANG = (("quote_items", "unit"), ("order_lines", "don_vi_tinh"))


def test_0264_chep_qua_pin_con_song():
    eng = _engine()
    with Session(eng) as db:
        _migrate_dvt_nhom_bao_gia_don(db)

    with eng.connect() as con:
        for bang, cot in BANG:
            assert _doc(con, bang, cot, 1) == ("cái", "cuốn"), bang  # bìa trả về "cái"
            assert _doc(con, bang, cot, 2) == ("cái", "cuốn"), bang
            # Pin chết: `0264` cố ý KHÔNG đụng — đó là việc của `0265`.
            assert _doc(con, bang, cot, 3) == ("cuốn", None), bang
            assert _doc(con, bang, cot, 6) == ("tờ", None), bang


def test_0265_do_theo_ten_khi_mat_pin():
    eng = _engine()
    with Session(eng) as db:
        _migrate_dvt_nhom_bao_gia_don(db)
        _migrate_dvt_nhom_do_theo_ten(db)

    with eng.connect() as con:
        for bang, cot in BANG:
            assert _doc(con, bang, cot, 3) == ("cái", "cuốn"), bang
            assert _doc(con, bang, cot, 4) == ("cái", "cuốn"), bang
            # Tên khớp NHIỀU thành phần khai `dvt_nhom` khác nhau → thà để nguyên còn hơn gán bừa.
            assert _doc(con, bang, cot, 5) == ("tờ", None), bang
            # Dòng không nhãn nhóm vẫn nguyên vẹn.
            assert _doc(con, bang, cot, 6) == ("tờ", None), bang
            # Dòng đã được `0264` xử theo pin sống thì `0265` không ghi đè.
            assert _doc(con, bang, cot, 1) == ("cái", "cuốn"), bang


def test_chay_lai_lan_hai_idempotent():
    eng = _engine()
    with Session(eng) as db:
        _migrate_dvt_nhom_bao_gia_don(db)
        _migrate_dvt_nhom_do_theo_ten(db)
    with eng.connect() as con:
        truoc = [_doc(con, b, c, i) for b, c in BANG for i in range(1, 7)]

    with Session(eng) as db:
        _migrate_dvt_nhom_bao_gia_don(db)
        _migrate_dvt_nhom_do_theo_ten(db)
    with eng.connect() as con:
        assert [_doc(con, b, c, i) for b, c in BANG for i in range(1, 7)] == truoc
