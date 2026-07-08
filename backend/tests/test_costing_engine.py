"""Engine tính giá — §6 lắp ráp (golden), §5.2 passes, smoke 1 component (name card §7A)."""
import pytest

from app.services import imposition_engine as impo
from app.services import costing_engine as ce


# --- §6 lắp ráp báo giá (deterministic golden) ---
def test_assemble_markup_vs_margin():
    # markup 20% trên vốn: 100 → 120
    r1 = ce.assemble_quote(100, so_luong=1, kieu_lai="markup_tren_von", he_so_lai_pct=20, vat_rate=0)
    assert r1["gia_net"] == 120.0
    # margin 20% trên giá bán: 100 → 100/0.8 = 125
    r2 = ce.assemble_quote(100, so_luong=1, kieu_lai="margin_tren_gia_ban", he_so_lai_pct=20, vat_rate=0)
    assert r2["gia_net"] == 125.0


def test_assemble_vat_after_discount_and_moq():
    # VAT trên net SAU chiết khấu: vốn 1000, ck 10%, VAT 8% → net 900, VAT 72, bán 972
    r = ce.assemble_quote(1000, so_luong=1, chiet_khau_pct=10, vat_rate=8)
    assert r["gia_net"] == 900.0 and r["vat"] == 72.0 and r["gia_ban"] == 972.0
    # sàn MOQ trên net TRƯỚC VAT
    r2 = ce.assemble_quote(1000, so_luong=1, don_toi_thieu=5000, vat_rate=8)
    assert r2["moq_applied"] is True and r2["gia_net"] == 5000.0 and r2["gia_ban"] == 5400.0


def test_assemble_golden_7a():
    # §7A: giá vốn 2.708.000 → +overhead 15% → markup 20% → VAT 8%
    r = ce.assemble_quote(2_708_000, so_luong=10_000, overhead_cty_pct=15,
                          kieu_lai="markup_tren_von", he_so_lai_pct=20, vat_rate=8)
    # 2708000×1.15×1.20×1.08 = 4.036.003,2 ; đơn giá ~404đ/cái
    assert abs(r["gia_ban"] - 4_036_003.2) < 1.0
    assert round(r["don_gia_ban"]) == 404


# --- §5.2 passes ---
def test_passes():
    assert ce.compute_passes(4, 4, 4) == 2                        # sheetwise 4/4, units 4
    assert ce.compute_passes(4, 0, 4) == 1                        # 1 mặt 4 màu
    assert ce.compute_passes(4, 4, 4, work_style="work_turn") == 2  # tự trở
    assert ce.compute_passes(6, 0, 4) == 2                        # 6 màu, units 4 → 2 lượt


# --- smoke 1 component: name card 4/4 Couché 300, máy khổ 74 ---
def test_component_name_card():
    rule = impo.RuleVersion(layout_mode="step_repeat", gutter_mm=4, side_margin_mm=5, tail_colorbar_mm=8)
    machine = impo.Machine(gripper_mm=12, max_w=530, max_h=740, min_w=210, min_h=280)
    product = impo.Product(rong_tp=53, dai_tp=90, bleed_mm=2)
    raw = impo.RawSheet(rong_ng=650, dai_ng=860, gsm=300, gia_kg=30000)
    cong_doan_in = {"che_do_tinh": "theo_san_luong", "pricing_basis": "per_1000_luot",
                    "run_rate": 8000, "first_unit_floor": 350000}
    c = ce.compute_component(rule=rule, machine=machine, product=product, raw=raw,
                             so_luong=10000, so_mau_truoc=4, so_mau_sau=4,
                             don_gia_kem=100000, don_gia_muc=8000, so_units=4,
                             cong_doan_in=cong_doan_in)
    assert not c.get("error")
    assert c["imposition"]["so_kem"] == 8            # 4/4 flat → 8 kẽm
    assert c["tien_kem"] == 800000.0                 # 8 × 100k
    assert c["imposition"]["don_vi_per_to_in"] > 0   # có con/tờ
    assert c["so_to_in_gross"] > c["imposition"]["so_to_in"]  # gross > net (đã bù hao)
    assert c["tien_giay"] > 0 and c["tien_in"] >= 350000      # sàn in
    assert c["tong"] == pytest.approx(
        c["tien_giay"] + c["tien_kem"] + c["tien_muc"] + c["tien_in"] + c["tien_gia_cong"], abs=1)


def test_compute_costing_wraps_components():
    comp = {"tong": 2_558_000.0}
    out = ce.compute_costing(components=[comp], chi_phi_khac=150000, so_luong=10000,
                             quote={"overhead_cty_pct": 15, "he_so_lai_pct": 20, "vat_rate": 8})
    assert out["gia_von"] == 2_708_000.0             # 2.558.000 + chế bản 150k
    assert abs(out["gia_ban"] - 4_036_003.2) < 1.0
