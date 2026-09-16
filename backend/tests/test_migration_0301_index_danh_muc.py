"""Migration 0301: index cho các câu hỏi ngược "ai đang trỏ tới dòng danh mục này".

Ba thứ phải khoá:
  1. DB đi đường migration (dev/prod có bảng từ trước) NHẬN đủ index — `create_all` không bao giờ
     thêm index cho bảng đã tồn tại.
  2. Tên + cột index ở migration TRÙNG model, không thì DB trắng và DB cũ lại ra hai bộ index khác
     nhau (đúng lỗi mg `0287` phải vá).
  3. Câu hỏi của tab Nhật ký THẬT SỰ đi qua index, không chỉ "index có tồn tại".
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db import Base
from app.db_migrations import _INDEX_0301, MIGRATIONS


def _chay(db: Session) -> None:
    dict(MIGRATIONS)["0301_index_danh_muc_tra_nguoc"](db)


def _index(insp, bang: str) -> dict[str, list[str]]:
    return {i["name"]: i["column_names"] for i in insp.get_indexes(bang)}


def test_0301_tao_du_index_tren_db_cu():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        for sql in (
            "CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, target VARCHAR(255), created_at DATETIME)",
            "CREATE TABLE phieu_thanh_phan (id INTEGER PRIMARY KEY, giay_id INTEGER, may_id INTEGER)",
            "CREATE TABLE phieu_thanh_pham (id INTEGER PRIMARY KEY, cong_doan_id INTEGER)",
            "CREATE TABLE phieu_vat_tu (id INTEGER PRIMARY KEY, vat_tu_id INTEGER)",
            "CREATE TABLE stock_request_lines (id INTEGER PRIMARY KEY, hang_loai VARCHAR(8), hang_id INTEGER)",
            "CREATE TABLE stock_voucher_lines (id INTEGER PRIMARY KEY, hang_loai VARCHAR(8), hang_id INTEGER)",
        ):
            db.execute(text(sql))
        db.commit()

        _chay(db)
        insp = inspect(db.get_bind())
        for bang, ten, cot in _INDEX_0301:
            assert _index(insp, bang).get(ten) == list(cot), f"{bang}: thiếu {ten}"
        _chay(db)   # chạy lại không nổ


def test_0301_thieu_bang_hoac_cot_thi_bo_qua():
    """DB trung gian: bảng chưa có, hoặc có bảng mà chưa có cột — không được nổ cả lượt migrate."""
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE stock_request_lines (id INTEGER PRIMARY KEY, hang_id INTEGER)"))
        db.commit()
        _chay(db)
        assert "ix_stock_request_lines_hang" not in _index(inspect(db.get_bind()), "stock_request_lines")


def test_0301_ten_va_cot_index_trung_model():
    for bang, ten, cot in _INDEX_0301:
        idx = {i.name: [c.name for c in i.columns] for i in Base.metadata.tables[bang].indexes}
        assert idx.get(ten) == list(cot), (
            f"{bang}: model chưa khai {ten}{cot} — DB trắng (`create_all`) sẽ lệch DB đi đường migration")


def test_nhat_ky_theo_target_di_qua_index():
    from app.models.audit import AuditLog

    eng = create_engine("sqlite://")
    AuditLog.__table__.create(eng)
    with eng.connect() as c:
        plan = " ".join(str(r[-1]) for r in c.execute(text(
            "EXPLAIN QUERY PLAN SELECT id FROM audit_logs WHERE target = 'cong_doan:1' "
            "ORDER BY created_at DESC, id DESC LIMIT 50")))
    assert "ix_audit_logs_target_created_at" in plan, plan
