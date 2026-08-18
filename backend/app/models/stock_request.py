"""Yêu cầu kho (nhập / xuất) — docs/spec-kho-de-nghi.md §3–§5.

1 yêu cầu = 1 chứng từ do người NGOÀI kho lập (tổ SX, mua hàng, bảo trì…). Hai luật
xương sống lấy từ BRD Module Kho:

* **Kho KHÔNG duyệt.** Duyệt là việc của tổ trưởng/quản lý bộ phận YÊU CẦU — BRD §2.6
  b8, §2.8 b6, §2.9 b5 đều ghi "Kho tiếp nhận phiếu ĐÃ DUYỆT". Kho chỉ lập phiếu
  nhập/xuất ứng theo yêu cầu đã duyệt.
* **Đã duyệt là khoá.** BRD §1.5: phiếu đã duyệt không sửa trực tiếp; muốn đổi thì hủy
  và tạo lại.

Bảng MỚI → `create_all` tự dựng, không cần migration (migration chỉ để ALTER bảng cũ).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# Loại yêu cầu. Giai đoạn 1 chỉ 2 giá trị; đặc thù nghiệp vụ (cấp bù, bảo trì, nhập trả…)
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
    """Header yêu cầu kho."""

    __tablename__ = "stock_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Số yêu cầu in trên chứng từ (DNN0001 / DNX0001) — sinh qua document_sequences.
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    loai: Mapped[str] = mapped_column(String(8), index=True, nullable=False)

    nguoi_tao_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    # Bộ phận yêu cầu — dùng cho scope `department` và cho ô "Bộ phận" trên bản in.
    bo_phan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=True
    )
    # Kho đích của yêu cầu: XUẤT = lĩnh từ kho nào, NHẬP = nhập về kho nào. Đèn tồn tính theo
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
    # Loại nhập/xuất kho — TỰ DO người tạo gõ ở form yêu cầu (tên hoặc mã, vd "nhập mua" / "2");
    # Báo cáo kho đọc để xuất Excel MISA. Nullable = chưa khai. (mig 0169 thêm INT → 0170 đổi VARCHAR)
    loai_kho: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # NGUỒN: đợt giao đơn mua sinh ra yêu cầu NHẬP này (bấm "Nhập kho" ở đợt giao). Soft ref (không
    # FK — module Mua hàng có thể migrate sau). Dùng để CHẶN nhập kho TRÙNG một đợt: đợt đã có yêu cầu
    # (chưa hủy) trỏ vào thì nút "Nhập kho" đổi thành "Đã nhập kho · Xem". Thêm qua migration 0189.
    purchase_delivery_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # ĐIỀU CHUYỂN KHO (mô hình 2 yêu cầu, mig 0203): ấn điều chuyển sinh CẶP yêu cầu — một XUẤT ở
    # kho nguồn (tự lập + ghi sổ ngay để trừ tồn) và một NHẬP ở kho đích (chờ đích lập phiếu nhận).
    # Cả hai bật `dieu_chuyen=true`. Yêu cầu NHẬP đích còn mang:
    #  · `kho_nguon_id` = kho nguồn (để hiện "Điều chuyển từ «kho nguồn»").
    #  · `xuat_voucher_id` = phiếu XUẤT nguồn đã ghi sổ (soft ref, truy cặp đi–đến).
    #  · dòng yêu cầu `don_gia` = GIÁ VỐN CHỐT từ nguồn → phiếu nhập đích khoá đơn giá theo đây.
    dieu_chuyen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    kho_nguon_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("kho_hang.id"), index=True, nullable=True
    )
    xuat_voucher_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    trang_thai: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False, server_default=REQ_DRAFT, default=REQ_DRAFT
    )
    nguoi_duyet_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    duyet_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ly_do_tu_choi: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Lý do KHO HỦY yêu cầu (hủy phiếu nháp → yêu cầu KẾT THÚC ở 'Đã hủy'). Tách khỏi
    # `ly_do_tu_choi` (lý do NGƯỜI DUYỆT từ chối). Null nếu chưa hủy. Thêm qua migration 0114.
    ly_do_huy: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Người TẠO đã xem QUYẾT ĐỊNH (duyệt/từ chối/kho hủy) tới lúc nào — NULL = chưa xem ⇒ nuôi badge
    # "yêu cầu của tôi vừa được quyết". So `duyet_luc > coalesce(quyet_dinh_xem_luc, epoch)`. Mirror
    # `decision_seen_at` của báo giá/nghỉ phép. Thêm qua migration 0188.
    quyet_dinh_xem_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    """1 dòng vật tư của yêu cầu.

    Bốn con số chạy theo thứ tự `sl_de_nghi → sl_duyet → sl_da_ung`; "còn lại" =
    `sl_duyet - sl_da_ung` (tính, không lưu — lưu thành cột thứ 4 là mời sai lệch).
    Service chặn cứng không cho ứng vượt `sl_duyet` (spec §5).
    """

    __tablename__ = "stock_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # MẶT HÀNG GỐC — bắt buộc, trỏ `giay_nguyen`/`vat_tu_in_an` (mg 0171).
    #
    # Trước đây dòng đề nghị cho gõ TÊN TỰ DO (`ten_tu_do`) rồi kho gắn mã sau. Bỏ hẳn từ
    # 2026-08-08 (chủ chốt "siết"): mọi thứ nhập kho phải có sẵn trong danh mục, vì hàng gõ tay là
    # nguồn đẻ ra mã trùng/tên lệch, mà đúng thứ đó làm MRP không nối được kho với mua hàng.
    hang_loai: Mapped[str] = mapped_column(String(8), nullable=False)
    hang_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # XIN CHO LỆNH NÀO (mg 0175) — soft ref `lsx.id` / `bai_ghep.id`, CẢ HAI để trống là hợp lệ
    # (xin lặt vặt: băng dính, giẻ lau). Bảng cân đối vật tư đọc hai cột này để trừ phần "đã cấp"
    # vào ĐÚNG dòng nhu cầu; không có nó thì kho cấp cho lệnh A mà mọi lệnh dùng chung loại giấy
    # đều tiếp tục hiện "còn thiếu".
    lsx_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    bai_ghep_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Đơn vị NGƯỜI ĐỀ NGHỊ chọn — phải nằm trong tập đổi được của mặt hàng
    # (`quy_doi_service.don_vi_dung_duoc`). Số lượng lưu THEO ĐƠN VỊ NÀY; quy về đơn vị gốc chỉ
    # xảy ra lúc ghi sổ, để phiếu in ra vẫn đúng con số người ta đề nghị.
    dvt: Mapped[str] = mapped_column(String(24), nullable=False)
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
    # Đơn giá NHẬP do NGƯỜI YÊU CẦU khai (chỉ yêu cầu NHẬP — họ biết giá NCC). Phiếu KẾ THỪA
    # giá này khi ghi sổ; kho KHÔNG sửa. Null với yêu cầu XUẤT (giá = giá vốn đích danh của lô).
    don_gia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # GỠ mg 0171: `don_vi_phu` + `he_so_quy_doi` — người đề nghị tự khai hệ số quy đổi cho từng
    # dòng. Nay quy đổi lấy từ đồ thị đơn vị dùng chung (`don_vi_quy_doi` + quy cách đóng gói của
    # mặt hàng), nên khai tay ở đây chỉ tạo ra nguồn số thứ hai — mà hai nguồn thì sớm muộn lệch,
    # và lệch ở đây là lệch TỒN KHO.
    # KHO PHẢN HỒI: lý do kho cấp/nhập ÍT HƠN số còn phải cấp (vd NCC giao thiếu). Kho khai lúc
    # lập phiếu khi SL < còn phải cấp; hiện ở mục "Kho phản hồi" của yêu cầu.
    ly_do_thieu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    request: Mapped[StockRequest] = relationship("StockRequest", back_populates="lines")
