"""Migration 0177 — tách `thu_mua` thành 3 màn. Kiểm CHÍNH LỆNH CHUYỂN ĐỔI, không kiểm endpoint.

Vì sao phải có test riêng: `drop_all` + `create_all` của fixture `db` KHÔNG chạy migration (bảng
`schema_migrations` bị xoá theo nên hệ thống coi như chưa có bản nào), tức mọi test API khác đang
chạy trên DB do `seed.py` dựng — migration không hề được gọi. Sai một dòng SQL ở đây thì test API
vẫn xanh, còn DB thật sáng hôm sau mất quyền.

Ba thứ được giữ:
1. Chạy được (đúng tên cột, không vỡ NOT NULL) và chạy LẠI được — không đẻ hàng trùng.
2. Sao chép ĐỦ cờ + phạm vi từ `thu_mua` sang hai màn mới — không ai mất đường làm việc.
3. Cấp bù cho TRƯỞNG PHÒNG đang tại vị, bù cho quyền ngầm theo chức danh vừa bị gỡ.
"""

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.db_migrations import (
    _migrate_tach_module_ke_toan,
    _migrate_tach_module_nhan_su_luong,
    _migrate_tach_module_thu_mua,
    _migrate_tach_o_danh_dau_da_chi_luong,
    _migrate_cham_cong_mot_o_mot_tab,
    _migrate_them_o_xem_nhat_ky_cham_cong,
    _migrate_tu_phuc_vu_co_o_thao_tac,
    _migrate_ycmh_khong_con_an_theo_khoa_thu_mua,
    _migrate_luong_o_that_thay_o_ma,
)
from app.models.role import SCOPE_DEPARTMENT, RolePermission


@pytest.fixture
def db(client):
    """Phiên DB thô trên CÙNG DB in-memory mà `client` vừa dựng + seed xong.

    Phải đi qua `client` chứ không tự tạo bảng: seed mới có sẵn phòng ban / vai / người dùng để
    dựng lại tình trạng trước khi tách."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _dung_du_lieu_cu(db) -> tuple[int, int]:
    """Dựng lại tình trạng TRƯỚC khi tách: chỉ có module `thu_mua`, một vai mua hàng, một trưởng phòng.

    Trả (id vai mua hàng, id vai của trưởng phòng)."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN "
                    "('thu_mua', 'nha_cung_cap', 'yeu_cau_mua_hang')"))
    db.execute(text("DELETE FROM modules WHERE key IN ('nha_cung_cap', 'yeu_cau_mua_hang')"))

    vai_mua = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope, can_approve, can_cancel) "
             "VALUES (:r, 'thu_mua', true, true, true, false, 'department', true, true)"),
        {"r": vai_mua},
    )

    # Một phòng có trưởng phòng, và trưởng phòng đó mang một vai KHÁC, chưa có quyền thu mua nào.
    vai_tp = db.execute(text("SELECT id FROM roles WHERE id <> :r LIMIT 1"), {"r": vai_mua}).scalar()
    nguoi = db.execute(text("SELECT id FROM users WHERE role_id = :v LIMIT 1"), {"v": vai_tp}).scalar()
    if nguoi is None:
        nguoi = db.execute(text("SELECT id FROM users LIMIT 1")).scalar()
        db.execute(text("UPDATE users SET role_id = :v WHERE id = :u"), {"v": vai_tp, "u": nguoi})
    phong = db.execute(text("SELECT id FROM departments LIMIT 1")).scalar()
    db.execute(text("UPDATE departments SET head_user_id = :u WHERE id = :d"), {"u": nguoi, "d": phong})
    db.commit()
    return vai_mua, vai_tp


def _quyen(db, role_id: int, khoa: str) -> dict | None:
    row = db.execute(
        text("SELECT can_read, can_create, can_update, can_delete, scope, can_approve, can_cancel "
             "FROM role_permissions WHERE role_id = :r AND module_key = :k"),
        {"r": role_id, "k": khoa},
    ).mappings().first()
    return dict(row) if row else None


def test_0177_sao_chep_du_co_va_pham_vi_sang_hai_man_moi(db):
    vai_mua, _ = _dung_du_lieu_cu(db)

    _migrate_tach_module_thu_mua(db)

    goc = _quyen(db, vai_mua, "thu_mua")
    for khoa in ("nha_cung_cap", "yeu_cau_mua_hang"):
        moi = _quyen(db, vai_mua, khoa)
        assert moi is not None, f"vai mua hàng mất sạch quyền màn {khoa}"
        # So NGUYÊN BỘ, không chỉ can_read: mất `scope` hay `can_approve` là đổi nghĩa quyền.
        assert moi == goc, f"màn {khoa} không giữ nguyên cờ/phạm vi: {moi} != {goc}"


def test_0177_cap_bu_cho_truong_phong_vi_da_go_quyen_ngam(db):
    """Trưởng phòng trước đây lập được yêu cầu mua hàng bằng quyền NGẦM theo chức danh.

    Quyền ngầm đó không có bản ghi nào để sao chép, nên nếu migration chỉ copy `thu_mua` thì gỡ
    đường ngầm xong là trưởng phòng hết lập được yêu cầu vật tư."""
    _, vai_tp = _dung_du_lieu_cu(db)
    assert _quyen(db, vai_tp, "yeu_cau_mua_hang") is None

    _migrate_tach_module_thu_mua(db)

    duoc = _quyen(db, vai_tp, "yeu_cau_mua_hang")
    assert duoc is not None, "trưởng phòng mất quyền lập yêu cầu mua hàng"
    assert duoc["can_read"] and duoc["can_create"] and duoc["can_update"]
    assert duoc["scope"] == SCOPE_DEPARTMENT


def test_0177_chay_lai_khong_de_hang_trung(db):
    """Migration chạy lại (deploy lại, hoặc bảng `schema_migrations` bị dọn) không được nhân đôi quyền."""
    vai_mua, _ = _dung_du_lieu_cu(db)

    _migrate_tach_module_thu_mua(db)
    _migrate_tach_module_thu_mua(db)

    for khoa in ("nha_cung_cap", "yeu_cau_mua_hang"):
        so_dong = db.execute(
            text("SELECT COUNT(*) FROM role_permissions WHERE role_id = :r AND module_key = :k"),
            {"r": vai_mua, "k": khoa},
        ).scalar()
        assert so_dong == 1, f"màn {khoa} có {so_dong} hàng quyền cho cùng một vai"
    so_module = db.execute(
        text("SELECT COUNT(*) FROM modules WHERE key IN ('nha_cung_cap', 'yeu_cau_mua_hang')")
    ).scalar()
    assert so_module == 2


# ═══════════════════════════════════════════════════ 0178 — tách `ke_toan` thành 6 màn


def _dung_quyen_ke_toan_cu(db, *, can_approve: bool) -> int:
    """Dựng lại tình trạng TRƯỚC khi tách: một vai chỉ có khoá `ke_toan`.

    `can_approve` chính là ô mà kế toán ngoài đời đang dùng để LẬP phiếu chi / phiếu thu — tên cũ
    gây hiểu nhầm là "duyệt"."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN "
                    "('ke_toan', 'phieu_chi', 'phieu_thu', 'cong_no_phai_tra', "
                    "'cong_no_phai_thu', 'tk_ngan_hang')"))
    db.execute(text("DELETE FROM modules WHERE key IN ('phieu_chi', 'phieu_thu', "
                    "'cong_no_phai_tra', 'cong_no_phai_thu', 'tk_ngan_hang')"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope, can_approve, can_cancel, can_manage_status, can_export) "
             "VALUES (:r, 'ke_toan', true, false, false, false, 'all', :a, true, true, true)"),
        {"r": vai, "a": can_approve},
    )
    db.commit()
    return vai


def _q(db, role_id: int, khoa: str) -> dict | None:
    row = db.execute(
        text("SELECT can_read, can_create, can_update, can_delete, scope, can_approve, "
             "can_cancel, can_manage_status, can_export "
             "FROM role_permissions WHERE role_id = :r AND module_key = :k"),
        {"r": role_id, "k": khoa},
    ).mappings().first()
    return dict(row) if row else None


def test_0178_ke_toan_dang_lap_phieu_bang_o_approve_thi_khong_duoc_mat_quyen(db):
    """Ánh xạ ĐỘNG TỪ — chỗ dễ sai nhất của cả đợt.

    Khoá cũ dùng `can_approve` làm cờ "lập phiếu chi / lập phiếu thu / gán chứng từ". Khoá mới gọi
    đúng tên là `can_create`. Sao chép nguyên xi là kế toán mở màn ra mà không bấm được nút nào —
    test này giữ đúng chỗ đó."""
    vai = _dung_quyen_ke_toan_cu(db, can_approve=True)

    _migrate_tach_module_ke_toan(db)

    for khoa in ("phieu_chi", "phieu_thu"):
        moi = _q(db, vai, khoa)
        assert moi is not None, f"vai kế toán mất sạch quyền màn {khoa}"
        assert moi["can_create"], f"{khoa}: người đang lập phiếu bằng ô `approve` bị mất quyền LẬP"
    # Màn Tài khoản ngân hàng: TK nhà cung cấp trước gác bằng `approve` ⇒ đổ vào `update`.
    assert _q(db, vai, "tk_ngan_hang")["can_update"]


def test_0178_khong_tu_dung_cho_them_quyen_lap_phieu(db):
    """Chiều ngược lại: ai KHÔNG có ô lập phiếu thì sau khi tách vẫn không có.

    Ánh xạ động từ dễ vống lên thành "cứ có `ke_toan` là được lập phiếu" — đó là mở cửa cho tiền
    ra, tệ hơn cả cái đang sửa."""
    vai = _dung_quyen_ke_toan_cu(db, can_approve=False)

    _migrate_tach_module_ke_toan(db)

    for khoa in ("phieu_chi", "phieu_thu"):
        moi = _q(db, vai, khoa)
        assert moi["can_read"], f"{khoa}: mất quyền XEM"
        assert not moi["can_create"], f"{khoa}: tự dưng được cấp quyền LẬP PHIẾU"
    assert not _q(db, vai, "tk_ngan_hang")["can_update"]


def test_0178_giu_nguyen_pham_vi_va_cac_co_phu(db):
    vai = _dung_quyen_ke_toan_cu(db, can_approve=True)

    _migrate_tach_module_ke_toan(db)

    for khoa in ("phieu_chi", "phieu_thu", "cong_no_phai_tra", "cong_no_phai_thu", "tk_ngan_hang"):
        moi = _q(db, vai, khoa)
        assert moi["scope"] == "all", f"{khoa}: rơi mất phạm vi"
        assert moi["can_cancel"] and moi["can_manage_status"] and moi["can_export"], (
            f"{khoa}: rơi mất cờ phụ (huỷ / xác nhận / in-xuất)"
        )


def test_0178_chay_lai_khong_de_hang_trung(db):
    vai = _dung_quyen_ke_toan_cu(db, can_approve=True)

    _migrate_tach_module_ke_toan(db)
    _migrate_tach_module_ke_toan(db)

    for khoa in ("phieu_chi", "phieu_thu", "cong_no_phai_tra", "cong_no_phai_thu", "tk_ngan_hang"):
        n = db.execute(
            text("SELECT COUNT(*) FROM role_permissions WHERE role_id = :r AND module_key = :k"),
            {"r": vai, "k": khoa},
        ).scalar()
        assert n == 1, f"màn {khoa} có {n} hàng quyền cho cùng một vai"


# ═══════════════════════════════════════ 0179 — tách Nhân sự & Lương


def _dung_quyen_nhan_su_cu(db, *, can_adjust: bool, pham_vi_ns: str = "all",
                           pham_vi_luong: str = "own") -> int:
    """Dựng lại tình trạng TRƯỚC khi tách: vai có `nhan_su` (kèm chấm bù) + `luong` phạm vi hẹp.

    `luong` phạm vi `own` mà `nhan_su` phạm vi `all` chính là tình trạng thật hôm nay: Lương MƯỢN
    phạm vi của Nhân sự nên phạm vi khai trên dòng `luong` chưa bao giờ có tác dụng."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN "
                    "('nhan_su', 'cham_cong', 'luong', 'self_service', 'noi_quy')"))
    db.execute(text("DELETE FROM modules WHERE key IN ('cham_cong', 'self_service')"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope, can_adjust, can_lock) "
             "VALUES (:r, 'nhan_su', true, true, true, false, :s, :a, false)"),
        {"r": vai, "s": pham_vi_ns, "a": can_adjust},
    )
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'luong', true, false, false, false, :s)"),
        {"r": vai, "s": pham_vi_luong},
    )
    db.commit()
    return vai


def _q2(db, role_id: int, khoa: str) -> dict | None:
    row = db.execute(
        text("SELECT can_read, can_create, can_update, can_delete, scope, can_adjust, can_lock "
             "FROM role_permissions WHERE role_id = :r AND module_key = :k"),
        {"r": role_id, "k": khoa},
    ).mappings().first()
    return dict(row) if row else None


def test_0179_nguoi_dang_cham_bu_van_cham_bu_duoc_o_man_moi(db):
    vai = _dung_quyen_nhan_su_cu(db, can_adjust=True)

    _migrate_tach_module_nhan_su_luong(db)

    cc = _q2(db, vai, "cham_cong")
    assert cc is not None, "vai nhân sự mất sạch quyền màn Chấm công"
    assert cc["can_read"] and cc["can_adjust"], "mất quyền xem / chấm bù"
    assert cc["scope"] == "all", "rơi mất phạm vi"


def test_0179_nguoi_dang_chot_ky_bang_o_cham_bu_khong_duoc_mat_quyen(db):
    """Ánh xạ động từ: Chốt kỳ trước đây gác bằng ô `adjust`, nay là ô `lock` riêng."""
    vai = _dung_quyen_nhan_su_cu(db, can_adjust=True)

    _migrate_tach_module_nhan_su_luong(db)

    assert _q2(db, vai, "cham_cong")["can_lock"], "người đang chốt kỳ bị mất quyền"


def test_0179_khong_tu_dung_cho_them_quyen_chot_ky(db):
    """Chiều ngược lại: ai không chấm bù được thì cũng không tự dưng chốt được kỳ."""
    vai = _dung_quyen_nhan_su_cu(db, can_adjust=False)

    _migrate_tach_module_nhan_su_luong(db)

    cc = _q2(db, vai, "cham_cong")
    assert cc["can_read"], "mất quyền xem bảng công"
    assert not cc["can_lock"], "tự dưng được cấp quyền CHỐT KỲ CÔNG"


def test_0179_luong_giu_nguyen_pham_vi_dang_thuc_su_dung(db):
    """Lương thôi mượn phạm vi Nhân sự ⇒ phải chép phạm vi sang, không thì tụt về `own`.

    Không chép: người đang xem lương cả công ty sáng mai chỉ còn thấy lương của chính mình, mà
    nhìn ma trận vẫn thấy "Lương · Tất cả" — không ai đoán ra."""
    vai = _dung_quyen_nhan_su_cu(db, can_adjust=True, pham_vi_ns="all", pham_vi_luong="own")

    _migrate_tach_module_nhan_su_luong(db)

    assert _q2(db, vai, "luong")["scope"] == "all", "Lương tụt phạm vi sau khi thôi mượn của Nhân sự"


def test_0179_moi_vai_deu_co_o_tu_phuc_vu_va_noi_quy(db):
    """Hai ô này trước là luật ngầm ⇒ không có dòng nào để sao chép, phải cấp cho MỌI vai."""
    _dung_quyen_nhan_su_cu(db, can_adjust=True)
    so_vai = db.execute(text("SELECT COUNT(*) FROM roles")).scalar()

    _migrate_tach_module_nhan_su_luong(db)

    for khoa in ("self_service", "noi_quy"):
        n = db.execute(
            text("SELECT COUNT(*) FROM role_permissions WHERE module_key = :k AND can_read"),
            {"k": khoa},
        ).scalar()
        assert n == so_vai, f"{khoa}: mới cấp {n}/{so_vai} vai"


def test_0179_chay_lai_khong_de_hang_trung(db):
    vai = _dung_quyen_nhan_su_cu(db, can_adjust=True)

    _migrate_tach_module_nhan_su_luong(db)
    _migrate_tach_module_nhan_su_luong(db)

    for khoa in ("cham_cong", "self_service", "noi_quy"):
        n = db.execute(
            text("SELECT COUNT(*) FROM role_permissions WHERE role_id = :r AND module_key = :k"),
            {"r": vai, "k": khoa},
        ).scalar()
        assert n == 1, f"màn {khoa} có {n} hàng quyền cho cùng một vai"


# ═══════════════════════════════════ 0180 — tách ô "Đánh dấu đã chi lương"


def _dung_quyen_luong_cu(db, *, can_lock: bool) -> int:
    db.execute(text("DELETE FROM role_permissions WHERE module_key = 'luong'"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope, can_lock, can_manage_status) "
             "VALUES (:r, 'luong', true, false, false, false, 'all', :l, false)"),
        {"r": vai, "l": can_lock},
    )
    db.commit()
    return vai


def _co_danh_dau(db, role_id: int) -> bool:
    return bool(db.execute(
        text("SELECT can_manage_status FROM role_permissions "
             "WHERE role_id = :r AND module_key = 'luong'"),
        {"r": role_id},
    ).scalar())


def test_0180_nguoi_dang_danh_dau_da_chi_bang_o_chot_khong_mat_quyen(db):
    vai = _dung_quyen_luong_cu(db, can_lock=True)
    _migrate_tach_o_danh_dau_da_chi_luong(db)
    assert _co_danh_dau(db, vai), "người đang đánh dấu đã chi bằng ô Chốt bị mất quyền"


def test_0180_khong_tu_dung_cho_them_quyen_danh_dau_da_chi(db):
    """Ô cho TIỀN RA — vống lên còn tệ hơn cái đang sửa."""
    vai = _dung_quyen_luong_cu(db, can_lock=False)
    _migrate_tach_o_danh_dau_da_chi_luong(db)
    assert not _co_danh_dau(db, vai), "vai không có ô Chốt mà tự dưng được cấp quyền đánh dấu đã chi"


# ═══════════════════════════════ 0181 — thêm ô "Xem Nhật ký chấm công"


def test_0181_nguoi_dang_xem_nhat_ky_khong_mat_quyen(db):
    """Cột MỚI mặc định `false` ⇒ không ánh xạ là sáng hôm sau tab Nhật ký trắng trơn với TẤT CẢ."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key = 'cham_cong'"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope, can_view_log) "
             "VALUES (:r, 'cham_cong', true, false, false, false, 'all', false)"),
        {"r": vai},
    )
    db.commit()

    _migrate_them_o_xem_nhat_ky_cham_cong(db)

    co = db.execute(
        text("SELECT can_view_log FROM role_permissions "
             "WHERE role_id = :r AND module_key = 'cham_cong'"), {"r": vai},
    ).scalar()
    assert co, "người đang xem được nhật ký bị mất quyền sau khi tách ô"


def test_0181_khong_cap_cho_vai_khong_xem_duoc_cham_cong(db):
    db.execute(text("DELETE FROM role_permissions WHERE module_key = 'cham_cong'"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope, can_view_log) "
             "VALUES (:r, 'cham_cong', false, false, false, false, 'own', false)"),
        {"r": vai},
    )
    db.commit()

    _migrate_them_o_xem_nhat_ky_cham_cong(db)

    co = db.execute(
        text("SELECT can_view_log FROM role_permissions "
             "WHERE role_id = :r AND module_key = 'cham_cong'"), {"r": vai},
    ).scalar()
    assert not co, "vai không xem được chấm công mà tự dưng đọc được nhật ký"


# ═══════════════════════════ 0183 — YCMH thôi ăn theo khoá `thu_mua`


def test_0183_bo_phan_mua_hang_khong_mat_hop_viec(db):
    """Gỡ lối tắt "có `thu_mua` là thấy YCMH cả công ty" ⇒ phải cấp bù phạm vi thật, nếu không
    sáng hôm sau bộ phận mua hàng mở màn ra chỉ còn yêu cầu của phòng mình."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN ('thu_mua', 'yeu_cau_mua_hang')"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'thu_mua', true, true, true, false, 'own')"),
        {"r": vai},
    )
    db.commit()

    _migrate_ycmh_khong_con_an_theo_khoa_thu_mua(db)

    row = db.execute(
        text("SELECT can_read, scope FROM role_permissions "
             "WHERE role_id = :r AND module_key = 'yeu_cau_mua_hang'"), {"r": vai},
    ).mappings().first()
    assert row is not None, "vai thu mua không được cấp bù ô Yêu cầu mua hàng"
    assert row["can_read"] and row["scope"] == "all", f"cấp bù sai: {dict(row)}"


def test_0183_khong_cap_bua_cho_vai_khong_lam_thu_mua(db):
    """Chỉ bù cho vai CÓ `thu_mua`. Vai chỉ có `kho`/`san_xuat`… xưa nay vẫn chỉ thấy phòng mình —
    nới cho họ là mở rộng dữ liệu ngoài ý muốn."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN ('thu_mua', 'yeu_cau_mua_hang')"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'yeu_cau_mua_hang', true, false, false, false, 'department')"),
        {"r": vai},
    )
    db.commit()

    _migrate_ycmh_khong_con_an_theo_khoa_thu_mua(db)

    pham_vi = db.execute(
        text("SELECT scope FROM role_permissions "
             "WHERE role_id = :r AND module_key = 'yeu_cau_mua_hang'"), {"r": vai},
    ).scalar()
    assert pham_vi == "department", f"vai không làm thu mua bị nới phạm vi lên {pham_vi}"


# ═══════════════════════ 0184 — Tự phục vụ có ô Thao tác


def test_0184_moi_vai_dang_tu_phuc_vu_deu_duoc_o_thao_tac(db):
    """⚠️ QUÊN MIGRATION NÀY = CẢ NHÀ MÁY KHÔNG CHẤM CÔNG ĐƯỢC.

    Cột `self_service.can_create` xưa nay chưa ai bật (nó vô nghĩa vì khoá chỉ dùng `read`). Từ
    11/08/2026 nó mới là ô cho GHI — chấm công, gửi đơn nghỉ, phiếu tăng ca, xin tạm ứng."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN ('self_service', 'nghi_phep')"))
    so_vai = db.execute(text("SELECT COUNT(*) FROM roles")).scalar()
    db.execute(text(
        "INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
        "can_delete, scope) SELECT id, 'self_service', true, false, false, false, 'own' FROM roles"
    ))
    db.commit()

    _migrate_tu_phuc_vu_co_o_thao_tac(db)

    n = db.execute(text(
        "SELECT COUNT(*) FROM role_permissions WHERE module_key = 'self_service' AND can_create"
    )).scalar()
    assert n == so_vai, f"mới {n}/{so_vai} vai có ô Thao tác — số còn lại hết chấm công được"


def test_0184_vai_khong_co_o_xem_thi_khong_tu_dung_duoc_ghi(db):
    """Ai đã bị gỡ ô Tự phục vụ thì đừng cấp lại cho họ quyền ghi."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN ('self_service', 'nghi_phep')"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'self_service', false, false, false, false, 'own')"),
        {"r": vai},
    )
    db.commit()

    _migrate_tu_phuc_vu_co_o_thao_tac(db)

    co = db.execute(
        text("SELECT can_create FROM role_permissions "
             "WHERE role_id = :r AND module_key = 'self_service'"), {"r": vai},
    ).scalar()
    assert not co, "vai đã bị gỡ ô Tự phục vụ mà lại được cấp quyền ghi"


def test_0184_nguoi_dang_xin_nghi_bang_o_nghi_phep_khong_mat_duong(db):
    """Xin nghỉ chuyển từ `nghi_phep:create` sang `self_service:create` ⇒ phải đổ cờ cũ sang."""
    db.execute(text("DELETE FROM role_permissions WHERE module_key IN ('self_service', 'nghi_phep')"))
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'self_service', false, false, false, false, 'own')"),
        {"r": vai},
    )
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'nghi_phep', true, true, false, false, 'own')"),
        {"r": vai},
    )
    db.commit()

    _migrate_tu_phuc_vu_co_o_thao_tac(db)

    co = db.execute(
        text("SELECT can_create FROM role_permissions "
             "WHERE role_id = :r AND module_key = 'self_service'"), {"r": vai},
    ).scalar()
    assert co, "người đang xin nghỉ bằng ô `nghi_phep:create` bị mất đường"


# ══════════════════════════════════════════ mg 0194 — Chấm công: một ô = một tab


def _o(db, role_id: int, module: str, cot: str):
    return db.execute(text(
        f"SELECT {cot} FROM role_permissions WHERE role_id = :r AND module_key = :m"
    ), {"r": role_id, "m": module}).scalar()


def test_0194_rot_quyen_khong_ai_mat_gi(db):
    """⭐ Điều kiện nghiệm thu số 1 của PRD: **không vai nào mất quyền sau khi cập nhật**.

    Migration tách "Cấu hình chấm công" thành ba ô và gộp hai khoá `di_muon` / `yeu_cau_chinh_cong`
    về màn Chấm công. Rót sai thì HCNS mở màn ra mất sạch tab cấu hình — mà chỉ lộ đúng lúc cần
    dùng, không có cảnh báo nào."""
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(text("DELETE FROM role_permissions WHERE role_id = :r AND module_key IN "
                    "('cham_cong', 'di_muon', 'yeu_cau_chinh_cong')"), {"r": vai})
    # Dựng bằng ORM: INSERT thô thiếu mấy cột NOT NULL không có server_default (can_create…).
    db.add_all([
        RolePermission(role_id=vai, module_key="cham_cong", can_read=True, can_update=True, scope="all"),
        RolePermission(role_id=vai, module_key="di_muon", can_read=True, can_approve=True, scope="all"),
        RolePermission(role_id=vai, module_key="yeu_cau_chinh_cong", can_read=True,
                       can_approve=True, scope="all"),
    ])
    db.commit()

    _migrate_cham_cong_mot_o_mot_tab(db)

    assert _o(db, vai, "cham_cong", "can_view_timesheet"), "đang xem bảng công mà mất tab đó"
    for cot in ("can_manage_locations", "can_manage_shifts", "can_manage_calendar"):
        assert _o(db, vai, "cham_cong", cot), f"'Cấu hình chấm công' cũ phải mở {cot}"
    assert _o(db, vai, "cham_cong", "can_approve_late_early"), "mất quyền duyệt đi muộn"
    assert _o(db, vai, "cham_cong", "can_approve"), "mất quyền duyệt yêu cầu chỉnh công"


def test_0194_khong_bat_bua_cho_vai_khong_co_gi(db):
    """Vế đối chứng: rót phải BÁM theo quyền cũ, không phải bật đại cho mọi vai.

    Thiếu vế này thì chỉ cần `UPDATE ... SET tất cả = true` là test trên vẫn xanh, mà cả công ty
    được quyền chốt kỳ công."""
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(text("DELETE FROM role_permissions WHERE role_id = :r AND module_key IN "
                    "('cham_cong', 'di_muon', 'yeu_cau_chinh_cong')"), {"r": vai})
    db.add(RolePermission(role_id=vai, module_key="cham_cong", can_read=True, scope="own"))
    db.commit()

    _migrate_cham_cong_mot_o_mot_tab(db)

    # can_read ⇒ vẫn xem bảng công như trước…
    assert _o(db, vai, "cham_cong", "can_view_timesheet")
    # …nhưng KHÔNG có gì khác được bật thêm.
    for cot in ("can_manage_locations", "can_manage_shifts", "can_manage_calendar",
                "can_approve_late_early", "can_approve"):
        assert not _o(db, vai, "cham_cong", cot), f"bật bừa {cot} cho vai không hề có quyền đó"


def test_0194_vai_chi_co_di_muon_van_duoc_dong_cham_cong(db):
    """Vai duyệt đi muộn mà CHƯA hề có dòng `cham_cong` — phải tạo dòng mới cho họ.

    Không tạo thì rót xong quyền rơi vào hư không: khoá cũ bỏ đi, khoá mới không có dòng nào để
    ghi, và người đó mất sạch quyền duyệt."""
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(text("DELETE FROM role_permissions WHERE role_id = :r AND module_key IN "
                    "('cham_cong', 'di_muon', 'yeu_cau_chinh_cong')"), {"r": vai})
    db.add(RolePermission(role_id=vai, module_key="di_muon", can_read=True,
                          can_approve=True, scope="department"))
    db.commit()

    _migrate_cham_cong_mot_o_mot_tab(db)

    assert _o(db, vai, "cham_cong", "can_approve_late_early"), "quyền duyệt rơi vào hư không"
    assert _o(db, vai, "cham_cong", "can_read"), "tạo dòng mới thì phải mở được màn mà dùng"


def test_0194_chay_lai_lan_hai_khong_doi_gi(db):
    """Migration phải chạy lại được — DB thật có thể chạy lượt hai sau khi khởi động lại."""
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    _migrate_cham_cong_mot_o_mot_tab(db)
    truoc = _o(db, vai, "cham_cong", "can_view_timesheet")
    _migrate_cham_cong_mot_o_mot_tab(db)
    assert _o(db, vai, "cham_cong", "can_view_timesheet") == truoc


# --- 0198: màn Lương đổi từ ô ma `self_service` sang ô THẬT `luong` ----------------------------
#
# Vì sao phải canh: cổng vào màn Lương bị gỡ khỏi `self_service` (ô cấp sẵn cho mọi vai, ĐÃ gỡ
# khỏi bảng phân quyền nên HCNS không tắt được). Nếu migration rót thiếu thì sáng hôm sau cả
# xưởng mất màn Lương — mất luôn phiếu lương của chính mình. Rót THỪA còn tệ hơn: bật nhầm
# `can_view_payroll_table` là thợ đọc được lương cả công ty.

def _dong_luong(db, role_id: int) -> dict | None:
    row = db.execute(
        text("SELECT scope, can_read, can_create, can_view_payroll_table, can_view_salary "
             "FROM role_permissions WHERE role_id = :r AND module_key = 'luong'"),
        {"r": role_id},
    ).mappings().first()
    return dict(row) if row else None


def _vai_khong_co_luong(db) -> int:
    """Một vai có ô tự phục vụ nhưng CHƯA có dòng `luong` — đúng cảnh 16/20 vai trên DB dev."""
    vai = db.execute(text("SELECT id FROM roles LIMIT 1")).scalar()
    db.execute(text("DELETE FROM role_permissions WHERE role_id = :r AND module_key = 'luong'"),
               {"r": vai})
    db.execute(text("DELETE FROM role_permissions WHERE role_id = :r AND module_key = 'self_service'"),
               {"r": vai})
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'self_service', true, true, false, false, 'own')"),
        {"r": vai},
    )
    db.commit()
    return vai


def test_0198_vai_chua_co_o_luong_thi_duoc_rot_phan_cua_toi(db):
    """Gỡ cổng ma mà không rót ô thật = cả xưởng mất màn Lương."""
    vai = _vai_khong_co_luong(db)
    assert _dong_luong(db, vai) is None, "dựng sai tình huống: vai này phải chưa có dòng luong"
    _migrate_luong_o_that_thay_o_ma(db)
    q = _dong_luong(db, vai)
    assert q is not None, "vai đi cửa self_service mà không được rót ô Lương ⇒ mất màn"
    assert q["can_read"] and q["can_create"], f"thiếu Xem/Thao tác: {q}"
    assert q["scope"] == "own", f"phải là phạm vi Của tôi, không phải {q['scope']}"


def test_0198_KHONG_rot_o_bang_luong_cho_tho(db):
    """⭐ Rót thừa một ô là thợ đọc được lương cả công ty — *"công nhân làm gì có quyền đó đâu"*."""
    vai = _vai_khong_co_luong(db)
    _migrate_luong_o_that_thay_o_ma(db)
    q = _dong_luong(db, vai)
    assert not q["can_view_payroll_table"], "rót nhầm ô Bảng lương tháng"
    assert not q["can_view_salary"], "rót nhầm ô Xem lương ⇒ đọc được lương người khác"


def test_0198_vai_da_duoc_cau_hinh_thi_KHONG_bi_dung_toi(db):
    """Ô đã có người bật/tắt có chủ đích — migration không được đè lên ý của họ."""
    vai = _vai_khong_co_luong(db)
    # HCNS đã cố ý cho vai này XEM mà không cho GHI ở màn Lương.
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'luong', true, false, false, false, 'department')"),
        {"r": vai},
    )
    db.commit()
    _migrate_luong_o_that_thay_o_ma(db)
    q = _dong_luong(db, vai)
    assert not q["can_create"], "migration bật thêm ô Thao tác mà không ai yêu cầu"
    assert q["scope"] == "department", "migration hạ phạm vi người ta đang dùng"


def test_0198_dong_trong_tron_van_duoc_rot(db):
    """Dòng bật-hết-false trông y như CHƯA CẤP trên bảng phân quyền ⇒ phải xử như chưa có."""
    vai = _vai_khong_co_luong(db)
    db.execute(
        text("INSERT INTO role_permissions (role_id, module_key, can_read, can_create, can_update, "
             "can_delete, scope) VALUES (:r, 'luong', false, false, false, false, 'own')"),
        {"r": vai},
    )
    db.commit()
    _migrate_luong_o_that_thay_o_ma(db)
    q = _dong_luong(db, vai)
    assert q["can_read"] and q["can_create"], f"dòng trống trơn không được rót: {q}"


def test_0198_chay_lai_khong_de_hang_trung(db):
    vai = _vai_khong_co_luong(db)
    _migrate_luong_o_that_thay_o_ma(db)
    _migrate_luong_o_that_thay_o_ma(db)
    n = db.execute(
        text("SELECT count(*) FROM role_permissions WHERE role_id = :r AND module_key = 'luong'"),
        {"r": vai},
    ).scalar()
    assert n == 1, f"chạy lại đẻ ra {n} dòng luong"
