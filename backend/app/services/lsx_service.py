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
from ..models.khuon_be import KhuonBe
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
    NS_CAI_GIO,
    NS_KEM_GIO,
    NS_TO_GIO,
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
from ..models.order import STATUS_ORDERED, Order, OrderLine
from ..models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia
from ..models.quotation import QuoteVersion
from ..models.user import User
from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn
from ..services.bu_hao_engine import hao_buoc
from ..models.don_vi_do import TRAM_CAI, TRAM_CON, TRAM_TAY, TRAM_TO, TRAM_TO_NGUYEN
from ..services.dong_giay import (
    ban_do_tram, chieu_hop_le, dich_chuoi, don_vi_chuoi, ma_cua_tram, tram_cua, tren_dong_giay,
)
from ..models.don_vi_do import DonViDo
from ..services.bien_cong_thuc import ngu_canh_lenh, quy_cach_bien
from ..services.don_vi_do_service import cong_thuc_chu
from ..services.piece_work_service import dau_viec_khop, khoan_snapshot
from ..services.quy_doi_service import bien_trong, doi_theo_quy_cach, don_vi_map, tien_khoan
from ..services.thanh_phan_engine import safe_eval
from ..services.thanh_phan_engine import cau_to_sang_cai, chua_theo_chieu, compute_phieu
from ..services.tinh_gia_service import _bu_hao_to_dict, _resolve_thanh_phan

# Công đoạn sau xén → đếm bằng CON (thành phẩm); còn lại đếm bằng TỜ. Heuristic theo tên để điền
# MẶC ĐỊNH cho kế hoạch, không phải luật — mọi dòng sửa được.

# Checklist "thiếu khuôn bế" ĐÃ BỎ khỏi file này (11/08/2026) cùng ô gán khuôn ở màn Kế hoạch.
# Luật ĐỌC CỜ (`requires_tooling` / `tooling_type` khai ở danh mục Công đoạn) vẫn sống ở bảng cân
# đối vật tư — xem `KeHoachVatTuService._cong_doan_can_dung_cu`. Công đoạn là danh mục người dùng
# tự khai, đặt tên gì cũng được, nên KHÔNG suy bất cứ thứ gì từ tên bước.

# Trường KHÔNG chép sang quy cách lệnh sản xuất: toàn bộ là TIỀN (lệnh xuống xưởng không mang
# giá vốn) + số lượng (đã có `so_luong_dat` của ĐƠN, chép lại chỉ gây mâu thuẫn).
_QC_BO_QUA = frozenset({
    "don_gia_giay", "don_gia_don_vi", "don_gia_cong_in", "che_ban_don_gia",
    "cong_thuc_gia", "gia_von_tp", "so_luong",
})
# Đơn vị năng suất luôn ĐI THEO đơn vị đầu vào của bước (công thức là `so_luong_vao / nang_suat`),
# nên suy ra chứ không lưu cột riêng — lưu riêng là mở đường cho hai thứ lệch nhau.
# `tay` đo bằng TỜ/GIỜ: một tay đúng bằng một tờ in, máy gấp đếm tờ chạy qua. Thiếu dòng này thì
# bước gấp/bắt tay không có đơn vị năng suất, ô nhập bỏ trống nhãn.
_DV_VAO_SANG_NS = {DV_TO_NGUYEN: NS_TO_GIO, DV_TO: NS_TO_GIO, DV_TAY: NS_TO_GIO,
                   DV_CAI: NS_CAI_GIO, DV_KEM: NS_KEM_GIO}


def dv_nang_suat_theo_khoan(don_vi_khoan: str | None, don_vi_vao: str | None,
                            tra_ma=None) -> str | None:
    """Đơn vị của con số NĂNG SUẤT ở bước Tổ — KHOÁ theo đơn giá khoán (chủ chốt 10/08/2026).

    Trước đây có ô cho chọn trong 9 mã tốc độ. Chủ: *"đơn vị này chỉ được theo đơn vị theo lương
    khoán và không được đổi"* — cùng một đầu việc thì tính tiền và đếm năng suất bằng cùng một thứ,
    không có lý do để hai nơi lệch nhau, và cũng không nên bắt người khai chọn lại cái đã khai.

    Chưa gắn đơn giá khoán (hoặc tên đơn vị không có trong danh mục) → lùi về đơn vị VÀO của công
    đoạn như cũ. KHÔNG tự chế mã từ tên: mã lạ thì nơi khác đọc vào lại im lặng hiểu sai.

    ⚠️ ĐÂY LÀ NHÃN, KHÔNG VÀO CÔNG THỨC. Thời lượng vẫn là `SL_vào × 60 ÷ năng_suất × số_lượt`,
    trong đó `SL_vào` tính bằng ĐƠN VỊ VÀO của bước — chủ chốt 05/08: *"công thức thời lượng chỉ
    quan tâm CON SỐ"*, và chủ chốt 10/08 giữ nguyên công thức. Nghĩa là đầu việc khoán theo `cuốn`
    gắn vào công đoạn vào bằng `tờ` sẽ hiện "cuốn/h" trong khi máy chia số TỜ cho con số đó. Biết
    và chấp nhận; muốn hết lệch thì phải làm bước QUY ĐỔI (`so_luong_vao` → đơn vị khoán rồi mới
    chia), đã bàn và HOÃN. Đừng "sửa" bằng cách đổi nhãn về đơn vị vào — đó là quay lại cái vừa bỏ.
    """
    ten = (don_vi_khoan or "").strip()
    if ten and tra_ma is not None:
        ma = tra_ma(ten)
        if ma:
            return f"{ma}_gio"
    return _DV_VAO_SANG_NS.get(don_vi_vao) if don_vi_vao else None


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


def _nang_suat_buoc(may, cd_obj, dv_vao: str | None, *, dv_ra: str | None = None,
                    tram: dict | None = None) -> tuple[float | None, str | None]:
    """Năng suất + đơn vị của 1 bước, lấy từ MÁY được gán.

    Luật: đơn vị tốc độ của máy phải KHỚP thứ mà bước đếm. Máy in khai `tờ/giờ` gắn vào bước đếm
    tờ thì lấy; khai đơn vị khác thì bỏ qua — dùng nhầm số đó là sai thầm lặng.

    Bước CHẾ BẢN không nằm trên dòng giấy nhưng vẫn đếm KẼM, nên nó khớp với máy ghi kẽm CTP khai
    `kẽm/giờ`. Trước đây luật bắt cứng `dv_vao == to` nên bước chế bản KHÔNG BAO GIỜ lấy được tốc
    độ: ghi 4 kẽm hay 40 kẽm cũng ra thời lượng bằng đúng thời gian chuẩn bị.

    Mã tốc độ mong đợi suy theo LUẬT CHUNG `<mã đơn vị>_gio`; `_DV_VAO_SANG_NS` chỉ còn là bảng
    NGOẠI LỆ cho mấy mã đo bằng thứ khác (một tay sách chạy máy đúng bằng một tờ). Bỏ luật chung là
    quay lại lỗi 11/08/2026: bước ghi kẽm khai `bai → kem` cho tử tế thì `bai` không có trong bảng
    5 mã, máy CTP hết khớp và thời lượng tụt về mỗi thời gian chuẩn bị — dùng đúng tính năng mới
    lại làm hỏng số.

    Bước NGOÀI dòng giấy nhận và nhả CÙNG một con số (`vao = ra`), nên máy đo bằng đầu nào cũng
    đúng — vì thế chấp nhận cả đơn vị RA. Bước TRÊN dòng giấy thì KHÔNG: vào 250 tờ ra 5.000 con,
    lấy nhầm `con/giờ` chia cho số tờ là sai 20 lần.
    """
    if may is None or _f(may.toc_do) <= 0:
        return None, None

    def _ma(dv: str | None) -> str | None:
        return (_DV_VAO_SANG_NS.get(dv) or f"{dv}_gio") if dv else None

    ngoai_dong = tram is not None and not tren_dong_giay(dv_vao, dv_ra, tram)
    mong_doi = [_ma(dv_vao)] + ([_ma(dv_ra)] if ngoai_dong else [])
    if not dv_vao:      # chưa khai đơn vị → lùi về luật cũ theo nhóm công đoạn
        mong_doi = [NS_KEM_GIO] if getattr(cd_obj, "nhom", None) == "prepress" else []
    for m in mong_doi:
        if m and may.don_vi_toc_do == m:
            return _f(may.toc_do), m
    return None, None
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


def thoi_luong_buoc(cd, may=None) -> dict:
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

        thời lượng = thời gian khác + SL vào ÷ (năng suất người × số người tính) × 60

    Ba mức năng suất (tối thiểu · trung bình · tối đa) khai ở ĐỊNH MỨC ĐẦU VIỆC và được ghim vào
    bước lúc chọn đầu việc (`khoan_json`). Năng suất CAO ⇒ thời lượng NHỎ. Đơn vị năng suất là
    NHÃN KHAI BÁO — không quy đổi, không kiểm khớp với đơn vị bước (bước quy đổi làm sau).
    Bước THUÊ NGOÀI đi theo ngày gửi/nhận, thời lượng máy = 0.

    ĐÃ GỠ khỏi công thức (cột còn trong DB, dormant): `setup_phut` · `chay_phut` (nhập đè) ·
    `di_chuyen_phut` · `ve_sinh_phut`.

    **CHỜ KỸ THUẬT ĐÃ GỠ 13/08/2026** (`cho_phut` — mực khô · keo đông · màng nguội) nên
    `tong_phut == chiem_may_phut`. Hai khoá vẫn tách vì bàn xếp lịch lấy HIỆU của chúng làm độ trễ
    giữa hai bước; hiệu = 0 ⇒ bước sau bắt đầu ngay khi máy nhả tờ.
    """
    canh_bao: list[str] = []
    loai = getattr(cd, "loai_buoc", LB_MAY) or LB_MAY
    vao = _f(cd.so_luong_vao)
    luot = max(int(getattr(cd, "so_luot_chay", 1) or 1), 1)
    khac = _f(getattr(cd, "phat_sinh_phut", 0))
    nguoi_ke_hoach = max(int(getattr(cd, "so_nhan_cong", 1) or 1), 1)
    nguoi_toi_da_raw = getattr(cd, "so_nhan_cong_toi_da", None)
    nguoi_toi_da = max(int(nguoi_toi_da_raw or nguoi_ke_hoach), 1)
    nguoi_tinh: int | None = None

    khoan = khoan_chuan_bi_cua_may(may) if loai == LB_MAY else []
    setup = _f(getattr(may, "makeready_time_default", None)) if (loai == LB_MAY and may) else 0.0
    # KHÔNG kiểm đơn vị tốc độ (chủ chốt 2026-08-05): cứ lấy SL đầu vào chia tốc độ máy. Trước đây
    # ở đây có guard "lệch đơn vị ⇒ chạy = 0" — nó CHẶN đúng những bước đã gán máy đàng hoàng chỉ
    # vì máy khai nhãn đơn vị khác, và đó là thứ tôi tự thêm chứ không phải yêu cầu. Nhãn đơn vị là
    # việc của màn Máy; công thức thời lượng chỉ quan tâm CON SỐ.
    may_dung_duoc = may if loai == LB_MAY else None
    ns = _f(getattr(may_dung_duoc, "toc_do", None)) if loai == LB_MAY else _f(cd.nang_suat)
    nang_suat_hieu_dung = ns

    def _chay(toc_do: float) -> float:
        return (vao * 60.0 / toc_do * luot) if toc_do > 0 and vao > 0 else 0.0

    if loai == LB_TO:
        nguoi_tinh = min(nguoi_ke_hoach, nguoi_toi_da)
        if nguoi_ke_hoach > nguoi_toi_da:
            canh_bao.append(
                "Số người kế hoạch vượt mức tối đa hiệu quả; thời gian chỉ tính theo mức tối đa."
            )
        # Dải năng suất ghim theo đầu việc. Chưa khai mức nào thì mức đó rơi về trung bình — râu
        # co về một điểm, y như máy chưa khai `toc_do_min`/`toc_do_max`.
        kh_dai = getattr(cd, "khoan_json", None) or {}
        ns_thap = _f(kh_dai.get("nang_suat_nguoi_gio_min")) or ns
        ns_cao = _f(kh_dai.get("nang_suat_nguoi_gio_max")) or ns
        nang_suat_hieu_dung = ns * nguoi_tinh

        def _chay_to(muc: float) -> float:
            hieu_dung = muc * nguoi_tinh
            return (vao / hieu_dung * 60.0) if hieu_dung > 0 and vao > 0 else 0.0

        chay = _chay_to(ns)
        chay_nhanh = _chay_to(ns_cao)   # năng suất CAO ⇒ chạy nhanh ⇒ thời lượng NHỎ nhất
        chay_cham = _chay_to(ns_thap)
        phuong_phap = "to" if nang_suat_hieu_dung > 0 else "thieu_nang_suat"
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
    if phuong_phap == "thieu_nang_suat":
        # Bước Tổ không có máy — chỉ về đúng chỗ phải đi khai, không thì người dùng đi tìm ô tốc
        # độ máy cho một bước dán tay.
        canh_bao.append(
            "Đầu việc chưa khai năng suất (hoặc bước chưa chọn đầu việc khoán) nên không tính "
            "được thời gian chạy."
            if loai == LB_TO else
            "Máy đang gán chưa khai tốc độ (hoặc bước chưa gán máy) nên không tính được thời gian chạy."
        )

    chiem_may = khac + setup + chay
    # 🔴 CHỜ KỸ THUẬT GỠ 13/08/2026 — `tong_phut` nay bằng đúng `chiem_may_phut`. Giữ hai khoá
    # riêng vì bàn xếp lịch đọc HIỆU của chúng làm độ trễ giữa hai bước (`lag`): hiệu = 0 nghĩa là
    # bước sau bắt đầu ngay khi máy nhả tờ. Muốn dựng lại độ trễ thì cộng vào `tong` ở đây, đừng
    # cộng vào `chiem_may` — chiếm máy là thứ ăn năng lực máy, chờ thì không.
    tong = chiem_may
    co_dai = round(chay_nhanh, 2) != round(chay_cham, 2)
    dien_giai = {
        "phuong_phap": phuong_phap,
        "so_luong_vao": round(vao, 2),
        "don_vi_vao": getattr(cd, "don_vi_vao", None),
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
        return [
            _bu_hao_to_dict(b)
            for b in self.db.execute(select(BuHao).where(BuHao.active.is_(True))).scalars()
        ]

    # --- Khoán theo đầu việc (bảng giá của tổ) + đơn vị quy đổi ---------------
    # Cache theo INSTANCE service (1 request = 1 instance): bung lệnh gọi mỗi bước một lần, mà hai
    # bảng này nhỏ và không đổi trong một request — query lại từng bước là N+1 vô ích.

    def _piece_rates(self) -> list:
        if self._rates_cache is None:
            from ..models.piece_work import PieceRate

            self._rates_cache = list(
                self.db.execute(select(PieceRate).where(PieceRate.is_active.is_(True))).scalars()
            )
        return self._rates_cache

    def _don_vis(self) -> dict:
        if self._dv_cache is None:
            from ..models.don_vi_do import DonViDo

            rows = self.db.execute(select(DonViDo).where(DonViDo.active.is_(True))).scalars()
            self._dv_cache = don_vi_map(list(rows))
        return self._dv_cache

    def _ma_don_vi(self, ten: str) -> str | None:
        """TÊN đơn vị (`"cuốn"`) → MÃ danh mục (`"cuon"`). Nhận cả khi đã là mã sẵn.

        `piece_rates.unit` lưu TÊN vì ô đó chọn từ danh mục theo tên; nhãn năng suất lưu MÃ theo
        khuôn `<mã>_gio`. Cầu nối để không nơi nào phải tự đoán.
        """
        if self._ma_dv_cache is None:
            from ..models.don_vi_do import DonViDo

            self._ma_dv_cache = {}
            for r in self.db.execute(select(DonViDo).where(DonViDo.active.is_(True))).scalars():
                self._ma_dv_cache[(r.ten or "").strip().lower()] = r.ma
                self._ma_dv_cache[(r.ma or "").strip().lower()] = r.ma
        return self._ma_dv_cache.get((ten or "").strip().lower())

    def _dv_ns(self, khoan: dict | None, don_vi_vao: str | None) -> str | None:
        """Nhãn đơn vị năng suất của bước — xem `dv_nang_suat_theo_khoan`."""
        return dv_nang_suat_theo_khoan(
            (khoan or {}).get("don_vi"), don_vi_vao, tra_ma=self._ma_don_vi
        )

    def _cap_quy_doi(self) -> list:
        """DÒNG cặp quy đổi — nguồn chân lý của mọi phép đổi (bảng `don_vi_quy_doi`).

        Giữ nguyên dòng chứ không dẹp sẵn thành đồ thị: dòng quy đổi động ("1 tờ = định lượng ×
        dài × rộng" kg) chỉ ra hệ số sau khi thay quy cách của chính bước đang tính.
        """
        if self._cap_cache is None:
            from ..repositories.don_vi_do_repo import DonViDoRepository

            self._cap_cache = DonViDoRepository(self.db).cap_rows()
        return self._cap_cache

    def _khoan_mac_dinh(self, department_id: int | None, cd_obj) -> dict | None:
        """Đầu việc khoán ĐIỀN SẴN cho một bước: khớp đúng 1 thì tự điền, nhiều thì để trống.

        Nhiều đầu việc khớp (bế tay / bế máy cùng công đoạn) là chuyện chỉ người biết → máy để
        trống + nhắc, KHÔNG chọn hộ. Tổ không ăn khoán thì danh sách rỗng, cũng ra None.

        🔴 GỠ 12/08/2026: nhánh ưu tiên cờ `is_default` khai ở danh mục. Cột đó cho khai một lần
        rồi chọn hộ mãi mãi, trong khi *bế tay hay bế máy* phụ thuộc HÀNG cụ thể chứ không phải
        công đoạn. Nay chỉ còn một luật: một đầu việc thì điền, hai trở lên thì để người quyết.
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
        định mức tuỳ quy cách của từng lệnh. Hai đường, theo thứ tự:

        1. **CÁCH ĐO của đơn vị** (`don_vi_do.cong_thuc`, mg 0192) — đường chính. Vật tư khai ĐVT là
           `m² tờ in` thì chạy thẳng công thức của đơn vị đó với quy cách lệnh. Không nối với đơn vị
           nào, không đi qua đồ thị, nên KHÔNG có gì để chọn nhầm.
        2. Đơn vị không có cách đo → lùi về quy đổi từ đơn vị của BƯỚC sang đơn vị vật tư
           (`doi_theo_quy_cach`, đúng cửa tiền khoán đang dùng). Giữ đường này cho vật tư đo bằng
           đơn vị thường (`cái`, `kg`) mà xưởng đã khai cặp sẵn.

        KHÔNG ĐOÁN: cả hai đường đều tịt thì bỏ dòng đó ra khỏi kết quả và trả câu lý do — thà người
        kế hoạch tự thêm còn hơn bung một con số sai trông như thật.

        Trả `([], [])` khi chưa đủ ngữ cảnh (gọi từ `dau_viec_options` lúc đổi tổ, chưa có bước).
        """
        vat_tus = list(getattr(dm, "vat_tus", None) or []) if dm is not None else []
        if not vat_tus or buoc is None:
            return [], []
        sl = _f(getattr(buoc, "so_luong_vao", 0))
        dv_buoc = getattr(buoc, "don_vi_vao", None)
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
        ctx = ngu_canh_lenh(quy_cach or {})
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
            so_luong, dien_giai, ly_do = self._luong_vat_tu(dvt, ctx, sl, dv_buoc, quy_cach)
            if so_luong is None:
                canh_bao.append(f"{mat.ten}: {ly_do}")
                continue
            ra.append({
                "vat_tu_id": mat.id, "ma": mat.ma, "ten": mat.ten, "don_vi": dvt,
                "so_luong": round(so_luong, 3), "dien_giai": dien_giai,
            })
        return ra, canh_bao

    def _cach_do(self) -> dict[str, str]:
        """`{mã đơn vị: công thức CÁCH ĐO}` — chỉ đơn vị nào đã khai. Nạp một lần cho cả request:
        `don_vi_map` không mang cột này, mà tra từng dòng là N+1 theo số vật tư của mọi bước."""
        if getattr(self, "_cach_do_cache", None) is None:
            self._cach_do_cache = {
                d.ma: (d.cong_thuc or "").strip()
                for d in self.db.execute(
                    select(DonViDo).where(DonViDo.cong_thuc.is_not(None))
                ).scalars()
                if (d.cong_thuc or "").strip()
            }
        return self._cach_do_cache

    def _luong_vat_tu(self, dvt: str, ctx: dict, sl: float, dv_buoc: str | None,
                      quy_cach: dict | None) -> tuple[float | None, str | None, str]:
        """Số lượng một vật tư đo bằng `dvt`. Trả `(số, diễn giải, lý do nếu tịt)`."""
        cach_do = self._cach_do().get(dvt.strip().lower(), "")
        if cach_do:
            try:
                gt = float(safe_eval(cach_do, dict(ctx)))
            except (ValueError, ZeroDivisionError) as e:
                return None, None, f"cách đo của {dvt} không chạy được ({e})."
            if gt <= 0:
                thieu = [b for b in bien_trong(cach_do) if _f(ctx.get(b)) <= 0]
                return None, None, (
                    f"cách đo của {dvt} ra 0 — thiếu {', '.join(thieu)}." if thieu
                    else f"cách đo của {dvt} ra 0.")
            return gt, f"{cong_thuc_chu(cach_do)} = {gt:g} {dvt}", ""
        # Không có cách đo → lùi về quy đổi từ đơn vị của bước.
        if not dv_buoc:
            return None, None, f"{dvt} chưa khai cách đo, và bước chưa có đơn vị để quy đổi."
        kq = doi_theo_quy_cach(sl, dv_buoc, dvt, quy_cach or {},
                               self._don_vis(), self._cap_quy_doi())
        if "gia_tri" not in kq:
            return None, None, (kq.get("ly_do") or f"chưa quy đổi được {dv_buoc} → {dvt}.")
        return float(kq["gia_tri"]), kq.get("dien_giai"), ""

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
                "ten": rate.name,
                "don_vi": rate.unit,
                "don_gia": _f(rate.unit_price),
            }
            if dm is not None:
                vt, cb = self._vat_tu_bung(dm, buoc, quy_cach)
                item.update({
                    **_dinh_muc_snapshot(dm),
                    # KHOÁ theo đơn giá khoán, người khai không đổi được — `dv_nang_suat_theo_khoan`.
                    "don_vi_nang_suat": self._dv_ns({"don_vi": rate.unit}, cd_obj.don_vi_vao),
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

    def _khoan_derived(self, cd, quy_cach: dict | None) -> dict:
        """Tiền khoán DỰ KIẾN của bước — tính LÚC ĐỌC, không lưu cột.

        SL lấy `so_luong_vao` (số thợ thật chạy qua tay, gồm cả tờ bù hao canh máy — thợ cán 241 tờ
        thì ăn 241 tờ), rồi ĐỔI thẳng sang đơn vị của đơn giá. Không nhân thêm hệ số ngầm nào:
        muốn trả theo lượt máy thì khai đơn giá theo đơn vị `lượt`, đừng giấu phép nhân trong code.
        """
        # Hợp đồng dict: LUÔN đủ 6 khoá (None khi chưa có gì) — caller `if kq["khoan_tien"]` chứ
        # không phải `if "khoan_tien" in kq`. Trả dict rỗng khi bước chưa chọn đầu việc là mời gọi
        # KeyError ở mọi chỗ đọc.
        trong = {"khoan_sl": None, "khoan_don_vi_sl": None, "khoan_tien": None,
                 "khoan_dien_giai": None, "khoan_thieu": [], "khoan_ly_do": None}
        kh = cd.khoan_json or {}
        if not kh.get("don_vi") or not kh.get("don_gia"):
            return trong
        sl = _f(cd.so_luong_vao)
        kq = tien_khoan(
            sl, cd.don_vi_vao, kh["don_vi"], _f(kh["don_gia"]), quy_cach or {},
            self._don_vis(), self._cap_quy_doi(),
        )
        if "tien" not in kq:
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

    def hang_cho(self) -> list[dict]:
        """Đơn Sale đã chuyển xuống SX mà CÒN dòng chưa lên lệnh."""
        orders = self.repo.orders_ban_giao()
        if not orders:
            return []
        line_ids = [ln.id for o in orders for ln in o.lines]
        da_co = self.repo.by_order_lines(line_ids)
        out: list[dict] = []
        for o in orders:
            so_dong = len(o.lines)
            so_co = sum(1 for ln in o.lines if ln.id in da_co)
            if so_dong and so_co >= so_dong:
                continue  # đã đủ lệnh → rời hàng chờ
            out.append({
                "order_id": o.id,
                "order_no": o.order_no,
                "customer_name": self._customer_name(o),
                "sale_name": self._user_name(o.sale_user_id),
                "delivery_committed_date": o.delivery_committed_date,
                "is_rush": bool(o.is_rush),
                "production_note": o.production_note,
                "san_xuat_released_at": o.san_xuat_released_at,
                "so_dong": so_dong,
                "so_dong_co_lsx": so_co,
            })
        return out

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
               routing: list[dict], khuon_be_id: int | None) -> list[str]:
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
        # "thiếu khuôn bế" ĐÃ BỎ khỏi checklist (chủ 11/08/2026): ô gán khuôn ở cấp lệnh đã gỡ
        # khỏi màn Kế hoạch, nên giữ điều kiện này thì mọi lệnh có bước bế mắc kẹt ở CHỜ BỔ SUNG
        # mà không ai gỡ được. Khuôn gắn với BƯỚC bế, không phải với cả lệnh.
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
                "bu_hao_to": (
                    int(round(float(comp.get("bu_hao_auto") or 0) + float(comp.get("bu_hao_tay") or 0)))
                    if tp is not None else None
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
                    order=order, tp=tp, quy_cach=calc["quy_cach"],
                    routing=calc["routing"], khuon_be_id=None,
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
        # Số lượng: bước NGOÀI dòng giấy (chế bản, đơn vị trống) đếm KẼM và đứng ngoài chuỗi ngược
        # nên phải điền ở đây. Bước trên dòng giấy để 0 — `_ap_chuoi_nguoc` ghi đè ngay sau khi
        # tạo; tự chế số ở đây chỉ tổ có hai công thức rồi lệch nhau.
        vao = ra = _f(comp.get("so_kem")) if nhom == "prepress" else 0.0

        nang_suat, dv_nang_suat = _nang_suat_buoc(
            may, cd_obj, dv_vao, dv_ra=dv_ra, tram=self._tram())

        khoan = self._khoan_mac_dinh(r.get("department_id"), cd_obj)
        kip = max(int(ceil(_f(may.so_nhan_cong))), 1) if may is not None else 1
        if loai_buoc == LB_TO and khoan:
            nang_suat = _f(khoan.get("nang_suat_nguoi_gio")) or nang_suat
            # KHOÁ theo đơn giá khoán — xem `dv_nang_suat_theo_khoan`.
            dv_nang_suat = self._dv_ns(khoan, dv_vao)
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
                khuon_be_id=None,
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
                # `bu_hao_to` = HAO THÊM của kế hoạch, mặc định 0. KHÔNG mồi bằng tổng bù hao của
                # phiếu tính giá: chuỗi ngược đã cộng hao từng bước theo định mức danh mục, mồi
                # thêm cục tổng vào bước cuối là ĐẾM HAI LẦN.
                bu_hao_to=0,
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

    def _canh_bao_don_vi(self, lsx: Lsx) -> list[str]:
        """Cảnh báo MỀM về chuỗi đơn vị. LỌC bước NGOÀI dòng giấy ra TRƯỚC rồi mới so liền kề —
        không lọc thì bước ghi kẽm (`bai → kem`) đứng đầu routing đẻ cảnh báo giả với bước in."""
        tram = self._tram()
        tat_ca = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        buoc = [c for c in tat_ca if tren_dong_giay(c.don_vi_vao, c.don_vi_ra, tram)]
        out: list[str] = []
        # Bước rơi KHỎI dòng giấy thì bù hao của nó biến mất khỏi số giấy phải mua và số lượng đứng
        # im ở 0 (kéo theo thời lượng 0) — phải kêu. Trừ chế bản: nó vốn không chạm giấy, kêu là kêu
        # oan mọi lệnh. Cùng luật với cảnh báo bên engine tính giá, để hai màn nói cùng một câu.
        if any(c.nhom != "prepress" and not tren_dong_giay(c.don_vi_vao, c.don_vi_ra, tram)
               for c in tat_ca):
            out.append("buoc_ngoai_dong_giay")
        if any(not chieu_hop_le(c.don_vi_vao, c.don_vi_ra, tram) for c in buoc):
            out.append("cap_don_vi_sai")
        # So liền mạch theo TRẠM: hai bước khai hai mã khác nhau cho cùng một chặng là hợp lệ.
        if any(tram_cua(t.don_vi_ra, tram) != tram_cua(s.don_vi_vao, tram)
               for t, s in zip(buoc, buoc[1:])):
            out.append("dut_don_vi")
        # Bước cuối phải giao đủ hàng — nhưng SO BẰNG ĐƠN VỊ CỦA NÓ, không so thẳng với SL đặt:
        # routing kết ở `con` thì bước cuối nhả số CON, khách thì đặt số CÁI. So thẳng là đẻ cảnh
        # báo giả cho mọi lệnh loại đó. Dựng lại đích bằng đúng công thức chuỗi đã dùng.
        if buoc:
            he_so = self._he_so_cau(lsx)
            mong_doi = dich_chuoi(
                float(lsx.so_luong_dat or 0),
                tram_ra_cuoi=tram_cua(buoc[-1].don_vi_ra, tram),
                cai_moi_to=he_so.get((TRAM_TO, TRAM_CAI)) or 1.0,
                he_so=he_so,
            )
            if ceil(mong_doi) != int(_f(buoc[-1].so_luong_ra)):
                out.append("lech_sl_don")
        return out

    # ================= TÍNH NGƯỢC · LEAD TIME · CẢNH BÁO =================

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
        if not idx:
            return []
        he_so = self._he_so_cau(lsx, so_con=so_con)
        bu_hao_rows = [_bu_hao_to_dict(b) for b in self.db.execute(
            select(BuHao).where(BuHao.active.is_(True))
        ).scalars()]
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
            if pos == len(idx) - 1:      # bước CUỐI nhận thêm hao của kế hoạch
                fixed += _f(lsx.bu_hao_to)
            # Hệ số tra theo TRẠM, không theo mã: xưởng khai mã riêng cho một chặng thì cặp mã
            # không có trong bảng cầu, engine ăn 1.0 và cấp thiếu giấy trong im lặng.
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
        bu_hao_rows = [_bu_hao_to_dict(b) for b in self.db.execute(
            select(BuHao).where(BuHao.active.is_(True))
        ).scalars()]
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
        for cd in lsx.cong_doans:
            t = thoi_luong_buoc(cd, self._may_cua_buoc(cd))
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

    def canh_bao_cua(self, lsx: Lsx) -> list[str]:
        """Rổ cảnh báo MỀM (§14) — chỉ tô màu, KHÔNG chặn lưu và KHÔNG chặn "Sẵn sàng".

        Toàn là phán đoán nghề: máy nêu nghi vấn, người kế hoạch quyết. Ví dụ "đứt chuyền" có thể
        đúng ý (chừa bán thành phẩm cho lệnh khác), nên chặn là sai.
        """
        canh_bao: list[str] = []
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)

        for i, cd in enumerate(buoc):
            vao, ra = _f(cd.so_luong_vao), _f(cd.so_luong_ra)
            if cd.don_vi_vao == cd.don_vi_ra and vao > 0 and ra > vao and "ra_lon_hon_vao" not in canh_bao:
                canh_bao.append("ra_lon_hon_vao")
            if i + 1 < len(buoc):
                sau = buoc[i + 1]
                if (cd.don_vi_ra == sau.don_vi_vao and ra > 0 and _f(sau.so_luong_vao) > ra
                        and "dut_chuyen" not in canh_bao):
                    canh_bao.append("dut_chuyen")

        lt = self.lead_time(lsx)
        if lt["ngay_con_lai"] is not None and lt["so_ngay"] > lt["ngay_con_lai"]:
            canh_bao.append("vuot_han_giao")

        goc = lsx.routing_goc_json
        if goc is not None and goc != _routing_van_tay(lsx.cong_doans):
            canh_bao.append("khac_bai_tinh_gia")

        if self._may_khong_hop_kho(lsx):
            canh_bao.append("may_khong_hop_kho")
        canh_bao.extend(self._canh_bao_don_vi(lsx))
        return canh_bao

    def _may_khong_hop_kho(self, lsx: Lsx) -> bool:
        """Khổ tờ in vượt khổ tối đa của máy đã gán (xoay 90° vẫn không lọt)."""
        qc = lsx.quy_cach_json or {}
        dai, rong = _f(qc.get("kho_in_dai")), _f(qc.get("kho_in_rong"))
        if dai <= 0 or rong <= 0:
            return False
        may_ids = {cd.may_id for cd in lsx.cong_doans if cd.may_id}
        if lsx.may_id:
            may_ids.add(lsx.may_id)
        for mid in may_ids:
            may = self.db.get(MayThietBi, mid)
            max_d, max_r = _f(may.kho_max_dai) if may else 0, _f(may.kho_max_rong) if may else 0
            if max_d <= 0 or max_r <= 0:
                continue
            lot = (dai <= max_d and rong <= max_r) or (rong <= max_d and dai <= max_r)
            if not lot:
                return True
        return False

    def detail_dict(self, lsx: Lsx) -> dict:
        """Ghép dữ liệu hiển thị (tên đơn/khách/máy/tổ/khuôn) cho 1 lệnh."""
        order = self.db.get(Order, lsx.order_id)
        dept_ids = {cd.department_id for cd in lsx.cong_doans if cd.department_id}
        may_ids = {cd.may_id for cd in lsx.cong_doans if cd.may_id}
        if lsx.may_id:
            may_ids.add(lsx.may_id)
        dept_names = self._dept_names(dept_ids)
        may_names = self._may_names(may_ids)
        khuon = self.db.get(KhuonBe, lsx.khuon_be_id) if lsx.khuon_be_id else None
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
        buoc_dicts = [
            self._cong_doan_dict(cd, dept_names, may_names, qc_bien)
            for cd in lsx.cong_doans
        ]
        return {
            "nhom": getattr(line, "nhom", None),
            "order_no": order.order_no if order else None,
            "customer_name": self._customer_name(order) if order else None,
            "customer_po_no": order.customer_po_no if order else None,
            "sale_name": self._user_name(order.sale_user_id) if order else None,
            "quote_number": quote_number,
            "quote_version_number": quote_version_number,
            "ptg_id": ptg_id,
            "ptg_ma": ptg_ma,
            "khuon_be_ten": (khuon.ten if khuon else None),
            "may_ten": may_names.get(lsx.may_id),
            "nguoi_phu_trach_ten": self._user_name(lsx.nguoi_phu_trach_id),
            "thieu": self.thieu_cua(lsx),
            "canh_bao": self.canh_bao_cua(lsx),
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

    def _khuon_ten(self, khuon_id: int | None) -> str | None:
        if not khuon_id:
            return None
        k = self.db.get(KhuonBe, khuon_id)
        return k.ten if k is not None else None

    def _cong_doan_dict(self, cd, dept_names: dict, may_names: dict,
                        quy_cach: dict | None = None) -> dict:
        vao = _f(cd.so_luong_vao)
        t = thoi_luong_buoc(cd, self._may_cua_buoc(cd))
        kh = cd.khoan_json or {}
        cd_obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
        return {
            "id": cd.id, "step_key": cd.step_key, "thu_tu": cd.thu_tu, "cong_doan_id": cd.cong_doan_id,
            "ten": cd.ten, "nhom": cd.nhom, "loai_buoc": cd.loai_buoc, "bat_buoc": bool(cd.bat_buoc),
            "department_id": cd.department_id,
            "department_ten": dept_names.get(cd.department_id),
            "may_id": cd.may_id, "may_ten": may_names.get(cd.may_id),
            # Dụng cụ của CHÍNH bước này. Hai cờ đi kèm để form biết có phải hỏi khuôn không —
            # đọc CỜ ở danh mục Công đoạn, không suy từ tên bước (tên là chữ người dùng gõ).
            # `khuon_be_ten` để hiện chữ khi người xem không có quyền đọc danh mục khuôn.
            "requires_tooling": bool(getattr(cd_obj, "requires_tooling", False)),
            "tooling_type": getattr(cd_obj, "tooling_type", None),
            "khuon_be_id": cd.khuon_be_id,
            "khuon_be_ten": self._khuon_ten(cd.khuon_be_id),
            "so_luong_vao": vao, "so_luong_ra": _f(cd.so_luong_ra),
            "don_vi_vao": cd.don_vi_vao, "don_vi_ra": cd.don_vi_ra,
            # Bước có nằm trên DÒNG GIẤY không. Bước ngoài dòng đứng ngoài chuỗi bù hao nên số
            # lượng KHÔNG tự tính (đứng im ở 0 nếu không ai điền) và hao của nó không cộng vào số
            # giấy phải mua. Không gửi cờ này thì màn chỉ thấy hai số 0 mà không có lời giải thích
            # — FE tự suy không nổi vì "trên dòng giấy hay không" nằm ở cờ của danh mục Đơn vị.
            "tren_dong_giay": tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, self._tram()),
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
        self.audit.create(
            actor_user_id=actor.id, action=action, target=f"lsx_cong_doan:{cd.id}",
            detail=f"{lsx.ma} · {cd.ten}: {ten} {nhan_vc} "
                   f"{_f(so_ghi):,.0f} {cd.don_vi_ra or ''}".replace(",", ".").strip(),
        )
        self.repo.commit()
        return self.get(lsx_id)

    def _dau_viec_cua_buoc(self, cd) -> list:
        obj = self.db.get(CongDoan, cd.cong_doan_id) if cd.cong_doan_id else None
        return self._dau_viec_cua_cong_doan(obj, cd.department_id)

    def list_rows(self, **kw) -> list[dict]:
        rows = self.repo.list(**kw)
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
                "customer_name": self._customer_name(o) if o else None,
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
        return out

    def phu_thuoc_options(self, lsx_id: int) -> list[dict]:
        current = self.get(lsx_id)
        lsxs = self.repo.list(order_id=current.order_id)
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

    def update(self, *, lsx_id: int, payload, actor) -> Lsx:
        lsx = self.get(lsx_id)
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxConflict("Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi sửa")
        data = payload.model_dump(exclude_unset=True)
        changed: list[str] = []
        # `so_to_ke_hoach` / `so_to_nguyen` KHÔNG còn nhận từ client — hai mốc đó nay đọc ra từ
        # chuỗi ngược (`_ap_chuoi_nguoc`), nhận thêm đường nữa là đẻ nguồn sự thật thứ hai.
        for field in (
            "ten", "so_luong_dat", "don_vi_tinh", "bu_hao_to",
            "so_con", "han_hoan_thanh_sx", "is_rush", "khuon_be_id", "may_id",
            "nguoi_phu_trach_id", "ghi_chu",
        ):
            if field in data and getattr(lsx, field) != data[field]:
                setattr(lsx, field, data[field])
                changed.append(field)
        # THÔNG SỐ (ảnh chụp) đổi → trộn vào rồi tính lại mọi số dẫn xuất. Đặt TRƯỚC chuỗi ngược
        # vì nó có thể đổi `so_con` (bình bài lại) — thứ chuỗi ngược lấy làm hệ số cầu.
        if data.get("quy_cach"):
            qc_moi, qc_doi = self.ap_quy_cach(lsx, data["quy_cach"])
            if qc_doi:
                lsx.quy_cach_json = qc_moi
                changed.extend(f"quy_cach.{k}" for k in qc_doi)
        # SL đặt / con·tờ / hao thêm / thông số đổi → cả chuỗi phải tính lại.
        if {"so_luong_dat", "so_con", "bu_hao_to"} & set(changed) or data.get("quy_cach"):
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
    )
    _ROUTING_FIELD_NULLABLE = {
        "may_id", "khuon_be_id", "chay_phut", "nha_cung_cap", "ngay_gui_dk", "ngay_nhan_dk",
        "ghi_chu",
    }

    def replace_routing(self, *, lsx_id: int, rows_in, actor, ly_do: str | None = None) -> Lsx:
        lsx = self.get(lsx_id)
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxConflict("Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi sửa routing")
        truoc = len(lsx.cong_doans)
        old_by_key = {r.step_key: r for r in lsx.cong_doans}
        rows: list[LsxCongDoan] = []
        payloads: list[dict] = []
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
                dv_vao = cd_obj.don_vi_vao if cd_obj is not None else row.don_vi_vao
                dv_ra = cd_obj.don_vi_ra if cd_obj is not None else row.don_vi_ra
                row.nang_suat, row.don_vi_nang_suat = _nang_suat_buoc(
                    may, cd_obj, dv_vao, dv_ra=dv_ra, tram=self._tram())
                kip = max(int(ceil(_f(may.so_nhan_cong))), 1) if may is not None else 1
                _ke_thua("so_nhan_cong_tieu_chuan", kip)
                _ke_thua("so_nhan_cong_toi_da", None)
                _ke_thua("so_nhan_cong_toi_thieu", None)
                _ke_thua("so_nhan_cong", kip)
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
                    raise LsxValidationError("Đầu việc không thuộc công đoạn hoặc tổ phụ trách")
                row.khoan_json = khoan_snapshot(rate) if rate is not None else None
                if rate is not None:
                    dm = next((x for x in (getattr(cd_obj, "dau_viec_dinh_muc", None) or [])
                               if x.piece_rate_id == rate.id), None)
                    if dm is not None:
                        row.khoan_json.update(_dinh_muc_snapshot(dm))
                        row.nang_suat = _f(dm.nang_suat_nguoi_gio)
                        row.don_vi_nang_suat = self._dv_ns(
                            row.khoan_json, cd_obj.don_vi_vao if cd_obj else None
                        )
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
                    row.don_vi_nang_suat = self._dv_ns(
                        snap, cd_obj.don_vi_vao if cd_obj else None
                    )
                    _ke_thua("so_nhan_cong_toi_thieu",
                             int(snap["so_nguoi_toi_thieu"]) if snap.get("so_nguoi_toi_thieu") else None)
                    _ke_thua("so_nhan_cong_tieu_chuan", int(snap.get("so_nguoi_tieu_chuan") or 1))
                    _ke_thua("so_nhan_cong_toi_da",
                             int(snap["so_nguoi_toi_da"]) if snap.get("so_nguoi_toi_da") else None)
                    _ke_thua("so_nhan_cong", row.so_nhan_cong_tieu_chuan)
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

        # Vật tư là khai báo riêng của bước, chỉ chọn từ danh mục đang hoạt động; không đọc PTG.
        for row, d in zip(rows, payloads):
            if "vat_tus" not in d:
                continue
            vat_tus = d.get("vat_tus") or []
            ids = [int(v.get("vat_tu_id") or 0) for v in vat_tus]
            if len(ids) != len(set(ids)):
                raise LsxValidationError("Một vật tư không được chọn trùng trong cùng công đoạn")
            mats = {
                v.id: v for v in self.db.execute(
                    select(VatTuInAn).where(VatTuInAn.id.in_(ids), VatTuInAn.active.is_(True))
                ).scalars()
            } if ids else {}
            if len(mats) != len(ids):
                raise LsxValidationError("Vật tư không tồn tại hoặc đã ngừng sử dụng")
            row.vat_tus.clear()
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
        order_id, ma = lsx.order_id, lsx.ma
        self.repo.delete(lsx)
        self.audit.create(
            actor_user_id=actor.id, action="delete_lsx", target=f"lsx:{lsx_id}",
            detail=f"Xoá lệnh {ma}",
        )
        self.repo.commit()
        return order_id
