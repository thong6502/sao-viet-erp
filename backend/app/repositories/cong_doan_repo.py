"""Repository — Công đoạn (danh mục). CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..models.cong_doan import (
    CongDoan, CongDoanKhoan, CongDoanKhoanPhatSinh, CongDoanMay, CongDoanTo, CongDoanVatTu,
)
from ..models.don_vi_do import DonViDo
from ..models.may_thiet_bi import MayThietBi
from ..models.piece_work import CongViecKhoanTo
from ..models.vat_lieu_kho import VatTuInAn
from .catalog_base import CatalogRepo

ASSIGNABLE = (
    # `he_so_ngoai_dong` · `cong_thuc_san_luong` · `don_vi_san_luong` GỠ 18/09/2026 (mg `0324`).
    "ten", "ten_hien_thi", "don_vi_vao", "don_vi_ra",
    "kieu_bu_hao", "bu_hao_id", "so_to_bu_hao", "nhom", "nhom_may_cho_phep", "department_ids", "khoan_ghi_theo",
    "allowed_defect_pct", "allowed_defect_abs",
    "che_do_tinh", "pricing_basis", "setup_cost", "setup_time", "nang_suat",
    "run_rate", "rate_tiers", "size_tiers", "first_unit_floor", "min_charge", "requires_tooling",
    "tooling_type", "spoilage_pct", "inline_flag", "ghi_chu", "active", "cong_thuc_gia",
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
        """Nạp kèm vật tư · máy · tổ — bảng công đoạn vẽ luôn các dòng con, để lazy là N+1
        truy vấn cho mỗi trang."""
        return select(CongDoan).options(
            selectinload(CongDoan.vat_tus),
            selectinload(CongDoan.may_lam_duoc),
            selectinload(CongDoan.to_phu_trach),
            selectinload(CongDoan.khoan).selectinload(CongDoanKhoan.viec_phat_sinh),
        )

    def extra_conds(self, *, nhom: str | None = None, **_) -> list:
        return [CongDoan.nhom == nhom] if nhom else []

    def get(self, cd_id: int) -> CongDoan | None:
        return self.db.execute(
            self._base_select().where(CongDoan.id == cd_id)
        ).scalar_one_or_none()

    # GỠ 06/09/2026: `don_vi_tram(mas)`. Ô đơn vị của công đoạn nay là menu ĐÓNG 5 chặng dòng giấy
    # nên `_validate` đối chiếu thẳng với `TRAM_DONG_GIAY` trong code — không phải hỏi danh mục
    # Đơn vị nữa, và cột `don_vi_do.tram_dong_giay` nó đọc cũng đã thành cột chết.

    def department_ids_dang_dung(self) -> set[int]:
        """Id phòng ban đang được CÔNG ĐOẠN hoặc CÔNG VIỆC KHOÁN nào đó trỏ tới.

        Dùng cho dropdown "Tổ phụ trách" / "Tổ làm việc này" (cùng một endpoint): đổi định nghĩa Tổ
        (mục H) thì giá trị cũ vẫn phải chọn lại được, không thì mở form ra là ô rỗng và bấm Lưu là
        mất tổ đang gán.
        """
        return {i for (i,) in self.db.execute(
            select(CongDoanTo.department_id).union(select(CongViecKhoanTo.department_id)))}

    def phong_ban_tos(self):
        """TỔ sản xuất = nút LÁ trong nhánh Khối Sản xuất (ĐỊNH NGHĨA CHUNG `to_san_xuat()`)."""
        from .rbac_repo import DepartmentRepository

        return DepartmentRepository(self.db).to_san_xuat()

    def phong_ban_tat_ca(self):
        """Mọi phòng ban — để dựng lại nhãn cho giá trị CŨ nay không còn là tổ."""
        from .rbac_repo import DepartmentRepository

        return DepartmentRepository(self.db).list_all()

    # ⚠️ `piece_rates()` + `piece_rates_active()` GỠ 18/09/2026 (mg `0320`): công đoạn thôi khai
    #    đầu việc nên không còn chỗ nào tra `piece_rates` từ màn này.

    def mays(self, ids: set[int]) -> dict[int, MayThietBi]:
        """Máy theo id — service dùng để chặn id không tồn tại / máy đã thanh lý (`may_id` là
        soft-ref nên không có FK gác hộ)."""
        if not ids:
            return {}
        rows = self.db.execute(select(MayThietBi).where(MayThietBi.id.in_(ids))).scalars()
        return {r.id: r for r in rows}

    def vat_tus(self, ids: set[int]) -> dict[int, VatTuInAn]:
        """Vật tư theo id — service dùng để chặn id không tồn tại / đã ngừng dùng, và để chụp
        mã·tên·đơn vị vào dòng trả về."""
        if not ids:
            return {}
        rows = self.db.execute(select(VatTuInAn).where(VatTuInAn.id.in_(ids))).scalars()
        return {r.id: r for r in rows}

    def don_vi_theo_ma(self, mas: set[str]) -> dict[str, DonViDo]:
        if not mas:
            return {}
        rows = self.db.execute(select(DonViDo).where(DonViDo.ma.in_(mas))).scalars()
        return {r.ma: r for r in rows}

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
        self._replace_vat_tu(cd, data.get("vat_tus") or [])
        self._replace_may(cd, data.get("may_lam_duoc") or [])
        if "khoan" in data:
            self._replace_khoan(cd, data.get("khoan"))

    def _replace_khoan(self, cd: CongDoan, raw: dict | None) -> None:
        """Thay aggregate Khoán nhưng giữ id các dòng phát sinh mà client gửi ngược lên."""
        if not raw:
            cd.khoan = None
            return
        k = cd.khoan
        if k is None:
            k = CongDoanKhoan()
            cd.khoan = k
        k.unit = raw["unit"]
        k.unit_price = raw["unit_price"]
        k.cong_thuc_khoan = raw.get("cong_thuc_khoan")
        cu = {v.id: v for v in k.viec_phat_sinh if v.id is not None}
        moi: list[CongDoanKhoanPhatSinh] = []
        for i, dong in enumerate(raw.get("viec_phat_sinh") or []):
            vid = dong.get("id")
            v = cu.get(int(vid)) if vid else None
            if v is None:
                v = CongDoanKhoanPhatSinh()
            v.ten = dong["ten"]
            v.don_gia = dong["don_gia"]
            v.don_vi = dong["don_vi"]
            v.thu_tu = i
            moi.append(v)
        k.viec_phat_sinh = moi

    def _replace_may(self, cd: CongDoan, rows: list[dict]) -> None:
        """Thay TRỌN danh sách máy của công đoạn.

        `flush()` giữa xoá và thêm vì cùng lý do với `_replace_dinh_muc`: trong MỘT flush
        SQLAlchemy phát INSERT trước DELETE cho cùng bảng, nên giữ lại đúng một máy cũ là đụng
        `uq_cd_may` → 500.
        """
        if cd.may_lam_duoc:
            cd.may_lam_duoc.clear()
            if cd.id is not None:
                self.db.flush()
        for i, r in enumerate(rows):
            r = dict(r)
            r.pop("id", None)          # khoá chỉ-đọc của schema Row, client có thể gửi ngược lên
            r["thu_tu"] = i
            cd.may_lam_duoc.append(CongDoanMay(**r))

    def _replace_vat_tu(self, cd: CongDoan, rows: list[dict]) -> None:
        """Thay TRỌN danh sách vật tư (kèm công thức định mức từng món) của công đoạn.

        BẮT BUỘC `flush()` giữa xoá và thêm: trong MỘT flush, SQLAlchemy phát INSERT trước DELETE
        cho cùng một bảng, nên lưu lại đúng một vật tư cũ là đụng `uq_cong_doan_vat_tu` → 500
        (`duplicate key (cong_doan_id, vat_tu_id)`). Xoá bay đi trước rồi mới chèn thì cả hai
        đường — sửa công thức của dòng cũ và bỏ/thêm dòng — đều chạy."""
        if cd.vat_tus:
            cd.vat_tus.clear()
            if cd.id is not None:          # công đoạn mới chưa có id thì chưa có gì để xoá
                self.db.flush()
        for i, r in enumerate(rows):
            r = dict(r)
            r.pop("id", None)          # khoá chỉ-đọc của schema Row, client có thể gửi ngược lên
            cd.vat_tus.append(CongDoanVatTu(
                vat_tu_id=int(r["vat_tu_id"]), thu_tu=i,
                cong_thuc_luong=((r.get("cong_thuc_luong") or "").strip() or None),
            ))
