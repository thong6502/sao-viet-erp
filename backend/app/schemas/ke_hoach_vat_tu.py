"""Pydantic schemas — bảng CÂN ĐỐI vật tư của Kế hoạch sản xuất.

⚠️ KHÔNG có trường tiền nào ở đây, và đừng thêm. Bảng này mở cho vai Kế hoạch SX (`san_xuat`),
trong khi giá vốn lô hàng thuộc quyền Kho/Kế toán (`view_cost`). Phơi một cột giá "cho tiện" là mở
toàn bộ bảng giá vốn cho một vai chưa từng được cấp quyền đó — mà lỗi kiểu này không ai báo.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class CanDoiDong(BaseModel):
    """1 dòng nhu cầu = 1 lệnh (hoặc 1 bài ghép) cần mặt hàng này vào một ngày."""

    #: `vat_tu` = có so tồn · `cong_cu` = khuôn bế, không so tồn (chỉ hỏi có sẵn sàng đúng lúc không).
    loai: str
    lsx_id: int | None = None
    bai_ghep_id: int | None = None
    buoc_id: int | None = None
    #: Mã lệnh / mã bài — thứ người dùng đọc.
    ma: str
    #: Lệnh có cờ GẤP. CHỈ ĐỂ BÀY — máy không xếp ưu tiên, không cướp chỗ, không nhắc. Người lập kế
    #: hoạch nhìn cờ rồi tự quyết nhả chỗ của lệnh nào (chủ chốt 17/08/2026).
    is_rush: bool = False
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

    #: xam | xanh | vang | do | **khong_ro** | **ve_muon**.
    #:
    #: `khong_ro` cố ý tách khỏi `xam`: xám nghĩa là "đã cấp đủ, hết việc phải lo", dán nhãn đó lên
    #: một dòng chưa ai tính nổi là nói ngược sự thật.
    #:
    #: `ve_muon` cố ý tách khỏi `do` (17/08/2026): ĐÃ MUA rồi, hàng đang về nhưng về SAU ngày cần.
    #: Hai ca có cách xử NGƯỢC NHAU — đỏ thì đi mua, về muộn thì phải DỜI LỊCH bước tiêu thụ. Gộp
    #: một màu thì người dùng tick đi mua lần nữa, tức MUA ĐÚP đúng lô đang trên đường về.
    trang_thai: str = "xam"
    #: [MỚI 30/08/2026] Giữ chỗ gộp theo (chủ thể, mặt hàng) của DÒNG này — KHÔNG phải phần riêng
    #: của dòng khi cùng chủ thể ăn cùng món ở nhiều bước (xem `GiuChoService.gan_giu_cho_vao_bang`).
    da_giu_kho: float | None = None
    da_giu_dang_ve: float | None = None
    co_the_giu_kho: float | None = None
    co_the_giu_dang_ve: float | None = None
    trang_thai_giu: str | None = None
    nguon_dang_ve: list[dict] | None = None
    #: Ngày về của lô ĐỦ ĐỂ PHỦ chỗ thiếu — chỉ có ở dòng `ve_muon`.
    #:
    #: ⚠️ KHÔNG phải lô gần nhất. Lô gần nhất có thể chỉ mang 1 kg trong khi lệnh thiếu 400 kg —
    #: dời lịch tới ngày đó thì tới nơi vẫn không đủ hàng. Đây là ngày SỚM NHẤT mà cộng dồn các lô
    #: đang về đã phủ được chỗ thiếu.
    ngay_du_hang: date | None = None
    #: Mã phiếu mua của chính lô làm nên `ngay_du_hang` — chỉ có ở dòng `ve_muon`. Không có mã thì
    #: câu "đã có hàng đang về" không tra được về đâu, mà việc phải làm nằm trong đúng phiếu đó.
    phieu_ve: str | None = None
    han_dat: date | None = None
    dat_muon: bool = False
    canh_bao: list[str] = Field(default_factory=list)
    ly_do_canh_bao: str | None = None


class PhieuMuaTom(BaseModel):
    """Một phiếu ĐANG CHẠY của mặt hàng — chỉ đủ để GỌI TÊN, không mang số lượng, không mang tiền.

    Trả lời câu *"cái nào đang yêu cầu mua"*: trước đó ba tình huống rất khác nhau (chưa ai mua ·
    đã đề nghị chờ duyệt · đã duyệt chưa hẹn ngày) đều vẽ ĐỎ giống hệt, nên người dùng bấm Mua
    chồng lên phiếu đã có.
    """

    #: Mã phiếu — `PMH-…` (phiếu mua của thu mua) hoặc `YCMH-…` (đề nghị của bộ phận).
    ma: str
    #: `pmh` | `ycmh`. Hai chuỗi khác nhau, tra ở hai màn khác nhau, nên phải phân biệt được.
    loai: str
    #: Trạng thái THÔ, FE tự dịch ra chữ (gửi chữ Việt sẵn thì hai đầu lệch nhau lúc thêm trạng
    #: thái mới). Với `pmh` là trạng thái của chính phiếu (`pending_approval`, `approved`…).
    #: Với `ycmh` là trạng thái của RIÊNG MÓN NÀY, không phải của yêu cầu cha — ngoài `open` còn
    #: hai giá trị chỉ tồn tại ở cấp món: `dang_lap_don` (thu mua đang gõ phiếu nháp cho nó) và
    #: `don_bi_tu_choi` (phiếu lập cho nó bị trả, đang chờ lập lại).
    trang_thai: str
    #: Ngày về NCC hẹn — chỉ PMH mới có, và cũng chỉ khi NCC đã chốt ngày.
    ngay_ve: date | None = None


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
    #: Số dòng ĐÃ MUA nhưng hàng về SAU ngày cần. Bộ lọc "chỉ thứ đang thiếu" cũng GIỮ LẠI — lệnh
    #: vẫn đứng máy, chỉ khác là việc phải lo là dời lịch chứ không phải chạy đi mua.
    so_dong_ve_muon: int = 0
    #: Chỉ nhóm công cụ mới có — tình trạng khuôn + ngày về dự kiến.
    khuon_tinh_trang: str | None = None
    khuon_ngay_ve: date | None = None
    #: Phiếu đang chạy của mặt hàng, xếp CHẮC → LỎNG (đã duyệt có ngày về đứng đầu). Treo ở nhóm
    #: chứ không ở dòng: phiếu mua không biết lệnh nào, nó chỉ biết mua món gì.
    phieu_mua: list[PhieuMuaTom] = Field(default_factory=list)
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
    #: Bước tiêu thụ — phần thứ năm của khoá. Client gửi lại đúng giá trị nhận được ở `CanDoiDong`.
    #: Thiếu nó thì hai dòng của cùng một lệnh (cùng món, hai công đoạn) tra ra cùng một chỗ và
    #: yêu cầu mua ra một nửa số cần.
    buoc_id: int | None = None


class TheoLenhHang(BaseModel):
    """Một MẶT HÀNG mà một lệnh/bài cần — đã gộp mọi công đoạn của lệnh đó."""

    hang_loai: str
    hang_id: int
    hang_ma: str | None = None
    hang_ten: str | None = None
    don_vi_goc: str | None = None
    #: Theo ĐƠN VỊ GỐC. `can` = tổng `con_phai_co` của mọi bước (đã trừ phần kho cấp rồi).
    can: float = 0
    thieu: float = 0
    dang_giu: float = 0
    #: [MỚI 30/08/2026] Tách nguồn + trạng thái giữ 6 mức. Xem `GiuChoService.giu_theo_chu_the_hang`.
    da_giu_kho: float = 0
    da_giu_dang_ve: float = 0
    co_the_giu_kho: float = 0
    co_the_giu_dang_ve: float = 0
    trang_thai_giu: str = "xam"
    #: Mã PMH cụ thể đang góp cho phần `da_giu_dang_ve` (spec §4 "để FE hiện được đang bám đơn
    #: nào") — mỗi phần tử {"purchase_request_line_id": int, "ma_pmh": str|None, "so_luong": float}.
    nguon_dang_ve: list[dict] = Field(default_factory=list)
    #: Bao nhiêu công đoạn của lệnh này ăn món đó — >1 là lời nhắc rằng con số đã gộp.
    so_buoc: int = 0
    #: Màu NẶNG NHẤT trong các bước. Thẻ chỉ hiện được một màu, và phải là màu tệ nhất.
    trang_thai: str = "xam"
    #: Ngày SỚM NHẤT món này cần tới — nhỏ nhất trong các bước ăn nó. Đứng cạnh `ngay_du_hang` để
    #: thẻ nói được "trễ mấy ngày" mà không phải mượn ngày của cả lệnh (lệnh lấy min của MỌI món).
    ngay_can: date | None = None
    #: Ngày lô đang về phủ đủ chỗ thiếu — MUỘN NHẤT trong các bước `ve_muon` của món: phải chờ tới
    #: khi bước cuối có hàng, không phải bước đầu.
    ngay_du_hang: date | None = None
    #: Mã phiếu mua của lô đó — để nút mua bị khoá gọi tên được đơn hàng đang trên đường về.
    phieu_ve: str | None = None
    #: MỌI phiếu đang chạy của món (kể cả YCMH chưa duyệt, kể cả PMH chưa hẹn ngày), xếp CHẮC →
    #: LỎNG. `phieu_ve` chỉ là cái lô phủ được chỗ thiếu; danh sách này mới nói hết "ai đang lo".
    phieu_mua: list[PhieuMuaTom] = Field(default_factory=list)
    #: Bao nhiêu lệnh/bài KHÁC đang thiếu chính món này — câu *"nhả ra thì ai đỡ"* của hộp xác nhận.
    #:
    #: Tính trên TOÀN BỘ bảng, trước mọi bộ lọc: đếm sau bộ lọc thì màn đang lọc sẽ báo "0 lệnh
    #: khác đang thiếu" trong khi thật ra có ba, và người dùng quyết dựa trên con số do chính bộ
    #: lọc của họ tạo ra.
    so_lenh_khac_thieu: int = 0
    #: Khoá 5 phần của TỪNG dòng đỏ, để nút "Đề nghị mua" trên thẻ đi lại đúng cửa `/de-nghi-mua`.
    #: Cố ý không gộp: một lệnh ăn cùng món ở hai công đoạn là hai dòng, gộp là mua một nửa.
    khoa_do: list[DeNghiMuaDong] = Field(default_factory=list)


class TheoLenhRow(BaseModel):
    """Một thẻ = MỘT lệnh (hoặc bài ghép) — cách nhìn *"lệnh này chạy được chưa"*."""

    lsx_id: int | None = None
    bai_ghep_id: int | None = None
    ma: str
    is_rush: bool = False
    #: Sớm nhất trong các mặt hàng — mốc lệnh bắt đầu cần vật tư.
    ngay_can: date | None = None
    moc_tam: bool = False
    #: Còn giữ chỗ nhưng ĐÃ RƠI khỏi bảng cân đối (lệnh bị kéo về nháp…). Chỗ giữ vẫn trừ vào tồn
    #: tự do của mọi người khác, nên phải bày ra để có đường nhả — không thì nó vô hình.
    ngoai_pham_vi: bool = False

    bat: bool = False
    #: Giữ đủ 100% ⇒ cửa xếp lịch mở. Đây là điều kiện DUY NHẤT của cửa đó.
    du: bool = False
    khong_ro: bool = False
    #: Ngày sớm nhất được xếp bước tiêu thụ — `None` khi mọi phần đều là hàng có thật trong kho.
    xep_som_nhat: date | None = None
    da_xep_lich: bool = False
    giu_tu: datetime | None = None
    so_ngay_giu: int | None = None
    #: Đã bật · đã giữ quá ngưỡng · mà chưa hề đưa vào kế hoạch. Máy CHỈ BÀY, không tự nhả.
    giu_lau_chua_chay: bool = False

    so_mat_hang: int = 0
    so_thieu: int = 0
    so_ve_muon: int = 0
    so_khong_ro: int = 0
    hang: list[TheoLenhHang] = Field(default_factory=list)


class TheoLenhOut(BaseModel):
    items: list[TheoLenhRow] = Field(default_factory=list)
    #: Đếm trên TOÀN BỘ danh sách, không phải phần đang lọc — nếu không thì bật bộ lọc là con số
    #: tự khớp với chính nó và chẳng còn nói lên điều gì.
    so_giu_lau: int = 0


class GiuChoIn(BaseModel):
    """Đúng MỘT chủ thể. Router chặn cả-hai-cùng-trống và cả-hai-cùng-có."""

    lsx_id: int | None = None
    bai_ghep_id: int | None = None


class DeNghiMuaIn(BaseModel):
    dong: list[DeNghiMuaDong] = Field(min_length=1)
    ghi_chu: str | None = Field(default=None, max_length=2000)


class DeNghiMuaDongOut(BaseModel):
    """Một dòng ĐÃ GỘP theo mặt hàng — đúng hình dạng ô vật tư của form Yêu cầu mua hàng."""

    hang_loai: str
    hang_id: int
    item_name: str
    unit: str
    quantity: float


class DeNghiMuaXemTruocOut(BaseModel):
    """Bản NHÁP của yêu cầu mua — tính xong nhưng CHƯA GHI gì vào cơ sở dữ liệu.

    Vì sao có cửa này (20/08/2026, theo yêu cầu chủ): bấm "Đề nghị mua ngay" mà hệ tự đẻ luôn một
    yêu cầu rồi bảo "sang màn Mua hàng xem lại" là bắt người ta ký trước rồi mới được đọc. Cửa
    xem-trước trả về ĐÚNG những gì đường tạo thật sẽ dùng (số lượng gộp · ngày cần · nội dung), FE
    đổ thẳng vào form "Tạo yêu cầu mua hàng" cho người dùng nhìn, sửa, rồi mới bấm Lưu.

    Dùng CHUNG `gom_de_nghi` với `POST /de-nghi-mua`, nên số ở form không thể lệch số hệ sẽ ghi —
    trừ đúng phần người dùng cố ý sửa tay.
    """

    #: Luôn `lsx` — giữ nguyên vết "yêu cầu này sinh từ lệnh sản xuất nào".
    related_document_type: str = "lsx"
    related_document_code: str
    needed_date: date
    #: Ô "Nội dung / mục đích" của form, đã nối sẵn phần ghi chú ngày cần của từng lệnh.
    noi_dung: str
    lines: list[DeNghiMuaDongOut]


class DeNghiMuaOut(BaseModel):
    """Trả MÃ yêu cầu để FE mở lên xem — cố ý KHÔNG tự gửi đi thu mua.

    Máy ghi nhận, người quyết: kế hoạch xem lại số lượng, sửa được, rồi mới bấm gửi ở màn mua hàng.
    """

    id: int
    code: str
