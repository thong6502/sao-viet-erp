"""Thực hiện sản xuất — Giai đoạn 1 (nền phát hành): thành phần liên thông + snapshot gói phát hành.

Soi đúng backbone §3–§4: gói/phiên bản/công việc đóng băng, một-bài-ghép-một-công-việc (§3.3),
suy nhóm thành phẩm từ OrderLine.nhom (§3.1), đánh công đoạn cuối nhóm khi rõ ràng (§4.4, KCS
theo lệnh mg 0306), idempotent ở mức
gói (chưa làm versioning cập nhật). Tái dùng fixtures + helper của test xếp lịch.
"""
from __future__ import annotations

import pytest

from app.models.department import Department
from app.models.lsx import LB_MAY, LsxCongDoan, LsxCongDoanPhuThuoc
from app.models.order import OrderLine
from app.models.san_xuat import (
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatNhom,
    SanXuatPhienBan,
    SanXuatPhuThuoc,
)
from app.repositories.cong_doan_repo import CongDoanRepository
from app.repositories.san_xuat_kcs_tieu_chi_repo import SanXuatKcsTieuChiRepository
from app.repositories.san_xuat_repo import SanXuatRepository
from app.services.cong_doan_service import CongDoanService
from app.services.san_xuat import component, release
from app.services.san_xuat_kcs_tieu_chi_service import SanXuatKcsTieuChiService

# Fixtures + helper dùng chung từ test xếp lịch.
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


def _steps(db, lsx_id):
    return (
        db.query(LsxCongDoan)
        .filter(LsxCongDoan.lsx_id == lsx_id)
        .order_by(LsxCongDoan.thu_tu, LsxCongDoan.id)
        .all()
    )


def _to_hoan_thien(db) -> Department:
    """Một tổ SX thường — công đoạn cuối do tổ nào làm cũng được (KCS theo lệnh, mg 0306)."""
    d = Department(name="Tổ Hoàn Thiện Xưởng", code="TO-HT-XL", la_san_xuat=True)
    db.add(d)
    db.flush()
    return d


def _cong_doan(db, ma: str):
    """Công đoạn danh mục tối thiểu (Task 3) — mượn CongDoanService cho đúng validate thay vì
    ORM trần, để `checklist_theo_cong_doan()` join đúng chỗ khi phát hành."""
    svc = CongDoanService(CongDoanRepository(db))
    return svc.create(dict(
        ma=ma, ten=ma, nhom="print",
        che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty", first_unit_floor=0,
    ))


def _tieu_chi(db, ma: str, *, cong_doan_id: int, active=True, thu_tu=0):
    """Một HẠNG MỤC KIỂM của MỘT công đoạn (mg `0285` — không còn nhiều-nhiều)."""
    svc = SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db))
    return svc.create(dict(
        ma=ma, ten=ma, active=active, thu_tu=thu_tu, cong_doan_id=cong_doan_id,
    ))


def _them_buoc(
    db, lsx_id, *, thu_tu, ten, department_id, cong_doan_id=None,
) -> LsxCongDoan:
    """Thêm MỘT bước routing thủ công vào LSX — engine giá không cần chạy lại, chỉ cần một
    `LsxCongDoan` mang đúng tổ để soi snapshot. `la_kcs_cuoi` suy TỰ ĐỘNG lúc `phat_hanh` từ "bước
    này có phải CUỐI routing của LSX" — không xét tổ (KCS theo lệnh, mg 0306).
    `cong_doan_id`: neo tới danh mục công đoạn để checklist KCS gắn đúng chỗ (ô "tiêu chí bổ sung"
    riêng lệnh đã GỠ ở mg `0283` — `docs/design-kcs-theo-cong-doan.md` mục 5)."""
    buoc = LsxCongDoan(
        lsx_id=lsx_id, thu_tu=thu_tu, ten=ten, nhom="finishing", loai_buoc=LB_MAY,
        department_id=department_id, cong_doan_id=cong_doan_id,
        so_luong_vao=1000, so_luong_ra=1000, don_vi_vao="cai", don_vi_ra="cai",
    )
    db.add(buoc)
    db.flush()
    return buoc


# --- Snapshot gói phát hành: mỗi công đoạn LSX một công việc, có gói + phiên bản ------------
def test_phat_hanh_dung_goi_phien_ban_va_cong_viec(db, orders, lsx_svc, admin, customer):
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    assert goi.ma.startswith("GPH")
    assert db.query(SanXuatPhienBan).filter_by(goi_id=goi.id, so=1).count() == 1

    so_buoc = len(_steps(db, a.id))
    cvs = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, lsx_id=a.id).all()
    assert so_buoc > 0 and len(cvs) == so_buoc
    # Snapshot mang tên công đoạn + neo step_key (không rỗng).
    assert all(cv.ten_cong_doan and cv.step_key for cv in cvs)

    # Nhóm thành phẩm được suy + gắn thành viên.
    member = SanXuatRepository(db).member_of_lsx(a.id)
    assert member is not None and member.nhom_id


# --- Thành phần liên thông: cùng (order_id, nhom) kéo nhau vào một gói (§4.1) ----------------
def test_thanh_phan_lien_thong_cung_nhom(db, orders, lsx_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for l in (a, b):
        db.get(OrderLine, l.order_line_id).nhom = "Sách A5"
    db.commit()

    tp = component.thanh_phan_lien_thong(SanXuatRepository(db), {a.id})
    assert tp.lsx_ids == {a.id, b.id}


def test_khac_nhom_khong_keo_nhau(db, orders, lsx_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    db.get(OrderLine, a.order_line_id).nhom = "Bìa"
    db.get(OrderLine, b.order_line_id).nhom = "Ruột"
    db.commit()

    tp = component.thanh_phan_lien_thong(SanXuatRepository(db), {a.id})
    assert tp.lsx_ids == {a.id}


# --- Công đoạn cuối: bước cuối routing → đánh dấu + chốt lệnh thân chính (§3.2/§4.4) ---------
def test_kcs_cuoi_danh_dau_va_than_chinh(db, orders, lsx_svc, admin, customer):
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    steps = _steps(db, a.id)

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cvs = db.query(SanXuatCongViec).filter_by(goi_id=goi.id).all()
    cuoi = [cv for cv in cvs if cv.la_kcs_cuoi]
    assert [cv.step_key for cv in cuoi] == [steps[-1].step_key]   # đúng bước CUỐI, tổ nào cũng được

    member = SanXuatRepository(db).member_of_lsx(a.id)
    assert member.la_than_chinh
    nhom = db.get(SanXuatNhom, member.nhom_id)
    assert nhom.than_chinh_lsx_id == a.id


# --- Cửa soi read-only: một nhóm nhiều công đoạn cuối thì báo chặn; một thì im (§4.4) --------
def test_van_de_phat_hanh_bao_nhom_nhieu_cong_doan_cuoi(db, orders, lsx_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Một lệnh lẻ: bước cuối là công đoạn cuối, không cần tổ KCS nào ⇒ không chặn.
    assert release.van_de_phat_hanh(db, lsx_ids={a.id}) == []

    # Hai lệnh cùng nhóm, mỗi lệnh tự kết thúc ⇒ hai công đoạn cuối, chưa rõ chỗ ra thành phẩm.
    db.get(OrderLine, a.order_line_id).nhom = "Kỷ yếu"
    db.get(OrderLine, b.order_line_id).nhom = "Kỷ yếu"
    db.commit()
    vd = release.van_de_phat_hanh(db, lsx_ids={a.id, b.id})
    assert [i["ma"] for i in vd] == ["kcs_cuoi_nhieu"]

    # Nối bước cuối lệnh phụ sang bước cuối thân chính ⇒ còn MỘT công đoạn cuối.
    db.add(LsxCongDoanPhuThuoc(
        buoc_truoc_id=_steps(db, b.id)[-1].id, buoc_sau_id=_steps(db, a.id)[-1].id,
    ))
    db.commit()
    assert release.van_de_phat_hanh(db, lsx_ids={a.id, b.id}) == []


# --- Công đoạn cuối theo VỊ TRÍ (bước cuối), không đồng nhất theo tổ --------------------------
def test_snapshot_cong_doan_cuoi_theo_vi_tri_khong_theo_to(db, orders, lsx_svc, admin, customer):
    """Dán và Đóng gói CÙNG một tổ nhưng khác VỊ TRÍ trong routing — snapshot phát hành phải theo
    TỪNG BƯỚC (chỉ bước CUỐI là công đoạn cuối), không đồng nhất theo tổ."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    to = _to_hoan_thien(db)
    _them_buoc(db, a.id, thu_tu=1, ten="Dán", department_id=to.id)
    _them_buoc(db, a.id, thu_tu=2, ten="Đóng gói", department_id=to.id)
    db.commit()

    assert release.van_de_phat_hanh(db, lsx_ids={a.id}) == []

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    steps = _steps(db, a.id)
    dan_step = next(s for s in steps if s.ten == "Dán")
    dg_step = next(s for s in steps if s.ten == "Đóng gói")
    cv_dan = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=dan_step.step_key).one()
    cv_dg = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=dg_step.step_key).one()

    assert cv_dan.department_id == to.id and cv_dan.la_kcs_cuoi is False
    assert cv_dg.department_id == to.id and cv_dg.la_kcs_cuoi is True


# --- Idempotent ở mức gói: phát hành lại KHÔNG đẻ gói trùng (versioning §4.3 để lát sau) -----
def test_phat_hanh_lai_khong_de_goi_trung(db, orders, lsx_svc, admin, customer):
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    g1 = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()
    g2 = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()
    assert g1.id == g2.id
    assert db.query(SanXuatGoiPhatHanh).count() == 1


# --- Bài ghép = MỘT công việc chung; bước LSX bị phủ KHÔNG đẻ trùng (§3.3) -------------------
def test_bai_ghep_mot_cong_viec_khong_de_trung(db, orders, lsx_svc, bg_svc, admin, customer):
    from tests.test_xep_lich_van_de import _gop_in_va_san_sang

    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    _nha_cho(db, [a.id, b.id])
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    _gop_in_va_san_sang(db, bg_svc, bg, admin)

    repo = SanXuatRepository(db)
    covered = repo.step_keys_da_ghep(bg.id)
    assert covered  # bước in của hai lệnh đã bị gộp

    goi = release.phat_hanh(db, lsx_ids={a.id, b.id}, bai_ghep_ids={bg.id}, actor=admin)
    db.commit()

    # Đúng MỘT công việc mang bai_ghep_id (bước in chung), phủ nhiều bước LSX.
    chung = db.query(SanXuatCongViec).filter(
        SanXuatCongViec.goi_id == goi.id, SanXuatCongViec.bai_ghep_id.is_not(None)
    ).all()
    assert len(chung) == 1

    # Không công việc LSX nào trùng step_key đã bị phủ.
    lsx_cvs = db.query(SanXuatCongViec).filter(
        SanXuatCongViec.goi_id == goi.id, SanXuatCongViec.lsx_id.is_not(None)
    ).all()
    assert all(cv.step_key not in covered for cv in lsx_cvs)


def test_dung_diem_toa_sinh_canh_theo_so_con(db, orders, lsx_svc, bg_svc, admin, customer):
    from tests.test_xep_lich_van_de import _gop_in_va_san_sang

    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Mỗi lệnh thêm bước "Xả tờ" (sau in) để còn bước RIÊNG cho điểm toả tách sản lượng vào.
    for lsx in (a, b):
        db.add(LsxCongDoan(
            lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
            may_id=_in_step(db, lsx.id).may_id, so_luong_vao=5000,
            don_vi_vao="to", don_vi_ra="to",
        ))
    db.commit()
    _nha_cho(db, [a.id, b.id])
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    _gop_in_va_san_sang(db, bg_svc, bg, admin)
    bg = bg_svc._get(bg.id)
    for tv in bg.thanh_viens:
        tv.so_con_tren_to = 8 if tv.lsx_id == a.id else 4
    db.commit()

    repo = SanXuatRepository(db)
    covered = repo.step_keys_da_ghep(bg.id)
    goi = release.phat_hanh(db, lsx_ids={a.id, b.id}, bai_ghep_ids={bg.id}, actor=admin)
    db.commit()

    cvs_a = [
        cv for cv in db.query(SanXuatCongViec).filter_by(goi_id=goi.id, lsx_id=a.id).all()
    ]
    cvs_b = [
        cv for cv in db.query(SanXuatCongViec).filter_by(goi_id=goi.id, lsx_id=b.id).all()
    ]
    assert cvs_a and cvs_b  # mỗi LSX còn ít nhất một bước RIÊNG sau bước chung
    canh_a = db.query(SanXuatPhuThuoc).filter(
        SanXuatPhuThuoc.dich_cong_viec_id.in_([cv.id for cv in cvs_a])
    ).all()
    canh_b = db.query(SanXuatPhuThuoc).filter(
        SanXuatPhuThuoc.dich_cong_viec_id.in_([cv.id for cv in cvs_b])
    ).all()
    assert len(canh_a) == 1 and float(canh_a[0].ty_le_ghep) == 8.0
    assert len(canh_b) == 1 and float(canh_b[0].ty_le_ghep) == 4.0
    nguon_ids = {c.nguon_cong_viec_id for c in canh_a + canh_b}
    assert len(nguon_ids) == 1  # cùng một công việc chung là điểm toả cho cả hai nhánh
    cv_nguon = db.get(SanXuatCongViec, next(iter(nguon_ids)))
    assert cv_nguon.bai_ghep_id == bg.id


# --- Checklist KCS đóng băng vào snapshot khi phát hành (Task 3) -----------------------------
def test_snapshot_checklist_chi_lay_tieu_chi_active(db, orders, lsx_svc, admin, customer):
    """Bước neo `cong_doan_id` tới danh mục có 2 tiêu chí (1 active, 1 đã ngừng) — snapshot chỉ
    đóng băng tiêu chí ACTIVE, nguồn `danh_muc`."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    to = _to_hoan_thien(db)
    cd = _cong_doan(db, "CD-KT-CUOI")
    tc_on = _tieu_chi(db, "TC-ON", active=True, thu_tu=1, cong_doan_id=cd.id)
    _tieu_chi(db, "TC-OFF", active=False, thu_tu=2, cong_doan_id=cd.id)
    buoc = _them_buoc(
        db, a.id, thu_tu=1, ten="Kiểm tra cuối", department_id=to.id,
        cong_doan_id=cd.id,
    )
    db.commit()

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cv = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=buoc.step_key).one()
    assert cv.kcs_tieu_chi_json == [{
        "tieu_chi_id": tc_on.id, "ma": "TC-ON", "ten": "TC-ON", "huong_dan": None,
        "bat_buoc": True, "nguon": "danh_muc", "thu_tu": 1,
    }]


def test_snapshot_checklist_moi_buoc_co_tieu_chi(db, orders, lsx_svc, admin, customer):
    """Checklist chụp cho MỌI bước mà công đoạn có tiêu chí trong danh mục, không riêng bước cuối
    (KCS kiểm được mọi công đoạn — mg 0306). Bước giữa ở tổ In có tiêu chí ⇒ có checklist, và vẫn
    không phải công đoạn cuối."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    to_in = Department(name="Tổ In Điểm Kiểm", code="TO-IN-DK", la_san_xuat=True)
    db.add(to_in)
    db.flush()
    to = _to_hoan_thien(db)
    cd = _cong_doan(db, "CD-IN-GIUA")
    tc = _tieu_chi(db, "TC-CHONG-MAU", active=True, thu_tu=1, cong_doan_id=cd.id)
    giua = _them_buoc(db, a.id, thu_tu=1, ten="In offset", department_id=to_in.id, cong_doan_id=cd.id)
    cuoi = _them_buoc(db, a.id, thu_tu=2, ten="Đóng gói", department_id=to.id)
    db.commit()

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cv_giua = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=giua.step_key).one()
    assert cv_giua.la_kcs_cuoi is False
    assert [t["tieu_chi_id"] for t in cv_giua.kcs_tieu_chi_json] == [tc.id]

    # Công đoạn cuối KHÔNG có tiêu chí ⇒ NULL chứ không phải `[]` (form KCS không hiện checklist).
    cv_cuoi = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=cuoi.step_key).one()
    assert cv_cuoi.la_kcs_cuoi is True and cv_cuoi.kcs_tieu_chi_json is None


def test_snapshot_checklist_bat_bien_sau_khi_sua_danh_muc(db, orders, lsx_svc, admin, customer):
    """Snapshot đã phát hành PHẢI đứng yên — sửa danh mục (ngừng active) SAU khi phát hành không
    được lan ngược vào `SanXuatCongViec.kcs_tieu_chi_json` đã đóng băng."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    to = _to_hoan_thien(db)
    cd = _cong_doan(db, "CD-KT-CUOI-3")
    tc = _tieu_chi(db, "TC-BAT-BIEN", active=True, thu_tu=1, cong_doan_id=cd.id)
    buoc = _them_buoc(
        db, a.id, thu_tu=1, ten="Kiểm tra cuối", department_id=to.id,
        cong_doan_id=cd.id,
    )
    db.commit()

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    truoc = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=buoc.step_key).one()
    checklist_truoc = truoc.kcs_tieu_chi_json
    assert len(checklist_truoc) == 1

    # Ngừng dùng tiêu chí ở danh mục SAU khi đã phát hành.
    tc_svc = SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db))
    tc_svc.dat_active(tc.id, False)
    db.commit()
    db.expire_all()   # đọc lại THẬT từ DB, không phải cache Python đang giữ

    sau = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=buoc.step_key).one()
    assert sau.kcs_tieu_chi_json == checklist_truoc


# --- Ảnh chụp KHUÔN + nhà gia công lúc phát hành (chốt 04/09/2026) ---------------------------
def test_phat_hanh_chup_khuon_va_nha_gia_cong(db, orders, lsx_svc, admin, customer):
    """Khuôn được CHỤP chứ không tra sống: bàn tổ phải thấy đúng con dao đã chốt lúc phát hành, kể
    cả khi kế hoạch đổi dao sau đó. Nhà gia công cũng chụp — không có nó thì chip "Ngoài · nơi làm"
    ở các màn xưởng phải tra ngược lệnh mới vẽ được."""
    from app.models.khuon_be import KhuonBe

    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    dao = KhuonBe(ma="KB-0001", ten="Dao bế hộp A", loai="khuon_be", so_ke="Kệ A3",
                  tinh_trang="dang_dung")
    db.add(dao)
    db.flush()
    steps = _steps(db, a.id)
    steps[0].khuon_be_id = dao.id
    # Bước thuê ngoài THÊM MỚI, không mượn bước đã có: lệnh mẫu chỉ một bước nên gán cả dao lẫn nhà
    # gia công lên nó thì không còn bước nào để soi nhánh "không trỏ dao".
    ngoai = _them_buoc(db, a.id, thu_tu=99, ten="Cán màng",
                       department_id=steps[0].department_id)
    ngoai.nha_cung_cap = "Cơ sở Minh Phát"
    db.flush()

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()
    cvs = {cv.step_key: cv for cv in
           db.query(SanXuatCongViec).filter_by(goi_id=goi.id, lsx_id=a.id).all()}

    cv_dao = cvs[steps[0].step_key]
    assert cv_dao.khuon_json and cv_dao.khuon_json["ma"] == "KB-0001"
    assert cv_dao.khuon_json["so_ke"] == "Kệ A3"
    # Chưa ai tích nhận — cột phải TRỐNG, không phải "đã nhận sẵn": đúng cái sẽ chặn nút Bắt đầu.
    assert cv_dao.khuon_nhan_luc is None and cv_dao.khuon_tra_luc is None
    # Bước không trỏ dao → None, không phải dict rỗng (rỗng đọc như "có khuôn mà mất thông tin").
    assert cvs[ngoai.step_key].khuon_json is None
    assert cvs[ngoai.step_key].nha_cung_cap == "Cơ sở Minh Phát"


def test_phat_hanh_khong_mang_dau_viec_hay_tien_vao_cong_viec(
    db, orders, lsx_svc, admin, customer,
):
    """⭐ Công việc phát hành KHÔNG mang ảnh chụp khoán nào (18/09/2026, mg `0320`).

    Trước đó bước lệnh ghim đầu việc (`khoan_json`) rồi phát hành chép nguyên xuống công việc. Bước
    thôi chọn việc khoán — thợ chọn LÚC GHI MẺ ở bàn tổ, mẻ mới là chỗ chụp tên · ĐVT · đơn giá.
    Bài này canh cho cột ấy (và `don_gia_hd` gỡ 11/09) khỏi mọc lại trên công việc.
    """
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()
    cvs = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, lsx_id=a.id).all()

    assert cvs
    for cv in cvs:
        assert not hasattr(cv, "khoan_json") and not hasattr(cv, "don_gia_hd")
