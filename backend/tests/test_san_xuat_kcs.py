"""Thực hiện sản xuất — Giai đoạn 5 (KCS): batch kiểm tra · lỗi · phản hồi trách nhiệm (§13).

Soi tầng service `services/san_xuat/kcs.py` (nơi chứa LUẬT), không qua HTTP:
  · §13.1 `so_luong_nhan = dat + khong_dat`; NĂNG SUẤT KCS lấy nền theo `so_luong_nhan` → đẻ kèm
    một `san_xuat_batch` (`tot = nhan`, `hong = 0`) để tái dùng NGUYÊN pipeline phân bổ; kết luận
    suy từ số (đạt / đạt một phần / không đạt);
  · chỉ ghi cho công việc KCS (`la_kcs`) đã khởi động; GATE = quyền KCS (`qc`) trên dòng quyền theo
    tổ của tổ chạy việc (mg 0302) — mức "Của tôi" chỉ ghi được việc đang giao cho mình;
  · §13.2 mỗi lỗi ≥1 ảnh, nhóm lỗi phải thuộc nhóm `loi`; người giữ KCS TRỌN ở tổ BỊ yêu cầu (KHÁC
    tổ KCS) CHẤP NHẬN / TỪ CHỐI-kèm-lý-do — chung thẩm; lỗi chờ CHẶN đóng đủ nhóm (§16);
  · kiểm đột xuất / điểm kiểm và điều chỉnh của chúng hỏi KCS TRỌN ở TỔ ĐI KIỂM — "đứng trong tổ"
    hay "đứng tên tổ trưởng" không còn là quyền;
  · hai test API cuối chứng minh đường dây HTTP: chưa đăng nhập → 401; multipart ảnh + admin
    (vai không bật KCS ở tổ nào) → 403.

Tái dùng dàn cảnh (đơn → SX → phát hành vào một tổ khoán) từ test sản lượng / thực thi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.department import Department
from app.models.kho_hang import KhoHang
from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.models.san_xuat import (
    CV_DANG_CHAY,
    CV_HOAN_THANH,
    CV_PHAT_HANH,
    CV_TAM_DUNG,
    SanXuatCongViec,
)
from app.models.san_xuat_kcs import (
    KCS_DAT,
    KCS_DAT_MOT_PHAN,
    KCS_KHONG_DAT,
    KCS_LOAI_DOT_XUAT,
    KCS_LOAI_ROUTING,
    TN_CHAP_NHAN,
    TN_CHO,
    TN_RECORDED,
    TN_TU_CHOI,
    SanXuatKcsBatch,
    SanXuatKcsLoi,
    SanXuatKcsLoiAnh,
)
from app.models.san_xuat_kho import YC_CHO_KHO, YC_DA_NHAP, YC_MOT_PHAN
from app.models.san_xuat_san_luong import BG_DE_XUAT, BG_XAC_NHAN, SanXuatBanGiao, SanXuatBatch
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from app.repositories.san_xuat_kho_repo import SanXuatKhoRepository
from app.services.san_xuat import kcs, kho, thuc_thi
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


def _cv_kcs(db, orders, lsx_svc, admin, customer, ma="TO-KCS"):
    """Một tổ khoán + một công việc KCS ĐANG CHẠY, có đơn vị ra để ghi batch kiểm tra."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.la_kcs = True
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "cái"
    cv.don_vi_vao = "cái"
    db.commit()
    return to, cv


def _to_chiu(db, ten="Tổ Bế Bị Đổ", ma="TO-CHIU") -> tuple[Department, User]:
    """Một tổ SX khác + MỘT người được bật đủ quyền (có KCS) trên TRỌN tổ đó — để soi gate phản hồi
    lỗi = người giữ KCS ở tổ BỊ yêu cầu. Người này không đứng tên tổ trưởng: `head_user_id` không
    còn là quyền."""
    u = User(username=f"tt_{ma.lower()}", name="Tổ Trưởng Bế", password_hash="x")
    db.add(u)
    db.flush()
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    cap_quyen_to(db, u, d)
    return d, u


def _nguoi_o_to(db, dept, username, *, scope: str | None = SCOPE_ALL, viec=("qc",)) -> User:
    """Một tài khoản ĐỨNG TRONG tổ `dept` (`department_id` trỏ tổ) + dòng quyền theo tổ của `dept`:
    bật Xem + `viec` với phạm vi `scope`. `scope=None` = không cấp gì — thành viên thường."""
    u = User(username=username, name=f"Người {username}", password_hash="x", department_id=dept.id)
    db.add(u)
    db.flush()
    if scope is not None:
        cap_quyen_to(db, u, dept, scope=scope, viec=viec)
    db.commit()
    return u


class _Authz:
    """Stub tham số `authz` của service đọc. Tham số còn trong chữ ký nhưng KHÔNG còn quyết định phạm
    vi — phạm vi nay do dòng quyền theo tổ của vai quyết định (mg 0302), nên `scope` ở đây vô tác
    dụng; muốn soi phạm vi thì cấp dòng thật bằng `cap_quyen_to`."""

    def __init__(self, scope: str | None = None) -> None:
        self._scope = scope

    def scope_for(self, user, module_key):  # noqa: D401 - stub
        return self._scope


def _anh() -> list[dict]:
    return [{"file_name": "loi.jpg", "file_url": "/api/files/san-xuat/kcs-loi/1/x_loi.jpg",
             "file_type": "image/jpeg"}]


def _batch(db, orders, lsx_svc, admin, customer, *, nhan=100, dat=90, khong_dat=10, ma="TO-KCS"):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, ma=ma)
    res = kcs.tao_batch_kcs(
        db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
        so_luong_nhan=nhan, so_luong_dat=dat, so_luong_khong_dat=khong_dat,
    )
    return to, cv, res


def _ban_giao(db, *, dich_cong_viec_id, so_luong, trang_thai=BG_XAC_NHAN):
    """Một dòng bàn giao TỚI công việc — dựng thẳng bằng ORM (test không cần đi qua flow bàn giao
    đầy đủ, chỉ cần đúng SHAPE mà `tong_ban_giao_xac_nhan` đọc). `nguon_cong_viec_id` không NULL
    được — dùng tạm cùng id với đích, test không quan tâm nguồn thật."""
    bg = SanXuatBanGiao(nguon_cong_viec_id=dich_cong_viec_id, dich_cong_viec_id=dich_cong_viec_id,
                         so_luong=so_luong, don_vi="cái", trang_thai=trang_thai)
    db.add(bg)
    db.flush()
    return bg


def _to_kiem(db, ten="Tổ Kiểm Đột Xuất", ma="TO-KIEM", *, quyen: bool = True) -> tuple[Department, User]:
    """Một tổ SX KHÁC được GIAO kiểm đột xuất + MỘT thành viên (`department_id` trỏ đúng tổ).

    Luật cũ "thành viên nào của tổ cũng ghi được" (`_gate_member`) đã gỡ: kiểm đột xuất / điểm kiểm
    đòi KCS (`qc`) trên TRỌN tổ đi kiểm. Nên mặc định thành viên này được bật ĐÚNG Xem + KCS phạm
    vi `all` ở tổ kiểm — không kèm quyền nào khác, không đứng tên tổ trưởng. `quyen=False` = thành
    viên thường chưa được cấp gì."""
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    u = User(username=f"tv_{ma.lower()}", name="Thành viên tổ kiểm", password_hash="x",
             department_id=d.id)
    db.add(u)
    db.flush()
    if quyen:
        cap_quyen_to(db, u, d, viec=("qc",))
    return d, u


def _to_kiem_truong(db, ten="Tổ Kiểm Đột Xuất TT", ma="TO-KIEM-TT") -> tuple[Department, User]:
    """Tổ đi kiểm đột xuất + MỘT người được bật đủ bốn quyền chi tiết trên TRỌN tổ đó (không đứng
    trong tổ, không đứng tên tổ trưởng) — dùng cho test gate điều chỉnh kết quả đột xuất."""
    u = User(username=f"tt_{ma.lower()}", name="Trưởng Tổ Kiểm", password_hash="x")
    db.add(u)
    db.flush()
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    cap_quyen_to(db, u, d)
    return d, u


def _cv_production(db, orders, lsx_svc, admin, customer, *, ma="TO-SX-DX", trang_thai=CV_DANG_CHAY):
    """Một công việc SẢN XUẤT THƯỜNG (`la_kcs=False`, KHÔNG qua `_cv_kcs`) đang chạy/tạm dừng —
    mục tiêu của kiểm đột xuất (mục 5: đột xuất KHÔNG đòi công việc phải là bước KCS)."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = trang_thai
    db.commit()
    return to, cv


# --- Batch kiểm tra (§13.1) -----------------------------------------------------------------
def test_tao_batch_de_kem_batch_san_luong_nen(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)

    kb = db.get(SanXuatKcsBatch, res["kcs_batch_id"])
    assert kb is not None and float(kb.so_luong_nhan) == 100
    assert float(kb.so_luong_dat) == 90 and float(kb.so_luong_khong_dat) == 10
    assert kb.ket_luan == KCS_DAT_MOT_PHAN and kb.don_vi == "cái"

    # Batch sản lượng nền: tot = số NHẬN (nền năng suất KCS §13.1), hong = 0 (không đạt là lỗi
    # SẢN PHẨM, không phải hỏng do KCS). Pipeline phân bổ đọc batch.tot → chạy nguyên.
    assert res["batch_id"] and kb.batch_id == res["batch_id"]
    b = db.get(SanXuatBatch, res["batch_id"])
    assert float(b.tong) == 100 and float(b.tot) == 100 and float(b.hong) == 0
    assert b.ghi_chu == "KCS" and b.cong_viec_id == cv.id


def test_ket_luan_dat_khi_khong_co_khong_dat(db, orders, lsx_svc, admin, customer):
    _to, _cv, r = _batch(db, orders, lsx_svc, admin, customer, nhan=50, dat=50, khong_dat=0)
    assert db.get(SanXuatKcsBatch, r["kcs_batch_id"]).ket_luan == KCS_DAT


def test_ket_luan_khong_dat_khi_khong_co_dat(db, orders, lsx_svc, admin, customer):
    _to, _cv, r = _batch(db, orders, lsx_svc, admin, customer, nhan=40, dat=0, khong_dat=40)
    assert db.get(SanXuatKcsBatch, r["kcs_batch_id"]).ket_luan == KCS_KHONG_DAT


def test_nhan_khac_dat_cong_khong_dat_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=100, so_luong_dat=80, so_luong_khong_dat=10,   # 80 + 10 ≠ 100
        )


def test_co_mau_khong_vuot_so_nhan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=100, so_luong_dat=100, so_luong_khong_dat=0, co_mau=120,
        )


def test_chi_cong_viec_kcs_moi_ghi_duoc(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-NOT-KCS")
    cv.la_kcs = False                                    # công việc thường, không KCS
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "cái"
    db.commit()
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        )


def test_chua_bat_dau_khong_ghi_duoc(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-KCS-CHUA")
    cv.la_kcs = True
    cv.don_vi_ra = "cái"
    db.commit()                                          # vẫn 'released'
    assert cv.trang_thai == CV_PHAT_HANH
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        )


def test_gate_ghi_batch_kcs_doi_quyen_kcs_o_to(db, orders, lsx_svc, admin, customer):
    """Ghi batch KCS routing đòi quyền KCS ở tổ chạy việc: có đủ ba quyền chi tiết còn lại mà thiếu
    KCS vẫn bị chặn; KCS mức "Của tôi" chỉ ghi được khi việc đang giao cho chính mình."""
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    kw = dict(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
              so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0)

    nguoi_la = SimpleNamespace(id=admin.id + 99_999)               # tài khoản không tồn tại
    with pytest.raises(PermissionError):
        kcs.tao_batch_kcs(db, user=nguoi_la, **kw)

    khong_kcs = _nguoi_o_to(db, to, "kcs_thieu_qc",
                            viec=("run_order", "confirm_output", "warehouse"))
    with pytest.raises(PermissionError, match="KCS"):
        kcs.tao_batch_kcs(db, user=khong_kcs, **kw)

    cua_toi = _nguoi_o_to(db, to, "kcs_cua_toi", scope=SCOPE_OWN)
    with pytest.raises(PermissionError):                            # chưa được giao việc này
        kcs.tao_batch_kcs(db, user=cua_toi, **kw)
    nv = _emp(db, to, "NV-KCS-OWN", user_id=cua_toi.id)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=nv.id)
    assert kcs.tao_batch_kcs(db, user=cua_toi, **kw)["kcs_batch_id"]


# --- KCS kiêm nhiệm (mg 0250) — chặn tổng vượt bàn giao trên ROUTING (mục 2-4) ---------------
def test_routing_nhieu_dot_cong_don_cung_cong_viec(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    _ban_giao(db, dich_cong_viec_id=cv.id, so_luong=100)
    kcs.tao_batch_kcs(db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
                       so_luong_nhan=40, so_luong_dat=40, so_luong_khong_dat=0)
    kcs.tao_batch_kcs(db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
                       so_luong_nhan=30, so_luong_dat=30, so_luong_khong_dat=0)
    repo = SanXuatKcsRepository(db)
    batches = repo.cac_kcs_batch(cv.id)
    assert len(batches) == 2
    assert all(b.loai == KCS_LOAI_ROUTING for b in batches)    # mặc định "routing", KHÔNG set tay


def test_routing_tong_cac_dot_vuot_ban_giao_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    _ban_giao(db, dich_cong_viec_id=cv.id, so_luong=50)
    kcs.tao_batch_kcs(db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
                       so_luong_nhan=40, so_luong_dat=40, so_luong_khong_dat=0)
    with pytest.raises(ValueError, match="vượt số đã bàn giao"):
        kcs.tao_batch_kcs(db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
                           so_luong_nhan=20, so_luong_dat=20, so_luong_khong_dat=0)


def test_routing_ban_giao_proposed_khong_tinh_vao_da_giao(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    _ban_giao(db, dich_cong_viec_id=cv.id, so_luong=100, trang_thai=BG_DE_XUAT)
    repo = SanXuatKcsRepository(db)
    assert repo.tong_ban_giao_xac_nhan(cv.id) == 0            # proposed CHƯA chốt → không tính
    res = kcs.tao_batch_kcs(db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
                             so_luong_nhan=100, so_luong_dat=100, so_luong_khong_dat=0)
    assert res["kcs_batch_id"]                                 # KHÔNG bị chặn


# --- KCS kiêm nhiệm (mg 0250) — checklist bắt buộc dùng CHUNG routing + đột xuất (mục 7) -----
_TIEU_CHI_BAT_BUOC = [{"tieu_chi_id": 1, "ma": "TC1", "ten": "x", "huong_dan": None,
                       "bat_buoc": True, "nguon": "danh_muc", "thu_tu": 1}]


def test_routing_checklist_bat_buoc_chan_khi_thieu_ket_qua(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    cv.kcs_tieu_chi_json = _TIEU_CHI_BAT_BUOC
    db.commit()
    with pytest.raises(ValueError, match="tiêu chí"):
        kcs.tao_batch_kcs(db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
                           so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0)
    res = kcs.tao_batch_kcs(
        db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
        so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        checklist_ket_qua=[{"thu_tu": 1, "dat": True}],
    )
    kb = db.get(SanXuatKcsBatch, res["kcs_batch_id"])
    assert kb.checklist_json == [{"thu_tu": 1, "dat": True}]


# --- Lỗi + ảnh (§13.2) ----------------------------------------------------------------------
def test_ghi_loi_kem_anh_va_neo_to_chiu(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    to2, tt2 = _to_chiu(db)
    _nguoi_o_to(db, to2, "kcs_own_to_chiu", scope=SCOPE_OWN)       # KCS "Của tôi" ở tổ chịu

    res = kcs.ghi_loi(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"],
        mo_ta="Lem mực mép trái", to_chiu_id=to2.id, so_luong=6, anh=_anh(),
    )

    loi = db.get(SanXuatKcsLoi, res["loi_id"])
    assert loi.trang_thai == TN_RECORDED and loi.to_chiu_id == to2.id
    assert loi.mo_ta == "Lem mực mép trái" and float(loi.so_luong) == 6
    # Đẩy SSE tới người giữ KCS TRỌN ở tổ BỊ yêu cầu — không tới admin (KCS ở tổ ghi lỗi, không
    # có dòng ở tổ chịu), không tới người chỉ có KCS "Của tôi" (không nhận thông báo cấp tổ).
    assert res["notify_user_ids"] == [tt2.id]
    anh = db.query(SanXuatKcsLoiAnh).filter_by(loi_id=loi.id).all()
    assert len(anh) == 1 and anh[0].file_name == "loi.jpg"


def test_ghi_loi_bat_buoc_it_nhat_mot_anh(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):
        kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"], anh=[])


def test_xoa_anh_giu_it_nhat_mot(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    res = kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"], anh=_anh())  # đúng 1 ảnh
    anh = db.query(SanXuatKcsLoiAnh).filter_by(loi_id=res["loi_id"]).first()
    with pytest.raises(ValueError):                        # xoá ảnh cuối → chặn
        kcs.xoa_anh_loi(db, user=admin, anh_id=anh.id)


def test_them_roi_xoa_anh(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    res = kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"], anh=_anh())
    them = kcs.them_anh_loi(db, user=admin, loi_id=res["loi_id"], anh=[
        {"file_name": "loi2.jpg", "file_url": "/api/files/san-xuat/kcs-loi/1/y.jpg",
         "file_type": "image/jpeg"}])
    assert them["so_anh"] == 2
    anh0 = db.query(SanXuatKcsLoiAnh).filter_by(loi_id=res["loi_id"]).first()
    out = kcs.xoa_anh_loi(db, user=admin, anh_id=anh0.id)   # còn 2 → xoá được
    assert out["file_url"] == anh0.file_url
    assert db.query(SanXuatKcsLoiAnh).filter_by(loi_id=res["loi_id"]).count() == 1


# --- Phản hồi trách nhiệm (§13.2) -----------------------------------------------------------
def _mot_loi(db, orders, lsx_svc, admin, customer):
    """Lỗi kiểu CŨ (trang_thai=pending), chèn thẳng qua model — dùng để test luồng phản hồi legacy
    (§7: hồ sơ cũ pending/accepted/rejected giữ nguyên để đọc lịch sử). KHÔNG qua `kcs.ghi_loi()`
    vì lỗi MỚI ghi `recorded`, không còn đi vào trạng thái `pending` nữa (Task 11.5)."""
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    to2, tt2 = _to_chiu(db)
    loi = SanXuatKcsLoi(
        kcs_batch_id=rb["kcs_batch_id"], mo_ta="Bong tróc mực", to_chiu_id=to2.id,
        so_luong=6, don_vi="cái", trang_thai=TN_CHO, created_by=admin.id,
    )
    db.add(loi)
    db.flush()
    db.add(SanXuatKcsLoiAnh(loi_id=loi.id, file_name="loi.jpg",
                             file_url="/api/files/san-xuat/kcs-loi/1/x_loi.jpg",
                             file_type="image/jpeg", uploaded_by=admin.id))
    db.commit()
    return cv, loi.id, to2, tt2


def test_phan_hoi_chap_nhan(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    res = kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    assert res["trang_thai"] == TN_CHAP_NHAN
    loi = db.get(SanXuatKcsLoi, loi_id)
    assert loi.phan_hoi_by_id == tt2.id and loi.ly_do_tu_choi is None


def test_phan_hoi_tu_choi_bat_buoc_ly_do(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):                        # từ chối mà không nêu lý do
        kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=False, ly_do_tu_choi="")
    res = kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=False,
                           ly_do_tu_choi="Do khâu in, không phải tổ tôi")
    assert res["trang_thai"] == TN_TU_CHOI
    assert db.get(SanXuatKcsLoi, loi_id).ly_do_tu_choi == "Do khâu in, không phải tổ tôi"


def test_phan_hoi_gate_dung_to_bi_yeu_cau(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    # admin giữ KCS ở tổ ghi lỗi, KHÔNG có dòng quyền ở tổ bị yêu cầu → không được phản hồi.
    with pytest.raises(PermissionError):
        kcs.phan_hoi_loi(db, user=admin, loi_id=loi_id, chap_nhan=True)
    # Đứng trong tổ bị yêu cầu, có KCS nhưng chỉ mức "Của tôi" → phản hồi thay cả tổ không được.
    cua_toi = _nguoi_o_to(db, to2, "kcs_own_phan_hoi", scope=SCOPE_OWN)
    with pytest.raises(PermissionError):
        kcs.phan_hoi_loi(db, user=cua_toi, loi_id=loi_id, chap_nhan=True)
    assert db.get(SanXuatKcsLoi, loi_id).trang_thai == TN_CHO


def test_phan_hoi_chung_tham(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    with pytest.raises(ValueError):                        # đã phản hồi → chung thẩm
        kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=False,
                         ly_do_tu_choi="đổi ý")


# --- Đọc: chi tiết + hộp thư + trần đóng nhóm (§13, §16) -------------------------------------
def test_chi_tiet_kcs_gom_batch_loi_anh(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    ct = kcs.chi_tiet_kcs(db, admin, _Authz(), cv.id)
    assert ct["la_kcs"] is True and len(ct["batch"]) == 1
    b0 = ct["batch"][0]
    assert b0["so_luong_nhan"] == 100 and len(b0["loi"]) == 1
    assert b0["loi"][0]["trang_thai"] == TN_CHO and len(b0["loi"][0]["anh"]) == 1
    assert b0["loi"][0]["mo_ta"] == "Bong tróc mực"


def test_chi_tiet_kcs_chi_can_xem_khong_can_quyen_kcs(db, orders, lsx_svc, admin, customer):
    """Người chỉ được bật XEM trọn tổ (không một quyền chi tiết nào — quản đốc theo dõi) vẫn phải xem
    được chi tiết KCS.

    Mặt đọc này gác bằng Xem của dòng quyền theo tổ, cùng phạm vi `/work-items/{id}`. Trước đây nó
    từng gác bằng cổng GHI nên người không đứng tên tổ mở trang KCS là 403 hàng loạt trong khi
    `/work-items?mode=kcs` ngay cạnh vẫn liệt kê đúng những việc đó.
    """
    cv, _loi_id, _to2, _tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    to = db.get(Department, cv.department_id)
    quan_doc = _nguoi_o_to(db, to, "quan_doc_chi_xem", viec=())

    ct = kcs.chi_tiet_kcs(db, quan_doc, _Authz(), cv.id)
    assert ct["cong_viec_id"] == cv.id and len(ct["batch"]) == 1
    with pytest.raises(PermissionError):                   # xem được ≠ ghi được
        kcs.tao_batch_kcs(db, user=quan_doc, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
                          so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0)


def test_chi_tiet_kcs_van_chan_khi_ngoai_pham_vi_to(db, orders, lsx_svc, admin, customer):
    """Cổng ĐỌC không mở toang: có đủ quyền ở tổ KHÁC vẫn bị chặn; Xem mức "Của tôi" ở chính tổ chỉ
    mở được việc đang giao cho mình."""
    cv, _loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    with pytest.raises(PermissionError):                   # tt2 chỉ có dòng ở tổ chịu
        kcs.chi_tiet_kcs(db, tt2, _Authz(), cv.id)

    to = db.get(Department, cv.department_id)
    tho = _nguoi_o_to(db, to, "tho_xem_cua_toi", scope=SCOPE_OWN, viec=())
    with pytest.raises(PermissionError):                   # chưa được giao việc này
        kcs.chi_tiet_kcs(db, tho, _Authz(), cv.id)
    nv = _emp(db, to, "NV-XEM-OWN", user_id=tho.id)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=nv.id)
    assert kcs.chi_tiet_kcs(db, tho, _Authz(), cv.id)["cong_viec_id"] == cv.id


def test_hop_thu_loi_theo_quyen_kcs_to_bi_yeu_cau(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    hop = kcs.hop_thu_loi(db, tt2)                         # giữ KCS trọn ở tổ bị yêu cầu
    assert [l["id"] for l in hop] == [loi_id]
    assert kcs.hop_thu_loi(db, admin) == []                # admin không có dòng ở tổ bị yêu cầu
    cua_toi = _nguoi_o_to(db, to2, "kcs_own_hop_thu", scope=SCOPE_OWN)
    assert kcs.hop_thu_loi(db, cua_toi) == []              # KCS "Của tôi" không nhận thư cấp tổ
    kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    assert kcs.hop_thu_loi(db, tt2) == []                  # đã phản hồi → rời hộp thư


def test_loi_cho_chan_dong_du_nhom(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    repo = SanXuatKcsRepository(db)
    assert repo.co_loi_chua_tra_loi(cv.nhom_id) is True    # còn lỗi chờ → chặn (§16)
    kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    assert repo.co_loi_chua_tra_loi(cv.nhom_id) is False   # hết chờ → mở


# --- KCS kiêm nhiệm (mg 0250): kiểm ĐỘT XUẤT, không đứng sẵn trong routing -------------------
def test_dot_xuat_khong_can_cong_viec_la_kcs(db, orders, lsx_svc, admin, customer):
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    assert cv.la_kcs is False                              # việc production BÌNH THƯỜNG

    res = kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        don_vi="cái",
    )
    kb = db.get(SanXuatKcsBatch, res["kcs_batch_id"])
    assert kb.loai == KCS_LOAI_DOT_XUAT and kb.kcs_department_id == to_kiem.id
    assert cv.la_kcs is False                              # vẫn KHÔNG đổi (mục 5)


def test_dot_xuat_khong_tao_san_xuat_batch(db, orders, lsx_svc, admin, customer):
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    truoc = db.query(SanXuatBatch).count()

    res = kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        don_vi="cái",
    )
    assert db.query(SanXuatBatch).count() == truoc         # KHÔNG đẻ kèm batch sản lượng (mục 6)
    assert res["batch_id"] is None


def test_dot_xuat_checklist_bat_buoc_dung_chung_ham_validate(db, orders, lsx_svc, admin, customer):
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    cv.kcs_tieu_chi_json = _TIEU_CHI_BAT_BUOC
    db.commit()

    with pytest.raises(ValueError, match="tiêu chí"):
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
            don_vi="cái",
        )
    res = kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        don_vi="cái", checklist_ket_qua=[{"thu_tu": 1, "dat": True}],
    )
    assert res["kcs_batch_id"]


def test_dot_xuat_khong_dat_bat_buoc_anh(db, orders, lsx_svc, admin, customer):
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)

    with pytest.raises(ValueError, match="ảnh bằng chứng"):
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=5, so_luong_khong_dat=5,
            don_vi="cái", anh=None,
        )
    res = kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=5, so_luong_khong_dat=5,
        don_vi="cái", anh=_anh(),
    )
    assert res["loi_id"] is not None
    repo = SanXuatKcsRepository(db)
    assert repo.loi(res["loi_id"]) is not None


def test_routing_khong_bi_doi_hoi_anh_khi_khong_dat(db, orders, lsx_svc, admin, customer):
    """Routing GIỮ NGUYÊN flow 2 bước — batch cũ `khong_dat=10` không kèm lỗi vẫn PASS (Ruling 2:
    y hệt `test_ket_luan_khong_dat_khi_khong_co_dat`, chạy lại để xác nhận KHÔNG bị retrofit)."""
    _to, _cv, r = _batch(db, orders, lsx_svc, admin, customer, nhan=40, dat=0, khong_dat=40)
    assert db.get(SanXuatKcsBatch, r["kcs_batch_id"]).ket_luan == KCS_KHONG_DAT


def test_dot_xuat_luat_so_khong_am_va_tong_khop(db, orders, lsx_svc, admin, customer):
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)

    with pytest.raises(ValueError):                        # số lượng nhận âm
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=-10, so_luong_dat=-10, so_luong_khong_dat=0,
            don_vi="cái",
        )
    with pytest.raises(ValueError):                        # dat + khong_dat ≠ nhan
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=8, so_luong_khong_dat=1,
            don_vi="cái",
        )
    with pytest.raises(ValueError):                        # nhan = 0
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=0, so_luong_dat=0, so_luong_khong_dat=0,
            don_vi="cái",
        )


def test_dot_xuat_chi_cho_dang_chay_hoac_tam_dung(db, orders, lsx_svc, admin, customer):
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer, trang_thai=CV_HOAN_THANH)
    to_kiem, tv = _to_kiem(db)

    with pytest.raises(ValueError, match="đang chạy hoặc tạm dừng"):
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
            don_vi="cái",
        )

    cv.trang_thai = CV_TAM_DUNG                            # khác routing — routing CHO PHÉP
    db.commit()                                             # HOAN_THANH, đột xuất THÌ KHÔNG (Ruling 4)
    res = kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        don_vi="cái",
    )
    assert res["kcs_batch_id"]


def test_dot_xuat_khong_sua_trang_thai_cong_viec(db, orders, lsx_svc, admin, customer):
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    cv_id = cv.id

    kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        don_vi="cái",
    )
    # Đọc lại từ DB (không dùng object Python cũ) — trạng thái/sản lượng/kho KHÔNG đổi (mục 11).
    # "Không đụng kho" tự kiểm bằng đọc `tao_kiem_dot_xuat`: nó không import gì từ `stock`/`kho`,
    # không cần bảng kho riêng cho test này (không tạo san_xuat_batch đã phủ ở test trên).
    lai = db.get(SanXuatCongViec, cv_id)
    assert lai.trang_thai == CV_DANG_CHAY


def test_dot_xuat_gate_chi_nguoi_giu_kcs_tron_o_to_kiem(db, orders, lsx_svc, admin, customer):
    """Kiểm đột xuất hỏi KCS trên TRỌN tổ đi kiểm (`kcs_department_id`). Luật cũ "thành viên nào của
    tổ kiểm cũng ghi được" đã gỡ: đứng trong tổ mà vai không bật KCS thì bị chặn; KCS mức "Của tôi"
    cũng không đủ (lượt kiểm đột xuất không gắn việc được giao của ai); có đủ quyền ở tổ BỊ kiểm
    (admin) không thay được quyền ở tổ đi kiểm."""
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    kw = dict(cong_viec_id=cv.id, kcs_department_id=to_kiem.id, bat_dau=_T0, ket_thuc=_T1,
              so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0, don_vi="cái")

    with pytest.raises(PermissionError):
        kcs.tao_kiem_dot_xuat(db, user=admin, **kw)                 # admin: quyền ở tổ BỊ kiểm
    thanh_vien = _nguoi_o_to(db, to_kiem, "tv_thuong_to_kiem", scope=None)
    with pytest.raises(PermissionError):
        kcs.tao_kiem_dot_xuat(db, user=thanh_vien, **kw)            # đứng trong tổ, không quyền
    cua_toi = _nguoi_o_to(db, to_kiem, "tv_own_to_kiem", scope=SCOPE_OWN)
    with pytest.raises(PermissionError):
        kcs.tao_kiem_dot_xuat(db, user=cua_toi, **kw)               # KCS "Của tôi" không đủ
    assert db.query(SanXuatKcsBatch).filter_by(cong_viec_id=cv.id).count() == 0

    assert kcs.tao_kiem_dot_xuat(db, user=tv, **kw)["kcs_batch_id"]  # KCS trọn tổ kiểm → ghi được


# --- Điều chỉnh có audit (Task 6, §4.3, §5.5) -------------------------------------------------
def test_dieu_chinh_gate_routing_doi_quyen_kcs_o_to_chay_viec(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)     # admin giữ KCS ở tổ (_to_khoan)

    out = kcs.dieu_chinh_ket_qua(
        db, user=admin, kcs_batch_id=res["kcs_batch_id"],
        so_luong_dat=95, so_luong_khong_dat=5, expected_version=res["version"],
    )
    assert out["so_luong_dat"] == 95 and out["so_luong_khong_dat"] == 5

    # Đứng trong tổ, bật Xem + Thực hiện lệnh trọn tổ nhưng không bật KCS → không sửa được kết quả.
    chay_may = _nguoi_o_to(db, to, "chay_may_khong_kcs", viec=("run_order",))
    with pytest.raises(PermissionError):
        kcs.dieu_chinh_ket_qua(
            db, user=chay_may, kcs_batch_id=res["kcs_batch_id"],
            so_luong_dat=90, so_luong_khong_dat=10, expected_version=out["version"],
        )


def test_dieu_chinh_gate_dot_xuat_hoi_kcs_tron_o_to_di_kiem(db, orders, lsx_svc, admin, customer):
    """Điều chỉnh kết quả đột xuất hỏi KCS TRỌN ở TỔ ĐI KIỂM — không phải tổ BỊ kiểm (không thì tổ
    bị kiểm tự sửa được kết quả kiểm mình), cũng không phải mức "Của tôi" của thành viên tổ kiểm."""
    to_sx, cv = _cv_production(db, orders, lsx_svc, admin, customer)   # admin: đủ quyền ở tổ BỊ kiểm
    to_kiem, u_kcs = _to_kiem_truong(db)
    cua_toi = _nguoi_o_to(db, to_kiem, "tv_own_dieu_chinh", scope=SCOPE_OWN)
    res = kcs.tao_kiem_dot_xuat(
        db, user=u_kcs, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        don_vi="cái",
    )

    out = kcs.dieu_chinh_ket_qua(
        db, user=u_kcs, kcs_batch_id=res["kcs_batch_id"],
        so_luong_dat=8, so_luong_khong_dat=2, expected_version=res["version"],
    )
    assert out["so_luong_dat"] == 8 and out["so_luong_khong_dat"] == 2

    for nguoi in (admin, cua_toi):                                  # tổ bị kiểm / KCS "Của tôi"
        with pytest.raises(PermissionError):
            kcs.dieu_chinh_ket_qua(
                db, user=nguoi, kcs_batch_id=res["kcs_batch_id"],
                so_luong_dat=7, so_luong_khong_dat=3, expected_version=out["version"],
            )


def test_dieu_chinh_version_lech_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError, match="Phiên bản"):
        kcs.dieu_chinh_ket_qua(
            db, user=admin, kcs_batch_id=res["kcs_batch_id"],
            so_luong_dat=95, so_luong_khong_dat=5, expected_version=res["version"] + 1,
        )


def test_dieu_chinh_thanh_cong_khi_chua_gui_kho(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)     # nhan=100, dat=90, khong_dat=10
    out = kcs.dieu_chinh_ket_qua(
        db, user=admin, kcs_batch_id=res["kcs_batch_id"],
        so_luong_dat=95, so_luong_khong_dat=5, expected_version=res["version"],
    )
    kb = SanXuatKcsRepository(db).kcs_batch(res["kcs_batch_id"])
    assert float(kb.so_luong_dat) == 95 and float(kb.so_luong_khong_dat) == 5
    assert kb.ket_luan == KCS_DAT_MOT_PHAN
    assert kb.version == res["version"] + 1 == out["version"]
    assert float(kb.so_luong_nhan) == 100                            # số nhận KHÔNG đổi


def test_dieu_chinh_chan_khi_con_yeu_cau_kho_chua_huy(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=res["kcs_batch_id"], so_luong=50)   # còn YC_CHO_KHO
    assert yc["trang_thai"] == YC_CHO_KHO
    with pytest.raises(ValueError, match="yêu cầu nhập kho"):
        kcs.dieu_chinh_ket_qua(
            db, user=admin, kcs_batch_id=res["kcs_batch_id"],
            so_luong_dat=95, so_luong_khong_dat=5, expected_version=res["version"],
        )


def test_dieu_chinh_chan_tuyet_doi_khi_kho_da_nhan_mot_phan(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=res["kcs_batch_id"], so_luong=50)
    # Kho ĐÍCH: `kho_xac_nhan_nhap` bắt buộc chọn kho từ 31/08/2026 (luật soi riêng ở
    # `test_san_xuat_kho_dich.py`) — ở đây chỉ là dàn cảnh.
    k = KhoHang(ma="KHO-TP-KCS", ten="Kho thành phẩm")
    db.add(k)
    db.flush()
    kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=20,
                          kho_id=k.id)                                  # kho nhận MỘT PHẦN
    y = SanXuatKhoRepository(db).yc(yc["yc_id"])
    assert y.trang_thai == YC_MOT_PHAN
    with pytest.raises(ValueError, match="yêu cầu nhập kho"):
        kcs.dieu_chinh_ket_qua(
            db, user=admin, kcs_batch_id=res["kcs_batch_id"],
            so_luong_dat=95, so_luong_khong_dat=5, expected_version=res["version"],
        )

    kho.huy_phan_chua_nhan(db, user=admin, yc_id=yc["yc_id"])   # KCS huỷ phần CHƯA nhận
    y = SanXuatKhoRepository(db).yc(yc["yc_id"])
    assert y.trang_thai == YC_DA_NHAP                            # KHÔNG PHẢI YC_HUY — không quay lại
    with pytest.raises(ValueError, match="yêu cầu nhập kho"):    # vẫn bị chặn — "tuyệt đối"
        kcs.dieu_chinh_ket_qua(
            db, user=admin, kcs_batch_id=res["kcs_batch_id"],
            so_luong_dat=95, so_luong_khong_dat=5, expected_version=res["version"],
        )


def test_dieu_chinh_khong_bypass_luat_giu_anh_cuoi(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, nhan=100, dat=90, khong_dat=10)
    loi = kcs.ghi_loi(db, user=admin, kcs_batch_id=res["kcs_batch_id"],
                      anh=_anh())                                   # đúng 1 ảnh

    out = kcs.dieu_chinh_ket_qua(
        db, user=admin, kcs_batch_id=res["kcs_batch_id"],
        so_luong_dat=85, so_luong_khong_dat=15,                     # vẫn khong_dat > 0
        expected_version=res["version"],
    )
    assert out["so_luong_khong_dat"] == 15

    anh = db.query(SanXuatKcsLoiAnh).filter_by(loi_id=loi["loi_id"]).first()
    with pytest.raises(ValueError, match="ảnh cuối"):                # luật cũ VẪN đứng, không bị bypass
        kcs.xoa_anh_loi(db, user=admin, anh_id=anh.id)


def test_dieu_chinh_ghi_audit_truoc_sau(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)     # dat=90, khong_dat=10
    kcs.dieu_chinh_ket_qua(
        db, user=admin, kcs_batch_id=res["kcs_batch_id"],
        so_luong_dat=95, so_luong_khong_dat=5, expected_version=res["version"],
    )
    vet = AuditLogRepository(db).list_by_target(f"san_xuat_kcs_batch:{res['kcs_batch_id']}", limit=20)
    dong = [r for r in vet if r.action == "san_xuat_kcs_dieu_chinh"]
    assert len(dong) == 1
    detail = dong[0].detail or ""
    assert "dat=90" in detail and "khong_dat=10" in detail           # TRƯỚC
    assert "dat=95" in detail and "khong_dat=5" in detail            # SAU


# --- Đường dây HTTP ---------------------------------------------------------------------------
def test_api_hop_thu_can_dang_nhap(client):
    assert client.get("/api/san-xuat/kcs/hop-thu").status_code == 401


def test_api_ghi_loi_multipart_admin_khong_co_quyen_kcs_403(client):
    """Admin seed (vai "Giám đốc") không có dòng quyền theo tổ nào bật KCS → cổng router
    `require_quyen_to("qc")` chặn ngay, chưa chạm service."""
    tok = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]
    resp = client.post(
        "/api/san-xuat/kcs/1/loi",
        data={"mo_ta": "Lem mực"},
        files={"files": ("loi.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403
