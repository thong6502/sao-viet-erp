"""Nhật ký danh mục phải thấy công thức nằm ở BẢNG CON của công đoạn.

Ba ô công thức (giờ chạy / giá theo máy / định mức vật tư) không nằm trên `cong_doan` mà ở hai
bảng con (`cong_doan_may`, `cong_doan_vat_tu` — mg `0316`; tầng đầu việc gỡ 18/09/2026). `anh_chup` đọc cột bằng `sa_inspect(...).columns` — chỉ thấy cột của
CHÍNH bảng — nên trước 07/09/2026 sửa công thức giá của một máy đổi thẳng vào tiền báo giá mà
Nhật ký không có lấy một dòng. Test này đỏ nếu ai gỡ phần gom bảng con.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — đăng ký metadata
from app.db import Base
from app.models.cong_doan import CongDoan, CongDoanMay, CongDoanVatTu
from app.models.may_thiet_bi import MayThietBi
from app.models.vat_lieu_kho import VatTuInAn
from app.repositories.audit_repo import AuditLogRepository
from app.services import nhat_ky_danh_muc as nk


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _cong_doan(db) -> CongDoan:
    db.add_all([
        MayThietBi(id=2, ma="IN-02", ten="Heidelberg SM102", loai_may="Máy in"),
        VatTuInAn(id=9, ma="VT-MUC", ten="Mực đen", don_vi_gia="kg", don_gia=1),
        VatTuInAn(id=11, ma="VT-KEO", ten="Keo dán", don_vi_gia="kg", don_gia=1),
    ])
    cd = CongDoan(ma="CD-NK", ten="In offset", nhom="print")
    db.add(cd)
    db.flush()
    cd.may_lam_duoc.append(CongDoanMay(may_id=2, cong_thuc_gio="sl_vao / 8000",
                                       cong_thuc_gia="sl_vao * 400", thu_tu=0))
    cd.vat_tus.append(CongDoanVatTu(vat_tu_id=9, thu_tu=0, cong_thuc_luong="sl_vao / 1000"))
    cd.vat_tus.append(CongDoanVatTu(vat_tu_id=11, thu_tu=1, cong_thuc_luong="so_mau * 2"))
    db.commit()
    db.refresh(cd)
    return cd


def test_doi_cong_thuc_gia_cua_mot_may_de_lai_dung_mot_dong(db):
    cd = _cong_doan(db)
    truoc = nk.anh_chup(cd)

    cd.may_lam_duoc[0].cong_thuc_gia = "sl_vao * 520"
    db.commit()
    dong = nk.mo_ta_thay_doi(truoc, nk.anh_chup(cd))

    assert len(dong) == 1, dong
    assert "Công thức tính giá" in dong[0] and "Heidelberg SM102 (IN-02)" in dong[0]
    assert "sl_vao * 400" in dong[0] and "sl_vao * 520" in dong[0]


def test_dinh_muc_tung_vat_tu_deu_co_vet(db):
    """Tab Vật tư: nhiều món, mỗi món một công thức — sửa món nào thì đúng một dòng món đó."""
    cd = _cong_doan(db)
    truoc = nk.anh_chup(cd)

    cd.vat_tus[0].cong_thuc_luong = "so_mau * 20"
    db.commit()
    dong = nk.mo_ta_thay_doi(truoc, nk.anh_chup(cd))

    assert len(dong) == 1, dong
    assert "Mực đen (VT-MUC)" in dong[0] and "so_mau * 20" in dong[0]


def test_bo_mot_vat_tu_khong_bi_nuot_im_lang(db):
    cd = _cong_doan(db)
    truoc = nk.anh_chup(cd)

    cd.vat_tus.pop()
    db.commit()
    dong = nk.mo_ta_thay_doi(truoc, nk.anh_chup(cd))

    assert len(dong) == 1 and "Keo dán (VT-KEO)" in dong[0], dong


def test_go_het_may_khong_bi_nuot_im_lang(db):
    cd = _cong_doan(db)
    truoc = nk.anh_chup(cd)

    cd.may_lam_duoc.clear()
    db.commit()
    dong = nk.mo_ta_thay_doi(truoc, nk.anh_chup(cd))

    assert len(dong) == 2, dong  # hai ô của cái máy vừa gỡ
    assert all("Heidelberg SM102 (IN-02)" in d for d in dong)


def test_khong_doi_gi_thi_khong_de_ra_dong_ma(db):
    cd = _cong_doan(db)
    assert nk.mo_ta_thay_doi(nk.anh_chup(cd), nk.anh_chup(cd)) == []


def test_may_da_xoa_khoi_danh_muc_van_goi_duoc_ten(db):
    cd = _cong_doan(db)
    cd.may_lam_duoc.append(CongDoanMay(may_id=77, cong_thuc_gia="sl_vao", thu_tu=1))
    db.commit()
    truoc = nk.anh_chup(cd)

    cd.may_lam_duoc[1].cong_thuc_gia = "sl_vao * 2"
    db.commit()
    dong = nk.mo_ta_thay_doi(truoc, nk.anh_chup(cd))

    assert len(dong) == 1 and "(máy #77 đã xoá)" in dong[0], dong


def test_moi_thay_doi_la_dung_mot_dong_tren_man(db):
    """Ảnh chụp 18/09/2026: khoá cũ "Máy #55 · Công thức tính giá" chứa đúng dấu " · " mà
    `NhatKyTab` dùng để cắt thay đổi ⇒ một thay đổi vẽ thành hai dòng cụt. Tên tự gõ có " · " cũng
    không được cắt đôi dòng."""
    cd = _cong_doan(db)
    db.get(MayThietBi, 2).ten = "Máy in · khổ lớn"
    db.commit()
    truoc = nk.anh_chup(cd)

    cd.may_lam_duoc[0].cong_thuc_gia = "sl_vao * 520"
    cd.vat_tus[0].cong_thuc_luong = "so_mau * 20"
    db.commit()
    audit = AuditLogRepository(db)
    nk.ghi_sua(audit, actor_id=None, loai="cong_doan", obj=cd, truoc=truoc)

    detail = audit.list_by_target(f"cong_doan:{cd.id}")[0].detail
    dong = detail.split(" · ")       # đúng cách `NhatKyTab` cắt
    assert len(dong) == 2, dong
    assert all(" → " in d for d in dong), dong
    assert "Máy in – khổ lớn (IN-02) › Công thức tính giá" in dong[0]
