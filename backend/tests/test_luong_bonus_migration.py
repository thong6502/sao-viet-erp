"""Migration 0124 — dời 6 cột thưởng nhập tay sang khoản danh mục.

Đây là migration ĐỤNG TIỀN: nó ghi đè cột lương của kỳ đang nháp. Hai thứ phải đúng tuyệt đối:
mỗi đồng rời khỏi cột phải vào đúng một dòng khoản, và kỳ ĐÃ CHỐT không được suy suyển.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_move_bonus_columns_to_components

_BONUS_COLS = ("thuong_5s", "thuong_doanh_so", "thuong_thanh_tich",
               "phep_nam", "tra_dong_phuc", "other_bonus")


def _fixture():
    """DB tối giản: 1 kỳ nháp + 1 kỳ đã chốt, mỗi kỳ 1 dòng lương có đủ 6 cột thưởng."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    cols = ", ".join(f"{c} NUMERIC(14,2) NOT NULL DEFAULT 0" for c in _BONUS_COLS)
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE payroll_periods (id INTEGER PRIMARY KEY, status VARCHAR(8))"))
        cn.execute(text(
            f"CREATE TABLE payroll_lines (id INTEGER PRIMARY KEY, period_id INTEGER, "
            f"gross NUMERIC(14,2) DEFAULT 0, {cols})"))
        cn.execute(text(
            "CREATE TABLE payroll_components (id INTEGER PRIMARY KEY, code VARCHAR(40), "
            "name VARCHAR(120), kind VARCHAR(8), is_taxable BOOLEAN)"))
        cn.execute(text(
            "CREATE TABLE payroll_line_components (id INTEGER PRIMARY KEY, line_id INTEGER, "
            "component_id INTEGER, code VARCHAR(40), name VARCHAR(120), kind VARCHAR(8), "
            "is_taxable BOOLEAN, amount NUMERIC(14,2), source VARCHAR(8), note VARCHAR(255), "
            "UNIQUE(line_id, component_id))"))
        cn.execute(text(
            "INSERT INTO payroll_periods (id, status) VALUES (1, 'draft'), (2, 'locked')"))
        for code, name in (("thuong_5s", "Thưởng 5S"), ("thuong_doanh_so", "Thưởng doanh số"),
                           ("thuong_thanh_tich", "Thưởng thành tích"),
                           ("tra_dong_phuc", "Trả đồng phục"),
                           ("thu_nhap_khac_ct", "Thu nhập khác (chịu thuế)")):
            cn.execute(text("INSERT INTO payroll_components (code, name, kind, is_taxable) "
                            "VALUES (:c, :n, 'thu', 1)"), {"c": code, "n": name})
        # Dòng 1 = kỳ NHÁP, dòng 2 = kỳ ĐÃ CHỐT — cùng số tiền để so sánh trực tiếp.
        for lid, pid in ((1, 1), (2, 2)):
            cn.execute(text(
                "INSERT INTO payroll_lines (id, period_id, gross, thuong_5s, thuong_doanh_so, "
                "thuong_thanh_tich, phep_nam, tra_dong_phuc, other_bonus) "
                "VALUES (:l, :p, 9000000, 300000, 2000000, 500000, 1500000, 200000, 700000)"),
                {"l": lid, "p": pid})
    return engine


def _sum_cols(db, line_id: int) -> float:
    expr = " + ".join(_BONUS_COLS)
    return float(db.execute(text(f"SELECT {expr} FROM payroll_lines WHERE id = :l"),
                            {"l": line_id}).scalar_one())


def test_0124_doi_cot_thuong_sang_khoan_khong_lam_lech_mot_dong():
    """⭐ Tổng tiền BẤT BIẾN, và kỳ đã chốt không bị đụng."""
    engine = _fixture()
    with Session(engine) as db:
        truoc = _sum_cols(db, 1)
        _migrate_move_bonus_columns_to_components(db)
        _migrate_move_bonus_columns_to_components(db)   # idempotent: chạy 2 lần không nhân đôi

        # Kỳ NHÁP: cột về 0, tiền chuyển hết sang khoản.
        assert _sum_cols(db, 1) == 0
        rows = db.execute(text(
            "SELECT code, amount, source, note FROM payroll_line_components "
            "WHERE line_id = 1 ORDER BY id")).all()
        assert sum(float(r[1]) for r in rows) == truoc, "tiền bốc hơi hoặc nhân đôi khi dời cột"
        assert {r[2] for r in rows} == {"line"}, "phải là khoản của RIÊNG kỳ này"
        by_code = {r[0]: float(r[1]) for r in rows}
        assert by_code["thuong_5s"] == 300_000
        assert by_code["thuong_doanh_so"] == 2_000_000
        assert by_code["thuong_thanh_tich"] == 500_000
        assert by_code["tra_dong_phuc"] == 200_000
        # `phep_nam` + `other_bonus` không có khoản riêng ⇒ gộp vào MỘT dòng "Thu nhập khác".
        assert by_code["thu_nhap_khac_ct"] == 1_500_000 + 700_000
        note = next(r[3] for r in rows if r[0] == "thu_nhap_khac_ct")
        assert "Phép năm" in note and "Thưởng khác" in note, "mất dấu vết nguồn tiền"

        # `gross` đã lưu KHÔNG đổi — migration chỉ dời chỗ, không tính lại lương.
        assert db.execute(text("SELECT gross FROM payroll_lines WHERE id = 1")).scalar_one() == 9000000

        # ⭐ Kỳ ĐÃ CHỐT: y nguyên. Phiếu lương đã ký không được đổi một đồng.
        assert _sum_cols(db, 2) == truoc
        assert db.execute(text(
            "SELECT COUNT(*) FROM payroll_line_components WHERE line_id = 2")).scalar_one() == 0


def test_0124_khong_dung_dong_khoan_hcns_da_tu_them():
    """Dòng khoản do HCNS tự thêm là dữ liệu của người dùng — không cộng thêm sau lưng họ.

    Va chạm thì BỎ QUA và để tiền ở cột cũ (vẫn được engine cộng, vẫn hiện ở khối "Khoản kỳ cũ")
    — thà hiển thị hơi cũ còn hơn sửa số tiền người ta đã gõ."""
    engine = _fixture()
    with Session(engine) as db:
        cid = db.execute(text(
            "SELECT id FROM payroll_components WHERE code = 'thu_nhap_khac_ct'")).scalar_one()
        db.execute(text(
            "INSERT INTO payroll_line_components (line_id, component_id, code, name, kind, "
            "is_taxable, amount, source, note) VALUES (1, :c, 'thu_nhap_khac_ct', "
            "'Thu nhập khác (chịu thuế)', 'thu', 1, 999000, 'line', 'HCNS tự thêm')"), {"c": cid})
        db.commit()

        _migrate_move_bonus_columns_to_components(db)

        row = db.execute(text(
            "SELECT amount, note FROM payroll_line_components "
            "WHERE line_id = 1 AND code = 'thu_nhap_khac_ct'")).one()
        assert float(row[0]) == 999_000 and row[1] == "HCNS tự thêm", "đã sửa số của người dùng"
        # 4 khoản có danh mục riêng vẫn dời được; `phep_nam` + `other_bonus` ở lại cột cũ.
        left = db.execute(text(
            "SELECT phep_nam, other_bonus, thuong_5s FROM payroll_lines WHERE id = 1")).one()
        assert float(left[0]) == 1_500_000 and float(left[1]) == 700_000
        assert float(left[2]) == 0


def test_0124_bo_qua_khi_thieu_bang():
    """DB chưa có bảng khoản (cài mới, chạy migration trước create_all) ⇒ không được nổ."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_move_bonus_columns_to_components(db)


# --- Migration 0125: đơn vị đơn giá khoán đổi từ MÃ sang CHỮ -----------------


def test_0125_doi_ma_don_vi_cu_sang_chu_hien_thi():
    """Bản cũ lưu mã (`m2`) rồi FE dịch sang nhãn (`m²`). Nay ô Đơn vị gõ tự do nên bấm gợi ý
    "m²" sẽ lưu chuỗi KHÁC với mã cũ ⇒ hai dòng cùng nghĩa, khác giá trị. Migration dọn việc đó."""
    from app.db_migrations import _migrate_piece_rate_unit_free_text

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, group_name VARCHAR(40), "
            "name VARCHAR(255), unit VARCHAR(12), unit_price NUMERIC(14,2))"))
        for i, u in enumerate(("m2", "bai_in", "tan", "cuon", "luot", "hop", "to", "khac"), 1):
            cn.execute(text("INSERT INTO piece_rates (id, group_name, name, unit, unit_price) "
                            "VALUES (:i, 'to', 'viec', :u, 100)"), {"i": i, "u": u})
        # Đơn vị người dùng tự gõ (đã là chữ) — KHÔNG được đụng vào.
        cn.execute(text("INSERT INTO piece_rates (id, group_name, name, unit, unit_price) "
                        "VALUES (99, 'to', 'viec', 'mét tới', 100)"))

    with Session(engine) as db:
        _migrate_piece_rate_unit_free_text(db)
        _migrate_piece_rate_unit_free_text(db)   # idempotent
        got = {r[0]: r[1] for r in db.execute(text("SELECT id, unit FROM piece_rates")).all()}

    assert [got[i] for i in range(1, 9)] == [
        "m²", "bài in", "tấn", "cuốn", "lượt", "hộp", "tờ", "khác"]
    assert got[99] == "mét tới", "đơn vị người dùng tự gõ bị migration đụng vào"


def test_0125_bo_qua_khi_chua_co_bang():
    from app.db_migrations import _migrate_piece_rate_unit_free_text

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_piece_rate_unit_free_text(db)
