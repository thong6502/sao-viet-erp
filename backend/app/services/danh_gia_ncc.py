"""SAO NHÀ CUNG CẤP — máy tự tính từ dữ liệu đã có, KHÔNG ai chấm tay.

Vì sao không có ô chấm điểm: điểm gõ tay là ý kiến, mà ý kiến thì không đối chiếu được với chứng
từ. Ở đây sao suy thẳng từ hai ngày CÓ SẴN trên phiếu mua hàng, nên mọi con số đều truy ngược
được về một đơn cụ thể — cãi nhau với NCC thì mở đơn đó ra xem.

MỐC HẸN = `purchase_requests.needed_date` (Ngày cần hàng). CHỈ MỘT Ô, KHÔNG fallback.
    Chủ chốt (26/08/2026): lấy NGÀY NHÀ MÁY CẦN HÀNG làm chuẩn — trễ ngày đó là trễ thật, bất kể
    NCC hẹn gì. Đừng "sửa lại cho đúng" thành `expected_receipt_date` hay COALESCE hai cột:
    `needed_date` có 19/19 = 100% dữ liệu, `expected_receipt_date` chỉ 10/19 = 53%, và ngày NCC
    tự hẹn thì chính NCC dời được — lấy nó làm thước là để họ tự chấm điểm mình.
    Đơn KHÔNG có `needed_date` ⇒ BỎ khỏi sổ điểm (không coi là 5 sao, cũng không coi là 0).

NGÀY CHỐT = ngày giao cuối cùng `max(purchase_deliveries.delivery_date)` với đơn đã nhận đủ;
    đơn CHƯA nhận đủ thì chốt tới HÔM NAY — nếu không, NCC ôm hàng không giao sẽ mãi không bị trừ
    điểm, càng chây ì càng sạch sổ.

⚠️ `None` KHÁC `0`. `rating=None` = CHƯA ĐÁNH GIÁ (chưa có đơn nào đủ điều kiện); `0` sẽ đọc thành
"tệ nhất". Vu oan cho NCC mới là lỗi nặng hơn cả tính sai sao — cùng luật với guard "im lặng ≠ 0đ"
ở màn Công nợ. Thang sao thấp nhất là 1, KHÔNG BAO GIỜ có 0 sao.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.purchase import NGUONG_SAO_NCC, SAO_THAP_NHAT


def sao_tu_so_ngay_tre(so_ngay_tre: float) -> int:
    """Số ngày trễ → số sao. Trễ ÂM (giao sớm) và 0 đều là đúng hẹn ⇒ 5 sao.

    Đây là bản Python của đúng cái thang mà `SupplierRepository._bang_danh_gia()` dựng thành CASE
    trong SQL. Hai đường phải ra CÙNG một số — `test_danh_gia_ncc.py` canh chỗ này.
    """
    for tran, diem in NGUONG_SAO_NCC:
        if so_ngay_tre <= tran:
            return diem
    return SAO_THAP_NHAT


@dataclass(frozen=True)
class DanhGiaNcc:
    """Sổ điểm của MỘT nhà cung cấp, đã gộp toàn bộ lịch sử."""

    #: Trung bình sao, làm tròn 1 chữ số thập phân. `None` = CHƯA ĐÁNH GIÁ — đừng ép thành 0.
    rating: float | None
    #: Số đơn ĐƯỢC TÍNH (không phải tổng số đơn của NCC).
    rating_count: int
    on_time_count: int
    late_count: int
    #: Trễ trung bình, tính TRÊN CÁC ĐƠN TRỄ (không chia cho cả đơn đúng hẹn — chia thế thì NCC
    #: giao 100 đơn đúng hẹn + 1 đơn trễ 30 ngày sẽ hiện "trễ TB 0,3 ngày", nghe như không có gì).
    #: `None` = chưa trễ đơn nào.
    avg_late_days: float | None


#: Trạng thái của NCC chưa có đơn nào đủ điều kiện. Dùng chung một thể để không ai lỡ tay gõ 0.
CHUA_DANH_GIA = DanhGiaNcc(
    rating=None, rating_count=0, on_time_count=0, late_count=0, avg_late_days=None
)


def tu_tong_hop(tho: dict | None) -> DanhGiaNcc:
    """Số thô đã gộp sẵn ở DB → sổ điểm hiển thị được.

    `tho=None` hoặc không có đơn nào ⇒ CHƯA ĐÁNH GIÁ. Đây là cửa DUY NHẤT sinh ra `DanhGiaNcc`,
    nên luật "`None` chứ không phải 0" chỉ cần đúng ở một chỗ.
    """
    if not tho:
        return CHUA_DANH_GIA
    so_don = int(tho.get("so_don") or 0)
    if so_don <= 0:
        return CHUA_DANH_GIA
    so_tre = int(tho.get("so_tre") or 0)
    tong_ngay_tre = float(tho.get("tong_ngay_tre") or 0)
    return DanhGiaNcc(
        rating=round(float(tho["sao_tb"]), 1),
        rating_count=so_don,
        on_time_count=int(tho.get("so_dung_hen") or 0),
        late_count=so_tre,
        avg_late_days=round(tong_ngay_tre / so_tre, 1) if so_tre else None,
    )
