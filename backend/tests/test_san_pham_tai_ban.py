"""Sản phẩm tái bản (docs/spec-san-pham-tai-ban.md) — snapshot tự động lúc Chốt đơn + tra cứu.

Service-level tests, cùng phong cách `test_orders_api.py`: dựng DB in-memory, chạy OrderService
thật cho phần chốt đơn, gọi thẳng `san_pham_tai_ban_service` cho phần tìm/đọc chi tiết.
"""
from __future__ import annotations

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.customer import Customer
from app.models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia, PhieuVatTu, SanPhamTaiBan
from app.models.quotation import STATUS_ACCEPTED, Quote, QuoteItem, QuoteVersion
from app.models.user import User
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.order import OrderCreate, OrderDepositReceiptIn, OrderUpdate
from app.seed import seed_all
from app.services import san_pham_tai_ban_service
from app.services.accounting_service import AccountingService
from app.services.order_service import OrderService, OrderValidationError
from app.services.sequence_service import SequenceService
from datetime import date


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    run_migrations(s)
    seed_all(s)
    yield s
    s.close()


@pytest.fixture
def admin(db):
    return db.query(User).filter(User.username == "admin").first()


@pytest.fixture
def svc(db):
    audit = AuditLogRepository(db)
    accounting_repo = AccountingRepository(db)
    accounting = AccountingService(
        accounting_repo,
        PurchaseRequestRepository(db),
        SupplierRepository(db),
        UserRepository(db),
        audit,
        SequenceService(DocumentSequenceRepository(db)),
    )
    return OrderService(
        OrderRepository(db), audit, QuotationRepository(db), db, accounting_repo, accounting
    )


def _customer(db, code="KH-T"):
    c = Customer(code=code, name=f"KH {code}")
    db.add(c)
    db.commit()
    return c


_ma_seq = 0


def _thanh_phan(db, *, ten="Card visit 350gsm", giay_id=101, may_id=201) -> PhieuThanhPhan:
    """Dựng 1 PhieuTinhGia + 1 PhieuThanhPhan (kèm 2 công đoạn + 1 vật tư) — nguồn để snapshot."""
    global _ma_seq
    _ma_seq += 1
    p = PhieuTinhGia(ma=f"PTG-T-{_ma_seq:04d}", ten_san_pham=ten, so_luong=1000)
    db.add(p)
    db.flush()
    tp = PhieuThanhPhan(
        phieu_id=p.id, thu_tu=0, loai_thanh_phan="to_roi", ten=ten,
        dai_thanh_pham=90, rong_thanh_pham=54, so_luong=1000, don_vi_tinh="cái",
        giay_id=giay_id, kho_nguyen="65x86", kho_nguyen_dai=650, kho_nguyen_rong=860,
        don_gia_giay=25000, don_gia_don_vi="to", nguon_giay="cong_ty",
        co_in=True, quy_cach_in="hai_mat", kho_in_dai=430, kho_in_rong=650,
        so_con=8, con_auto=True, may_id=may_id, don_gia_cong_in=500,
        muc_a=["C", "M", "Y", "K"], muc_b=["C", "M", "Y", "K"],
        so_mau_a=4, so_mau_b=4, gia_von_tp=1_234_000,
    )
    db.add(tp)
    db.flush()
    tp.thanh_phams.append(PhieuThanhPham(
        thanh_phan_id=tp.id, thu_tu=1, cong_doan_id=301, ten="Cán màng", don_gia=200,
        so_mat=1, phi_khuon=0, ghi_chu="mờ",
    ))
    tp.thanh_phams.append(PhieuThanhPham(
        thanh_phan_id=tp.id, thu_tu=0, cong_doan_id=300, ten="Cắt xén", don_gia=100,
        so_mat=1, phi_khuon=50_000,
    ))
    tp.vat_tus.append(PhieuVatTu(thanh_phan_id=tp.id, thu_tu=0, vat_tu_id=401, ten="Keo dán", don_gia=300))
    db.commit()
    db.refresh(tp)
    return tp


def _quote_for(db, customer, tp: PhieuThanhPhan | None, *, qty=1000) -> Quote:
    q = Quote(quote_number=f"BG-{tp.id if tp else 'X'}-{customer.id}", customer_id=customer.id, status=STATUS_ACCEPTED)
    db.add(q)
    db.flush()
    v = QuoteVersion(quote_id=q.id, version_number=1, vat_percent=8)
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    db.add(QuoteItem(
        quote_version_id=v.id, line_no=1, product_type="tr", product_name=tp.ten if tp else "SP tay",
        quantity=qty, unit="cái", selling_price=1_000_000, discount_amount=0,
        unit_price=1_000_000 / qty, vat_percent=8, vat_amount=80_000,
        final_amount=1_080_000, total_cost_snapshot=600_000, margin_percent=20,
        phieu_thanh_phan_id=tp.id if tp else None,
    ))
    db.commit()
    return q


def _confirm_ready_order(svc, db, admin, quote):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(quotation_id=quote.id))
    svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                             payload=OrderDepositReceiptIn(receipt_method="bank_transfer", amount=1_080_000))
    svc.update(order_id=d.id, actor=admin, scope="all",
               payload=OrderUpdate(customer_po_no="PO1", delivery_committed_date=date.today()))
    return d


def test_confirm_creates_full_snapshot(svc, admin, db):
    cust = _customer(db)
    tp = _thanh_phan(db)
    q = _quote_for(db, cust, tp)
    d = _confirm_ready_order(svc, db, admin, q)
    out = svc.confirm(order_id=d.id, actor=admin, scope="all")
    assert out.status == "ordered"

    row = db.query(SanPhamTaiBan).filter(SanPhamTaiBan.ten_chuan_hoa == san_pham_tai_ban_service.chuan_hoa_ten(tp.ten)).one()
    cfg = row.cau_hinh_json
    assert cfg["ten"] == tp.ten
    assert cfg["giay_id"] == 101 and cfg["may_id"] == 201
    assert cfg["dai_thanh_pham"] == 90 and cfg["rong_thanh_pham"] == 54
    assert cfg["muc_a"] == ["C", "M", "Y", "K"]
    # Công đoạn giữ ĐÚNG THỨ TỰ (thu_tu 0 rồi 1), dù insert ngược.
    assert [c["ten"] for c in cfg["thanh_phams"]] == ["Cắt xén", "Cán màng"]
    assert cfg["thanh_phams"][1]["phi_khuon"] == 0
    assert cfg["thanh_phams"][0]["phi_khuon"] == 50_000
    assert cfg["vat_tus"][0]["ten"] == "Keo dán"
    # KHÔNG lưu: SL của đơn cũ, giá vốn đã tính, số bài in/số màu dẫn xuất.
    assert cfg.get("so_luong") is None
    assert cfg.get("so_to_per_sp") is None
    assert cfg.get("so_mau_a") is None and cfg.get("so_mau_b") is None


def test_confirm_multiple_products_each_saved(svc, admin, db):
    cust = _customer(db)
    tp1 = _thanh_phan(db, ten="Hộp cứng A")
    tp2 = _thanh_phan(db, ten="Hộp cứng B", giay_id=102, may_id=202)
    q = Quote(quote_number="BG-multi", customer_id=cust.id, status=STATUS_ACCEPTED)
    db.add(q)
    db.flush()
    v = QuoteVersion(quote_id=q.id, version_number=1, vat_percent=8)
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    for i, tp in enumerate((tp1, tp2), start=1):
        db.add(QuoteItem(
            quote_version_id=v.id, line_no=i, product_type="tr", product_name=tp.ten,
            quantity=500, unit="cái", selling_price=500_000, discount_amount=0,
            unit_price=1000, vat_percent=8, vat_amount=40_000, final_amount=540_000,
            total_cost_snapshot=300_000, margin_percent=20, phieu_thanh_phan_id=tp.id,
        ))
    db.commit()
    d = _confirm_ready_order(svc, db, admin, q)
    svc.confirm(order_id=d.id, actor=admin, scope="all")
    assert db.query(SanPhamTaiBan).count() == 2


def test_confirm_overwrites_same_name_regardless_of_customer(svc, admin, db):
    cust_a = _customer(db, "KH-A")
    cust_b = _customer(db, "KH-B")
    tp1 = _thanh_phan(db, ten="Tờ rơi A5", giay_id=101)
    d1 = _confirm_ready_order(svc, db, admin, _quote_for(db, cust_a, tp1))
    svc.confirm(order_id=d1.id, actor=admin, scope="all")

    tp2 = _thanh_phan(db, ten="Tờ rơi A5", giay_id=102)   # tên GIỐNG hệt, giấy khác, khách khác
    d2 = _confirm_ready_order(svc, db, admin, _quote_for(db, cust_b, tp2))
    svc.confirm(order_id=d2.id, actor=admin, scope="all")

    rows = db.query(SanPhamTaiBan).filter(
        SanPhamTaiBan.ten_chuan_hoa == san_pham_tai_ban_service.chuan_hoa_ten("Tờ rơi A5")
    ).all()
    assert len(rows) == 1   # ghi đè, không nhân đôi
    assert rows[0].cau_hinh_json["giay_id"] == 102   # cấu hình của lần chốt SAU


def test_confirm_without_phieu_thanh_phan_id_still_confirms(svc, admin, db):
    cust = _customer(db)
    q = _quote_for(db, cust, None)   # dòng báo giá KHÔNG gắn PTG (nhập tay)
    d = _confirm_ready_order(svc, db, admin, q)
    out = svc.confirm(order_id=d.id, actor=admin, scope="all")
    assert out.status == "ordered"
    assert db.query(SanPhamTaiBan).count() == 0


def test_confirm_rejects_and_rolls_back_when_source_deleted(svc, admin, db):
    cust = _customer(db)
    tp = _thanh_phan(db, ten="Sẽ bị xoá")
    q = _quote_for(db, cust, tp)
    d = _confirm_ready_order(svc, db, admin, q)
    db.delete(tp)
    db.commit()
    with pytest.raises(OrderValidationError):
        svc.confirm(order_id=d.id, actor=admin, scope="all")
    fresh = svc.get(order_id=d.id, actor=admin, scope="all")
    assert fresh.status == "draft"   # KHÔNG chốt nửa vời
    assert db.query(SanPhamTaiBan).count() == 0


def test_tim_kiem_bo_dau_va_lay_chi_tiet(svc, admin, db):
    cust = _customer(db)
    tp = _thanh_phan(db, ten="Áo thun cotton")
    d = _confirm_ready_order(svc, db, admin, _quote_for(db, cust, tp))
    svc.confirm(order_id=d.id, actor=admin, scope="all")

    goi_y = san_pham_tai_ban_service.tim_kiem(db, "ao thun")   # gõ KHÔNG dấu
    assert any(r.ten == "Áo thun cotton" for r in goi_y)

    row = next(r for r in goi_y if r.ten == "Áo thun cotton")
    chi_tiet = san_pham_tai_ban_service.lay_chi_tiet(db, row.id)
    assert chi_tiet is not None
    assert chi_tiet.cau_hinh_json["ten"] == "Áo thun cotton"
    assert chi_tiet.cau_hinh_json["giay_id"] == 101
