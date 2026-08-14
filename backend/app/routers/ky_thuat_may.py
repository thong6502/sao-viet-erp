"""Kỹ thuật máy — router: phiếu sửa chữa · phiếu bảo trì · ảnh minh chứng.

RBAC: MỘT module `ky_thuat_may` cho cả hai màn, chỉ hai công tắc Xem / Chỉnh sửa (chủ chốt
12/08/2026 — "coi như ông sửa và ông bảo trì là một"). Không quyền duyệt, không tách nghiệm thu:
người sửa cũng là người ký, cái gác cửa là ẢNH chứ không phải chữ ký.

Module nằm trong `SCOPELESS_MODULES` — phiếu máy là việc chung của xưởng, không có "phiếu của tôi".
"""
from __future__ import annotations

from datetime import date, datetime, timezone
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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.ky_thuat_may import (
    GIAI_DOAN_SAU,
    LOAI_PHIEU_BAO_TRI,
    LOAI_PHIEU_SUA_CHUA,
    TT_BT_DANG_MO,
    TT_BT_HOAN_THANH,
    BaoTriMay,
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
from ..services.ky_thuat_may_service import (
    KyThuatMayNotFound,
    KyThuatMayService,
    KyThuatMayThieuAnh,
    KyThuatMayValidationError,
)
from ..storage import get_storage, key_from_url, make_key, url_from_key

router = APIRouter(prefix="/api/ky-thuat-may", tags=["ky-thuat-may"])
MODULE = "ky_thuat_may"

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
Deleter = Annotated[User, Depends(require_permission(MODULE, "delete"))]


def _400(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _404(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


def _409(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ================= Phiếu sửa chữa =================


def _row_sua_chua(svc: KyThuatMayService, phieu, may_map: dict, anh_map: dict) -> SuaChuaRow:
    row = SuaChuaRow.model_validate(phieu)
    may = may_map.get(phieu.may_id) or {}
    row.may_ma, row.may_ten = may.get("ma"), may.get("ten")
    row.so_anh = anh_map.get(phieu.id, 0)
    row.co_anh_sau = svc.repo.dem_anh_sau(LOAI_PHIEU_SUA_CHUA, phieu.id) > 0
    return row


@router.get("/sua-chua", response_model=SuaChuaListOut)
def list_sua_chua(
    svc: Service,
    _: Reader,
    q: str | None = Query(default=None),
    may_id: int | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> SuaChuaListOut:
    rows, total = svc.list_sua_chua(q=q, may_id=may_id, trang_thai=trang_thai, page=page, size=size)
    may_map = svc.may_map([r.may_id for r in rows])
    anh_map = svc.repo.anh_map(LOAI_PHIEU_SUA_CHUA, [r.id for r in rows])
    return SuaChuaListOut(
        items=[_row_sua_chua(svc, r, may_map, anh_map) for r in rows],
        total=total, page=page, size=size, dem=svc.dem_sua_chua(),
    )


@router.get("/sua-chua/{phieu_id}", response_model=SuaChuaRow)
def get_sua_chua(phieu_id: int, svc: Service, _: Reader) -> SuaChuaRow:
    try:
        phieu = svc.get_sua_chua(phieu_id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    return _row_sua_chua(svc, phieu, svc.may_map([phieu.may_id]),
                         svc.repo.anh_map(LOAI_PHIEU_SUA_CHUA, [phieu.id]))


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
                         svc.repo.anh_map(LOAI_PHIEU_SUA_CHUA, [phieu.id]))


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
                         svc.repo.anh_map(LOAI_PHIEU_SUA_CHUA, [phieu.id]))


# 🔴 KHÔNG có `DELETE /sua-chua/{id}` (chủ chốt 12/08/2026). Phiếu là VẾT của một việc đã xảy ra
# ngoài đời: máy đã hỏng, thợ đã sờ vào, ảnh đã chụp. Xoá được nghĩa là lịch sử hỏng hóc của máy có
# thể bị dọn sạch — đúng thứ người ta cần nhất khi cãi nhau "máy này hay hỏng chỗ nào".
# Ghi nhầm thì SỬA nội dung; phiếu không còn hiệu lực thì để nguyên đó, nó không cản ai.


# ================= Phiếu bảo trì =================


def _row_bao_tri(svc: KyThuatMayService, phieu, may_map: dict, anh_map: dict,
                 hom_nay: date | None = None) -> BaoTriRow:
    hom_nay = hom_nay or datetime.now(timezone.utc).date()
    row = BaoTriRow.model_validate(phieu)
    may = may_map.get(phieu.may_id) or {}
    row.may_ma, row.may_ten = may.get("ma"), may.get("ten")
    row.so_anh = anh_map.get(phieu.id, 0)
    row.co_anh_sau = svc.repo.dem_anh_sau(LOAI_PHIEU_BAO_TRI, phieu.id) > 0
    # DẪN XUẤT, không lưu: cột lưu là thứ phải nhớ đi cập nhật, và không ai nhớ.
    row.qua_han = phieu.trang_thai != TT_BT_HOAN_THANH and phieu.ngay_ke_hoach < hom_nay
    row.da_doi = bool(phieu.ngay_ke_hoach_goc and phieu.ngay_ke_hoach_goc != phieu.ngay_ke_hoach)
    return row


@router.get("/bao-tri", response_model=BaoTriListOut)
def list_bao_tri(
    svc: Service,
    _: Reader,
    q: str | None = Query(default=None),
    may_id: int | None = Query(default=None),
    # Nhận cả `can_lam` / `qua_han` — hai bộ lọc dẫn xuất, xem `repo.list_bao_tri`.
    trang_thai: str | None = Query(default=None),
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> BaoTriListOut:
    rows, total = svc.list_bao_tri(q=q, may_id=may_id, trang_thai=trang_thai,
                                   tu=tu, den=den, page=page, size=size)
    may_map = svc.may_map([r.may_id for r in rows])
    anh_map = svc.repo.anh_map(LOAI_PHIEU_BAO_TRI, [r.id for r in rows])
    return BaoTriListOut(
        items=[_row_bao_tri(svc, r, may_map, anh_map) for r in rows],
        total=total, page=page, size=size, dem=svc.dem_bao_tri(),
    )


# 🔴 `POST /bao-tri/sinh-tu-lich` ĐÃ GỠ 12/08/2026 (chủ chốt). Nút "quét tất cả máy rồi đẻ phiếu
# hàng loạt" là nguồn gốc của 41 phiếu rác cùng ngày; từ khi có màn LỊCH thì cách tạo phiếu định kỳ
# là bấm thẳng vào ô kỳ dự kiến (`GET /bao-tri/lich` + `POST /bao-tri` kèm `goi_id`), tạo đúng một
# phiếu người ta đang nhìn. Đừng dựng lại.


# 🔴 `POST /bao-tri/don-phieu-chua-dung` cũng GỠ luôn: nó sinh ra chỉ để hốt 41 phiếu rác của cái
# nút trên. Không còn cơ chế đẻ hàng loạt thì không còn rác hàng loạt để dọn — phiếu lẻ tạo nhầm thì
# mở ra bấm "Xoá phiếu" là xong.


@router.get("/bao-tri/den-han", response_model=DenHanOut)
def den_han(
    db: Annotated[Session, Depends(get_db)],
    _: Reader,
) -> DenHanOut:
    """Số phiếu tới hạn/quá hạn còn dở — BADGE cạnh mục "Phiếu bảo trì" trên thanh bên.

    Đếm ở DB, không tải danh sách về đếm: badge nạp lại mỗi lần có sự kiện SSE.
    """
    hom_nay = datetime.now(timezone.utc).date()
    tong = int(db.execute(
        select(func.count()).select_from(BaoTriMay).where(
            BaoTriMay.ngay_ke_hoach <= hom_nay,
            BaoTriMay.trang_thai.in_(TT_BT_DANG_MO),
        )
    ).scalar_one())
    qua_han = int(db.execute(
        select(func.count()).select_from(BaoTriMay).where(
            BaoTriMay.ngay_ke_hoach < hom_nay,
            BaoTriMay.trang_thai.in_(TT_BT_DANG_MO),
        )
    ).scalar_one())
    return DenHanOut(total=tong, qua_han=qua_han)


@router.get("/bao-tri/lich", response_model=LichOut)
def lich_bao_tri(
    svc: Service,
    _: Reader,
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
    anh_map = svc.repo.anh_map(LOAI_PHIEU_BAO_TRI, [p.id for p in rows])
    return LichOut(
        phieu=[_row_bao_tri(svc, p, may_map, anh_map) for p in rows],
        du_kien=kq["du_kien"],
    )


@router.get("/bao-tri/han/{may_id}", response_model=HanMayOut)
def han_cua_may(may_id: int, svc: Service, _: Reader) -> HanMayOut:
    """Hạn kế tiếp từng gói của một máy — tab "Lịch bảo trì" ở màn Thiết bị đọc endpoint này."""
    try:
        return HanMayOut(items=svc.han_cua_may(may_id))
    except KyThuatMayValidationError as e:
        raise _404(e) from None


@router.get("/bao-tri/{phieu_id}", response_model=BaoTriRow)
def get_bao_tri(phieu_id: int, svc: Service, _: Reader) -> BaoTriRow:
    try:
        phieu = svc.get_bao_tri(phieu_id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_map(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri", response_model=BaoTriRow, status_code=status.HTTP_201_CREATED)
def create_bao_tri(payload: BaoTriIn, svc: Service, user: Creator) -> BaoTriRow:
    data = payload.model_dump(exclude_unset=True)
    if data.get("hang_muc") is not None:
        data["hang_muc"] = [dict(h) for h in data["hang_muc"]]
    try:
        phieu = svc.tao_bao_tri(data, actor_id=user.id)
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]), {})


@router.put("/bao-tri/{phieu_id}", response_model=BaoTriRow)
def update_bao_tri(phieu_id: int, payload: BaoTriPatch, svc: Service, user: Writer) -> BaoTriRow:
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
                        svc.repo.anh_map(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri/{phieu_id}/hang-muc", response_model=BaoTriRow)
def tick_hang_muc(phieu_id: int, payload: TickHangMucIn, svc: Service, user: Writer) -> BaoTriRow:
    try:
        phieu = svc.tick_hang_muc(phieu_id, payload.hang_muc_id, payload.xong, actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_map(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri/{phieu_id}/doi-lich", response_model=BaoTriRow)
def doi_lich(phieu_id: int, payload: DoiLichIn, svc: Service, user: Writer) -> BaoTriRow:
    try:
        phieu = svc.doi_lich(phieu_id, payload.ngay_moi, payload.ly_do, actor_id=user.id)
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_map(LOAI_PHIEU_BAO_TRI, [phieu.id]))


@router.post("/bao-tri/{phieu_id}/trang-thai", response_model=BaoTriRow)
def doi_trang_thai_bao_tri(
    phieu_id: int, payload: DoiTrangThaiIn, svc: Service, user: Writer,
) -> BaoTriRow:
    try:
        phieu = svc.doi_trang_thai_bao_tri(
            phieu_id, payload.trang_thai,
            ngay_hoan_thanh=payload.ngay_hoan_thanh, actor_id=user.id,
        )
    except KyThuatMayNotFound as e:
        raise _404(e) from None
    except KyThuatMayThieuAnh as e:
        raise _409(e) from None
    except KyThuatMayValidationError as e:
        raise _400(e) from None
    return _row_bao_tri(svc, phieu, svc.may_map([phieu.may_id]),
                        svc.repo.anh_map(LOAI_PHIEU_BAO_TRI, [phieu.id]))


# 🔴 KHÔNG có `DELETE /bao-tri/{id}` — cùng lý do với phiếu sửa chữa, cộng thêm một điều nữa: phiếu
# bảo trì đã hoàn thành là MỐC tính kỳ kế tiếp. Xoá một phiếu là chuỗi kỳ phía sau tính lại từ đầu
# mà không ai thấy nó vừa đổi.


# ================= Ảnh minh chứng (dùng chung 2 loại phiếu) =================


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
def list_anh(loai_phieu: str, phieu_id: int, svc: Service, _: Reader) -> AnhListOut:
    _phieu_ton_tai(svc, loai_phieu, phieu_id)
    return AnhListOut(items=[AnhRow.model_validate(a) for a in svc.list_anh(loai_phieu, phieu_id)])


@router.post("/{loai_phieu}/{phieu_id}/anh", response_model=AnhRow,
             status_code=status.HTTP_201_CREATED)
def upload_anh(
    loai_phieu: str,
    phieu_id: int,
    svc: Service,
    user: Writer,
    giai_doan: str = Query(default=GIAI_DOAN_SAU),
    file: UploadFile = File(...),
) -> AnhRow:
    _phieu_ton_tai(svc, loai_phieu, phieu_id)
    data = file.file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tệp rỗng.")
    if len(data) > _MAX_ANH_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Ảnh vượt quá 15MB.")

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
def delete_anh(anh_id: int, svc: Service, user: Writer) -> Response:
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
