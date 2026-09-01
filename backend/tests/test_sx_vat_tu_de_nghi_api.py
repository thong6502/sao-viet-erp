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


_PUT_PATH = "/api/san-xuat/work-items/{cong_viec_id}/material-requests/{de_nghi_id}"


def _cong_quyen(path: str, method: str):
    """Lấy đúng callable mà `require_permission(...)` đã cắm vào route, để `dependency_overrides`
    mở cổng RBAC cho MỘT test.

    `require_permission` sinh một closure MỚI mỗi lần gọi nên không thể lấy key bằng cách gọi lại
    nó — phải moi ra từ chính route đang chạy.
    """
    from app.main import app

    for r in app.routes:
        if getattr(r, "path", "") == path and method in getattr(r, "methods", set()):
            for d in r.dependant.dependencies:
                if getattr(d.call, "__name__", "") == "dependency":
                    return d.call
    raise AssertionError(f"không tìm thấy cổng quyền của {method} {path}")


def test_sua_de_nghi_bi_kho_khoa_thi_400_doc_duoc_chu_khong_500(client, monkeypatch):
    """Kho đã lập phiếu ⇒ `sua()` để `StockRequestError` xuyên ra; router PHẢI dịch thành 400.

    Luật này đã có test SERVICE (`test_sx_vat_tu_de_nghi.py::
    test_sua_qua_kho_huy_roi_nhap_so_duong_thi_chan_khong_ghi_nua_voi`), nhưng KHÔNG có gì canh
    mệnh đề `except (VatTuDeNghiError, StockRequestError)` ở tầng router: gỡ nó ra thì test service
    vẫn xanh, còn người bấm nhận 500 trắng không đọc được. FE đã ẩn nút "Sửa đề nghị" ngay khi kho
    có phiếu nên đường này chỉ tới được bằng HTTP thẳng — chính vì thế nó cần lưới ở tầng HTTP.

    Chỉ soi PHÉP DỊCH LỖI: `sua()` bị thay bằng hàm ném sẵn, nên test không phụ thuộc vào việc dựng
    cả một yêu cầu kho có phiếu (bộ này cố ý không dùng fixture `db` — xem docstring đầu file).
    """
    from app.main import app
    from app.routers import san_xuat as R
    from app.services.stock_request_service import StockRequestError

    loi = "Yêu cầu đã được kho lập phiếu, không sửa được nữa."

    def _chan(*_a, **_k):
        raise StockRequestError(loi)

    monkeypatch.setattr(R.vat_tu_de_nghi, "sua", _chan)
    cong = _cong_quyen(_PUT_PATH, "PUT")
    app.dependency_overrides[cong] = lambda: object()
    try:
        resp = client.put(
            "/api/san-xuat/work-items/1/material-requests/1",
            json={"can_luc": _T0, "lines": []},
        )
    finally:
        app.dependency_overrides.pop(cong, None)

    assert resp.status_code == 400, resp.text
    # Câu chữ phải đi tới người dùng, không bị nuốt thành "Internal Server Error".
    assert resp.json()["detail"] == loi
