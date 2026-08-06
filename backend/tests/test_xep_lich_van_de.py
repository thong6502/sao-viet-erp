"""Vấn đề kế hoạch (xung đột & nguy cơ trễ) — service-level tests.

Tái dùng fixtures + helpers của test xếp lịch (đơn → SX → lệnh → sẵn sàng → đưa vào kế hoạch → gán).
Kiểm detector đè khóa máy và sai tiền nhiệm, vòng đời state, luật ngoại
lệ (kỹ thuật bất khả không được duyệt), và gate PHÁT HÀNH (còn Chặn → chặn; ngoại lệ → thả; thu hồi).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.db import SessionLocal
from app.models.lsx import (
    LB_MAY, LB_THUE_NGOAI, LB_TO, Lsx, LsxCongDoan, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH,
)
from app.models.may_thiet_bi import MayThietBi
from app.models.role import Role, RolePermission
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.repositories.xep_lich_repo import XepLichRepository
from app.security import create_access_token, hash_password
from app.services.xep_lich_service import XepLichConflict, _utcnow
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
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1  # theo máy 30+60 = 90'
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


def _gop_in_va_san_sang(db, bg_svc, bg, admin):
    """Gộp bước in + lập kế hoạch lượt chung → bài đủ điều kiện sẵn sàng.

    Bài ghép không tự gộp bước nào; chưa gộp thì đó là N lệnh rời và gate `san_sang` chặn.
    """
    from app.models.department import Department

    tvs = bg_svc._get(bg.id).thanh_viens
    bg_svc.gop(bai_ghep_id=bg.id, actor=admin,
               step_keys=[_in_step(db, tv.lsx_id).step_key for tv in tvs])
    mau = _in_step(db, tvs[0].lsx_id)
    to_id = mau.department_id or db.query(Department.id).scalar()
    for c in bg_svc._buoc_chungs(bg_svc._get(bg.id)):
        bg_svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bg.id, gang_step_key=c.step_key, actor=admin,
            patch={"department_id": to_id, "may_id": mau.may_id},
        )
    return bg_svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai="san_sang", actor=admin)


# --- Xả tờ là bước Máy bình thường, không còn detector theo tên ---------------
def test_khong_con_detector_gang_thieu_xa_to(db, orders, lsx_svc, bg_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Có hay không có bước tên Xả tờ đều do routing động quyết định, không sinh cảnh báo hardcode.
    db.add(LsxCongDoan(lsx_id=a.id, thu_tu=1, ten="Dán", nhom="finishing", loai_buoc=LB_TO,
                       department_id=_in_step(db, a.id).department_id, so_luong_vao=5000, chay_phut=20))
    db.add(LsxCongDoan(lsx_id=b.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
                       may_id=_in_step(db, b.id).may_id, so_luong_vao=5000, nang_suat=6000,
                       don_vi_nang_suat="to_gio"))
    db.commit()
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    bg = _gop_in_va_san_sang(db, bg_svc, bg, admin)
    xl_svc.dua_vao_bai_ghep(bai_ghep_id=bg.id, actor=admin)
    gang = _cats(vd_svc.liet_ke(), "gang_thieu_xa_to")
    assert gang == []


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
    # Mốc xếp phải nằm ở TƯƠNG LAI so với lúc chạy test, không được ghim cứng ngày.
    # `_san_thoi_gian` lấy sàn = max(now, ban_giao_at) — mà `ban_giao_at` do fixture đóng dấu
    # bằng giờ THẬT. Ghim cứng một ngày thì tới ngày đó test đỏ vĩnh viễn: sàn vượt `start_at`
    # ⇒ detector `sai_tien_nhiem` bắn thêm xung đột Chặn, gate phát hành không bao giờ mở.
    # ĐÃ NỔ THẬT lúc 2026-07-27 08:00 UTC với mốc cũ `datetime(2026, 7, 27, 8, 0)`.
    bat_dau = (_utcnow() + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
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


# --- Detector: quá tải máy (cửa sổ 7 ngày) ----------------------------------
def test_qua_tai_may_detector(db, orders, lsx_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    # Neo "hôm nay" của detector về đúng ngày xếp (cửa sổ 7 ngày mới trùm dòng đã xếp).
    fixed = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.xep_lich_van_de_service._utcnow", lambda: fixed)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_step(db, lsx.id)
    # Ô "Thời gian khác" 4000' (~66h) chiếm máy > 7×480' = 3360' khả dụng (nền fallback
    # 8h/ngày) → >100% Cao. Dùng ô này vì `chay_phut` gõ đè đã bỏ (2026-08-04): thời gian
    # chạy nay luôn suy từ tốc độ máy, không ghim cứng được nữa.
    step.so_luot_chay, step.so_luong_vao = 1, 5000
    step.phat_sinh_phut = 4000
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    xl_svc.gan(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": fixed}, actor=admin)
    qt = _cats(vd_svc.liet_ke(), "qua_tai_may")
    assert len(qt) == 1 and qt[0]["severity"] == "cao"
    assert step.may_id in qt[0]["impacts"]["may_ids"]

    # Dời "hôm nay" ra xa 60 ngày → dòng nằm NGOÀI cửa sổ 7 ngày → hết cảnh báo tải.
    monkeypatch.setattr("app.services.xep_lich_van_de_service._utcnow",
                        lambda: datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc))
    assert _cats(vd_svc.liet_ke(), "qua_tai_may") == []


# --- Detector: hạn LSX sớm hơn lúc bài ghép in xong -------------------------
def test_han_som_bai_ghep_detector(db, orders, lsx_svc, bg_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    a.han_hoan_thanh_sx = date(2026, 7, 20)   # SỚM hơn lúc in ghép xong (27/7) → bị bắt
    b.han_hoan_thanh_sx = date(2026, 8, 30)   # xa → không bị bắt
    db.commit()
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    bg = _gop_in_va_san_sang(db, bg_svc, bg, admin)
    xl_svc.dua_vao_bai_ghep(bai_ghep_id=bg.id, actor=admin)
    in_dong = XepLichRepository(db).by_bai_ghep(bg.id)[0]
    xl_svc.gan(dong_id=in_dong.id, patch={"may_id": _in_step(db, a.id).may_id,
               "start_at": datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)}, actor=admin)
    keys = [it["issue_key"] for it in _cats(vd_svc.liet_ke(), "han_bai_ghep")]
    assert f"han_bai_ghep:{a.id}:{bg.id}" in keys
    assert f"han_bai_ghep:{b.id}:{bg.id}" not in keys
    only = _cats(vd_svc.liet_ke(), "han_bai_ghep")
    assert all(it["severity"] == "nghiem_trong" for it in only)


# --- Detector: thuê ngoài thiếu dữ liệu (Chặn) ------------------------------
def test_thue_ngoai_thieu_detector(db, orders, lsx_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    s = _in_step(db, lsx.id)
    s.setup_phut, s.nang_suat, s.so_luong_vao, s.chay_phut = 0, 5000, 5000, None
    # Bước thuê ngoài BẮT BUỘC chưa chọn NCC + chưa có ngày gửi/nhận → Chặn.
    db.add(LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Cán màng ngoài", nhom="finishing",
                       loai_buoc=LB_THUE_NGOAI, bat_buoc=True, so_luong_vao=5000))
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    tn = _cats(vd_svc.liet_ke(), "thue_ngoai")
    assert any(it["issue_key"].startswith("thue_ngoai_thieu") and it["severity"] == "chan" for it in tn)


# --- Detector: bước sau xếp trước ngày nhận gia công (Nghiêm trọng) ---------
def test_thue_ngoai_tre_detector(db, orders, lsx_svc, xl_svc, vd_svc, admin, customer, monkeypatch):
    _luon_lam(monkeypatch)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    s = _in_step(db, lsx.id)
    s.setup_phut, s.nang_suat, s.so_luong_vao, s.chay_phut = 0, 5000, 5000, None
    # Thuê ngoài ĐỦ dữ liệu (không "thiếu"), nhận hàng dự kiến 30/7.
    db.add(LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Cán màng ngoài", nhom="finishing",
                       loai_buoc=LB_THUE_NGOAI, bat_buoc=True, so_luong_vao=5000,
                       nha_cung_cap="Cơ sở A", ngay_gui_dk=date(2026, 7, 28), ngay_nhan_dk=date(2026, 7, 30)))
    # Bước sau (Dán, chiếm tổ) — sẽ xếp TRƯỚC ngày nhận.
    db.add(LsxCongDoan(lsx_id=lsx.id, thu_tu=2, ten="Dán", nhom="finishing", loai_buoc=LB_TO,
                       department_id=s.department_id, so_luong_vao=5000, chay_phut=30, don_vi_vao="cai"))
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    dongs = XepLichRepository(db).by_lsx(lsx.id)
    dan = next(d for d in dongs if d.loai_buoc == LB_TO)
    tn_dong = next(d for d in dongs if d.loai_buoc == LB_THUE_NGOAI)
    xl_svc.gan(dong_id=dan.id, patch={"department_id": s.department_id,
               "start_at": datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)}, actor=admin)
    keys = [it["issue_key"] for it in _cats(vd_svc.liet_ke(), "thue_ngoai")]
    assert f"thue_ngoai_tre:{tn_dong.id}" in keys           # bước sau (28/7) trước ngày nhận (30/7)
    assert not any(k.startswith("thue_ngoai_thieu") for k in keys)  # đã đủ NCC + ngày


# --- Gate: duyệt ngoại lệ đòi approve_exception (tách khỏi approve) ----------
def test_ngoai_le_gate_doi_approve_exception(client):
    """Vai chỉ có `approve` (phát hành) mà THIẾU `approve_exception` → duyệt ngoại lệ 403;
    vai Kế hoạch SX (seed đã gán approve_exception) qua được cửa quyền."""
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name("Sản xuất")
        users = UserRepository(db)
        # Vai A: có approve NHƯNG thiếu approve_exception.
        role_a = Role(name="SX phát-không-ngoại-lệ", department_id=dept.id)
        db.add(role_a)
        db.flush()
        db.add(RolePermission(role_id=role_a.id, module_key="san_xuat", scope="all",
                              can_read=True, can_update=True, can_approve=True,
                              can_approve_exception=False))
        ua = users.create(username="sx_approve_only", name="SX phát", password_hash=hash_password("x"))
        users.set_assignment(ua, department_id=dept.id, role_id=role_a.id, is_active=True)
        # Vai B: Kế hoạch SX (seed_all đã gán can_approve_exception=True).
        role_b = RoleRepository(db).get_by_name_and_department("Kế hoạch SX", dept.id)
        ub = users.create(username="sx_ke_hoach", name="KH SX", password_hash=hash_password("x"))
        users.set_assignment(ub, department_id=dept.id, role_id=role_b.id, is_active=True)
        db.commit()
        uid_a, uid_b = ua.id, ub.id
    finally:
        db.close()

    key = {"issue_key": "trung_may:1:1:2", "ly_do": "thử"}
    r = client.post("/api/xep-lich/van-de/ngoai-le", json=key,
                    headers={"Authorization": f"Bearer {create_access_token(str(uid_a))}"})
    assert r.status_code == 403, r.text

    r2 = client.post("/api/xep-lich/van-de/ngoai-le", json=key,
                     headers={"Authorization": f"Bearer {create_access_token(str(uid_b))}"})
    assert r2.status_code != 403, r2.text
