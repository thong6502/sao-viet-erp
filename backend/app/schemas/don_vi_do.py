"""Pydantic schemas — Danh mục Đơn vị đo + cặp quy đổi."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DonViDoIn(BaseModel):
    ma: str = Field(min_length=1, max_length=24)
    ten: str = Field(min_length=1, max_length=60)
    # LOẠI ĐO, gõ tự do (gợi ý ở `GET /api/don-vi/ho`). Không còn quyết định "đổi được hay không"
    # (việc đó theo cặp đã khai) — chỉ còn để gom nhóm khi hiển thị.
    ho: str = Field(default="khac", max_length=24)
    hieu_luc_tu: date | None = None
    ghi_chu: str | None = Field(default=None, max_length=500)
    active: bool = True


class DonViDoRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten: str
    ho: str
    hieu_luc_tu: date | None = None
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None
    # Cảnh báo mềm (chưa khai quy đổi với ai) — hiện ở màn khai, không chặn lưu.
    canh_bao: list[str] = Field(default_factory=list)
    # Câu quy đổi bằng CHỮ NGƯỜI ĐỌC: "1 tấn = 1.000 kg". Server dựng vì chỉ server thấy cả bảng cặp.
    quy_doi_text: str | None = None


class DonViDoListOut(BaseModel):
    items: list[DonViDoRow]
    total: int
    page: int
    size: int


class BienListOut(BaseModel):
    """Biến dùng được trong công thức quy đổi động: {ma, nhan}."""

    items: list[dict]


class HoListOut(BaseModel):
    """Gợi ý cho ô "Loại đo" — KHÔNG phải whitelist, gõ loại mới vẫn lưu được."""

    items: list[str]


# --- cặp quy đổi --------------------------------------------------------------


class CapIn(BaseModel):
    tu_id: int
    den_id: int
    # Số HOẶC công thức. Dòng công thức gửi he_so = 0 (service tự chuẩn hoá) — `gt=0` ở đây sẽ
    # chặn oan quy đổi động.
    he_so: float = Field(default=0, ge=0)
    cong_thuc: str | None = Field(default=None, max_length=200)
    ghi_chu: str | None = Field(default=None, max_length=500)


class CapRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tu_id: int
    den_id: int
    tu_ma: str
    den_ma: str
    tu_ten: str
    den_ten: str
    he_so: float
    cong_thuc: str | None = None
    ghi_chu: str | None = None
    # "1 tấn = 1.000 kg" — dựng sẵn để mọi màn hiện cùng một câu.
    cau: str | None = None
    # Màn danh mục dùng chung tìm kiếm/hiển thị theo `ma` + `ten`. Cặp không có mã người nhập nên
    # server tự dựng: mã = "tan → kg", tên = chính câu quy đổi.
    ma: str | None = None
    ten: str | None = None


class CapListOut(BaseModel):
    items: list[CapRowOut]
    total: int
    page: int
    size: int


class QuyDoiIn(BaseModel):
    """Thử một phép đổi (ô xem trước ở màn khai + kiểm tra tay)."""

    gia_tri: float = 0
    tu: str = Field(min_length=1, max_length=24)
    den: str = Field(min_length=1, max_length=24)
    # Quy cách lệnh khi đổi qua loại đo khác: kho_in_dai · kho_in_rong (mm) · gsm · so_con.
    quy_cach: dict | None = None


class QuyDoiOut(BaseModel):
    gia_tri: float | None = None
    don_vi: str | None = None
    dien_giai: str | None = None
    thieu: list[str] = Field(default_factory=list)
    ly_do: str | None = None
