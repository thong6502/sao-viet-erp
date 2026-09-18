"""Bàn Thực hiện sản xuất — API `/api/san-xuat/*` (gác quyền + hình dạng ra).

Soi tầng router + schema + cổng `require_quyen_to` (mg 0302 — có quyền ở ít nhất một dòng tổ mới
qua, đúng tổ nào do service hỏi): chưa đăng nhập → 401; admin được cấp dòng của tổ → 200 và tổ vừa
tạo hiện trong danh sách (badge 0 khi chưa phát hành); timeline tổ hợp lệ → 200 rỗng; tổ không
thuộc khối SX → 403. Không dựng cả luồng phát hành ở đây (đã có ở test service backbone) —
chỉ cần một tổ-lá để chứng minh đường dây HTTP.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.department import Department
from app.models.user import User
from tests.quyen_to_fixtures import cap_quyen_to

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _to_la_sx(ten="Tổ In API", ma="TO-API") -> int:
    db = SessionLocal()
    try:
        d = Department(name=ten, code=ma, la_san_xuat=True)
        db.add(d)
        db.flush()
        # Quyền Bàn tổ nằm ở dòng `to_sx_<id>` của vai — bật cho admin như quản trị tích ma trận.
        cap_quyen_to(db, db.query(User).filter(User.username == "admin").one(), d)
        db.commit()
        return d.id
    finally:
        db.close()


def test_teams_can_dang_nhap(client):
    assert client.get("/api/san-xuat/teams").status_code == 401


def test_teams_admin_thay_to_moi(client):
    to_id = _to_la_sx()
    resp = client.get("/api/san-xuat/teams", headers=_admin_h(client))
    assert resp.status_code == 200
    teams = resp.json()["teams"]
    row = next((t for t in teams if t["id"] == to_id), None)
    assert row is not None
    assert set(row) == {
        "id", "ten", "ma", "cap", "la_kcs", "la_tho", "so_viec_cho", "quyen", "so_cho_xac_nhan",
    }
    assert row["ten"] == "Tổ In API" and row["so_viec_cho"] == 0
    assert row["cap"] == 0  # tổ không có phòng cha → gốc cây
    # Admin được bật Xem + 3 quyền chi tiết phạm vi Tất cả → mức `all`, không phải thợ.
    assert row["quyen"] == {
        "read": "all", "run_order": "all", "confirm_output": "all", "warehouse": "all",
    }
    assert row["la_tho"] is False


def test_work_items_to_hop_le_rong(client):
    to_id = _to_la_sx()
    resp = client.get(
        "/api/san-xuat/work-items", params={"team_id": to_id}, headers=_admin_h(client)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == to_id and body["cong_viec"] == []


def test_work_items_ngoai_pham_vi_403(client):
    resp = client.get(
        "/api/san-xuat/work-items", params={"team_id": 999_999}, headers=_admin_h(client)
    )
    assert resp.status_code == 403


def test_work_items_bo_tham_so_mode(client):
    """KCS theo lệnh (mg 0306): bàn tổ không còn chế độ "kcs" — tham số `mode` lạ bị bỏ qua, không
    lọc gì."""
    to_id = _to_la_sx()
    resp = client.get(
        "/api/san-xuat/work-items",
        params={"team_id": to_id, "mode": "kcs", "nhom": "phang"},
        headers=_admin_h(client),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == to_id and body["cong_viec"] == []


# --- Bàn tổ trục LỆNH (spec 2026-09-11) ------------------------------------------------------
def test_work_items_mac_dinh_tra_nhom_lenh(client):
    """Hình dạng mới: mặc định gom theo LỆNH và kèm vị trí trang. Tổ rỗng vẫn phải nói rõ
    `nhom` + `trang`, nếu không FE không biết đang ở chế độ nào để vẽ."""
    to_id = _to_la_sx(ten="Tổ Lệnh API", ma="TO-LENH-API")
    r = client.get(
        "/api/san-xuat/work-items",
        params={"team_id": to_id, "co_trang": 2},
        headers=_admin_h(client),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["nhom"] == "lenh"
    assert d["trang"] == {"trang": 1, "co_trang": 2, "tong": 0}
    assert d["lenh"] == []


def test_work_items_che_do_phang_giu_hinh_cu_cho_gantt(client):
    to_id = _to_la_sx(ten="Tổ Phẳng API", ma="TO-PHANG-API")
    r = client.get(
        "/api/san-xuat/work-items",
        params={"team_id": to_id, "nhom": "phang",
                "tu_ngay": "2026-09-01", "den_ngay": "2026-09-30"},
        headers=_admin_h(client),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["nhom"] == "phang"
    assert isinstance(d["cong_viec"], list)
    assert d["lenh"] == [] and d["trang"] is None


def test_work_items_co_trang_bi_kep_tran_100(client):
    """Trần phải do schema chặn, không để service tự bóp im lặng: client gửi 9999 phải biết mình
    gửi sai, chứ không nhận về 100 dòng rồi tưởng đã lấy hết."""
    to_id = _to_la_sx(ten="Tổ Trần API", ma="TO-TRAN-API")
    r = client.get(
        "/api/san-xuat/work-items",
        params={"team_id": to_id, "co_trang": 9999},
        headers=_admin_h(client),
    )
    assert r.status_code == 422


def test_work_items_nhom_la_bi_chan(client):
    to_id = _to_la_sx(ten="Tổ Nhóm Lạ", ma="TO-NHOM-LA")
    r = client.get(
        "/api/san-xuat/work-items",
        params={"team_id": to_id, "nhom": "abc"},
        headers=_admin_h(client),
    )
    assert r.status_code == 422


# --- Luỹ kế sản lượng tháng của CHÍNH mình (spec 2026-09-11 §6) -----------------------------
# Route gác `require_quyen_to("read")`: admin seed KHÔNG có dòng tổ nào (không bypass) → mỗi bài tự
# cấp Xem ở một tổ trước khi gọi, như quản trị tích ma trận.
def test_luy_ke_khong_co_xem_o_to_nao_bi_chan(client):
    r = client.get("/api/san-xuat/toi/san-luong", params={"nam": 2026, "thang": 9},
                   headers=_admin_h(client))
    assert r.status_code == 403


def test_luy_ke_san_luong_cua_toi_hinh_dang(client):
    _to_la_sx(ten="Tổ Luỹ Kế API", ma="TO-LK-API")
    r = client.get("/api/san-xuat/toi/san-luong", params={"nam": 2026, "thang": 9},
                   headers=_admin_h(client))
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"nam", "thang", "employee_id", "theo_don_vi", "so_me"}
    assert d["nam"] == 2026 and d["thang"] == 9
    assert "tien" not in str(d) and "don_gia" not in str(d)


def test_luy_ke_khong_nhan_employee_id_tu_client(client):
    """Nhận `employee_id` từ URL là mở cửa cho bất kỳ ai xem sản lượng người khác."""
    _to_la_sx(ten="Tổ Luỹ Kế API", ma="TO-LK-API")
    r = client.get("/api/san-xuat/toi/san-luong",
                   params={"nam": 2026, "thang": 9, "employee_id": 999},
                   headers=_admin_h(client))
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert r.json()["employee_id"] != 999


def test_luy_ke_can_dang_nhap(client):
    assert client.get("/api/san-xuat/toi/san-luong?nam=2026&thang=9").status_code == 401


def test_luy_ke_thang_ngoai_1_12_bi_chan(client):
    _to_la_sx(ten="Tổ Luỹ Kế API", ma="TO-LK-API")
    r = client.get("/api/san-xuat/toi/san-luong", params={"nam": 2026, "thang": 13},
                   headers=_admin_h(client))
    assert r.status_code == 422


# --- Tab Sản lượng của bàn tổ (spec 2026-09-14 §6) ------------------------------------------
def test_san_luong_to_khong_co_xem_bi_chan(client):
    r = client.get("/api/san-xuat/san-luong", params={"team_id": 1}, headers=_admin_h(client))
    assert r.status_code == 403


def test_san_luong_to_hinh_dang_va_khoang_ngay_sai(client):
    to_id = _to_la_sx(ten="Tổ Sản Lượng API", ma="TO-SLT-API")
    h = _admin_h(client)
    r = client.get("/api/san-xuat/san-luong", params={"team_id": to_id}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["tong_lenh"] == 0 and d["lenh"] == [] and d["trang"] == 1
    assert d["tu"][-2:] == "01" and [t["id"] for t in d["cac_to"]] == [to_id]
    r = client.get("/api/san-xuat/san-luong",
                   params={"team_id": to_id, "tu": "2026-09-10", "den": "2026-09-01"}, headers=h)
    assert r.status_code == 400
