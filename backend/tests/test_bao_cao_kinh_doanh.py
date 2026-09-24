"""Báo cáo kinh doanh theo khách hàng (24/09/2026).

Chủ chốt: chỉ ĐƠN ĐÃ CHỐT, vào kỳ theo NGÀY CHỐT (giờ VN), phạm vi theo ô quyền riêng
`bao_cao_kinh_doanh` (sale `own` chỉ thấy đơn mình bán). Mỗi khách → đơn → dòng sản phẩm (đơn giá)
+ cọc phải thu / đã nhận của từng đơn. Xuất Excel được mọi khách hoặc đúng một khách.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from openpyxl import load_workbook

from app.db import SessionLocal
from app.models.accounting import PAYMENT_RECEIPT_RECEIVED, RECEIPT_SOURCE_ORDER, PaymentReceipt
from app.models.customer import Customer
from app.models.order import Order, OrderLine
from app.models.user import User
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

URL = "/api/bao-cao-kinh-doanh"
VN = timezone(timedelta(hours=7))


def _h(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _khach(ten: str, ma: str) -> int:
    db = SessionLocal()
    try:
        k = Customer(code=ma, name=ten)
        db.add(k)
        db.commit()
        return k.id
    finally:
        db.close()


def _don(khach_id: int, so: str, *, chot_luc: datetime | None, status: str = "ordered",
         coc_pct: float | None = 30, sale_id: int | None = None,
         dong=(("Hộp giấy in 4 màu", 1000, 2500),)) -> int:
    db = SessionLocal()
    try:
        o = Order(order_no=so, customer_id=khach_id, status=status, ordered_at=chot_luc,
                  deposit_pct=coc_pct, sale_user_id=sale_id, customer_po_no=f"PO-{so}")
        for ten, sl, gia in dong:
            o.lines.append(OrderLine(description=ten, qty=sl, don_vi_tinh="cái",
                                     unit_price_snapshot=gia, line_total=sl * gia,
                                     vat_pct_estimate=8))
        db.add(o)
        db.commit()
        return o.id
    finally:
        db.close()


def _coc(order_id: int, tien: int) -> None:
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        db.add(PaymentReceipt(
            code=f"PT-BCKD-{order_id}-{tien}", source_type=RECEIPT_SOURCE_ORDER,
            order_id=order_id, payer_name="Khách", receipt_method="cash",
            status=PAYMENT_RECEIPT_RECEIVED, receipt_date=date.today(), amount=tien,
            amount_vnd=tien, currency="VND", exchange_rate=1, content="Cọc đơn",
            created_by_user_id=admin.id, received_by_user_id=admin.id,
        ))
        db.commit()
    finally:
        db.close()


def _luc(y, m, d, h=10) -> datetime:
    """Giờ VN → lưu UTC, y như app (`ordered_at = datetime.now(timezone.utc)`). SQLite của test so
    chuỗi, nên ghi lệch múi giờ với tham số truy vấn là so sai — Postgres thì không bị."""
    return datetime(y, m, d, h, tzinfo=VN).astimezone(timezone.utc)


def test_gom_theo_khach_don_dong_va_coc(client):
    kh = _khach("Công ty BCKD Alpha", "KH-BCKD-A")
    d1 = _don(kh, "DH-BCKD-1", chot_luc=_luc(2026, 9, 5),
              dong=(("Hộp cứng", 1000, 2500), ("Tem nhãn", 2000, 300)))   # 3.100.000
    _coc(d1, 500_000)
    _don(kh, "DH-BCKD-NHAP", chot_luc=None, status="draft")               # nháp: không vào
    _don(kh, "DH-BCKD-HUY", chot_luc=_luc(2026, 9, 6), status="cancelled")  # hủy: không vào
    _don(kh, "DH-BCKD-NGOAI", chot_luc=_luc(2026, 10, 1))                 # ngoài kỳ
    # Chốt 23:30 giờ VN ngày 30/09 = 16:30 UTC — vẫn là ngày 30/09, phải VÀO kỳ tháng 9.
    _don(kh, "DH-BCKD-KHUYA", chot_luc=_luc(2026, 9, 30, 23), dong=(("Túi giấy", 10, 1000),))

    r = client.get(URL, params={"tu_ngay": "2026-09-01", "den_ngay": "2026-09-30"}, headers=_h(client))
    assert r.status_code == 200, r.text
    k = next(x for x in r.json()["khach"] if x["ma"] == "KH-BCKD-A")
    assert [d["order_no"] for d in k["don"]] == ["DH-BCKD-1", "DH-BCKD-KHUYA"]
    d = k["don"][0]
    assert [(ln["ten"], ln["so_luong"], ln["don_gia"], ln["thanh_tien"]) for ln in d["dong"]] == [
        ("Hộp cứng", 1000, 2500, 2_500_000), ("Tem nhãn", 2000, 300, 600_000)]
    assert d["tong"] == 3_100_000 and d["tong_vat"] == 3_348_000          # VAT 8%
    assert d["coc_pct"] == 30 and d["coc_phai_thu"] == 1_004_400          # 30% × có VAT
    assert (d["coc_da_nhan"], d["coc_con_thieu"]) == (500_000, 504_400)
    assert d["ngay_chot"] == "2026-09-05"
    assert k["so_don"] == 2 and k["tong"] == 3_110_000


def test_xuat_excel_mot_khach(client):
    ka = _khach("Công ty BCKD Beta", "KH-BCKD-B")
    kb = _khach("Công ty BCKD Gamma", "KH-BCKD-G")
    _don(ka, "DH-BCKD-B1", chot_luc=_luc(2026, 8, 10))
    _don(kb, "DH-BCKD-G1", chot_luc=_luc(2026, 8, 11))
    r = client.get(f"{URL}/export.xlsx",
                   params={"tu_ngay": "2026-08-01", "den_ngay": "2026-08-31", "customer_id": ka},
                   headers=_h(client))
    assert r.status_code == 200, r.text
    assert "bao-cao-kinh-doanh-KH-BCKD-B-2026-08-01" in r.headers["content-disposition"]
    ws = load_workbook(BytesIO(r.content)).active
    chu = [str(v) for row in ws.iter_rows(values_only=True) for v in row if v is not None]
    assert any("KH-BCKD-B" in c for c in chu)
    assert not any("KH-BCKD-G" in c for c in chu), "xuất một khách thì không lẫn khách khác"
    assert "DH-BCKD-B1" in chu and "Hộp giấy in 4 màu" in chu
    assert ws["D4"].value == "Sản phẩm" and ws["G4"].value == "Đơn giá"
    assert ws["L4"].value == "Cọc phải thu" and ws["M4"].value == "Cọc đã nhận"


def test_sale_pham_vi_cua_toi_chi_thay_don_minh_ban(client):
    db = SessionLocal()
    try:
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        vai = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        users = UserRepository(db)
        u = users.create(username="sale-bckd", name="Sale BCKD", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=vai.id, is_active=True)
        sale_id = u.id
    finally:
        db.close()
    kh = _khach("Công ty BCKD Delta", "KH-BCKD-D")
    _don(kh, "DH-BCKD-CUA-TOI", chot_luc=_luc(2026, 7, 5), sale_id=sale_id)
    _don(kh, "DH-BCKD-NGUOI-KHAC", chot_luc=_luc(2026, 7, 6))
    tok = create_access_token(str(sale_id))
    r = client.get(URL, params={"tu_ngay": "2026-07-01", "den_ngay": "2026-07-31"},
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    so = [d["order_no"] for k in r.json()["khach"] for d in k["don"]]
    assert so == ["DH-BCKD-CUA-TOI"]


def test_thieu_quyen_bi_chan_va_khoang_ngay_nguoc(client):
    db = SessionLocal()
    try:
        sx = DepartmentRepository(db).get_by_name("Sản xuất")
        vai = RoleRepository(db).get_by_name_and_department("Thợ SX", sx.id)
        users = UserRepository(db)
        u = users.create(username="tho-bckd", name="Thợ", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=sx.id, role_id=vai.id, is_active=True)
        tok = create_access_token(str(u.id))
    finally:
        db.close()
    r = client.get(URL, params={"tu_ngay": "2026-07-01", "den_ngay": "2026-07-31"},
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    r2 = client.get(URL, params={"tu_ngay": "2026-07-31", "den_ngay": "2026-07-01"},
                    headers=_h(client))
    assert r2.status_code == 422
