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


def test_migration_them_cot_purchase_request_line_id_tao_index(db):
    """Migration 0245 phải tự tạo INDEX cho cột mới — DB thật (dev/prod) không chạy lại
    create_all() nên nếu migration không tự tạo, index sẽ KHÔNG BAO GIỜ xuất hiện, và mọi
    doi_soat_dang_ve()/doi_soat_dang_ve_don() filter trên cột này full-scan dưới khoá FOR UPDATE.

    KHÔNG dùng `ALTER TABLE ... DROP COLUMN` trên bảng đã create_all(): SQLite từ chối thẳng
    ("unknown column ... in foreign key definition") vì cột này có ràng buộc FK cấp-bảng
    (`FOREIGN KEY(purchase_request_line_id) REFERENCES purchase_request_lines(id)`) — hạn chế cấu
    trúc của SQLite (không liên quan `PRAGMA foreign_keys`, đã xác minh riêng). Thay vào đó DROP +
    CREATE lại đúng bảng `vat_tu_giu_cho` KHÔNG có cột/index đó, giữ nguyên mọi bảng khác (lsx,
    bai_ghep, purchase_request_lines...) nguyên vẹn từ create_all() của fixture `db` — không bảng
    nào khác có FK trỏ VÀO `vat_tu_giu_cho` nên an toàn drop/recreate riêng bảng này, và
    `_dung_lai_giu_cho_dang_ve()` bên trong migration (backfill gọi `GiuChoService.nhat_them()`)
    vẫn chạy được bình thường vì mọi bảng nó cần đọc vẫn còn nguyên."""
    from sqlalchemy import inspect, text

    from app.db_migrations import _migrate_giu_cho_purchase_request_line_id

    db.execute(text("DROP TABLE vat_tu_giu_cho"))
    db.execute(text(
        "CREATE TABLE vat_tu_giu_cho ("
        "id INTEGER PRIMARY KEY, hang_loai VARCHAR(8) NOT NULL, hang_id INTEGER NOT NULL, "
        "lsx_id INTEGER, bai_ghep_id INTEGER, so_luong NUMERIC(14,2) NOT NULL, "
        "nguon VARCHAR(10) NOT NULL, ngay_ve DATE, "
        "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
    ))
    db.commit()

    insp = inspect(db.get_bind())
    cols_truoc = {c["name"] for c in insp.get_columns("vat_tu_giu_cho")}
    assert "purchase_request_line_id" not in cols_truoc

    _migrate_giu_cho_purchase_request_line_id(db)

    insp = inspect(db.get_bind())
    cols = {c["name"] for c in insp.get_columns("vat_tu_giu_cho")}
    assert "purchase_request_line_id" in cols
    idx_cols = [tuple(i["column_names"]) for i in insp.get_indexes("vat_tu_giu_cho")]
    assert ("purchase_request_line_id",) in idx_cols, (
        f"thiếu index trên purchase_request_line_id — indexes hiện có: {idx_cols}"
    )


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


def test_doi_soat_dang_ve_don_ban_sse_dung_mot_lan_du_nhieu_mat_hang(db, svc, kh, customer, monkeypatch):
    """Một PMH có NHIỀU dòng, mỗi dòng đang giữ hứa `dang_ve` cho MỘT mặt hàng khác nhau —
    `doi_soat_dang_ve_don()` lặp gọi `doi_soat_dang_ve()` cho TỪNG dòng, nhưng phải bắn SSE
    ĐÚNG MỘT LẦN cho cả đợt, không phải N lần cho N mặt hàng (một lần Save đợt giao/huỷ/đóng đơn
    không được nổ N toast đúp trên AppShell)."""
    from app.services import giu_cho_service

    g1 = _giay(db, ma="GY-1")
    g2 = _giay(db, ma="GY-2")
    a = _lenh(db, customer, ma="LSX-A", giay_id=g1.id, so_to_nguyen=200)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g2.id, so_to_nguyen=200)

    p = PurchaseRequest(code="PMH-MULTI", status=PR_PURCHASED, expected_receipt_date=MAI)
    db.add(p)
    db.flush()
    ln1 = PurchaseRequestLine(purchase_request_id=p.id, item_name="Giấy 1", hang_loai="giay",
                               hang_id=g1.id, unit="kg", quantity=100, expected_unit_price=1)
    ln2 = PurchaseRequestLine(purchase_request_id=p.id, item_name="Giấy 2", hang_loai="giay",
                               hang_id=g2.id, unit="kg", quantity=100, expected_unit_price=1)
    db.add_all([ln1, ln2])
    db.commit()

    svc.bat(lsx_id=a.id)
    svc.bat(lsx_id=b.id)
    assert any(r.purchase_request_line_id == ln1.id
               for r in svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)), "phải giữ hứa mặt hàng 1 trước đã"
    assert any(r.purchase_request_line_id == ln2.id
               for r in svc.repo.cua_chu_the(lsx_id=b.id, bai_ghep_id=None)), "phải giữ hứa mặt hàng 2 trước đã"

    calls: list[dict] = []
    monkeypatch.setattr(giu_cho_service.hub, "broadcast", lambda e: calls.append(e))

    svc.doi_soat_dang_ve_don(p.id)

    assert len(calls) == 1, f"phải bắn đúng 1 lần cho cả PMH (2 mặt hàng), thực tế {len(calls)} lần: {calls}"


# ================== HOOK PurchaseService ⇄ GIỮ CHỖ (30/08/2026, Task 4) ==================


def _thu_mua(db, kh) -> "PurchaseService":
    """Dựng `PurchaseService` NGOÀI FastAPI DI, soi đúng cách `deps.get_purchase_service` ráp —
    KHÔNG đoán tên module: `AuthorizationService` nằm ở `rbac_service` (không phải
    `authorization_service` — file đó không tồn tại), `DepartmentRepository`/`RoleRepository`
    nằm chung `rbac_repo`, và `DepartmentPurchaseRequestRepository`/`PurchaseStatusHistoryRepository`
    nằm chung `purchase_repo` với `SupplierRepository`/`PurchaseRequestRepository` đã import ở
    đầu file này (không có file `department_purchase_repo.py`/`department_repo.py` riêng)."""
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.purchase_repo import (
        DepartmentPurchaseRequestRepository,
        PurchaseStatusHistoryRepository,
    )
    from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
    from app.repositories.user_repo import UserRepository
    from app.services.purchase_service import PurchaseService
    from app.services.rbac_service import AuthorizationService

    return PurchaseService(
        suppliers=SupplierRepository(db),
        department_requests=DepartmentPurchaseRequestRepository(db),
        requests=PurchaseRequestRepository(db),
        users=UserRepository(db),
        departments=DepartmentRepository(db),
        audit=AuditLogRepository(db),
        authz=AuthorizationService(RoleRepository(db)),
        lich_su=PurchaseStatusHistoryRepository(db),
        giu_cho=GiuChoService(db, kh),
    )


def test_huy_pmh_nha_sach_giu_cho_dang_ve(db, svc, kh, customer):
    """Huỷ PMH → PMH rời khỏi trạng thái 'đang về' → `GiuChoService.doi_soat_dang_ve_don` phải tự
    chạy và nhả sạch phần giữ hứa bám phiếu đó, KHÔNG cần ai gọi tay `nhat_them`/`doi_soat_dang_ve`.

    Actor dùng user `admin` đã seed sẵn (KHÔNG dùng actor giả `type("A", (), {"id": 1})()` như bản
    nháp đầu của test này): `_phieu_mua()` dựng PMH thẳng ở trạng thái `PR_PURCHASED`, nên
    `PurchaseService.cancel()` đòi actor có quyền `ke_toan:approve` — nhánh "tự huỷ phiếu NHÁP do
    chính mình lập" không áp được vì phiếu không ở `PR_DRAFT`. Một actor giả chỉ có `.id` còn vỡ
    sớm hơn nữa: `AuthorizationService.can()` đọc `user.role_id`, actor giả không có thuộc tính đó
    nên ném `AttributeError` trước khi kịp bàn tới việc có quyền hay không."""
    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    svc.bat(lsx_id=a.id)
    assert svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None), "phải giữ được trước đã"

    thu_mua = _thu_mua(db, kh)
    from app.models.user import User

    admin = db.query(User).filter(User.username == "admin").first()
    thu_mua.cancel(phieu.id, reason="Không mua nữa", actor=admin)

    con = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert not any(float(r.so_luong) > 0 for r in con
                   if getattr(r, "purchase_request_line_id", None)), (
        "huỷ PMH phải nhả hết phần giữ hứa bám phiếu đó"
    )


def test_mark_received_nha_sach_giu_cho_dang_ve(db, svc, kh, customer):
    """`mark_received` — ĐƯỜNG CŨ cho PMH không theo dõi đợt giao — đánh dấu "Đã nhận hàng" thì
    PMH rời khỏi trạng thái 'đang về' (`_hang_dang_ve()` chỉ đếm APPROVED/PURCHASED/
    PARTIALLY_RECEIVED). Trước bản vá này, `mark_received` không gọi `_doi_soat_giu_cho` như 5 chỗ
    khác đã làm (`_sau_khi_doi_dot`/`dong_don`/`cancel`), nên dòng giữ hứa `dang_ve` bám dòng phiếu
    này bị bỏ quên vĩnh viễn — hàng vừa về bị giữ HAI LẦN (một lần ma ở đây, một lần thật khi nhập
    kho), `ton_tu_do` hụt mãi bằng đúng số vừa nhận."""
    from app.models.purchase import PurchaseRequestLine
    from app.models.user import User

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()
    assert not phieu.deliveries, "test này phải đi đúng đường cũ — PMH không có đợt giao"

    svc.bat(lsx_id=a.id)
    assert any(r.purchase_request_line_id == line.id
               for r in svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)), (
        "phải giữ được hứa từ PMH trước đã"
    )

    thu_mua = _thu_mua(db, kh)
    admin = db.query(User).filter(User.username == "admin").first()
    thu_mua.mark_received(phieu.id, actor=admin)

    con = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert not any(r.purchase_request_line_id == line.id for r in con), (
        "đánh dấu 'Đã nhận hàng' phải tự đối soát nhả sạch phần giữ hứa bám dòng phiếu này"
    )


# ================== NHẬP KHO CHUYỂN HỨA → THẬT ==================


def test_chuyen_dang_ve_sang_kho_go_khoa_ngay(db, svc, kh, customer):
    """Hàng đang về (hứa, khoá lịch tới `ngay_ve`) nhập kho xong phải chuyển thành `nguon=kho`
    (không ngày nào khoá nữa) — không thì lệnh vẫn bị chặn lịch dù hàng đã nằm trong kho."""
    from app.models.vat_tu_giu_cho import NGUON_DANG_VE, NGUON_KHO

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    svc.bat(lsx_id=a.id)
    tt_truoc = svc.trang_thai(lsx_id=a.id)
    assert tt_truoc["xep_som_nhat"] is not None, "đang giữ hứa nên phải có ngày khoá lịch"

    svc.chuyen_dang_ve_sang_kho(_giay_hang(g), 100)

    rows = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert all(r.nguon == NGUON_KHO for r in rows), "phải chuyển hết sang kho"
    assert not any(r.nguon == NGUON_DANG_VE for r in rows)
    tt_sau = svc.trang_thai(lsx_id=a.id)
    assert tt_sau["xep_som_nhat"] is None, "hàng đã có thật thì không còn ngày nào khoá lịch nữa"


# ================== TÁCH NGUỒN TRONG trang_thai() ==================


def test_trang_thai_tach_da_giu_kho_va_dang_ve(db, svc, kh, customer):
    """`trang_thai()` phải tách được giữ THẬT (kho) và giữ HỨA (đang về), VÀ trả ra ĐÚNG dòng PMH
    nào đang góp cho phần hứa đó — không thì màn không biết phần nào đã chắc, phần nào còn treo
    theo ngày về, và không biết đang bám đơn nào để hối NCC."""
    from app.models.purchase import PurchaseRequestLine

    g = _giay(db)
    _ton(db, _giay_hang(g), 5)   # đủ 5 kg thật, còn thiếu phải bám hàng đang về
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()

    tt = svc.bat(lsx_id=a.id)

    hang = _giay_hang(g)
    assert tt["da_giu_kho"].get(hang, 0) == pytest.approx(5, abs=0.01)
    assert tt["da_giu_dang_ve"].get(hang, 0) == pytest.approx(16.77 - 5, abs=0.05)
    # Tổng hai nguồn phải khớp `dang_giu` cũ — không phá số cũ, chỉ tách thêm.
    assert tt["da_giu_kho"][hang] + tt["da_giu_dang_ve"][hang] == pytest.approx(
        tt["dang_giu"][hang], abs=0.01
    )
    nguon = tt["nguon_dang_ve"].get(hang, [])
    assert nguon and all(n["purchase_request_line_id"] == line.id for n in nguon)
    assert sum(n["so_luong"] for n in nguon) == pytest.approx(tt["da_giu_dang_ve"][hang], abs=0.01)


# ================== TRẠNG THÁI GIỮ 6 MỨC ==================


def test_giu_theo_chu_the_hang_co_the_giu_roi_thanh_da_giu(db, svc, kh, customer):
    """Chưa bật giữ chỗ nhưng tồn đủ ⇒ `co_the_giu` (chưa giữ, biết là giữ được). Bật xong ⇒
    `da_giu`. Không tồn/không đủ để giữ ⇒ vẫn `thieu`/`ve_muon`/`khong_ro` như can_doi() gốc."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    hang = _giay_hang(g)

    bang = kh.can_doi()
    gom = svc._gom_theo_chu_the(bang)
    svc.giu_theo_chu_the_hang(bang, gom)
    h = gom[(a.id, None)]["hang"][hang]
    assert h["trang_thai_giu"] == "co_the_giu", h
    assert h["co_the_giu_kho"] == pytest.approx(16.77, abs=0.05)
    assert h["da_giu_kho"] == 0 and h["da_giu_dang_ve"] == 0

    svc.bat(lsx_id=a.id)
    bang2 = kh.can_doi()
    gom2 = svc._gom_theo_chu_the(bang2)
    svc.giu_theo_chu_the_hang(bang2, gom2)
    h2 = gom2[(a.id, None)]["hang"][hang]
    assert h2["trang_thai_giu"] == "da_giu", h2
    assert h2["da_giu_kho"] == pytest.approx(16.77, abs=0.05)
    assert h2["co_the_giu_kho"] == 0


def test_giu_theo_chu_the_hang_lo_ma_pmh_dang_bam(db, svc, kh, customer):
    """Phần giữ HỨA phải lộ ra ĐÚNG mã PMH đang góp cho nó (spec §4: 'để FE hiện được đang bám đơn
    nào') — không chỉ số lượng trần."""
    from app.models.purchase import PurchaseRequest, PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()
    hang = _giay_hang(g)

    svc.bat(lsx_id=a.id)
    bang = kh.can_doi()
    gom = svc._gom_theo_chu_the(bang)
    svc.giu_theo_chu_the_hang(bang, gom)

    nguon = gom[(a.id, None)]["hang"][hang]["nguon_dang_ve"]
    assert nguon, "phải liệt kê nguồn PMH đang bám"
    assert nguon[0]["purchase_request_line_id"] == line.id
    assert nguon[0]["ma_pmh"] == phieu.code


# ================== GẮN GIỮ CHỖ VÀO BẢNG /can-doi ==================


def test_gan_giu_cho_vao_bang_dan_dung_dong(db, svc, kh, customer):
    """Mỗi dòng của bảng /can-doi phải nhận đúng con số giữ-chỗ của (chủ thể, mặt hàng) nó thuộc
    về — dòng nào không thuộc chủ thể nào (mồ côi cả hai) thì bỏ qua, không lỗi."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)

    bang = kh.can_doi()
    svc.gan_giu_cho_vao_bang(bang)

    dong = [d for nhom in bang["items"] if nhom["loai_nhom"] == "vat_tu"
            for d in nhom["dong"] if d.get("lsx_id") == a.id]
    assert dong, "phải có ít nhất một dòng của lệnh A"
    assert dong[0]["trang_thai_giu"] == "da_giu"
    assert dong[0]["da_giu_kho"] == pytest.approx(16.77, abs=0.05)

    from app.schemas.ke_hoach_vat_tu import CanDoiOut
    CanDoiOut(**bang)  # phải KHÔNG raise — xác nhận field mới không làm vỡ response_model của router thật


# ================== CHẶN SỬA KHI ĐANG GIỮ CHỖ (LSX) ==================


def _lsx_svc(db) -> "LsxService":
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.document_sequence_repo import DocumentSequenceRepository
    from app.repositories.lsx_repo import LsxRepository
    from app.services.lsx_service import LsxService
    from app.services.sequence_service import SequenceService

    return LsxService(
        db, LsxRepository(db), AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


def test_sua_so_luong_dat_khi_dang_giu_cho_bi_chan(db, svc, customer):
    """Đang giữ chỗ mà sửa SL đặt là đổi luôn số vật tư cần ⇒ phải chặn, giống cách bài ghép đã
    chặn thêm/rút thành viên khi đang giữ (`BaiGhepService._chan_dang_giu_cho`)."""
    from app.services.lsx_service import LsxConflict

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _ton(db, _giay_hang(g), 100)
    svc.bat(lsx_id=a.id)

    lsx_svc = _lsx_svc(db)
    payload = type("P", (), {"model_dump": lambda self, exclude_unset=True: {"so_luong_dat": 2000}})()
    admin = db.query(__import__("app.models.user", fromlist=["User"]).User).first()
    with pytest.raises(LsxConflict, match="giữ chỗ"):
        lsx_svc.update(lsx_id=a.id, payload=payload, actor=admin)


def test_xoa_lsx_khi_dang_giu_cho_bi_chan(db, svc, customer):
    from app.services.lsx_service import LsxConflict

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _ton(db, _giay_hang(g), 100)
    svc.bat(lsx_id=a.id)

    lsx_svc = _lsx_svc(db)
    admin = db.query(__import__("app.models.user", fromlist=["User"]).User).first()
    with pytest.raises(LsxConflict, match="giữ chỗ"):
        lsx_svc.xoa(lsx_id=a.id, actor=admin)


def test_sua_routing_khi_dang_giu_cho_bi_chan(db, svc, customer):
    """`replace_routing` phải chặn NGANG NHAU cho cả lưu thật (commit=True) và xem trước
    (`xem_truoc_routing` gọi commit=False) — số trên màn xem trước đã dùng để người dùng quyết
    định có nhả chỗ hay không, cho preview chạy qua thì màn nói dối, bấm Lưu thật mới báo lỗi."""
    from app.services.lsx_service import LsxConflict

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _ton(db, _giay_hang(g), 100)
    svc.bat(lsx_id=a.id)

    lsx_svc = _lsx_svc(db)
    admin = db.query(__import__("app.models.user", fromlist=["User"]).User).first()
    with pytest.raises(LsxConflict, match="giữ chỗ"):
        lsx_svc.replace_routing(lsx_id=a.id, rows_in=[], actor=admin)
    with pytest.raises(LsxConflict, match="giữ chỗ"):
        lsx_svc.replace_routing(lsx_id=a.id, rows_in=[], actor=admin, commit=False)


# ================== XUẤT KHO QUY LSX ĐÃ GHÉP VỀ BÀI ==================


def _dung_svcv(db, kh):
    from app.repositories.stock_voucher_repo import StockVoucherRepository
    from app.services.giu_cho_service import GiuChoService
    from app.services.stock_voucher_service import StockVoucherService

    return StockVoucherService(
        vouchers=StockVoucherRepository(db), requests=None, lots=None, sequence=None,
        request_service=None, hang=kh.hang, giu_cho=GiuChoService(db, kh),
    )


def _dung_phieu_xuat(db, hang, *, lsx_id, bai_ghep_id, kho_id=None):
    """Dựng thẳng 1 StockRequest (1 dòng) + 1 StockVoucher XUẤT khớp dòng đó — trả `(voucher,
    {request_line_id: request_line})` để gọi thẳng `_gom_theo_hang_va_chu_the`."""
    from app.models.stock_request import REQ_APPROVED, REQ_XUAT, StockRequest, StockRequestLine
    from app.models.stock_voucher import VOUCHER_DRAFT, VOUCHER_XUAT, StockVoucher, StockVoucherLine

    if kho_id is None:
        kho = db.query(KhoHang).first()
        if kho is None:
            kho = KhoHang(ma="K1", ten="Kho test")
            db.add(kho)
            db.flush()
        kho_id = kho.id

    n = db.query(StockRequest).count() + 1
    req = StockRequest(ma=f"DNX-TEST-{n}", loai=REQ_XUAT, nguoi_tao_id=1,
                       kho_id=kho_id, trang_thai=REQ_APPROVED)
    db.add(req)
    db.flush()
    rl = StockRequestLine(request_id=req.id, hang_loai=hang[0], hang_id=hang[1], dvt="kg",
                          sl_de_nghi=10, sl_duyet=10, sl_da_ung=0,
                          lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
    db.add(rl)
    db.commit()

    v = StockVoucher(ma=f"PXK-TEST-{n}", loai=VOUCHER_XUAT, request_id=req.id, kho_id=req.kho_id,
                     ngay=HOM_NAY, nguoi_lap_id=1, trang_thai=VOUCHER_DRAFT)
    db.add(v)
    db.flush()
    db.add(StockVoucherLine(voucher_id=v.id, request_line_id=rl.id, hang_loai=hang[0],
                            hang_id=hang[1], so_luong=10, sl_goc=10, lot_id=None))
    db.commit()
    return v, {rl.id: rl}


def test_gom_theo_hang_va_chu_the_quy_ve_bai_ghep(db, kh, customer):
    """Dòng yêu cầu kho khai `lsx_id` (lúc lập yêu cầu, lệnh còn ĐỘC LẬP) nhưng LSX đó SAU ĐÓ bị
    cuốn vào bài ghép — giấy LUÔN thuộc bài một khi đã ghép (spec §2: "Giấy... thuộc bài ghép"), nên
    `can_doi()` không còn nhu cầu riêng `(a.id, None)` cho giấy nữa. `kiem_xuat`/`tieu_thu` phải tra
    ĐÚNG chủ thể BÀI (nơi giữ chỗ dồn về), chứ không phải LSX đơn lẻ (nơi không còn giữ gì)."""
    from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien

    g = _giay(db)
    hang = _giay_hang(g)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    # `giay_id`/`kho_in_dai`/`kho_in_rong` BẮT BUỘC để bài thật sự sinh dòng nhu cầu giấy của
    # RIÊNG NÓ (`_gom_nhu_cau`: thiếu `giay_id` thì bài rơi vào `bo_qua`, không có dòng nào cả) —
    # thiếu thì cả hai bên `(a.id, None)` lẫn `(None, bg.id)` đều rỗng, hoá thành ca "mơ hồ" oan,
    # đúng bẫy mà `test_bai_ghep_la_CHU_THE_giu_cho` (file này) đã dặn qua cách dựng dữ liệu.
    bg = BaiGhep(ma="GB-1", ten="Bài 1", trang_thai="nhap",
                giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id))
    db.commit()

    svcv = _dung_svcv(db, kh)
    v, lines_by_id = _dung_phieu_xuat(db, hang, lsx_id=a.id, bai_ghep_id=None)
    ra = svcv._gom_theo_hang_va_chu_the(v, lines_by_id)
    assert (hang, (None, bg.id)) in ra, f"phải quy về bài ghép, thực tế: {ra}"
    assert (hang, (a.id, None)) not in ra


def test_gom_theo_hang_va_chu_the_khong_ghep_giu_nguyen_chu_the_lsx(db, kh, customer):
    """LSX KHÔNG nằm trong bài ghép nào (`ghep_cua` rỗng) — dòng yêu cầu khai `lsx_id` phải giữ
    NGUYÊN chủ thể LSX, không bị đụng tới. Đây là ca phổ biến nhất (đa số LSX không ghép) và cũng
    chứng minh nhánh "vật tư riêng không bị quy nhầm": vì `a` không hề thuộc bài nào, guard
    `lsx_id in ghep_cua` sai ngay từ đầu, không có cơ hội quy nhầm."""
    g = _giay(db)
    hang = _giay_hang(g)
    a = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200)
    db.commit()

    svcv = _dung_svcv(db, kh)
    v, lines_by_id = _dung_phieu_xuat(db, hang, lsx_id=a.id, bai_ghep_id=None)
    ra = svcv._gom_theo_hang_va_chu_the(v, lines_by_id)
    assert (hang, (a.id, None)) in ra
    assert all(chu != (None, None) for _, chu in ra)


def test_gom_theo_hang_va_chu_the_mo_ho_chan_ghi_so(db, kh, customer):
    """LSX đã ghép, nhưng mặt hàng trên dòng yêu cầu KHÔNG khớp nhu cầu riêng của LSX lẫn nhu cầu
    của bài (hàng lạ, không nằm trong routing của ai) — mơ hồ, phải chặn ghi sổ thay vì đoán, đúng
    spec §2 "trường hợp mơ hồ phải cảnh báo"."""
    from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
    from app.services.stock_voucher_service import StockVoucherError

    g = _giay(db)
    g_la = _giay(db, ma="GIAY-LA")  # giấy khác, KHÔNG nằm trong routing của `a` hay của bài
    hang_la = _giay_hang(g_la)
    a = _lenh(db, customer, ma="LSX-C", giay_id=g.id, so_to_nguyen=200)
    bg = BaiGhep(ma="GB-2", ten="Bài 2", trang_thai="nhap")
    db.add(bg)
    db.flush()
    db.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id))
    db.commit()

    svcv = _dung_svcv(db, kh)
    v, lines_by_id = _dung_phieu_xuat(db, hang_la, lsx_id=a.id, bai_ghep_id=None)
    try:
        svcv._gom_theo_hang_va_chu_the(v, lines_by_id)
        assert False, "phải raise StockVoucherError vì mơ hồ, không được đoán"
    except StockVoucherError:
        pass


# ================== KHOÁ NGUỒN — GIAO DỊCH MỘT LẦN ==================


def test_khoa_nguon_khong_loi_va_theo_thu_tu_on_dinh(db, svc, monkeypatch):
    """`_khoa_nguon` phải chạy được (không lỗi) khi truyền LỘN thứ tự — VÀ THẬT SỰ khoá theo
    (hang_loai, hang_id) TĂNG DẦN, không chỉ "không raise". Khoá lộn xộn giữa hai giao dịch cùng
    đụng chung tập mặt hàng là khoá CHÉO (deadlock) trên Postgres thật — SQLite (test) im lặng vì
    `FOR UPDATE` là no-op ở đây, nên phải soi TRỰC TIẾP chuỗi id đã khoá bằng spy trên `db.execute`;
    "không raise" không chứng minh được thứ tự đúng, chỉ chứng minh SQLite không phàn nàn.

    Cũng xác nhận không lỗi khi gọi LẦN HAI trong CÙNG giao dịch (mô phỏng `nhat_them()` rồi
    `kiem_xuat()` cùng chạm một mặt hàng trong một lượt xử lý)."""
    g1 = _giay(db, ma="GY-1")
    g2 = _giay(db, ma="GY-2")
    g3 = _giay(db, ma="GY-3")

    da_khoa: list[int] = []
    goc_execute = db.execute

    def spy(stmt, *a, **kw):
        where = getattr(stmt, "whereclause", None)
        if where is not None:
            da_khoa.append(where.right.value)
        return goc_execute(stmt, *a, **kw)

    monkeypatch.setattr(db, "execute", spy)

    svc._khoa_nguon([("giay", g3.id), ("giay", g1.id), ("giay", g2.id)])

    assert da_khoa == sorted([g1.id, g2.id, g3.id]), (
        f"phải khoá THEO THỨ TỰ id tăng dần bất kể thứ tự truyền vào, thực tế: {da_khoa}"
    )

    # Gọi lần hai trong CÙNG giao dịch — không được lỗi.
    svc._khoa_nguon([("giay", g1.id)])
