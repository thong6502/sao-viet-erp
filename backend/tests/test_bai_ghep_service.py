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
        toc_do=5_000, don_vi_toc_do="to_gio",
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
def _ptg_2_in(db, *, sl_a=20_000, sl_b=8_000, sl_them: tuple[int, ...] = ()) -> PhieuTinhGia:
    """PTG 2 thành phần in cùng giấy. `sl_them` nối thêm thành phần — cần khi test tầm ngắm của
    `_do_thi_cua`: phải có lệnh CÙNG ĐƠN nhưng NGOÀI bài để đồ thị còn chỗ mà lan tới."""
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
    for i, sl in enumerate(sl_them):
        p.thanh_phans.append(_sp(2 + i, f"Hộp {chr(ord('C') + i)}", sl, 160, 100))
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
    rows = bg_svc.hang_cho_ghep()["items"]
    assert len(rows) == 2
    assert all(r["giay_ten"] == "Ivory 350" for r in rows)


def test_hang_cho_ghep_GIAU_lenh_dang_giu_cho(db, orders, lsx_svc, bg_svc, admin, customer):
    """Lệnh đã bật giữ chỗ vật tư KHÔNG hiện ở hàng chờ ghép (chủ chốt 17/08/2026).

    Bày nó ra rồi báo lỗi lúc bấm là mời người ta làm một việc không làm được. Cửa chặn ở
    `_validate_them` vẫn giữ làm chốt cuối (API gọi thẳng được), nhưng người dùng thường sẽ không
    bao giờ chạm tới nó nữa.

    Thứ tự đúng mà luật này ép ra: **ghép bài TRƯỚC, giữ chỗ SAU** — ghép làm số giấy cần ít đi,
    giữ trước rồi ghép là ôm chỗ cho một đống giấy không ai cần nữa.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx_svc.repo.get(created[0].id).giu_cho_bat = True
    db.commit()

    kq = bg_svc.hang_cho_ghep()
    assert {r["lsx_id"] for r in kq["items"]} == {created[1].id}
    assert kq["so_giu_cho"] == 1, "phải đếm được để màn nói ra vì sao lệnh kia biến mất"


def test_so_giu_cho_dem_SAU_moi_bo_loc_khac(db, orders, lsx_svc, bg_svc, admin, customer):
    """Ruột sách đang giữ chỗ KHÔNG được tính vào `so_giu_cho`.

    Đếm trước các bộ lọc kia thì con số nói dối: người dùng đọc "1 lệnh đang giữ chỗ", đi nhả chỗ,
    quay lại vẫn chẳng thấy lệnh nào hiện ra — vì nó bị chặn bởi lý do khác mà bảng không nói.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    sach = _hoa_thanh_sach(db, lsx_svc.get(created[0].id))
    lsx_svc.repo.get(sach.id).giu_cho_bat = True
    db.commit()

    kq = bg_svc.hang_cho_ghep()
    assert kq["so_giu_cho"] == 0, "ruột sách không bao giờ ghép được — nhả chỗ cũng chẳng hiện ra"
    assert {r["lsx_id"] for r in kq["items"]} == {created[1].id}


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
    # `so_con_tren_to` khởi tạo từ `lsx.so_con` — số con khi lệnh còn đứng RIÊNG, tự tính như thể
    # được cả tờ. Ghép 2 lệnh cùng tờ mà giữ nguyên cả hai số đó là chồng diện tích → gate mới
    # `vuot_dien_tich` chặn đúng, người bình bài phải TỰ chia lại tờ trước khi sẵn sàng.
    d = bg_svc.detail_dict(bg_svc._get(bg.id))
    a_tv = _by_sl(d, 20_000)["thanh_vien_id"]
    b_tv = _by_sl(d, 8_000)["thanh_vien_id"]
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=a_tv, so_con_tren_to=4, actor=admin)
    bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=b_tv, so_con_tren_to=2, actor=admin)

    bg = bg_svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai=TT_SAN_SANG, actor=admin)
    assert bg.trang_thai == TT_SAN_SANG
    tv0 = bg_svc.detail_dict(bg)["thanh_vien"][0]["thanh_vien_id"]
    bg = bg_svc.sua_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv0, so_con_tren_to=6, actor=admin)
    assert bg.trang_thai == "nhap"  # sửa thành viên khi đã sẵn sàng → tự rớt nháp


def test_thieu_cua_khac_giay(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    b = created[1]
    qc_b = dict(b.quy_cach_json or {})
    qc_b["giay_id"] = (qc_b.get("giay_id") or 0) + 9999
    b.quy_cach_json = qc_b
    db.commit()
    bg = bg_svc._get(bg.id)
    assert "khac_giay" in bg_svc.thieu_cua(bg)


def test_thieu_cua_buoc_chung_thieu_thanh_vien(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer, sl_them=(5000,))
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created[:2], admin)  # chỉ gộp 2/3 thành viên
    bg = bg_svc._get(bg.id)
    assert "buoc_chung_thieu_thanh_vien" in bg_svc.thieu_cua(bg)


def test_thieu_cua_buoc_chung_tren_giay(db, orders, lsx_svc, bg_svc, admin, customer):
    from app.models.lsx import LsxCongDoan
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id.in_([l.id for l in created])
    ).update(
        {LsxCongDoan.don_vi_vao: "khong_ton_tai", LsxCongDoan.don_vi_ra: "khong_ton_tai"},
        synchronize_session=False,
    )
    db.commit()
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    bg = bg_svc._get(bg.id)
    assert "thieu_buoc_chung_tren_giay" in bg_svc.thieu_cua(bg)


def test_thieu_cua_vuot_con_toi_da(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    bg.thanh_viens[0].so_con_tren_to = 9999
    db.commit()
    bg = bg_svc._get(bg.id)
    assert "vuot_con_toi_da" in bg_svc.thieu_cua(bg)


def test_thieu_cua_vuot_dien_tich(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    bg.kho_in_dai = 1
    bg.kho_in_rong = 1
    db.commit()
    bg = bg_svc._get(bg.id)
    assert "vuot_dien_tich" in bg_svc.thieu_cua(bg)


def test_xoa_lsx_dang_ghep_bi_chan(db, orders, lsx_svc, bg_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    with pytest.raises(LsxConflict):
        lsx_svc.xoa(lsx_id=created[0].id, actor=admin)


def test_ghep_khong_bat_buoc_co_buoc_in(db, orders, lsx_svc, bg_svc, admin, customer):
    """§5(b): bỏ chặn "phải có bước IN" — bài chỉ gộp CTP/cán vẫn hợp lệ. CHỈ chặn lệnh KHÔNG có
    công đoạn nào (không ghép được gì với ai)."""
    from app.models.lsx import LsxCongDoan
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)

    # Lệnh chỉ có công đoạn SAU IN (đổi bước in thành finishing) → NAY được ghép (trước đây chặn).
    db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == created[0].id, LsxCongDoan.nhom == "print"
    ).update({LsxCongDoan.nhom: "finishing"}, synchronize_session=False)
    db.commit()
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    assert bg.id

    # Nhưng lệnh KHÔNG còn công đoạn nào thì vẫn chặn.
    bg_svc.xoa(bai_ghep_id=bg.id, actor=admin)
    db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == created[0].id
    ).delete(synchronize_session=False)
    db.commit()
    with pytest.raises(BaiGhepValidationError):
        bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)


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


def _resync_don_vi(lsx_svc, lsx_id, actor) -> None:
    """Lưu lại NGUYÊN routing hiện có để ép đơn vị của lệnh đọc lại danh mục công đoạn mới nhất.

    Đơn vị của một bước là BẢN SAO chỉ đồng bộ lại khi CHÍNH lệnh đó được ghi — dùng khi test vừa
    đổi đơn vị ở một công đoạn DÙNG CHUNG cho lệnh khác, còn lệnh này chưa đụng gì tới nên vẫn giữ
    bản sao cũ (xem `LsxService._ap_chuoi_nguoc`)."""
    from app.schemas.lsx import LsxCongDoanIn

    cu = sorted(lsx_svc.get(lsx_id).cong_doans, key=lambda c: c.thu_tu)
    lsx_svc.replace_routing(lsx_id=lsx_id, actor=actor, rows_in=[
        LsxCongDoanIn(step_key=c.step_key, ten=c.ten, nhom=c.nhom, cong_doan_id=c.cong_doan_id)
        for c in cu
    ])


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
    cho = {r["lsx_id"] for r in bg_svc.hang_cho_ghep()["items"]}
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


def test_ty_le_hao_va_breakdown_hao_theo_buoc(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """T1+T4: `ty_le_hao` = hao/tốt (cảnh báo makeready nuốt sản lượng), breakdown per bước khớp tổng."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    cd_in = db.get(CongDoan, sorted(
        lsx_svc.get(created[0].id).cong_doans, key=lambda c: c.thu_tu)[0].cong_doan_id)
    cd_in.kieu_bu_hao, cd_in.so_to_bu_hao = "co_dinh", 250
    db.commit()

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    so_to = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]

    assert so_to["hao_de_xuat"] == 250
    assert so_to["ty_le_hao"] == round(
        (so_to["tong_to"] - so_to["so_to_tot"]) / so_to["so_to_tot"] * 100, 1
    )
    assert so_to["ty_le_hao"] > 0, "hao 250 trên lô nhỏ phải cho tỷ lệ > 0"
    # T4: breakdown có mặt bước In và cộng lại đúng bằng tổng đề xuất.
    assert so_to["hao_theo_buoc"], "phải liệt kê hao từng bước chung"
    assert sum(b["hao"] for b in so_to["hao_theo_buoc"]) == so_to["hao_de_xuat"]


def test_may_hop_cong_doan_bat_may_sai_loai(db, bg_svc):
    """T3: máy Bế gán cho công đoạn In (chỉ cho "Máy in"/"In ngoài") → cảnh báo mềm; máy đúng loại
    thì không. Chưa khai `nhom_may_cho_phep` → không ràng buộc (không đẻ cảnh báo giả)."""
    cd_in = CongDoan(ma="CD-T3", ten="In test", nhom="print",
                     nhom_may_cho_phep=["Máy in", "In ngoài"])
    may_be = MayThietBi(ma="BE-T3", ten="Máy bế test", loai_may="Bế")
    may_in = MayThietBi(ma="IN-T3", ten="Máy in test", loai_may="Máy in")

    assert bg_svc._may_hop_cong_doan(may_be, cd_in, {}), "máy Bế cho công đoạn In phải bị cảnh báo"
    assert bg_svc._may_hop_cong_doan(may_in, cd_in, {}) == [], "máy In hợp công đoạn In → im"

    cd_khong_khai = CongDoan(ma="CD-T3b", ten="X", nhom="print", nhom_may_cho_phep=None)
    assert bg_svc._may_hop_cong_doan(may_be, cd_khong_khai, {}) == [], "chưa khai ràng buộc → im"


def test_con_toi_da_theo_kho_xoay_90(db, bg_svc):
    """D3: con/tờ tối đa = khổ tờ in ÷ khổ thành phẩm, lấy hướng xếp được NHIỀU hơn (xoay 90°)."""
    from app.models.bai_ghep import BaiGhep
    from app.models.lsx import Lsx

    bg = BaiGhep(ma="GB-T3", kho_in_dai=860, kho_in_rong=650)
    l = Lsx(quy_cach_json={"dai_thanh_pham": 86, "rong_thanh_pham": 54})
    # thẳng floor(860/86)*floor(650/54)=10*12=120 ; xoay floor(860/54)*floor(650/86)=15*7=105 → 120
    assert bg_svc._con_toi_da(l, bg) == 120
    assert bg_svc._con_toi_da(None, bg) == 0, "thiếu lệnh → 0 (không đoán)"
    assert bg_svc._con_toi_da(Lsx(quy_cach_json={}), bg) == 0, "thiếu khổ thành phẩm → 0"


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
    lsx_b = next(l for l in created if l.id != lsx_a.id)
    _them_buoc_hao_sau_in(db, lsx_svc, lsx_svc.get(lsx_a.id), admin, so_to_bu_hao=0)
    # `_them_buoc_hao_sau_in` khai to→cái cho công đoạn IN DÙNG CHUNG của cả 2 lệnh, nhưng chỉ
    # lưu lại lsx_a — lsx_b vẫn giữ bản sao đơn vị cũ (rỗng) cho tới khi CHÍNH nó được ghi lại.
    # Gộp 2 bước in mà một bên còn bản sao cũ là chặn nhầm gộp thật — đồng bộ lsx_b trước.
    _resync_don_vi(lsx_svc, lsx_b.id, admin)
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


# --- §3 sổ nợ: hao khai tay · thứ tự bước chung · khoán lượt chung ------------
def _cd_can_mang_chung(db) -> CongDoan:
    """MỘT công đoạn cán màng dùng chung cho cả hai lệnh — cùng `cong_doan_id` mới gộp được.

    Khác `_them_buoc_hao_sau_in`: hàm kia đẻ mỗi lệnh một công đoạn riêng, hai bước đó không bao
    giờ gộp chung lượt được.
    """
    cd = CongDoan(
        ma="CD-CAN-CHUNG", ten="Cán màng", nhom="finishing",
        cong_thuc_gia="so_luong * don_gia", don_vi_vao="to", don_vi_ra="to",
        department_id=_to_san_xuat(db).id,
    )
    db.add(cd)
    db.flush()
    return cd


def _noi_buoc_cuoi(lsx_svc, lsx_id, admin, cd: CongDoan) -> None:
    """Nối `cd` vào CUỐI routing, KHÔNG khai `phu_thuoc_step_keys`.

    Cố ý để routing không có cạnh phụ thuộc nào — đó chính là ca đồ thị rời rạc, Kahn trả thứ tự
    tuỳ ý. Chuỗi thật của lệnh nằm ở `thu_tu`.
    """
    from app.schemas.lsx import LsxCongDoanIn

    cu = sorted(lsx_svc.get(lsx_id).cong_doans, key=lambda c: c.thu_tu)
    lsx_svc.replace_routing(lsx_id=lsx_id, actor=admin, rows_in=[
        *[LsxCongDoanIn(step_key=c.step_key, ten=c.ten, nhom=c.nhom,
                        cong_doan_id=c.cong_doan_id) for c in cu],
        LsxCongDoanIn(ten=cd.ten, nhom=cd.nhom, cong_doan_id=cd.id),
    ])


def _keys_cua_cong_doan(lsx_svc, created, cd_id: int) -> list[str]:
    return [
        next(c.step_key for c in lsx_svc.get(l.id).cong_doans if c.cong_doan_id == cd_id)
        for l in created
    ]


def test_khai_hao_0_thi_bai_khong_tu_thay_bang_de_xuat(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """"Chạy đúng số, không bù" là quyết định hợp lệ — máy không được đè lên nó.

    Hai cột hao từng `NOT NULL DEFAULT 0` nên "chưa ai khai" và "khai 0" là CÙNG một giá trị, mà
    engine đọc bằng `int(setup) + int(chay) or hao_de_xuat`: ai gõ 0 vẫn bị cộng hao máy, và
    không có đường nào khai không-bù-hao.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Công đoạn in của seed không khai quy tắc bù hao → đề xuất = 0, test sẽ rỗng nghĩa.
    cd_in = db.get(CongDoan, sorted(
        lsx_svc.get(created[0].id).cong_doans, key=lambda c: c.thu_tu)[0].cong_doan_id)
    cd_in.kieu_bu_hao, cd_in.so_to_bu_hao = "co_dinh", 250
    db.commit()

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    chua_khai = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]
    assert chua_khai["hao_de_xuat"] == 250, "fixture phải có hao đề xuất thì test mới có nghĩa"
    # CHƯA KHAI (NULL) → vẫn dùng số máy đề xuất, y như trước khi sửa.
    assert chua_khai["tong_to"] == chua_khai["so_to_tot"] + chua_khai["hao_de_xuat"]

    bg_svc.sua(bai_ghep_id=bg.id, patch={"hao_hut_setup": 0, "hao_hut_chay": 0}, actor=admin)
    khai_0 = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]
    assert khai_0["hao_de_xuat"] == chua_khai["hao_de_xuat"], "đề xuất vẫn hiện để còn đối chiếu"
    assert khai_0["tong_to"] == khai_0["so_to_tot"], "khai 0 mà vẫn cộng hao là đè lên ý người dùng"
    assert khai_0["to_nguyen_can"] == khai_0["so_to_tot"]

    # Xoá khai báo (None) → quay về đề xuất, không kẹt ở 0.
    bg_svc.sua(bai_ghep_id=bg.id, patch={"hao_hut_setup": None, "hao_hut_chay": None}, actor=admin)
    lai = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]
    assert lai["tong_to"] == lai["so_to_tot"] + lai["hao_de_xuat"]


def test_tong_to_va_to_nguyen_can_dung_chung_mot_co_so_hao(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Hai số cùng nghĩa "tờ phải cấp", chỉ khác đơn vị — không được lấy hai cơ sở hao khác nhau.

    `tong_to` từng chỉ cộng hao KHAI TAY còn `to_nguyen_can` cộng hao ÁP DỤNG (có fallback đề
    xuất). Bài chưa khai hao thì hai ô nằm cạnh nhau trên cùng header nói hai chuyện khác nhau.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    for patch in ({}, {"hao_hut_setup": 120, "hao_hut_chay": 30},
                  {"hao_hut_setup": 0, "hao_hut_chay": 0}):
        if patch:
            bg_svc.sua(bai_ghep_id=bg.id, patch=patch, actor=admin)
        so_to = bg_svc.detail_dict(bg_svc._get(bg.id))["so_to"]
        # Fixture không có bước xả (1 tờ nguyên = 1 tờ in) nên hai số phải TRÙNG khít.
        assert so_to["tong_to"] == so_to["to_nguyen_can"], (
            f"patch={patch}: to in {so_to['tong_to']} != to nguyen {so_to['to_nguyen_can']}"
        )


def test_thu_tu_buoc_chung_dung_chieu_du_routing_khong_co_canh(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Routing chưa nối dây → đồ thị RỜI RẠC, nhưng thứ tự bước chung vẫn phải đúng chiều.

    `lsx_cong_doan_phu_thuoc` chỉ lưu cạnh NGƯỜI nối tay; chuỗi trong một lệnh là ngầm theo
    `thu_tu`. Thiếu chuỗi ngầm thì Kahn trả thứ tự tuỳ ý, `_sap_lai_thu_tu` đánh số sai chiều,
    rồi `_node_chungs` chạy NGƯỢC theo đúng thứ tự sai đó để chia hao — sai lặng lẽ.

    Gộp CỐ Ý ngược chiều (cán trước, in sau) để thứ tự bấm khác thứ tự routing.
    """
    from app.models.lsx import LsxCongDoanPhuThuoc

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    cd_can = _cd_can_mang_chung(db)
    for l in created:
        _noi_buoc_cuoi(lsx_svc, l.id, admin, cd_can)

    ids = [c.id for l in created for c in lsx_svc.get(l.id).cong_doans]
    assert db.query(LsxCongDoanPhuThuoc).filter(
        LsxCongDoanPhuThuoc.buoc_sau_id.in_(ids)
    ).count() == 0, "test chỉ có nghĩa khi routing KHÔNG có cạnh phụ thuộc nào"

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    bg_svc.gop(bai_ghep_id=bg.id,
               step_keys=_keys_cua_cong_doan(lsx_svc, created, cd_can.id), actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    sd = bg_svc.so_do(bg_svc._get(bg.id))
    chung_in = next(g for g in sd["gop"] if g["nhom"] == "print")
    chung_can = next(g for g in sd["gop"] if g["cong_doan_id"] == cd_can.id)
    assert chung_in["thu_tu"] < chung_can["thu_tu"], (
        f"in phai dung truoc can: in={chung_in['thu_tu']} can={chung_can['thu_tu']}"
    )


def test_sua_routing_thi_thu_tu_buoc_chung_duoc_danh_lai(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """`_sap_lai_thu_tu` từng CHỈ chạy khi gộp/tách — sửa routing thì `thu_tu` bước chung thiu.

    `replace_routing` chặn XOÁ bước đang bị đè, nhưng vẫn cho đổi `thu_tu`. Đảo hai bước đã gộp
    mà bài không đánh lại thứ tự thì `_node_chungs` chia hao theo chuỗi đã cũ.
    """
    from app.schemas.lsx import LsxCongDoanIn

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    cd_can = _cd_can_mang_chung(db)
    for l in created:
        _noi_buoc_cuoi(lsx_svc, l.id, admin, cd_can)

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    bg_svc.gop(bai_ghep_id=bg.id,
               step_keys=_keys_cua_cong_doan(lsx_svc, created, cd_can.id), actor=admin)

    def _thu_tu(khoa) -> int:
        sd = bg_svc.so_do(bg_svc._get(bg.id))
        return next(g["thu_tu"] for g in sd["gop"]
                    if g["nhom"] == khoa or g["cong_doan_id"] == khoa)

    assert _thu_tu("print") < _thu_tu(cd_can.id)

    # ĐẢO routing của cả hai lệnh: cán chạy trước, in sau. Không xoá bước nào nên không bị chặn.
    for l in created:
        cu = sorted(lsx_svc.get(l.id).cong_doans, key=lambda c: c.thu_tu)
        lsx_svc.replace_routing(lsx_id=l.id, actor=admin, rows_in=[
            LsxCongDoanIn(step_key=c.step_key, ten=c.ten, nhom=c.nhom,
                          cong_doan_id=c.cong_doan_id)
            for c in reversed(cu)
        ])

    assert _thu_tu(cd_can.id) < _thu_tu("print"), (
        "dao routing xong ma thu tu buoc chung khong doi = `thu_tu` da thiu"
    )


def test_khoan_luot_chung_ghim_theo_id_va_chan_dau_viec_la(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Lượt chung chọn được đầu việc khoán — backend vẫn nhận nhưng form chưa có ô nhập.

    Ghim theo ID và SERVER chụp ảnh đơn giá: cho client gửi `khoan_json` thô là mở cửa cho đơn
    giá bịa chảy thẳng vào phiếu lương.
    """
    from app.models.cong_doan import CongDoanDauViec
    from app.models.piece_work import PieceRate

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Khai bảng khoán TRƯỚC khi đụng tới bài: `LsxService._piece_rates()` cache theo instance,
    # mà `BaiGhepService` dựng instance đó ở lần gọi engine đầu tiên.
    to = _to_san_xuat(db)
    cd_in_id = sorted(lsx_svc.get(created[0].id).cong_doans, key=lambda c: c.thu_tu)[0].cong_doan_id
    rate = PieceRate(group_name="to_in", ten="In tờ rời", unit="to", unit_price=35,
                     department_id=to.id, active=True)
    db.add(rate)
    db.flush()
    db.add(CongDoanDauViec(
        cong_doan_id=cd_in_id, piece_rate_id=rate.id,
        nang_suat_nguoi_gio=3000, so_nguoi_tieu_chuan=2, so_nguoi_toi_da=3,
    ))
    db.commit()

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    chung = bg_svc.so_do(bg_svc._get(bg.id))["gop"][0]
    assert chung["cong_doan_id"] == cd_in_id

    bg_svc.lap_ke_hoach_buoc_chung(
        bai_ghep_id=bg.id, gang_step_key=chung["step_key"],
        patch={"department_id": to.id, "piece_rate_id": rate.id}, actor=admin,
    )
    sau = bg_svc.so_do(bg_svc._get(bg.id))["gop"][0]
    assert sau["khoan_rate_id"] == rate.id
    assert sau["khoan_ten"] == "In tờ rời" and sau["khoan_don_gia"] == 35
    assert rate.id in {k["id"] for k in sau["khoan_chon_duoc"]}
    # Định mức đi kèm: chọn xong mà năng suất vẫn trống thì thẻ vẫn kêu "Chưa có năng suất".
    assert sau["nang_suat"] == 3000 and sau["so_nhan_cong"] == 2
    assert "Chưa có năng suất" not in sau["thieu"]

    # Đầu việc không thuộc tổ / công đoạn → CHẶN, không âm thầm ghim.
    la = PieceRate(group_name="to_khac", ten="Việc tổ khác", unit="to", unit_price=99,
                   department_id=None, active=True)
    db.add(la)
    db.commit()
    with pytest.raises(BaiGhepValidationError):
        bg_svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bg.id, gang_step_key=chung["step_key"],
            patch={"piece_rate_id": la.id}, actor=admin,
        )


def test_dau_viec_khoan_luot_chung_mang_san_vat_tu_de_drawer_bung(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Bước chung: chọn đầu việc khoán phải BUNG sẵn vật tư đã tính số, đúng như đường lệnh.

    Bug 20/08 (drawer bước chung hiện "0 vật tư"): `_khoan_chung_dict` gọi `_dau_viec_option_dicts`
    THIẾU `buoc`+`quy_cach`, nên `_vat_tu_bung` trả rỗng — trong khi đường lệnh (`lsx_service`) luôn
    kèm hai thứ đó. Lỗi chép lệch giữa hai chỗ cùng một việc; test này đỏ nếu ai gỡ `buoc`/`quy_cach`.
    """
    from app.models.cong_doan import CongDoanDauViec, CongDoanDauViecVatTu
    from app.models.piece_work import PieceRate
    from app.models.vat_lieu_kho import VatTuInAn

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Khai bảng khoán + vật tư TRƯỚC khi đụng tới bài (cache `_piece_rates()` theo instance).
    to = _to_san_xuat(db)
    cd_in_id = sorted(lsx_svc.get(created[0].id).cong_doans, key=lambda c: c.thu_tu)[0].cong_doan_id
    rate = PieceRate(group_name="to_in", ten="In tờ rời", unit="to", unit_price=35,
                     department_id=to.id, active=True)
    db.add(rate)
    db.flush()
    link = CongDoanDauViec(
        cong_doan_id=cd_in_id, piece_rate_id=rate.id,
        nang_suat_nguoi_gio=3000, so_nguoi_tieu_chuan=2, so_nguoi_toi_da=3,
    )
    db.add(link)
    db.flush()
    keo = VatTuInAn(ma="KEO-CH", ten="Keo bước chung", don_vi_gia="kg", don_gia=45_000,
                    cong_thuc_luong="sl_vao * 0.001", active=True)
    db.add(keo)
    db.flush()
    link.vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0))
    db.commit()

    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    chung = bg_svc.so_do(bg_svc._get(bg.id))["gop"][0]
    assert chung["cong_doan_id"] == cd_in_id
    assert chung["so_luong_vao"] > 0, "bước chung in phải có số tờ vào để công thức lượng chạy"

    chon = next(k for k in chung["khoan_chon_duoc"] if k["id"] == rate.id)
    assert [v["ma"] for v in chon["vat_tus"]] == ["KEO-CH"], (
        "chọn đầu việc khoán ở bước chung phải bung sẵn vật tư như đường lệnh, không để 0 vật tư"
    )
    assert chon["vat_tus"][0]["so_luong"] == pytest.approx(
        round(chung["so_luong_vao"] * 0.001, 3))
    assert chon["vat_tus"][0]["don_vi"] == "kg"


# --- §4 sổ nợ: khoá TẦNG SERVICE của đồ thị (9 test cũ đều thuần Python) -----
def _step_key(lsx_svc, lsx_id: int, *, nhom: str | None = None, cd_id: int | None = None) -> str:
    cds = sorted(lsx_svc.get(lsx_id).cong_doans, key=lambda c: c.thu_tu)
    return next(c.step_key for c in cds
                if (nhom is None or c.nhom == nhom) and (cd_id is None or c.cong_doan_id == cd_id))


def _cho_buoc_cua(lsx_svc, lsx_id: int, admin, *, step_key: str, cho_key: str | None) -> None:
    """Khai `step_key` PHỤ THUỘC `cho_key` — cạnh CHÉO LỆNH, qua đúng API thật. `None` = gỡ cạnh.

    `replace_routing` chỉ cho phụ thuộc công đoạn CÙNG ĐƠN HÀNG, nên mọi cạnh chéo ở đây đều là
    cạnh hợp lệ theo luật hiện hành, không phải cạnh nhét tay vào DB.
    """
    from app.schemas.lsx import LsxCongDoanIn

    cu = sorted(lsx_svc.get(lsx_id).cong_doans, key=lambda c: c.thu_tu)
    lsx_svc.replace_routing(lsx_id=lsx_id, actor=admin, rows_in=[
        LsxCongDoanIn(
            step_key=c.step_key, ten=c.ten, nhom=c.nhom, cong_doan_id=c.cong_doan_id,
            phu_thuoc_step_keys=([cho_key] if (cho_key and c.step_key == step_key) else []),
        )
        for c in cu
    ])


def test_do_thi_cua_lan_theo_canh_qua_NHIEU_bac_khong_dung_o_mot_hop(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Tầm ngắm kiểm vòng phải ĐÓNG BAO THEO CẠNH, lặp tới khi không kéo thêm được ai.

    `_do_thi_cua` là phần CHẠM DB của đồ thị — 9 test `bai_ghep_graph` đều thuần Python nên
    khoá được thuật toán mà không khoá được việc service nạp đúng tập node/cạnh. Cắt tầm ngắm
    ở một bậc thì kiểm vòng báo "gộp được" rồi xưởng mới phát hiện kẹt.

    Dây chuyền: A (trong bài) chờ C, C chờ D. Cả C lẫn D đều NGOÀI bài — D cách bài hai bậc.
    """
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer, sl_them=(5_000, 4_000))
    assert len(created) == 4, "cần 2 lệnh ngoài bài để có bậc thứ hai mà lan tới"
    a, b, c, d = created
    cd_can = _cd_can_mang_chung(db)
    for l in created:
        _noi_buoc_cuoi(lsx_svc, l.id, admin, cd_can)

    _cho_buoc_cua(lsx_svc, a.id, admin,
                  step_key=_step_key(lsx_svc, a.id, nhom="print"),
                  cho_key=_step_key(lsx_svc, c.id, cd_id=cd_can.id))
    _cho_buoc_cua(lsx_svc, c.id, admin,
                  step_key=_step_key(lsx_svc, c.id, nhom="print"),
                  cho_key=_step_key(lsx_svc, d.id, cd_id=cd_can.id))

    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    buocs, canhs = bg_svc._do_thi_cua(bg_svc._get(bg.id))

    trong_tam = {x.lsx_id for x in buocs}
    assert {a.id, b.id, c.id} <= trong_tam, "chưa kéo nổi lệnh kề bài — cắt ngay bậc một"
    assert d.id in trong_tam, "dừng ở một bậc: lệnh cách bài hai bậc bị bỏ ngoài tầm ngắm"
    assert {x.trong_bai for x in buocs if x.lsx_id == a.id} == {True}
    assert {x.trong_bai for x in buocs if x.lsx_id == d.id} == {False}

    # Và CẠNH chéo lệnh phải theo về, không chỉ mỗi node.
    keys = {x.key for x in buocs}
    cap = {(e.truoc, e.sau) for e in canhs}
    assert all(e.truoc in keys and e.sau in keys for e in canhs)
    assert (_step_key(lsx_svc, c.id, cd_id=cd_can.id),
            _step_key(lsx_svc, a.id, nhom="print")) in cap


def test_canh_cheo_lenh_lam_vo_phep_gop_o_TANG_SERVICE(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Cạnh chéo lệnh phải chặn được phép gộp khi đi qua service thật, không chỉ ở tầng thuần.

    A.In chờ B.Cán, mà B.Cán lại chờ B.In. Gộp A.In với B.In là bắt một lượt máy vừa phải chạy
    trước vừa phải chạy sau chính nó — vòng thật, không phải bắt lỗi hình thức.

    Test này ĐỎ ngay nếu `_do_thi_cua` quên nạp cạnh chéo: bỏ cạnh đó đi thì đồ thị sạch bong.
    """
    from app.services.bai_ghep_service import BaiGhepVongPhuThuoc

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    a, b = created
    cd_can = _cd_can_mang_chung(db)
    for l in created:
        _noi_buoc_cuoi(lsx_svc, l.id, admin, cd_can)

    _cho_buoc_cua(lsx_svc, a.id, admin,
                  step_key=_step_key(lsx_svc, a.id, nhom="print"),
                  cho_key=_step_key(lsx_svc, b.id, cd_id=cd_can.id))

    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    keys_in = [_step_key(lsx_svc, l.id, nhom="print") for l in created]

    # Canvas hỏi TRƯỚC: bước in của B phải hiện MỜ kèm lý do, không để bấm rồi mới 409.
    uv = bg_svc.ung_vien_gop(bg_svc._get(bg.id), [keys_in[0]])
    assert uv[keys_in[1]]["gop_duoc"] is False
    assert uv[keys_in[1]]["ly_do"]

    with pytest.raises(BaiGhepVongPhuThuoc) as e:
        bg_svc.gop(bai_ghep_id=bg.id, step_keys=keys_in, actor=admin)
    assert e.value.nut, "409 phải mang chu trình để người dùng biết gỡ ở đâu"
    assert e.value.nhan_chung, "và mang nhân chứng để canvas tô đúng cặp bước chọi nhau"

    # Không có cạnh chéo thì chính phép gộp ấy chạy ngon — chứng minh đỏ là DO cạnh, không do
    # test dựng sai.
    _cho_buoc_cua(lsx_svc, a.id, admin,
                  step_key=_step_key(lsx_svc, a.id, nhom="print"), cho_key=None)
    bg_svc.gop(bai_ghep_id=bg.id, step_keys=keys_in, actor=admin)
    assert len(bg_svc.so_do(bg_svc._get(bg.id))["gop"]) == 1


def test_khai_vat_tu_cho_luot_chung_va_snapshot_dung_don_vi(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Khai vật tư cho lượt chung — nhánh này CHƯA có test nào chạy qua, và nó đang gãy thật.

    `_thay_vat_tu_chung` đọc `mat.don_vi`, mà `VatTuInAn` chỉ có `don_vi_gia`: bấm Lưu ở drawer
    bước chung với một dòng vật tư là AttributeError → 500. Bước lệnh bên `lsx_service` vẫn luôn
    dùng đúng `don_vi_gia`, nên đây là lỗi chép lệch giữa hai chỗ làm cùng một việc.

    Snapshot mã/tên/đơn vị là CÓ Ý: đổi danh mục về sau không được làm xê dịch kế hoạch đã chốt.
    """
    from app.models.vat_lieu_kho import VatTuInAn

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)
    chung = bg_svc.so_do(bg_svc._get(bg.id))["gop"][0]

    muc = VatTuInAn(ma="VT-MUC-01", ten="Mực đen", don_vi_gia="kg", don_gia=180_000, active=True)
    db.add(muc)
    db.commit()

    bg_svc.lap_ke_hoach_buoc_chung(
        bai_ghep_id=bg.id, gang_step_key=chung["step_key"],
        patch={"vat_tus": [{"vat_tu_id": muc.id, "so_luong": 2.5}]}, actor=admin,
    )
    sau = bg_svc.so_do(bg_svc._get(bg.id))["gop"][0]
    assert len(sau["vat_tus"]) == 1
    v = sau["vat_tus"][0]
    assert (v["ma"], v["ten"], v["don_vi"]) == ("VT-MUC-01", "Mực đen", "kg")
    assert v["so_luong"] == pytest.approx(2.5)

    # Đổi danh mục KHÔNG được kéo theo kế hoạch đã chốt.
    muc.ten, muc.don_vi_gia = "Mực đen (đổi tên)", "lit"
    db.commit()
    lai = bg_svc.so_do(bg_svc._get(bg.id))["gop"][0]["vat_tus"][0]
    assert (lai["ten"], lai["don_vi"]) == ("Mực đen", "kg")

    # Cùng một vật tư hai dòng trong một bước → chặn.
    with pytest.raises(BaiGhepValidationError):
        bg_svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bg.id, gang_step_key=chung["step_key"],
            patch={"vat_tus": [{"vat_tu_id": muc.id, "so_luong": 1},
                               {"vat_tu_id": muc.id, "so_luong": 2}]}, actor=admin,
        )


def test_so_do_chung_mang_bang_boc_tach_gio_va_goi_y_vat_tu(
    db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Drawer bước chung dựng bảng bóc tách giờ + nút "Dùng số này" từ ĐÚNG hai khoá này.

    Đi qua `SoDoOut.model_validate` chứ không đọc thẳng dict của service: bẫy "Pydantic nuốt
    field im lặng" nằm ở chỗ khoá nào service trả mà schema không khai thì rơi mất KHÔNG lỗi,
    frontend nhận `undefined` và bảng bóc tách hiện rỗng.
    """
    from app.models.vat_lieu_kho import VatTuInAn
    from app.schemas.bai_ghep import SoDoOut

    db.add(VatTuInAn(ma="VT-MUC-GY", ten="Mực đen", don_vi_gia="kg", don_gia=180_000,
                     cong_thuc_luong="sl_vao / 1000", active=True))
    db.commit()

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    _gop_buoc_in(bg_svc, lsx_svc, bg, created, admin)

    chung = SoDoOut.model_validate(bg_svc.so_do(bg_svc._get(bg.id))).model_dump()["gop"][0]

    dg = chung["thoi_luong_dien_giai"]
    assert dg, "rỗng ⇒ drawer chỉ còn một con số tổng, người xem không kiểm được vì sao ra nó"
    # Bộ khoá drawer đọc thẳng — thiếu khoá nào là mất đúng một dòng trong bảng bóc tách.
    assert {"phuong_phap", "so_luong_vao", "don_vi_vao", "chuan_bi_khoan", "setup_phut",
            "phat_sinh_phut", "chay_phut", "tong_phut", "canh_bao"} <= set(dg)
    assert dg["tong_phut"] == pytest.approx(chung["tong_phut"])

    goi_y = {g["vat_tu_id"]: g for g in chung["vat_tu_goi_y"]}
    muc = db.query(VatTuInAn).filter(VatTuInAn.ma == "VT-MUC-GY").one()
    assert muc.id in goi_y, "vật tư đang dùng phải có mặt thì drawer mới bày được nút Dùng số này"
    # Số của LƯỢT CHUNG (tờ ghép), không phải số của một lệnh thành viên nào.
    assert goi_y[muc.id]["so_luong"] == pytest.approx(chung["so_luong_vao"] / 1000, rel=1e-6)
    assert goi_y[muc.id]["dien_giai"], "phải kèm câu công thức = thay số = kết quả"
