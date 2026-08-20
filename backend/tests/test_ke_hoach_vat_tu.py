"""Kế hoạch vật tư — bảng cân đối. Test SỐ HỌC, không qua HTTP.

Trọng tâm là mấy chỗ mà sai thì KHÔNG AI BÁO, chỉ có hệ quả ngoài đời (mua thừa một lô giấy, hoặc
lệnh đứng máy vì tưởng còn đủ):

* hai **bẫy đếm hai lần** — đã cấp không được trừ vào tồn lần nữa; hàng đang về chỉ cộng một lần;
* *đang lĩnh* chỉ là nhãn;
* bài ghép KHÔNG đếm đôi giấy;
* thiếu đường quy đổi → báo `khong_doi_chieu_duoc`, không đoán;
* dòng mua không gắn mặt hàng → không trừ;
* giấy nguồn khách → không sinh dòng;
* lệnh chưa xếp → mốc tạm = hạn SX **trừ** tổng thời gian dẫn.

Dựng dữ liệu THẲNG vào DB (Order/OrderLine tối thiểu để thoả FK) thay vì chạy cả luồng
đơn → chuyển SX → tạo lệnh: cái đang kiểm là phép cộng trừ của bảng cân đối, không phải luồng bán.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
from app.models.customer import Customer
from app.models.lsx import TT_CHO_BO_SUNG, TT_NHAP, TT_SAN_SANG, Lsx, LsxCongDoan
from app.models.may_thiet_bi import MayThietBi
from app.models.order import Order, OrderLine
from app.models.purchase import (
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    PR_PENDING,
    PR_PURCHASED,
    SOURCE_SAN_XUAT,
    DepartmentPurchaseRequest,
    DepartmentPurchaseRequestLine,
    PurchaseRequest,
    PurchaseRequestLine,
    Supplier,
    SupplierItem,
)
from app.models.kho_hang import KhoHang
from app.models.stock_lot import LOT_AVAILABLE, StockLot
from app.models.stock_request import REQ_APPROVED, REQ_XUAT, StockRequest, StockRequestLine
from app.models.vat_lieu_kho import GiayNguyen, VatTuInAn
from app.repositories.bai_ghep_repo import BaiGhepRepository
from app.repositories.don_vi_do_repo import DonViDoRepository
from app.repositories.lsx_repo import LsxRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.stock_lot_repo import StockLotRepository
from app.repositories.stock_request_repo import StockRequestRepository
from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from app.seed import seed_all
from app.services.ke_hoach_vat_tu_service import (
    KeHoachVatTuService,
    KeHoachVatTuValidationError,
)
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
def svc(db):
    return KeHoachVatTuService(
        db,
        lsx_repo=LsxRepository(db),
        bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db),
        requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db),
        suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )


# --- dựng dữ liệu -------------------------------------------------------------


def _giay(db, *, ma="GY-TEST", don_vi="kg", gsm=150, dai=860, rong=650) -> GiayNguyen:
    """Giấy 65×86 định lượng 150 ⇒ 1 tờ = 0,15 × 0,86 × 0,65 = 0,08385 kg.

    `cong_thuc_luong` mặc định BẬT (14/08/2026): cặp quy đổi động `tờ → kg` đã gỡ, nên giấy phải tự
    khai cách đo mới ra được kg. Đúng chuỗi mà seed và migration `0197` điền cho giấy bán theo cân.
    """
    g = GiayNguyen(ma=ma, ten=f"Giấy {ma}", gsm=gsm, kho_dai=dai, kho_rong=rong,
                   don_vi_gia=don_vi,
                   cong_thuc_luong="dinh_luong * dai_nguyen * rong_nguyen * to_nguyen")
    db.add(g)
    db.commit()
    return g


def _don(db, customer) -> Order:
    o = Order(order_no=f"DH-{customer.id}-{db.query(Order).count() + 1}", customer_id=customer.id)
    db.add(o)
    db.flush()
    ln = OrderLine(order_id=o.id, description="dòng test", qty=1_000)
    db.add(ln)
    db.commit()
    o._line = ln
    return o


def _may(db) -> MayThietBi:
    """Máy in 1.000 tờ/giờ, chuẩn bị 30'. Thời lượng bước LẤY TỪ MÁY (setup_phut/chay_phut trên
    bước là cột dormant từ 2026-08-04) — không gán máy thì tổng thời gian dẫn = 0."""
    may = db.query(MayThietBi).filter(MayThietBi.ma == "MAY-KHVT").first()
    if may is None:
        may = MayThietBi(ma="MAY-KHVT", ten="Máy in test", loai_may="press_offset_sheet",
                         toc_do=1_000, don_vi_toc_do="to_gio", makeready_time_default=30,
                         kho_max_dai=1020, kho_max_rong=720)
        db.add(may)
        db.commit()
    return may


def _lenh(db, customer, *, ma, giay_id, so_to_nguyen, han=None, nguon_giay=None,
          buoc=True) -> Lsx:
    o = _don(db, customer)
    qc = {"giay_id": giay_id}
    if nguon_giay:
        qc["nguon_giay"] = nguon_giay
    l = Lsx(
        ma=ma, ten=ma, order_id=o.id, order_line_id=o._line.id,
        so_luong_dat=1_000, so_to_nguyen=so_to_nguyen, so_con=1,
        han_hoan_thanh_sx=han, quy_cach_json=qc, trang_thai=TT_SAN_SANG,
    )
    db.add(l)
    db.flush()
    if buoc:
        db.add(LsxCongDoan(
            lsx_id=l.id, thu_tu=1, ten="In offset", loai_buoc="may", may_id=_may(db).id,
            don_vi_vao="to_nguyen", don_vi_ra="to",
            so_luong_vao=so_to_nguyen, so_luong_ra=so_to_nguyen,
        ))
    db.commit()
    return l


def _ton(db, giay: GiayNguyen, so_kg: float) -> None:
    kho = db.query(KhoHang).first()
    if kho is None:
        kho = KhoHang(ma="K1", ten="Kho test")
        db.add(kho)
        db.flush()
    db.add(StockLot(
        hang_loai="giay", hang_id=giay.id, kho_id=kho.id, ma_lo=f"LOT-{giay.ma}-{so_kg}",
        sl_ban_dau=so_kg, sl_con_lai=so_kg, ngay_nhap=HOM_NAY, trang_thai=LOT_AVAILABLE,
    ))
    db.commit()


def _de_nghi_xuat(db, giay: GiayNguyen, *, lsx_id, duyet, da_ung, dvt="kg") -> StockRequest:
    r = StockRequest(ma=f"DNX{db.query(StockRequest).count() + 1:04d}", loai=REQ_XUAT,
                     nguoi_tao_id=1, trang_thai=REQ_APPROVED)
    db.add(r)
    db.flush()
    db.add(StockRequestLine(
        request_id=r.id, hang_loai="giay", hang_id=giay.id, lsx_id=lsx_id,
        dvt=dvt, sl_de_nghi=duyet, sl_duyet=duyet, sl_da_ung=da_ung,
    ))
    db.commit()
    return r


def _phieu_mua(db, *, hang, so_luong, ngay_ve, unit="kg", status=PR_PURCHASED) -> PurchaseRequest:
    p = PurchaseRequest(code=f"PMH-{db.query(PurchaseRequest).count() + 1}",
                        status=status, expected_receipt_date=ngay_ve)
    db.add(p)
    db.flush()
    db.add(PurchaseRequestLine(
        purchase_request_id=p.id, item_name="Giấy mua",
        hang_loai=hang[0] if hang else None, hang_id=hang[1] if hang else None,
        unit=unit, quantity=so_luong, expected_unit_price=1,
    ))
    db.commit()
    return p


def _ycmh(db, *, hang, so_luong, status=DPR_OPEN, unit="kg") -> DepartmentPurchaseRequest:
    """Đề nghị mua của bộ phận — chính là thứ nút "Mua" trên bảng cân đối đẻ ra."""
    yc = DepartmentPurchaseRequest(
        code=f"YCMH-{db.query(DepartmentPurchaseRequest).count() + 1}",
        status=status, source_type=SOURCE_SAN_XUAT, purpose="Thiếu vật tư",
        needed_date=HOM_NAY,
    )
    db.add(yc)
    db.flush()
    db.add(DepartmentPurchaseRequestLine(
        department_request_id=yc.id, item_name="Giấy đề nghị",
        hang_loai=hang[0], hang_id=hang[1], unit=unit, quantity=so_luong,
    ))
    db.commit()
    return yc


@pytest.fixture
def customer(db):
    c = Customer(code="KH-KHVT", name="KH kế hoạch vật tư")
    db.add(c)
    db.commit()
    return c


def _nhom(bang, giay) -> dict:
    return next(g for g in bang["items"] if (g["hang_loai"], g["hang_id"]) == ("giay", giay.id))


# --- BẪY ĐẾM HAI LẦN ----------------------------------------------------------


def test_da_cap_du_thi_dong_xam_va_khong_tru_vao_ton_lan_nua(db, svc, customer):
    """Bẫy #1. Kho đã xuất 100 kg cho lệnh A ⇒ tồn ĐÃ giảm còn 100.

    Phần đã cấp chỉ được trừ vào NHU CẦU (A thành xám). Nếu trừ thêm lần nữa vào tồn thì lệnh B
    thấy 0 kg và báo đỏ oan — rồi ai đó đi mua một lô giấy không cần mua.
    """
    g = _giay(db)
    _ton(db, g, 100)                                   # tồn SAU khi đã xuất 100 cho lệnh A
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000,
          han=MAI + timedelta(days=1))
    _de_nghi_xuat(db, g, lsx_id=a.id, duyet=100, da_ung=100)

    nhom = _nhom(svc.can_doi(), g)
    dong = {d["ma"]: d for d in nhom["dong"]}
    assert dong["LSX-A"]["trang_thai"] == "xam"
    assert dong["LSX-A"]["da_cap"] == pytest.approx(100)
    assert dong["LSX-A"]["con_phai_co"] == pytest.approx(0)
    # 1.000 tờ × 0,08385 kg = 83,85 kg ⇒ B đủ bằng CHÍNH tồn 100 kg đang có (không cần hàng về).
    assert dong["LSX-B"]["trang_thai"] == "xanh"
    assert dong["LSX-B"]["thieu"] == pytest.approx(0)


def test_hang_dang_ve_chi_cong_mot_lan(db, svc, customer):
    """Bẫy #2. Một đợt hàng về 100 kg không được cộng cho CẢ HAI lệnh."""
    g = _giay(db)
    _phieu_mua(db, hang=("giay", g.id), so_luong=100, ngay_ve=HOM_NAY)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000,
          han=MAI + timedelta(days=1))

    dong = {d["ma"]: d for d in _nhom(svc.can_doi(), g)["dong"]}
    assert dong["LSX-A"]["trang_thai"] == "vang"       # đủ NHỜ hàng đang về
    assert dong["LSX-B"]["trang_thai"] == "do"         # lô đó đã dùng cho A rồi
    assert dong["LSX-B"]["thieu"] > 0


def test_dang_linh_chi_la_nhan_khong_vao_phep_tru(db, svc, customer):
    """Đề nghị đã lập nhưng kho CHƯA ghi sổ: hàng vẫn nằm trong kho ⇒ tồn không đổi."""
    g = _giay(db)
    _ton(db, g, 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    _de_nghi_xuat(db, g, lsx_id=a.id, duyet=100, da_ung=0)

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["dang_linh"] == pytest.approx(100)
    assert dong["da_cap"] == pytest.approx(0)
    assert dong["con_phai_co"] == pytest.approx(dong["nhu_cau"])
    assert dong["trang_thai"] == "xanh"                # tồn vẫn còn nguyên


def test_thieu_cua_tung_dong_khong_cong_don(db, svc, customer):
    """Hai dòng đỏ liên tiếp: `thieu` của dòng sau KHÔNG được gộp cả phần thiếu của dòng trước.

    Nếu cộng dồn thì tick cả hai rồi gộp một yêu cầu mua là đặt thừa đúng phần đếm hai lần.
    """
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000,
          han=MAI + timedelta(days=1))

    nhom = _nhom(svc.can_doi(), g)
    dong = {d["ma"]: d for d in nhom["dong"]}
    assert dong["LSX-A"]["thieu"] == pytest.approx(dong["LSX-B"]["thieu"])
    assert sum(d["thieu"] for d in nhom["dong"]) == pytest.approx(nhom["tong_can"])


# --- BÀI GHÉP -----------------------------------------------------------------


def test_bai_ghep_khong_dem_doi_giay(db, svc, customer):
    """Hai lệnh in chung một tờ ⇒ MỘT dòng giấy mang mã bài, KHÔNG có dòng nào mang mã lệnh."""
    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    bg = BaiGhep(ma="GB-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    db.commit()

    mas = [d["ma"] for d in _nhom(svc.can_doi(), g)["dong"]]
    assert mas == ["GB-001"]


# --- KHÔNG ĐOÁN ---------------------------------------------------------------


def test_thieu_duong_quy_doi_thi_bao_chu_khong_doan(db, svc, customer):
    """Giấy đếm theo kg nhưng CHƯA khai khổ ⇒ cạnh động `tờ → kg` tắt.

    Phải ra cờ `khong_doi_chieu_duoc` chứ không được lặng lẽ lấy hệ số 1 — hệ số 1 ở đây nghĩa là
    "1 tờ nặng 1 kg", sai gấp hơn 10 lần mà bảng vẫn xanh.
    """
    g = _giay(db, ma="GY-KHONG-KHO", dai=0, rong=0)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert "khong_doi_chieu_duoc" in dong["canh_bao"]
    assert dong["nhu_cau"] == 0
    assert dong["ly_do_canh_bao"]


def test_dong_mua_khong_gan_mat_hang_thi_khong_tru(db, svc, customer):
    """Phiếu mua 500 kg nhưng không gắn `(hang_loai, hang_id)` ⇒ bảng KHÔNG cộng.

    Ghép ngược bằng `item_name` là đoán; đoán trúng nhầm lô giấy khác thì bảng báo đủ trong khi
    thực tế thiếu.
    """
    g = _giay(db)
    _phieu_mua(db, hang=None, so_luong=500, ngay_ve=HOM_NAY)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["trang_thai"] == "do"


def test_lenh_cu_con_co_nguon_khach_VAN_sinh_dong_can_doi(db, svc, customer):
    """Đợt 4 · K — nguồn giấy "khách cấp" đã gỡ, nên bảng cân đối thôi bỏ qua lệnh mang cờ đó.

    Test cũ ghim "không sinh dòng"; nay ngược lại. Lý do nghiệp vụ: giấy vẫn phải CÓ MẶT ở xưởng
    đúng ngày bất kể ai trả tiền — chuyện tiền là của phiếu tính giá, không phải của bảng cân đối.
    Lệnh cũ còn cờ trong `quy_cach_json` cũng hiện dòng.
    """
    g = _giay(db)
    _lenh(db, customer, ma="LSX-KHACH", giay_id=g.id, so_to_nguyen=5_000, han=MAI,
          nguon_giay="khach")

    assert [gr for gr in svc.can_doi()["items"] if gr["hang_id"] == g.id]


def test_lenh_chua_chon_giay_hien_o_bo_qua_chu_khong_im_lang(db, svc, customer):
    o = _don(db, customer)
    db.add(Lsx(ma="LSX-NOGIAY", ten="x", order_id=o.id, order_line_id=o._line.id,
               so_luong_dat=10, so_to_nguyen=100, quy_cach_json={}, trang_thai=TT_SAN_SANG))
    db.commit()

    assert [b["ma"] for b in svc.can_doi()["bo_qua"]] == ["LSX-NOGIAY"]


# --- NGÀY CẦN -----------------------------------------------------------------


def test_lenh_chua_xep_lay_moc_tam_bang_han_sx_tru_thoi_gian_dan(db, svc, customer):
    """⚠️ KHÔNG lấy thẳng hạn SX: giấy cần ở ĐẦU chuỗi, hạn SX là mốc CUỐI chuỗi."""
    g = _giay(db)
    han = HOM_NAY + timedelta(days=10)
    # 1 bước: 30 phút setup + 60 phút chạy = 90 phút ⇒ ceil(90/60/8) = 1 ngày.
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=han)

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["moc_tam"] is True
    assert dong["ngay_can"] == han - timedelta(days=1)
    assert dong["ngay_can"] < han


def test_hang_ve_sau_ngay_can_KHONG_duoc_cong_vao_ton(db, svc, customer):
    """Lô về sau ngày cần KHÔNG được cộng vào tồn — dòng vẫn là việc phải lo.

    ⚠️ Đổi assert 17/08/2026: trước đây kỳ vọng `do`, nay là `ve_muon`. KHÔNG phải nới lỏng — nó
    CHẶT hơn: `ve_muon` nói thêm rằng hàng ĐÃ MUA rồi, chỉ sai ngày. Cửa chặn phát hành ở bàn xếp
    lịch nhận cả hai mã như nhau (`xep_lich_van_de_service._thieu_vat_tu`), nên lệnh vẫn không
    phát hành được. Cái đổi là CÂU CHỈ VIỆC: đỏ thì đi mua, về muộn thì dời lịch.
    """
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=2))
    _phieu_mua(db, hang=("giay", g.id), so_luong=500, ngay_ve=HOM_NAY + timedelta(days=30))

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["trang_thai"] == "ve_muon"
    assert dong["con_lai_sau"] < 0          # lô kia KHÔNG được cộng vào — đây mới là điều cốt lõi
    assert dong["ngay_du_hang"] == HOM_NAY + timedelta(days=30)


# --- HẠN ĐẶT ------------------------------------------------------------------


def test_han_dat_chi_tru_ngay_kiem_nhap(db, svc, customer):
    """Hạn đặt = ngày cần − ngày kiểm nhập, KHÔNG phụ thuộc NCC.

    Ô "số ngày giao" ở bảng giá NCC đã bỏ (10/08/2026): lúc khai danh mục chưa ai biết ông ấy
    giao mấy ngày, số gõ vào là số đoán mà lại đi bật đèn "đặt muộn". Khai NCC kiểu gì thì hạn
    đặt vẫn ra y nhau.
    """
    g = _giay(db)
    for ten in ("NCC A", "NCC B"):
        s = Supplier(name=ten, status="active")
        db.add(s)
        db.flush()
        db.add(SupplierItem(supplier_id=s.id, hang_loai="giay", hang_id=g.id,
                            item_name=g.ten, unit="kg", unit_price=1))
    db.commit()
    han = HOM_NAY + timedelta(days=20)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=han)

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert "ncc_nhanh_nhat" not in dong
    assert dong["han_dat"] == dong["ngay_can"] - timedelta(days=1)


# --- VẬT TƯ KHÁC + KHÔNG PHƠI GIÁ --------------------------------------------


def test_vat_tu_khai_tay_o_buoc_len_bang(db, svc, customer):
    g = _giay(db)
    vt = VatTuInAn(ma="VT-MUC", ten="Mực đen", don_vi_gia="kg")
    db.add(vt)
    db.commit()
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=100, han=MAI)
    buoc = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == l.id).first()
    from app.models.lsx import LsxCongDoanVatTu

    db.add(LsxCongDoanVatTu(
        lsx_cong_doan_id=buoc.id, vat_tu_id=vt.id, vat_tu_ma_snapshot=vt.ma,
        vat_tu_ten_snapshot=vt.ten, don_vi_snapshot="kg", so_luong=5,
    ))
    db.commit()

    nhom = next(g for g in svc.can_doi()["items"]
                if (g["hang_loai"], g["hang_id"]) == ("vat_tu", vt.id))
    assert nhom["dong"][0]["nhu_cau"] == pytest.approx(5)


def test_khong_phoi_gia_von_o_bat_ky_truong_nao(db, svc, customer):
    """Bảng mở cho vai Kế hoạch SX; giá vốn thuộc quyền Kho/Kế toán."""
    g = _giay(db)
    _ton(db, g, 100)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    cam = ("gia", "don_gia", "tien", "price", "cost")
    for nhom in svc.can_doi()["items"]:
        assert not [k for k in nhom if k in cam]
        for d in nhom["dong"]:
            assert not [k for k in d if k in cam]


# --- VÁ SAU AUDIT (2026-08-09) -------------------------------------------------
# Bốn ca dưới đây là lỗi THẬT bị bắt lúc soi lại, không phải giả định. Giữ test để đừng ai vô tình
# quay lại hành vi cũ.


def test_khong_doi_chieu_duoc_KHONG_deo_nhan_da_cap_du(db, svc, customer):
    """Dòng máy không tính nổi phải mang trạng thái RIÊNG.

    Trước đây `nhu_cau = 0` rơi vào nhánh "con_phai_co ≤ 0" ⇒ pill "Đã cấp đủ" — mạnh hơn cả "đủ",
    dán lên đúng dòng chưa ai tính được. Và vì `so_dong_do` không tăng, nhóm còn biến mất khỏi bộ
    lọc "chỉ mặt hàng đang thiếu": giấu đúng cái cần thấy.
    """
    g = _giay(db, ma="GY-KHONG-KHO2", dai=0, rong=0)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    nhom = _nhom(svc.can_doi(), g)
    assert nhom["dong"][0]["trang_thai"] == "khong_ro"
    assert nhom["so_dong_khong_ro"] == 1
    # Và phải CÒN LẠI khi lọc "chỉ thiếu" — thứ máy không đánh giá được thì phải lo nhiều hơn.
    assert _nhom(svc.can_doi(chi_thieu=True), g)["so_dong_khong_ro"] == 1


def test_da_cap_gan_vao_lenh_thanh_vien_van_tru_dung_vao_bai_ghep(db, svc, customer):
    """Thủ kho chọn LỆNH (thành viên bài) thay vì BÀI — số đã cấp không được bốc hơi.

    Giấy của lệnh thành viên KHÔNG có dòng nhu cầu riêng (một dòng cho cả bài, chống đếm đôi), nên
    khoá `(hang, lsx_id, None)` không dòng nào tra tới. Không quy về bài thì bài hiện đỏ dù kho đã
    cấp đủ giấy — rồi ai đó đi mua thêm.
    """
    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    bg = BaiGhep(ma="GB-002", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    db.commit()
    # Kho cấp 200 kg, khai "cho LSX-A" (lệnh thành viên), không phải "cho GB-002".
    _de_nghi_xuat(db, g, lsx_id=a.id, duyet=200, da_ung=200)

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["ma"] == "GB-002"
    assert dong["da_cap"] == pytest.approx(200)


def test_phieu_mua_da_nhan_mot_phan_thi_chi_con_phan_chua_ve(db, svc, customer):
    """Phiếu cũ (chưa có đợt giao) khai `received_quantity` một phần: phần ĐÃ nhận nằm trong tồn rồi.

    Coi là "chưa nhận gì" thì phần đó bị đếm HAI LẦN — một lần ở tồn, một lần ở hàng đang về — và
    bảng báo đủ trong khi thật ra thiếu.
    """
    g = _giay(db)
    p = _phieu_mua(db, hang=("giay", g.id), so_luong=100, ngay_ve=HOM_NAY)
    ln = p.lines[0]
    ln.received_quantity = 90            # đã về 90, còn đúng 10 đang trên đường
    db.commit()
    _ton(db, g, 90)                      # 90 đó đã nằm trong kho
    # Cần 1.000 tờ = 83,85 kg → tồn 90 đủ; nhưng nếu cộng nhầm cả 100 "đang về" thì lệnh thứ hai
    # cũng hoá đủ, trong khi thật ra chỉ còn 90 + 10 = 100 kg cho 167,7 kg nhu cầu.
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000,
          han=MAI + timedelta(days=1))

    dong = {d["ma"]: d for d in _nhom(svc.can_doi(), g)["dong"]}
    assert dong["LSX-A"]["trang_thai"] == "xanh"
    assert dong["LSX-B"]["trang_thai"] == "do"


def test_lenh_chua_gan_may_thi_bao_khong_suy_duoc_thoi_gian_dan(db, svc, customer):
    """Thời gian dẫn lấy từ MÁY. Bước máy chưa gán máy ⇒ tổng = 0 ⇒ mốc tạm rơi đúng về hạn SX,
    nhìn y như đã tính — đúng cái bẫy plan gạch chân. Phải NÓI RA, không bịa số ngày mặc định."""
    g = _giay(db)
    han = HOM_NAY + timedelta(days=10)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=han)
    for cd in db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == l.id):
        cd.may_id = None                 # gỡ máy → không suy được thời gian dẫn
    db.commit()

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["ngay_can"] == han        # đúng: máy không đoán
    assert "dan_khong_suy_duoc" in dong["canh_bao"]
    assert dong["ly_do_canh_bao"]


def test_giay_khong_co_kho_o_danh_muc_van_quy_ra_kg_bang_kho_CUA_LENH(db, svc, customer):
    """Danh mục Giấy KHÔNG có ô khổ (chốt 21/07) — khổ lấy từ chính lệnh.

    Không có luật này thì mọi giấy do người dùng tự khai đều rơi vào "chưa đánh giá được", vì chỉ
    giấy seed demo mới tình cờ còn khổ trong dữ liệu. Mà lệnh thì LUÔN mang khổ tờ in + định lượng,
    và đó mới là khổ giấy thực sự bị tiêu thụ.

    Số thật: 1.000 tờ giấy 150 g/m² khổ 790×1090 = 0,79 × 1,09 × 150 g = 129,165 g/tờ ⇒ 129,165 kg.
    """
    g = _giay(db, ma="GY-KHONG-KHO", dai=0, rong=0, gsm=0)   # danh mục trống khổ + định lượng
    o = _don(db, customer)
    l = Lsx(
        ma="LSX-QC", ten="LSX-QC", order_id=o.id, order_line_id=o._line.id,
        so_luong_dat=1_000, so_to_nguyen=1_000, so_con=1,
        han_hoan_thanh_sx=HOM_NAY + timedelta(days=10),
        quy_cach_json={"giay_id": g.id, "kho_in_dai": 1090, "kho_in_rong": 790, "gsm": 150},
        trang_thai=TT_SAN_SANG,
    )
    db.add(l)
    db.commit()

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert "khong_doi_chieu_duoc" not in dong["canh_bao"], dong.get("ly_do_canh_bao")
    assert dong["nhu_cau"] == pytest.approx(129.165, abs=0.01)
    assert "kg" in dong["nhu_cau_hien_thi"]


def test_giay_co_CONG_THUC_LUONG_thi_ra_so_thang_khong_qua_quy_doi(db, svc, customer):
    """Giấy khai ĐVT `kg` THẬT + công thức lượng riêng ⇒ kế hoạch ra kg, khỏi cạnh `tờ → kg`.

    Chốt 13/08/2026: công thức KHÔNG có đích. Cạnh quy đổi động `tờ → kg` là chỗ duy nhất còn giữ
    kiểu "công thức mà lại có đích"; khai công thức ngay trên mặt hàng thì cạnh đó hết lý do sống.

    Cùng số với test trên: 1.000 tờ 150 g/m² khổ 790×1090 ⇒ 129,165 kg.
    """
    g = _giay(db, ma="GY-CTL", dai=0, rong=0, gsm=0)
    g.cong_thuc_luong = "dinh_luong * dai_in * rong_in * to_nguyen"
    o = _don(db, customer)
    l = Lsx(
        ma="LSX-CTL", ten="LSX-CTL", order_id=o.id, order_line_id=o._line.id,
        so_luong_dat=1_000, so_to_nguyen=1_000, so_con=1,
        han_hoan_thanh_sx=HOM_NAY + timedelta(days=10),
        quy_cach_json={"giay_id": g.id, "kho_in_dai": 1090, "kho_in_rong": 790, "gsm": 150},
        trang_thai=TT_SAN_SANG,
    )
    db.add(l)
    db.commit()

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert "khong_doi_chieu_duoc" not in dong["canh_bao"], dong.get("ly_do_canh_bao")
    assert dong["nhu_cau"] == pytest.approx(129.165, abs=0.01)


def test_giay_thieu_kho_o_CA_HAI_noi_thi_van_bao_khong_doi_chieu_duoc(db, svc, customer):
    """Lệnh cũ chưa có khổ trong quy cách + danh mục cũng trống ⇒ KHÔNG đoán, phải nói ra."""
    g = _giay(db, ma="GY-TRONG", dai=0, rong=0, gsm=0)
    _lenh(db, customer, ma="LSX-TRONG", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=10))

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert "khong_doi_chieu_duoc" in dong["canh_bao"]


def test_dong_trong_nhom_sap_theo_NGAY_CAN(db, svc, customer):
    """Con trỏ tồn chạy theo NGÀY CẦN, nên thứ tự dòng phải là thứ tự ngày cần — không phải thứ tự
    tạo lệnh, không phải id.

    Sai thứ tự là sai kết quả chứ không chỉ sai hiển thị: lệnh cần sau mà đứng trước sẽ ăn hết tồn,
    rồi lệnh cần trước bị báo đỏ oan và người ta đi mua giấy đã có sẵn trong kho.
    """
    g = _giay(db)
    _ton(db, g, 10_000)
    # Tạo NGƯỢC thứ tự ngày cần: lệnh hạn muộn tạo TRƯỚC, hạn sớm tạo SAU.
    _lenh(db, customer, ma="LSX-MUON", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=20))
    _lenh(db, customer, ma="LSX-SOM", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=3))
    _lenh(db, customer, ma="LSX-GIUA", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=10))

    dong = _nhom(svc.can_doi(), g)["dong"]
    ngays = [d["ngay_can"] for d in dong]
    assert ngays == sorted(ngays), f"dòng phải xếp theo ngày cần tăng dần, thực tế {ngays}"
    assert [d["ma"] for d in dong] == ["LSX-SOM", "LSX-GIUA", "LSX-MUON"]


# 🔴 Khối test nhóm "Công cụ" (khuôn) đã GỠ 16/08/2026 cùng chính nhóm đó — xem mg `0203`.
# Cặp cờ `requires_tooling` / `tooling_type` VẪN CÒN ở danh mục Công đoạn, nhưng nay chỉ phiếu
# tính giá đọc (để biết bước nào hỏi PHÍ khuôn) — luật đó gác ở `test_thanh_phan_engine.py`.


# ============ ĐỢT 1 (17/08/2026) — ba lỗi làm SAI SỐ TIỀN ĐI MUA ============
#
# Cả ba cùng một họ HỎNG CÂM: bảng vẫn vẽ ra, không lỗi, chỉ con số gửi sang thu mua là sai.


def _vat_tu(db, *, ma="VT-MUC", ten="Mực đen", don_vi="kg") -> VatTuInAn:
    vt = VatTuInAn(ma=ma, ten=ten, don_vi_gia=don_vi)
    db.add(vt)
    db.commit()
    return vt


def _khai_vat_tu(db, buoc, vt, so_luong, dvt="kg") -> None:
    from app.models.lsx import LsxCongDoanVatTu

    db.add(LsxCongDoanVatTu(
        lsx_cong_doan_id=buoc.id, vat_tu_id=vt.id, vat_tu_ma_snapshot=vt.ma,
        vat_tu_ten_snapshot=vt.ten, don_vi_snapshot=dvt, so_luong=so_luong,
    ))
    db.commit()


def _them_buoc(db, lsx, *, thu_tu, ten) -> LsxCongDoan:
    b = LsxCongDoan(lsx_id=lsx.id, thu_tu=thu_tu, ten=ten, loai_buoc="may", may_id=_may(db).id,
                    don_vi_vao="to", don_vi_ra="to", so_luong_vao=100, so_luong_ra=100)
    db.add(b)
    db.commit()
    return b


def _buoc_dau(db, lsx) -> LsxCongDoan:
    """Bước ĐẦU của lệnh. `order_by` tường minh: mọi chỗ gọi hiện đều lúc lệnh mới có một bước,
    nhưng `.first()` trần sẽ gãy im lặng nếu ai đó tái dùng sau `_them_buoc`."""
    return (db.query(LsxCongDoan)
            .filter(LsxCongDoan.lsx_id == lsx.id)
            .order_by(LsxCongDoan.thu_tu.asc(), LsxCongDoan.id.asc())
            .first())


def _khai_vat_tu_bai(db, buoc_chung, vt, so_luong, dvt="kg") -> None:
    """Vật tư của một bước CHUNG của bài ghép — bảng khác hẳn bảng vật tư của bước lệnh."""
    from app.models.bai_ghep_cong_doan import BaiGhepCongDoanVatTu

    db.add(BaiGhepCongDoanVatTu(
        bai_ghep_cong_doan_id=buoc_chung.id, vat_tu_id=vt.id, vat_tu_ma_snapshot=vt.ma,
        vat_tu_ten_snapshot=vt.ten, don_vi_snapshot=dvt, so_luong=so_luong,
    ))
    db.commit()


# --- Lỗi ①: một lệnh ăn CÙNG một vật tư ở NHIỀU công đoạn ---------------------


def test_cung_vat_tu_o_hai_buoc_sinh_HAI_dong_khac_khoa(db, svc, customer):
    """Một lệnh có nhiều công đoạn, mỗi công đoạn khai vật tư riêng ⇒ hai dòng RIÊNG BIỆT.

    Ca thật trên DB dev: LSX26-0004 khai *Màng cán bóng* ở cả #20 In offset lẫn #50 Xén 3 mặt.
    """
    g = _giay(db)
    vt = _vat_tu(db)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=100, han=MAI)
    b1 = _buoc_dau(db, l)
    b2 = _them_buoc(db, l, thu_tu=2, ten="Bước hai")
    _khai_vat_tu(db, b1, vt, 5)
    _khai_vat_tu(db, b2, vt, 5)

    nhom = next(x for x in svc.can_doi()["items"]
                if (x["hang_loai"], x["hang_id"]) == ("vat_tu", vt.id))
    assert len(nhom["dong"]) == 2, "hai công đoạn ⇒ hai dòng, không được gộp"
    assert nhom["tong_can"] == pytest.approx(10)
    # KHOÁ phải khác nhau — đây là thứ `gom_de_nghi` tra; trùng khoá là nuốt mất một dòng.
    assert {d["buoc_id"] for d in nhom["dong"]} == {b1.id, b2.id}


def test_de_nghi_mua_cong_DU_ca_hai_buoc_khong_ra_mot_nua(db, svc, customer):
    """🔴 Lỗi ① — trước 17/08/2026 hàm này trả 5 thay vì 10, đúng MỘT NỬA.

    Khoá dòng thiếu `buoc_id` nên hai dòng cùng lệnh + cùng món trùng khoá; dict `tra` ghi đè, dòng
    sau nuốt dòng trước. Không lỗi, không cảnh báo — chỉ là đơn mua ra nửa số cần.
    """
    g = _giay(db)
    vt = _vat_tu(db)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=100, han=MAI)
    b1 = _buoc_dau(db, l)
    b2 = _them_buoc(db, l, thu_tu=2, ten="Bước hai")
    _khai_vat_tu(db, b1, vt, 5)
    _khai_vat_tu(db, b2, vt, 5)

    gom = svc.gom_de_nghi([
        {"hang_loai": "vat_tu", "hang_id": vt.id, "lsx_id": l.id,
         "bai_ghep_id": None, "buoc_id": b1.id},
        {"hang_loai": "vat_tu", "hang_id": vt.id, "lsx_id": l.id,
         "bai_ghep_id": None, "buoc_id": b2.id},
    ])
    assert len(gom["lines"]) == 1                      # gộp về MỘT dòng hàng để đi mua
    assert gom["lines"][0]["quantity"] == pytest.approx(10)


def test_da_cap_CHIA_cho_cac_buoc_khong_tru_nguyen_vao_tung_dong(db, svc, customer):
    """🔴 Cùng họ lỗi ①, nhưng ở phía ĐÃ CẤP — sửa 17/08/2026.

    Phiếu xuất kho chỉ gắn `lsx_id`, KHÔNG có `lsx_cong_doan_id`: kho xuất cho một LỆNH chứ không
    cho một bước. Nhưng lệnh ăn cùng món ở hai công đoạn thì có HAI dòng cùng khoá đó. Trừ nguyên
    phần đã cấp vào cả hai ⇒ cả hai ra `con_phai_co = 0` ⇒ bảng báo "đã cấp đủ" trong khi xưởng
    còn thiếu đúng một nửa. Tệ hơn báo thiếu oan: không ai đi mua bù.

    Chia theo thứ tự ngày cần — cùng luật con trỏ tồn và luật ưu tiên của giữ chỗ.
    """
    g = _giay(db)
    vt = _vat_tu(db)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=100, han=MAI)
    b1 = _buoc_dau(db, l)
    b2 = _them_buoc(db, l, thu_tu=2, ten="Bước hai")
    _khai_vat_tu(db, b1, vt, 5)
    _khai_vat_tu(db, b2, vt, 5)
    # Kho mới cấp 5 kg cho cả lệnh — đủ MỘT bước, không đủ hai.
    r = StockRequest(ma="DNX-CHIA", loai=REQ_XUAT, nguoi_tao_id=1, trang_thai=REQ_APPROVED)
    db.add(r)
    db.flush()
    db.add(StockRequestLine(request_id=r.id, hang_loai="vat_tu", hang_id=vt.id, lsx_id=l.id,
                            dvt="kg", sl_de_nghi=5, sl_duyet=5, sl_da_ung=5))
    db.commit()

    nhom = next(x for x in svc.can_doi()["items"]
                if (x["hang_loai"], x["hang_id"]) == ("vat_tu", vt.id))
    con = [_f2(d["con_phai_co"]) for d in nhom["dong"]]
    assert sorted(con) == [0, 5], f"5 kg chỉ phủ được MỘT bước, thực tế còn phải có: {con}"
    assert nhom["tong_can"] == pytest.approx(5), "cả lệnh vẫn còn thiếu 5 kg"


def _f2(v) -> float:
    return round(float(v or 0), 2)


def test_tick_trung_mot_dong_khong_lam_mua_gap_doi(db, svc, customer):
    """Client gửi hai lần cùng một khoá (bấm đúp / bảng cũ) ⇒ vẫn chỉ tính MỘT lần."""
    g = _giay(db)
    vt = _vat_tu(db)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=100, han=MAI)
    b1 = _buoc_dau(db, l)
    _khai_vat_tu(db, b1, vt, 5)

    khoa = {"hang_loai": "vat_tu", "hang_id": vt.id, "lsx_id": l.id,
            "bai_ghep_id": None, "buoc_id": b1.id}
    gom = svc.gom_de_nghi([khoa, dict(khoa)])
    assert gom["lines"][0]["quantity"] == pytest.approx(5)


# --- Lỗi ②: "đã mua nhưng về muộn" KHÁC "chưa mua gì" ------------------------


def test_ve_muon_khong_cho_tick_mua_them(db, svc, customer):
    """Mua thêm cho lô đang trên đường về là MUA ĐÚP — chặn ngay ở cửa."""
    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000,
              han=HOM_NAY + timedelta(days=2))
    _phieu_mua(db, hang=("giay", g.id), so_luong=500, ngay_ve=HOM_NAY + timedelta(days=30))

    with pytest.raises(KeHoachVatTuValidationError, match="đang về"):
        svc.gom_de_nghi([{"hang_loai": "giay", "hang_id": g.id, "lsx_id": l.id,
                          "bai_ghep_id": None, "buoc_id": _buoc_dau(db, l).id}])


def test_ngay_ve_lay_lo_DU_PHU_khong_phai_lo_gan_nhat(db, svc, customer):
    """Dời lịch theo lô gần nhất mà lô đó chỉ có 1 kg thì tới nơi vẫn không đủ hàng.

    Hai lô: 1 kg về sau 10 ngày, 5.000 kg về sau 40 ngày. Lệnh cần ~83 kg ⇒ chỉ lô THỨ HAI mới cứu
    được, nên ngày trả về phải là ngày của lô đó.
    """
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=2))
    _phieu_mua(db, hang=("giay", g.id), so_luong=1, ngay_ve=HOM_NAY + timedelta(days=10))
    _phieu_mua(db, hang=("giay", g.id), so_luong=5_000, ngay_ve=HOM_NAY + timedelta(days=40))

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["trang_thai"] == "ve_muon"
    assert dong["ngay_du_hang"] == HOM_NAY + timedelta(days=40)


def test_dong_khong_co_ngay_can_thi_KHONG_dan_nhan_ve_muon(db, svc, customer):
    """"Muộn" là muộn SO VỚI một mốc — dòng chưa có mốc nào thì không có gì để so.

    Dán nhãn đó vào sẽ vừa cấm tick mua vừa chặn phát hành với câu "dời bước tiêu thụ", trong khi
    việc thật là đi khai hạn sản xuất.
    """
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=None)
    _phieu_mua(db, hang=("giay", g.id), so_luong=5_000, ngay_ve=HOM_NAY + timedelta(days=30))

    assert _nhom(svc.can_doi(), g)["dong"][0]["trang_thai"] != "ve_muon"


def test_loc_chi_thieu_GIU_nhom_chi_co_dong_ve_muon(db, svc, customer):
    """Hàng mua rồi mà về muộn thì lệnh VẪN đứng máy — lọc nó đi là giấu đúng việc phải lo."""
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=2))
    _phieu_mua(db, hang=("giay", g.id), so_luong=5_000, ngay_ve=HOM_NAY + timedelta(days=30))

    nhom = _nhom(svc.can_doi(chi_thieu=True), g)
    assert nhom["so_dong_ve_muon"] == 1 and nhom["so_dong_do"] == 0


# --- Lỗi ③: đặt hàng theo ngày mà hệ TỰ NHẬN là không suy được ---------------


def test_ngay_khong_suy_duoc_thi_KHONG_dung_lam_needed_date(db, svc, customer):
    """Lệnh còn bước chưa gán máy ⇒ mốc tạm rơi về đúng hạn SX (muộn hơn thật), và hệ TỰ ĐÁNH DẤU.

    Lấy chính con số mình vừa tuyên bố là sai đi đặt hàng thì đặt trễ mà bảng vẫn xanh.
    """
    g = _giay(db)
    han = HOM_NAY + timedelta(days=20)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=han)
    buoc = _buoc_dau(db, l)
    buoc.may_id = None          # gỡ máy ⇒ thời gian dẫn = 0 ⇒ cờ `dan_khong_suy_duoc`
    db.commit()

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert "dan_khong_suy_duoc" in dong["canh_bao"]

    gom = svc.gom_de_nghi([{"hang_loai": "giay", "hang_id": g.id, "lsx_id": l.id,
                            "bai_ghep_id": None, "buoc_id": buoc.id}])
    assert gom["needed_date"] != han, "không được lấy ngày mà hệ vừa nói là không suy được"
    assert "chưa suy được" in gom["ghi_chu_ngay"]


def test_ghi_chu_kem_ngay_can_tung_lenh(db, svc, customer):
    """Yêu cầu chỉ mang MỘT ngày (sớm nhất) — người mua cần biết các mốc còn lại."""
    g = _giay(db)
    l1 = _lenh(db, customer, ma="LSX-SOM", giay_id=g.id, so_to_nguyen=500,
               han=HOM_NAY + timedelta(days=5))
    l2 = _lenh(db, customer, ma="LSX-MUON", giay_id=g.id, so_to_nguyen=500,
               han=HOM_NAY + timedelta(days=25))

    gom = svc.gom_de_nghi([
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": l1.id,
         "bai_ghep_id": None, "buoc_id": _buoc_dau(db, l1).id},
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": l2.id,
         "bai_ghep_id": None, "buoc_id": _buoc_dau(db, l2).id},
    ])
    assert "LSX-SOM" in gom["ghi_chu_ngay"] and "LSX-MUON" in gom["ghi_chu_ngay"]


def test_khong_co_han_SX_thi_noi_dung_ly_do(db, svc, customer):
    """Hai đường làm `ngays` rỗng ⇒ hai câu khác nhau. Chẩn đoán sai thì thu mua đi sửa nhầm chỗ.

    Ở đây lệnh KHÔNG có hạn SX (khác hẳn ca "còn bước chưa gán máy") — nói "chưa gán máy" là chỉ
    người ta đi gán máy, gán xong vẫn không ra ngày.
    """
    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=None)

    gom = svc.gom_de_nghi([{"hang_loai": "giay", "hang_id": g.id, "lsx_id": l.id,
                            "bai_ghep_id": None, "buoc_id": _buoc_dau(db, l).id}])
    assert "chưa khai hạn sản xuất" in gom["ghi_chu_ngay"]
    assert "chưa gán máy" not in gom["ghi_chu_ngay"]


def test_tron_lenh_ro_va_lenh_mo_thi_GOI_TEN_lenh_mo(db, svc, customer):
    """Yêu cầu vẫn có ngày (từ lệnh rõ) nhưng phải nói ra lệnh nào KHÔNG tin được ngày.

    Im lặng ở đây thì người mua đọc "LSX-RO, LSX-MO · cần 21/08" và tưởng cả hai cùng cần 21/08.
    """
    g = _giay(db)
    ro = _lenh(db, customer, ma="LSX-RO", giay_id=g.id, so_to_nguyen=500,
               han=HOM_NAY + timedelta(days=6))
    mo = _lenh(db, customer, ma="LSX-MO", giay_id=g.id, so_to_nguyen=500,
               han=HOM_NAY + timedelta(days=20))
    b_mo = _buoc_dau(db, mo)
    b_mo.may_id = None                       # ⇒ cờ `dan_khong_suy_duoc`
    db.commit()

    # Lấy ngày cần THẬT của từng dòng thay vì ghim số: ngày cần là mốc SUY (hạn SX − thời gian
    # dẫn), nên ghim cứng sẽ đỏ oan mỗi khi ai đó chỉnh tốc độ máy trong fixture.
    dong = {d["ma"]: d for d in _nhom(svc.can_doi(), g)["dong"]}
    gom = svc.gom_de_nghi([
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": ro.id,
         "bai_ghep_id": None, "buoc_id": _buoc_dau(db, ro).id},
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": mo.id,
         "bai_ghep_id": None, "buoc_id": b_mo.id},
    ])
    assert gom["needed_date"] == dong["LSX-RO"]["ngay_can"], "phải lấy ngày của lệnh RÕ"
    assert gom["needed_date"] != dong["LSX-MO"]["ngay_can"]
    assert "LSX-MO" in gom["ghi_chu_ngay"] and "Chưa suy được" in gom["ghi_chu_ngay"]
    assert "chưa gán máy" in gom["ghi_chu_ngay"]      # LSX-MO có hạn, chỉ thiếu máy


def test_tron_lenh_ro_va_lenh_KHONG_HAN_thi_noi_dung_ly_do(db, svc, customer):
    """🔴 Cùng cờ `dan_khong_suy_duoc` nhưng HAI nguyên nhân — phải ra HAI câu.

    Lệnh chưa khai hạn SX cũng đeo cờ đó, dù máy đã gán đủ. In cứng "còn bước chưa gán máy" là chỉ
    thu mua đi bảo kế hoạch gán máy, kế hoạch mở ra thấy máy đủ rồi. Vài lần thế là không ai đọc
    câu ⚠ nữa — mà cả đợt này dựng lên để những câu ⚠ đó đáng tin.
    """
    g = _giay(db)
    ro = _lenh(db, customer, ma="LSX-RO", giay_id=g.id, so_to_nguyen=500,
               han=HOM_NAY + timedelta(days=6))
    # Máy GÁN ĐỦ, chỉ thiếu hạn SX.
    khong_han = _lenh(db, customer, ma="LSX-NOHAN", giay_id=g.id, so_to_nguyen=500, han=None)

    gom = svc.gom_de_nghi([
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": ro.id,
         "bai_ghep_id": None, "buoc_id": _buoc_dau(db, ro).id},
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": khong_han.id,
         "bai_ghep_id": None, "buoc_id": _buoc_dau(db, khong_han).id},
    ])
    assert "LSX-NOHAN" in gom["ghi_chu_ngay"]
    assert "chưa khai hạn sản xuất" in gom["ghi_chu_ngay"]
    assert "chưa gán máy" not in gom["ghi_chu_ngay"], "máy đã gán đủ — nói vậy là chỉ sai chỗ sửa"


def test_bai_ghep_co_ngay_nhung_thanh_vien_thieu_han_thi_noi_DUNG_ly_do(db, svc, customer):
    """🔴 Nguồn thứ BA của `dan_khong_suy_duoc`, chỉ có ở dòng BÀI GHÉP.

    Ở bài, `ngay_can` lấy từ thành viên CÓ mốc, còn cờ hỏng đến từ thành viên KHÁC. Nên bài vừa có
    ngày vừa đeo cờ — suy lý do bằng `bool(ngay_can)` sẽ ra "còn bước chưa gán máy" trong khi máy
    đã gán đủ cả hai thành viên, thứ thiếu là HẠN SX của một thành viên.
    """
    g = _giay(db)
    ro = _lenh(db, customer, ma="LSX-RO", giay_id=g.id, so_to_nguyen=500,
               han=HOM_NAY + timedelta(days=6))
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=500,
              han=HOM_NAY + timedelta(days=25))
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=500, han=None)  # thiếu HẠN
    bg = BaiGhep(ma="GB-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    db.commit()

    dong = {d["ma"]: d for d in _nhom(svc.can_doi(), g)["dong"]}
    assert dong["GB-001"]["ngay_can"] is not None, "bài VẪN có ngày (từ thành viên tốt)"
    assert "dan_khong_suy_duoc" in dong["GB-001"]["canh_bao"]

    gom = svc.gom_de_nghi([
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": ro.id,
         "bai_ghep_id": None, "buoc_id": _buoc_dau(db, ro).id},
        {"hang_loai": "giay", "hang_id": g.id, "lsx_id": None,
         "bai_ghep_id": bg.id, "buoc_id": dong["GB-001"]["buoc_id"]},
    ])
    assert "GB-001" in gom["ghi_chu_ngay"]
    assert "chưa khai hạn sản xuất" in gom["ghi_chu_ngay"]
    assert "chưa gán máy" not in gom["ghi_chu_ngay"], \
        "máy đã gán đủ cả hai thành viên — nói vậy là chỉ sai chỗ sửa"


def test_cat_danh_sach_lenh_mo_thi_NOI_ra_con_bao_nhieu(db, svc, customer):
    """Câu ⚠ này tồn tại để chống im lặng — cắt im lặng ngay trong nó là tự phản."""
    g = _giay(db)
    ro = _lenh(db, customer, ma="LSX-RO", giay_id=g.id, so_to_nguyen=100,
               han=HOM_NAY + timedelta(days=6))
    chon = [{"hang_loai": "giay", "hang_id": g.id, "lsx_id": ro.id,
             "bai_ghep_id": None, "buoc_id": _buoc_dau(db, ro).id}]
    for i in range(7):                       # 7 lệnh mờ > ngưỡng cắt 5
        l = _lenh(db, customer, ma=f"LSX-M{i}", giay_id=g.id, so_to_nguyen=100,
                  han=HOM_NAY + timedelta(days=20))
        b = _buoc_dau(db, l)
        b.may_id = None
        db.commit()
        chon.append({"hang_loai": "giay", "hang_id": g.id, "lsx_id": l.id,
                     "bai_ghep_id": None, "buoc_id": b.id})

    ghi = svc.gom_de_nghi(chon)["ghi_chu_ngay"]
    assert "và 2 lệnh nữa" in ghi, f"cắt 5/7 thì phải nói còn 2, thực tế: {ghi!r}"


def test_router_NOI_ghi_chu_ngay_vao_noi_dung_yeu_cau(client):
    """Router phải nối `ghi_chu_ngay` vào `content` của yêu cầu mua — kiểm HÀNH VI, không grep.

    `gom_de_nghi` dựng câu đó, nhưng nếu router thôi dùng thì cả mục "Kèm luôn" của lỗi ③ chết câm:
    service vẫn trả đúng, test service vẫn xanh, chỉ người mua là không bao giờ đọc được.

    Bơm cả HAI service qua `dependency_overrides` thay vì seed lệnh có dòng đỏ: cái đang kiểm là
    ĐOẠN NỐI ở router, không phải phép cộng trừ của bảng cân đối (đã có test riêng ở trên).
    Bản grep-nguồn trước đó bị bác đúng — nó xanh cả khi đảo điều kiện `if` lẫn khi gán vào biến
    chết, mà lại đỏ oan khi đổi f-string sang nối chuỗi.
    """
    from app.main import app
    from app.routers import ke_hoach_vat_tu as r

    ghi = "LSX-X cần 30/08 ⚠ Chưa suy được ngày cần cho LSX-Y"
    da_nhan: dict = {}

    class _KhoGia:
        def gom_de_nghi(self, chon):
            return {"lines": [{"hang_loai": "giay", "hang_id": 1, "item_name": "Giấy",
                               "unit": "kg", "quantity": 5}],
                    "needed_date": HOM_NAY, "related_document_code": "LSX-X, LSX-Y",
                    "ghi_chu_ngay": ghi}

    class _ThuMuaGia:
        def create_department_request(self, **kw):
            da_nhan.update(kw)
            return {"id": 1, "code": "YC-0001"}

    app.dependency_overrides[r.get_service] = lambda: _KhoGia()
    app.dependency_overrides[r.get_purchase_service] = lambda: _ThuMuaGia()
    try:
        resp = client.post(
            "/api/ke-hoach-vat-tu/de-nghi-mua",
            json={"dong": [{"hang_loai": "giay", "hang_id": 1}]},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201, resp.text
    assert ghi in (da_nhan.get("content") or ""), \
        f"nội dung yêu cầu mua phải mang ghi chú ngày, thực tế: {da_nhan.get('content')!r}"


def test_xem_truoc_de_nghi_mua_TRA_DU_DE_DIEN_FORM_va_KHONG_ghi_gi(client):
    """Cửa xem-trước phải trả đủ bộ để đổ vào form — và tuyệt đối KHÔNG lập phiếu.

    Đây là chỗ dễ hỏng nhất của đợt 20/08/2026: nút "Đề nghị mua ngay" đổi nghĩa từ "lập phiếu"
    sang "mở form". Nếu cửa này lỡ gọi `create_department_request` thì mỗi lần người dùng bấm rồi
    bấm Huỷ ở form vẫn đẻ ra một yêu cầu mua ma — không ai thấy, tới lúc thu mua mở màn mới lộ ra
    một đống phiếu trùng.
    """
    from app.main import app
    from app.routers import ke_hoach_vat_tu as r

    ghi = "LSX-X cần 30/08 ⚠ Chưa suy được ngày cần cho LSX-Y"
    da_tao: list = []

    class _KhoGia:
        def gom_de_nghi(self, chon):
            return {"lines": [{"hang_loai": "vat_tu", "hang_id": 7, "item_name": "Kẽm CTP",
                               "unit": "kem", "quantity": 15}],
                    "needed_date": HOM_NAY, "related_document_code": "LSX-X, LSX-Y",
                    "ghi_chu_ngay": ghi}

    class _ThuMuaGia:
        def can_create_department_request(self, actor):
            return True

        def create_department_request(self, **kw):
            da_tao.append(kw)
            return {"id": 1, "code": "YC-0001"}

    app.dependency_overrides[r.get_service] = lambda: _KhoGia()
    app.dependency_overrides[r.get_purchase_service] = lambda: _ThuMuaGia()
    try:
        resp = client.post(
            "/api/ke-hoach-vat-tu/de-nghi-mua/xem-truoc",
            json={"dong": [{"hang_loai": "vat_tu", "hang_id": 7}]},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert da_tao == [], "cửa xem-trước mà vẫn lập phiếu — bấm rồi huỷ là đẻ yêu cầu ma"
    assert body["related_document_type"] == "lsx"
    assert body["related_document_code"] == "LSX-X, LSX-Y"
    assert body["needed_date"] == HOM_NAY.isoformat()
    assert ghi in body["noi_dung"], f"thiếu ghi chú ngày: {body['noi_dung']!r}"
    assert body["lines"] == [{"hang_loai": "vat_tu", "hang_id": 7, "item_name": "Kẽm CTP",
                              "unit": "kem", "quantity": 15}]


def test_xem_truoc_de_nghi_mua_CHAN_nguoi_khong_duoc_lap_yeu_cau(client):
    """Không có bit tạo yêu cầu mua thì chặn NGAY ở cửa xem-trước, đừng dẫn tới form rồi mới 403."""
    from app.main import app
    from app.routers import ke_hoach_vat_tu as r

    class _KhoGia:
        def gom_de_nghi(self, chon):  # pragma: no cover - không được gọi tới
            raise AssertionError("chặn quyền phải xảy ra TRƯỚC khi tính toán")

    class _ThuMuaGia:
        def can_create_department_request(self, actor):
            return False

    app.dependency_overrides[r.get_service] = lambda: _KhoGia()
    app.dependency_overrides[r.get_purchase_service] = lambda: _ThuMuaGia()
    try:
        resp = client.post(
            "/api/ke-hoach-vat-tu/de-nghi-mua/xem-truoc",
            json={"dong": [{"hang_loai": "vat_tu", "hang_id": 7}]},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403, resp.text


def _admin_token() -> str:
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token

    s = SessionLocal()
    try:
        return create_access_token(str(UserRepository(s).get_by_username("admin").id))
    finally:
        s.close()


def test_is_rush_ra_toi_dong_va_ghi_chu(db, svc, customer):
    """Cờ GẤP phải đi hết chuỗi. Nửa vời (backend có, dòng không mang) là bẫy dự án đã dính 4 lần."""
    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-GAP", giay_id=g.id, so_to_nguyen=500,
              han=HOM_NAY + timedelta(days=6))
    l.is_rush = True
    db.commit()

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["is_rush"] is True

    gom = svc.gom_de_nghi([{"hang_loai": "giay", "hang_id": g.id, "lsx_id": l.id,
                            "bai_ghep_id": None, "buoc_id": _buoc_dau(db, l).id}])
    assert "(GẤP)" in gom["ghi_chu_ngay"]


# --- Lỗi ①, nhánh BÀI GHÉP ---------------------------------------------------


def test_bai_ghep_cung_vat_tu_o_hai_buoc_chung_cung_KHONG_gop_khoa(db, svc, customer):
    """🔴 Nhánh bài ghép của lỗi ① — plan ghi đích danh.

    `buoc_id` của dòng BÀI là `bai_ghep_cong_doan.id`, KHÁC không gian id với bước lệnh. Cặp
    `(lsx_id=None, bai_ghep_id=X)` trong khoá là thứ phân biệt hai không gian đó — nếu luật ấy sai
    thì bài ghép ăn cùng món ở hai bước chung cũng ra đơn mua một nửa, y như lệnh thường.
    """
    from app.models.bai_ghep_cong_doan import BaiGhepCongDoan
    from app.models.lsx import LsxCongDoanVatTu  # noqa: F401 — cùng module với bảng vật tư bước

    g = _giay(db)
    vt = _vat_tu(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    bg = BaiGhep(ma="GB-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    # HAI bước CHUNG của bài, cả hai cùng ăn một món.
    buocs = []
    for i in (1, 2):
        c = BaiGhepCongDoan(bai_ghep_id=bg.id, thu_tu=i, ten=f"Bước chung {i}",
                            so_luong_vao=100, so_luong_ra=100)
        db.add(c)
        db.flush()
        buocs.append(c)
    db.commit()
    for c in buocs:
        _khai_vat_tu_bai(db, c, vt, 5)

    nhom = next(x for x in svc.can_doi()["items"]
                if (x["hang_loai"], x["hang_id"]) == ("vat_tu", vt.id))
    assert len(nhom["dong"]) == 2
    assert {d["buoc_id"] for d in nhom["dong"]} == {buocs[0].id, buocs[1].id}
    assert all(d["lsx_id"] is None and d["bai_ghep_id"] == bg.id for d in nhom["dong"])

    gom = svc.gom_de_nghi([
        {"hang_loai": "vat_tu", "hang_id": vt.id, "lsx_id": None,
         "bai_ghep_id": bg.id, "buoc_id": buocs[0].id},
        {"hang_loai": "vat_tu", "hang_id": vt.id, "lsx_id": None,
         "bai_ghep_id": bg.id, "buoc_id": buocs[1].id},
    ])
    assert gom["lines"][0]["quantity"] == pytest.approx(10), "phải cộng cả hai bước chung"


def test_bai_GAP_khi_co_it_nhat_mot_thanh_vien_gap(db, svc, customer):
    """Bài chạy chung một lượt, không tách được — một thành viên gấp là cả bài gấp."""
    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    b.is_rush = True
    bg = BaiGhep(ma="GB-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    db.commit()

    dong = _nhom(svc.can_doi(), g)["dong"][0]
    assert dong["ma"] == "GB-001" and dong["is_rush"] is True


def test_vat_tu_hieu_luc_bai_ghep_khong_cong_lai_buoc_nguon_bi_override(
    db, svc, customer,
):
    """Bước chung tính một lần; bước riêng theo LSX; bước nguồn bị đè không còn hiệu lực."""
    from app.models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
    from app.models.lsx import LsxCongDoan

    g = _giay(db)
    vt = _vat_tu(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    b = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    a.trang_thai = TT_NHAP
    b.trang_thai = TT_CHO_BO_SUNG
    db.commit()
    nguon_a, nguon_b = _buoc_dau(db, a), _buoc_dau(db, b)
    rieng_a = LsxCongDoan(lsx_id=a.id, thu_tu=2, ten="Riêng A", nhom="finishing")
    rieng_b = LsxCongDoan(lsx_id=b.id, thu_tu=2, ten="Riêng B", nhom="finishing")
    db.add_all([rieng_a, rieng_b])
    bg = BaiGhep(ma="GB-EFFECTIVE", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    chung = BaiGhepCongDoan(
        bai_ghep_id=bg.id, thu_tu=1, ten="Bước chung", nhom="print",
        so_luong_vao=100, so_luong_ra=100,
    )
    db.add(chung)
    db.flush()
    db.add_all([
        BaiGhepCongDoanMap(
            bai_ghep_cong_doan_id=chung.id, lsx_id=a.id, lsx_step_key=nguon_a.step_key,
        ),
        BaiGhepCongDoanMap(
            bai_ghep_cong_doan_id=chung.id, lsx_id=b.id, lsx_step_key=nguon_b.step_key,
        ),
    ])
    db.commit()

    # Hai dòng 5 kg ở bước nguồn đã bị đè phải biến khỏi nhu cầu hiệu lực.
    _khai_vat_tu(db, nguon_a, vt, 5)
    _khai_vat_tu(db, nguon_b, vt, 5)
    # Hai bước riêng vẫn tính theo từng LSX; bước chung chỉ tính đúng một lần cho cả bài.
    _khai_vat_tu(db, rieng_a, vt, 2)
    _khai_vat_tu(db, rieng_b, vt, 3)
    _khai_vat_tu_bai(db, chung, vt, 7)

    nhom = next(x for x in svc.can_doi(include_lsx_ids={a.id, b.id})["items"]
                if (x["hang_loai"], x["hang_id"]) == ("vat_tu", vt.id))
    assert len(nhom["dong"]) == 3
    assert sum(d["nhu_cau"] for d in nhom["dong"]) == pytest.approx(12)
    assert {(d["lsx_id"], d["bai_ghep_id"], d["nhu_cau"]) for d in nhom["dong"]} == {
        (a.id, None, 2), (b.id, None, 3), (None, bg.id, 7),
    }

    hieu_luc = svc.vat_tu_hieu_luc(bg.id)
    assert hieu_luc["bai_ghep_id"] == bg.id
    tab = next(x for x in hieu_luc["items"]
               if (x["hang_loai"], x["hang_id"]) == ("vat_tu", vt.id))
    assert tab["tong_can"] == pytest.approx(12), "phải tính lại sau khi lọc khỏi tổng toàn xưởng"
    assert {(d["pham_vi"], d["lsx_id"], d["nhu_cau"]) for d in tab["dong"]} == {
        ("lsx", a.id, 2), ("lsx", b.id, 3), ("bai_ghep", None, 7),
    }
    assert {
        (d["pham_vi"], d["gang_step_key"]) for d in tab["dong"]
    } == {("lsx", None), ("bai_ghep", chung.step_key)}


# --- VẾT MUA (chip "đang có phiếu chạy") --------------------------------------


def test_ycmh_moi_de_nghi_hien_ten_phieu_ma_KHONG_doi_mot_con_so_nao(db, svc, customer):
    """Câu hỏi 20/08/2026: *"sao biết được cái nào đang yêu cầu mua"*.

    Bấm "Mua" trên bảng cân đối chỉ đẻ ra YCMH; engine cố ý KHÔNG cộng nó vào tồn (chưa ai duyệt,
    hàng chưa chắc có). Nên trước đây "đã đề nghị" và "chưa ai đụng vào" vẽ ĐỎ giống hệt nhau và
    người tiếp theo bấm Mua chồng lên. `phieu_mua` là NHÃN — phải hiện tên phiếu mà tuyệt đối
    không được nhích một con số nào của bảng, nếu không nhãn hoá thành lời hứa có hàng.
    """
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    truoc = _nhom(svc.can_doi(), g)
    assert truoc["phieu_mua"] == []
    assert truoc["dong"][0]["trang_thai"] == "do"

    yc = _ycmh(db, hang=("giay", g.id), so_luong=200)

    sau = _nhom(svc.can_doi(), g)
    assert sau["phieu_mua"] == [
        {"ma": yc.code, "loai": "ycmh", "trang_thai": DPR_OPEN, "ngay_ve": None},
    ]
    # Số học không đổi một ly: vẫn đỏ, vẫn thiếu đúng ngần ấy, vẫn còn nút Mua.
    assert sau["dong"][0]["trang_thai"] == "do"
    assert sau["dong"][0]["thieu"] == pytest.approx(truoc["dong"][0]["thieu"])
    assert sau["tong_can"] == pytest.approx(truoc["tong_can"])
    assert sau["ton"] == pytest.approx(truoc["ton"])


def test_vet_mua_xep_chac_truoc_long_sau(db, svc, customer):
    """Chip vật tư chỉ đủ chỗ MỘT dòng ⇒ phần tử đầu phải là lời hứa CHẮC nhất.

    Xếp ngược lại thì chip báo "mới đề nghị" trong khi hàng đã nằm trên xe — tin xấu che tin tốt.
    """
    g = _giay(db)
    cho_duyet = _phieu_mua(db, hang=("giay", g.id), so_luong=10, ngay_ve=None, status=PR_PENDING)
    khong_ngay = _phieu_mua(db, hang=("giay", g.id), so_luong=10, ngay_ve=None)
    co_ngay = _phieu_mua(db, hang=("giay", g.id), so_luong=10, ngay_ve=MAI)
    yc = _ycmh(db, hang=("giay", g.id), so_luong=10, status=DPR_PENDING_APPROVAL)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    nhom = _nhom(svc.can_doi(), g)
    assert [v["ma"] for v in nhom["phieu_mua"]] == [
        co_ngay.code,      # đã duyệt + có ngày về  → chắc nhất
        khong_ngay.code,   # đã duyệt, NCC chưa hẹn ngày
        cho_duyet.code,    # PMH còn nằm chờ duyệt
        yc.code,           # mới là đề nghị của bộ phận → lỏng nhất
    ]
    assert [v["loai"] for v in nhom["phieu_mua"]] == ["pmh", "pmh", "pmh", "ycmh"]
    assert nhom["phieu_mua"][0]["ngay_ve"] == MAI


def test_phieu_nhan_du_va_phieu_khep_KHONG_con_la_viec_dang_chay(db, svc, customer):
    """Nhãn nói "đang có người lo" ⇒ phiếu đã xong phải rụng khỏi danh sách.

    Giữ lại thì mặt hàng nào từng mua một lần cũng đeo nhãn vĩnh viễn, và nhãn hết nghĩa.
    """
    g = _giay(db)
    p = _phieu_mua(db, hang=("giay", g.id), so_luong=100, ngay_ve=HOM_NAY)
    p.lines[0].received_quantity = 100          # về đủ rồi, hàng nằm trong kho
    db.commit()
    _ycmh(db, hang=("giay", g.id), so_luong=50, status="done")
    _ycmh(db, hang=("giay", g.id), so_luong=50, status="cancelled")
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    assert _nhom(svc.can_doi(), g)["phieu_mua"] == []


def test_dong_mua_khong_gan_mat_hang_thi_khong_deo_nhan(db, svc, customer):
    """Ghép ngược bằng TÊN hàng là đoán. Đoán trúng nhầm lô giấy khác thì nhãn nói dối."""
    g = _giay(db)
    _phieu_mua(db, hang=None, so_luong=100, ngay_ve=MAI)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)

    assert _nhom(svc.can_doi(), g)["phieu_mua"] == []


def test_vat_tu_co_CONG_THUC_LUONG_van_lay_SO_DA_CHOT_o_buoc_khong_tinh_lai(db, svc, customer):
    """Vật tư khai công thức lượng ⇒ bảng cân đối DÙNG số của bước, KHÔNG chạy lại công thức.

    Hỏng thật 20/08/2026 (LSX26-0020): kẽm/mực/màng đều khai công thức lượng, BOM của lệnh ghi
    10 bản kẽm · 100 kg mực · 91.000 m² màng, còn kế hoạch vật tư hiện "0 · Chưa rõ ĐVT" cho cả
    năm dòng ⇒ độ sẵn sàng 0%, không bật được giữ chỗ, không xếp lịch được.

    Vì sao: `_ve_goc` chạy lại công thức bằng `ngu_canh_lenh(qc)`, mà `qc` chỉ được dựng cho GIẤY
    (`_quy_cach_cua` trả None cho loại khác) nên cả 16 biến đều 0 ⇒ "Chưa biết so_kem".
    Số của bước mới là số đúng: `LsxService._luong_vat_tu` tính nó bằng ngữ cảnh có cả `sl_vao`
    của chính bước — thứ mà tầng lệnh không bao giờ có (`sl_vao` là biến TẦNG BƯỚC).
    """
    g = _giay(db)
    kem = _vat_tu(db, ma="VT-KEM", ten="Bản kẽm khổ 102", don_vi="kem")
    kem.cong_thuc_luong = "so_kem"                  # biến CÓ ở tầng lệnh
    mang = _vat_tu(db, ma="VT-MANG", ten="Màng cán bóng", don_vi="m2")
    mang.cong_thuc_luong = "sl_vao * 1000"          # biến CHỈ có ở tầng bước
    db.commit()

    l = _lenh(db, customer, ma="LSX-CTL-VT", giay_id=g.id, so_to_nguyen=241, han=MAI)
    l.quy_cach_json = {**l.quy_cach_json, "so_kem": 5}
    db.commit()
    buoc = _buoc_dau(db, l)
    _khai_vat_tu(db, buoc, kem, 5, dvt="kem")
    _khai_vat_tu(db, buoc, mang, 91_000, dvt="m2")

    bang = svc.can_doi()
    for vt, cho_doi in ((kem, 5), (mang, 91_000)):
        dong = next(n for n in bang["items"]
                    if (n["hang_loai"], n["hang_id"]) == ("vat_tu", vt.id))["dong"][0]
        assert "khong_doi_chieu_duoc" not in dong["canh_bao"], dong.get("ly_do_canh_bao")
        assert dong["nhu_cau"] == pytest.approx(cho_doi)
