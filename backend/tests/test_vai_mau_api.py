"""Bảng VAI MẪU (đợt 6, 11/08/2026) — dựng sẵn bộ quyền cho các vai điển hình.

Vai mẫu là DỮ LIỆU viết tay: gõ sai một khoá module hay một tên cờ thì không có gì báo, mãi tới
lúc quản trị bấm "Áp dụng mẫu" mới thấy quyền thiếu — mà lúc đó không ai biết là thiếu, vì bảng
quyền trông vẫn đầy đủ. Nên phần lớn file này là GUARD đối chiếu mẫu với model thật.
"""

from __future__ import annotations

from app.db import SessionLocal
from app.models.role import RolePermission
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services.role_templates import TEMPLATES

COT_QUYEN = {c.name for c in RolePermission.__table__.columns}


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin(client) -> str:
    return client.post("/api/auth/login",
                       json={"username": "admin", "password": "admin123"}).json()["access_token"]


# ══════════════════════════════════════════════ Guard: mẫu phải khớp model thật


def test_moi_ten_co_trong_vai_mau_deu_la_cot_that(client):
    """Gõ sai tên cờ (vd `can_aprove`) thì mẫu im lặng bỏ qua — vai được cấp THIẾU quyền mà nhìn
    bảng vẫn thấy đủ. Guard này bắt ngay lúc chạy test."""
    sai = []
    for mau in TEMPLATES:
        for khoa, cai_dat in mau["quyen"].items():
            for ten_co in cai_dat:
                if ten_co == "scope":
                    continue
                if ten_co not in COT_QUYEN:
                    sai.append(f'{mau["key"]} · {khoa} · {ten_co}')
    assert not sai, "tên cờ không có trong bảng role_permissions:\n  " + "\n  ".join(sai)


def test_moi_khoa_module_trong_vai_mau_deu_ton_tai(client):
    """Khoá module gõ sai ⇒ dòng đó rơi mất khi dựng ma trận, vai thiếu nguyên một màn."""
    from app.seed import ALL_MODULE_KEYS
    sai = [f'{m["key"]} · {k}' for m in TEMPLATES for k in m["quyen"] if k not in ALL_MODULE_KEYS]
    assert not sai, "khoá module không có trong danh mục:\n  " + "\n  ".join(sai)


def test_pham_vi_trong_vai_mau_deu_hop_le(client):
    hop_le = {"own", "department", "all"}
    sai = [
        f'{m["key"]} · {k} · {v.get("scope")}'
        for m in TEMPLATES for k, v in m["quyen"].items()
        if v.get("scope", "own") not in hop_le
    ]
    assert not sai, "phạm vi không hợp lệ:\n  " + "\n  ".join(sai)


def test_moi_mau_deu_giu_hai_o_mac_dinh(client):
    """Áp mẫu KHÔNG được gỡ Tự phục vụ / Nội quy.

    ⚠️ ĐÃ VỠ THẬT 11/08/2026, tìm ra khi soi giao diện chứ không phải từ test: ma trận mẫu là bản
    ĐẦY ĐỦ và giao diện thay sạch, nên khoá nào mẫu không khai sẽ về TẮT. Áp mẫu "Công nhân" cho
    một vai thợ ⇒ thợ hết tự chấm công được và không đọc nổi nội quy — đúng loại hồi quy mà cả đợt
    phân quyền này sinh ra để chặn.

    Hai ô đó nay được ép BẬT ở `role_service.role_templates()` chứ không bắt từng mẫu tự khai —
    thêm mẫu thứ sáu là quên ngay."""
    mau = client.get("/api/roles/templates", headers=_h(_admin(client))).json()
    for m in mau:
        for khoa in ("self_service", "noi_quy"):
            dong = next((d for d in m["permissions"] if d["module_key"] == khoa), None)
            assert dong is not None, f'{m["key"]}: thiếu hẳn dòng {khoa}'
            assert dong["can_read"], f'{m["key"]}: áp mẫu sẽ GỠ ô {khoa}'


def test_endpoint_tra_ma_tran_day_du_cho_tung_mau(client):
    r = client.get("/api/roles/templates", headers=_h(_admin(client)))
    assert r.status_code == 200, r.text
    mau = r.json()
    assert [m["key"] for m in mau] == [m["key"] for m in TEMPLATES]

    so_module = len(client.get("/api/rbac/modules", headers=_h(_admin(client))).json())
    for m in mau:
        assert m["label"] and m["mo_ta"], f'{m["key"]}: thiếu nhãn / mô tả'
        # Ma trận ĐẦY ĐỦ: áp mẫu là thay sạch, không để sót quyền cũ của vai.
        assert len(m["permissions"]) == so_module, (
            f'{m["key"]}: {len(m["permissions"])} dòng, cần đủ {so_module} module'
        )


def test_mau_cong_nhan_khong_he_cham_vao_du_lieu_nguoi_khac(client):
    """Mẫu thấp nhất phải THẬT SỰ thấp — đây là mẫu sẽ được dùng cho phần lớn người trong nhà máy."""
    mau = client.get("/api/roles/templates", headers=_h(_admin(client))).json()
    cn = next(m for m in mau if m["key"] == "cong_nhan")
    for dong in cn["permissions"]:
        if dong["can_read"]:
            assert dong["scope"] == "own", (
                f'mẫu Công nhân xem {dong["module_key"]} với phạm vi {dong["scope"]}'
            )
        for co in ("can_delete", "can_approve", "can_lock", "can_adjust",
                   "can_manage_status", "can_view_salary", "can_edit_salary"):
            assert not dong.get(co), f'mẫu Công nhân có {co} trên {dong["module_key"]}'


def test_mau_hcns_khong_co_o_danh_dau_da_chi_luong(client):
    """Tách vai của đợt 4: HCNS chốt SỐ, kế toán mới xác nhận TIỀN ĐÃ RA. Mẫu phải dạy đúng điều đó,
    nếu không thì gộp lại y như trước khi tách."""
    mau = client.get("/api/roles/templates", headers=_h(_admin(client))).json()
    hcns = next(m for m in mau if m["key"] == "hcns")
    luong = next(d for d in hcns["permissions"] if d["module_key"] == "luong")
    assert luong["can_lock"], "HCNS phải chốt được bảng lương"
    assert not luong["can_manage_status"], "HCNS KHÔNG được có ô Đánh dấu đã chi lương"

    ke_toan = next(m for m in mau if m["key"] == "ke_toan")
    kt_luong = next(d for d in ke_toan["permissions"] if d["module_key"] == "luong")
    assert kt_luong["can_manage_status"], "Kế toán phải có ô Đánh dấu đã chi"
    assert not kt_luong["can_lock"], "Kế toán KHÔNG chốt bảng lương"


def test_mau_thu_mua_khong_tu_duyet_phieu_cua_minh(client):
    """Chốt 04/08/2026: ai đề xuất chi tiền thì không được là người đồng ý chi."""
    mau = client.get("/api/roles/templates", headers=_h(_admin(client))).json()
    tm = next(m for m in mau if m["key"] == "thu_mua")
    pm = next(d for d in tm["permissions"] if d["module_key"] == "thu_mua")
    assert pm["can_create"] and not pm["can_approve"]

    kt = next(m for m in mau if m["key"] == "ke_toan")
    don = next(d for d in kt["permissions"] if d["module_key"] == "ke_toan")
    assert don["can_read"] and not don["can_approve"], "kế toán xem đơn mua, KHÔNG duyệt"


def test_ap_mau_roi_luu_thi_quyen_vao_dung(client):
    """Đường đi thật: lấy mẫu → lưu qua endpoint cũ → đọc lại thấy đúng."""
    admin = _admin(client)
    kd = next(d for d in client.get("/api/departments", headers=_h(admin)).json()
              if d["name"] == "Kinh doanh")
    vai = client.post("/api/roles", json={"name": "Vai thu mau", "department_id": kd["id"]},
                      headers=_h(admin)).json()["id"]

    mau = client.get("/api/roles/templates", headers=_h(admin)).json()
    to_truong = next(m for m in mau if m["key"] == "to_truong")

    luu = client.put(f"/api/roles/{vai}/permissions",
                     json={"permissions": to_truong["permissions"]}, headers=_h(admin))
    assert luu.status_code == 200, luu.text

    doc = client.get(f"/api/roles/{vai}/permissions", headers=_h(admin)).json()
    cc = next(d for d in doc if d["module_key"] == "cham_cong")
    assert cc["can_read"] and cc["can_view_log"] and cc["scope"] == "department"
    assert not cc["can_lock"] and not cc["can_adjust"], "tổ trưởng KHÔNG chấm bù / chốt kỳ"


def test_khong_co_quyen_vai_tro_thi_khong_xem_duoc_mau(client):
    """Bộ quyền dựng sẵn cũng là thông tin phân quyền — không phơi cho mọi tài khoản."""
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles, users = RoleRepository(db), UserRepository(db)
        vai = roles.create(name="Khong quyen vai tro", department_id=dept.id)
        u = users.create(username="probe-vai-mau", name="probe", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=vai.id, is_active=True)
        db.commit()
        tok = create_access_token(str(u.id))
    finally:
        db.close()
    assert client.get("/api/roles/templates", headers=_h(tok)).status_code == 403
