"""Máy thiết bị — model + validate (§8) + danh mục Nhóm máy. Self-contained in-memory DB.

🔴 Test BHR (`compute_bhr` §4.2/4.3) ĐÃ GỠ 11/08/2026 cùng cả khối cột BHR: form Máy chưa bao giờ
có ô nhập cho chúng ⇒ công thức luôn chạy trên dữ liệu rỗng. Xem `models/may_thiet_bi.py`.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.repositories.may_thiet_bi_repo import MayThietBiRepository
from app.schemas.may_thiet_bi import MayThietBiIn
from app.services.may_thiet_bi_service import (
    MayThietBiDuplicate,
    MayThietBiService,
    MayThietBiValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, MayThietBiService(MayThietBiRepository(db))


def _off74(**over):
    """Máy offset 74 — chỉ còn field CÓ ô nhập trên form Máy."""
    base = dict(
        ma="OFF-74-4C", ten="Offset 74 4 màu", loai_may="press_offset_sheet",
        kho_max_dai=740, kho_max_rong=530, kho_min_dai=210, kho_min_rong=280,
        gripper_mm=12, so_nhan_cong=2,
    )
    base.update(over)
    return base


def test_create_va_sua_may():
    """`trang_thai` + property `active` đã GỠ 11/08/2026 — không có ô nhập nên mọi máy luôn
    "active", cờ đó chưa bao giờ phân loại được gì. Máy dừng thì khoá theo KHOẢNG THỜI GIAN ở
    `machine_unavailable_periods`, đó mới là thứ Xếp lịch đọc."""
    db, svc = _svc()
    m = svc.create(_off74())
    assert m.id and m.ma == "OFF-74-4C" and m.loai_may == "press_offset_sheet"
    m2 = svc.update(m.id, _off74(ten="Offset 74 đổi tên"))
    assert m2.ten == "Offset 74 đổi tên" and m2.id == m.id


def test_kip_van_hanh_tieu_chuan_la_du_lieu_khai_bao_cua_may():
    assert "so_nhan_cong" in MayThietBiIn.model_fields
    payload = MayThietBiIn(**_off74(so_nhan_cong=3))
    assert payload.so_nhan_cong == 3
    with pytest.raises(ValidationError):
        MayThietBiIn(**_off74(so_nhan_cong=0))


def test_duplicate_ma_rejected():
    db, svc = _svc()
    svc.create(_off74())
    with pytest.raises(MayThietBiDuplicate):
        svc.create(_off74(ten="Khác tên"))


def test_validate_kho_and_nhip():
    db, svc = _svc()
    with pytest.raises(MayThietBiValidationError):      # E-MAY-KHO
        svc.create(_off74(ma="X1", kho_min_dai=800, kho_max_dai=740))
    with pytest.raises(MayThietBiValidationError):      # E-MAY-NHIP: gripper ≥ kho_min_rong
        svc.create(_off74(ma="X2", gripper_mm=300, kho_min_rong=280))
    with pytest.raises(MayThietBiValidationError):      # nhóm máy để trống (loai_may free text nhưng bắt buộc)
        svc.create(_off74(ma="X3", loai_may="  "))


def test_fields_theo_loai_json_roundtrip():
    db, svc = _svc()
    m = svc.create(_off74(ma="DIG-1", loai_may="press_digital",
                          fields_theo_loai={"cong_nghe": "toner", "click_mau": 1200}))
    got = svc.get(m.id)
    assert got.fields_theo_loai["click_mau"] == 1200


def test_list_filter_by_loai_may():
    db, svc = _svc()
    svc.create(_off74())
    svc.create(_off74(ma="CTP-B1", ten="CTP", loai_may="prepress_ctp"))
    rows, total = svc.list(loai_may="prepress_ctp")
    assert total == 1 and rows[0].ma == "CTP-B1"


# --- Dải tốc độ: CHỈ ĐỂ KHAI, không nối tính toán ---------------------------
#
# Chủ chốt 03/08/2026: "cái tối đa với tối thiểu thì khai ra vậy thôi, sau họ dùng họ sẽ tự biết
# để lấy ra". `toc_do` (trung bình) vẫn là số DUY NHẤT chảy vào tính giá / lệnh SX / xếp lịch.


def test_chi_khai_toc_do_trung_binh_van_luu_duoc():
    """⭐ KHÔNG ép khai đủ ba. Bắt điền đủ chỉ tổ làm người ta gõ số bừa cho qua."""
    db, svc = _svc()
    m = svc.create(_off74(toc_do=9000, don_vi_toc_do="to_gio"))
    assert float(m.toc_do) == 9000
    assert m.toc_do_min is None and m.toc_do_max is None


def test_khai_du_dai_toc_do_hop_le():
    db, svc = _svc()
    m = svc.create(_off74(toc_do=9000, toc_do_min=6000, toc_do_max=12000))
    assert (float(m.toc_do_min), float(m.toc_do), float(m.toc_do_max)) == (6000, 9000, 12000)


@pytest.mark.parametrize(
    "over",
    [
        dict(toc_do=9000, toc_do_min=12000, toc_do_max=6000),   # min > max
        dict(toc_do=9000, toc_do_min=10000),                    # min > trung bình
        dict(toc_do=9000, toc_do_max=8000),                     # max < trung bình
        dict(toc_do=9000, toc_do_min=0),                        # <= 0
    ],
)
def test_dai_toc_do_vo_ly_bi_chan(over):
    db, svc = _svc()
    with pytest.raises(MayThietBiValidationError):
        svc.create(_off74(**over))


def test_dai_toc_do_KHONG_dung_de_tinh_gi_ca():
    """⭐ Canh cho quyết định của chủ: hai cột này là DỮ LIỆU KHAI, không phải đầu vào công thức.

    Lõi xếp lịch đơn trị (`_cong_gio_lam` cộng MỘT con số phút để ra giờ kết thúc). Nếu một ngày
    ai đó "tiện tay" cho nó đọc min/max, đây là thứ đỏ lên — và người đó phải quay lại đọc §3 của
    kế hoạch trước khi viết lại lõi xếp lịch."""
    from app.services.xep_lich_service import _thoi_luong_in_ghep

    db, svc = _svc()
    may = svc.create(_off74(toc_do=6000, toc_do_min=1000, toc_do_max=60000,
                            makeready_time_default=30))

    class _BG:  # bai ghep gia - ham chi doc may + tong to
        pass

    t = _thoi_luong_in_ghep(_BG(), 6000, may)
    # 6000 to / 6000 to/gio = 1 gio = 60 phut chay, + 30 phut makeready.
    assert t["chay_phut"] == 60.0, "phai tinh bang TRUNG BINH, khong phai min/max"
    assert t["chiem_may_phut"] == 90.0


# --- Thời gian chuẩn bị (canh máy) 3 kiểu ------------------------------------
#
# Chủ chốt 03/08/2026: "chuẩn bị" của MÁY (Xếp lịch đọc) và của CÔNG ĐOẠN (Lệnh SX đọc) để
# nguyên hai nơi hai việc — KHÔNG gộp, KHÔNG cộng. Ba kiểu chỉ khác nhau ở chỗ AI điền số tổng.
# `makeready_time_default` vẫn là NGUỒN CHÂN LÝ DUY NHẤT; chi tiết khoản cất trong fields_theo_loai.


def test_chuan_bi_kieu_dien_tong():
    db, svc = _svc()
    m = svc.create(_off74(makeready_time_default=30))
    assert float(m.makeready_time_default) == 30


def test_chuan_bi_kieu_theo_khoan_luu_ca_tong_lan_chi_tiet():
    """Tổng do FE cộng (15+18=33) rồi ghi vào cột — Xếp lịch chỉ đọc cột, không phải cộng lại."""
    db, svc = _svc()
    m = svc.create(_off74(
        makeready_time_default=33,
        fields_theo_loai={"chuan_bi_khoan": [
            {"ten": "Thay giấy", "phut": 15}, {"ten": "Thay mực", "phut": 18},
        ]},
    ))
    assert float(m.makeready_time_default) == 33
    assert [r["phut"] for r in m.fields_theo_loai["chuan_bi_khoan"]] == [15, 18]


def test_doi_kieu_ve_de_TRONG_thi_XOA_han_so_cu():
    """⭐ Chỗ dễ hỏng nhất. Backend gán TỪNG PHẦN (`if k in data`) và form chỉ gửi ô ĐANG HIỆN,
    nên chuyển sang "để trống" mà không gửi null thì số cũ nằm lại — rồi lần mở sau form đọc được
    nó và lật ngược kiểu về "điền tổng". FE phải gửi null + danh sách rỗng; đây là hợp đồng đó."""
    db, svc = _svc()
    m = svc.create(_off74(
        makeready_time_default=33,
        fields_theo_loai={"chuan_bi_khoan": [{"ten": "Thay giấy", "phut": 33}]},
    ))
    m2 = svc.update(m.id, _off74(makeready_time_default=None,
                                 fields_theo_loai={"chuan_bi_khoan": []}))
    assert m2.makeready_time_default is None
    assert m2.fields_theo_loai["chuan_bi_khoan"] == []


def test_chuan_bi_cua_MAY_khong_dinh_gi_toi_cong_doan():
    """⭐ Canh chốt "hai nơi hai việc": Xếp lịch cộng số của MÁY, không đụng `cong_doan.setup_time`."""
    from app.services.xep_lich_service import _thoi_luong_in_ghep

    db, svc = _svc()
    may = svc.create(_off74(toc_do=6000, makeready_time_default=33))

    class _BG:
        pass

    t = _thoi_luong_in_ghep(_BG(), 6000, may)
    assert t["setup_phut"] == 33.0, "Xep lich phai lay makeready cua MAY"
    assert t["chiem_may_phut"] == 93.0        # 33 canh may + 60 chay


# --- Đơn vị tốc độ suy ra từ danh mục Đơn vị --------------------------------


def test_don_vi_toc_do_dai_van_luu_duoc():
    """⭐ Bẫy CHỈ POSTGRES mới lộ. Mã đơn vị tốc độ là `<ma>_gio` suy từ `don_vi_do.ma` (rộng 24)
    ⇒ tới 28 ký tự, mà cột cũ chỉ VARCHAR(16). SQLite không ép độ dài nên test kiểu này KHÔNG bắt
    được lỗi — nó chỉ canh cho phần khai báo cột (migration 0153 nới lên 32)."""
    from app.models.may_thiet_bi import MayThietBi

    assert MayThietBi.__table__.c.don_vi_toc_do.type.length >= 28, \
        "cot hep hon ma co the sinh ra -> Postgres that se loi luc luu"

    db, svc = _svc()
    ma_dai = "khoi_luong_quy_doi_gio"          # 22 ky tu, kieu ma chu tu them
    m = svc.create(_off74(toc_do=500, don_vi_toc_do=ma_dai))
    assert m.don_vi_toc_do == ma_dai


def test_quy_uoc_ma_don_vi_toc_do_khop_bang_tra_cua_lenh_SX():
    """⭐ Mã PHẢI là `<đơn vị đếm>_gio` — Lệnh SX tra bảng theo đúng dạng đó.

    Đây là chốt cho quyết định "suy danh sách từ danh mục Đơn vị": nếu ai đó đổi quy ước đặt mã
    (vd `toc_do_1`), lệnh SX BỎ QUA tốc độ trong im lặng — bước ra thời gian trống, không báo lỗi,
    không ai biết. Test này bắt cái im lặng đó."""
    from app.models.lsx import DV_KEM, DV_TO, NS_KEM_GIO, NS_TO_GIO
    from app.services.lsx_service import _DV_VAO_SANG_NS

    for dv_dem, ns in ((DV_TO, NS_TO_GIO), (DV_KEM, NS_KEM_GIO)):
        assert ns == f"{dv_dem}_gio", f"{ns} khong theo quy uoc <{dv_dem}>_gio"
        assert _DV_VAO_SANG_NS[dv_dem] == ns


# --- Danh mục NHÓM MÁY -------------------------------------------------------
#
# Trước 03/08/2026 "nhóm máy" chỉ là chữ tự do trên từng máy + 5 tên khai cứng trong FE ⇒ không
# cách nào xoá. Nay là bảng thật (`nhom_may`), nhưng CỐ Ý không phải khoá ngoại: `loai_may` vẫn
# lưu chữ vì Lệnh SX / Phiếu tính giá / `isMayIn()` đang đọc chuỗi đó.


def _nhom_svc(db):
    from app.services.may_thiet_bi_service import NhomMayService
    return NhomMayService(db)


def test_them_nhom_may_va_chan_trung_ten():
    db, svc = _svc()
    n = _nhom_svc(db)
    n.create("Ép kim")
    assert [x.ten for x in n.list()] == ["Ép kim"]
    with pytest.raises(MayThietBiDuplicate):
        n.create("Ép kim")


def test_xoa_nhom_khong_ai_dung_thi_duoc():
    db, svc = _svc()
    n = _nhom_svc(db)
    row = n.create("Ép kim")
    n.delete(row.id)
    assert n.list() == []


def test_XOA_nhom_con_may_dung_bi_CHAN_kem_so_may():
    """⭐ Chốt quan trọng nhất. Bảng KHÔNG phải khoá ngoại nên DB không tự giữ — xoá mù là để lại
    máy mang tên nhóm không còn tồn tại, và không chỗ nào báo. Thông báo phải có SỐ MÁY để người
    ta biết còn phải đi sửa mấy cái."""
    db, svc = _svc()
    n = _nhom_svc(db)
    row = n.create("Offset tờ rời")
    svc.create(_off74(ma="M1", loai_may="Offset tờ rời"))
    svc.create(_off74(ma="M2", loai_may="Offset tờ rời"))

    with pytest.raises(MayThietBiValidationError) as e:
        n.delete(row.id)
    assert "2" in str(e.value), f"thieu so may trong thong bao: {e.value}"
    assert n.list(), "nhom bi xoa mat du da chan"


def test_tao_lai_ten_da_an_thi_BAT_LAI_chu_khong_bao_trung():
    """Người dùng gõ đúng cái tên đó nghĩa là họ muốn nó có mặt — báo "đã tồn tại" trong khi danh
    sách không thấy nó đâu là kiểu lỗi khiến người ta bó tay."""
    db, svc = _svc()
    n = _nhom_svc(db)
    row = n.create("Ép kim")
    row.active = False
    db.commit()
    assert n.list() == []

    lai = n.create("Ép kim")
    assert lai.id == row.id and lai.active is True


def test_dem_theo_loai_nuoi_tab_loc():
    """Số trên tab lọc màn Thiết bị do MÁY CHỦ đếm (màn chỉ cầm 20 dòng của trang đang xem).

    Không lọc theo `loai_may` — tab đang không được chọn vẫn phải có số. Và tổng các tab
    phải đúng bằng tổng danh mục, vì màn cộng chính các số này ra số cho tab "Tất cả"
    (`loai_may` là cột NOT NULL nên ở đây không có nhóm khuyết).
    """
    db, svc = _svc()
    svc.create(_off74(ma="OFF-1", loai_may="press_offset_sheet"))
    svc.create(_off74(ma="OFF-2", loai_may="press_offset_sheet"))
    svc.create(_off74(ma="BE-1", loai_may="die_cut"))

    assert svc.dem_theo_loai() == {"press_offset_sheet": 2, "die_cut": 1}
    assert sum(svc.dem_theo_loai().values()) == svc.list(size=1)[1]   # khớp tổng danh mục
    assert svc.dem_theo_loai(q="be-1") == {"die_cut": 1}              # đi theo ô tìm
