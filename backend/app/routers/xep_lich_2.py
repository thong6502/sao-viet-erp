"""Router Xếp lịch công đoạn 2 — cửa vào THỨ HAI cho cùng một lịch xưởng (`xep_lich_cong_doan`).

Prefix `/api/xep-lich-2`. RBAC MODULE RIÊNG = "xep_lich_2" (mg 0218 chép quyền từ `xep_lich` sang,
gồm cả hai bit `approve` phát hành + `approve_exception`). Hai màn DÙNG CHUNG một bảng lịch: luật
xếp / phát hành ở đây do engine v2 (`services/xep_lich_2`) quyết, còn màn cũ vẫn chạy song song.

Luồng: LSX / bài ghép cần xếp nằm ở `/hang-cho` (chia rổ xếp-được / bị-chặn-vật-tư) → `POST /dua-vao/*`
sinh dòng NHÁP (cho phép thiếu vật tư) → `GET /dong/{id}/xem-truoc` soi trước khi ghi → `PUT /dong/{id}`
ghi (khóa lạc quan theo `updated_at`, chặn theo luật đặt lịch) → `GET /kiem-phat-hanh` rồi
`POST /phat-hanh/*` (cửa vật tư dùng chung). Router CHỈ điều phối + kiểm quyền + đẩy SSE.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..models.xep_lich import NGUON_IN_GHEP, NGUON_LSX
from ..realtime import hub
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.xep_lich_2_repo import XepLich2Repository
from ..schemas.xep_lich_2 import DuyetNgoaiLeIn, LuuIn, PhatHanhCapNhatIn
from ..services.xep_lich_2 import (
    XepLich2Blocked,
    XepLich2Conflict,
    XepLich2Error,
    XepLich2Service,
)
from ..services.xep_lich_service import (
    XepLichConflict,
    XepLichNotFound,
    XepLichValidationError,
)

router = APIRouter(prefix="/api/xep-lich-2", tags=["xep-lich-2"])
MODULE = "xep_lich_2"


def _svc(db: Session) -> XepLich2Service:
    return XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))


def _map(exc: Exception) -> HTTPException:
    """Ánh xạ lỗi nghiệp vụ (v2 + engine cũ được ủy thác) sang HTTP. Không nuốt lỗi lạ — re-raise."""
    if isinstance(exc, XepLich2Blocked):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"loai": "chan_dat_lich", "van_de": exc.van_de},
        )
    if isinstance(exc, (XepLich2Conflict, XepLichConflict)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, XepLichNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (XepLich2Error, XepLichValidationError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


# --- Hàng chờ + bàn làm việc (CHỈ ĐỌC) --------------------------------------
@router.get("/hang-cho", response_model=None)
def hang_cho(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    trang: int = Query(1, ge=1, description="Trang hàng chờ (cắt trang ở máy chủ)"),
    moi_trang: int = Query(50, ge=1, le=200, description="Số dòng mỗi trang"),
    q: str | None = Query(None, description="Tìm theo mã LSX/bài ghép (lọc ở máy chủ)"),
    loc: str = Query("all", pattern="^(all|tre|gap)$", description="Chip lọc: tất cả / trễ hạn / gấp"),
) -> dict:
    """LSX / bài ghép cần xếp, chia hai rổ `xep_duoc` / `bi_chan` (thiếu vật tư), cờ gấp nổi lên.

    Cắt trang + lọc + đếm Ở MÁY CHỦ: trả thêm `tong` / `so_trang` / `trang` (khớp kết quả lọc) và
    `facets` (đếm cả hàng chờ theo chip); mỗi dòng kèm `han_giao` + `so_cong_doan_chua_xep`."""
    return _svc(db).queue(trang=trang, moi_trang=moi_trang, q=q, loc=loc)


@router.get("/ban-lam-viec", response_model=None)
def ban_lam_viec(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tu: date = Query(..., description="Ngày đầu cửa sổ"),
    den: date = Query(..., description="Ngày cuối cửa sổ"),
) -> dict:
    """Một bàn [tu, den]: ca nền + ngày lễ (tô nền, vẫn xếp được) + các dòng đã xếp trong cửa sổ."""
    return _svc(db).workspace(tu=tu, den=den)


@router.get("/boi-canh/{nguon}/{id}", response_model=None)
def boi_canh(
    nguon: str,
    id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Dữ liệu Panel phải cho MỘT lệnh/bài: đầu thực thể + hai hạn + đệm + vật tư + vấn đề + chuỗi DAG
    (thời lượng ba mức, máy/tổ/NCC, số người & định biên, quân số & phần rảnh). CHỈ ĐỌC.

    `nguon` ∈ `lsx` | `in_ghep`. Không thấy lệnh/bài ⇒ 404; nguồn sai ⇒ 400 (qua `_map`)."""
    try:
        return _svc(db).boi_canh(nguon=nguon, id=id)
    except Exception as exc:
        raise _map(exc)


# --- Đưa vào kế hoạch (nháp — cho phép thiếu vật tư) -------------------------
@router.post("/dua-vao/lsx/{lsx_id}", status_code=status.HTTP_201_CREATED, response_model=None)
def dua_vao_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.tao_nhap(nguon=NGUON_LSX, id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return {"ok": True}


@router.post("/dua-vao/bai-ghep/{bai_ghep_id}", status_code=status.HTTP_201_CREATED, response_model=None)
def dua_vao_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> dict:
    svc = _svc(db)
    try:
        svc.tao_nhap(nguon=NGUON_IN_GHEP, id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return {"ok": True}


# --- Xoá nháp (bỏ một lệnh/bài ra khỏi kế hoạch) ----------------------------
@router.delete("/dua-vao/lsx/{lsx_id}", response_model=None)
def xoa_nhap_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Bỏ một LSX ra khỏi kế hoạch nháp — xoá các dòng nháp, đưa lệnh về SẴN SÀNG. Đã phát hành /
    đang khoá thì engine cũ chặn (409). Cùng quyền `update` với sửa một dòng."""
    svc = _svc(db)
    try:
        svc.xoa_nhap(nguon=NGUON_LSX, id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return {"ok": True}


@router.delete("/dua-vao/bai-ghep/{bai_ghep_id}", response_model=None)
def xoa_nhap_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    """Bỏ một bài ghép ra khỏi kế hoạch nháp — xoá các dòng nháp, đưa bài về SẴN SÀNG (409 nếu đã
    phát hành / đang khoá)."""
    svc = _svc(db)
    try:
        svc.xoa_nhap(nguon=NGUON_IN_GHEP, id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return {"ok": True}


# --- Xem trước + gợi ý (CHỈ ĐỌC, KHÔNG ghi, KHÔNG broadcast) -----------------
@router.get("/dong/{dong_id}/xem-truoc", response_model=None)
def xem_truoc(
    dong_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    may_id: int | None = Query(default=None),
    department_id: int | None = Query(default=None),
    nha_cung_cap: str | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
) -> dict:
    """Tính thử một cách đặt (máy/tổ/giờ) → giờ kết thúc liên tục + danh sách vấn đề. Không ghi gì.

    Dùng GET (không POST) đúng vì hàm KHÔNG mutate: mọi route ghi của màn này đều phải đẩy SSE, còn
    xem-trước thì không được đẩy — tách bằng phương thức cho rạch ròi."""
    patch: dict = {}
    if may_id is not None:
        patch["may_id"] = may_id
    if department_id is not None:
        patch["department_id"] = department_id
    if nha_cung_cap is not None:
        patch["nha_cung_cap"] = nha_cung_cap
    if start_at is not None:
        patch["start_at"] = start_at
    try:
        return _svc(db).xem_truoc(dong_id=dong_id, patch=patch)
    except Exception as exc:
        raise _map(exc)


@router.get("/dong/{dong_id}/goi-y", response_model=None)
def goi_y(
    dong_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> dict:
    """Gợi ý máy cùng nhóm công đoạn (không lọc theo khổ/màu/định lượng — người quyết). CHỈ ĐỌC."""
    try:
        return _svc(db).goi_y(dong_id=dong_id)
    except Exception as exc:
        raise _map(exc)


@router.get("/dong/{dong_id}/goi-y-khe", response_model=None)
def goi_y_khe(
    dong_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tu: date = Query(..., description="Ngày đầu cửa sổ tìm khe"),
    den: date = Query(..., description="Ngày cuối cửa sổ tìm khe"),
) -> dict:
    """Chấm tối đa 3 khe trống SỚM NHẤT để xếp dòng trong [tu, den] (B8) — người bấm một phát là xong.

    Chưa chọn máy / chưa tính được thời lượng ⇒ `khe` rỗng kèm `ghi_chu` nói thiếu gì. CHỈ ĐỌC."""
    try:
        return _svc(db).goi_y_khe(dong_id=dong_id, tu=tu, den=den)
    except Exception as exc:
        raise _map(exc)


# --- Ghi một dòng (khóa lạc quan + chặn đặt lịch) ---------------------------
@router.put("/dong/{dong_id}", response_model=None)
def luu(
    dong_id: int,
    payload: LuuIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> dict:
    svc = _svc(db)
    patch = payload.model_dump(exclude_unset=True, exclude={"expected_updated_at"})
    try:
        saved = svc.luu(
            dong_id=dong_id, patch=patch,
            expected_updated_at=payload.expected_updated_at, actor=user,
        )
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    return svc.dong_view(saved)


# --- Kiểm phát hành + phát hành / thu hồi (cửa vật tư dùng chung) ------------
@router.get("/kiem-phat-hanh", response_model=None)
def kiem_phat_hanh(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    nguon: str = Query(..., description="lsx | in_ghep"),
    id: int = Query(..., description="id LSX hoặc bài ghép"),
) -> dict:
    """Danh sách vấn đề CHẶN PHÁT HÀNH (vật tư chưa đủ · dòng chưa xếp giờ · luật đặt còn vướng).

    `van_de` rỗng ⇒ phát hành được. Cửa vật tư dùng chung nên màn cũ cũng vấp đúng luật này."""
    return {"van_de": _svc(db).kiem_phat_hanh(nguon=nguon, id=id)}


@router.post("/duyet-ngoai-le/lsx/{lsx_id}", response_model=None)
def duyet_ngoai_le_lsx(
    lsx_id: int,
    payload: DuyetNgoaiLeIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve_exception"))],
) -> dict:
    """Duyệt NGOẠI LỆ trễ hạn SX cho một LSX (§7.2): trễ hạn vẫn cho phát hành, kèm lý do.

    NEO THEO MỐC ĐÃ DUYỆT — hệ thống tự ghi mốc hoàn thành hiện tại; dời lịch xong muộn hơn mốc thì
    ngoại lệ tự mất hiệu lực, phải duyệt lại. Quyền RIÊNG `approve_exception` (không phải `approve`
    phát hành). Chỉ hạ được đúng `tre_han_sx`."""
    svc = _svc(db)
    try:
        kq = svc.duyet_ngoai_le(nguon=NGUON_LSX, id=lsx_id, ly_do=payload.ly_do, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return kq


@router.post("/duyet-ngoai-le/bai-ghep/{bai_ghep_id}", response_model=None)
def duyet_ngoai_le_bai_ghep(
    bai_ghep_id: int,
    payload: DuyetNgoaiLeIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve_exception"))],
) -> dict:
    """Duyệt NGOẠI LỆ trễ hạn SX cho một bài ghép (§7.2) — NEO THEO MỐC ĐÃ DUYỆT. Quyền RIÊNG
    `approve_exception`."""
    svc = _svc(db)
    try:
        kq = svc.duyet_ngoai_le(nguon=NGUON_IN_GHEP, id=bai_ghep_id, ly_do=payload.ly_do, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return kq


@router.post("/phat-hanh/lsx/{lsx_id}", response_model=None)
def phat_hanh_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> dict:
    svc = _svc(db)
    try:
        lsx = svc.phat_hanh(nguon=NGUON_LSX, id=lsx_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return {"id": lsx.id, "ma": lsx.ma, "trang_thai": lsx.trang_thai}


@router.post("/phat-hanh/bai-ghep/{bai_ghep_id}", response_model=None)
def phat_hanh_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> dict:
    svc = _svc(db)
    try:
        bg = svc.phat_hanh(nguon=NGUON_IN_GHEP, id=bai_ghep_id, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return {"id": bg.id, "ma": bg.ma, "trang_thai": bg.trang_thai}


@router.delete("/phat-hanh/lsx/{lsx_id}", response_model=None)
def go_phat_hanh_lsx(
    lsx_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
    ly_do: str = Query(default="", max_length=500, description="Ghi vào AuditLog"),
) -> dict:
    svc = _svc(db)
    try:
        lsx = svc.thu_hoi(nguon=NGUON_LSX, id=lsx_id, actor=user, ly_do=ly_do)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    return {"id": lsx.id, "ma": lsx.ma, "trang_thai": lsx.trang_thai}


@router.delete("/phat-hanh/bai-ghep/{bai_ghep_id}", response_model=None)
def go_phat_hanh_bai_ghep(
    bai_ghep_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
    ly_do: str = Query(default="", max_length=500, description="Ghi vào AuditLog"),
) -> dict:
    svc = _svc(db)
    try:
        bg = svc.thu_hoi(nguon=NGUON_IN_GHEP, id=bai_ghep_id, actor=user, ly_do=ly_do)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    return {"id": bg.id, "ma": bg.ma, "trang_thai": bg.trang_thai}


# --- Phát hành cập nhật (phiên bản lịch §4.3) --------------------------------
@router.get("/goi-phat-hanh", response_model=None)
def goi_phat_hanh(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    nguon: str = Query(..., description="lsx | in_ghep"),
    id: int = Query(..., description="id LSX hoặc bài ghép"),
) -> dict:
    """Trạng thái gói phát hành (phiên bản + số việc đã/chưa bắt đầu) cho UI quyết nút cập-nhật /
    thu-hồi. `co_goi=False` khi chưa phát hành. Chỉ đọc."""
    return _svc(db).goi_phat_hanh(nguon=nguon, id=id)


@router.post("/phat-hanh-cap-nhat/lsx/{lsx_id}", response_model=None)
def phat_hanh_cap_nhat_lsx(
    lsx_id: int,
    payload: PhatHanhCapNhatIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> dict:
    """Phát hành CẬP NHẬT lịch cho một LSX (§4.3): tái chụp việc chưa bắt đầu → phiên bản mới, kèm
    lý do. Việc đã bắt đầu giữ nguyên; phân công + hỗ trợ của việc cập nhật bị huỷ (tổ xác nhận lại)."""
    svc = _svc(db)
    try:
        kq = svc.phat_hanh_cap_nhat(nguon=NGUON_LSX, id=lsx_id, ly_do=payload.ly_do, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "lsx_changed"})
    hub.broadcast({"type": "san_xuat_changed"})
    return kq


@router.post("/phat-hanh-cap-nhat/bai-ghep/{bai_ghep_id}", response_model=None)
def phat_hanh_cap_nhat_bai_ghep(
    bai_ghep_id: int,
    payload: PhatHanhCapNhatIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> dict:
    """Phát hành CẬP NHẬT lịch cho một bài ghép (§4.3) — như trên, cho gói bài ghép."""
    svc = _svc(db)
    try:
        kq = svc.phat_hanh_cap_nhat(nguon=NGUON_IN_GHEP, id=bai_ghep_id, ly_do=payload.ly_do, actor=user)
    except Exception as exc:
        raise _map(exc)
    hub.broadcast({"type": "xep_lich_changed"})
    hub.broadcast({"type": "bai_ghep_changed"})
    hub.broadcast({"type": "san_xuat_changed"})
    return kq
