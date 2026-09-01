"""Tầng TRẠNG THÁI của Lệnh SX & Theo dõi SX (Task 8): một trạng thái CHÍNH + nhiều cờ PHỤ.

Bảng lệnh cần đúng MỘT ô trạng thái cho mỗi dòng (`trang_thai_chinh`) để chia tab và đếm; badge
thì cần biết ĐỦ mọi thứ đang sai (`co_canh_bao`). Hai câu hỏi khác nhau nên hai hàm khác nhau —
gộp làm một thì hoặc bảng mất tab, hoặc badge mất tin.

ĐỌC TỪ `BoiCanh` (Task 6) + `tien_do` (Task 7), KHÔNG truy vấn DB. Ngoại lệ DUY NHẤT là
`den_vat_tu_theo_lo()` — nó nhận `db` và cố ý đứng RIÊNG, để bên gọi thấy rõ đó là lượt đọc đắt
phải làm MỘT LẦN cho cả trang. Thiếu dữ liệu thì bổ sung ở `boi_canh.py`, không lén query ở đây.

--- Sáu tab: TRẠNG THÁI CHÍNH = KHÂU XA NHẤT lệnh đã tới -----------------------------------------
Lệnh chảy một chiều: sản xuất → KCS → nhập kho → giao. Một lệnh có thể dính nhiều khâu cùng lúc
(bước sau đang chạy trong khi hàng của bước trước đã vào kho), nên luật là **khâu XA NHẤT**, không
phải "khâu duy nhất đang làm" — nếu không, cùng một lệnh sẽ nhảy tới nhảy lui giữa hai tab tuỳ ai
bấm nút trước.

Thứ tự xét (đọc từ trên xuống, dừng ở cái đầu tiên đúng):

  1. `TAB_HOAN_THANH`     — khách đã THỰC NHẬN đủ `so_luong_dat`.
  2. `TAB_CANH_BAO`       — `co_canh_bao()` không rỗng.
  3. `TAB_SAN_SANG_GIAO`  — sản xuất xong + kho ĐÃ XÁC NHẬN NHẬN được ít nhất một phần.
  4. `TAB_CHO_NHAP_KHO`   — sản xuất xong + KCS CUỐI đã chốt được hàng ĐẠT.
  5. `TAB_KCS`            — mọi bước KHÔNG-KCS đã xong, còn bước KCS chưa đóng.
  6. `TAB_DANG_SX`        — còn lại.

VÌ SAO CẢNH BÁO ĂN TRƯỚC (chốt 31/08/2026): điều độ quét bảng để TÌM CHỖ TẮC. Lệnh vừa chạy vừa
có sự cố mà xếp vào "Đang SX" thì nó biến mất khỏi tầm mắt đúng lúc cần nhìn nhất. Luật này áp
cho CẢ ba tab khâu sau, không riêng Đang SX (`test_canh_bao_an_truoc_ca_ba_tab_khau_sau`).

VÌ SAO HOÀN THÀNH ĂN TRƯỚC CẢNH BÁO (phán quyết của tầng này, ngoài brief): lệnh đã ra khỏi nhà
máy KHÔNG còn chỗ nào để tắc — cảnh báo ở đó là việc không ai làm được nữa. Sự cố còn treo trên
một lệnh đã giao xong là việc của tổ kỹ thuật, không phải việc điều độ phải gỡ trên bảng lệnh.
HAI bài canh, cố ý đi qua HAI cờ khác nhau: `test_hoan_thanh_an_truoc_canh_bao` (cờ `tre_han`)
và `test_hoan_thanh_an_truoc_canh_bao_ke_ca_khi_con_su_co` (cờ `su_co`).
(Bản Task 8 biện minh luật này bằng "`tre_han` của lệnh đã xong bật vĩnh viễn". Lý lẽ đó đã HẾT
hiệu lực từ Vòng sửa 1: `tien_do.du_kien_xong` không còn lùi về `bay_gio` cho lệnh đã xong — nên
lưới thứ hai KHÔNG được phụ thuộc vào `tre_han` nữa. Luật giữ nguyên, nhưng vì lý do ở trên.)

LỆNH CHƯA PHÁT HÀNH KHÔNG CÓ Ô NÀO ở đây, và đó là chủ ý: hai màn này chỉ nhận
`trang_thai = 'da_phat_hanh'` (`pham_vi.loc_lsx_da_phat_hanh`). Lệnh nháp/đang lập vẫn xem ở màn
Kế hoạch SX. Gọi hàm này cho một lệnh nháp sẽ ra `TAB_DANG_SX` — không sai, chỉ là vô nghĩa; lọc
là việc của tầng danh sách.

--- Năm cờ, không hơn ----------------------------------------------------------------------------
`co_canh_bao` trả đúng năm mã, THEO THỨ TỰ `CO_CANH_BAO` (badge của FE phải xếp ổn định giữa các
lần tải). Cả năm đều tính từ dữ liệu mà luật ưu tiên ở trên ĐÃ PHẢI XÉT — không đẻ nguồn mới.

  `su_co`         — yêu cầu sửa chữa neo vào lệnh còn ĐANG MỞ.
  `tam_dung`      — có công việc `paused`.
  `tre_han`       — `tien_do.tre_han` (hạn SX nội bộ, so theo ngày GIỜ XƯỞNG).
  `kcs_khong_dat` — có batch KCS kết luận KHÔNG ĐẠT toàn bộ.
  `thieu_vat_tu`  — đèn `vat_tu` của `lsx_tong_quan` báo ĐỎ.

Ba chỗ hẹp có chủ ý, mỗi chỗ vì một lý do khác nhau:

  · `su_co` chỉ tính `TT_YC_DANG_MO` (= `cho_tiep_nhan`). Yêu cầu `tu_choi` là đóng thật ("không
    phải hỏng / báo trùng / xử lý tại chỗ"). Còn `da_tao_phieu` thì tổ kỹ thuật đã cầm việc, mà
    trạng thái ĐÓNG của phiếu nằm ở `ky_thuat_sua_chua` — bảng `BoiCanh` KHÔNG nạp. Lấy
    `da_tao_phieu` làm cờ nghĩa là mọi lệnh từng hỏng máy đeo cờ vĩnh viễn, kể cả khi máy đã sửa
    xong từ ba tuần trước. Sự cố THẬT SỰ chặn sản xuất thì đã có cờ khác bắt: nhánh "Dừng sản
    xuất" của `san_xuat/su_co.bao_su_co` tạm dừng luôn công việc trong cùng transaction ⇒ `tam_dung`.
  · `kcs_khong_dat` chỉ tính `KCS_KHONG_DAT`, KHÔNG tính `KCS_DAT_MOT_PHAN`. In offset luôn có tờ
    hỏng — đạt-một-phần là ca THƯỜNG; coi nó là cảnh báo thì gần như mọi lệnh đeo cờ và tab Cảnh
    báo hết tác dụng lọc.
  · `thieu_vat_tu` chỉ bật khi bên gọi TRUYỀN đèn vào (`den_vat_tu`). Không truyền = "chưa đọc
    đèn", và tầng này KHÔNG đoán hộ. Đèn đó là một lượt `KeHoachVatTuService.can_doi()` cho cả
    trang; tự gọi trong hàm per-lệnh là đẻ lại đúng N+1 mà Task 6 sinh ra để chặn.

--- Cầu về khâu KHO: đi qua BATCH KCS + NHÓM, không qua registry hàng -----------------------------
"Đã nhập kho chưa" đọc từ `bc.nhap_kho_yc[lsx_id]`, cụ thể là `so_luong_xac_nhan` (số kho ĐÃ NHẬN),
KHÔNG phải `so_luong_yeu_cau`: lập yêu cầu là việc của KCS, hàng vẫn nằm ở tổ cho tới khi thủ kho
bấm nhận. Map đó nay gom CẢ yêu cầu của NHÓM (Ruột + Bìa → Kỷ yếu), không riêng của lệnh — lý do
đầy đủ ở `boi_canh.py`; hệ quả ở đây: hàng vào kho thì mọi lệnh trong nhóm ĐỀU ĐỌC ĐƯỢC, nhưng
lệnh nào chưa xong sản xuất vẫn ở tab Đang SX (cửa `_sx_da_xong`, thêm ở Vòng sửa 2).

BA nhánh khâu sau đều đòi "mọi bước không-KCS đã `completed`". Ba lần vá ở ba vòng khác nhau, cùng
một lỗi: hàng đi trước lệnh. Batch KCS giữa chuyền, tồn kho từng phần, số đạt của KCS cuối — cả ba
đều có thể xuất hiện khi máy còn chạy, và cả ba đều KHÔNG được kéo lệnh khỏi tầm mắt điều độ.

KHÔNG dùng `bc.lot[lsx_id]` cho "sẵn sàng giao", dù nghe hợp lý hơn. Lot THÀNH PHẨM sinh ở
`kho.kho_xac_nhan_nhap` KHÔNG mang `lsx_id` (nó neo `order_id` + `nhom_id` — thành phẩm thuộc NHÓM
"Ruột + Bìa → Kỷ yếu", không thuộc một lệnh), nên `bc.lot[lsx_id]` chỉ chứa lot BTP. Đọc nó ra
"tồn thành phẩm" là đọc nhầm hàng.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ...models.ky_thuat_may import TT_YC_DANG_MO
from ...models.san_xuat import CV_HOAN_THANH, CV_TAM_DUNG
from ...models.san_xuat_kcs import KCS_KHONG_DAT
from ...models.san_xuat_kho import YC_HUY
from .. import lsx_tong_quan
from . import tien_do
from .boi_canh import BoiCanh

# --- Sáu tab của bảng lệnh. Giá trị đi thẳng ra API + URL hash của FE nên coi như hợp đồng: đổi
# chuỗi là hỏng dấu trang của người dùng. Đặt CẠNH NHAU để FE import một chỗ.
TAB_DANG_SX = "dang_sx"
TAB_CANH_BAO = "canh_bao"
TAB_KCS = "kcs"
TAB_CHO_NHAP_KHO = "cho_nhap_kho"
TAB_SAN_SANG_GIAO = "san_sang_giao"
TAB_HOAN_THANH = "hoan_thanh"
# Thứ tự trong tuple = thứ tự tab trên màn (trái → phải), theo dòng chảy của lệnh; Cảnh báo chen
# ngay sau Đang SX vì đó là hai tab điều độ nhìn nhiều nhất.
TAB_CHINH = (
    TAB_DANG_SX, TAB_CANH_BAO, TAB_KCS, TAB_CHO_NHAP_KHO, TAB_SAN_SANG_GIAO, TAB_HOAN_THANH,
)

# --- Năm cờ phụ. Thứ tự trong tuple = thứ tự badge hiện trên dòng.
CO_SU_CO = "su_co"
CO_TAM_DUNG = "tam_dung"
CO_TRE_HAN = "tre_han"
CO_KCS_KHONG_DAT = "kcs_khong_dat"
CO_THIEU_VAT_TU = "thieu_vat_tu"
CO_CANH_BAO = (CO_SU_CO, CO_TAM_DUNG, CO_TRE_HAN, CO_KCS_KHONG_DAT, CO_THIEU_VAT_TU)


class _TuTinh:
    """Sentinel "bên gọi chưa tính `du_kien_xong`" — cùng lý do với `tien_do._TuTinh`: `None` là
    một KẾT QUẢ hợp lệ của `du_kien_xong` ("chưa đủ dữ liệu") mà bên gọi có quyền truyền lại, nên
    không dùng `None` làm mặc định được.

    Khai riêng ở đây thay vì import `tien_do._TU_TINH` (tên `_`-riêng tư của module khác): hàm này
    LUÔN quy `xong` về `datetime | None` rồi mới gọi `tien_do.tre_han(..., xong=...)` bằng giá trị
    thật, nên hai sentinel không bao giờ phải so với nhau.
    """


_TU_TINH = _TuTinh()


def den_vat_tu_theo_lo(db: Session, lsx_ids: list[int]) -> dict[int, str]:
    """`{lsx_id: mức đèn vật tư}` (`do` / `vang` / `ok`) cho CẢ LÔ — gọi MỘT lần cho cả trang.

    Đọc LẠI đèn của `lsx_tong_quan.tong_quan`, KHÔNG tính lại: đèn đó cố ý soi đúng cửa chặn
    `XepLichService._chan_chua_giu_du`, nên "đỏ" ở đây nghĩa là cùng một câu mà cửa chặn nói —
    tính lại bằng công thức riêng là đẻ nguồn sự thật thứ hai lệch với cửa.

    Đắt: bên trong là một lượt `KeHoachVatTuService.can_doi()` + một lượt `XepLichVanDeService` cho
    cả lô. Chi phí gần như không đổi theo số lệnh nhưng KHÁC 0 — gọi hàm này trong vòng lặp từng
    lệnh là đẻ lại đúng N+1 mà Task 6 sinh ra để chặn.

    Lệnh nào không ra được đèn (id không tồn tại, hoặc `tong_quan` bỏ qua id rỗng) đơn giản VẮNG
    MẶT trong dict — `co_canh_bao` đọc bằng `.get` nên vắng mặt = không giương cờ, không nổ.
    """
    return {
        r["lsx_id"]: r["den"]["vat_tu"]["muc"]
        for r in lsx_tong_quan.tong_quan(db, lsx_ids)
    }


def _co_su_co_dang_mo(bc: BoiCanh, lsx_id: int) -> bool:
    """Yêu cầu sửa chữa neo vào lệnh còn ĐANG MỞ (xem docstring module: chỉ `TT_YC_DANG_MO`).

    SỰ CỐ CỦA CA IN GHÉP CÓ VỀ ĐƯỢC (sửa ở Vòng sửa 1 — trước đó docstring này nói ngược lại).
    `su_co.bao_su_co` neo `lsx_id = cv.lsx_id`, mà công việc ghép có `lsx_id IS NULL`
    (`san_xuat/su_co.py:118-120`) ⇒ đường `lsx_id` hụt; nhưng nó LUÔN ghi `cong_viec_id`, và câu 10
    của `boi_canh` OR thêm vế đó. Hệ quả cố ý: sự cố trên ca ghép giương cờ cho MỌI lệnh nằm trên
    tờ in ấy — máy đứng thì cả tờ đứng. Bài canh: `test_su_co_bao_tren_ca_ghep_van_ve_duoc_lenh`.
    """
    return any(yc.trang_thai in TT_YC_DANG_MO for yc in bc.su_co[lsx_id])


def _co_tam_dung(bc: BoiCanh, lsx_id: int) -> bool:
    """Đọc `cong_viec_du` chứ không `cong_viec`: bước bị bài ghép phủ nằm ở công việc CHUNG, mà ca
    in ghép dừng thì lệnh dừng thật."""
    return any(cv.trang_thai == CV_TAM_DUNG for cv in bc.cong_viec_du(lsx_id))


def _co_kcs_khong_dat(bc: BoiCanh, lsx_id: int) -> bool:
    """CỜ: có batch nào kết luận KHÔNG ĐẠT — đọc MỌI bước KCS, kể cả bước bị bài ghép phủ.

    Rộng ở đây là ĐÚNG: ca in ghép hỏng thì mọi lệnh nằm trên tờ in ấy đều dính. Đường đọc này
    CỐ Ý khác `_so_kcs_dat_cuoi` — xem docstring hàm đó.
    """
    return any(
        k.ket_luan == KCS_KHONG_DAT
        for cv in bc.cong_viec_du(lsx_id)
        for k in bc.kcs[cv.id]
    )


def _so_kcs_dat_cuoi(bc: BoiCanh, lsx_id: int) -> float:
    """TAB: số hàng ĐẠT của bước KCS CUỐI — chỉ số này mới lái được tab Chờ nhập kho.

    HẸP hơn `_co_kcs_khong_dat` một cách có chủ ý, hai lý do khác nhau:

    1. `kcs.tao_batch_kcs:110` chỉ đòi `cv.la_kcs`, KHÔNG đòi bước cuối — mọi chốt kiểm giữa
       chuyền đều đẻ số đạt. Nhưng yêu cầu nhập kho CHỈ sinh từ batch của KCS cuối (nó cần
       `nhom_id` của batch, `kho.py:122-124`), nên đếm batch giữa chừng là đẩy lệnh sang một tab
       mà kho sẽ không bao giờ nhận hàng — lệnh kẹt vĩnh viễn, không đường tự thoát.
    2. Batch của một bước GHÉP là số của CẢ CA, không phải của riêng một lệnh. Với cờ
       `kcs_khong_dat` thì đếm đủ cho mọi lệnh là đúng (bước hỏng thì cả ca dính); với TAB thì
       không — "5.000 cái đạt" của ca ghép không nói gì về phần của lệnh này.

    Bước KCS cuối bị bài ghép phủ vẫn được đếm (đọc `cong_viec_du`, không phải `cong_viec`):
    `snapshot.danh_dau_kcs_cuoi:170` đánh `la_kcs_cuoi` lên chính công việc chung khi bước cuối
    của lệnh nằm trong cụm ghép, và bỏ nó đi thì lệnh mất luôn đường vào tab. Ca đó số vẫn là số
    của cả ca — chấp nhận được vì nhập kho là sự thật cấp NHÓM (xem `boi_canh.py`).

    `Numeric` ⇒ `Decimal`, ép `float` ngay tại chỗ đọc (bẫy `Decimal / float` tái phát của repo).
    """
    return sum(
        float(k.so_luong_dat or 0)
        for cv in bc.cong_viec_du(lsx_id)
        if cv.la_kcs_cuoi
        for k in bc.kcs[cv.id]
    )


def _yc_con_song(bc: BoiCanh, lsx_id: int) -> list:
    """Yêu cầu nhập kho CÒN HIỆU LỰC — bỏ `huy` (KCS huỷ phần chưa nhận để phân loại lại, §14.1).

    Lọc thẳng theo trạng thái là ĐỦ, không sợ ăn nhầm phần đã nhận: `kho.huy_phan_chua_nhan`
    (`services/san_xuat/kho.py:290`) chỉ đặt `huy` khi CHƯA nhận gì — đã nhận một phần rồi mới huỷ
    phần còn lại thì nó đặt `da_nhap`, vì phần đã nhận đã đẻ lot và bị khoá.
    """
    return [yc for yc in bc.nhap_kho_yc[lsx_id] if yc.trang_thai != YC_HUY]


def _co_ton_thanh_pham(bc: BoiCanh, lsx_id: int) -> bool:
    """Kho ĐÃ NHẬN được ít nhất một phần, VÀ sản xuất đã xong ⇒ có tồn thành phẩm để giao.

    Đọc `so_luong_xac_nhan` (số thủ kho đã bấm nhận), KHÔNG phải `so_luong_yeu_cau`: yêu cầu là
    lời của KCS, hàng vẫn nằm ở tổ cho tới lúc kho nhận.

    Vế `_sx_da_xong` thêm ở Vòng sửa 2, cùng lý do đã phải vá hai lần ở hai nhánh dưới: lệnh còn
    chạy máy mà đã có 2.000 sản phẩm vào kho thì vẫn là ĐANG SX. Tồn từng phần là chi tiết của màn
    hồ sơ, không phải cớ để lệnh đổi tab và biến khỏi tầm mắt điều độ khi công việc chưa xong.

    CHƯA làm (đã ghi nhận, ngoài phạm vi Vòng sửa 2): với NHÓM nhiều lệnh (Ruột + Bìa giao chung),
    "sẵn sàng" đúng nghiệp vụ phải là MỌI thành viên xong sản xuất. Ở đây mỗi lệnh mới tự soi công
    việc của chính nó, nên Ruột xong trước sẽ báo sẵn sàng trong khi Bìa còn chạy. Vá được nhưng
    cần công việc của lệnh KHÁC đã nạp — việc của tầng nạp, không phải của hàm này.
    """
    if not _sx_da_xong(bc, lsx_id):
        return False
    return any(float(yc.so_luong_xac_nhan or 0) > 0 for yc in _yc_con_song(bc, lsx_id))


def _sx_da_xong(bc: BoiCanh, lsx_id: int) -> bool:
    """Mọi bước KHÔNG-KCS đã `completed` — "hàng đã ra khỏi chuyền"."""
    return all(cv.trang_thai == CV_HOAN_THANH for cv in bc.cong_viec_du(lsx_id) if not cv.la_kcs)


def _kcs_dat_cho_nhap(bc: BoiCanh, lsx_id: int) -> bool:
    """Có hàng ĐẠT của KCS cuối, và sản xuất đã xong.

    Vế "sản xuất đã xong" là cùng một cửa mà `_dang_o_kcs` đã có, và cần vì đúng lý do đó: chừng
    nào còn bước máy đang chạy thì lệnh vẫn ở khâu SX, dù KCS cuối đã chốt được một phần.

    KHÔNG còn vế "kho chưa nhận món nào" (bản Task 8 có): nhánh này chỉ chạy khi
    `_co_ton_thanh_pham` đã False (xem thứ tự trong `trang_thai_chinh`), nên vế đó là mã chết —
    Vòng sửa 1 bỏ đi. Đổi lại, THỨ TỰ hai nhánh thành load-bearing; bài canh là
    `test_co_ton_chua_giao_ra_san_sang_giao` (lệnh vừa có số đạt vừa có tồn ⇒ Sẵn sàng giao).
    """
    return _so_kcs_dat_cuoi(bc, lsx_id) > 0 and _sx_da_xong(bc, lsx_id)


def _dang_o_kcs(bc: BoiCanh, lsx_id: int) -> bool:
    """Sản xuất xong, còn bước KCS chưa đóng.

    Đòi MỌI bước không-KCS đã `completed`: bước KCS giữa chuỗi (kiểm tra giữa chừng) không có
    nghĩa là lệnh "đang ở KCS" — lệnh vẫn đang chạy, và xếp nó vào tab KCS là giấu nó khỏi tab
    Đang SX.
    """
    cvs = bc.cong_viec_du(lsx_id)
    if not cvs:
        return False
    if not any(cv.la_kcs and cv.trang_thai != CV_HOAN_THANH for cv in cvs):
        return False
    return _sx_da_xong(bc, lsx_id)


def _da_giao_het(bc: BoiCanh, lsx_id: int) -> bool:
    """Khách đã THỰC NHẬN đủ `so_luong_dat` (= `order_lines.qty`, bản cam kết bán).

    `so_luong_dat <= 0` ⇒ False: không có số cam kết thì không có gì để phủ, và coi "0 ≥ 0" là
    giao xong sẽ đẩy mọi lệnh thiếu dữ liệu vào tab Hoàn thành.

    Đọc `bc.da_giao_cua(lsx_id)` — tổng `delivery_trip_lines.qty_giao` qua các chuyến trong
    `LAN_GIAO_CO_HANG_DEN_TAY` — KHÔNG phải `sum(g.qty for g in bc.giao_cua(...))`. `qty` bên đó
    là số YÊU CẦU giao: lập phiếu xong là đủ số ngay dù xe chưa chạy, hoặc chạy rồi mà thất bại.
    Cách đọc mới cũng tự loại yêu cầu đã HUỶ mà không cần lọc `trang_thai`:
    `delivery_service.huy_yeu_cau:301` từ chối huỷ khi đã có bất kỳ chuyến nào, nên yêu cầu `da_huy`
    không bao giờ có dòng chuyến để cộng.

    GIỚI HẠN còn lại: nhiều lệnh cùng một dòng đơn (lệnh bù — pha sau) sẽ CÙNG đọc trọn số của
    dòng đó. Cần chia thì phải chia ở tầng nạp, không phải ở đây.
    """
    dat = bc.lenh[lsx_id].so_luong_dat or 0
    if dat <= 0:
        return False
    return bc.da_giao_cua(lsx_id) >= dat


def co_canh_bao(
    bc: BoiCanh, lsx_id: int, bay_gio: datetime, *,
    den_vat_tu: dict[int, str] | None = None,
    xong: datetime | None | _TuTinh = _TU_TINH,
) -> list[str]:
    """MỌI thứ đang sai của một lệnh, theo thứ tự cố định của `CO_CANH_BAO`. Rỗng = không có gì.

    Khác `trang_thai_chinh` ở chỗ nó KHÔNG chọn một cái: badge phải nói đủ, còn tab thì chỉ có
    một ô. Lệnh dính cả sự cố lẫn trễ hạn đeo hai badge nhưng vẫn nằm ở đúng một tab.

    `den_vat_tu` (KEYWORD-ONLY) = `{lsx_id: mức}` do `den_vat_tu_theo_lo()` đọc MỘT lần cho cả
    trang. Bỏ trống = CHƯA ĐỌC đèn ⇒ cờ `thieu_vat_tu` không được xét — im lặng bỏ một cờ, nên
    tầng danh sách BẮT BUỘC truyền vào (xem docstring module).

    `xong` (KEYWORD-ONLY) = kết quả `tien_do.du_kien_xong` bên gọi ĐÃ tính. Bỏ trống thì hàm tự
    tính; màn 200 lệnh phải truyền vào, không thì trang duyệt đường găng 400 lượt. Truyền `None`
    là hợp lệ và có nghĩa "đã tính, không đủ dữ liệu" — vì vậy mặc định là sentinel riêng.
    """
    co: list[str] = []
    if _co_su_co_dang_mo(bc, lsx_id):
        co.append(CO_SU_CO)
    if _co_tam_dung(bc, lsx_id):
        co.append(CO_TAM_DUNG)
    if isinstance(xong, _TuTinh):
        xong = tien_do.du_kien_xong(bc, lsx_id, bay_gio)
    # `xong` đã là `datetime | None` thật ⇒ truyền thẳng, `tien_do.tre_han` không phải tính lại.
    if tien_do.tre_han(bc, lsx_id, bay_gio, xong=xong):
        co.append(CO_TRE_HAN)
    if _co_kcs_khong_dat(bc, lsx_id):
        co.append(CO_KCS_KHONG_DAT)
    if den_vat_tu is not None and den_vat_tu.get(lsx_id) == lsx_tong_quan.MUC_DO:
        co.append(CO_THIEU_VAT_TU)
    return co


def trang_thai_chinh(
    bc: BoiCanh, lsx_id: int, bay_gio: datetime, *,
    den_vat_tu: dict[int, str] | None = None,
    xong: datetime | None | _TuTinh = _TU_TINH,
) -> str:
    """MỘT trạng thái cho một dòng bảng — luôn là một trong `TAB_CHINH`, không bao giờ rỗng.

    Thứ tự xét + lý do từng nhánh: xem docstring module. Hai tham số keyword-only đi thẳng xuống
    `co_canh_bao`; ý nghĩa và bẫy của chúng nằm ở đó.
    """
    if _da_giao_het(bc, lsx_id):
        return TAB_HOAN_THANH
    if co_canh_bao(bc, lsx_id, bay_gio, den_vat_tu=den_vat_tu, xong=xong):
        return TAB_CANH_BAO
    if _co_ton_thanh_pham(bc, lsx_id):
        return TAB_SAN_SANG_GIAO
    if _kcs_dat_cho_nhap(bc, lsx_id):
        return TAB_CHO_NHAP_KHO
    if _dang_o_kcs(bc, lsx_id):
        return TAB_KCS
    return TAB_DANG_SX
