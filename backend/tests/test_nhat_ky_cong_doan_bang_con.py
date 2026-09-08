"""Nhật ký danh mục phải thấy công thức nằm ở BẢNG CON của công đoạn.

Bốn ô công thức tiền nong (giờ chạy / giá theo máy / tiền công / định mức vật tư) không nằm trên
`cong_doan` mà ở ba bảng con. `anh_chup` đọc cột bằng `sa_inspect(...).columns` — chỉ thấy cột của
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
from app.models.cong_doan import CongDoan, CongDoanDauViec, CongDoanDauViecVatTu, CongDoanMay
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
    cd = CongDoan(ma="CD-NK", ten="In offset", nhom="print")
    db.add(cd)
    db.flush()
    cd.may_lam_duoc.append(CongDoanMay(may_id=2, cong_thuc_gio="sl_vao / 8000",
                                       cong_thuc_gia="sl_vao * 400", thu_tu=0))
    dv = CongDoanDauViec(cong_doan_id=cd.id, piece_rate_id=5,
                         nang_suat_nguoi_gio=3000, so_nguoi_tieu_chuan=2,
                         cong_thuc_khoan="sl_vao * so_luot_chay")
    db.add(dv)
    db.flush()
    dv.vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=9, thu_tu=0, cong_thuc_luong="sl_vao / 1000"))
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
    assert "Công thức tính giá" in dong[0] and "Máy #2" in dong[0]
    assert "sl_vao * 400" in dong[0] and "sl_vao * 520" in dong[0]


def test_cong_thuc_tien_cong_va_dinh_muc_vat_tu_deu_co_vet(db):
    cd = _cong_doan(db)
    truoc = nk.anh_chup(cd)

    cd.dau_viec_dinh_muc[0].cong_thuc_khoan = "sl_ra"
    cd.dau_viec_dinh_muc[0].vat_tus[0].cong_thuc_luong = "so_mau * 20"
    db.commit()
    dong = nk.mo_ta_thay_doi(truoc, nk.anh_chup(cd))

    assert len(dong) == 2, dong
    assert any("Công thức tính tiền công" in d and "sl_ra" in d for d in dong)
    assert any("vật tư #9" in d and "so_mau * 20" in d for d in dong)


def test_go_het_may_khong_bi_nuot_im_lang(db):
    cd = _cong_doan(db)
    truoc = nk.anh_chup(cd)

    cd.may_lam_duoc.clear()
    db.commit()
    dong = nk.mo_ta_thay_doi(truoc, nk.anh_chup(cd))

    assert len(dong) == 2, dong  # hai ô của cái máy vừa gỡ
    assert all("Máy #2" in d for d in dong)


def test_khong_doi_gi_thi_khong_de_ra_dong_ma(db):
    cd = _cong_doan(db)
    assert nk.mo_ta_thay_doi(nk.anh_chup(cd), nk.anh_chup(cd)) == []
