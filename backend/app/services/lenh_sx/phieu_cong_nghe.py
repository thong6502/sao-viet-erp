"""Phiếu công nghệ A4 — bản in giấy phát cho TỔ SẢN XUẤT (Task 13).

Khác báo giá đối ngoại: phiếu này đi xuống XƯỞNG chứ không phải cho khách, và nội dung của nó
(routing một lệnh dài) không có TRẦN số dòng — 40 công đoạn là chuyện thường. Vẽ tay bằng
`canvas` như `routers/quotations.py::_render_pdf` thì "tự chia trang không cắt bảng giữa dòng"
phải tự lập trình lại từ đầu; dùng `platypus` (`SimpleDocTemplate` + `Table(repeatRows=1)`) thì
ReportLab tự lo — `Table.split()` chỉ cắt ở RANH GIỚI DÒNG, không bao giờ giữa một dòng.

--- KHÔNG MỘT SỐ TIỀN NÀO -----------------------------------------------------------------------
Ràng buộc toàn cục của plan (giống `services/lenh_sx/ho_so.py`). Phiếu này KHÔNG tự mở một đường
đọc DB thứ hai: nó gọi `ho_so.ho_so()` và xin ĐÚNG bốn khối nó in — `thong_tin` / `thong_so` /
`routing` / `phien_ban` (tham số `chi_khoi`).

ĐỌC KỸ NGUỒN BẢO ĐẢM — bản đầu của đoạn này dẫn SAI. Nó viết "an toàn vì `ho_so.py` khai TỪNG
TRƯỜNG nên không có cột tiền nào để quên in". Nhưng chính `ho_so.py:50-56` nói ngược: *LƯỚI THẬT
LÀ SCHEMA, KHÔNG PHẢI FILE NÀY* — `response_model` lặng lẽ vứt mọi khoá không khai ở `ThongSoOut`,
và vì tin lưới ấy nên `ho_so.py` CỐ Ý cấp phép cho người sau đổ nguyên `quy_cach_json` (có
`phi_giao_hang`) vào `_thong_so`. Đường PDF gọi THẲNG service, không đi qua `response_model`, nên
lưới đó KHÔNG có ở đây.

Hôm nay phiếu vẫn sạch, nhưng vì một lý do KHÁC: nó TỰ GỌI TÊN từng khoá nó in (`thong_so_rows`,
`routing_rows` bên dưới), không đổ dict nào ra giấy. Lưới thay cho schema là bài
`test_khong_mot_so_tien_nao_len_giay` — bài đó bắt CHUỖI THẬT lúc nó được vẽ. Thêm một ô vào phiếu
thì đó là chỗ bắt được tiền lọt lên giấy; đừng xoá nó.

Đây cũng là lý do route mới đi ĐÚNG một cửa quyền với `GET /api/lenh-san-xuat/{id}`:
`ho_so.ho_so()` tự ném 404 (lệnh không tồn tại / chưa phát hành) hoặc 403 (lệnh có thật nhưng
ngoài phạm vi người gọi) qua `pham_vi.chan_ngoai_pham_vi` — phiếu không viết lại phép kiểm đó
lần hai (và `chi_khoi` KHÔNG đụng tới cửa ấy: nó chạy trước, luôn luôn), còn tải PDF không đụng
cột `phien_ban` (đọc, không ghi) nên không làm nó tăng lên.

--- FONT: DejaVu Sans, CÓ DẤU ĐẦY ĐỦ ------------------------------------------------------------
v1 của task này từng bỏ dấu tiếng Việt (font Helvetica/Vera đi kèm ReportLab 4.4.5 thiếu ký tự có
dấu, và lúc đó repo chưa có font nào khác) — chủ dự án bác quyết định đó: phiếu công nghệ PHẢI có
dấu đầy đủ, vì đây là giấy tổ trưởng cầm đọc tên công đoạn/quy cách, bỏ dấu là đánh đố người đọc.
Phần nạp font nằm ở `services/pdf_font.py` — DÙNG CHUNG với bản in báo giá (`routers/quotations.py`),
vì cả hai đều bị bác cùng một lý do; chép hai bản đăng ký là hai chỗ phải sửa khi đổi font.

`pdf_font.cat_vua` (cắt chữ theo `stringWidth`) cũng ở đó và cũng dùng chung — nó vốn là hàm
riêng của `quotations.py`, dời sang khi chân trang phiếu này cần cắt tên người in. Không chép:
task này đã một lần chép hàm tra tên đơn vị rồi để hai bản lệch nhau (Q-03).

--- ĐƠN VỊ: IN TÊN, KHÔNG IN MÃ -----------------------------------------------------------------
Cột `don_vi_vao`/`don_vi_ra` của `lsx_cong_doan` (và `don_vi_tinh` của `lsx`) giữ MÃ danh mục
(`to`, `kem`, `cai`, `ram`…) — xem `models/don_vi_do.py:127-128`: "Mã dùng trong công thức / API
… CHỮ HIỂN THỊ nằm ở `ten`." In thẳng mã lên phiếu giấy là đưa tổ trưởng đọc "480 to" thay vì
"480 tờ".

Dùng ĐÚNG hai hàm mà file anh em `ho_so.py` đang dùng cho nhật ký (`:710`, `:761`, `:794`, `:803`):
`DonViDoRepository.ten_theo_ma()` nạp bảng tra MỘT lần cho cả phiếu, `nhan_don_vi(bang, ma)` tra
tên — mã lạ trả CHÍNH MÃ ĐÓ, không bịa không nuốt. Bản trước của file này chép lại cả hai thành
`_bang_ten_don_vi`/`_nhan_dv`, và hai bản ĐÃ LỆCH: mã rỗng ra `""` ở bản gốc nhưng `"—"` ở bản
chép, tức cùng một lệnh mà nhật ký hiện một kiểu còn phiếu in một kiểu. Gạch ngang cho ô trống là
việc của chỗ HIỂN THỊ (`gia_tri()` bên dưới), không phải của hàm tra tên.

--- KHOÁ MÁY: DỊCH SANG TIẾNG VIỆT TRƯỚC KHI IN -------------------------------------------------
Ba cột của phiếu mang khoá máy đọc: `quy_cach_in` (`mot_mat`…), `nhom` (`print`…), `loai_buoc`
(`may`…). Cùng một loại lỗi với "480 to", trên cùng tờ giấy.

ĐÃ KIỂM từng nhóm là ENUM KHAI CỨNG TRONG CODE chứ không phải dòng danh mục — `models/lsx.py:67-70`
(`LB_MAY`/`LB_TO`/`LB_THUE_NGOAI` + `LOAI_BUOC`), `models/cong_doan.py:25` (`NHOM`),
`models/phieu_tinh_gia.py:124` (cột `quy_cach_in`, chú thích `mot_mat|hai_mat(AB)|tu_tro|tro_nhip`;
`thanh_phan_engine.py:139` và `_may_fit.py:53` so thẳng bằng chuỗi). Luật "danh mục là ĐỘNG, cấm
hardcode tên" áp cho DÒNG DANH MỤC — enum trong code thì bảng nhãn khai cạnh nơi in là đúng chỗ.

Nhãn chép đúng chữ MÀN HÌNH đang hiện cho cùng dữ liệu (`LenhSxHoSoView.CACH_IN`,
`keHoachSxShared.NHOM_CONG_DOAN`, `client.LSX_LOAI_BUOC_META`), để giấy và màn không nói hai kiểu.
KHÔNG import từ `quotation_service._QUY_CACH_IN_NHAN`: bảng đó viết cho câu văn giữa dòng của báo
giá gửi khách ("In 4 màu trở nhíp" — chữ thường, không có "(AB)"), khác chữ trên màn hồ sơ, mà
import còn kéo cả chuỗi module báo giá vào đường in của xưởng.

Khoá lạ (ảnh chụp lệnh cũ, hoặc enum thêm giá trị mới mà quên chỗ này) ⇒ IN NGUYÊN KHOÁ — cùng
luật `nhan_don_vi`: thà tổ thấy một chữ khó đọc còn hơn ô trống hoặc một cái tên hệ tự bịa.

--- QR --------------------------------------------------------------------------------------
Nội dung QR: `{base}/#lsx=<lsx_id>&pv=<phien_ban>` — HASH FRAGMENT, không phải query string, vì FE
là SPA điều hướng bằng state/hash (`AppShell.navigate`), không có route thật đọc `?ho-so=...`.
`pv` là chính con số `phien_ban` đang in ở đầu mỗi trang: cho phép một màn hồ sơ tương lai so `pv`
trên QR với `phien_ban` hiện tại của lệnh rồi cảnh báo "phiếu giấy này là bản cũ". MỘT QR cho cả
lệnh — không QR riêng từng công đoạn. KHÔNG nhúng token đăng nhập: trang đích vẫn đòi đăng nhập,
và một QR in trên giấy lưu hành khắp xưởng không được mang credential nào.

Đi cùng `pv` là MỐC IN + NGƯỜI IN ở chân trang: `pv` chỉ so được nếu người cầm tờ giấy biết nó in
lúc nào. Xem chỗ dựng `chan_trang` trong `render_pdf`.

`{base}` = `settings.frontend_origin` (thêm ở `config.py`, Task 13): mặc định lấy origin ĐẦU của
`CORS_ORIGINS` — chỗ đã khai "frontend nằm ở đâu" cho từng môi trường, nên deploy không phải khai
thêm biến mới. Rỗng (không có origin nào cấu hình) thì QR mang đường dẫn TƯƠNG ĐỐI
`/#lsx=...&pv=...` — không ném lỗi, không bỏ QR.

BẪY của fallback đó: ai thêm một origin nội bộ lên ĐẦU `CORS_ORIGINS` là QR im lặng trỏ sai host,
không lỗi không cảnh báo. Vì thế `FRONTEND_BASE_URL` đã được ghi vào `.env.example` +
`backend/.env.example` kèm đúng cảnh báo này — nhưng KHÔNG vào danh sách `REQUIRED` của
`.github/workflows/deploy.yml`: fallback là chủ ý, biến này không bắt buộc.
"""
from __future__ import annotations

import io
import re
from typing import NamedTuple
from xml.sax.saxutils import escape as _xml_escape

from sqlalchemy.orm import Session

from ...config import settings
from ...repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi
from ..gio_xuong import gio_xuong
from ..pdf_font import DAM, THUONG, cat_vua, dang_ky_font as _dang_ky_font
from . import ho_so

# Khổ A4 dùng lề 15mm hai bên ⇒ khung nội dung rộng 180mm. Mọi bảng bên dưới cộng KHÔNG vượt số
# đó — cộng vừa khít độ rộng khung là rủi ro tràn 1-2px khi ReportLab làm tròn, nên chừa dư.
_LE_MM = 15.0

#: Cỡ chữ chân trang. Khai thành hằng vì phép CẮT chân trang phải đo bằng đúng cỡ đang vẽ — đổi
#: một chỗ mà quên chỗ kia là chuỗi cắt theo cỡ này rồi vẽ bằng cỡ khác, tức lại đè "Trang N".
_CO_CHAN_TRANG = 8

#: Bốn khối phiếu thật sự in ra giấy. Truyền vào `ho_so.ho_so(chi_khoi=...)` để nút In không kéo
#: theo engine cân đối vật tư + giao hàng + KCS + timeline — xem docstring `ho_so.ho_so`.
_KHOI_CAN = {"thong_tin", "thong_so", "routing", "phien_ban"}

# --- Bảng nhãn cho KHOÁ MÁY (xem docstring module: cả ba đều là enum cứng trong code) ------------
#: `phieu_tinh_gia.quy_cach_in` — chữ y hệt màn hồ sơ (`LenhSxHoSoView.CACH_IN`).
_NHAN_QUY_CACH_IN = {
    "mot_mat": "1 mặt",
    "hai_mat": "2 mặt (AB)",
    "tu_tro": "Tự trở",
    "tro_nhip": "Trở nhíp",
}
#: `cong_doan.NHOM` — chữ y hệt ô lọc Nhóm công đoạn (`keHoachSxShared.NHOM_CONG_DOAN`).
_NHAN_NHOM = {
    "prepress": "Chế bản",
    "print": "In",
    "finishing": "Gia công sau in",
    "other": "Dịch vụ khác",
}
#: `lsx.LOAI_BUOC` — chữ y hệt chip loại bước trên màn hồ sơ (`client.LSX_LOAI_BUOC_META`).
_NHAN_LOAI_BUOC = {
    "may": "Máy",
    "to": "Tổ",
    "thue_ngoai": "Thuê ngoài",
}


class PhieuPdf(NamedTuple):
    """Bytes PDF + TÊN FILE gợi ý cho `Content-Disposition`.

    Tên file đi kèm nội dung chứ không để router tự dựng: chỉ service mới có `lsx.ma` trong tay
    (nó vừa đọc qua cửa phạm vi), router đọc lại là mở một đường đọc DB thứ hai — không đi qua
    cửa ấy — cho đúng một chuỗi.
    """

    ten_file: str
    noi_dung: bytes


def _ten_file(ma: str) -> str:
    """`LSX26-0001` -> `phieu-cong-nghe-LSX26-0001.pdf`.

    Lọc ký tự về `[A-Za-z0-9._-]`: `Content-Disposition` là header HTTP, một dấu `"` hay xuống
    dòng lọt vào `filename="..."` là header vỡ (và về nguyên tắc là chỗ tiêm header). Mã lệnh do
    `SequenceService` sinh nên hôm nay vốn đã sạch — bộ lọc này để nó vẫn sạch khi có người đổi
    khuôn mã.
    """
    an_toan = re.sub(r"[^A-Za-z0-9._-]+", "-", ma).strip("-") or "lenh"
    return f"phieu-cong-nghe-{an_toan}.pdf"


def _nhan_khoa(bang: dict[str, str], khoa: str | None) -> str:
    """Khoá enum → chữ tiếng Việt. Khoá rỗng ⇒ `""` (chỗ hiển thị lo gạch ngang), khoá lạ ⇒ CHÍNH
    KHOÁ ĐÓ.

    Luật "khoá lạ ⇒ in nguyên khoá, không bịa không nuốt" là chung với
    `don_vi_do_repo.nhan_don_vi`. Chỗ CỐ Ý khác: hàm kia tra `bang.get(k.lower(), k)`, hàm này
    tra `bang.get(k, k)` — **không hạ chữ thường**. Chú thích cũ ở đây khai "cùng luật" trống
    không nên đọc thành "giống hệt"; viết lại cho đúng thứ code thật sự làm.

    Vì sao không thêm `.lower()`: mã đơn vị tới từ DANH MỤC người dùng gõ (`don_vi_do.ma`) nên
    chuẩn hoá là đúng; còn ba nhóm khoá ở đây là ENUM do code viết ra và phần còn lại của hệ so
    chúng BẰNG CHUỖI Y NGUYÊN — `thanh_phan_engine.py:137,139` (`== "mot_mat"`,
    `in ("tu_tro","tro_nhip")`), `_may_fit.py:53`, `lsx_service.py:2603,2696`,
    `bien_cong_thuc.py:306`, và `quotation_service.py:99` cũng tra không hạ chữ. Hạ chữ RIÊNG ở
    đây thì một giá trị `"Mot_Mat"` sẽ ra giấy là "1 mặt" trong khi engine coi nó là khoá lạ và
    tính 1 mặt/2 mặt theo nhánh khác — tờ giấy nói một đằng, hệ tính một nẻo, mà không ai thấy.
    In nguyên `Mot_Mat` lên giấy thì người đọc biết ngay có gì đó sai.
    """
    k = (khoa or "").strip()
    return bang.get(k, k)


def noi_dung_qr(lsx_id: int, phien_ban: int | None) -> str:
    """URL để tổ trưởng quét QR mở đúng hồ sơ lệnh — xem docstring module về hình dạng chuỗi.

    `phien_ban=None` (lệnh chưa từng có gói phát hành — không nên xảy ra với một lệnh đã qua cửa
    `chan_ngoai_pham_vi`, nhưng hàm này không có quyền giả định) ⇒ `pv=` rỗng, vẫn là một URL hợp
    lệ chứ không ném lỗi.
    """
    base = settings.frontend_origin
    pv = "" if phien_ban is None else str(phien_ban)
    return f"{base}/#lsx={lsx_id}&pv={pv}"


def _qr_drawing(value: str, size_mm: float = 20.0):
    """Widget QR của chính ReportLab (`graphics.barcode.qr`) — KHÔNG dùng gói `qrcode`/`Pillow`
    ngoài, chưa từng có trong `requirements.txt` và task này không được thêm thư viện mới."""
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.units import mm

    widget = qr.QrCodeWidget(value)
    x0, y0, x1, y1 = widget.getBounds()
    w, h = (x1 - x0) or 1, (y1 - y0) or 1
    size = size_mm * mm
    d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    d.add(widget)
    return d


def _ngay(v) -> str:
    return v.isoformat() if v else "—"


def _so(v) -> str:
    """`137.0` -> `"137"`, `137.5` -> `"137.5"` — cùng khuôn `_f(x):g` của `ho_so.py`."""
    if v is None:
        return "—"
    return f"{float(v):g}"


def render_pdf(
    db: Session, lsx_id: int, *, sale_ids: set[int] | None, nguoi_in: str | None = None
) -> PhieuPdf:
    """Dựng phiếu công nghệ A4 cho MỘT lệnh đã phát hành. Trả `PhieuPdf(ten_file, noi_dung)`.

    Ném `HTTPException` 404/403 giống hệt `GET /api/lenh-san-xuat/{id}` (xem docstring module) —
    router chỉ gọi hàm này, không tự kiểm quyền lần hai.

    `nguoi_in` = tên người đang đăng nhập, in ở chân trang cạnh mốc giờ in. Router có sẵn `user`
    nên truyền xuống; `None` thì chân trang chỉ có mốc giờ (service không tự đọc user — tầng
    service không được biết chuyện đăng nhập).
    """
    _dang_ky_font()

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.graphics import renderPDF
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ho_so_dict = ho_so.ho_so(db, lsx_id, sale_ids=sale_ids, chi_khoi=_KHOI_CAN)
    tt = ho_so_dict["thong_tin"]
    ts = ho_so_dict["thong_so"]
    nodes = ho_so_dict["routing"]["nodes"]
    phien_ban = ho_so_dict["phien_ban"]
    bang_dv = DonViDoRepository(db).ten_theo_ma()

    nhan_style = ParagraphStyle("plc_nhan", fontName=DAM, fontSize=9, leading=12)
    gia_tri_style = ParagraphStyle("plc_gia_tri", fontName=THUONG, fontSize=9, leading=12)
    khoi_style = ParagraphStyle("plc_khoi", fontName=DAM, fontSize=12, leading=15)
    tieu_de_style = ParagraphStyle("plc_tieu_de", fontName=DAM, fontSize=16, leading=20)

    def nhan(s) -> Paragraph:
        return Paragraph(_xml_escape(str(s)), nhan_style)

    def gia_tri(s) -> Paragraph:
        txt = str(s) if s not in (None, "") else "—"
        return Paragraph(_xml_escape(txt), gia_tri_style)

    khoi_table_style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])

    # --- Khối "Thông tin lệnh" --------------------------------------------------------------
    so_luong = f"{tt.get('so_luong_dat') or 0:,}".replace(",", ".")
    dvt_luong = nhan_don_vi(bang_dv, tt.get("don_vi_tinh"))
    if dvt_luong:
        so_luong = f"{so_luong} {dvt_luong}"
    thong_tin_rows = [
        [nhan("Mã LSX"), gia_tri(tt.get("ma"))],
        [nhan("Tên sản phẩm"), gia_tri(tt.get("ten"))],
        [nhan("Khách hàng"), gia_tri(tt.get("khach_hang"))],
        [nhan("Số lượng đặt"), gia_tri(so_luong)],
        [nhan("Hạn hoàn thành SX"), gia_tri(_ngay(tt.get("han_hoan_thanh_sx")))],
        [nhan("Ưu tiên gấp"), gia_tri("Có" if tt.get("is_rush") else "Không")],
        [nhan("Ghi chú"), gia_tri(tt.get("ghi_chu"))],
    ]
    thong_tin_table = Table(thong_tin_rows, colWidths=[40 * mm, 130 * mm])
    thong_tin_table.setStyle(khoi_table_style)

    # --- Khối "Thông số kỹ thuật" (KHAI TỪNG TRƯỜNG như `ho_so._thong_so` — không đổ dict) ----
    def kho(dai, rong) -> str:
        """`790 × 1090 mm`. Đi qua `_so()` để `790.0` không lên giấy thành `790.0`, và ĐƠN VỊ là
        bắt buộc: màn hồ sơ (`LenhSxHoSoView.khoMm`) cảnh báo thẳng rằng bỏ `mm` là ra "một tờ
        giấy nguyên 860 × 650 cm — to bằng gian phòng". Khổ nhập bằng mm ở cả phiếu tính giá lẫn
        màn Kế hoạch SX, hồ sơ chỉ chép lại ảnh chụp đó."""
        if dai is None and rong is None:
            return "—"
        d = _so(dai) if dai is not None else "?"
        r = _so(rong) if rong is not None else "?"
        return f"{d} × {r} mm"

    thong_so_rows = [
        [nhan("Giấy"), gia_tri(ts.get("giay_ten"))],
        [nhan("Định lượng"), gia_tri(_so(ts.get("dinh_luong")))],
        [nhan("Khổ nguyên (dài x rộng)"), gia_tri(kho(ts.get("kho_nguyen_dai"), ts.get("kho_nguyen_rong")))],
        [nhan("Khổ in (dài x rộng)"), gia_tri(kho(ts.get("kho_in_dai"), ts.get("kho_in_rong")))],
        [nhan("Khổ thành phẩm (dài x rộng)"),
         gia_tri(kho(ts.get("dai_thanh_pham"), ts.get("rong_thanh_pham")))],
        [nhan("Quy cách in"), gia_tri(_nhan_khoa(_NHAN_QUY_CACH_IN, ts.get("quy_cach_in")))],
        [nhan("Số màu (mặt A / mặt B)"),
         gia_tri(f"{_so(ts.get('so_mau_a'))} / {_so(ts.get('so_mau_b'))}")],
        [nhan("Mực mặt A"), gia_tri(", ".join(ts.get("muc_a") or []))],
        [nhan("Mực mặt B"), gia_tri(", ".join(ts.get("muc_b") or []))],
        [nhan("Số trang / số trang mỗi tay"),
         gia_tri(f"{_so(ts.get('so_trang'))} / {_so(ts.get('trang_moi_tay'))}")],
        # "kẽm" (bản in offset), KHÔNG phải "kèm" — cả hệ gọi nó là "Số kẽm"
        # (`LenhSxHoSoView.tsx:801`, `BaiGhep2Page.tsx:872`, `LsxDetailView.tsx:1352`), và bảng
        # routing ngay bên dưới in đơn vị "bản kẽm". Sai một dấu là tờ giấy nói khác cả hệ.
        [nhan("Số kẽm"), gia_tri(_so(ts.get("so_kem")))],
        [nhan("Số mảnh xả"), gia_tri(_so(ts.get("so_manh_xa")))],
        [nhan("Loại sản phẩm"), gia_tri(ts.get("loai_san_pham"))],
        [nhan("Ghi chú kỹ thuật"), gia_tri(ts.get("ghi_chu_ky_thuat"))],
    ]
    thong_so_table = Table(thong_so_rows, colWidths=[40 * mm, 130 * mm])
    thong_so_table.setStyle(khoi_table_style)

    # --- Khối "Routing công đoạn" — bảng DÀI, chỗ cần tự chia trang -------------------------
    routing_style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])
    # Cột LỚP, không phải chỉ một cột STT chạy 1→N. `ho_so._lop_topo` sinh `lop` = đường DÀI NHẤT
    # từ một bước không tiền nhiệm tới nó, và `ho_so.py:209-219` nói rõ vì sao: bìa và ruột chạy
    # SONG SONG nhưng `thu_tu` của chúng vẫn là 1 và 2. Một tờ giấy đánh số 1→40 nói với tổ trưởng
    # rằng bước 12 xong mới tới bước 13 — sai với routing có nhánh. Hai bước CÙNG lớp = làm được
    # song song; lớp lớn hơn = phải đợi.
    #
    # Vẫn giữ STT vì đó là cách người ta gọi nhau qua tờ giấy ("dòng 12"), chỉ thôi để nó một mình
    # gánh nghĩa thứ tự thi công.
    routing_rows = [[
        nhan("STT"), nhan("Lớp"), nhan("Công đoạn"), nhan("Nhóm"), nhan("Loại bước"),
        nhan("SL vào"), nhan("SL ra"), nhan("ĐVT"), nhan("Tổ"), nhan("Bắt buộc"),
    ]]
    for i, node in enumerate(nodes, start=1):
        ma_dv = node.get("don_vi_ra") or node.get("don_vi_vao")
        # Nhà gia công đi CHUNG ô "Loại bước" chứ không thành cột riêng: chỉ bước `thue_ngoai` mới
        # có, thêm hẳn một cột là để trống ở gần hết số dòng và ăn mất bề ngang của cột Công đoạn.
        # Bước thuê ngoài mà không ghi tên nhà gia công thì tổ không biết giao hàng cho ai.
        loai_buoc = _nhan_khoa(_NHAN_LOAI_BUOC, node.get("loai_buoc"))
        ncc = (node.get("nha_cung_cap") or "").strip()
        if ncc:
            loai_buoc = f"{loai_buoc}: {ncc}" if loai_buoc else ncc
        routing_rows.append([
            gia_tri(i),
            gia_tri(node.get("lop")),
            gia_tri(node.get("ten")),
            gia_tri(_nhan_khoa(_NHAN_NHOM, node.get("nhom"))),
            gia_tri(loai_buoc),
            gia_tri(_so(node.get("so_luong_vao"))),
            gia_tri(_so(node.get("so_luong_ra"))),
            gia_tri(nhan_don_vi(bang_dv, ma_dv)),
            gia_tri(node.get("to")),
            gia_tri("Có" if node.get("bat_buoc") else "Không"),
        ])
    # Cộng đúng 176mm, khung nội dung rộng 180mm (xem `_LE_MM`). Chỗ nhường cho cột Lớp lấy từ
    # Công đoạn (38→34) và Bắt buộc (18→14) — hai cột dư nhất: tên công đoạn tự xuống dòng trong
    # `Paragraph`, còn ô Bắt buộc chỉ chứa "Có"/"Không".
    routing_table = Table(
        routing_rows,
        colWidths=[
            9 * mm, 10 * mm, 34 * mm, 19 * mm, 26 * mm,
            14 * mm, 14 * mm, 12 * mm, 24 * mm, 14 * mm,
        ],
        repeatRows=1,
    )
    routing_table.setStyle(routing_style)

    story = [
        Paragraph("PHIẾU CÔNG NGHỆ", tieu_de_style),
        Spacer(1, 4 * mm),
        Paragraph("Thông tin lệnh", khoi_style),
        Spacer(1, 2 * mm),
        thong_tin_table,
        Spacer(1, 6 * mm),
        Paragraph("Thông số kỹ thuật", khoi_style),
        Spacer(1, 2 * mm),
        thong_so_table,
        Spacer(1, 6 * mm),
        Paragraph(_xml_escape(f"Routing công đoạn ({len(nodes)} bước)"), khoi_style),
        Spacer(1, 2 * mm),
        routing_table,
    ]

    ma = tt.get("ma") or f"LSX-{lsx_id}"
    phien_ban_text = str(phien_ban) if phien_ban is not None else "—"
    qr_drawing = _qr_drawing(noi_dung_qr(lsx_id, phien_ban))

    # MỐC IN + NGƯỜI IN ở chân trang. `pv` trong QR có mặt để một màn hồ sơ sau này so được "tờ
    # giấy này là bản cũ" — nhưng một tờ giấy đi khắp xưởng mà không ghi in LÚC NÀO thì người đang
    # cầm nó không tự đối chiếu được, phải đi hỏi. Tên người in để còn biết hỏi ai khi tờ giấy và
    # màn hình nói khác nhau.
    #
    # Lấy `gio_xuong()` — đồng hồ XƯỞNG (giờ tường máy chủ), cùng quy ước với mọi mốc mà tổ đọc
    # trên màn. Dùng `datetime.now(timezone.utc)` là in ra một giờ lệch 7 tiếng so với đồng hồ treo
    # tường của xưởng. Tính MỘT lần ngoài `_dau_trang`: mọi trang của cùng một tờ phiếu phải mang
    # cùng một mốc, không phải mốc lúc ReportLab vẽ tới trang ấy.
    chan_trang = f"In lúc {gio_xuong().strftime('%d/%m/%Y %H:%M')}"
    if (nguoi_in or "").strip():
        chan_trang += f" · Người in: {nguoi_in.strip()}"

    # CẮT THEO BỀ RỘNG THẬT, không theo số ký tự. Bản trước cắt cứng 28 ký tự và ĐÈ lên ô
    # "Trang N": đo bằng `stringWidth` của chính font đang vẽ thì một tên 28 ký tự chạy tới
    # 108,4 mm trong khi "Trang 1" bắt đầu ở 99,6 mm — đè 8,8 mm. Mà 28 cũng không phải mức an
    # toàn nào cả: tên đầy đủ tiếng Việt 22 ký tự ("Nguyễn Thị Thanh Hương") đã sát mép, còn
    # cùng 28 ký tự toàn chữ "l" thì vẫn thừa chỗ. Đếm ký tự không nói được gì về bề rộng.
    #
    # Cắt CẢ chuỗi chứ không riêng phần tên: một luật, và vì `cat_vua` cắt từ ĐUÔI nên thứ mất
    # trước là tên người in, mốc giờ ở đầu chuỗi sống lâu nhất — đúng thứ tự ưu tiên (không biết
    # in cho ai thì còn đoán được, không biết in lúc nào thì `pv` trên QR hết đối chiếu được).
    # Dấu "…" báo cho người cầm giấy biết có chữ đã bị cắt.
    #
    # Chừa chỗ cho ô "Trang N" canh giữa trang: lấy bề rộng của `Trang 999` (dài hơn mọi số
    # trang thật) rồi trừ nửa sang trái, cộng 3 mm khe.
    from reportlab.pdfbase.pdfmetrics import stringWidth

    rong_chan_trang = (
        A4[0] / 2 - stringWidth("Trang 999", THUONG, _CO_CHAN_TRANG) / 2 - _LE_MM * mm - 3 * mm
    )
    chan_trang = cat_vua(chan_trang, rong_chan_trang, THUONG, _CO_CHAN_TRANG)

    # `onFirstPage`/`onLaterPages` CÙNG một hàm ⇒ mã LSX + phiên bản + QR lặp lại trên MỌI trang
    # (luật 3), vẽ thẳng lên canvas nên KHÔNG choán chỗ của luồng nội dung (`story`) đang tự chia
    # trang bên dưới nó. Bài canh: `test_moi_trang_deu_co_ma_va_phien_ban` (bỏ `onLaterPages` là
    # bài đó đỏ).
    def _dau_trang(canvas_obj, _doc) -> None:
        canvas_obj.saveState()
        canvas_obj.setFont(DAM, 11)
        canvas_obj.drawString(_LE_MM * mm, A4[1] - 15 * mm, f"Mã LSX: {ma}")
        canvas_obj.setFont(THUONG, 10)
        canvas_obj.drawString(
            _LE_MM * mm, A4[1] - 21 * mm, f"Phiên bản phát hành: {phien_ban_text}"
        )
        renderPDF.draw(
            qr_drawing, canvas_obj, A4[0] - _LE_MM * mm - 20 * mm, A4[1] - 32 * mm
        )
        canvas_obj.setFont(THUONG, _CO_CHAN_TRANG)
        canvas_obj.drawString(_LE_MM * mm, 10 * mm, chan_trang)
        canvas_obj.drawCentredString(
            A4[0] / 2, 10 * mm, f"Trang {canvas_obj.getPageNumber()}"
        )
        canvas_obj.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_LE_MM * mm,
        rightMargin=_LE_MM * mm,
        topMargin=36 * mm,
        bottomMargin=16 * mm,
        title=f"Phiếu công nghệ {ma}",
    )
    doc.build(story, onFirstPage=_dau_trang, onLaterPages=_dau_trang)
    return PhieuPdf(ten_file=_ten_file(ma), noi_dung=buf.getvalue())
