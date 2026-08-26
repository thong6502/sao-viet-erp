"""Repositories for Thu mua (suppliers + purchase requests)."""
from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import Date, Integer, and_, asc, case, desc, exists, func, literal, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.accounting import PAYMENT_VOUCHER_PAID, PaymentVoucher
from ..models.purchase import (
    DPR_CANCELLED,
    DPR_IN_PURCHASE,
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    DepartmentPurchaseRequest,
    DepartmentPurchaseRequestLine,
    NGUONG_SAO_NCC,
    PR_APPROVED,
    PR_DRAFT,
    PR_PENDING,
    PR_PARTIALLY_RECEIVED,
    PR_PURCHASED,
    PR_RECEIVED,
    PR_REJECTED,
    SAO_THAP_NHAT,
    SUPPLIER_ACTIVE,
    TRANG_THAI_TINH_SAO,
    PurchaseDelivery,
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseRequestSource,
    PurchaseStatusHistory,
    Supplier,
    SupplierItem,
)


# Quan hệ mà `purchase_money` cần để tính TIỀN. Khai một chỗ rồi dùng lại ở cả ba cửa đọc phiếu —
# thiếu ở cửa nào thì cửa đó vừa N+1 vừa (với `deliveries`) tính RA SỐ KHÁC: không thấy đợt giao
# nghĩa là rơi về nhánh phiếu-cũ, công nợ hiện sai mà không có lỗi nào bắn ra.
def _quan_he_tien():
    return (
        selectinload(PurchaseRequest.lines),
        selectinload(PurchaseRequest.supplier),
        selectinload(PurchaseRequest.deliveries).selectinload(PurchaseDelivery.lines),
        selectinload(PurchaseRequest.payment_vouchers).selectinload(PaymentVoucher.receipts),
    )


def _so_ngay(bind, sau, truoc):
    """SỐ NGÀY giữa hai giá trị DATE, tính NGAY TRONG SQL.

    Phải rẽ nhánh vì hai DB nói hai thứ tiếng: Postgres cho `date - date` ra INTEGER; SQLite lưu
    DATE thành chuỗi 'YYYY-MM-DD' nên trừ thẳng ra số rác (nó ép chuỗi về 0), phải đi vòng qua
    `julianday()`. Dev/prod là Postgres, test là SQLite in-memory ⇒ thiếu nhánh nào thì nhánh đó
    ra sai mà KHÔNG bắn lỗi — chỉ là mọi đơn bỗng "đúng hẹn".

    `.op("-")` chứ không phải `sau - truoc`: SQLAlchemy khai Date − Date = Interval, còn Postgres
    trả về INTEGER, lệch kiểu là vỡ lúc đọc kết quả.
    """
    if (bind.dialect.name or "").startswith("sqlite"):
        return func.julianday(sau) - func.julianday(truoc)
    return sau.op("-", return_type=Integer)(truoc)


_SUPPLIER_SORTABLE = {
    "name": Supplier.name,
    "tax_code": Supplier.tax_code,
    "created_at": Supplier.created_at,
}

#: Khoá sắp xếp theo SAO — không phải cột của bảng nên không nằm trong bảng tra ở trên, `list()`
#: bắt riêng và lấy cột của truy vấn con đánh giá.
_SORT_SAO = "rating"

_REQUEST_SORTABLE = {
    "code": PurchaseRequest.code,
    "status": PurchaseRequest.status,
    "needed_date": PurchaseRequest.needed_date,
    "created_at": PurchaseRequest.created_at,
}

_DEPARTMENT_REQUEST_SORTABLE = {
    "code": DepartmentPurchaseRequest.code,
    "status": DepartmentPurchaseRequest.status,
    "needed_date": DepartmentPurchaseRequest.needed_date,
    "created_at": DepartmentPurchaseRequest.created_at,
}


class SupplierRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, supplier_id: int) -> Supplier | None:
        return self.db.execute(
            select(Supplier)
            .options(selectinload(Supplier.items))
            .where(Supplier.id == supplier_id)
        ).scalars().first()

    def find_by_name(self, name: str) -> Supplier | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(Supplier).where(func.lower(Supplier.name) == name.lower())
        ).scalars().first()

    def find_by_tax_code(self, tax_code: str) -> Supplier | None:
        """Tra NCC theo MÃ SỐ THUẾ (không phân biệt hoa thường, bỏ khoảng trắng hai đầu).

        MST là định danh pháp lý — hai hồ sơ cùng MST nghĩa là một nhà cung cấp bị nhập hai lần,
        và mọi con số công nợ của họ bị chẻ đôi. Trùng TÊN đã chặn từ trước; MST thì chưa."""
        tax_code = (tax_code or "").strip()
        if not tax_code:
            return None
        return self.db.execute(
            select(Supplier).where(func.lower(Supplier.tax_code) == tax_code.lower())
        ).scalars().first()

    def _bang_danh_gia(self, hom_nay: date | None = None):
        """SỔ ĐIỂM đã gộp sẵn theo `supplier_id` — MỘT truy vấn con cho TOÀN BỘ nhà cung cấp.

        Cố ý là truy vấn con chứ không phải vòng lặp: màn Nhà cung cấp tải 500 dòng một lượt, hỏi
        từng NCC một là 500 lượt đi DB cho một cột hiển thị.

        Luật nghiệp vụ (mốc hẹn · ngày chốt · thang sao) viết ở `services/danh_gia_ncc.py`; ở đây
        chỉ DỊCH đúng thang ấy sang SQL, và thang thì đọc chung `NGUONG_SAO_NCC` nên không có
        đường nào để hai bên lệch nhau.
        """
        bind = self.db.get_bind()
        hom_nay = hom_nay or date.today()
        moc_hom_nay = literal(hom_nay, Date)

        # Ngày giao CUỐI CÙNG của từng phiếu. Gộp trước rồi mới nối, để một phiếu nhiều đợt giao
        # không nhân dòng lên khi đếm.
        giao = (
            select(
                PurchaseDelivery.purchase_request_id.label("pr_id"),
                func.max(PurchaseDelivery.delivery_date).label("ngay_giao_cuoi"),
            )
            .group_by(PurchaseDelivery.purchase_request_id)
            .subquery()
        )

        # Đơn đã nhận đủ ⇒ chốt ở ngày giao cuối. Đơn CHƯA đủ ⇒ chốt ở HÔM NAY: hàng còn nằm bên
        # NCC thì đồng hồ còn chạy, không thì ôm hàng mãi lại thành sạch sổ.
        ngay_chot = case(
            (PurchaseRequest.status == PR_RECEIVED, giao.c.ngay_giao_cuoi),
            else_=moc_hom_nay,
        )
        so_ngay_tre = _so_ngay(bind, ngay_chot, PurchaseRequest.needed_date)
        sao = case(
            *[(so_ngay_tre <= tran, diem) for tran, diem in NGUONG_SAO_NCC],
            else_=SAO_THAP_NHAT,
        )

        don = (
            select(
                PurchaseRequest.supplier_id.label("supplier_id"),
                sao.label("sao"),
                case((so_ngay_tre > 0, 1), else_=0).label("tre"),
                case((so_ngay_tre > 0, so_ngay_tre), else_=0).label("ngay_tre"),
            )
            .select_from(PurchaseRequest)
            .outerjoin(giao, giao.c.pr_id == PurchaseRequest.id)
            .where(
                PurchaseRequest.supplier_id.isnot(None),
                # Thiếu MỐC HẸN thì không có gì để so — bỏ đơn, đừng đoán thành đúng hẹn.
                PurchaseRequest.needed_date.isnot(None),
                PurchaseRequest.status.in_(TRANG_THAI_TINH_SAO),
                or_(
                    # Đã giao ít nhất một đợt ⇒ có ngày để chấm.
                    giao.c.ngay_giao_cuoi.isnot(None),
                    # Hoặc: chưa nhận đủ mà ĐÃ quá hẹn ⇒ chấm tới hôm nay.
                    # Vế `status != received` chặn luôn ca phiếu cũ ghi "đã nhận" mà không có đợt
                    # giao nào: không biết hàng về ngày nào thì bỏ qua, chứ tính là trễ tới hôm
                    # nay thì đổ oan cho một đơn đã xong.
                    and_(
                        PurchaseRequest.status != PR_RECEIVED,
                        PurchaseRequest.needed_date < moc_hom_nay,
                    ),
                ),
            )
            .subquery()
        )

        return (
            select(
                don.c.supplier_id.label("supplier_id"),
                func.avg(don.c.sao).label("sao_tb"),
                func.count().label("so_don"),
                func.sum(1 - don.c.tre).label("so_dung_hen"),
                func.sum(don.c.tre).label("so_tre"),
                func.sum(don.c.ngay_tre).label("tong_ngay_tre"),
            )
            .group_by(don.c.supplier_id)
            .subquery()
        )

    @staticmethod
    def _doc_danh_gia(sao_tb, so_don, so_dung_hen, so_tre, tong_ngay_tre) -> dict | None:
        """Một dòng sổ điểm thô → dict, hoặc `None` khi NCC chưa có đơn nào đủ điều kiện.

        `None` ở đây đi thẳng thành "Chưa đánh giá" ở service. KHÔNG được đổi thành 0.
        """
        if sao_tb is None or not so_don:
            return None
        return {
            "sao_tb": float(sao_tb),
            "so_don": int(so_don),
            "so_dung_hen": int(so_dung_hen or 0),
            "so_tre": int(so_tre or 0),
            "tong_ngay_tre": float(tong_ngay_tre or 0),
        }

    def danh_gia_mot(self, supplier_id: int) -> dict | None:
        """Sổ điểm thô của ĐÚNG một NCC — cho các cửa trả về một dòng (tạo · sửa · bật/tắt)."""
        dg = self._bang_danh_gia()
        row = self.db.execute(
            select(dg.c.sao_tb, dg.c.so_don, dg.c.so_dung_hen, dg.c.so_tre, dg.c.tong_ngay_tre)
            .where(dg.c.supplier_id == supplier_id)
        ).first()
        return self._doc_danh_gia(*row) if row is not None else None

    def list(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_group: str | None = None,
        # Lọc theo SAO: chỉ lấy NCC có trung bình ≥ mức này. NCC "Chưa đánh giá" (`sao_tb` NULL)
        # tự rơi ra khỏi kết quả — đúng ý, vì lọc "≥4 sao" là đang hỏi ai ĐÃ chứng minh được.
        rating_min: float | None = None,
        # MỚI NHẤT TRƯỚC (chủ chốt 12/08/2026). Trước đây xếp theo TÊN — NCC vừa khai xong nằm
        # tận trang 3, người khai phải đi tìm chính thứ mình vừa tạo.
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[tuple[Supplier, dict | None]], int]:
        danh_gia = self._bang_danh_gia()
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Supplier.name).like(like),
                    func.lower(Supplier.tax_code).like(like),
                    func.lower(Supplier.phone).like(like),
                )
            )
        if status:
            conditions.append(Supplier.status == status)
        if supplier_group:
            conditions.append(Supplier.supplier_group == supplier_group)
        if rating_min is not None:
            conditions.append(danh_gia.c.sao_tb >= rating_min)

        # Nối sổ điểm bằng OUTER join ở CẢ hai truy vấn: NCC chưa có đơn nào vẫn phải nằm trong
        # danh sách (và vẫn phải được đếm) — chỉ là cột sao của họ rỗng.
        stmt = (
            select(
                Supplier,
                danh_gia.c.sao_tb,
                danh_gia.c.so_don,
                danh_gia.c.so_dung_hen,
                danh_gia.c.so_tre,
                danh_gia.c.tong_ngay_tre,
            )
            .options(selectinload(Supplier.items))
            .outerjoin(danh_gia, danh_gia.c.supplier_id == Supplier.id)
        )
        count_stmt = (
            select(func.count())
            .select_from(Supplier)
            .outerjoin(danh_gia, danh_gia.c.supplier_id == Supplier.id)
        )
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        if key == _SORT_SAO:
            # NCC "Chưa đánh giá" xuống CUỐI ở CẢ HAI CHIỀU: chưa có dữ liệu KHÔNG phải là điểm
            # thấp nhất, xếp họ lên đầu khi sort tăng dần là đọc thành "đây là mấy ông tệ nhất".
            # Tự dựng khoá phụ thay vì NULLS LAST — mệnh đề đó không có ở mọi bản SQLite.
            stmt = stmt.order_by(
                case((danh_gia.c.sao_tb.is_(None), 1), else_=0).asc(),
                direction(danh_gia.c.sao_tb),
                direction(Supplier.id),
            )
        else:
            cot = _SUPPLIER_SORTABLE.get(key, Supplier.created_at)
            # Tie-break đi CÙNG CHIỀU với cột chính: xếp mới-nhất-trước mà `id ASC` thì hai NCC tạo
            # cùng giây lại đảo ngược nhau ngay trong danh sách vừa xếp giảm dần.
            stmt = stmt.order_by(direction(cot), direction(Supplier.id))
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = [
            (sup, self._doc_danh_gia(sao_tb, so_don, so_dung_hen, so_tre, tong_ngay_tre))
            for sup, sao_tb, so_don, so_dung_hen, so_tre, tong_ngay_tre in self.db.execute(
                stmt.offset((page - 1) * size).limit(size)
            ).all()
        ]
        return rows, total

    def create(
        self,
        *,
        name: str,
        tax_code: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        address: str | None = None,
        contact_name: str | None = None,
        supplier_group: str | None = None,
        payment_terms: str | None = None,
        credit_limit: int = 0,
        credit_days: int | None = None,
        status: str = SUPPLIER_ACTIVE,
        note: str | None = None,
        items: Sequence["SupplierItemInput"] | None = None,
    ) -> Supplier:
        row = Supplier(
            name=name,
            tax_code=tax_code,
            phone=phone,
            email=email,
            address=address,
            contact_name=contact_name,
            supplier_group=supplier_group,
            payment_terms=payment_terms,
            credit_limit=credit_limit,
            credit_days=credit_days,
            status=status,
            note=note,
        )
        row.items = [
            SupplierItem(
                hang_loai=item.hang_loai,
                hang_id=item.hang_id,
                item_name=item.item_name,
                unit=item.unit,
                unit_price=item.unit_price,
                vat_percent=item.vat_percent,
                is_active=True,
                note=item.note,
            )
            for item in (items or [])
        ]
        self.db.add(row)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return row

    def update(self, supplier: Supplier, **values) -> Supplier:
        items = values.pop("items", None)
        for key, value in values.items():
            setattr(supplier, key, value)
        if items is not None:
            supplier.items = [
                SupplierItem(
                    hang_loai=item.hang_loai,
                    hang_id=item.hang_id,
                    item_name=item.item_name,
                    unit=item.unit,
                    unit_price=item.unit_price,
                    vat_percent=item.vat_percent,
                        is_active=True,
                    note=item.note,
                )
                for item in items
            ]
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(supplier)
        return supplier

    def list_item_catalog(self) -> list[dict]:
        rows = list(
            self.db.execute(
                select(SupplierItem)
                .join(Supplier, Supplier.id == SupplierItem.supplier_id)
                .where(Supplier.status == SUPPLIER_ACTIVE)
                .order_by(func.lower(SupplierItem.item_name), SupplierItem.unit_price.asc(), SupplierItem.id.asc())
            ).scalars()
        )
        grouped: dict[str, dict] = {}
        suppliers_by_key: dict[str, set[int]] = {}
        for row in rows:
            key = (row.item_name or "").strip().lower()
            if not key:
                continue
            current = grouped.get(key)
            if current is None:
                grouped[key] = {
                    "item_name": row.item_name,
                    "unit": row.unit,
                    "min_unit_price": int(row.unit_price),
                }
                suppliers_by_key[key] = set()
            elif int(row.unit_price) < int(current["min_unit_price"]):
                current["min_unit_price"] = int(row.unit_price)
                current["unit"] = row.unit
                current["item_name"] = row.item_name
            suppliers_by_key[key].add(row.supplier_id)
        return [
            {
                **value,
                "supplier_count": len(suppliers_by_key[key]),
            }
            for key, value in grouped.items()
        ]

    def items_for_hang(self, hang_loai: str, hang_id: int) -> list[tuple]:
        """Mọi dòng bảng-giá đang bán MỘT mặt hàng gốc, kèm NCC — nguồn của bảng so giá (mg 0172).

        Chỉ NCC đang hoạt động và dòng còn `is_active`: so giá với NCC đã ngưng hợp tác là mời
        người ta chọn một đường không đi được.
        """
        rows = self.db.execute(
            select(Supplier, SupplierItem)
            .join(SupplierItem, SupplierItem.supplier_id == Supplier.id)
            .where(
                Supplier.status == SUPPLIER_ACTIVE,
                SupplierItem.is_active.is_(True),
                SupplierItem.hang_loai == hang_loai,
                SupplierItem.hang_id == hang_id,
            )
            .order_by(Supplier.name.asc())
        ).all()
        return [(r[0], r[1]) for r in rows]

    def has_active_item(self, item_name: str) -> bool:
        """CÓ NCC NÀO đang hoạt động bán thứ này không — dùng lúc lập YÊU CẦU mua, khi chưa biết
        sẽ mua của ai. Muốn hỏi "NCC CỤ THỂ này có bán không" thì dùng `supplier_sells`."""
        clean_name = (item_name or "").strip().lower()
        if not clean_name:
            return False
        return (
            self.db.execute(
                select(SupplierItem.id)
                .join(Supplier, Supplier.id == SupplierItem.supplier_id)
                .where(
                    Supplier.status == SUPPLIER_ACTIVE,
                    func.lower(SupplierItem.item_name) == clean_name,
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def has_active_item_for_hang(self, hang_loai: str, hang_id: int) -> bool:
        """Có NCC đang hoạt động khai bán đúng mặt hàng gốc này không."""
        return (
            self.db.execute(
                select(SupplierItem.id)
                .join(Supplier, Supplier.id == SupplierItem.supplier_id)
                .where(
                    Supplier.status == SUPPLIER_ACTIVE,
                    SupplierItem.is_active.is_(True),
                    SupplierItem.hang_loai == hang_loai,
                    SupplierItem.hang_id == int(hang_id),
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def active_hang_pairs(self) -> set[tuple[str, int]]:
        """Mặt hàng gốc có ít nhất một dòng bảng giá NCC đang dùng."""
        rows = self.db.execute(
            select(SupplierItem.hang_loai, SupplierItem.hang_id)
            .join(Supplier, Supplier.id == SupplierItem.supplier_id)
            .where(
                Supplier.status == SUPPLIER_ACTIVE,
                SupplierItem.is_active.is_(True),
                SupplierItem.hang_loai.is_not(None),
                SupplierItem.hang_id.is_not(None),
            )
            .distinct()
        ).all()
        return {(str(loai), int(hang_id)) for loai, hang_id in rows}

    def supplier_sells(self, supplier_id: int, item_name: str) -> bool:
        """NCC CỤ THỂ này có bán mặt hàng đó không — dùng lúc lập PHIẾU MUA, khi đã chọn NCC.

        Khác `has_active_item` ở hai chỗ: bó theo đúng một NCC, và có xét `SupplierItem.is_active`
        (mặt hàng đã ngưng bán thì không đặt mới được nữa). Khớp tên theo chuỗi viết thường đã cắt
        khoảng trắng — đúng cách `list_item_catalog` gom danh mục, để hai nơi không hiểu khác nhau.
        """
        clean_name = (item_name or "").strip().lower()
        if not clean_name or not supplier_id:
            return False
        return (
            self.db.execute(
                select(SupplierItem.id)
                .where(
                    SupplierItem.supplier_id == int(supplier_id),
                    SupplierItem.is_active.is_(True),
                    func.lower(SupplierItem.item_name) == clean_name,
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )


class SupplierItemInput:
    def __init__(
        self,
        *,
        item_name: str,
        unit: str,
        unit_price: int,
        vat_percent: float = 0,
        note: str | None = None,
        hang_loai: str | None = None,
        hang_id: int | None = None,
    ) -> None:
        self.item_name = item_name
        self.unit = unit
        self.unit_price = unit_price
        self.vat_percent = vat_percent
        self.note = note
        # Mặt hàng gốc (mg 0172) — None với thứ NCC bán ngoài danh mục vật tư.
        self.hang_loai = hang_loai
        self.hang_id = hang_id


class PurchaseRequestLineInput:
    def __init__(
        self,
        *,
        item_name: str,
        unit: str,
        quantity: float,
        expected_unit_price: int,
        discount_percent: float = 0,
        vat_percent: float = 0,
        note: str | None = None,
        department_request_line_id: int | None = None,
        hang_loai: str | None = None,
        hang_id: int | None = None,
    ) -> None:
        self.item_name = item_name
        self.unit = unit
        self.quantity = quantity
        self.expected_unit_price = expected_unit_price
        self.discount_percent = discount_percent
        self.vat_percent = vat_percent
        self.note = note
        self.department_request_line_id = department_request_line_id
        # Mặt hàng gốc (mg 0174) — KẾ THỪA từ dòng YCMH, không đoán từ `item_name`.
        self.hang_loai = hang_loai
        self.hang_id = hang_id


class DepartmentPurchaseRequestLineInput:
    def __init__(
        self,
        *,
        item_name: str,
        unit: str,
        quantity: float,
        expected_unit_price: int = 0,
        note: str | None = None,
        hang_loai: str | None = None,
        hang_id: int | None = None,
    ) -> None:
        self.item_name = item_name
        self.unit = unit
        self.quantity = quantity
        self.expected_unit_price = expected_unit_price
        self.note = note
        # Mặt hàng gốc (mg 0174) — bảng cân đối vật tư ghi vào đây khi bấm "Đề nghị mua".
        self.hang_loai = hang_loai
        self.hang_id = hang_id


# Phiếu mua sinh ra từ yêu cầu, kèm dòng + NCC. Cần cho HAI việc, cả hai đều chạy trên MỌI yêu
# cầu được đọc ra: suy trạng thái (`_tinh_lai_trang_thai_ycmh`) và hiện tình trạng TỪNG SẢN PHẨM ở
# chi tiết. Không nạp sẵn thì mỗi yêu cầu trong danh sách bắn thêm mấy query — danh sách 20 dòng
# thành cả trăm lượt hỏi DB.
_NAP_PHIEU_CON = (
    selectinload(DepartmentPurchaseRequest.purchase_links)
    .selectinload(PurchaseRequestSource.purchase_request)
    .selectinload(PurchaseRequest.lines),
    selectinload(DepartmentPurchaseRequest.purchase_links)
    .selectinload(PurchaseRequestSource.purchase_request)
    .selectinload(PurchaseRequest.supplier),
)


class DepartmentPurchaseRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: int) -> DepartmentPurchaseRequest | None:
        return self.db.execute(
            select(DepartmentPurchaseRequest)
            .options(
                selectinload(DepartmentPurchaseRequest.lines),
                selectinload(DepartmentPurchaseRequest.requesting_department),
                selectinload(DepartmentPurchaseRequest.requested_by),
                *_NAP_PHIEU_CON,
            )
            .where(DepartmentPurchaseRequest.id == request_id)
        ).scalars().first()

    def get_by_code(self, code: str) -> DepartmentPurchaseRequest | None:
        return self.db.execute(
            select(DepartmentPurchaseRequest).where(DepartmentPurchaseRequest.code == code)
        ).scalars().first()

    def get_many(self, ids: Sequence[int]) -> list[DepartmentPurchaseRequest]:
        if not ids:
            return []
        return list(
            self.db.execute(
                select(DepartmentPurchaseRequest)
                .options(
                    selectinload(DepartmentPurchaseRequest.lines),
                    selectinload(DepartmentPurchaseRequest.requesting_department),
                    selectinload(DepartmentPurchaseRequest.requested_by),
                )
                .where(DepartmentPurchaseRequest.id.in_(list(ids)))
            ).scalars()
        )

    def list(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        requesting_department_id: int | None = None,
        filter_by_department: bool = False,
        # Phạm vi `own` — CHỈ yêu cầu do chính người này gửi. Trước 11/08/2026 không có tham số
        # này: `own` rơi xuống dùng chung nhánh lọc theo phòng, tức thấy luôn yêu cầu của đồng
        # nghiệp cùng phòng. Đo được: vai phạm vi `own` thấy 1 dòng do NGƯỜI KHÁC tạo.
        requested_by_user_id: int | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[DepartmentPurchaseRequest], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(DepartmentPurchaseRequest.code).like(like),
                    func.lower(DepartmentPurchaseRequest.purpose).like(like),
                    func.lower(DepartmentPurchaseRequest.related_document_code).like(like),
                    func.lower(DepartmentPurchaseRequest.content).like(like),
                )
            )
        if status:
            # `drafting` và `needs_correction` là trạng thái HIỂN THỊ suy từ đơn mua con. Lọc ngay
            # trong SQL để `total` và phân trang vẫn chính xác, thay vì lọc 20 dòng sau khi tải.
            def co_phieu_con(*statuses: str):
                return exists(
                    select(PurchaseRequestSource.id)
                    .join(
                        PurchaseRequest,
                        PurchaseRequest.id == PurchaseRequestSource.purchase_request_id,
                    )
                    .where(
                        PurchaseRequestSource.department_request_id
                        == DepartmentPurchaseRequest.id,
                        PurchaseRequest.status.in_(statuses),
                    )
                )

            # "Huỷ một phần" (mg 0233) = có ít nhất một món đã bỏ VÀ vẫn còn món sống. Huy hiệu
            # trên bảng lấy trạng thái này ĐÈ lên nhãn tiến độ, nên bộ lọc phải đi cùng: lọc "Đang
            # mua" mà vẫn trả về dòng đang đeo huy hiệu "Huỷ một phần" là người dùng thôi tin bộ lọc.
            def co_dong(da_huy: bool):
                dk = (
                    DepartmentPurchaseRequestLine.cancelled_at.is_not(None)
                    if da_huy
                    else DepartmentPurchaseRequestLine.cancelled_at.is_(None)
                )
                return exists(
                    select(DepartmentPurchaseRequestLine.id).where(
                        DepartmentPurchaseRequestLine.department_request_id
                        == DepartmentPurchaseRequest.id,
                        dk,
                    )
                )

            huy_mot_phan = and_(co_dong(True), co_dong(False))
            co_tu_choi = co_phieu_con(PR_REJECTED)
            co_nhap = co_phieu_con(PR_DRAFT)
            if status == "partially_cancelled":
                conditions.append(huy_mot_phan)
            elif status == "needs_correction":
                conditions.extend((co_tu_choi, ~huy_mot_phan))
            elif status == "drafting":
                conditions.extend((~co_tu_choi, co_nhap, ~huy_mot_phan))
            elif status == DPR_PENDING_APPROVAL:
                conditions.extend(
                    (
                        DepartmentPurchaseRequest.status == DPR_PENDING_APPROVAL,
                        ~co_tu_choi,
                        ~co_nhap,
                        ~huy_mot_phan,
                    )
                )
            elif status == DPR_CANCELLED:
                # Phiếu huỷ HẲN: không còn món sống nào ⇒ `huy_mot_phan` tự sai, không cần loại.
                conditions.append(DepartmentPurchaseRequest.status == status)
            else:
                conditions.extend(
                    (DepartmentPurchaseRequest.status == status, ~huy_mot_phan)
                )
        if source_type:
            conditions.append(DepartmentPurchaseRequest.source_type == source_type)
        if requested_by_user_id is not None:
            conditions.append(DepartmentPurchaseRequest.requested_by_user_id == requested_by_user_id)
        elif filter_by_department:
            conditions.append(DepartmentPurchaseRequest.requesting_department_id == requesting_department_id)

        stmt = select(DepartmentPurchaseRequest).options(
            selectinload(DepartmentPurchaseRequest.lines),
            selectinload(DepartmentPurchaseRequest.requesting_department),
            selectinload(DepartmentPurchaseRequest.requested_by),
            *_NAP_PHIEU_CON,
        )
        count_stmt = select(func.count()).select_from(DepartmentPurchaseRequest)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        stmt = stmt.order_by(
            direction(_DEPARTMENT_REQUEST_SORTABLE.get(key, DepartmentPurchaseRequest.created_at)),
            DepartmentPurchaseRequest.id.desc(),
        )
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total

    def count_open(
        self, *, requesting_department_id: int | None = None, filter_by_department: bool = False
    ) -> int:
        """Số YCMH đang **Chờ mua** — nuôi badge Thu mua (COUNT ở DB, không tải danh sách).

        Nhận ĐÚNG hai tham số lọc mà `list` dùng, để badge và màn hình không thể lệch nhau: badge
        báo 5 mà mở màn ra thấy 1 thì người dùng thôi tin con số, badge thành vô dụng."""
        stmt = select(func.count(DepartmentPurchaseRequest.id)).where(
            DepartmentPurchaseRequest.status == DPR_OPEN
        )
        if filter_by_department:
            stmt = stmt.where(
                DepartmentPurchaseRequest.requesting_department_id == requesting_department_id
            )
        return int(self.db.execute(stmt).scalar_one())

    def dang_de_nghi(self) -> list[DepartmentPurchaseRequest]:
        """YCMH CHƯA KHÉP — nguồn câu *"món này đã có ai đề nghị mua chưa"* của bảng cân đối.

        Bảng cân đối chỉ cộng hàng khi đã có PMH duyệt (`dong_dang_ve`). Nhưng giữa lúc bấm "Mua"
        và lúc PMH được duyệt, món hàng nằm ở đây — mà màn lại vẽ nó ĐỎ y như chưa ai đụng vào, nên
        người tiếp theo bấm Mua lần nữa. Ngày 20/08/2026 Couché 300 của GB26-0004 có ĐÚNG hai YCMH
        cùng 38,08 kg vì lẽ đó.

        `done`/`cancelled` bỏ (việc đã khép), `in_purchase` GIỮ (PMH sinh ra từ nó có thể còn nằm
        chờ duyệt). Chỉ nạp `lines` — phía gọi cần mã · trạng thái · mặt hàng, không cần phiếu con.
        """
        stmt = (
            select(DepartmentPurchaseRequest)
            .options(selectinload(DepartmentPurchaseRequest.lines))
            .where(
                DepartmentPurchaseRequest.status.in_(
                    [DPR_OPEN, DPR_PENDING_APPROVAL, DPR_IN_PURCHASE]
                )
            )
            .order_by(DepartmentPurchaseRequest.id.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def create(
        self,
        *,
        code: str,
        source_type: str,
        requesting_department_id: int | None,
        requested_by_user_id: int | None,
        related_document_type: str | None,
        related_document_code: str | None,
        purpose: str,
        content: str | None = None,
        needed_date: date = None,
        note: str | None = None,
        lines: Sequence[DepartmentPurchaseRequestLineInput] = (),
    ) -> DepartmentPurchaseRequest:
        row = DepartmentPurchaseRequest(
            code=code,
            status=DPR_OPEN,
            source_type=source_type,
            requesting_department_id=requesting_department_id,
            requested_by_user_id=requested_by_user_id,
            related_document_type=related_document_type,
            related_document_code=related_document_code,
            # `purpose` là BẢN SAO CHẾT của `content`, cắt 500 ký tự — cột cũ NOT NULL nên vẫn
            # phải có giá trị, nhưng KHÔNG đọc nó nữa (07/08/2026).
            purpose=purpose,
            content=content if content is not None else purpose,
            needed_date=needed_date,
            note=note,
        )
        row.lines = [
            DepartmentPurchaseRequestLine(
                item_name=line.item_name,
                unit=line.unit,
                quantity=line.quantity,
                expected_unit_price=line.expected_unit_price,
                note=line.note,
                hang_loai=getattr(line, "hang_loai", None),
                hang_id=getattr(line, "hang_id", None),
            )
            for line in lines
        ]
        self.db.add(row)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return self.get_by_id(row.id) or row

    def save(self, request: DepartmentPurchaseRequest) -> DepartmentPurchaseRequest:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(request)
        return self.get_by_id(request.id) or request

    def update(
        self,
        request: DepartmentPurchaseRequest,
        *,
        purpose: str,
        content: str | None = None,
        needed_date: date = None,
        note: str | None = None,
        lines: Sequence[DepartmentPurchaseRequestLineInput] = (),
    ) -> DepartmentPurchaseRequest:
        request.purpose = purpose
        request.content = content if content is not None else purpose
        request.needed_date = needed_date
        # DÒNG ĐÃ HUỶ KHÔNG ĐI QUA FORM SỬA (mg 0233) — form chỉ gửi lên các món còn sống. Gán đè
        # cả list là `delete-orphan` xoá sạch dòng đã huỷ: mất vết "đã từng đề nghị rồi bỏ", và
        # `purchase_request_lines.department_request_line_id` trỏ tới nó bị SET NULL theo (dòng đơn
        # mua mất luôn nguồn). Giữ chúng ở ĐẦU, đúng thứ tự id cũ.
        da_huy = [ln for ln in request.lines if ln.cancelled_at is not None]
        moi = [
            DepartmentPurchaseRequestLine(
                item_name=line.item_name,
                unit=line.unit,
                quantity=line.quantity,
                expected_unit_price=line.expected_unit_price,
                note=line.note,
                hang_loai=getattr(line, "hang_loai", None),
                hang_id=getattr(line, "hang_id", None),
            )
            for line in lines
        ]
        request.lines = [*da_huy, *moi]
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(request)
        return self.get_by_id(request.id) or request


class PurchaseRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: int) -> PurchaseRequest | None:
        return self.db.execute(
            select(PurchaseRequest)
            .options(
                *_quan_he_tien(),
                selectinload(PurchaseRequest.sources).selectinload(PurchaseRequestSource.department_request),
                selectinload(PurchaseRequest.attachments),
            )
            .where(PurchaseRequest.id == request_id)
        ).scalars().first()

    def get_by_code(self, code: str) -> PurchaseRequest | None:
        return self.db.execute(
            select(PurchaseRequest).where(PurchaseRequest.code == code)
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_id: int | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
        needed_from: date | None = None,
        needed_to: date | None = None,
        expected_receipt_from: date | None = None,
        expected_receipt_to: date | None = None,
        deposit_status: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
        creator_ids: list[int] | None = None,
        exclude_statuses: list[str] | None = None,
    ) -> tuple[list[PurchaseRequest], int]:
        conditions = []
        # PHẠM VI NHÌN: None = thấy hết (giám đốc / kế toán). Danh sách RỖNG nghĩa là không thấy
        # gì — phải phân biệt với None, `if creator_ids:` sẽ nuốt mất trường hợp rỗng và cho thấy
        # cả công ty, đúng cái lỗ đang vá.
        if creator_ids is not None:
            conditions.append(PurchaseRequest.created_by_user_id.in_(creator_ids or [-1]))
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PurchaseRequest.code).like(like),
                    func.lower(PurchaseRequest.purpose).like(like),
                    func.lower(PurchaseRequest.note).like(like),
                    PurchaseRequest.supplier.has(func.lower(Supplier.name).like(like)),
                    PurchaseRequest.sources.any(
                        func.lower(PurchaseRequestSource.source_code_snapshot).like(like)
                    ),
                )
            )
        if status:
            conditions.append(PurchaseRequest.status == status)
        # Loại hẳn vài trạng thái khỏi một hộp thư nào đó (vd hộp Kế toán không nhận phiếu NHÁP).
        # Chặn ở ĐÂY chứ không chỉ ở giao diện — lọc trên màn thì gọi thẳng API vẫn ra.
        if exclude_statuses:
            conditions.append(PurchaseRequest.status.notin_(exclude_statuses))
        if supplier_id is not None:
            conditions.append(PurchaseRequest.supplier_id == supplier_id)
        if created_from is not None:
            conditions.append(func.date(PurchaseRequest.created_at) >= created_from)
        if created_to is not None:
            conditions.append(func.date(PurchaseRequest.created_at) <= created_to)
        if needed_from is not None:
            conditions.append(PurchaseRequest.needed_date >= needed_from)
        if needed_to is not None:
            conditions.append(PurchaseRequest.needed_date <= needed_to)
        if expected_receipt_from is not None:
            conditions.append(PurchaseRequest.expected_receipt_date >= expected_receipt_from)
        if expected_receipt_to is not None:
            conditions.append(PurchaseRequest.expected_receipt_date <= expected_receipt_to)
        if deposit_status:
            advance_paid = (
                select(func.coalesce(func.sum(PaymentVoucher.amount_vnd), 0))
                .where(
                    PaymentVoucher.purchase_request_id == PurchaseRequest.id,
                    PaymentVoucher.status == PAYMENT_VOUCHER_PAID,
                    PaymentVoucher.payment_stage == "advance",
                )
                .correlate(PurchaseRequest)
                .scalar_subquery()
            )
            if deposit_status == "none":
                conditions.append(func.coalesce(PurchaseRequest.deposit_expected, 0) <= 0)
            elif deposit_status == "unpaid":
                conditions.append(func.coalesce(PurchaseRequest.deposit_expected, 0) > 0)
                conditions.append(advance_paid <= 0)
            elif deposit_status == "partial":
                conditions.append(func.coalesce(PurchaseRequest.deposit_expected, 0) > 0)
                conditions.append(advance_paid > 0)
                conditions.append(advance_paid < func.coalesce(PurchaseRequest.deposit_expected, 0))
            elif deposit_status == "enough":
                conditions.append(func.coalesce(PurchaseRequest.deposit_expected, 0) > 0)
                conditions.append(advance_paid >= func.coalesce(PurchaseRequest.deposit_expected, 0))

        stmt = select(PurchaseRequest).options(
            *_quan_he_tien(),
            selectinload(PurchaseRequest.sources).selectinload(PurchaseRequestSource.department_request),
        )
        count_stmt = select(func.count()).select_from(PurchaseRequest)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        stmt = stmt.order_by(direction(_REQUEST_SORTABLE.get(key, PurchaseRequest.created_at)), PurchaseRequest.id.desc())
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total

    def count_rejected_pending_correction(self, *, creator_ids: list[int] | None = None) -> int:
        """Số PMH **bị từ chối** mà YCMH nguồn vẫn đang được phiếu đó giữ.

        PMH bị từ chối giữ YCMH ở `pending_approval`: đây là việc Thu mua phải sửa trên CHÍNH PMH
        rồi gửi lại. YCMH đã huỷ thì không còn việc; PMH đã gửi lại không còn trạng thái rejected
        nên tự hết đếm.

        `COUNT(DISTINCT ...)` vì một PMH gom được nhiều YCMH nguồn: không DISTINCT thì phiếu gom 3
        yêu cầu bị đếm 3 lần.

        `creator_ids`: None = KHÔNG lọc (thấy toàn công ty). List rỗng = không thấy gì — phải phân
        biệt với None, đúng nếp `list` ở trên.
        """
        stmt = (
            select(func.count(func.distinct(PurchaseRequest.id)))
            .select_from(PurchaseRequest)
            .join(
                PurchaseRequestSource,
                PurchaseRequestSource.purchase_request_id == PurchaseRequest.id,
            )
            .join(
                DepartmentPurchaseRequest,
                DepartmentPurchaseRequest.id == PurchaseRequestSource.department_request_id,
            )
            .where(PurchaseRequest.status == PR_REJECTED)
            .where(DepartmentPurchaseRequest.status == DPR_PENDING_APPROVAL)
        )
        if creator_ids is not None:
            stmt = stmt.where(PurchaseRequest.created_by_user_id.in_(creator_ids or [-1]))
        return int(self.db.execute(stmt).scalar_one())

    def list_for_payables(self, *, supplier_id: int | None = None) -> list[PurchaseRequest]:
        """Các phiếu mua CÓ THỂ đang nợ NCC — nguồn của màn Công nợ phải trả.

        Lọc hẹp ngay ở SQL: chỉ phiếu `đã duyệt / đã mua / đã nhận`. Nháp, chờ duyệt, bị từ chối và
        đã huỷ thì không nợ ai đồng nào nên không lôi ra. Ai còn nợ THẬT thì lọc tiếp bằng Python —
        bắt buộc, vì giá trị đơn cộng từ các dòng (có chiết khấu + VAT) chứ không phải một cột SUM
        được.

        Không phân trang: màn công nợ phải cộng đúng TỔNG, cắt trang là ra số sai. Bù lại nạp sẵn
        đúng những quan hệ `purchase_money` cần, để không đẻ ra N+1 query.

        ⚠️ Tập này lớn dần theo thời gian (đơn đã trả xong vẫn mang trạng thái `received`). Ở quy mô
        vài trăm phiếu/tháng thì chưa đáng lo; khi nào chậm thì cắt bằng mốc ngày, đừng bỏ Python
        filter đi."""
        stmt = (
            select(PurchaseRequest)
            .options(
                *_quan_he_tien(),
                # Badge "chưa có chứng từ" đọc `voucher.attachments`. Thiếu dòng này là mỗi phiếu
                # chi bắn thêm một query — đúng cái N+1 mà eager load ở đây sinh ra để tránh.
                selectinload(PurchaseRequest.payment_vouchers).selectinload(
                    PaymentVoucher.attachments
                ),
            )
            .where(
                PurchaseRequest.status.in_(
                    [PR_APPROVED, PR_PURCHASED, PR_PARTIALLY_RECEIVED, PR_RECEIVED]
                )
            )
        )
        if supplier_id is not None:
            stmt = stmt.where(PurchaseRequest.supplier_id == supplier_id)
        return list(self.db.execute(stmt.order_by(PurchaseRequest.id.desc())).scalars())

    def dong_dang_ve(self) -> list[PurchaseRequest]:
        """Phiếu mua ĐANG TRÊN ĐƯỜNG VỀ — nguồn "hàng đang về" của bảng cân đối vật tư.

        Lấy nguyên PHIẾU (kèm dòng + đợt giao) chứ không lấy dòng rời: số CÒN VỀ của một dòng =
        `quantity − Σ các đợt đã giao`, mà đợt giao treo ở phiếu. Cắt sẵn ở tầng repo thì phía gọi
        phải join lại bằng tay — đúng chỗ dễ tính thiếu một đợt rồi cộng dư hàng chưa về.

        Bỏ `PR_RECEIVED` (đã nhận đủ ⇒ hàng nằm trong kho rồi, tồn đã cộng — đếm lại là ĐẾM HAI
        LẦN), bỏ `draft`/`pending`/`rejected`/`cancelled` (chưa chắc có hàng, hứa suông).
        """
        stmt = (
            select(PurchaseRequest)
            .options(
                selectinload(PurchaseRequest.lines),
                selectinload(PurchaseRequest.deliveries).selectinload(PurchaseDelivery.lines),
            )
            .where(
                PurchaseRequest.status.in_(
                    [PR_APPROVED, PR_PURCHASED, PR_PARTIALLY_RECEIVED]
                )
            )
        )
        return list(self.db.execute(stmt.order_by(PurchaseRequest.id.asc())).scalars())

    def dong_cho_duyet(self) -> list[PurchaseRequest]:
        """PMH đã lập, ĐANG CHỜ DUYỆT — hàng chưa chắc có nên KHÔNG được cộng vào tồn.

        Cố ý tách khỏi `dong_dang_ve`: gộp vào đó là hứa suông (phiếu có thể bị từ chối, đúng như
        PMH-260820-YC1U ngày 20/08/2026). Ở đây chỉ để bảng cân đối NÓI ĐƯỢC "đã có phiếu, đang chờ
        duyệt" thay vì vẽ đỏ như chưa ai mua — số học không đổi một ly.

        `draft` bỏ: phiếu nháp là tờ giấy ai đó đang gõ dở, chưa phải lời hứa với lệnh nào.
        """
        stmt = (
            select(PurchaseRequest)
            .options(
                selectinload(PurchaseRequest.lines),
                selectinload(PurchaseRequest.deliveries).selectinload(PurchaseDelivery.lines),
            )
            .where(PurchaseRequest.status == PR_PENDING)
            .order_by(PurchaseRequest.id.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def dong_nhap_hoac_bi_tu_choi(self) -> list[PurchaseRequest]:
        """PMH NHÁP + PMH BỊ TỪ CHỐI — hai loại phiếu KHÔNG hứa hàng, nhưng nói được món đang kẹt.

        Cố ý đứng ngoài `dong_dang_ve`/`dong_cho_duyet`: cả hai loại này số học bằng 0, không được
        cộng một ly nào vào tồn. Chúng chỉ để trả lời câu *"món này chưa ai lo, hay đã có người lo
        mà hỏng giữa chừng"* — hai tình huống trước 24/08/2026 vẽ y hệt nhau trên bảng cân đối
        (`YCMH-260820-JI8X` đeo chip "mới đề nghị" trong khi `PMH-260820-YC1U` của chính món đó đã
        bị từ chối, đang chờ thu mua lập lại).

        Chỉ nạp `lines` — phía gọi cần `department_request_line_id` để dò về đúng DÒNG yêu cầu,
        không cần đợt giao (phiếu nháp/bị từ chối thì làm gì có đợt giao nào).
        """
        stmt = (
            select(PurchaseRequest)
            .options(selectinload(PurchaseRequest.lines))
            .where(PurchaseRequest.status.in_([PR_DRAFT, PR_REJECTED]))
            .order_by(PurchaseRequest.id.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def _build(
        self,
        *,
        code: str,
        supplier_id: int | None,
        purpose: str | None,
        content: str | None = None,
        needed_date: date | None,
        expected_receipt_date: date | None,
        created_by_user_id: int | None,
        note: str | None,
        lines: Sequence[PurchaseRequestLineInput],
        source_requests: Sequence[DepartmentPurchaseRequest],
    ) -> PurchaseRequest:
        """Dựng một phiếu trong bộ nhớ (CHƯA commit) — dùng chung cho `create` và `create_many`."""
        row = PurchaseRequest(
            code=code,
            status=PR_DRAFT,
            supplier_id=supplier_id,
            purpose=purpose,
            content=content if content is not None else purpose,
            needed_date=needed_date,
            expected_receipt_date=expected_receipt_date,
            created_by_user_id=created_by_user_id,
            note=note,
        )
        row.lines = [
            PurchaseRequestLine(
                item_name=line.item_name,
                unit=line.unit,
                quantity=line.quantity,
                expected_unit_price=line.expected_unit_price,
                discount_percent=line.discount_percent,
                vat_percent=line.vat_percent,
                note=line.note,
                department_request_line_id=getattr(line, "department_request_line_id", None),
                hang_loai=getattr(line, "hang_loai", None),
                hang_id=getattr(line, "hang_id", None),
            )
            for line in lines
        ]
        self._replace_sources(row, source_requests)
        self.db.add(row)
        return row

    def create(
        self,
        *,
        code: str,
        supplier_id: int | None,
        purpose: str | None,
        content: str | None = None,
        needed_date: date | None,
        expected_receipt_date: date | None = None,
        created_by_user_id: int | None,
        note: str | None,
        lines: Sequence[PurchaseRequestLineInput],
        source_requests: Sequence[DepartmentPurchaseRequest],
    ) -> PurchaseRequest:
        row = self._build(
            code=code, supplier_id=supplier_id, purpose=purpose, content=content,
            needed_date=needed_date,
            expected_receipt_date=expected_receipt_date, created_by_user_id=created_by_user_id,
            note=note, lines=lines, source_requests=source_requests,
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return self.get_by_id(row.id) or row

    def create_many(self, items: Sequence[dict]) -> list[PurchaseRequest]:
        """Tạo NHIỀU phiếu trong MỘT commit — hoặc ra đủ, hoặc không ra cái nào.

        Gọi `create` trong vòng lặp thì mỗi lần một commit: hỏng ở phiếu thứ hai là phiếu đầu đã
        nằm lại trong DB và yêu cầu nguồn bị giữ chỗ dở dang, không ai dọn."""
        rows = [self._build(**item) for item in items]
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return [self.get_by_id(row.id) or row for row in rows]

    def update_header_and_lines(
        self,
        request: PurchaseRequest,
        *,
        supplier_id: int | None,
        purpose: str | None,
        content: str | None = None,
        needed_date: date | None,
        expected_receipt_date: date | None = None,
        note: str | None,
        lines: Sequence[PurchaseRequestLineInput],
        source_requests: Sequence[DepartmentPurchaseRequest],
    ) -> PurchaseRequest:
        request.supplier_id = supplier_id
        request.purpose = purpose
        request.content = content if content is not None else purpose
        request.needed_date = needed_date
        request.expected_receipt_date = expected_receipt_date
        request.note = note
        request.lines = [
            PurchaseRequestLine(
                item_name=line.item_name,
                unit=line.unit,
                quantity=line.quantity,
                expected_unit_price=line.expected_unit_price,
                discount_percent=line.discount_percent,
                vat_percent=line.vat_percent,
                note=line.note,
                department_request_line_id=getattr(line, "department_request_line_id", None),
                hang_loai=getattr(line, "hang_loai", None),
                hang_id=getattr(line, "hang_id", None),
            )
            for line in lines
        ]
        self._replace_sources(request, source_requests)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(request)
        return self.get_by_id(request.id) or request

    def save(self, request: PurchaseRequest) -> PurchaseRequest:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(request)
        return request

    def delete(self, request: PurchaseRequest) -> None:
        self.db.delete(request)
        self.db.commit()

    def _replace_sources(
        self,
        request: PurchaseRequest,
        source_requests: Sequence[DepartmentPurchaseRequest],
    ) -> None:
        old_sources = {
            link.department_request_id: link.department_request
            for link in getattr(request, "sources", [])
            if link.department_request is not None
        }
        new_ids = {source.id for source in source_requests}
        for source_id, source in old_sources.items():
            if source_id not in new_ids and source.status in (DPR_PENDING_APPROVAL, DPR_IN_PURCHASE):
                source.status = DPR_OPEN
        for source in source_requests:
            source.status = DPR_PENDING_APPROVAL
        request.sources = [
            PurchaseRequestSource(
                department_request_id=source.id,
                source_code_snapshot=source.code,
            )
            for source in source_requests
        ]


class PurchaseStatusHistoryRepository:
    """Lịch sử đổi trạng thái của YCMH + PMH.

    Bảng dùng SOFT REF (`doc_type` + `doc_id`) nên không gắn được relationship — mọi truy vấn phải
    đi qua đây, đừng để màn nào tự join tay."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def them(
        self,
        *,
        doc_type: str,
        doc_id: int,
        from_status: str | None,
        to_status: str,
        changed_by_user_id: int | None,
        source: str,
        reason: str | None = None,
    ) -> PurchaseStatusHistory:
        """Ghi MỘT dòng lịch sử.

        KHÔNG commit: hàm gọi đang ở giữa một giao dịch (đổi trạng thái + suy lại YCMH + lưu phiếu).
        Commit ở đây là lịch sử ghi rồi mà phiếu rollback — sổ nói một đằng, chứng từ một nẻo."""
        row = PurchaseStatusHistory(
            doc_type=doc_type,
            doc_id=doc_id,
            from_status=from_status,
            to_status=to_status,
            changed_by_user_id=changed_by_user_id,
            source=source,
            reason=reason,
        )
        self.db.add(row)
        return row

    def cua(self, doc_type: str, doc_id: int) -> list[PurchaseStatusHistory]:
        """Lịch sử của MỘT chứng từ, MỚI NHẤT TRƯỚC — đúng thứ tự màn hình đọc."""
        return list(
            self.db.execute(
                select(PurchaseStatusHistory)
                .where(
                    PurchaseStatusHistory.doc_type == doc_type,
                    PurchaseStatusHistory.doc_id == doc_id,
                )
                .order_by(PurchaseStatusHistory.id.desc())
            ).scalars()
        )
