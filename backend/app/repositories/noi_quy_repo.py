"""Truy cập DB cho Nội quy công ty — tầng DUY NHẤT chạm bảng `noi_quy_*`.

Không có luật nghiệp vụ ở đây (luật nháp/ban hành nằm ở `NoiQuyService`).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.noi_quy import (
    NQ_DRAFT,
    NQ_PUBLISHED,
    NQ_SRC_HTML,
    NoiQuyAttachment,
    NoiQuyDocument,
    NoiQuyPage,
    NoiQuyVersion,
)


class NoiQuyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- đọc ----------------------------------------------------------------

    # ⚠️ CẢ BA hàm dưới đây BẮT BUỘC lọc theo `document_id`. Trước khi có tầng tài liệu chúng lọc
    # toàn cục, và nếu để nguyên khi đã có nhiều tài liệu thì hỏng theo kiểu IM LẶNG nhất:
    #   - `get_draft()` không lọc ⇒ mở nháp tài liệu A rồi mở nháp B sẽ trả về nháp của A; ghi cho
    #     B là đè vào A, và Ban hành biến nó thành bản hiệu lực của A. Đảo nội dung giữa hai văn
    #     bản, không một dòng cảnh báo.
    #   - `current()` không lọc ⇒ tài liệu MỚI ra đời là bản sao nguyên văn của tài liệu khác (nó
    #     được dùng để mồi nháp), kèm cả file đã ký và ảnh trang.
    #   - `list_versions()` không lọc ⇒ lịch sử trộn chung mọi tài liệu.

    def current(self, document_id: int) -> NoiQuyVersion | None:
        """Bản ĐANG HIỆU LỰC của MỘT tài liệu = `published` có `published_at` mới nhất.

        Hoà ngày thì `id` lớn hơn thắng (bản lưu SAU) — cùng quy ước với `employee_salaries`."""
        return self.db.execute(
            select(NoiQuyVersion)
            .where(NoiQuyVersion.document_id == document_id)
            .where(NoiQuyVersion.status == NQ_PUBLISHED)
            .order_by(NoiQuyVersion.published_at.desc(), NoiQuyVersion.id.desc())
        ).scalars().first()

    def get_draft(self, document_id: int) -> NoiQuyVersion | None:
        """Bản nháp đang mở CỦA MỘT TÀI LIỆU. Luật là "tối đa một nháp MỖI TÀI LIỆU"."""
        return self.db.execute(
            select(NoiQuyVersion)
            .where(NoiQuyVersion.document_id == document_id)
            .where(NoiQuyVersion.status == NQ_DRAFT)
            .order_by(NoiQuyVersion.id.desc())
        ).scalars().first()

    def get(self, version_id: int) -> NoiQuyVersion | None:
        return self.db.get(NoiQuyVersion, version_id)

    def list_versions(self, document_id: int, *, limit: int = 50) -> list[NoiQuyVersion]:
        """Lịch sử các bản ĐÃ ban hành của MỘT tài liệu, mới nhất trước. Nháp không nằm trong đây."""
        return list(self.db.execute(
            select(NoiQuyVersion)
            .where(NoiQuyVersion.document_id == document_id)
            .where(NoiQuyVersion.status == NQ_PUBLISHED)
            .order_by(NoiQuyVersion.published_at.desc(), NoiQuyVersion.id.desc())
            .limit(limit)
        ).scalars())

    # --- tài liệu -----------------------------------------------------------

    def list_documents(self, *, chi_dang_dung: bool = True) -> list[NoiQuyDocument]:
        q = select(NoiQuyDocument)
        if chi_dang_dung:
            q = q.where(NoiQuyDocument.is_active.is_(True))
        return list(self.db.execute(
            q.order_by(NoiQuyDocument.seq.asc(), NoiQuyDocument.id.asc())
        ).scalars())

    def get_document(self, document_id: int) -> NoiQuyDocument | None:
        return self.db.get(NoiQuyDocument, document_id)

    def find_document_by_title(self, title: str) -> NoiQuyDocument | None:
        """Tìm theo tên đã chuẩn hoá — để chặn trùng tiêu đề. Hai "Nội quy lao động" trong danh sách
        là chủ sẽ sửa nhầm cái, và không cách nào nhìn ra."""
        chuan = " ".join(title.split()).lower()
        for d in self.list_documents(chi_dang_dung=True):
            if " ".join(d.title.split()).lower() == chuan:
                return d
        return None

    def create_document(self, *, title: str, seq: int) -> NoiQuyDocument:
        d = NoiQuyDocument(title=title, seq=seq)
        self.db.add(d)
        self.db.commit()
        self.db.refresh(d)
        return d

    def update_document(self, doc: NoiQuyDocument, **fields) -> NoiQuyDocument:
        for k, v in fields.items():
            setattr(doc, k, v)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def next_seq(self) -> int:
        return len(self.list_documents(chi_dang_dung=False)) + 1

    # --- ghi ----------------------------------------------------------------

    def create_draft(self, *, document_id: int, noi_dung: str = "", ghi_chu: str | None = None,
                     source_kind: str = NQ_SRC_HTML, title: str | None = None) -> NoiQuyVersion:
        v = NoiQuyVersion(document_id=document_id, noi_dung=noi_dung, ghi_chu=ghi_chu,
                          status=NQ_DRAFT, source_kind=source_kind, title=title)
        self.db.add(v)
        self.db.commit()
        self.db.refresh(v)
        return v

    def update(self, version: NoiQuyVersion, **fields) -> NoiQuyVersion:
        for k, v in fields.items():
            setattr(version, k, v)
        self.db.commit()
        self.db.refresh(version)
        return version

    def publish(self, version: NoiQuyVersion, *, actor_id: int | None) -> NoiQuyVersion:
        version.status = NQ_PUBLISHED
        version.published_at = datetime.now(timezone.utc)
        version.published_by = actor_id
        self.db.commit()
        self.db.refresh(version)
        return version

    # --- đính kèm -----------------------------------------------------------

    def list_attachments(self, version_id: int) -> list[NoiQuyAttachment]:
        return list(self.db.execute(
            select(NoiQuyAttachment)
            .where(NoiQuyAttachment.version_id == version_id)
            .order_by(NoiQuyAttachment.id.asc())
        ).scalars())

    def add_attachment(self, *, version_id: int, file_name: str, file_url: str,
                       file_type: str | None, uploaded_by: int | None,
                       is_import_source: bool = False) -> NoiQuyAttachment:
        a = NoiQuyAttachment(version_id=version_id, file_name=file_name, file_url=file_url,
                             file_type=file_type, uploaded_by=uploaded_by,
                             is_import_source=is_import_source)
        self.db.add(a)
        self.db.commit()
        self.db.refresh(a)
        return a

    def get_attachment(self, attachment_id: int) -> NoiQuyAttachment | None:
        return self.db.get(NoiQuyAttachment, attachment_id)

    def delete_attachment(self, attachment: NoiQuyAttachment) -> None:
        self.db.delete(attachment)
        self.db.commit()

    def list_import_sources(self, version_id: int) -> list[NoiQuyAttachment]:
        """Các hàng file GỐC do hệ thống tự đính khi nhập (`is_import_source`).

        Tách riêng khỏi `list_attachments` vì đây là những hàng DUY NHẤT được phép thay khi nhập
        lại — file chứng từ chủ tự đính kèm thì không bao giờ đụng tới."""
        return list(self.db.execute(
            select(NoiQuyAttachment)
            .where(NoiQuyAttachment.version_id == version_id)
            .where(NoiQuyAttachment.is_import_source.is_(True))
        ).scalars())

    # --- ảnh trang PDF ------------------------------------------------------

    def list_pages(self, version_id: int) -> list[NoiQuyPage]:
        return list(self.db.execute(
            select(NoiQuyPage)
            .where(NoiQuyPage.version_id == version_id)
            .order_by(NoiQuyPage.page_no.asc())
        ).scalars())

    def replace_pages(self, version_id: int, rows: list[tuple[str, int, int]]) -> list[NoiQuyPage]:
        """THAY toàn bộ ảnh trang của một bản. `rows` = `[(file_url, rộng, cao), ...]`.

        Thay chứ không cộng thêm: tải lại tài liệu khác mà giữ ảnh cũ thì bản nội quy thành hai tài
        liệu dán vào nhau — sai mà nhìn vẫn "có nội dung" nên rất dễ lọt tới lúc ban hành."""
        self.delete_pages(version_id)
        pages = [
            NoiQuyPage(version_id=version_id, page_no=i, file_url=url, width=w, height=h)
            for i, (url, w, h) in enumerate(rows, start=1)
        ]
        self.db.add_all(pages)
        self.db.commit()
        return pages

    def delete_pages(self, version_id: int) -> None:
        for p in self.list_pages(version_id):
            self.db.delete(p)
        self.db.commit()
