"""Xếp lịch công đoạn — service-level tests.

Tái dùng luồng thật (đơn → chuyển SX → tạo lệnh → sẵn sàng) như test bài ghép. Kiểm:
- Đưa lệnh vào kế hoạch → sinh dòng + trạng thái `da_lap_ke_hoach` + KHÓA routing.
- Gán máy + giờ → tính giờ kết thúc theo GIỜ LÀM VIỆC + `da_xep`.
- Xung đột máy (2 dòng cùng máy chồng giờ).
- Gỡ kế hoạch → xóa dòng, mở lại routing.
- Bài ghép: dòng in chung xuất hiện MỘT lần, công đoạn in của thành viên bị loại (chạy chung).
- Unit: cộng giờ làm việc tràn sang ngày kế.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan
from app.models.customer import Customer
from app.models.department import Department
from app.models.lsx import LB_MAY, LB_XA_TO, TT_DA_LAP_KE_HOACH, TT_SAN_SANG, LsxCongDoan
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
from app.repositories.xep_lich_repo import XepLichRepository
from app.schemas.order import OrderCreate, OrderDepositReceiptIn, OrderUpdate
from app.seed import seed_all
from app.services.accounting_service import AccountingService
from app.services.bai_ghep_service import BaiGhepService
from app.services.lsx_service import LsxConflict, LsxService
from app.services.order_service import OrderService
from app.services.sequence_service import SequenceService
from app.services.xep_lich_service import XepLichConflict, XepLichService, _cong_gio_lam


# --- helper dựng nguồn (copy để test tự-chứa) --------------------------------
def _to_san_xuat(db) -> Department:
    to = db.query(Department).filter(Department.la_san_xuat.is_(True)).first()
    if to is None:
        to = Department(name="Tổ In XL", code="TO-IN-XL", la_san_xuat=True)
        db.add(to)
        db.flush()
    return to


def _may_in(db) -> MayThietBi:
    may = MayThietBi(
        ma="MAY-IN-XL", ten="Máy in 4 màu", loai_may="press_offset_sheet",
        toc_do=5_000, don_vi_toc_do="to_gio", thoi_gian_rua_muc=15, makeready_time_default=30,
        kho_max_dai=1020, kho_max_rong=720,
    )
    db.add(may)
    db.flush()
    return may


def _quote_from_ptg(db, customer, ptg: PhieuTinhGia) -> Quote:
    q = Quote(quote_number="XL-QUOTE", customer_id=customer.id, status=STATUS_ACCEPTED,
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


def _don_da_chuyen_sx(db, orders, admin, customer, ptg):
    q = _quote_from_ptg(db, customer, ptg)
    d = orders.create(actor=admin, scope="all",
                      payload=OrderCreate(source_type="bao_gia", quotation_id=q.id, deposit_pct=50))
    orders.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                               payload=OrderDepositReceiptIn(receipt_method="cash",
                                                             amount=d.deposit_required))
    orders.update(order_id=d.id, actor=admin, scope="all", payload=OrderUpdate(
        customer_po_no="PO-XL", delivery_committed_date=date.today() + timedelta(days=10),
    ))
    d = orders.confirm(order_id=d.id, actor=admin, scope="all")
    return orders.release_production(order_id=d.id, actor=admin, scope="all")


def _ptg_2_in(db, *, sl_a=20_000, sl_b=8_000) -> PhieuTinhGia:
    giay = GiayNguyen(
        ma="G-IV350X", ten="Ivory 350", gsm=350, don_gia=25_000, don_vi_gia="tan",
        cong_thuc_gia="to_nguyen * dai_nguyen * rong_nguyen * dinh_luong * don_gia / 1000",
    )
    db.add(giay)
    to_id = _to_san_xuat(db).id
    may = _may_in(db)
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()
    if cd_in is None:
        cd_in = CongDoan(ma="CD-IN-X", ten="In offset", nhom="print",
                         cong_thuc_gia="so_luong * don_gia")
        db.add(cd_in)
    cd_in.department_id = cd_in.department_id or to_id
    cd_in.may_id = cd_in.may_id or may.id
    cd_in.setup_time = 45
    db.flush()

    def _sp(thu_tu, ten, sl, dai, rong):
        sp = PhieuThanhPhan(
            thu_tu=thu_tu, ten=ten, so_luong=sl, don_vi_tinh="cái",
            dai_thanh_pham=dai, rong_thanh_pham=rong, giay_id=giay.id,
            kho_nguyen_dai=790, kho_nguyen_rong=1090, kho_in_dai=650, kho_in_rong=900,
            so_mau_a=4, so_mau_b=0, quy_cach_in="mot_mat",
        )
        sp.thanh_phams.append(
            PhieuThanhPham(thu_tu=0, cong_doan_id=cd_in.id, ten="In offset", don_gia=200)
        )
        return sp

    p = PhieuTinhGia(ma="PTG-XL-0001", ten_san_pham="2 hộp ghép", so_luong=sl_a)
    p.thanh_phans.extend([_sp(0, "Hộp A", sl_a, 200, 150), _sp(1, "Hộp B", sl_b, 180, 120)])
    db.add(p)
    db.commit()
    return p


def _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_in(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    created = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    for l in created:
        lsx_svc.set_trang_thai(lsx_id=l.id, trang_thai=TT_SAN_SANG, actor=admin)
    return created


def _in_step(db, lsx_id: int) -> LsxCongDoan:
    return db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == lsx_id, LsxCongDoan.nhom == "print"
    ).first()


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
    c = Customer(code="KH-XL", name="KH Xếp lịch")
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


@pytest.fixture
def xl_svc(db):
    return XepLichService(db, XepLichRepository(db), AuditLogRepository(db))


# --- tests -------------------------------------------------------------------
def test_dua_vao_lsx_sinh_dong_va_khoa_routing(db, orders, lsx_svc, xl_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)

    assert lsx.trang_thai == TT_DA_LAP_KE_HOACH
    rows = XepLichRepository(db).by_lsx(lsx.id)
    assert len(rows) >= 1 and all(r.trang_thai == "cho_xep" for r in rows)
    # Đã lập kế hoạch → routing bị khóa.
    with pytest.raises(LsxConflict):
        lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=[], actor=admin)


def test_gan_tinh_gio_ket_thuc_va_da_xep(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)  # loại nhiễu nghỉ lễ
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao = 45, 5000, 5000  # 45 + 5000/5000*60 = 105 phút
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1
    db.commit()

    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    res = xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": bat_dau}, actor=admin)

    assert res.trang_thai == "da_xep"
    # SQLite (dev) đọc DateTime trả naive; giá trị đúng 09:45 (= 08:00 + 105 phút trong ngày).
    assert res.finish_at.replace(tzinfo=None) == datetime(2026, 7, 27, 9, 45)


def test_xung_dot_may_khi_chong_gio(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for lsx in (a, b):
        s = _in_step(db, lsx.id)
        s.setup_phut, s.nang_suat, s.so_luong_vao, s.chay_phut = 0, 5000, 5000, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    xl_svc.dua_vao_lsx(lsx_id=b.id, actor=admin)

    repo = XepLichRepository(db)
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    may_id = _in_step(db, a.id).may_id  # 2 LSX cùng công đoạn in → cùng máy
    xl_svc.gan(dong_id=repo.by_lsx(a.id)[0].id, patch={"may_id": may_id, "start_at": bat_dau}, actor=admin)
    xl_svc.gan(dong_id=repo.by_lsx(b.id)[0].id, patch={"may_id": may_id, "start_at": bat_dau}, actor=admin)

    items = {it["id"]: it for it in xl_svc.danh_sach()["items"]}
    assert all(it["co_xung_dot"] for it in items.values() if it["may_id"] == may_id)


def test_go_ke_hoach_xoa_dong_va_mo_routing(db, orders, lsx_svc, xl_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    xl_svc.go_lsx(lsx_id=lsx.id, actor=admin)

    assert lsx.trang_thai == TT_SAN_SANG
    assert XepLichRepository(db).by_lsx(lsx.id) == []


def test_bai_ghep_in_chung_mot_dong_loai_tru_in(db, orders, lsx_svc, bg_svc, xl_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Mỗi LSX thêm bước xả tờ (sau in) để thành viên còn công đoạn xếp riêng sau khi in chung.
    for lsx in created:
        db.add(LsxCongDoan(
            lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_XA_TO,
            may_id=_in_step(db, lsx.id).may_id, so_luong_vao=5000, nang_suat=3000,
            don_vi_nang_suat="to_gio",
        ))
    db.commit()
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    bg = bg_svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai=TT_SAN_SANG, actor=admin)

    xl_svc.dua_vao_bai_ghep(bai_ghep_id=bg.id, actor=admin)
    repo = XepLichRepository(db)

    gang = repo.by_bai_ghep(bg.id)
    assert len(gang) == 1 and gang[0].nguon == "in_ghep"        # in chung xuất hiện MỘT lần
    member = repo.by_lsx(created[0].id)
    assert len(member) == 1 and member[0].loai_buoc == LB_XA_TO  # in bị loại, còn xả tờ
    assert all(l.trang_thai == TT_DA_LAP_KE_HOACH for l in created)
    # Thành viên bài ghép KHÔNG gỡ kế hoạch trực tiếp (phải gỡ qua bài ghép) — tránh mồ côi dòng in chung.
    with pytest.raises(XepLichConflict):
        xl_svc.go_lsx(lsx_id=created[0].id, actor=admin)


def test_som_nhat_theo_gio_thuc_cua_buoc_truoc(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Gán In MUỘN → 'sớm nhất' của Xả tờ phải chạy theo giờ KẾT THÚC thực của In (không phải mốc lý
    thuyết) — nhờ đó cột Sớm nhất tự cảnh báo khi ai xếp bước sau chạy trước bước trước."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None  # In = 60 phút
    db.add(LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_XA_TO,
                       may_id=step.may_id, so_luong_vao=5000, nang_suat=6000, don_vi_nang_suat="to_gio"))
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dongs = XepLichRepository(db).by_lsx(lsx.id)
    in_dong = next(d for d in dongs if d.source_thu_tu == 0)
    xa_dong = next(d for d in dongs if d.loai_buoc == LB_XA_TO)
    # Gán In bắt đầu 28/7 08:00 → kết thúc 09:00.
    xl_svc.gan(dong_id=in_dong.id,
               patch={"may_id": step.may_id, "start_at": datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)},
               actor=admin)
    items = {it["id"]: it for it in xl_svc.danh_sach()["items"]}
    # Sớm nhất của Xả tờ KHÔNG được sớm hơn khi In kết thúc thật (09:00).
    assert items[xa_dong.id]["som_nhat"].replace(tzinfo=None) >= datetime(2026, 7, 28, 9, 0)


def test_cong_gio_lam_tran_sang_ngay_ke(db, xl_svc, monkeypatch):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    # 600 phút = 8h ngày đầu (đến 16:00) + 120 phút ngày kế (08:00 → 10:00).
    assert _cong_gio_lam(bat_dau, 600, xl_svc.cal) == datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


def test_gan_lai_mot_phan_tren_dong_da_co_gio(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Regression: patch MỘT PHẦN (chỉ đổi máy, KHÔNG kèm start_at) trên dòng ĐÃ có giờ.

    Sau `commit()` SQLAlchemy expire object → lần gán sau đọc lại `start_at` từ SQLite là
    NAIVE. Trước fix, giá trị naive rơi vào `_cong_gio_lam` → so naive vs aware → TypeError
    (500 + mất header CORS → trình duyệt báo ERR_FAILED). Inline sửa máy/tổ/NCC đều gửi patch
    một phần nên dính. Fix: chuẩn hóa `start_at` qua `_aware()` trước khi tính giờ.
    """
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao = 0, 5000, 5000
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1  # chiếm máy = 5000/5000*60 = 60 phút
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": bat_dau}, actor=admin)

    # Gán LẠI, chỉ đổi máy — KHÔNG kèm start_at (giống inline popover). Không được lỗi.
    res = xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id}, actor=admin)
    assert res.trang_thai == "da_xep"
    assert res.start_at.replace(tzinfo=None) == datetime(2026, 7, 27, 8, 0)   # giờ giữ nguyên
    assert res.finish_at.replace(tzinfo=None) == datetime(2026, 7, 27, 9, 0)  # 08:00 + 60 phút
