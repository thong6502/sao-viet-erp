"""Đề nghị cấp vật tư theo công đoạn (docs/spec-de-nghi-cap-vat-tu-cong-doan.md).

Hai bảng SẢN XUẤT giữ bản đối chiếu ĐẦY ĐỦ (kể cả dòng xin 0); yêu cầu kho là ẢNH CHIẾU chỉ chứa
dòng dương. Test file này chốt: cấu trúc, luật lý do, luật khoá, luật quyền, và luật "sửa hết về 0".

Fixture `db` (+ `admin`/`customer`/`orders`/`lsx_svc`) KHÔNG khai lại ở đây — tái xuất từ
`tests.test_san_xuat_thuc_thi`, nơi dựng đúng luồng thật (đơn → SX → sẵn sàng → phát hành vào tổ)
mà `_kh_service`/`nhu_cau_cua_cong_viec` cần để có LSX/routing thật. Khai một fixture `db` cục bộ
KHÁC ở đây là hai định nghĩa `db` chồng nhau trong cùng module — cái sau âm thầm che cái trước.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.san_xuat_vat_tu import (
    DN_BO_SUNG, DN_LAN_DAU, SanXuatVatTuDeNghi, SanXuatVatTuDeNghiDong,
)
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _mot_cv, admin, customer, db, lsx_svc, orders,
)

_T0 = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


def _kh_service(db):
    """Dựng `KeHoachVatTuService` đúng bộ repo như `routers/ke_hoach_vat_tu.py::get_service()`.

    Ghép THIẾU một repo là engine im lặng trả rỗng (không lỗi, không cảnh báo) — nên copy nguyên
    danh sách từ router, không tự rút gọn.
    """
    from app.repositories.bai_ghep_repo import BaiGhepRepository
    from app.repositories.don_vi_do_repo import DonViDoRepository
    from app.repositories.lsx_repo import LsxRepository
    from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
    from app.repositories.stock_lot_repo import StockLotRepository
    from app.repositories.stock_request_repo import StockRequestRepository
    from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from app.services.ke_hoach_vat_tu_service import KeHoachVatTuService
    from app.services.vat_lieu_kho_service import VatLieuKhoService

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


# --- Task 1: hai bảng + cột mới (giữ nguyên, chạy lại để chắc còn xanh sau khi đổi fixture) ---

def test_mot_cong_viec_khong_co_hai_lan_cung_so(db):
    for _ in range(2):
        db.add(SanXuatVatTuDeNghi(cong_viec_id=1, lan_so=1, loai=DN_LAN_DAU, can_luc=_T0))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_mot_de_nghi_khong_co_hai_dong_cung_mat_hang(db):
    dn = SanXuatVatTuDeNghi(cong_viec_id=2, lan_so=1, loai=DN_LAN_DAU, can_luc=_T0)
    db.add(dn)
    db.flush()
    for _ in range(2):
        db.add(SanXuatVatTuDeNghiDong(
            de_nghi_id=dn.id, hang_loai="giay", hang_id=9, dvt="tờ", dvt_goc="kg",
            sl_ke_hoach=100, sl_ke_hoach_goc=12, sl_yeu_cau=100, sl_yeu_cau_goc=12,
        ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_mot_yeu_cau_kho_chi_thuoc_mot_de_nghi(db):
    for lan in (1, 2):
        db.add(SanXuatVatTuDeNghi(cong_viec_id=3, lan_so=lan, loai=DN_LAN_DAU,
                                  can_luc=_T0, stock_request_id=555))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_dong_yeu_cau_kho_mac_dinh_chua_chot_thuc_xuat(db):
    """`sl_chot_thuc_xuat` NULL = kho CHƯA điều chỉnh. KHÁC hẳn 0 (đã chốt là không xuất gì)."""
    from app.models.stock_request import StockRequestLine

    ln = StockRequestLine(request_id=1, hang_loai="giay", hang_id=1, dvt="kg", sl_de_nghi=100)
    assert ln.sl_chot_thuc_xuat is None


def test_migration_0249_co_trong_danh_sach():
    from app.db_migrations import MIGRATIONS
    assert any(ma == "0249_sx_vat_tu_de_nghi" for ma, _fn in MIGRATIONS)


# --- Task 2: nhu_cau_cua_cong_viec — nguồn kế hoạch của một công đoạn -------------------------

def test_nhu_cau_cua_cong_viec_tra_ca_hai_thang_don_vi(db, orders, lsx_svc, admin, customer):
    """Bước IN của một lệnh phải ra dòng GIẤY, kèm cả đơn vị kế hoạch lẫn đơn vị gốc.

    KHÔNG lấy từ `SanXuatCongViec.vat_tu_json`: snapshot đó chỉ có vật tư khai TAY ở bước, không
    có giấy — mà giấy mới là thứ tổ in cần xin.
    """
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT1")
    kh = _kh_service(db)          # helper của file này, dựng đúng chuỗi như routers/ke_hoach_vat_tu.py
    ra = kh.nhu_cau_cua_cong_viec(cv)

    assert ra, "bước phải có ít nhất một dòng nhu cầu"
    d = ra[0]
    assert set(d) >= {"hang_loai", "hang_id", "ten", "dvt", "sl", "dvt_goc", "sl_goc"}
    assert d["sl"] > 0 and d["sl_goc"] > 0


def test_nhu_cau_gop_trung_theo_mat_hang(db, orders, lsx_svc, admin, customer):
    """Hai dòng cùng mặt hàng (vd khai tay trùng loại giấy) phải gộp thành MỘT sau khi về đơn vị
    gốc — không thì tổ nhìn thấy hai dòng y hệt và không biết sửa dòng nào."""
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT2")
    ra = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    khoa = [(d["hang_loai"], d["hang_id"]) for d in ra]
    assert len(khoa) == len(set(khoa))


def test_nhu_cau_cong_viec_khong_thuoc_lenh_bai_nao_tra_rong(db, orders, lsx_svc, admin, customer):
    """Công việc không mang `lsx_id`/`bai_ghep_id` (vd việc phụ trợ) thì không có nguồn kế hoạch
    để suy — trả rỗng, không phải lỗi."""
    from types import SimpleNamespace

    kh = _kh_service(db)
    cv = SimpleNamespace(lsx_id=None, bai_ghep_id=None, lsx_cong_doan_id=None,
                         bai_ghep_cong_doan_id=None)
    assert kh.nhu_cau_cua_cong_viec(cv) == []


def test_ve_don_vi_goc_quy_dung_va_bao_loi_ro_khi_khong_quy_duoc(db, orders, lsx_svc, admin, customer):
    """`ve_don_vi_goc` là wrapper công khai quanh `_ve_goc` — Task 3 dựa vào số này để so lệch kế
    hoạch. Mặt hàng không có trong danh mục thì phải NÉM LỖI, không trả 0 im lặng.

    Đổi kg → tấn (cặp TĨNH "1 tấn = 1.000 kg" đã seed, xem `seed_rebuild._QUY_DOI_SEED`) — quy đổi
    này KHÔNG cần khổ giấy nên đường tĩnh đủ dùng. Khác nhánh "tờ → kg" của giấy: nhánh đó chỉ chạy
    qua công thức lượng của LỆNH (`_ve_goc(..., tong_lenh=True)`, dùng trong `nhu_cau_cua_cong_viec`)
    — `ve_don_vi_goc` không có ngữ cảnh lệnh nên KHÔNG dùng nhánh đó, đúng theo chữ ký đã chốt.
    """
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT3")
    ra = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    assert ra, "cần một dòng thật để lấy đúng mặt hàng"
    d = ra[0]

    # Instance MỚI, CHƯA gọi `nhu_cau_cua_cong_viec`/`can_doi` nào — `ve_don_vi_goc` phải tự nạp
    # `_objs`/`_dvs` cho riêng mặt hàng này, không dựa vào một lượt gọi trước đó.
    kh2 = _kh_service(db)
    sl_goc, ten_dv_goc = kh2.ve_don_vi_goc(d["hang_loai"], d["hang_id"], "kg", 1000)
    assert sl_goc == pytest.approx(1.0)
    assert ten_dv_goc == "tấn"

    from app.services.ke_hoach_vat_tu_service import KeHoachVatTuError

    with pytest.raises(KeHoachVatTuError):
        kh2.ve_don_vi_goc("giay", 999_999, "tờ", 10)


# --- Vòng sửa 1: phạm vi HẸP thật (2 phát hiện Important của người rà) -----------------------

def test_theo_ids_dung_lenh_goi_ten_khong_bi_loc_trang_thai(db, orders, lsx_svc, admin, customer):
    """`theo_ids` là đường HẸP thật cho một công việc — khác `cho_mrp`, hàm luôn OR thêm điều
    kiện `trang_thai IN TRANG_THAI_TINH` (đúng cho MRP toàn xưởng, sai cho một công việc: kéo về
    mọi lệnh còn sống). Ép lệnh về một trạng thái NGOÀI `TRANG_THAI_TINH` (`TT_NHAP`) để chứng
    minh `theo_ids` không hề đọc cột `trang_thai` — nếu ai đó lỡ tay thêm điều kiện lọc vào, lệnh
    NHAP sẽ biến mất khỏi kết quả và test này đỏ.
    """
    from app.models.lsx import TT_NHAP, Lsx
    from app.repositories.lsx_repo import LsxRepository

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT4")
    lsx_id = cv.lsx_id
    lsx = db.get(Lsx, lsx_id)
    lsx.trang_thai = TT_NHAP
    db.commit()

    repo = LsxRepository(db)
    ra = repo.theo_ids({lsx_id})
    assert [l.id for l in ra] == [lsx_id]
    assert repo.theo_ids(set()) == []


def test_nhu_cau_cong_viec_bai_ghep_ra_dung_bai_qua_theo_ids(db, orders, lsx_svc, admin, customer):
    """Công việc mang `bai_ghep_id` (nhánh trước đây chưa test nào chạm) vẫn phải chạy được:
    `bais` lấy đích danh bài bằng `bai_ghep_repo.get(bai_id)`, rồi `lsx_repo.theo_ids` nạp đúng
    các lệnh thành viên (không đi qua `cho_mrp`). Test chạy QUA nhánh thật (không phải đọc
    thuộc tính rồi assert hằng số): dựng một bài ghép tối thiểu (2 lệnh + 1 bước chung), gọi
    `nhu_cau_cua_cong_viec` với `cv` giả neo đúng `bai_ghep_id`/`bai_ghep_cong_doan_id`, và đòi
    kết quả THẬT (dòng giấy, sl > 0) — không phải danh sách rỗng do lỗi âm thầm nuốt phạm vi.
    """
    from types import SimpleNamespace

    from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
    from app.models.bai_ghep_cong_doan import BaiGhepCongDoan
    from tests.test_ke_hoach_vat_tu import _giay, _lenh

    g = _giay(db, ma="GY-BAI-VT")
    a = _lenh(db, customer, ma="LSX-BAI-VT-A", giay_id=g.id, so_to_nguyen=1_000)
    b = _lenh(db, customer, ma="LSX-BAI-VT-B", giay_id=g.id, so_to_nguyen=1_000)
    bg = BaiGhep(ma="GB-VT-001", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
        BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1),
    ])
    chung = BaiGhepCongDoan(bai_ghep_id=bg.id, thu_tu=1, ten="In chung", nhom="print", loai_buoc="may")
    db.add(chung)
    db.commit()

    cv = SimpleNamespace(lsx_id=None, bai_ghep_id=bg.id, lsx_cong_doan_id=None,
                         bai_ghep_cong_doan_id=chung.id)
    ra = _kh_service(db).nhu_cau_cua_cong_viec(cv)

    assert ra, "công việc mang bai_ghep_id phải ra dòng nhu cầu (nhánh vừa sửa)"
    assert all(d["sl"] > 0 for d in ra)
    assert {(d["hang_loai"], d["hang_id"]) for d in ra} == {("giay", g.id)}
