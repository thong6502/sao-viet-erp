"""Xuất BẢNG LƯƠNG THÁNG ra .xlsx theo khuôn kế toán công ty đang dùng (chủ chốt 09/09/2026).

Bản cũ (`_build_table_xlsx` trong router) có 28 cột do mình tự đặt, và kế toán **không dò được**:

1. **Không cộng ra Thực nhận.** Công thức máy là
   `net = gross − BHXH − đoàn phí − TNCN − khoản trừ danh mục − (tạm ứng + đợt 1 + nợ kỳ trước)`,
   mà file cũ chỉ có Tổng · BHXH · TNCN · Tạm ứng ⇒ thiếu **đoàn phí**, **khoản trừ danh mục**,
   **lương đợt 1**. Đoàn viên công đoàn thì cột không bao giờ khớp thực nhận.
2. **Gộp cột.** Bảng của họ tách BHXH 8% / BHYT 1,5% / BHTN 1%; tách thưởng thành tích · doanh số ·
   5S · trả đồng phục · điều chỉnh lương; tách phạt đi trễ · biên bản · ĐT vượt trội · đồng phục-5S;
   tách công thường / công lễ-CN / tổng công. File cũ gộp mỗi nhóm thành một cột.
3. **Thiếu cột thông tin**: chức vụ, ngày vào làm, lương vị trí, lương đóng BHXH, người phụ thuộc.
4. **Thiếu bảng phụ**: bảng ký nhận và bảng tạm ứng theo ngày chi.

File mới có 3 sheet: `Bảng lương` · `Ký nhận` · `Tạm ứng`.

⚠️ LUẬT SỐ HỌC CỦA SHEET 1 — có test khoá (`test_luong_excel.py`), đừng phá:

    Cộng thu − Phạt/trừ thực tế            = Tổng lương
    Tổng lương − BHXH − BHYT − BHTN − đoàn phí − TNCN − khoản trừ − tạm ứng trừ kỳ này = Thực nhận

Thêm khoản mới vào engine thì thêm cột Ở ĐÂY, nếu không hai vế lệch và test đỏ ngay.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

MEDIA_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

TIEN = "#,##0"
CONG = "0.##"

NEN_NHOM = {
    "tt": "FFEFF2F5",     # thông tin
    "cong": "FFEAF3EA",   # ngày công
    "thu": "FFFDF6E3",    # các khoản thu
    "phat": "FFFBEAEA",   # phạt
    "tru": "FFEDE7F6",    # các khoản trừ
    "cuoi": "FFE3F2FD",   # thực nhận
}
VIEN = Border(*(Side(style="thin", color="FFCED4DA"),) * 4)


def _f(v) -> float:
    return float(v or 0)


def _khoan_phat_sinh_thu(ln) -> float:
    """Khoản danh mục PHÁT SINH riêng kỳ này (nguồn `line`, loại thu) — nằm NGOÀI `allowance`."""
    return sum(_f(c.amount) for c in getattr(ln, "components", []) or []
               if getattr(c, "kind", "") != "tru" and getattr(c, "source", "") == "line")


def _khoan_tru(ln) -> float:
    """Khoản danh mục loại TRỪ (mọi nguồn) — engine trừ thẳng vào thực nhận."""
    return sum(_f(c.amount) for c in getattr(ln, "components", []) or []
               if getattr(c, "kind", "") == "tru")


#: (nhãn, nhóm, lấy số, định dạng). Giữ NGUYÊN thứ tự — đây là thứ tự bảng của kế toán.
COT = [
    ("STT", "tt", None, None),
    ("Mã NV", "tt", lambda ln, nv: getattr(ln, "employee_code", "") or "", None),
    ("Họ và tên", "tt", lambda ln, nv: getattr(ln, "employee_name", "") or "", None),
    ("Chức vụ", "tt", lambda ln, nv: nv.get("chuc_vu") or "", None),
    ("Bộ phận", "tt", lambda ln, nv: getattr(ln, "department_name", "") or "", None),
    ("Ngày vào làm", "tt", lambda ln, nv: nv.get("ngay_vao_lam"), "dd/mm/yyyy"),
    ("Loại", "tt", lambda ln, nv: "Thử việc" if getattr(ln, "is_probation", False) else "Chính thức", None),

    ("Công ngày thường", "cong", lambda ln, nv: round(
        max(0.0, _f(ln.actual_cong) - _f(getattr(ln, "special_cong", 0))
            - _f(getattr(ln, "paid_leave_cong", 0))), 2), CONG),
    ("Công lễ/CN", "cong", lambda ln, nv: round(_f(getattr(ln, "special_cong", 0)), 2), CONG),
    ("Công phép", "cong", lambda ln, nv: round(_f(getattr(ln, "paid_leave_cong", 0)), 2), CONG),
    ("Tổng công", "cong", lambda ln, nv: round(_f(ln.actual_cong), 2), CONG),
    ("Công chuẩn", "cong", lambda ln, nv: round(_f(ln.standard_cong), 2), CONG),
    ("Giờ tăng ca", "cong", lambda ln, nv: round(int(getattr(ln, "ot_minutes", 0) or 0) / 60, 2), CONG),
    ("Ngày ca đêm", "cong", lambda ln, nv: int(getattr(ln, "night_days", 0) or 0), CONG),

    # ⚠️ `monthly_salary` là MỨC NỀN = lương vị trí + lương trách nhiệm (xem docstring `_compute`),
    # KHÔNG phải riêng lương vị trí. Đặt nhãn "Lương vị trí" là nói sai một cột tiền — hai khoản
    # đó chỉ tách được ở hồ sơ lương, dòng lương chỉ chụp lại tổng.
    ("Mức lương tháng", "thu", lambda ln, nv: _f(ln.monthly_salary), TIEN),
    ("Lương đóng BHXH", "thu", lambda ln, nv: _f(getattr(ln, "insurance_base", 0)), TIEN),

    ("Lương công", "thu", lambda ln, nv: _f(ln.luong_cong), TIEN),
    ("Điều chỉnh lương", "thu", lambda ln, nv: _f(getattr(ln, "dieu_chinh_luong", 0)), TIEN),
    ("Chuyên cần", "thu", lambda ln, nv: _f(ln.chuyen_can), TIEN),
    ("Phụ cấp", "thu", lambda ln, nv: _f(ln.allowance), TIEN),
    ("Ngoài giờ/Tăng ca", "thu", lambda ln, nv: _f(ln.ot_pay), TIEN),
    ("Phụ cấp ca đêm", "thu", lambda ln, nv: _f(ln.night_pay), TIEN),
    ("Ca đêm (giờ × hệ số)", "thu", lambda ln, nv: _f(getattr(ln, "night_premium_pay", 0)), TIEN),
    ("Cơm ca", "thu", lambda ln, nv: _f(getattr(ln, "meal_allowance_pay", 0)), TIEN),
    ("Cơm tăng ca", "thu", lambda ln, nv: _f(getattr(ln, "com_tang_ca_pay", 0)), TIEN),
    ("Phụ cấp ca", "thu", lambda ln, nv: _f(getattr(ln, "shift_allowance_pay", 0)), TIEN),
    ("Lương khoán", "thu", lambda ln, nv: _f(getattr(ln, "khoan", 0)), TIEN),
    ("Khoán km", "thu", lambda ln, nv: _f(getattr(ln, "khoan_km", 0)), TIEN),
    ("Thưởng/phạt tổ trưởng", "thu", lambda ln, nv: _f(getattr(ln, "thuong_to_truong", 0)), TIEN),
    ("Hoa hồng", "thu", lambda ln, nv: _f(getattr(ln, "hoa_hong", 0)), TIEN),
    ("Thưởng thành tích", "thu", lambda ln, nv: _f(getattr(ln, "thuong_thanh_tich", 0)), TIEN),
    ("Thưởng doanh số", "thu", lambda ln, nv: _f(getattr(ln, "thuong_doanh_so", 0)), TIEN),
    # Chủ chốt 09/09/2026: BỎ ba cột "Thưởng 5S" · "Trả đồng phục" · "Phép năm", gộp hết vào
    # một cột "Thưởng" — bảng đã quá rộng mà ba khoản đó ít khi có số. Vẫn giữ riêng thưởng
    # thành tích và doanh số (hai khoản kế toán soi thường xuyên). Tổng KHÔNG đổi.
    ("Thưởng", "thu", lambda ln, nv: (_f(ln.other_bonus) + _f(getattr(ln, "thuong_5s", 0))
                                      + _f(getattr(ln, "tra_dong_phuc", 0))
                                      + _f(getattr(ln, "phep_nam", 0))), TIEN),
    ("Khoản phát sinh", "thu", lambda ln, nv: _khoan_phat_sinh_thu(ln), TIEN),
    ("CỘNG THU", "thu", None, TIEN),                       # tính ở dưới

    ("Vi phạm", "phat", lambda ln, nv: _f(ln.vi_pham), TIEN),
    ("Đi trễ/về sớm", "phat", lambda ln, nv: _f(getattr(ln, "di_tre", 0)), TIEN),
    ("Phạt biên bản", "phat", lambda ln, nv: _f(getattr(ln, "phat_bien_ban", 0)), TIEN),
    ("ĐT vượt trội", "phat", lambda ln, nv: _f(getattr(ln, "dt_vuot_troi", 0)), TIEN),
    ("Đồng phục/5S", "phat", lambda ln, nv: _f(getattr(ln, "phat_5s_dong_phuc", 0)), TIEN),
    ("Phạt/trừ thực tế", "phat", None, TIEN),              # = CỘNG THU − Tổng lương

    ("TỔNG LƯƠNG", "thu", lambda ln, nv: _f(ln.gross), TIEN),

    ("BHXH", "tru", None, TIEN),
    ("BHYT", "tru", None, TIEN),
    ("BHTN", "tru", None, TIEN),
    ("Đoàn phí công đoàn", "tru", lambda ln, nv: _f(getattr(ln, "cong_doan", 0)), TIEN),
    ("Thuế TNCN", "tru", lambda ln, nv: _f(ln.pit), TIEN),
    ("Khoản trừ danh mục", "tru", lambda ln, nv: _khoan_tru(ln), TIEN),
    ("Tạm ứng", "tru", lambda ln, nv: _f(ln.advance_total), TIEN),
    ("Lương đợt 1", "tru", lambda ln, nv: _f(getattr(ln, "luong_dot_1_total", 0)), TIEN),
    ("Nợ ứng kỳ trước", "tru", lambda ln, nv: _f(getattr(ln, "no_ung_ky_truoc", 0)), TIEN),
    ("Tạm ứng trừ kỳ này", "tru", None, TIEN),             # = 3 cột trên − nợ chuyển kỳ sau

    ("THỰC NHẬN", "cuoi", lambda ln, nv: _f(ln.net_pay), TIEN),
    ("Nợ ứng chuyển kỳ sau", "cuoi", lambda ln, nv: _f(getattr(ln, "no_ung_chuyen_ky_sau", 0)), TIEN),

    ("Người phụ thuộc", "tt", lambda ln, nv: int(nv.get("nguoi_phu_thuoc") or 0), CONG),
    ("Trong đó: lương ngày phép", "tt", lambda ln, nv: _f(getattr(ln, "luong_ngay_phep", 0)), TIEN),
    ("Trong đó: phụ cấp thâm niên", "tt", lambda ln, nv: _f(getattr(ln, "phu_cap_tham_nien", 0)), TIEN),
    ("Thu nhập chịu thuế", "tt", lambda ln, nv: _f(getattr(ln, "thu_nhap_chiu_thue", 0)), TIEN),
    ("Thu nhập tính thuế", "tt", lambda ln, nv: _f(getattr(ln, "pit_taxable", 0)), TIEN),
    ("Ghi chú", "tt", lambda ln, nv: getattr(ln, "note", None) or "", None),
]

I_CONG_THU = next(i for i, c in enumerate(COT) if c[0] == "CỘNG THU")
I_PHAT_TT = next(i for i, c in enumerate(COT) if c[0] == "Phạt/trừ thực tế")
I_TONG = next(i for i, c in enumerate(COT) if c[0] == "TỔNG LƯƠNG")
I_BHXH = next(i for i, c in enumerate(COT) if c[0] == "BHXH")
I_TU_TRU = next(i for i, c in enumerate(COT) if c[0] == "Tạm ứng trừ kỳ này")
I_THUC_NHAN = next(i for i, c in enumerate(COT) if c[0] == "THỰC NHẬN")
#: Cột tiền thuộc khối THU (dùng để cộng ra "CỘNG THU") — từ "Lương công" tới "Khoản phát sinh".
I_THU_DAU = next(i for i, c in enumerate(COT) if c[0] == "Lương công")


def dong_so(ln, nv: dict, bh3: tuple[float, float, float]) -> list:
    """Một dòng lương → list giá trị theo đúng `COT`. Tách ra để test đối chiếu số học."""
    gia_tri: list = [None] * len(COT)
    for i, (_ten, _nhom, lay, _fmt) in enumerate(COT):
        if lay is not None:
            gia_tri[i] = lay(ln, nv)
    cong_thu = sum(_f(gia_tri[i]) for i in range(I_THU_DAU, I_CONG_THU))
    gia_tri[I_CONG_THU] = cong_thu
    # Phạt THỰC TRỪ = phần engine đã cắt khỏi thu nhập (đã qua trần 30% Điều 102 và có thể gồm
    # trừ lỗi khoán). Lấy hiệu chứ không cộng 5 cột phạt: 5 cột đó là số GHI NHẬN, trần có thể
    # cắt bớt, và trừ lỗi khoán không có cột riêng trên dòng lương.
    gia_tri[I_PHAT_TT] = round(cong_thu - _f(gia_tri[I_TONG]))
    # BHYT/BHTN nằm NGAY SAU BHXH trong `COT` — đổi thứ tự ba cột đó thì sửa cả chỗ này.
    assert COT[I_BHXH + 1][0] == "BHYT" and COT[I_BHXH + 2][0] == "BHTN"
    gia_tri[I_BHXH], gia_tri[I_BHXH + 1], gia_tri[I_BHXH + 2] = (round(x) for x in bh3)
    # Tạm ứng TRỪ ĐƯỢC kỳ này = tổng phải trừ − phần chuyển sang kỳ sau (engine kẹp sàn 0).
    no_sau = _f(getattr(ln, "no_ung_chuyen_ky_sau", 0))
    phai_tru = (_f(ln.advance_total) + _f(getattr(ln, "luong_dot_1_total", 0))
                + _f(getattr(ln, "no_ung_ky_truoc", 0)))
    gia_tri[I_TU_TRU] = round(max(0.0, phai_tru - no_sau))
    return gia_tri


def _to_dam(ws, hang: int, cot: int, gia_tri, fmt: str | None, nen: str | None = None,
            dam: bool = False):
    o = ws.cell(row=hang, column=cot, value=gia_tri)
    if fmt:
        o.number_format = fmt
    if nen:
        o.fill = PatternFill("solid", fgColor=nen)
    if dam:
        o.font = Font(bold=True)
    o.border = VIEN
    return o


def _sheet_bang_luong(wb, lines, nam, thang, nhan_vien, bh_tach):
    ws = wb.active
    ws.title = f"Bang luong {thang:02d}-{nam}"
    so_cot = len(COT)

    o = ws.cell(row=1, column=1, value=f"BẢNG THANH TOÁN LƯƠNG THÁNG {thang:02d}/{nam}")
    o.font = Font(bold=True, size=14)
    o.alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=min(so_cot, 20))

    o = ws.cell(row=2, column=1, value=(
        "Cộng thu − Phạt/trừ thực tế = Tổng lương. "
        "Tổng lương − BHXH − BHYT − BHTN − đoàn phí − TNCN − khoản trừ danh mục "
        "− tạm ứng trừ kỳ này = Thực nhận."))
    o.font = Font(italic=True, size=9)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=min(so_cot, 20))

    for i, (ten, nhom, _lay, _fmt) in enumerate(COT, start=1):
        o = ws.cell(row=4, column=i, value=ten)
        o.font = Font(bold=True, size=10)
        o.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        o.fill = PatternFill("solid", fgColor=NEN_NHOM[nhom])
        o.border = VIEN
    ws.row_dimensions[4].height = 34

    hang = 5
    for stt, ln in enumerate(lines, start=1):
        nv = nhan_vien.get(getattr(ln, "employee_id", None), {}) or {}
        gia_tri = dong_so(ln, nv, bh_tach(ln))
        gia_tri[0] = stt
        for i, (ten, nhom, _lay, fmt) in enumerate(COT, start=1):
            _to_dam(ws, hang, i, gia_tri[i - 1], fmt,
                    nen=NEN_NHOM[nhom] if ten in ("CỘNG THU", "TỔNG LƯƠNG", "THỰC NHẬN") else None,
                    dam=ten in ("CỘNG THU", "TỔNG LƯƠNG", "THỰC NHẬN"))
        hang += 1

    if lines:
        _to_dam(ws, hang, 1, "TỔNG", None, dam=True)
        for i, (_ten, _nhom, _lay, fmt) in enumerate(COT, start=1):
            if fmt != TIEN:
                continue
            chu = get_column_letter(i)
            _to_dam(ws, hang, i, f"=SUM({chu}5:{chu}{hang - 1})", TIEN, dam=True)

    rong = {1: 5, 2: 10, 3: 22, 4: 14, 5: 16, 6: 12, 7: 10}
    for i in range(1, so_cot + 1):
        ws.column_dimensions[get_column_letter(i)].width = rong.get(i, 14)
    ws.freeze_panes = "D5"
    return ws


def _sheet_ky_nhan(wb, lines, nam, thang, nhan_vien):
    ws = wb.create_sheet("Ky nhan")
    o = ws.cell(row=1, column=1, value=f"BẢNG KÝ NHẬN LƯƠNG THÁNG {thang:02d}/{nam}")
    o.font = Font(bold=True, size=13)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    tieu_de = ["STT", "Mã NV", "Họ và tên", "Chức vụ", "Bộ phận", "Thực nhận", "Thu lại", "Thực chi", "Ký nhận"]
    for i, ten in enumerate(tieu_de, start=1):
        o = ws.cell(row=3, column=i, value=ten)
        o.font = Font(bold=True)
        o.alignment = Alignment(horizontal="center")
        o.fill = PatternFill("solid", fgColor=NEN_NHOM["tt"])
        o.border = VIEN
    hang = 4
    for stt, ln in enumerate(lines, start=1):
        nv = nhan_vien.get(getattr(ln, "employee_id", None), {}) or {}
        net = _f(ln.net_pay)
        # "Thu lại" để TRỐNG cho kế toán ghi tay (thu lại tiền đã ứng thừa ngoài hệ thống);
        # "Thực chi" là công thức để sửa ô Thu lại là số tự chạy.
        for i, v in enumerate([stt, getattr(ln, "employee_code", "") or "",
                               getattr(ln, "employee_name", "") or "", nv.get("chuc_vu") or "",
                               getattr(ln, "department_name", "") or "", net, None,
                               # `N()` biến ô Thu lại bỏ trống thành 0 ⇒ Thực chi tự chạy khi kế
                               # toán ghi tay số thu lại.
                               f"=F{hang}-N(G{hang})", None], start=1):
            _to_dam(ws, hang, i, v, TIEN if i in (6, 7, 8) else None)
        hang += 1
    for chu, w in {"A": 5, "B": 10, "C": 24, "D": 16, "E": 16, "F": 15, "G": 13, "H": 15, "I": 18}.items():
        ws.column_dimensions[chu].width = w
    ws.freeze_panes = "A4"
    return ws


def _sheet_tam_ung(wb, lines, nam, thang, nhan_vien, tam_ung):
    """Bảng tạm ứng xếp theo NGÀY CHI, đúng cách kế toán đang làm (mỗi ngày một cột)."""
    ws = wb.create_sheet("Tam ung")
    ngay = sorted({t["ngay"] for t in tam_ung if t.get("ngay")})
    o = ws.cell(row=1, column=1, value=f"BẢNG TẠM ỨNG LƯƠNG THÁNG {thang:02d}/{nam}")
    o.font = Font(bold=True, size=13)
    tieu_de = ["STT", "Mã NV", "Họ và tên", "Chức vụ"] + [d.strftime("%d/%m") for d in ngay] + \
        ["Tổng ứng", "Lương đợt 1", "Nợ ứng kỳ trước", "Đã trừ kỳ này", "Còn nợ kỳ sau"]
    for i, ten in enumerate(tieu_de, start=1):
        o = ws.cell(row=3, column=i, value=ten)
        o.font = Font(bold=True)
        o.alignment = Alignment(horizontal="center")
        o.fill = PatternFill("solid", fgColor=NEN_NHOM["tru"])
        o.border = VIEN
    theo_nv: dict[int, dict] = {}
    for t in tam_ung:
        theo_nv.setdefault(t["employee_id"], {}).setdefault(t.get("ngay"), 0.0)
        theo_nv[t["employee_id"]][t.get("ngay")] += _f(t.get("so_tien"))
    hang = 4
    for stt, ln in enumerate(lines, start=1):
        eid = getattr(ln, "employee_id", None)
        nv = nhan_vien.get(eid, {}) or {}
        cua_nv = theo_nv.get(eid, {})
        no_sau = _f(getattr(ln, "no_ung_chuyen_ky_sau", 0))
        phai_tru = (_f(ln.advance_total) + _f(getattr(ln, "luong_dot_1_total", 0))
                    + _f(getattr(ln, "no_ung_ky_truoc", 0)))
        cot = [stt, getattr(ln, "employee_code", "") or "", getattr(ln, "employee_name", "") or "",
               nv.get("chuc_vu") or ""]
        cot += [cua_nv.get(d) or None for d in ngay]
        cot += [_f(ln.advance_total), _f(getattr(ln, "luong_dot_1_total", 0)),
                _f(getattr(ln, "no_ung_ky_truoc", 0)), round(max(0.0, phai_tru - no_sau)), no_sau]
        for i, v in enumerate(cot, start=1):
            _to_dam(ws, hang, i, v, TIEN if i > 4 else None)
        hang += 1
    for i in range(1, len(tieu_de) + 1):
        ws.column_dimensions[get_column_letter(i)].width = {1: 5, 2: 10, 3: 24, 4: 16}.get(i, 14)
    ws.freeze_panes = "E4"
    return ws


def xuat_bang_luong(lines, *, nam: int, thang: int, nhan_vien: dict, bh_tach,
                    tam_ung: list[dict] | None = None) -> bytes:
    """Ba sheet: Bảng lương · Ký nhận · Tạm ứng.

    `nhan_vien` = {employee_id: {chuc_vu, ngay_vao_lam, nguoi_phu_thuoc}} — thứ bảng lương không
    giữ mà bảng của kế toán có. `bh_tach(line)` trả `(BHXH, BHYT, BHTN)` đã tách từ tổng đã đóng
    băng (dùng lại `_insurance_lines` của router, phần dư dồn vào BHTN nên luôn cộng đúng tổng).
    """
    wb = Workbook()
    lines = list(lines)
    _sheet_bang_luong(wb, lines, nam, thang, nhan_vien, bh_tach)
    _sheet_ky_nhan(wb, lines, nam, thang, nhan_vien)
    _sheet_tam_ung(wb, lines, nam, thang, nhan_vien, tam_ung or [])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
