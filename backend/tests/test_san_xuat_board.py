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

from app.models.department import Department
from app.models.lsx import LsxCongDoan
from app.models.role import SCOPE_DEPARTMENT, SCOPE_OWN
from app.models.san_xuat import CV_HOAN_THANH, SanXuatCongViec
from app.repositories.rbac_repo import RoleRepository
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
    assert set(row) == {"id", "ten", "ma", "la_kcs", "so_viec_cho"}
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
