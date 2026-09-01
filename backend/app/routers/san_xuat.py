"""Router Thực hiện sản xuất — bàn của TỔ (Giai đoạn 2 mặt đọc + Giai đoạn 1 navbar node lá).

Prefix `/api/san-xuat`. RBAC tái dùng MODULE = "san_xuat" (không đẻ quyền mới): tổ trưởng có
quyền `read` trên module này + scope phòng/tổ mình; cấp xưởng scope `all` thấy mọi tổ.

Lát này CHỈ ĐỌC:
  · GET /teams        — danh sách tổ sản xuất (node lá) + badge số việc chờ, cho navbar + màn.
  · GET /work-items   — công việc ĐÃ PHÁT HÀNH của MỘT tổ (timeline), chặn nếu ngoài phạm vi.

Phân công / phiên chạy / sản lượng (ghi) là các lát sau, thêm bảng riêng.
"""
from __future__ import annotations

import json
from datetime import date, datetime
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
from ..deps import get_authorization_service, require_permission
from ..models.user import User
from ..realtime import hub
from ..repositories.san_xuat_repo import SanXuatRepository
from ..storage import get_storage, key_from_url, make_key, url_from_key
from ..schemas.san_xuat import (
    BanGiaoDeXuatIn,
    BanGiaoDieuChinhIn,
    BanGiaoKetQuaOut,
    BanGiaoSuaIn,
    BanGiaoXacNhanIn,
    BatchIn,
    BatDauIn,
    BuTruIn,
    BuTruKetQuaOut,
    DoiMayIn,
    DongNhomDieuKienOut,
    DongNhomKetQuaOut,
    DongThieuIn,
    GoPhanCongIn,
    HoTroDeXuatIn,
    HoTroHuyIn,
    HoTroKetQuaOut,
    HoTroXacNhanIn,
    KcsAnhThemKetQuaOut,
    KcsBaoCaoOut,
    KcsBatchIn,
    KcsBatchKetQuaOut,
    KcsChiTietOut,
    KcsDieuChinhIn,
    KcsDieuChinhKetQuaOut,
    KcsDotXuatKetQuaOut,
    KcsHopThuOut,
    KcsLoiKetQuaOut,
    KcsPhanHoiKetQuaOut,
    KcsPhanHoiLoiIn,
    KetThucIn,
    KhoChiTietOut,
    KhoHopThuOut,
    KhoXacNhanBtpKetQuaOut,
    KhoXacNhanNhapIn,
    KhoXacNhanNhapKetQuaOut,
    HuyPhanChuaNhanIn,
    LenhKetQuaOut,
    HoTroUngVienListOut,
    GoLoaiTruIn,
    LoaiTruIn,
    LoaiTruKetQuaOut,
    NhanVienChonListOut,
    NhapKhoYcKetQuaOut,
    NhapKhoYeuCauIn,
    PhanLoaiBtpIn,
    PhanLoaiBtpKetQuaOut,
    PhanBoChotIn,
    PhanBoMoLaiIn,
    PhanBoTomTatOut,
    PhanBoTrangThaiOut,
    PhanCongIn,
    SanLuongKetQuaOut,
    SuCoIn,
    SuCoKetQuaOut,
    TamDungIn,
    TeamsOut,
    ThemLotIn,
    VatTuDeNghiIn,
    VatTuNhanKetQuaOut,
    VatTuXacNhanIn,
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
    phan_bo,
    san_luong,
    su_co,
    thuc_thi,
    vat_tu_de_nghi,
    vat_tu_nhan,
)
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
    """Bàn giao đổi trạng thái → refresh CẢ hai bàn tổ (nguồn + đích) + đẩy tới người cần hành động."""
    for team in {res.get("nguon_department_id"), res.get("dich_department_id")}:
        if team:
            hub.broadcast({
                "type": "san_xuat_ban_giao_changed",
                "team_id": team,
                "ban_giao_id": res.get("ban_giao_id"),
                "trang_thai": res.get("trang_thai_ban_giao"),
            })
    uid = res.get("notify_user_id")
    if uid:
        hub.publish(uid, {
            "type": "san_xuat_ban_giao",
            "ban_giao_id": res.get("ban_giao_id"),
            "trang_thai": res.get("trang_thai_ban_giao"),
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
    """Thỏa thuận hỗ trợ đổi (§9) → refresh chỗ hiển thị + đẩy tới CẢ HAI tổ trưởng liên quan (§18)."""
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
        })


def _phat_sse_phan_bo(res: dict) -> None:
    """Phân bổ đổi (§12) → refresh bàn tổ thực hiện (bảng chia + trạng thái chốt)."""
    team = res.get("department_id")
    if team:
        hub.broadcast({
            "type": "san_xuat_phan_bo_changed",
            "team_id": team,
            "phan_bo_id": res.get("phan_bo_id"),
            "trang_thai": res.get("trang_thai"),
        })


def _phat_sse_kcs(res: dict, notify_uids: list[int | None] | None = None) -> None:
    """KCS đổi (§13) → refresh panel KCS + ĐẨY tới người cần hành động (§18): tổ trưởng phụ trách khi
    có lỗi mới, người ghi KCS khi lỗi được phản hồi. Lỗi KCS là tương tác GIỮA hai tổ nên phải tới
    NGAY, không bắt refresh."""
    hub.broadcast({
        "type": "san_xuat_kcs_changed",
        "cong_viec_id": res.get("cong_viec_id"),
        "kcs_batch_id": res.get("kcs_batch_id"),
        "loi_id": res.get("loi_id"),
        "trang_thai": res.get("trang_thai"),
        "team_id": res.get("kcs_department_id") or res.get("department_id"),
        "loai": res.get("loai"),
    })
    for uid in notify_uids or []:
        if uid:
            hub.publish(uid, {
                "type": "san_xuat_kcs_loi",
                "cong_viec_id": res.get("cong_viec_id"),
                "loi_id": res.get("loi_id"),
                "trang_thai": res.get("trang_thai"),
            })


def _phat_sse_kho(res: dict, notify_uids: list[int | None] | None = None) -> None:
    """Kho sản xuất đổi (§14) → refresh panel kho + hộp thư nhân viên kho, và ĐẨY tới người cần hành
    động (§17, §18): nhân viên kho khi có yêu cầu/BTP mới chờ nhận, người ghi KCS khi kho đã nhận.
    Nhập kho là tương tác GIỮA KCS và kho nên phải tới NGAY."""
    hub.broadcast({
        "type": "san_xuat_kho_changed",
        "nhom_id": res.get("nhom_id"),
        "yc_id": res.get("yc_id"),
        "lot_id": res.get("lot_id"),
        "trang_thai": res.get("trang_thai"),
    })
    for uid in notify_uids or []:
        if uid:
            hub.publish(uid, {
                "type": "san_xuat_kho",
                "nhom_id": res.get("nhom_id"),
                "yc_id": res.get("yc_id"),
                "lot_id": res.get("lot_id"),
                "trang_thai": res.get("trang_thai"),
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
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> TeamsOut:
    """Tổ sản xuất user được thấy + badge số việc chưa xong (navbar §2.1, màn bàn tổ §11)."""
    return TeamsOut(teams=board.teams(db, user, authz))


@router.get("/teams/{team_id}/nhan-vien", response_model=NhanVienChonListOut)
def nhan_vien_cua_to(
    team_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> NhanVienChonListOut:
    """Danh nhân viên chọn được để giao vào việc của tổ (ô "Giao người" §7.1). 403 nếu ngoài phạm vi.

    Gác bằng `san_xuat:read` (KHÔNG mượn `nhan_su`): tổ trưởng đổ được danh chọn của tổ mình mà
    không cần quyền nhân sự. Ghi thật vẫn do `phan-cong` gác `assign_work` + `_gate` đúng-tổ-trưởng.
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
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> HoTroUngVienListOut:
    """Ứng viên mời HỖ TRỢ CHÉO (§9) cho tổ: thợ ở các tổ SX khác. 403 nếu tổ ngoài phạm vi.

    Cùng gác `san_xuat:read` như ô "Giao người". Ghi thỏa thuận vẫn do `/work-items/{id}/ho-tro`
    gác `assign_work` + service kiểm đúng-tổ-trưởng.
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
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    team_id: int = Query(..., ge=1),
    mode: Literal["production", "kcs"] = Query("production"),
) -> WorkItemsOut:
    """Công việc đã phát hành của MỘT tổ, lọc theo `mode` (§18 /work-items, Task 4).
    403 nếu tổ ngoài phạm vi quyền."""
    try:
        return WorkItemsOut.model_validate(
            board.work_items(db, user, authz, team_id=team_id, mode=mode)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/work-items/{cong_viec_id}", response_model=WorkItemChiTietOut)
def work_item_detail(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
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


# --- Mặt GHI (§7.1–§7.2) --------------------------------------------------------------------
# Gác RBAC coarse bằng bit `assign_work` (tổ trưởng SX có đủ 3 bit); ranh giới an ninh THỰC là
# `_gate` đúng-tổ-trưởng ở service. Không có bit "chạy" riêng nên phiên chạy dùng chung bit này.
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Tổ đề nghị cấp vật tư cho công đoạn (spec-de-nghi-cap-vat-tu-cong-doan §6).

    Bit `assign_work` chỉ là cổng THÔ — ranh giới thật ("đúng tổ trưởng của tổ nào") nằm trong
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Bắt đầu / tiếp tục chạy (§7.2): mở phiên mới + khoảng tham gia cho cả tổ."""
    res = _chay(lambda: thuc_thi.bat_dau(
        db, user=user, cong_viec_id=cong_viec_id,
        ly_do_tre=body.ly_do_tre, ly_do_so_nguoi=body.ly_do_so_nguoi,
        expected_version=body.expected_version,
    ))
    _phat_sse(res)
    return res


@router.post("/work-items/{cong_viec_id}/doi-may", response_model=LenhKetQuaOut)
def doi_may(
    cong_viec_id: int,
    body: DoiMayIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Đổi máy giữa chừng (§7.2 mở rộng 31/08/2026). CÙNG cửa quyền với Bắt đầu
    (`can_assign_work` + tổ trưởng của CHÍNH tổ, siết ở `_gate`) — đổi máy là quyết định điều
    hành, không phải ghi nhận. Dùng `_chay` (như mọi route ghi khác ở đây) để `_gate` ném
    `PermissionError` cũng dịch ra 403 — không thì lệch đường dây so với `bat-dau`."""
    res = _chay(lambda: thuc_thi.doi_may(
        db, user=user, cong_viec_id=cong_viec_id,
        may_id_moi=body.may_id, ly_do=body.ly_do,
        expected_version=body.expected_version,
    ))
    _phat_sse(res)
    return res


@router.post("/work-items/{cong_viec_id}/tam-dung", response_model=LenhKetQuaOut)
def tam_dung(
    cong_viec_id: int,
    body: TamDungIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Báo sự cố máy ngay tại tổ (31/08/2026) → ghi vào hộp thư "Báo máy hỏng" của tổ sửa chữa.

    CÙNG cửa quyền với `tam-dung` (`assign_work` + tổ trưởng của CHÍNH tổ, siết ở `_gate`): nhánh
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Kết thúc (§7.2): đóng phiên + khoảng tham gia, đánh dấu hoàn thành."""
    res = _chay(lambda: thuc_thi.ket_thuc(
        db, user=user, cong_viec_id=cong_viec_id,
        ly_do_tre=body.ly_do_tre, expected_version=body.expected_version,
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Ghi một batch sản lượng + lot đầu vào (§11.1). Ràng buộc tổng = tốt + hỏng, hỏng cần nhóm lỗi."""
    res = _chay(lambda: san_luong.tao_batch(
        db, user=user, cong_viec_id=cong_viec_id,
        bat_dau=body.bat_dau, ket_thuc=body.ket_thuc,
        tong=body.tong, tot=body.tot, hong=body.hong, don_vi=body.don_vi,
        nhom_loi_id=body.nhom_loi_id, mo_ta_loi=body.mo_ta_loi, ghi_chu=body.ghi_chu,
        lot_vao=[lot.model_dump() for lot in body.lot_vao],
    ))
    _phat_sse(res)
    return res


@router.post("/outputs/{batch_id}/inputs", response_model=SanLuongKetQuaOut)
def them_lot(
    batch_id: int,
    body: ThemLotIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Bổ sung một lot đầu vào cho batch đã tạo (§10.3 truy vết nguyên liệu/BTP)."""
    res = _chay(lambda: san_luong.them_lot(
        db, user=user, batch_id=batch_id,
        nguon_loai=body.nguon_loai, nguon_batch_id=body.nguon_batch_id,
        nguon_lot_id=body.nguon_lot_id, so_luong=body.so_luong, don_vi=body.don_vi,
    ))
    _phat_sse(res)
    return res


# --- Bàn giao công đoạn (§11.2–§11.3) --------------------------------------------------------
@router.post("/work-items/{cong_viec_id}/handovers", response_model=BanGiaoKetQuaOut)
def de_xuat_ban_giao(
    cong_viec_id: int,
    body: BanGiaoDeXuatIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Bên NGUỒN đề xuất giao sản lượng tốt sang công đoạn sau (§11.2). Cùng tổ+LSX ⇒ xác nhận luôn."""
    res = _chay(lambda: ban_giao.de_xuat(
        db, user=user, nguon_cong_viec_id=cong_viec_id,
        dich_cong_viec_id=body.dich_cong_viec_id, so_luong=body.so_luong, don_vi=body.don_vi,
    ))
    _phat_sse_ban_giao(res)
    return res


@router.post("/handovers/{ban_giao_id}/sua", response_model=BanGiaoKetQuaOut)
def sua_ban_giao(
    ban_giao_id: int,
    body: BanGiaoSuaIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Bên NGUỒN sửa số lượng khi bàn giao còn chờ xác nhận (§11.2)."""
    res = _chay(lambda: ban_giao.sua_de_xuat(
        db, user=user, ban_giao_id=ban_giao_id,
        so_luong=body.so_luong, expected_version=body.expected_version,
    ))
    _phat_sse_ban_giao(res)
    return res


@router.post("/handovers/{ban_giao_id}/xac-nhan", response_model=BanGiaoKetQuaOut)
def xac_nhan_ban_giao(
    ban_giao_id: int,
    body: BanGiaoXacNhanIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Điều chỉnh số lượng đã xác nhận (§11.3): đẻ dòng lịch sử, cờ không nhất quán nếu giảm quá."""
    res = _chay(lambda: ban_giao.dieu_chinh(
        db, user=user, ban_giao_id=ban_giao_id,
        so_luong_sau=body.so_luong_sau, ly_do_id=body.ly_do_id, mo_ta=body.mo_ta,
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Tổ trưởng xác nhận đã nhận vật tư của một phiếu xuất đã ghi sổ, nguyên trạng (§10.1)."""
    res = _chay(lambda: vat_tu_nhan.xac_nhan_vat_tu(
        db, user=user, voucher_id=body.voucher_id,
        department_id=body.department_id, ghi_chu=body.ghi_chu,
    ))
    _phat_sse_vat_tu(res)
    return res


# --- Hỗ trợ chéo giữa hai tổ (§9) ------------------------------------------------------------
@router.post("/work-items/{cong_viec_id}/ho-tro", response_model=HoTroKetQuaOut)
def de_xuat_ho_tro(
    cong_viec_id: int,
    body: HoTroDeXuatIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Tổ trưởng đề xuất một thỏa thuận hỗ trợ chéo (§9.1). Bên còn lại xác nhận sau."""
    res = _chay(lambda: ho_tro.de_xuat_ho_tro(
        db, user=user, cong_viec_id=cong_viec_id,
        employee_id=body.employee_id, ngay_lam_viec=body.ngay_lam_viec,
        ty_le_phan_tram=body.ty_le_phan_tram, mo_ta=body.mo_ta,
    ))
    _phat_sse_ho_tro(res)
    return res


@router.post("/ho-tro/{ho_tro_id}/xac-nhan", response_model=HoTroKetQuaOut)
def xac_nhan_ho_tro(
    ho_tro_id: int,
    body: HoTroXacNhanIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Tổ trưởng bên còn lại xác nhận thỏa thuận (§9.1). Đủ hai bên → confirmed + kiểm trần ≤ 100%."""
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
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Huỷ thỏa thuận hỗ trợ (tổ trưởng một trong hai bên) (§9.2)."""
    res = _chay(lambda: ho_tro.huy_ho_tro(
        db, user=user, ho_tro_id=ho_tro_id,
        ly_do=body.ly_do, expected_version=body.expected_version,
    ))
    _phat_sse_ho_tro(res)
    return res


# --- Phân bổ sản lượng → lương khoán (§12) ---------------------------------------------------
@router.post("/outputs/{batch_id}/phan-bo", response_model=PhanBoTomTatOut)
def tinh_phan_bo(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Tính/refresh bản NHÁP phân bổ của một batch (§12.2). Phơi cảnh báo nếu chưa đủ điều kiện chốt."""
    res = _chay(lambda: phan_bo.tinh_phan_bo(db, user=user, batch_id=batch_id))
    _phat_sse_phan_bo(res)
    return res


@router.post("/phan-bo/{phan_bo_id}/chot", response_model=PhanBoTomTatOut)
def chot_phan_bo(
    phan_bo_id: int,
    body: PhanBoChotIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """CHỐT phân bổ (§12.3): tính lại nghiêm, chặn nếu thiếu hệ số/trọng số hoặc bàn giao không nhất quán."""
    res = _chay(lambda: phan_bo.chot_phan_bo(
        db, user=user, phan_bo_id=phan_bo_id, expected_version=body.expected_version,
    ))
    _phat_sse_phan_bo(res)
    _thu_dong_nhom(db, res, user=user, su_kien="phan_bo_chot")
    return res


@router.post("/phan-bo/{phan_bo_id}/mo-lai", response_model=PhanBoTrangThaiOut)
def mo_lai_phan_bo(
    phan_bo_id: int,
    body: PhanBoMoLaiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Mở lại phân bổ đã chốt để sửa (§12.3) — CHỈ khi kỳ lương chưa khoá. Bắt buộc lý do."""
    res = _chay(lambda: phan_bo.mo_lai_phan_bo(
        db, user=user, phan_bo_id=phan_bo_id,
        ly_do_id=body.ly_do_id, expected_version=body.expected_version,
    ))
    _phat_sse_phan_bo(res)
    return res


@router.post("/outputs/{batch_id}/bu-tru", response_model=BuTruKetQuaOut)
def bu_tru(
    batch_id: int,
    body: BuTruIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Đẻ dòng bù trừ sau khi kỳ lương gốc đã khoá (§12.3): ghi chênh lệch vào kỳ bù đang mở."""
    res = _chay(lambda: phan_bo.bu_tru(
        db, user=user, batch_id=batch_id, employee_id=body.employee_id,
        so_luong_tra_luong=body.so_luong_tra_luong,
        ky_bu_nam=body.ky_bu_nam, ky_bu_thang=body.ky_bu_thang,
        ly_do_id=body.ly_do_id, mo_ta=body.mo_ta,
    ))
    _phat_sse_phan_bo({
        "department_id": res.get("department_id"),
        "phan_bo_id": None,
        "trang_thai": "bu_tru",
    })
    return res


@router.post("/outputs/{batch_id}/loai-tru", response_model=LoaiTruKetQuaOut)
def loai_tru_khoi_phan_bo(
    batch_id: int,
    body: LoaiTruIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Loại một người khỏi lương của batch kèm lý do (§7.3): xử lý người tham gia nhưng thiếu chấm
    công hợp lệ. Engine bỏ họ khỏi vòng chia + cờ 'thiếu chấm công' tan → cho chốt."""
    res = _chay(lambda: phan_bo.loai_tru_khoi_phan_bo(
        db, user=user, batch_id=batch_id, employee_id=body.employee_id, ly_do=body.ly_do,
    ))
    _phat_sse_phan_bo(res)
    return res


@router.post("/outputs/{batch_id}/go-loai-tru", response_model=LoaiTruKetQuaOut)
def go_loai_tru(
    batch_id: int,
    body: GoLoaiTruIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Gỡ loại trừ (§7.3): trả người này về vòng chia lại (cờ chặn chốt có thể nổi lên lại)."""
    res = _chay(lambda: phan_bo.go_loai_tru(
        db, user=user, batch_id=batch_id, employee_id=body.employee_id,
    ))
    _phat_sse_phan_bo(res)
    return res


# --- KCS: batch kiểm tra · lỗi · phản hồi trách nhiệm (Giai đoạn 5, §13) ---------------------
# Cùng bit `assign_work`; ranh giới an ninh THỰC ở service: ghi batch/lỗi gác đúng-tổ-trưởng-KCS
# (`_gate`), còn phản hồi trách nhiệm gác đúng-tổ-trưởng-tổ-BỊ-yêu-cầu (`_gate_to`) — KHÁC tổ KCS.
@router.get("/work-items/{cong_viec_id}/kcs", response_model=KcsChiTietOut)
def chi_tiet_kcs(
    cong_viec_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Batch kiểm tra + lỗi + ảnh của MỘT công việc KCS (panel drawer §13). 403 nếu ngoài PHẠM VI
    ĐỌC — cùng phạm vi với `GET /work-items/{id}`, không đòi phải là tổ trưởng tổ đó."""
    try:
        return kcs.chi_tiet_kcs(db, user, authz, cong_viec_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/kcs/hop-thu", response_model=KcsHopThuOut)
def hop_thu_loi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Hộp thư lỗi KCS đang CHỜ phản hồi gửi tới các tổ mà user làm tổ trưởng (§13.2)."""
    return {"loi": kcs.hop_thu_loi(db, user)}


@router.post("/work-items/{cong_viec_id}/kcs", response_model=KcsBatchKetQuaOut)
def tao_batch_kcs(
    cong_viec_id: int,
    body: KcsBatchIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Ghi một batch kiểm tra KCS (§13.1): số nhận = đạt + không đạt; đẻ kèm batch sản lượng nền cho
    phân bổ năng suất KCS. Chỉ công việc KCS đã bắt đầu."""
    checklist_ket_qua = (
        [kq.model_dump() for kq in body.checklist_ket_qua] if body.checklist_ket_qua else None
    )
    res = _chay(lambda: kcs.tao_batch_kcs(
        db, user=user, cong_viec_id=cong_viec_id,
        bat_dau=body.bat_dau, ket_thuc=body.ket_thuc,
        so_luong_nhan=body.so_luong_nhan, so_luong_dat=body.so_luong_dat,
        so_luong_khong_dat=body.so_luong_khong_dat, co_mau=body.co_mau,
        don_vi=body.don_vi, ghi_chu=body.ghi_chu, checklist_ket_qua=checklist_ket_qua,
    ))
    _phat_sse_kcs(res)
    return res


@router.post("/kcs/{kcs_batch_id}/loi", response_model=KcsLoiKetQuaOut,
             status_code=status.HTTP_201_CREATED)
def ghi_loi_kcs(
    kcs_batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
    nhom_loi_id: int = Form(...),
    to_chiu_id: int | None = Form(default=None),
    cong_doan_ref_id: int | None = Form(default=None),
    so_luong: float = Form(default=0),
    mo_ta: str | None = Form(default=None),
    don_vi: str | None = Form(default=None),
    files: list[UploadFile] = File(...),
) -> dict:
    """Ghi MỘT lỗi phát hiện trong batch KCS (§13.2) + ≥1 ảnh bằng chứng (bắt buộc, gửi kèm multipart).
    Đẩy SSE tới tổ trưởng tổ bị yêu cầu nhận trách nhiệm."""
    anh, keys = _luu_anh_kcs(kcs_batch_id, files)
    try:
        res = kcs.ghi_loi(
            db, user=user, kcs_batch_id=kcs_batch_id, nhom_loi_id=nhom_loi_id,
            mo_ta=mo_ta, to_chiu_id=to_chiu_id, cong_doan_ref_id=cong_doan_ref_id,
            so_luong=so_luong, don_vi=don_vi, anh=anh,
        )
    except PermissionError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _phat_sse_kcs(res, notify_uids=[res.get("to_chiu_head_user_id")])
    return res


@router.post("/kcs/dot-xuat", response_model=KcsDotXuatKetQuaOut, status_code=status.HTTP_201_CREATED)
def tao_kiem_dot_xuat(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
    cong_viec_id: int = Form(...),
    kcs_department_id: int = Form(...),
    bat_dau: datetime = Form(...),
    ket_thuc: datetime = Form(...),
    so_luong_nhan: float = Form(...),
    so_luong_dat: float = Form(...),
    so_luong_khong_dat: float = Form(default=0),
    co_mau: float | None = Form(default=None),
    don_vi: str | None = Form(default=None),
    ghi_chu: str | None = Form(default=None),
    checklist_ket_qua_json: str | None = Form(default=None),
    nhom_loi_id: int | None = Form(default=None),
    loi_mo_ta: str | None = Form(default=None),
    to_chiu_id: int | None = Form(default=None),
    cong_doan_ref_id: int | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
) -> dict:
    """KCS KIÊM NHIỆM (mg 0250): tổ SX khác kiểm đột xuất một việc đang chạy/tạm dừng, không đứng
    sẵn trong routing. Multipart vì có thể kèm ảnh lỗi NGAY một lượt (khác routing tách hai bước)."""
    try:
        checklist_ket_qua = json.loads(checklist_ket_qua_json) if checklist_ket_qua_json else None
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "checklist_ket_qua_json không hợp lệ.")
    anh, keys = _luu_anh_kcs(cong_viec_id, files) if files else ([], [])
    try:
        res = kcs.tao_kiem_dot_xuat(
            db, user=user, cong_viec_id=cong_viec_id, kcs_department_id=kcs_department_id,
            bat_dau=bat_dau, ket_thuc=ket_thuc, so_luong_nhan=so_luong_nhan,
            so_luong_dat=so_luong_dat, so_luong_khong_dat=so_luong_khong_dat, co_mau=co_mau,
            don_vi=don_vi, ghi_chu=ghi_chu, checklist_ket_qua=checklist_ket_qua,
            nhom_loi_id=nhom_loi_id, loi_mo_ta=loi_mo_ta, to_chiu_id=to_chiu_id,
            cong_doan_ref_id=cong_doan_ref_id, anh=anh,
        )
    except PermissionError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _phat_sse_kcs(res)
    return res


@router.post("/kcs/loi/{loi_id}/anh", response_model=KcsAnhThemKetQuaOut,
             status_code=status.HTTP_201_CREATED)
def them_anh_loi_kcs(
    loi_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
    files: list[UploadFile] = File(...),
) -> dict:
    """Bổ sung ảnh bằng chứng cho một lỗi KCS đã ghi (§13.2)."""
    anh, keys = _luu_anh_kcs(loi_id, files)
    try:
        return kcs.them_anh_loi(db, user=user, loi_id=loi_id, anh=anh)
    except PermissionError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        _don_anh(keys)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/kcs/anh/{anh_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response)
def xoa_anh_loi_kcs(
    anh_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> Response:
    """Xoá MỘT ảnh bằng chứng nhưng GIỮ ≥1 ảnh/lỗi (§13.2). Xoá cả file trong storage."""
    res = _chay(lambda: kcs.xoa_anh_loi(db, user=user, anh_id=anh_id))
    key = key_from_url(res.get("file_url"))
    if key:
        get_storage().delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/kcs/loi/{loi_id}/phan-hoi", response_model=KcsPhanHoiKetQuaOut)
def phan_hoi_loi_kcs(
    loi_id: int,
    body: KcsPhanHoiLoiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Tổ trưởng tổ BỊ yêu cầu CHẤP NHẬN/TỪ CHỐI trách nhiệm lỗi (§13.2, chung thẩm). Đẩy SSE tới
    người ghi KCS. Từ chối bắt buộc lý do."""
    res = _chay(lambda: kcs.phan_hoi_loi(
        db, user=user, loi_id=loi_id, chap_nhan=body.chap_nhan,
        ly_do_tu_choi=body.ly_do_tu_choi, expected_version=body.expected_version,
    ))
    _phat_sse_kcs(res, notify_uids=[res.get("nguoi_ghi_id")])
    _thu_dong_nhom(db, res, user=user, su_kien="kcs_phan_hoi_loi")
    return res


@router.patch("/kcs/{kcs_batch_id}", response_model=KcsDieuChinhKetQuaOut)
def dieu_chinh_kcs(
    kcs_batch_id: int,
    body: KcsDieuChinhIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Điều chỉnh kết quả batch KCS đã ghi (§4.3, §5.5) — không xoá, ghi audit trước/sau, kiểm
    expected_version. Chặn khi kho đã đụng vào (xác nhận dù một phần) hoặc còn yêu cầu chưa hủy."""
    checklist_ket_qua = (
        [kq.model_dump() for kq in body.checklist_ket_qua] if body.checklist_ket_qua else None
    )
    res = _chay(lambda: kcs.dieu_chinh_ket_qua(
        db, user=user, kcs_batch_id=kcs_batch_id, so_luong_dat=body.so_luong_dat,
        so_luong_khong_dat=body.so_luong_khong_dat, checklist_ket_qua=checklist_ket_qua,
        ghi_chu=body.ghi_chu, expected_version=body.expected_version,
    ))
    _phat_sse_kcs(res)
    return res


_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content, media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/kcs/bao-cao", response_model=KcsBaoCaoOut)
def bao_cao_kcs(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    kcs_department_id: int | None = Query(default=None),
    lsx_id: int | None = Query(default=None),
    tu_khoa: str | None = Query(default=None),
    cong_doan_id: int | None = Query(default=None),
    loai: str | None = Query(default=None),
    nhom_loi_id: int | None = Query(default=None),
) -> dict:
    """Tổng hợp KCS theo filter + scope (§5.7, §6.2 KPI/biểu đồ). Đọc quyền `read` — xem báo cáo
    không cần quyền xuất file."""
    return kcs_bao_cao.bao_cao_kcs(
        db, user, authz, tu=tu, den=den, kcs_department_id=kcs_department_id,
        lsx_id=lsx_id, tu_khoa=tu_khoa, cong_doan_id=cong_doan_id, loai=loai,
        nhom_loi_id=nhom_loi_id,
    )


@router.get("/kcs/bao-cao/export.xlsx")
def export_bao_cao_kcs(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "export"))],
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    kcs_department_id: int | None = Query(default=None),
    lsx_id: int | None = Query(default=None),
    tu_khoa: str | None = Query(default=None),
    cong_doan_id: int | None = Query(default=None),
    loai: str | None = Query(default=None),
    nhom_loi_id: int | None = Query(default=None),
) -> Response:
    """Xuất Excel — gác riêng `export` (§4.4), KHÁC `read` của endpoint JSON ở trên. Dùng CHUNG
    hàm lấy dòng với `/kcs/bao-cao` (§9 mục 10: cùng filter phải trả cùng tổng)."""
    content, filename = kcs_bao_cao.xuat_excel_kcs(
        db, user, authz, tu=tu, den=den, kcs_department_id=kcs_department_id,
        lsx_id=lsx_id, tu_khoa=tu_khoa, cong_doan_id=cong_doan_id, loai=loai,
        nhom_loi_id=nhom_loi_id,
    )
    return _xlsx_response(content, filename)


# --- KHO SẢN XUẤT (§14) ---------------------------------------------------------------------
# Bên KCS/tổ (tạo yêu cầu, phân loại BTP, huỷ phần chưa nhận) gate `assign_work` + ranh giới THẬT là
# `_gate` đúng-tổ-trưởng ở service. Bên KHO (xác nhận nhận) gate module RIÊNG "kho" — nhân viên kho
# không phải tổ trưởng SX (khớp `kho_request.receive`).
KHO_MODULE = "kho"


@router.get("/kho/hop-thu", response_model=KhoHopThuOut)
def hop_thu_kho(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(KHO_MODULE, "read"))],
) -> dict:
    """Hộp thư nhân viên kho: yêu cầu nhập kho thành phẩm chờ/một phần + BTP `nhập kho BTP` chờ nhận (§14, §17)."""
    return kho.hop_thu_kho(db)


@router.get("/kho/nhom/{nhom_id}", response_model=KhoChiTietOut)
def chi_tiet_kho_nhom(
    nhom_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Toàn cảnh kho của một nhóm thành phẩm cho panel §14 (yêu cầu nhập kho + lot + BTP đã phân loại)."""
    return kho.chi_tiet_kho_nhom(db, nhom_id)


@router.post("/kho/yeu-cau-nhap", response_model=NhapKhoYcKetQuaOut,
             status_code=status.HTTP_201_CREATED)
def tao_yeu_cau_nhap_thanh_pham(
    body: NhapKhoYeuCauIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """KCS tạo yêu cầu nhập kho thành phẩm một phần từ một batch ĐẠT (§14.1). Tổng yêu cầu ≤ số KCS đã
    chấp nhận. Broadcast để nhân viên kho thấy ngay trong hộp thư."""
    res = _chay(lambda: kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=user, kcs_batch_id=body.kcs_batch_id, so_luong=body.so_luong,
        quy_cach=body.quy_cach, ghi_chu=body.ghi_chu,
    ))
    _phat_sse_kho(res)
    return res


@router.post("/kcs/{kcs_batch_id}/yeu-cau-nhap-kho", response_model=NhapKhoYcKetQuaOut,
             status_code=status.HTTP_201_CREATED)
def tao_yeu_cau_kho_mot_nut(
    kcs_batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Gửi kho MỘT NÚT (§5.6) — server tự tính số đạt chưa gửi, không nhận số từ client. Chỉ batch
    routing + công việc KCS cuối. 409 nếu không còn số đạt chưa gửi."""
    try:
        res = kho.tao_yeu_cau_kho_mot_nut(db, user=user, kcs_batch_id=kcs_batch_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except kho.KhongConSoDuGuiKho as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _phat_sse_kho(res)
    return res


@router.post("/kho/yeu-cau/{yc_id}/xac-nhan", response_model=KhoXacNhanNhapKetQuaOut)
def kho_xac_nhan_nhap(
    yc_id: int,
    body: KhoXacNhanNhapIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(KHO_MODULE, "create"))],
) -> dict:
    """Kho xác nhận nhận một phần yêu cầu nhập kho (§14.1) → đẻ lot thành phẩm MANG KHO ĐÍCH, khoá
    phần đã nhận. Đẩy SSE tới người ghi KCS (đã nhận đến đâu)."""
    res = _chay(lambda: kho.kho_xac_nhan_nhap(
        db, user=user, yc_id=yc_id, so_luong=body.so_luong, kho_id=body.kho_id,
        expected_version=body.expected_version,
    ))
    _phat_sse_kho(res, notify_uids=[res.get("nguoi_tao_id")])
    return res


@router.post("/kho/yeu-cau/{yc_id}/huy-phan-con-lai", response_model=NhapKhoYcKetQuaOut)
def huy_phan_chua_nhan(
    yc_id: int,
    body: HuyPhanChuaNhanIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """KCS huỷ PHẦN CHƯA NHẬN của yêu cầu để phân loại lại (§14.1). Phần kho đã xác nhận giữ nguyên."""
    res = _chay(lambda: kho.huy_phan_chua_nhan(
        db, user=user, yc_id=yc_id, expected_version=body.expected_version,
    ))
    _phat_sse_kho(res)
    return res


@router.post("/kho/btp/phan-loai", response_model=PhanLoaiBtpKetQuaOut,
             status_code=status.HTTP_201_CREATED)
def phan_loai_btp_du(
    body: PhanLoaiBtpIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Phân loại BTP dư của một công việc trước khi đóng nhóm (§14.2): nhập kho BTP / mẫu lưu / phế.
    `nhập kho BTP` broadcast để nhân viên kho thấy chờ xác nhận nhận."""
    res = _chay(lambda: kho.phan_loai_btp_du(
        db, user=user, cong_viec_id=body.cong_viec_id, so_luong=body.so_luong,
        phan_loai=body.phan_loai, quy_cach=body.quy_cach,
        nguon_batch_id=body.nguon_batch_id, ghi_chu=body.ghi_chu,
    ))
    _phat_sse_kho(res)
    return res


@router.post("/kho/lot/{lot_id}/xac-nhan-btp", response_model=KhoXacNhanBtpKetQuaOut)
def kho_xac_nhan_btp(
    lot_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(KHO_MODULE, "create"))],
) -> dict:
    """Kho xác nhận đã NHẬN BTP `nhập kho BTP` vào kho (§14.2) → gỡ chặn đóng nhóm (§16). Đẩy SSE tới
    tổ đã phân loại."""
    res = _chay(lambda: kho.kho_xac_nhan_btp(db, user=user, lot_id=lot_id))
    _phat_sse_kho(res, notify_uids=[res.get("nguoi_phan_loai_id")])
    _thu_dong_nhom(db, res, user=user, su_kien="kho_xac_nhan_btp")
    return res


# --- ĐÓNG NHÓM THÀNH PHẨM (§16 tự đóng đủ · §13.3 đóng thiếu) -------------------------------
@router.get("/kho/nhom/{nhom_id}/dieu-kien-dong", response_model=DongNhomDieuKienOut)
def dieu_kien_dong_nhom(
    nhom_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Checklist cổng đóng nhóm (§16): từng điều kiện đạt/chưa + đủ-đóng-đủ / đủ-đóng-thiếu để FE
    hiện "vì sao chưa đóng" và bật nút đóng thiếu."""
    return _chay(lambda: dong_nhom.dieu_kien_dong_nhom(db, nhom_id))


@router.post("/kho/nhom/{nhom_id}/dong-thieu", response_model=DongNhomKetQuaOut)
def dong_thieu_nhom(
    nhom_id: int,
    body: DongThieuIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
) -> dict:
    """Trưởng KCS đóng THIẾU nhóm còn dở (§13.3): bắt buộc lý do nhóm `dong_thieu`, vẫn phải sạch mọi
    điều kiện toàn vẹn TRỪ hoàn thành. Ranh giới THẬT là tổ-trưởng-KCS ở service (403 nếu không phải).
    Báo Sale + Kế hoạch SX NGAY."""
    res = _chay(lambda: dong_nhom.dong_thieu(
        db, user=user, nhom_id=nhom_id, ly_do_id=body.ly_do_id,
        expected_version=body.expected_version,
    ))
    _phat_sse_dong_nhom(res)
    return res
