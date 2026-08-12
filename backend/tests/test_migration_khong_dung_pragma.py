"""Guard: migration KHÔNG được hỏi cấu trúc bảng bằng `PRAGMA` ở nhánh chạy cho mọi dialect.

VÌ SAO CÓ FILE NÀY — vỡ thật trên DB dev ngày 11/08/2026:

    psycopg2.errors.SyntaxError: syntax error at or near "PRAGMA"
    ERROR: Application startup failed. Exiting.

Ba migration mới viết theo khuôn "thử PRAGMA trước, không có thì hỏi information_schema":

    cols = [r[1] for r in db.execute(text("PRAGMA table_info(x)")).fetchall()]
    if not cols:  # Postgres
        cols = [...information_schema...]

Khuôn đó SAI: trên Postgres `PRAGMA` KHÔNG trả rỗng mà NÉM SyntaxError, nên dòng dự phòng không
bao giờ chạy tới — app chết ngay lúc khởi động, trước cả khi phục vụ request đầu tiên.

Bộ test chạy SQLite (`conftest.py` ép `sqlite:///:memory:`) nên PRAGMA luôn chạy ngon và 1300 test
vẫn xanh. Đây chính là loại lỗi mà test không bao giờ bắt được — nên phải chặn bằng luật đọc mã.

CÁCH ĐÚNG: `_existing_columns(inspect(db.get_bind()), "ten_bang")` — inspector của SQLAlchemy
dịch sang đúng dialect đang chạy.

PRAGMA vẫn được phép trong nhánh ĐÃ CHẶN dialect (kiểu `if dialect != "sqlite": ... return`), nên
guard này chỉ soi những dòng PRAGMA không có lá chắn đó ở ngay trên.
"""

from __future__ import annotations

import re
from pathlib import Path

NGUON = Path(__file__).resolve().parents[1] / "app" / "db_migrations.py"

# Số dòng ngược lên để tìm lá chắn dialect. Đủ rộng cho khuôn "if dialect == 'sqlite':" hoặc một
# nhánh non-sqlite kết thúc bằng `return` ngay trước đó.
CUA_SO = 25


def test_migration_khong_goi_pragma_o_nhanh_chung():
    noi_dung = NGUON.read_text(encoding="utf-8").splitlines()

    pham = []
    for i, dong in enumerate(noi_dung):
        # Bỏ qua dòng chú thích — file này có sẵn các chú thích nhắc chính chuyện đó.
        if "PRAGMA" not in dong or dong.lstrip().startswith("#"):
            continue
        truoc = "\n".join(noi_dung[max(0, i - CUA_SO):i])
        co_la_chan = bool(
            re.search(r'dialect\s*==\s*["\']sqlite["\']', truoc)
            or re.search(r'dialect\s*!=\s*["\']sqlite["\']', truoc)
            or re.search(r'\.name\s*==\s*["\']sqlite["\']', truoc)
        )
        if not co_la_chan:
            pham.append(f"  dòng {i + 1}: {dong.strip()[:100]}")

    assert not pham, (
        "PRAGMA ở nhánh chạy cho MỌI dialect — sẽ nổ `syntax error at or near \"PRAGMA\"` trên "
        "Postgres và app không khởi động được.\n"
        'Dùng `_existing_columns(inspect(db.get_bind()), "ten_bang")` thay vì PRAGMA.\n'
        + "\n".join(pham)
    )
