"""Xuất / Nhập Excel cho màn Hồ sơ nhân sự.

Việc này sinh ra để NẠP DỮ LIỆU BAN ĐẦU: khai một lượt vài trăm hồ sơ trên Excel rồi đổ vào, và
sửa hàng loạt trong lúc còn đang dọn dữ liệu. Nên file xuất ra phải là file nạp ngược lại được —
đủ mọi ô của hồ sơ, không phải 8 cột danh sách như bản trước 10/09/2026.

LUẬT DỮ LIỆU (cùng khuôn với Excel danh mục, `services/catalog_excel.py`):

1. Upsert theo cột **Mã**. Mã ĐÃ CÓ ⇒ sửa đúng người đó. Mã CHƯA CÓ ⇒ tạo mới và GIỮ NGUYÊN
   mã đó (nhờ vậy file xuất từ máy này nạp thẳng sang máy khác mà mã NV không lệch — mã nằm
   trên hợp đồng / thẻ / bảng lương). Bỏ trống mã ⇒ tạo mới, máy tự cấp mã (NV001, NV002…)
   y như bấm "Thêm nhân viên" trên màn.
2. Cột CÓ trong tiêu đề nhưng ô trống ⇒ xoá giá trị. Cột VẮNG khỏi tiêu đề ⇒ giữ nguyên.
   Ba cột mà cột DB là NOT NULL (Thâm niên trước · Số người phụ thuộc · Cách tính thuế TNCN)
   thì "xoá" nghĩa là VỀ MẶC ĐỊNH (`Cot.mac_dinh`) — xem sheet 'Huong dan'.
3. Người không có mặt trong file thì KHÔNG bị đụng tới (không xoá ai bao giờ).
4. Cả file là MỘT giao dịch: còn một dòng sai thì không ghi gì cả. `ghi=False` chạy y hệt rồi
   rollback, nên con số xem trước là con số THẬT.
5. Dòng không đổi một ô nào thì KHÔNG gọi service ⇒ không đẻ dòng nhật ký / mốc công tác ma.

BA THỨ EXCEL KHÔNG LÀM THAY ĐƯỢC — cố ý, đừng "mở cho tiện":

* **Trạng thái của người ĐÃ CÓ.** Nghỉ việc / đình chỉ còn khoá tài khoản và cắt phiên đăng nhập
  đang sống (`_apply_status`); tuyển lại thì mở khoá. Một ô Excel không mang nổi ngần ấy hệ quả —
  đổi trạng thái phải bấm trên màn. Lúc TẠO MỚI thì ghi được, vì đó là trạng thái ban đầu.
* **Tài khoản đăng nhập.** File không tạo tài khoản, không đặt mật khẩu, không gán vai trò —
  và từ 10/09/2026 cũng không xuất kèm tên tài khoản / vai trò nữa. Việc đó ở Tài khoản & Quyền.
* **Đổi Phòng/Tổ hoặc Bậc của người đã có** đi qua ĐÚNG luồng điều chuyển / nâng bậc
  (`apply_transition`) chứ không ghi thẳng cột: luồng đó còn đồng bộ phòng xuống tài khoản, gỡ
  chức trưởng phòng cũ, gỡ vai trò thuộc phòng cũ và ghi mốc Quá trình công tác. Ghi thẳng cột là
  để lại một tài khoản mang vai trò của phòng nó không còn thuộc về.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from io import BytesIO
from typing import Any

from .catalog_excel import ExcelSaiMan, mot_giao_dich
from .employee_service import EDITABLE_FIELDS, SENSITIVE_FIELDS, EmployeeError

#: Sheet dữ liệu. Không dấu — vài bản Excel cũ đặt tên sheet có dấu là hỏng công thức tham chiếu.
SHEET_CHINH = "Nhan su"
#: Sheet chỉ dẫn: liệt kê giá trị hợp lệ của các cột phải gõ đúng tên (phòng/tổ, bậc…).
SHEET_HD = "Huong dan"
#: Sheet ẨN ghi loại màn + phiên bản định dạng — chặn nhập nhầm workbook của màn khác.
SHEET_META = "_meta"
LOAI = "nhan_su"
PHIEN_BAN = "1"

#: Nhãn trạng thái — PHẢI khớp nhãn trên màn, nếu không kế toán đối chiếu là lệch.
TRANG_THAI = (
    ("probation", "Thử việc"),
    ("active", "Chính thức"),
    ("on_leave", "Nghỉ dài hạn"),
    ("suspended", "Đình chỉ"),
    ("resigned", "Đã nghỉ"),
)
GIOI_TINH = (("male", "Nam"), ("female", "Nữ"), ("other", "Khác"))
PIT_MODE = (
    ("luy_tien", "Luỹ tiến"),
    ("khau_tru_10", "Khấu trừ 10%"),
    ("cam_ket_08", "Cam kết 08"),
)

#: Lấy theo mẻ khi xuất. KHÔNG phải trần kết quả — vòng lặp chạy tới khi đủ `total`.
ME_XUAT = 200

#: Sheet ẨN chứa danh sách hợp lệ cho ô chọn (dropdown). Excel không nhận danh sách gõ thẳng
#: quá 255 ký tự — riêng cột Phòng/Tổ đã vượt — nên phải trỏ vào một vùng ô.
SHEET_DM = "_dm"

# --- Bảng màu: lấy theo màn Hồ sơ nhân sự để file mở ra không lạc khỏi phần mềm ------------
MAU_TIEU_DE = "FF1B2A41"
#: Ô lương / BHXH / ngân hàng — tô khác để người cầm file biết đây là khối nhạy cảm, và để
#: người thiếu quyền `view_salary` hiểu vì sao cả khối trống chứ không tưởng file lỗi.
MAU_TIEU_DE_NHAY_CAM = "FF7C3A12"
MAU_KE = "FFDCE1E8"
MAU_KE_NHOM = "FF8A97A8"
MAU_SOC = "FFF7F9FC"

#: Cột MỞ ĐẦU mỗi nhóm — chỉ dùng để kẻ vạch dọc phân nhóm, không đụng gì tới dữ liệu.
DAU_NHOM = ("Mã", "Ngày sinh", "Số sổ BHXH", "Số tài khoản NH")

#: Cột phải giữ nguyên chuỗi: số 0 đứng đầu của CCCD / số điện thoại / số tài khoản mà để Excel
#: đoán thành kiểu Số là mất sạch.
COT_DANG_CHU = ("code", "national_id", "phone", "emergency_contact_phone",
                "social_insurance_no", "pit_tax_code", "bank_account")

#: Số dòng phủ sẵn dropdown dưới dòng cuối — khai thêm người vẫn còn danh sách để chọn.
DONG_DU_DROPDOWN = 200
#: Dòng trống kẻ sẵn trong file MẪU cho ra hình hài một tờ khai.
DONG_TRONG_MAU = 30


class GiaTriSai(Exception):
    """Một ô không đọc được → thành một dòng trong bảng lỗi, không làm hỏng cả file."""


# --------------------------------------------------------------------------------------
# Khai cột
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cot:
    """Một cột Excel.

    `kieu`:
      * `chu`    — chuỗi.
      * `ngay`   — ghi ra dd/mm/yyyy (ĐỪNG ghi kiểu ngày thật: Excel mỗi máy hiện một định dạng
                   theo vùng, người đối chiếu là lệch); đọc vào nhận cả ngày thật lẫn chuỗi.
      * `nguyen` — số nguyên ≥ 0.
      * `chon`   — tập nhãn cố định (`chon`), nhận cả mã lẫn nhãn khi đọc.
      * `dm`     — tra danh mục theo TÊN (`dm` = phong | bac).
    """

    nhan: str
    field: str = ""
    kieu: str = "chu"
    chon: tuple[tuple[str, str], ...] = ()
    dm: str = ""
    #: Ô lương/BHXH/ngân hàng — che khi xuất nếu thiếu `view_salary`, bỏ khi nhập nếu thiếu
    #: `edit_salary`. Dùng CHUNG danh sách với service (`SENSITIVE_FIELDS`), không chép tay.
    nhay_cam: bool = False
    #: Giá trị khi ô để TRỐNG. Chỉ khai cho cột mà cột DB là NOT NULL (`prior_seniority_months`,
    #: `dependents_count`, `pit_mode`): "xoá giá trị" của một cột không cho rỗng nghĩa là ĐƯA VỀ
    #: MẶC ĐỊNH, không phải ghi NULL — ghi NULL là 500 trắng từ tầng DB, người khai không hiểu gì.
    mac_dinh: Any = None
    rong: int = 18


COT: tuple[Cot, ...] = (
    Cot("Mã", "code", rong=12),
    Cot("Họ tên", "full_name", rong=26),
    Cot("Phòng/Tổ", "department_id", kieu="dm", dm="phong", rong=24),
    Cot("Chức danh", "position", rong=22),
    Cot("Bậc tay nghề", "job_grade_id", kieu="dm", dm="bac", rong=18),
    Cot("Trạng thái", "status", kieu="chon", chon=TRANG_THAI, rong=14),
    Cot("Ngày vào", "hire_date", kieu="ngay", rong=12),
    Cot("Ngày hết thử việc", "probation_end_date", kieu="ngay", rong=16),
    Cot("Thâm niên trước (tháng)", "prior_seniority_months", kieu="nguyen", mac_dinh=0, rong=20),
    Cot("Ngày sinh", "date_of_birth", kieu="ngay", rong=12),
    Cot("Giới tính", "gender", kieu="chon", chon=GIOI_TINH, rong=10),
    Cot("CCCD", "national_id", rong=16),
    Cot("Ngày cấp CCCD", "national_id_date", kieu="ngay", rong=14),
    Cot("Nơi cấp CCCD", "national_id_place", rong=26),
    Cot("Điện thoại", "phone", rong=14),
    Cot("Email", "email", rong=24),
    Cot("Hộ khẩu thường trú", "permanent_address", rong=32),
    Cot("Chỗ ở hiện tại", "current_address", rong=32),
    Cot("Người liên hệ khẩn", "emergency_contact_name", rong=22),
    Cot("SĐT liên hệ khẩn", "emergency_contact_phone", rong=16),
    Cot("Số sổ BHXH", "social_insurance_no", nhay_cam=True, rong=16),
    Cot("MST cá nhân", "pit_tax_code", nhay_cam=True, rong=16),
    Cot("Số người phụ thuộc", "dependents_count", kieu="nguyen", mac_dinh=0, rong=16),
    Cot("Cách tính thuế TNCN", "pit_mode", kieu="chon", chon=PIT_MODE, nhay_cam=True,
        mac_dinh="luy_tien", rong=18),
    Cot("Số tài khoản NH", "bank_account", nhay_cam=True, rong=20),
    Cot("Ngân hàng", "bank_name", nhay_cam=True, rong=20),
    Cot("Nhóm lương", "payroll_group", nhay_cam=True, rong=16),
    # BỎ 10/09/2026 — sáu cột: Ca mặc định · Ghi chú · Ngày nghỉ việc · Lý do nghỉ việc ·
    # Tài khoản · Vai trò tài khoản. Ca nền gán ở Chấm công → Khai ca → Phân ca tháng (một ô
    # Excel không mang nổi lưới ngày × người); hai cột nghỉ việc do luồng cho nghỉ trên màn
    # sinh ra; hai cột tài khoản là dữ liệu của RBAC, file không tạo/gán được nên xuất kèm chỉ
    # tổ làm file rộng thêm. File cũ còn mang mấy tiêu đề này thì lượt nhập bỏ qua, không lỗi.
)

COT_THEO_NHAN = {c.nhan: c for c in COT}

#: Ô ghi thẳng lúc TẠO nhưng KHÔNG nằm trong `EDITABLE_FIELDS` (sửa hồ sơ thường không đụng tới).
#: `prior_seniority_months` chỉ là một con số nền, không kéo theo hệ quả nào ⇒ nhập sửa được.
CHI_KHI_TAO = ("prior_seniority_months",)


# --------------------------------------------------------------------------------------
# Ngữ cảnh tra tên ↔ id
# --------------------------------------------------------------------------------------


@dataclass
class NguCanh:
    """Bảng tra tên ↔ id của mọi danh mục mà file Excel nhắc tới bằng TÊN.

    Dựng MỘT LẦN cho cả lượt xuất/nhập: mỗi ô đi tra DB là vài nghìn round-trip cho một file
    vài trăm dòng.
    """

    ten: dict[str, dict[int, str]] = dc_field(default_factory=dict)
    id_theo_ten: dict[str, dict[str, int]] = dc_field(default_factory=dict)

    def ten_cua(self, nhom: str, gia_tri: int | None) -> str:
        if gia_tri is None:
            return ""
        return self.ten.get(nhom, {}).get(int(gia_tri), "")

    def id_cua(self, nhom: str, ten: str) -> int | None:
        return self.id_theo_ten.get(nhom, {}).get(ten.strip().casefold())

    def ten_hop_le(self, nhom: str) -> list[str]:
        return sorted(self.ten.get(nhom, {}).values())


def dung_ngu_canh(svc) -> NguCanh:
    """Đọc danh mục nền mà file nhắc tới bằng TÊN: phòng/tổ · bậc tay nghề."""
    from ..repositories.rbac_repo import DepartmentRepository

    db = svc.employees.db
    nc = NguCanh()
    nhom = {
        "phong": [(d.id, d.name) for d in DepartmentRepository(db).list_all()],
        "bac": [(g.id, g.name) for g in svc.employees.list_job_grades()],
    }
    for khoa, cap in nhom.items():
        nc.ten[khoa] = {i: t for i, t in cap}
        nc.id_theo_ten[khoa] = {t.strip().casefold(): i for i, t in cap}
    return nc


# --------------------------------------------------------------------------------------
# Đọc / ghi một ô
# --------------------------------------------------------------------------------------


def _rong(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _ra_chuoi(v: Any) -> str:
    """Số nguyên do Excel trả về dạng float (`900000001.0`) phải ra chuỗi không đuôi `.0` —
    nếu không thì số điện thoại / CCCD gõ vào ô kiểu Số quay về thành rác."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    return str(v).strip()


def _doc_ngay(v: Any) -> date | None:
    if _rong(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    chu = str(v).strip()
    for khuon in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(chu, khuon).date()
        except ValueError:
            continue
    raise GiaTriSai(f"Không đọc được ngày {chu!r} — ghi dạng dd/mm/yyyy.")


def doc_o(cot: Cot, gia_tri: Any, nc: NguCanh) -> Any:
    """Ô Excel → giá trị field. Ném `GiaTriSai` kèm câu tiếng Việt nói rõ phải sửa thế nào."""
    if cot.kieu == "ngay":
        return _doc_ngay(gia_tri)
    if _rong(gia_tri):
        return cot.mac_dinh
    if cot.kieu == "nguyen":
        try:
            so = int(float(_ra_chuoi(gia_tri)))
        except ValueError:
            raise GiaTriSai(f"{_ra_chuoi(gia_tri)!r} không phải số.") from None
        if so < 0:
            raise GiaTriSai("Không được là số âm.")
        return so
    if cot.kieu == "chon":
        chu = _ra_chuoi(gia_tri).casefold()
        for ma, nhan in cot.chon:
            if chu in (ma.casefold(), nhan.casefold()):
                return ma
        raise GiaTriSai("Chỉ nhận: " + " · ".join(n for _, n in cot.chon) + ".")
    if cot.kieu == "dm":
        chu = _ra_chuoi(gia_tri)
        found = nc.id_cua(cot.dm, chu)
        if found is None:
            raise GiaTriSai(f"Không có {cot.nhan.lower()} tên {chu!r} — xem sheet '{SHEET_HD}'.")
        return found
    return _ra_chuoi(gia_tri) or None


def _ghi_o(cot: Cot, employee, nc: NguCanh) -> Any:
    gia_tri = getattr(employee, cot.field, None)
    if cot.kieu == "dm":
        return nc.ten_cua(cot.dm, gia_tri)
    if cot.kieu == "ngay":
        return gia_tri.strftime("%d/%m/%Y") if gia_tri else ""
    if cot.kieu == "chon":
        return dict(cot.chon).get(gia_tri, gia_tri or "")
    if cot.kieu == "nguyen":
        return int(gia_tri or 0)
    return gia_tri if gia_tri is not None else ""


# --------------------------------------------------------------------------------------
# XUẤT
# --------------------------------------------------------------------------------------


def _danh_sach_chon(cot: Cot, nc: NguCanh) -> list[str]:
    """Các giá trị hợp lệ của một cột chọn — cùng nguồn với lúc ĐỌC ô, không chép tay lần hai."""
    if cot.kieu == "chon":
        return [nhan for _, nhan in cot.chon]
    if cot.kieu == "dm":
        return list(nc.ten_hop_le(cot.dm))
    return []


def _ke_dropdown(wb, ws, nc: NguCanh, den_dong: int) -> None:
    """Gắn ô chọn cho mọi cột phải gõ ĐÚNG TÊN (trạng thái · giới tính · thuế · phòng/tổ · bậc).

    Danh sách nằm ở sheet ẩn `_dm` rồi trỏ vào bằng vùng ô: gõ thẳng vào công thức thì Excel
    chặn ở 255 ký tự, mà riêng danh sách phòng/tổ đã dài hơn thế.
    """
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    can = [(i, c) for i, c in enumerate(COT, start=1) if _danh_sach_chon(c, nc)]
    if not can:
        return
    dm = wb.create_sheet(SHEET_DM)
    dm.sheet_state = "hidden"
    for thu_tu, (i, c) in enumerate(can, start=1):
        gia_tri = _danh_sach_chon(c, nc)
        cot_dm = get_column_letter(thu_tu)
        dm.cell(row=1, column=thu_tu).value = c.nhan
        for hang, v in enumerate(gia_tri, start=2):
            dm.cell(row=hang, column=thu_tu).value = v
        dv = DataValidation(
            type="list",
            formula1=f"={SHEET_DM}!${cot_dm}$2:${cot_dm}${len(gia_tri) + 1}",
            allow_blank=True,
            showDropDown=False,     # False = CÓ hiện mũi tên (cờ này là "ẩn dropdown")
        )
        dv.promptTitle = c.nhan
        dv.prompt = "Chọn trong danh sách; gõ tay cũng được nhưng phải đúng tên."
        dv.errorTitle = "Giá trị không có trong danh mục"
        dv.error = "Chọn một giá trị trong danh sách xổ xuống."
        ws.add_data_validation(dv)
        o = get_column_letter(i)
        dv.add(f"{o}2:{o}{den_dong}")


def _to_dinh_dang(ws, nc: NguCanh, *, so_dong: int) -> None:
    """Kẻ bảng cho sheet dữ liệu: dòng tiêu đề, vạch phân nhóm, sọc, khoá dòng tiêu đề, lọc."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    ke = Side(style="thin", color=MAU_KE)
    ke_nhom = Side(style="thin", color=MAU_KE_NHOM)
    soc = PatternFill("solid", fgColor=MAU_SOC)
    nen = PatternFill("solid", fgColor=MAU_TIEU_DE)
    nen_nhay = PatternFill("solid", fgColor=MAU_TIEU_DE_NHAY_CAM)
    chu_tieu_de = Font(bold=True, color="FFFFFFFF", size=11)

    ws.row_dimensions[1].height = 34
    for i, c in enumerate(COT, start=1):
        chu_cot = get_column_letter(i)
        ws.column_dimensions[chu_cot].width = c.rong
        trai = ke_nhom if c.nhan in DAU_NHOM else ke
        o = ws.cell(row=1, column=i)
        o.font = chu_tieu_de
        o.fill = nen_nhay if c.nhay_cam else nen
        o.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        o.border = Border(left=trai, right=ke, top=ke, bottom=ke)
        ngang = "center" if c.kieu in ("nguyen", "ngay") else "left"
        for hang in range(2, so_dong + 2):
            o = ws.cell(row=hang, column=i)
            o.alignment = Alignment(horizontal=ngang, vertical="center")
            o.border = Border(left=trai, right=ke, top=ke, bottom=ke)
            if hang % 2 == 1:
                o.fill = soc
            if c.field in COT_DANG_CHU:
                o.number_format = "@"
            elif c.kieu == "nguyen":
                o.number_format = "0"

    ws.freeze_panes = "C2"          # giữ luôn Mã + Họ tên khi kéo ngang 27 cột
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COT))}{max(so_dong + 1, 2)}"
    _ke_dropdown(ws.parent, ws, nc, so_dong + 1 + DONG_DU_DROPDOWN)


def _to_huong_dan(hd) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    ke = Side(style="thin", color=MAU_KE)
    hd.column_dimensions["A"].width = 26
    hd.column_dimensions["B"].width = 88
    hd.row_dimensions[1].height = 26
    for o in hd[1]:
        o.font = Font(bold=True, color="FFFFFFFF", size=11)
        o.fill = PatternFill("solid", fgColor=MAU_TIEU_DE)
        o.alignment = Alignment(horizontal="left", vertical="center")
    for hang in range(2, hd.max_row + 1):
        chu = str(hd.cell(row=hang, column=2).value or "")
        hd.row_dimensions[hang].height = 15 * max(1, -(-len(chu) // 84))
        for cot in (1, 2):
            o = hd.cell(row=hang, column=cot)
            o.alignment = Alignment(vertical="top", wrap_text=cot == 2)
            o.border = Border(left=ke, right=ke, top=ke, bottom=ke)
            if cot == 1:
                o.font = Font(bold=True)


def _dung_workbook(nc: NguCanh, *, kem_huong_dan: bool):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_CHINH
    ws.append([c.nhan for c in COT])

    if kem_huong_dan:
        hd = wb.create_sheet(SHEET_HD)
        hd.append(["Cột", "Gõ đúng một trong các giá trị sau"])
        hd.append(["Mã", "Mã đã có thì máy sửa đúng người đó. Mã chưa có thì máy tạo người "
                         "mới và giữ nguyên mã đó. Bỏ TRỐNG thì máy tự cấp mã (NV001, NV002…)."])
        hd.append(["Phòng/Tổ", " · ".join(nc.ten_hop_le("phong"))])
        hd.append(["Bậc tay nghề", " · ".join(nc.ten_hop_le("bac"))])
        hd.append(["Trạng thái", " · ".join(n for _, n in TRANG_THAI)
                   + "  (người ĐÃ CÓ thì không đổi được bằng file — bấm trên màn)"])
        hd.append(["Giới tính", " · ".join(n for _, n in GIOI_TINH)])
        hd.append(["Cách tính thuế TNCN", " · ".join(n for _, n in PIT_MODE)])
        hd.append(["Ngày (mọi cột)", "dd/mm/yyyy — ví dụ 15/01/2024"])
        hd.append(["Cột không cho rỗng", "Thâm niên trước · Số người phụ thuộc · Cách tính thuế "
                                         "TNCN: để trống là về MẶC ĐỊNH (0 · 0 · Luỹ tiến), "
                                         "không phải để nguyên giá trị cũ."])
        hd.append(["Khối tô nâu", "Lương · BHXH · Ngân hàng: chỉ người có quyền xem lương mới "
                                  "thấy dữ liệu; thiếu quyền thì cả khối xuất ra trống."])
        _to_huong_dan(hd)

    meta = wb.create_sheet(SHEET_META)
    meta["A1"], meta["B1"] = "loai", LOAI
    meta["A2"], meta["B2"] = "phien_ban", PHIEN_BAN
    meta.sheet_state = "hidden"
    return wb, ws


def _bytes(wb) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def xuat_excel(rows, nc: NguCanh, *, co_xem_luong: bool) -> bytes:
    """Workbook đầy đủ của những người trong `rows` (đã lọc + đã cắt theo phạm vi quyền).

    `co_xem_luong=False` ⇒ ô lương/BHXH/ngân hàng ra RỖNG: đọc hồ sơ đã che thì file xuất cũng
    phải che, không thì `view_salary` chỉ là một tấm rèm trên giao diện.
    """
    wb, ws = _dung_workbook(nc, kem_huong_dan=False)
    for e in rows:
        ws.append([
            "" if (c.nhay_cam and not co_xem_luong) else _ghi_o(c, e, nc)
            for c in COT
        ])
    _to_dinh_dang(ws, nc, so_dong=max(ws.max_row - 1, 0))
    return _bytes(wb)


def mau_nhap(nc: NguCanh) -> bytes:
    """File mẫu: đúng tiêu đề của file xuất, không kèm ai, cộng sheet Hướng dẫn."""
    wb, ws = _dung_workbook(nc, kem_huong_dan=True)
    # Kẻ sẵn mấy chục dòng trống cho ra hình tờ khai. Dòng trống thì lượt nhập bỏ qua.
    _to_dinh_dang(ws, nc, so_dong=DONG_TRONG_MAU)
    return _bytes(wb)


# --------------------------------------------------------------------------------------
# NHẬP
# --------------------------------------------------------------------------------------


@dataclass
class Loi:
    sheet: str
    dong: int
    cot: str
    ly_do: str


@dataclass
class KetQua:
    hop_le: bool = False
    tong_dong: int = 0
    tao_moi: int = 0
    cap_nhat: int = 0
    khong_doi: int = 0
    da_ghi: bool = False
    loi: list[Loi] = dc_field(default_factory=list)


def _kiem_meta(wb) -> None:
    if SHEET_META not in wb.sheetnames:
        return  # file người dùng tự gõ tay — vẫn nhận, tiêu đề cột là hợp đồng thật.
    meta = wb[SHEET_META]
    ghi = {str(r[0].value): str(r[1].value) for r in meta.iter_rows(min_row=1, max_col=2)
           if r[0].value is not None}
    if ghi.get("loai") not in (None, LOAI):
        raise ExcelSaiMan(
            f"File này là workbook của màn khác ({ghi.get('loai')}), không phải Hồ sơ nhân sự.")
    if ghi.get("phien_ban") not in (None, PHIEN_BAN):
        raise ExcelSaiMan(
            "File thuộc phiên bản định dạng khác — bấm 'Xuất Excel' lấy file mới rồi sửa trên đó.")


def _bang_nhau(cu: Any, moi: Any) -> bool:
    """So sánh giá trị cũ/mới. Chuỗi rỗng và `None` là MỘT — không thì mỗi lần nhập lại chính
    file vừa xuất là cả bảng bị tính thành 'cập nhật' và đẻ một loạt dòng nhật ký ma."""
    if cu in (None, "") and moi in (None, ""):
        return True
    if isinstance(cu, (int, float)) and isinstance(moi, (int, float)):
        return float(cu) == float(moi)
    return cu == moi


def nhap_excel(du_lieu: bytes, *, svc, nc: NguCanh, actor, scope: str,
               co_sua_luong: bool, co_dieu_chuyen: bool, ghi: bool) -> KetQua:
    """Đọc file → dựng kế hoạch → chạy trong MỘT giao dịch. `ghi=False` = xem trước (rollback)."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(BytesIO(du_lieu), data_only=True)
    except Exception:
        raise ExcelSaiMan("Không đọc được file — cần đúng tệp .xlsx.") from None
    _kiem_meta(wb)

    ws = wb[SHEET_CHINH] if SHEET_CHINH in wb.sheetnames else wb.worksheets[0]
    tieu_de: dict[str, int] = {}
    for o in ws[1]:
        if o.value is not None and str(o.value).strip():
            tieu_de.setdefault(str(o.value).strip(), o.column)
    co_mat = [c for c in COT if c.nhan in tieu_de]
    if not any(c.field == "code" for c in co_mat) or not any(
            c.field == "full_name" for c in co_mat):
        raise ExcelSaiMan(
            "File thiếu cột 'Mã' hoặc 'Họ tên' — bấm 'Tải file mẫu' rồi khai trên file đó.")
    # Ô lương/BHXH thiếu quyền `edit_salary` ⇒ BỎ cột khỏi lượt nhập (không chặn cả file):
    # cùng luật với `create_employee` / `update_employee`, không lưu lén.
    if not co_sua_luong:
        co_mat = [c for c in co_mat if not c.nhay_cam]

    kq = KetQua()
    ke_hoach: list[tuple[int, dict]] = []
    for hang in range(2, ws.max_row + 1):
        o = {c.nhan: ws.cell(row=hang, column=tieu_de[c.nhan]).value for c in co_mat}
        if all(_rong(v) for v in o.values()):
            continue
        kq.tong_dong += 1
        gia_tri: dict[str, Any] = {}
        hong = False
        for c in co_mat:
            try:
                gia_tri[c.field] = doc_o(c, o[c.nhan], nc)
            except GiaTriSai as e:
                kq.loi.append(Loi(ws.title, hang, c.nhan, str(e)))
                hong = True
        if hong:
            continue
        if not gia_tri.get("code") and not gia_tri.get("full_name"):
            kq.loi.append(Loi(ws.title, hang, "Họ tên", "Bắt buộc khi tạo người mới."))
            continue
        ke_hoach.append((hang, gia_tri))

    db = svc.employees.db
    with mot_giao_dich(db) as gd:
        # Xem trước KHÔNG được "ting" cho ai: `update_employee` đẩy thông báo đổi ca ngay lúc gọi,
        # mà bản xem trước rollback ngay sau đó ⇒ người ta nhận báo đổi ca chưa hề xảy ra.
        with _im_lang_neu_xem_truoc(ghi):
            for hang, gia_tri in ke_hoach:
                diem = db.begin_nested()
                try:
                    da_doi = _chay_mot_dong(
                        svc, nc, gia_tri, actor=actor, scope=scope,
                        co_sua_luong=co_sua_luong, co_dieu_chuyen=co_dieu_chuyen, kq=kq,
                        hang=hang, sheet=ws.title,
                    )
                    diem.commit()
                    if da_doi is None:
                        pass  # dòng đã có lỗi, `_chay_mot_dong` ghi vào `kq.loi` rồi
                    elif da_doi == "tao":
                        kq.tao_moi += 1
                    elif da_doi == "sua":
                        kq.cap_nhat += 1
                    else:
                        kq.khong_doi += 1
                except EmployeeError as e:
                    diem.rollback()
                    kq.loi.append(Loi(sheet=ws.title, dong=hang, cot="", ly_do=str(e)))
        kq.hop_le = not kq.loi
        kq.da_ghi = bool(ghi and kq.hop_le)
        gd["chot"] = kq.da_ghi
    return kq


class _im_lang_neu_xem_truoc:
    """Tắt đẩy thông báo đổi ca trong lượt XEM TRƯỚC. No-op khi chốt thật."""

    def __init__(self, ghi: bool) -> None:
        self.ghi = ghi

    def __enter__(self):
        if self.ghi:
            return self
        from . import employee_service as es

        self._that = es.push_shift_changes
        es.push_shift_changes = lambda logs: (0, 0)  # type: ignore[assignment]
        return self

    def __exit__(self, *a):
        if not self.ghi:
            from . import employee_service as es

            es.push_shift_changes = self._that  # type: ignore[assignment]
        return False


def _chay_mot_dong(svc, nc: NguCanh, gia_tri: dict, *, actor, scope: str, co_sua_luong: bool,
                   co_dieu_chuyen: bool, kq: KetQua, hang: int, sheet: str) -> str | None:
    """Ghi một dòng. Trả 'tao' | 'sua' | 'nguyen' (không đổi), hoặc None nếu dòng có lỗi."""
    gia_tri = dict(gia_tri)
    ma = gia_tri.pop("code", None)
    if not ma:
        _tao_moi(svc, gia_tri, actor=actor, co_sua_luong=co_sua_luong)
        return "tao"

    emp = svc.employees.find_by_code(str(ma).strip())
    if emp is None:
        # Mã chưa có ⇒ TẠO MỚI GIỮ NGUYÊN MÃ ĐÓ, không phải báo lỗi.
        # Bản đầu 10/09/2026 báo lỗi ở đây để chặn gõ nhầm mã. Nhưng thử nạp chính file xuất vào
        # một DB TRẮNG thì 199/200 dòng đỏ hết: file mang sẵn NV002…NV200 mà bên kia chưa có ai.
        # Cách duy nhất còn lại là xoá tay cả cột Mã, mà xoá xong máy cấp lại mã từ đầu ⇒ lệch
        # mã của cả công ty. Mã NV nằm trên hợp đồng / thẻ / bảng lương nên phải giữ.
        # Gõ nhầm mã vẫn thấy được: bản xem trước đếm dòng đó vào "tạo mới", không phải "cập nhật".
        _tao_moi(svc, gia_tri, actor=actor, co_sua_luong=co_sua_luong, ma=str(ma).strip())
        return "tao"
    if not svc.employees.can_access(employee=emp, scope=scope, actor=actor):
        kq.loi.append(Loi(sheet, hang, "Mã", f"Mã {ma!r} nằm ngoài phạm vi dữ liệu của bạn."))
        return None
    return _cap_nhat(svc, nc, emp, gia_tri, actor=actor, scope=scope,
                     co_sua_luong=co_sua_luong, co_dieu_chuyen=co_dieu_chuyen,
                     kq=kq, hang=hang, sheet=sheet)


def _tao_moi(svc, gia_tri: dict, *, actor, co_sua_luong: bool, ma: str | None = None) -> None:
    fields = dict(gia_tri)
    department_id = fields.pop("department_id", None)
    # Cột Trạng thái vắng khỏi file ⇒ mặc định Thử việc, y như bấm "Thêm nhân viên" trên màn.
    trang_thai = fields.pop("status", None) or "probation"
    hire_date = fields.pop("hire_date", None)
    svc.create_employee(
        actor=actor, department_id=department_id, status=trang_thai, hire_date=hire_date,
        fields=fields, can_edit_salary=co_sua_luong, code=ma,
    )


def _cap_nhat(svc, nc: NguCanh, emp, gia_tri: dict, *, actor, scope: str, co_sua_luong: bool,
              co_dieu_chuyen: bool, kq: KetQua, hang: int, sheet: str) -> str | None:
    doi = False

    # 1. Trạng thái — Excel KHÔNG đổi được (xem đầu file).
    if "status" in gia_tri and gia_tri["status"] and gia_tri["status"] != emp.status:
        nhan = dict(TRANG_THAI)
        kq.loi.append(Loi(
            sheet, hang, "Trạng thái",
            f"Đang là {nhan.get(emp.status, emp.status)!r} — đổi trạng thái phải bấm trên màn "
            "(nghỉ việc / đình chỉ còn khoá tài khoản), file không làm thay được."))
        return None

    # 2. Phòng/Tổ + Bậc — đi qua ĐÚNG luồng điều chuyển / nâng bậc.
    phong_moi = gia_tri.get("department_id", emp.department_id) if "department_id" in gia_tri \
        else emp.department_id
    bac_moi = gia_tri.get("job_grade_id", emp.job_grade_id) if "job_grade_id" in gia_tri \
        else emp.job_grade_id
    doi_phong = phong_moi != emp.department_id
    doi_bac = bac_moi != emp.job_grade_id
    if (doi_phong or doi_bac) and not co_dieu_chuyen:
        kq.loi.append(Loi(sheet, hang, "Phòng/Tổ" if doi_phong else "Bậc tay nghề",
                          "Đổi phòng/tổ hoặc bậc của người đã có cần quyền Điều chuyển."))
        return None
    if doi_phong:
        svc.apply_transition(
            employee_id=emp.id, scope=scope, actor=actor, kind="transfer",
            effective_date=date.today(), note="Nhập Excel",
            new_department_id=phong_moi, new_job_grade_id=bac_moi,
        )
        doi = True
    elif doi_bac:
        svc.apply_transition(
            employee_id=emp.id, scope=scope, actor=actor, kind="promote",
            effective_date=date.today(), note="Nhập Excel", new_job_grade_id=bac_moi,
        )
        doi = True

    # 3. Ô nền không kéo theo hệ quả nào — ghi thẳng.
    thang: dict[str, Any] = {}
    for f in CHI_KHI_TAO:
        if f in gia_tri and not _bang_nhau(getattr(emp, f, None), gia_tri[f]):
            thang[f] = gia_tri[f]
    if thang:
        svc.employees.update(emp, **thang)
        doi = True

    # 4. Phần còn lại của hồ sơ — qua service (validate + nhật ký + đồng bộ tài khoản).
    sua = {f: v for f, v in gia_tri.items()
           if f in EDITABLE_FIELDS and not _bang_nhau(getattr(emp, f, None), v)}
    if not co_sua_luong:
        sua = {f: v for f, v in sua.items() if f not in SENSITIVE_FIELDS}
    if sua:
        svc.update_employee(employee_id=emp.id, scope=scope, actor=actor, fields=sua,
                            can_edit_salary=co_sua_luong)
        doi = True

    return "sua" if doi else "nguyen"
