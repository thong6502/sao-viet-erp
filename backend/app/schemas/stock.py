"""Pydantic schemas — Yêu cầu kho & Phiếu nhập/xuất (spec-kho-de-nghi).

Lưu ý phân quyền trên các schema Out: những trường NHẠY CẢM (`don_gia`, `don_gia_nhap`,
`gia_von`, `ton_kha_dung`) đều `None`-able và được router XÓA khi người gọi thiếu quyền
(`can_view_cost` / `can_view_stock`). Ẩn ở tầng schema chứ không chỉ ẩn trên UI — nếu chỉ
ẩn cột ở FE thì số vẫn nằm trong response, mở DevTools là thấy.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Yêu cầu ----------------------------------------------------------------

class StockRequestLineIn(BaseModel):
    # MẶT HÀNG GỐC — bắt buộc chọn từ danh mục Giấy / Vật tư khác (siết 2026-08-08). Không còn
    # đường gõ tên tự do rồi kho gắn mã sau.
    hang_loai: str = Field(pattern="^(giay|vat_tu)$")
    hang_id: int = Field(gt=0)
    # XIN CHO LỆNH NÀO (mg 0175). Bỏ trống được — xin lặt vặt (băng dính, giẻ lau) không thuộc lệnh
    # nào, bắt buộc gắn là chặn luôn luồng kho đang chạy. Khai rồi thì bảng cân đối vật tư trừ phần
    # đã cấp vào ĐÚNG dòng nhu cầu, thay vì để mọi lệnh dùng chung loại giấy cùng báo thiếu.
    lsx_id: int | None = Field(default=None, gt=0)
    bai_ghep_id: int | None = Field(default=None, gt=0)
    # Đơn vị người đề nghị chọn — phải nằm trong tập đổi được của chính mặt hàng đó (service kiểm).
    dvt: str = Field(min_length=1, max_length=24)
    sl_de_nghi: float = Field(gt=0)
    # Đơn giá NHẬP do người đề nghị khai (chỉ đề nghị NHẬP), theo `dvt`. Phiếu kế thừa; kho không sửa.
    don_gia: int | None = Field(default=None, ge=0)
    ghi_chu: str | None = Field(default=None, max_length=500)


class StockRequestCreate(BaseModel):
    loai: str = Field(pattern="^(NHAP|XUAT)$")
    # Kho KHÔNG chọn ở yêu cầu nữa — quyết ở bước lập phiếu. Giữ optional cho tương thích.
    kho_id: int | None = None
    # Số yêu cầu tự nhập (tuỳ chọn); bỏ trống → hệ thống tự sinh (DNN/DNX####).
    ma: str | None = Field(default=None, max_length=30)
    ngay_can: date | None = None
    uu_tien: str = Field(default="binh_thuong", pattern="^(binh_thuong|gap)$")
    ghi_chu: str | None = Field(default=None, max_length=1000)
    # Mã loại nhập/xuất kho theo MISA (0/1/2/3…) — người tạo gõ tay; Báo cáo kho dùng để export.
    loai_kho: str | None = Field(default=None, max_length=50)
    lines: list[StockRequestLineIn] = Field(min_length=1)


class StockRequestUpdate(BaseModel):
    ngay_can: date | None = None
    uu_tien: str | None = Field(default=None, pattern="^(binh_thuong|gap)$")
    ghi_chu: str | None = Field(default=None, max_length=1000)
    loai_kho: str | None = Field(default=None, max_length=50)
    lines: list[StockRequestLineIn] | None = None


class StockRequestApprove(BaseModel):
    """`approved_qty`: line_id → SL duyệt. Bỏ trống = duyệt nguyên số yêu cầu."""

    approved_qty: dict[int, float] | None = None


class StockRequestReject(BaseModel):
    ly_do: str = Field(min_length=1, max_length=500)


class StockRequestLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hang_loai: str
    hang_id: int
    # Mã · tên · nhóm của mặt hàng gốc — router gán để FE khỏi gọi thêm danh mục.
    hang_ma: str | None = None
    hang_ten: str | None = None
    hang_nhom: str | None = None
    # "Cho lệnh nào" (mg 0175) + MÃ để FE hiện thẳng, khỏi gọi thêm một vòng /api/lsx cho mỗi dòng.
    lsx_id: int | None = None
    bai_ghep_id: int | None = None
    lsx_ma: str | None = None
    bai_ghep_ma: str | None = None
    dvt: str
    # Số đã quy về ĐƠN VỊ GỐC + câu diễn giải ("1 ram = 41,93 kg") — FE hiện dòng nhắc dưới ô SL
    # để người khai thấy trước con số sẽ vào tồn. None = không đổi được (kèm `canh_bao_dv`).
    don_vi_goc: str | None = None
    sl_quy_doi: float | None = None
    quy_doi_dien_giai: str | None = None
    canh_bao_dv: str | None = None
    sl_de_nghi: float
    sl_duyet: float
    sl_da_ung: float
    # Đơn giá NHẬP người yêu cầu khai — phiếu kế thừa (kho chỉ đọc). Null với yêu cầu XUẤT.
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
    # Loại nhập/xuất kho (tự do — tên hoặc mã) người tạo gõ ở yêu cầu — Báo cáo kho đọc để export.
    loai_kho: str | None = None
    trang_thai: str
    nguoi_duyet_id: int | None = None
    nguoi_duyet_ten: str | None = None
    duyet_luc: datetime | None = None
    ly_do_tu_choi: str | None = None
    # Lý do KHO hủy yêu cầu (hủy phiếu → yêu cầu 'Đã hủy'). Hiện ở mục "Đã hủy".
    ly_do_huy: str | None = None
    created_at: datetime
    # Lần đổi gần nhất (tạo/cấp/hoàn tất/hủy) — FE xếp yêu cầu VỪA CÓ PHẢN HỒI lên đầu cho dễ thấy.
    updated_at: datetime
    # Id phiếu ĐANG CHỜ GHI SỔ (nếu có) — FE đổi nút "Lập phiếu" thành "Xem phiếu", chống tạo trùng.
    open_voucher_id: int | None = None
    lines: list[StockRequestLineOut] = []


class StockRequestPage(BaseModel):
    items: list[StockRequestOut]
    total: int


# --- Báo cáo kho (kế toán) — docs/spec-bao-cao-kho.md ---

class BaoCaoKhoRow(BaseModel):
    """1 dòng hàng của 1 phiếu ĐÃ GHI SỔ — cho màn Báo cáo kho (kế toán) + export MISA."""

    voucher_id: int
    ngay_ghi_so: date | None = None      # = ngày hạch toán (MISA)
    ngay_ct: date | None = None          # = ngày chứng từ (ngày lập phiếu)
    so_ct: str                            # = số chứng từ (mã phiếu)
    loai: str                             # NHAP / XUAT
    loai_kho: str | None = None           # loại (tự do) người tạo gõ ở yêu cầu
    ma_hang: str | None = None
    ten_hang: str | None = None
    dvt: str | None = None
    so_luong: float
    don_gia: int | None = None
    thanh_tien: float | None = None
    kho_id: int | None = None
    kho_ten: str | None = None


class BaoCaoKhoPage(BaseModel):
    items: list[BaoCaoKhoRow]
    total: int


class KhoKhoaSoIn(BaseModel):
    kho_id: int | None = None             # None = TOÀN KHO
    tu_ngay: date
    den_ngay: date
    hanh_dong: str = Field(default="khoa", pattern="^(khoa|mo)$")
    ten: str | None = Field(default=None, max_length=120)   # tên kỳ (chỉ khi 'khoa')

    @model_validator(mode="after")
    def _check_range(self):
        if self.den_ngay < self.tu_ngay:
            raise ValueError("Ngày đến phải lớn hơn hoặc bằng ngày từ.")
        return self


class KhoKhoaSoRow(BaseModel):
    id: int
    kho_id: int | None = None
    kho_ten: str | None = None            # None khi kho_id None = "Toàn kho"
    tu_ngay: date
    den_ngay: date
    hanh_dong: str                        # 'khoa' | 'mo'
    nguoi_khoa_ten: str | None = None
    khoa_luc: datetime | None = None
    ten: str | None = None                # tên kỳ (nếu có)


class KhoaSoKyRow(BaseModel):
    """1 kỳ CÒN đang khóa (đã gộp khoảng liền mạch) — cho tab 'Kỳ đã khóa' chọn nhanh + xuất."""
    kho_id: int | None = None             # None = Toàn kho
    kho_ten: str | None = None
    tu_ngay: date
    den_ngay: date
    khoa_luc: datetime | None = None      # thời điểm khóa quyết định tại ngày đầu kỳ
    ten: str | None = None                # tên kỳ (từ bản ghi 'khoa' quyết định)


class StockVoucherCancel(BaseModel):
    """Body khi HỦY phiếu nháp — BẮT BUỘC lý do; yêu cầu chuyển 'Đã hủy' kèm lý do này."""

    ly_do: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _strip(self) -> "StockVoucherCancel":
        self.ly_do = self.ly_do.strip()
        if not self.ly_do:
            raise ValueError("Phải nhập lý do hủy.")
        return self


# --- Phiếu -------------------------------------------------------------------

class StockVoucherLineIn(BaseModel):
    # Mặt hàng KẾ THỪA từ dòng đề nghị (kho không đổi được), nên phiếu chỉ gửi `request_line_id`.
    # Bỏ `material_id` + cụm `new_*`: đường "kho tạo hàng mới lúc lập phiếu" đã đóng (siết).
    request_line_id: int
    so_luong: float = Field(gt=0)
    # Phiếu NHẬP: giá của lô sắp tạo. Phiếu XUẤT: bỏ qua (giá lấy từ lô).
    don_gia: int | None = Field(default=None, ge=0)
    # Phiếu XUẤT: bắt buộc. Phiếu NHẬP: bỏ qua (lô sinh ra lúc ghi sổ).
    lot_id: int | None = None
    # Lý do cấp/nhập THIẾU (khi SL < còn phải cấp) — bắt buộc nếu thiếu; ghi vào yêu cầu (kho phản hồi).
    ly_do: str | None = Field(default=None, max_length=500)
    ghi_chu: str | None = Field(default=None, max_length=500)
    # Phiếu NHẬP: vị trí cất lô trong kho (kệ/ô) — thủ kho khai; ghi sổ chép sang lô.
    vi_tri: str | None = Field(default=None, max_length=100)


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
    hang_loai: str
    hang_id: int
    hang_ma: str | None = None
    hang_ten: str | None = None
    dvt: str | None = None
    lot_id: int | None = None
    ma_lo: str | None = None
    # SL người yêu cầu XIN trên dòng yêu cầu gốc (đọc-nối từ StockRequestLine, không lưu cột).
    # Để phiếu đối chiếu "yêu cầu vs thực nhận/xuất". None nếu không nối được dòng yêu cầu.
    sl_de_nghi: float | None = None
    so_luong: float
    # Số đã quy về đơn vị gốc (số thật sự chạy vào lô) + đơn vị đó — để bản in và màn phiếu nói rõ
    # "10 ram (= 419,25 kg)" thay vì để người đọc tự đoán con số nào vào tồn.
    sl_goc: float | None = None
    don_vi_goc: str | None = None
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
    # Loại phiếu (tự do) người tạo gõ ở YÊU CẦU — hiện trên phiếu + list; Báo cáo kho dùng export.
    loai_kho: str | None = None
    kho_id: int
    kho_ten: str | None = None
    ngay: date
    nguoi_lap_id: int
    nguoi_lap_ten: str | None = None
    # Chuỗi trách nhiệm lấy từ YÊU CẦU gốc: ai yêu cầu · ai duyệt (phiếu tự nó không có bước duyệt).
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

class StockLotViTriIn(BaseModel):
    """Sửa vị trí cất lô (kệ/ô) trong kho."""

    vi_tri: str | None = Field(default=None, max_length=100)


class StockLotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma_lo: str
    hang_loai: str
    hang_id: int
    hang_ma: str | None = None
    hang_ten: str | None = None
    # ĐƠN VỊ GỐC của mặt hàng — `sl_ban_dau`/`sl_con_lai` của lô đều theo đơn vị này.
    dvt: str | None = None
    kho_id: int
    vi_tri: str | None = None
    ngay_nhap: date
    ncc: str | None = None
    sl_ban_dau: float
    sl_con_lai: float
    hsd: date | None = None
    trang_thai: str
    # Phiếu NHẬP đã tạo ra lô này — màn Tồn kho hiển thị lô THEO MÃ PHIẾU (link mở phiếu). Null = đầu kỳ.
    voucher_id: int | None = None
    voucher_ma: str | None = None
    # Giá vốn của lô — chỉ có khi `can_view_cost`. Thủ kho chọn lô mà không thấy giá.
    don_gia_nhap: int | None = None
    # SL yêu cầu đã sinh ra lô (đọc-nối qua dòng phiếu NHẬP tạo lô → dòng yêu cầu). Không lưu cột.
    # Không phải tiền → luôn hiện được. None = lô đầu kỳ / không nối được dòng yêu cầu.
    sl_de_nghi: float | None = None


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
    # SL yêu cầu đã sinh ra dòng xuất (đọc-nối qua dòng phiếu XUẤT → dòng yêu cầu). Không lưu cột.
    sl_de_nghi: float | None = None
    so_luong: float
    # Giá vốn ĐÍCH DANH của lô đã xuất — router XÓA khi thiếu `can_view_cost`.
    don_gia: int | None = None


class MaterialHistoryOut(BaseModel):
    """Lịch sử 1 mã hàng tại 1 kho: NHẬP = các lô (kể cả đã hết) · XUẤT = dòng phiếu xuất."""

    hang_loai: str
    hang_id: int
    hang_ma: str | None = None
    hang_ten: str | None = None
    dvt: str | None = None
    on_hand: float
    nhap: list[StockLotOut] = []
    xuat: list[MaterialXuatRow] = []


# --- Tra kho CÔNG KHAI (quét tem QR, không đăng nhập) -------------------------
# TUYỆT ĐỐI không có trường tiền (giá vốn/đơn giá): trang này ai có link cũng xem được.

class PublicScanLot(BaseModel):
    ma_lo: str | None = None
    ngay_nhap: date
    hsd: date | None = None
    vi_tri: str | None = None
    sl_con_lai: float


class PublicScanMove(BaseModel):
    """1 lần nhập/xuất gần đây (công khai — TUYỆT ĐỐI KHÔNG có tiền)."""

    loai: str              # NHAP / XUAT
    ngay: date | None = None
    so_ct: str
    so_luong: float


class PublicScanOut(BaseModel):
    """Dữ liệu tra kho công khai: tên vật tư · ĐVT · kho · tổng tồn · vị trí · lịch sử nhập/xuất."""

    material_code: str | None = None
    material_name: str | None = None
    dvt: str | None = None
    kho_ten: str | None = None
    on_hand: float
    lots: list[PublicScanLot] = []
    history: list[PublicScanMove] = []


# --- Ngưỡng tồn ---------------------------------------------------------------

class StockThresholdIn(BaseModel):
    hang_loai: str = Field(pattern="^(giay|vat_tu)$")
    hang_id: int = Field(gt=0)
    kho_id: int
    nguong_ton: float = Field(ge=0)
    # Bỏ trống → service suy ra = nguong_ton × 1.3 (spec §7).
    nguong_can_ton: float | None = Field(default=None, ge=0)
    nguong_toi_da: float | None = Field(default=None, ge=0)
    canh_bao: bool = True


class StockThresholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hang_loai: str
    hang_id: int
    hang_ma: str | None = None
    hang_ten: str | None = None
    kho_id: int
    nguong_ton: float
    nguong_can_ton: float | None = None
    nguong_toi_da: float | None = None
    canh_bao: bool


class StockLevelOut(BaseModel):
    """Mức tồn của 1 mã hàng. `ton_kha_dung` chỉ có khi `can_view_stock` — thiếu quyền thì
    người dùng vẫn thấy `muc_ton` (đèn 5 màu) để biết sắp hết mà không biết còn bao nhiêu."""

    hang_loai: str
    hang_id: int
    muc_ton: str
    ton_kha_dung: float | None = None


# GỠ 2026-08-08: `StockMaterialCreate` + `StockMaterialQuyDoi` — hai cửa cho kho tự đẻ mặt
# hàng và tự khai quy đổi cho từng dòng. Nay mặt hàng phải có sẵn trong danh mục Giấy / Vật
# tư khác, còn quy đổi lấy từ đồ thị đơn vị dùng chung.
