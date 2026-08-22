"""Dọn dòng `TP-*` khai theo THIẾT KẾ CŨ (trước mg 0203).

Bối cảnh: bản đầu bắt người lập yêu cầu giao "chọn mặt hàng kho", nên seed dựng sẵn 6 dòng mã tự
đặt (`TP-HOP-BANH`, `TP-TEM-DAN`…). Từ mg 0203 mã sinh theo công thức `TP-<số đơn>-<id dòng>` và
có `order_line_id` trỏ về dòng đơn — 6 dòng cũ không nối về đâu cả, để lại là rác trong ô tìm
mặt hàng của kho.

Chủ chốt 19/08/2026: "xoá", không backfill.

KHÔNG nhét vào migration: migration chạy cả trên prod, mà prod chưa bao giờ có mấy dòng này —
một migration đi xoá dữ liệu theo tên là thứ không ai muốn thấy chạy trên DB thật.

Chạy:  python -m scripts.don_thanh_pham_cu          (chỉ xem)
       python -m scripts.don_thanh_pham_cu --xoa    (xoá thật)
"""
from __future__ import annotations

import sys

from app.db import SessionLocal
from app.models.stock_lot import StockLot
from app.models.stock_voucher import StockVoucherLine
from app.models.vat_lieu_kho import VatTuInAn


def main() -> int:
    xoa = "--xoa" in sys.argv
    db = SessionLocal()
    try:
        # Dòng `TP-*` khai theo KHOÁ CŨ: mã cũ là `TP-<số đơn>-<id dòng>` (mg 0203) hoặc mã tự
        # đặt của seed đời đầu — cả hai đều KHÔNG khớp khuôn mới `TP-<mã khách>-<nnn>`.
        # Nhận diện bằng chính khuôn mã: đuôi phải là đúng 3 chữ số.
        import re

        rac = [
            r for r in db.query(VatTuInAn).filter(VatTuInAn.ma.like("TP-%"))
                        .order_by(VatTuInAn.ma).all()
            if not re.fullmatch(r"TP-.+-\d{3}", r.ma or "")
        ]
        if not rac:
            print("Không còn dòng TP-* kiểu cũ nào.")
            return 0

        print(f"{len(rac)} dòng danh mục kiểu cũ:")
        chan = []
        for r in rac:
            lots = db.query(StockLot).filter(
                StockLot.hang_loai == "vat_tu", StockLot.hang_id == r.id
            ).all()
            # Lô ĐÃ ĐI VÀO PHIẾU thì không xoá — xoá là thủng sổ kho. Chỉ xoá lô chưa ai đụng.
            dinh = sum(
                db.query(StockVoucherLine).filter(StockVoucherLine.lot_id == lot.id).count()
                for lot in lots
            )
            print(f"   {r.ma:<24} | {r.ten[:44]:<46} | {len(lots)} lô | {dinh} dòng phiếu")
            if dinh:
                chan.append(r.ma)

        if chan:
            print(f"\n⚠️  BỎ QUA {len(chan)} dòng đã có phiếu kho: {', '.join(chan)}")
            print("   Xoá mấy dòng này là thủng sổ kho — phải huỷ phiếu bên kho trước.")

        if not xoa:
            print("\n(chỉ xem — thêm --xoa để xoá thật)")
            return 0

        n_lot = n_hang = 0
        for r in rac:
            if r.ma in chan:
                continue
            for lot in db.query(StockLot).filter(
                StockLot.hang_loai == "vat_tu", StockLot.hang_id == r.id
            ).all():
                db.delete(lot)
                n_lot += 1
            db.delete(r)
            n_hang += 1
        db.commit()
        print(f"\nĐã xoá {n_hang} dòng danh mục + {n_lot} lô tồn.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
