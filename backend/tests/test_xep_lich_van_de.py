"""Vấn đề kế hoạch (xung đột & nguy cơ trễ) — service-level tests.

Tái dùng fixtures + helpers của test xếp lịch (đơn → SX → lệnh → sẵn sàng → đưa vào kế hoạch → gán).
Kiểm 3 detector mới rẻ (đè khóa máy · sai tiền nhiệm · gang thiếu xả tờ), vòng đời state, luật ngoại
lệ (kỹ thuật bất khả không được duyệt), và gate PHÁT HÀNH (còn Chặn → chặn; ngoại lệ → thả; thu hồi).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.lsx import LB_TO, LB_XA_TO, Lsx, LsxCongDoan, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH
from app.models.may_thiet_bi import MayThietBi
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.xep_lich_repo import XepLichRepository
from app.services.xep_lich_service import XepLichConflict
from app.services.xep_lich_van_de_service import XepLichVanDeService

# Fixtures (db/admin/customer/orders/lsx_svc/bg_svc/xl_svc) + helpers dùng chung từ test xếp lịch.
from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    _in_step,
    admin,
    bg_svc,
    customer,
    db,
    lsx_svc,
    orders,
    xl_svc,
)


@pytest.fixture
def vd_svc(db):
    return XepLichVanDeService(db, AuditLogRepository(db))


def _luon_lam(monkeypatch):
    """Bỏ nhiễu ngày nghỉ cho MỌI CalendarService (cả instance trong vd_svc.xl)."""
    monkeypatch.setattr(
        "app.services.calendar_service.CalendarService.is_working_day", lambda self, d: True
    )


def _cats(res, cat):
    return [it for it in res["items"] if it["category"] == cat]


# --- Detector: đè vùng khóa máy ---------------------------------------------
def test_de_khoa_may_detector(db, orders, lsx_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao = 0, 5000, 5000
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1  # theo máy 30+60+15 = 105'
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id,
               "start_at": datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)}, actor=admin)  # 08:00→09:45
    # Khóa máy CHỒNG khối đã xếp — tạo SAU khi gán nên engine không né được.
    xl_svc.tao_vung_khoa(may_id=step.may_id,
                         tu=datetime(2026, 7, 27, 8, 30, tzinfo=timezone.utc),
                         den=datetime(2026, 7, 27, 8, 45, tzinfo=timezone.utc),
                         ly_do="bao_tri", note=None, actor=admin)
    des = _cats(vd_svc.liet_ke(), "de_khoa_may")
    assert len(des) == 1 and des[0]["severity"] == "chan"
    assert dong.id in des[0]["impacts"]["dong_ids"]


# --- Detector: sai thứ tự tiền nhiệm ----------------------------------------
def test_sai_tien_nhiem_detector(db, orders, lsx_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None  # In 60'
    # Bước sau (Dán, chiếm TỔ — không máy nên không lẫn trùng-máy).
    db.add(LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Dán tay", nhom="finishing", loai_buoc=LB_TO,
                       department_id=step.department_id, so_luong_vao=5000, chay_phut=30, don_vi_vao="cai"))
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dongs = XepLichRepository(db).by_lsx(lsx.id)
    in_dong = next(d for d in dongs if d.source_thu_tu == 0)
    dan_dong = next(d for d in dongs if d.loai_buoc == LB_TO)
    # In 28/7 09:00→10:00; Dán bị xếp 08:00 — TRƯỚC khi In xong.
    xl_svc.gan(dong_id=in_dong.id, patch={"may_id": step.may_id,
               "start_at": datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)}, actor=admin)
    xl_svc.gan(dong_id=dan_dong.id, patch={"department_id": step.department_id,
               "start_at": datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)}, actor=admin)
    sai = _cats(vd_svc.liet_ke(), "sai_tien_nhiem")
    assert any(dan_dong.id in it["impacts"]["dong_ids"] for it in sai)
    assert all(it["severity"] == "chan" for it in sai)


# --- Detector: gang thiếu bước xả tờ ----------------------------------------
def test_gang_thieu_xa_to_detector(db, orders, lsx_svc, bg_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # a: có bước finishing KHÁC (thiếu xả tờ) → phải bị bắt. b: có xả tờ → hợp lệ.
    db.add(LsxCongDoan(lsx_id=a.id, thu_tu=1, ten="Dán", nhom="finishing", loai_buoc=LB_TO,
                       department_id=_in_step(db, a.id).department_id, so_luong_vao=5000, chay_phut=20))
    db.add(LsxCongDoan(lsx_id=b.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_XA_TO,
                       may_id=_in_step(db, b.id).may_id, so_luong_vao=5000, nang_suat=6000,
                       don_vi_nang_suat="to_gio"))
    db.commit()
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    bg = bg_svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai="san_sang", actor=admin)
    xl_svc.dua_vao_bai_ghep(bai_ghep_id=bg.id, actor=admin)
    gang = _cats(vd_svc.liet_ke(), "gang_thieu_xa_to")
    assert len(gang) == 1 and gang[0]["severity"] == "chan"
    assert a.id in gang[0]["impacts"]["lsx_ids"] and b.id not in gang[0]["impacts"]["lsx_ids"]


# --- Gate phát hành: còn Chặn → chặn; ngoại lệ → thả; thu hồi ----------------
def test_phat_hanh_gate_ngoai_le_revert(db, orders, lsx_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for lsx in (a, b):
        s = _in_step(db, lsx.id)
        s.setup_phut, s.nang_suat, s.so_luong_vao, s.chay_phut = 0, 5000, 5000, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    xl_svc.dua_vao_lsx(lsx_id=b.id, actor=admin)
    repo = XepLichRepository(db)
    may_id = _in_step(db, a.id).may_id
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    xl_svc.gan(dong_id=repo.by_lsx(a.id)[0].id, patch={"may_id": may_id, "start_at": bat_dau}, actor=admin)
    xl_svc.gan(dong_id=repo.by_lsx(b.id)[0].id, patch={"may_id": may_id, "start_at": bat_dau}, actor=admin)

    # Trùng máy (Chặn) touching cả a lẫn b → a KHÔNG phát hành được.
    with pytest.raises(XepLichConflict):
        vd_svc.phat_hanh_lsx(lsx_id=a.id, actor=admin)
    tm = _cats(vd_svc.liet_ke(), "trung_may")[0]

    # Duyệt ngoại lệ → hết Chặn → phát hành được (Released).
    vd_svc.ngoai_le(issue_key=tm["issue_key"], ly_do="chấp nhận chạy nối ca", expires_at=None, actor=admin)
    lsx_a = vd_svc.phat_hanh_lsx(lsx_id=a.id, actor=admin)
    assert lsx_a.trang_thai == TT_DA_PHAT_HANH

    # Đã phát hành → không gỡ kế hoạch trực tiếp; thu hồi phát hành để về da_lap_ke_hoach.
    with pytest.raises(XepLichConflict):
        xl_svc.go_lsx(lsx_id=a.id, actor=admin)
    vd_svc.go_phat_hanh_lsx(lsx_id=a.id, actor=admin)
    assert db.get(Lsx, a.id).trang_thai == TT_DA_LAP_KE_HOACH


# --- Vòng đời state + ngoại lệ kỹ thuật bị chặn + tái phát -------------------
def test_state_lifecycle_technical_no_exception_reopen(db, orders, lsx_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]  # quy_cach kho_in 650×900, 4 màu
    nho = MayThietBi(ma="MAY-NHO-VD", ten="Máy con", loai_may="press_offset_sheet",
                     toc_do=3000, don_vi_toc_do="to_gio", kho_max_dai=520, kho_max_rong=360, so_units=2)
    db.add(nho)
    db.flush()
    step = _in_step(db, lsx.id)
    step.setup_phut, step.nang_suat, step.so_luong_vao, step.chay_phut = 0, 5000, 5000, None
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    xl_svc.gan(dong_id=dong.id, patch={"may_id": nho.id,
               "start_at": datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)}, actor=admin)

    mk = _cats(vd_svc.liet_ke(), "may_khong_kham")[0]
    assert mk["severity"] == "cao" and mk["trang_thai"] == "moi"

    # Vấn đề kỹ thuật (máy không kham) KHÔNG được duyệt ngoại lệ → 409.
    with pytest.raises(XepLichConflict):
        vd_svc.ngoai_le(issue_key=mk["issue_key"], ly_do="tạm chạy", expires_at=None, actor=admin)

    # Tiếp nhận → hiện trạng thái tiep_nhan.
    vd_svc.tiep_nhan(issue_key=mk["issue_key"], actor=admin)
    it2 = next(it for it in vd_svc.liet_ke()["items"] if it["issue_key"] == mk["issue_key"])
    assert it2["trang_thai"] == "tiep_nhan"

    # Đánh dấu đã xử lý nhưng máy vẫn nhỏ → vấn đề vẫn dẫn xuất → TÁI PHÁT (mo_lai).
    vd_svc.danh_dau_xu_ly(issue_key=mk["issue_key"], actor=admin)
    it3 = next(it for it in vd_svc.liet_ke()["items"] if it["issue_key"] == mk["issue_key"])
    assert it3["mo_lai"] is True
