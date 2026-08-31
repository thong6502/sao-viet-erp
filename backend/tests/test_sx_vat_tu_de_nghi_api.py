"""Đề nghị cấp vật tư công đoạn — đường dây HTTP `/api/san-xuat/work-items/{id}/material-requests`
(spec-de-nghi-cap-vat-tu-cong-doan §6, Task 6).

Soi tầng router + gác quyền, KHÔNG dựng lại cả luồng nghiệp vụ (khuôn `test_san_xuat_dong_nhom_api`
— luật đã có test SERVICE riêng ở `test_sx_vat_tu_de_nghi.py`, khớp response dict đã kiểm ở đó):
  · chưa đăng nhập → 401;
  · admin (Giám đốc, KHÔNG có bit `san_xuat:assign_work`) → 403, đúng như mọi endpoint ghi khác
    của module (khớp `test_san_xuat_dong_nhom_api.py::test_dong_thieu_admin_thieu_bit_assign_work_403`).

CHỦ Ý KHÔNG dùng fixture `db` ở đây: `conftest.client` và `db` (từ `test_lsx_service.py`) đều
`drop_all`+`create_all` trên CÙNG một engine SQLite in-memory (StaticPool một connection) — nhận cả
hai trong một test là cái dựng sau xoá sạch cái dựng trước (task-6-ruling-route.md, ruling 20).

Hai luật nghiệp vụ mà đường HTTP này lẽ ra chứng minh được đã có test SERVICE gọi thẳng
`vat_tu_de_nghi.tao()`/`.sua()` rồi, KHÔNG lặp lại ở đây:
  · "đúng tổ trưởng mới ghi được" — `test_sx_vat_tu_de_nghi.py::test_khong_phai_to_truong_thi_chan`.
  · "không cần `kho:request`" — `test_sx_vat_tu_de_nghi.py::test_khong_can_quyen_kho_de_tao_de_nghi`.
  · "`sua()` để `StockRequestError` xuyên ra ngoài" —
    `test_sx_vat_tu_de_nghi.py::test_sua_qua_kho_huy_roi_nhap_so_duong_thi_chan_khong_ghi_nua_voi`.
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}
_T0 = "2026-08-31T08:00:00"


def _admin_h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_tao_de_nghi_can_dang_nhap(client):
    resp = client.post(
        "/api/san-xuat/work-items/1/material-requests",
        json={"can_luc": _T0, "lines": []},
    )
    assert resp.status_code == 401


def test_tao_de_nghi_admin_thieu_bit_assign_work_403(client):
    # Admin (Giám đốc) không có bit `assign_work` — cùng cổng với mọi endpoint ghi khác của
    # module (`_gate_to_truong` ở tầng service không bao giờ chạm tới vì cổng RBAC chặn trước).
    resp = client.post(
        "/api/san-xuat/work-items/1/material-requests",
        json={"can_luc": _T0, "lines": []},
        headers=_admin_h(client),
    )
    assert resp.status_code == 403


def test_sua_de_nghi_can_dang_nhap(client):
    resp = client.put(
        "/api/san-xuat/work-items/1/material-requests/1",
        json={"can_luc": _T0, "lines": []},
    )
    assert resp.status_code == 401


def test_sua_de_nghi_admin_thieu_bit_assign_work_403(client):
    resp = client.put(
        "/api/san-xuat/work-items/1/material-requests/1",
        json={"can_luc": _T0, "lines": []},
        headers=_admin_h(client),
    )
    assert resp.status_code == 403
