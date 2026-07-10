"""Repository — Máy thiết bị. CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.may_thiet_bi import MayThietBi

# Field client được phép gán (ma chuẩn hoá riêng; id/created/updated do server quản).
ASSIGNABLE = (
    "ten", "loai_may", "finishing_subtype", "nhom_cost_center", "phong_ban_id", "dia_diem",
    "hang_san_xuat", "model", "so_seri", "trang_thai", "ghi_chu", "ghi_chu_2",
    "ma_tai_san", "ma_TK_cost_center", "nha_cung_cap", "ngay_dua_vao_su_dung",
    "het_han_bao_hanh", "phuong_phap_khau_hao",
    "nguon_bhr", "don_gia_gio_BHR", "von_dau_tu", "gia_tri_thu_hoi", "nam_khau_hao",
    "lai_von_pct", "gio_lam_nam", "availability_pct", "productivity_pct", "efficiency_pct",
    "so_nhan_cong", "luong_gio", "luong_burden_pct", "cong_suat_kW", "he_so_tai_dien",
    "don_gia_dien", "bao_hiem_nam", "dien_tich_san_m2", "don_gia_thue_m2_nam", "bao_tri_gio",
    "overhead_gio", "markup_pct", "ngay_cap_nhat_bhr",
    "toc_do", "don_vi_toc_do", "makeready_time_default", "thoi_gian_rua_muc", "min_stock_gsm",
    "max_stock_gsm", "vat_lieu_ho_tro_class", "so_may_song_song", "so_ca", "chi_so_dem_luot",
    "ngay_bao_tri_gan_nhat", "chu_ky_bao_tri", "chu_ky_bao_tri_don_vi", "ngay_bao_tri_ke_tiep",
    "kho_max_dai", "kho_max_rong", "kho_min_dai", "kho_min_rong",
    "kho_kem_dai", "kho_kem_rong", "vung_in_dai", "vung_in_rong", "gripper_mm", "le_hong_mm",
    "duoi_thang_mau_mm", "so_units", "units_truoc", "units_sau", "khoa_class", "co_tro_mat",
    "cho_phep_tu_tro", "cho_phep_tro_dau_duoi", "bu_hao_canh_may_per_mau", "bu_hao_chay_pct",
    "ho_tro_cip3", "fields_theo_loai",
)


class MayThietBiRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, may_id: int) -> MayThietBi | None:
        return self.db.get(MayThietBi, may_id)

    def find_by_ma(self, ma: str) -> MayThietBi | None:
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(
            select(MayThietBi).where(func.upper(MayThietBi.ma) == ma)
        ).scalars().first()

    def list(self, *, q: str | None = None, loai_may: str | None = None,
             trang_thai: str | None = None, page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(MayThietBi.ma).like(like),
                             func.lower(MayThietBi.ten).like(like)))
        if loai_may:
            conds.append(MayThietBi.loai_may == loai_may)
        if trang_thai:
            conds.append(MayThietBi.trang_thai == trang_thai)
        base = select(MayThietBi)
        count_stmt = select(func.count()).select_from(MayThietBi)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.order_by(MayThietBi.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # -- writes --
    def _apply(self, may: MayThietBi, data: dict) -> None:
        for k in ASSIGNABLE:
            if k in data:
                setattr(may, k, data[k])

    def create(self, data: dict) -> MayThietBi:
        may = MayThietBi(ma=data["ma"].strip().upper())
        self._apply(may, data)
        self.db.add(may)
        self.db.commit()
        self.db.refresh(may)
        return may

    def update(self, may: MayThietBi, data: dict) -> MayThietBi:
        if data.get("ma"):
            may.ma = data["ma"].strip().upper()
        self._apply(may, data)
        self.db.commit()
        self.db.refresh(may)
        return may

    def delete(self, may: MayThietBi) -> None:
        self.db.delete(may)
        self.db.commit()
