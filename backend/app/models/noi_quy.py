"""Nội quy công ty.

Luồng hiện hành dùng `noi_quy_records`: mỗi dòng là một tài liệu tải lên, không còn nháp, soạn
thảo hay ban hành phiên bản. Các bảng version/page/attachment phía dưới được giữ lại ở dạng
legacy để DB đã chạy không mất dữ liệu; API mới không ghi vào chúng.

Hai bảng:
  - `noi_quy_versions`    — mỗi lần ban hành là MỘT dòng mới, KHÔNG ghi đè bản cũ.
  - `noi_quy_attachments` — bản PDF/Word đã ký/đóng dấu, đính vào ĐÚNG bản đã ban hành.

**Vì sao versioned chứ không phải một dòng sửa đè:** nội quy là căn cứ kỷ luật. Sửa đè thì sau này
không ai trả lời được *"hồi tháng 5 luật là gì"* — mà lúc cần câu trả lời đó thường là lúc đang
tranh chấp. Append là đúng khuôn `employee_salaries` của dự án: gần như miễn phí, mà mất thì không
lấy lại được.

**Nháp vs Ban hành:** Giám đốc sửa trên bản `draft` — chỉ mình thấy. Bấm ban hành thì nháp thành
`published` và bản cũ lùi thành lịch sử. Không có bước này thì cả công ty đọc được nội quy viết dở.

Bảng MỚI ⇒ `create_all` tự tạo, KHÔNG cần migration. Nhưng phải export ở `models/__init__.py`
(quên là create_all không thấy bảng) và ghi vào `docs/DB_SCHEMA.md` (guard test bắt).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import false as sa_false, true as sa_true

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NoiQuyRecord(Base):
    """Một tài liệu trong danh mục nội quy công ty."""

    __tablename__ = "noi_quy_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )

# --- Trạng thái một bản nội quy ---------------------------------------------
NQ_DRAFT = "draft"          # đang soạn — CHỈ người soạn thấy
NQ_PUBLISHED = "published"  # đã ban hành — mọi nhân viên thấy
NQ_STATUSES = (NQ_DRAFT, NQ_PUBLISHED)

# --- Nguồn nội dung của MỘT bản ---------------------------------------------
# Chủ chốt "cả hai": công ty có sẵn file thì hiện đúng file (giữ nguyên dáng chữ 100%), không có
# thì gõ trong app. Nhưng mỗi BẢN BAN HÀNH khai đúng MỘT nguồn — nếu để cả hai cùng sống trên một
# bản thì sớm muộn chúng lệch nhau và không ai biết bản nào đang là luật.
NQ_SRC_HTML = "html"  # gõ/sửa trong app → đọc từ `noi_dung`
NQ_SRC_FILE = "file"  # tải tài liệu lên → đọc từ ảnh trang (`noi_quy_pages`) hoặc `noi_dung` giàu
NQ_SOURCE_KINDS = (NQ_SRC_HTML, NQ_SRC_FILE)

class NoiQuyDocument(Base):
    """MỘT tài liệu trong bộ nội quy — danh tính bền, sống qua mọi lần ban hành.

    Bộ nội quy của một nhà máy thường là NHIỀU văn bản: Nội quy lao động, Quy chế lương thưởng,
    An toàn lao động, Các lỗi thường gặp… Mỗi cái một file, một vòng đời riêng (chủ 30/07/2026:
    *"upload được nhiều file, mỗi file đi theo title, bấm title thì mở ra bên trái"*).

    **Mỗi tài liệu là một CHUỖI VERSION riêng** (`noi_quy_versions.document_id`) ⇒ sửa "Các lỗi
    thường gặp" thì "Nội quy lao động" giữ nguyên ngày ban hành cũ, và mỗi tài liệu có lịch sử
    riêng. Đây là chủ đã chốt, không phải mặc định kỹ thuật.

    ⚠️ **KHÔNG có đường xoá tài liệu.** `noi_quy_pages` và `noi_quy_attachments` đều
    `ondelete=CASCADE` theo version, nên xoá một tài liệu là bay toàn bộ lịch sử + ảnh trang + hàng
    file của nó chỉ bằng một cú bấm. Muốn thôi dùng thì đặt `is_active=False` — và bản cũ vẫn tra
    được, vì "hồi tháng 5 luật là gì" là câu phải trả lời được.

    Bảng MỚI ⇒ `create_all` tự tạo, KHÔNG cần migration; nhưng phải export ở `models/__init__.py`.
    """

    __tablename__ = "noi_quy_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tên HIỆN HÀNH, dùng để hiện danh sách. Tiêu đề của từng bản đã ban hành được chụp riêng ở
    # `noi_quy_versions.title` — xem chú thích ở đó.
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # False = thôi áp dụng: mất khỏi danh sách nhân viên, nhưng KHÔNG mất khỏi lịch sử.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class NoiQuyVersion(Base):
    """Một bản của MỘT tài liệu. Bản hiệu lực = `published` có `published_at` mới nhất TRONG tài
    liệu đó."""

    __tablename__ = "noi_quy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # FK TRƠN, CỐ Ý KHÔNG cascade: xoá lạc một tài liệu thì phải NỔ, không được âm thầm kéo theo
    # cả lịch sử ban hành.
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("noi_quy_documents.id"), index=True, nullable=True
    )
    # BẢN CHỤP tiêu đề lúc ban hành. Vì sao không chỉ đọc từ `noi_quy_documents.title`: đổi tên tài
    # liệu khi đó sẽ viết lại tiêu đề của MỌI bản lịch sử đã ban hành — đúng thứ mà cả kiến trúc
    # append-only này dựng ra để chống.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # **HTML đã lọc allowlist ở server** (`lam_sach_html` — nh3), KHÔNG phải văn bản thuần.
    # Chỉ giữ thẻ cấu trúc + định dạng chữ; `<img src>` chỉ được trỏ vào `/api/files/`.
    # `source_kind='file'` với bản PDF thì cột này để trống — nội dung nằm ở `noi_quy_pages`.
    noi_dung: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Nguồn của bản này: `html` (gõ trong app) hay `file` (tải tài liệu lên). Xem `NQ_SOURCE_KINDS`.
    source_kind: Mapped[str] = mapped_column(
        String(8), nullable=False, default=NQ_SRC_HTML, server_default=NQ_SRC_HTML
    )
    # "Bản này sửa gì" — để người đọc lịch sử biết đổi gì mà không phải so từng chữ.
    ghi_chu: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=NQ_DRAFT, server_default=NQ_DRAFT, index=True
    )
    # Chỉ có giá trị khi đã ban hành. NULL ⇒ vẫn là nháp, nhân viên KHÔNG thấy.
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    published_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class NoiQuyAttachment(Base):
    """File đính kèm của MỘT bản nội quy (bản scan có ký/đóng dấu).

    Gắn vào version chứ không phải "toàn cục": bản PDF có dấu là của đúng bản nội quy đó, ban hành
    bản mới thì đính bản scan mới.

    ⚠️ Bytes nằm ở kho file chung (`app/storage.py`), lưu dưới thư mục **`noi-quy/`**. Thư mục này
    CỐ Ý không khai trong `_PREFIX_PERMISSION` của `routers/files.py` ⇒ ai đăng nhập cũng tải
    được — giống `avatars/`. Thêm nó vào bảng đó là chỉ Giám đốc mở được file, phá đúng yêu cầu
    "tất cả nhân viên thấy". Có test canh.
    """

    __tablename__ = "noi_quy_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("noi_quy_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)   # MIME
    # True = file GỐC của lần nhập/tải nội dung, hệ thống tự đính. Nhập lại thì hàng này bị THAY,
    # không cộng dồn: nhập 3 lần mà để lại 3 file gần giống nhau thì lúc tranh chấp không ai biết
    # bản nào là bản thật. File do người dùng tự bấm "Đính kèm" thì False và không bao giờ bị thay.
    is_import_source: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class NoiQuyPage(Base):
    """MỘT trang của bản nội quy dạng PDF, đã dựng thành ảnh.

    **Vì sao dựng ảnh thay vì tách chữ:** PDF không lưu đoạn văn hay kiểu chữ, chỉ lưu vị trí từng
    chữ trên trang — tách chữ ra thì mất sạch dáng. Chủ yêu cầu "giữ nguyên form chữ kiểu chữ dáng
    chữ", nên cách duy nhất đúng là hiện chính trang đó. Kèm lợi ích lớn: bản SCAN đã ký/đóng dấu
    đỏ cũng dùng được, không cần OCR.

    Dựng MỘT LẦN lúc ban hành, không dựng lúc đọc: nếu dựng khi đọc thì mỗi nhân viên mở màn là
    server giải mã lại cả tập PDF.

    Bảng MỚI ⇒ `create_all` tự tạo, KHÔNG cần migration — nhưng phải export ở `models/__init__.py`.
    """

    __tablename__ = "noi_quy_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("noi_quy_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)  # đếm từ 1
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Kích thước ảnh thật — để FE đặt `width`/`height` trên `<img>` và trang KHÔNG nhảy khi ảnh
    # tải xong (mỗi trang vài trăm KB, tải lười, nên nhảy layout là thấy rõ).
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
