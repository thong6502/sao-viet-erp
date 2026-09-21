"""Service Lệnh sản xuất (LSX) — Kế hoạch nhận đơn Sale đã bàn giao → bung lệnh dự kiến → tạo lệnh.

Ba tầng như print MIS: Job (`orders`) → Part (`lsx`) → Operation (`lsx_cong_doan`).

Nguyên tắc:
- **Nguồn sinh lệnh là DÒNG ĐƠN** (`order_lines`), không quét thẳng phiếu tính giá — vì khách có thể
  chốt MỘT PHẦN báo giá, và đơn mới là bản cam kết bán.
- **Số lượng lấy từ ĐƠN**: chạy lại engine (hàm THUẦN) với `so_luong = order_lines.qty` để ra số tờ
  đúng cam kết. KHÔNG gọi `compute_phieu_snapshot` (hàm đó ghi đè ảnh chụp lên phiếu tính giá).
- **Máy chỉ đề xuất**: routing/đơn vị/số lượng vào-ra copy sang lệnh là MẶC ĐỊNH, kế hoạch sửa hết.
- **Snapshot**: quy cách + routing chụp lúc tạo; sửa phiếu tính giá về sau không lay lệnh đã tạo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import ceil, floor

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models.bai_ghep import BaiGhep, BaiGhepThanhVien
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from ..models.bu_hao import BuHao
from ..models.cong_doan import CongDoan, CongDoanMay
from ..models.customer import Customer
from ..models.loai_san_pham import LoaiSanPham
from ..models.lsx import (
    DV_CAI,
    DV_CON,
    DV_KEM,
    DV_TAY,
    DV_TO,
    DV_TO_NGUYEN,
    LB_MAY,
    LB_THUE_NGOAI,
    LB_TO,
    LOAI_BUOC,
    LOAI_MOI,
    TT_CHO_BO_SUNG,
    TT_DA_LAP_KE_HOACH,
    TT_NHAP,
    TT_SAN_SANG,
    TEN_BUOC_TRONG,
    TRANG_THAI_LSX,
    Lsx,
    LsxCongDoan,
    LsxCongDoanPhuThuoc,
    LsxCongDoanVatTu,
)
from ..models.may_thiet_bi import MayThietBi, ma_don_vi_goc
from ..models.order import STATUS_CANCELLED, STATUS_ORDERED, Order, OrderLine
from ..models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia
from ..models.quotation import QuoteVersion
from ..models.user import User
from ..models.vat_lieu_kho import HANG_GIAY, HANG_VAT_TU, GiayNguyen, VatTuInAn
from ..services.bu_hao_engine import hao_buoc
from ..models.don_vi_do import (
    TRAM_CAI, TRAM_CON, TRAM_TAY, TRAM_TO, TRAM_TO_NGUYEN,
)
from ..services.dong_giay import (
    ban_do_tram, dich_chuoi, don_vi_chuoi, ma_cua_tram, tram_cua, tren_dong_giay,
)
from ..models.don_vi_do import DonViDo
from ..services.bien_cong_thuc import MAC_DINH_TANG_LENH, ngu_canh_lenh, quy_cach_bien
from ..services.don_vi_do_service import cong_thuc_chu, cong_thuc_the_so
from ..services.lsx_danh_muc_doi import vat_tu_lech
from ..services.quy_doi_service import (
    _so as _so_vn, bien_trong, doi_theo_quy_cach, don_vi_map,
)
from ..services.thanh_phan_engine import safe_eval
from ..services.thanh_phan_engine import cau_to_sang_cai, chua_theo_chieu, compute_phieu
from ..services.tinh_gia_service import _bu_hao_to_dict, _resolve_thanh_phan

# Công đoạn sau xén → đếm bằng CON (thành phẩm); còn lại đếm bằng TỜ. Heuristic theo tên để điền
# MẶC ĐỊNH cho kế hoạch, không phải luật — mọi dòng sửa được.


# Trường KHÔNG chép sang quy cách lệnh sản xuất: toàn bộ là TIỀN (lệnh xuống xưởng không mang
# giá vốn) + số lượng (đã có `so_luong_dat` của ĐƠN, chép lại chỉ gây mâu thuẫn).
_QC_BO_QUA = frozenset({
    "don_gia_giay", "don_gia_don_vi", "don_gia_cong_in", "che_ban_don_gia",
    "cong_thuc_gia", "gia_von_tp", "so_luong",
})


# Dụng cụ mà bước ở LỆNH phải chốt MỘT CON cụ thể trong kho (`khuon_be_id`). `kem` KHÔNG có mặt
# (bản kẽm là vật tư tiêu hao, mỗi bài phơi một bản mới nên không có gì để "đi lấy ở kệ").
#
# `khung_lua` cũng KHÔNG có mặt (chủ chốt 18/09/2026): khung lụa vẫn là đồ lưu kho dùng lại, sale
# vẫn tính phí khung ở phiếu tính giá, nhưng ở lệnh bước khung lụa là bước BÌNH THƯỜNG — không thẻ
# "Khuôn của bước", không chọn / làm khung mới, không nhắc lệch với sale, không chặn "Sẵn sàng".
TOOLING_CO_KHO = frozenset({"khuon_be", "khuon_ep"})


def can_chot_khuon(requires_tooling, tooling_type) -> bool:
    """Bước ở lệnh có phải chốt một con khuôn trong kho không.

    MỘT chỗ quyết cho mọi màn của lệnh — drawer bước, cửa "Sẵn sàng lập kế hoạch", hồ sơ lệnh,
    điều độ. Các màn đó đọc cờ `requires_tooling` server trả về chứ không tự suy, nên chỉ cần cờ ấy
    đi qua đây là cả hệ nói cùng một câu.
    """
    return bool(requires_tooling) and tooling_type in TOOLING_CO_KHO


def _don_vi_theo_buoc(cd_obj, *, con: int = 1, xa: int = 1,
                      cau: dict | None = None,
                      tram: dict[str, str] | None = None) -> tuple[str, str, float]:
    """Đơn vị VÀO/RA + hệ số quy đổi của 1 bước — ĐỌC KHAI BÁO ở danh mục công đoạn.

    `cong_doan.don_vi_vao/ra` là KHAI BÁO, cả tầng lệnh lẫn tầng tính giá cùng đọc — một nguồn sự
    thật. Không suy đơn vị từ tên bước: tên là chữ người dùng gõ.

    Bảng cầu (`cau`) khoá theo **TRẠM**, còn `don_vi_vao/ra` là **MÃ** do xưởng đặt — nên phải dịch
    một nhịp qua `tram` trước khi tra. Bỏ `tram` là rơi về so mã: chạy đúng với dữ liệu seed (mã
    trùng trạm) rồi im lặng trả hệ số 1.0 ngay khi xưởng khai `to_chay` thay cho `to`.

    Hệ số KHÔNG lưu ở danh mục: nó thuộc về PHIẾU (`con` từ bình bài, `xa` = số mảnh xả từ khổ
    giấy). Caller truyền vào.
    """
    dv_vao = getattr(cd_obj, "don_vi_vao", None) or None
    dv_ra = getattr(cd_obj, "don_vi_ra", None) or None
    if dv_vao is None or dv_ra is None:
        return None, None, 1.0
    if dv_vao == dv_ra:
        return dv_vao, dv_ra, 1.0
    # `tram=None` = nơi gọi chưa có bản đồ ⇒ coi mã chính là trạm (dữ liệu seed mặc định). Đây là
    # lối lùi, KHÔNG phải cách dùng đúng — mọi nơi gọi thật đều truyền `self._tram()`.
    tv = tram_cua(dv_vao, tram) if tram else dv_vao
    tr = tram_cua(dv_ra, tram) if tram else dv_ra
    # Có BẢNG CẦU của lệnh thì tra thẳng ở đó — nó là nguồn sự thật, biết cả cầu `tay` của sách
    # (`to→cai` sách nhỏ hơn 1, `con` không suy ra được). Hai nhánh tay dưới chỉ còn để phục vụ
    # lúc TẠO bước, khi lệnh chưa tồn tại nên chưa có bảng; số đó bị `_ap_chuoi_nguoc` ghi đè ngay.
    if cau is not None:
        return dv_vao, dv_ra, float(cau.get((tv, tr), 1.0) or 1.0)
    if (tv, tr) == (TRAM_TO, TRAM_CAI):
        return dv_vao, dv_ra, float(max(con, 1))
    if (tv, tr) == (TRAM_TO_NGUYEN, TRAM_TO):
        return dv_vao, dv_ra, float(max(xa, 1))
    return dv_vao, dv_ra, 1.0


def tu_khai_don_vi(buoc, cd_obj) -> bool:
    """Bước NGOÀI dòng giấy mà người kế hoạch TỰ KHAI đơn vị ngay tại lệnh (10/09/2026).

    Ghi kẽm là ca điển hình: số bản kẽm đổi theo số màu / số mặt / số bài của TỪNG đơn, mà công
    đoạn thì dùng chung cho mọi lệnh — không công thức chung nào nói hộ được. Nên drawer mở hai ô
    đơn vị + hai ô số, và bước nào đã khai thì danh mục thôi kéo lại đơn vị. Công thức sản lượng
    ra ở danh mục GỠ 18/09/2026 (mg `0324`): đây là đường DUY NHẤT để bước ngoài dòng có số.

    Dấu hiệu DẪN XUẤT từ chính cặp đơn vị — bước có, danh mục để trống — nên KHÔNG cần cột cờ:
    xoá một trong hai ô đơn vị ở drawer là bước trả ngay về cho danh mục. Danh mục có khai đơn vị
    thì bước vẫn kế thừa như cũ; đây chỉ mở đúng chỗ danh mục im lặng.

    Đòi ĐỦ CẢ HAI ô mới tính là khai tay. Nửa cặp không phải một lời khai mà là ô còn dở: bước tự
    thêm giữa chuỗi vốn chỉ mang `don_vi_vao` rồi để LƯỢT 2 của `_ap_chuoi_nguoc` nối vế RA theo
    bước trước — nhận nửa cặp là bước ấy đứng lại ngoài dòng giấy và hao của nó biến mất khỏi số
    giấy phải mua, im lặng.
    """
    if not (getattr(buoc, "don_vi_vao", None) and getattr(buoc, "don_vi_ra", None)):
        return False
    return _don_vi_theo_buoc(cd_obj)[:2] == (None, None)


# ⚠️ `_dinh_muc_snapshot()` GỠ 18/09/2026 (mg `0320`): ảnh chụp năng suất người-giờ + kíp chuẩn
#    của một đầu việc. Công đoạn thôi khai đầu việc, và thời lượng bước TỔ nay là SỐ GIỜ KẾ
#    HOẠCH người lập lệnh gõ tay (`so_gio_ke_hoach`) — không còn phép chia nào cần năng suất.


def ma_don_vi_toc_do(may) -> str | None:
    """Mã ĐƠN VỊ mà tốc độ của máy đếm: `to_gio` → `to`. None khi máy chưa khai.

    Máy lưu mã dạng `<đơn vị>_gio` (`may_thiet_bi.don_vi_toc_do`), sinh từ chính danh mục Đơn vị &
    quy đổi. Phép cắt hậu tố nằm ở `models.may_thiet_bi.ma_don_vi_goc` — ĐÚNG một chỗ, để nơi khác
    khỏi tự cắt mỗi nơi một kiểu (danh mục Máy tra TÊN đơn vị cũng gọi nó).
    """
    return ma_don_vi_goc(getattr(may, "don_vi_toc_do", None))


# ⚠️ `dich_gio_cua_khoan()` GỠ 18/09/2026 (mg `0321`): nó dịch ảnh chụp đầu việc ra cặp
#    (đơn vị đích, công thức) để QUY ĐỔI SL vào rồi chia năng suất. Bước TỔ thôi tính giờ theo
#    sản lượng — người lập lệnh gõ thẳng SỐ GIỜ KẾ HOẠCH — nên cả phép quy đổi ấy không còn
#    khách. Bước MÁY vẫn quy đổi, nhưng đích của nó là `ma_don_vi_toc_do(may)`, đường riêng.
# LOẠI BƯỚC (Máy / Tổ / Thuê ngoài) CHỈ do người kế hoạch chọn, ở ô "Loại bước" trong drawer bước.
# Máy KHÔNG suy nó từ tên công đoạn — tên là chữ người dùng gõ nên mọi phép suy đều gãy khi xưởng
# đặt tên khác đi (gỡ 12/08/2026). Mặc định của bước mới là `may`, trùng đúng mặc định FE dùng cho
# bước tự thêm (`lsxBuoc.emptyRow`) nên hai đầu không lệch nhau.

# Số giờ làm việc quy ước 1 ngày, dùng quy đổi lead-time phút → ngày. CHƯA đấu `work_calendar`
# (nghỉ lễ/ca kíp) — lát này chỉ cần con số thô để cảnh báo "có nguy cơ trễ hạn giao".
GIO_LAM_MOI_NGAY = 8.0


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _so_luot_chay(comp: dict) -> int:
    """Số lượt tờ chạy qua máy in (1 mặt = 1, in trở = 2).

    Engine chỉ xuất `so_luot` = TỔNG lượt tờ (`to_dau_vao × số mặt`) chứ không xuất số mặt, nên
    chia ngược ra. Lấy nhầm `so_luot` sẽ nhân thời gian chạy lên hàng nghìn lần.
    """
    to_vao = _f(comp.get("to_dau_vao"))
    tong_luot = _f(comp.get("so_luot"))
    if to_vao <= 0 or tong_luot <= 0:
        return 1
    return max(round(tong_luot / to_vao), 1)


def _routing_van_tay(cong_doans) -> list[dict]:
    """Vân tay routing để so "đã đổi so với bài tính giá" — chỉ giữ phần CẤU TRÚC (bước nào, làm
    ở đâu). Cố tình KHÔNG chụp số lượng/thời gian: sửa số là việc thường ngày của kế hoạch, chỉ
    thêm/bớt/đổi-thứ-tự/đổi-thuê-ngoài mới đáng cảnh báo."""
    return [
        {"ten": cd.ten, "nhom": cd.nhom, "loai_buoc": cd.loai_buoc}
        for cd in sorted(cong_doans, key=lambda c: c.thu_tu)
    ]


def khoan_chuan_bi_cua_may(may) -> list[dict]:
    """Các khoản chuẩn bị của máy (đổi kẽm · canh màu · lên giấy · pha mực…) để drawer XỔ CHI TIẾT
    thay vì chỉ hiện một cục tổng. Sống trong `may_thiet_bi.fields_theo_loai['chuan_bi_khoan']`;
    form Máy tự cộng lại rồi ghi tổng vào `makeready_time_default` — cột mà engine đọc."""
    if may is None:
        return []
    rows = (getattr(may, "fields_theo_loai", None) or {}).get("chuan_bi_khoan")
    if not isinstance(rows, list):
        return []
    return [
        {"ten": str(r.get("ten") or ""), "phut": round(_f(r.get("phut")), 2)}
        for r in rows if isinstance(r, dict)
    ]


class _BuocThu:
    """Bản sao CHỈ ĐỌC của một bước, thay vài thuộc tính để tính THỬ.

    Dùng cho `xem_truoc_may`: gán thẳng lên đối tượng ORM thì autoflush ghi luôn xuống DB, trong
    khi người dùng mới chỉ đang so hai máy trên form. Thuộc tính không đè thì đọc từ bước thật.
    """

    def __init__(self, goc, **thay):
        self._goc = goc
        self._thay = thay

    def __getattr__(self, ten):
        thay = object.__getattribute__(self, "_thay")
        if ten in thay:
            return thay[ten]
        return getattr(object.__getattribute__(self, "_goc"), ten)


def thoi_luong_buoc(cd, may=None, sl_tinh=None) -> dict:
    """Thời lượng 1 bước, tính TẠI CHỖ (không lưu cột) — nguồn số cho Gantt.

    CÔNG THỨC (chốt 2026-08-04, chỉ áp cho bước loại MÁY)::

        thời lượng = thời gian khác + chuẩn bị (từ MÁY) + SL đầu vào × 60 ÷ tốc độ × số lượt

    Trả về BA con số bằng cách thay `tốc độ` bằng max / trung bình / min của máy:
    - `chiem_may_phut`      — theo tốc độ TRUNG BÌNH → Gantt ĐẶT THANH bằng số này.
    - `chiem_may_phut_min`  — theo tốc độ TỐI ĐA (chạy nhanh nhất ⇒ thời lượng nhỏ nhất).
    - `chiem_may_phut_max`  — theo tốc độ TỐI THIỂU.
    Máy chưa khai min/max thì cả ba bằng nhau (râu co về một điểm) — ĐỪNG vẽ râu 0 như thể
    máy chạy chính xác tuyệt đối, UI phải nói rõ là chưa khai dải.

    `may` là MÁY ĐANG GÁN, đọc SỐNG chứ không dùng snapshot trên bước: tốc độ và chuẩn bị nay
    KẾ THỪA từ module Máy và người kế hoạch KHÔNG sửa được tại bước. Không truyền `may` (hoặc
    bước chưa gán máy) ⇒ tốc độ 0 ⇒ chạy 0 + cảnh báo, chuẩn bị 0.

    Bước TỔ KHÔNG tính gì — nó ĐỌC số người lập kế hoạch gõ (18/09/2026, mg `0319`)::

        thời lượng = thời gian khác + SỐ GIỜ KẾ HOẠCH × 60

    Ba con số bằng nhau (râu co về một điểm): một con số gõ tay không có dải nhanh–chậm. Để 0 là
    HỢP LỆ và KHÔNG có cảnh báo — chủ xưởng 18/09/2026: *"không cần cảnh báo, bản chất nó là số giờ
    kế hoạch, nếu thiếu thì cứ để 0"*.

    ⚠️ Công thức cũ (`SL vào ÷ (năng suất khoán × kíp chuẩn) × 60`) GỠ cùng ngày với tầng đầu việc
    của công đoạn (mg `0320`) và logic kíp (mg `0321`). Nó đòi ba thứ khai trước ở danh mục — năng
    suất người-giờ, kíp chuẩn, cách đo giờ — mà xưởng không khai nổi cho từng việc tay; kết quả là
    mọi bước tổ ra 0 phút kèm một cảnh báo không ai chữa được. Gõ tay một con số thì luôn có số.
    Bước THUÊ NGOÀI đi theo ngày gửi/nhận, thời lượng máy = 0.

    **`sl_tinh` — SL vào ĐÃ QUY ĐỔI về đơn vị của tốc độ** (15/08/2026), dạng
    `(số, tên đơn vị, câu diễn giải)`. Nơi gọi dựng bằng `LsxService._sl_theo_don_vi`, tức đúng
    cơ chế tiền khoán: cầu quy đổi → công thức của đơn vị.

    - có   ⇒ chia số ĐÃ ĐỔI cho tốc độ. Máy khai `m²/giờ` mà bước đếm tờ thì tờ được quy ra m².
    - None ⇒ **chạy = 0** + `phuong_phap = "chua_quy_doi"` + cảnh báo. KHÔNG lùi về chia số thô:
      chia số tờ cho `500 kg/h` ra con số trông như thật, và số trông-như-thật thì không ai đi kiểm.

    None là mặc định nên MỌI nơi gọi phải truyền — sót một chỗ là bước đó im lặng về 0 phút.
    Sáu nơi gọi trong hệ (lệnh · bài ghép · xếp lịch · kế hoạch vật tư) đều đã nối.

    `sl_tinh` KHÔNG áp cho bước TỔ nữa: giờ của tổ là số gõ tay, chẳng chia cho gì, nên `None` ở
    bước tổ là BÌNH THƯỜNG chứ không phải "quy đổi tịt".

    ĐÃ GỠ khỏi công thức (cột còn trong DB, dormant): `setup_phut` · `chay_phut` (nhập đè) ·
    `di_chuyen_phut` · `ve_sinh_phut`.

    **CHỜ KỸ THUẬT ĐÃ GỠ 13/08/2026** (`cho_phut` — mực khô · keo đông · màng nguội) nên
    `tong_phut == chiem_may_phut`. Hai khoá vẫn tách vì bàn xếp lịch lấy HIỆU của chúng làm độ trễ
    giữa hai bước; hiệu = 0 ⇒ bước sau bắt đầu ngay khi máy nhả tờ.
    """
    canh_bao: list[str] = []
    loai = getattr(cd, "loai_buoc", LB_MAY) or LB_MAY
    # SL đưa vào phép chia là số ĐÃ QUY ĐỔI về đơn vị của tốc độ. `so_luong_vao` thô chỉ còn dùng
    # để hiển thị "bước này nhận bao nhiêu", không tham gia tính giờ nữa.
    vao = _f(sl_tinh[0]) if sl_tinh else 0.0
    dv_tinh = sl_tinh[1] if sl_tinh else None
    quy_doi_dien_giai = sl_tinh[2] if sl_tinh else None
    luot = max(int(getattr(cd, "so_luot_chay", 1) or 1), 1)
    khac = _f(getattr(cd, "phat_sinh_phut", 0))
    gio_ke_hoach = _f(getattr(cd, "so_gio_ke_hoach", 0))

    # THUÊ NGOÀI ăn CHUNG đường của bước máy: nhà thầu được khai như một MÁY trong danh mục (tên
    # kèm hậu tố "thuê ngoài – …"), nên chuẩn bị/tốc độ/lượt đều lấy từ máy đó. Hai điểm khác duy
    # nhất (không sinh tiền khoán, không ghi sản lượng vào tổ) nằm ngoài hàm này.
    theo_may = loai in (LB_MAY, LB_THUE_NGOAI)
    khoan = khoan_chuan_bi_cua_may(may) if theo_may else []
    setup = _f(getattr(may, "makeready_time_default", None)) if (theo_may and may) else 0.0
    may_dung_duoc = may if theo_may else None
    # Bước TỔ không có "năng suất" nào nữa — ô đó và cả dải min/max đã gỡ khỏi bước (mg `0321`).
    ns = _f(getattr(may_dung_duoc, "toc_do", None)) if theo_may else 0.0

    def _chay(toc_do: float) -> float:
        return (vao * 60.0 / toc_do * luot) if toc_do > 0 and vao > 0 else 0.0

    if loai == LB_TO:
        # Giờ của tổ = SỐ GIỜ KẾ HOẠCH người lập lệnh gõ (§5.1). Ba mức bằng nhau: một con số gõ
        # tay không có dải nhanh–chậm, và bịa ra ±x% là dựng một khoảng chẳng ai khai.
        chay = chay_nhanh = chay_cham = gio_ke_hoach * 60.0
        phuong_phap = "to"
    else:
        # Máy chưa khai dải thì min/max rơi về tốc độ TB — ba số bằng nhau, không bịa khoảng.
        toc_do_cao = _f(getattr(may_dung_duoc, "toc_do_max", None)) if may_dung_duoc else 0.0
        toc_do_thap = _f(getattr(may_dung_duoc, "toc_do_min", None)) if may_dung_duoc else 0.0
        chay = _chay(ns)
        chay_nhanh = _chay(toc_do_cao) if toc_do_cao > 0 else chay
        chay_cham = _chay(toc_do_thap) if toc_do_thap > 0 else chay
        phuong_phap = "may" if ns > 0 else "thieu_nang_suat"

    # QUY ĐỔI TỊT thắng mọi lý do khác: có tốc độ mà không biết bước nhận bao nhiêu THEO ĐƠN VỊ ĐÓ
    # thì phép chia vô nghĩa. Nói "chưa quy đổi" chứ đừng nói "chưa khai năng suất" — sai chỗ khai.
    if sl_tinh is None and theo_may:
        chay = chay_nhanh = chay_cham = 0.0
        phuong_phap = "chua_quy_doi"
        canh_bao.append(
            # CHƯA GÁN MÁY là lý do khác hẳn, phải nói khác (09/09/2026). Bước máy chưa có máy thì
            # `sl_tinh_cua_buoc` trả None vì KHÔNG CÓ ĐÍCH để quy về — cả cách đo giờ
            # (`cong_doan_may.cong_thuc_gio`) lẫn tốc độ đều treo ở CẶP (công đoạn × máy). Dán câu
            # "chưa quy đổi" vào ca này là chỉ người dùng đi khai cầu quy đổi trong khi chỉ cần
            # chọn máy — mà khai xong cũng chẳng cứu được gì.
            #
            # Mã `phuong_phap` vẫn giữ `chua_quy_doi`: xếp lịch
            # (`xep_lich_service`) phân nhánh theo mã này, đẻ mã mới là phải sửa cả bên đó cho
            # một câu chữ. Câu là thứ người đọc, mã là thứ máy đọc — chỉ câu cần đổi.
            "Bước chưa gán máy nên chưa biết chạy trên máy nào — chọn máy ở tab Phân công & "
            "Thiết bị. Cách đo giờ chạy và tốc độ đều khai theo cặp (công đoạn × máy)."
            if theo_may and may_dung_duoc is None else
            "Chưa quy đổi được số lượng vào sang đơn vị của tốc độ nên không tính được thời gian "
            "chạy. Khai cầu quy đổi (hoặc công thức cho đơn vị đó) ở Cấu hình danh mục → "
            "Đơn vị & quy đổi."
        )
    elif phuong_phap == "thieu_nang_suat":
        # Chỉ còn bước MÁY vào được nhánh này. Bước TỔ để 0 giờ là hợp lệ, KHÔNG cảnh báo (§5.1).
        canh_bao.append(
            "Máy đang gán chưa khai tốc độ (hoặc bước chưa gán máy) nên không tính được thời gian chạy."
        )

    chiem_may = khac + setup + chay
    tong = chiem_may
    co_dai = round(chay_nhanh, 2) != round(chay_cham, 2)
    dien_giai = {
        "phuong_phap": phuong_phap,
        # `so_luong_vao` ở đây là số ĐÃ QUY ĐỔI (thứ thật sự đem chia), `don_vi_vao` là đơn vị của
        # nó — KHÔNG phải đơn vị bước. Frontend đọc thẳng hai khoá này để bản preview không phải
        # dựng lại phép quy đổi (nó không có bảng cặp trong tay).
        "so_luong_vao": round(vao, 2),
        "don_vi_vao": dv_tinh or getattr(cd, "don_vi_vao", None),
        "so_luong_vao_goc": round(_f(getattr(cd, "so_luong_vao", 0)), 2),
        "don_vi_vao_goc": getattr(cd, "don_vi_vao", None),
        "quy_doi_dien_giai": quy_doi_dien_giai,
        "nguon_nang_suat": "gio_ke_hoach" if loai == LB_TO else "may",
        "nang_suat_co_so": round(ns, 2) if ns > 0 else None,
        "nang_suat_hieu_dung": round(ns, 2) if ns > 0 else None,
        # 06/09/2026: MỌI loại bước đều có số lượt, mặc định 1. Trước đó bước tổ bị ép `None` —
        # nhưng công thức tiền công (chỉ chạy ở bước tổ) cần chip `so_luot_chay` có số thật.
        "so_luot_chay": luot,
        # SỐ GIỜ KẾ HOẠCH của bước tổ — bày ra để drawer dựng lại được đúng phép cộng, và để bảng
        # bóc tách thời gian nói rõ giờ này từ đâu ra (gõ tay, không phải máy tính).
        "so_gio_ke_hoach": round(gio_ke_hoach, 2),
        # Chuẩn bị KẾ THỪA từ máy — kèm chi tiết từng khoản để drawer xổ ra, không hiện cục tổng.
        "setup_phut": round(setup, 2),
        "chuan_bi_khoan": khoan,
        "phat_sinh_phut": round(khac, 2),
        "chay_phut": round(chay, 2),
        "chay_phut_min": round(chay_nhanh, 2),
        "chay_phut_max": round(chay_cham, 2),
        # Ba tốc độ của máy gửi kèm để CLIENT tính lại được y hệt khi người dùng đổi số lượt /
        # thời gian khác (drawer cập nhật ngay, không phải lưu rồi mới thấy). Client KHÔNG tự
        # đi lấy máy — công thức chỉ có một bản, số gốc do server phát.
        "toc_do": round(ns, 2) if ns > 0 else None,
        "toc_do_min": round(_f(getattr(may_dung_duoc, "toc_do_min", None)), 2) if may_dung_duoc else None,
        "toc_do_max": round(_f(getattr(may_dung_duoc, "toc_do_max", None)), 2) if may_dung_duoc else None,
        "co_dai_toc_do": co_dai,
        "chiem_tai_nguyen_phut": round(chiem_may, 2),
        "tong_phut": round(tong, 2),
        "canh_bao": canh_bao,
    }
    return {
        "chay_phut": round(chay, 2),
        "chiem_may_phut": round(chiem_may, 2),
        "chiem_may_phut_min": round(khac + setup + chay_nhanh, 2),
        "chiem_may_phut_max": round(khac + setup + chay_cham, 2),
        "tong_phut": round(tong, 2),
        "dien_giai": dien_giai,
    }


class LsxError(Exception):
    """Lỗi nghiệp vụ LSX (router map sang HTTP)."""


class LsxNotFound(LsxError):
    pass


class LsxValidationError(LsxError):
    pass


class LsxConflict(LsxError):
    pass


def canh_bao_lech_khuon(nguon: str | None, phi: float | None, tinh_trang: str | None) -> str | None:
    """Sale định một đằng, kế hoạch chốt một nẻo → MỘT câu nhắc. KHÔNG chặn.

    Máy chỉ ghi nhận: nó không biết xưởng sẽ báo lại khách hay tự nuốt chi phí, nên nó nói ra chỗ
    lệch rồi để người quyết. Chưa chọn nguồn (phiếu cũ) hoặc chưa trỏ dao → không có gì để so, im.
    """
    if not nguon or not tinh_trang:
        return None
    if nguon == "co_san" and tinh_trang == "dang_dat_lam":
        return "Sale báo dùng khuôn có sẵn, nhưng khuôn của bước này đang đặt làm."
    if nguon == "lam_moi" and tinh_trang == "dang_dung" and float(phi or 0) > 0:
        tien = f"{float(phi or 0):,.0f}".replace(",", ".")
        return f"Sale đã tính {tien} đồng tiền làm khuôn, nhưng bước này dùng khuôn có sẵn."
    return None


class LsxService:
    def __init__(self, db: Session, repo, audit, sequence) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.sequence = sequence
        self._tram_cache: dict | None = None     # cờ trạm dòng giấy (xem `_tram`)
        self._dv_cache: dict | None = None      # danh mục đơn vị (xem `_don_vis`)
        self._cap_cache: dict | None = None     # đồ thị cặp quy đổi (xem `_cap_quy_doi`)
        self._ma_dv_cache: dict | None = None   # tên đơn vị → mã (xem `_ma_don_vi`)
        self._mon_cache: dict | None = None     # giấy + vật tư đang dùng (xem `_mon_active`)

    # ================= tra cứu phụ trợ =================

    def _tram(self) -> dict[str, str]:
        """Bản đồ `{mã đơn vị: trạm dòng giấy}` — CACHE theo service.

        `tinh_nguoc_routing` chạy một lần mỗi lệnh, mà màn danh sách bung cả trăm lệnh: hỏi lại
        danh mục từng lệnh là đúng bài N+1 đã dính một lần ở màn đơn hàng.
        """
        if self._tram_cache is None:
            self._tram_cache = ban_do_tram(self.db)
        return self._tram_cache

    def _mon_active(self) -> dict[tuple[str, int], object]:
        """Mọi MÓN đang dùng, khoá `(hang_loai, id)` — CACHE theo service, như `_piece_rates`.

        GỘP hai danh mục (08/09/2026): từ khi bước chọn được NVL chính, khối vật tư của bước ăn cả
        `giay_nguyen` lẫn `vat_tu_in_an`. Hỏi rời hai bảng ở ba nơi (`_vat_tu_bung`,
        `_goi_y_luong_vat_tu`, `_soi_danh_muc`) cho MỖI bước là đúng bài N+1 đã dính một lần ở màn
        đơn hàng — cả hai bảng đều vài chục dòng nên nạp trọn một lượt rẻ hơn hẳn.
        """
        if self._mon_cache is None:
            ra: dict[tuple[str, int], object] = {}
            for m in self.db.execute(
                    select(VatTuInAn).where(VatTuInAn.active.is_(True))).scalars():
                ra[(HANG_VAT_TU, m.id)] = m
            for g in self.db.execute(
                    select(GiayNguyen).where(GiayNguyen.active.is_(True))).scalars():
                ra[(HANG_GIAY, g.id)] = g
            self._mon_cache = ra
        return self._mon_cache

    def _vat_tu_active(self) -> list:
        """Chỉ VẬT TƯ KHÁC — đường của ĐẦU VIỆC, vốn không bao giờ khai giấy.

        Giấy tuỳ TỪNG ĐƠN ("chạy sóng" hôm nay ăn kraft, mai ăn duplex) nên không khai trước ở danh
        mục công đoạn được — nó chỉ vào bước qua cửa người lập lệnh tự chọn.
        """
        return [m for (hl, _i), m in self._mon_active().items() if hl == HANG_VAT_TU]

    def _bu_hao_rows(self) -> list[dict]:
        # KHÔNG lọc `active`: bảng bù hao ở đây là để DỰNG LẠI số của lệnh đã có. Mã bù hao bị
        # ngừng dùng sau khi lệnh chạy mà lọc ở đây thì số tờ hao đổi ⇒ lệnh cũ tự nhiên lệch.
        # Ô CHỌN mã bù hao lọc ở router danh mục, không phải ở đây.
        return [_bu_hao_to_dict(b) for b in self.db.execute(select(BuHao)).scalars()]

    def _don_vis(self) -> dict:
        if self._dv_cache is None:
            from ..models.don_vi_do import DonViDo

            # KHÔNG lọc `active` — xem `DonViDoRepository.all_rows`. Đơn vị ngừng dùng mà lệnh cũ
            # còn trỏ tới thì `don_vi_map` mất khoá ⇒ đích quy đổi tịt ⇒ thời lượng của lệnh
            # lịch sử hiện RỖNG. Ô chọn lọc ở router, không phải ở bảng tra.
            rows = self.db.execute(select(DonViDo)).scalars()
            self._dv_cache = don_vi_map(list(rows))
        return self._dv_cache

    def _ma_don_vi(self, ten: str) -> str | None:
        """TÊN đơn vị (`"cuốn"`) → MÃ danh mục (`"cuon"`). Nhận cả khi đã là mã sẵn.

        `piece_rates.unit` lưu TÊN vì ô đó chọn từ danh mục theo tên; nhãn năng suất lưu MÃ theo
        khuôn `<mã>_gio`. Cầu nối để không nơi nào phải tự đoán.
        """
        if self._ma_dv_cache is None:
            from ..models.don_vi_do import DonViDo

            # KHÔNG lọc `active`: `piece_rates.unit` lưu TÊN, cầu TÊN→MÃ này là đường DUY NHẤT
            # để lệnh cũ tra ra đơn vị của mình. Đơn vị ngừng dùng mà lọc ở đây là đứt cầu.
            self._ma_dv_cache = {}
            for r in self.db.execute(select(DonViDo)).scalars():
                self._ma_dv_cache[(r.ten or "").strip().lower()] = r.ma
                self._ma_dv_cache[(r.ma or "").strip().lower()] = r.ma
        return self._ma_dv_cache.get((ten or "").strip().lower())

    def _cap_quy_doi(self) -> list:
        """DÒNG cặp quy đổi — nguồn chân lý của mọi phép đổi (bảng `don_vi_quy_doi`).

        Giữ nguyên dòng chứ không dẹp sẵn thành đồ thị: dòng quy đổi động ("1 tờ = định lượng ×
        dài × rộng" kg) chỉ ra hệ số sau khi thay quy cách của chính bước đang tính.
        """
        if self._cap_cache is None:
            from ..repositories.don_vi_do_repo import DonViDoRepository

            self._cap_cache = DonViDoRepository(self.db).cap_rows()
        return self._cap_cache

    def _may_mac_dinh(self, cd_obj, may_phieu: int | None) -> int | None:
        """MÁY điền sẵn cho một bước máy: máy của phiếu tính giá, NHƯNG phải chạy được.

        MỌI bước máy, không riêng bước IN (09/09/2026). Trước đó chỉ nhóm `print` được điền, nên
        một bước như Cắt tờ luôn ra đời với máy trống — mà cả cách đo giờ (`cong_doan_may.
        cong_thuc_gio`) lẫn tốc độ đều treo ở CẶP (công đoạn × máy), nên bảng bóc tách thời gian
        của nó không bao giờ ra số cho tới khi có người vào chọn máy bằng tay. Công đoạn khai đúng
        MỘT máy còn dùng thì không có lựa chọn thứ hai để mà đoán sai — điền luôn.
        `may_phieu` chỉ có nghĩa với bước IN (ô "Máy in" của phiếu); nơi gọi truyền None cho nhóm
        khác chứ hàm này không tự đoán hộ.

        Ô "Máy in" của phiếu tính giá mời HỢP của `may_lam_duoc` trên MỌI công đoạn nhóm In
        (`PhieuTinhGiaDetailView.mayIn`), chứ không riêng công đoạn In mà chính phiếu ấy xếp vào
        routing. Nên máy sale chọn hoàn toàn có thể là máy công đoạn kia khai — chép thẳng xuống
        thì bước sinh ra đã sai từ lúc chào đời: `cong_thuc_gio` treo ở cặp (công đoạn × máy), cặp
        không tồn tại ⇒ thời lượng ra "—" và băng "Danh mục đã đổi" kêu ngay ở lệnh vừa tạo.

        Ba nhánh, theo đúng lối `_khoan_mac_dinh` — rõ thì điền, mơ hồ thì để trống chứ không đoán:
          · Công đoạn CHƯA khai máy nào ⇒ không có gì để đối chiếu, tin phiếu.
          · Phiếu chọn máy nằm trong danh sách ⇒ dùng máy đó.
          · Còn lại (phiếu bỏ trống, hoặc chọn máy công đoạn không nhận) ⇒ chỉ điền khi công đoạn
            khai ĐÚNG MỘT máy còn dùng — lúc ấy không có lựa chọn thứ hai để mà đoán sai.
        """
        cho_phep = [int(m.may_id) for m in (getattr(cd_obj, "may_lam_duoc", None) or [])
                    if m.may_id is not None]
        if not cho_phep:
            return int(may_phieu) if may_phieu else None
        if may_phieu and int(may_phieu) in cho_phep:
            return int(may_phieu)
        con_dung = [mid for mid in cho_phep
                    if getattr(self.db.get(MayThietBi, mid), "active", False)]
        return con_dung[0] if len(con_dung) == 1 else None

    # ⚠️ `_khoan_mac_dinh()` + `_dau_viec_cua_cong_doan()` GỠ 18/09/2026 (mg `0320`): bước lệnh
    #    thôi chọn đầu việc, nên không còn gì để điền sẵn hay để lọc theo (công đoạn ∩ tổ). Việc
    #    khoán chọn LÚC GHI MẺ ở bàn tổ, lọc theo ĐÚNG MỘT chiều — tổ của bước
    #    (`san_xuat/viec_khoan.danh_sach_cua_to`).

    def _vat_tu_bung(self, cd_obj, buoc, quy_cach: dict | None) -> tuple[list[dict], list[str]]:
        """Vật tư của MỘT CÔNG ĐOẠN, kèm số lượng tính cho ĐÚNG bước này — nền BOM.

        Số lượng suy ở đây vì định mức tuỳ quy cách của từng lệnh. MỘT đường duy nhất: **công thức
        của chính DÒNG vật tư** (`cong_doan_vat_tu.cong_thuc_luong`). Riêng tới từng dòng nên đúng
        nhất: trong cùng một công đoạn in, mực ăn theo SỐ TỜ còn dung môi rửa máy ăn theo SỐ MÀU,
        dù cả hai cùng đo bằng `kg`.

        ⚠️ 18/09/2026 (mg `0316`): neo đổi từ ĐẦU VIỆC sang chính CÔNG ĐOẠN — nơi gọi truyền `cd_obj`
        (bản ghi danh mục Công đoạn) thay cho `dm`. Vật tư thôi phụ thuộc việc bước có chọn đầu việc
        hay không, nên MỌI bước gắn công đoạn đều bung được vật tư của nó.

        Hai đường "trả lời hộ" đã gỡ, cùng một lý do — thứ dùng chung không biết món nào đang hỏi:
        cách đo của ĐƠN VỊ (`don_vi_do.cong_thuc`, mg `0215`, 17/08/2026) và quy đổi từ đơn vị của
        BƯỚC sang đơn vị vật tư (BFS trên cầu quy đổi, 18/08/2026 — xem `_luong_vat_tu`).

        KHÔNG ĐOÁN: chưa khai công thức thì bỏ dòng đó ra khỏi kết quả và trả câu lý do — thà người
        kế hoạch tự thêm còn hơn bung một con số sai trông như thật.

        Trả `([], [])` khi chưa đủ ngữ cảnh (công đoạn chưa khai vật tư, hoặc chưa có bước).
        """
        vat_tus = list(getattr(cd_obj, "vat_tus", None) or []) if cd_obj is not None else []
        if not vat_tus or buoc is None:
            return [], []
        # KHÔNG chặn khi bước chưa có số lượng (gỡ 09/09/2026). Cửa ấy viết 12/08/2026, hồi lượng
        # vật tư còn suy RA TỪ số của bước (cách đo của đơn vị · BFS quy đổi — cả hai đã gỡ), nên
        # SL = 0 đúng là "không có gì để quy đổi". Nay công thức khai ở CHÍNH DÒNG vật tư, nhiều
        # món chẳng đụng `sl_vao`: `so_kem` ở bước Ghi kẽm CTP là một, mà bước ấy ngoài dòng giấy
        # nên SL luôn 0 ⇒ bản kẽm không bao giờ bung ra bước. Công thức nào thật sự cần SL thì
        # `_luong_vat_tu` đã trả "ra 0 — thiếu sl_vao", vẫn không đoán số.
        sl = _f(getattr(buoc, "so_luong_vao", 0))
        can = {v.vat_tu_id for v in vat_tus}
        mats = {m.id: m for m in self._vat_tu_active() if m.id in can}
        # Bơm SỐ CỦA CHÍNH BƯỚC lên trên ngữ cảnh lệnh — `sl_vao`/`sl_ra` chỉ tồn tại ở tầng này.
        # Bơm SAU `ngu_canh_lenh` vì hàm đó assert bộ khoá của nó phải khớp `MA_NGU_CANH_PHIEU`.
        # Ba ô khuôn mặc định 0 — tầng lệnh không có nguồn tương đương phiếu tính giá.
        ctx = {**ngu_canh_lenh(quy_cach or {}), **MAC_DINH_TANG_LENH,
               "sl_vao": sl, "sl_ra": _f(getattr(buoc, "so_luong_ra", 0)),
               "so_luot_chay": float(max(int(getattr(buoc, "so_luot_chay", 1) or 1), 1))}
        ra: list[dict] = []
        canh_bao: list[str] = []
        for v in vat_tus:
            mat = mats.get(v.vat_tu_id)
            if mat is None:
                continue        # đã ngừng dùng sau khi khai — im lặng bỏ, danh mục là nguồn sống
            dvt = (mat.don_vi_gia or "").strip()
            if not dvt:
                canh_bao.append(f"{mat.ten}: chưa chọn đơn vị tính ở danh mục Vật tư khác.")
                continue
            so_luong, dien_giai, ly_do = self._luong_vat_tu(
                dvt, ctx, mat=mat, cong_thuc=(v.cong_thuc_luong or ""))
            if so_luong is None:
                canh_bao.append(f"{mat.ten}: {ly_do}")
                continue
            ra.append({
                # Đường CÔNG ĐOẠN chỉ đẻ ra vật tư khác — giấy vào bước bằng cửa người lập lệnh
                # tự chọn, không qua đây.
                "hang_loai": HANG_VAT_TU,
                "vat_tu_id": mat.id, "ma": mat.ma, "ten": mat.ten, "don_vi": dvt,
                "so_luong": round(so_luong, 3), "dien_giai": dien_giai,
            })
        return ra, canh_bao

    def _goi_y_luong_vat_tu(self, buoc, quy_cach: dict | None) -> list[dict]:
        """`[{vat_tu_id, so_luong, dien_giai, ly_do}]` cho MỌI vật tư đang dùng, theo bước này.

        Vì sao server tính hộ (13/08/2026): người kế hoạch chọn "Keo vào gáy" từ dropdown thì số
        phải hiện ra NGAY. Frontend không tự tính được: nó không có công thức, không có bảng quy
        đổi, và cũng không nên có — công thức chỉ được có MỘT bản, ở server.

        Định mức khai theo DÒNG VẬT TƯ của CÔNG ĐOẠN (mg `0316`), nên một món công đoạn không khai
        thì không có công thức nào để gợi ý — trả `so_luong=None` kèm lý do chỉ thẳng chỗ khai. Món
        ĐANG nằm trong danh sách vật tư của công đoạn thì mượn công thức của dòng đó, để chọn lại
        đúng món đã khai vẫn ra số ngay.

        Món chưa tính ra được vẫn CÓ trong danh sách, `so_luong=None` kèm `ly_do` (18/08/2026):
        trước đó nó biến mất im lặng, drawer để ô trống mà không ai biết vì sao — người dùng chỉ
        thấy "chỗ này không tự tính" và đoán là hỏng. Ô vẫn trống để tự gõ, đúng luật "không đoán",
        nhưng câu lý do chỉ thẳng chỗ khai công thức.

        Danh mục vật tư là bảng nhỏ (đơn vị chục dòng) nên quét hết rẻ hơn hẳn đẻ thêm một endpoint
        chỉ để hỏi từng món.
        """
        # Bước chưa có SL vẫn gợi ý — cùng lý do gỡ chặn ở `_vat_tu_bung`: công thức của dòng vật
        # tư có thể chẳng đụng `sl_vao`. Món nào thật sự cần thì xuống dưới ra `ly_do`, ô để trống.
        sl = _f(getattr(buoc, "so_luong_vao", 0))
        # Bơm SỐ CỦA CHÍNH BƯỚC lên trên ngữ cảnh lệnh — `sl_vao`/`sl_ra` chỉ tồn tại ở tầng này.
        # Bơm SAU `ngu_canh_lenh` vì hàm đó assert bộ khoá của nó phải khớp `MA_NGU_CANH_PHIEU`.
        # Ba ô khuôn mặc định 0 — tầng lệnh không có nguồn tương đương phiếu tính giá.
        ctx = {**ngu_canh_lenh(quy_cach or {}), **MAC_DINH_TANG_LENH,
               "sl_vao": sl, "sl_ra": _f(getattr(buoc, "so_luong_ra", 0)),
               "so_luot_chay": float(max(int(getattr(buoc, "so_luot_chay", 1) or 1), 1))}
        # Công thức của những món CÔNG ĐOẠN của bước này đã khai.
        cd_obj = (self.db.get(CongDoan, buoc.cong_doan_id)
                  if getattr(buoc, "cong_doan_id", None) else None)
        ct_theo_mon: dict[int, str] = {
            v.vat_tu_id: (v.cong_thuc_luong or "")
            for v in (getattr(cd_obj, "vat_tus", None) or [])
        }
        ra: list[dict] = []
        for (hang_loai, mon_id), mat in self._mon_active().items():
            dvt = (mat.don_vi_gia or "").strip()
            if not dvt:
                continue
            # Giấy KHÔNG mượn công thức của công đoạn: công đoạn không bao giờ khai giấy (xem
            # `_vat_tu_active`), mà mượn nhầm là gán định mức mực cho một loại giấy trùng id.
            so_luong, dien_giai, ly_do = self._luong_vat_tu(
                dvt, ctx, mat=mat,
                cong_thuc=("" if hang_loai == HANG_GIAY else ct_theo_mon.get(mon_id, "")),
                hang_loai=hang_loai)
            ra.append({
                "hang_loai": hang_loai,
                "vat_tu_id": mon_id,
                "so_luong": None if so_luong is None else round(so_luong, 3),
                "dien_giai": dien_giai,
                "ly_do": ly_do or None,
            })
        return ra

    # `_cach_do` / `_cach_do_lan` GỠ 17/08/2026 cùng cột `don_vi_do.cong_thuc` (mg `0215`).
    # "Cách đo" treo ở ĐƠN VỊ là thứ dùng chung cho mọi ai đếm bằng đơn vị đó, trong khi câu hỏi
    # thật luôn thuộc về một MÓN / MÁY / ĐẦU VIỆC cụ thể — và cả ba nay đều có ô riêng
    # (`cong_thuc_luong` của giấy · vật tư · máy · đầu việc khoán). Đừng dựng lại: mượn-trong-cụm
    # của hàm cũ là chỗ hai đơn vị cùng cụm tranh nhau trả lời.

    def _luong_vat_tu(self, dvt: str, ctx: dict, *, mat=None, cong_thuc: str = "",
                      hang_loai: str = HANG_VAT_TU) -> tuple[float | None, str | None, str]:
        """Số lượng một vật tư đo bằng `dvt`. Trả `(số, diễn giải, lý do nếu tịt)`.

        MỘT đường duy nhất: công thức của DÒNG VẬT TƯ của công đoạn
        (`cong_doan_vat_tu.cong_thuc_luong`, mg `0316`) — nơi gọi truyền vào qua `cong_thuc`. Trước
        đó công thức treo ở CHÍNH MÓN HÀNG (`vat_tu_in_an.cong_thuc_luong`), nên
        mọi công đoạn dùng món đó lĩnh chung một con số: cùng "Mực Cyan" mà In khổ 79×109 ăn 1 kg /
        8.000 tờ, In khổ 11×11 ăn 1 kg / 40.000 tờ.

        Đường "quy đổi từ đơn vị của BƯỚC sang đơn vị vật tư" (BFS trên cầu quy đổi) GỠ 18/08/2026.
        Cầu quy đổi chỉ được chở quan hệ BẤT BIẾN (`1 ram = 500 tờ`, `1 tấn = 1.000 kg`). Còn "một
        tờ ăn mấy kg keo / mấy m² màng" thì đổi theo từng món và từng quy cách — hỏi cầu quy đổi câu
        đó là ép người dùng khai một cạnh sai bản chất, rồi MỌI món cùng đo bằng `kg` lĩnh chung một
        đáp án. Đúng thứ ô `cong_thuc_luong` sinh ra để thay.

        KHÔNG có ngoại lệ cho ca "trùng đơn vị" (bước đo `m²`, màng đo `m²`): trùng đơn vị KHÔNG có
        nghĩa là 1 m² chạy máy ăn đúng 1 m² màng — vẫn còn bù hao, còn phần không phủ. Một luật gọn
        (mọi món đều phải khai) dễ nhớ hơn hẳn một luật có ngoại lệ mà không ai đoán được lúc nào nó
        bật. Đo trước khi gỡ: 0/5 dòng vật tư đang sống nhờ đường này.

        KHÔNG ĐOÁN: chưa khai thì trả lý do kèm chỗ khai, drawer để ô trống cho người kế hoạch.
        """
        ten = getattr(mat, "ten", None) or dvt
        dv_ten = (self._don_vis().get(dvt.strip().lower()) or {}).get("ten") or dvt
        rieng = (cong_thuc or "").strip()
        # GIẤY (08/09/2026): công thức nằm ở CHÍNH MÓN (`giay_nguyen.cong_thuc_luong`), không ở đầu
        # việc. Giấy tuỳ TỪNG ĐƠN — cùng công đoạn "chạy sóng" mà đơn này ăn kraft, đơn kia ăn
        # duplex — nên không khai trước ở danh mục công đoạn được. Đây là lý do đúng để món tự mang
        # công thức, khác hẳn mực: cùng "Mực Cyan" mà hai khổ in ăn hai định mức, nên mực phải khai
        # theo đầu việc.
        if not rieng and hang_loai == HANG_GIAY:
            rieng = (getattr(mat, "cong_thuc_luong", None) or "").strip()
        if not rieng:
            if hang_loai == HANG_GIAY:
                return None, None, (
                    f"chưa khai công thức định mức. Mở danh mục Giấy → sửa “{ten}” → điền ô "
                    f"“Công thức tính lượng” (ra {dv_ten}).")
            return None, None, (
                f"chưa khai công thức định mức. Mở danh mục Công đoạn → sửa công đoạn → bảng "
                f"“Đầu việc và định mức của tổ” → bấm dòng “{ten}” trong khối vật tư → điền ô "
                f"“Công thức định mức” (ra {dv_ten}).")
        try:
            gt = float(safe_eval(rieng, dict(ctx)))
        except (ValueError, ZeroDivisionError) as e:
            return None, None, f"công thức lượng không chạy được ({e})."
        if gt <= 0:
            thieu = [b for b in bien_trong(rieng) if _f(ctx.get(b)) <= 0]
            return None, None, (
                f"công thức lượng ra 0 — thiếu {', '.join(thieu)}." if thieu
                else "công thức lượng ra 0.")
        # Cùng khuôn diễn giải với `_sl_theo_don_vi`: công thức chữ = thay số = kết quả.
        the_so = cong_thuc_the_so(rieng, ctx)
        dau = "" if the_so == _so_vn(gt) else f"{the_so} = "
        return gt, f"{cong_thuc_chu(rieng)} = {dau}{_so_vn(gt)} {dv_ten}", ""

    # ⚠️ `_dau_viec_option_dicts()` · `dau_viec_options()` · `_khoan_thu()` GỠ 18/09/2026 (mg
    #    `0320`): cả ba chỉ phục vụ ô "Đầu việc thợ làm" của drawer bước, nay đã biến. Vật tư của
    #    bước bung từ CÔNG ĐOẠN (`_bung_vat_tu_cong_doan`) nên không cần đi kèm từng lựa chọn nữa.

    def xem_truoc_buoc(
        self, *, lsx_id: int, step_key: str, may_id: int | None,
        loai_buoc: str | None = None, so_luot_chay: int | None = None,
        so_gio_ke_hoach: float | None = None,
    ) -> dict:
        """Giờ chạy của MỘT bước theo ĐÚNG những gì đang hiện trên form — KHÔNG ghi DB.

        Vì sao drawer phải hỏi server (chủ chốt 20/08/2026 — *"chọn máy thì thời gian không thay
        đổi, phải nhấn Lưu mới đổi"*): số đem chia cho tốc độ không phải số tờ thô mà là SL vào ĐÃ
        QUY ĐỔI về đơn vị ĐÍCH của bước (`sl_tinh_cua_buoc`) — Yawa 1050 đo bằng `kem_gio` và còn
        có công thức riêng `so_kem`. Cầu quy đổi và bộ chạy công thức chỉ có ở server, nên client
        đành xài lại con số của LẦN LƯU TRƯỚC nếu không hỏi.

        Ba tham số đè thêm — vắng cái nào thì lấy theo bản đã lưu, nên caller cũ vẫn chạy y như trước:
          · `loai_buoc` — Máy quy đổi SL vào sang đơn vị tốc độ của máy, Tổ thì KHÔNG quy đổi gì
            (giờ là số gõ tay). Bấm Máy→Tổ mà không hỏi lại thì câu quy đổi CỦA MÁY nằm nguyên
            dưới nhãn "Tổ";
          · `so_luot_chay` — chip dùng được trong ô đo giờ của máy (`sl_ra * so_luot_chay`);
          · `so_gio_ke_hoach` — số giờ người lập lệnh vừa gõ cho bước TỔ (§5.1). Nhận đè vì nó là
            TOÀN BỘ giờ chạy của bước tổ: không đè thì xem trước bày số của lần lưu trước.

        ⚠️ `piece_rate_id` GỠ 18/09/2026 (mg `0320`) — bước thôi chọn đầu việc.
        """
        lsx = self.get(lsx_id)
        cd = next((r for r in lsx.cong_doans if r.step_key == step_key), None)
        if cd is None:
            raise LsxNotFound("Không tìm thấy bước trong lệnh")
        may = self.db.get(MayThietBi, may_id) if may_id else None
        if may_id and may is None:
            raise LsxNotFound("Không tìm thấy máy")
        # Bản SAO ĐỌC của bước: KHÔNG gán `cd.may_id = ...` — gán vào ORM là autoflush ghi thẳng
        # xuống DB một lựa chọn người dùng mới chỉ rê chuột qua.
        thay: dict = {"may_id": may_id}
        if loai_buoc:
            thay["loai_buoc"] = loai_buoc
        if so_luot_chay is not None:
            thay["so_luot_chay"] = max(int(so_luot_chay), 1)
        if so_gio_ke_hoach is not None:
            thay["so_gio_ke_hoach"] = max(float(so_gio_ke_hoach), 0.0)
        thu = _BuocThu(cd, **thay)
        quy_cach = quy_cach_bien(lsx)
        t = thoi_luong_buoc(thu, may, self.sl_tinh_cua_buoc(thu, may, quy_cach))
        return {
            "step_key": step_key,
            "may_id": may_id,
            "chiem_may_phut": t["chiem_may_phut"],
            "thoi_luong_dien_giai": t["dien_giai"],
        }

    def _ct_gio_cua_may(self, cong_doan_id, may_id) -> str:
        """Công thức GIỜ CHẠY của cặp (công đoạn, máy) — `""` khi cặp chưa khai.

        Nhớ lại trong `_ct_gio_cache` vì `sl_tinh_cua_buoc` bị gọi cho TỪNG bước trong vòng lặp của
        bốn service ngoài (bài ghép · xếp lịch · kế hoạch vật tư); hỏi DB mỗi bước là N+1.
        """
        if not cong_doan_id or not may_id:
            return ""
        khoa = (int(cong_doan_id), int(may_id))
        if not hasattr(self, "_ct_gio_cache"):
            self._ct_gio_cache: dict[tuple[int, int], str] = {}
        if khoa not in self._ct_gio_cache:
            ct = self.db.execute(
                select(CongDoanMay.cong_thuc_gio).where(
                    CongDoanMay.cong_doan_id == khoa[0], CongDoanMay.may_id == khoa[1])
            ).scalar()
            self._ct_gio_cache[khoa] = (ct or "").strip()
        return self._ct_gio_cache[khoa]

    def nap_ct_gio(self, cap) -> None:
        """Nạp sẵn `_ct_gio_cua_may` cho cả lô cặp `(cong_doan_id, may_id)` — MỘT truy vấn.

        Nhớ lại theo cặp chỉ chặn hỏi LẠI; lượt đầu vẫn là một câu mỗi cặp. Cột Trạng thái của màn
        Máy trải mọi lệnh đã xếp nên số câu chạy theo số máy khác nhau trong lịch (đo dev
        14/09/2026: 11 câu `cong_doan_may` cho 2 lệnh). Service ngoài có cả routing trong tay thì
        gọi hàm này TRƯỚC vòng lặp. Cặp chưa khai nhận `""`, y như `_ct_gio_cua_may`.
        """
        if not hasattr(self, "_ct_gio_cache"):
            self._ct_gio_cache = {}
        thieu = {(int(a), int(b)) for a, b in cap if a and b} - self._ct_gio_cache.keys()
        if not thieu:
            return
        rows = self.db.execute(
            select(CongDoanMay.cong_doan_id, CongDoanMay.may_id, CongDoanMay.cong_thuc_gio).where(
                CongDoanMay.cong_doan_id.in_(sorted({a for a, _ in thieu})),
                CongDoanMay.may_id.in_(sorted({b for _, b in thieu})),
            )
        ).all()
        for cd_id, may_id, ct in rows:
            if (cd_id, may_id) in thieu:
                self._ct_gio_cache[(cd_id, may_id)] = (ct or "").strip()
        for khoa in thieu:
            self._ct_gio_cache.setdefault(khoa, "")

    def sl_tinh_cua_buoc(self, cd, may, quy_cach: dict | None) -> tuple[float, str, str] | None:
        """SL vào của bước quy về đơn vị của TỐC ĐỘ — đầu vào `sl_tinh` của `thoi_luong_buoc`.

        Đích: bước MÁY (và THUÊ NGOÀI — nhà thầu là một máy khai trong danh mục) → đơn vị TỐC ĐỘ của
        máy đang gán. Bước TỔ trả `None`: giờ của nó là SỐ GIỜ KẾ HOẠCH gõ tay (mg `0319`), không
        chia cho gì nên chẳng có đích nào phải quy về — và `thoi_luong_buoc` KHÔNG coi `None` ở bước
        tổ là lỗi.

        Public vì bốn service ngoài (bài ghép · xếp lịch · kế hoạch vật tư) phải dựng cùng một số —
        mỗi nơi tự suy đích là mở đường cho Gantt và drawer lệch nhau.
        """
        loai = getattr(cd, "loai_buoc", LB_MAY) or LB_MAY
        if loai in (LB_MAY, LB_THUE_NGOAI):
            dich = ma_don_vi_toc_do(may)
            # 06/09/2026: cách đo lấy từ cặp (CÔNG ĐOẠN × MÁY), không còn từ `may.cong_thuc_luong`.
            # Cùng một máy chạy hai công đoạn thì đo khác nhau — In khổ 79×109 và In khổ 11×11
            # không thể chung một công thức. Đọc SỐNG (không ghim): đổi máy là đổi cách đo.
            ct_rieng = self._ct_gio_cua_may(
                getattr(cd, "cong_doan_id", None), getattr(may, "id", None))
        else:
            return None
        return self._sl_theo_don_vi(cd, dich, quy_cach, ct_rieng=ct_rieng) if dich else None

    def _sl_theo_don_vi(self, cd, dv_dich: str | None,
                        quy_cach: dict | None, *,
                        ct_rieng: str = "") -> tuple[float, str, str] | None:
        """SL VÀO của bước quy về `dv_dich`. Trả `(số, tên đơn vị, câu diễn giải)` — None nếu tịt.

        Đường đi của THỜI LƯỢNG (chủ chốt 15/08/2026):

            SL vào → đơn vị TỐC ĐỘ / NĂNG SUẤT → ÷ tốc độ → phút

        Trước 11/09/2026 tiền khoán cũng đi qua đây (SL vào → đơn vị ĐƠN GIÁ → × đơn giá). Nay sản
        xuất chỉ ghi số lượng nên chỉ còn một khách duy nhất: phép đo giờ.

        HAI đường, theo đúng thứ tự RIÊNG → CHUNG (cùng luật với `_luong_vat_tu`):
          ⓿ `ct_rieng` — công thức của CHÍNH cặp việc-và-nơi-làm: `cong_doan_may.cong_thuc_gio` cho
             bước máy (06/09/2026, trước đó là `may_thiet_bi.cong_thuc_luong`),
             `khoan_json["cong_thuc_gio"]` (ảnh chụp của đầu việc) cho bước tổ. Riêng nhất nên
             thắng: lượt in của máy 5 màu khác máy 2 màu, mà cả hai cùng đo bằng `to_gio`.
          ① `doi_theo_quy_cach` — cầu quy đổi đã khai (kể cả đi vòng qua trung gian).

        Bậc "công thức của ĐƠN VỊ ĐÍCH" GỠ 17/08/2026 (mg `0215`) — bậc ⓿ thay đúng chỗ nó: cùng bộ
        chip `sl_vao`/`sl_ra`, nhưng khai trên chính cái máy / đầu việc cần nó thay vì trên đơn vị
        dùng chung.

        Tịt cả hai ⇒ None. Nơi gọi tự quyết, hàm này KHÔNG đoán và KHÔNG lùi về số thô.

        ⚠️ Công thức riêng ra thẳng số theo `dv_dich` — KHÔNG quy đổi tiếp. Nó được khai ĐỂ trả lời
        đúng câu "bằng bao nhiêu <đơn vị đích>", nên nhân thêm một hệ số nào nữa là tính hai lần.

        Đừng chép phép đổi này ra chỗ khác: hai bản chép tay là hai cơ hội lệch, mà lệch giữa hai
        màn cùng đọc thời lượng của một bước thì không ai soi ra.
        """
        ma_dich = (self._don_vis().get(str(dv_dich or "").strip().lower()) or {}).get("ma")
        if not ma_dich:
            return None
        sl = _f(cd.so_luong_vao)
        ten_dich = (self._don_vis().get(ma_dich) or {}).get("ten") or ma_dich

        # ⓿ công thức RIÊNG của máy / của đầu việc khoán.
        #
        # Ra 0 (hoặc không chạy được) thì RƠI XUỐNG hai đường sau chứ không tịt hẳn: công thức
        # thiếu biến là chuyện của một lệnh cụ thể (chưa khai số màu, chưa có khổ), mà cầu quy
        # đổi vẫn có thể trả lời được. Tịt luôn ở đây là làm mất số giờ vốn đang tính ra.
        if (r0 := self._ct_rieng(cd, ct_rieng, quy_cach)) is not None:
            gt0, chu0, the_so0 = r0
            dau0 = "" if the_so0 == _so_vn(gt0) else f"{the_so0} = "
            return gt0, ten_dich, f"{chu0} = {dau0}{_so_vn(gt0)} {ten_dich}"

        # ① cầu quy đổi. Cùng đơn vị cũng đi lối này (`doi` trả thẳng, hệ số 1).
        #
        # ĐẦU NGUỒN của phép đổi là `don_vi_vao` của BƯỚC. Bước NGOÀI dòng giấy (ghi kẽm) để trống ở
        # danh mục, nên ô này chỉ có khi người lập lệnh tự khai ở bước (`tu_khai_don_vi`); chưa
        # khai thì tịt ⇒ 0 phút chạy, xếp lịch bày "chưa quy đổi được". Lối lùi về đơn vị sản lượng
        # của công đoạn GỠ 18/09/2026 cùng cột ấy (mg `0324`).
        kq = doi_theo_quy_cach(sl, cd.don_vi_vao, ma_dich, quy_cach or {},
                               self._don_vis(), self._cap_quy_doi())
        if "gia_tri" in kq:
            return float(kq["gia_tri"]), kq["don_vi"], kq["dien_giai"]
        return None

    def _ct_rieng(self, cd, ct: str, quy_cach: dict | None) -> tuple[float, str, str] | None:
        """Chạy công thức RIÊNG của bước → `(giá trị, công thức bằng chữ, công thức đã thế số)`.

        Tách khỏi `_sl_theo_don_vi` ngày 08/09/2026 vì lúc ấy có nơi thứ hai cần ĐÚNG bộ ngữ cảnh và
        đúng cách thế số này mà KHÔNG quy đổi gì cả (công thức tiền công ra thẳng tiền). Nơi ấy đã
        gỡ 11/09/2026 cùng tiền khoán; hàm vẫn đứng riêng vì đọc được một mình, và bậc ⓿ của
        `_sl_theo_don_vi` gọi nó.

        Trả `None` khi công thức rỗng, chạy lỗi, hoặc ra ≤ 0 — nơi gọi tự quyết đi tiếp hay tịt.
        Chỉ trả nguyên liệu, KHÔNG ghép câu: nơi gọi tự đóng nhãn đuôi.

        Chip `don_gia_khoan` vẫn nằm trong ngữ cảnh nhưng LUÔN 0 (`MAC_DINH_TANG_LENH`): ô "Cách đo
        giờ chạy" dùng chung bộ chip nên gõ tay được, và gõ tay thì phải ra 0 chứ không NameError.
        """
        if not (ct := (ct or "").strip()):
            return None
        ctx = {**ngu_canh_lenh(quy_cach or {}), **MAC_DINH_TANG_LENH,
               "sl_vao": _f(cd.so_luong_vao), "sl_ra": _f(cd.so_luong_ra),
               "so_luot_chay": float(max(int(getattr(cd, "so_luot_chay", 1) or 1), 1))}
        try:
            gt = float(safe_eval(ct, dict(ctx)))
        except (ValueError, ZeroDivisionError):
            return None
        if gt <= 0:
            return None
        return gt, cong_thuc_chu(ct), cong_thuc_the_so(ct, ctx)

    def _customer_name(self, order: Order) -> str | None:
        if not order.customer_id:
            return None
        c = self.db.get(Customer, order.customer_id)
        return c.name if c else None

    def _customer_names(self, ids: set[int]) -> dict[int, str]:
        """customer_id → tên, MỘT truy vấn cho cả danh sách.

        `_customer_name` ở trên tra từng đơn một; gọi nó trong vòng lặp dựng bảng là N+1 — với
        100.000 lệnh thì đó là 100.000 lượt `SELECT`. Danh sách/hàng chờ phải dùng hàm này.
        """
        if not ids:
            return {}
        rows = self.db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(ids))).all()
        return {i: n for i, n in rows}

    def _user_names(self, ids: set[int]) -> dict[int, str]:
        """user_id → tên hiển thị, MỘT truy vấn (bản gộp của `_user_name`, xem lý do ở trên)."""
        if not ids:
            return {}
        rows = self.db.execute(select(User.id, User.name, User.username).where(User.id.in_(ids))).all()
        return {i: (n or u) for i, n, u in rows}

    def _user_name(self, user_id: int | None) -> str | None:
        if not user_id:
            return None
        u = self.db.get(User, user_id)
        return (u.name or u.username) if u else None

    def _dept_names(self, ids: set[int]) -> dict[int, str]:
        from ..models.department import Department

        if not ids:
            return {}
        rows = self.db.execute(select(Department.id, Department.name).where(Department.id.in_(ids))).all()
        return {i: n for i, n in rows}

    def _may_names(self, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}
        rows = self.db.execute(
            select(MayThietBi.id, MayThietBi.ten).where(MayThietBi.id.in_(ids))
        ).all()
        return {i: n for i, n in rows}

    def khuon_chon_duoc(self, lsx: Lsx, *, loai: str | None, dang_chon: int | None) -> list[dict]:
        """Dao mà bước của lệnh này CHỌN ĐƯỢC — đã lọc sẵn hai chiều: khách của lệnh + loại của bước.

        Vì sao có endpoint riêng thay vì gọi danh mục Khuôn rồi lọc: (1) lọc ở client là điều chủ
        dự án đã bác thẳng một lần; (2) nền chung của 10 màn danh mục chỉ nhận ĐÚNG MỘT bộ lọc
        riêng (`loc`), nới nó ra cho một màn là sửa nền của cả 10.

        Lọc theo khách là thứ làm nhánh "dùng dao có sẵn" DÙNG ĐƯỢC: kho vài trăm dao mà bày hết
        thì người ta tìm không ra, bấm "làm dao mới", rồi đặt lại con dao đã có — mất tiền thật.

        `dang_chon` LUÔN được giữ trong danh sách dù không khớp bộ lọc: dao đã gán từ trước có thể
        khai thiếu loại/khách, mà rơi khỏi danh sách thì ô chọn nhảy về rỗng và cú Lưu kế tiếp gỡ
        mất dao của bước — đúng bẫy đã gặp ở ô chọn khuôn đời cũ.
        """
        from ..models.khuon_be import KhuonBe

        order = self.db.get(Order, lsx.order_id) if lsx.order_id else None
        khach_id = getattr(order, "customer_id", None) if order else None

        dk = [KhuonBe.active.is_(True)]
        if khach_id:
            dk.append(KhuonBe.khach_hang_id == khach_id)
        if loai:
            dk.append(KhuonBe.loai == loai)
        rows = list(self.db.execute(
            select(KhuonBe).where(*dk).order_by(KhuonBe.ma)
        ).scalars())
        if dang_chon and not any(k.id == dang_chon for k in rows):
            if (cu := self.db.get(KhuonBe, dang_chon)) is not None:
                rows.insert(0, cu)
        return [
            # `loai` phải trả về: màn lọc tiếp theo loại của TỪNG BƯỚC trên danh sách đã rút gọn
            # này (một lệnh có thể vừa có bước bế vừa có bước ép nhũ), nên nạp một lần dùng chung.
            {"id": k.id, "ma": k.ma, "ten": k.ten, "loai": k.loai, "so_ke": k.so_ke,
             "tinh_trang": k.tinh_trang}
            for k in rows
        ]

    def tao_khuon_cho_lenh(self, lsx: Lsx, *, ten: str, loai: str | None, actor) -> dict:
        """Nhánh "làm dao mới": đẻ một dòng trong danh mục Khuôn ở tình trạng `dang_dat_lam`.

        KHÁCH lấy từ chính lệnh, LOẠI lấy từ cờ của bước — không hỏi lại người dùng thứ hệ thống
        đã biết. Đó là toàn bộ lý do nhánh này nằm ở đây chứ không bắt họ mở màn Khuôn khai tay
        rồi quay lại chọn: ba lần chuyển màn cho một việc là ba lần người ta bỏ dở.

        Dựng qua `KhuonBeService` chứ không `db.add` thẳng: service giữ luật riêng của danh mục
        (sinh mã KB-####) và ghi nhật ký — bỏ qua nó là dao mới lọt vào kho không mã, không vết.

        KHÔNG hỏi ngày dự kiến có dao (mg `0293` gỡ `ngay_ve_du_kien`): ô đó chỉ bắt người lập lệnh
        đoán một ngày mà không phép tính nào đọc. `dang_dat_lam` đã chặn bước.
        """
        from ..repositories.khuon_be_repo import KhuonBeRepository
        from ..services.khuon_be_service import KhuonBeService

        order = self.db.get(Order, lsx.order_id) if lsx.order_id else None
        svc = KhuonBeService(KhuonBeRepository(self.db), self.audit)
        k = svc.create(
            {
                "ten": ten,
                "loai": loai,
                "khach_hang_id": getattr(order, "customer_id", None) if order else None,
                "tinh_trang": "dang_dat_lam",
            },
            getattr(actor, "id", None),
        )
        return {"id": k.id, "ma": k.ma, "ten": k.ten, "loai": k.loai, "so_ke": k.so_ke,
                "tinh_trang": k.tinh_trang}

    def _khuon_map(self, ids: set[int]) -> dict[int, dict]:
        """Dao của các bước — nạp LÔ, không tra từng bước (routing 10 bước = 10 query thừa).

        Trả đủ thứ bước cần bày cho thợ: mã · tên ấn phẩm · SỐ KỆ (thứ thợ thật sự cần để đi lấy)
        · tình trạng.
        """
        from ..models.khuon_be import KhuonBe

        ids = {int(i) for i in ids if i}
        if not ids:
            return {}
        rows = self.db.execute(select(KhuonBe).where(KhuonBe.id.in_(ids))).scalars()
        return {
            k.id: {
                "khuon_be_ma": k.ma,
                "khuon_be_ten": k.ten,
                "khuon_be_so_ke": k.so_ke,
                "khuon_be_tinh_trang": k.tinh_trang,
            }
            for k in rows
        }

    def _thanh_phan(self, tp_id: int | None) -> PhieuThanhPhan | None:
        if not tp_id:
            return None
        return self.db.execute(
            select(PhieuThanhPhan)
            .where(PhieuThanhPhan.id == tp_id)
            .options(
                selectinload(PhieuThanhPhan.thanh_phams),
                selectinload(PhieuThanhPhan.vat_tus),
            )
        ).scalar_one_or_none()

    # ================= HÀNG CHỜ =================

    def hang_cho(self, *, page: int = 1, size: int = 50) -> tuple[list[dict], int]:
        """`(đơn của TRANG này, TỔNG số đơn còn nợ lệnh)`.

        Điều kiện "còn dòng chưa lên lệnh" đã chuyển xuống SQL (`repo.orders_ban_giao`) — ở đây
        chỉ còn đếm để HIỆN "x/y dòng đã lên lệnh".
        """
        orders, total = self.repo.orders_ban_giao(page=page, size=size)
        if not orders:
            return [], total
        line_ids = [ln.id for o in orders for ln in o.lines]
        da_co = self.repo.by_order_lines(line_ids)
        khach = self._customer_names({o.customer_id for o in orders if o.customer_id})
        nguoi = self._user_names({o.sale_user_id for o in orders if o.sale_user_id})
        out: list[dict] = []
        for o in orders:
            so_dong = len(o.lines)
            so_co = sum(1 for ln in o.lines if ln.id in da_co)
            # Tóm tắt tên các sản phẩm/hạng mục trong đơn (OrderLine.description)
            sp_names = list(dict.fromkeys((ln.description or "").strip() for ln in o.lines if (ln.description or "").strip()))
            san_pham_tom_tat = ", ".join(sp_names) if sp_names else None
            out.append({
                "order_id": o.id,
                "order_no": o.order_no,
                "customer_name": khach.get(o.customer_id),
                "sale_name": nguoi.get(o.sale_user_id),
                "delivery_committed_date": o.delivery_committed_date,
                "is_rush": bool(o.is_rush),
                "production_note": o.production_note,
                "san_xuat_released_at": o.san_xuat_released_at,
                "so_dong": so_dong,
                "so_dong_co_lsx": so_co,
                "san_pham_tom_tat": san_pham_tom_tat,
            })
        return out, total

    # ================= tính số cho 1 dòng đơn =================

    def _tinh_dong(self, line: OrderLine, tp: PhieuThanhPhan | None) -> dict:
        """Chạy engine (hàm thuần) cho 1 dòng đơn với SL CỦA ĐƠN → số tờ / bù hao / kẽm / lượt.

        Trả `{comp, quy_cach, routing, sl_ptg}`. `tp=None` (đơn nhập giá tay) → số 0, routing rỗng.
        """
        qty = int(line.qty or 0)
        if tp is None:
            return {"comp": {}, "quy_cach": None, "routing": [], "sl_ptg": None}

        resolved = _resolve_thanh_phan(self.db, tp)
        sl_ptg = int(resolved.get("so_luong") or 0)
        # ÉP số lượng theo ĐƠN: engine ưu tiên `tp["so_luong"]` nếu > 0, nên phải ghi đè.
        resolved["so_luong"] = qty
        result = compute_phieu(
            so_luong=qty, thanh_phans=[resolved], bu_hao_rows=self._bu_hao_rows()
        )
        comps = result.get("meta", {}).get("components") or []
        comp = comps[0] if comps else {}

        # QUY CÁCH = KẾ THỪA TRỌN từ bài tính giá: chép NGUYÊN cụm trường của sản phẩm thay vì
        # liệt kê tay — thêm trường mới ở phiếu tính giá là lệnh nhận được ngay, không phải nhớ
        # sửa thêm chỗ này (đó là lý do màu pha / bleed / khe cắt / máy từng bị rơi mất).
        # Chỉ BỎ tiền và dữ liệu lồng: lệnh xuống xưởng không mang giá vốn.
        quy_cach = {
            k: v
            for k, v in resolved.items()
            if k not in _QC_BO_QUA and not isinstance(v, (list, dict))
        }
        quy_cach.update({
            "giay_ten": resolved.get("giay_ten") or resolved.get("kho_nguyen"),
            "kho_nguyen_dai": resolved.get("kho_dai") or resolved.get("kho_nguyen_dai"),
            "kho_nguyen_rong": resolved.get("kho_rong") or resolved.get("kho_nguyen_rong"),
            # Nhãn nhóm + ghi chú kỹ thuật không nằm trong bộ field engine → lấy thẳng từ ORM.
            "nhom_bao_gia": getattr(tp, "nhom_bao_gia", None),
            "ghi_chu_ky_thuat": getattr(tp, "ghi_chu_ky_thuat", None),
            # Loại sản phẩm: tra TÊN ngay lúc chụp. Snapshot mang id trần thì màn lệnh không hiện
            # được gì, mà bắt frontend đi tra thêm một vòng cho một chữ là thừa.
            "loai_san_pham_ten": self._loai_san_pham_ten(resolved.get("loai_san_pham_id")),
            # Vật tư in ấn (mực · màng · keo): tên + lượng, KHÔNG kèm đơn giá.
            "vat_tus": [
                {"ten": vt.get("ten"), "so_luong": vt.get("so_luong")}
                for vt in (resolved.get("vat_tus") or [])
            ],
            # MỰC: hai trường này là LIST nên bộ lọc `not isinstance(v, (list, dict))` ở trên
            # nuốt mất — phải chép tay. Không có chúng thì bản lệnh chỉ biết "4/1 màu" mà không
            # biết cái "1" là K hay Pantone, và ai tính lại kẽm từ hai con số sẽ ra sai đúng ca
            # tự trở `|A ∪ B| ≠ max`. Lấy từ ENGINE (đã chuẩn hoá) chứ không lấy thẳng cột.
            "muc_a": comp.get("muc_a") or [],
            "muc_b": comp.get("muc_b") or [],
            "kem_moi_tay": comp.get("kem_moi_tay"),
            # Số DẪN XUẤT của engine (chạy lại theo SL đơn).
            "so_kem": comp.get("so_kem"),
            "so_luot": comp.get("so_luot"),
            "so_con": comp.get("con"),
            "so_manh_xa": comp.get("so_manh_xa"),
        })

        routing: list[dict] = []
        for i, row in enumerate(resolved.get("thanh_phams") or []):
            cd = row.get("cong_doan") or {}
            cd_id = row.get("cong_doan_id")
            if not cd and cd_id:
                obj = self.db.get(CongDoan, cd_id)
                if obj is not None:
                    cd = {"nhom": obj.nhom, "ten": obj.ten, "department_id": obj.to_mac_dinh_id,
                          "requires_tooling": obj.requires_tooling,
                          "tooling_type": obj.tooling_type,
                          "don_vi_vao": obj.don_vi_vao, "don_vi_ra": obj.don_vi_ra}
            else:
                # `_cong_doan_to_dict` không bơm department_id + cờ dụng cụ → lấy thêm.
                if cd_id:
                    obj = self.db.get(CongDoan, cd_id)
                    if obj is not None:
                        cd = {**cd, "department_id": obj.to_mac_dinh_id,
                              "requires_tooling": obj.requires_tooling,
                              "tooling_type": obj.tooling_type,
                              "don_vi_vao": obj.don_vi_vao, "don_vi_ra": obj.don_vi_ra}
            ten = row.get("ten") or cd.get("ten") or "Công đoạn"
            nhom = cd.get("nhom")
            routing.append({
                "thu_tu": i,
                "cong_doan_id": cd_id,
                "ten": ten,
                "nhom": nhom,
                "department_id": cd.get("department_id"),
                # Cờ dụng cụ của DANH MỤC — nguồn duy nhất cho checklist "thiếu khuôn".
                "requires_tooling": can_chot_khuon(cd.get("requires_tooling"), cd.get("tooling_type")),
                "tooling_type": cd.get("tooling_type"),
                # Đặt loại bước NGAY TỪ ĐÂY để màn "lệnh dự kiến" và màn lệnh đã tạo nói cùng một
                # thứ tiếng — trước đó preview chỉ có cờ thuê-ngoài nên hai màn hiển thị lệch nhau.
                "loai_buoc": LB_THUE_NGOAI if row.get("nha_cung_cap") else LB_MAY,
                "nha_cung_cap": row.get("nha_cung_cap"),
                # Ý ĐỊNH của sale về khuôn — chép nguyên si, KHÔNG diễn giải. Kế hoạch vẫn tự chốt
                # con dao (`khuon_be_id`); hai thứ đứng cạnh nhau để so ra chỗ lệch.
                "khuon_nguon": row.get("khuon_nguon"),
                "khuon_phi": float(row.get("phi_khuon") or 0),
                # Đơn vị KHAI ở danh mục — bảng "lệnh dự kiến" cần chúng để nói số tờ bằng đúng
                # tên xưởng đặt. Chỉ là NHÃN ở đây; hệ số quy đổi vẫn do `_don_vi_theo_buoc` lo.
                "don_vi_vao": cd.get("don_vi_vao"),
                "don_vi_ra": cd.get("don_vi_ra"),
            })
        return {"comp": comp, "quy_cach": quy_cach, "routing": routing, "sl_ptg": sl_ptg}

    # Checklist "job readiness" chấm ở tầng DÒNG ĐƠN (`_thieu`) đã GỠ 07/09/2026: bảng lệnh dự kiến
    # không còn cột Thiếu, và lệnh mới luôn sinh ra ở NHÁP. Cửa duy nhất còn gác là `thieu_cua` —
    # checklist của LỆNH đã có routing, chặn nút "Sẵn sàng lập kế hoạch".

    # ================= PREVIEW =================

    def preview(self, order_id: int) -> dict:
        order = self.repo.order_with_lines(order_id)
        if order is None:
            raise LsxNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_ORDERED or order.san_xuat_released_at is None:
            raise LsxConflict("Đơn chưa được chuyển xuống sản xuất")

        da_co = self.repo.by_order_lines([ln.id for ln in order.lines])
        lines: list[dict] = []
        for line in order.lines:
            tp = self._thanh_phan(line.phieu_thanh_phan_id)
            calc = self._tinh_dong(line, tp)
            comp = calc["comp"]
            existing = da_co.get(line.id)
            ptg_ma = None
            if tp is not None:
                ptg = self.db.get(PhieuTinhGia, tp.phieu_id)
                ptg_ma = ptg.ma if ptg else None
            dept_ids = {r["department_id"] for r in calc["routing"] if r.get("department_id")}
            dept_names = self._dept_names(dept_ids)
            lines.append({
                "order_line_id": line.id,
                "ten": line.description or (tp.ten if tp else "") or "Sản phẩm",
                "so_luong_dat": int(line.qty or 0),
                "don_vi_tinh": line.don_vi_tinh or "cái",
                "phieu_thanh_phan_id": line.phieu_thanh_phan_id,
                "ptg_ma": ptg_ma,
                # Nhãn nhóm chỉ để GOM HIỂN THỊ ở màn kế hoạch — vẫn 1 lệnh / 1 dòng đơn.
                "nhom": getattr(line, "nhom", None),
                # Chưa có bài tính giá → comp rỗng, các số dẫn xuất là "chưa tính được" → None
                # (UI hiện "—"), KHÔNG ép 0/1 giả. Có PTG mà số thật = 0 thì vẫn hiện 0.
                # Chỉ còn bù hao MÁY TỰ TRA — ô "+ Bù thêm" của phiếu tính giá đã bỏ 15/08/2026.
                "bu_hao_to": (
                    int(round(float(comp.get("bu_hao_auto") or 0))) if tp is not None else None
                ),
                "so_to_ke_hoach": int(round(float(comp.get("to_dau_vao") or 0))) if tp is not None else None,
                "so_to_nguyen": int(comp.get("to_nguyen") or 0) if tp is not None else None,
                "so_con": int(comp.get("con") or 1) if tp is not None else None,
                "so_kem": int(comp.get("so_kem") or 0) if tp is not None else None,
                "so_luot": int(round(float(comp.get("so_luot") or 0))) if tp is not None else None,
                # MÃ đơn vị từng chặng (client tra tên ở danh mục). Bảng này liệt kê NHIỀU dòng đơn,
                # mỗi dòng một bộ đơn vị riêng — nên đơn vị phải đi theo dòng, không nằm ở tiêu đề.
                **{f"don_vi_{k}": v for k, v in
                   don_vi_chuoi(calc["routing"], self._tram()).items()},
                "routing": [
                    {**r, "department_ten": dept_names.get(r.get("department_id"))}
                    for r in calc["routing"]
                ],
                "quy_cach": calc["quy_cach"],
                "sl_ptg": calc["sl_ptg"] if calc["sl_ptg"] and calc["sl_ptg"] != int(line.qty or 0) else None,
                "lsx_id": existing.id if existing else None,
                "lsx_ma": existing.ma if existing else None,
            })
        return {
            "order_id": order.id,
            "order_no": order.order_no,
            "customer_name": self._customer_name(order),
            "sale_name": self._user_name(order.sale_user_id),
            "delivery_committed_date": order.delivery_committed_date,
            "is_rush": bool(order.is_rush),
            "production_note": order.production_note,
            "lines": lines,
        }

    # ================= TẠO LỆNH =================

    def _loai_san_pham_ten(self, lsp_id) -> str | None:
        """Tên loại sản phẩm để chụp vào quy cách. Không có / đã xoá → None (màn lệnh hiện "—")."""
        if not lsp_id:
            return None
        obj = self.db.get(LoaiSanPham, int(lsp_id))
        return obj.ten if obj is not None else None

    def _default_buoc(self, r: dict, *, comp: dict, lsx_may_id: int | None,
                      loai_san_pham_id=None) -> dict:
        """Toàn bộ giá trị MẶC ĐỊNH của 1 bước khi bung routing từ bài tính giá.

        "Kế thừa" ở đây = GIÁ TRỊ KHỞI ĐIỂM; năng suất là snapshot chỉ đọc, còn thời gian chạy có
        thể nhập đè. Công đoạn chỉ cấp tổ/đơn vị/setup; loại bước do KHSX chọn. Riêng máy in đã
        chọn trên phiếu tính giá được mang xuống bước in làm gợi ý ban đầu — nhưng phải là máy
        công đoạn ấy chạy được, xem `_may_mac_dinh`. Danh mục thiếu thì để TRỐNG, KHÔNG đoán
        bừa — thời lượng hiện "—" là tín hiệu đúng để đi khai danh mục, số 0 giả thì không.
        """
        nhom, ten = r.get("nhom"), r.get("ten")
        cd_obj = self.db.get(CongDoan, r["cong_doan_id"]) if r.get("cong_doan_id") else None
        # Loại là thuộc tính của BƯỚC KHSX, không phải của danh mục Công đoạn. Routing từ phiếu có
        # thể đưa gợi ý ban đầu; sau đó kế hoạch đổi tự do trong drawer.
        loai_buoc = (LB_THUE_NGOAI if r.get("nha_cung_cap") else
                     r.get("loai_buoc") or LB_MAY)
        # Máy của PHIẾU chỉ mang xuống bước IN (ô đó là "Máy in"); bước khác vẫn được điền khi công
        # đoạn khai đúng một máy còn dùng — xem `_may_mac_dinh`.
        may_id = (self._may_mac_dinh(cd_obj, lsx_may_id if nhom == "print" else None)
                  if loai_buoc == LB_MAY else None)

        con = max(int(comp.get("con") or 1), 1)

        # --- Đơn vị vào/ra + hệ số: KẾ THỪA từ danh mục, không suy từ tên ---
        dv_vao, dv_ra, he_so = _don_vi_theo_buoc(
            cd_obj, con=con, xa=max(int(comp.get("so_manh_xa") or 1), 1), tram=self._tram())
        # Số lượng để 0 cho MỌI bước — `_ap_chuoi_nguoc` ghi đè ngay sau khi tạo, cả bước trên dòng
        vao = ra = 0.0

        # ⚠️ Bốn ô nhân-lực-và-năng-suất GỠ 18/09/2026: `nang_suat` · `don_vi_nang_suat` (cột bỏ,
        #    mg `0321`) · `so_nhan_cong_tieu_chuan` (kíp chuẩn, mg `0321`) · `khoan_json` (đầu việc
        #    ghim ở bước, mg `0320`). Bước TỔ nay chỉ có SỐ GIỜ KẾ HOẠCH, và bước mới sinh ra bằng
        #    0 — người lập lệnh gõ vào, không có nguồn danh mục nào để kế thừa.
        return {
            "loai_buoc": loai_buoc,
            "so_luong_vao": vao,
            "so_luong_ra": ra,
            "don_vi_vao": dv_vao,
            "don_vi_ra": dv_ra,
            "he_so_quy_doi": he_so,
            # Hao để 0 ở đây: `_ap_chuoi_nguoc` tra theo quy tắc bù hao của DANH MỤC công đoạn,
            # ở ĐÚNG đơn vị của từng bước. Bản cũ dồn cả cục bù hao vào một bước (bước in đầu) —
            # đó chính là con số 131 tờ mồ côi trong khi 6 bước đều hao 0.
            "hao_hut": 0.0,
            "hao_hut_pct": 0.0,
            # CẨN THẬN: `comp["so_luot"]` của engine là TỔNG LƯỢT TỜ (`to_dau_vao × số mặt`),
            # KHÔNG phải số lượt chạy. Số lượt chạy = so_luot ÷ số tờ (in trở 2 mặt → 2).
            "so_luot_chay": _so_luot_chay(comp) if nhom == "print" else 1,
            "setup_phut": _f(cd_obj.setup_time) if cd_obj else 0.0,
            # Giờ kế hoạch của bước TỔ — 0 là hợp lệ và KHÔNG cảnh báo (§5.1). Bước máy bỏ qua ô
            # này (giờ của nó chia theo tốc độ máy), nhưng cột vẫn sinh 0 cho mọi bước để đổi
            # Máy→Tổ ở drawer không gặp `None`.
            "so_gio_ke_hoach": 0.0,
            # Vệ sinh/rửa mực đã BỎ khỏi hệ — bước mới luôn sinh 0, cột giữ cho dữ liệu cũ.
            "ve_sinh_phut": 0.0,
            # CHỜ KỸ THUẬT kế thừa từ MÁY (bước máy) hoặc ĐẦU VIỆC (bước tổ) — mực khô · màng nguội
            # · keo đông. Là GIÁ TRỊ KHỞI ĐIỂM, kế hoạch sửa đè được ở drawer bước; kế thừa nghĩa là
            # mặc định, không phải read-only.
            "may_id": may_id,
        }

    def _bung_lai_vat_tu(self, lsx: Lsx, buocs: list[LsxCongDoan]) -> None:
        """Bước mới / vừa đổi công đoạn: thay dòng MÁY BUNG bằng vật tư của công đoạn MỚI.

        Vật tư đi theo CÔNG ĐOẠN (mg `0316`): đổi "Cán màng bóng" sang "Cán màng mờ" mà vẫn giữ
        màng bóng của công đoạn cũ là lệnh đi mua nhầm hàng. Chỉ thay dòng `tu_dong=True`; dòng
        người tự thêm/sửa giữ nguyên, trùng món thì dòng người thắng (không bung đè).

        THUÊ NGOÀI không bung — cùng luật với `_soi_danh_muc`: nhà thầu tự lo vật tư của họ.
        Chỉ gọi cho bước ĐỔI công đoạn: bước giữ nguyên thì danh mục đổi sau đi qua băng "Danh
        mục đã đổi" + nút Cập nhật, không âm thầm đổi số dưới chân người lập lệnh.
        """
        if not buocs:
            return
        quy_cach = quy_cach_bien(lsx)
        for cd in buocs:
            cd_obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
            if cd_obj is None:
                continue
            for v in [v for v in cd.vat_tus if v.tu_dong]:
                cd.vat_tus.remove(v)
            # FLUSH giữa xoá và thêm: UNIQUE (lsx_cong_doan_id, hang_loai, vat_tu_id) — công đoạn
            # mới dùng lại đúng món của công đoạn cũ là xoá rồi thêm chính cặp đó.
            self.db.flush()
            if cd.loai_buoc == LB_THUE_NGOAI:
                continue
            co = {(v.hang_loai, int(v.vat_tu_id)) for v in cd.vat_tus if v.vat_tu_id}
            thu_tu = max((v.thu_tu for v in cd.vat_tus), default=-1)
            rows, _canh_bao = self._vat_tu_bung(cd_obj, cd, quy_cach)
            for v in rows:
                cap = (v.get("hang_loai") or HANG_VAT_TU, int(v["vat_tu_id"]))
                if cap in co:
                    continue
                co.add(cap)
                thu_tu += 1
                cd.vat_tus.append(LsxCongDoanVatTu(
                    hang_loai=cap[0], vat_tu_id=cap[1], vat_tu_ma_snapshot=v["ma"],
                    vat_tu_ten_snapshot=v["ten"], don_vi_snapshot=v["don_vi"] or "",
                    so_luong=float(v["so_luong"]), thu_tu=thu_tu, tu_dong=True,
                ))
        self.db.flush()

    def _bung_vat_tu_cong_doan(self, lsx: Lsx, quy_cach: dict) -> None:
        """Bung VẬT TƯ của CÔNG ĐOẠN vào từng bước, ngay lúc tạo lệnh.

        Vì sao ở SERVER chứ không đợi frontend (13/08/2026): frontend chỉ bung vật tư khi người
        dùng TỰ TAY mở drawer bước. Không điền sẵn ⇒ lệnh tạo xong khối "Vật tư cần dùng" trống
        trơn, và kế hoạch vật tư không thấy gì để đi mua. Điền ở đây thì mọi lệnh đều có.

        `tu_dong=True` để lần bung sau (đồng bộ danh mục) thay được — dòng người tự thêm vẫn chừa
        ra. Vật tư nào chưa quy đổi ra lượng được thì BỎ QUA, không ghi số đoán: `_vat_tu_bung` đã
        trả lý do, drawer hiện cảnh báo cho người kế hoạch tự thêm.

        ⚠️ 18/09/2026 (mg `0316`): trước đây chỉ bung khi bước đã GHIM một đầu việc khoán
        (`khoan_json.rate_id`) — tầng ấy đã gỡ. Nay MỌI bước gắn công đoạn đều bung, nên lệnh
        không còn cảnh trống vật tư chỉ vì tổ khớp hai đầu việc nên máy không dám chọn hộ.
        """
        for cd in lsx.cong_doans:
            if not cd.cong_doan_id:
                continue
            cd_obj = self.db.get(CongDoan, cd.cong_doan_id)
            if cd_obj is None:
                continue
            rows, _canh_bao = self._vat_tu_bung(cd_obj, cd, quy_cach)
            for pos, v in enumerate(rows):
                cd.vat_tus.append(LsxCongDoanVatTu(
                    hang_loai=v.get("hang_loai") or HANG_VAT_TU,
                    vat_tu_id=v["vat_tu_id"], vat_tu_ma_snapshot=v["ma"],
                    vat_tu_ten_snapshot=v["ten"], don_vi_snapshot=v["don_vi"] or "",
                    so_luong=float(v["so_luong"]), thu_tu=pos, tu_dong=True,
                ))

    def tao(self, *, order_id: int, order_line_ids: list[int], actor) -> list[Lsx]:
        order = self.repo.order_with_lines(order_id)
        if order is None:
            raise LsxNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_ORDERED:
            raise LsxConflict("Đơn chưa chốt / đã hủy — không tạo lệnh sản xuất")
        if order.san_xuat_released_at is None:
            raise LsxConflict("Sale chưa chuyển đơn xuống sản xuất")

        by_id = {ln.id: ln for ln in order.lines}
        chosen = [by_id[i] for i in order_line_ids if i in by_id]
        if not chosen:
            raise LsxValidationError("Chưa chọn dòng nào của đơn để tạo lệnh")
        if len(chosen) != len(set(order_line_ids)):
            raise LsxValidationError("Có dòng không thuộc đơn hàng này")

        da_co = self.repo.by_order_lines([ln.id for ln in chosen])
        trung = [ln.id for ln in chosen if ln.id in da_co]
        if trung:
            raise LsxConflict("Dòng đã có lệnh sản xuất — không tạo trùng")

        quote_version_id = order.quotation_id and self._quote_version_id(order.quotation_id)
        created: list[Lsx] = []
        for line in chosen:
            tp = self._thanh_phan(line.phieu_thanh_phan_id)
            calc = self._tinh_dong(line, tp)
            comp = calc["comp"]
            so_luong_dat = int(line.qty or 0)
            lsx = Lsx(
                ma=self.sequence.generate_code("job"),
                loai=LOAI_MOI,
                # Nhận diện sản phẩm (tên · ĐVT) lấy từ PHIẾU TÍNH GIÁ — đó là nơi khai quy cách,
                # nên nó là nguồn. Dòng đơn chỉ là đường lui khi lệnh không gắn phiếu.
                # SỐ LƯỢNG thì ngược lại: lấy từ ĐƠN (`line.qty`) — đơn đặt đợt nào làm đợt đó,
                # phiếu báo giá cho cả lô lớn.
                ten=(tp.ten if tp else "") or line.description or "Sản phẩm",
                order_id=order.id,
                order_line_id=line.id,
                quote_version_id=quote_version_id or None,
                phieu_thanh_phan_id=line.phieu_thanh_phan_id,
                so_luong_dat=so_luong_dat,
                don_vi_tinh=(getattr(tp, "don_vi_tinh", None) or line.don_vi_tinh or "cái"),
                # Hai mốc số tờ để 0 — `_ap_chuoi_nguoc` ở dưới đọc ra từ chuỗi rồi ghi đè.
                so_to_ke_hoach=0,
                so_to_nguyen=0,
                so_con=int(comp.get("con") or 1),
                ban_giao_at=order.san_xuat_released_at,
                han_giao_khach=order.delivery_committed_date,
                is_rush=bool(order.is_rush),
                quy_cach_json=calc["quy_cach"],
                may_id=(calc["quy_cach"] or {}).get("may_id") or (tp.may_id if tp else None),
                # Lệnh mới LUÔN ở Nháp (07/09/2026): checklist chấm dòng đơn đã gỡ. Thiếu gì thì
                # `thieu_cua` nói ở màn lệnh, và lệnh tự rơi về Chờ bổ sung khi kế hoạch sửa routing.
                trang_thai=TT_NHAP,
                nguoi_phu_trach_id=actor.id,
                created_by=actor.id,
            )
            for r in calc["routing"]:
                d = self._default_buoc(
                    r, comp=comp, lsx_may_id=lsx.may_id,
                    loai_san_pham_id=(calc["quy_cach"] or {}).get("loai_san_pham_id"),
                )
                lsx.cong_doans.append(LsxCongDoan(
                    thu_tu=r["thu_tu"],
                    cong_doan_id=r.get("cong_doan_id"),
                    ten=r.get("ten") or "Công đoạn",
                    nhom=r.get("nhom"),
                    department_id=r.get("department_id"),
                    nha_cung_cap=r.get("nha_cung_cap"),
                    khuon_nguon=r.get("khuon_nguon"),
                    khuon_phi=r.get("khuon_phi") or 0,
                    **d,
                ))
            # Số lượng từng bước là DẪN XUẤT — chạy chuỗi ngược ngay sau khi dựng đủ routing.
            self._ap_chuoi_nguoc(lsx)
            # ...rồi mới bung VẬT TƯ của công đoạn: `_vat_tu_bung` cần `so_luong_vao` của bước để
            # quy ra lượng, mà số đó chỉ có sau chuỗi ngược.
            # `quy_cach_bien` chứ KHÔNG phải `calc["quy_cach"]` thô: năm biến dẫn xuất (SL đặt ·
            # con/tờ · tờ in · tờ nguyên · tờ sau in) nằm ở CỘT của lệnh. Thiếu chúng thì công thức
            # nào dùng `so_luong`/`to_dau_vao` cũng ra 0 ⇒ bị coi là thiếu biến và không bung gì.
            self._bung_vat_tu_cong_doan(lsx, quy_cach_bien(lsx))
            lsx.routing_goc_json = _routing_van_tay(lsx.cong_doans)
            self.repo.add(lsx)
            # Giữ hành vi tuyến tính hiện tại làm mặc định; sau đó kế hoạch có thể bỏ/thêm cạnh
            # để tạo nhánh song song hoặc điểm ghép xuyên LSX.
            ordered_steps = sorted(lsx.cong_doans, key=lambda x: x.thu_tu)
            for prev, cur in zip(ordered_steps, ordered_steps[1:]):
                cur.phu_thuoc.append(LsxCongDoanPhuThuoc(buoc_truoc_id=prev.id))
            created.append(lsx)
            self.audit.create(
                actor_user_id=actor.id, action="create_lsx", target=f"lsx:{lsx.id}",
                detail=f"Tạo lệnh {lsx.ma} — {lsx.ten} (đơn {order.order_no}, "
                       f"{so_luong_dat:,} {lsx.don_vi_tinh})".replace(",", "."),
            )
        self.repo.commit()
        return created

    def _quote_version_id(self, quotation_id: int) -> int | None:
        from ..models.quotation import Quote

        q = self.db.get(Quote, quotation_id)
        return q.current_version_id if q else None

    # ================= ĐỌC / SỬA =================

    def get(self, lsx_id: int) -> Lsx:
        lsx = self.repo.get(lsx_id)
        if lsx is None:
            raise LsxNotFound("Không tìm thấy lệnh sản xuất")
        return lsx

    def thieu_cua(self, lsx: Lsx) -> list[str]:
        """Checklist CHẶN — còn mã nào thì không cho đánh dấu "Sẵn sàng lập kế hoạch" (§12)."""
        order = self.db.get(Order, lsx.order_id)
        tp = self._thanh_phan(lsx.phieu_thanh_phan_id)
        # Nạp cờ dụng cụ theo LÔ (1 query) — bước của lệnh chỉ giữ `cong_doan_id`, mà hỏi lẻ từng
        # bước là N+1 trên màn danh sách lệnh.
        cd_ids = [cd.cong_doan_id for cd in lsx.cong_doans if cd.cong_doan_id]
        co_dung_cu: dict[int, tuple[bool, str | None]] = {}
        if cd_ids:
            co_dung_cu = {
                r.id: (bool(r.requires_tooling), r.tooling_type)
                for r in self.db.query(CongDoan)
                .filter(CongDoan.id.in_(set(cd_ids)))
                .all()
            }
        routing = [
            {
                "ten": cd.ten,
                "nhom": cd.nhom,
                "requires_tooling": can_chot_khuon(*co_dung_cu.get(cd.cong_doan_id, (False, None))),
                "tooling_type": co_dung_cu.get(cd.cong_doan_id, (False, None))[1],
            }
            for cd in lsx.cong_doans
        ]
        thieu: list[str] = []
        qc = lsx.quy_cach_json or {}
        if lsx.phieu_thanh_phan_id is None:
            thieu.append("khong_co_ptg")
        else:
            if not qc.get("giay_id"):
                thieu.append("thieu_giay")
            if not (qc.get("dai_thanh_pham") and qc.get("rong_thanh_pham")):
                thieu.append("thieu_kho")
            if not routing:
                thieu.append("thieu_routing")
        if (order.delivery_committed_date if order else None) is None and lsx.han_giao_khach is None:
            thieu.append("thieu_ngay_giao")

        # --- Điều kiện "sẵn sàng xếp lịch" của từng bước (§12) ---
        for cd in lsx.cong_doans:
            # Mọi bước phải biết ai/máy nào làm thì Gantt mới có chỗ đặt. THUÊ NGOÀI cũng vậy:
            # nhà thầu được khai như một MÁY trong danh mục (tên kèm hậu tố "thuê ngoài – …"),
            # nên cửa này không có luật riêng cho nó nữa. Bước `cho` không chiếm tài nguyên nên miễn.
            if (cd.loai_buoc in (LB_MAY, LB_TO, LB_THUE_NGOAI)
                    and not (cd.department_id or cd.may_id)):
                if "thieu_to_may" not in thieu:
                    thieu.append("thieu_to_may")
            # Bước cần dụng cụ lưu kho mà chưa trỏ con dao nào → chưa chạy được, chặn Y NHƯ
            # thiếu nhà gia công. Trước 04/09/2026 cửa này im lặng: lệnh qua cửa ngon lành rồi tới
            # lúc thợ ra máy mới biết không có dao. Danh sách dụng cụ đọc từ CỜ của công đoạn
            # (`co_dung_cu` nạp theo lô ở trên), KHÔNG ghi cứng tên bước.
            can_dc, loai_dc = co_dung_cu.get(cd.cong_doan_id, (False, None))
            if can_chot_khuon(can_dc, loai_dc) and cd.khuon_be_id is None:
                if "thieu_khuon" not in thieu:
                    thieu.append("thieu_khuon")
        # Thiếu NGUỒN của hệ số quy đổi — hai cầu, hai nguồn khác nhau. KHÔNG kiểm `he_so <= 1`
        # như bản cũ: hệ số 1 HỢP LỆ ở cả hai cầu (1 tờ nguyên ra 1 tờ in là chuyện thường; 1
        # con/tờ hiếm nhưng có — poster bằng khổ tờ). Chỉ 0/thiếu mới là chưa khai.
        # So theo TRẠM, KHÔNG theo mã. `don_vi_vao/ra` là mã xưởng tự đặt (`to_chay`, `sp_xong`);
        # so thẳng với `("to","cai")` thì chỉ khớp trên dữ liệu seed, còn xưởng nào đổi tên đơn vị
        # là ba cảnh báo dưới đây IM LẶNG và nút "Sẵn sàng" mở toang dù thiếu Con/tờ (12/08/2026).
        tram_bd = self._tram()
        cau = {(tram_cua(c.don_vi_vao, tram_bd), tram_cua(c.don_vi_ra, tram_bd))
               for c in lsx.cong_doans if c.don_vi_vao and c.don_vi_ra}
        qc_kt = lsx.quy_cach_json or {}
        # Sách gấp tay lấy hệ số từ TRANG MỖI TAY, không phải số con — đòi `so_con` ở lệnh sách là
        # bắt khai một số không vào công thức, rồi chặn phát hành vì thiếu thứ vô dụng.
        la_sach = _f(qc_kt.get("trang_moi_tay")) > 1
        if (TRAM_TO, TRAM_CAI) in cau and not la_sach and int(lsx.so_con or 0) <= 0:
            thieu.append("thieu_con_tren_to")
        # Cầu `tay → cuốn` chỉ có nghĩa khi biết một cuốn mấy tay = số trang / trang mỗi tay.
        if (TRAM_TAY, TRAM_CAI) in cau and (la_sach is False or _f(qc_kt.get("so_trang")) <= 0):
            thieu.append("thieu_trang_moi_tay")
        if (TRAM_TO_NGUYEN, TRAM_TO) in cau and _f(qc_kt.get("so_manh_xa")) <= 0:
            thieu.append("thieu_manh_xa")
        # tp chỉ dùng để xác nhận nguồn còn sống — lệnh vẫn chạy được khi PTG đã đổi/xoá.
        del tp
        return thieu

    # ================= TÍNH NGƯỢC · LEAD TIME =================

    def mac_dinh_buoc(self, *, lsx_id: int, cong_doan_id: int) -> dict:
        """Thuộc tính công việc khi kế hoạch ĐỔI công đoạn giữa chừng.

        Công đoạn chỉ quyết định tên, tổ, đơn vị và setup. Loại Máy/Tổ/Thuê ngoài, máy cụ thể và
        nguồn năng suất thuộc chính bước KHSX nên tuyệt đối không được endpoint này ghi đè —
        `may_id_goi_y` là GỢI Ý cho ô đang trống, không phải lệnh gán (xem chú thích ở khoá đó).

        KHÔNG trả số lượng vào/ra: chúng thuộc CHUỖI (bước trước giao bao nhiêu thì bước này nhận
        bấy nhiêu), không thuộc công đoạn — người kế hoạch giữ số đang cân, lệch thì đã có cảnh báo
        `dut_chuyen` và nút "Tính ngược từ SL thành phẩm".
        """
        lsx = self.get(lsx_id)
        cd = self.db.get(CongDoan, cong_doan_id)
        if cd is None:
            raise LsxNotFound("Không tìm thấy công đoạn")

        dv_vao, dv_ra, he_so = _don_vi_theo_buoc(
            cd, cau=self._he_so_cau(lsx), tram=self._tram())
        return {
            "cong_doan_id": cd.id,
            "ten": cd.ten,
            "nhom": cd.nhom,
            # Công đoạn NHIỀU tổ (mg `0312`): tổ đầu là mặc định, kèm cả danh sách để client biết
            # ô chọn tổ của bước được chọn những tổ nào.
            "department_id": cd.to_mac_dinh_id,
            "department_ids": cd.department_ids,
            "don_vi_vao": dv_vao,
            "don_vi_ra": dv_ra,
            "he_so_quy_doi": he_so,
            # Cờ dòng giấy phải đi CÙNG cặp đơn vị mới. Client áp `don_vi_vao`/`don_vi_ra` của công
            # đoạn vừa chọn lên dòng đang sửa; không trả kèm cờ thì nó giữ cờ của công đoạn CŨ, và
            # FE không tự suy lại được (trạm là cờ trên danh mục Đơn vị, không đọc ra từ mã).
            # Đổi bước in → ghi kẽm là dòng đó mang cặp `m² → bài in` mà vẫn tự nhận "trên dòng
            # giấy" cho tới lúc lưu.
            "tren_dong_giay": tren_dong_giay(dv_vao, dv_ra, self._tram()),
            # Cờ DỤNG CỤ cũng phải đi kèm, cùng một lẽ với cờ dòng giấy: ô chọn khuôn của bước lọc
            # kho theo `tooling_type`, mà FE không suy ra được nó từ tên công đoạn. Không trả kèm
            # thì đổi bước Bế sang một công đoạn cần KHUÔN ÉP KIM vẫn thấy thẻ "Khuôn của bước (khuôn
            # bế)" và ô chọn vẫn bày dao bế — sai loại, im lặng, cho tới lúc lưu rồi nạp lại màn.
            "requires_tooling": can_chot_khuon(cd.requires_tooling, cd.tooling_type),
            "tooling_type": cd.tooling_type,
            "setup_phut": _f(cd.setup_time),
            # GỢI Ý máy, không phải lệnh gán (09/09/2026): chỉ có số khi công đoạn mới khai ĐÚNG
            # MỘT máy còn dùng, và client chỉ áp khi dòng đang TRỐNG máy. Máy người ta đã chọn vẫn
            # bất khả xâm phạm — đó là ranh giới mà docstring trên vẫn giữ. Có nó vì cách đo giờ và
            # tốc độ đều treo ở cặp (công đoạn × máy): đổi sang công đoạn một-máy mà để trống thì
            # bảng thời gian của bước ra "—" cho tới khi có người vào chọn đúng cái máy duy nhất.
            "may_id_goi_y": self._may_mac_dinh(cd, None),
        }

    def _he_so_cau(self, lsx: Lsx, *, so_con: int | None = None) -> dict:
        """Hệ số của HAI CẦU quy đổi — hai nguồn KHÁC NHAU, đừng gộp.

        `to→cai` lấy cột `lsx.so_con`; `to_nguyen→to` lấy `quy_cach_json["so_manh_xa"]` — số mảnh
        xả KHÔNG có cột riêng trên `lsx`, `getattr(lsx, "so_manh_xa")` sẽ luôn ra None.

        `so_con` truyền vào để BÀI GHÉP hỏi "nếu xếp 2 con/tờ thì cần bao nhiêu tờ" mà không phải
        ghi đè cột của lệnh — bố cục ghép khác bố cục in riêng.

        LỆNH ĐÃ GHÉP thì cả hai cầu đọc theo BÀI: bài mới là chủ của tờ giấy (số con trên tờ ghép,
        khổ tờ in, giấy). Giữ số của bài tính giá ở đây là ra hai con số tờ đá nhau giữa hai màn.
        """
        qc = lsx.quy_cach_json or {}
        ghep = self._ghep_cua(lsx)
        con = so_con if so_con is not None else (
            (ghep and ghep[1].so_con_tren_to) or lsx.so_con
        )
        xa = _f(qc.get("so_manh_xa"))
        if ghep is not None and (xa_bai := self._manh_xa_theo_bai(qc, ghep[0])):
            xa = xa_bai
        # Cầu `to → cai` KHÔNG phải lúc nào cũng là số con: sách gấp tay thì nhiều TỜ mới gom
        # thành MỘT cuốn (hệ số `1/so_tay`, nhỏ hơn 1), và `con` không vào công thức giấy.
        # Dùng chung hàm với engine tính giá — trước đây tầng này trả thẳng `con` nên lệnh sách
        # cấp thiếu giấy đúng `con × so_tay` lần, một chiều, không ai báo.
        to_sang_cai = cau_to_sang_cai(
            trang_moi_tay=qc.get("trang_moi_tay"), so_trang=qc.get("so_trang"), con=con,
        )
        so_con = float(max(int(con or 0), 1))
        # Khoá là cặp TRẠM, KHÔNG phải cặp mã đơn vị — `dich_chuoi` tra bằng `TRAM_*`, và mọi nơi
        # tra bằng mã phải dịch qua `tram_cua` trước. Trước 12/08/2026 chỗ này viết bằng hằng `DV_*`
        # (cùng chuỗi "to"/"cai" nên chạy đúng) khiến người đọc tưởng khoá theo mã rồi tra bằng mã —
        # đúng cái bẫy làm ba cảnh báo `thieu_*` chết câm khi xưởng đổi tên đơn vị.
        return {
            (TRAM_TO, TRAM_CAI): to_sang_cai,
            (TRAM_TO_NGUYEN, TRAM_TO): float(max(int(xa or 0), 1)),
            # Đường DÀI qua `con`, cho bước thật sự đếm mảnh cắt. Tích hai cầu phải bằng đúng cầu
            # đi tắt `to → cai`, không thì hai lối cho ra hai số giấy khác nhau trên cùng một lệnh.
            (TRAM_TO, TRAM_CON): so_con,
            (TRAM_CON, TRAM_CAI): to_sang_cai / so_con,
            # Đường DÀI của SÁCH: gấp (tờ in → tay) rồi bắt tay + vào keo (tay → cuốn). Gấp không
            # sinh không mất tờ nên cầu đầu là 1, cầu sau gánh trọn — cùng luật bảo toàn tích.
            (TRAM_TO, TRAM_TAY): 1.0,
            (TRAM_TAY, TRAM_CAI): to_sang_cai,
        }

    def nap_ghep_cua(self, ghep: dict, lsx_ids) -> None:
        """Nạp sẵn kết quả `_ghep_cua` cho một lô lệnh — `ghep` = `BaiGhepRepository.ghep_theo_lsx`.

        Engine bài ghép hỏi câu này 4–6 lần cho MỖI thành viên (cầu quy đổi, chuỗi ngược, chuỗi
        xuôi…). Chỉ đường ĐỌC nhiều bài mới nạp (xem `BaiGhepService.nap_truoc`); lệnh ngoài lô vẫn
        hỏi DB như cũ.
        """
        nap = dict(getattr(self, "_ghep_nap", None) or {})
        nap.update({int(i): ghep.get(int(i)) for i in lsx_ids if i})
        self._ghep_nap = nap

    def _ghep_cua(self, lsx: Lsx):
        """(BaiGhep, BaiGhepThanhVien) nếu lệnh đang trong một bài ghép, không thì None."""
        if not getattr(lsx, "id", None):
            return None
        nap = getattr(self, "_ghep_nap", None)
        if nap is not None and lsx.id in nap:
            return nap[lsx.id]
        return self.db.execute(
            select(BaiGhep, BaiGhepThanhVien)
            .join(BaiGhepThanhVien, BaiGhepThanhVien.bai_ghep_id == BaiGhep.id)
            .where(BaiGhepThanhVien.lsx_id == lsx.id)
        ).first()

    @staticmethod
    def _manh_xa_theo_bai(qc: dict, bg) -> int | None:
        """Số mảnh xả tính lại theo KHỔ TỜ IN CỦA BÀI (giấy nguyên vẫn của lệnh).

        Ghép bài đổi khổ tờ in mà giữ nguyên `so_manh_xa` của bài tính giá thì số giấy nguyên
        phải mua sai theo. Xếp thử cả hai hướng, lấy nhiều hơn — giống `_fit` bên engine tính giá.
        """
        ng_d, ng_r = _f(qc.get("kho_nguyen_dai")), _f(qc.get("kho_nguyen_rong"))
        in_d, in_r = _f(bg.kho_in_dai), _f(bg.kho_in_rong)
        if min(ng_d, ng_r, in_d, in_r) <= 0:
            return None
        thang = int(ng_d // in_d) * int(ng_r // in_r)
        xoay = int(ng_d // in_r) * int(ng_r // in_d)
        return max(thang, xoay) or None

    def tinh_nguoc_routing(
        self, lsx: Lsx, *, so_con: int | None = None, bo_hao_step_keys: set[str] | None = None,
        bu_hao_rows: list[dict] | None = None,
    ) -> list[dict]:
        """Chạy NGƯỢC chuỗi công đoạn từ SL thành phẩm → SL vào/ra của từng bước.

        Đúng chiều tư duy xưởng và đúng mô hình BC (`Input = Output × (1 + Scrap%) + FixedScrap`,
        cộng dồn từ bước CUỐI về bước ĐẦU): *cần 20.500 hộp tốt thì phải in bao nhiêu tờ*.

        Dòng giấy có BA đơn vị và HAI cầu (`to_nguyen → to → cai`):
        - Bước **NGOÀI dòng giấy đứng ngoài chuỗi** — nhận ra bằng ô đơn vị BỎ TRỐNG (06/09/2026;
          giữa 11/08 và 06/09 nó khai đơn vị thật `bai → kem` và phải hỏi cờ `tram_dong_giay`).
          Hàm này KHÔNG trả gì cho nó: số của bước ấy do người lập lệnh tự khai ở bước
          (`tu_khai_don_vi`), duyệt cả bước này là "Tính ngược" ghi đè kẽm bằng số tờ. Công thức
          sản lượng ra ở danh mục công đoạn GỠ 18/09/2026 (mg `0324`).
        - Đích = đơn vị RA của bước cuối SAU KHI LỌC: ra `cai` thì đích là SL đặt.
        - Hao lấy từ DANH MỤC công đoạn (`bu_hao_engine.hao_buoc`) ở ĐÚNG đơn vị của bước, không
          đọc `cd.hao_hut` nữa. Hao thêm của kế hoạch (`lsx.bu_hao_to`) cộng vào bước CUỐI.
        - `%` đo trên số RA của bước (chốt 06/09/2026): ra 100 hao 10% ⇒ vào 110, KHÔNG phải
          111,11. Cùng một nghĩa với `bu_hao_engine.chuoi_nguoc_dv` — hai tầng phải ra một số.

        Hàm THUẦN — chỉ trả số, KHÔNG ghi DB (`_ap_chuoi_nguoc` mới ghi). `so_con` cho phép hỏi
        "nếu xếp N con/tờ thì cần bao nhiêu tờ" mà không đụng cột của lệnh — bài ghép cần đúng thế.
        """
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        tram = self._tram()
        idx = [i for i, c in enumerate(buoc)
               if tren_dong_giay(c.don_vi_vao, c.don_vi_ra, tram)]
        he_so = self._he_so_cau(lsx, so_con=so_con)
        # KHÔNG lọc `active`: chuỗi tính này chạy MỖI LẦN ĐỌC chi tiết lệnh. Lọc ở đây thì ẩn một
        # mã bù hao là cả loạt lệnh cũ hiện nhãn "tính lại" dù chẳng ai đụng vào chúng.
        # Bài ghép gọi hàm này cho TỪNG thành viên nên truyền sẵn bảng đã nạp — hỏi lại mỗi lần
        # là mỗi thành viên thêm một câu.
        if bu_hao_rows is None:
            bu_hao_rows = [_bu_hao_to_dict(b) for b in self.db.execute(select(BuHao)).scalars()]
        cd_cache: dict[int, dict] = {}

        def _quy_tac_bu_hao(cong_doan_id) -> dict:
            """Quy tắc bù hao của DANH MỤC công đoạn — `hao_buoc` chỉ cần 3 khoá này."""
            if not cong_doan_id:
                return {}
            if cong_doan_id not in cd_cache:
                obj = self.db.get(CongDoan, cong_doan_id)
                cd_cache[cong_doan_id] = {} if obj is None else {
                    "kieu_bu_hao": obj.kieu_bu_hao,
                    "bu_hao_id": obj.bu_hao_id,
                    "so_to_bu_hao": obj.so_to_bu_hao,
                }
            return cd_cache[cong_doan_id]

        out: list[dict] = [{} for _ in buoc]
        # Bước NGOÀI dòng giấy (ghi kẽm, phơi bản…) không có dòng nào ở đây: số của nó do người lập
        # lệnh tự khai ở bước. `buoc_ngoai_dong` (tính từ `cong_thuc_san_luong`) GỠ 18/09/2026.
        # `idx` để áp ngược, KHÔNG khớp theo `id` (lúc `tao()` id còn None).
        if not idx:
            return [o for o in out if o]

        # Đích = SL đặt QUY VỀ đơn vị ra của bước cuối. Bản cũ luôn lấy thẳng SL đặt, nên routing
        # kết ở `con` (bế xong là hết) bị hiểu là "cần ngần ấy CON" trong khi khách đặt ngần ấy CÁI
        # — lệch đúng số con/cái. Dùng chung công thức với engine tính giá, xem `dich_chuoi`.
        can_ra = dich_chuoi(
            float(lsx.so_luong_dat or 0),
            tram_ra_cuoi=tram_cua(buoc[idx[-1]].don_vi_ra, tram),
            cai_moi_to=he_so.get((TRAM_TO, TRAM_CAI)) or 1.0,
            he_so=he_so,
        )
        for pos in range(len(idx) - 1, -1, -1):
            i = idx[pos]
            cd = buoc[i]
            tram_vao, tram_ra = tram_cua(cd.don_vi_vao, tram), tram_cua(cd.don_vi_ra, tram)
            if bo_hao_step_keys and cd.step_key in bo_hao_step_keys:
                # Bước đã CHUYỂN TẦNG hao lên bài ghép: một lượt in chung thì chỉ canh máy một lần,
                # để hao ở đây nữa là mỗi lệnh trong bài cộng thêm một bộ hao cho cùng lượt in đó.
                fixed, pct = 0.0, 0.0
            else:
                fixed, pct = hao_buoc(_quy_tac_bu_hao(cd.cong_doan_id), rows=bu_hao_rows, sl=can_ra)
            hs = he_so.get((tram_vao, tram_ra), 1.0) if tram_vao != tram_ra else 1.0
            pct = max(pct, 0.0)
            vao = float(ceil(can_ra / hs * (1.0 + pct / 100.0) + fixed))
            out[i] = {
                # `idx` = vị trí trong danh sách đã sort — dùng để áp ngược. KHÔNG khớp theo `id`:
                # lúc `tao()` các bước chưa flush nên `id` còn None, khớp theo id là trượt sạch.
                "idx": i,
                "id": cd.id, "thu_tu": cd.thu_tu, "ten": cd.ten,
                "so_luong_vao": vao,
                "so_luong_ra": float(ceil(can_ra)),
                "don_vi_vao": cd.don_vi_vao, "don_vi_ra": cd.don_vi_ra,
                "he_so_quy_doi": hs, "hao_hut": fixed, "hao_hut_pct": pct,
            }
            can_ra = vao  # bước trước phải GIAO đủ chừng này
        return [o for o in out if o]

    def tinh_xuoi_tu_to(
        self, lsx: Lsx, *, tu_step_key: str, so_to: float, so_con: int | None = None,
        bu_hao_rows: list[dict] | None = None,
    ) -> list[dict]:
        """Chạy XUÔI từ số tờ THẬT giao cho lệnh → sản lượng thật ở từng bước sau đó.

        Lượt về trả lời "cần bao nhiêu tờ để đủ hàng". Ghép bài thì câu hỏi ngược lại: bài in
        `so_to` tờ chung cho mọi lệnh, vậy TỪNG lệnh thật sự ra bao nhiêu? Không có lượt đi thì
        chỗ đó phải đoán bằng `so_to × con` — tức bỏ qua toàn bộ hao của các bước sau in, và số
        dư báo lên gấp cả chục lần thực tế.

        Nghịch đảo đúng công thức của lượt về (`vào = ra/hs × (1 + %) + tờ`):
            `ra = (vào − tờ) ÷ (1 + %) × hs`

        `tu_step_key` là ĐIỂM TOẢ — bước chạy chung cuối cùng. Bài giao `so_to` TỜ vào bước đó, và
        chính bước đó có thể đổi đơn vị (bế: 1 tờ → N con). Nên phải áp HỆ SỐ của bước toả trước
        khi chạy tiếp, nếu không thì bước kế nhận số tờ mà tưởng là số con — sản lượng hụt đúng
        `con` lần. HAO của bước toả thì KHÔNG áp: nó đã đếm một lần ở tầng bài.
        """
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        tram = self._tram()
        idx = [i for i, c in enumerate(buoc)
               if tren_dong_giay(c.don_vi_vao, c.don_vi_ra, tram)]
        try:
            bat_dau = next(p for p, i in enumerate(idx) if buoc[i].step_key == tu_step_key)
        except StopIteration:
            return []

        he_so = self._he_so_cau(lsx, so_con=so_con)
        # KHÔNG lọc `active`: chuỗi tính này chạy MỖI LẦN ĐỌC chi tiết lệnh. Lọc ở đây thì ẩn một
        # mã bù hao là cả loạt lệnh cũ hiện nhãn "tính lại" dù chẳng ai đụng vào chúng.
        if bu_hao_rows is None:
            bu_hao_rows = [_bu_hao_to_dict(b) for b in self.db.execute(select(BuHao)).scalars()]
        cd_cache: dict[int, dict] = {}

        def _quy_tac(cong_doan_id) -> dict:
            if not cong_doan_id:
                return {}
            if cong_doan_id not in cd_cache:
                obj = self.db.get(CongDoan, cong_doan_id)
                cd_cache[cong_doan_id] = {} if obj is None else {
                    "kieu_bu_hao": obj.kieu_bu_hao,
                    "bu_hao_id": obj.bu_hao_id,
                    "so_to_bu_hao": obj.so_to_bu_hao,
                }
            return cd_cache[cong_doan_id]

        def _hs(cd) -> float:
            """Hệ số cầu của bước — tra theo TRẠM, không theo mã đơn vị (xem `tinh_nguoc_routing`)."""
            tv, tr = tram_cua(cd.don_vi_vao, tram), tram_cua(cd.don_vi_ra, tram)
            return he_so.get((tv, tr), 1.0) if tv != tr else 1.0

        cd_toa = buoc[idx[bat_dau]]
        out: list[dict] = []
        dang_co = float(so_to) * _hs(cd_toa)   # đã ở ĐƠN VỊ VÀO của bước kế tiếp
        for pos in range(bat_dau + 1, len(idx)):
            i = idx[pos]
            cd = buoc[i]
            fixed, pct = hao_buoc(_quy_tac(cd.cong_doan_id), rows=bu_hao_rows, sl=dang_co)
            pct = max(pct, 0.0)
            hs = _hs(cd)
            ra = (dang_co - fixed) / (1.0 + pct / 100.0) * hs
            ra = max(0.0, floor(ra))
            out.append({
                "idx": i, "step_key": cd.step_key, "thu_tu": cd.thu_tu, "ten": cd.ten,
                "so_luong_vao": dang_co, "so_luong_ra": ra,
                "don_vi_vao": cd.don_vi_vao, "don_vi_ra": cd.don_vi_ra,
                "he_so_quy_doi": hs, "hao_hut": fixed, "hao_hut_pct": pct,
            })
            dang_co = ra
        return out

    def _bo_hao_do_ghep(self, lsx: Lsx) -> set[str] | None:
        """Bước của lệnh đang bị bài ghép ĐÈ → hao đã đếm một lần ở tầng bài, đừng cộng lại.

        Không có chỗ nối này thì `lsx_cong_doan` vẫn LƯU hao riêng của từng lệnh cho bước chạy
        chung: bài ghép hiển thị một bộ hao, mà DB giữ hai bộ — hai nguồn sự thật lệch nhau ngay
        ở con số quan trọng nhất (số giấy phải mua).
        """
        if not lsx.id:
            return None
        keys = set(self.db.execute(
            select(BaiGhepCongDoanMap.lsx_step_key)
            .where(BaiGhepCongDoanMap.lsx_id == lsx.id)
        ).scalars())
        return keys or None

    def _ap_chuoi_nguoc(self, lsx: Lsx) -> None:
        """GHI kết quả chuỗi ngược vào từng bước + hai mốc số tờ của lệnh. KHÔNG commit.

        Gọi ở MỌI cửa làm số đổi (`tao`, `update`, `replace_routing`) — số lượng bước nay là dẫn
        xuất, không phải thứ client gửi lên. Cũng làm luôn việc **kế thừa lại đơn vị từ danh mục**:
        đơn vị không sửa được ở lệnh nên giữ bản sao chỉ tổ lệch khi danh mục đổi.
        """
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        tram = self._tram()
        # LƯỢT 1 — kế thừa lại đơn vị từ DANH MỤC. Phải xong hết lượt này rồi mới đọc được "chặng
        # tờ in của lệnh": chính lượt này là nơi đơn vị được ghi, đọc trước là đọc trạng thái cũ.
        # `khai_tay` = bước ngoài dòng giấy có đơn vị do người kế hoạch khai TẠI LỆNH (xem
        # `tu_khai_don_vi`). Cả hai lượt dưới đều phải chừa nó ra, nếu không thì gõ xong bấm Lưu
        # phát nữa là bay sạch — đó đúng là lý do ô ghi kẽm đứng im ở `0 –` bấy lâu.
        # Chọn nhầm hai mã CHẶNG (`to → cai`) thì bước nhập hẳn vào dòng giấy: lúc ấy không còn là
        # khai tay nữa mà là một bước trên chuỗi, để chuỗi ngược tính như mọi bước khác.
        tu_danh_muc: dict[int, bool] = {}
        khai_tay: dict[int, bool] = {}
        for i, cd in enumerate(buoc):
            obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
            tu_danh_muc[i] = obj is not None or cd.nhom == "prepress"
            khai_tay[i] = (tu_khai_don_vi(cd, obj)
                           and not tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram))
            if khai_tay[i]:
                continue
            if obj is not None:
                cd.don_vi_vao, cd.don_vi_ra, _hs = _don_vi_theo_buoc(obj)
            elif cd.nhom == "prepress":
                cd.don_vi_vao = cd.don_vi_ra = None
        # Đơn vị chặng TỜ IN của CHÍNH lệnh này — cho bước tự thêm đứng ĐẦU chuỗi (không có bước
        # trước để nối tiếp). Trước đây chỗ đó đóng đinh mã `to`: xưởng khai `to_chay` thì mã `to`
        # không có trong danh mục ⇒ bước rớt khỏi dòng giấy và hao của nó biến mất khỏi số giấy phải
        # mua, không một dòng cảnh báo. Lệnh chưa có bước nào nối danh mục ⇒ hỏi danh mục Đơn vị
        # (`ma_cua_tram`), vẫn không rõ thì để None và bước sẽ đeo cảnh báo `buoc_ngoai_dong_giay`.
        dv_to_lenh = don_vi_chuoi(buoc, tram)["to"] or ma_cua_tram(TRAM_TO, tram)
        # LƯỢT 2 — bước kế hoạch TỰ THÊM nối tiếp đơn vị bước liền trước, không đổi cách đếm.
        truoc_ra: str | None = None
        for i, cd in enumerate(buoc):
            if khai_tay[i]:
                # Đơn vị khai tay KHÔNG được làm mốc nối cho bước sau: `kem` chảy sang bước tự thêm
                # đứng kế là bước ấy rơi khỏi dòng giấy, hao của nó biến mất khỏi số giấy phải mua.
                # Bước ngoài dòng kế thừa danh mục vốn để trống nên `or truoc_ra` tự giữ mốc cũ —
                # đây chỉ giữ đúng hành vi ấy khi hai ô đã có chữ.
                continue
            if not tu_danh_muc[i]:
                cd.don_vi_vao = cd.don_vi_ra = truoc_ra or dv_to_lenh
            truoc_ra = cd.don_vi_ra or truoc_ra
        rows = {r["idx"]: r for r in self.tinh_nguoc_routing(
            lsx, bo_hao_step_keys=self._bo_hao_do_ghep(lsx),
        )}
        for i, cd in enumerate(buoc):
            r = rows.get(i)
            if r is None:            # bước ngoài dòng giấy (chế bản) — giữ nguyên số kẽm
                if khai_tay[i]:
                    # Hai đầu đều là số người ta gõ ⇒ không còn phép suy nào để hao hay hệ số quy
                    # đổi tham gia. Bỏ qua thì ba cột này nằm lại ở giá trị của lần danh mục tính
                    # cuối, rồi drawer đọc thành "Số vào = 1 bài in = 6 bản kẽm + 2 bài in hao" —
                    # sai số học; `ty_le_hao_hut` và cảnh báo vượt định mức hao cũng đo trên số cũ.
                    cd.hao_hut = 0.0
                    cd.hao_hut_pct = 0.0
                    cd.he_so_quy_doi = 0.0
                continue
            cd.so_luong_vao = r["so_luong_vao"]
            cd.so_luong_ra = r["so_luong_ra"]
            cd.he_so_quy_doi = r["he_so_quy_doi"]
            cd.hao_hut = r["hao_hut"]
            cd.hao_hut_pct = r["hao_hut_pct"]

        # Hai mốc số tờ = ĐỌC RA khỏi chuỗi tại đúng ranh giới, không tính riêng bên ngoài.
        # Dò theo TRẠM: xưởng khai mã riêng cho chặng tờ in thì dò theo mã không thấy, hai mốc rơi
        # về 0 và số giấy phải mua biến mất — hỏng im lặng.
        tram = self._tram()

        def _vao_tai(tram_can: str) -> float | None:
            return next((r["so_luong_vao"] for i, cd in enumerate(buoc)
                         if (r := rows.get(i)) and tram_cua(cd.don_vi_vao, tram) == tram_can), None)

        to_in = _vao_tai(TRAM_TO)
        lsx.so_to_ke_hoach = int(to_in or 0)
        nguyen = _vao_tai(TRAM_TO_NGUYEN)
        if nguyen is not None:
            lsx.so_to_nguyen = int(nguyen)
        else:
            # Chuỗi không có bước xả → quy đổi ở đây, đúng fallback `thanh_phan_engine` đang dùng.
            xa = self._he_so_cau(lsx)[(TRAM_TO_NGUYEN, TRAM_TO)]
            lsx.so_to_nguyen = ceil(lsx.so_to_ke_hoach / xa) if lsx.so_to_ke_hoach else 0

    def _may_cua_buoc(self, cd) -> MayThietBi | None:
        """Máy ĐANG GÁN của bước — nguồn SỐNG của tốc độ + thời gian chuẩn bị sau chốt 2026-08-04.
        `db.get` đi qua identity map nên gọi lặp trong một vòng lặp không sinh query mới."""
        return self.db.get(MayThietBi, cd.may_id) if getattr(cd, "may_id", None) else None

    def lead_time(self, lsx: Lsx) -> dict:
        """Tổng thời gian dẫn của cả lệnh + ngày dự kiến xong (thô, 8h/ngày, chưa trừ nghỉ lễ)."""
        chiem_may = 0.0
        durations: dict[int, float] = {}
        qc = quy_cach_bien(lsx)
        for cd in lsx.cong_doans:
            may = self._may_cua_buoc(cd)
            t = thoi_luong_buoc(cd, may, self.sl_tinh_cua_buoc(cd, may, qc))
            durations[cd.id] = t["tong_phut"]
            chiem_may += t["chiem_may_phut"]
        ids = set(durations)
        preds: dict[int, list[int]] = {i: [] for i in ids}
        for a, b in self.db.execute(select(
            LsxCongDoanPhuThuoc.buoc_truoc_id, LsxCongDoanPhuThuoc.buoc_sau_id
        ).where(LsxCongDoanPhuThuoc.buoc_sau_id.in_(ids))).all() if ids else []:
            if a in ids:
                preds[b].append(a)
        memo: dict[int, float] = {}
        def finish(i: int) -> float:
            if i not in memo:
                memo[i] = durations[i] + max((finish(p) for p in preds[i]), default=0.0)
            return memo[i]
        tong = max((finish(i) for i in ids), default=0.0)
        so_ngay = tong / 60.0 / GIO_LAM_MOI_NGAY if tong else 0.0
        han = lsx.han_giao_khach
        con_lai = (han - date.today()).days if han else None
        return {
            "tong_phut": round(tong, 2),
            "chiem_may_phut": round(chiem_may, 2),
            "so_ngay": round(so_ngay, 2),
            "ngay_du_kien_xong": date.today() + timedelta(days=ceil(so_ngay)) if tong else None,
            "ngay_con_lai": con_lai,
        }

    def detail_dict(self, lsx: Lsx) -> dict:
        """Ghép dữ liệu hiển thị (tên đơn/khách/máy/tổ/khuôn) cho 1 lệnh."""
        order = self.db.get(Order, lsx.order_id)
        dept_ids = {cd.department_id for cd in lsx.cong_doans if cd.department_id}
        may_ids = {cd.may_id for cd in lsx.cong_doans if cd.may_id}
        if lsx.may_id:
            may_ids.add(lsx.may_id)
        dept_names = self._dept_names(dept_ids)
        may_names = self._may_names(may_ids)
        khuon_map = self._khuon_map({cd.khuon_be_id for cd in lsx.cong_doans})
        ptg_id = ptg_ma = None
        tp = self._thanh_phan(lsx.phieu_thanh_phan_id)
        if tp is not None:
            ptg = self.db.get(PhieuTinhGia, tp.phieu_id)
            ptg_id, ptg_ma = (ptg.id, ptg.ma) if ptg else (None, None)
        quote_number = quote_version_number = None
        if lsx.quote_version_id:
            ver = self.db.get(QuoteVersion, lsx.quote_version_id)
            if ver is not None:
                quote_version_number = ver.version_number
                from ..models.quotation import Quote

                quote = self.db.get(Quote, ver.quote_id)
                quote_number = quote.quote_number if quote else None
        # Nhãn nhóm ĐỌC SỐNG từ dòng đơn, KHÔNG lấy trong `quy_cach_json`: quy cách là ảnh chụp
        # lúc tạo lệnh nên lệnh tạo trước khi có tính năng nhóm sẽ trống — mà "thuộc sản phẩm nào"
        # là thông tin thương mại, phải luôn đúng hiện tại.
        line = self.db.get(OrderLine, lsx.order_line_id) if lsx.order_line_id else None
        chua_d, chua_r = chua_theo_chieu(lsx.quy_cach_json or {})
        # Quy cách của lệnh là nguồn biến cho quy đổi khoán. Đi qua `quy_cach_bien` chứ KHÔNG lấy
        # `quy_cach_json` trần: năm số dẫn xuất (SL đặt · con/tờ · tờ in · tờ nguyên · tờ sau in)
        # nằm ở cột, thiếu chúng thì công thức khoán dùng `to_dau_vao` báo "chưa biết Tờ vào máy"
        # ngay giữa màn đang hiện số tờ đó.
        qc_bien = quy_cach_bien(lsx)
        # SỐ LƯỢNG LÀ ẢNH CHỤP lúc tạo lệnh — engine chỉ chạy lại ở ba cửa: tạo · sửa quy cách ·
        # lưu routing. Danh mục đổi sau đó (bậc bù hao, công thức đơn vị, hệ số ngoài dòng) thì lệnh
        # đã tạo KHÔNG hay biết, và người kế hoạch cũng không có gì để mà biết mà bấm Lưu.
        #
        # Nên tính lại NGẦM ở đây rồi SO với số đã lưu. Khác thì phơi ra `so_luong_*_moi` để màn
        # gạch số cũ + hiện nhãn "tính lại". CỐ Ý KHÔNG tự đè: lệnh đã phát xuống xưởng mà số giấy
        # tự đổi dưới chân người kế hoạch còn tệ hơn số cũ — máy đề xuất, người quyết.
        moi = {r["idx"]: r for r in self.tinh_nguoc_routing(lsx)}
        thu_tu_idx = {id(c): i for i, c in enumerate(sorted(lsx.cong_doans, key=lambda x: x.thu_tu))}
        buoc_dicts = [
            self._cong_doan_dict(cd, dept_names, may_names, qc_bien,
                                 moi.get(thu_tu_idx.get(id(cd), -1)), khuon_map)
            for cd in lsx.cong_doans
        ]
        return {
            "nhom": getattr(line, "nhom", None),
            "order_no": order.order_no if order else None,
            "order_status": order.status if order else None,
            "customer_name": self._customer_name(order) if order else None,
            "customer_po_no": order.customer_po_no if order else None,
            "sale_name": self._user_name(order.sale_user_id) if order else None,
            # "Lưu ý sản xuất (gửi xưởng)" của ĐƠN — đọc SỐNG (sale sửa lúc nào thợ thấy lúc đó),
            # KHÔNG ảnh chụp. Đây là nguồn DUY NHẤT của ô lưu ý thợ thấy trên lệnh; khác hẳn
            # `ghi_chu_ky_thuat` (ghi chú kỹ thuật theo sản phẩm, chốt ở khâu tính giá).
            "luu_y_gui_xuong": order.production_note if order else None,
            "quote_number": quote_number,
            "quote_version_number": quote_version_number,
            "ptg_id": ptg_id,
            "ptg_ma": ptg_ma,
            "may_ten": may_names.get(lsx.may_id),
            "nguoi_phu_trach_ten": self._user_name(lsx.nguoi_phu_trach_id),
            "thieu": self.thieu_cua(lsx),
            "lead_time": self.lead_time(lsx),
            "cong_doans": buoc_dicts,
            # KHÔNG có `khoan_tien_tong` (gỡ 11/09/2026). Tổng công thợ của lệnh là số của kế toán
            # lương, tính theo bảng giá TẠI KỲ TÍNH LƯƠNG — cộng ở đây là bày một con số mà tầng
            # dưới không có gì để đối chiếu, và nó từng là con số duy nhất người xem tin.
            # Chừa TÁCH CHIỀU — tính LÚC ĐỌC bằng đúng hàm của engine, kể cả cho lệnh cũ. Màn lệnh
            # chỉ việc hiện: để nó tự cộng lại từ các khoản chừa là đẻ ra bản thứ hai của công
            # thức, mà bản thứ hai chính là chỗ vừa sai (gộp 20/20 thay vì 15/10).
            "chua_dai": chua_d,
            "chua_rong": chua_r,
            # MÃ đơn vị bốn CHẶNG dòng giấy của lệnh này. Server chấm MỘT chỗ (`don_vi_chuoi`) rồi
            # gửi cho cả ba màn — danh sách, hàng chờ, chi tiết. Trước đây màn chi tiết tự suy lại
            # bằng bản chép tay bên frontend; hai bản cùng luật là hai cơ hội lệch, và lần đầu tiên
            # chúng đã cùng sai y hệt nhau ở chặng "tay" (12/08/2026).
            **{f"don_vi_{k}": v for k, v in don_vi_chuoi(lsx.cong_doans, self._tram()).items()},
            # Lệnh đang ghép chung tờ với ai — màn lệnh trước đây MÙ hoàn toàn, người kế hoạch
            # sửa máy in ở đây mà không biết máy thật nằm ở bài.
            "bai_ghep": self._bai_ghep_dict(lsx),
            # Danh mục Công đoạn đã đổi sau lúc lệnh chụp ảnh — None khi còn khớp hết. Cùng tinh
            # thần `so_luong_*_moi` ngay trên: MÁY ĐỀ XUẤT, NGƯỜI QUYẾT. Không tự đè, chỉ phơi ra.
            "danh_muc_doi": self.danh_muc_doi(lsx),
        }

    def _bai_ghep_dict(self, lsx: Lsx) -> dict | None:
        """Khối bài ghép của lệnh (None nếu in riêng) — DẪN XUẤT, đọc sống từ bài."""
        ghep = self._ghep_cua(lsx)
        if ghep is None:
            return None
        bg, tv = ghep
        # Bước nào của lệnh đang bị bài ĐÈ + số của cả lượt chung. Màn lệnh phải nói được CẢ HAI
        # số ("bài cấp 1.480 tờ · phần lệnh này 987 tờ"), không thì người sửa máy in ở đây mà
        # không biết máy thật nằm ở bài.
        de_len = {
            m.lsx_step_key: {
                "gop_step_key": c.step_key, "ten": c.ten,
                "to_ten": self._dept_names({c.department_id}).get(c.department_id),
                "may_ten": self._may_names({c.may_id}).get(c.may_id),
                "so_luong_vao": _f(c.so_luong_vao), "so_luong_ra": _f(c.so_luong_ra),
                "hao_hut": _f(c.hao_hut),
            }
            for c, m in self.db.execute(
                select(BaiGhepCongDoan, BaiGhepCongDoanMap)
                .join(BaiGhepCongDoanMap,
                      BaiGhepCongDoanMap.bai_ghep_cong_doan_id == BaiGhepCongDoan.id)
                .where(BaiGhepCongDoanMap.lsx_id == lsx.id)
            ).all()
        }
        return {
            "id": bg.id, "ma": bg.ma, "trang_thai": bg.trang_thai,
            "may_id": bg.may_id, "may_ten": self._may_names({bg.may_id}).get(bg.may_id),
            "giay_id": bg.giay_id,
            "kho_in_dai": bg.kho_in_dai, "kho_in_rong": bg.kho_in_rong,
            "so_con_tren_to": tv.so_con_tren_to,
            "buoc_bi_de": de_len,
        }

    def _cong_doan_dict(self, cd, dept_names: dict, may_names: dict,
                        quy_cach: dict | None = None, moi: dict | None = None,
                        khuon_map: dict | None = None) -> dict:
        vao = _f(cd.so_luong_vao)
        may_cd = self._may_cua_buoc(cd)
        t = thoi_luong_buoc(cd, may_cd, self.sl_tinh_cua_buoc(cd, may_cd, quy_cach))
        cd_obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
        _tren_dg = tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, self._tram())
        # ⚠️ `loi_quy_doi` + `san_luong_dien_giai` GỠ 18/09/2026 (mg `0324`) cùng công thức sản lượng
        #    ra của công đoạn: bước ngoài dòng giấy nay là số người lập lệnh tự khai, không có phép
        #    đổi nào để báo lỗi hay câu công thức nào để diễn giải.
        return {
            "id": cd.id, "step_key": cd.step_key, "thu_tu": cd.thu_tu, "cong_doan_id": cd.cong_doan_id,
            "ten": cd.ten, "nhom": cd.nhom, "loai_buoc": cd.loai_buoc, "bat_buoc": bool(cd.bat_buoc),
            "department_id": cd.department_id,
            "department_ten": dept_names.get(cd.department_id),
            "may_id": cd.may_id, "may_ten": may_names.get(cd.may_id),
            # Hai cờ dụng cụ đọc từ danh mục Công đoạn (KHÔNG suy từ tên bước — tên là chữ người
            # dùng gõ, đặt "Die-cut" hay "Ép kim" đều được). Chúng quyết định bước này có hỏi khuôn
            # hay không, và `tooling_type` còn là chiều lọc thứ hai của ô chọn dao.
            "requires_tooling": can_chot_khuon(getattr(cd_obj, "requires_tooling", False),
                                               getattr(cd_obj, "tooling_type", None)),
            "tooling_type": getattr(cd_obj, "tooling_type", None),
            # Con dao của bước + thông tin bày cho thợ. Nạp theo LÔ ở `_khuon_map`, không tra ở đây.
            "khuon_be_id": cd.khuon_be_id,
            **(khuon_map or {}).get(cd.khuon_be_id, {}),
            # Ý định của sale + chỗ lệch với con dao kế hoạch đã chốt. `khuon_lech` là câu tiếng
            # Việt hoặc None — dựng ở server để mọi màn nói cùng một câu, FE không tự suy lại.
            "khuon_nguon": cd.khuon_nguon,
            "khuon_phi": _f(cd.khuon_phi),
            "khuon_lech": canh_bao_lech_khuon(
                cd.khuon_nguon, cd.khuon_phi,
                (khuon_map or {}).get(cd.khuon_be_id, {}).get("khuon_be_tinh_trang"),
            ),
            "so_luong_vao": vao, "so_luong_ra": _f(cd.so_luong_ra),
            # Số ĐÚNG RA phải là, tính lại theo danh mục HIỆN TẠI. Chỉ có mặt khi KHÁC số đã lưu —
            # bằng nhau thì để None cho màn khỏi phải so lại lần nữa. Xem `detail_dict`.
            "so_luong_vao_moi": (
                _f(moi["so_luong_vao"]) if moi and _f(moi["so_luong_vao"]) != vao else None),
            "so_luong_ra_moi": (
                _f(moi["so_luong_ra"])
                if moi and _f(moi["so_luong_ra"]) != _f(cd.so_luong_ra) else None),
            "don_vi_vao": cd.don_vi_vao, "don_vi_ra": cd.don_vi_ra,
            # Bước có nằm trên DÒNG GIẤY không. Bước ngoài dòng đứng ngoài chuỗi bù hao nên số
            # lượng KHÔNG tự tính (đứng im ở 0 nếu không ai điền) và hao của nó không cộng vào số
            # giấy phải mua. Không gửi cờ này thì màn chỉ thấy hai số 0 mà không có lời giải thích
            # — FE tự suy không nổi vì "trên dòng giấy hay không" nằm ở cờ của danh mục Đơn vị.
            "tren_dong_giay": _tren_dg,
            "he_so_quy_doi": _f(cd.he_so_quy_doi),
            "hao_hut": _f(cd.hao_hut), "hao_hut_pct": _f(cd.hao_hut_pct),
            # % thực tế suy từ số — KHÔNG lưu cột, tránh hai nguồn sự thật với `hao_hut`.
            "ty_le_hao_hut": round(_f(cd.hao_hut) / vao * 100, 2) if vao > 0 else 0.0,
            "so_luot_chay": cd.so_luot_chay,
            # SỐ GIỜ KẾ HOẠCH của bước TỔ (mg `0319`) — ô gõ tay, thay chỗ "Kíp chuẩn" cũ.
            "so_gio_ke_hoach": _f(cd.so_gio_ke_hoach),
            # Chuẩn bị TRẢ RA LÀ SỐ KẾ THỪA TỪ MÁY (`t`), không phải cột `cd.setup_phut` đã dormant
            # — nếu trả cột cũ thì UI hiện một số mà engine lại tính bằng số khác.
            "setup_phut": t["dien_giai"]["setup_phut"],
            "phat_sinh_phut": _f(cd.phat_sinh_phut),
            "chay_phut": t["chay_phut"],
            "nha_cung_cap": cd.nha_cung_cap, "sl_gui": cd.sl_gui and _f(cd.sl_gui),
            "ngay_gui_dk": cd.ngay_gui_dk, "ngay_nhan_dk": cd.ngay_nhan_dk,
            "van_chuyen_ngay": cd.van_chuyen_ngay and _f(cd.van_chuyen_ngay),
            "gia_cong_ngay": cd.gia_cong_ngay and _f(cd.gia_cong_ngay),
            "hao_hut_cho_phep": cd.hao_hut_cho_phep and _f(cd.hao_hut_cho_phep),
            "don_gia_gia_cong": cd.don_gia_gia_cong and _f(cd.don_gia_gia_cong),
            "yeu_cau_ky_thuat": cd.yeu_cau_ky_thuat,
            "ghi_chu": cd.ghi_chu,
            **self._giao_nhan_dict(cd),
            # CHỈ lấy hai số DẪN XUẤT. KHÔNG spread cả `thoi_luong_buoc` vào đây: nó cũng có key
            # `chay_phut` và sẽ GHI ĐÈ giá trị đã lưu ở trên — client nhận số đã-tính, tưởng là
            # người dùng gõ đè, lưu ngược lại, thế là hợp đồng "để trống = máy tự tính" vỡ vĩnh
            # viễn ngay sau lần lưu đầu (bước chưa khai năng suất bị đóng băng ở 0 phút).
            "chiem_may_phut": t["chiem_may_phut"],
            # Dải nhanh/chậm nhất (tốc độ max/min của máy) — bảng công đoạn + Gantt vẽ râu.
            "chiem_may_phut_min": t["chiem_may_phut_min"],
            "chiem_may_phut_max": t["chiem_may_phut_max"],
            "tong_phut": t["tong_phut"],
            "thoi_luong_dien_giai": t["dien_giai"],
            # ⚠️ Ba khoá đầu việc GỠ 18/09/2026 (mg `0320`): `khoan_rate_id` · `khoan_ten` ·
            #    `khoan_chon_duoc`. Bước lệnh thôi chọn việc khoán — việc ấy chọn LÚC GHI MẺ ở bàn
            #    tổ, nơi thợ biết mình vừa làm gì. Vật tư của bước nay bung từ CÔNG ĐOẠN nên cũng
            #    không cần đi kèm từng lựa chọn nữa.
            "phu_thuoc_step_keys": [
                p.step_key for edge in cd.phu_thuoc
                if (p := self.db.get(LsxCongDoan, edge.buoc_truoc_id)) is not None
            ],
            "vat_tus": [
                {"id": v.id, "hang_loai": v.hang_loai, "vat_tu_id": v.vat_tu_id,
                 "vat_tu_ma": v.vat_tu_ma_snapshot, "vat_tu_ten": v.vat_tu_ten_snapshot,
                 "don_vi": v.don_vi_snapshot, "so_luong": _f(v.so_luong),
                 "tu_dong": bool(v.tu_dong)}
                for v in cd.vat_tus
            ],
            # Lượng tính sẵn cho MỌI vật tư — drawer chọn món nào là điền được ngay, khỏi gõ tay.
            "vat_tu_goi_y": self._goi_y_luong_vat_tu(cd, quy_cach),
        }

    def _giao_nhan_dict(self, cd) -> dict:
        """Sổ giao – nhận thực tế + mọi thứ SUY RA từ nó. Không lưu cột nào cho phần suy ra.

        Bước không phải thuê ngoài vẫn trả khoá (schema thẳng), nhưng để trống — tránh cho client
        phải nhớ "khoá này chỉ có ở loại bước kia".
        """
        giao, nhan = cd.giao_luc, cd.nhan_luc
        if giao is None:
            trang_thai = "chua_gui"
        elif nhan is None:
            trang_thai = "dang_ngoai"
        else:
            trang_thai = "da_ve"
        sl_giao, sl_nhan = cd.sl_giao_thuc, cd.sl_nhan_thuc
        hut = _f(sl_giao) - _f(sl_nhan) if (sl_giao is not None and sl_nhan is not None) else None
        # Quá hạn chỉ có nghĩa khi hàng CHƯA về: về rồi thì trễ bao nhiêu đọc ở `nhan_luc`.
        qua_han = None
        if cd.ngay_nhan_dk and nhan is None and giao is not None:
            tre = (date.today() - cd.ngay_nhan_dk).days
            qua_han = tre if tre > 0 else 0
        return {
            "nguoi_giao_id": cd.nguoi_giao_id,
            "nguoi_giao_ten": self._user_name(cd.nguoi_giao_id),
            "giao_luc": giao,
            "sl_giao_thuc": sl_giao and _f(sl_giao),
            "nguoi_nhan_id": cd.nguoi_nhan_id,
            "nguoi_nhan_ten": self._user_name(cd.nguoi_nhan_id),
            "nhan_luc": nhan,
            "sl_nhan_thuc": sl_nhan and _f(sl_nhan),
            "giao_nhan_trang_thai": trang_thai,
            "so_hut": hut,
            # Định mức để trống = CHƯA KHAI, không phải "cho phép 0" — chưa khai thì đừng phán hụt.
            "hut_vuot_dinh_muc": bool(
                hut is not None and cd.hao_hut_cho_phep is not None
                and hut > _f(cd.hao_hut_cho_phep)
            ),
            # Tiền theo số NHẬN ĐƯỢC, không theo số gửi đi — trả tiền cho hàng cầm về được.
            "tien_gia_cong_thuc": (
                round(_f(sl_nhan) * _f(cd.don_gia_gia_cong), 2)
                if sl_nhan is not None and cd.don_gia_gia_cong is not None else None
            ),
            "qua_han_ngay": qua_han,
        }

    def ghi_giao_nhan(self, *, lsx_id: int, buoc_id: int, payload, actor) -> Lsx:
        """Ghi MỘT sự kiện giao/nhận của bước thuê ngoài. Cửa THỰC THI — KHÔNG có guard
        `da_lap_ke_hoach`.

        Hàng ra khỏi cổng đúng lúc lệnh đang chạy; nếu đi chung cửa với `replace_routing` thì bắt
        kế hoạch gỡ lịch cả lệnh chỉ để ghi một dòng "đã giao 1.050 tờ lúc 14h" — tức là ghi không
        nổi đúng lúc cần ghi nhất.
        """
        lsx = self.get(lsx_id)
        cd = next((c for c in lsx.cong_doans if c.id == buoc_id), None)
        if cd is None:
            raise LsxNotFound("Không tìm thấy bước trong lệnh này")
        if cd.loai_buoc != LB_THUE_NGOAI:
            raise LsxValidationError("Chỉ bước gia công ngoài mới có sổ giao – nhận")

        d = payload.model_dump(exclude_unset=True)
        nguoi_id = d.get("nguoi_id") or actor.id
        luc = d.get("luc") or datetime.now(timezone.utc)
        so_luong = d.get("so_luong")
        if d.get("su_kien") == "giao":
            cd.nguoi_giao_id, cd.giao_luc = nguoi_id, luc
            cd.sl_giao_thuc = so_luong if so_luong is not None else (
                cd.sl_giao_thuc if cd.sl_giao_thuc is not None else cd.sl_gui
            )
            action, nhan_vc = "lsx_gia_cong_giao", "giao"
            so_ghi = cd.sl_giao_thuc
        else:
            cd.nguoi_nhan_id, cd.nhan_luc = nguoi_id, luc
            cd.sl_nhan_thuc = so_luong if so_luong is not None else (
                cd.sl_nhan_thuc if cd.sl_nhan_thuc is not None else cd.sl_giao_thuc
            )
            action, nhan_vc = "lsx_gia_cong_nhan", "nhận"
            so_ghi = cd.sl_nhan_thuc

        ten = self._user_name(nguoi_id) or f"#{nguoi_id}"
        # Vết audit người đọc, nên bày TÊN đơn vị ("tờ") chứ không bày MÃ ("to").
        from ..repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi
        dv = nhan_don_vi(DonViDoRepository(self.db).ten_theo_ma(), cd.don_vi_ra)
        # `.replace(",", ".")` CHỈ áp lên con số (đổi dấu nghìn sang kiểu Việt) — bọc cả câu như
        # trước thì một cái tên đơn vị có dấu phẩy sẽ bị đổi theo.
        so = f"{_f(so_ghi):,.0f}".replace(",", ".")
        self.audit.create(
            actor_user_id=actor.id, action=action, target=f"lsx_cong_doan:{cd.id}",
            detail=f"{lsx.ma} · {cd.ten}: {ten} {nhan_vc} {so} {dv}".strip(),
        )
        self.repo.commit()
        return self.get(lsx_id)

    # ⚠️ `_dau_viec_cua_buoc()` GỠ 18/09/2026 (mg `0320`) — không còn ai gọi từ lúc bước lệnh
    #    thôi chọn đầu việc.

    def list_rows(self, **kw) -> tuple[list[dict], int]:
        """`(dòng của TRANG này, TỔNG số dòng khớp lọc)`. Nhận thêm `page`/`size` xuống repo."""
        rows, total = self.repo.list(**kw)
        order_ids = {r.order_id for r in rows}
        orders = {
            o.id: o for o in self.db.execute(select(Order).where(Order.id.in_(order_ids))).scalars()
        } if order_ids else {}
        # Nhãn nhóm (vd "Catalogue A4 - 32 trang") — ĐỌC SỐNG từ dòng đơn: lệnh "Bìa" đứng một
        # mình thì không ai biết nó thuộc cuốn nào. `order_line_id` là FK THẬT nên đọc sống
        # an toàn, khỏi thêm cột (`phieu_thanh_phan_id` cũng ổn định từ 07/09/2026 nhưng nó không
        # mang nhãn nhóm — nhãn nằm ở dòng đơn).
        line_ids = {r.order_line_id for r in rows if r.order_line_id}
        nhom_by_line = {
            ln.id: ln.nhom
            for ln in (
                self.db.execute(select(OrderLine).where(OrderLine.id.in_(line_ids))).scalars()
                if line_ids else []
            )
        }
        dept_ids = {cd.department_id for r in rows for cd in r.cong_doans if cd.department_id}
        dept_names = self._dept_names(dept_ids)
        khach_names = self._customer_names({o.customer_id for o in orders.values() if o.customer_id})
        tram = self._tram()          # đọc MỘT lần cho cả danh sách
        out: list[dict] = []
        for r in rows:
            o = orders.get(r.order_id)
            first = r.cong_doans[0] if r.cong_doans else None
            out.append({
                "id": r.id, "ma": r.ma, "loai": r.loai, "ten": r.ten, "trang_thai": r.trang_thai,
                "nhom": nhom_by_line.get(r.order_line_id),
                "order_id": r.order_id,
                "order_no": o.order_no if o else None,
                "customer_name": khach_names.get(o.customer_id) if o else None,
                "so_luong_dat": r.so_luong_dat, "don_vi_tinh": r.don_vi_tinh,
                "so_to_ke_hoach": r.so_to_ke_hoach,
                "han_giao_khach": r.han_giao_khach, "han_hoan_thanh_sx": r.han_hoan_thanh_sx,
                "is_rush": bool(r.is_rush),
                "to_dau_ten": dept_names.get(first.department_id) if first else None,
                "so_cong_doan": len(r.cong_doans),
                # `r.cong_doans` đã nạp sẵn (dùng ngay ở hai dòng trên) nên chỗ này KHÔNG thêm
                # query nào — đừng đổi sang tra danh mục theo từng dòng, danh sách sẽ thành N+1.
                "don_vi_to": don_vi_chuoi(r.cong_doans, tram)["to"],
            })
        return out, total

    def dem_trang_thai(self, **kw) -> dict[str, int]:
        """Số trên TAB lọc — đếm ở máy chủ theo cùng bộ lọc trừ chính `trang_thai`.

        Trước đây màn tự đếm mảng đã tải về. Đếm kiểu đó chỉ đúng khi client cầm TOÀN BỘ dữ liệu;
        có phân trang rồi thì nó thành số của trang đang xem, tức số SAI.
        """
        return self.repo.dem_theo_trang_thai(**kw)

    def phu_thuoc_options(self, lsx_id: int) -> list[dict]:
        from ..repositories.catalog_base import SIZE_TRAN

        current = self.get(lsx_id)
        # Trong PHẠM VI MỘT ĐƠN — vài chục lệnh là cùng, lấy trọn trần một trang.
        lsxs, _ = self.repo.list(order_id=current.order_id, size=SIZE_TRAN)
        line_ids = [x.order_line_id for x in lsxs if x.order_line_id]
        groups = {
            x.id: x.nhom for x in self.db.execute(
                select(OrderLine).where(OrderLine.id.in_(line_ids))
            ).scalars()
        } if line_ids else {}
        # Tên bước ưu tiên tên CÔNG ĐOẠN đang gắn, y hệt `tenBuoc()` bên FE. Trả thẳng `step.ten`
        # thì chip phụ thuộc + panel "Bước LSX khác" là hai chỗ DUY NHẤT không có `cong_doan_id`
        # để tra ngược, nên bước mang nhãn tạm sẽ hiện "Công đoạn" trong khi bảng/DAG hiện tên thật.
        cd_ids = {
            step.cong_doan_id for item in lsxs for step in item.cong_doans if step.cong_doan_id
        }
        ten_cd = {
            c.id: c.ten for c in self.db.execute(
                select(CongDoan).where(CongDoan.id.in_(cd_ids))
            ).scalars()
        } if cd_ids else {}
        return [
            {"lsx_id": item.id, "lsx_ma": item.ma, "nhom": groups.get(item.order_line_id),
             "step_key": step.step_key,
             "ten_buoc": ten_cd.get(step.cong_doan_id) or step.ten,
             "thu_tu": step.thu_tu}
            for item in lsxs for step in sorted(item.cong_doans, key=lambda x: x.thu_tu)
        ]

    # THÔNG SỐ kế hoạch sửa được (nguyên nhân) — khớp `LsxQuyCachIn`. Mọi thứ ngoài bộ này trong
    # `quy_cach_json` là HỆ QUẢ, tính lại ở `ap_quy_cach`, không nhận từ client.
    _QC_SUA_DUOC = (
        "giay_id", "nguon_giay", "kho_nguyen_dai", "kho_nguyen_rong",
        "kho_in_dai", "kho_in_rong", "dai_thanh_pham", "rong_thanh_pham",
        "quy_cach_in", "muc_a", "muc_b", "so_trang", "trang_moi_tay",
        "bleed_mm", "khe_cat_mm", "con_auto",
    )

    def ap_quy_cach(self, lsx: Lsx, patch: dict) -> tuple[dict, list[str]]:
        """Trộn THÔNG SỐ mới vào ảnh chụp rồi tính lại mọi số DẪN XUẤT. KHÔNG ghi DB.

        Trả `(quy_cach_json mới, danh sách khoá đã đổi)`. Dùng cho cả đường LƯU (`update`) lẫn
        đường XEM TRƯỚC — một hàm, nên số xem trước không thể lệch số lưu xuống.

        Tính lại từ CHÍNH ảnh chụp của lệnh, KHÔNG đọc lại phiếu tính giá: lệnh đã được phép rời
        phiếu, quay về hỏi phiếu là xoá mất đúng thứ người kế hoạch vừa sửa.
        """
        from .thanh_phan_engine import (
            _fit, binh_bai_con, chua_theo_chieu, so_kem_moi_tay, so_mau_dan_xuat,
            so_tay_moi_cuon, tap_muc,
        )

        qc = dict(lsx.quy_cach_json or {})
        doi: list[str] = []
        for k in self._QC_SUA_DUOC:
            if k in patch and patch[k] is not None and qc.get(k) != patch[k]:
                qc[k] = patch[k]
                doi.append(k)
        if not doi:
            return qc, []

        # Đổi giấy → kéo theo định lượng + tên, không thì lệnh mang gsm của cuộn giấy cũ.
        if "giay_id" in doi and qc.get("giay_id"):
            giay = self.db.get(GiayNguyen, int(qc["giay_id"]))
            if giay is not None:
                qc["gsm"] = giay.gsm
                qc["giay_ten"] = giay.ten

        qc["muc_a"] = tap_muc(qc.get("muc_a"))
        qc["muc_b"] = tap_muc(qc.get("muc_b"))
        qc["so_mau_a"], qc["so_mau_b"], qc["so_mau_pha"] = so_mau_dan_xuat(
            qc["muc_a"], qc["muc_b"])

        # ① xả giấy: mấy tờ in cắt được từ một tờ nguyên.
        kn_d, kn_r = _f(qc.get("kho_nguyen_dai")), _f(qc.get("kho_nguyen_rong"))
        ki_d, ki_r = _f(qc.get("kho_in_dai")), _f(qc.get("kho_in_rong"))
        if kn_d > 0 and kn_r > 0 and ki_d > 0 and ki_r > 0:
            qc["so_manh_xa"] = max(_fit(kn_d, kn_r, ki_d, ki_r), 1)

        # ② bình bài: chỉ khi đang để MÁY TỰ. `con_auto=False` là người đã ép số con — tôn trọng.
        chua_d, chua_r = chua_theo_chieu(qc)
        if qc.get("con_auto") is not False and ki_d > 0 and ki_r > 0:
            con = binh_bai_con(
                kho_in_dai=ki_d, kho_in_rong=ki_r,
                dai_tp=_f(qc.get("dai_thanh_pham")), rong_tp=_f(qc.get("rong_thanh_pham")),
                chua_mm=0, chua_dai_mm=chua_d, chua_rong_mm=chua_r,
                bleed_mm=_f(qc.get("bleed_mm")), khe_cat_mm=_f(qc.get("khe_cat_mm")),
            )
            if con > 0:
                lsx.so_con = con
        qc["chua_dai"], qc["chua_rong"] = chua_d, chua_r

        # ③ số bài in = số TAY, và số kẽm = kẽm mỗi tay × số tay.
        so_tay = so_tay_moi_cuon(
            trang_moi_tay=qc.get("trang_moi_tay"), so_trang=qc.get("so_trang"))
        qc["so_to_per_sp"] = so_tay
        qc["kem_moi_tay"] = so_kem_moi_tay(
            qc["muc_a"], qc["muc_b"], str(qc.get("quy_cach_in") or "mot_mat"))
        qc["so_kem"] = qc["kem_moi_tay"] * so_tay
        return qc, doi

    def xem_truoc_quy_cach(self, *, lsx_id: int, patch: dict) -> dict:
        """Sửa thông số này thì các số MÁY TỰ TÍNH ra bao nhiêu? — KHÔNG ghi gì vào DB.

        Chạy ĐÚNG đường mà nút Lưu chạy (`ap_quy_cach` + `_ap_chuoi_nguoc`) rồi `rollback`. Cố ý
        không viết một bản tính riêng cho xem-trước: hai bản là hai chỗ để lệch, mà lệch ở đây
        nghĩa là màn hiện một số rồi lưu xuống một số khác.
        """
        lsx = self.get(lsx_id)
        try:
            qc, doi = self.ap_quy_cach(lsx, patch or {})
            if doi:
                lsx.quy_cach_json = qc
                self._ap_chuoi_nguoc(lsx)
            qc = dict(lsx.quy_cach_json or {})
            passes = 1 if qc.get("quy_cach_in") == "mot_mat" else 2
            return {
                "doi": doi,
                "so_con": int(lsx.so_con or 0),
                "so_kem": int(qc.get("so_kem") or 0),
                "kem_moi_tay": int(qc.get("kem_moi_tay") or 0),
                "so_manh_xa": int(qc.get("so_manh_xa") or 0),
                "so_to_per_sp": int(qc.get("so_to_per_sp") or 1),
                "so_to_ke_hoach": int(lsx.so_to_ke_hoach or 0),
                "so_to_nguyen": int(lsx.so_to_nguyen or 0),
                "so_luot": int(round(_f(lsx.so_to_ke_hoach) * passes)),
                "so_mau_a": int(qc.get("so_mau_a") or 0),
                "so_mau_b": int(qc.get("so_mau_b") or 0),
                "so_mau_pha": int(qc.get("so_mau_pha") or 0),
            }
        finally:
            # Rollback dọn SẠCH mọi thay đổi ở trên — kể cả `so_con` và cả chuỗi bước mà
            # `_ap_chuoi_nguoc` vừa ghi. Endpoint này không làm gì khác nên rollback là an toàn.
            self.db.rollback()

    def xem_truoc_routing(self, *, lsx_id: int, rows_in, actor) -> list[dict]:
        """Đổi/chèn công đoạn thì SỐ VÀO–RA + đơn vị của cả chuỗi ra bao nhiêu? — KHÔNG ghi DB.

        Chạy ĐÚNG đường nút Lưu routing chạy (`replace_routing`) ở chế độ không commit rồi
        `rollback`, y hệt `xem_truoc_quy_cach`. Cố ý không viết bản tính số thứ hai (ở FE hay ở
        đây): hai bản là hai chỗ để lệch, mà lệch nghĩa là drawer hiện một số rồi Lưu xuống số
        khác. Chỉ trả phần DÒNG CHẢY drawer cần nhảy tức thì, khớp `step_key` client gửi lên.
        """
        try:
            lsx = self.replace_routing(
                lsx_id=lsx_id, rows_in=rows_in, actor=actor, commit=False)
            tram = self._tram()
            out: list[dict] = []
            for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu):
                out.append({
                    "step_key": cd.step_key,
                    "so_luong_vao": _f(cd.so_luong_vao),
                    "so_luong_ra": _f(cd.so_luong_ra),
                    "don_vi_vao": cd.don_vi_vao,
                    "don_vi_ra": cd.don_vi_ra,
                    "he_so_quy_doi": _f(cd.he_so_quy_doi),
                    "hao_hut": _f(cd.hao_hut),
                    "hao_hut_pct": _f(cd.hao_hut_pct),
                    "tren_dong_giay": tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram),
                })
            return out
        finally:
            # Rollback dọn SẠCH chuỗi bước `replace_routing(commit=False)` vừa ghi (kể cả bước
            # mới chèn). Endpoint chỉ đọc số nên rollback là an toàn.
            self.db.rollback()

    def update(self, *, lsx_id: int, payload, actor) -> Lsx:
        lsx = self.get(lsx_id)
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxConflict("Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi sửa")
        data = payload.model_dump(exclude_unset=True)
        changed: list[str] = []
        # `so_to_ke_hoach` / `so_to_nguyen` KHÔNG còn nhận từ client — hai mốc đó nay đọc ra từ
        # chuỗi ngược (`_ap_chuoi_nguoc`), nhận thêm đường nữa là đẻ nguồn sự thật thứ hai.
        for field in (
            "ten", "so_luong_dat", "don_vi_tinh",
            "so_con", "han_hoan_thanh_sx", "is_rush", "may_id",
            "nguoi_phu_trach_id", "ghi_chu",
        ):
            if field in data and getattr(lsx, field) != data[field]:
                setattr(lsx, field, data[field])
                changed.append(field)
        # Đổi SL đặt / con·tờ / quy cách là đổi luôn số vật tư cần — chặn khi đang giữ chỗ, cùng
        # luật với routing (`replace_routing`) và xoá lệnh (`xoa`). Field khác (tên, ghi chú, người
        # phụ trách...) không đụng vật tư nên KHÔNG chặn.
        # Điều kiện phải TRÙNG KHÍT với điều kiện chạy lại chuỗi ngược ở dưới: cái gì làm
        # `_ap_chuoi_nguoc` viết lại số tờ vào máy thì cái đó đổi lượng giấy cần. `so_con` từng
        # lọt vì đọc như "thông số trình bày", nhưng bình bài lại là số tờ kế hoạch khác đi.
        if {"so_luong_dat", "so_con"} & set(changed) or data.get("quy_cach"):
            self._chan_dang_giu_cho(lsx)
        # THÔNG SỐ (ảnh chụp) đổi → trộn vào rồi tính lại mọi số dẫn xuất. Đặt TRƯỚC chuỗi ngược
        # vì nó có thể đổi `so_con` (bình bài lại) — thứ chuỗi ngược lấy làm hệ số cầu.
        if data.get("quy_cach"):
            qc_moi, qc_doi = self.ap_quy_cach(lsx, data["quy_cach"])
            if qc_doi:
                lsx.quy_cach_json = qc_moi
                changed.extend(f"quy_cach.{k}" for k in qc_doi)
        # SL đặt / con·tờ / thông số đổi → cả chuỗi phải tính lại.
        if {"so_luong_dat", "so_con"} & set(changed) or data.get("quy_cach"):
            self._ap_chuoi_nguoc(lsx)
            # Số lượt phải đợi chuỗi ngược chốt số tờ vào máy mới tính được.
            qc = dict(lsx.quy_cach_json or {})
            passes = 1 if qc.get("quy_cach_in") == "mot_mat" else 2
            qc["so_luot"] = int(round(_f(lsx.so_to_ke_hoach) * passes))
            lsx.quy_cach_json = qc
        if changed:
            # Sửa xong mà hết thiếu → về NHÁP; còn thiếu → CHỜ BỔ SUNG (giữ nguyên nếu đã SẴN SÀNG
            # và vẫn đủ dữ liệu).
            thieu = self.thieu_cua(lsx)
            if thieu:
                lsx.trang_thai = TT_CHO_BO_SUNG
            elif lsx.trang_thai == TT_CHO_BO_SUNG:
                lsx.trang_thai = TT_NHAP
            self.audit.create(
                actor_user_id=actor.id, action="update_lsx", target=f"lsx:{lsx.id}",
                detail=f"Sửa lệnh {lsx.ma}: {', '.join(changed)}",
            )
        self.repo.commit()
        return self.get(lsx_id)

    # Cột nhận thẳng từ client, không cần suy diễn gì thêm. KHÔNG có `he_so_quy_doi`/`hao_hut`/
    # `hao_hut_pct`: cả ba nay là dẫn xuất của chuỗi ngược, server ghi trong `_ap_chuoi_nguoc`.
    # Thời lượng nay KẾ THỪA từ máy (2026-08-04) nên client chỉ còn gửi được `phat_sinh_phut`.
    # `setup_phut` · `chay_phut` · `di_chuyen_phut` · `ve_sinh_phut` · `cho_phut` đã rời bộ này:
    # còn cột trong DB nhưng không nhận từ client và engine không đọc.
    # `bat_buoc` rời bộ này 07/09/2026: mọi bước trong routing đều bắt buộc, cột do server giữ TRUE.
    _ROUTING_FIELD_THUAN = (
        "may_id", "khuon_be_id", "so_luot_chay",
        # SỐ GIỜ KẾ HOẠCH của bước TỔ (mg `0319`) — số gõ tay, KHÔNG kế thừa từ đâu cả, nên nó
        # thuộc bộ "nhận thẳng" này. Thay chỗ `so_nhan_cong_tieu_chuan` (kíp chuẩn) đã gỡ.
        "so_gio_ke_hoach", "phat_sinh_phut",
        # Chờ kỹ thuật: kế thừa từ danh mục Công đoạn là MẶC ĐỊNH, sửa đè tại bước (mục B).
        "nha_cung_cap", "sl_gui", "ngay_gui_dk", "van_chuyen_ngay", "gia_cong_ngay",
        "ngay_nhan_dk", "hao_hut_cho_phep", "don_gia_gia_cong", "yeu_cau_ky_thuat",
        "ghi_chu",
        # `kcs_tieu_chi_bo_sung_json` rời bộ này 08/09/2026 (mg `0283`): tiêu chí KCS chỉ còn MỘT
        # nguồn là danh mục gắn theo công đoạn — `docs/design-kcs-theo-cong-doan.md` mục 5.
    )
    _ROUTING_FIELD_NULLABLE = {
        "may_id", "khuon_be_id", "chay_phut", "nha_cung_cap", "ngay_gui_dk", "ngay_nhan_dk",
        "ghi_chu",
    }

    def _chan_dang_giu_cho(self, lsx: Lsx) -> None:
        """Lệnh đang giữ chỗ vật tư → không đổi số lượng/con·tờ/quy cách/routing, không xoá.

        Đối xứng với `BaiGhepService._chan_dang_giu_cho`/`_chan_lenh_dang_giu_cho` ở phía bài ghép
        — nới ở phía lệnh sẽ vô hiệu hoá khoá phía bài (LSX đứng riêng vẫn đổi được số vật tư cần
        mà giữ chỗ không hay biết). Có ĐƯỜNG LÙI: nhả chỗ ở màn Kế hoạch vật tư rồi làm — chặn
        cứng không lối ra sẽ biến giữ chỗ thành cái khoá vĩnh viễn.

        Chặn CẢ preview (`replace_routing(commit=False)`, tức `xem_truoc_routing`): số trên màn
        xem trước đã dùng để người dùng QUYẾT ĐỊNH có nhả chỗ hay không — cho preview chạy qua thì
        màn nói dối, bấm Lưu thật mới báo lỗi.
        """
        if getattr(lsx, "giu_cho_bat", False):
            raise LsxConflict(
                f"Lệnh {lsx.ma} đang giữ chỗ vật tư — nhả chỗ ở màn Kế hoạch vật tư trước khi sửa "
                "số lượng, số con/tờ, quy cách, routing hoặc xoá lệnh."
            )

    # --- Danh mục đổi dưới chân lệnh -----------------------------------------

    def _ly_do_khong_cap_nhat(self, lsx: Lsx) -> str | None:
        """Vì sao lệnh này KHÔNG lấy được số mới của danh mục. `None` = lấy được.

        Đúng ba cửa mà `replace_routing` chặn, và chặn bằng cùng câu chữ: đồng bộ danh mục cũng là
        ghi đè `khoan_json` + dòng vật tư của bước, tức là đúng thứ ba cửa kia đang giữ. Nới ở đây
        là mở cửa hậu cho chính thứ vừa khoá.
        """
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            return "Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi lấy số mới của danh mục"
        order = self.db.get(Order, lsx.order_id)
        if order is not None and order.status == STATUS_CANCELLED:
            return "Đơn đã hủy — không cập nhật được"
        if getattr(lsx, "giu_cho_bat", False):
            return ("Lệnh đang giữ chỗ vật tư — nhả chỗ ở màn Kế hoạch vật tư trước khi lấy số mới")
        return None

    def _soi_danh_muc(self, lsx: Lsx) -> list[dict]:
        """Từng bước lệch danh mục ra sao — kèm rổ `ap` là thứ sẽ ghi nếu người dùng bấm cập nhật.

        Gộp SOI và ÁP vào một lượt, cố ý: hai lượt tính riêng là hai cơ hội lệch nhau, mà lệch ở
        đây nghĩa là băng hứa một đằng nút ghi một nẻo. `danh_muc_doi` bóc phần `ap` ra trước khi
        trả về client.

        ⚠️ 18/09/2026: nửa KHOÁN của băng này GỠ HẲN (mg `0320`) — bước thôi ghim đầu việc nên
        chẳng còn ảnh chụp nào lệch với danh mục. Băng còn đúng hai việc: VẬT TƯ của công đoạn và
        MÁY bị gỡ khỏi công đoạn. Ảnh chụp đơn giá nay nằm ở MẺ sản xuất, và băng "Danh mục đã
        đổi" của mẻ là một cửa riêng ở bàn tổ (§7.2b), không đi qua đây.
        """
        quy_cach = quy_cach_bien(lsx)
        ra: list[dict] = []
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu):
            if not cd.cong_doan_id:
                continue
            cd_obj = self.db.get(CongDoan, cd.cong_doan_id)
            if cd_obj is None:
                continue        # công đoạn bị xoá hẳn — `thieu_cua` lo phần đó, đừng nói hai lần
            # THUÊ NGOÀI vẫn miễn soi vật tư: nhà thầu tự lo vật tư của họ, bung định mức của
            # công đoạn vào bước thuê ngoài là đẻ ra một nhu cầu mua hàng không có thật.
            ngoai = cd.loai_buoc == LB_THUE_NGOAI
            ap: dict = {"vat_tu_them": [], "vat_tu_dat_lai": []}
            muc: dict = {
                "buoc_id": cd.id, "step_key": cd.step_key, "thu_tu": cd.thu_tu, "ten": cd.ten,
                "vat_tu_them": [], "vat_tu_bo": [], "vat_tu_lech": [], "may_canh_bao": None,
            }
            # Vật tư soi thẳng theo CÔNG ĐOẠN (mg `0316`) — không còn phải đợi bước chọn đầu việc.
            if not ngoai:
                moi_rows, _ = self._vat_tu_bung(cd_obj, cd, quy_cach)
                hien_co = [
                    {"hang_loai": v.hang_loai, "vat_tu_id": v.vat_tu_id,
                     "ma": v.vat_tu_ma_snapshot,
                     "ten": v.vat_tu_ten_snapshot, "don_vi": v.don_vi_snapshot,
                     "so_luong": _f(v.so_luong), "tu_dong": bool(v.tu_dong)}
                    for v in cd.vat_tus
                ]
                vt = vat_tu_lech(hien_co, moi_rows)
                muc["vat_tu_them"], muc["vat_tu_bo"], muc["vat_tu_lech"] = (
                    vt["them"], vt["bo"], vt["lech"])
                moi_theo_id = {(r.get("hang_loai") or HANG_VAT_TU, int(r["vat_tu_id"])): r
                               for r in moi_rows}
                ap["vat_tu_them"] = [moi_theo_id[(r["hang_loai"], r["vat_tu_id"])]
                                     for r in vt["them"]]
                ap["vat_tu_dat_lai"] = [moi_theo_id[(r["hang_loai"], r["vat_tu_id"])]
                                        for r in vt["lech"]]
            # Máy: công thức giờ chạy của cặp (công đoạn × máy) đọc SỐNG lúc tính thời lượng nên
            # không có gì để đồng bộ. Thứ DUY NHẤT trôi được là danh sách máy: gỡ máy khỏi công
            # đoạn thì bước vẫn ôm `may_id` cũ và vẫn tính giờ bằng công thức đã bị gỡ.
            may_ids = {m.may_id for m in (cd_obj.may_lam_duoc or [])}
            if cd.may_id and may_ids and cd.may_id not in may_ids:
                muc["may_canh_bao"] = (
                    "Máy đang gán không còn nằm trong danh sách máy của công đoạn — chọn máy khác")
            co_gi = (muc["vat_tu_them"] or muc["vat_tu_bo"] or muc["vat_tu_lech"]
                     or muc["may_canh_bao"])
            if co_gi:
                ra.append({**muc, "ap": ap})
        return ra

    def danh_muc_doi(self, lsx: Lsx) -> dict | None:
        """Lệnh đang giữ số cũ ở chỗ nào so với danh mục hiện tại. `None` = còn khớp hết.

        Đi kèm mọi lần đọc lệnh (`detail_dict`) để người lập kế hoạch THẤY mà không phải đi tìm —
        đó là cả lý do tồn tại của nó: ảnh chụp không tự đổi là ĐÚNG, nhưng im lặng thì sai.
        """
        buocs = self._soi_danh_muc(lsx)
        if not buocs:
            return None
        khoa = self._ly_do_khong_cap_nhat(lsx)
        return {
            "so_buoc": len(buocs),
            "co_the_cap_nhat": khoa is None,
            "ly_do_khoa": khoa,
            "buocs": [{k: v for k, v in b.items() if k != "ap"} for b in buocs],
        }

    def dong_bo_danh_muc(self, *, lsx_id: int, actor) -> Lsx:
        """Lấy số mới của danh mục cho MỌI bước của lệnh — cửa của nút "Cập nhật theo danh mục".

        Ghi HAI thứ: dòng vật tư danh mục có mà bước chưa có, và số của dòng vật tư MÁY BUNG bị
        lệch. KHÔNG đụng: dòng người khai tay (`tu_dong=False`), dòng danh mục không còn bung (xem
        `vat_tu_lech`), máy của bước, và SỐ GIỜ KẾ HOẠCH (số người lập lệnh gõ, danh mục không có
        nguồn tương đương).
        """
        lsx = self.get(lsx_id)
        if (loi := self._ly_do_khong_cap_nhat(lsx)) is not None:
            raise LsxConflict(loi)
        buocs = self._soi_danh_muc(lsx)
        if not buocs:
            return lsx
        theo_id = {b["buoc_id"]: b["ap"] for b in buocs}
        for cd in lsx.cong_doans:
            ap = theo_id.get(cd.id)
            if ap is None:
                continue
            dat_lai = {(r.get("hang_loai") or HANG_VAT_TU, int(r["vat_tu_id"])): r
                       for r in ap["vat_tu_dat_lai"]}
            for v in cd.vat_tus:
                if (r := dat_lai.get((v.hang_loai, int(v.vat_tu_id)))) is not None:
                    v.so_luong = float(r["so_luong"])
            thu_tu = max((v.thu_tu for v in cd.vat_tus), default=-1)
            for r in ap["vat_tu_them"]:
                thu_tu += 1
                cd.vat_tus.append(LsxCongDoanVatTu(
                    hang_loai=r.get("hang_loai") or HANG_VAT_TU,
                    vat_tu_id=int(r["vat_tu_id"]), vat_tu_ma_snapshot=r.get("ma") or "",
                    vat_tu_ten_snapshot=r.get("ten") or "", don_vi_snapshot=r.get("don_vi") or "",
                    so_luong=float(r["so_luong"]), thu_tu=thu_tu, tu_dong=True,
                ))
        self.db.flush()
        # Lượt đồng bộ có thể gỡ nốt chỗ "thiếu" cuối cùng — cùng luật với lưu routing, để trạng
        # thái lệnh không đứng lại ở Chờ bổ sung vì một lý do đã hết.
        thieu = self.thieu_cua(lsx)
        if thieu and lsx.trang_thai != TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_CHO_BO_SUNG
        elif not thieu and lsx.trang_thai == TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_NHAP
        self.audit.create(
            actor_user_id=actor.id, action="update_lsx_danh_muc", target=f"lsx:{lsx.id}",
            detail=f"Cập nhật lệnh {lsx.ma} theo danh mục: {len(buocs)} công đoạn lấy số mới",
        )
        self.repo.commit()
        return self.get(lsx_id)

    def replace_routing(self, *, lsx_id: int, rows_in, actor, ly_do: str | None = None,
                        commit: bool = True) -> Lsx:
        lsx = self.get(lsx_id)
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxConflict("Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi sửa routing")
        order = self.db.get(Order, lsx.order_id)
        if order is not None and order.status == STATUS_CANCELLED:
            raise LsxConflict("Đơn đã hủy — không thể sửa routing")
        self._chan_dang_giu_cho(lsx)
        truoc = len(lsx.cong_doans)
        old_by_key = {r.step_key: r for r in lsx.cong_doans}
        rows: list[LsxCongDoan] = []
        payloads: list[dict] = []
        # Bước MỚI gắn công đoạn hoặc bước vừa ĐỔI công đoạn — lưu xong phải bung lại vật tư theo
        # công đoạn của nó (`_bung_lai_vat_tu`). Drawer chỉ bỏ dòng máy bung của công đoạn cũ.
        doi_cd: list[LsxCongDoan] = []
        # ⚠️ Rổ `bo_dau_viec` (lưu ý "bước này mất đầu việc mồ côi") GỠ 18/09/2026 (mg `0320`):
        #    bước thôi ghim đầu việc nên không có gì mồ côi được nữa.
        for i, r in enumerate(rows_in):
            d = r.model_dump(exclude_unset=True)
            payloads.append(d)
            cd_id = d.get("cong_doan_id")
            ten = d.get("ten")
            nhom = d.get("nhom")
            dept = d.get("department_id")
            cd_obj = self.db.get(CongDoan, cd_id) if cd_id else None
            # Chuỗi `TEN_BUOC_TRONG` là NHÃN TẠM của bước chưa đặt tên, không phải tên người đặt.
            # Bước chèn tay từng bị client cũ gửi đúng chuỗi này; khi bước đã gắn công đoạn thì coi
            # như chưa có tên để lấy lại tên danh mục, nếu không nó trơ chữ "Công đoạn" vĩnh viễn.
            if cd_id and ten and ten.strip() == TEN_BUOC_TRONG:
                ten = None
            if cd_id and (not ten or nhom is None or dept is None):
                if cd_obj is not None:
                    ten = ten or cd_obj.ten
                    nhom = nhom if nhom is not None else cd_obj.nhom
                    dept = dept if dept is not None else cd_obj.to_mac_dinh_id
            key = (d.get("step_key") or "").strip()
            row = old_by_key.get(key) if key else None
            old_cd_id = row.cong_doan_id if row is not None else None
            old_dept_id = row.department_id if row is not None else None
            old_loai = row.loai_buoc if row is not None else None
            # Tổ của bước phải là một TỔ PHỤ TRÁCH của công đoạn (mg `0312`) — chỉ soi khi bước mới,
            # đổi tổ hoặc đổi công đoạn. Bước giữ nguyên thì để yên snapshot cũ: danh mục đổi tổ sau
            # khi lên lệnh không được khoá đường lưu cả lệnh vì một bước chẳng ai đụng.
            if (cd_obj is not None and dept is not None and cd_obj.department_ids
                    and dept not in cd_obj.department_ids
                    and (row is None or old_cd_id != cd_id or old_dept_id != dept)):
                raise LsxValidationError(
                    f'Tổ đã chọn không phụ trách công đoạn "{cd_obj.ten}" — chọn một trong các tổ '
                    f'khai ở danh mục Công đoạn.')
            if row is None:
                row = LsxCongDoan(thu_tu=i, **({"step_key": key} if key else {}))
            row.cong_doan_id = cd_id
            row.ten = ten or TEN_BUOC_TRONG
            row.nhom = nhom
            row.department_id = dept
            # Loại bước do KHSX chọn. Đổi Công đoạn không được âm thầm đổi lại Máy/Tổ.
            loai = d.get("loai_buoc") or old_loai or LB_MAY
            if loai not in LOAI_BUOC:
                raise LsxValidationError("Loại bước chỉ nhận Máy, Tổ hoặc Thuê ngoài")
            row.loai_buoc = loai
            for f in self._ROUTING_FIELD_THUAN:
                if f in d and (d.get(f) is not None or f in self._ROUTING_FIELD_NULLABLE):
                    setattr(row, f, d[f])
            # ĐƠN VỊ + SỐ LƯỢNG (10/09/2026): nhận từ client cho bước NGOÀI dòng giấy — ghi kẽm đếm
            # bản kẽm theo số màu của TỪNG đơn, không có công thức chung nào ở danh mục nói hộ.
            # Bước TRÊN dòng giấy gửi lên cũng vô hại: `_ap_chuoi_nguoc` ở cuối hàm ghi đè cả bốn ô
            # bằng số của chuỗi ngược — nó vẫn là nơi DUY NHẤT quyết ai được giữ số của mình.
            # Chuỗi rỗng phải về None, đừng lưu `""`: "chưa khai" và "khai bằng đơn vị tên rỗng" mà
            # lẫn nhau thì `tu_khai_don_vi` bật lên cho mọi bước và danh mục hết đường kéo lại.
            for f in ("don_vi_vao", "don_vi_ra"):
                if f in d:
                    setattr(row, f, (d[f] or "").strip() or None)
            for f in ("so_luong_vao", "so_luong_ra"):
                if d.get(f) is not None:
                    setattr(row, f, float(d[f]))
            # Bước TỔ làm bằng tay theo tổ, KHÔNG chiếm máy. Gỡ máy ở SERVER chứ không chỉ ẩn ô
            # trên form: máy còn dính lại thì bước vẫn chiếm một lane Gantt của máy đó.
            if row.loai_buoc == LB_TO:
                row.may_id = None
                # Cùng lẽ ấy với "số lượt qua máy" (08/09/2026): ô đã gỡ khỏi drawer ở bước tổ —
                # làm tay thì không có lượt chạy qua máy nào. Ép 1 ở SERVER để số cũ khác 1 không
                # nằm lại VÔ HÌNH: chip `so_luot_chay` của công thức tiền công vẫn có số thật để
                # dùng (`thoi_luong_buoc` vẫn báo `so_luot_chay`), chỉ là luôn bằng 1.
                row.so_luot_chay = 1
            # ⚠️ Cả khối ĐẦU VIỆC KHOÁN của bước GỠ 18/09/2026 (mg `0320`): nhận `piece_rate_id`,
            #    ghim `khoan_json`, kế thừa kíp chuẩn + năng suất người-giờ, và cửa dọn ảnh chụp
            #    cho bước máy / thuê ngoài. Bước thôi mang đầu việc; việc khoán chọn LÚC GHI MẺ ở
            #    bàn tổ (`san_xuat_batch.piece_rate_id`), nơi thợ biết mình vừa làm gì. Cửa
            #    `source_changed` + `_ke_thua` đi theo luôn — chúng chỉ phục vụ khối này.

            if cd_id and old_cd_id != cd_id:
                doi_cd.append(row)
            rows.append(row)
        # Bước đang bị một bài ghép ĐÈ mà biến mất khỏi payload → bài mất chỗ bám. Chặn ở đây
        # thay vì để lớp đè âm thầm trỏ vào một `step_key` không còn tồn tại. Neo nay là
        # `bai_ghep_cong_doan_map` (mọi bước đã gộp), không riêng bước in.
        con_lai = {r.step_key for r in rows}
        mat = self.db.execute(
            select(BaiGhep.ma, BaiGhepCongDoanMap.lsx_step_key, BaiGhepCongDoan.ten)
            .join(BaiGhepCongDoan, BaiGhepCongDoan.bai_ghep_id == BaiGhep.id)
            .join(BaiGhepCongDoanMap,
                  BaiGhepCongDoanMap.bai_ghep_cong_doan_id == BaiGhepCongDoan.id)
            .where(BaiGhepCongDoanMap.lsx_id == lsx.id)
        ).all()
        hong = next((m for m in mat if m[1] not in con_lai), None)
        if hong:
            raise LsxConflict(
                f'Bước "{hong[2]}" đang chạy chung trong bài ghép {hong[0]} — tách bước khỏi bài '
                f"trước khi bỏ nó khỏi routing"
            )
        removed_ids = {r.id for r in lsx.cong_doans if r not in rows and r.id is not None}
        # Cạnh còn sống trỏ VÀO bước sắp xoá. Phân đôi theo chủ sở hữu bước phụ thuộc:
        #  · Bước ở LỆNH KHÁC → chặn: routing của lệnh này không có quyền viết lại cạnh của lệnh kia.
        #  · Bước trong CHÍNH lệnh này → cạnh đó đang được chính lần lưu này vẽ lại, gỡ luôn cạnh
        #    chết. Không gỡ thì FK `buoc_truoc_id` (ondelete RESTRICT) làm vỡ `sync_cong_doans`,
        #    còn chặn cứng thì XEM TRƯỚC báo oan — payload xem-trước cố ý KHÔNG gửi
        #    `phu_thuoc_step_keys` (xem `LsxRoutingTable.xemTruocChuoi`) nên mọi lần bỏ bước giữa
        #    chuỗi đều dính "Không thể xóa bước đang được <chính lệnh này> phụ thuộc".
        canh_chet: list[LsxCongDoanPhuThuoc] = []
        for e in self.repo.phu_thuoc_toi_buoc(removed_ids):
            if e.buoc_sau_id in removed_ids:
                continue
            dep = self.db.get(LsxCongDoan, e.buoc_sau_id)
            if dep is not None and dep.lsx_id == lsx.id:
                canh_chet.append(e)
                continue
            dep_lsx = self.db.get(Lsx, dep.lsx_id) if dep else None
            raise LsxConflict(
                f"Không thể xóa bước đang được {dep_lsx.ma if dep_lsx else 'LSX khác'} / "
                f"{dep.ten if dep else 'công đoạn khác'} phụ thuộc"
            )
        for e in canh_chet:
            dep = self.db.get(LsxCongDoan, e.buoc_sau_id)
            if dep is not None and e in dep.phu_thuoc:
                dep.phu_thuoc.remove(e)   # delete-orphan
            else:
                self.db.delete(e)
        if canh_chet:
            self.db.flush()
        self.repo.sync_cong_doans(lsx, rows)

        # Vật tư là khai báo riêng của bước, chọn từ danh mục; không đọc PTG.
        for row, d in zip(rows, payloads):
            if "vat_tus" not in d:
                continue
            vat_tus = d.get("vat_tus") or []
            # Khoá là CẶP `(hang_loai, id)` (08/09/2026): bước ăn cả giấy lẫn vật tư, mà Giấy #7 và
            # Vật tư #7 là hai món khác nhau — khoá bằng id trần sẽ báo trùng oan và ghi nhầm món.
            caps = [(str(v.get("hang_loai") or HANG_VAT_TU), int(v.get("vat_tu_id") or 0))
                    for v in vat_tus]
            if len(caps) != len(set(caps)):
                raise LsxValidationError("Một vật tư không được chọn trùng trong cùng công đoạn")
            # Món ĐÃ nằm trên bước từ trước — giữ lại được kể cả khi danh mục đã ngừng nó. Chặn cả
            # hai kiểu như trước thì một lệnh cũ có vật tư ngừng dùng là KHÔNG LƯU LẠI ĐƯỢC routing
            # nữa, kể cả khi người ta chỉ sửa cái khác.
            cu_theo_cap = {(v.hang_loai, int(v.vat_tu_id)): v for v in row.vat_tus if v.vat_tu_id}
            mons = self._mon_active()
            thieu = [c for c in caps if c not in mons and c not in cu_theo_cap]
            if thieu:
                raise LsxValidationError(
                    "Vật tư không tồn tại hoặc đã ngừng dùng — chọn món khác")
            row.vat_tus.clear()
            # FLUSH giữa xoá và thêm: bảng có UNIQUE (lsx_cong_doan_id, hang_loai, vat_tu_id), mà
            # lưu lại bước với ĐÚNG món cũ là xoá rồi thêm lại chính cặp đó. Không ép DELETE chạy
            # trước thì SQLAlchemy gộp một lượt và INSERT đụng hàng chưa kịp xoá → 500 ngay khi
            # bấm Lưu lần thứ hai mà không đổi gì.
            self.db.flush()
            for pos, (item, cap) in enumerate(zip(vat_tus, caps)):
                # Món đã ngừng dùng thì `_mon_active` không có — mượn SNAPSHOT của chính dòng cũ,
                # đúng thứ đang hiện trên màn, thay vì để tên/đơn vị rỗng.
                mon = mons.get(cap)
                cu = cu_theo_cap.get(cap)
                row.vat_tus.append(LsxCongDoanVatTu(
                    hang_loai=cap[0],
                    vat_tu_id=cap[1],
                    # `or ""`: đơn vị gốc có thể CHƯA KHAI (nullable từ 2026-08-08) còn cột
                    # snapshot NOT NULL — không chặn thì IntegrityError 500.
                    vat_tu_ma_snapshot=(getattr(mon, "ma", None)
                                        or getattr(cu, "vat_tu_ma_snapshot", None) or ""),
                    vat_tu_ten_snapshot=(getattr(mon, "ten", None)
                                         or getattr(cu, "vat_tu_ten_snapshot", None) or ""),
                    don_vi_snapshot=(getattr(mon, "don_vi_gia", None)
                                     or getattr(cu, "don_vi_snapshot", None) or ""),
                    so_luong=float(item["so_luong"]), thu_tu=pos,
                    # Cờ MÁY BUNG / NGƯỜI KHAI đi theo từng dòng: lần bung sau chỉ thay dòng máy,
                    # dòng người đã sửa thì chừa ra. Client cũ không gửi ⇒ False = người khai.
                    tu_dong=bool(item.get("tu_dong")),
                ))

        # Ghi lại cạnh đến từng bước; key có thể trỏ bước cùng LSX hoặc LSX khác cùng đơn hàng.
        all_keys = {k for d in payloads for k in (d.get("phu_thuoc_step_keys") or [])}
        predecessors = {
            x.step_key: x for x in self.db.execute(
                select(LsxCongDoan).where(LsxCongDoan.step_key.in_(all_keys))
            ).scalars()
        } if all_keys else {}
        for row, d in zip(rows, payloads):
            if "phu_thuoc_step_keys" not in d:
                continue
            desired_ids: list[int] = []
            for key in dict.fromkeys(d.get("phu_thuoc_step_keys") or []):
                pred = predecessors.get(key)
                if pred is None:
                    raise LsxValidationError("Không tìm thấy công đoạn tiền nhiệm")
                if pred.id == row.id:
                    raise LsxValidationError("Công đoạn không thể tự phụ thuộc")
                pred_lsx = self.db.get(Lsx, pred.lsx_id)
                if pred_lsx is None or pred_lsx.order_id != lsx.order_id:
                    raise LsxValidationError("Chỉ được phụ thuộc công đoạn thuộc cùng đơn hàng")
                desired_ids.append(pred.id)
            # Giữ lại cạnh không đổi để tránh INSERT đụng UNIQUE trước khi ORM kịp DELETE cạnh cũ.
            existing = {edge.buoc_truoc_id: edge for edge in row.phu_thuoc}
            row.phu_thuoc[:] = [existing[pred_id] for pred_id in desired_ids if pred_id in existing]
            for pred_id in desired_ids:
                if pred_id not in existing:
                    row.phu_thuoc.append(LsxCongDoanPhuThuoc(buoc_truoc_id=pred_id))
        self.db.flush()
        self._kiem_chu_trinh_phu_thuoc(lsx.order_id)
        self._ap_chuoi_nguoc(lsx)     # đơn vị + số lượng của MỌI bước là dẫn xuất, server ghi
        # SAU chuỗi ngược: lượng vật tư tính trên số vào–ra của chính bước, số ấy vừa mới chốt.
        self._bung_lai_vat_tu(lsx, doi_cd)
        if not commit:
            # XEM TRƯỚC (đổi/chèn công đoạn): số vào–ra + đơn vị của MỌI bước đã nằm trên
            # `lsx.cong_doans` nhưng CHƯA ghi DB. Không đụng bài ghép / trạng thái / audit —
            # người gọi (`xem_truoc_routing`) đọc số xong rollback. Trả `lsx` in-session.
            return lsx
        self._bai_ghep_xep_lai(lsx)   # lệnh đang ghép → thứ tự bước chung của bài phải theo
        thieu = self.thieu_cua(lsx)
        if thieu and lsx.trang_thai != TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_CHO_BO_SUNG
        elif not thieu and lsx.trang_thai == TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_NHAP
        # §10: routing lệch bài tính giá thì phải lưu NGƯỜI xác nhận (audit đã có) + LÝ DO.
        detail = f"Sửa routing lệnh {lsx.ma}: {truoc} → {len(rows)} công đoạn"
        if (ly_do or "").strip():
            detail += f" — lý do: {ly_do.strip()}"
        self.audit.create(
            actor_user_id=actor.id, action="update_lsx_routing", target=f"lsx:{lsx.id}",
            detail=detail,
        )
        self.repo.commit()
        return self.get(lsx_id)

    def _bai_ghep_xep_lai(self, lsx: Lsx) -> None:
        """Routing của lệnh đổi → đánh lại thứ tự bước chung của bài rồi tính lại. KHÔNG commit.

        `_sap_lai_thu_tu` trước đây chỉ chạy khi GỘP / TÁCH. Nhưng sửa routing đổi được cả
        `thu_tu` lẫn `cong_doan_id` của bước đang bị đè (chỉ XOÁ bước đó mới bị chặn), nên
        `thu_tu` của bước chung thiu ngay sau lần kéo-thả đầu tiên — mà `_node_chungs` chạy
        NGƯỢC theo đúng thứ tự đó để chia hao. Sai lặng lẽ, không ai báo.

        Import trễ y như `BaiGhepService._lsx_svc` đi chiều ngược lại: hai service gọi chéo nhau,
        import ở đầu file là vòng.
        """
        ghep = self._ghep_cua(lsx)
        if ghep is None:
            return
        from ..repositories.bai_ghep_repo import BaiGhepRepository
        from .bai_ghep_service import BaiGhepService

        svc = BaiGhepService(self.db, BaiGhepRepository(self.db), self.audit, self.sequence)
        bg = ghep[0]
        svc._sap_lai_thu_tu(bg)
        svc._tinh_lai(bg)

    def _kiem_chu_trinh_phu_thuoc(self, order_id: int) -> None:
        step_ids = set(self.db.execute(
            select(LsxCongDoan.id).join(Lsx, Lsx.id == LsxCongDoan.lsx_id)
            .where(Lsx.order_id == order_id)
        ).scalars())
        edges = self.db.execute(select(
            LsxCongDoanPhuThuoc.buoc_truoc_id, LsxCongDoanPhuThuoc.buoc_sau_id
        ).where(
            LsxCongDoanPhuThuoc.buoc_truoc_id.in_(step_ids),
            LsxCongDoanPhuThuoc.buoc_sau_id.in_(step_ids),
        )).all() if step_ids else []
        graph: dict[int, list[int]] = {i: [] for i in step_ids}
        indegree = {i: 0 for i in step_ids}
        for a, b in edges:
            graph[a].append(b)
            indegree[b] += 1
        queue = [i for i, n in indegree.items() if n == 0]
        seen = 0
        while queue:
            node = queue.pop()
            seen += 1
            for nxt in graph[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if seen != len(step_ids):
            raise LsxValidationError("Phụ thuộc công đoạn tạo thành vòng lặp")

    def set_trang_thai(self, *, lsx_id: int, trang_thai: str, actor) -> Lsx:
        lsx = self.get(lsx_id)
        if trang_thai not in TRANG_THAI_LSX:
            raise LsxValidationError("Trạng thái không hợp lệ")
        if trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxValidationError("Lập kế hoạch qua màn Xếp lịch, không đổi trực tiếp ở đây")
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxConflict("Lệnh đã lập kế hoạch — gỡ kế hoạch trước")
        if trang_thai == TT_SAN_SANG:
            thieu = self.thieu_cua(lsx)
            if thieu:
                raise LsxConflict("Còn thiếu dữ liệu — bổ sung xong mới đánh dấu sẵn sàng")
        lsx.trang_thai = trang_thai
        self.audit.create(
            actor_user_id=actor.id, action="lsx_trang_thai", target=f"lsx:{lsx.id}",
            detail=f"Lệnh {lsx.ma} → {trang_thai}",
        )
        self.repo.commit()
        return self.get(lsx_id)

    def xoa(self, *, lsx_id: int, actor) -> int:
        """Xoá lệnh chưa phát hành → dòng đơn quay lại hàng chờ. Trả `order_id` để router bắn SSE."""
        lsx = self.get(lsx_id)
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxConflict("Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi xoá")
        # Coupling bài ghép: neo thành viên là FK RESTRICT (chặn ở Postgres); SQLite dev tắt FK nên
        # chặn ở đây + báo đẹp. Gỡ LSX khỏi bài ghép trước rồi mới xoá được lệnh.
        ghep_ma = self.db.execute(
            select(BaiGhep.ma)
            .join(BaiGhepThanhVien, BaiGhepThanhVien.bai_ghep_id == BaiGhep.id)
            .where(BaiGhepThanhVien.lsx_id == lsx_id)
        ).scalars().first()
        if ghep_ma:
            raise LsxConflict(f"LSX đang trong bài ghép {ghep_ma} — gỡ khỏi bài trước khi xoá")
        self._chan_dang_giu_cho(lsx)
        order_id, ma = lsx.order_id, lsx.ma
        self.repo.delete(lsx)
        self.audit.create(
            actor_user_id=actor.id, action="delete_lsx", target=f"lsx:{lsx_id}",
            detail=f"Xoá lệnh {ma}",
        )
        self.repo.commit()
        return order_id
