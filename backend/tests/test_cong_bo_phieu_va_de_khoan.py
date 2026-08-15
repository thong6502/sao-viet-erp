"""ĐỢT B (12/08/2026) — công bố phiếu lương + đè khoản "Từ hồ sơ" cho riêng một kỳ.

HAI VIỆC, MỘT GỐC: cả hai đều sinh ra từ chỗ "dữ liệu của kỳ này bị đường tự động ghi đè".

**§6b — Công bố phiếu lương.** `latest_line_for_employee` trả dòng lương của kỳ mới nhất mà KHÔNG
lọc trạng thái: HCNS vừa bấm "Tính lại", số còn đang soát, thợ đã mở điện thoại xem được; HCNS sửa
tiếp thì số đổi, không ai báo. Nay phải qua cửa CÔNG BỐ.

Chủ chốt chọn **đường 2**: KHÔNG thêm ô quyền nào. Phiếu lương là tiền của chính người ta nên ai
cũng được xem của mình — thứ cần kiểm soát là THỜI ĐIỂM, không phải AI.

**§6c — Đè khoản "Từ hồ sơ".** *"gán Hỗ trợ chi phí đi lại 200.000, nhưng tháng này nó đi nhiều
hơn thì sửa thế nào?"* Trước đó chặn thẳng, vì dòng chép từ hồ sơ bị xoá-ghi-lại mỗi lần "Tính lại".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository
from app.repositories.user_repo import UserRepository

ADMIN = {"username": "admin", "password": "admin123"}
NAM, THANG = 2026, 6


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _nv_gan_admin(client, h, ten="NV Phieu Luong") -> int:
    """NV nối vào chính tài khoản admin ⇒ gọi `/payslip/me` là ra phiếu của NV này."""
    r = client.post("/api/employees",
                    json={"full_name": ten, "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": "2020-01-01"}, headers=h)
    assert r.status_code in (200, 201), r.text
    eid = r.json()["employee"]["id"]
    db = SessionLocal()
    try:
        uid = UserRepository(db).get_by_username("admin").id
    finally:
        db.close()
    client.post(f"/api/employees/{eid}/account", json={"user_id": uid}, headers=h)
    client.post(f"/api/luong/salaries/{eid}",
                json={"effective_from": "2026-01-01", "luong_vi_tri": 10_000_000}, headers=h)
    return eid


def _chot_luong(client, h):
    """Chốt công rồi chốt lương — vòng khoá của đợt trước bắt đúng thứ tự này."""
    assert client.post("/api/attendance/period/lock", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    assert client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    r = client.post("/api/luong/lock", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════ §6b — công bố phiếu lương


def test_chua_cong_bo_thi_NV_khong_thay_phieu(client):
    """⭐ Lỗ chính: trước 12/08/2026 dòng lương vừa tính xong là NV xem được ngay."""
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)

    ps = client.get("/api/luong/payslip/me", headers=h).json()
    assert ps["has_employee"] is True
    assert ps["line"] is None, "chưa công bố mà NV đã thấy phiếu"


def test_cong_bo_roi_thi_thay(client):
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    r = client.post("/api/luong/cong-bo", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["cong_bo_luc"] is not None

    ps = client.get("/api/luong/payslip/me", headers=h).json()
    assert ps["line"] is not None and ps["period"]["month"] == THANG


def test_hen_gio_chua_toi_thi_van_chua_thay(client):
    """Hẹn giờ chỉ là ghi một mốc tương lai rồi để phép so ngày tự đúng — KHÔNG job chạy nền.
    Không job thì không có job để mà chết, không lệch múi giờ, không lo nhiều worker."""
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    mai = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post("/api/luong/cong-bo", json={"year": NAM, "month": THANG, "luc": mai},
                       headers=h).status_code == 200

    ps = client.get("/api/luong/payslip/me", headers=h).json()
    assert ps["line"] is None, "hẹn giờ ngày mai mà hôm nay đã thấy"


def test_hen_gio_da_qua_thi_thay_ngay(client):
    """Vế đối chứng của ca trên: mốc trong quá khứ = đã tới giờ."""
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    hom_qua = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert client.post("/api/luong/cong-bo", json={"year": NAM, "month": THANG, "luc": hom_qua},
                       headers=h).status_code == 200
    assert client.get("/api/luong/payslip/me", headers=h).json()["line"] is not None


def test_khong_cong_bo_duoc_ky_NHAP(client):
    """Bịt đúng cái lỗ: kỳ nháp thì số chưa đóng băng, phát ra là mời người ta đọc số sắp đổi."""
    h = _h(client)
    _nv_gan_admin(client, h)
    assert client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200

    r = client.post("/api/luong/cong-bo", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code in (400, 409, 422), f"công bố được bản nháp: {r.text}"
    assert "nháp" in r.json()["detail"]


def test_thu_hoi_thi_NV_thoi_thay_ngay(client):
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    client.post("/api/luong/cong-bo", json={"year": NAM, "month": THANG}, headers=h)
    assert client.get("/api/luong/payslip/me", headers=h).json()["line"] is not None

    assert client.post("/api/luong/thu-hoi", json={"year": NAM, "month": THANG},
                       headers=h).status_code == 200
    assert client.get("/api/luong/payslip/me", headers=h).json()["line"] is None


def test_mo_lai_ky_luong_thi_TU_THU_HOI_phieu(client):
    """Mở lại nghĩa là số sắp đổi. Để phiếu mở là NLĐ đang đọc một con số không còn đúng — mà họ
    không có cách nào biết."""
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    client.post("/api/luong/cong-bo", json={"year": NAM, "month": THANG}, headers=h)

    r = client.post("/api/luong/reopen", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["cong_bo_luc"] is None, "mở lại kỳ mà phiếu vẫn công bố"
    assert client.get("/api/luong/payslip/me", headers=h).json()["line"] is None


def test_dong_phieu_theo_gio_thi_NV_thoi_thay(client):
    """Cửa sổ MỞ–ĐÓNG (chủ chốt 12/08/2026): "cài giờ phiếu nó hiển thị trong bao nhiêu lâu".

    Cả hai đầu đều chỉ là phép so ngày lúc ĐỌC — không job nền, nên không có job để mà chết."""
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    hom_qua = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    da_dong = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert client.post("/api/luong/cong-bo",
                       json={"year": NAM, "month": THANG, "luc": hom_qua, "den": da_dong},
                       headers=h).status_code == 200

    assert client.get("/api/luong/payslip/me", headers=h).json()["line"] is None, (
        "đã qua giờ đóng mà NV vẫn xem được phiếu"
    )


def test_trong_cua_so_thi_van_thay(client):
    """Vế đối chứng: chưa tới giờ đóng thì vẫn xem được."""
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    mai = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post("/api/luong/cong-bo",
                       json={"year": NAM, "month": THANG, "den": mai},
                       headers=h).status_code == 200
    assert client.get("/api/luong/payslip/me", headers=h).json()["line"] is not None


def test_gio_dong_truoc_gio_mo_thi_chan(client):
    """Cửa sổ ngược là cửa sổ RỖNG — nhận vào thì HCNS tưởng đã phát mà không ai thấy gì."""
    h = _h(client)
    _nv_gan_admin(client, h)
    _chot_luong(client, h)
    mai = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    hom_qua = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = client.post("/api/luong/cong-bo",
                    json={"year": NAM, "month": THANG, "luc": mai, "den": hom_qua}, headers=h)
    assert r.status_code in (400, 409, 422), f"nhận cửa sổ ngược: {r.text}"
    assert "sau giờ mở" in r.json()["detail"]


# ══════════════════════════════════════════════ §6c — đè khoản "Từ hồ sơ"


def _khoan_ho_so(client, h, eid, *, muc=200_000) -> int:
    """Khai một khoản danh mục rồi gán cho NV — đây là đường "Từ hồ sơ"."""
    r = client.post("/api/luong/components",
                    json={"name": "Hỗ trợ chi phí đi lại", "kind": "thu", "is_taxable": False},
                    headers=h)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    g = client.put(f"/api/luong/components/employee/{eid}",
                   json={"items": [{"component_id": cid, "amount": muc}]}, headers=h)
    assert g.status_code in (200, 201), g.text
    return cid


def _dong_ho_so(client, h, lid: int) -> dict:
    rows = client.get(f"/api/luong/lines/{lid}/components", headers=h).json()["items"]
    return next(r for r in rows if r["source"] == "employee")


def test_de_khoan_tu_ho_so_va_TINH_LAI_khong_ghi_de(client):
    """⭐ Ca quan trọng nhất của §6c — canh CẢ HAI vế của cơ chế đè.

    Vế 1: `replace_employee_line_components` phải chừa dòng đã đè khi xoá.
    Vế 2: `generate` phải BỎ QUA khoản hồ sơ đã có dòng đè.

    Thiếu vế 1 ⇒ Tính lại ghi đè số đã sửa. Thiếu vế 2 ⇒ Tính lại sinh THÊM một dòng nữa và NV ăn
    tiền hai lần. Ca này bắt cả hai."""
    h = _h(client)
    eid = _nv_gan_admin(client, h)
    _khoan_ho_so(client, h, eid)
    gen = client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                      headers=h).json()
    lid = next(l["id"] for l in gen["lines"] if l["employee_id"] == eid)
    row = _dong_ho_so(client, h, lid)
    assert row["amount"] == 200_000 and row["da_de_tay"] is False

    # Tháng này đi nhiều hơn → đè lên 350.000.
    sua = client.put(f"/api/luong/lines/components/{row['id']}",
                     json={"amount": 350_000}, headers=h)
    assert sua.status_code == 200, sua.text
    assert sua.json()["amount"] == 350_000 and sua.json()["da_de_tay"] is True

    client.post("/api/luong/generate", json={"year": NAM, "month": THANG}, headers=h)
    sau = client.get(f"/api/luong/lines/{lid}/components", headers=h).json()["items"]
    cua_ho_so = [r for r in sau if r["source"] == "employee"]
    assert len(cua_ho_so) == 1, (
        f"Tính lại sinh {len(cua_ho_so)} dòng — `generate` chưa bỏ qua khoản đã đè, "
        "NV sẽ ăn tiền hai lần"
    )
    assert cua_ho_so[0]["amount"] == 350_000, "Tính lại đã ghi đè số đè tay"


def test_tra_ve_theo_ho_so(client):
    """Người bấm "Trả về theo hồ sơ" muốn thấy số cũ NGAY, không phải chờ bấm Tính lại."""
    h = _h(client)
    eid = _nv_gan_admin(client, h)
    _khoan_ho_so(client, h, eid)
    gen = client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                      headers=h).json()
    lid = next(l["id"] for l in gen["lines"] if l["employee_id"] == eid)
    row = _dong_ho_so(client, h, lid)
    client.put(f"/api/luong/lines/components/{row['id']}", json={"amount": 350_000}, headers=h)

    r = client.post(f"/api/luong/lines/components/{row['id']}/bo-de", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 200_000 and r.json()["da_de_tay"] is False


def test_thuong_nong_van_song_qua_tinh_lai_nhu_cu(client):
    """Vế CŨ không được vỡ: dòng `source='line'` (thưởng nóng) vẫn phải sống sót qua Tính lại.
    Sửa cơ chế xoá-ghi-lại mà làm hỏng vế này là mất tiền của người lao động."""
    h = _h(client)
    eid = _nv_gan_admin(client, h)
    gen = client.post("/api/luong/generate", json={"year": NAM, "month": THANG},
                      headers=h).json()
    lid = next(l["id"] for l in gen["lines"] if l["employee_id"] == eid)
    cid = client.post("/api/luong/components",
                      json={"name": "Thưởng nóng T6", "kind": "thu", "is_taxable": True},
                      headers=h).json()["id"]
    them = client.post(f"/api/luong/lines/{lid}/components",
                       json={"component_id": cid, "amount": 500_000}, headers=h)
    assert them.status_code in (200, 201), them.text

    client.post("/api/luong/generate", json={"year": NAM, "month": THANG}, headers=h)
    sau = client.get(f"/api/luong/lines/{lid}/components", headers=h).json()["items"]
    assert any(r["source"] == "line" and float(r["amount"]) == 500_000 for r in sau)


def test_giao_dien_that_su_noi_vao_hai_tinh_nang_nay():
    """Hàng rào chống khuôn sai đã lặp 4 lần vòng này: máy chủ đổi, giao diện quên.

    Backend có endpoint mà màn không gọi thì tính năng coi như không tồn tại — mà test API vẫn
    xanh hết."""
    from pathlib import Path

    fe = Path(__file__).resolve().parents[2] / "frontend" / "src"
    client_ts = (fe / "api" / "client.ts").read_text(encoding="utf-8")
    luong = (fe / "pages" / "LuongPage.tsx").read_text(encoding="utf-8")

    for can in ("cong_bo_luc", "dong_phieu_luc", "congBo(", "thuHoi(", "boDeComponent(",
                "da_de_tay"):
        assert can in client_ts, f"client.ts thiếu {can}"
    for can in ("congBo(", "thuHoi(", "cong_bo_luc", "dong_phieu_luc", "boDeComponent(",
                "da_de_tay", "lg-congbo"):
        assert can in luong, f"màn Lương không dùng {can}"
    assert "Trả về theo hồ sơ" in luong, "thiếu nút bỏ đè — đè xong không có đường lui"
    assert "Thu hồi phiếu" in luong, "thiếu nút thu hồi — công bố nhầm là kẹt"
