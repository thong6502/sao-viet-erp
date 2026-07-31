"""Migration 0130 — xoá hẳn thưởng năng suất KPI (chủ 29/07/2026).

`DROP COLUMN` là thao tác **không lùi được**: xoá xong thì trong DB không còn bản sao nào để khôi
phục. Nên migration có một cái HÃM — còn dòng lương nào mang tiền KPI thì không drop.

Test đáng giá nhất ở đây là `test_CON_TIEN_thi_KHONG_duoc_drop`: nó canh cái hãm đó. Hãm hỏng thì
không ai biết cho tới lúc chạy lên DB thật và tiền đã bay.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_drop_kpi_bonus

_COT_KPI = {"kpi_percent", "kpi_bonus"}


def _fixture(*, kpi_percent=0, kpi_bonus=0):
    """DB "cũ": `payroll_lines` còn 2 cột KPI + một dòng bật/tắt KPI theo tổ."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE payroll_lines (id INTEGER PRIMARY KEY, employee_id INTEGER, "
            "gross NUMERIC(14,2) NOT NULL DEFAULT 0, "
            "kpi_percent NUMERIC(6,2) NOT NULL DEFAULT 0, "
            "kpi_bonus NUMERIC(14,2) NOT NULL DEFAULT 0)"))
        cn.execute(text(
            "CREATE TABLE department_salary_components (id INTEGER PRIMARY KEY, "
            "department_id INTEGER, component_key VARCHAR(32), is_enabled BOOLEAN, "
            "value NUMERIC(14,2))"))
        cn.execute(
            text("INSERT INTO payroll_lines (id, employee_id, gross, kpi_percent, kpi_bonus) "
                 "VALUES (1, 7, 9000000, :p, :b)"),
            {"p": kpi_percent, "b": kpi_bonus},
        )
        for key in ("kpi", "chuyen_can", "tang_ca"):
            cn.execute(
                text("INSERT INTO department_salary_components "
                     "(department_id, component_key, is_enabled, value) VALUES (1, :k, 1, 100)"),
                {"k": key},
            )
    return engine


def _run(engine) -> None:
    with Session(engine) as db:
        _migrate_drop_kpi_bonus(db)
        db.commit()


def _cot(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("payroll_lines")}


def _khoan_theo_to(engine) -> list[str]:
    with engine.begin() as cn:
        return [r[0] for r in cn.execute(text(
            "SELECT component_key FROM department_salary_components ORDER BY component_key"))]


def test_DB_SACH_thi_drop_ca_hai_cot():
    """Không dòng nào mang tiền KPI ⇒ dọn sạch. Đây là trạng thái DB thật hôm nay."""
    engine = _fixture()
    _run(engine)

    assert _COT_KPI & _cot(engine) == set(), "phải drop cả 2 cột"
    assert "gross" in _cot(engine), "chỉ được đụng 2 cột KPI, đừng chạm cột tiền khác"


def test_CON_TIEN_thi_KHONG_duoc_drop():
    """⭐ Cái hãm. Còn tiền KPI ⇒ GIỮ NGUYÊN cột và giữ nguyên số.

    DROP là không lùi được, mà DB thật trên VPS thì tôi không đọc được. Thà để lại cột thừa (vô
    hại — model không đọc nữa) còn hơn xoá nhầm tiền của người ta."""
    engine = _fixture(kpi_percent=80, kpi_bonus=500_000)
    _run(engine)

    assert _COT_KPI <= _cot(engine), "còn tiền mà vẫn drop ⇒ mất dữ liệu không cứu được"
    with engine.begin() as cn:
        assert float(cn.execute(text(
            "SELECT kpi_bonus FROM payroll_lines WHERE id = 1")).scalar()) == 500_000


def test_chi_co_PHAN_TRAM_ma_chua_ra_tien_cung_duoc_giu():
    """% đã chấm mà tiền chưa ra (tổ chưa bật trần) vẫn là dữ liệu người ta nhập — đừng vứt."""
    engine = _fixture(kpi_percent=75, kpi_bonus=0)
    _run(engine)
    assert _COT_KPI <= _cot(engine)


def test_dong_bat_tat_KPI_theo_to_bi_xoa_khoan_khac_con_nguyen():
    """Cấu hình bật/tắt không phải tiền ⇒ xoá vô điều kiện. Nhưng CHỈ dòng `kpi`."""
    engine = _fixture()
    _run(engine)
    assert _khoan_theo_to(engine) == ["chuyen_can", "tang_ca"]


def test_chay_lai_lan_hai_va_DB_moi_deu_khong_sao():
    """Migration chạy MỖI lần khởi động; DB dựng mới bằng `create_all` vốn không có 2 cột này."""
    engine = _fixture()
    _run(engine)
    _run(engine)                       # lần hai — không được nổ
    assert _COT_KPI & _cot(engine) == set()

    trong = create_engine("sqlite+pysqlite:///:memory:")
    with Session(trong) as db:
        _migrate_drop_kpi_bonus(db)    # chưa có bảng nào — im lặng bỏ qua
        db.commit()
