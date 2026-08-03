"""Máy thiết bị — model + compute_bhr (§4.2/4.3) + validate (§8). Self-contained in-memory DB."""
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.models.may_thiet_bi import MayThietBi
from app.repositories.may_thiet_bi_repo import MayThietBiRepository
from app.schemas.may_thiet_bi import MayThietBiIn
from app.services.may_thiet_bi_service import (
    MayThietBiDuplicate,
    MayThietBiService,
    MayThietBiValidationError,
    compute_bhr,
    compute_bhr_preview,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, MayThietBiService(MayThietBiRepository(db))


def _off74(**over):
    """Máy offset 74 theo ví dụ §4.3."""
    base = dict(
        ma="OFF-74-4C", ten="Offset 74 4 màu", loai_may="press_offset_sheet",
        kho_max_dai=740, kho_max_rong=530, kho_min_dai=210, kho_min_rong=280,
        gripper_mm=12, so_units=4, khoa_class="74",
        von_dau_tu=4_000_000_000, gia_tri_thu_hoi=400_000_000, nam_khau_hao=8,
        gio_lam_nam=2000, availability_pct=90, productivity_pct=83, lai_von_pct=10,
        bao_hiem_nam=40_000_000, dien_tich_san_m2=40, don_gia_thue_m2_nam=1_200_000,
        luong_gio=60_000, luong_burden_pct=30, so_nhan_cong=2, so_may_song_song=1,
        bao_tri_gio=30_000, overhead_gio=50_000,
        cong_suat_kW=80, he_so_tai_dien=0.65, don_gia_dien=3000, markup_pct=15,
    )
    base.update(over)
    return base


def test_create_and_active_from_trang_thai():
    db, svc = _svc()
    m = svc.create(_off74())
    assert m.id and m.ma == "OFF-74-4C" and m.loai_may == "press_offset_sheet"
    assert m.active is True                       # trang_thai=active → active
    m2 = svc.update(m.id, _off74(trang_thai="retired"))
    assert m2.active is False


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


def test_bhr_matches_spec_example():
    db, svc = _svc()
    m = svc.create(_off74())
    r = compute_bhr(m)
    # §4.3: gio_tinh_phi ≈ 1494 (spec làm tròn 1500), BHR ≈ 897–899k.
    assert 1490 <= r["gio_tinh_phi"] <= 1500
    assert 880_000 <= r["BHR"] <= 915_000, r
    # điện là chi phí CHẠY = 80×0.65×3000 = 156.000
    assert r["breakdown"]["dien_gio"] == 156_000
    # lao động = 60k×1.3×2 = 156.000
    assert r["breakdown"]["lao_dong_gio"] == 156_000
    # don_gia_ban = BHR×1.15
    assert abs(r["don_gia_ban_gio"] - r["BHR"] * 1.15) < 1


def test_bhr_direct_source():
    db, svc = _svc()
    m = svc.create(_off74(nguon_bhr="nhap_truc_tiep", don_gia_gio_BHR=1_000_000, markup_pct=20))
    r = compute_bhr(m)
    assert r["BHR"] == 1_000_000 and r["don_gia_ban_gio"] == 1_200_000


def test_validate_kho_and_nhip():
    db, svc = _svc()
    with pytest.raises(MayThietBiValidationError):      # E-MAY-KHO
        svc.create(_off74(ma="X1", kho_min_dai=800, kho_max_dai=740))
    with pytest.raises(MayThietBiValidationError):      # E-MAY-NHIP: gripper ≥ kho_min_rong
        svc.create(_off74(ma="X2", gripper_mm=300, kho_min_rong=280))
    with pytest.raises(MayThietBiValidationError):      # nhóm máy để trống (loai_may free text nhưng bắt buộc)
        svc.create(_off74(ma="X3", loai_may="  "))


def test_bhr_preview_from_form_payload():
    # Payload form CHƯA lưu (string rỗng, field lạ) → vẫn ra đúng BHR §4.3 nhờ default preview.
    payload = {**_off74(), "ghi_chu": "", "field_la": 123, "fields_theo_loai": {"x": 1}}
    r = compute_bhr_preview(payload)
    assert 880_000 <= r["BHR"] <= 915_000
    # nhập trực tiếp: dùng thẳng đơn giá
    r2 = compute_bhr_preview({"nguon_bhr": "nhap_truc_tiep", "don_gia_gio_BHR": 900_000})
    assert r2["BHR"] == 900_000
    # thiếu đơn giá khi nhập trực tiếp → E-MAY-BHR0
    with pytest.raises(MayThietBiValidationError):
        compute_bhr_preview({"nguon_bhr": "nhap_truc_tiep"})


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
                            makeready_time_default=30, thoi_gian_rua_muc=0))

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
    may = svc.create(_off74(toc_do=6000, makeready_time_default=33, thoi_gian_rua_muc=0))

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
    from app.models.lsx import DV_BAI, DV_KEM, DV_TO, NS_BAI_GIO, NS_KEM_GIO, NS_TO_GIO
    from app.services.lsx_service import _DV_VAO_SANG_NS

    for dv_dem, ns in ((DV_TO, NS_TO_GIO), (DV_KEM, NS_KEM_GIO), (DV_BAI, NS_BAI_GIO)):
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
