"""GIỮ CHỖ vật tư (Đợt 2, 17/08/2026) — bật · tắt · tự nhặt thêm · tồn tự do.

Trọng tâm là mấy chỗ mà sai thì KHÔNG AI BÁO, chỉ có hệ quả ngoài đời:

* tồn tự do không trừ phần đã giữ ⇒ hai lệnh cùng tưởng mình có hàng, lịch cả hai thành lịch ma;
* giữ chỗ không gộp các BƯỚC ⇒ lệnh ăn cùng món ở hai công đoạn được mở khoá xếp lịch khi mới có
  một nửa (cùng họ với lỗi ① của Đợt 1);
* dòng "chưa đánh giá được" bị coi là 0 ⇒ mở khoá cho lệnh chưa ai biết cần bao nhiêu;
* tắt rồi bật lại tưởng là hoàn tác.

Dựng dữ liệu THẲNG vào DB như `test_ke_hoach_vat_tu.py` — cái đang kiểm là phép cộng trừ của giữ
chỗ, không phải luồng bán.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
from app.models.customer import Customer
from app.models.lsx import TT_SAN_SANG, Lsx, LsxCongDoan, LsxCongDoanVatTu
from app.models.may_thiet_bi import MayThietBi
from app.models.order import Order, OrderLine
from app.models.purchase import (
    DPR_OPEN,
    PR_PURCHASED,
    SOURCE_SAN_XUAT,
    DepartmentPurchaseRequest,
    DepartmentPurchaseRequestLine,
    PurchaseRequest,
    PurchaseRequestLine,
)
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
from app.seed import seed_all
from app.services.giu_cho_service import GiuChoService
from app.services.ke_hoach_vat_tu_service import KeHoachVatTuService
from app.services.vat_lieu_kho_service import VatLieuKhoService

HOM_NAY = date.today()
MAI = HOM_NAY + timedelta(days=1)


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
def kh(db):
    return KeHoachVatTuService(
        db, lsx_repo=LsxRepository(db), bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db), requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db), suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )


@pytest.fixture
def svc(db, kh):
    return GiuChoService(db, kh)


@pytest.fixture
def customer(db):
    c = Customer(code="KH-1", name="Khách test")
    db.add(c)
    db.commit()
    return c


# --- dựng dữ liệu -------------------------------------------------------------


def _giay(db, *, ma="GY-1") -> GiayNguyen:
    """Giấy 65×86 định lượng 150 ⇒ 1 tờ = 0,15 × 0,86 × 0,65 = 0,08385 kg."""
    g = GiayNguyen(ma=ma, ten=f"Giấy {ma}", gsm=150, kho_dai=860, kho_rong=650, don_vi_gia="kg",
                   cong_thuc_luong="dinh_luong * dai_nguyen * rong_nguyen * to_nguyen")
    db.add(g)
    db.commit()
    return g


def _may(db) -> MayThietBi:
    m = db.query(MayThietBi).filter(MayThietBi.ma == "MAY-GC").first()
    if m is None:
        m = MayThietBi(ma="MAY-GC", ten="Máy test", loai_may="press_offset_sheet", toc_do=1_000,
                       don_vi_toc_do="to_gio", makeready_time_default=30,
                       kho_max_dai=1020, kho_max_rong=720)
        db.add(m)
        db.commit()
    return m


def _lenh(db, customer, *, ma, giay_id, so_to_nguyen, han=MAI) -> Lsx:
    o = Order(order_no=f"DH-{ma}", customer_id=customer.id)
    db.add(o)
    db.flush()
    ln = OrderLine(order_id=o.id, description="x", qty=1_000)
    db.add(ln)
    db.flush()
    l = Lsx(ma=ma, ten=ma, order_id=o.id, order_line_id=ln.id, so_luong_dat=1_000,
            so_to_nguyen=so_to_nguyen, so_con=1, han_hoan_thanh_sx=han,
            quy_cach_json={"giay_id": giay_id}, trang_thai=TT_SAN_SANG)
    db.add(l)
    db.flush()
    db.add(LsxCongDoan(lsx_id=l.id, thu_tu=1, ten="In offset", loai_buoc="may", may_id=_may(db).id,
                       don_vi_vao="to_nguyen", don_vi_ra="to",
                       so_luong_vao=so_to_nguyen, so_luong_ra=so_to_nguyen))
    db.commit()
    return l


def _ton(db, hang, so_luong) -> None:
    kho = db.query(KhoHang).first()
    if kho is None:
        kho = KhoHang(ma="K1", ten="Kho test")
        db.add(kho)
        db.flush()
    db.add(StockLot(hang_loai=hang[0], hang_id=hang[1], kho_id=kho.id,
                    ma_lo=f"LOT-{hang[0]}{hang[1]}-{so_luong}", sl_ban_dau=so_luong,
                    sl_con_lai=so_luong, ngay_nhap=HOM_NAY, trang_thai=LOT_AVAILABLE))
    db.commit()


def _phieu_mua(db, *, hang, so_luong, ngay_ve, unit="kg") -> None:
    p = PurchaseRequest(code=f"PMH-{db.query(PurchaseRequest).count() + 1}",
                        status=PR_PURCHASED, expected_receipt_date=ngay_ve)
    db.add(p)
    db.flush()
    db.add(PurchaseRequestLine(purchase_request_id=p.id, item_name="Giấy mua",
                               hang_loai=hang[0], hang_id=hang[1], unit=unit,
                               quantity=so_luong, expected_unit_price=1))
    db.commit()


def _ycmh(db, *, hang, so_luong, status=DPR_OPEN, unit="kg") -> DepartmentPurchaseRequest:
    """Đề nghị mua của bộ phận — đúng thứ mà nút "Mua" trên thẻ lệnh đẻ ra."""
    yc = DepartmentPurchaseRequest(
        code=f"YCMH-{db.query(DepartmentPurchaseRequest).count() + 1}",
        status=status, source_type=SOURCE_SAN_XUAT, purpose="Thiếu vật tư", needed_date=HOM_NAY,
    )
    db.add(yc)
    db.flush()
    db.add(DepartmentPurchaseRequestLine(
        department_request_id=yc.id, item_name="Giấy đề nghị",
        hang_loai=hang[0], hang_id=hang[1], unit=unit, quantity=so_luong,
    ))
    db.commit()
    return yc


def _giay_hang(g) -> tuple[str, int]:
    return ("giay", g.id)


# ================== TỒN TỰ DO ==================


def test_ton_tu_do_TRU_phan_da_giu(db, svc, customer):
    """Con số kho cho người khác lĩnh = tồn − Σ đã giữ. Không trừ là hai lệnh cùng tưởng có hàng."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg

    assert svc.ton_tu_do([_giay_hang(g)])[_giay_hang(g)] == pytest.approx(100)
    svc.bat(lsx_id=a.id)
    con = svc.ton_tu_do([_giay_hang(g)])[_giay_hang(g)]
    assert con == pytest.approx(100 - 16.77, abs=0.05), f"phải trừ phần đã giữ, thực tế {con}"


def test_lenh_thu_hai_chi_nhat_duoc_phan_CON_LAI(db, svc, customer):
    """Ai bật trước ăn trước phần tự do — lệnh sau nhìn phần còn lại, không giữ chồng lên nhau."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 20)                                    # đủ cho A, thiếu cho B
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200, han=MAI)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200,
              han=HOM_NAY + timedelta(days=30))

    assert svc.bat(lsx_id=a.id)["du"] is True
    tt_b = svc.bat(lsx_id=b.id)
    assert tt_b["du"] is False, "chỉ còn ~3 kg tự do, không đủ cho lệnh thứ hai"
    assert sum(tt_b["dang_giu"].values()) == pytest.approx(20 - 16.77, abs=0.05)


# ================== BẬT · TẮT ==================


def test_bat_giu_du_thi_mo_khoa_xep_lich(db, svc, customer):
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)

    assert svc.du_chua(lsx_id=a.id) is False, "chưa bật thì chưa giữ gì"
    assert svc.bat(lsx_id=a.id)["du"] is True
    assert db.get(Lsx, a.id).giu_cho_bat is True


def test_tat_NHA_THAT_va_tra_lai_ton_tu_do(db, svc, customer):
    """Tắt ≠ hoàn tác: hàng quay về tồn tự do, ai cũng lấy được."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)

    tt = svc.tat(lsx_id=a.id)
    assert tt["du"] is False and tt["dang_giu"] == {}
    assert db.get(Lsx, a.id).giu_cho_bat is False
    assert svc.ton_tu_do([_giay_hang(g)])[_giay_hang(g)] == pytest.approx(100)


def test_bat_hai_lan_KHONG_giu_gap_doi(db, svc, customer):
    """Bấm lại nút khi đã đủ ⇒ không đẻ thêm dòng nào."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)

    svc.bat(lsx_id=a.id)
    tong1 = sum(svc.trang_thai(lsx_id=a.id)["dang_giu"].values())
    svc.bat(lsx_id=a.id)
    assert sum(svc.trang_thai(lsx_id=a.id)["dang_giu"].values()) == pytest.approx(tong1)


# ================== BẬT = ĐĂNG KÝ, HÀNG VỀ TỰ NHẶT ==================


def test_bat_khi_kho_TRONG_van_giu_cho_va_tu_nhat_khi_hang_ve(db, svc, customer):
    """Đây là toàn bộ lý do "bật = đăng ký": không bắt ai nhớ quay lại bấm đúng lúc hàng nhập kho."""
    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)

    tt = svc.bat(lsx_id=a.id)
    assert tt["du"] is False and tt["dang_giu"] == {}
    assert db.get(Lsx, a.id).giu_cho_bat is True, "công tắc VẪN bật dù chưa giữ được gì"

    _ton(db, _giay_hang(g), 100)                    # hàng về nhập kho
    svc.nhat_them()
    assert svc.du_chua(lsx_id=a.id) is True, "phải TỰ bù, không bắt bấm lại"


def test_hang_ve_thi_lenh_CAN_SOM_nhat_duoc_uu_tien(db, svc, customer):
    """Theo NGÀY CẦN, không theo ai bật trước. Cùng luật con trỏ của bảng cân đối."""
    g = _giay(db)
    muon = _lenh(db, customer, ma="LSX-MUON", giay_id=g.id, so_to_nguyen=200,
                 han=HOM_NAY + timedelta(days=30))
    som = _lenh(db, customer, ma="LSX-SOM", giay_id=g.id, so_to_nguyen=200, han=MAI)

    svc.bat(lsx_id=muon.id)                          # bật TRƯỚC
    svc.bat(lsx_id=som.id)
    _ton(db, _giay_hang(g), 20)                      # chỉ đủ cho MỘT lệnh
    svc.nhat_them()

    assert svc.du_chua(lsx_id=som.id) is True, "lệnh cần sớm phải được ăn trước"
    assert svc.du_chua(lsx_id=muon.id) is False


# ================== GIỮ HỨA (lô đang về) ==================


def test_giu_hua_bam_lo_dang_ve_va_CHAN_DUOI_lich(db, svc, customer):
    """Hàng chưa có thật thì ngày về là chặn dưới của lịch — nhốt rắc rối ngày vào đúng một nhánh."""
    g = _giay(db)
    ve = HOM_NAY + timedelta(days=10)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=ve)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200,
              han=HOM_NAY + timedelta(days=40))

    tt = svc.bat(lsx_id=a.id)
    assert tt["du"] is True
    assert tt["xep_som_nhat"] == ve, "giữ hứa ⇒ không xếp lịch trước ngày về"


def test_giu_CHAC_thi_khong_rang_buoc_ngay(db, svc, customer):
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)

    assert svc.bat(lsx_id=a.id)["xep_som_nhat"] is None


def test_hai_lenh_KHONG_cung_bam_mot_lo_dang_ve(db, svc, customer):
    """Không trừ phần đã hứa thì hai lệnh cùng bám một lô và cả hai đều tưởng mình có hàng."""
    g = _giay(db)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=20, ngay_ve=HOM_NAY + timedelta(days=10))
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200, han=MAI)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200,
              han=HOM_NAY + timedelta(days=30))

    assert svc.bat(lsx_id=a.id)["du"] is True
    assert svc.bat(lsx_id=b.id)["du"] is False, "lô 20 kg chỉ đủ cho một lệnh"


# ================== HÀNG ĐANG VỀ MANG ĐÚNG DÒNG PHIẾU ==================


def test_nhat_them_gan_dung_purchase_request_line_id(db, svc, kh, customer):
    """Dòng giữ `dang_ve` mới đẻ ra phải bám ĐÚNG dòng phiếu mua đã sinh ra lô đang về đó — không
    thì đối soát sau này (Task 3) không biết nhả theo dòng nào."""
    from app.models.purchase import PurchaseRequestLine
    from app.models.vat_tu_giu_cho import NGUON_DANG_VE

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()

    svc.bat(lsx_id=a.id)

    rows = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    ve = [r for r in rows if r.nguon == NGUON_DANG_VE]
    assert ve, "phải giữ được từ lô đang về"
    assert all(r.purchase_request_line_id == line.id for r in ve)


# ================== GỘP CÁC BƯỚC (cùng họ lỗi ① Đợt 1) ==================


def test_cung_vat_tu_o_hai_buoc_phai_giu_TONG_ca_hai(db, svc, customer):
    """Lệnh chỉ chạy được khi đủ cho CẢ chuỗi — giữ một nửa mà mở khoá là mở cho lệnh sẽ đứng máy."""
    g = _giay(db)
    vt = VatTuInAn(ma="VT-MUC", ten="Mực", don_vi_gia="kg")
    db.add(vt)
    db.commit()
    _ton(db, ("vat_tu", vt.id), 7)                   # cần 5 + 5 = 10 ⇒ thiếu
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    b1 = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == a.id).first()
    b2 = LsxCongDoan(lsx_id=a.id, thu_tu=2, ten="Bước hai", loai_buoc="may", may_id=_may(db).id,
                     don_vi_vao="to", don_vi_ra="to", so_luong_vao=200, so_luong_ra=200)
    db.add(b2)
    db.flush()
    for b in (b1, b2):
        db.add(LsxCongDoanVatTu(lsx_cong_doan_id=b.id, vat_tu_id=vt.id, vat_tu_ma_snapshot=vt.ma,
                                vat_tu_ten_snapshot=vt.ten, don_vi_snapshot="kg", so_luong=5))
    db.commit()

    tt = svc.bat(lsx_id=a.id)
    assert tt["du"] is False, "7 kg < 10 kg cần cho hai bước"
    assert tt["dang_giu"][("vat_tu", vt.id)] == pytest.approx(7)


# ================== KHÔNG ĐÁNH GIÁ ĐƯỢC ==================


def test_dong_khong_quy_doi_duoc_thi_KHONG_BAO_GIO_du(db, svc, customer):
    """`nhu_cau=0` vì máy chưa tính nổi, KHÔNG phải vì không cần.

    Coi là 0 rồi mở khoá xếp lịch là mở cho một lệnh chưa ai biết cần bao nhiêu — đúng kiểu hỏng
    tệ nhất: bảng xanh, lịch xếp xong, tới ngày chạy mới biết không có giấy.
    """
    # Giấy KHÔNG khai công thức lượng ⇒ cạnh tờ→kg tắt ⇒ dòng `khong_ro`.
    g = GiayNguyen(ma="GY-MU", ten="Giấy mù", gsm=150, kho_dai=860, kho_rong=650, don_vi_gia="kg")
    db.add(g)
    db.commit()
    _ton(db, _giay_hang(g), 1_000)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)

    tt = svc.bat(lsx_id=a.id)
    assert tt["khong_ro"] is True
    assert tt["du"] is False, "chưa quy đổi được thì KHÔNG được tính là đủ"


# ================== BÀI GHÉP ==================


def test_bai_ghep_la_CHU_THE_giu_cho(db, svc, customer):
    """Lệnh đã ghép không giữ riêng — bài đại diện. Cùng luật chủ thể của bảng nhu cầu."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200)
    bg = BaiGhep(ma="GB-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    db.commit()

    assert svc.bat(bai_ghep_id=bg.id)["du"] is True
    assert db.get(BaiGhep, bg.id).giu_cho_bat is True
    # Lệnh thành viên KHÔNG có nhu cầu riêng ⇒ không giữ được gì.
    assert svc.trang_thai(lsx_id=a.id)["dang_giu"] == {}


# ================== KHO GỌI VÀO (2.3) ==================


def test_xuat_kho_KHONG_lan_vao_cho_lenh_khac_giu(db, svc, customer):
    """Cửa chặn của kho: phần lệnh khác đang giữ không ai lấy được."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 20)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈16,77 kg
    svc.bat(lsx_id=a.id)

    # Người khác đòi lĩnh 10 kg — tự do chỉ còn ~3,2.
    loi = svc.kiem_xuat(hang=_giay_hang(g), so_luong=10)
    assert loi and "đang được lệnh khác giữ chỗ" in loi

    # CHÍNH lệnh đang giữ thì lấy được — không thì giữ chỗ tự khoá chân người giữ.
    assert svc.kiem_xuat(hang=_giay_hang(g), so_luong=10, lsx_id=a.id) is None


def test_xuat_cho_lenh_thi_NHA_phan_giu_tuong_ung(db, svc, customer):
    """Giữ chỗ HOÁ THÀNH đã cấp. Không nhả là đếm hai lần ⇒ lệnh khác báo thiếu oan."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)
    truoc = sum(svc.trang_thai(lsx_id=a.id)["dang_giu"].values())

    svc.tieu_thu(hang=_giay_hang(g), so_luong=10, lsx_id=a.id)
    sau = sum(svc.trang_thai(lsx_id=a.id)["dang_giu"].values())
    assert sau == pytest.approx(truoc - 10, abs=0.02)


def test_tieu_thu_nha_phan_TRONG_KHO_truoc(db, svc, customer):
    """Hàng vừa xuất là hàng có thật ⇒ nhả đúng loại đó, giữ lại phần bám lô đang về."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 10)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=50, ngay_ve=HOM_NAY + timedelta(days=10))
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)

    svc.tieu_thu(hang=_giay_hang(g), so_luong=10, lsx_id=a.id)
    con = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert all(r.nguon == "dang_ve" for r in con), "phần kho phải nhả trước"


# ================== BA DÂY KHOÁ (2.4) ==================


def test_lenh_dang_giu_cho_thi_KHONG_ghep_bai_duoc(db, svc, customer):
    """Ghép bài làm ĐỔI số giấy cần — và đổi XUỐNG. Không nhả trước là ôm chỗ cho giấy thừa."""
    from app.repositories.audit_repo import AuditLogRepository
    from app.services.bai_ghep_service import BaiGhepConflict, BaiGhepService

    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)

    bg = BaiGhep(ma="GB-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1))
    db.commit()

    bg_svc = BaiGhepService(db, BaiGhepRepository(db), AuditLogRepository(db), None)
    with pytest.raises(BaiGhepConflict, match="đang giữ chỗ"):
        bg_svc.them_thanh_vien(bai_ghep_id=bg.id, lsx_ids=[a.id], actor=None)

    svc.tat(lsx_id=a.id)                       # ĐƯỜNG LÙI: nhả rồi ghép được
    bg_svc.them_thanh_vien(bai_ghep_id=bg.id, lsx_ids=[a.id], actor=None)
    assert {tv.lsx_id for tv in db.get(BaiGhep, bg.id).thanh_viens} == {a.id, b.id}


def test_bai_dang_giu_cho_thi_KHONG_rut_thanh_vien_hay_pha_bai(db, svc, customer):
    from app.repositories.audit_repo import AuditLogRepository
    from app.services.bai_ghep_service import BaiGhepConflict, BaiGhepService

    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200)
    bg = BaiGhep(ma="GB-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    db.commit()
    svc.bat(bai_ghep_id=bg.id)

    bg_svc = BaiGhepService(db, BaiGhepRepository(db), AuditLogRepository(db), None)
    tv_id = db.get(BaiGhep, bg.id).thanh_viens[0].id
    with pytest.raises(BaiGhepConflict, match="đang giữ chỗ"):
        bg_svc.bo_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv_id, actor=None)
    with pytest.raises(BaiGhepConflict, match="đang giữ chỗ"):
        bg_svc.xoa(bai_ghep_id=bg.id, actor=None)


# ================== CÁCH NHÌN THEO LỆNH ==================


def _buoc_dau_cua(db, lsx) -> LsxCongDoan:
    return (db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == lsx.id)
            .order_by(LsxCongDoan.thu_tu.asc()).first())


def _them_buoc_hai(db, lsx, vt, *, so_luong=5) -> None:
    """Khai CÙNG một vật tư ở cả hai công đoạn của lệnh — ca sinh ra lỗi "mua một nửa"."""
    b1 = _buoc_dau_cua(db, lsx)
    b2 = LsxCongDoan(lsx_id=lsx.id, thu_tu=2, ten="Bước hai", loai_buoc="may",
                     may_id=_may(db).id, don_vi_vao="to", don_vi_ra="to",
                     so_luong_vao=200, so_luong_ra=200)
    db.add(b2)
    db.flush()
    for b in (b1, b2):
        db.add(LsxCongDoanVatTu(lsx_cong_doan_id=b.id, vat_tu_id=vt.id,
                                vat_tu_ma_snapshot=vt.ma, vat_tu_ten_snapshot=vt.ten,
                                don_vi_snapshot="kg", so_luong=so_luong))
    db.commit()


def _the(svc, lsx_id) -> dict:
    ds = [r for r in svc.theo_chu_the()["items"] if r["lsx_id"] == lsx_id]
    assert ds, f"không thấy thẻ của lệnh {lsx_id}"
    return ds[0]


def test_the_lenh_lay_DUNG_so_cua_bang_can_doi(db, svc, customer):
    """Thẻ lệnh và bảng mặt hàng phải ra CÙNG con số — vì cùng một nguồn.

    Tự cộng lại nhu cầu bằng đường riêng là đẻ hai con số cho cùng một màn hình, và lúc lệch thì
    không ai biết tin bên nào.
    """
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)

    hang = [h for h in _the(svc, a.id)["hang"] if h["hang_loai"] == "giay"][0]
    dong = [d for n in svc.kh.can_doi()["items"] if n["hang_id"] == g.id
            for d in n["dong"] if d["lsx_id"] == a.id]
    assert dong, "bảng cân đối phải có dòng giấy của lệnh này"
    assert hang["can"] == pytest.approx(sum(d["con_phai_co"] for d in dong))


def test_the_lenh_GOP_hai_buoc_nhung_GIU_DU_HAI_KHOA_MUA(db, svc, customer):
    """Một món ở hai công đoạn: thẻ hiện MỘT dòng, nhưng `khoa_do` phải còn ĐỦ HAI.

    Gộp luôn cả khoá là tái diễn đúng lỗi "mua một nửa" đã sửa 17/08 — chỉ khác là lần này nó nằm
    ở nút mua trên thẻ lệnh thay vì ở bảng mặt hàng.
    """
    g = _giay(db)
    vt = VatTuInAn(ma="VT-MUC", ten="Mực", don_vi_gia="kg")
    db.add(vt)
    db.commit()
    _ton(db, _giay_hang(g), 100)                 # giấy đủ; mực KHÔNG có tồn ⇒ hai dòng đỏ
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _them_buoc_hai(db, a, vt)

    muc = [h for h in _the(svc, a.id)["hang"] if h["hang_id"] == vt.id][0]
    assert muc["so_buoc"] == 2
    assert muc["can"] == pytest.approx(10), "thẻ phải cộng cả hai bước"
    assert len({k["buoc_id"] for k in muc["khoa_do"]}) == 2, \
        f"phải còn 2 khoá riêng cho 2 bước, thực tế: {muc['khoa_do']}"


def test_the_lenh_lay_mau_NANG_NHAT_trong_cac_buoc(db, svc, customer):
    """Thẻ hiện được đúng một màu; lấy màu bước đầu là giấu mất thứ phải lo."""
    g = _giay(db)
    vt = VatTuInAn(ma="VT-MUC", ten="Mực", don_vi_gia="kg")
    db.add(vt)
    db.commit()
    _ton(db, _giay_hang(g), 1_000)
    _ton(db, ("vat_tu", vt.id), 5)               # đủ cho một bước, KHÔNG đủ cho cả hai
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _them_buoc_hai(db, a, vt)

    the = _the(svc, a.id)
    muc = [h for h in the["hang"] if h["hang_id"] == vt.id][0]
    assert muc["trang_thai"] == "do", "một bước đủ + một bước thiếu ⇒ thẻ phải nói THIẾU"
    assert the["so_thieu"] == 1


def test_q_KHONG_duoc_cat_mat_mon_dang_thieu_cua_lenh(db, svc, customer):
    """`q` lọc theo CHỦ THỂ, không truyền xuống bộ lọc mặt hàng của `can_doi()`.

    Truyền xuống thì gõ tên MỘT mặt hàng sẽ cắt mất mặt hàng kia khỏi thẻ, và một lệnh còn thiếu
    mực hiện ra như đã đủ.
    """
    g = _giay(db)
    vt = VatTuInAn(ma="VT-MUC", ten="Mực", don_vi_gia="kg")
    db.add(vt)
    db.commit()
    _ton(db, _giay_hang(g), 1_000)               # giấy đủ; mực không tồn ⇒ thiếu
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    db.add(LsxCongDoanVatTu(lsx_cong_doan_id=_buoc_dau_cua(db, a).id, vat_tu_id=vt.id,
                            vat_tu_ma_snapshot=vt.ma, vat_tu_ten_snapshot=vt.ten,
                            don_vi_snapshot="kg", so_luong=5))
    db.commit()

    row = [r for r in svc.theo_chu_the(q="GY-1")["items"] if r["lsx_id"] == a.id][0]
    assert row["so_mat_hang"] == 2, "lọc theo tên giấy KHÔNG được làm mất dòng mực của lệnh"
    assert row["so_thieu"] == 1, "mực vẫn phải báo thiếu"


def test_so_lenh_khac_thieu_de_hop_XAC_NHAN_noi_duoc_ai_dang_can(db, svc, customer):
    """Hộp xác nhận nhả chỗ phải nói *"nhả ra thì ai đỡ"* — nửa tích cực của quyết định.

    Hộp chỉ doạ ("không hoàn tác được") thì người ta không bao giờ nhả, kể cả lúc nên nhả.
    """
    g = _giay(db)
    _ton(db, _giay_hang(g), 20)                  # đủ cho MỘT lệnh (16,77 kg), không đủ cho hai
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)

    giay_a = [h for h in _the(svc, a.id)["hang"] if h["hang_id"] == g.id][0]
    assert giay_a["so_lenh_khac_thieu"] == 1, "A đang giữ, B đang thiếu ⇒ nhả ra thì B đỡ"

    giay_b = [h for h in _the(svc, b.id)["hang"] if h["hang_id"] == g.id][0]
    assert giay_b["so_lenh_khac_thieu"] == 0, "không tính CHÍNH NÓ vào số lệnh khác"


def test_so_lenh_khac_thieu_dem_TRUOC_bo_loc(db, svc, customer):
    """Đếm sau bộ lọc thì màn đang lọc sẽ báo "0 lệnh khác đang thiếu" trong khi thật ra có —
    và người dùng quyết nhả (hay không) dựa trên con số do chính bộ lọc của họ tạo ra."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 20)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)

    # Lọc còn ĐÚNG thẻ A — B bị cắt khỏi danh sách trả về.
    kq = svc.theo_chu_the(q="LSX-A")
    assert [r["ma"] for r in kq["items"]] == ["LSX-A"]
    giay = [h for h in kq["items"][0]["hang"] if h["hang_id"] == g.id][0]
    assert giay["so_lenh_khac_thieu"] == 1, "vẫn phải thấy B, dù B không có trong danh sách"


# ================== GIỮ LÂU MÀ CHƯA CHẠY ==================


def _lui_ngay_giu(db, *, so_ngay: int) -> None:
    """Kéo lùi `created_at` mọi dòng giữ chỗ — giả lập chỗ giữ đã nằm đó mấy hôm."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    from app.models.vat_tu_giu_cho import VatTuGiuCho

    for r in db.query(VatTuGiuCho).all():
        r.created_at = _dt.now(_tz.utc) - _td(days=so_ngay)
    db.commit()


def test_giu_qua_NGUONG_ma_chua_xep_lich_thi_noi_len(db, svc, customer):
    """Thay cho tự-hết-hạn: máy BÀY ra, người nhìn rồi tự quyết nhả (luật ③)."""
    from app.services.giu_cho_service import NGUONG_GIU_LAU_NGAY

    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)
    assert _the(svc, a.id)["giu_lau_chua_chay"] is False, "vừa bật xong chưa phải giữ lâu"

    _lui_ngay_giu(db, so_ngay=NGUONG_GIU_LAU_NGAY + 1)
    kq = svc.theo_chu_the()
    row = [r for r in kq["items"] if r["lsx_id"] == a.id][0]
    assert row["giu_lau_chua_chay"] is True
    assert row["so_ngay_giu"] >= NGUONG_GIU_LAU_NGAY
    assert kq["so_giu_lau"] == 1


def test_nhat_them_khi_hang_ve_KHONG_reset_dong_ho_giu_lau(db, svc, customer):
    """`giu_tu` lấy dòng CŨ NHẤT. Lấy mới nhất thì mỗi lần bù hàng là đồng hồ về 0, và đúng chỗ
    giữ lâu nhất thì không bao giờ nổi lên."""
    from app.services.giu_cho_service import NGUONG_GIU_LAU_NGAY

    g = _giay(db)
    _ton(db, _giay_hang(g), 5)                   # chỉ giữ được một phần
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)
    _lui_ngay_giu(db, so_ngay=NGUONG_GIU_LAU_NGAY + 1)

    _ton(db, _giay_hang(g), 50)                  # hàng về ⇒ nhặt thêm dòng MỚI hôm nay
    svc.nhat_them()

    assert _the(svc, a.id)["giu_lau_chua_chay"] is True, \
        "bù hàng không được xoá dấu vết đã giữ từ tuần trước"


def test_da_dua_vao_ke_hoach_thi_KHONG_con_la_giu_lau(db, svc, customer):
    """Giữ chỗ sinh ra để mở khoá xếp lịch — đã qua cửa đó thì chỗ giữ đang dùng đúng việc."""
    from app.models.xep_lich import NGUON_LSX, TT_CHO_XEP, XepLichCongDoan
    from app.services.giu_cho_service import NGUONG_GIU_LAU_NGAY

    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)
    _lui_ngay_giu(db, so_ngay=NGUONG_GIU_LAU_NGAY + 5)
    db.add(XepLichCongDoan(nguon=NGUON_LSX, lsx_id=a.id,
                           lsx_cong_doan_id=_buoc_dau_cua(db, a).id, trang_thai=TT_CHO_XEP))
    db.commit()

    row = _the(svc, a.id)
    assert row["da_xep_lich"] is True
    assert row["giu_lau_chua_chay"] is False


def test_lenh_ROI_KHOI_pham_vi_van_hien_de_con_duong_NHA(db, svc, customer):
    """Lệnh bị kéo về nháp: rơi khỏi bảng cân đối nhưng chỗ giữ VẪN trừ vào tồn tự do.

    Chỉ duyệt theo bảng cân đối thì đúng những chỗ giữ tệ nhất lại là chỗ không màn nào hiện —
    giấy nằm chết mà chẳng ai có nút để nhả.
    """
    from app.models.lsx import TT_NHAP

    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)
    tu_do_truoc = svc.ton_tu_do([_giay_hang(g)])[_giay_hang(g)]

    db.get(Lsx, a.id).trang_thai = TT_NHAP
    db.commit()

    row = _the(svc, a.id)
    assert row["ngoai_pham_vi"] is True
    assert row["ma"] == "LSX-A", "vẫn phải đọc được mã để biết đi nhả cái gì"
    giay = [h for h in row["hang"] if h["hang_id"] == g.id]
    assert giay and giay[0]["dang_giu"] > 0, \
        "phải kê cả ĐANG GIỮ GÌ — thẻ trống thì không ai có căn cứ quyết nhả"
    assert giay[0]["hang_ten"], "tên mặt hàng phải tra được dù lệnh đã rơi khỏi bảng"
    assert svc.ton_tu_do([_giay_hang(g)])[_giay_hang(g)] == pytest.approx(tu_do_truoc), \
        "rơi khỏi bảng KHÔNG tự nhả — đó chính là lý do phải bày ra"


# ================== CỬA API ==================


def test_router_theo_lenh_va_bat_giu_cho_chay_that(client):
    """Đi qua CỬA THẬT: định tuyến · quyền · Pydantic serialize.

    Không bơm service giả ở đây (khác test router của `/de-nghi-mua`, chỗ đó chỉ kiểm đoạn nối
    chuỗi): cái dễ vỡ ở hai cửa này nằm đúng ở lớp schema — `giu_tu` là datetime, `khoa_do` là
    danh sách model có `pattern` trên `hang_loai`, và thẻ trả về sau khi bật phải là thẻ ĐÃ CẬP
    NHẬT chứ không phải bản chụp trước lúc bấm. Test service không chạm được lớp đó.
    """
    s = SessionLocal()
    try:
        cus = Customer(code="KH-API", name="Khách API")
        s.add(cus)
        s.commit()
        g = _giay(s, ma="GY-API")
        _ton(s, _giay_hang(g), 100)
        l = _lenh(s, cus, ma="LSX-API", giay_id=g.id, so_to_nguyen=200)
        lsx_id, giay_id = l.id, g.id
    finally:
        s.close()

    h = {"Authorization": f"Bearer {_admin_token()}"}
    r = client.get("/api/ke-hoach-vat-tu/theo-lenh", headers=h)
    assert r.status_code == 200, r.text
    the = [x for x in r.json()["items"] if x["lsx_id"] == lsx_id][0]
    assert the["bat"] is False and the["du"] is False
    assert any(x["hang_id"] == giay_id for x in the["hang"])

    r = client.post("/api/ke-hoach-vat-tu/giu-cho/bat",
                    json={"lsx_id": lsx_id}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["bat"] is True, "thẻ trả về phải là thẻ ĐÃ cập nhật, không phải bản chụp cũ"
    assert r.json()["du"] is True, "100 kg tồn > 16,77 kg cần ⇒ giữ đủ"

    r = client.post("/api/ke-hoach-vat-tu/giu-cho/tat",
                    json={"lsx_id": lsx_id}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["bat"] is False


def test_router_giu_cho_CHAN_thieu_hoac_thua_chu_the(client):
    """Cả hai cùng trống ⇒ dòng mồ côi trừ tồn của mọi người mà không tra ngược ra ai giữ.
    Cả hai cùng có ⇒ không biết giữ cho ai. Chặn ngay ở biên API, cùng luật với CheckConstraint."""
    h = {"Authorization": f"Bearer {_admin_token()}"}
    assert client.post("/api/ke-hoach-vat-tu/giu-cho/bat", json={}, headers=h).status_code == 400
    assert client.post("/api/ke-hoach-vat-tu/giu-cho/bat",
                       json={"lsx_id": 1, "bai_ghep_id": 1}, headers=h).status_code == 400


def _admin_token() -> str:
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token

    s = SessionLocal()
    try:
        return create_access_token(str(UserRepository(s).get_by_username("admin").id))
    finally:
        s.close()


def test_tat_thi_the_het_giu_va_ton_tu_do_tra_lai(db, svc, customer):
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)
    svc.tat(lsx_id=a.id)

    row = svc.mot_dong(lsx_id=a.id)
    assert row["bat"] is False
    assert row["du"] is False
    assert row["giu_lau_chua_chay"] is False
    assert all(h["dang_giu"] == 0 for h in row["hang"])


# ================== VẾT MUA TRÊN THẺ LỆNH ==================


def test_the_lenh_goi_ten_phieu_dang_chay_cua_tung_mon(db, svc, customer):
    """Màn "Theo lệnh sản xuất" là chỗ người dùng bấm Mua, nên nó phải là chỗ nói được "đã có ai lo".

    Nhãn đi từ engine cân đối xuống tận thẻ lệnh (Pydantic nuốt im lặng field không khai ⇒ phải
    kiểm ở ĐÚNG cửa mà màn ăn), và tuyệt đối không đụng vào phần giữ chỗ/thiếu.
    """
    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)

    truoc = [h for h in _the(svc, a.id)["hang"] if h["hang_id"] == g.id][0]
    assert truoc["phieu_mua"] == []

    yc = _ycmh(db, hang=_giay_hang(g), so_luong=20)

    sau = [h for h in _the(svc, a.id)["hang"] if h["hang_id"] == g.id][0]
    assert sau["phieu_mua"] == [
        {"ma": yc.code, "loai": "ycmh", "trang_thai": DPR_OPEN, "ngay_ve": None},
    ]
    assert sau["thieu"] == pytest.approx(truoc["thieu"])
    assert sau["dang_giu"] == pytest.approx(truoc["dang_giu"])


# ================== MIGRATION 0245 ==================


def test_migration_them_cot_purchase_request_line_id(db):
    """Cột mới phải tồn tại, nullable, và chạy lại migration không vỡ (idempotent)."""
    from sqlalchemy import inspect

    from app.db_migrations import run_migrations

    insp = inspect(db.get_bind())
    cols = {c["name"] for c in insp.get_columns("vat_tu_giu_cho")}
    assert "purchase_request_line_id" in cols

    # Chạy lại lần hai — no-op, không raise.
    run_migrations(db)


def test_migration_backfill_dung_lai_nhat_them_cho_chu_the_dang_bat(db, kh, customer):
    """Chủ thể đã BẬT giữ chỗ từ trước (cờ `giu_cho_bat=true`), dòng `dang_ve` của nó vừa bị
    migration xoá sạch — hàm backfill `_dung_lai_giu_cho_dang_ve` phải tự gọi lại `nhat_them()`
    cho chủ thể đó, không để nó "trắng tay" tới lần Nhập kho/Bật-Tắt kế tiếp."""
    from app.db_migrations import _dung_lai_giu_cho_dang_ve
    from app.services.giu_cho_service import GiuChoService

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)

    # Mô phỏng "đã bật từ trước migration": bật cờ THẲNG qua ORM, KHÔNG gọi svc.bat() (gọi bat()
    # sẽ tự nhat_them() ngay, làm mất ý nghĩa của test — ta cần trạng thái "cờ bật nhưng CHƯA có
    # dòng giữ", đúng như sau khi migration xoá sạch dang_ve).
    a.giu_cho_bat = True
    db.commit()

    svc = GiuChoService(db, kh)
    assert not svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None), "chưa gọi nhat_them nên phải trống"

    _dung_lai_giu_cho_dang_ve(db)

    rows = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert rows, "backfill phải tự dựng lại giữ chỗ cho chủ thể đang bật"


# ================== ĐỐI SOÁT KHI PMH ĐỔI ==================


def _dot_giao(db, phieu, line, *, so_luong) -> None:
    """Ghi MỘT đợt giao cho dòng phiếu — đủ để `da_giao_theo_dong()` cộng vào 'đã giao', khớp
    hành vi `PurchaseService.ghi_dot_giao` mà không phải dựng toàn bộ service."""
    from app.models.purchase import PurchaseDelivery, PurchaseDeliveryLine

    dot = PurchaseDelivery(purchase_request_id=phieu.id, seq_no=1, delivery_date=HOM_NAY)
    db.add(dot)
    db.flush()
    db.add(PurchaseDeliveryLine(delivery_id=dot.id, purchase_request_line_id=line.id,
                                quantity=so_luong))
    db.commit()


def test_doi_soat_nha_moi_nhat_truoc_khi_con_ve_co_lai(db, svc, kh, customer):
    """Bảo vệ cam kết CŨ: khi phần hứa co lại, dòng giữ MỚI TẠO bị nhả trước, dòng CŨ giữ nguyên."""
    from app.models.purchase import PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1000)  # cần nhiều, ăn hết lô
    _phieu_mua(db, hang=_giay_hang(g), so_luong=200, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()

    svc.bat(lsx_id=a.id)
    truoc = sum(float(r.so_luong) for r in svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None))
    assert truoc > 0, "phải giữ được từ lô đang về"

    # NCC chỉ giao 50/200 — con_ve giảm còn 150.
    _dot_giao(db, phieu, line, so_luong=50)

    svc.doi_soat_dang_ve(line.id)

    sau = sum(float(r.so_luong) for r in svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None))
    assert sau == pytest.approx(min(truoc, 150), abs=0.01), (
        f"phải nhả bớt xuống còn tối đa 150 (con_ve mới), thực tế còn {sau}"
    )


def test_doi_soat_nha_sach_khi_dong_khong_con_trong_hang_dang_ve(db, svc, kh, customer):
    """Phiếu rời khỏi trạng thái 'đang về' (đóng/huỷ) ⇒ `_hang_dang_ve()` không còn dòng nào của
    nó ⇒ đối soát phải nhả SẠCH phần đã giữ theo dòng đó."""
    from app.models.purchase import PR_CANCELLED, PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()
    svc.bat(lsx_id=a.id)
    assert svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None), "phải giữ được trước đã"

    phieu.status = PR_CANCELLED   # mô phỏng PurchaseService.cancel() đã đổi trạng thái
    db.commit()

    svc.doi_soat_dang_ve(line.id)

    con = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert not any(r.purchase_request_line_id == line.id for r in con)
