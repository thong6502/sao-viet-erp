"""Nhật ký thao tác của bản ghi danh mục — ai đổi gì, lúc nào.

Kiểm ở tầng service (dựng DB in-memory như `test_vat_lieu_kho`) cho phần GHI, và một vòng
qua API cho phần ĐỌC + cổng quyền.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata mọi bảng
from app.models.don_vi_do import DonViDo
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.don_vi_do_repo import DonViDoRepository
from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from app.services import nhat_ky_danh_muc as nk
from app.services.vat_lieu_kho_service import VatLieuKhoService


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add(DonViDo(ma="kg", ten="kg", ho="khoi_luong"))
    db.commit()
    audit = AuditLogRepository(db)
    return db, audit, VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db), audit)


def _giay(svc, **kw):
    cl = svc.create("chung_loai_giay", dict(ma="COUCHE", ten="Couché"), actor_id=7)
    data = dict(ma="C100", ten="Couché 100 79×109", chung_loai_giay_id=cl.id,
                kho_dai=1090, kho_rong=790, gsm=100, don_vi_gia="kg", don_gia=27800)
    data.update(kw)
    return svc.create("giay", data, actor_id=7)


def test_sua_don_gia_ghi_ro_tu_bao_nhieu_sang_bao_nhieu():
    """Dòng đáng soi nhất của màn Giấy: đơn giá cũ → mới, kèm đơn vị theo ĐVT của chính bản ghi."""
    db, audit, svc = _svc()
    g = _giay(svc)
    svc.update("giay", g.id, dict(ma="C100", ten="Couché 100 79×109",
                                  chung_loai_giay_id=g.chung_loai_giay_id,
                                  kho_dai=1090, kho_rong=790, gsm=100,
                                  don_vi_gia="kg", don_gia=29000), actor_id=7)

    rows = audit.list_by_target(f"giay:{g.id}")
    assert [r.action for r in rows] == [nk.ACTION_SUA, nk.ACTION_TAO]   # mới nhất trước
    assert "Đơn giá 27.800 → 29.000 đ/kg" in rows[0].detail
    assert rows[0].actor_user_id == 7


def test_mot_lan_luu_nhieu_truong_van_la_mot_muc():
    """Sửa 2 trường = 1 dòng nhật ký (một lần bấm Lưu), không tách thành 2 mục."""
    db, audit, svc = _svc()
    g = _giay(svc)
    svc.update("giay", g.id, dict(ma="C100", ten="Couché 100 79×109",
                                  chung_loai_giay_id=g.chung_loai_giay_id,
                                  kho_dai=1090, kho_rong=790, gsm=120,
                                  don_vi_gia="kg", don_gia=29000), actor_id=7)

    sua = [r for r in audit.list_by_target(f"giay:{g.id}") if r.action == nk.ACTION_SUA]
    assert len(sua) == 1
    assert "Đơn giá 27.800 → 29.000 đ/kg" in sua[0].detail
    assert "27.800" in sua[0].detail and "29.000" in sua[0].detail


def test_bam_luu_ma_khong_doi_gi_thi_khong_de_ra_dong_rong():
    db, audit, svc = _svc()
    g = _giay(svc)
    nguyen_ven = dict(ma="C100", ten="Couché 100 79×109", chung_loai_giay_id=g.chung_loai_giay_id,
                      kho_dai=1090, kho_rong=790, gsm=100, don_vi_gia="kg", don_gia=27800)
    svc.update("giay", g.id, nguyen_ven, actor_id=7)

    assert [r.action for r in audit.list_by_target(f"giay:{g.id}")] == [nk.ACTION_TAO]


def test_xoa_ghi_vet_truoc_khi_ban_ghi_bien_mat():
    db, audit, svc = _svc()
    g = _giay(svc)
    svc.delete("giay", g.id, actor_id=9)

    rows = audit.list_by_target(f"giay:{g.id}")
    assert rows[0].action == nk.ACTION_XOA and rows[0].actor_user_id == 9


def test_bool_khong_lam_no_phep_so():
    """`active` là bool mà bool là con của int trong Python — so bằng Decimal sẽ nổ nếu không loại."""
    dong = nk.mo_ta_thay_doi({"active": True}, {"active": False})
    assert dong == ["Đang hoạt động Có → Không"]


def test_so_thap_phan_bang_nhau_khong_de_ra_thay_doi_ma():
    assert nk.mo_ta_thay_doi({"gsm": 100}, {"gsm": 100.00}) == []


def test_o_de_trong_hien_gach_ngang():
    assert nk.mo_ta_thay_doi({"ghi_chu": None}, {"ghi_chu": "khổ lẻ"}) == ["Ghi chú — → khổ lẻ"]


def test_trong_van_hoan_trong_thi_khong_bao_la_thay_doi():
    """Màn Máy luôn gửi kèm cột JSON `fields_theo_loai`, nên đổi mỗi Loại máy cũng khiến nó đi từ
    NULL sang {"chuan_bi_khoan": []}. Với người dùng thì vẫn là "chưa thiết lập" — đừng báo."""
    assert nk.mo_ta_thay_doi(
        {"fields_theo_loai": None}, {"fields_theo_loai": {"chuan_bi_khoan": []}},
    ) == []
    assert nk.mo_ta_thay_doi({"ghi_chu": None}, {"ghi_chu": ""}) == []
    assert nk.mo_ta_thay_doi({"nhom_may": []}, {"nhom_may": None}) == []


def test_json_co_noi_dung_that_thi_van_ghi():
    dong = nk.mo_ta_thay_doi(
        {"fields_theo_loai": None},
        {"fields_theo_loai": {"chuan_bi_khoan": [{"ten": "Canh kẽm", "phut": 15}]}},
    )
    assert len(dong) == 1 and "Thông số theo loại máy" in dong[0]


# ── Ô JSON `fields_theo_loai` của màn Máy ────────────────────────────────────
# Ảnh chụp màn hình 18/08/2026: sửa MỘT khoản chuẩn bị, nhật ký in nguyên cục JSON ra CẢ HAI vế —
# "Lich Bao Tri: Id: hm-seed-in-01-00; Viec: …; So: 1; Don Vi: tuan; Ngay Bat Dau: …" — dài hết bề
# ngang màn hình, hai bên mũi tên giống hệt nhau, và không chỉ ra được cái gì vừa đổi.
_LICH = [
    {"id": "hm-seed-in-01-00", "viec": "Bảo trì tuần máy in", "so": 1, "don_vi": "tuan",
     "ngay_bat_dau": "2026-08-09",
     "hang_muc": [{"id": "a-0", "ten": "Vệ sinh lô mực"}, {"id": "a-1", "ten": "Kiểm tra nhíp"},
                  {"id": "a-2", "ten": "Tra dầu"}, {"id": "a-3", "ten": "Xả nước làm ẩm"}]},
]
_KHOAN = [{"ten": "Thay giấy", "phut": 10}, {"ten": "Thay kẽm", "phut": 20}]


def test_sua_mot_khoa_con_khong_loi_ca_o_json_ra_in_lai():
    """⭐ Chủ chốt: thêm một khoản chuẩn bị thì lịch bảo trì KHÔNG được xuất hiện trong câu."""
    truoc = {"fields_theo_loai": {"lich_bao_tri": _LICH, "chuan_bi_khoan": _KHOAN}}
    sau = {"fields_theo_loai": {"lich_bao_tri": _LICH,
                                "chuan_bi_khoan": [*_KHOAN, {"ten": "Canh màu", "phut": 15}]}}
    dong = nk.mo_ta_thay_doi(truoc, sau)

    assert len(dong) == 1
    assert "Các khoản chuẩn bị" in dong[0] and "Canh màu (15 phút)" in dong[0]
    assert "Lịch bảo trì" not in dong[0], "khoá con KHÔNG đổi mà vẫn bị lôi ra in"


def test_dong_json_doc_duoc_khong_lo_ten_khoa_may():
    dong = nk.mo_ta_thay_doi({"fields_theo_loai": None},
                             {"fields_theo_loai": {"lich_bao_tri": _LICH}})

    assert dong == ["Thông số theo loại máy › Lịch bảo trì định kỳ — → "
                    "Bảo trì tuần máy in (mỗi 1 tuần, từ 09/08/2026, 4 việc)"]
    # Không rò khoá kỹ thuật, không rò tên khoá thô, ngày viết kiểu Việt.
    for rac in ("hm-seed", "Lich Bao Tri", "hang_muc", "ngay_bat_dau", "2026-08-09"):
        assert rac not in dong[0], rac


def test_khong_dung_dau_cham_giua_trong_mot_dong():
    """`NhatKyTab` cắt `detail` bằng " · " để tách trường. Lọt dấu đó vào GIỮA một giá trị là
    một thay đổi bị vẽ thành mấy dòng cụt nghĩa."""
    dong = nk.mo_ta_thay_doi({"fields_theo_loai": None},
                             {"fields_theo_loai": {"lich_bao_tri": _LICH, "chuan_bi_khoan": _KHOAN}})
    assert len(dong) == 2 and all(" · " not in d for d in dong)


def test_danh_sach_qua_dai_thi_cat_bot_chu_khong_dai_vo_han():
    goi = [{"ten": f"Khoản {i}", "phut": i} for i in range(1, 9)]
    dong = nk.mo_ta_thay_doi({"fields_theo_loai": None},
                             {"fields_theo_loai": {"chuan_bi_khoan": goi}})
    assert "Khoản 5 (5 phút)" in dong[0] and "Khoản 6" not in dong[0]
    assert "… và 3 mục nữa" in dong[0]
