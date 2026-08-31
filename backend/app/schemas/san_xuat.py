"""Schema mặt ĐỌC của module Thực hiện sản xuất (Giai đoạn 2 — bàn tổ).

Chỉ khai phần đang dùng: danh sách tổ + badge, và công việc đã phát hành của một tổ. Service trả
dict nên các schema này chỉ để `response_model` khoá hình dạng ra FE (Pydantic nuốt field lạ IM
LẶNG — thêm field ở service phải thêm ở đây, xem [[pydantic-nuot-field-im-lang]])."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class TeamOut(BaseModel):
    id: int
    ten: str
    ma: str
    la_kcs: bool
    so_viec_cho: int
    # Task 4 (mg 0250) — badge/cổng cho board KCS kiêm nhiệm, đọc theo `SanXuatCongViec.la_kcs`
    # (cấp CÔNG VIỆC), KHÁC `la_kcs` phía trên (đó là `Department.is_kcs`, cấp TỔ).
    so_viec_kcs_cho: int
    co_viec_kcs: bool


class TeamsOut(BaseModel):
    teams: list[TeamOut]


class ThucTeKhoangOut(BaseModel):
    """Một phiên chạy THỰC TẾ (§7.2) để vẽ lớp thực-tế đè lên thanh kế hoạch (§5.1). `ket_thuc=None`
    = phiên còn mở (đang chạy) → FE kéo tới "bây giờ"."""
    bat_dau: datetime
    ket_thuc: datetime | None = None


class VatTuDinhMucOut(BaseModel):
    """Một dòng định mức vật tư của bước — đóng băng lúc phát hành (`vat_tu_json`), KHÁC "vật tư"
    ở drawer (đó là phiếu XUẤT đã cấp cho cả LSX, không phải định mức theo bước)."""
    vat_tu_id: int | None = None
    ma: str | None = None
    ten: str | None = None
    don_vi: str | None = None
    so_luong: float | None = None


class WorkItemOut(BaseModel):
    id: int
    goi_id: int
    phien_ban_so: int
    nguon_loai: str          # "lsx" | "bai_ghep" | ""
    nguon_ma: str
    nguon_ten: str
    nhom_id: int | None = None   # id nhóm thành phẩm (khoá cho panel Kho §14 + checklist đóng §16)
    nhom: str                # nhãn nhóm thành phẩm
    ten_cong_doan: str
    nhom_cong_doan: str | None = None
    loai_buoc: str
    la_kcs: bool
    la_kcs_cuoi: bool
    may: str
    du_kien_bat_dau: datetime | None = None
    du_kien_ket_thuc: datetime | None = None
    du_kien_so_nguoi: int | None = None      # số người dự kiến (§7.1) — so với roster để đòi lý do lệch
    so_luong_vao: float | None = None
    so_luong_ra: float | None = None
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    trang_thai: str
    # Định mức vật tư đóng băng lúc phát hành (view "Danh sách") — đọc thẳng `vat_tu_json`.
    dinh_muc_vat_tu: list[VatTuDinhMucOut] = []
    # Lớp thực-tế đè lên thanh kế hoạch (§5.1): các phiên chạy đã ghi, phiên mở để ket_thuc=None.
    thuc_te: list[ThucTeKhoangOut] = []


class WorkItemsOut(BaseModel):
    team_id: int
    cong_viec: list[WorkItemOut]


class NhanVienChonOut(BaseModel):
    """Một người chọn được cho ô "Giao người" (§7.1). `la_luong_khoan` để FE lọc bước nội bộ."""
    id: int
    code: str | None = None
    full_name: str
    la_luong_khoan: bool
    co_tai_khoan: bool


class NhanVienChonListOut(BaseModel):
    team_id: int
    nhan_vien: list[NhanVienChonOut]


class HoTroUngVienOut(BaseModel):
    """Một thợ tổ KHÁC có thể mời hỗ trợ chéo (§9) — kèm nhãn tổ gốc."""
    id: int
    code: str | None = None
    full_name: str
    to_id: int | None = None
    to_ten: str | None = None


class HoTroUngVienListOut(BaseModel):
    team_id: int
    nhan_vien: list[HoTroUngVienOut]


# --- Mặt GHI: phân công / phiên chạy (Giai đoạn 2, §7) ---------------------------------------
class PhanCongIn(BaseModel):
    employee_id: int
    expected_version: int | None = None


class GoPhanCongIn(BaseModel):
    ly_do: str | None = None
    expected_version: int | None = None


class BatDauIn(BaseModel):
    ly_do_tre: str | None = None       # bắt buộc khi bắt đầu TRỄ (§7.2)
    ly_do_so_nguoi: str | None = None  # bắt buộc khi số người thực tế ≠ dự kiến (§7.1)
    expected_version: int | None = None


class TamDungIn(BaseModel):
    ly_do: str                          # bắt buộc (§7.2)
    expected_version: int | None = None


class KetThucIn(BaseModel):
    ly_do_tre: str | None = None       # cần khi trễ mà chưa có lý do tạm dừng (§7.2)
    expected_version: int | None = None


class LenhKetQuaOut(BaseModel):
    """Kết quả một lệnh ghi — đủ để FE cập nhật thanh + version lạc quan."""
    cong_viec_id: int
    department_id: int | None = None
    trang_thai: str
    version: int


# --- Drawer chi tiết: roster + phiên + khoảng tham gia --------------------------------------
class PhanCongItemOut(BaseModel):
    id: int
    employee_id: int
    ho_ten: str
    la_luong_khoan: bool
    co_tai_khoan: bool
    trang_thai: str


class PhienChayOut(BaseModel):
    id: int
    so_thu_tu: int
    bat_dau: datetime
    ket_thuc: datetime | None = None
    loai_dong: str | None = None
    ly_do_bat_dau_tre: str | None = None
    ly_do: str | None = None


class KhoangThamGiaOut(BaseModel):
    id: int
    phien_chay_id: int
    employee_id: int
    ho_ten: str
    bat_dau: datetime
    ket_thuc: datetime | None = None


# --- Sản lượng · bàn giao · vật tư trên drawer (Giai đoạn 3) --------------------------------
class LotVaoOut(BaseModel):
    id: int
    nguon_loai: str                     # "batch" | "kho_lot"
    nguon_batch_id: int | None = None
    nguon_lot_id: int | None = None
    so_luong: float
    don_vi: str


class NguoiThamGiaBatchOut(BaseModel):
    employee_id: int
    ho_ten: str


class BatchOut(BaseModel):
    id: int
    bat_dau: datetime
    ket_thuc: datetime
    tong: float
    tot: float
    hong: float
    don_vi: str
    nhom_loi_id: int | None = None
    nhom_loi_ten: str | None = None
    mo_ta_loi: str | None = None
    ghi_chu: str | None = None
    version: int
    nguoi_tham_gia: list[NguoiThamGiaBatchOut]
    lot_vao: list[LotVaoOut]


class SanLuongOut(BaseModel):
    tong_tot: float
    da_giao: float
    batches: list[BatchOut]


class BanGiaoOut(BaseModel):
    """Một dòng bàn giao trên drawer — `doi_tac_*` là công đoạn ở đầu kia (đích khi giao đi, nguồn
    khi nhận về)."""
    id: int
    doi_tac_cong_viec_id: int | None = None
    doi_tac_ten: str
    cung_to: bool
    so_luong: float
    don_vi: str
    trang_thai: str                     # proposed | confirmed | adjusted
    khong_nhat_quan: bool
    version: int


class BanGiaoDichGoiYOut(BaseModel):
    """Gợi ý ĐÍCH khi tạo bàn giao — chặng sau cùng gói/LSX (§11.2). Ngoài danh sách này, tổ
    trưởng vẫn được chọn "giao ra ngoài" (đích trống)."""
    cong_viec_id: int
    ten_cong_doan: str
    to_id: int | None = None
    to_ten: str | None = None
    du_kien_bat_dau: datetime | None = None


class VatTuNhanOut(BaseModel):
    voucher_id: int
    ma: str
    da_nhan: bool
    xac_nhan_luc: datetime | None = None


class HoTroChiTietOut(BaseModel):
    """Một thỏa thuận hỗ trợ chéo hiển thị trên drawer (§9)."""
    id: int
    employee_id: int
    ho_ten: str
    to_goc_id: int | None = None
    to_goc_ten: str | None = None
    to_thuc_hien_id: int | None = None
    to_thuc_hien_ten: str | None = None
    ngay_lam_viec: date
    ty_le_phan_tram: float
    trang_thai: str                      # pending_both | confirmed | cancelled
    mo_ta: str | None = None
    da_xac_nhan_goc: bool
    da_xac_nhan_thuc_hien: bool
    version: int


class PhanBoDongOut(BaseModel):
    """Một dòng phân bổ theo người (§12.2)."""
    employee_id: int
    ho_ten: str
    department_id: int | None = None
    la_ho_tro: bool
    ngay: date
    so_luong_tra_luong: float
    so_luong_ban_dia: float | None = None
    trong_so: float | None = None
    phut_thuc_te: float | None = None
    he_so_bac: float | None = None
    don_gia: float


class BuTruDongOut(BaseModel):
    id: int
    employee_id: int
    ho_ten: str
    so_luong_tra_luong: float
    don_gia: float
    ky_bu_nam: int
    ky_bu_thang: int
    mo_ta: str | None = None


class LoaiTruDongOut(BaseModel):
    """Một người bị loại khỏi lương batch (§7.3) — để FE hiện + cho gỡ."""
    employee_id: int
    ho_ten: str
    ly_do: str


class PhanBoChiTietOut(BaseModel):
    """Header phân bổ MỘT batch + bảng chia theo người + dòng bù trừ (§12)."""
    phan_bo_id: int
    batch_id: int
    trang_thai: str                      # draft | finalized | reopened
    version: int
    ngay: date
    ky_nam: int
    ky_thang: int
    q_tra_luong: float
    don_vi_tra_luong: str | None = None
    don_gia: float
    q_ban_dia: float | None = None
    don_vi_ban_dia: str | None = None
    tong_ty_le_ho_tro: float
    can_chot: bool = True
    canh_bao: list[str] = []
    thieu_cham_cong: list[int] = []      # employee_id thiếu chấm công hợp lệ (§7.3)
    loai_tru: list[LoaiTruDongOut] = []
    dong: list[PhanBoDongOut]
    bu_tru: list[BuTruDongOut]


class WorkItemChiTietOut(BaseModel):
    cong_viec: WorkItemOut
    trang_thai: str
    version: int
    phan_cong: list[PhanCongItemOut]
    phien_chay: list[PhienChayOut]
    khoang_tham_gia: list[KhoangThamGiaOut]
    san_luong: SanLuongOut
    ban_giao_di: list[BanGiaoOut]
    ban_giao_den: list[BanGiaoOut]
    ban_giao_goi_y: list[BanGiaoDichGoiYOut]
    vat_tu: list[VatTuNhanOut]
    ho_tro: list[HoTroChiTietOut]
    phan_bo: list[PhanBoChiTietOut]


# --- Mặt GHI: sản lượng · bàn giao · vật tư (Giai đoạn 3, §10–§11) ---------------------------
class LotVaoIn(BaseModel):
    nguon_loai: str = "batch"           # "batch" (lot công đoạn trước) | "kho_lot" (BTP kho)
    nguon_batch_id: int | None = None
    nguon_lot_id: int | None = None
    so_luong: float
    don_vi: str | None = None           # trống ⇒ đơn vị vào của công việc


class BatchIn(BaseModel):
    bat_dau: datetime
    ket_thuc: datetime
    tong: float
    tot: float
    hong: float = 0
    don_vi: str | None = None           # trống ⇒ đơn vị ra của công việc
    nhom_loi_id: int | None = None      # bắt buộc khi hong > 0 (nhóm `loi`)
    mo_ta_loi: str | None = None
    ghi_chu: str | None = None
    lot_vao: list[LotVaoIn] = []


class ThemLotIn(BaseModel):
    nguon_loai: str = "batch"
    nguon_batch_id: int | None = None
    nguon_lot_id: int | None = None
    so_luong: float
    don_vi: str | None = None


class KetQuaNhanhOut(BaseModel):
    lsx_id: int
    so_luong: float
    don_vi: str
    ban_giao_id: int | None = None


class SanLuongKetQuaOut(BaseModel):
    cong_viec_id: int
    department_id: int | None = None
    trang_thai: str
    version: int
    batch_id: int | None = None
    ket_qua_lsx: list[KetQuaNhanhOut] = []


class BanGiaoDeXuatIn(BaseModel):
    dich_cong_viec_id: int | None = None  # None = giao ra ngoài (nhập kho BTP, pha sau)
    so_luong: float
    don_vi: str | None = None


class BanGiaoSuaIn(BaseModel):
    so_luong: float
    expected_version: int | None = None


class BanGiaoXacNhanIn(BaseModel):
    expected_version: int | None = None


class BanGiaoDieuChinhIn(BaseModel):
    so_luong_sau: float
    ly_do_id: int                        # bắt buộc, nhóm `dieu_chinh_ban_giao`
    mo_ta: str | None = None
    expected_version: int | None = None


class BanGiaoKetQuaOut(BaseModel):
    ban_giao_id: int
    trang_thai_ban_giao: str
    so_luong: float
    khong_nhat_quan: bool
    version: int
    nguon_cong_viec_id: int
    dich_cong_viec_id: int | None = None
    nguon_department_id: int | None = None
    dich_department_id: int | None = None


class VatTuXacNhanIn(BaseModel):
    voucher_id: int
    department_id: int
    ghi_chu: str | None = None


class VatTuNhanKetQuaOut(BaseModel):
    voucher_id: int
    department_id: int


# --- Hỗ trợ chéo giữa hai tổ (Giai đoạn 4, §9) ----------------------------------------------
class HoTroDeXuatIn(BaseModel):
    employee_id: int
    ngay_lam_viec: date
    ty_le_phan_tram: float               # % do người NHẬP (§9.1) — không mặc định, không giới hạn 7%
    mo_ta: str | None = None


class HoTroXacNhanIn(BaseModel):
    expected_version: int | None = None


class HoTroHuyIn(BaseModel):
    ly_do: str | None = None
    expected_version: int | None = None


class HoTroKetQuaOut(BaseModel):
    """Kết quả một lệnh thỏa thuận hỗ trợ. `notify_user_ids` = cả hai tổ trưởng liên quan (§18 SSE)."""
    ho_tro_id: int
    cong_viec_id: int
    to_goc_id: int | None = None
    to_thuc_hien_id: int | None = None
    trang_thai: str                      # pending_both | confirmed | cancelled
    notify_user_ids: list[int]


# --- Phân bổ sản lượng → lương khoán theo người (Giai đoạn 4, §12) --------------------------
class PhanBoChotIn(BaseModel):
    expected_version: int | None = None


class PhanBoMoLaiIn(BaseModel):
    ly_do_id: int                        # bắt buộc, nhóm `mo_lai_phan_bo`
    expected_version: int | None = None


class PhanBoTomTatOut(BaseModel):
    """Kết quả tính/chốt phân bổ — đủ để FE dựng bảng chia + cờ chặn chốt + cảnh báo."""
    phan_bo_id: int
    batch_id: int
    cong_viec_id: int
    department_id: int | None = None
    trang_thai: str                      # draft | finalized | reopened
    version: int
    q_tra_luong: float
    tong_ty_le_ho_tro: float
    so_dong: int
    can_chot: bool
    canh_bao: list[str]
    thieu_cham_cong: list[int] = []      # employee_id tham gia nhưng 0 phút chấm công hợp lệ (§7.3)
    loai_tru: list[int] = []             # employee_id đã bị loại khỏi lương batch (§7.3)


class LoaiTruIn(BaseModel):
    employee_id: int
    ly_do: str                           # bắt buộc — vì sao loại người này khỏi lương batch


class GoLoaiTruIn(BaseModel):
    employee_id: int                     # gỡ loại trừ không cần lý do


class LoaiTruKetQuaOut(BaseModel):
    """Kết quả loại/gỡ-loại người khỏi lương batch (§7.3). Nếu đã có bản nháp thì kèm bảng chia mới;
    chưa tính lần nào thì chỉ trả danh sách loại trừ hiện tại."""
    phan_bo_id: int | None = None
    batch_id: int
    cong_viec_id: int | None = None
    department_id: int | None = None
    trang_thai: str | None = None
    version: int | None = None
    q_tra_luong: float | None = None
    tong_ty_le_ho_tro: float | None = None
    so_dong: int | None = None
    can_chot: bool | None = None
    canh_bao: list[str] = []
    thieu_cham_cong: list[int] = []
    loai_tru: list[int] = []


class PhanBoTrangThaiOut(BaseModel):
    """Kết quả đổi trạng thái phân bổ (mở lại) — không kèm bảng chia."""
    phan_bo_id: int
    batch_id: int
    cong_viec_id: int
    department_id: int | None = None
    trang_thai: str
    version: int


class BuTruIn(BaseModel):
    employee_id: int
    so_luong_tra_luong: float            # chênh lệch, có thể âm
    ky_bu_nam: int
    ky_bu_thang: int
    ly_do_id: int                        # bắt buộc, nhóm `mo_lai_phan_bo`
    mo_ta: str | None = None


class BuTruKetQuaOut(BaseModel):
    bu_tru_id: int
    batch_id: int
    cong_viec_id: int
    department_id: int | None = None
    employee_id: int
    so_luong_tra_luong: float
    ky_bu: list[int]


# --- KCS: batch kiểm tra · lỗi · phản hồi trách nhiệm (Giai đoạn 5, §13) ---------------------
class KcsBatchIn(BaseModel):
    """Ghi một batch kiểm tra KCS (§13.1). `so_luong_nhan = dat + khong_dat` (service kiểm)."""
    bat_dau: datetime
    ket_thuc: datetime
    so_luong_nhan: float
    so_luong_dat: float
    so_luong_khong_dat: float = 0
    co_mau: float | None = None          # cỡ mẫu kiểm (≤ số nhận); trống ⇒ không ghi
    don_vi: str | None = None            # trống ⇒ đơn vị ra của công việc
    ghi_chu: str | None = None


class KcsBatchKetQuaOut(BaseModel):
    cong_viec_id: int
    department_id: int | None = None
    nhom_id: int | None = None
    kcs_batch_id: int
    batch_id: int | None = None          # batch sản lượng nền cho phân bổ năng suất KCS (§13.1)
    version: int


class KcsLoiKetQuaOut(BaseModel):
    """Kết quả ghi lỗi KCS (§13.2). `to_chiu_head_user_id` KHÔNG phơi ra FE — router dùng nó để đẩy
    SSE tới tổ trưởng phụ trách rồi Pydantic tự nuốt (không khai ở đây là cố ý)."""
    loi_id: int
    kcs_batch_id: int
    cong_viec_id: int
    to_chiu_id: int | None = None
    trang_thai: str                      # pending | accepted | rejected
    version: int


class KcsAnhThemKetQuaOut(BaseModel):
    loi_id: int
    so_anh: int


class KcsPhanHoiLoiIn(BaseModel):
    chap_nhan: bool                      # True = nhận trách nhiệm, False = từ chối (bắt buộc lý do)
    ly_do_tu_choi: str | None = None
    expected_version: int | None = None


class KcsPhanHoiKetQuaOut(BaseModel):
    loi_id: int
    trang_thai: str
    kcs_batch_id: int
    cong_viec_id: int | None = None
    version: int


class KcsAnhOut(BaseModel):
    id: int
    file_name: str
    file_url: str
    file_type: str | None = None


class KcsLoiOut(BaseModel):
    id: int
    kcs_batch_id: int
    nhom_loi_id: int | None = None
    nhom_loi_ten: str | None = None
    mo_ta: str | None = None
    to_chiu_id: int | None = None
    cong_doan_ref_id: int | None = None
    so_luong: float
    don_vi: str | None = None
    trang_thai: str                      # pending | accepted | rejected
    ly_do_tu_choi: str | None = None
    phan_hoi_luc: datetime | None = None
    version: int
    anh: list[KcsAnhOut]


class KcsBatchChiTietOut(BaseModel):
    id: int
    batch_id: int | None = None
    nhom_id: int | None = None
    bat_dau: datetime
    ket_thuc: datetime
    so_luong_nhan: float
    co_mau: float | None = None
    so_luong_dat: float
    so_luong_khong_dat: float
    don_vi: str
    ket_luan: str                        # dat | dat_mot_phan | khong_dat
    ghi_chu: str | None = None
    version: int
    loi: list[KcsLoiOut]


class KcsChiTietOut(BaseModel):
    cong_viec_id: int
    la_kcs: bool
    batch: list[KcsBatchChiTietOut]


class KcsHopThuOut(BaseModel):
    """Hộp thư lỗi KCS chờ tổ của user phản hồi (§13.2)."""
    loi: list[KcsLoiOut]


# --- KHO SẢN XUẤT (§14) ---------------------------------------------------------------------
class NhapKhoYeuCauIn(BaseModel):
    """KCS tạo yêu cầu nhập kho thành phẩm một phần từ một batch ĐẠT (§14.1)."""
    kcs_batch_id: int
    so_luong: float
    quy_cach: str | None = None
    ghi_chu: str | None = None


class KhoXacNhanNhapIn(BaseModel):
    """Kho xác nhận nhận một phần yêu cầu (§14.1)."""
    so_luong: float
    expected_version: int | None = None


class HuyPhanChuaNhanIn(BaseModel):
    expected_version: int | None = None


class NhapKhoYcKetQuaOut(BaseModel):
    """Kết quả tạo/đổi yêu cầu nhập kho. `nguoi_tao_id` KHÔNG phơi FE — router dùng để đẩy SSE tới
    người ghi KCS rồi Pydantic tự nuốt (không khai ở đây là cố ý)."""
    yc_id: int
    kcs_batch_id: int
    nhom_id: int | None = None
    trang_thai: str                      # cho_kho | nhap_mot_phan | da_nhap | huy
    version: int


class KhoXacNhanNhapKetQuaOut(BaseModel):
    yc_id: int
    lot_id: int
    kcs_batch_id: int
    nhom_id: int | None = None
    trang_thai: str
    so_luong_xac_nhan: float
    version: int


class PhanLoaiBtpIn(BaseModel):
    """Phân loại BTP dư của một công việc trước khi đóng nhóm (§14.2)."""
    cong_viec_id: int
    so_luong: float
    phan_loai: str                       # nhap_btp | mau_luu | phe
    quy_cach: str | None = None
    nguon_batch_id: int | None = None
    ghi_chu: str | None = None


class PhanLoaiBtpKetQuaOut(BaseModel):
    lot_id: int
    hang_id: int
    cong_viec_id: int
    nhom_id: int | None = None
    phan_loai: str
    cho_kho: bool                        # còn chờ kho xác nhận nhận (nhap_btp) hay chung cục ngay


class KhoXacNhanBtpKetQuaOut(BaseModel):
    lot_id: int
    nhom_id: int | None = None
    cong_viec_id: int | None = None


class NhapKhoYcOut(BaseModel):
    id: int
    kcs_batch_id: int
    hang_id: int | None = None
    nhom_id: int | None = None
    order_id: int | None = None
    so_luong_yeu_cau: float
    so_luong_xac_nhan: float
    con_lai: float
    don_vi: str
    quy_cach: str | None = None
    trang_thai: str
    ghi_chu: str | None = None
    version: int


class KhoLotOut(BaseModel):
    id: int
    hang_id: int
    loai_hang: str                       # btp | thanh_pham
    nhom_id: int | None = None
    lsx_id: int | None = None
    cong_doan_ref_id: int | None = None
    kcs_batch_id: int | None = None
    so_luong: float
    don_vi: str
    phan_loai: str | None = None         # BTP dư: nhap_btp | mau_luu | phe
    kho_xac_nhan: bool
    quy_cach: str | None = None
    ghi_chu: str | None = None


class KhoChiTietOut(BaseModel):
    """Toàn cảnh kho của một nhóm thành phẩm (panel §14)."""
    nhom_id: int
    yeu_cau: list[NhapKhoYcOut]
    lot: list[KhoLotOut]
    btp_tra_cho_kho: list[KhoLotOut]     # BTP nhap_btp còn chờ kho xác nhận (chặn đóng nhóm §16)


class KhoHopThuOut(BaseModel):
    """Hộp thư nhân viên kho: mọi việc còn chờ kho hành động (§14, §17)."""
    yeu_cau_nhap: list[NhapKhoYcOut]     # yêu cầu nhập kho thành phẩm chờ/một phần
    btp_cho_nhan: list[KhoLotOut]        # BTP nhap_btp chờ kho xác nhận nhận


# --- ĐÓNG NHÓM THÀNH PHẨM (§16 tự đóng đủ · §13.3 đóng thiếu) -------------------------------
class DongNhomDieuKienItemOut(BaseModel):
    """Một điều kiện của cổng đóng nhóm — FE dựng checklist "vì sao chưa đóng"."""
    ma: str
    ten: str
    dat: bool
    chi_tiet: str = ""


class DongNhomDieuKienOut(BaseModel):
    """Tình trạng cổng đóng nhóm: đủ đóng-đủ chưa, đủ đóng-thiếu chưa, và từng điều kiện."""
    nhom_id: int
    order_id: int | None = None
    trang_thai: str
    version: int
    du_dong_du: bool
    du_dong_thieu: bool
    dieu_kien: list[DongNhomDieuKienItemOut]


class DongThieuIn(BaseModel):
    """Trưởng KCS đóng thiếu nhóm còn dở (§13.3): bắt buộc lý do nhóm `dong_thieu`."""
    ly_do_id: int
    expected_version: int | None = None


class DongNhomKetQuaOut(BaseModel):
    nhom_id: int
    order_id: int | None = None
    trang_thai: str
    kieu: str                            # du | thieu
    ly_do_id: int | None = None
    version: int
