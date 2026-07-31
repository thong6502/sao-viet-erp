"""Pydantic schemas — Đề nghị kho & Phiếu nhập/xuất (spec-kho-de-nghi).

Lưu ý phân quyền trên các schema Out: những trường NHẠY CẢM (`don_gia`, `don_gia_nhap`,
`gia_von`, `ton_kha_dung`) đều `None`-able và được router XÓA khi người gọi thiếu quyền
(`can_view_cost` / `can_view_stock`). Ẩn ở tầng schema chứ không chỉ ẩn trên UI — nếu chỉ
ẩn cột ở FE thì số vẫn nằm trong response, mở DevTools là thấy.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Đề nghị ----------------------------------------------------------------

class StockRequestLineIn(BaseModel):
    # Hàng đã có mã → material_id. Hàng MỚI → bỏ material_id, gõ `ten_tu_do`. Đúng 1 trong 2.
    material_id: int | None = None
    ten_tu_do: str | None = Field(default=None, max_length=255)
    dvt: str = Field(min_length=1, max_length=16)
    sl_de_nghi: float = Field(gt=0)
    # Đơn giá NHẬP do người đề nghị khai (chỉ đề nghị NHẬP). Phiếu kế thừa; kho không sửa.
    don_gia: int | None = Field(default=None, ge=0)
    # Quy đổi đơn vị do người đề nghị khai (1 don_vi_phu = he_so_quy_doi × dvt tồn).
    don_vi_phu: str | None = Field(default=None, max_length=16)
    he_so_quy_doi: float | None = Field(default=None, gt=0)
    ghi_chu: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _one_of(self):
        has_id = self.material_id is not None
        has_name = bool((self.ten_tu_do or "").strip())
        if has_id == has_name:
            raise ValueError("Mỗi dòng phải có ĐÚNG một: mã hàng có sẵn HOẶC tên hàng mới.")
        return self


class StockRequestCreate(BaseModel):
    loai: str = Field(pattern="^(NHAP|XUAT)$")
    # Kho KHÔNG chọn ở đề nghị nữa — quyết ở bước lập phiếu. Giữ optional cho tương thích.
    kho_id: int | None = None
    # Số đề nghị tự nhập (tuỳ chọn); bỏ trống → hệ thống tự sinh (DNN/DNX####).
    ma: str | None = Field(default=None, max_length=30)
    ngay_can: date | None = None
    uu_tien: str = Field(default="binh_thuong", pattern="^(binh_thuong|gap)$")
    ghi_chu: str | None = Field(default=None, max_length=1000)
    lines: list[StockRequestLineIn] = Field(min_length=1)


class StockRequestUpdate(BaseModel):
    ngay_can: date | None = None
    uu_tien: str | None = Field(default=None, pattern="^(binh_thuong|gap)$")
    ghi_chu: str | None = Field(default=None, max_length=1000)
    lines: list[StockRequestLineIn] | None = None


class StockRequestApprove(BaseModel):
    """`approved_qty`: line_id → SL duyệt. Bỏ trống = duyệt nguyên số đề nghị."""

    approved_qty: dict[int, float] | None = None


class StockRequestReject(BaseModel):
    ly_do: str = Field(min_length=1, max_length=500)


class StockRequestLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int | None = None
    material_code: str | None = None
    material_name: str | None = None
    # Hàng mới chưa có mã: tên gõ tự do. Kho gắn/tạo mã ở phiếu.
    ten_tu_do: str | None = None
    dvt: str
    # Quy đổi KHO của mặt hàng (để phiếu NHẬP cho nhập theo đơn vị phụ). None = không quy đổi.
    don_vi_phu: str | None = None
    he_so_quy_doi: float | None = None
    sl_de_nghi: float
    sl_duyet: float
    sl_da_ung: float
    # Đơn giá NHẬP người đề nghị khai — phiếu kế thừa (kho chỉ đọc). Null với đề nghị XUẤT.
    don_gia: int | None = None
    # Kho phản hồi: lý do kho cấp/nhập thiếu so với còn phải cấp (nếu có).
    ly_do_thieu: str | None = None
    ghi_chu: str | None = None
    # Tính, không lưu — xem models/stock_request.py.
    sl_con_lai: float = 0.0
    # Đèn tín hiệu 5 màu: AI CŨNG nhận được (không kèm số nên không lộ tồn).
    muc_ton: str | None = None
    # CHỈ khi có `can_view_stock`; router xóa nếu thiếu quyền.
    ton_kha_dung: float | None = None


class StockRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    loai: str
    nguoi_tao_id: int
    nguoi_tao_ten: str | None = None
    bo_phan_id: int | None = None
    # Ô "Bộ phận" trên mẫu 01-VT/02-VT + cột Bộ phận ở Hộp yêu cầu.
    bo_phan_ten: str | None = None
    kho_id: int | None = None
    kho_ten: str | None = None
    ngay_can: date | None = None
    uu_tien: str
    ghi_chu: str | None = None
    trang_thai: str
    nguoi_duyet_id: int | None = None
    nguoi_duyet_ten: str | None = None
    duyet_luc: datetime | None = None
    ly_do_tu_choi: str | None = None
    # Lý do KHO hủy đề nghị (hủy phiếu → đề nghị 'Đã hủy'). Hiện ở mục "Đã hủy".
    ly_do_huy: str | None = None
    created_at: datetime
    # Id phiếu ĐANG CHỜ GHI SỔ (nếu có) — FE đổi nút "Lập phiếu" thành "Xem phiếu", chống tạo trùng.
    open_voucher_id: int | None = None
    lines: list[StockRequestLineOut] = []


class StockRequestPage(BaseModel):
    items: list[StockRequestOut]
    total: int


class StockVoucherCancel(BaseModel):
    """Body khi HỦY phiếu nháp — BẮT BUỘC lý do; đề nghị chuyển 'Đã hủy' kèm lý do này."""

    ly_do: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _strip(self) -> "StockVoucherCancel":
        self.ly_do = self.ly_do.strip()
        if not self.ly_do:
            raise ValueError("Phải nhập lý do hủy.")
        return self


# --- Phiếu -------------------------------------------------------------------

class StockVoucherLineIn(BaseModel):
    request_line_id: int
    # Dòng đề nghị là HÀNG MỚI (chưa có mã): kho CHỌN mã có sẵn → điền `material_id`; hoặc TẠO
    # MỚI → bỏ material_id, khai `new_*` (backend tạo mã khi LƯU/GHI SỔ, không tạo eager ở FE).
    material_id: int | None = None
    new_name: str | None = Field(default=None, max_length=255)
    new_unit: str | None = Field(default=None, max_length=16)
    new_don_vi_phu: str | None = Field(default=None, max_length=16)
    new_he_so_quy_doi: float | None = Field(default=None, gt=0)
    so_luong: float = Field(gt=0)
    # Phiếu NHẬP: giá của lô sắp tạo. Phiếu XUẤT: bỏ qua (giá lấy từ lô).
    don_gia: int | None = Field(default=None, ge=0)
    # Phiếu XUẤT: bắt buộc. Phiếu NHẬP: bỏ qua (lô sinh ra lúc ghi sổ).
    lot_id: int | None = None
    # Lý do cấp/nhập THIẾU (khi SL < còn phải cấp) — bắt buộc nếu thiếu; ghi vào đề nghị (kho phản hồi).
    ly_do: str | None = Field(default=None, max_length=500)
    ghi_chu: str | None = Field(default=None, max_length=500)


class StockVoucherCreate(BaseModel):
    request_id: int
    kho_id: int
    # Số phiếu tự nhập (tuỳ chọn); bỏ trống → hệ thống tự sinh (PNK/PXK####).
    ma: str | None = Field(default=None, max_length=30)
    ngay: date | None = None
    nguoi_giao_nhan: str | None = Field(default=None, max_length=150)
    ghi_chu: str | None = Field(default=None, max_length=1000)
    lines: list[StockVoucherLineIn] = Field(min_length=1)


class StockVoucherLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_line_id: int
    material_id: int
    material_code: str | None = None
    material_name: str | None = None
    dvt: str | None = None
    lot_id: int | None = None
    ma_lo: str | None = None
    so_luong: float
    ghi_chu: str | None = None
    # Hai trường tiền — router xóa khi thiếu `can_view_cost`.
    don_gia: int | None = None
    thanh_tien: int | None = None


class StockVoucherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    loai: str
    request_id: int
    request_ma: str | None = None
    kho_id: int
    kho_ten: str | None = None
    ngay: date
    nguoi_lap_id: int
    nguoi_lap_ten: str | None = None
    # Chuỗi trách nhiệm lấy từ ĐỀ NGHỊ gốc: ai đề nghị · ai duyệt (phiếu tự nó không có bước duyệt).
    nguoi_de_nghi_ten: str | None = None
    nguoi_duyet_ten: str | None = None
    # Người GHI SỔ (duyệt/chốt phiếu) — chỉ có sau khi đã ghi sổ.
    nguoi_ghi_so_ten: str | None = None
    nguoi_giao_nhan: str | None = None
    ghi_chu: str | None = None
    trang_thai: str
    ghi_so_luc: datetime | None = None
    created_at: datetime
    lines: list[StockVoucherLineOut] = []
    # Tổng giá vốn — chỉ có khi `can_view_cost`.
    gia_von: int | None = None


class StockVoucherPage(BaseModel):
    items: list[StockVoucherOut]
    total: int


class StockVoucherAttachmentOut(BaseModel):
    """Hóa đơn/chứng từ gốc đính kèm phiếu — chỉ metadata + đường dẫn tải (mount /static)."""

    id: int
    stock_voucher_id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime


class StockVoucherAttachmentListOut(BaseModel):
    items: list[StockVoucherAttachmentOut]


# --- Lô & phân bổ ------------------------------------------------------------

class StockLotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma_lo: str
    material_id: int
    material_code: str | None = None
    material_name: str | None = None
    # Đơn vị tính của mã hàng — để màn Tồn kho tạo dòng "Yêu cầu mua" có sẵn ĐVT.
    dvt: str | None = None
    kho_id: int
    vi_tri: str | None = None
    ngay_nhap: date
    ncc: str | None = None
    sl_ban_dau: float
    sl_con_lai: float
    hsd: date | None = None
    trang_thai: str
    # Phiếu NHẬP đã tạo ra lô này — để màn Tồn kho link mã lô → phiếu. Null với tồn đầu kỳ.
    voucher_id: int | None = None
    # Giá vốn của lô — chỉ có khi `can_view_cost`. Thủ kho chọn lô mà không thấy giá.
    don_gia_nhap: int | None = None


class AllocationLineOut(BaseModel):
    lot_id: int
    ma_lo: str
    ngay_nhap: date
    hsd: date | None = None
    sl_con_lai: float
    so_luong: float
    don_gia_nhap: int | None = None


class AllocationOut(BaseModel):
    """Gợi ý phân bổ lô cho 1 dòng xuất. `thieu` > 0 = kho không đủ hàng."""

    lines: list[AllocationLineOut]
    thieu: float


# --- Lịch sử Nhập/Xuất theo vật tư (popup màn Tồn kho) -----------------------

class MaterialXuatRow(BaseModel):
    """1 dòng phiếu XUẤT đã ghi sổ của mã hàng — để theo dõi xuất RIÊNG với nhập (lô)."""

    ngay: date
    voucher_id: int
    voucher_ma: str | None = None
    lot_id: int | None = None
    ma_lo: str | None = None
    so_luong: float
    # Giá vốn ĐÍCH DANH của lô đã xuất — router XÓA khi thiếu `can_view_cost`.
    don_gia: int | None = None


class MaterialHistoryOut(BaseModel):
    """Lịch sử 1 mã hàng tại 1 kho: NHẬP = các lô (kể cả đã hết) · XUẤT = dòng phiếu xuất."""

    material_id: int
    material_code: str | None = None
    material_name: str | None = None
    dvt: str | None = None
    on_hand: float
    nhap: list[StockLotOut] = []
    xuat: list[MaterialXuatRow] = []


# --- Ngưỡng tồn ---------------------------------------------------------------

class StockThresholdIn(BaseModel):
    material_id: int
    kho_id: int
    nguong_ton: float = Field(ge=0)
    # Bỏ trống → service suy ra = nguong_ton × 1.3 (spec §7).
    nguong_can_ton: float | None = Field(default=None, ge=0)
    nguong_toi_da: float | None = Field(default=None, ge=0)
    canh_bao: bool = True


class StockThresholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    kho_id: int
    nguong_ton: float
    nguong_can_ton: float | None = None
    nguong_toi_da: float | None = None
    canh_bao: bool


class StockLevelOut(BaseModel):
    """Mức tồn của 1 mã hàng. `ton_kha_dung` chỉ có khi `can_view_stock` — thiếu quyền thì
    người dùng vẫn thấy `muc_ton` (đèn 5 màu) để biết sắp hết mà không biết còn bao nhiêu."""

    material_id: int
    muc_ton: str
    ton_kha_dung: float | None = None


class StockMaterialCreate(BaseModel):
    """Thêm nhanh mặt hàng ngay ở đề nghị — tên + ĐVT (giá nhập ở bước phiếu).

    `code` tuỳ chọn: người dùng tự đặt mã; bỏ trống → hệ thống tự sinh (HH###).
    """

    name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=16)
    code: str | None = Field(default=None, max_length=20)
    # Quy đổi đơn vị KHO (tuỳ chọn): 1 don_vi_phu = he_so_quy_doi × unit (đơn vị tồn).
    don_vi_phu: str | None = Field(default=None, max_length=16)
    he_so_quy_doi: float | None = Field(default=None, gt=0)


class StockMaterialQuyDoi(BaseModel):
    """Khai/sửa quy đổi cho hàng đã có — nút 'Quy đổi' trên dòng phiếu. Cả hai trống = bỏ quy đổi."""

    don_vi_phu: str | None = Field(default=None, max_length=16)
    he_so_quy_doi: float | None = Field(default=None, gt=0)
