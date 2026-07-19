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

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import (
    get_authorization_service,
    get_current_user,
    get_lenh_san_xuat_service,
    require_permission,
)
from ..models.user import User
from ..realtime import hub
from ..schemas.cong_doan import RefOption, RefOptionListOut
from ..schemas.lenh_san_xuat import (
    AnPhamChiTietOut,
    AssignWorkersIn,
    BungIn,
    GanMayIn,
    GhepIn,
    HanGiaoIn,
    HangChoOut,
    KhuonGanIn,
    LenhDetailOut,
    LenhListOut,
    LenhOut,
    BanGiaoIn,
    LichChayReorderIn,
    LichChayRow,
    MayCaIn,
    NhanIn,
    SanLuongIn,
    XepLichIn,
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
from ..services.rbac_service import AuthorizationService


router = APIRouter(prefix="/api/lenh-sx", tags=["lenh_san_xuat"])
MODULE = "san_xuat"

Service = Annotated[LenhSanXuatService, Depends(get_lenh_san_xuat_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _scope_for(authz: AuthorizationService, user: User) -> str:
    """Scope của user trên module SX (own/department/all) — lọc navbar + hộp việc tổ."""
    return authz.scope_for(user, MODULE) or "own"


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


@router.get("/to", response_model=RefOptionListOut)
def list_to_san_xuat(
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    authz: Authz,
) -> RefOptionListOut:
    """Tổ khối SẢN XUẤT cho MENU CON ĐỘNG dưới 'Sản xuất', LỌC theo scope user (Lát 1 §15): own=tổ
    mình · department=cây con · all=hết. Thợ/tổ trưởng chỉ thấy tổ mình; quản đốc/giám đốc rộng hơn.
    KHÔNG fallback — chưa tick `la_san_xuat` → rỗng (navbar không phun mọi phòng ban)."""
    tos = svc.to_list_scoped(actor=user, scope=_scope_for(authz, user))
    return RefOptionListOut(items=[RefOption(id=d.id, ma=d.code, ten=d.name) for d in tos])


# ================================================================ HỘP VIỆC TỔ (Lát 1)
@router.get("/to-badges")
def to_badges(
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    authz: Authz,
) -> dict:
    """Badge mỗi tổ SX (đếm việc đang chờ ở tổ) — FE map sang nav id `to-sx:<id>`; tự lành khi reconnect."""
    items = svc.to_badges(
        actor=user, scope=_scope_for(authz, user),
        can_assign_work=authz.can(user, MODULE, "assign_work"),
    )
    return {"items": items}


@router.get("/to/{to_id}/inbox")
def to_inbox(
    to_id: int,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    authz: Authz,
) -> dict:
    """Hộp việc 1 tổ (2 tầng): tổ trưởng/giám sát thấy FULL lệnh của tổ + gán được; thợ CHỈ thấy
    lệnh mình được gán. Mỗi lệnh kèm routing (traveler) + assignees; bước thuộc tổ này `is_mine`."""
    try:
        return svc.to_inbox(
            actor=user, scope=_scope_for(authz, user), to_id=to_id,
            can_assign_work=authz.can(user, MODULE, "assign_work"),
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.get("/to/{to_id}/members")
def to_members(
    to_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Thợ (có tài khoản) thuộc 1 tổ — để tổ trưởng gán vào công đoạn."""
    return {"items": svc.to_members(to_id=to_id)}


@router.get("/finishing-mays")
def finishing_mays(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """1.12 — máy finishing (bế/cán/bồi) cho tổ xếp máy bước. Lọc non-press server-side, gác
    `san_xuat:read` (tổ trưởng KHÔNG cần quyền danh mục máy `dm_thiet_bi`)."""
    return {"items": svc.finishing_mays()}


@router.post("/routing/{step_id}/assign")
def gan_tho(
    step_id: int,
    payload: AssignWorkersIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Tổ trưởng gán 1..n thợ vào 1 bước routing (lệnh đang chạy). Đẩy realtime ĐÍCH DANH tới từng thợ."""
    try:
        assigned: list[tuple[int, int, int | None]] = []
        for uid in payload.user_ids:
            lenh_id, to_id = svc.assign_worker(step_id=step_id, user_id=uid, actor_id=user.id)
            assigned.append((uid, lenh_id, to_id))
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    for uid, lenh_id, to_id in assigned:
        hub.publish(uid, {"type": "lenh_sx_assigned", "lenh_id": lenh_id, "to_id": to_id})
    return {"ok": True, "count": len(assigned)}


@router.delete("/routing/{step_id}/assign/{user_id}")
def bo_gan_tho(
    step_id: int,
    user_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Bỏ gán 1 thợ khỏi 1 bước routing."""
    try:
        svc.unassign_worker(step_id=step_id, user_id=user_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return {"ok": True}


@router.put("/routing/{step_id}/may-ca")
def xep_may_ca(
    step_id: int,
    payload: MayCaIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """1.12 — tổ xếp MÁY finishing + CA cho 1 bước (record-only, máy CHỈ GHI NHẬN). Gate như gán thợ
    (`assign_work`); chỉ khi lệnh đang chạy. Không đẩy realtime (chi tiết cấu hình, thợ thấy khi refetch)."""
    try:
        svc.set_step_may_ca(step_id=step_id, may_id=payload.may_id, ca=payload.ca)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return {"ok": True}


# ================================================================ Lát 2 — Sản lượng · Bàn giao
@router.post("/routing/{step_id}/san-luong")
def ghi_san_luong(
    step_id: int,
    payload: SanLuongIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "record_output"))],
) -> dict:
    """Tổ trưởng ghi 1 đợt sản lượng đạt/hỏng cho bước (record-only, cộng dồn). Gate `record_output`."""
    try:
        svc.ghi_san_luong(
            step_id=step_id, so_dat=payload.so_dat, so_hong=payload.so_hong,
            don_vi=payload.don_vi, ghi_chu=payload.ghi_chu, actor_id=user.id,
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return {"ok": True}


@router.post("/routing/{step_id}/ban-giao")
def ban_giao(
    step_id: int,
    payload: BanGiaoIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "handover"))],
) -> dict:
    """Tổ giao số sang bước KẾ. Ting ĐÍCH DANH tổ nhận (slot `lenh_sx_ban_giao`). Gate `handover`."""
    try:
        lenh_id, ban_giao_id, to_nhan_id = svc.ban_giao(
            step_id=step_id, so_giao=payload.so_giao, don_vi=payload.don_vi, actor_id=user.id,
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    hub.broadcast({"type": "lenh_sx_ban_giao", "lenh_id": lenh_id,
                   "ban_giao_id": ban_giao_id, "to_nhan_id": to_nhan_id})
    return {"ok": True, "ban_giao_id": ban_giao_id}


@router.post("/ban-giao/{ban_giao_id}/nhan")
def xac_nhan_nhan(
    ban_giao_id: int,
    payload: NhanIn,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "handover"))],
) -> dict:
    """Tổ nhận XÁC NHẬN số nhận (con dấu 2 — lệch được). Gate `handover`."""
    try:
        svc.xac_nhan_nhan(
            ban_giao_id=ban_giao_id, so_nhan=payload.so_nhan,
            ly_do_lech=payload.ly_do_lech, actor_id=user.id,
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    return {"ok": True}


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
        ghi_chu_ky_thuat=d["ghi_chu_ky_thuat"],
        can_khuon=d["can_khuon"], khuon_be_label=d["khuon_be_label"],
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


@router.put("/lenh/{lenh_id}/han-giao", response_model=LenhOut)
def sua_han_giao(
    lenh_id: int,
    payload: HanGiaoIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LenhOut:
    """① Kế hoạch sửa hạn giao (khách/nội bộ) — CHỈ khi lệnh còn NHÁP; sau phát 409. Máy CHỈ GHI."""
    sent = payload.model_dump(exclude_unset=True)
    try:
        return svc.sua_han_giao(
            lenh_id=lenh_id,
            han_giao_khach=payload.han_giao_khach, set_khach=("han_giao_khach" in sent),
            han_giao_noi_bo=payload.han_giao_noi_bo, set_noi_bo=("han_giao_noi_bo" in sent),
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.put("/lenh/{lenh_id}/khuon", response_model=LenhOut)
def gan_khuon(
    lenh_id: int,
    payload: KhuonGanIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LenhOut:
    """③ Điều độ gán khuôn bế cho lệnh (record-only — cảnh báo mềm ở FE, KHÔNG chặn phát). null = gỡ."""
    try:
        return svc.gan_khuon(lenh_id=lenh_id, khuon_be_id=payload.khuon_be_id)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


# ================================================================ ④ LỊCH CHẠY (Máy × Ngày)
@router.get("/lich-chay", response_model=list[LichChayRow])
def lich_chay(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> list[LichChayRow]:
    """④ Các lệnh nháp + đang chạy để dựng bảng Máy×Ngày (FE tự lọc vào ô ngày; lệnh chưa xếp → khay)."""
    return [LichChayRow(**r) for r in svc.lich_chay(from_date=from_date, to_date=to_date)]


@router.put("/lenh/{lenh_id}/lich-chay", response_model=LenhOut)
def xep_lich(
    lenh_id: int,
    payload: XepLichIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> LenhOut:
    """④ Kéo lệnh vào ô (máy, ngày) hoặc gỡ khỏi lưới — field nào gửi thì set (cho null). Máy chỉ ghi nhận."""
    sent = payload.model_dump(exclude_unset=True)
    try:
        return svc.xep_lich(
            lenh_id=lenh_id,
            may_id=payload.may_id, set_may=("may_id" in sent),
            ngay_chay=payload.ngay_chay, set_ngay=("ngay_chay" in sent),
            thu_tu_chay=payload.thu_tu_chay, set_thu_tu=("thu_tu_chay" in sent),
            thoi_luong_phut=payload.thoi_luong_phut, set_thoi_luong=("thoi_luong_phut" in sent),
        )
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None


@router.post("/lich-chay/reorder", response_model=list[LenhOut])
def reorder_lich_chay(
    payload: LichChayReorderIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> list[LenhOut]:
    """④ Đổi thứ tự chạy trong 1 ô (máy×ngày) — mảng id theo thứ tự mới → set `thu_tu_chay`."""
    try:
        return svc.doi_thu_tu_chay(lenh_ids=payload.lenh_ids)
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
    """Phát tờ in xuống xưởng — CỔNG AND (đã gán máy + mọi lệnh duyệt mẫu). Đẩy real-time tới các tổ
    CÓ CÔNG ĐOẠN TRONG ROUTING (badge hộp tổ nhảy + toast); tín hiệu nhẹ, FE reload summary đã lọc scope."""
    try:
        lenh_ids = [l.id for l in svc.lenh_on_form(form_id)]
        form = svc.phat(form_id=form_id)
        to_ids = svc.to_ids_of_lenhs(lenh_ids)
    except (LenhSXNotFound, LenhSXValidationError, LenhSXConflict) as exc:
        raise _map(exc) from None
    hub.broadcast({"type": "lenh_sx_routing", "form_id": form_id, "lenh_ids": lenh_ids, "to_ids": to_ids})
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
