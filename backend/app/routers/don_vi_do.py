"""Đơn vị & quy đổi router — CRUD đơn vị + CRUD cặp quy đổi + thử một phép đổi.

HAI danh mục trên MỘT router, cả hai sinh từ `routers/catalog_base.make_catalog_router`:
`/api/don-vi` (đơn vị) và `/api/don-vi/quy-doi` (cặp quy đổi).

Dependency INLINE (bám `routers/bu_hao.py`). MODULE quyền = "dm_don_vi" — quyền RIÊNG. Trước đây
đi ké `dm_cong_doan`, nghĩa là muốn cho kế toán khai "1 thùng = 24 hộp" thì phải mở luôn cho họ
danh mục công đoạn. Đơn vị dùng chung cho kho · mua hàng · khoán lương, không thuộc riêng ai.

⚠️ THỨ TỰ TRONG FILE = thứ tự khớp route của FastAPI. Ba route tĩnh (`/ho`, `/bien`, `/thu`) và cả
nhánh `/quy-doi` phải khai TRƯỚC factory của đơn vị — nó dựng `/{item_id}`, và `"ho"` không ép
được sang int nên sẽ ăn 422.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..schemas.don_vi_do import (
    BienListOut, CapIn, CapListOut, CapRowOut, DonViDoIn, DonViDoListOut, DonViDoRow, HoListOut,
    QuyDoiIn, QuyDoiOut,
)
from ..services.don_vi_do_service import (
    CapQuyDoiService, DonViDoService, cong_thuc_chu,
)
from ..services.quy_doi_service import BIEN, _so, don_vi_map, doi_theo_quy_cach
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/don-vi", tags=["don-vi"])
MODULE = "dm_don_vi"


def get_service(db: Annotated[Session, Depends(get_db)]) -> DonViDoService:
    return DonViDoService(DonViDoRepository(db), AuditLogRepository(db))


def get_cap_service(db: Annotated[Session, Depends(get_db)]) -> CapQuyDoiService:
    return CapQuyDoiService(get_service(db))


Service = Annotated[DonViDoService, Depends(get_service)]
CapService = Annotated[CapQuyDoiService, Depends(get_cap_service)]


def _dung_rows(svc: DonViDoService, objs: list) -> list[DonViDoRow]:
    """Dòng của màn Đơn vị — mã trần không đủ, phải kèm cảnh báo + câu quy đổi + cách đo bằng chữ.

    Dựng chip MỘT lần rồi rút chuỗi phẳng ra từ đó — gọi cả `quy_doi_text` lẫn `quy_doi_chips` là
    quét bảng cặp hai lượt cho mỗi dòng (20 đơn vị → 40 lượt) mà ra đúng cùng một thứ.
    """
    ra = []
    for obj in objs:
        row = DonViDoRow.model_validate(obj)
        row.canh_bao = svc.canh_bao(obj)
        row.quy_doi_chips = svc.quy_doi_chips(obj)
        row.quy_doi_text = (" · ".join(c["text"] for c in row.quy_doi_chips)
                            if row.quy_doi_chips else "Chưa khai quy đổi")
        if (hl := svc.cong_thuc_hieu_luc(obj)):
            row.cong_thuc_hieu_luc, row.cong_thuc_chu_ma, row.cong_thuc_chu_ten = hl
        # Cách đo dịch sang chữ để màn danh sách khỏi nhúng bảng nhãn biến thứ hai.
        row.cong_thuc_text = cong_thuc_chu(obj.cong_thuc) if obj.cong_thuc else None
        ra.append(row)
    return ra


def _dung_cap_rows(_svc, caps: list) -> list[CapRowOut]:
    ra = []
    for c in caps:
        row = CapRowOut.model_validate(c)
        row.cau = f"1 {c.tu_ten} = {_so(float(c.he_so))} {c.den_ten}"
        row.ma = f"{c.tu_ma} → {c.den_ma}"
        row.ten = row.cau
        ra.append(row)
    return ra


# ĐỌC danh sách đơn vị: quyền RỘNG hơn phần khai (`MODULE`). Từ 2026-08-08 ô ĐVT của Giấy · Vật tư
# khác · Kho · NCC đều chọn từ danh mục này, mà mấy màn đó gác bằng module KHÁC — để nguyên
# `dm_cong_doan` thì người dùng kho mở drawer sẽ ăn 403, và `RebuildCatalogPage` NUỐT lỗi thành
# danh sách rỗng (`.catch(() => [])`) nên họ chỉ thấy ô tìm không ra gì, không thấy báo lỗi nào.
_doc_don_vi = require_any_permission(
    (MODULE, "read"), ("kho", "read"), ("thu_mua", "read"),
    ("tinh_gia_thanh", "read"), ("san_xuat", "read"),
    # Các màn danh mục có ô ĐVT trong form: Giấy · Vật tư khác · Công đoạn (đơn vị năng suất) ·
    # Máy (ô "Đơn vị tốc độ" nay đọc động từ danh mục này thay danh sách viết cứng).
    ("dm_giay", "read"), ("dm_vat_tu", "read"), ("dm_cong_doan", "read"), ("dm_thiet_bi", "read"))


# --- Route TĨNH: khai TRƯỚC factory (xem cảnh báo ở docstring) ---------------------------


@router.get("/ho", response_model=HoListOut)
def list_ho(svc: Service, _: Annotated[User, Depends(_doc_don_vi)]) -> HoListOut:
    return HoListOut(items=svc.ho_goi_y())


@router.get("/bien", response_model=BienListOut)
def list_bien(_: Annotated[User, Depends(_doc_don_vi)]) -> BienListOut:
    """Biến dùng được trong công thức quy đổi — màn khai phải LIỆT KÊ, không bắt người ta đoán tên."""
    return BienListOut(items=[{"ma": k, "nhan": v} for k, v in BIEN.items()])


@router.post("/thu", response_model=QuyDoiOut)
def thu_quy_doi(
    payload: QuyDoiIn,
    svc: Service,
    _: Annotated[User, Depends(_doc_don_vi)],
) -> QuyDoiOut:
    """Thử một phép đổi — trả kèm DIỄN GIẢI cách tính, hoặc nói rõ thiếu gì (không đoán)."""
    # `all_rows`: đây là công cụ TRA CỨU ("thử đổi 5 tấn ra kg"), không phải ô chọn. Người dùng
    # có quyền thử một đơn vị đã ngừng để hiểu con số trên chứng từ cũ.
    dvs = don_vi_map(svc.repo.all_rows())
    kq = doi_theo_quy_cach(payload.gia_tri, payload.tu, payload.den, payload.quy_cach, dvs,
                           svc.repo.cap_rows())
    return QuyDoiOut(**kq)


# --- Danh mục THỨ HAI: cặp quy đổi (`/api/don-vi/quy-doi`) --------------------------------
make_catalog_router(
    router, goc="/quy-doi", ten="don_vi_quy_doi", ServiceDep=CapService,
    module=MODULE, doc=_doc_don_vi,
    InModel=CapIn, RowModel=CapRowOut, ListModel=CapListOut,
    dung_rows=_dung_cap_rows,
    # ⚠️ `don_vi_quy_doi` KHÔNG có cột `active` — bật cờ là nền đi lọc một cột không tồn tại.
    co_active=False,
)

# --- Danh mục CHÍNH: đơn vị. Có `/{item_id}` nên phải khai SAU CÙNG ----------------------
make_catalog_router(
    router, ten="don_vi_do", ServiceDep=Service, module=MODULE, doc=_doc_don_vi,
    InModel=DonViDoIn, RowModel=DonViDoRow, ListModel=DonViDoListOut,
    loc="ho",
    dung_rows=_dung_rows,
    # Không mở `/ma-goi-y`: mã đơn vị là chữ (`kg`, `to`, `m2`), không phải dãy số — repo không
    # khai `ma_prefix`.
)
