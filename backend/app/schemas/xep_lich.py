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
    # --- Đợt 2 ---
    # ⚠️ Service đã bơm sáu field dưới vào dict từ đầu, nhưng thiếu chúng ở ĐÂY thì pydantic
    # NUỐT IM LẶNG: FE nhận `undefined`, không lỗi, không log. Cụ thể `gom_key` mất làm "Tự xếp"
    # gom mọi dòng vào cùng một khoá ⇒ mục E (gom việc cùng loại) chạy y như chưa có.
    #: (`can_dung_cu` + `khuon_be_id` đã gỡ 16/08/2026 cùng hai detector khuôn — xem mg `0203`.)
    so_nhan_cong: int | None = None
    so_nhan_cong_toi_thieu: int | None = None
    #: Khoá GOM việc cùng loại (giấy · khổ · bộ mực). null = chưa đủ quy cách ⇒ không gom với ai.
    gom_key: str | None = None


class XepLichDongListOut(BaseModel):
    items: list[XepLichDongOut] = Field(default_factory=list)
    total: int = 0


# ============================ Xem trước ảnh hưởng (kéo-thả) ============================
class DayDoiItem(BaseModel):
    id: int
    cong_doan_ten: str | None = None
    som_nhat: datetime | None = None    # sớm-nhất MỚI sau khi bước trước bị đẩy


class CanhBaoItem(BaseModel):
    loai: str
    chu: str


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
    # Cảnh báo tại chỗ thả (mục 2f): khóa máy · ngoài giờ làm · tổ thiếu người · khổ vượt máy.
    # `loai` là hằng `CB_*` của `xep_lich_service`; `chu` đã là câu đủ nghĩa, FE chỉ việc vẽ.
    canh_bao: list[CanhBaoItem] = Field(default_factory=list)


# ============================ Quân số tổ & tầng tuần (ĐỢT 3) ============================
class QuanSoOut(BaseModel):
    """Quân số CÓ HIỆU LỰC của một tổ trong một ngày + quỹ giờ-người suy ra từ đó.

    Trả CẢ `tu_tinh` lẫn `so_nguoi`: người xem phải thấy số đang dùng lệch số suy-từ-hồ-sơ bao
    nhiêu và vì sao (`ly_do`) — chỉ đưa con số cuối thì nó thành số trời cho.
    """
    department_id: int
    ngay: date
    so_nguoi: int
    #: Suy từ hồ sơ nhân sự (đúng tổ lá) trừ phép đã duyệt — nền để so với số gõ đè.
    tu_tinh: int
    go_de: bool = False
    ly_do: str | None = None
    gio_ca: float = 0
    quy_gio_nguoi: float = 0


class QuanSoIn(BaseModel):
    """Gõ đè quân số một ngày. `so_nguoi=None` = BỎ gõ đè (quay về số tự tính)."""
    ngay: date
    so_nguoi: int | None = Field(default=None, ge=0, le=500)
    ly_do: str = Field(default="", max_length=300)


class TaiToKhoangOut(BaseModel):
    """Một khoảng giờ có mức dùng người KHÔNG ĐỔI trong một tổ — nền để Gantt tô lane.

    Cùng nguồn với detector `qua_tai_to`, nên Gantt tô đỏ chỗ nào thì cửa phát hành chặn đúng chỗ
    đó. Khoảng của tổ CHƯA KHAI nhân sự không xuất hiện ở đây (chưa biết thì không kết luận).
    """
    department_id: int
    department_ten: str | None = None
    start: datetime
    finish: datetime
    dung: int = 0
    quan_so: int = 0
    qua_tai: bool = False
    dong_ids: list[int] = Field(default_factory=list)


class NguoiTangGiuaOut(BaseModel):
    """Người thuộc khối SX nhưng gắn ở TẦNG GIỮA — không nằm trong tổ lá nào (mục I).

    KHÔNG được cộng vào tổ nào (cộng là đếm thừa người, lịch hứa năng lực không có thật), nhưng
    cũng không được im lặng bỏ — quỹ giờ-người sẽ hụt mà không ai biết vì sao. Nên: không đếm,
    nhưng NÓI RA để người quản lý đi gắn tổ.
    """
    department_id: int
    department_ten: str
    so_nguoi: int


class TaiToListOut(BaseModel):
    items: list[TaiToKhoangOut] = Field(default_factory=list)
    tang_giua: list[NguoiTangGiuaOut] = Field(default_factory=list)


class TuanOut(BaseModel):
    """Một ô của bảng tuần: một tài nguyên × một tuần.

    Máy gom theo **NHÓM** (`res_id=None`, `nhom` = tên nhóm) chứ không theo máy lẻ: xưởng có 3 máy
    in thì câu hỏi thật là "khâu in tuần sau còn chỗ không". Tổ thì theo từng tổ (`res_id` = id).
    """
    tuan: date
    iso_tuan: int
    loai: str            # may | to
    res_id: int | None = None
    nhom: str | None = None
    ten: str
    can_gio: float = 0
    kha_dung_gio: float = 0
    pct: float = 0
    mau: str = "xanh"    # xanh | vang | do


class KeHoachTuanOut(BaseModel):
    tu: date
    so_tuan: int = 0
    items: list[TuanOut] = Field(default_factory=list)


# ============================ Chèn lệnh gấp & đẩy (G1) ============================
class ChenIn(BaseModel):
    """Chèn dòng vào máy tại mốc `tai`. `may_id=None` = giữ máy hiện tại của dòng.

    `tai` là mốc RANH GIỚI người dùng chỉ trên Gantt; rơi vào giữa một việc thì service tự nhích tới
    lúc việc đó xong (không cắt đôi việc đang xếp).
    """
    may_id: int | None = None
    tai: datetime


class ChenDongOut(BaseModel):
    """Một dòng trong bảng xem trước — *giờ cũ → giờ mới* kèm hai cờ cần nhìn trước khi Lưu."""
    id: int
    lsx_ma: str | None = None
    cong_doan_ten: str | None = None
    may_id: int | None = None
    may_ten: str | None = None
    cu: datetime | None = None
    moi: datetime | None = None
    finish_moi: datetime | None = None
    #: Chính việc đang chèn (dòng đầu bảng) — UI tô khác để phân biệt với việc BỊ đẩy.
    la_viec_chen: bool = False
    tre_han: bool = False
    #: Mã lệnh/bài mà dòng này sẽ ĐÈ lên sau khi dời — chỉ cảnh báo, KHÔNG đẩy tiếp (đúng một tầng).
    dung_do: list[str] = Field(default_factory=list)
    is_locked: bool = False


class ChenOut(BaseModel):
    """Kết quả mô phỏng chèn — **chưa ghi gì vào DB**; UI áp bằng `gan-loat` khi người dùng bấm Lưu."""
    dong_id: int
    may_id: int
    start_at: datetime | None = None
    finish_at: datetime | None = None
    chiem_may_phut: float = 0
    #: `gap_khoa` = dừng lan vì gặp dòng đã khóa. None = lan hết tự nhiên (khe trống nuốt vừa).
    chan: str | None = None
    rows: list[ChenDongOut] = Field(default_factory=list)


# ============================ Gợi ý ============================
class GoiYMayOut(BaseModel):
    """Một máy ứng viên — *tên máy · khe sớm nhất · **giờ xong** · cờ khổ*.

    `finish` là thứ để SẮP, không phải `khe_trong`: tốc độ khai theo từng máy nên máy rảnh sớm hơn
    chưa chắc xong sớm hơn. `chiem_may_phut` tính LẠI theo chính máy này (mỗi dòng một con số khác).
    """

    may_id: int
    may_ten: str | None = None
    khe_trong: datetime | None = None
    finish: datetime | None = None
    chiem_may_phut: float = 0
    #: Khổ giấy vượt khổ máy — vẫn liệt kê (xếp cuối) chứ không giấu: máy đề xuất, người quyết.
    khong_hop_kho: bool = False
    #: Việc liền trước trên máy này CÙNG LOẠI (giấy · khổ · bộ mực) — mục E. Là tiêu chí PHỤ khi
    #: hai máy hoà giờ xong; không bao giờ lật ngược thứ tự giờ.
    cung_gom: bool = False


class GoiYOut(BaseModel):
    may_id: int | None = None
    khe_trong: datetime | None = None       # khe trống sớm nhất trên máy
    finish_neu_xep: datetime | None = None  # kết thúc nếu xếp vào khe đó
    han_lui: datetime | None = None         # bắt đầu muộn nhất còn kịp hạn
    #: Top 3 máy làm được công đoạn, sắp theo GIỜ XONG. Chạy cả khi dòng CHƯA gán máy — đúng lúc
    #: cần gợi ý nhất; bốn field trên khi đó đều rỗng vì chúng bám "máy đang gán".
    goi_y_may: list[GoiYMayOut] = Field(default_factory=list)


# ============================ Lịch nền máy (Gantt) ============================
class KhoangLamOut(BaseModel):
    start: datetime
    finish: datetime


class VungKhoaOut(BaseModel):
    start: datetime
    finish: datetime
    ly_do: str | None = None
    #: `chan` = máy nghỉ · `mo_them` = máy chạy thêm ngoài ca. Hai chuyện NGƯỢC nhau nên Gantt phải
    #: vẽ khác màu; thiếu field này thì vùng tăng ca hiện y như vùng bảo trì — đọc ngược ý.
    kieu: str = "chan"


class LichNenMayOut(BaseModel):
    """Nền để Gantt vẽ: khoảng LÀM VIỆC của xưởng (theo ca) + vùng KHÓA máy (bảo trì/khóa) trong dải ngày."""
    may_id: int
    khoang_lam: list[KhoangLamOut] = Field(default_factory=list)
    khoang_khoa: list[VungKhoaOut] = Field(default_factory=list)


# ============================ Vùng khóa máy (CRUD) ============================
class VungKhoaIn(BaseModel):
    """Khoảng giờ RIÊNG của 1 máy. `tu`/`den` = giờ nhà máy (naive → coi giờ nhà máy).

    Hai kiểu dùng CHUNG một form (mục G3): `chan` = máy nghỉ (bảo trì/hỏng), `mo_them` = máy chạy
    thêm ngoài ca. Cùng hình dạng dữ liệu, chỉ khác dấu — tách làm hai màn là hai nơi phải nhớ.
    Kiểu `mo_them` thì `ly_do` không mang nghĩa nghỉ; service tự ép về `khac`.
    """
    tu: datetime
    den: datetime
    ly_do: str = "bao_tri"          # bao_tri | hong_hoc | nghi | khac
    kieu: str = "chan"              # chan | mo_them
    note: str | None = None


class VungKhoaItemOut(BaseModel):
    id: int
    may_id: int
    start: datetime
    finish: datetime
    ly_do: str
    kieu: str = "chan"
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
    category: str                        # may | nguoi | vat_tu | han | du_lieu | thue_ngoai
    severity: str                        # chan | luu_y
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
    chan: int = 0                        # chưa phát hành được
    luu_y: int = 0                       # cứ làm, nhưng nên biết
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
    #: ĐÃ phát hành chưa (G2). True ⇒ UI hiện nút "Gỡ phát hành" thay cho nút "Phát hành".
    #: Thiếu cờ này thì lệnh phát hành xong biến mất khỏi màn và ĐÓNG BĂNG: sửa thì bị chặn
    #: "gỡ kế hoạch trước", mà gỡ kế hoạch lại đòi gỡ phát hành trước — không có cửa nào.
    da_phat_hanh: bool = False


class SanSangOut(BaseModel):
    items: list[SanSangItem] = Field(default_factory=list)
    total: int = 0
