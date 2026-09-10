"""Schema Xếp lịch 3 (cấp LỆNH SẢN XUẤT).

CẢNH BÁO đã dính một lần ở chỗ khác: `response_model` của Pydantic BỎ IM LẶNG mọi khoá service
trả về mà schema không khai — không lỗi, không log, FE chỉ nhận `undefined`. Thêm số nào thì phải
đi hết dây: dict của service → schema ở đây → type TS ở `api/xepLich3.ts`.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DoanChayOut(BaseModel):
    """Một đoạn máy chạy liền mạch — lớp đậm bên trong thanh Gantt."""

    tu: datetime
    den: datetime
    buoc_index: int


class _LichChung(BaseModel):
    """Phần LỊCH dùng chung giữa dòng Gantt và panel chi tiết."""

    bat_dau_at: datetime | None = None
    ket_thuc: datetime | None = None
    chay_phut: float = 0.0
    # Khoảng hở giữa các đoạn chạy: nghỉ giữa ca + ngoài ca + ngày nghỉ. Trả lời đúng câu người
    # dùng hỏi khi nhìn thanh: "vì sao nó dài hơn giờ chạy?".
    nghi_ngoai_ca_phut: float = 0.0
    doan: list[DoanChayOut] = Field(default_factory=list)
    ghi_chu: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class DongLichOut(_LichChung):
    """Một dòng trên bàn Gantt = MỘT lệnh sản xuất."""

    model_config = ConfigDict(from_attributes=True)

    lsx_id: int
    ma: str
    ten: str
    customer_name: str | None = None
    trang_thai: str
    is_rush: bool = False
    so_luong_dat: int = 0
    don_vi_tinh: str | None = None
    so_to_ke_hoach: int = 0
    so_con: int = 1
    han_hoan_thanh_sx: date | None = None
    han_giao_khach: date | None = None
    may_ten: str | None = None
    # Chỉ có ở phản hồi của PUT — cho băng thông báo biết mốc vừa bị dời.
    da_doi: bool | None = None
    thong_bao: str | None = None


class LichOut(BaseModel):
    dong: list[DongLichOut] = Field(default_factory=list)
    tong: int = 0


class TheHangChoOut(BaseModel):
    lsx_id: int
    ma: str
    ten: str
    customer_name: str | None = None
    han_hoan_thanh_sx: date | None = None
    han_giao_khach: date | None = None
    is_rush: bool = False
    so_to_ke_hoach: int = 0
    so_luong_dat: int = 0
    don_vi_tinh: str | None = None
    chay_phut: float = 0.0
    so_buoc: int = 0


class HangChoOut(BaseModel):
    dong: list[TheHangChoOut] = Field(default_factory=list)
    tong: int = 0


class CongDoanOut(BaseModel):
    """Dòng bảng công đoạn trong panel. CỐ Ý không có mốc bắt đầu/kết thúc (spec §4)."""

    id: int
    thu_tu: int
    ten: str
    loai_buoc: str | None = None
    may_id: int | None = None
    may_ten: str | None = None
    to_ten: str | None = None
    so_luong_vao: float = 0.0
    don_vi_vao: str | None = None
    kip_chuan: int = 0
    chay_phut: float = 0.0
    thue_ngoai_ngay: int | None = None
    mau_index: int = 0


class ChiTietOut(_LichChung):
    lsx_id: int
    ma: str
    ten: str
    trang_thai: str
    is_rush: bool = False
    customer_name: str | None = None
    order_no: str | None = None
    customer_po_no: str | None = None
    sale_name: str | None = None
    so_luong_dat: int = 0
    don_vi_tinh: str | None = None
    so_to_ke_hoach: int = 0
    so_to_nguyen: int = 0
    so_con: int = 1
    han_hoan_thanh_sx: date | None = None
    han_giao_khach: date | None = None
    nguoi_phu_trach_ten: str | None = None
    luu_y_gui_xuong: str | None = None
    # Quy cách đọc từ `quy_cach_json` — ẢNH CHỤP lúc tạo lệnh, khoá có thể trống. Trống thì FE BỎ
    # ô, đừng in `null` hay bịa nhãn.
    giay: str | None = None
    kho_in: str | None = None
    so_mau: str | None = None
    so_kem: str | None = None
    kip_chuan: int = 0
    cong_doans: list[CongDoanOut] = Field(default_factory=list)


class DatMocIn(BaseModel):
    bat_dau_at: datetime
    # Chốt chống ghi đè: mốc `updated_at` mà màn đang cầm. Bỏ trống = đặt lần đầu (kéo từ hàng
    # chờ) — không có gì để so, và KHÔNG được đòi.
    expected_updated_at: datetime | None = None
