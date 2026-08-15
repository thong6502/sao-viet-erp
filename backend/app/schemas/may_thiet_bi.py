"""Pydantic schemas — Máy thiết bị. Create/Update permissive (extra allow → field phụ theo
loai_may đi thẳng vào fields_theo_loai/ASSIGNABLE); Row đầy đủ.

🔴 Dọn 11/08/2026: gỡ toàn bộ field KHÔNG có ô nhập trên form Máy (khối BHR + tài sản + offset
chưa nối engine + bảo trì thô) và `BhrBreakdownOut`. Danh sách đầy đủ + lý do: docstring
`models/may_thiet_bi.py`. ⚠️ Thêm field mới phải đi HẾT chuỗi model → ASSIGNABLE → schema In/Row
→ type TS, thiếu một mắt là Pydantic nuốt im lặng và FE nhận `undefined`.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class MayThietBiIn(BaseModel):
    # Cho phép field phụ (theo loai_may) đi kèm — service/repo lọc theo ASSIGNABLE.
    model_config = ConfigDict(extra="allow")

    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    loai_may: str = Field(min_length=1, max_length=24)
    hang_san_xuat: str | None = None
    model: str | None = None
    so_seri: str | None = None
    # Khổ + nhíp (engine bình bài) — khai rõ để validate chặt.
    kho_max_dai: int | None = None
    kho_max_rong: int | None = None
    kho_min_dai: int | None = None
    kho_min_rong: int | None = None
    kho_kem_dai: int | None = None
    kho_kem_rong: int | None = None
    vung_in_dai: int | None = None
    vung_in_rong: int | None = None
    gripper_mm: int | None = None
    nhip_giay_mm: int | None = None
    le_hong_mm: int | None = None
    duoi_thang_mau_mm: int | None = None
    toc_do: float | None = None          # TRUNG BÌNH — số duy nhất chảy vào mọi tính toán
    toc_do_min: float | None = None      # dải năng lực, CHỈ ĐỂ KHAI (xem model)
    toc_do_max: float | None = None
    don_vi_toc_do: str | None = None
    # `makeready_time_default` = thời gian CANH MÁY, Xếp lịch đọc. KHÁC "Chuẩn bị" của Công đoạn
    # (`cong_doan.setup_time`, Lệnh SX đọc) — hai nơi hai việc, không gộp không cộng.
    makeready_time_default: float | None = None
    # Kíp chuẩn cần để vận hành máy. Đây là nhu cầu nhân lực, không nhân tốc độ máy.
    so_nhan_cong: float = Field(default=1, ge=1)
    # Túi JSON: `chuan_bi_khoan` (các khoản chuẩn bị) + `lich_bao_tri` (Lịch bảo trì định kỳ).
    fields_theo_loai: dict | None = None
    # Máy còn dùng hay đã thanh lý (mg `0202`). Máy dừng TẠM thì vẫn `True` — khai ở
    # `machine_unavailable_periods`, xem `models/may_thiet_bi`.
    active: bool = True


class MayThietBiRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten: str
    loai_may: str
    hang_san_xuat: str | None = None
    model: str | None = None
    so_seri: str | None = None
    # Năng lực
    toc_do: float | None = None
    toc_do_min: float | None = None
    toc_do_max: float | None = None
    don_vi_toc_do: str | None = None
    # TÊN đọc được của đơn vị tốc độ, tra từ danh mục Đơn vị (`may_thiet_bi_service.gan_ten_don_vi`)
    # — bảng chỉ lưu MÃ (`to_gio`) mà mã không thành lời. Cùng cách đã làm cho Giấy · Vật tư ·
    # Công đoạn, để màn khỏi nhúng bảng nhãn thứ hai rồi lệch với danh mục.
    #
    # ⚠️ BẪY ĐÃ DÍNH 4 LẦN: service trả thêm field mà schema Out không khai thì Pydantic NUỐT IM
    # LẶNG và FE nhận `undefined`, không lỗi nào. Thêm field phải đi HẾT đường service → schema.
    don_vi_toc_do_ten: str | None = None
    makeready_time_default: float | None = None
    so_nhan_cong: float = 1
    # Engine bình bài
    kho_max_dai: int | None = None
    kho_max_rong: int | None = None
    kho_min_dai: int | None = None
    kho_min_rong: int | None = None
    kho_kem_dai: int | None = None
    kho_kem_rong: int | None = None
    vung_in_dai: int | None = None
    vung_in_rong: int | None = None
    gripper_mm: int | None = None
    nhip_giay_mm: int | None = None
    le_hong_mm: int | None = None
    duoi_thang_mau_mm: int | None = None
    fields_theo_loai: dict | None = None
    active: bool = True
    ghi_chu: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MayThietBiListOut(BaseModel):
    items: list[MayThietBiRow]
    total: int
    page: int
    size: int
    # Số máy theo TỪNG loại (`{"Máy in": 12, "Bế": 3}`) — nuôi số trên tab lọc của màn Thiết bị.
    # Phải do server trả: màn chỉ cầm 20 dòng của trang đang xem nên không tự đếm được nữa, mà
    # `loai_may` là chữ TỰ DO nên màn cũng không biết trước có những tab nào.
    facets: dict[str, int] = {}


# --- Trạng thái máy LÚC NÀY (dẫn xuất) ---------------------------------------
# Cố ý KHÔNG nhét vào `MayThietBiRow`: hàng loạt màn khác đang đổ dropdown máy bằng chính schema
# đó (Tính giá, Lệnh SX, Công đoạn), thêm số phải-tính-mỗi-lần-đọc vào đấy là bắt cả chục chỗ
# không cần trả giá. Màn Thiết bị gọi riêng endpoint này rồi ghép theo id.


class TrangThaiMayRow(BaseModel):
    trang_thai: str          # may_dung | bao_tri | khoa | dang_chay | ranh
    nhan: str                # nhãn tiếng Việt dựng sẵn ở backend — hai màn khỏi tự đặt tên khác nhau
    chi_tiet: str | None = None    # "đứng 3 giờ 20 · dao bế" / "LSX26-0142 · xong 14:30"
    phieu_id: int | None = None    # phiếu sự cố đang mở (mở thẳng drawer bên màn Bảo trì)
    den: datetime | None = None    # lúc máy chạy lại / lệnh chạy xong


class TrangThaiMayOut(BaseModel):
    # Máy KHÔNG có mặt trong map = đang rảnh. Chỉ trả máy có chuyện, khỏi tải cả bảng.
    items: dict[int, TrangThaiMayRow]


# --- Danh mục Nhóm máy -------------------------------------------------------


class NhomMayIn(BaseModel):
    ten: str = Field(min_length=1, max_length=60)


class NhomMayRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ten: str
    active: bool

    # `ma` để dùng chung khuôn danh mục bên FE (`crud()` gõ theo Row có ma/ten). Nhóm máy KHÔNG có
    # mã riêng — chính cái TÊN là giá trị lưu trên `may_thiet_bi.loai_may` — nên soi lại từ `ten`.
    # Phải là `computed_field`: `@property` trần KHÔNG được Pydantic v2 đưa vào JSON.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def ma(self) -> str:
        return self.ten


class NhomMayListOut(BaseModel):
    items: list[NhomMayRow]
    total: int
    # `page`/`size` để phong bì giống 10 danh mục còn lại — FE dùng chung `crud()` và đọc cả bốn
    # khoá; thiếu hai cái này là phân trang câm (undefined). Bảng nhóm máy nhỏ và KHÔNG cắt trang:
    # luôn trả trọn một trang, `size` = số dòng thật.
    page: int = 1
    size: int = 0
