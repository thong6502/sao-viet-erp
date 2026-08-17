"""HTTP contract Bài ghép 2: đủ route như màn cũ nhưng có khóa quyền riêng."""
from __future__ import annotations

from app.db import SessionLocal
from app.main import app
from app.models.module import Module
from app.models.role import RolePermission
from app.models.user import User
from app.repositories.rbac_repo import RoleRepository
from app.routers.ke_hoach_vat_tu import get_service as get_material_service


def _route_contract(prefix: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path == prefix or path.startswith(prefix + "/"):
            suffix = path[len(prefix):]
            for method in getattr(route, "methods", set()):
                if method not in {"HEAD", "OPTIONS"}:
                    out.add((suffix, method))
    return out


def _headers(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_api_bg2_co_du_endpoint_tuong_duong_bai_ghep_cu():
    legacy = _route_contract("/api/bai-ghep")
    bg2 = _route_contract("/api/bai-ghep-2")
    assert legacy <= bg2
    assert ("/{bai_ghep_id}/vat-tu-hieu-luc", "GET") in bg2
    assert ("/nguoi-phu-trach-options", "GET") in bg2


def test_module_bg2_scopeless_khong_cap_quyen_mac_dinh_va_router_guard_dung_khoa(client):
    headers = _headers(client)
    db = SessionLocal()
    try:
        assert db.query(Module).filter(Module.key == "bai_ghep_2").one().label == "Bài ghép 2"
        assert db.query(RolePermission).filter(RolePermission.module_key == "bai_ghep_2").count() == 0

        denied = client.get("/api/bai-ghep-2/hang-cho", headers=headers)
        assert denied.status_code == 403

        admin = db.query(User).filter(User.username == "admin").one()
        RoleRepository(db).set_permission(
            role_id=admin.role_id,
            module_key="bai_ghep_2",
            can_read=True,
            scope="all",
        )
        allowed = client.get("/api/bai-ghep-2/hang-cho", headers=headers)
        assert allowed.status_code == 200
        assert allowed.json() == {"items": [], "total": 0, "so_giu_cho": 0}
        assert client.post("/api/bai-ghep-2", json={"lsx_ids": []}, headers=headers).status_code == 403
        assert client.put("/api/bai-ghep-2/999999", json={"ten": "x"}, headers=headers).status_code == 403

        RoleRepository(db).set_permission(
            role_id=admin.role_id,
            module_key="bai_ghep_2",
            can_read=True,
            can_update=True,
            can_delete=False,
            scope="all",
        )
        assert client.delete("/api/bai-ghep-2/999999", headers=headers).status_code == 403

        RoleRepository(db).set_permission(
            role_id=admin.role_id,
            module_key="bai_ghep_2",
            can_read=True,
            can_create=True,
            can_update=True,
            can_delete=True,
            scope="all",
        )
        assert client.post("/api/bai-ghep-2", json={"lsx_ids": []}, headers=headers).status_code == 400
        assert client.put("/api/bai-ghep-2/999999", json={"ten": "x"}, headers=headers).status_code == 404
        assert client.delete("/api/bai-ghep-2/999999", headers=headers).status_code == 404
    finally:
        db.close()


def test_endpoint_vat_tu_hieu_luc_tra_contract_typed(client):
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        RoleRepository(db).set_permission(
            role_id=admin.role_id,
            module_key="bai_ghep_2",
            can_read=True,
            scope="all",
        )
    finally:
        db.close()

    class _VatTuGia:
        def vat_tu_hieu_luc(self, bai_ghep_id: int) -> dict:
            return {
                "bai_ghep_id": bai_ghep_id,
                "items": [{
                    "loai_nhom": "vat_tu",
                    "hang_loai": "vat_tu",
                    "hang_id": 7,
                    "hang_ma": "VT-07",
                    "hang_ten": "Mực đen",
                    "don_vi_goc": "kg",
                    "tong_can": 12,
                    "ton": 999,  # schema endpoint cố ý không phơi tồn kho ở tab bài
                    "dong": [{
                        "pham_vi": "bai_ghep",
                        "lsx_id": None,
                        "bai_ghep_id": bai_ghep_id,
                        "buoc_id": 4,
                        "gang_step_key": "gang-4",
                        "ma": "GB-001",
                        "ten_viec": "In chung",
                        "nhu_cau": 12,
                        "nhu_cau_hien_thi": "12 kg",
                    }],
                }],
                "bo_qua": [{"ma": "GB-001", "ly_do": "Chưa chọn giấy chung."}],
            }

    app.dependency_overrides[get_material_service] = lambda: _VatTuGia()
    try:
        response = client.get("/api/bai-ghep-2/123/vat-tu-hieu-luc", headers=_headers(client))
    finally:
        app.dependency_overrides.pop(get_material_service, None)

    assert response.status_code == 200
    assert response.json() == {
        "bai_ghep_id": 123,
        "items": [{
            "loai_nhom": "vat_tu", "hang_loai": "vat_tu", "hang_id": 7,
            "hang_ma": "VT-07", "hang_ten": "Mực đen", "don_vi_goc": "kg",
            "tong_can": 12.0,
            "dong": [{
                "pham_vi": "bai_ghep", "lsx_id": None, "bai_ghep_id": 123,
                "buoc_id": 4, "gang_step_key": "gang-4",
                "ma": "GB-001", "ten_viec": "In chung",
                "nhu_cau": 12.0, "nhu_cau_hien_thi": "12 kg",
            }],
        }],
        "bo_qua": [{"ma": "GB-001", "ly_do": "Chưa chọn giấy chung."}],
    }


def test_endpoint_nguoi_phu_trach_chi_tra_user_active_co_quyen_update(client):
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        RoleRepository(db).set_permission(
            role_id=admin.role_id,
            module_key="bai_ghep_2",
            can_read=True,
            can_update=True,
            scope="all",
        )
        admin_id, admin_name = admin.id, admin.name
    finally:
        db.close()

    response = client.get("/api/bai-ghep-2/nguoi-phu-trach-options", headers=_headers(client))

    assert response.status_code == 200
    assert response.json() == {"items": [{"id": admin_id, "ten": admin_name}]}
