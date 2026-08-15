"""Ba mặt API ĐỜI CŨ chỉ-đọc — `machines` · `operations` · `product-types-catalog`.

Từ 15/08/2026 chúng có Ô QUYỀN RIÊNG (`legacy_readonly`) thay vì đi ké ô quyền của ba màn danh
mục đời mới. Ô này CỐ Ý không nằm trong `seed.MODULES` ⇒ không vai nào có ⇒ mặc định 403 cho tất
cả, kể cả admin. Lý do + số đo: `app/legacy_api.py`.

Hai mặt phải khoá lại, thiếu mặt nào cũng thành đèn xanh giả:
  * mặc định CHẶN — nếu ai lỡ thêm khoá vào `MODULES` thì test này đỏ ngay;
  * cấp quyền vào thì vẫn ĐỌC ĐƯỢC — chứng minh đây là "ngừng dùng", không phải "đã gỡ", và
    đảo lại đúng một dòng.

Dữ liệu test nạp thẳng qua model chứ không qua HTTP: mặt ghi của các router này đã bị gỡ từ trước.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import SessionLocal
from app.legacy_api import LEGACY_READONLY
from app.models.operation import Operation, OperationRate
from app.repositories.rbac_repo import RoleRepository
from app.repositories.user_repo import UserRepository


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _cap_quyen_legacy() -> None:
    """Cấp `legacy_readonly:read` cho chính vai của admin — mô phỏng ĐÚNG cách đảo lại thật
    (thêm khoá vào `seed.MODULES` rồi vai Giám đốc nhận `_full` ở lần seed kế tiếp)."""
    db = SessionLocal()
    try:
        admin = UserRepository(db).get_by_username("admin")
        assert admin is not None and admin.role_id is not None
        RoleRepository(db).set_permission(
            role_id=admin.role_id, module_key=LEGACY_READONLY, can_read=True, scope="all",
        )
        db.commit()
    finally:
        db.close()


def _seed_operation() -> int:
    """Chèn 1 công đoạn + biểu giá hiện hành thẳng qua model.

    `SessionLocal` dùng chung đúng connection StaticPool với app, nên hàng vừa commit là các
    endpoint đang test nhìn thấy được.
    """
    db = SessionLocal()
    try:
        op = Operation(
            code="CD900",
            name="Cán màng nhung",
            operation_type="can_mang",
            unit="m2",
            allow_outsource=True,
            is_active=True,
        )
        db.add(op)
        db.flush()
        db.add(
            OperationRate(
                operation_id=op.id,
                setup_fee=150000,
                run_rate=3500,
                labor_rate=500,
                min_charge=300000,
                speed=2000.0,
                effective_from=date.today(),
            )
        )
        db.commit()
        return op.id
    finally:
        db.close()


def test_ba_mat_legacy_mac_dinh_chan_ca_admin(client, auth_headers):
    """Không vai nào có `legacy_readonly` ⇒ 403 hết, kể cả Giám đốc.

    Đây là cái CHỐT của đợt B9: trước đó tick MỘT ô quyền cho màn Công đoạn là mở luôn một mặt
    API thứ hai đọc bảng khác, người cấp quyền không hề biết.
    """
    for duong in ("/api/machines", "/api/operations", "/api/product-types-catalog"):
        r = client.get(duong, headers=auth_headers)
        assert r.status_code == 403, f"{duong} phải 403 khi chưa cấp {LEGACY_READONLY}, gặp {r.status_code}"


def test_cap_quyen_legacy_thi_doc_lai_duoc(client, auth_headers):
    """Cấp ô quyền vào là đọc được ngay — chứng minh "ngừng dùng" chứ không phải "đã gỡ"."""
    op_id = _seed_operation()
    _cap_quyen_legacy()

    resp = client.get("/api/operations", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(x["id"] == op_id for x in body["items"])

    resp = client.get(f"/api/operations/{op_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Cán màng nhung"


def test_o_quyen_legacy_khong_duoc_seed(client):
    """`legacy_readonly` KHÔNG được nằm trong danh sách module seed.

    Vai Giám đốc nhận `_full(SCOPE_ALL)` cho MỌI khoá trong `seed.MODULES`, nên thêm khoá này vào
    đó là tự tay cấp lại đúng thứ vừa gỡ — mà lại im lặng. Test đỏ ở đây nghĩa là ai đó vừa làm
    thế; đọc `app/legacy_api.py` trước khi quyết định nới.
    """
    from app.seed import MODULES

    assert LEGACY_READONLY not in {k for k, *_ in MODULES}


def test_operations_write_endpoints_removed(client, auth_headers):
    """Mặt GHI đã gỡ từ trước — kiểm cả khi ĐÃ có quyền, để 405/404 là do route chứ không do 403."""
    op_id = _seed_operation()
    _cap_quyen_legacy()

    payload = {"name": "X", "operation_type": "can_mang", "unit": "m2"}

    assert client.post(
        "/api/operations", json=payload, headers=auth_headers
    ).status_code in (404, 405)
    assert client.put(
        f"/api/operations/{op_id}", json=payload, headers=auth_headers
    ).status_code in (404, 405)
    assert client.delete(
        f"/api/operations/{op_id}", headers=auth_headers
    ).status_code in (404, 405)
    assert client.post(
        f"/api/operations/{op_id}/rates", json={}, headers=auth_headers
    ).status_code in (404, 405)
    assert client.post(
        f"/api/operations/{op_id}/preview", json={}, headers=auth_headers
    ).status_code in (404, 405)
