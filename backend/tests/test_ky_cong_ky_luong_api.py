"""Kỳ công và kỳ lương khoá lẫn nhau — tiền đã phát thì bảng công đằng sau phải đóng băng.

Chốt hiện có ở `reopen_period` chỉ chặn khi kỳ lương ở trạng thái **đã chốt** (`locked`), mà `paid`
là trạng thái ĐI SAU nó (chốt → đã chi). Nên nó quên đúng lúc nguy hiểm nhất: lương đã phát cho
công nhân rồi mà bảng công đằng sau vẫn mở lại và sửa được ⇒ mất hẳn dấu vết "lương tháng này trả
theo công nào", kiểm toán hỏi là không trả lời được.

Cùng lỗi ở `period_status` — nó nuôi cái nút "Mở lại kỳ công" trên giao diện. Sót `paid` ở đó thì
màn vẫn bày nút ra, người dùng bấm mới ăn lỗi: hai tầng nói khác nhau.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository
from app.repositories.user_repo import UserRepository

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG = 2026, 5


def _h(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json=ADMIN).json()['access_token']}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _uid(username: str) -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username(username).id
    finally:
        db.close()


def _mot_nhan_vien(client, h) -> dict:
    emp = client.post(
        "/api/employees",
        json={"probation_end_date": "2025-12-31", "full_name": "NV Khoá Kỳ", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2020-01-01"},
        headers=h,
    )
    assert emp.status_code in (200, 201), emp.text
    body = emp.json()["employee"]
    client.post(f"/api/employees/{body['id']}/account", json={"user_id": _uid("admin")}, headers=h)
    return body


def _den_trang_thai(client, h, *, den: str) -> None:
    """Đưa cả kỳ công lẫn kỳ lương tới trạng thái cần thử.

    `den` = "locked" (lương đã chốt) hoặc "paid" (lương đã chi)."""
    assert client.post("/api/attendance/period/lock", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    assert client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    assert client.post("/api/luong/lock", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    if den == "paid":
        r = client.post("/api/luong/pay", json={"year": NAM, "month": THANG, "note": "chi lương"},
                        headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "paid"


def test_luong_DA_CHI_thi_khong_mo_lai_duoc_ky_cong(client):
    """⭐ Lỗ chính: tiền đã phát rồi mà vẫn sửa được bảng công đằng sau."""
    h = _h(client)
    _mot_nhan_vien(client, h)
    _den_trang_thai(client, h, den="paid")

    r = client.post("/api/attendance/period/reopen", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 400, f"mở lại được kỳ công trong khi lương ĐÃ CHI: {r.text}"
    assert "ĐÃ CHI" in r.json()["detail"], "câu báo phải nói rõ là đã chi, không phải chỉ 'đã chốt'"

    # Kỳ công phải còn nguyên trạng thái chốt.
    st = client.get("/api/attendance/period", params={"year": NAM, "month": THANG}, headers=h).json()
    assert st["status"] == "locked"


def test_giao_dien_khong_duoc_bay_nut_mo_lai_khi_luong_da_chi(client):
    """`period_status.payroll_locked` nuôi cái nút trên màn. Sót `paid` ở đây thì màn mời người
    dùng bấm vào một nút chắc chắn lỗi."""
    h = _h(client)
    _mot_nhan_vien(client, h)
    _den_trang_thai(client, h, den="paid")

    st = client.get("/api/attendance/period", params={"year": NAM, "month": THANG}, headers=h).json()
    assert st["payroll_locked"] is True, "màn sẽ bày nút Mở lại kỳ công cho kỳ đã chi"


def test_luong_moi_CHOT_van_chan_nhu_cu(client):
    """Vế cũ không được vỡ khi vá vế mới."""
    h = _h(client)
    _mot_nhan_vien(client, h)
    _den_trang_thai(client, h, den="locked")

    r = client.post("/api/attendance/period/reopen", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 400, r.text
    assert "đã chốt" in r.json()["detail"]
    assert client.get("/api/attendance/period", params={"year": NAM, "month": THANG},
                      headers=h).json()["payroll_locked"] is True


def test_huy_da_chi_roi_mo_lai_luong_thi_ky_cong_mo_duoc(client):
    """Vẫn phải có đường ra: huỷ đã chi → mở lại kỳ lương → lúc đó kỳ công mới mở được.

    Không có vế này thì cái chốt trên thành ngõ cụt vĩnh viễn."""
    h = _h(client)
    _mot_nhan_vien(client, h)
    _den_trang_thai(client, h, den="paid")

    assert client.post("/api/luong/unpay", json={"year": NAM, "month": THANG, "note": "hủy"},
                       headers=h).status_code == 200
    # Mới huỷ chi thì lương về "đã chốt" — vẫn còn chặn.
    assert client.post("/api/attendance/period/reopen", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 400

    assert client.post("/api/luong/reopen", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    mo = client.post("/api/attendance/period/reopen", json={"year": NAM, "month": THANG}, headers=h)
    assert mo.status_code == 200, f"lương đã mở lại mà kỳ công vẫn kẹt: {mo.text}"
    assert client.get("/api/attendance/period", params={"year": NAM, "month": THANG},
                      headers=h).json()["status"] == "draft"
