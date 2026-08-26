"""Pydantic schemas — Danh mục "Công việc khoán" (bảng `piece_rates`).

Cùng hình dạng với 10 màn danh mục kia (In · Row · ListOut + `facets`), nên `make_catalog_router`
dùng được không cần vá gì.

⚠️ TÊN FIELD: `unit` · `unit_price` · `note` giữ nguyên tên cột đời cũ (không đổi sang
`don_vi`/`don_gia`/`ghi_chu`). Đợt 17/08/2026 chỉ đổi tên ĐÚNG BA cột mà nền danh mục đọc
(`ma` · `ten` · `active`); ba cột này không ai đọc theo tên nên đổi thêm chỉ để cho đẹp là mở rộng
một migration đang chạy trên bảng có dữ liệu sống. Nhãn tiếng Việt nằm ở màn.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CongViecKhoanIn(BaseModel):
    """Thân POST/PUT. `ma` bỏ trống ⇒ server cấp `KH-####` (màn không có ô Mã lúc tạo).

    `group_name` KHÔNG có ở đây: nó là nhãn tổ, service tự lấy theo `department_id` — để client
    gửi thì hai chỗ cùng khai một sự thật rồi lệch nhau (dòng nào cũng có tổ, nhưng nhãn của nó
    lại là tên tổ từ tháng trước).
    """

    ma: str | None = Field(default=None, max_length=20)
    ten: str = Field(min_length=1, max_length=255)
    department_id: int | None = None
    # Đơn vị lưu MÃ danh mục (`to`, `kg`, `m2`) — cùng lối với `giay.don_vi_gia`. KHÔNG enum cứng:
    # xưởng thêm đơn vị ở màn Đơn vị & quy đổi, không sửa code. Chữ ngoài danh mục vẫn lưu được
    # (dòng cũ, seed, import đang mang đơn vị ngoài danh mục — chặn ở đây là khoá luôn đường sửa).
    unit: str = Field(default="khác", max_length=24)
    unit_price: float = Field(ge=0)
    #: Cách đo LƯỢNG của việc này (ra số đơn vị `unit` rồi mới nhân đơn giá). Rỗng = để hệ tự quy
    #: đổi như cũ (cầu quy đổi, rồi công thức của đơn vị) — xem `LsxService._sl_theo_don_vi`.
    cong_thuc_luong: str | None = None
    note: str | None = Field(default=None, max_length=255)
    active: bool = True


class CongViecKhoanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str | None = None
    ten: str
    #: Nhãn tổ đã lưu trên dòng (tên tổ lúc khai, hoặc mã tổ đời cũ `to_boi`). Trục gom của bảng.
    group_name: str
    department_id: int | None = None
    unit: str
    unit_price: float
    cong_thuc_luong: str | None = None
    # "Lần trước công thức lượng" (mục 3+7) — router gán từ `cong_thuc_lich_su`, không có trong DB.
    cong_thuc_luong_truoc: str | None = None
    cong_thuc_luong_sua_luc: datetime | None = None
    note: str | None = None
    active: bool
    #: TÊN đọc được của đơn vị, server gán từ danh mục (`to` → "tờ"). Không có mã trong danh mục
    #: thì `None` — màn hiện nguyên mã kèm dấu hiệu, không im lặng bỏ trắng.
    don_vi_ten: str | None = None


class CongViecKhoanListOut(BaseModel):
    items: list[CongViecKhoanRow]
    total: int
    page: int
    size: int
    #: Số dòng theo TỪNG tổ — nuôi số trên tab lọc (màn chỉ cầm 20 dòng, không tự đếm được).
    facets: dict[str, int] = {}
