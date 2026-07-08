"""Engine TÍNH GIÁ (costing) — ráp giá vốn → giá bán, spec `docs/spec-tinh-gia.md` §4–§6.

Bộ não integrator: gọi `imposition_engine.resolve` (bình bài) + `routing_engine` (hao/step/kẽm)
+ tra giá (kẽm/mực/giấy) → dòng chi phí mỗi component → §6 lắp ráp thương mại.

Phạm vi hiện tại: FLAT / 1 bộ phận (golden §7A name card) + §6 đầy đủ (markup vs margin,
VAT sau chiết khấu, sàn MOQ trước VAT, làm tròn 1 LẦN cuối). Đa bộ phận (ruột+bìa §4.0/§4.7),
box/label, jobspec/component persistence = follow-up.
"""
from __future__ import annotations

from math import ceil

from . import imposition_engine as impo
from . import routing_engine as rte


def _f(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# --- §5.2 công in: số lượt qua máy ---------------------------------------
def compute_passes(so_mau_truoc: int, so_mau_sau: int, so_units: int, *,
                   work_style: str = "sheetwise", perfector: bool = False,
                   units_truoc: int = 0, units_sau: int = 0) -> int:
    """passes = số lượt tờ qua máy (§5.2). units ≤ 0 ⇒ coi như đủ (1 lượt/mặt)."""
    u = max(int(so_units or 0), 0)
    mt, ms = int(so_mau_truoc or 0), int(so_mau_sau or 0)
    if work_style == "work_turn":          # tự trở: 2 lượt (1 bộ kẽm, canh máy ×1)
        return 2
    if perfector:                          # in 2 mặt 1 lượt nếu đủ units mỗi mặt
        ok = (mt <= (units_truoc or u)) and (ms <= (units_sau or u))
        return 1 if ok else 1 + (0 if ms == 0 else 1)
    def _p(mau: int) -> int:
        return 0 if mau <= 0 else (ceil(mau / u) if u > 0 else 1)
    return _p(mt) + _p(ms)


# --- §6 LẮP RÁP BÁO GIÁ (thương mại) — làm tròn 1 LẦN cuối ---------------
def assemble_quote(gia_von: float, *, so_luong: int, overhead_cty_pct: float = 0.0,
                   kieu_lai: str = "markup_tren_von", he_so_lai_pct: float = 0.0,
                   chiet_khau_pct: float = 0.0, don_toi_thieu: float = 0.0,
                   vat_rate: float = 8.0) -> dict:
    """§6.1: giá thành → lãi (§6.2 markup/margin) → chiết khấu → sàn MOQ → VAT.
    KHÔNG làm tròn giữa chừng; chỉ round(gia_net, VAT, gia_ban) ở bước CUỐI (§6.1)."""
    gia_von = _f(gia_von)
    gia_thanh = gia_von * (1 + _f(overhead_cty_pct) / 100.0)          # G&A công ty (§6.4 tranche riêng)
    r = _f(he_so_lai_pct) / 100.0
    if kieu_lai == "margin_tren_gia_ban":
        gia_truoc_ck = gia_thanh / (1 - r) if r < 1 else gia_thanh    # margin trên giá bán
    else:
        gia_truoc_ck = gia_thanh * (1 + r)                           # markup trên vốn
    gia_net = gia_truoc_ck * (1 - _f(chiet_khau_pct) / 100.0)         # chiết khấu THƯƠNG MẠI (trong base VAT)
    moq_applied = gia_net < _f(don_toi_thieu)
    gia_net = max(gia_net, _f(don_toi_thieu))                         # SÀN MOQ (trên net TRƯỚC VAT)
    vat = gia_net * _f(vat_rate) / 100.0
    gia_ban = gia_net + vat
    q = max(int(so_luong or 0), 1)
    return {
        "gia_von": round(gia_von, 2),
        "gia_thanh": round(gia_thanh, 2),
        "gia_net": round(gia_net, 2),
        "moq_applied": moq_applied,
        "vat": round(vat, 2),
        "vat_rate": _f(vat_rate),
        "gia_ban": round(gia_ban, 2),
        "don_gia_ban": round(gia_ban / q, 2),
    }


# --- 1 component sheet: bình bài → hao → dòng chi phí (§4.4–4.6) ----------
def compute_component(*, rule: impo.RuleVersion, machine: impo.Machine, product: impo.Product,
                      raw: impo.RawSheet, so_luong: int, so_mau_truoc: int, so_mau_sau: int,
                      don_gia_kem: float, don_gia_muc: float = 0.0,
                      bu_hao_canh_may_per_mau: float = 100, bu_hao_chay_pct: float = 2.0,
                      so_units: int = 4, cong_doan_in: dict | None = None,
                      routing_steps: list[dict] | None = None) -> dict:
    """Trả breakdown 1 bộ phận + `tong` (Σ dòng). so_luong = SL thành phẩm của component."""
    imp = impo.resolve(rule, machine, product, raw, so_luong, so_mau_truoc, so_mau_sau)
    warns = [{"code": w.code, "message": w.message, "severity": w.severity} for w in imp.warnings]
    if imp.has_error or not imp.so_to_in:
        return {"error": True, "warnings": warns, "imposition": _imp_dict(imp)}

    sides = 2 if so_mau_sau > 0 else 1
    so_mau_total = int(so_mau_truoc) + int(so_mau_sau)
    # ③ tờ in gross = net + bù hao máy (theo số màu) + %chạy — bù hao chỉ từ MÁY (§4.4)
    so_to_in_gross = rte.so_to_in_gross(imp.so_to_in, so_mau=max(so_mau_total, 1),
                                        bu_hao_canh_may_per_mau=bu_hao_canh_may_per_mau,
                                        bu_hao_chay_pct=bu_hao_chay_pct)
    so_to_nguyen = ceil(so_to_in_gross / imp.to_in_per_nguyen) if imp.to_in_per_nguyen else so_to_in_gross

    # ⑦ GIẤY — cân theo TỜ NGUYÊN (khổ lớn), dims mm → cm
    dai_cm, rong_cm = raw.dai_ng / 10.0, raw.rong_ng / 10.0
    kg = dai_cm * rong_cm * raw.gsm * so_to_nguyen / 10_000_000.0
    tien_giay = kg * raw.gia_kg

    # ⑧ KẼM
    tien_kem = imp.so_kem * _f(don_gia_kem)

    # ⑩⑪ IN — passes × gross = lượt; per_1000 (sàn) hoặc BHR
    passes = compute_passes(so_mau_truoc, so_mau_sau, so_units, work_style=rule.work_style)
    so_luot = so_to_in_gross * passes
    if cong_doan_in:
        r_in = rte.compute_step_cost(cong_doan_in, {"so_luot": so_luot, "so_to_in_gross": so_to_in_gross})
        tien_in = r_in["total"]
    else:
        tien_in = 0.0

    # ⑨ MỰC — đơn giá × (lượt/1000) × số màu (cả 2 mặt)
    tien_muc = _f(don_gia_muc) * (so_luot / 1000.0) * max(so_mau_total, 1)

    # ⑫ GIA CÔNG — routing steps (cascade hao đã ở caller nếu cần; ở đây tính per-step theo gross)
    tien_gia_cong = 0.0
    steps_out = []
    for st in (routing_steps or []):
        ctx = {"so_to_in_gross": so_to_in_gross, "so_luot": so_luot,
               "dt_to_in_m2": (imp.kho_to_in.rong / 1000.0) * (imp.kho_to_in.dai / 1000.0) if imp.kho_to_in else 0,
               "so_mat": sides, "so_cuon": so_luong, "so_con": so_luong}
        r_st = rte.compute_step_cost(st, ctx, tooling_one_time=_f(st.get("tooling_one_time")),
                                     reuse_tooling=bool(st.get("reuse_tooling")))
        tien_gia_cong += r_st["total"]
        steps_out.append({"ma": st.get("ma"), **r_st})

    tong = round(tien_giay + tien_kem + tien_muc + tien_in + tien_gia_cong, 2)
    return {
        "imposition": _imp_dict(imp),
        "so_to_in_gross": so_to_in_gross, "so_to_nguyen": so_to_nguyen, "kg_giay": round(kg, 3),
        "so_luot": so_luot, "passes": passes,
        "tien_giay": round(tien_giay, 2), "tien_kem": round(tien_kem, 2), "tien_muc": round(tien_muc, 2),
        "tien_in": round(tien_in, 2), "tien_gia_cong": round(tien_gia_cong, 2),
        "gia_cong_steps": steps_out, "tong": tong, "warnings": warns,
    }


def _imp_dict(imp: impo.ImpositionResult) -> dict:
    return {"layout_mode": imp.layout_mode, "don_vi_per_to_in": imp.don_vi_per_to_in,
            "to_in_per_nguyen": imp.to_in_per_nguyen, "so_to_in": imp.so_to_in,
            "so_to_nguyen": imp.so_to_nguyen, "so_kem": imp.so_kem, "so_tay": imp.so_tay,
            "hao_hinh_hoc_pct": imp.hao_hinh_hoc_pct}


def compute_costing(*, components: list[dict], chi_phi_khac: float = 0.0, so_luong: int,
                    quote: dict | None = None) -> dict:
    """Ráp nhiều component (hiện flat=1) + chi phí chung (chế bản…) → §6 báo giá."""
    gia_von = sum(c.get("tong", 0.0) for c in components if not c.get("error")) + _f(chi_phi_khac)
    q = assemble_quote(gia_von, so_luong=so_luong, **(quote or {}))
    return {"components": components, "chi_phi_khac": _f(chi_phi_khac), **q}
