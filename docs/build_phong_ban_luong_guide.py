from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


OUT_PATH = Path("docs/Huong_dan_su_dung_Phong_ban_va_Luong.docx")


TITLE = "HƯỚNG DẪN SỬ DỤNG PHÂN HỆ PHÒNG BAN VÀ LƯƠNG"
SUBTITLE = (
    "Tài liệu này mô tả chức năng, công dụng, trạng thái, vai trò và cách vận hành "
    "của 2 phân hệ Phòng ban và Lương theo hệ thống hiện tại."
)


PAYROLL_PERIOD_STATUS = [
    ("Nháp", "draft", "Kỳ lương đang soạn, còn được tính lại và sửa số."),
    ("Đã chốt", "locked", "Đã khóa số liệu, không cho sửa trực tiếp nữa."),
    ("Đã chi", "paid", "Đã xác nhận chi trả, khóa cứng hơn kỳ đã chốt."),
]

ADVANCE_STATUS = [
    ("Chờ duyệt", "pending", "Phiếu mới tạo, đang chờ người có quyền duyệt."),
    ("Đã duyệt", "approved", "Phiếu hợp lệ, số tiền sẽ được tính để trừ vào lương."),
    ("Từ chối", "rejected", "Phiếu không được duyệt, không đi vào bảng lương."),
    ("Đã hủy", "cancelled", "Phiếu bị hủy, ngừng hiệu lực."),
]

SCOPE_ROWS = [
    ("Của tôi", "Chỉ đụng tới dữ liệu của chính người dùng."),
    ("Cả phòng", "Đụng tới dữ liệu thuộc phòng hoặc tổ của mình và các tổ con."),
    ("Tất cả", "Đụng tới dữ liệu toàn công ty."),
]

ROLE_ROWS = [
    ("Admin", "Xem và thao tác toàn bộ, gồm cơ cấu, quyền, lương, tạm ứng, chốt kỳ, xuất file."),
    ("HCNS / C&B", "Quản lý hồ sơ, khai lương, tính lương, soát bảng lương, cấu hình lương."),
    ("Kế toán lương", "Duyệt tạm ứng, theo dõi chi trả, xác nhận đã chi, xuất dữ liệu chuyển khoản."),
    ("Trưởng phòng / trưởng bộ phận", "Quản lý nhân sự trong phạm vi được cấp, có thể được giao thêm quyền vận hành hoặc duyệt."),
    ("Nhân viên", "Xem phiếu lương của mình, theo dõi và tạo đề nghị tạm ứng của mình."),
]

ROOM_SUMMARY_ROWS = [
    ("Tổng quan", "Nhìn nhanh toàn bộ cơ cấu, số lượng phòng, nhân sự, tình trạng trưởng phòng."),
    ("Nhân sự", "Xem người trong phòng, thêm nhân viên, gán vai trò hàng loạt, điều chuyển phòng."),
    ("Vai trò & Quyền", "Tạo vai trò của từng phòng và gán ma trận phân quyền chi tiết."),
]

PAYROLL_TABS = [
    ("Bảng lương tháng", "Tạo bảng lương, soát số, chốt kỳ, xuất file, in phiếu."),
    ("Lương nhân viên", "Khai mức lương và các khoản cố định của từng nhân viên."),
    ("Lương khoán", "Khu vực dành cho luồng lương khoán khi doanh nghiệp áp dụng."),
    ("Tạm ứng", "Quản lý phiếu tạm ứng và phiếu lương đợt 1."),
    ("Cấu hình lương", "Quản lý tham số chung, cấu hình theo bộ phận, bảo hiểm, thuế, phụ cấp."),
    ("Phiếu lương của tôi", "Nhân viên tự xem phiếu lương cá nhân."),
    ("Tạm ứng của tôi", "Nhân viên tự tạo và theo dõi đề nghị tạm ứng của chính mình."),
]


def set_cell_text(cell, text: str, *, bold: bool = False, center: bool = False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(text)
    run.bold = bold
    set_run_font(run, size=Pt(10.5), color="222222")
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_run_font(run, *, size: Pt | None = None, color: str | None = None, bold: bool | None = None) -> None:
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    if size is not None:
        run.font.size = size
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def add_table(doc: Document, headers: list[str], rows: list[tuple[str, ...]], widths_cm: list[float]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    hdr = table.rows[0].cells
    for idx, text in enumerate(headers):
        hdr[idx].width = Cm(widths_cm[idx])
        set_cell_text(hdr[idx], text, bold=True)
        set_cell_shading(hdr[idx], "E8EEF5")

    for row in rows:
        cells = table.add_row().cells
        for idx, text in enumerate(row):
            cells[idx].width = Cm(widths_cm[idx])
            set_cell_text(cells[idx], text)

    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(2)


def add_bullet(doc: Document, text: str, level: int = 0) -> None:
    p = doc.add_paragraph(style="List Bullet")
    if level:
        p.paragraph_format.left_indent = Cm(0.6 * level)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    set_run_font(run, size=Pt(11), color="222222")


def add_number(doc: Document, text: str) -> None:
    p = doc.add_paragraph(style="List Number")
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    set_run_font(run, size=Pt(11), color="222222")


def add_para(doc: Document, text: str, *, italic: bool = False) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    set_run_font(run, size=Pt(11), color="222222")
    run.italic = italic


def add_heading(doc: Document, text: str, level: int) -> None:
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.space_before = Pt(16 if level == 1 else 10)
    p.paragraph_format.space_after = Pt(6 if level == 1 else 4)
    run = p.add_run(text)
    if level == 1:
        set_run_font(run, size=Pt(16), color="2E74B5", bold=True)
    elif level == 2:
        set_run_font(run, size=Pt(13), color="2E74B5", bold=True)
    else:
        set_run_font(run, size=Pt(12), color="1F4D78", bold=True)


def add_footer_with_page_number(section) -> None:
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.text = ""
    label = p.add_run("Trang ")
    set_run_font(label, size=Pt(9), color="666666")

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run = p.add_run()
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    txt = OxmlElement("w:t")
    txt.text = "1"
    run._r.append(txt)
    run._r.append(fld_end)


def configure_styles(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54)
    section.right_margin = Cm(2.54)
    section.header_distance = Cm(1.25)
    section.footer_distance = Cm(1.25)
    add_footer_with_page_number(section)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11)


def add_title_block(doc: Document) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(TITLE)
    set_run_font(run, size=Pt(20), color="1F3A5F", bold=True)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(12)
    r2 = p2.add_run(SUBTITLE)
    set_run_font(r2, size=Pt(11), color="4A5568")

    info = doc.add_table(rows=2, cols=2)
    info.style = "Table Grid"
    info.alignment = WD_TABLE_ALIGNMENT.CENTER
    info.autofit = False
    widths = [3.4, 12.0]
    rows = [
        ("Phạm vi", "Phân hệ Phòng ban và phân hệ Lương"),
        ("Mục tiêu", "Giúp quản trị, HCNS, kế toán và nhân viên hiểu đúng cách dùng hệ thống hiện tại"),
    ]
    for ridx, row in enumerate(rows):
        for cidx, val in enumerate(row):
            info.rows[ridx].cells[cidx].width = Cm(widths[cidx])
            set_cell_text(info.rows[ridx].cells[cidx], val, bold=(cidx == 0))
            if cidx == 0:
                set_cell_shading(info.rows[ridx].cells[cidx], "F2F4F7")


def build_doc() -> Path:
    doc = Document()
    configure_styles(doc)
    add_title_block(doc)

    add_heading(doc, "1. Mục đích tài liệu", 1)
    add_para(
        doc,
        "Tài liệu này giải thích rõ chức năng, công dụng, trạng thái, vai trò và cách vận hành của "
        "hai phân hệ Phòng ban và Lương theo đúng luồng hiện có trong hệ thống."
    )
    add_para(
        doc,
        "Nội dung ưu tiên cách dùng thực tế cho quản trị hệ thống, HCNS, kế toán, trưởng bộ phận và nhân viên."
    )

    add_heading(doc, "2. Phân hệ Phòng ban", 1)
    add_heading(doc, "2.1. Mục đích", 2)
    add_para(
        doc,
        "Phân hệ Phòng ban dùng để quản lý cơ cấu tổ chức của công ty. Đây là nơi giữ bộ khung tổ chức, "
        "đầu mối quản lý nhân sự theo phòng, vai trò và quyền hạn của từng nhóm người dùng."
    )
    add_bullet(doc, "Tạo phòng ban gốc và phòng ban con.")
    add_bullet(doc, "Quản lý cây tổ chức của công ty.")
    add_bullet(doc, "Gán trưởng phòng hoặc người đứng đầu đơn vị.")
    add_bullet(doc, "Theo dõi nhân sự trong từng phòng.")
    add_bullet(doc, "Tạo vai trò và gán phân quyền theo từng phòng.")
    add_bullet(doc, "Điều chuyển nhân sự giữa các phòng ban.")

    add_heading(doc, "2.2. Các khu vực chính trên màn hình", 2)
    add_para(doc, "Màn hình Phòng ban hiện được tổ chức thành các khu vực chính sau:")
    add_table(
        doc,
        ["Khu vực", "Công dụng"],
        ROOM_SUMMARY_ROWS,
        [4.2, 12.3],
    )

    add_heading(doc, "2.3. Chức năng Tổng quan", 2)
    add_para(
        doc,
        "Khu vực Tổng quan giúp người dùng nắm nhanh bức tranh tổ chức toàn công ty mà không cần mở từng phòng."
    )
    add_bullet(doc, "Hiển thị tổng số phòng ban.")
    add_bullet(doc, "Hiển thị tổng số nhân sự toàn công ty.")
    add_bullet(doc, "Hiển thị số phòng đã có trưởng phòng và số phòng còn thiếu trưởng phòng.")
    add_bullet(doc, "Hiển thị phân bố giữa khối sản xuất và khối văn phòng.")
    add_bullet(doc, "Cho phép tìm theo tên hoặc mã phòng ban.")
    add_bullet(doc, "Có thể lọc nhanh các phòng thiếu trưởng phòng hoặc chưa có nhân sự.")
    add_bullet(doc, "Có thể đổi giữa chế độ danh sách và sơ đồ cây.")

    add_heading(doc, "2.4. Quản lý phòng ban", 2)
    add_para(doc, "Người có quyền phù hợp có thể thực hiện các nghiệp vụ chính sau:")
    add_number(doc, "Tạo mới phòng ban gốc hoặc phòng ban con.")
    add_number(doc, "Sửa thông tin phòng ban.")
    add_number(doc, "Xóa phòng ban khi không còn phù hợp.")
    add_number(doc, "Đổi cấp trên trong cây tổ chức.")
    add_number(doc, "Chỉ định trưởng phòng.")
    add_para(
        doc,
        "Nếu một phòng đã có người nhưng chưa có trưởng phòng, hệ thống hiển thị cảnh báo riêng để dễ xử lý. "
        "Phòng chưa có nhân sự được đánh dấu riêng, không bị coi là lỗi dữ liệu."
    )

    add_heading(doc, "2.5. Quản lý nhân sự trong phòng", 2)
    add_para(
        doc,
        "Tab Nhân sự trong Phòng ban là nơi xử lý nhân sự theo góc nhìn tổ chức, không phải góc nhìn lương."
    )
    add_bullet(doc, "Xem danh sách người thuộc phòng.")
    add_bullet(doc, "Lọc theo trạng thái nhân sự.")
    add_bullet(doc, "Chọn nhiều người để gán vai trò hàng loạt.")
    add_bullet(doc, "Chuyển nhiều người sang phòng khác.")
    add_bullet(doc, "Thêm nhân viên mới ngay trong màn hình Phòng ban.")
    add_para(
        doc,
        "Khi chuyển phòng, vai trò cũ có thể bị gỡ vì vai trò luôn thuộc về đúng phòng ban. "
        "Nếu người được chuyển đang là trưởng phòng cũ thì hệ thống cũng bỏ gán trưởng phòng ở đơn vị cũ."
    )

    add_heading(doc, "2.6. Tab Vai trò & Quyền", 2)
    add_para(
        doc,
        "Vai trò trong hệ thống là bó quyền gắn với từng phòng ban cụ thể. Một vai trò không dùng chung cho toàn công ty."
    )
    add_bullet(doc, "Tạo vai trò mới trong phòng.")
    add_bullet(doc, "Đổi tên vai trò.")
    add_bullet(doc, "Xóa vai trò.")
    add_bullet(doc, "Gán ma trận phân quyền cho vai trò.")
    add_para(
        doc,
        "Mỗi tài khoản chỉ giữ một vai trò tại một thời điểm, và vai trò đó phải thuộc đúng phòng của người dùng."
    )

    add_heading(doc, "2.7. Logic phân quyền", 2)
    add_para(doc, "Ma trận phân quyền hiện vận hành theo 3 lớp chính:")
    add_bullet(doc, "Xem: được vào module và đọc dữ liệu.")
    add_bullet(doc, "Thao tác: được thêm, sửa, xóa.")
    add_bullet(doc, "Phạm vi: quy định được đụng tới dữ liệu của ai.")
    add_para(doc, "Các mức phạm vi hiện có như sau:")
    add_table(doc, ["Phạm vi", "Ý nghĩa"], SCOPE_ROWS, [4.2, 12.3])
    add_para(
        doc,
        "Nguyên tắc đang áp dụng là: nếu đã có quyền thao tác thì hệ thống tự hiểu phải có quyền xem; "
        "nếu tắt quyền xem thì các quyền thao tác liên quan cũng bị tắt theo. Mục đích là tránh cấp quyền nửa chừng."
    )

    add_heading(doc, "2.8. Các quyền chi tiết quan trọng", 2)
    add_para(
        doc,
        "Ngoài CRUD cơ bản, phân hệ hiện dùng nhiều quyền chi tiết để kiểm soát các thao tác nhạy cảm."
    )
    add_bullet(doc, "Đặt trưởng phòng.")
    add_bullet(doc, "Đổi cấp trên trong cây tổ chức.")
    add_bullet(doc, "Gán vai trò.")
    add_bullet(doc, "Chuyển phòng ban.")
    add_bullet(doc, "Sửa ma trận phân quyền.")
    add_bullet(doc, "Khóa hoặc mở khóa tài khoản.")
    add_bullet(doc, "Đặt lại mật khẩu và thu hồi phiên đăng nhập.")
    add_bullet(doc, "Xem lương & BHXH khi được cấp quyền nhạy cảm.")

    add_heading(doc, "2.9. Những điều cần nhớ ở phân hệ Phòng ban", 2)
    add_bullet(doc, "Một tài khoản chỉ thuộc một phòng ban tại một thời điểm.")
    add_bullet(doc, "Một tài khoản chỉ giữ một vai trò tại một thời điểm.")
    add_bullet(doc, "Vai trò phải thuộc đúng phòng của người đó.")
    add_bullet(doc, "Chuyển phòng xong nên kiểm tra lại vai trò.")
    add_bullet(doc, "Phòng ban là nơi quản lý cơ cấu, không phải nơi khai chính sách lương.")

    add_heading(doc, "3. Phân hệ Lương", 1)
    add_heading(doc, "3.1. Mục đích", 2)
    add_para(
        doc,
        "Phân hệ Lương là trung tâm xử lý lương thời gian của hệ thống. Phân hệ này quản lý dữ liệu lương, "
        "cấu hình tính lương, bảng lương tháng, tạm ứng và phiếu lương cá nhân."
    )

    add_heading(doc, "3.2. Các tab chính", 2)
    add_table(doc, ["Tab", "Công dụng"], PAYROLL_TABS, [4.2, 12.3])

    add_heading(doc, "3.3. Tab Bảng lương tháng", 2)
    add_para(
        doc,
        "Đây là nơi người có quyền quản lý lương vận hành kỳ lương theo từng tháng."
    )
    add_number(doc, "Chọn tháng cần xử lý.")
    add_number(doc, "Sinh bảng lương từ dữ liệu chấm công, hồ sơ lương và cấu hình lương.")
    add_number(doc, "Soát từng dòng lương theo nhân viên.")
    add_number(doc, "Sửa các ô tay khi kỳ còn ở trạng thái nháp.")
    add_number(doc, "Chốt kỳ lương.")
    add_number(doc, "Đánh dấu đã chi trả.")
    add_number(doc, "Xuất bảng lương Excel hoặc file chuyển khoản ngân hàng.")
    add_number(doc, "In phiếu lương từng người.")

    add_heading(doc, "3.4. Trạng thái kỳ lương", 2)
    add_table(doc, ["Tên hiển thị", "Mã trạng thái", "Ý nghĩa"], PAYROLL_PERIOD_STATUS, [3.5, 3.2, 9.8])
    add_para(
        doc,
        "Chỉ kỳ lương ở trạng thái nháp mới được tính lại và sửa trực tiếp. "
        "Kỳ đã chốt hoặc đã chi được giữ lại để bảo toàn lịch sử."
    )

    add_heading(doc, "3.5. Tab Lương nhân viên", 2)
    add_para(
        doc,
        "Tab này giữ dữ liệu gốc của từng nhân viên để phục vụ tính lương. Đây là nơi khai mức lương và "
        "các khoản cố định theo từng người, không dùng kiểu cả tổ một mức tiền."
    )
    add_bullet(doc, "Lương cơ bản dùng làm mức đóng bảo hiểm.")
    add_bullet(doc, "Lương trách nhiệm.")
    add_bullet(doc, "Thưởng chuyên cần.")
    add_bullet(doc, "Phụ cấp thâm niên.")
    add_bullet(doc, "Phụ cấp khác.")
    add_bullet(doc, "Lương trả 1 lần (đợt 1).")
    add_bullet(doc, "Các khoản cộng hoặc trừ riêng theo từng người.")
    add_bullet(doc, "Cách tính thuế TNCN khi hồ sơ yêu cầu.")
    add_para(
        doc,
        "Các thay đổi tại đây sẽ ảnh hưởng tới những kỳ lương còn nháp. Những kỳ đã chốt hoặc đã chi sẽ không tự thay đổi ngược."
    )

    add_heading(doc, "3.6. Tab Cấu hình lương", 2)
    add_para(
        doc,
        "Đây là khu vực dữ liệu nhạy cảm, không phải ai vào module Lương cũng được xem hoặc sửa."
    )
    add_bullet(doc, "Quản lý tham số chung như giờ chuẩn, tỷ lệ thử việc, tăng ca.")
    add_bullet(doc, "Quản lý cấu hình theo bộ phận.")
    add_bullet(doc, "Quản lý tỷ lệ bảo hiểm người lao động và doanh nghiệp.")
    add_bullet(doc, "Quản lý giảm trừ gia cảnh, thuế và các ngưỡng liên quan.")
    add_para(
        doc,
        "Người có quyền xem cấu hình lương được đọc dữ liệu nhạy cảm; người có quyền cập nhật mới được lưu thay đổi."
    )

    add_heading(doc, "3.7. Tab Tạm ứng", 2)
    add_para(
        doc,
        "Tab Tạm ứng quản lý cả phiếu tạm ứng thông thường và phiếu lương đợt 1."
    )
    add_bullet(doc, "Tạm ứng: khoản ứng trước ngoài lương chính.")
    add_bullet(doc, "Lương đợt 1: khoản trả trước một phần lương tháng.")
    add_para(doc, "Các trạng thái của phiếu tạm ứng hiện có như sau:")
    add_table(doc, ["Tên hiển thị", "Mã trạng thái", "Ý nghĩa"], ADVANCE_STATUS, [3.5, 3.2, 9.8])
    add_para(
        doc,
        "Khi phiếu đã duyệt, hệ thống dùng số đó để trừ vào bảng lương. "
        "Lương đợt 1 không phải khoản thu nhập cộng thêm, mà là khoản trả trước sẽ khấu trừ lại."
    )

    add_heading(doc, "3.8. Phiếu lương của tôi", 2)
    add_para(
        doc,
        "Đây là khu vực self-service cho nhân viên, dùng để xem phiếu lương cá nhân mà không cần quyền quản trị."
    )
    add_bullet(doc, "Xem lương theo công.")
    add_bullet(doc, "Xem các khoản cộng.")
    add_bullet(doc, "Xem các khoản khấu trừ.")
    add_bullet(doc, "Xem số tạm ứng đã nhận.")
    add_bullet(doc, "Xem số thực lĩnh.")

    add_heading(doc, "3.9. Tạm ứng của tôi", 2)
    add_para(
        doc,
        "Khu vực này cho phép nhân viên tự tạo và theo dõi đề nghị tạm ứng của chính mình."
    )
    add_bullet(doc, "Tạo đề nghị tạm ứng.")
    add_bullet(doc, "Tạo đề nghị lương đợt 1 nếu doanh nghiệp áp dụng.")
    add_bullet(doc, "Theo dõi phiếu đang chờ duyệt, đã duyệt, bị từ chối hoặc đã hủy.")

    add_heading(doc, "3.10. Logic dữ liệu người dùng cần hiểu", 2)
    add_number(doc, "Bảng lương tháng lấy dữ liệu từ hồ sơ lương, chấm công và cấu hình lương.")
    add_number(doc, "Tạm ứng đã duyệt sẽ tự đi vào phần khấu trừ.")
    add_number(doc, "Kỳ nháp có thể tính lại và sửa tay.")
    add_number(doc, "Kỳ đã chốt hoặc đã chi phải giữ nguyên để bảo toàn lịch sử.")
    add_number(doc, "Phân hệ có cả số liệu tự tính và số liệu sửa tay, nên phải xem đúng trạng thái trước khi thao tác.")

    add_heading(doc, "4. Vai trò thường gặp", 1)
    add_para(
        doc,
        "Dưới đây là cách hiểu ngắn gọn theo nhóm người dùng phổ biến trong doanh nghiệp."
    )
    add_table(doc, ["Vai trò", "Mô tả thực tế"], ROLE_ROWS, [4.2, 12.3])

    add_heading(doc, "5. Các lưu ý vận hành quan trọng", 1)
    add_bullet(doc, "Không sửa dữ liệu lương nếu chưa xác định kỳ đó đang là nháp, đã chốt hay đã chi.")
    add_bullet(doc, "Không xem Phòng ban là nơi khai chính sách tiền lương; đó là việc của phân hệ Lương.")
    add_bullet(doc, "Sau khi chuyển phòng phải kiểm tra lại vai trò, vì vai trò cũ có thể không còn hợp lệ.")
    add_bullet(doc, "Dữ liệu cấu hình lương là dữ liệu nhạy cảm, không nên cấp tràn lan.")
    add_bullet(doc, "Phiếu lương đợt 1 và tạm ứng đều là khoản sẽ được trừ lại khi tính lương tháng.")

    add_heading(doc, "6. Kết luận", 1)
    add_para(
        doc,
        "Phân hệ Phòng ban giúp doanh nghiệp quản lý cơ cấu, đầu mối chịu trách nhiệm, vai trò và phạm vi quyền hạn. "
        "Phân hệ Lương giúp doanh nghiệp quản lý tiền lương, tham số tính lương, bảng lương tháng và phiếu lương cá nhân."
    )
    add_para(
        doc,
        "Khi người dùng hiểu rõ ai thuộc phòng nào, ai giữ vai trò gì và ai được phép thao tác đến đâu, "
        "việc vận hành nhân sự và lương sẽ rõ ràng, dễ truy vết và ít sai sót hơn."
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_PATH)
    return OUT_PATH


if __name__ == "__main__":
    path = build_doc()
    print(path)
