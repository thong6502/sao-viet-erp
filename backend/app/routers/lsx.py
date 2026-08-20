"""Router Lệnh sản xuất (LSX) — bàn của bộ phận Kế hoạch sản xuất.

Prefix `/api/lsx`. RBAC MODULE = "san_xuat".

Luồng: Sale bấm "Chuyển xuống sản xuất" (đơn hàng) → đơn rơi vào `/hang-cho` → Kế hoạch mở
`/preview/{order_id}` xem danh sách lệnh DỰ KIẾN (dẫn xuất tại chỗ, chưa ghi DB) → tick dòng →
`POST /tao/{order_id}` sinh lệnh Nháp/Chờ bổ sung → sửa routing/số lượng → đánh dấu Sẵn sàng.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_authorization_service, require_permission
from ..models.lsx import Lsx
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from ..realtime import hub
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.catalog_base import SIZE_TRAN
from ..repositories.document_sequence_repo import DocumentSequenceRepository
from ..repositories.lsx_repo import LsxRepository
from ..repositories.org_scope import dept_subtree_ids
from ..schemas.lsx import (
    BuocMacDinhOut,
    HangChoOut,
    LsxActivityItem,
    LsxActivityOut,
    LsxGiaoNhanIn,
    LsxListItem,
    LsxListOut,
    LsxOut,
    LsxQuyCachIn,
    LsxTongQuanItem,
    LsxTongQuanOut,
    LsxUpdateIn,
    PreviewOut,
    KhuonMoiIn,
    PhuThuocOption,
    RoutingReplaceIn,
    TaoLsxIn,
    TinhNguocOut,
    TinhNguocRow,
    TrangThaiIn,
    XemTruocRoutingIn,
    XemTruocRoutingOut,
)
from ..services import lsx_tong_quan
from ..services.actor_display import actor_labels
from ..services.lsx_service import (
    LsxConflict,
    LsxNotFound,
    LsxService,
    LsxValidationError,
)
from ..services.rbac_service import AuthorizationService
from ..services.sequence_service import SequenceService

router = APIRouter(prefix="/api/lsx", tags=["lsx"])
MODULE = "san_xuat"
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _svc(db: Session) -> LsxService:
    return LsxService(
        db,
        LsxRepository(db),
        AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, LsxNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LsxConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, LsxValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


def _owner_ids_for_scope(db: Session, user: User, authz: AuthorizationService) -> set[int] | None:
    """Tập user-id mà `user` được thấy lệnh theo scope module `san_xuat`. None = thấy TẤT CẢ.

    Lệnh KHÔNG thuộc sale (khác đơn hàng) nên phạm vi tính theo người phụ trách / người tạo lệnh:
    Kế hoạch SX cầm scope `all` → thấy hết; tổ trưởng/thợ scope `own` → chỉ lệnh của mình.
    """
    scope = authz.scope_for(user, MODULE) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return None
    if scope == SCOPE_DEPARTMENT:
        dept_ids = dept_subtree_ids(db, user.department_id)
        if dept_ids:
            ids = db.execute(select(User.id).where(User.department_id.in_(dept_ids))).scalars().all()
            return set(ids) | {user.id}
    return {user.id}


def _guard_scope(db: Session, lsx, user: User, authz: AuthorizationService) -> None:
    owner_ids = _owner_ids_for_scope(db, user, authz)
    if owner_ids is None:
        return
    if lsx.nguoi_phu_trach_id in owner_ids or lsx.created_by in owner_ids:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lệnh sản xuất")


def _out(svc: LsxService, lsx) -> LsxOut:
    return LsxOut.model_validate({**lsx.__dict__, **svc.detail_dict(lsx)})


# --- Hàng chờ tiếp nhận -------------------------------------------------------
@router.get("/hang-cho", response_model=HangChoOut)
def hang_cho(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=SIZE_TRAN),
) -> HangChoOut:
    """Đơn Sale đã chuyển xuống SX mà còn dòng chưa lên lệnh. Chỉ người có phạm vi TOÀN BỘ (Kế
    hoạch SX) mới thấy — đơn chưa lên lệnh thì chưa thuộc về ai bên sản xuất."""
    if _owner_ids_for_scope(db, user, authz) is not None:
        return HangChoOut(items=[], total=0, page=page, size=size)
    items, total = _svc(db).hang_cho(page=page, size=size)
    return HangChoOut(items=items, total=total, page=page, size=size)


# --- Xem trước danh sách lệnh dự kiến ----------------------------------------
@router.get("/preview/{order_id}", response_model=PreviewOut)
def preview(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PreviewOut:
    try:
        return PreviewOut.model_validate(_svc(db).preview(order_id))
    except Exception as exc:
        raise _map(exc)


@router.post("/tao/{order_id}", response_model=LsxListOut, status_code=status.HTTP_201_CREATED)
def tao(
    order_id: int,
    payload: TaoLsxIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> LsxListOut:
    svc = _svc(db)
    try:
        created = svc.tao(order_id=order_id, order_line_ids=payload.order_line_ids, actor=user)
    except Exception as exc:
        raise _map(exc)
    ids = [c.id for c in created]
    # Trong PHẠM VI MỘT ĐƠN — vài chục dòng là cùng, lấy trọn trần một trang rồi lọc ra dòng vừa tạo.
    rows, _ = svc.list_rows(order_id=order_id, size=SIZE_TRAN)
    rows = [r for r in rows if r["id"] in ids]
    # Đơn hàng + hàng chờ nhảy ngay (badge/đếm) — không bắt ai refresh.
    hub.broadcast({"type": "lsx_changed", "order_id": order_id})
    return LsxListOut(items=[LsxListItem.model_validate(r) for r in rows], total=len(rows))


# --- Danh sách / chi tiết -----------------------------------------------------
@router.get("", response_model=LsxListOut)
def list_items(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    order_id: int | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    # Trần 200 khớp `repositories/catalog_base.SIZE_TRAN` — chặn client gõ `?size=99999` để kéo
    # cả bảng về, đúng cái đã làm chết endpoint này ở 100.000 lệnh.
    size: int = Query(default=50, ge=1, le=SIZE_TRAN),
) -> LsxListOut:
    svc = _svc(db)
    loc = {
        "order_id": order_id, "trang_thai": trang_thai, "q": q,
        "owner_ids": _owner_ids_for_scope(db, user, authz),
    }
    rows, total = svc.list_rows(page=page, size=size, **loc)
    return LsxListOut(
        items=[LsxListItem.model_validate(r) for r in rows],
        total=total, page=page, size=size,
        # Cùng `loc` — số trên tab và số dòng trong bảng luôn nói cùng một chuyện. Bộ lọc
        # `trang_thai` bị bỏ ở tầng repo, không phải ở đây.
        facets=svc.dem_trang_thai(**loc),
    )


# --- Hàng đèn tổng quan -------------------------------------------------------
@router.get("/tong-quan", response_model=LsxTongQuanOut)
def tong_quan(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    ids: str = Query(default="", description="lsx_id ngăn bởi dấu phẩy"),
) -> LsxTongQuanOut:
    """Ba đèn (Vật tư · Máy & giờ · Người) cho ĐÚNG các lệnh đang hiện trên bảng.

    ⚠️ PHẢI đứng TRƯỚC `/{lsx_id}`, không thì FastAPI nuốt `tong-quan` thành path param → 422.

    Gọi RỜI sau bảng lệnh, KHÔNG nhét vào `GET /api/lsx`: bên trong chạy engine cân đối vật tư +
    bộ dò vấn đề cho cả bàn. Đèn nhảy vào sau vài trăm ms thì chấp nhận được, bảng lệnh ngồi chờ
    engine thì không. Client cũng đừng gọi lại khi chỉ gõ ô tìm — `loadLenhs` chạy lại mỗi 250ms.
    """
    wanted = [int(s) for s in (ids or "").replace(" ", "").split(",") if s.isdigit()]
    if not wanted:
        return LsxTongQuanOut(items=[])
    if len(wanted) > SIZE_TRAN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Tối đa {SIZE_TRAN} lệnh mỗi lượt")
    # Lọc về đúng lệnh CÓ THẬT và người này được thấy — cùng luật phạm vi với bảng lệnh. Không lọc
    # thì id rác cũng nhận được đèn đỏ "chưa giữ chỗ vật tư", tức là bịa trạng thái cho lệnh không
    # tồn tại và rò trạng thái của lệnh ngoài phạm vi.
    truy = select(Lsx.id).where(Lsx.id.in_(wanted))
    owner_ids = _owner_ids_for_scope(db, user, authz)
    if owner_ids is not None:
        truy = truy.where(or_(Lsx.nguoi_phu_trach_id.in_(owner_ids),
                              Lsx.created_by.in_(owner_ids)))
    thay = set(db.execute(truy).scalars())
    wanted = [i for i in wanted if i in thay]
    return LsxTongQuanOut(items=[LsxTongQuanItem.model_validate(r)
                                 for r in lsx_tong_quan.tong_quan(db, wanted)])


@router.get("/{lsx_id}", response_model=LsxOut)
def get_item(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> LsxOut:
    svc = _svc(db)
    try:
        lsx = svc.get(lsx_id)
    except Exception as exc:
        raise _map(exc)
    _guard_scope(db, lsx, user, authz)
    return _out(svc, lsx)


@router.get("/{lsx_id}/phu-thuoc-options", response_model=list[PhuThuocOption])
def phu_thuoc_options(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[PhuThuocOption]:
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        return [PhuThuocOption.model_validate(x) for x in svc.phu_thuoc_options(lsx_id)]
    except Exception as exc:
        raise _map(exc)


@router.get("/{lsx_id}/khuon-chon-duoc")
def khuon_chon_duoc(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    loai: str | None = None,
    dang_chon: int | None = None,
) -> list[dict]:
    """Dao chọn được cho một bước — đã lọc theo KHÁCH của lệnh + LOẠI của bước (xem service).

    Gác bằng quyền `lenh_san_xuat.read` chứ không phải quyền màn Khuôn: người cấu hình lệnh phải
    chọn được dao mà không cần cấp thêm quyền vào danh mục — đây là danh sách rút gọn của đúng
    một lệnh, không phải cửa vào toàn bộ kho.
    """
    svc = _svc(db)
    try:
        lsx = svc.get(lsx_id)
    except Exception as exc:
        raise _map(exc)
    _guard_scope(db, lsx, user, authz)
    return svc.khuon_chon_duoc(lsx, loai=loai, dang_chon=dang_chon)


@router.post("/{lsx_id}/khuon-moi", status_code=201)
def tao_khuon_cho_lenh(
    lsx_id: int,
    payload: KhuonMoiIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Nhánh "làm dao mới" ở bước — tạo dòng trong danh mục Khuôn, tình trạng `dang_dat_lam`.

    Gác bằng `lenh_san_xuat.update` chứ không phải quyền ghi danh mục Khuôn: người cấu hình lệnh
    phải đi tiếp được ngay tại chỗ. Bắt họ có thêm quyền vào danh mục là dựng lại đúng ngõ cụt
    làm ô chọn khuôn đời trước chết — mở ra không có dao, không có đường tạo, đóng lại bỏ qua.
    """
    svc = _svc(db)
    try:
        lsx = svc.get(lsx_id)
    except Exception as exc:
        raise _map(exc)
    _guard_scope(db, lsx, user, authz)
    try:
        return svc.tao_khuon_cho_lenh(
            lsx, ten=payload.ten, loai=payload.loai, ngay_ve=payload.ngay_ve_du_kien, actor=user,
        )
    except Exception as exc:
        raise _map(exc)


@router.get("/{lsx_id}/dau-viec-options")
def dau_viec_options(
    lsx_id: int,
    cong_doan_id: int,
    department_id: int | None,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[dict]:
    """Đầu việc khoán hợp lệ sau khi kế hoạch đổi tổ của một bước LSX."""
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        return svc.dau_viec_options(
            lsx_id=lsx_id, cong_doan_id=cong_doan_id, department_id=department_id,
        )
    except Exception as exc:
        raise _map(exc)


@router.get("/{lsx_id}/xem-truoc-may")
def xem_truoc_may(
    lsx_id: int,
    step_key: str,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    may_id: int | None = None,
) -> dict:
    """Thời lượng bước NẾU đổi sang máy này — drawer hỏi trước khi lưu, không ghi gì.

    Chỉ server mới quy đổi được SL vào sang đơn vị tốc độ của máy (cầu quy đổi + công thức riêng
    của máy), nên đây là đường DUY NHẤT để ô thời gian nhảy ngay lúc chọn máy.
    Trả `dict` trần, KHÔNG bọc response_model: thêm khoá vào diễn giải mà quên khai schema là bị
    nuốt im lặng, mà khối này chính là thứ drawer đọc từng khoá.
    """
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        return svc.xem_truoc_may(lsx_id=lsx_id, step_key=step_key, may_id=may_id)
    except Exception as exc:
        raise _map(exc)


@router.put("/{lsx_id}", response_model=LsxOut)
def update_item(
    lsx_id: int,
    payload: LsxUpdateIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LsxOut:
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        lsx = svc.update(lsx_id=lsx_id, payload=payload, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": lsx.order_id})
    return _out(svc, lsx)


@router.post("/{lsx_id}/xem-truoc-quy-cach")
def xem_truoc_quy_cach(
    lsx_id: int,
    payload: LsxQuyCachIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Sửa thông số này thì các số máy tự tính ra bao nhiêu? — KHÔNG ghi DB.

    Có endpoint này để màn lệnh khỏi phải chép công thức engine sang JavaScript: hai bản công
    thức là chỗ đẻ ra cảnh màn hiện một số còn DB lưu số khác. Cùng khuôn với khối "SỐ TỜ TỰ TÍNH
    · ENGINE THẬT" bên phiếu tính giá.
    """
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        return svc.xem_truoc_quy_cach(
            lsx_id=lsx_id, patch=payload.model_dump(exclude_unset=True))
    except Exception as exc:
        raise _map(exc)


@router.post("/{lsx_id}/xem-truoc-routing", response_model=XemTruocRoutingOut)
def xem_truoc_routing(
    lsx_id: int,
    payload: XemTruocRoutingIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> XemTruocRoutingOut:
    """Đổi/chèn công đoạn thì số VÀO–RA + đơn vị cả chuỗi ra bao nhiêu? — KHÔNG ghi DB.

    Cùng lý do với `xem-truoc-quy-cach`: để drawer khỏi chép công thức chuỗi ngược sang
    JavaScript. Số nhảy ngay lúc đổi công đoạn (giống lúc đổi máy gọi thời lượng), khỏi bấm Lưu.
    """
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        return XemTruocRoutingOut(cong_doans=svc.xem_truoc_routing(
            lsx_id=lsx_id, rows_in=payload.cong_doans, actor=user))
    except Exception as exc:
        raise _map(exc)


@router.put("/{lsx_id}/routing", response_model=LsxOut)
def replace_routing(
    lsx_id: int,
    payload: RoutingReplaceIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LsxOut:
    """REPLACE-ALL routing của LỆNH — không đụng phiếu tính giá, không ảnh hưởng lệnh khác."""
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        lsx = svc.replace_routing(
            lsx_id=lsx_id, rows_in=payload.cong_doans, actor=user, ly_do=payload.ly_do
        )
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": lsx.order_id})
    return _out(svc, lsx)


@router.post("/{lsx_id}/buoc/{buoc_id}/giao-nhan", response_model=LsxOut)
def ghi_giao_nhan(
    lsx_id: int,
    buoc_id: int,
    payload: LsxGiaoNhanIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LsxOut:
    """Ghi nhận THỰC TẾ hàng gia công ngoài đi/về — CỬA RIÊNG, không đi qua lưu routing.

    Việc này xảy ra lúc lệnh ĐANG CHẠY (đã lập kế hoạch), mà `PUT /routing` chặn đúng trạng thái
    đó. Tách cửa để khỏi bắt kế hoạch gỡ lịch cả lệnh chỉ để ghi một dòng giao hàng. Quyền tái
    dùng `update` của lệnh — không đẻ vai mới; ai bấm ghi vào AuditLog.
    """
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        lsx = svc.ghi_giao_nhan(lsx_id=lsx_id, buoc_id=buoc_id, payload=payload, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": lsx.order_id})
    return _out(svc, lsx)


@router.get("/{lsx_id}/tinh-nguoc", response_model=TinhNguocOut)
def tinh_nguoc(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> TinhNguocOut:
    """Gợi ý SL vào/ra cho CẢ chuỗi, chạy ngược từ SL thành phẩm (BC: scrap cộng dồn từ bước cuối).

    CHỈ ĐỌC — không ghi gì. Máy đề xuất, người kế hoạch xem diff rồi mới bấm áp dụng + Lưu.
    """
    svc = _svc(db)
    try:
        lsx = svc.get(lsx_id)
    except Exception as exc:
        raise _map(exc)
    _guard_scope(db, lsx, user, authz)
    return TinhNguocOut(
        rows=[TinhNguocRow.model_validate(r) for r in svc.tinh_nguoc_routing(lsx)],
        so_to_ke_hoach=lsx.so_to_ke_hoach,
    )


@router.get("/{lsx_id}/mac-dinh-buoc/{cong_doan_id}", response_model=BuocMacDinhOut)
def mac_dinh_buoc(
    lsx_id: int,
    cong_doan_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> BuocMacDinhOut:
    """Bộ mặc định khi kế hoạch ĐỔI một bước sang công đoạn khác (loại bước · tổ · máy · đơn vị ·
    chuẩn bị · năng suất).

    Luật suy loại bước / đơn vị nằm ở service — client CHỈ áp kết quả, không tự tính lại, để hai
    nơi không trôi khỏi nhau. CHỈ ĐỌC, chưa ghi gì; người dùng vẫn phải bấm "Lưu công đoạn".
    """
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        return BuocMacDinhOut.model_validate(
            svc.mac_dinh_buoc(lsx_id=lsx_id, cong_doan_id=cong_doan_id)
        )
    except Exception as exc:
        raise _map(exc)


@router.post("/{lsx_id}/trang-thai", response_model=LsxOut)
def set_trang_thai(
    lsx_id: int,
    payload: TrangThaiIn,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LsxOut:
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        lsx = svc.set_trang_thai(lsx_id=lsx_id, trang_thai=payload.trang_thai, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": lsx.order_id})
    return _out(svc, lsx)


@router.delete("/{lsx_id}")
def delete_item(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Xoá lệnh chưa phát hành → dòng đơn quay lại hàng chờ (thay cho 'hủy lệnh' ở lát này)."""
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
        order_id = svc.xoa(lsx_id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "lsx_changed", "order_id": order_id})
    return {"ok": True}


@router.get("/{lsx_id}/activity", response_model=LsxActivityOut)
def activity(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> LsxActivityOut:
    """Nhật ký của 1 lệnh (ai sửa gì, khi nào) — đọc audit theo target `lsx:{id}`, mới→cũ."""
    svc = _svc(db)
    try:
        _guard_scope(db, svc.get(lsx_id), user, authz)
    except Exception as exc:
        raise _map(exc)
    rows = AuditLogRepository(db).list_by_target(f"lsx:{lsx_id}")
    names = actor_labels(db, {r.actor_user_id for r in rows if r.actor_user_id is not None})
    return LsxActivityOut(items=[
        LsxActivityItem(
            action=r.action,
            actor_name=names.get(r.actor_user_id) if r.actor_user_id else None,
            detail=r.detail,
            at=r.created_at,
        )
        for r in rows
    ])
