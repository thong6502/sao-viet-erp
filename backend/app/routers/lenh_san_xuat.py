"""Kế hoạch & Lệnh sản xuất — API routes (Chunk 3), spec `docs/spec-ke-hoach-san-xuat.md`.

Router CHỈ ĐIỀU PHỐI: gọi `LenhSanXuatService` (nghiệp vụ + suy trạng thái) → map exception sang HTTP
→ đẩy sự kiện real-time (hub in-process, bám pattern báo giá/đơn). MÁY CHỈ GHI NHẬN.

RBAC: guard theo module `san_xuat` (đã có sẵn trong catalog quyền — "Sản xuất"). Action-level dùng
bit CRUD/đặc thù chung: read · create · update · approve (cổng duyệt mẫu + phát) · cancel (hủy) ·
manage_status (nhập kho đóng lệnh). Phân tách vai chi tiết (thợ/tổ trưởng/QC/kho) DEFER — xem
GIẢ ĐỊNH trong docs (chưa có vai công nhân riêng trong seed RBAC).

Real-time (SSE): đẩy tín hiệu NHẸ qua hub chung (client giữ 1 kết nối `/api/quotations/events`, lọc
theo `type`) cho các mốc: duyệt mẫu · phát · bàn giao · QC nêu lỗi. Payload kèm tổ nhận / tổ bị quy
để FE lọc đúng người. Đẩy per-tổ (resolve tổ→user) là refinement Chunk 8 (màn thợ).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_lenh_san_xuat_service, require_permission
from ..models.user import User
from ..realtime import hub
from ..schemas.lenh_san_xuat import (
    BanGiaoIn,
    BanGiaoOut,
    BungIn,
    GanMayIn,
    GhepIn,
    GhiLoiQcIn,
    GhiSanLuongIn,
    LenhDetailOut,
    LenhListOut,
    LenhOut,
    NhapKhoIn,
    NhapKhoOut,
    PlacementAddIn,
    PlacementUpdateIn,
    PrintFormDetailOut,
    PrintFormListOut,
    PrintFormOut,
    QcDefectOut,
    SanLuongOut,
)
from ..services.lenh_san_xuat_service import (
    LenhSanXuatService,
    LenhSXConflict,
    LenhSXNotFound,
    LenhSXValidationError,
)


router = APIRouter(prefix="/api/lenh-sx", tags=["lenh_san_xuat"])
MODULE = "san_xuat"

Service = Annotated[LenhSanXuatService, Depends(get_lenh_san_xuat_service)]


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, LenhSXNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LenhSXValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, LenhSXConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ================================================================ LỆNH (đọc + bung + hủy)
@router.get("/lenh", response_model=LenhListOut)
def list_lenh(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    order_id: int | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> LenhListOut:
    rows, total = svc.list_lenh(order_id=order_id, trang_thai=trang_thai, page=page, size=size)
    return LenhListOut(items=rows, total=total, page=page, size=size)


@router.get("/lenh/{lenh_id}", response_model=LenhDetailOut)
def get_lenh(
    lenh_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> LenhDetailOut:
    try:
        d = svc.lenh_detail(lenh_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return LenhDetailOut(
        **LenhOut.model_validate(d["lenh"]).model_dump(),
        forms=d["forms"], san_luong=d["san_luong"], ban_giao=d["ban_giao"], qc=d["qc"],
        muc_tieu_sl=d["muc_tieu_sl"], tong_dat=d["tong_dat"],
    )


@router.post("/lenh/bung", response_model=list[LenhOut], status_code=status.HTTP_201_CREATED)
def bung_lenh(
    payload: BungIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> list[LenhOut]:
    """Đơn chốt → tự đề lệnh nháp (idempotent theo đơn·ấn phẩm). Trả các lệnh MỚI tạo (gọi lại = [])."""
    try:
        return svc.bung_lenh(order_id=payload.order_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/lenh/{lenh_id}/huy", response_model=LenhOut)
def huy_lenh(
    lenh_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "cancel"))],
) -> LenhOut:
    try:
        return svc.huy_lenh(lenh_id=lenh_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/lenh/{lenh_id}/duyet-mau", response_model=LenhOut)
def duyet_mau(
    lenh_id: int,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> LenhOut:
    """Duyệt mẫu 1 lệnh (con dấu + snapshot đóng băng). Đẩy real-time: 1 vế cổng phát (AND) đã đủ."""
    try:
        lenh = svc.duyet_mau(lenh_id=lenh_id, actor_id=user.id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    hub.broadcast({"type": "lenh_sx_duyet_mau", "lenh_id": lenh_id})
    return lenh


# ================================================================ TỜ IN (ghép · gán máy · phát)
@router.get("/forms", response_model=PrintFormListOut)
def list_forms(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    trang_thai: str | None = Query(default=None),
    may_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> PrintFormListOut:
    rows, total = svc.list_forms(trang_thai=trang_thai, may_id=may_id, page=page, size=size)
    return PrintFormListOut(items=rows, total=total, page=page, size=size)


@router.get("/forms/{form_id}", response_model=PrintFormDetailOut)
def get_form(
    form_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PrintFormDetailOut:
    try:
        d = svc.form_detail(form_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return PrintFormDetailOut(
        **PrintFormOut.model_validate(d["form"]).model_dump(),
        placements=d["placements"], lenhs=d["lenhs"],
    )


@router.post("/forms/ghep", response_model=PrintFormDetailOut, status_code=status.HTTP_201_CREATED)
def ghep(
    payload: GhepIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PrintFormDetailOut:
    """Tạo 1 tờ in + xếp bài (số con nhập tay). Máy CHỈ GHI — không lọc/chặn 'cùng loại'."""
    try:
        form = svc.ghep(
            giay_id=payload.giay_id, giay_label=payload.giay_label,
            kho_in_dai=payload.kho_in_dai, kho_in_rong=payload.kho_in_rong,
            so_mau=payload.so_mau, may_id=payload.may_id,
            so_to_chay=payload.so_to_chay, so_kem=payload.so_kem,
            placements=[p.model_dump() for p in payload.placements],
        )
        d = svc.form_detail(form.id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return PrintFormDetailOut(
        **PrintFormOut.model_validate(d["form"]).model_dump(),
        placements=d["placements"], lenhs=d["lenhs"],
    )


@router.post("/forms/{form_id}/gan-may", response_model=PrintFormOut)
def gan_may(
    form_id: int,
    payload: GanMayIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PrintFormOut:
    try:
        return svc.gan_may(form_id=form_id, may_id=payload.may_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/forms/{form_id}/phat", response_model=PrintFormOut)
def phat(
    form_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PrintFormOut:
    """Phát tờ in xuống xưởng — CỔNG AND (đã gán máy + mọi lệnh duyệt mẫu). Đẩy real-time: tổ có việc."""
    try:
        lenh_ids = [l.id for l in svc.lenh_on_form(form_id)]
        form = svc.phat(form_id=form_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    hub.broadcast({"type": "lenh_sx_phat", "form_id": form_id, "lenh_ids": lenh_ids})
    return form


# --- xếp bài (placement) add / sửa / xoá ------------------------------------------
@router.post("/forms/{form_id}/placements", response_model=PrintFormDetailOut, status_code=status.HTTP_201_CREATED)
def them_placement(
    form_id: int,
    payload: PlacementAddIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PrintFormDetailOut:
    try:
        svc.them_placement(form_id=form_id, lenh_sx_id=payload.lenh_sx_id, so_con=payload.so_con)
        d = svc.form_detail(form_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return PrintFormDetailOut(
        **PrintFormOut.model_validate(d["form"]).model_dump(),
        placements=d["placements"], lenhs=d["lenhs"],
    )


@router.put("/placements/{placement_id}", response_model=PrintFormDetailOut)
def sua_placement(
    placement_id: int,
    payload: PlacementUpdateIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PrintFormDetailOut:
    try:
        form = svc.sua_placement(placement_id=placement_id, so_con=payload.so_con)
        d = svc.form_detail(form.id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return PrintFormDetailOut(
        **PrintFormOut.model_validate(d["form"]).model_dump(),
        placements=d["placements"], lenhs=d["lenhs"],
    )


@router.delete("/placements/{placement_id}", response_model=PrintFormDetailOut)
def xoa_placement(
    placement_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PrintFormDetailOut:
    try:
        form = svc.xoa_placement(placement_id=placement_id)
        d = svc.form_detail(form.id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return PrintFormDetailOut(
        **PrintFormOut.model_validate(d["form"]).model_dump(),
        placements=d["placements"], lenhs=d["lenhs"],
    )


# ================================================================ TỔ CHẠY (sản lượng · bàn giao · QC)
@router.post("/lenh/{lenh_id}/san-luong", response_model=SanLuongOut, status_code=status.HTTP_201_CREATED)
def ghi_san_luong(
    lenh_id: int,
    payload: GhiSanLuongIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> SanLuongOut:
    """Tổ trưởng ghi sản lượng (số đạt + hỏng). Cổng cứng: chỉ ghi khi lệnh đã PHÁT (đang chạy)."""
    try:
        return svc.ghi_san_luong(
            lenh_id=lenh_id, cong_doan_id=payload.cong_doan_id, to_id=payload.to_id,
            so_dat=payload.so_dat, so_hong=payload.so_hong, nguoi_ghi=user.id,
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.get("/lenh/{lenh_id}/san-luong", response_model=list[SanLuongOut])
def list_san_luong(
    lenh_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[SanLuongOut]:
    try:
        return svc.san_luong_of(lenh_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/lenh/{lenh_id}/ban-giao", response_model=BanGiaoOut, status_code=status.HTTP_201_CREATED)
def ban_giao(
    lenh_id: int,
    payload: BanGiaoIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> BanGiaoOut:
    """Tổ trưởng GIAO số đạt sang tổ kế. Đẩy real-time: tổ nhận cần XÁC NHẬN."""
    try:
        bg = svc.ban_giao(
            lenh_id=lenh_id, cong_doan_tu_id=payload.cong_doan_tu_id,
            cong_doan_toi_id=payload.cong_doan_toi_id, so_giao=payload.so_giao,
            to_giao_id=payload.to_giao_id, to_nhan_id=payload.to_nhan_id,
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    hub.broadcast({
        "type": "lenh_sx_ban_giao", "lenh_id": lenh_id,
        "ban_giao_id": bg.id, "to_nhan_id": payload.to_nhan_id,
    })
    return bg


@router.post("/ban-giao/{ban_giao_id}/xac-nhan-nhan", response_model=BanGiaoOut)
def xac_nhan_nhan(
    ban_giao_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> BanGiaoOut:
    try:
        return svc.xac_nhan_nhan(ban_giao_id=ban_giao_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/lenh/{lenh_id}/qc", response_model=QcDefectOut, status_code=status.HTTP_201_CREATED)
def ghi_loi_qc(
    lenh_id: int,
    payload: GhiLoiQcIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> QcDefectOut:
    """QC/KCS nêu lỗi → CHỜ tổ trưởng xác nhận. Đẩy real-time: tổ bị quy cần xác nhận NGAY."""
    try:
        qc = svc.ghi_loi_qc(
            lenh_id=lenh_id, cong_doan_id=payload.cong_doan_id,
            to_bi_quy_id=payload.to_bi_quy_id, anh_url=payload.anh_url, mo_ta=payload.mo_ta,
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    hub.broadcast({
        "type": "lenh_sx_qc_loi", "lenh_id": lenh_id,
        "qc_id": qc.id, "to_bi_quy_id": payload.to_bi_quy_id,
    })
    return qc


@router.post("/qc/{qc_id}/to-truong-xac-nhan", response_model=QcDefectOut)
def to_truong_xac_nhan_qc(
    qc_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> QcDefectOut:
    try:
        return svc.to_truong_xac_nhan_qc(qc_id=qc_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


# ================================================================ KẾT THÚC (nhập kho → đóng lệnh)
@router.post("/lenh/{lenh_id}/nhap-kho", response_model=NhapKhoOut)
def nhap_kho(
    lenh_id: int,
    payload: NhapKhoIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "manage_status"))],
) -> NhapKhoOut:
    """Ghi nhận nhập kho thành phẩm → suy lệnh XONG (đủ SL) → suy đơn xong sản xuất."""
    try:
        res = svc.nhap_kho_thanh_pham(lenh_id=lenh_id, so_luong_nhap=payload.so_luong_nhap)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return NhapKhoOut(
        lenh=LenhOut.model_validate(res["lenh"]),
        muc_tieu_sl=res["muc_tieu_sl"], so_luong_nhap=res["so_luong_nhap"],
        lenh_xong=res["lenh_xong"], order_production_done=res["order_production_done"],
    )
