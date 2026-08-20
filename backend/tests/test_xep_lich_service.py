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
from types import SimpleNamespace

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan
from app.models.customer import Customer
from app.models.department import Department
from app.models.lsx import LB_MAY, TT_DA_LAP_KE_HOACH, TT_SAN_SANG, LsxCongDoan, LsxCongDoanPhuThuoc
from app.models.machine_unavailable import KIEU_CHAN, LY_DO_BAO_TRI, MachineUnavailablePeriod
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
from app.services.xep_lich_service import (
    LichXuong, XepLichConflict, XepLichService, XepLichValidationError, _cong_gio_lam, _dau_ca,
)


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
        toc_do=5_000, don_vi_toc_do="to_gio", makeready_time_default=30,
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
        # CÔNG THỨC LƯỢNG — mọi giấy thật đều có (mg `0197` điền cho dòng cũ, seed điền cho dòng
        # mới). Test dựng bằng `create_all` nên migration không chạy ⇒ phải khai tay, không thì
        # bảng cân đối không quy được tờ → tấn và detector "thiếu vật tư" im.
        # `/ 1000` vì giấy này bán theo TẤN: kết quả công thức đọc theo đúng `don_vi_gia`.
        cong_thuc_luong="dinh_luong * dai_nguyen * rong_nguyen * to_nguyen / 1000",
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
    cd_in.setup_time = 45
    # Đơn vị KHAI ở danh mục (bước in chạy TỜ IN) — thiếu thì bước rơi khỏi dòng giấy và xếp lịch
    # mất luôn đường tính thời lượng theo máy (`to_gio`).
    cd_in.don_vi_vao = cd_in.don_vi_ra = "to"
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

    p = PhieuTinhGia(ma="PTG-XL-0001", ten_san_pham="2 hộp ghép", so_luong=sl_a)
    p.thanh_phans.extend([_sp(0, "Hộp A", sl_a, 200, 150), _sp(1, "Hộp B", sl_b, 180, 120)])
    db.add(p)
    db.commit()
    return p


def _giu_cho_du(db, *, lsx_ids=(), bai_ghep_ids=()):
    """Dựng ĐỦ VẬT TƯ + bật giữ chỗ — tiền đề MỚI của việc vào kế hoạch (17/08/2026).

    Từ Đợt 2, `dua_vao_lsx` / `dua_vao_bai_ghep` chặn khi chưa giữ đủ vật tư: *đã xếp lịch nghĩa là
    vật tư đã có chủ*. Mọi test ở file này soi CƠ CHẾ XẾP LỊCH (gán máy, vùng khoá, tiền nhiệm, xem
    trước), không soi vật tư — nên dựng sẵn kho đầy ở đây, một chỗ, thay vì rắc `bat()` vào 31 chỗ
    gọi và làm loãng thứ mỗi test thật sự kiểm.

    Kho đầy = một lô rất lớn cho MỌI mặt hàng trong danh mục. Thô nhưng đúng ý: fixture này nói
    "vật tư không phải là biến của bài toán đang kiểm".
    """
    from app.models.kho_hang import KhoHang
    from app.models.stock_lot import LOT_AVAILABLE, StockLot
    from app.models.vat_lieu_kho import GiayNguyen, VatTuInAn
    from app.repositories.bai_ghep_repo import BaiGhepRepository
    from app.repositories.don_vi_do_repo import DonViDoRepository
    from app.repositories.lsx_repo import LsxRepository
    from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
    from app.repositories.stock_lot_repo import StockLotRepository
    from app.repositories.stock_request_repo import StockRequestRepository
    from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from app.services.giu_cho_service import GiuChoService
    from app.services.ke_hoach_vat_tu_service import KeHoachVatTuService
    from app.services.vat_lieu_kho_service import VatLieuKhoService

    kho = db.query(KhoHang).first()
    if kho is None:
        kho = KhoHang(ma="K-XL", ten="Kho test xếp lịch")
        db.add(kho)
        db.flush()
    for loai, model in (("giay", GiayNguyen), ("vat_tu", VatTuInAn)):
        for mh in db.query(model).all():
            ma_lo = f"LOT-XL-{loai}-{mh.id}"
            if db.query(StockLot).filter(StockLot.ma_lo == ma_lo).first():
                continue
            db.add(StockLot(hang_loai=loai, hang_id=mh.id, kho_id=kho.id, ma_lo=ma_lo,
                            sl_ban_dau=1_000_000, sl_con_lai=1_000_000,
                            ngay_nhap=date.today(), trang_thai=LOT_AVAILABLE))
    db.commit()

    kh = KeHoachVatTuService(
        db, lsx_repo=LsxRepository(db), bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db), requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db), suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )
    gc = GiuChoService(db, kh)
    for i in lsx_ids:
        gc.bat(lsx_id=i)
    for i in bai_ghep_ids:
        gc.bat(bai_ghep_id=i)


def _nha_cho(db, lsx_ids):
    """Nhả chỗ của các lệnh trước khi GHÉP BÀI.

    Từ Đợt 2, lệnh đang giữ chỗ không ghép bài được — vì ghép làm ĐỔI số giấy cần (và đổi xuống).
    `_hai_lsx_san_sang` bật sẵn giữ chỗ cho mọi lệnh, nên test nào đi đường bài ghép phải nhả trước.
    Đúng thao tác người dùng thật: Nhả chỗ → ghép → giữ lại ở bài.
    """
    from app.models.lsx import Lsx

    for i in lsx_ids:
        l = db.get(Lsx, i)
        if l is not None:
            l.giu_cho_bat = False
    from app.models.vat_tu_giu_cho import VatTuGiuCho

    db.query(VatTuGiuCho).filter(VatTuGiuCho.lsx_id.in_(list(lsx_ids))).delete(
        synchronize_session=False)
    db.commit()


def _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_in(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    created = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    for l in created:
        lsx_svc.set_trang_thai(lsx_id=l.id, trang_thai=TT_SAN_SANG, actor=admin)
    _giu_cho_du(db, lsx_ids=[l.id for l in created])
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
    step.setup_phut, step.nang_suat, step.so_luong_vao = 45, 5000, 5000
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1
    db.commit()

    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    res = xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": bat_dau}, actor=admin)

    assert res.trang_thai == "da_xep"
    # Bước In gán vào máy `_may_in` (to_gio) → THEO MÁY (HM3): makeready 30 + chạy 5000/5000*60=60 +
    # = 90 phút (setup của máy THẮNG snapshot bước). SQLite trả naive → 09:30.
    assert res.finish_at.replace(tzinfo=None) == datetime(2026, 7, 27, 9, 30)


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


def _gop_in_va_san_sang(db, bg_svc, bg, admin, keys=None):
    """Gộp bước in của các thành viên + lập kế hoạch cho lượt chung → bài đủ điều kiện sẵn sàng.

    Bài ghép KHÔNG tự gộp bước nào: chưa gộp thì đó là N lệnh rời, gate `san_sang` chặn.
    """
    from app.models.department import Department

    tvs = bg_svc._get(bg.id).thanh_viens
    bg_svc.gop(
        bai_ghep_id=bg.id, actor=admin,
        step_keys=keys or [_in_step(db, tv.lsx_id).step_key for tv in tvs],
    )
    mau = _in_step(db, tvs[0].lsx_id)
    to_id = mau.department_id or db.query(Department.id).scalar()
    for c in bg_svc._buoc_chungs(bg_svc._get(bg.id)):
        bg_svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bg.id, gang_step_key=c.step_key, actor=admin,
            patch={"department_id": to_id, "may_id": mau.may_id},
        )
    ra = bg_svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai=TT_SAN_SANG, actor=admin)
    # Bài ghép là CHỦ THỂ giữ chỗ của các lệnh thành viên — bật ở đây, sau khi gộp xong, vì gộp làm
    # đổi số giấy cần (đó chính là lý do bài đang giữ chỗ thì không cho thêm/rút thành viên).
    _giu_cho_du(db, bai_ghep_ids=[bg.id])
    return ra


def test_moi_buoc_chung_mot_dong_lich_khong_bi_boc_hoi(
    db, orders, lsx_svc, bg_svc, xl_svc, admin, customer
):
    """Gộp NHIỀU công đoạn → mỗi bước chung một dòng lịch, dùng máy của chính bước đó.

    `_sinh_dong` loại MỌI bước bị đè khỏi routing lệnh. Nếu bài chỉ đẻ đúng một dòng "in ghép" thì
    gộp thêm một công đoạn nữa là bước đó **bốc hơi khỏi board**: không đặt chỗ máy, không tính
    thời lượng, không ai báo.
    """
    from app.models.department import Department

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Mỗi lệnh thêm bước "Xả tờ" để có công đoạn thứ hai gộp được.
    for lsx in created:
        db.add(LsxCongDoan(
            lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
            cong_doan_id=_in_step(db, lsx.id).cong_doan_id,
            may_id=_in_step(db, lsx.id).may_id, so_luong_vao=5000, nang_suat=3000,
            don_vi_nang_suat="to_gio", don_vi_vao="to", don_vi_ra="to",
        ))
    db.commit()
    _nha_cho(db, [l.id for l in created])
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)

    tvs = bg_svc._get(bg.id).thanh_viens
    bg_svc.gop(bai_ghep_id=bg.id, actor=admin,
               step_keys=[_in_step(db, tv.lsx_id).step_key for tv in tvs])
    bg_svc.gop(bai_ghep_id=bg.id, actor=admin, step_keys=[
        next(c.step_key for c in lsx_svc.get(tv.lsx_id).cong_doans if c.ten == "Xả tờ")
        for tv in tvs
    ])
    mau = _in_step(db, tvs[0].lsx_id)
    to_id = mau.department_id or db.query(Department.id).scalar()
    for c in bg_svc._buoc_chungs(bg_svc._get(bg.id)):
        bg_svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bg.id, gang_step_key=c.step_key, actor=admin,
            patch={"department_id": to_id, "may_id": mau.may_id},
        )
    bg = bg_svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai=TT_SAN_SANG, actor=admin)
    _giu_cho_du(db, bai_ghep_ids=[bg.id])       # tiền đề mới: giữ đủ vật tư mới vào kế hoạch
    xl_svc.dua_vao_bai_ghep(bai_ghep_id=bg.id, actor=admin)

    gang = XepLichRepository(db).by_bai_ghep(bg.id)
    assert len(gang) == 2, "gộp 2 công đoạn phải ra 2 dòng lịch, không phải 1"
    assert all(r.bai_ghep_cong_doan_id for r in gang), "dòng phải neo đích danh bước chung"
    # Máy lấy từ bước chung người dùng vừa khai, KHÔNG phải `bg.may_id` (bài chưa chọn máy).
    assert bg.may_id is None and all(r.may_id == mau.may_id for r in gang)
    # Thời lượng suy từ MÁY của chính bước chung (bài chưa chọn máy) — mọi dòng đều ra số > 0
    # bằng đúng công thức chung, không còn ô `chay_phut` gõ đè để ghim số cứng.
    assert all(xl_svc._thoi_luong(r)["chay_phut"] > 0 for r in gang)
    assert all(xl_svc._thoi_luong(r)["theo_may"] is True for r in gang)
    # Không lệnh nào còn giữ dòng riêng cho hai bước đã gộp.
    for lsx in created:
        assert XepLichRepository(db).by_lsx(lsx.id) == []


def test_bai_ghep_in_chung_mot_dong_loai_tru_in(db, orders, lsx_svc, bg_svc, xl_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Mỗi LSX thêm bước xả tờ (sau in) để thành viên còn công đoạn xếp riêng sau khi in chung.
    for lsx in created:
        db.add(LsxCongDoan(
            lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
            may_id=_in_step(db, lsx.id).may_id, so_luong_vao=5000, nang_suat=3000,
            don_vi_nang_suat="to_gio", don_vi_vao="to", don_vi_ra="to",
        ))
    db.commit()
    _nha_cho(db, [l.id for l in created])
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    bg = _gop_in_va_san_sang(db, bg_svc, bg, admin)

    xl_svc.dua_vao_bai_ghep(bai_ghep_id=bg.id, actor=admin)
    repo = XepLichRepository(db)

    gang = repo.by_bai_ghep(bg.id)
    assert len(gang) == 1 and gang[0].nguon == "in_ghep"        # in chung xuất hiện MỘT lần
    member = repo.by_lsx(created[0].id)
    assert len(member) == 1 and member[0].loai_buoc == LB_MAY  # in bị loại, còn xả tờ như bước Máy
    assert all(l.trang_thai == TT_DA_LAP_KE_HOACH for l in created)
    # Thành viên bài ghép KHÔNG gỡ kế hoạch trực tiếp (phải gỡ qua bài ghép) — tránh mồ côi dòng in chung.
    with pytest.raises(XepLichConflict):
        xl_svc.go_lsx(lsx_id=created[0].id, actor=admin)

    # Lane của lệnh đã ghép khuyết bước in (nó chạy chung ở bài) — mỗi dòng lệnh phải mang được mã
    # bài để màn Gantt ghi "in ở GB-xx". Thiếu thì người xem lịch thấy lệnh hụt một bước, không
    # có gì giải thích. Chính dòng in chung thì KHÔNG mang (nó là đích, không phải con trỏ).
    ds = {r["id"]: r for r in xl_svc.danh_sach()["items"]}
    assert ds[member[0].id]["gang_bai_ghep_id"] == bg.id
    assert ds[member[0].id]["gang_ma"] == bg.ma
    assert ds[gang[0].id]["gang_bai_ghep_id"] is None


def test_som_nhat_theo_gio_thuc_cua_buoc_truoc(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Gán In MUỘN → 'sớm nhất' của Xả tờ phải chạy theo giờ KẾT THÚC thực của In (không phải mốc lý
    thuyết) — nhờ đó cột Sớm nhất tự cảnh báo khi ai xếp bước sau chạy trước bước trước."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None  # In = 60 phút
    xa = LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
                     may_id=step.may_id, so_luong_vao=5000, nang_suat=6000, don_vi_nang_suat="to_gio",
                     don_vi_vao="to", don_vi_ra="to")
    db.add(xa)
    db.flush()
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=step.id, buoc_sau_id=xa.id))
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dongs = XepLichRepository(db).by_lsx(lsx.id)
    in_dong = next(d for d in dongs if d.source_thu_tu == 0)
    xa_dong = next(d for d in dongs if d.lsx_cong_doan_id != in_dong.lsx_cong_doan_id)
    # Gán In bắt đầu 28/7 08:00 → kết thúc 09:00.
    xl_svc.gan(dong_id=in_dong.id,
               patch={"may_id": step.may_id, "start_at": datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)},
               actor=admin)
    items = {it["id"]: it for it in xl_svc.danh_sach()["items"]}
    # Sớm nhất của Xả tờ KHÔNG được sớm hơn khi In kết thúc thật (09:00).
    assert items[xa_dong.id]["som_nhat"].replace(tzinfo=None) >= datetime(2026, 7, 28, 9, 0)


def test_dag_buoc_ghep_lay_moc_muon_nhat_cua_nhieu_tien_nhiem(
    db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch,
):
    monkeypatch.setattr("app.services.xep_lich_service._utcnow",
                        lambda: datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    # `som_nhat` còn bị chặn dưới bởi mốc BÀN GIAO SX (`_san_thoi_gian`), mà mốc đó do
    # `order_service.release_production` đóng dấu bằng giờ THẬT — nó không đi qua `_utcnow` vừa
    # patch ở trên. Không ghim lại thì hễ chạy sau 11:00 UTC là sàn giờ thật vượt mốc tiền nhiệm,
    # `som_nhat` thành "bây giờ" và test đỏ theo đồng hồ chứ không theo logic đang đo.
    lsx.ban_giao_at = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    db.commit()
    a = _in_step(db, lsx.id)
    b = LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Nhánh B", loai_buoc=LB_MAY,
                    may_id=a.may_id, so_luong_vao=100, nang_suat=100,
                    don_vi_vao="to", don_vi_ra="to")
    c = LsxCongDoan(lsx_id=lsx.id, thu_tu=2, ten="Ghép", loai_buoc=LB_MAY,
                    may_id=a.may_id, so_luong_vao=100, nang_suat=100,
                    don_vi_vao="to", don_vi_ra="to")
    db.add_all([b, c]); db.flush()
    db.add_all([
        LsxCongDoanPhuThuoc(buoc_truoc_id=a.id, buoc_sau_id=c.id),
        LsxCongDoanPhuThuoc(buoc_truoc_id=b.id, buoc_sau_id=c.id),
    ])
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    rows = XepLichRepository(db).by_lsx(lsx.id)
    by_step = {r.lsx_cong_doan_id: r for r in rows}
    by_step[a.id].finish_at = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)
    by_step[b.id].finish_at = datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc)
    db.commit()
    items = {it["id"]: it for it in xl_svc.danh_sach()["items"]}
    assert items[by_step[c.id].id]["som_nhat"].replace(tzinfo=None) == datetime(2026, 8, 3, 11, 0)


def test_cong_gio_lam_tran_sang_ngay_ke(db, xl_svc, monkeypatch):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    # 600 phút = 8h ngày đầu (đến 16:00) + 120 phút ngày kế (08:00 → 10:00). Tập ca rỗng (seed không
    # tick `dung_cho_lich_may`) → LichXuong fallback 8h phẳng [08:00,16:00) giữ nguyên hành vi lát 1.
    assert _cong_gio_lam(bat_dau, 600, xl_svc.lich) == datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


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
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1  # theo máy: 30+60 = 90 phút
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": bat_dau}, actor=admin)

    # Gán LẠI, chỉ đổi máy — KHÔNG kèm start_at (giống inline popover). Không được lỗi.
    res = xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id}, actor=admin)
    assert res.trang_thai == "da_xep"
    assert res.start_at.replace(tzinfo=None) == datetime(2026, 7, 27, 8, 0)   # giờ giữ nguyên
    assert res.finish_at.replace(tzinfo=None) == datetime(2026, 7, 27, 9, 30)  # 08:00 + 90 (theo máy)


# --- LichXuong: lịch máy theo CA THẬT (nghỉ trưa / ca đêm / fallback) ---------
def _lich(cas, working=lambda d: True) -> LichXuong:
    """Dựng LichXuong nhanh: `cas` = list (start_minute, end_minute, is_overnight)."""
    cal = SimpleNamespace(is_working_day=working)
    rows = [SimpleNamespace(start_minute=s, end_minute=e, is_overnight=o) for s, e, o in cas]
    return LichXuong(cal, rows)


def test_khung_ca_nghi_trua():
    lich = _lich([(480, 720, False), (780, 1020, False)])  # ca sáng 08–12, ca chiều 13–17
    t = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    # 300 phút = 4h sáng (08→12) + 1h chiều (13→14); nghỉ trưa 12–13 bị NHẢY, không tính.
    assert _cong_gio_lam(t, 300, lich) == datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc)
    # Bắt đầu GIỮA nghỉ trưa 12:30 → dời tới đầu ca chiều 13:00.
    assert _dau_ca(datetime(2026, 7, 27, 12, 30, tzinfo=timezone.utc), lich) == \
        datetime(2026, 7, 27, 13, 0, tzinfo=timezone.utc)


def test_ca_dem_qua_nua_dem():
    lich = _lich([(1320, 360, True)])  # ca đêm 22:00 → 06:00 hôm sau
    t = datetime(2026, 7, 27, 22, 0, tzinfo=timezone.utc)
    assert _cong_gio_lam(t, 300, lich) == datetime(2026, 7, 28, 3, 0, tzinfo=timezone.utc)  # trong ca
    assert _cong_gio_lam(t, 480, lich) == datetime(2026, 7, 28, 6, 0, tzinfo=timezone.utc)  # trọn ca 8h
    # Tràn 1 phút → hết ca đêm (06:00) rồi sang ca đêm KẾ (22:00 ngày 28) + 1 phút.
    assert _cong_gio_lam(t, 481, lich) == datetime(2026, 7, 28, 22, 1, tzinfo=timezone.utc)


def test_tap_ca_rong_fallback_phang():
    lich = _lich([])  # không ca lịch-máy nào → fallback 8h phẳng [08:00,16:00)
    t = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    assert _cong_gio_lam(t, 600, lich) == datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


def test_lich_nen_may_lien_tuc(db, xl_svc, monkeypatch):
    """Nền Gantt của MÁY = trọn ngày làm việc (2026-08-10: máy chạy liên tục, bỏ ca của máy).

    Trước đây là 8h/ngày theo ca. Nay 24h — thanh việc xếp lúc 22h phải nằm TRONG nền, không thì
    người xem tưởng lịch sai.
    """
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    res = xl_svc.lich_nen_may(may_id=1, tu=date(2026, 7, 27), den=date(2026, 7, 28))
    assert res["may_id"] == 1 and res["khoang_khoa"] == []
    assert len(res["khoang_lam"]) == 2  # 1 khoảng/ngày × 2 ngày
    assert all((k["finish"] - k["start"]).total_seconds() / 3600 == 24 for k in res["khoang_lam"])


def test_gan_ghi_audit(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    from app.models.audit import AuditLog
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    xl_svc.gan(dong_id=dong.id,
               patch={"may_id": step.may_id, "start_at": datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)},
               actor=admin)
    logs = db.query(AuditLog).filter(
        AuditLog.target == f"xep_lich:{dong.id}", AuditLog.action == "xep_lich_gan"
    ).all()
    assert len(logs) >= 1


# --- HM2: vùng máy không khả dụng (né khi cộng giờ / khe trống + CRUD) --------
def test_cong_gio_nhay_qua_vung_khoa():
    lich = _lich([])  # fallback 8h phẳng [08:00,16:00)
    chan = ((datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
             datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)),)  # bảo trì 10–12
    t = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    # 120' = 08→10 vừa chạm đầu khóa (chưa đụng).
    assert _cong_gio_lam(t, 120, lich, chan) == datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)
    # 180' = 08→10 (120') + khóa 10–12 NHẢY + 12→13 (60') = 13:00.
    assert _cong_gio_lam(t, 180, lich, chan) == datetime(2026, 7, 27, 13, 0, tzinfo=timezone.utc)


def test_gan_ne_vung_khoa(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao = 0, 5000, 15000  # theo máy: 30+180+15 = 225'
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    xl_svc.tao_vung_khoa(may_id=step.may_id,
                         tu=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                         den=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
                         ly_do="bao_tri", note=None, actor=admin)
    res = xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id,
                     "start_at": datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)}, actor=admin)
    # 210' (theo máy) né khóa 10–12: 08→10 (120') + 12→13:30 (90') = 13:30.
    assert res.finish_at.replace(tzinfo=None) == datetime(2026, 7, 27, 13, 30)


def test_vung_khoa_crud_va_lich_nen(db, xl_svc, admin, monkeypatch):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    x = xl_svc.tao_vung_khoa(may_id=25,
                             tu=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                             den=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
                             ly_do="bao_tri", note="vệ sinh", actor=admin)
    assert x["id"] and x["may_id"] == 25 and x["ly_do"] == "bao_tri"
    # Đầu ra phải NAIVE (wall-clock giờ nhà máy) — FE `new Date` không dịch múi (tránh lệch +7h).
    assert x["start"].tzinfo is None and x["finish"].tzinfo is None
    nen = xl_svc.lich_nen_may(may_id=25, tu=date(2026, 7, 27), den=date(2026, 7, 27))
    assert len(nen["khoang_khoa"]) == 1 and nen["khoang_khoa"][0]["ly_do"] == "bao_tri"
    assert nen["khoang_khoa"][0]["start"].tzinfo is None
    assert all(k["start"].tzinfo is None for k in nen["khoang_lam"])
    assert any(k["id"] == x["id"] for k in xl_svc.vung_khoa_range(tu=date(2026, 7, 27), den=date(2026, 7, 27)))
    assert len(xl_svc.list_vung_khoa(may_id=25)) == 1
    xl_svc.xoa_vung_khoa(pid=x["id"], actor=admin)
    assert xl_svc.list_vung_khoa(may_id=25) == []


def test_vung_khoa_tu_sau_den_bao_loi(db, xl_svc, admin):
    with pytest.raises(XepLichValidationError):
        xl_svc.tao_vung_khoa(may_id=25,
                             tu=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
                             den=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                             ly_do="bao_tri", note=None, actor=admin)


# --- HM3: thời lượng TÍNH LẠI theo máy đang gán (to_gio ⟷ tờ) -----------------
def test_thoi_luong_theo_may_khop_don_vi(db, orders, lsx_svc, xl_svc, admin, customer):
    """Bước In gán máy `to_gio`, bước vào `tờ` → tính LẠI theo máy (makeready + tốc-độ + rửa-mực),
    BỎ QUA snapshot nang_suat/setup/vệ-sinh vô lý của bước."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao = 999, 1, 5000   # snapshot cố tình vô lý
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 999, 1
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    d = xl_svc._thoi_luong(dong)
    assert d["theo_may"] is True and d["canh_bao"] is None
    # makeready 30 + 5000/5000*60=60 = 90 (KHÔNG lấy snapshot 999). Vệ sinh đã gỡ khỏi hệ nên
    # `ve_sinh_phut=999` của bước bị bỏ qua hoàn toàn — breakdown cũng không còn khoá đó.
    assert d["setup_phut"] == 30 and d["chay_phut"] == 60
    assert "ve_sinh_phut" not in d
    assert d["chiem_may_phut"] == 90


def test_xep_lich_va_drawer_cung_mot_so_khi_don_vi_may_lech(
    db, orders, lsx_svc, xl_svc, admin, customer,
):
    """⭐ Máy khai `m2_gio` mà bước đếm `tờ`, chưa khai quy đổi ⇒ **xếp lịch cũng không bịa giờ**.

    🔴 ĐỔI 15/08/2026 — test này trước đây chốt "kệ nhãn, cứ chia con số" (5.000 tờ ÷ 5.000 m²/giờ
    = 60 phút). Nay Gantt phải nói cùng một câu với drawer lệnh: quy đổi được thì tính, không thì
    thôi + cảnh báo `chua_quy_doi`. Điều KHÔNG được phép là hai màn ra hai số.
    """
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.so_luong_vao, step.so_luot_chay = 5000, 1
    may = db.get(MayThietBi, step.may_id)
    may.don_vi_toc_do = "m2_gio"
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    d = xl_svc._thoi_luong(dong)
    assert d["chay_phut"] == 0 and d["canh_bao"] == "chua_quy_doi"
    assert d["setup_phut"] == float(may.makeready_time_default or 0)
    assert d["chiem_may_phut"] == d["setup_phut"]

    # Cùng bước, cùng máy → drawer lệnh phải ra ĐÚNG con số đó.
    buoc = next(b for b in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
                if b["id"] == step.id)
    assert buoc["chay_phut"] == d["chay_phut"]
    assert buoc["chiem_may_phut"] == d["chiem_may_phut"]


# --- HM4: kiểm KHẢ NĂNG máy (mềm — máy đề xuất, người quyết) -------------------
def test_kiem_kha_nang_chi_con_kiem_kho():
    """CHỈ CÒN KIỂM KHỔ (chốt 2026-08-09) — bỏ số màu và định lượng.

    Khổ là tiêu chí VẬT LÝ tuyệt đối: tờ không lọt máy thì không có cách nào chạy. Số màu thì thợ
    chạy 2 lượt là qua (chuyện thường ngày, không phải sự cố), còn khoảng gsm ở danh mục máy phần
    lớn chưa khai đúng nên nó loại nhầm máy chạy được — cảnh báo mà sai thì người ta thôi tin nó.
    """
    from app.services._may_fit import kiem_kha_nang
    qc = {"kho_in_dai": 650, "kho_in_rong": 900, "so_mau_a": 4, "so_mau_b": 0, "gsm": 350}
    nho = SimpleNamespace(kho_max_dai=520, kho_max_rong=360, so_units=2,
                          min_stock_gsm=80, max_stock_gsm=250)
    # Máy nhỏ: vẫn nêu KHỔ, KHÔNG còn nêu số màu / gsm dù cả hai đều ngoài ngưỡng.
    assert kiem_kha_nang(qc, nho) == ["kho_vuot_may"]
    big = SimpleNamespace(kho_max_dai=1200, kho_max_rong=1000, so_units=8,
                          min_stock_gsm=50, max_stock_gsm=400)
    assert kiem_kha_nang(qc, big) == []          # đủ lớn → không nghi ngờ
    assert kiem_kha_nang(qc, None) == []          # chưa gán máy → bỏ qua
    # Máy 2 đầu mực + khoảng gsm hẹp nhưng khổ VỪA ⇒ im lặng, đúng ý chốt.
    hep = SimpleNamespace(kho_max_dai=1200, kho_max_rong=1000, so_units=2,
                          min_stock_gsm=80, max_stock_gsm=250)
    assert kiem_kha_nang(qc, hep) == []
    # Thiếu spec máy (None) → BỎ tiêu chí, không dựng cảnh báo giả.
    thieu = SimpleNamespace(kho_max_dai=None, kho_max_rong=None, so_units=None,
                            min_stock_gsm=None, max_stock_gsm=None)
    assert kiem_kha_nang(qc, thieu) == []


def test_dau_muc_can_dem_theo_tap_muc_khong_theo_so_mau_process():
    """Số đầu mực máy phải có = đếm TẬP MỰC, không phải `max` hai số màu process.

    `so_mau_a/b` chỉ đếm CMYK nên "CMYK + 1 Pantone" ra 4 — máy 4 đơn vị lọt cửa trong khi thợ ra
    máy mới biết thiếu một đầu mực.
    """
    from app.services._may_fit import LY_DO_SO_MAU, dau_muc_can, kiem_kha_nang

    cmyk = ["C", "M", "Y", "K"]
    may4 = SimpleNamespace(kho_max_dai=1200, kho_max_rong=1000, so_units=4,
                           min_stock_gsm=50, max_stock_gsm=400)
    kho = {"kho_in_dai": 650, "kho_in_rong": 900, "gsm": 300}

    # AB: mỗi lượt chạy MỘT mặt → max(|A|,|B|). CMYK/K vừa máy 4 đơn vị.
    ab = {**kho, "quy_cach_in": "hai_mat", "muc_a": cmyk, "muc_b": ["K"]}
    assert dau_muc_can(ab) == 4
    # Thêm Pantone vào mặt A → 5 đầu mực (max hai số màu process sẽ ra 4).
    ab5 = {**ab, "muc_a": cmyk + ["185C"]}
    assert dau_muc_can(ab5) == 5

    # Tự trở: một lượt chạy CẢ HAI mặt trên chung bản → hợp tập, không phải max.
    tu = {**kho, "quy_cach_in": "tu_tro", "muc_a": cmyk, "muc_b": ["185C"]}
    assert dau_muc_can(tu) == 5                       # max sẽ ra 4
    # Cùng bộ mực hai mặt thì hợp lại vẫn 4.
    assert dau_muc_can({**tu, "muc_b": ["K"]}) == 4

    # ⚠️ Từ 2026-08-09 `dau_muc_can` KHÔNG còn chỗ gọi nào trong app (chủ chốt "cảnh báo khả năng
    # máy chỉ theo KHỔ") — chỉ test này còn dùng. GIỮ hàm + test vì công thức số đầu mực là thứ
    # module kẽm sẽ cần; nhưng đừng đọc mấy dòng trên thành "đang chạy trong sản phẩm".
    assert LY_DO_SO_MAU not in kiem_kha_nang(ab5, may4)
    assert LY_DO_SO_MAU not in kiem_kha_nang(tu, may4)

    # Lệnh CŨ chưa có tập mực → rơi về hai số như trước.
    assert dau_muc_can({**kho, "so_mau_a": 6, "so_mau_b": 2}) == 6
    assert dau_muc_can({}) == 0


def test_can_xac_nhan_khi_gan_may_nho(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """danh_sach nêu cờ can_xac_nhan khi bước In bị gán sang máy nhỏ hơn khổ tờ in — KHÔNG chặn gán."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]   # quy_cach kho_in 650×900
    nho = MayThietBi(ma="MAY-NHO", ten="Máy con", loai_may="press_offset_sheet",
                     toc_do=3000, don_vi_toc_do="to_gio", kho_max_dai=520, kho_max_rong=360)
    db.add(nho)
    db.flush()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    res = xl_svc.gan(dong_id=dong.id, patch={"may_id": nho.id,
                     "start_at": datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)}, actor=admin)
    assert res.trang_thai == "da_xep"           # vẫn gán được (soft-check, không chặn)
    it = {x["id"]: x for x in xl_svc.danh_sach()["items"]}[dong.id]
    assert it["can_xac_nhan"] is True
    # Chỉ còn KHỔ — máy 2 đầu mực không còn là lý do (chốt 2026-08-09).
    assert it["ly_do_xac_nhan"] == ["kho_vuot_may"]


# --- HM5: xem trước ảnh hưởng khi kéo-thả (KHÔNG commit) ----------------------
def test_xem_truoc_khong_commit(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Xem trước trả finish giả định (theo máy) NHƯNG không đổi DB — dòng vẫn `cho_xep`, chưa có giờ."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong_id = XepLichRepository(db).by_lsx(lsx.id)[0].id
    res = xl_svc.xem_truoc(dong_id=dong_id, may_id=step.may_id,
                           start_at=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc))
    assert res["finish_at"].replace(tzinfo=None) == datetime(2026, 7, 27, 9, 30)  # theo máy 90'
    assert res["finish_at"].tzinfo is None                                        # wall-clock naive
    db.expire_all()
    fresh = XepLichRepository(db).get(dong_id)
    assert fresh.start_at is None and fresh.finish_at is None and fresh.trang_thai == "cho_xep"


def test_xem_truoc_day_buoc_sau(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Xem trước gán In muộn → bước Xả tờ (sau) bị ĐẨY: som_nhat mới ≥ giờ In kết thúc giả định."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None
    xa = LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
                     may_id=step.may_id, so_luong_vao=5000, nang_suat=6000, don_vi_nang_suat="to_gio",
                     don_vi_vao="to", don_vi_ra="to")
    db.add(xa)
    db.flush()
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=step.id, buoc_sau_id=xa.id))
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dongs = XepLichRepository(db).by_lsx(lsx.id)
    in_id = next(d.id for d in dongs if d.source_thu_tu == 0)
    xa_id = next(d.id for d in dongs if d.source_thu_tu == 1)
    res = xl_svc.xem_truoc(dong_id=in_id, may_id=step.may_id,
                           start_at=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc))
    xa = next((x for x in res["day_doi"] if x["id"] == xa_id), None)
    assert xa is not None and xa["som_nhat"].replace(tzinfo=None) >= datetime(2026, 7, 28, 9, 30)


def test_xem_truoc_bao_xung_dot(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Xem trước thả B chồng giờ với A đã xếp trên cùng máy → nêu id A trong `xung_dot_ids`."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for lsx in (a, b):
        s = _in_step(db, lsx.id)
        s.setup_phut, s.nang_suat, s.so_luong_vao, s.chay_phut = 0, 5000, 5000, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    xl_svc.dua_vao_lsx(lsx_id=b.id, actor=admin)
    repo = XepLichRepository(db)
    may_id = _in_step(db, a.id).may_id
    a_id, b_id = repo.by_lsx(a.id)[0].id, repo.by_lsx(b.id)[0].id
    xl_svc.gan(dong_id=a_id, patch={"may_id": may_id,
               "start_at": datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)}, actor=admin)  # A: 08:00→09:45
    res = xl_svc.xem_truoc(dong_id=b_id, may_id=may_id,
                           start_at=datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc))       # B chồng A
    assert a_id in res["xung_dot_ids"]


def test_lenh_in_hai_luot_chi_loai_dung_luot_duoc_ghep(
    db, orders, lsx_svc, bg_svc, xl_svc, admin, customer
):
    """Quét cả nhóm `print` sẽ làm BỐC HƠI cả hai lượt in khỏi board — lớp đè theo `step_key` mới đúng."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for lsx in created:
        db.add(LsxCongDoan(
            lsx_id=lsx.id, thu_tu=1, ten="In mặt sau", nhom="print", loai_buoc=LB_MAY,
            may_id=_in_step(db, lsx.id).may_id, so_luong_vao=5000, nang_suat=3000,
            don_vi_nang_suat="to_gio", don_vi_vao="to", don_vi_ra="to",
        ))
    db.commit()
    _nha_cho(db, [l.id for l in created])
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)

    # Hai lượt in → máy không đoán, bài chưa có gì chạy chung cho tới khi người gộp.
    assert "thieu_buoc_chung" in bg_svc.thieu_cua(bg_svc._get(bg.id))
    bg = _gop_in_va_san_sang(db, bg_svc, bg, admin)   # gộp ĐÚNG lượt mặt trước

    xl_svc.dua_vao_bai_ghep(bai_ghep_id=bg.id, actor=admin)
    member = XepLichRepository(db).by_lsx(created[0].id)
    assert [r.source_thu_tu for r in member] == [1]     # chỉ lượt ĐƯỢC NEO bị loại


# --- 2f: cảnh báo TẠI CHỖ THẢ (xem trước) -------------------------------------
# Bốn thứ này KHÔNG chặn (chốt 18/08/2026) — nhưng phải nói ra, không thì người kéo thanh không
# hề biết mình vừa thả vào giữa khoảng bảo trì hay vào ngày nghỉ.
def _dong_in_san_sang(db, orders, lsx_svc, xl_svc, admin, customer):
    """Một lệnh có bước In 90 phút đã vào kế hoạch — nền chung cho 4 test cảnh báo."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    return XepLichRepository(db).by_lsx(lsx.id)[0], step


def _loai(res) -> set:
    return {c["loai"] for c in res["canh_bao"]}


def test_xem_truoc_bao_de_vung_khoa_may(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Thả đúng vào khoảng bảo trì → nói ngay, kèm giờ khóa. Engine vẫn nhảy qua (không chặn)."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    dong, step = _dong_in_san_sang(db, orders, lsx_svc, xl_svc, admin, customer)
    db.add(MachineUnavailablePeriod(
        may_id=step.may_id, kieu=KIEU_CHAN, reason=LY_DO_BAO_TRI,
        unavailable_from=datetime(2026, 7, 27, 7, 0, tzinfo=timezone.utc),
        unavailable_to=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
    ))
    db.commit()
    res = xl_svc.xem_truoc(dong_id=dong.id, may_id=step.may_id,
                           start_at=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc))
    assert "khoa_may" in _loai(res)
    chu = next(c["chu"] for c in res["canh_bao"] if c["loai"] == "khoa_may")
    assert "27/07" in chu and "bao_tri" in chu


def test_xem_truoc_bao_ngoai_gio_lam(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Thả vào NGÀY NGHỈ → nêu mốc việc thật sự bắt đầu được, không im lặng đẩy sang hôm sau."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: d != date(2026, 7, 26))
    dong, step = _dong_in_san_sang(db, orders, lsx_svc, xl_svc, admin, customer)
    res = xl_svc.xem_truoc(dong_id=dong.id, may_id=step.may_id,
                           start_at=datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc))
    assert "ngoai_gio" in _loai(res)
    assert "27/07" in next(c["chu"] for c in res["canh_bao"] if c["loai"] == "ngoai_gio")


def test_xem_truoc_bao_to_thieu_nguoi(db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch):
    """Bước cần 3 người mà tổ gõ đè còn 1 → báo. Số người lấy từ QUÂN SỐ THẬT của tổ hôm đó."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    dong, step = _dong_in_san_sang(db, orders, lsx_svc, xl_svc, admin, customer)
    to = _to_san_xuat(db)
    step.so_nhan_cong = 3
    dong.department_id = to.id
    db.commit()
    xl_svc.dat_quan_so(department_id=to.id, ngay=date(2026, 7, 27), so_nguoi=1,
                       ly_do="cả tổ nghỉ, còn 1 người trực", actor=admin)
    res = xl_svc.xem_truoc(dong_id=dong.id, may_id=step.may_id,
                           start_at=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc))
    assert "thieu_nguoi" in _loai(res)
    chu = next(c["chu"] for c in res["canh_bao"] if c["loai"] == "thieu_nguoi")
    assert "cần 3 người" in chu and "có mặt 1" in chu


def test_xem_truoc_tha_sach_thi_khong_canh_bao_gi(db, orders, lsx_svc, xl_svc, admin, customer,
                                                  monkeypatch):
    """Thả đúng chỗ đẹp → danh sách RỖNG. Cảnh báo kêu cả lúc không có gì thì người dùng học cách
    bỏ qua cảnh báo — hỏng hơn là không có."""
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    dong, step = _dong_in_san_sang(db, orders, lsx_svc, xl_svc, admin, customer)
    res = xl_svc.xem_truoc(dong_id=dong.id, may_id=step.may_id,
                           start_at=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc))
    assert res["canh_bao"] == []


def test_canh_bao_di_het_duong_dict_den_schema(db, orders, lsx_svc, xl_svc, admin, customer,
                                               monkeypatch):
    """Pydantic nuốt field IM LẶNG: không khai ở `XemTruocOut` thì FE nhận `undefined`, không lỗi."""
    from app.schemas.xep_lich import XemTruocOut

    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: d != date(2026, 7, 26))
    dong, step = _dong_in_san_sang(db, orders, lsx_svc, xl_svc, admin, customer)
    res = xl_svc.xem_truoc(dong_id=dong.id, may_id=step.may_id,
                           start_at=datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc))
    assert "canh_bao" in XemTruocOut.model_fields
    ra = XemTruocOut.model_validate(res)
    assert [c.loai for c in ra.canh_bao] == [c["loai"] for c in res["canh_bao"]]
    assert ra.model_dump()["canh_bao"][0]["chu"]
