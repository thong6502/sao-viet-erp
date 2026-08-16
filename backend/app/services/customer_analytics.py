"""CRM-360 analytics — spec-06 (Khách hàng "hub of information").

All figures here are COMPUTED FROM REAL ROWS in the same app (``orders`` + ``order_lines``
+ ``quotations``) — never fabricated. When a customer has no orders/quotations the numbers
come back as honest zeros / empty series and the frontend renders an explicit empty state
(§PRODUCT_SENSE #4: "thà trống trung thực còn hơn số giả").

Two surfaces:
  - **List analytics** (:class:`CustomerListStats`): the KPI header strip (tổng KH · thân
    thiết · KH mới trong tháng · TB đơn) + a per-customer derived tier / LTV / order-count,
    all rolled up over the scoped set in ONE pass (no N+1).
  - **Detail analytics** (:class:`CustomerDashboard`): the Object-page Dashboard — doanh số
    12 tháng (bar), số đơn 12T, TB/đơn, công nợ (SEAM-16 read-only), cơ cấu sản phẩm (donut
    from order-line descriptions), tần suất đặt (heatmap 12T × weekday) — plus the two history
    tables (Lịch sử mua hàng from orders, Lịch sử báo giá from quotations).

Tier is a *behavioural* classification derived from real history (spend + tenure + recency),
NOT an invented master field — the domain (§DOMAIN L333) only speaks of "khách VIP" for the
volume discount, so a spend-based tier is the honest, data-grounded reading:
  - ``new``      — mới tạo trong 30 ngày HOẶC chưa có đơn nào.
  - ``loyal``    — doanh số 12T ≥ ``LOYAL_REVENUE_VND`` (khách thân thiết / VIP theo chi tiêu).
  - ``partner``  — khách từ > 365 ngày trước và có ≥1 đơn (đối tác lâu năm).
  - ``regular``  — còn lại (đang giao dịch, chưa đạt ngưỡng thân thiết).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.customer import Customer
from ..models.order import STATUS_CANCELLED as ORDER_CANCELLED
from ..models.order import Order, OrderLine
from ..models.phieu_tinh_gia import PhieuThanhPhan, PhieuThanhPham
from ..models.quotation import STATUS_CANCELLED as QUOTE_CANCELLED
from ..models.quotation import Quote, QuoteVersion
from ..models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen

# Redesign spec-06 v2: BỎ tier (tự phân loại thân thiết/đối tác/mới) — thay bằng thẻ gán tay.
# Chỉ giữ số THẬT (doanh số / số đơn / recency) cho danh sách + dashboard.

# Orders in these statuses are excluded from realised revenue (đã hủy).
_EXCLUDED_ORDER_STATUSES = (ORDER_CANCELLED,)

# --- TỈ LỆ CHỐT: định nghĩa "thắng" và "đã chào" ở ĐÚNG MỘT CHỖ ---------------------------
#
# Sửa 16/08/2026 — bản cũ đếm sai CẢ HAI CHIỀU và cho ra con số bôi nhọ chính mình:
#   · BỎ SÓT `converted_to_order` ("Đã lên đơn — khoá 1 báo giá = 1 đơn"). Đây là thắng CHẮC
#     CHẮN, đã thành đơn hàng rồi. Khách An Phát có 11 báo giá loại này ⇒ màn hình ghi tỉ lệ
#     chốt 18% trong khi thực tế 88%.
#   · TÍNH NHẦM `approved` là thắng. Trạng thái đó nghĩa là "GĐ Kinh doanh duyệt xong, CHỜ sale
#     gửi khách" — khách còn chưa nhìn thấy báo giá.
#
# MẪU SỐ chỉ gồm báo giá khách ĐÃ THẤY. Loại `draft` / `pending_approval` / `approved` (chưa ra
# khỏi cửa) và `cancelled` (mình tự huỷ, không phải khách chê) — để trong mẫu số là tự trừ điểm
# vì những việc khách chưa hề biết. Báo giá `sent` đang chờ trả lời thì VẪN tính: đã chào mà
# chưa chốt được thì chưa phải thắng.
CHOT_THANG = ("accepted", "converted_to_order")
CHOT_DA_CHAO = ("sent", "accepted", "rejected", "expired", "converted_to_order")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


# Bốn mã mực PROCESS cố định (xem `PhieuThanhPhan.muc_a`); mọi mã khác là màu PHA.
_PROCESS_INKS = {"C", "M", "Y", "K"}

# Khổ ISO thông dụng (rộng×dài, mm) để gọi tên khổ thành phẩm thay vì đọc số mm.
_ISO_SIZES: dict[tuple[int, int], str] = {
    (74, 105): "A7",
    (105, 148): "A6",
    (148, 210): "A5",
    (210, 297): "A4",
    (297, 420): "A3",
    (420, 594): "A2",
}
_ISO_TOLERANCE_MM = 3


def _mau_label(muc_a, muc_b, so_mau_a: int, so_mau_b: int, so_mau_pha: int) -> str | None:
    """Cấu hình màu của 1 sản phẩm → nhãn đọc được ("5 màu (CMYK + 1 pha)").

    Số màu = số KẼM = |A ∪ B| (tự trở/trở nhíp dùng chung bộ bản). Phiếu đời cũ chưa có
    `muc_a`/`muc_b` thì lùi về ba cột dẫn xuất `so_mau_a/b/pha` — kém chính xác hơn (không biết
    mực hai mặt có trùng mã không) nhưng còn hơn bỏ trống.
    """
    a = {str(x).strip().upper() for x in (muc_a or []) if str(x).strip()}
    b = {str(x).strip().upper() for x in (muc_b or []) if str(x).strip()}
    ink = a | b
    if ink:
        process = len(ink & _PROCESS_INKS)
        pha = len(ink - _PROCESS_INKS)
    else:
        process = max(int(so_mau_a or 0), int(so_mau_b or 0))
        pha = int(so_mau_pha or 0)
    tong = process + pha
    if tong <= 0:
        return None
    if process == 4 and pha == 0:
        return "4 màu (CMYK)"
    if process == 4:
        return f"{tong} màu (CMYK + {pha} pha)"
    if pha == 0:
        return f"{process} màu"
    if process == 0:
        return f"{pha} màu pha"
    return f"{tong} màu ({process} process + {pha} pha)"


def _kho_label(rong_mm: int, dai_mm: int) -> str | None:
    """Khổ thành phẩm (mm) → tên khổ ISO nếu khớp trong sai số 3mm, không thì "210×297 mm"."""
    if not rong_mm or not dai_mm:
        return None
    ngan, dai = sorted((int(rong_mm), int(dai_mm)))
    for (w, h), name in _ISO_SIZES.items():
        if abs(ngan - w) <= _ISO_TOLERANCE_MM and abs(dai - h) <= _ISO_TOLERANCE_MM:
            return name
    return f"{ngan}×{dai} mm"


@dataclass
class CustomerStat:
    """Per-customer derived numbers for a list row (all from real orders)."""

    customer_id: int
    revenue_12m: int = 0
    orders_12m: int = 0
    orders_total: int = 0
    last_order_at: date | None = None


@dataclass
class CustomerListStats:
    total_customers: int = 0
    new_this_month: int = 0
    avg_order_value: int = 0        # TB/đơn trên toàn tập scoped (0 nếu chưa có đơn)
    total_revenue: int = 0
    per_customer: dict[int, CustomerStat] = field(default_factory=dict)


@dataclass
class MonthPoint:
    month: str          # "YYYY-MM"
    label: str          # "T7" (tháng 7)
    revenue: int
    orders: int


@dataclass
class ProductSlice:
    label: str
    revenue: int
    orders: int


@dataclass
class PrintSpec:
    """1 dòng "Thông số in thường đặt" — giá trị HAY GẶP NHẤT trên các phiếu tính giá của khách.

    `pct` = tỉ lệ % sản phẩm (dòng `phieu_thanh_phan`) khớp giá trị này, tính trên số sản phẩm CÓ
    khai thông số đó — không phải trên toàn bộ. Phiếu cũ bỏ trống giấy thì nó không kéo tụt % giấy
    của những phiếu có khai.
    """

    key: str            # giay | mau | gia_cong | kho
    label: str          # nhãn hiển thị ("Giấy hay dùng")
    value: str          # giá trị hay gặp ("Couché 300gsm")
    pct: int            # 0..100


@dataclass
class HeatCell:
    month_index: int    # 0..11 (oldest→newest, aligns with revenue_12m order)
    weekday: int        # 0=Mon .. 6=Sun
    count: int


@dataclass
class OrderLineBrief:
    """1 dòng của đơn: tên sản phẩm + TIỀN THẬT của chính dòng đó."""

    description: str
    line_total: int


@dataclass
class OrderHistoryRow:
    id: int
    order_no: str
    status: str
    order_kind: str
    summary: str        # mô tả gộp các dòng đơn (đối ngoại), "SP A, SP B"
    # Từng dòng kèm tiền. Thêm 16/08/2026 vì khối "Sản phẩm mua nhiều nhất" trước đây chỉ có
    # `summary` (chuỗi nối) nên frontend phải tách theo dấu phẩy rồi CHIA ĐỀU tổng đơn cho số
    # phần — đơn 21,5 Mđ gồm "Ruột sách 160 trang, Bìa sách, Thẻ nhân viên" bị gán mỗi thứ
    # 7,17 Mđ, dù ruột sách đắt hơn thẻ nhân viên nhiều lần. Tiền thật vốn nằm sẵn ở
    # `order_lines.line_total`, chỉ là không được trả xuống.
    lines: list[OrderLineBrief]
    total: int | None
    created_at: datetime


@dataclass
class QuoteHistoryRow:
    id: int
    code: str
    version: int
    status: str
    total: int | None
    valid_until: date | None
    created_at: datetime


@dataclass
class CustomerDashboard:
    revenue_12m: int
    orders_12m: int
    avg_order_value: int | None
    orders_total: int
    quotes_total: int
    win_rate_pct: int | None        # đơn / báo giá đã gửi (tỉ lệ chốt), None nếu chưa có BG
    first_order_at: date | None
    last_order_at: date | None
    months: list[MonthPoint]
    product_mix: list[ProductSlice]
    heatmap: list[HeatCell]
    has_data: bool
    # Thông số in thường đặt — rỗng khi khách chưa có phiếu tính giá nào (UI ẩn hẳn card).
    print_specs: list[PrintSpec] = field(default_factory=list)
    print_specs_phieu: int = 0      # số phiếu tính giá làm cơ sở (hiện dưới nhãn card)


class CustomerAnalyticsService:
    """Read-only analytics over the live sales tables. Framework-agnostic (takes a Session)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- list roll-up -------------------------------------------------------

    def list_stats(self, customers: list[Customer]) -> CustomerListStats:
        """Roll up KPIs + per-customer tier over the given (already scoped+paged? no —
        WHOLE scoped set for the header) list of customers, in a bounded number of
        queries. `customers` should be the full scoped set so the KPI strip reflects the
        whole book, not just the current page."""
        stats = CustomerListStats(total_customers=len(customers))
        if not customers:
            return stats

        ids = [c.id for c in customers]
        since = _utcnow() - timedelta(days=365)

        # Realised revenue + order count per customer over trailing 12 months (non-cancelled).
        rev_rows = self.db.execute(
            select(
                Order.customer_id,
                func.coalesce(func.sum(OrderLine.line_total), 0),
                func.count(func.distinct(Order.id)),
            )
            .join(OrderLine, OrderLine.order_id == Order.id)
            .where(
                Order.customer_id.in_(ids),
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
                Order.created_at >= since,
            )
            .group_by(Order.customer_id)
        ).all()
        rev_by_cust: dict[int, tuple[int, int]] = {
            cid: (int(rev or 0), int(cnt or 0)) for cid, rev, cnt in rev_rows
        }

        # Total order count + last order date per customer (all time, non-cancelled).
        tot_rows = self.db.execute(
            select(
                Order.customer_id,
                func.count(func.distinct(Order.id)),
                func.max(Order.created_at),
            )
            .where(
                Order.customer_id.in_(ids),
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
            )
            .group_by(Order.customer_id)
        ).all()
        tot_by_cust: dict[int, tuple[int, date | None]] = {
            cid: (int(cnt or 0), _as_date(last) if last else None)
            for cid, cnt, last in tot_rows
        }

        now = _utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total_rev_12m = 0
        total_orders_12m = 0
        for c in customers:
            rev_12m, orders_12m = rev_by_cust.get(c.id, (0, 0))
            orders_total, last_order = tot_by_cust.get(c.id, (0, None))
            stats.per_customer[c.id] = CustomerStat(
                customer_id=c.id,
                revenue_12m=rev_12m,
                orders_12m=orders_12m,
                orders_total=orders_total,
                last_order_at=last_order,
            )
            created = c.created_at
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created is not None and created >= month_start:
                stats.new_this_month += 1
            total_rev_12m += rev_12m
            total_orders_12m += orders_12m

        stats.avg_order_value = (
            round(total_rev_12m / total_orders_12m) if total_orders_12m else 0
        )
        stats.total_revenue = total_rev_12m
        return stats

    # --- detail dashboard ---------------------------------------------------

    def dashboard(self, customer: Customer) -> CustomerDashboard:
        now = _utcnow()
        cid = customer.id

        # 12-month window aligned to calendar months (oldest → newest).
        months: list[tuple[int, int]] = []  # (year, month)
        y, m = now.year, now.month
        for _ in range(12):
            months.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        months.reverse()
        index_of: dict[tuple[int, int], int] = {ym: i for i, ym in enumerate(months)}

        # All non-cancelled orders for this customer with line totals + created_at.
        order_rows = self.db.execute(
            select(
                Order.id,
                Order.created_at,
                func.coalesce(func.sum(OrderLine.line_total), 0),
            )
            .join(OrderLine, OrderLine.order_id == Order.id, isouter=True)
            .where(
                Order.customer_id == cid,
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
            )
            .group_by(Order.id, Order.created_at)
        ).all()

        revenue_by_month = [0] * 12
        orders_by_month = [0] * 12
        heat: dict[tuple[int, int], int] = {}
        revenue_12m = 0
        orders_12m = 0
        orders_total = 0
        first_order_at: date | None = None
        last_order_at: date | None = None
        for _oid, created, total in order_rows:
            orders_total += 1
            created_dt = created
            if isinstance(created_dt, datetime) and created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            d = _as_date(created)
            if first_order_at is None or d < first_order_at:
                first_order_at = d
            if last_order_at is None or d > last_order_at:
                last_order_at = d
            key = (d.year, d.month)
            idx = index_of.get(key)
            if idx is not None:
                revenue_by_month[idx] += int(total or 0)
                orders_by_month[idx] += 1
                revenue_12m += int(total or 0)
                orders_12m += 1
                heat_key = (idx, d.weekday())
                heat[heat_key] = heat.get(heat_key, 0) + 1

        month_points = [
            MonthPoint(
                month=f"{yy:04d}-{mm:02d}",
                label=f"T{mm}",
                revenue=revenue_by_month[i],
                orders=orders_by_month[i],
            )
            for i, (yy, mm) in enumerate(months)
        ]
        heatmap = [
            HeatCell(month_index=mi, weekday=wd, count=cnt)
            for (mi, wd), cnt in sorted(heat.items())
        ]

        # Cơ cấu sản phẩm (donut): group non-cancelled order lines by description over 12T.
        since = now - timedelta(days=365)
        mix_rows = self.db.execute(
            select(
                OrderLine.description,
                func.coalesce(func.sum(OrderLine.line_total), 0),
                func.count(OrderLine.id),
            )
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                Order.customer_id == cid,
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
                Order.created_at >= since,
            )
            .group_by(OrderLine.description)
            .order_by(func.coalesce(func.sum(OrderLine.line_total), 0).desc())
        ).all()
        product_mix = [
            ProductSlice(
                label=(desc or "Khác").strip() or "Khác",
                revenue=int(rev or 0),
                orders=int(cnt or 0),
            )
            for desc, rev, cnt in mix_rows
            if int(rev or 0) > 0
        ]

        # Quotation totals (đã gửi trở lên) for the win-rate + count.
        quotes_total = self.db.execute(
            select(func.count(Quote.id)).where(Quote.customer_id == cid)
        ).scalar_one()
        da_chao = self.db.execute(
            select(func.count(Quote.id)).where(
                Quote.customer_id == cid, Quote.status.in_(CHOT_DA_CHAO),
            )
        ).scalar_one()
        thang = self.db.execute(
            select(func.count(Quote.id)).where(
                Quote.customer_id == cid, Quote.status.in_(CHOT_THANG),
            )
        ).scalar_one()

        avg_order_value = round(revenue_12m / orders_12m) if orders_12m else None
        # Cả tử lẫn mẫu đều là SỐ BÁO GIÁ. Bản cũ lấy `orders_total / sent_quotes` — số ĐƠN chia
        # cho số BÁO GIÁ, hai đại lượng khác loại, nên một đơn tách làm hai báo giá (hoặc một
        # báo giá đẻ hai đơn) là tỉ lệ vọt qua 100%.
        win_rate = round(thang / da_chao * 100) if da_chao else None
        has_data = orders_total > 0 or quotes_total > 0
        print_specs, print_specs_phieu = self.print_specs(cid)

        return CustomerDashboard(
            revenue_12m=revenue_12m,
            orders_12m=orders_12m,
            avg_order_value=avg_order_value,
            orders_total=orders_total,
            quotes_total=quotes_total,
            win_rate_pct=win_rate,
            first_order_at=first_order_at,
            last_order_at=last_order_at,
            months=month_points,
            product_mix=product_mix,
            heatmap=heatmap,
            has_data=has_data,
            print_specs=print_specs,
            print_specs_phieu=print_specs_phieu,
        )

    # --- thông số in thường đặt ---------------------------------------------

    def print_specs(self, customer_id: int) -> tuple[list[PrintSpec], int]:
        """Giấy · số màu · gia công · khổ mà khách này HAY đặt, đọc từ phiếu tính giá thật.

        Chuỗi dữ liệu: `quotes.customer_id` → `quotes.phieu_tinh_gia_id` → `phieu_thanh_phan`
        (giấy · mực · khổ thành phẩm) → `phieu_thanh_pham` (bước gia công). Đơn vị đếm là SẢN PHẨM
        (1 phiếu nhiều sản phẩm: ruột · bìa…) vì thông số khai ở tầng đó.

        Báo giá đã HUỶ bị loại; các trạng thái khác đều tính — card trả lời "khách quen in gì",
        tức nhu cầu, nên báo giá khách chưa chốt vẫn là tín hiệu thật. Trả `([], 0)` khi khách chưa
        có phiếu nào ⇒ UI ẩn card thay vì bịa số.
        """
        ptg_ids = [
            pid
            for (pid,) in self.db.execute(
                select(Quote.phieu_tinh_gia_id)
                .where(
                    Quote.customer_id == customer_id,
                    Quote.phieu_tinh_gia_id.is_not(None),
                    Quote.status != QUOTE_CANCELLED,
                )
                .distinct()
            ).all()
        ]
        if not ptg_ids:
            return [], 0

        sp_rows = self.db.execute(
            select(
                PhieuThanhPhan.id,
                PhieuThanhPhan.giay_id,
                PhieuThanhPhan.kho_nguyen,
                PhieuThanhPhan.muc_a,
                PhieuThanhPhan.muc_b,
                PhieuThanhPhan.so_mau_a,
                PhieuThanhPhan.so_mau_b,
                PhieuThanhPhan.so_mau_pha,
                PhieuThanhPhan.rong_thanh_pham,
                PhieuThanhPhan.dai_thanh_pham,
            ).where(PhieuThanhPhan.phieu_id.in_(ptg_ids))
        ).all()
        if not sp_rows:
            return [], len(ptg_ids)

        # Nhãn giấy: gom theo CHỦNG LOẠI + định lượng ("Couché 300gsm") chứ không theo từng khổ —
        # cùng loại giấy mà hai khổ thì vẫn là một thói quen dùng giấy. Không tra được thì lùi về
        # nhãn khổ đã lưu trên phiếu.
        giay_ids = {r.giay_id for r in sp_rows if r.giay_id}
        nhan_giay: dict[int, str] = {}
        if giay_ids:
            for gid, ten, gsm, cl_ten in self.db.execute(
                select(GiayNguyen.id, GiayNguyen.ten, GiayNguyen.gsm, ChungLoaiGiay.ten)
                .join(
                    ChungLoaiGiay,
                    ChungLoaiGiay.id == GiayNguyen.chung_loai_giay_id,
                    isouter=True,
                )
                .where(GiayNguyen.id.in_(giay_ids))
            ).all():
                nhan = f"{cl_ten} {gsm}gsm" if cl_ten and gsm else (ten or "").strip()
                if nhan:
                    nhan_giay[gid] = nhan

        dem_giay: Counter[str] = Counter()
        dem_mau: Counter[str] = Counter()
        dem_kho: Counter[str] = Counter()
        for r in sp_rows:
            nhan = nhan_giay.get(r.giay_id or -1) or (r.kho_nguyen or "").strip()
            if nhan:
                dem_giay[nhan] += 1
            mau = _mau_label(r.muc_a, r.muc_b, r.so_mau_a, r.so_mau_b, r.so_mau_pha)
            if mau:
                dem_mau[mau] += 1
            kho = _kho_label(r.rong_thanh_pham, r.dai_thanh_pham)
            if kho:
                dem_kho[kho] += 1

        # Gia công: mỗi sản phẩm có NHIỀU bước nên đếm theo số sản phẩm có bước đó, rồi lấy 2 bước
        # hay gặp nhất ("Cán bóng · Đóng keo"). `%` là của bước đầu.
        sp_ids = [r.id for r in sp_rows]
        dem_gia_cong: Counter[str] = Counter()
        nhan_goc: dict[str, str] = {}
        for (ten,) in self.db.execute(
            select(PhieuThanhPham.ten).where(PhieuThanhPham.thanh_phan_id.in_(sp_ids))
        ).all():
            sach = (ten or "").strip()
            if not sach:
                continue
            khoa = sach.lower()
            nhan_goc.setdefault(khoa, sach)
            dem_gia_cong[khoa] += 1

        specs: list[PrintSpec] = []

        def _them(key: str, label: str, dem: Counter[str]) -> None:
            if not dem:
                return
            gia_tri, so_lan = dem.most_common(1)[0]
            tong = sum(dem.values())
            specs.append(
                PrintSpec(
                    key=key,
                    label=label,
                    value=gia_tri,
                    pct=round(so_lan / tong * 100) if tong else 0,
                )
            )

        _them("giay", "Giấy hay dùng", dem_giay)
        _them("mau", "Số màu hay in", dem_mau)
        if dem_gia_cong:
            top = dem_gia_cong.most_common(2)
            specs.append(
                PrintSpec(
                    key="gia_cong",
                    label="Gia công hay đặt",
                    value=" · ".join(nhan_goc[k] for k, _ in top),
                    pct=round(top[0][1] / len(sp_rows) * 100),
                )
            )
        _them("kho", "Khổ thành phẩm", dem_kho)
        return specs, len(ptg_ids)

    # --- history tables -----------------------------------------------------

    def order_history(self, customer_id: int, *, limit: int = 200) -> list[OrderHistoryRow]:
        rows = self.db.execute(
            select(
                Order.id,
                Order.order_no,
                Order.status,
                Order.order_kind,
                func.sum(OrderLine.line_total),
                Order.created_at,
            )
            .join(OrderLine, OrderLine.order_id == Order.id, isouter=True)
            .where(Order.customer_id == customer_id)
            .group_by(
                Order.id, Order.order_no, Order.status, Order.order_kind, Order.created_at
            )
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
        ).all()
        # Dòng của đơn: mô tả + TIỀN THẬT của từng dòng — one query, no N+1.
        order_ids = [r[0] for r in rows]
        lines_by_order: dict[int, list[OrderLineBrief]] = {}
        if order_ids:
            for oid, desc, line_total in self.db.execute(
                select(OrderLine.order_id, OrderLine.description, OrderLine.line_total)
                .where(OrderLine.order_id.in_(order_ids))
                .order_by(OrderLine.id)
            ):
                if desc:
                    lines_by_order.setdefault(oid, []).append(
                        OrderLineBrief(description=desc.strip(), line_total=int(line_total or 0))
                    )
        return [
            OrderHistoryRow(
                id=oid,
                order_no=no,
                status=status,
                order_kind=kind,
                summary=", ".join(d.description for d in lines_by_order.get(oid, [])) or "—",
                lines=lines_by_order.get(oid, []),
                total=int(total) if total is not None else None,
                created_at=created,
            )
            for oid, no, status, kind, total, created in rows
        ]

    def quote_history(self, customer_id: int, *, limit: int = 200) -> list[QuoteHistoryRow]:
        rows = self.db.execute(
            select(Quote, QuoteVersion)
            .join(QuoteVersion, Quote.current_version_id == QuoteVersion.id, isouter=True)
            .where(Quote.customer_id == customer_id)
            .order_by(Quote.created_at.desc(), Quote.id.desc())
            .limit(limit)
        ).all()
        return [
            QuoteHistoryRow(
                id=q.id,
                code=q.quote_number,
                version=qv.version_number if qv else 1,
                status=q.status,
                total=int(qv.final_amount) if qv else 0,
                valid_until=q.valid_until,
                created_at=q.created_at,
            )
            for q, qv in rows
        ]
