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


def _buoc_in_keys(lsx_svc, created) -> list[str]:
    return [
        next(c.step_key for c in sorted(lsx_svc.get(l.id).cong_doans, key=lambda c: c.thu_tu)
             if c.nhom == "print")
        for l in created
    ]


def _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin):
    """Thao tác NGƯỜI làm trên canvas: chọn bước in của từng lệnh rồi bấm Gộp.

    Bài ghép KHÔNG tự gộp — mở ra là routing đầy đủ của từng lệnh, chưa chung gì cả.
    """
    return bg_svc.gop(bai_ghep_id=bg.id, step_keys=_buoc_in_keys(lsx_svc, created), actor=admin)


def test_tao_bai_ghep_va_tinh_so_to(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)  # A=20k, B=8k
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    d = bg_svc.detail_dict(bg)

    # Đặt số con/tờ: A=4, B=2 → tờ A=ceil(20000/4)=5000, tờ B=ceil(8000/2)=4000 → chạy 5000.
    a = _by_sl(d, 20_000)
    b = _by_sl(d, 8_000)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=a["thanh_vien_id"], so_con_tren_to=4, actor=admin)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=b["thanh_vien_id"], so_con_tren_to=2, actor=admin)

    # Chưa gộp bước nào = chưa chung tờ với ai → dư chưa có nghĩa, không báo bừa một con số.
    assert all(tv["du"] == 0 for tv in bg_svc.detail_dict(bg_svc._get(bg.id))["thanh_vien"])

    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
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


def _lap_ke_hoach_moi_buoc_chung(db, bg_svc, bg, admin):
    """Gán tổ/máy/thời lượng cho mọi bước chung — gộp xong là phải lập lại kế hoạch cho lượt đó."""
    may = db.query(MayThietBi).first() or _may_in(db)
    for c in bg_svc._buoc_chungs(bg_svc._get(bg.id)):
        bg_svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bg.id, gang_step_key=c.step_key, actor=admin,
            patch={"department_id": _to_san_xuat(db).id, "may_id": may.id, "chay_phut": 60},
        )


def test_san_sang_ok_va_sua_thanh_vien_ha_ve_nhap(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)  # giấy + khổ auto, ups>0
    # Chưa gộp gì thì đây là 2 lệnh rời, không phải bài ghép → chặn sẵn sàng.
    assert "thieu_buoc_chung" in bg_svc.thieu_cua(bg_svc._get(bg.id))
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    # Gộp rồi mà chưa gán tổ/máy cho lượt chung → vẫn chặn.
    assert "thieu_ke_hoach_buoc_chung" in bg_svc.thieu_cua(bg_svc._get(bg.id))
    _lap_ke_hoach_moi_buoc_chung(db, bg_svc, bg, admin)

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


def test_du_tru_hao_cac_buoc_sau_diem_toa(db, orders, lsx_svc, bg_svc, admin, customer):
    """Số DƯ phải đi qua LƯỢT ĐI, không phải `so_to_tot × con`.

    Đây là con số từng sai 12× và 241× mà LỌT QUA trọn bộ test — chưa từng có test nào canh `du`.
    Lấy `so_to_tot × con` là bỏ sạch hao của các bước sau điểm toả: bài báo dư một đống trong khi
    thực tế vừa đủ, người kế hoạch nhìn số đó rồi bớt giấy là thiếu hàng.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)   # A=20k, B=8k
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    # Bước sau in ăn 300 cái → lượt đi phải trừ đúng 300 khi tính sản lượng thật.
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=300)

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    d = bg_svc.detail_dict(bg)
    for sl, con in ((20_000, 4), (8_000, 2)):
        bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=_by_sl(d, sl)["thanh_vien_id"],
                              so_con_tren_to=con, actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    d2 = bg_svc.detail_dict(bg_svc._get(bg.id))
    so_to_tot = d2["so_to"]["so_to_tot"]
    a = _by_sl(d2, 20_000)
    assert so_to_tot == 5_075                      # 20.300 cái ÷ 4 con/tờ, đã gồm hao bước cán

    # Lệnh A quyết định số tờ → chạy hết chuỗi riêng còn ĐÚNG số đặt, không dư.
    assert a["san_luong_du_kien"] == 20_000 and a["du"] == 0
    # Nếu ai đó tính bằng `so_to_tot × con` thì ra 20.300 → dư 300 ảo. Khoá lại đúng chỗ đó.
    assert a["san_luong_du_kien"] != so_to_tot * a["so_con_tren_to"]
    assert a["du_to"] == 0                         # A là lệnh cần nhiều tờ nhất

    # Lệnh B không có bước hao thêm nên `so_to_tot × con` mới đúng với nó — và nó dư thật.
    b = _by_sl(d2, 8_000)
    assert b["du_to"] == so_to_tot - b["nhu_cau_to"] > 0
    assert b["du"] == so_to_tot * b["so_con_tren_to"] - 8_000


def test_hao_buoc_chung_dem_dung_mot_lan_cho_ca_luot(db, orders, lsx_svc, bg_svc, admin, customer):
    """Một lần lên máy thì canh máy MỘT lần — không phải mỗi lệnh một bộ hao cho cùng lượt đó.

    Trước đây mỗi lệnh chạy chuỗi ngược riêng nên mỗi lệnh tự cộng một bộ hao canh máy; hai lệnh
    ghép chung là 2× hao cho một lần in.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    sd = bg_svc.so_do(bg_svc._get(bg.id))
    assert len(sd["gop"]) == 1
    chung = sd["gop"][0]

    # Hao của lượt chung phải bằng ĐÚNG MỘT lần tra bù hao của công đoạn ở bậc số tờ của BÀI.
    # KHÔNG assert `vao - ra == hao_hut`: `_node_chungs` viết thẳng `hao_hut = vao - ra` nên đó là
    # hằng đẳng thức, engine đếm hao hai lần test vẫn xanh.
    cd_in = next(c for c in lsx_svc.get(created[0].id).cong_doans if c.nhom == "print")
    mot_lan, _pct = bg_svc._hao_o_bac(cd_in.cong_doan_id, sd["bai_ghep"]["so_to_tot"])
    assert chung["hao_hut"] == pytest.approx(mot_lan)
    assert sd["bai_ghep"]["hao_setup_de_xuat"] == int(mot_lan)   # 1 bộ, không phải 2

    # Và bước bị đè trong từng lệnh KHÔNG còn giữ bộ hao riêng nữa (lớp đè đã chuyển tầng hao).
    for lsx in created:
        cd = next(c for c in lsx_svc.get(lsx.id).cong_doans if c.nhom == "print")
        assert float(cd.hao_hut or 0) == 0.0, "hao bước đã gộp phải nằm ở bài, không ở lệnh"


def test_to_nguyen_can_di_qua_cau_to_nguyen_sang_to(db, orders, lsx_svc, bg_svc, admin, customer):
    """"Giấy lĩnh kho" phải quy đổi qua cầu `to_nguyen → to` (số mảnh xả), KHÔNG qua con/tờ.

    Bước toả thường là bế (`to → cai`) nên hệ số của nó là con/tờ. Lấy nhầm cầu thì 5.075 tờ với
    4 con/tờ ra 1.269 tờ nguyên — ai cầm số đó đi lĩnh giấy là thiếu 3/4. Số này hiện thẳng trên
    header nên sai là sai ngay trước mắt người kế hoạch.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    # Fixture này khai bước in là `to → cai`, tức điểm toả ĐỔI ĐƠN VỊ — đúng ca dễ lấy nhầm cầu.
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=0)

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    d = bg_svc.detail_dict(bg)
    for sl, con in ((20_000, 4), (8_000, 2)):
        bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=_by_sl(d, sl)["thanh_vien_id"],
                              so_con_tren_to=con, actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    so_to = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]
    # Chuỗi seed không có bước xả → 1 tờ nguyên = 1 tờ in, giấy lĩnh kho KHÔNG ĐƯỢC nhỏ hơn tờ in.
    assert so_to["to_nguyen_can"] >= so_to["so_to_tot"], (
        f"lĩnh {so_to['to_nguyen_can']} tờ nguyên cho {so_to['so_to_tot']} tờ in là thiếu giấy"
    )
    assert so_to["to_nguyen_can"] == so_to["so_to_tot"] + so_to["hao_de_xuat"]


def test_quy_doi_don_vi_buoc_chung_tra_BANG_CAU_giong_tinh_gia(
    db, orders, lsx_svc, bg_svc, admin, customer
):
    """Quy đổi vào→ra của bước chung phải đi qua BẢNG CẦU của bài, đúng cách engine tính giá làm.

    Đơn vị vào/ra là thứ NGƯỜI khai ở danh mục công đoạn; hệ số thì BÀI cấp (`con` từ bình bài,
    `so_manh_xa` từ khổ giấy) — khai hệ số ở danh mục là đẻ nguồn sự thật thứ hai. Với bước bế
    chung, hệ số là **TỔNG con của mọi lệnh** trên tờ ghép, không phải con của một lệnh nào.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    # Helper này khai bước in là `to → cai` → bước gộp CÓ đổi đơn vị, đúng ca cần khoá.
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=0)

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    d = bg_svc.detail_dict(bg)
    for sl, con in ((20_000, 4), (8_000, 2)):
        bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=_by_sl(d, sl)["thanh_vien_id"],
                              so_con_tren_to=con, actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    chung = bg_svc._buoc_chungs(bg_svc._get(bg.id))[0]
    assert (chung.don_vi_vao, chung.don_vi_ra) == ("to", "cai"), "phải snapshot đơn vị đã khai"
    assert float(chung.he_so_quy_doi) == 6.0, "4 + 2 con/tờ — TỔNG, không phải con của một lệnh"
    # Vào đếm TỜ, ra đếm CON. Ra / hệ số = tờ tốt, luôn ≤ tờ vào (phần chênh chính là hao).
    assert float(chung.so_luong_ra) / 6.0 <= float(chung.so_luong_vao)
    assert float(chung.hao_hut) >= 0

    node = next(g for g in bg_svc.so_do(bg_svc._get(bg.id))["gop"]
                if g["step_key"] == chung.step_key)
    assert (node["don_vi_vao"], node["don_vi_ra"]) == ("to", "cai")
    assert node["so_luong_ra"] == pytest.approx(float(chung.so_luong_ra))


def _hoa_thanh_sach(db, lsx, *, so_trang=160, trang_moi_tay=16):
    """Biến một lệnh thành SÁCH gấp tay: 160 trang / 16 trang mỗi tay → 10 tay = 10 TỜ mỗi cuốn."""
    lsx.quy_cach_json = {**(lsx.quy_cach_json or {}),
                         "so_trang": so_trang, "trang_moi_tay": trang_moi_tay}
    db.commit()
    return lsx


def test_ruot_sach_khong_vao_duoc_bai_ghep(db, orders, lsx_svc, bg_svc, admin, customer):
    """Ruột sách KHÔNG ghép chung tờ được — chặn ở CẢ hàng chờ lẫn cửa ghi.

    Một cuốn 10 tay = 10 TỜ IN KHÁC NHAU, mỗi tay một bộ kẽm. Mô hình bài ghép giả định mỗi thành
    viên góp ĐÚNG MỘT bố cục tờ (`so_con_tren_to`), nên không diễn tả nổi — cho vào là ra số vô
    nghĩa chứ không phải số xấp xỉ.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    sach = _hoa_thanh_sach(db, lsx_svc.get(created[0].id))
    bia = created[1]                      # `trang_moi_tay` = 1 → hàng cắt rời

    # Hàng chờ: sách biến mất, bìa vẫn còn.
    cho = {r["lsx_id"] for r in bg_svc.hang_cho_ghep()}
    assert sach.id not in cho
    assert bia.id in cho, "bìa sách là hàng cắt rời, KHÔNG được chặn nhầm"

    # Cửa ghi phải chặn độc lập — hàng chờ chỉ là bộ lọc hiển thị, API vẫn gọi thẳng được.
    with pytest.raises(BaiGhepValidationError) as e:
        bg_svc.tao(lsx_ids=[sach.id, bia.id], actor=admin)
    assert "10 tay/cuốn" in str(e.value)   # câu báo nói rõ VÌ SAO, không chỉ "không hợp lệ"

    # Và chặn cả ở cửa thêm-thành-viên, không riêng lúc tạo.
    bg = bg_svc.tao(lsx_ids=[bia.id], actor=admin)
    with pytest.raises(BaiGhepValidationError):
        bg_svc.them_thanh_vien(bai_ghep_id=bg.id, lsx_ids=[sach.id], actor=admin)


def test_cai_moi_to_cua_bai_van_theo_dung_luat_gap_tay(db, orders, lsx_svc, bg_svc, admin, customer):
    """`_cai_moi_to` vẫn phải theo luật chung, kể cả khi cửa vào đã chặn sách.

    Chặn là chính sách ở CỬA; hệ số là LUẬT. Để hệ số sai rồi dựa vào cửa chặn là đặt cược rằng
    cửa không bao giờ hở — mà cửa thì thay đổi (vd sau này cho ghép theo từng tay).
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    sach = _hoa_thanh_sach(db, lsx_svc.get(created[0].id))
    cat_roi = lsx_svc.get(created[1].id)

    assert bg_svc._cai_moi_to(sach, 4) == pytest.approx(0.1), "10 tờ = 1 cuốn, `con` không tính"
    assert bg_svc._cai_moi_to(cat_roi, 2) == 2.0


def test_the_buoc_bi_de_hien_so_cua_luot_chung_khong_phai_nhu_cau_rieng(
    db, orders, lsx_svc, bg_svc, admin, customer
):
    """Lệnh nhỏ trong bài cần 4.000 tờ nhưng bài chạy 5.075 → nó THẬT SỰ nhận 5.075.

    Để thẻ hiện nhu cầu riêng (4.000) thì nó đá nhau với chính chip "dư tờ 1.075" ngay bên cạnh,
    và đá cả với sản lượng dự kiến của nhánh. Kiểm chéo: dư tờ × con = dư thành phẩm.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    lsx_b = next(l for l in created if l.so_luong_dat == 8_000)
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=300)

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    d = bg_svc.detail_dict(bg)
    for sl, con in ((20_000, 4), (8_000, 2)):
        bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=_by_sl(d, sl)["thanh_vien_id"],
                              so_con_tren_to=con, actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    sd = bg_svc.so_do(bg_svc._get(bg.id))
    so_to_tot = sd["bai_ghep"]["so_to_tot"]
    assert so_to_tot == 5_075                      # max(5.075 của A, 4.000 của B)

    nh_b = next(n for n in sd["nhanh"] if n["lsx_id"] == lsx_b.id)
    in_b = next(b for b in nh_b["buoc"] if b["gop_step_key"])
    assert in_b["so_luong_vao"] == so_to_tot, "bước bị đè phải nhận số TỜ của lượt chung"
    assert in_b["so_luong_ra"] == so_to_tot * 2, "qua cầu thì nhân con/tờ của CHÍNH lệnh này"
    assert in_b["so_luong_ra"] == nh_b["san_luong_du_kien"]   # thẻ khớp nhánh

    # Kiểm chéo cầu: dư TỜ × con/tờ = dư THÀNH PHẨM. Lệch là cầu quy đổi sai ở đâu đó.
    assert nh_b["du_to"] == 1_075
    assert nh_b["du_to"] * 2 == nh_b["du"] == 2_150


def test_so_luong_buoc_chung_duoc_GHI_xuong_db(db, orders, lsx_svc, bg_svc, admin, customer):
    """Số của bước chung là DẪN XUẤT nhưng vẫn phải GHI — `thoi_luong_buoc()` đọc `so_luong_vao`
    để suy giờ chạy, và màn lệnh đọc mấy cột này. Không ghi thì cả hai đọc ra 0."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    chung = bg_svc._buoc_chungs(bg_svc._get(bg.id))[0]
    assert float(chung.so_luong_vao) > 0, "cột số của bước chung không được để trống"
    assert float(chung.so_luong_ra) > 0

    # Đổi con/tờ → số của bước chung phải đổi theo, không được thiu.
    tv = bg_svc._get(bg.id).thanh_viens[0]
    truoc = float(bg_svc._buoc_chungs(bg_svc._get(bg.id))[0].so_luong_vao)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv.id,
                          so_con_tren_to=max(1, tv.so_con_tren_to // 2), actor=admin)
    assert float(bg_svc._buoc_chungs(bg_svc._get(bg.id))[0].so_luong_vao) != truoc


def test_khoi_bai_ghep_cua_lenh_khong_bi_response_model_nuot(
    db, orders, lsx_svc, bg_svc, admin, customer
):
    """Mọi khoá service trả phải SỐNG SÓT qua response model.

    Đã dính một lần: service trả `buoc_bi_de` mà `LsxBaiGhepOut` quên khai, pydantic lọc mất, nên
    badge mã bài ghép và hai-số ở màn lệnh thành code chết — FE dùng optional chaining nên không
    crash, nó chỉ im lặng không hiện gì. Không test nào bắt được.
    """
    from app.schemas.lsx import LsxBaiGhepOut

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    d = lsx_svc._bai_ghep_dict(lsx_svc.get(created[0].id))
    assert d and d["buoc_bi_de"], "service phải trả lớp đè của lệnh"
    ra = LsxBaiGhepOut.model_validate(d).model_dump()
    assert set(d) <= set(ra), f"response model nuốt mất khoá: {set(d) - set(ra)}"

    de = next(iter(ra["buoc_bi_de"].values()))
    assert de["so_luong_vao"] > 0, "màn lệnh sẽ hiện 'bài cấp 0 tờ'"
    assert de["ten"] and de["gop_step_key"]


def test_lenh_roi_bai_thi_lop_de_di_theo(db, orders, lsx_svc, bg_svc, admin, customer):
    """Bỏ thành viên phải dọn lớp đè của nó.

    Để lại map mồ côi thì lệnh đã rời bài vẫn bị chặn sửa routing ("tách bước khỏi bài trước") mà
    UI không còn đường nào để tách — người dùng vào ngõ cụt. Nó cũng vẫn bị bỏ hao ở bước in dù
    không còn ghép với ai, tức mua thiếu giấy.
    """
    from app.models.bai_ghep_cong_doan import BaiGhepCongDoanMap
    from app.schemas.lsx import LsxCongDoanIn

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    assert db.query(BaiGhepCongDoanMap).count() == 2

    tv = next(t for t in bg_svc._get(bg.id).thanh_viens if t.lsx_id == created[0].id)
    bg_svc.bo_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv.id, actor=admin)

    # Lượt chung còn một mình một lệnh thì không còn là "chạy chung" → xoá cả dòng lẫn map.
    assert db.query(BaiGhepCongDoanMap).count() == 0
    assert bg_svc._buoc_chungs(bg_svc._get(bg.id)) == []

    # Và lệnh vừa rời bài phải sửa routing được ngay, không bị lớp đè cũ khoá.
    lsx_a = lsx_svc.get(created[0].id)
    lsx_svc.replace_routing(lsx_id=lsx_a.id, actor=admin, rows_in=[
        LsxCongDoanIn(step_key=c.step_key, ten=c.ten, nhom=c.nhom, cong_doan_id=c.cong_doan_id)
        for c in sorted(lsx_a.cong_doans, key=lambda c: c.thu_tu)
    ])


def test_tao_bai_ghep_khong_tu_gop_buoc_nao(db, orders, lsx_svc, bg_svc, admin, customer):
    """Mở bài ra là routing ĐẦY ĐỦ của từng lệnh, không có node "in chung tờ" nào tự mọc ra.

    Ghép bài chung cả CTP/cán/bế chứ không riêng bước in, nên máy đoán hộ vừa sai vừa cướp mất
    quyết định của người lập kế hoạch.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)

    assert bg_svc._buoc_chungs(bg_svc._get(bg.id)) == []
    assert "thieu_buoc_chung" in bg_svc.thieu_cua(bg_svc._get(bg.id))
    sd = bg_svc.so_do(bg_svc._get(bg.id))
    assert sd["gop"] == []
    assert all(not b["gop_step_key"] for n in sd["nhanh"] for b in n["buoc"])


def test_lenh_hai_luot_in_gop_dung_luot_nguoi_chon(db, orders, lsx_svc, bg_svc, admin, customer):
    """In 2 lượt (mặt trước / mặt sau tách dòng) → chỉ lượt NGƯỜI chọn bị đè, lượt kia chạy riêng."""
    from app.schemas.lsx import LsxCongDoanIn

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = lsx_svc.get(created[0].id)
    in_cu = sorted(lsx_a.cong_doans, key=lambda c: c.thu_tu)[0]
    lsx_svc.replace_routing(lsx_id=lsx_a.id, actor=admin, rows_in=[
        LsxCongDoanIn(step_key=in_cu.step_key, ten=in_cu.ten, nhom="print",
                      cong_doan_id=in_cu.cong_doan_id, may_id=in_cu.may_id),
        LsxCongDoanIn(ten="In offset mặt sau", nhom="print",
                      cong_doan_id=in_cu.cong_doan_id, may_id=in_cu.may_id),
    ])
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)

    luot_2 = sorted(lsx_svc.get(lsx_a.id).cong_doans, key=lambda c: c.thu_tu)[1]
    in_b = next(c for c in sorted(lsx_svc.get(created[1].id).cong_doans, key=lambda c: c.thu_tu)
                if c.nhom == "print")
    bg_svc.gop(bai_ghep_id=bg.id, step_keys=[luot_2.step_key, in_b.step_key], actor=admin)

    sd = bg_svc.so_do(bg_svc._get(bg.id))
    nh = next(n for n in sd["nhanh"] if n["lsx_id"] == lsx_a.id)
    bi_de = {b["step_key"] for b in nh["buoc"] if b["gop_step_key"]}
    assert bi_de == {luot_2.step_key}          # lượt 1 vẫn chạy riêng, không bị nuốt theo
    assert nh["toa_step_key"] == luot_2.step_key


def test_mot_lenh_khong_gop_hai_buoc_vao_cung_mot_luot(db, orders, lsx_svc, bg_svc, admin, customer):
    """Hai lượt in của CÙNG một lệnh là hai lần lên máy — gộp làm một là bịa mất một lượt."""
    from app.schemas.lsx import LsxCongDoanIn

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = lsx_svc.get(created[0].id)
    in_cu = sorted(lsx_a.cong_doans, key=lambda c: c.thu_tu)[0]
    lsx_svc.replace_routing(lsx_id=lsx_a.id, actor=admin, rows_in=[
        LsxCongDoanIn(step_key=in_cu.step_key, ten=in_cu.ten, nhom="print",
                      cong_doan_id=in_cu.cong_doan_id, may_id=in_cu.may_id),
        LsxCongDoanIn(ten="In offset mặt sau", nhom="print",
                      cong_doan_id=in_cu.cong_doan_id, may_id=in_cu.may_id),
    ])
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    hai_luot = sorted(lsx_svc.get(lsx_a.id).cong_doans, key=lambda c: c.thu_tu)[:2]

    with pytest.raises(BaiGhepValidationError):
        bg_svc.gop(bai_ghep_id=bg.id, step_keys=[c.step_key for c in hai_luot], actor=admin)


def test_chi_gop_duoc_cac_buoc_cung_cong_doan(db, orders, lsx_svc, bg_svc, admin, customer):
    """Điều kiện gộp là CÙNG CÔNG ĐOẠN — quy cách thì người dùng có nghiệp vụ đó, máy không phán."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=0)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)

    can_a = next(c for c in lsx_svc.get(lsx_a.id).cong_doans if c.ten == "Cán màng")
    in_b = next(c for c in sorted(lsx_svc.get(created[1].id).cong_doans, key=lambda c: c.thu_tu)
                if c.nhom == "print")
    with pytest.raises(BaiGhepValidationError):
        bg_svc.gop(bai_ghep_id=bg.id, step_keys=[can_a.step_key, in_b.step_key], actor=admin)


def test_tach_tra_lai_so_rieng_cua_tung_lenh(db, orders, lsx_svc, bg_svc, admin, customer):
    """Ghi đè, KHÔNG phá gốc: tách gộp ra là số cũ quay lại, không phải khôi phục từ đâu cả."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    truoc = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]["so_to_tot"]

    bg_svc.gop(bai_ghep_id=bg.id, step_keys=_buoc_in_keys(lsx_svc, created), actor=admin)
    chung = bg_svc._buoc_chungs(bg_svc._get(bg.id))
    assert len(chung) == 1

    bg_svc.tach(bai_ghep_id=bg.id, gang_step_key=chung[0].step_key, actor=admin)
    assert bg_svc._buoc_chungs(bg_svc._get(bg.id)) == []
    assert bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]["so_to_tot"] == truoc


def test_chan_bo_buoc_dang_gop_khi_sua_routing(db, orders, lsx_svc, bg_svc, admin, customer):
    """Bỏ bước đang chạy chung = bài mất chỗ bám. Chặn, không để lớp đè trỏ vào key đã chết."""
    from app.schemas.lsx import LsxCongDoanIn
    from app.services.lsx_service import LsxConflict

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    lsx_a = lsx_svc.get(created[0].id)

    # Chưa gộp thì sửa routing thoải mái — bài chưa bám vào bước nào của lệnh.
    lsx_svc.replace_routing(lsx_id=lsx_a.id, actor=admin, rows_in=[
        LsxCongDoanIn(step_key=c.step_key, ten=c.ten, nhom=c.nhom, cong_doan_id=c.cong_doan_id)
        for c in sorted(lsx_svc.get(lsx_a.id).cong_doans, key=lambda c: c.thu_tu)
    ])
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    with pytest.raises(LsxConflict):
        lsx_svc.replace_routing(lsx_id=lsx_a.id, actor=admin, rows_in=[
            LsxCongDoanIn(ten="Cán màng", nhom="finishing"),      # bước đang gộp biến mất
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


def test_so_do_giu_routing_day_du_va_khong_luu_canh(db, orders, lsx_svc, bg_svc, admin, customer):
    """Sơ đồ: mỗi lệnh giữ routing ĐẦY ĐỦ; bước đã gộp được đánh dấu `gop_step_key`, không biến mất."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_a = next(l for l in created if l.so_luong_dat == 20_000)
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=0)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    sd = bg_svc.so_do(bg_svc._get(bg.id))
    assert sd["bai_ghep"]["ma"] == bg.ma
    assert len(sd["nhanh"]) == 2
    nh = next(n for n in sd["nhanh"] if n["lsx_id"] == lsx_a.id)

    # Bước in VẪN nằm trong routing của lệnh, chỉ mang thêm dấu bị đè.
    bi_de = [b for b in nh["buoc"] if b["gop_step_key"]]
    assert len(bi_de) == 1 and bi_de[0]["nhom"] == "print"
    assert "Cán màng" in [b["ten"] for b in nh["buoc"]]
    assert nh["mau"] != next(n for n in sd["nhanh"] if n["lsx_id"] != lsx_a.id)["mau"]

    # Một thẻ chung, mang đủ hai lệnh nó đè lên.
    assert len(sd["gop"]) == 1
    assert {tv["lsx_id"] for tv in sd["gop"][0]["thanh_vien"]} == {l.id for l in created}
    assert sd["gop"][0]["ma_bai_ghep"] == bg.ma

    # Không có cạnh nào được lưu thêm: đồ thị dựng lúc đọc từ thành viên + routing + lớp đè.
    from app.models.lsx import LsxCongDoanPhuThuoc
    truoc = db.query(LsxCongDoanPhuThuoc).count()
    bg_svc.so_do(bg_svc._get(bg.id))
    assert db.query(LsxCongDoanPhuThuoc).count() == truoc
