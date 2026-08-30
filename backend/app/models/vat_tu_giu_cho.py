"""GIỮ CHỖ vật tư — phần tồn kho đã có CHỦ, chưa xuất nhưng không ai khác lấy được.

Chủ dự án chốt 17/08/2026: *lệnh phải giữ được vật tư thì mới được xếp lịch.*

Trước đó bảng cân đối **chỉ đọc** — tồn không thuộc về ai. Hệ quả ngoài đời: lệnh A xếp lịch 22/8
dựa trên 60 kg giấy đang có, chiều hôm sau lệnh B lĩnh mất 50 kg, và lịch của A thành lịch ma mà
không ai báo. Bảng này là chỗ tồn được ĐẶT CHỖ.

## Bốn luật, đừng phá

**① Chủ thể = lệnh HOẶC bài ghép, không bao giờ cả hai.** Trùng luật chủ thể của bảng nhu cầu
(`_gom_nhu_cau`): lệnh đã ghép thì bài đại diện, không đẻ dòng giấy riêng. Giữ chỗ đi theo đúng chủ
đó — một luật, hai chỗ dùng.

**② Giữ theo (mặt hàng, SỐ LƯỢNG), KHÔNG đích danh lô.** Chỉ lô sẽ phá nhập-trước-xuất-trước của
kho: giữ lô cũ cho lệnh chạy tháng sau thì lô đó nằm ì, còn lệnh tuần này phải bóc lô mới. Kho cứ
xuất theo thứ tự của kho; giữ chỗ chỉ ăn vào con số **tồn tự do** = tồn − Σ đã giữ.

**③ Đơn vị là ĐƠN VỊ GỐC của mặt hàng** (`don_vi_gia`) — cùng thang với `stock_lots.sl_con_lai`,
để phép trừ tồn tự do không phải quy đổi lần nữa.

**④ `nguon` phân biệt hàng CÓ THẬT với hàng mới HỨA.**
  · `kho`     — hàng đang nằm trong kho ⇒ lệnh xếp lịch ngày nào cũng được.
  · `dang_ve` — bám vào lô đang mua ⇒ lịch KHÔNG được đặt trước `ngay_ve`.
Nhốt toàn bộ rắc rối về ngày vào đúng một nhánh: hàng đã trong kho thì ngày tháng vô nghĩa, chỉ khi
lập kế hoạch dựa trên thứ CHƯA TỒN TẠI thì ngày về mới thật sự là ràng buộc.

⚠️ `nguồn = dang_ve` mà `ngay_ve` trống thì KHÔNG thành giữ chỗ — hàng không có ngày về thì không
hứa được với lệnh nào cả (cùng luật với `_hang_dang_ve` ở bảng cân đối).

## Công tắc nằm ở đâu

Cờ `lsx.giu_cho_bat` / `bai_ghep.giu_cho_bat`, KHÔNG suy từ "có dòng nào trong bảng này không".
Cần cờ riêng vì trạng thái *"đã bật nhưng chưa giữ được gì"* (kho trống, đang chờ mua) không có
dòng nào để suy ra — mà đó chính là trạng thái phải nhớ, để hàng về thì TỰ NHẶT THÊM chứ không bắt
người dùng quay lại bấm.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Nguồn của phần đang giữ.
NGUON_KHO = "kho"
NGUON_DANG_VE = "dang_ve"
NGUON_GIU_CHO = (NGUON_KHO, NGUON_DANG_VE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VatTuGiuCho(Base):
    """1 dòng = 1 chủ thể giữ N đơn vị gốc của MỘT mặt hàng, từ MỘT nguồn."""

    __tablename__ = "vat_tu_giu_cho"
    __table_args__ = (
        # Đúng MỘT trong hai chủ thể. Cả hai cùng có (hoặc cùng trống) là dòng mồ côi: không tra
        # ngược ra ai đang giữ, mà vẫn trừ vào tồn tự do của mọi người khác.
        CheckConstraint(
            "(lsx_id IS NOT NULL AND bai_ghep_id IS NULL)"
            " OR (lsx_id IS NULL AND bai_ghep_id IS NOT NULL)",
            name="ck_giu_cho_mot_chu_the",
        ),
        CheckConstraint("so_luong > 0", name="ck_giu_cho_so_duong"),
        # Tra "mặt hàng này ai đang giữ, tổng bao nhiêu" — chạy mỗi lần tính tồn tự do.
        Index("ix_giu_cho_hang", "hang_loai", "hang_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cặp trỏ về MẶT HÀNG GỐC — `giay` | `vat_tu`, cùng cặp khoá `stock_lots` và bảng cân đối dùng.
    # Soft-ref (không FK) vì hai danh mục nguồn nằm ở hai bảng khác nhau; service chặn id không có.
    hang_loai: Mapped[str] = mapped_column(String(8), nullable=False)
    hang_id: Mapped[int] = mapped_column(Integer, nullable=False)

    lsx_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lsx.id", ondelete="CASCADE"), index=True, nullable=True
    )
    bai_ghep_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bai_ghep.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # [MỚI 30/08/2026] Dòng PHIẾU MUA (`purchase_request_lines.id`) làm phát sinh phần giữ NÀY —
    # CHỈ có ý nghĩa khi `nguon = dang_ve`. Để `GiuChoService.doi_soat_dang_ve()` tra NGƯỢC lại
    # đúng dòng khi PMH đổi (dời ngày, giảm/huỷ SL, đóng đơn) — không phải đoán theo mặt hàng.
    # SET NULL: xoá dòng phiếu (hiếm) không kéo theo xoá chỗ giữ, chỉ để nó thành "mồ côi" — lần
    # đối soát/`nhat_them()` sau sẽ dọn.
    purchase_request_line_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("purchase_request_lines.id", ondelete="SET NULL"),
        index=True, nullable=True,
    )

    #: Theo ĐƠN VỊ GỐC của mặt hàng — cùng thang `stock_lots.sl_con_lai`, khỏi quy đổi khi trừ.
    so_luong: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    nguon: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=NGUON_KHO, default=NGUON_KHO
    )
    #: CHỈ có nghĩa khi `nguon = dang_ve` — ngày lô đang mua về tới kho. Đây là CHẶN DƯỚI của lịch:
    #: bước tiêu thụ không được xếp trước ngày này.
    ngay_ve: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
