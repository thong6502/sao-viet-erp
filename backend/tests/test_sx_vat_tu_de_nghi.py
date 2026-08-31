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


# --- Task 3: repository + luật tạo đề nghị --------------------------------------------------

def test_tao_luu_ca_dong_xin_0_va_chi_gui_kho_dong_duong(
    db, orders, lsx_svc, admin, customer,
):
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT3")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    assert len(kh) >= 1

    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"],
              "dvt": kh[0]["dvt"], "sl_yeu_cau": 0, "ly_do_chenh_lech": "Tổ còn tồn tại chỗ"}]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    dn = db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"])
    assert dn.lan_so == 1 and dn.loai == DN_LAN_DAU
    assert len(dn.dongs) == len(kh)          # lưu MỌI vật tư kế hoạch, kể cả dòng 0
    assert dn.stock_request_id is None       # không dòng dương ⇒ KHÔNG đẻ chứng từ kho


def test_tao_co_dong_duong_thi_de_yeu_cau_kho_approved(db, orders, lsx_svc, admin, customer):
    from app.models.stock_request import REQ_APPROVED, REQ_XUAT, StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT4")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    req = db.get(StockRequest, ra["stock_request_id"])
    assert req.loai == REQ_XUAT
    assert req.trang_thai == REQ_APPROVED
    assert req.bo_phan_id == cv.department_id     # tổ của CÔNG ĐOẠN, không phải phòng của user
    assert req.nguoi_tao_id == admin.id
    assert req.ngay_can == _T0.date()
    assert all(float(l.sl_de_nghi) > 0 for l in req.lines)


def test_khop_ke_hoach_thi_khong_doi_ly_do(db, orders, lsx_svc, admin, customer):
    """Xin đúng số kế hoạch (sau quy đổi) ⇒ không phải giải thích gì."""
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT8")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]

    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)  # không raise

    dn = db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"])
    assert all(d.ly_do_chenh_lech is None for d in dn.dongs)


def test_lech_ke_hoach_ma_thieu_ly_do_thi_chan(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT5")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"],
              "dvt": kh[0]["dvt"], "sl_yeu_cau": kh[0]["sl"] * 1.5}]
    with pytest.raises(VatTuDeNghiError) as e:
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    assert "lý do" in str(e.value).lower()


def test_khong_phai_to_truong_thi_chan(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT6")
    to.head_user_id = None          # không ai là tổ trưởng ⇒ kể cả admin cũng không ghi được
    db.commit()
    with pytest.raises(PermissionError):
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=[])


def test_dang_co_de_nghi_sua_duoc_thi_khong_tao_them(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT7")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    with pytest.raises(VatTuDeNghiError) as e:
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    assert "sửa" in str(e.value).lower()


# --- Ruling 10: quy đổi giấy "tờ" không có cạnh tĩnh sang gốc --------------------------------

def test_giu_nguyen_don_vi_ke_hoach_thi_quy_goc_theo_ti_le_cua_lenh(
    db, orders, lsx_svc, admin, customer,
):
    """Giấy khai bằng "tờ": cầu quy đổi tĩnh KHÔNG có cạnh tờ→tấn, nhưng bản đối chiếu vẫn phải
    có `sl_yeu_cau_goc` đúng — lấy theo tỉ lệ kế hoạch của chính lệnh này."""
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT9")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    k0 = kh[0]
    lines = [{"hang_loai": k0["hang_loai"], "hang_id": k0["hang_id"], "dvt": k0["dvt"],
              "sl_yeu_cau": k0["sl"] / 2, "ly_do_chenh_lech": "Chia hai lần cấp"}]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    dn = db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"])
    d0 = next(d for d in dn.dongs
              if (d.hang_loai, d.hang_id) == (k0["hang_loai"], k0["hang_id"]))
    # `sl_yeu_cau_goc` là cột Numeric(18, 3) — đọc lại sau `db.commit()` (expire_on_commit) nên
    # so KHÔNG được đòi khớp tuyệt đối, chỉ khớp trong nửa đơn vị làm tròn của chính cột đó
    # (0.0005), không thì mọi test đụng cột Numeric đều đỏ vì lượng tử hoá của DB, không phải bug.
    assert float(d0.sl_yeu_cau_goc) == pytest.approx(float(k0["sl_goc"]) / 2, abs=0.0005)
    assert d0.dvt_goc == k0["dvt_goc"]


def test_yeu_cau_kho_gui_bang_don_vi_thich_hop_khong_phai_to_cung_khong_phai_tan(
    db, orders, lsx_svc, admin, customer,
):
    """Ảnh chiếu sang kho KHÔNG còn gửi thẳng đơn vị GỐC (Ruling 11b, thay Ruling 11 cũ): giấy gốc
    là "tấn", mà `StockRequestLine.sl_de_nghi` là `Numeric(14, 2)` — vài trăm kg quy sang tấn bị
    ép về bước lượng tử 0.01 TẤN ≈ 33 tờ, lệch xa số tổ khai. `_don_vi_gui_kho` phải lùi xuống
    đơn vị THÔ NHẤT mà lượng vẫn ≥ 1 — với giấy là "kg", không phải "tờ" (không có cạnh quy đổi
    tĩnh) cũng không phải "tấn" (đơn vị gốc, quá thô cho cột 2 số lẻ)."""
    from app.models.stock_request import StockRequest
    from app.repositories.don_vi_do_repo import DonViDoRepository
    from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from app.services.san_xuat import vat_tu_de_nghi as V
    from app.services.vat_lieu_kho_service import VatLieuKhoService
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTB")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    req = db.get(StockRequest, ra["stock_request_id"])
    k0 = next(k for k in kh if k["hang_loai"] == "giay")
    ln = next(l for l in req.lines if (l.hang_loai, l.hang_id) == (k0["hang_loai"], k0["hang_id"]))
    assert ln.dvt == "kg" and ln.dvt != k0["dvt"] and ln.dvt != k0["dvt_goc"]

    # Hệ số kg→gốc là DỮ LIỆU DANH MỤC — lấy động, đừng gõ cứng 1000.
    hang = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    he_so_kg = next(
        d["he_so_ve_goc"] for d in hang.don_vi_cua_mat_hang(k0["hang_loai"], k0["hang_id"])["ds"]
        if d["ma"] == "kg"
    )
    # `StockRequestLine.sl_de_nghi` là cột Numeric(14, 2) — dung sai đúng bằng nửa bước lượng tử
    # của CỘT NÀY (0.005), không cần nới rộng hơn (đo thật trên ~335 kg).
    assert float(ln.sl_de_nghi) == pytest.approx(float(k0["sl_goc"]) / he_so_kg, abs=0.005)


def test_xin_luong_rat_nho_van_tao_duoc_yeu_cau_kho(db, orders, lsx_svc, admin, customer):
    """Trước fix (Ruling 11 cũ, gửi kho bằng đơn vị GỐC "tấn"): 10 tờ giấy ("Ivory 350") ≈ 0.00301
    tấn — Postgres ép `Numeric(14, 2)` về 0.00 và vỡ `CheckConstraint("sl_de_nghi > 0")` —
    `IntegrityError` thoát ra thành 500 (SQLite của test không ép scale nên không lộ). Sau fix,
    `_don_vi_gui_kho` lùi xuống "kg" (≈ 3 kg, thừa xa nửa bước lượng tử) nên vẫn ra số dương ghi
    được và thật sự đẻ được yêu cầu kho (khác lượng nhỏ hơn NỮA — dưới `_EPS` — bị `_lines_kho`
    coi là "không đáng gửi" và bỏ qua ngay từ đầu, không phải lỗi Numeric)."""
    from app.models.stock_request import StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTE")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    k0 = next(k for k in kh if k["hang_loai"] == "giay")
    lines = [{"hang_loai": k0["hang_loai"], "hang_id": k0["hang_id"], "dvt": k0["dvt"],
              "sl_yeu_cau": 10, "ly_do_chenh_lech": "Xin thử một lượng rất ít"}]

    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)  # không raise

    assert ra["stock_request_id"] is not None
    req = db.get(StockRequest, ra["stock_request_id"])
    ln = next(l for l in req.lines if (l.hang_loai, l.hang_id) == (k0["hang_loai"], k0["hang_id"]))
    assert ln.dvt == "kg"
    assert float(ln.sl_de_nghi) > 0.005


def test_don_vi_gui_kho_vat_tu_dem_duoc_giu_nguyen_don_vi_goc(db):
    """`_don_vi_gui_kho` chỉ nên đổi thang khi đơn vị gốc biến lượng thành số lẻ dưới 1 (ca giấy).
    Vật tư đếm bằng "cái" — mặt hàng vừa tạo, KHÔNG có cạnh quy đổi phụ nào coarser hơn chính nó —
    phải giữ NGUYÊN đơn vị gốc: 50 cái vẫn là "cái", không bị dò xuống đơn vị khác. Đây là chốt
    chặn để `_don_vi_gui_kho` không làm loạn các mặt hàng vốn đang gửi kho tốt trước giờ."""
    from app.models.vat_lieu_kho import VatTuInAn
    from app.repositories.don_vi_do_repo import DonViDoRepository
    from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from app.services.san_xuat.vat_tu_de_nghi import _don_vi_gui_kho
    from app.services.vat_lieu_kho_service import VatLieuKhoService

    vt = VatTuInAn(ma="VT-DEM-CAI", ten="Đinh ghim", don_vi_gia="cai")
    db.add(vt)
    db.commit()

    hang = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    dvt, sl = _don_vi_gui_kho(hang, "vat_tu", vt.id, 50.0)
    assert (dvt, sl) == ("cai", 50.0)


def test_doi_don_vi_khong_quy_duoc_thi_bao_loi_ro_chu_khong_ghi_0(
    db, orders, lsx_svc, admin, customer,
):
    """Tổ tự đổi sang đơn vị không có cầu quy đổi ⇒ BE không biết họ xin bao nhiêu. Phải nổ
    `VatTuDeNghiError` với câu người dùng đọc được, KHÔNG lặng lẽ ghi 0 vào yêu cầu kho."""
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTA")
    to.head_user_id = admin.id
    db.commit()
    k0 = _kh_service(db).nhu_cau_cua_cong_viec(cv)[0]
    lines = [{"hang_loai": k0["hang_loai"], "hang_id": k0["hang_id"],
              "dvt": "đơn-vị-không-có-thật", "sl_yeu_cau": 5, "ly_do_chenh_lech": "thử"}]
    with pytest.raises(V.VatTuDeNghiError):
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)


# --- Vòng sửa 1: Minor -------------------------------------------------------------------------

def test_so_am_thi_chan(db, orders, lsx_svc, admin, customer):
    """`sl_yeu_cau` âm không có nghĩa cho "xin cấp" — trước fix nó lọt qua `_chuan_hoa`, được lưu
    vào bản đối chiếu (bảng sản xuất ghi được "−50 tờ"), rồi mới bị `_lines_kho` âm thầm loại vì
    `sl_yeu_cau_goc <= _EPS`. Phải chặn NGAY ở `_chuan_hoa`, không để lọt vào bảng."""
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTC")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"],
              "dvt": kh[0]["dvt"], "sl_yeu_cau": -50, "ly_do_chenh_lech": "thử số âm"}]

    with pytest.raises(VatTuDeNghiError) as e:
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    assert "âm" in str(e.value).lower()

    # Không có gì được lưu — kể cả bảng đối chiếu SX (khác luật cũ: lọt vào bảng rồi mới bị
    # `_lines_kho` loại).
    assert V.SanXuatVatTuRepository(db).cac_de_nghi(cv.id) == []


def test_lan_dau_khong_dong_duong_van_bi_chan_tao_them_khong_kep_cung(
    db, orders, lsx_svc, admin, customer,
):
    """`co_voucher(None)` phải trả `False` TƯỜNG MINH: lần 1 xin 0 hết không đẻ yêu cầu kho
    (`stock_request_id=None`). Guard ở `tao()` vẫn phải đọc đúng nghĩa "đề nghị này CHƯA có phiếu,
    còn sửa được" và chặn tạo LẦN MỚI chồng lên (hướng người dùng đi sửa lần 1) — nếu `co_voucher`
    lỡ coi `None` là "có phiếu rồi" thì `tao()` sẽ vô tình cho tạo lần 2, và lần 1 (đã chiếm
    `lan_so=1`) sẽ không bao giờ sửa được nữa vì không ai còn trỏ tới nó — đó mới là khoá cứng
    thật."""
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTD")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"],
              "dvt": kh[0]["dvt"], "sl_yeu_cau": 0, "ly_do_chenh_lech": "Tổ còn tồn tại chỗ"}]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    dn = db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"])
    assert dn.stock_request_id is None
    # Hỏi ĐÚNG cửa mà `tao()` dùng (`StockRequestRepository`) — hỏi qua một facade khác thì test
    # vẫn xanh dù bản thật đổi hành vi.
    assert V.StockRequestRepository(db).co_voucher(dn.stock_request_id) is False

    with pytest.raises(VatTuDeNghiError) as e:
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    assert "sửa" in str(e.value).lower()


def test_dong_ngoai_ke_hoach_xin_0_thi_khong_luu(db, orders, lsx_svc, admin, customer):
    """Dòng NGOÀI kế hoạch (không nằm trong `nhu_cau_cua_cong_viec`) mà xin 0 là vô nghĩa — không
    được lưu vào bản đối chiếu. Khác dòng TRONG kế hoạch xin 0 (luôn phải lưu, để tổ còn thấy đủ
    danh mục kế hoạch kể cả phần không lấy)."""
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTG")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    ngoai_id = max(k["hang_id"] for k in kh) + 999_999   # chắc chắn KHÔNG có trong kế hoạch
    # Khai ĐÚNG số kế hoạch cho mọi mặt hàng TRONG kế hoạch (khỏi vướng luật "lệch phải có lý
    # do") — chỉ cố tình thêm MỘT dòng NGOÀI kế hoạch xin 0 để cô lập đúng nhánh đang test.
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    lines.append({"hang_loai": kh[0]["hang_loai"], "hang_id": ngoai_id,
                   "dvt": kh[0]["dvt"], "sl_yeu_cau": 0})

    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)  # không raise

    dn = db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"])
    assert len(dn.dongs) == len(kh)                       # không thêm dòng nào cho mặt hàng ngoài
    assert all(d.hang_id != ngoai_id for d in dn.dongs)


# --- Task 4: sửa — đồng bộ, huỷ về 0, khôi phục, khoá ------------------------------------------

def _tao_de_nghi(db, orders, lsx_svc, admin, customer, ma):
    """Dựng nhanh một lần đề nghị LẦN ĐẦU với đúng số kế hoạch (không lệch, khỏi vướng luật lý
    do) — trả `(de_nghi_id, stock_request_id, ma_yeu_cau_kho, kh)` cho các test sửa/huỷ dùng lại.
    """
    from app.models.stock_request import StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    req = db.get(StockRequest, ra["stock_request_id"])
    return ra["de_nghi_id"], ra["stock_request_id"], req.ma, kh


def _cv_id(db, de_nghi_id: int) -> int:
    return db.get(SanXuatVatTuDeNghi, de_nghi_id).cong_viec_id


def _lap_phieu_nhap_kho_cho(db, req_id: int):
    """Đẻ 1 `StockVoucher` NHÁP cho yêu cầu — mô phỏng "kho đã bắt tay soạn", chốt chặn `co_voucher`
    phải thấy để chặn sửa/huỷ từ phía sản xuất."""
    from datetime import date

    from app.models.stock_request import StockRequest
    from app.models.stock_voucher import VOUCHER_DRAFT, VOUCHER_XUAT, StockVoucher

    req = db.get(StockRequest, req_id)
    v = StockVoucher(
        ma=f"PXK-TEST-{req_id}", loai=VOUCHER_XUAT, request_id=req_id, kho_id=1,
        ngay=date(2026, 8, 31), nguoi_lap_id=req.nguoi_tao_id, trang_thai=VOUCHER_DRAFT,
    )
    db.add(v)
    db.commit()
    return v


def test_sua_truoc_khi_co_phieu_thi_de_len_chinh_yeu_cau_cu(db, orders, lsx_svc, admin, customer):
    """Giữ MÃ và ID — kho đã nhìn thấy số DNX… đó rồi, đổi mã là bắt họ đi tìm lại.

    Ruling task-4 mục C: dòng KHO không cùng thang với số TỔ KHAI (giấy "tờ" → kho gửi "kg") nên
    so bằng TỈ LỆ (gấp đôi số tổ khai ⇒ dòng kho cũng gấp đôi giá trị trước sửa), không so tuyệt
    đối với `kh[0]["sl"]`.
    """
    from app.models.stock_request import StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, ma_cu, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VT8")
    k0 = kh[0]
    truoc = db.get(StockRequest, req_id)
    l0_truoc = next(l for l in truoc.lines
                     if (l.hang_loai, l.hang_id) == (k0["hang_loai"], k0["hang_id"]))
    dvt_truoc, sl_truoc = l0_truoc.dvt, float(l0_truoc.sl_de_nghi)

    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
              "sl_yeu_cau": k["sl"] * 2, "ly_do_chenh_lech": "Chạy bù mẻ hỏng"} for k in kh]
    V.sua(db, user=admin, cong_viec_id=_cv_id(db, dn_id), de_nghi_id=dn_id,
          can_luc=_T0, lines=lines)

    req = db.get(StockRequest, req_id)
    assert req.ma == ma_cu and req.id == req_id
    l0_sau = next(l for l in req.lines
                   if (l.hang_loai, l.hang_id) == (k0["hang_loai"], k0["hang_id"]))
    assert l0_sau.dvt == dvt_truoc
    assert float(l0_sau.sl_de_nghi) == pytest.approx(sl_truoc * 2, rel=0.02)
    assert float(l0_sau.sl_duyet) == float(l0_sau.sl_de_nghi)


def test_sua_het_ve_0_thi_huy_yeu_cau_nhung_giu_ma(db, orders, lsx_svc, admin, customer):
    from app.models.stock_request import REQ_CANCELLED, StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, ma_cu, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VT9")
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
              "sl_yeu_cau": 0, "ly_do_chenh_lech": "Tổ đã có sẵn"} for k in kh]
    V.sua(db, user=admin, cong_viec_id=_cv_id(db, dn_id), de_nghi_id=dn_id,
          can_luc=_T0, lines=lines)

    req = db.get(StockRequest, req_id)
    assert req.trang_thai == REQ_CANCELLED
    assert req.ma == ma_cu
    assert req.lines == []
    assert "không cần cấp" in (req.ly_do_huy or "")
    # Bản ghi SẢN XUẤT vẫn còn nguyên và vẫn trỏ vào yêu cầu đó.
    assert db.get(SanXuatVatTuDeNghi, dn_id).stock_request_id == req_id


def test_nhap_lai_so_duong_thi_khoi_phuc_dung_yeu_cau_cu(db, orders, lsx_svc, admin, customer):
    from app.models.stock_request import REQ_APPROVED, StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, ma_cu, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTA")
    cv_id = _cv_id(db, dn_id)
    ve0 = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
            "sl_yeu_cau": 0, "ly_do_chenh_lech": "nhầm"} for k in kh]
    V.sua(db, user=admin, cong_viec_id=cv_id, de_nghi_id=dn_id, can_luc=_T0, lines=ve0)
    lai = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
            "sl_yeu_cau": k["sl"]} for k in kh]
    V.sua(db, user=admin, cong_viec_id=cv_id, de_nghi_id=dn_id, can_luc=_T0, lines=lai)

    req = db.get(StockRequest, req_id)
    assert req.trang_thai == REQ_APPROVED
    assert req.ma == ma_cu            # KHÔNG đẻ mã mới
    assert len(req.lines) == len(kh)


def test_co_phieu_roi_thi_sua_bi_chan_va_khong_doi_gi(db, orders, lsx_svc, admin, customer):
    from app.models.stock_request import StockRequest
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTB")
    _lap_phieu_nhap_kho_cho(db, req_id)      # helper: đẻ 1 StockVoucher NHÁP cho yêu cầu
    truoc = [(l.id, float(l.sl_de_nghi)) for l in db.get(StockRequest, req_id).lines]

    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
              "sl_yeu_cau": k["sl"] * 3, "ly_do_chenh_lech": "x"} for k in kh]
    with pytest.raises(VatTuDeNghiError) as e:
        V.sua(db, user=admin, cong_viec_id=_cv_id(db, dn_id), de_nghi_id=dn_id,
              can_luc=_T0, lines=lines)
    assert "phiếu" in str(e.value).lower()
    db.rollback()
    assert [(l.id, float(l.sl_de_nghi)) for l in db.get(StockRequest, req_id).lines] == truoc


def test_khoa_roi_thi_tao_duoc_lan_bo_sung(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTC")
    _lap_phieu_nhap_kho_cho(db, req_id)
    cv_id = _cv_id(db, dn_id)
    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"], "dvt": kh[0]["dvt"],
              "sl_yeu_cau": 10, "ly_do_chenh_lech": "Bù hao khi canh máy"}]
    ra = V.tao(db, user=admin, cong_viec_id=cv_id, can_luc=_T0, lines=lines)
    assert ra["lan_so"] == 2
    assert db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"]).loai == DN_BO_SUNG


# --- Ruling 14: `_lines_kho` không được lọc theo `sl_yeu_cau_goc` -----------------------------

def test_xin_1_to_khong_bi_am_tham_bo_dong(db, orders, lsx_svc, admin, customer):
    """Trước fix: `_lines_kho` lọc `sl_yeu_cau_goc > _EPS` — hai thang khác hẳn (0.0005 tấn ≈ 1.6
    tờ), nên tổ xin 1 tờ bị loại IM LẶNG. Nếu đó là dòng dương duy nhất thì không yêu cầu kho nào
    được đẻ ra mà tổ không hề biết (`tao()` trả về thành công, `stock_request_id=None`, không có
    dấu vết gì báo cho tổ biết yêu cầu của họ đã bị nuốt).

    Sau fix: duyệt theo `sl_yeu_cau` (đúng thang tổ gõ) — kết quả CHỈ có thể là một trong hai:
    yêu cầu kho có đúng dòng đó, hoặc `VatTuDeNghiError` nổ ra với câu đọc được. Test này chấp
    nhận CẢ HAI nhánh, miễn không phải "không có gì xảy ra".
    """
    from app.models.stock_request import StockRequest
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTF")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    k0 = next(k for k in kh if k["hang_loai"] == "giay")
    lines = [{"hang_loai": k0["hang_loai"], "hang_id": k0["hang_id"], "dvt": k0["dvt"],
              "sl_yeu_cau": 1, "ly_do_chenh_lech": "Xin thử đúng 1 tờ"}]

    try:
        ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    except VatTuDeNghiError as e:
        assert str(e)                    # có câu đọc được — không phải lỗi trắng
        return

    # Không nổ lỗi ⇒ BẮT BUỘC phải có yêu cầu kho mang đúng dòng này.
    assert ra["stock_request_id"] is not None
    req = db.get(StockRequest, ra["stock_request_id"])
    assert any((l.hang_loai, l.hang_id) == (k0["hang_loai"], k0["hang_id"]) for l in req.lines)


# --- Task 4 vòng sửa 1: chốt chặn DƯỚI KHOÁ ở tầng StockRequestService (ruling important-3) ------
# Cả 5 test Task 4 phía trên đi qua `sua()`, mà `sua()` bị chặn sớm hơn ở chốt NGOÀI
# (`vt_repo.co_voucher`, không khoá). Nhóm test dưới đây gọi THẲNG `StockRequestService`, dựng
# `StockVoucher` thật trỏ `request_id` để bật đúng cái khoá `lock_for_update`/`co_voucher` mà
# `dong_bo_tu_san_xuat`/`huy_tu_san_xuat`/`khoi_phuc_tu_san_xuat` tự kiểm bên trong.

def _req_svc(db):
    from app.services.san_xuat.vat_tu_de_nghi import _hang_service, _req_service

    return _req_service(db, _hang_service(db))


def _kho_lines_tu_req(db, req_id):
    """Dòng kho HỢP LỆ để gọi thẳng `dong_bo_tu_san_xuat`/`khoi_phuc_tu_san_xuat` trong test — phải
    theo đúng thang đơn vị KHO (vd "kg" cho giấy), không phải thang TỔ KHAI (vd "tờ") mà
    `VatLieuKhoService.quy_ve_goc` không quy tĩnh được (ruling 10: không có cạnh quy đổi tờ→gốc,
    xem `_ve_goc_dong`). Lấy lại từ CHÍNH dòng yêu cầu kho đã có sẵn (do `_tao_de_nghi` tạo qua
    `tao()`, vốn đã đi qua `_lines_kho`/`_don_vi_gui_kho`) — PHẢI gọi TRƯỚC khi yêu cầu bị
    `huy_tu_san_xuat` xoá sạch dòng.
    """
    from app.models.stock_request import StockRequest

    req = db.get(StockRequest, req_id)
    return [{"hang_loai": l.hang_loai, "hang_id": l.hang_id, "dvt": l.dvt,
             "sl_de_nghi": float(l.sl_de_nghi), "lsx_id": l.lsx_id, "bai_ghep_id": l.bai_ghep_id}
            for l in req.lines]


def test_dong_bo_tu_san_xuat_khi_da_co_phieu_thi_chan_va_khong_doi_gi(
    db, orders, lsx_svc, admin, customer,
):
    from app.models.stock_request import StockRequest
    from app.services.stock_request_service import StockRequestError

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS1")
    lines = _kho_lines_tu_req(db, req_id)
    _lap_phieu_nhap_kho_cho(db, req_id)
    truoc = [(l.id, float(l.sl_de_nghi)) for l in db.get(StockRequest, req_id).lines]

    with pytest.raises(StockRequestError) as e:
        _req_svc(db).dong_bo_tu_san_xuat(req_id, lines, user=admin, ngay_can=_T0.date())
    assert "phiếu" in str(e.value).lower()
    assert [(l.id, float(l.sl_de_nghi)) for l in db.get(StockRequest, req_id).lines] == truoc


def test_huy_tu_san_xuat_tren_yeu_cau_approved_thanh_cong(db, orders, lsx_svc, admin, customer):
    """`approved` KHÔNG nằm trong `REQUEST_EDITABLE` (draft/pending) — `huy_tu_san_xuat` phải chạy
    được trên yêu cầu do sản xuất tạo (luôn `approved` ngay từ `create()`), khác hẳn `cancel()`
    thường (chặn cứng ngoài draft/pending)."""
    from app.models.stock_request import REQ_APPROVED, REQ_CANCELLED, StockRequest

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS2")
    assert db.get(StockRequest, req_id).trang_thai == REQ_APPROVED

    ra = _req_svc(db).huy_tu_san_xuat(req_id, user=admin)
    assert ra.trang_thai == REQ_CANCELLED


def test_huy_tu_san_xuat_khi_da_co_phieu_thi_chan(db, orders, lsx_svc, admin, customer):
    from app.services.stock_request_service import StockRequestError

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS3")
    _lap_phieu_nhap_kho_cho(db, req_id)

    with pytest.raises(StockRequestError) as e:
        _req_svc(db).huy_tu_san_xuat(req_id, user=admin)
    assert "phiếu" in str(e.value).lower()


def test_huy_tu_san_xuat_goi_hai_lan_lien_tiep_lan_hai_khong_nem(
    db, orders, lsx_svc, admin, customer,
):
    """Important 1: hủy lần hai trên yêu cầu ĐÃ `cancelled` là lũy đẳng — không được ném lỗi, nếu
    không tổ sửa lần hai (vd chỉ sửa lý do) khi vẫn để 0 sẽ rơi vào ngõ cụt."""
    from app.models.stock_request import REQ_CANCELLED

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS4")
    svc = _req_svc(db)
    svc.huy_tu_san_xuat(req_id, user=admin)
    ra = svc.huy_tu_san_xuat(req_id, user=admin)          # lần hai — KHÔNG được ném
    assert ra.trang_thai == REQ_CANCELLED


def test_huy_tu_san_xuat_tren_yeu_cau_da_cap_xong_thi_van_chan(
    db, orders, lsx_svc, admin, customer,
):
    """Nửa còn lại của Important 1: lũy đẳng CHỈ áp cho `cancelled`. `done` vẫn phải ném — kho đã
    cấp hàng ra khỏi lô rồi, tổ không được rút yêu cầu về như chưa có gì.

    Đặt trạng thái thẳng tay: `done` thật chỉ tới sau khi có phiếu ĐÃ GHI SỔ, mà chốt `co_voucher`
    nằm SAU chốt này — nên dựng qua phiếu sẽ không chứng minh được chốt nào đã bắt. Thứ tự đó là cố
    ý: người dùng cần đọc "đã cấp xong", không phải "kho đã lập phiếu".
    """
    from app.models.stock_request import REQ_DONE, StockRequest
    from app.services.stock_request_service import StockRequestError

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS4B")
    req = db.get(StockRequest, req_id)
    req.trang_thai = REQ_DONE
    db.commit()

    with pytest.raises(StockRequestError) as e:
        _req_svc(db).huy_tu_san_xuat(req_id, user=admin)
    assert "cấp xong" in str(e.value).lower()
    assert db.get(StockRequest, req_id).trang_thai == REQ_DONE


def test_dong_bo_chan_yeu_cau_do_kho_huy_giu_nguyen_ly_do_roi_khoi_phuc_yeu_cau_do_sx_huy(
    db, orders, lsx_svc, admin, customer,
):
    """Important 2, hai nửa của cùng luật phân biệt AI hủy:
      · Kho hủy (`cancel_by_kho`) ⇒ `dong_bo_tu_san_xuat` phải CHẶN, và `ly_do_huy` của kho phải
        còn nguyên — sản xuất không được lật quyết định của kho, cũng không xoá mất lý do.
      · Sản xuất tự hủy (`huy_tu_san_xuat`) ⇒ `khoi_phuc_tu_san_xuat` phải cho khôi phục lại
        `approved`, và `ly_do_huy` (vốn do `huy_tu_san_xuat` ghi) phải về `None`.
    """
    from app.models.stock_request import REQ_APPROVED, StockRequest
    from app.services.stock_request_service import StockRequestError

    # Nửa 1: kho hủy.
    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS5")
    lines1 = _kho_lines_tu_req(db, req_id)
    svc = _req_svc(db)
    svc.cancel_by_kho(db.get(StockRequest, req_id), "Kho hết hàng, không cấp")

    with pytest.raises(StockRequestError):
        svc.dong_bo_tu_san_xuat(req_id, lines1, user=admin, ngay_can=_T0.date())
    assert db.get(StockRequest, req_id).ly_do_huy == "Kho hết hàng, không cấp"

    # Nửa 2: chính sản xuất hủy (công việc khác, để không lẫn state với nửa 1).
    dn_id2, req_id2, _ma2, kh2 = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS5B")
    lines2 = _kho_lines_tu_req(db, req_id2)     # lấy TRƯỚC khi huỷ xoá sạch dòng
    svc.huy_tu_san_xuat(req_id2, user=admin)
    ra = svc.khoi_phuc_tu_san_xuat(req_id2, lines2, user=admin, ngay_can=_T0.date())
    assert ra.trang_thai == REQ_APPROVED
    assert ra.ly_do_huy is None


def test_sua_qua_kho_huy_roi_nhap_so_duong_thi_chan_khong_ghi_nua_voi(
    db, orders, lsx_svc, admin, customer,
):
    """Ca đầu-cuối của Important 2 qua đúng cửa `sua()` (không gọi thẳng service): kho hủy → tổ
    sửa lại số dương → phải nhận lỗi (đây là `StockRequestError` không được `sua()` bọc lại thành
    `VatTuDeNghiError` — ruling task-4-fix-1 chấp nhận cả hai, miễn router dịch được), và KHÔNG
    bảng SX nào bị ghi nửa vời (rollback trọn transaction, dòng đối chiếu cũ còn nguyên)."""
    from app.models.stock_request import StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V
    from app.services.stock_request_service import StockRequestError

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTS6")
    _req_svc(db).cancel_by_kho(db.get(StockRequest, req_id), "Kho hết hàng, không cấp")
    dongs_truoc = [(d.hang_id, float(d.sl_yeu_cau))
                   for d in db.get(SanXuatVatTuDeNghi, dn_id).dongs]

    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
              "sl_yeu_cau": k["sl"] * 2, "ly_do_chenh_lech": "Chạy bù mẻ hỏng"} for k in kh]
    with pytest.raises(StockRequestError):
        V.sua(db, user=admin, cong_viec_id=_cv_id(db, dn_id), de_nghi_id=dn_id,
              can_luc=_T0, lines=lines)
    db.rollback()

    req_sau = db.get(StockRequest, req_id)
    assert req_sau.ly_do_huy == "Kho hết hàng, không cấp"
    dongs_sau = [(d.hang_id, float(d.sl_yeu_cau)) for d in db.get(SanXuatVatTuDeNghi, dn_id).dongs]
    assert dongs_sau == dongs_truoc


# --- Task 6: route chỉ gác `assign_work`, không đòi `kho:request` (ruling 6/21) ----------------
# `sua()` phải để `StockRequestError` xuyên thẳng ra ngoài (không bọc thành `VatTuDeNghiError`) —
# đã CHỐT ở đây rồi, KHÔNG cần thêm test: `test_sua_qua_kho_huy_roi_nhap_so_duong_thi_chan_khong_ghi_nua_voi`
# (ngay phía trên) gọi thẳng `V.sua()` và `pytest.raises(StockRequestError)` — router Task 6 chỉ
# việc thêm `except (VatTuDeNghiError, StockRequestError)` để dịch nó thành 400.


def test_khong_can_quyen_kho_de_tao_de_nghi(db, orders, lsx_svc, admin, customer):
    """`tao()`/`sua()` không hề hỏi RBAC — ranh giới an ninh DUY NHẤT là `_gate_to_truong` (đúng
    `department.head_user_id`). Mọi test khác trong file này gọi `V.tao(..., user=admin)`, mà
    `admin` (Giám đốc) lại CÓ `kho.can_request=True` qua `_full()` (`app/seed.py`) — nên tự chúng
    không chứng minh được "route Task 6 không cần bit kho:request". Test này dựng một tổ trưởng
    THẬT SỰ trắng RBAC (`role_id=None`, không một bit quyền nào — không riêng gì kho) và xác nhận
    `tao()` vẫn tạo được đề nghị + yêu cầu kho bình thường."""
    from app.models.user import User
    from app.services.san_xuat import vat_tu_de_nghi as V

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VTKHO")
    to_truong = User(username="to_truong_khong_quyen_kho", name="Tổ trưởng không quyền kho",
                      password_hash="x")
    db.add(to_truong)
    db.flush()
    to.head_user_id = to_truong.id
    db.commit()

    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    ra = V.tao(db, user=to_truong, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    assert ra["de_nghi_id"] and ra["stock_request_id"]


# --- Task 7: khối đối chiếu `vat_tu_cap` trong drawer + đổi nguồn phiếu theo công việc ---------
# task-7-brief.md + task-7-ruling-doi-chieu.md (BỐN đính chính: 24 dùng model_validate thay
# client_admin; 25 gộp `ma_yeu_cau`/`trang_thai_yeu_cau`/`ten_hang` thành 2 hàm GỘP gọi 1 lần;
# 26 `co_voucher` chỉ còn ở `StockRequestRepository`; 27 rút vị ngữ `moi_dong_deu_0` dùng chung).

def _authz(db):
    """`chi_tiet_cong_viec(db, user, authz, *, cong_viec_id)` — `authz` nhận `RoleRepository`,
    KHÔNG nhận `Session` (dựng đúng như `deps.get_authorization_service`, `backend/app/deps.py:190`)."""
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def _phieu_xuat_khop_yeu_cau(db, admin, req, *, ma):
    """Dựng 1 `StockVoucher` XUẤT đã `posted` với dòng khớp TOÀN BỘ dòng của `req` — mô phỏng kho
    đã thực xuất đúng số đề nghị. Trả về voucher."""
    from app.models.stock_voucher import (
        VOUCHER_POSTED, VOUCHER_XUAT, StockVoucher, StockVoucherLine,
    )

    v = StockVoucher(ma=ma, loai=VOUCHER_XUAT, request_id=req.id, kho_id=1,
                      ngay=_T0.date(), nguoi_lap_id=admin.id, trang_thai=VOUCHER_POSTED)
    db.add(v)
    db.flush()
    for ln in req.lines:
        db.add(StockVoucherLine(
            voucher_id=v.id, request_line_id=ln.id,
            hang_loai=ln.hang_loai, hang_id=ln.hang_id,
            so_luong=ln.sl_de_nghi, sl_goc=ln.sl_de_nghi,
        ))
    db.commit()
    return v


def test_doi_chieu_gom_ca_ba_con_so(db, orders, lsx_svc, admin, customer):
    """Kế hoạch / đã yêu cầu / kho thực xuất — mỗi mặt hàng một dòng."""
    from app.models.stock_request import StockRequest
    from app.services.san_xuat import board
    from app.services.san_xuat import vat_tu_de_nghi as V

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VC1")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    req = db.get(StockRequest, ra["stock_request_id"])
    _phieu_xuat_khop_yeu_cau(db, admin, req, ma="PXK-VC1")

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    d = ct["vat_tu_cap"]["doi_chieu"][0]
    assert set(d) >= {"hang_loai", "hang_id", "ten", "dvt",
                      "sl_ke_hoach", "sl_yeu_cau", "sl_thuc_xuat",
                      "lech_ke_hoach", "lech_thuc_te", "cac_ly_do"}
    assert d["lech_ke_hoach"] == pytest.approx(d["sl_yeu_cau"] - d["sl_ke_hoach"])
    assert d["lech_thuc_te"] == pytest.approx(d["sl_thuc_xuat"] - d["sl_yeu_cau"])
    assert any(row["sl_thuc_xuat"] > 0 for row in ct["vat_tu_cap"]["doi_chieu"])
    assert ct["vat_tu_cap"]["du_lieu_cu"] is False


def test_cong_doan_co_de_nghi_thi_khong_lay_phieu_theo_lsx(db, orders, lsx_svc, admin, customer):
    """Công đoạn đã nối link mới KHÔNG được trộn đường lùi — nếu không, tổ in thấy cả phiếu của
    tổ cán màng chỉ vì hai bên cùng một LSX."""
    from app.models.stock_request import (
        REQ_APPROVED, REQ_XUAT, StockRequest, StockRequestLine,
    )
    from app.models.stock_voucher import (
        VOUCHER_POSTED, VOUCHER_XUAT, StockVoucher, StockVoucherLine,
    )
    from app.services.san_xuat import board
    from app.services.san_xuat import vat_tu_de_nghi as V

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VC2")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    req_cua_de_nghi = db.get(StockRequest, ra["stock_request_id"])
    v_de_nghi = _phieu_xuat_khop_yeu_cau(db, admin, req_cua_de_nghi, ma="PXK-VC2-A")

    # Phiếu KHÁC — theo đường lùi lsx_id, mô phỏng dữ liệu "tổ khác cùng LSX" trước 31/08/2026.
    req_theo_lsx = StockRequest(ma="YC-VC2-LSX", loai=REQ_XUAT, nguoi_tao_id=admin.id,
                                trang_thai=REQ_APPROVED, bo_phan_id=to.id, ngay_can=_T0.date())
    db.add(req_theo_lsx)
    db.flush()
    db.add(StockRequestLine(request_id=req_theo_lsx.id, hang_loai=kh[0]["hang_loai"],
                            hang_id=kh[0]["hang_id"], lsx_id=cv.lsx_id, dvt=kh[0]["dvt"],
                            sl_de_nghi=5))
    db.commit()
    ln0 = req_theo_lsx.lines[0]
    v_lsx = StockVoucher(ma="PXK-VC2-B", loai=VOUCHER_XUAT, request_id=req_theo_lsx.id, kho_id=1,
                         ngay=_T0.date(), nguoi_lap_id=admin.id, trang_thai=VOUCHER_POSTED)
    db.add(v_lsx)
    db.flush()
    db.add(StockVoucherLine(voucher_id=v_lsx.id, request_line_id=ln0.id,
                            hang_loai=ln0.hang_loai, hang_id=ln0.hang_id, so_luong=5, sl_goc=5))
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert {v["voucher_id"] for v in ct["vat_tu"]} == {v_de_nghi.id}
    assert ct["vat_tu_cap"]["du_lieu_cu"] is False


def test_cong_doan_chua_tung_co_de_nghi_thi_lui_ve_lsx_va_danh_dau(
    db, orders, lsx_svc, admin, customer,
):
    from app.models.stock_request import (
        REQ_APPROVED, REQ_XUAT, StockRequest, StockRequestLine,
    )
    from app.models.stock_voucher import (
        VOUCHER_POSTED, VOUCHER_XUAT, StockVoucher, StockVoucherLine,
    )
    from app.services.san_xuat import board

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VC3")
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)

    req = StockRequest(ma="YC-VC3", loai=REQ_XUAT, nguoi_tao_id=admin.id,
                       trang_thai=REQ_APPROVED, bo_phan_id=to.id, ngay_can=_T0.date())
    db.add(req)
    db.flush()
    db.add(StockRequestLine(request_id=req.id, hang_loai=kh[0]["hang_loai"],
                            hang_id=kh[0]["hang_id"], lsx_id=cv.lsx_id, dvt=kh[0]["dvt"],
                            sl_de_nghi=5))
    db.commit()
    ln0 = req.lines[0]
    v = StockVoucher(ma="PXK-VC3", loai=VOUCHER_XUAT, request_id=req.id, kho_id=1,
                     ngay=_T0.date(), nguoi_lap_id=admin.id, trang_thai=VOUCHER_POSTED)
    db.add(v)
    db.flush()
    db.add(StockVoucherLine(voucher_id=v.id, request_line_id=ln0.id,
                            hang_loai=ln0.hang_loai, hang_id=ln0.hang_id, so_luong=5, sl_goc=5))
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["vat_tu_cap"]["du_lieu_cu"] is True
    assert {vv["voucher_id"] for vv in ct["vat_tu"]} == {v.id}


def test_vat_tu_cap_khong_bi_schema_nuot(db, orders, lsx_svc, admin, customer):
    """`WorkItemChiTietOut` CÓ response_model ⇒ field chưa khai bị bỏ IM LẶNG (service trả đủ, FE
    nhận undefined, không lỗi ở đâu). Ép qua schema thật mới bắt được (ruling 24 — `db`/`client`
    loại trừ nhau trên cùng engine SQLite in-memory, không dựng `client_admin` như brief gốc)."""
    from app.schemas.san_xuat import WorkItemChiTietOut
    from app.services.san_xuat import board
    from app.services.san_xuat import vat_tu_de_nghi as V

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VC4")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    ra = WorkItemChiTietOut.model_validate(ct)
    assert ra.vat_tu_cap.doi_chieu, "khối đối chiếu phải sống sót qua schema"
    assert ra.vat_tu_cap.du_lieu_cu is False


def test_kho_huy_thi_khong_mo_o_sua_nhung_van_them_bo_sung_duoc(
    db, orders, lsx_svc, admin, customer,
):
    """Ruling 27: kho hủy yêu cầu (`cancel_by_kho`) ⇒ `sua()` sẽ ném lỗi nếu FE mời tổ bấm sửa —
    drawer phải khoá `de_nghi_co_the_sua_id`, nhưng vẫn phải chừa đường bổ sung."""
    from app.models.stock_request import StockRequest
    from app.services.san_xuat import board

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VC5")
    cv_id = _cv_id(db, dn_id)
    _req_svc(db).cancel_by_kho(db.get(StockRequest, req_id), "Kho hết hàng, không cấp")

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv_id)
    vt = ct["vat_tu_cap"]
    assert vt["de_nghi_co_the_sua_id"] is None
    assert vt["co_the_tao_bo_sung"] is True


# --- Ruling task-7 47: `cac_de_nghi[].dongs` — dòng CỦA RIÊNG lần đó, không phải số cộng dồn ----
# Phát hiện lúc rà thiết kế: `doi_chieu[].sl_yeu_cau` cộng dồn qua MỌI lần, còn form "Sửa đề nghị"
# (PUT .../material-requests/{de_nghi_id}) THAY THẾ toàn bộ dòng của ĐÚNG lần đó — điền số cộng
# dồn vào form sửa sẽ âm thầm thổi phồng lần đang sửa lên bằng tổng mọi lần.

def test_cac_de_nghi_dongs_la_rieng_lan_khong_phai_cong_don(
    db, orders, lsx_svc, admin, customer,
):
    """Hai lần đề nghị trên CÙNG một mặt hàng: lần 1 xin đúng kế hoạch (1112), lần 2 bổ sung xin
    thêm 30. `doi_chieu[0]["sl_yeu_cau"]` phải là tổng cộng dồn (1142), nhưng
    `cac_de_nghi[-1]["dongs"][0]["sl_yeu_cau"]` phải là số CỦA RIÊNG lần 2 (30), không phải 1142."""
    from app.services.san_xuat import board

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VC6")
    k0 = kh[0]
    _lap_phieu_nhap_kho_cho(db, req_id)          # mở khoá cho lần bổ sung
    cv_id = _cv_id(db, dn_id)
    lines2 = [{"hang_loai": k0["hang_loai"], "hang_id": k0["hang_id"], "dvt": k0["dvt"],
              "sl_yeu_cau": 30, "ly_do_chenh_lech": "Bổ sung thêm do bù hao"}]
    from app.services.san_xuat import vat_tu_de_nghi as V
    V.tao(db, user=admin, cong_viec_id=cv_id, can_luc=_T0, lines=lines2)

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv_id)
    vt = ct["vat_tu_cap"]
    d0 = vt["doi_chieu"][0]
    assert d0["hang_loai"] == k0["hang_loai"] and d0["hang_id"] == k0["hang_id"]
    assert d0["sl_yeu_cau"] == pytest.approx(k0["sl"] + 30)      # cộng dồn qua MỌI lần

    assert len(vt["cac_de_nghi"]) == 2
    lan_cuoi = vt["cac_de_nghi"][-1]
    assert lan_cuoi["lan_so"] == 2
    assert len(lan_cuoi["dongs"]) == 1
    dong_lan2 = lan_cuoi["dongs"][0]
    assert dong_lan2["hang_loai"] == k0["hang_loai"] and dong_lan2["hang_id"] == k0["hang_id"]
    assert dong_lan2["sl_yeu_cau"] == pytest.approx(30)          # RIÊNG lần 2 — không phải 1142
    assert dong_lan2["ly_do_chenh_lech"] == "Bổ sung thêm do bù hao"

    lan_dau = vt["cac_de_nghi"][0]
    assert lan_dau["dongs"][0]["sl_yeu_cau"] == pytest.approx(k0["sl"])   # RIÊNG lần 1
