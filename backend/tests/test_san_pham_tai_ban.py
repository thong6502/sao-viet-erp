"""Sản phẩm tái bản (docs/spec-san-pham-tai-ban.md) — snapshot tự động lúc Chốt đơn + tra cứu.

Service-level tests, cùng phong cách `test_orders_api.py`: dựng DB in-memory, chạy OrderService
thật cho phần chốt đơn, gọi thẳng `san_pham_tai_ban_service` cho phần tìm/đọc chi tiết.
"""
from __future__ import annotations

import pytest

from tests.conftest import phien_da_seed

from app.models.customer import Customer
from app.models.phieu_tinh_gia import (
    PhieuChiPhiKhac, PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia, PhieuVatTu, SanPhamTaiBan,
)
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
from app.services import san_pham_tai_ban_service
from app.services.accounting_service import AccountingService
from app.services.order_service import OrderService, OrderValidationError
from app.services.sequence_service import SequenceService
from datetime import date


@pytest.fixture
def db():
    yield from phien_da_seed()


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


def _thanh_phan(db, *, ten="Card visit 350gsm", giay_id=101, may_id=201, phi_giao_hang=0,
                chi_phi_khac: list[tuple[str, float]] | None = None) -> PhieuThanhPhan:
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
        so_mau_a=4, so_mau_b=4, gia_von_tp=1_234_000, phi_giao_hang=phi_giao_hang,
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
    for i, (ten_cp, tien_cp) in enumerate(chi_phi_khac or []):
        tp.chi_phi_khacs.append(PhieuChiPhiKhac(
            thanh_phan_id=tp.id, thu_tu=i, ten=ten_cp, so_tien=tien_cp))
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


def test_snapshot_giu_phi_giao_hang(svc, admin, db):
    """Tái bản nạp lại NGUYÊN cấu hình — bỏ sót phí giao hàng thì đơn tái bản tự nhiên rẻ đi một
    khoản mà không ai được báo."""
    cust = _customer(db, code="KH-GH")
    tp = _thanh_phan(db, ten="Hộp giao tận nơi", phi_giao_hang=750_000)
    q = _quote_for(db, cust, tp)
    d = _confirm_ready_order(svc, db, admin, q)
    svc.confirm(order_id=d.id, actor=admin, scope="all")

    row = db.query(SanPhamTaiBan).filter(
        SanPhamTaiBan.ten_chuan_hoa == san_pham_tai_ban_service.chuan_hoa_ten(tp.ten)
    ).one()
    assert row.cau_hinh_json["phi_giao_hang"] == 750_000


def test_snapshot_giu_chi_phi_khac(svc, admin, db):
    """Khoản lẻ tự khai (làm kẽm, phí thiết kế) cũng phải theo mẫu tái bản — cả TÊN lẫn tiền, vì
    cái tên gõ tay là thứ duy nhất nói được khoản ấy là gì."""
    cust = _customer(db, code="KH-CPK")
    tp = _thanh_phan(db, ten="Hộp có kẽm ngoài",
                     chi_phi_khac=[("làm kẽm", 800_000), ("phí thiết kế", 1_500_000)])
    q = _quote_for(db, cust, tp)
    d = _confirm_ready_order(svc, db, admin, q)
    svc.confirm(order_id=d.id, actor=admin, scope="all")

    row = db.query(SanPhamTaiBan).filter(
        SanPhamTaiBan.ten_chuan_hoa == san_pham_tai_ban_service.chuan_hoa_ten(tp.ten)
    ).one()
    assert [(c["ten"], c["so_tien"]) for c in row.cau_hinh_json["chi_phi_khacs"]] == [
        ("làm kẽm", 800_000), ("phí thiết kế", 1_500_000),
    ]


def test_snapshot_giu_nguon_khuon(svc, admin, db):
    """Sale đã trả lời "khuôn có sẵn hay làm mới" thì tái bản phải nạp lại đúng câu trả lời đó.
    Mất nó thì thẻ nạp ra còn 800.000đ phí khuôn mà không nút nào được chọn, ô tiền ẩn, và lệnh
    xuống xưởng không còn so được ý sale với con dao kế hoạch chốt."""
    cust = _customer(db, code="KH-KN")
    tp = _thanh_phan(db, ten="Hộp bế dao mới")
    tp.thanh_phams[0].khuon_nguon = "lam_moi"   # Cắt xén, phi_khuon 50.000
    tp.thanh_phams[1].khuon_nguon = "co_san"    # Cán màng, phi_khuon 0
    db.commit()
    d = _confirm_ready_order(svc, db, admin, _quote_for(db, cust, tp))
    svc.confirm(order_id=d.id, actor=admin, scope="all")

    row = db.query(SanPhamTaiBan).filter(
        SanPhamTaiBan.ten_chuan_hoa == san_pham_tai_ban_service.chuan_hoa_ten(tp.ten)
    ).one()
    assert [(c["ten"], c["phi_khuon"], c["khuon_nguon"]) for c in row.cau_hinh_json["thanh_phams"]] == [
        ("Cắt xén", 50_000, "lam_moi"), ("Cán màng", 0, "co_san"),
    ]


def _chuan(v):
    """Numeric của DB về float để so với JSON của ảnh chụp."""
    from decimal import Decimal

    return float(v) if isinstance(v, Decimal) else v


def _so_du_o(cfg: dict, nguon, schema, bo_qua: set[str], cap: str) -> None:
    for ten_o in schema.model_fields:
        if ten_o in bo_qua:
            continue
        gia_tri = _chuan(getattr(nguon, ten_o))
        # Ô mới thêm vào schema mà test chưa điền thì nguồn là None, ảnh chụp bỏ sót cũng ra None —
        # so bằng nhau là lọt. Bắt người thêm cột điền giá trị ở đây.
        assert gia_tri is not None, f"{cap}.{ten_o}: điền giá trị khác None cho ô này trong test"
        assert cfg.get(ten_o) == gia_tri, f"ảnh chụp tái bản bỏ sót {cap}.{ten_o}"


def test_snapshot_chep_du_moi_o_nhap(db):
    """Chặn tái phát: hàm chụp liệt kê TAY từng ô, nên thêm ô nhập mới mà quên chép là tái bản
    nạp thiếu im lặng (đã xảy ra với `khuon_nguon`, thêm 04/09 sau khi hàm chụp viết 30/08).
    Test đi theo schema đầu vào: schema có ô nào thì ảnh chụp phải có đúng giá trị ô đó, trừ các
    ô CỐ Ý bỏ (số lượng của đơn cũ + số dẫn xuất engine tự tính lại)."""
    p = PhieuTinhGia(ma="PTG-T-DU-O", ten_san_pham="Hộp đủ ô", so_luong=1000)
    db.add(p)
    db.flush()
    tp = PhieuThanhPhan(
        phieu_id=p.id, thu_tu=0, loai_thanh_phan="hop", ten="Hộp đủ ô",
        dai_thanh_pham=90.5, rong_thanh_pham=54.5, so_trang=4, trang_moi_tay=2, so_luong=1000,
        don_vi_tinh="hộp", nhom_bao_gia="Bộ hộp", dvt_nhom="bộ", loai_san_pham_id=7,
        giay_id=101, kho_nguyen="65x86", kho_nguyen_dai=650, kho_nguyen_rong=860,
        don_gia_giay=25000, don_gia_don_vi="kg", nguon_giay="khach", chua_nhip=12,
        bleed_mm=3, khe_cat_mm=2, co_in=False, che_ban_loai="ctp", che_ban_don_gia=150_000,
        quy_cach_in="tu_tro", kho_in_dai=430, kho_in_rong=650, so_con=8, con_auto=False,
        may_id=201, don_gia_cong_in=500, muc_a=["C", "M"], muc_b=["K"],
        ghi_chu_ky_thuat="canh màu như mẫu", phi_giao_hang=750_000,
    )
    db.add(tp)
    db.flush()
    tp.thanh_phams.append(PhieuThanhPham(
        thanh_phan_id=tp.id, thu_tu=0, cong_doan_id=300, ten="Bế", don_gia=100, bu_hao=True,
        so_mat=2, so_vi_tri=3, dien_tich=12.5, nha_cung_cap="Xưởng khuôn A", ghi_chu="dao sắc",
        phi_khuon=800_000, khuon_nguon="lam_moi", dai_khuon=100, rong_khuon=50, so_khuon=2,
    ))
    tp.vat_tus.append(PhieuVatTu(
        thanh_phan_id=tp.id, thu_tu=0, vat_tu_id=401, ten="Keo dán", don_gia=300, ghi_chu="keo sữa",
    ))
    tp.chi_phi_khacs.append(PhieuChiPhiKhac(thanh_phan_id=tp.id, thu_tu=0, ten="làm kẽm", so_tien=800_000))
    db.commit()
    db.refresh(tp)

    from app.schemas.phieu_tinh_gia import ChiPhiKhacIn, ThanhPhamIn, ThanhPhanIn, VatTuLineIn

    cfg = san_pham_tai_ban_service._cau_hinh_tu_thanh_phan(tp)
    _so_du_o(cfg, tp, ThanhPhanIn, {
        "thu_tu", "so_luong", "so_to_per_sp", "so_mau_a", "so_mau_b", "so_mau_pha",
        "thanh_phams", "vat_tus", "chi_phi_khacs",
    }, "san_pham")
    # `so_luong` của bước/vật tư: "0 = dùng SL đặt" — cùng lẽ SL của đơn cũ, màn Tính giá cũng không
    # có ô nào sửa nó.
    _so_du_o(cfg["thanh_phams"][0], tp.thanh_phams[0], ThanhPhamIn, {"thu_tu", "so_luong"}, "cong_doan")
    _so_du_o(cfg["vat_tus"][0], tp.vat_tus[0], VatTuLineIn, {"thu_tu", "so_luong"}, "vat_tu")
    _so_du_o(cfg["chi_phi_khacs"][0], tp.chi_phi_khacs[0], ChiPhiKhacIn, {"thu_tu"}, "chi_phi_khac")
