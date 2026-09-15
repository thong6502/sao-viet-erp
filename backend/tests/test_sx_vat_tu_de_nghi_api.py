"""Đề nghị cấp vật tư công đoạn — đường dây HTTP `/api/san-xuat/work-items/{id}/material-requests`
(spec-de-nghi-cap-vat-tu-cong-doan §6, Task 6).

Soi tầng router + gác quyền, KHÔNG dựng lại cả luồng nghiệp vụ (khuôn `test_san_xuat_dong_nhom_api`
— luật đã có test SERVICE riêng ở `test_sx_vat_tu_de_nghi.py`, khớp response dict đã kiểm ở đó):
  · chưa đăng nhập → 401;
  · cổng router là `require_quyen_to("warehouse")` (mg 0302): người KHÔNG có quyền Kho ở tổ nào
    → 403 — kể cả khi có Xem + đủ ba quyền chi tiết còn lại ở một tổ. Admin seed (Giám đốc) không
    có dòng `to_sx_*` nào nên test tự cấp bằng `cap_quyen_to`, commit trên `SessionLocal` riêng.

CHỦ Ý KHÔNG dùng fixture `db` ở đây: `conftest.client` và `db` (từ `test_lsx_service.py`) đều
`drop_all`+`create_all` trên CÙNG một engine SQLite in-memory (StaticPool một connection) — nhận cả
hai trong một test là cái dựng sau xoá sạch cái dựng trước (task-6-ruling-route.md, ruling 20).

Các luật nghiệp vụ mà đường HTTP này lẽ ra chứng minh được đã có test SERVICE gọi thẳng
`vat_tu_de_nghi.tao()`/`.sua()` rồi, KHÔNG lặp lại ở đây:
  · "đúng quyền Kho ở tổ của công đoạn mới ghi được" —
    `test_sx_vat_tu_de_nghi.py::test_khong_co_quyen_kho_o_to_thi_chan`.
  · "không cần `kho:request`" — `test_sx_vat_tu_de_nghi.py::test_khong_can_quyen_kho_de_tao_de_nghi`.
  · "`sua()` để `StockRequestError` xuyên ra ngoài" —
    `test_sx_vat_tu_de_nghi.py::test_sua_qua_kho_huy_roi_nhap_so_duong_thi_chan_khong_ghi_nua_voi`.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.department import Department
from app.models.user import User
from tests.quyen_to_fixtures import cap_quyen_to

ADMIN = {"username": "admin", "password": "admin123"}
_T0 = "2026-08-31T08:00:00"
_BA_VIEC_TRU_KHO = ("run_order", "confirm_output", "qc")


def _admin_h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _cap_admin_o_to_moi(viec, *, ma: str) -> int:
    """Dựng một tổ khối sản xuất rồi bật Xem + `viec` trên dòng tổ cho vai của admin — y như quản
    trị tích ma trận. Commit trên phiên riêng để request HTTP thấy được."""
    db = SessionLocal()
    try:
        d = Department(name=f"Tổ Vật Tư API {ma}", code=ma, la_san_xuat=True)
        db.add(d)
        db.flush()
        cap_quyen_to(db, db.query(User).filter(User.username == "admin").one(), d, viec=viec)
        db.commit()
        return d.id
    finally:
        db.close()


def test_tao_de_nghi_can_dang_nhap(client):
    resp = client.post(
        "/api/san-xuat/work-items/1/material-requests",
        json={"can_luc": _T0, "lines": []},
    )
    assert resp.status_code == 401


def test_tao_de_nghi_khong_co_quyen_kho_o_to_nao_403(client):
    # Admin có Xem + Thực hiện lệnh + Xác nhận sản lượng + KCS ở một tổ, nhưng KHÔNG có Kho ở tổ
    # nào ⇒ cổng `require_quyen_to("warehouse")` chặn ngay tầng router (service không bị chạm tới).
    _cap_admin_o_to_moi(_BA_VIEC_TRU_KHO, ma="TO-VT-API-1")
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


def test_sua_de_nghi_khong_co_quyen_kho_o_to_nao_403(client):
    _cap_admin_o_to_moi(_BA_VIEC_TRU_KHO, ma="TO-VT-API-2")
    resp = client.put(
        "/api/san-xuat/work-items/1/material-requests/1",
        json={"can_luc": _T0, "lines": []},
        headers=_admin_h(client),
    )
    assert resp.status_code == 403


def test_sua_de_nghi_bi_kho_khoa_thi_400_doc_duoc_chu_khong_500(client, monkeypatch):
    """Kho đã lập phiếu ⇒ `sua()` để `StockRequestError` xuyên ra; router PHẢI dịch thành 400.

    Luật này đã có test SERVICE (`test_sx_vat_tu_de_nghi.py::
    test_sua_qua_kho_huy_roi_nhap_so_duong_thi_chan_khong_ghi_nua_voi`), nhưng KHÔNG có gì canh
    mệnh đề `except (VatTuDeNghiError, StockRequestError)` ở tầng router: gỡ nó ra thì test service
    vẫn xanh, còn người bấm nhận 500 trắng không đọc được. FE đã ẩn nút "Sửa đề nghị" ngay khi kho
    có phiếu nên đường này chỉ tới được bằng HTTP thẳng — chính vì thế nó cần lưới ở tầng HTTP.

    Chỉ soi PHÉP DỊCH LỖI: `sua()` bị thay bằng hàm ném sẵn, nên test không phụ thuộc vào việc dựng
    cả một yêu cầu kho có phiếu (bộ này cố ý không dùng fixture `db` — xem docstring đầu file).
    Cổng router đi đường THẬT: admin được cấp Kho ở một tổ nên `require_quyen_to("warehouse")` cho
    qua, không phải đè dependency.
    """
    from app.routers import san_xuat as R
    from app.services.stock_request_service import StockRequestError

    loi = "Yêu cầu đã được kho lập phiếu, không sửa được nữa."

    def _chan(*_a, **_k):
        raise StockRequestError(loi)

    monkeypatch.setattr(R.vat_tu_de_nghi, "sua", _chan)
    _cap_admin_o_to_moi(("warehouse",), ma="TO-VT-API-3")
    resp = client.put(
        "/api/san-xuat/work-items/1/material-requests/1",
        json={"can_luc": _T0, "lines": []},
        headers=_admin_h(client),
    )

    assert resp.status_code == 400, resp.text
    # Câu chữ phải đi tới người dùng, không bị nuốt thành "Internal Server Error".
    assert resp.json()["detail"] == loi
