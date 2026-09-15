"""Thực hiện sản xuất — Giai đoạn 2 (mặt đọc): bàn TỔ `/api/san-xuat/teams` + `/work-items`.

Soi tầng service `services/san_xuat/board.py`:
  · liệt kê tổ (node lá Khối SX) + badge số việc chờ, đọc từ snapshot gói đang hiệu lực;
  · timeline công việc của MỘT tổ, nhãn nguồn/nhóm/máy resolve theo lô;
  · PHẠM VI theo DÒNG QUYỀN THEO TỔ (`to_sx_<id>`, mg 0302 — `services/quyen_to.py`), tính từ vị
    trí người xem trong VÙNG của dòng: all thấy trọn vùng · department thấy cây con của phòng mình
    (đứng tại/trên nút thì trọn vùng, nhánh khác thì không gì) · own chỉ việc giao cho mình; ngoài
    phạm vi → chặn. Bàn của nút cấp gom gộp việc của các tổ trực thuộc.

Các bài soi phạm vi cấp dòng quyền THẬT (`cap_quyen_to`) cho người dùng thật trên cây phòng ban
thật (`Department.parent_id`) — không stub scope, không dựa `head_user_id`.

Tái dùng luồng thật (đơn → SX → sẵn sàng) + phát hành backbone của test xếp lịch/backbone.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from datetime import datetime, timezone

from app.models.department import Department
from app.models.employee import Employee
from app.models.lsx import LsxCongDoan
from app.models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from app.models.san_xuat import CV_HOAN_THANH, SanXuatCongViec
from app.models.san_xuat_kcs import SanXuatKcsBatch
from app.models.san_xuat_san_luong import BG_XAC_NHAN, SanXuatBanGiao
from app.models.san_xuat_thuc_thi import PC_HOAT_DONG, SanXuatPhanCong
from app.models.user import User
from app.repositories.rbac_repo import RoleRepository
from app.repositories.san_xuat_repo import SanXuatRepository
from app.services.rbac_service import AuthorizationService
from app.services.san_xuat import board, release
from tests.quyen_to_fixtures import BON_VIEC, cap_quyen_to

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


def _ban_phang(db, user, authz, **kw):
    """Bàn tổ ở chế độ PHẲNG — mảng bước, đúng hình mà loạt bài dưới đây soi (và là hình Gantt
    dùng). Từ 11/09/2026 `work_items` mặc định trả tầng LỆNH có phân trang; tầng đó có bài riêng ở
    `tests/test_san_xuat_lenh_phan_trang.py`, còn ở đây ta cố định `nhom="phang"`."""
    kw.setdefault("nhom", "phang")
    return board.work_items(db, user, authz, **kw)


_TAT_CA_5_VIEC = {"read": "all", "run_order": "all", "confirm_output": "all", "qc": "all",
                  "warehouse": "all"}


class _FakeAuthz:
    """Ép cứng scope của `authz.scope_for` — CÒN GIỮ vì vài file test khác import.

    Từ mg 0302 phạm vi Bàn tổ KHÔNG còn đọc `authz` (tham số chỉ còn trong chữ ký service) mà đọc
    dòng quyền theo tổ của vai ⇒ stub này không quyết định gì ở bàn tổ; muốn soi phạm vi thì cấp
    dòng thật bằng `cap_quyen_to`."""

    def __init__(self, scope: str) -> None:
        self._scope = scope

    def scope_for(self, user, module_key):  # noqa: D401 - stub
        return self._scope


def _to_moi(db, ten="Tổ In Board", ma="TO-BOARD", *, quyen_admin: bool = True) -> Department:
    """Tổ SX mới. Mặc định bật đủ quyền trên dòng tổ cho vai của admin seed — như quản trị tích ma
    trận; test soi phạm vi tự cấp thì truyền `quyen_admin=False`."""
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    if quyen_admin:
        cap_quyen_to(db, db.query(User).filter(User.username == "admin").one(), d)
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


def _cay_san_xuat(db) -> SimpleNamespace:
    """Cây khối Sản xuất THẬT theo `Department.parent_id` (ví dụ của spec §2):

        Sản xuất (gốc, cấp 0) ─┬─ Tổ in (cấp 1) ── Nhóm in 2 màu (cấp 2, lá)
                                └─ Tổ cắt (cấp 1, lá)

    Chỉ gốc bật `la_san_xuat` — các nút con thuộc khối nhờ tổ tiên (`quyen_to.doc_cay`), đúng như
    quản trị tick một lần ở phòng cha. Không ai được cấp quyền ở đây."""
    goc = Department(name="Sản xuất Board", code="SX-BOARD", la_san_xuat=True)
    db.add(goc)
    db.flush()
    to_in = Department(name="Tổ in Board", code="TI-BOARD", parent_id=goc.id)
    to_cat = Department(name="Tổ cắt Board", code="TC-BOARD", parent_id=goc.id)
    db.add_all([to_in, to_cat])
    db.flush()
    nhom = Department(name="Nhóm in 2 màu Board", code="N2M-BOARD", parent_id=to_in.id)
    db.add(nhom)
    db.flush()
    return SimpleNamespace(goc=goc, to_in=to_in, to_cat=to_cat, nhom=nhom)


def _nguoi(db, username: str, phong: Department | None) -> User:
    """Tài khoản thật (chưa có vai, chưa nối hồ sơ nhân viên) đứng ở phòng `phong`."""
    u = User(username=username, name=username, password_hash="x",
             department_id=phong.id if phong is not None else None)
    db.add(u)
    db.flush()
    return u


# --- /teams: liệt kê tổ + badge số việc chờ (§2.1 navbar, §11 màn) --------------------------
def test_teams_liet_ke_va_badge(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    ts = board.teams(db, admin, _authz(db))
    by_id = {t["id"]: t for t in ts}
    assert to.id in by_id
    row = by_id[to.id]
    assert set(row) == {
        "id", "ten", "ma", "cap", "la_kcs", "la_tho", "so_viec_cho", "so_viec_kcs_cho",
        "co_viec_kcs", "quyen", "so_cho_xac_nhan",
    }
    assert row["ten"] == "Tổ In Board" and row["ma"] == "TO-BOARD" and row["la_kcs"] is False
    # Tổ không có phòng cha → gốc cây, cấp 0; `_to_moi` bật Xem + 4 quyền chi tiết phạm vi all.
    assert row["cap"] == 0
    assert row["quyen"] == _TAT_CA_5_VIEC and row["la_tho"] is False

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

    res = _ban_phang(db, admin, _authz(db), team_id=to.id)
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

    res = _ban_phang(db, admin, _authz(db), team_id=to.id)
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

    res = _ban_phang(db, admin, _authz(db), team_id=to.id)
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
        # Ảnh chụp nhà gia công + khuôn lúc phát hành (`729f08e`). Bản giả này phải khai ĐỦ mọi
        # cột `_item_dict` đọc, không thì thêm cột mới là test rụng vì AttributeError — vốn chẳng
        # liên quan gì tới thứ nó đo (nhãn múi giờ).
        nha_cung_cap=None, khuon_json=None, khuon_nhan_luc=None, khuon_tra_luc=None,
        # Dặn dò + thẻ quy cách (10/09/2026) — cùng lý do như hai dòng trên.
        ghi_chu=None, quy_cach_json=None,
        # Tổ thật của việc (bàn nút cha gộp nhiều tổ con, mg 0302) — cùng lý do.
        department_id=None,
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
        w for w in _ban_phang(db, admin, _authz(db), team_id=to.id)["cong_viec"]
        if w["id"] == cvid
    )
    assert item["du_kien_bat_dau"].tzinfo is None
    assert item["du_kien_bat_dau"] == ke_hoach.replace(tzinfo=None)   # đúng con số người xếp thấy
    thuc = item["thuc_te"][0]["bat_dau"]
    assert thuc.tzinfo is None
    # Cùng thang với `du_kien_*`: lệch dưới một phút so với đồng hồ xưởng, không lệch cả offset.
    assert abs((thuc - gio_xuong().replace(tzinfo=None)).total_seconds()) < 60


# --- Phạm vi quyền: all / department / own trên dòng quyền theo tổ (mg 0302) -----------------
def test_scope_department_thay_cay_con(db):
    """`department` trên dòng Tổ in tính từ VỊ TRÍ người xem (bảng ví dụ spec §2): B đứng TẠI Tổ in
    → trọn vùng (Tổ in + Nhóm 2 màu); A đứng DƯỚI (Nhóm 2 màu) → chỉ cây con của phòng mình; X ở
    nhánh khác (Tổ cắt) → không thấy gì. Không ai thấy gốc Sản xuất hay Tổ cắt."""
    c = _cay_san_xuat(db)
    b = _nguoi(db, "b_to_in", c.to_in)
    a = _nguoi(db, "a_nhom_2_mau", c.nhom)
    x = _nguoi(db, "x_to_cat", c.to_cat)
    for u in (a, b, x):
        cap_quyen_to(db, u, c.to_in, scope=SCOPE_DEPARTMENT)   # vai mẫu Tổ trưởng: Cả phòng + 4
    db.commit()

    ts_b = board.teams(db, b, _authz(db))
    assert [(t["id"], t["cap"]) for t in ts_b] == [(c.to_in.id, 1), (c.nhom.id, 2)]
    assert all(t["quyen"] == _TAT_CA_5_VIEC and t["la_tho"] is False for t in ts_b)

    ts_a = board.teams(db, a, _authz(db))
    assert [(t["id"], t["cap"]) for t in ts_a] == [(c.nhom.id, 2)]
    assert ts_a[0]["quyen"] == _TAT_CA_5_VIEC

    assert board.teams(db, x, _authz(db)) == []
    with pytest.raises(PermissionError):
        _ban_phang(db, x, _authz(db), team_id=c.to_in.id)


def test_scope_own_chi_thay_to_minh(db):
    """`own` (vai mẫu Công nhân: Xem + Của tôi) trên dòng GỐC Sản xuất: menu chỉ hiện đúng nút của
    phòng mình — không bày cả dãy tổ mà mở ra đều chỉ có việc của mình; nút mang nhãn thợ và mức
    quyền `own`, không có quyền chi tiết nào."""
    c = _cay_san_xuat(db)
    a = _nguoi(db, "a_cong_nhan", c.nhom)
    cap_quyen_to(db, a, c.goc, scope=SCOPE_OWN, viec=())
    db.commit()

    ts = board.teams(db, a, _authz(db))
    assert [t["id"] for t in ts] == [c.nhom.id]
    assert ts[0]["cap"] == 2 and ts[0]["la_tho"] is True
    assert ts[0]["quyen"] == {"read": "own"}


def test_scope_own_them_to_kiem_nhiem(db, orders, lsx_svc, admin, customer):
    """Người KIÊM NHIỆM tổ khác: có dòng quyền ở tổ đó thì menu có lối vào và mở được bàn, dù phòng
    nhà ở chỗ khác — vì cổng ghi (`gate_to`) cũng đọc đúng dòng này, ghi được thì phải xem được.

    Ngược lại, chỉ ĐỨNG TÊN trưởng tổ (`head_user_id`) mà vai không có dòng của tổ thì không thấy,
    không mở được: `head_user_id` nay chỉ còn là thông tin tổ chức."""
    nha = _to_moi(db, "Tổ Nhà", "TO-NHA", quyen_admin=False)
    kiem = _to_moi(db, "Tổ Kiêm Nhiệm", "TO-KIEM", quyen_admin=False)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, kiem.id)

    u = _nguoi(db, "kiem_nhiem", nha)
    cap_quyen_to(db, u, nha)
    cap_quyen_to(db, u, kiem)
    db.commit()
    ts = board.teams(db, u, _authz(db))
    assert {t["id"] for t in ts} == {nha.id, kiem.id}
    res = _ban_phang(db, u, _authz(db), team_id=kiem.id)
    assert res["team_id"] == kiem.id and len(res["cong_viec"]) > 0

    dung_ten = _nguoi(db, "chi_dung_ten_truong", nha)
    cap_quyen_to(db, dung_ten, nha)
    kiem.head_user_id = dung_ten.id
    db.commit()
    assert {t["id"] for t in board.teams(db, dung_ten, _authz(db))} == {nha.id}
    with pytest.raises(PermissionError):
        _ban_phang(db, dung_ten, _authz(db), team_id=kiem.id)


def test_work_items_ngoai_pham_vi_bi_chan(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    ngoai = _to_moi(db, "Tổ Ngoài", "TO-NGOAI", quyen_admin=False)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    # Người chỉ có dòng quyền ở `ngoai` (phạm vi Tất cả): bàn của `to` → chặn; bàn tổ mình → được
    # (rỗng). Dòng `all` ở một tổ không lan sang tổ ngang hàng.
    u = _nguoi(db, "chi_to_ngoai", ngoai)
    cap_quyen_to(db, u, ngoai, scope=SCOPE_ALL)
    db.commit()
    with pytest.raises(PermissionError):
        _ban_phang(db, u, _authz(db), team_id=to.id)
    res = _ban_phang(db, u, _authz(db), team_id=ngoai.id)
    assert res["team_id"] == ngoai.id and res["cong_viec"] == []


def test_ban_nut_cha_gom_viec_cua_to_con(db, orders, lsx_svc, admin, customer):
    """Bàn của cấp GOM phủ cả VÙNG (spec §5): việc phát hành vào Nhóm 2 màu và Tổ cắt.

    · Quản đốc giữ dòng `all` ở gốc Sản xuất: bàn gốc gộp việc của cả hai tổ lá (cả chế độ phẳng lẫn
      tầng lệnh), badge nút gốc = tổng badge các tổ trong vùng, menu thụt lề theo cây.
    · Tổ trưởng Tổ in (`department`, đứng tại Tổ in): bàn Tổ in gộp việc của Nhóm 2 màu, KHÔNG có
      việc Tổ cắt; bàn gốc bị chặn vì không có Xem ở nút đó."""
    c = _cay_san_xuat(db)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == a.id).update(
        {LsxCongDoan.department_id: c.nhom.id}, synchronize_session=False
    )
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == b.id).update(
        {LsxCongDoan.department_id: c.to_cat.id}, synchronize_session=False
    )
    db.commit()
    release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()

    quan_doc = _nguoi(db, "quan_doc_sx", c.goc)
    cap_quyen_to(db, quan_doc, c.goc, scope=SCOPE_ALL)
    truong_in = _nguoi(db, "truong_to_in", c.to_in)
    cap_quyen_to(db, truong_in, c.to_in, scope=SCOPE_DEPARTMENT)
    db.commit()

    def _viec(dept) -> set[int]:
        return {i for (i,) in db.query(SanXuatCongViec.id).filter_by(department_id=dept.id)}

    viec_nhom, viec_cat = _viec(c.nhom), _viec(c.to_cat)
    assert viec_nhom and viec_cat, "cần việc ở cả hai tổ lá mới soi được phép gộp"

    ban_goc = _ban_phang(db, quan_doc, _authz(db), team_id=c.goc.id)
    assert ban_goc["team_id"] == c.goc.id
    assert {w["id"] for w in ban_goc["cong_viec"]} == viec_nhom | viec_cat
    # Mỗi dòng mang tổ THẬT của việc, không phải nút đang mở — thao tác theo tổ lấy tổ ở đây.
    assert {w["department_id"] for w in ban_goc["cong_viec"] if w["id"] in viec_nhom} == {c.nhom.id}
    assert {w["department_id"] for w in ban_goc["cong_viec"] if w["id"] in viec_cat} == {c.to_cat.id}
    lenh_goc = board.work_items(db, quan_doc, _authz(db), team_id=c.goc.id)
    assert lenh_goc["trang"]["tong"] == 2   # hai lệnh ở hai tổ con cùng hiện trên một bàn

    ts = board.teams(db, quan_doc, _authz(db))
    assert [(t["id"], t["cap"]) for t in ts] == [
        (c.goc.id, 0), (c.to_in.id, 1), (c.nhom.id, 2), (c.to_cat.id, 1),
    ]
    badge = {t["id"]: t["so_viec_cho"] for t in ts}
    assert badge[c.nhom.id] > 0 and badge[c.to_cat.id] > 0
    assert badge[c.to_in.id] == badge[c.nhom.id]
    assert badge[c.goc.id] == badge[c.nhom.id] + badge[c.to_cat.id]

    ban_in = _ban_phang(db, truong_in, _authz(db), team_id=c.to_in.id)
    assert {w["id"] for w in ban_in["cong_viec"]} == viec_nhom
    with pytest.raises(PermissionError):
        _ban_phang(db, truong_in, _authz(db), team_id=c.goc.id)


def test_work_items_team_khong_hop_le_bi_chan(db, admin):
    # Không phải node lá Khối SX → ngoài tập cho phép → chặn (kể cả scope all).
    with pytest.raises(PermissionError):
        _ban_phang(db, admin, _authz(db), team_id=999_999)


# --- Task 4: tách board production/KCS + hai badge (§18 mục 6, mg 0250) ---------------------
def test_mode_production_chi_tra_khong_kcs(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to.id)

    res = _ban_phang(db, admin, _authz(db), team_id=to.id, mode="production")
    items = res["cong_viec"]
    assert items  # tổ này còn việc sản xuất khác ngoài bước KCS
    assert all(i["la_kcs"] is False for i in items)


def test_mode_kcs_chi_tra_kcs(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to.id)

    res = _ban_phang(db, admin, _authz(db), team_id=to.id, mode="kcs")
    items = res["cong_viec"]
    assert items  # fixture đảm bảo có ít nhất 1 việc la_kcs=True
    assert all(i["la_kcs"] is True for i in items)


def test_thieu_mode_mac_dinh_production(db, orders, lsx_svc, admin, customer):
    to = _to_moi(db)
    _phat_hanh_vao_to_co_kcs(db, orders, lsx_svc, admin, customer, to.id)

    mac_dinh = _ban_phang(db, admin, _authz(db), team_id=to.id)
    tuong_minh = _ban_phang(db, admin, _authz(db), team_id=to.id, mode="production")
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


# --- Thợ (mức Xem `own`) chỉ thấy việc được giao (§7.1) ------------------------------------
def _tho_co_tai_khoan(db, to, *, username, ma_nv, pham_vi: str | None = SCOPE_OWN, viec=()):
    """Một THỢ thật: tài khoản + hồ sơ nhân viên nối với nhau, thuộc tổ `to`.

    Mặc định cấp đúng vai mẫu Công nhân trên dòng của tổ: Xem + phạm vi Của tôi, không quyền chi
    tiết nào (`viec` để bật thêm). `pham_vi=None` thì không cấp gì — test tự cấp."""
    u = User(username=username, name=f"Thợ {ma_nv}", password_hash="x", department_id=to.id)
    db.add(u)
    db.flush()
    db.add(Employee(code=ma_nv, full_name=u.name, department_id=to.id, user_id=u.id))
    db.flush()
    if pham_vi is not None:
        cap_quyen_to(db, u, to, scope=pham_vi, viec=viec)
        db.commit()
    return u


def _giao(db, cv_id: int, employee_id: int) -> None:
    db.add(SanXuatPhanCong(
        cong_viec_id=cv_id, employee_id=employee_id, trang_thai=PC_HOAT_DONG
    ))
    db.commit()


def _emp_id(db, user_id: int) -> int:
    return db.query(Employee).filter_by(user_id=user_id).one().id


def test_tho_chi_thay_viec_duoc_giao(db, orders, lsx_svc, admin, customer):
    """Thợ (Xem phạm vi Của tôi) mở bàn tổ mình: chỉ những việc CÒN đang giao cho chính họ, không
    phải cả tổ."""
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    tho = _tho_co_tai_khoan(db, to, username="tho_board_1", ma_nv="NV-BOARD-1")

    ca_ban = _ban_phang(db, admin, _authz(db), team_id=to.id)["cong_viec"]
    assert len(ca_ban) >= 2, "cần ít nhất 2 việc mới soi được phép lọc"

    # Chưa giao gì → không thấy việc nào, KHÔNG rơi về "thấy hết".
    assert _ban_phang(db, tho, _authz(db), team_id=to.id)["cong_viec"] == []

    _giao(db, ca_ban[0]["id"], _emp_id(db, tho.id))
    thay = _ban_phang(db, tho, _authz(db), team_id=to.id)["cong_viec"]
    assert [w["id"] for w in thay] == [ca_ban[0]["id"]]


def test_to_truong_van_thay_ca_ban(db, orders, lsx_svc, admin, customer):
    """Lọc chỉ áp cho mức `own` — người giữ dòng Cả phòng đứng tại tổ (vai mẫu Tổ trưởng) thấy trọn
    bàn dù không được giao việc nào, và KHÔNG cần đứng tên `head_user_id` của tổ."""
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    truong = _nguoi(db, "truong_board", to)
    cap_quyen_to(db, truong, to, scope=SCOPE_DEPARTMENT)
    db.commit()
    assert to.head_user_id is None

    thay = _ban_phang(db, truong, _authz(db), team_id=to.id)["cong_viec"]
    assert thay
    assert len(thay) == len(_ban_phang(db, admin, _authz(db), team_id=to.id)["cong_viec"])


def test_badge_navbar_cua_tho_khop_so_viec_mo_ra(db, orders, lsx_svc, admin, customer):
    """Badge trên navbar phải đếm đúng số dòng thợ mở ra thấy — báo 12 mà bàn có 2 là nói dối."""
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    tho = _tho_co_tai_khoan(db, to, username="tho_board_2", ma_nv="NV-BOARD-2")
    ca_ban = _ban_phang(db, admin, _authz(db), team_id=to.id)["cong_viec"]
    _giao(db, ca_ban[0]["id"], _emp_id(db, tho.id))

    badge = {t["id"]: t["so_viec_cho"] for t in board.teams(db, tho, _authz(db))}
    so_dong = len(_ban_phang(db, tho, _authz(db), team_id=to.id)["cong_viec"])
    assert badge[to.id] == so_dong == 1


def test_tho_mo_viec_khong_duoc_giao_bi_chan(db, orders, lsx_svc, admin, customer):
    """Không có ở bàn thì cũng không mở được bằng đường link/chi tiết."""
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    tho = _tho_co_tai_khoan(db, to, username="tho_board_3", ma_nv="NV-BOARD-3")
    ca_ban = _ban_phang(db, admin, _authz(db), team_id=to.id)["cong_viec"]
    _giao(db, ca_ban[0]["id"], _emp_id(db, tho.id))

    ct = board.chi_tiet_cong_viec(db, tho, _authz(db), cong_viec_id=ca_ban[0]["id"])
    assert ct["cong_viec"]["id"] == ca_ban[0]["id"]
    # Vai Công nhân không có quyền chi tiết nào → drawer tắt mọi nút, kể cả trên việc của mình.
    assert ct["quyen"] == {
        "run_order": False, "confirm_output": False, "qc": False, "warehouse": False,
    }
    with pytest.raises(PermissionError):
        board.chi_tiet_cong_viec(db, tho, _authz(db), cong_viec_id=ca_ban[1]["id"])


def test_chi_tiet_quyen_muc_own_chi_bat_tren_viec_dang_giao(db, orders, lsx_svc, admin, customer):
    """`quyen` của drawer theo TỪNG việc (`quyen_tren_viec`), hai dòng chồng nhau: Xem Tất cả ở Tổ
    in (thấy trọn bàn) nhưng Thực hiện lệnh chỉ Của tôi (dòng gốc Sản xuất). Nút Thực hiện bật trên
    việc đang giao cho mình, tắt trên việc người khác; quyền không được cấp luôn tắt."""
    c = _cay_san_xuat(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, c.to_in.id)
    u = _tho_co_tai_khoan(db, c.to_in, username="tho_board_own", ma_nv="NV-BOARD-OWN",
                          pham_vi=SCOPE_ALL, viec=())
    cap_quyen_to(db, u, c.goc, scope=SCOPE_OWN, viec=("run_order",), xem=False)
    db.commit()

    ca_ban = _ban_phang(db, u, _authz(db), team_id=c.to_in.id)["cong_viec"]
    assert len(ca_ban) >= 2, "Xem Tất cả ở Tổ in phải thấy trọn bàn"
    _giao(db, ca_ban[0]["id"], _emp_id(db, u.id))

    tat = {"confirm_output": False, "qc": False, "warehouse": False}
    cua_minh = board.chi_tiet_cong_viec(db, u, _authz(db), cong_viec_id=ca_ban[0]["id"])
    assert cua_minh["quyen"] == {"run_order": True, **tat}
    nguoi_khac = board.chi_tiet_cong_viec(db, u, _authz(db), cong_viec_id=ca_ban[1]["id"])
    assert nguoi_khac["quyen"] == {"run_order": False, **tat}

    # Menu nói đúng mức từng việc trên nút Tổ in.
    row = {t["id"]: t for t in board.teams(db, u, _authz(db))}[c.to_in.id]
    assert row["quyen"] == {"read": "all", "run_order": "own"} and row["la_tho"] is False


def test_dong_bang_chay_duoc_theo_quyen_thuc_hien(db, orders, lsx_svc, admin, customer):
    """Nút Bắt đầu / Tạm dừng / Kết thúc ngay trên DÒNG bảng hiện theo `chay_duoc` — cùng luật với
    `quyen` của drawer: chỉ Xem thì tắt hết; Thực hiện lệnh mức Của tôi chỉ bật trên việc đang giao
    cho mình. Hai hình bàn (lệnh, phẳng) phải nói giống nhau."""
    c = _cay_san_xuat(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, c.to_in.id)
    u = _tho_co_tai_khoan(db, c.to_in, username="tho_board_chay", ma_nv="NV-BOARD-CHAY",
                          pham_vi=SCOPE_ALL, viec=())
    db.commit()

    ca_ban = _ban_phang(db, u, _authz(db), team_id=c.to_in.id)["cong_viec"]
    assert len(ca_ban) >= 2
    assert not any(w["chay_duoc"] for w in ca_ban), "chỉ Xem thì dòng không được có nút chạy"

    cap_quyen_to(db, u, c.goc, scope=SCOPE_OWN, viec=("run_order",), xem=False)
    db.commit()
    _giao(db, ca_ban[0]["id"], _emp_id(db, u.id))

    phang = {w["id"]: w["chay_duoc"] for w in _ban_phang(db, u, _authz(db), team_id=c.to_in.id)["cong_viec"]}
    assert phang[ca_ban[0]["id"]] is True
    assert phang[ca_ban[1]["id"]] is False
    lenh = board.work_items(db, u, _authz(db), team_id=c.to_in.id)["lenh"]
    assert {w["id"]: w["chay_duoc"] for l in lenh for w in l["cong_viec"]} == phang


def test_tai_khoan_chua_noi_ho_so_nhan_vien_thi_khong_thay_gi(db, orders, lsx_svc, admin, customer):
    """`employee.user_id` chưa nối ⇒ không biết người đó được giao gì ⇒ bàn trống, không mở toang."""
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    tho = _nguoi(db, "tho_board_4", to)
    cap_quyen_to(db, tho, to, scope=SCOPE_OWN, viec=())
    db.commit()
    assert _ban_phang(db, tho, _authz(db), team_id=to.id)["cong_viec"] == []


def test_teams_noi_ro_vai_tho_de_fe_khong_phai_doan(db, orders, lsx_svc, admin, customer):
    """FE cần biết "tôi vào tổ này với tư cách THỢ" để bật băng *Sản lượng của tôi* (spec §6).

    Service đã tính sẵn — `la_tho` = mức Xem của nút là `own` — trả ra kèm `quyen` chứ đừng để FE tự
    suy từ phạm vi: suy sai một nhánh là thợ mất băng, hoặc tổ trưởng bị gán nhầm vai thợ."""
    to = _to_moi(db)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    tho = _tho_co_tai_khoan(db, to, username="tho_board_vai", ma_nv="NV-BOARD-VAI")
    truong = _tho_co_tai_khoan(db, to, username="truong_board_vai", ma_nv="NV-TRUONG-VAI",
                               pham_vi=SCOPE_DEPARTMENT, viec=BON_VIEC)

    row_tho = {t["id"]: t for t in board.teams(db, tho, _authz(db))}[to.id]
    assert row_tho["la_tho"] is True and row_tho["quyen"] == {"read": "own"}
    row_truong = {t["id"]: t for t in board.teams(db, truong, _authz(db))}[to.id]
    assert row_truong["la_tho"] is False and row_truong["quyen"] == _TAT_CA_5_VIEC
    assert {t["id"]: t["la_tho"] for t in board.teams(db, admin, _authz(db))}[to.id] is False
