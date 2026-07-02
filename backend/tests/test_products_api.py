"""feat-034..036 — Sản phẩm in (Product catalog) API (spec-07).

Covers: list + q/type filter + component counts (F1); create with the full validation
matrix — name required + unique, binding→≥1 component, tay-sách %4 only for bound body,
colors 0..8, khổ>0, mã tự sinh, audit, SEAM-03 paper picker unavailable (F2); edit
read-only code + duplicate + audit, delete cascades + audit, RBAC 403 (F3/F4).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _role_token(username: str, role_name: str, dept_name: str = "Kinh doanh") -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username(username)
        if existing is not None:
            return create_access_token(str(existing.id))
        dept = DepartmentRepository(db).get_by_name(dept_name)
        role = RoleRepository(db).get_by_name_and_department(role_name, dept.id)
        u = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _last_audit(action: str) -> str | None:
    db = SessionLocal()
    try:
        for row in AuditLogRepository(db).list_recent(200):
            if row.action == action:
                return row.detail
        return None
    finally:
        db.close()


def _book(name="Sách A", binding="saddle", body_pages=32):
    return {
        "name": name,
        "product_type": "sach",
        "binding_type": binding,
        "components": [
            {
                "component_type": "cover",
                "colors_front": 4,
                "colors_back": 0,
                "page_count": 4,
                "finished_w": 20.5,
                "finished_h": 29.0,
                "bleed": 3.0,
                "grain_direction": "short",
                "sequence": 0,
            },
            {
                "component_type": "body",
                "colors_front": 4,
                "colors_back": 4,
                "page_count": body_pages,
                "finished_w": 20.0,
                "finished_h": 28.5,
                "bleed": 3.0,
                "grain_direction": "long",
                "sequence": 1,
            },
        ],
    }


# --- RBAC ------------------------------------------------------------------


def test_list_requires_read_permission(client):
    db = SessionLocal()
    try:
        u = UserRepository(db).create(
            username="norole-sp", name="No Role", password_hash=hash_password("x")
        )
        token = create_access_token(str(u.id))
    finally:
        db.close()
    assert client.get("/api/products", headers=_h(token)).status_code == 403


def test_create_requires_create_permission(client):
    # Trưởng phòng HCNS has no san_pham permission → 403.
    token = _role_token("hcns-sp", "Trưởng phòng HCNS", dept_name="Hành chính nhân sự")
    resp = client.post(
        "/api/products", json={"name": "X", "product_type": "name_card"}, headers=_h(token)
    )
    assert resp.status_code == 403


# --- F1 list ---------------------------------------------------------------


def test_list_empty_then_filters(client):
    token = _admin_token(client)
    empty = client.get("/api/products", headers=_h(token)).json()
    assert empty["total"] == 0 and empty["items"] == []

    client.post("/api/products", json={"name": "Name card X", "product_type": "name_card"}, headers=_h(token))
    client.post("/api/products", json=_book(name="Sách List"), headers=_h(token))

    all_ = client.get("/api/products", headers=_h(token)).json()
    assert all_["total"] == 2
    # component_count reflected: name card 0, book 2.
    by_name = {r["name"]: r for r in all_["items"]}
    assert by_name["Name card X"]["component_count"] == 0
    assert by_name["Sách List"]["component_count"] == 2

    # Filter by type.
    books = client.get("/api/products?product_type=sach", headers=_h(token)).json()
    assert books["total"] == 1 and books["items"][0]["name"] == "Sách List"
    # q by name.
    q = client.get("/api/products?q=card", headers=_h(token)).json()
    assert q["total"] == 1 and q["items"][0]["name"] == "Name card X"


# --- F2 create -------------------------------------------------------------


def test_create_name_card_without_components_ok(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/products",
        json={"name": "Name card công ty", "product_type": "name_card"},
        headers=_h(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"].startswith("SP")
    assert body["components"] == []
    assert _last_audit("create_product") is not None


def test_bound_product_without_components_blocked(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/products",
        json={"name": "Sách rỗng", "product_type": "sach", "binding_type": "perfect"},
        headers=_h(token),
    )
    assert resp.status_code == 422
    assert "cấu phần" in resp.json()["detail"]


def test_create_full_book_persists_components(client):
    token = _admin_token(client)
    resp = client.post("/api/products", json=_book(name="Sách đầy đủ"), headers=_h(token))
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["components"]) == 2
    assert body["code"].startswith("SP")


def test_duplicate_name_blocked_409(client):
    token = _admin_token(client)
    client.post("/api/products", json={"name": "Trùng Tên", "product_type": "name_card"}, headers=_h(token))
    dup = client.post("/api/products", json={"name": "Trùng Tên", "product_type": "brochure"}, headers=_h(token))
    assert dup.status_code == 409
    # Case-insensitive.
    dup2 = client.post("/api/products", json={"name": "trùng tên", "product_type": "brochure"}, headers=_h(token))
    assert dup2.status_code == 409


def test_blank_name_422(client):
    token = _admin_token(client)
    resp = client.post("/api/products", json={"name": "   ", "product_type": "name_card"}, headers=_h(token))
    assert resp.status_code == 422


def test_bad_product_type_422(client):
    token = _admin_token(client)
    resp = client.post("/api/products", json={"name": "X", "product_type": "khong_ton_tai"}, headers=_h(token))
    assert resp.status_code == 422


def test_tay_sach_rule_body_of_bound_product(client):
    """page_count % 4 != 0 blocks ONLY body of a bound product."""
    token = _admin_token(client)
    # Body 30 pages (not %4) in a saddle book → blocked.
    resp = client.post("/api/products", json=_book(name="Sách lẻ", body_pages=30), headers=_h(token))
    assert resp.status_code == 422
    assert "chia hết cho 4" in resp.json()["detail"]


def test_tay_sach_rule_not_applied_to_cover(client):
    """A cover with an odd page_count is allowed (rule is body-only)."""
    token = _admin_token(client)
    payload = {
        "name": "Bìa lẻ OK",
        "product_type": "sach",
        "binding_type": "saddle",
        "components": [
            {"component_type": "cover", "colors_front": 4, "colors_back": 4,
             "page_count": 5, "finished_w": 20, "finished_h": 28, "bleed": 3, "sequence": 0},
            {"component_type": "body", "colors_front": 4, "colors_back": 4,
             "page_count": 16, "finished_w": 20, "finished_h": 28, "bleed": 3, "sequence": 1},
        ],
    }
    assert client.post("/api/products", json=payload, headers=_h(token)).status_code == 201


def test_tay_sach_rule_not_applied_to_loose_leaf(client):
    """A loose-leaf product (binding none) with an odd-page component is allowed."""
    token = _admin_token(client)
    payload = {
        "name": "Tờ rơi 1 cấu phần lẻ",
        "product_type": "to_roi",
        "binding_type": None,
        "components": [
            {"component_type": "body", "colors_front": 4, "colors_back": 4,
             "page_count": 2, "finished_w": 14.8, "finished_h": 21, "bleed": 3, "sequence": 0},
        ],
    }
    assert client.post("/api/products", json=payload, headers=_h(token)).status_code == 201


def test_colors_out_of_range_422(client):
    token = _admin_token(client)
    payload = {
        "name": "Màu quá 8",
        "product_type": "sach",
        "binding_type": "saddle",
        "components": [
            {"component_type": "body", "colors_front": 9, "colors_back": 0,
             "page_count": 8, "finished_w": 20, "finished_h": 28, "bleed": 3, "sequence": 0},
        ],
    }
    # 9 > 8 caught by pydantic (422) — either way must be 422.
    assert client.post("/api/products", json=payload, headers=_h(token)).status_code == 422


def test_nonpositive_dimensions_422(client):
    token = _admin_token(client)
    payload = {
        "name": "Khổ 0",
        "product_type": "sach",
        "binding_type": "saddle",
        "components": [
            {"component_type": "body", "colors_front": 4, "colors_back": 4,
             "page_count": 8, "finished_w": 0, "finished_h": 28, "bleed": 3, "sequence": 0},
        ],
    }
    assert client.post("/api/products", json=payload, headers=_h(token)).status_code == 422


def test_nonpositive_page_count_422(client):
    token = _admin_token(client)
    payload = {
        "name": "Trang 0",
        "product_type": "sach",
        "binding_type": "saddle",
        "components": [
            {"component_type": "body", "colors_front": 4, "colors_back": 4,
             "page_count": 0, "finished_w": 20, "finished_h": 28, "bleed": 3, "sequence": 0},
        ],
    }
    assert client.post("/api/products", json=payload, headers=_h(token)).status_code == 422


# --- SEAM-03 paper picker --------------------------------------------------


def test_paper_picker_available_and_returns_seeded_list(client):
    """SEAM-03 built → picker available=True and returns the seeded paper list."""
    token = _admin_token(client)
    resp = client.get("/api/products/papers", headers=_h(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert len(body["items"]) >= 1
    assert any("Couche" in item["display_name"] for item in body["items"])


def test_enums_endpoint(client):
    token = _admin_token(client)
    body = client.get("/api/products/enums", headers=_h(token)).json()
    types = {o["value"] for o in body["product_types"]}
    assert {"name_card", "sach", "hop", "to_roi"} <= types
    bindings = {o["value"] for o in body["binding_types"]}
    assert {"none", "perfect", "saddle", "sewn"} <= bindings


# --- F3 edit ---------------------------------------------------------------


def test_update_readonly_code_and_audit(client):
    token = _admin_token(client)
    created = client.post("/api/products", json=_book(name="Sửa SP"), headers=_h(token)).json()
    pid, code = created["id"], created["code"]

    upd = client.put(
        f"/api/products/{pid}",
        json=_book(name="Sửa SP đổi", body_pages=16),
        headers=_h(token),
    )
    assert upd.status_code == 200
    body = upd.json()
    assert body["code"] == code  # read-only
    assert body["name"] == "Sửa SP đổi"
    assert body["components"][1]["page_count"] == 16
    assert _last_audit("update_product") is not None


def test_update_duplicate_name_blocked(client):
    token = _admin_token(client)
    client.post("/api/products", json={"name": "Existing SP", "product_type": "name_card"}, headers=_h(token))
    other = client.post("/api/products", json={"name": "Other SP", "product_type": "name_card"}, headers=_h(token)).json()
    resp = client.put(
        f"/api/products/{other['id']}",
        json={"name": "Existing SP", "product_type": "name_card"},
        headers=_h(token),
    )
    assert resp.status_code == 409


def test_update_same_name_allowed(client):
    token = _admin_token(client)
    created = client.post("/api/products", json={"name": "Same SP", "product_type": "name_card"}, headers=_h(token)).json()
    resp = client.put(
        f"/api/products/{created['id']}",
        json={"name": "Same SP", "product_type": "brochure"},
        headers=_h(token),
    )
    assert resp.status_code == 200
    assert resp.json()["product_type"] == "brochure"


# --- F4 delete -------------------------------------------------------------


def test_delete_removes_product_and_components_and_audits(client):
    token = _admin_token(client)
    created = client.post("/api/products", json=_book(name="Xoá SP"), headers=_h(token)).json()
    pid = created["id"]
    resp = client.delete(f"/api/products/{pid}", headers=_h(token))
    assert resp.status_code == 204
    assert client.get(f"/api/products/{pid}", headers=_h(token)).status_code == 404
    assert _last_audit("delete_product") is not None


def test_delete_requires_delete_permission(client):
    """NV Sales lacks san_pham entirely → 403 (only admin/TP KD have it in seed)."""
    admin = _admin_token(client)
    created = client.post("/api/products", json={"name": "Bảo vệ xoá", "product_type": "name_card"}, headers=_h(admin)).json()
    sale = _role_token("sale-del", "NV Sales")
    resp = client.delete(f"/api/products/{created['id']}", headers=_h(sale))
    assert resp.status_code == 403
