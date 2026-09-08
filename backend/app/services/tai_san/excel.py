"""Xuất bảng khấu hao / phân bổ một THÁNG ra .xlsx.

Bố cục cố ý ĐƠN GIẢN, không bắt chước khuôn MISA như báo cáo công nợ: file này không dán vào bộ
hồ sơ nào cả, nó là bảng để kế toán đọc rồi tự gõ định khoản sang phần mềm kế toán. Cột cuối là
Còn lại — cột ghi chú hạch toán đã gỡ (mg 0278), định khoản ai cần nhớ thì ghi ở ô ghi chú của
chính tài sản.

    A1  BẢNG TRÍCH KHẤU HAO / PHÂN BỔ — tháng MM/YYYY
    A2  (trống)
    A3  tiêu đề cột (Mã · Tên · SL · Bộ phận · Nguyên giá · Trích tháng này · Lũy kế · Còn lại · Diễn giải)
    A4+ dữ liệu
    cuối: dòng TỔNG (chỉ cột tiền)
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

MEDIA_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DINH_DANG_TIEN = "#,##0"

TIEU_DE = [
    "Mã", "Tên tài sản", "SL", "Bộ phận", "Nguyên giá",
    "Trích tháng này", "Lũy kế", "Còn lại", "Diễn giải",
]
#: Khoá trong dict `bang_thang()` theo đúng thứ tự cột ở trên. "Diễn giải" = câu trước → sau
#: của tháng có chuyện (bớt cái, nâng cấp, ghi giảm) — kế toán đọc file cũng phải hiểu vì sao
#: nguyên giá tháng này khác tháng trước.
KHOA = ["ma", "ten", "so_luong", "bo_phan_ten", "nguyen_gia", "muc_trich", "luy_ke", "con_lai",
        "dien_giai"]
COT_TIEN = {5, 6, 7, 8}
RONG_COT = {"A": 12, "B": 34, "C": 6, "D": 18, "E": 16, "F": 15, "G": 16, "H": 16, "I": 60}


def xuat_bang_ky(rows: list[dict], *, nam: int, thang: int) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"Khau hao {thang:02d}-{nam}"

    ws.cell(row=1, column=1, value=f"BẢNG TRÍCH KHẤU HAO / PHÂN BỔ — tháng {thang:02d}/{nam}")
    ws.cell(row=1, column=1).font = Font(bold=True, size=13)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(TIEU_DE))
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center")

    for i, ten in enumerate(TIEU_DE, start=1):
        o = ws.cell(row=3, column=i, value=ten)
        o.font = Font(bold=True)
        o.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    dong = 4
    for r in rows:
        for i, khoa in enumerate(KHOA, start=1):
            gia_tri = r.get(khoa)
            o = ws.cell(row=dong, column=i, value=gia_tri)
            if i in COT_TIEN:
                o.number_format = DINH_DANG_TIEN
        dong += 1

    o = ws.cell(row=dong, column=1, value="TỔNG")
    o.font = Font(bold=True)
    for i in COT_TIEN:
        khoa = KHOA[i - 1]
        o = ws.cell(row=dong, column=i, value=sum(int(r.get(khoa) or 0) for r in rows))
        o.font = Font(bold=True)
        o.number_format = DINH_DANG_TIEN

    for chu, rong in RONG_COT.items():
        ws.column_dimensions[chu].width = rong
    ws.freeze_panes = "A4"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
