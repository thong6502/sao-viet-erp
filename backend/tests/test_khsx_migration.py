from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_khsx_dinh_muc_vat_tu_phu_thuoc


def test_migration_chuyen_loai_gop_cho_va_tao_phu_thuoc_tuyen_tinh(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE cong_doan (id INTEGER PRIMARY KEY, ten TEXT, may_id INTEGER, department_id INTEGER, nang_suat NUMERIC)"))
        c.execute(text("CREATE TABLE piece_rates (id INTEGER PRIMARY KEY, department_id INTEGER, is_active BOOLEAN)"))
        c.execute(text("CREATE TABLE lsx (id INTEGER PRIMARY KEY, order_id INTEGER)"))
        c.execute(text("CREATE TABLE lsx_cong_doan (id INTEGER PRIMARY KEY, lsx_id INTEGER, thu_tu INTEGER, cong_doan_id INTEGER, loai_buoc TEXT, so_nhan_cong INTEGER, setup_phut NUMERIC, chay_phut NUMERIC, ve_sinh_phut NUMERIC, cho_phut NUMERIC, di_chuyen_phut NUMERIC, dieu_kien_json JSON)"))
        c.execute(text("CREATE TABLE xep_lich_cong_doan (id INTEGER PRIMARY KEY, lsx_cong_doan_id INTEGER, loai_buoc TEXT)"))
        c.execute(text("INSERT INTO cong_doan VALUES (1,'KCS',NULL,10,500),(2,'Xả tờ',20,11,1000)"))
        c.execute(text("INSERT INTO lsx VALUES (1,99)"))
        c.execute(text("INSERT INTO lsx_cong_doan VALUES (1,1,10,1,'kcs',2,5,NULL,3,0,2,'[]'),(2,1,20,NULL,'cho',1,1,4,2,6,3,'[]'),(3,1,30,2,'xa_to',1,7,NULL,1,0,0,'[]')"))

    with Session(engine) as db:
        _migrate_khsx_dinh_muc_vat_tu_phu_thuoc(db)
        rows = db.execute(text("SELECT id,loai_buoc,cho_phut,step_key FROM lsx_cong_doan ORDER BY thu_tu")).all()
        assert [r[1] for r in rows] == ["to", "may"]
        assert float(rows[0][2]) == 16  # 1 setup + 4 chạy + 2 vệ sinh + 6 chờ + 3 di chuyển
        assert all(r[3] for r in rows)
        assert db.execute(text("SELECT count(*) FROM lsx_cong_doan_phu_thuoc")).scalar_one() == 1
        assert "dieu_kien_json" not in {r[1] for r in db.execute(text("PRAGMA table_info(lsx_cong_doan)"))}


def test_migration_dung_khi_buoc_cho_o_dau_tuyen(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE lsx (id INTEGER PRIMARY KEY, order_id INTEGER)"))
        c.execute(text("CREATE TABLE lsx_cong_doan (id INTEGER PRIMARY KEY, lsx_id INTEGER, thu_tu INTEGER, cong_doan_id INTEGER, loai_buoc TEXT, so_nhan_cong INTEGER, setup_phut NUMERIC, chay_phut NUMERIC, ve_sinh_phut NUMERIC, cho_phut NUMERIC, di_chuyen_phut NUMERIC, dieu_kien_json JSON)"))
        c.execute(text("INSERT INTO lsx VALUES (1,99)"))
        c.execute(text("INSERT INTO lsx_cong_doan VALUES (1,1,10,NULL,'cho',1,0,5,0,0,0,'[]')"))
    with Session(engine) as db:
        try:
            _migrate_khsx_dinh_muc_vat_tu_phu_thuoc(db)
            assert False, "migration phải yêu cầu audit"
        except RuntimeError as exc:
            assert "cần audit tay" in str(exc)
