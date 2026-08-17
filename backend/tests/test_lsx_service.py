"""Lệnh sản xuất (LSX) — service-level tests.

Luồng thật: đơn từ báo giá → thu đủ cọc → chốt → Sale "Chuyển xuống sản xuất" → Kế hoạch preview
→ tạo lệnh → sửa routing → đánh dấu sẵn sàng. Mỗi DÒNG ĐƠN đúng 1 lệnh, lệnh ngang hàng.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from types import SimpleNamespace

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan, CongDoanDauViec
from app.models.customer import Customer
from app.models.department import Department
from app.models.lsx import (
    TT_CHO_BO_SUNG,
    TT_DA_LAP_KE_HOACH,
    TT_NHAP,
    TT_SAN_SANG,
    LsxCongDoan,
)
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


def _ptg_sach(db, *, so_cuon=2_000, so_trang=160, trang_moi_tay=16) -> PhieuTinhGia:
    """Phiếu tính giá một cuốn SÁCH: In → Gấp tay → Bắt tay+vào keo → Xén 3 mặt.

    `Bắt tay + vào keo` là bước duy nhất đổi đơn vị `to → cai` — chỗ GOM `so_tay` tờ thành MỘT
    cuốn (đúng như migration `0148` khai cho `CD-0008`). Gấp tay giữ `to → to` vì nó gấp cả tờ,
    một tờ thành một tay.
    """
    giay = GiayNguyen(ma="G-FORD70", ten="Ford 70", gsm=70, don_gia=22_000, don_vi_gia="tan",
                      cong_thuc_gia="to_nguyen * dai_nguyen * rong_nguyen * dinh_luong * don_gia / 1000")
    db.add(giay)
    to_id = _to_san_xuat(db).id
    may = _may_in(db)
    cds = [
        CongDoan(ma="CD-IN-S", ten="In offset", nhom="print", cong_thuc_gia="so_luong * don_gia",
                 department_id=to_id, don_vi_vao="to", don_vi_ra="to"),
        CongDoan(ma="CD-GAP-S", ten="Gấp tay sách", nhom="finishing",
                 cong_thuc_gia="so_luong * don_gia", department_id=to_id,
                 don_vi_vao="to", don_vi_ra="to"),
        CongDoan(ma="CD-KEO-S", ten="Bắt tay + vào keo", nhom="finishing",
                 cong_thuc_gia="so_luong * don_gia", department_id=to_id,
                 don_vi_vao="to", don_vi_ra="cai"),
        # Hao 50 CUỐN ở bước xén — để kiểm nó lội ngược qua cầu ra đúng 500 TỜ.
        CongDoan(ma="CD-XEN-S", ten="Xén 3 mặt", nhom="finishing",
                 cong_thuc_gia="so_luong * don_gia", department_id=to_id,
                 don_vi_vao="cai", don_vi_ra="cai", kieu_bu_hao="co_dinh", so_to_bu_hao=50),
    ]
    db.add_all(cds)
    db.flush()

    p = PhieuTinhGia(ma="PTG-SACH-0001", ten_san_pham="Sách A5", so_luong=so_cuon)
    ruot = PhieuThanhPhan(
        thu_tu=0, ten="Ruột sách A5", so_luong=so_cuon, don_vi_tinh="cuốn",
        dai_thanh_pham=210, rong_thanh_pham=148,
        so_trang=so_trang, trang_moi_tay=trang_moi_tay,
        giay_id=giay.id, kho_nguyen_dai=860, kho_nguyen_rong=650,
        kho_in_dai=860, kho_in_rong=650, so_mau_a=1, so_mau_b=1, quy_cach_in="hai_mat",
        may_id=may.id,
    )
    for i, cd in enumerate(cds):
        ruot.thanh_phams.append(PhieuThanhPham(thu_tu=i, cong_doan_id=cd.id, ten=cd.ten, don_gia=50))
    p.thanh_phans.append(ruot)
    db.add(p)
    db.commit()
    return p


def test_sach_di_het_luong_don_den_lenh(db, orders, lsx_svc, admin, customer):
    """SÁCH đi hết luồng đơn → tính giá → lệnh: số giấy phải nhân lên theo SỐ TAY.

    Ca thật, không phải chuỗi tự dựng. Đúng bộ số của panel bù hao bên Tính giá:
    2.000 cuốn × 10 tay = 20.000 tờ, cộng 50 cuốn hao ở bước xén lội ngược qua cầu thành 500 tờ
    → 20.500 tờ. Code cũ lấy `so_con` (bình bài = 16) nên bước in chỉ nhận 128 tờ — hụt 160 lần,
    và giờ máy in cũng hụt theo (3 phút thay vì hơn 8 tiếng), tức xếp lịch cũng vỡ.
    """
    ptg = _ptg_sach(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)

    assert lsx_svc._he_so_cau(lsx)[("to", "cai")] == pytest.approx(0.1)   # 10 tờ = 1 cuốn
    assert lsx.so_to_ke_hoach == 20_500

    buoc = {c.ten: c for c in lsx.cong_doans}
    keo = buoc["Bắt tay + vào keo"]
    assert (float(keo.so_luong_vao), float(keo.so_luong_ra)) == (20_500, 2_050)
    assert (keo.don_vi_vao, keo.don_vi_ra) == ("to", "cai")
    xen = buoc["Xén 3 mặt"]
    assert (float(xen.so_luong_vao), float(xen.so_luong_ra)) == (2_050, 2_000)
    assert float(xen.hao_hut) == 50
    # Hao 50 CUỐN ở cuối chuỗi lội ngược qua cầu = 500 TỜ ở bước in. Cộng hao phẳng thì chỉ ra 50.
    assert float(buoc["In offset"].so_luong_vao) == 20_500

    # Giờ máy ăn theo `so_luong_vao`: hệ số sai là xếp lịch sai theo, không riêng số giấy.
    assert _tl(buoc["In offset"], db)["chiem_may_phut"] > 400   # 20.500 tờ ÷ 5.000 tờ/giờ


def _ptg_hinh(db, *, ma: str, buoc: list[tuple[str, str, str, str]],
              kho_nguyen=(860, 650), kho_in=(860, 650), sl=5_000) -> PhieuTinhGia:
    """Phiếu tính giá với HÌNH ROUTING chỉ định — `buoc` là list `(mã, tên, đv vào, đv ra)`.

    Dùng để đối chiếu hai nguồn biến trên nhiều hình chuỗi khác nhau, không chỉ hình quen thuộc.
    Bước cuối luôn mang hao cố định 40 để kiểm nó lội ngược qua cầu ra đúng số tờ ở hai bên.

    Máy RIÊNG cho mỗi hình, khổ tối đa = `kho_in`: số mảnh xả tính theo khổ giấy MÁY CHẠY
    (`kho_may` = `may.kho_max_*`), KHÔNG theo khổ tờ in. Dùng chung máy 1020×720 thì giấy 860×650
    không cắt ra nổi một mảnh máy nhận ⇒ `_fit` = 0 ⇒ xả = 1, và ca "có xả" hoá ra không xả.
    """
    giay = GiayNguyen(ma=f"G-{ma}", ten=f"Giấy {ma}", gsm=300, don_gia=25_000, don_vi_gia="tan",
                      cong_thuc_gia="to_nguyen * dai_nguyen * rong_nguyen * dinh_luong * don_gia / 1000")
    db.add(giay)
    to_id = _to_san_xuat(db).id
    cds = []
    for i, (cd_ma, ten, dv_vao, dv_ra) in enumerate(buoc):
        cuoi = i == len(buoc) - 1
        cds.append(CongDoan(
            ma=f"{cd_ma}-{ma}", ten=ten, nhom="print" if "In" in ten else "finishing",
            cong_thuc_gia="so_luong * don_gia", department_id=to_id,
            don_vi_vao=dv_vao, don_vi_ra=dv_ra,
            kieu_bu_hao="co_dinh" if cuoi else None, so_to_bu_hao=40 if cuoi else None,
        ))
    db.add_all(cds)
    db.flush()

    may = MayThietBi(ma=f"MAY-{ma}", ten=f"Máy {ma}", loai_may="press_offset_sheet",
                     toc_do=5_000, don_vi_toc_do="to_gio",
                     kho_max_dai=kho_in[0], kho_max_rong=kho_in[1])
    db.add(may)
    db.flush()

    p = PhieuTinhGia(ma=f"PTG-{ma}", ten_san_pham=f"SP {ma}", so_luong=sl)
    tpn = PhieuThanhPhan(
        thu_tu=0, ten=f"SP {ma}", so_luong=sl, don_vi_tinh="cái",
        dai_thanh_pham=86, rong_thanh_pham=54,
        giay_id=giay.id, kho_nguyen_dai=kho_nguyen[0], kho_nguyen_rong=kho_nguyen[1],
        kho_in_dai=kho_in[0], kho_in_rong=kho_in[1],
        so_mau_a=4, so_mau_b=1, quy_cach_in="hai_mat", may_id=may.id,
    )
    for i, cd in enumerate(cds):
        tpn.thanh_phams.append(PhieuThanhPham(thu_tu=i, cong_doan_id=cd.id, ten=cd.ten, don_gia=0))
    p.thanh_phans.append(tpn)
    db.add(p)
    db.commit()
    return p


@pytest.mark.parametrize("ten_hinh,buoc,kho_in", [
    # Có bước XẢ GIẤY: `to_nguyen` tách khỏi `to_dau_vao`, đọc ở bước xả chứ không chia mảnh.
    ("xa-giay", [("CD-XA", "Xả giấy", "to_nguyen", "to"), ("CD-IN", "In offset", "to", "to"),
                 ("CD-BE", "Bế", "to", "cai")], (430, 650)),
    # KHÔNG có bước xả nhưng khổ in nhỏ hơn khổ nguyên → cả hai bên phải tự chia mảnh xả.
    ("chia-manh", [("CD-IN", "In offset", "to", "to"), ("CD-BE", "Bế", "to", "cai")], (430, 650)),
    # Chuỗi KẾT Ở `con`: đích của chuỗi không phải SL đặt — hai engine phải cùng quy đổi.
    ("ket-o-con", [("CD-IN", "In offset", "to", "to"), ("CD-BE", "Bế", "to", "con")], (860, 650)),
    # Đường DÀI qua `con`: tích hai cầu phải bằng đúng cầu tắt `to → cai`.
    ("qua-con", [("CD-IN", "In offset", "to", "to"), ("CD-BE", "Bế", "to", "con"),
                 ("CD-DG", "Đóng gói", "con", "cai")], (860, 650)),
])
def test_hai_nguon_khop_tren_moi_hinh_routing(db, orders, lsx_svc, admin, customer,
                                              ten_hinh, buoc, kho_in):
    """Cùng bộ 16 biến, hai nguồn số, chạy qua BỐN hình chuỗi khác nhau — phải khớp từng cái.

    Ca sách (`test_hai_nguon_bien_ra_cung_so_khi_lenh_chua_ai_sua`) chỉ phủ hình `to → tay → cai`
    không xả giấy. Bốn hình ở đây là bốn chỗ hai engine dễ rẽ nhánh khác nhau nhất: đọc `to_nguyen`
    ở bước xả hay tự chia mảnh · đích chuỗi khi kết ở `con` · tích hai cầu qua `con`.
    """
    from app.services.bien_cong_thuc import MA_NGU_CANH_PHIEU, ngu_canh_lenh, quy_cach_bien
    from app.services.thanh_phan_engine import compute_phieu
    from app.services.tinh_gia_service import _resolve_thanh_phan

    ptg = _ptg_hinh(db, ma=ten_hinh.upper().replace("-", ""), buoc=buoc,
                    kho_nguyen=(860, 650), kho_in=kho_in)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)

    resolved = _resolve_thanh_phan(db, ptg.thanh_phans[0])
    resolved["so_luong"] = lsx.so_luong_dat
    phieu = compute_phieu(so_luong=lsx.so_luong_dat, thanh_phans=[resolved],
                          bu_hao_rows=lsx_svc._bu_hao_rows())["meta"]["components"][0]
    lenh = ngu_canh_lenh(quy_cach_bien(lsx))
    doi = {"so_tp": "con", "so_luong": "so_luong", "to_dau_vao": "to_dau_vao",
           "to_sau_in": "to_sau_in", "to_nguyen": "to_nguyen", "so_kem": "so_kem",
           "so_mau_pha": "so_mau_pha"}
    for bien, o_phieu in doi.items():
        assert lenh[bien] == pytest.approx(float(phieu[o_phieu])), (
            f"[{ten_hinh}] `{bien}`: lệnh {lenh[bien]} ≠ phiếu {phieu[o_phieu]}")
    # Số phải THẬT — cùng bằng 0 rồi khoe khớp thì test này vô nghĩa.
    assert lenh["to_dau_vao"] > 0 and lenh["to_nguyen"] > 0
    assert not [k for k in MA_NGU_CANH_PHIEU if k != "so_mau_pha" and not lenh[k]], \
        f"[{ten_hinh}] còn biến bằng 0 ngoài số màu pha"
    if "xa" in ten_hinh or "chia" in ten_hinh:
        assert lenh["to_nguyen"] < lenh["to_dau_vao"], "khổ in nửa khổ nguyên thì tờ nguyên phải ít hơn"


def test_hai_nguon_bien_ra_cung_so_khi_lenh_chua_ai_sua(db, orders, lsx_svc, admin, customer):
    """MỘT bộ 16 biến, HAI nguồn số — lệnh chưa ai sửa thì hai nguồn phải trùng khít.

    Công thức người dùng gõ (`1 tờ = dinh_luong * dai_in * rong_in` kg) chạy ở hai nơi: ở phiếu
    tính giá thì `thanh_phan_engine.ngu_canh_phieu` bơm số, ở lệnh thì `quy_cach_bien` +
    `ngu_canh_lenh` bơm. Hai đường bơm là hai chỗ để lệch, mà lệch ở đây nghĩa là báo giá 20.500 tờ
    còn lệnh đi mua 2.050 tờ — không ai biết bên nào đúng.

    Rủi ro có thật, không phải giả định: chuỗi bù hao ngược cũng có HAI bản cài
    (`bu_hao_engine.chuoi_nguoc_dv` cho phiếu · `lsx_service.tinh_nguoc_routing` cho lệnh). Chúng
    dùng chung `hao_buoc` · `dich_chuoi` · cờ trạm nên ĐÁNG LẼ khớp; test này là chỗ chứng minh.

    Lấy ca SÁCH vì nó đi đường dài nhất (tờ → tay → cuốn) — ca dễ lệch nhất. Fixture để nguyên
    `don_gia=50` trên các dòng công đoạn: bước cấu hình danh mục phải chạy BẤT KỂ dòng có đơn giá
    phẳng hay không (xem ca canh ở cuối hàm).
    """
    from app.services.bien_cong_thuc import ngu_canh_lenh, quy_cach_bien
    from app.services.thanh_phan_engine import compute_phieu
    from app.services.tinh_gia_service import _resolve_thanh_phan

    ptg = _ptg_sach(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)

    # Bên PHIẾU: đúng đường `tao` chạy — engine thuần với SL ép theo đơn.
    resolved = _resolve_thanh_phan(db, ptg.thanh_phans[0])
    resolved["so_luong"] = lsx.so_luong_dat
    phieu = compute_phieu(so_luong=lsx.so_luong_dat, thanh_phans=[resolved],
                          bu_hao_rows=lsx_svc._bu_hao_rows())["meta"]["components"][0]

    # Bên LỆNH: qua đúng cửa mà quy đổi động đi.
    lenh = ngu_canh_lenh(quy_cach_bien(lsx))

    for bien, o_phieu in (("so_luong", "so_luong"), ("so_tp", "con"),
                          ("to_dau_vao", "to_dau_vao"), ("to_sau_in", "to_sau_in"),
                          ("to_nguyen", "to_nguyen"), ("so_kem", "so_kem"),
                          ("so_mau_pha", "so_mau_pha")):
        assert lenh[bien] == pytest.approx(float(phieu[o_phieu])), (
            f"biến `{bien}` lệch giữa hai nguồn: lệnh {lenh[bien]} ≠ phiếu {phieu[o_phieu]}")

    # Số phải là số THẬT, không phải cùng bằng 0 rồi khoe khớp.
    assert lenh["to_dau_vao"] == 20_500 and lenh["so_luong"] == 2_000
    # Khổ + định lượng đi từ ảnh chụp, cùng đơn vị MÉT / kg·m⁻² với bên phiếu.
    assert lenh["dai_nguyen"] == pytest.approx(0.86) and lenh["dinh_luong"] == pytest.approx(0.07)

    # ĐƠN GIÁ PHẲNG trên dòng KHÔNG được làm mất bù hao. Tới 11/08/2026 nó có làm: điều kiện
    # `if not don_gia` ở `_resolve_thanh_phan` bỏ qua cấu hình danh mục, bước rơi khỏi dòng giấy,
    # phiếu ra 20.000 tờ trong khi lệnh ra 20.500 — báo giá hụt 500 tờ giấy, im lặng.
    for row in ptg.thanh_phans[0].thanh_phams:
        row.don_gia = 0
    db.commit()
    khong_gia = compute_phieu(so_luong=lsx.so_luong_dat,
                              thanh_phans=[{**_resolve_thanh_phan(db, ptg.thanh_phans[0]),
                                            "so_luong": lsx.so_luong_dat}],
                              bu_hao_rows=lsx_svc._bu_hao_rows())["meta"]["components"][0]
    assert khong_gia["to_dau_vao"] == phieu["to_dau_vao"] == 20_500, (
        "có hay không có đơn giá phẳng thì số giấy phải như nhau — giá và bù hao là hai chuyện")


def test_cau_to_sang_cai_sach_gap_tay_nguoc_chieu_voi_cat_roi(db, lsx_svc):
    """Sách gấp tay: NHIỀU tờ mới gom thành MỘT cuốn → hệ số `1/so_tay`, nhỏ hơn 1.

    Đây là chỗ tầng lệnh từng lệch với tính giá: nó trả thẳng `so_con` cho mọi loại hàng, nên lệnh
    sách cấp thiếu giấy đúng `con × so_tay` lần — một chiều, không bao giờ thừa, và không ai báo.
    Migration `0148` đã dựng sẵn cầu `to → cai` cho bước "Bắt tay + vào keo"; thiếu đúng hệ số.
    """
    from app.models.lsx import Lsx

    # Sách A5 160 trang, tay 16 → 10 tay = 10 TỜ cho mỗi cuốn. `so_con` để 8 cho chắc: kiểu gấp
    # tay thì `con` KHÔNG được vào công thức giấy, có đặt bao nhiêu cũng không đổi hệ số.
    sach = Lsx(so_con=8, quy_cach_json={"so_trang": 160, "trang_moi_tay": 16, "so_manh_xa": 1})
    assert lsx_svc._he_so_cau(sach)[("to", "cai")] == pytest.approx(0.1)

    # Hàng CẮT RỜI đi chiều ngược lại: một tờ ra `con` cái. Nhánh mới không được đụng vào ca này.
    the = Lsx(so_con=99, quy_cach_json={"so_manh_xa": 1})
    assert lsx_svc._he_so_cau(the)[("to", "cai")] == 99.0

    # `trang_moi_tay = 1` là hàng thường, không phải sách một tay.
    mot_tay = Lsx(so_con=4, quy_cach_json={"so_trang": 4, "trang_moi_tay": 1})
    assert lsx_svc._he_so_cau(mot_tay)[("to", "cai")] == 4.0


def test_chuoi_nguoc_sach_can_nhieu_to_hon_so_cuon(db, lsx_svc):
    """Hệ quả trên chuỗi ngược: 2.000 cuốn sách 10 tay phải ra 20.000 tờ, không phải 2.000/con."""
    from app.models.lsx import Lsx, LsxCongDoan

    sach = Lsx(
        so_luong_dat=2_000, so_con=8,
        quy_cach_json={"so_trang": 160, "trang_moi_tay": 16, "so_manh_xa": 1},
    )
    # Chuỗi tối thiểu có ranh giới tờ↔cuốn, đúng như `0148` khai cho khâu sách.
    sach.cong_doans = [
        LsxCongDoan(thu_tu=0, ten="In offset", nhom="print", don_vi_vao="to", don_vi_ra="to"),
        LsxCongDoan(thu_tu=1, ten="Bắt tay + vào keo", nhom="finishing",
                    don_vi_vao="to", don_vi_ra="cai"),
    ]
    rows = {r["ten"]: r for r in lsx_svc.tinh_nguoc_routing(sach)}
    assert rows["Bắt tay + vào keo"]["so_luong_ra"] == 2_000
    assert rows["Bắt tay + vào keo"]["so_luong_vao"] == 20_000
    assert rows["In offset"]["so_luong_vao"] == 20_000


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
    """Máy in có tốc độ → routing kế thừa được năng suất."""
    may = MayThietBi(
        ma="MAY-IN-T", ten="Máy in 4 màu", loai_may="press_offset_sheet",
        toc_do=5_000, don_vi_toc_do="to_gio",
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
    # `requires_tooling` cũng vậy — checklist "thiếu khuôn" đọc CỜ này, không dò chữ "bế" trong tên
    # (công đoạn do người dùng khai lúc chạy, tên gì cũng có thể).
    cd_be = CongDoan(ma="CD-BE-T", ten="Bế", nhom="finishing", cong_thuc_gia="so_luong * don_gia",
                     department_id=to_id, setup_time=30, don_vi_vao="to", don_vi_ra="cai",
                     requires_tooling=True, tooling_type="khuon_be")
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

    # Bước nội bộ chưa biết TỔ/MÁY nào làm → CHỜ BỔ SUNG. (Mục "thiếu khuôn bế" đã bỏ khỏi
    # checklist 11/08/2026: ô gán khuôn ở cấp lệnh không còn, giữ lại là khoá lệnh vĩnh viễn.)
    buoc = hop.cong_doans[0]
    buoc.department_id = None
    buoc.may_id = None
    db.commit()
    hop = lsx_svc.get(hop.id)
    assert "thieu_to_may" in lsx_svc.thieu_cua(hop)
    with pytest.raises(LsxConflict):
        lsx_svc.set_trang_thai(lsx_id=hop.id, trang_thai=TT_SAN_SANG, actor=admin)

    # Gán lại tổ cho bước đó → hết thiếu → mở cửa "Sẵn sàng".
    lsx_svc.get(hop.id).cong_doans[0].department_id = _to_san_xuat(db).id
    db.commit()
    hop = lsx_svc.get(hop.id)
    assert lsx_svc.thieu_cua(hop) == [] and hop.trang_thai == TT_NHAP
    assert lsx_svc.set_trang_thai(lsx_id=hop.id, trang_thai=TT_SAN_SANG, actor=admin).trang_thai == TT_SAN_SANG


def test_don_vi_nang_suat_KHOA_theo_don_gia_khoan(db, lsx_svc):
    """Đơn vị năng suất LÀ đơn vị đơn giá khoán, người khai KHÔNG đổi được (chủ 10/08/2026).

    Ghim luôn ca dễ hiểu nhầm: cột `cong_doan_dau_viec.don_vi_nang_suat` vẫn còn trong DB và vẫn
    có dữ liệu cũ, nhưng thôi được đọc — đọc nó ra là quay lại lối "người khai chọn" vừa bỏ.

    🔴 ĐỔI 15/08/2026: trước đây trả MÃ `cuon_gio` qua `dv_nang_suat_theo_khoan` — một nhãn suông,
    hiện "cuốn/h" trong khi công thức chia số TỜ. Hàm đó đã gỡ cùng hai cơ chế đơn vị khác; nay
    trả thẳng TÊN đơn vị của đơn giá, và thời lượng quy SL vào về chính đơn vị này trước khi chia.
    """
    from app.models.don_vi_do import DonViDo
    from app.models.piece_work import PieceRate

    to = _to_san_xuat(db)
    for ma, ten, ho in (("to", "tờ", "to"), ("cuon", "cuốn", "thanh_pham")):
        if db.query(DonViDo).filter(DonViDo.ma == ma).first() is None:
            db.add(DonViDo(ma=ma, ten=ten, ho=ho, he_so_goc=1, active=True))
    rate = PieceRate(group_name="to_be", department_id=to.id, ma="XEN-K",
                     ten="Xén 3 mặt thành phẩm", unit="cuốn", unit_price=120)
    db.add(rate)
    cd = CongDoan(ma="CD-BE-KHOA", ten="Bế nổi", nhom="finishing", department_id=to.id,
                  don_vi_vao="to", don_vi_ra="cai", cong_thuc_gia="so_luong * don_gia")
    db.add(cd)
    db.flush()
    db.add(CongDoanDauViec(
        cong_doan_id=cd.id, piece_rate_id=rate.id, nang_suat_nguoi_gio=500,
        so_nguoi_tieu_chuan=1, so_nguoi_toi_da=1,
        # Giá trị CŨ người khai từng chọn — phải bị bỏ qua, không được thắng đơn giá khoán.
        don_vi_nang_suat="to_gio",
    ))
    db.commit()

    # Dòng đã khai sẵn "to_gio" vẫn phải bị đơn giá khoán thắng.
    [dv] = [x for x in lsx_svc._dau_viec_option_dicts(cd, to.id) if x["id"] == rate.id]
    assert dv["don_vi"] == "cuốn" and dv["don_vi_nang_suat"] == "cuốn"


def test_thoi_gian_buoc_TO_quy_SL_vao_ve_don_vi_don_gia_khoan(
    db, orders, lsx_svc, admin, customer,
):
    """⭐ Bước đếm `cai`, khoán đ/`ram`, có cầu `1 ram = 500 cái` ⇒ chia RAM cho ram/giờ.

    Đây là ca chủ bắt lỗi 15/08: năng suất hiện "500 kg/h" mà máy vẫn nhận số TỜ. Nay SL vào đi
    qua đúng bộ quy đổi của tiền khoán trước khi chia — hai màn nói cùng một đơn vị.
    """
    from app.models.don_vi_do import DonViDo, DonViQuyDoi

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Bó ram", don_vi="ram", don_gia=900, nang_suat=2)
    cai = db.query(DonViDo).filter(DonViDo.ma == "cai").one()
    ram = db.query(DonViDo).filter(DonViDo.ma == "ram").one_or_none() \
        or DonViDo(ma="ram", ten="ram", ho="to")
    db.add(ram)
    db.flush()
    db.add(DonViQuyDoi(tu_id=ram.id, den_id=cai.id, he_so=500))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})

    buoc = next(b for b in lsx_svc.detail_dict(lsx_svc.get(hop.id))["cong_doans"]
                if b["ten"] == "Dán hộp")
    dg = buoc["thoi_luong_dien_giai"]
    vao_cai = float(buoc["so_luong_vao"])
    assert vao_cai > 0
    # Số đem chia là RAM, không phải cái.
    assert dg["so_luong_vao"] == pytest.approx(vao_cai / 500, rel=1e-6)
    assert dg["don_vi_vao"] == "ram"
    assert dg["so_luong_vao_goc"] == pytest.approx(vao_cai, rel=1e-6)
    # phút = ram ÷ (2 ram/giờ × số người) × 60 — chia theo người là luật cũ, không đụng.
    nguoi = int(dg["so_nhan_cong_tinh"] or 1)
    assert buoc["chay_phut"] == pytest.approx(vao_cai / 500 / (2 * nguoi) * 60, abs=0.01)


def test_thoi_gian_buoc_MAY_doc_cong_thuc_cua_CHINH_MAY(
    db, orders, lsx_svc, admin, customer,
):
    """⭐ Máy khai `m²/giờ`, bước đếm `tờ`, không có cầu ⇒ chạy CÔNG THỨC của CHÍNH MÁY (mg `0213`).

    Trước 17/08/2026 số này đọc công thức của ĐƠN VỊ đích (`don_vi_do.cong_thuc`, gỡ ở mg `0215`) —
    một cách đo dùng chung cho mọi máy đếm bằng `m²`, trong khi lượt của máy 5 màu khác máy 2 màu.
    Không có công thức thì bước im lặng về 0 — xem `test_chua_quy_doi_duoc_thi_KHONG_bia_gio`.
    """
    from app.models.don_vi_do import DonViDo

    ptg = _ptg_2_san_pham(db)
    if db.query(DonViDo).filter(DonViDo.ma == "m2").one_or_none() is None:
        db.add(DonViDo(ma="m2", ten="m²", ho="dien_tich"))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    may_in = next(x for x in hop.cong_doans if x.ten == "In offset")
    may = db.get(MayThietBi, may_in.may_id)
    may.don_vi_toc_do, may.toc_do = "m2_gio", 3000
    may.toc_do_min = may.toc_do_max = None
    may.cong_thuc_luong = "sl_vao * 0.559"   # tờ 65×86 = 0,559 m²
    db.commit()

    buoc = next(b for b in lsx_svc.detail_dict(lsx_svc.get(hop.id))["cong_doans"]
                if b["id"] == may_in.id)
    dg = buoc["thoi_luong_dien_giai"]
    vao_to = float(buoc["so_luong_vao"])
    assert dg["so_luong_vao"] == pytest.approx(vao_to * 0.559, abs=0.01)   # server làm tròn 2 số
    assert dg["don_vi_vao"] == "m²"
    assert "SL vào của công đoạn" in (dg["quy_doi_dien_giai"] or "")
    luot = int(dg["so_luot_chay"] or 1)
    assert buoc["chay_phut"] == pytest.approx(vao_to * 0.559 * 60 / 3000 * luot, abs=0.01)


def test_sua_quy_cach_tren_lenh_tinh_lai_moi_so_dan_xuat(db, orders, lsx_svc, admin, customer):
    """Snapshot vẫn là snapshot, nhưng kế hoạch sửa được THÔNG SỐ tại chỗ — sửa là hệ quả tính lại.

    Ngả 1: số dẫn xuất (`so_kem` · `so_luot` · `so_manh_xa` · số tờ) luôn bám thông số, số gõ tay
    bị đè. Đổi lại là lệnh không bao giờ ở trạng thái tự mâu thuẫn.
    """
    from app.schemas.lsx import LsxQuyCachIn

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    [hop, _tem] = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    kem_dau = int((hop.quy_cach_json or {}).get("so_kem") or 0)
    assert kem_dau > 0

    # Đổi MỰC: thêm một Pantone vào mặt A → mỗi tay thêm đúng 1 bản kẽm.
    qc0 = hop.quy_cach_json or {}
    muc_a = list(qc0.get("muc_a") or []) + ["185C"]
    hop = lsx_svc.update(
        lsx_id=hop.id, actor=admin,
        payload=LsxUpdateIn(quy_cach=LsxQuyCachIn(muc_a=muc_a, muc_b=qc0.get("muc_b") or [])),
    )
    qc = hop.quy_cach_json
    assert qc["muc_a"][-1] == "185C"
    assert qc["so_kem"] == kem_dau + qc["so_to_per_sp"]     # +1 bản mỗi tay
    assert qc["so_mau_pha"] == 1                            # ba số màu là DẪN XUẤT, tự theo

    # Đổi QUY CÁCH IN sang tự trở → hai mặt chung một bộ bản, kẽm rơi về hợp tập.
    hop = lsx_svc.update(
        lsx_id=hop.id, actor=admin, payload=LsxUpdateIn(quy_cach=LsxQuyCachIn(quy_cach_in="tu_tro")))
    qc = hop.quy_cach_json
    hop_tap = len(set(qc["muc_a"]) | set(qc["muc_b"]))
    assert qc["kem_moi_tay"] == hop_tap
    assert qc["so_kem"] == hop_tap * qc["so_to_per_sp"]
    assert qc["so_luot"] == int(hop.so_to_ke_hoach) * 2      # tự trở vẫn 2 lượt


def test_xem_truoc_quy_cach_khong_ghi_gi_vao_db(db, orders, lsx_svc, admin, customer):
    """Xem trước chạy ĐÚNG đường của nút Lưu rồi rollback — số hiện ra không thể lệch số lưu."""
    from app.schemas.lsx import LsxQuyCachIn

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    [hop, _tem] = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    truoc = dict(hop.quy_cach_json or {})
    con_truoc = int(hop.so_con or 0)

    xem = lsx_svc.xem_truoc_quy_cach(
        lsx_id=hop.id, patch={"quy_cach_in": "tu_tro", "muc_a": ["C", "M", "Y", "K"],
                              "muc_b": ["185C"]})
    assert xem["kem_moi_tay"] == 5                 # |{C,M,Y,K,185C}| — max sẽ ra 4
    assert xem["so_kem"] == 5 * xem["so_to_per_sp"]

    # DB không đổi một chữ.
    sau = lsx_svc.get(hop.id)
    assert (sau.quy_cach_json or {}).get("so_kem") == truoc.get("so_kem")
    assert (sau.quy_cach_json or {}).get("quy_cach_in") == truoc.get("quy_cach_in")
    assert int(sau.so_con or 0) == con_truoc

    # Và lưu thật thì ra ĐÚNG số vừa xem.
    luu = lsx_svc.update(
        lsx_id=hop.id, actor=admin,
        payload=LsxUpdateIn(quy_cach=LsxQuyCachIn(
            quy_cach_in="tu_tro", muc_a=["C", "M", "Y", "K"], muc_b=["185C"])),
    )
    assert luu.quy_cach_json["so_kem"] == xem["so_kem"]
    assert int(luu.so_to_ke_hoach or 0) == xem["so_to_ke_hoach"]


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

    r = PieceRate(group_name="Tổ test", department_id=department_id, ten=ten, unit=don_vi,
                  unit_price=don_gia, active=True)
    db.add(r)
    db.commit()
    return r


def _gan_dinh_muc(db, *, cong_doan: CongDoan, ten: str, don_vi: str, don_gia: float,
                  nang_suat: float = 1000,
                  ns_min: float | None = None, ns_max: float | None = None,
                  don_vi_ns: str | None = None):
    """Gắn một đầu việc + định mức vào công đoạn.

    Tham số `mac_dinh` đã BỎ 12/08/2026 cùng cột `is_default` (mg 0190): đầu việc điền sẵn nay chỉ
    suy từ "công đoạn có đúng MỘT đầu việc", không còn cờ nào khai ở danh mục.
    """
    rate = _don_gia_khoan(db, department_id=cong_doan.department_id,
                          ten=ten, don_vi=don_vi, don_gia=don_gia)
    db.add(CongDoanDauViec(
        cong_doan_id=cong_doan.id, piece_rate_id=rate.id,
        nang_suat_nguoi_gio=nang_suat, nang_suat_nguoi_gio_min=ns_min,
        nang_suat_nguoi_gio_max=ns_max, don_vi_nang_suat=don_vi_ns,
        so_nguoi_tieu_chuan=2, so_nguoi_toi_da=4,
    ))
    db.commit()
    return rate


def _chon_loai_buoc(lsx_svc, lsx, admin, chon: dict[str, str]):
    """Kế hoạch chọn LOẠI BƯỚC ở drawer — nay là cách DUY NHẤT để một bước thành Tổ.

    Từ 12/08/2026 server KHÔNG còn đoán Máy/Tổ theo tên bước (`_suy_loai_buoc` đã gỡ: nó dò 10 chữ
    tiếng Việt nên đổi tên, gõ không dấu, hoặc máy tên "Máy dán tự động" là suy sai). Bước bung ra
    luôn là `may`; muốn Tổ thì người kế hoạch bấm ô "Loại bước" trong drawer, và chính lúc đó
    `replace_routing` mới kéo định mức đầu việc (năng suất · số người · chờ) về.

    Helper này gửi đúng payload mà drawer gửi, để test đi qua cùng một cửa với người dùng thật.
    """
    rows = [
        LsxCongDoanIn(
            step_key=cd.step_key, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
            loai_buoc=chon.get(cd.ten, cd.loai_buoc),
            department_id=cd.department_id, may_id=cd.may_id,
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    return lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin)


def test_buoc_bung_ra_luon_la_may_khong_doan_theo_ten(db, orders, lsx_svc, admin, customer):
    """Bung lệnh KHÔNG được đoán bước nào là Tổ — kể cả bước tên "Dán hộp".

    Đây là hợp đồng thay cho `_suy_loai_buoc`: tên bước không còn quyết định gì. Chốt bằng test để
    người sau đừng "tiện tay" khai lại một bảng từ khoá mới.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    assert {cd.loai_buoc for cd in hop.cong_doans} == {"may"}
    # Bấm sang Tổ ở drawer ⇒ server gỡ máy và kéo định mức về.
    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})
    dan = {cd.ten: cd for cd in hop.cong_doans}["Dán hộp"]
    assert dan.loai_buoc == "to" and dan.may_id is None


def test_danh_sach_va_preview_gui_kem_don_vi_theo_tung_dong(
    db, orders, lsx_svc, admin, customer
):
    """Bảng DANH SÁCH và bảng LỆNH DỰ KIẾN phải biết đơn vị của TỪNG dòng.

    Màn chi tiết mở một lệnh nên đọc đơn vị từ routing được; hai bảng này xếp nhiều lệnh cạnh nhau,
    mỗi lệnh có thể đếm bằng đơn vị xưởng tự đặt — một tiêu đề cột không gánh nổi. Thiếu mã này thì
    frontend chỉ có con số trần và buộc phải ghi cứng chữ "Tờ in".
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    ln = lines[0]
    assert ln["don_vi_to"] and ln["don_vi_tp"], "preview phải chấm đơn vị từ routing dự kiến"

    hop = lsx_svc.tao(order_id=d.id, order_line_ids=[ln["order_line_id"]], actor=admin)[0]
    row = next(r for r in lsx_svc.list_rows(order_id=d.id) if r["id"] == hop.id)
    # Hai màn phải nói CÙNG một đơn vị cho cùng một lệnh — lệch là người dùng mất niềm tin vào số.
    assert row["don_vi_to"] == ln["don_vi_to"]


def test_doi_to_thi_danh_sach_dau_viec_khoan_doi_theo_to_va_cong_doan(
    db, orders, lsx_svc, admin, customer
):
    """Dropdown LSX không được giữ đầu việc của tổ cũ sau khi kế hoạch đổi tổ."""
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    rate = _gan_dinh_muc(
        db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250,
        nang_suat=1200,
    )
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line_id = lsx_svc.preview(d.id)["lines"][0]["order_line_id"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[line_id], actor=admin)[0]

    dung_to = lsx_svc.dau_viec_options(
        lsx_id=lsx.id, cong_doan_id=cd_dan.id, department_id=cd_dan.department_id,
    )
    assert [x["id"] for x in dung_to] == [rate.id]
    assert dung_to[0]["nang_suat_nguoi_gio"] == 1200
    assert "is_default" not in dung_to[0], "cờ mặc định đã gỡ khỏi API (mg 0190)"

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


def test_bung_vat_tu_theo_dau_viec_va_khong_de_len_dong_nguoi_sua(
    db, orders, lsx_svc, admin, customer
):
    """BOM (mg 0191): đầu việc khai sẵn vật tư → bước lệnh có số lượng ĐÃ quy đổi, và dòng người
    sửa thì máy chừa ra.

    Số lượng suy từ quy đổi động: bước "Dán hộp" đếm `cai`, mực khai `kg`, nên phải có cạnh
    `cai → kg` mới ra số — không có thì máy KHÔNG bung, chỉ nói thiếu gì.
    """
    from app.models.cong_doan import CongDoanDauViecVatTu
    from app.models.don_vi_do import DonViDo, DonViQuyDoi
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    rate = _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)
    keo = VatTuInAn(ma="KEO-T", ten="Keo dán hộp", don_vi_gia="kg", don_gia=95_000)
    coi = VatTuInAn(ma="COI-T", ten="Cồn không quy đổi", don_vi_gia="lit", don_gia=1)
    db.add_all([keo, coi])
    db.flush()
    dm = cd_dan.dau_viec_dinh_muc[0]
    dm.vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0))
    dm.vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=coi.id, thu_tu=1))
    # Cạnh TĨNH `cai → kg`: 1 hộp ăn 0,004 kg keo. (Cạnh động cần biến quy cách, ca này không cần.)
    cai = db.query(DonViDo).filter(DonViDo.ma == "cai").one()
    kg = db.query(DonViDo).filter(DonViDo.ma == "kg").one_or_none() \
        or DonViDo(ma="kg", ten="kg")
    db.add_all([kg, DonViDo(ma="lit", ten="lít")])
    db.flush()
    db.add(DonViQuyDoi(tu_id=cai.id, den_id=kg.id, he_so=0.004))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")
    chon = next(x for x in buoc["khoan_chon_duoc"] if x["id"] == rate.id)

    # Keo ra số THẬT = SL vào bước × 0,004; cồn không có đường đổi ⇒ KHÔNG bung, chỉ cảnh báo.
    assert [v["ma"] for v in chon["vat_tus"]] == ["KEO-T"]
    sl_buoc = next(float(c.so_luong_vao) for c in lsx.cong_doans if c.ten == "Dán hộp")
    assert chon["vat_tus"][0]["so_luong"] == pytest.approx(round(sl_buoc * 0.004, 3))
    assert chon["vat_tus"][0]["don_vi"] == "kg"
    assert any("Cồn không quy đổi" in c for c in chon["canh_bao_vat_tu"]), \
        "vật tư không đổi được phải NÓI THIẾU GÌ, không im lặng biến mất"

    # Lưu hai dòng: một của máy, một người tự thêm. Cờ phải đi đúng theo từng dòng.
    rows = [
        LsxCongDoanIn(
            thu_tu=cd.thu_tu, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
            department_id=cd.department_id, so_luong_vao=float(cd.so_luong_vao),
            so_luong_ra=float(cd.so_luong_ra), don_vi_vao=cd.don_vi_vao, don_vi_ra=cd.don_vi_ra,
            vat_tus=([{"vat_tu_id": keo.id, "so_luong": 40, "tu_dong": True},
                      {"vat_tu_id": coi.id, "so_luong": 7, "tu_dong": False}]
                     if cd.ten == "Dán hộp" else None),
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin, ly_do=None)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")
    co = {v["vat_tu_ma"]: v for v in buoc["vat_tus"]}
    assert co["KEO-T"]["tu_dong"] is True, "dòng máy bung ⇒ lần sau thay được"
    assert co["COI-T"]["tu_dong"] is False, "dòng người tự thêm ⇒ máy phải chừa ra"
    assert co["COI-T"]["so_luong"] == 7


def test_so_luong_vat_tu_lay_tu_CONG_THUC_cua_chinh_mon_hang(db, orders, lsx_svc, admin, customer):
    """Đường CHÍNH của BOM: vật tư khai `cong_thuc_luong` của CHÍNH nó (mg 0194).

    Không đi qua bảng cặp, không cần đơn vị của bước khớp gì cả — công thức tự lấy chip từ quy cách
    lệnh. Trước 17/08/2026 đường này đọc CÁCH ĐO của đơn vị (`don_vi_do.cong_thuc`, gỡ ở mg `0215`):
    một công thức trả lời hộ mọi món cùng đơn vị, trong khi keo và mực cùng đo `kg` mà ăn khác nhau.
    """
    from app.models.cong_doan import CongDoanDauViecVatTu
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    rate = _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)
    db.add(DonViDo(ma="m2_tp", ten="m² thành phẩm"))
    # Công thức khai trên CHÍNH món hàng: dài × rộng thành phẩm × số lượng đặt.
    keo = VatTuInAn(ma="MANG-TP", ten="Màng phủ thành phẩm", don_vi_gia="m2_tp", don_gia=9_000,
                    cong_thuc_luong="dai_tp * rong_tp * so_luong")
    db.add(keo)
    db.flush()
    cd_dan.dau_viec_dinh_muc[0].vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")
    chon = next(x for x in buoc["khoan_chon_duoc"] if x["id"] == rate.id)

    qc = lsx.quy_cach_json or {}
    cho = (float(qc["dai_thanh_pham"]) / 1000) * (float(qc["rong_thanh_pham"]) / 1000) \
        * float(lsx.so_luong_dat)
    assert [v["ma"] for v in chon["vat_tus"]] == ["MANG-TP"]
    assert chon["vat_tus"][0]["so_luong"] == pytest.approx(round(cho, 3))
    assert chon["vat_tus"][0]["don_vi"] == "m2_tp"
    # Diễn giải phải đọc được bằng chữ, không phải mã biến trần.
    assert "Dài sản phẩm" in (chon["vat_tus"][0]["dien_giai"] or "")

    # Công thức ra 0 vì thiếu chip (lệnh này không có màu pha) ⇒ KHÔNG bung, nói thiếu biến nào.
    # Thà để trống cho người kế hoạch tự thêm còn hơn ghi 0 rồi mua hụt.
    db.query(VatTuInAn).filter(VatTuInAn.ma == "MANG-TP").one().cong_thuc_luong = "so_mau_pha * dai_tp"
    db.commit()
    buoc = next(b for b in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
                if b["ten"] == "Dán hộp")
    chon = next(x for x in buoc["khoan_chon_duoc"] if x["id"] == rate.id)
    assert chon["vat_tus"] == []
    assert any("so_mau_pha" in c for c in chon["canh_bao_vat_tu"])


def test_vat_tu_khai_o_dau_viec_TU_BUNG_vao_buoc_luc_tao_lenh(db, orders, lsx_svc, admin, customer):
    """Khai vật tư ở ĐẦU VIỆC (danh mục) ⇒ tạo lệnh xong bước phải CÓ SẴN dòng đó, kèm số lượng.

    Dính 13/08/2026: server tự điền đầu việc khi tổ chỉ khớp một dòng, nhưng chỉ FRONTEND mới bung
    vật tư — và nó chỉ bung khi người dùng TỰ TAY chọn lại đầu việc ở drawer. Kết quả: lệnh có đầu
    việc "In 2 màu" mà khối "Vật tư cần dùng" trống, kế hoạch vật tư không thấy gì để đi mua.
    """
    from app.models.cong_doan import CongDoanDauViecVatTu
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)
    db.add(DonViDo(ma="kg_keo", ten="kg keo"))
    # Định mức khai trên CHÍNH món keo: 2 g cho mỗi thành phẩm của lệnh.
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg_keo", don_gia=45_000,
                    cong_thuc_luong="0.002 * so_luong")
    db.add(keo)
    db.flush()
    cd_dan.dau_viec_dinh_muc[0].vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)

    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    assert buoc.khoan_json, "tổ chỉ có một đầu việc ⇒ server phải điền sẵn"
    ma = [v.vat_tu_ma_snapshot for v in buoc.vat_tus]
    assert ma == ["KEO-GAY"], f"vật tư của đầu việc phải tự bung, đang có: {ma}"
    v = buoc.vat_tus[0]
    assert float(v.so_luong) == pytest.approx(0.002 * float(lsx.so_luong_dat), rel=1e-6)
    assert v.tu_dong is True, "dòng máy bung ⇒ lần đổi đầu việc sau phải thay được"


def test_cong_thuc_luong_cua_VAT_TU_thang_cong_thuc_cua_don_vi(db, orders, lsx_svc, admin, customer):
    """Keo đo bằng `kg` THẬT + công thức lượng riêng ⇒ BOM ra số kg, khỏi đẻ đơn vị `kg_keo`.

    Chốt 13/08/2026: công thức ra LƯỢNG thuộc về MÓN HÀNG, không thuộc về ĐƠN VỊ. `kg` dùng chung
    cho keo · mực · giấy mà mỗi thứ tiêu hao một kiểu — gắn lên `kg` là cả ba bị tính như nhau.
    Kho và mua hàng vẫn thấy `kg` thật, không phải `kg_keo`.
    """
    from app.models.cong_doan import CongDoanDauViecVatTu
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)
    # `kg` mang công thức của GIẤY — cố tình, để chứng minh vật tư THẮNG đơn vị.
    dv_kg = db.query(DonViDo).filter(DonViDo.ma == "kg").one_or_none()
    if dv_kg is None:
        dv_kg = DonViDo(ma="kg", ten="kg", ho="khoi_luong")
        db.add(dv_kg)
    dv_kg.cong_thuc = "dinh_luong * dai_in * rong_in * to_dau_vao"
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45_000,
                    cong_thuc_luong="0.002 * so_luong")
    db.add(keo)
    db.flush()
    cd_dan.dau_viec_dinh_muc[0].vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    v = next(x for x in buoc.vat_tus if x.vat_tu_ma_snapshot == "KEO-GAY")

    # Số theo công thức CỦA KEO, KHÔNG phải công thức khối lượng giấy gắn trên `kg`.
    assert float(v.so_luong) == pytest.approx(0.002 * float(lsx.so_luong_dat), rel=1e-6)
    assert v.don_vi_snapshot == "kg", "kho vẫn cân bằng kg thật, không phải kg_keo"


def test_goi_y_luong_cho_MOI_vat_tu_de_drawer_dien_san(db, orders, lsx_svc, admin, customer):
    """Chọn một vật tư BẤT KỲ ở drawer thì số phải hiện ngay — server tính sẵn cho cả danh mục.

    Chủ 13/08/2026: "khi chọn keo vào gáy thì nó tính luôn". Công thức + quy cách đều nằm ở server;
    client không có và không nên có (công thức chỉ được một bản). Nên server gửi kèm `vat_tu_goi_y`.

    Món chưa tính ra được thì KHÔNG có trong danh sách ⇒ drawer để trống, không đoán số.
    """
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45_000,
                    cong_thuc_luong="0.002 * so_luong")
    # Món CHƯA khai gì để tính lượng ⇒ phải VẮNG khỏi gợi ý, không được bịa số.
    mu = VatTuInAn(ma="MU-LA", ten="Món lạ", don_vi_gia="thung_la", don_gia=1_000)
    db.add_all([keo, mu, DonViDo(ma="thung_la", ten="thùng lạ")])
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")

    goi_y = {g["vat_tu_id"]: g for g in buoc["vat_tu_goi_y"]}
    assert keo.id in goi_y, "vật tư có công thức lượng phải được tính sẵn"
    assert goi_y[keo.id]["so_luong"] == pytest.approx(
        round(0.002 * float(lsx.so_luong_dat), 3), rel=1e-6)
    assert mu.id not in goi_y, "chưa tính ra được thì VẮNG mặt, không bịa số 0"


def test_dau_viec_mang_san_vat_tu_da_tinh_so_de_drawer_bung(db, orders, lsx_svc, admin, customer):
    """`khoan_chon_duoc[].vat_tus` phải CÓ SẴN vật tư + số, để drawer chọn đầu việc là điền ngay."""
    from app.models.cong_doan import CongDoanDauViecVatTu
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    rate = _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45_000,
                    cong_thuc_luong="0.002 * so_luong")
    db.add(keo)
    db.flush()
    cd_dan.dau_viec_dinh_muc[0].vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")
    chon = next(x for x in buoc["khoan_chon_duoc"] if x["id"] == rate.id)

    assert [v["ma"] for v in chon["vat_tus"]] == ["KEO-GAY"]
    assert chon["vat_tus"][0]["so_luong"] == pytest.approx(
        0.002 * float(lsx.so_luong_dat), rel=1e-6)


def test_xem_truoc_quy_cach_doi_kho_thi_so_TINH_LAI(db, orders, lsx_svc, admin, customer):
    """Đổi khổ tờ in ở màn Quy cách ⇒ xem trước phải trả số MỚI ngay, chưa cần Lưu.

    Màn LSX gọi `POST /xem-truoc-quy-cach` mỗi lần gõ (debounce 350ms) rồi gạch số cũ, hiện số mới
    kèm nhãn "tính lại". Frontend NUỐT lỗi (`.catch(() => setXemTruoc(null))`) nên endpoint này hỏng
    là màn đứng im mà không báo gì — test giữ cửa đó.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    qc = lsx.quy_cach_json or {}

    # Khổ tờ in bé lại một nửa ⇒ mỗi tờ ra ít con hơn ⇒ cần NHIỀU tờ hơn.
    patch = {"kho_in_dai": float(qc["kho_in_dai"]) / 2}
    kq = lsx_svc.xem_truoc_quy_cach(lsx_id=lsx.id, patch=patch)

    assert kq["so_con"] < int(lsx.so_con), "khổ bé đi thì con/tờ phải giảm"
    assert kq["so_to_ke_hoach"] > int(lsx.so_to_ke_hoach), "ít con/tờ thì phải nhiều tờ hơn"
    assert "kho_in_dai" in kq["doi"], "phải nói rõ thông số nào đổi"
    # Chưa Lưu thì DB KHÔNG được đụng tới.
    db.refresh(lsx)
    assert int(lsx.so_to_ke_hoach) != kq["so_to_ke_hoach"]


def test_buoc_NGOAI_dong_giay_lay_so_tu_cong_thuc_SAN_LUONG_va_co_hao(
    db, orders, lsx_svc, admin, customer,
):
    """Bước ngoài dòng giấy: `ra` ← `cong_doan.cong_thuc_san_luong`, `vào` suy ngược kèm hao.

    Chốt 14/08/2026, thay dòng hardcode `vao = ra = so_kem if nhom == "prepress"`. Bản cũ khoá theo
    TÊN NHÓM (đặt nhóm khác là số rơi về 0 không một lời) và ép vào = ra nên hao hết chỗ nhét.

    Ghi kẽm: 1 bài, 4 màu ⇒ ra 4 bản TỐT; hỏng 1 ⇒ phải ghi 5.
        ra  = so_kem = 4
        vào = (4 ÷ hệ_số 4 + hao 1) = 2 bài?  → KHÔNG: hệ số 4 nghĩa 1 bài ra 4 bản,
              nên (4 ÷ 4) = 1 bài, + hao 1 (tính bằng đơn vị VÀO) = 2.
    Test dùng `kẽm → kẽm` (hệ số 1) cho đúng nghiệp vụ hao: hỏng 1 BẢN, không phải hỏng 1 bài.
    """
    from app.models.don_vi_do import DonViDo

    ptg = _ptg_2_san_pham(db)
    if db.query(DonViDo).filter(DonViDo.ma == "kem").one_or_none() is None:
        db.add(DonViDo(ma="kem", ten="bản kẽm", ho="kem"))
    # Lấy một bước ĐANG CÓ trong routing rồi đẩy nó ra NGOÀI dòng giấy bằng cách đổi đơn vị —
    # đúng thứ xảy ra khi xưởng khai `bai → kem` cho chế bản. Công thức sản lượng khai trên CHÍNH
    # công đoạn (mg `0214`): một lệnh cần bấy nhiêu bản kẽm.
    cd_cb = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    cd_cb.don_vi_vao = cd_cb.don_vi_ra = "kem"
    cd_cb.cong_thuc_san_luong = "so_kem"
    cd_cb.kieu_bu_hao, cd_cb.so_to_bu_hao = "co_dinh", 1
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    so_kem = int((lsx.quy_cach_json or {}).get("so_kem") or 0)
    assert so_kem > 0, "lệnh phải có số kẽm để test có nghĩa"

    cb = next(c for c in lsx.cong_doans if c.cong_doan_id == cd_cb.id)
    assert float(cb.so_luong_ra) == so_kem, "ra = công thức sản lượng của công đoạn"
    assert float(cb.so_luong_vao) == so_kem + 1, "vào = ra + hao — hao nay CÓ chỗ chảy"


def test_danh_muc_doi_sau_khi_tao_lenh_thi_BAO_LECH_chu_khong_tu_de(
    db, orders, lsx_svc, admin, customer,
):
    """Sửa danh mục SAU khi tạo lệnh ⇒ lệnh phơi số mới để màn báo, nhưng KHÔNG tự ghi đè.

    Chủ hỏi 14/08/2026: "tôi ra lệnh rồi mà người khác sửa hệ số thì sao, tôi đâu có biết mà bấm
    Lưu". Đúng — số lượng là ẢNH CHỤP, engine chỉ chạy lại ở ba cửa (tạo · sửa quy cách · lưu
    routing). Nay lúc ĐỌC có so ngầm với danh mục hiện tại.

    KHÔNG tự đè: lệnh đã phát xuống xưởng mà số giấy tự đổi dưới chân người kế hoạch còn tệ hơn số
    cũ. Máy đề xuất, người quyết.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0].id)

    truoc = lsx_svc.detail_dict(lsx)["cong_doans"]
    assert all(b["so_luong_vao_moi"] is None for b in truoc), "chưa đổi gì thì không được báo lệch"
    buoc_in = next(b for b in truoc if b["nhom"] == "print")
    vao_cu = buoc_in["so_luong_vao"]

    # Người khác vào danh mục cộng thêm hao cho công đoạn IN.
    cd_in = db.get(CongDoan, buoc_in["cong_doan_id"])
    cd_in.kieu_bu_hao, cd_in.so_to_bu_hao = "co_dinh", int(cd_in.so_to_bu_hao or 0) + 500
    db.commit()

    sau = lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
    b2 = next(b for b in sau if b["cong_doan_id"] == cd_in.id)
    assert b2["so_luong_vao"] == vao_cu, "số ĐÃ LƯU phải giữ nguyên — lệnh là ảnh chụp"
    assert b2["so_luong_vao_moi"] is not None, "phải phơi số mới để màn báo"
    assert b2["so_luong_vao_moi"] > vao_cu, "thêm hao thì cần nhiều tờ hơn"
    # DB cũng không được đụng.
    db.refresh(lsx)
    cd_db = next(c for c in lsx.cong_doans if c.cong_doan_id == cd_in.id)
    assert float(cd_db.so_luong_vao) == vao_cu


def test_chip_sl_vao_lay_so_cua_CHINH_BUOC_khong_phai_cua_lenh(
    db, orders, lsx_svc, admin, customer,
):
    """`sl_vao` trong công thức lượng của vật tư ⇒ số theo SL VÀO của bước, không phải SL lệnh.

    Keo dán ở bước Bắt tay phải tính theo số cuốn chạy qua ĐÚNG bước đó — bước sau hao bớt thì
    lượng keo ít đi theo. Mọi chip khác đều là số của cả lệnh, không nói được điều này.
    """
    from app.models.cong_doan import CongDoanDauViecVatTu
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)
    # Cho bước có HAO để `so_luong_vao` khác hẳn SL đặt — không thì test không chứng minh được
    # chip lấy số của BƯỚC chứ không phải của lệnh.
    cd_dan.kieu_bu_hao, cd_dan.so_to_bu_hao = "co_dinh", 300
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45_000,
                    cong_thuc_luong="sl_vao * 0.002")
    db.add(keo)
    db.flush()
    cd_dan.dau_viec_dinh_muc[0].vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    v = next(x for x in buoc.vat_tus if x.vat_tu_ma_snapshot == "KEO-GAY")

    assert float(v.so_luong) == pytest.approx(float(buoc.so_luong_vao) * 0.002, rel=1e-6)
    # Và nó KHÁC số tính theo SL lệnh — nếu bằng nhau thì test không chứng minh được gì.
    assert float(buoc.so_luong_vao) != float(lsx.so_luong_dat)


def test_khoan_khong_co_cau_quy_doi_thi_doc_CONG_THUC_cua_DAU_VIEC(
    db, orders, lsx_svc, admin, customer,
):
    """Không có cầu `tay → cuốn` ⇒ đọc công thức của CHÍNH ĐẦU VIỆC (mg `0213`), dùng chip `sl_ra`.

    Ca thật ở xưởng: "Bắt tay + vào keo" bước đếm `tay`, khoán đ/`cuốn`. `tay` không nối với
    `cuốn` trong bảng cặp (cầu tay→cái nằm ở code `_he_so_cau`, không phải cặp khai) nên đầu việc
    này CHƯA BAO GIỜ tính được tiền — đo 14/08/2026: 1/10 đầu việc câm dù đã đủ cặp.

    Khai `cuốn := sl_ra` là xong: bước ra bao nhiêu cuốn thì trả bấy nhiêu.
    """
    from app.models.don_vi_do import DonViDo

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    # Bước đếm `tay` — đơn vị KHÔNG nối với `cuon` bằng cặp nào.
    cd_dan.don_vi_vao = "tay"
    rate = _gan_dinh_muc(db, cong_doan=cd_dan, ten="Bắt tay vào keo", don_vi="cuốn", don_gia=700)
    if db.query(DonViDo).filter(DonViDo.ma == "cuon").one_or_none() is None:
        db.add(DonViDo(ma="cuon", ten="cuốn", ho="thanh_pham"))
    # Cách đo khai trên CHÍNH đầu việc, không phải trên đơn vị `cuốn`: việc "đếm, bó" cùng đo bằng
    # cuốn nhưng đo theo bó — hai việc, hai cách.
    rate.cong_thuc_luong = "sl_ra"
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"]
                if b["cong_doan_id"] == cd_dan.id)
    assert buoc["khoan_rate_id"] == rate.id

    sl_ra = float(buoc["so_luong_ra"])
    assert sl_ra > 0
    assert buoc["khoan_sl"] == pytest.approx(sl_ra, rel=1e-6), "SL khoán = sl_ra qua công thức"
    assert buoc["khoan_tien"] == round(sl_ra * 700)
    assert buoc["khoan_ly_do"] is None, "có tiền rồi thì không được kèm lý do tịt"
    # Diễn giải phải ĐI HẾT tới số tiền, cùng giọng với đường một. Câu cụt kiểu
    # "… = 35000 kg × 600 đ" bắt người xem tự nhân — chủ bắt lỗi 14\08\2026.
    dg = buoc["khoan_dien_giai"]
    assert dg.startswith("SL ra của công đoạn = ")
    assert "đ/cuốn" in dg and dg.endswith(f"= {round(sl_ra * 700):,} đ".replace(",", "."))


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


# 🔴 Hai test của cơ chế MƯỢN CÔNG THỨC TRONG CỤM gỡ 17/08/2026 cùng cột `don_vi_do.cong_thuc`
# (mg `0215`): `test_cong_thuc_luong_khai_o_kg_thi_TAN_dung_chung` và
# `test_khoan_muon_cong_thuc_trong_cum_thi_dien_giai_phoi_buoc_doi`. Mượn-trong-cụm chỉ có nghĩa khi
# công thức treo ở ĐƠN VỊ; nay nó treo ở món hàng / máy / đầu việc / bước, mỗi cái tự khai của mình.


# ================= Công thức lượng RIÊNG của máy / của đầu việc khoán (mg 0213) =================
# Bậc ⓿ của `_sl_theo_don_vi`: công thức của CHÍNH đối tượng thắng cầu quy đổi và thắng công thức
# của đơn vị. Cùng luật "RIÊNG → CHUNG" mà `_luong_vat_tu` đã đi cho vật tư/giấy.


def test_cong_thuc_luong_cua_DAU_VIEC_thang_ca_cau_quy_doi(db, orders, lsx_svc, admin, customer):
    """⭐ Hai việc cùng khoán đ/`cuốn` nhưng đo hai cách ⇒ công thức của ĐẦU VIỆC phải thắng.

    Ở đây CÓ cầu quy đổi hẳn hoi (`tay → cuốn`, 1 cuốn = 4 tay) nên đường ① tính ra tiền bình
    thường. Nếu công thức riêng đứng SAU cầu thì nó chỉ chạy khi cầu tịt — tức khai xong mà không
    có tác dụng gì, đúng kiểu hỏng im lặng.
    """
    from app.models.don_vi_do import DonViDo, DonViQuyDoi

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    cd_dan.don_vi_vao = "tay"
    rate = _gan_dinh_muc(db, cong_doan=cd_dan, ten="Đếm bó đóng gói", don_vi="cuốn", don_gia=40)
    tay = db.query(DonViDo).filter(DonViDo.ma == "tay").one_or_none()
    if tay is None:
        tay = DonViDo(ma="tay", ten="tay sách", ho="thanh_pham")
        db.add(tay)
    cuon = db.query(DonViDo).filter(DonViDo.ma == "cuon").one_or_none()
    if cuon is None:
        cuon = DonViDo(ma="cuon", ten="cuốn", ho="thanh_pham")
        db.add(cuon)
    db.commit()
    # Cầu quy đổi CÓ THẬT: 1 cuốn = 4 tay ⇒ đường ① sẽ ra `sl_vao / 4`.
    db.add(DonViQuyDoi(tu_id=cuon.id, den_id=tay.id, he_so=4))
    # Công thức RIÊNG của đầu việc: đếm theo BÓ 10 cuốn.
    rate.cong_thuc_luong = "sl_ra / 10"
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"]
                if b["cong_doan_id"] == cd_dan.id)

    sl_ra = float(buoc["so_luong_ra"])
    sl_vao = float(buoc["so_luong_vao"])
    assert sl_ra > 0 and sl_vao > 0
    assert buoc["khoan_sl"] == pytest.approx(sl_ra / 10, rel=1e-6), \
        "công thức của đầu việc phải thắng cầu quy đổi"
    assert buoc["khoan_tien"] == round(sl_ra / 10 * 40)
    assert buoc["khoan_ly_do"] is None


def test_cong_thuc_dau_viec_duoc_GHIM_sua_danh_muc_khong_xe_dich_lenh(
    db, orders, lsx_svc, admin, customer,
):
    """⭐ Ảnh chụp: sửa cách đo ở danh mục KHÔNG được đổi tiền của lệnh đã tạo.

    Cùng luật đã áp cho `don_gia` từ trước — và phải ghim CÙNG LÚC: ghim một nửa (giá đóng băng,
    cách đo đọc sống) là kiểu sai khó thấy nhất, tiền lệnh cũ tự đổi mà không dòng nhật ký nào nói.
    """
    from app.models.don_vi_do import DonViDo

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    cd_dan.don_vi_vao = "tay"
    rate = _gan_dinh_muc(db, cong_doan=cd_dan, ten="Bắt tay vào keo", don_vi="cuốn", don_gia=700)
    if db.query(DonViDo).filter(DonViDo.ma == "cuon").one_or_none() is None:
        db.add(DonViDo(ma="cuon", ten="cuốn", ho="thanh_pham"))
    rate.cong_thuc_luong = "sl_ra"
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    truoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"]
                 if b["cong_doan_id"] == cd_dan.id)
    assert truoc["khoan_tien"] == round(float(truoc["so_luong_ra"]) * 700)

    # Xưởng đổi cách đo ở DANH MỤC (chia 10) — lệnh đã tạo phải giữ nguyên số của nó.
    rate.cong_thuc_luong = "sl_ra / 10"
    db.commit()
    db.expire_all()
    sau = next(b for b in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
               if b["cong_doan_id"] == cd_dan.id)
    assert sau["khoan_tien"] == truoc["khoan_tien"], "lệnh đã tạo bị xê dịch theo danh mục"
    assert sau["khoan_sl"] == pytest.approx(truoc["khoan_sl"], rel=1e-6)


def test_cong_thuc_luong_cua_MAY_ra_luong_theo_don_vi_toc_do(db, orders, lsx_svc, admin, customer):
    """⭐ Máy đo `m²/giờ` mà bước đếm `tờ` ⇒ công thức của CHÍNH MÁY ra số m², rồi mới chia tốc độ.

    Đọc SỐNG (khác đầu việc khoán bị ghim): đổi máy là đổi cả tốc độ lẫn cách đếm lượt, nên giờ
    chạy phải tính theo máy ĐANG gán.
    """
    from app.models.don_vi_do import DonViDo
    from app.services.bien_cong_thuc import quy_cach_bien

    ptg = _ptg_2_san_pham(db)
    if db.query(DonViDo).filter(DonViDo.ma == "m2_gio").one_or_none() is None:
        db.add(DonViDo(ma="m2_gio", ten="m² mỗi giờ", ho="toc_do", dung_lam_toc_do=True))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next((b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b.get("may_id")), None)
    if buoc is None:
        pytest.skip("lệnh mẫu không có bước nào gán máy")

    may = db.get(MayThietBi, buoc["may_id"])
    may.don_vi_toc_do = "m2_gio"
    may.toc_do = 800
    # 1 tờ in = dai_in × rong_in (m²) ⇒ lượng theo m² của CHÍNH bước này.
    may.cong_thuc_luong = "sl_vao * dai_in * rong_in"
    db.commit()
    db.expire_all()

    lsx_obj = lsx_svc.get(lsx.id)
    cd = next(c for c in lsx_obj.cong_doans if c.id == buoc["id"])
    kq = lsx_svc.sl_tinh_cua_buoc(cd, db.get(MayThietBi, buoc["may_id"]),
                                  quy_cach_bien(lsx_obj))
    assert kq is not None, "công thức của máy không chạy — lẽ ra phải ra số m²"
    so, ten_dv, cau = kq
    assert so > 0
    assert "m²" in ten_dv


def test_cong_thuc_may_thieu_bien_thi_ROI_XUONG_duong_quy_doi(db, orders, lsx_svc, admin, customer):
    """Công thức riêng ra 0 (thiếu biến) thì KHÔNG tịt hẳn — rơi xuống cầu quy đổi như trước.

    Thiếu biến là chuyện của MỘT lệnh cụ thể (chưa khai số màu, chưa có khổ), còn cầu quy đổi vẫn
    trả lời được. Tịt luôn ở bậc ⓿ là làm mất số vốn đang tính ra bình thường.
    """
    from app.services.bien_cong_thuc import quy_cach_bien

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next((b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b.get("may_id")), None)
    if buoc is None:
        pytest.skip("lệnh mẫu không có bước nào gán máy")
    lsx_obj = lsx_svc.get(lsx.id)
    cd = next(c for c in lsx_obj.cong_doans if c.id == buoc["id"])
    truoc = lsx_svc.sl_tinh_cua_buoc(cd, db.get(MayThietBi, buoc["may_id"]),
                                     quy_cach_bien(lsx_obj))

    # `bien_khong_ton_tai` không có trong ngữ cảnh ⇒ công thức ra 0 ⇒ phải rơi xuống ①.
    may = db.get(MayThietBi, buoc["may_id"])
    may.cong_thuc_luong = "sl_vao * bien_khong_ton_tai"
    db.commit()
    db.expire_all()
    lsx_obj = lsx_svc.get(lsx.id)
    cd = next(c for c in lsx_obj.cong_doans if c.id == buoc["id"])
    sau = lsx_svc.sl_tinh_cua_buoc(cd, db.get(MayThietBi, buoc["may_id"]),
                                   quy_cach_bien(lsx_obj))
    assert (sau is None) == (truoc is None), "công thức hỏng làm đổi cả kết cục của đường quy đổi"
    if truoc is not None:
        assert sau[0] == pytest.approx(truoc[0], rel=1e-6), \
            "phải rơi về đúng số của cầu quy đổi như khi chưa khai công thức"


# ================= Routing lát 2: thời gian · tính ngược · cảnh báo =================
def _buoc(**kw) -> LsxCongDoan:
    """1 bước rời để test công thức thời gian — không cần DB."""
    return LsxCongDoan(lsx_id=0, thu_tu=0, ten=kw.pop("ten", "Bước"), **kw)


def _may_gia(toc_do=None, chuan_bi=0, toc_do_min=None, toc_do_max=None,
             don_vi="to_gio", khoan=None):
    """Máy giả cho test công thức. Từ 2026-08-04 tốc độ + thời gian chuẩn bị KẾ THỪA từ máy,
    nên bước rời không còn tự mang số — phải truyền máy vào `thoi_luong_buoc`."""
    return SimpleNamespace(
        toc_do=toc_do, toc_do_min=toc_do_min, toc_do_max=toc_do_max,
        don_vi_toc_do=don_vi, makeready_time_default=chuan_bi,
        fields_theo_loai={"chuan_bi_khoan": khoan} if khoan else None,
    )


def _sl_1_1(cd, dv="tờ"):
    """`sl_tinh` coi như quy đổi 1:1 — dùng cho các test chốt CÔNG THỨC.

    Từ 15/08/2026 `thoi_luong_buoc` nhận SL ĐÃ quy đổi về đơn vị của tốc độ (`sl_tinh`), không tự
    lấy `so_luong_vao` nữa. Các test dưới kiểm phép chia / ba mức / số người — phần quy đổi có test
    riêng, nên ở đây truyền thẳng số của bước cho khỏi lẫn hai thứ vào nhau.
    """
    return (float(cd.so_luong_vao or 0), dv, f"{cd.so_luong_vao:g} {dv}")


def _tlb(cd, may=None, dv="tờ"):
    """`thoi_luong_buoc` với `sl_tinh` 1:1 — xem `_sl_1_1`."""
    return thoi_luong_buoc(cd, may, _sl_1_1(cd, dv))


def _tl(cd, db=None):
    """Thời lượng bước trong test tích hợp — nạp đúng máy đang gán như service làm."""
    may = db.get(MayThietBi, cd.may_id) if (db is not None and cd.may_id) else None
    return _tlb(cd, may)


def test_thoi_luong_bo_qua_cac_o_dormant():
    """`ve_sinh_phut` · `di_chuyen_phut` · `cho_phut` đều DORMANT — truyền vào để CHỨNG MINH bỏ qua.

    CHỜ KỸ THUẬT gỡ 13/08/2026: `tong_phut` nay bằng đúng `chiem_may_phut`. Hai khoá vẫn tách vì
    bàn xếp lịch lấy HIỆU của chúng làm độ trễ giữa hai bước — hiệu = 0 nghĩa là bước sau bắt đầu
    ngay khi máy nhả tờ. Muốn dựng lại độ trễ thì cộng vào `tong`, KHÔNG cộng vào `chiem_may`.
    """
    b = _buoc(so_luong_vao=5300, ve_sinh_phut=15, di_chuyen_phut=30)
    t = _tlb(b, _may_gia(toc_do=5000, chuan_bi=45))
    assert round(t["chay_phut"]) == 64
    assert round(t["chiem_may_phut"]) == 109                 # 45 + 64
    assert round(t["tong_phut"]) == 109                      # không cộng thêm gì


def test_thoi_gian_khac_cong_thang_vao_chiem_may():
    """Ô "Thời gian khác" là ô DUY NHẤT người kế hoạch còn gõ được — phải có tác dụng thật.

    `chay_phut` nhập đè đã BỎ: truyền vào cũng bị bỏ qua, giờ chạy luôn suy từ tốc độ máy."""
    b = _buoc(so_luong_vao=5300, chay_phut=120, phat_sinh_phut=30)
    t = _tlb(b, _may_gia(toc_do=5000, chuan_bi=45))
    assert round(t["chay_phut"]) == 64                       # KHÔNG lấy 120 gõ đè
    assert round(t["chiem_may_phut"]) == 139                 # 30 khác + 45 chuẩn bị + 64 chạy


def test_may_nhan_so_luot_nhung_khong_chia_theo_kip_nguoi():
    may = _may_gia(toc_do=5000)
    assert _tlb(_buoc(loai_buoc="may", so_luong_vao=5000), may)["chay_phut"] == 60
    # In trở 2 lượt → chạy gấp đôi.
    t = _tlb(_buoc(loai_buoc="may", so_luong_vao=5000,
                              so_luot_chay=2, so_nhan_cong=3), may)
    assert t["chay_phut"] == 120
    assert t["dien_giai"]["phuong_phap"] == "may"
    assert t["dien_giai"]["so_nhan_cong_tinh"] is None
    assert t["dien_giai"]["so_nhan_cong_ke_hoach"] == 3
    assert t["dien_giai"]["so_nhan_cong_tieu_chuan"] == 1


def test_to_chia_theo_nguoi_va_gioi_han_o_muc_toi_da():
    t = _tlb(_buoc(
        loai_buoc="to", so_luong_vao=5000, nang_suat=500,
        so_nhan_cong=6, so_nhan_cong_toi_da=5,
    ))
    assert t["chay_phut"] == 120
    # Bước TỔ không gán máy ⇒ chuẩn bị = 0 (chuẩn bị nay CHỈ kế thừa từ máy).
    assert t["chiem_may_phut"] == 120
    assert t["dien_giai"]["nang_suat_hieu_dung"] == 2500
    assert t["dien_giai"]["so_nhan_cong_tinh"] == 5
    assert t["dien_giai"]["so_nhan_cong_ke_hoach"] == 6
    assert t["dien_giai"]["so_nhan_cong_toi_da"] == 5
    assert any("vượt mức tối đa hiệu quả" in x for x in t["dien_giai"]["canh_bao"])


def test_to_co_ba_muc_nang_suat_nhu_may_co_ba_muc_toc_do():
    """Bước TỔ ra BA con thời lượng — cùng lối với máy, chỉ khác nguồn năng suất.

    5.000 cái ÷ (500 cái/người/giờ × 2 người) × 60 = 300′ theo mức TRUNG BÌNH; mức CAO (1.000)
    chạy nhanh hơn nên ra thời lượng NHỎ nhất, mức THẤP (400) ra lớn nhất. "Thời gian khác" là
    hằng số nên cộng đều vào cả ba, không làm khoảng rộng ra.
    """
    t = _tlb(_buoc(
        loai_buoc="to", so_luong_vao=5000, nang_suat=500, phat_sinh_phut=10,
        so_nhan_cong=2, so_nhan_cong_toi_da=5,
        khoan_json={"nang_suat_nguoi_gio": 500,
                    "nang_suat_nguoi_gio_min": 400, "nang_suat_nguoi_gio_max": 1000},
    ))
    assert t["chay_phut"] == 300
    assert t["chiem_may_phut"] == 310                       # 10 khác + 300 chạy
    assert t["chiem_may_phut_min"] == 160                   # 10 + 5000/(1000×2)×60
    assert t["chiem_may_phut_max"] == 385                   # 10 + 5000/(400×2)×60
    assert t["dien_giai"]["co_dai_toc_do"] is True
    # Số người vẫn nhân vào CẢ BA mức: 4 người thì cả ba co lại đúng một nửa.
    t4 = _tlb(_buoc(
        loai_buoc="to", so_luong_vao=5000, nang_suat=500, so_nhan_cong=4, so_nhan_cong_toi_da=5,
        khoan_json={"nang_suat_nguoi_gio_min": 400, "nang_suat_nguoi_gio_max": 1000},
    ))
    assert t4["chay_phut"] == 150
    assert t4["chiem_may_phut_min"] == 75 and t4["chiem_may_phut_max"] == 187.5


def test_to_chua_khai_dai_thi_ba_muc_bang_nhau():
    """Định mức cũ (chưa khai min/max) → râu co về một điểm, KHÔNG bịa khoảng."""
    t = _tlb(_buoc(
        loai_buoc="to", so_luong_vao=5000, nang_suat=500, so_nhan_cong=2,
        khoan_json={"nang_suat_nguoi_gio": 500},
    ))
    assert t["chiem_may_phut"] == t["chiem_may_phut_min"] == t["chiem_may_phut_max"] == 300
    assert t["dien_giai"]["co_dai_toc_do"] is False


def test_dai_nang_suat_va_don_vi_khai_bao_theo_lenh_xuong_buoc(
    db, orders, lsx_svc, admin, customer
):
    """Khai dải năng suất ở định mức → bung lệnh là bước Tổ mang đủ, không phải khai lại.

    ĐƠN VỊ thì ngược lại: từ 10/08/2026 nó KHOÁ theo đơn giá khoán, người khai không đè được nữa
    (chủ: *"đơn vị này chỉ được theo đơn vị theo lương khoán và không được đổi"*). Dòng dưới cố ý
    khai đè `hop_gio` trong khi đơn giá khoán ghi `cái` — bước phải ra `cai_gio`, tức giá trị khai
    đè bị bỏ qua. Trước đó test này ghim chiều ngược lại (`hop_gio` thắng); đổi assert là do ĐỔI
    LUẬT, không phải nới test cho qua.

    🔴 15/08/2026: đơn vị THÔI là nhãn suông — thời lượng quy SL vào về chính đơn vị đó rồi mới
    chia. Ở ca này bước đếm `cai` và đơn giá khoán cũng `cái` nên tỉ số 1, mấy assert phút không
    đổi; ca lệch đơn vị có test riêng bên dưới.
    """
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp", don_vi="cái", don_gia=80,
                  nang_suat=500, ns_min=400, ns_max=1000, don_vi_ns="hop_gio")
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})

    dan = {cd.ten: cd for cd in hop.cong_doans}["Dán hộp"]
    # Khoá theo đơn giá khoán ("cái") — giá trị khai đè `hop_gio` KHÔNG thắng. Từ 15/08/2026 lưu
    # TÊN đơn vị chứ không phải mã `<đv>_gio`: thời lượng quy SL vào về chính đơn vị này.
    assert dan.don_vi_nang_suat == "cái"
    assert dan.khoan_json["nang_suat_nguoi_gio_min"] == 400
    assert dan.khoan_json["nang_suat_nguoi_gio_max"] == 1000
    t = _tl(dan, db)
    assert t["chiem_may_phut_min"] < t["chiem_may_phut"] < t["chiem_may_phut_max"]


def test_buoc_to_go_may_va_ba_moc_nhan_luc_sua_duoc(db, orders, lsx_svc, admin, customer):
    """Đổi bước sang TỔ: server gỡ máy, và ba mốc người sửa tay THẮNG định mức danh mục."""
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp", don_vi="cái", don_gia=80,
                  nang_suat=500)          # định mức: chuẩn 2 · tối đa 4
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    dan = {cd.ten: cd for cd in lsx.cong_doans}["Dán hộp"]
    dan.may_id = 1                                        # giả bộ bước đang dính một máy
    db.commit()

    rows = [
        LsxCongDoanIn(
            step_key=cd.step_key, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
            # Kế hoạch bấm "Tổ" cho bước dán — server không tự đoán nữa (xem `_chon_loai_buoc`).
            loai_buoc="to" if cd.ten == "Dán hộp" else cd.loai_buoc,
            department_id=cd.department_id, may_id=cd.may_id,
            **({"so_nhan_cong": 6, "so_nhan_cong_toi_thieu": 3, "so_nhan_cong_tieu_chuan": 5,
                "so_nhan_cong_toi_da": 9} if cd.ten == "Dán hộp" else {}),
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin)
    dan = {cd.ten: cd for cd in lsx.cong_doans}["Dán hộp"]
    assert dan.loai_buoc == "to" and dan.may_id is None   # Tổ ⇒ không giữ máy
    assert (dan.so_nhan_cong_toi_thieu, dan.so_nhan_cong_tieu_chuan, dan.so_nhan_cong_toi_da) \
        == (3, 5, 9)                                      # số gõ tay thắng định mức 2/4
    assert dan.so_nhan_cong == 6
    # 6 người vượt trần 9? không — trần là 9 nên tính đủ 6 người.
    assert _tl(dan, db)["dien_giai"]["so_nhan_cong_tinh"] == 6


def test_thieu_nang_suat_thi_khong_bia_so():
    """Chưa khai năng suất → thời gian chạy = 0, KHÔNG đoán bừa để Gantt khỏi vẽ số sai."""
    result = _tlb(_buoc(so_luong_vao=5000))    # bước máy CHƯA gán máy
    assert result["chay_phut"] == 0
    assert any("chưa khai tốc độ" in x for x in result["dien_giai"]["canh_bao"])


def test_mac_dinh_ke_thua_tu_danh_muc_cong_doan_va_may(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp", don_vi="cái", don_gia=80,
                  nang_suat=4000)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})

    b = {cd.ten: cd for cd in hop.cong_doans}
    # setup ← cong_doan.setup_time; năng suất ← may_thiet_bi. Vệ sinh/rửa mực đã gỡ khỏi hệ nên
    # bước sinh ra LUÔN 0 (cột `thoi_gian_rua_muc` cũng đã gỡ khỏi model 11/08/2026).
    assert float(b["In offset"].setup_phut) == 45
    # Bước MÁY không chép tốc độ lên bước nữa (15/08/2026) — `thoi_luong_buoc` đọc SỐNG từ máy,
    # nên cột ở đây để trống chứ không giữ một bản dễ lệch.
    assert b["In offset"].nang_suat is None and b["In offset"].don_vi_nang_suat is None
    assert float(b["In offset"].ve_sinh_phut) == 0
    assert float(b["Bế"].setup_phut) == 30 and float(b["Bế"].ve_sinh_phut) == 0
    # Bước Tổ lấy năng suất/người từ định mức đầu việc; đơn vị LÀ đơn vị của đơn giá khoán.
    assert float(b["Dán hộp"].nang_suat) == 4000
    assert b["Dán hộp"].don_vi_nang_suat == "cái" and b["Dán hộp"].may_id is None
    assert _tl(b["Dán hộp"], db)["chay_phut"] > 0
    # Hao hụt % KHÔNG kế thừa từ danh mục dù `cong_doan.spoilage_pct` = 2: module Bù hao đã bao cả
    # hao theo % (bậc `don_vi='pct'`, `tra_bac` quy về số tờ) và đã nằm trong `hao_hut` — lấy thêm
    # lần nữa là đếm hai lần. Ô này để trống cho người kế hoạch quyết tại lệnh.
    assert float(b["Dán hộp"].hao_hut_pct) == 0
    # Hao của mỗi bước lấy từ ĐỊNH MỨC của chính công đoạn (danh mục Bù hao). Fixture này KHÔNG
    # khai bù hao cho công đoạn nào ⇒ cả ba bước đều 0.
    #
    # Trước 15/08/2026 dòng này viết `assert hao_hut == hop.bu_hao_to`, mà `bu_hao_to` cũng bằng 0
    # ⇒ nó chỉ khẳng định `0 == 0`, chưa bao giờ chứng minh "cục hao gắn đúng bước in" như lời
    # comment. Cột `bu_hao_to` nay đã bỏ; muốn canh chuyện gắn-đúng-bước thì xem
    # `test_thanh_phan_engine.test_chip_sl_vao_bat_dung_so_to_cua_chinh_buoc`.
    assert float(b["In offset"].hao_hut) == 0
    assert float(b["Bế"].hao_hut) == 0 and float(b["Dán hộp"].hao_hut) == 0
    # Loại bước do NGƯỜI chọn: in giữ mặc định `may`, dán tay là "to" vì kế hoạch vừa bấm ở trên.
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


def test_doi_giay_tai_lenh_keo_theo_dinh_luong_va_ten(db, orders, lsx_svc, admin, customer):
    """Giấy PHẢI đổi được ngay tại lệnh, và định lượng đi theo giấy mới.

    Nghiệp vụ: giấy hết hàng thì xưởng thay loại khác cùng tính chất (có khi xịn hơn). Bắt quay về
    phiếu tính giá rồi tạo lại lệnh là mất sạch routing đã chỉnh — nên `giay_id` nằm trong bộ
    THÔNG SỐ sửa được của lệnh. Định lượng KHÔNG phải khai lại: nó là thuộc tính của giấy.
    """
    from app.schemas.lsx import LsxQuyCachIn

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    gsm_cu = (hop.quy_cach_json or {}).get("gsm")

    khac = GiayNguyen(ma="G-COUCHE400", ten="Couché 400", gsm=400, don_gia=31_000,
                      don_vi_gia="tan", cong_thuc_gia="so_luong * don_gia")
    db.add(khac)
    db.commit()

    hop = lsx_svc.update(
        lsx_id=hop.id, actor=admin,
        payload=LsxUpdateIn(quy_cach=LsxQuyCachIn(giay_id=khac.id)),
    )
    qc = hop.quy_cach_json
    assert qc["giay_id"] == khac.id
    # Định lượng + tên đi THEO giấy, không giữ số của cuộn giấy cũ.
    assert qc["gsm"] == 400 and qc["gsm"] != gsm_cu
    assert qc["giay_ten"] == "Couché 400"


def test_kiem_thieu_he_so_doc_theo_TRAM_khong_theo_MA_don_vi(
    db, orders, lsx_svc, admin, customer
):
    """Xưởng đặt tên đơn vị riêng ⇒ checklist VẪN phải chặn.

    Đơn vị là danh mục ĐỘNG: xưởng khai `to_chay` (trạm `to`) thay cho `to`. Ba phép kiểm nguồn hệ
    số phải hỏi CỜ TRẠM, không so mã. So mã thì trên dữ liệu thật `("to","cai") in cau` luôn False
    ⇒ ba cảnh báo im lặng ⇒ nút "Sẵn sàng lập kế hoạch" mở toang dù thiếu Con/tờ.

    Test cũ ngay trên KHÔNG bắt được vì fixture khai toàn mã mặc định (mã trùng trạm nên phép so
    khớp do trùng hợp). Đây là bản chạy với mã do xưởng đặt.
    """
    from app.models.don_vi_do import DonViDo

    ptg = _ptg_2_san_pham(db)
    # Khai ở màn "Đơn vị & quy đổi": mã riêng + cờ trạm dòng giấy.
    db.add_all([
        DonViDo(ma="to_chay", ten="TỜ CHẠY MÁY", tram_dong_giay="to"),
        DonViDo(ma="sp_xong", ten="SẢN PHẨM XONG", tram_dong_giay="cai"),
    ])
    # Màn "Công đoạn": trỏ vào/ra sang mã mới.
    doi = {"to": "to_chay", "cai": "sp_xong"}
    for cd in db.query(CongDoan).all():
        cd.don_vi_vao = doi.get(cd.don_vi_vao or "", cd.don_vi_vao)
        cd.don_vi_ra = doi.get(cd.don_vi_ra or "", cd.don_vi_ra)
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    assert {c.don_vi_vao for c in hop.cong_doans} & {"to_chay", "sp_xong"}, \
        "routing phải mang mã của xưởng, không thì test này không kiểm được gì"

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
            di_chuyen_phut=45, so_nhan_cong=3, bat_buoc=False,
        ),
    ])
    cd = lsx_svc.get(hop.id).cong_doans[0]
    assert cd.nha_cung_cap == "Cơ sở Tân Bình" and float(cd.don_gia_gia_cong) == 450
    assert cd.yeu_cau_ky_thuat == "Màng mờ, không bong mép"
    assert not hasattr(cd, "dieu_kien_json")
    # `di_chuyen_phut` đã rời hợp đồng lưu routing (2026-08-04) — cột còn trong DB nhưng client
    # không gửi được nữa, nên nó KHÔNG sống sót qua vòng lưu. Khối thuê ngoài
    # (nhà cung cấp · ngày gửi/nhận · đơn giá · yêu cầu kỹ thuật) mới là thứ phải giữ.
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
                  nang_suat=4000)
    to_id = _to_san_xuat(db).id
    can = CongDoan(ma="CD-CAN-T", ten="Cán màng bóng", nhom="finishing",
                   cong_thuc_gia="so_luong * don_gia", department_id=to_id, setup_time=20,
                   don_vi_vao="to", don_vi_ra="to")
    db.add(can)
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})
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


def test_mac_dinh_buoc_tra_kem_co_dong_giay(db, orders, lsx_svc, admin, customer):
    """Đổi công đoạn phải trả kèm cờ `tren_dong_giay` CỦA CẶP ĐƠN VỊ MỚI.

    Client áp `don_vi_vao`/`don_vi_ra` của công đoạn vừa chọn lên dòng đang sửa. Không trả kèm cờ
    thì dòng giữ cờ của công đoạn CŨ — mà frontend không tự suy lại được, vì trạm là cờ khai trên
    danh mục Đơn vị chứ không đọc ra từ mã.

    Hậu quả nếu thiếu: bước vừa đổi sang ghi kẽm (`m² → bài in`) vẫn tự nhận là nằm trên dòng giấy,
    nên bị đem so đơn vị với bước in ngay sau ⇒ cảnh báo "đứt đơn vị" GIẢ sống lại đúng lúc người
    dùng đang sửa. Xem `frontend/src/pages/lsxBuoc.loiDong` (+ `lsxBuoc.test.ts`).
    """
    ptg = _ptg_2_san_pham(db)
    to_id = _to_san_xuat(db).id
    ctp = CongDoan(ma="CD-CTP-T", ten="Ghi kẽm CTP", nhom="prepress",
                   cong_thuc_gia="so_luong * don_gia", department_id=to_id, setup_time=15,
                   don_vi_vao="m2", don_vi_ra="bai")
    xen = CongDoan(ma="CD-XEN-T", ten="Xén thành phẩm", nhom="finishing",
                   cong_thuc_gia="so_luong * don_gia", department_id=to_id, setup_time=10,
                   don_vi_vao="to", don_vi_ra="to")
    db.add_all([ctp, xen])
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [line["order_line_id"] for line in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    # `m² → bài in` là thước đo RIÊNG của khâu chế bản, không phải một chặng của dòng giấy.
    assert lsx_svc.mac_dinh_buoc(lsx_id=hop.id, cong_doan_id=ctp.id)["tren_dong_giay"] is False
    # `tờ → tờ` thì đứng trên dòng.
    assert lsx_svc.mac_dinh_buoc(lsx_id=hop.id, cong_doan_id=xen.id)["tren_dong_giay"] is True


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
    assert saved.may_id == may_moi.id
    # Tốc độ KHÔNG chép lên bước nữa (15/08/2026) — đổi máy là thời lượng tự đổi theo máy mới,
    # khỏi cần đồng bộ một bản chép.
    assert saved.nang_suat is None
    assert round(_tl(saved, db)["chay_phut"], 2) == round(
        float(saved.so_luong_vao) * 60 / 4000, 2)


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
    assert _tl(dan, db)["chay_phut"] == 0


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
    assert float(b["In offset"].setup_phut) == 45


def test_chay_phut_luon_la_so_dan_xuat_khong_bi_dong_bang(
    db, orders, lsx_svc, admin, customer
):
    """Vòng LƯU → ĐỌC → LƯU LẠI không được đóng băng thời gian chạy.

    Trước 2026-08-04 rủi ro là API trả số đã-tính vào chính ô gõ đè, client lưu ngược lại rồi
    năng suất hết tác dụng. Nay ô gõ đè ĐÃ BỎ: `chay_phut` luôn là DẪN XUẤT từ tốc độ máy, và
    `replace_routing` không nhận trường đó nữa — nên không còn đường nào đóng băng nó.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})

    ra = {c["ten"]: c for c in lsx_svc.detail_dict(hop)["cong_doans"]}
    assert ra["In offset"]["chay_phut"] > 0             # dẫn xuất từ tốc độ máy đang gán
    assert ra["In offset"]["chiem_may_phut"] > 0
    # Cột DB vẫn NULL: số hiển thị là tính-lúc-đọc, không ghi ngược vào bước.
    assert {c.ten: c for c in lsx_svc.get(hop.id).cong_doans}["In offset"].chay_phut is None

    # Client gửi lại đúng thứ nó nhận → cột vẫn NULL, số vẫn tính lại từ máy.
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten=c["ten"], nhom=c["nhom"], loai_buoc=c["loai_buoc"],
                      department_id=c["department_id"], may_id=c["may_id"],
                      so_luong_vao=c["so_luong_vao"], so_luong_ra=c["so_luong_ra"],
                      don_vi_vao=c["don_vi_vao"], don_vi_ra=c["don_vi_ra"],
                      he_so_quy_doi=c["he_so_quy_doi"], nang_suat=c["nang_suat"],
                      don_vi_nang_suat=c["don_vi_nang_suat"])
        for c in lsx_svc.detail_dict(hop)["cong_doans"]
    ])
    sau = {c.ten: c for c in lsx_svc.get(hop.id).cong_doans}
    assert sau["In offset"].chay_phut is None
    assert _tl(sau["In offset"], db)["chay_phut"] > 0

    # Bước TỔ khai năng suất muộn vẫn ăn ngay (tổ không lấy tốc độ từ máy).
    sau["Dán hộp"].nang_suat = 4000
    db.commit()
    assert _tl(lsx_svc.get(hop.id).cong_doans[-1], db)["chay_phut"] > 0


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
        cd.may_id, cd.nang_suat, cd.phat_sinh_phut = None, None, 0
    db.commit()
    assert "vuot_han_giao" not in lsx_svc.canh_bao_cua(lsx_svc.get(hop.id))

    # Bơm giờ bằng ô DUY NHẤT còn gõ được: 200 giờ ⇒ 25 ngày > 10 ngày còn lại.
    hop.cong_doans[0].phat_sinh_phut = 200 * 60
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


# ===================== Thuê ngoài: sổ giao – nhận thực tế =====================
# Hàng ra khỏi cổng phải có tên người và số thực. Việc này xảy ra lúc lệnh ĐANG CHẠY, nên nó đi
# qua cửa THỰC THI riêng — không dùng chung cửa với sửa cấu hình routing.


def _lenh_co_buoc_thue_ngoai(db, orders, lsx_svc, admin, customer):
    """1 lệnh có bước cuối là gia công ngoài, đã khai dự kiến (gửi 20.500, cho phép hụt 100)."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop, _tem = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(ten="In offset", nhom="print", don_vi_vao="to"),
        LsxCongDoanIn(ten="Cán màng", nhom="finishing", loai_buoc="thue_ngoai",
                      nha_cung_cap="Cơ sở Tân Bình", sl_gui=20_500,
                      ngay_gui_dk=date.today() - timedelta(days=5),
                      ngay_nhan_dk=date.today() - timedelta(days=2),
                      hao_hut_cho_phep=100, don_gia_gia_cong=500),
    ])
    lsx = lsx_svc.get(hop.id)
    return lsx, next(cd for cd in lsx.cong_doans if cd.loai_buoc == "thue_ngoai")


def _gn(su_kien: str, **kw):
    from app.schemas.lsx import LsxGiaoNhanIn

    return LsxGiaoNhanIn(su_kien=su_kien, **kw)


def test_ghi_giao_nhan_van_chay_khi_lenh_da_lap_ke_hoach(db, orders, lsx_svc, admin, customer):
    """LÝ DO TỒN TẠI của cửa riêng: giao hàng xảy ra SAU khi đã lập kế hoạch.

    Đi chung cửa với `replace_routing` thì bắt kế hoạch gỡ lịch cả lệnh chỉ để ghi một dòng
    "đã giao 20.500 lúc 14h" — tức ghi không nổi đúng lúc cần ghi nhất.
    """
    lsx, buoc = _lenh_co_buoc_thue_ngoai(db, orders, lsx_svc, admin, customer)
    lsx.trang_thai = TT_DA_LAP_KE_HOACH
    db.commit()

    # Cửa cấu hình bị khoá...
    with pytest.raises(LsxConflict):
        lsx_svc.replace_routing(lsx_id=lsx.id, actor=admin, rows_in=[
            LsxCongDoanIn(ten="In offset", nhom="print", don_vi_vao="to"),
        ])
    # ...nhưng cửa thực thi thì không.
    lsx_svc.ghi_giao_nhan(lsx_id=lsx.id, buoc_id=buoc.id, payload=_gn("giao"), actor=admin)

    d = lsx_svc.detail_dict(lsx_svc.get(lsx.id))
    row = next(c for c in d["cong_doans"] if c["loai_buoc"] == "thue_ngoai")
    assert row["giao_nhan_trang_thai"] == "dang_ngoai"
    assert row["nguoi_giao_id"] == admin.id and row["giao_luc"] is not None
    assert float(row["sl_giao_thuc"]) == 20_500          # để trống → lấy số gửi dự kiến


def test_giao_nhan_chi_cho_buoc_thue_ngoai(db, orders, lsx_svc, admin, customer):
    lsx, _ = _lenh_co_buoc_thue_ngoai(db, orders, lsx_svc, admin, customer)
    buoc_may = next(cd for cd in lsx.cong_doans if cd.loai_buoc != "thue_ngoai")
    with pytest.raises(LsxValidationError):
        lsx_svc.ghi_giao_nhan(lsx_id=lsx.id, buoc_id=buoc_may.id, payload=_gn("giao"), actor=admin)


def test_nhan_ve_hut_vuot_dinh_muc_va_tien_tinh_theo_so_nhan(db, orders, lsx_svc, admin, customer):
    """Trả tiền cho hàng CẦM VỀ ĐƯỢC, không phải hàng gửi đi. Hụt vượt định mức thì nói ra."""
    lsx, buoc = _lenh_co_buoc_thue_ngoai(db, orders, lsx_svc, admin, customer)
    lsx_svc.ghi_giao_nhan(lsx_id=lsx.id, buoc_id=buoc.id,
                          payload=_gn("giao", so_luong=20_500), actor=admin)
    lsx_svc.ghi_giao_nhan(lsx_id=lsx.id, buoc_id=buoc.id,
                          payload=_gn("nhan", so_luong=20_300), actor=admin)

    row = next(c for c in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
               if c["loai_buoc"] == "thue_ngoai")
    assert row["giao_nhan_trang_thai"] == "da_ve"
    assert row["so_hut"] == 200                       # 20.500 − 20.300
    assert row["hut_vuot_dinh_muc"] is True           # cho phép 100
    assert row["tien_gia_cong_thuc"] == 20_300 * 500  # theo SỐ NHẬN
    assert row["qua_han_ngay"] is None                # về rồi thì không còn "quá hạn"


def test_dang_o_ngoai_qua_han_dem_theo_ngay_nhan_du_kien(db, orders, lsx_svc, admin, customer):
    lsx, buoc = _lenh_co_buoc_thue_ngoai(db, orders, lsx_svc, admin, customer)
    row = next(c for c in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
               if c["loai_buoc"] == "thue_ngoai")
    assert row["giao_nhan_trang_thai"] == "chua_gui" and row["qua_han_ngay"] is None

    lsx_svc.ghi_giao_nhan(lsx_id=lsx.id, buoc_id=buoc.id, payload=_gn("giao"), actor=admin)
    row = next(c for c in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
               if c["loai_buoc"] == "thue_ngoai")
    assert row["qua_han_ngay"] == 2                   # hẹn về 2 hôm trước, chưa nhận


# ===================== Chế bản lấy được tốc độ máy ghi kẽm =====================
# Trước đây luật bắt cứng "bước phải đếm TỜ" nên bước chế bản (đếm KẼM, đứng ngoài dòng giấy)
# KHÔNG BAO GIỜ lấy được tốc độ máy: ghi 4 kẽm hay 40 kẽm cũng ra thời lượng bằng đúng thời gian
# chuẩn bị, và lead-time cả lệnh hụt phần chế bản.


class _May:
    def __init__(self, toc_do, don_vi):
        self.toc_do, self.don_vi_toc_do = toc_do, don_vi


class _Cd:
    def __init__(self, nhom):
        self.nhom = nhom


def test_che_ban_lay_toc_do_may_ghi_kem():
    """Đơn vị của tốc độ đọc từ mã `<đv>_gio` của máy — nguồn duy nhất.

    🔴 ĐỔI 15/08/2026: trước đây `_nang_suat_buoc` so mã rồi TRẢ VỀ (None, None) khi lệch, tức là
    vứt luôn tốc độ của một cái máy có thật. Hàm đó đã gỡ: nay lệch đơn vị thì đi QUY ĐỔI
    (`_sl_theo_don_vi`), quy đổi không được mới thôi — và nói rõ lý do thay vì im lặng.
    """
    from app.services.lsx_service import ma_don_vi_toc_do

    assert ma_don_vi_toc_do(_May(20, "kem_gio")) == "kem"
    assert ma_don_vi_toc_do(_May(5000, "to_gio")) == "to"
    assert ma_don_vi_toc_do(_May(5000, None)) is None


def test_thoi_luong_che_ban_chay_theo_so_kem():
    """4 kẽm @ 20 kẽm/giờ = 12 phút ghi; cộng 10 phút chuẩn bị của MÁY CTP → 22 phút."""
    ctp = _may_gia(toc_do=20, chuan_bi=10, don_vi="kem_gio")
    b = _buoc(ten="Ghi kèm CTP", loai_buoc="may", nhom="prepress", so_luong_vao=4,
              don_vi_vao=None)
    t = _tlb(b, ctp, "kẽm")
    assert round(t["chay_phut"]) == 12
    assert round(t["chiem_may_phut"]) == 22
    # Gấp 10 lần số kẽm thì thời gian ghi cũng gấp 10 — trước đây cả hai đều ra 10 phút.
    b10 = _buoc(ten="Ghi kèm CTP", loai_buoc="may", nhom="prepress", so_luong_vao=40,
                don_vi_vao=None)
    assert round(_tlb(b10, ctp, "kẽm")["chay_phut"]) == 120


def test_ba_con_so_theo_dai_toc_do_may():
    """Công thức chốt 2026-08-04 — ba con số chỉ khác nhau ở MẪU SỐ (tốc độ max/TB/min).

    Số thật của máy 5 màu Mitsubishi: chuẩn bị 55' (4 khoản) · tốc độ 8.000/11.000/15.000."""
    khoan = [{"ten": "Đổi kẽm", "phut": 15}, {"ten": "Canh màu", "phut": 15},
             {"ten": "Lên giấy", "phut": 10}, {"ten": "Pha mực", "phut": 15}]
    may = _may_gia(toc_do=11_000, toc_do_min=8_000, toc_do_max=15_000, chuan_bi=55, khoan=khoan)
    t = _tlb(_buoc(loai_buoc="may", so_luong_vao=20_000, don_vi_vao="to"), may)
    assert round(t["chiem_may_phut"]) == 164        # 55 + 20.000×60÷11.000
    assert round(t["chiem_may_phut_min"]) == 135    # tốc độ TỐI ĐA ⇒ thời lượng NHỎ nhất
    assert round(t["chiem_may_phut_max"]) == 205
    # Chuẩn bị là hằng ⇒ độ rộng râu = đúng dao động của phần CHẠY, không dính setup.
    dg = t["dien_giai"]
    assert round(dg["chay_phut_max"] - dg["chay_phut_min"]) == 70
    assert dg["co_dai_toc_do"] is True
    # Chuẩn bị xổ CHI TIẾT cho drawer, không chỉ một cục tổng.
    assert [k["ten"] for k in dg["chuan_bi_khoan"]] == ["Đổi kẽm", "Canh màu", "Lên giấy", "Pha mực"]
    assert sum(k["phut"] for k in dg["chuan_bi_khoan"]) == 55


def test_may_chua_khai_dai_thi_ba_so_bang_nhau():
    """Máy chỉ khai tốc độ TB ⇒ râu co về một điểm — KHÔNG bịa khoảng."""
    t = _tlb(_buoc(loai_buoc="may", so_luong_vao=5_000, don_vi_vao="to"),
                        _may_gia(toc_do=5_000, chuan_bi=30))
    assert t["chiem_may_phut"] == t["chiem_may_phut_min"] == t["chiem_may_phut_max"] == 90
    assert t["dien_giai"]["co_dai_toc_do"] is False


def test_chua_quy_doi_duoc_thi_KHONG_bia_gio():
    """⭐ Bước đếm `tờ`, máy khai `tấn/giờ`, không quy đổi được ⇒ **không có số**, nêu lý do.

    🔴 ĐỔI 15/08/2026 — chỗ này trước đây chốt điều NGƯỢC LẠI ("chỉ lấy CON SỐ, không kiểm nhãn"),
    nên 20.000 tờ chia 11.000 tấn/giờ ra 109 phút trông như thật. Chủ bắt lỗi ở ca `500 kg/h` nhận
    số tờ. Nay quy đổi được thì tính, không được thì thôi — thà trống còn hơn một con số không ai
    đi kiểm. Chuẩn bị của máy vẫn còn vì nó không phụ thuộc số lượng.
    """
    t = thoi_luong_buoc(_buoc(loai_buoc="may", so_luong_vao=20_000, don_vi_vao="to"),
                        _may_gia(toc_do=11_000, chuan_bi=55, don_vi="tan_gio"))
    assert t["chay_phut"] == 0
    assert round(t["chiem_may_phut"]) == 55                  # chỉ còn chuẩn bị
    assert t["dien_giai"]["phuong_phap"] == "chua_quy_doi"
    assert any("quy đổi" in c for c in t["dien_giai"]["canh_bao"])


# --- Khuôn của bước: hai nhánh gán-cũ / làm-mới (mg 0205, 16/08/2026) ----------------


def _lenh_don_gian(db, orders, lsx_svc, admin, customer):
    """Một lệnh bất kỳ CỦA `customer` — đủ để kiểm hai nhánh khuôn."""
    d = _don_da_chuyen_sx(db, orders, admin, customer, _ptg_sach(db))
    line = lsx_svc.preview(d.id)["lines"][0]
    return lsx_svc.get(
        lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]], actor=admin)[0].id
    )


def test_khuon_chon_duoc_LOC_theo_khach_cua_lenh(db, orders, lsx_svc, admin, customer):
    """Ô chọn dao chỉ bày dao CỦA KHÁCH NÀY.

    Đây là thứ làm nhánh "dùng dao có sẵn" dùng được: kho vài trăm dao mà bày hết thì người ta
    tìm không ra, bấm "làm dao mới", rồi đặt lại con dao đã có — mất tiền thật.
    """
    from app.models.khuon_be import KhuonBe

    lsx = _lenh_don_gian(db, orders, lsx_svc, admin, customer)
    khac = Customer(code="KH-KHAC", name="Khách khác")
    db.add(khac)
    db.flush()
    db.add_all([
        KhuonBe(ma="KB-A", ten="Dao của khách này", khach_hang_id=customer.id, loai="khuon_be"),
        KhuonBe(ma="KB-B", ten="Dao khách khác", khach_hang_id=khac.id, loai="khuon_be"),
        KhuonBe(ma="KB-C", ten="Dao chưa gán khách", loai="khuon_be"),
    ])
    db.commit()

    ma = {k["ma"] for k in lsx_svc.khuon_chon_duoc(lsx, loai=None, dang_chon=None)}
    assert ma == {"KB-A"}, ma


def test_khuon_dang_chon_LUON_con_trong_danh_sach(db, orders, lsx_svc, admin, customer):
    """Dao đã gán từ trước phải ở lại dù không khớp bộ lọc.

    Dao cũ có thể khai thiếu khách/loại. Rơi khỏi danh sách thì ô chọn nhảy về rỗng và cú Lưu kế
    tiếp GỠ MẤT dao của bước — đúng bẫy đã gặp ở ô chọn khuôn đời trước.
    """
    from app.models.khuon_be import KhuonBe

    lsx = _lenh_don_gian(db, orders, lsx_svc, admin, customer)
    mo_coi = KhuonBe(ma="KB-CU", ten="Dao đời cũ, chưa khai khách")
    db.add(mo_coi)
    db.commit()

    ds = lsx_svc.khuon_chon_duoc(lsx, loai="khuon_be", dang_chon=mo_coi.id)
    assert [k["ma"] for k in ds] == ["KB-CU"]


def test_tao_khuon_moi_lay_khach_TU_LENH_va_vao_kho_o_trang_thai_dang_dat(
    db, orders, lsx_svc, admin, customer,
):
    """Nhánh "làm dao mới": khách + loại KHÔNG hỏi lại người dùng, lấy từ lệnh và từ bước."""
    from datetime import date as _date

    from app.models.khuon_be import KhuonBe

    lsx = _lenh_don_gian(db, orders, lsx_svc, admin, customer)
    ra = lsx_svc.tao_khuon_cho_lenh(
        lsx, ten="Hộp bánh trung thu 20×20", loai="khuon_be",
        ngay_ve=_date(2026, 8, 20), actor=admin,
    )
    assert ra["ma"].startswith("KB-")          # mã do danh mục sinh, không phải tự đặt
    assert ra["tinh_trang"] == "dang_dat_lam"

    k = db.get(KhuonBe, ra["id"])
    assert k.khach_hang_id == customer.id      # lấy từ lệnh
    assert k.loai == "khuon_be"                # lấy từ cờ của bước
    assert k.ngay_ve_du_kien == _date(2026, 8, 20)

    # Và nó xuất hiện ngay trong danh sách chọn của chính lệnh đó.
    assert ra["id"] in {x["id"] for x in lsx_svc.khuon_chon_duoc(lsx, loai="khuon_be", dang_chon=None)}
