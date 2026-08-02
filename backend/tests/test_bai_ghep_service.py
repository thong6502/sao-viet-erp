"""Bài ghép (print gang) — service-level tests.

Dựng 2 LSX in offset cùng giấy, cùng `san_sang` → gom vào 1 bài ghép → kiểm số tờ (`max(ceil)`),
dư, guard '1 LSX ≤ 1 bài', gate 'sẵn sàng', và coupling: chặn xoá LSX đang ghép.

Tái dùng luồng thật (đơn → chuyển SX → tạo lệnh) qua helper của `test_lsx_service`; routing sản
phẩm cố ý CHỈ có bước In để LSX dễ đạt `san_sang` (không vướng khuôn/hệ số).
"""
from __future__ import annotations

from datetime import date, timedelta
from math import ceil

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan
from app.models.customer import Customer
from app.models.department import Department
from app.models.lsx import TT_SAN_SANG
from app.models.may_thiet_bi import MayThietBi
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuThanhPham, PhieuTinhGia
from app.models.quotation import STATUS_ACCEPTED, Quote, QuoteItem, QuoteVersion
from app.models.user import User
from app.models.vat_lieu_kho import GiayNguyen
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.bai_ghep_repo import BaiGhepRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.lsx_repo import LsxRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.order import OrderCreate, OrderDepositReceiptIn, OrderUpdate
from app.seed import seed_all
from app.services.accounting_service import AccountingService
from app.services.bai_ghep_service import (
    BaiGhepConflict,
    BaiGhepService,
    BaiGhepValidationError,
)
from app.services.lsx_service import LsxConflict, LsxService
from app.services.order_service import OrderService
from app.services.sequence_service import SequenceService


# --- helper dựng nguồn (copy từ test_lsx_service để test tự-chứa) -------------
def _to_san_xuat(db) -> Department:
    to = db.query(Department).filter(Department.la_san_xuat.is_(True)).first()
    if to is None:
        to = Department(name="Tổ In test", code="TO-IN-BG", la_san_xuat=True)
        db.add(to)
        db.flush()
    return to


def _may_in(db) -> MayThietBi:
    may = MayThietBi(
        ma="MAY-IN-BG", ten="Máy in 4 màu", loai_may="press_offset_sheet",
        toc_do=5_000, don_vi_toc_do="to_gio", thoi_gian_rua_muc=15,
        kho_max_dai=1020, kho_max_rong=720,
    )
    db.add(may)
    db.flush()
    return may


def _quote_from_ptg(db, customer, ptg: PhieuTinhGia) -> Quote:
    q = Quote(quote_number="BG-BGHEP", customer_id=customer.id, status=STATUS_ACCEPTED,
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
    q = _quote_from_ptg(db, customer, ptg)
    d = orders.create(actor=admin, scope="all",
                      payload=OrderCreate(source_type="bao_gia", quotation_id=q.id, deposit_pct=50))
    orders.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                               payload=OrderDepositReceiptIn(receipt_method="cash",
                                                             amount=d.deposit_required))
    orders.update(order_id=d.id, actor=admin, scope="all", payload=OrderUpdate(
        customer_po_no="PO-BG", delivery_committed_date=date.today() + timedelta(days=10),
    ))
    return orders.confirm(order_id=d.id, actor=admin, scope="all")


def _don_da_chuyen_sx(db, orders, admin, customer, ptg):
    d = _don_da_chot(db, orders, admin, customer, ptg)
    return orders.release_production(order_id=d.id, actor=admin, scope="all")


# --- fixtures ----------------------------------------------------------------
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
    c = Customer(code="KH-BG", name="KH Bài ghép")
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


@pytest.fixture
def bg_svc(db):
    return BaiGhepService(
        db, BaiGhepRepository(db), AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


# --- dựng nguồn: 2 sản phẩm CÙNG GIẤY, mỗi cái chỉ có bước In ------------------
def _ptg_2_in(db, *, sl_a=20_000, sl_b=8_000) -> PhieuTinhGia:
    giay = GiayNguyen(
        ma="G-IV350B", ten="Ivory 350", gsm=350, don_gia=25_000, don_vi_gia="tan",
        cong_thuc_gia="to_nguyen * dai_nguyen * rong_nguyen * dinh_luong * don_gia / 1000",
    )
    db.add(giay)
    to_id = _to_san_xuat(db).id
    may = _may_in(db)
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()
    if cd_in is None:
        cd_in = CongDoan(ma="CD-IN-B", ten="In offset", nhom="print",
                         cong_thuc_gia="so_luong * don_gia")
        db.add(cd_in)
    cd_in.department_id = cd_in.department_id or to_id
    cd_in.setup_time = 45
    db.flush()

    def _sp(thu_tu, ten, sl, dai, rong):
        sp = PhieuThanhPhan(
            thu_tu=thu_tu, ten=ten, so_luong=sl, don_vi_tinh="cái",
            dai_thanh_pham=dai, rong_thanh_pham=rong, giay_id=giay.id,
            kho_nguyen_dai=790, kho_nguyen_rong=1090, kho_in_dai=650, kho_in_rong=900,
            so_mau_a=4, so_mau_b=0, quy_cach_in="mot_mat", may_id=may.id,
        )
        sp.thanh_phams.append(
            PhieuThanhPham(thu_tu=0, cong_doan_id=cd_in.id, ten="In offset", don_gia=200)
        )
        return sp

    p = PhieuTinhGia(ma="PTG-GHEP-0001", ten_san_pham="2 hộp ghép", so_luong=sl_a)
    p.thanh_phans.extend([_sp(0, "Hộp A", sl_a, 200, 150), _sp(1, "Hộp B", sl_b, 180, 120)])
    db.add(p)
    db.commit()
    return p


def _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer, **kw):
    """2 LSX in cùng giấy, đã `san_sang`. Trả list[Lsx]."""
    ptg = _ptg_2_in(db, **kw)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    created = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    for l in created:
        lsx_svc.set_trang_thai(lsx_id=l.id, trang_thai=TT_SAN_SANG, actor=admin)
    return created


def _by_sl(detail: dict, sl: int) -> dict:
    return next(tv for tv in detail["thanh_vien"] if tv["so_luong_dat"] == sl)


# --- tests -------------------------------------------------------------------
def test_hang_cho_ghep_hien_2_lsx_cung_giay(db, orders, lsx_svc, bg_svc, admin, customer):
    _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    rows = bg_svc.hang_cho_ghep()
    assert len(rows) == 2
    assert all(r["giay_ten"] == "Ivory 350" for r in rows)


def test_tao_bai_ghep_va_tinh_so_to(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)  # A=20k, B=8k
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    d = bg_svc.detail_dict(bg)

    # Đặt số con/tờ: A=4, B=2 → tờ A=ceil(20000/4)=5000, tờ B=ceil(8000/2)=4000 → chạy 5000.
    a = _by_sl(d, 20_000)
    b = _by_sl(d, 8_000)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=a["thanh_vien_id"], so_con_tren_to=4, actor=admin)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=b["thanh_vien_id"], so_con_tren_to=2, actor=admin)

    d2 = bg_svc.detail_dict(bg_svc._get(bg.id))
    assert d2["so_to"]["so_to_tot"] == 5000
    assert _by_sl(d2, 20_000)["du"] == 0            # 5000×4 − 20000
    assert _by_sl(d2, 8_000)["du"] == 2000          # 5000×2 − 8000
    # tao đồng nhất giấy → gợi ý sẵn giấy + khổ chung.
    assert d2["giay_id"] is not None and d2["kho_in_dai"] == 650


def test_guard_mot_lsx_toi_da_mot_bai(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    a = created[0].id
    bg_svc.tao(lsx_ids=[a], actor=admin)
    with pytest.raises(BaiGhepConflict):
        bg_svc.tao(lsx_ids=[a], actor=admin)


def test_gate_san_sang_can_it_nhat_2_thanh_vien(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg1 = bg_svc.tao(lsx_ids=[created[0].id], actor=admin)      # chỉ 1 thành viên
    assert "thieu_thanh_vien" in bg_svc.thieu_cua(bg_svc._get(bg1.id))
    with pytest.raises(BaiGhepConflict):
        bg_svc.set_trang_thai(bai_ghep_id=bg1.id, trang_thai=TT_SAN_SANG, actor=admin)


def test_san_sang_ok_va_sua_thanh_vien_ha_ve_nhap(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)  # giấy + khổ auto, ups>0
    bg = bg_svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai=TT_SAN_SANG, actor=admin)
    assert bg.trang_thai == TT_SAN_SANG
    tv0 = bg_svc.detail_dict(bg)["thanh_vien"][0]["thanh_vien_id"]
    bg = bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv0, so_con_tren_to=6, actor=admin)
    assert bg.trang_thai == "nhap"  # sửa thành viên khi đã sẵn sàng → tự rớt nháp


def test_xoa_lsx_dang_ghep_bi_chan(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    with pytest.raises(LsxConflict):
        lsx_svc.xoa(lsx_id=created[0].id, actor=admin)


def test_tao_chan_lsx_khong_co_cong_doan_in(db, orders, lsx_svc, bg_svc, admin, customer):
    from app.models.lsx import LsxCongDoan
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Gỡ công đoạn IN của 1 LSX (giả lập lệnh không có bước in) → không được ghép.
    db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == created[0].id, LsxCongDoan.nhom == "print"
    ).delete(synchronize_session=False)
    db.commit()
    with pytest.raises(BaiGhepValidationError):
        bg_svc.tao(lsx_ids=[created[0].id, created[1].id], actor=admin)


# ============ Số tờ theo NHU CẦU THẬT + neo bước in ============
# Công thức cũ `ceil(SL đặt / con)` lấy số thành phẩm GIAO KHÁCH, bỏ mất hao của các bước sau in
# (gấp, bắt tay, vào keo, xén) → bài ghép cấp không đủ giấy mà không ai báo.


def _them_buoc_hao_sau_in(db, lsx_svc, lsx, actor, *, so_to_bu_hao: int):
    """Nối thêm bước SAU IN có bù hao cố định. Bước in của seed nhả `cái`, nên bước sau nó
    cũng đếm `cái` — hao ở đây phải lần ngược qua cầu tờ→cái mới ra số tờ phải in."""
    from app.schemas.lsx import LsxCongDoanIn

    # Công đoạn IN của seed không khai đơn vị → nó đứng NGOÀI dòng giấy. Khai to→cái cho nó
    # thì chuỗi mới có ranh giới tờ↔cái để hao ở bước sau lần ngược về số tờ phải in.
    cd_in = db.get(CongDoan, sorted(lsx.cong_doans, key=lambda c: c.thu_tu)[0].cong_doan_id)
    cd_in.don_vi_vao, cd_in.don_vi_ra = "to", "cai"
    db.flush()
    cd = CongDoan(
        ma=f"CD-HAO-{lsx.id}", ten="Cán màng", nhom="finishing",
        cong_thuc_gia="so_luong * don_gia",
        don_vi_vao="cai", don_vi_ra="cai",
        kieu_bu_hao="co_dinh", so_to_bu_hao=so_to_bu_hao,
        department_id=_to_san_xuat(db).id,
    )
    db.add(cd)
    db.flush()
    cu = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    lsx_svc.replace_routing(lsx_id=lsx.id, actor=actor, rows_in=[
        *[LsxCongDoanIn(step_key=c.step_key, ten=c.ten, nhom=c.nhom,
                        cong_doan_id=c.cong_doan_id) for c in cu],
        LsxCongDoanIn(ten="Cán màng", nhom="finishing", cong_doan_id=cd.id),
    ])
    return cd


def test_so_to_gom_hao_cac_buoc_sau_in(db, orders, lsx_svc, bg_svc, admin, customer):
    """Thêm bước sau in hao 300 tờ → bài phải cấp thêm đúng 300 tờ, không còn `ceil(SL/con)`."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)   # A=20k, B=8k
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    d = bg_svc.detail_dict(bg)
    a, b = _by_sl(d, 20_000), _by_sl(d, 8_000)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=a["thanh_vien_id"],
                          so_con_tren_to=4, actor=admin)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=b["thanh_vien_id"],
                          so_con_tren_to=2, actor=admin)
    truoc = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]["so_to_tot"]
    assert truoc == 5_000                       # chưa có bước sau in → đúng bằng ceil(20000/4)

    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=300)

    # Hao 300 CÁI ở bước cán → phải in 20.300 cái → 20.300 ÷ 4 con/tờ = 5.075 tờ.
    # Công thức cũ `ceil(20.000/4)` vẫn ra 5.000 → thiếu 75 tờ, không ai báo.
    d3 = bg_svc.detail_dict(bg_svc._get(bg.id))
    assert d3["so_to"]["so_to_tot"] == 5_075
    assert _by_sl(d3, 20_000)["nhu_cau_to"] == 5_075


def test_neo_buoc_in_dien_san_khi_lenh_chi_co_mot_luot(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    assert all(tv.buoc_in_step_key for tv in bg_svc._get(bg.id).thanh_viens)
    # Không thiếu dữ liệu vì máy suy được — người dùng không phải chọn gì.
    assert "thieu_buoc_in" not in bg_svc.thieu_cua(bg_svc._get(bg.id))


def test_lenh_hai_luot_in_thi_bat_chon_khong_doan(db, orders, lsx_svc, bg_svc, admin, customer):
    """In 2 lượt (mặt trước / mặt sau tách dòng) → máy KHÔNG đoán lượt nào ghép chung tờ."""
    from app.schemas.lsx import LsxCongDoanIn

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = lsx_svc.get(created[0].id)
    cu = sorted(lsx_a.cong_doans, key=lambda c: c.thu_tu)
    in_cu = cu[0]
    lsx_svc.replace_routing(lsx_id=lsx_a.id, actor=admin, rows_in=[
        LsxCongDoanIn(step_key=in_cu.step_key, ten=in_cu.ten, nhom="print",
                      cong_doan_id=in_cu.cong_doan_id, may_id=in_cu.may_id),
        LsxCongDoanIn(ten="In offset mặt sau", nhom="print",
                      cong_doan_id=in_cu.cong_doan_id, may_id=in_cu.may_id),
    ])
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    tv_a = next(tv for tv in bg_svc._get(bg.id).thanh_viens if tv.lsx_id == lsx_a.id)
    assert tv_a.buoc_in_step_key is None                       # để trống, không đoán
    assert "thieu_buoc_in" in bg_svc.thieu_cua(bg_svc._get(bg.id))

    buoc_in_2 = sorted(lsx_svc.get(lsx_a.id).cong_doans, key=lambda c: c.thu_tu)[1]
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv_a.id, so_con_tren_to=4,
                          buoc_in_step_key=buoc_in_2.step_key, actor=admin)
    assert "thieu_buoc_in" not in bg_svc.thieu_cua(bg_svc._get(bg.id))

    with pytest.raises(BaiGhepValidationError):
        bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv_a.id, so_con_tren_to=4,
                              buoc_in_step_key="khong-ton-tai", actor=admin)


def test_chan_bo_buoc_in_khi_lenh_dang_ghep(db, orders, lsx_svc, bg_svc, admin, customer):
    """Bỏ bước in của lệnh đang ghép = bài mất chỗ bám. Chặn, không để nó trỏ vào key đã chết."""
    from app.schemas.lsx import LsxCongDoanIn
    from app.services.lsx_service import LsxConflict

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    lsx_a = lsx_svc.get(created[0].id)

    with pytest.raises(LsxConflict):
        lsx_svc.replace_routing(lsx_id=lsx_a.id, actor=admin, rows_in=[
            LsxCongDoanIn(ten="Cán màng", nhom="finishing"),      # bước in biến mất
        ])


def test_sua_so_con_o_bai_thi_lenh_tinh_lai_ngay(db, orders, lsx_svc, bg_svc, admin, customer):
    """Thông số tờ của lệnh là DẪN XUẤT của bài. Không có chỗ nối này thì hai màn lệch nhau ngay
    lần gõ đầu tiên: bài nói 2 con/tờ, lệnh vẫn giữ số tờ tính theo con cũ."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=0)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    tv = next(t for t in bg_svc._get(bg.id).thanh_viens if t.lsx_id == lsx_a.id)

    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv.id, so_con_tren_to=4, actor=admin)
    db.refresh(lsx_svc.get(lsx_a.id))
    bon_con = lsx_svc.get(lsx_a.id).so_to_ke_hoach

    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv.id, so_con_tren_to=2, actor=admin)
    db.refresh(lsx_svc.get(lsx_a.id))
    hai_con = lsx_svc.get(lsx_a.id).so_to_ke_hoach

    assert bon_con == 5_000 and hai_con == 10_000        # ít con/tờ → phải in nhiều tờ hơn

    # Gỡ khỏi bài → thông số in trả về bài tính giá gốc (con/tờ của lệnh), không giữ số của bài.
    bg_svc.bo_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv.id, actor=admin)
    db.refresh(lsx_svc.get(lsx_a.id))
    l = lsx_svc.get(lsx_a.id)
    assert l.so_to_ke_hoach == ceil(20_000 / l.so_con)


def test_so_do_cat_chuoi_tai_buoc_in_va_khong_luu_canh(db, orders, lsx_svc, bg_svc, admin, customer):
    """Sơ đồ: mỗi lệnh giữ chuỗi riêng cả TRƯỚC lẫn SAU in, gặp nhau đúng một điểm là node IN."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=0)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)

    sd = bg_svc.so_do(bg_svc._get(bg.id))
    assert sd["bai_ghep"]["ma"] == bg.ma
    assert len(sd["nhanh"]) == 2
    nh = next(n for n in sd["nhanh"] if n["lsx_id"] == lsx_a.id)
    # Bước in KHÔNG nằm ở nhánh nào — nó là node IN chung ở giữa.
    keys = {c["step_key"] for c in nh["truoc_in"] + nh["sau_in"]}
    assert nh["buoc_in_step_key"] not in keys
    assert [c["ten"] for c in nh["sau_in"]] == ["Cán màng"]     # sau in là chuỗi riêng của lệnh
    assert nh["mau"] != next(n for n in sd["nhanh"] if n["lsx_id"] != lsx_a.id)["mau"]

    # Không có cạnh nào được lưu thêm: đồ thị dựng lúc đọc từ thành viên + routing.
    from app.models.lsx import LsxCongDoanPhuThuoc
    truoc = db.query(LsxCongDoanPhuThuoc).count()
    bg_svc.so_do(bg_svc._get(bg.id))
    assert db.query(LsxCongDoanPhuThuoc).count() == truoc
