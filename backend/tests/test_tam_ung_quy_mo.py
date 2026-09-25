"""Tạm ứng ở quy mô nhà máy (~1000 người) — khoá bằng SỐ TRUY VẤN (25/09/2026).

Đo trên Postgres với 1000 nhân viên, trước khi gom: lập 1000 phiếu 25 giây, duyệt 1000 phiếu 33
giây, lập 200 phiếu chi 12 giây — mỗi phiếu ~10 truy vấn + 1 commit. Sau khi gom: 0,6 s · 1,3 s ·
2,2 s (1000 phiếu chi). Bài này không đo giây (máy CI lên xuống), mà khoá điều làm nên con số đó:
số câu ĐỌC (SELECT) KHÔNG tăng theo số phiếu. Ai vô tình đưa một câu tra cứu vào vòng lặp là bài
đỏ ngay.

Chỉ đếm SELECT: câu GHI trên SQLite của bộ test vẫn đi từng dòng vì driver `pysqlite` không báo
được số dòng của executemany (SQLAlchemy tự tách UPDATE/INSERT để kiểm) — trên Postgres cả lượt
1000 phiếu chỉ ~20 câu. N+1 luôn là câu ĐỌC trong vòng lặp.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models.accounting import PaymentVoucher
from app.models.employee import Employee

from .test_accounting_api import _headers

NAM, THANG = 2026, 8


class _Dem:
    def __init__(self):
        self.n = 0

    def __enter__(self):
        event.listen(engine, "before_cursor_execute", self._cong)
        return self

    def __exit__(self, *a):
        event.remove(engine, "before_cursor_execute", self._cong)

    def _cong(self, conn, cursor, statement, *a, **k):
        if statement.lstrip().upper().startswith("SELECT"):
            self.n += 1


def _nhan_vien(tien_to: str, n: int) -> list[int]:
    db = SessionLocal()
    try:
        rows = [Employee(code=f"{tien_to}{i:03d}", full_name=f"Quy Mô {tien_to} {i}", status="active",
                         hire_date=date(2024, 1, 1)) for i in range(n)]
        db.add_all(rows)
        db.commit()
        return [r.id for r in rows]
    finally:
        db.close()


def _lap(client, h, eids):
    return client.post("/api/luong/advances/bulk", headers=h, json={
        "period_year": NAM, "period_month": THANG, "advance_date": "2026-08-15", "kind": "tam_ung",
        "reason": "Ứng giữa tháng", "items": [{"employee_id": e, "amount": 500_000} for e in eids]})


def _ba_buoc(client, h, eids) -> tuple[list[int], dict[str, int]]:
    """Lập → duyệt → chi một lượt cho `eids`; trả id phiếu + số truy vấn từng bước."""
    so = {}
    with _Dem() as d:
        r = _lap(client, h, eids)
    assert r.status_code == 201, r.text
    so["lap"] = d.n
    ids = [a["id"] for a in r.json()["items"]]
    with _Dem() as d:
        r = client.post("/api/luong/advances/bulk-decision", json={"ids": ids, "approve": True},
                        headers=h)
    assert r.status_code == 200, r.text
    so["duyet"] = d.n
    with _Dem() as d:
        r = client.post("/api/accounting/payment-vouchers/from-advances", json={
            "salary_advance_ids": ids, "voucher_type": "cash", "voucher_date": "2026-08-20"},
            headers=h)
    assert r.status_code == 201, r.text
    so["chi"] = d.n
    return ids, so


def test_so_truy_van_khong_tang_theo_so_phieu(client):
    h = _headers(client)
    _, it = _ba_buoc(client, h, _nhan_vien("QA", 3))
    _, nhieu = _ba_buoc(client, h, _nhan_vien("QB", 30))
    for buoc in ("lap", "duyet", "chi"):
        # 10× số phiếu mà số câu đọc đứng yên.
        assert nhieu[buoc] - it[buoc] <= 3, (buoc, it, nhieu)


def test_danh_sach_gan_ma_phieu_chi_cua_ca_lo(client):
    h = _headers(client)
    ids, _ = _ba_buoc(client, h, _nhan_vien("QC", 4))
    r = client.get("/api/luong/advances", params={"year": NAM, "month": THANG}, headers=h)
    theo = {a["id"]: a for a in r.json()["items"]}
    db = SessionLocal()
    try:
        pcs = db.query(PaymentVoucher).filter(PaymentVoucher.content.like("%4 người%")).all()
    finally:
        db.close()
    # Chi một lượt 4 người ⇒ MỘT phiếu chi, cả 4 dòng mang cùng mã (máy chủ gắn sẵn trên dòng).
    assert len(pcs) == 1 and int(pcs[0].amount) == 4 * 500_000
    for aid in ids:
        assert theo[aid]["phieu_chi_code"] == pcs[0].code
        assert theo[aid]["phieu_chi_id"] == pcs[0].id
        assert theo[aid]["employee_code"].startswith("QC")


def test_lap_hang_loat_vuong_tra_ve_dung_nguoi(client):
    """Một người ngoài bảng công lẫn vào ⇒ không phiếu nào; `vuong_ids` chỉ đúng người đó."""
    h = _headers(client)
    eids = _nhan_vien("QD", 3)
    r = _lap(client, h, eids + [999_999])
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["vuong_ids"] == [999_999]
    r = client.get("/api/luong/advances", params={"year": NAM, "month": THANG}, headers=h)
    assert not [a for a in r.json()["items"] if (a.get("employee_code") or "").startswith("QD")]
