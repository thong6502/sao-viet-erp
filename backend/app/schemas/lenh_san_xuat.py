"""Schema ra của màn "Lệnh sản xuất" (Task 9).

BẪY PYDANTIC CỦA REPO — đọc trước khi thêm trường: service ở đây trả `dict`, router khai
`response_model`, nên field KHÔNG có mặt trong schema bị NUỐT IM LẶNG — không lỗi, không cảnh báo,
frontend nhận `undefined`. Thêm một trường là phải đi HẾT chuỗi: `danh_sach._dong()` → schema này →
type TS bên `frontend/src/api/client.ts`. Thiếu một mắt là mất trường mà test backend vẫn xanh.

KHÔNG MỘT SỐ TIỀN NÀO. Ràng buộc toàn cục của plan: không `don_gia` / `gia_von` / `thanh_tien` /
`luong_khoan` / `chi_phi`. Màn này cho điều độ và tổ trưởng xem — họ cần biết lệnh đang ở đâu và
có kịp không, không cần biết nó lãi bao nhiêu. Ràng buộc ấy được canh bằng
`test_khong_lo_tien`; nó chỉ có nghĩa khi schema này KHÔNG mở cửa cho các trường đó.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class LenhSxItem(BaseModel):
    """MỘT dòng bảng lệnh. Các cột đã chốt: Mã · Sản phẩm/SL · Khách · Máy · Công đoạn + tiến độ ·
    Hạn/Dự kiến · Trạng thái."""

    id: int
    ma: str
    ten: str | None = None
    khach_hang: str | None = None
    khach_hang_id: int | None = None
    sale: str | None = None

    so_luong_dat: int
    don_vi_tinh: str | None = None
    # Số đã giao THẬT (`delivery_lines.qty_delivered`), không phải số yêu cầu giao — xem
    # `BoiCanh.da_giao_cua`.
    da_giao: int = 0

    is_rush: bool = False
    buoc_hien_tai: str | None = None
    nhom_cong_doan: str | None = None
    may: str | None = None
    # Nửa "người" của cột Máy/người: TÊN những người đang được giao ở ĐÚNG bước đang hiện ở cột
    # "Máy". Danh sách chứ không phải chuỗi "A +2" dựng sẵn — nhiều người trên một bước là chuyện
    # thường (roster), cột hẹp thì UI tự cắt "+N", còn tooltip vẫn có đủ tên mà không phải gọi thêm
    # API. Thứ tự là THỨ TỰ GIAO nên cắt từ cuối là an toàn. Rỗng = bước chưa giao ai (đừng bịa).
    # Người đã bị RÚT (`trang_thai='removed'`) không có mặt ở đây — xem `BoiCanh.nguoi_cua`.
    nguoi: list[str] = []

    tien_do_pct: float
    # `True` = phần trăm đang đo bằng THỜI LƯỢNG kế hoạch vì bước chưa khai sản lượng. Bắt buộc
    # phải ra tới UI: 40% "đo được" và 40% "ước tính" là hai mức tin cậy khác hẳn nhau, gộp làm một
    # là mời điều độ ra quyết định trên con số họ tưởng chắc hơn thực tế.
    tien_do_uoc_tinh: bool = False
    gio_may: float = 0.0

    han_hoan_thanh_sx: date | None = None
    han_giao_khach: date | None = None
    du_kien_xong: datetime | None = None

    trang_thai: str
    canh_bao: list[str] = []


class LenhSxListOut(BaseModel):
    """`dem_theo_tab` là FACET của tập đã lọc (đếm TRÊN TOÀN TẬP, không phải trên trang đang xem) và
    KHÔNG bị chính `tab` đang chọn lọc lại — nếu không, bấm một tab là mọi tab khác về 0."""

    items: list[LenhSxItem]
    total: int
    page: int
    page_size: int
    dem_theo_tab: dict[str, int]


class LenhSxSummaryOut(BaseModel):
    """Bốn thẻ KPI. "Hôm nay" = ngày GIỜ XƯỞNG (+7), không phải ngày UTC — xưởng chạy ca đêm."""

    dang_sx: int
    cong_doan_xong_hom_nay: int
    du_kien_tre: int
    # `None` = CHƯA kiểm cái nào hôm nay, khác hẳn `0.0` = kiểm rồi và trượt sạch. UI phải hiện
    # "—" cho `None`; đổ 0 vào đó là báo động giả mỗi sáng sớm.
    ty_le_kcs_dat_hom_nay: float | None = None
