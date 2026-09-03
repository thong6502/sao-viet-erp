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
from ..models.cong_doan import CongDoan
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
    TRANG_THAI_LSX,
    Lsx,
    LsxCongDoan,
    LsxCongDoanPhuThuoc,
    LsxCongDoanVatTu,
)
from ..models.may_thiet_bi import MayThietBi
from ..models.order import STATUS_CANCELLED, STATUS_ORDERED, Order, OrderLine
from ..models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia
from ..models.quotation import QuoteVersion
from ..models.user import User
from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn
from ..services.bu_hao_engine import hao_buoc
from ..models.don_vi_do import TRAM_CAI, TRAM_CON, TRAM_TAY, TRAM_TO, TRAM_TO_NGUYEN
from ..services.dong_giay import (
    ban_do_tram, dich_chuoi, don_vi_chuoi, ma_cua_tram, tram_cua, tren_dong_giay,
)
from ..models.don_vi_do import DonViDo
from ..services.bien_cong_thuc import KHUNG_LUA_MAC_DINH, ngu_canh_lenh, quy_cach_bien
from ..services.don_vi_do_service import cong_thuc_chu, cong_thuc_the_so
from ..services.piece_work_service import dau_viec_khop, khoan_snapshot
from ..services.quy_doi_service import (
    _so as _so_vn, _tien, bien_trong, doi_theo_quy_cach, don_vi_map, tien_khoan,
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


def _dinh_muc_snapshot(dm) -> dict:
    """Ảnh chụp ĐỊNH MỨC của một đầu việc (`cong_doan_dau_viec`) để ghim vào bước Tổ.

    Ba mức năng suất đi cùng nhau: `nang_suat_nguoi_gio` là TRUNG BÌNH — số chảy vào công thức
    thời lượng; min/max chỉ để ra khoảng nhanh–chậm, chưa khai thì để None và râu co về một điểm.
    `don_vi_nang_suat` DORMANT từ 10/08/2026: nhãn nay KHOÁ theo đơn giá khoán
    (`dv_nang_suat_theo_khoan`), không ai khai được nữa. Vẫn chụp để dữ liệu cũ không mất, nhưng
    ĐỪNG đọc khoá này ra làm nhãn — đọc là quay lại lối "người khai chọn" vừa bỏ.
    """
    return {
        "nang_suat_nguoi_gio": _f(dm.nang_suat_nguoi_gio),
        "nang_suat_nguoi_gio_min": _f(dm.nang_suat_nguoi_gio_min) or None,
        "nang_suat_nguoi_gio_max": _f(dm.nang_suat_nguoi_gio_max) or None,
        "don_vi_nang_suat": dm.don_vi_nang_suat or None,
        # `so_nguoi_toi_thieu` mới chỉ là KHAI BÁO: ghim theo bước để không mất, nhưng chưa vào
        # công thức thời lượng và chưa chặn gì.
        "so_nguoi_toi_thieu": int(getattr(dm, "so_nguoi_toi_thieu", 1) or 1),
        "so_nguoi_tieu_chuan": int(dm.so_nguoi_tieu_chuan),
        "so_nguoi_toi_da": int(dm.so_nguoi_toi_da),
    }


def ma_don_vi_toc_do(may) -> str | None:
    """Mã ĐƠN VỊ mà tốc độ của máy đếm: `to_gio` → `to`. None khi máy chưa khai.

    Máy lưu mã dạng `<đơn vị>_gio` (`may_thiet_bi.don_vi_toc_do`), sinh từ chính danh mục Đơn vị &
    quy đổi. Cắt hậu tố ở ĐÚNG một chỗ này để nơi khác khỏi tự cắt mỗi nơi một kiểu.
    """
    ma = (getattr(may, "don_vi_toc_do", None) or "").strip().lower()
    return ma[:-4] if ma.endswith("_gio") else (ma or None)
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

    Bước TỔ dùng công thức riêng, cũng ra BA con số theo đúng lối trên::

        thời lượng = thời gian khác + SL vào ÷ (năng suất khoán × số người TIÊU CHUẨN) × 60

    Ba mức năng suất (tối thiểu · trung bình · tối đa) khai ở ĐỊNH MỨC ĐẦU VIỆC và được ghim vào
    bước lúc chọn đầu việc (`khoan_json`). Năng suất CAO ⇒ thời lượng NHỎ — GIỐNG hệt máy có ba
    mức tốc độ. **Nhân với số người TIÊU CHUẨN** (chốt 20/08/2026): năng suất khoán khai theo ĐẦU
    NGƯỜI (`nang_suat_nguoi_gio`), nên kíp chuẩn N người làm nhanh gấp N — cùng một kíp chuẩn nhân
    đều cả ba mức. Dùng số người TIÊU CHUẨN (`so_nhan_cong_tieu_chuan`), KHÔNG dùng số người kế
    hoạch/tối thiểu/tối đa — mấy số kia chỉ để bàn xếp lịch cân quân số + đối chiếu thực hiện.
    Bước THUÊ NGOÀI đi theo ngày gửi/nhận, thời lượng máy = 0.

    **`sl_tinh` — SL vào ĐÃ QUY ĐỔI về đơn vị của tốc độ** (15/08/2026), dạng
    `(số, tên đơn vị, câu diễn giải)`. Nơi gọi dựng bằng `LsxService._sl_theo_don_vi`, tức đúng
    cơ chế tiền khoán: cầu quy đổi → công thức của đơn vị.

    - có   ⇒ chia số ĐÃ ĐỔI cho tốc độ. Máy khai `m²/giờ` mà bước đếm tờ thì tờ được quy ra m².
    - None ⇒ **chạy = 0** + `phuong_phap = "chua_quy_doi"` + cảnh báo. KHÔNG lùi về chia số thô:
      chia số tờ cho `500 kg/h` ra con số trông như thật, và số trông-như-thật thì không ai đi kiểm.

    None là mặc định nên MỌI nơi gọi phải truyền — sót một chỗ là bước đó im lặng về 0 phút.
    Sáu nơi gọi trong hệ (lệnh · bài ghép · xếp lịch · kế hoạch vật tư) đều đã nối.

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
    nguoi_ke_hoach = max(int(getattr(cd, "so_nhan_cong", 1) or 1), 1)
    nguoi_toi_da_raw = getattr(cd, "so_nhan_cong_toi_da", None)
    nguoi_toi_da = max(int(nguoi_toi_da_raw or nguoi_ke_hoach), 1)
    nguoi_tinh: int | None = None

    khoan = khoan_chuan_bi_cua_may(may) if loai == LB_MAY else []
    setup = _f(getattr(may, "makeready_time_default", None)) if (loai == LB_MAY and may) else 0.0
    may_dung_duoc = may if loai == LB_MAY else None
    ns = _f(getattr(may_dung_duoc, "toc_do", None)) if loai == LB_MAY else _f(cd.nang_suat)
    nang_suat_hieu_dung = ns

    def _chay(toc_do: float) -> float:
        return (vao * 60.0 / toc_do * luot) if toc_do > 0 and vao > 0 else 0.0

    if loai == LB_TO:
        # Thời lượng bước TỔ = SL vào ÷ (năng suất khoán × SỐ NGƯỜI TIÊU CHUẨN) × 60. Năng suất
        # khoán khai THEO ĐẦU NGƯỜI (`nang_suat_nguoi_gio`) nên kíp chuẩn N người làm nhanh gấp N.
        # Dùng số người TIÊU CHUẨN (định mức), KHÔNG dùng kế hoạch/tối thiểu/tối đa. Dải năng suất
        # (tối thiểu/trung bình/tối đa) ghim theo đầu việc cho ra BA con thời lượng như máy có ba
        # mức tốc độ — cùng một kíp chuẩn nhân đều cả ba. Chưa khai mức nào thì mức đó rơi về TB.
        kh_dai = getattr(cd, "khoan_json", None) or {}
        ns_thap = _f(kh_dai.get("nang_suat_nguoi_gio_min")) or ns
        ns_cao = _f(kh_dai.get("nang_suat_nguoi_gio_max")) or ns
        nguoi_tc = max(int(getattr(cd, "so_nhan_cong_tieu_chuan", 1) or 1), 1)
        nguoi_tinh = nguoi_tc
        nang_suat_hieu_dung = ns * nguoi_tc

        def _chay_to(muc: float) -> float:
            mau = muc * nguoi_tc
            return (vao / mau * 60.0) if mau > 0 and vao > 0 else 0.0

        chay = _chay_to(ns)
        chay_nhanh = _chay_to(ns_cao)   # năng suất CAO ⇒ chạy nhanh ⇒ thời lượng NHỎ nhất
        chay_cham = _chay_to(ns_thap)
        phuong_phap = "to" if ns > 0 else "thieu_nang_suat"
    elif loai == LB_MAY:
        # Máy chưa khai dải thì min/max rơi về tốc độ TB — ba số bằng nhau, không bịa khoảng.
        toc_do_cao = _f(getattr(may_dung_duoc, "toc_do_max", None)) if may_dung_duoc else 0.0
        toc_do_thap = _f(getattr(may_dung_duoc, "toc_do_min", None)) if may_dung_duoc else 0.0
        chay = _chay(ns)
        chay_nhanh = _chay(toc_do_cao) if toc_do_cao > 0 else chay
        chay_cham = _chay(toc_do_thap) if toc_do_thap > 0 else chay
        phuong_phap = "may" if ns > 0 else "thieu_nang_suat"
    else:
        chay = chay_nhanh = chay_cham = 0.0
        nang_suat_hieu_dung = 0.0
        phuong_phap = "thue_ngoai"

    # QUY ĐỔI TỊT thắng mọi lý do khác: có tốc độ mà không biết bước nhận bao nhiêu THEO ĐƠN VỊ ĐÓ
    # thì phép chia vô nghĩa. Nói "chưa quy đổi" chứ đừng nói "chưa khai năng suất" — sai chỗ khai.
    if loai in (LB_MAY, LB_TO) and sl_tinh is None:
        chay = chay_nhanh = chay_cham = 0.0
        phuong_phap = "chua_quy_doi"
        canh_bao.append(
            "Chưa quy đổi được số lượng vào sang đơn vị của tốc độ nên không tính được thời gian "
            "chạy. Khai cầu quy đổi (hoặc công thức cho đơn vị đó) ở Cấu hình danh mục → "
            "Đơn vị & quy đổi."
        )
    elif phuong_phap == "thieu_nang_suat":
        # Bước Tổ không có máy — chỉ về đúng chỗ phải đi khai, không thì người dùng đi tìm ô tốc
        # độ máy cho một bước dán tay.
        canh_bao.append(
            "Đầu việc chưa khai năng suất (hoặc bước chưa chọn đầu việc khoán) nên không tính "
            "được thời gian chạy."
            if loai == LB_TO else
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
        "nguon_nang_suat": "dau_viec" if loai == LB_TO else ("may" if loai == LB_MAY else None),
        "nang_suat_co_so": round(ns, 2) if ns > 0 else None,
        "nang_suat_hieu_dung": round(nang_suat_hieu_dung, 2) if nang_suat_hieu_dung > 0 else None,
        "so_luot_chay": luot if loai == LB_MAY else None,
        "so_nhan_cong_ke_hoach": nguoi_ke_hoach if loai in (LB_MAY, LB_TO) else None,
        "so_nhan_cong_tieu_chuan": (
            max(int(getattr(cd, "so_nhan_cong_tieu_chuan", 1) or 1), 1)
            if loai in (LB_MAY, LB_TO) else None
        ),
        "so_nhan_cong_toi_da": nguoi_toi_da if loai == LB_TO else None,
        "so_nhan_cong_tinh": nguoi_tinh,
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


class LsxService:
    def __init__(self, db: Session, repo, audit, sequence) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.sequence = sequence
        self._tram_cache: dict | None = None     # cờ trạm dòng giấy (xem `_tram`)
        self._rates_cache: list | None = None   # bảng đơn giá khoán (xem `_piece_rates`)
        self._dv_cache: dict | None = None      # danh mục đơn vị (xem `_don_vis`)
        self._cap_cache: dict | None = None     # đồ thị cặp quy đổi (xem `_cap_quy_doi`)
        self._cap_graph_cache: dict | None = None  # cặp quy đổi đã dựng đồ thị (xem `_he_so_ngoai_dong`)
        self._ma_dv_cache: dict | None = None   # tên đơn vị → mã (xem `_ma_don_vi`)

    # ================= tra cứu phụ trợ =================

    def _tram(self) -> dict[str, str]:
        """Bản đồ `{mã đơn vị: trạm dòng giấy}` — CACHE theo service.

        `tinh_nguoc_routing` chạy một lần mỗi lệnh, mà màn danh sách bung cả trăm lệnh: hỏi lại
        danh mục từng lệnh là đúng bài N+1 đã dính một lần ở màn đơn hàng.
        """
        if self._tram_cache is None:
            self._tram_cache = ban_do_tram(self.db)
        return self._tram_cache

    def _bu_hao_rows(self) -> list[dict]:
        # KHÔNG lọc `active`: bảng bù hao ở đây là để DỰNG LẠI số của lệnh đã có. Mã bù hao bị
        # ngừng dùng sau khi lệnh chạy mà lọc ở đây thì số tờ hao đổi ⇒ lệnh cũ tự nhiên lệch.
        # Ô CHỌN mã bù hao lọc ở router danh mục, không phải ở đây.
        return [_bu_hao_to_dict(b) for b in self.db.execute(select(BuHao)).scalars()]

    # --- Khoán theo đầu việc (bảng giá của tổ) + đơn vị quy đổi ---------------
    # Cache theo INSTANCE service (1 request = 1 instance): bung lệnh gọi mỗi bước một lần, mà hai
    # bảng này nhỏ và không đổi trong một request — query lại từng bước là N+1 vô ích.

    def _piece_rates(self) -> list:
        if self._rates_cache is None:
            from ..models.piece_work import PieceRate

            self._rates_cache = list(
                self.db.execute(select(PieceRate).where(PieceRate.active.is_(True))).scalars()
            )
        return self._rates_cache

    def _don_vis(self) -> dict:
        if self._dv_cache is None:
            from ..models.don_vi_do import DonViDo

            # KHÔNG lọc `active` — xem `DonViDoRepository.all_rows`. Đơn vị ngừng dùng mà lệnh cũ
            # còn trỏ tới thì `don_vi_map` mất khoá ⇒ `tien_khoan` không ra ⇒ tiền công thợ của
            # lệnh lịch sử hiện RỖNG. Ô chọn lọc ở router, không phải ở bảng tra.
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

    def _he_so_ngoai_dong(self, dv_vao: str | None, dv_ra: str | None) -> tuple[float | None, str | None]:
        """Hệ số "1 <vào> = hs <ra>" của bước NGOÀI dòng giấy — LẤY TỪ module Đơn vị & quy đổi.

        Trả `(hs, loi)`:
        - cùng đơn vị (kẽm→kẽm) → `(1.0, None)`: phép đồng nhất, không phải hệ số hardcode;
        - khác đơn vị có cầu trong `don_vi_quy_doi` (vd 1 bài in = 4 bản kẽm) → `(4.0, None)`;
        - khác đơn vị mà module CHƯA khai cầu → `(None, câu-lỗi)`.

        NGUỒN DUY NHẤT là cầu quy đổi (`quy_doi_service.doi`), KHÔNG đọc `he_so_ngoai_dong` khai tay
        (nguồn thứ hai gây sai), KHÔNG mặc định ×1 khi thiếu cầu — thiếu thì báo lỗi để người khai.
        """
        if not dv_vao or not dv_ra or dv_vao == dv_ra:
            return 1.0, None
        from .quy_doi_service import cap_map, doi

        if self._cap_graph_cache is None:
            self._cap_graph_cache = cap_map(self._cap_quy_doi())
        kq = doi(1.0, dv_vao, dv_ra, self._don_vis(), self._cap_graph_cache)
        if "gia_tri" in kq and _f(kq["gia_tri"]) > 0:
            return _f(kq["gia_tri"]), None
        return None, kq.get("ly_do") or f"Chưa khai quy đổi giữa {dv_vao} và {dv_ra} ở Đơn vị & quy đổi."

    def _khoan_mac_dinh(self, department_id: int | None, cd_obj) -> dict | None:
        """Đầu việc khoán ĐIỀN SẴN cho một bước: khớp đúng 1 thì tự điền, nhiều thì để trống.

        Nhiều đầu việc khớp (bế tay / bế máy cùng công đoạn) là chuyện chỉ người biết → máy để
        trống + nhắc, KHÔNG chọn hộ. Tổ không ăn khoán thì danh sách rỗng, cũng ra None.

        """
        khop = self._dau_viec_cua_cong_doan(cd_obj, department_id)
        if not khop:
            return None
        assoc = {x.piece_rate_id: x for x in (getattr(cd_obj, "dau_viec_dinh_muc", None) or [])}
        chosen = khop[0] if len(khop) == 1 else None
        if chosen is None:
            return None
        snap = khoan_snapshot(chosen)
        dm = assoc.get(chosen.id)
        if dm is not None:
            snap.update(_dinh_muc_snapshot(dm))
        return snap

    def _dau_viec_cua_cong_doan(self, cd_obj, department_id: int | None) -> list:
        rates = dau_viec_khop(self._piece_rates(), department_id=department_id)
        links = (getattr(cd_obj, "dau_viec_dinh_muc", None) or []) if cd_obj is not None else []
        if cd_obj is not None:
            allowed = {x.piece_rate_id for x in links}
            return [r for r in rates if r.id in allowed]
        return rates

    def _vat_tu_bung(self, dm, buoc, quy_cach: dict | None) -> tuple[list[dict], list[str]]:
        """Vật tư của MỘT đầu việc, kèm số lượng tính cho ĐÚNG bước này — nền BOM.

        Danh sách khai ở danh mục (`cong_doan_dau_viec_vat_tu`) chỉ có TÊN; số lượng suy ở đây vì
        định mức tuỳ quy cách của từng lệnh. MỘT đường duy nhất: **công thức lượng của chính món
        hàng** (`vat_tu_in_an.cong_thuc_luong`, mg 0194). Riêng nhất nên đúng nhất: keo và mực cùng
        đo bằng `kg` mà ăn khác hẳn nhau.

        Hai đường "trả lời hộ" đã gỡ, cùng một lý do — thứ dùng chung không biết món nào đang hỏi:
        cách đo của ĐƠN VỊ (`don_vi_do.cong_thuc`, mg `0215`, 17/08/2026) và quy đổi từ đơn vị của
        BƯỚC sang đơn vị vật tư (BFS trên cầu quy đổi, 18/08/2026 — xem `_luong_vat_tu`).

        KHÔNG ĐOÁN: chưa khai công thức thì bỏ dòng đó ra khỏi kết quả và trả câu lý do — thà người
        kế hoạch tự thêm còn hơn bung một con số sai trông như thật.

        Trả `([], [])` khi chưa đủ ngữ cảnh (gọi từ `dau_viec_options` lúc đổi tổ, chưa có bước).
        """
        vat_tus = list(getattr(dm, "vat_tus", None) or []) if dm is not None else []
        if not vat_tus or buoc is None:
            return [], []
        sl = _f(getattr(buoc, "so_luong_vao", 0))
        if sl <= 0:
            return [], []
        mats = {
            m.id: m for m in self.db.execute(
                select(VatTuInAn).where(
                    VatTuInAn.id.in_([v.vat_tu_id for v in vat_tus]),
                    VatTuInAn.active.is_(True),
                )
            ).scalars()
        }
        # Bơm SỐ CỦA CHÍNH BƯỚC lên trên ngữ cảnh lệnh — `sl_vao`/`sl_ra` chỉ tồn tại ở tầng này.
        # Bơm SAU `ngu_canh_lenh` vì hàm đó assert bộ khoá của nó phải khớp `MA_NGU_CANH_PHIEU`.
        # Khung lụa mặc định 0 — tầng lệnh không có nguồn tương đương phiếu tính giá.
        ctx = {**ngu_canh_lenh(quy_cach or {}), **KHUNG_LUA_MAC_DINH,
               "sl_vao": sl, "sl_ra": _f(getattr(buoc, "so_luong_ra", 0))}
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
            so_luong, dien_giai, ly_do = self._luong_vat_tu(dvt, ctx, mat=mat)
            if so_luong is None:
                canh_bao.append(f"{mat.ten}: {ly_do}")
                continue
            ra.append({
                "vat_tu_id": mat.id, "ma": mat.ma, "ten": mat.ten, "don_vi": dvt,
                "so_luong": round(so_luong, 3), "dien_giai": dien_giai,
            })
        return ra, canh_bao

    def _goi_y_luong_vat_tu(self, buoc, quy_cach: dict | None) -> list[dict]:
        """`[{vat_tu_id, so_luong, dien_giai, ly_do}]` cho MỌI vật tư đang dùng, theo bước này.

        Vì sao server tính hộ (13/08/2026): người kế hoạch chọn "Keo vào gáy" từ dropdown thì số
        phải hiện ra NGAY — công thức đã có ở vật tư và quy cách lệnh cũng có, không việc gì bắt gõ
        tay. Frontend không tự tính được: nó không có công thức, không có bảng quy đổi, và cũng
        không nên có — công thức chỉ được có MỘT bản, ở server.

        Món chưa tính ra được vẫn CÓ trong danh sách, `so_luong=None` kèm `ly_do` (18/08/2026):
        trước đó nó biến mất im lặng, drawer để ô trống mà không ai biết vì sao — người dùng chỉ
        thấy "chỗ này không tự tính" và đoán là hỏng. Ô vẫn trống để tự gõ, đúng luật "không đoán",
        nhưng câu lý do chỉ thẳng chỗ khai công thức.

        Danh mục vật tư là bảng nhỏ (đơn vị chục dòng) nên quét hết rẻ hơn hẳn đẻ thêm một endpoint
        chỉ để hỏi từng món.
        """
        sl = _f(getattr(buoc, "so_luong_vao", 0))
        if sl <= 0:
            return []
        # Bơm SỐ CỦA CHÍNH BƯỚC lên trên ngữ cảnh lệnh — `sl_vao`/`sl_ra` chỉ tồn tại ở tầng này.
        # Bơm SAU `ngu_canh_lenh` vì hàm đó assert bộ khoá của nó phải khớp `MA_NGU_CANH_PHIEU`.
        # Khung lụa mặc định 0 — tầng lệnh không có nguồn tương đương phiếu tính giá.
        ctx = {**ngu_canh_lenh(quy_cach or {}), **KHUNG_LUA_MAC_DINH,
               "sl_vao": sl, "sl_ra": _f(getattr(buoc, "so_luong_ra", 0))}
        ra: list[dict] = []
        for mat in self.db.execute(
            select(VatTuInAn).where(VatTuInAn.active.is_(True))
        ).scalars():
            dvt = (mat.don_vi_gia or "").strip()
            if not dvt:
                continue
            so_luong, dien_giai, ly_do = self._luong_vat_tu(dvt, ctx, mat=mat)
            ra.append({
                "vat_tu_id": mat.id,
                "so_luong": None if so_luong is None else round(so_luong, 3),
                "dien_giai": dien_giai,
                "ly_do": ly_do or None,
            })
        return ra

    # `_cach_do` / `_cach_do_lan` GỠ 17/08/2026 cùng cột `don_vi_do.cong_thuc` (mg `0215`).
    # "Cách đo" treo ở ĐƠN VỊ là thứ dùng chung cho mọi ai đếm bằng đơn vị đó, trong khi câu hỏi
    # thật luôn thuộc về một MÓN / MÁY / ĐẦU VIỆC / BƯỚC cụ thể — và cả bốn nay đều có ô riêng
    # (`cong_thuc_luong` của giấy · vật tư · máy · đầu việc khoán, `cong_thuc_san_luong` của công
    # đoạn). Đừng dựng lại: mượn-trong-cụm của hàm cũ là chỗ hai đơn vị cùng cụm tranh nhau trả lời.

    def _luong_vat_tu(self, dvt: str, ctx: dict, *,
                      mat=None) -> tuple[float | None, str | None, str]:
        """Số lượng một vật tư đo bằng `dvt`. Trả `(số, diễn giải, lý do nếu tịt)`.

        MỘT đường duy nhất: `vat_tu_in_an.cong_thuc_luong` — công thức của CHÍNH món hàng (mg 0194).

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
        rieng = (getattr(mat, "cong_thuc_luong", None) or "").strip() if mat is not None else ""
        if not rieng:
            return None, None, (
                f"chưa khai công thức lượng. Mở danh mục Vật tư khác → sửa “{ten}” → điền ô "
                f"“Công thức lượng” (ra {dv_ten}).")
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

    def _dau_viec_option_dicts(
        self, cd_obj, department_id: int | None, *, buoc=None, quy_cach: dict | None = None
    ) -> list[dict]:
        """Đầu việc + định mức để drawer có thể preview nhân lực/thời gian trước khi lưu.

        `buoc` + `quy_cach` có mặt (đường đọc lệnh) thì kèm luôn VẬT TƯ đã tính số cho bước đó —
        drawer chọn công việc khoán là bung được ngay, không phải gọi thêm API. Vắng (đường đổi tổ)
        thì chỉ trả danh sách đầu việc như cũ.
        """
        assoc = {
            x.piece_rate_id: x
            for x in (getattr(cd_obj, "dau_viec_dinh_muc", None) or [])
        }
        out: list[dict] = []
        for rate in self._dau_viec_cua_cong_doan(cd_obj, department_id):
            dm = assoc.get(rate.id)
            item = {
                "id": rate.id,
                "ten": rate.ten,
                "don_vi": rate.unit,
                "don_gia": _f(rate.unit_price),
            }
            if buoc is not None:
                # Tiền công DỰ KIẾN cho ĐÚNG lựa chọn này, tính bằng cùng bộ máy `_khoan_derived`
                # dùng cho bước đã lưu — chọn đầu việc ở dropdown là "nhảy tiền" ngay, không phải
                # lưu bước rồi backend mới trả số (kể cả bước vừa gộp chưa có nền khoán nào).
                kq_t = self._khoan_tu_kh(buoc, khoan_snapshot(rate), quy_cach)
                item.update({
                    "tien_du_kien": kq_t["khoan_tien"],
                    "sl_du_kien": kq_t["khoan_sl"],
                    "don_vi_sl_du_kien": kq_t["khoan_don_vi_sl"],
                    "dien_giai_du_kien": kq_t["khoan_dien_giai"] or kq_t["khoan_ly_do"],
                })
            if dm is not None:
                vt, cb = self._vat_tu_bung(dm, buoc, quy_cach)
                item.update({
                    **_dinh_muc_snapshot(dm),
                    # Đơn vị của năng suất = đơn vị của ĐƠN GIÁ KHOÁN, không còn nhãn riêng: thời
                    # lượng nay quy SL vào về chính đơn vị đó rồi mới chia (`_sl_theo_don_vi`).
                    "don_vi_nang_suat": rate.unit,
                    "vat_tus": vt,
                    "canh_bao_vat_tu": cb,
                })
            out.append(item)
        return out

    def dau_viec_options(
        self, *, lsx_id: int, cong_doan_id: int, department_id: int | None
    ) -> list[dict]:
        """Đầu việc chọn được khi KHSX đổi tổ, lọc đồng thời theo công đoạn và tổ mới."""
        self.get(lsx_id)
        cd = self.db.get(CongDoan, cong_doan_id)
        if cd is None:
            raise LsxNotFound("Không tìm thấy công đoạn")
        if department_id is None:
            return []
        return self._dau_viec_option_dicts(cd, department_id)

    def xem_truoc_may(self, *, lsx_id: int, step_key: str, may_id: int | None) -> dict:
        """Thời lượng của MỘT bước NẾU đổi sang máy khác — tính thử, KHÔNG ghi gì vào DB.

        Vì sao drawer phải hỏi server (chủ chốt 20/08/2026 — *"chọn máy thì thời gian không thay
        đổi, phải nhấn Lưu mới đổi"*): số đem chia cho tốc độ không phải số tờ thô mà là SL vào ĐÃ
        QUY ĐỔI về đơn vị của CHÍNH máy đang chọn (`sl_tinh_cua_buoc`) — Yawa 1050 đo bằng
        `kem_gio` và còn có công thức riêng `so_kem`. Cầu quy đổi và bộ chạy công thức chỉ có ở
        server, nên trước đây drawer đành xài lại con số của LẦN LƯU TRƯỚC: bước chưa gán máy thì
        số đó là 0 ⇒ chọn máy nào cũng ra 0 phút, mà đổi giữa hai máy khác đơn vị thì lại lấy số
        quy đổi của máy CŨ ⇒ xem trước sai mà không báo gì.

        Trả về đúng khối `thoi_luong_dien_giai` mà drawer đang đọc, kèm KÍP của máy mới để ô số
        người nhảy theo luôn — bước máy thì số người là kíp đứng máy (xem `replace_routing`).
        """
        lsx = self.get(lsx_id)
        cd = next((r for r in lsx.cong_doans if r.step_key == step_key), None)
        if cd is None:
            raise LsxNotFound("Không tìm thấy bước trong lệnh")
        may = self.db.get(MayThietBi, may_id) if may_id else None
        if may_id and may is None:
            raise LsxNotFound("Không tìm thấy máy")
        kip = max(int(ceil(_f(may.so_nhan_cong))), 1) if may is not None else 1
        # Bản SAO ĐỌC của bước: KHÔNG gán `cd.may_id = ...` — gán vào ORM là autoflush ghi thẳng
        # xuống DB một lựa chọn người dùng mới chỉ rê chuột qua.
        thu = _BuocThu(cd, may_id=may_id, so_nhan_cong_tieu_chuan=kip)
        quy_cach = quy_cach_bien(lsx)
        t = thoi_luong_buoc(thu, may, self.sl_tinh_cua_buoc(thu, may, quy_cach))
        return {
            "step_key": step_key,
            "may_id": may_id,
            "so_nhan_cong_tieu_chuan": kip,
            "chiem_may_phut": t["chiem_may_phut"],
            "thoi_luong_dien_giai": t["dien_giai"],
        }

    def sl_tinh_cua_buoc(self, cd, may, quy_cach: dict | None) -> tuple[float, str, str] | None:
        """SL vào của bước quy về đơn vị của TỐC ĐỘ — đầu vào `sl_tinh` của `thoi_luong_buoc`.

        Đích: bước MÁY → đơn vị tốc độ của máy đang gán · bước TỔ → đơn vị của ĐƠN GIÁ KHOÁN
        (năng suất đầu việc đếm bằng chính thứ mà đơn giá đếm). Thuê ngoài không tính giờ máy.

        Public vì bốn service ngoài (bài ghép · xếp lịch · kế hoạch vật tư) phải dựng cùng một số —
        mỗi nơi tự suy đích là mở đường cho Gantt và drawer lệch nhau.
        """
        loai = getattr(cd, "loai_buoc", LB_MAY) or LB_MAY
        if loai == LB_MAY:
            dich = ma_don_vi_toc_do(may)
            # Công thức riêng của CHÍNH MÁY đang gán (mg `0213`) — đọc SỐNG, vì đổi máy là đổi cả
            # tốc độ lẫn cách đếm lượt. Không có máy (bước chưa gán) thì không có công thức riêng.
            ct_rieng = (getattr(may, "cong_thuc_luong", None) or "").strip() if may is not None else ""
        elif loai == LB_TO:
            kh = getattr(cd, "khoan_json", None) or {}
            dich = kh.get("don_vi")
            # Công thức GHIM trong ảnh chụp đầu việc, KHÔNG đọc lại danh mục: xưởng sửa cách đo về
            # sau không được xê dịch tiền công của lệnh đã phát (xem `khoan_snapshot`).
            ct_rieng = (kh.get("cong_thuc") or "").strip()
        else:
            return None
        return self._sl_theo_don_vi(cd, dich, quy_cach, ct_rieng=ct_rieng) if dich else None

    def _sl_theo_don_vi(self, cd, dv_dich: str | None,
                        quy_cach: dict | None, *,
                        ct_rieng: str = "") -> tuple[float, str, str] | None:
        """SL VÀO của bước quy về `dv_dich`. Trả `(số, tên đơn vị, câu diễn giải)` — None nếu tịt.

        **MỘT bộ quy đổi cho CẢ tiền lẫn giờ** (chủ chốt 15/08/2026):

            tiền khoán   SL vào → đơn vị ĐƠN GIÁ   → × đơn giá  → tiền
            thời lượng   SL vào → đơn vị TỐC ĐỘ    → ÷ tốc độ   → phút

        HAI đường, theo đúng thứ tự RIÊNG → CHUNG (cùng luật với `_luong_vat_tu`):
          ⓿ `ct_rieng` — công thức của CHÍNH đối tượng: `may_thiet_bi.cong_thuc_luong` cho bước máy,
             `khoan_json["cong_thuc"]` (ảnh chụp của đầu việc) cho bước tổ. Mg `0213`. Riêng nhất nên
             thắng: lượt in của máy 5 màu khác máy 2 màu, mà cả hai cùng đo bằng `to_gio`.
          ① `doi_theo_quy_cach` — cầu quy đổi đã khai (kể cả đi vòng qua trung gian).

        Bậc "công thức của ĐƠN VỊ ĐÍCH" GỠ 17/08/2026 (mg `0215`) — bậc ⓿ thay đúng chỗ nó: cùng bộ
        chip `sl_vao`/`sl_ra`, nhưng khai trên chính cái máy / đầu việc cần nó thay vì trên đơn vị
        dùng chung.

        Tịt cả hai ⇒ None. Nơi gọi tự quyết, hàm này KHÔNG đoán và KHÔNG lùi về số thô.

        ⚠️ Công thức riêng ra thẳng số theo `dv_dich` — KHÔNG quy đổi tiếp. Nó được khai ĐỂ trả lời
        đúng câu "bằng bao nhiêu <đơn vị đích>", nên nhân thêm một hệ số nào nữa là tính hai lần.

        Đừng chép phép đổi này ra chỗ khác: hai bản chép tay là hai cơ hội lệch, mà lệch giữa tiền
        công và giờ công của cùng một bước thì không ai soi ra.
        """
        ma_dich = (self._don_vis().get(str(dv_dich or "").strip().lower()) or {}).get("ma")
        if not ma_dich:
            return None
        sl = _f(cd.so_luong_vao)
        ten_dich = (self._don_vis().get(ma_dich) or {}).get("ten") or ma_dich

        # ⓿ công thức RIÊNG của máy / của đầu việc khoán.
        if (ct_rieng := (ct_rieng or "").strip()):
            ctx0 = {**ngu_canh_lenh(quy_cach or {}), **KHUNG_LUA_MAC_DINH,
                    "sl_vao": sl, "sl_ra": _f(cd.so_luong_ra)}
            try:
                gt0 = float(safe_eval(ct_rieng, dict(ctx0)))
            except (ValueError, ZeroDivisionError):
                gt0 = 0.0
            # Ra 0 (hoặc không chạy được) thì RƠI XUỐNG hai đường sau chứ không tịt hẳn: công thức
            # thiếu biến là chuyện của một lệnh cụ thể (chưa khai số màu, chưa có khổ), mà cầu quy
            # đổi vẫn có thể trả lời được. Tịt luôn ở đây là làm mất tiền khoán vốn đang tính ra.
            if gt0 > 0:
                the_so0 = cong_thuc_the_so(ct_rieng, ctx0)
                dau0 = "" if the_so0 == _so_vn(gt0) else f"{the_so0} = "
                return gt0, ten_dich, f"{cong_thuc_chu(ct_rieng)} = {dau0}{_so_vn(gt0)} {ten_dich}"

        # ① cầu quy đổi. Cùng đơn vị cũng đi lối này (`doi` trả thẳng, hệ số 1).
        kq = doi_theo_quy_cach(sl, cd.don_vi_vao, ma_dich, quy_cach or {},
                               self._don_vis(), self._cap_quy_doi())
        if "gia_tri" in kq:
            return float(kq["gia_tri"]), kq["don_vi"], kq["dien_giai"]
        return None

    def _khoan_theo_cong_thuc(self, cd, kh: dict, quy_cach: dict | None) -> dict | None:
        """Tiền khoán khi KHÔNG có cầu quy đổi — quy SL vào về đơn vị ĐƠN GIÁ rồi nhân đơn giá.

        Phép quy đổi KHÔNG viết ở đây: gọi `_sl_theo_don_vi`, cùng một hàm mà thời lượng dùng
        (15/08/2026). Hai bản chép tay của cùng phép đổi là hai cơ hội lệch nhau, mà lệch giữa
        tiền công và giờ công thì không ai soi ra.

        Trả None khi không quy đổi được ⇒ nơi gọi giữ nguyên câu lý do cũ. KHÔNG đoán.

        `cong_thuc` lấy từ ẢNH CHỤP `khoan_json` (mg `0213`), không đọc lại danh mục — cùng lý do
        đơn giá được ghim: sửa cách đo ở danh mục không được đổi tiền của lệnh đã phát.
        """
        kq = self._sl_theo_don_vi(cd, kh.get("don_vi"), quy_cach,
                                  ct_rieng=(kh.get("cong_thuc") or ""))
        if kq is None:
            return None
        gt, dv, cau = kq
        don_gia = _f(kh.get("don_gia"))
        tien = round(gt * don_gia)
        return {
            "khoan_sl": round(gt, 4),
            "khoan_don_vi_sl": kh.get("don_vi"),
            "khoan_tien": tien,
            # Kết thúc bằng SỐ TIỀN, cùng giọng đường MỘT (`tien_khoan`). Câu cũ dừng ở "× 600 đ"
            # nên người xem phải tự nhân — đúng thứ diễn giải sinh ra để khỏi phải làm.
            "khoan_dien_giai": f"{cau} × {_tien(don_gia)} đ/{dv} = {_tien(tien)} đ",
        }

    def _khoan_derived(self, cd, quy_cach: dict | None) -> dict:
        """Tiền khoán DỰ KIẾN của bước — tính LÚC ĐỌC, không lưu cột.

        SL lấy `so_luong_vao` (số thợ thật chạy qua tay, gồm cả tờ bù hao canh máy — thợ cán 241 tờ
        thì ăn 241 tờ), rồi ĐỔI thẳng sang đơn vị của đơn giá. Không nhân thêm hệ số ngầm nào:
        muốn trả theo lượt máy thì khai đơn giá theo đơn vị `lượt`, đừng giấu phép nhân trong code.
        """
        return self._khoan_tu_kh(cd, cd.khoan_json or {}, quy_cach)

    def _khoan_tu_kh(self, cd, kh: dict, quy_cach: dict | None) -> dict:
        """Tiền khoán DỰ KIẾN khi áp MỘT ảnh chụp đầu việc `kh` lên SL của bước `cd`.

        Tách khỏi `_khoan_derived` để dropdown đầu việc chấm TỪNG lựa chọn bằng ĐÚNG một bộ máy:
        chọn công việc khoán là ra tiền NGAY, không phải lưu bước rồi backend mới trả số. `kh` cùng
        shape `khoan_json` đã ghim — hoặc ảnh chụp `khoan_snapshot(rate)` của một lựa chọn chưa lưu.
        """
        # Hợp đồng dict: LUÔN đủ 6 khoá (None khi chưa có gì) — caller `if kq["khoan_tien"]` chứ
        # không phải `if "khoan_tien" in kq`. Trả dict rỗng khi bước chưa chọn đầu việc là mời gọi
        # KeyError ở mọi chỗ đọc.
        trong = {"khoan_sl": None, "khoan_don_vi_sl": None, "khoan_tien": None,
                 "khoan_dien_giai": None, "khoan_thieu": [], "khoan_ly_do": None}
        if not kh.get("don_vi") or not kh.get("don_gia"):
            return trong
        # ⓿ CÔNG THỨC RIÊNG của đầu việc (ảnh chụp `khoan_json["cong_thuc"]`, mg `0213`) thắng cả cầu
        # quy đổi: nó được khai ĐÚNG cho việc này, còn cầu là luật chung của hai đơn vị. Ví dụ tổ
        # đóng gói vừa "bắt tay + vào keo" (đ/cuốn theo `sl_ra`) vừa "đếm, bó" (đ/cuốn theo bó) —
        # cùng cặp `tay → cuốn`, hai cách đo khác nhau. Đặt sau cầu thì công thức chỉ chạy khi cầu
        # tịt, tức là khai xong mà không có tác dụng gì.
        if (kh.get("cong_thuc") or "").strip():
            if (kq0 := self._khoan_theo_cong_thuc(cd, kh, quy_cach)) is not None:
                return {**trong, **kq0}
        sl = _f(cd.so_luong_vao)
        kq = tien_khoan(
            sl, cd.don_vi_vao, kh["don_vi"], _f(kh["don_gia"]), quy_cach or {},
            self._don_vis(), self._cap_quy_doi(),
        )
        if "tien" not in kq:
            # ĐƯỜNG HAI (14/08/2026): không có cầu quy đổi thì đọc CÔNG THỨC của đơn vị đơn giá
            # khoán — công thức đó dùng chip `sl_vao`/`sl_ra` nên tự lấy số của CHÍNH bước này.
            #
            # Ca thật: "Bắt tay + vào keo" bước đếm `tay`, khoán đ/`cuốn`. `tay` không nối với
            # `cuốn` trong bảng cặp (cầu tay→cái nằm ở code `_he_so_cau`, không phải cặp khai) nên
            # đầu việc này CHƯA BAO GIỜ tính được tiền. Khai `cuốn := sl_ra` là xong.
            if (kq2 := self._khoan_theo_cong_thuc(cd, kh, quy_cach)) is not None:
                return {**trong, **kq2}
            return {**trong, "khoan_ly_do": kq.get("ly_do"), "khoan_thieu": kq.get("thieu") or []}
        return {
            **trong,
            "khoan_sl": round(kq["sl"], 4),
            "khoan_don_vi_sl": kq["don_vi"],
            "khoan_tien": kq["tien"],
            "khoan_dien_giai": kq["dien_giai"],
        }

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

    def _kcs_dept_ids(self, ids: set[int]) -> set[int]:
        """Tập con của `ids` có `Department.is_kcs=true` — suy `la_kcs` (KCS kiêm nhiệm) dùng
        "bước cuối routing + tổ thực hiện có is_kcs" thay vì đọc cờ khai tay đã bỏ, xem
        docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem-suy-tu-dong.md."""
        from ..models.department import Department

        if not ids:
            return set()
        rows = self.db.execute(
            select(Department.id).where(Department.id.in_(ids), Department.is_kcs.is_(True))
        ).scalars()
        return set(rows)

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
             "tinh_trang": k.tinh_trang, "ngay_ve_du_kien": k.ngay_ve_du_kien}
            for k in rows
        ]

    def tao_khuon_cho_lenh(self, lsx: Lsx, *, ten: str, loai: str | None, ngay_ve, actor) -> dict:
        """Nhánh "làm dao mới": đẻ một dòng trong danh mục Khuôn ở tình trạng `dang_dat_lam`.

        KHÁCH lấy từ chính lệnh, LOẠI lấy từ cờ của bước — không hỏi lại người dùng thứ hệ thống
        đã biết. Đó là toàn bộ lý do nhánh này nằm ở đây chứ không bắt họ mở màn Khuôn khai tay
        rồi quay lại chọn: ba lần chuyển màn cho một việc là ba lần người ta bỏ dở.

        Dựng qua `KhuonBeService` chứ không `db.add` thẳng: service giữ luật riêng của danh mục
        (sinh mã KB-####, bắt buộc ngày về khi `dang_dat_lam`) và ghi nhật ký — bỏ qua nó là dao
        mới lọt vào kho không mã, không vết.
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
                "ngay_ve_du_kien": ngay_ve,
            },
            getattr(actor, "id", None),
        )
        return {"id": k.id, "ma": k.ma, "ten": k.ten, "loai": k.loai, "so_ke": k.so_ke,
                "tinh_trang": k.tinh_trang, "ngay_ve_du_kien": k.ngay_ve_du_kien}

    def _khuon_map(self, ids: set[int]) -> dict[int, dict]:
        """Dao của các bước — nạp LÔ, không tra từng bước (routing 10 bước = 10 query thừa).

        Trả đủ thứ bước cần bày cho thợ: mã · tên ấn phẩm · SỐ KỆ (thứ thợ thật sự cần để đi lấy)
        · tình trạng · ngày về nếu đang đặt làm.
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
                "khuon_be_ngay_ve": k.ngay_ve_du_kien,
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

    def _tinh_dong(self, line: OrderLine, tp: PhieuThanhPhan | None, warnings: list[str]) -> dict:
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
            so_luong=qty, thanh_phans=[resolved], bu_hao_rows=self._bu_hao_rows(), warnings=warnings
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
                    cd = {"nhom": obj.nhom, "ten": obj.ten, "department_id": obj.department_id,
                          "requires_tooling": obj.requires_tooling,
                          "tooling_type": obj.tooling_type,
                          "don_vi_vao": obj.don_vi_vao, "don_vi_ra": obj.don_vi_ra}
            else:
                # `_cong_doan_to_dict` không bơm department_id + cờ dụng cụ → lấy thêm.
                if cd_id:
                    obj = self.db.get(CongDoan, cd_id)
                    if obj is not None:
                        cd = {**cd, "department_id": obj.department_id,
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
                "requires_tooling": bool(cd.get("requires_tooling")),
                "tooling_type": cd.get("tooling_type"),
                # Đặt loại bước NGAY TỪ ĐÂY để màn "lệnh dự kiến" và màn lệnh đã tạo nói cùng một
                # thứ tiếng — trước đó preview chỉ có cờ thuê-ngoài nên hai màn hiển thị lệch nhau.
                "loai_buoc": LB_THUE_NGOAI if row.get("nha_cung_cap") else LB_MAY,
                "nha_cung_cap": row.get("nha_cung_cap"),
                # Đơn vị KHAI ở danh mục — bảng "lệnh dự kiến" cần chúng để nói số tờ bằng đúng
                # tên xưởng đặt. Chỉ là NHÃN ở đây; hệ số quy đổi vẫn do `_don_vi_theo_buoc` lo.
                "don_vi_vao": cd.get("don_vi_vao"),
                "don_vi_ra": cd.get("don_vi_ra"),
            })
        return {"comp": comp, "quy_cach": quy_cach, "routing": routing, "sl_ptg": sl_ptg}

    def _thieu(self, *, order: Order, tp: PhieuThanhPhan | None, quy_cach: dict | None,
               routing: list[dict]) -> list[str]:
        """Checklist 'job readiness' — thiếu gì thì lệnh nằm ở CHỜ BỔ SUNG."""
        thieu: list[str] = []
        if tp is None:
            thieu.append("khong_co_ptg")
        else:
            qc = quy_cach or {}
            if not qc.get("giay_id"):
                thieu.append("thieu_giay")
            if not (qc.get("dai_thanh_pham") and qc.get("rong_thanh_pham")):
                thieu.append("thieu_kho")
            if not routing:
                thieu.append("thieu_routing")
        if order.delivery_committed_date is None:
            thieu.append("thieu_ngay_giao")
        # "thiếu khuôn bế" ĐÃ BỎ khỏi checklist (11/08/2026), và từ 16/08 khuôn ra khỏi lệnh hẳn
        # (mg `0203`) — không còn chỗ nào trong lệnh biết con dao nào, nên đừng thêm lại điều kiện
        # này: mọi lệnh có bước bế sẽ mắc kẹt ở CHỜ BỔ SUNG mà không ai gỡ được.
        return thieu

    # ================= PREVIEW =================

    def preview(self, order_id: int) -> dict:
        order = self.repo.order_with_lines(order_id)
        if order is None:
            raise LsxNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_ORDERED or order.san_xuat_released_at is None:
            raise LsxConflict("Đơn chưa được chuyển xuống sản xuất")

        da_co = self.repo.by_order_lines([ln.id for ln in order.lines])
        warnings: list[str] = []
        lines: list[dict] = []
        for line in order.lines:
            tp = self._thanh_phan(line.phieu_thanh_phan_id)
            calc = self._tinh_dong(line, tp, warnings)
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
                "thieu": self._thieu(
                    order=order, tp=tp, quy_cach=calc["quy_cach"], routing=calc["routing"],
                ),
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
            "warnings": warnings,
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
        chọn trên phiếu tính giá được mang xuống bước in làm gợi ý ban đầu. Danh mục thiếu thì để TRỐNG, KHÔNG đoán
        bừa — thời lượng hiện "—" là tín hiệu đúng để đi khai danh mục, số 0 giả thì không.
        """
        nhom, ten = r.get("nhom"), r.get("ten")
        cd_obj = self.db.get(CongDoan, r["cong_doan_id"]) if r.get("cong_doan_id") else None
        # Loại là thuộc tính của BƯỚC KHSX, không phải của danh mục Công đoạn. Routing từ phiếu có
        # thể đưa gợi ý ban đầu; sau đó kế hoạch đổi tự do trong drawer.
        loai_buoc = (LB_THUE_NGOAI if r.get("nha_cung_cap") else
                     r.get("loai_buoc") or LB_MAY)
        may_id = lsx_may_id if loai_buoc == LB_MAY and nhom == "print" else None
        may = self.db.get(MayThietBi, may_id) if may_id else None

        con = max(int(comp.get("con") or 1), 1)

        # --- Đơn vị vào/ra + hệ số: KẾ THỪA từ danh mục, không suy từ tên ---
        dv_vao, dv_ra, he_so = _don_vi_theo_buoc(
            cd_obj, con=con, xa=max(int(comp.get("so_manh_xa") or 1), 1), tram=self._tram())
        # Số lượng để 0 cho MỌI bước — `_ap_chuoi_nguoc` ghi đè ngay sau khi tạo, cả bước trên dòng
        vao = ra = 0.0

        # Bước MÁY không ghi năng suất lên bước nữa (gỡ `_nang_suat_buoc` 15/08/2026):
        # `thoi_luong_buoc` đọc SỐNG `may.toc_do`, nên cột ở đây chỉ là bản chép dễ lệch.
        nang_suat: float | None = None
        dv_nang_suat: str | None = None

        khoan = self._khoan_mac_dinh(r.get("department_id"), cd_obj)
        kip = max(int(ceil(_f(may.so_nhan_cong))), 1) if may is not None else 1
        if loai_buoc == LB_TO and khoan:
            nang_suat = _f(khoan.get("nang_suat_nguoi_gio")) or None
            # Đơn vị của năng suất LÀ đơn vị đơn giá khoán — thời lượng quy SL vào về chính nó.
            dv_nang_suat = khoan.get("don_vi")
            kip = int(khoan.get("so_nguoi_tieu_chuan") or 1)
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
            "nang_suat": nang_suat,
            "don_vi_nang_suat": dv_nang_suat,
            # Vệ sinh/rửa mực đã BỎ khỏi hệ — bước mới luôn sinh 0, cột giữ cho dữ liệu cũ.
            "ve_sinh_phut": 0.0,
            # CHỜ KỸ THUẬT kế thừa từ MÁY (bước máy) hoặc ĐẦU VIỆC (bước tổ) — mực khô · màng nguội
            # · keo đông. Là GIÁ TRỊ KHỞI ĐIỂM, kế hoạch sửa đè được ở drawer bước; kế thừa nghĩa là
            # mặc định, không phải read-only.
            "may_id": may_id,
            "so_nhan_cong": kip,
            "so_nhan_cong_tieu_chuan": kip,
            "so_nhan_cong_toi_da": (
                int(khoan.get("so_nguoi_toi_da") or kip) if loai_buoc == LB_TO and khoan else None
            ),
            "so_nhan_cong_toi_thieu": (
                int(khoan.get("so_nguoi_toi_thieu") or 1) if loai_buoc == LB_TO and khoan else None
            ),
            # Đầu việc khoán của bước: điền sẵn khi bảng giá của tổ chỉ khớp MỘT dòng. Nhiều dòng
            # (bế tay / bế máy) hoặc tổ không ăn khoán → None, kế hoạch tự chọn ở drawer.
            "khoan_json": khoan,
        }

    def _bung_vat_tu_dau_viec(self, lsx: Lsx, quy_cach: dict) -> None:
        """Bung VẬT TƯ của đầu việc vào từng bước, ngay lúc tạo lệnh.

        Vì sao ở SERVER chứ không đợi frontend (13/08/2026): server tự điền đầu việc khi bảng giá
        của tổ chỉ khớp MỘT dòng (`_khoan_mac_dinh`), nhưng frontend chỉ bung vật tư khi người dùng
        TỰ TAY chọn lại đầu việc ở drawer. Hai chỗ lệch nhau ⇒ lệnh tạo xong có đầu việc mà khối
        "Vật tư cần dùng" trống trơn, và kế hoạch vật tư không thấy gì để đi mua. Điền sẵn ở đây thì
        mọi lệnh đều có, khỏi phụ thuộc người dùng có mở drawer hay không.

        `tu_dong=True` để lần bung sau (đổi đầu việc) thay được — dòng người tự thêm vẫn chừa ra.
        Vật tư nào chưa quy đổi ra lượng được thì BỎ QUA, không ghi số đoán: `_vat_tu_bung` đã trả
        lý do, drawer hiện cảnh báo cho người kế hoạch tự thêm.
        """
        for cd in lsx.cong_doans:
            rate_id = int((cd.khoan_json or {}).get("rate_id") or 0)
            if not rate_id or not cd.cong_doan_id:
                continue
            cd_obj = self.db.get(CongDoan, cd.cong_doan_id)
            dm = next((x for x in (getattr(cd_obj, "dau_viec_dinh_muc", None) or [])
                       if x.piece_rate_id == rate_id), None)
            if dm is None:
                continue
            rows, _canh_bao = self._vat_tu_bung(dm, cd, quy_cach)
            for pos, v in enumerate(rows):
                cd.vat_tus.append(LsxCongDoanVatTu(
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
        warnings: list[str] = []
        created: list[Lsx] = []
        for line in chosen:
            tp = self._thanh_phan(line.phieu_thanh_phan_id)
            calc = self._tinh_dong(line, tp, warnings)
            comp = calc["comp"]
            so_luong_dat = int(line.qty or 0)
            thieu = self._thieu(
                order=order, tp=tp, quy_cach=calc["quy_cach"], routing=calc["routing"],
            )
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
                trang_thai=TT_CHO_BO_SUNG if thieu else TT_NHAP,
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
                    **d,
                ))
            # Số lượng từng bước là DẪN XUẤT — chạy chuỗi ngược ngay sau khi dựng đủ routing.
            self._ap_chuoi_nguoc(lsx)
            # ...rồi mới bung VẬT TƯ của đầu việc: `_vat_tu_bung` cần `so_luong_vao` của bước để
            # quy ra lượng, mà số đó chỉ có sau chuỗi ngược.
            # `quy_cach_bien` chứ KHÔNG phải `calc["quy_cach"]` thô: năm biến dẫn xuất (SL đặt ·
            # con/tờ · tờ in · tờ nguyên · tờ sau in) nằm ở CỘT của lệnh. Thiếu chúng thì công thức
            # nào dùng `so_luong`/`to_dau_vao` cũng ra 0 ⇒ bị coi là thiếu biến và không bung gì.
            self._bung_vat_tu_dau_viec(lsx, quy_cach_bien(lsx))
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
                "requires_tooling": co_dung_cu.get(cd.cong_doan_id, (False, None))[0],
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
        # (bỏ "thieu_khuon" — xem chú thích ở `_thieu`)

        # --- Điều kiện "sẵn sàng xếp lịch" của từng bước (§12) ---
        for cd in lsx.cong_doans:
            # Bước NỘI BỘ phải biết ai/máy nào làm thì Gantt mới có chỗ đặt. Bước `cho` không chiếm
            # tài nguyên nên miễn.
            if cd.loai_buoc in (LB_MAY, LB_TO) and not (cd.department_id or cd.may_id):
                if "thieu_to_may" not in thieu:
                    thieu.append("thieu_to_may")
            if cd.loai_buoc == LB_THUE_NGOAI:
                if not (cd.nha_cung_cap or "").strip() and "thieu_ncc" not in thieu:
                    thieu.append("thieu_ncc")
                if not (cd.ngay_gui_dk and cd.ngay_nhan_dk) and "thieu_tg_thue_ngoai" not in thieu:
                    thieu.append("thieu_tg_thue_ngoai")
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
        nguồn năng suất thuộc chính bước KHSX nên tuyệt đối không được endpoint này ghi đè.

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
            "department_id": cd.department_id,
            "don_vi_vao": dv_vao,
            "don_vi_ra": dv_ra,
            "he_so_quy_doi": he_so,
            # Cờ dòng giấy phải đi CÙNG cặp đơn vị mới. Client áp `don_vi_vao`/`don_vi_ra` của công
            # đoạn vừa chọn lên dòng đang sửa; không trả kèm cờ thì nó giữ cờ của công đoạn CŨ, và
            # FE không tự suy lại được (trạm là cờ trên danh mục Đơn vị, không đọc ra từ mã).
            # Đổi bước in → ghi kẽm là dòng đó mang cặp `m² → bài in` mà vẫn tự nhận "trên dòng
            # giấy" cho tới lúc lưu.
            "tren_dong_giay": tren_dong_giay(dv_vao, dv_ra, self._tram()),
            "setup_phut": _f(cd.setup_time),
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

    def _ghep_cua(self, lsx: Lsx):
        """(BaiGhep, BaiGhepThanhVien) nếu lệnh đang trong một bài ghép, không thì None."""
        if not getattr(lsx, "id", None):
            return None
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

    def buoc_ngoai_dong(
        self, buoc, quy_cach: dict | None, *, bu_hao_rows: list[dict] | None = None,
    ) -> dict | None:
        """SL vào/ra của MỘT bước NGOÀI dòng giấy (ghi kẽm, phơi bản…) — dùng CHUNG cho LỆNH và BÀI GHÉP.

        Tách ra từ vòng off-flow của `tinh_nguoc_routing` để bài ghép KHÔNG chép lại phép tính (đúng
        yêu cầu "ghép bài bám theo lệnh" — chung công đoạn thì chung một công thức). `buoc` chỉ cần ba
        thuộc tính `cong_doan_id · don_vi_vao · don_vi_ra` — cả `LsxCongDoan` lẫn `BaiGhepCongDoan`
        đều có. `quy_cach` là nguồn số của biến công thức: lệnh truyền `quy_cach_bien(lsx)`, bài ghép
        truyền `quy_cach_bien_bai(...)` (nơi `so_kem`/`so_mau`… đã gộp ở CẤP BÀI).

        Đích KHÔNG phải thành phẩm mà là CÔNG THỨC của công đoạn ("kem := so_kem" ⇒ 5 bản), rồi suy
        ngược y hệt dòng giấy: `vào = (ra/hệ_số + hao_cố_định) / (1 − hao%)`. Vế VÀO cố tình KHÔNG đọc
        công thức đơn vị vào — hai đầu cùng chốt cứng thì hao hết chỗ nhét (bệnh `vao = ra` của bản cũ).

        Trả `{so_luong_vao, so_luong_ra, he_so_quy_doi, hao_hut, hao_hut_pct[, loi_quy_doi]}`; None khi
        bước chưa khai `cong_thuc_san_luong` hoặc công thức ra ≤ 0 — nơi gọi để trống, KHÔNG đoán. Hệ số
        vào→ra LẤY TỪ module Đơn vị & quy đổi: khác đơn vị mà chưa khai cầu → `so_luong_vao=0` +
        `loi_quy_doi` để drawer và danh sách Vấn đề chặn phát hành.
        """
        if not getattr(buoc, "don_vi_ra", None):
            return None
        # CÔNG THỨC SẢN LƯỢNG của CHÍNH CÔNG ĐOẠN (mg `0214`, không phải của đơn vị RA — đã gỡ mg
        # `0215`): hai công đoạn cùng đo bằng `kem` vẫn ra số khác nhau được.
        cd_obj = self.db.get(CongDoan, buoc.cong_doan_id) if buoc.cong_doan_id else None
        ct = (getattr(cd_obj, "cong_thuc_san_luong", None) or "").strip()
        if not ct:
            return None
        try:
            ra_ngoai = float(safe_eval(ct, {**ngu_canh_lenh(quy_cach or {}), **KHUNG_LUA_MAC_DINH}))
        except (ValueError, ZeroDivisionError):
            return None
        if ra_ngoai <= 0:
            return None
        if bu_hao_rows is None:
            bu_hao_rows = [_bu_hao_to_dict(b) for b in self.db.execute(select(BuHao)).scalars()]
        quy_tac = {} if cd_obj is None else {
            "kieu_bu_hao": cd_obj.kieu_bu_hao,
            "bu_hao_id": cd_obj.bu_hao_id,
            "so_to_bu_hao": cd_obj.so_to_bu_hao,
        }
        fixed_n, pct_n = hao_buoc(quy_tac, rows=bu_hao_rows, sl=ra_ngoai)
        pct_n = min(max(pct_n, 0.0), 99.0)
        hs_n, loi_qd = self._he_so_ngoai_dong(buoc.don_vi_vao, buoc.don_vi_ra)
        if hs_n is None:
            return {
                "so_luong_vao": 0.0, "so_luong_ra": float(ceil(ra_ngoai)),
                "he_so_quy_doi": 0.0, "hao_hut": fixed_n, "hao_hut_pct": pct_n,
                "loi_quy_doi": loi_qd,
            }
        return {
            "so_luong_vao": float(ceil((ra_ngoai / hs_n + fixed_n) / (1.0 - pct_n / 100.0))),
            "so_luong_ra": float(ceil(ra_ngoai)),
            "he_so_quy_doi": hs_n, "hao_hut": fixed_n, "hao_hut_pct": pct_n,
        }

    def tinh_nguoc_routing(
        self, lsx: Lsx, *, so_con: int | None = None, bo_hao_step_keys: set[str] | None = None
    ) -> list[dict]:
        """Chạy NGƯỢC chuỗi công đoạn từ SL thành phẩm → SL vào/ra của từng bước.

        Đúng chiều tư duy xưởng và đúng mô hình BC (`Input = Output × (1 + Scrap%) + FixedScrap`,
        cộng dồn từ bước CUỐI về bước ĐẦU): *cần 20.500 hộp tốt thì phải in bao nhiêu tờ*.

        Dòng giấy có BA đơn vị và HAI cầu (`to_nguyen → to → cai`):
        - Bước **NGOÀI dòng giấy đứng ngoài chuỗi** — nhận ra bằng cờ trạm của đơn vị
          (`don_vi_do.tram_dong_giay`), không phải bằng "đơn vị để trống" như trước: nay bước chế
          bản khai đơn vị THẬT (`bai → kem`) nên trống-hay-không không còn phân biệt được. SL của
          nó = `so_kem`, giữ nguyên — hàm duyệt cả bước này là "Tính ngược" ghi đè kẽm bằng số tờ.
        - Đích = đơn vị RA của bước cuối SAU KHI LỌC: ra `cai` thì đích là SL đặt.
        - Hao lấy từ DANH MỤC công đoạn (`bu_hao_engine.hao_buoc`) ở ĐÚNG đơn vị của bước, không
          đọc `cd.hao_hut` nữa. Hao thêm của kế hoạch (`lsx.bu_hao_to`) cộng vào bước CUỐI.

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
        # --- Bước NGOÀI dòng giấy (ghi kẽm, phơi bản…): mỗi cái ĐỘC LẬP, không nối chuỗi ---------
        # Phép tính nay nằm ở `buoc_ngoai_dong` để BÀI GHÉP chạy CHUNG một công thức (ghép bài bám
        # theo lệnh). Ở đây chỉ bọc thêm khoá định danh (`idx/id/thu_tu/ten/don_vi_*`) quanh kết quả
        # số — `idx` để áp ngược, KHÔNG khớp theo `id` (lúc `tao()` id còn None).
        qc_bien = quy_cach_bien(lsx)
        for i, cd in enumerate(buoc):
            if i in idx:
                continue
            r = self.buoc_ngoai_dong(cd, qc_bien, bu_hao_rows=bu_hao_rows)
            if r is None:
                continue
            out[i] = {
                "idx": i, "id": cd.id, "thu_tu": cd.thu_tu, "ten": cd.ten,
                "don_vi_vao": cd.don_vi_vao, "don_vi_ra": cd.don_vi_ra, **r,
            }
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
            pct = min(max(pct, 0.0), 99.0)
            vao = float(ceil((can_ra / hs + fixed) / (1.0 - pct / 100.0)))
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
        self, lsx: Lsx, *, tu_step_key: str, so_to: float, so_con: int | None = None
    ) -> list[dict]:
        """Chạy XUÔI từ số tờ THẬT giao cho lệnh → sản lượng thật ở từng bước sau đó.

        Lượt về trả lời "cần bao nhiêu tờ để đủ hàng". Ghép bài thì câu hỏi ngược lại: bài in
        `so_to` tờ chung cho mọi lệnh, vậy TỪNG lệnh thật sự ra bao nhiêu? Không có lượt đi thì
        chỗ đó phải đoán bằng `so_to × con` — tức bỏ qua toàn bộ hao của các bước sau in, và số
        dư báo lên gấp cả chục lần thực tế.

        Nghịch đảo đúng công thức của lượt về (`vào = (ra/hs + tờ) / (1 − %)`):
            `ra = (vào × (1 − %) − tờ) × hs`

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
            pct = min(max(pct, 0.0), 99.0)
            hs = _hs(cd)
            ra = (dang_co * (1.0 - pct / 100.0) - fixed) * hs
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
        tu_danh_muc: dict[int, bool] = {}
        for i, cd in enumerate(buoc):
            obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
            tu_danh_muc[i] = obj is not None or cd.nhom == "prepress"
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
            if not tu_danh_muc[i]:
                cd.don_vi_vao = cd.don_vi_ra = truoc_ra or dv_to_lenh
            truoc_ra = cd.don_vi_ra or truoc_ra
        rows = {r["idx"]: r for r in self.tinh_nguoc_routing(
            lsx, bo_hao_step_keys=self._bo_hao_do_ghep(lsx),
        )}
        for i, cd in enumerate(buoc):
            r = rows.get(i)
            if r is None:            # bước ngoài dòng giấy (chế bản) — giữ nguyên số kẽm
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
        # KCS kiêm nhiệm — suy TỰ ĐỘNG: bước cuối (theo thu_tu, id — cùng thứ tự `routing_steps`
        # dùng khi phát hành) của tổ có `is_kcs=true`. Tính MỘT LẦN cho cả routing, không phải mỗi
        # bước một truy vấn.
        kcs_dept_ids = self._kcs_dept_ids(dept_ids)
        buoc_cuoi = max(lsx.cong_doans, key=lambda x: (x.thu_tu, x.id)) if lsx.cong_doans else None
        buoc_dicts = [
            self._cong_doan_dict(cd, dept_names, may_names, qc_bien,
                                 moi.get(thu_tu_idx.get(id(cd), -1)), khuon_map,
                                 la_kcs=(cd is buoc_cuoi and cd.department_id in kcs_dept_ids))
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
            # Công thợ DỰ KIẾN cả lệnh = Σ các bước quy đổi được. Bước nào chưa chọn đầu việc / thiếu
            # số để quy đổi thì không góp — nên đây là số SÀN, không phải con số cuối.
            "khoan_tien_tong": round(sum(_f(b.get("khoan_tien")) for b in buoc_dicts)),
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

    def _san_luong_dien_giai(self, cd, cd_obj, quy_cach: dict | None) -> str | None:
        """Câu diễn giải SỐ RA của bước ngoài dòng: `<công thức chữ> = [<thay số> = ]<kết quả> <đvị>`.

        Dùng ĐÚNG công thức + cách làm tròn (ceil) mà `tinh_nguoc_routing` dùng để chốt `so_luong_ra`
        nên số ở đây khớp pill. Danh mục đổi sau khi lưu thì câu này bám số MỚI (giống khối Vật tư);
        pill vẫn là số đã lưu — chênh thì `so_luong_ra_moi` lo phần cảnh báo.
        """
        if cd_obj is None:
            return None
        ct = (getattr(cd_obj, "cong_thuc_san_luong", None) or "").strip()
        if not ct:
            return None
        ctx = {**ngu_canh_lenh(quy_cach or {}), **KHUNG_LUA_MAC_DINH}
        try:
            gt = float(safe_eval(ct, dict(ctx)))
        except (ValueError, ZeroDivisionError):
            return None
        if gt <= 0:
            return None
        dv_ten = (self._don_vis().get((cd.don_vi_ra or "").strip().lower()) or {}).get("ten") \
            or cd.don_vi_ra
        kq = _so_vn(float(ceil(gt)))
        the_so = cong_thuc_the_so(ct, ctx)
        dau = "" if the_so == kq else f"{the_so} = "
        return f"{cong_thuc_chu(ct)} = {dau}{kq} {dv_ten}"

    def _cong_doan_dict(self, cd, dept_names: dict, may_names: dict,
                        quy_cach: dict | None = None, moi: dict | None = None,
                        khuon_map: dict | None = None, *, la_kcs: bool = False) -> dict:
        vao = _f(cd.so_luong_vao)
        may_cd = self._may_cua_buoc(cd)
        t = thoi_luong_buoc(cd, may_cd, self.sl_tinh_cua_buoc(cd, may_cd, quy_cach))
        kh = cd.khoan_json or {}
        cd_obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
        _tren_dg = tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, self._tram())
        # Bước NGOÀI dòng đổi VÀO←RA qua cầu Đơn vị & quy đổi; chưa khai cầu thì đây là câu lỗi cho
        # drawer bày (đỏ) + chặn phát hành. Bước trên dòng không dùng cầu này nên không xét.
        _loi_qd = None if _tren_dg else self._he_so_ngoai_dong(cd.don_vi_vao, cd.don_vi_ra)[1]
        # Diễn giải SỐ RA của bước NGOÀI dòng: công thức sản lượng của công đoạn, thay số theo ngữ
        # cảnh lệnh (cùng khuôn "chữ = thay số = kết quả" với khối Vật tư/thời gian). Bước trên dòng
        # giấy suy ngược theo chuỗi nên không có công thức riêng — caption node RA nói thay.
        _san_luong_dg = None if _tren_dg else self._san_luong_dien_giai(cd, cd_obj, quy_cach)
        return {
            "id": cd.id, "step_key": cd.step_key, "thu_tu": cd.thu_tu, "cong_doan_id": cd.cong_doan_id,
            "ten": cd.ten, "nhom": cd.nhom, "loai_buoc": cd.loai_buoc, "bat_buoc": bool(cd.bat_buoc),
            # KCS kiêm nhiệm — suy TỰ ĐỘNG (không còn khai tay): FE ẩn/hiện khối "Tiêu chí KCS bổ
            # sung" theo `la_kcs`, do caller (`detail_dict`) tính sẵn = bước cuối routing + tổ có
            # `is_kcs=true`. PHẢI truyền tay ở đây — output này là dict thủ công, KHÔNG chạy
            # `from_attributes`.
            "la_kcs": la_kcs, "kcs_tieu_chi_bo_sung_json": cd.kcs_tieu_chi_bo_sung_json,
            "department_id": cd.department_id,
            "department_ten": dept_names.get(cd.department_id),
            "may_id": cd.may_id, "may_ten": may_names.get(cd.may_id),
            # Hai cờ dụng cụ đọc từ danh mục Công đoạn (KHÔNG suy từ tên bước — tên là chữ người
            # dùng gõ, đặt "Die-cut" hay "Ép kim" đều được). Chúng quyết định bước này có hỏi khuôn
            # hay không, và `tooling_type` còn là chiều lọc thứ hai của ô chọn dao.
            "requires_tooling": bool(getattr(cd_obj, "requires_tooling", False)),
            "tooling_type": getattr(cd_obj, "tooling_type", None),
            # Con dao của bước + thông tin bày cho thợ. Nạp theo LÔ ở `_khuon_map`, không tra ở đây.
            "khuon_be_id": cd.khuon_be_id,
            **(khuon_map or {}).get(cd.khuon_be_id, {}),
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
            # Câu lỗi khi bước ngoài dòng thiếu cầu quy đổi giữa hai đơn vị (None = không có lỗi).
            "loi_quy_doi": _loi_qd,
            # Diễn giải công thức SỐ RA (bước ngoài dòng) — None với bước trên dòng giấy.
            "san_luong_dien_giai": _san_luong_dg,
            "he_so_quy_doi": _f(cd.he_so_quy_doi),
            "hao_hut": _f(cd.hao_hut), "hao_hut_pct": _f(cd.hao_hut_pct),
            # % thực tế suy từ số — KHÔNG lưu cột, tránh hai nguồn sự thật với `hao_hut`.
            "ty_le_hao_hut": round(_f(cd.hao_hut) / vao * 100, 2) if vao > 0 else 0.0,
            "so_luot_chay": cd.so_luot_chay, "so_nhan_cong": cd.so_nhan_cong,
            "so_nhan_cong_toi_thieu": cd.so_nhan_cong_toi_thieu,
            "so_nhan_cong_tieu_chuan": cd.so_nhan_cong_tieu_chuan,
            "so_nhan_cong_toi_da": cd.so_nhan_cong_toi_da,
            # Chuẩn bị TRẢ RA LÀ SỐ KẾ THỪA TỪ MÁY (`t`), không phải cột `cd.setup_phut` đã dormant
            # — nếu trả cột cũ thì UI hiện một số mà engine lại tính bằng số khác.
            "setup_phut": t["dien_giai"]["setup_phut"],
            "phat_sinh_phut": _f(cd.phat_sinh_phut),
            "nang_suat": cd.nang_suat and _f(cd.nang_suat),
            "don_vi_nang_suat": cd.don_vi_nang_suat,
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
            # --- Khoán: phần GHIM (đầu việc đã chọn) + phần DẪN XUẤT (SL quy đổi · tiền · diễn giải)
            "khoan_rate_id": kh.get("rate_id"),
            "khoan_ten": kh.get("ten"),
            "khoan_don_vi": kh.get("don_vi"),
            "khoan_don_gia": _f(kh.get("don_gia")) or None,
            # Các đầu việc CHỌN ĐƯỢC cho bước này = mọi đơn giá của TỔ — gửi kèm để drawer khỏi
            # gọi thêm API.
            # Kèm `buoc` + `quy_cach` để mỗi đầu việc mang sẵn VẬT TƯ đã tính số cho ĐÚNG bước này —
            # drawer chọn công việc khoán là bung được ngay, khỏi gọi thêm API (nền BOM, mg 0191).
            "khoan_chon_duoc": self._dau_viec_option_dicts(
                cd_obj, cd.department_id, buoc=cd, quy_cach=quy_cach),
            "phu_thuoc_step_keys": [
                p.step_key for edge in cd.phu_thuoc
                if (p := self.db.get(LsxCongDoan, edge.buoc_truoc_id)) is not None
            ],
            "vat_tus": [
                {"id": v.id, "vat_tu_id": v.vat_tu_id,
                 "vat_tu_ma": v.vat_tu_ma_snapshot, "vat_tu_ten": v.vat_tu_ten_snapshot,
                 "don_vi": v.don_vi_snapshot, "so_luong": _f(v.so_luong),
                 "tu_dong": bool(v.tu_dong)}
                for v in cd.vat_tus
            ],
            # Lượng tính sẵn cho MỌI vật tư — drawer chọn món nào là điền được ngay, khỏi gõ tay.
            "vat_tu_goi_y": self._goi_y_luong_vat_tu(cd, quy_cach),
            **self._khoan_derived(cd, quy_cach),
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

    def _dau_viec_cua_buoc(self, cd) -> list:
        obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
        return self._dau_viec_cua_cong_doan(obj, cd.department_id)

    def list_rows(self, **kw) -> tuple[list[dict], int]:
        """`(dòng của TRANG này, TỔNG số dòng khớp lọc)`. Nhận thêm `page`/`size` xuống repo."""
        rows, total = self.repo.list(**kw)
        order_ids = {r.order_id for r in rows}
        orders = {
            o.id: o for o in self.db.execute(select(Order).where(Order.id.in_(order_ids))).scalars()
        } if order_ids else {}
        # Nhãn nhóm (vd "Catalogue A4 - 32 trang") — ĐỌC SỐNG từ dòng đơn: lệnh "Bìa" đứng một
        # mình thì không ai biết nó thuộc cuốn nào. `order_line_id` là FK THẬT, ổn định (khác
        # `phieu_thanh_phan_id` bị tái sinh mỗi lần lưu PTG) nên đọc sống an toàn, khỏi thêm cột.
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
        return [
            {"lsx_id": item.id, "lsx_ma": item.ma, "nhom": groups.get(item.order_line_id),
             "step_key": step.step_key, "ten_buoc": step.ten, "thu_tu": step.thu_tu}
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
            qc = lsx.quy_cach_json or {}
            out: list[dict] = []
            for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu):
                cd_obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
                tren = tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram)
                out.append({
                    "step_key": cd.step_key,
                    "so_luong_vao": _f(cd.so_luong_vao),
                    "so_luong_ra": _f(cd.so_luong_ra),
                    "don_vi_vao": cd.don_vi_vao,
                    "don_vi_ra": cd.don_vi_ra,
                    "he_so_quy_doi": _f(cd.he_so_quy_doi),
                    "hao_hut": _f(cd.hao_hut),
                    "hao_hut_pct": _f(cd.hao_hut_pct),
                    "tren_dong_giay": tren,
                    # Bước ngoài dòng giấy: câu lỗi cầu quy đổi + diễn giải công thức SỐ RA —
                    # giống hệt `_cong_doan_dict` để pill và caption khớp lúc Lưu.
                    "loi_quy_doi": None if tren else self._he_so_ngoai_dong(
                        cd.don_vi_vao, cd.don_vi_ra)[1],
                    "san_luong_dien_giai": None if tren else self._san_luong_dien_giai(
                        cd, cd_obj, qc),
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
        # Đổi SL đặt / quy cách là đổi luôn số vật tư cần — chặn khi đang giữ chỗ, cùng luật với
        # routing (`replace_routing`) và xoá lệnh (`xoa`). Field khác (tên, ghi chú, người phụ
        # trách...) không đụng vật tư nên KHÔNG chặn.
        if ("so_luong_dat" in changed or data.get("quy_cach")):
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
    _ROUTING_FIELD_THUAN = (
        "may_id", "khuon_be_id", "bat_buoc", "so_luot_chay",
        # Ba mốc nhân lực: kế thừa từ định mức là MẶC ĐỊNH, người kế hoạch sửa được tại bước.
        "so_nhan_cong", "so_nhan_cong_toi_thieu", "so_nhan_cong_tieu_chuan",
        "so_nhan_cong_toi_da", "phat_sinh_phut",
        # Chờ kỹ thuật: kế thừa từ danh mục Công đoạn là MẶC ĐỊNH, sửa đè tại bước (mục B).
        "nha_cung_cap", "sl_gui", "ngay_gui_dk", "van_chuyen_ngay", "gia_cong_ngay",
        "ngay_nhan_dk", "hao_hut_cho_phep", "don_gia_gia_cong", "yeu_cau_ky_thuat",
        "ghi_chu",
        # KCS kiêm nhiệm (mg 0250, Task 3): tiêu chí BỔ SUNG riêng của lệnh này (không sửa được
        # checklist danh mục ở đây). KHÔNG vào `_ROUTING_FIELD_NULLABLE` — gửi `[]` để xoá sạch đã
        # đủ, không cần gửi `null`.
        "kcs_tieu_chi_bo_sung_json",
    )
    _ROUTING_FIELD_NULLABLE = {
        "may_id", "khuon_be_id", "chay_phut", "nha_cung_cap", "ngay_gui_dk", "ngay_nhan_dk",
        "ghi_chu",
    }

    def _chan_dang_giu_cho(self, lsx: Lsx) -> None:
        """Lệnh đang giữ chỗ vật tư → không đổi số lượng/quy cách/routing, không xoá.

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
                "số lượng, quy cách, routing hoặc xoá lệnh."
            )

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
        # Bước có đầu việc đã GHIM nhưng nay mồ côi (không còn thuộc công đoạn ∩ tổ) → gỡ tại đây rồi
        # gom về đây để BÁO LƯU Ý sau khi lưu, thay vì chặn cứng cả lệnh. Xem khối "piece_rate_id".
        # Treo lên chính service (per-request) để router đọc; KHÔNG đính lên object ORM vì identity-map
        # trả cùng instance trong một session ⇒ lần đọc sau sẽ dính lưu ý cũ.
        bo_dau_viec: list[dict] = []
        self.bo_dau_viec_lan_luu = bo_dau_viec
        for i, r in enumerate(rows_in):
            d = r.model_dump(exclude_unset=True)
            payloads.append(d)
            cd_id = d.get("cong_doan_id")
            ten = d.get("ten")
            nhom = d.get("nhom")
            dept = d.get("department_id")
            cd_obj = self.db.get(CongDoan, cd_id) if cd_id else None
            if cd_id and (not ten or nhom is None or dept is None):
                if cd_obj is not None:
                    ten = ten or cd_obj.ten
                    nhom = nhom if nhom is not None else cd_obj.nhom
                    dept = dept if dept is not None else cd_obj.department_id
            # Đơn vị + số lượng KHÔNG nhận từ client: đơn vị kế thừa từ danh mục công đoạn, số
            # lượng là dẫn xuất của chuỗi ngược. `_ap_chuoi_nguoc` ở cuối hàm ghi cả bốn.
            key = (d.get("step_key") or "").strip()
            row = old_by_key.get(key) if key else None
            old_cd_id = row.cong_doan_id if row is not None else None
            old_dept_id = row.department_id if row is not None else None
            old_may_id = row.may_id if row is not None else None
            old_loai = row.loai_buoc if row is not None else None
            if row is None:
                row = LsxCongDoan(thu_tu=i, **({"step_key": key} if key else {}))
            row.cong_doan_id = cd_id
            row.ten = ten or "Công đoạn"
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
            # Bước TỔ làm bằng tay theo tổ, KHÔNG chiếm máy. Gỡ máy ở SERVER chứ không chỉ ẩn ô
            # trên form: máy còn dính lại thì bước vẫn chiếm một lane Gantt của máy đó.
            if row.loai_buoc == LB_TO:
                row.may_id = None
            source_changed = (
                row.id is None or old_cd_id != cd_id or old_dept_id != dept
                or old_may_id != row.may_id or old_loai != row.loai_buoc
            )
            # Kế thừa định mức là MẶC ĐỊNH, không read-only: ô nào người kế hoạch vừa gõ (có mặt
            # trong payload) thì giữ nguyên số của họ, chỉ ô KHÔNG gửi mới bị kéo lại theo định mức.
            def _ke_thua(field: str, gia_tri, _d=d, _row=row) -> None:
                if field not in _d:
                    setattr(_row, field, gia_tri)

            if row.loai_buoc == LB_MAY and source_changed:
                may = self.db.get(MayThietBi, row.may_id) if row.may_id else None
                # Bước MÁY: tốc độ đọc SỐNG từ máy lúc tính thời lượng, không chép lên bước nữa.
                row.nang_suat = row.don_vi_nang_suat = None
                # Nhân lực của bước máy do khối "BƯỚC MÁY NGHE MÁY" cuối vòng lặp chốt — ở đây
                # không đụng vào nữa, để chỉ có MỘT chỗ quyết kíp.
                # ĐỔI MÁY ⇒ TÍNH LẠI chờ kỹ thuật (chủ chốt 10/08/2026). Kéo lệnh từ máy cán màng
                # sang máy UV mà chờ vẫn 2 tiếng là vô lý. Đi qua `_ke_thua` nên số người kế hoạch
                # vừa gõ trong CÙNG lần lưu vẫn thắng — kế thừa là mặc định, không phải read-only.
                row.khoan_json = None
            elif row.loai_buoc == LB_THUE_NGOAI and source_changed:
                row.nang_suat = row.don_vi_nang_suat = None
                _ke_thua("so_nhan_cong_toi_da", None)
                _ke_thua("so_nhan_cong_toi_thieu", None)
                row.khoan_json = None
            # Đầu việc khoán: client gửi `piece_rate_id` thì GHIM ảnh chụp theo id đó (0/None = bỏ
            # chọn); không gửi thì điền mặc định như lúc bung lệnh — kế thừa là MẶC ĐỊNH, không
            # read-only, nên người sửa routing không mất đầu việc đã có.
            if "piece_rate_id" in d:
                rid = d.get("piece_rate_id") or 0
                rate = next((x for x in self._piece_rates() if x.id == rid), None) if rid else None
                allowed = self._dau_viec_cua_cong_doan(cd_obj, dept)
                if rate is not None and rate.id not in {x.id for x in allowed}:
                    # Đầu việc đã GHIM trên bước nay không còn thuộc (công đoạn ∩ tổ) — thường vì
                    # danh mục đổi dưới chân lệnh (đổi tổ phụ trách · gỡ định mức đầu việc · ngừng
                    # dùng đầu việc/công đoạn). KHÔNG chặn cả lệnh (một đầu việc mồ côi từng khoá
                    # cứng nút Lưu kể cả khi người ta chỉ sửa chỗ khác): tự GỠ đầu việc mồ côi rồi
                    # báo LƯU Ý đích danh bước để mở lại chọn đầu việc phù hợp — cùng lối "giữ được
                    # thứ đã có" như khối vật tư ngừng-dùng bên dưới.
                    bo_dau_viec.append(
                        {"vi_tri": i + 1, "ten": row.ten, "dau_viec": rate.ten})
                    rate = None
                row.khoan_json = khoan_snapshot(rate) if rate is not None else None
                if rate is not None:
                    dm = next((x for x in (getattr(cd_obj, "dau_viec_dinh_muc", None) or [])
                               if x.piece_rate_id == rate.id), None)
                    if dm is not None:
                        row.khoan_json.update(_dinh_muc_snapshot(dm))
                        # ĐỊNH MỨC NHÂN LỰC của đầu việc là định mức TỔ LÀM TAY — "xúm mấy người
                        # cho nhanh". Bước MÁY thì số người là KÍP ĐỨNG MÁY, khai ở danh mục Máy.
                        # Trộn hai thứ vào nhau thì bước chạy Yawa (máy khai 2) hiện 3 người theo
                        # bảng khoán, mà năng suất-người-giờ cũng không ai chia (bước máy chia theo
                        # tốc độ máy). TIỀN khoán vẫn ghim bình thường ở `khoan_json`.
                        if row.loai_buoc == LB_TO:
                            row.nang_suat = _f(dm.nang_suat_nguoi_gio)
                            row.don_vi_nang_suat = row.khoan_json.get("don_vi")
                            _ke_thua("so_nhan_cong_toi_thieu",
                                     int(getattr(dm, "so_nguoi_toi_thieu", 1) or 1))
                            _ke_thua("so_nhan_cong_tieu_chuan", int(dm.so_nguoi_tieu_chuan))
                            _ke_thua("so_nhan_cong_toi_da", int(dm.so_nguoi_toi_da))
                            _ke_thua("so_nhan_cong", int(dm.so_nguoi_tieu_chuan))
                elif row.loai_buoc == LB_TO:
                    row.nang_suat = row.don_vi_nang_suat = None
                    _ke_thua("so_nhan_cong_tieu_chuan", 1)
                    _ke_thua("so_nhan_cong_toi_da", None)
                    _ke_thua("so_nhan_cong_toi_thieu", None)
            elif source_changed:
                row.khoan_json = self._khoan_mac_dinh(dept, cd_obj)
                if row.loai_buoc == LB_TO:
                    snap = row.khoan_json or {}
                    row.nang_suat = _f(snap.get("nang_suat_nguoi_gio")) or None
                    row.don_vi_nang_suat = snap.get("don_vi")
                    _ke_thua("so_nhan_cong_toi_thieu",
                             int(snap["so_nguoi_toi_thieu"]) if snap.get("so_nguoi_toi_thieu") else None)
                    _ke_thua("so_nhan_cong_tieu_chuan", int(snap.get("so_nguoi_tieu_chuan") or 1))
                    _ke_thua("so_nhan_cong_toi_da",
                             int(snap["so_nguoi_toi_da"]) if snap.get("so_nguoi_toi_da") else None)
                    _ke_thua("so_nhan_cong", row.so_nhan_cong_tieu_chuan)
            # BƯỚC MÁY NGHE MÁY (chốt 20/08/2026). Kíp tiêu chuẩn = số người vận hành khai ở danh
            # mục Máy, ghi đè MỖI LẦN LƯU chứ không qua `_ke_thua`: đây là thông số của MÁY, drawer
            # chỉ hiện chứ không cho sửa tại bước — muốn đổi thì đổi ở danh mục để mọi lệnh cùng ăn.
            # Nhờ ghi đè, bước cũ lỡ dính số 3 của bảng khoán tự về đúng ngay lần lưu kế tiếp.
            # Ba mốc tối thiểu/tối đa là chuyện của bước TỔ, bước máy để trống.
            if row.loai_buoc == LB_MAY:
                may_gan = self.db.get(MayThietBi, row.may_id) if row.may_id else None
                kip_may = max(int(ceil(_f(may_gan.so_nhan_cong))), 1) if may_gan is not None else 1
                row.so_nhan_cong_tieu_chuan = kip_may
                row.so_nhan_cong_toi_thieu = None
                row.so_nhan_cong_toi_da = None
                _ke_thua("so_nhan_cong", kip_may)
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
        external = [e for e in self.repo.phu_thuoc_toi_buoc(removed_ids)
                    if e.buoc_sau_id not in removed_ids]
        if external:
            dep = self.db.get(LsxCongDoan, external[0].buoc_sau_id)
            dep_lsx = self.db.get(Lsx, dep.lsx_id) if dep else None
            raise LsxConflict(
                f"Không thể xóa bước đang được {dep_lsx.ma if dep_lsx else 'LSX khác'} / "
                f"{dep.ten if dep else 'công đoạn khác'} phụ thuộc"
            )
        self.repo.sync_cong_doans(lsx, rows)

        # Vật tư là khai báo riêng của bước, chọn từ danh mục; không đọc PTG.
        for row, d in zip(rows, payloads):
            if "vat_tus" not in d:
                continue
            vat_tus = d.get("vat_tus") or []
            ids = [int(v.get("vat_tu_id") or 0) for v in vat_tus]
            if len(ids) != len(set(ids)):
                raise LsxValidationError("Một vật tư không được chọn trùng trong cùng công đoạn")
            # Vật tư ĐÃ nằm trên bước từ trước — giữ lại được kể cả khi danh mục đã ngừng nó.
            # Chặn cả hai kiểu như trước thì một lệnh cũ có vật tư ngừng dùng là KHÔNG LƯU LẠI
            # ĐƯỢC routing nữa, kể cả khi người ta chỉ sửa cái khác.
            dang_co = {int(v.vat_tu_id) for v in row.vat_tus if v.vat_tu_id}
            mats = {
                v.id: v for v in self.db.execute(
                    select(VatTuInAn).where(VatTuInAn.id.in_(ids))
                ).scalars()
            } if ids else {}
            if len(mats) != len(ids):
                raise LsxValidationError("Vật tư không tồn tại")
            ngung_moi = [mats[i] for i in ids if not mats[i].active and i not in dang_co]
            if ngung_moi:
                raise LsxValidationError(
                    f"Vật tư “{ngung_moi[0].ten}” đã ngừng dùng — chọn vật tư khác")
            row.vat_tus.clear()
            # FLUSH giữa xoá và thêm: bảng có UNIQUE (lsx_cong_doan_id, vat_tu_id), mà lưu lại
            # bước với ĐÚNG vật tư cũ là xoá rồi thêm lại chính cặp đó. Không ép DELETE chạy
            # trước thì SQLAlchemy gộp một lượt và INSERT đụng hàng chưa kịp xoá → 500 ngay khi
            # bấm Lưu lần thứ hai mà không đổi gì.
            self.db.flush()
            for pos, item in enumerate(vat_tus):
                mat = mats[int(item["vat_tu_id"])]
                row.vat_tus.append(LsxCongDoanVatTu(
                    # `or ""`: đơn vị gốc có thể CHƯA KHAI (nullable từ 2026-08-08) còn cột
                    # snapshot NOT NULL — không chặn thì IntegrityError 500.
                    vat_tu_id=mat.id, vat_tu_ma_snapshot=mat.ma,
                    vat_tu_ten_snapshot=mat.ten, don_vi_snapshot=mat.don_vi_gia or "",
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
