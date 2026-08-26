"""Gieo MỘT đơn NHÁP để chạy thử ca "khách đặt lại món cũ".

Vì sao có script này: chủ dự án lo rằng khách đặt lại đúng món cũ thì danh mục Thành phẩm sẽ
phình ra (19/08/2026). Script dựng sẵn đơn để tự bấm **Chốt đơn** trên giao diện rồi mở
`Cấu hình danh mục ▸ Thành phẩm` xem số dòng có tăng không — đúng ra là KHÔNG.

Đơn được dựng cho **đúng khách đã có thành phẩm** (`KH-GH-03` — Dược phẩm Sao Mai), mô tả gõ
LỆCH nhẹ so với lần trước (hoa/thường + kiểu gạch) để chứng minh phần chuẩn hoá tên đang chạy.

Đơn dựng thẳng ở trạng thái NHÁP và đủ điều kiện qua cổng chốt (`_confirm_gate`): có số PO, có
ngày giao cam kết, dòng đã có giá. Không có báo giá nguồn ⇒ `source_type` phải là nhập tay.

Chạy:  python -m scripts.seed_don_dat_lai
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.order import SOURCE_NHAP_TAY, STATUS_DRAFT, Order, OrderLine  # noqa: E402
from app.models.vat_lieu_kho import VatTuInAn  # noqa: E402

MA_DON = "DH-DAT-LAI"
#: Gõ LỆCH so với "Hộp thuốc 10 vỉ — in 2 màu, cán bóng": thường hoá + gạch ngắn + thừa khoảng
#: trắng. Chuẩn hoá tên phải nhận ra đây vẫn là một món (docs/prd-thanh-pham.md §5 L2).
MO_TA = "hộp thuốc 10 vỉ  -  IN 2 màu, cán bóng"


def main() -> int:
    db = SessionLocal()
    try:
        kh = db.execute(select(Customer).where(Customer.code == "KH-GH-03")).scalar_one_or_none()
        if kh is None:
            print("Chưa có khách KH-GH-03 — chạy `python -m scripts.seed_giao_hang_demo` trước.")
            return 1

        truoc = db.query(VatTuInAn).filter(VatTuInAn.customer_id == kh.id).count()

        cu = db.execute(select(Order).where(Order.order_no == MA_DON)).scalar_one_or_none()
        if cu is not None:
            db.query(OrderLine).filter(OrderLine.order_id == cu.id).delete()
            db.delete(cu)
            db.commit()
            print(f"  ~ xoá đơn {MA_DON} lần chạy trước")

        o = Order(
            order_no=MA_DON,
            customer_id=kh.id,
            status=STATUS_DRAFT,
            # `nhap_tay` để cổng chốt bỏ qua nhánh "báo giá phải được khách đồng ý" — đơn chạy
            # thử này không có báo giá nguồn. Hằng số vẫn còn (đường TẠO đã gỡ, nhưng đọc/chốt
            # thì vẫn chạy), nên đây là cách rẻ nhất để có một đơn nháp bấm Chốt được ngay.
            source_type=SOURCE_NHAP_TAY,
            # Đủ ba thứ cổng chốt đòi: PO · ngày giao · dòng có giá.
            customer_po_no="PO-DAT-LAI-01",
            delivery_committed_date=date.today() + timedelta(days=10),
            delivery_address=kh.address,
            delivery_contact_name=kh.contact_name,
            delivery_contact_phone=kh.phone,
            vat_pct_estimate=8,
        )
        o.lines.append(OrderLine(
            description=MO_TA, qty=5000, don_vi_tinh="hộp",
            unit_price_snapshot=2500, line_total=5000 * 2500, vat_pct_estimate=8,
        ))
        db.add(o)
        db.commit()

        print(f"Đã gieo đơn NHÁP {MA_DON} — {kh.name}")
        print(f"  dòng hàng: \"{MO_TA}\"  ×5.000 hộp")
        print(f"  khách này đang có {truoc} thành phẩm trong danh mục")
        print("")
        print("Cách chạy thử:")
        print(f"  1. Đơn hàng bán → mở {MA_DON} → bấm CHỐT ĐƠN.")
        print("  2. Cấu hình danh mục ▸ Thành phẩm → lọc/tìm 'Hộp thuốc'.")
        print(f"  3. Đúng ra vẫn là {truoc} dòng của khách này, KHÔNG lên {truoc + 1} —")
        print("     dòng cũ TP-KH-GH-03-001 được dùng lại dù mô tả gõ lệch hoa/thường và kiểu gạch.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
