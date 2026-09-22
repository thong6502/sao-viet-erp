"""Dàn cảnh MẺ dùng chung cho test bàn tổ.

Mẻ mới tự lấy cấu hình Khoán từ công đoạn. Test nào chỉ cần "có một mẻ" gọi `tao_me`; không phải
tạo hay chọn một Công việc khoán độc lập.

Thay các helper của `test_san_xuat_phan_bo` (xoá cùng engine chia sản lượng, mg 0322): chấm công,
khoảng tham gia, dàn cảnh "công việc đang chạy + một mẻ tốt".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.attendance import CHECK_IN, CHECK_OUT, AttendanceLog, WorkShift
from app.models.piece_work import PieceRate, ViecPhatSinh
from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.san_xuat_thuc_thi import SanXuatKhoangThamGia
from app.models.user import User
from app.services.attendance_service import VN_TZ
from app.services.san_xuat import san_luong

T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
NGAY = T0.date()


def viec_khoan_cua_to(
    db, to_id: int, *, ma: str | None = None, ten: str = "Việc khoán test", don_gia=100,
    unit: str = "cai", note: str | None = None,
) -> PieceRate:
    """Một việc khoán ĐANG DÙNG của tổ `to_id` (mã mặc định `VK-T<tổ>`, gọi lại thì dùng lại)."""
    ma = ma or f"VK-T{to_id}"
    r = db.query(PieceRate).filter_by(ma=ma).first()
    if r is None:
        r = PieceRate(ma=ma, ten=ten, unit=unit, unit_price=don_gia, note=note, active=True)
        db.add(r)
        db.flush()
        r.department_ids = [to_id]
        db.flush()
    return r


def viec_phat_sinh(db, rate: PieceRate, *, ten="Lên khuôn", don_gia=5000, don_vi="lan") -> ViecPhatSinh:
    ps = ViecPhatSinh(piece_rate_id=rate.id, ten=ten, don_gia=don_gia, don_vi=don_vi)
    db.add(ps)
    db.flush()
    return ps


def tao_me(db, *, user, cong_viec_id: int, **kw) -> dict:
    return san_luong.tao_batch(db, user=user, cong_viec_id=cong_viec_id, **kw)


def tao_user(db, username) -> User:
    u = User(username=username, name=username, password_hash="x")
    db.add(u)
    db.flush()
    return u


def utc(dt: datetime) -> datetime:
    """SQLite trả cột `DateTime(timezone=True)` về NAIVE — ép nhãn UTC để so thời điểm."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def khoang(db, cv, emp, bat_dau, ket_thuc) -> SanXuatKhoangThamGia:
    """Khoảng tham gia dựng thẳng — `nguoi_trong_me` giao nó với cửa sổ mẻ để biết ai có mặt."""
    k = SanXuatKhoangThamGia(
        cong_viec_id=cv.id, phien_chay_id=1, employee_id=emp.id,
        bat_dau=bat_dau, ket_thuc=ket_thuc,
    )
    db.add(k)
    db.flush()
    return k


def cham_cong(db, emp, *, ngay=NGAY, vao_h=8, ra_h=17) -> None:
    """Ca hành chính 08:00–17:00 (giờ VN) + một cặp chấm công VÀO/RA phủ trọn cửa sổ mẻ."""
    ca = db.query(WorkShift).filter_by(name="HC-PB").first()
    if ca is None:
        ca = WorkShift(name="HC-PB", start_minute=480, end_minute=1020, is_overnight=False)
        db.add(ca)
        db.flush()
    emp.default_shift_id = ca.id
    for h, ct in ((vao_h, CHECK_IN), (ra_h, CHECK_OUT)):
        loc = datetime(ngay.year, ngay.month, ngay.day, h, 0, tzinfo=VN_TZ)
        db.add(AttendanceLog(employee_id=emp.id, check_type=ct,
                             checked_at=loc.astimezone(timezone.utc)))
    db.flush()


def canh_me(db, orders, lsx_svc, admin, customer, *, tot=100.0, ma="TO-ME"):
    """Tổ khoán (vai admin đủ quyền trên dòng tổ) + công việc ĐANG CHẠY + một mẻ tốt `T0 → T0+1h`."""
    from tests.test_san_xuat_thuc_thi import _mot_cv

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "tờ"
    cv.don_vi_vao = "tờ"
    db.commit()
    r = tao_me(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=T0, ket_thuc=T0 + timedelta(hours=1), tong=tot, tot=tot,
    )
    batch = db.get(SanXuatBatch, r["batch_id"])
    return to, cv, batch
