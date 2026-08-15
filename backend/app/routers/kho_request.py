"""Router — Yêu cầu kho (spec-kho-de-nghi §2–§4, §7–§8).

Phục vụ CẢ HAI màn, khác nhau ở scope + quyền hiển thị cột (không nhân đôi dữ liệu):
* **Yêu cầu kho** — người yêu cầu, scope `own`, không thấy tồn/giá
* **Hộp yêu cầu kho** — thủ kho/quản lý kho, scope `all`, thấy tồn (+ giá nếu có quyền)

Dependency INLINE theo pattern các router kho hiện có. MODULE quyền = "kho".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, get_authorization_service, require_permission
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.stock_request import REQ_APPROVED, REQ_NHAP, REQ_XUAT
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.document_sequence_repo import DocumentSequenceRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.stock_lot_repo import StockLotRepository, StockThresholdRepository
from ..repositories.stock_request_repo import StockRequestRepository
from ..repositories.stock_voucher_repo import StockVoucherRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.user_repo import UserRepository
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..schemas.stock import (
    StockRequestCreate,
    StockRequestLineOut,
    StockRequestOut,
    StockRequestPage,
    StockRequestReject,
    StockRequestUpdate,
)
from ..services.rbac_service import AuthorizationService
from ..services.sequence_service import SequenceService
from ..services.stock_request_service import StockRequestError, StockRequestService
from ..services.vat_lieu_kho_service import HANG_NHAN, VatLieuKhoError, VatLieuKhoService

router = APIRouter(prefix="/api/kho/de-nghi", tags=["kho-de-nghi"])
MODULE = "kho"


def _hang_service(db: Session) -> VatLieuKhoService:
    """Danh mục gốc (Giấy + Vật tư khác) — nguồn mặt hàng và nguồn quy đổi đơn vị của kho."""
    return VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))


def get_service(db: Annotated[Session, Depends(get_db)]) -> StockRequestService:
    return StockRequestService(
        StockRequestRepository(db),
        StockLotRepository(db),
        StockThresholdRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
        hang=_hang_service(db),
    )


Service = Annotated[StockRequestService, Depends(get_service)]
Db = Annotated[Session, Depends(get_db)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _err(e: StockRequestError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _lenh_map(db: Session, reqs) -> dict[tuple[str, int], str]:
    """`{("lsx"|"bai_ghep", id): mã}` cho CẢ TRANG trong 2 query (mg 0175).

    Tra từng dòng là N+1 ngay trên màn Hộp yêu cầu — nơi đúng ra phải mở nhanh nhất.
    """
    from ..models.bai_ghep import BaiGhep
    from ..models.lsx import Lsx

    lsx_ids = {ln.lsx_id for r in reqs for ln in r.lines if ln.lsx_id}
    bg_ids = {ln.bai_ghep_id for r in reqs for ln in r.lines if ln.bai_ghep_id}
    ra: dict[tuple[str, int], str] = {}
    if lsx_ids:
        for i, ma in db.query(Lsx.id, Lsx.ma).filter(Lsx.id.in_(lsx_ids)):
            ra[("lsx", i)] = ma
    if bg_ids:
        for i, ma in db.query(BaiGhep.id, BaiGhep.ma).filter(BaiGhep.id.in_(bg_ids)):
            ra[("bai_ghep", i)] = ma
    return ra


def _serialize(req, *, db: Session, can_view_stock: bool, levels: dict | None,
               on_hand: dict | None,
               open_voucher_id: int | None = None,
               hang_map: dict | None = None,
               hang_svc: VatLieuKhoService | None = None,
               lenh_map: dict | None = None) -> StockRequestOut:
    """Dựng payload + ÁP quyền hiển thị.

    `muc_ton` (đèn 5 màu) trả cho mọi vai vì không kèm con số; `ton_kha_dung` chỉ set khi
    có `can_view_stock`. Ẩn ở đây chứ không chỉ ẩn trên UI — ẩn cột ở FE thì số vẫn nằm
    trong response.

    `hang_map` ((loai,id) → bản ghi danh mục) dựng SẴN theo cả trang để tránh N+1 khi list;
    gọi lẻ 1 đề nghị thì để None, hàm tự nạp.
    """
    hang_svc = hang_svc or _hang_service(db)
    users = UserRepository(db)
    cap = [(ln.hang_loai, ln.hang_id) for ln in req.lines]
    if hang_map is None:
        hang_map = hang_svc.map_theo_cap(cap)
    if lenh_map is None:
        lenh_map = _lenh_map(db, [req])
    lines: list[StockRequestLineOut] = []
    for ln in req.lines:
        key = (ln.hang_loai, ln.hang_id)
        m = hang_map.get(key)
        # Quy đổi để FE hiện "10 ram ≈ 419,25 kg" ngay dưới ô SL — người khai thấy TRƯỚC con số
        # sẽ vào tồn, thay vì bấm Lưu rồi mới biết. Không đổi được thì trả `canh_bao_dv` nguyên
        # văn lý do chứ không im lặng.
        qd, canh_bao = None, None
        try:
            qd = hang_svc.quy_ve_goc(ln.hang_loai, ln.hang_id, ln.dvt, float(ln.sl_de_nghi))
        except VatLieuKhoError as e:
            canh_bao = str(e)
        lines.append(StockRequestLineOut(
            id=ln.id,
            hang_loai=ln.hang_loai,
            hang_id=ln.hang_id,
            hang_ma=getattr(m, "ma", None),
            hang_ten=getattr(m, "ten", None),
            hang_anh=getattr(m, "anh_url", None),
            hang_nhom=HANG_NHAN.get(ln.hang_loai),
            lsx_id=ln.lsx_id,
            bai_ghep_id=ln.bai_ghep_id,
            lsx_ma=lenh_map.get(("lsx", ln.lsx_id)),
            bai_ghep_ma=lenh_map.get(("bai_ghep", ln.bai_ghep_id)),
            dvt=ln.dvt,
            don_vi_goc=(qd or {}).get("don_vi_goc_ten"),
            sl_quy_doi=(qd or {}).get("sl_goc"),
            quy_doi_dien_giai=(qd or {}).get("dien_giai"),
            canh_bao_dv=canh_bao,
            sl_de_nghi=float(ln.sl_de_nghi),
            sl_duyet=float(ln.sl_duyet),
            sl_da_ung=float(ln.sl_da_ung),
            sl_con_lai=max(0.0, float(ln.sl_duyet) - float(ln.sl_da_ung)),
            don_gia=ln.don_gia,
            ly_do_thieu=ln.ly_do_thieu,
            ghi_chu=ln.ghi_chu,
            muc_ton=(levels or {}).get(key),
            ton_kha_dung=(on_hand or {}).get(key) if can_view_stock else None,
        ))
    creator = users.get_by_id(req.nguoi_tao_id) if req.nguoi_tao_id else None
    approver = users.get_by_id(req.nguoi_duyet_id) if req.nguoi_duyet_id else None
    dept = DepartmentRepository(db).get_by_id(req.bo_phan_id) if req.bo_phan_id else None
    kho = KhoHangRepository(db).get(req.kho_id) if req.kho_id else None
    return StockRequestOut(
        id=req.id, ma=req.ma, loai=req.loai,
        nguoi_tao_id=req.nguoi_tao_id,
        nguoi_tao_ten=getattr(creator, "name", None),
        bo_phan_id=req.bo_phan_id, bo_phan_ten=getattr(dept, "name", None),
        kho_id=req.kho_id, kho_ten=getattr(kho, "ten", None),
        ngay_can=req.ngay_can, uu_tien=req.uu_tien,
        ghi_chu=req.ghi_chu, loai_kho=req.loai_kho, trang_thai=req.trang_thai,
        nguoi_duyet_id=req.nguoi_duyet_id,
        nguoi_duyet_ten=getattr(approver, "name", None),
        duyet_luc=req.duyet_luc, ly_do_tu_choi=req.ly_do_tu_choi,
        ly_do_huy=req.ly_do_huy,
        open_voucher_id=open_voucher_id,
        created_at=req.created_at, updated_at=req.updated_at, lines=lines,
    )


def _levels(svc: StockRequestService, req):
    """TỒN KHẢ DỤNG + đèn (`muc_ton`) cho các dòng của yêu cầu. Yêu cầu KHÔNG gắn kho (kho quyết ở
    bước lập phiếu) → `req.kho_id` thường None → `on_hand_map` cộng tồn khả dụng TRÊN MỌI KHO.
    `levels_and_on_hand` tính CẢ đèn lẫn tồn trong 1 lượt: đèn theo ngưỡng của kho (kho_id None thì
    chưa có ngưỡng → chỉ phân biệt hết/còn). UI đã bỏ cột đèn nên không nhiễu, nhưng GIỮ `muc_ton`
    cho API/test (bỏ hẳn làm vỡ test đèn + mất tín hiệu cho ai còn dùng)."""
    cap = [(ln.hang_loai, ln.hang_id) for ln in req.lines]
    return svc.levels_and_on_hand(cap, req.kho_id)


def _scoped_filters(user: User, authz: AuthorizationService) -> dict:
    """Dịch scope của vai trò thành bộ lọc list.

    `own` là cách người yêu cầu bị chặn khỏi kho: họ chỉ thấy yêu cầu của chính mình,
    nên không có đường nào nhìn thấy yêu cầu/tồn của bộ phận khác.
    """
    scope = authz.scope_for(user, MODULE) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return {}
    if scope == SCOPE_DEPARTMENT:
        return {"bo_phan_id": user.department_id}
    return {"nguoi_tao_id": user.id}


def _require_visible(req, user: User, authz: AuthorizationService) -> None:
    """404 (không phải 403) khi yêu cầu nằm ngoài scope — không tiết lộ là nó có tồn tại."""
    scope = authz.scope_for(user, MODULE) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return
    if scope == SCOPE_DEPARTMENT and req.bo_phan_id == user.department_id:
        return
    if scope == SCOPE_OWN and req.nguoi_tao_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy yêu cầu")


@router.get("", response_model=StockRequestPage)
def list_requests(
    svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    loai: str | None = Query(default=None),
    trang_thai: list[str] | None = Query(default=None),
    kho_id: int | None = Query(default=None, description="Lọc yêu cầu theo kho đích"),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> StockRequestPage:
    rows, total = svc.requests.list(
        loai=loai, trang_thai=trang_thai, q=q, kho_id=kho_id, page=page, size=size,
        **_scoped_filters(user, authz),
    )
    can_view_stock = authz.can(user, MODULE, "view_stock")
    draft_map = StockVoucherRepository(db).draft_ids_by_request([r.id for r in rows])
    # Nạp SẴN mọi mã hàng của cả trang trong 1 query (tránh N+1 trong _serialize).
    hang_svc = _hang_service(db)
    hang_map = hang_svc.map_theo_cap(
        [(ln.hang_loai, ln.hang_id) for r in rows for ln in r.lines]
    )
    lenh_map = _lenh_map(db, rows)
    items = []
    for r in rows:
        # List KHÔNG hiện tồn khả dụng/đèn (chỉ drawer chi tiết hiện) → khỏi tính, tránh N+1 query.
        levels, on_hand = None, None
        items.append(_serialize(r, db=db, can_view_stock=can_view_stock,
                                levels=levels, on_hand=on_hand, lenh_map=lenh_map,
                                open_voucher_id=draft_map.get(r.id), hang_map=hang_map, hang_svc=hang_svc))
    return StockRequestPage(items=items, total=total)


@router.get("/counts")
def request_counts(
    svc: Service, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict[str, int]:
    """Số yêu cầu ĐÃ DUYỆT chờ kho lập phiếu, theo chiều. Badge "chờ cấp" là VIỆC CỦA KHO nên CHỈ
    hiện cho người XỬ LÝ (can_create=lập phiếu / can_view_stock) — khớp đúng người nhận thông báo;
    người chỉ TẠO yêu cầu (vd tổ trưởng SX) KHÔNG thấy badge. Trong tầm thì lọc theo SCOPE như list:
    kho trung tâm (all) thấy tổng; phòng ban thấy của phòng; scope own thấy của mình."""
    # `done_unseen` / `fail_unseen` = phản hồi kho (yêu cầu HOÀN TẤT / KHÔNG THÀNH) của CHÍNH user mà
    # user chưa mở xem — KHÔNG lọc theo scope xử-lý (việc của NGƯỜI TẠO, không phải workload kho).
    # Người chỉ tạo yêu cầu vẫn nhận số này dù nhap/xuat = 0. Badge người tạo = done + fail.
    resp = svc.requests.unseen_response_counts(user.id)
    is_kho_worker = authz.can(user, MODULE, "create") or authz.can(user, MODULE, "view_stock")
    if not is_kho_worker:
        return {"nhap": 0, "xuat": 0, "done_unseen": resp["done"], "fail_unseen": resp["fail"]}
    counts = svc.requests.count_by_loai([REQ_APPROVED], **_scoped_filters(user, authz))
    return {
        "nhap": counts.get(REQ_NHAP, 0),
        "xuat": counts.get(REQ_XUAT, 0),
        "done_unseen": resp["done"],
        "fail_unseen": resp["fail"],
    }


@router.post("/{request_id}/seen", status_code=204)
def mark_request_seen(
    request_id: int,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
):
    """NGƯỜI TẠO mở xem 1 yêu cầu của mình → đánh dấu đã xem → hạ badge/số đỏ đúng yêu cầu đó.
    Chỉ tác dụng lên yêu cầu do chính user tạo (repo lọc theo nguoi_tao_id)."""
    svc.requests.mark_seen_one(request_id, user.id)


# GỠ 2026-08-08 — ba cửa cũ: `GET /vat-tu` (tìm trong bảng `materials`), `POST /vat-tu` (kho tự
# tạo mã hàng), `PUT /vat-tu/{id}/quy-doi` (khai hệ số riêng cho kho). Picker mặt hàng giờ dùng
# `GET /api/vat-lieu-kho/mat-hang`, đơn vị dùng `.../mat-hang/{loai}/{id}/don-vi`.


@router.get("/{request_id}", response_model=StockRequestOut)
def get_request(
    request_id: int, svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> StockRequestOut:
    req = svc.requests.get_with_lines(request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy yêu cầu")
    _require_visible(req, user, authz)
    levels, on_hand = _levels(svc, req)
    draft_map = StockVoucherRepository(db).draft_ids_by_request([req.id])
    return _serialize(req, db=db, can_view_stock=authz.can(user, MODULE, "view_stock"),
                      levels=levels, on_hand=on_hand,
                      open_voucher_id=draft_map.get(req.id))


@router.post("", response_model=StockRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: StockRequestCreate, svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "request"))],
) -> StockRequestOut:
    try:
        req = svc.create(
            user=user, loai=payload.loai, kho_id=payload.kho_id, ma=payload.ma,
            lines=[ln.model_dump() for ln in payload.lines],
            ngay_can=payload.ngay_can, uu_tien=payload.uu_tien, ghi_chu=payload.ghi_chu,
            loai_kho=payload.loai_kho, purchase_delivery_id=payload.purchase_delivery_id,
        )
    except StockRequestError as e:
        raise _err(e) from None
    levels, on_hand = _levels(svc, req)
    return _serialize(req, db=db, can_view_stock=authz.can(user, MODULE, "view_stock"),
                      levels=levels, on_hand=on_hand)


@router.put("/{request_id}", response_model=StockRequestOut)
def update_request(
    request_id: int, payload: StockRequestUpdate, svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "request"))],
) -> StockRequestOut:
    req = svc.requests.get_with_lines(request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy yêu cầu")
    if req.nguoi_tao_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Chỉ người tạo mới sửa được yêu cầu")
    data = payload.model_dump(exclude_unset=True, exclude={"lines"})
    lines = [ln.model_dump() for ln in payload.lines] if payload.lines is not None else None
    try:
        req = svc.update(req, lines=lines, **data)
    except StockRequestError as e:
        raise _err(e) from None
    return _serialize(req, db=db, can_view_stock=authz.can(user, MODULE, "view_stock"),
                      levels=None, on_hand=None)


def _act(svc: StockRequestService, request_id: int, user: User, authz: AuthorizationService,
         db: Session, fn) -> StockRequestOut:
    req = svc.requests.get_with_lines(request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy yêu cầu")
    try:
        req = fn(req)
    except StockRequestError as e:
        raise _err(e) from None
    return _serialize(req, db=db, can_view_stock=authz.can(user, MODULE, "view_stock"),
                      levels=None, on_hand=None)


@router.post("/{request_id}/trinh-duyet", response_model=StockRequestOut)
def submit(request_id: int, svc: Service, db: Db, authz: Authz,
           user: Annotated[User, Depends(require_permission(MODULE, "request"))]):
    return _act(svc, request_id, user, authz, db, svc.submit)


# Yêu cầu BỎ BƯỚC DUYỆT (chủ 06/08/2026): tạo là 'approved' luôn (xem service.create). Không còn
# ai duyệt/từ chối → gỡ 2 endpoint `/duyet` và `/tu-choi`. Service `approve`/`reject` GIỮ lại (không
# gọi từ đâu nữa) để khỏi đụng thêm; nhưng KHÔNG để endpoint mồ côi require `approve`.


@router.post("/{request_id}/huy", response_model=StockRequestOut)
def cancel(request_id: int, svc: Service, db: Db, authz: Authz,
           user: Annotated[User, Depends(require_permission(MODULE, "request"))]):
    req = svc.requests.get(request_id)
    if req is not None and req.nguoi_tao_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Chỉ người tạo mới hủy được yêu cầu")
    return _act(svc, request_id, user, authz, db, svc.cancel)


@router.post("/{request_id}/huy-kho", response_model=StockRequestOut)
def cancel_kho(request_id: int, payload: StockRequestReject, svc: Service, db: Db, authz: Authz,
               user: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    """Kho HỦY yêu cầu (quyết định KHÔNG lập phiếu) — kèm lý do; gate bằng `create` (quyền lập
    phiếu), KHÔNG cần là người tạo. Yêu cầu chuyển 'Đã hủy'; số đã cấp bởi phiếu đã ghi sổ (nếu
    có) vẫn giữ nguyên trong kho."""
    return _act(svc, request_id, user, authz, db, lambda r: svc.cancel_by_kho(r, payload.ly_do))


@router.post("/{request_id}/tiep-nhan", response_model=StockRequestOut)
def receive(request_id: int, svc: Service, db: Db, authz: Authz,
            user: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    """Kho bấm 'Tiếp nhận'. Gate bằng `create` (= quyền lập phiếu) chứ không phải `approve`
    — kho KHÔNG duyệt, chỉ nhận việc (BRD §2.6 b8)."""
    return _act(svc, request_id, user, authz, db, svc.mark_received)


@router.post("/{request_id}/chuan-bi", response_model=StockRequestOut)
def prepare(request_id: int, svc: Service, db: Db, authz: Authz,
            user: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    return _act(svc, request_id, user, authz, db, svc.mark_preparing)


@router.get("/goi-y/so-luong")
def suggest_qty(
    svc: Service, user: CurrentUser,
    _: Annotated[User, Depends(require_permission(MODULE, "request"))],
    hang_loai: str = Query(...),
    hang_id: int = Query(..., gt=0),
):
    """Gợi ý số lượng từ lịch sử đề nghị của bộ phận (spec §8). Không đụng tới tồn nên
    người đề nghị gọi được mà không lộ gì."""
    return {"so_luong": svc.suggest_quantity((hang_loai, hang_id), user.department_id)}
