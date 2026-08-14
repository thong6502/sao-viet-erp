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
    # Bày trong ô "Đơn vị tốc độ" của màn Máy hay không. Mặc định KHÔNG: bảng này dùng chung cho
    # kho/khoán/mua hàng, đơn vị mới thêm chưa chắc là tốc độ máy.
    dung_lam_toc_do: bool = False
    # Trạm trên DÒNG GIẤY (`to_nguyen · to · con · tay · cai`) — None = ngoài dòng giấy, đúng cho
    # gần hết danh mục. Đây là thứ duy nhất engine bù hao cần biết về một đơn vị.
    tram_dong_giay: str | None = Field(default=None, max_length=12)
    # CÁCH ĐO: công thức định nghĩa chính đơn vị này ("m² tờ in = dai_in × rong_in × to_sau_in").
    # Ra LƯỢNG, không phải tiền. Không nối với đơn vị nào — khác hẳn `CapIn.cong_thuc`.
    cong_thuc: str | None = Field(default=None, max_length=200)


class DonViDoRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten: str
    ho: str
    hieu_luc_tu: date | None = None
    ghi_chu: str | None = None
    active: bool
    dung_lam_toc_do: bool = False
    tram_dong_giay: str | None = None
    cong_thuc: str | None = None
    # Công thức HIỆU LỰC + đơn vị CHỦ. Khác `cong_thuc` khi đơn vị này MƯỢN của đơn vị khác trong
    # cụm tĩnh (khai ở `kg` thì `tấn`/`g` dùng chung). Màn hiện read-only — xoá phải về đúng chủ.
    cong_thuc_hieu_luc: str | None = None
    cong_thuc_chu_ma: str | None = None
    cong_thuc_chu_ten: str | None = None
    # Cách đo bằng CHỮ NGƯỜI ĐỌC ("Dài tờ in × Rộng tờ in × Tờ tốt sau in") — server dịch, để màn
    # danh sách khỏi phải nhúng bảng nhãn biến thứ hai.
    cong_thuc_text: str | None = None
    updated_at: datetime | None = None
    # Cảnh báo mềm (chưa khai quy đổi với ai) — hiện ở màn khai, không chặn lưu.
    canh_bao: list[str] = Field(default_factory=list)
    # Câu quy đổi bằng CHỮ NGƯỜI ĐỌC: "1 tấn = 1.000 kg". Server dựng vì chỉ server thấy cả bảng cặp.
    quy_doi_text: str | None = None
    # Cũng câu đó nhưng TÁCH SẴN từng mảnh kèm `loai` ("cong_thuc" / "co_dinh") — màn danh sách tô
    # màu theo `loai`. Bản trước nó tự tách `quy_doi_text` rồi đoán loại bằng tên biến ghi cứng,
    # trong khi biến đã được đổi sang nhãn tiếng Việt ⇒ công thức nào không có dấu × đều hiện xám.
    quy_doi_chips: list[dict] = Field(default_factory=list)


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
    # CHỈ số cố định. Quy đổi động (`1 tờ = f(chip) kg`) đã gỡ 14/08/2026 — cách đo nay khai ở
    # chính đơn vị (`DonViDoIn.cong_thuc`) và trả LƯỢNG, không phải tỉ lệ giữa hai đơn vị.
    # Vẫn để `ge=0` (không `gt`) vì service mới là nơi báo lỗi có chữ, đẹp hơn 422 trống.
    he_so: float = Field(default=0, ge=0)
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
