"""Bước NGOÀI dòng giấy đo bằng ĐƠN VỊ CỦA CHÍNH NÓ — từ lệnh xuống tới bàn tổ.

Ghi kẽm CTP không chạm tờ giấy nào nên nó đứng ngoài chuỗi bù hao: `so_luong_vao/ra` của nó KHÔNG
do dòng giấy quyết, mà do người lập lệnh TỰ KHAI ở bước (đơn vị `kem` + 4 bản). Công thức sản lượng
ra ở danh mục (`cong_doan.cong_thuc_san_luong` + `don_vi_san_luong`) GỠ 18/09/2026 (mg `0324`).

Bài này soi trọn đường đi của một bước như thế (`docs/superpowers/specs/2026-09-10-ban-to-du-thong-
tin-design.md` §10):

  ① kế hoạch: khai tay 4 bản kẽm thì giữ qua chuỗi ngược; không khai thì bước đứng ở 0;
  ② phát hành ⇒ công việc mang `don_vi_vao/ra = "kem"`, cờ `ngoai_dong`, dặn dò, thẻ quy cách,
    dải phút chạy;
  ③ ghi mẻ ở tổ ⇒ đơn vị mặc định là `kem`, mục tiêu 4, còn thiếu rút dần;
  ④ bước TRÊN dòng giấy không xê dịch một số nào (hồi quy).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.department import Department
from app.models.lsx import LB_MAY, LsxCongDoan
from app.models.san_xuat import CV_DANG_CHAY, SanXuatCongViec
from app.models.san_xuat_san_luong import SanXuatBatch
from app.repositories.cong_doan_repo import CongDoanRepository
from app.services.cong_doan_service import CongDoanService
from app.services.san_xuat import board, release
from tests.san_xuat_me_fixtures import tao_me
from tests.quyen_to_fixtures import cap_quyen_to

# Fixtures + helper luồng thật (đơn → lệnh → sẵn sàng).
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

_T0 = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
_DAN_DO = "Kẽm cũ của đợt 1 còn dùng được, chỉ ghi lại tay 3."


def _to_ky_thuat(db, admin) -> Department:
    """Tổ chế bản, vai của admin được bật đủ quyền trên dòng tổ — để qua cổng ghi mẻ."""
    d = Department(
        name="Tổ kỹ thuật (ngoài dòng)", code="TO-KT-NDG", la_san_xuat=True,
        has_piece_work=True,
    )
    db.add(d)
    db.flush()
    cap_quyen_to(db, admin, d)
    return d


def _cd_ghi_kem(db):
    """Công đoạn NGOÀI dòng giấy: bỏ TRỐNG cả hai ô đơn vị chặng.

    Đi qua `CongDoanService` chứ không ORM trần để ăn đúng `_validate`.
    """
    return CongDoanService(CongDoanRepository(db)).create(dict(
        ma="CD-KEM-X", ten="Ghi kẽm CTP", nhom="prepress",
        che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty", first_unit_floor=0,
    ))


def _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, *, to_id, khai_tay=True):
    """Một lệnh có thêm bước Ghi kẽm CTP đứng ĐẦU routing và mang câu dặn dò.

    `khai_tay` = người lập lệnh khai `kem → kem`, 4 bản ở bước (đúng thứ drawer gửi lên). Chạy
    `_ap_chuoi_nguoc` — đúng hàm mà nút Lưu routing chạy — để soi số khai tay có sống sót không.
    """
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    a.quy_cach_json = {**(a.quy_cach_json or {}), "so_kem": 4}
    cd = _cd_ghi_kem(db)
    dau = min(c.thu_tu or 0 for c in a.cong_doans)
    khai = dict(don_vi_vao="kem", don_vi_ra="kem", so_luong_vao=4, so_luong_ra=4) \
        if khai_tay else {}
    buoc = LsxCongDoan(
        lsx_id=a.id, thu_tu=dau - 1, ten="Ghi kẽm CTP", nhom="prepress", loai_buoc=LB_MAY,
        department_id=to_id, cong_doan_id=cd.id, ghi_chu=_DAN_DO, **khai,
    )
    db.add(buoc)
    db.flush()
    db.expire(a, ["cong_doans"])
    lsx_svc._ap_chuoi_nguoc(a)
    db.commit()
    return a, buoc


def _cv_cua(db, goi, step_key: str) -> SanXuatCongViec:
    return db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=step_key).one()


# --- ① Kế hoạch: số khai tay sống qua chuỗi ngược; không khai thì đứng ở 0 ------------------
def test_buoc_ngoai_dong_khai_tay_giu_so_khong_khai_thi_bang_0(
    db, orders, lsx_svc, admin, customer
):
    to = _to_ky_thuat(db, admin)
    a, buoc = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    assert (buoc.don_vi_vao, buoc.don_vi_ra) == ("kem", "kem")
    assert float(buoc.so_luong_ra) == 4 and float(buoc.so_luong_vao) == 4
    # Hai đầu đều là số người ta gõ ⇒ không hao, không hệ số.
    assert float(buoc.hao_hut) == 0 and float(buoc.he_so_quy_doi) == 0


def test_buoc_ngoai_dong_khong_khai_thi_dung_o_0(db, orders, lsx_svc, admin, customer):
    """Danh mục không còn công thức sản lượng ra (mg `0324`) ⇒ bước chưa khai đứng ở 0, không đoán."""
    to = _to_ky_thuat(db, admin)
    _a, buoc = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id,
                                khai_tay=False)
    assert (buoc.don_vi_vao, buoc.don_vi_ra) == (None, None)
    assert float(buoc.so_luong_ra or 0) == 0 and float(buoc.so_luong_vao or 0) == 0


# --- ② Phát hành: hành lý của thẻ việc -------------------------------------------------------
def test_snapshot_mang_don_vi_dan_do_quy_cach_va_dai_thoi_luong(
    db, orders, lsx_svc, admin, customer
):
    to = _to_ky_thuat(db, admin)
    a, buoc = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cv = _cv_cua(db, goi, buoc.step_key)
    # Đơn vị BẢN ĐỊA: điền đúng một chỗ này thì ghi mẻ · bàn giao · KCS · yêu cầu kho · phân bổ
    # lương đều có đơn vị (§3.3).
    assert cv.don_vi_vao == "kem" and cv.don_vi_ra == "kem"
    assert float(cv.so_luong_ra) == 4

    dm = cv.dinh_muc_json
    assert dm["ngoai_dong"] is True
    assert "sl_dien_giai" not in dm            # gỡ 18/09/2026 cùng công thức sản lượng ra
    # Ba số phút cùng thang, có mặt kể cả khi bằng 0 (bước chưa gán máy).
    assert {"chay_phut", "chay_phut_min", "chay_phut_max"} <= set(dm)

    assert cv.ghi_chu == _DAN_DO

    qc = cv.quy_cach_json
    assert qc["so_kem"] == 4
    # Thẻ rút gọn, KHÔNG bê cả `lsx.quy_cach_json` xuống tổ.
    assert set(qc) <= {"giay", "dinh_luong", "kho_nguyen", "kho_in", "kho_tp", "cach_in",
                       "so_mat", "so_mau", "so_kem", "muc_a", "muc_b", "so_con", "so_luong",
                       "ghi_chu_ky_thuat"}
    assert "×" in qc["kho_in"], "khổ tờ in ghép thành một chuỗi mm để mọi màn đọc giống nhau"

    # Payload bàn tổ bày đúng những thứ trên (FE không phải suy lại từ mã đơn vị).
    item = board._item_dict(cv, {}, {}, {}, {})
    assert item["ngoai_dong"] is True and item["ghi_chu"] == _DAN_DO
    assert item["quy_cach"]["so_kem"] == 4
    assert "sl_dien_giai" not in item


# --- ③ Bàn tổ: ghi mẻ theo đơn vị bản địa ----------------------------------------------------
def test_ghi_me_lay_don_vi_ban_dia_va_muc_tieu_bon(db, orders, lsx_svc, admin, customer):
    to = _to_ky_thuat(db, admin)
    a, buoc = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    cv = _cv_cua(db, goi, buoc.step_key)
    cv.trang_thai = CV_DANG_CHAY
    db.commit()

    r = tao_me(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=2, tot=2,
    )
    # Không truyền `don_vi` ⇒ lấy `don_vi_ra` của công việc. Trước 10/09/2026 chỗ này ném
    # "Batch chưa có đơn vị." vì bước ngoài dòng xuống tổ với hai cột đơn vị rỗng.
    b = db.get(SanXuatBatch, r["batch_id"])
    assert b.don_vi == "kem"

    muc_tieu, con_thieu = board._con_thieu(cv, 2.0)
    assert muc_tieu == 4 and con_thieu == 2
    assert board._con_thieu(cv, 4.0)[1] == 0


# --- ④ Hồi quy: bước TRÊN dòng giấy không xê dịch --------------------------------------------
def test_buoc_tren_dong_giay_giu_nguyen_don_vi_va_co_dai_phut(
    db, orders, lsx_svc, admin, customer
):
    to = _to_ky_thuat(db, admin)
    a, _buoc = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    in_buoc = _in_step(db, a.id)
    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cv = _cv_cua(db, goi, in_buoc.step_key)
    assert cv.don_vi_vao == in_buoc.don_vi_vao == "to"
    assert cv.don_vi_ra == in_buoc.don_vi_ra == "to"
    assert float(cv.so_luong_vao) == float(in_buoc.so_luong_vao)

    dm = cv.dinh_muc_json
    assert dm["ngoai_dong"] is False
    # Bước in có máy nên có giờ thật; dải luôn bọc lấy số giữa (máy chưa khai min/max ⇒ bằng nhau).
    assert dm["chay_phut"] > 0
    assert dm["chay_phut_min"] <= dm["chay_phut"] <= dm["chay_phut_max"]
