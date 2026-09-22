"""Guard: xóa cứng một tài khoản phải cascade mọi dữ liệu đang tham chiếu tài khoản đó."""
from __future__ import annotations

import app.models  # noqa: F401  -- đăng ký đủ model vào metadata
from app.db import Base


def test_moi_foreign_key_toi_users_deu_on_delete_cascade():
    sai: list[str] = []
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.target_fullname == "users.id" and fk.ondelete != "CASCADE":
                sai.append(f"{table.name}.{fk.parent.name}: {fk.ondelete or 'NO ACTION'}")

    assert not sai, "FK tới users chưa ON DELETE CASCADE:\n  " + "\n  ".join(sorted(sai))
