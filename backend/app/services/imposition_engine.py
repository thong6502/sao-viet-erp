"""Imposition geometry engine — thuần hình học, KHÔNG DB, KHÔNG tính tiền.

Đây là "mắt xích đầu" của engine tính giá (spec `docs/spec-quy-tac-binh-bai.md` §5/§6):
nhận rule_version + máy in + sản phẩm + tờ nguyên → trả **số con / tay / blank trên 1 tờ in**,
số tờ in / tờ nguyên, số kẽm, %hao hình học, cảnh báo. Con số này chảy vào các dòng chi phí
ở `pricing_engine` (§7) — nhưng module NÀY không tính tiền (ranh giới §13).

ĐƠN VỊ: tất cả kích thước là **mm** (nội bộ nhất quán). Caller tự quy đổi cm→mm.

Golden chuẩn (spec §5.1): name card 90×53 (+2 bleed) → cell 94×57; tờ in 430×650, nhíp 12,
lề 5, thang màu 8, gutter 4 → usable 420×630 → n0 = ⌊424/98⌋×⌊634/61⌋ = 4×10 = 40 con.
⚠ Spec tự mâu thuẫn số ở vài chỗ (§5.1=40 con vs §7.4=44 vs §9.5 tờ nguyên 205 vs 192).
   Ta lấy **§5.1 (40 con) làm chuẩn** và KHÔNG cố khớp các ví dụ lệch nhau.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, floor
from typing import Optional

# --- Enums (khớp cột model version) ---------------------------------------
LAYOUT_MODES = ("step_repeat", "signature", "nesting", "repeat_around")
GRAIN_CONSTRAINTS = ("none", "canh_dai", "song_song_gay", "theo_song")
WORK_STYLES = ("sheetwise", "work_turn")
NEST_METHODS = ("grid", "true_shape")
# binding (đến từ Sản phẩm) — quyết cách xếp tay + creep
BINDINGS = ("saddle", "perfect", "sewn")


# --- §6 I/O dataclasses ----------------------------------------------------
@dataclass
class RuleVersion:
    """Cấu hình quy tắc (1 version). Mọi field ảnh hưởng giá (§7.3)."""
    layout_mode: str = "step_repeat"
    # Hình học chung (mọi mode)
    side_margin_mm: float = 5.0
    tail_colorbar_mm: float = 8.0
    gutter_mm: float = 4.0
    allow_rotate: bool = True
    grain_constraint: str = "none"
    bleed_default_mm: float = 3.0
    # A. step_repeat
    allow_gang: bool = False
    min_gutter_mm: float = 4.0
    # B. signature
    pages_per_sig: Optional[int] = None  # None = auto
    work_style: str = "sheetwise"
    # C. nesting
    nest_method: str = "grid"
    matrix_allowance_mm: float = 5.0
    # D. repeat_around
    lanes: Optional[int] = None  # None = auto
    gap_around_mm: float = 3.0
    # Guardrails
    min_pages: Optional[int] = None
    max_pages: Optional[int] = None
    min_spine_mm: Optional[float] = None
    warn_on_grain_violation: bool = True


@dataclass
class Machine:
    """Từ Máy in (§13). max_*/min_* = 0 ⇒ không giới hạn chiều đó."""
    gripper_mm: float = 12.0
    max_w: float = 0.0
    max_h: float = 0.0
    min_w: float = 0.0
    min_h: float = 0.0
    # Trục (repeat_around)
    teeth: Optional[int] = None
    pitch_mm: Optional[float] = None
    dia_mm: Optional[float] = None


@dataclass
class Product:
    """Từ Sản phẩm (§13). rong_tp/dai_tp = khổ thành phẩm."""
    rong_tp: float = 0.0
    dai_tp: float = 0.0
    bleed_mm: Optional[float] = None  # None ⇒ rule.bleed_default_mm
    so_trang: Optional[int] = None    # signature
    binding: Optional[str] = None     # saddle | perfect | sewn
    cover_separate: bool = False
    # Blank (nesting) — suy từ dieline
    blank_w: Optional[float] = None
    blank_h: Optional[float] = None
    # Caliper ruột (mm/tờ) — spine + creep; test-bench nhập, thật thì từ giấy/SP
    caliper_mm: Optional[float] = None


@dataclass
class RawSheet:
    """Tờ nguyên (§13)."""
    rong_ng: float = 0.0
    dai_ng: float = 0.0
    gsm: float = 0.0
    gia_kg: float = 0.0
    tho: str = "none"  # thớ giấy


@dataclass
class PrintSheet:
    """Khổ tờ in — engine tự xả từ tờ nguyên (spec §1.4: rule KHÔNG tự chọn khổ tờ in)."""
    rong: float
    dai: float
    kieu_cat: str          # vd "1x2" = xả tờ nguyên thành 1×2 tờ in
    per_nguyen: int = 1    # số tờ in / tờ nguyên


@dataclass
class Warning:
    code: str
    message: str
    severity: str = "warning"  # "error" chặn | "warning" cảnh báo


@dataclass
class ImpositionResult:
    """Hợp đồng output §6."""
    layout_mode: str
    kho_to_in: Optional[PrintSheet]
    don_vi_per_to_in: int            # con | tay | blank | tem / 1 tờ in
    to_in_per_nguyen: int
    tong_don_vi_per_nguyen: int
    so_kem: int
    hao_hinh_hoc_pct: float
    so_to_in: Optional[int] = None
    so_to_nguyen: Optional[int] = None
    so_tay: Optional[int] = None
    danh_sach_tay: Optional[list] = None
    spine_mm: Optional[float] = None
    creep_mm: Optional[float] = None
    warnings: list[Warning] = field(default_factory=list)

    @property
    def has_error(self) -> bool:
        return any(w.severity == "error" for w in self.warnings)


# --- §5.0 Lõi hình học chung ----------------------------------------------
def _fit_1d(usable: float, cell: float, gutter: float) -> int:
    """Số ô xếp theo 1 chiều = ⌊(usable+gutter)/(cell+gutter)⌋ (kẹp sàn 0)."""
    denom = cell + gutter
    if usable <= 0 or denom <= 0:
        return 0
    return max(0, int(floor((usable + gutter) / denom)))


def usable_area(sheet_w: float, sheet_h: float, gripper_mm: float,
                side_margin_mm: float, tail_colorbar_mm: float) -> tuple[float, float]:
    """(Wu, Lu): trừ lề hông 2 bên (rộng) + nhíp & thang màu đuôi (dài). §5.0."""
    Wu = sheet_w - 2 * side_margin_mm
    Lu = sheet_h - gripper_mm - tail_colorbar_mm
    return Wu, Lu


def fit_count(Wu: float, Lu: float, w: float, h: float, gutter: float,
              allow_rotate: bool) -> tuple[int, bool]:
    """max(n0, n90). Trả (count, rotated) — rotated=True nếu hướng xoay 90° thắng. §5.0."""
    n0 = _fit_1d(Wu, w, gutter) * _fit_1d(Lu, h, gutter)
    n90 = (_fit_1d(Wu, h, gutter) * _fit_1d(Lu, w, gutter)) if allow_rotate else 0
    if n90 > n0:
        return n90, True
    return n0, False


def waste_pct(count: int, dt_con: float, dt_to_in: float) -> float:
    """%hao hình học = 1 − (count×dt_con)/dt_tờ_in. §5.0."""
    if dt_to_in <= 0:
        return 0.0
    return 1.0 - (count * dt_con) / dt_to_in


def fits_machine(w: float, h: float, m: Machine) -> bool:
    """Tờ in (w×h) có nạp vừa máy không (thử cả 2 hướng nạp). max/min=0 ⇒ bỏ qua."""
    def _le(a: float, lim: float) -> bool:
        return lim <= 0 or a <= lim + 1e-9

    def _ge(a: float, lim: float) -> bool:
        return lim <= 0 or a >= lim - 1e-9

    orient_ok = (_le(w, m.max_w) and _le(h, m.max_h)) or (_le(h, m.max_w) and _le(w, m.max_h))
    min_ok = (_ge(w, m.min_w) and _ge(h, m.min_h)) or (_ge(h, m.min_w) and _ge(w, m.min_h))
    return orient_ok and min_ok


def _bleed(rule: RuleVersion, product: Product) -> float:
    return product.bleed_mm if product.bleed_mm is not None else rule.bleed_default_mm


# --- Xả giấy: tờ nguyên → các khổ tờ in ứng viên --------------------------
def derive_print_sheets(raw: RawSheet, machine: Machine, max_div: int = 8) -> list[PrintSheet]:
    """Liệt kê ứng viên khổ tờ in bằng cách xả tờ nguyên thành lưới nx×ny tờ bằng nhau,
    giữ những khổ nạp vừa máy. Engine chạy layout trên từng ứng viên rồi chọn tốt nhất.

    Spec §1.4/§6: rule KHÔNG chọn khổ tờ in — engine chọn dựa Máy in + Tờ nguyên."""
    out: list[PrintSheet] = []
    if raw.rong_ng <= 0 or raw.dai_ng <= 0:
        return out
    seen: set[tuple[int, int]] = set()
    for nx in range(1, max_div + 1):
        for ny in range(1, max_div + 1):
            pw = raw.rong_ng / nx
            ph = raw.dai_ng / ny
            key = (round(pw, 3), round(ph, 3))
            if key in seen:
                continue
            seen.add(key)
            if fits_machine(pw, ph, machine):
                out.append(PrintSheet(rong=pw, dai=ph, kieu_cat=f"{nx}x{ny}", per_nguyen=nx * ny))
    return out


# --- Layout per mode (chạy trên 1 khổ tờ in cho trước) --------------------
@dataclass
class _LayoutOut:
    don_vi: int
    hao_pct: float
    rotated: bool = False
    so_tay: Optional[int] = None
    danh_sach_tay: Optional[list] = None
    spine_mm: Optional[float] = None
    creep_mm: Optional[float] = None
    warnings: list[Warning] = field(default_factory=list)


def layout_step_repeat(psheet_w: float, psheet_h: float, rule: RuleVersion,
                       machine: Machine, product: Product) -> _LayoutOut:
    """§5.1 — xếp con giống hệt (name card, tờ rơi, poster, lịch tờ, tem rời)."""
    warns: list[Warning] = []
    bleed = _bleed(rule, product)
    cell_w = product.rong_tp + 2 * bleed
    cell_h = product.dai_tp + 2 * bleed
    Wu, Lu = usable_area(psheet_w, psheet_h, machine.gripper_mm,
                         rule.side_margin_mm, rule.tail_colorbar_mm)
    count, rotated = fit_count(Wu, Lu, cell_w, cell_h, rule.gutter_mm, rule.allow_rotate)
    if count <= 0:
        warns.append(Warning("E-FIT-0", "Con lớn hơn vùng in được — không xếp được con nào.", "error"))
    if (rule.grain_constraint != "none" and rule.warn_on_grain_violation and rotated):
        warns.append(Warning("W-GRAIN", "Hướng đặt (xoay 90°) có thể vi phạm ràng buộc thớ giấy.", "warning"))
    hao = waste_pct(count, cell_w * cell_h, psheet_w * psheet_h)
    return _LayoutOut(don_vi=count, hao_pct=hao, rotated=rotated, warnings=warns)


def layout_nesting(psheet_w: float, psheet_h: float, rule: RuleVersion,
                   machine: Machine, product: Product) -> _LayoutOut:
    """§5.3 — dàn khuôn bao bì (hộp giấy). blank từ dieline (Sản phẩm)."""
    warns: list[Warning] = []
    bw, bh = product.blank_w, product.blank_h
    if not bw or not bh or bw <= 0 or bh <= 0:
        warns.append(Warning("E-MODE-REQ", "Thiếu kích thước blank (dieline) cho kiểu dàn khuôn.", "error"))
        return _LayoutOut(don_vi=0, hao_pct=0.0, warnings=warns)
    Wu, Lu = usable_area(psheet_w, psheet_h, machine.gripper_mm,
                         rule.side_margin_mm, rule.tail_colorbar_mm)
    matrix = rule.matrix_allowance_mm
    # Nesting: floor(Wu/(blank+matrix)) — KHÔNG cộng matrix vào tử (khác step_repeat). 2 hướng.
    n0 = (_nest_1d(Wu, bw, matrix) * _nest_1d(Lu, bh, matrix))
    n90 = (_nest_1d(Wu, bh, matrix) * _nest_1d(Lu, bw, matrix)) if rule.allow_rotate else 0
    rotated = n90 > n0
    blanks = max(n0, n90)
    if rule.nest_method == "true_shape" and blanks > 0:
        # true_shape nest so le/xoay: tiết kiệm hơn grid ~ +8% (xấp xỉ; nest thật cần solver).
        blanks = int(blanks * 1.08)
    if blanks <= 0:
        warns.append(Warning("E-FIT-0", "Blank lớn hơn vùng in được — không xếp được blank nào.", "error"))
    hao = waste_pct(blanks, bw * bh, psheet_w * psheet_h)
    return _LayoutOut(don_vi=blanks, hao_pct=hao, rotated=rotated, warnings=warns)


def _nest_1d(usable: float, blank: float, matrix: float) -> int:
    denom = blank + matrix
    if usable <= 0 or denom <= 0:
        return 0
    return max(0, int(floor(usable / denom)))


def layout_repeat_around(rule: RuleVersion, machine: Machine, product: Product,
                         web_width_mm: float) -> _LayoutOut:
    """§5.4 — lặp theo trục (tem nhãn cuộn, flexo). Cần trục máy (teeth×pitch)."""
    warns: list[Warning] = []
    if not machine.teeth or not machine.pitch_mm:
        warns.append(Warning("E-MODE-REQ", "Thiếu thông số trục (số răng × bước răng) của máy in cuộn.", "error"))
        return _LayoutOut(don_vi=0, hao_pct=0.0, warnings=warns)
    if product.rong_tp <= 0 or product.dai_tp <= 0:
        warns.append(Warning("E-MODE-REQ", "Thiếu kích thước tem.", "error"))
        return _LayoutOut(don_vi=0, hao_pct=0.0, warnings=warns)
    bleed = _bleed(rule, product)
    tem_w = product.rong_tp + 2 * bleed
    tem_h = product.dai_tp + 2 * bleed
    repeat_length = machine.teeth * machine.pitch_mm
    around = _floor_gap(repeat_length, tem_h, rule.gap_around_mm)
    if rule.lanes is not None:
        lanes = rule.lanes
    else:
        lanes = _floor_gap(web_width_mm, tem_w, rule.gap_around_mm)
    per_vong = lanes * around
    if per_vong <= 0:
        warns.append(Warning("E-FIT-0", "Tem không vừa chu vi trục / khổ cuộn.", "error"))
    hao = waste_pct(per_vong, tem_w * tem_h, web_width_mm * repeat_length)
    return _LayoutOut(don_vi=per_vong, hao_pct=hao, warnings=warns)


def _floor_gap(span: float, size: float, gap: float) -> int:
    """⌊span/(size+gap)⌋ — dùng cho repeat_around (khoảng cách gap giữa tem)."""
    denom = size + gap
    if span <= 0 or denom <= 0:
        return 0
    return max(0, int(floor(span / denom)))


def layout_signature(psheet_w: float, psheet_h: float, rule: RuleVersion,
                     machine: Machine, product: Product, so_mau: int,
                     so_luong: int = 0) -> _LayoutOut:
    """§5.2 — bình tay sách (sách, catalogue, tạp chí). Trả don_vi = SỐ TAY."""
    warns: list[Warning] = []
    P = product.so_trang or 0
    if P <= 0:
        warns.append(Warning("E-MODE-REQ", "Thiếu số trang (P) cho kiểu bình tay sách.", "error"))
        return _LayoutOut(don_vi=0, hao_pct=0.0, warnings=warns)

    # [A] Chọn trang/tay (auto = tay lớn nhất mà nửa số trang xếp vừa 1 MẶT tờ in ≤ khổ máy)
    if rule.pages_per_sig is None:
        pps = _auto_pages_per_sig(psheet_w, psheet_h, rule, machine, product)
    else:
        pps = rule.pages_per_sig
    if pps <= 0:
        warns.append(Warning("E-FIT-0", "Không tay nào (kể cả F4) xếp vừa khổ tờ in.", "error"))
        return _LayoutOut(don_vi=0, hao_pct=0.0, warnings=warns)

    # [W-P4] P không bội 4 → chèn trang trắng cho đủ bội 4
    P_eff = P
    if P % 4 != 0:
        P_eff = ((P + 3) // 4) * 4
        warns.append(Warning("W-P4", f"P={P} không bội 4 — đã chèn {P_eff - P} trang trắng cho đủ {P_eff}.", "warning"))

    # [B] Số tay
    so_tay = ceil(P_eff / pps)

    # Guardrails trang (§10)
    binding = (product.binding or "").lower()
    if rule.min_pages is not None and P < rule.min_pages:
        warns.append(Warning("W-PAGES-MIN", f"P={P} thấp hơn ngưỡng đóng ({rule.min_pages}).", "warning"))
    if rule.max_pages is not None and P > rule.max_pages:
        warns.append(Warning("W-PAGES-MAX", f"P={P} vượt giới hạn ghim ({rule.max_pages}) — nên chuyển đóng keo.", "warning"))

    # [D] Creep (chỉ saddle/ghim): tay trong cùng lệch nhiều nhất ≈ caliper × (số_tay-1)
    creep = None
    if binding == "saddle" and product.caliper_mm:
        creep = round(product.caliper_mm * max(0, so_tay - 1), 3)

    # [G] Bìa + spine (nếu bìa in riêng)
    spine = None
    if product.caliper_mm:
        spine = round((P / 2.0) * product.caliper_mm, 3)
        if rule.min_spine_mm is not None and spine < rule.min_spine_mm:
            warns.append(Warning("W-SPINE", f"Gáy {spine}mm mỏng hơn ngưỡng đóng keo ({rule.min_spine_mm}mm).", "warning"))

    # %hao: dựa số trang thực xếp trên tờ in vs khổ tờ in (2 mặt) — xấp xỉ theo diện tích trang
    page_w = product.rong_tp + 2 * _bleed(rule, product)
    page_h = product.dai_tp + 2 * _bleed(rule, product)
    pages_per_side = pps // 2
    hao = waste_pct(pages_per_side, page_w * page_h, psheet_w * psheet_h)

    tay = [{"tay": k + 1, "pages_per_sig": pps} for k in range(so_tay)]
    return _LayoutOut(don_vi=so_tay, hao_pct=hao, so_tay=so_tay, danh_sach_tay=tay,
                      spine_mm=spine, creep_mm=creep, warnings=warns)


def _auto_pages_per_sig(psheet_w: float, psheet_h: float, rule: RuleVersion,
                        machine: Machine, product: Product) -> int:
    """auto = tay lớn nhất trong {32,16,8,4} mà (pps÷2) trang xếp vừa 1 MẶT tờ in."""
    page_w = product.rong_tp + 2 * _bleed(rule, product)
    page_h = product.dai_tp + 2 * _bleed(rule, product)
    Wu, Lu = usable_area(psheet_w, psheet_h, machine.gripper_mm,
                         rule.side_margin_mm, rule.tail_colorbar_mm)
    for pps in (32, 16, 8, 4):
        fit, _ = fit_count(Wu, Lu, page_w, page_h, rule.gutter_mm, rule.allow_rotate)
        if fit >= pps // 2:
            return pps
    return 0


# --- Số kẽm (§5.2 E / §7 ⑧) ------------------------------------------------
def compute_so_kem(layout_mode: str, so_mau_truoc: int, so_mau_sau: int,
                   sides: int, so_tay: Optional[int], work_style: str) -> int:
    """Số kẽm rule emit (TỔNG — thay cả biểu thức pricing).

    - signature: số_tay × số_màu × (sheetwise?2:1). work_turn dùng chung 1 bộ kẽm cả 2 mặt.
    - phẳng (step_repeat/nesting/repeat_around): 1 bộ kẽm mỗi mặt in → màu_trước + màu_sau.
    """
    if layout_mode == "signature" and so_tay:
        mau = max(int(so_mau_truoc or 0), int(so_mau_sau or 0))
        return so_tay * mau * (2 if work_style == "sheetwise" else 1)
    # Ấn phẩm phẳng: mỗi mặt 1 bộ kẽm = số màu mặt đó.
    front = int(so_mau_truoc or 0)
    back = int(so_mau_sau or 0) if sides >= 2 else 0
    return front + back


# --- Orchestrator §6 -------------------------------------------------------
def resolve(rule: RuleVersion, machine: Machine, product: Product, raw: RawSheet,
            so_luong: int = 0, so_mau_truoc: int = 4, so_mau_sau: int = 0,
            print_sheet: Optional[PrintSheet] = None) -> ImpositionResult:
    """Chạy engine đầy đủ: xả giấy → layout theo mode → số tờ/kẽm/hao. §6."""
    warns: list[Warning] = []
    sides = 2 if (so_mau_sau and so_mau_sau > 0) else 1

    # 1) Chọn khổ tờ in (nếu caller không truyền sẵn): xả tờ nguyên, chạy layout mỗi ứng viên, lấy max đơn vị/tờ nguyên.
    candidates = [print_sheet] if print_sheet is not None else derive_print_sheets(raw, machine)
    if not candidates:
        # Không xả được (thiếu tờ nguyên / không vừa máy) — thử dùng chính tờ nguyên làm tờ in.
        if raw.rong_ng > 0 and raw.dai_ng > 0:
            candidates = [PrintSheet(rong=raw.rong_ng, dai=raw.dai_ng, kieu_cat="1x1", per_nguyen=1)]
        else:
            warns.append(Warning("E-MODE-REQ", "Thiếu tờ nguyên/khổ tờ in để chạy bình bài.", "error"))
            return ImpositionResult(rule.layout_mode, None, 0, 0, 0, 0, 0.0, warnings=warns)

    best: Optional[tuple] = None  # (tong_per_nguyen, sheet, layout_out)
    for ps in candidates:
        lo = _run_layout(ps, rule, machine, product, so_mau_truoc, so_luong)
        tong = lo.don_vi * ps.per_nguyen
        cand = (tong, ps, lo)
        if best is None or tong > best[0]:
            best = cand
    tong, ps, lo = best  # type: ignore
    warns.extend(lo.warnings)

    # 2) Số tờ in / tờ nguyên
    so_to_in = None
    so_to_nguyen = None
    if so_luong > 0 and lo.don_vi > 0:
        if rule.layout_mode == "signature" and lo.so_tay:
            # tờ in = số_tay × Q (bù hao sản xuất TÁCH ở pricing_engine, không cộng ở đây)
            so_to_in = lo.so_tay * so_luong
        else:
            so_to_in = ceil(so_luong / lo.don_vi)
        so_to_nguyen = ceil(so_to_in / ps.per_nguyen) if ps.per_nguyen > 0 else so_to_in

    # 3) Số kẽm
    so_kem = compute_so_kem(rule.layout_mode, so_mau_truoc, so_mau_sau, sides,
                            lo.so_tay, rule.work_style)

    # 4) Gang gutter guard (§10 W-GANG-GUTTER)
    if rule.layout_mode == "step_repeat" and rule.allow_gang and rule.gutter_mm < rule.min_gutter_mm:
        warns.append(Warning("W-GANG-GUTTER",
                             f"Gutter {rule.gutter_mm}mm nhỏ hơn tối thiểu khi ghép bài ({rule.min_gutter_mm}mm).",
                             "warning"))

    return ImpositionResult(
        layout_mode=rule.layout_mode,
        kho_to_in=ps,
        don_vi_per_to_in=lo.don_vi,
        to_in_per_nguyen=ps.per_nguyen,
        tong_don_vi_per_nguyen=tong,
        so_kem=so_kem,
        hao_hinh_hoc_pct=round(lo.hao_pct, 4),
        so_to_in=so_to_in,
        so_to_nguyen=so_to_nguyen,
        so_tay=lo.so_tay,
        danh_sach_tay=lo.danh_sach_tay,
        spine_mm=lo.spine_mm,
        creep_mm=lo.creep_mm,
        warnings=warns,
    )


def _run_layout(ps: PrintSheet, rule: RuleVersion, machine: Machine, product: Product,
                so_mau: int, so_luong: int) -> _LayoutOut:
    mode = rule.layout_mode
    if mode == "step_repeat":
        return layout_step_repeat(ps.rong, ps.dai, rule, machine, product)
    if mode == "nesting":
        return layout_nesting(ps.rong, ps.dai, rule, machine, product)
    if mode == "signature":
        return layout_signature(ps.rong, ps.dai, rule, machine, product, so_mau, so_luong)
    if mode == "repeat_around":
        # Với tem cuộn, "tờ in" = khổ cuộn; web_width = chiều rộng cuộn (rong tờ in).
        return layout_repeat_around(rule, machine, product, ps.rong)
    return _LayoutOut(don_vi=0, hao_pct=0.0,
                      warnings=[Warning("E-MODE-REQ", f"layout_mode không hợp lệ: {mode}", "error")])
