"""Bước NGOÀI dòng giấy đo bằng ĐƠN VỊ CỦA CHÍNH NÓ — từ danh mục xuống tới bàn tổ.

Ghi kẽm CTP không chạm tờ giấy nào nên nó đứng ngoài chuỗi bù hao: `so_luong_vao/ra` của nó KHÔNG
do dòng giấy quyết, mà do `cong_doan.cong_thuc_san_luong` (`so_kem` ⇒ 4 bản). Trước 10/09/2026 con
số ấy đi tới bàn tổ mà không mang theo chữ nào — thẻ việc hiện `0 → 0`, ô Ghi mẻ trống đơn vị, khối
Sản lượng nói "mục tiêu 0 · đủ mục tiêu" ngay lúc chưa ai chạm máy.

Bài này soi trọn đường đi của một bước như thế (`docs/superpowers/specs/2026-09-10-ban-to-du-thong-
tin-design.md` §10):

  ① danh mục khai công thức + `don_vi_san_luong` ⇒ kế hoạch ra 4 và câu diễn giải có ĐUÔI đơn vị;
  ② phát hành ⇒ công việc mang `don_vi_vao/ra = "kem"`, cờ `ngoai_dong`, dặn dò, thẻ quy cách,
    dải phút chạy;
  ③ ghi mẻ ở tổ ⇒ đơn vị mặc định là `kem`, mục tiêu 4, còn thiếu rút dần;
  ④ bước TRÊN dòng giấy không xê dịch một số nào (hồi quy).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.cong_doan import CongDoan
from app.models.department import Department
from app.models.lsx import LB_MAY, LsxCongDoan
from app.models.san_xuat import CV_DANG_CHAY, SanXuatCongViec
from app.models.san_xuat_san_luong import SanXuatBatch
from app.repositories.cong_doan_repo import CongDoanRepository
from app.services.bien_cong_thuc import quy_cach_bien
from app.services.cong_doan_service import CongDoanService
from app.services.san_xuat import board, release, san_luong

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
    """Tổ chế bản, admin làm tổ trưởng — để qua GATE §6 khi gọi thẳng service ghi mẻ."""
    d = Department(
        name="Tổ kỹ thuật (ngoài dòng)", code="TO-KT-NDG", la_san_xuat=True,
        has_piece_work=True, head_user_id=admin.id,
    )
    db.add(d)
    db.flush()
    return d


def _cd_ghi_kem(db):
    """Công đoạn NGOÀI dòng giấy khai đủ CẶP: ra bao nhiêu (`so_kem`) và ra bằng gì (`kem`).

    Đi qua `CongDoanService` chứ không ORM trần để ăn đúng `_validate` — chính chỗ chặn khai đơn vị
    sản lượng cho bước đã có đơn vị chặng, và chặn mã đơn vị không có trong danh mục.
    """
    return CongDoanService(CongDoanRepository(db)).create(dict(
        ma="CD-KEM-X", ten="Ghi kẽm CTP", nhom="prepress",
        che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty", first_unit_floor=0,
        cong_thuc_san_luong="so_kem", don_vi_san_luong="kem",
    ))


def _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, *, to_id):
    """Một lệnh 4 bản kẽm, có thêm bước Ghi kẽm CTP đứng ĐẦU routing và mang câu dặn dò.

    Chạy `_ap_chuoi_nguoc` — đúng hàm mà nút Lưu routing chạy — thay vì gán tay `so_luong_vao/ra`:
    thứ đang soi CHÍNH LÀ "số của bước ngoài dòng có tự hiện không", gán tay là tự trả lời hộ.
    """
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Số kẽm là thứ công thức ăn vào; lệnh dựng từ phiếu 1 mặt 4 màu nên khai thẳng cho khỏi phụ
    # thuộc engine bình bài (bài này không soi số kẽm được tính ra sao).
    a.quy_cach_json = {**(a.quy_cach_json or {}), "so_kem": 4}
    cd = _cd_ghi_kem(db)
    dau = min(c.thu_tu or 0 for c in a.cong_doans)
    buoc = LsxCongDoan(
        lsx_id=a.id, thu_tu=dau - 1, ten="Ghi kẽm CTP", nhom="prepress", loai_buoc=LB_MAY,
        department_id=to_id, cong_doan_id=cd.id, ghi_chu=_DAN_DO,
    )
    db.add(buoc)
    db.flush()
    db.expire(a, ["cong_doans"])
    lsx_svc._ap_chuoi_nguoc(a)
    db.commit()
    return a, buoc


def _cv_cua(db, goi, step_key: str) -> SanXuatCongViec:
    return db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=step_key).one()


# --- ① Kế hoạch: số tự hiện, câu diễn giải có đuôi đơn vị ------------------------------------
def test_buoc_ngoai_dong_ra_bon_ban_kem_va_dien_giai_co_don_vi(
    db, orders, lsx_svc, admin, customer
):
    to = _to_ky_thuat(db, admin)
    a, buoc = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)

    # Bước ngoài dòng để TRỐNG cả hai ô đơn vị chặng (menu công đoạn chỉ còn 5 chặng, mg `0273`).
    assert buoc.don_vi_vao is None and buoc.don_vi_ra is None
    # Vào = ra = 4: hệ số vào→ra của bước ngoài dòng là 1,0 và công đoạn không bù hao.
    assert float(buoc.so_luong_ra) == 4 and float(buoc.so_luong_vao) == 4

    r = lsx_svc.buoc_ngoai_dong(buoc, quy_cach_bien(a))
    assert r["so_luong_ra"] == 4 and r["so_luong_vao"] == 4

    cau = lsx_svc.san_luong_dien_giai(
        buoc, db.get(CongDoan, buoc.cong_doan_id), quy_cach_bien(a))
    # Đuôi đơn vị là thứ mg `0289` sinh ra để cứu: trước đó câu này cụt ở "Số bản kẽm = 4".
    assert cau.startswith("Số bản kẽm =") and cau.endswith("bản kẽm")


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
    assert dm["sl_dien_giai"].endswith("bản kẽm")
    # Ba số phút cùng thang, có mặt kể cả khi bằng 0 (bước chưa gán máy).
    assert {"chay_phut", "chay_phut_min", "chay_phut_max"} <= set(dm)

    assert cv.ghi_chu == _DAN_DO

    qc = cv.quy_cach_json
    assert qc["so_kem"] == 4
    # Thẻ rút gọn, KHÔNG bê cả `lsx.quy_cach_json` xuống tổ.
    assert set(qc) <= {"giay", "dinh_luong", "kho_in", "kho_tp", "so_mat", "so_mau",
                       "so_kem", "so_con", "so_luong", "ghi_chu_ky_thuat"}
    assert "×" in qc["kho_in"], "khổ tờ in ghép thành một chuỗi mm để mọi màn đọc giống nhau"

    # Payload bàn tổ bày đúng những thứ trên (FE không phải suy lại từ mã đơn vị).
    item = board._item_dict(cv, {}, {}, {}, {})
    assert item["ngoai_dong"] is True and item["ghi_chu"] == _DAN_DO
    assert item["quy_cach"]["so_kem"] == 4
    assert item["sl_dien_giai"].endswith("bản kẽm")


# --- ③ Bàn tổ: ghi mẻ theo đơn vị bản địa ----------------------------------------------------
def test_ghi_me_lay_don_vi_ban_dia_va_muc_tieu_bon(db, orders, lsx_svc, admin, customer):
    to = _to_ky_thuat(db, admin)
    a, buoc = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    cv = _cv_cua(db, goi, buoc.step_key)
    cv.trang_thai = CV_DANG_CHAY
    db.commit()

    r = san_luong.tao_batch(
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
    assert dm["ngoai_dong"] is False and dm["sl_dien_giai"] is None
    # Bước in có máy nên có giờ thật; dải luôn bọc lấy số giữa (máy chưa khai min/max ⇒ bằng nhau).
    assert dm["chay_phut"] > 0
    assert dm["chay_phut_min"] <= dm["chay_phut"] <= dm["chay_phut_max"]
