"""MỘT chỗ hỏi chung: *"tháng này chốt công chưa?"* — trước khi ghi thứ ra tiền.

VÌ SAO TÁCH RA MODULE RIÊNG
---------------------------
Luật "kỳ công đã chốt thì không sửa số công nữa" trước đây nằm rải trong `AttendanceService`
(`_require_period_open`). Nó viết đúng, nhưng chỉ được gắn vào **4 đường**: chấm bù · xóa punch bù ·
sửa ca · gửi yêu cầu chỉnh công. Còn **duyệt đơn nghỉ · duyệt phiếu tăng ca · duyệt phiếu đi muộn**
thì không ai hỏi — mà đó mới là đường đi hằng ngày (thợ nộp giấy nghỉ ốm tuần sau, tổ trưởng duyệt bù).

Hậu quả đã đo được (12/08/2026): duyệt một đơn nghỉ CÓ LƯƠNG cho tháng đã chốt ⇒ Bảng công tháng
cộng thêm công (nó tính LIVE), còn Bảng lương giữ số cũ (nó đọc ẢNH CHỤP). Hai màn nói hai con số,
không chỗ nào báo, và người lao động là bên mất tiền.

Nên luật phải sống ở MỘT chỗ mà mọi phân hệ cùng gọi, thay vì chép lại ở từng service — chép lại
thì đúng ba tháng nữa thêm một đường ghi mới là lại sót.

CÁCH DÙNG
---------
Nhận REPO (không phải service) nên không sinh vòng service ↔ service — cùng quy ước với chỗ
`AttendanceService` nhận `PayrollRepository` để chặn chiều ngược lại::

    loi = ly_do_ky_cong_da_chot(self.attendance, don.start_date, don.end_date,
                                viec="duyệt đơn nghỉ")
    if loi:
        raise LeaveValidationError(loi)

Trả về CHUỖI thay vì tự ném lỗi: mỗi phân hệ có lớp lỗi riêng đã được router ánh xạ sẵn sang 422,
ném lỗi lạ ở đây là rơi ra 500.
"""

from __future__ import annotations

from datetime import date

from ..models.attendance import APERIOD_LOCKED


def ly_do_ky_cong_da_chot(attendance_repo, *nhung_ngay: date | None, viec: str) -> str | None:
    """None = ghi được. Chuỗi = lý do chặn, đã viết sẵn cho người dùng đọc.

    Nhận NHIỀU ngày vì đơn nghỉ bắc cầu hai tháng (28/8 → 03/9): chỉ cần MỘT đầu rơi vào tháng đã
    chốt là phải chặn — duyệt nó sẽ thêm công vào tháng đã đóng băng.
    """
    for ngay in nhung_ngay:
        if ngay is None:
            continue
        ky = attendance_repo.get_period_by_ym(ngay.year, ngay.month)
        if ky is not None and ky.status == APERIOD_LOCKED:
            return (
                f"Kỳ công {ngay.month}/{ngay.year} đã chốt — số công tháng đó đã đóng băng cho "
                f"bảng lương. Mở lại kỳ công trước khi {viec}."
            )
    return None
