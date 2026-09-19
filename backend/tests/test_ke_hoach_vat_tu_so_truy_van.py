"""Màn Kế hoạch vật tư: số truy vấn KHÔNG được chạy theo số bài ghép (rà 18/09/2026).

Cả hai cách nhìn của màn (`/can-doi` theo mặt hàng, `/theo-lenh` theo lệnh) đều dựng bảng cân đối
TOÀN XƯỞNG, và bảng đó chạy engine bài ghép (`tinh_so_to`) cho MỌI bài. Engine hỏi từng bài: bước
chung, bản đồ gộp, "lệnh này thuộc bài nào" (4–6 lần mỗi thành viên), bảng bù hao (mỗi thành viên
hai lần), vật tư của bước chung… Đo được 18/09/2026: mỗi bài thêm 15 câu, 1 → 5 bài là 62 → 122
câu. Nay nạp lô trước vòng lặp (`BaiGhepService.nap_truoc`). Khoá bằng SỐ ĐO, cùng lối
`test_ke_hoach_sx_so_truy_van.py`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import event

from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
from app.models.bai_ghep_cong_doan import (
    BaiGhepCongDoan, BaiGhepCongDoanMap, BaiGhepCongDoanVatTu,
)
from app.models.lsx import LsxCongDoanVatTu
from app.models.vat_lieu_kho import VatTuInAn
from app.models.xep_lich_lenh import XepLichLenh
from app.repositories.bai_ghep_repo import BaiGhepRepository
from app.routers.ke_hoach_vat_tu import get_service
from app.services.bai_ghep_service import BaiGhepService
from app.services.giu_cho_service import GiuChoService
from tests.test_ke_hoach_vat_tu import (  # noqa: F401
    MAI,
    _de_nghi_xuat,
    _giay,
    _lenh,
    _phieu_mua,
    _ton,
    _ycmh,
    customer,
    db,
)


def _dem(db, fn):
    so = {"n": 0}

    def _ghi(conn, cursor, statement, parameters, context, executemany):
        so["n"] += 1

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _ghi)
    try:
        kq = fn()
    finally:
        event.remove(bind, "before_cursor_execute", _ghi)
    return kq, so["n"]


def _ba_luot(db) -> dict[str, tuple[int, dict]]:
    """Ba lượt đọc của màn: `/can-doi`, `/theo-lenh`, và `/theo-lenh?chi_giu_lau`."""
    def can_doi():
        svc = get_service(db)
        bang = svc.can_doi()
        GiuChoService(db, svc).gan_giu_cho_vao_bang(bang)
        return bang

    luot = {
        "can_doi": can_doi,
        "theo_lenh": lambda: GiuChoService(db, get_service(db)).theo_chu_the(),
        "giu_lau": lambda: GiuChoService(db, get_service(db)).theo_chu_the(chi_giu_lau=True),
    }
    out = {}
    for ten, fn in luot.items():
        # Phiên ORM giữ sẵn đối tượng của lượt dựng dữ liệu ⇒ lazy-load im lặng, số đo đẹp giả.
        db.expire_all()
        kq, n = _dem(db, fn)
        out[ten] = (n, kq)
    return out


_SO = {"i": 0}


def _mot_lenh(db, customer):
    """Lệnh đủ mặt: giấy + mực ở bước, tồn, phiếu mua đang về, YCMH, đề nghị xuất, đã xếp lịch."""
    _SO["i"] += 1
    i = _SO["i"]
    g = _giay(db, ma=f"GY-{i}")
    l = _lenh(db, customer, ma=f"L{i}", giay_id=g.id, so_to_nguyen=1000, han=MAI)
    muc = VatTuInAn(ma=f"MUC-{i}", ten=f"Mực {i}", don_vi_gia="kg")
    db.add(muc)
    db.flush()
    db.add(LsxCongDoanVatTu(lsx_cong_doan_id=l.cong_doans[0].id, hang_loai="vat_tu",
                            vat_tu_id=muc.id, vat_tu_ma_snapshot=muc.ma,
                            vat_tu_ten_snapshot=muc.ten, don_vi_snapshot="kg", so_luong=2,
                            thu_tu=1, tu_dong=False))
    db.commit()
    _ton(db, g, 20)
    _phieu_mua(db, hang=("giay", g.id), so_luong=50, ngay_ve=MAI)
    _ycmh(db, hang=("giay", g.id), so_luong=10)
    _de_nghi_xuat(db, g, lsx_id=l.id, duyet=10, da_ung=5)
    db.add(XepLichLenh(lsx_id=l.id, bat_dau_at=datetime(2026, 9, 25, 8, tzinfo=timezone.utc)))
    db.commit()


def _mot_bai(db, customer):
    """Bài hai lệnh, có bước in CHUNG đè bước in của cả hai + một món mực của lượt chung.

    Phải có bước chung: không có thì nhánh chuỗi xuôi từ điểm toả (`tinh_xuoi_tu_to`) và vật tư
    bước chung không chạy, số đo phẳng giả.
    """
    _SO["i"] += 1
    i = _SO["i"]
    g = _giay(db, ma=f"GB-GY-{i}")
    a = _lenh(db, customer, ma=f"BA{i}", giay_id=g.id, so_to_nguyen=1000, han=MAI,
              giay_o_buoc=False)
    b = _lenh(db, customer, ma=f"BB{i}", giay_id=g.id, so_to_nguyen=1000, han=MAI,
              giay_o_buoc=False)
    bg = BaiGhep(ma=f"GB-{i}", giay_id=g.id, kho_in_dai=860, kho_in_rong=650)
    db.add(bg)
    db.flush()
    db.add_all([BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id, so_con_tren_to=1),
                BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=b.id, so_con_tren_to=1)])
    c = BaiGhepCongDoan(bai_ghep_id=bg.id, thu_tu=1, ten="In chung", loai_buoc="may",
                        don_vi_vao="to_nguyen", don_vi_ra="to", so_luong_vao=1000,
                        so_luong_ra=1000)
    db.add(c)
    db.flush()
    for l in (a, b):
        db.add(BaiGhepCongDoanMap(bai_ghep_cong_doan_id=c.id, lsx_id=l.id,
                                  lsx_step_key=l.cong_doans[0].step_key))
    muc = VatTuInAn(ma=f"MUC-GB-{i}", ten=f"Mực bài {i}", don_vi_gia="kg")
    db.add(muc)
    db.flush()
    db.add(BaiGhepCongDoanVatTu(bai_ghep_cong_doan_id=c.id, vat_tu_id=muc.id,
                                vat_tu_ma_snapshot=muc.ma, vat_tu_ten_snapshot=muc.ten,
                                don_vi_snapshot="kg", so_luong=3, thu_tu=1))
    db.commit()


def test_bang_can_doi_khong_chay_theo_so_bai_ghep(db, customer):
    """1 bài và 5 bài (kèm thêm lệnh lẻ) phải tốn CÙNG một số truy vấn cho cả ba lượt đọc."""
    for _ in range(2):
        _mot_lenh(db, customer)
    _mot_bai(db, customer)
    _ba_luot(db)                       # lượt nháp: danh mục/cấu hình lười ở lần đọc đầu
    nho = _ba_luot(db)

    for _ in range(6):
        _mot_lenh(db, customer)
    for _ in range(4):
        _mot_bai(db, customer)
    lon = _ba_luot(db)

    assert len(lon["can_doi"][1]["items"]) > len(nho["can_doi"][1]["items"]), "dữ liệu phải lớn thật"
    tang = {k: (nho[k][0], lon[k][0]) for k in nho if lon[k][0] - nho[k][0] > 1}
    assert not tang, f"số truy vấn nhảy theo số bài/lệnh (trước, sau): {tang} — N+1 đã quay lại"


def test_nap_lo_ra_dung_bang_nhu_hoi_tung_bai(db, customer, monkeypatch):
    """Đường nạp lô phải cho ra ĐÚNG bảng của đường hỏi từng bài — tối ưu không được đổi số."""
    for _ in range(3):
        _mot_lenh(db, customer)
    for _ in range(3):
        _mot_bai(db, customer)
    _ba_luot(db)
    moi = _ba_luot(db)

    # Tắt nạp lô ⇒ engine quay về hỏi DB từng bài như trước 18/09/2026.
    monkeypatch.setattr(BaiGhepService, "nap_truoc", lambda self, *a, **k: None)
    monkeypatch.setattr(BaiGhepRepository, "buoc_chung_theo_bai", lambda self, ids: {})
    cu = _ba_luot(db)

    for k in moi:
        assert json.dumps(moi[k][1], sort_keys=True, default=str) == \
            json.dumps(cu[k][1], sort_keys=True, default=str), f"{k}: nạp lô ra số khác"
        assert moi[k][0] < cu[k][0], f"{k}: nạp lô phải tốn ít câu hơn ({moi[k][0]} / {cu[k][0]})"
