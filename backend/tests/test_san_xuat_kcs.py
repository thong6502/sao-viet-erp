"""Thực hiện sản xuất — KCS theo LỆNH (`docs/design-kcs-theo-lenh.md`, mg `0306`).

Soi tầng service `services/san_xuat/kcs.py` + `kho.tao_yeu_cau_nhap_kho_cong_doan`, không qua HTTP:
  · ai là KCS: thành viên phòng ban `is_kcs` — kiểm được công đoạn của MỌI tổ, không cần dòng quyền
    theo tổ nào; admin không đứng trong tổ KCS thì bị chặn; đóng thiếu chỉ trưởng tổ KCS;
  · MỘT hành động `kiem_cong_doan`: công đoạn đang chạy / tạm dừng / đã xong, lặp nhiều lần; không đẻ
    mẻ sản lượng, không đổi trạng thái; lỗi > 0 ⇒ mô tả + ≥1 ảnh, tổ chịu = tổ của công đoạn; công
    đoạn cuối ⇒ Σ đạt ≤ Σ tốt;
  · tổ bị báo lỗi bấm "Đã xem" (người Xác nhận sản lượng TRỌN tổ), bấm lại không đổi gì;
  · điều chỉnh giữ nguyên tổng; Σ đạt sau điều chỉnh không thấp hơn Σ đã đề nghị nhập kho;
  · màn KCS: danh sách lệnh + chuỗi công đoạn; mục "Kết quả KCS" của một công đoạn;
  · nhập kho từ công đoạn cuối: server tự tính phần đạt chưa gửi, trần theo tốt, hết số → 409;
  · migration `0306` nắn lỗi cũ + bỏ cột, chạy lại vô hại;
  · đường dây HTTP: chưa đăng nhập 401, admin không thuộc tổ KCS 403.

File này cũng là NGUỒN HELPER cho các test KCS/kho/đóng nhóm khác (`_batch`, `_to_kiem`, …).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text

from app.db_migrations import _migrate_kcs_theo_lenh
from app.models.department import Department
from app.models.may_thiet_bi import MayThietBi
from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_PHAT_HANH, CV_TAM_DUNG
from app.models.san_xuat_kcs import (
    KCS_DAT,
    KCS_DAT_MOT_PHAN,
    KCS_KHONG_DAT,
    SanXuatKcsBatch,
    SanXuatKcsLoi,
    SanXuatKcsLoiAnh,
)
from app.models.lsx import LsxCongDoan
from app.models.san_xuat import SanXuatCongViec
from app.models.stock_request import REQ_APPROVED, StockRequest
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from app.services.san_xuat.vat_tu_de_nghi import _hang_service, _req_service
from app.services.san_xuat import kcs, kho
from tests.quyen_to_fixtures import cap_quyen_to

# Fixtures + helper luồng thật (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    _mot_cv,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_T0 = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
_T1 = _T0 + timedelta(hours=1)


# --- Dàn cảnh dùng chung --------------------------------------------------------------------
def _cv_kcs(db, orders, lsx_svc, admin, customer, ma="TO-KCS", *, cuoi: bool = False):
    """Một tổ khoán + một công đoạn ĐANG CHẠY có đơn vị ra — kiểm được ngay.

    Cờ công đoạn cuối nhóm đặt TƯỜNG MINH theo `cuoi`: lệnh phát hành trọn vào một tổ nên phát hành
    có thể đã đánh dấu công đoạn này là cuối — test luật giữa chuyền cần gỡ cờ đó."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = CV_DANG_CHAY
    cv.la_kcs_cuoi = cuoi
    cv.don_vi_ra = "cái"
    cv.don_vi_vao = "cái"
    db.commit()
    return to, cv


def _cv_production(db, orders, lsx_svc, admin, customer, *, ma="TO-SX-DX", trang_thai=CV_DANG_CHAY):
    """Một công đoạn sản xuất thường ở trạng thái `trang_thai` (giữ đơn vị gốc của routing)."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = trang_thai
    cv.la_kcs_cuoi = False
    db.commit()
    return to, cv


def _to_kiem(db, ten="Tổ KCS", ma="TO-KCS-KIEM", *, truong: bool = False) -> tuple[Department, User]:
    """Một phòng ban `is_kcs` + MỘT thành viên (`department_id` trỏ đúng phòng). Không cấp dòng quyền
    theo tổ nào — là KCS chỉ nhờ đứng trong phòng. `truong` thì người này đứng đầu phòng."""
    d = Department(name=ten, code=ma, is_kcs=True)
    db.add(d)
    db.flush()
    u = User(username=f"kcs_{ma.lower()}", name=f"KCS {ma}", password_hash="x", department_id=d.id)
    db.add(u)
    db.flush()
    if truong:
        d.head_user_id = u.id
    db.commit()
    return d, u


def _to_chiu(db, ten="Tổ Bế Bị Đổ", ma="TO-CHIU") -> tuple[Department, User]:
    """Một tổ SX khác + MỘT người được bật đủ quyền chi tiết trên TRỌN tổ đó."""
    u = User(username=f"tt_{ma.lower()}", name="Tổ Trưởng Bế", password_hash="x")
    db.add(u)
    db.flush()
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    cap_quyen_to(db, u, d)
    return d, u


def _nguoi_o_to(db, dept, username, *, scope: str | None = SCOPE_ALL,
                viec=("confirm_output",)) -> User:
    """Một tài khoản ĐỨNG TRONG tổ `dept` + dòng quyền theo tổ của `dept`: bật Xem + `viec` với phạm
    vi `scope`. `scope=None` = không cấp gì — thành viên thường."""
    u = User(username=username, name=f"Người {username}", password_hash="x", department_id=dept.id)
    db.add(u)
    db.flush()
    if scope is not None:
        cap_quyen_to(db, u, dept, scope=scope, viec=viec)
    db.commit()
    return u


def _anh() -> list[dict]:
    return [{"file_name": "loi.jpg", "file_url": "/api/files/san-xuat/kcs-loi/1/x_loi.jpg",
             "file_type": "image/jpeg"}]


def _ghi_tot(db, cv, tot, *, hong=0) -> SanXuatBatch:
    """Một mẻ sản lượng tổ đã ghi — nền trần "Σ đạt ≤ Σ tốt" của công đoạn cuối."""
    b = SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1, tong=tot + hong, tot=tot,
                     hong=hong, don_vi=cv.don_vi_ra or "cái")
    db.add(b)
    db.commit()
    return b


def _batch(db, orders, lsx_svc, admin, customer, *, nhan=None, dat=90, khong_dat=10, ma="TO-KCS",
           cuoi: bool = False, tot=None):
    """Tổ `ma` + công đoạn đang chạy + MỘT lần kiểm của một người KCS (có lỗi thì kèm mô tả + ảnh).

    Luôn ghi sẵn mẻ tốt (`tot`, mặc định = đạt + lỗi) — tổ chưa ghi thì chưa có gì để kiểm.
    `cuoi` đánh dấu công đoạn cuối nhóm. `nhan` giữ cho chữ ký cũ — nếu truyền thì phải bằng đạt +
    lỗi. Trả `(to, cv, res)`; `res["nguoi_kcs"]` là người đã kiểm, dùng tiếp cho các thao tác cần KCS
    (nhập kho, điều chỉnh)."""
    assert nhan is None or abs(nhan - (dat + khong_dat)) < 1e-9
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, ma=ma, cuoi=cuoi)
    _ghi_tot(db, cv, dat + khong_dat if tot is None else tot)
    _d, nguoi = _to_kiem(db, ten=f"Tổ KCS {ma}", ma=f"{ma}-KCS")
    res = kcs.kiem_cong_doan(
        db, user=nguoi, cong_viec_id=cv.id, so_dat=dat, so_loi=khong_dat,
        loi_mo_ta="Lem mực" if khong_dat else None, anh=_anh() if khong_dat else None,
    )
    res["nguoi_kcs"] = nguoi
    return to, cv, res


def _dem_me(db, cv) -> int:
    return db.query(SanXuatBatch).filter_by(cong_viec_id=cv.id).count()


# --- Ai là KCS ------------------------------------------------------------------------------
def test_gate_kcs_chi_thanh_vien_phong_is_kcs(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, cuoi=True)
    _ghi_tot(db, cv, 10)
    # Admin có đủ quyền theo tổ trên tổ chạy việc nhưng không đứng trong tổ KCS nào.
    with pytest.raises(PermissionError):
        kcs.kiem_cong_doan(db, user=admin, cong_viec_id=cv.id, so_dat=10)
    tho = _nguoi_o_to(db, to, "tho_cung_to", viec=("run_order", "confirm_output", "warehouse"))
    with pytest.raises(PermissionError):
        kcs.kiem_cong_doan(db, user=tho, cong_viec_id=cv.id, so_dat=10)
    assert db.query(SanXuatKcsBatch).count() == 0

    _d, thanh_vien = _to_kiem(db)
    assert kcs.la_nguoi_kcs(db, thanh_vien) and not kcs.la_truong_kcs(db, thanh_vien)
    kcs.kiem_cong_doan(db, user=thanh_vien, cong_viec_id=cv.id, so_dat=10)
    _d2, truong = _to_kiem(db, ten="Tổ KCS 2", ma="TO-KCS-2", truong=True)
    assert kcs.la_truong_kcs(db, truong)
    with pytest.raises(PermissionError):
        kcs.gate_truong_kcs(db, thanh_vien)
    kcs.gate_truong_kcs(db, truong)


# --- Kiểm công đoạn -------------------------------------------------------------------------
def test_kiem_cong_doan_ghi_lan_kiem_khong_de_me_khong_doi_trang_thai(
    db, orders, lsx_svc, admin, customer
):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, cuoi=True)
    _ghi_tot(db, cv, 100)
    me_truoc = _dem_me(db, cv)
    _d, nguoi = _to_kiem(db)

    res = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=90, so_loi=10,
                             loi_mo_ta="Lem mực", anh=_anh(), ghi_chu="  Soi đèn  ")

    kb = db.get(SanXuatKcsBatch, res["kcs_batch_id"])
    assert float(kb.so_luong_nhan) == 100 and float(kb.so_luong_dat) == 90
    assert float(kb.so_luong_khong_dat) == 10 and kb.ket_luan == KCS_DAT_MOT_PHAN
    assert kb.created_by == nguoi.id and kb.nhom_id == cv.nhom_id and kb.don_vi == "cái"
    assert kb.ghi_chu == "Soi đèn"
    db.refresh(cv)
    assert _dem_me(db, cv) == me_truoc and cv.trang_thai == CV_DANG_CHAY
    assert res["department_id"] == to.id and res["lsx_id"] == cv.lsx_id and res["lsx_ma"]
    assert res["nguoi_kiem"] == nguoi.name
    assert AuditLogRepository(db).list_for_target(f"san_xuat_kcs_batch:{kb.id}")[0].action \
        == "san_xuat_kcs_kiem"


@pytest.mark.parametrize("dat, loi, ket_luan", [(50, 0, KCS_DAT), (0, 40, KCS_KHONG_DAT)])
def test_ket_luan_suy_tu_so(db, orders, lsx_svc, admin, customer, dat, loi, ket_luan):
    _to, _cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=dat, khong_dat=loi, cuoi=True)
    assert db.get(SanXuatKcsBatch, res["kcs_batch_id"]).ket_luan == ket_luan


@pytest.mark.parametrize("trang_thai, duoc", [
    (CV_TAM_DUNG, True), (CV_HOAN_THANH, True), (CV_PHAT_HANH, False),
])
def test_trang_thai_kiem_duoc(db, orders, lsx_svc, admin, customer, trang_thai, duoc):
    _to, cv = _cv_production(db, orders, lsx_svc, admin, customer, trang_thai=trang_thai)
    _ghi_tot(db, cv, 5)
    _d, nguoi = _to_kiem(db)
    if duoc:
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=1, loi_mo_ta="Lem", anh=_anh())
        db.refresh(cv)
        assert cv.trang_thai == trang_thai
    else:
        with pytest.raises(ValueError, match="chưa bắt đầu"):
            kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=1, loi_mo_ta="Lem", anh=_anh())


def test_kiem_lap_nhieu_lan_cong_don(db, orders, lsx_svc, admin, customer):
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=30, khong_dat=0, cuoi=True)
    _ghi_tot(db, cv, 25)
    kcs.kiem_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv.id, so_dat=20, so_loi=5,
                       loi_mo_ta="Xước", anh=_anh())
    assert SanXuatKcsRepository(db).tong_kiem_nhieu([cv.id])[cv.id] == (2, 50.0, 5.0)


@pytest.mark.parametrize("dat, loi, loi_msg", [
    (-1, 0, "không được âm"), (5, -2, "không được âm"), (0, 0, "Nhập số đạt hoặc số lỗi"),
    ("abc", 0, "không hợp lệ"),
])
def test_luat_so(db, orders, lsx_svc, admin, customer, dat, loi, loi_msg):
    _to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, cuoi=True)
    _ghi_tot(db, cv, 10)
    _d, nguoi = _to_kiem(db)
    with pytest.raises(ValueError, match=loi_msg):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=dat, so_loi=loi)


def test_co_loi_bat_buoc_mo_ta_va_anh(db, orders, lsx_svc, admin, customer):
    _to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    _ghi_tot(db, cv, 6)
    _d, nguoi = _to_kiem(db)
    with pytest.raises(ValueError, match="mô tả lỗi"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=5, so_loi=1,
                           loi_mo_ta="   ", anh=_anh())
    with pytest.raises(ValueError, match="ít nhất một ảnh"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=5, so_loi=1,
                           loi_mo_ta="Lem", anh=[])
    with pytest.raises(ValueError, match="thiếu tên file"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=5, so_loi=1,
                           loi_mo_ta="Lem", anh=[{"file_name": "a.jpg"}])
    assert db.query(SanXuatKcsBatch).count() == 0


def test_loi_neo_to_cua_cong_doan_va_bao_nguoi_xac_nhan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    xac_nhan = _nguoi_o_to(db, to, "xn_tron", viec=("confirm_output",))
    chi_chay = _nguoi_o_to(db, to, "chi_chay", viec=("run_order",))
    xn_cua_toi = _nguoi_o_to(db, to, "xn_cua_toi", scope=SCOPE_OWN, viec=("confirm_output",))
    _d, nguoi = _to_kiem(db)
    _ghi_tot(db, cv, 10)

    res = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=8, so_loi=2,
                             loi_mo_ta="Bong keo", anh=_anh() + _anh())

    loi = db.get(SanXuatKcsLoi, res["loi_id"])
    assert loi.to_chiu_id == to.id and loi.cong_doan_ref_id == cv.id
    assert float(loi.so_luong) == 2 and loi.mo_ta == "Bong keo" and loi.phan_hoi_luc is None
    assert db.query(SanXuatKcsLoiAnh).filter_by(loi_id=loi.id).count() == 2
    ids = set(res["notify_user_ids"])
    assert xac_nhan.id in ids and chi_chay.id not in ids and xn_cua_toi.id not in ids


def test_khong_loi_thi_khong_ghi_dong_loi(db, orders, lsx_svc, admin, customer):
    _to, _cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=10, khong_dat=0, cuoi=True)
    assert res["loi_id"] is None
    assert db.query(SanXuatKcsLoi).count() == 0


def test_checklist_bat_buoc(db, orders, lsx_svc, admin, customer):
    _to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, cuoi=True)
    cv.kcs_tieu_chi_json = [
        {"thu_tu": 1, "ten": "Đúng màu", "bat_buoc": True},
        {"thu_tu": 2, "ten": "Sạch bụi", "bat_buoc": False},
    ]
    db.commit()
    _ghi_tot(db, cv, 5)
    _d, nguoi = _to_kiem(db)
    with pytest.raises(ValueError, match="tiêu chí kiểm tra bắt buộc"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=5,
                           checklist_ket_qua=[{"thu_tu": 2, "dat": True}])
    res = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=5,
                             checklist_ket_qua=[{"thu_tu": 1, "dat": True}])
    assert db.get(SanXuatKcsBatch, res["kcs_batch_id"]).checklist_json == [{"thu_tu": 1, "dat": True}]


def test_so_dat_tuong_minh_cung_khong_vuot_phan_chua_kiem(db, orders, lsx_svc, admin, customer):
    """Nhánh gửi `so_dat` (kiểm một phần) chung trần với form chỉ gõ số lỗi. Trước 19/09/2026 nó chỉ
    chặn đạt vượt tốt ở bước cuối ⇒ lọt lần kiểm 0 đạt · 1 lỗi trên Đóng gói đã kiểm hết (301/300)."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=40, khong_dat=0, cuoi=True, tot=50)
    nguoi = res["nguoi_kcs"]
    with pytest.raises(ValueError, match=r"Đạt \+ lỗi \(11\) vượt phần tổ đã làm mà chưa kiểm \(10\)"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=11)
    # Lỗi cũng là hàng tổ đã ghi — tính vào trần như đạt.
    with pytest.raises(ValueError, match="vượt phần tổ đã làm mà chưa kiểm"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=0, so_loi=11,
                           loi_mo_ta="Móp góc", anh=_anh())
    kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=4, so_loi=6,
                       loi_mo_ta="Lệch bế", anh=_anh())
    # Đã kiểm hết ⇒ đúng ca lọt cũ giờ bị chặn, không đẻ lần kiểm.
    with pytest.raises(ValueError, match="chưa có gì để kiểm"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=0, so_loi=1,
                           loi_mo_ta="Móp góc", anh=_anh())
    assert SanXuatKcsRepository(db).tong_kiem_nhieu([cv.id])[cv.id] == (2, 44.0, 6.0)


# --- Công đoạn GIỮA chỉ ghi lỗi (19/09/2026): không đạt, không tiêu chí, trần Σ lỗi ≤ Σ tốt ------
def test_cong_doan_giua_chi_ghi_loi(db, orders, lsx_svc, admin, customer):
    _to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    assert not cv.la_kcs_cuoi
    cv.kcs_tieu_chi_json = [{"thu_tu": 1, "ten": "Đúng màu", "bat_buoc": True}]
    db.commit()
    _d, nguoi = _to_kiem(db)
    with pytest.raises(ValueError, match="chưa ghi sản lượng"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=1, loi_mo_ta="Lem", anh=_anh())
    _ghi_tot(db, cv, 20)
    # Không lỗi thì không có gì để ghi — dù gửi số đạt.
    with pytest.raises(ValueError, match="ít nhất một dòng lỗi"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=20)
    # Số đạt gửi kèm bị bỏ qua, tiêu chí bắt buộc không đòi; ghi được nhiều lần, không cần tổ ghi thêm.
    r1 = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=15, so_loi=5,
                            loi_mo_ta="Lem", anh=_anh())
    kb = db.get(SanXuatKcsBatch, r1["kcs_batch_id"])
    assert r1["so_dat"] == 0 and float(kb.so_luong_dat) == 0 and kb.checklist_json is None
    kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=15, loi_mo_ta="Xước", anh=_anh())
    # Trần: Σ lỗi không vượt số tốt tổ đã ghi.
    with pytest.raises(ValueError, match=r"Tổng lỗi \(21\) vượt số tốt tổ đã ghi \(20\)"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=1, loi_mo_ta="Móp", anh=_anh())
    assert SanXuatKcsRepository(db).tong_kiem_nhieu([cv.id])[cv.id] == (2, 0.0, 20.0)
    out = kcs.ket_qua_kcs_cong_viec(db, nguoi, cv.id)
    assert out["la_kcs_cuoi"] is False and out["cuoi"] is None


# --- Form KCS chỉ gõ SỐ LỖI (18/09/2026): đạt = phần tổ đã làm chưa kiểm − lỗi ----------------
def test_chi_go_so_loi_dat_la_phan_chua_kiem_tru_loi(db, orders, lsx_svc, admin, customer):
    _to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, cuoi=True)
    _d, nguoi = _to_kiem(db)
    _ghi_tot(db, cv, 100)
    r1 = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=3,
                            loi_mo_ta="Lem mực", anh=_anh())
    kb = db.get(SanXuatKcsBatch, r1["kcs_batch_id"])
    assert r1["so_dat"] == 97 and float(kb.so_luong_nhan) == 100 and kb.ket_luan == KCS_DAT_MOT_PHAN
    # Tổ ghi thêm 50 ⇒ lần kiểm sau chỉ bao 50 mới, không lỗi thì đạt trọn.
    _ghi_tot(db, cv, 50)
    r2 = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id)
    assert r2["so_dat"] == 50 and r2["so_loi"] == 0
    assert SanXuatKcsRepository(db).tong_kiem_nhieu([cv.id])[cv.id] == (2, 147.0, 3.0)


def test_chi_go_so_loi_chan_khi_chua_co_gi_de_kiem_hoac_loi_vuot(db, orders, lsx_svc, admin, customer):
    _to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, cuoi=True)
    _d, nguoi = _to_kiem(db)
    with pytest.raises(ValueError, match="chưa có gì để kiểm"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=0)
    _ghi_tot(db, cv, 20)
    with pytest.raises(ValueError, match=r"Số lỗi \(21\) vượt phần tổ đã làm mà chưa kiểm \(20\)"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=21,
                           loi_mo_ta="Lem", anh=_anh())
    # Lỗi trọn phần chưa kiểm ⇒ đạt 0, kết luận không đạt; sau đó hết phần để kiểm.
    r = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_loi=20, loi_mo_ta="Lem", anh=_anh())
    assert r["so_dat"] == 0 and r["ket_luan"] == KCS_KHONG_DAT
    with pytest.raises(ValueError, match="chưa có gì để kiểm"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id)
    assert db.query(SanXuatKcsBatch).count() == 1


# --- Tổ bấm "Đã xem" ------------------------------------------------------------------------
def test_da_xem_loi_gate_va_bam_lai_khong_doi(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    with pytest.raises(PermissionError):
        kcs.da_xem_loi(db, user=res["nguoi_kcs"], loi_id=res["loi_id"])
    cua_toi = _nguoi_o_to(db, to, "xem_cua_toi", scope=SCOPE_OWN)
    with pytest.raises(PermissionError):
        kcs.da_xem_loi(db, user=cua_toi, loi_id=res["loi_id"])
    to_khac, tt_khac = _to_chiu(db)
    with pytest.raises(PermissionError):
        kcs.da_xem_loi(db, user=tt_khac, loi_id=res["loi_id"])

    truong = _nguoi_o_to(db, to, "truong_to_xem")
    r1 = kcs.da_xem_loi(db, user=truong, loi_id=res["loi_id"])
    assert r1["nguoi_xem"] == truong.name and r1["da_xem_luc"] and r1["version"] == 2
    assert r1["department_id"] == to.id and r1["cong_viec_id"] == cv.id
    assert r1["nguoi_kiem_id"] == res["nguoi_kcs"].id

    khac = _nguoi_o_to(db, to, "truong_to_xem_2")
    r2 = kcs.da_xem_loi(db, user=khac, loi_id=res["loi_id"])
    assert r2["version"] == 2 and r2["nguoi_xem"] == truong.name and r2["da_xem_luc"] == r1["da_xem_luc"]
    with pytest.raises(ValueError):
        kcs.da_xem_loi(db, user=truong, loi_id=999_999)


def test_loi_cho_xem_het_khi_to_da_xem(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    ds = kcs.loi_cho_xem(db, [to.id])
    assert [d["loi_id"] for d in ds] == [res["loi_id"]]
    d = ds[0]
    assert d["cong_viec_id"] == cv.id and d["to_id"] == to.id and d["ten_cong_doan"] == cv.ten_cong_doan
    assert d["lsx_ma"] == res["lsx_ma"] and d["mo_ta"] == "Lem mực" and d["so_luong"] == 10
    assert d["so_anh"] == 1 and d["nguoi_kiem"] == res["nguoi_kcs"].name
    assert kcs.loi_cho_xem(db, [to.id + 999]) == []

    kcs.da_xem_loi(db, user=_nguoi_o_to(db, to, "xem_xong"), loi_id=res["loi_id"])
    assert kcs.loi_cho_xem(db, [to.id]) == []


# --- Điều chỉnh -----------------------------------------------------------------------------
def test_dieu_chinh_gate_version_va_tong(db, orders, lsx_svc, admin, customer):
    _to, _cv, res = _batch(db, orders, lsx_svc, admin, customer)
    nguoi, kid = res["nguoi_kcs"], res["kcs_batch_id"]
    with pytest.raises(PermissionError):
        kcs.dieu_chinh_ket_qua(db, user=admin, kcs_batch_id=kid, so_luong_dat=95,
                               so_luong_khong_dat=5, expected_version=1)
    with pytest.raises(ValueError, match="Phiên bản"):
        kcs.dieu_chinh_ket_qua(db, user=nguoi, kcs_batch_id=kid, so_luong_dat=95,
                               so_luong_khong_dat=5, expected_version=7)
    with pytest.raises(ValueError, match="không đổi tổng"):
        kcs.dieu_chinh_ket_qua(db, user=nguoi, kcs_batch_id=kid, so_luong_dat=95,
                               so_luong_khong_dat=10, expected_version=1)


def test_dieu_chinh_chia_lai_dat_loi_va_audit(db, orders, lsx_svc, admin, customer):
    _to, _cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    kid = res["kcs_batch_id"]
    out = kcs.dieu_chinh_ket_qua(db, user=res["nguoi_kcs"], kcs_batch_id=kid, so_luong_dat=95,
                                 so_luong_khong_dat=5, expected_version=1)
    assert out["version"] == 2 and out["ket_luan"] == KCS_DAT_MOT_PHAN
    loi = db.get(SanXuatKcsLoi, res["loi_id"])
    assert float(loi.so_luong) == 5 and loi.version == 2
    assert db.query(SanXuatKcsLoiAnh).filter_by(loi_id=loi.id).count() == 1
    log = AuditLogRepository(db).list_for_target(f"san_xuat_kcs_batch:{kid}")
    dc = [r for r in log if r.action == "san_xuat_kcs_dieu_chinh"]
    assert dc and "truoc(dat=90, loi=10" in dc[0].detail and "sau(dat=95, loi=5" in dc[0].detail


def test_dieu_chinh_them_loi_khi_chua_co_mo_ta_bi_chan(db, orders, lsx_svc, admin, customer):
    _to, _cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=10, khong_dat=0, cuoi=True)
    with pytest.raises(ValueError, match="chưa có mô tả"):
        kcs.dieu_chinh_ket_qua(db, user=res["nguoi_kcs"], kcs_batch_id=res["kcs_batch_id"],
                               so_luong_dat=7, so_luong_khong_dat=3, expected_version=1)


def test_dieu_chinh_cong_doan_cuoi_van_giu_tran_tot(db, orders, lsx_svc, admin, customer):
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=60, khong_dat=0, cuoi=True, tot=100)
    r2 = kcs.kiem_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv.id, so_dat=30, so_loi=10,
                            loi_mo_ta="Lem", anh=_anh())
    # Tổ hạ mẻ SAU khi KCS đã kiểm ⇒ điều chỉnh (giữ tổng) vẫn không được đẩy Σ đạt vượt tốt.
    me = db.query(SanXuatBatch).filter_by(cong_viec_id=cv.id).one()
    me.tot = me.tong = 95
    db.commit()
    with pytest.raises(ValueError, match="vượt số tốt"):
        kcs.dieu_chinh_ket_qua(db, user=res["nguoi_kcs"], kcs_batch_id=r2["kcs_batch_id"],
                               so_luong_dat=40, so_luong_khong_dat=0, expected_version=1)


def _huy_boi_kho(db, request_id: int) -> None:
    """Kho huỷ yêu cầu nhập (Hộp yêu cầu ▸ Huỷ) — đúng hàm router kho gọi."""
    req = db.get(StockRequest, request_id)
    _req_service(db, _hang_service(db)).cancel_by_kho(req, "Không nhận")


def test_dieu_chinh_khong_ha_dat_duoi_so_da_gui_kho(db, orders, lsx_svc, admin, customer):
    """Đã đề nghị nhập 90 thì Σ đạt không được hạ dưới 90; kho huỷ yêu cầu thì hạ được."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    nguoi, kid = res["nguoi_kcs"], res["kcs_batch_id"]
    yc = kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=nguoi, cong_viec_id=cv.id)
    with pytest.raises(ValueError, match="đã đề nghị nhập kho 90"):
        kcs.dieu_chinh_ket_qua(db, user=nguoi, kcs_batch_id=kid, so_luong_dat=85,
                               so_luong_khong_dat=15, expected_version=1)
    _huy_boi_kho(db, yc["request_id"])
    kcs.dieu_chinh_ket_qua(db, user=nguoi, kcs_batch_id=kid, so_luong_dat=85,
                           so_luong_khong_dat=15, expected_version=1)


# --- Đọc ------------------------------------------------------------------------------------
def test_ket_qua_kcs_cong_viec(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    _ghi_tot(db, cv, 5)
    r2 = kcs.kiem_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv.id, so_dat=5)

    out = kcs.ket_qua_kcs_cong_viec(db, res["nguoi_kcs"], cv.id)
    assert out["cong_viec_id"] == cv.id and out["la_kcs_cuoi"] is True
    # Công đoạn cuối: tổ thấy KCS đạt trên số tốt mình ghi + đã đề nghị kho.
    assert out["cuoi"] == {"tot": 105.0, "dat": 95.0, "da_de_nghi_kho": 0.0, "don_vi": "cái"}
    assert [l["id"] for l in out["lan_kiem"]] == [r2["kcs_batch_id"], res["kcs_batch_id"]]
    cu = out["lan_kiem"][1]
    assert cu["so_dat"] == 90 and cu["so_loi"] == 10 and cu["nguoi_kiem"] == res["nguoi_kcs"].name
    assert cu["loi"][0]["mo_ta"] == "Lem mực" and cu["loi"][0]["da_xem_luc"] is None
    assert cu["loi"][0]["anh"][0]["file_name"] == "loi.jpg"

    # Người của tổ xem theo phạm vi Xem của dòng quyền theo tổ.
    assert kcs.ket_qua_kcs_cong_viec(db, _nguoi_o_to(db, to, "doc_tron"), cv.id)["lan_kiem"]
    with pytest.raises(PermissionError):
        kcs.ket_qua_kcs_cong_viec(db, _nguoi_o_to(db, to, "doc_cua_toi", scope=SCOPE_OWN), cv.id)
    _to2, ngoai = _to_chiu(db)
    with pytest.raises(PermissionError):
        kcs.ket_qua_kcs_cong_viec(db, ngoai, cv.id)


def test_chuoi_cong_doan_kcs(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True, tot=100)
    with pytest.raises(PermissionError):
        kcs.chuoi_cong_doan_kcs(db, admin, cv.lsx_id)
    with pytest.raises(ValueError):
        kcs.chuoi_cong_doan_kcs(db, res["nguoi_kcs"], 999_999)

    out = kcs.chuoi_cong_doan_kcs(db, res["nguoi_kcs"], cv.lsx_id)
    assert out["lsx"]["id"] == cv.lsx_id and out["lsx"]["ma"] == res["lsx_ma"]
    dong = next(c for c in out["cong_doan"] if c["cong_viec_id"] == cv.id)
    assert dong["to_id"] == to.id and dong["to_ten"] == to.name and dong["la_kcs_cuoi"] is True
    assert dong["tot"] == 100 and dong["so_lan_kiem"] == 1
    assert dong["tong_dat"] == 90 and dong["tong_loi"] == 10
    assert dong["da_yeu_cau_kho"] == 0 and dong["con_gui_kho"] == 90
    assert dong["lan_kiem"][0]["id"] == res["kcs_batch_id"]

    kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv.id)
    dong = next(c for c in kcs.chuoi_cong_doan_kcs(db, res["nguoi_kcs"], cv.lsx_id)["cong_doan"]
                if c["cong_viec_id"] == cv.id)
    assert dong["da_yeu_cau_kho"] == 90 and dong["con_gui_kho"] == 0
    [yc] = dong["yeu_cau_kho"]
    assert yc["trang_thai"] == REQ_APPROVED and yc["sl_de_nghi"] == 90 and yc["sl_da_nhan"] == 0


def test_chuoi_cong_doan_kcs_kem_boi_canh_form_kiem(db, orders, lsx_svc, admin, customer):
    """Form kiểm bày kế hoạch, máy, dặn dò, quy cách và các mẻ tổ đã ghi (mới nhất trước)."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True, tot=100)
    may = MayThietBi(ma="MAY-KCS-1", ten="Máy bế 1", loai_may="be")
    db.add(may)
    db.flush()
    cv.may_id = may.id
    cv.ghi_chu = "Bế sát mép, không xơ"
    cv.quy_cach_json = {"giay": "C300", "so_mau": 4}
    cv.so_luong_ra = 1200
    moi = _ghi_tot(db, cv, 30)
    moi.bat_dau, moi.ket_thuc, moi.created_by = _T1, _T1 + timedelta(hours=1), admin.id
    moi.ten_khoan_snapshot = "Bế hộp"
    db.commit()

    dong = next(c for c in kcs.chuoi_cong_doan_kcs(db, res["nguoi_kcs"], cv.lsx_id)["cong_doan"]
                if c["cong_viec_id"] == cv.id)
    assert dong["so_luong_ra"] == 1200 and dong["may"] == "Máy bế 1"
    assert dong["ghi_chu_ky_thuat"] == "Bế sát mép, không xơ"
    assert dong["quy_cach"] == {"giay": "C300", "so_mau": 4}
    assert [m["so_luong"] for m in dong["me"]] == [30, 100]
    dau = dong["me"][0]
    assert dau["id"] == moi.id and dau["viec"] == "Bế hộp" and dau["nguoi_ghi"] == admin.name
    assert dau["nguoi"] == [] and dau["don_vi"] == cv.don_vi_ra


def test_danh_sach_lenh_kcs(db, orders, lsx_svc, admin, customer):
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    with pytest.raises(PermissionError):
        kcs.danh_sach_lenh_kcs(db, admin)

    out = kcs.danh_sach_lenh_kcs(db, res["nguoi_kcs"], gom_da_dong=True)
    assert out["trang"] == 1 and out["tong"] >= 1
    dong = next(i for i in out["items"] if i["lsx_id"] == cv.lsx_id)
    assert dong["ma"] == res["lsx_ma"] and dong["so_da_kiem"] == 1 and dong["so_loi"] == 10
    assert dong["so_cong_doan"] >= 1

    tim = kcs.danh_sach_lenh_kcs(db, res["nguoi_kcs"], tim=res["lsx_ma"], gom_da_dong=True)
    assert [i["lsx_id"] for i in tim["items"]] == [cv.lsx_id]
    assert kcs.danh_sach_lenh_kcs(db, res["nguoi_kcs"], tim="KHONG-CO-LENH-NAY",
                                  gom_da_dong=True)["items"] == []


# --- Nhập kho từ công đoạn cuối -------------------------------------------------------------
def test_nhap_kho_chi_cong_doan_cuoi_va_chi_nguoi_kcs(db, orders, lsx_svc, admin, customer):
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError, match="công đoạn cuối"):
        kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv.id)
    cv.la_kcs_cuoi = True
    db.commit()
    with pytest.raises(PermissionError):
        kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=admin, cong_viec_id=cv.id)
    assert db.query(StockRequest).filter_by(san_xuat_cong_viec_id=cv.id).count() == 0


def test_nhap_kho_lay_phan_dat_chua_gui_roi_het_so(db, orders, lsx_svc, admin, customer):
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True, tot=120)
    nguoi = res["nguoi_kcs"]

    r1 = kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=nguoi, cong_viec_id=cv.id)
    assert r1["so_luong"] == 90 and r1["cong_viec_id"] == cv.id and len(r1["dong"]) == 1
    yc = db.get(StockRequest, r1["request_id"])
    assert yc.san_xuat_cong_viec_id == cv.id and yc.trang_thai == REQ_APPROVED
    with pytest.raises(kho.KhongConSoDuGuiKho):
        kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=nguoi, cong_viec_id=cv.id)

    kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=cv.id, so_dat=20)
    moi = kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=nguoi, cong_viec_id=cv.id)
    assert moi["so_luong"] == 20 and moi["request_id"] != r1["request_id"]

    # Kho huỷ yêu cầu thì phần đó gửi lại được.
    _huy_boi_kho(db, r1["request_id"])
    lai = kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=nguoi, cong_viec_id=cv.id)
    assert lai["so_luong"] == 90


def test_nhap_kho_tran_theo_tot_hien_tai(db, orders, lsx_svc, admin, customer):
    """Tổ sửa mẻ xuống sau khi KCS đã kiểm — số gửi kho không vượt số tốt còn lại."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=80, khong_dat=0, cuoi=True, tot=100)
    me = db.query(SanXuatBatch).filter_by(cong_viec_id=cv.id).one()
    me.tot = 60
    me.tong = 60
    db.commit()
    r = kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv.id)
    assert r["so_luong"] == 60


# --- Migration 0306 -------------------------------------------------------------------------
@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 35), reason="SQLite cũ không DROP COLUMN")
def test_migration_0306_nan_loi_cu_va_bo_cot(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    cot_cu = (
        ("role_permissions", "can_qc", "BOOLEAN NOT NULL DEFAULT 0"),
        ("san_xuat_cong_viec", "la_kcs", "BOOLEAN NOT NULL DEFAULT 0"),
        ("san_xuat_kcs_batch", "loai", "VARCHAR(16) NOT NULL DEFAULT 'routing'"),
        ("san_xuat_kcs_batch", "kcs_department_id", "INTEGER"),
        ("san_xuat_kcs_batch", "batch_id", "INTEGER"),
        ("san_xuat_kcs_loi", "trang_thai", "VARCHAR(16) NOT NULL DEFAULT 'pending'"),
        ("san_xuat_kcs_loi", "ly_do_tu_choi", "VARCHAR(500)"),
    )
    for bang, ten, kieu in cot_cu:
        db.execute(text(f"ALTER TABLE {bang} ADD COLUMN {ten} {kieu}"))
    db.execute(text("CREATE INDEX ix_san_xuat_kcs_batch_batch_id ON san_xuat_kcs_batch (batch_id)"))
    # Lỗi kiểu cũ: tổ chịu chọn tay (trống), chưa neo công đoạn, chưa ai phản hồi.
    db.execute(text(
        "UPDATE san_xuat_kcs_loi SET to_chiu_id = NULL, cong_doan_ref_id = NULL, phan_hoi_luc = NULL "
        "WHERE id = :i"), {"i": res["loi_id"]})
    db.commit()

    _migrate_kcs_theo_lenh(db)
    _migrate_kcs_theo_lenh(db)  # chạy lại vô hại

    insp = inspect(db.get_bind())
    for bang, ten, _kieu in cot_cu:
        assert ten not in {c["name"] for c in insp.get_columns(bang)}, (bang, ten)
    row = db.execute(text(
        "SELECT to_chiu_id, cong_doan_ref_id, phan_hoi_luc, created_at FROM san_xuat_kcs_loi "
        "WHERE id = :i"), {"i": res["loi_id"]}).one()
    assert row[0] == to.id and row[1] == cv.id and row[2] is not None and row[2] == row[3]


# --- Đường dây HTTP -------------------------------------------------------------------------
def test_api_kiem_can_dang_nhap(client):
    assert client.post("/api/san-xuat/kcs/cong-viec/1/kiem", data={"so_dat": "1"}).status_code == 401
    assert client.get("/api/san-xuat/kcs/lenh").status_code == 401


def test_api_kiem_admin_khong_thuoc_to_kcs_403(client):
    """Admin seed không đứng trong phòng ban `is_kcs` nào → service chặn trước khi lưu ảnh."""
    tok = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    resp = client.post(
        "/api/san-xuat/kcs/cong-viec/1/kiem",
        data={"so_dat": "5", "so_loi": "1", "loi_mo_ta": "Lem mực"},
        files={"files": ("loi.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        headers=h,
    )
    assert resp.status_code == 403
    assert client.get("/api/san-xuat/kcs/lenh", headers=h).status_code == 403
    me = client.get("/api/auth/permissions", headers=h)
    if me.status_code == 200:
        assert me.json()["kcs"] is False and me.json()["truong_kcs"] is False


def test_api_kiem_dong_loi_so_anh_khong_khop_400(client):
    """`loi_json` khai số ảnh từng dòng; tổng không khớp số tệp gửi lên thì chặn ngay, chưa lưu ảnh."""
    tok = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]
    resp = client.post(
        "/api/san-xuat/kcs/cong-viec/1/kiem",
        data={"loi_json": '[{"cong_viec_id": 1, "so_luong": 2, "mo_ta": "Lem", "so_anh": 2}]'},
        files={"files": ("loi.png", b"PNG-anh", "image/png")},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 400


# --- Quy lỗi về công đoạn TRƯỚC (19/09/2026) ------------------------------------------------
def _chuoi_hai_to(db, orders, lsx_svc, admin, customer, ma):
    """Lệnh hai công đoạn: công đoạn fixture (TRƯỚC, chuyển sang tổ chịu lỗi) + một bước "Đóng gói"
    thêm vào CUỐI routing (SAU, tổ gốc). Trả (cv_truoc, cv_sau, tổ chịu, tổ trưởng tổ chịu, người
    KCS). `cv_sau` ghi sẵn 100 tốt."""
    to, truoc = _cv_kcs(db, orders, lsx_svc, admin, customer, ma=ma)
    _d, nguoi = _to_kiem(db, ten=f"Tổ KCS {ma}", ma=f"{ma}-KCS")
    to_chiu, tt = _to_chiu(db, ten=f"Tổ in {ma}", ma=f"{ma}-IN")
    truoc.department_id = to_chiu.id
    cuoi_tt = max(c.thu_tu for c in db.query(LsxCongDoan).filter_by(lsx_id=truoc.lsx_id))
    cd = LsxCongDoan(lsx_id=truoc.lsx_id, thu_tu=cuoi_tt + 100, ten="Đóng gói", nhom="finishing")
    db.add(cd)
    db.flush()
    sau = SanXuatCongViec(
        goi_id=truoc.goi_id, lsx_id=truoc.lsx_id, lsx_cong_doan_id=cd.id, step_key=cd.step_key,
        phan_doan_so=1, phan_doan_tong=1, ten_cong_doan=cd.ten, trang_thai=CV_DANG_CHAY,
        department_id=to.id, don_vi_ra="cái", don_vi_vao="cái", la_kcs_cuoi=True,
    )
    db.add(sau)
    db.commit()
    ds = [c["cong_viec_id"] for c in kcs.chuoi_cong_doan_kcs(db, nguoi, truoc.lsx_id)["cong_doan"]]
    assert ds.index(truoc.id) < ds.index(sau.id)
    _ghi_tot(db, sau, 100)
    return truoc, sau, to_chiu, tt, nguoi


def test_kiem_quy_loi_ve_cong_doan_truoc(db, orders, lsx_svc, admin, customer):
    truoc, sau, to_chiu, tt, nguoi = _chuoi_hai_to(db, orders, lsx_svc, admin, customer, "KCS-QL")
    res = kcs.kiem_cong_doan(
        db, user=nguoi, cong_viec_id=sau.id, lsx_id=sau.lsx_id or truoc.lsx_id,
        cac_loi=[
            {"cong_viec_id": truoc.id, "so_luong": 8, "mo_ta": "Lem mực", "anh": _anh()},
            {"cong_viec_id": None, "so_luong": 5, "mo_ta": "Móp góc", "anh": _anh()},
        ],
    )
    assert res["so_loi"] == 13 and res["so_dat"] == 87 and res["so_loi_cua_to"] == 5
    [m] = res["bao_loi_nguon"]
    assert m["cong_viec_id"] == truoc.id and m["department_id"] == to_chiu.id and m["so_loi"] == 8
    assert tt.id in m["notify_user_ids"]

    loi = {l.mo_ta: l for l in db.query(SanXuatKcsLoi).filter_by(kcs_batch_id=res["kcs_batch_id"])}
    assert loi["Lem mực"].to_chiu_id == to_chiu.id and loi["Lem mực"].cong_doan_ref_id == truoc.id
    assert loi["Móp góc"].to_chiu_id == sau.department_id and loi["Móp góc"].cong_doan_ref_id == sau.id

    # Tổ chịu thấy lỗi gắn vào CÔNG ĐOẠN CỦA MÌNH, kèm bước KCS bắt.
    [cho] = kcs.loi_cho_xem(db, [to_chiu.id])
    assert cho["cong_viec_id"] == truoc.id and cho["ten_cong_doan"] == truoc.ten_cong_doan
    assert cho["phat_hien_o"] == sau.ten_cong_doan and cho["so_luong"] == 8
    # Ô "chờ xác nhận" trên bàn tổ chịu: lệnh còn lại đúng công đoạn chịu lỗi, không lọc ra trắng.
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService as _Az
    from app.services.san_xuat import board

    loc = board.work_items(db, tt, _Az(RoleRepository(db)), team_id=to_chiu.id, cho_xac_nhan=True)
    assert [[w["id"] for w in l["cong_viec"]] for l in loc["lenh"]] == [[truoc.id]]

    # Tab KCS của công đoạn trước: lần kiểm ở bước sau, chỉ mang lỗi của mình.
    kq = kcs.ket_qua_kcs_cong_viec(db, nguoi, truoc.id)
    [lk] = kq["lan_kiem_buoc_sau"]
    assert lk["cong_doan_ten"] == sau.ten_cong_doan and [l["mo_ta"] for l in lk["loi"]] == ["Lem mực"]
    assert lk["loi"][0]["cong_doan_id"] == truoc.id and lk["loi"][0]["to_chiu_ten"] == to_chiu.name

    # Chuỗi công đoạn: số lượng vẫn tính ở bước bắt, bước trước có dòng "bắt ở bước sau".
    ds = {c["cong_viec_id"]: c for c in kcs.chuoi_cong_doan_kcs(db, nguoi, truoc.lsx_id)["cong_doan"]}
    assert ds[sau.id]["tong_loi"] == 13 and ds[truoc.id]["tong_loi"] == 0
    assert ds[truoc.id]["loi_buoc_sau"] == [
        {"phat_hien_o": sau.ten_cong_doan, "don_vi": sau.don_vi_ra, "so_luong": 8.0}
    ]
    assert ds[sau.id]["loi_buoc_sau"] == []

    # Bảng xếp hạng lỗi theo tổ quy trách nhiệm về tổ chịu.
    from app.services.rbac_service import AuthorizationService
    from app.services.san_xuat import kcs_bao_cao

    bc = kcs_bao_cao.bao_cao_kcs(db, nguoi, AuthorizationService(db))
    theo_to = {r["to_id"]: r["tong_so_luong"] for r in bc["to"]}
    assert theo_to[to_chiu.id] == 8 and theo_to[sau.department_id] == 5


def test_kiem_quy_loi_chan_sai(db, orders, lsx_svc, admin, customer):
    truoc, sau, _to_chiu_, _tt, nguoi = _chuoi_hai_to(db, orders, lsx_svc, admin, customer, "KCS-QS")
    _ghi_tot(db, truoc, 50)
    lid = truoc.lsx_id

    # Không quy lỗi về công đoạn đứng SAU.
    with pytest.raises(ValueError, match="đứng trước"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=truoc.id, lsx_id=lid, cac_loi=[
            {"cong_viec_id": sau.id, "so_luong": 1, "mo_ta": "x", "anh": _anh()}])
    # Dòng thiếu ảnh / thiếu mô tả / số 0.
    with pytest.raises(ValueError, match="ảnh"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=sau.id, lsx_id=lid, cac_loi=[
            {"cong_viec_id": truoc.id, "so_luong": 1, "mo_ta": "x", "anh": []}])
    with pytest.raises(ValueError, match="mô tả"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=sau.id, lsx_id=lid, cac_loi=[
            {"cong_viec_id": truoc.id, "so_luong": 1, "mo_ta": " ", "anh": _anh()}])
    with pytest.raises(ValueError, match="lớn hơn 0"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=sau.id, lsx_id=lid, cac_loi=[
            {"cong_viec_id": truoc.id, "so_luong": 0, "mo_ta": "x", "anh": _anh()}])
    # Tổng dòng lệch số lỗi gửi kèm.
    with pytest.raises(ValueError, match="Tổng các dòng"):
        kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=sau.id, lsx_id=lid, so_loi=3, cac_loi=[
            {"cong_viec_id": truoc.id, "so_luong": 1, "mo_ta": "x", "anh": _anh()}])
    assert db.query(SanXuatKcsBatch).count() == 0


def test_dieu_chinh_chan_doi_tong_khi_loi_chia_nhieu_cong_doan(db, orders, lsx_svc, admin, customer):
    truoc, sau, _to_chiu_, _tt, nguoi = _chuoi_hai_to(db, orders, lsx_svc, admin, customer, "KCS-QD")
    res = kcs.kiem_cong_doan(db, user=nguoi, cong_viec_id=sau.id, lsx_id=truoc.lsx_id, cac_loi=[
        {"cong_viec_id": truoc.id, "so_luong": 4, "mo_ta": "Lem", "anh": _anh()},
        {"cong_viec_id": sau.id, "so_luong": 6, "mo_ta": "Móp", "anh": _anh()},
    ])
    with pytest.raises(ValueError, match="nhiều công đoạn"):
        kcs.dieu_chinh_ket_qua(db, user=nguoi, kcs_batch_id=res["kcs_batch_id"], so_luong_dat=92,
                               so_luong_khong_dat=8, expected_version=res["version"])
    # Giữ nguyên tổng lỗi thì vẫn sửa được phần khác (ghi chú).
    kq = kcs.dieu_chinh_ket_qua(db, user=nguoi, kcs_batch_id=res["kcs_batch_id"], so_luong_dat=90,
                                so_luong_khong_dat=10, ghi_chu="soát lại",
                                expected_version=res["version"])
    assert kq["so_luong_khong_dat"] == 10
    assert sorted(float(l.so_luong) for l in db.query(SanXuatKcsLoi)
                  .filter_by(kcs_batch_id=res["kcs_batch_id"])) == [4.0, 6.0]
