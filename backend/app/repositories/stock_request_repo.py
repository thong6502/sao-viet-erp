"""Repository — Đề nghị kho (spec-kho-de-nghi §3–§5).

Chỉ truy vấn/ghi DB. Luật nghiệp vụ (ai được duyệt, chặn ứng vượt duyệt, chuyển trạng
thái) nằm ở `services/stock_request_service.py`.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.stock_request import StockRequest, StockRequestLine

_HEADER_FIELDS = ("bo_phan_id", "kho_id", "ngay_can", "uu_tien", "ghi_chu")


def _build_line(ln: dict, loai: str) -> StockRequestLine:
    """Dựng 1 dòng đề nghị từ dict payload. Đơn giá + QUY ĐỔI chỉ áp cho đề nghị NHẬP
    (người đề nghị khai); XUẤT → null (giá vốn/đơn vị lấy đích danh từ lô)."""
    is_nhap = loai == "NHAP"
    dvp = ((ln.get("don_vi_phu") or "").strip() or None) if is_nhap else None
    hs = ln.get("he_so_quy_doi")
    return StockRequestLine(
        material_id=ln.get("material_id"),
        ten_tu_do=(ln.get("ten_tu_do") or "").strip() or None,
        dvt=ln["dvt"],
        sl_de_nghi=ln["sl_de_nghi"],
        don_gia=ln.get("don_gia") if is_nhap else None,
        don_vi_phu=dvp,
        he_so_quy_doi=(hs if (dvp and hs and float(hs) > 0) else None),
        ghi_chu=ln.get("ghi_chu"),
    )


class StockRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, request_id: int) -> StockRequest | None:
        return self.db.get(StockRequest, request_id)

    def get_by_ma(self, ma: str) -> StockRequest | None:
        return self.db.execute(
            select(StockRequest).where(func.upper(StockRequest.ma) == ma.strip().upper())
        ).scalars().first()

    def get_with_lines(self, request_id: int) -> StockRequest | None:
        return self.db.execute(
            select(StockRequest)
            .options(selectinload(StockRequest.lines))
            .where(StockRequest.id == request_id)
        ).scalars().first()

    def get_line(self, line_id: int) -> StockRequestLine | None:
        return self.db.get(StockRequestLine, line_id)

    def by_ids_with_lines(self, ids) -> dict[int, StockRequest]:
        """Nạp NHIỀU đề nghị kèm dòng trong 1 (+lines) query — tránh N+1 khi serialize danh sách phiếu."""
        ids = [i for i in set(ids) if i is not None]
        if not ids:
            return {}
        rows = self.db.execute(
            select(StockRequest)
            .options(selectinload(StockRequest.lines))
            .where(StockRequest.id.in_(ids))
        ).scalars()
        return {r.id: r for r in rows}

    def list(self, *, loai: str | None = None, trang_thai: list[str] | None = None,
             q: str | None = None, nguoi_tao_id: int | None = None,
             bo_phan_id: int | None = None, kho_id: int | None = None,
             page: int = 1, size: int = 50):
        """Danh sách đề nghị. `nguoi_tao_id` / `bo_phan_id` là cách áp SCOPE: người đề nghị
        (scope `own`) chỉ thấy đề nghị của chính mình — đó là lý do họ không nhìn thấy kho."""
        conds = []
        if loai:
            conds.append(StockRequest.loai == loai)
        if trang_thai:
            conds.append(StockRequest.trang_thai.in_(trang_thai))
        if nguoi_tao_id is not None:
            conds.append(StockRequest.nguoi_tao_id == nguoi_tao_id)
        if bo_phan_id is not None:
            conds.append(StockRequest.bo_phan_id == bo_phan_id)
        if kho_id is not None:
            conds.append(StockRequest.kho_id == kho_id)
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(
                func.lower(StockRequest.ma).like(like),
                func.lower(func.coalesce(StockRequest.ghi_chu, "")).like(like),
            ))

        base = select(StockRequest).options(selectinload(StockRequest.lines))
        count_stmt = select(func.count()).select_from(StockRequest)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(StockRequest.id.desc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, *, ma: str, loai: str, nguoi_tao_id: int, lines: list[dict],
               **header) -> StockRequest:
        obj = StockRequest(ma=ma, loai=loai, nguoi_tao_id=nguoi_tao_id)
        for k in _HEADER_FIELDS:
            if k in header:
                setattr(obj, k, header[k])
        for ln in lines:
            obj.lines.append(_build_line(ln, loai))
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def replace_lines(self, obj: StockRequest, lines: list[dict]) -> None:
        """Thay toàn bộ dòng (chỉ dùng khi đề nghị còn sửa được). Xóa-rồi-thêm thay vì
        khớp từng dòng: đề nghị còn nháp thì chưa có phiếu nào trỏ vào dòng cũ."""
        obj.lines.clear()
        self.db.flush()
        for ln in lines:
            obj.lines.append(_build_line(ln, obj.loai))

    def update_header(self, obj: StockRequest, data: dict) -> StockRequest:
        for k in _HEADER_FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        return obj

    def save(self, obj: StockRequest) -> StockRequest:
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: StockRequest) -> None:
        self.db.delete(obj)
        self.db.commit()
