"""Không file Python nào được định nghĩa TRÙNG TÊN ở cấp module.

⚠️ ĐÃ VỠ THẬT — 12/08/2026, `test_payables_api.py`.

Hai nhánh cùng sửa file đó rồi hoà vào nhau, lần gỡ conflict **dán cả hai bản nối đuôi**:

    bd297e9  1638 dòng · 48 test · 0 trùng · 23 chỗ `coc=`   ← bản MỚI, đúng luật cọc 09/08
    3c30a12  1445 dòng · 43 test · 0 trùng ·  0 chỗ `coc=`   ← bản CŨ
    e64911f  2258 dòng · 70 def  · 24 TRÙNG                  ← hoà xong: dính cả hai

Python im lặng lấy **bản định nghĩa SAU**. Bản sau lại là bản CŨ, nên 24 test mới bị bản cũ đè —
13 cái đỏ ngay, 11 cái còn lại **xanh mà đang kiểm luật đã bị bỏ**, tức là luật mới KHÔNG có ai
canh mà bảng điểm vẫn đẹp. Kiểu hỏng tệ nhất: không nhìn thấy được.

Đọc `pytest -q` cũng không ra: nó đếm 46 test và báo xanh, đúng bằng số TÊN riêng — 24 thân hàm
biến mất không để lại dấu vết nào.

Guard này rẻ (đọc file, không chạy app) và bắt đúng khoảnh khắc dán trùng.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]

#: Bỏ qua thư mục sinh tự động / thư viện ngoài.
BO_QUA = {"__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", "migrations_backup"}

#: `def`/`class` ở CẤP MODULE (không thụt đầu dòng). Method trùng tên giữa các class là bình
#: thường, nên không soi phần thụt lề.
DINH_NGHIA = re.compile(r"^(?:async def|def|class) (\w+)")


def _trung_trong(p: Path) -> dict[str, list[int]]:
    vi_tri: dict[str, list[int]] = collections.defaultdict(list)
    for so, dong in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        m = DINH_NGHIA.match(dong)
        if m:
            vi_tri[m.group(1)].append(so)
    return {k: v for k, v in vi_tri.items() if len(v) > 1}


def _moi_file_python():
    for p in GOC.rglob("*.py"):
        if BO_QUA & set(p.parts):
            continue
        yield p


def test_khong_file_nao_dinh_nghia_trung_ten_o_cap_module():
    loi = []
    for p in _moi_file_python():
        for ten, dong in sorted(_trung_trong(p).items(), key=lambda x: x[1][0]):
            loi.append(f"  {p.relative_to(GOC)}  ·  {ten}  ·  dòng {dong}")
    assert not loi, (
        "Có định nghĩa trùng tên ở cấp module — Python lấy bản CUỐI, các bản trước biến mất im "
        "lặng. Gần như luôn là vết hoà code dán hai bản nối đuôi (xem docstring đầu file).\n"
        + "\n".join(loi)
    )


def test_guard_nay_that_su_doc_duoc_file():
    """Guard quét-file dễ chết thầm: đường dẫn sai ⇒ không đọc file nào ⇒ xanh vĩnh viễn.

    Neo bằng một con số sàn thay vì đếm chính xác (repo còn thêm file mới hoài)."""
    so_file = sum(1 for _ in _moi_file_python())
    assert so_file > 200, f"chỉ quét được {so_file} file — kiểm lại `GOC`"
    assert (GOC / "tests" / "test_payables_api.py") in set(_moi_file_python()), (
        "không thấy chính file từng vỡ — phạm vi quét sai"
    )
