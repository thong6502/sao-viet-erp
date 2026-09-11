"""Nhập Excel — KHÁCH HÀNG (11/09/2026). Tải mẫu rỗng → điền khách mới → xem trước → ghi.

Vì sao KHÔNG dùng `services/catalog_excel.py` (chủ chốt 11/09/2026: *"không muốn động sâu, các màn
khác đang ổn"*): cơ chế chung **bắt buộc có cột Mã** và **từ chối dòng Mã trống**
(`catalog_excel.py` — `'Sheet chính thiếu cột "Mã"'` / `"Thiếu mã."`). Mà mã khách hàng là mã hệ tự
cấp (`KH001`…), người dùng KHÔNG gõ — model ghi thẳng *"never entered by the user"*. Dạy cơ chế
chung hiểu "mã trống = dòng mới" thì sửa được cho cả ba màn đang vướng (Công việc khoán · Kho hàng ·
Khuôn bế), nhưng đó là code dùng chung của 15 màn ⇒ để lại, ghi trong
`docs/spec-nhap-excel-khach-hang.md`.

Bài toán ở đây NHỎ hơn hẳn bài toán danh mục nên bản riêng cũng ngắn: **một sheet**, **chỉ thêm
mới** (không upsert, không so dòng cũ/mới), **không sheet con**, **không round-trip khoá lạ**. Phần
thật sự phải có là: đọc .xlsx · gom lỗi theo dòng · xem trước bằng rollback · MỘT giao dịch cho cả
file.

Dùng lại mà KHÔNG sửa gì: ba hằng số `SHEET_META` / `PHIEN_BAN` / `ExcelSaiMan` của cơ chế chung —
nhờ đó file mẫu màn này mang đúng dấu `_meta` như mọi màn khác, và nhập nhầm file của màn khác vẫn
bị chặn bằng đúng một cơ chế. Import hằng số là ĐỌC, không phải sửa.

BA LUẬT XƯƠNG SỐNG:

1. **Mỗi dòng = một khách MỚI.** Không có cột Mã ⇒ không có đường trỏ vào khách đã có.
2. **Một giao dịch cho cả file** — còn một dòng lỗi thì KHÔNG ghi gì cả. `ghi=False` (xem trước)
   chạy y hệt lượt thật rồi `rollback`, nên con số xem trước là con số THẬT.
3. **Trùng MST / tên / email là CẢNH BÁO, không phải lỗi.** Model nói rõ `tax_code` được index
   nhưng KHÔNG unique, trùng là cảnh báo mềm (§34, §41) — form nhập tay cũng chỉ cảnh báo. Chặn ở
   Excel là chặt hơn cả form, tức là sai.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.customer import KIND_CA_NHAN, KIND_CONG_TY
from ..models.user import User
from .catalog_excel import PHIEN_BAN, SHEET_META, ExcelSaiMan
from .customer_service import (
    CustomerError,
    CustomerService,
    nguoi_du_tu_cach_nhan_khach,
)

#: Dấu nhận diện màn, ghi vào sheet `_meta` ẩn. Nhập file của màn khác ⇒ chặn ngay ở cửa.
LOAI = "khach_hang"
TIEU_DE = "Khách hàng"
#: Sheet ẨN chứa danh sách Sale — nguồn cho ô chọn xổ xuống ở cột "Sale phụ trách".
SHEET_SALE = "_sale"

# Nhãn tiếng Việt của LOẠI KHÁCH. Ô Excel là chữ người đọc, không phải mã máy — người khai gõ
# "Công ty", không gõ "cong_ty".
NHAN_LOAI = {"công ty": KIND_CONG_TY, "cá nhân": KIND_CA_NHAN}
NHAN_LOAI_NGUOC = {KIND_CONG_TY: "Công ty", KIND_CA_NHAN: "Cá nhân"}

# Tên tiêu chí trùng, để câu cảnh báo đọc được thành lời.
NHAN_TRUNG = {"tax_code": "MST", "name": "tên", "email": "email"}


@dataclass(frozen=True)
class Cot:
    """Một cột trên sheet chính.

    `tai_chinh=True` ⇒ chỉ xuất ra mẫu cho người có quyền `set_credit_terms`, và khi nhập thì
    người không có quyền sẽ bị BỎ QUA cột đó (kèm lời nói rõ), chứ không ghi lén và cũng không
    chặn cả file — xem `nhap()`.
    """

    nhan: str
    khoa: str
    kieu: str            # chu | so_nguyen | phan_tram | loai_khach | sale
    bat_buoc: bool = False
    rong: int = 18
    tai_chinh: bool = False


COT: tuple[Cot, ...] = (
    Cot("Tên khách hàng", "name", "chu", bat_buoc=True, rong=32),
    Cot("Loại khách", "customer_kind", "loai_khach", bat_buoc=True, rong=14),
    Cot("MST", "tax_code", "chu", rong=16),
    Cot("Điện thoại", "phone", "chu", rong=16),
    Cot("Email", "email", "chu", rong=26),
    Cot("Địa chỉ", "address", "chu", rong=40),
    Cot("Người liên hệ", "contact_name", "chu", rong=22),
    Cot("Sale phụ trách", "sale_user_id", "sale", rong=22),
    Cot("Hạn mức công nợ (đ)", "credit_limit", "so_nguyen", rong=20, tai_chinh=True),
    Cot("Số ngày nợ tối đa", "payment_term_days", "so_nguyen", rong=18, tai_chinh=True),
    Cot("Chiết khấu tối thiểu (%)", "discount_min_pct", "phan_tram", rong=20, tai_chinh=True),
    Cot("Chiết khấu tối đa (%)", "discount_max_pct", "phan_tram", rong=20, tai_chinh=True),
    Cot("Markup tối thiểu (%)", "markup_min_pct", "phan_tram", rong=20, tai_chinh=True),
    Cot("Markup tối đa (%)", "markup_max_pct", "phan_tram", rong=20, tai_chinh=True),
)

KHOA_TAI_CHINH = tuple(c.khoa for c in COT if c.tai_chinh)


# ======================= kết quả =======================


@dataclass
class LoiDong:
    dong: int
    cot: str
    ly_do: str


@dataclass
class CanhBaoDong:
    dong: int
    ly_do: str


@dataclass
class KetQua:
    tong_dong: int = 0
    tao_moi: int = 0
    da_ghi: bool = False
    #: File có cột tài chính nhưng người nhập không có quyền ⇒ đã bỏ qua đúng mấy cột đó.
    bo_qua_tai_chinh: bool = False
    loi: list[LoiDong] = dc_field(default_factory=list)
    canh_bao: list[CanhBaoDong] = dc_field(default_factory=list)

    @property
    def hop_le(self) -> bool:
        return not self.loi


# ======================= đọc ô =======================


def _chuoi(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _so_nguyen(v: Any, nhan: str) -> tuple[int | None, str | None]:
    """(giá trị, lỗi). Ô trống ⇒ (None, None) — "chưa đặt", không phải 0."""
    s = _chuoi(v)
    if s is None:
        return None, None
    # Excel trả số về dạng float (2000000.0) — ép về int khi phần lẻ bằng 0.
    try:
        f = float(str(s).replace(",", "").replace(" ", ""))
    except ValueError:
        return None, f"{nhan}: phải là số."
    if f != int(f):
        return None, f"{nhan}: phải là số nguyên."
    if f < 0:
        return None, f"{nhan}: không được âm."
    return int(f), None


def _phan_tram(v: Any, nhan: str) -> tuple[float | None, str | None]:
    s = _chuoi(v)
    if s is None:
        return None, None
    try:
        f = float(str(s).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None, f"{nhan}: phải là số phần trăm."
    if not 0 <= f <= 100:
        return None, f"{nhan}: phải trong khoảng 0–100."
    return f, None


def _map_sale(db: Session) -> tuple[dict[str, int], set[int], list[str]]:
    """({khoá tra: user_id}, {id đủ tư cách}, [tên hiển thị trong ô chọn]).

    Tra được bằng CẢ tên đăng nhập lẫn họ tên (hạ chữ, gom khoảng trắng) — người khai gõ cái nào
    cũng ra. Họ tên TRÙNG NHAU thì bỏ khoá tên đi, chỉ còn tra bằng tên đăng nhập: đoán bừa một
    trong hai là gán khách cho nhầm người, mà đây là cột quyết định ai được thấy khách đó.

    Bảng tra giữ MỌI người, nhưng ô chọn và cửa kiểm chỉ nhận người **đủ tư cách nhận khách**
    (`nguoi_du_tu_cach_nhan_khach` — cùng luật với ô "NV phụ trách" trên màn). Giữ cả người ngoài
    khối trong bảng tra là có chủ ý: gõ tên Thủ kho thì phải báo *"không thuộc khối Kinh doanh"*
    chứ không phải *"không tìm thấy người nào tên đó"* — hai câu dẫn người dùng đi hai hướng khác
    hẳn nhau.
    """
    rows = list(db.execute(select(User.id, User.username, User.name)).all())
    du_tu_cach = nguoi_du_tu_cach_nhan_khach(db)

    dem_ten: dict[str, int] = {}
    for _, _, ten in rows:
        k = _khoa(ten)
        if k:
            dem_ten[k] = dem_ten.get(k, 0) + 1

    tra: dict[str, int] = {}
    hien: list[str] = []
    for uid, username, ten in rows:
        ku = _khoa(username)
        if ku:
            tra[ku] = int(uid)
        kt = _khoa(ten)
        if kt and dem_ten.get(kt, 0) == 1:
            tra[kt] = int(uid)
        if int(uid) in du_tu_cach:
            hien.append((ten or username or "").strip() or str(username))
    return tra, du_tu_cach, sorted(set(h for h in hien if h))


def _khoa(s: str | None) -> str:
    return " ".join((s or "").strip().lower().split())


# ======================= tạo file mẫu =======================


def tao_mau(db: Session, *, co_tai_chinh: bool) -> bytes:
    """Workbook RỖNG — chỉ dòng tiêu đề (chốt 11/09/2026).

    Không kèm khách đang có: mẫu này để THÊM MỚI. Muốn sửa hàng loạt thì phải có cột Mã, mà mã là
    của hệ — đó là việc khác, ghi trong `docs/spec-nhap-excel-khach-hang.md`.

    Người không có quyền `set_credit_terms` thì 6 cột tài chính KHÔNG xuất ra — đưa ra một cột họ
    không được ghi chỉ tổ mời họ điền vào chỗ sẽ bị bỏ qua.
    """
    cot = [c for c in COT if co_tai_chinh or not c.tai_chinh]

    wb = Workbook()
    ws_meta = wb.active
    ws_meta.title = SHEET_META
    ws_meta.append(["khoa", "gia_tri"])
    ws_meta.append(["loai", LOAI])
    ws_meta.append(["phien_ban", PHIEN_BAN])
    ws_meta.sheet_state = "hidden"

    ws = wb.create_sheet(TIEU_DE)
    ws.append([c.nhan for c in cot])
    dam = Font(bold=True, color="FFFFFF")
    nen = PatternFill("solid", fgColor="1F3864")
    for i, c in enumerate(cot, start=1):
        o = ws.cell(row=1, column=i)
        o.font, o.fill = dam, nen
        ws.column_dimensions[get_column_letter(i)].width = c.rong
    ws.freeze_panes = "A2"      # tiêu đề dính khi cuộn — file này người ta gõ hàng trăm dòng

    # Ô chọn xổ xuống: lấy THẲNG từ hệ thống, để người khai không phải đoán chữ.
    _o_chon(ws, cot, "customer_kind", '"Công ty,Cá nhân"')
    _, _, ten_sale = _map_sale(db)
    if ten_sale:
        ws_sale = wb.create_sheet(SHEET_SALE)
        for t in ten_sale:
            ws_sale.append([t])
        ws_sale.sheet_state = "hidden"
        _o_chon(ws, cot, "sale_user_id",
                f"={SHEET_SALE}!$A$1:$A${len(ten_sale)}")

    ra = BytesIO()
    wb.save(ra)
    return ra.getvalue()


#: Cột của file XUẤT. Nhãn trùng khít file mẫu nhập ở phần dùng chung, cộng hai cột chỉ-có-khi-xuất
#: (`Mã KH` — mã hệ đã cấp, và nó là lý do file xuất KHÔNG nhập ngược lại được: mẫu nhập cố ý không
#: có cột Mã, xem `tao_mau`). Hai file đọc quen mắt nhau là có chủ ý.
COT_XUAT = ("Mã KH", *(c.nhan for c in COT))


def xuat(db: Session, khach: list) -> bytes:
    """Xuất danh bạ ĐANG THẤY ra .xlsx — phạm vi do người gọi lọc sẵn (router đã soi scope).

    Đây là file ĐỌC/ĐỐI CHIẾU, không phải file để sửa rồi nhập ngược: nhập chỉ thêm mới, và mẫu
    nhập không có cột Mã. Sửa khách đã có thì sửa trên màn.
    """
    ten = {int(i): (t or u or "") for i, u, t in
           db.execute(select(User.id, User.username, User.name)).all()}

    wb = Workbook()
    ws = wb.active
    ws.title = TIEU_DE
    ws.append(list(COT_XUAT))
    dam = Font(bold=True, color="FFFFFF")
    nen = PatternFill("solid", fgColor="1F3864")
    rong = [14, *(c.rong for c in COT)]
    for i in range(1, len(COT_XUAT) + 1):
        o = ws.cell(row=1, column=i)
        o.font, o.fill = dam, nen
        ws.column_dimensions[get_column_letter(i)].width = rong[i - 1]
    ws.freeze_panes = "A2"

    for k in khach:
        ws.append([
            k.code,
            k.name,
            NHAN_LOAI_NGUOC.get(k.customer_kind, ""),
            k.tax_code or "",
            k.phone or "",
            k.email or "",
            k.address or "",
            k.contact_name or "",
            ten.get(k.sale_user_id, "") if k.sale_user_id else "",
            k.credit_limit,
            k.payment_term_days,
            k.discount_min_pct,
            k.discount_max_pct,
            k.markup_min_pct,
            k.markup_max_pct,
        ])

    ra = BytesIO()
    wb.save(ra)
    return ra.getvalue()


def _o_chon(ws, cot: list[Cot], khoa: str, cong_thuc: str) -> None:
    """Gắn ô chọn cho một cột, phủ 500 dòng đầu — quá số đó thì gõ tay, vẫn nhập được."""
    vi_tri = next((i for i, c in enumerate(cot, start=1) if c.khoa == khoa), None)
    if vi_tri is None:
        return
    dv = DataValidation(type="list", formula1=cong_thuc, allow_blank=True, showDropDown=False)
    ws.add_data_validation(dv)
    chu = get_column_letter(vi_tri)
    dv.add(f"{chu}2:{chu}501")


# ======================= đọc file =======================


def _mo_workbook(du_lieu: bytes):
    try:
        return load_workbook(BytesIO(du_lieu), data_only=True)
    except Exception:  # noqa: BLE001 — mọi kiểu hỏng của file đều cùng một câu trả lời
        raise ExcelSaiMan("Không đọc được file — phải là .xlsx đúng mẫu tải từ hệ thống.") from None


def _kiem_meta(wb) -> None:
    if SHEET_META not in wb.sheetnames:
        raise ExcelSaiMan(
            'File không phải mẫu của màn Khách hàng (thiếu dấu "_meta"). Bấm "Tải file mẫu" '
            "rồi điền vào đúng file đó."
        )
    gia: dict[str, Any] = {}
    for hang in wb[SHEET_META].iter_rows(min_row=2, values_only=True):
        if hang and hang[0]:
            gia[str(hang[0]).strip()] = hang[1]
    if str(gia.get("loai") or "").strip() != LOAI:
        raise ExcelSaiMan(
            f'File này là mẫu của màn khác ("{gia.get("loai")}"), không phải Khách hàng.'
        )


# ======================= nhập =======================


def nhap(db: Session, svc: CustomerService, du_lieu: bytes, *, actor, scope: str,
         co_tai_chinh: bool, ghi: bool) -> KetQua:
    """Đọc file → dựng kế hoạch → chạy trong MỘT giao dịch.

    `ghi=False` là XEM TRƯỚC: chạy y hệt lượt thật rồi `rollback`. Cố ý không làm một bản kiểm
    "sơ bộ" nhẹ hơn — nếu xem trước dễ dãi hơn lúc ghi thì người dùng bấm Xác nhận xong mới ăn lỗi,
    đúng thứ mà cái nút xem trước sinh ra để tránh.
    """
    wb = _mo_workbook(du_lieu)
    _kiem_meta(wb)
    if TIEU_DE not in wb.sheetnames:
        raise ExcelSaiMan(f'File thiếu sheet "{TIEU_DE}".')

    hang = list(wb[TIEU_DE].iter_rows(values_only=True))
    if not hang:
        raise ExcelSaiMan(f'Sheet "{TIEU_DE}" trống — không có cả dòng tiêu đề.')

    tieu_de = [(_chuoi(o) or "") for o in hang[0]]
    vi_tri = {c.khoa: tieu_de.index(c.nhan) for c in COT if c.nhan in tieu_de}
    thieu = [c.nhan for c in COT if c.bat_buoc and c.khoa not in vi_tri]
    if thieu:
        raise ExcelSaiMan("File thiếu cột bắt buộc: " + " · ".join(thieu) + ". Tải lại file mẫu.")

    kq = KetQua()
    # File có cột tài chính mà người nhập KHÔNG có quyền: bỏ qua đúng mấy cột đó, ghi phần còn lại,
    # và NÓI RA. Ghi lén là vượt quyền; chặn cả file là một người mượn mẫu của đồng nghiệp rồi
    # không nhập nổi gì.
    co_cot_tc = any(k in vi_tri for k in KHOA_TAI_CHINH)
    dung_tai_chinh = co_cot_tc and co_tai_chinh
    kq.bo_qua_tai_chinh = co_cot_tc and not co_tai_chinh

    tra_sale, du_tu_cach, _ = _map_sale(db)
    ke_hoach: list[tuple[int, dict, dict]] = []

    for so_dong, dong in enumerate(hang[1:], start=2):
        o = {c.khoa: (dong[vi_tri[c.khoa]] if vi_tri.get(c.khoa, -1) < len(dong) else None)
             for c in COT if c.khoa in vi_tri}
        # Dòng TRẮNG HOÀN TOÀN: bỏ qua, không tính là lỗi — ai cũng để thừa vài dòng cuối file.
        if all(_chuoi(v) is None for v in o.values()):
            continue
        kq.tong_dong += 1

        thong, tai_chinh = _doc_dong(o, so_dong, tra_sale, du_tu_cach,
                                     dung_tai_chinh, kq.loi)
        if thong is not None:
            ke_hoach.append((so_dong, thong, tai_chinh))

    # Còn lỗi thì DỪNG TRƯỚC KHI chạm DB — không cần rollback cái chưa từng ghi.
    if kq.loi:
        return kq

    try:
        for so_dong, thong, tai_chinh in ke_hoach:
            kh, trung = svc.create_customer(actor=actor, commit=False, **thong)
            kq.tao_moi += 1
            for tieu_chi, khac in trung:
                kq.canh_bao.append(CanhBaoDong(
                    so_dong,
                    f"Trùng {NHAN_TRUNG.get(tieu_chi, tieu_chi)} với {khac.code} · {khac.name}",
                ))
            if tai_chinh:
                svc.update_financial(customer_id=kh.id, scope=scope, actor=actor,
                                     commit=False, **tai_chinh)
        if ghi:
            db.commit()
            kq.da_ghi = True
        else:
            db.rollback()
    except CustomerError as e:
        # Lỗi nghiệp vụ lộ ra ở tầng service (vd rào min > max, ngoài phạm vi quyền) — trả về dưới
        # dạng lỗi DÒNG chứ không 500, và KHÔNG ghi gì cả.
        db.rollback()
        kq.loi.append(LoiDong(so_dong, "", str(e)))
        kq.tao_moi = 0
    except Exception:
        db.rollback()
        raise
    return kq


def _doc_dong(o: dict, so_dong: int, tra_sale: dict[str, int], du_tu_cach: set[int],
              dung_tai_chinh: bool, loi: list[LoiDong]) -> tuple[dict | None, dict]:
    """Đọc một dòng thành (thông tin tạo khách, chính sách tài chính). Lỗi ⇒ (None, {})."""
    hong = len(loi)

    ten = _chuoi(o.get("name"))
    if not ten:
        loi.append(LoiDong(so_dong, "Tên khách hàng", "Chưa điền tên khách hàng."))

    loai_raw = _chuoi(o.get("customer_kind"))
    loai = KIND_CONG_TY
    if loai_raw:
        loai = NHAN_LOAI.get(_khoa(loai_raw), "")
        if not loai:
            loi.append(LoiDong(so_dong, "Loại khách",
                               f'"{loai_raw}" không hợp lệ — điền "Công ty" hoặc "Cá nhân".'))

    sale_id = None
    sale_raw = _chuoi(o.get("sale_user_id"))
    if sale_raw:
        sale_id = tra_sale.get(_khoa(sale_raw))
        if sale_id is None:
            loi.append(LoiDong(so_dong, "Sale phụ trách",
                               f'Không tìm thấy người nào tên "{sale_raw}".'))
        elif sale_id not in du_tu_cach:
            # CÓ người này, nhưng không thuộc khối Kinh doanh. Nói đúng lý do — cùng luật với ô
            # "NV phụ trách" trên màn, để đi đường Excel không gán được khách cho Thủ kho.
            loi.append(LoiDong(
                so_dong, "Sale phụ trách",
                f'"{sale_raw}" không thuộc khối Kinh doanh nên không nhận khách được. '
                "Bật cờ khối Kinh doanh cho phòng của họ ở Phòng ban, hoặc chọn người khác."))
            sale_id = None

    tai_chinh: dict = {}
    if dung_tai_chinh:
        for khoa, nhan, doc in (
            ("credit_limit", "Hạn mức công nợ", _so_nguyen),
            ("payment_term_days", "Số ngày nợ tối đa", _so_nguyen),
            ("discount_min_pct", "Chiết khấu tối thiểu", _phan_tram),
            ("discount_max_pct", "Chiết khấu tối đa", _phan_tram),
            ("markup_min_pct", "Markup tối thiểu", _phan_tram),
            ("markup_max_pct", "Markup tối đa", _phan_tram),
        ):
            if khoa not in o:
                continue
            gia, hong_o = doc(o.get(khoa), nhan)
            if hong_o:
                loi.append(LoiDong(so_dong, nhan, hong_o))
            else:
                tai_chinh[khoa] = gia
        # Chỉ gọi `update_financial` khi người khai THẬT SỰ điền gì đó — gọi với toàn None là ghi
        # đè "chưa đặt" lên chính sách mặc định, và đẻ một dòng nhật ký cho việc không xảy ra.
        if all(v is None for v in tai_chinh.values()):
            tai_chinh = {}

    if len(loi) > hong:
        return None, {}
    return {
        "name": ten,
        "customer_kind": loai,
        "tax_code": _chuoi(o.get("tax_code")),
        "phone": _chuoi(o.get("phone")),
        "email": _chuoi(o.get("email")),
        "address": _chuoi(o.get("address")),
        "contact_name": _chuoi(o.get("contact_name")),
        "sale_user_id": sale_id,
    }, tai_chinh
