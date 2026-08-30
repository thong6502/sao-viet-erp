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
from app.services.xep_lich_2.constraint import MUC_CHAN_PHAT_HANH

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


def _dept_khong_kcs(db, *, ten="Tổ Thành Phẩm XL", ma="TO-TP-XL") -> Department:
    d = Department(name=ten, code=ma, la_san_xuat=True)
    db.add(d)
    db.flush()
    return d


def _them_buoc(db, lsx_id, *, thu_tu, ten, department_id, la_kcs) -> LsxCongDoan:
    """Thêm MỘT bước routing thủ công vào LSX — tái dùng cho mọi test soi cờ `la_kcs` (Task 2):
    engine giá không cần chạy lại, chỉ cần một `LsxCongDoan` mang đúng cờ/tổ để soi snapshot."""
    buoc = LsxCongDoan(
        lsx_id=lsx_id, thu_tu=thu_tu, ten=ten, nhom="finishing", loai_buoc=LB_MAY,
        department_id=department_id, la_kcs=la_kcs,
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


# --- KCS-cuối: bước KCS ở cuối routing → đánh dấu + chốt lệnh thân chính (§3.2/§4.4) ---------
def test_kcs_cuoi_danh_dau_va_than_chinh(db, orders, lsx_svc, admin, customer):
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    kcs = _kcs_dept(db)
    steps = _steps(db, a.id)
    # Nguồn XÁC ĐỊNH KCS-cuối là CỜ `la_kcs` của bước (Task 2), KHÔNG còn suy theo
    # `department_id in kcs_depts` — set cả hai cho khớp cấu hình hợp lệ (luật 5: bước la_kcs=true
    # phải nằm ở tổ is_kcs=true).
    steps[-1].department_id = kcs.id
    steps[-1].la_kcs = True
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
    cuoi = _steps(db, a.id)[-1]
    cuoi.department_id = kcs.id
    cuoi.la_kcs = True
    db.commit()
    assert release.van_de_phat_hanh(db, lsx_ids={a.id}) == []


# --- KCS kiêm nhiệm (Task 2): nguồn ĐÚNG là cờ của BƯỚC, không phải department.is_kcs ---------
def test_snapshot_la_kcs_theo_tung_buoc_khong_theo_to(db, orders, lsx_svc, admin, customer):
    """Dán và Kiểm tra cuối CÙNG một tổ (is_kcs=true) nhưng khai `la_kcs` khác nhau ở danh mục —
    snapshot phát hành phải theo TỪNG BƯỚC, không đồng nhất theo tổ (luật 1/2/4 spec §2.1)."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    kcs = _kcs_dept(db)
    _them_buoc(db, a.id, thu_tu=1, ten="Dán", department_id=kcs.id, la_kcs=False)
    _them_buoc(db, a.id, thu_tu=2, ten="Kiểm tra cuối", department_id=kcs.id, la_kcs=True)
    db.commit()

    # Case bình thường: đúng một KCS-cuối/nhóm → không có vấn đề chặn phát hành.
    assert release.van_de_phat_hanh(db, lsx_ids={a.id}) == []

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    steps = _steps(db, a.id)
    dan_step = next(s for s in steps if s.ten == "Dán")
    kt_step = next(s for s in steps if s.ten == "Kiểm tra cuối")
    cv_dan = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=dan_step.step_key).one()
    cv_kt = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=kt_step.step_key).one()

    assert cv_dan.department_id == kcs.id and cv_dan.la_kcs is False
    assert cv_kt.department_id == kcs.id and cv_kt.la_kcs is True and cv_kt.la_kcs_cuoi is True


def test_buoc_la_kcs_sai_to_chan_phat_hanh(db, orders, lsx_svc, admin, customer):
    """Luật 5: bước khai `la_kcs=true` nhưng tổ thực hiện KHÔNG có `is_kcs=true` — sai cấu hình
    phải CHẶN phát hành và chỉ rõ TÊN bước + TÊN tổ, không phải câu chung chung."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    to_sai = _dept_khong_kcs(db)
    _them_buoc(db, a.id, thu_tu=1, ten="Kiểm tra cuối", department_id=to_sai.id, la_kcs=True)
    db.commit()

    vd = release.van_de_phat_hanh(db, lsx_ids={a.id})
    loi = next(i for i in vd if i["ma"] == "kcs_sai_to")
    assert loi["muc"] == MUC_CHAN_PHAT_HANH
    assert "Kiểm tra cuối" in loi["mo_ta"] and to_sai.name in loi["mo_ta"]


def test_kcs_trung_gian_khong_bi_danh_kcs_cuoi(db, orders, lsx_svc, admin, customer):
    """Bước `la_kcs=true` nằm GIỮA routing (không phải bước cuối) là KCS TRUNG GIAN hợp lệ — nó
    vẫn là công việc KCS (`la_kcs=True`), nhưng KHÔNG được đánh `la_kcs_cuoi`. Bước cuối vẫn
    `la_kcs=false` nên hành vi CŨ (thiếu KCS-cuối bị chặn) phải còn nguyên."""
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    kcs = _kcs_dept(db)
    to_thuong = _dept_khong_kcs(db, ten="Tổ Đóng Gói XL", ma="TO-DG-XL")
    _them_buoc(db, a.id, thu_tu=1, ten="Kiểm tra giữa", department_id=kcs.id, la_kcs=True)
    _them_buoc(db, a.id, thu_tu=2, ten="Đóng gói", department_id=to_thuong.id, la_kcs=False)
    db.commit()

    vd = release.van_de_phat_hanh(db, lsx_ids={a.id})
    assert any(i["ma"] == "kcs_cuoi_thieu" for i in vd)          # hành vi CŨ vẫn đúng
    assert not any(i["ma"] == "kcs_sai_to" for i in vd)          # bước giữa khai đúng tổ KCS

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    giua_step = next(s for s in _steps(db, a.id) if s.ten == "Kiểm tra giữa")
    cv_giua = db.query(SanXuatCongViec).filter_by(
        goi_id=goi.id, step_key=giua_step.step_key
    ).one()
    assert cv_giua.la_kcs is True and cv_giua.la_kcs_cuoi is False
    assert db.query(SanXuatCongViec).filter_by(goi_id=goi.id, la_kcs_cuoi=True).count() == 0


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
