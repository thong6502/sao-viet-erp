"""Repository — Công đoạn (danh mục). CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.cong_doan import CongDoan, CongDoanDauViec, CongDoanDauViecVatTu
from ..models.don_vi_do import DonViDo
from ..models.piece_work import PieceRate
from ..models.vat_lieu_kho import VatTuInAn

ASSIGNABLE = (
    "ten", "ten_hien_thi", "don_vi_vao", "don_vi_ra",
    "kieu_bu_hao", "bu_hao_id", "so_to_bu_hao", "nhom", "nhom_may_cho_phep", "department_id", "khoan_ghi_theo",
    "allowed_defect_pct", "allowed_defect_abs",
    "che_do_tinh", "pricing_basis", "setup_cost", "setup_time", "nang_suat",
    "run_rate", "rate_tiers", "size_tiers", "first_unit_floor", "min_charge", "requires_tooling",
    "tooling_type", "spoilage_pct", "inline_flag", "ghi_chu", "active", "cong_thuc_gia",
)


class CongDoanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, cd_id: int) -> CongDoan | None:
        return self.db.execute(
            select(CongDoan).where(CongDoan.id == cd_id)
            .options(selectinload(CongDoan.dau_viec_dinh_muc)
                     .selectinload(CongDoanDauViec.vat_tus))
        ).scalar_one_or_none()

    def don_vi_tram(self, mas: set[str]) -> dict[str, str | None]:
        """`{mã đơn vị: trạm dòng giấy}` cho các mã CÓ THẬT trong danh mục Đơn vị.

        Mã không có trong danh mục thì VẮNG key (khác với có key mà giá trị None = có trong danh
        mục nhưng đứng ngoài dòng giấy) — service phân biệt hai ca đó để báo lỗi cho đúng.
        """
        if not mas:
            return {}
        return {ma: tram for ma, tram in self.db.execute(
            select(DonViDo.ma, DonViDo.tram_dong_giay).where(DonViDo.ma.in_(mas))
        ).all()}

    def don_vi_ten(self) -> dict[str, str]:
        """`{mã đơn vị: tên}` cho CẢ danh mục — một truy vấn cho cả trang, không N+1.

        Bảng nhỏ (20 dòng) nên nạp hết rẻ hơn lọc theo mã đang dùng.
        """
        return {
            (ma or "").strip().lower(): ten
            for ma, ten in self.db.execute(select(DonViDo.ma, DonViDo.ten)).all()
        }

    def department_ids_dang_dung(self) -> set[int]:
        """Id phòng ban đang được CÔNG ĐOẠN nào đó trỏ tới.

        Dùng cho dropdown "Tổ phụ trách": đổi định nghĩa Tổ (mục H) thì giá trị cũ vẫn phải chọn
        lại được, không thì mở form ra là ô rỗng và bấm Lưu là mất tổ đang gán.
        """
        return {
            i for (i,) in self.db.execute(
                select(CongDoan.department_id).where(CongDoan.department_id.is_not(None)).distinct()
            )
        }

    def piece_rates(self, ids: set[int]) -> dict[int, PieceRate]:
        if not ids:
            return {}
        rows = self.db.execute(select(PieceRate).where(PieceRate.id.in_(ids))).scalars()
        return {r.id: r for r in rows}

    def vat_tus(self, ids: set[int]) -> dict[int, VatTuInAn]:
        """Vật tư theo id — service dùng để chặn id không tồn tại / đã ngừng dùng, và để chụp
        mã·tên·đơn vị vào dòng trả về."""
        if not ids:
            return {}
        rows = self.db.execute(select(VatTuInAn).where(VatTuInAn.id.in_(ids))).scalars()
        return {r.id: r for r in rows}

    def piece_rates_active(self, department_id: int | None = None) -> list[PieceRate]:
        stmt = select(PieceRate).where(PieceRate.is_active.is_(True))
        if department_id is not None:
            stmt = stmt.where(PieceRate.department_id == department_id)
        return list(self.db.execute(stmt.order_by(PieceRate.department_id, PieceRate.code, PieceRate.name)).scalars())

    def find_by_ma(self, ma: str) -> CongDoan | None:
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(select(CongDoan).where(func.upper(CongDoan.ma) == ma)).scalars().first()

    def list(self, *, q: str | None = None, nhom: str | None = None,
             active: bool | None = None, page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(CongDoan.ma).like(like), func.lower(CongDoan.ten).like(like)))
        if nhom:
            conds.append(CongDoan.nhom == nhom)
        if active is not None:
            conds.append(CongDoan.active.is_(active))
        base = select(CongDoan).options(selectinload(CongDoan.dau_viec_dinh_muc)
                     .selectinload(CongDoanDauViec.vat_tus))
        count_stmt = select(func.count()).select_from(CongDoan)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(CongDoan.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def _apply(self, cd: CongDoan, data: dict) -> None:
        for k in ASSIGNABLE:
            if k in data:
                setattr(cd, k, data[k])

    def _replace_dinh_muc(self, cd: CongDoan, rows: list[dict]) -> None:
        """Thay TRỌN bộ định mức đầu việc của công đoạn.

        BẮT BUỘC `flush()` giữa xoá và thêm: trong MỘT flush, SQLAlchemy phát INSERT trước DELETE
        cho cùng một bảng, nên lưu lại đúng đầu việc cũ là đụng `uq_cd_dau_viec_rate` → 500
        (`duplicate key (cong_doan_id, piece_rate_id)`). Xoá bay đi trước rồi mới chèn thì cả hai
        đường — sửa số của dòng cũ và bỏ/thêm dòng — đều chạy.
        """
        if cd.dau_viec_dinh_muc:
            cd.dau_viec_dinh_muc.clear()
            if cd.id is not None:          # công đoạn mới chưa có id thì chưa có gì để xoá
                self.db.flush()
        for r in rows:
            # `vat_tu_ids` là DANH SÁCH CON, không phải cột — tách ra trước khi dựng model.
            r = dict(r)
            ids = r.pop("vat_tu_ids", None) or []
            r.pop("vat_tus", None)         # khoá chỉ-đọc của schema Row, client có thể gửi ngược lên
            dv = CongDoanDauViec(**r)
            dv.vat_tus.extend(
                CongDoanDauViecVatTu(vat_tu_id=int(v), thu_tu=i) for i, v in enumerate(ids)
            )
            cd.dau_viec_dinh_muc.append(dv)

    def create(self, data: dict) -> CongDoan:
        cd = CongDoan(ma=data["ma"].strip().upper())
        self._apply(cd, data)
        self._replace_dinh_muc(cd, data.get("dau_viec_dinh_muc") or [])
        self.db.add(cd)
        self.db.commit()
        self.db.refresh(cd)
        return cd

    def update(self, cd: CongDoan, data: dict) -> CongDoan:
        if data.get("ma"):
            cd.ma = data["ma"].strip().upper()
        self._apply(cd, data)
        self._replace_dinh_muc(cd, data.get("dau_viec_dinh_muc") or [])
        self.db.commit()
        self.db.refresh(cd)
        return cd

    def delete(self, cd: CongDoan) -> None:
        self.db.delete(cd)
        self.db.commit()
