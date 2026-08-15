"""Chứng minh ô 'Dài/Rộng nguyên' trên phiếu ĐÈ khổ danh mục → engine tính tiền giấy theo phiếu.

Dựng phiếu transient (KHÔNG commit, rollback cuối) với cùng 1 mã giấy nhưng 3 khổ nguyên khác nhau
→ tiền giấy phải ĐỔI theo số nhập trên phiếu (0 = lấy danh mục).

Chạy:  cd backend && PYTHONIOENCODING=utf-8 python scripts/verify_override.py
"""
from __future__ import annotations

import sys
from sqlalchemy import select

sys.path.insert(0, ".")
from app.db import SessionLocal  # noqa: E402
from app.models.vat_lieu_kho import GiayNguyen  # noqa: E402
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia  # noqa: E402
from app.services.tinh_gia_service import compute_phieu_snapshot  # noqa: E402


def _vi(n):
    n = float(n or 0)
    return f"{n:,.0f}".replace(",", ".")


def paper_cost(db, giay, knd, knr):
    p = PhieuTinhGia(ma="__ovr__", so_luong=4000)
    tp = PhieuThanhPhan(
        thu_tu=0, ten="x", giay_id=giay.id, quy_cach_in="mot_mat", so_mau_a=4, so_mau_b=0,
        kho_nguyen_dai=knd, kho_nguyen_rong=knr, kho_in_dai=640, kho_in_rong=435,
        con_auto=False, so_con=2, co_in=False,
    )
    p.thanh_phans = [tp]
    db.add(p)
    db.flush()
    res = compute_phieu_snapshot(db, p)
    giay_row = res["groups"][0]["rows"][0]
    db.rollback()
    return giay_row["thanh_tien"], giay_row["cong_thuc"]


def main():
    db = SessionLocal()
    try:
        giay = db.execute(select(GiayNguyen).where(GiayNguyen.ma == "D250-BOI-44.5x64")).scalar_one()
        print(f"Giấy danh mục: {giay.ma}  khổ {giay.kho_rong}×{giay.kho_dai}mm  {_vi(giay.don_gia)}đ/kg\n")
        cases = [
            ("Phiếu để 0 (lấy danh mục)", 0, 0),
            ("Phiếu nhập 640×445 (= danh mục)", 640, 445),
            ("Phiếu nhập 700×500 (ĐÈ, khổ to hơn)", 700, 500),
        ]
        for label, knd, knr in cases:
            tien, ct = paper_cost(db, giay, knd, knr)
            print(f"  {label:42} → tiền giấy {_vi(tien):>12}đ")
            print(f"      {ct}")
        print("\n→ Nếu dòng 3 KHÁC dòng 1&2 nghĩa là override ĂN vào engine (ô không còn chết).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
