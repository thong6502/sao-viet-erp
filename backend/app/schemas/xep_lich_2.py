"""Schema I/O màn Xếp lịch 2.

Chỉ khai schema cho phần THÂN yêu cầu (PUT lưu dòng). Các endpoint ĐỌC (hàng chờ · bàn làm việc ·
xem trước · gợi ý · kiểm phát hành) trả thẳng dict service dựng sẵn với `response_model=None` — cấu
trúc lồng/động, ép qua Pydantic Out dễ NUỐT field im lặng (bẫy đã dính nhiều lần), mà đằng nào cũng
là dữ liệu dẫn xuất chỉ để hiển thị.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LuuIn(BaseModel):
    """Ghi một quyết định xếp lịch cho một dòng.

    `expected_updated_at` là MỐC khóa lạc quan: FE gửi lại đúng `updated_at` nó đang cầm; lệch mốc
    ⇒ 409 (ai đó vừa sửa). Các trường còn lại chỉ áp khi có mặt (patch một phần)."""

    model_config = ConfigDict(extra="forbid")

    expected_updated_at: datetime
    may_id: int | None = None
    department_id: int | None = None
    nha_cung_cap: str | None = None
    work_shift_id: int | None = None
    start_at: datetime | None = None


class TachDongIn(BaseModel):
    """Tách một công đoạn thành nhiều LẦN CHẠY (spec-thuc-te-vs-ke-hoach §2.4).

    Client gửi ĐÚNG các con số muốn chia, không gửi "số phần" — chia đều là ca hiếm, xưởng hay
    tách 6.000 máy A + 4.000 máy B. Mọi LUẬT (ít nhất 2 phần · mỗi phần dương · tổng khớp bước)
    nằm ở service, không chép lên đây: một luật hai nơi là hai câu báo lỗi khác nhau cho cùng một
    lỗi. `max_length` chỉ là chặn kích thước thô, không phải luật nghiệp vụ."""

    model_config = ConfigDict(extra="forbid")

    cac_phan: list[float] = Field(..., max_length=50)


class DuyetNgoaiLeIn(BaseModel):
    """Duyệt ngoại lệ TRỄ HẠN SX cho một lệnh/bài (§7.2): CHỈ cần lý do.

    Chỉ dùng cho `tre_han_sx` — trễ hạn hoàn thành SX vẫn cho phát hành khi người có quyền duyệt.
    Ngoại lệ NEO THEO MỐC ĐÃ DUYỆT: hệ thống tự ghi mốc hoàn thành đang có làm ngưỡng, KHÔNG để
    người dùng nhập thời hạn — dời lịch xong muộn hơn mốc thì tự mất hiệu lực, phải duyệt lại."""

    model_config = ConfigDict(extra="forbid")

    ly_do: str = Field(..., min_length=3, max_length=500)


class PhatHanhCapNhatIn(BaseModel):
    """Phát hành cập nhật lịch cho một lệnh/bài (§4.3): tái chụp việc CHƯA bắt đầu theo lịch hiện
    tại, kèm LÝ DO bắt buộc (giữ lịch sử phiên bản). Việc đã bắt đầu giữ nguyên; phân công + hỗ trợ
    của việc được cập nhật bị huỷ để tổ xác nhận lại."""

    model_config = ConfigDict(extra="forbid")

    ly_do: str = Field(..., min_length=3, max_length=500)
