"""NGỪNG DÙNG một mục danh mục KHÔNG được làm sai chứng từ đã có.

Danh mục (đơn vị · bù hao · vật tư · giấy…) là dữ liệu GỐC, mọi module khác chỉ ăn theo. Trước
14/08/2026 các đường ĐỌC đều lọc `active` — nghĩa là ẩn một mục là lệnh sản xuất cũ tự đổi số,
và không ai được báo:

  * ẩn một ĐƠN VỊ  → `_don_vis()` / `_ma_don_vi()` mất khoá → `tien_khoan` không ra → tiền công
    thợ của lệnh lịch sử hiện RỖNG;
  * ẩn một BÙ HAO  → `tinh_nguoc_routing` (chạy MỖI LẦN đọc chi tiết lệnh) ra số khác → cả loạt
    lệnh cũ hiện nhãn "tính lại" dù chẳng ai đụng vào;
  * ẩn một VẬT TƯ  → `replace_routing` ném lỗi → lệnh cũ KHÔNG LƯU LẠI ĐƯỢC routing nữa, kể cả
    khi người ta chỉ sửa một thứ khác hẳn.

Luật (đã chốt cho lương 27/07, `payroll_service.py:501`): **đọc lịch sử không bao giờ lọc
`active`; gán mới thì luôn lọc.** File này là lưới chặn tái phát cho đúng câu đó.
"""
from __future__ import annotations

import pytest

from app.models.bu_hao import BuHao
from app.models.cong_doan import CongDoan
from app.models.don_vi_do import DonViDo
from app.models.lsx import LsxCongDoan
from app.models.vat_lieu_kho import VatTuInAn
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.lsx_repo import LsxRepository
from app.services.lsx_service import LsxService
from app.services.sequence_service import SequenceService
from tests.test_lsx_service import (  # noqa: F401  (fixture dùng lại qua tên)
    _don_da_chuyen_sx,
    _gan_dinh_muc,
    _ptg_2_san_pham,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _svc_moi(db) -> LsxService:
    """Service MỚI TINH cho lần đọc sau.

    `LsxService` cache danh mục theo instance (`_dv_cache`, `_ma_dv_cache`, `_bu_hao_cache`) —
    một request là một instance. Đọc lại bằng chính instance cũ thì cache che mất thay đổi và
    test xanh giả.
    """
    return LsxService(db, LsxRepository(db), AuditLogRepository(db),
                      SequenceService(DocumentSequenceRepository(db)))


def _lenh_co_khoan(db, orders, lsx_svc, admin, customer):
    """Một lệnh có bước khoán "Dán hộp" tính bằng CÁI, đơn giá 250 đ/cái."""
    ptg = _ptg_2_san_pham(db)
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)
    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    return lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]


def test_an_don_vi_khong_lam_tien_khoan_lenh_cu_ve_rong(db, orders, lsx_svc, admin, customer):
    """Ẩn đơn vị "cái" xong, tiền khoán của lệnh ĐÃ CÓ phải y nguyên.

    Đây là ca đau nhất: `piece_rates.unit` lưu TÊN đơn vị, `_ma_don_vi` là cầu TÊN→MÃ duy nhất.
    Lọc `active` ở cầu đó là đứt cầu, và số tiền không báo lỗi — nó chỉ lặng lẽ thành `None`.
    """
    lsx = _lenh_co_khoan(db, orders, lsx_svc, admin, customer)
    truoc = lsx_svc.detail_dict(lsx)
    buoc_truoc = next(b for b in truoc["cong_doans"] if b["ten"] == "Dán hộp")
    assert buoc_truoc["khoan_tien"], "chưa có tiền khoán thì test không kiểm được gì"

    dv = db.query(DonViDo).filter(DonViDo.ma == "cai").first()
    assert dv is not None, "seed phải có đơn vị `cai` thì ca này mới đúng bài"
    dv.active = False
    db.commit()

    sau = _svc_moi(db).detail_dict(db.get(type(lsx), lsx.id))
    buoc_sau = next(b for b in sau["cong_doans"] if b["ten"] == "Dán hộp")
    assert buoc_sau["khoan_tien"] == buoc_truoc["khoan_tien"]
    assert sau["khoan_tien_tong"] == truoc["khoan_tien_tong"]


def test_an_bu_hao_khong_lam_so_to_lenh_cu_doi(db, orders, lsx_svc, admin, customer):
    """Ẩn mã bù hao xong, số lượng vào/ra của lệnh cũ phải y nguyên.

    `tinh_nguoc_routing` chạy mỗi lần MỞ chi tiết lệnh. Lọc `active` ở đó thì lệnh cũ tự đổi số
    và màn hiện nhãn "tính lại" — báo động giả hàng loạt trên dữ liệu không ai đụng vào.

    Seed không có sẵn mã bù hao nào nên phải tự khai, và phải khai TRƯỚC khi bung lệnh thì số
    của lệnh mới thật sự ăn theo nó — không thì test xanh mà chẳng chứng minh gì.
    """
    ptg = _ptg_2_san_pham(db)
    bh = BuHao(ma="BH-TEST", ten="Bù hao thử",
               bac=[{"sl_tu": 0, "sl_den": None, "gia_tri": 200, "don_vi": "to"}])
    db.add(bh)
    db.commit()
    cd_dan = db.query(CongDoan).filter(CongDoan.ma == "CD-DAN-T").first()
    cd_dan.kieu_bu_hao = "tra_bang"
    cd_dan.bu_hao_id = bh.id
    _gan_dinh_muc(db, cong_doan=cd_dan, ten="Dán hộp thủ công", don_vi="cái", don_gia=250)

    d = _don_da_chuyen_sx(db, orders, admin, customer, ptg)
    lines = lsx_svc.preview(d.id)["lines"]
    lsx = lsx_svc.tao(order_id=d.id, order_line_ids=[lines[0]["order_line_id"]], actor=admin)[0]

    truoc = {b["ten"]: (b["so_luong_vao"], b["so_luong_ra"])
             for b in lsx_svc.detail_dict(lsx)["cong_doans"]}

    bh.active = False
    db.commit()

    sau = {b["ten"]: (b["so_luong_vao"], b["so_luong_ra"])
           for b in _svc_moi(db).detail_dict(db.get(type(lsx), lsx.id))["cong_doans"]}
    assert sau == truoc


def test_an_vat_tu_van_luu_lai_duoc_routing_cua_lenh_cu(db, orders, lsx_svc, admin, customer):
    """Vật tư đã nằm trên bước thì giữ lại được; gán THÊM vật tư đã ngừng thì vẫn chặn."""
    lsx = _lenh_co_khoan(db, orders, lsx_svc, admin, customer)
    vt = VatTuInAn(ma="VT-KEO-X", ten="Keo dán", don_vi_gia="kg", don_gia=50_000)
    db.add(vt)
    db.commit()

    buoc = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == lsx.id).order_by(
        LsxCongDoan.thu_tu).all()

    def _rows(vat_tu_ids_cua_buoc_dau: list[int]):
        from app.schemas.lsx import LsxCongDoanIn
        ra = []
        for i, cd in enumerate(buoc):
            ra.append(LsxCongDoanIn(
                step_key=cd.step_key, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
                loai_buoc=cd.loai_buoc, thu_tu=cd.thu_tu,
                vat_tus=([{"vat_tu_id": v, "so_luong": 1} for v in vat_tu_ids_cua_buoc_dau]
                         if i == 0 else []),
            ))
        return ra

    lsx_svc.replace_routing(lsx_id=lsx.id, rows_in=_rows([vt.id]), actor=admin)
    db.commit()

    vt.active = False                       # kho ngừng dùng vật tư SAU khi lệnh đã khai nó
    db.commit()

    # Lưu lại nguyên trạng: KHÔNG được chặn — nếu chặn thì lệnh này bị nhốt vĩnh viễn.
    _svc_moi(db).replace_routing(lsx_id=lsx.id, rows_in=_rows([vt.id]), actor=admin)
    db.commit()
    con = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == lsx.id).order_by(
        LsxCongDoan.thu_tu).first()
    assert [v.vat_tu_id for v in con.vat_tus] == [vt.id]

    # Nhưng GÁN THÊM một vật tư đã ngừng thì vẫn phải chặn.
    from app.services.lsx_service import LsxValidationError
    khac = VatTuInAn(ma="VT-TAT-X", ten="Mực cũ", don_vi_gia="kg", don_gia=1, active=False)
    db.add(khac)
    db.commit()
    with pytest.raises(LsxValidationError, match="đã ngừng dùng"):
        _svc_moi(db).replace_routing(lsx_id=lsx.id, rows_in=_rows([vt.id, khac.id]), actor=admin)


def test_ma_don_vi_van_tra_ra_ma_khi_don_vi_da_ngung(db):
    """Cầu TÊN→MÃ phải sống kể cả khi đơn vị đã ngừng — nó là đường DUY NHẤT để `piece_rates`
    (lưu TÊN) tra ra mã danh mục."""
    dv = db.query(DonViDo).filter(DonViDo.ma == "cai").first()
    dv.active = False
    db.commit()
    assert _svc_moi(db)._ma_don_vi(dv.ten) == "cai"
