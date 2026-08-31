"""Thực hiện sản xuất — Giai đoạn 1 (nền phát hành): thành phần liên thông + snapshot gói phát hành.

Soi đúng backbone §3–§4: gói/phiên bản/công việc đóng băng, một-bài-ghép-một-công-việc (§3.3),
suy nhóm thành phẩm từ OrderLine.nhom (§3.1), đánh KCS-cuối khi rõ ràng (§4.4), idempotent ở mức
gói (chưa làm versioning cập nhật). Tái dùng fixtures + helper của test xếp lịch.
"""
from __future__ import annotations

from app.models.department import Department
from app.models.lsx import LB_MAY, LsxCongDoan
from app.models.order import OrderLine
from app.models.san_xuat import (
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatNhom,
    SanXuatPhienBan,
    SanXuatPhuThuoc,
)
from app.repositories.san_xuat_repo import SanXuatRepository
from app.services.san_xuat import component, release

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


def _kcs_dept(db) -> Department:
    d = Department(name="KCS Xưởng", code="KCS-XL", is_kcs=True)
    db.add(d)
    db.flush()
    return d


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


# --- KCS-cuối: bước KCS ở cuối routing → đánh dấu + chốt lệnh thân chính (§3.2/§4.4) ---------
def test_kcs_cuoi_danh_dau_va_than_chinh(db, orders, lsx_svc, admin, customer):
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    kcs = _kcs_dept(db)
    steps = _steps(db, a.id)
    steps[-1].department_id = kcs.id
    db.commit()

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cv_cuoi = db.query(SanXuatCongViec).filter_by(
        goi_id=goi.id, step_key=steps[-1].step_key
    ).one()
    assert cv_cuoi.la_kcs and cv_cuoi.la_kcs_cuoi

    member = SanXuatRepository(db).member_of_lsx(a.id)
    assert member.la_than_chinh
    nhom = db.get(SanXuatNhom, member.nhom_id)
    assert nhom.than_chinh_lsx_id == a.id


# --- Cửa soi read-only: thiếu KCS-cuối thì báo chặn; có thì im (§4.4) -----------------------
def test_van_de_phat_hanh_bao_thieu_kcs_cuoi(db, orders, lsx_svc, admin, customer):
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    vd = release.van_de_phat_hanh(db, lsx_ids={a.id})
    assert any(i["ma"] == "kcs_cuoi_thieu" for i in vd)

    kcs = _kcs_dept(db)
    _steps(db, a.id)[-1].department_id = kcs.id
    db.commit()
    assert release.van_de_phat_hanh(db, lsx_ids={a.id}) == []


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
            may_id=_in_step(db, lsx.id).may_id, so_luong_vao=5000, nang_suat=3000,
            don_vi_nang_suat="to_gio", don_vi_vao="to", don_vi_ra="to",
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
