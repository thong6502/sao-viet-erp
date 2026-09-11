"""Luỹ kế SẢN LƯỢNG THÁNG của chính người đang đăng nhập (spec 2026-09-11 §6, mục 3).

Thợ cần một con số trả lời được câu *"tháng này tôi làm được bao nhiêu"* mà không phải chờ bảng
lương. Không có tiền ở đây — sản xuất ghi số lượng, quy ra tiền là việc của kế toán lương.

Chỉ đọc dòng chia ĐÃ CHỐT: bản nháp còn đổi theo chấm công và còn bị tính lại, đưa nó vào luỹ kế
là mỗi lần mở màn ra một số khác.

`employee_id` LUÔN suy từ token, KHÔNG nhận từ client — nếu nhận thì đây là cửa xem sản lượng của
bất kỳ ai chỉ bằng cách đổi một số trên URL.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models.san_xuat_phan_bo import PB_DA_CHOT, SanXuatPhanBo, SanXuatPhanBoDong
from ...models.user import User
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository


def _khoang_thang(nam: int, thang: int) -> tuple[date, date]:
    """`[đầu tháng, đầu tháng sau)` — nửa mở, để không phải biết tháng có 28/30/31 ngày."""
    dau = date(nam, thang, 1)
    return dau, (date(nam + 1, 1, 1) if thang == 12 else date(nam, thang + 1, 1))


def san_luong_cua_toi(db: Session, user: User, *, nam: int, thang: int) -> dict:
    """Tổng sản lượng đã chốt của chính `user` trong tháng, gộp theo ĐƠN VỊ.

    Gộp theo đơn vị chứ không cộng thành một số: một tháng thợ có thể vừa chạy bước đếm bằng tờ
    vừa chạy bước đếm bằng cái — cộng chung hai thứ đó ra một con số vô nghĩa.
    """
    nv = SanXuatThucThiRepository(db).nhan_vien_theo_user(user.id)
    if nv is None:
        # Tài khoản chưa nối hồ sơ nhân sự ⇒ không có sản lượng nào, KHÔNG rơi về "của cả tổ".
        return {"nam": nam, "thang": thang, "employee_id": None, "theo_don_vi": [], "so_me": 0}
    dau, ke = _khoang_thang(nam, thang)
    rows = db.execute(
        select(SanXuatPhanBo.don_vi_tra_luong,
               func.sum(SanXuatPhanBoDong.so_luong_tra_luong),
               func.count(SanXuatPhanBoDong.id))
        .join(SanXuatPhanBo, SanXuatPhanBoDong.phan_bo_id == SanXuatPhanBo.id)
        .where(
            SanXuatPhanBoDong.employee_id == nv.id,
            SanXuatPhanBo.trang_thai == PB_DA_CHOT,
            SanXuatPhanBoDong.ngay >= dau,
            SanXuatPhanBoDong.ngay < ke,
        )
        .group_by(SanXuatPhanBo.don_vi_tra_luong)
    ).all()
    return {
        "nam": nam, "thang": thang, "employee_id": nv.id,
        "theo_don_vi": [{"don_vi": dv, "tong": float(t or 0)} for dv, t, _ in rows],
        "so_me": int(sum(n for _, _, n in rows)),
    }
