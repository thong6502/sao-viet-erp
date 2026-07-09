"""Unit test engine hình học bình bài (thuần, không DB) — spec §5/§6.

Golden chuẩn = §5.1 (name card → 40 con/tờ in). Các ví dụ khác của spec (§7.4=44,
§9.5=205/192) mâu thuẫn nhau nên KHÔNG dùng làm golden (xem docstring engine)."""
from __future__ import annotations

from app.services import imposition_engine as E


# ---------- §5.0 lõi hình học ----------
def test_fit_1d_basic():
    assert E._fit_1d(420, 94, 4) == 4      # ⌊424/98⌋
    assert E._fit_1d(630, 57, 4) == 10     # ⌊634/61⌋
    assert E._fit_1d(-5, 10, 4) == 0
    assert E._fit_1d(100, 0, 0) == 0


def test_usable_area():
    Wu, Lu = E.usable_area(430, 650, gripper_mm=12, side_margin_mm=5, tail_colorbar_mm=8)
    assert Wu == 420
    assert Lu == 630


def test_fit_count_orientation():
    # golden §5.1: n0=40 thắng n90=36
    count, rotated = E.fit_count(420, 630, 94, 57, gutter=4, allow_rotate=True)
    assert count == 40
    assert rotated is False
    # tắt xoay không đổi (n0 vốn thắng)
    count2, _ = E.fit_count(420, 630, 94, 57, gutter=4, allow_rotate=False)
    assert count2 == 40


def test_waste_pct():
    hao = E.waste_pct(40, 94 * 57, 430 * 650)
    assert 0.23 < hao < 0.24     # ~23.4%


# ---------- §5.1 step_repeat GOLDEN ----------
def _card_setup():
    rule = E.RuleVersion(layout_mode="step_repeat", side_margin_mm=5, tail_colorbar_mm=8,
                         gutter_mm=4, allow_rotate=True, bleed_default_mm=2)
    machine = E.Machine(gripper_mm=12, max_w=0, max_h=0)
    product = E.Product(rong_tp=90, dai_tp=53, bleed_mm=2)  # cell 94×57
    return rule, machine, product


def test_step_repeat_golden_40():
    rule, machine, product = _card_setup()
    lo = E.layout_step_repeat(430, 650, rule, machine, product)
    assert lo.don_vi == 40
    assert not any(w.severity == "error" for w in lo.warnings)


def test_step_repeat_gutter_up_reduces_count():
    """gutter 4→8: con giảm (spec §9.5: 40→36)."""
    rule, machine, product = _card_setup()
    base = E.layout_step_repeat(430, 650, rule, machine, product).don_vi
    rule.gutter_mm = 8
    wider = E.layout_step_repeat(430, 650, rule, machine, product).don_vi
    assert wider < base


def test_step_repeat_efit0():
    rule, machine, _ = _card_setup()
    big = E.Product(rong_tp=500, dai_tp=700, bleed_mm=2)  # lớn hơn tờ in
    lo = E.layout_step_repeat(430, 650, rule, machine, big)
    assert lo.don_vi == 0
    assert any(w.code == "E-FIT-0" and w.severity == "error" for w in lo.warnings)


def test_grain_locks_orientation():
    # C1: con dài, xoay 90° cho nhiều con hơn — nhưng ràng buộc thớ ⇒ CẤM xoay ⇒ giữ hướng gốc (ít hơn).
    base = dict(layout_mode="step_repeat", side_margin_mm=0, tail_colorbar_mm=0,
                gutter_mm=4, bleed_default_mm=0)
    machine = E.Machine(gripper_mm=0)
    product = E.Product(rong_tp=250, dai_tp=40)
    free = E.layout_step_repeat(600, 300, E.RuleVersion(allow_rotate=True, grain_constraint="none", **base),
                                machine, product)
    locked = E.layout_step_repeat(600, 300, E.RuleVersion(allow_rotate=True, grain_constraint="canh_dai", **base),
                                  machine, product)
    assert free.rotated and free.don_vi == 13    # tự do xoay → 13
    assert not locked.rotated and locked.don_vi == 12   # thớ khoá hướng → 12


# ---------- §5.3 nesting ----------
def test_nesting_golden_12():
    """§5.3: blank 250×180, tờ in 720×1020, grid, matrix 5 → 12 blank."""
    rule = E.RuleVersion(layout_mode="nesting", side_margin_mm=0, tail_colorbar_mm=0,
                         matrix_allowance_mm=5, allow_rotate=True)
    machine = E.Machine(gripper_mm=0)
    product = E.Product(blank_w=250, blank_h=180)
    # tờ in 1020×720 (rong=1020, dai=720) để usable = full sheet
    lo = E.layout_nesting(1020, 720, rule, machine, product)
    assert lo.don_vi == 12
    assert 0.25 < lo.hao_pct < 0.27       # ~26%


def test_nesting_missing_blank():
    rule = E.RuleVersion(layout_mode="nesting")
    lo = E.layout_nesting(1020, 720, rule, E.Machine(), E.Product())
    assert any(w.code == "E-MODE-REQ" for w in lo.warnings)


# ---------- §5.2 signature ----------
def test_signature_plates_and_sigs():
    """§5.2: A5 P=96, keo, 4/4, sheetwise, tay=16 → số_tay=6, kẽm=48."""
    rule = E.RuleVersion(layout_mode="signature", pages_per_sig=16, work_style="sheetwise")
    machine = E.Machine(gripper_mm=12, max_w=0)
    product = E.Product(rong_tp=148, dai_tp=210, so_trang=96, binding="perfect")
    lo = E.layout_signature(650, 900, rule, machine, product, so_mau=4)
    assert lo.so_tay == 6
    kem = E.compute_so_kem("signature", 4, 4, sides=2, so_tay=lo.so_tay, work_style="sheetwise")
    assert kem == 48
    # perfect (keo) → creep=0/None
    assert lo.creep_mm in (None, 0)


def test_signature_work_turn_halves_plates():
    kem_sheetwise = E.compute_so_kem("signature", 4, 4, 2, so_tay=6, work_style="sheetwise")
    kem_workturn = E.compute_so_kem("signature", 4, 4, 2, so_tay=6, work_style="work_turn")
    assert kem_sheetwise == 48
    assert kem_workturn == 24


def test_signature_w_p4_inserts_blanks():
    rule = E.RuleVersion(layout_mode="signature", pages_per_sig=8)
    product = E.Product(rong_tp=148, dai_tp=210, so_trang=94, binding="saddle")
    lo = E.layout_signature(650, 900, rule, E.Machine(gripper_mm=12), product, so_mau=4)
    assert any(w.code == "W-P4" for w in lo.warnings)
    # 94 → 96 (bội 4) → 12 tay F8
    assert lo.so_tay == 12


def test_signature_pages_max_warns():
    rule = E.RuleVersion(layout_mode="signature", pages_per_sig=8, max_pages=64)
    product = E.Product(rong_tp=148, dai_tp=210, so_trang=80, binding="saddle")
    lo = E.layout_signature(650, 900, rule, E.Machine(gripper_mm=12), product, so_mau=4)
    assert any(w.code == "W-PAGES-MAX" for w in lo.warnings)


def test_signature_missing_pages():
    rule = E.RuleVersion(layout_mode="signature", pages_per_sig=8)
    lo = E.layout_signature(650, 900, rule, E.Machine(), E.Product(rong_tp=148, dai_tp=210), so_mau=4)
    assert any(w.code == "E-MODE-REQ" for w in lo.warnings)


# ---------- xả giấy + resolve orchestrator ----------
def test_derive_print_sheets_respects_machine():
    raw = E.RawSheet(rong_ng=650, dai_ng=860)
    machine = E.Machine(max_w=740, max_h=0)   # khổ máy 740
    sheets = E.derive_print_sheets(raw, machine)
    assert sheets, "phải có ít nhất 1 ứng viên khổ tờ in"
    # mọi ứng viên phải nạp vừa máy
    for ps in sheets:
        assert E.fits_machine(ps.rong, ps.dai, machine)


def test_resolve_step_repeat_end_to_end():
    rule = E.RuleVersion(layout_mode="step_repeat", side_margin_mm=5, tail_colorbar_mm=8,
                         gutter_mm=4, allow_rotate=True, bleed_default_mm=2)
    machine = E.Machine(gripper_mm=12, max_w=0, max_h=0)
    product = E.Product(rong_tp=90, dai_tp=53, bleed_mm=2)
    raw = E.RawSheet(rong_ng=430, dai_ng=650, gsm=150, gia_kg=30000)
    res = E.resolve(rule, machine, product, raw, so_luong=10000, so_mau_truoc=4, so_mau_sau=4)
    # 1 tờ in / tờ nguyên (430×650 vừa máy), 40 con/tờ
    assert res.don_vi_per_to_in == 40
    assert res.so_to_in == 250            # ceil(10000/40)
    assert res.so_kem == 8                # 4 trước + 4 sau
    assert not res.has_error


def test_resolve_picks_best_cut():
    """Xả giấy chọn cách cắt cho NHIỀU con/tờ nguyên nhất."""
    rule = E.RuleVersion(layout_mode="step_repeat", bleed_default_mm=2, allow_rotate=True)
    machine = E.Machine(gripper_mm=10, max_w=500, max_h=800)
    product = E.Product(rong_tp=90, dai_tp=53, bleed_mm=2)
    raw = E.RawSheet(rong_ng=650, dai_ng=860)
    res = E.resolve(rule, machine, product, raw, so_luong=5000, so_mau_truoc=4)
    assert res.kho_to_in is not None
    assert res.tong_don_vi_per_nguyen >= res.don_vi_per_to_in
    assert not res.has_error
