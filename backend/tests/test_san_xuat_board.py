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
from app.models.employee import Employee
from app.models.lsx import LsxCongDoan
from app.models.role import SCOPE_DEPARTMENT, SCOPE_OWN
from app.models.san_xuat import CV_HOAN_THANH, SanXuatCongViec
from app.models.san_xuat_kcs import SanXuatKcsBatch
from app.models.san_xuat_san_luong import BG_XAC_NHAN, SanXuatBanGiao
from app.models.san_xuat_thuc_thi import PC_HOAT_DONG, SanXuatPhanCong
from app.models.user import User
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
    """Giống `_phat_hanh_vao_to` nhưng tổ `to_id` được bật `is_kcs=True` VÀ LSX `a` được thêm một
    bước ĐẦU (trước bước gốc "In offset") — dựng dữ liệu có CẢ việc sản xuất (bước không phải cuối)
    lẫn việc KCS (bước CUỐI của mỗi LSX) trong CÙNG một tổ. `la_kcs` từ 2026-08-31 suy TỰ ĐỘNG
    (bước cuối routing + `departments.is_kcs`), không còn khai tay trên `LsxCongDoan` — xem
    `docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem-suy-tu-dong.md`."""
    db.query(Department).filter(Department.id == to_id).update({"is_kcs": True})
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id.in_([a.id, b.id])).update(
        {LsxCongDoan.department_id: to_id}, synchronize_session=False
    )
    buoc_goc = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == a.id).order_by(
        LsxCongDoan.thu_tu, LsxCongDoan.id
    ).first()
    db.add(LsxCongDoan(
        lsx_id=a.id, thu_tu=(buoc_goc.thu_tu or 0) - 1, ten="Chuẩn bị", nhom="prepress",
        department_id=to_id,
    ))
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


def test_work_items_ten_may_lay_tu_danh_muc_dang_chay(db, orders, lsx_svc, admin, customer):
    """Cột "Máy" của bàn tổ phải ra TÊN, không rỗng.

    `san_xuat_cong_viec.may_id` là soft-key sang `may_thiet_bi` (mg `0237`), nhưng `may_nhan` từng
    tra trong `machines` — danh mục đời tính giá, id lệch hẳn — nên join không bao giờ trúng và ô
    máy trống trơn với MỌI công việc có máy."""
    from app.models.may_thiet_bi import MayThietBi

    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    may = MayThietBi(ma="MAY-BOARD-1", ten="Máy in offset 4 màu", loai_may="in")
    db.add(may)
    db.flush()
    cvid = db.query(SanXuatCongViec.id).filter_by(department_id=to.id).order_by(
        SanXuatCongViec.id
    ).first()[0]
    db.query(SanXuatCongViec).filter_by(id=cvid).update({"may_id": may.id})
    db.commit()

    res = board.work_items(db, admin, _authz(db), team_id=to.id)
    item = next(w for w in res["cong_viec"] if w["id"] == cvid)
    assert item["may"] == "Máy in offset 4 màu"


def test_item_dict_gio_khong_lech_khi_db_tra_aware():
    """Bản vá giờ phải đo được TRÊN POSTGRES, nơi lỗi thật xảy ra.

    SQLite trả datetime naive dù cột khai `timezone=True`, nên một test đi qua `work_items` ở đây
    không bao giờ thấy `+00:00` — đúng lý do bug sống sót lâu. Gọi thẳng `_item_dict` với giá trị
    AWARE (khuôn Postgres trả về) mới bắt được: mốc kế hoạch phải rụng nhãn UTC nguyên con số, mốc
    phiên chạy (UTC THẬT) phải được kéo về giờ xưởng trước khi rụng nhãn."""
    from datetime import timedelta

    from app.services.san_xuat.board import _item_dict

    ke_hoach = datetime(2026, 8, 20, 18, 34, tzinfo=timezone.utc)
    moc_that = datetime(2026, 8, 20, 11, 34, tzinfo=timezone.utc)
    cv = SimpleNamespace(
        id=7, goi_id=1, phien_ban_so=1, nhom_id=None, lsx_id=None, bai_ghep_id=None,
        ten_cong_doan="In offset (lần 1/2)", nhom_cong_doan="print", loai_buoc="may",
        la_kcs=False, la_kcs_cuoi=False, may_id=None,
        du_kien_bat_dau=ke_hoach, du_kien_ket_thuc=ke_hoach + timedelta(hours=1),
        dinh_muc_json=None, so_luong_vao=400, so_luong_ra=316, don_vi_vao="tờ", don_vi_ra="tờ",
        trang_thai="released", vat_tu_json=None,
    )
    phien = SimpleNamespace(bat_dau=moc_that, ket_thuc=None)

    item = _item_dict(cv, {}, {}, {}, {}, phien_map={7: [phien]})

    assert item["du_kien_bat_dau"] == ke_hoach.replace(tzinfo=None), "giữ nguyên giờ người xếp thấy"
    # Mốc thực tế quy về đồng hồ xưởng rồi mới rụng nhãn — viết theo múi MÁY CHỦ, không cứng +7h.
    assert item["thuc_te"][0]["bat_dau"] == moc_that.astimezone().replace(tzinfo=None)
    assert item["thuc_te"][0]["ket_thuc"] is None


def test_work_items_moi_moc_gio_cung_mot_thang(db, orders, lsx_svc, admin, customer):
    """Mốc KẾ HOẠCH và mốc THỰC TẾ phải ra cùng thang wall-clock giờ xưởng, và KHÔNG mang tzinfo.

    Hai lớp này chồng lên nhau trên cùng một thanh Gantt (`ThsxTimeline`), mà FE đo bằng
    `gantt-time.wallMinutes` — hàm đọc thành phần ISO, không dịch múi. Trả kèm `+00:00` là màn
    danh sách (`ngayGio` dùng `new Date`) cộng thêm offset máy: bàn Xếp lịch hiện 18:34 thì bàn tổ
    hiện 01:34 hôm sau. Trả UTC THẬT cho `thuc_te` thì thanh thực-tế lùi đúng một offset."""
    from datetime import timedelta

    from app.models.san_xuat_thuc_thi import SanXuatPhienChay
    from app.services.gio_xuong import gio_xuong

    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cvid = db.query(SanXuatCongViec.id).filter_by(department_id=to.id).order_by(
        SanXuatCongViec.id
    ).first()[0]
    ke_hoach = datetime(2026, 8, 20, 18, 34, tzinfo=timezone.utc)   # giờ TƯỜNG dán nhãn UTC
    db.query(SanXuatCongViec).filter_by(id=cvid).update({
        "du_kien_bat_dau": ke_hoach, "du_kien_ket_thuc": ke_hoach + timedelta(hours=1),
    })
    # Phiên chạy ghi bằng UTC THẬT (`thuc_thi._moc`) — mốc "bây giờ" của hai thang lệch nhau đúng
    # offset máy chủ, nên dựng bằng chính cặp hàm đó thay vì viết cứng +7h.
    db.add(SanXuatPhienChay(cong_viec_id=cvid, so_thu_tu=1,
                            bat_dau=datetime.now(timezone.utc), ket_thuc=None))
    db.commit()

    item = next(
        w for w in board.work_items(db, admin, _authz(db), team_id=to.id)["cong_viec"]
        if w["id"] == cvid
    )
    assert item["du_kien_bat_dau"].tzinfo is None
    assert item["du_kien_bat_dau"] == ke_hoach.replace(tzinfo=None)   # đúng con số người xếp thấy
    thuc = item["thuc_te"][0]["bat_dau"]
    assert thuc.tzinfo is None
    # Cùng thang với `du_kien_*`: lệch dưới một phút so với đồng hồ xưởng, không lệch cả offset.
    assert abs((thuc - gio_xuong().replace(tzinfo=None)).total_seconds()) < 60


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


def test_scope_own_them_to_kiem_nhiem(db, orders, lsx_svc, admin, customer):
    """Tổ trưởng KIÊM NHIỆM (`Department.head_user_id` trỏ tới user) phải thấy được tổ đó dù
    ngoài phòng nhà của mình — nếu không, `_gate` (thuc_thi.py) đã cho GHI việc của tổ đó nhưng
    sidebar/board lại không có lối vào để XEM (bug đã vá)."""
    nha = _to_moi(db, "Tổ Nhà", "TO-NHA")
    kiem = _to_moi(db, "Tổ Kiêm Nhiệm", "TO-KIEM")
    kiem.head_user_id = admin.id
    db.commit()
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, kiem.id)

    user = SimpleNamespace(id=admin.id, department_id=nha.id, role_id=admin.role_id)
    ts = board.teams(db, user, _FakeAuthz(SCOPE_OWN))
    assert {t["id"] for t in ts} == {nha.id, kiem.id}

    res = board.work_items(db, user, _FakeAuthz(SCOPE_OWN), team_id=kiem.id)
    assert res["team_id"] == kiem.id and len(res["cong_viec"]) > 0


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


# --- Thợ chỉ thấy việc được giao (§7.1) -----------------------------------------------------
def _tho_co_tai_khoan(db, to, *, username, ma_nv):
    """Một THỢ thật: tài khoản + hồ sơ nhân viên nối với nhau, thuộc tổ `to`."""
    u = User(username=username, name=f"Thợ {ma_nv}", password_hash="x")
    db.add(u)
    db.flush()
    db.add(Employee(code=ma_nv, full_name=u.name, department_id=to.id, user_id=u.id))
    db.flush()
    return u


def _giao(db, cv_id: int, employee_id: int) -> None:
    db.add(SanXuatPhanCong(
        cong_viec_id=cv_id, employee_id=employee_id, trang_thai=PC_HOAT_DONG
    ))
    db.commit()


def _emp_id(db, user_id: int) -> int:
    return db.query(Employee).filter_by(user_id=user_id).one().id


def test_tho_chi_thay_viec_duoc_giao(db, orders, lsx_svc, admin, customer):
    """Thợ mở bàn tổ mình: chỉ những việc CÒN đang giao cho chính họ, không phải cả tổ."""
    to = _to_moi(db)
    to.head_user_id = admin.id          # tổ trưởng là admin, không phải người thợ dưới đây
    db.commit()
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    u = _tho_co_tai_khoan(db, to, username="tho_board_1", ma_nv="NV-BOARD-1")
    tho = SimpleNamespace(id=u.id, department_id=to.id, role_id=admin.role_id)

    ca_ban = board.work_items(db, admin, _authz(db), team_id=to.id)["cong_viec"]
    assert len(ca_ban) >= 2, "cần ít nhất 2 việc mới soi được phép lọc"

    # Chưa giao gì → không thấy việc nào, KHÔNG rơi về "thấy hết".
    assert board.work_items(db, tho, _FakeAuthz(SCOPE_OWN), team_id=to.id)["cong_viec"] == []

    _giao(db, ca_ban[0]["id"], _emp_id(db, u.id))
    thay = board.work_items(db, tho, _FakeAuthz(SCOPE_OWN), team_id=to.id)["cong_viec"]
    assert [w["id"] for w in thay] == [ca_ban[0]["id"]]


def test_to_truong_van_thay_ca_ban(db, orders, lsx_svc, admin, customer):
    """Lọc chỉ áp cho THỢ — tổ trưởng của chính tổ đó vẫn thấy trọn bàn dù không được giao việc nào."""
    to = _to_moi(db)
    to.head_user_id = admin.id
    db.commit()
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    truong = SimpleNamespace(id=admin.id, department_id=to.id, role_id=admin.role_id)
    thay = board.work_items(db, truong, _FakeAuthz(SCOPE_OWN), team_id=to.id)["cong_viec"]
    assert len(thay) == len(board.work_items(db, admin, _authz(db), team_id=to.id)["cong_viec"])
    assert thay


def test_badge_navbar_cua_tho_khop_so_viec_mo_ra(db, orders, lsx_svc, admin, customer):
    """Badge trên navbar phải đếm đúng số dòng thợ mở ra thấy — báo 12 mà bàn có 2 là nói dối."""
    to = _to_moi(db)
    to.head_user_id = admin.id
    db.commit()
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    u = _tho_co_tai_khoan(db, to, username="tho_board_2", ma_nv="NV-BOARD-2")
    tho = SimpleNamespace(id=u.id, department_id=to.id, role_id=admin.role_id)
    ca_ban = board.work_items(db, admin, _authz(db), team_id=to.id)["cong_viec"]
    _giao(db, ca_ban[0]["id"], _emp_id(db, u.id))

    badge = {t["id"]: t["so_viec_cho"] for t in board.teams(db, tho, _FakeAuthz(SCOPE_OWN))}
    so_dong = len(board.work_items(db, tho, _FakeAuthz(SCOPE_OWN), team_id=to.id)["cong_viec"])
    assert badge[to.id] == so_dong == 1


def test_tho_mo_viec_khong_duoc_giao_bi_chan(db, orders, lsx_svc, admin, customer):
    """Không có ở bàn thì cũng không mở được bằng đường link/chi tiết."""
    to = _to_moi(db)
    to.head_user_id = admin.id
    db.commit()
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    u = _tho_co_tai_khoan(db, to, username="tho_board_3", ma_nv="NV-BOARD-3")
    tho = SimpleNamespace(id=u.id, department_id=to.id, role_id=admin.role_id)
    ca_ban = board.work_items(db, admin, _authz(db), team_id=to.id)["cong_viec"]
    _giao(db, ca_ban[0]["id"], _emp_id(db, u.id))

    ct = board.chi_tiet_cong_viec(db, tho, _FakeAuthz(SCOPE_OWN), cong_viec_id=ca_ban[0]["id"])
    assert ct["cong_viec"]["id"] == ca_ban[0]["id"]
    with pytest.raises(PermissionError):
        board.chi_tiet_cong_viec(db, tho, _FakeAuthz(SCOPE_OWN), cong_viec_id=ca_ban[1]["id"])


def test_tai_khoan_chua_noi_ho_so_nhan_vien_thi_khong_thay_gi(db, orders, lsx_svc, admin, customer):
    """`employee.user_id` chưa nối ⇒ không biết người đó được giao gì ⇒ bàn trống, không mở toang."""
    to = _to_moi(db)
    to.head_user_id = admin.id
    db.commit()
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    u = User(username="tho_board_4", name="Thợ Chưa Nối Hồ Sơ", password_hash="x")
    db.add(u)
    db.commit()
    tho = SimpleNamespace(id=u.id, department_id=to.id, role_id=admin.role_id)
    assert board.work_items(db, tho, _FakeAuthz(SCOPE_OWN), team_id=to.id)["cong_viec"] == []
