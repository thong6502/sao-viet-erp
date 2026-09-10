"""Xếp lịch 3 — lớp API: RBAC, mã lỗi, và cam kết "không chặn gì hết" ở tầng HTTP.

Luật nghiệp vụ đã có bộ riêng (`test_xep_lich_3_service.py`) chạy trên luồng thật. File này soi
đúng phần router: ai vào được, tham số thiếu thì 4xx nào, lỗi nghiệp vụ ra đúng mã, và mọi đường
GHI đều đẩy SSE (thiếu một cái là badge người khác đứng im — nguyên tắc real-time của dự án).

Lệnh trong file này dựng THẲNG bằng ORM chứ không chạy lại luồng đơn→SX: ở đây không kiểm con số,
chỉ kiểm cửa vào, nên dựng nguồn đầy đủ chỉ làm test chậm mà không thêm bằng chứng nào.
"""
from __future__ import annotations

import ast
import inspect as _inspect
from datetime import date, datetime

import pytest

from app.db import SessionLocal
from app.models.lsx import TT_SAN_SANG, Lsx

ADMIN = {"username": "admin", "password": "admin123"}
GOC = "/api/xep-lich-3"


def _hd(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _lenh(ma: str = "LSX-XL3-01", **kw) -> int:
    db = SessionLocal()
    try:
        kw.setdefault("order_id", 1)
        l = Lsx(ma=ma, ten="Lệnh thử Xếp lịch 3", order_line_id=1,
                trang_thai=TT_SAN_SANG, so_luong_dat=1000, so_to_ke_hoach=120, **kw)
        db.add(l)
        db.commit()
        return l.id
    finally:
        db.close()


# ============================================================== cửa vào
def test_chua_dang_nhap_thi_401(client):
    assert client.get(f"{GOC}/hang-cho").status_code == 401


def test_admin_doc_duoc_hang_cho(client):
    lid = _lenh()
    r = client.get(f"{GOC}/hang-cho", headers=_hd(client))
    assert r.status_code == 200
    body = r.json()
    assert lid in [d["lsx_id"] for d in body["dong"]]
    assert body["tong"] >= 1


def test_hang_cho_tim_va_phan_trang_di_qua_may_chu(client):
    _lenh("LSX-XL3-A")
    _lenh("LSX-XL3-B")
    h = _hd(client)
    assert len(client.get(f"{GOC}/hang-cho?moi_trang=1", headers=h).json()["dong"]) == 1
    r = client.get(f"{GOC}/hang-cho?tim=LSX-XL3-B", headers=h).json()
    assert [d["ma"] for d in r["dong"]] == ["LSX-XL3-B"]


def test_lich_thieu_cua_so_thi_422(client):
    """`tu`/`den` BẮT BUỘC — không mở đường trải cả lịch sử (spec §4.1)."""
    assert client.get(f"{GOC}/lich", headers=_hd(client)).status_code == 422


def test_lich_cua_so_nguoc_thi_400(client):
    r = client.get(f"{GOC}/lich?tu=2026-09-20&den=2026-09-10", headers=_hd(client))
    assert r.status_code == 400


def test_lenh_khong_ton_tai_thi_404(client):
    assert client.get(f"{GOC}/lenh/999999", headers=_hd(client)).status_code == 404


# ============================================================== ghi
def test_dat_moc_roi_doc_lai_ra_dung_moc(client):
    lid, h = _lenh(), _hd(client)
    r = client.put(f"{GOC}/lenh/{lid}", json={"bat_dau_at": "2026-09-11T08:00:00"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["bat_dau_at"].startswith("2026-09-11T08:00")
    ct = client.get(f"{GOC}/lenh/{lid}", headers=h).json()
    assert ct["bat_dau_at"].startswith("2026-09-11T08:00")
    assert lid not in [d["lsx_id"] for d in client.get(f"{GOC}/hang-cho", headers=h).json()["dong"]]


def test_chot_cu_thi_409(client):
    lid, h = _lenh(), _hd(client)
    client.put(f"{GOC}/lenh/{lid}", json={"bat_dau_at": "2026-09-11T08:00:00"}, headers=h)
    r = client.put(f"{GOC}/lenh/{lid}", json={
        "bat_dau_at": "2026-09-12T08:00:00", "expected_updated_at": "2020-01-01T00:00:00",
    }, headers=h)
    assert r.status_code == 409


def test_KHONG_CHAN_du_xep_sau_han_sx(client):
    """§1 ở tầng HTTP: trễ hạn SX vẫn 200. Trễ là chuyện của MÀU trên thanh, không phải cửa gác."""
    lid, h = _lenh(han_hoan_thanh_sx=date(2026, 9, 1)), _hd(client)
    r = client.put(f"{GOC}/lenh/{lid}", json={"bat_dau_at": "2026-09-11T08:00:00"}, headers=h)
    assert r.status_code == 200


def test_xoa_moc_tra_lenh_ve_hang_cho(client):
    lid, h = _lenh(), _hd(client)
    client.put(f"{GOC}/lenh/{lid}", json={"bat_dau_at": "2026-09-11T08:00:00"}, headers=h)
    assert client.delete(f"{GOC}/lenh/{lid}", headers=h).status_code == 200
    assert lid in [d["lsx_id"] for d in client.get(f"{GOC}/hang-cho", headers=h).json()["dong"]]


def test_xoa_moc_lenh_chua_xep_thi_404(client):
    lid, h = _lenh(), _hd(client)
    assert client.delete(f"{GOC}/lenh/{lid}", headers=h).status_code == 404


def test_phat_hanh_chua_co_moc_thi_400(client):
    lid, h = _lenh(), _hd(client)
    assert client.post(f"{GOC}/phat-hanh/{lid}", headers=h).status_code == 400


def test_phat_hanh_bam_la_di_khong_hoi_gi(client):
    """Lệnh mới `san_sang`, chưa giữ vật tư, chưa khai KCS cuối — màn 2 chặn cả ba, màn 3 cho qua."""
    from app.models.lsx import TT_DA_PHAT_HANH

    lid, h = _lenh(), _hd(client)
    client.put(f"{GOC}/lenh/{lid}", json={"bat_dau_at": "2026-09-11T08:00:00"}, headers=h)
    r = client.post(f"{GOC}/phat-hanh/{lid}", headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert db.get(Lsx, lid).trang_thai == TT_DA_PHAT_HANH
    finally:
        db.close()
    assert client.post(f"{GOC}/phat-hanh/{lid}", headers=h).status_code == 409   # bấm hai lần


def test_thu_hoi_thieu_ly_do_thi_400_chu_khong_phai_500(client):
    """Lý do thu hồi là cái VẾT, không phải cửa gác xếp lịch — nhưng lỗi phải ra 400 đọc được."""
    lid, h = _lenh(), _hd(client)
    client.put(f"{GOC}/lenh/{lid}", json={"bat_dau_at": "2026-09-11T08:00:00"}, headers=h)
    client.post(f"{GOC}/phat-hanh/{lid}", headers=h)
    assert client.delete(f"{GOC}/phat-hanh/{lid}", headers=h).status_code == 400
    r = client.delete(f"{GOC}/phat-hanh/{lid}?ly_do=Khách dời hạn", headers=h)
    assert r.status_code == 200, r.text


# ============================================================== hợp đồng router
def test_moi_duong_GHI_deu_day_SSE():
    """Soi NGUỒN chứ không soi hành vi: quên `hub.broadcast` thì màn người khác đứng im mà không
    test nghiệp vụ nào đỏ — đúng kiểu lỗi lọt lưới."""
    from app.routers import xep_lich_3 as r

    cay = ast.parse(_inspect.getsource(r))
    ghi = {"dat_moc", "xoa_moc", "phat_hanh", "thu_hoi"}
    thay = {
        n.name for n in ast.walk(cay)
        if isinstance(n, ast.FunctionDef) and n.name in ghi
        and "hub.broadcast" in ast.unparse(n)
    }
    assert thay == ghi, f"thiếu SSE ở: {sorted(ghi - thay)}"


def test_moi_route_deu_co_cua_quyen():
    from app.routers import xep_lich_3 as r

    nguon = _inspect.getsource(r)
    for hanh_dong in ("read", "update", "approve"):
        assert f'require_permission(MODULE, "{hanh_dong}")' in nguon
    # Không route nào để trống cửa: đếm số route == số lần gọi require_permission.
    cay = ast.parse(nguon)
    so_route = sum(
        1 for n in ast.walk(cay) if isinstance(n, ast.FunctionDef)
        and any("router." in ast.unparse(d) for d in n.decorator_list)
    )
    assert nguon.count("require_permission(MODULE") == so_route


def test_xep_lich_3_khong_co_scope():
    """Bàn lịch là bức tranh chung — bày dropdown Phạm vi chỉ khiến người cấp quyền tưởng nhầm."""
    from app.services.role_service import SCOPELESS_MODULES

    assert "xep_lich_3" in SCOPELESS_MODULES


# ============================================================== payload chi tiết
def test_chi_tiet_chiu_duoc_quy_cach_so_va_tra_ten_khach(client):
    """Hai lỗi ĐÃ GẶP trên dev-browser, khoá lại bằng test.

    1. `quy_cach_json` là ảnh chụp lúc tạo lệnh, `so_kem`/`so_mau` có thể là SỐ. Schema khai
       `str | None` ⇒ FastAPI ném `ResponseValidationError` = 500; mà 500 rơi NGOÀI
       `CORSMiddleware` nên trình duyệt chỉ báo "blocked by CORS policy", không ai thấy 500.
    2. `Lsx` không có relationship `order`, nên `getattr(l, "order")` luôn None và bốn ô đầu panel
       (khách · đơn · PO · sale) im lặng hiện "—".
    """
    from app.models.customer import Customer
    from app.models.order import Order

    db = SessionLocal()
    try:
        kh = Customer(code="KH-XL3", name="Công ty Bánh Ngọt")
        db.add(kh)
        db.flush()
        don = Order(order_no="SO-XL3-9", customer_id=kh.id, customer_po_no="PO-77")
        db.add(don)
        db.commit()
        oid, ten_kh = don.id, kh.name
    finally:
        db.close()

    lid = _lenh("LSX-XL3-QC", order_id=oid, quy_cach_json={"so_kem": 4, "so_mau": 4, "giay_ten": "Giấy C300"})
    r = client.get(f"{GOC}/lenh/{lid}", headers=_hd(client))
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["so_kem"], b["so_mau"], b["giay"]) == ("4", "4", "Giấy C300")
    assert b["customer_name"] == ten_kh
    assert b["order_no"] == "SO-XL3-9"
    assert b["customer_po_no"] == "PO-77"
