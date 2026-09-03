"""Schema ra của màn "Hồ sơ lệnh sản xuất" (Task 9).

BẪY PYDANTIC CỦA REPO — đọc trước khi thêm trường: service ở đây trả `dict`, router khai
`response_model`, nên field KHÔNG có mặt trong schema bị NUỐT IM LẶNG — không lỗi, không cảnh báo,
frontend nhận `undefined`. Thêm một trường là phải đi HẾT chuỗi: `danh_sach._dong()` → schema này →
type TS bên `frontend/src/api/client.ts`. Thiếu một mắt là mất trường mà test backend vẫn xanh.

KHÔNG MỘT SỐ TIỀN NÀO. Ràng buộc toàn cục của plan: không `don_gia` / `gia_von` / `thanh_tien` /
`luong_khoan` / `chi_phi`. Màn này cho điều độ và tổ trưởng xem — họ cần biết lệnh đang ở đâu và
có kịp không, không cần biết nó lãi bao nhiêu. Ràng buộc ấy được canh bằng
`test_khong_lo_tien`; nó chỉ có nghĩa khi schema này KHÔNG mở cửa cho các trường đó.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class LenhSxItem(BaseModel):
    """MỘT dòng bảng lệnh. Các cột đã chốt: Mã · Sản phẩm/SL · Khách · Máy · Công đoạn + tiến độ ·
    Hạn/Dự kiến · Trạng thái."""

    id: int
    ma: str
    ten: str | None = None
    khach_hang: str | None = None
    khach_hang_id: int | None = None
    sale: str | None = None

    so_luong_dat: int
    don_vi_tinh: str | None = None
    # Số đã giao THẬT (`delivery_lines.qty_delivered`), không phải số yêu cầu giao — xem
    # `BoiCanh.da_giao_cua`.
    da_giao: int = 0

    is_rush: bool = False
    buoc_hien_tai: str | None = None
    nhom_cong_doan: str | None = None
    may: str | None = None
    # Nửa "người" của cột Máy/người: TÊN những người đang được giao ở ĐÚNG bước đang hiện ở cột
    # "Máy". Danh sách chứ không phải chuỗi "A +2" dựng sẵn — nhiều người trên một bước là chuyện
    # thường (roster), cột hẹp thì UI tự cắt "+N", còn tooltip vẫn có đủ tên mà không phải gọi thêm
    # API. Thứ tự là THỨ TỰ GIAO nên cắt từ cuối là an toàn. Rỗng = bước chưa giao ai (đừng bịa).
    # Người đã bị RÚT (`trang_thai='removed'`) không có mặt ở đây — xem `BoiCanh.nguoi_cua`.
    nguoi: list[str] = []

    tien_do_pct: float
    # `True` = phần trăm đang đo bằng THỜI LƯỢNG kế hoạch vì bước chưa khai sản lượng. Bắt buộc
    # phải ra tới UI: 40% "đo được" và 40% "ước tính" là hai mức tin cậy khác hẳn nhau, gộp làm một
    # là mời điều độ ra quyết định trên con số họ tưởng chắc hơn thực tế.
    tien_do_uoc_tinh: bool = False
    gio_may: float = 0.0

    han_hoan_thanh_sx: date | None = None
    han_giao_khach: date | None = None
    du_kien_xong: datetime | None = None

    trang_thai: str
    canh_bao: list[str] = []


class LenhSxListOut(BaseModel):
    """`dem_theo_tab` là FACET của tập đã lọc (đếm TRÊN TOÀN TẬP, không phải trên trang đang xem) và
    KHÔNG bị chính `tab` đang chọn lọc lại — nếu không, bấm một tab là mọi tab khác về 0."""

    items: list[LenhSxItem]
    total: int
    page: int
    page_size: int
    dem_theo_tab: dict[str, int]


class LenhSxMayLocOut(BaseModel):
    """MỘT lựa chọn của ô lọc Máy. `so_lenh` = số LỆNH đang dính máy này trong phạm vi người gọi
    (ca in ghép phục vụ hai lệnh thì đếm hai) — để ô chọn nói luôn "chọn cái này ra bao nhiêu dòng".

    KHÔNG có trường tiền, và cũng không có cột năng lực máy (tốc độ, khổ in): đây là một ô LỌC,
    không phải cửa sổ danh mục máy — vai QC dùng màn này không có quyền `dm_thiet_bi`."""

    id: int
    ma: str | None = None
    ten: str | None = None
    so_lenh: int = 0


class LenhSxBoLocOut(BaseModel):
    """Nguồn của các ô lọc cần DANH SÁCH ĐỘNG. Hôm nay chỉ có Máy: ba ô còn lại (Nhóm công đoạn ·
    Ưu tiên · khoảng ngày) là enum/kiểu cố định, đã khai ở `Literal` của router — bơm chúng qua đây
    là đẻ ra nguồn sự thật thứ hai cho cùng một danh sách."""

    may: list[LenhSxMayLocOut] = []


class LenhSxSummaryOut(BaseModel):
    """Bốn thẻ KPI. "Hôm nay" = ngày GIỜ XƯỞNG (+7), không phải ngày UTC — xưởng chạy ca đêm."""

    dang_sx: int
    cong_doan_xong_hom_nay: int
    du_kien_tre: int
    # `None` = CHƯA kiểm cái nào hôm nay, khác hẳn `0.0` = kiểm rồi và trượt sạch. UI phải hiện
    # "—" cho `None`; đổ 0 vào đó là báo động giả mỗi sáng sớm.
    ty_le_kcs_dat_hom_nay: float | None = None


# ================= HỒ SƠ MỘT LỆNH (Task 10) =================
# Cùng bẫy Pydantic đã cảnh báo ở đầu file, và ở đây nó nguy hơn: DTO này có 13 khối lồng nhau,
# thiếu một trường trong một khối con thì phần còn lại vẫn ra bình thường — FE nhận `undefined` ở
# đúng một ô và không ai thấy lỗi. Bài canh đọc JSON THẬT qua HTTP: `test_du_cac_khoi`.
class ThongTinOut(BaseModel):
    """Danh tính lệnh. KHÔNG có trường tiền nào — đơn hàng có `don_gia`, hồ sơ này không đọc tới."""

    id: int
    ma: str
    ten: str | None = None
    loai: str | None = None
    order_id: int | None = None
    order_no: str | None = None
    order_line_id: int | None = None
    khach_hang: str | None = None
    khach_hang_id: int | None = None
    sale: str | None = None
    so_luong_dat: int = 0
    don_vi_tinh: str | None = None
    is_rush: bool = False
    han_hoan_thanh_sx: date | None = None
    han_giao_khach: date | None = None
    ban_giao_at: datetime | None = None
    ghi_chu: str | None = None
    tao_luc: datetime | None = None


class TienDoOut(BaseModel):
    """`uoc_tinh=True` = phần trăm đang đo bằng THỜI LƯỢNG kế hoạch vì bước chưa khai sản lượng.
    Phải ra tới UI: 40% "đo được" và 40% "ước tính" là hai mức tin cậy khác hẳn nhau."""

    phan_tram: float = 0.0
    uoc_tinh: bool = False
    gio_may: float = 0.0
    du_kien_xong: datetime | None = None
    trang_thai: str
    canh_bao: list[str] = []
    buoc_hien_tai: str | None = None
    buoc_hien_tai_cong_viec_id: int | None = None
    nhom_cong_doan: str | None = None
    may: str | None = None
    nguoi: list[str] = []
    da_giao: int = 0


class ThongSoOut(BaseModel):
    """Thông số kỹ thuật chụp từ phiếu tính giá. KHAI TỪNG TRƯỜNG là chuyện SỐNG CÒN, không phải
    gu code: `lsx.quy_cach_json` chép nguyên cụm trường vô hướng của phiếu — kể cả
    `phi_giao_hang` — nên khai một trường `dict` ở đây là mở cửa cho tiền chảy ra màn xưởng.

    Khoá thiếu (ảnh chụp của lệnh cũ) ⇒ `None` ⇒ UI hiện "—". Đừng đổi sang `0`."""

    giay_ten: str | None = None
    dinh_luong: float | None = None
    kho_nguyen_dai: float | None = None
    kho_nguyen_rong: float | None = None
    kho_in_dai: float | None = None
    kho_in_rong: float | None = None
    dai_thanh_pham: float | None = None
    rong_thanh_pham: float | None = None
    quy_cach_in: str | None = None
    so_mau_a: int | None = None
    so_mau_b: int | None = None
    muc_a: list[str] = []
    muc_b: list[str] = []
    so_trang: int | None = None
    trang_moi_tay: int | None = None
    so_kem: int | None = None
    so_manh_xa: int | None = None
    loai_san_pham: str | None = None
    ghi_chu_ky_thuat: str | None = None
    so_con: int = 1
    so_to_ke_hoach: int = 0
    so_to_nguyen: int = 0
    don_vi_tinh: str | None = None


class RoutingNodeOut(BaseModel):
    """`lop` = đường DÀI NHẤT từ bước gốc tới bước này, không phải `thu_tu`. Hai bước cùng `lop` là
    hai bước chạy SONG SONG được — thiếu nó thì UI vẽ một chuỗi tuần tự không tồn tại.

    `la_buoc_ghep=True`: bước này do một ca in GHÉP đảm nhiệm, trạng thái/máy/người là của CẢ CA
    chứ không riêng lệnh này."""

    id: int
    thu_tu: int = 0
    lop: int = 0
    phu_thuoc: list[int] = []
    ten: str | None = None
    nhom: str | None = None
    loai_buoc: str | None = None
    bat_buoc: bool = False
    nha_cung_cap: str | None = None
    cong_viec_id: int | None = None
    la_buoc_ghep: bool = False
    la_kcs: bool = False
    la_buoc_hien_tai: bool = False
    trang_thai: str | None = None
    may: str | None = None
    to: str | None = None
    nguoi: list[str] = []
    du_kien_bat_dau: datetime | None = None
    du_kien_ket_thuc: datetime | None = None
    hoan_thanh_luc: datetime | None = None
    so_luong_vao: float = 0.0
    so_luong_ra: float = 0.0
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    # Khuôn & khung của bước. `can_khuon` là "công đoạn CÓ ĐÒI dụng cụ", tách khỏi "đã trỏ dao
    # nào" — thiếu nó thì bước cần dao mà chưa chốt hiện y hệt bước không cần. Phải khai ĐỦ ở đây:
    # service trả dict, Pydantic im lặng nuốt mọi field không khai và FE nhận `undefined`.
    can_khuon: bool = False
    khuon_da_nhan: bool = False
    khuon_be_ma: str | None = None
    khuon_be_ten: str | None = None
    khuon_be_so_ke: str | None = None
    khuon_be_tinh_trang: str | None = None
    khuon_be_ngay_ve: date | None = None


class RoutingOut(BaseModel):
    """`canh` = cặp `[bước trước, bước sau]` bằng id node — đủ để dựng lại đồ thị, không chỉ để
    tô màu."""

    nodes: list[RoutingNodeOut] = []
    canh: list[list[int]] = []


class VatTuDongOut(BaseModel):
    """MỘT dòng cân đối vật tư, lấy nguyên số của `ke_hoach_vat_tu_service` — không tính lại ở tầng
    hồ sơ. `pham_vi` phân biệt dòng của chính lệnh với dòng của BÀI GHÉP mà lệnh là thành viên
    (giấy của cả tờ in ghép): hai thứ đều là vật tư thật của lệnh nhưng người đi lĩnh phải biết
    mình đang lĩnh cho ai."""

    pham_vi: str
    ma: str | None = None
    ten_viec: str | None = None
    buoc_id: int | None = None
    hang_loai: str | None = None
    hang_id: int | None = None
    hang_ma: str | None = None
    hang_ten: str | None = None
    don_vi_goc: str | None = None
    ton: float | None = None
    nhu_cau: float | None = None
    nhu_cau_hien_thi: str | None = None
    # Kho ĐÃ ghi sổ (tồn đã trừ) / đề nghị còn treo. Cả hai tới từ CHÍNH dòng cân đối.
    da_cap: float | None = None
    dang_linh: float | None = None
    con_phai_co: float | None = None
    thieu: float | None = None
    trang_thai: str | None = None
    ngay_can: date | None = None
    ngay_du_hang: date | None = None


class VatTuMucOut(BaseModel):
    """`du` = mọi dòng của bước đang làm đều `xanh`/`xam`. Không dòng nào ⇒ `True` (không có gì để
    thiếu), chứ không phải `False`."""

    du: bool = True
    dong: list[VatTuDongOut] = []


class VatTuOut(BaseModel):
    """Ba câu hỏi khác nhau, ba danh sách: bước ĐANG LÀM có đủ đồ không · bước SẮP TỚI hụt gì ·
    kho đã xuất bao nhiêu rồi. `bo_qua` = dòng engine không đối chiếu được (thiếu công thức lượng,
    đơn vị lạ) — phải bày ra, vì một bảng vật tư im lặng bỏ sót vài món trông y hệt bảng đủ."""

    hien_tai: VatTuMucOut
    canh_bao_sau: list[VatTuDongOut] = []
    da_cap: list[VatTuDongOut] = []
    bo_qua: list[dict] = []


class NhanLucBuocOut(BaseModel):
    cong_viec_id: int
    buoc_id: int | None = None
    ten_viec: str | None = None
    to: str | None = None
    may: str | None = None
    nguoi: list[str] = []


class NhanLucSuKienOut(BaseModel):
    """`loai` ∈ `giao_nguoi` · `rut_nguoi` · `doi_may`. `may_cu`/`may_moi` chỉ có ở `doi_may` —
    và đó là vết DUY NHẤT của lần đổi máy, vì `cong_viec.may_id` chỉ nhớ máy cuối cùng."""

    loai: str
    luc: datetime
    cong_viec_id: int | None = None
    ten_viec: str | None = None
    nguoi: str | None = None
    may_cu: str | None = None
    may_moi: str | None = None
    ly_do: str | None = None


class NhanLucOut(BaseModel):
    """`hien_tai` = roster đang mở (giống cột "Máy/người" của bảng); `lich_su` giữ CẢ người đã bị
    rút — hồ sơ là chỗ trả lời "ai từng làm việc này", bảng danh sách thì không."""

    hien_tai: list[NhanLucBuocOut] = []
    lich_su: list[NhanLucSuKienOut] = []


class SanLuongBatchOut(BaseModel):
    id: int
    cong_viec_id: int
    ten_viec: str | None = None
    la_buoc_ghep: bool = False
    bat_dau: datetime | None = None
    ket_thuc: datetime | None = None
    tong: float = 0.0
    tot: float = 0.0
    hong: float = 0.0
    don_vi: str | None = None
    mo_ta_loi: str | None = None


class SanLuongOut(BaseModel):
    tong: float = 0.0
    tot: float = 0.0
    hong: float = 0.0
    batch: list[SanLuongBatchOut] = []


class KcsBatchOut(BaseModel):
    id: int
    cong_viec_id: int
    ten_viec: str | None = None
    la_buoc_ghep: bool = False
    la_kcs_cuoi: bool = False
    ket_thuc: datetime | None = None
    so_luong_nhan: float = 0.0
    so_luong_dat: float = 0.0
    so_luong_khong_dat: float = 0.0
    don_vi: str | None = None
    ket_luan: str | None = None
    ghi_chu: str | None = None


class KcsOut(BaseModel):
    """`ty_le_dat=None` = CHƯA kiểm cái nào, khác hẳn `0.0` = kiểm rồi và trượt sạch."""

    tong_nhan: float = 0.0
    tong_dat: float = 0.0
    tong_khong_dat: float = 0.0
    ty_le_dat: float | None = None
    batch: list[KcsBatchOut] = []


class PhieuSuaOut(BaseModel):
    id: int
    ma: str
    trang_thai: str | None = None
    nguyen_nhan_phuong_an: str | None = None
    hoan_thanh_at: datetime | None = None


class SuCoOut(BaseModel):
    """`phieu` = phiếu sửa sinh ra từ yêu cầu này (soft-ref `phieu_id`, nối tay ở service). `None`
    khi chưa ai tiếp nhận — không phải lỗi."""

    id: int
    ma: str
    cong_viec_id: int | None = None
    ten_viec: str | None = None
    may: str | None = None
    bo_phan_hong: str | None = None
    mo_ta: str | None = None
    muc_do: str | None = None
    may_dung: bool = False
    nguoi_bao: str | None = None
    thoi_diem: datetime | None = None
    trang_thai: str | None = None
    ly_do_tu_choi: str | None = None
    phieu: PhieuSuaOut | None = None


class KhoYeuCauOut(BaseModel):
    id: int
    kcs_batch_id: int | None = None
    nhom_id: int | None = None
    so_luong_yeu_cau: float = 0.0
    so_luong_xac_nhan: float = 0.0
    con_lai: float = 0.0
    don_vi: str | None = None
    quy_cach: str | None = None
    trang_thai: str | None = None
    tao_luc: datetime | None = None
    xac_nhan_luc: datetime | None = None


class KhoBtpOut(BaseModel):
    id: int
    so_luong: float = 0.0
    don_vi: str | None = None
    phan_loai: str | None = None
    kho_xac_nhan: bool = False
    quy_cach: str | None = None


class KhoOut(BaseModel):
    """Số ở đây là của NHÓM thành phẩm (Ruột + Bìa → Kỷ yếu), KHÔNG phải phần đóng góp của riêng
    lệnh này — cộng qua các lệnh của một trang là nhân số thật lên đúng bằng số thành viên nhóm.

    `so_lenh_trong_nhom` là SỐ chứ không phải cờ, và đó là chủ ý: bản trước trả `cap_nhom=True`
    hằng — một lời chú thích đội lốt trường dữ liệu, đúng cả khi nhóm chỉ có một lệnh (lúc đó số
    của nhóm CHÍNH LÀ số của lệnh, cộng thoải mái) lẫn khi nhóm có ba lệnh. Có con số thì mặt đọc
    tự quyết được. `0` = lệnh chưa vào nhóm nào."""

    so_lenh_trong_nhom: int = 0
    yeu_cau: list[KhoYeuCauOut] = []
    btp: list[KhoBtpOut] = []


class GiaoHangHangOut(BaseModel):
    """MỘT dòng điền sẵn của form giao hàng = một cặp (mặt hàng × kho), vì phiếu xuất đi từ MỘT kho.

    Hai con số, hai nghĩa, đừng dùng lẫn:
      · `so_luong` — tồn THẬT của cặp này, CHƯA trừ đã giao. Để đối chiếu với kho.
      · `so_toi_da` — TRẦN được phép ghi vào phiếu (đã trừ đã giao). Đây là số khoá ô nhập.

    `khong_tinh_duoc=True` ⇒ không dựng được ánh xạ mặt hàng ⇄ dòng đơn (nhóm nhiều dòng đơn, nhóm
    nhiều mặt hàng, hoặc thành viên thiếu `order_line_id`) nên `so_toi_da` là `None`. Ô trống có lý
    do, không phải số 0: hàng vẫn còn trong kho, chỉ là hệ chưa biết chắc đã giao bao nhiêu của
    riêng món này. UI phải cảnh báo, đừng tự điền `so_luong` vào chỗ trần.

    ⚠️ NGHĨA VỤ CỦA TASK 12: `co_the_giao` vẫn TRUE ở ca này (tắt nút lúc kho còn hàng thật là cái
    hại nặng hơn), nên màn hồ sơ PHẢI vẽ được trạng thái "chưa tính được trần" — hiện rõ là chưa
    biết, và bắt người lập phiếu tự đối chiếu kho. Máy chủ KHÔNG đỡ hộ: lưới duy nhất bên giao hàng
    là `delivery_service.tao_yeu_cau` (`:247-257`), nó chặn theo số còn phải giao của DÒNG ĐƠN chứ
    không biết tồn kho — phiếu vượt tồn mà trong hạn mức đơn vẫn lập được. Quên vẽ thì không gì kêu."""

    hang_id: int
    ma: str | None = None
    ten: str | None = None
    quy_cach: str | None = None
    don_vi: str | None = None
    kho_id: int | None = None
    kho_ten: str | None = None
    so_luong: float = 0.0
    so_toi_da: float | None = None
    khong_tinh_duoc: bool = True


class GiaoHangOut(BaseModel):
    """Đủ để KHOÁ nút và ĐIỀN SẴN form. Số dựng ở `san_xuat/kho.ton_kha_dung_thanh_pham` — hàm
    NHẮM tới việc thành nguồn duy nhất dùng chung với form giao hàng (hai bên tự tính thì một bên
    cho bấm, bên kia từ chối), nhưng hôm nay bên giao hàng CHƯA gọi nó.

    KHÔNG có `so_toi_da` cấp nhóm, và đừng thêm lại: trần chỉ có nghĩa ở mức TỪNG mặt hàng
    (`hang[].so_toi_da`). Bản đầu có scalar đó và nó ra số sai ở nhóm nhiều dòng đơn — kho còn 300
    thật mà nút tắt vĩnh viễn.

    `da_nhap_kho`/`da_giao` là số CẤP NHÓM (mọi mặt hàng, mọi dòng đơn) — để đối chiếu, không phải
    để lập phiếu. `da_giao` LUÔN mang nghĩa đó, kể cả khi lệnh chưa vào nhóm nào (lúc ấy `0.0`, và
    số đã giao của riêng dòng đơn lệnh này vẫn có ở `tien_do.da_giao`).

    `so_lenh_trong_nhom` nói mức GỘP: `1` thì số của nhóm chính là số của lệnh; `3` thì cộng qua ba
    lệnh của một trang là nhân số thật lên gấp ba.

    `don_vi_lech=True` ⇒ nhóm có nhiều đơn vị khác nhau, con số tổng KHÔNG có nghĩa; UI phải im nó
    đi thay vì bày ra."""

    nhom_id: int | None = None
    order_id: int | None = None
    order_line_ids: list[int] = []
    so_lenh_trong_nhom: int = 0
    hang: list[GiaoHangHangOut] = []
    da_nhap_kho: float = 0.0
    da_giao: float = 0.0
    co_the_giao: bool = False
    don_vi_lech: bool = False


class TimelineOut(BaseModel):
    """Một dòng thời gian, mốc MÁY CHỦ, sắp tăng dần. `nguoi` có thể trống: vài đường ghi không lưu
    ai bấm (batch KCS), và bịa tên vào đó thì tệ hơn để trống."""

    loai: str
    luc: datetime
    nguoi: str | None = None
    noi_dung: str
    cong_viec_id: int | None = None
    ten_viec: str | None = None


class LenhSxHoSoOut(BaseModel):
    """13 khối của màn Hồ sơ lệnh sản xuất. `phien_ban` đọc từ
    `san_xuat_goi_phat_hanh.version_hien_tai` — `None` khi lệnh chưa có công việc nào (chưa từng
    được phát hành), KHÔNG mặc định 1."""

    thong_tin: ThongTinOut
    tien_do: TienDoOut
    thong_so: ThongSoOut
    routing: RoutingOut
    vat_tu: VatTuOut
    nhan_luc: NhanLucOut
    san_luong: SanLuongOut
    su_co: list[SuCoOut] = []
    kcs: KcsOut
    kho: KhoOut
    giao_hang: GiaoHangOut
    timeline: list[TimelineOut] = []
    phien_ban: int | None = None
