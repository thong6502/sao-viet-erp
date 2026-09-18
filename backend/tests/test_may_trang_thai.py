"""Trạng thái máy LÚC NÀY (dẫn xuất từ vùng khoá + lệnh đang chạy). In-memory DB."""
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.models.machine_unavailable import (
    KIEU_CHAN,
    KIEU_MO_THEM,
    LY_DO_BAO_TRI,
    LY_DO_HONG_HOC,
    LY_DO_KHAC,
    MachineUnavailablePeriod,
)
from app.models.may_thiet_bi import MayThietBi
from app.services import may_trang_thai as mtt


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _may(db, *, ma="IN-01") -> MayThietBi:
    m = MayThietBi(ma=ma, ten=f"Máy {ma}", loai_may="Máy in")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _khoa(db, may_id: int, *, ly_do: str, kieu: str = KIEU_CHAN, gio_con_lai: float = 3,
          note: str | None = None) -> None:
    # Giờ TƯỜNG của xưởng: cột `unavailable_from/to` lưu wall-clock dán nhãn UTC, nên mốc dựng
    # trong test phải cùng gốc với `mtt._gio_xuong()` mà service đem ra so (sửa 22/08/2026).
    now = mtt._gio_xuong()
    db.add(MachineUnavailablePeriod(
        may_id=may_id, kieu=kieu, reason=ly_do, note=note,
        unavailable_from=now - timedelta(hours=1),
        unavailable_to=now + timedelta(hours=gio_con_lai),
    ))
    db.commit()


def _phieu_sua(db, may_id: int, *, ma: str, bo_phan: str = "Trục cán",
               muc_do: str = "trung_binh", trang_thai: str = "cho_sua") -> None:
    from app.models.ky_thuat_may import SuaChuaMay
    db.add(SuaChuaMay(ma=ma, may_id=may_id, bo_phan_hong=bo_phan,
                      muc_do=muc_do, trang_thai=trang_thai))
    db.commit()


def test_phieu_sua_dang_mo_chi_la_CANH_BAO_khong_phai_vung_khoa():
    """Chủ chốt 11/09/2026: "chỉ cảnh báo thôi". Phiếu sửa chữa là lời khai của tổ kỹ thuật, không
    chặn xếp lệnh — nhưng để nguyên chữ "Xếp được" cho máy đang tháo ra sửa là nói dối."""
    db = _db()
    may = _may(db)
    _phieu_sua(db, may.id, ma="SC-0001", bo_phan="Trục cán")

    tt = mtt.trang_thai_may(db, [may.id])[may.id]
    assert tt["trang_thai"] == mtt.TT_CO_PHIEU_SUA
    assert tt["nhan"] == "Có phiếu sửa chữa"
    assert tt["chi_tiet"] == "SC-0001 · Trục cán"
    assert tt["den"] is None                     # không có mốc "máy chạy lại" — nó không bị khoá


def test_phieu_sua_DA_DONG_thi_thoi_canh_bao():
    db = _db()
    may = _may(db)
    _phieu_sua(db, may.id, ma="SC-0001", trang_thai="da_sua_xong")
    assert mtt.trang_thai_may(db, [may.id]) == {}


def test_canh_bao_phieu_sua_KHONG_de_len_trang_thai_co_that():
    """Cảnh báo là nguồn YẾU NHẤT. Máy đang chạy / đã bị khoá là sự thật cụ thể hơn một tờ phiếu —
    đè lên là làm lệch đúng cái thứ tự ưu tiên mà chủ dặn đừng động vào."""
    db = _db()
    m1, m2 = _may(db, ma="IN-01"), _may(db, ma="IN-02")
    _phieu_sua(db, m1.id, ma="SC-0001")
    _phieu_sua(db, m2.id, ma="SC-0002")
    _khoa(db, m1.id, ly_do=LY_DO_HONG_HOC)       # m1 có CẢ vùng khoá lẫn phiếu

    kq = mtt.trang_thai_may(db, [m1.id, m2.id])
    assert kq[m1.id]["trang_thai"] == mtt.TT_MAY_DUNG        # vùng khoá thắng
    assert kq[m2.id]["trang_thai"] == mtt.TT_CO_PHIEU_SUA    # không có gì khác ⇒ mới cảnh báo


def test_nhieu_phieu_mo_thi_lay_cai_NANG_NHAT_va_dem_so_con_lai():
    db = _db()
    may = _may(db)
    _phieu_sua(db, may.id, ma="SC-0001", bo_phan="Lô ép", muc_do="nhe")
    _phieu_sua(db, may.id, ma="SC-0002", bo_phan="Hệ thuỷ lực", muc_do="nghiem_trong")
    _phieu_sua(db, may.id, ma="SC-0003", bo_phan="Bạc đạn", muc_do="trung_binh")

    tt = mtt.trang_thai_may(db, [may.id])[may.id]
    assert tt["chi_tiet"] == "SC-0002 · Hệ thuỷ lực · +2 phiếu"


def test_may_khong_co_chuyen_gi_thi_KHONG_co_trong_map():
    """Map chỉ chứa máy CÓ chuyện — bên gọi đã cầm danh sách máy, trả thêm một bản sao "không có
    gì" cho cả bảng là tốn công vô ích."""
    db = _db()
    may = _may(db)
    assert mtt.trang_thai_may(db, [may.id]) == {}


def test_vung_khoa_bao_tri_cho_ra_dang_bao_tri():
    db = _db()
    may = _may(db)
    _khoa(db, may.id, ly_do=LY_DO_BAO_TRI, note="BD 3 tháng")
    tt = mtt.trang_thai_may(db, [may.id])[may.id]
    assert tt["trang_thai"] == mtt.TT_BAO_TRI
    assert tt["chi_tiet"] == "BD 3 tháng"


def test_vung_khoa_hong_hoc_cho_ra_may_dung():
    db = _db()
    may = _may(db)
    _khoa(db, may.id, ly_do=LY_DO_HONG_HOC)
    assert mtt.trang_thai_may(db, [may.id])[may.id]["trang_thai"] == mtt.TT_MAY_DUNG


def test_khoa_ly_do_khac_khong_bi_goi_nham_la_bao_tri():
    db = _db()
    may = _may(db)
    _khoa(db, may.id, ly_do=LY_DO_KHAC)
    assert mtt.trang_thai_may(db, [may.id])[may.id]["trang_thai"] == mtt.TT_KHOA


def test_khoang_MO_THEM_khong_phai_may_nam():
    """⭐ `mo_them` là máy chạy THÊM ngoài ca (cùng bảng, khác dấu). Đọc nhầm nó thành vùng cấm
    là báo "máy đang bảo trì" đúng lúc máy đang chạy tăng ca."""
    db = _db()
    may = _may(db)
    _khoa(db, may.id, ly_do=LY_DO_BAO_TRI, kieu=KIEU_MO_THEM)
    assert mtt.trang_thai_may(db, [may.id]) == {}


def test_vung_khoa_DE_len_lenh_dang_chay(monkeypatch):
    """⭐ Bàn lịch vẫn giữ lệnh trên lane của máy vừa bị khoá (chưa ai dời đi đâu). Hiện "Đang
    chạy" cho cái máy đang tháo ra sửa là nói dối đúng lúc người ta cần tin nhất."""
    db = _db()
    may = _may(db)
    monkeypatch.setattr(mtt, "lenh_dang_chay", lambda *_a, **_k: {
        may.id: {"ma": "LSX26-0142", "finish_at": datetime.now() + timedelta(hours=1)},
    })

    tt = mtt.trang_thai_may(db, [may.id])[may.id]
    assert tt["trang_thai"] == mtt.TT_DANG_CHAY and "LSX26-0142" in tt["chi_tiet"]

    _khoa(db, may.id, ly_do=LY_DO_HONG_HOC)
    assert mtt.trang_thai_may(db, [may.id])[may.id]["trang_thai"] == mtt.TT_MAY_DUNG


def test_khoang_da_het_gio_thi_may_tro_lai_binh_thuong():
    db = _db()
    may = _may(db)
    # Giờ TƯỜNG của xưởng: cột `unavailable_from/to` lưu wall-clock dán nhãn UTC, nên mốc dựng
    # trong test phải cùng gốc với `mtt._gio_xuong()` mà service đem ra so (sửa 22/08/2026).
    now = mtt._gio_xuong()
    db.add(MachineUnavailablePeriod(
        may_id=may.id, kieu=KIEU_CHAN, reason=LY_DO_HONG_HOC,
        unavailable_from=now - timedelta(hours=5), unavailable_to=now - timedelta(hours=1),
    ))
    db.commit()
    assert mtt.trang_thai_may(db, [may.id]) == {}


def test_nhieu_khoang_chong_nhau_giu_cai_mo_khoa_MUON_nhat():
    """Gia hạn sửa chữa hay đẻ khoảng thứ hai chồng lên khoảng cũ. Lấy nhầm cái hết sớm là báo
    máy chạy lại lúc nó còn đang nằm."""
    db = _db()
    may = _may(db)
    _khoa(db, may.id, ly_do=LY_DO_HONG_HOC, gio_con_lai=1)
    _khoa(db, may.id, ly_do=LY_DO_HONG_HOC, gio_con_lai=6)
    den = mtt.trang_thai_may(db, [may.id])[may.id]["den"]
    assert den is not None
    # `den` là NAIVE nhưng mang GIỜ TƯỜNG của xưởng (quy ước đầu ra của Xếp lịch: FE
    # `new Date(iso)` không được dịch múi) — so bằng chính đồng hồ tường, không phải UTC.
    bay_gio = mtt._gio_xuong().replace(tzinfo=None)
    assert (den - bay_gio) > timedelta(hours=5)
