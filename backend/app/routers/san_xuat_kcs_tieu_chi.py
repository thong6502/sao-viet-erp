"""Hạng mục kiểm KCS router — CRUD danh mục checklist kiểm tra chất lượng.

Ngoài CRUD phẳng (nền `make_catalog_router`) còn `GET .../khai-bao` trả sẵn ba tầng
Giai đoạn → Công đoạn → hạng mục cho màn khai báo (`docs/design-kcs-theo-cong-doan.md` mục 5).

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE.

MODULE quyền = "dm_kcs_tieu_chi".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.san_xuat_kcs_tieu_chi_repo import SanXuatKcsTieuChiRepository
from ..models.cong_doan import NHOM as NHOM_CONG_DOAN, CongDoan
from ..repositories.san_xuat_kcs_tieu_chi_repo import hang_muc_theo_cong_doan
from ..schemas.san_xuat_kcs_tieu_chi import (
    KcsKhaiBaoCongDoanOut, KcsKhaiBaoGiaiDoanOut, KcsKhaiBaoOut,
    SanXuatKcsTieuChiIn, SanXuatKcsTieuChiListOut, SanXuatKcsTieuChiRow,
)
from ..services.san_xuat_kcs_tieu_chi_service import SanXuatKcsTieuChiService
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/san-xuat-kcs-tieu-chi", tags=["san-xuat-kcs-tieu-chi"])
MODULE = "dm_kcs_tieu_chi"

# Ai ĐỌC được danh mục này: người khai tiêu chí + Sản xuất (board KCS Task 4/5 cần hiển thị
# checklist) — cùng lý do `bu_hao.py:35-37` mở đọc cho Tính giá/Sản xuất.
_DOC = require_any_permission((MODULE, "read"), ("san_xuat", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> SanXuatKcsTieuChiService:
    return SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db), AuditLogRepository(db))


Service = Annotated[SanXuatKcsTieuChiService, Depends(get_service)]

# Đăng ký TRƯỚC `make_catalog_router`: FastAPI khớp route theo THỨ TỰ, để sau thì
# `GET /{item_id}` của nền CRUD nuốt mất đường này (422 vì "khai-bao" không ép được sang int).
@router.get("/khai-bao", response_model=KcsKhaiBaoOut)
def khai_bao(db: Annotated[Session, Depends(get_db)], _=Depends(_DOC)) -> KcsKhaiBaoOut:
    """Ba tầng Giai đoạn → Công đoạn → hạng mục — hình dạng màn khai báo dùng thẳng.

    CHỈ liệt kê công đoạn ĐÃ khai hạng mục: đây là "danh sách công đoạn cần kiểm", không phải
    bản sao danh mục Công đoạn. Muốn thêm công đoạn vào bàn kiểm thì khai hạng mục đầu tiên
    cho nó (POST bản ghi thường). Giai đoạn xếp theo thứ tự cố định của `cong_doan.nhom`;
    công đoạn không khai nhóm rơi vào cụm cuối mang `nhom = ""`.

    ĐỌC CẢ hạng mục `active=False` — màn khai báo phải thấy dòng đang ngừng dùng để bật lại;
    chỉ đường PHÁT HÀNH mới lọc `active` (`SanXuatRepository.checklist_theo_cong_doan`).
    """
    theo_cd = hang_muc_theo_cong_doan(db)
    if not theo_cd:
        return KcsKhaiBaoOut(giai_doan=[])
    cds = db.execute(select(CongDoan).where(CongDoan.id.in_(set(theo_cd)))).scalars().all()
    theo_nhom: dict[str, list[KcsKhaiBaoCongDoanOut]] = {}
    for cd in sorted(cds, key=lambda c: (c.ma or "", c.id)):
        theo_nhom.setdefault(cd.nhom or "", []).append(KcsKhaiBaoCongDoanOut(
            cong_doan_id=cd.id, ma=cd.ma or "", ten=cd.ten or "",
            hang_muc=[SanXuatKcsTieuChiRow.model_validate(h) for h in theo_cd[cd.id]],
        ))
    thu_tu = {ma: i for i, ma in enumerate(NHOM_CONG_DOAN)}
    khoa = sorted(theo_nhom, key=lambda ma: (thu_tu.get(ma, len(thu_tu)), ma))
    return KcsKhaiBaoOut(giai_doan=[
        KcsKhaiBaoGiaiDoanOut(nhom=ma, cong_doan=theo_nhom[ma]) for ma in khoa
    ])


make_catalog_router(
    router, ten="san_xuat_kcs_tieu_chi", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=SanXuatKcsTieuChiIn, RowModel=SanXuatKcsTieuChiRow, ListModel=SanXuatKcsTieuChiListOut,
    # KHÔNG truyền excel_spec= — danh mục này khai theo cây (công đoạn → hạng mục), không có
    # cột phẳng để map vào một dòng Excel.
)
