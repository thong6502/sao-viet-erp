"""Dọn sạch dữ liệu GIAO DỊCH của phân hệ Giao hàng để chạy thử lại từ đầu.

XOÁ (thứ sinh ra trong lúc chạy thử):
  · yêu cầu giao · chuyến · dòng · lịch sử trạng thái;
  · yêu cầu kho + phiếu kho DO GIAO HÀNG sinh ra (`stock_requests.delivery_trip_id` khác NULL);
  · lô tồn của thành phẩm + chính các dòng danh mục Thành phẩm.

GIỮ (thứ khai một lần, xoá là phải khai lại): đơn hàng bán · khách hàng · nhân viên · tài khoản ·
phòng ban · kho · vật tư thường · yêu cầu kho của các bộ phận KHÁC.

⚠️ Chỉ đụng chứng từ kho CỦA GIAO HÀNG. Yêu cầu/phiếu vật tư thường của kho không được chạm —
đó là sổ sách của bộ phận khác.

Chạy:  python -m scripts.reset_giao_hang_demo          (chỉ xem)
       python -m scripts.reset_giao_hang_demo --xoa    (xoá thật, rồi gieo lại nền)
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from app.db import SessionLocal

#: Thứ tự XOÁ đi từ lá lên gốc — đảo thứ tự là vướng khoá ngoại.
BUOC: list[tuple[str, str]] = [
    ("dòng phiếu kho (của giao hàng)",
     "DELETE FROM stock_voucher_lines WHERE voucher_id IN ("
     "  SELECT v.id FROM stock_vouchers v JOIN stock_requests r ON r.id = v.request_id"
     "  WHERE r.delivery_trip_id IS NOT NULL)"),
    ("phiếu kho (của giao hàng)",
     "DELETE FROM stock_vouchers WHERE request_id IN ("
     "  SELECT id FROM stock_requests WHERE delivery_trip_id IS NOT NULL)"),
    ("dòng yêu cầu kho (của giao hàng)",
     "DELETE FROM stock_request_lines WHERE request_id IN ("
     "  SELECT id FROM stock_requests WHERE delivery_trip_id IS NOT NULL)"),
    ("yêu cầu kho (của giao hàng)",
     "DELETE FROM stock_requests WHERE delivery_trip_id IS NOT NULL"),
    ("lịch sử trạng thái chuyến", "DELETE FROM delivery_status_history"),
    ("dòng chuyến giao", "DELETE FROM delivery_trip_lines"),
    ("chuyến giao", "DELETE FROM delivery_trips"),
    ("dòng yêu cầu giao", "DELETE FROM delivery_request_lines"),
    ("yêu cầu giao", "DELETE FROM delivery_requests"),
    ("lô tồn của thành phẩm",
     "DELETE FROM stock_lots WHERE hang_loai = 'vat_tu' AND hang_id IN ("
     "  SELECT id FROM vat_tu_in_an WHERE customer_id IS NOT NULL)"),
    ("dòng danh mục Thành phẩm",
     "DELETE FROM vat_tu_in_an WHERE customer_id IS NOT NULL"),
]

XEM: list[tuple[str, str]] = [
    ("yêu cầu giao", "SELECT count(*) FROM delivery_requests"),
    ("chuyến giao", "SELECT count(*) FROM delivery_trips"),
    ("yêu cầu kho của giao hàng",
     "SELECT count(*) FROM stock_requests WHERE delivery_trip_id IS NOT NULL"),
    ("dòng danh mục Thành phẩm",
     "SELECT count(*) FROM vat_tu_in_an WHERE customer_id IS NOT NULL"),
    ("lô tồn của thành phẩm",
     "SELECT count(*) FROM stock_lots s WHERE s.hang_loai='vat_tu' AND EXISTS ("
     "  SELECT 1 FROM vat_tu_in_an v WHERE v.id = s.hang_id AND v.customer_id IS NOT NULL)"),
]


def _dem(db, sql: str):
    try:
        return db.execute(text(sql)).scalar()
    except Exception:
        db.rollback()
        return "?"


def main() -> int:
    xoa = "--xoa" in sys.argv
    db = SessionLocal()
    try:
        print("Trước khi dọn:")
        for ten, sql in XEM:
            print(f"   {ten:<28} {_dem(db, sql)}")

        if not xoa:
            print("\n(chỉ xem — thêm --xoa để dọn thật)")
            return 0

        print("\nĐang dọn:")
        for ten, sql in BUOC:
            try:
                n = db.execute(text(sql)).rowcount
                db.commit()
                print(f"   − {ten:<34} {n}")
            except Exception as e:
                db.rollback()
                print(f"   ! {ten:<34} BỎ QUA ({type(e).__name__})")

        print("\nSau khi dọn:")
        for ten, sql in XEM:
            print(f"   {ten:<28} {_dem(db, sql)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
