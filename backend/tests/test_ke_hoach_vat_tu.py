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
from app.models.lsx import TT_SAN_SANG, Lsx, LsxCongDoan
from app.models.may_thiet_bi import MayThietBi
from app.models.order import Order, OrderLine
from app.models.purchase import (
    PR_PURCHASED,
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
    """Giấy 65×86 định lượng 150 ⇒ 1 tờ = 0,15 × 0,86 × 0,65 = 0,08385 kg."""
    g = GiayNguyen(ma=ma, ten=f"Giấy {ma}", gsm=gsm, kho_dai=dai, kho_rong=rong,
                   don_vi_gia=don_vi)
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


def _phieu_mua(db, *, hang, so_luong, ngay_ve, unit="kg") -> PurchaseRequest:
    p = PurchaseRequest(code=f"PMH-{db.query(PurchaseRequest).count() + 1}",
                        status=PR_PURCHASED, expected_receipt_date=ngay_ve)
    db.add(p)
    db.flush()
    db.add(PurchaseRequestLine(
        purchase_request_id=p.id, item_name="Giấy mua",
        hang_loai=hang[0] if hang else None, hang_id=hang[1] if hang else None,
        unit=unit, quantity=so_luong, expected_unit_price=1,
    ))
    db.commit()
    return p


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


def test_hang_ve_sau_ngay_can_thi_van_do(db, svc, customer):
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000,
          han=HOM_NAY + timedelta(days=2))
    _phieu_mua(db, hang=("giay", g.id), so_luong=500, ngay_ve=HOM_NAY + timedelta(days=30))

    assert _nhom(svc.can_doi(), g)["dong"][0]["trang_thai"] == "do"


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


# ── Dòng CÔNG CỤ (khuôn): đọc CỜ danh mục, KHÔNG dò tên công đoạn ───────────────
# Chốt chặn này trước nằm ở `test_lsx_service` (checklist "thiếu khuôn" của lệnh). Checklist đó
# đã bỏ 11/08/2026 cùng ô gán khuôn ở màn Kế hoạch, nhưng CÙNG cặp cờ vẫn quyết định bảng cân
# đối có sinh dòng khuôn hay không — nên luật phải được ghim lại ở đây.
#
# Công đoạn là danh mục ĐỘNG: người dùng khai lúc chạy, đặt tên gì cũng được ("Ép kim",
# "Die-cut", "Bế nổi"…). Dò chữ "bế" trong tên sai cả hai chiều.
def _cong_doan_dung_cu(db, *, ma: str, ten: str, can_khuon: bool, loai: str | None = "khuon_be"):
    from app.models.cong_doan import CongDoan

    cd = CongDoan(
        ma=ma, ten=ten, nhom="finishing", don_vi_vao="to", don_vi_ra="to",
        requires_tooling=can_khuon, tooling_type=loai if can_khuon else None,
    )
    db.add(cd)
    db.flush()
    return cd


def _gan_buoc(db, lsx: Lsx, cd, ten: str) -> None:
    db.add(LsxCongDoan(
        lsx_id=lsx.id, thu_tu=9, ten=ten, cong_doan_id=cd.id, loai_buoc="may",
        may_id=_may(db).id, don_vi_vao="to", don_vi_ra="to",
        so_luong_vao=100, so_luong_ra=100,
    ))
    db.commit()


def test_dong_khuon_theo_CO_danh_muc_du_ten_khong_co_chu_be(db, svc, customer):
    """Tên "Ép kim" — không có chữ "bế" — nhưng danh mục khai CẦN khuôn ⇒ vẫn phải có dòng khuôn."""
    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-EPKIM", giay_id=g.id, so_to_nguyen=100)
    _gan_buoc(db, l, _cong_doan_dung_cu(db, ma="CD-EP", ten="Ép kim", can_khuon=True,
                                        loai="khuon_ep"), "Ép kim")

    nhoms = [n for n in svc.can_doi()["items"] if n.get("loai_nhom") == "cong_cu"]
    assert nhoms, "công đoạn khai requires_tooling=True phải sinh dòng công cụ"
    assert any(d["ma"] == "LSX-EPKIM" for n in nhoms for d in n["dong"])


def test_ten_co_chu_be_nhung_danh_muc_noi_khong_can_thi_KHONG_de_ra_dong_khuon(db, svc, customer):
    """Chiều ngược lại: "Kiểm bế" có chữ "bế" nhưng không cần khuôn ⇒ không được báo oan."""
    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-KIEMBE", giay_id=g.id, so_to_nguyen=100)
    _gan_buoc(db, l, _cong_doan_dung_cu(db, ma="CD-KIEM", ten="Kiểm bế", can_khuon=False),
              "Kiểm bế")

    nhoms = [n for n in svc.can_doi()["items"] if n.get("loai_nhom") == "cong_cu"]
    assert not any(d["ma"] == "LSX-KIEMBE" for n in nhoms for d in n["dong"])


def test_hai_buoc_can_khuon_thi_RA_HAI_DONG_theo_tung_khuon(db, svc, customer):
    """Hộp vừa Bế vừa Ép nhũ = hai khuôn khác nhau, hai ngày cần khác nhau.

    Trước 11/08/2026 khuôn gán ở CẤP LỆNH nên chỉ giữ được một cái và bảng cân đối chỉ lấy bước
    ĐẦU TIÊN cần khuôn — khuôn ép về muộn vẫn báo xanh vì đã canh theo ngày bế.
    """
    from app.models.khuon_be import KhuonBe

    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-2KHUON", giay_id=g.id, so_to_nguyen=100)
    kb = KhuonBe(ma="KB-01", ten="Khuôn bế hộp")
    ke = KhuonBe(ma="KE-01", ten="Khuôn ép nhũ")
    db.add_all([kb, ke])
    db.flush()

    cd_be = _cong_doan_dung_cu(db, ma="CD-BE2", ten="Die-cut", can_khuon=True, loai="khuon_be")
    cd_ep = _cong_doan_dung_cu(db, ma="CD-EP2", ten="Ép nhũ", can_khuon=True, loai="khuon_ep")
    db.add(LsxCongDoan(lsx_id=l.id, thu_tu=8, ten="Die-cut", cong_doan_id=cd_be.id,
                       loai_buoc="may", may_id=_may(db).id, khuon_be_id=kb.id,
                       don_vi_vao="to", don_vi_ra="to", so_luong_vao=100, so_luong_ra=100))
    db.add(LsxCongDoan(lsx_id=l.id, thu_tu=9, ten="Ép nhũ", cong_doan_id=cd_ep.id,
                       loai_buoc="may", may_id=_may(db).id, khuon_be_id=ke.id,
                       don_vi_vao="to", don_vi_ra="to", so_luong_vao=100, so_luong_ra=100))
    db.commit()

    nhoms = [n for n in svc.can_doi()["items"] if n.get("loai_nhom") == "cong_cu"]
    theo_ten = {n["hang_ten"]: n for n in nhoms}
    assert "Khuôn bế hộp" in theo_ten and "Khuôn ép nhũ" in theo_ten, theo_ten.keys()
    # Mỗi khuôn một dòng, và dòng nào cũng chỉ đích danh BƯỚC dùng nó.
    assert [d["ten_viec"] for d in theo_ten["Khuôn bế hộp"]["dong"]] == ["Die-cut"]
    assert [d["ten_viec"] for d in theo_ten["Khuôn ép nhũ"]["dong"]] == ["Ép nhũ"]


def test_buoc_chua_gan_khuon_van_gom_rieng_va_bao_do(db, svc, customer):
    """Chưa gán khuôn thì vẫn phải hiện (đỏ) — im lặng thì tới ngày bế mới biết là không có khuôn."""
    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-CHUAGAN", giay_id=g.id, so_to_nguyen=100)
    cd = _cong_doan_dung_cu(db, ma="CD-BE3", ten="Bế", can_khuon=True, loai="khuon_be")
    _gan_buoc(db, l, cd, "Bế")

    nhom = next(n for n in svc.can_doi()["items"]
                if n.get("loai_nhom") == "cong_cu" and n["hang_id"] == 0)
    assert nhom["hang_ten"] == "Chưa gán khuôn"
    assert nhom["so_dong_do"] == 1
