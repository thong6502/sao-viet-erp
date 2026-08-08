"""PROBE TẠM — xoá sau khi chạy. Kiểm chứng nhánh apply_self_deduction=False có được engine chạy."""
import app.services.payroll_service as ps
from tests import test_luong_api as T


def test_probe_engine_nhan_co_false(client):
    seen = []
    orig = ps.PayrollService._auto_pit

    def spy(self, **kw):
        seen.append(kw.get("apply_self_deduction"))
        return orig(self, **kw)

    ps.PayrollService._auto_pit = spy
    try:
        T.test_tat_giam_tru_ban_than_thi_thue_tang(client)
    finally:
        ps.PayrollService._auto_pit = orig
    assert False in seen, f"engine KHONG bao gio nhan False; seen={set(seen)}"
    assert True in seen, f"seen={set(seen)}"
