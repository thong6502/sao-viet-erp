"""Bài ghép 2 - luật hàng chờ, metadata, bước chung và migration dùng chung bảng cũ."""
from __future__ import annotations

from datetime import date, timedelta
from importlib import import_module

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lsx import (
    TT_CHO_BO_SUNG,
    TT_DA_LAP_KE_HOACH,
    TT_DA_PHAT_HANH,
    TT_NHAP,
    TT_SAN_SANG,
)
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.services.bai_ghep_service import BaiGhepConflict, BaiGhepValidationError
from app.services.sequence_service import SequenceService

# Tái dùng fixture dựng đơn -> LSX thật của bộ Bài ghép hiện hữu; test mới chỉ tập trung vào luật BG2.
from tests.test_bai_ghep_service import (  # noqa: F401
    _hai_lsx_san_sang,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _bg2_svc(db):
    service_mod = import_module("app.services.bai_ghep_2_service")
    repo_mod = import_module("app.repositories.bai_ghep_2_repo")
    return service_mod.BaiGhep2Service(
        db,
        repo_mod.BaiGhep2Repository(db),
        AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


def test_hang_cho_bg2_nhan_ba_trang_thai_khong_can_giay_kho_mau_hay_buoc_in(
    db, orders, lsx_svc, admin, customer,
):
    lsxs = _hai_lsx_san_sang(
        db, orders, lsx_svc, admin, customer,
        sl_them=(7_000, 6_000, 5_000, 4_000, 3_000, 2_000),
    )
    trang_thai = (
        TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG,
        TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH, TT_NHAP, TT_NHAP, TT_NHAP,
    )
    for lsx, tt in zip(lsxs, trang_thai):
        lsx.trang_thai = tt

    # BG2 không lấy giấy/khổ/màu/bước in làm điều kiện vào hàng chờ.
    lsxs[0].quy_cach_json = {}
    lsxs[0].cong_doans.clear()
    # Hai cửa loại độc lập còn lại: đang giữ chỗ và ruột sách nhiều tay.
    lsxs[5].giu_cho_bat = True
    lsxs[6].quy_cach_json = {**(lsxs[6].quy_cach_json or {}), "so_trang": 32, "trang_moi_tay": 16}
    lsxs[7].quy_cach_json = {**(lsxs[7].quy_cach_json or {}), "so_trang": 16, "trang_moi_tay": 16}
    db.commit()

    # Kể cả client cũ còn gửi giay_id, BG2 cũng không được biến nó thành điều kiện lọc.
    kq = _bg2_svc(db).hang_cho_ghep(giay_id=999999)

    assert {row["lsx_id"] for row in kq["items"]} == {
        lsxs[0].id, lsxs[1].id, lsxs[2].id, lsxs[7].id,
    }
    assert kq["so_giu_cho"] == 1
    svc = _bg2_svc(db)
    assert svc.tao(lsx_ids=[lsxs[7].id, lsxs[0].id], actor=admin).id
    with pytest.raises(BaiGhepValidationError, match="tay/cuốn"):
        svc.tao(lsx_ids=[lsxs[6].id, lsxs[1].id], actor=admin)


def test_tao_bg2_can_hai_lsx_khoi_tao_metadata_mot_lan_va_cho_sua(
    db, orders, lsx_svc, admin, customer,
):
    lsxs = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer, sl_them=(5_000,))
    lsxs[0].trang_thai = TT_NHAP
    lsxs[1].trang_thai = TT_CHO_BO_SUNG
    lsxs[2].trang_thai = TT_SAN_SANG
    lsxs[0].han_hoan_thanh_sx = date.today() + timedelta(days=5)
    lsxs[1].han_hoan_thanh_sx = date.today() + timedelta(days=2)
    lsxs[2].han_hoan_thanh_sx = date.today() + timedelta(days=1)
    lsxs[1].is_rush = True
    db.commit()
    svc = _bg2_svc(db)

    with pytest.raises(BaiGhepValidationError, match="ít nhất 2"):
        svc.tao(lsx_ids=[lsxs[0].id], actor=admin)

    bg = svc.tao(lsx_ids=[lsxs[0].id, lsxs[1].id], actor=admin)
    assert bg.ten == f"Bài ghép {bg.ma}"
    assert bg.han_hoan_thanh_sx == lsxs[1].han_hoan_thanh_sx
    assert bg.is_rush is True
    assert bg.nguoi_phu_trach_id == admin.id
    assert _bg2_svc(db).detail_dict(bg)["nguoi_phu_trach_ten"] == admin.name
    assert _bg2_svc(db).list_rows()[0]["nguoi_phu_trach_ten"] == admin.name

    custom_han = date.today() + timedelta(days=20)
    svc.sua(
        bai_ghep_id=bg.id,
        patch={
            "ten": "Bài gấp ca tối",
            "han_hoan_thanh_sx": custom_han,
            "is_rush": False,
            "nguoi_phu_trach_id": None,
        },
        actor=admin,
    )
    svc.them_thanh_vien(bai_ghep_id=bg.id, lsx_ids=[lsxs[2].id], actor=admin)
    sau_them = svc._get(bg.id)
    tv_moi = next(tv for tv in sau_them.thanh_viens if tv.lsx_id == lsxs[2].id)
    svc.bo_thanh_vien(bai_ghep_id=bg.id, thanh_vien_id=tv_moi.id, actor=admin)
    sau = svc._get(bg.id)

    assert (sau.ten, sau.han_hoan_thanh_sx, sau.is_rush, sau.nguoi_phu_trach_id) == (
        "Bài gấp ca tối", custom_han, False, None,
    )


def test_gop_bg2_chi_ke_thua_nhan_dien_danh_muc_don_vi_va_thu_tu(
    db, orders, lsx_svc, admin, customer,
):
    lsxs = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    mau = sorted(lsx_svc.get(lsxs[0].id).cong_doans, key=lambda x: x.thu_tu)[0]
    mau.department_id = 123
    mau.may_id = 456
    mau.nha_cung_cap = "NCC mẫu"
    mau.nang_suat = 999
    mau.so_nhan_cong_tieu_chuan = 4
    mau.so_nhan_cong_toi_thieu = 2
    mau.so_nhan_cong_toi_da = 8
    mau.don_vi_nang_suat = "to_gio"
    mau.khoan_json = {"piece_rate_id": 77, "ten": "Khoán mẫu"}
    mau.ghi_chu = "Không được bê sang lượt chung"
    db.commit()

    svc = _bg2_svc(db)
    bg = svc.tao(lsx_ids=[l.id for l in lsxs], actor=admin)
    keys = [
        sorted(lsx_svc.get(l.id).cong_doans, key=lambda x: x.thu_tu)[0].step_key
        for l in lsxs
    ]
    svc.gop(bai_ghep_id=bg.id, step_keys=keys, actor=admin)
    chung = svc._buoc_chungs(svc._get(bg.id))[0]

    assert (chung.cong_doan_id, chung.ten, chung.nhom, chung.loai_buoc) == (
        mau.cong_doan_id, mau.ten, mau.nhom, mau.loai_buoc,
    )
    assert (chung.don_vi_vao, chung.don_vi_ra, chung.thu_tu) == (
        mau.don_vi_vao, mau.don_vi_ra, mau.thu_tu,
    )
    assert chung.department_id is None
    assert chung.may_id is None
    assert chung.nha_cung_cap is None
    assert chung.nang_suat is None
    assert chung.so_nhan_cong_tieu_chuan == 1
    assert chung.so_nhan_cong == 1
    assert chung.so_nhan_cong_toi_thieu is None
    assert chung.so_nhan_cong_toi_da is None
    assert chung.don_vi_nang_suat is None
    assert chung.khoan_json is None
    assert chung.ghi_chu is None
    assert list(chung.vat_tus) == []


def test_bai_dang_giu_cho_chan_doi_cau_truc_vat_tu_nhung_khong_chan_metadata(
    db, orders, lsx_svc, admin, customer,
):
    lsxs = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    svc = _bg2_svc(db)
    bg = svc.tao(lsx_ids=[l.id for l in lsxs], actor=admin)
    keys = [
        sorted(lsx_svc.get(l.id).cong_doans, key=lambda x: x.thu_tu)[0].step_key
        for l in lsxs
    ]
    bg.giu_cho_bat = True
    db.commit()

    with pytest.raises(BaiGhepConflict, match="đang giữ chỗ"):
        svc.gop(bai_ghep_id=bg.id, step_keys=keys, actor=admin)
    with pytest.raises(BaiGhepConflict, match="đang giữ chỗ"):
        svc.sua(bai_ghep_id=bg.id, patch={"giay_id": 999}, actor=admin)

    # Tên/hạn/gấp/phụ trách/ghi chú không đổi lượng vật tư nên vẫn sửa được khi đang giữ.
    svc.sua(
        bai_ghep_id=bg.id,
        patch={"ten": "Tên khi đang giữ", "is_rush": True, "ghi_chu": "metadata thuần"},
        actor=admin,
    )

    bg = svc._get(bg.id)
    bg.giu_cho_bat = False
    db.commit()
    svc.gop(bai_ghep_id=bg.id, step_keys=keys, actor=admin)
    chung = svc._buoc_chungs(svc._get(bg.id))[0]
    bg = svc._get(bg.id)
    bg.giu_cho_bat = True
    db.commit()

    with pytest.raises(BaiGhepConflict, match="đang giữ chỗ"):
        svc.tach(bai_ghep_id=bg.id, gang_step_key=chung.step_key, actor=admin)
    with pytest.raises(BaiGhepConflict, match="đang giữ chỗ"):
        svc.lap_ke_hoach_buoc_chung(
            bai_ghep_id=bg.id,
            gang_step_key=chung.step_key,
            patch={"vat_tus": []},
            actor=admin,
        )

    sau = svc._get(bg.id)
    assert (sau.ten, sau.is_rush, sau.ghi_chu) == (
        "Tên khi đang giữ", True, "metadata thuần",
    )


def test_da_phat_hanh_khoa_mutation_xoa_va_khong_duoc_keo_nguoc_trang_thai(
    db, orders, lsx_svc, admin, customer,
):
    lsxs = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    svc = _bg2_svc(db)
    bg = svc.tao(lsx_ids=[l.id for l in lsxs], actor=admin)
    bg.trang_thai = TT_DA_PHAT_HANH
    db.commit()

    with pytest.raises(BaiGhepConflict, match="phát hành"):
        svc.sua(bai_ghep_id=bg.id, patch={"ten": "Không được sửa"}, actor=admin)
    with pytest.raises(BaiGhepConflict, match="phát hành"):
        svc.xoa(bai_ghep_id=bg.id, actor=admin)
    with pytest.raises(BaiGhepConflict, match="phát hành"):
        svc.set_trang_thai(bai_ghep_id=bg.id, trang_thai=TT_NHAP, actor=admin)


def test_sua_thanh_vien_ghi_audit_va_race_unique_duoc_map_conflict(
    db, orders, lsx_svc, admin, customer, monkeypatch,
):
    lsxs = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    svc = _bg2_svc(db)
    bg = svc.tao(lsx_ids=[l.id for l in lsxs], actor=admin)
    tv = bg.thanh_viens[0]

    svc.sua_thanh_vien(
        bai_ghep_id=bg.id, thanh_vien_id=tv.id, so_con_tren_to=3, actor=admin,
    )
    assert any(
        row.action == "sua_thanh_vien"
        for row in AuditLogRepository(db).list_by_target(f"bai_ghep:{bg.id}")
    )

    # Mô phỏng cửa sổ hai request cùng qua pre-check rồi DB unique mới là nơi phân xử.
    svc2 = _bg2_svc(db)
    monkeypatch.setattr(
        svc2.repo,
        "add",
        lambda _bg: (_ for _ in ()).throw(IntegrityError("unique lsx_id", {}, Exception())),
    )
    with pytest.raises(BaiGhepConflict, match="bài ghép khác"):
        svc2.tao(lsx_ids=[l.id for l in lsxs], actor=admin)
    assert db.is_active


def _legacy_db(*, duplicate_member: bool = False) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    session = Session(engine)
    session.execute(text(
        "CREATE TABLE bai_ghep (id INTEGER PRIMARY KEY, ma VARCHAR(30) NOT NULL, created_by INTEGER)"
    ))
    session.execute(text(
        "CREATE TABLE lsx (id INTEGER PRIMARY KEY, han_hoan_thanh_sx DATE, "
        "is_rush BOOLEAN NOT NULL DEFAULT FALSE)"
    ))
    session.execute(text(
        "CREATE TABLE bai_ghep_thanh_vien (id INTEGER PRIMARY KEY, bai_ghep_id INTEGER NOT NULL, "
        "lsx_id INTEGER NOT NULL)"
    ))
    session.execute(text("INSERT INTO bai_ghep VALUES (1, 'GB26-0001', 9)"))
    session.execute(text(
        "INSERT INTO lsx VALUES (10, '2026-09-20', FALSE), (11, '2026-09-05', TRUE)"
    ))
    session.execute(text("INSERT INTO bai_ghep_thanh_vien VALUES (1, 1, 10), (2, 1, 11)"))
    if duplicate_member:
        session.execute(text("INSERT INTO bai_ghep_thanh_vien VALUES (3, 1, 10)"))
    session.commit()
    return session


def test_migration_bg2_backfill_idempotent_va_tao_unique_lsx_id():
    db = _legacy_db()
    migrate = import_module("app.db_migrations")._migrate_bai_ghep_2

    migrate(db)
    migrate(db)

    row = db.execute(text(
        "SELECT ten, han_hoan_thanh_sx, is_rush, nguoi_phu_trach_id FROM bai_ghep WHERE id = 1"
    )).one()
    assert tuple(row) == ("Bài ghép GB26-0001", "2026-09-05", 1, 9)
    assert {"ten", "han_hoan_thanh_sx", "is_rush", "nguoi_phu_trach_id"} <= {
        c["name"] for c in inspect(db.get_bind()).get_columns("bai_ghep")
    }
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO bai_ghep_thanh_vien VALUES (4, 2, 10)"))


def test_migration_bg2_khong_bat_lai_co_gap_nguoi_dung_da_tat():
    """Retry migration KHÔNG được đè metadata người lập kế hoạch đã sửa.

    `is_rush` sinh ra từ thành viên, nhưng sau đó là ô người dùng bấm được: bài gồm một lệnh gấp
    mà cả bài vẫn chạy kịp thì họ tắt cờ. Cột thêm kèm DEFAULT FALSE nên "đã tắt" và "chưa
    backfill" cùng là FALSE — chỉ lượt tạo cột mới được phép suy lại.
    """
    db = _legacy_db()
    migrate = import_module("app.db_migrations")._migrate_bai_ghep_2

    migrate(db)
    assert db.execute(text("SELECT is_rush FROM bai_ghep WHERE id = 1")).scalar_one() == 1

    db.execute(text("UPDATE bai_ghep SET is_rush = FALSE WHERE id = 1"))
    db.commit()
    migrate(db)

    assert db.execute(text("SELECT is_rush FROM bai_ghep WHERE id = 1")).scalar_one() == 0


def test_migration_bg2_bao_ro_data_trung_va_khong_tu_xoa():
    db = _legacy_db(duplicate_member=True)
    migrate = import_module("app.db_migrations")._migrate_bai_ghep_2

    with pytest.raises(RuntimeError, match=r"lsx_id=10.*2"):
        migrate(db)

    assert db.execute(text(
        "SELECT COUNT(*) FROM bai_ghep_thanh_vien WHERE lsx_id = 10"
    )).scalar_one() == 2
    # Duplicate phải được phát hiện trước mọi ALTER/backfill để retry không ở trạng thái nửa vời.
    assert "ten" not in {c["name"] for c in inspect(db.get_bind()).get_columns("bai_ghep")}
