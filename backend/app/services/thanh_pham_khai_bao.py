"""Khai THÀNH PHẨM của một khách vào danh mục — MỘT hàm, hai nơi gọi.

Vì sao có file này (docs/prd-thanh-pham.md):

Sản phẩm in là hàng ĐẶT RIÊNG. "Hộp thuốc 10 vỉ — in 2 màu, cán bóng" của khách A không có sẵn ở
danh mục nào và sẽ không bao giờ có. Nhưng kho chỉ xuất được thứ CÓ trong danh mục (luật siết
08/08/2026 bỏ ô tên tự do `stock_request_lines.ten_tu_do`). Hai câu đó đá nhau, và bản đầu giải
sai bằng cách bắt người lập yêu cầu giao "chọn mặt hàng kho" — tức bắt chọn một thứ chưa tồn tại.

⚠️ PHẠM VI ĐỊNH DANH là `(khách hàng, tên đã chuẩn hoá)`, **KHÔNG** phải dòng đơn.

Bản đầu lấy khoá `TP-<số đơn>-<id dòng>` và chủ dự án bắt đúng lỗi (19/08/2026):

    Th08  Khách A · đơn 041 · dòng #11  "Hộp thuốc 10 vỉ"  → TP-...-041-11
    Th09  Khách A · đơn 052 · dòng #77  "Hộp thuốc 10 vỉ"  → TP-...-052-77   ⚠️ dòng THỨ HAI

Nặng nhất không phải danh mục phình, mà là **TỒN KHO BỊ XÉ ĐÔI**: hàng dư tháng 8 nằm ở dòng một,
hàng in tháng 9 nằm ở dòng hai, và kho không trả lời được "còn bao nhiêu Hộp thuốc 10 vỉ" — đúng
câu duy nhất họ cần.

Có KHÁCH trong khoá là bắt buộc: hai khách khác nhau đều có thể đặt "Tờ hướng dẫn sử dụng — gấp 3"
nhưng là hai file in khác hẳn. Gộp lại là giao tờ của khách A cho khách B.

Hai nơi gọi:

  1. `OrderService.confirm()` — ĐƯỜNG CHÍNH. Chốt đơn là khai, để kho nhập kho thành phẩm được
     ngay khi sản xuất xong, không phải chờ ai đó nghĩ tới việc lập yêu cầu giao.
  2. `DeliveryService._mat_hang_cua_dong_don` — LƯỚI AN TOÀN cho đơn đã chốt TRƯỚC mg 0203.
     Cùng hàm này nên khoá sinh ra giống hệt, không lệch.
"""
from __future__ import annotations

import re
import unicodedata

from ..models.vat_lieu_kho import VatTuInAn

#: Tiền tố mã thành phẩm. `ma` chỉ 30 ký tự nên `TP-` + mã khách (`KH001`) + `-001` là vừa.
TIEN_TO = "TP"

#: Mọi biến thể gạch ngang về một mối trước khi so tên. "10 vỉ — in" và "10 vỉ - in" là MỘT
#: sản phẩm; giữ nguyên hai kiểu gạch là đẻ hai dòng danh mục cho cùng một món.
_GACH = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")


def chuan_ten(ten: str | None) -> str:
    """Khoá so sánh tên. Lệch hoa/thường · khoảng trắng · kiểu gạch ⇒ vẫn là MỘT sản phẩm.

    Chuẩn hoá chứ không so nguyên văn (chủ chốt 19/08/2026): người lập đơn tháng sau gõ lại mô tả
    bằng tay, lệch một dấu phẩy là bản so-nguyên-văn đẻ thêm dòng — đúng cái lỗi đang sửa.

    KHÔNG bỏ dấu tiếng Việt: "Bìa" và "Bia" là hai thứ khác nhau.
    """
    s = unicodedata.normalize("NFC", (ten or "")).translate(_GACH).casefold()
    s = re.sub(r"\s+", " ", s).strip()
    # Chỉ gọt dấu câu ở HAI ĐẦU — gọt cả chuỗi thì "7×5cm" và "75cm" hoá một.
    return s.strip(" -–—.,;:·|/\\")


def _ma_ke_tiep(db) -> str:
    """`TP-00001`, một dãy số dùng chung.

    Trước 21/08/2026 mã kèm mã khách (`TP-KH001-001`) vì thành phẩm thuộc về một khách. Chủ bỏ
    khách khỏi thành phẩm ⇒ không còn gì để nhét vào giữa. Mã CŨ giữ nguyên, không đổi: nó đang
    nằm trong lô tồn và phiếu đã ghi sổ.

    Đếm theo TIỀN TỐ chứ không theo `count(*)`: dòng đã xoá không được làm tái dụng số cũ.
    """
    goc = f"{TIEN_TO}-"
    dung = {
        r[0] for r in db.query(VatTuInAn.ma).filter(VatTuInAn.ma.like(f"{goc}%")).all()
    }
    n = 1
    while f"{goc}{n:05d}" in dung:
        n += 1
    return f"{goc}{n:05d}"


def tim_hoac_khai(db, *, customer_id: int | None = None, ten: str, dvt: str | None = None,
                  order_id: int | None = None, order_line_id: int | None = None) -> VatTuInAn:
    """Get-or-create theo TÊN ĐÃ CHUẨN HOÁ. Trả về dòng danh mục.

    ⚠️ Khoá gộp trùng ĐỔI ngày 21/08/2026, từ `(khách, tên)` sang `tên`. Chủ: "thành phẩm này là
    một cái tên hàng, nêu chưa khai để tái sử dụng, tránh phình lên" — hai khách cùng đặt "Hộp
    thuốc 10 vỉ" nay dùng CHUNG một dòng, không đẻ hai dòng nữa.

    `customer_id` vẫn nhận để ghi lại khách ĐẦU TIÊN đặt món này (tra nguồn gốc), KHÔNG còn là
    khoá — đừng dùng nó để lọc.

    `flush()` chứ không `commit()`: nơi gọi làm chủ giao dịch. `confirm()` chốt đơn và khai thành
    phẩm phải đi CHUNG một giao dịch — chốt xong mà khai hỏng thì đơn đã `ordered` nhưng kho
    không có gì để nhập, và không ai biết cho tới lúc cần giao.
    """
    khoa = chuan_ten(ten)
    if khoa:
        # Nạp cả rổ THÀNH PHẨM rồi so trong Python: `chuan_ten` gộp gạch ngang và khoảng trắng,
        # SQL `lower()` không làm được. Lọc `la_thanh_pham` để không đụng vào mực/kẽm/hoá chất
        # bên màn Vật tư — trùng tên với vật tư là chuyện có thể xảy ra.
        for h in db.query(VatTuInAn).filter(VatTuInAn.la_thanh_pham.is_(True)).all():
            if chuan_ten(h.ten) == khoa:
                return h

    obj = VatTuInAn(
        ma=_ma_ke_tiep(db),
        la_thanh_pham=True,
        # NGUYÊN VĂN mô tả dòng đơn (PRD L3) — kho tìm bằng đúng cái tên khách đặt. Cắt 150 theo
        # `vat_tu_in_an.ten`.
        ten=(ten or "").strip()[:150] or "(chưa có tên)",
        don_vi_gia=dvt or None,
        don_gia=0,
        customer_id=customer_id,
        # `order_id` / `order_line_id` = đơn ĐẦU TIÊN đặt món này, giữ để tra nguồn gốc. KHÔNG
        # dùng làm khoá định danh nữa và KHÔNG cập nhật ở lần đặt sau (xem đầu file).
        order_id=order_id,
        order_line_id=order_line_id,
        ghi_chu=None,
    )
    db.add(obj)
    db.flush()
    return obj


def khai_mot_dong(db, order, order_line) -> VatTuInAn:
    """Thành phẩm của MỘT dòng đơn."""
    return tim_hoac_khai(
        db,
        customer_id=order.customer_id,
        ten=order_line.description or "",
        dvt=order_line.don_vi_tinh,
        order_id=order.id,
        order_line_id=order_line.id,
    )


def khai_cho_don(db, order) -> list[VatTuInAn]:
    """Khai TOÀN BỘ dòng của một đơn. Gọi từ `OrderService.confirm()`.

    KHÔNG commit — `confirm()` commit chung một lượt (xem `tim_hoac_khai`).
    """
    if order is None or not order.customer_id:
        return []
    return [khai_mot_dong(db, order, ln) for ln in (order.lines or [])]
