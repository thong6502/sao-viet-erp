"""Lệnh sản xuất (LSX) — service-level tests.

Luồng thật: đơn từ báo giá → thu đủ cọc → chốt → Sale "Chuyển xuống sản xuất" → Kế hoạch preview
→ tạo lệnh → sửa routing → đánh dấu sẵn sàng. Mỗi DÒNG ĐƠN đúng 1 lệnh, lệnh ngang hàng.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import ceil

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan, CongDoanDauViec
from app.models.customer import Customer
from app.models.department import Department
from app.models.lsx import TT_CHO_BO_SUNG, TT_NHAP, TT_SAN_SANG, LsxCongDoan
from app.models.may_thiet_bi import MayThietBi
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuThanhPham, PhieuTinhGia
from app.models.quotation import STATUS_ACCEPTED, Quote, QuoteItem, QuoteVersion
from app.models.user import User
from app.models.vat_lieu_kho import GiayNguyen, VatTuInAn
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
from app.services.lsx_service import (
    LsxConflict,
    LsxService,
    LsxValidationError,
    thoi_luong_buoc,
)
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
def _to_san_xuat(db) -> Department:
    """Một tổ sản xuất để gán cho công đoạn — §12 đòi bước NỘI BỘ phải biết ai làm.

    TỰ DỰNG nếu seed chưa có: fixture không được phụ thuộc vào seed có sẵn tổ nào, nếu không
    test sẽ đỏ/xanh theo dữ liệu mẫu chứ không theo code.
    """
    to = db.query(Department).filter(Department.la_san_xuat.is_(True)).first()
    if to is None:
        to = Department(name="Tổ In test", code="TO-IN-T", la_san_xuat=True)
        db.add(to)
        db.flush()
    return to


def _may_in(db) -> MayThietBi:
    """Máy in có tốc độ + thời gian rửa mực → routing kế thừa được năng suất/vệ sinh."""
    may = MayThietBi(
        ma="MAY-IN-T", ten="Máy in 4 màu", loai_may="press_offset_sheet",
        toc_do=5_000, don_vi_toc_do="to_gio", thoi_gian_rua_muc=15,
        kho_max_dai=1020, kho_max_rong=720,
    )
    db.add(may)
    db.flush()
    return may


def _ptg_2_san_pham(db, *, sl_hop=20_000, sl_tem=35_000) -> PhieuTinhGia:
    """1 phiếu tính giá 2 sản phẩm (Hộp + Tem), mỗi sản phẩm có giấy + routing riêng."""
    giay = GiayNguyen(ma="G-IV350", ten="Ivory 350", gsm=350, don_gia=25_000, don_vi_gia="tan",
                      cong_thuc_gia="to_nguyen * dai_nguyen * rong_nguyen * dinh_luong * don_gia / 1000")
    db.add(giay)
    to_id = _to_san_xuat(db).id
    may = _may_in(db)
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()
    if cd_in is None:
        cd_in = CongDoan(ma="CD-IN-T", ten="In offset", nhom="print",
                         cong_thuc_gia="so_luong * don_gia")
        db.add(cd_in)
    cd_in.department_id = cd_in.department_id or to_id
    cd_in.setup_time = 45          # chuẩn bị máy in 45 phút
    # Đơn vị KHAI ở danh mục — lệnh chỉ kế thừa. Không khai = bước không chạm giấy (chế bản).
    cd_in.don_vi_vao = cd_in.don_vi_ra = "to"
    db.flush()
    # Đơn vị vào/ra là KHAI BÁO, không suy từ tên: bế = ranh giới tờ in → con, dán hộp đếm con.
    cd_be = CongDoan(ma="CD-BE-T", ten="Bế", nhom="finishing", cong_thuc_gia="so_luong * don_gia",
                     department_id=to_id, setup_time=30, don_vi_vao="to", don_vi_ra="cai")
    # Dán hộp = bước LÀM TAY: không gắn máy, nên năng suất phải tới từ danh mục công đoạn.
    # `spoilage_pct=2` để nguyên làm bằng chứng NGƯỢC: routing không được kế thừa nó (module Bù hao
    # đã lo phần hao) — xem assert `hao_hut_pct == 0` ở test kế thừa mặc định.
    cd_dan = CongDoan(ma="CD-DAN-T", ten="Dán hộp", nhom="finishing",
                      cong_thuc_gia="so_luong * don_gia", department_id=to_id, spoilage_pct=2,
                      nang_suat=4000, don_vi_vao="cai", don_vi_ra="cai")
    db.add_all([cd_be, cd_dan])
    db.flush()

    p = PhieuTinhGia(ma="PTG-TEST-0001", ten_san_pham="Bộ hộp + tem", so_luong=sl_hop)
    hop = PhieuThanhPhan(
        thu_tu=0, ten="Hộp bánh 500g", so_luong=sl_hop, don_vi_tinh="cái",
        dai_thanh_pham=200, rong_thanh_pham=150,
        giay_id=giay.id, kho_nguyen_dai=790, kho_nguyen_rong=1090,
        kho_in_dai=650, kho_in_rong=900, so_mau_a=4, so_mau_b=0, quy_cach_in="mot_mat",
        ghi_chu_ky_thuat="Canh màu như mẫu", may_id=may.id,
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
    # Đơn vị theo ranh giới xén: in đếm TỜ; BẾ là chỗ ĐỔI đơn vị tờ→con (hệ số = con/tờ);
    # sau bế đếm CON.
    dv = {cd.ten: (cd.don_vi_vao, cd.don_vi_ra) for cd in hop.cong_doans}
    assert dv["In offset"] == ("to", "to")
    assert dv["Bế"] == ("to", "cai")
    assert dv["Dán hộp"] == ("cai", "cai")
    be = next(cd for cd in hop.cong_doans if cd.ten == "Bế")
    assert float(be.he_so_quy_doi) == float(hop.so_con) > 1
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
    # Chưa có bài tính giá → số dẫn xuất là "chưa tính được" = None (UI hiện "—"), KHÔNG bày 0/1 giả.
    assert pv["bu_hao_to"] is None and pv["so_to_ke_hoach"] is None and pv["so_to_nguyen"] is None
    assert pv["so_con"] is None and pv["so_kem"] is None and pv["so_luot"] is None
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
        LsxCongDoanIn(ten="In offset", nhom="print", so_luong_vao=5300, so_luong_ra=5250,
                      don_vi_vao="to"),
        LsxCongDoanIn(ten="Cán màng", nhom="finishing", so_luong_vao=5250, so_luong_ra=5200,
                      don_vi_vao="to"),
        LsxCongDoanIn(ten="Bế", nhom="finishing", so_luong_vao=5200, so_luong_ra=5200,
                      don_vi_vao="to"),
        LsxCongDoanIn(ten="Dán hộp", nhom="finishing", so_luong_vao=20500, so_luong_ra=20000,
                      don_vi_vao="cai", loai_buoc="thue_ngoai", nha_cung_cap="Cơ sở Tân Bình"),
    ])
    hop2 = lsx_svc.get(hop.id)
    assert [cd.ten for cd in hop2.cong_doans] == ["In offset", "Cán màng", "Bế", "Dán hộp"]
    assert hop2.cong_doans[-1].loai_buoc == "thue_ngoai"
    # Đơn vị KHÔNG nhận từ client nữa: nó kế thừa từ danh mục công đoạn. Bốn dòng trên đều là
    # bước tự thêm (không `cong_doan_id`) nên nối tiếp đơn vị bước trước — pass-through "to",
    # KHÔNG phải "cai" mà client gửi.
    assert hop2.cong_doans[-1].don_vi_ra == "to"
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
    assert lsx_svc.thieu_cua(hop) == [] and hop.trang_thai == TT_NHAP
    assert lsx_svc.set_trang_thai(lsx_id=hop.id, trang_thai=TT_SAN_SANG, actor=admin).trang_thai == TT_SAN_SANG


def test_xoa_lenh_tra_dong_don_ve_hang_cho(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    created = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    assert not any(r["order_id"] == d.id for r in lsx_svc.hang_cho())

    xoa_id = created[0].id
    assert lsx_svc.xoa(lsx_id=xoa_id, actor=admin) == d.id
    row = next(r for r in lsx_svc.hang_cho() if r["order_id"] == d.id)
    assert row["so_dong_co_lsx"] == 1 and row["so_dong"] == 2
    # Công đoạn phải đi theo lệnh. SQLite dev TẮT `PRAGMA foreign_keys`, nên nếu giao việc xoá
    # con cho DB thì chúng thành mồ côi — lệnh mới TÁI DÙNG id sẽ nhận nhầm routing đã xoá.
    from sqlalchemy import text as _sql

    con_lai = db.execute(
        _sql("SELECT COUNT(*) FROM lsx_cong_doan WHERE lsx_id = :i"), {"i": xoa_id}
    ).scalar()
    assert con_lai == 0
    assert lsx_svc.preview(d.id)["lines"][0]["lsx_id"] is None   # dòng mở lại để tạo lệnh mới


# ================= Khoán theo đầu việc ở bước lệnh =================
def _don_gia_khoan(db, *, department_id: int, ten: str, don_vi: str, don_gia: float):
    """1 dòng bảng CÔNG KHOÁN của tổ. Đơn giá chỉ treo vào TỔ — bảng khai báo không biết công đoạn
    nào dùng dòng nào, bên sản xuất chọn ở bước lệnh."""
    from app.models.piece_work import PieceRate

    r = PieceRate(group_name="Tổ test", department_id=department_id, name=ten, unit=don_vi,
                  unit_price=don_gia, is_active=True)
    db.add(r)
    db.commit()
    return r


def _gan_dinh_muc(db, *, cong_doan: CongDoan, ten: str, don_vi: str, don_gia: float,
                  nang_suat: float = 1000, mac_dinh: bool = False):
    rate = _don_gia_khoan(db, department_id=cong_doan.department_id,
                          ten=ten, don_vi=don_vi, don_gia=don_gia)
    db.add(CongDoanDauViec(
        cong_doan_id=cong_doan.id, piece_rate_id=rate.id,
        nang_suat_nguoi_gio=nang_suat, so_nguoi_tieu_chuan=2,
        so_nguoi_toi_da=4, is_default=mac_dinh,
    ))
    db.commit()
    return rate


def test_doi_to_thi_danh_sach_dau_viec_khoan_doi_theo_to_va_cong_doan(
    db, orders, lsx_svc, admin, customer
):
    """Dropdown LSX không được giữ đầu việc của tổ cũ sau khi kế hoạch đổi tổ."""
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    rate = _gan_dinh_muc(
        db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250,
        nang_suat=1200, mac_dinh=True,
    )
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line_id = lsx_svc.preview(d.id)["lines"][0]["order_line_id"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[line_id], actor=admin)[0]

    dung_to = lsx_svc.dau_viec_options(
        lsx_id=lsx.id, cong_doan_id=cd_dan.id, department_id=cd_dan.department_id,
    )
    assert [x["id"] for x in dung_to] == [rate.id]
    assert dung_to[0]["nang_suat_nguoi_gio"] == 1200
    assert dung_to[0]["is_default"] is True

    to_khac = Department(name="Tổ Đóng gói khác", code="TO-DG-KHAC", la_san_xuat=True)
    db.add(to_khac)
    db.commit()
    assert lsx_svc.dau_viec_options(
        lsx_id=lsx.id, cong_doan_id=cd_dan.id, department_id=to_khac.id,
    ) == []


def test_bung_lenh_tu_dien_dau_viec_va_ra_tien_du_kien(db, orders, lsx_svc, admin, customer):
    """Bảng khoán của tổ khớp ĐÚNG MỘT đầu việc → máy điền sẵn + quy đổi ra tiền công dự kiến.

    Bước "Dán hộp" đếm CON, đơn giá cũng đ/con nên không cần cầu; phần quy đổi chéo họ (tờ → m²) đã có
    test riêng ở `test_quy_doi.py`.
    """
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]

    chi_tiet = lsx_svc.detail_dict(lsx)
    buoc_be = next(b for b in chi_tiet["cong_doans"] if b["ten"] == "Dán hộp")
    assert buoc_be["khoan_ten"] == "Dán hộp thủ công"
    assert buoc_be["khoan_don_gia"] == 250
    # Tiền = SL VÀO của bước × đơn giá: thợ chạy bao nhiêu tờ thì ăn bấy nhiêu (kể cả tờ bù hao).
    assert buoc_be["khoan_tien"] == pytest.approx(buoc_be["so_luong_vao"] * 250, rel=1e-6)
    assert "đ/cái" in buoc_be["khoan_dien_giai"]
    assert chi_tiet["khoan_tien_tong"] >= buoc_be["khoan_tien"]


def test_hai_dau_viec_cung_cong_doan_thi_khong_dien_ho(db, orders, lsx_svc, admin, customer):
    """Tổ có 2 đơn giá (bế máy 250đ/tờ · bế tay 400đ/tờ) — chỉ người biết hôm đó bế bằng gì, nên
    máy để TRỐNG và gửi kèm danh sách chọn thay vì chọn hộ một cái."""
    ptg = _ptg_2_san_pham(db)
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    for ten, gia in (("Dán thường", 250), ("Dán khó", 400)):
        _gan_dinh_muc(db, cong_doan=cd_be, ten=ten, don_vi="cái", don_gia=gia)

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]

    buoc_be = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")
    assert buoc_be["khoan_rate_id"] is None
    assert {k["ten"] for k in buoc_be["khoan_chon_duoc"]} == {"Dán thường", "Dán khó"}
    # Drawer phải có đủ định mức NGAY KHI mở dropdown để đổi đầu việc là xem được nhân lực
    # và thời gian live, không phải lưu bước rồi mới nhận snapshot từ backend.
    assert {
        (k["nang_suat_nguoi_gio"], k["so_nguoi_tieu_chuan"], k["so_nguoi_toi_da"])
        for k in buoc_be["khoan_chon_duoc"]
    } == {(1000, 2, 4)}
    assert buoc_be["khoan_tien"] is None      # chưa chọn thì KHÔNG có số nào


def test_sua_routing_ghim_dau_viec_va_giu_gia_luc_chon(db, orders, lsx_svc, admin, customer):
    """Chọn đầu việc ở drawer → ghim SNAPSHOT. Xưởng lên giá khoán sau đó KHÔNG được xê dịch lệnh
    đã phát: bước vẫn giữ đơn giá lúc chọn."""
    ptg = _ptg_2_san_pham(db)
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    r1 = _gan_dinh_muc(db, cong_doan=cd_be, ten="Dán thường", don_vi="cái", don_gia=250)
    _gan_dinh_muc(db, cong_doan=cd_be, ten="Dán khó", don_vi="cái", don_gia=400)

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]

    rows = [
        LsxCongDoanIn(
            thu_tu=cd.thu_tu, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
            department_id=cd.department_id, so_luong_vao=float(cd.so_luong_vao),
            so_luong_ra=float(cd.so_luong_ra), don_vi_vao=cd.don_vi_vao, don_vi_ra=cd.don_vi_ra,
            piece_rate_id=(r1.id if cd.ten == "Dán hộp" else None),
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin, ly_do=None)
    buoc_be = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")
    assert buoc_be["khoan_rate_id"] == r1.id and buoc_be["khoan_don_gia"] == 250

    # Xưởng tăng giá khoán → lệnh ĐÃ ghim không đổi (đọc-sống là sai ở đây).
    r1.unit_price = 999
    db.commit()
    buoc_be = next(b for b in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
                   if b["ten"] == "Dán hộp")
    assert buoc_be["khoan_don_gia"] == 250


def test_khong_co_bang_khoan_thi_khong_co_tien(db, orders, lsx_svc, admin, customer):
    """Tổ chưa khai giá khoán → mọi bước im lặng, tổng = 0. KHÔNG bịa số nào."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]

    chi_tiet = lsx_svc.detail_dict(lsx)
    assert all(b["khoan_rate_id"] is None and b["khoan_tien"] is None
               for b in chi_tiet["cong_doans"])
    assert chi_tiet["khoan_tien_tong"] == 0


# ================= Routing lát 2: thời gian · tính ngược · cảnh báo =================
def _buoc(**kw) -> LsxCongDoan:
    """1 bước rời để test công thức thời gian — không cần DB."""
    return LsxCongDoan(lsx_id=0, thu_tu=0, ten=kw.pop("ten", "Bước"), **kw)


def test_thoi_luong_tach_chiem_may_khoi_cho_va_di_chuyen():
    """Ví dụ §4.4: 45 chuẩn bị + 5.300 tờ @ 5.000 tờ/h + 15 vệ sinh ≈ 124 phút CHIẾM MÁY.

    Chờ khô mực 4 tiếng KHÔNG làm máy in bị chiếm thêm 4 tiếng — nó chỉ đẩy bước sau.
    """
    b = _buoc(so_luong_vao=5300, nang_suat=5000, don_vi_nang_suat="to_gio",
              setup_phut=45, ve_sinh_phut=15, cho_phut=240, di_chuyen_phut=30)
    t = thoi_luong_buoc(b)
    assert round(t["chay_phut"]) == 64
    assert round(t["chiem_may_phut"]) == 124                 # 45 + 64 + 15
    assert round(t["tong_phut"]) == 124 + 240 + 30           # chờ + di chuyển chỉ vào TỔNG


def test_chay_phut_go_de_thang_cong_thuc_nang_suat():
    b = _buoc(so_luong_vao=5300, nang_suat=5000, don_vi_nang_suat="to_gio",
              setup_phut=45, ve_sinh_phut=15, chay_phut=120)
    t = thoi_luong_buoc(b)
    assert t["chay_phut"] == 120 and round(t["chiem_may_phut"]) == 180


def test_may_nhan_so_luot_nhung_khong_chia_theo_kip_nguoi():
    assert thoi_luong_buoc(_buoc(loai_buoc="may", so_luong_vao=5000, nang_suat=5000))["chay_phut"] == 60
    # In trở 2 lượt → chạy gấp đôi.
    t = thoi_luong_buoc(_buoc(loai_buoc="may", so_luong_vao=5000, nang_suat=5000,
                              so_luot_chay=2, so_nhan_cong=3))
    assert t["chay_phut"] == 120
    assert t["dien_giai"]["phuong_phap"] == "may"
    assert t["dien_giai"]["so_nhan_cong_tinh"] is None
    assert t["dien_giai"]["so_nhan_cong_ke_hoach"] == 3
    assert t["dien_giai"]["so_nhan_cong_tieu_chuan"] == 1


def test_to_chia_theo_nguoi_va_gioi_han_o_muc_toi_da():
    t = thoi_luong_buoc(_buoc(
        loai_buoc="to", so_luong_vao=5000, nang_suat=500,
        setup_phut=45, so_nhan_cong=6, so_nhan_cong_toi_da=5,
    ))
    assert t["chay_phut"] == 120
    assert t["chiem_may_phut"] == 165
    assert t["dien_giai"]["nang_suat_hieu_dung"] == 2500
    assert t["dien_giai"]["so_nhan_cong_tinh"] == 5
    assert t["dien_giai"]["so_nhan_cong_ke_hoach"] == 6
    assert t["dien_giai"]["so_nhan_cong_toi_da"] == 5
    assert any("vượt mức tối đa hiệu quả" in x for x in t["dien_giai"]["canh_bao"])


def test_thieu_nang_suat_thi_khong_bia_so():
    """Chưa khai năng suất → thời gian chạy = 0, KHÔNG đoán bừa để Gantt khỏi vẽ số sai."""
    result = thoi_luong_buoc(_buoc(so_luong_vao=5000, setup_phut=45))
    assert result["chay_phut"] == 0
    assert any("Thiếu năng suất hợp lệ" in x for x in result["dien_giai"]["canh_bao"])


def test_mac_dinh_ke_thua_tu_danh_muc_cong_doan_va_may(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp", don_vi="cái", don_gia=80,
                  nang_suat=4000, mac_dinh=True)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    b = {cd.ten: cd for cd in hop.cong_doans}
    # setup ← cong_doan.setup_time; năng suất + rửa mực ← may_thiet_bi (chỉ bước IN mới rửa mực)
    assert float(b["In offset"].setup_phut) == 45
    assert float(b["In offset"].nang_suat) == 5000 and b["In offset"].don_vi_nang_suat == "to_gio"
    assert float(b["In offset"].ve_sinh_phut) == 15
    assert float(b["Bế"].setup_phut) == 30 and float(b["Bế"].ve_sinh_phut) == 0
    # Bước Tổ lấy năng suất/người từ định mức đầu việc, đơn vị suy từ đơn vị vào
    # của bước (dán đếm con ⇒ con/giờ) chứ không đọc cột lưu nào.
    assert float(b["Dán hộp"].nang_suat) == 4000
    assert b["Dán hộp"].don_vi_nang_suat == "cai_gio" and b["Dán hộp"].may_id is None
    assert thoi_luong_buoc(b["Dán hộp"])["chay_phut"] > 0
    # Hao hụt % KHÔNG kế thừa từ danh mục dù `cong_doan.spoilage_pct` = 2: module Bù hao đã bao cả
    # hao theo % (bậc `don_vi='pct'`, `tra_bac` quy về số tờ) và đã nằm trong `hao_hut` — lấy thêm
    # lần nữa là đếm hai lần. Ô này để trống cho người kế hoạch quyết tại lệnh.
    assert float(b["Dán hộp"].hao_hut_pct) == 0
    # Cục bù hao của engine chỉ gắn ĐÚNG MỘT bước (bước in) — bước khác phải bằng 0.
    assert float(b["In offset"].hao_hut) == hop.bu_hao_to
    assert float(b["Bế"].hao_hut) == 0 and float(b["Dán hộp"].hao_hut) == 0
    # Loại bước suy theo nhóm/tên: in = máy, dán tay = tổ.
    assert b["In offset"].loai_buoc == "may" and b["Dán hộp"].loai_buoc == "to"
    # BẪY: `comp["so_luot"]` của engine là TỔNG lượt tờ (tờ × số mặt), KHÔNG phải số lượt chạy.
    # In 1 mặt phải ra 1 — lấy nhầm sẽ nhân thời gian chạy lên hàng nghìn lần.
    assert b["In offset"].so_luot_chay == 1


def test_che_ban_dung_ngoai_chuoi_va_khong_deo_canh_bao_dut_don_vi(db, orders, lsx_svc, admin, customer):
    """Chế bản đếm KẼM → đơn vị TRỐNG, đứng ngoài chuỗi, và KHÔNG được đẻ cảnh báo giả.

    Đây là bẫy chính: nếu so liền kề mà không lọc bước trống ra trước thì bước chế bản đứng đầu
    routing sẽ "đứt đơn vị" với bước in ngay sau nó, dù chuỗi giấy hoàn toàn liền mạch.
    """
    ptg = _ptg_2_san_pham(db)
    to_id = _to_san_xuat(db).id
    ctp = CongDoan(ma="CD-CTP-T", ten="Ghi kẽm CTP", nhom="prepress", department_id=to_id,
                   cong_thuc_gia="so_luong * don_gia")   # KHÔNG khai đơn vị = không chạm giấy
    db.add(ctp)
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-BE-T").first()
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten="Ghi kẽm CTP", nhom="prepress", department_id=to_id, cong_doan_id=ctp.id),
        LsxCongDoanIn(ten="In offset", nhom="print", department_id=to_id, cong_doan_id=cd_in.id),
        LsxCongDoanIn(ten="Bế", nhom="finishing", department_id=to_id, cong_doan_id=cd_be.id),
    ])
    hop2 = lsx_svc.get(hop.id)
    ctp_row = hop2.cong_doans[0]
    assert (ctp_row.don_vi_vao, ctp_row.don_vi_ra) == (None, None)
    # Chuỗi giấy (in → bế) liền mạch ⇒ KHÔNG cảnh báo, dù chế bản chen ở đầu.
    assert "dut_don_vi" not in lsx_svc.canh_bao_cua(hop2)
    # Bước cuối vẫn giao đúng SL đơn → không lệch.
    assert "lech_sl_don" not in lsx_svc.canh_bao_cua(hop2)


def test_chi_tiet_lenh_co_buoc_che_ban_van_qua_duoc_SCHEMA(db, orders, lsx_svc, admin, customer):
    """Chế bản có đơn vị NULL → schema phải nhận. Khai `str` cứng là mọi lần mở lệnh đều 500.

    Test service KHÔNG bắt được lỗi này vì nó không đi qua lớp Pydantic — phải validate đúng
    payload mà router trả về.
    """
    from app.schemas.lsx import LsxOut

    ptg = _ptg_2_san_pham(db)
    to_id = _to_san_xuat(db).id
    ctp = CongDoan(ma="CD-CTP-S", ten="Ghi kẽm CTP", nhom="prepress", department_id=to_id,
                   cong_thuc_gia="so_luong * don_gia")   # không khai đơn vị
    db.add(ctp)
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten="Ghi kẽm CTP", nhom="prepress", department_id=to_id, cong_doan_id=ctp.id),
        LsxCongDoanIn(ten="In offset", nhom="print", department_id=to_id, cong_doan_id=cd_in.id),
    ])
    lsx = lsx_svc.get(hop.id)
    out = LsxOut.model_validate({**lsx.__dict__, **lsx_svc.detail_dict(lsx)})   # y hệt `routers.lsx._out`
    assert out.cong_doans[0].don_vi_vao is None and out.cong_doans[0].don_vi_ra is None
    assert out.cong_doans[1].don_vi_vao == "to"


def test_client_gui_so_luong_va_don_vi_len_thi_server_lo_di(db, orders, lsx_svc, admin, customer):
    """Số lượng + đơn vị là DẪN XUẤT — client gửi gì cũng bị chuỗi ngược ghi đè."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    to_id = _to_san_xuat(db).id
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-BE-T").first()

    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten="Bế", nhom="finishing", department_id=to_id, cong_doan_id=cd_be.id,
                      so_luong_vao=999_999, so_luong_ra=888_888,     # số bịa
                      don_vi_vao="cai", don_vi_ra="cai",             # đơn vị bịa
                      he_so_quy_doi=7, hao_hut=12345, hao_hut_pct=99),
    ])
    be = lsx_svc.get(hop.id).cong_doans[0]
    assert (be.don_vi_vao, be.don_vi_ra) == ("to", "cai")     # theo DANH MỤC, không theo client
    assert float(be.he_so_quy_doi) == float(hop.so_con)
    assert float(be.so_luong_ra) == hop.so_luong_dat          # bước cuối giao đúng SL đơn
    assert float(be.so_luong_vao) not in (999_999, 888_888)
    assert float(be.hao_hut) != 12345 and float(be.hao_hut_pct) != 99


def test_ba_don_vi_doc_ra_hai_moc_so_to_cua_lenh(db, orders, lsx_svc, admin, customer):
    """`so_to_ke_hoach` / `so_to_nguyen` là ĐỌC RA từ chuỗi tại đúng ranh giới đơn vị."""
    ptg = _ptg_2_san_pham(db)
    to_id = _to_san_xuat(db).id
    # Bước xả giấy = cầu tờ nguyên → tờ in, hệ số lấy từ `quy_cach_json["so_manh_xa"]`.
    xa = CongDoan(ma="CD-XA-T", ten="Xả giấy", nhom="finishing", department_id=to_id,
                  cong_thuc_gia="so_luong * don_gia", don_vi_vao="to_nguyen", don_vi_ra="to",
                  kieu_bu_hao="co_dinh", so_to_bu_hao=5)
    db.add(xa)
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-BE-T").first()

    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten="Xả giấy", nhom="finishing", department_id=to_id, cong_doan_id=xa.id),
        LsxCongDoanIn(ten="In offset", nhom="print", department_id=to_id, cong_doan_id=cd_in.id),
        LsxCongDoanIn(ten="Bế", nhom="finishing", department_id=to_id, cong_doan_id=cd_be.id),
    ])
    hop2 = lsx_svc.get(hop.id)
    b = {c.ten: c for c in hop2.cong_doans}
    assert (b["Xả giấy"].don_vi_vao, b["Xả giấy"].don_vi_ra) == ("to_nguyen", "to")
    # Liền mạch qua CẢ HAI cầu: tờ nguyên → tờ in → con.
    assert float(b["Xả giấy"].so_luong_ra) == float(b["In offset"].so_luong_vao)
    assert float(b["In offset"].so_luong_ra) == float(b["Bế"].so_luong_vao)
    assert float(b["Bế"].so_luong_ra) == hop2.so_luong_dat
    # Hai mốc số tờ của lệnh đọc đúng chỗ, KHÔNG tính riêng bên ngoài.
    assert hop2.so_to_ke_hoach == int(float(b["In offset"].so_luong_vao))
    assert hop2.so_to_nguyen == int(float(b["Xả giấy"].so_luong_vao))


def test_tinh_nguoc_tu_sl_thanh_pham_qua_ranh_gioi_doi_don_vi(db, orders, lsx_svc, admin, customer):
    """Đúng chiều xưởng: cần 20.000 hộp tốt → ngược lên phải in bao nhiêu tờ.

    Chuỗi In(to→to) → Bế(to→cai, hệ số = con/tờ) → Dán(cai→cai). Hao cộng dồn từ bước CUỐI về
    ĐẦU, và lấy theo quy tắc bù hao của DANH MỤC công đoạn — không đọc `hao_hut` gõ tay ở bước.
    Mỗi bước tra hao ở ĐÚNG đơn vị của nó: dán đếm CON nên hao tính bằng con, bế/in bằng tờ.
    """
    ptg = _ptg_2_san_pham(db)
    for ma, hao in (("CD-DAN-T", 400), ("CD-BE-T", 30)):
        db.query(CongDoan).filter(CongDoan.ma == ma).update(
            {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": hao})
    db.query(CongDoan).filter(CongDoan.nhom == "print").update(
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 150})
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    rows = {r["ten"]: r for r in lsx_svc.tinh_nguoc_routing(hop)}
    con = float(hop.so_con)
    assert rows["Dán hộp"]["so_luong_ra"] == 20_000          # bước cuối giao đúng SL khách đặt
    assert rows["Dán hộp"]["so_luong_vao"] == 20_000 + 400   # hao 400 CON (đơn vị của bước)
    # Bế là ranh giới: quy con → tờ TRƯỚC rồi mới cộng hao tính bằng TỜ.
    assert rows["Bế"]["so_luong_ra"] == rows["Dán hộp"]["so_luong_vao"]
    assert rows["Bế"]["so_luong_vao"] == ceil(rows["Bế"]["so_luong_ra"] / con + 30)
    assert rows["In offset"]["so_luong_vao"] == rows["Bế"]["so_luong_vao"] + 150
    # Số đã được GHI thẳng vào bước, không còn là "gợi ý" chờ bấm áp dụng.
    assert float(next(c for c in hop.cong_doans if c.ten == "In offset").so_luong_vao) \
        == rows["In offset"]["so_luong_vao"]


def test_tinh_nguoc_doi_hao_buoc_giua_thi_buoc_dau_doi_theo(db, orders, lsx_svc, admin, customer):
    """Đổi định mức bù hao ở DANH MỤC bước giữa → bước đầu chuỗi phải đòi nhiều tờ hơn."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    truoc = lsx_svc.tinh_nguoc_routing(hop)[0]["so_luong_vao"]

    db.query(CongDoan).filter(CongDoan.ma == "CD-BE-T").update(
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 500})
    db.commit()
    assert lsx_svc.tinh_nguoc_routing(lsx_svc.get(hop.id))[0]["so_luong_vao"] > truoc


def test_thieu_NGUON_he_so_moi_chan_chu_khong_phai_he_so_bang_1(db, orders, lsx_svc, admin, customer):
    """Hệ số quy đổi nay do server suy — không ai khai, nên "chưa khai hệ số" là khái niệm chết.

    Chỉ thiếu NGUỒN của nó mới là lỗi thật, và HAI CẦU có HAI nguồn khác nhau:
    `tờ in → con` lấy `lsx.so_con`, `tờ nguyên → tờ in` lấy `quy_cach_json["so_manh_xa"]`.
    Hệ số = 1 là HỢP LỆ ở cả hai (1 tờ nguyên ra 1 tờ in là chuyện thường) — luật cũ chặn ở
    `he_so <= 1` nên bắt oan chính ca đó.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    # Chuỗi có bước bế (to→cai, từ danh mục) và con/tờ khai đủ → KHÔNG thiếu gì về hệ số.
    assert "thieu_con_tren_to" not in lsx_svc.thieu_cua(hop)

    hop.so_con = 0
    db.commit()
    assert "thieu_con_tren_to" in lsx_svc.thieu_cua(lsx_svc.get(hop.id))
    with pytest.raises(LsxConflict):
        lsx_svc.set_trang_thai(lsx_id=hop.id, trang_thai=TT_SAN_SANG, actor=admin)

    # Hệ số ĐÚNG BẰNG 1 (1 con/tờ — poster bằng khổ tờ) là hợp lệ, không được chặn.
    hop.so_con = 1
    db.commit()
    assert "thieu_con_tren_to" not in lsx_svc.thieu_cua(lsx_svc.get(hop.id))


def test_thue_ngoai_thieu_ncc_hoac_ngay_thi_chan_khai_du_thi_mo(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    to_id = _to_san_xuat(db).id

    def dat_routing(**ngoai) -> list[str]:
        lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
            LsxCongDoanIn(ten="In offset", nhom="print", department_id=to_id,
                          so_luong_vao=5300, so_luong_ra=5300, don_vi_vao="to"),
            LsxCongDoanIn(ten="Cán màng", nhom="finishing", loai_buoc="thue_ngoai",
                          so_luong_vao=5300, so_luong_ra=5250, don_vi_vao="to", **ngoai),
        ])
        return lsx_svc.thieu_cua(lsx_svc.get(hop.id))

    assert {"thieu_ncc", "thieu_tg_thue_ngoai"} <= set(dat_routing())
    # Có NCC nhưng chưa có mốc thời gian → vẫn chặn (Gantt không biết đặt vào đâu).
    thieu = dat_routing(nha_cung_cap="Cơ sở Tân Bình")
    assert "thieu_ncc" not in thieu and "thieu_tg_thue_ngoai" in thieu

    thieu = dat_routing(
        nha_cung_cap="Cơ sở Tân Bình", sl_gui=5300,
        ngay_gui_dk=date.today() + timedelta(days=1),
        ngay_nhan_dk=date.today() + timedelta(days=4),
        van_chuyen_ngay=1, gia_cong_ngay=1, don_gia_gia_cong=500,
    )
    assert "thieu_ncc" not in thieu and "thieu_tg_thue_ngoai" not in thieu


def test_replace_routing_giu_nguyen_khoi_thue_ngoai(db, orders, lsx_svc, admin, customer):
    """REPLACE-ALL không được làm rơi dữ liệu người dùng vừa khai ở drawer."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(
            ten="Cán màng", nhom="finishing", loai_buoc="thue_ngoai",
            so_luong_vao=5300, so_luong_ra=5250, don_vi_vao="to",
            nha_cung_cap="Cơ sở Tân Bình", sl_gui=5300,
            ngay_gui_dk=date.today(), ngay_nhan_dk=date.today() + timedelta(days=3),
            van_chuyen_ngay=1, gia_cong_ngay=1, hao_hut_cho_phep=50, don_gia_gia_cong=450,
            yeu_cau_ky_thuat="Màng mờ, không bong mép",
            cho_phut=120, di_chuyen_phut=45, so_nhan_cong=3, bat_buoc=False,
        ),
    ])
    cd = lsx_svc.get(hop.id).cong_doans[0]
    assert cd.nha_cung_cap == "Cơ sở Tân Bình" and float(cd.don_gia_gia_cong) == 450
    assert cd.yeu_cau_ky_thuat == "Màng mờ, không bong mép"
    assert not hasattr(cd, "dieu_kien_json")
    assert float(cd.cho_phut) == 120 and float(cd.di_chuyen_phut) == 45
    assert cd.so_nhan_cong == 3 and cd.bat_buoc is False
    assert float(cd.hao_hut_cho_phep) == 50 and cd.ngay_nhan_dk is not None


def test_replace_routing_upsert_giu_id_va_luu_vat_tu_phu_thuoc(
    db, orders, lsx_svc, admin, customer
):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line_id = lsx_svc.preview(d.id)["lines"][0]["order_line_id"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[line_id], actor=admin)[0]
    before = list(sorted(lsx.cong_doans, key=lambda x: x.thu_tu))[:2]
    before_ids = [x.id for x in before]
    vt = VatTuInAn(ma="KEO-TEST", ten="Keo đóng cuốn", don_vi_gia="kg", don_gia=0)
    db.add(vt)
    db.commit()

    rows = [
        LsxCongDoanIn(
            step_key=before[0].step_key, cong_doan_id=before[0].cong_doan_id,
            ten=before[0].ten, nhom=before[0].nhom, loai_buoc=before[0].loai_buoc,
            department_id=before[0].department_id, may_id=before[0].may_id,
            phu_thuoc_step_keys=[], vat_tus=[],
        ),
        LsxCongDoanIn(
            step_key=before[1].step_key, cong_doan_id=before[1].cong_doan_id,
            ten=before[1].ten, nhom=before[1].nhom, loai_buoc=before[1].loai_buoc,
            department_id=before[1].department_id, may_id=before[1].may_id,
            phu_thuoc_step_keys=[before[0].step_key],
            vat_tus=[{"vat_tu_id": vt.id, "so_luong": 2.5}],
        ),
    ]
    saved = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin)
    after = list(sorted(saved.cong_doans, key=lambda x: x.thu_tu))

    assert [x.id for x in after] == before_ids
    assert after[1].phu_thuoc[0].buoc_truoc_id == after[0].id
    assert after[1].vat_tus[0].vat_tu_ten_snapshot == "Keo đóng cuốn"
    assert after[1].vat_tus[0].don_vi_snapshot == "kg"
    assert float(after[1].vat_tus[0].so_luong) == 2.5


def test_doi_cong_doan_giua_chung_thi_keo_lai_mac_dinh_cua_cong_doan_moi(
    db, orders, lsx_svc, admin, customer
):
    """Đổi công đoạn của 1 bước KHÔNG được để nó đeo nguyên số của công đoạn cũ.

    Đổi Công đoạn chỉ kéo lại thuộc tính của công việc (tên, tổ, đơn vị, setup). Loại bước, máy và
    nguồn năng suất là quyết định riêng ở KHSX nên endpoint mặc định không được ghi đè chúng.
    """
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp", don_vi="cái", don_gia=80,
                  nang_suat=4000, mac_dinh=True)
    to_id = _to_san_xuat(db).id
    can = CongDoan(ma="CD-CAN-T", ten="Cán màng bóng", nhom="finishing",
                   cong_thuc_gia="so_luong * don_gia", department_id=to_id, setup_time=20,
                   don_vi_vao="to", don_vi_ra="to")
    db.add(can)
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    dan = next(cd for cd in hop.cong_doans if cd.ten == "Dán hộp")
    assert dan.loai_buoc == "to" and dan.don_vi_vao == "cai" and float(dan.nang_suat) == 4000

    m = lsx_svc.mac_dinh_buoc(lsx_id=hop.id, cong_doan_id=can.id)
    assert m["don_vi_vao"] == "to" and m["don_vi_ra"] == "to"   # đếm TỜ, chưa qua bế
    assert float(m["setup_phut"]) == 20 and m["department_id"] == to_id
    assert {"loai_buoc", "may_id", "nang_suat", "don_vi_nang_suat"}.isdisjoint(m)
    # Số lượng KHÔNG nằm trong bộ mặc định — thuộc chuỗi, người kế hoạch giữ số đang cân.
    assert "so_luong_vao" not in m and "so_luong_ra" not in m


def test_mac_dinh_buoc_chi_tra_thuoc_tinh_cua_cong_doan(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    for cd in hop.cong_doans:
        if cd.cong_doan_id is None:
            continue
        m = lsx_svc.mac_dinh_buoc(lsx_id=hop.id, cong_doan_id=cd.cong_doan_id)
        assert m["don_vi_vao"] == cd.don_vi_vao and m["don_vi_ra"] == cd.don_vi_ra, cd.ten
        assert float(m["setup_phut"]) == float(cd.setup_phut), cd.ten
        assert {"loai_buoc", "may_id", "nang_suat", "don_vi_nang_suat"}.isdisjoint(m), cd.ten


def test_replace_routing_ton_trong_loai_buoc_do_khsx_chon(
    db, orders, lsx_svc, admin, customer
):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [line["order_line_id"] for line in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    row = next(x for x in hop.cong_doans if x.ten == "Bế")

    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(
            step_key=x.step_key, cong_doan_id=x.cong_doan_id, ten=x.ten, nhom=x.nhom,
            department_id=x.department_id, loai_buoc=("to" if x.id == row.id else x.loai_buoc),
            may_id=None if x.id == row.id else x.may_id,
        )
        for x in sorted(hop.cong_doans, key=lambda item: item.thu_tu)
    ])

    saved = next(x for x in lsx_svc.get(hop.id).cong_doans if x.id == row.id)
    assert saved.loai_buoc == "to"
    assert saved.may_id is None


def test_doi_may_ke_thua_kip_chuan_nhung_giu_so_nguoi_ke_hoach_nhap_tai_lsx(
    db, orders, lsx_svc, admin, customer
):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line_id = lsx_svc.preview(d.id)["lines"][0]["order_line_id"]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=[line_id], actor=admin)[0]
    may_moi = MayThietBi(
        ma="MAY-KIP-2", ten="Máy kíp 2", loai_may="Bế", toc_do=4000,
        don_vi_toc_do="to_gio", so_nhan_cong=2,
    )
    db.add(may_moi)
    db.commit()
    muc_tieu = next(x for x in hop.cong_doans if x.loai_buoc == "may")

    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(
            step_key=x.step_key, cong_doan_id=x.cong_doan_id, ten=x.ten, nhom=x.nhom,
            department_id=x.department_id, loai_buoc=x.loai_buoc,
            may_id=may_moi.id if x.id == muc_tieu.id else x.may_id,
            so_nhan_cong=4 if x.id == muc_tieu.id else x.so_nhan_cong,
        )
        for x in sorted(hop.cong_doans, key=lambda item: item.thu_tu)
    ])

    saved = next(x for x in lsx_svc.get(hop.id).cong_doans if x.id == muc_tieu.id)
    assert saved.so_nhan_cong_tieu_chuan == 2
    assert saved.so_nhan_cong == 4
    assert float(saved.nang_suat) == 4000


def test_cong_doan_chua_khai_nang_suat_thi_de_trong_chu_khong_bia_so(
    db, orders, lsx_svc, admin, customer
):
    """Danh mục trống ⇒ bước để TRỐNG năng suất, KHÔNG rơi về 0.

    Thời lượng hiện "—" là tín hiệu đúng để đi khai danh mục; số 0 giả thì Gantt sau này vẽ thanh
    dài 0 mà không ai biết là do thiếu dữ liệu.
    """
    ptg = _ptg_2_san_pham(db)
    db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one().nang_suat = None
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    dan = next(cd for cd in hop.cong_doans if cd.ten == "Dán hộp")
    assert dan.nang_suat is None and dan.don_vi_nang_suat is None
    assert thoi_luong_buoc(dan)["chay_phut"] == 0


def test_may_khai_don_vi_toc_do_khac_to_gio_thi_khong_nhan(db, orders, lsx_svc, admin, customer):
    """Máy khai m²/giờ mà đem dùng làm tờ/giờ là SAI THẦM LẶNG — thà để trống cho người khai.

    Xưởng chỉ in offset tờ nên `to_gio` là đơn vị duy nhất dùng được; các đơn vị khác của
    `may_thiet_bi.don_vi_toc_do` không quy đổi được nếu không có thêm quy cách.
    """
    ptg = _ptg_2_san_pham(db)             # đã dựng sẵn máy MAY-IN-T bên trong
    db.query(MayThietBi).filter(MayThietBi.ma == "MAY-IN-T").one().don_vi_toc_do = "m2_gio"
    db.commit()                           # số vẫn 5000 nhưng đơn vị khác
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    b = {cd.ten: cd for cd in hop.cong_doans}
    assert b["In offset"].nang_suat is None and b["In offset"].don_vi_nang_suat is None
    # Nhưng các số KHÁC của máy/công đoạn vẫn kế thừa bình thường.
    assert float(b["In offset"].setup_phut) == 45 and float(b["In offset"].ve_sinh_phut) == 15


def test_de_trong_thoi_gian_chay_thi_khong_bi_dong_bang_sau_khi_luu(
    db, orders, lsx_svc, admin, customer
):
    """Vòng LƯU → ĐỌC → LƯU LẠI không được biến số MÁY TÍNH thành số NGƯỜI GÕ ĐÈ.

    `chay_phut` để trống nghĩa là "máy tự tính từ năng suất". Nếu API trả về số đã tính ở chính
    trường đó, client tưởng người dùng gõ đè rồi lưu ngược lại — từ đó năng suất hết tác dụng và
    bước chưa khai năng suất bị đóng băng ở 0 phút. Đây là lỗi ÂM THẦM: mọi test một-chiều đều xanh.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    # Cái API trả ra phải là giá trị ĐÃ LƯU (None), không phải số dẫn xuất.
    ra = {c["ten"]: c for c in lsx_svc.detail_dict(hop)["cong_doans"]}
    assert ra["In offset"]["chay_phut"] is None
    assert ra["In offset"]["chiem_may_phut"] > 0        # số dẫn xuất nằm ở trường RIÊNG

    # Client gửi lại đúng thứ nó nhận (chay_phut=None) → DB vẫn phải là None.
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten=c["ten"], nhom=c["nhom"], loai_buoc=c["loai_buoc"],
                      department_id=c["department_id"], may_id=c["may_id"],
                      so_luong_vao=c["so_luong_vao"], so_luong_ra=c["so_luong_ra"],
                      don_vi_vao=c["don_vi_vao"], don_vi_ra=c["don_vi_ra"],
                      he_so_quy_doi=c["he_so_quy_doi"], nang_suat=c["nang_suat"],
                      don_vi_nang_suat=c["don_vi_nang_suat"], setup_phut=c["setup_phut"],
                      chay_phut=c["chay_phut"])
        for c in lsx_svc.detail_dict(hop)["cong_doans"]
    ])
    sau = {c.ten: c for c in lsx_svc.get(hop.id).cong_doans}
    assert sau["In offset"].chay_phut is None
    assert sau["Dán hộp"].chay_phut is None            # chưa khai năng suất ⇒ KHÔNG đóng băng ở 0

    # Khai năng suất muộn vẫn phải ăn — bằng chứng là ô gõ đè còn trống.
    sau["Dán hộp"].nang_suat = 4000
    db.commit()
    assert thoi_luong_buoc(lsx_svc.get(hop.id).cong_doans[-1])["chay_phut"] > 0


def test_canh_bao_mem_khong_lot_vao_ro_chan_va_ghi_ly_do(db, orders, lsx_svc, admin, customer):
    """§14: chuỗi đứt đơn vị / lệch bài tính giá chỉ TÔ MÀU, không chặn. §10: lưu lý do thay đổi.

    "Đứt chuyền" theo SỐ nay không xảy ra được nữa — số lượng mọi bước là dẫn xuất của chuỗi
    ngược nên luôn khớp. Cái còn đứt được là ĐƠN VỊ: bước sau ăn đơn vị khác bước trước nhả.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    assert hop.routing_goc_json and "khac_bai_tinh_gia" not in lsx_svc.canh_bao_cua(hop)
    to_id = _to_san_xuat(db).id
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-BE-T").first()
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()

    # Bế nhả CON rồi tới bước ăn TỜ → chuỗi đứt đơn vị. Đơn vị lấy từ DANH MỤC nên phải gắn
    # `cong_doan_id`, client gửi `don_vi_*` không còn tác dụng.
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, ly_do="Khách đổi sang gia công ngoài", rows_in=[
        LsxCongDoanIn(ten="Bế", nhom="finishing", department_id=to_id, cong_doan_id=cd_be.id),
        LsxCongDoanIn(ten="In offset", nhom="print", department_id=to_id, cong_doan_id=cd_in.id),
    ])
    hop2 = lsx_svc.get(hop.id)
    cb = lsx_svc.canh_bao_cua(hop2)
    assert "dut_don_vi" in cb and "khac_bai_tinh_gia" in cb
    assert not (set(cb) & set(lsx_svc.thieu_cua(hop2)))      # hai rổ TÁCH BẠCH
    chi_tiet = [r.detail for r in AuditLogRepository(db).list_by_target(f"lsx:{hop.id}")]
    assert any("Khách đổi sang gia công ngoài" in c for c in chi_tiet)


def test_canh_bao_vuot_han_giao_khi_lead_time_dai_hon_han(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)   # hạn giao = hôm nay + 10 ngày
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    for cd in hop.cong_doans:
        cd.chay_phut, cd.setup_phut, cd.ve_sinh_phut, cd.cho_phut = 0, 0, 0, 0
    db.commit()
    assert "vuot_han_giao" not in lsx_svc.canh_bao_cua(lsx_svc.get(hop.id))

    hop.cong_doans[0].cho_phut = 200 * 60      # 200 giờ chờ ⇒ 25 ngày > 10 ngày còn lại
    db.commit()
    lt = lsx_svc.lead_time(lsx_svc.get(hop.id))
    assert lt["so_ngay"] > lt["ngay_con_lai"]
    assert "vuot_han_giao" in lsx_svc.canh_bao_cua(lsx_svc.get(hop.id))


def test_migration_0093_chay_hai_lan_van_no_op():
    """Migration phải idempotent — `run_migrations` có thể chạy lại trên DB đã nâng cấp."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import Session as RawSession

    from app.db_migrations import _migrate_lsx_routing_chi_tiet

    eng = create_engine("sqlite://")
    s = RawSession(eng)
    s.execute(text("CREATE TABLE lsx (id INTEGER PRIMARY KEY, ma VARCHAR(30))"))
    s.execute(text(
        "CREATE TABLE lsx_cong_doan (id INTEGER PRIMARY KEY, lsx_id INTEGER NOT NULL, "
        "thu_tu INTEGER NOT NULL DEFAULT 0, ten VARCHAR(255) NOT NULL DEFAULT '', "
        "nhom VARCHAR(12), don_vi VARCHAR(8) NOT NULL DEFAULT 'to', "
        "thue_ngoai BOOLEAN NOT NULL DEFAULT 0)"
    ))
    cu = [("In offset", "print", "to", 0), ("Cán màng", "finishing", "to", 1),
          ("Dán hộp", "finishing", "cai", 0), ("Chờ khô mực", "finishing", "to", 0)]
    for i, (ten, nhom, dv, tn) in enumerate(cu):
        s.execute(
            text("INSERT INTO lsx_cong_doan (id, lsx_id, thu_tu, ten, nhom, don_vi, thue_ngoai) "
                 "VALUES (:i, 1, :i, :t, :n, :d, :x)"),
            {"i": i, "t": ten, "n": nhom, "d": dv, "x": tn},
        )
    s.commit()

    _migrate_lsx_routing_chi_tiet(s)
    _migrate_lsx_routing_chi_tiet(s)          # lần 2 phải im lặng

    cols = {c["name"] for c in inspect(eng).get_columns("lsx_cong_doan")}
    assert {"loai_buoc", "don_vi_vao", "don_vi_ra", "so_nhan_cong", "di_chuyen_phut"} <= cols
    assert "thue_ngoai" not in cols and "don_vi" not in cols        # cột cũ đã bỏ
    assert "routing_goc_json" in {c["name"] for c in inspect(eng).get_columns("lsx")}

    loai = dict(s.execute(text("SELECT ten, loai_buoc FROM lsx_cong_doan")).all())
    assert loai == {"In offset": "may", "Cán màng": "thue_ngoai",
                    "Dán hộp": "to", "Chờ khô mực": "cho"}
    dv = dict(s.execute(text("SELECT ten, don_vi_vao FROM lsx_cong_doan")).all())
    assert dv["Dán hộp"] == "cai" and dv["In offset"] == "to"
    s.close()
