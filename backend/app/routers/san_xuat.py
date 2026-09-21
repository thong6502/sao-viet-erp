"""Router Thực hiện sản xuất — bàn của TỔ (Giai đoạn 2 mặt đọc + Giai đoạn 1 navbar node lá).

Prefix `/api/san-xuat`. Quyền theo DÒNG QUYỀN THEO TỔ `to_sx_<id phòng ban>` (spec 2026-09-14):
Xem + phạm vi + ba quyền chi tiết (Thực hiện lệnh · Xác nhận sản lượng · Kho). KCS KHÔNG theo tổ:
người thuộc phòng ban `is_kcs` kiểm được mọi tổ (cổng ở `services/san_xuat/kcs.py`). Router chỉ
gác THÔ bằng `require_quyen_to(việc)` (có việc đó ở ÍT NHẤT một tổ); cổng theo đúng tổ + mức "Của
tôi" nằm ở service (`quyen_to.gate_to`). Module `san_xuat` giữ cho Kế hoạch SX, không gác Bàn tổ.

Lát này CHỈ ĐỌC:
  · GET /teams        — danh sách tổ sản xuất (node lá) + badge số việc chờ, cho navbar + màn.
  · GET /work-items   — công việc ĐÃ PHÁT HÀNH của MỘT tổ (timeline), chặn nếu ngoài phạm vi.

Phân công / phiên chạy / sản lượng (ghi) là các lát sau, thêm bảng riêng.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import (
    get_authorization_service, get_current_user, require_permission, require_quyen_to,
)
from ..models.user import User
from ..realtime import hub
from ..repositories.san_xuat_repo import SanXuatRepository
from ..storage import get_storage, make_key, url_from_key
from ..schemas.san_xuat import (
    BanGiaoDeXuatIn,
    BanGiaoDieuChinhIn,
    BanGiaoKetQuaOut,
    BanGiaoSuaIn,
    BanGiaoXacNhanIn,
    BatchIn,
    BatDauIn,
    DoiMayIn,
    DongNhomDieuKienOut,
    DongNhomKetQuaOut,
    DongThieuIn,
    GoPhanCongIn,
    HoTroDeXuatIn,
    HoTroHuyIn,
    HoTroKetQuaOut,
    HoTroXacNhanIn,
    KcsBaoCaoOut,
    KcsChuoiCongDoanOut,
    KcsCongDoanLocListOut,
    KcsCongViecOut,
    KcsDaXemKetQuaOut,
    KcsDieuChinhIn,
    KcsDieuChinhKetQuaOut,
    KcsKiemKetQuaOut,
    KcsLenhListOut,
    KetThucIn,
    MayDoiOut,
    LenhKetQuaOut,
    HoTroUngVienListOut,
    ChoXacNhanOut,
    NhanVienChonListOut,
    NhapKhoYcKetQuaOut,
    PhanCongIn,
    SanLuongCuaToiOut,
    SanLuongToOut,
    SanLuongKetQuaOut,
    SuCoIn,
    SuCoKetQuaOut,
    TamDungIn,
    TeamsOut,
    ThemLotIn,
    VatTuDeNghiIn,
    VatTuNhanKetQuaOut,
    VatTuXacNhanIn,
    TepLenhOut,
    WorkItemChiTietOut,
    WorkItemsOut,
)
from ..services.rbac_service import AuthorizationService
from ..services.san_xuat import (
    ban_giao,
    board,
    dong_nhom,
    ho_tro,
    kcs,
    kcs_bao_cao,
    kho,
    san_luong,
    su_co,
    tep_lenh,
    thuc_thi,
    vat_tu_de_nghi,
    vat_tu_nhan,
    viec_khoan,
)
from ..services.san_xuat.san_luong_cua_toi import san_luong_cua_toi as san_luong_cua_toi_svc
from ..services.san_xuat import san_luong_to as san_luong_to_svc
from ..services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
from ..services.stock_request_service import StockRequestError

router = APIRouter(prefix="/api/san-xuat", tags=["san-xuat"])
MODULE = "san_xuat"
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]

# Ảnh bằng chứng lỗi KCS — subdir khai kèm ở `routers/files.py::_PREFIX_PERMISSION["san-xuat"]` để
# chỉ người có quyền đọc module này mới xem được. Giới hạn 15MB như ky_thuat_may.
SUBDIR = "san-xuat"
_MAX_ANH_BYTES = 15 * 1024 * 1024


def _phat_sse(res: dict) -> None:
    """SSE SAU commit (§18): báo bàn tổ đổi + đẩy thông báo tới người vừa được giao (nếu có tài khoản)."""
    hub.broadcast({
        "type": "san_xuat_cong_viec_changed",
        "team_id": res.get("department_id"),
        "cong_viec_id": res.get("cong_viec_id"),
        "trang_thai": res.get("trang_thai"),
    })
    uid = res.get("notify_user_id")
    if uid:
        hub.publish(uid, {"type": "san_xuat_duoc_giao_viec",
                          "cong_viec_id": res.get("cong_viec_id")})


def _phat_sse_ban_giao(res: dict) -> None:
    """Bàn giao đổi trạng thái → refresh CẢ hai bàn tổ (nguồn + đích) + đẩy tới người cần hành động.

    MỘT gói mang cả hai tổ (`team_ids`), không phải mỗi tổ một gói: `broadcast` tới MỌI kết nối và
    mỗi gói bump tick chung ở FE, nên hai gói là mọi màn đang mở nạp lại hai lượt cho một cú bấm
    (đo 16/09/2026 ở bàn tổ: danh sách việc ×3, hộp thư kho ×2, chờ xác nhận ×2 cho một Đề xuất)."""
    teams = sorted({t for t in (res.get("nguon_department_id"), res.get("dich_department_id")) if t})
    if teams:
        hub.broadcast({
            "type": "san_xuat_ban_giao_changed",
            "team_ids": teams,
            "ban_giao_id": res.get("ban_giao_id"),
            "trang_thai": res.get("trang_thai_ban_giao"),
        })
    for uid in res.get("notify_user_ids") or []:
        hub.publish(uid, {
            "type": "san_xuat_ban_giao",
            "ban_giao_id": res.get("ban_giao_id"),
            "trang_thai": res.get("trang_thai_ban_giao"),
            "su_kien": res.get("su_kien"),
            "nguon_ten": res.get("nguon_ten"),
            "dich_ten": res.get("dich_ten"),
            "so_luong": res.get("so_luong"),
            "don_vi": res.get("don_vi"),
        })


def _phat_sse_vat_tu(res: dict) -> None:
    """Tổ xác nhận nhận vật tư → refresh bàn tổ nhận."""
    team = res.get("department_id")
    if team:
        hub.broadcast({
            "type": "san_xuat_vat_tu_nhan",
            "team_id": team,
            "voucher_id": res.get("voucher_id"),
        })


def _phat_sse_ho_tro(res: dict) -> None:
    """Thỏa thuận hỗ trợ đổi (§9) → refresh chỗ hiển thị + đẩy tới người giữ quyền Xác nhận ở CẢ HAI tổ (§18)."""
    hub.broadcast({
        "type": "san_xuat_ho_tro_changed",
        "cong_viec_id": res.get("cong_viec_id"),
        "ho_tro_id": res.get("ho_tro_id"),
        "trang_thai": res.get("trang_thai"),
    })
    for uid in res.get("notify_user_ids") or []:
        hub.publish(uid, {
            "type": "san_xuat_ho_tro",
            "ho_tro_id": res.get("ho_tro_id"),
            "trang_thai": res.get("trang_thai"),
            "su_kien": res.get("su_kien"),
            "ho_ten": res.get("ho_ten"),
            "ten_cong_doan": res.get("ten_cong_doan"),
            "to_goc_ten": res.get("to_goc_ten"),
            "to_thuc_hien_ten": res.get("to_thuc_hien_ten"),
        })


def _phat_sse_kcs(res: dict) -> None:
    """KCS đổi → refresh màn KCS + bàn tổ của công đoạn; kiểm có kết quả thì ĐẨY tới người Xác nhận
    sản lượng trọn tổ đó (§18) — kết quả kiểm là tương tác GIỮA KCS và tổ nên phải tới NGAY."""
    hub.broadcast({
        "type": "san_xuat_kcs_changed",
        "cong_viec_id": res.get("cong_viec_id"),
        "kcs_batch_id": res.get("kcs_batch_id"),
        "loi_id": res.get("loi_id"),
        "team_id": res.get("department_id"),
        "lsx_id": res.get("lsx_id"),
    })
    for uid in res.get("notify_user_ids") or []:
        if uid:
            hub.publish(uid, {
                "type": "san_xuat_kcs_ket_qua",
                "team_id": res.get("department_id"),
                "cong_viec_id": res.get("cong_viec_id"),
                "loi_id": res.get("loi_id"),
                "lsx_ma": res.get("lsx_ma"),
                "ten_cong_doan": res.get("ten_cong_doan"),
                "so_dat": res.get("so_dat"),
                "so_loi": res.get("so_loi_cua_to", res.get("so_loi")),
                "nguoi_kiem": res.get("nguoi_kiem"),
            })
    # Lỗi KCS quy về công đoạn TRƯỚC (bắt ở bước sau) — tổ đó cũng phải biết NGAY.
    for m in res.get("bao_loi_nguon") or []:
        hub.broadcast({
            "type": "san_xuat_kcs_changed",
            "cong_viec_id": m.get("cong_viec_id"),
            "kcs_batch_id": res.get("kcs_batch_id"),
            "loi_id": m.get("loi_id"),
            "team_id": m.get("department_id"),
            "lsx_id": res.get("lsx_id"),
        })
        for uid in m.get("notify_user_ids") or []:
            if uid:
                hub.publish(uid, {
                    "type": "san_xuat_kcs_ket_qua",
                    "team_id": m.get("department_id"),
                    "cong_viec_id": m.get("cong_viec_id"),
                    "loi_id": m.get("loi_id"),
                    "lsx_ma": res.get("lsx_ma"),
                    "ten_cong_doan": m.get("ten_cong_doan"),
                    "phat_hien_o": res.get("ten_cong_doan"),
                    "so_loi": m.get("so_loi"),
                    "don_vi": res.get("don_vi"),
                    "nguoi_kiem": res.get("nguoi_kiem"),
                })


def _phat_sse_dong_nhom(ket: dict) -> None:
    """Nhóm thành phẩm đã đóng (§16 đủ / §13.3 thiếu) → refresh chỗ hiển thị nhóm + báo Sale và Kế
    hoạch SX NGAY (§17): đơn đã ra thành phẩm, có thể giao/đóng đơn. Broadcast là đủ (ai đang mở
    bàn/đơn đó tự cập nhật); không nhắm riêng vì người nhận là vai, không phải một tài khoản."""
    hub.broadcast({
        "type": "san_xuat_nhom_dong",
        "nhom_id": ket.get("nhom_id"),
        "order_id": ket.get("order_id"),
        "trang_thai": ket.get("trang_thai"),
        "kieu": ket.get("kieu"),
    })


def _thu_dong_nhom(db: Session, res: dict, *, user=None, su_kien: str = "") -> None:
    """CHỐT CHẶN §16 sau một thao tác có thể hoàn tất điều kiện cuối: lần ra `nhom_id` từ kết quả
    (trực tiếp hoặc qua công việc), thử tự đóng ĐỦ, và nếu đóng thì bắn SSE. Lỗi lần-ra hay không đủ
    điều kiện đều im lặng — chốt chặn không được làm hỏng thao tác chính đã commit."""
    try:
        nhom_id = res.get("nhom_id")
        if not nhom_id:
            cvid = res.get("cong_viec_id") or res.get("nguon_cong_viec_id")
            if cvid:
                cv = SanXuatRepository(db).cong_viec(cvid)
                nhom_id = cv.nhom_id if cv else None
        if not nhom_id:
            return
        ket = dong_nhom.tu_dong_dong_neu_du(db, nhom_id=nhom_id, actor=user, su_kien=su_kien)
        if ket:
            _phat_sse_dong_nhom(ket)
    except Exception:
        # Thao tác chính đã commit + bắn SSE; chốt chặn hỏng KHÔNG được hoá 500. Nhóm sẽ tự đóng ở
        # lần chốt chặn kế tiếp (hoặc trưởng KCS đóng thiếu).
        db.rollback()


def _luu_anh_kcs(owner_id: int, files: list[UploadFile]) -> tuple[list[dict], list[str]]:
    """Lưu ảnh bằng chứng lỗi KCS vào storage, trả (mô-tả-ảnh, keys). Kiểm rỗng/kích-thước/loại-ảnh
    như ky_thuat_may. Nếu bất kỳ file nào lỗi → xoá hết key đã ghi rồi ném (đừng để rác mồ côi)."""
    anh: list[dict] = []
    keys: list[str] = []
    try:
        for f in files:
            data = f.file.read()
            if not data:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tệp rỗng.")
            if len(data) > _MAX_ANH_BYTES:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Ảnh vượt quá 15MB.")
            if not (f.content_type or "").lower().startswith("image/"):
                raise HTTPException(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    f"Chỉ nhận tệp ảnh (JPG, PNG, HEIC…) — tệp này là "
                    f"{f.content_type or 'không rõ loại'}.",
                )
            key, safe = make_key(f"{SUBDIR}/kcs-loi", owner_id, f.filename)
            get_storage().save(key, data, f.content_type)
            keys.append(key)
            anh.append({"file_name": safe, "file_url": url_from_key(key),
                        "file_type": f.content_type})
        return anh, keys
    except HTTPException:
        for k in keys:
            get_storage().delete(k)
        raise


def _don_anh(keys: list[str]) -> None:
    for k in keys:
        get_storage().delete(k)


@router.get("/teams", response_model=TeamsOut)
def teams(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_quyen_to("read"))],
) -> TeamsOut:
    """Tổ sản xuất user được thấy + badge số việc chưa xong (navbar §2.1, màn bàn tổ §11)."""
    return TeamsOut(teams=board.teams(db, user, authz))


@router.get("/teams/{team_id}/nhan-vien", response_model=NhanVienChonListOut)
def nhan_vien_cua_to(
    team_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_quyen_to("read"))],
) -> NhanVienChonListOut:
    """Danh nhân viên chọn được để giao vào việc của tổ (ô "Giao người" §7.1). 403 nếu ngoài phạm vi.

    Gác bằng Xem của dòng tổ (KHÔNG mượn `nhan_su`): người điều hành tổ đổ được danh chọn mà không
    cần quyền nhân sự. Ghi thật vẫn do `phan-cong` gác quyền Thực hiện lệnh đúng tổ ở service.
    """
    try:
        return NhanVienChonListOut.model_validate(
            board.nhan_vien_chon(db, user, authz, team_id=team_id)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/teams/{team_id}/ho-tro-ung-vien", response_model=HoTroUngVienListOut)
def ho_tro_ung_vien_cua_to(
    team_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_quyen_to("read"))],
) -> HoTroUngVienListOut:
    """Ứng viên mời HỖ TRỢ CHÉO (§9) cho tổ: thợ ở các tổ SX khác. 403 nếu tổ ngoài phạm vi.

    Cùng gác Xem như ô "Giao người". Ghi thỏa thuận vẫn do `/work-items/{id}/ho-tro` gác quyền
    Xác nhận sản lượng đúng tổ ở service.
    """
    try:
        return HoTroUngVienListOut.model_validate(
            board.ho_tro_ung_vien(db, user, authz, team_id=team_id)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/work-items", response_model=WorkItemsOut)
def work_items(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_quyen_to("read"))],
    team_id: int = Query(..., ge=1),
    nhom: Literal["lenh", "phang"] = Query("lenh"),
    tim: str | None = Query(None, max_length=200),
    trang: int = Query(1, ge=1),
    co_trang: int = Query(20, ge=1, le=100),
    tu_ngay: date | None = Query(None),
    den_ngay: date | None = Query(None),
    cho_xac_nhan: bool = Query(False),
    trang_thai: list[Literal["released", "running", "paused", "completed"]] | None = Query(None),
    nhan_tu: date | None = Query(None),
    nhan_den: date | None = Query(None),
    sap_xep: Literal["moi_nhan", "cu_nhan", "du_kien"] = Query("moi_nhan"),
) -> WorkItemsOut:
    """Việc đã phát hành của MỘT tổ (§18 /work-items).

    `nhom="lenh"` (mặc định) trả ĐẦU MỤC LỆNH SX / BÀI GHÉP, mỗi lệnh bọc các công đoạn của tổ —
    đơn vị việc vẫn là CÔNG ĐOẠN, lệnh chỉ là tầng nhãn để tổ trưởng biết công đoạn này của lệnh
    nào. Cắt trang Ở MÁY CHỦ và đếm trang bằng LỆNH nên một lệnh không bao giờ bị xé đôi;
    `co_trang` chặn trần ngay tại đây (`le=100`) chứ không bóp im lặng trong service.

    `tim` là ô tìm kiếm của bàn — lọc Ở SQL trước khi cắt trang, chứ không lọc bằng JS sau khi
    trang đã về (lọc sau thì ô tìm kiếm chỉ soi được đúng 20 lệnh đang hiện).

    `nhom="phang"` giữ nguyên mảng bước phẳng cho Gantt, thêm cửa sổ `tu_ngay`/`den_ngay`.

    `cho_xac_nhan=true` (ô "chờ xác nhận" của bàn): chỉ lệnh có công đoạn đang chờ tổ bấm.

    Lọc nâng cao (view Bảng): `trang_thai` (lặp tham số), `nhan_tu`/`nhan_den` (ngày xưởng tổ
    nhận lệnh, gồm cả hai đầu), `sap_xep` (mặc định `moi_nhan`: lệnh phát hành sau nằm trên).

    403 nếu tổ ngoài phạm vi quyền."""
    try:
        return WorkItemsOut.model_validate(
            board.work_items(db, user, authz, team_id=team_id, nhom=nhom, tim=tim,
                             trang=trang, co_trang=co_trang, tu_ngay=tu_ngay, den_ngay=den_ngay,
                             cho_xac_nhan=cho_xac_nhan, trang_thai=set(trang_thai or ()) or None,
                             nhan_tu=nhan_tu, nhan_den=nhan_den, sap_xep=sap_xep)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/toi/san-luong", response_model=SanLuongCuaToiOut)
def san_luong_cua_toi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("read"))],
    nam: int = Query(..., ge=2000, le=2200),
    thang: int = Query(..., ge=1, le=12),
) -> SanLuongCuaToiOut:
    """Luỹ kế sản lượng tháng của CHÍNH người đăng nhập (§6): thợ tự trả lời "tháng này tôi làm
    được bao nhiêu" mà không phải chờ bảng lương.

    KHÔNG nhận `employee_id` — nhân sự luôn suy từ token trong service. Nhận từ URL là biến đây
    thành cửa xem sản lượng của bất kỳ ai chỉ bằng cách đổi một con số.
    """
    return SanLuongCuaToiOut.model_validate(
        san_luong_cua_toi_svc(db, user, nam=nam, thang=thang)
    )


@router.get("/san-luong", response_model=SanLuongToOut)
def san_luong_to(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("read"))],
    team_id: int = Query(...),
    tu: date | None = Query(None),
    den: date | None = Query(None),
    to_id: int | None = Query(None),
    tim: str | None = Query(None, max_length=100),
    trang: int = Query(1, ge=1),
    co_trang: int = Query(20, ge=1, le=100),
) -> SanLuongToOut:
    """Tab Sản lượng của bàn tổ: lệnh → công đoạn → người, lọc theo ngày bắt đầu mẻ (giờ xưởng),
    đơn vị trong vùng và mã/tên lệnh. Phạm vi theo dòng quyền tổ; 403 nếu tổ ngoài phạm vi xem."""
    try:
        return SanLuongToOut.model_validate(san_luong_to_svc.san_luong(
            db, user, team_id=team_id, tu=tu, den=den, to_id=to_id, tim=tim,
            trang=trang, co_trang=co_trang,
        ))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/work-items/{cong_viec_id}", response_model=WorkItemChiTietOut)
def work_item_detail(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_quyen_to("read"))],
) -> WorkItemChiTietOut:
    """Drawer một công việc (§5.1): thanh kế hoạch + roster + phiên chạy + khoảng tham gia."""
    try:
        return WorkItemChiTietOut.model_validate(
            board.chi_tiet_cong_viec(db, user, authz, cong_viec_id=cong_viec_id)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/work-items/{cong_viec_id}/tep-lenh", response_model=TepLenhOut)
def work_item_tep_lenh(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("read"))],
) -> TepLenhOut:
    """Tệp Kế hoạch SX đính kèm vào lệnh của công việc — tổ xem/tải sau khi phát hành, không sửa."""
    try:
        return TepLenhOut(nhom=tep_lenh.tep_cua_cong_viec(db, user, cong_viec_id=cong_viec_id))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# --- Mặt GHI (§7.1–§7.2) --------------------------------------------------------------------
# Gác THÔ bằng `require_quyen_to(việc)`; ranh giới an ninh THỰC là `_gate` → `quyen_to.gate_to` ở
# service (đúng tổ của công việc, mức "Của tôi" chỉ qua khi việc đang giao cho mình).
def _chay(fn):
    """Chạy lệnh ghi, dịch lỗi nghiệp vụ: quyền → 403, ràng buộc → 400."""
    try:
        return fn()
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/work-items/{cong_viec_id}/phan-cong", response_model=LenhKetQuaOut)
def phan_cong(
    cong_viec_id: int,
    body: PhanCongIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Giao MỘT người vào công việc (§7.1). Lần giao đầu = tổ tiếp nhận (§5.2)."""
    res = _chay(lambda: thuc_thi.phan_cong(
        db, user=user, cong_viec_id=cong_viec_id,
        employee_id=body.employee_id, expected_version=body.expected_version,
    ))
    _phat_sse(res)
    return res


@router.post("/phan-cong/{phan_cong_id}/rut", response_model=LenhKetQuaOut)
def go_phan_cong(
    phan_cong_id: int,
    body: GoPhanCongIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Rút một người khỏi công việc (§7.2), đóng khoảng tham gia đang mở của họ."""
    res = _chay(lambda: thuc_thi.go_phan_cong(
        db, user=user, phan_cong_id=phan_cong_id,
        ly_do=body.ly_do, expected_version=body.expected_version,
    ))
    _phat_sse(res)
    return res


@router.post("/work-items/{cong_viec_id}/material-requests",
             status_code=status.HTTP_201_CREATED, response_model=None)
def tao_de_nghi_vat_tu(
    cong_viec_id: int,
    body: VatTuDeNghiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("warehouse"))],
) -> dict:
    """Tổ đề nghị cấp vật tư cho công đoạn (spec-de-nghi-cap-vat-tu-cong-doan §6).

    Quyền Kho ở router chỉ là cổng THÔ — ranh giới thật (Kho ở đúng tổ của công việc) nằm trong
    service, giống hệt `phan-cong`. KHÔNG đòi `kho:request`: kho không duyệt yêu cầu này.
    """
    try:
        return vat_tu_de_nghi.tao(
            db, user=user, cong_viec_id=cong_viec_id, can_luc=body.can_luc,
            lines=[l.model_dump() for l in body.lines],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except (VatTuDeNghiError, StockRequestError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put("/work-items/{cong_viec_id}/material-requests/{de_nghi_id}", response_model=None)
def sua_de_nghi_vat_tu(
    cong_viec_id: int,
    de_nghi_id: int,
    body: VatTuDeNghiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("warehouse"))],
) -> dict:
    """`de_nghi_id` là id ĐỀ NGHỊ SẢN XUẤT, không phải id yêu cầu kho — đừng nhầm hai không gian id."""
    try:
        return vat_tu_de_nghi.sua(
            db, user=user, cong_viec_id=cong_viec_id, de_nghi_id=de_nghi_id,
            can_luc=body.can_luc, lines=[l.model_dump() for l in body.lines],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except (VatTuDeNghiError, StockRequestError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/work-items/{cong_viec_id}/bat-dau", response_model=LenhKetQuaOut)
def bat_dau(
    cong_viec_id: int,
    body: BatDauIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Bắt đầu / tiếp tục chạy (§7.2): mở phiên mới + khoảng tham gia cho cả tổ."""
    res = _chay(lambda: thuc_thi.bat_dau(
        db, user=user, cong_viec_id=cong_viec_id,
        expected_version=body.expected_version,
    ))
    _phat_sse(res)
    return res


@router.post("/work-items/{cong_viec_id}/nhan-khuon", response_model=LenhKetQuaOut)
def nhan_khuon(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Tổ xác nhận đã cầm con dao trong tay (chốt 04/09/2026) — thứ DUY NHẤT mở cổng Bắt đầu cho
    bước cần dụng cụ. Cùng cửa quyền với Bắt đầu: nói "dao đã ở đây" là quyết định điều hành."""
    res = _chay(lambda: thuc_thi.nhan_khuon(db, user=user, cong_viec_id=cong_viec_id))
    _phat_sse(res)
    return res


@router.post("/work-items/{cong_viec_id}/tra-khuon", response_model=LenhKetQuaOut)
def tra_khuon(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Trả dao về kệ — KHÔNG chặn gì, chỉ để hệ thống khỏi mất dấu con dao sau khi nó rời kệ."""
    res = _chay(lambda: thuc_thi.tra_khuon(db, user=user, cong_viec_id=cong_viec_id))
    _phat_sse(res)
    return res


@router.post("/work-items/{cong_viec_id}/doi-may", response_model=LenhKetQuaOut)
def doi_may(
    cong_viec_id: int,
    body: DoiMayIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Đổi máy giữa chừng (§7.2 mở rộng 31/08/2026). CÙNG cửa quyền với Bắt đầu
    (quyền Thực hiện lệnh ở CHÍNH tổ, siết ở `_gate`) — đổi máy là quyết định điều
    hành, không phải ghi nhận. Dùng `_chay` (như mọi route ghi khác ở đây) để `_gate` ném
    `PermissionError` cũng dịch ra 403 — không thì lệch đường dây so với `bat-dau`."""
    res = _chay(lambda: thuc_thi.doi_may(
        db, user=user, cong_viec_id=cong_viec_id,
        may_id_moi=body.may_id, ly_do=body.ly_do,
        expected_version=body.expected_version,
    ))
    _phat_sse(res)
    return res


@router.get("/work-items/{cong_viec_id}/may-doi", response_model=MayDoiOut)
def may_doi(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Ô "Đổi máy": máy làm được công đoạn của việc + tình trạng lúc này. CÙNG cửa quyền với
    `doi-may` — ai không đổi được máy thì cũng không cần danh sách này."""
    return _chay(lambda: thuc_thi.may_doi_duoc(db, user=user, cong_viec_id=cong_viec_id))


@router.post("/work-items/{cong_viec_id}/tam-dung", response_model=LenhKetQuaOut)
def tam_dung(
    cong_viec_id: int,
    body: TamDungIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Tạm dừng (§7.2): đóng phiên + khoảng tham gia. Bắt buộc lý do."""
    res = _chay(lambda: thuc_thi.tam_dung(
        db, user=user, cong_viec_id=cong_viec_id,
        ly_do=body.ly_do, expected_version=body.expected_version,
    ))
    _phat_sse(res)
    return res


@router.post("/work-items/{cong_viec_id}/su-co", response_model=SuCoKetQuaOut)
def bao_su_co(
    cong_viec_id: int,
    body: SuCoIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Báo sự cố máy ngay tại tổ (31/08/2026) → ghi vào hộp thư "Báo máy hỏng" của tổ sửa chữa.

    CÙNG cửa quyền với `tam-dung` (Thực hiện lệnh ở CHÍNH tổ, siết ở `_gate`): nhánh
    "Dừng sản xuất" chính là một cú tạm dừng, không thể dễ hơn.

    KHÔNG gọi `_phat_sse` ở đây — khác mọi route ghi bên trên: đường này phải đẩy HAI tin (bàn tổ
    + hàng chờ tổ sửa chữa) và cả hai chỉ hợp lệ SAU khi giao dịch chốt, nên `su_co.bao_su_co` tự
    bắn ngay sau `commit` của chính nó. Gọi thêm `_phat_sse` ở đây là bắn trùng tin bàn tổ.
    """
    return _chay(lambda: su_co.bao_su_co(
        db, user=user, cong_viec_id=cong_viec_id,
        bo_phan_hong=body.bo_phan_hong, mo_ta=body.mo_ta, muc_do=body.muc_do,
        dung_san_xuat=body.dung_san_xuat, expected_version=body.expected_version,
    ))


@router.post("/work-items/{cong_viec_id}/ket-thuc", response_model=LenhKetQuaOut)
def ket_thuc(
    cong_viec_id: int,
    body: KetThucIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Kết thúc (§7.2): đóng phiên + khoảng tham gia, đánh dấu hoàn thành."""
    res = _chay(lambda: thuc_thi.ket_thuc(
        db, user=user, cong_viec_id=cong_viec_id,
        expected_version=body.expected_version,
    ))
    _phat_sse(res)
    _thu_dong_nhom(db, res, user=user, su_kien="ket_thuc")
    return res


# --- Sản lượng (§11.1) + lot đầu vào (§10.3) -------------------------------------------------
@router.post("/work-items/{cong_viec_id}/outputs", response_model=SanLuongKetQuaOut)
def tao_batch(
    cong_viec_id: int,
    body: BatchIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Ghi một mẻ sản lượng + lot đầu vào (§11.1) + việc khoán & việc phát sinh (§7.1).

    Ràng buộc tổng = tốt + hỏng. Cấu hình Khoán tự lấy từ công đoạn; việc phát sinh KHÔNG cộng
    vào sản lượng nên không đụng gì tới ba con số trên."""
    res = _chay(lambda: san_luong.tao_batch(
        db, user=user, cong_viec_id=cong_viec_id,
        bat_dau=body.bat_dau, ket_thuc=body.ket_thuc,
        tong=body.tong, tot=body.tot, hong=body.hong, don_vi=body.don_vi,
        mo_ta_loi=body.mo_ta_loi, ghi_chu=body.ghi_chu,
        lot_vao=[lot.model_dump() for lot in body.lot_vao],
        phat_sinh=[ps.model_dump() for ps in body.phat_sinh],
    ))
    _phat_sse(res)
    return res


@router.post("/outputs/{batch_id}/cap-nhat-danh-muc", response_model=SanLuongKetQuaOut)
def cap_nhat_danh_muc_me(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Bấm "Cập nhật theo danh mục" trên băng của mẻ (§7.2b): ảnh chụp lấy số MỚI.

    Không có cửa ngược lại ("Giữ số cũ" là KHÔNG bấm gì) — hệ chưa bao giờ tự đổi số dưới chân mẻ
    đã ghi, nên không cần lệnh để giữ."""
    res = _chay(lambda: viec_khoan.cap_nhat_theo_danh_muc(db, user=user, batch_id=batch_id))
    _phat_sse(res)
    return res


@router.post("/outputs/{batch_id}/inputs", response_model=SanLuongKetQuaOut)
def them_lot(
    batch_id: int,
    body: ThemLotIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("run_order"))],
) -> dict:
    """Bổ sung một lot đầu vào cho batch đã tạo (§10.3 truy vết mẻ công đoạn trước)."""
    res = _chay(lambda: san_luong.them_lot(
        db, user=user, batch_id=batch_id,
        nguon_batch_id=body.nguon_batch_id, so_luong=body.so_luong, don_vi=body.don_vi,
    ))
    _phat_sse(res)
    return res


# --- Bàn giao công đoạn (§11.2–§11.3) --------------------------------------------------------
@router.post("/work-items/{cong_viec_id}/handovers", response_model=BanGiaoKetQuaOut)
def de_xuat_ban_giao(
    cong_viec_id: int,
    body: BanGiaoDeXuatIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Bên NGUỒN đề xuất giao sản lượng tốt sang công đoạn sau (§11.2). Cùng tổ+LSX ⇒ xác nhận luôn."""
    res = _chay(lambda: ban_giao.de_xuat(
        db, user=user, nguon_cong_viec_id=cong_viec_id,
        dich_cong_viec_id=body.dich_cong_viec_id, don_vi=body.don_vi, batch_ids=body.batch_ids,
    ))
    _phat_sse_ban_giao(res)
    return res


@router.post("/handovers/{ban_giao_id}/sua", response_model=BanGiaoKetQuaOut)
def sua_ban_giao(
    ban_giao_id: int,
    body: BanGiaoSuaIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Bên NGUỒN sửa lại mẻ đi theo lần giao khi còn chờ xác nhận (§11.2); số lượng tính lại."""
    res = _chay(lambda: ban_giao.sua_de_xuat(
        db, user=user, ban_giao_id=ban_giao_id,
        batch_ids=body.batch_ids, expected_version=body.expected_version,
    ))
    _phat_sse_ban_giao(res)
    return res


@router.post("/handovers/{ban_giao_id}/xac-nhan", response_model=BanGiaoKetQuaOut)
def xac_nhan_ban_giao(
    ban_giao_id: int,
    body: BanGiaoXacNhanIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Bên ĐÍCH xác nhận đúng con số cuối (§11.2)."""
    res = _chay(lambda: ban_giao.xac_nhan(
        db, user=user, ban_giao_id=ban_giao_id, expected_version=body.expected_version,
    ))
    _phat_sse_ban_giao(res)
    _thu_dong_nhom(db, res, user=user, su_kien="ban_giao_xac_nhan")
    return res


@router.post("/handovers/{ban_giao_id}/dieu-chinh", response_model=BanGiaoKetQuaOut)
def dieu_chinh_ban_giao(
    ban_giao_id: int,
    body: BanGiaoDieuChinhIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Điều chỉnh số lượng đã xác nhận (§11.3): đẻ dòng lịch sử, cờ không nhất quán nếu giảm quá."""
    res = _chay(lambda: ban_giao.dieu_chinh(
        db, user=user, ban_giao_id=ban_giao_id,
        so_luong_sau=body.so_luong_sau, mo_ta=body.mo_ta,
        expected_version=body.expected_version,
    ))
    _phat_sse_ban_giao(res)
    _thu_dong_nhom(db, res, user=user, su_kien="ban_giao_dieu_chinh")
    return res


# --- Xác nhận vật tư đã nhận (§10.1) ---------------------------------------------------------
@router.post("/stock/xac-nhan", response_model=VatTuNhanKetQuaOut)
def xac_nhan_vat_tu(
    body: VatTuXacNhanIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("warehouse"))],
) -> dict:
    """Người có quyền Kho ở tổ nhận xác nhận đã nhận vật tư của một phiếu xuất đã ghi sổ (§10.1)."""
    res = _chay(lambda: vat_tu_nhan.xac_nhan_vat_tu(
        db, user=user, voucher_id=body.voucher_id,
        department_id=body.department_id, ghi_chu=body.ghi_chu,
    ))
    _phat_sse_vat_tu(res)
    return res


@router.get("/teams/{team_id}/cho-xac-nhan", response_model=ChoXacNhanOut)
def cho_xac_nhan_cua_to(
    team_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_quyen_to("read"))],
) -> ChoXacNhanOut:
    """Việc chờ tổ bấm trên bàn `team_id`: bàn giao đến chờ nhận + thỏa thuận hỗ trợ chéo chờ bên
    tổ mình (kể cả khi tổ mình chỉ là tổ CHO MƯỢN người, không thấy công đoạn đó) + lỗi KCS chưa
    xem. Mỗi dòng mang `tren_ban` — bàn vẽ chấm đỏ trên dòng công đoạn hay liệt kê riêng.
    Chỉ tính tổ trong vùng mà user giữ Xác nhận sản lượng trọn tổ. 403 nếu bàn ngoài phạm vi xem."""
    try:
        return ChoXacNhanOut.model_validate(board.cho_xac_nhan(db, user, team_id=team_id))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

# --- Hỗ trợ chéo giữa hai tổ (§9) ------------------------------------------------------------
@router.post("/work-items/{cong_viec_id}/ho-tro", response_model=HoTroKetQuaOut)
def de_xuat_ho_tro(
    cong_viec_id: int,
    body: HoTroDeXuatIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Đề xuất một thỏa thuận hỗ trợ chéo (§9.1), đòi Xác nhận sản lượng. Bên còn lại xác nhận sau."""
    res = _chay(lambda: ho_tro.de_xuat_ho_tro(
        db, user=user, cong_viec_id=cong_viec_id,
        employee_id=body.employee_id, ngay_lam_viec=body.ngay_lam_viec,
        mo_ta=body.mo_ta,
    ))
    _phat_sse_ho_tro(res)
    return res


@router.post("/ho-tro/{ho_tro_id}/xac-nhan", response_model=HoTroKetQuaOut)
def xac_nhan_ho_tro(
    ho_tro_id: int,
    body: HoTroXacNhanIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Người có Xác nhận sản lượng ở bên còn lại xác nhận thỏa thuận (§9.1). Đủ hai bên → confirmed."""
    res = _chay(lambda: ho_tro.xac_nhan_ho_tro(
        db, user=user, ho_tro_id=ho_tro_id, expected_version=body.expected_version,
    ))
    _phat_sse_ho_tro(res)
    return res


@router.post("/ho-tro/{ho_tro_id}/huy", response_model=HoTroKetQuaOut)
def huy_ho_tro(
    ho_tro_id: int,
    body: HoTroHuyIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Huỷ thỏa thuận hỗ trợ (người giữ quyền Xác nhận ở một trong hai tổ) (§9.2)."""
    res = _chay(lambda: ho_tro.huy_ho_tro(
        db, user=user, ho_tro_id=ho_tro_id,
        ly_do=body.ly_do, expected_version=body.expected_version,
    ))
    _phat_sse_ho_tro(res)
    return res


# ⚠️ SÁU endpoint PHÂN BỔ (`/outputs/{id}/phan-bo` · `/phan-bo/{id}/chot` · `/mo-lai` ·
#    `/bu-tru` · `/loai-tru` · `/go-loai-tru`) GỠ 18/09/2026 cùng tầng chia sản lượng (mg
#    `0322`). Sản xuất CHỈ GHI NHẬN số lượng — chia và ra tiền là màn của kế toán lương.

# --- KCS theo LỆNH (mg 0306, docs/design-kcs-theo-lenh.md) -----------------------------------
# Người KCS = thành viên phòng ban `is_kcs`, kiểm được MỌI tổ — cổng nằm ở service (`kcs.gate_kcs`),
# router chỉ đòi đăng nhập. "Đã xem" lỗi gác Xác nhận sản lượng TRỌN tổ bị báo lỗi.
@router.get("/kcs/lenh", response_model=KcsLenhListOut)
def danh_sach_lenh_kcs(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    tim: str | None = Query(None, max_length=200),
    trang: int = Query(1, ge=1),
    da_dong: bool = Query(False),
) -> dict:
    """Danh sách lệnh cho màn KCS — lệnh đã vào nhóm thành phẩm, mặc định chỉ nhóm còn mở.
    Tìm + cắt trang ở máy chủ."""
    return _chay(lambda: kcs.danh_sach_lenh_kcs(db, user, tim=tim, trang=trang, gom_da_dong=da_dong))


@router.get("/kcs/lenh/{lsx_id}", response_model=KcsChuoiCongDoanOut)
def chuoi_cong_doan_kcs(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Chuỗi công đoạn của một lệnh theo thứ tự routing + các lần kiểm đã ghi."""
    try:
        return kcs.chuoi_cong_doan_kcs(db, user, lsx_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/work-items/{cong_viec_id}/kcs", response_model=KcsCongViecOut)
def ket_qua_kcs_cong_viec(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Mục "Kết quả KCS" của một công đoạn — người KCS xem mọi công đoạn, người khác theo phạm vi
    Xem của tổ."""
    try:
        return kcs.ket_qua_kcs_cong_viec(db, user, cong_viec_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/kcs/cong-viec/{cong_viec_id}/kiem", response_model=KcsKiemKetQuaOut,
             status_code=status.HTTP_201_CREATED)
def kiem_cong_doan(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    # Bỏ trống = form KCS chỉ gõ số lỗi, máy chủ suy số đạt (`kcs.kiem_cong_doan`).
    so_dat: float | None = Form(default=None),
    so_loi: float = Form(default=0),
    checklist_json: str | None = Form(default=None),
    ghi_chu: str | None = Form(default=None),
    loi_mo_ta: str | None = Form(default=None),
    # Lỗi theo DÒNG: JSON `[{cong_viec_id, so_luong, mo_ta, so_anh}]` — `files` nối theo đúng thứ
    # tự dòng, dòng i lấy `so_anh` tệp kế tiếp. Có trường này thì `loi_mo_ta` bị bỏ qua.
    loi_json: str | None = Form(default=None),
    lsx_id: int | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
) -> dict:
    """Ghi MỘT lần kiểm công đoạn (multipart vì lỗi đi kèm ảnh). Không trừ số, không đổi trạng thái
    công việc. Đẩy SSE tới người Xác nhận sản lượng của tổ bị kiểm và của tổ công đoạn trước bị
    quy lỗi."""
    try:
        checklist = json.loads(checklist_json) if checklist_json else None
        dong_loi = json.loads(loi_json) if loi_json else None
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kết quả tiêu chí hoặc dòng lỗi không hợp lệ.")
    if dong_loi is not None and (
        not isinstance(dong_loi, list) or not all(isinstance(r, dict) for r in dong_loi)
        or not all(isinstance(r.get("so_anh", 0), int) and r.get("so_anh", 0) >= 0 for r in dong_loi)
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dòng lỗi không hợp lệ.")
    if dong_loi is not None and sum(int(r.get("so_anh") or 0) for r in dong_loi) != len(files or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Số ảnh gửi lên không khớp các dòng lỗi.")
    # Cổng quyền TRƯỚC khi ghi ảnh — người ngoài tổ KCS không được để lại tệp rác trong kho lưu.
    _chay(lambda: kcs.gate_kcs(db, user))
    anh, keys = _luu_anh_kcs(cong_viec_id, files) if files else ([], [])
    cac_loi = None
    if dong_loi is not None:
        cac_loi, i = [], 0
        for r in dong_loi:
            n = int(r.get("so_anh") or 0)
            cac_loi.append({
                "cong_viec_id": r.get("cong_viec_id"), "so_luong": r.get("so_luong"),
                "mo_ta": r.get("mo_ta"), "anh": anh[i:i + n],
            })
            i += n
    try:
        res = kcs.kiem_cong_doan(
            db, user=user, cong_viec_id=cong_viec_id, so_dat=so_dat, so_loi=so_loi,
            checklist_ket_qua=checklist, ghi_chu=ghi_chu, loi_mo_ta=loi_mo_ta, anh=anh,
            cac_loi=cac_loi, lsx_id=lsx_id,
        )
    except PermissionError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _phat_sse_kcs(res)
    _thu_dong_nhom(db, res, user=user, su_kien="kcs_kiem")
    return res


@router.patch("/kcs/{kcs_batch_id}", response_model=KcsDieuChinhKetQuaOut)
def dieu_chinh_kcs(
    kcs_batch_id: int,
    body: KcsDieuChinhIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Điều chỉnh một lần kiểm đã ghi — không xoá, audit trước/sau, kiểm expected_version. Chặn
    khi đã có yêu cầu nhập kho chưa huỷ từ lần kiểm đó."""
    checklist_ket_qua = (
        [kq.model_dump() for kq in body.checklist_ket_qua] if body.checklist_ket_qua else None
    )
    res = _chay(lambda: kcs.dieu_chinh_ket_qua(
        db, user=user, kcs_batch_id=kcs_batch_id, so_luong_dat=body.so_luong_dat,
        so_luong_khong_dat=body.so_luong_khong_dat, checklist_ket_qua=checklist_ket_qua,
        ghi_chu=body.ghi_chu, expected_version=body.expected_version,
    ))
    _phat_sse_kcs(res)
    _thu_dong_nhom(db, res, user=user, su_kien="kcs_dieu_chinh")
    return res


@router.post("/kcs/loi/{loi_id}/da-xem", response_model=KcsDaXemKetQuaOut)
def da_xem_loi_kcs(
    loi_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("confirm_output"))],
) -> dict:
    """Tổ bị báo lỗi bấm "Đã xem". Gác Xác nhận sản lượng TRỌN tổ chịu ở service."""
    res = _chay(lambda: kcs.da_xem_loi(db, user=user, loi_id=loi_id))
    _phat_sse_kcs(res)
    return res


_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content, media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/kcs/cong-doan", response_model=KcsCongDoanLocListOut)
def cong_doan_loc_kcs(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(require_quyen_to("read", cho_kcs=True))],
) -> dict:
    """Danh mục công đoạn cho ô lọc dashboard KCS — cùng cổng Xem với `/kcs/bao-cao`, để người chỉ
    giữ quyền tổ không phải có quyền Danh mục công đoạn mới lọc được."""
    return {"items": kcs_bao_cao.cong_doan_loc(db)}


@router.get("/kcs/bao-cao", response_model=KcsBaoCaoOut)
def bao_cao_kcs(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_quyen_to("read", cho_kcs=True))],
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    lsx_id: int | None = Query(default=None),
    tu_khoa: str | None = Query(default=None),
    cong_doan_id: int | None = Query(default=None),
) -> dict:
    """Tổng hợp KCS theo filter + scope (§5.7, §6.2 KPI/biểu đồ). Đọc quyền `read` — xem báo cáo
    không cần quyền xuất file."""
    return kcs_bao_cao.bao_cao_kcs(
        db, user, authz, tu=tu, den=den,
        lsx_id=lsx_id, tu_khoa=tu_khoa, cong_doan_id=cong_doan_id,
    )


@router.get("/kcs/bao-cao/export.xlsx")
def export_bao_cao_kcs(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(get_current_user)],
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    lsx_id: int | None = Query(default=None),
    tu_khoa: str | None = Query(default=None),
    cong_doan_id: int | None = Query(default=None),
) -> Response:
    """Xuất Excel — người thuộc tổ KCS, hoặc vai có ô `san_xuat:export` (§4.4); KHÁC `read` của
    endpoint JSON ở trên. Dùng CHUNG hàm lấy dòng với `/kcs/bao-cao` (§9 mục 10: cùng filter phải
    trả cùng tổng)."""
    if not (authz.can(user, MODULE, "export") or kcs.la_nguoi_kcs(db, user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không có quyền thực hiện thao tác này")
    content, filename = kcs_bao_cao.xuat_excel_kcs(
        db, user, authz, tu=tu, den=den,
        lsx_id=lsx_id, tu_khoa=tu_khoa, cong_doan_id=cong_doan_id,
    )
    return _xlsx_response(content, filename)


# --- NHẬP KHO THÀNH PHẨM (yêu cầu nhập xuất của kho thật) -----------------------------------
# Kho nhận bằng phiếu nhập ở module Kho (`kho_voucher`), không còn endpoint xác nhận riêng ở đây.
KHO_MODULE = "kho"


@router.post("/kcs/cong-viec/{cong_viec_id}/yeu-cau-nhap-kho", response_model=NhapKhoYcKetQuaOut,
             status_code=status.HTTP_201_CREATED)
def tao_yeu_cau_nhap_kho_cong_doan(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """"Tạo yêu cầu nhập kho" trên công đoạn cuối nhóm — lập MỘT yêu cầu NHẬP của kho thật cho
    thành phẩm của cụm bán; server tự tính phần đạt chưa gửi, không nhận số từ client. Người thuộc
    tổ KCS. 409 nếu không còn số đạt chưa gửi. SSE (kho + màn KCS) phát trong service sau commit."""
    try:
        res = kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=user, cong_viec_id=cong_viec_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except kho.KhongConSoDuGuiKho as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _phat_sse_kcs(res)
    # Giá bán là TIỀN — chỉ người có `kho:view_cost` mới nhận (chủ 18/09/2026); người KCS bấm gửi
    # thì không, dù màn KCS không hiện số này.
    if not authz.can(user, KHO_MODULE, "view_cost"):
        res = {**res, "dong": [{**d, "don_gia_ban": None} for d in res.get("dong", [])]}
    return res


# --- ĐÓNG NHÓM THÀNH PHẨM (§16 tự đóng đủ · §13.3 đóng thiếu) -------------------------------
@router.get("/kho/nhom/{nhom_id}/dieu-kien-dong", response_model=DongNhomDieuKienOut)
def dieu_kien_dong_nhom(
    nhom_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_quyen_to("read", (KHO_MODULE, "read"), cho_kcs=True))],
) -> dict:
    """Checklist cổng đóng nhóm (§16): từng điều kiện đạt/chưa + đủ-đóng-đủ / đủ-đóng-thiếu để FE
    hiện "vì sao chưa đóng" và bật nút đóng thiếu."""
    return _chay(lambda: dong_nhom.dieu_kien_dong_nhom(db, nhom_id))


@router.post("/kho/nhom/{nhom_id}/dong-thieu", response_model=DongNhomKetQuaOut)
def dong_thieu_nhom(
    nhom_id: int,
    body: DongThieuIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Trưởng tổ KCS đóng THIẾU nhóm còn dở (§13.3): vẫn phải sạch mọi điều kiện toàn vẹn TRỪ hoàn
    thành. Ranh giới THẬT là trưởng phòng ban `is_kcs` ở service (403 nếu không phải).
    Báo Sale + Kế hoạch SX NGAY."""
    res = _chay(lambda: dong_nhom.dong_thieu(
        db, user=user, nhom_id=nhom_id, expected_version=body.expected_version,
    ))
    _phat_sse_dong_nhom(res)
    return res
