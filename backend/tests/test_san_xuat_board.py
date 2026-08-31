"""Thực hiện sản xuất — Giai đoạn 2 (mặt đọc): bàn TỔ `/api/san-xuat/teams` + `/work-items`.

Soi tầng service `services/san_xuat/board.py`:
  · liệt kê tổ (node lá Khối SX) + badge số việc chờ, đọc từ snapshot gói đang hiệu lực;
  · timeline công việc của MỘT tổ, nhãn nguồn/nhóm/máy resolve theo lô;
  · PHẠM VI QUYỀN: all thấy hết · department thấy cây con · own chỉ tổ mình; ngoài phạm vi → chặn.

Tái dùng luồng thật (đơn → SX → sẵn sàng) + phát hành backbone của test xếp lịch/backbone.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from datetime import datetime, timezone

from app.models.department import Department
from app.models.lsx import LsxCongDoan
from app.models.role import SCOPE_DEPARTMENT, SCOPE_OWN
from app.models.san_xuat import CV_HOAN_THANH, SanXuatCongViec
from app.models.san_xuat_kcs import SanXuatKcsBatch
from app.models.san_xuat_san_luong import BG_XAC_NHAN, SanXuatBanGiao
from app.repositories.rbac_repo import RoleRepository
from app.repositories.san_xuat_repo import SanXuatRepository
from app.services.rbac_service import AuthorizationService
from app.services.san_xuat import board, release

# Fixtures + helper dùng chung từ test xếp lịch.
from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_KEYS_ITEM = {
    "id", "goi_id", "phien_ban_so", "nguon_loai", "nguon_ma", "nguon_ten", "nhom",
    "ten_cong_doan", "nhom_cong_doan", "loai_buoc", "la_kcs", "la_kcs_cuoi", "may",
    "du_kien_bat_dau", "du_kien_ket_thuc", "so_luong_vao", "so_luong_ra",
    "don_vi_vao", "don_vi_ra", "trang_thai",
}


class _FakeAuthz:
    """Ép cứng scope để soi từng nhánh `_to_thay_duoc` mà không phụ thuộc tên role seed."""

    def __init__(self, scope: str) -> None:
        self._scope = scope

    def scope_for(self, user, module_key):  # noqa: D401 - stub
        return self._scope


def _to_moi(db, ten="Tổ In Board", ma="TO-BOARD") -> Department:
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    return d


def _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to_id: int):
    """Hai lệnh sẵn sàng → dồn MỌI công đoạn về một tổ → phát hành. Trả (a, b, gói)."""
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id.in_([a.id, b.id])).update(
        {LsxCongDoan.department_id: to_id}, synchronize_session=False
    )
    db.commit()
    goi = release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()
    return a, b, goi


def _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to_id: int):
    """Giống `_phat_hanh_vao_to` nhưng đánh bước CUỐI của LSX `a` là KCS (`la_kcs=True`) TRƯỚC khi
    phát hành — dựng dữ liệu có CẢ việc sản xuất lẫn việc KCS trong CÙNG một tổ (KCS kiêm nhiệm:
    tổ này không cần `is_kcs=True`, đúng cách `_kcs_hoa()` của `test_xep_lich_2.py` làm)."""
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id.in_([a.id, b.id])).update(
        {LsxCongDoan.department_id: to_id}, synchronize_session=False
    )
    buoc_cuoi = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == a.id).order_by(
        LsxCongDoan.thu_tu, LsxCongDoan.id
    ).all()[-1]
    buoc_cuoi.la_kcs = True
    db.commit()
    goi = release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()
    return a, b, goi


def _authz(db) -> AuthorizationService:
    return AuthorizationService(RoleRepository(db))


# --- /teams: liệt kê tổ + badge số việc chờ (§2.1 navbar, §11 màn) --------------------------
def test_teams_liet_ke_va_badge(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    ts = board.teams(db, admin, _authz(db))
    by_id = {t["id"]: t for t in ts}
    assert to.id in by_id
    row = by_id[to.id]
    assert set(row) == {
        "id", "ten", "ma", "la_kcs", "so_viec_cho", "so_viec_kcs_cho", "co_viec_kcs",
    }
    assert row["ten"] == "Tổ In Board" and row["ma"] == "TO-BOARD" and row["la_kcs"] is False

    n_cho = (
        db.query(SanXuatCongViec)
        .filter(
            SanXuatCongViec.department_id == to.id,
            SanXuatCongViec.trang_thai != CV_HOAN_THANH,
        )
        .count()
    )
    assert n_cho > 0 and row["so_viec_cho"] == n_cho


def test_badge_bo_qua_viec_hoan_thanh(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    truoc = {t["id"]: t["so_viec_cho"] for t in board.teams(db, admin, _authz(db))}[to.id]
    cv = db.query(SanXuatCongViec).filter_by(department_id=to.id).first()
    cv.trang_thai = CV_HOAN_THANH
    db.commit()
    sau = {t["id"]: t["so_viec_cho"] for t in board.teams(db, admin, _authz(db))}[to.id]
    assert sau == truoc - 1


# --- /work-items: timeline một tổ, nhãn nguồn/nhóm đầy đủ (§18) ------------------------------
def test_work_items_liet_ke_day_du(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _a, _b, goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    res = board.work_items(db, admin, _authz(db), team_id=to.id)
    assert res["team_id"] == to.id
    cv = res["cong_viec"]
    assert len(cv) == db.query(SanXuatCongViec).filter_by(department_id=to.id).count()

    first = cv[0]
    assert _KEYS_ITEM <= set(first)
    assert first["goi_id"] == goi.id and first["phien_ban_so"] == 1
    assert first["trang_thai"] == "released"
    assert first["nguon_loai"] in ("lsx", "bai_ghep")
    assert first["nguon_ma"]        # nhãn nguồn không rỗng
    assert first["ten_cong_doan"]   # tên công đoạn không rỗng
    assert first["nhom"]            # nhóm thành phẩm gắn nhãn
    assert first["thuc_te"] == []   # chưa chạy phiên nào → lớp thực-tế rỗng


def test_work_items_lop_thuc_te_theo_phien_chay(db, orders, lsx_svc, admin, customer):
    """Lớp thực-tế (§5.1): mỗi phiên chạy của công việc phơi thành một khoảng trong `thuc_te`,
    phiên còn mở giữ ket_thuc=None (FE kéo tới "bây giờ")."""
    from datetime import datetime, timezone

    from app.models.san_xuat_thuc_thi import SanXuatPhienChay

    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cvid = db.query(SanXuatCongViec.id).filter_by(department_id=to.id).order_by(
        SanXuatCongViec.id
    ).first()[0]

    t0 = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)
    db.add_all([
        SanXuatPhienChay(cong_viec_id=cvid, so_thu_tu=1, bat_dau=t0, ket_thuc=t1,
                         loai_dong="tam_dung"),
        SanXuatPhienChay(cong_viec_id=cvid, so_thu_tu=2, bat_dau=t2, ket_thuc=None),  # còn mở
    ])
    db.commit()

    res = board.work_items(db, admin, _authz(db), team_id=to.id)
    item = next(w for w in res["cong_viec"] if w["id"] == cvid)
    tt = item["thuc_te"]
    assert len(tt) == 2                       # đúng thứ tự so_thu_tu
    assert tt[0]["ket_thuc"] is not None      # phiên 1 đã đóng
    assert tt[1]["ket_thuc"] is None          # phiên 2 còn mở → kéo tới "bây giờ"


# --- Phạm vi quyền: all / department / own --------------------------------------------------
def test_scope_department_thay_cay_con(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _to_moi(db, "Tổ Khác", "TO-KHAC")  # tổ ngoài cây con → không được thấy
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    user = SimpleNamespace(id=admin.id, department_id=to.id, role_id=admin.role_id)
    ts = board.teams(db, user, _FakeAuthz(SCOPE_DEPARTMENT))
    assert {t["id"] for t in ts} == {to.id}  # tổ lá: cây con = chính nó


def test_scope_own_chi_thay_to_minh(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _to_moi(db, "Tổ Khác", "TO-KHAC")
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    user = SimpleNamespace(id=admin.id, department_id=to.id, role_id=admin.role_id)
    ts = board.teams(db, user, _FakeAuthz(SCOPE_OWN))
    assert {t["id"] for t in ts} == {to.id}


def test_work_items_ngoai_pham_vi_bi_chan(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    ngoai = _to_moi(db, "Tổ Ngoài", "TO-NGOAI")
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    # User chỉ thuộc `ngoai` (scope own): xem việc của `to` → chặn; xem tổ mình → được (rỗng).
    user = SimpleNamespace(id=admin.id, department_id=ngoai.id, role_id=admin.role_id)
    with pytest.raises(PermissionError):
        board.work_items(db, user, _FakeAuthz(SCOPE_OWN), team_id=to.id)
    res = board.work_items(db, user, _FakeAuthz(SCOPE_OWN), team_id=ngoai.id)
    assert res["team_id"] == ngoai.id and res["cong_viec"] == []


def test_work_items_team_khong_hop_le_bi_chan(db, admin):
    # Không phải node lá Khối SX → ngoài tập cho phép → chặn (kể cả scope all).
    with pytest.raises(PermissionError):
        board.work_items(db, admin, _authz(db), team_id=999_999)


# --- Task 4: tách board production/KCS + hai badge (§18 mục 6, mg 0250) ---------------------
def test_mode_production_chi_tra_khong_kcs(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to.id)

    res = board.work_items(db, admin, _authz(db), team_id=to.id, mode="production")
    items = res["cong_viec"]
    assert items  # tổ này còn việc sản xuất khác ngoài bước KCS
    assert all(i["la_kcs"] is False for i in items)


def test_mode_kcs_chi_tra_kcs(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to.id)

    res = board.work_items(db, admin, _authz(db), team_id=to.id, mode="kcs")
    items = res["cong_viec"]
    assert items  # fixture đảm bảo có ít nhất 1 việc la_kcs=True
    assert all(i["la_kcs"] is True for i in items)


def test_thieu_mode_mac_dinh_production(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to.id)

    mac_dinh = board.work_items(db, admin, _authz(db), team_id=to.id)
    tuong_minh = board.work_items(db, admin, _authz(db), team_id=to.id, mode="production")
    assert mac_dinh == tuong_minh


def test_badge_production_khong_dem_kcs(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to.id)

    repo = SanXuatRepository(db)
    badge = repo.dem_cho_lam_theo_to({to.id})
    n_production = (
        db.query(SanXuatCongViec)
        .filter(
            SanXuatCongViec.department_id == to.id,
            SanXuatCongViec.trang_thai != CV_HOAN_THANH,
            SanXuatCongViec.la_kcs.is_(False),
        )
        .count()
    )
    n_kcs = (
        db.query(SanXuatCongViec)
        .filter(
            SanXuatCongViec.department_id == to.id,
            SanXuatCongViec.trang_thai != CV_HOAN_THANH,
            SanXuatCongViec.la_kcs.is_(True),
        )
        .count()
    )
    assert n_production > 0 and n_kcs > 0  # fixture phải có cả hai loại để test có ý nghĩa
    assert badge.get(to.id) == n_production


def test_badge_kcs_chi_dem_cho_kiem(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _a, _b, goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    def _viec(la_kcs: bool, ten: str) -> SanXuatCongViec:
        cv = SanXuatCongViec(
            goi_id=goi.id, department_id=to.id, la_kcs=la_kcs, ten_cong_doan=ten,
        )
        db.add(cv)
        db.flush()
        return cv

    # (a) việc KCS CHƯA có bàn giao đến — KHÔNG tính.
    _viec(True, "KCS chưa bàn giao")

    # (b) việc KCS có bàn giao confirmed, CHƯA có SanXuatKcsBatch — TÍNH.
    cv_b = _viec(True, "KCS chờ kiểm")
    nguon_b = _viec(False, "Nguồn của (b)")
    db.add(SanXuatBanGiao(
        nguon_cong_viec_id=nguon_b.id, dich_cong_viec_id=cv_b.id,
        so_luong=10, don_vi="to", trang_thai=BG_XAC_NHAN,
    ))

    # (c) việc KCS có bàn giao confirmed VÀ đã có SanXuatKcsBatch — KHÔNG tính (đã kiểm).
    cv_c = _viec(True, "KCS đã kiểm")
    nguon_c = _viec(False, "Nguồn của (c)")
    db.add(SanXuatBanGiao(
        nguon_cong_viec_id=nguon_c.id, dich_cong_viec_id=cv_c.id,
        so_luong=10, don_vi="to", trang_thai=BG_XAC_NHAN,
    ))
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    db.add(SanXuatKcsBatch(
        cong_viec_id=cv_c.id, bat_dau=now, ket_thuc=now,
        so_luong_nhan=10, so_luong_dat=10, don_vi="to",
    ))
    db.commit()

    repo = SanXuatRepository(db)
    badge = repo.dem_kcs_cho_kiem_theo_to({to.id})
    assert badge.get(to.id, 0) == 1


def test_sinh_node_kcs_chi_khi_co_viec_kcs(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _a, _b, goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    repo = SanXuatRepository(db)
    assert repo.to_co_viec_kcs({to.id}) == set()
    truoc = {t["id"]: t for t in board.teams(db, admin, _authz(db))}
    assert truoc[to.id]["co_viec_kcs"] is False
    assert truoc[to.id]["so_viec_kcs_cho"] == 0

    cv_kcs = SanXuatCongViec(
        goi_id=goi.id, department_id=to.id, la_kcs=True, ten_cong_doan="KCS đột xuất",
    )
    db.add(cv_kcs)
    db.commit()

    assert repo.to_co_viec_kcs({to.id}) == {to.id}
    sau = {t["id"]: t for t in board.teams(db, admin, _authz(db))}
    assert sau[to.id]["co_viec_kcs"] is True

    # Việc KCS đã HOÀN THÀNH → không còn "đang hoạt động" → node phải biến mất.
    cv_kcs.trang_thai = CV_HOAN_THANH
    db.commit()
    assert repo.to_co_viec_kcs({to.id}) == set()
    cuoi = {t["id"]: t for t in board.teams(db, admin, _authz(db))}
    assert cuoi[to.id]["co_viec_kcs"] is False
