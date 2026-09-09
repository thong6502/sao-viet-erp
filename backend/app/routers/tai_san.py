"""Router — sổ tài sản cố định & công cụ dụng cụ (module quyền `tai_san`).

⚠️ Route TĨNH (`/thang…`, `/nhan-vien`) phải khai TRƯỚC route động `/{tai_san_id}`: FastAPI khớp
theo THỨ TỰ khai, để sau thì chuỗi "thang" rơi vào `{tai_san_id}` và ăn 422 vì không ép được sang
int. Cùng bẫy đã dính ở `may_thiet_bi.py`.

Dependency provider khai INLINE để không đụng `deps.py` (file dùng chung).

Quyền: dùng lại action có sẵn — `read`/`create`/`update`/`delete`/`export`. Từ 08/09/2026 không
còn chốt/mở kỳ nên `close_book` không dùng tới nữa (cột quyền vẫn nằm đó, vô hại).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.department import Department
from ..models.tai_san import NGUON_DAU_KY, TT_DA_GIAM, TaiSan
from ..models.user import User
from ..repositories.tai_san_repo import TaiSanRepository
from ..schemas.tai_san import (
    BangThangOut,
    BienDongIn,
    BienDongOut,
    DongDuKienOut,
    KhauHaoDongOut,
    NhanVienChonOut,
    SuKienOut,
    TaiSanDetailOut,
    TaiSanIn,
    TaiSanListOut,
    TaiSanRow,
    TaiSanSuaIn,
)
from ..services.tai_san.bang_thang import bang_thang
from ..services.tai_san.excel import MEDIA_XLSX, xuat_bang_ky
from ..services.tai_san.service import (
    TaiSanDaCoChungTu,
    TaiSanNotFound,
    TaiSanService,
    TaiSanTrung,
    TaiSanValidationError,
    thang_da_tinh,
)

router = APIRouter(prefix="/api/tai-san", tags=["tai-san"])
MODULE = "tai_san"

_DOC = require_permission(MODULE, "read")
_TAO = require_permission(MODULE, "create")
_GHI = require_permission(MODULE, "update")
_XOA = require_permission(MODULE, "delete")
_XUAT = require_permission(MODULE, "export")


def get_service(db: Annotated[Session, Depends(get_db)]) -> TaiSanService:
    return TaiSanService(TaiSanRepository(db))


Service = Annotated[TaiSanService, Depends(get_service)]
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


def _dung_rows(db: Session, svc: TaiSanService, objs: list[TaiSan]) -> list[TaiSanRow]:
    """Hao mòn lũy kế tới hết tháng trước. Dòng CŨ còn mang `da_giam` (nghiệp vụ ghi giảm đã bỏ
    08/09/2026) thì lũy kế chốt ở tháng giảm và "còn lại" = 0 — nó đã ra khỏi sổ."""
    ten = _ten_bo_phan(db, {o.bo_phan_id for o in objs})
    nam, thang = thang_da_tinh()
    ra = []
    for o in objs:
        row = TaiSanRow.model_validate(o)
        row.bo_phan_ten = ten.get(o.bo_phan_id)
        if o.trang_thai == TT_DA_GIAM and o.ngay_giam is not None:
            row.hao_mon_luy_ke = svc.hao_mon_den(o, o.ngay_giam.year, o.ngay_giam.month)
            row.luy_ke_den = f"{o.ngay_giam.year:04d}-{o.ngay_giam.month:02d}"
            row.con_lai = 0
        else:
            row.hao_mon_luy_ke = svc.hao_mon_den(o, nam, thang)
            row.luy_ke_den = f"{nam:04d}-{thang:02d}"
            row.con_lai = int(o.nguyen_gia or 0) - row.hao_mon_luy_ke
        ra.append(row)
    return ra


def _bao_loi(exc: Exception) -> HTTPException:
    """Một chỗ đổi lỗi nghiệp vụ sang HTTP — mọi endpoint dùng chung, khỏi lệch mã."""
    if isinstance(exc, TaiSanNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (TaiSanTrung, TaiSanDaCoChungTu)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


LOI_NGHIEP_VU = (TaiSanNotFound, TaiSanTrung, TaiSanValidationError, TaiSanDaCoChungTu)

# =====================================================================================
# Route TĨNH — khai TRƯỚC mọi route `/{tai_san_id}` (xem cảnh báo ở docstring)
# =====================================================================================


def _bang(db: Session, nam: int, thang: int) -> BangThangOut:
    try:
        items = bang_thang(db, nam, thang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return BangThangOut(
        nam=nam, thang=thang,
        tong_muc_trich=sum(int(h["muc_trich"]) for h in items),
        items=items,
    )


@router.get("/thang/{nam}/{thang}", response_model=BangThangOut)
def bang_khau_hao_thang(
    nam: int, thang: int, db: Db, _: Annotated[User, Depends(_DOC)]
) -> BangThangOut:
    """Bảng khấu hao của một tháng — tính tại chỗ từ sổ, không cần tính/chốt."""
    return _bang(db, nam, thang)


@router.get("/thang/{nam}/{thang}/excel")
def excel_thang(nam: int, thang: int, db: Db, _: Annotated[User, Depends(_XUAT)]) -> Response:
    """Bảng khấu hao tháng ra .xlsx — kế toán đọc rồi tự gõ sang phần mềm kế toán bên ngoài."""
    noi_dung = xuat_bang_ky(_bang(db, nam, thang).model_dump()["items"], nam=nam, thang=thang)
    return Response(
        content=noi_dung,
        media_type=MEDIA_XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="khau-hao-{thang:02d}-{nam}.xlsx"'
        },
    )


@router.get("/nhan-vien", response_model=list[NhanVienChonOut])
def nhan_vien_bo_phan(
    svc: Service, _: Annotated[User, Depends(_DOC)], bo_phan_id: int = Query(...)
) -> list[NhanVienChonOut]:
    """Nhân viên đang làm của một bộ phận — nguồn ô "Người quản lý" trên phiếu.

    Đi qua quyền `tai_san.read` chứ không qua `nhan_su.read`: kế toán quản tài sản thường không
    có quyền xem hồ sơ nhân sự, mà ô này chỉ cần mã + tên.
    """
    return [NhanVienChonOut.model_validate(e) for e in svc.nhan_vien_bo_phan(bo_phan_id)]


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
    return TaiSanListOut(items=_dung_rows(db, svc, rows), total=tong)


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
    return _dung_rows(db, svc, [t])[0]


@router.get("/{tai_san_id}", response_model=TaiSanDetailOut)
def chi_tiet(
    tai_san_id: int, db: Db, svc: Service, _: Annotated[User, Depends(_DOC)]
) -> TaiSanDetailOut:
    t = svc.repo.lay_kem_chi_tiet(tai_san_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài sản #{tai_san_id}")
    row = _dung_rows(db, svc, [t])[0]
    return TaiSanDetailOut(
        **row.model_dump(),
        chi_phi=t.chi_phi,
        bien_dong=[BienDongOut.model_validate(b) for b in t.bien_dong],
        khau_hao=[KhauHaoDongOut(**d.__dict__) for d in svc.lich_da_tinh(t)],
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
    return _dung_rows(db, svc, [t])[0]


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
    """Lịch khấu hao trọn đời của tài sản — hiện ngay sau khi lưu phiếu ghi tăng, và trong ngăn
    xem chi tiết. Mỗi dòng kèm câu diễn giải khi tháng đó có chuyện."""
    t = svc.repo.lay_kem_chi_tiet(tai_san_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài sản #{tai_san_id}")
    theo_thang = svc.su_kien_theo_thang(t)
    ra = []
    for d in svc.lich(t):
        d = svc.dong_hien_thi(t, d)
        ra.append(DongDuKienOut(
            **d.__dict__,
            su_kien=[SuKienOut(**s.__dict__) for s in svc.su_kien_dong(d, theo_thang)],
            dien_giai=svc.dien_giai_dong(d, theo_thang),
        ))
    return ra


@router.post(
    "/{tai_san_id}/bien-dong", response_model=BienDongOut, status_code=status.HTTP_201_CREATED
)
def bien_dong(
    tai_san_id: int, payload: BienDongIn, svc: Service, user: Annotated[User, Depends(_GHI)]
) -> BienDongOut:
    """Một cửa cho hai chứng từ điều chuyển · nâng cấp — `loai` quyết định ô nào bắt buộc.
    (Ghi giảm đã bỏ 08/09/2026: món không dùng nữa thì xoá khỏi sổ.)"""
    try:
        if payload.loai == "dieu_chuyen":
            bd = svc.dieu_chuyen(
                tai_san_id, ngay=payload.ngay, bo_phan_moi_id=payload.bo_phan_moi_id or 0,
                nguoi_quan_ly_id=payload.nguoi_quan_ly_id, ly_do=payload.ly_do, user_id=user.id,
            )
        elif payload.loai == "nang_cap":
            bd = svc.nang_cap(
                tai_san_id, ngay=payload.ngay, so_tien=int(payload.so_tien or 0),
                so_thang_con_lai=int(payload.so_thang_con_lai or 0), ly_do=payload.ly_do,
                user_id=user.id,
            )
        else:
            raise TaiSanValidationError(f"Loại biến động không hợp lệ: {payload.loai}")
    except LOI_NGHIEP_VU as e:
        raise _bao_loi(e) from None
    return BienDongOut.model_validate(bd)
