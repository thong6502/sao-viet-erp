"""Nội quy công ty — luật nghiệp vụ (chủ 30/07/2026).

Giữ đúng hai luật, và cả hai đều là thứ hỏng thì đau:

1. **Nháp KHÔNG lọt ra ngoài.** Nhân viên chỉ đọc bản đã ban hành. Cho sửa thẳng vào bản đang
   hiệu lực là cả công ty đọc được nội quy viết dở.
2. **Ban hành là APPEND, không ghi đè.** Bản cũ lùi thành lịch sử chứ không mất — nội quy là căn
   cứ kỷ luật, phải trả lời được "hồi tháng 5 luật là gì".
"""
from __future__ import annotations

from io import BytesIO
import re

import nh3

from ..models.noi_quy import (
    NQ_PUBLISHED,
    NQ_SOURCE_KINDS,
    NQ_SRC_FILE,
    NQ_SRC_HTML,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.noi_quy_repo import NoiQuyRepository


class NoiQuyError(Exception):
    """Base cho lỗi miền nội quy."""


class NoiQuyValidationError(NoiQuyError):
    """Sai dữ liệu / thao tác không hợp lệ."""


class NoiQuyNotFound(NoiQuyError):
    """Không tìm thấy bản nội quy hoặc file đính kèm."""


class NoiQuyInfrastructureError(NoiQuyError):
    """Server thiếu/hỏng hạ tầng (thư viện chưa cài, kho file chết…) — KHÔNG phải lỗi dữ liệu.

    Tách riêng khỏi `NoiQuyValidationError` là có lý do rất cụ thể: gộp vào đó thì người dùng tải
    một file hoàn toàn lành lên và được báo **"file của bạn hỏng"**. Họ sẽ đi xuất lại file, đổi
    máy, nhờ người khác kiểm tra — mất cả buổi cho một lỗi cài đặt phía server. Lỗi hạ tầng phải
    nói là lỗi hạ tầng."""


# --- Lọc HTML nội quy -------------------------------------------------------
# Nội quy do MỘT người (Giám đốc) ghi nhưng MỌI nhân viên render ⇒ một lần ghi độc là cả công ty
# chạy. Lọc ở ĐÂY (server) mới là chốt thật; DOMPurify phía trình duyệt chỉ là lớp hai — ai gọi
# thẳng API là đi vòng qua nó.
#
# Allowlist bám đúng thứ một bản nội quy cần: tiêu đề, đoạn, in đậm/nghiêng, danh sách, BẢNG
# ("hành vi vi phạm → hình thức xử lý" gần như nội quy nào cũng có), trích dẫn, ảnh.
_HTML_TAGS = {
    "h1", "h2", "h3", "h4", "p", "br", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "hr", "a", "img",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    # `span`/`div` để đường "chuyển đổi trung thực từ Word" giữ được cụm chữ đổi cỡ/đổi màu giữa
    # câu và các khối canh lề. Không có chúng thì mọi định dạng trong dòng bị dồn thành chữ trơn.
    "span", "div",
}
# Cho `style` — nhưng CHỈ với tập thuộc tính ở `_CSS_CHO_PHEP`, lọc trong `_loc_css`.
_STYLE_TAGS = {"p", "div", "span", "td", "th", "table", "tr",
               "h1", "h2", "h3", "h4", "li", "ul", "ol", "blockquote"}
_HTML_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan", "style"},
    "th": {"colspan", "rowspan", "style"},
    **{t: {"style"} for t in _STYLE_TAGS - {"td", "th"}},
}

# Chỉ những thuộc tính CSS thật sự cần để giữ DÁNG một văn bản: canh lề, cỡ/kiểu/màu chữ, thụt lề,
# bề rộng cột. Cố ý KHÔNG có `position`, `z-index`, `background-image`, `content`, `transform`.
_CSS_CHO_PHEP = {
    "text-align", "text-indent", "text-decoration", "text-transform",
    "font-weight", "font-style", "font-size", "font-family",
    "color", "background-color", "width", "margin-left", "padding-left",
    "vertical-align", "line-height",
}
# Chuỗi độc trong giá trị CSS, chặn theo TỪNG khai báo:
#   `url(...)`      — kéo tài nguyên từ máy chủ lạ ⇒ mỗi nhân viên mở nội quy là bên đó biết,
#                     vô tình điểm danh cả công ty cho người ngoài (cùng lý do siết `<img src>`).
#   `expression()`  — chạy được script trên IE cũ.
#   `@import`       — nạp cả một bảng CSS ngoài.
#   `\` và `/*`     — thoát/ẩn ký tự để đi vòng qua chính bộ lọc này.
_CSS_CHAN = ("url(", "expression", "@import", "javascript:", "\\", "/*", "*/")


def _loc_css(value: str) -> str | None:
    """Giữ lại CHỈ các khai báo CSS trong allowlist; trả `None` nếu không còn gì.

    Phải tự làm vì **nh3 không có bộ lọc CSS** — khai `style` vào `attributes` là cho qua NGUYÊN
    chuỗi. Lọc theo TỪNG khai báo (không phải cả chuỗi) để một khai báo xấu không kéo theo cả
    những khai báo lành: mất `text-align: center` là bản nội quy lệch hết tiêu đề."""
    giu: list[str] = []
    for khai_bao in value.split(";"):
        ten, dau, gia_tri = khai_bao.partition(":")
        if not dau:
            continue
        ten = ten.strip().lower()
        gia_tri = " ".join(gia_tri.split())
        if ten not in _CSS_CHO_PHEP or not gia_tri:
            continue
        if any(x in gia_tri.lower() for x in _CSS_CHAN):
            continue
        giu.append(f"{ten}: {gia_tri}")
    return "; ".join(giu) or None
# Cho phép link ra ngoài (nội quy hay dẫn văn bản luật), nhưng ẢNH thì siết riêng ở
# `_loc_thuoc_tinh` bên dưới.
_URL_SCHEMES = {"http", "https", "mailto"}

# Ảnh CHỈ được trỏ vào kho file của chính hệ thống. Cho ảnh ngoài thì mỗi lần một nhân viên mở
# nội quy là máy chủ bên thứ ba biết — thành ra vô tình điểm danh cả công ty cho người lạ; chưa
# kể trang kia chết là nội quy vỡ hình.
_IMG_PREFIX = "/api/files/"


def _loc_thuoc_tinh(tag: str, attr: str, value: str) -> str | None:
    """Trả `None` để BỎ thuộc tính. Chạy sau allowlist của nh3."""
    if tag == "img" and attr == "src" and not value.startswith(_IMG_PREFIX):
        return None
    if attr == "style":
        return _loc_css(value)
    return value


# Word soạn được tới `Heading 6` nhưng allowlist chỉ tới `h4`. Nếu để nh3 xử lý thì nó BỎ THẺ và
# giữ chữ trơn ⇒ tiêu đề tụt thành văn bản thường, âm thầm. Hạ thành `h4` thì mất độ sâu nhưng còn
# giữ vai trò tiêu đề. FE cũng hạ (`capHeadings`), nhưng chốt phải nằm ở đây: ai gọi thẳng API là
# đi vòng qua FE.
_HA_CAP_TIEU_DE = re.compile(r"<(/?)h[56](\s[^>]*)?>", re.IGNORECASE)


def lam_sach_html(html: str | None) -> str:
    """Lọc HTML nội quy theo allowlist. Thẻ/thuộc tính lạ bị bỏ, CHỮ giữ nguyên.

    `nh3` (Rust ammonia) tự bỏ `<script>`, mọi `on*=`, và `href="javascript:"` — không tự chế
    regex lọc HTML, đó là bài toán không bao giờ tự viết đúng."""
    if not html:
        return ""
    # Đổi TÊN THẺ trước khi lọc. Việc lọc thật vẫn do nh3 làm ngay sau, nên dù chuỗi vào có méo
    # thế nào thì kết quả cuối cũng đã qua allowlist.
    html = _HA_CAP_TIEU_DE.sub(r"<\1h4\2>", html)
    return nh3.clean(
        html, tags=_HTML_TAGS, attributes=_HTML_ATTRS, url_schemes=_URL_SCHEMES,
        attribute_filter=_loc_thuoc_tinh, link_rel="noopener noreferrer",
    )



# --- Dựng ảnh trang PDF -----------------------------------------------------
# Bề rộng ảnh. 1400px đọc rõ trên laptop và vẫn nét khi phóng to trên điện thoại. Tăng lên là nặng
# theo bình phương: mỗi nhân viên tải lại chừng đó MỖI LẦN mở màn nội quy.
_ANH_RONG_TOI_DA = 1400
# JPEG chứ không PNG: trang văn bản scan nén PNG nặng gấp 3–5 lần mà mắt không phân biệt được.
_ANH_CHAT_LUONG = 78
# Trần số trang. Một nội quy lao động thực tế 15–40 trang; quá 60 trang gần như chắc chắn là tải
# nhầm tài liệu khác, mà dựng ảnh 200 trang thì API treo vài phút và kho file phình vô ích.
_SO_TRANG_TOI_DA = 60


def pdf_thanh_anh(data: bytes) -> list[tuple[bytes, int, int]]:
    """Dựng TỪNG TRANG PDF thành ảnh JPEG. Trả `[(bytes, rộng, cao), ...]` theo đúng thứ tự trang.

    Đây là đường "giữ nguyên dáng chữ": không đọc chữ, không dựng lại bố cục — hiện chính trang đó.
    Nhờ vậy bản SCAN đã ký, đóng dấu đỏ cũng dùng được mà không cần OCR.

    Gọi MỘT LẦN khi tải tài liệu lên, KHÔNG gọi lúc đọc: dựng khi đọc thì mỗi nhân viên mở màn là
    server giải mã lại cả tập PDF."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # xem `NoiQuyInfrastructureError` — đừng vu cho file của người dùng
        raise NoiQuyInfrastructureError(
            "Server chưa cài thư viện dựng ảnh PDF nên tạm thời không hiện được bản gốc. Đây là lỗi "
            "cài đặt của hệ thống, KHÔNG phải do file của bạn — hãy báo bộ phận kỹ thuật."
        ) from exc
    from PIL import Image as PILImage  # theo reportlab, luôn có sẵn

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as exc:
        raise NoiQuyValidationError("PDF không hợp lệ hoặc đã bị hỏng.") from exc

    so_trang = len(pdf)
    if so_trang == 0:
        raise NoiQuyValidationError("PDF không có trang nào.")
    if so_trang > _SO_TRANG_TOI_DA:
        raise NoiQuyValidationError(
            f"Tài liệu có {so_trang} trang, vượt mức {_SO_TRANG_TOI_DA} trang. Hãy kiểm tra lại "
            f"xem có phải đúng file nội quy không."
        )

    ket_qua: list[tuple[bytes, int, int]] = []
    for i in range(so_trang):
        trang = pdf[i]
        rong_diem = float(trang.get_width()) or 1.0
        # `scale` tính theo 72 dpi. Không phóng to trang vốn đã lớn hơn mức cần (scale ≤ 1 giữ
        # nguyên) — phóng lên chỉ làm file nặng, không thêm chi tiết nào.
        ti_le = min(_ANH_RONG_TOI_DA / rong_diem, 4.0)
        anh = trang.render(scale=ti_le).to_pil().convert("RGB")
        if anh.width > _ANH_RONG_TOI_DA:
            cao = round(anh.height * _ANH_RONG_TOI_DA / anh.width)
            anh = anh.resize((_ANH_RONG_TOI_DA, cao), PILImage.LANCZOS)
        buf = BytesIO()
        anh.save(buf, format="JPEG", quality=_ANH_CHAT_LUONG, optimize=True)
        ket_qua.append((buf.getvalue(), anh.width, anh.height))
    return ket_qua


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class NoiQuyService:
    def __init__(self, noi_quy: NoiQuyRepository, audit: AuditLogRepository | None = None) -> None:
        self.noi_quy = noi_quy
        self.audit = audit

    # --- đọc: ai đăng nhập cũng gọi được ------------------------------------

    def current(self, document_id: int):
        """Bản đang hiệu lực CỦA MỘT TÀI LIỆU. `None` = tài liệu này chưa ban hành lần nào."""
        return self.noi_quy.current(document_id)

    def current_dau_tien(self):
        """Bản hiệu lực của tài liệu ĐẦU DANH SÁCH — cho `GET /current` cũ khỏi gãy.

        Giữ endpoint cũ sống thêm một nhịp phát hành: lúc deploy, bản giao diện cũ vẫn đang mở
        trong trình duyệt nhân viên và nó chỉ biết gọi `/current`."""
        ds = self.documents_for_reader()
        return ds[0][1] if ds else None

    def list_versions(self, document_id: int):
        return self.noi_quy.list_versions(document_id)

    # --- danh mục tài liệu --------------------------------------------------

    def documents_for_reader(self):
        """Danh sách tài liệu NHÂN VIÊN được thấy: đang dùng **và đã ban hành ít nhất một lần**.

        Lọc "đã ban hành" là bắt buộc: chủ tạo tiêu đề rồi chưa tải nội dung lên thì nhân viên bấm
        vào sẽ ra trang trắng — trông y như hệ thống hỏng."""
        ra = []
        for d in self.noi_quy.list_documents(chi_dang_dung=True):
            hien_hanh = self.noi_quy.current(d.id)
            if hien_hanh is not None:
                ra.append((d, hien_hanh))
        return ra

    def documents_for_editor(self):
        """Danh sách cho người soạn: KÈM tài liệu chưa ban hành và tài liệu đã ẩn — họ cần thấy để
        làm tiếp, hoặc để bật lại."""
        return [(d, self.noi_quy.current(d.id))
                for d in self.noi_quy.list_documents(chi_dang_dung=False)]

    def co_nhap(self, document_id: int) -> bool:
        """Tài liệu này có nháp đang treo không — để danh sách của người soạn đánh dấu."""
        return self.noi_quy.get_draft(document_id) is not None

    def get_document(self, document_id: int):
        d = self.noi_quy.get_document(document_id)
        if d is None:
            raise NoiQuyNotFound("Không tìm thấy tài liệu nội quy.")
        return d

    def create_document(self, *, title: str):
        ten = _clean(title)
        if not ten:
            raise NoiQuyValidationError("Tên tài liệu không được để trống.")
        if self.noi_quy.find_document_by_title(ten) is not None:
            raise NoiQuyValidationError(f"Đã có tài liệu tên “{ten}”. Đặt tên khác cho khỏi lẫn.")
        return self.noi_quy.create_document(title=ten, seq=self.noi_quy.next_seq())

    def update_document(self, document_id: int, *, title: str | None = None,
                        seq: int | None = None, is_active: bool | None = None):
        """Đổi tên / xếp lại / ẩn.

        ⚠️ Đổi tên CHỈ đổi tên hiện hành. Tiêu đề của các bản ĐÃ BAN HÀNH nằm ở
        `noi_quy_versions.title` và KHÔNG bị đụng — nếu không thì đổi tên hôm nay là viết lại lịch
        sử của hôm qua."""
        doc = self.get_document(document_id)
        fields: dict = {}
        if title is not None:
            ten = _clean(title)
            if not ten:
                raise NoiQuyValidationError("Tên tài liệu không được để trống.")
            trung = self.noi_quy.find_document_by_title(ten)
            if trung is not None and trung.id != doc.id:
                raise NoiQuyValidationError(f"Đã có tài liệu tên “{ten}”. Đặt tên khác cho khỏi lẫn.")
            fields["title"] = ten
        if seq is not None:
            fields["seq"] = seq
        if is_active is not None:
            fields["is_active"] = is_active
        return self.noi_quy.update_document(doc, **fields) if fields else doc

    def attachments(self, version_id: int):
        return self.noi_quy.list_attachments(version_id)

    def pages(self, version_id: int):
        """Ảnh từng trang (chỉ có với bản `source_kind='file'` từ PDF)."""
        return self.noi_quy.list_pages(version_id)

    # --- soạn thảo: chỉ người có quyền --------------------------------------

    def get_or_create_draft(self, document_id: int):
        """Bản nháp đang mở CỦA MỘT TÀI LIỆU; chưa có thì mở mới, chép sẵn nội dung bản hiệu lực.

        Chép nội dung bản cũ chứ không mở trang trắng: sửa nội quy hầu như luôn là sửa vài chỗ
        trên bản đang có, bắt làm lại từ đầu là mời người ta làm thiếu.

        ⚠️ Cả `get_draft` lẫn `current` đều PHẢI lọc theo `document_id`. Không lọc thì tài liệu mới
        ra đời là bản sao nguyên văn của tài liệu khác, và nháp của hai tài liệu lẫn vào nhau."""
        doc = self.get_document(document_id)
        draft = self.noi_quy.get_draft(doc.id)
        if draft is not None:
            return draft
        hien_hanh = self.noi_quy.current(doc.id)
        draft = self.noi_quy.create_draft(
            document_id=doc.id,
            noi_dung=hien_hanh.noi_dung if hien_hanh else "",
            source_kind=hien_hanh.source_kind if hien_hanh else NQ_SRC_HTML,
            title=doc.title,
        )
        if hien_hanh is not None:
            # CHÉP CẢ FILE ĐÍNH KÈM sang nháp. Không chép thì sửa một lỗi chính tả rồi ban hành
            # là bản PDF đã ký BIẾN MẤT — mà không ai báo gì. Chỉ nhân đôi DÒNG trong DB, cùng
            # trỏ về một file trong kho (không nhân đôi file thật).
            for f in self.noi_quy.list_attachments(hien_hanh.id):
                self.noi_quy.add_attachment(
                    version_id=draft.id, file_name=f.file_name, file_url=f.file_url,
                    file_type=f.file_type, uploaded_by=f.uploaded_by,
                    is_import_source=f.is_import_source,
                )
            # CHÉP CẢ ẢNH TRANG — cùng một lý do, và ở đây hậu quả còn nặng hơn: với bản
            # `source_kind='file'` thì ảnh trang CHÍNH LÀ nội dung. Không chép thì chỉ cần mở nháp
            # ra rồi ban hành lại là cả công ty mở nội quy thấy TRỐNG TRƠN.
            pages = self.noi_quy.list_pages(hien_hanh.id)
            if pages:
                self.noi_quy.replace_pages(
                    draft.id, [(p.file_url, p.width, p.height) for p in pages])
        return draft

    def save_draft(self, document_id: int, *, noi_dung: str, ghi_chu: str | None = None,
                   source_kind: str | None = None):
        """Lưu nháp. KHÔNG đụng bản đang hiệu lực ⇒ nhân viên vẫn đọc bản cũ.

        `source_kind=None` = giữ nguyên nguồn hiện tại. Truyền `'html'` là **chuyển hẳn về đường gõ
        trong app**, và khi đó ảnh trang PDF bị xoá: để lại thì một bản mang cả ảnh trang lẫn HTML,
        tức hai nội dung cùng lúc, và không ai biết nhân viên đang đọc cái nào."""
        draft = self.get_or_create_draft(document_id)
        fields: dict = {"noi_dung": lam_sach_html(noi_dung), "ghi_chu": _clean(ghi_chu)}
        if source_kind is not None:
            if source_kind not in NQ_SOURCE_KINDS:
                raise NoiQuyValidationError(f"Nguồn nội dung không hợp lệ: {source_kind}")
            fields["source_kind"] = source_kind
            if source_kind == NQ_SRC_HTML:
                self.noi_quy.delete_pages(draft.id)
        return self.noi_quy.update(draft, **fields)

    def dat_ban_goc_pdf(self, document_id: int, *, trang: list[tuple[str, int, int]],
                        file_name: str, file_url: str, file_type: str | None, actor):
        """Đặt bản nháp thành "hiện đúng bản gốc PDF": ảnh từng trang + file gốc đính kèm.

        `trang` = `[(file_url, rộng, cao), ...]` do router dựng sẵn (router giữ việc ghi kho file).

        `noi_dung` bị xoá trắng là CHỦ Ý: nội dung của bản này là ảnh trang. Để lại HTML cũ thì một
        bản mang hai nội dung, và lúc hiện ra sẽ tuỳ nhánh code nào chạy trước — kiểu lỗi không ai
        lần ra được."""
        draft = self.get_or_create_draft(document_id)

        # Nhập lại thì THAY file gốc cũ, không cộng dồn (chủ chốt 30/07/2026). Nội quy là căn cứ
        # kỷ luật: để lại 3 file gần giống nhau thì lúc tranh chấp không ai biết bản nào là thật.
        # CHỈ xoá hàng `is_import_source` — file chứng từ chủ tự đính kèm không bao giờ bị đụng.
        for cu in self.noi_quy.list_import_sources(draft.id):
            self.noi_quy.delete_attachment(cu)

        self.noi_quy.add_attachment(
            version_id=draft.id, file_name=file_name, file_url=file_url, file_type=file_type,
            uploaded_by=getattr(actor, "id", None), is_import_source=True,
        )
        self.noi_quy.replace_pages(draft.id, trang)
        return self.noi_quy.update(draft, noi_dung="", source_kind=NQ_SRC_FILE)

    def publish(self, document_id: int, *, actor):
        """Ban hành nháp CỦA MỘT TÀI LIỆU → thành bản hiệu lực của tài liệu đó.

        Chỉ đụng tài liệu này: các tài liệu khác giữ nguyên ngày ban hành cũ (chủ chốt 30/07/2026 —
        sửa "Các lỗi thường gặp" thì "Nội quy lao động" không được đổi ngày)."""
        doc = self.get_document(document_id)
        draft = self.noi_quy.get_draft(doc.id)
        if draft is None:
            raise NoiQuyValidationError("Chưa có bản nháp nào để ban hành.")
        # Chốt chặn cuối: nháp lấy ra phải đúng của tài liệu đang ban hành. Nếu một ngày ai đó nới
        # `get_draft` trở lại thành truy vấn toàn cục, dòng này là thứ nổ ra thay vì âm thầm ban
        # hành nội dung của tài liệu khác.
        if draft.document_id != doc.id:
            raise NoiQuyValidationError("Bản nháp không thuộc tài liệu này.")
        # Bản dạng ảnh trang (PDF) có `noi_dung` TRỐNG là bình thường — nội dung của nó là ảnh.
        # Kiểm theo chữ ở đây sẽ chặn luôn việc ban hành nội quy PDF.
        co_anh_trang = bool(self.noi_quy.list_pages(draft.id))
        # Đếm theo CHỮ chứ không theo độ dài chuỗi: trình soạn thảo luôn để lại `<p></p>` khi
        # người dùng xoá hết, nên `"<p></p>".strip()` vẫn "có nội dung" — bấm Ban hành là xoá
        # trắng nội quy cả công ty mà hệ thống không cản.
        co_chu = bool(nh3.clean(draft.noi_dung or "", tags=set()).strip())
        if not co_anh_trang and not co_chu:
            raise NoiQuyValidationError("Nội quy đang trống — nhập nội dung rồi mới ban hành được.")
        # CHỤP tiêu đề vào chính bản này trước khi ban hành. Từ đây về sau chủ đổi tên tài liệu bao
        # nhiêu lần cũng không viết lại tiêu đề của bản đã ban hành hôm nay.
        if draft.title != doc.title:
            self.noi_quy.update(draft, title=doc.title)
        v = self.noi_quy.publish(draft, actor_id=getattr(actor, "id", None))
        if self.audit is not None:
            self.audit.create(
                actor_user_id=getattr(actor, "id", None),
                action="noi_quy_published",
                target=f"noi_quy_version:{v.id}",
                detail=(v.ghi_chu or f"Ban hành nội quy: {doc.title}"),
            )
        return v

    # --- đính kèm -----------------------------------------------------------

    def add_attachment(self, *, version_id: int, file_name: str, file_url: str,
                       file_type: str | None, actor):
        v = self.noi_quy.get(version_id)
        if v is None:
            raise NoiQuyNotFound("Không tìm thấy bản nội quy.")
        if v.status == NQ_PUBLISHED:
            # Bản đã ban hành là ảnh chụp tại thời điểm đó — thêm/bớt file sau lưng người đã đọc
            # thì "bản tháng 5" không còn là bản tháng 5 nữa. Muốn đổi file thì ban hành bản mới.
            raise NoiQuyValidationError(
                "Bản đã ban hành không sửa được. Mở bản nháp mới rồi ban hành lại.")
        return self.noi_quy.add_attachment(
            version_id=version_id, file_name=file_name, file_url=file_url,
            file_type=file_type, uploaded_by=getattr(actor, "id", None),
        )

    def delete_attachment(self, *, attachment_id: int):
        a = self.noi_quy.get_attachment(attachment_id)
        if a is None:
            raise NoiQuyNotFound("Không tìm thấy file đính kèm.")
        v = self.noi_quy.get(a.version_id)
        if v is not None and v.status == NQ_PUBLISHED:
            raise NoiQuyValidationError(
                "Bản đã ban hành không sửa được. Mở bản nháp mới rồi ban hành lại.")
        self.noi_quy.delete_attachment(a)
