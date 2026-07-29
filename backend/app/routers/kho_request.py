"""Router — Đề nghị kho (spec-kho-de-nghi §2–§4, §7–§8).

Phục vụ CẢ HAI màn, khác nhau ở scope + quyền hiển thị cột (không nhân đôi dữ liệu):
* **Đề nghị kho** — người đề nghị, scope `own`, không thấy tồn/giá
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
from ..models.stock_request import REQ_XUAT
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.document_sequence_repo import DocumentSequenceRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.material_repo import MaterialRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.stock_lot_repo import StockLotRepository, StockThresholdRepository
from ..repositories.stock_request_repo import StockRequestRepository
from ..repositories.stock_voucher_repo import StockVoucherRepository
from ..repositories.user_repo import UserRepository
from ..schemas.stock import (
    StockMaterialCreate,
    StockMaterialQuyDoi,
    StockRequestApprove,
    StockRequestCreate,
    StockRequestLineOut,
    StockRequestOut,
    StockRequestPage,
    StockRequestReject,
    StockRequestUpdate,
)
from ..services.material_service import MaterialDuplicate, MaterialError, MaterialService
from ..services.rbac_service import AuthorizationService
from ..services.sequence_service import SequenceService
from ..services.stock_request_service import StockRequestError, StockRequestService

router = APIRouter(prefix="/api/kho/de-nghi", tags=["kho-de-nghi"])
MODULE = "kho"


def get_service(db: Annotated[Session, Depends(get_db)]) -> StockRequestService:
    return StockRequestService(
        StockRequestRepository(db),
        StockLotRepository(db),
        StockThresholdRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


Service = Annotated[StockRequestService, Depends(get_service)]
Db = Annotated[Session, Depends(get_db)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _err(e: StockRequestError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _serialize(req, *, db: Session, can_view_stock: bool, levels: dict[int, str] | None,
               on_hand: dict[int, float] | None,
               open_voucher_id: int | None = None,
               mat_map: dict | None = None) -> StockRequestOut:
    """Dựng payload + ÁP quyền hiển thị.

    `muc_ton` (đèn 5 màu) trả cho mọi vai vì không kèm con số; `ton_kha_dung` chỉ set khi
    có `can_view_stock`. Ẩn ở đây chứ không chỉ ẩn trên UI — ẩn cột ở FE thì số vẫn nằm
    trong response.

    `mat_map` (id → Material) dựng SẴN theo cả trang để tránh N+1 khi list; gọi lẻ 1 đề nghị
    thì để None, hàm tự nạp 1 query cho các dòng của đề nghị đó.
    """
    materials = MaterialRepository(db)
    users = UserRepository(db)
    if mat_map is None:
        mat_map = materials.by_ids([ln.material_id for ln in req.lines])
    lines: list[StockRequestLineOut] = []
    for ln in req.lines:
        m = mat_map.get(ln.material_id) if ln.material_id else None
        lines.append(StockRequestLineOut(
            id=ln.id,
            material_id=ln.material_id,
            material_code=getattr(m, "code", None),
            # Hàng chưa có mã → hiển thị tên gõ tự do (kèm dấu để phân biệt ở FE).
            material_name=getattr(m, "name", None) or ln.ten_tu_do,
            ten_tu_do=ln.ten_tu_do,
            dvt=ln.dvt,
            # Quy đổi ưu tiên khai TRÊN DÒNG (người đề nghị); hàng có mã chưa khai → lấy của mặt hàng.
            don_vi_phu=ln.don_vi_phu or getattr(m, "don_vi_phu", None),
            he_so_quy_doi=(
                float(ln.he_so_quy_doi) if ln.he_so_quy_doi is not None
                else (float(m.he_so_quy_doi) if getattr(m, "he_so_quy_doi", None) is not None else None)
            ),
            sl_de_nghi=float(ln.sl_de_nghi),
            sl_duyet=float(ln.sl_duyet),
            sl_da_ung=float(ln.sl_da_ung),
            sl_con_lai=max(0.0, float(ln.sl_duyet) - float(ln.sl_da_ung)),
            don_gia=ln.don_gia,
            ly_do_thieu=ln.ly_do_thieu,
            ghi_chu=ln.ghi_chu,
            muc_ton=(levels or {}).get(ln.material_id),
            ton_kha_dung=(on_hand or {}).get(ln.material_id) if can_view_stock else None,
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
        ghi_chu=req.ghi_chu, trang_thai=req.trang_thai,
        nguoi_duyet_id=req.nguoi_duyet_id,
        nguoi_duyet_ten=getattr(approver, "name", None),
        duyet_luc=req.duyet_luc, ly_do_tu_choi=req.ly_do_tu_choi,
        open_voucher_id=open_voucher_id,
        created_at=req.created_at, lines=lines,
    )


def _levels(svc: StockRequestService, req):
    """Mức tồn cho các dòng của đề nghị, tính theo KHO ĐÍCH của chính đề nghị (`req.kho_id`).
    Chỉ có nghĩa với đề nghị XUẤT (đề nghị NHẬP thì tồn thấp là chuyện đương nhiên, tô đèn đỏ
    chỉ gây nhiễu). Đề nghị cũ chưa có kho → không có đèn."""
    if req.kho_id is None or req.loai != REQ_XUAT:
        return None, None
    ids = [ln.material_id for ln in req.lines]
    return svc.levels_and_on_hand(ids, req.kho_id)


def _scoped_filters(user: User, authz: AuthorizationService) -> dict:
    """Dịch scope của vai trò thành bộ lọc list.

    `own` là cách người đề nghị bị chặn khỏi kho: họ chỉ thấy đề nghị của chính mình,
    nên không có đường nào nhìn thấy đề nghị/tồn của bộ phận khác.
    """
    scope = authz.scope_for(user, MODULE) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return {}
    if scope == SCOPE_DEPARTMENT:
        return {"bo_phan_id": user.department_id}
    return {"nguoi_tao_id": user.id}


def _require_visible(req, user: User, authz: AuthorizationService) -> None:
    """404 (không phải 403) khi đề nghị nằm ngoài scope — không tiết lộ là nó có tồn tại."""
    scope = authz.scope_for(user, MODULE) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return
    if scope == SCOPE_DEPARTMENT and req.bo_phan_id == user.department_id:
        return
    if scope == SCOPE_OWN and req.nguoi_tao_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đề nghị")


@router.get("", response_model=StockRequestPage)
def list_requests(
    svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    loai: str | None = Query(default=None),
    trang_thai: list[str] | None = Query(default=None),
    kho_id: int | None = Query(default=None, description="Lọc đề nghị theo kho đích"),
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
    mat_map = MaterialRepository(db).by_ids(
        [ln.material_id for r in rows for ln in r.lines]
    )
    items = []
    for r in rows:
        # Đèn tồn tính theo KHO của chính đề nghị (r.kho_id), không phải theo bộ lọc.
        levels, on_hand = _levels(svc, r)
        items.append(_serialize(r, db=db, can_view_stock=can_view_stock,
                                levels=levels, on_hand=on_hand,
                                open_voucher_id=draft_map.get(r.id), mat_map=mat_map))
    return StockRequestPage(items=items, total=total)


@router.get("/vat-tu")
def search_materials(
    db: Db,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    size: int = Query(default=20, ge=1, le=50),
):
    """Tìm vật tư để chọn khi lập đề nghị.

    Có endpoint riêng vì `/api/materials` gác bằng module `dm_giay_vat_tu` — không vai kho
    nào có quyền đó, mà cấp thêm thì lộ luôn bảng giá (`MaterialRow.costs`). Ở đây gác bằng
    `kho:read` và CHỈ trả 4 trường tối thiểu: người đề nghị thấy tên + ĐVT, không thấy giá.
    """
    rows, _total = MaterialRepository(db).list(q=q, is_active=True, size=size)
    return [_material_out(m) for m in rows]


def _material_out(m) -> dict:
    return {
        "id": m.id, "code": m.code, "name": m.name, "unit": m.unit,
        "don_vi_phu": m.don_vi_phu,
        "he_so_quy_doi": float(m.he_so_quy_doi) if m.he_so_quy_doi is not None else None,
    }


@router.post("/vat-tu", status_code=status.HTTP_201_CREATED)
def create_material(
    body: StockMaterialCreate,
    db: Db,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
):
    """Tạo mã hàng — CHỈ KHO (vai lập phiếu) làm, ở bước lập phiếu khi gặp hàng mới (BRD §3.4).
    Người đề nghị KHÔNG tạo mã: họ gõ tên tự do, kho gắn/tạo mã sau. Chống trùng theo tên/mã."""
    svc = MaterialService(MaterialRepository(db), AuditLogRepository(db))
    try:
        m = svc.create_material(
            name=body.name, material_type="hang_khac", unit=body.unit,
            code=body.code, actor=user,
            don_vi_phu=body.don_vi_phu, he_so_quy_doi=body.he_so_quy_doi,
        )
    except MaterialDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except MaterialError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _material_out(m)


@router.put("/vat-tu/{material_id}/quy-doi")
def set_material_quy_doi(
    material_id: int,
    body: StockMaterialQuyDoi,
    db: Db,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
):
    """Khai/sửa quy đổi đơn vị cho hàng đã có — nút 'Quy đổi' trên dòng phiếu (vai lập phiếu)."""
    svc = MaterialService(MaterialRepository(db), AuditLogRepository(db))
    try:
        m = svc.set_quy_doi(
            material_id=material_id, don_vi_phu=body.don_vi_phu,
            he_so_quy_doi=body.he_so_quy_doi, actor=user,
        )
    except MaterialError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _material_out(m)


@router.get("/{request_id}", response_model=StockRequestOut)
def get_request(
    request_id: int, svc: Service, db: Db, authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> StockRequestOut:
    req = svc.requests.get_with_lines(request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đề nghị")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đề nghị")
    if req.nguoi_tao_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Chỉ người tạo mới sửa được đề nghị")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đề nghị")
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


@router.post("/{request_id}/duyet", response_model=StockRequestOut)
def approve(request_id: int, payload: StockRequestApprove, svc: Service, db: Db, authz: Authz,
            user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    return _act(svc, request_id, user, authz, db,
                lambda r: svc.approve(r, approver=user, approved_qty=payload.approved_qty))


@router.post("/{request_id}/tu-choi", response_model=StockRequestOut)
def reject(request_id: int, payload: StockRequestReject, svc: Service, db: Db, authz: Authz,
           user: Annotated[User, Depends(require_permission(MODULE, "approve"))]):
    return _act(svc, request_id, user, authz, db,
                lambda r: svc.reject(r, approver=user, ly_do=payload.ly_do))


@router.post("/{request_id}/huy", response_model=StockRequestOut)
def cancel(request_id: int, svc: Service, db: Db, authz: Authz,
           user: Annotated[User, Depends(require_permission(MODULE, "request"))]):
    req = svc.requests.get(request_id)
    if req is not None and req.nguoi_tao_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Chỉ người tạo mới hủy được đề nghị")
    return _act(svc, request_id, user, authz, db, svc.cancel)


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
    material_id: int = Query(...),
):
    """Gợi ý số lượng từ lịch sử đề nghị của bộ phận (spec §8). Không đụng tới tồn nên
    người đề nghị gọi được mà không lộ gì."""
    return {"so_luong": svc.suggest_quantity(material_id, user.department_id)}
