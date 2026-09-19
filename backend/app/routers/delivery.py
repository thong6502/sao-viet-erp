"""Router — Giao hàng (docs/prd-giao-hang.md).

Router chỉ điều phối: gác quyền, dịch lỗi nghiệp vụ sang HTTP, ánh xạ ORM → schema. Mọi luật
nằm ở `services/delivery_service.py`.

Bản đồ ô quyền (PRD §14) — MỘT Ô = MỘT TAB:

    can_read          mở màn + tab "Kế hoạch giao hàng" (lọc theo phạm vi)
    can_create        GHI: tạo yêu cầu · bấm đã lấy hàng · nhập kết quả + km
    can_plan          tab "Yêu cầu chờ lên kế hoạch" + nút phân công tài xế
    can_view_drivers  tab "Nhân viên giao hàng" (lịch + KPI của NGƯỜI KHÁC)
    can_cancel        huỷ yêu cầu / huỷ kế hoạch

Kho KHÔNG cần ô `giao_hang`: ba nút của kho gác bằng ô `kho` sẵn có, vì đề nghị xuất hàng sống
trong Hộp yêu cầu mà kho vẫn mở hằng ngày. Bắt kho được cấp thêm một ô nữa mới làm được việc là
đẻ thêm một chỗ để quên cấp.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import (APIRouter, Depends, File, HTTPException, Query, Request, Response,
                     UploadFile, status)
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_authorization_service, require_any_permission, require_permission
from ..models.delivery import LAN_GIAO_DANG_CHAY
from ..realtime import hub
from ..models.role import SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from ..repositories.customer_repo import CustomerRepository
from ..repositories.delivery_repo import DeliveryRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.order_repo import OrderRepository
from ..repositories.xe_repo import MucKhoanKmRepository, XeRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.user_repo import UserRepository
from ..schemas.delivery import (
    DinhKemListOut,
    DinhKemOut,
    KmBracketOut,
    KhoanKmPctIn,
    KhoanKmPctOut,
    MucKmBracketsIn,
    MucKmIn,
    MucKmListOut,
    MucKmOut,
    MucKmSua,
    ConPhaiGiaoLine,
    ConPhaiGiaoOut,
    DeliveryRequestCreate,
    DeliveryRequestLineOut,
    DeliveryRequestOut,
    DeliveryRequestPage,
    DeliveryRequestUpdate,
    DriverOut,
    DriverPage,
    HistoryOut,
    KetQuaIn,
    LyDoIn,
    PlanIn,
    PlanOut,
    PlanUpdate,
    RequestDetailOut,
    TaiXeChonOut,
    HangCanXuatOut,
    YeuCauKhoOut,
    YeuCauXuatKhoIn,
    TaiXeChonPage,
    TripLineOut,
    TripOut,
    TripPage,
    BangGiaoItem,
    BangGiaoPage,
    BatDauGiaoIn,
    CaLuotOut,
    GuiXuatKhoCaLuotIn,
    LenLuotIn,
    LenLuotOut,
    LuotXeChiTietOut,
    LuotXeMoOut,
    LuotXeMoPage,
    LuotXeTrongChuyenOut,
    VeKhoIn,
    VeKhoOut,
)
from ..services.delivery_service import (
    DeliveryError,
    DeliveryForbidden,
    DeliveryNotFound,
    DeliveryService,
)
from ..services.rbac_service import AuthorizationService
from ..services.thanh_pham_khai_bao import cum_ban

def _bao_giao_hang_doi(request: Request):
    """Mọi thao tác GHI thành công ở màn Giao hàng ⇒ đẩy một tín hiệu im lặng: drawer Đơn hàng bán
    đang mở tự đọc lại tiến độ (real-time, không toast — chủ chốt 19/09/2026 bỏ chuông báo Sales)."""
    yield
    if request.method != "GET":
        hub.broadcast({"type": "giao_hang_changed"})


router = APIRouter(prefix="/api/giao-hang", tags=["giao-hang"],
                   dependencies=[Depends(_bao_giao_hang_doi)])
MODULE = "giao_hang"
MODULE_KHO = "kho"


def _stock_request_service(db: Session):
    """Service YÊU CẦU KHO của chính họ — dựng đúng như `routers/kho_request.py` đang dựng.

    Giao hàng KHÔNG tự đẻ chứng từ; nó gọi đúng cửa mà mọi bộ phận khác gọi. Nhờ vậy luật kho
    (mặt hàng có thật, đơn vị đổi được, tạo là duyệt luôn) áp cho giao hàng miễn phí.
    """
    from ..repositories.don_vi_do_repo import DonViDoRepository
    from ..repositories.document_sequence_repo import DocumentSequenceRepository
    from ..repositories.stock_lot_repo import StockLotRepository, StockThresholdRepository
    from ..repositories.stock_request_repo import StockRequestRepository
    from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from ..services.sequence_service import SequenceService
    from ..services.stock_request_service import StockRequestService
    from ..services.vat_lieu_kho_service import VatLieuKhoService

    return StockRequestService(
        StockRequestRepository(db),
        StockLotRepository(db),
        StockThresholdRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
    )


def _stock_voucher_service(db: Session):
    """Service PHIẾU kho — chỉ dùng cho đường TRẢ HÀNG VỀ khi chuyến hỏng / giao thiếu.

    Dựng đúng như `routers/kho_voucher.py`, KHÔNG kèm `giu_cho`: đường trả hàng chỉ lập phiếu
    NHẬP, mà giữ chỗ chỉ gác chiều XUẤT.
    """
    from ..repositories.don_vi_do_repo import DonViDoRepository
    from ..repositories.document_sequence_repo import DocumentSequenceRepository
    from ..repositories.stock_lot_repo import StockLotRepository, StockThresholdRepository
    from ..repositories.stock_request_repo import StockRequestRepository
    from ..repositories.stock_voucher_repo import StockVoucherRepository
    from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from ..services.sequence_service import SequenceService
    from ..services.stock_request_service import StockRequestService
    from ..services.stock_voucher_service import StockVoucherService
    from ..services.vat_lieu_kho_service import VatLieuKhoService

    sequence = SequenceService(DocumentSequenceRepository(db))
    requests = StockRequestRepository(db)
    lots = StockLotRepository(db)
    hang = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    return StockVoucherService(
        StockVoucherRepository(db), requests, lots, sequence,
        StockRequestService(requests, lots, StockThresholdRepository(db), sequence, hang=hang),
        hang,
    )


def get_service(db: Annotated[Session, Depends(get_db)]) -> DeliveryService:
    return DeliveryService(
        DeliveryRepository(db),
        OrderRepository(db),
        EmployeeRepository(db),
        UserRepository(db),
        DepartmentRepository(db),
        stock_requests=_stock_request_service(db),
        stock_vouchers=_stock_voucher_service(db),
        xe=XeRepository(db),
        muc_km=MucKhoanKmRepository(db),
    )


Service = Annotated[DeliveryService, Depends(get_service)]
Db = Annotated[Session, Depends(get_db)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]

Reader = Annotated[User, Depends(require_permission(MODULE, "read"))]
Writer = Annotated[User, Depends(require_permission(MODULE, "create"))]
Planner = Annotated[User, Depends(require_permission(MODULE, "plan"))]
DriverViewer = Annotated[User, Depends(require_permission(MODULE, "view_drivers"))]
Canceller = Annotated[User, Depends(require_permission(MODULE, "cancel"))]
KhoUser = Annotated[User, Depends(require_permission(MODULE_KHO, "read"))]


def _err(e: DeliveryError) -> HTTPException:
    if isinstance(e, DeliveryNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, DeliveryForbidden):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _scope(authz: AuthorizationService, user: User) -> str:
    """Phạm vi lọc DÒNG. Thiếu dòng quyền ⇒ siết về `own`, không mở toang."""
    return authz.scope_for(user, MODULE) or SCOPE_OWN


# =================================================================================
# Ánh xạ ORM → schema
# =================================================================================
def _ten_nguoi(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = UserRepository(db).get_by_id(user_id)
    return getattr(u, "name", None) if u is not None else None


def _ten_mat_hang(db: Session, cap: set[tuple[str, int]]) -> dict[tuple[str, int], str]:
    """`{(hang_loai, hang_id): tên}` cho CẢ TRANG trong 2 truy vấn — tra từng dòng là N+1."""
    from sqlalchemy import select as _select

    from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn

    ra: dict[tuple[str, int], str] = {}
    giay = {i for (l, i) in cap if l == "giay"}
    vat_tu = {i for (l, i) in cap if l == "vat_tu"}
    if giay:
        for r in db.execute(_select(GiayNguyen.id, GiayNguyen.ten)
                            .where(GiayNguyen.id.in_(giay))).all():
            ra[("giay", int(r[0]))] = r[1]
    if vat_tu:
        for r in db.execute(_select(VatTuInAn.id, VatTuInAn.ten)
                            .where(VatTuInAn.id.in_(vat_tu))).all():
            ra[("vat_tu", int(r[0]))] = r[1]
    return ra


def _dong_don(db: Session, order_id: int) -> dict[int, tuple[str, str]]:
    order = OrderRepository(db).get_by_id(order_id)
    if order is None:
        return {}
    return {ln.id: (ln.description or "", ln.don_vi_tinh or "") for ln in order.lines}


def _request_out(db: Session, svc: DeliveryService, req) -> DeliveryRequestOut:
    order = OrderRepository(db).get_by_id(req.order_id)
    mo_ta = _dong_don(db, req.order_id)
    da_giao = svc.deliveries.da_giao_cua_yeu_cau(req.id)
    ten_kho = _ten_mat_hang(
        db, {(ln.hang_loai, ln.hang_id) for ln in req.lines
             if ln.hang_loai and ln.hang_id is not None},
    )
    khach = None
    if req.customer_id is not None:
        kh = CustomerRepository(db).get_by_id(req.customer_id)
        khach = getattr(kh, "name", None) if kh is not None else None
    cum = _cum_theo_dong(order)
    return DeliveryRequestOut(
        id=req.id,
        code=req.code,
        order_id=req.order_id,
        order_code=getattr(order, "order_no", None),
        customer_id=req.customer_id,
        customer_name=khach,
        department_id=req.department_id,
        ngay_can_giao=req.ngay_can_giao,
        dia_chi=req.dia_chi or "",
        nguoi_nhan=req.nguoi_nhan,
        sdt_nguoi_nhan=req.sdt_nguoi_nhan,
        ghi_chu=req.ghi_chu,
        trang_thai=svc.trang_thai_yeu_cau(req),
        ly_do_huy=req.ly_do_huy,
        created_by=req.created_by,
        created_by_name=_ten_nguoi(db, req.created_by),
        created_at=req.created_at,
        lines=[
            DeliveryRequestLineOut(
                **_cum_cua(cum, ln.order_line_id),
                id=ln.id, order_line_id=ln.order_line_id, qty=ln.qty,
                mo_ta=mo_ta.get(ln.order_line_id, ("", ""))[0],
                don_vi_tinh=mo_ta.get(ln.order_line_id, ("", ""))[1],
                da_giao=int(da_giao.get(ln.order_line_id, 0)),
                hang_loai=ln.hang_loai, hang_id=ln.hang_id, dvt=ln.dvt,
                hang_ten=ten_kho.get((ln.hang_loai or "", ln.hang_id or 0)),
            )
            for ln in req.lines
        ],
        so_lan_giao=len(svc.deliveries.trips_cua_yeu_cau(req.id)),
    )


def _cum_theo_dong(order) -> dict:
    """`{order_line_id: CumBan}` — chỉ cụm NHIỀU dòng (dòng đứng một mình không cần gom trên form)."""
    if order is None:
        return {}
    return {ln.id: c for c in cum_ban(order) if len(c.dong) > 1 for ln in c.dong}


def _cum_cua(cum: dict, order_line_id: int) -> dict:
    c = cum.get(order_line_id)
    return {"cum_khoa": c.khoa, "cum_ten": c.ten, "cum_dvt": c.dvt} if c is not None else {}


# `_trang_thai_lsx` GỠ 20/08/2026 (chủ chốt): "bên bộ phận giao hàng chỉ nhận yêu cầu thôi,
# SX như nào kệ nó". Nó chạy MỘT truy vấn cho MỖI dòng yêu cầu (N+1) để lấy một cột mà bộ phận
# giao hàng không dùng vào việc gì — PRD §quyết định #1 vốn đã nói rõ là KHÔNG chặn theo nó.


def _xe_cua(svc: DeliveryService, vehicle_id):
    """Bản ghi xe của chuyến, hoặc None. Gói lại vì `_trip_out` hỏi hai lần (biển số + tên)."""
    if vehicle_id is None or svc.xe is None:
        return None
    return svc.xe.get(vehicle_id)


def _trip_out(db: Session, svc: DeliveryService, trip, *, tong_km: int | None = None,
              canh_bao: list[str] | None = None) -> TripOut:
    req = svc.deliveries.get_request(trip.request_id)
    order = OrderRepository(db).get_by_id(req.order_id) if req is not None else None
    emp = EmployeeRepository(db).get_by_id(trip.employee_id)
    khach = None
    if req is not None and req.customer_id is not None:
        kh = CustomerRepository(db).get_by_id(req.customer_id)
        khach = getattr(kh, "name", None) if kh is not None else None
    yc_kho = svc.yeu_cau_kho_cua_trip(trip.id)
    yc_tra = svc.deliveries.yeu_cau_kho_cua_chuyen(trip.id, "NHAP")
    return TripOut(
        id=trip.id,
        request_id=trip.request_id,
        request_code=getattr(req, "code", None),
        order_id=getattr(req, "order_id", None),
        order_code=getattr(order, "order_no", None),
        customer_name=khach,
        lan_thu=trip.lan_thu,
        employee_id=trip.employee_id,
        employee_name=getattr(emp, "full_name", None),
        phu_xe_employee_id=trip.phu_xe_employee_id,
        phu_xe_name=getattr(
            svc.employees.get_by_id(trip.phu_xe_employee_id) if trip.phu_xe_employee_id else None,
            "full_name", None),
        vehicle_id=trip.vehicle_id,
        xe_bien_so=getattr(_xe_cua(svc, trip.vehicle_id), "ma", None),
        xe_ten=getattr(_xe_cua(svc, trip.vehicle_id), "ten", None),
        gio_lay_hang=trip.gio_lay_hang,
        gio_du_kien_giao=trip.gio_du_kien_giao,
        ghi_chu_phan_cong=trip.ghi_chu_phan_cong,
        trang_thai=trip.trang_thai,
        km=trip.km,
        tong_km=tong_km if tong_km is not None else (trip.km or 0),
        thoi_gian_ket_thuc=trip.thoi_gian_ket_thuc,
        nguoi_nhan_thuc_te=trip.nguoi_nhan_thuc_te,
        ly_do_that_bai=trip.ly_do_that_bai,
        huong_xu_ly=trip.huong_xu_ly,
        ngay_hen_lai=trip.ngay_hen_lai,
        ghi_chu_ket_qua=trip.ghi_chu_ket_qua,
        lines=[TripLineOut(order_line_id=l.order_line_id, qty_giao=l.qty_giao) for l in trip.lines],
        yeu_cau_kho_ma=getattr(yc_kho, "ma", None),
        yeu_cau_kho_trang_thai=getattr(yc_kho, "trang_thai", None),
        kho_da_lap_phieu=svc.kho_da_lap_phieu(trip.id),
        tra_hang_ma=getattr(yc_tra, "ma", None),
        tra_hang_trang_thai=getattr(yc_tra, "trang_thai", None),
        luot=_luot_out(svc.luot_cua_trip(trip)),
        canh_bao=list(canh_bao or []),
    )


def _luot_out(d: dict | None) -> LuotXeTrongChuyenOut | None:
    return LuotXeTrongChuyenOut(**d) if d is not None else None


# =================================================================================
# Yêu cầu giao hàng
# =================================================================================
@router.post("/requests", response_model=DeliveryRequestOut,
             status_code=status.HTTP_201_CREATED)
def tao_yeu_cau(body: DeliveryRequestCreate, svc: Service, db: Db, user: Writer):
    """GHI LÀ GHI — gửi yêu cầu giao cho đơn của CHÍNH MÌNH vẫn đòi ô Thao tác."""
    try:
        kq = svc.tao_yeu_cau(
            order_id=body.order_id,
            ngay_can_giao=body.ngay_can_giao,
            lines=[l.model_dump() for l in body.lines],
            actor=user,
            dia_chi_id=body.dia_chi_id,
            lien_he_id=body.lien_he_id,
        )
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _request_out(db, svc, svc.deliveries.get_request(kq["request"].id))


@router.get("/requests", response_model=DeliveryRequestPage)
def danh_sach_yeu_cau(
    svc: Service, db: Db, authz: Authz, user: Reader,
    order_id: int | None = Query(None),
    cho_len_ke_hoach: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    scope = _scope(authz, user)
    phong = svc._phong_duoc_xem(scope=scope, actor=user)
    nguoi_tao = user.id if scope == SCOPE_OWN else None
    dept_ids = None if scope != SCOPE_DEPARTMENT else phong
    # `trang_thai` trả về là TRẠNG THÁI TÍNH (svc.trang_thai_yeu_cau — nhiều bảng), không phải cột
    # thô, nên `cho_len_ke_hoach=True` phải lọc SAU khi dựng đủ item — không trang hoá được ở SQL.
    # `order_id` (màn Tạo yêu cầu, phạm vi 1 đơn) cũng giữ lấy TRỌN như cũ. Chỉ đường mặc định
    # (danh sách chung, không lọc) mới trang hoá thật ở SQL.
    phan_trang = order_id is None and not cho_len_ke_hoach
    reqs = svc.deliveries.list_requests(
        order_id=order_id,
        department_ids=dept_ids,
        created_by=nguoi_tao,
        chi_cho_len_ke_hoach=False,
        limit=size if phan_trang else None,
        offset=(page - 1) * size if phan_trang else 0,
    )
    items = [_request_out(db, svc, r) for r in reqs]
    if cho_len_ke_hoach:
        items = [i for i in items if i.trang_thai == "cho_len_ke_hoach"]
    total = (
        svc.deliveries.count_requests(order_id=order_id, department_ids=dept_ids,
                                      created_by=nguoi_tao)
        if phan_trang else len(items)
    )
    return DeliveryRequestPage(items=items, total=total)


@router.get("/requests/{request_id}", response_model=RequestDetailOut)
def chi_tiet_yeu_cau(request_id: int, svc: Service, db: Db, authz: Authz, user: Reader):
    req = svc.deliveries.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu giao hàng")
    try:
        svc.chan_ngoai_pham_vi_yeu_cau(req, scope=_scope(authz, user), actor=user)
    except DeliveryError as e:
        raise _err(e)
    trips = svc.deliveries.trips_cua_yeu_cau(request_id)
    lich_su: list[HistoryOut] = []
    for t in trips:
        for h in svc.deliveries.lich_su_cua_trip(t.id):
            lich_su.append(HistoryOut(
                id=h.id, tu_trang_thai=h.tu_trang_thai, den_trang_thai=h.den_trang_thai,
                nguoi_thao_tac_id=h.nguoi_thao_tac_id,
                nguoi_thao_tac_name=_ten_nguoi(db, h.nguoi_thao_tac_id),
                luc=h.luc, ghi_chu=h.ghi_chu, ly_do=h.ly_do,
            ))
    # MỚI NHẤT LÊN ĐẦU (chủ chốt 20/08/2026). Vòng lặp trên gom theo TỪNG CHUYẾN rồi mới theo
    # thời gian, nên yêu cầu giao hai lần thì toàn bộ chuyến 1 nằm trên toàn bộ chuyến 2 — không
    # phải dòng thời gian thật, và việc vừa xảy ra lại bị chôn ở giữa.
    #
    # Sắp bằng `(luc, id)`: `luc` là mốc nghiệp vụ, `id` phá hoà khi hai mốc trùng giây — thiếu
    # `id` thì hai dòng cùng giây đảo chỗ nhau mỗi lần mở màn.
    lich_su.sort(key=lambda h: (h.luc, h.id), reverse=True)
    return RequestDetailOut(
        request=_request_out(db, svc, req),
        trips=[_trip_out(db, svc, t) for t in trips],
        lich_su=lich_su,
    )


@router.put("/requests/{request_id}", response_model=DeliveryRequestOut)
def sua_yeu_cau(request_id: int, body: DeliveryRequestUpdate, svc: Service, db: Db,
                authz: Authz, user: Writer):
    try:
        svc.sua_yeu_cau(request_id, actor=user, scope=_scope(authz, user),
                        **body.model_dump(exclude_unset=True))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _request_out(db, svc, svc.deliveries.get_request(request_id))


@router.post("/requests/{request_id}/huy", response_model=DeliveryRequestOut)
def huy_yeu_cau(request_id: int, body: LyDoIn, svc: Service, db: Db, authz: Authz,
                # Người LẬP (ô Thao tác) huỷ được yêu cầu của mình khi CHƯA có chuyến — service chặn
                # khi đã có chuyến sống; chuyến đã xếp thì phải qua quản lý huỷ chuyến trước.
                user: Annotated[User, Depends(require_any_permission((MODULE, "create"),
                                                                    (MODULE, "cancel")))]):
    try:
        svc.huy_yeu_cau(request_id, ly_do=body.ly_do, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _request_out(db, svc, svc.deliveries.get_request(request_id))


@router.get("/orders/{order_id}/con-phai-giao", response_model=ConPhaiGiaoOut)
def con_phai_giao(order_id: int, svc: Service, db: Db, user: Reader):
    """Dùng ở màn Đơn hàng bán khi lập yêu cầu — và là cờ "đã giao đủ" cho kế toán."""
    try:
        con = svc.con_phai_giao(order_id)
    except DeliveryError as e:
        raise _err(e)
    order = OrderRepository(db).get_by_id(order_id)
    da_giao = svc.deliveries.da_giao_theo_dong(order_id)
    cum = _cum_theo_dong(order)
    return ConPhaiGiaoOut(
        order_id=order_id,
        da_giao_du=svc.da_giao_du(order_id),
        lines=[
            ConPhaiGiaoLine(
                **_cum_cua(cum, ln.id),
                order_line_id=ln.id, mo_ta=ln.description, don_vi_tinh=ln.don_vi_tinh,
                qty_dat=int(ln.qty or 0), da_giao=int(da_giao.get(ln.id, 0)),
                con_phai_giao=int(con.get(ln.id, 0)),
            )
            for ln in (order.lines if order is not None else [])
        ],
    )


# =================================================================================
# Lên kế hoạch — tab đòi ô `can_plan`
# =================================================================================
@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def len_ke_hoach(body: PlanIn, svc: Service, db: Db, authz: Authz, user: Planner):
    try:
        kq = svc.len_ke_hoach(
            request_id=body.request_id, employee_id=body.employee_id,
            phu_xe_employee_id=body.phu_xe_employee_id,
            vehicle_id=body.vehicle_id,
            gio_lay_hang=body.gio_lay_hang, gio_du_kien_giao=body.gio_du_kien_giao,
            actor=user, kho_id=body.kho_id, ghi_chu_phan_cong=body.ghi_chu_phan_cong,
            scope=_scope(authz, user), luot_xe_id=body.luot_xe_id,
        )
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return PlanOut(trip=_trip_out(db, svc, svc.deliveries.get_trip(kq["trip"].id)),
                   canh_bao=kq["canh_bao"])


@router.put("/plans/{trip_id}", response_model=PlanOut)
def doi_ke_hoach(trip_id: int, body: PlanUpdate, svc: Service, db: Db,
                 authz: Authz, user: Planner):
    try:
        kq = svc.doi_ke_hoach(trip_id, actor=user, scope=_scope(authz, user),
                              **body.model_dump(exclude_unset=True))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return PlanOut(trip=_trip_out(db, svc, svc.deliveries.get_trip(trip_id)),
                   canh_bao=kq["canh_bao"])


@router.get("/plans/{trip_id}/hang-can-xuat", response_model=list[HangCanXuatOut])
def hang_can_xuat(trip_id: int, svc: Service, db: Db, authz: Authz, user: Planner):
    """Xem trước dòng sẽ gửi kho — SUY RA từ yêu cầu giao, người dùng không sửa được.

    Có đường này để giao diện hiện đúng thứ sắp gửi, thay vì bắt gõ lại rồi hy vọng khớp.
    """
    trip = svc.deliveries.get_trip(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chuyến giao")
    try:
        svc.chan_ngoai_pham_vi_trip(trip, scope=_scope(authz, user), actor=user)
        ds = svc.hang_can_xuat(trip)
    except DeliveryError as e:
        raise _err(e)
    ten = _ten_mat_hang(db, {(d["hang_loai"], d["hang_id"]) for d in ds})
    return [
        HangCanXuatOut(hang_loai=d["hang_loai"], hang_id=d["hang_id"], dvt=d["dvt"],
                       sl_de_nghi=d["sl_de_nghi"],
                       hang_ten=ten.get((d["hang_loai"], d["hang_id"])))
        for d in ds
    ]


@router.post("/plans/{trip_id}/yeu-cau-xuat-kho", response_model=YeuCauKhoOut,
             status_code=status.HTTP_201_CREATED)
def gui_yeu_cau_xuat_kho(trip_id: int, body: YeuCauXuatKhoIn, svc: Service, db: Db,
                         authz: Authz, user: Planner):
    """Gửi YÊU CẦU XUẤT KHO thật cho chuyến — không phải chứng từ riêng của Giao hàng.

    Hàng ra khỏi kho phải có phiếu kho, giao khách không ngoại lệ (chủ chốt 19/08/2026). Đường
    này gọi thẳng service của kho nên mọi luật bên đó áp y hệt: mặt hàng phải có trong danh mục
    Giấy / Vật tư khác, đơn vị phải đổi được, tạo là duyệt luôn ⇒ kho lập phiếu ngay.
    """
    try:
        req = svc.gui_yeu_cau_xuat_kho(
            trip_id, actor=user, scope=_scope(authz, user), kho_id=body.kho_id,
            ngay_can=body.ngay_can, ghi_chu=body.ghi_chu,
        )
    except DeliveryError as e:
        raise _err(e)
    except Exception as e:  # lỗi nghiệp vụ của KHO (mặt hàng không có, đơn vị không đổi được…)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    return YeuCauKhoOut(id=req.id, ma=req.ma, trang_thai=req.trang_thai)


@router.post("/plans/{trip_id}/huy", response_model=TripOut)
def huy_ke_hoach(trip_id: int, body: LyDoIn, svc: Service, db: Db,
                 authz: Authz, user: Canceller):
    try:
        svc.huy_ke_hoach(trip_id, ly_do=body.ly_do, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _trip_out(db, svc, svc.deliveries.get_trip(trip_id))


# =================================================================================
# Chuyến giao — tab mặc định (ô Xem)
# =================================================================================
@router.get("/trips", response_model=TripPage)
def danh_sach_chuyen(svc: Service, db: Db, authz: Authz, user: Reader,
                     dang_chay: bool = Query(False),
                     page: int = Query(1, ge=1),
                     size: int = Query(20, ge=1, le=200)):
    scope = _scope(authz, user)
    emp_ids = None
    dept_ids = None
    if scope == SCOPE_OWN:
        eid = svc._employee_cua_user(user)
        emp_ids = [eid] if eid is not None else [-1]
    elif scope == SCOPE_DEPARTMENT:
        dept_ids = svc._phong_duoc_xem(scope=scope, actor=user)
    trang_thai = list(LAN_GIAO_DANG_CHAY) if dang_chay else None
    # Tab "Đơn giao hàng" gộp theo yêu cầu (1 dòng = chuyến MỚI NHẤT) — trang hoá thật ở SQL trên
    # chính danh sách đã gộp đó, không phải trang hoá rồi mới gộp (sai tổng/sai trang).
    trips = svc.deliveries.list_trips(
        employee_ids=emp_ids, department_ids=dept_ids, trang_thai=trang_thai,
        latest_per_request=True, limit=size, offset=(page - 1) * size,
    )
    total = svc.deliveries.count_trips(
        employee_ids=emp_ids, department_ids=dept_ids, trang_thai=trang_thai,
        latest_per_request=True,
    )
    tong_km_map = svc.deliveries.tong_km_theo_yeu_cau([t.request_id for t in trips])
    return TripPage(
        items=[_trip_out(db, svc, t, tong_km=tong_km_map.get(t.request_id, t.km or 0))
               for t in trips],
        total=total,
    )


@router.post("/trips/{trip_id}/da-lay-hang", response_model=TripOut)
def da_lay_hang(trip_id: int, svc: Service, db: Db, authz: Authz, user: Writer):
    """TÀI XẾ tự bấm khi đã cầm được hàng. Trước đây do KHO bấm — đổi 19/08/2026."""
    try:
        svc.da_lay_hang(trip_id, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _trip_out(db, svc, svc.deliveries.get_trip(trip_id))


@router.post("/trips/{trip_id}/bat-dau-giao", response_model=TripOut)
def bat_dau_giao(trip_id: int, svc: Service, db: Db, authz: Authz, user: Writer,
                 body: BatDauGiaoIn | None = None):
    """Chuyến ĐẦU của một lượt xe kèm số đồng hồ lúc xuất phát (PRD khoán km §14)."""
    try:
        kq = svc.bat_dau_giao(
            trip_id, actor=user, scope=_scope(authz, user),
            so_dong_ho_xuat_phat=body.so_dong_ho_xuat_phat if body is not None else None,
        )
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _trip_out(db, svc, svc.deliveries.get_trip(trip_id), canh_bao=kq["canh_bao"])


@router.post("/trips/{trip_id}/ket-qua", response_model=TripOut)
def ghi_ket_qua(trip_id: int, body: KetQuaIn, svc: Service, db: Db,
                authz: Authz, user: Writer):
    try:
        svc.ghi_ket_qua(
            trip_id, ket_qua=body.ket_qua, km=body.km, actor=user, scope=_scope(authz, user),
            thoi_gian_ket_thuc=body.thoi_gian_ket_thuc,
            nguoi_nhan_thuc_te=body.nguoi_nhan_thuc_te,
            ly_do_that_bai=body.ly_do_that_bai, huong_xu_ly=body.huong_xu_ly,
            ghi_chu=body.ghi_chu,
            so_thuc_nhan=[m.model_dump() for m in (body.so_thuc_nhan or [])] or None,
            xac_nhan_km_lon=body.xac_nhan_km_lon,
            vehicle_id=body.vehicle_id,
            so_dong_ho=body.so_dong_ho,
        )
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _trip_out(db, svc, svc.deliveries.get_trip(trip_id))


# =================================================================================
# Lượt xe — tiền km theo CHẶNG (PRD khoán km §14, chủ chốt 18/09/2026)
# =================================================================================
@router.get("/luot-xe", response_model=LuotXeMoPage)
def luot_xe_mo(svc: Service, user: Planner, vehicle_id: int = Query(...)):
    """Lượt CHƯA về kho của một xe — ô Lượt xe lúc lên đơn (người lên đơn giao hàng lập lượt)."""
    return LuotXeMoPage(items=[LuotXeMoOut(**x) for x in svc.luot_mo_cua_xe(vehicle_id)])


@router.post("/luot-xe/{luot_id}/ve-kho", response_model=VeKhoOut)
def ve_kho(luot_id: int, body: VeKhoIn, svc: Service, db: Db, authz: Authz, user: Writer):
    """Tài xế ghi số đồng hồ VỀ KHO ⇒ đóng lượt, tính chặng về kho."""
    try:
        kq = svc.ve_kho(luot_id, so_dong_ho=body.so_dong_ho, actor=user,
                        scope=_scope(authz, user), xac_nhan_km_lon=body.xac_nhan_km_lon)
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    luot = kq["luot"]
    return VeKhoOut(id=luot.id, code=luot.code, so_dong_ho_ve_kho=luot.so_dong_ho_ve_kho,
                    km_ve_kho=luot.km_ve_kho, ve_kho_luc=luot.ve_kho_luc,
                    canh_bao=kq["canh_bao"])


# --- Gom theo lượt: một lần bấm cho cả lượt (chủ chốt 18/09/2026) ------------------------------
# Lỗi giữa chừng ⇒ ném trước `db.commit()` ⇒ phiên đóng không commit ⇒ cả lô không lưu.
@router.post("/luot-xe", response_model=LenLuotOut, status_code=status.HTTP_201_CREATED)
def len_luot(body: LenLuotIn, svc: Service, db: Db, authz: Authz, user: Planner):
    """Lên đơn NHIỀU yêu cầu giao vào MỘT lượt xe — mỗi yêu cầu vẫn một chuyến, một phiếu kho."""
    try:
        kq = svc.len_luot(
            request_ids=body.request_ids, employee_id=body.employee_id,
            phu_xe_employee_id=body.phu_xe_employee_id, vehicle_id=body.vehicle_id,
            gio_lay_hang=body.gio_lay_hang, gio_du_kien_giao=body.gio_du_kien_giao,
            ghi_chu_phan_cong=body.ghi_chu_phan_cong, luot_xe_id=body.luot_xe_id,
            actor=user, scope=_scope(authz, user),
        )
    except DeliveryError as e:
        db.rollback()
        raise _err(e)
    db.commit()
    return LenLuotOut(
        luot_id=kq["luot"].id, code=kq["luot"].code, canh_bao=kq["canh_bao"],
        trips=[_trip_out(db, svc, svc.deliveries.get_trip(t.id)) for t in kq["trips"]],
    )


def _luot_chi_tiet_out(db: Session, svc: DeliveryService, kq: dict) -> LuotXeChiTietOut:
    luot = kq["luot"]
    xe = _xe_cua(svc, luot.vehicle_id)
    return LuotXeChiTietOut(
        id=luot.id, code=luot.code, ngay=luot.ngay, vehicle_id=luot.vehicle_id,
        xe_bien_so=getattr(xe, "ma", None), xe_ten=getattr(xe, "ten", None),
        so_dong_ho_xuat_phat=luot.so_dong_ho_xuat_phat,
        so_dong_ho_ve_kho=luot.so_dong_ho_ve_kho, ve_kho_luc=luot.ve_kho_luc,
        km_ve_kho=luot.km_ve_kho, goi_y_xuat_phat=kq["goi_y_xuat_phat"],
        so_dong_ho_gan_nhat=kq["so_dong_ho_gan_nhat"], cho_ve_kho=kq["cho_ve_kho"],
        tong_km=kq["tong_km"], diem=[_trip_out(db, svc, t) for t in kq["trips"]],
        so_cho_gui_kho=kq["so_cho_gui_kho"], so_cho_lay_hang=kq["so_cho_lay_hang"],
        so_cho_bat_dau=kq["so_cho_bat_dau"], so_dang_giao=kq["so_dang_giao"],
    )


@router.get("/luot-xe/{luot_id}", response_model=LuotXeChiTietOut)
def chi_tiet_luot(luot_id: int, svc: Service, db: Db, authz: Authz, user: Reader):
    try:
        kq = svc.chi_tiet_luot(luot_id, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        raise _err(e)
    return _luot_chi_tiet_out(db, svc, kq)


@router.get("/bang-giao", response_model=BangGiaoPage)
def bang_giao(svc: Service, db: Db, authz: Authz, user: Reader,
              page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200)):
    """Tab "Đơn giao hàng" gom theo LƯỢT XE (chủ chốt 18/09/2026: ghép nhiều yêu cầu mà hiện rời
    từng dòng thì tài xế lẫn người lên đơn khó hiểu). Mỗi khối là MỘT lượt (đủ các điểm, theo thứ
    tự chặng) hoặc MỘT chuyến lẻ; trang hoá theo khối nên một lượt không bị cắt đôi."""
    scope = _scope(authz, user)
    emp_ids = None
    dept_ids = None
    if scope == SCOPE_OWN:
        eid = svc._employee_cua_user(user)
        emp_ids = [eid] if eid is not None else [-1]
    elif scope == SCOPE_DEPARTMENT:
        dept_ids = svc._phong_duoc_xem(scope=scope, actor=user)
    khoi, total = svc.deliveries.khoi_bang_giao(
        employee_ids=emp_ids, department_ids=dept_ids, limit=size, offset=(page - 1) * size,
    )
    so_don = svc.deliveries.count_trips(employee_ids=emp_ids, department_ids=dept_ids,
                                        latest_per_request=True)
    le = [svc.deliveries.get_trip(i) for loai, i in khoi if loai == "chuyen"]
    tong_km_map = svc.deliveries.tong_km_theo_yeu_cau([t.request_id for t in le if t is not None])
    items: list[BangGiaoItem] = []
    for loai, i in khoi:
        if loai == "luot":
            try:
                kq = svc.chi_tiet_luot(i, actor=user, scope=scope)
            except DeliveryError:
                continue   # lượt vừa bị xoá giữa hai truy vấn — bỏ, đừng làm vỡ cả trang
            items.append(BangGiaoItem(luot=_luot_chi_tiet_out(db, svc, kq)))
        else:
            t = svc.deliveries.get_trip(i)
            if t is not None:
                items.append(BangGiaoItem(
                    trip=_trip_out(db, svc, t, tong_km=tong_km_map.get(t.request_id, t.km or 0))))
    return BangGiaoPage(items=items, total=total, so_don=so_don)


@router.post("/luot-xe/{luot_id}/yeu-cau-xuat-kho", response_model=CaLuotOut)
def gui_xuat_kho_ca_luot(luot_id: int, svc: Service, db: Db, authz: Authz, user: Planner,
                         body: GuiXuatKhoCaLuotIn | None = None):
    """Mỗi chuyến của lượt MỘT phiếu yêu cầu xuất kho — gửi cả lượt bằng một lần bấm."""
    try:
        phieu = svc.gui_xuat_kho_ca_luot(luot_id, actor=user, scope=_scope(authz, user),
                                         ghi_chu=body.ghi_chu if body is not None else None)
    except DeliveryError as e:
        db.rollback()
        raise _err(e)
    except Exception as e:  # lỗi nghiệp vụ của KHO — như đường gửi từng chuyến
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    # Báo kho SAU commit — bắn trước thì kho refetch trên kết nối khác, chưa thấy phiếu.
    for p in phieu:
        svc.stock_requests.thong_bao_yeu_cau_moi(p)
    return CaLuotOut(so_chuyen=len(phieu), phieu=[p.ma for p in phieu])


@router.post("/luot-xe/{luot_id}/da-lay-hang", response_model=CaLuotOut)
def da_lay_hang_ca_luot(luot_id: int, svc: Service, db: Db, authz: Authz, user: Writer):
    try:
        trips = svc.da_lay_hang_ca_luot(luot_id, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        db.rollback()
        raise _err(e)
    db.commit()
    return CaLuotOut(so_chuyen=len(trips))


@router.post("/luot-xe/{luot_id}/bat-dau-giao", response_model=CaLuotOut)
def bat_dau_giao_ca_luot(luot_id: int, svc: Service, db: Db, authz: Authz, user: Writer,
                         body: BatDauGiaoIn | None = None):
    try:
        kq = svc.bat_dau_giao_ca_luot(
            luot_id, actor=user, scope=_scope(authz, user),
            so_dong_ho_xuat_phat=body.so_dong_ho_xuat_phat if body is not None else None,
        )
    except DeliveryError as e:
        db.rollback()
        raise _err(e)
    db.commit()
    return CaLuotOut(so_chuyen=len(kq["trips"]), canh_bao=kq["canh_bao"])


@router.post("/trips/{trip_id}/da-tra-hang", response_model=TripOut)
def da_tra_hang(trip_id: int, svc: Service, db: Db, authz: Authz, user: Writer):
    try:
        svc.kho_nhan_lai_hang(trip_id, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return _trip_out(db, svc, svc.deliveries.get_trip(trip_id))


def _ai_la_tai_xe(db, *, scope, actor, svc):
    """MỘT luật cho câu "ai là tài xế" — dùng chung ô CHỌN và tab NHÂN VIÊN.

    Trước 20/08/2026 hai chỗ trả lời bằng hai luật khác nhau: tab lọc theo BỘ PHẬN, ô chọn lọc
    theo QUYỀN RBAC. Hậu quả thấy ngay trên màn: ô chọn mời cả Admin và thủ kho, còn tài xế thật
    thì lẫn giữa họ. Hai nguồn sự thật cho một câu hỏi thì sớm muộn lệch — đây là lần thứ ba
    trong tuần (xem `_dung_man` ở `vat_lieu_kho_service`).

    Luật:
      · Đã khai **Bộ phận Giao hàng** ⇒ lấy người thuộc bộ phận đó, CỘNG người đã có chuyến
        (chuyến cũ khai trước khi có cờ vẫn phải sửa/đổi tài xế được).
      · CHƯA khai phòng nào ⇒ lùi về luật cũ (có tài khoản mở được màn Giao hàng). Cùng khuôn
        `la_kinh_doanh`: "chưa tick phòng nào thì hệ tạm suy theo quyền module".

    Trả `(danh sách nhân viên, {user_id: có ô Thao tác}, có-đi-theo-bộ-phận-không)`.

    KHÔNG loại người chưa có tài khoản: `da-lay-hang` / `ket-qua` gác bằng ô **Thao tác**, nên
    quản lý bấm hộ được — chuyến không tắc. Chỉ đánh dấu `co_thao_tac` để người phân công biết ai
    tự bấm được.
    """
    from sqlalchemy import select as _select

    from ..models.role import RolePermission
    from ..models.user import User as _User

    emps = EmployeeRepository(db).list_scoped_all(scope=scope, actor=actor)
    # {user_id: can_create} — MỘT truy vấn cho cả danh sách; tra từng người là N+1 ngay trên ô
    # chọn mà quản lý mở mỗi lần phân công.
    vao_duoc = {
        int(uid): bool(ghi)
        for uid, ghi in db.execute(
            _select(_User.id, RolePermission.can_create)
            .join(RolePermission, RolePermission.role_id == _User.role_id)
            .where(RolePermission.module_key == MODULE, RolePermission.can_read.is_(True))
        ).all()
    }

    bo_phan = DepartmentRepository(db).dept_ids_giao_hang()
    if not bo_phan:
        return [e for e in emps if e.user_id is not None and e.user_id in vao_duoc], vao_duoc, False

    ra = [
        e for e in emps
        if e.department_id in bo_phan or svc.deliveries.list_trips(employee_ids=[e.id])
    ]
    return ra, vao_duoc, True


@router.get("/tai-xe-chon", response_model=TaiXeChonPage)
def tai_xe_chon(svc: Service, db: Db, authz: Authz, user: Planner):
    """Tài xế chọn được khi phân công — gác bằng ô LÊN KẾ HOẠCH, không phải `nhan_su`.

    Nguồn người CHUNG với tab Nhân viên giao hàng (`_ai_la_tai_xe`) — hai chỗ mà trả lời khác
    nhau thì ô chọn mời cả Admin lẫn thủ kho, còn tài xế thật lẫn giữa họ.

    Chỉ trả id · mã · họ tên · phòng · có-ô-thao-tác: vừa đủ để chọn, không phơi lương / BHXH.
    """
    emps, vao_duoc, _ = _ai_la_tai_xe(db, scope=_scope(authz, user), actor=user, svc=svc)
    phong = {d.id: d.name for d in DepartmentRepository(db).list_all()}
    return TaiXeChonPage(items=[
        TaiXeChonOut(id=e.id, code=e.code, full_name=e.full_name,
                     department=phong.get(e.department_id),
                     co_tai_khoan=e.user_id is not None,
                     co_thao_tac=bool(vao_duoc.get(e.user_id or 0, False)))
        for e in emps
    ])


# =================================================================================
# Tab Nhân viên giao hàng — ô riêng vì phơi lịch + KPI của NGƯỜI KHÁC
# =================================================================================
@router.get("/nhan-vien", response_model=DriverPage)
def nhan_vien_giao_hang(svc: Service, db: Db, authz: Authz, user: DriverViewer,
                        ngay: date | None = Query(None),
                        thang: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")):
    """`ngay` cho cột HÔM NAY, `thang` (YYYY-MM) cho cột THÁNG — hai tham số RỜI, cố ý.

    Gộp một tham số thì xem tháng sau là cột "hôm nay" nhảy sang ngày 1 tháng sau — một con số
    không có nghĩa gì. Trạng thái / chuyến đang chạy luôn là BÂY GIỜ, không đổi theo tháng xem.
    """
    hom = ngay or date.today()
    if thang:
        nam_s, thang_s = thang.split("-")
        moc_thang = date(int(nam_s), int(thang_s), 1)
    else:
        moc_thang = hom
    # CÙNG nguồn phạm vi với Chấm công / Nghỉ phép / Lương — tự viết điều kiện lọc thứ hai
    # là hai nơi hiểu "cả phòng" theo hai kiểu.
    # CÙNG nguồn người với ô chọn tài xế (`_ai_la_tai_xe`) — xem docstring hàm đó.
    emps, _vao_duoc, _theo_bo_phan = _ai_la_tai_xe(
        db, scope=_scope(authz, user), actor=user, svc=svc,
    )
    items: list[DriverOut] = []
    for e in emps:
        trips = svc.deliveries.list_trips(employee_ids=[e.id])
        dang = next((t for t in trips if t.trang_thai in LAN_GIAO_DANG_CHAY), None)
        ke_tiep = next(
            (t for t in sorted(trips, key=lambda x: x.gio_lay_hang)
             if t.trang_thai in LAN_GIAO_DANG_CHAY and (dang is None or t.id != dang.id)),
            None,
        )
        tk = svc.thong_ke_ngay(e.id, ngay=hom)
        tkt = svc.thong_ke_thang(e.id, ngay=moc_thang)
        req_dang = svc.deliveries.get_request(dang.request_id) if dang is not None else None
        req_ke = svc.deliveries.get_request(ke_tiep.request_id) if ke_tiep is not None else None
        items.append(DriverOut(
            employee_id=e.id,
            ho_ten=getattr(e, "full_name", "") or "",
            trang_thai=svc.trang_thai_nhan_vien(e.id, ngay=hom),
            chuyen_dang_thuc_hien=getattr(req_dang, "code", None),
            chuyen_ke_tiep=getattr(req_ke, "code", None),
            so_chuyen_xong=tk["so_chuyen_xong"],
            tong_km=tk["tong_km"],
            so_chuyen_thang=tkt["so_chuyen_xong"],
            tong_km_thang=tkt["tong_km"],
        ))
    return DriverPage(items=items)


# =========================================================================================
# File minh chứng của chuyến — hàng đi kèm hoá đơn (chủ chốt 22/08/2026)
# =========================================================================================
@router.get("/trips/{trip_id}/dinh-kem", response_model=DinhKemListOut)
def dinh_kem_list(trip_id: int, svc: Service, authz: Authz, user: Reader):
    try:
        rows = svc.dinh_kem_cua_trip(trip_id, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        raise _err(e)
    return DinhKemListOut(items=[DinhKemOut.model_validate(r) for r in rows])


@router.post("/trips/{trip_id}/dinh-kem", response_model=DinhKemOut,
             status_code=status.HTTP_201_CREATED)
def dinh_kem_them(trip_id: int, svc: Service, db: Db, authz: Authz, user: Writer,
                  file: UploadFile = File(...)):
    try:
        row = svc.dinh_kem_them(
            trip_id, actor=user, scope=_scope(authz, user),
            file_name=file.filename, content_type=file.content_type, data=file.file.read(),
        )
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    db.refresh(row)
    return DinhKemOut.model_validate(row)


@router.delete("/trips/{trip_id}/dinh-kem/{attachment_id}",
               status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def dinh_kem_xoa(trip_id: int, attachment_id: int, svc: Service, db: Db, authz: Authz,
                 user: Writer):
    try:
        svc.dinh_kem_xoa(trip_id, attachment_id, actor=user, scope=_scope(authz, user))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- % chia tiền một chuyến cho kíp xe --------------------------------------------------------
# Trước 12/09/2026 hai ô này đi ké endpoint ghi BẢNG BẬC cấp phòng. Bảng bậc đó đã GỠ (mọi xe ăn
# theo MỨC, xem khối dưới) nên % tách ra đường riêng — nó vẫn là luật thật: tiền một chuyến chia
# cho tài xế và phụ xe, đi một mình thì tài xế ăn trọn.
#
# Gate `luong` HOẶC `phong_ban`: khối khoán km nằm ở màn Cấu hình lương (quyền `luong`), nhưng vẫn
# nhận `phong_ban` để không phá luồng cũ / người quản phòng ban.
@router.get("/departments/{dept_id}/khoan-km-pct", response_model=KhoanKmPctOut)
def khoan_km_pct(
    dept_id: int, svc: Service,
    _: Annotated[User, Depends(require_any_permission(("luong", "view_salary"),
                                                      ("luong", "update"),
                                                      ("phong_ban", "read")))],
) -> KhoanKmPctOut:
    tx, px = svc.khoan_km_pct(dept_id)
    return KhoanKmPctOut(pct_tai_xe=tx, pct_phu_xe=px)


@router.put("/departments/{dept_id}/khoan-km-pct", response_model=KhoanKmPctOut)
def ghi_khoan_km_pct(
    dept_id: int, body: KhoanKmPctIn, svc: Service, db: Db,
    _: Annotated[User, Depends(require_any_permission(("luong", "update"),
                                                      ("phong_ban", "update")))],
) -> KhoanKmPctOut:
    try:
        tx, px = svc.ghi_khoan_km_pct(dept_id, pct_tai_xe=body.pct_tai_xe,
                                      pct_phu_xe=body.pct_phu_xe)
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return KhoanKmPctOut(pct_tai_xe=tx, pct_phu_xe=px)


# --- MỨC khoán km (PRD §11) ------------------------------------------------------------------
# Mỗi mức một bảng bậc, nhiều xe dùng chung một mức. Cấu hình CHUNG (14/09/2026), không thuộc phòng
# ban nào. Cổng GHI là quyền lương: người khai biển số (`dm_xe`) không sửa được giá. Cổng ĐỌC có
# thêm `dm_xe`: từ 14/09 xe BẮT BUỘC có mức — người khai xe không đọc được danh sách mức thì màn Xe
# không tạo nổi chiếc nào.
_DOC_MUC = require_any_permission(("luong", "view_salary"), ("luong", "update"),
                                  ("phong_ban", "read"), ("dm_xe", "read"))
_GHI_MUC = require_any_permission(("luong", "update"), ("phong_ban", "update"))


@router.get("/muc-khoan-km", response_model=MucKmListOut)
def danh_sach_muc(svc: Service, _: Annotated[User, Depends(_DOC_MUC)]) -> MucKmListOut:
    return MucKmListOut(items=[MucKmOut(**m) for m in svc.danh_sach_muc()])


@router.post("/muc-khoan-km", response_model=MucKmListOut, status_code=201)
def tao_muc(body: MucKmIn, svc: Service, db: Db,
            _: Annotated[User, Depends(_GHI_MUC)]) -> MucKmListOut:
    try:
        svc.tao_muc(ten=body.ten, ghi_chu=body.ghi_chu)
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return MucKmListOut(items=[MucKmOut(**m) for m in svc.danh_sach_muc()])


@router.put("/muc-khoan-km/{muc_id}", response_model=MucKmListOut)
def sua_muc(muc_id: int, body: MucKmSua, svc: Service, db: Db,
            _: Annotated[User, Depends(_GHI_MUC)]) -> MucKmListOut:
    try:
        # `exclude_unset`: ô KHÔNG gửi thì giữ nguyên. Ghi cả ba ô mỗi lần là màn đổi tên (chỉ gửi
        # `{ten}`) xoá mất ghi chú và bật lại mức đang tắt — lỗi thật, bắt được 14/09/2026.
        svc.sua_muc(muc_id, **body.model_dump(exclude_unset=True))
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return MucKmListOut(items=[MucKmOut(**m) for m in svc.danh_sach_muc()])


@router.delete("/muc-khoan-km/{muc_id}", response_model=MucKmListOut)
def xoa_muc(muc_id: int, svc: Service, db: Db,
            _: Annotated[User, Depends(_GHI_MUC)]) -> MucKmListOut:
    try:
        svc.xoa_muc(muc_id)
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return MucKmListOut(items=[MucKmOut(**m) for m in svc.danh_sach_muc()])


@router.put("/muc-khoan-km/{muc_id}/bac", response_model=MucKmListOut)
def ghi_bac_muc(muc_id: int, body: MucKmBracketsIn, svc: Service, db: Db,
                _: Annotated[User, Depends(_GHI_MUC)]) -> MucKmListOut:
    """Ghi bảng bậc của một mức. Hết tham số phòng ban (14/09/2026): bậc thuộc về MỨC."""
    try:
        svc.ghi_bac_muc(muc_id, [it.model_dump() for it in body.items])
    except DeliveryError as e:
        raise _err(e)
    db.commit()
    return MucKmListOut(items=[MucKmOut(**m) for m in svc.danh_sach_muc()])
