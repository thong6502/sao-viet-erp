"""Router — Phiếu nhập/xuất kho + lô + ngưỡng tồn (spec-kho-de-nghi §5–§7, §9).

Điểm phân quyền quan trọng: mọi số TIỀN (`don_gia`, `thanh_tien`, `gia_von`,
`don_gia_nhap`) chỉ được điền khi người gọi có `can_view_cost`. Thiếu quyền thì không
những ẩn cột mà còn KHÔNG TÍNH — số không lọt ra qua response, kể cả khi mở DevTools.
Bản in 01-VT/02-VT dùng chính response này nên tự động bỏ 2 cột tiền.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_authorization_service, require_permission
from ..models.stock_voucher import VOUCHER_NHAP
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.document_sequence_repo import DocumentSequenceRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.stock_lot_repo import StockLotRepository, StockThresholdRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.stock_request_repo import StockRequestRepository
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..repositories.stock_voucher_repo import StockVoucherRepository
from ..repositories.user_repo import UserRepository
from ..schemas.stock import (
    AllocationLineOut,
    AllocationOut,
    MaterialHistoryOut,
    MaterialXuatRow,
    StockLotOut,
    StockThresholdIn,
    StockThresholdOut,
    StockVoucherAttachmentListOut,
    StockVoucherAttachmentOut,
    StockVoucherCancel,
    StockVoucherCreate,
    StockVoucherLineOut,
    StockVoucherOut,
    StockVoucherPage,
)
from ..services.vat_lieu_kho_service import HANG_NHAN, VatLieuKhoService
from ..services.rbac_service import AuthorizationService
from ..services.sequence_service import SequenceService
from ..services.stock_request_service import StockRequestService
from ..services.stock_voucher_service import StockVoucherError, StockVoucherService

router = APIRouter(prefix="/api/kho/phieu", tags=["kho-phieu"])
# Ngưỡng tồn để PREFIX RIÊNG, không nhét dưới /phieu: `/phieu/nguong` là path 1 đoạn nên sẽ
# bị `/phieu/{voucher_id}` nuốt trước (FastAPI khớp theo thứ tự khai báo) → 422.
threshold_router = APIRouter(prefix="/api/kho/nguong-ton", tags=["kho-nguong"])
MODULE = "kho"


def _hang_service(db: Session) -> VatLieuKhoService:
    return VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))


def get_service(db: Annotated[Session, Depends(get_db)]) -> StockVoucherService:
    sequence = SequenceService(DocumentSequenceRepository(db))
    requests = StockRequestRepository(db)
    lots = StockLotRepository(db)
    hang = _hang_service(db)
    request_service = StockRequestService(
        requests, lots, StockThresholdRepository(db), sequence, hang=hang)
    return StockVoucherService(
        StockVoucherRepository(db), requests, lots, sequence, request_service, hang,
    )


Service = Annotated[StockVoucherService, Depends(get_service)]
Db = Annotated[Session, Depends(get_db)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _err(e: StockVoucherError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _serialize(v, *, svc: StockVoucherService, db: Session, can_view_cost: bool,
               hang_map: dict | None = None, lot_map: dict | None = None,
               req_map: dict | None = None) -> StockVoucherOut:
    """`hang_map`/`lot_map`/`req_map` dựng SẴN theo cả trang (list) để tránh N+1; gọi lẻ 1 phiếu
    thì để None, hàm tự nạp mỗi map 1 query cho các dòng của phiếu đó."""
    users = UserRepository(db)
    khos = KhoHangRepository(db)
    requests = StockRequestRepository(db)
    if req_map is None:
        req_map = requests.by_ids_with_lines([v.request_id])
    if hang_map is None:
        hang_map = svc.hang.map_theo_cap([(ln.hang_loai, ln.hang_id) for ln in v.lines])
    if lot_map is None:
        lot_map = svc.lots.by_ids([ln.lot_id for ln in v.lines])

    req = req_map.get(v.request_id)
    line_dvt = {ln.id: ln.dvt for ln in (req.lines if req is not None else [])}
    goc_map = svc.hang.don_vi_goc_map([(ln.hang_loai, ln.hang_id) for ln in v.lines])

    lines: list[StockVoucherLineOut] = []
    gia_von_total = 0
    for ln in v.lines:
        key = (ln.hang_loai, ln.hang_id)
        m = hang_map.get(key)
        lot = lot_map.get(ln.lot_id) if ln.lot_id else None
        # NHẬP: đơn giá và `so_luong` cùng ở đơn vị người khai. XUẤT: giá của lô theo ĐƠN VỊ GỐC
        # nên phải nhân `sl_goc` — nhân nhầm `so_luong` là lệch đúng bằng hệ số quy đổi.
        if v.loai == VOUCHER_NHAP:
            unit, sl_tien = int(ln.don_gia or 0), float(ln.so_luong)
        else:
            unit, sl_tien = int(getattr(lot, "don_gia_nhap", 0) or 0), float(ln.sl_goc)
        thanh_tien = int(round(unit * sl_tien))
        gia_von_total += thanh_tien
        lines.append(StockVoucherLineOut(
            id=ln.id,
            request_line_id=ln.request_line_id,
            hang_loai=ln.hang_loai,
            hang_id=ln.hang_id,
            hang_ma=getattr(m, "ma", None),
            hang_ten=getattr(m, "ten", None),
            dvt=line_dvt.get(ln.request_line_id),
            lot_id=ln.lot_id,
            ma_lo=getattr(lot, "ma_lo", None),
            so_luong=float(ln.so_luong),
            sl_goc=float(ln.sl_goc),
            don_vi_goc=goc_map.get(key),
            ghi_chu=ln.ghi_chu,
            don_gia=unit if can_view_cost else None,
            thanh_tien=thanh_tien if can_view_cost else None,
        ))

    kho = khos.get(v.kho_id)
    lap = users.get_by_id(v.nguoi_lap_id) if v.nguoi_lap_id else None
    ghi_so_u = users.get_by_id(v.nguoi_ghi_so_id) if getattr(v, "nguoi_ghi_so_id", None) else None
    # Ai đề nghị / ai duyệt lấy từ đề nghị gốc (phiếu ứng theo đề nghị đã duyệt).
    de_nghi_u = users.get_by_id(req.nguoi_tao_id) if req and req.nguoi_tao_id else None
    duyet_u = (
        users.get_by_id(req.nguoi_duyet_id)
        if req and getattr(req, "nguoi_duyet_id", None)
        else None
    )
    return StockVoucherOut(
        id=v.id, ma=v.ma, loai=v.loai,
        request_id=v.request_id, request_ma=getattr(req, "ma", None),
        kho_id=v.kho_id, kho_ten=getattr(kho, "ten", None),
        ngay=v.ngay, nguoi_lap_id=v.nguoi_lap_id, nguoi_lap_ten=getattr(lap, "name", None),
        nguoi_de_nghi_ten=getattr(de_nghi_u, "name", None),
        nguoi_duyet_ten=getattr(duyet_u, "name", None),
        nguoi_ghi_so_ten=getattr(ghi_so_u, "name", None),
        nguoi_giao_nhan=v.nguoi_giao_nhan, ghi_chu=v.ghi_chu,
        trang_thai=v.trang_thai, ghi_so_luc=v.ghi_so_luc, created_at=v.created_at,
        lines=lines,
        gia_von=gia_von_total if can_view_cost else None,
    )


@router.get("", response_model=StockVoucherPage)
def list_vouchers(
    svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    loai: str | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    request_id: int | None = Query(default=None),
    kho_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> StockVoucherPage:
    rows, total = svc.vouchers.list(
        loai=loai, trang_thai=trang_thai, request_id=request_id,
        kho_id=kho_id, q=q, page=page, size=size,
    )
    can_view_cost = authz.can(user, MODULE, "view_cost")
    # Nạp SẴN mã hàng / lô / đề nghị của cả trang trong vài query (tránh N+1 trong _serialize).
    hang_map = _hang_service(db).map_theo_cap(
        [(ln.hang_loai, ln.hang_id) for v in rows for ln in v.lines])
    lot_map = svc.lots.by_ids([ln.lot_id for v in rows for ln in v.lines])
    req_map = StockRequestRepository(db).by_ids_with_lines([v.request_id for v in rows])
    return StockVoucherPage(
        items=[
            _serialize(v, svc=svc, db=db, can_view_cost=can_view_cost,
                       hang_map=hang_map, lot_map=lot_map, req_map=req_map)
            for v in rows
        ],
        total=total,
    )


@router.get("/{voucher_id}", response_model=StockVoucherOut)
def get_voucher(
    voucher_id: int, svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> StockVoucherOut:
    v = svc.vouchers.get_with_lines(voucher_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu")
    return _serialize(v, svc=svc, db=db, can_view_cost=authz.can(user, MODULE, "view_cost"))


@router.post("", response_model=StockVoucherOut, status_code=status.HTTP_201_CREATED)
def create_voucher(
    payload: StockVoucherCreate, svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> StockVoucherOut:
    try:
        v = svc.create(
            user=user, request_id=payload.request_id, kho_id=payload.kho_id, ma=payload.ma,
            lines=[ln.model_dump() for ln in payload.lines],
            ngay=payload.ngay, nguoi_giao_nhan=payload.nguoi_giao_nhan, ghi_chu=payload.ghi_chu,
        )
    except StockVoucherError as e:
        raise _err(e) from None
    return _serialize(v, svc=svc, db=db, can_view_cost=authz.can(user, MODULE, "view_cost"))


@router.post("/{voucher_id}/ghi-so", response_model=StockVoucherOut)
def post_voucher(
    voucher_id: int, svc: Service, db: Db, authz: Authz,
    # GHI SỔ gác quyền RIÊNG `post` (SoD): thủ kho lập nháp (create) không tự ghi sổ được;
    # Kế toán kho / QL kho (có can_post) mới chốt tồn.
    user: Annotated[User, Depends(require_permission(MODULE, "post"))],
) -> StockVoucherOut:
    """Ghi sổ — điểm DUY NHẤT tồn kho thay đổi."""
    try:
        v = svc.post(voucher_id, user)
    except StockVoucherError as e:
        raise _err(e) from None
    return _serialize(v, svc=svc, db=db, can_view_cost=authz.can(user, MODULE, "view_cost"))


@router.post("/{voucher_id}/huy", response_model=StockVoucherOut)
def cancel_voucher(
    voucher_id: int, payload: StockVoucherCancel, svc: Service, db: Db, authz: Authz,
    # Hủy phiếu = quyền của người GHI SỔ (kế toán kho / QL kho), KHÔNG phải người lập. Người lập
    # tạo phiếu là gửi luôn, không tự rút lại được (SoD: tách người cầm hàng & người chốt sổ).
    # BẮT BUỘC lý do → đề nghị chuyển 'Đã hủy' kèm lý do (kết thúc, không cấp lại).
    user: Annotated[User, Depends(require_permission(MODULE, "post"))],
) -> StockVoucherOut:
    try:
        v = svc.cancel(voucher_id, ly_do=payload.ly_do)
    except StockVoucherError as e:
        raise _err(e) from None
    return _serialize(v, svc=svc, db=db, can_view_cost=authz.can(user, MODULE, "view_cost"))


# --- Lô & gợi ý phân bổ ------------------------------------------------------

@router.get("/lo/goi-y", response_model=AllocationOut)
def suggest_allocation(
    svc: Service, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
    hang_loai: str = Query(...),
    hang_id: int = Query(..., gt=0),
    kho_id: int = Query(...),
    so_luong: float = Query(..., gt=0, description="Số theo ĐƠN VỊ GỐC của mặt hàng"),
) -> AllocationOut:
    """Gợi ý lấy hàng từ lô nào (FEFO → FIFO). Thủ kho sửa được — giá xuất là ĐÍCH DANH."""
    rows, thieu = svc.suggest_allocation((hang_loai, hang_id), kho_id, so_luong)
    can_view_cost = authz.can(user, MODULE, "view_cost")
    return AllocationOut(
        lines=[
            AllocationLineOut(
                lot_id=r["lot_id"], ma_lo=r["ma_lo"], ngay_nhap=r["ngay_nhap"],
                hsd=r["hsd"], sl_con_lai=r["sl_con_lai"], so_luong=r["so_luong"],
                don_gia_nhap=r["don_gia_nhap"] if can_view_cost else None,
            )
            for r in rows
        ],
        thieu=thieu,
    )


@router.get("/lo/danh-sach", response_model=list[StockLotOut])
def list_lots(
    svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    hang_loai: str | None = Query(default=None),
    hang_id: int | None = Query(default=None),
    kho_id: int | None = Query(default=None),
    con_hang: bool = Query(default=True),
) -> list[StockLotOut]:
    can_view_cost = authz.can(user, MODULE, "view_cost")
    hang = (hang_loai, hang_id) if (hang_loai and hang_id) else None
    lots = svc.lots.list_lots(hang=hang, kho_id=kho_id, con_hang=con_hang)
    # Nạp SẴN mọi mặt hàng của các lô trong 1 lượt (tránh N+1).
    hang_map = svc.hang.map_theo_cap([(lot.hang_loai, lot.hang_id) for lot in lots])
    out = []
    for lot in lots:
        row = StockLotOut.model_validate(lot)
        m = hang_map.get((lot.hang_loai, lot.hang_id))
        row.hang_ma = getattr(m, "ma", None)
        row.hang_ten = getattr(m, "ten", None)
        row.dvt = getattr(m, "don_vi_gia", None)
        # Thủ kho chọn lô nhưng KHÔNG thấy giá (spec §6).
        row.don_gia_nhap = int(lot.don_gia_nhap or 0) if can_view_cost else None
        out.append(row)
    return out


@router.get("/mat-hang/{hang_loai}/{hang_id}/lich-su", response_model=MaterialHistoryOut)
def material_history(
    hang_loai: str, hang_id: int, svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    kho_id: int = Query(...),
) -> MaterialHistoryOut:
    """Lịch sử NHẬP (mọi lô, kể cả đã hết) + XUẤT (dòng phiếu xuất đã ghi sổ) của 1 mặt hàng
    tại 1 kho — cho popup màn Tồn kho, tách theo dõi nhập/xuất riêng. Giá vốn ẩn nếu thiếu
    `can_view_cost` (đường path nhiều đoạn nên không đụng route `/{voucher_id}`)."""
    can_view_cost = authz.can(user, MODULE, "view_cost")
    hang = (hang_loai, hang_id)
    m = svc.hang.map_theo_cap([hang]).get(hang)
    dvt = getattr(m, "don_vi_gia", None)

    # NHẬP = mọi lô của mặt hàng tại kho (con_hang=False để giữ cả lô đã xuất hết), FIFO theo ngày.
    nhap: list[StockLotOut] = []
    for lot in svc.lots.list_lots(hang=hang, kho_id=kho_id, con_hang=False):
        row = StockLotOut.model_validate(lot)
        row.hang_ma = getattr(m, "ma", None)
        row.hang_ten = getattr(m, "ten", None)
        row.dvt = dvt
        row.don_gia_nhap = int(lot.don_gia_nhap or 0) if can_view_cost else None
        nhap.append(row)

    # XUẤT = dòng phiếu xuất đã ghi sổ (đích danh lô); giá vốn = giá lô, ẩn nếu thiếu quyền.
    xuat = [
        MaterialXuatRow(
            ngay=r["ngay"], voucher_id=r["voucher_id"], voucher_ma=r["voucher_ma"],
            lot_id=r["lot_id"], ma_lo=r["ma_lo"], so_luong=r["so_luong"],
            don_gia=r["don_gia"] if can_view_cost else None,
        )
        for r in svc.vouchers.xuat_history(hang, kho_id)
    ]

    return MaterialHistoryOut(
        hang_loai=hang_loai,
        hang_id=hang_id,
        hang_ma=getattr(m, "ma", None),
        hang_ten=getattr(m, "ten", None),
        dvt=dvt,
        on_hand=svc.lots.on_hand(hang, kho_id),
        nhap=nhap, xuat=xuat,
    )


# --- Đính kèm hóa đơn/chứng từ gốc --------------------------------------------

@router.get("/{voucher_id}/attachments", response_model=StockVoucherAttachmentListOut)
def list_voucher_attachments(
    voucher_id: int, svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> StockVoucherAttachmentListOut:
    try:
        items = svc.list_attachments(voucher_id)
    except StockVoucherError as e:
        raise _err(e) from None
    return StockVoucherAttachmentListOut(
        items=[StockVoucherAttachmentOut(**it) for it in items]
    )


@router.post(
    "/{voucher_id}/attachments",
    response_model=StockVoucherAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_voucher_attachment(
    voucher_id: int, svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
    file: UploadFile = File(...),
) -> StockVoucherAttachmentOut:
    data = file.file.read()
    try:
        return StockVoucherAttachmentOut(**svc.add_attachment(
            voucher_id, actor=user, file_name=file.filename,
            content_type=file.content_type, data=data,
        ))
    except StockVoucherError as e:
        raise _err(e) from None


@router.delete(
    "/{voucher_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_voucher_attachment(
    voucher_id: int, attachment_id: int, svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> Response:
    try:
        svc.delete_attachment(voucher_id, attachment_id, actor=user)
    except StockVoucherError as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Ngưỡng tồn ---------------------------------------------------------------

@threshold_router.get("", response_model=list[StockThresholdOut])
def list_thresholds(
    db: Db, _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[StockThresholdOut]:
    return [
        StockThresholdOut.model_validate(t)
        for t in StockThresholdRepository(db).list_active()
    ]


@threshold_router.put("", response_model=StockThresholdOut)
def upsert_threshold(
    payload: StockThresholdIn, db: Db,
    _: Annotated[User, Depends(require_permission(MODULE, "set_threshold"))],
) -> StockThresholdOut:
    """Khai ngưỡng. Bỏ trống `nguong_can_ton` thì để NULL — service tự suy ra
    `nguong_ton × 1.3` lúc so sánh, khỏi phải backfill khi đổi hệ số."""
    if payload.nguong_can_ton is not None and payload.nguong_can_ton < payload.nguong_ton:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngưỡng cận tồn phải lớn hơn hoặc bằng ngưỡng tồn.",
        )
    if payload.nguong_toi_da is not None and payload.nguong_toi_da < payload.nguong_ton:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngưỡng tối đa phải lớn hơn hoặc bằng ngưỡng tồn.",
        )
    obj = StockThresholdRepository(db).upsert(
        hang=(payload.hang_loai, payload.hang_id), kho_id=payload.kho_id,
        nguong_ton=payload.nguong_ton, nguong_can_ton=payload.nguong_can_ton,
        nguong_toi_da=payload.nguong_toi_da, canh_bao=payload.canh_bao,
    )
    return StockThresholdOut.model_validate(obj)
