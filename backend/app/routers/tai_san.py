"""Router — sổ tài sản cố định & công cụ dụng cụ (module quyền `tai_san`).

⚠️ Route TĨNH (`/ky…`, `/kiem-ke…`) phải khai TRƯỚC route động `/{tai_san_id}`: FastAPI khớp
theo THỨ TỰ khai, để sau thì chuỗi "ky" rơi vào `{tai_san_id}` và ăn 422 vì không ép được sang
int. Cùng bẫy đã dính ở `may_thiet_bi.py`.

Dependency provider khai INLINE để không đụng `deps.py` (file dùng chung).

Quyền: dùng lại action có sẵn — `read`/`create`/`update`/`delete`/`export`, và `close_book` cho
chốt/mở kỳ (cột `can_close_book` đã có trên `role_permissions`, không đẻ cột mới).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.department import Department
from ..models.tai_san import NGUON_DAU_KY, TaiSan, TaiSanKhauHao
from ..models.user import User
from ..repositories.tai_san_repo import TaiSanRepository
from ..schemas.tai_san import (
    BangKyOut,
    BienDongIn,
    BienDongOut,
    DongDuKienOut,
    KetQuaKiemKeOut,
    KiemKeDetailOut,
    KiemKeDongIn,
    KiemKeDongOut,
    KiemKeIn,
    KiemKeListOut,
    KiemKeRow,
    KyOut,
    PhatHienIn,
    TaiSanDetailOut,
    TaiSanIn,
    TaiSanListOut,
    TaiSanRow,
    TaiSanSuaIn,
)
from ..services.tai_san.excel import MEDIA_XLSX, xuat_bang_ky
from ..services.tai_san.kiem_ke_service import (
    KiemKeDaKet,
    KiemKeNotFound,
    KiemKeService,
    KiemKeValidationError,
)
from ..services.tai_san.ky_service import (
    KyCoChungTuSau,
    KyDaChot,
    KyKhongTonTai,
    KyService,
    KyTruocChuaChot,
)
from ..services.tai_san.service import (
    TaiSanDaChotKy,
    TaiSanNotFound,
    TaiSanService,
    TaiSanTrung,
    TaiSanValidationError,
)

router = APIRouter(prefix="/api/tai-san", tags=["tai-san"])
MODULE = "tai_san"

_DOC = require_permission(MODULE, "read")
_TAO = require_permission(MODULE, "create")
_GHI = require_permission(MODULE, "update")
_XOA = require_permission(MODULE, "delete")
_XUAT = require_permission(MODULE, "export")
_CHOT = require_permission(MODULE, "close_book")


def get_service(db: Annotated[Session, Depends(get_db)]) -> TaiSanService:
    return TaiSanService(TaiSanRepository(db))


def get_ky_service(db: Annotated[Session, Depends(get_db)]) -> KyService:
    return KyService(db)


def get_kiem_ke_service(db: Annotated[Session, Depends(get_db)]) -> KiemKeService:
    return KiemKeService(db)


Service = Annotated[TaiSanService, Depends(get_service)]
Ky = Annotated[KyService, Depends(get_ky_service)]
KiemKe = Annotated[KiemKeService, Depends(get_kiem_ke_service)]
Db = Annotated[Session, Depends(get_db)]


def _ten_bo_phan(db: Session, ids: set[int]) -> dict[int, str]:
    """Một truy vấn cho cả trang — không tra danh mục từng dòng."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {
        i: ten
        for i, ten in db.execute(
            select(Department.id, Department.name).where(Department.id.in_(ids))
        )
    }


def _dung_rows(db: Session, objs: list[TaiSan]) -> list[TaiSanRow]:
    ten = _ten_bo_phan(db, {o.bo_phan_id for o in objs})
    ra = []
    for o in objs:
        row = TaiSanRow.model_validate(o)
        row.bo_phan_ten = ten.get(o.bo_phan_id)
        row.con_lai = int(o.nguyen_gia or 0) - int(o.hao_mon_luy_ke or 0)
        ra.append(row)
    return ra


def _bao_loi(exc: Exception) -> HTTPException:
    """Một chỗ đổi lỗi nghiệp vụ sang HTTP — mọi endpoint dùng chung, khỏi lệch mã."""
    if isinstance(exc, TaiSanNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (TaiSanTrung, TaiSanDaChotKy, KyDaChot, KyTruocChuaChot, KyCoChungTuSau)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, KyKhongTonTai):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


LOI_NGHIEP_VU = (
    TaiSanNotFound, TaiSanTrung, TaiSanValidationError, TaiSanDaChotKy,
    KyDaChot, KyTruocChuaChot, KyKhongTonTai, KyCoChungTuSau,
)

LOI_KIEM_KE = (KiemKeNotFound, KiemKeDaKet, KiemKeValidationError)


def _bao_loi_kiem_ke(exc: Exception) -> HTTPException:
    if isinstance(exc, KiemKeNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, KiemKeDaKet):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _dung_dot(kk: KiemKeService, dot_id: int) -> KiemKeDetailOut:
    dot = kk.lay(dot_id)
    return KiemKeDetailOut(
        **KiemKeRow.model_validate(dot).model_dump(),
        dong=[KiemKeDongOut(**d) for d in kk.dong_kem_ten(dot_id)],
    )


# =====================================================================================
# Route TĨNH — khai TRƯỚC mọi route `/{tai_san_id}` (xem cảnh báo ở docstring)
# =====================================================================================


@router.get("/ky", response_model=list[KyOut])
def danh_sach_ky(ky: Ky, _: Annotated[User, Depends(_DOC)]) -> list[KyOut]:
    return [KyOut.model_validate(k) for k in ky.danh_sach_ky()]


def _bang_ky(ky: KyService, nam: int, thang: int) -> BangKyOut:
    k = ky.lay_ky(nam, thang)
    items = ky.bang(nam, thang)
    return BangKyOut(
        nam=nam,
        thang=thang,
        trang_thai=k.trang_thai if k else "mo",
        tong_muc_trich=sum(int(h["muc_trich"]) for h in items),
        items=items,
    )


@router.get("/ky/{nam}/{thang}/bang", response_model=BangKyOut)
def bang_ky(nam: int, thang: int, ky: Ky, _: Annotated[User, Depends(_DOC)]) -> BangKyOut:
    return _bang_ky(ky, nam, thang)


@router.post("/ky/{nam}/{thang}/tinh", response_model=BangKyOut)
def tinh_ky(nam: int, thang: int, ky: Ky, _: Annotated[User, Depends(_GHI)]) -> BangKyOut:
    """Tính (hoặc tính lại) khấu hao của kỳ. Ghi đè dòng cũ, KHÔNG cộng dồn."""
    try:
        ky.tinh(nam, thang)
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None
    return _bang_ky(ky, nam, thang)


@router.get("/ky/{nam}/{thang}/excel")
def excel_ky(
    nam: int, thang: int, ky: Ky, _: Annotated[User, Depends(_XUAT)]
) -> Response:
    """Bảng khấu hao kỳ ra .xlsx — bảng để kế toán đọc rồi tự gõ sang phần mềm kế toán bên
    ngoài; cột cuối là Còn lại."""
    noi_dung = xuat_bang_ky(ky.bang(nam, thang), nam=nam, thang=thang)
    return Response(
        content=noi_dung,
        media_type=MEDIA_XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="khau-hao-{thang:02d}-{nam}.xlsx"'
        },
    )


@router.post("/ky/{nam}/{thang}/chot", response_model=KyOut)
def chot_ky(
    nam: int, thang: int, ky: Ky, user: Annotated[User, Depends(_CHOT)]
) -> KyOut:
    try:
        return KyOut.model_validate(ky.chot(nam, thang, user_id=user.id))
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None


@router.post("/ky/{nam}/{thang}/mo", response_model=KyOut)
def mo_ky(nam: int, thang: int, ky: Ky, _: Annotated[User, Depends(_CHOT)]) -> KyOut:
    try:
        return KyOut.model_validate(ky.mo(nam, thang))
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None


# --- Kiểm kê (vẫn là route TĨNH — phải nằm TRƯỚC `/{tai_san_id}`) ---------------------


@router.get("/kiem-ke", response_model=KiemKeListOut)
def danh_sach_kiem_ke(
    kk: KiemKe,
    _: Annotated[User, Depends(_DOC)],
    offset: int = 0,
    limit: int = Query(default=50, ge=1, le=200),
) -> KiemKeListOut:
    rows, tong = kk.danh_sach(offset=offset, limit=limit)
    return KiemKeListOut(items=[KiemKeRow.model_validate(r) for r in rows], total=tong)


@router.post("/kiem-ke", response_model=KiemKeDetailOut, status_code=status.HTTP_201_CREATED)
def tao_dot_kiem_ke(
    payload: KiemKeIn, kk: KiemKe, user: Annotated[User, Depends(_TAO)]
) -> KiemKeDetailOut:
    dot = kk.tao_dot(
        ngay=payload.ngay, bo_phan_id=payload.bo_phan_id, ghi_chu=payload.ghi_chu,
        user_id=user.id,
    )
    return _dung_dot(kk, dot.id)


@router.get("/kiem-ke/{dot_id}", response_model=KiemKeDetailOut)
def chi_tiet_kiem_ke(
    dot_id: int, kk: KiemKe, _: Annotated[User, Depends(_DOC)]
) -> KiemKeDetailOut:
    try:
        return _dung_dot(kk, dot_id)
    except LOI_KIEM_KE as e:
        raise _bao_loi_kiem_ke(e) from None


@router.put("/kiem-ke/{dot_id}/dong/{dong_id}", response_model=KiemKeDetailOut)
def ghi_ket_qua_kiem_ke(
    dot_id: int, dong_id: int, payload: KiemKeDongIn, kk: KiemKe,
    _: Annotated[User, Depends(_GHI)],
) -> KiemKeDetailOut:
    try:
        kk.ghi_ket_qua(
            dot_id, dong_id, ket_qua=payload.ket_qua, tinh_trang=payload.tinh_trang,
            ghi_chu=payload.ghi_chu,
        )
        return _dung_dot(kk, dot_id)
    except LOI_KIEM_KE as e:
        raise _bao_loi_kiem_ke(e) from None


@router.post("/kiem-ke/{dot_id}/phat-hien", response_model=KiemKeDetailOut)
def them_phat_hien(
    dot_id: int, payload: PhatHienIn, kk: KiemKe, _: Annotated[User, Depends(_GHI)]
) -> KiemKeDetailOut:
    """Món có ở xưởng mà không có trong sổ — ghi nhận vào đợt, chưa phải ghi tăng."""
    try:
        kk.them_phat_hien(
            dot_id, ten_phat_hien=payload.ten_phat_hien, tinh_trang=payload.tinh_trang,
            ghi_chu=payload.ghi_chu,
        )
        return _dung_dot(kk, dot_id)
    except LOI_KIEM_KE as e:
        raise _bao_loi_kiem_ke(e) from None


@router.post("/kiem-ke/{dot_id}/ket-thuc", response_model=KetQuaKiemKeOut)
def ket_thuc_kiem_ke(
    dot_id: int, kk: KiemKe, _: Annotated[User, Depends(_GHI)]
) -> KetQuaKiemKeOut:
    try:
        return KetQuaKiemKeOut(**kk.ket_thuc(dot_id))
    except LOI_KIEM_KE as e:
        raise _bao_loi_kiem_ke(e) from None


# =====================================================================================
# Sổ tài sản
# =====================================================================================


@router.get("", response_model=TaiSanListOut)
def danh_sach(
    db: Db,
    svc: Service,
    _: Annotated[User, Depends(_DOC)],
    q: str | None = None,
    loai: str | None = None,
    bo_phan_id: int | None = None,
    trang_thai: str | None = None,
    offset: int = 0,
    limit: int = Query(default=50, ge=1, le=200),
) -> TaiSanListOut:
    rows, tong = svc.repo.danh_sach(
        q=q, loai=loai, bo_phan_id=bo_phan_id, trang_thai=trang_thai,
        offset=offset, limit=limit,
    )
    return TaiSanListOut(items=_dung_rows(db, rows), total=tong)


@router.post("", response_model=TaiSanRow, status_code=status.HTTP_201_CREATED)
def ghi_tang(
    payload: TaiSanIn, db: Db, svc: Service, user: Annotated[User, Depends(_TAO)]
) -> TaiSanRow:
    body = payload.model_dump()
    body["chi_phi"] = [c for c in body.get("chi_phi") or []]
    try:
        if body.get("nguon_vao") == NGUON_DAU_KY:
            t = svc.nap_dau_ky(body, user_id=user.id)
        else:
            t = svc.ghi_tang(body, user_id=user.id)
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None
    return _dung_rows(db, [t])[0]


@router.get("/{tai_san_id}", response_model=TaiSanDetailOut)
def chi_tiet(
    tai_san_id: int, db: Db, svc: Service, _: Annotated[User, Depends(_DOC)]
) -> TaiSanDetailOut:
    t = svc.repo.lay_kem_chi_tiet(tai_san_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài sản #{tai_san_id}")
    row = _dung_rows(db, [t])[0]
    khau_hao = list(
        db.execute(
            select(TaiSanKhauHao)
            .where(TaiSanKhauHao.tai_san_id == tai_san_id)
            .order_by(TaiSanKhauHao.ky_nam, TaiSanKhauHao.ky_thang)
        ).scalars()
    )
    return TaiSanDetailOut(
        **row.model_dump(),
        chi_phi=t.chi_phi,
        bien_dong=[BienDongOut.model_validate(b) for b in t.bien_dong],
        khau_hao=khau_hao,
        chenh_lech_thanh_ly=svc.chenh_lech_thanh_ly(tai_san_id),
    )


@router.put("/{tai_san_id}", response_model=TaiSanRow)
def sua(
    tai_san_id: int, payload: TaiSanSuaIn, db: Db, svc: Service,
    _: Annotated[User, Depends(_GHI)],
) -> TaiSanRow:
    body = payload.model_dump(exclude_unset=True)
    try:
        t = svc.sua(tai_san_id, body)
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None
    return _dung_rows(db, [t])[0]


@router.delete("/{tai_san_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def xoa(tai_san_id: int, svc: Service, _: Annotated[User, Depends(_XOA)]) -> Response:
    try:
        svc.xoa(tai_san_id)
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{tai_san_id}/du-kien", response_model=list[DongDuKienOut])
def du_kien(
    tai_san_id: int, svc: Service, _: Annotated[User, Depends(_DOC)]
) -> list[DongDuKienOut]:
    """Bảng khấu hao DỰ KIẾN — hiện ngay sau khi lưu phiếu ghi tăng, chưa ghi sổ."""
    try:
        return [DongDuKienOut(**d.__dict__) for d in svc.du_kien(tai_san_id)]
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None


@router.post(
    "/{tai_san_id}/bien-dong", response_model=BienDongOut, status_code=status.HTTP_201_CREATED
)
def bien_dong(
    tai_san_id: int, payload: BienDongIn, svc: Service, user: Annotated[User, Depends(_GHI)]
) -> BienDongOut:
    """Một cửa cho cả ba chứng từ — `loai` quyết định ô nào bắt buộc."""
    try:
        if payload.loai == "dieu_chuyen":
            bd = svc.dieu_chuyen(
                tai_san_id, ngay=payload.ngay, bo_phan_moi_id=payload.bo_phan_moi_id or 0,
                ly_do=payload.ly_do, user_id=user.id,
            )
        elif payload.loai == "nang_cap":
            bd = svc.nang_cap(
                tai_san_id, ngay=payload.ngay, so_tien=int(payload.so_tien or 0),
                so_thang_con_lai=int(payload.so_thang_con_lai or 0), ly_do=payload.ly_do,
                user_id=user.id,
            )
        elif payload.loai == "ghi_giam":
            bd = svc.ghi_giam(
                tai_san_id, ngay=payload.ngay, ly_do=payload.ly_do or "",
                gia_ban=payload.gia_ban, so_luong_giam=payload.so_luong_giam,
                user_id=user.id,
            )
        else:
            raise TaiSanValidationError(f"Loại biến động không hợp lệ: {payload.loai}")
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None
    return BienDongOut.model_validate(bd)
