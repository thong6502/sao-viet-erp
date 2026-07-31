"""Schema Nội quy công ty."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoiQuyAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    # Phơi ra để FE biết ĐÂU là bản gốc của lần tải nội dung (nút "Tải bản PDF gốc" trỏ vào nó).
    # Không có field này thì FE phải SUY từ đường dẫn kho file (`noi-quy/<id>/` vs
    # `noi-quy/<id>-trang/`) — đoán đúng hôm nay nhưng sai ngay khi chủ đính kèm thêm một PDF nữa,
    # và đổi cách đặt tên file trong `storage.py` là âm thầm hỏng.
    is_import_source: bool = False
    uploaded_at: datetime


class NoiQuyPageOut(BaseModel):
    """Một trang của bản nội quy dạng PDF, đã dựng thành ảnh."""

    model_config = ConfigDict(from_attributes=True)

    page_no: int
    file_url: str
    # FE đặt sẵn `width`/`height` lên `<img>` để trang KHÔNG nhảy khi ảnh tải lười xong.
    width: int = 0
    height: int = 0


class NoiQuyOut(BaseModel):
    """Một bản nội quy + file kèm theo.

    `has_content=False` ⇒ công ty CHƯA ban hành lần nào; màn hiện trạng thái rỗng chứ không phải
    trang trắng. Không dùng `null` cho cả object để FE khỏi phải phân biệt "chưa tải xong" với
    "chưa có gì"."""

    has_content: bool = False
    id: int | None = None
    document_id: int | None = None
    # Tiêu đề CỦA BẢN NÀY (bản chụp lúc ban hành), không phải tên hiện hành của tài liệu.
    title: str | None = None
    noi_dung: str = ""
    # `html` = gõ trong app · `file` = hiện đúng bản gốc đã tải lên (giữ nguyên dáng chữ).
    # FE rẽ nhánh hiển thị theo cột này.
    source_kind: str = "html"
    ghi_chu: str | None = None
    status: str | None = None
    published_at: datetime | None = None
    published_by_name: str | None = None
    updated_at: datetime | None = None
    attachments: list[NoiQuyAttachmentOut] = []
    # Rỗng với bản `html`. Có giá trị ⇒ nội dung nằm ở ẢNH TRANG, không ở `noi_dung`.
    pages: list[NoiQuyPageOut] = []


class NoiQuyDocumentRow(BaseModel):
    """Một dòng trong DANH SÁCH TÀI LIỆU (cột phải). Bấm vào là mở nội dung bên trái."""

    id: int
    title: str
    seq: int = 1
    is_active: bool = True
    # `None` = tài liệu chưa ban hành lần nào. Danh sách của NHÂN VIÊN đã lọc bỏ những dòng này —
    # để lại là họ bấm vào ra trang trắng, trông y như hệ thống hỏng.
    published_at: datetime | None = None
    co_nhap: bool = False   # chỉ có nghĩa với người soạn


class NoiQuyDocumentsOut(BaseModel):
    items: list[NoiQuyDocumentRow]


class NoiQuyDocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class NoiQuyDocumentPatch(BaseModel):
    """Đổi tên / xếp lại / ẩn. KHÔNG có đường xoá — xem chú thích ở model `NoiQuyDocument`."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    seq: int | None = None
    is_active: bool | None = None


class NoiQuyVersionRow(BaseModel):
    """Một dòng trong lịch sử các bản ĐÃ ban hành."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ghi_chu: str | None = None
    published_at: datetime | None = None
    published_by_name: str | None = None


class NoiQuyVersionsOut(BaseModel):
    items: list[NoiQuyVersionRow]


class NoiQuyDraftIn(BaseModel):
    # Trần độ dài là CÓ CHỦ Ý, không phải phòng xa: `noi_dung` được MỌI nhân viên tải lại mỗi lần
    # mở màn nội quy. Không có trần thì một lần dán nhầm là cả công ty gánh khối đó mãi. Nội quy
    # 100 trang HTML ~400 KB, nên 2 MB là rất rộng rãi mà vẫn chặn được tai nạn.
    noi_dung: str = Field(default="", max_length=2 * 1024 * 1024)
    ghi_chu: str | None = Field(default=None, max_length=255)
    # `None` = giữ nguyên nguồn hiện tại. `'html'` = chuyển hẳn về đường gõ trong app (xoá ảnh
    # trang). `'file'` = nội dung này là bản chuyển đổi trung thực từ tài liệu đã tải lên.
    source_kind: str | None = Field(default=None)


# `NoiQuyImportOut` đã bỏ cùng đường "tách chữ từ PDF": màn này giờ CHỈ tải file lên (chủ chốt
# 30/07/2026). Giữ nguyên dáng thì PDF dựng ảnh trang, Word chuyển bằng docx-preview.
