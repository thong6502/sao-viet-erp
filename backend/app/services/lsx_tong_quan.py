"""Hàng đèn TỔNG QUAN của lệnh sản xuất — đọc lại 2 engine đã có, KHÔNG tính lại gì.

Câu hỏi màn Kế hoạch SX phải trả lời trong một cái liếc: *lệnh này đang tắc ở đâu*. Trước đây
muốn biết phải mở 3 màn (Kế hoạch vật tư · Bài ghép · Xếp lịch). Ba đèn ở đây là ba thứ bảng lệnh
CHƯA hề nói:

  · **Vật tư**    — giữ chỗ đủ chưa. Cố ý soi ĐÚNG cửa `XepLichService._chan_chua_giu_du`: đèn đỏ
    nghĩa là bấm "Đưa vào kế hoạch" sẽ bị chặn, không phải "hình như có vấn đề".
  · **Máy & giờ** — bước nào chưa lên được lịch, hoặc lịch đang đá nhau.
  · **Người**     — tổ có đủ quân cho khung giờ đã xếp không.

**Không thêm đèn cho Hạn và Định mức**: bảng lệnh đã có cột `Hạn` tô màu (`classHan`) và cột `CĐ`
đỏ khi lệnh chưa có công đoạn. Đèn thứ tư nói lại chuyện cột bên cạnh vừa nói chỉ làm loãng đúng
hai cái đèn đáng nhìn.

**Chỉ trả `do` / `vang` / `ok`** — FE chỉ vẽ chấm cho `do` và `vang`. 20 lệnh × 3 chấm mà đa số
xanh thì mắt không bắt được cái đỏ; điều độ quét bảng để TÌM chỗ tắc, không cần xác nhận chỗ
không tắc.

Đắt: một lượt `KeHoachVatTuService.can_doi()` + một lượt `XepLichVanDeService` cho CẢ trang — chi
phí gần như không đổi theo số lệnh, nhưng khác 0. Nên router gọi RỜI sau bảng lệnh, chỉ cho các
lệnh đang hiển thị (xem `routers/lsx.py::tong_quan`).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.lsx import LB_TO
from ..models.xep_lich_van_de import TT_NGOAI_LE
from .xep_lich_van_de_service import (
    K_DE_KHOA_MAY, K_LECH_THUC_TE, K_LICH_DA_QUA, K_MAY_KHONG_KHAM, K_QUA_TAI_TO,
    K_SAI_TIEN_NHIEM, K_THIEU_DU_LIEU, K_THIEU_NGUOI, K_TRUNG_MAY, XepLichVanDeService,
)

MUC_DO = "do"
MUC_VANG = "vang"
MUC_OK = "ok"

MAN_VAT_TU = "ke-hoach-vat-tu"
# Id ĐƯỜNG DẪN của màn xếp lịch là `xep-lich-cong-doan-2` (màn cũ gỡ 19/08/2026, id `-2`
# giữ nguyên để không hỏng dấu trang + bản đồ badge — xem chú thích trong Sidebar.tsx).
# Trỏ vào id cũ = FE không tra ra module nào ⇒ bắn banner 403 dù người dùng là admin.
MAN_XEP_LICH = "xep-lich-cong-doan-2"

# Vấn đề nào rơi vào đèn nào. Soi TIỀN TỐ `issue_key` (`trung_may:…`) chứ KHÔNG soi `category`:
# 18/08/2026 `category` đã gom còn 6 loại cho người đọc, nên `may` nay trùm cả bốn thứ trùng-giờ ·
# đè-khoá · quá-tải · không-kham-khổ — bốn thứ đó không cùng màu đèn (ba cái đầu ĐỎ, cái cuối
# VÀNG) và mỗi cái một câu chữ khác nhau, gom lại là mất đúng chỗ điều độ cần. Tiền tố khoá thì
# vẫn mịn theo từng bộ dò.
# LẤY HẰNG TỪ `xep_lich_van_de_service`, KHÔNG gõ lại chuỗi: đổi tiền tố ở đó mà quên ở đây thì
# đèn tắt IM LẶNG (không lỗi, chỉ là không khớp cái nào) — kiểu hỏng khó thấy nhất.
# Thứ tự trong tuple là thứ tự ưu tiên hiện chữ khi một lệnh dính nhiều thứ một lúc.
CAT_MAY_DO = (K_TRUNG_MAY, K_DE_KHOA_MAY, K_SAI_TIEN_NHIEM, K_LICH_DA_QUA, K_THIEU_DU_LIEU)
CAT_NGUOI_DO = (K_QUA_TAI_TO, K_THIEU_NGUOI)
# Khổ tờ in vượt máy: CẢNH BÁO, không chặn (chốt 18/08/2026 — thợ còn cách xử lý, máy không quyết).
# Tổ chạy lệch mốc đã xếp: cũng CẢNH BÁO — lệnh đã phát hành rồi, chặn ở đây không cứu được gì,
# việc của điều độ là BIẾT để kéo lại tay (spec-thuc-te-vs-ke-hoach §2.2). Không có dòng này thì bộ
# dò `lech_thuc_te` chạy đúng nhưng không tới được mắt ai: hàng đèn là mặt duy nhất của nó trên
# bảng lệnh, và tập ở đây mới quyết đèn nào sáng — đúng kiểu hỏng im lặng mà chú thích trên cảnh báo.
CAT_MAY_VANG = (K_MAY_KHONG_KHAM, K_LECH_THUC_TE)

_CHU_MAY_DO = {
    K_TRUNG_MAY: "Trùng giờ với việc khác trên cùng máy",
    K_DE_KHOA_MAY: "Xếp đè lên khoảng khóa máy",
    K_SAI_TIEN_NHIEM: "Công đoạn sau chạy trước công đoạn trước",
    K_LICH_DA_QUA: "Mốc đã xếp trôi qua, chưa ai vào việc — xếp lại giờ",
    K_THIEU_DU_LIEU: "Có bước chưa gán máy/tổ hoặc chưa khai năng suất",
}
_CHU_MAY_VANG = {
    K_MAY_KHONG_KHAM: "Khổ tờ in vượt khổ máy — cần xác nhận",
    K_LECH_THUC_TE: "Xưởng đang chạy lệch mốc đã xếp — xem lại giờ",
}
_CHU_NGUOI_DO = {
    K_QUA_TAI_TO: "Tổ không đủ người cho các việc chạy cùng lúc",
    K_THIEU_NGUOI: "Bố trí dưới số người tối thiểu của đầu việc",
}


def _den(muc: str, chu: str = "", man: str | None = None, lsx_id: int | None = None) -> dict:
    return {"muc": muc, "chu": chu,
            "nhay": {"man": man, "id": lsx_id} if man and muc != MUC_OK else None}


def _den_vat_tu(tt: dict, lsx_id: int) -> dict:
    """Soi ĐÚNG thứ tự của `_chan_chua_giu_du` để đèn nói cùng một câu với cửa chặn.

    `du=True` mà còn hàng đang trên đường về → vàng kèm ngày: chạy được, nhưng đừng xếp trước ngày
    đó. Đây là thông tin điều độ cần TRƯỚC khi kéo thanh, không phải sau khi bị báo đỏ.
    """
    if tt.get("du"):
        ngay = tt.get("xep_som_nhat")
        if ngay:
            return _den(MUC_VANG, f"Đủ, nhưng hàng về {ngay:%d/%m} — xếp từ ngày đó trở đi",
                        MAN_VAT_TU, lsx_id)
        return _den(MUC_OK)
    if not tt.get("bat"):
        # Lệnh không cần vật tư nào cũng rơi vào đây (`du` cần `bool(can)`), và cửa chặn thật cũng
        # chặn — đèn nói y hệt cửa thì người dùng không phải đoán vì sao bấm không được.
        return _den(MUC_DO, "Chưa giữ chỗ vật tư", MAN_VAT_TU, lsx_id)
    if tt.get("khong_ro"):
        return _den(MUC_DO, "Có vật tư chưa quy đổi được đơn vị kho", MAN_VAT_TU, lsx_id)
    thieu = tt.get("thieu") or {}
    if not thieu:
        # `du` đòi `bool(can)`: lệnh không ra được nhu cầu nào cũng rơi vào nhánh này, và cửa chặn
        # thật cũng chặn — nhưng câu "còn thiếu 0 mặt hàng" thì vô nghĩa, nói thẳng ra là chưa tính
        # được nhu cầu.
        return _den(MUC_DO, "Chưa tính được nhu cầu vật tư của lệnh", MAN_VAT_TU, lsx_id)
    return _den(MUC_DO, f"Mới giữ được một phần, còn thiếu {len(thieu)} mặt hàng",
                MAN_VAT_TU, lsx_id)


def _den_may(cats: set[str], rows: list[dict], lsx_id: int) -> dict:
    """`cats` = tập TIỀN TỐ `issue_key` của lệnh (xem chú thích CAT_MAY_DO)."""
    for c in CAT_MAY_DO:
        if c in cats:
            return _den(MUC_DO, _CHU_MAY_DO[c], MAN_XEP_LICH, lsx_id)
    if not rows:
        return _den(MUC_OK)                       # chưa vào kế hoạch — cột Trạng thái đã nói rồi
    cho_gio = sum(1 for r in rows if not r.get("start_at"))
    if cho_gio:
        return _den(MUC_VANG, f"{cho_gio} bước chưa có giờ", MAN_XEP_LICH, lsx_id)
    for c in CAT_MAY_VANG:
        if c in cats:
            return _den(MUC_VANG, _CHU_MAY_VANG[c], MAN_XEP_LICH, lsx_id)
    return _den(MUC_OK)


def _den_nguoi(cats: set[str], rows: list[dict], lsx_id: int) -> dict:
    for c in CAT_NGUOI_DO:
        if c in cats:
            return _den(MUC_DO, _CHU_NGUOI_DO[c], MAN_XEP_LICH, lsx_id)
    # Bước tổ chưa gán tổ mà KHÔNG bắt buộc: `thieu_du_lieu` bỏ qua (đúng — nó không chặn), nhưng
    # người điều độ vẫn cần biết còn một việc tay chưa có ai làm.
    chua_to = sum(1 for r in rows if r.get("loai_buoc") == LB_TO and not r.get("department_id"))
    if chua_to:
        return _den(MUC_VANG, f"{chua_to} bước tổ chưa gán tổ", MAN_XEP_LICH, lsx_id)
    return _den(MUC_OK)


def _dung_vat_tu(db: Session):
    """Dựng `GiuChoService` + bảng cân đối MỘT lần cho cả trang.

    Import trễ y như `XepLichService._chan_chua_giu_du`: cả chuỗi kho/mua/đơn vị kéo theo nhau,
    nạp sẵn ở đầu module chỉ để phục vụ một endpoint đọc là nặng import graph vô ích.
    """
    from ..repositories.bai_ghep_repo import BaiGhepRepository
    from ..repositories.don_vi_do_repo import DonViDoRepository
    from ..repositories.lsx_repo import LsxRepository
    from ..repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
    from ..repositories.stock_lot_repo import StockLotRepository
    from ..repositories.stock_request_repo import StockRequestRepository
    from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from .giu_cho_service import GiuChoService
    from .ke_hoach_vat_tu_service import KeHoachVatTuService
    from .vat_lieu_kho_service import VatLieuKhoService

    kh = KeHoachVatTuService(
        db, lsx_repo=LsxRepository(db), bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db), requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db), suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )
    return GiuChoService(db, kh), kh.can_doi()


def tong_quan(db: Session, lsx_ids: list[int]) -> list[dict]:
    """`[{lsx_id, den: {vat_tu, may_gio, nguoi}}]` cho đúng các lệnh được hỏi.

    Hai nguồn số đều HỎNG ĐƯỢC (bảng cân đối lỗi đơn vị, engine lịch lỗi dữ liệu) mà không được
    kéo sập cả bảng lệnh — bảng lệnh vẫn phải hiện. Nên mỗi nguồn bọc `try` riêng và khi hỏng thì
    đèn tương ứng về `ok` KÈM chữ: im lặng ở đây là nói dối "không có vấn đề".
    """
    ids = [i for i in dict.fromkeys(lsx_ids) if i]
    if not ids:
        return []
    idset = set(ids)

    # --- Nguồn 1: bàn xếp lịch (dòng + vấn đề) trong MỘT lượt tính ---
    cats: dict[int, set[str]] = {i: set() for i in ids}
    rows_theo_lsx: dict[int, list[dict]] = {i: [] for i in ids}
    loi_lich = ""
    try:
        rows, issues = XepLichVanDeService(db).dong_va_van_de()
        for r in rows:
            if r.get("lsx_id") in idset:
                rows_theo_lsx[r["lsx_id"]].append(r)
        for it in issues:
            if it.get("trang_thai") == TT_NGOAI_LE:      # đã duyệt ngoại lệ = đã có người chịu
                continue
            for i in it["impacts"]["lsx_ids"]:
                if i in idset:
                    cats[i].add(it["issue_key"].split(":", 1)[0])
    except Exception as exc:                                            # noqa: BLE001
        loi_lich = f"Chưa đọc được lịch ({type(exc).__name__})"

    # --- Nguồn 2: giữ chỗ vật tư, một bảng cân đối dùng chung cả trang ---
    giu = bang = None
    giu_theo_lsx: dict[int, list] = {}
    loi_vt = ""
    try:
        giu, bang = _dung_vat_tu(db)
        # Dòng giữ chỗ của CẢ TRANG trong MỘT câu. Không có nó thì `trang_thai()` bên dưới tự đi
        # lấy — tức một câu SELECT cho MỖI lệnh, và hàm này lại là nguồn đèn vật tư của màn danh
        # sách lệnh. Bài canh: `test_lenh_sx_api.test_so_cau_sql_hang_tren_truc_lenh`.
        giu_theo_lsx = giu.repo.cua_nhieu_chu_the([(i, None) for i in ids])
    except Exception as exc:                                            # noqa: BLE001
        loi_vt = f"Chưa đọc được vật tư ({type(exc).__name__})"

    out: list[dict] = []
    for i in ids:
        if giu is not None:
            try:
                den_vt = _den_vat_tu(
                    giu.trang_thai(lsx_id=i, bang=bang, dang_theo_chu_the=giu_theo_lsx), i
                )
            except Exception as exc:                                    # noqa: BLE001
                den_vt = _den(MUC_OK, f"Chưa đọc được vật tư ({type(exc).__name__})")
        else:
            den_vt = _den(MUC_OK, loi_vt)
        if loi_lich:
            den_may = den_nguoi = _den(MUC_OK, loi_lich)
        else:
            den_may = _den_may(cats[i], rows_theo_lsx[i], i)
            den_nguoi = _den_nguoi(cats[i], rows_theo_lsx[i], i)
        out.append({"lsx_id": i, "slack_ngay": _slack(rows_theo_lsx[i]),
                    "den": {"vat_tu": den_vt, "may_gio": den_may, "nguoi": den_nguoi}})
    return out


def _slack(rows: list[dict]) -> int | None:
    """Độ dư NHỎ NHẤT giữa các bước — để cột `Hạn` tô màu theo LỊCH THẬT, không đếm ngày lịch.

    `classHan` ở FE đang tô đỏ khi quá hạn / hổ phách khi còn ≤3 ngày. Câu đó bỏ qua mất chuyện
    quan trọng hơn: lệnh còn 10 ngày tới hạn nhưng lịch đã kéo qua hạn 2 ngày thì nó ĐANG trễ, mà
    bảng vẫn xanh. Có số này thì cột cũ nói đúng hơn, không thêm ô nào.

    `None` khi lệnh chưa vào kế hoạch hoặc chưa bước nào có giờ ⇒ FE lùi về đếm ngày lịch.
    """
    co = [r["slack_ngay"] for r in rows if r.get("slack_ngay") is not None]
    return min(co) if co else None
