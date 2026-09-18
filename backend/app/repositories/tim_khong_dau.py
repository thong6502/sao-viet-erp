"""Tìm kiếm TƯƠNG ĐỐI — bỏ dấu tiếng Việt ở CẢ HAI phía (ô tìm và cột trong DB).

Chủ xưởng 18/09/2026: *"phải cho tìm kiếm tương đối nữa"* — gõ `can mang` phải ra "Cán màng",
gõ `Ép Kim` phải ra "ép kim". Ô tìm của nền danh mục (`catalog_base._loc_q`) chỉ `lower().like()`
nên khớp chữ-có-dấu với chữ-có-dấu, người khai gõ không dấu là ra rỗng.

Bỏ dấu phía DB làm bằng REPLACE lồng thay vì `unaccent` của Postgres: `unaccent` là EXTENSION,
phải `CREATE EXTENSION` trên từng database (dev, CI, prod) — một câu SQL ngoài `db_migrations.py`
mà quên ở đâu là màn đó ăn 500. REPLACE lồng chạy y hệt trên SQLite (bộ test) và Postgres, không
cài gì. Chỉ dựng khi ô tìm CÓ chữ, nên bảng nào không ai tìm thì không phải trả giá.

Chỉ cần bảng chữ THƯỜNG: cả hai phía đã `lower()` trước khi thay.
"""
from __future__ import annotations

import unicodedata

from sqlalchemy import func

#: `{chữ có dấu: chữ trần}` — đủ 67 nguyên âm tiếng Việt + `đ`. Dựng bằng NFD cho khỏi gõ tay sai.
_NGUON = (
    "àảãáạăằẳẵắặâầẩẫấậ"
    "èẻẽéẹêềểễếệ"
    "ìỉĩíị"
    "òỏõóọôồổỗốộơờởỡớợ"
    "ùủũúụưừửữứự"
    "ỳỷỹýỵ"
)


def _tran(ch: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")


#: Xếp theo chữ ĐÍCH để REPLACE lồng gom được: mọi `a` có dấu thay về `a` trong cùng một mạch.
BANG: dict[str, str] = {ch: _tran(ch) for ch in _NGUON}
BANG["đ"] = "d"


def bo_dau(s: str | None) -> str:
    """Bỏ dấu + hạ chữ THƯỜNG phía Python — dùng cho ô tìm, và cho những danh sách nhỏ lọc ngay
    trong bộ nhớ (danh sách việc khoán của một tổ ở bàn tổ) thay vì đi thêm một vòng SQL."""
    return "".join(BANG.get(c, c) for c in (s or "").strip().lower())


def bo_dau_sql(col):
    """Biểu thức SQL `bỏ_dấu(lower(col))` — lồng REPLACE, chạy cả SQLite lẫn Postgres."""
    bieu_thuc = func.lower(col)
    for co_dau, tran in BANG.items():
        bieu_thuc = func.replace(bieu_thuc, co_dau, tran)
    return bieu_thuc


def like_khong_dau(col, q: str | None):
    """Điều kiện `col` KHỚP TƯƠNG ĐỐI `q` (chứa, không phân biệt dấu/hoa-thường). `None` khi ô
    tìm trống — chỗ gọi tự hiểu là "không lọc gì"."""
    kim = bo_dau(q)
    if not kim:
        return None
    return bo_dau_sql(col).like(f"%{kim}%")
