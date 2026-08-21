"""Pydantic schemas — Kỹ thuật máy (phiếu sửa chữa · phiếu bảo trì · ảnh).

⚠️ Thêm field mới phải đi HẾT chuỗi model → ASSIGNABLE (repo) → schema In/Row → type TS. Thiếu một
mắt là Pydantic nuốt IM LẶNG và FE nhận `undefined` (bẫy đã dính nhiều lần ở repo này).

Cột dẫn xuất (`qua_han`, `da_doi`, `so_anh`, `may_ma`…) chỉ có ở Row, KHÔNG có ở In: chúng được
tính lúc đọc, client gửi lên là bỏ qua.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ================= Phiếu sửa chữa =================


class SuaChuaIn(BaseModel):
    may_id: int
    bo_phan_hong: str = Field(min_length=1, max_length=150)
    mo_ta: str | None = None
    muc_do: str | None = None                # nhe | trung_binh | nghiem_trong
    # Người BÁO hỏng — ô chọn nhân viên, KHÔNG mặc định bằng người đăng nhập (thợ đứng máy báo
    # miệng, tổ kỹ thuật nhập hộ).
    nguoi_bao_id: int | None = None
    nguoi_bao_ten: str | None = None
    thoi_diem: datetime | None = None
    nguyen_nhan_phuong_an: str | None = None
    ghi_chu: str | None = None


class SuaChuaPatch(BaseModel):
    """Sửa từng phần — mọi field optional, router lọc bằng `exclude_unset`."""

    may_id: int | None = None
    bo_phan_hong: str | None = Field(default=None, max_length=150)
    mo_ta: str | None = None
    muc_do: str | None = None
    nguoi_bao_id: int | None = None
    nguoi_bao_ten: str | None = None
    thoi_diem: datetime | None = None
    nguyen_nhan_phuong_an: str | None = None
    ghi_chu: str | None = None


class SuaChuaRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    may_id: int
    bo_phan_hong: str
    mo_ta: str | None = None
    muc_do: str
    nguoi_bao_id: int | None = None
    nguoi_bao_ten: str | None = None
    thoi_diem: datetime | None = None
    nguyen_nhan_phuong_an: str | None = None
    trang_thai: str
    hoan_thanh_at: datetime | None = None
    ghi_chu: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # --- dẫn xuất, service/router bơm vào ---
    may_ma: str | None = None
    may_ten: str | None = None
    so_anh: int = 0
    co_anh_sau: bool = False     # đủ điều kiện đóng phiếu chưa — FE khoá nút theo cờ này
    # Phiếu này sinh ra từ yêu cầu của ai (nếu có). Đọc ngược từ `ky_thuat_yeu_cau_sua.phieu_id`,
    # không phải cột trên bảng phiếu.
    yeu_cau_id: int | None = None
    yeu_cau_ma: str | None = None
    yeu_cau_nguoi_bao: str | None = None
    yeu_cau_bo_phan: str | None = None


class SuaChuaListOut(BaseModel):
    items: list[SuaChuaRow]
    total: int
    page: int
    size: int
    # {trang_thai: số phiếu} cho dãy tab. Đếm ở DB trên TOÀN BỘ bảng, không phải đếm trang hiện tại.
    dem: dict[str, int] = {}


# ================= Yêu cầu sửa chữa (bộ phận khác báo hỏng) =================


class YeuCauIn(BaseModel):
    """Người ngoài tổ kỹ thuật báo máy hỏng. Ít ô nhất có thể — người gõ đang đứng cạnh cái máy
    hỏng, không phải ngồi bàn giấy."""

    may_id: int
    bo_phan_hong: str = Field(min_length=1, max_length=150)
    mo_ta: str | None = None
    muc_do: str | None = None                # mức người báo TỰ THẤY; tổ sửa chữa đặt lại lúc tạo phiếu
    may_dung: bool = False                   # máy đang dừng hẳn — cái quyết định thứ tự ưu tiên
    # KHÔNG có `nguoi_bao_id`: server lấy từ tài khoản đăng nhập. Cho client gửi lên là mở cửa hậu
    # báo hỏng dưới tên người khác.


class YeuCauPatch(BaseModel):
    may_id: int | None = None
    bo_phan_hong: str | None = Field(default=None, max_length=150)
    mo_ta: str | None = None
    muc_do: str | None = None
    may_dung: bool | None = None


class YeuCauRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    may_id: int
    bo_phan_hong: str
    mo_ta: str | None = None
    muc_do: str
    may_dung: bool = False
    nguoi_bao_id: int | None = None
    nguoi_bao_ten: str | None = None
    bo_phan: str | None = None
    thoi_diem: datetime | None = None
    trang_thai: str                          # cho_tiep_nhan | da_tao_phieu | tu_choi
    phieu_id: int | None = None
    ly_do_tu_choi: str | None = None
    xu_ly_ten: str | None = None
    xu_ly_at: datetime | None = None
    created_at: datetime | None = None

    # --- dẫn xuất ---
    may_ma: str | None = None
    may_ten: str | None = None
    so_anh: int = 0
    phieu_ma: str | None = None              # mã phiếu SC đã sinh — để người báo bấm theo dõi tiếp
    phieu_trang_thai: str | None = None


class YeuCauListOut(BaseModel):
    items: list[YeuCauRow]
    total: int
    page: int
    size: int
    dem: dict[str, int] = {}


class TaoPhieuTuYeuCauIn(BaseModel):
    """Tổ sửa chữa chỉnh lại lúc TIẾP NHẬN. Bỏ trống hết = bê nguyên lời người báo.

    Có ô để sửa vì lời người báo là mô tả triệu chứng ("in ra bị sọc"), còn phiếu cần ghi bộ phận
    hỏng theo cách tổ sửa chữa tra cứu được ("cụm lô mực đơn vị 3").
    """

    bo_phan_hong: str | None = Field(default=None, max_length=150)
    mo_ta: str | None = None
    muc_do: str | None = None
    nguyen_nhan_phuong_an: str | None = None
    ghi_chu: str | None = None


class TaoPhieuTuYeuCauOut(BaseModel):
    phieu: SuaChuaRow
    yeu_cau: YeuCauRow


class TuChoiYeuCauIn(BaseModel):
    # Bắt buộc, cùng lý do với hủy phiếu bảo trì: người báo phải đọc được vì sao, không thì lần sau
    # họ thôi không báo nữa.
    ly_do: str = Field(min_length=1, max_length=300)


class ChoTiepNhanOut(BaseModel):
    """Badge cạnh mục "Sửa chữa máy": số yêu cầu chưa ai tiếp nhận."""

    total: int


class MayChonRow(BaseModel):
    """Ô chọn máy cho người KHÔNG có quyền danh mục thiết bị — đúng bốn cột."""

    id: int
    ma: str
    ten: str | None = None
    loai_may: str | None = None


class MayChonOut(BaseModel):
    items: list[MayChonRow]


# ================= Phiếu bảo trì =================


class HangMucRow(BaseModel):
    id: str | None = None
    ten: str
    xong: bool = False
    # "Không áp dụng lần này" + lý do — nằm trong chính cột JSON `hang_muc`, không đẻ cột mới.
    bo_qua: bool = False
    ly_do_bo_qua: str | None = None


class BaoTriIn(BaseModel):
    may_id: int
    goi_id: str | None = None            # neo `lich_bao_tri[].id`; trống = đột xuất
    goi_ten: str | None = None
    chu_ky_so: float | None = None
    chu_ky_don_vi: str | None = None
    loai: str | None = None              # dinh_ky | dot_xuat
    ngay_ke_hoach: date | None = None
    hang_muc: list[HangMucRow] | None = None
    ghi_chu: str | None = None


class BaoTriPatch(BaseModel):
    # KHÔNG có `nguoi_thuc_hien`: người nhận việc gán từ tài khoản bấm "Đang thực hiện", không gõ tay.
    goi_ten: str | None = None
    chu_ky_so: float | None = None
    chu_ky_don_vi: str | None = None
    hang_muc: list[HangMucRow] | None = None
    ghi_chu: str | None = None


class BaoTriRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    may_id: int
    goi_id: str | None = None
    goi_ten: str | None = None
    chu_ky_so: float | None = None
    chu_ky_don_vi: str | None = None
    loai: str
    ngay_ke_hoach: date
    ngay_ke_hoach_goc: date | None = None
    ly_do_doi: str | None = None
    ly_do_huy: str | None = None       # lý do khi phiếu ở trạng thái da_huy
    hang_muc: list[HangMucRow] | None = None
    nguoi_thuc_hien_id: int | None = None
    nguoi_thuc_hien: str | None = None      # tên snapshot lúc nhận việc
    trang_thai: str
    ngay_hoan_thanh: date | None = None
    ghi_chu: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # --- dẫn xuất ---
    may_ma: str | None = None
    may_ten: str | None = None
    may_loai: str | None = None  # nhóm máy trong danh mục — màn Lịch lọc theo cái này
    so_anh: int = 0
    co_anh_sau: bool = False
    qua_han: bool = False        # ngày kế hoạch đã qua mà chưa hoàn thành
    da_doi: bool = False         # ngay_ke_hoach_goc khác ngay_ke_hoach


class BaoTriListOut(BaseModel):
    items: list[BaoTriRow]
    total: int
    page: int
    size: int
    # {trang_thai: số} + 3 số dẫn xuất theo ngày (`qua_han`, `den_hom_nay`, `tuan_nay`), đếm ở DB
    # theo ĐÚNG bộ lọc đang xem (trừ trạng thái) — không phải đếm trang hiện tại, cũng không phải
    # đếm cả bảng.
    dem: dict[str, int] = {}


class HuyPhieuIn(BaseModel):
    # Bắt buộc: kỳ bảo trì bị bỏ mà không kèm chữ nào thì tháng sau không ai giải thích được vì sao
    # máy chưa được bảo trì. Lý do vừa lưu trên phiếu (`ly_do_huy`) vừa vào nhật ký.
    ly_do: str = Field(min_length=1, max_length=300)


class DoiTrangThaiIn(BaseModel):
    trang_thai: str
    # Chỉ dùng khi chuyển sang `hoan_thanh`: ngày làm THẬT (thợ làm thứ Bảy, thứ Hai mới vào bấm).
    # Đây là mốc tính kỳ sau nên không lấy giờ bấm nút.
    ngay_hoan_thanh: date | None = None


class TickHangMucIn(BaseModel):
    hang_muc_id: str
    xong: bool
    # `bo_qua=True` ⇒ đánh "không áp dụng lần này", BẮT BUỘC kèm `ly_do` (service chặn nếu trống).
    bo_qua: bool | None = None
    ly_do: str | None = Field(default=None, max_length=200)




# ================= Lịch (calendar) =================


class DuKienRow(BaseModel):
    """Kỳ bảo trì TƯƠNG LAI chưa có phiếu — vẽ mờ trên lịch, bấm vào là tạo phiếu thật.

    Không lưu ở bảng nào: tính lúc đọc từ chu kỳ gói trong `lich_bao_tri` của máy.
    """

    may_id: int
    may_ma: str
    may_ten: str | None = None
    may_loai: str | None = None
    goi_id: str | None = None
    goi_ten: str | None = None
    ngay: date
    chu_ky_so: float | None = None
    chu_ky_don_vi: str | None = None


class LichOut(BaseModel):
    phieu: list[BaoTriRow]
    du_kien: list[DuKienRow]


class DenHanOut(BaseModel):
    """Badge cạnh mục "Phiếu bảo trì": số phiếu tới hạn/quá hạn còn dở."""

    total: int
    qua_han: int


class HanGoiRow(BaseModel):
    goi_id: str | None = None
    goi_ten: str | None = None
    han: date | None = None
    # phieu | ngay_bat_dau | thieu_chu_ky | thieu_ngay_bat_dau — nói rõ hạn này tính từ đâu, hoặc
    # vì sao KHÔNG tính được (hai lý do là hai ô khác nhau trên form Máy).
    nguon: str
    phieu_dang_mo_id: int | None = None


class HanMayOut(BaseModel):
    items: list[HanGoiRow]


# ================= Ảnh =================


class AnhRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    loai_phieu: str
    phieu_id: int
    giai_doan: str
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_at: datetime | None = None


class AnhListOut(BaseModel):
    items: list[AnhRow]
