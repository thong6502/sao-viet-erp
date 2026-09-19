"""Lệnh sản xuất (LSX) — service-level tests.

Luồng thật: đơn từ báo giá → thu đủ cọc → chốt → Sale "Chuyển xuống sản xuất" → Kế hoạch preview
→ tạo lệnh → sửa routing → đánh dấu sẵn sàng. Mỗi DÒNG ĐƠN đúng 1 lệnh, lệnh ngang hàng.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from math import ceil
from types import SimpleNamespace

import pytest

from tests.conftest import phien_da_seed

from app.db import engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan, CongDoanMay, CongDoanVatTu
from app.models.customer import Customer
from app.models.department import Department
from app.models.lsx import (
    TT_DA_LAP_KE_HOACH,
    TT_NHAP,
    TT_SAN_SANG,
    LsxCongDoan,
)
from app.models.may_thiet_bi import MayThietBi
from app.models.phieu_tinh_gia import (
    PhieuChiPhiKhac,
    PhieuThanhPhan,
    PhieuThanhPham,
    PhieuTinhGia,
)
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
from app.schemas.lsx import BuocMacDinhOut, LsxCongDoanIn, LsxUpdateIn
from app.schemas.order import OrderCreate, OrderDepositReceiptIn, OrderUpdate
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
    yield from phien_da_seed()


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
                 department_ids=[to_id], don_vi_vao="to", don_vi_ra="to"),
        CongDoan(ma="CD-GAP-S", ten="Gấp tay sách", nhom="finishing",
                 cong_thuc_gia="so_luong * don_gia", department_ids=[to_id],
                 don_vi_vao="to", don_vi_ra="to"),
        CongDoan(ma="CD-KEO-S", ten="Bắt tay + vào keo", nhom="finishing",
                 cong_thuc_gia="so_luong * don_gia", department_ids=[to_id],
                 don_vi_vao="to", don_vi_ra="cai"),
        # Hao 50 CUỐN ở bước xén — để kiểm nó lội ngược qua cầu ra đúng 500 TỜ.
        CongDoan(ma="CD-XEN-S", ten="Xén 3 mặt", nhom="finishing",
                 cong_thuc_gia="so_luong * don_gia", department_ids=[to_id],
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
            cong_thuc_gia="so_luong * don_gia", department_ids=[to_id],
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
    doi = {"so_con": "con", "so_luong": "so_luong", "to_dau_vao": "to_dau_vao",
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

    for bien, o_phieu in (("so_luong", "so_luong"), ("so_con", "con"),
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
    _viec_khoan_cho_to(db, to.id)
    return to


def _viec_khoan_cho_to(db, to_id: int):
    """Tổ phải có ÍT NHẤT một công việc khoán còn dùng — cổng "Sẵn sàng lập kế hoạch" đòi thế
    từ 18/09/2026 (`thieu_viec_khoan_to`), vì bàn tổ ghi mẻ theo công việc khoán. Fixture nào chỉ
    muốn kiểm điều kiện KHÁC thì phải qua được cổng này sẵn."""
    from app.models.piece_work import PieceRate

    for r in db.query(PieceRate).filter(PieceRate.active.is_(True)).all():
        if to_id in (r.department_ids or []):
            return r
    r = PieceRate(ma=f"VK-T{to_id}", ten="Việc khoán test", unit="cai", unit_price=100)
    r.department_ids = [to_id]
    db.add(r)
    db.flush()
    return r


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
    if not cd_in.department_ids:
        cd_in.department_ids = [to_id]
    cd_in.setup_time = 45          # chuẩn bị máy in 45 phút
    # Đơn vị KHAI ở danh mục — lệnh chỉ kế thừa. Không khai = bước không chạm giấy (chế bản).
    cd_in.don_vi_vao = cd_in.don_vi_ra = "to"
    db.flush()
    # Đơn vị vào/ra là KHAI BÁO, không suy từ tên: bế = ranh giới tờ in → con, dán hộp đếm con.
    # `requires_tooling` cũng vậy — checklist "thiếu khuôn" đọc CỜ này, không dò chữ "bế" trong tên
    # (công đoạn do người dùng khai lúc chạy, tên gì cũng có thể).
    cd_be = CongDoan(ma="CD-BE-T", ten="Bế", nhom="finishing", cong_thuc_gia="so_luong * don_gia",
                     department_ids=[to_id], setup_time=30, don_vi_vao="to", don_vi_ra="cai",
                     requires_tooling=True, tooling_type="khuon_be")
    # Dán hộp = bước LÀM TAY: không gắn máy, nên năng suất phải tới từ danh mục công đoạn.
    # `spoilage_pct=2` để nguyên làm bằng chứng NGƯỢC: routing không được kế thừa nó (module Bù hao
    # đã lo phần hao) — xem assert `hao_hut_pct == 0` ở test kế thừa mặc định.
    cd_dan = CongDoan(ma="CD-DAN-T", ten="Dán hộp", nhom="finishing",
                      cong_thuc_gia="so_luong * don_gia", department_ids=[to_id], spoilage_pct=2,
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
    # Số báo giá đánh số tăng dần: có test cần DỰNG HAI ĐƠN trong cùng một ca, để mã cứng là
    # đụng ràng buộc unique `quotes.quote_number`.
    q = Quote(quote_number=f"BG-SX{db.query(Quote).count() + 1}", customer_id=customer.id,
              status=STATUS_ACCEPTED,
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
    assert not any(r["order_id"] == d.id for r in lsx_svc.hang_cho()[0])  # chốt rồi nhưng chưa chuyển

    orders.release_production(order_id=d.id, actor=admin, scope="all")

    row = next(r for r in lsx_svc.hang_cho()[0] if r["order_id"] == d.id)
    assert row["so_dong"] == 2 and row["so_dong_co_lsx"] == 0

    lines = lsx_svc.preview(d.id)["lines"]
    lsx_svc.tao(order_id=d.id, order_line_ids=[l["order_line_id"] for l in lines], actor=admin)
    assert not any(r["order_id"] == d.id for r in lsx_svc.hang_cho()[0])  # đủ lệnh → rời hàng chờ


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


def test_lenh_khong_mang_chi_phi_khac_cua_phieu_tinh_gia(db, orders, lsx_svc, admin, customer):
    """Khoản CHI PHÍ KHÁC (tên tự gõ + số tiền) là tiền nội bộ của giá vốn — xuống lệnh là hết.

    Hai bài `test_khong_lo_tien` ở tầng API cấm chuỗi "chi_phi" trong body, nhưng fixture của chúng
    không có khoản nào nên xanh cả khi lọt. Bài này dựng phiếu CÓ khoản "làm kẽm" thật: khoá không
    được có trong `quy_cach` (preview lẫn ảnh chụp lệnh), và cả CÁI TÊN cũng không được đi theo —
    tên gõ tay đứng một mình vẫn cho thợ biết đơn này gánh thêm một khoản.
    """
    ptg = _ptg_2_san_pham(db)
    ptg.thanh_phans[0].chi_phi_khacs.append(
        PhieuChiPhiKhac(thu_tu=0, ten="làm kẽm ngoài", so_tien=800_000)
    )
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    dong = lsx_svc.preview(d.id)["lines"][0]
    assert "chi_phi_khacs" not in dong["quy_cach"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[dong["order_line_id"]], actor=admin)[0]

    qc = lsx.quy_cach_json or {}
    assert not any(k.startswith("chi_phi") for k in qc), sorted(qc)
    toan_bo = json.dumps(
        [dong, qc, lsx_svc.detail_dict(lsx)], ensure_ascii=False, default=str
    ).lower()
    assert "làm kẽm ngoài" not in toan_bo
    assert "800000" not in toan_bo.replace(".0", "")


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


def test_dong_khong_co_phieu_tinh_gia_van_tao_duoc_lenh(db, orders, lsx_svc, admin, customer):
    """Dòng đơn không gắn phiếu tính giá (đơn nhập giá tay) → lệnh vẫn tạo được, quy cách trống.

    Từ 07/09/2026 bảng lệnh dự kiến KHÔNG còn chấm checklist thiếu: payload không có `thieu` và
    lệnh sinh ra ở NHÁP. Cửa gác còn lại là `thieu_cua` — nó vẫn kêu `khong_co_ptg` nên nút
    "Sẵn sàng lập kế hoạch" vẫn đóng cho tới khi kế hoạch khai đủ."""
    from app.models.order import OrderLine

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ol = db.query(OrderLine).filter(OrderLine.order_id == d.id).order_by(OrderLine.id).first()
    ol.phieu_thanh_phan_id = None
    db.commit()

    pv = next(l for l in lsx_svc.preview(d.id)["lines"] if l["order_line_id"] == ol.id)
    assert "thieu" not in pv and pv["routing"] == []
    # Chưa có bài tính giá → số dẫn xuất là "chưa tính được" = None (UI hiện "—"), KHÔNG bày 0/1 giả.
    assert pv["bu_hao_to"] is None and pv["so_to_ke_hoach"] is None and pv["so_to_nguyen"] is None
    assert pv["so_con"] is None and pv["so_kem"] is None and pv["so_luot"] is None
    [lsx] = lsx_svc.tao(order_id=d.id, order_line_ids=[ol.id], actor=admin)
    assert lsx.trang_thai == TT_NHAP and lsx.so_luong_dat == ol.qty
    assert lsx.cong_doans == []
    assert "khong_co_ptg" in lsx_svc.thieu_cua(lsx)
    with pytest.raises(LsxConflict):
        lsx_svc.set_trang_thai(lsx_id=lsx.id, trang_thai=TT_SAN_SANG, actor=admin)


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
    # Client gửi NỬA cặp đơn vị (chỉ `don_vi_vao`) thì đó chưa phải lời khai: bước vẫn kế thừa
    # như cũ — bốn dòng trên đều tự thêm (không `cong_doan_id`) nên nối tiếp đơn vị bước trước,
    # ra pass-through "to", KHÔNG phải "cai" mà client gửi. Khai ĐỦ CẢ HAI ô mới giữ được số của
    # mình, xem `tests/test_lsx_buoc_khai_tay.py` (10/09/2026).
    assert hop2.cong_doans[-1].don_vi_ra == "to"
    assert [cd.thu_tu for cd in hop2.cong_doans] == [0, 1, 2, 3]

    assert [cd.ten for cd in lsx_svc.get(tem.id).cong_doans] == tem_truoc      # lệnh khác nguyên vẹn
    tp = db.query(PhieuThanhPhan).filter(PhieuThanhPhan.id == hop.phieu_thanh_phan_id).first()
    assert [r.ten for r in tp.thanh_phams] == ["In offset", "Bế", "Dán hộp"]   # PTG nguyên vẹn


def test_sua_routing_bi_chan_khi_don_da_huy(db, orders, lsx_svc, admin, customer):
    """Đơn hủy rồi thì khóa hẳn routing — chặn ở tầng service, không chỉ ẩn trên UI."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop, _tem = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)

    from app.models.order import FAULT_KHACH

    orders.cancel(order_id=d.id, actor=admin, scope="all", reason="Khách đổi ý",
                  fault=FAULT_KHACH, can_cancel_ordered=True)

    with pytest.raises(LsxConflict):
        lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
            LsxCongDoanIn(ten="In offset", nhom="print", don_vi_vao="to"),
        ])


def _gan_dao_cho_buoc_can(db, lsx):
    """Trỏ một con dao cho MỌI bước cần dụng cụ — cửa "Sẵn sàng" đòi đủ khuôn từ 04/09/2026.

    Danh mục công đoạn seed sẵn đã có bước bật `requires_tooling` (bế/ép), nên lệnh dựng từ fixture
    mặc định là thiếu khuôn. Test nào chỉ muốn kiểm điều kiện KHÁC thì gọi hàm này để dọn đường,
    thay vì nới điều kiện thật ở service.
    """
    from app.models.cong_doan import CongDoan
    from app.models.khuon_be import KhuonBe

    can = {
        r.id for r in db.query(CongDoan).all()
        if r.requires_tooling and r.tooling_type in ("khuon_be", "khuon_ep", "khung_lua")
    }
    if not any(cd.cong_doan_id in can for cd in lsx.cong_doans):
        return
    dao = KhuonBe(ma=f"KB-TEST-{lsx.id}", ten="Dao test", loai="khuon_be",
                  tinh_trang="dang_dung")
    db.add(dao)
    db.flush()
    for cd in lsx.cong_doans:
        if cd.cong_doan_id in can:
            cd.khuon_be_id = dao.id
    db.commit()


def test_san_sang_bi_chan_khi_con_thieu_va_mo_khi_du(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    [hop, _tem] = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    _gan_dao_cho_buoc_can(db, hop)

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


def test_to_CHUA_CO_viec_khoan_thi_khong_san_sang_duoc(db, orders, lsx_svc, admin, customer):
    """⭐ §5.4 (chủ chốt 18/09/2026): *"tổ chưa có công việc khoán thì không nhấn được nút sẵn sàng
    lập kế hoạch đâu"*. Thợ mở bàn tổ ra mà danh sách việc rỗng thì không ghi nổi một mẻ nào.

    Soi CẢ bước MÁY (tổ đứng máy cũng ghi mẻ ở bàn tổ); chỉ THUÊ NGOÀI miễn.
    """
    from app.models.piece_work import PieceRate

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    _gan_dao_cho_buoc_can(db, hop)
    hop = lsx_svc.get(hop.id)
    assert lsx_svc.thieu_cua(hop) == []

    # Ngừng dùng mọi việc khoán của tổ ⇒ cổng đóng, kể cả khi mọi bước đều là MÁY.
    for r in db.query(PieceRate).all():
        r.active = False
    db.commit()
    lsx_svc._rates_cache = None
    hop = lsx_svc.get(hop.id)
    assert {cd.loai_buoc for cd in hop.cong_doans} == {"may"}
    assert "thieu_viec_khoan_to" in lsx_svc.thieu_cua(hop)
    # Màn lệnh gọi ĐÍCH DANH tổ thiếu (mỗi tổ một lần, theo thứ tự bước), không câu chung chung.
    ten_to = lsx_svc.to_thieu_viec_khoan(hop)
    assert ten_to and len(ten_to) == len(set(ten_to))
    assert lsx_svc.detail_dict(hop)["to_thieu_viec_khoan"] == ten_to
    with pytest.raises(LsxConflict):
        lsx_svc.set_trang_thai(lsx_id=hop.id, trang_thai=TT_SAN_SANG, actor=admin)

    # THUÊ NGOÀI miễn: việc làm ở xưởng người ta, thợ của tổ không ghi mẻ theo việc khoán.
    for cd in hop.cong_doans:
        cd.loai_buoc = "thue_ngoai"
    db.commit()
    assert "thieu_viec_khoan_to" not in lsx_svc.thieu_cua(lsx_svc.get(hop.id))

    # Bật lại việc khoán ⇒ cổng mở cho bước TỔ.
    for cd in hop.cong_doans:
        cd.loai_buoc = "to"
    for r in db.query(PieceRate).all():
        r.active = True
    db.commit()
    lsx_svc._rates_cache = None
    assert "thieu_viec_khoan_to" not in lsx_svc.thieu_cua(lsx_svc.get(hop.id))
    assert lsx_svc.to_thieu_viec_khoan(lsx_svc.get(hop.id)) == []


def _khai_ct_gio(db, lsx_svc, cong_doan_id, may_id, ct: str) -> None:
    """Khai công thức GIỜ CHẠY ở cặp (công đoạn × máy) — chỗ mới từ 06/09/2026.

    `_ct_gio_cache` phải xoá theo: service nhớ lại kết quả tra để khỏi N+1, mà ở đây danh mục đổi
    GIỮA hai lần tính — chuyện chỉ xảy ra trong test, một request thật không sửa danh mục giữa chừng.
    """
    from app.models.cong_doan import CongDoanMay

    db.add(CongDoanMay(cong_doan_id=cong_doan_id, may_id=may_id, cong_thuc_gio=ct))
    db.commit()
    getattr(lsx_svc, "_ct_gio_cache", {}).clear()


def test_thoi_gian_buoc_MAY_doc_cong_thuc_cua_CHINH_MAY(
    db, orders, lsx_svc, admin, customer,
):
    """⭐ Máy khai `m²/giờ`, bước đếm `tờ`, không có cầu ⇒ chạy công thức của CẶP công đoạn × máy.

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
    db.commit()
    # tờ 65×86 = 0,559 m² — khai ở cặp (công đoạn × máy), không còn ở riêng máy.
    _khai_ct_gio(db, lsx_svc, may_in.cong_doan_id, may.id, "sl_vao * 0.559")

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
    assert not any(r["order_id"] == d.id for r in lsx_svc.hang_cho()[0])

    xoa_id = created[0].id
    assert lsx_svc.xoa(lsx_id=xoa_id, actor=admin) == d.id
    row = next(r for r in lsx_svc.hang_cho()[0] if r["order_id"] == d.id)
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

    r = PieceRate(department_ids=[department_id] if department_id else [], ten=ten, unit=don_vi,
                  unit_price=don_gia, active=True)
    db.add(r)
    db.commit()
    return r


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


def _ptg_mot_buoc_in(db, *, may_cua_phieu, may_lam_duoc) -> PhieuTinhGia:
    """PTG một thành phần, routing đúng 2 bước In → Bế, để soi MÁY điền sẵn ở bước In.

    `may_lam_duoc` là bảng "Máy chạy được công đoạn này" của công đoạn In — nó KHÁC danh sách máy
    ô "Máy in" của phiếu mời chọn (phiếu mời HỢP của mọi công đoạn nhóm In), nên hai thứ lệch nhau
    là chuyện thường ngày chứ không phải dữ liệu hỏng.
    """
    giay = GiayNguyen(ma="G-MAYIN", ten="Giấy máy in", gsm=300, don_gia=25_000, don_vi_gia="tan",
                      cong_thuc_gia="to_nguyen * dai_nguyen * rong_nguyen * dinh_luong * don_gia / 1000")
    db.add(giay)
    to_id = _to_san_xuat(db).id
    cd_in = CongDoan(ma="CD-IN-M", ten="In AB", nhom="print", department_ids=[to_id],
                     don_vi_vao="to", don_vi_ra="to", cong_thuc_gia="so_luong * don_gia")
    cd_be = CongDoan(ma="CD-BE-M", ten="Bế", nhom="finishing", department_ids=[to_id],
                     don_vi_vao="to", don_vi_ra="to", cong_thuc_gia="so_luong * don_gia")
    db.add_all([cd_in, cd_be])
    db.flush()
    for m in may_lam_duoc:
        db.add(CongDoanMay(cong_doan_id=cd_in.id, may_id=m.id, cong_thuc_gio="sl_vao"))
    db.flush()

    p = PhieuTinhGia(ma="PTG-MAYIN-0001", ten_san_pham="Thẻ nhân viên", so_luong=500)
    tp = PhieuThanhPhan(
        thu_tu=0, ten="Thẻ nhân viên", so_luong=500, don_vi_tinh="cái",
        dai_thanh_pham=86, rong_thanh_pham=54, giay_id=giay.id,
        kho_nguyen_dai=860, kho_nguyen_rong=650, kho_in_dai=860, kho_in_rong=650,
        so_mau_a=4, so_mau_b=1, quy_cach_in="hai_mat", co_in=True,
        may_id=(may_cua_phieu.id if may_cua_phieu is not None else None),
    )
    for i, cd in enumerate((cd_in, cd_be)):
        tp.thanh_phams.append(PhieuThanhPham(thu_tu=i, cong_doan_id=cd.id, ten=cd.ten, don_gia=50))
    p.thanh_phans.append(tp)
    db.add(p)
    db.commit()
    return p


def _may_khac(db, ma: str) -> MayThietBi:
    may = MayThietBi(ma=ma, ten=f"Máy {ma}", loai_may="press_offset_sheet",
                     toc_do=5_000, don_vi_toc_do="to_gio", kho_max_dai=1020, kho_max_rong=720)
    db.add(may)
    db.flush()
    return may


def test_may_in_dien_san_o_buoc_in_phai_la_may_cong_doan_chay_duoc(
    db, orders, lsx_svc, admin, customer
):
    """Máy của phiếu tính giá KHÔNG nằm trong "Máy chạy được công đoạn này" ⇒ không chép mù.

    Ô "Máy in" của phiếu mời HỢP máy của MỌI công đoạn nhóm In, nên sale hoàn toàn có thể chọn máy
    thuộc công đoạn In khác. Chép thẳng xuống thì cặp (công đoạn × máy) không tồn tại ⇒ bước không
    có `cong_thuc_gio`, thời lượng ra "—", và lệnh vừa tạo đã kêu "máy không nằm trong danh sách".
    Công đoạn khai đúng MỘT máy thì đó là câu trả lời duy nhất — điền nó, đúng lối `_khoan_mac_dinh`.
    """
    phieu_chon = _may_in(db)                 # máy sale chọn trên phiếu
    cua_cong_doan = _may_khac(db, "MAY-IN-CD")   # máy DUY NHẤT công đoạn In khai
    ptg = _ptg_mot_buoc_in(db, may_cua_phieu=phieu_chon, may_lam_duoc=[cua_cong_doan])
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                  actor=admin)[0].id)

    assert lsx.may_id == phieu_chon.id           # cấp LỆNH vẫn giữ nguyên ý định của phiếu
    buoc = {c.ten: c for c in lsx.cong_doans}
    assert buoc["In AB"].may_id == cua_cong_doan.id
    # Lệnh vừa tạo KHÔNG được đẻ ra sẵn một cảnh báo máy.
    assert [x for x in lsx_svc._soi_danh_muc(lsx) if x.get("may_canh_bao")] == []


@pytest.mark.parametrize("so_may, dien", [(1, True), (2, False)])
def test_may_in_phieu_bo_trong_thi_chi_dien_khi_cong_doan_khai_dung_mot_may(
    db, orders, lsx_svc, admin, customer, so_may, dien
):
    """Phiếu bỏ trống ô Máy in: công đoạn khai 1 máy ⇒ điền; khai 2 máy ⇒ để trống cho KHSX chọn.

    Sale rất hay bỏ trống ô này (phiếu chỉ cần đơn giá công in), nên bước In xuống xưởng trống máy
    là ca THƯỜNG chứ không phải ngoại lệ. Một máy thì không có gì để đoán — điền. Hai máy trở lên
    là quyết định của người xếp lịch, máy không chọn hộ.
    """
    mays = [_may_in(db)] + [_may_khac(db, f"MAY-IN-{i}") for i in range(1, so_may)]
    ptg = _ptg_mot_buoc_in(db, may_cua_phieu=None, may_lam_duoc=mays)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                  actor=admin)[0].id)

    assert lsx.may_id is None
    buoc_in = {c.ten: c for c in lsx.cong_doans}["In AB"]
    assert buoc_in.may_id == (mays[0].id if dien else None)


def test_may_in_cong_doan_chua_khai_may_nao_thi_tin_phieu(
    db, orders, lsx_svc, admin, customer
):
    """Công đoạn In chưa khai bảng máy ⇒ không có gì đối chiếu, máy của phiếu xuống thẳng bước In."""
    phieu_chon = _may_in(db)
    ptg = _ptg_mot_buoc_in(db, may_cua_phieu=phieu_chon, may_lam_duoc=[])
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                  actor=admin)[0].id)
    assert {c.ten: c for c in lsx.cong_doans}["In AB"].may_id == phieu_chon.id


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
    row = next(r for r in lsx_svc.list_rows(order_id=d.id)[0] if r["id"] == hop.id)
    # Hai màn phải nói CÙNG một đơn vị cho cùng một lệnh — lệch là người dùng mất niềm tin vào số.
    assert row["don_vi_to"] == ln["don_vi_to"]


def test_buoc_lenh_THOI_mang_dau_viec_kip_va_nang_suat(db, orders, lsx_svc, admin, customer):
    """⭐ 18/09/2026: bước lệnh thôi chọn đầu việc khoán, thôi kíp chuẩn, thôi năng suất tổ.

    Việc khoán chọn LÚC GHI MẺ ở bàn tổ — nơi thợ biết mình vừa làm việc gì. Bước tổ chỉ còn SỐ
    GIỜ KẾ HOẠCH, bước mới sinh ra bằng 0. Khoá phải VẮNG HẲN (không phải mang `None`): khoá còn là
    FE còn chỗ vẽ lại ô cũ.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]

    chi_tiet = lsx_svc.detail_dict(lsx)
    for b in chi_tiet["cong_doans"]:
        for khoa in ("khoan_rate_id", "khoan_ten", "khoan_chon_duoc", "so_nhan_cong_tieu_chuan",
                     "so_nhan_cong", "nang_suat", "don_vi_nang_suat", "khoan_json"):
            assert khoa not in b, (b["ten"], khoa)
        assert b["so_gio_ke_hoach"] == 0
        for khoa in ("so_nhan_cong_tinh", "so_nhan_cong_tieu_chuan"):
            assert khoa not in b["thoi_luong_dien_giai"], khoa
    assert "khoan_tien_tong" not in chi_tiet
    for ten in ("dau_viec_options", "_dau_viec_option_dicts", "_khoan_mac_dinh",
                "_khoan_derived", "don_gia_hieu_dung"):
        assert not hasattr(lsx_svc, ten), ten


def test_bung_vat_tu_theo_cong_doan_va_khong_de_len_dong_nguoi_sua(
    db, orders, lsx_svc, admin, customer
):
    """BOM (mg 0316): công đoạn khai sẵn vật tư → bước lệnh có sẵn số lượng, và dòng người sửa thì
    máy chừa ra.

    Số lượng CHỈ tới từ công thức của DÒNG vật tư của công đoạn. Cồn ở đây đo bằng `kg` và bảng
    cặp CÓ cạnh `cai → kg` — nhưng chưa khai công thức thì máy vẫn KHÔNG bung, chỉ nói thiếu gì.
    """
    from app.models.don_vi_do import DonViDo, DonViQuyDoi
    from app.models.vat_lieu_kho import VatTuInAn
    from app.services.bien_cong_thuc import quy_cach_bien

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    keo = VatTuInAn(ma="KEO-T", ten="Keo dán hộp", don_vi_gia="kg", don_gia=95_000)
    coi = VatTuInAn(ma="COI-T", ten="Cồn chưa khai công thức", don_vi_gia="kg", don_gia=1)
    db.add_all([keo, coi])
    db.flush()
    # 1 hộp ăn 0,004 kg keo — khai ở DÒNG vật tư của công đoạn.
    cd_dan.vat_tus.append(CongDoanVatTu(vat_tu_id=keo.id, thu_tu=0,
                                        cong_thuc_luong="sl_vao * 0.004"))
    cd_dan.vat_tus.append(CongDoanVatTu(vat_tu_id=coi.id, thu_tu=1))
    # Cạnh `cai → kg` CÓ TỒN TẠI — để chứng minh nó KHÔNG còn đẻ số cho vật tư nữa.
    cai = db.query(DonViDo).filter(DonViDo.ma == "cai").one()
    kg = db.query(DonViDo).filter(DonViDo.ma == "kg").one_or_none() \
        or DonViDo(ma="kg", ten="kg")
    db.add(kg)
    db.flush()
    db.add(DonViQuyDoi(tu_id=cai.id, den_id=kg.id, he_so=0.004))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")

    # Keo ra số THẬT = SL vào bước × 0,004; cồn chưa khai công thức ⇒ KHÔNG bung, chỉ cảnh báo.
    rows, canh_bao = lsx_svc._vat_tu_bung(cd_dan, buoc, quy_cach_bien(lsx))
    assert [v["ma"] for v in rows] == ["KEO-T"]
    assert rows[0]["so_luong"] == pytest.approx(round(float(buoc.so_luong_vao) * 0.004, 3))
    assert rows[0]["don_vi"] == "kg"
    canh_bao_coi = next(c for c in canh_bao if "Cồn chưa khai công thức" in c)
    assert "công thức định mức" in canh_bao_coi, \
        "chưa khai thì phải NÓI THIẾU GÌ và chỉ chỗ khai, không im lặng biến mất"
    assert [v.vat_tu_ma_snapshot for v in buoc.vat_tus] == ["KEO-T"], "tạo lệnh là tự bung"

    # Lưu hai dòng: một của máy, một người tự thêm. Cờ phải đi đúng theo từng dòng.
    rows_in = [
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
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows_in, actor=admin, ly_do=None)
    b = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")
    co = {v["vat_tu_ma"]: v for v in b["vat_tus"]}
    assert co["KEO-T"]["tu_dong"] is True, "dòng máy bung ⇒ lần sau thay được"
    assert co["COI-T"]["tu_dong"] is False, "dòng người tự thêm ⇒ máy phải chừa ra"
    assert co["COI-T"]["so_luong"] == 7


def test_doi_cong_doan_cua_buoc_thi_luu_xong_bung_lai_vat_tu_theo_cong_doan_moi(
    db, orders, lsx_svc, admin, customer
):
    """Vật tư đi theo CÔNG ĐOẠN (spec 2026-09-18 §5.2): đổi công đoạn của bước rồi Lưu ⇒ dòng máy
    bung của công đoạn CŨ đi, vật tư của công đoạn MỚI bung vào theo số vào của bước. Dòng người tự
    thêm vẫn nằm yên; bước không đổi công đoạn thì không bị bung lại.
    """
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    keo = VatTuInAn(ma="KEO-T", ten="Keo dán hộp", don_vi_gia="kg", don_gia=95_000)
    keo_nong = VatTuInAn(ma="KEO-NONG", ten="Keo nhiệt", don_vi_gia="kg", don_gia=120_000)
    bang = VatTuInAn(ma="BANG-KEO", ten="Băng keo 2 mặt", don_vi_gia="cuon", don_gia=15_000)
    db.add_all([keo, keo_nong, bang])
    db.flush()
    cd_dan.vat_tus.append(CongDoanVatTu(vat_tu_id=keo.id, thu_tu=0,
                                        cong_thuc_luong="sl_vao * 0.004"))
    cd_may = CongDoan(ma="CD-DAN-MAY", ten="Dán hộp máy", nhom="finishing",
                      cong_thuc_gia="so_luong * don_gia", department_ids=list(cd_dan.department_ids),
                      don_vi_vao="cai", don_vi_ra="cai")
    cd_may.vat_tus.append(CongDoanVatTu(vat_tu_id=keo_nong.id, thu_tu=0,
                                        cong_thuc_luong="sl_vao * 0.01"))
    db.add(cd_may)
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    assert [v.vat_tu_ma_snapshot for v in buoc.vat_tus] == ["KEO-T"]
    khac_truoc = {c.step_key: sorted(v.vat_tu_ma_snapshot for v in c.vat_tus)
                  for c in lsx.cong_doans if c.step_key != buoc.step_key}

    # Đúng payload drawer gửi sau khi đổi công đoạn: dòng máy bung của công đoạn cũ đã bỏ, chỉ còn
    # dòng người tự thêm.
    rows_in = [
        LsxCongDoanIn(
            step_key=cd.step_key, thu_tu=cd.thu_tu,
            cong_doan_id=cd_may.id if cd.step_key == buoc.step_key else cd.cong_doan_id,
            ten="Dán hộp máy" if cd.step_key == buoc.step_key else cd.ten,
            nhom=cd.nhom, department_id=cd.department_id, loai_buoc=cd.loai_buoc,
            vat_tus=([{"vat_tu_id": bang.id, "so_luong": 3, "tu_dong": False}]
                     if cd.step_key == buoc.step_key else None),
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows_in, actor=admin, ly_do=None)
    b = next(c for c in lsx.cong_doans if c.step_key == buoc.step_key)
    co = {v.vat_tu_ma_snapshot: v for v in b.vat_tus}
    assert set(co) == {"KEO-NONG", "BANG-KEO"}, "keo của công đoạn cũ phải đi, keo nhiệt phải vào"
    assert co["KEO-NONG"].tu_dong is True
    assert float(co["KEO-NONG"].so_luong) == pytest.approx(round(float(b.so_luong_vao) * 0.01, 3))
    assert co["BANG-KEO"].tu_dong is False and float(co["BANG-KEO"].so_luong) == 3
    assert {c.step_key: sorted(v.vat_tu_ma_snapshot for v in c.vat_tus)
            for c in lsx.cong_doans if c.step_key != buoc.step_key} == khac_truoc

    # Lưu lại lần nữa KHÔNG đổi gì ⇒ không bung lại (dòng máy giữ nguyên, người sửa số thì giữ số).
    rows_in2 = [
        LsxCongDoanIn(
            step_key=cd.step_key, thu_tu=cd.thu_tu, cong_doan_id=cd.cong_doan_id, ten=cd.ten,
            nhom=cd.nhom, department_id=cd.department_id, loai_buoc=cd.loai_buoc,
            vat_tus=([{"vat_tu_id": keo_nong.id, "so_luong": 99, "tu_dong": False},
                      {"vat_tu_id": bang.id, "so_luong": 3, "tu_dong": False}]
                     if cd.step_key == buoc.step_key else None),
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows_in2, actor=admin, ly_do=None)
    b = next(c for c in lsx.cong_doans if c.step_key == buoc.step_key)
    assert {v.vat_tu_ma_snapshot: float(v.so_luong) for v in b.vat_tus} == {
        "KEO-NONG": 99, "BANG-KEO": 3}


def test_so_luong_vat_tu_lay_tu_CONG_THUC_cua_dong_vat_tu(db, orders, lsx_svc, admin, customer):
    """Đường CHÍNH của BOM: DÒNG vật tư của công đoạn khai `cong_thuc_luong` (mg 0316).

    Không đi qua bảng cặp, không cần đơn vị của bước khớp gì cả — công thức tự lấy chip từ quy cách
    lệnh.
    """
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn
    from app.services.bien_cong_thuc import quy_cach_bien

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    db.add(DonViDo(ma="m2_tp", ten="m² thành phẩm"))
    mang = VatTuInAn(ma="MANG-TP", ten="Màng phủ thành phẩm", don_vi_gia="m2_tp", don_gia=9_000)
    db.add(mang)
    db.flush()
    # Công thức khai trên DÒNG vật tư: dài × rộng thành phẩm × số lượng đặt.
    cd_dan.vat_tus.append(CongDoanVatTu(
        vat_tu_id=mang.id, thu_tu=0, cong_thuc_luong="dai_tp * rong_tp * so_luong"))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    rows, _ = lsx_svc._vat_tu_bung(cd_dan, buoc, quy_cach_bien(lsx))

    qc = lsx.quy_cach_json or {}
    cho = (float(qc["dai_thanh_pham"]) / 1000) * (float(qc["rong_thanh_pham"]) / 1000) \
        * float(lsx.so_luong_dat)
    assert [v["ma"] for v in rows] == ["MANG-TP"]
    assert rows[0]["so_luong"] == pytest.approx(round(cho, 3))
    assert rows[0]["don_vi"] == "m2_tp"
    # Diễn giải phải đọc được bằng chữ, không phải mã biến trần.
    assert "Dài sản phẩm" in (rows[0]["dien_giai"] or "")

    # Công thức ra 0 vì thiếu chip (lệnh này không có màu pha) ⇒ KHÔNG bung, nói thiếu biến nào.
    cd_dan.vat_tus[0].cong_thuc_luong = "so_mau_pha * dai_tp"
    db.commit()
    rows, canh_bao = lsx_svc._vat_tu_bung(cd_dan, buoc, quy_cach_bien(lsx))
    assert rows == []
    assert any("so_mau_pha" in c for c in canh_bao)


def test_vat_tu_khai_o_cong_doan_TU_BUNG_vao_buoc_luc_tao_lenh(
    db, orders, lsx_svc, admin, customer,
):
    """Khai vật tư ở CÔNG ĐOẠN (danh mục) ⇒ tạo lệnh xong bước phải CÓ SẴN dòng đó, kèm số lượng.

    Từ 18/09/2026 (mg 0316) không còn phải đợi bước chọn đầu việc: MỌI bước gắn công đoạn đều bung.
    """
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    db.add(DonViDo(ma="kg_keo", ten="kg keo"))
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg_keo", don_gia=45_000)
    db.add(keo)
    db.flush()
    # Định mức khai trên DÒNG vật tư của công đoạn: 2 g cho mỗi thành phẩm của lệnh.
    cd_dan.vat_tus.append(CongDoanVatTu(
        vat_tu_id=keo.id, thu_tu=0, cong_thuc_luong="0.002 * so_luong"))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)

    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    ma = [v.vat_tu_ma_snapshot for v in buoc.vat_tus]
    assert ma == ["KEO-GAY"], f"vật tư của công đoạn phải tự bung, đang có: {ma}"
    v = buoc.vat_tus[0]
    assert float(v.so_luong) == pytest.approx(0.002 * float(lsx.so_luong_dat), rel=1e-6)
    assert v.tu_dong is True, "dòng máy bung ⇒ lần đổi đầu việc sau phải thay được"


def test_dinh_muc_vat_tu_lay_tu_dong_cua_cong_doan(db, orders, lsx_svc, admin, customer):
    """Keo đo bằng `kg` THẬT + định mức khai ở DÒNG vật tư ⇒ BOM ra số kg, khỏi đẻ đơn vị `kg_keo`.

    Công thức ra LƯỢNG không thuộc về ĐƠN VỊ (chốt 13/08/2026) và từ 06/09/2026 cũng không thuộc về
    MÓN HÀNG nữa, mà thuộc về DÒNG vật tư của công đoạn (mg 0316). `kg` dùng chung cho keo ·
    mực · giấy mà mỗi thứ tiêu hao một kiểu; và cùng một món keo dùng ở hai công đoạn cũng ăn khác
    nhau. Kho và mua hàng vẫn thấy `kg` thật, không phải `kg_keo`.
    """
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    # `kg` mang công thức của GIẤY — cố tình, để chứng minh vật tư THẮNG đơn vị.
    dv_kg = db.query(DonViDo).filter(DonViDo.ma == "kg").one_or_none()
    if dv_kg is None:
        dv_kg = DonViDo(ma="kg", ten="kg", ho="khoi_luong")
        db.add(dv_kg)
    dv_kg.cong_thuc = "dinh_luong * dai_in * rong_in * to_dau_vao"
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45_000)
    db.add(keo)
    db.flush()
    cd_dan.vat_tus.append(CongDoanVatTu(
        vat_tu_id=keo.id, thu_tu=0, cong_thuc_luong="0.002 * so_luong"))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    v = next(x for x in buoc.vat_tus if x.vat_tu_ma_snapshot == "KEO-GAY")

    # Số theo công thức CỦA DÒNG KEO, KHÔNG phải công thức khối lượng giấy gắn trên `kg`.
    assert float(v.so_luong) == pytest.approx(0.002 * float(lsx.so_luong_dat), rel=1e-6)
    assert v.don_vi_snapshot == "kg", "kho vẫn cân bằng kg thật, không phải kg_keo"


def test_goi_y_luong_cho_MOI_vat_tu_de_drawer_dien_san(db, orders, lsx_svc, admin, customer):
    """Chọn một vật tư BẤT KỲ ở drawer thì số phải hiện ngay — server tính sẵn cho cả danh mục.

    Chủ 13/08/2026: "khi chọn keo vào gáy thì nó tính luôn". Công thức + quy cách đều nằm ở server;
    client không có và không nên có (công thức chỉ được một bản). Nên server gửi kèm `vat_tu_goi_y`.

    Món chưa tính ra được VẪN có mặt, `so_luong=None` kèm `ly_do` chỉ chỗ khai (18/08/2026): ô vẫn
    để trống cho người khai (không đoán số), nhưng drawer nói được VÌ SAO nó trống thay vì để người
    dùng đoán là màn hỏng.

    Công thức mượn của DÒNG vật tư của công đoạn (mg 0316) — món công đoạn không khai thì không
    có gì để mượn, đúng nghĩa "chưa khai".
    """
    from app.models.don_vi_do import DonViDo
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45_000)
    # Món CHƯA khai gì để tính lượng ⇒ phải VẮNG khỏi gợi ý, không được bịa số.
    mu = VatTuInAn(ma="MU-LA", ten="Món lạ", don_vi_gia="thung_la", don_gia=1_000)
    db.add_all([keo, mu, DonViDo(ma="thung_la", ten="thùng lạ")])
    db.flush()
    cd_dan.vat_tus.append(CongDoanVatTu(
        vat_tu_id=keo.id, thu_tu=0, cong_thuc_luong="0.002 * so_luong"))
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == "Dán hộp")

    # Khoá theo CẶP: gợi ý nay gồm cả danh mục Giấy, mà Giấy #7 với Vật tư #7 là hai món khác
    # nhau — khoá bằng id trần thì một loại giấy trùng id sẽ đè mất dòng vật tư đang kiểm.
    goi_y = {(g["hang_loai"], g["vat_tu_id"]): g for g in buoc["vat_tu_goi_y"]}
    k_keo, k_mu = ("vat_tu", keo.id), ("vat_tu", mu.id)
    assert k_keo in goi_y, "vật tư đã khai định mức ở công đoạn phải được tính sẵn"
    assert goi_y[k_keo]["so_luong"] == pytest.approx(
        round(0.002 * float(lsx.so_luong_dat), 3), rel=1e-6)
    dien_giai = goi_y[k_keo]["dien_giai"] or ""
    assert "Số lượng đặt" in dien_giai and dien_giai.endswith("kg"), \
        f"phải hiện công thức ĐÃ THAY SỐ để kiểm bằng mắt, đang là: {dien_giai!r}"
    assert goi_y[k_keo]["ly_do"] is None

    # Món chưa khai: có mặt, KHÔNG có số, và câu lý do chỉ đúng chỗ khai.
    assert goi_y[k_mu]["so_luong"] is None, "chưa tính ra được thì để trống, không bịa số 0"
    assert "công thức định mức" in goi_y[k_mu]["ly_do"]
    assert "Công đoạn" in goi_y[k_mu]["ly_do"], "lý do phải chỉ được chỗ khai"


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


# `test_buoc_NGOAI_dong_giay_lay_so_tu_cong_thuc_SAN_LUONG_va_co_hao` GỠ 18/09/2026 cùng
# `cong_doan.cong_thuc_san_luong` (mg `0324`): bước ngoài dòng giấy nay lấy số do người lập
# lệnh tự khai ở bước — xem `test_san_xuat_buoc_ngoai_dong.py` · `test_lsx_buoc_khai_tay.py`.


def test_xem_truoc_routing_doi_cong_doan_thi_so_va_don_vi_nhay_ngay(
    db, orders, lsx_svc, admin, customer,
):
    """Đổi công đoạn ở drawer ⇒ `POST /xem-truoc-routing` trả số VÀO–RA + đơn vị MỚI ngay, chưa Lưu.

    Đúng thứ chủ chửi 20/08: đổi bước "Dán hộp" (cai→cai, trên dòng giấy) sang Ghi kẽm CTP
    (kem→kem, ngoài dòng) mà số + đơn vị đứng im. Xem trước chạy ĐÚNG `replace_routing` rồi
    rollback nên không thể lệch số Lưu; test giữ cửa đó (FE nuốt lỗi endpoint này).
    """
    from app.models.don_vi_do import DonViDo
    from app.schemas.lsx import XemTruocRoutingRow

    ptg = _ptg_2_san_pham(db)
    if db.query(DonViDo).filter(DonViDo.ma == "kem").one_or_none() is None:
        db.add(DonViDo(ma="kem", ten="bản kẽm", ho="kem"))
    # Công đoạn ĐÍCH để đổi sang: ngoài dòng giấy (hai ô đơn vị để trống, mg `0273`).
    ctp = CongDoan(ma="CD-CTP-T", ten="Ghi kẽm CTP", nhom="prepress",
                   cong_thuc_gia="so_luong * don_gia", department_ids=[_to_san_xuat(db).id],
                   kieu_bu_hao="co_dinh", so_to_bu_hao=1)
    db.add(ctp)
    db.commit()

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                  actor=admin)[0].id)
    dan = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    assert dan.don_vi_ra == "cai", "trước khi đổi, bước dán đo bằng cái (trên dòng giấy)"
    dan_key = dan.step_key

    def _payload(doi_dan_sang_ctp: bool):
        rows = []
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu):
            la_dan = cd.step_key == dan_key
            rows.append(XemTruocRoutingRow(
                step_key=cd.step_key, thu_tu=cd.thu_tu,
                cong_doan_id=ctp.id if (la_dan and doi_dan_sang_ctp) else cd.cong_doan_id,
                ten="Ghi kẽm CTP" if (la_dan and doi_dan_sang_ctp) else cd.ten,
                nhom="prepress" if (la_dan and doi_dan_sang_ctp) else cd.nhom,
                loai_buoc=cd.loai_buoc, department_id=cd.department_id, may_id=cd.may_id,
            ))
        return rows

    # ① Không đổi gì ⇒ số xem trước = số đã lưu (chứng minh một engine, không bản tính thứ hai).
    base = {r["step_key"]: r for r in lsx_svc.xem_truoc_routing(
        lsx_id=lsx.id, rows_in=_payload(False), actor=admin)}
    assert base[dan_key]["don_vi_ra"] == "cai"
    assert base[dan_key]["so_luong_vao"] == float(dan.so_luong_vao)

    # ② Đổi bước Dán sang Ghi kẽm CTP ⇒ đơn vị nhảy ngay theo danh mục (trống), ra khỏi dòng giấy.
    sau = {r["step_key"]: r for r in lsx_svc.xem_truoc_routing(
        lsx_id=lsx.id, rows_in=_payload(True), actor=admin)}
    doi = sau[dan_key]
    assert (doi["don_vi_vao"], doi["don_vi_ra"]) == (None, None), "đơn vị phải nhảy ngay"
    assert doi["tren_dong_giay"] is False, "kẽm là bước ngoài dòng giấy"
    # Công thức sản lượng ra GỠ 18/09/2026 (mg `0324`): số của bước ngoài dòng do người lập lệnh
    # khai ở drawer, xem trước không còn câu diễn giải hay lỗi quy đổi nào để trả.
    assert "san_luong_dien_giai" not in doi and "loi_quy_doi" not in doi

    # ③ DB KHÔNG được đụng — xem trước là read-only.
    db.refresh(lsx)
    dan_db = next(c for c in lsx.cong_doans if c.step_key == dan_key)
    assert dan_db.don_vi_ra == "cai" and dan_db.cong_doan_id != ctp.id


def test_xem_truoc_routing_chen_buoc_moi_thi_doi_lai_dung_step_key(
    db, orders, lsx_svc, admin, customer,
):
    """Chèn công đoạn giữa chuỗi (khoá client `r{n}`) ⇒ xem trước phải dội lại đúng dòng đó.

    FE khớp kết quả theo `step_key`; bước mới chưa có id nên gửi khoá tạm `r{n}` — server phải
    echo nguyên khoá đó thì số của dòng vừa chèn mới về đúng chỗ trên drawer.
    """
    from app.schemas.lsx import XemTruocRoutingRow

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                  actor=admin)[0].id)
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-BE-T").one()

    rows = [
        XemTruocRoutingRow(step_key=cd.step_key, thu_tu=cd.thu_tu, cong_doan_id=cd.cong_doan_id,
                           ten=cd.ten, nhom=cd.nhom, loai_buoc=cd.loai_buoc,
                           department_id=cd.department_id, may_id=cd.may_id)
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    # Chèn một bước Bế mới ngay sau bước đầu, mang khoá tạm "r99".
    rows.insert(1, XemTruocRoutingRow(
        step_key="r99", thu_tu=1, cong_doan_id=cd_be.id,
        ten=cd_be.ten, nhom=cd_be.nhom, loai_buoc="may", department_id=cd_be.to_mac_dinh_id))
    for i, r in enumerate(rows):
        r.thu_tu = i

    out = lsx_svc.xem_truoc_routing(lsx_id=lsx.id, rows_in=rows, actor=admin)
    keys = [r["step_key"] for r in out]
    assert "r99" in keys, "bước mới chèn phải được dội lại đúng khoá client gửi lên"
    # DB không đổi.
    db.refresh(lsx)
    assert not any(c.step_key == "r99" for c in lsx.cong_doans)


def test_bo_buoc_giua_chuoi_khong_bao_oan_chinh_lenh_minh(db, orders, lsx_svc, admin, customer):
    """Bỏ một bước GIỮA chuỗi ⇒ không được báo "bước đang được <chính lệnh này> phụ thuộc".

    Lệnh sinh ra đã nối cạnh tuyến tính bước-trước → bước-sau. Chốt `removed_ids` cũ đọc cạnh ĐÃ
    LƯU mà không nhìn chủ sở hữu, nên bước kế tiếp (cùng lệnh) luôn bị tính là "phụ thuộc bên
    ngoài": xem trước báo băng đỏ, còn Lưu thì chặn cứng. Cạnh trong CHÍNH lệnh này do lần lưu
    này vẽ lại nên phải gỡ, không phải chặn.
    """
    from app.schemas.lsx import XemTruocRoutingRow

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop, _tem = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    buoc = sorted(hop.cong_doans, key=lambda c: c.thu_tu)
    assert len(buoc) >= 3, "cần ≥3 bước mới có bước GIỮA để bỏ"
    bo = buoc[1]
    con_lai = [c for c in buoc if c.step_key != bo.step_key]

    # ① XEM TRƯỚC (payload cố ý KHÔNG mang `phu_thuoc_step_keys`) — phải ra số, không ném xung đột.
    out = lsx_svc.xem_truoc_routing(lsx_id=hop.id, actor=admin, rows_in=[
        XemTruocRoutingRow(step_key=c.step_key, thu_tu=i, cong_doan_id=c.cong_doan_id,
                           ten=c.ten, nhom=c.nhom, loai_buoc=c.loai_buoc,
                           department_id=c.department_id, may_id=c.may_id)
        for i, c in enumerate(con_lai)
    ])
    assert [r["step_key"] for r in out] == [c.step_key for c in con_lai]
    db.refresh(hop)
    assert bo.step_key in {c.step_key for c in hop.cong_doans}, "xem trước không được ghi DB"

    # ② LƯU thật — bước bị bỏ biến mất, cạnh chết trỏ vào nó cũng đi theo (FK RESTRICT không nổ).
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(step_key=c.step_key, thu_tu=i, cong_doan_id=c.cong_doan_id,
                      ten=c.ten, nhom=c.nhom, loai_buoc=c.loai_buoc,
                      department_id=c.department_id, may_id=c.may_id)
        for i, c in enumerate(con_lai)
    ])
    sau = lsx_svc.get(hop.id)
    assert [c.step_key for c in sorted(sau.cong_doans, key=lambda x: x.thu_tu)] == \
        [c.step_key for c in con_lai]
    con_id = {c.id for c in sau.cong_doans}
    for c in sau.cong_doans:
        assert all(e.buoc_truoc_id in con_id for e in c.phu_thuoc), "còn cạnh trỏ vào bước đã xoá"


def test_bo_buoc_van_bi_chan_khi_LENH_KHAC_dang_phu_thuoc(db, orders, lsx_svc, admin, customer):
    """Bước của lệnh KHÁC trỏ vào bước sắp xoá ⇒ vẫn chặn: lệnh này không viết lại cạnh của lệnh kia."""
    from app.models.lsx import LsxCongDoanPhuThuoc

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop, tem = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    buoc = sorted(hop.cong_doans, key=lambda c: c.thu_tu)
    bo = buoc[1]
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=bo.id, buoc_sau_id=tem.cong_doans[0].id))
    db.commit()

    with pytest.raises(LsxConflict) as ex:
        lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
            LsxCongDoanIn(step_key=c.step_key, thu_tu=i, cong_doan_id=c.cong_doan_id,
                          ten=c.ten, nhom=c.nhom, loai_buoc=c.loai_buoc,
                          department_id=c.department_id, may_id=c.may_id)
            for i, c in enumerate(c for c in buoc if c.step_key != bo.step_key)
        ])
    assert tem.ma in str(ex.value)


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
    from app.models.vat_lieu_kho import VatTuInAn

    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    # Cho bước có HAO để `so_luong_vao` khác hẳn SL đặt — không thì test không chứng minh được
    # chip lấy số của BƯỚC chứ không phải của lệnh.
    cd_dan.kieu_bu_hao, cd_dan.so_to_bu_hao = "co_dinh", 300
    keo = VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45_000)
    db.add(keo)
    db.flush()
    cd_dan.vat_tus.append(CongDoanVatTu(
        vat_tu_id=keo.id, thu_tu=0, cong_thuc_luong="sl_vao * 0.002"))
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


# 🔴 Hai test của cơ chế MƯỢN CÔNG THỨC TRONG CỤM gỡ 17/08/2026 cùng cột `don_vi_do.cong_thuc`
# (mg `0215`): `test_cong_thuc_luong_khai_o_kg_thi_TAN_dung_chung` và
# `test_khoan_muon_cong_thuc_trong_cum_thi_dien_giai_phoi_buoc_doi`. Mượn-trong-cụm chỉ có nghĩa khi
# công thức treo ở ĐƠN VỊ; nay nó treo ở món hàng / máy / đầu việc / bước, mỗi cái tự khai của mình.


# ================= Công thức lượng RIÊNG của máy / của đầu việc khoán (mg 0213) =================
# Bậc ⓿ của `_sl_theo_don_vi`: công thức của CHÍNH đối tượng thắng cầu quy đổi và thắng công thức
# của đơn vị. Cùng luật "RIÊNG → CHUNG" mà `_luong_vat_tu` đã đi cho vật tư/giấy.


def test_don_gia_khoan_khong_lot_vao_cong_thuc_gio_cua_may(db):
    """Bước MÁY không đứng ở đầu việc nào ⇒ chip bằng 0, KHÔNG nổ NameError.

    Bộ chip `quy_doi` dùng chung cho cả ô "Cách đo giờ chạy" của cặp công đoạn × máy. Chip bị ẩn ở
    đó (`FormulaField.AN_MOI_O`) nhưng validator vẫn nhận, nên gõ tay được — và gõ tay thì phải ra
    0 chứ không được làm vỡ cả bước.
    """
    from types import SimpleNamespace

    from app.services.lsx_service import LsxService

    svc = LsxService.__new__(LsxService)
    svc._don_vis = lambda: {"to": {"ma": "to", "ten": "tờ"}}
    svc._cap_quy_doi = lambda: []
    buoc = SimpleNamespace(so_luong_vao=1000, so_luong_ra=1000, don_vi_vao="to",
                           so_luot_chay=1, khoan_json=None)

    # `sl_vao + don_gia_khoan` ⇒ 1000 + 0. Chạy được là đủ: điều đang khoá là KHÔNG NameError.
    got = svc._sl_theo_don_vi(buoc, "to", {}, ct_rieng="sl_vao + don_gia_khoan")
    assert got is not None and got[0] == pytest.approx(1000.0)


def test_buoc_TO_thoi_gian_la_SO_GIO_KE_HOACH(db, orders, lsx_svc, admin, customer):
    """⭐ §5.1 (18/09/2026): giờ của bước tổ là SỐ GIỜ KẾ HOẠCH người lập lệnh gõ — nhận số lẻ.

    Không chia năng suất, không nhân kíp. Để 0 là HỢP LỆ và KHÔNG cảnh báo — chủ xưởng: *"không
    cần cảnh báo, bản chất nó là số giờ kế hoạch, nếu thiếu thì cứ để 0"*.
    """
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    lsx = _chon_loai_buoc(lsx_svc, lsx, admin, {"Dán hộp": "to"})

    def _doc() -> dict:
        return next(x for x in lsx_svc.detail_dict(lsx_svc.get(lsx.id))["cong_doans"]
                    if x["cong_doan_id"] == cd_dan.id)

    khong = _doc()
    assert khong["so_gio_ke_hoach"] == 0
    assert khong["chay_phut"] == 0
    assert khong["thoi_luong_dien_giai"]["canh_bao"] == [], "0 giờ KHÔNG được kèm cảnh báo"

    rows = [
        LsxCongDoanIn(
            step_key=cd.step_key, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
            loai_buoc=cd.loai_buoc, department_id=cd.department_id, may_id=cd.may_id,
            **({"so_gio_ke_hoach": 4.5} if cd.cong_doan_id == cd_dan.id else {}),
        )
        for cd in sorted(lsx_svc.get(lsx.id).cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin)
    db.expire_all()
    co = _doc()
    assert co["so_gio_ke_hoach"] == 4.5, "số lẻ phải giữ nguyên, không bắt tròn"
    assert co["chay_phut"] == pytest.approx(270)
    assert co["chiem_may_phut"] == co["chiem_may_phut_min"] == co["chiem_may_phut_max"]
    assert co["thoi_luong_dien_giai"]["nguon_nang_suat"] == "gio_ke_hoach"


def test_cong_thuc_luong_cua_MAY_ra_luong_theo_don_vi_toc_do(db, orders, lsx_svc, admin, customer):
    """⭐ Máy đo `m²/giờ` mà bước đếm `tờ` ⇒ công thức của cặp CÔNG ĐOẠN × MÁY ra số m², rồi mới
    chia tốc độ.

    Từ 06/09/2026 công thức nằm ở `cong_doan_may.cong_thuc_gio` chứ không ở `may.cong_thuc_luong`:
    cùng một máy chạy hai công đoạn thì đo khác nhau. Đọc SỐNG (khác đầu việc khoán bị ghim): đổi
    máy là đổi cả tốc độ lẫn cách đếm lượt, nên giờ chạy phải tính theo máy ĐANG gán.
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
    db.commit()
    # 1 tờ in = dai_in × rong_in (m²) ⇒ lượng theo m² của CHÍNH cặp công đoạn × máy này.
    _khai_ct_gio(db, lsx_svc, db.get(LsxCongDoan, buoc["id"]).cong_doan_id, may.id,
                 "sl_vao * dai_in * rong_in")
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
    _khai_ct_gio(db, lsx_svc, db.get(LsxCongDoan, buoc["id"]).cong_doan_id, may.id,
                 "sl_vao * bien_khong_ton_tai")
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


def test_may_nhan_so_luot_chay():
    may = _may_gia(toc_do=5000)
    assert _tlb(_buoc(loai_buoc="may", so_luong_vao=5000), may)["chay_phut"] == 60
    # In trở 2 lượt → chạy gấp đôi.
    t = _tlb(_buoc(loai_buoc="may", so_luong_vao=5000, so_luot_chay=2), may)
    assert t["chay_phut"] == 120
    assert t["dien_giai"]["phuong_phap"] == "may"
    assert "so_nhan_cong_tinh" not in t["dien_giai"], "kíp người đã gỡ hẳn (mg 0321)"


def test_to_doc_SO_GIO_KE_HOACH_khong_chia_gi():
    """Bước TỔ: thời lượng = thời gian khác + số giờ kế hoạch × 60. Ba mức bằng nhau (một con số
    gõ tay không có dải nhanh–chậm), SL vào không tham gia, và KHÔNG có cảnh báo khi để 0."""
    t = thoi_luong_buoc(_buoc(loai_buoc="to", so_luong_vao=5000, so_gio_ke_hoach=4.5,
                              phat_sinh_phut=10))
    assert t["chay_phut"] == 270
    assert t["chiem_may_phut"] == t["chiem_may_phut_min"] == t["chiem_may_phut_max"] == 280
    assert t["dien_giai"]["so_gio_ke_hoach"] == 4.5
    assert t["dien_giai"]["nguon_nang_suat"] == "gio_ke_hoach"
    assert t["dien_giai"]["canh_bao"] == []

    khong = thoi_luong_buoc(_buoc(loai_buoc="to", so_luong_vao=5000, so_gio_ke_hoach=0))
    assert khong["chay_phut"] == 0
    assert khong["dien_giai"]["canh_bao"] == [], "0 giờ là hợp lệ — không cảnh báo"


def test_buoc_to_go_may_va_giu_so_gio_ke_hoach(db, orders, lsx_svc, admin, customer):
    """Đổi bước sang TỔ: server gỡ máy, và số giờ kế hoạch người lập lệnh gõ được LƯU nguyên."""
    ptg = _ptg_2_san_pham(db)
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
            **({"so_gio_ke_hoach": 2.25} if cd.ten == "Dán hộp" else {}),
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin)
    dan = {cd.ten: cd for cd in lsx.cong_doans}["Dán hộp"]
    assert dan.loai_buoc == "to" and dan.may_id is None   # Tổ ⇒ không giữ máy
    assert float(dan.so_gio_ke_hoach) == 2.25
    assert _tl(dan, db)["chay_phut"] == pytest.approx(135)


def test_buoc_to_ep_mot_luot_chay(db, orders, lsx_svc, admin, customer):
    """Chủ chốt 08/09/2026: "loại bước là tổ thì ẩn cái này đi và cho mặc định là 1".

    Ô "số lượt chạy qua máy" nay CHỈ còn ở bước máy/thuê ngoài — làm tay thì không có lượt qua
    máy nào để đếm. Ép ở SERVER chứ không chỉ ẩn ô trên form (cùng lẽ với `may_id = None` của
    bước tổ): số 2 lượt còn sót lại từ hồi bước là máy sẽ nằm VÔ HÌNH trong DB, mà chip
    `so_luot_chay` của công thức tiền công đọc thẳng cột này.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    # Client cũ (hoặc bước từng là máy) gửi 2 lượt cho MỌI bước, kể cả bước tổ.
    rows = [
        LsxCongDoanIn(
            step_key=cd.step_key, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
            loai_buoc="to" if cd.ten == "Dán hộp" else cd.loai_buoc,
            department_id=cd.department_id, may_id=cd.may_id, so_luot_chay=2,
        )
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
    ]
    lsx = lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=rows, actor=admin)
    theo_ten = {cd.ten: cd for cd in lsx.cong_doans}
    assert theo_ten["Dán hộp"].so_luot_chay == 1
    # Bước KHÔNG phải tổ giữ nguyên số đã khai — ô vẫn còn ở đó.
    khac = [cd for cd in lsx.cong_doans if cd.loai_buoc != "to"]
    assert khac and all(cd.so_luot_chay == 2 for cd in khac)


def test_thieu_nang_suat_thi_khong_bia_so():
    """Chưa khai năng suất → thời gian chạy = 0, KHÔNG đoán bừa để Gantt khỏi vẽ số sai."""
    result = _tlb(_buoc(so_luong_vao=5000))    # bước máy CHƯA gán máy
    assert result["chay_phut"] == 0
    assert any("chưa khai tốc độ" in x for x in result["dien_giai"]["canh_bao"])


def test_mac_dinh_ke_thua_tu_danh_muc_cong_doan_va_may(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})

    b = {cd.ten: cd for cd in hop.cong_doans}
    # setup ← cong_doan.setup_time; năng suất ← may_thiet_bi. Vệ sinh/rửa mực đã gỡ khỏi hệ nên
    # bước sinh ra LUÔN 0 (cột `thoi_gian_rua_muc` cũng đã gỡ khỏi model 11/08/2026).
    assert float(b["In offset"].setup_phut) == 45
    # Bước MÁY không chép tốc độ lên bước (15/08/2026) — `thoi_luong_buoc` đọc SỐNG từ máy; hai
    # cột năng suất của bước gỡ hẳn 18/09/2026 (mg 0321).
    assert not hasattr(b["In offset"], "nang_suat")
    assert float(b["In offset"].ve_sinh_phut) == 0
    assert float(b["Bế"].setup_phut) == 30 and float(b["Bế"].ve_sinh_phut) == 0
    # Bước Tổ sinh ra với SỐ GIỜ KẾ HOẠCH = 0 (§5.1) — không có nguồn danh mục nào để kế thừa.
    assert float(b["Dán hộp"].so_gio_ke_hoach) == 0 and b["Dán hộp"].may_id is None
    assert _tl(b["Dán hộp"], db)["chay_phut"] == 0
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


def test_che_ban_dung_ngoai_chuoi_giu_don_vi_trong(db, orders, lsx_svc, admin, customer):
    """Chế bản đếm KẼM → đơn vị TRỐNG, đứng ngoài chuỗi giấy.

    `replace_routing` không được gán đơn vị dòng giấy cho bước prepress: gán vào là nó chen
    giữa chuỗi bù hao ngược và số tờ phải mua sai theo.
    """
    ptg = _ptg_2_san_pham(db)
    to_id = _to_san_xuat(db).id
    ctp = CongDoan(ma="CD-CTP-T", ten="Ghi kẽm CTP", nhom="prepress", department_ids=[to_id],
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
    # Chuỗi giấy (in → bế) vẫn liền mạch, chế bản chen ở đầu không cắt vào nó.
    assert [c.don_vi_vao for c in hop2.cong_doans[1:]] == ["to", "to"]


def test_chi_tiet_lenh_co_buoc_che_ban_van_qua_duoc_SCHEMA(db, orders, lsx_svc, admin, customer):
    """Chế bản có đơn vị NULL → schema phải nhận. Khai `str` cứng là mọi lần mở lệnh đều 500.

    Test service KHÔNG bắt được lỗi này vì nó không đi qua lớp Pydantic — phải validate đúng
    payload mà router trả về.
    """
    from app.schemas.lsx import LsxOut

    ptg = _ptg_2_san_pham(db)
    to_id = _to_san_xuat(db).id
    ctp = CongDoan(ma="CD-CTP-S", ten="Ghi kẽm CTP", nhom="prepress", department_ids=[to_id],
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


def test_chi_tiet_lenh_noi_ra_dang_giu_cho_vat_tu(db, orders, lsx_svc, admin, customer):
    """Cờ giữ chỗ phải RA TỚI client — thiếu nó là màn lệnh không nói trước được cái khoá.

    `_chan_dang_giu_cho` chặn sửa routing VÀ chặn cả `xem_truoc_routing` (cố ý, xem docstring của
    nó). Mà FE nuốt lỗi xem-trước im lặng, nên không có cờ này thì người kế hoạch sửa xong cả
    routing mới ăn 409 lúc bấm Lưu, còn mỗi lần đổi công đoạn thì số trên bảng đứng im không ai
    giải thích. Trả cờ ra để bảng routing khoá lại + nói rõ đường lùi ngay từ đầu.
    """
    from app.schemas.lsx import LsxOut

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    lsx = lsx_svc.get(hop.id)
    assert LsxOut.model_validate(
        {**lsx.__dict__, **lsx_svc.detail_dict(lsx)}).giu_cho_bat is False

    lsx.giu_cho_bat = True
    db.commit()
    lsx = lsx_svc.get(hop.id)
    assert LsxOut.model_validate(
        {**lsx.__dict__, **lsx_svc.detail_dict(lsx)}).giu_cho_bat is True
    # Đúng cái khoá mà cờ đang cảnh báo: bản XEM TRƯỚC cũng 409 y hệt lưu thật.
    with pytest.raises(LsxConflict):
        lsx_svc.xem_truoc_routing(lsx_id=hop.id, rows_in=[], actor=admin)


def test_giu_cho_chan_dung_ba_duong_con_ten_ghi_chu_van_luu_duoc(
    db, orders, lsx_svc, admin, customer,
):
    """Cái khoá giữ chỗ CHẶN GÌ — màn lệnh khoá theo đúng đường này, không khoá cả màn.

    `_chan_dang_giu_cho` chỉ nổ khi đụng vào thứ làm ĐỔI LƯỢNG VẬT TƯ CẦN: `so_luong_dat`,
    `quy_cach`, routing, và xoá lệnh. Tên / hạn / ghi chú / cờ gấp không đụng vật tư nên phải
    lưu được bình thường — FE dựa vào đúng ranh giới này để khoá cụm Thông số + nút Xoá mà vẫn
    để nút "Lưu thay đổi" sống. Khoá rộng hơn là màn nói dối theo chiều ngược lại.
    """
    from app.schemas.lsx import LsxQuyCachIn

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    sl_cu = hop.so_luong_dat

    lsx = lsx_svc.get(hop.id)
    lsx.giu_cho_bat = True
    db.commit()

    # `update` GÁN field rồi mới gọi `_chan_dang_giu_cho`, nên lần nổ để lại giá trị bẩn trong
    # identity map của session. Thật thì mỗi request một session và transaction hỏng bị bỏ, nên
    # phải `rollback()` sau mỗi lần chặn — không thì lần gọi sau so với số bẩn chứ không phải số DB.
    with pytest.raises(LsxConflict):
        lsx_svc.update(
            lsx_id=hop.id, actor=admin,
            payload=LsxUpdateIn(so_luong_dat=sl_cu + 100),
        )
    db.rollback()
    with pytest.raises(LsxConflict):
        lsx_svc.update(
            lsx_id=hop.id, actor=admin,
            payload=LsxUpdateIn(quy_cach=LsxQuyCachIn(quy_cach_in="tu_tro")),
        )
    db.rollback()
    # `so_con` cũng phải chặn: đổi số con/tờ là bình bài lại ⇒ `_ap_chuoi_nguoc` viết lại số tờ kế
    # hoạch ⇒ đổi lượng GIẤY cần. Nó là ô "Bình bài" ngay trong cụm thông số mà FE đã khoá.
    with pytest.raises(LsxConflict):
        lsx_svc.update(
            lsx_id=hop.id, actor=admin,
            payload=LsxUpdateIn(so_con=int(hop.so_con) + 1),
        )
    db.rollback()
    with pytest.raises(LsxConflict):
        lsx_svc.xoa(lsx_id=hop.id, actor=admin)
    db.rollback()

    # Còn ĐÂY thì phải qua — đó là lý do nút "Lưu thay đổi" ở màn lệnh vẫn để sống khi giữ chỗ.
    ra = lsx_svc.update(
        lsx_id=hop.id, actor=admin,
        payload=LsxUpdateIn(ten="Đổi tên lúc đang giữ chỗ", ghi_chu="ghi chú mới", is_rush=True),
    )
    assert ra.ten == "Đổi tên lúc đang giữ chỗ"
    assert ra.ghi_chu == "ghi chú mới"
    assert ra.is_rush is True
    # Gửi lại ĐÚNG số cũ thì không tính là đổi ⇒ không chạm khoá. `luu()` của FE gửi kèm
    # `so_luong_dat` mỗi lần lưu, nên nếu chỗ này chặn thì nút Lưu thành nút báo lỗi.
    assert lsx_svc.update(
        lsx_id=hop.id, actor=admin,
        payload=LsxUpdateIn(so_luong_dat=sl_cu, ten="Tên lần hai"),
    ).ten == "Tên lần hai"


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
    xa = CongDoan(ma="CD-XA-T", ten="Xả giấy", nhom="finishing", department_ids=[to_id],
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


# GỠ 06/09/2026: `test_kiem_thieu_he_so_doc_theo_TRAM_khong_theo_MA_don_vi`.
#
# Nó dựng đơn vị mã riêng của xưởng (`to_chay` gắn cờ trạm `to`, `sp_xong` gắn `cai`) để chứng minh
# ba phép kiểm nguồn hệ số hỏi CỜ TRẠM chứ không so mã. Cờ `don_vi_do.tram_dong_giay` đã gỡ: ô Đơn
# vị vào/ra của công đoạn nay là menu ĐÓNG đúng 5 chặng, mã của bước CHÍNH LÀ tên chặng nên tình
# huống test dựng ra không còn khai được — `cong_doan_service` chặn ngay ở màn danh mục.
#
# Phần luật còn sống (thiếu con/tờ thì chặn "Sẵn sàng lập kế hoạch") do
# `test_thieu_NGUON_he_so_moi_chan_chu_khong_phai_he_so_bang_1` phía trên giữ.


def test_thue_ngoai_doi_to_may_y_het_buoc_may(db, orders, lsx_svc, admin, customer):
    """Bước THUÊ NGOÀI không còn cổng riêng (NCC · ngày gửi/nhận).

    Nhà thầu được khai như một MÁY trong danh mục (tên kèm hậu tố "thuê ngoài – <nhà in>"), nên
    cổng phát hành đòi đúng một thứ như bước máy: đã gán tổ hoặc máy chưa.
    """
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    to_id = _to_san_xuat(db).id
    may_ngoai = MayThietBi(ma="MAY-TN-1", ten="Máy cán (thuê ngoài – Cơ sở Tân Bình)",
                           loai_may="thue_ngoai", toc_do=4000, don_vi_toc_do="to_gio")
    db.add(may_ngoai)
    db.flush()

    def dat_routing(**ngoai) -> list[str]:
        lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
            LsxCongDoanIn(ten="In offset", nhom="print", department_id=to_id,
                          so_luong_vao=5300, so_luong_ra=5300, don_vi_vao="to"),
            LsxCongDoanIn(ten="Cán màng", nhom="finishing", loai_buoc="thue_ngoai",
                          so_luong_vao=5300, so_luong_ra=5250, don_vi_vao="to", **ngoai),
        ])
        return lsx_svc.thieu_cua(lsx_svc.get(hop.id))

    # Chưa gán gì → chặn Y NHƯ bước máy trắng, và KHÔNG còn hai mã cũ.
    thieu = dat_routing()
    assert "thieu_to_may" in thieu
    assert "thieu_ncc" not in thieu and "thieu_tg_thue_ngoai" not in thieu

    # Chọn máy của nhà thầu → hết thiếu, dù không khai NCC/ngày gửi–nhận nào.
    assert "thieu_to_may" not in dat_routing(may_id=may_ngoai.id)


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
            di_chuyen_phut=45,
        ),
    ])
    cd = lsx_svc.get(hop.id).cong_doans[0]
    assert cd.nha_cung_cap == "Cơ sở Tân Bình" and float(cd.don_gia_gia_cong) == 450
    assert cd.yeu_cau_ky_thuat == "Màng mờ, không bong mép"
    assert not hasattr(cd, "dieu_kien_json")
    # `di_chuyen_phut` đã rời hợp đồng lưu routing (2026-08-04) — cột còn trong DB nhưng client
    # không gửi được nữa, nên nó KHÔNG sống sót qua vòng lưu. Khối thuê ngoài
    # (nhà cung cấp · ngày gửi/nhận · đơn giá · yêu cầu kỹ thuật) mới là thứ phải giữ.
    # `bat_buoc` cũng rời hợp đồng lưu routing (07/09/2026): mọi bước đều bắt buộc, server giữ
    # TRUE nên client có gửi `false` cũng không ghi được (mg 0275 backfill dòng cũ).
    assert cd.bat_buoc is True
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
    to_id = _to_san_xuat(db).id
    can = CongDoan(ma="CD-CAN-T", ten="Cán màng bóng", nhom="finishing",
                   cong_thuc_gia="so_luong * don_gia", department_ids=[to_id], setup_time=20,
                   don_vi_vao="to", don_vi_ra="to")
    db.add(can)
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    hop = _chon_loai_buoc(lsx_svc, hop, admin, {"Dán hộp": "to"})
    dan = next(cd for cd in hop.cong_doans if cd.ten == "Dán hộp")
    assert dan.loai_buoc == "to" and dan.don_vi_vao == "cai"

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
        # Chặng CUỐI của router: dict service phải qua được `BuocMacDinhOut`. Không có dòng này thì
        # cả ba test của endpoint đều dừng ở tầng service, còn schema trôi tự do — đúng cách endpoint
        # 500 suốt mà bộ test vẫn xanh (schema đòi `loai_buoc`, service cố ý không trả).
        BuocMacDinhOut.model_validate(m)


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
                   cong_thuc_gia="so_luong * don_gia", department_ids=[to_id], setup_time=15,
                   don_vi_vao="m2", don_vi_ra="bai")
    xen = CongDoan(ma="CD-XEN-T", ten="Xén thành phẩm", nhom="finishing",
                   cong_thuc_gia="so_luong * don_gia", department_ids=[to_id], setup_time=10,
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


def test_mac_dinh_buoc_tra_kem_co_dung_cu(db, orders, lsx_svc, admin, customer):
    """Đổi công đoạn phải trả kèm `requires_tooling` + `tooling_type` CỦA CÔNG ĐOẠN MỚI.

    Ô chọn dao ở drawer bước lọc kho Khuôn & khung theo đúng hai cờ này (khách của lệnh × loại của
    bước). Không trả kèm thì dòng giữ cờ của công đoạn CŨ và frontend không suy lại được — đổi bước
    Bế sang một công đoạn cần KHUÔN ÉP KIM vẫn thấy thẻ "Khuôn của bước (khuôn bế)" và ô chọn vẫn
    bày dao bế, sai loại và im lặng cho tới lúc lưu rồi nạp lại màn.
    """
    ptg = _ptg_2_san_pham(db)
    to_id = _to_san_xuat(db).id
    ep = CongDoan(ma="CD-EP-T", ten="Ép kim", nhom="finishing",
                  cong_thuc_gia="so_luong * don_gia", department_ids=[to_id], setup_time=20,
                  don_vi_vao="to", don_vi_ra="to",
                  requires_tooling=True, tooling_type="khuon_ep")
    xen = CongDoan(ma="CD-XEN-D", ten="Xén thành phẩm", nhom="finishing",
                   cong_thuc_gia="so_luong * don_gia", department_ids=[to_id], setup_time=10,
                   don_vi_vao="to", don_vi_ra="to")
    db.add_all([ep, xen])
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [line["order_line_id"] for line in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    m = lsx_svc.mac_dinh_buoc(lsx_id=hop.id, cong_doan_id=ep.id)
    assert m["requires_tooling"] is True and m["tooling_type"] == "khuon_ep"
    BuocMacDinhOut.model_validate(m)
    # Công đoạn KHÔNG cần dụng cụ phải nói ra điều đó, không để client tự đoán bằng cách giữ cờ cũ.
    m2 = lsx_svc.mac_dinh_buoc(lsx_id=hop.id, cong_doan_id=xen.id)
    assert m2["requires_tooling"] is False and m2["tooling_type"] is None


def test_buoc_khung_lua_o_lenh_la_buoc_binh_thuong(db, orders, lsx_svc, admin, customer):
    """Chủ chốt 18/09/2026: khung lụa vẫn lưu kho + sale vẫn tính phí khung, nhưng ở LỆNH bước khung
    lụa KHÔNG hỏi khuôn — không thẻ "Khuôn của bước", không chặn "Sẵn sàng" vì chưa chọn khung.
    Loại dụng cụ vẫn trả về (phiếu / nhãn còn dùng), chỉ cờ "phải chốt khuôn" tắt."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    [hop, _tem] = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    # MỌI bước của lệnh đều thành bước khung lụa: seed có sẵn công đoạn bế/ép bật cờ dụng cụ, để
    # sót một bước là cửa vẫn đóng vì bước đó chứ không vì khung lụa.
    for buoc in hop.cong_doans:
        cd = db.get(CongDoan, buoc.cong_doan_id)
        cd.requires_tooling, cd.tooling_type = True, "khung_lua"
    db.commit()

    assert "thieu_khuon" not in lsx_svc.thieu_cua(lsx_svc.get(hop.id))
    m = lsx_svc.mac_dinh_buoc(lsx_id=hop.id, cong_doan_id=hop.cong_doans[0].cong_doan_id)
    assert m["requires_tooling"] is False and m["tooling_type"] == "khung_lua"


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


def test_doi_may_thi_thoi_luong_theo_may_moi(
    db, orders, lsx_svc, admin, customer
):
    """Đổi máy ⇒ thời lượng đọc SỐNG tốc độ của máy mới. Kíp người gỡ hẳn 18/09/2026 (mg 0321)."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line_id = lsx_svc.preview(d.id)["lines"][0]["order_line_id"]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=[line_id], actor=admin)[0]
    may_moi = MayThietBi(
        ma="MAY-KIP-2", ten="Máy kíp 2", loai_may="Bế", toc_do=4000,
        don_vi_toc_do="to_gio",
    )
    db.add(may_moi)
    db.commit()
    muc_tieu = next(x for x in hop.cong_doans if x.loai_buoc == "may")

    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, rows_in=[
        LsxCongDoanIn(
            step_key=x.step_key, cong_doan_id=x.cong_doan_id, ten=x.ten, nhom=x.nhom,
            department_id=x.department_id, loai_buoc=x.loai_buoc,
            may_id=may_moi.id if x.id == muc_tieu.id else x.may_id,
        )
        for x in sorted(hop.cong_doans, key=lambda item: item.thu_tu)
    ])

    saved = next(x for x in lsx_svc.get(hop.id).cong_doans if x.id == muc_tieu.id)
    assert saved.may_id == may_moi.id
    # Tốc độ KHÔNG chép lên bước (15/08/2026) — đổi máy là thời lượng tự đổi theo máy mới.
    assert round(_tl(saved, db)["chay_phut"], 2) == round(
        float(saved.so_luong_vao) * 60 / 4000, 2)


def test_xem_truoc_buoc_ra_gio_moi_ngay_va_khong_ghi_gi_vao_DB(
    db, orders, lsx_svc, admin, customer,
):
    """Chọn máy trong drawer là ra số NGAY (chủ 20/08/2026: *"khi chọn máy là phải lấy số luôn"*),
    nhưng chưa bấm Lưu thì DB không được đổi một chữ."""
    ptg = _ptg_2_san_pham(db)
    may_cham = MayThietBi(ma="MAY-IN-CHAM", ten="Máy in cũ", loai_may="press_offset_sheet",
                          toc_do=2_500, don_vi_toc_do="to_gio")
    db.add(may_cham)
    db.commit()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    inn = next(x for x in hop.cong_doans if x.ten == "In offset")
    may_cu, vao = inn.may_id, float(inn.so_luong_vao)
    assert may_cu is not None and may_cu != may_cham.id

    xt = lsx_svc.xem_truoc_buoc(lsx_id=hop.id, step_key=inn.step_key, may_id=may_cham.id)

    assert xt["thoi_luong_dien_giai"]["toc_do"] == 2_500
    assert xt["thoi_luong_dien_giai"]["chay_phut"] == pytest.approx(vao * 60 / 2_500, abs=0.01)
    # Máy cũ 5.000 tờ/giờ ⇒ máy này phải lâu gấp đôi, không phải "y hệt".
    assert xt["chiem_may_phut"] > _tl(inn, db)["chiem_may_phut"]

    db.expire_all()
    van_the = next(x for x in lsx_svc.get(hop.id).cong_doans if x.ten == "In offset")
    assert van_the.may_id == may_cu                                # KHÔNG ghi gì


def test_route_xem_truoc_buoc_dau_day_dung(client):
    """Đấu dây HTTP của cửa xem-trước: tên tham số + quyền + 404 khi lệnh không có thật.

    Service xanh mà route sai tên query (`step_key`) thì FastAPI trả 422 — drawer im ru, người
    dùng lại tưởng "chọn máy vẫn không đổi số" y như lỗi cũ.
    """
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert client.get("/api/lsx/1/xem-truoc-buoc?step_key=s1").status_code == 401
    assert client.get("/api/lsx/1/xem-truoc-buoc", headers=h).status_code == 422   # thiếu step_key
    assert client.get(
        "/api/lsx/999999/xem-truoc-buoc?step_key=s1&may_id=1&loai_buoc=to", headers=h,
    ).status_code == 404


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
    # Các số KHÁC của máy/công đoạn vẫn kế thừa bình thường.
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
                      he_so_quy_doi=c["he_so_quy_doi"], so_gio_ke_hoach=c["so_gio_ke_hoach"])
        for c in lsx_svc.detail_dict(hop)["cong_doans"]
    ])
    sau = {c.ten: c for c in lsx_svc.get(hop.id).cong_doans}
    assert sau["In offset"].chay_phut is None
    assert _tl(sau["In offset"], db)["chay_phut"] > 0

    # Bước TỔ gõ số giờ kế hoạch muộn vẫn ăn ngay (tổ không lấy tốc độ từ máy).
    sau["Dán hộp"].so_gio_ke_hoach = 2
    db.commit()
    assert _tl(lsx_svc.get(hop.id).cong_doans[-1], db)["chay_phut"] > 0


def test_replace_routing_ghi_ly_do_vao_audit(db, orders, lsx_svc, admin, customer):
    """§10: đổi routing của lệnh phải để lại vết LÝ DO trong audit, không sửa lén."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]
    assert hop.routing_goc_json
    to_id = _to_san_xuat(db).id
    cd_be = db.query(CongDoan).filter(CongDoan.ma == "CD-BE-T").first()
    cd_in = db.query(CongDoan).filter(CongDoan.nhom == "print").first()

    # Bế nhả CON rồi tới bước ăn TỜ → chuỗi đứt đơn vị. Đơn vị lấy từ DANH MỤC nên phải gắn
    # `cong_doan_id`, client gửi `don_vi_*` không còn tác dụng.
    lsx_svc.replace_routing(lsx_id=hop.id, actor=admin, ly_do="Khách đổi sang gia công ngoài", rows_in=[
        LsxCongDoanIn(ten="Bế", nhom="finishing", department_id=to_id, cong_doan_id=cd_be.id),
        LsxCongDoanIn(ten="In offset", nhom="print", department_id=to_id, cong_doan_id=cd_in.id),
    ])
    chi_tiet = [r.detail for r in AuditLogRepository(db).list_by_target(f"lsx:{hop.id}")]
    assert any("Khách đổi sang gia công ngoài" in c for c in chi_tiet)


def test_lead_time_dai_hon_so_ngay_con_lai_toi_han(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)   # hạn giao = hôm nay + 10 ngày
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    hop = lsx_svc.tao(order_id=d.id, order_line_ids=ids[:1], actor=admin)[0]

    for cd in hop.cong_doans:
        cd.may_id, cd.phat_sinh_phut = None, 0
    db.commit()
    lt0 = lsx_svc.lead_time(lsx_svc.get(hop.id))
    assert lt0["so_ngay"] <= lt0["ngay_con_lai"]

    # Bơm giờ bằng ô DUY NHẤT còn gõ được: 200 giờ ⇒ 25 ngày > 10 ngày còn lại.
    hop.cong_doans[0].phat_sinh_phut = 200 * 60
    db.commit()
    lt = lsx_svc.lead_time(lsx_svc.get(hop.id))
    assert lt["so_ngay"] > lt["ngay_con_lai"]


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
    """Nhánh "làm dao mới": khách + loại KHÔNG hỏi lại người dùng, lấy từ lệnh và từ bước.

    KHÔNG hỏi ngày dự kiến nữa (mg `0293`) — nhánh này chỉ còn TÊN là thứ người dùng phải gõ.
    """
    from app.models.khuon_be import KhuonBe

    lsx = _lenh_don_gian(db, orders, lsx_svc, admin, customer)
    ra = lsx_svc.tao_khuon_cho_lenh(
        lsx, ten="Hộp bánh trung thu 20×20", loai="khuon_be", actor=admin,
    )
    assert ra["ma"].startswith("KB-")          # mã do danh mục sinh, không phải tự đặt
    assert ra["tinh_trang"] == "dang_dat_lam"

    k = db.get(KhuonBe, ra["id"])
    assert k.khach_hang_id == customer.id      # lấy từ lệnh
    assert k.loai == "khuon_be"                # lấy từ cờ của bước

    # Và nó xuất hiện ngay trong danh sách chọn của chính lệnh đó.
    assert ra["id"] in {x["id"] for x in lsx_svc.khuon_chon_duoc(lsx, loai="khuon_be", dang_chon=None)}


# ============================ Phân trang + đếm ở MÁY CHỦ ============================
# Cả cụm này chốt hợp đồng của đợt tối ưu 100k lệnh (18/08/2026): danh sách PHẢI cắt trang ở SQL
# và số trên tab PHẢI là số của máy chủ, không phải số dòng đang hiện.
def test_list_cat_trang_va_tra_tong_that(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx_svc.tao(order_id=d.id, order_line_ids=[l["order_line_id"] for l in lines], actor=admin)

    rows, total = lsx_svc.list_rows(order_id=d.id, page=1, size=1)
    assert total == 2 and len(rows) == 1, "total là TỔNG khớp lọc, không phải số dòng của trang"
    rows2, total2 = lsx_svc.list_rows(order_id=d.id, page=2, size=1)
    assert total2 == 2 and len(rows2) == 1
    assert rows[0]["id"] != rows2[0]["id"], "hai trang không được trả trùng dòng"
    assert not lsx_svc.list_rows(order_id=d.id, page=3, size=1)[0], "quá trang cuối thì rỗng"


def test_list_kep_size_ve_tran_khong_cho_client_keo_ca_bang(db, orders, lsx_svc, admin, customer):
    from app.repositories.catalog_base import SIZE_TRAN

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lsx_svc.tao(order_id=d.id,
                order_line_ids=[l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]],
                actor=admin)
    # ?size=99999 phải bị kẹp — không thì một cú gọi kéo cả 100.000 lệnh kèm công đoạn.
    rows, _ = LsxRepository(db).list(size=99_999)
    assert len(rows) <= SIZE_TRAN


def test_facets_dem_ca_trang_thai_dang_bi_loc_ra(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lenhs = lsx_svc.tao(
        order_id=d.id,
        order_line_ids=[l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]],
        actor=admin)
    _gan_dao_cho_buoc_can(db, lenhs[0])
    lsx_svc.set_trang_thai(lsx_id=lenhs[0].id, trang_thai=TT_SAN_SANG, actor=admin)

    facets = lsx_svc.dem_trang_thai(order_id=d.id, trang_thai=TT_NHAP)
    # Đang đứng ở tab Nháp nhưng tab "Sẵn sàng" vẫn phải khoe số 1 của nó, không thì bấm sang tab
    # trống hoá ra lại có dòng.
    assert facets[TT_SAN_SANG] == 1 and facets[TT_NHAP] == 1 and facets["all"] == 2


def test_hang_cho_giu_don_khong_co_dong_nao(db, orders, lsx_svc, admin, customer):
    """Đơn 0 dòng vẫn nằm lại hàng chờ — hành vi cũ của bộ lọc Python (`if so_dong and …`)."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    from app.models.order import OrderLine

    db.query(OrderLine).filter(OrderLine.order_id == d.id).delete()
    db.commit()

    rows, total = lsx_svc.hang_cho()
    row = next(r for r in rows if r["order_id"] == d.id)
    assert row["so_dong"] == 0 and total >= 1


def test_hang_cho_cat_trang(db, orders, lsx_svc, admin, customer):
    ptg = _ptg_2_san_pham(db)
    d1 = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    d2 = _don_da_chuyen_sx(db, orders, admin, customer, ptg)

    rows, total = lsx_svc.hang_cho(page=1, size=1)
    assert total >= 2 and len(rows) == 1
    thay = {r["order_id"] for r in rows} | {r["order_id"] for r in lsx_svc.hang_cho(page=2, size=1)[0]}
    assert {d1.id, d2.id} <= thay


# --- Lệch ý định khuôn: sale định một đằng, kế hoạch chốt một nẻo (chốt 04/09/2026) -------------
def test_khuon_lech_sale_bao_co_san_ma_dao_dang_dat_lam():
    """Máy chỉ NHẮC, không chặn: tiền đã trót báo cho khách nên người phải biết mà quyết."""
    from app.services.lsx_service import canh_bao_lech_khuon
    msg = canh_bao_lech_khuon("co_san", 0, "dang_dat_lam")
    assert msg is not None and "có sẵn" in msg


def test_khuon_lech_sale_tinh_tien_ma_dung_dao_cu():
    from app.services.lsx_service import canh_bao_lech_khuon
    msg = canh_bao_lech_khuon("lam_moi", 1_200_000, "dang_dung")
    assert msg is not None and "1.200.000" in msg


def test_khuon_khong_lech_thi_im_lang():
    from app.services.lsx_service import canh_bao_lech_khuon
    assert canh_bao_lech_khuon("lam_moi", 1_200_000, "dang_dat_lam") is None
    assert canh_bao_lech_khuon("co_san", 0, "dang_dung") is None
    assert canh_bao_lech_khuon(None, 0, "dang_dung") is None


# --- Cửa "Sẵn sàng lập kế hoạch" đòi đủ khuôn (chốt 04/09/2026) ---------------------------------
def _buoc_can_dao(db, hop):
    """Biến bước đầu của lệnh thành bước CẦN DAO — bật cờ ở DANH MỤC, không ghi cứng tên bước."""
    from app.models.cong_doan import CongDoan

    buoc = hop.cong_doans[0]
    cd = db.get(CongDoan, buoc.cong_doan_id)
    cd.requires_tooling = True
    cd.tooling_type = "khuon_be"
    db.commit()
    return buoc


def test_thieu_khuon_chan_san_sang(db, orders, lsx_svc, admin, customer):
    """Bước bế chưa trỏ dao → không qua cửa. Đứng NGANG HÀNG với thiếu nhà gia công: cùng một danh
    sách, người dùng không phải học luật mới. Trước đây cửa im lặng, tới lúc thợ ra máy mới biết
    không có dao."""
    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    [hop, _tem] = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    _buoc_can_dao(db, hop)
    assert "thieu_khuon" in lsx_svc.thieu_cua(lsx_svc.get(hop.id))


def test_tro_dao_roi_thi_het_thieu_khuon(db, orders, lsx_svc, admin, customer):
    from app.models.khuon_be import KhuonBe

    ptg = _ptg_2_san_pham(db)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
    [hop, _tem] = lsx_svc.tao(order_id=d.id, order_line_ids=ids, actor=admin)
    buoc = _buoc_can_dao(db, hop)
    dao = KhuonBe(ma="KB-9001", ten="Dao bế hộp", loai="khuon_be", tinh_trang="dang_dung")
    db.add(dao)
    db.flush()
    # Trỏ dao cho MỌI bước của lệnh, không chỉ bước vừa bật cờ: danh mục seed sẵn có công đoạn
    # khác cũng bật `requires_tooling` (bế/ép), bỏ sót một bước thì cửa vẫn đóng và test này đọc
    # như hàm hỏng trong khi hàm đúng.
    for cd in hop.cong_doans:
        cd.khuon_be_id = dao.id
    _ = buoc
    db.commit()
    assert "thieu_khuon" not in lsx_svc.thieu_cua(lsx_svc.get(hop.id))


def test_xem_truoc_buoc_doi_LOAI_va_SO_GIO_thi_so_doi_theo_form(
    db, orders, lsx_svc, admin, customer,
):
    """⭐ Drawer sửa gì thì xem trước phải nói theo cái đang sửa, không đợi Lưu.

    Bước đang lưu là MÁY, người dùng bấm sang TỔ và gõ 1,5 giờ kế hoạch ⇒ xem trước ra 90 phút
    ngay; số lượt không nhân vào giờ của tổ. Không ghi gì xuống DB.
    """
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").one()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    line = lsx_svc.preview(d.id)["lines"][0]
    lsx = lsx_svc.get(lsx_svc.tao(order_id=d.id, order_line_ids=[line["order_line_id"]],
                                 actor=admin)[0].id)
    buoc = next(x for x in lsx.cong_doans if x.cong_doan_id == cd_dan.id)
    assert buoc.loai_buoc == "may", "bước bung ra phải là máy thì mới thử được chiều đổi sang tổ"

    def _xt(**thay) -> dict:
        return lsx_svc.xem_truoc_buoc(lsx_id=lsx.id, step_key=buoc.step_key, may_id=None, **thay)

    to = _xt(loai_buoc="to", so_gio_ke_hoach=1.5, so_luot_chay=1)
    assert to["thoi_luong_dien_giai"]["chay_phut"] == pytest.approx(90)
    assert "khoan" not in to

    hai = _xt(loai_buoc="to", so_gio_ke_hoach=1.5, so_luot_chay=2)
    assert hai["thoi_luong_dien_giai"]["chay_phut"] == pytest.approx(90)

    db.expire_all()
    van_the = next(x for x in lsx_svc.get(lsx.id).cong_doans if x.cong_doan_id == cd_dan.id)
    assert van_the.loai_buoc == "may" and float(van_the.so_gio_ke_hoach or 0) == 0


# ================= Danh mục đổi dưới chân lệnh =================
# Ảnh chụp KHÔNG tự đổi là đúng thiết kế (lệnh đã bung không được tự đổi số dưới chân thợ) —
# nhưng im lặng thì sai: người lập kế hoạch chẳng có gì để BIẾT mà bấm lấy số mới. Bộ test dưới
# canh đúng cặp đó: BÁO cho đủ, và GHI cho đúng những gì đã báo.
#
# Từ 18/09/2026 (mg 0320) nửa KHOÁN của băng gỡ hẳn — bước thôi ghim đầu việc. Băng còn VẬT TƯ của
# công đoạn và MÁY bị gỡ khỏi công đoạn; ảnh chụp đơn giá nay nằm ở MẺ (băng riêng ở bàn tổ).

def _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer):
    """Lệnh có bước "Dán hộp" — điểm xuất phát chung của cả nhóm test này."""
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]
    return lsx_svc.get(lsx.id), cd_dan


def _buoc_dm(lsx_svc, lsx, ten="Dán hộp"):
    return next(b for b in lsx_svc.detail_dict(lsx)["cong_doans"] if b["ten"] == ten)


def test_vua_bung_xong_thi_khong_co_bang_danh_muc_nao(db, orders, lsx_svc, admin, customer):
    """Băng phải im khi lệnh còn khớp danh mục. Băng vàng hiện thường trực là băng bị bỏ qua."""
    lsx, _ = _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer)
    assert lsx_svc.detail_dict(lsx)["danh_muc_doi"] is None


def test_cap_nhat_theo_danh_muc_ghi_so_moi_roi_bang_tat(db, orders, lsx_svc, admin, customer):
    """So NỘI DUNG: xưởng sửa CÔNG THỨC định mức của dòng vật tư ⇒ băng báo lệch đúng món, bấm
    cập nhật là ghi số mới và băng tắt."""
    lsx, cd_dan = _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer)
    _khai_vat_tu_cho_cong_doan(db, cd_dan)
    lsx = lsx_svc.dong_bo_danh_muc(lsx_id=lsx.id, actor=admin)
    [cu] = _buoc_dm(lsx_svc, lsx)["vat_tus"]

    cd_dan.vat_tus[0].cong_thuc_luong = "sl_vao / 5000"          # gấp đôi
    db.commit()
    dm = lsx_svc.detail_dict(lsx_svc.get(lsx.id))["danh_muc_doi"]
    assert dm is not None and dm["so_buoc"] == 1
    [lech] = dm["buocs"][0]["vat_tu_lech"]
    assert lech["ma"] == "VT-KEO"
    assert lech["so_luong_moi"] == pytest.approx(cu["so_luong"] * 2, rel=1e-3)
    assert dm["co_the_cap_nhat"] is True and dm["ly_do_khoa"] is None

    saved = lsx_svc.dong_bo_danh_muc(lsx_id=lsx.id, actor=admin)
    [dong] = _buoc_dm(lsx_svc, saved)["vat_tus"]
    assert dong["so_luong"] == pytest.approx(cu["so_luong"] * 2, rel=1e-3)
    # Băng TẮT sau khi ghi — còn sáng nghĩa là nút vừa bấm không làm được việc nó hứa.
    assert lsx_svc.detail_dict(saved)["danh_muc_doi"] is None


def test_lenh_da_lap_ke_hoach_van_thay_bang_nhung_khong_bam_duoc(
    db, orders, lsx_svc, admin, customer,
):
    """Biết mà chưa sửa được vẫn hơn không biết: băng vẫn hiện, chỉ nút khoá và nói rõ đường lùi.
    Cùng ba cửa mà `replace_routing` chặn — nới ở đây là mở cửa hậu cho chính thứ vừa khoá."""
    lsx, cd_dan = _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer)
    _khai_vat_tu_cho_cong_doan(db, cd_dan)
    lsx.trang_thai = TT_DA_LAP_KE_HOACH
    db.commit()

    dm = lsx_svc.detail_dict(lsx_svc.get(lsx.id))["danh_muc_doi"]
    assert dm["so_buoc"] == 1, "vẫn phải BÁO"
    assert dm["co_the_cap_nhat"] is False
    assert "gỡ kế hoạch" in dm["ly_do_khoa"]
    with pytest.raises(LsxConflict):
        lsx_svc.dong_bo_danh_muc(lsx_id=lsx.id, actor=admin)


def _khai_vat_tu_cho_cong_doan(db, cd, *, ma="VT-KEO", ct="sl_vao / 10000"):
    """Xưởng khai định mức vật tư cho công đoạn — việc làm SAU khi lệnh đã bung."""
    muc = VatTuInAn(ma=ma, ten="Keo dán hộp", don_vi_gia="kg", don_gia=90_000, active=True)
    db.add(muc)
    db.flush()
    cd.vat_tus.append(CongDoanVatTu(vat_tu_id=muc.id, thu_tu=0, cong_thuc_luong=ct))
    db.commit()
    return muc


def test_them_dinh_muc_vat_tu_sau_khi_bung_thi_bao_them_va_cap_nhat_them_dong(
    db, orders, lsx_svc, admin, customer,
):
    """Đúng tình huống 07/09/2026: xưởng khai định mức vật tư cho công đoạn SAU khi lệnh đã bung.
    Bước lệnh không hay biết vì `lsx_cong_doan_vat_tu` chỉ được ghi lúc drawer gửi `vat_tus`."""
    lsx, cd_dan = _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer)
    # Đọc THẲNG ORM chứ không qua `detail_dict`: một lần đọc lệnh làm nóng `_vat_tu_cache` của
    # service, mà ngoài đời mỗi lần mở màn là một request ⇒ một service mới. Gọi ở đây là dựng ra
    # một tình huống không có thật rồi bắt code chiều nó.
    assert list(next(c for c in lsx.cong_doans if c.ten == "Dán hộp").vat_tus) == []
    _khai_vat_tu_cho_cong_doan(db, cd_dan)

    b = lsx_svc.detail_dict(lsx_svc.get(lsx.id))["danh_muc_doi"]["buocs"][0]
    assert [x["ma"] for x in b["vat_tu_them"]] == ["VT-KEO"]
    assert b["vat_tu_them"][0]["so_luong_cu"] is None

    saved = lsx_svc.dong_bo_danh_muc(lsx_id=lsx.id, actor=admin)
    [dong] = _buoc_dm(lsx_svc, saved)["vat_tus"]
    assert dong["vat_tu_ma"] == "VT-KEO" and dong["so_luong"] > 0
    assert lsx_svc.detail_dict(saved)["danh_muc_doi"] is None


def test_dong_vat_tu_nguoi_khai_tay_khong_bi_so_danh_muc_de_len(
    db, orders, lsx_svc, admin, customer,
):
    """Người ta đã cố ý gõ đè số đó — lấy số danh mục ghi lên là xoá việc họ vừa làm."""
    from app.models.lsx import LsxCongDoanVatTu

    lsx, cd_dan = _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer)
    muc = _khai_vat_tu_cho_cong_doan(db, cd_dan)
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    db.add(LsxCongDoanVatTu(
        lsx_cong_doan_id=buoc.id, vat_tu_id=muc.id, vat_tu_ma_snapshot=muc.ma,
        vat_tu_ten_snapshot=muc.ten, don_vi_snapshot="kg", so_luong=9.9, thu_tu=0, tu_dong=False,
    ))
    db.commit()

    # Số tay khác số danh mục nhưng KHÔNG vào rổ lệch ⇒ băng cũng không hiện vì chuyện này.
    dm = lsx_svc.detail_dict(lsx_svc.get(lsx.id))["danh_muc_doi"]
    assert dm is None or dm["buocs"][0]["vat_tu_lech"] == []

    lsx_svc.dong_bo_danh_muc(lsx_id=lsx.id, actor=admin)
    [dong] = _buoc_dm(lsx_svc, lsx_svc.get(lsx.id))["vat_tus"]
    assert dong["so_luong"] == 9.9, "số người khai phải nguyên vẹn"


def test_go_dinh_muc_vat_tu_o_danh_muc_thi_chi_bao_khong_xoa_dong(
    db, orders, lsx_svc, admin, customer,
):
    """Dòng ấy vẫn tính vào nhu cầu vật tư — máy đoán sai là mất một dòng vật tư thật, nên bỏ hay
    giữ là quyết định của người lập kế hoạch."""
    lsx, cd_dan = _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer)
    _khai_vat_tu_cho_cong_doan(db, cd_dan)
    lsx_svc.dong_bo_danh_muc(lsx_id=lsx.id, actor=admin)          # bước đã có dòng keo

    # Xưởng gỡ món khỏi tab Vật tư của công đoạn ⇒ danh mục không bung món này nữa.
    db.query(CongDoanVatTu).filter_by(cong_doan_id=cd_dan.id).delete()
    db.commit()
    db.expire_all()

    b = lsx_svc.detail_dict(lsx_svc.get(lsx.id))["danh_muc_doi"]["buocs"][0]
    assert [x["ma"] for x in b["vat_tu_bo"]] == ["VT-KEO"]

    lsx_svc.dong_bo_danh_muc(lsx_id=lsx.id, actor=admin)
    assert [x["vat_tu_ma"] for x in _buoc_dm(lsx_svc, lsx_svc.get(lsx.id))["vat_tus"]] == ["VT-KEO"]


def test_go_may_khoi_cong_doan_thi_bao_may_dang_gan_khong_con_thuoc(
    db, orders, lsx_svc, admin, customer,
):
    """Công thức giờ chạy của cặp (công đoạn × máy) đọc SỐNG lúc tính thời lượng nên không trôi
    được. Thứ DUY NHẤT trôi là danh sách máy — bước vẫn ôm `may_id` đã bị gỡ."""
    from app.models.cong_doan import CongDoanMay

    lsx, cd_be = _lenh_co_buoc_dan(db, orders, lsx_svc, admin, customer)
    may = db.query(MayThietBi).filter(MayThietBi.ma == "MAY-IN-T").one()
    # Công đoạn CHỈ khai một máy khác ⇒ máy đang gán ở bước rơi ra ngoài danh sách.
    db.add(CongDoanMay(cong_doan_id=cd_be.id, may_id=may.id + 999))
    buoc = next(c for c in lsx.cong_doans if c.ten == "Dán hộp")
    buoc.may_id = may.id
    db.commit()

    b = lsx_svc.detail_dict(lsx_svc.get(lsx.id))["danh_muc_doi"]["buocs"][0]
    assert "không còn nằm trong danh sách máy" in b["may_canh_bao"]


def test_dong_vat_tu_cua_buoc_mang_hang_loai_va_cho_trung_id_khac_loai(db):
    """Giấy #7 và Vật tư #7 là HAI món khác nhau — unique key phải gồm cả `hang_loai`."""
    from app.models.lsx import LsxCongDoanVatTu

    cols = {c.name for c in LsxCongDoanVatTu.__table__.columns}
    assert "hang_loai" in cols
    uq = next(c for c in LsxCongDoanVatTu.__table__.constraints
              if getattr(c, "name", "") == "uq_lsx_buoc_vat_tu")
    assert [c.name for c in uq.columns] == ["lsx_cong_doan_id", "hang_loai", "vat_tu_id"]


@pytest.fixture()
def lenh_giay(db):
    """Lệnh tối thiểu: 1 bước in, quy cách đủ khổ nguyên + định lượng + số tờ nguyên.

    Không seed công đoạn/đầu việc: ca đang kiểm là giấy CHỌN TAY, thứ không đi qua đầu việc nào.
    """
    from app.models.lsx import TT_SAN_SANG, Lsx, LsxCongDoan
    from app.models.order import Order, OrderLine

    c = db.query(Customer).first() or Customer(code="KH-GIAY", name="KH Giấy")
    db.add(c)
    db.flush()
    o = Order(order_no="DH-GIAY", customer_id=c.id)
    db.add(o)
    db.flush()
    ln = OrderLine(order_id=o.id, description="hộp giấy", qty=2000)
    db.add(ln)
    db.flush()

    l = Lsx(ma="LSX-GIAY", ten="LSX-GIAY", order_id=o.id, order_line_id=ln.id,
            so_luong_dat=2000, so_to_nguyen=553, so_con=9,
            trang_thai=TT_SAN_SANG,
            quy_cach_json={"kho_nguyen_dai": 860, "kho_nguyen_rong": 650, "gsm": 300})
    db.add(l)
    db.flush()
    b = LsxCongDoan(lsx_id=l.id, thu_tu=1, ten="In offset", loai_buoc="may",
                    don_vi_vao="to_nguyen", don_vi_ra="to",
                    so_luong_vao=553, so_luong_ra=553)
    db.add(b)
    db.commit()
    return l, b


def test_goi_y_luong_co_ca_GIAY_va_ra_kg_bang_cong_thuc_cua_chinh_loai_giay(db, lsx_svc, lenh_giay):
    """Giấy chọn tay ở bước ⇒ lượng suy bằng `giay_nguyen.cong_thuc_luong`, ra ĐƠN VỊ GỐC (kg).

    Không có đầu việc nào khai giấy — đó chính là ca thật: giấy tuỳ từng đơn, không khai trước ở
    danh mục công đoạn được. Nên nguồn công thức phải là CHÍNH MÓN GIẤY, khác hẳn mực.
    """
    from app.services.bien_cong_thuc import quy_cach_bien

    lsx, buoc = lenh_giay
    g = GiayNguyen(
        ma="GY-C300", ten="Giấy C300", gsm=300, kho_dai=860, kho_rong=650, don_vi_gia="kg",
        cong_thuc_luong="dinh_luong * dai_nguyen * rong_nguyen * to_nguyen",
    )
    db.add(g)
    db.commit()

    goi_y = lsx_svc._goi_y_luong_vat_tu(buoc, quy_cach_bien(lsx))
    dong = next(x for x in goi_y if x["hang_loai"] == "giay" and x["vat_tu_id"] == g.id)

    # 0,3 kg/m² × 0,86 m × 0,65 m × 553 tờ nguyên = 92,73 kg
    assert dong["so_luong"] == pytest.approx(92.73, abs=0.01)
    assert dong["ly_do"] is None


def test_goi_y_GIAY_chua_khai_cong_thuc_thi_chi_thang_danh_muc_GIAY_khong_chi_dau_viec(
    db, lsx_svc, lenh_giay,
):
    """Câu lý do phải chỉ đúng ô người dùng cần mở — giấy khai ở danh mục Giấy, không ở đầu việc."""
    from app.services.bien_cong_thuc import quy_cach_bien

    lsx, buoc = lenh_giay
    g = GiayNguyen(ma="GY-TRONG", ten="Giấy chưa khai", gsm=300, kho_dai=860, kho_rong=650,
                   don_vi_gia="kg")
    db.add(g)
    db.commit()

    dong = next(x for x in lsx_svc._goi_y_luong_vat_tu(buoc, quy_cach_bien(lsx))
                if x["hang_loai"] == "giay" and x["vat_tu_id"] == g.id)
    assert dong["so_luong"] is None
    assert "danh mục Giấy" in dong["ly_do"]
    assert "Đầu việc" not in dong["ly_do"]
