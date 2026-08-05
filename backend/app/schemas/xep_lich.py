"""Pydantic schemas — Xếp lịch công đoạn.

Service trả DICT đã tính sẵn (thời lượng · sớm-nhất/muộn-nhất · độ dư · nhãn nguy cơ · cờ xung đột);
response model chỉ để validate + tài liệu OpenAPI. Request dùng `exclude_unset` (router) để phân biệt
"không gửi" với "gửi null" khi gán từng phần.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# ============================ Request ============================
class GanIn(BaseModel):
    """Gán tài nguyên + giờ cho 1 dòng. Trường nào không gửi thì giữ nguyên (router `exclude_unset`)."""
    may_id: int | None = None
    department_id: int | None = None
    nha_cung_cap: str | None = None
    work_shift_id: int | None = None
    start_at: datetime | None = None


class GanLoatRow(GanIn):
    id: int


class GanLoatIn(BaseModel):
    rows: list[GanLoatRow] = Field(default_factory=list)


class XemTruocIn(BaseModel):
    """Mô phỏng thả 1 dòng vào (máy, giờ) — không đổi DB. `may_id=None` = giữ máy hiện tại của dòng."""
    may_id: int | None = None
    start_at: datetime


class KhoaIn(BaseModel):
    khoa: bool = True


# ============================ Hàng chờ (order-pool) ============================
class HangChoItem(BaseModel):
    nguon: str                       # lsx | in_ghep
    id: int
    ma: str
    ten: str | None = None
    so_cong_doan: int = 0
    is_rush: bool = False
    han_hoan_thanh_sx: date | None = None


class HangChoOut(BaseModel):
    items: list[HangChoItem] = Field(default_factory=list)
    total: int = 0


# ============================ Bảng dòng lịch ============================
class XepLichDongOut(BaseModel):
    id: int
    nguon: str
    lsx_id: int | None = None
    bai_ghep_id: int | None = None
    lsx_ma: str | None = None
    cong_doan_ten: str | None = None
    loai_buoc: str | None = None
    so_luong_vao: float | None = None
    don_vi_vao: str | None = None
    # Tài nguyên gán
    may_id: int | None = None
    may_ten: str | None = None
    department_id: int | None = None
    department_ten: str | None = None
    nha_cung_cap: str | None = None
    work_shift_id: int | None = None
    # Lịch (theo giờ) + dẫn xuất
    som_nhat: datetime | None = None
    muon_nhat: datetime | None = None
    start_at: datetime | None = None
    finish_at: datetime | None = None
    chiem_may_phut: float = 0
    # Dải nhanh/chậm nhất — Gantt vẽ RÂU ở đuôi thanh (thanh vẫn đặt theo TB).
    chiem_may_phut_min: float = 0
    chiem_may_phut_max: float = 0
    tong_phut: float = 0
    # Breakdown chiếm máy (Gantt vẽ thanh 2 đoạn setup+chạy). Vệ sinh/rửa mực đã bỏ khỏi hệ.
    setup_phut: float = 0
    chay_phut: float = 0
    theo_may: bool = False              # thời lượng tính LẠI theo tốc độ máy đang gán (HM3) vs snapshot bước
    canh_bao_thoi_luong: str | None = None  # may_chua_toc_do | don_vi_lech — vì sao không tính-theo-máy được
    slack_ngay: int | None = None
    nhan_rui_ro: str | None = None      # an_toan | sap_toi_han | nguy_co_tre | da_tre | chua_co_han
    # Trạng thái
    trang_thai: str
    is_locked: bool = False
    co_xung_dot: bool = False
    blocked_reason: str | None = None
    # Kiểm khả năng máy (HM4) — soft, KHÔNG chặn: khổ/số màu/định lượng vượt spec máy đang gán.
    can_xac_nhan: bool = False
    ly_do_xac_nhan: list[str] = Field(default_factory=list)
    is_rush: bool = False


class XepLichDongListOut(BaseModel):
    items: list[XepLichDongOut] = Field(default_factory=list)
    total: int = 0


# ============================ Xem trước ảnh hưởng (kéo-thả) ============================
class DayDoiItem(BaseModel):
    id: int
    cong_doan_ten: str | None = None
    som_nhat: datetime | None = None    # sớm-nhất MỚI sau khi bước trước bị đẩy


class XemTruocOut(BaseModel):
    """Ảnh hưởng khi thả 1 dòng — hộp thoại xác nhận chỉ bật khi có `day_doi`/`xung_dot_ids`/`can_xac_nhan`."""
    finish_at: datetime | None = None
    chiem_may_phut: float = 0
    # Dải nhanh/chậm nhất — Gantt vẽ RÂU ở đuôi thanh (thanh vẫn đặt theo TB).
    chiem_may_phut_min: float = 0
    chiem_may_phut_max: float = 0
    setup_phut: float = 0
    chay_phut: float = 0
    theo_may: bool = False
    xung_dot_ids: list[int] = Field(default_factory=list)
    day_doi: list[DayDoiItem] = Field(default_factory=list)
    han_hoan_thanh_moi: date | None = None
    nhan_rui_ro: str | None = None
    can_xac_nhan: bool = False
    ly_do_xac_nhan: list[str] = Field(default_factory=list)


# ============================ Gợi ý ============================
class GoiYOut(BaseModel):
    may_id: int | None = None
    khe_trong: datetime | None = None       # khe trống sớm nhất trên máy
    finish_neu_xep: datetime | None = None  # kết thúc nếu xếp vào khe đó
    han_lui: datetime | None = None         # bắt đầu muộn nhất còn kịp hạn


# ============================ Lịch nền máy (Gantt) ============================
class KhoangLamOut(BaseModel):
    start: datetime
    finish: datetime


class VungKhoaOut(BaseModel):
    start: datetime
    finish: datetime
    ly_do: str | None = None


class LichNenMayOut(BaseModel):
    """Nền để Gantt vẽ: khoảng LÀM VIỆC của xưởng (theo ca) + vùng KHÓA máy (bảo trì/khóa) trong dải ngày."""
    may_id: int
    khoang_lam: list[KhoangLamOut] = Field(default_factory=list)
    khoang_khoa: list[VungKhoaOut] = Field(default_factory=list)


# ============================ Vùng khóa máy (CRUD) ============================
class VungKhoaIn(BaseModel):
    """Tạo khoảng khóa 1 máy (bảo trì/hỏng/nghỉ). `tu`/`den` = giờ nhà máy (naive → coi giờ nhà máy)."""
    tu: datetime
    den: datetime
    ly_do: str = "bao_tri"          # bao_tri | hong_hoc | nghi | khac
    note: str | None = None


class VungKhoaItemOut(BaseModel):
    id: int
    may_id: int
    start: datetime
    finish: datetime
    ly_do: str
    note: str | None = None


class VungKhoaListOut(BaseModel):
    items: list[VungKhoaItemOut] = Field(default_factory=list)


# ============================ Vấn đề kế hoạch (xung đột & nguy cơ trễ) ============================
# Vấn đề là DẪN XUẤT (service tính lúc đọc) — response model chỉ để validate + tài liệu.
class VanDeImpact(BaseModel):
    lsx_ids: list[int] = Field(default_factory=list)
    bai_ghep_ids: list[int] = Field(default_factory=list)
    may_ids: list[int] = Field(default_factory=list)
    dong_ids: list[int] = Field(default_factory=list)
    mas: list[str] = Field(default_factory=list)


class VanDeException(BaseModel):
    ly_do: str | None = None
    by: int | None = None
    expires_at: datetime | None = None


class VanDeItem(BaseModel):
    issue_key: str
    category: str                        # de_khoa_may | sai_tien_nhiem | thieu_du_lieu | nguy_co_tre | may_khong_kham | qua_tai_may | han_bai_ghep | thue_ngoai
    severity: str                        # chan | nghiem_trong | cao | canh_bao
    title: str
    nguyen_nhan: str | None = None
    impacts: VanDeImpact
    delay_phut: float | None = None
    group_key: str | None = None
    # State người xử lý (trộn lúc đọc)
    trang_thai: str                      # moi | tiep_nhan | dang_xu_ly | ngoai_le | tam_hoan
    assigned_to: int | None = None
    note: str | None = None
    tai_phat: int = 0
    mo_lai: bool = False                 # vấn đề tái phát (đã xử lý mà lại dẫn xuất)
    exception: VanDeException | None = None


class VanDeSummary(BaseModel):
    chan: int = 0
    nghiem_trong: int = 0
    cao: int = 0
    canh_bao: int = 0
    ngoai_le: int = 0
    tong: int = 0


class VanDeListOut(BaseModel):
    items: list[VanDeItem] = Field(default_factory=list)
    summary: VanDeSummary
    total: int = 0


class VanDeActionIn(BaseModel):
    issue_key: str


class VanDeGiaoIn(VanDeActionIn):
    user_id: int


class VanDeGhiChuIn(VanDeActionIn):
    note: str


class VanDeNgoaiLeIn(VanDeActionIn):
    ly_do: str
    expires_at: datetime | None = None


class VanDeStateOut(BaseModel):
    """Dòng state sau một hành động (không kèm phần dẫn xuất)."""
    issue_key: str
    trang_thai: str
    assigned_to: int | None = None
    note: str | None = None
    tai_phat: int = 0


class PhatHanhOut(BaseModel):
    id: int
    ma: str
    trang_thai: str


class SanSangItem(BaseModel):
    nguon: str                           # lsx | in_ghep
    id: int
    ma: str
    blocking: int                        # số xung đột CHẶN còn lại (0 = phát hành được)


class SanSangOut(BaseModel):
    items: list[SanSangItem] = Field(default_factory=list)
    total: int = 0
