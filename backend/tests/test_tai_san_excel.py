"""Bảng khấu hao xuất Excel — cột cuối phải là Ghi chú hạch toán.

Cột đó là lý do cả module không có ô tài khoản kế toán: kế toán đọc bảng này rồi gõ định khoản
sang phần mềm kế toán bên ngoài, nên nội dung họ tự ghi phải đi kèm ra file.
"""
from io import BytesIO

from openpyxl import load_workbook

from app.services.tai_san.excel import xuat_bang_ky


def _rows():
    return [{
        "ma": "TS-0001", "ten": "May in Komori 4 mau", "loai": "tscd", "bo_phan_ten": "To In",
        "nguyen_gia": 3_300_000_000, "muc_trich": 27_500_000,
        "luy_ke": 157_016_129, "con_lai": 3_142_983_871,
        "ghi_chu_hach_toan": "211 / 6274 - to In",
    }]


def test_file_excel_co_dung_cot_va_dong_tong():
    wb = load_workbook(BytesIO(xuat_bang_ky(_rows(), nam=2026, thang=8)))
    ws = wb.active
    tieu_de = [c.value for c in ws[3]]
    assert tieu_de[0] == "Mã"
    assert tieu_de[-1] == "Ghi chú hạch toán"
    assert ws.cell(row=4, column=1).value == "TS-0001"
    assert ws.cell(row=4, column=len(tieu_de)).value == "211 / 6274 - to In"
    # dòng cuối là TỔNG mức trích (cột 5 = "Trích kỳ này")
    assert ws.cell(row=5, column=1).value == "TỔNG"
    assert ws.cell(row=5, column=5).value == 27_500_000


def test_bang_rong_van_xuat_duoc():
    wb = load_workbook(BytesIO(xuat_bang_ky([], nam=2026, thang=8)))
    ws = wb.active
    assert ws.cell(row=4, column=1).value == "TỔNG"
    assert ws.cell(row=4, column=5).value == 0
