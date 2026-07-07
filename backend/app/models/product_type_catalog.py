"""Product Type Catalog model — spec-20/21 + spec page #1 (Loại sản phẩm & Quy tắc tính).

Configures dynamic fields, dimension rules, routing, materials, imposition allowlist and
calculation strategies for product types. Đây là "template nghiệp vụ" điều khiển màn Tính giá:
khi chọn một loại SP, engine/UI đọc cấu hình ở đây để biết hỏi field nào, gợi ý công đoạn nào,
dùng bleed/gutter mặc định nào và đi theo nhánh tính nào.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

# Strategies for calculating prices, validated in service
STRATEGY_SHEET = "sheet_based"
STRATEGY_PAGE = "page_based"
STRATEGY_AREA = "area_based"
STRATEGY_ROLL = "roll_based"
STRATEGY_BOX = "box_based"
STRATEGY_BOOK = "book_based"

CALCULATION_STRATEGIES = (
    STRATEGY_SHEET,
    STRATEGY_PAGE,
    STRATEGY_AREA,
    STRATEGY_ROLL,
    STRATEGY_BOX,
    STRATEGY_BOOK,
)

# spec §A — nhóm sản phẩm
PRODUCT_GROUPS = ("an_pham", "bao_bi", "sach", "nhan", "khac")
# spec §C — kiểu kích thước dùng tính số con
DIMENSION_RULE_TYPES = ("finished", "spread", "multi_page")
# spec §H — cách tính số tờ / mực
SHEET_COUNT_MODES = ("by_pieces", "by_pages", "manual")
INK_COST_MODES = ("per_1000", "coverage")

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class ProductTypeCatalog(Base):
    __tablename__ = "product_types_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # E.g. business_card, brochure, catalogue, book, sticker, label, paper_box, paper_bag, banner, standee
    product_type: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    # #25 — unique ở DB để chặn đua tạo/sửa trùng tên (find_by_name chỉ là kiểm tra đọc-trước-ghi).
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    calculation_strategy: Mapped[str] = mapped_column(String(32), nullable=False)

    # --- §A Thông tin chung ------------------------------------------------
    product_group: Mapped[str] = mapped_column(String(24), nullable=False, server_default="an_pham")
    technology: Mapped[str] = mapped_column(String(20), nullable=False, server_default="offset")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # --- §B Input cần nhập trên màn Tính giá -------------------------------
    # required_fields = tập BẮT BUỘC; shown_fields = tập HIỂN THỊ (superset). Vocab field xem
    # service.VALID_INPUT_FIELDS (finished_w/h/d, spread_w/h, quantity, colors, sides, page_count,
    # signature_count, spine_width, paper, cover_paper, body_paper, machine, sheet_size, imposition, operations).
    required_fields: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    shown_fields: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # --- §C Quy tắc kích thước --------------------------------------------
    dimension_rule_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="finished")
    default_bleed_mm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    default_gutter_mm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    default_trim_mm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    allow_rotation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    allow_custom_size: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # --- §D Số trang / số tay / form --------------------------------------
    has_page_count: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    page_multiple: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")  # 0 = không ràng buộc
    pages_per_signature: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    has_cover_body_split: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # --- §E Vật tư mặc định (ID cụ thể) -----------------------------------
    allowed_materials: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # material TYPE
    default_paper_material_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_cover_material_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_body_material_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_ink_material_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_packaging: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    default_pack_qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # --- §F Routing / công đoạn mặc định ----------------------------------
    # default_operations = danh sách operation_type CÓ THỨ TỰ (thứ tự routing).
    default_operations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    required_operations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allow_extra_operations: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # --- §G Kiểu bình bài được phép ---------------------------------------
    allowed_imposition_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    default_imposition_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allow_imposition_change: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # --- §H Quy tắc tính đặc thù ------------------------------------------
    compatible_technologies: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    sheet_count_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="by_pieces")
    ink_cost_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default="per_1000")
    has_tooling: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    default_tooling_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    allow_manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # --- Bù hao (thay module Định mức cũ) — % áp thẳng vào SỐ TỜ SẢN XUẤT --------
    # Đội giấy + mực + giờ máy (không đội kẽm). VD 5 = +5% số tờ. 0 = không hao.
    waste_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="0", default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
