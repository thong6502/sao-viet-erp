"""Repository — Công đoạn (danh mục). CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..models.cong_doan import CongDoan, CongDoanDauViec, CongDoanDauViecVatTu
from ..models.don_vi_do import DonViDo
from ..models.piece_work import PieceRate
from ..models.vat_lieu_kho import VatTuInAn
from .catalog_base import CatalogRepo

ASSIGNABLE = (
    # `he_so_ngoai_dong` GỠ khỏi đây 20/08/2026 (ngưng dùng): hệ số vào→ra của bước ngoài dòng nay
    # lấy TỪ cầu `don_vi_quy_doi` (module Đơn vị & quy đổi), không khai tay. Cột DB còn để lượt sau
    # drop bằng migration — xem `LsxService._he_so_ngoai_dong`.
    "ten", "ten_hien_thi", "don_vi_vao", "don_vi_ra",
    "kieu_bu_hao", "bu_hao_id", "so_to_bu_hao", "nhom", "nhom_may_cho_phep", "department_id", "khoan_ghi_theo",
    "cong_thuc_san_luong",
    "allowed_defect_pct", "allowed_defect_abs",
    "che_do_tinh", "pricing_basis", "setup_cost", "setup_time", "nang_suat",
    "run_rate", "rate_tiers", "size_tiers", "first_unit_floor", "min_charge", "requires_tooling",
    "tooling_type", "spoilage_pct", "inline_flag", "la_kcs", "ghi_chu", "active", "cong_thuc_gia",
)


class CongDoanRepository(CatalogRepo):
    model = CongDoan
    fields = ASSIGNABLE
    commit_on_write = False   # `CongDoanService` chốt sau khi ghi nhật ký — xem `catalog_base`
    # Mã KHAI TAY (service không tự cấp), nhưng quy ước đánh số là `CD-####` — khai `ma_prefix`
    # để `GET /api/cong-doan/ma-goi-y` gợi được mã kế tiếp. Trước 15/08/2026 frontend tự đoán
    # tiền tố này bằng cách dò chuỗi trong URL (`danh-muc/maGoiY.ts`).
    ma_prefix = "CD-"

    def _base_select(self):
        """Nạp kèm định mức đầu việc + vật tư của nó — bảng công đoạn vẽ luôn các dòng con,
        để lazy là N+1 truy vấn cho mỗi trang."""
        return select(CongDoan).options(
            selectinload(CongDoan.dau_viec_dinh_muc).selectinload(CongDoanDauViec.vat_tus)
        )

    def extra_conds(self, *, nhom: str | None = None, **_) -> list:
        return [CongDoan.nhom == nhom] if nhom else []

    def get(self, cd_id: int) -> CongDoan | None:
        return self.db.execute(
            self._base_select().where(CongDoan.id == cd_id)
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

    def phong_ban_tos(self):
        """TỔ sản xuất = nút LÁ trong nhánh Khối Sản xuất (ĐỊNH NGHĨA CHUNG `to_san_xuat()`)."""
        from .rbac_repo import DepartmentRepository

        return DepartmentRepository(self.db).to_san_xuat()

    def phong_ban_tat_ca(self):
        """Mọi phòng ban — để dựng lại nhãn cho giá trị CŨ nay không còn là tổ."""
        from .rbac_repo import DepartmentRepository

        return DepartmentRepository(self.db).list_all()

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
        stmt = select(PieceRate).where(PieceRate.active.is_(True))
        if department_id is not None:
            stmt = stmt.where(PieceRate.department_id == department_id)
        return list(self.db.execute(
            stmt.order_by(PieceRate.department_id, PieceRate.ma, PieceRate.ten)).scalars())

    def dem_theo_nhom(self, *, q: str | None = None, active: bool | None = None) -> dict[str, int]:
        """Số công đoạn của TỪNG giai đoạn — số hiện trên tab lọc. Không áp điều kiện `nhom`
        (tab nào cũng phải có số của nó), nhưng CÓ áp `q` và `active`."""
        stmt = select(CongDoan.nhom, func.count()).group_by(CongDoan.nhom)
        loc = self._loc_q(q)
        if loc is not None:
            stmt = stmt.where(loc)
        if active is not None:
            stmt = stmt.where(CongDoan.active.is_(active))
        # Nhóm khuyết gom vào khoá rỗng "" (xem `may_thiet_bi_repo.dem_theo_loai`).
        return {(str(nhom).strip() if nhom is not None else ""): int(n)
                for nhom, n in self.db.execute(stmt)}

    def _sau_gan(self, cd: CongDoan, data: dict) -> None:
        self._replace_dinh_muc(cd, data.get("dau_viec_dinh_muc") or [])

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

