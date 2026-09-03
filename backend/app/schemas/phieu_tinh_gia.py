"""Pydantic schemas — Phiếu tính giá THEO THÀNH PHẦN (component-based costing).

Cây lồng: Phiếu → thanh_phans[] (thành phần / tờ giấy) → thanh_phams[] (dòng gia công sau in).
`PhieuTinhGiaOut` map `result_json → result`, `warnings_json → warnings`. Mọi trường đầu vào
optional (cho phép tạo nháp trắng / thành phần thiếu). SAVE = engine tính lại + ảnh chụp.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# ============================ THÀNH PHẨM (finishing op) ============================
class ThanhPhamIn(BaseModel):
    """1 dòng gia công sau in (đầu vào — mọi trường optional)."""
    thu_tu: int | None = None
    cong_doan_id: int | None = None
    ten: str | None = None
    don_gia: float | None = None
    so_luong: int | None = Field(default=None, ge=0)
    bu_hao: bool | None = None
    so_mat: int | None = None
    so_vi_tri: int | None = None
    dien_tich: float | None = None
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None
    # Phí làm khuôn của CHÍNH bước này — MỘT LẦN, không nhân SL. 0 = dùng lại dao cũ.
    phi_khuon: float | None = Field(default=None, ge=0)
    # Khuôn có sẵn hay làm mới (`co_san`/`lam_moi`) + ngày sale dự kiến có dao. None = chưa chọn.
    khuon_nguon: str | None = None
    khuon_ngay_du_kien: date | None = None
    # Kích thước/số lượng khung lụa — TÁCH BIỆT với `phi_khuon`, chỉ ăn vào công thức của công đoạn.
    dai_khung_lua: float | None = Field(default=None, ge=0)
    rong_khung_lua: float | None = Field(default=None, ge=0)
    so_khung_lua: int | None = Field(default=None, ge=0)


class ThanhPhamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thanh_phan_id: int
    thu_tu: int
    cong_doan_id: int | None = None
    ten: str
    don_gia: float
    so_luong: int
    bu_hao: bool
    so_mat: int
    so_vi_tri: int
    dien_tich: float
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None
    phi_khuon: float = 0
    khuon_nguon: str | None = None
    khuon_ngay_du_kien: date | None = None
    dai_khung_lua: float = 0
    rong_khung_lua: float = 0
    so_khung_lua: int = 0


# ============================ SẢN PHẨM TÁI BẢN (docs/spec-san-pham-tai-ban.md) ============================
class SanPhamTaiBanGoiY(BaseModel):
    """1 dòng gợi ý tìm sản phẩm tái bản — nhẹ, chỉ đủ hiển thị danh sách chọn."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ten: str
    updated_at: datetime


# ============================ VẬT TƯ (nguyên vật liệu thêm) ============================
class VatTuLineIn(BaseModel):
    """1 dòng vật tư in ấn thêm tay (đầu vào — mọi trường optional)."""
    thu_tu: int | None = None
    vat_tu_id: int | None = None
    ten: str | None = None
    don_gia: float | None = None
    so_luong: int | None = Field(default=None, ge=0)
    ghi_chu: str | None = None


class VatTuLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thanh_phan_id: int
    thu_tu: int
    vat_tu_id: int | None = None
    ten: str
    don_gia: float
    so_luong: int
    ghi_chu: str | None = None


# ============================ THÀNH PHẦN (paper component) ============================
class ThanhPhanIn(BaseModel):
    """1 thành phần (tờ giấy) — đầu vào (mọi trường optional)."""
    thu_tu: int | None = None
    loai_thanh_phan: str | None = None
    ten: str | None = None
    # mm — SỐ THỰC (khổ hay lẻ nửa ly: name card 88.9×50.8, letter 215.9×279.4).
    dai_thanh_pham: float | None = None
    rong_thanh_pham: float | None = None
    so_to_per_sp: int | None = Field(default=None, ge=1)   # DẪN XUẤT (engine ghi) — client gửi cũng bị đè
    so_trang: int | None = Field(default=None, ge=1)        # số trang nội dung của 1 sản phẩm
    trang_moi_tay: int | None = Field(default=None, ge=1)   # số trang mỗi tay gấp
    so_luong: int | None = Field(default=None, ge=0)   # SL của sản phẩm này
    don_vi_tinh: str | None = Field(default=None, max_length=30)   # ĐVT sản phẩm (text tự do)
    # Nhãn gộp dòng KHI IN báo giá (ruột + bìa 1 cuốn gõ giống nhau). Không vào công thức giá.
    nhom_bao_gia: str | None = Field(default=None, max_length=120)
    loai_san_pham_id: int | None = None
    # Giấy
    giay_id: int | None = None
    kho_nguyen: str | None = None
    kho_nguyen_dai: float | None = None
    kho_nguyen_rong: float | None = None
    don_gia_giay: float | None = None
    don_gia_don_vi: str | None = None
    nguon_giay: str | None = None
    chua_nhip: float | None = None
    bleed_mm: float | None = None
    khe_cat_mm: float | None = None
    # In
    co_in: bool | None = None
    che_ban_loai: str | None = None
    che_ban_don_gia: float | None = None
    quy_cach_in: str | None = None
    kho_in_dai: float | None = None
    kho_in_rong: float | None = None
    so_con: int | None = Field(default=None, ge=1)
    con_auto: bool | None = None
    may_id: int | None = None
    don_gia_cong_in: float | None = None
    # Mực in: TẬP mã mỗi mặt (`["C","M","Y","K"]`) — nguồn sự thật của số kẽm, vì tự trở dùng
    # chung một bộ bản nên kẽm là `|A ∪ B|`, không suy được từ hai con số.
    muc_a: list[str] | None = None
    muc_b: list[str] | None = None
    # Ba số màu: DẪN XUẤT, engine tính lại từ tập rồi ghi đè. Còn nhận từ client để phiếu cũ
    # (chưa có tập mực) lưu lại không mất số — đừng dựa vào chúng để tính gì.
    so_mau_a: int | None = None
    so_mau_b: int | None = None
    so_mau_pha: int | None = Field(default=None, ge=0)
    ghi_chu_ky_thuat: str | None = None   # note KỸ THUẬT/SX theo sản phẩm (canh màu/kẽm cũ/bù hao) → drawer lệnh
    # ⑤ Phí giao hàng: TỔNG tiền chở cho toàn bộ sản lượng của sản phẩm này — khoản MỘT LẦN, cộng
    # thẳng vào giá vốn (⇒ chịu markup ở Báo giá). 0 = không thu.
    phi_giao_hang: float | None = Field(default=None, ge=0)
    thanh_phams: list[ThanhPhamIn] | None = None
    vat_tus: list[VatTuLineIn] | None = None


class ThanhPhanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phieu_id: int
    thu_tu: int
    loai_thanh_phan: str
    ten: str
    dai_thanh_pham: float
    rong_thanh_pham: float
    so_to_per_sp: int
    so_trang: int = 1
    trang_moi_tay: int = 1
    so_luong: int
    don_vi_tinh: str = "cái"
    nhom_bao_gia: str | None = None
    loai_san_pham_id: int | None = None
    # Giấy
    giay_id: int | None = None
    kho_nguyen: str | None = None
    kho_nguyen_dai: float = 0
    kho_nguyen_rong: float = 0
    don_gia_giay: float
    don_gia_don_vi: str
    nguon_giay: str
    chua_nhip: float
    bleed_mm: float = 0
    khe_cat_mm: float = 0
    # In
    co_in: bool
    che_ban_loai: str | None = None
    che_ban_don_gia: float
    quy_cach_in: str
    kho_in_dai: float
    kho_in_rong: float
    so_con: int
    con_auto: bool
    may_id: int | None = None
    don_gia_cong_in: float
    # Mực in — tập mã mỗi mặt; ba số dưới là dẫn xuất engine đã chốt.
    muc_a: list[str] = Field(default_factory=list)
    muc_b: list[str] = Field(default_factory=list)
    so_mau_a: int
    so_mau_b: int
    so_mau_pha: int = 0
    ghi_chu_ky_thuat: str | None = None   # note KỸ THUẬT/SX theo sản phẩm → drawer lệnh
    phi_giao_hang: float = 0
    gia_von_tp: float
    thanh_phams: list[ThanhPhamOut] = Field(default_factory=list)
    vat_tus: list[VatTuLineOut] = Field(default_factory=list)


# ============================ PHIẾU (header) ============================
class PhieuTinhGiaCreate(BaseModel):
    """Tạo phiếu — mọi trường optional (cho phép nháp trắng)."""
    ten_san_pham: str | None = None
    kho_thanh_pham: str | None = None
    loai_san_pham_id: int | None = None
    so_luong: int | None = Field(default=None, ge=0)
    ghi_chu: str | None = None
    thanh_phans: list[ThanhPhanIn] | None = None


class PhieuTinhGiaUpdate(BaseModel):
    """Sửa phiếu — replace-all con (nếu gửi thanh_phans thì thay toàn bộ)."""
    ten_san_pham: str | None = None
    kho_thanh_pham: str | None = None
    loai_san_pham_id: int | None = None
    so_luong: int | None = Field(default=None, ge=0)
    ghi_chu: str | None = None
    thanh_phans: list[ThanhPhanIn] | None = None


class DanhMucDoi(BaseModel):
    """Danh mục đã lệch SAU lần tính gần nhất của phiếu — nuôi câu nhắc "bấm Tính giá để cập nhật".

    Chỉ là LỜI NHẮC: số tiền và tên trong phiếu vẫn giữ nguyên ảnh chụp cũ cho tới khi người lập
    phiếu chủ động bấm tính lại. Xem `services.tinh_gia_service.danh_muc_doi_sau_khi_tinh`.

    Ba rổ TÁCH RIÊNG vì việc phải làm khác nhau: `ten` sửa cấu hình (tính lại là xong) · `ngung`
    bị ngừng dùng (tính lại vẫn ra số nhưng lần sau không chọn lại được) · `xoa` đã xoá hẳn khỏi
    danh mục (dòng phiếu trỏ vào hư không, phải thay bước).
    """
    luc: datetime                                  # mốc tính gần nhất của phiếu
    ten: list[str]                                 # mục ĐỔI cấu hình/tên (công đoạn · giấy · máy · vật tư · bù hao)
    ngung: list[str] = Field(default_factory=list)  # mục bị NGỪNG DÙNG (active = false)
    xoa: list[str] = Field(default_factory=list)    # mục đã XOÁ HẲN khỏi danh mục


class PhieuTinhGiaOut(BaseModel):
    """Phiếu đầy đủ — kèm thành phần lồng + result (ảnh chụp engine) + warnings."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten_san_pham: str
    kho_thanh_pham: str | None = None
    loai_san_pham_id: int | None = None
    so_luong: int
    tong_gia_von: float
    gia_von_don: float
    result: dict | None = Field(default=None, validation_alias="result_json")
    warnings: list[str] | None = Field(default=None, validation_alias="warnings_json")
    ktv: str | None = None
    ghi_chu: str | None = None
    thanh_phans: list[ThanhPhanOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # None = phiếu còn khớp danh mục. Router gán tay (không đọc được từ ORM) — xem router GET/PUT.
    danh_muc_doi: DanhMucDoi | None = None


class PhieuTinhGiaListItem(BaseModel):
    """Dòng nhẹ cho bảng — KHÔNG kèm result_json / thành phần."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten_san_pham: str
    loai_san_pham_id: int | None = None
    kho_thanh_pham: str | None = None
    # Σ SL CÁC SẢN PHẨM bên trong phiếu — không phải ô SL mặc định ở đầu phiếu. Router tính lại
    # (xem `list_items`) để cột SL × cột giá vốn/đơn ra đúng cột tổng giá vốn.
    so_luong: int
    gia_von_don: float
    tong_gia_von: float
    ktv: str | None = None
    so_thanh_phan: int = 0
    # Tên các sản phẩm BÊN TRONG phiếu. Ô `ten_san_pham` ở đầu phiếu là chữ tự do người lập
    # gõ, bỏ trống được — bỏ trống thì bảng ngoài này chẳng biết phiếu báo cái gì. Gửi kèm
    # tên hàng bên trong để cột "Sản phẩm" có cái mà rơi về. Danh sách đã selectinload sẵn,
    # không thêm truy vấn nào.
    ten_thanh_phans: list[str] = Field(default_factory=list)
    ngay: datetime | None = Field(default=None, validation_alias="created_at")

    @field_serializer("ngay")
    def _ser_ngay(self, v: datetime | None) -> str | None:
        return v.date().isoformat() if v is not None else None


class PhieuTinhGiaListOut(BaseModel):
    items: list[PhieuTinhGiaListItem]
    total: int


class PhieuTinhGiaStatsOut(BaseModel):
    """Đếm cho thanh tab — độc lập với trang/tìm kiếm hiện tại (đúng phạm vi scope người xem)."""
    all: int
    draft: int
    calculated: int


# ============================ NHẬT KÝ HOẠT ĐỘNG ============================
class PtgActivityItem(BaseModel):
    """1 dòng nhật ký hoạt động (ai làm gì · khi nào) của 1 phiếu tính giá."""
    action: str
    actor_name: str | None = None
    detail: str
    at: datetime


class PtgActivityOut(BaseModel):
    items: list[PtgActivityItem]
