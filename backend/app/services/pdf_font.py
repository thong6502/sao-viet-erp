"""Font Unicode cho MỌI bản in PDF của hệ thống — đăng ký MỘT LẦN cho cả tiến trình.

Font mặc định của ReportLab (Helvetica) là Type 1 chuẩn PDF, bảng mã Latin-1: chữ tiếng Việt có
dấu KHÔNG có glyph. Hai bản in giấy của hệ thống — phiếu công nghệ phát cho tổ sản xuất và bảng
báo giá gửi khách — trước đây đều lách bằng cách bỏ dấu; chủ dự án bác cả hai lần ("không được bỏ
dấu, không ai đọc được đâu"). Bản in là giấy người ta cầm đọc, bỏ dấu là đánh đố người đọc.

Dùng file TĨNH `app/assets/fonts/DejaVuSans{,-Bold}.ttf` nằm sẵn trong repo: không tải từ mạng,
không thêm thư viện — `TTFont` là của chính `reportlab`, gói đã có trong `requirements.txt` từ
trước. Đường dẫn dựng từ `__file__` chứ KHÔNG hardcode ổ đĩa (prod chạy Docker Linux).

Đăng ký một lần cho cả tiến trình (khoá `_da_dang_ky`): `registerFont` gọi lại mỗi lần dựng PDF là
phí, mà trong bộ test hàm này chạy hàng chục lượt. `registerFontFamily` để `<b>…</b>` trong
`Paragraph` nhảy sang bản đậm THẬT thay vì ReportLab giả lập đậm bằng cách kéo dày nét (chữ nhòe).

CHỈ CÓ THƯỜNG VÀ ĐẬM — repo không nhúng bản nghiêng. Chỗ nào trước dùng `Helvetica-Oblique` thì
đổi sang `THUONG`: thà chữ đứng có dấu còn hơn chữ nghiêng mất dấu.

Ngoài tên font, module còn giữ `cat_vua` — phép cắt chữ cho vừa bề rộng. Nó ở đây vì cùng lý do:
muốn đo được bề rộng thì phải biết font đang vẽ, mà font là thứ file này cấp. Hai bản in (báo giá
gửi khách, phiếu công nghệ phát cho tổ) đều cần cắt, và task 13 đã một lần chép hàm tra tên đơn vị
rồi để hai bản lệch nhau (finding Q-03) — không chép lần thứ hai.
"""
from __future__ import annotations

from pathlib import Path

#: `app/assets/fonts/` — file này nằm ở `app/services/`, `parents[1]` là `app/`.
_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"

#: Tên font để truyền cho `setFont` / `ParagraphStyle(fontName=...)`.
THUONG = "DejaVuSans"
DAM = "DejaVuSans-Bold"

_da_dang_ky = False


def dang_ky_font() -> None:
    """Nạp DejaVu Sans (Unicode, phủ đủ dấu tiếng Việt) vào ReportLab. Gọi trước khi dựng PDF."""
    global _da_dang_ky
    if _da_dang_ky:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont(THUONG, str(_FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(DAM, str(_FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(THUONG, normal=THUONG, bold=DAM)
    _da_dang_ky = True


def cat_vua(s: str, rong: float, font: str, co: float) -> str:
    """Cắt `s` cho vừa `rong` (đơn vị point), thêm "…" khi phải cắt.

    Đo bằng `stringWidth` của chính font đang vẽ chứ không đếm ký tự: chữ tiếng Việt có dấu và
    dấu câu rộng hẹp rất khác nhau, đếm ký tự thì tên toàn chữ hoa vẫn tràn. Đây đúng là lỗi mà
    chân trang phiếu công nghệ mắc phải khi cắt cứng 28 ký tự — tên 28 ký tự đè 8,8 mm lên ô
    "Trang N", trong khi cùng con số đó với tên chữ thường lại còn thừa chỗ.

    `rong` nhỏ hơn bề rộng của chính dấu "…" (10 pt ở cỡ 10) thì hàm vẫn trả `"…"` và nó rộng hơn
    `rong` — vòng lặp không thể trả ngắn hơn thế. Chấp nhận: mọi lời gọi thật đều cấp `rong` lớn
    hơn nhiều lần, và trả chuỗi rỗng thì mất luôn tín hiệu "còn chữ bị cắt".

    Gọi `dang_ky_font()` TRƯỚC: `stringWidth` với một font chưa đăng ký sẽ ném `KeyError`.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    if stringWidth(s, font, co) <= rong:
        return s
    while s and stringWidth(s + "…", font, co) > rong:
        s = s[:-1]
    return s + "…"
