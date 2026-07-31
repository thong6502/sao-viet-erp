"""Đề nghị kho (nhập / xuất) — docs/spec-kho-de-nghi.md §3–§5.

1 đề nghị = 1 chứng từ do người NGOÀI kho lập (tổ SX, mua hàng, bảo trì…). Hai luật
xương sống lấy từ BRD Module Kho:

* **Kho KHÔNG duyệt.** Duyệt là việc của tổ trưởng/quản lý bộ phận ĐỀ NGHỊ — BRD §2.6
  b8, §2.8 b6, §2.9 b5 đều ghi "Kho tiếp nhận phiếu ĐÃ DUYỆT". Kho chỉ lập phiếu
  nhập/xuất ứng theo đề nghị đã duyệt.
* **Đã duyệt là khoá.** BRD §1.5: phiếu đã duyệt không sửa trực tiếp; muốn đổi thì hủy
  và tạo lại.

Bảng MỚI → `create_all` tự dựng, không cần migration (migration chỉ để ALTER bảng cũ).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# Loại đề nghị. Giai đoạn 1 chỉ 2 giá trị; đặc thù nghiệp vụ (cấp bù, bảo trì, nhập trả…)
# ghi vào `ghi_chu` chứ chưa tách loại riêng (spec §1).
REQ_NHAP = "NHAP"
REQ_XUAT = "XUAT"
REQUEST_KINDS = (REQ_NHAP, REQ_XUAT)

# Vòng đời (spec §3). `partial`/`done` do hệ thống tự set khi phiếu ứng số lượng.
REQ_DRAFT = "draft"          # Nháp — người tạo còn sửa được
REQ_PENDING = "pending"      # Chờ duyệt
REQ_APPROVED = "approved"    # Đã duyệt → kho nhìn thấy trong Hộp yêu cầu
REQ_RECEIVED = "received"    # Kho tiếp nhận
REQ_PREPARING = "preparing"  # Kho đang chuẩn bị
REQ_PARTIAL = "partial"      # Đã cấp một phần
REQ_DONE = "done"            # Hoàn tất — mọi dòng đã ứng đủ
REQ_REJECTED = "rejected"
REQ_CANCELLED = "cancelled"
REQUEST_STATUSES = (
    REQ_DRAFT, REQ_PENDING, REQ_APPROVED, REQ_RECEIVED, REQ_PREPARING,
    REQ_PARTIAL, REQ_DONE, REQ_REJECTED, REQ_CANCELLED,
)
# Trạng thái người tạo còn được sửa/hủy.
REQUEST_EDITABLE = (REQ_DRAFT, REQ_PENDING)
# Trạng thái kho được phép lập phiếu ứng.
REQUEST_FULFILLABLE = (REQ_APPROVED, REQ_RECEIVED, REQ_PREPARING, REQ_PARTIAL)

PRIORITY_NORMAL = "binh_thuong"
PRIORITY_URGENT = "gap"
PRIORITIES = (PRIORITY_NORMAL, PRIORITY_URGENT)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockRequest(Base):
    """Header đề nghị kho."""

    __tablename__ = "stock_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Số đề nghị in trên chứng từ (DNN0001 / DNX0001) — sinh qua document_sequences.
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    loai: Mapped[str] = mapped_column(String(8), index=True, nullable=False)

    nguoi_tao_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    # Bộ phận đề nghị — dùng cho scope `department` và cho ô "Bộ phận" trên bản in.
    bo_phan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=True
    )
    # Kho đích của đề nghị: XUẤT = lĩnh từ kho nào, NHẬP = nhập về kho nào. Đèn tồn tính theo
    # kho này; phiếu kế thừa kho này (khoá). Nullable ở DB cho hàng cũ trước khi có cột, nhưng
    # API create BẮT BUỘC (schema).
    kho_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("kho_hang.id"), index=True, nullable=True
    )
    ngay_can: Mapped[date | None] = mapped_column(Date, nullable=True)
    uu_tien: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=PRIORITY_NORMAL, default=PRIORITY_NORMAL
    )
    # Đặc thù nghiệp vụ (nhập mua / xuất cấp bù / xuất bảo trì…) ghi ở đây — giai đoạn 1
    # chưa tách loại phiếu riêng nên đây là chỗ duy nhất giữ ngữ cảnh.
    ghi_chu: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    trang_thai: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False, server_default=REQ_DRAFT, default=REQ_DRAFT
    )
    nguoi_duyet_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    duyet_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ly_do_tu_choi: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Lý do KHO HỦY đề nghị (hủy phiếu nháp → đề nghị KẾT THÚC ở 'Đã hủy'). Tách khỏi
    # `ly_do_tu_choi` (lý do NGƯỜI DUYỆT từ chối). Null nếu chưa hủy. Thêm qua migration 0114.
    ly_do_huy: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lines: Mapped[list[StockRequestLine]] = relationship(
        "StockRequestLine",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="StockRequestLine.id",
    )

    __table_args__ = (
        CheckConstraint("loai IN ('NHAP','XUAT')", name="chk_stock_requests_loai"),
    )


class StockRequestLine(Base):
    """1 dòng vật tư của đề nghị.

    Bốn con số chạy theo thứ tự `sl_de_nghi → sl_duyet → sl_da_ung`; "còn lại" =
    `sl_duyet - sl_da_ung` (tính, không lưu — lưu thành cột thứ 4 là mời sai lệch).
    Service chặn cứng không cho ứng vượt `sl_duyet` (spec §5).
    """

    __tablename__ = "stock_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Hàng ĐÃ có mã → material_id. Hàng MỚI (đề nghị gõ tên tự do) → material_id rỗng + ten_tu_do;
    # kho gắn/tạo mã ở bước lập phiếu (BRD §3.4: chỉ kho khai mã). Đúng 1 trong 2 phải có.
    material_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("materials.id"), index=True, nullable=True
    )
    ten_tu_do: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dvt: Mapped[str] = mapped_column(String(16), nullable=False)
    sl_de_nghi: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("sl_de_nghi > 0"), nullable=False
    )
    sl_duyet: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("sl_duyet >= 0"),
        nullable=False, server_default="0", default=0.0,
    )
    sl_da_ung: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("sl_da_ung >= 0"),
        nullable=False, server_default="0", default=0.0,
    )
    # Đơn giá NHẬP do NGƯỜI ĐỀ NGHỊ khai (chỉ đề nghị NHẬP — họ biết giá NCC). Phiếu KẾ THỪA
    # giá này khi ghi sổ; kho KHÔNG sửa. Null với đề nghị XUẤT (giá = giá vốn đích danh của lô).
    don_gia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Quy đổi đơn vị do NGƯỜI ĐỀ NGHỊ khai (1 don_vi_phu = he_so_quy_doi × dvt tồn). Hàng mới →
    # kho tạo mã kèm quy đổi này; hàng có mã → prefill từ mặt hàng. Kho KHÔNG khai lại ở phiếu.
    don_vi_phu: Mapped[str | None] = mapped_column(String(16), nullable=True)
    he_so_quy_doi: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    # KHO PHẢN HỒI: lý do kho cấp/nhập ÍT HƠN số còn phải cấp (vd NCC giao thiếu). Kho khai lúc
    # lập phiếu khi SL < còn phải cấp; hiện ở mục "Kho phản hồi" của đề nghị.
    ly_do_thieu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    request: Mapped[StockRequest] = relationship("StockRequest", back_populates="lines")
