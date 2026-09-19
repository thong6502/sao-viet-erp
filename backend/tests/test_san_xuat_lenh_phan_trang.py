"""Bàn tổ đổi trục sang LỆNH: gom nhóm + cắt trang phải ở MÁY CHỦ, và đơn vị trang là LỆNH.

Đơn vị VIỆC vẫn là CÔNG ĐOẠN — một dòng `san_xuat_cong_viec` là một bước của lệnh, và đó vẫn là
thứ tổ bấm Bắt đầu / Ghi sản lượng. Chỉ CÁCH BÀY đổi: các công đoạn ấy bọc dưới đầu mục LỆNH
(hoặc BÀI GHÉP), và trang đếm theo LỆNH. Cắt trang theo BƯỚC thì một lệnh bị xé qua hai trang —
tổ trưởng mở trang 2 thấy một công đoạn trơ trọi không biết của lệnh nào, đúng thứ chủ xưởng bác.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.department import Department
from app.models.lsx import LsxCongDoan
from app.models.san_xuat import SanXuatCongViec
from app.models.san_xuat_thuc_thi import PC_HOAT_DONG, SanXuatPhanCong
from app.repositories.san_xuat_repo import SanXuatRepository
from app.models.user import User
from app.services.san_xuat import release
from tests.quyen_to_fixtures import cap_quyen_to

# Fixtures + helper dùng chung từ test xếp lịch / phát hành — KHÔNG tự INSERT tay.
from tests.test_xep_lich_service import (  # noqa: F401
    _giu_cho_du,
    _hai_lsx_san_sang,
    _in_step,
    _nha_cho,
    admin,
    bg_svc,
    customer,
    db,
    lsx_svc,
    orders,
    xl_svc,
)


def _to_moi(db, ten="Tổ Bế trang", ma="TO-TRANG") -> Department:
    """Tổ SX mới + bật đủ quyền trên dòng tổ cho vai của admin seed (như quản trị tích ma trận)."""
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    cap_quyen_to(db, db.query(User).filter(User.username == "admin").one(), d)
    return d


def _don_het_ve_to(db, lsx_ids: list[int], to_id: int) -> None:
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id.in_(lsx_ids)).update(
        {LsxCongDoan.department_id: to_id}, synchronize_session=False
    )
    db.commit()


@pytest.fixture
def to_co_3_lenh_9_buoc(db, orders, lsx_svc, admin, customer):
    """Một tổ ôm BA lệnh, mỗi lệnh vài công đoạn — đủ để cắt trang 2 lệnh/trang thành 2 trang."""
    to = _to_moi(db)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    c, _d = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    ids = [a.id, b.id, c.id]
    _don_het_ve_to(db, ids, to.id)
    release.phat_hanh(db, lsx_ids=set(ids), actor=admin)
    db.commit()
    return to.id


@pytest.fixture
def to_lenh_gio_lech(db, to_co_3_lenh_9_buoc):
    """Ba lệnh ấy, bước SỚM NHẤT của tổ đặt lệch giờ hẳn nhau + một lệnh chưa xếp giờ.

    Trả `(to_id, thứ tự khoá lệnh mong đợi)`."""
    to_id = to_co_3_lenh_9_buoc
    cvs = db.query(SanXuatCongViec).filter(SanXuatCongViec.department_id == to_id).all()
    theo_lenh: dict[int, list[SanXuatCongViec]] = {}
    for cv in cvs:
        theo_lenh.setdefault(cv.lsx_id, []).append(cv)
    lsx_ids = sorted(theo_lenh)
    assert len(lsx_ids) == 3

    goc = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc)
    # Lệnh thứ 2 chạy TRƯỚC lệnh thứ 1; lệnh thứ 3 chưa xếp giờ ⇒ phải dồn cuối.
    for cv in theo_lenh[lsx_ids[1]]:
        cv.du_kien_bat_dau = goc
    for cv in theo_lenh[lsx_ids[0]]:
        cv.du_kien_bat_dau = goc + timedelta(hours=5)
    for cv in theo_lenh[lsx_ids[2]]:
        cv.du_kien_bat_dau = None
    db.commit()
    return to_id, [("lsx", lsx_ids[1]), ("lsx", lsx_ids[0]), ("lsx", lsx_ids[2])]


@pytest.fixture
def to_co_bai_ghep_2_lenh(db, orders, lsx_svc, bg_svc, admin, customer):
    """Hai lệnh ghép chung một tờ: bước in chung là MỘT công việc mang `bai_ghep_id`."""
    from tests.test_xep_lich_van_de import _gop_in_va_san_sang

    to = _to_moi(db, ten="Tổ In ghép", ma="TO-INGHEP")
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    _nha_cho(db, [a.id, b.id])
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    _gop_in_va_san_sang(db, bg_svc, bg, admin)

    release.phat_hanh(db, lsx_ids={a.id, b.id}, bai_ghep_ids={bg.id}, actor=admin)
    db.commit()
    # Dồn RIÊNG công việc của bài ghép về tổ mới — các bước LSX khác ở tổ cũ, ngoài tầm nhìn tổ này.
    db.query(SanXuatCongViec).filter(SanXuatCongViec.bai_ghep_id == bg.id).update(
        {SanXuatCongViec.department_id: to.id}, synchronize_session=False
    )
    db.commit()
    return to.id


@pytest.fixture
def tho_chi_lam_lenh_thu_3(db, to_co_3_lenh_9_buoc):
    """Một thợ CHỈ được giao việc ở lệnh thứ 3 (theo thứ tự sắp của repo)."""
    from app.models.employee import Employee

    to_id = to_co_3_lenh_9_buoc
    emp = Employee(full_name="Thợ Một Lệnh", code="NV-1LENH", department_id=to_id)
    db.add(emp)
    db.flush()

    rows, _ = SanXuatRepository(db).lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=50)
    khoa_cuoi = rows[-1][0]
    for cv in db.query(SanXuatCongViec).filter(SanXuatCongViec.department_id == to_id).all():
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id else ("lsx", cv.lsx_id)
        if k == khoa_cuoi:
            db.add(SanXuatPhanCong(
                cong_viec_id=cv.id, employee_id=emp.id, trang_thai=PC_HOAT_DONG,
            ))
    db.commit()
    return emp.id


def test_gom_theo_lenh_va_cat_trang_theo_lenh(db, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    repo = SanXuatRepository(db)

    trang1, tong = repo.lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=2)
    assert tong == 3
    assert len(trang1) == 2

    trang2, tong2 = repo.lenh_cua_to_phan_trang({to_id}, trang=2, co_trang=2)
    assert tong2 == 3
    assert len(trang2) == 1
    assert {k for k, _, _ in trang1} & {k for k, _, _ in trang2} == set(), "trang không được trùng lệnh"


def test_sap_theo_buoc_som_nhat_cua_to_lenh_chua_xep_gio_don_cuoi(db, to_lenh_gio_lech):
    """Sắp theo giờ dự kiến của bước SỚM NHẤT của TỔ trong lệnh đó — không phải giờ của lệnh."""
    to_id, mong_doi = to_lenh_gio_lech
    rows, _ = SanXuatRepository(db).lenh_cua_to_phan_trang(
        {to_id}, trang=1, co_trang=50, sap_xep="du_kien")
    assert [k for k, _, _ in rows] == mong_doi


def test_bai_ghep_la_mot_dong_khong_xe_theo_lenh_thanh_vien(db, to_co_bai_ghep_2_lenh):
    to_id = to_co_bai_ghep_2_lenh
    rows, tong = SanXuatRepository(db).lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=50)
    assert tong == 1
    assert rows[0][0][0] == "bai_ghep"


def test_lay_dung_buoc_cua_cac_lenh_trong_trang(db, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    repo = SanXuatRepository(db)
    trang1, _ = repo.lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=2)
    khoa = [k for k, _, _ in trang1]
    rows = repo.cong_viec_cua_lenh({to_id}, khoa)
    assert rows
    for cv in rows:
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id else ("lsx", cv.lsx_id)
        assert k in khoa


def test_loc_cho_xac_nhan_giu_ca_lenh_va_mat_trang_khong_doi(db, to_co_3_lenh_9_buoc):
    """Ô "chờ xác nhận": chỉ còn lệnh chứa công đoạn đang chờ, nhưng lệnh đó vẫn đủ mọi công đoạn
    của tổ và giữ đúng mốc sớm/muộn như bàn không lọc (HAVING, không WHERE). Tập rỗng ⇒ trang rỗng."""
    to_id = to_co_3_lenh_9_buoc
    repo = SanXuatRepository(db)
    tat_ca, _ = repo.lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=10)
    (k0, _, _), (k1, _, _), _k2 = tat_ca
    # Dồn bước của lệnh đầu sang lệnh thứ hai: lệnh thứ hai có hai bước, bước đang chờ là bước MUỘN.
    t0 = datetime(2026, 9, 21, 8, 0)
    som = repo.cong_viec_cua_lenh({to_id}, [k1])[0]
    cho = repo.cong_viec_cua_lenh({to_id}, [k0])[0]
    som.du_kien_bat_dau, som.du_kien_ket_thuc = t0, t0 + timedelta(hours=1)
    cho.lsx_id = som.lsx_id
    cho.du_kien_bat_dau, cho.du_kien_ket_thuc = t0 + timedelta(hours=5), t0 + timedelta(hours=6)
    db.commit()
    khong_loc = {k: (s, m) for k, s, m in repo.lenh_cua_to_phan_trang({to_id}, co_trang=10)[0]}

    rows, tong = repo.lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=10, chi_cong_viec_ids={cho.id})
    assert tong == 1
    assert rows == [(k1, *khong_loc[k1])]
    assert rows[0][1] == t0 or rows[0][1].replace(tzinfo=None) == t0
    assert {cv.id for cv in repo.cong_viec_cua_lenh({to_id}, [k1])} == {som.id, cho.id}

    assert repo.lenh_cua_to_phan_trang({to_id}, chi_cong_viec_ids=set()) == ([], 0)


def test_loc_theo_nguoi_duoc_giao_chay_o_SQL_truoc_khi_cat_trang(
    db, to_co_3_lenh_9_buoc, tho_chi_lam_lenh_thu_3,
):
    """Thợ chỉ được giao việc ở LỆNH cuối. Lọc sau khi cắt trang thì trang 1 rỗng — sai."""
    to_id = to_co_3_lenh_9_buoc
    emp_id = tho_chi_lam_lenh_thu_3
    rows, tong = SanXuatRepository(db).lenh_cua_to_phan_trang(
        {to_id}, employee_id=emp_id, trang=1, co_trang=2)
    assert tong == 1
    assert len(rows) == 1


# --- Tầng service: work_items gom theo LỆNH nhưng THẺ VIỆC vẫn là CÔNG ĐOẠN -------------------
def _authz(db):
    from app.repositories.rbac_repo import RoleRepository
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def test_work_items_gom_theo_lenh_the_viec_van_la_cong_doan(db, admin, to_co_3_lenh_9_buoc):
    from app.services.san_xuat import board

    to_id = to_co_3_lenh_9_buoc
    d = board.work_items(db, admin, _authz(db), team_id=to_id, co_trang=2)

    assert d["nhom"] == "lenh"
    assert d["trang"] == {"trang": 1, "co_trang": 2, "tong": 3}
    assert len(d["lenh"]) == 2

    l0 = d["lenh"][0]
    assert l0["nguon_loai"] in ("lsx", "bai_ghep")
    assert l0["nguon_ma"], "không có mã lệnh thì tổ trưởng vẫn không biết công đoạn này của lệnh nào"
    assert l0["so_viec"] == len(l0["cong_viec"])
    assert set(l0["digest"]) == {"released", "running", "paused", "completed"}
    assert sum(l0["digest"].values()) == l0["so_viec"]
    # Thẻ việc bên trong giữ ĐÚNG hình cũ — bốn view đọc chung một hình.
    assert {"id", "ten_cong_doan", "trang_thai", "du_kien_bat_dau"} <= set(l0["cong_viec"][0])


def test_work_items_khong_xe_mot_lenh_qua_hai_trang(db, admin, to_co_3_lenh_9_buoc):
    from app.services.san_xuat import board

    to_id = to_co_3_lenh_9_buoc
    az = _authz(db)
    t1 = board.work_items(db, admin, az, team_id=to_id, trang=1, co_trang=2)
    t2 = board.work_items(db, admin, az, team_id=to_id, trang=2, co_trang=2)
    khoa1 = {(x["nguon_loai"], x["lsx_id"], x["bai_ghep_id"]) for x in t1["lenh"]}
    khoa2 = {(x["nguon_loai"], x["lsx_id"], x["bai_ghep_id"]) for x in t2["lenh"]}
    assert khoa1 & khoa2 == set()
    ids1 = {cv["id"] for x in t1["lenh"] for cv in x["cong_viec"]}
    ids2 = {cv["id"] for x in t2["lenh"] for cv in x["cong_viec"]}
    assert ids1 & ids2 == set(), "một bước chỉ được thuộc đúng một trang"


def test_work_items_che_do_phang_giu_mang_buoc_cho_gantt(db, admin, to_co_3_lenh_9_buoc):
    from app.services.san_xuat import board

    to_id = to_co_3_lenh_9_buoc
    d = board.work_items(db, admin, _authz(db), team_id=to_id, nhom="phang")
    assert d["nhom"] == "phang"
    assert d["cong_viec"] and "lenh" not in d
    assert {"id", "ten_cong_doan", "trang_thai"} <= set(d["cong_viec"][0])


def test_cua_so_ngay_KHONG_nuot_buoc_chua_xep_gio(db, admin, to_co_3_lenh_9_buoc):
    """Bước chưa xếp giờ nằm ở khúc "chưa định giờ" của Gantt — cắt nó theo cửa sổ là làm nó biến
    mất khỏi MỌI khoảng, không màn nào tìm lại được."""
    from datetime import date

    from app.services.san_xuat import board

    to_id = to_co_3_lenh_9_buoc
    db.query(SanXuatCongViec).filter(SanXuatCongViec.department_id == to_id).update(
        {SanXuatCongViec.du_kien_bat_dau: None, SanXuatCongViec.du_kien_ket_thuc: None},
        synchronize_session=False,
    )
    db.commit()
    d = board.work_items(
        db, admin, _authz(db), team_id=to_id, nhom="phang",
        tu_ngay=date(2026, 9, 1), den_ngay=date(2026, 9, 2),
    )
    assert d["cong_viec"], "bước chưa xếp giờ phải còn nguyên"


def test_tim_kiem_loc_o_may_chu_truoc_khi_cat_trang(db, admin, to_co_3_lenh_9_buoc):
    """Ô tìm kiếm của bàn phải lọc Ở SQL: gõ mã một lệnh thì `tong` co lại còn 1, chứ không phải
    trả về cả ba lệnh rồi để màn tự giấu bớt — giấu ở JS thì từ khoá chỉ soi được đúng trang
    đang hiện."""
    from app.models.lsx import Lsx
    from app.services.san_xuat import board

    to_id = to_co_3_lenh_9_buoc
    ca_ban = board.work_items(db, admin, _authz(db), team_id=to_id)
    assert ca_ban["trang"]["tong"] == 3
    ma = ca_ban["lenh"][0]["nguon_ma"]

    d = board.work_items(db, admin, _authz(db), team_id=to_id, tim=ma)
    assert d["trang"]["tong"] == 1
    assert [x["nguon_ma"] for x in d["lenh"]] == [ma]
    # Khớp theo tên CÔNG ĐOẠN cũng phải ra lệnh chứa bước ấy.
    ten_cd = d["lenh"][0]["cong_viec"][0]["ten_cong_doan"]
    assert board.work_items(db, admin, _authz(db), team_id=to_id, tim=ten_cd)["trang"]["tong"] >= 1
    # Từ khoá không khớp gì ⇒ rỗng hẳn, không rơi về "trả tất".
    assert board.work_items(db, admin, _authz(db), team_id=to_id,
                            tim="khong-co-lenh-nao-ten-the-nay")["trang"]["tong"] == 0
    # Lệnh tra được bằng TÊN chứ không chỉ bằng mã.
    ten_lsx = db.get(Lsx, d["lenh"][0]["lsx_id"]).ten
    assert board.work_items(db, admin, _authz(db), team_id=to_id, tim=ten_lsx)["trang"]["tong"] >= 1


def test_ten_khach_xuong_ban_to_va_tim_duoc_theo_khach(db, admin, to_co_3_lenh_9_buoc):
    """Tổ nhìn bàn phải biết hàng của AI: dòng lệnh, thẻ việc lẫn ngăn chi tiết mang tên khách
    (lệnh → đơn → khách), đi qua được schema trả về, và ô tìm kiếm tra được theo tên khách."""
    from app.models.customer import Customer
    from app.models.lsx import Lsx
    from app.models.order import Order
    from app.schemas.san_xuat import WorkItemChiTietOut, WorkItemsOut
    from app.services.san_xuat import board

    to_id = to_co_3_lenh_9_buoc
    ca_ban = board.work_items(db, admin, _authz(db), team_id=to_id)
    # Đổi khách của MỘT đơn chỉ chứa đúng một lệnh trên bàn — lệnh ấy phải mang tên khách mới.
    don_cua = {l["lsx_id"]: db.get(Lsx, l["lsx_id"]).order_id for l in ca_ban["lenh"]}
    lsx_rieng = next(i for i, o in don_cua.items() if list(don_cua.values()).count(o) == 1)
    moi = Customer(code="KH-MP", name="Bao bì Minh Phát")
    db.add(moi)
    db.flush()
    db.get(Order, don_cua[lsx_rieng]).customer_id = moi.id
    db.commit()

    ban = board.work_items(db, admin, _authz(db), team_id=to_id)
    khach = {l["lsx_id"]: l["khach_hang"] for l in ban["lenh"]}
    assert khach[lsx_rieng] == "Bao bì Minh Phát"
    assert {v for k, v in khach.items() if k != lsx_rieng} == {"KH Xếp lịch"}
    for l in ban["lenh"]:
        assert {w["khach_hang"] for w in l["cong_viec"]} == {l["khach_hang"]}
    # Pydantic bỏ IM LẶNG khoá không khai ở schema — soi qua schema, không chỉ soi dict.
    out = WorkItemsOut.model_validate(ban)
    assert {l.khach_hang for l in out.lenh} == {"Bao bì Minh Phát", "KH Xếp lịch"}

    cv_id = next(l for l in ban["lenh"] if l["lsx_id"] == lsx_rieng)["cong_viec"][0]["id"]
    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv_id)
    assert WorkItemChiTietOut.model_validate(ct).cong_viec.khach_hang == "Bao bì Minh Phát"

    tim = board.work_items(db, admin, _authz(db), team_id=to_id, tim="minh phát")
    assert tim["trang"]["tong"] == 1
    assert [l["lsx_id"] for l in tim["lenh"]] == [lsx_rieng]


def test_bai_ghep_mang_ten_khach_cac_lenh_thanh_vien(db, admin, to_co_bai_ghep_2_lenh):
    """Bài ghép chạy chung nhiều lệnh: khách lấy từ lệnh thành viên, trùng khách thì chỉ ghi một
    lần; tìm theo tên khách ra được bài ghép."""
    from app.services.san_xuat import board

    to_id = to_co_bai_ghep_2_lenh
    ban = board.work_items(db, admin, _authz(db), team_id=to_id)
    assert [(l["nguon_loai"], l["khach_hang"]) for l in ban["lenh"]] == [("bai_ghep", "KH Xếp lịch")]
    assert {w["khach_hang"] for w in ban["lenh"][0]["cong_viec"]} == {"KH Xếp lịch"}
    assert board.work_items(db, admin, _authz(db), team_id=to_id, tim="xếp lịch")["trang"]["tong"] == 1


@pytest.fixture
def to_nhan_lech_ngay(db, to_co_3_lenh_9_buoc):
    """Ba lệnh tổ nhận ở ba lúc khác nhau (UTC thật). Trả `(to_id, [khoá theo lúc nhận TĂNG dần])`."""
    to_id = to_co_3_lenh_9_buoc
    cvs = db.query(SanXuatCongViec).filter(SanXuatCongViec.department_id == to_id).all()
    theo_lenh: dict[int, list[SanXuatCongViec]] = {}
    for cv in cvs:
        theo_lenh.setdefault(cv.lsx_id, []).append(cv)
    a, b, c = sorted(theo_lenh)
    # b nhận sớm nhất, rồi c, rồi a — lệch hẳn thứ tự id để test không đỗ nhờ trùng hợp.
    moc = {b: datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc),
           c: datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc),
           a: datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc)}
    for lid, ds in theo_lenh.items():
        for i, cv in enumerate(ds):
            cv.created_at = moc[lid] + timedelta(minutes=i)
    db.commit()
    return to_id, [("lsx", b), ("lsx", c), ("lsx", a)]


def test_mac_dinh_lenh_nhan_sau_nam_tren(db, to_nhan_lech_ngay):
    """Chủ xưởng 19/09/2026: cái nào phát hành sau thì nằm trên đầu."""
    to_id, tang = to_nhan_lech_ngay
    repo = SanXuatRepository(db)
    rows, _ = repo.lenh_cua_to_phan_trang({to_id}, co_trang=50)
    assert [k for k, _, _ in rows] == list(reversed(tang))
    rows, _ = repo.lenh_cua_to_phan_trang({to_id}, co_trang=50, sap_xep="cu_nhan")
    assert [k for k, _, _ in rows] == tang


def test_loc_theo_luc_nhan_truoc_khi_cat_trang(db, to_nhan_lech_ngay):
    to_id, tang = to_nhan_lech_ngay
    repo = SanXuatRepository(db)
    rows, tong = repo.lenh_cua_to_phan_trang(
        {to_id}, co_trang=1,
        nhan_tu=datetime(2026, 9, 11, tzinfo=timezone.utc),
        nhan_den=datetime(2026, 9, 16, tzinfo=timezone.utc))
    assert tong == 2, "đếm tổng SAU khi lọc — trang mới đúng số"
    assert [k for k, _, _ in rows] == [tang[2]]


def test_loc_trang_thai_giu_lenh_co_buoc_khop(db, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    repo = SanXuatRepository(db)
    assert repo.lenh_cua_to_phan_trang({to_id}, trang_thai={"running"}) == ([], 0)
    cv = db.query(SanXuatCongViec).filter(SanXuatCongViec.department_id == to_id).first()
    cv.trang_thai = "running"
    db.commit()
    rows, tong = repo.lenh_cua_to_phan_trang({to_id}, trang_thai={"running", "paused"})
    assert tong == 1
    assert rows[0][0] == ("lsx", cv.lsx_id)


def test_board_loc_trang_thai_chi_bay_buoc_khop_va_ngay_la_ngay_xuong(
        db, admin, to_co_3_lenh_9_buoc):
    """Qua service: trong lệnh chỉ còn bước khớp trạng thái; `nhan_tu/nhan_den` là NGÀY XƯỞNG."""
    from datetime import date

    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService
    from app.services.san_xuat import board
    from app.services.gio_xuong import ve_gio_xuong

    to_id = to_co_3_lenh_9_buoc
    cvs = db.query(SanXuatCongViec).filter(SanXuatCongViec.department_id == to_id).all()
    chay = cvs[0]
    chay.trang_thai = "running"
    db.commit()
    authz = AuthorizationService(RoleRepository(db))
    kq = board.work_items(db, admin, authz, team_id=to_id, trang_thai={"running"})
    assert [cv["id"] for l in kq["lenh"] for cv in l["cong_viec"]] == [chay.id]

    ngay = ve_gio_xuong(chay.created_at).date()
    kq = board.work_items(db, admin, authz, team_id=to_id, nhan_tu=ngay, nhan_den=ngay)
    assert kq["trang"]["tong"] == 3
    kq = board.work_items(db, admin, authz, team_id=to_id, nhan_tu=ngay + timedelta(days=1))
    assert kq["trang"]["tong"] == 0
