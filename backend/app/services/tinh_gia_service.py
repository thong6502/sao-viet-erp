"""Tính giá — service resolve master data (theo id) → input engine → costing_engine.

Nối các danh mục rebuild vào bộ não `costing_engine` để RA GIÁ THẬT (chưa nối Báo giá).
Phạm vi: FLAT / 1 bộ phận. Thiếu mặt hàng Kho/máy/giấy → lỗi (E-TG-*), KHÔNG tính 0.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.cong_doan import CongDoan
from ..models.loai_san_pham import LoaiSanPham
from ..models.may_thiet_bi import MayThietBi
from ..models.quy_tac_binh_bai import QuyTacBinhBai, QuyTacBinhBaiVersion
from ..models.vat_lieu_kho import BanKem, GiayNguyen, Muc
from ..services import costing_engine as ce
from ..services import imposition_engine as impo


class TinhGiaError(Exception):
    pass


def _f(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# Field RuleVersion (dataclass) lấy từ QuyTacBinhBaiVersion.
_RULE_FIELDS = (
    "layout_mode", "side_margin_mm", "tail_colorbar_mm", "gutter_mm", "allow_rotate",
    "grain_constraint", "bleed_default_mm", "allow_gang", "min_gutter_mm", "pages_per_sig",
    "work_style", "nest_method", "matrix_allowance_mm", "lanes", "gap_around_mm",
    "min_pages", "max_pages", "min_spine_mm", "warn_on_grain_violation",
)


class TinhGiaService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _current_rule(self, rule_id: int | None) -> impo.RuleVersion:
        """RuleVersion đang hiệu lực của 1 quy tắc bình bài; None ⇒ mặc định step_repeat."""
        if not rule_id:
            return impo.RuleVersion()
        v = self.db.execute(
            select(QuyTacBinhBaiVersion)
            .where(QuyTacBinhBaiVersion.rule_id == rule_id, QuyTacBinhBaiVersion.is_current.is_(True))
        ).scalars().first()
        if v is None:
            return impo.RuleVersion()
        kw = {}
        for f in _RULE_FIELDS:
            val = getattr(v, f, None)
            if val is None:
                continue
            # số → float; bool/str giữ nguyên
            if f in ("layout_mode", "grain_constraint", "work_style", "nest_method"):
                kw[f] = val
            elif f in ("allow_rotate", "allow_gang", "warn_on_grain_violation"):
                kw[f] = bool(val)
            elif f in ("pages_per_sig", "lanes", "min_pages", "max_pages"):
                kw[f] = int(val)
            else:
                kw[f] = _f(val)
        return impo.RuleVersion(**kw)

    def _machine(self, may_id: int) -> tuple[impo.Machine, MayThietBi]:
        m = self.db.get(MayThietBi, may_id)
        if m is None:
            raise TinhGiaError("Không tìm thấy máy. [E-TG-KHO-MISS]")
        mac = impo.Machine(
            gripper_mm=_f(m.gripper_mm, 12), max_w=_f(m.kho_max_rong), max_h=_f(m.kho_max_dai),
            min_w=_f(m.kho_min_rong), min_h=_f(m.kho_min_dai),
        )
        return mac, m

    def _raw(self, giay_id: int) -> impo.RawSheet:
        g = self.db.get(GiayNguyen, giay_id)
        if g is None:
            raise TinhGiaError("Không tìm thấy giấy trong Kho. [E-TG-KHO-MISS]")
        return impo.RawSheet(rong_ng=_f(g.kho_rong), dai_ng=_f(g.kho_dai), gsm=_f(g.gsm),
                             gia_kg=_f(g.don_gia), tho=g.tho or "none")

    def _don_gia_kem(self, khoa_class: str | None) -> float:
        if not khoa_class:
            return 0.0
        b = self.db.execute(select(BanKem).where(BanKem.khoa_class == khoa_class)).scalars().first()
        return _f(b.don_gia_kem) if b else 0.0

    def _don_gia_muc(self) -> float:
        m = self.db.execute(select(Muc).where(Muc.loai_muc == "process")).scalars().first()
        return _f(m.don_gia) if m else 0.0

    def _routing(self, template: list | None):
        """Trả (cong_doan_in dict | None, [finishing step dicts]) từ routing_template ids."""
        cong_doan_in = None
        steps = []
        for cid in (template or []):
            cd = self.db.get(CongDoan, cid)
            if cd is None:
                continue
            cfg = {"ma": cd.ma, "che_do_tinh": cd.che_do_tinh, "pricing_basis": cd.pricing_basis,
                   "setup_cost": _f(cd.setup_cost), "run_rate": _f(cd.run_rate),
                   "rate_tiers": cd.rate_tiers, "first_unit_floor": _f(cd.first_unit_floor) or None,
                   "min_charge": _f(cd.min_charge) or None, "setup_time": _f(cd.setup_time),
                   "nhom": cd.nhom}
            if cd.nhom == "print" and cong_doan_in is None:
                cong_doan_in = cfg
            elif cd.nhom == "finishing":
                steps.append(cfg)
        return cong_doan_in, steps

    def preview(self, data: dict) -> dict:
        """data: loai_san_pham_id?, may_id, giay_id, so_luong, so_mau_truoc/sau, rong_tp, dai_tp,
        bleed_mm?, chi_phi_khac?, + quote(overhead_cty_pct/kieu_lai/he_so_lai_pct/chiet_khau_pct/
        don_toi_thieu/vat_rate)."""
        may_id = data.get("may_id")
        giay_id = data.get("giay_id")
        if not may_id or not giay_id:
            raise TinhGiaError("Cần chọn Máy + Giấy để tính giá.")

        sp = self.db.get(LoaiSanPham, data["loai_san_pham_id"]) if data.get("loai_san_pham_id") else None
        rule = self._current_rule(getattr(sp, "imposition_rule_id", None))
        mac, may = self._machine(may_id)
        raw = self._raw(giay_id)
        product = impo.Product(
            rong_tp=_f(data.get("rong_tp")), dai_tp=_f(data.get("dai_tp")),
            bleed_mm=_f(data.get("bleed_mm")) or None,
        )
        cong_doan_in, steps = self._routing(getattr(sp, "routing_template", None))
        so_mau_truoc = int(data.get("so_mau_truoc", 4))
        so_mau_sau = int(data.get("so_mau_sau", 0))

        comp = ce.compute_component(
            rule=rule, machine=mac, product=product, raw=raw,
            so_luong=int(data.get("so_luong", 0)), so_mau_truoc=so_mau_truoc, so_mau_sau=so_mau_sau,
            don_gia_kem=self._don_gia_kem(may.khoa_class), don_gia_muc=self._don_gia_muc(),
            so_units=int(may.so_units or 4),
            bu_hao_canh_may_per_mau=_f(may.bu_hao_canh_may_per_mau, 100),
            bu_hao_chay_pct=_f(may.bu_hao_chay_pct, 2),
            cong_doan_in=cong_doan_in, routing_steps=steps,
        )
        quote = dict(data.get("quote") or {})
        if sp is not None and "vat_rate" not in quote:
            quote["vat_rate"] = _f(sp.vat_rate, 8)
        out = ce.compute_costing(
            components=[comp], chi_phi_khac=_f(data.get("chi_phi_khac")),
            so_luong=int(data.get("so_luong", 0)), quote=quote,
        )
        out["loai_san_pham"] = sp.ten if sp else None
        out["may"] = may.ten
        return out
