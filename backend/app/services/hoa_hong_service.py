"""Hoa hồng kinh doanh — MỘT chỗ duy nhất giữ công thức.

Nền: `docs/redesign-luong-kinh-doanh.md` §4.6, có HAI điểm chủ dự án chốt khác spec (21/08/2026):

1. **MỐC sinh hoa hồng = lúc RA CÔNG NỢ PHẢI THU**, tức khi hoá đơn bán được ghi nhận
   (`sales_invoices` — docstring của model đó ghi đúng chữ "mốc làm phát sinh công nợ phải thu").
   Spec §4.6 chọn mốc *thu được tiền* ("mở dần theo tiền thu"). Chủ chốt đổi sang mốc công nợ.

   ⚠️ Hệ quả phải biết: hoa hồng trả TRƯỚC khi tiền về. Khách nợ xấu thì tiền đã chi rồi, đòi lại
   phải qua kỳ lương sau. Muốn quay lại mốc "thu được tiền" thì sửa ĐÚNG hàm `_moc_phat_sinh`
   phía dưới — cả engine chỉ đọc qua đó.

2. **GỐC tính = TRƯỚC VAT**, quy đổi theo tỷ lệ. Spec tự mâu thuẫn: dòng 149 ghi
   `= Σ payments(đơn) × %` (tức có VAT), dòng 259 ghi "giá trị đơn cho hoa hồng: mặc định trước
   VAT". Chủ chọn TRƯỚC VAT — VAT là tiền thu hộ nhà nước, trả hoa hồng trên đó là trả trên tiền
   không phải của công ty.

Công thức:

    Hoa hồng(NV, kỳ) = Σ  hoá_đơn.amount_vnd × tỷ_lệ_trước_VAT(đơn) × commission_pct(đơn)
                      hoá đơn ISSUED, invoice_date trong kỳ, đơn có sale_user_id = NV

    tỷ_lệ_trước_VAT(đơn) = Σ line_total / tổng_có_VAT      (1.0 nếu đơn không có VAT)

`order_lines.line_total` là NET **trước VAT, sau chiết khấu** — xem `order_service.py` chỗ tính
`net_line = final_amount − vat_amount`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from ..models.accounting import SALES_INVOICE_ISSUED, SalesInvoice
from ..models.employee import Employee
from ..models.order import Order


class HoaHongService:
    """Tính hoa hồng kinh doanh của một nhân viên trong một kỳ.

    KHÔNG ghi gì — chỉ đọc và trả số. Nơi ghi là `PayrollService` (khoản danh mục nguồn `auto`).
    """

    def __init__(self, db) -> None:
        self.db = db

    # ---------------------------------------------------------------- mốc phát sinh
    def _moc_phat_sinh(self, tu_ngay: date, den_ngay: date):
        """Các chứng từ làm PHÁT SINH hoa hồng trong kỳ. Trả `[(order_id, số tiền có VAT)]`.

        Đổi chính sách thì sửa DUY NHẤT hàm này:
          · mốc công nợ (đang dùng)  → hoá đơn `issued` trong kỳ;
          · mốc tiền về (spec §4.6)  → `payment_receipts` `received` trong kỳ, gộp cả `order_id`
            lẫn `sales_invoice_id`.
        """
        rows = self.db.execute(
            select(SalesInvoice.order_id, SalesInvoice.amount_vnd).where(
                SalesInvoice.status == SALES_INVOICE_ISSUED,
                SalesInvoice.invoice_date >= tu_ngay,
                SalesInvoice.invoice_date <= den_ngay,
            )
        ).all()
        return [(int(r[0]), int(r[1] or 0)) for r in rows if r[0]]

    # ---------------------------------------------------------------- quy đổi trước VAT
    def _ty_le_truoc_vat(self, order: Order) -> float:
        """`tổng trước VAT / tổng có VAT` của đơn. 1.0 khi đơn không có VAT hoặc chưa có số.

        Quy đổi theo TỶ LỆ chứ không trừ thẳng VAT của hoá đơn: một đơn có thể xuất nhiều hoá đơn
        từng phần, mỗi hoá đơn chỉ là một mẩu — nhân tỷ lệ giữ đúng phần trước VAT của mẩu đó.
        """
        truoc = sum(int(l.line_total or 0) for l in (order.lines or []))
        if truoc <= 0:
            return 1.0
        co_vat = sum(
            int(l.line_total or 0) * (100 + int(l.vat_pct_estimate or 0)) / 100.0
            for l in order.lines
        )
        if co_vat <= 0:
            return 1.0
        return truoc / co_vat

    # ---------------------------------------------------------------- API
    def hoa_hong_ky(self, employee_id: int, *, tu_ngay: date, den_ngay: date) -> float:
        """Tiền hoa hồng của MỘT nhân viên trong kỳ `[tu_ngay, den_ngay]`. 0 nếu không có.

        Nhân viên nối với đơn qua `employees.user_id` ↔ `orders.sale_user_id`: đơn ghi USER, còn
        bảng lương chạy theo EMPLOYEE. Nhân viên chưa có tài khoản thì không thể là sales của đơn
        nào, nên trả 0 sớm.
        """
        emp = self.db.get(Employee, int(employee_id))
        uid = getattr(emp, "user_id", None)
        if not uid:
            return 0.0

        moc = self._moc_phat_sinh(tu_ngay, den_ngay)
        if not moc:
            return 0.0

        # Nạp MỘT lượt các đơn có liên quan — mỗi hoá đơn tra một đơn là N+1 ngay giữa vòng tính
        # lương của cả trăm người.
        ids = sorted({oid for oid, _ in moc})
        don = {
            o.id: o for o in self.db.execute(
                select(Order).where(Order.id.in_(ids), Order.sale_user_id == int(uid))
            ).scalars()
        }
        if not don:
            return 0.0

        tong = 0.0
        for oid, tien_co_vat in moc:
            o = don.get(oid)
            if o is None:
                continue                      # đơn của người khác
            pct = float(o.commission_pct or 0)
            if pct <= 0:
                continue                      # đơn không có hoa hồng
            tong += tien_co_vat * self._ty_le_truoc_vat(o) * pct
        return round(tong)
