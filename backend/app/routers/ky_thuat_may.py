"""Kỹ thuật máy — router: phiếu sửa chữa · phiếu bảo trì · ảnh minh chứng.

RBAC — HAI module từ 17/08/2026, mỗi màn một ô: `ky_thuat_may` = Sửa chữa máy, `phieu_bao_tri` =
Phiếu bảo trì. Trước đó gộp một khoá ("coi như ông sửa và ông bảo trì là một", 12/08/2026); lý do
đó vẫn đúng với NGƯỜI LÀM — vai "Thợ sửa chữa" được cấp cả hai — nhưng ô quyền còn phải phục vụ
người ĐI CẤP: điều độ cần xem lịch bảo trì để né máy nằm mà không nên đọc phiếu máy hỏng. Migration
0209 sao chép quyền `ky_thuat_may` cũ sang khoá mới nên không ai mất đường làm việc.

Vẫn không có quyền duyệt, không tách nghiệm thu: người sửa cũng là người ký, cái gác cửa là ẢNH
chứ không phải chữ ký.

Cả hai module nằm trong `SCOPELESS_MODULES` — phiếu máy là việc chung của xưởng, không có "phiếu
của tôi".
"""
from __future__ import annotations

from datetime import date
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
from ..deps import get_authorization_service, require_any_permission, require_permission
from ..models.ky_thuat_may import (
    GIAI_DOAN_SAU,
    LOAI_PHIEU_BAO_TRI,
    LOAI_PHIEU_SUA_CHUA,
    TT_BT_HOAN_THANH,
)
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.ky_thuat_may_repo import KyThuatMayRepository
from ..schemas.ky_thuat_may import (
    AnhListOut,
    AnhRow,
    BaoTriIn,
    BaoTriListOut,
    BaoTriPatch,
    BaoTriRow,
    DoiLichIn,
    DenHanOut,
    DoiTrangThaiIn,
    HanMayOut,
    LichOut,
    SuaChuaIn,
    SuaChuaListOut,
    SuaChuaPatch,
    SuaChuaRow,
    TickHangMucIn,
)
from ..services.rbac_service import AuthorizationService
from ..services.ky_thuat_may_service import (
    KyThuatMayChuaXongViec,
    KyThuatMayNotFound,
    KyThuatMayService,
    KyThuatMayThieuAnh,
    KyThuatMayValidationError,
    hom_nay_vn,
)
from ..storage import get_storage, key_from_url, make_key, url_from_key

router = APIRouter(prefix="/api/ky-thuat-may", tags=["ky-thuat-may"])
MODULE = "ky_thuat_may"      # màn Sửa chữa máy
MODULE_BT = "phieu_bao_tri"  # màn Phiếu bảo trì

# Subdir storage — khai kèm ở `routers/files.py::_PREFIX_PERMISSION` để ảnh chỉ người có quyền đọc
# module này mới xem được (ảnh máy hỏng có thể lộ tình trạng nhà xưởng).
SUBDIR = "ky-thuat-may"
_MAX_ANH_BYTES = 15 * 1024 * 1024


def get_service(db: Annotated[Session, Depends(get_db)]) -> KyThuatMayService:
    return KyThuatMayService(db, KyThuatMayRepository(db), AuditLogRepository(db))


Service = Annotated[KyThuatMayService, Depends(get_service)]
Reader = Annotated[User, Depends(require_permission(MODULE, "read"))]
Writer = Annotated[User, Depends(require_permission(MODULE, "update"))]
Creator = Annotated[User, Depends(require_permission(MODULE, "create"))]
# Cửa của màn Phiếu bảo trì — cùng router, khác ô quyền (xem docstring đầu file).
BtReader = Annotated[User, Depends(require_permission(MODULE_BT, "read"))]
BtWriter = Annotated[User, Depends(require_permission(MODULE_BT, "update"))]
BtCreator = Annotated[User, Depends(require_permission(MODULE_BT, "create"))]
# Ảnh minh chứng dùng CHUNG một cửa cho cả hai loại phiếu ⇒ dep chỉ chặn được người không có ô
# nào; ô nào đúng với loại phiếu thì `_quyen_theo_loai` kiểm tiếp bên trong.
AnhReader = Annotated[User, Depends(require_any_permission((MODULE, "read"), (MODULE_BT, "read")))]
AnhWriter = Annotated[
    User, Depends(require_any_permission((MODULE, "update"), (MODULE_BT, "update")))
]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]
# Không khai `Deleter`: module này KHÔNG có đường xoá phiếu nào (xem ghi chú ở cuối mỗi mục). Để
# sẵn một cái tên chờ dùng là lời mời gắn nó vào một endpoint DELETE nào đó.


def _400(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _404(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


def _409(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ================= Phiếu sửa chữa =================


def _row_sua_chua(svc: KyThuatMayService, phieu, may_map: dict, anh_tk: dict) -> SuaChuaRow:
    """`anh_tk` = {phieu_id: (tổng ảnh, số ảnh "sau")} nạp sẵn cho CẢ TRANG (`repo.anh_thong_ke`).
    Hỏi từng dòng là N+1 — 20 dòng thành 20 query chỉ để bật/tắt một cái nút."""
    row = SuaChuaRow.model_validate(phieu)
    may = may_map.get(phieu.may_id) or {}
    row.may_ma, row.may_ten = may.get("ma"), may.get("ten")
    tong, sau = anh_tk.get(phieu.id, (0, 0))
    row.so_anh, row.co_anh_sau = tong, sau > 0
    return row


@router.get("/sua-chua", response_model=SuaChuaListOut)
def list_sua_chua(
    svc: Service,
    _: Reader,
    q: str | None = Query(default=None),
    may_id: int | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    muc_do: str | None = Query(default=None),
    # moi_nhat (mặc định) | cu_nhat | muc_do — xem `repo.list_sua_chua`.
    sort: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> SuaChuaListOut:
    rows, total = svc.list_sua_chua(q=q, may_id=may_id, trang_thai=trang_thai, muc_do=muc_do,
                                    sort=sort, page=page, size=size)
    may_map = svc.may_map([r.may_id for r in rows])
    anh_tk = svc.repo.anh_thong_ke(LOAI_PHIEU_SUA_CHUA, [r.id for r in rows])
    return SuaChuaListOut(
        items=[_row_sua_chua(svc, r, may_map, anh_tk) for r in rows],
        total=total, page=page, size=size,
        # Đếm theo ĐÚNG bộ lọc đang xem (trừ trạng thái) — gõ tìm kiếm mà số trên tab đứng im ở số
        # cả bảng thì người dùng chỉ còn cách tự đếm tay.
        dem=svc.dem_sua_chua(q=q, may_id=may_id, muc_do=muc_do),
    )


@router.get("/sua-chua/{phieu_id}", response_model=SuaChuaRow)
def get_sua_chua(phieu_id: int, svc: Service, _: Reader) -> SuaChuaRow:
    try:
        phieu = svc.get_sua_chua(phieu_id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    return _row_sua_chua(svc, phieu, svc.may_map([phieu.may_id]),
                         svc.repo.anh_thong_ke(LOAI_PHIEU_SUA_CHUA, [phieu.id]))


@router.post("/sua-chua", response_model=SuaChuaRow, status_code=status.HTTP_201_CREATED)
def create_sua_chua(payload: SuaChuaIn, svc: Service, user: Creator) -> SuaChuaRow:
    try:
        phieu = svc.tao_sua_chua(payload.model_dump(exclude_unset=True), actor_id=user.id)
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_sua_chua(svc, phieu, svc.may_map([phieu.may_id]), {})


@router.put("/sua-chua/{phieu_id}", response_model=SuaChuaRow)
def update_sua_chua(phieu_id: int, payload: SuaChuaPatch, svc: Service, user: Writer) -> SuaChuaRow:
    try:
        phieu = svc.sua_sua_chua(phieu_id, payload.model_dump(exclude_unset=True), actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_sua_chua(svc, phieu, svc.may_map([phieu.may_id]),
                         svc.repo.anh_thong_ke(LOAI_PHIEU_SUA_CHUA, [phieu.id]))


@router.post("/sua-chua/{phieu_id}/trang-thai", response_model=SuaChuaRow)
def doi_trang_thai_sua_chua(
    phieu_id: int, payload: DoiTrangThaiIn, svc: Service, user: Writer,
) -> SuaChuaRow:
    """Chuyển bước; `da_sua_xong` bị cửa ẢNH chặn (409 nếu chưa có ảnh chứng thực)."""
    try:
        phieu = svc.doi_trang_thai_sua_chua(phieu_id, payload.trang_thai, actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayThieuAnh as e:
        raise _409(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_sua_chua(svc, phieu, svc.may_map([phieu.may_id]),
                         svc.repo.anh_thong_ke(LOAI_PHIEU_SUA_CHUA, [phieu.id]))




# ================= Phiếu bảo trì =================


def _row_bao_tri(svc: KyThuatMayService, phieu, may_map: dict, anh_tk: dict,
                 hom_nay: date | None = None) -> BaoTriRow:
    hom_nay = hom_nay or hom_nay_vn()
    row = BaoTriRow.model_validate(phieu)
    may = may_map.get(phieu.may_id) or {}
    row.may_ma, row.may_ten = may.get("ma"), may.get("ten")
    # Nhóm máy lấy từ danh mục (`may_thiet_bi.loai_may`), KHÔNG đoán từ tiền tố mã: màn Lịch lọc
    # theo nhóm, mà đoán chữ thì máy đặt mã kiểu khác rơi hết vào một rổ "khác".
    row.may_loai = may.get("loai_may")
    tong, sau = anh_tk.get(phieu.id, (0, 0))
    row.so_anh, row.co_anh_sau = tong, sau > 0
    # DẪN XUẤT, không lưu: cột lưu là thứ phải nhớ đi cập nhật, và không ai nhớ.
    row.qua_han = phieu.trang_thai != TT_BT_HOAN_THANH and phieu.ngay_ke_hoach < hom_nay
    row.da_doi = bool(phieu.ngay_ke_hoach_goc and phieu.ngay_ke_hoach_goc != phieu.ngay_ke_hoach)
    return row


@router.get("/bao-tri", response_model=BaoTriListOut)
def list_bao_tri(
    svc: Service,
    _: BtReader,
    q: str | None = Query(default=None),
    may_id: int | None = Query(default=None),
    # Nhận cả `can_lam` / `qua_han` — hai bộ lọc dẫn xuất, xem `repo.list_bao_tri`.
    trang_thai: str | None = Query(default=None),
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    # han_som (mặc định) | han_muon
    sort: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> BaoTriListOut:
    rows, total = svc.list_bao_tri(q=q, may_id=may_id, trang_thai=trang_thai,
                                   tu=tu, den=den, sort=sort, page=page, size=size)
    may_map = svc.may_map([r.may_id for r in rows])
    anh_tk = svc.repo.anh_thong_ke(LOAI_PHIEU_BAO_TRI, [r.id for r in rows])
    hom_nay = hom_nay_vn()
    return BaoTriListOut(
        items=[_row_bao_tri(svc, r, may_map, anh_tk, hom_nay) for r in rows],
        total=total, page=page, size=size,
        # `dem` đi theo ĐÚNG bộ lọc đang xem (trừ trạng thái) — lọc tháng 8 mà tab đếm cả năm thì
        # con số trên tab chỉ còn là trang trí.
        dem=svc.dem_bao_tri(q=q, may_id=may_id, tu=tu, den=den),
    )






@router.get("/bao-tri/den-han", response_model=DenHanOut)
def den_han(svc: Service, _: BtReader) -> DenHanOut:
    """Số phiếu tới hạn/quá hạn còn dở — BADGE cạnh mục "Phiếu bảo trì" trên thanh bên.

    Đếm ở DB, không tải danh sách về đếm: badge nạp lại mỗi lần có sự kiện SSE. Câu SQL nằm ở repo
    (trước đây viết thẳng trong router — sai tầng, và nó tự tính "hôm nay" bằng UTC nên lệch 7 giờ
    với giờ VN).
    """
    tong, qua_han = svc.dem_den_han()
    return DenHanOut(total=tong, qua_han=qua_han)


@router.get("/bao-tri/lich", response_model=LichOut)
def lich_bao_tri(
    svc: Service,
    _: BtReader,
    tu: date = Query(...),
    den: date = Query(...),
) -> LichOut:
    """Màn LỊCH: phiếu thật + kỳ dự kiến chưa sinh, trong khoảng [tu, den].

    Khai TRƯỚC `/bao-tri/{phieu_id}` (FastAPI khớp theo thứ tự). Chặn khoảng > 366 ngày: kỳ dự
    kiến tính bằng vòng lặp cộng chu kỳ nên xin 10 năm là bắt server đếm hộ vài chục nghìn mốc.
    """
    if den < tu:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Khoảng ngày không hợp lệ.")
    if (den - tu).days > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chỉ xem tối đa 1 năm mỗi lần.")
    kq = svc.lich(tu, den)
    rows = kq["phieu"]
    may_map = svc.may_map([p.may_id for p in rows])
    anh_tk = svc.repo.anh_thong_ke(LOAI_PHIEU_BAO_TRI, [p.id for p in rows])
    hom_nay = hom_nay_vn()
    return LichOut(
        phieu=[_row_bao_tri(svc, p, may_map, anh_tk, hom_nay) for p in rows],
        du_kien=kq["du_kien"],
    )


@router.get("/bao-tri/han/{may_id}", response_model=HanMayOut)
def han_cua_may(may_id: int, svc: Service, _: BtReader) -> HanMayOut:
    """Hạn kế tiếp từng gói của một máy — tab "Lịch bảo trì" ở màn Thiết bị đọc endpoint này."""
    try:
        return HanMayOut(items=svc.han_cua_may(may_id))
    except KyThuatMayValidationError as e:
        raise _404(e) from None


@router.get("/bao-tri/{phieu_id}", response_model=BaoTriRow)
def get_bao_tri(phieu_id: int, svc: Service, _: BtReader) -> BaoTriRow:
    try:
        phieu = svc.get_bao_tri(phieu_id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_thong_ke(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri", response_model=BaoTriRow, status_code=status.HTTP_201_CREATED)
def create_bao_tri(payload: BaoTriIn, svc: Service, user: BtCreator) -> BaoTriRow:
    data = payload.model_dump(exclude_unset=True)
    if data.get("hang_muc") is not None:
        data["hang_muc"] = [dict(h) for h in data["hang_muc"]]
    try:
        phieu = svc.tao_bao_tri(data, actor_id=user.id)
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]), {})


@router.put("/bao-tri/{phieu_id}", response_model=BaoTriRow)
def update_bao_tri(phieu_id: int, payload: BaoTriPatch, svc: Service, user: BtWriter) -> BaoTriRow:
    data = payload.model_dump(exclude_unset=True)
    if data.get("hang_muc") is not None:
        data["hang_muc"] = [dict(h) for h in data["hang_muc"]]
    try:
        phieu = svc.sua_bao_tri(phieu_id, data, actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_thong_ke(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri/{phieu_id}/hang-muc", response_model=BaoTriRow)
def tick_hang_muc(phieu_id: int, payload: TickHangMucIn, svc: Service, user: BtWriter) -> BaoTriRow:
    try:
        phieu = svc.tick_hang_muc(phieu_id, payload.hang_muc_id, payload.xong,
                                  bo_qua=payload.bo_qua, ly_do=payload.ly_do, actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_thong_ke(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri/{phieu_id}/doi-lich", response_model=BaoTriRow)
def doi_lich(phieu_id: int, payload: DoiLichIn, svc: Service, user: BtWriter) -> BaoTriRow:
    try:
        phieu = svc.doi_lich(phieu_id, payload.ngay_moi, payload.ly_do, actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_thong_ke(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri/{phieu_id}/trang-thai", response_model=BaoTriRow)
def doi_trang_thai_bao_tri(
    phieu_id: int, payload: DoiTrangThaiIn, svc: Service, user: BtWriter,
) -> BaoTriRow:
    try:
        phieu = svc.doi_trang_thai_bao_tri(
            phieu_id, payload.trang_thai,
            ngay_hoan_thanh=payload.ngay_hoan_thanh, actor_id=user.id,
        )
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    # Hai cửa chặn, cùng 409: dữ liệu gửi lên hợp lệ, chỉ là TRẠNG THÁI phiếu chưa cho đóng.
    except (KyThuatMayThieuAnh, KyThuatMayChuaXongViec) as e:
        raise _409(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_thong_ke(LOAI_PHIEU_BAO_TRI, [phieu.id]))




# ================= Ảnh minh chứng (dùng chung 2 loại phiếu) =================


def _quyen_theo_loai(authz: AuthorizationService, user: User, loai_phieu: str, viec: str) -> None:
    """Ba cửa ảnh dùng chung cho hai loại phiếu, mà từ 17/08/2026 là HAI ô quyền khác nhau.

    Dep `AnhReader`/`AnhWriter` chỉ chặn được người KHÔNG có ô nào; đúng ô của đúng loại phiếu phải
    kiểm ở đây — thiếu bước này thì người chỉ được cấp Phiếu bảo trì lại gỡ được ảnh chứng thực của
    phiếu sửa chữa, tức làm rỗng bằng chứng của một việc đã ký ở màn họ không có quyền mở.
    """
    mk = MODULE_BT if loai_phieu == LOAI_PHIEU_BAO_TRI else MODULE
    if not authz.can(user, mk, viec):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Bạn không có quyền thực hiện thao tác này"
        )


def _phieu_ton_tai(svc: KyThuatMayService, loai_phieu: str, phieu_id: int) -> None:
    """Kiểm phiếu có thật TRƯỚC khi ghi file — né rác trong storage khi id sai."""
    try:
        if loai_phieu == LOAI_PHIEU_SUA_CHUA:
            svc.get_sua_chua(phieu_id)
        elif loai_phieu == LOAI_PHIEU_BAO_TRI:
            svc.get_bao_tri(phieu_id)
        else:
            raise KyThuatMayValidationError(f"Loại phiếu không hợp lệ: {loai_phieu}")
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None


@router.get("/{loai_phieu}/{phieu_id}/anh", response_model=AnhListOut)
def list_anh(
    loai_phieu: str, phieu_id: int, svc: Service, user: AnhReader, authz: Authz,
) -> AnhListOut:
    _quyen_theo_loai(authz, user, loai_phieu, "read")
    _phieu_ton_tai(svc, loai_phieu, phieu_id)
    return AnhListOut(items=[AnhRow.model_validate(a) for a in svc.list_anh(loai_phieu, phieu_id)])


@router.post("/{loai_phieu}/{phieu_id}/anh", response_model=AnhRow,
             status_code=status.HTTP_201_CREATED)
def upload_anh(
    loai_phieu: str,
    phieu_id: int,
    svc: Service,
    user: AnhWriter,
    authz: Authz,
    giai_doan: str = Query(default=GIAI_DOAN_SAU),
    file: UploadFile = File(...),
) -> AnhRow:
    _quyen_theo_loai(authz, user, loai_phieu, "update")
    _phieu_ton_tai(svc, loai_phieu, phieu_id)
    data = file.file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tệp rỗng.")
    if len(data) > _MAX_ANH_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Ảnh vượt quá 15MB.")
    # Cửa ảnh của module là "có ảnh mới đóng được phiếu" — nhận cả PDF/zip thì cái cửa đó qua được
    # bằng một tệp trắng. Chỉ kiểm content-type: đủ chặn nhầm lẫn, không cần soi nội dung tệp.
    if not (file.content_type or "").lower().startswith("image/"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Chỉ nhận tệp ảnh (JPG, PNG, HEIC…) — tệp này là {file.content_type or 'không rõ loại'}.",
        )

    key, safe = make_key(f"{SUBDIR}/{loai_phieu}", phieu_id, file.filename)
    get_storage().save(key, data, file.content_type)
    try:
        anh = svc.them_anh(
            loai_phieu, phieu_id, giai_doan=giai_doan,
            file_name=safe, file_url=url_from_key(key), file_type=file.content_type,
            actor_id=user.id,
        )
    except KyThuatMayValidationError as e:
        get_storage().delete(key)  # ghi file rồi mới lỗi ⇒ dọn, đừng để rác mồ côi trong storage
        raise _400(e) from None
    return AnhRow.model_validate(anh)


@router.delete("/anh/{anh_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_anh(anh_id: int, svc: Service, user: AnhWriter, authz: Authz) -> Response:
    # Đọc ảnh TRƯỚC để biết nó thuộc loại phiếu nào rồi mới kiểm quyền — `xoa_anh` cũng tra lại,
    # nhưng kiểm sau khi xoá thì đã muộn.
    truoc = svc.repo.get_anh(anh_id)
    if truoc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy ảnh.")
    _quyen_theo_loai(authz, user, truoc.loai_phieu, "update")
    try:
        anh = svc.xoa_anh(anh_id, actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _409(e) from None
    key = key_from_url(anh.file_url)
    if key:
        get_storage().delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
