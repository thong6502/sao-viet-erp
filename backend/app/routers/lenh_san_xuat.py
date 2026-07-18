"""Kế hoạch & Lệnh sản xuất — API routes (Chunk 3), spec `docs/spec-ke-hoach-san-xuat.md`.

Router CHỈ ĐIỀU PHỐI: gọi `LenhSanXuatService` (nghiệp vụ + suy trạng thái) → map exception sang HTTP
→ đẩy sự kiện real-time (hub in-process, bám pattern báo giá/đơn). MÁY CHỈ GHI NHẬN.

RBAC: guard theo module `san_xuat` (đã có sẵn trong catalog quyền — "Sản xuất"). Action-level dùng
bit CRUD/đặc thù chung: read · create · update · approve (cổng duyệt mẫu + phát) · cancel (hủy).

Real-time (SSE): đẩy tín hiệu NHẸ qua hub chung (client giữ 1 kết nối `/api/quotations/events`, lọc
theo `type`) cho các mốc kế hoạch: duyệt mẫu · phát.

(Module theo dõi thực thi xưởng — sản lượng/bàn giao/QC/nhập kho + màn tổ — đã GỠ.)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_lenh_san_xuat_service, require_permission
from ..models.user import User
from ..realtime import hub
from ..schemas.lenh_san_xuat import (
    AnPhamChiTietOut,
    BungIn,
    GanMayIn,
    GhepIn,
    HangChoOut,
    LenhDetailOut,
    LenhListOut,
    LenhOut,
    PlacementAddIn,
    PlacementUpdateIn,
    PrintFormDetailOut,
    PrintFormListOut,
    PrintFormOut,
    QuyCachOverrideIn,
    RoutingReorderIn,
    RoutingStepIn,
    RoutingStepOut,
    TaoLenhIn,
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


@router.get("/hang-cho", response_model=list[HangChoOut])
def hang_cho(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[HangChoOut]:
    """Đơn đã chốt CHỜ lên kế hoạch (handoff §5.1) — kế hoạch bấm 'Lên kế hoạch' (bung) từ đây."""
    return [HangChoOut(**r) for r in svc.hang_cho()]


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
        items=d["items"], routing=d["routing"],
        forms=d["forms"], muc_tieu_sl=d["muc_tieu_sl"],
    )


@router.get("/an-pham/{ptp_id}", response_model=AnPhamChiTietOut)
def an_pham_chi_tiet(
    ptp_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    lenh_item_id: int | None = Query(default=None),
) -> AnPhamChiTietOut:
    """Chi tiết ấn phẩm cho DRAWER — CÔ LẬP THƯƠNG MẠI (lọc giá). Kèm `lenh_item_id` (mở từ lệnh) →
    giá trị HIỆU LỰC = báo giá + override + cờ `editable` (lệnh nháp); không kèm → thuần báo giá."""
    try:
        return AnPhamChiTietOut(**svc.an_pham_chi_tiet(ptp_id, lenh_item_id=lenh_item_id))
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.put("/bai-con/{item_id}/quy-cach", response_model=AnPhamChiTietOut)
def sua_quy_cach_bai_con(
    item_id: int,
    payload: QuyCachOverrideIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> AnPhamChiTietOut:
    """Kế hoạch SỬA quy cách in của 1 bài con (override báo giá) — CHỈ khi lệnh còn NHÁP. Máy CHỈ GHI."""
    try:
        return AnPhamChiTietOut(
            **svc.sua_quy_cach_bai_con(item_id=item_id, override=payload.model_dump(exclude_unset=True))
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


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


@router.post("/lenh", response_model=LenhOut, status_code=status.HTTP_201_CREATED)
def tao_lenh(
    payload: TaoLenhIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> LenhOut:
    """Người kế hoạch PICK gom nhóm ấn phẩm (cùng 1 đơn) → 1 LỆNH nháp + bài con. Máy CHỈ GHI."""
    try:
        return svc.tao_lenh(
            order_id=payload.order_id, phieu_thanh_phan_ids=payload.phieu_thanh_phan_ids,
        )
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


# ================================================================ ROUTING (kế hoạch §13.2)
@router.get("/lenh/{lenh_id}/routing", response_model=list[RoutingStepOut])
def get_routing(
    lenh_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[RoutingStepOut]:
    try:
        return svc.get_routing(lenh_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/lenh/{lenh_id}/routing", response_model=list[RoutingStepOut], status_code=status.HTTP_201_CREATED)
def them_buoc_routing(
    lenh_id: int,
    payload: RoutingStepIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> list[RoutingStepOut]:
    """Kế hoạch thêm 1 bước vào cuối routing (tổ mặc định = tổ của công đoạn, đổi được)."""
    try:
        svc.them_buoc_routing(lenh_id=lenh_id, cong_doan_id=payload.cong_doan_id, to_id=payload.to_id)
        return svc.get_routing(lenh_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.put("/routing/{step_id}", response_model=list[RoutingStepOut])
def sua_buoc_routing(
    step_id: int,
    payload: RoutingStepIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> list[RoutingStepOut]:
    """Đổi công đoạn / tổ 1 bước — CHỈ khi bước còn chờ (chưa chạy)."""
    try:
        step = svc.sua_buoc_routing(step_id=step_id, cong_doan_id=payload.cong_doan_id, to_id=payload.to_id)
        return svc.get_routing(step.lenh_sx_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.delete("/routing/{step_id}", response_model=list[RoutingStepOut])
def xoa_buoc_routing(
    step_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> list[RoutingStepOut]:
    """Xóa 1 bước routing — CHỈ khi bước còn chờ (chưa chạy)."""
    try:
        lenh_id = svc.xoa_buoc_routing(step_id=step_id)
        return svc.get_routing(lenh_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/lenh/{lenh_id}/routing/reorder", response_model=list[RoutingStepOut])
def reorder_routing(
    lenh_id: int,
    payload: RoutingReorderIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> list[RoutingStepOut]:
    """Đổi thứ tự routing — CHỈ khi lệnh còn nháp (trước khi phát)."""
    try:
        return svc.doi_thu_tu_routing(lenh_id=lenh_id, step_ids=payload.step_ids)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


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
