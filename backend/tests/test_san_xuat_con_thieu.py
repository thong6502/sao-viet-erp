"""Con số CÒN THIẾU — dẫn xuất, chỉ để BÀY (docs/spec-thuc-te-vs-ke-hoach.md §2.3).

Cổng đóng nhóm KHÔNG đổi: `dong_nhom._danh_gia` vẫn đo "đã phân loại / đã nhận", cố ý không so
mục tiêu đơn (chú thích dòng 63 của module đó). Test dưới đây chốt đúng hai điều:
  · số còn thiếu XUẤT HIỆN ở bước và ở nhóm;
  · nó KHÔNG làm nhóm mất quyền đóng.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_san_luong import SanXuatBatch
from app.services.san_xuat import dong_nhom

# `_authz` đã có sẵn ở `tests/test_san_xuat_board.py:100` (và được `test_san_xuat_thuc_thi` re-export)
# — dựng đúng như `deps.get_authorization_service`, nhận `RoleRepository` chứ KHÔNG nhận `Session`.
# Đừng chép lần hai, tái dùng cho khớp mọi nơi khác trong bộ test module này.
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _cvs, _mot_cv, _phat_hanh_vao_to, _to_khoan, _authz, admin, customer, db, lsx_svc, orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def test_buoc_chay_thieu_thi_con_thieu_bang_hieu(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT1")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "tờ"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=9400, tot=9400, hong=0, don_vi="tờ"))
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["muc_tieu"] == 10000.0
    assert ct["san_luong"]["con_thieu"] == 600.0
    assert ct["san_luong"]["don_vi"] == "tờ"


def test_chay_du_thi_con_thieu_bang_khong(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT2")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_ra = 500
    cv.don_vi_ra = "tờ"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
                        tong=520, tot=520, hong=0, don_vi="tờ"))
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["con_thieu"] == 0.0   # chạy dư KHÔNG ra số âm


def test_buoc_khong_khai_muc_tieu_thi_khong_bia_so(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT3")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_ra = None
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["muc_tieu"] is None
    assert ct["san_luong"]["con_thieu"] is None


def test_nhom_co_so_con_thieu_ma_cong_dong_khong_doi(
    db, orders, lsx_svc, admin, customer,
):
    """Số còn thiếu XUẤT HIỆN ở nhóm, nhưng KHÔNG tự mở hay tự khoá cổng đóng.

    Kịch bản KHÔNG dựng đủ điều kiện đóng (CV còn `CV_DANG_CHAY`, chưa có `SanXuatKcsBatch` nào
    ghi "đã nhận") — `du_dong_du`/`du_dong_thieu` vì vậy đều False, giống hệt giá trị mà
    `_danh_gia` (KHÔNG bị đụng bởi Task 5) đã trả từ trước. Assert thẳng cả hai khoá cổng để
    chứng minh việc thêm `muc_tieu`/`da_dat`/`con_thieu` không làm lệch chúng đi, thay vì chỉ nói
    suông trong docstring."""
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT4")
    cv.trang_thai = CV_DANG_CHAY
    cv.la_kcs_cuoi = True
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "cuốn"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=9400, tot=9400, hong=0, don_vi="cuốn"))
    db.commit()

    dk = dong_nhom.dieu_kien_dong_nhom(db, nhom_id=cv.nhom_id)
    assert dk["muc_tieu"] == 10000.0
    assert dk["da_dat"] == 9400.0
    assert dk["con_thieu"] == 600.0
    # Hàng rào thật của "cổng không đổi" — không phải suy đoán, là giá trị `_danh_gia` tính ra:
    # CV chưa hoàn thành ⇒ chưa đóng đủ; chưa dựng `SanXuatKcsBatch` nào ⇒ điều kiện (3) "KCS cuối
    # đã phân loại hết số nhận" cũng chưa đạt (chưa NHẬN gì) ⇒ chưa đủ đóng thiếu.
    assert dk["du_dong_du"] is False
    assert dk["du_dong_thieu"] is False
    # 6 điều kiện cũ còn nguyên — số còn thiếu KHÔNG phải điều kiện thứ 7. `dieu_kien` là LIST các
    # dict {"ma": ...}, so `in` với chuỗi trên chính list đó luôn False (bug im lặng) — phải rút mã
    # ra thành set rồi mới so.
    assert "con_thieu" not in {d["ma"] for d in dk["dieu_kien"]}


def test_work_items_con_thieu_dung_tung_dong_khi_gop_nhieu_viec(
    db, orders, lsx_svc, admin, customer,
):
    """Canh nhánh nạp GỘP (`SanXuatSanLuongRepository.tong_tot_nhieu`, `board.work_items` dùng nó
    để tránh N+1): HAI công việc CÙNG một tổ, mỗi cái HAI batch, mục tiêu khác nhau hẳn nhau.

    Ba test mức-một-việc phía trên đều đi qua `chi_tiet_cong_viec` (dùng `tong_tot` đơn lẻ) hoặc
    nhóm chỉ có MỘT công việc — không cái nào phát hiện được `group_by` gán nhầm tổng sang id khác
    hay map tra sai key. Test này mới canh đúng chỗ đó: hai con số còn thiếu PHẢI khác nhau đúng
    theo đúng công việc của nó, không hoán đổi/chung một số."""
    from app.services.san_xuat import board

    to = _to_khoan(db, admin, ma="TO-CT6")
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cvs = _cvs(db, to)
    assert len(cvs) >= 2, "cần ít nhất hai công việc cùng tổ để canh nạp gộp"
    cv1, cv2 = cvs[0], cvs[1]

    cv1.trang_thai = CV_DANG_CHAY
    cv1.so_luong_ra = 10000
    cv1.don_vi_ra = "tờ"
    cv2.trang_thai = CV_DANG_CHAY
    cv2.so_luong_ra = 3000
    cv2.don_vi_ra = "tờ"
    db.add_all([
        SanXuatBatch(cong_viec_id=cv1.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
                     tong=4000, tot=4000, hong=0, don_vi="tờ"),
        SanXuatBatch(cong_viec_id=cv1.id, bat_dau=_T0 + timedelta(hours=1),
                     ket_thuc=_T0 + timedelta(hours=2), tong=3000, tot=3000, hong=0, don_vi="tờ"),
        SanXuatBatch(cong_viec_id=cv2.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
                     tong=1000, tot=1000, hong=0, don_vi="tờ"),
        SanXuatBatch(cong_viec_id=cv2.id, bat_dau=_T0 + timedelta(hours=1),
                     ket_thuc=_T0 + timedelta(hours=2), tong=500, tot=500, hong=0, don_vi="tờ"),
    ])
    db.commit()

    res = board.work_items(db, admin, _authz(db), team_id=to.id)
    by_id = {item["id"]: item for item in res["cong_viec"]}
    # cv1: tổng tốt 4000+3000=7000, mục tiêu 10000 ⇒ còn thiếu 3000.
    assert by_id[cv1.id]["con_thieu"] == 3000.0
    # cv2: tổng tốt 1000+500=1500, mục tiêu 3000 ⇒ còn thiếu 1500 — khác hẳn số của cv1. Nếu
    # `group_by`/map lệch key (vd gán nhầm tổng của cv1 cho cv2) thì một trong hai assert đỏ.
    assert by_id[cv2.id]["con_thieu"] == 1500.0


# --- Mốc chấm rút theo lượng THỰC NHẬN ------------------------------------------------------
def _giao_toi(db, dich_cv, so_luong: float, don_vi: str, *, nguon_cv_id: int | None = None):
    """Một bàn giao ĐÃ XÁC NHẬN đổ về `dich_cv` — đây là "thực nhận" của bước đó."""
    from app.models.san_xuat_san_luong import BG_XAC_NHAN, SanXuatBanGiao

    db.add(SanXuatBanGiao(
        nguon_cong_viec_id=nguon_cv_id or dich_cv.id,
        dich_cong_viec_id=dich_cv.id,
        so_luong=so_luong, don_vi=don_vi, trang_thai=BG_XAC_NHAN,
    ))
    db.commit()


def test_nhan_thieu_thi_moc_rut_theo_ti_le_khong_de_ke_hoach(
    db, orders, lsx_svc, admin, customer
):
    """Tổ trước giao thiếu ⇒ mốc chấm của tổ này rút theo tỉ lệ, KẾ HOẠCH giữ nguyên.

    Kế hoạch: vào 1.000 tờ → ra 1.000 cái. Thực nhận 960 tờ ⇒ mốc còn 960 cái. Làm đủ 960 thì
    KHÔNG thiếu gì — hụt 40 là của tổ trước, không đổ sang đây.
    """
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TN1")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_vao, cv.don_vi_vao = 1000, "tờ"
    cv.so_luong_ra, cv.don_vi_ra = 1000, "cái"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=960, tot=960, hong=0, don_vi="cái"))
    db.commit()
    _giao_toi(db, cv, 960, "tờ")

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["thuc_nhan"] == 960.0
    assert ct["san_luong"]["muc_tieu"] == 960.0
    assert ct["san_luong"]["con_thieu"] == 0.0
    # Kế hoạch KHÔNG bị đè.
    assert ct["cong_viec"]["so_luong_vao"] == 1000.0
    assert ct["cong_viec"]["so_luong_ra"] == 1000.0
    assert ct["cong_viec"]["da_lam"] == 960.0


def test_nhan_du_ma_lam_thieu_thi_van_hut_dung_o_to_nay(db, orders, lsx_svc, admin, customer):
    """Nhận đủ 1.000 mà chỉ ra 960 ⇒ hụt 40 nằm ở CHÍNH tổ này — đúng địa chỉ."""
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TN2")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_vao, cv.don_vi_vao = 1000, "tờ"
    cv.so_luong_ra, cv.don_vi_ra = 1000, "cái"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=1000, tot=960, hong=40, don_vi="cái"))
    db.commit()
    _giao_toi(db, cv, 1000, "tờ")

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["muc_tieu"] == 1000.0
    assert ct["san_luong"]["con_thieu"] == 40.0


def test_khong_ai_giao_toi_thi_giu_nguyen_moc_ke_hoach(db, orders, lsx_svc, admin, customer):
    """Bước ĐẦU chuỗi lấy vật tư từ kho, không ai bàn giao tới ⇒ mốc vẫn là kế hoạch, không tụt về 0."""
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TN3")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_vao, cv.don_vi_vao = 1000, "tờ"
    cv.so_luong_ra, cv.don_vi_ra = 1000, "cái"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=900, tot=900, hong=0, don_vi="cái"))
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["thuc_nhan"] is None
    assert ct["san_luong"]["muc_tieu"] == 1000.0
    assert ct["san_luong"]["con_thieu"] == 100.0


def test_moc_quy_doi_khi_vao_ra_khac_don_vi(db, orders, lsx_svc, admin, customer):
    """Nhận "tờ" mà ra "cái": 12 tờ → 1.188 cái. Nhận 11 tờ ⇒ mốc 1.089 cái, không phải 11."""
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TN4")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_vao, cv.don_vi_vao = 12, "tờ"
    cv.so_luong_ra, cv.don_vi_ra = 1188, "cái"
    db.commit()
    _giao_toi(db, cv, 11, "tờ")

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["muc_tieu"] == 1089.0
    assert ct["san_luong"]["con_thieu"] == 1089.0


def test_nhan_du_bu_hao_thi_moc_khong_phinh_len(db, orders, lsx_svc, admin, customer):
    """Nhà in giao dư để bù hao (1.050 tờ cho 1.000 cái) — nhận dư KHÔNG bắt tổ làm nhiều hơn
    cam kết. Mốc chỉ rút xuống, không đẩy lên."""
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TN5")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_vao, cv.don_vi_vao = 1000, "tờ"
    cv.so_luong_ra, cv.don_vi_ra = 1000, "cái"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=1000, tot=1000, hong=0, don_vi="cái"))
    db.commit()
    _giao_toi(db, cv, 1050, "tờ")

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["muc_tieu"] == 1000.0
    assert ct["san_luong"]["con_thieu"] == 0.0


def test_ban_giao_khac_don_vi_dau_vao_thi_khong_rut_moc(db, orders, lsx_svc, admin, customer):
    """Bàn giao ghi "con" mà bước nhận "tờ": không đem số đó chia cho `so_luong_vao` — chia bừa ra
    mốc bịa (đúng lỗi đã thấy trên dev: nhận 26.888 chia cho 68 ⇒ thiếu 7 triệu)."""
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TN6")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_vao, cv.don_vi_vao = 68, "tờ"
    cv.so_luong_ra, cv.don_vi_ra = 18, "tờ"
    db.commit()
    _giao_toi(db, cv, 26888, "con")

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["thuc_nhan"] is None
    assert ct["san_luong"]["muc_tieu"] == 18.0
    assert ct["san_luong"]["con_thieu"] == 18.0
