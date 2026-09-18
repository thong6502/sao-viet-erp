"""Pydantic schemas — Danh mục "Công việc khoán" (bảng `piece_rates`).

Cùng hình dạng với 10 màn danh mục kia (In · Row · ListOut + `facets`), nên `make_catalog_router`
dùng được không cần vá gì.

⚠️ TÊN FIELD: `unit` · `unit_price` · `note` giữ nguyên tên cột đời cũ (không đổi sang
`don_vi`/`don_gia`/`ghi_chu`). Đợt 17/08/2026 chỉ đổi tên ĐÚNG BA cột mà nền danh mục đọc
(`ma` · `ten` · `active`); ba cột này không ai đọc theo tên nên đổi thêm chỉ để cho đẹp là mở rộng
một migration đang chạy trên bảng có dữ liệu sống. Nhãn tiếng Việt nằm ở màn.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ViecPhatSinhIn(BaseModel):
    """Một việc phát sinh trong thân POST/PUT — ba ô người khai + `id` của dòng đang sửa.

    Kiểu nới (`ten` rỗng được, `don_gia`/`don_vi` bỏ trống được) là CỐ Ý: luật khai nằm ở
    `CongViecKhoanService._validate`, câu lỗi tiếng Việt gọi đúng tên việc. Để Pydantic chặn thì
    người khai nhận "Field required" kèm đường dẫn `viec_phat_sinh.1.don_gia`, không biết dòng nào.
    """

    #: Id dòng đang có (form nạp từ Row gửi ngược lên). Bỏ trống = dòng mới.
    id: int | None = None
    ten: str = Field(default="", max_length=255)
    don_gia: float | None = None
    #: MÃ đơn vị trong danh mục Đơn vị & quy đổi (`kem`, `luot`).
    don_vi: str | None = Field(default=None, max_length=24)


class ViecPhatSinhRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ten: str
    don_gia: float
    don_vi: str


class ToLamRow(BaseModel):
    """Một tổ làm công việc khoán — id kèm mã/tên đọc được, server tra lúc dựng dòng."""

    id: int
    ma: str | None = None
    #: Tên tổ ĐANG dùng. Tổ đã bị xoá khỏi cây tổ chức thì `None` — màn hiện dấu hiệu để người
    #: khai tự gỡ, không im lặng bỏ tổ đó khỏi danh sách.
    ten: str | None = None


class CongViecKhoanIn(BaseModel):
    """Thân POST/PUT. `ma` bỏ trống ⇒ server cấp `KH-####` (màn không có ô Mã lúc tạo).

    `department_ids` — CÁC tổ làm việc này (17/09/2026; trước là MỘT `department_id`). VẮNG = giữ
    nguyên danh sách đang có (nhập Excel thiếu cột, client chỉ sửa đơn giá); có mặt = TRỌN danh
    sách. Tạo mới phải có ít nhất một tổ — luật nằm ở service để câu lỗi là tiếng Việt.
    """

    ma: str | None = Field(default=None, max_length=20)
    ten: str = Field(min_length=1, max_length=255)
    department_ids: list[int] | None = None
    # Đơn vị lưu MÃ danh mục (`to`, `kg`, `m2`) — cùng lối với `giay.don_vi_gia`. KHÔNG enum cứng:
    # xưởng thêm đơn vị ở màn Đơn vị & quy đổi, không sửa code. Chữ ngoài danh mục vẫn lưu được
    # (dòng cũ, seed, import đang mang đơn vị ngoài danh mục — chặn ở đây là khoá luôn đường sửa).
    unit: str = Field(default="khác", max_length=24)
    unit_price: float = Field(ge=0)
    #: CÁCH ĐO LƯỢNG KHOÁN — tab "Công thức khoán" (18/09/2026, mg `0317`). Ra LƯỢNG theo `unit`;
    #: kế toán nhân `unit_price` sau. Bàn tổ KHÔNG chạy công thức này — sản xuất chỉ ghi số lượng.
    cong_thuc_khoan: str | None = None
    note: str | None = Field(default=None, max_length=255)
    active: bool = True
    #: VIỆC PHÁT SINH (14/09/2026). VẮNG = giữ nguyên danh sách đang có (nhập Excel không mang
    #: khoá này); `[]` = xoá hết. Xem `CongViecKhoanRepository._sau_gan`.
    viec_phat_sinh: list[ViecPhatSinhIn] | None = None


class CongViecKhoanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str | None = None
    ten: str
    #: Id các tổ làm việc này — form nạp ngược vào ô chọn tổ.
    department_ids: list[int] = []
    #: Cùng thứ tự với `department_ids`, kèm tên — cột "Tổ" của bảng và panel lương đọc từ đây.
    tos: list[ToLamRow] = []
    unit: str
    unit_price: float
    cong_thuc_khoan: str | None = None
    note: str | None = None
    active: bool
    #: TÊN đọc được của đơn vị, server gán từ danh mục (`to` → "tờ"). Không có mã trong danh mục
    #: thì `None` — màn hiện nguyên mã kèm dấu hiệu, không im lặng bỏ trắng.
    don_vi_ten: str | None = None
    #: Theo thứ tự đã khai. Luôn có mặt (kể cả `[]`) — màn vẽ cột "Việc phát sinh" từ đây.
    viec_phat_sinh: list[ViecPhatSinhRow] = []


class CongViecKhoanListOut(BaseModel):
    items: list[CongViecKhoanRow]
    total: int
    page: int
    size: int
    #: Số dòng theo TỪNG tổ — nuôi số trên tab lọc (màn chỉ cầm 20 dòng, không tự đếm được).
    facets: dict[str, int] = {}
    #: Tổng dòng khớp ô tìm, KHÔNG theo tab — số của tab "Tất cả". Cần riêng vì một việc làm ở hai
    #: tổ được đếm ở CẢ HAI tab: cộng `facets` lại là đếm trùng.
    tong_theo_tim: int | None = None
