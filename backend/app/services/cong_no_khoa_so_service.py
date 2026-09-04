"""Dịch vụ khóa sổ kỳ kế toán công nợ và báo cáo công nợ chi tiết."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from ..models.cong_no_khoa_so import (
    PHAN_HE_PHAI_THU,
    PHAN_HE_PHAI_TRA,
    CongNoKhoaSo,
    CongNoKyChot,
)
from ..repositories.cong_no_khoa_so_repo import CongNoKhoaSoRepository
from ..services.accounting_service import AccountingService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CongNoKhoaSoError(ValueError):
    """Thao tác khóa/mở kỳ không hợp lệ. Router dịch thành 422."""


class CongNoKhoaSoService:
    def __init__(self, db: Session, acct_svc: AccountingService | None = None) -> None:
        self.db = db
        self.repo = CongNoKhoaSoRepository(db)
        self.acct_svc = acct_svc

    def is_locked(self, ngay: date, phan_he: str | None = None) -> bool:
        return self.repo.is_locked(ngay, phan_he)

    def history(self, limit: int = 100, phan_he: str | None = None) -> list[dict]:
        from ..models.user import User
        users = {u.id: u.name for u in self.db.query(User).all()}
        rows = self.repo.history(limit, phan_he)
        return [
            {
                "id": r.id,
                "tu_ngay": r.tu_ngay,
                "den_ngay": r.den_ngay,
                "hanh_dong": r.hanh_dong,
                "nguoi_khoa_ten": users.get(r.nguoi_khoa_id),
                "khoa_luc": r.khoa_luc,
                "ten": r.ten,
                "phan_he": r.phan_he,
            }
            for r in rows
        ]

    def moc_chot_cuoi(self, phan_he: str | None = None) -> date | None:
        """Ngày CUỐI CÙNG đang bị khóa. `None` = chưa chốt kỳ nào.

        Là mốc để suy ra kỳ tiếp theo bắt đầu từ đâu — kỳ mới luôn nối ngay sau kỳ chốt trước,
        không được đè lên (chủ chốt 04/09/2026: *"đừng cho... trùng ngày đã chốt của kì trước"*).
        """
        rows = [r for r in self.repo.history(500, phan_he) if r.hanh_dong == "khoa"]
        if not rows:
            return None
        xa_nhat = max(r.den_ngay for r in rows)
        som_nhat = min(r.tu_ngay for r in rows)
        bi_khoa = self.repo.ngay_bi_khoa(som_nhat, xa_nhat, phan_he)
        return max(bi_khoa) if bi_khoa else None

    def list_ky(self, phan_he: str | None = None) -> list[dict]:
        """Danh sách KỲ KẾ TOÁN = những lần ĐÃ BẤM CHỐT, cộng kỳ hiện tại chưa chốt.

        Đổi hẳn cách dựng 04/09/2026 (chủ chốt: *"những kì mà mình bấm chốt"*). Trước đó hàm này
        tự đẻ ra 12 tháng lịch — mà kế toán ở đây chốt sổ theo kỳ TỰ ĐẶT, có tên riêng ("Chốt kì 1
        2026", 03/07–03/09). Hai cách đánh kỳ khác nhau nằm chung một màn chính là thứ đẻ ra mớ
        "Chốt một phần" không ai hiểu: kỳ báo cáo 01/09–04/09 (tháng lịch) chẳng bao giờ trùng kỳ
        đã chốt 01/09–03/09 (kỳ tự đặt).

        Bản ghi chốt đã bị MỞ LẠI (toàn phần) thì không còn là một kỳ nữa nên bị loại; mở lại một
        phần thì vẫn liệt kê, kèm cờ `khoa_mot_phan` để nói rõ nó đang hở.
        """
        ky_list: list[dict] = []
        da_thay: set[tuple[date, date]] = set()

        for r in self.repo.history(500, phan_he):
            if r.hanh_dong != "khoa":
                continue
            khoa = (r.tu_ngay, r.den_ngay)
            # Cùng một khoảng bấm chốt nhiều lần (đúng ca 01/09–03/09 bị bấm 4 lần vì màn hình
            # không báo gì) ⇒ chỉ giữ bản ghi MỚI NHẤT, đừng đổ ra bốn dòng y hệt nhau.
            if khoa in da_thay:
                continue
            da_thay.add(khoa)
            tron, mot_phan = self.repo.khoa_ca_khoang(r.tu_ngay, r.den_ngay, phan_he)
            if not tron and not mot_phan:
                continue                      # đã mở lại hoàn toàn — không còn là kỳ đã chốt
            ky_list.append({
                "tu_ngay": r.tu_ngay,
                "den_ngay": r.den_ngay,
                "ten": r.ten or f"Kỳ {r.tu_ngay:%d/%m/%Y}–{r.den_ngay:%d/%m/%Y}",
                "da_khoa": tron,
                "khoa_mot_phan": mot_phan,
                "dang_dien_ra": False,
                # Server nói luôn kỳ nào mở được, để giao diện MỜ nút thay vì cho bấm rồi ăn 422.
                "co_the_mo": self.ky_chan_mo(r.den_ngay, phan_he) is None,
                "khoa_luc": r.khoa_luc,
            })

        ky_list.sort(key=lambda k: k["den_ngay"], reverse=True)

        # KỲ HIỆN TẠI (chưa chốt) — luôn đứng đầu danh sách. Nối ngay sau ngày chốt cuối cùng;
        # chưa chốt kỳ nào thì lấy từ đầu năm. Có mục này thì kế toán xem được phần đang phát sinh
        # mà không phải gõ tay ngày nào.
        moc = self.moc_chot_cuoi(phan_he)
        today = date.today()
        tu_hien_tai = (moc + timedelta(days=1)) if moc else date(today.year, 1, 1)
        if tu_hien_tai <= today:
            ky_list.insert(0, {
                "tu_ngay": tu_hien_tai,
                "den_ngay": today,
                "ten": f"Kỳ hiện tại (chưa chốt) · {tu_hien_tai:%d/%m}–{today:%d/%m/%Y}",
                "da_khoa": False,
                "khoa_mot_phan": False,
                "dang_dien_ra": True,
                "co_the_mo": False,          # chưa chốt thì không có gì để mở
                "khoa_luc": None,
            })
        return ky_list

    def chot_ky(
        self, *, phan_he: str, tu_ngay: date, den_ngay: date, ten: str | None,
        user_id: int | None,
    ) -> CongNoKhoaSo:
        self._kiem_khoang(tu_ngay, den_ngay)
        self._kiem_chong_lan(tu_ngay, den_ngay, phan_he)
        ten_ky = ten or f"Tháng {tu_ngay.month:02d}/{tu_ngay.year}"
        log = self.repo.add_log(
            phan_he=phan_he,
            tu_ngay=tu_ngay,
            den_ngay=den_ngay,
            hanh_dong="khoa",
            nguoi_khoa_id=user_id,
            ten=ten_ky,
        )

        self.repo.delete_snapshots(tu_ngay, den_ngay, phan_he)
        snapshots: list[CongNoKyChot] = []

        if self.acct_svc and phan_he == PHAN_HE_PHAI_THU:
            # Snapshot phải thu
            rcv_rows = self.acct_svc._receivable_rows()
            for r in rcv_rows:
                inv_date = r.get("invoice_date")
                if inv_date and inv_date <= den_ngay:
                    con_no = r.get("remaining_amount", 0)
                    snapshots.append(
                        CongNoKyChot(
                            phan_he="phai_thu",
                            doi_tuong_id=r["customer_id"],
                            ref_type="sales_invoice",
                            ref_id=r["invoice_id"],
                            tu_ngay=tu_ngay,
                            den_ngay=den_ngay,
                            ten_ky=ten_ky,
                            tong_tien=r.get("amount", 0),
                            da_thanh_toan=r.get("received_amount", 0),
                            con_no=con_no,
                            is_settled=(con_no <= 0),
                        )
                    )

        if self.acct_svc and phan_he == PHAN_HE_PHAI_TRA:
            # Snapshot phải trả
            purchases_list = self.acct_svc.purchases.list_for_payables()
            for row in purchases_list:
                dots, coc, coc_du = self.acct_svc._no_tung_dot(row)
                for dot in dots:
                    d_date = dot.get("delivery_date")
                    if d_date and d_date <= den_ngay:
                        con_no = dot.get("con_no", 0)
                        snapshots.append(
                            CongNoKyChot(
                                phan_he="phai_tra",
                                doi_tuong_id=row.supplier_id,
                                ref_type="purchase_delivery",
                                ref_id=dot.get("delivery_id", 0),
                                tu_ngay=tu_ngay,
                                den_ngay=den_ngay,
                                ten_ky=ten_ky,
                                # Cùng lỗi tên khoá như bảng chi tiết, nhưng chỗ này NẶNG HƠN:
                                # nó GHI 0 vào snapshot chốt sổ, tức là đóng sổ xong thì sổ lưu
                                # lại giá trị đợt = 0 vĩnh viễn (04/09/2026).
                                tong_tien=int(dot.get("amount", 0) or 0),
                                da_thanh_toan=int(dot.get("paid", 0) or 0)
                                + int(dot.get("coc_bu", 0) or 0),
                                con_no=con_no,
                                is_settled=(con_no <= 0),
                            )
                        )

        if snapshots:
            self.repo.save_snapshots(snapshots)

        return log

    def _kiem_chong_lan(self, tu_ngay: date, den_ngay: date, phan_he: str | None = None) -> None:
        """Kỳ mới KHÔNG được đè lên ngày đã chốt (chủ chốt 04/09/2026).

        Kỳ kế toán phải nối nhau, không giẫm lên nhau: chốt lại một ngày đã chốt nghĩa là có hai
        kỳ cùng nhận một ngày, và số dư cuối kỳ này với đầu kỳ kia đếm trùng chứng từ. Muốn chốt
        lại thì MỞ kỳ cũ ra trước — thao tác đó có ghi lịch sử, còn đè âm thầm thì không.
        """
        trung = self.repo.ngay_bi_khoa(tu_ngay, den_ngay, phan_he)
        if not trung:
            return
        raise CongNoKhoaSoError(
            f"Khoảng này chồng lấn kỳ đã chốt ({min(trung):%d/%m/%Y}–{max(trung):%d/%m/%Y}). "
            f"Mở kỳ đó ra trước nếu muốn chốt lại."
        )

    @staticmethod
    def _kiem_khoang(tu_ngay: date, den_ngay: date) -> None:
        """Chặn khoảng ngược và chặn CHỐT SỔ CHO TƯƠNG LAI (sửa 04/09/2026).

        Chốt sổ nghĩa là "kỳ này đã xong, số đã chốt". Chốt tới 30/09 khi mới mùng 4 là đóng sổ
        cho 26 ngày chưa xảy ra: chứng từ ghi vào sau đó rơi vào kỳ đã khóa, và snapshot lưu lúc
        chốt thì rỗng — sổ nói đã chốt mà chẳng chốt cái gì.

        MỞ khóa thì KHÔNG chặn: gỡ một bản ghi lỡ tay tạo ra phải luôn làm được, kể cả khi nó trót
        phủ sang tương lai.
        """
        if den_ngay < tu_ngay:
            raise CongNoKhoaSoError("Ngày đến phải lớn hơn hoặc bằng ngày từ.")
        hom_nay = date.today()
        if den_ngay > hom_nay:
            raise CongNoKhoaSoError(
                f"Không chốt sổ cho ngày trong tương lai — hôm nay mới {hom_nay:%d/%m/%Y}."
            )

    def ky_chan_mo(
        self, den_ngay: date, phan_he: str | None = None
    ) -> tuple[date, date] | None:
        """Kỳ CHỐT nào ra đời sau `den_ngay` — nếu có thì kỳ này niêm vĩnh viễn.

        Xét trên LỊCH SỬ CHỐT, không phải trạng thái khóa hiện tại (chủ chốt 04/09/2026: *"đã tạo
        ra kì mới rồi thì không cho mở nữa"*). Nghĩa là mở kỳ sau ra rồi thì kỳ trước VẪN không mở
        được — sổ đã đóng là đóng, không có đường tháo ngược từng nấc.

        ⚠️ Hệ quả cố ý, ghi rõ ra: chốt nhầm kỳ 8 rồi lỡ chốt tiếp kỳ 9 thì kỳ 8 **không sửa được
        qua giao diện nữa**. Van an toàn duy nhất còn lại là kỳ MỚI NHẤT — chưa có kỳ nào sau nó
        thì vẫn mở thoải mái, nên chốt nhầm phát hiện ngay vẫn cứu được.

        Trả `(ngày đầu, ngày cuối)` của kỳ chốt SỚM NHẤT nằm sau; `None` = không có gì chặn.
        """
        sau = [
            r for r in self.repo.history(500, phan_he)
            if r.hanh_dong == "khoa" and r.den_ngay > den_ngay
        ]
        if not sau:
            return None
        r = min(sau, key=lambda x: (x.den_ngay, x.id))
        return (r.tu_ngay, r.den_ngay)

    def mo_ky(
        self, *, phan_he: str, tu_ngay: date, den_ngay: date, user_id: int | None
    ) -> CongNoKhoaSo:
        """Mở lại một kỳ đã chốt. CHỈ mở được kỳ MỚI NHẤT (chủ chốt 04/09/2026).

        *"Tôi chốt kì tháng 8, sau đó chốt kì tháng 9, thì thằng tháng 8 không cho mở nữa"* —
        đúng luật kế toán: số dư ĐẦU kỳ tháng 9 lấy từ số dư CUỐI kỳ tháng 8. Mở tháng 8 ra sửa
        trong khi tháng 9 đã chốt là rút gốc của một kỳ đã đóng.

        NIÊM VĨNH VIỄN, không phải tháo ngược từng nấc: mở kỳ 9 ra rồi thì kỳ 8 VẪN không mở được
        (chủ chốt: *"không cho luôn, đã tạo ra kì mới rồi thì không cho mở nữa"*). Van an toàn duy
        nhất là kỳ MỚI NHẤT — chưa có kỳ nào chốt sau nó thì mở thoải mái, nên chốt nhầm mà phát
        hiện ngay vẫn cứu được.
        """
        chan = self.ky_chan_mo(den_ngay, phan_he)
        if chan is not None:
            raise CongNoKhoaSoError(
                f"Kỳ này đã niêm: đã có kỳ chốt sau nó ({chan[0]:%d/%m/%Y}–{chan[1]:%d/%m/%Y}). "
                f"Sổ đã đóng thì không mở lại được nữa, kể cả khi kỳ sau đã được mở ra."
            )
        log = self.repo.add_log(
            phan_he=phan_he,
            tu_ngay=tu_ngay,
            den_ngay=den_ngay,
            hanh_dong="mo",
            nguoi_khoa_id=user_id,
            ten=None,
        )
        self.repo.delete_snapshots(tu_ngay, den_ngay, phan_he)
        return log

    def cong_no_chi_tiet_phai_thu(
        self,
        *,
        tu_ngay: date | None = None,
        den_ngay: date | None = None,
        customer_id: int | None = None,
    ) -> list[dict]:
        from ..models.customer import Customer
        customers_query = self.db.query(Customer)
        if customer_id:
            customers_query = customers_query.filter(Customer.id == customer_id)
        customers = {c.id: c for c in customers_query.all()}

        rows = self.acct_svc._receivable_rows(customer_id=customer_id) if self.acct_svc else []
        if den_ngay:
            rows = [r for r in rows if r["invoice_date"] and r["invoice_date"] <= den_ngay]

        by_customer: dict[int, list[dict]] = {}
        for r in rows:
            cid = r["customer_id"]
            by_customer.setdefault(cid, []).append(r)

        out = []
        for cid, cust in customers.items():
            c_rows = by_customer.get(cid, [])
            if not c_rows:
                continue
            total_due = sum(r["remaining_amount"] for r in c_rows)
            overdue_amount = sum(
                r["remaining_amount"]
                for r in c_rows
                if r["due_date"] and (den_ngay or date.today()) > r["due_date"] and r["remaining_amount"] > 0
            )
            out.append({
                "customer_id": cid,
                "customer_code": cust.code,
                "customer_name": cust.name,
                "credit_limit": int(cust.credit_limit or 0),
                "total_due": total_due,
                "overdue_amount": overdue_amount,
                "items": c_rows,
            })
        out.sort(key=lambda x: x["total_due"], reverse=True)
        return out

    def cong_no_chi_tiet_phai_tra(
        self,
        *,
        tu_ngay: date | None = None,
        den_ngay: date | None = None,
        supplier_id: int | None = None,
    ) -> list[dict]:
        from ..models.purchase import Supplier
        suppliers_query = self.db.query(Supplier)
        if supplier_id:
            suppliers_query = suppliers_query.filter(Supplier.id == supplier_id)
        suppliers = {s.id: s for s in suppliers_query.all()}

        by_supplier: dict[int, list[dict]] = {}
        moc_tre = den_ngay or date.today()
        if self.acct_svc:
            purchases_list = self.acct_svc.purchases.list_for_payables(supplier_id=supplier_id)
            for row in purchases_list:
                dots, coc, coc_du = self.acct_svc._no_tung_dot(row)
                for dot in dots:
                    d_date = dot.get("delivery_date")
                    if den_ngay and d_date and d_date > den_ngay:
                        continue
                    # ⚠️ TÊN KHOÁ phải khớp `_no_tung_dot`, nó trả `amount / paid / coc_bu /
                    # con_no / seq_no` — KHÔNG có `delivery_value`, `paid_amount`,
                    # `delivery_code`, `overdue_days`. Bản đầu hỏi mấy tên không tồn tại rồi để
                    # `.get(..., 0)` nuốt gọn, nên màn hình hiện "Giá trị đợt 0đ · Đã trả 0đ ·
                    # Còn nợ 1.305.000.000đ" — ba cột cạnh nhau mà không trừ ra nhau (04/09/2026).
                    #
                    # ĐÃ TRẢ = trả đích danh + CỌC BÙ xuống. Thiếu `coc_bu` thì đợt được cọc phủ
                    # hiện "Giá trị 100 · Đã trả 0 · Còn nợ 0", lại vô lý y như cũ.
                    tien_dot = int(dot.get("amount", 0) or 0)
                    coc_bu = int(dot.get("coc_bu", 0) or 0)
                    da_tra = int(dot.get("paid", 0) or 0) + coc_bu
                    han = dot.get("due_date")
                    by_supplier.setdefault(row.supplier_id, []).append({
                        "delivery_id": dot.get("delivery_id"),
                        # Số ĐỢT TRONG ĐƠN, không phải id bản ghi. Giao diện lùi về
                        # `Đợt #{delivery_id}` khi thiếu, nên đợt đầu tiên của một NCC hiện thành
                        # "Đợt #20" chỉ vì id nó là 20.
                        "seq_no": dot.get("seq_no"),
                        "delivery_code": None,
                        "delivery_date": dot.get("delivery_date"),
                        "purchase_request_id": row.id,
                        "purchase_request_code": row.code,
                        "delivery_value": tien_dot,
                        "paid_amount": da_tra,
                        "coc_bu": coc_bu,
                        "con_no": int(dot.get("con_no", 0) or 0),
                        "due_date": han,
                        # Trễ tính TẠI MỐC ĐANG XEM, không phải luôn theo hôm nay — báo cáo kỳ cũ
                        # phải in lại ra đúng con số cũ.
                        "overdue_days": (
                            (moc_tre - han).days if han and moc_tre > han else 0
                        ),
                    })

        out = []
        for sid, supp in suppliers.items():
            s_rows = by_supplier.get(sid, [])
            if not s_rows:
                continue
            total_due = sum(r.get("con_no", 0) for r in s_rows)
            overdue_amount = sum(
                r.get("con_no", 0)
                for r in s_rows
                if r.get("due_date") and (den_ngay or date.today()) > r["due_date"] and r.get("con_no", 0) > 0
            )
            out.append({
                "supplier_id": sid,
                "supplier_code": supp.code,
                "supplier_name": supp.name,
                "credit_limit": int(supp.credit_limit or 0),
                "total_due": total_due,
                "overdue_amount": overdue_amount,
                "items": s_rows,
            })
        out.sort(key=lambda x: x["total_due"], reverse=True)
        return out
