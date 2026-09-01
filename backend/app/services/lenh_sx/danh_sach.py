"""Tầng DANH SÁCH + KPI của màn "Lệnh sản xuất" (Task 9) — cửa HTTP đầu tiên của cả tầng đọc.

Hai hàm: `danh_sach()` (bảng + facet tab) và `summary()` (4 thẻ KPI). Cả hai CHỈ ĐỌC.

--- LỌC HAI TẦNG, và nói thẳng ra thay vì giấu (phán quyết C60) ---------------------------------
`tab` và `tre` KHÔNG phải cột. Chúng là kết quả của `trang_thai.trang_thai_chinh` /
`tien_do.tre_han`, tính lúc đọc từ 20 map của `boi_canh` — không có mệnh đề `WHERE` nào diễn đạt
được chúng. Thêm nữa `dem_theo_tab` (số trên từng tab) BẮT BUỘC tính trên TOÀN BỘ tập đã lọc chứ
không phải trang đang xem: tab hiện "3" trong khi tập có 47 là một con số sai mà không ai thấy sai.

Nên đường đi là:

  TẦNG 1 — SQL (`_loc_sql`): phạm vi người bán + `da_phat_hanh` (`pham_vi.loc_lsx_da_phat_hanh`),
           `q`, khoảng ngày hạn SX, `may_id`, `nhom_cong_doan`, `uu_tien`. Trả về TẬP `lsx_id`.
  TẦNG 2 — Python (`_soi`): MỘT lần `boi_canh.nap()` + MỘT lần `den_vat_tu_theo_lo()` cho cả tập
           ⇒ trạng thái + cờ cảnh báo ⇒ dựng `dem_theo_tab` ⇒ lọc `tab`/`tre` ⇒ SẮP ⇒ CẮT TRANG.

Điều bị cấm ở dự án này là CLIENT kéo cả bảng về rồi slice trong JS. Tính dẫn xuất ở MÁY CHỦ trên
một tập đã hẹp là chuyện khác — trình duyệt vẫn chỉ nhận đúng một trang.

CHI PHÍ PHẢI BIẾT, vì đây là chỗ sẽ phải vá trước tiên khi xưởng lớn lên: tầng 1 trả về MỌI lệnh
đã phát hành trong phạm vi (trừ phần `q`/ngày/máy/nhóm cắt bớt), và tập đó CHỈ TĂNG theo thời gian
— vòng đời `lsx` hôm nay dừng ở `da_phat_hanh`, không có trạng thái "đã đóng" nào để lọc ra. Một
xưởng chạy 50 lệnh/tháng sau hai năm có ~1.200 dòng tầng 1 cho MỖI request.

SỐ CÂU SQL — nói cho đúng, vì câu nói gọn ở đây từng là một khẳng định SAI: hằng số theo số LỆNH
(bài `test_so_cau_sql_hang_tren_truc_lenh` khoá), nhưng TUYẾN TÍNH theo số BÀI GHÉP tồn tại trong
kế hoạch — đo được **+28 câu mỗi bài ghép**: 90 → 98 (thêm 2 lệnh thường rồi PHẲNG) → 126 → 154.
Nguồn KHÔNG nằm ở tầng này mà ở `ke_hoach_vat_tu_service._gom_nhu_cau` (hai vòng `for bg in bais`
quanh dòng 881-895 và 914-925), tới đây qua `_soi` → `trang_thai.den_vat_tu_theo_lo` → `can_doi()`.
Chi phí ấy bám vào SỐ BÀI GHÉP CÓ TRONG DB, không bám trang đang xem: lọc `q=` xuống đúng một dòng
vẫn tốn y hệt. Phán quyết C68: KHÔNG vá trong Task 9 (mã cũ của module Kế hoạch vật tư, mổ
`_gom_nhu_cau` là một task riêng) — nhưng ai đọc đoạn này phải biết trần thật của nó ở đâu.

Khi những con số đó thành vấn đề, ba đường vá theo thứ tự: (a) gộp hai vòng `for bg in bais` của
`_gom_nhu_cau` lại thành truy vấn theo LÔ; (b) vật chất hoá `trang_thai_chinh` thành cột được ghi
lại mỗi lần công việc/KCS/kho đổi, rồi `WHERE` thẳng lên nó; (c) cho lệnh một trạng thái kết thúc
để tập tầng 1 thôi phình. ĐỪNG vá bằng cách đếm tab trên trang đang xem.

--- "HÔM NAY" CỦA KPI LÀ NGÀY GIỜ XƯỞNG (phán quyết C61) ----------------------------------------
Dùng `tien_do.BUSINESS_TZ` (+7), đúng như `tien_do.tre_han` đã làm — KHÔNG phải ngày UTC. Xưởng
CÓ chạy ca đêm: 2h sáng giờ VN vẫn là ngày HÔM TRƯỚC theo UTC, nên KPI tính theo UTC sẽ cắt đôi
một ca đêm và đổ nửa đầu sang hôm qua. Bài canh: `test_summary_cong_doan_xong_theo_gio_xuong`.

--- BỐN KPI, mỗi cái đọc từ đâu ------------------------------------------------------------------
  `dang_sx`                — số lệnh trong phạm vi CHƯA ra khỏi nhà máy (`trang_thai_chinh` khác
                             `TAB_HOAN_THANH`). KHÔNG phải số đếm của tab "Đang SX": lệnh đang
                             chạy mà dính sự cố nằm ở tab Cảnh báo, nhưng nó vẫn đang sản xuất.
  `cong_doan_xong_hom_nay` — số CÔNG VIỆC `completed` có `hoan_thanh_luc` rơi vào ngày xưởng hôm
                             nay. Cột NGHIỆP VỤ riêng (mig `0250`), KHÔNG phải `updated_at`: mốc
                             bảo trì dời theo mọi `version += 1` về sau, và đó là lỗi ĐÃ ĐO —
                             `thuc_thi.go_phan_cong` rút người khỏi một bước đã xong cũng
                             `version += 1`, kéo một bước đóng năm 2020 vào KPI hôm nay. Bịt riêng
                             đường ghi ấy không xử được lớp lỗi: đường ghi thêm sau lại phá lại,
                             âm thầm. Dấu đóng ở `thuc_thi.ket_thuc` — chỗ DUY NHẤT trong hệ đặt
                             `trang_thai='completed'`. Bài canh:
                             `test_kpi_khong_bi_go_phan_cong_keo_vao_hom_nay`.
                             KHÔNG đếm qua phiên chạy: bước bị TẠM DỪNG rồi mới Kết thúc không có
                             phiên nào mang `loai_dong='ket_thuc'` (`thuc_thi.ket_thuc:396` chỉ
                             đóng phiên ĐANG MỞ, mà việc tạm dừng thì không còn phiên mở) — đếm
                             kiểu đó là bỏ sót im lặng đúng những bước gặp trục trặc.
                             Đếm theo ID CÔNG VIỆC (`set`), nên ca in GHÉP phục vụ nhiều lệnh chỉ
                             tính MỘT — nó là một công đoạn, không phải ba.
  `du_kien_tre`            — số lệnh chưa xong mà `tien_do.tre_han` bật. Tập con của `dang_sx`:
                             lệnh đã giao đủ thì không còn "dự kiến" gì để trễ.
  `ty_le_kcs_dat_hom_nay`  — `Σ so_luong_dat / Σ so_luong_nhan` của các batch KCS KẾT THÚC trong
                             ngày xưởng, theo SỐ chứ không phải trung bình cộng các batch (batch
                             10 cái và batch 10.000 cái không cân nhau). Mốc là `ket_thuc` (lúc
                             kiểm xong) chứ không phải `created_at` (lúc gõ vào máy): ca đêm nhập
                             số buổi sáng vẫn phải nằm ở ngày kiểm.
                             KHÔNG kiểm cái nào ⇒ `None`, không phải `0.0`: "0% đạt" là một lời
                             báo động sai, và nó sẽ xuất hiện mỗi sáng sớm.

--- MỘT BẢNG, MỘT SỐ TIỀN CŨNG KHÔNG --------------------------------------------------------------
Ràng buộc toàn cục của cả plan: không `don_gia` / `gia_von` / `thanh_tien` / `luong_khoan` /
`chi_phi`. Hàm dựng dòng ở đây chỉ chạm mã · tên · khách · số lượng · thời gian · trạng thái.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models.bai_ghep_cong_doan import BaiGhepCongDoanMap
from ...models.customer import Customer
from ...models.lsx import Lsx, LsxCongDoan
from ...models.order import Order
from ...models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG, SanXuatCongViec
from . import boi_canh, pham_vi, tien_do, trang_thai
from .boi_canh import BoiCanh

# Tab thứ BẢY của màn — "tất cả", không phải một trạng thái. Để cạnh `TAB_CHINH` của
# `trang_thai.py` chứ không trộn vào đó: `trang_thai_chinh` không bao giờ trả giá trị này, mà
# nhét nó vào `TAB_CHINH` sẽ làm mọi vòng lặp "duyệt 6 tab" ở tầng khác đếm thừa một ô.
TAB_TAT_CA = "tat_ca"
TAB_CHO_PHEP = (TAB_TAT_CA,) + trang_thai.TAB_CHINH

# Giá trị hợp lệ của bộ lọc `uu_tien`. Bám nguyên chuỗi của `schemas/stock.py:42` để cả hệ nói
# cùng một từ; cột thật trên lệnh là `lsx.is_rush` (Boolean), không phải một cột chuỗi.
UU_TIEN_GAP = "gap"
UU_TIEN_THUONG = "binh_thuong"
UU_TIEN_CHO_PHEP = (UU_TIEN_GAP, UU_TIEN_THUONG)

PAGE_SIZE_MAC_DINH = 50
PAGE_SIZE_TOI_DA = 200

# Mốc "vô cùng" để sắp xếp: lệnh KHÔNG có hạn SX xuống cuối bảng (không có hạn thì không gấp),
# công việc chưa xếp lịch xuống cuối chuỗi bước.
_NGAY_XA = date(9999, 12, 31)
_LUC_XA = datetime(9999, 12, 31, tzinfo=timezone.utc)
_LUC_XUA = datetime(1, 1, 1, tzinfo=timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite trả datetime NAIVE — ép aware UTC trước khi so/trừ (bẫy tái phát của repo). Khai lại
    cục bộ thay vì import `tien_do._aware` (tên `_`-riêng tư của module khác), đúng thói quen sẵn
    có của gói này."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _ngay_xuong(bay_gio: datetime) -> tuple[datetime, datetime]:
    """Nửa khoảng `[đầu ngày, đầu ngày sau)` của NGÀY GIỜ XƯỞNG chứa `bay_gio` (phán quyết C61).

    Trả về mốc AWARE nên so được thẳng với `_aware(...)` của mọi cột thời gian, bất kể chúng được
    lưu ở múi nào.
    """
    dau = _aware(bay_gio).astimezone(tien_do.BUSINESS_TZ).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return dau, dau + timedelta(days=1)


# --- TẦNG 1: những gì SQL nói được ---------------------------------------------------------------
def _co_buoc(cot_cong_viec, cot_routing, gia_tri):
    """"Lệnh này có bước nào mang `gia_tri` không" — hỏi BA nơi bước có thể sống.

    · `san_xuat_cong_viec` NEO THẲNG (`lsx_id = Lsx.id`) — snapshot lúc phát hành, và là nơi thực
      thi GHI ĐÈ về sau (`thuc_thi.doi_may` đổi máy giữa chừng). Sự thật hiện hành của bước RIÊNG.
    · `san_xuat_cong_viec` QUA CẦU GHÉP — bước bị BÀI GHÉP phủ KHÔNG đẻ công việc riêng: cả cụm
      dùng CHUNG một công việc mang `lsx_id IS NULL` + `bai_ghep_cong_doan_id`
      (`snapshot.dung_cong_viec`). Vế đầu không với tới nó, và máy/nhóm THẬT của ca in ghép chỉ
      nằm ở đây — `bai_ghep_cong_doan.may_id` được chụp vào công việc chung lúc phát hành và
      KHÔNG chỗ nào ghi ngược về `lsx_cong_doan.may_id` (grep cả `bai_ghep_service` lẫn
      `bai_ghep_2_service`: 0 chỗ ghi). Thiếu vế này thì lọc `?may_id=` bỏ sót đúng lệnh in ghép ở
      đúng khâu nặng nhất của nó — bảng hiện tên máy mà lọc theo chính máy đó lại trả rỗng.
      Cầu: `san_xuat_cong_viec.bai_ghep_cong_doan_id` → `bai_ghep_cong_doan_map` → `lsx_id`
      (`models/bai_ghep_cong_doan.py:146` — bảng phủ neo bằng `lsx_step_key`, nhưng nó có sẵn cột
      `lsx_id` nên không phải đi vòng qua `step_key`).
    · `lsx_cong_doan` = routing của chính lệnh. Bắt ca bước đã khai máy/nhóm ở routing mà snapshot
      chưa mang (`thoi_gian_lsx_step` trả `None` thì `snapshot` lùi về `cd.may_id`, nhưng routing
      sửa SAU phát hành thì hai bên lệch).

    Ba `EXISTS` trong cùng một `WHERE` ⇒ vẫn MỘT câu SQL, không phải ba lượt đi DB.
    """
    return or_(
        select(SanXuatCongViec.id)
        .where(SanXuatCongViec.lsx_id == Lsx.id, cot_cong_viec == gia_tri)
        .exists(),
        select(SanXuatCongViec.id)
        .join(
            BaiGhepCongDoanMap,
            BaiGhepCongDoanMap.bai_ghep_cong_doan_id
            == SanXuatCongViec.bai_ghep_cong_doan_id,
        )
        .where(BaiGhepCongDoanMap.lsx_id == Lsx.id, cot_cong_viec == gia_tri)
        .exists(),
        select(LsxCongDoan.id)
        .where(LsxCongDoan.lsx_id == Lsx.id, cot_routing == gia_tri)
        .exists(),
    )


def _loc_sql(
    sale_ids: set[int] | None, *,
    q: str | None, tu_ngay: date | None, den_ngay: date | None,
    may_id: int | None, nhom_cong_doan: str | None, uu_tien: str | None,
):
    """`select(Lsx.id)` đã gắn HẾT phần lọc mà SQL diễn đạt được. Phần còn lại ở `_soi`.

    Khoảng ngày soi `han_hoan_thanh_sx` — hạn SX NỘI BỘ, cùng cột mà `tien_do.tre_han` lấy làm mốc.
    Chọn cột này chứ không phải `han_giao_khach` để bộ lọc ngày và cột Trạng thái nói cùng một
    chuyện; lệnh CHƯA có hạn SX rơi ra ngoài mọi khoảng (NULL không khớp phép so nào) — đúng, vì
    không có hạn thì không xếp được vào khoảng nào cả.
    """
    stmt = pham_vi.loc_lsx_da_phat_hanh(select(Lsx.id), sale_ids)

    if q and q.strip():
        mau = f"%{q.strip()}%"
        # Khách + số đơn đi qua SUBQUERY chứ không JOIN thêm: `loc_lsx_da_phat_hanh` ĐÃ có thể
        # join `orders` cho phần phạm vi, join lần hai là bảng xuất hiện hai lần trong cùng câu.
        don_khop = (
            select(Order.id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(or_(Order.order_no.ilike(mau), Customer.name.ilike(mau)))
        )
        stmt = stmt.where(
            or_(Lsx.ma.ilike(mau), Lsx.ten.ilike(mau), Lsx.order_id.in_(don_khop))
        )

    if tu_ngay is not None:
        stmt = stmt.where(Lsx.han_hoan_thanh_sx >= tu_ngay)
    if den_ngay is not None:
        stmt = stmt.where(Lsx.han_hoan_thanh_sx <= den_ngay)

    if may_id is not None:
        stmt = stmt.where(_co_buoc(SanXuatCongViec.may_id, LsxCongDoan.may_id, may_id))
    if nhom_cong_doan:
        stmt = stmt.where(
            _co_buoc(SanXuatCongViec.nhom_cong_doan, LsxCongDoan.nhom, nhom_cong_doan)
        )

    if uu_tien == UU_TIEN_GAP:
        stmt = stmt.where(Lsx.is_rush.is_(True))
    elif uu_tien == UU_TIEN_THUONG:
        stmt = stmt.where(Lsx.is_rush.is_(False))
    return stmt


# --- TẦNG 2: những gì chỉ tính lúc đọc mới biết ---------------------------------------------------
def _soi(db: Session, lsx_ids: list[int], bay_gio: datetime) -> tuple[BoiCanh, dict[int, dict]]:
    """MỘT lượt nạp + MỘT lượt đọc đèn vật tư cho CẢ TẬP, rồi tính trạng thái từng lệnh.

    `den_vat_tu` BẮT BUỘC truyền vào `trang_thai_chinh`/`co_canh_bao`: bỏ trống là im lặng bỏ cờ
    `thieu_vat_tu` (xem docstring `trang_thai.py`), và khi đó tab Cảnh báo thiếu người mà không ai
    biết. `xong` cũng truyền vào để đường găng chỉ duyệt MỘT lần cho mỗi lệnh thay vì bốn.
    """
    bc = boi_canh.nap(db, lsx_ids)
    den = trang_thai.den_vat_tu_theo_lo(db, lsx_ids)
    ket: dict[int, dict] = {}
    for i in lsx_ids:
        xong = tien_do.du_kien_xong(bc, i, bay_gio)
        co = trang_thai.co_canh_bao(bc, i, bay_gio, den_vat_tu=den, xong=xong)
        tt = trang_thai.trang_thai_chinh(bc, i, bay_gio, den_vat_tu=den, xong=xong)
        ket[i] = {
            "xong": xong,
            "canh_bao": co,
            "trang_thai": tt,
            "tre": trang_thai.CO_TRE_HAN in co,
        }
    return bc, ket


def _bat_dau(cv: SanXuatCongViec) -> datetime:
    return _aware(cv.du_kien_bat_dau) if cv.du_kien_bat_dau is not None else _LUC_XA


def _ket_thuc(cv: SanXuatCongViec) -> datetime:
    return _aware(cv.du_kien_ket_thuc) if cv.du_kien_ket_thuc is not None else _LUC_XUA


def _buoc_hien_tai(bc: BoiCanh, lsx_id: int) -> SanXuatCongViec | None:
    """Bước để hiện ở cột "Công đoạn": ĐANG CHẠY > TẠM DỪNG > bước chờ sớm nhất > bước cuối đã xong.

    Đọc `cong_viec_du` chứ không `cong_viec`: ca in GHÉP là bước nặng nhất của lệnh và nó nằm ở
    công việc chung; bỏ nó đi thì lệnh đang chạy máy in lại hiện tên bước chế bản.

    Lệnh đã xong hết bước vẫn hiện bước CUỐI (không để trống): "Đóng gói" nói đúng lệnh dừng ở đâu,
    còn một ô rỗng thì người đọc không phân biệt được với "chưa có routing".
    """
    cvs = bc.cong_viec_du(lsx_id)
    if not cvs:
        return None
    for tt in (CV_DANG_CHAY, CV_TAM_DUNG):
        nhom = [cv for cv in cvs if cv.trang_thai == tt]
        if nhom:
            return min(nhom, key=lambda cv: (_bat_dau(cv), cv.id))
    cho = [cv for cv in cvs if cv.trang_thai != CV_HOAN_THANH]
    if cho:
        return min(cho, key=lambda cv: (_bat_dau(cv), cv.id))
    return max(cvs, key=lambda cv: (_ket_thuc(cv), cv.id))


def _may_id(bc: BoiCanh, cv: SanXuatCongViec | None) -> int | None:
    """Máy của bước đang xét: `cong_viec.may_id` — máy HIỆN TẠI, `thuc_thi.doi_may` ghi vào đây.

    Nhánh lùi về phiên chạy là PHÒNG THỦ CHIỀU SÂU, không phải một ca đang sống: `bat_dau`
    chụp `cv.may_id` vào phiên (`thuc_thi.py:281`) và `doi_may` ghi cả hai (`:473` và `:491`), nên
    hôm nay `cv.may_id IS NULL` kéo theo mọi phiên của nó cũng `may_id IS NULL` — vòng lặp dưới
    không bao giờ trả khác `None`. Giữ lại vì nó rẻ (đọc bộ nhớ) và vì đường ghi phiên có thể đổi;
    ĐỪNG đọc nó như bằng chứng rằng ca ấy có thật.
    """
    if cv is None:
        return None
    if cv.may_id is not None:
        return cv.may_id
    for p in sorted(bc.phien[cv.id], key=lambda p: _aware(p.bat_dau), reverse=True):
        if p.may_id is not None:
            return p.may_id
    return None


def _dong(bc: BoiCanh, lsx_id: int, tinh: dict, bay_gio: datetime) -> dict:
    """MỘT dòng bảng. Không một con số tiền nào — xem docstring module."""
    lsx = bc.lenh[lsx_id]
    don = bc.don.get(lsx.order_id)
    khach = bc.khach.get(don.customer_id) if don is not None and don.customer_id else None
    sale = bc.sale.get(don.sale_user_id) if don is not None and don.sale_user_id else None
    cv = _buoc_hien_tai(bc, lsx_id)
    may_id = _may_id(bc, cv)
    pct, uoc_tinh = tien_do.phan_tram(bc, lsx_id)
    return {
        "id": lsx.id,
        "ma": lsx.ma,
        "ten": lsx.ten,
        "khach_hang": khach.name if khach is not None else None,
        "khach_hang_id": khach.id if khach is not None else None,
        "sale": sale.name if sale is not None else None,
        "so_luong_dat": lsx.so_luong_dat,
        "don_vi_tinh": lsx.don_vi_tinh,
        "da_giao": bc.da_giao_cua(lsx_id),
        "is_rush": bool(lsx.is_rush),
        "buoc_hien_tai": cv.ten_cong_doan if cv is not None else None,
        "nhom_cong_doan": cv.nhom_cong_doan if cv is not None else None,
        "may": may.ten if (may := bc.may.get(may_id)) is not None else None,
        # Cột "Máy/người" — nửa NGƯỜI. Trả DANH SÁCH tên chứ không phải chuỗi "A +2" dựng sẵn:
        # cột hẹp thì FE cắt được (và cắt từ cuối, vì thứ tự là thứ tự giao), nhưng tooltip/hồ sơ
        # cần đủ tên — cắt sẵn ở đây là FE không còn đường lấy hai người kia mà không gọi thêm API.
        # Rỗng khi bước hiện tại chưa giao ai; ĐỪNG bịa chữ thay thế, đó là việc của UI.
        "nguoi": bc.nguoi_cua(cv.id) if cv is not None else [],
        "tien_do_pct": pct,
        "tien_do_uoc_tinh": uoc_tinh,
        "gio_may": tien_do.gio_may(bc, lsx_id, bay_gio),
        "han_hoan_thanh_sx": lsx.han_hoan_thanh_sx,
        "han_giao_khach": lsx.han_giao_khach,
        "du_kien_xong": tinh["xong"],
        "trang_thai": tinh["trang_thai"],
        "canh_bao": tinh["canh_bao"],
    }


def _khoa_sap(bc: BoiCanh, lsx_id: int) -> tuple:
    """Thứ tự mặc định: GẤP trước · hạn SX gần trước · mã lệnh.

    Sắp ở Python chứ không `ORDER BY`: tập đã nằm sẵn trong bộ nhớ (tầng 2 phải duyệt hết để đếm
    tab), và `NULLS LAST` thì SQLite với Postgres không nói cùng một câu — cắt trang mà thứ tự
    lệch giữa hai DB là lỗi chỉ hiện ra trên production.

    Mã lệnh đứng cuối khoá để thứ tự TOÀN PHẦN: hai lệnh cùng độ gấp cùng hạn mà không có nấc phân
    giải cuối thì trang 1 và trang 2 có quyền chồng nhau.
    """
    lsx = bc.lenh[lsx_id]
    return (0 if lsx.is_rush else 1, lsx.han_hoan_thanh_sx or _NGAY_XA, lsx.ma or "")


def danh_sach(
    db: Session, *, sale_ids: set[int] | None,
    tab: str | None = None, q: str | None = None,
    page: int = 1, page_size: int = PAGE_SIZE_MAC_DINH,
    nhom_cong_doan: str | None = None, may_id: int | None = None,
    uu_tien: str | None = None, tre: bool | None = None,
    tu_ngay: date | None = None, den_ngay: date | None = None,
    bay_gio: datetime | None = None,
) -> dict:
    """`{items, total, page, page_size, dem_theo_tab}` — bảng lệnh đã lọc, đếm và CẮT TRANG.

    `total` = số dòng khớp TOÀN BỘ bộ lọc (kể cả `tab`), không phải số dòng của trang đang xem.
    `dem_theo_tab` = số dòng theo từng tab của tập đã lọc TRỪ chính `tab` — nó là FACET: đổi ô tìm
    kiếm hay bộ lọc thì các con số đổi theo, còn bấm sang tab khác thì chúng đứng yên. Tính khác đi
    là người dùng bấm một tab rồi thấy mọi tab còn lại về 0.

    `bay_gio` để bài test chốt được con số (cùng lý do `tien_do.gio_may` nhận tham số ấy); phần còn
    lại của hệ gọi không truyền và lấy mốc máy chủ.
    """
    bay_gio = _aware(bay_gio) if bay_gio is not None else datetime.now(timezone.utc)
    page = max(1, page)
    # LỚP THỨ HAI, không phải lớp duy nhất: router đã chặn `page_size` bằng `Query(le=...)`
    # nên URL vượt trần ăn 422 chứ không tới đây. Giữ trần ở service cho những nơi gọi thẳng
    # hàm này (test, tác vụ nền, router sau này) — service không được tin người gọi.
    page_size = max(1, min(page_size, PAGE_SIZE_TOI_DA))

    ids = list(
        db.execute(
            _loc_sql(
                sale_ids, q=q, tu_ngay=tu_ngay, den_ngay=den_ngay, may_id=may_id,
                nhom_cong_doan=nhom_cong_doan, uu_tien=uu_tien,
            )
        ).scalars()
    )
    bc, tinh = _soi(db, ids, bay_gio)

    if tre is not None:
        ids = [i for i in ids if tinh[i]["tre"] is tre]

    dem = {t: 0 for t in trang_thai.TAB_CHINH}
    for i in ids:
        dem[tinh[i]["trang_thai"]] += 1
    dem[TAB_TAT_CA] = len(ids)

    if tab and tab != TAB_TAT_CA:
        ids = [i for i in ids if tinh[i]["trang_thai"] == tab]

    ids.sort(key=lambda i: _khoa_sap(bc, i))
    dau = (page - 1) * page_size
    trang = ids[dau:dau + page_size]
    return {
        "items": [_dong(bc, i, tinh[i], bay_gio) for i in trang],
        "total": len(ids),
        "page": page,
        "page_size": page_size,
        "dem_theo_tab": dem,
    }


def summary(
    db: Session, *, sale_ids: set[int] | None, bay_gio: datetime | None = None
) -> dict:
    """Bốn thẻ KPI trên đầu màn. Cùng phạm vi với bảng — xem docstring module cho định nghĩa từng số.

    Phạm vi phải hẹp GIỐNG bảng: KPI của cả nhà máy đặt trên một cái bảng chỉ có một dòng là con số
    mà người đọc không có cách nào đối chiếu.
    """
    bay_gio = _aware(bay_gio) if bay_gio is not None else datetime.now(timezone.utc)
    dau, cuoi = _ngay_xuong(bay_gio)

    ids = list(db.execute(pham_vi.loc_lsx_da_phat_hanh(select(Lsx.id), sale_ids)).scalars())
    bc, tinh = _soi(db, ids, bay_gio)

    dang_sx = du_kien_tre = 0
    # Đếm theo ID: một công việc GHÉP phục vụ nhiều lệnh vẫn là MỘT công đoạn, một batch KCS của
    # bước ghép vẫn là MỘT lần kiểm. Cộng theo lệnh là nhân số thật lên đúng bằng số thành viên ca.
    cv_xong: set[int] = set()
    kcs_da_dem: set[int] = set()
    kcs_nhan = kcs_dat = 0.0
    for i in ids:
        if tinh[i]["trang_thai"] != trang_thai.TAB_HOAN_THANH:
            dang_sx += 1
            if tinh[i]["tre"]:
                du_kien_tre += 1
        for cv in bc.cong_viec_du(i):
            if (
                cv.trang_thai == CV_HOAN_THANH
                and cv.hoan_thanh_luc is not None
                and dau <= _aware(cv.hoan_thanh_luc) < cuoi
            ):
                cv_xong.add(cv.id)
            for k in bc.kcs[cv.id]:
                if k.id in kcs_da_dem or not (dau <= _aware(k.ket_thuc) < cuoi):
                    continue
                kcs_da_dem.add(k.id)
                # `Numeric` ⇒ `Decimal`; ép `float` ngay tại chỗ đọc (bẫy `Decimal / float`).
                kcs_nhan += float(k.so_luong_nhan or 0)
                kcs_dat += float(k.so_luong_dat or 0)

    return {
        "dang_sx": dang_sx,
        "cong_doan_xong_hom_nay": len(cv_xong),
        "du_kien_tre": du_kien_tre,
        "ty_le_kcs_dat_hom_nay": (100.0 * kcs_dat / kcs_nhan) if kcs_nhan > 0 else None,
    }
