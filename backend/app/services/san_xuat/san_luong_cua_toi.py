"""CÁC MẺ TÔI THAM GIA trong tháng — màn của thợ (spec 18/09/2026 §7.5).

Trước bản này mục tên là "Sản lượng của tôi" và đọc DÒNG CHIA ĐÃ CHỐT của engine phân bổ. Engine
đó gỡ hẳn 18/09/2026 (mg `0322`) theo chốt của chủ xưởng — *"ghi nhận thế thôi, đừng có chia bất
cứ gì"* — nên nguồn cũ hết tồn tại.

Đổi nghĩa chứ không gỡ màn: thợ vẫn cần xem lại mình đã làm gì để đối chiếu với kế toán. Mỗi dòng
là MỘT MẺ mà chính người gọi có mặt, mang sản lượng của **cả mẻ** kèm **danh sách người tham gia**.
KHÔNG có dòng "phần của tôi", KHÔNG có số phút của ai, không có tiền — hệ không bịa ra con số mà
không ai quyết (chốt ý 13).

`employee_id` LUÔN suy từ token, KHÔNG nhận từ client — nếu nhận thì đây là cửa xem sản lượng của
bất kỳ ai chỉ bằng cách đổi một số trên URL.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models.san_xuat import SanXuatCongViec
from ...models.san_xuat_phan_bo import HT_XAC_NHAN, SanXuatHoTro
from ...models.san_xuat_san_luong import SanXuatBatch
from ...models.san_xuat_thuc_thi import SanXuatKhoangThamGia
from ...models.user import User
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ..gio_xuong import thuc_te_hien_thi
from .nguoi_trong_me import nguoi_theo_me


def _khoang_thang(nam: int, thang: int) -> tuple[date, date]:
    """`[đầu tháng, đầu tháng sau)` — nửa mở, để không phải biết tháng có 28/30/31 ngày."""
    dau = date(nam, thang, 1)
    return dau, (date(nam + 1, 1, 1) if thang == 12 else date(nam, thang + 1, 1))


def _rong(ngay: date) -> datetime:
    return datetime.combine(ngay, time.min, tzinfo=timezone.utc)


def san_luong_cua_toi(db: Session, user: User, *, nam: int, thang: int) -> dict:
    """Các mẻ trong tháng mà chính `user` có mặt — khoảng tham gia giao với cửa sổ mẻ, hoặc hỗ trợ
    chéo đã xác nhận đúng công việc + ngày của mẻ (cùng luật `nguoi_trong_me`).

    Cửa sổ mẻ là UTC THẬT (mg `0298`) nên lọc tháng cũng bằng mốc UTC — đừng trộn giờ tường vào,
    mẻ đầu/cuối tháng sẽ nhảy sang tháng bên cạnh.
    """
    nv = SanXuatThucThiRepository(db).nhan_vien_theo_user(user.id)
    if nv is None:
        # Tài khoản chưa nối hồ sơ nhân sự ⇒ không có mẻ nào, KHÔNG rơi về "của cả tổ".
        return {"nam": nam, "thang": thang, "employee_id": None, "me": [], "so_me": 0}
    dau, ke = _khoang_thang(nam, thang)

    # Lấy mẻ theo CỬA SỔ THÁNG rồi mới suy ai có mặt — cùng một luật giao khoảng với tab Sản
    # lượng của tổ (`nguoi_theo_me`), không có đường thứ hai để hai màn lệch nhau. Chỉ quét mẻ của
    # các công việc người này TỪNG có khoảng tham gia HOẶC được xác nhận sang giúp (hỗ trợ chéo —
    # người tổ khác không có khoảng tham gia, xem `nguoi_trong_me`): không lọc thì mỗi lần mở màn
    # kéo mẻ cả xưởng trong tháng (hàng nghìn dòng) chỉ để bỏ gần hết.
    viec_cua_toi = (
        select(SanXuatKhoangThamGia.cong_viec_id)
        .where(SanXuatKhoangThamGia.employee_id == nv.id)
        .distinct()
    )
    viec_giup = (
        select(SanXuatHoTro.cong_viec_id)
        .where(SanXuatHoTro.employee_id == nv.id, SanXuatHoTro.trang_thai == HT_XAC_NHAN)
        .distinct()
    )
    batches = list(db.scalars(
        select(SanXuatBatch)
        .where(SanXuatBatch.bat_dau >= _rong(dau), SanXuatBatch.bat_dau < _rong(ke),
               or_(SanXuatBatch.cong_viec_id.in_(viec_cua_toi),
                   SanXuatBatch.cong_viec_id.in_(viec_giup)))
        .order_by(SanXuatBatch.bat_dau.desc(), SanXuatBatch.id.desc())
    ))
    if not batches:
        return {"nam": nam, "thang": thang, "employee_id": nv.id, "me": [], "so_me": 0}
    theo_me = nguoi_theo_me(db, [b.id for b in batches])
    cua_toi = [b for b in batches if any(n["employee_id"] == nv.id for n in theo_me.get(b.id, []))]
    if not cua_toi:
        return {"nam": nam, "thang": thang, "employee_id": nv.id, "me": [], "so_me": 0}

    repo = SanXuatRepository(db)
    cv_map = {
        cv.id: cv for cv in db.scalars(
            select(SanXuatCongViec).where(
                SanXuatCongViec.id.in_({b.cong_viec_id for b in cua_toi})
            )
        )
    }
    lsx_map = repo.lsx_nhan({cv.lsx_id for cv in cv_map.values() if cv.lsx_id})
    to_ten = repo.to_ten_nhan({n["department_id"] for ds in theo_me.values() for n in ds
                               if n["department_id"]})

    # "Tổ đang xem" của màn thợ là TỔ CỦA CHÍNH THỢ (§7.3b luật 2): ai khác tổ mình thì kèm nhãn tổ
    # gốc — thợ sang giúp tổ bế thấy "tôi · a (Tổ bế) · b (Tổ bế)", không phải nhãn dán lên mình.
    to_toi = nv.department_id

    def _nguoi(b: SanXuatBatch) -> list[dict]:
        return [
            {
                "employee_id": n["employee_id"],
                "ho_ten": "tôi" if n["employee_id"] == nv.id else n["ho_ten"],
                "to_ten": (to_ten.get(n["department_id"])
                           if n["department_id"] and n["department_id"] != to_toi else None),
            }
            for n in theo_me.get(b.id, [])
        ]

    ds = []
    for b in cua_toi:
        cv = cv_map.get(b.cong_viec_id)
        lsx = lsx_map.get(cv.lsx_id) if cv and cv.lsx_id else None
        ds.append({
            "batch_id": b.id,
            "bat_dau": thuc_te_hien_thi(b.bat_dau),
            "ket_thuc": thuc_te_hien_thi(b.ket_thuc),
            "lsx_ma": lsx[0] if lsx else None,
            "ten_cong_doan": cv.ten_cong_doan if cv else "",
            # Mẻ ghi trước 18/09/2026 không có việc khoán để chụp ⇒ None, FE hiện
            # "— chưa khai việc khoán". KHÔNG đoán, không tự gán.
            "viec_khoan_ten": b.ten_khoan_snapshot,
            "tot": float(b.tot),
            "hong": float(b.hong),
            "don_vi": b.don_vi,
            "nguoi_tham_gia": _nguoi(b),
        })
    return {"nam": nam, "thang": thang, "employee_id": nv.id, "me": ds, "so_me": len(ds)}
