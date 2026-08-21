"""Nhãn công đoạn (bước lệnh) — bản sao NGUYÊN LỐI của nhãn khách hàng (`customer_tags` +
`customer_tag_catalog`), chỉ khác: "khách" đổi thành "một BƯỚC công đoạn".

Vì sao có (20/08/2026): bỏ loại bước "thuê ngoài" — cả một cụm ngày gửi/nhận, hao hụt, đơn giá
gia công, tab giao–nhận — quá sâu cho một màn LÊN KẾ HOẠCH. Thay bằng cách đơn giản nhất: gắn
NHÃN cho bước (vd "Thuê ngoài"), người dùng thêm/xoá/tạo nhãn Y HỆT cách gắn thẻ ở màn Khách hàng.

Bước công đoạn nằm ở HAI bảng khác nhau (`lsx_cong_doan` của routing LSX, `bai_ghep_cong_doan`
của Bài ghép 2), nên bảng GÁN trỏ bằng CẶP (`buoc_loai`, `buoc_id`) — cùng lối khớp lỏng đã dùng
ở mặt-hàng-gốc (`hang_loai`, `hang_id`). Không khoá ngoại cứng: một bảng gán không thể FK sang
hai bảng cha.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Giá trị hợp lệ cho `buoc_loai` — bước thuộc bảng nào.
BUOC_LOAI_LSX = "lsx"            # LsxCongDoan (routing lệnh sản xuất)
BUOC_LOAI_BAI_GHEP = "bai_ghep"  # BaiGhepCongDoan (bước chung của bài ghép)
BUOC_LOAI_HOP_LE = (BUOC_LOAI_LSX, BUOC_LOAI_BAI_GHEP)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CongDoanTag(Base):
    """Nhãn ĐÃ GÁN cho một bước. Một bước nhiều nhãn; service chặn trùng nhãn (case-insensitive)
    trong cùng một bước. Khớp lỏng với kho nhãn bằng chuỗi `label`, không FK — xem `CongDoanTagCatalog`."""

    __tablename__ = "cong_doan_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Cặp (buoc_loai, buoc_id) trỏ tới lsx_cong_doan.id HOẶC bai_ghep_cong_doan.id. Không FK cứng
    # vì một cột không trỏ được sang hai bảng cha; dọn rác khi xoá bước là việc của service nguồn.
    buoc_loai: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    buoc_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CongDoanTagCatalog(Base):
    """KHO NHÃN dùng chung cho bước công đoạn — danh sách nhãn *có thể* gán, tách khỏi việc đã gán
    cho bước nào. Cùng triết lý với `customer_tag_catalog`:

      · quan hệ với `cong_doan_tags` là LỎNG — nối bằng chuỗi `label`, KHÔNG khoá ngoại;
      · xoá nhãn ở đây thì service tự dọn mọi dòng gán mang đúng nhãn đó (xem `xoa_nhan_kho`);
      · KHÔNG có cột `mau` — màu chip do `tagTone()` bên frontend suy từ chuỗi nhãn;
      · KHÔNG có cột `active` — yêu cầu là THÊM và XOÁ, cờ ngừng-dùng không ô bật/tắt là cột chết.
    """

    __tablename__ = "cong_doan_tag_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
