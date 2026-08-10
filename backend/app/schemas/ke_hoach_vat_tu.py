"""Pydantic schemas — bảng CÂN ĐỐI vật tư của Kế hoạch sản xuất.

⚠️ KHÔNG có trường tiền nào ở đây, và đừng thêm. Bảng này mở cho vai Kế hoạch SX (`san_xuat`),
trong khi giá vốn lô hàng thuộc quyền Kho/Kế toán (`view_cost`). Phơi một cột giá "cho tiện" là mở
toàn bộ bảng giá vốn cho một vai chưa từng được cấp quyền đó — mà lỗi kiểu này không ai báo.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CanDoiDong(BaseModel):
    """1 dòng nhu cầu = 1 lệnh (hoặc 1 bài ghép) cần mặt hàng này vào một ngày."""

    #: `vat_tu` = có so tồn · `cong_cu` = khuôn bế, không so tồn (chỉ hỏi có sẵn sàng đúng lúc không).
    loai: str
    lsx_id: int | None = None
    bai_ghep_id: int | None = None
    #: Mã lệnh / mã bài — thứ người dùng đọc.
    ma: str
    #: Tên bước tiêu thụ, để biết "cần cho khâu nào".
    ten_viec: str | None = None
    ngay_can: date | None = None
    #: `true` = bước CHƯA xếp lịch, ngày cần là mốc SUY (hạn SX − tổng thời gian dẫn). UI phải hiện
    #: khác mốc thật, không thì người dùng tin vào một con số chưa ai chốt.
    moc_tam: bool = False

    #: Mọi số dưới đây theo ĐƠN VỊ GỐC của mặt hàng (kho đếm theo đơn vị đó). `None` ở dòng công cụ.
    nhu_cau: float | None = None
    #: Hai đơn vị cùng lúc: "2.961 tờ ≈ 116 kg" — kế hoạch nghĩ theo tờ, kho đếm theo đơn vị gốc.
    nhu_cau_hien_thi: str = ""
    da_cap: float | None = None
    #: CHỈ LÀ NHÃN — hàng chưa ra khỏi kho thì tồn vẫn còn, không vào phép trừ nào.
    dang_linh: float | None = None
    con_phai_co: float | None = None
    con_lai_sau: float | None = None
    #: Phần thiếu RIÊNG của dòng này (không phải thiếu luỹ kế) — tick nhiều dòng rồi cộng vẫn đúng.
    thieu: float | None = None

    #: xam | xanh | vang | do | **khong_ro** (không quy đổi được đơn vị ⇒ máy CHƯA ĐÁNH GIÁ ĐƯỢC).
    #: `khong_ro` cố ý tách khỏi `xam`: xám nghĩa là "đã cấp đủ, hết việc phải lo", dán nhãn đó lên
    #: một dòng chưa ai tính nổi là nói ngược sự thật.
    trang_thai: str = "xam"
    han_dat: date | None = None
    dat_muon: bool = False
    canh_bao: list[str] = Field(default_factory=list)
    ly_do_canh_bao: str | None = None


class CanDoiNhom(BaseModel):
    """Gom theo MẶT HÀNG: một khối = một thứ phải lo, các dòng bên trong là các lệnh giành nhau nó."""

    loai_nhom: str                   # vat_tu | cong_cu
    hang_loai: str
    hang_id: int
    hang_ma: str | None = None
    hang_ten: str | None = None
    don_vi_goc: str | None = None
    ton: float | None = None
    tong_can: float | None = None
    so_dong_do: int = 0
    #: Số dòng KHÔNG đánh giá được. Bộ lọc "chỉ mặt hàng đang thiếu" GIỮ LẠI nhóm có số này > 0 —
    #: thứ máy không tính nổi thì phải lo nhiều hơn, không phải ít hơn.
    so_dong_khong_ro: int = 0
    #: Chỉ nhóm công cụ mới có — tình trạng khuôn + ngày về dự kiến.
    khuon_tinh_trang: str | None = None
    khuon_ngay_ve: date | None = None
    dong: list[CanDoiDong] = Field(default_factory=list)


class CanDoiBoQua(BaseModel):
    """Lệnh/bài KHÔNG cân đối được — hiện thẳng ra thay vì im lặng bỏ.

    Bỏ im lặng là kiểu lỗi tệ nhất ở màn này: bảng xanh hết, người dùng yên tâm, còn lệnh thiếu
    giấy thì không xuất hiện ở đâu cả.
    """

    ma: str
    ly_do: str


class CanDoiOut(BaseModel):
    items: list[CanDoiNhom] = Field(default_factory=list)
    bo_qua: list[CanDoiBoQua] = Field(default_factory=list)


class DeNghiMuaDong(BaseModel):
    """Khoá của một dòng trên bảng — server tự tính lại số thiếu, client KHÔNG gửi số lượng.

    Cố ý không nhận `quantity`: client giữ bản chụp cũ, mà trong lúc người dùng ngồi nhìn bảng thì
    kho có thể đã cấp hoặc hàng đã về. Nhận số của client là đặt mua theo một sự thật đã hết hạn.
    """

    hang_loai: str = Field(pattern="^(giay|vat_tu)$")
    hang_id: int = Field(gt=0)
    lsx_id: int | None = None
    bai_ghep_id: int | None = None


class DeNghiMuaIn(BaseModel):
    dong: list[DeNghiMuaDong] = Field(min_length=1)
    ghi_chu: str | None = Field(default=None, max_length=2000)


class DeNghiMuaOut(BaseModel):
    """Trả MÃ yêu cầu để FE mở lên xem — cố ý KHÔNG tự gửi đi thu mua.

    Máy ghi nhận, người quyết: kế hoạch xem lại số lượng, sửa được, rồi mới bấm gửi ở màn mua hàng.
    """

    id: int
    code: str
