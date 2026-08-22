"""CỘNG THÊM dữ liệu để chạy thử phân hệ Giao hàng (docs/prd-giao-hang.md). KHÔNG wipe gì.

Gieo đúng những thứ luồng giao hàng CẦN mà DB dev đang thiếu:

  · 1 kho "Kho thành phẩm"  — đề nghị xuất hàng phải trỏ vào một kho trong danh mục `kho_hang`.
                              Danh mục kho không ràng buộc loại hàng nên đây là CẤU HÌNH, không
                              phải code (PRD §6).
  · 3 khách hàng            — có địa chỉ + người nhận, để màn tạo yêu cầu ĐIỀN SẴN được.
  · 3 đơn hàng bán ĐÃ CHỐT  — mỗi đơn 2 dòng hàng, có `delivery_*` để test luật snapshot.
  · 2 tài xế CÓ TÀI KHOẢN   — kèm vai "Tài xế giao hàng" (Xem + Thao tác, phạm vi Của tôi).
  · 1 vai "Quản lý giao hàng" — đủ ô để lên kế hoạch.

**Tài xế bắt buộc có tài khoản đăng nhập.** Họ còn phải tự bấm *Đã lấy hàng* rồi nhập kết quả +
km; ai không vào được màn Giao hàng thì không lọt vào ô chọn lúc phân công — và nếu lọt thì chuyến
nhận xong sẽ TẮC ở đó, không ai đóng được.

Idempotent: get-or-create theo mã / username. Chạy lại KHÔNG đẻ thêm hàng.

Mọi thứ gieo ra đều mang tiền tố `KH-GH` / `DH-GH` / `NVGH` để tìm và xoá lại được:

    DELETE FROM delivery_requests WHERE order_id IN
      (SELECT id FROM orders WHERE order_no LIKE 'DH-GH%');
    DELETE FROM orders    WHERE order_no LIKE 'DH-GH%';
    DELETE FROM customers WHERE code     LIKE 'KH-GH%';
    DELETE FROM employees WHERE code     LIKE 'NVGH%';
    DELETE FROM users     WHERE username IN ('taixe1', 'taixe2');

Chạy:  cd backend && PYTHONIOENCODING=utf-8 python scripts/seed_giao_hang_demo.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from sqlalchemy import bindparam, select, text

sys.path.insert(0, ".")
from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.delivery import (  # noqa: E402
    DeliveryRequest,
    DeliveryRequestLine,
    DeliveryStatusHistory,
    DeliveryTrip,
    DeliveryTripLine,
)
from app.models.department import Department  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.kho_hang import KhoHang  # noqa: E402
from app.models.stock_lot import LOT_AVAILABLE, StockLot  # noqa: E402
from app.services.thanh_pham_khai_bao import khai_cho_don  # noqa: E402
from app.models.order import STATUS_ORDERED, Order, OrderLine  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.repositories.rbac_repo import RoleRepository  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402
from app.security import hash_password  # noqa: E402

KHACH = [
    ("KH-GH-01", "Công ty Bánh kẹo Minh Long",
     "112 Nguyễn Văn Cừ, P. An Hoà, Q. Ninh Kiều, Cần Thơ", "Chị Lan (kho)", "0901234567"),
    ("KH-GH-02", "Nhà sách Trí Việt",
     "45 Lê Lợi, P. Bến Nghé, Q.1, TP.HCM", "Anh Tuấn", "0912345678"),
    ("KH-GH-03", "Dược phẩm Sao Mai",
     "Lô C3, KCN Tân Bình, TP.HCM", "Chị Hạnh (nhận hàng)", "0938765432"),
]

# (mã đơn, mã khách, [(mô tả, số lượng, đvt, đơn giá)])
DON = [
    ("DH-GH-01", "KH-GH-01", [
        ("Hộp giấy đựng bánh 200g — in offset 4 màu", 5000, "hộp", 4200),
        ("Tem nhãn dán hộp — decal 7×5cm", 5000, "cái", 350),
    ]),
    ("DH-GH-02", "KH-GH-02", [
        ("Sách bài tập Toán lớp 5 — bìa mềm 120 trang", 3000, "cuốn", 18500),
        ("Bìa lót sách — giấy Ford 100gsm", 3000, "tờ", 900),
    ]),
    ("DH-GH-03", "KH-GH-03", [
        ("Hộp thuốc 10 vỉ — in 2 màu, cán bóng", 12000, "hộp", 2800),
        ("Tờ hướng dẫn sử dụng — gấp 3", 12000, "tờ", 450),
    ]),
]

# Danh mục thành phẩm KHÔNG khai ở đây nữa (mg 0203): chốt đơn là hệ tự khai từ chính dòng đơn,
# mã `TP-<số đơn>-<id dòng>`. Bảng `THANH_PHAM` cũ gỡ 19/08/2026 — sáu mã tự đặt ở đó không nối về
# đơn nào cả, đúng cái sai mà docs/prd-thanh-pham.md §9 ghi lại.

# (mã NV, họ tên, username)
TAI_XE = [("NVGH01", "Trần Văn Hùng", "taixe1"), ("NVGH02", "Lê Minh Tú", "taixe2")]

# Tài xế: Xem + Thao tác, phạm vi CỦA TÔI ⇒ chỉ thấy chuyến của chính mình.
VAI_TAI_XE = dict(can_read=True, can_create=True, scope="own")
# Quản lý giao hàng: thêm hai ô chi tiết + huỷ, phạm vi TẤT CẢ.
VAI_QUAN_LY = dict(can_read=True, can_create=True, can_plan=True, can_view_drivers=True,
                   can_cancel=True, scope="all")


def _don_rac(db) -> None:
    """XOÁ mọi yêu cầu giao / chuyến của ba đơn demo, kèm yêu cầu kho chúng đã đẻ ra.

    Vì sao cần: luồng Giao hàng đã đổi ba lần trong ngày 19/08/2026 (chứng từ tự sinh → chứng từ
    song song → yêu cầu xuất kho thật). Dòng lập theo luồng cũ KHÔNG có mặt hàng kho
    (`delivery_request_lines.hang_loai` NULL) nên tới bước gửi kho là tắc, mà thông báo lại chỉ
    nói "chưa khai mặt hàng" — người test tưởng tính năng hỏng.

    Chỉ đụng dữ liệu của ĐƠN DEMO `DH-GH-*`. Yêu cầu giao của đơn thật (nếu có) giữ nguyên.
    """
    don_ids = [r[0] for r in db.execute(
        select(Order.id).where(Order.order_no.like("DH-GH-%"))
    ).all()]
    if not don_ids:
        return
    req_ids = [r[0] for r in db.execute(
        select(DeliveryRequest.id).where(DeliveryRequest.order_id.in_(don_ids))
    ).all()]
    if not req_ids:
        print("  = chưa có yêu cầu giao cũ nào để dọn")
        return
    trip_ids = [r[0] for r in db.execute(
        select(DeliveryTrip.id).where(DeliveryTrip.request_id.in_(req_ids))
    ).all()]

    # Gỡ soft-ref trước khi xoá chuyến — cột trỏ hư không thì màn Kho hiện yêu cầu mồ côi.
    if trip_ids:
        db.execute(text(
            "UPDATE stock_requests SET delivery_trip_id = NULL WHERE delivery_trip_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)), {"ids": trip_ids})
        db.query(DeliveryStatusHistory).filter(
            DeliveryStatusHistory.trip_id.in_(trip_ids)).delete(synchronize_session=False)
        db.query(DeliveryTripLine).filter(
            DeliveryTripLine.trip_id.in_(trip_ids)).delete(synchronize_session=False)
    db.query(DeliveryTrip).filter(
        DeliveryTrip.request_id.in_(req_ids)).delete(synchronize_session=False)
    db.query(DeliveryRequestLine).filter(
        DeliveryRequestLine.request_id.in_(req_ids)).delete(synchronize_session=False)
    db.query(DeliveryRequest).filter(
        DeliveryRequest.id.in_(req_ids)).delete(synchronize_session=False)
    db.commit()
    print(f"  ~ dọn {len(req_ids)} yêu cầu giao + {len(trip_ids)} chuyến cũ (luồng đã bỏ)")


def _kho(db) -> KhoHang:
    kho = db.execute(select(KhoHang).where(KhoHang.ma == "KTP")).scalar_one_or_none()
    if kho is None:
        kho = KhoHang(ma="KTP", ten="Kho thành phẩm", vi_tri="Tầng 1 — xưởng A",
                      ghi_chu="Nơi giữ hàng đã in xong, chờ giao khách")
        db.add(kho)
        db.flush()
        print(f"  + kho {kho.ma} — {kho.ten}")
    else:
        print(f"  = kho {kho.ma} đã có")
    return kho


def _khach(db) -> dict[str, Customer]:
    ra: dict[str, Customer] = {}
    for ma, ten, dia_chi, nguoi, sdt in KHACH:
        kh = db.execute(select(Customer).where(Customer.code == ma)).scalar_one_or_none()
        if kh is None:
            kh = Customer(code=ma, name=ten, address=dia_chi, phone=sdt,
                          contact_name=nguoi, payment_term_days=30)
            db.add(kh)
            db.flush()
            print(f"  + khách {ma} — {ten}")
        else:
            print(f"  = khách {ma} đã có")
        ra[ma] = kh
    return ra


def _vai(db, ten: str, phong_id, quyen: dict) -> Role:
    """Vai có ô `giao_hang` khai sẵn. Get-or-create theo (tên, phòng)."""
    r = db.execute(
        select(Role).where(Role.name == ten, Role.department_id == phong_id)
    ).scalar_one_or_none()
    if r is None:
        r = Role(name=ten, department_id=phong_id)
        db.add(r)
        db.flush()
        print(f"  + vai {ten}")
    else:
        print(f"  = vai {ten} đã có")
    RoleRepository(db).set_permission(role_id=r.id, module_key="giao_hang", **quyen)
    return r


def _tai_xe(db) -> None:
    phong = db.execute(select(Department)).scalars().first()
    phong_id = phong.id if phong is not None else None
    vai = _vai(db, "Tài xế giao hàng", phong_id, VAI_TAI_XE)
    users = UserRepository(db)

    for ma, ten, username in TAI_XE:
        u = users.get_by_username(username)
        if u is None:
            u = users.create(username=username, name=ten,
                             password_hash=hash_password(settings.default_user_password))
            users.set_assignment(u, department_id=phong_id, role_id=vai.id, is_active=True)
            print(f"  + tài khoản {username}")
        e = db.execute(select(Employee).where(Employee.code == ma)).scalar_one_or_none()
        if e is None:
            db.add(Employee(code=ma, full_name=ten, department_id=phong_id,
                            hire_date=date(2024, 1, 1), user_id=u.id))
            print(f"  + tài xế {ma} — {ten}")
        elif e.user_id is None:
            # Hồ sơ gieo từ lượt trước chưa nối tài khoản ⇒ nối bù, nếu không nó không lọt
            # vào ô chọn tài xế lúc phân công.
            e.user_id = u.id
            print(f"  ~ nối {ma} với tài khoản {username}")
        else:
            print(f"  = tài xế {ma} đã có")


def _thanh_pham(db, kho: KhoHang) -> None:
    """Nhập kho THÀNH PHẨM của các đơn vừa gieo.

    Danh mục thành phẩm KHÔNG khai ở đây nữa: từ mg 0203, chốt đơn là hệ tự khai
    (`OrderService.confirm()` → `khai_cho_don`), mã theo công thức `TP-<số đơn>-<id dòng>`. Script
    gọi ĐÚNG hàm đó thay vì tự dựng mã — dựng mã riêng là đúng cái sai của bản trước: sáu mặt
    hàng `TP-HOP-BANH`… không nối về đơn nào cả (xem docs/prd-thanh-pham.md §9).

    Còn NHẬP KHO thì vẫn phải làm: thiếu tồn thì ghi sổ phiếu xuất báo *"Lô … chỉ còn 0"*, và
    luồng tắc ở đúng bước cuối, sau khi tài xế đã tới kho.
    """
    for ma_don, _ma_kh, _dong in DON:
        o = db.execute(select(Order).where(Order.order_no == ma_don)).scalar_one_or_none()
        if o is None:
            continue
        for h in khai_cho_don(db, o):
            print(f"  + thành phẩm {h.ma} — {h.ten}")
            ma_lo = f"LOT-{h.ma}"
            lo = db.execute(select(StockLot).where(StockLot.ma_lo == ma_lo)).scalar_one_or_none()
            if lo is not None:
                print(f"      = đã có tồn {float(lo.sl_con_lai):g} {h.don_vi_gia or ''}")
                continue
            # Nhập DƯ 20% so với số đặt: chạy thử hay lập nhiều đợt giao, tồn khít quá thì tắc ở
            # đợt thứ hai và trông như lỗi phần mềm.
            dong_don = next((l for l in o.lines if l.id == h.order_line_id), None)
            sl = int(float(dong_don.qty) * 1.2) if dong_don is not None else 0
            db.add(StockLot(
                ma_lo=ma_lo, hang_loai="vat_tu", hang_id=h.id, kho_id=kho.id,
                ngay_nhap=date.today(), don_gia_nhap=0,
                sl_ban_dau=sl, sl_con_lai=sl, trang_thai=LOT_AVAILABLE,
            ))
            print(f"      + nhập kho {sl} {h.don_vi_gia or ''}")


def _don(db, khach: dict[str, Customer]) -> None:
    for ma_don, ma_kh, dong in DON:
        o = db.execute(select(Order).where(Order.order_no == ma_don)).scalar_one_or_none()
        if o is not None:
            print(f"  = đơn {ma_don} đã có")
            continue
        kh = khach[ma_kh]
        o = Order(
            order_no=ma_don,
            customer_id=kh.id,
            status=STATUS_ORDERED,
            vat_pct_estimate=8,
            # Bốn ô này là NGUỒN ĐIỀN SẴN của màn tạo yêu cầu giao hàng — có chúng thì Bán hàng
            # chỉ việc xác nhận, không phải gõ lại (PRD §5).
            delivery_committed_date=date.today() + timedelta(days=7),
            delivery_address=kh.address,
            delivery_contact_name=kh.contact_name,
            delivery_contact_phone=kh.phone,
            delivery_note="Giao giờ hành chính, gọi trước 30 phút.",
        )
        for mo_ta, sl, dvt, gia in dong:
            o.lines.append(OrderLine(
                description=mo_ta, qty=sl, don_vi_tinh=dvt,
                unit_price_snapshot=gia, line_total=sl * gia, vat_pct_estimate=8,
            ))
        db.add(o)
        db.flush()
        print(f"  + đơn {ma_don} — {kh.name} ({len(dong)} dòng)")


def main() -> None:
    db = SessionLocal()
    try:
        print("Gieo dữ liệu chạy thử Giao hàng:")
        _don_rac(db)
        kho = _kho(db)
        khach = _khach(db)
        _tai_xe(db)
        phong = db.execute(select(Department)).scalars().first()
        _vai(db, "Quản lý giao hàng", phong.id if phong is not None else None, VAI_QUAN_LY)
        # THỨ TỰ QUAN TRỌNG (mg 0203): đơn phải có TRƯỚC, vì thành phẩm nay do chính dòng đơn
        # sinh ra — mã `TP-<số đơn>-<id dòng>`. Bản cũ khai 6 mặt hàng mã tự đặt rồi mới dựng
        # đơn, nên hai bên chẳng dính gì nhau và kho không tra ngược về đơn nào được.
        _don(db, khach)
        _thanh_pham(db, kho)
        db.commit()

        mk = settings.default_user_password
        print("")
        print("Xong. Ba bước để chạy thử:")
        print("  1. Vai trò → gán vai 'Quản lý giao hàng' cho tài khoản bạn đang dùng, hoặc tự")
        print("     bật ô Giao hàng trên vai hiện tại (Xem · Thao tác · Lên kế hoạch · Nhân")
        print("     viên giao hàng · Huỷ, phạm vi Tất cả).")
        print("  2. Đơn hàng bán → mở DH-GH-01 → khối 'Giao hàng' ở cuối trang.")
        print("     Tích dòng hàng → CHỌN MẶT HÀNG KHO (gõ 'Hộp', 'Sách'… ra danh mục TP-*).")
        print("     Rồi Lên đơn giao → Gửi yêu cầu xuất kho (máy tự điền, không sửa được).")
        print("     Rồi sang màn Kho → Hộp yêu cầu → Lập phiếu → Ghi sổ.")
        print(f"  3. Tài xế đăng nhập: taixe1 hoặc taixe2 — mật khẩu {mk}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
