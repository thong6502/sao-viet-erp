"""Accounting API: purchase inbox, bank accounts, Phiếu chi and UNC."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from sqlalchemy.orm import Session
from ..db import get_db
from ..services.cong_no_khoa_so_service import CongNoKhoaSoError, CongNoKhoaSoService
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from ..deps import (
    get_accounting_service,
    get_authorization_service,
    get_module_notification_repository,
    get_order_service,
    get_purchase_service,
    require_any_permission,
    require_permission,
)
from ..models.purchase import PR_DRAFT
from ..realtime import hub
from ..models.user import User
from ..repositories.module_notification_repo import (
    CHANNEL_THU_MUA,
    ModuleNotificationRepository,
)
from ..schemas.accounting import (
    ApproveAndCreateVoucherIn,
    BaoCaoCongNoOut,
    SoChiTietCongNoOut,
    CongNoKhoaSoIn,
    CongNoKhoaSoRow,
    CongNoKhoaSoTrangThaiOut,
    CongNoKyRow,
    CancelSalesInvoiceIn,
    CancelPaymentReceiptIn,
    CancelPaymentVoucherIn,
    CompanyBankAccountIn,
    CompanyBankAccountOut,
    MarkPaymentReceiptReceivedIn,
    PaymentReceiptAttachmentListOut,
    PaymentReceiptAttachmentOut,
    PaymentReceiptIn,
    PaymentReceiptListOut,
    PaymentReceiptOut,
    PaymentVoucherAttachmentListOut,
    PaymentVoucherAttachmentOut,
    PaymentVoucherIn,
    PaymentVoucherListOut,
    PaymentVoucherOut,
    VoucherBatchIn,
    VoucherBatchOut,
    PayablesDetailOut,
    PayablesSummaryOut,
    ReceivablesDetailOut,
    ReceivablesSummaryOut,
    SalesInvoiceIn,
    SalesInvoiceListOut,
    SalesInvoiceOut,
    SupplierBankAccountIn,
    SupplierBankAccountOut,
)
from ..schemas.purchase import PurchaseRequestListOut
from ..services import bao_cao_cong_no_excel
from ..services.accounting_service import (
    AccountingConflict,
    AccountingNotFound,
    AccountingService,
    AccountingValidationError,
)
from ..services.purchase_service import PurchaseService
from ..services.order_service import OrderForbidden, OrderNotFound, OrderService
from ..services.rbac_service import AuthorizationService


router = APIRouter(tags=["accounting"])
# TÁCH THEO MÀN (10/08/2026, đường A). Trước đây CẢ phân hệ treo trên một khoá `ke_toan`:
# bật `read` là mở luôn 6 màn, còn `approve` bị dùng làm cờ vạn năng cho "lập phiếu chi", "lập
# phiếu thu" và "gán chứng từ" — bật một ô là tiền ra được. Đúng bệnh tester ghi.
#
# `MODULE` giữ khoá `ke_toan` (đổi khoá là mọi hàng `role_permissions` cũ trỏ vào hư không) nhưng
# nay chỉ còn nghĩa MÀN ĐƠN MUA HÀNG. Năm màn kia có khoá riêng.
#
# ĐỘNG TỪ cũng được gọi đúng tên: LẬP phiếu nay là `create` chứ không phải `approve`.
# Migration 0178 ánh xạ `create = create OR approve` khi sao chép, nếu không kế toán đang lập
# phiếu bằng ô `approve` sẽ mất quyền ngay khi bản này lên.
MODULE = "ke_toan"                    # màn Đơn mua hàng (hộp thư kế toán)
MODULE_PC = "phieu_chi"               # màn Phiếu chi / UNC
MODULE_PT = "phieu_thu"               # màn Phiếu thu
MODULE_CN_TRA = "cong_no_phai_tra"    # màn Công nợ phải trả
MODULE_CN_THU = "cong_no_phai_thu"    # màn Công nợ phải thu
MODULE_TKNH = "tk_ngan_hang"          # màn Tài khoản ngân hàng
# Module RIÊNG cho "Báo cáo" (chủ chốt 04/09/2026: "báo cáo đó là một module riêng mà") — trước
# 10 endpoint dưới đây gác bằng MODULE_CN_TRA/MODULE_CN_THU (lệch với sidebar đã gộp báo cáo
# thành MỘT mục), migration 0260 sao chép quyền cũ sang. Xem = xem báo cáo/xuất Excel/in, Thao
# tác = khoá/mở kỳ (`POST /khoa-so`) — một động từ cho cả hai phân hệ, không lệch nữa.
MODULE_BAO_CAO = "bao_cao_cong_no"


NotificationRepo = Annotated[
    ModuleNotificationRepository, Depends(get_module_notification_repository)
]


def _notify_accounting_changed(
    code: str | None = None,
    *,
    event_type: str = "accounting_changed",
    notifications: ModuleNotificationRepository | None = None,
    channel: str | None = None,
    actor_user_id: int | None = None,
    recipient_user_id: int | None = None,
    **extra,
) -> None:
    """Tín hiệu nhẹ cho các màn Kế toán/Thu mua tự refetch qua SSE."""
    if notifications is not None and channel is not None:
        notifications.create(
            channel=channel,
            event_type=event_type,
            actor_user_id=actor_user_id,
            recipient_user_id=recipient_user_id,
            source_code=code,
        )
    hub.broadcast({
        "type": event_type,
        "code": code,
        "actor_user_id": actor_user_id,
        "recipient_user_id": recipient_user_id,
        **extra,
    })


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AccountingNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AccountingValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, AccountingConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/api/accounting/inbox", response_model=PurchaseRequestListOut)
def accounting_inbox(
    purchases: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    supplier_id: int | None = Query(default=None),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    needed_from: date | None = Query(default=None),
    needed_to: date | None = Query(default=None),
    expected_receipt_from: date | None = Query(default=None),
    expected_receipt_to: date | None = Query(default=None),
    deposit_status: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PurchaseRequestListOut:
    # Kế toán có `ke_toan` scope `all` ⇒ `_purchase_scope` trả `all` ⇒ thấy HẾT đơn mua, đúng như
    # họ cần để lập phiếu chi. Truyền `actor` để chính lối này không thành lỗ nhìn xuyên phạm vi.
    rows, total = purchases.list_requests(
        q=q,
        status=status_,
        supplier_id=supplier_id,
        created_from=created_from,
        created_to=created_to,
        needed_from=needed_from,
        needed_to=needed_to,
        expected_receipt_from=expected_receipt_from,
        expected_receipt_to=expected_receipt_to,
        deposit_status=deposit_status,
        sort=sort,
        page=page,
        size=size,
        actor=user,
        # Đơn NHÁP là thu mua còn đang sửa, CHƯA gửi duyệt — không thuộc hộp thư kế toán (chủ
        # 04/08/2026). Chặn ở API chứ không chỉ giấu ở giao diện.
        exclude_statuses=[PR_DRAFT],
    )
    return PurchaseRequestListOut(items=rows, total=total, page=page, size=size)


@router.get("/api/accounting/payables", response_model=PayablesSummaryOut)
def accounting_payables(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_CN_TRA, "read"))],
    q: str | None = Query(default=None),
    filter_: str = Query(default="all", alias="filter"),
    aging_bucket: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PayablesSummaryOut:
    # Chỉ ĐỌC — không đẻ ô quyền mới, `ke_toan:read` là đủ. Không phân trang: cắt trang là ra
    # TỔNG sai.
    #
    # `q` lọc ở SERVER chứ không lọc trên danh sách đã trả về: NCC đã trả hết và im lặng lâu thì
    # KHÔNG có dòng nào trong danh sách để mà lọc — phải để service lôi họ ra.
    #
    # `aging_bucket` = một khoá rổ tuổi (`AGING_KEYS`). Router chỉ chuyển tiếp; việc gom rổ và
    # hiểu khoá nằm ở service.
    return PayablesSummaryOut(
        **svc.payables_summary(
            q=q, filter_=filter_, aging_bucket=aging_bucket, page=page, size=size
        )
    )


@router.get("/api/accounting/payables/{supplier_id}", response_model=PayablesDetailOut)
def accounting_payables_detail(
    supplier_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_CN_TRA, "read"))],
    all_history: bool = Query(default=False),
) -> PayablesDetailOut:
    # `all_history` bỏ mốc kỳ cho riêng rổ "đã chi" — nút "Xem lịch sử cũ hơn". Chỉ nới cho MỘT
    # NCC nên vẫn nhẹ; đừng bao giờ nới cho bảng tổng hợp.
    return PayablesDetailOut(**svc.payables_detail(supplier_id, all_history=all_history))


@router.get("/api/accounting/receivables", response_model=ReceivablesSummaryOut)
def accounting_receivables(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_CN_THU, "read"))],
    q: str | None = Query(default=None),
    filter_: str = Query(default="all", alias="filter"),
    # CÙNG TÊN với bên phải trả (`aging_bucket`), đừng đặt tên khác: hai màn song sinh mà tham
    # số lệch tên là chỗ người ta chép URL từ màn này sang màn kia rồi bộ lọc im lặng không chạy.
    aging_bucket: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> ReceivablesSummaryOut:
    return ReceivablesSummaryOut(
        **svc.receivables_summary(
            q=q, filter_=filter_, aging_bucket=aging_bucket, page=page, size=size
        )
    )


@router.get("/api/accounting/receivables/{customer_id}", response_model=ReceivablesDetailOut)
def accounting_receivables_detail(
    customer_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_CN_THU, "read"))],
    all_history: bool = Query(default=False),
) -> ReceivablesDetailOut:
    return ReceivablesDetailOut(**svc.receivables_detail(customer_id, all_history=all_history))


# --- BÁO CÁO TỔNG HỢP CÔNG NỢ THEO KỲ (docs/prd-bao-cao-cong-no.md §5.1) -------------------
#
# ⚠️ ĐỪNG nhầm với `/payables` và `/receivables` ngay trên: hai cửa kia là ảnh chụp TẠI HÔM NAY
# để đi đòi nợ (có phân trang, có phân tuổi, cứng kỳ 3 tháng). Hai cửa dưới là SỔ THEO KỲ — chọn
# khoảng ngày bất kỳ, trả về TOÀN BỘ đối tượng, không phân trang.
#
# KHÔNG phân trang có chủ ý: sổ tổng hợp phải cộng đúng dòng TỔNG CỘNG, mà cắt trang là ra tổng
# của trang chứ không phải tổng của kỳ. Bản xuất MISA cũng một mạch 202/275 dòng.
#
# Dùng lại quyền `read` của chính màn công nợ tương ứng: ai xem được công nợ thì xem được sổ của
# nó — đẻ thêm một ô quyền nữa chỉ tổ có người xem được số này mà không xem được số kia.


def _khoang_ngay(tu_ngay: date, den_ngay: date) -> None:
    """Chặn khoảng ngày ngược. Không có ô này thì báo cáo trả về bảng rỗng một cách bí ẩn: mọi
    chứng từ đều rơi vào nhánh 'ngoài kỳ' và không ai hiểu vì sao."""
    if tu_ngay > den_ngay:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Từ ngày phải trước hoặc bằng đến ngày.",
        )


def _loc_ro(bc: dict, khoa: str | None) -> dict:
    """Lọc sổ theo RỔ TUỔI. Chỉ giữ đối tượng có tiền trong rổ đó — số tiền của họ giữ NGUYÊN.

    Dòng TỔNG cũng tính lại theo phần còn hiện, nhưng DẢI RỔ thì giữ nguyên toàn màn: dải là bức
    tranh tổng, bấm vào để soi chứ không phải để đổi bức tranh (cùng nếp `AgingStrip` đang chạy).
    """
    from ..services.accounting_service import AGING_KEYS

    if khoa not in AGING_KEYS:
        return bc
    giu = [d for d in bc["items"] if (d.get("aging") or {}).get(khoa, {}).get("amount", 0) > 0]
    cot = ("dau_no", "dau_co", "ps_no", "ps_co", "cuoi_no", "cuoi_co")
    return {
        **bc,
        "items": giu,
        "tong": {"so_dong": len(giu), **{k: sum(d[k] for d in giu) for k in cot}},
    }


@router.get("/api/accounting/reports/receivables", response_model=BaoCaoCongNoOut)
def bao_cao_tong_hop_phai_thu(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
    #: Khoá rổ tuổi — chỉ giữ đối tượng còn tiền trong rổ đó. Lọc chọn DÒNG, KHÔNG cắt SỐ: 9 cột
    #: tiền của họ vẫn hiện đủ. Khoá lạ thì BỎ QUA, không ném 422 vào mặt người đang xem sổ.
    aging_bucket: str | None = Query(default=None),
) -> BaoCaoCongNoOut:
    _khoang_ngay(tu_ngay, den_ngay)
    return BaoCaoCongNoOut(
        **_loc_ro(
            svc.bao_cao_phai_thu(tu_ngay=tu_ngay, den_ngay=den_ngay),
            aging_bucket,
        )
    )


@router.get("/api/accounting/reports/payables", response_model=BaoCaoCongNoOut)
def bao_cao_tong_hop_phai_tra(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
    #: Khoá rổ tuổi — chỉ giữ đối tượng còn tiền trong rổ đó. Lọc chọn DÒNG, KHÔNG cắt SỐ: 9 cột
    #: tiền của họ vẫn hiện đủ. Khoá lạ thì BỎ QUA, không ném 422 vào mặt người đang xem sổ.
    aging_bucket: str | None = Query(default=None),
) -> BaoCaoCongNoOut:
    _khoang_ngay(tu_ngay, den_ngay)
    return BaoCaoCongNoOut(
        **_loc_ro(
            svc.bao_cao_phai_tra(tu_ngay=tu_ngay, den_ngay=den_ngay),
            aging_bucket,
        )
    )


# SỔ CHI TIẾT của MỘT đối tượng (PRD §5.1) — mở ra khi bấm một dòng ở sổ tổng hợp.
# `doi_tuong_id` BỎ TRỐNG = dòng gom "không gắn đối tượng" (§❸), không phải "lấy tất cả".
@router.get("/api/accounting/reports/receivables/so-chi-tiet", response_model=SoChiTietCongNoOut)
def so_chi_tiet_phai_thu(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
    doi_tuong_id: int | None = Query(default=None),
) -> SoChiTietCongNoOut:
    _khoang_ngay(tu_ngay, den_ngay)
    return SoChiTietCongNoOut(
        **svc.so_chi_tiet_phai_thu(
            doi_tuong_id=doi_tuong_id, tu_ngay=tu_ngay, den_ngay=den_ngay
        )
    )


@router.get("/api/accounting/reports/payables/so-chi-tiet", response_model=SoChiTietCongNoOut)
def so_chi_tiet_phai_tra(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
    doi_tuong_id: int | None = Query(default=None),
) -> SoChiTietCongNoOut:
    _khoang_ngay(tu_ngay, den_ngay)
    return SoChiTietCongNoOut(
        **svc.so_chi_tiet_phai_tra(
            doi_tuong_id=doi_tuong_id, tu_ngay=tu_ngay, den_ngay=den_ngay
        )
    )


@router.get("/api/accounting/reports/receivables.xlsx")
def bao_cao_tong_hop_phai_thu_xlsx(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
) -> Response:
    _khoang_ngay(tu_ngay, den_ngay)
    bc = svc.bao_cao_phai_thu(tu_ngay=tu_ngay, den_ngay=den_ngay)
    return _tra_file(bc)



@router.get("/api/accounting/khoa-so", response_model=list[CongNoKhoaSoRow])
def get_cong_no_khoa_so_history(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    phan_he: str | None = Query(default=None),
) -> list[CongNoKhoaSoRow]:
    svc = CongNoKhoaSoService(db)
    return [CongNoKhoaSoRow(**r) for r in svc.history(phan_he=phan_he)]


@router.get("/api/accounting/khoa-so/ky", response_model=list[CongNoKyRow])
def get_cong_no_ky_list(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    #: `phai_thu` (TK 131) | `phai_tra` (TK 331). Bỏ trống = gộp cả hai — chỉ dùng cho màn lịch sử.
    #: Hai sổ ĐỘC LẬP: chốt sổ mua hàng không được đụng tới sổ bán hàng (sửa 04/09/2026).
    phan_he: str | None = Query(default=None),
) -> list[CongNoKyRow]:
    svc = CongNoKhoaSoService(db)
    return [CongNoKyRow(**r) for r in svc.list_ky(phan_he=phan_he)]


@router.get("/api/accounting/khoa-so/trang-thai", response_model=CongNoKhoaSoTrangThaiOut)
def get_cong_no_khoa_so_trang_thai(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
    #: `phai_thu` (131) | `phai_tra` (331). Bỏ trống = xét gộp cả hai.
    phan_he: str | None = Query(default=None),
) -> CongNoKhoaSoTrangThaiOut:
    """Khoảng `[tu_ngay, den_ngay]` đang khóa trọn / khóa một phần / chưa khóa?

    Có cửa này thì màn báo cáo hỏi thẳng đúng kỳ NÓ đang xem, thay vì dò trong danh sách kỳ tháng
    rồi so bằng đúng hai đầu ngày — cách cũ không bao giờ khớp với kỳ lẻ (sửa 04/09/2026).
    """
    _khoang_ngay(tu_ngay, den_ngay)
    svc = CongNoKhoaSoService(db)
    tron, mot_phan = svc.repo.khoa_ca_khoang(tu_ngay, den_ngay, phan_he)
    return CongNoKhoaSoTrangThaiOut(
        tu_ngay=tu_ngay, den_ngay=den_ngay, da_khoa=tron, khoa_mot_phan=mot_phan
    )


@router.post("/api/accounting/khoa-so", response_model=CongNoKhoaSoRow, status_code=status.HTTP_201_CREATED)
def set_cong_no_khoa_so(
    payload: CongNoKhoaSoIn,
    db: Annotated[Session, Depends(get_db)],
    acct_svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "update"))],
) -> CongNoKhoaSoRow:
    svc = CongNoKhoaSoService(db, acct_svc=acct_svc)
    if payload.hanh_dong == "khoa":
        try:
            log = svc.chot_ky(
                phan_he=payload.phan_he,
                tu_ngay=payload.tu_ngay,
                den_ngay=payload.den_ngay,
                ten=payload.ten,
                user_id=user.id,
            )
        except CongNoKhoaSoError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
    else:
        try:
            log = svc.mo_ky(
                phan_he=payload.phan_he,
                tu_ngay=payload.tu_ngay,
                den_ngay=payload.den_ngay,
                user_id=user.id,
            )
        except CongNoKhoaSoError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
    return CongNoKhoaSoRow(
        id=log.id,
        phan_he=log.phan_he,
        tu_ngay=log.tu_ngay,
        den_ngay=log.den_ngay,
        hanh_dong=log.hanh_dong,
        nguoi_khoa_ten=user.name,
        khoa_luc=log.khoa_luc,
        ten=log.ten,
    )


@router.get("/api/accounting/reports/payables.xlsx")
def bao_cao_tong_hop_phai_tra_xlsx(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_BAO_CAO, "read"))],
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
) -> Response:
    _khoang_ngay(tu_ngay, den_ngay)
    bc = svc.bao_cao_phai_tra(tu_ngay=tu_ngay, den_ngay=den_ngay)
    return _tra_file(bc)


def _tra_file(bao_cao: dict) -> Response:
    return Response(
        content=bao_cao_cong_no_excel.xuat_xlsx(bao_cao),
        media_type=bao_cao_cong_no_excel.MEDIA_XLSX,
        headers={
            "Content-Disposition":
                f'attachment; filename="{bao_cao_cong_no_excel.ten_file(bao_cao)}"'
        },
    )


@router.get("/api/accounting/sales-invoices", response_model=SalesInvoiceListOut)
def list_sales_invoices(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[
        User,
        Depends(
            require_any_permission(
                (MODULE_PT, "read"),
                (MODULE_CN_THU, "read"),
                ("don_hang_ban", "read"),
            )
        ),
    ],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    orders: Annotated[OrderService, Depends(get_order_service)],
    order_id: int = Query(gt=0),
) -> SalesInvoiceListOut:
    if not (
        authz.can(user, MODULE_PT, "read")
        or authz.can(user, MODULE_CN_THU, "read")
    ):
        try:
            orders.get(
                order_id=order_id,
                actor=user,
                scope=authz.scope_for(user, "don_hang_ban") or "own",
            )
        except (OrderNotFound, OrderForbidden):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy đơn hàng bán.",
            ) from None
    try:
        return SalesInvoiceListOut(**svc.list_order_sales_invoices(order_id))
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.post(
    "/api/accounting/sales-invoices",
    response_model=SalesInvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_sales_invoice(
    payload: SalesInvoiceIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "create"))],
) -> SalesInvoiceOut:
    try:
        row = svc.create_sales_invoice(actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(
        row.get("order_code"),
        event_type="sales_invoice_created",
        invoice_id=row.get("id"),
        invoice_number=row.get("invoice_number"),
    )
    return SalesInvoiceOut(**row)


@router.post(
    "/api/accounting/sales-invoices/{invoice_id}/cancel",
    response_model=SalesInvoiceOut,
)
def cancel_sales_invoice(
    invoice_id: int,
    payload: CancelSalesInvoiceIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "cancel"))],
) -> SalesInvoiceOut:
    try:
        row = svc.cancel_sales_invoice(invoice_id, actor=user, reason=payload.reason)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(
        row.get("order_code"),
        event_type="sales_invoice_cancelled",
        invoice_id=row.get("id"),
        invoice_number=row.get("invoice_number"),
    )
    return SalesInvoiceOut(**row)


@router.get("/api/accounting/company-bank-accounts", response_model=list[CompanyBankAccountOut])
def list_company_bank_accounts(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_TKNH, "read"))],
    active_only: bool = Query(default=False),
    usage: str | None = Query(default=None),
):
    try:
        return svc.list_company_accounts(active_only=active_only, usage=usage)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.post(
    "/api/accounting/company-bank-accounts",
    response_model=CompanyBankAccountOut,
    status_code=status.HTTP_201_CREATED,
)
def create_company_bank_account(
    payload: CompanyBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_TKNH, "update"))],
):
    try:
        return svc.create_company_account(actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/accounting/company-bank-accounts/{account_id}", response_model=CompanyBankAccountOut)
def update_company_bank_account(
    account_id: int,
    payload: CompanyBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_TKNH, "update"))],
):
    try:
        return svc.update_company_account(account_id, actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.patch("/api/accounting/company-bank-accounts/{account_id}/toggle-active", response_model=CompanyBankAccountOut)
def toggle_company_bank_account(
    account_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_TKNH, "update"))],
):
    try:
        return svc.toggle_company_account(account_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.get("/api/accounting/supplier-bank-accounts", response_model=list[SupplierBankAccountOut])
def list_supplier_bank_accounts(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[
        User,
        Depends(require_any_permission((MODULE_TKNH, "read"), ("nha_cung_cap", "read"))),
    ],
    supplier_id: int | None = Query(default=None),
    active_only: bool = Query(default=False),
):
    return svc.list_supplier_accounts(supplier_id=supplier_id, active_only=active_only)


@router.post(
    "/api/accounting/supplier-bank-accounts",
    response_model=SupplierBankAccountOut,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_bank_account(
    payload: SupplierBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE_TKNH, "update"), ("nha_cung_cap", "update"))),
    ],
):
    try:
        return svc.create_supplier_account(actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/accounting/supplier-bank-accounts/{account_id}", response_model=SupplierBankAccountOut)
def update_supplier_bank_account(
    account_id: int,
    payload: SupplierBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE_TKNH, "update"), ("nha_cung_cap", "update"))),
    ],
):
    try:
        return svc.update_supplier_account(account_id, actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.patch("/api/accounting/supplier-bank-accounts/{account_id}/toggle-active", response_model=SupplierBankAccountOut)
def toggle_supplier_bank_account(
    account_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE_TKNH, "update"), ("nha_cung_cap", "update"))),
    ],
):
    try:
        return svc.toggle_supplier_account(account_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.get("/api/accounting/payment-vouchers", response_model=PaymentVoucherListOut)
def list_payment_vouchers(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_PC, "read"))],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
    voucher_type: str | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    purchase_request_id: int | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
):
    rows, total, totals = svc.list_vouchers(
        q=q,
        status=status_,
        source_type=source_type,
        voucher_type=voucher_type,
        supplier_id=supplier_id,
        purchase_request_id=purchase_request_id,
        sort=sort,
        page=page,
        size=size,
    )
    return PaymentVoucherListOut(items=rows, total=total, page=page, size=size, **totals)


@router.get("/api/accounting/payment-vouchers/{voucher_id}", response_model=PaymentVoucherOut)
def get_payment_voucher(
    voucher_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_PC, "read"))],
):
    try:
        return PaymentVoucherOut(**svc.get_voucher(voucher_id))
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.post(
    "/api/accounting/payment-vouchers",
    response_model=PaymentVoucherOut,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_voucher(
    payload: PaymentVoucherIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    notifications: NotificationRepo,
    user: Annotated[User, Depends(require_permission(MODULE_PC, "create"))],
):
    try:
        row = svc.create_voucher(actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    purchase_code = row.get("purchase_request_code")
    _notify_accounting_changed(
        purchase_code or row.get("code"),
        event_type="payment_voucher_created" if purchase_code else "accounting_changed",
        voucher_code=row.get("code"),
        notifications=notifications if purchase_code else None,
        channel=CHANNEL_THU_MUA if purchase_code else None,
        actor_user_id=user.id,
        recipient_user_id=row.get("purchase_created_by_user_id"),
    )
    return PaymentVoucherOut(**row)


@router.post(
    "/api/accounting/payment-vouchers/batch",
    response_model=VoucherBatchOut,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_vouchers_batch(
    payload: VoucherBatchIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    notifications: NotificationRepo,
    user: Annotated[User, Depends(require_permission(MODULE_PC, "create"))],
) -> VoucherBatchOut:
    """Thanh toán NHIỀU đợt giao của CÙNG một NCC trong MỘT lượt (04/09/2026, §Công nợ phải trả).

    Vẫn ra N `PaymentVoucher` riêng (mỗi phiếu một đợt, đúng luật cũ) — batch chỉ gộp thao tác
    nhập liệu, không gộp chứng từ.
    """
    body = payload.model_dump()
    items = body.pop("items")
    try:
        rows = svc.create_vouchers_batch(actor=user, items=items, shared=body)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    for row in rows:
        purchase_code = row.get("purchase_request_code")
        _notify_accounting_changed(
            purchase_code or row.get("code"),
            event_type="payment_voucher_created" if purchase_code else "accounting_changed",
            voucher_code=row.get("code"),
            notifications=notifications if purchase_code else None,
            channel=CHANNEL_THU_MUA if purchase_code else None,
            actor_user_id=user.id,
            recipient_user_id=row.get("purchase_created_by_user_id"),
        )
    return VoucherBatchOut(
        vouchers=[PaymentVoucherOut(**r) for r in rows],
        total_amount=sum(int(r.get("amount_vnd") or 0) for r in rows),
    )


# ĐÃ GỠ 07/08/2026 — `PUT /api/accounting/payment-vouchers/{id}`. Phiếu chi phát hành ra là tiền
# đã rời két, không sửa. Sai thì huỷ rồi lập lại; chỉ còn đính kèm tài liệu là sửa được.


@router.post("/api/accounting/payment-vouchers/{voucher_id}/cancel", response_model=PaymentVoucherOut)
def cancel_payment_voucher(
    voucher_id: int,
    payload: CancelPaymentVoucherIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    notifications: NotificationRepo,
    user: Annotated[User, Depends(require_permission(MODULE_PC, "cancel"))],
):
    try:
        row = svc.cancel_voucher(voucher_id, actor=user, reason=payload.reason)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    purchase_code = row.get("purchase_request_code")
    _notify_accounting_changed(
        purchase_code or row.get("code"),
        event_type="payment_voucher_cancelled" if purchase_code else "accounting_changed",
        voucher_code=row.get("code"),
        notifications=notifications if purchase_code else None,
        channel=CHANNEL_THU_MUA if purchase_code else None,
        actor_user_id=user.id,
        recipient_user_id=row.get("purchase_created_by_user_id"),
    )
    return PaymentVoucherOut(**row)


@router.get(
    "/api/accounting/payment-vouchers/{voucher_id}/attachments",
    response_model=PaymentVoucherAttachmentListOut,
)
def list_payment_voucher_attachments(
    voucher_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_PC, "read"))],
):
    try:
        items = svc.list_voucher_attachments(voucher_id)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    return PaymentVoucherAttachmentListOut(
        items=[PaymentVoucherAttachmentOut(**item) for item in items]
    )


@router.post(
    "/api/accounting/payment-vouchers/{voucher_id}/attachments",
    response_model=PaymentVoucherAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_payment_voucher_attachment(
    voucher_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PC, "create"))],
    file: UploadFile = File(...),
):
    data = file.file.read()
    try:
        row = svc.add_voucher_attachment(
            voucher_id,
            actor=user,
            file_name=file.filename,
            content_type=file.content_type,
            data=data,
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed()
    return PaymentVoucherAttachmentOut(**row)


@router.delete(
    "/api/accounting/payment-vouchers/{voucher_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_payment_voucher_attachment(
    voucher_id: int,
    attachment_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PC, "create"))],
) -> Response:
    try:
        svc.delete_voucher_attachment(voucher_id, attachment_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/accounting/payment-receipts", response_model=PaymentReceiptListOut)
def list_payment_receipts(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_PT, "read"))],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    payment_voucher_id: int | None = Query(default=None),
    source_type: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
):
    rows, total = svc.list_receipts(
        q=q,
        status=status_,
        payment_voucher_id=payment_voucher_id,
        source_type=source_type,
        sort=sort,
        page=page,
        size=size,
    )
    return PaymentReceiptListOut(items=rows, total=total, page=page, size=size)


@router.post(
    "/api/accounting/payment-receipts",
    response_model=PaymentReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def create_other_payment_receipt(
    payload: PaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "create"))],
):
    try:
        row = svc.create_other_receipt(actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(row.get("code"))
    return PaymentReceiptOut(**row)


@router.post(
    "/api/accounting/sales-invoices/{invoice_id}/receipts",
    response_model=PaymentReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def create_sales_invoice_receipt(
    invoice_id: int,
    payload: PaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "create"))],
) -> PaymentReceiptOut:
    try:
        row = svc.create_sales_invoice_receipt(
            invoice_id, actor=user, **payload.model_dump()
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(
        row.get("order_code") or row.get("code"),
        event_type="sales_invoice_receipt_created",
        invoice_id=row.get("sales_invoice_id"),
        receipt_code=row.get("code"),
    )
    return PaymentReceiptOut(**row)


@router.post(
    "/api/accounting/payment-vouchers/{voucher_id}/receipts",
    response_model=PaymentReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_receipt(
    voucher_id: int,
    payload: PaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "create"))],
):
    try:
        row = svc.create_receipt(voucher_id, actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(row.get("code"))
    return PaymentReceiptOut(**row)


@router.put("/api/accounting/payment-receipts/{receipt_id}", response_model=PaymentReceiptOut)
def update_payment_receipt(
    receipt_id: int,
    payload: PaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "create"))],
):
    try:
        row = svc.update_receipt(receipt_id, actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(row.get("code"))
    return PaymentReceiptOut(**row)


@router.post(
    "/api/accounting/payment-receipts/{receipt_id}/mark-received",
    response_model=PaymentReceiptOut,
)
def mark_payment_receipt_received(
    receipt_id: int,
    payload: MarkPaymentReceiptReceivedIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "manage_status"))],
):
    try:
        row = svc.mark_receipt_received(
            receipt_id, actor=user, bank_reference=payload.bank_reference
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(row.get("code"))
    return PaymentReceiptOut(**row)


@router.post("/api/accounting/payment-receipts/{receipt_id}/cancel", response_model=PaymentReceiptOut)
def cancel_payment_receipt(
    receipt_id: int,
    payload: CancelPaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "cancel"))],
):
    try:
        row = svc.cancel_receipt(receipt_id, actor=user, reason=payload.reason)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed(row.get("code"))
    return PaymentReceiptOut(**row)


@router.get(
    "/api/accounting/payment-receipts/{receipt_id}/attachments",
    response_model=PaymentReceiptAttachmentListOut,
)
def list_payment_receipt_attachments(
    receipt_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE_PT, "read"))],
):
    try:
        items = svc.list_receipt_attachments(receipt_id)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    return PaymentReceiptAttachmentListOut(
        items=[PaymentReceiptAttachmentOut(**item) for item in items]
    )


@router.post(
    "/api/accounting/payment-receipts/{receipt_id}/attachments",
    response_model=PaymentReceiptAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_payment_receipt_attachment(
    receipt_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "create"))],
    file: UploadFile = File(...),
):
    data = file.file.read()
    try:
        row = svc.add_receipt_attachment(
            receipt_id,
            actor=user,
            file_name=file.filename,
            content_type=file.content_type,
            data=data,
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed()
    return PaymentReceiptAttachmentOut(**row)


@router.delete(
    "/api/accounting/payment-receipts/{receipt_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_payment_receipt_attachment(
    receipt_id: int,
    attachment_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE_PT, "create"))],
) -> Response:
    try:
        svc.delete_receipt_attachment(receipt_id, attachment_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    _notify_accounting_changed()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
