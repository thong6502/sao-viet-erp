"""Lệnh sản xuất (LSX) — service-level tests.

Luồng thật: đơn từ báo giá → thu đủ cọc → chốt → Sale "Chuyển xuống sản xuất" → Kế hoạch preview
→ tạo lệnh → sửa routing → đánh dấu sẵn sàng. Mỗi DÒNG ĐƠN đúng 1 lệnh, lệnh ngang hàng.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan
from app.models.customer import Customer
from app.models.lsx import TT_CHO_BO_SUNG, TT_NHAP, TT_SAN_SANG
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuThanhPham, PhieuTinhGia
from app.models.quotation import STATUS_ACCEPTED, Quote, QuoteItem, QuoteVersion
from app.models.user import User
from app.models.vat_lieu_kho import GiayNguyen
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.lsx_repo import LsxRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.lsx import LsxCongDoanIn, LsxUpdateIn
from app.schemas.order import OrderCreate, OrderDepositReceiptIn, OrderUpdate
from app.seed import seed_all
from app.services.accounting_service import AccountingService
from app.services.lsx_service import LsxConflict, LsxService, LsxValidationError
from app.services.order_service import OrderService
from app.services.sequence_service import SequenceService


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
def customer(db):
    c = Customer(code="KH-SX", name="KH Sản xuất")
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def orders(db):
    audit = AuditLogRepository(db)
    acc_repo = AccountingRepository(db)
    accounting = AccountingService(
        acc_repo, PurchaseRequestRepository(db), SupplierRepository(db), UserRepository(db),
        audit, SequenceService(DocumentSequenceRepository(db)),
    )
    return OrderService(OrderRepository(db), audit, QuotationRepository(db), db, acc_repo, accounting)


@pytest.fixture
def lsx_svc(db):
    return LsxService(
        db, LsxRepository(db), AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


# --- dựng dữ liệu nguồn -------------------------------------------------------
def _ptg_2_san_pham(db, *, sl_hop=20_000, sl_tem=35_000) -> PhieuTinhGia:
    """1 phiếu tính giá 2 sản phẩm (Hộp + Tem), mỗi sản phẩm có giấy + routing riêng."""
    giay = GiayNguyen(ma="G-IV350", ten="Ivory 350", gsm=350, don_gia=25_000, don_vi_gia="tan",
                      cong_thuc_gia="to_nguyen * dai_nguyen * rong_nguyen * dinh_luong * don_gia / 1000")
    db.add(giay)
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()
    cd_be = CongDoan(ma="CD-BE-T", ten="Bế", nhom="finishing", cong_thuc_gia="so_luong * don_gia")
    cd_dan = CongDoan(ma="CD-DAN-T", ten="Dán hộp", nhom="finishing", cong_thuc_gia="so_luong * don_gia")
    db.add_all([cd_be, cd_dan])
    db.flush()

    p = PhieuTinhGia(ma="PTG-TEST-0001", ten_san_pham="Bộ hộp + tem", so_luong=sl_hop)
    hop = PhieuThanhPhan(
        thu_tu=0, ten="Hộp bánh 500g", so_luong=sl_hop, don_vi_tinh="cái",
        dai_thanh_pham=200, rong_thanh_pham=150,
        giay_id=giay.id, kho_nguyen_dai=790, kho_nguyen_rong=1090,
        kho_in_dai=650, kho_in_rong=900, so_mau_a=4, so_mau_b=0, quy_cach_in="mot_mat",
        ghi_chu_ky_thuat="Canh màu như mẫu",
    )
    hop.thanh_phams.append(PhieuThanhPham(thu_tu=0, cong_doan_id=cd_in.id if cd_in else None,
                                          ten="In offset", don_gia=200))
    hop.thanh_phams.append(PhieuThanhPham(thu_tu=1, cong_doan_id=cd_be.id, ten="Bế", don_gia=50))
    hop.thanh_phams.append(PhieuThanhPham(thu_tu=2, cong_doan_id=cd_dan.id, ten="Dán hộp", don_gia=80))
    tem = PhieuThanhPhan(
        thu_tu=1, ten="Tem nhãn", so_luong=sl_tem, don_vi_tinh="cái",
        dai_thanh_pham=60, rong_thanh_pham=40,
        giay_id=giay.id, kho_nguyen_dai=790, kho_nguyen_rong=1090,
        kho_in_dai=650, kho_in_rong=900, so_mau_a=4, so_mau_b=0, quy_cach_in="mot_mat",
    )
    tem.thanh_phams.append(PhieuThanhPham(thu_tu=0, cong_doan_id=cd_be.id, ten="Bế", don_gia=30))
    p.thanh_phans.extend([hop, tem])
    db.add(p)
    db.commit()
    return p


def _quote_from_ptg(db, customer, ptg: PhieuTinhGia) -> Quote:
    q = Quote(quote_number="BG-SX", customer_id=customer.id, status=STATUS_ACCEPTED,
              phieu_tinh_gia_id=ptg.id)
    db.add(q)
    db.flush()
    v = QuoteVersion(quote_id=q.id, version_number=1, vat_percent=8)
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    for i, tp in enumerate(ptg.thanh_phans, start=1):
        net = 10_000_000
        db.add(QuoteItem(
            quote_version_id=v.id, line_no=i, product_type="hop", product_name=tp.ten,
            quantity=tp.so_luong, unit=tp.don_vi_tinh, phieu_thanh_phan_id=tp.id,
            selling_price=net, unit_price=net / tp.so_luong, vat_percent=8,
            vat_amount=net * 0.08, final_amount=net * 1.08, total_cost_snapshot=net * 0.8,
            margin_percent=20, accepted=True,
        ))
    db.commit()
    return q


def _don_da_chot(db, orders, admin, customer, ptg):
    """Đơn từ báo giá đã qua cổng chốt (đủ cọc + PO + ngày giao) — CHƯA chuyển xuống sản xuất."""
    q = _quote_from_ptg(db, customer, ptg)
    d = orders.create(actor=admin, scope="all",
                      payload=OrderCreate(source_type="bao_gia", quotation_id=q.id, deposit_pct=50))
    orders.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                               payload=OrderDepositReceiptIn(receipt_method="cash",
                                                             amount=d.deposit_required))
    orders.update(order_id=d.id, actor=admin, scope="all", payload=OrderUpdate(
        customer_po_no="PO-SX", delivery_committed_date=date.today() + timedelta(days=10),
    ))
    return orders.confirm(order_id=d.id, actor=admin, scope="all")


def _don_da_chuyen_sx(db, orders, admin, customer, ptg):
    """Đơn đã chốt + Sale đã bấm 'Chuyển xuống sản xuất' → nằm trong hàng chờ Kế hoạch."""
    d = _don_da_chot(db, orders, admin, customer, ptg)
    return orders.release_production(order_id=d.id, actor=admin, scope="all")


# ============================ Hàng chờ + preview ============================
def test_hang_cho_chi_hien_don_da_chuyen_va_con_no_lenh(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chot(db, orders, admin, customer, ptg)
    assert not any(r["order_id"] == d.id for r in lsx_svc.hang_cho())  # chốt rồi nhưng chưa chuyển

    orders.release_production(order_id=d.id, actor=admin, scope="all")

    row = next(r for r in lsx_svc.hang_cho() if r["order_id"] == d.id)
    assert row["so_dong"] == 2 and row["so_dong_co_lsx"] == 0

    lines = lsx_svc.preview(d.id)["lines"]
    lsx_svc.tao(order_id=d.id, order_line_ids=[l["order_line_id"] for l in lines], actor=admin)
    assert not any(r["order_id"] == d.id for r in lsx_svc.hang_cho())  # đủ lệnh → rời hàng chờ


def test_preview_bung_moi_dong_mot_lenh_du_kien(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    out = lsx_svc.preview(d.id)
    assert len(out["lines"]) == 2
    hop = out["lines"][0]
    assert hop["so_luong_dat"] == 20_000
    assert hop["so_to_ke_hoach"] > 0 and hop["so_con"] > 1     # engine bình bài ra con/tờ
    assert [r["ten"] for r in hop["routing"]][-2:] == ["Bế", "Dán hộp"]
    assert hop["quy_cach"]["giay_ten"] == "Ivory 350" and hop["quy_cach"]["gsm"] == 350
    assert hop["lsx_id"] is None


def test_preview_chan_don_chua_chuyen_xuong_san_xuat(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    q = _quote_from_ptg(db, customer, ptg)
    d = orders.create(actor=admin, scope="all",
                      payload=OrderCreate(source_type="bao_gia", quotation_id=q.id, deposit_pct=50))
    with pytest.raises(LsxConflict):
        lsx_svc.preview(d.id)


# ============================ Tạo lệnh ============================
def test_tao_moi_dong_mot_lenh_ngang_hang_va_copy_routing(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    created = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)

    assert len(created) == 2
    assert all(c.ma.startswith("LSX") for c in created)
    assert {c.lsx_goc_id for c in created} == {None}          # ngang hàng, không cha-con
    assert [c.order_line_id for c in created] == ids

    hop = created[0]
    assert [cd.ten for cd in hop.cong_doans] == ["In offset", "Bế", "Dán hộp"]
    assert hop.quy_cach_json["ghi_chu_ky_thuat"] == "Canh màu như mẫu"
    assert hop.so_luong_dat == 20_000 and hop.don_vi_tinh == "cái"
    assert hop.ban_giao_at is not None
    # đơn vị theo ranh giới xén: in/bế đếm TỜ, dán đếm CON
    dv = {cd.ten: cd.don_vi for cd in hop.cong_doans}
    assert dv["In offset"] == "to" and dv["Bế"] == "to" and dv["Dán hộp"] == "cai"
    dan = next(cd for cd in hop.cong_doans if cd.ten == "Dán hộp")
    assert float(dan.so_luong_ra) == 20_000


def test_tao_chan_trung_lenh_tren_cung_dong_don(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)
    with pytest.raises(LsxConflict):
        lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)
    # dòng còn lại vẫn tạo được → đơn không bị kẹt
    assert len(lsx_svc.tao(order_id=d.id, order_line_ids=ids[1:], actor=admin)) == 1


def test_tao_chan_don_chua_chuyen_va_dong_khong_thuoc_don(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chot(db, orders, admin, customer, ptg)
    with pytest.raises(LsxConflict):        # chốt rồi nhưng Sale chưa bấm chuyển xuống SX
        lsx_svc.tao(order_id=d.id, order_line_ids=[d.lines[0].id], actor=admin)

    orders.release_production(order_id=d.id, actor=admin, scope="all")
    with pytest.raises(LsxValidationError):  # id dòng không thuộc đơn
        lsx_svc.tao(order_id=d.id, order_line_ids=[d.lines[0].id, 999_999], actor=admin)


def test_so_luong_lay_tu_don_khong_lay_tu_phieu_tinh_gia(db, orders, lsx_svc, admin, customer):
    """SL lúc tính giá 20.000 nhưng đơn chốt 5.000 → số tờ tính theo ĐƠN; PTG không bị ghi đè."""
    from app.models.order import OrderLine

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ol = db.query(OrderLine).filter(OrderLine.order_id == d.id).order_by(OrderLine.id).first()
    ol.qty = 5_000
    db.commit()

    pv = next(l for l in lsx_svc.preview(d.id)["lines"] if l["order_line_id"] == ol.id)
    assert pv["so_luong_dat"] == 5_000
    assert pv["sl_ptg"] == 20_000                      # cảnh báo mềm cho kế hoạch
    to_5k = pv["so_to_ke_hoach"]

    [lsx] = lsx_svc.tao(order_id=d.id, order_line_ids=[ol.id], actor=admin)
    assert lsx.so_luong_dat == 5_000 and lsx.so_to_ke_hoach == to_5k

    tp = db.query(PhieuThanhPhan).filter(PhieuThanhPhan.id == ol.phieu_thanh_phan_id).first()
    assert tp.so_luong == 20_000                       # phiếu tính giá không bị sửa
    assert db.query(PhieuTinhGia).filter(PhieuTinhGia.id == tp.phieu_id).first().result_json is None


def test_dong_khong_co_phieu_tinh_gia_van_tao_duoc_lenh_o_cho_bo_sung(
    db, orders, lsx_svc, admin, customer
):
    """Dòng đơn không gắn phiếu tính giá (đơn nhập giá tay) → lệnh vẫn tạo được, quy cách trống,
    nằm ở CHỜ BỔ SUNG để kế hoạch tự khai."""
    from app.models.order import OrderLine

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ol = db.query(OrderLine).filter(OrderLine.order_id == d.id).order_by(OrderLine.id).first()
    ol.phieu_thanh_phan_id = None
    db.commit()

    pv = next(l for l in lsx_svc.preview(d.id)["lines"] if l["order_line_id"] == ol.id)
    assert "khong_co_ptg" in pv["thieu"] and pv["routing"] == []
    [lsx] = lsx_svc.tao(order_id=d.id, order_line_ids=[ol.id], actor=admin)
    assert lsx.trang_thai == TT_CHO_BO_SUNG and lsx.so_luong_dat == ol.qty
    assert lsx.cong_doans == []


# ============================ Sửa routing / trạng thái ============================
def test_sua_routing_khong_dung_phieu_tinh_gia_va_khong_anh_huong_lenh_khac(
    db, orders, lsx_svc, admin, customer
):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop, tem = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    tem_truoc = [cd.ten for cd in tem.cong_doans]

    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten="In offset", nhom="print", so_luong_vao=5300, so_luong_ra=5250, don_vi="to"),
        LsxCongDoanIn(ten="Cán màng", nhom="finishing", so_luong_vao=5250, so_luong_ra=5200, don_vi="to"),
        LsxCongDoanIn(ten="Bế", nhom="finishing", so_luong_vao=5200, so_luong_ra=5200, don_vi="to"),
        LsxCongDoanIn(ten="Dán hộp", nhom="finishing", so_luong_vao=20500, so_luong_ra=20000,
                      don_vi="cai", thue_ngoai=True, nha_cung_cap="Cơ sở Tân Bình"),
    ])
    hop2 = lsx_svc.get(hop.id)
    assert [cd.ten for cd in hop2.cong_doans] == ["In offset", "Cán màng", "Bế", "Dán hộp"]
    assert hop2.cong_doans[-1].thue_ngoai is True
    assert [cd.thu_tu for cd in hop2.cong_doans] == [0, 1, 2, 3]

    assert [cd.ten for cd in lsx_svc.get(tem.id).cong_doans] == tem_truoc      # lệnh khác nguyên vẹn
    tp = db.query(PhieuThanhPhan).filter(PhieuThanhPhan.id == hop.phieu_thanh_phan_id).first()
    assert [r.ten for r in tp.thanh_phams] == ["In offset", "Bế", "Dán hộp"]   # PTG nguyên vẹn


def test_san_sang_bi_chan_khi_con_thieu_va_mo_khi_du(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    [hop, _tem] = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)

    # có công đoạn Bế mà chưa gán khuôn → CHỜ BỔ SUNG
    assert hop.trang_thai == TT_CHO_BO_SUNG
    assert "thieu_khuon" in lsx_svc.thieu_cua(hop)
    with pytest.raises(LsxConflict):
        lsx_svc.set_trang_thai(lsx_id=hop.id, trang_thai=TT_SAN_SANG, actor=admin)

    from app.models.khuon_be import KhuonBe

    khuon = KhuonBe(ma="KB-01", ten="Khuôn hộp 200x150")
    db.add(khuon)
    db.commit()
    hop = lsx_svc.update(lsx_id=hop.id, actor=admin, payload=LsxUpdateIn(khuon_be_id=khuon.id))
    assert hop.trang_thai == TT_NHAP and lsx_svc.thieu_cua(hop) == []
    assert lsx_svc.set_trang_thai(lsx_id=hop.id, trang_thai=TT_SAN_SANG, actor=admin).trang_thai == TT_SAN_SANG


def test_xoa_lenh_tra_dong_don_ve_hang_cho(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    created = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    assert not any(r["order_id"] == d.id for r in lsx_svc.hang_cho())

    assert lsx_svc.xoa(lsx_id=created[0].id, actor=admin) == d.id
    row = next(r for r in lsx_svc.hang_cho() if r["order_id"] == d.id)
    assert row["so_dong_co_lsx"] == 1 and row["so_dong"] == 2
    assert lsx_svc.preview(d.id)["lines"][0]["lsx_id"] is None   # dòng mở lại để tạo lệnh mới
