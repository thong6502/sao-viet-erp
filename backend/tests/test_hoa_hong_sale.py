"""Ô khai % hoa hồng của NV kinh doanh (chủ 29/07/2026 — "khai phần trăm hoa hồng cho NV sale").

File này canh Ô KHAI: khai/đọc lại đúng số, chặn gõ nhầm 5 thành 500%, và % đi theo MỐC HIỆU
LỰC — đổi % từ tháng sau thì kỳ tháng trước tính lại vẫn ra số cũ.

⚠️ Từ 21/08/2026 hoa hồng ĐÃ ra tiền thật, nhưng KHÔNG qua cột này: `_compute` vẫn không đọc
`employee_salaries.commission_pct`. Đường ra tiền là CHỤP % vào `orders.commission_pct` lúc chốt
đơn rồi nhân với hoá đơn bán trong kỳ — xem `tests/test_hoa_hong_kinh_doanh.py`.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.payroll_repo import PayrollRepository
from app.services.payroll_service import PayrollService
from tests.test_luong_api import _admin_token, _h, _make_emp, _sal


def _khai(client, token, eid, *, tu_ngay, pct, luong=15_000_000):
    r = client.post(f"/api/luong/salaries/{eid}",
                    json={"effective_from": tu_ngay, "luong_vi_tri": luong,
                          "commission_pct": pct},
                    headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


def test_khai_va_doc_lai_dung_so(client):
    """⭐ Bẫy Pydantic nuốt field: thiếu `commission_pct` ở schema Out thì service trả đúng mà
    API trả thiếu, KHÔNG báo lỗi gì. Dự án này đã dính đúng kiểu đó hai lần."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Kinh Doanh A")

    assert _khai(client, token, eid, tu_ngay="2026-06-01", pct=0.05)["commission_pct"] == 0.05

    doc_lai = client.get(f"/api/luong/salaries/{eid}", headers=_h(token)).json()["items"]
    assert doc_lai[0]["commission_pct"] == 0.05, "đọc lại phải ra đúng số vừa khai"


def test_khong_khai_thi_bang_0(client):
    """Đại đa số nhân viên không hưởng hoa hồng — không khai gì thì phải là 0, không phải null."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Không Hoa Hồng")
    client.post(f"/api/luong/salaries/{eid}",
                json={"effective_from": "2026-06-01", "luong_vi_tri": 9_000_000},
                headers=_h(token))

    assert client.get(f"/api/luong/salaries/{eid}",
                      headers=_h(token)).json()["items"][0]["commission_pct"] == 0


def test_go_qua_100_phan_tram_bi_chan(client):
    """Gõ "5" thay vì 0.05 ra 500% hoa hồng — chặn ngay ở cổng."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Gõ Nhầm")
    r = client.post(f"/api/luong/salaries/{eid}",
                    json={"effective_from": "2026-06-01", "luong_vi_tri": 9_000_000,
                          "commission_pct": 5},
                    headers=_h(token))
    assert r.status_code == 422, r.text


def test_doi_phan_tram_KHONG_lam_doi_ky_cu(client):
    """⭐ Lý do đặt cột ở `employee_salaries` chứ không ở `employees`.

    Khai 5% từ 01/06, đổi 8% từ 01/08 ⇒ mốc tháng 6 vẫn giữ 5%. Nếu để trên hồ sơ thì sửa % là
    mất số cũ, kỳ lương cũ tính lại ra số khác."""
    token = _admin_token(client)
    eid = _make_emp(client, token, name="NV Đổi Hoa Hồng")
    _khai(client, token, eid, tu_ngay="2026-06-01", pct=0.05)
    _khai(client, token, eid, tu_ngay="2026-08-01", pct=0.08)

    items = client.get(f"/api/luong/salaries/{eid}", headers=_h(token)).json()["items"]
    theo_ngay = {i["effective_from"]: i["commission_pct"] for i in items}
    assert theo_ngay["2026-06-01"] == 0.05, "mốc cũ KHÔNG được đổi theo"
    assert theo_ngay["2026-08-01"] == 0.08


def test_khai_hoa_hong_KHONG_lam_doi_mot_dong_nao(client):
    """⭐ `_compute` KHÔNG được tự đọc % của nhân viên — chốt bằng SỐ THẬT.

    Từ 21/08/2026 hoa hồng đã ra tiền, nhưng theo ĐÚNG MỘT đường: chụp % vào đơn lúc chốt rồi
    nhân với hoá đơn bán trong kỳ (khoản danh mục `hoa_hong_kd`, nguồn `auto`). Nếu `_compute`
    đọc thêm cột này của hồ sơ thì NV ăn hoa hồng HAI LẦN — một lần theo hoá đơn, một lần phẳng
    theo % nhân lương — mà phiếu lương trông vẫn bình thường vì hai số nằm hai chỗ.

    Gọi thẳng `_compute` với đủ 26 công: NV không có chấm công thì lương = 0, so 0 với 0 là
    test rỗng (đã dính đúng bẫy này ở các test thuế trước đây)."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        params = svc.get_params()
        emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                              payroll_group=None, pay_grade_key=None, dependents_count=0)

        def _v(pct):
            return svc._compute(employee=emp, params=params, actual_cong=26, standard_cong=26,
                                salary=_sal(luong_vi_tri=15_000_000, commission_pct=pct),
                                on=date(2026, 10, 1))

        khong, co = _v(0), _v(0.10)
        assert khong["gross"] > 0, "test phải có lương thật thì so sánh mới có nghĩa"
        for k in ("gross", "pit", "bhxh", "luong_cong", "allowance", "chuyen_can"):
            assert khong[k] == co[k], f"khai hoa hồng làm đổi {k}: {khong[k]} → {co[k]}"
    finally:
        db.close()
