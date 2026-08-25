"""Router Phiếu tính giá — LƯU/liệt kê/mở lại/sửa bản tính giá THEO THÀNH PHẦN.

Prefix `/api/phieu-tinh-gia`. RBAC MODULE = "tinh_gia_thanh". 1 phiếu = header + nhiều thành phần
(mỗi thành phần = 1 tờ giấy) → mỗi thành phần có nhiều dòng gia công sau in.

SAVE (POST/PUT) = dựng lại cây con + `services.tinh_gia_service.compute_phieu_snapshot` tính lại
giá vốn từng thành phần + Σ toàn phiếu + ảnh chụp. PUT = REPLACE-ALL con.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_authorization_service, require_permission
from ..models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia, PhieuVatTu
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.org_scope import dept_subtree_ids
from ..services.actor_display import actor_labels
from ..schemas.phieu_tinh_gia import (
    DanhMucDoi,
    PhieuTinhGiaCreate,
    PhieuTinhGiaListItem,
    PhieuTinhGiaListOut,
    PhieuTinhGiaOut,
    PhieuTinhGiaUpdate,
    PtgActivityItem,
    PtgActivityOut,
    ThanhPhanIn,
)
from ..services.rbac_service import AuthorizationService
from ..services.tinh_gia_service import compute_phieu_snapshot, danh_muc_doi_sau_khi_tinh

router = APIRouter(prefix="/api/phieu-tinh-gia", tags=["phieu-tinh-gia"])
MODULE = "tinh_gia_thanh"
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _owner_ids_for_scope(db: Session, user: User, authz: AuthorizationService) -> set[int] | None:
    """Tập user-id chủ sở hữu phiếu mà `user` được thấy theo scope module. None = thấy TẤT CẢ.
    - Tất cả (all) → None (không lọc).
    - Của tôi (own) → chỉ mình.
    - Phòng (department) → mọi người trong phòng mình + cây con (GĐ/TP thấy cả team)."""
    scope = authz.scope_for(user, MODULE) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return None
    if scope == SCOPE_DEPARTMENT:
        dept_ids = dept_subtree_ids(db, user.department_id)
        if dept_ids:
            ids = db.execute(select(User.id).where(User.department_id.in_(dept_ids))).scalars().all()
            return set(ids) | {user.id}
    return {user.id}


def _fetch_in_scope(db: Session, p_id: int, user: User, authz: AuthorizationService) -> PhieuTinhGia:
    """Lấy 1 phiếu + chặn nếu ngoài phạm vi của người xem (ẩn = 404, không lộ tồn tại)."""
    p = db.get(PhieuTinhGia, p_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu tính giá")
    owner_ids = _owner_ids_for_scope(db, user, authz)
    if owner_ids is not None and p.created_by not in owner_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu tính giá")
    return p


def _next_ma(db: Session) -> str:
    """PTG-{year}-{seq:04d} — seq = (số phiếu năm nay) + 1."""
    year = datetime.now().year
    prefix = f"PTG-{year}-"
    count = db.scalar(
        select(func.count()).select_from(PhieuTinhGia).where(PhieuTinhGia.ma.like(f"{prefix}%"))
    ) or 0
    return f"{prefix}{count + 1:04d}"


def _build_thanh_phan(tp_in: ThanhPhanIn, thu_tu: int) -> PhieuThanhPhan:
    """Dựng ORM thành phần + con finishing từ payload (chỉ set field được gửi → giữ default model)."""
    data = tp_in.model_dump(exclude_unset=True)
    rows_in = data.pop("thanh_phams", None) or []
    vt_in = data.pop("vat_tus", None) or []
    data.setdefault("thu_tu", thu_tu)
    tp = PhieuThanhPhan(**data)
    for j, row in enumerate(rows_in):
        rd = dict(row)
        rd.setdefault("thu_tu", j)
        tp.thanh_phams.append(PhieuThanhPham(**rd))
    for k, vt in enumerate(vt_in):
        vd = dict(vt)
        vd.setdefault("thu_tu", k)
        tp.vat_tus.append(PhieuVatTu(**vd))
    return tp


def _replace_children(p: PhieuTinhGia, thanh_phans: list[ThanhPhanIn] | None) -> None:
    """REPLACE-ALL: xoá sạch thành phần cũ, dựng lại từ payload (delete-orphan lo xoá con sâu)."""
    p.thanh_phans.clear()
    for i, tp_in in enumerate(thanh_phans or []):
        p.thanh_phans.append(_build_thanh_phan(tp_in, i))


@router.get("", response_model=PhieuTinhGiaListOut)
def list_items(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
) -> PhieuTinhGiaListOut:
    stmt = select(PhieuTinhGia)
    owner_ids = _owner_ids_for_scope(db, user, authz)
    if owner_ids is not None:
        stmt = stmt.where(PhieuTinhGia.created_by.in_(owner_ids))
    if q:
        like = f"%{q.strip()}%"
        # Gõ tên hàng phải ra phiếu, kể cả khi tên đó chỉ nằm ở SẢN PHẨM BÊN TRONG. Cột "Sản phẩm"
        # ngoài bảng rơi về tên hàng bên trong khi ô đầu phiếu bỏ trống (xem `ten_thanh_phans`) —
        # nhìn thấy chữ mà gõ đúng chữ đó lại không tìm ra thì người dùng tưởng mất phiếu.
        stmt = stmt.where(or_(
            PhieuTinhGia.ma.ilike(like),
            PhieuTinhGia.ten_san_pham.ilike(like),
            PhieuTinhGia.id.in_(
                select(PhieuThanhPhan.phieu_id).where(PhieuThanhPhan.ten.ilike(like))
            ),
        ))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.options(selectinload(PhieuTinhGia.thanh_phans)).order_by(PhieuTinhGia.created_at.desc())
    ).scalars().all()
    items = []
    for r in rows:
        it = PhieuTinhGiaListItem.model_validate(r)
        it.so_thanh_phan = len(r.thanh_phans)
        it.ten_thanh_phans = [tp.ten for tp in sorted(r.thanh_phans, key=lambda x: x.thu_tu) if tp.ten]
        items.append(it)
    return PhieuTinhGiaListOut(items=items, total=total)


@router.post("", response_model=PhieuTinhGiaOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: PhieuTinhGiaCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PhieuTinhGia:
    p = PhieuTinhGia(
        ma=_next_ma(db),
        ten_san_pham=payload.ten_san_pham or "",
        kho_thanh_pham=payload.kho_thanh_pham,
        loai_san_pham_id=payload.loai_san_pham_id,
        so_luong=payload.so_luong or 0,
        ghi_chu=payload.ghi_chu,
        ktv=(user.name or user.username),
        created_by=user.id,
    )
    _replace_children(p, payload.thanh_phans)
    db.add(p)
    db.flush()
    compute_phieu_snapshot(db, p)
    # Nhật ký hoạt động: ai LẬP phiếu, khi nào (audit.create tự commit → snapshot cùng lưu).
    AuditLogRepository(db).create(
        actor_user_id=user.id,
        action="create_ptg",
        target=f"phieu_tinh_gia:{p.id}",
        detail=f"Lập phiếu tính giá {p.ma}",
    )
    db.commit()
    db.refresh(p)
    return p


@router.get("/{p_id}", response_model=PhieuTinhGiaOut)
def get_item(
    p_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PhieuTinhGiaOut:
    p = _fetch_in_scope(db, p_id, user, authz)
    out = PhieuTinhGiaOut.model_validate(p)
    # Mở phiếu = ĐỌC LẠI ẢNH CHỤP, không tính lại (chủ ý — xem docstring service). Chỉ kèm thêm
    # lời nhắc nếu danh mục đã đổi sau lần tính; bấm hay không là quyền người lập phiếu.
    # POST/PUT không cần: hai đường đó vừa tính lại xong nên luôn còn khớp.
    doi = danh_muc_doi_sau_khi_tinh(db, p)
    if doi is not None:
        out.danh_muc_doi = DanhMucDoi(**doi)
    return out


@router.put("/{p_id}", response_model=PhieuTinhGiaOut)
def update_item(
    p_id: int,
    payload: PhieuTinhGiaUpdate,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PhieuTinhGia:
    p = _fetch_in_scope(db, p_id, user, authz)
    data = payload.model_dump(exclude_unset=True)
    for field in ("ten_san_pham", "kho_thanh_pham", "loai_san_pham_id", "so_luong", "ghi_chu"):
        if field in data:
            setattr(p, field, data[field])
    if "thanh_phans" in data:
        _replace_children(p, payload.thanh_phans)
    db.flush()
    compute_phieu_snapshot(db, p)
    # Nhật ký hoạt động: ai CẬP NHẬT phiếu, khi nào (audit.create tự commit).
    AuditLogRepository(db).create(
        actor_user_id=user.id,
        action="update_ptg",
        target=f"phieu_tinh_gia:{p.id}",
        detail=f"Cập nhật phiếu tính giá {p.ma}",
    )
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{p_id}")
def delete_item(
    p_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> dict:
    p = _fetch_in_scope(db, p_id, user, authz)
    ma = p.ma
    pid = p.id
    db.delete(p)
    db.commit()
    # Nhật ký hoạt động: ai XOÁ phiếu, khi nào (ghi sau khi đã xoá; giữ target theo id cũ).
    AuditLogRepository(db).create(
        actor_user_id=user.id,
        action="delete_ptg",
        target=f"phieu_tinh_gia:{pid}",
        detail=f"Xoá phiếu tính giá {ma}",
    )
    return {"ok": True}


@router.get("/{p_id}/activity", response_model=PtgActivityOut)
def phieu_activity(
    p_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PtgActivityOut:
    """Nhật ký hoạt động THẬT của 1 phiếu tính giá (ai làm gì · khi nào) — nhiều vai trò
    (KTV/sale/TP) có thể cùng sửa 1 phiếu nên mỗi thao tác để lại dấu vết. Đọc audit theo
    target `phieu_tinh_gia:{id}`, mới→cũ, kèm NGƯỜI thao tác ghi theo HỒ SƠ ("Phòng ban · Chức vụ
    · Tên" — `actor_display`, dùng chung với feed Báo giá). RBAC + phạm vi qua `_fetch_in_scope`
    (ngoài phạm vi = 404, không lộ tồn tại)."""
    _fetch_in_scope(db, p_id, user, authz)
    rows = AuditLogRepository(db).list_by_target(f"phieu_tinh_gia:{p_id}")
    names = actor_labels(db, {r.actor_user_id for r in rows if r.actor_user_id is not None})
    items = [
        PtgActivityItem(
            action=r.action,
            actor_name=names.get(r.actor_user_id) if r.actor_user_id else None,
            detail=r.detail,
            at=r.created_at,
        )
        for r in rows
    ]
    return PtgActivityOut(items=items)
