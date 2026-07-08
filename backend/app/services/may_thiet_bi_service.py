"""Máy thiết bị — service: CRUD + validate (§8) + compute_bhr (§4.2).

BHR = đơn giá giờ máy GIÁ VỐN. Mọi chi phí ĐỨNG (khấu hao/lãi vốn/bảo hiểm/mặt bằng/lương/
bảo trì/overhead) chia CÙNG `gio_tinh_phi`; chỉ điện (chạy) theo giờ chạy. Lãi vốn trên VỐN
BÌNH QUÂN. BHR LOẠI TRỪ giấy + mực. Khớp ví dụ §4.3 (offset 74 → BHR ≈ 897k).
"""
from __future__ import annotations

from decimal import Decimal

from ..models.may_thiet_bi import KHOA_CLASS, LOAI_MAY, MayThietBi
from ..repositories.may_thiet_bi_repo import MayThietBiRepository


class MayThietBiError(Exception):
    pass


class MayThietBiValidationError(MayThietBiError):
    pass


class MayThietBiDuplicate(MayThietBiError):
    pass


class MayThietBiNotFound(MayThietBiError):
    pass


def _f(v, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def compute_bhr(may: MayThietBi) -> dict:
    """Trả breakdown BHR (§4.2). Nếu nguon_bhr='nhap_truc_tiep' → dùng thẳng don_gia_gio_BHR.

    Raise MayThietBiValidationError khi gio_tinh_phi ≤ 0 (E-MAY-BHR0).
    """
    if (may.nguon_bhr or "dung_tu_von") == "nhap_truc_tiep":
        bhr = _f(may.don_gia_gio_BHR)
        if bhr <= 0:
            raise MayThietBiValidationError("Đơn giá giờ BHR (nhập trực tiếp) phải > 0. [E-MAY-BHR0]")
        markup = _f(may.markup_pct) / 100.0
        return {"gio_tinh_phi": None, "breakdown": {"nhap_truc_tiep": bhr},
                "BHR": round(bhr, 2), "don_gia_ban_gio": round(bhr * (1 + markup), 2)}

    gio_tinh_phi = _f(may.gio_lam_nam) * (_f(may.availability_pct) / 100.0) * (_f(may.productivity_pct) / 100.0)
    if gio_tinh_phi <= 0:
        raise MayThietBiValidationError(
            "Giờ tính phí ≤ 0 (gio_lam_nam × availability × productivity). [E-MAY-BHR0]"
        )

    von = _f(may.von_dau_tu)
    thu_hoi = _f(may.gia_tri_thu_hoi)
    # --- chi phí ĐỨNG (÷ cùng gio_tinh_phi) ---
    khau_hao = (von - thu_hoi) / (max(_f(may.nam_khau_hao), 1) * gio_tinh_phi) if von else 0.0
    lai_von = ((von + thu_hoi) / 2.0 * (_f(may.lai_von_pct) / 100.0)) / gio_tinh_phi if von else 0.0
    bao_hiem = _f(may.bao_hiem_nam) / gio_tinh_phi
    mat_bang = (_f(may.dien_tich_san_m2) * _f(may.don_gia_thue_m2_nam)) / gio_tinh_phi
    lao_dong = _f(may.luong_gio) * (1 + _f(may.luong_burden_pct) / 100.0) \
        * _f(may.so_nhan_cong, 1.0) / max(_f(may.so_may_song_song, 1.0), 1.0)
    bao_tri = _f(may.bao_tri_gio)
    overhead = _f(may.overhead_gio)
    # --- chi phí CHẠY (theo giờ chạy thực) ---
    dien = _f(may.cong_suat_kW) * _f(may.he_so_tai_dien, 0.65) * _f(may.don_gia_dien)

    breakdown = {
        "khau_hao_gio": round(khau_hao, 2), "lai_von_gio": round(lai_von, 2),
        "bao_hiem_gio": round(bao_hiem, 2), "mat_bang_gio": round(mat_bang, 2),
        "lao_dong_gio": round(lao_dong, 2), "bao_tri_gio": round(bao_tri, 2),
        "overhead_gio": round(overhead, 2), "dien_gio": round(dien, 2),
    }
    bhr = sum(breakdown.values())
    markup = _f(may.markup_pct) / 100.0
    return {"gio_tinh_phi": round(gio_tinh_phi, 2), "breakdown": breakdown,
            "BHR": round(bhr, 2), "don_gia_ban_gio": round(bhr * (1 + markup), 2)}


class MayThietBiService:
    def __init__(self, repo: MayThietBiRepository) -> None:
        self.repo = repo

    # -- validate (§8) --
    def _validate(self, data: dict, *, self_id: int | None = None) -> None:
        if not (data.get("ma") or "").strip():
            raise MayThietBiValidationError("Mã máy không được trống.")
        if not (data.get("ten") or "").strip():
            raise MayThietBiValidationError("Tên máy không được trống.")
        if data.get("loai_may") not in LOAI_MAY:
            raise MayThietBiValidationError("Loại máy (loai_may) không hợp lệ.")
        if data.get("khoa_class") not in (None, "") and data.get("khoa_class") not in KHOA_CLASS:
            raise MayThietBiValidationError("khoa_class không hợp lệ.")

        kmaxd, kmaxr = data.get("kho_max_dai"), data.get("kho_max_rong")
        kmind, kminr = data.get("kho_min_dai"), data.get("kho_min_rong")
        if kmind and kmaxd and kmind > kmaxd:
            raise MayThietBiValidationError("Khổ min (dài) > khổ max. [E-MAY-KHO]")
        if kminr and kmaxr and kminr > kmaxr:
            raise MayThietBiValidationError("Khổ min (rộng) > khổ max. [E-MAY-KHO]")
        gr, minr = data.get("gripper_mm"), data.get("kho_min_rong")
        if gr and minr and gr >= minr:
            raise MayThietBiValidationError("Nhíp (gripper) ≥ khổ min (rộng). [E-MAY-NHIP]")

        toc_do = data.get("toc_do")
        dvtd = data.get("don_vi_toc_do")
        if toc_do is not None and _f(toc_do) <= 0:
            raise MayThietBiValidationError("Tốc độ phải > 0. [E-MAY-SPEED]")
        # BHR ≤ 0 kiểm khi tính (compute_bhr) — dữ liệu chưa đủ vẫn cho lưu nháp.
        if (data.get("nguon_bhr") or "dung_tu_von") == "nhap_truc_tiep":
            if _f(data.get("don_gia_gio_BHR")) <= 0:
                raise MayThietBiValidationError("Nhập trực tiếp BHR: đơn giá giờ phải > 0. [E-MAY-BHR0]")
        _ = dvtd  # đơn vị tốc độ khớp loai_may — cảnh báo mềm, không chặn ở MVP.

    # -- reads --
    def get(self, may_id: int) -> MayThietBi:
        m = self.repo.get(may_id)
        if m is None:
            raise MayThietBiNotFound("Không tìm thấy máy.")
        return m

    def list(self, **kw):
        return self.repo.list(**kw)

    # -- writes --
    def create(self, data: dict) -> MayThietBi:
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise MayThietBiDuplicate("Mã máy đã tồn tại.")
        return self.repo.create(data)

    def update(self, may_id: int, data: dict) -> MayThietBi:
        m = self.get(may_id)
        self._validate(data, self_id=m.id)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != m.id:
            raise MayThietBiDuplicate("Mã máy đã tồn tại.")
        return self.repo.update(m, data)

    def delete(self, may_id: int) -> None:
        m = self.get(may_id)
        self.repo.delete(m)

    def bhr(self, may_id: int) -> dict:
        return compute_bhr(self.get(may_id))
