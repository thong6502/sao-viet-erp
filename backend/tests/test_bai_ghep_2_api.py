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


#: Hợp đồng HTTP của màn Bài ghép — chép tay để đổi/gỡ route là test đỏ, không im lặng.
#: Màn cũ `/api/bai-ghep` gỡ 18/08/2026; danh sách này chính là phần màn cũ có, cộng
#: `vat-tu-hieu-luc` + `nguoi-phu-trach-options` của bản mới.
CONTRACT_BG2 = {
    ("/hang-cho", "GET"), ("", "GET"), ("/nguoi-phu-trach-options", "GET"),
    ("/{bai_ghep_id}", "GET"), ("/{bai_ghep_id}/so-do", "GET"),
    ("/{bai_ghep_id}/vat-tu-hieu-luc", "GET"),
    ("", "POST"), ("/{bai_ghep_id}", "PUT"), ("/{bai_ghep_id}", "DELETE"),
    ("/{bai_ghep_id}/thanh-vien", "POST"),
    ("/{bai_ghep_id}/thanh-vien/{thanh_vien_id}", "PUT"),
    ("/{bai_ghep_id}/thanh-vien/{thanh_vien_id}", "DELETE"),
    ("/{bai_ghep_id}/gop", "POST"),
    ("/{bai_ghep_id}/gop/{gang_step_key}", "PUT"),
    ("/{bai_ghep_id}/gop/{gang_step_key}", "DELETE"),
    ("/{bai_ghep_id}/ung-vien-gop", "POST"), ("/{bai_ghep_id}/trang-thai", "POST"),
    ("/{bai_ghep_id}/activity", "GET"),
}


def test_api_bg2_giu_du_hop_dong_va_man_cu_da_go_han():
    """Màn này là màn Bài ghép DUY NHẤT từ 18/08/2026 — không còn `/api/bai-ghep` để rơi về."""
    assert _route_contract("/api/bai-ghep-2") == CONTRACT_BG2
    con_sot = {
        p for p in (getattr(r, "path", "") for r in app.routes)
        if p == "/api/bai-ghep" or p.startswith("/api/bai-ghep/")
    }
    assert not con_sot, f"router màn cũ còn mount: {sorted(con_sot)}"


def test_module_bg2_scopeless_ke_thua_quyen_man_cu_va_router_guard_dung_khoa(client):
    headers = _headers(client)
    db = SessionLocal()
    try:
        # Nhãn bỏ hậu tố "2" (mg `0216`); khoá giữ `bai_ghep_2` vì quyền trong DB thật neo theo khoá.
        assert db.query(Module).filter(Module.key == "bai_ghep_2").one().label == "Bài ghép"
        assert db.query(Module).filter(Module.key == "bai_ghep").count() == 0
        assert db.query(RolePermission).filter(RolePermission.module_key == "bai_ghep").count() == 0
        # Vai nào từng có màn cũ thì nay có màn này — seed cấp cho chủ chốt, mg `0216` chép cho DB đang chạy.
        assert db.query(RolePermission).filter(RolePermission.module_key == "bai_ghep_2").count() > 0

        admin = db.query(User).filter(User.username == "admin").one()
        RoleRepository(db).set_permission(
            role_id=admin.role_id,
            module_key="bai_ghep_2",
            can_read=False,
            scope="all",
        )
        denied = client.get("/api/bai-ghep-2/hang-cho", headers=headers)
        assert denied.status_code == 403

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
