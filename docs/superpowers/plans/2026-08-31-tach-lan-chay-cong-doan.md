# Tách lần chạy công đoạn — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một công đoạn xếp được thành nhiều lần chạy (10.000 tờ = 6.000 hôm nay máy A + 4.000 mai máy B), thời lượng chia đúng tỉ lệ, và khi phát hành thì mỗi phân đoạn thành một công việc riêng cho tổ.

**Architecture:** `xep_lich_cong_doan` mọc thêm chiều SỐ LƯỢNG (`so_luong`, `phan_doan_so`, `phan_doan_tong`, `goc_dong_id`). Tách = nhân bản dòng gốc thành N dòng cùng neo `lsx_cong_doan_id`, chia số lượng; engine thời lượng nhân tỉ lệ qua tham số `sl_tinh` vốn đã có. Phát hành đẻ một `SanXuatCongViec` cho mỗi phân đoạn; `cv_by_step` đổi từ `dict[str, cv]` sang `dict[str, list[cv]]` và chuỗi phụ thuộc nối theo phân đoạn.

**Tech Stack:** FastAPI + SQLAlchemy 2 (Postgres dev/prod, SQLite in-memory cho test) · React 18 + TypeScript + Vite · pytest.

**Spec:** `docs/spec-thuc-te-vs-ke-hoach.md` §1.3 và §2.4. Nền: `docs/spec-xep-lich-2.md`, `docs/spec-thuc-hien-san-xuat.md`.

## Global Constraints

- Ngôn ngữ code/comment/chuỗi UI: **tiếng Việt** (thuật ngữ kỹ thuật giữ tiếng Anh).
- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, không ALTER. Mọi cột mới **bắt buộc** viết vào `backend/app/db_migrations.py`, nếu không DB dev/prod không nhận. Dev cũng là Postgres — không phải file SQLite xoá là xong.
- Cột Boolean: `server_default` phải là `false()`/`true()` của SQLAlchemy, **không** phải `"0"`/`"1"` (chuỗi chạy SQLite nhưng VỠ khi Postgres `create_all` trên DB trắng). Plan này không thêm Boolean nào, nhưng nhớ luật.
- `docs/DB_SCHEMA.md` có guard test: **mọi cột mới phải ghi vào đó cùng lúc**, không thì `init` FAIL.
- Migration **cấm ORM full-select** để backfill — dùng raw SQL đích danh cột; ORM full-select kéo cả cột do migration SAU thêm ⇒ vỡ deploy trên DB trung gian.
- `step_key` là hợp đồng sống còn của `PUT /routing` — **không đổi ý nghĩa `step_key`**. Phân đoạn phân biệt bằng `phan_doan_so`, không bằng `step_key` mới.
- Tổng số lượng các phân đoạn phải **luôn** bằng số lượng dòng gốc. Bất biến này kiểm ở service, có test riêng.
- Verify: `pytest` nhắm đúng file test đã đổi + `npx tsc --noEmit` trong `frontend/`. **Đừng chạy `./init.ps1`**; đừng chạy cả bộ test nếu chưa được yêu cầu.
- Sửa route/schema backend ⇒ **restart uvicorn**.
- **Không commit hoặc push nếu chưa được yêu cầu.**


> **SỐ MIGRATION — KIỂM TRƯỚC KHI GHI.** Đang có nhiều plan chưa thi công cùng đặt trước dãy số này
> (`docs/superpowers/plans/2026-08-31-lenh-sx-va-theo-doi-sx.md` giữ `0246`–`0248`,
> `2026-08-31-tach-lan-chay-cong-doan.md` giữ `0247`,
> `2026-08-31-de-nghi-cap-vat-tu-cong-doan.md` giữ `0246`). Ngay trước khi viết migration, chạy
> `tail -40 backend/app/db_migrations.py | grep MIGRATIONS.append` để lấy số CAO NHẤT đang có thật
> rồi dùng số kế tiếp, và sửa lại mọi chỗ nhắc số cũ trong plan này (bảng File Structure, khối
> Interfaces, test `test_migration_*`, bước restart uvicorn). Trùng số = hai migration khác nội
> dung mang cùng id, DB nào chạy trước thì migration kia im lặng không chạy — vỡ đúng ở prod.


---

## File Structure

**Pha 1 — kế hoạch tách được (Task 1–5)**

| File | Trách nhiệm |
| --- | --- |
| `backend/app/models/xep_lich.py` | **Sửa.** 4 cột mới trên `XepLichCongDoan`. |
| `backend/app/db_migrations.py` | **Sửa.** Migration `0247_xep_lich_phan_doan` — ALTER + backfill. |
| `docs/DB_SCHEMA.md` | **Sửa.** 4 dòng mới trong bảng `xep_lich_cong_doan`. |
| `backend/app/services/xep_lich_2/phan_doan.py` | **Tạo.** Toàn bộ luật tách/gộp. Không HTTP, không Gantt. |
| `backend/app/services/xep_lich_service.py` | **Sửa.** `_sl_tinh` nhận tỉ lệ phân đoạn. |
| `backend/app/routers/xep_lich_2.py` | **Sửa.** 2 route mới `tach` / `gop`. |
| `frontend/src/api/client.ts` | **Sửa.** Trường phân đoạn trên `Xl2Dong` + 2 hàm gọi API. |
| `frontend/src/pages/XepLich2Page.tsx` | **Sửa.** Nút Tách / Gộp trong panel dòng. |
| `frontend/src/pages/Xl2Gantt.tsx` | **Sửa.** Nhãn `2/3` + số lượng trên thanh. |
| `backend/tests/test_xep_lich_phan_doan.py` | **Tạo.** Luật tách/gộp + thời lượng tỉ lệ. |

**Pha 2 — phát hành nhiều phân đoạn (Task 6–8)**

| File | Trách nhiệm |
| --- | --- |
| `backend/app/repositories/san_xuat_repo.py` | **Sửa.** `thoi_gian_lsx_step` / `thoi_gian_bg_step` trả DANH SÁCH. |
| `backend/app/services/san_xuat/snapshot.py` | **Sửa.** `dung_cong_viec` đẻ 1 công việc / phân đoạn; `cv_by_step` thành `dict[str, list]`; `dung_phu_thuoc` nối chuỗi trong-phân-đoạn. |
| `backend/tests/test_san_xuat_release_phan_doan.py` | **Tạo.** Phát hành lệnh có phân đoạn. |

---

# PHA 1 — Kế hoạch tách được

### Task 1: Bốn cột phân đoạn trên `xep_lich_cong_doan`

**Files:**
- Modify: `backend/app/models/xep_lich.py` (sau `loai_buoc`, ~dòng 86)
- Modify: `backend/app/db_migrations.py` (cuối file)
- Modify: `docs/DB_SCHEMA.md` (bảng `xep_lich_cong_doan`, ~dòng 4205)
- Test: `backend/tests/test_xep_lich_phan_doan.py`

**Interfaces:**
- Produces: `XepLichCongDoan.so_luong: float | None`, `.phan_doan_so: int`, `.phan_doan_tong: int`, `.goc_dong_id: int | None`. Migration id `0247_xep_lich_phan_doan`.

- [ ] **Step 1: Viết test thất bại trước**

Tạo `backend/tests/test_xep_lich_phan_doan.py`:

```python
"""Tách lần chạy công đoạn (docs/spec-thuc-te-vs-ke-hoach.md §1.3, §2.4).

Bất biến xương sống của cả file: TỔNG số lượng các phân đoạn LUÔN bằng số lượng dòng gốc. Mọi
đường vào (tách, tách tiếp, gộp) đều phải giữ nó — lệch một tờ ở đây là lệch cả bảng cân đối vật
tư lẫn định mức khoán.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.xep_lich import NGUON_LSX, TT_CHO_XEP, XepLichCongDoan

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def test_dong_moi_mac_dinh_la_mot_phan_doan_duy_nhat(db):
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=1, source_thu_tu=0,
                        loai_buoc="may", trang_thai=TT_CHO_XEP)
    db.add(d)
    db.commit()
    db.refresh(d)
    assert d.phan_doan_so == 1
    assert d.phan_doan_tong == 1
    assert d.goc_dong_id is None
    assert d.so_luong is None      # None = "cả bước", KHÁC hẳn với 0


def test_migration_0247_co_trong_danh_sach():
    from app.db_migrations import MIGRATIONS
    assert any(ma == "0247_xep_lich_phan_doan" for ma, _fn in MIGRATIONS)
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py -q
```

Kỳ vọng: FAIL — `AttributeError: 'XepLichCongDoan' object has no attribute 'phan_doan_so'`.

- [ ] **Step 3: Thêm cột vào model**

Trong `backend/app/models/xep_lich.py`, ngay sau `loai_buoc`:

```python
    # --- PHÂN ĐOẠN: một công đoạn chạy làm nhiều lần (spec-thuc-te-vs-ke-hoach §2.4) ---
    # `so_luong` = phần việc của CHÍNH dòng này, theo đơn vị vào của bước. NULL = dòng chưa tách,
    # mang trọn số lượng của bước — KHÁC hẳn 0 ("không chạy gì"), nên đừng backfill về 0.
    so_luong: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    # 1..N. Dòng chưa tách là 1/1. Phân biệt phân đoạn bằng HAI số này, KHÔNG bằng `step_key`:
    # `step_key` là hợp đồng của `PUT /routing`, đổi nghĩa nó là vỡ cả đường phát hành.
    phan_doan_so: Mapped[int] = mapped_column(Integer, nullable=False,
                                              server_default="1", default=1)
    phan_doan_tong: Mapped[int] = mapped_column(Integer, nullable=False,
                                                server_default="1", default=1)
    # Dòng gốc mà phân đoạn này tách ra. Phân đoạn ĐẦU giữ id gốc và có `goc_dong_id = NULL`;
    # các phân đoạn sau trỏ về nó. Gộp = xoá các dòng trỏ về, trả phân đoạn đầu về 1/1.
    goc_dong_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
```

Bổ sung `Numeric` vào import `sqlalchemy` ở đầu file nếu chưa có.

- [ ] **Step 4: Viết migration 0247**

Cuối `backend/app/db_migrations.py`:

```python
def _migrate_xep_lich_phan_doan(db: Session) -> None:
    """`xep_lich_cong_doan`: 4 cột cho phép TÁCH một công đoạn thành nhiều lần chạy.

    Bảng này vốn không có chiều số lượng — một công đoạn = một thanh = một khoảng giờ = một máy,
    nên không cách nào diễn đạt "in 10.000 tờ: 6.000 máy A hôm nay, 4.000 máy B ngày mai"
    (spec-thuc-te-vs-ke-hoach §1.3).

    Hàng CŨ giữ `so_luong = NULL` (nghĩa: trọn bước) và `1/1`. KHÔNG backfill `so_luong` bằng số
    thật của bước: số đó tính lúc đọc từ routing + quy cách, viết cứng vào đây là đẻ nguồn số thứ
    hai, và hai nguồn thì sớm muộn lệch.

    Không dùng ORM ở đây — full-select sẽ kéo cả cột do migration SAU thêm và vỡ trên DB trung gian.
    """
    insp = inspect(db.get_bind())
    if "xep_lich_cong_doan" not in set(insp.get_table_names()):
        return
    co = _existing_columns(insp, "xep_lich_cong_doan")
    if "so_luong" not in co:
        db.execute(text(
            "ALTER TABLE xep_lich_cong_doan ADD COLUMN so_luong NUMERIC(18,3)"))
    if "phan_doan_so" not in co:
        db.execute(text(
            "ALTER TABLE xep_lich_cong_doan ADD COLUMN phan_doan_so INTEGER NOT NULL DEFAULT 1"))
    if "phan_doan_tong" not in co:
        db.execute(text(
            "ALTER TABLE xep_lich_cong_doan ADD COLUMN phan_doan_tong INTEGER NOT NULL DEFAULT 1"))
    if "goc_dong_id" not in co:
        db.execute(text(
            "ALTER TABLE xep_lich_cong_doan ADD COLUMN goc_dong_id INTEGER"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_xep_lich_cong_doan_goc_dong_id "
            "ON xep_lich_cong_doan (goc_dong_id)"))
    db.commit()


MIGRATIONS.append(("0247_xep_lich_phan_doan", _migrate_xep_lich_phan_doan))
```

- [ ] **Step 5: Ghi vào `docs/DB_SCHEMA.md`**

Trong bảng `xep_lich_cong_doan`, thêm 4 dòng ngay sau `loai_buoc`:

```markdown
| `so_luong` | `Numeric(18,3)` → `NUMERIC` | — | yes | — | Phần việc của CHÍNH dòng này (đơn vị vào của bước) khi công đoạn bị TÁCH thành nhiều lần chạy. NULL = chưa tách, dòng mang trọn số lượng bước — KHÁC hẳn 0. |
| `phan_doan_so` | `Integer` | — | no | `1` | Thứ tự phân đoạn 1..N. Dòng chưa tách = 1. |
| `phan_doan_tong` | `Integer` | — | no | `1` | Tổng số phân đoạn của công đoạn. Dòng chưa tách = 1. |
| `goc_dong_id` | `Integer` | IX | yes | — | Dòng gốc đã tách ra dòng này. Phân đoạn ĐẦU giữ id gốc + NULL ở đây; các phân đoạn sau trỏ về nó. Thêm qua migration `0247`. |
```

Đồng thời sửa câu **Purpose** của bảng: bỏ mệnh đề "Bảng mới → `create_all` tự tạo (không migration)" thành "…; từ `0247` có thêm cột nên **có** migration."

- [ ] **Step 6: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py tests/test_xep_lich_2_migration.py -q
```

Kỳ vọng: pass. Nếu guard `DB_SCHEMA` đỏ thì Step 5 chưa đủ — đọc thông báo, nó nêu đích danh cột thiếu.

- [ ] **Step 7: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/models/xep_lich.py backend/app/db_migrations.py docs/DB_SCHEMA.md backend/tests/test_xep_lich_phan_doan.py
git commit -m "Xếp lịch: thêm chiều phân đoạn cho xep_lich_cong_doan (mg 0247)"
```

---

### Task 2: Luật tách và gộp

**Files:**
- Create: `backend/app/services/xep_lich_2/phan_doan.py`
- Test: `backend/tests/test_xep_lich_phan_doan.py` (thêm)

**Interfaces:**
- Consumes: `XepLichCongDoan` (4 cột Task 1), `app.services.xep_lich_2.XepLich2Error`.
- Produces:
  ```python
  def tach(db, *, dong_id: int, cac_phan: list[float], tong_bước: float | None = None) -> list[XepLichCongDoan]
  def gop(db, *, dong_id: int) -> XepLichCongDoan
  def cac_phan_doan(db, dong: XepLichCongDoan) -> list[XepLichCongDoan]
  def ty_le(dong: XepLichCongDoan) -> float          # phần việc của dòng / cả bước, 0<x<=1
  ```

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào `backend/tests/test_xep_lich_phan_doan.py`:

```python
def _dong_goc(db, tong=10000.0) -> XepLichCongDoan:
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_id=None, lsx_cong_doan_id=77, source_thu_tu=0,
                        loai_buoc="may", trang_thai=TT_CHO_XEP,
                        start_at=_T0, finish_at=_T0 + timedelta(hours=5), so_luong=tong)
    db.add(d)
    db.commit()
    return d


def test_tach_hai_phan_giu_tong_va_danh_so(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])

    assert [float(d.so_luong) for d in ra] == [6000.0, 4000.0]
    assert [d.phan_doan_so for d in ra] == [1, 2]
    assert {d.phan_doan_tong for d in ra} == {2}
    assert ra[0].id == g.id                 # phân đoạn ĐẦU giữ id gốc → không mất neo ngoài
    assert ra[0].goc_dong_id is None
    assert ra[1].goc_dong_id == g.id
    assert sum(float(d.so_luong) for d in ra) == 10000.0


def test_tach_giu_nguyen_neo_cong_doan_va_khong_dong_step_key(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[5000, 5000])
    assert {d.lsx_cong_doan_id for d in ra} == {77}
    assert {d.source_thu_tu for d in ra} == {0}


def test_phan_doan_sau_khong_thua_ke_gio_cua_goc(db):
    """Tách xong, phân đoạn 2 trở đi phải CHỜ XẾP — thừa kế giờ của gốc là tự nhân đôi chỗ máy."""
    from app.models.xep_lich import TT_CHO_XEP as _CHO
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    assert ra[1].start_at is None and ra[1].finish_at is None
    assert ra[1].trang_thai == _CHO


def test_tach_lech_tong_thi_chan(db):
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    with pytest.raises(XepLich2Error) as e:
        P.tach(db, dong_id=g.id, cac_phan=[6000, 3000])
    assert "tổng" in str(e.value).lower()


def test_tach_phai_it_nhat_hai_phan_va_moi_phan_duong(db):
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    with pytest.raises(XepLich2Error):
        P.tach(db, dong_id=g.id, cac_phan=[10000])
    with pytest.raises(XepLich2Error):
        P.tach(db, dong_id=g.id, cac_phan=[10000, 0])


def test_tach_dong_da_khoa_thi_chan(db):
    from app.services.xep_lich_2 import XepLich2Error
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    g.is_locked = True
    db.commit()
    with pytest.raises(XepLich2Error) as e:
        P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    assert "khóa" in str(e.value).lower()


def test_gop_tra_ve_mot_dong_giu_tong(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    P.tach(db, dong_id=g.id, cac_phan=[6000, 3000, 1000])
    lai = P.gop(db, dong_id=g.id)
    assert lai.id == g.id
    assert float(lai.so_luong) == 10000.0
    assert lai.phan_doan_so == 1 and lai.phan_doan_tong == 1
    assert P.cac_phan_doan(db, lai) == [lai]


def test_ty_le_dung_cho_ca_dong_chua_tach(db):
    from app.services.xep_lich_2 import phan_doan as P

    g = _dong_goc(db)
    assert P.ty_le(g) == 1.0
    ra = P.tach(db, dong_id=g.id, cac_phan=[6000, 4000])
    assert P.ty_le(ra[0]) == pytest.approx(0.6)
    assert P.ty_le(ra[1]) == pytest.approx(0.4)
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'phan_doan'`.

- [ ] **Step 3: Viết `phan_doan.py`**

```python
"""Tách một công đoạn thành nhiều LẦN CHẠY (spec-thuc-te-vs-ke-hoach §2.4).

Xưởng vẫn chạy như vậy từ lâu — tầng thực thi đã cho nhiều `SanXuatBatch` cho một công việc — chỉ
tầng KẾ HOẠCH là chưa diễn đạt được. Module này thêm đúng chuyện đó và KHÔNG hơn: nó chia số
lượng và đánh số phân đoạn, còn xếp giờ/gán máy vẫn là việc của `service.py` như mọi dòng khác.

Ba luật xương sống:
1. **Tổng bất biến.** Σ `so_luong` các phân đoạn == số lượng dòng gốc. Lệch một tờ là lệch bảng
   cân đối vật tư lẫn định mức khoán.
2. **Phân đoạn đầu GIỮ id gốc.** Mọi thứ đang neo vào dòng đó (audit, vấn đề đang mở theo
   `issue_key`, dòng đã phát hành) không bị mất neo khi người ta bấm tách.
3. **Phân đoạn sau về CHỜ XẾP.** Thừa kế giờ của gốc là tự đặt hai lần chỗ trên cùng một máy —
   đúng thứ mà bộ dò `trung_may` sẽ la lên ngay sau đó.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.xep_lich import TT_CHO_XEP, XepLichCongDoan
from . import XepLich2Error

_EPS = 0.0005   # cùng dung sai làm tròn với `san_luong.tao_batch`


def cac_phan_doan(db: Session, dong: XepLichCongDoan) -> list[XepLichCongDoan]:
    """Mọi phân đoạn cùng gốc với `dong`, sắp theo `phan_doan_so`. Dòng chưa tách trả [chính nó]."""
    goc_id = dong.goc_dong_id or dong.id
    ra = list(db.scalars(
        select(XepLichCongDoan)
        .where((XepLichCongDoan.id == goc_id) | (XepLichCongDoan.goc_dong_id == goc_id))
        .order_by(XepLichCongDoan.phan_doan_so, XepLichCongDoan.id)
    ))
    return ra or [dong]


def ty_le(dong: XepLichCongDoan) -> float:
    """Phần việc của dòng / cả bước — nhân vào `sl_tinh` để ra thời lượng của riêng phân đoạn.

    Dòng chưa tách (`phan_doan_tong == 1`) luôn là 1.0, kể cả khi `so_luong` NULL: NULL nghĩa là
    "trọn bước", không phải "không biết".
    """
    if dong.phan_doan_tong <= 1 or dong.so_luong is None:
        return 1.0
    tong = float(dong.so_luong or 0)
    # Tổng của cả cụm phải lấy từ chính cụm — không suy từ `phan_doan_tong` (các phần không đều).
    return tong  # bên gọi chia cho tổng cụm; xem `ty_le_trong_cum`


def ty_le_trong_cum(dong: XepLichCongDoan, cum: list[XepLichCongDoan]) -> float:
    tong_cum = sum(float(d.so_luong or 0) for d in cum)
    if tong_cum <= 0:
        return 1.0
    return float(dong.so_luong or 0) / tong_cum


def tach(db: Session, *, dong_id: int, cac_phan: list[float]) -> list[XepLichCongDoan]:
    """Tách `dong_id` thành `len(cac_phan)` phân đoạn theo đúng các con số đã cho."""
    goc = db.get(XepLichCongDoan, dong_id)
    if goc is None:
        raise XepLich2Error("Không tìm thấy dòng lịch.")
    if goc.is_locked:
        raise XepLich2Error("Dòng đang khóa — mở khóa trước khi tách lần chạy.")
    if goc.phan_doan_tong > 1:
        raise XepLich2Error("Dòng đã tách rồi — gộp lại trước khi chia kiểu khác.")
    if len(cac_phan) < 2:
        raise XepLich2Error("Tách phải có ít nhất 2 phần.")
    if any(float(p) <= 0 for p in cac_phan):
        raise XepLich2Error("Mỗi phần phải lớn hơn 0.")
    if goc.so_luong is None:
        raise XepLich2Error(
            "Bước chưa biết số lượng nên chưa chia được — kiểm quy cách lệnh trước.")
    tong = float(goc.so_luong)
    if abs(sum(float(p) for p in cac_phan) - tong) > _EPS:
        raise XepLich2Error(f"Tổng các phần phải bằng {tong:g}.")

    n = len(cac_phan)
    goc.so_luong = float(cac_phan[0])
    goc.phan_doan_so = 1
    goc.phan_doan_tong = n
    goc.goc_dong_id = None
    ra = [goc]
    for i, phan in enumerate(cac_phan[1:], start=2):
        moi = XepLichCongDoan(
            nguon=goc.nguon, lsx_id=goc.lsx_id, lsx_cong_doan_id=goc.lsx_cong_doan_id,
            bai_ghep_id=goc.bai_ghep_id, bai_ghep_cong_doan_id=goc.bai_ghep_cong_doan_id,
            source_thu_tu=goc.source_thu_tu, loai_buoc=goc.loai_buoc,
            # Máy/tổ/NCC thừa kế làm GỢI Ý (người kế hoạch hay chạy tiếp trên cùng máy), nhưng
            # GIỜ thì không — hai phân đoạn cùng giờ cùng máy là xung đột dựng sẵn.
            may_id=goc.may_id, department_id=goc.department_id, nha_cung_cap=goc.nha_cung_cap,
            work_shift_id=goc.work_shift_id,
            start_at=None, finish_at=None, trang_thai=TT_CHO_XEP,
            so_luong=float(phan), phan_doan_so=i, phan_doan_tong=n, goc_dong_id=goc.id,
            created_by=goc.created_by,
        )
        db.add(moi)
        ra.append(moi)
    db.flush()
    db.commit()
    return ra


def gop(db: Session, *, dong_id: int) -> XepLichCongDoan:
    """Gộp cả cụm phân đoạn về lại MỘT dòng — dòng gốc, giữ nguyên id và tổng số lượng."""
    dong = db.get(XepLichCongDoan, dong_id)
    if dong is None:
        raise XepLich2Error("Không tìm thấy dòng lịch.")
    cum = cac_phan_doan(db, dong)
    if len(cum) <= 1:
        return dong
    if any(d.is_locked for d in cum):
        raise XepLich2Error("Có phân đoạn đang khóa — mở khóa trước khi gộp.")
    goc = cum[0]
    goc.so_luong = sum(float(d.so_luong or 0) for d in cum)
    goc.phan_doan_so = 1
    goc.phan_doan_tong = 1
    goc.goc_dong_id = None
    for d in cum[1:]:
        db.delete(d)
    db.flush()
    db.commit()
    return goc
```

> Bỏ hàm `ty_le` một-tham-số nếu nó gây nhầm: chỉ giữ `ty_le_trong_cum`. Test ở Step 1 gọi
> `P.ty_le(dong)` — sửa test thành `P.ty_le_trong_cum(dong, P.cac_phan_doan(db, dong))` để chỉ
> còn MỘT đường tính tỉ lệ. Hai hàm cùng nghĩa là mời lệch.

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py -q
```

Kỳ vọng: pass hết (9 test).

- [ ] **Step 5: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/xep_lich_2/phan_doan.py backend/tests/test_xep_lich_phan_doan.py
git commit -m "Xếp lịch 2: luật tách và gộp lần chạy công đoạn"
```

---

### Task 3: Thời lượng chia đúng tỉ lệ phân đoạn

**Files:**
- Modify: `backend/app/services/xep_lich_service.py` (`_sl_tinh` ~dòng 918, chỗ gọi ~dòng 945)
- Test: `backend/tests/test_xep_lich_phan_doan.py` (thêm)

**Interfaces:**
- Consumes: `phan_doan.cac_phan_doan`, `phan_doan.ty_le_trong_cum` (Task 2); `LsxService.sl_tinh_cua_buoc(cd, may, quy_cach) -> tuple[float, str, str] | None`.
- Produces: `_sl_tinh(self, lcd, may, *, dong=None)` — khi `dong` là phân đoạn, phần tử đầu của tuple được nhân tỉ lệ.

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào `backend/tests/test_xep_lich_phan_doan.py`:

```python
def test_sl_tinh_nhan_ty_le_phan_doan():
    """Phân đoạn 60% thì SL đưa vào engine thời lượng cũng phải là 60% — không đụng công thức.

    Soi ở mức HÀM: dựng lệnh thật chỉ để nhân một số là phí, mà chỗ dễ sai lại đúng là phép nhân
    này (nhân vào `chiem_may_phut` sau khi tính sẽ nhân CẢ thời gian chuẩn bị máy — sai hẳn:
    chuẩn bị máy KHÔNG chia theo sản lượng, mỗi lần chạy đều phải canh lại).
    """
    from app.services.xep_lich_service import _nhan_sl_tinh

    assert _nhan_sl_tinh((10000.0, "tờ", "10.000 tờ"), 0.6) == (6000.0, "tờ", "10.000 tờ")
    assert _nhan_sl_tinh(None, 0.6) is None
    assert _nhan_sl_tinh((10000.0, "tờ", ""), 1.0) == (10000.0, "tờ", "")
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py::test_sl_tinh_nhan_ty_le_phan_doan -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name '_nhan_sl_tinh'`.

- [ ] **Step 3: Cài đặt**

Trong `backend/app/services/xep_lich_service.py`, thêm hàm module-level cạnh `_dur_0`:

```python
def _nhan_sl_tinh(sl_tinh, ty_le: float):
    """Nhân SL vào của bước với tỉ lệ phân đoạn, GIỮ nguyên đơn vị và diễn giải quy đổi.

    Nhân ở ĐẦU VÀO chứ không nhân vào kết quả: `thoi_luong_buoc` cộng `chuẩn bị máy` vào thời
    lượng, mà chuẩn bị máy KHÔNG chia theo sản lượng — mỗi lần chạy vẫn phải canh lại từ đầu.
    Nhân vào `chiem_may_phut` sau khi tính là chia luôn cả phần canh máy: bước tách đôi sẽ hiện ra
    như thể canh máy hai lần chỉ mất bằng một lần.
    """
    if sl_tinh is None or ty_le == 1.0:
        return sl_tinh
    vao, dv, dien_giai = sl_tinh
    return (float(vao) * ty_le, dv, dien_giai)
```

Đổi `_sl_tinh` để nhận dòng lịch:

```python
    def _sl_tinh(self, lcd, may, *, dong=None):
        ...
        goc = self.bg_svc._lsx_svc().sl_tinh_cua_buoc(lcd, may, qc)
        if dong is None or getattr(dong, "phan_doan_tong", 1) <= 1:
            return goc
        from .xep_lich_2.phan_doan import cac_phan_doan, ty_le_trong_cum

        cum = cac_phan_doan(self.db, dong)
        return _nhan_sl_tinh(goc, ty_le_trong_cum(dong, cum))
```

Ở chỗ gọi (`thoi_luong_buoc(lcd, may, self._sl_tinh(lcd, may))`, ~dòng 945) truyền thêm dòng đang
xét: `self._sl_tinh(lcd, may, dong=r)` — tên biến dòng lịch trong hàm đó là gì thì dùng đúng tên
đó (kiểm bằng `sed -n '935,950p' backend/app/services/xep_lich_service.py`).

Làm y hệt ở `backend/app/services/xep_lich_2/auto.py:74`:
`thoi_luong_buoc(lcd, may, service.core._sl_tinh(lcd, may, dong=dong))`.

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py tests/test_xep_lich_2.py tests/test_xep_lich_service.py -q
```

Kỳ vọng: pass hết. Test cũ không được đỏ — mặc định `dong=None` giữ nguyên hành vi.

- [ ] **Step 5: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/xep_lich_service.py backend/app/services/xep_lich_2/auto.py backend/tests/test_xep_lich_phan_doan.py
git commit -m "Xếp lịch: thời lượng phân đoạn chia theo tỉ lệ sản lượng, giữ nguyên phần canh máy"
```

---

### Task 4: Hai route tách / gộp

**Files:**
- Modify: `backend/app/routers/xep_lich_2.py`
- Modify: `backend/app/services/xep_lich_2/service.py` (phơi 2 phương thức mỏng + SSE)
- Test: `backend/tests/test_xep_lich_phan_doan.py` (thêm)

**Interfaces:**
- Consumes: `phan_doan.tach`, `phan_doan.gop` (Task 2).
- Produces:
  - `POST /api/xep-lich-2/dong/{dong_id}/tach` body `{"cac_phan": [6000, 4000]}` → `{"dong": [...]}`
  - `POST /api/xep-lich-2/dong/{dong_id}/gop` → `{"dong": {...}}`
  - `XepLich2Service.tach_dong(dong_id, cac_phan, user)` / `.gop_dong(dong_id, user)`

- [ ] **Step 1: Viết test thất bại trước**

```python
def test_route_tach_va_gop_day_sse(db, client_admin):
    """Mọi mutation của bàn xếp lịch đều phải đẩy SSE (§12.11) — tách/gộp không ngoại lệ."""
    import app.services.xep_lich_2.service as S

    g = _dong_goc(db)
    ban_tin = []
    goc_broadcast = S.hub.broadcast
    S.hub.broadcast = lambda m: ban_tin.append(m)
    try:
        r = client_admin.post(f"/api/xep-lich-2/dong/{g.id}/tach", json={"cac_phan": [6000, 4000]})
        assert r.status_code == 200
        assert len(r.json()["dong"]) == 2
        r2 = client_admin.post(f"/api/xep-lich-2/dong/{g.id}/gop")
        assert r2.status_code == 200
        assert float(r2.json()["dong"]["so_luong"]) == 10000.0
    finally:
        S.hub.broadcast = goc_broadcast
    assert len(ban_tin) >= 2


def test_route_tach_lech_tong_tra_400(db, client_admin):
    g = _dong_goc(db)
    r = client_admin.post(f"/api/xep-lich-2/dong/{g.id}/tach", json={"cac_phan": [6000, 3000]})
    assert r.status_code == 400
```

> Fixture `client_admin` là tên giả định. Đọc `backend/tests/conftest.py` và các test router hiện
> có (`grep -rn "def client" backend/tests/conftest.py`) rồi dùng ĐÚNG fixture client đang chạy;
> đừng đẻ fixture mới.

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py -q -k route
```

Kỳ vọng: FAIL 404.

- [ ] **Step 3: Thêm phương thức service**

Trong `backend/app/services/xep_lich_2/service.py`:

```python
    def tach_dong(self, dong_id: int, cac_phan: list[float], user=None) -> list[dict]:
        """Tách một dòng thành nhiều lần chạy rồi trả view của cả cụm."""
        from .phan_doan import tach

        cum = tach(self.db, dong_id=dong_id, cac_phan=cac_phan)
        self.audit.create(
            actor_user_id=getattr(user, "id", None), action="xep_lich_tach_dong",
            target=f"xep_lich_cong_doan:{dong_id}",
            detail="; ".join(f"{d.phan_doan_so}/{d.phan_doan_tong}={float(d.so_luong):g}"
                             for d in cum),
        )
        self.db.commit()
        hub.broadcast({"type": "xep_lich_thay_doi"})
        nhan = self._nap_nhan(cum)
        return [self._dong_view(d, nhan) for d in cum]

    def gop_dong(self, dong_id: int, user=None) -> dict:
        from .phan_doan import gop

        goc = gop(self.db, dong_id=dong_id)
        self.audit.create(
            actor_user_id=getattr(user, "id", None), action="xep_lich_gop_dong",
            target=f"xep_lich_cong_doan:{goc.id}", detail=f"tổng={float(goc.so_luong or 0):g}",
        )
        self.db.commit()
        hub.broadcast({"type": "xep_lich_thay_doi"})
        return self._dong_view(goc, self._nap_nhan([goc]))
```

> Chuỗi sự kiện SSE phải khớp cái bàn xếp lịch ĐANG dùng. Kiểm bằng
> `grep -n "hub.broadcast" backend/app/services/xep_lich_2/service.py` và dùng đúng `type` ở đó,
> đừng đẻ tên sự kiện mới — FE đang lắng theo tên cũ.

- [ ] **Step 4: Thêm route**

Trong `backend/app/routers/xep_lich_2.py`, cạnh `PUT /dong/{dong_id}` (~dòng 264), copy đúng khuôn
dependency/permission của route đó:

```python
class TachDongIn(BaseModel):
    cac_phan: list[float]


@router.post("/dong/{dong_id}/tach", response_model=None)
def tach_dong(dong_id: int, body: TachDongIn, ...):
    """Tách một công đoạn thành nhiều lần chạy (spec-thuc-te-vs-ke-hoach §2.4)."""
    try:
        return {"dong": svc.tach_dong(dong_id, body.cac_phan, user)}
    except XepLich2Error as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/dong/{dong_id}/gop", response_model=None)
def gop_dong(dong_id: int, ...):
    try:
        return {"dong": svc.gop_dong(dong_id, user)}
    except XepLich2Error as e:
        raise HTTPException(status_code=400, detail=str(e))
```

> `...` = đúng bộ tham số dependency của `PUT /dong/{dong_id}` (session, user, quyền). Copy y
> nguyên từ route đó — tách/gộp là cùng một quyền "sửa lịch", không đẻ quyền mới.

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_xep_lich_phan_doan.py -q
```

Kỳ vọng: pass hết.

- [ ] **Step 6: Restart uvicorn** (route mới ⇒ bắt buộc).

- [ ] **Step 7: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/routers/xep_lich_2.py backend/app/services/xep_lich_2/service.py backend/tests/test_xep_lich_phan_doan.py
git commit -m "Xếp lịch 2: API tách và gộp lần chạy công đoạn"
```

---

### Task 5: Tách / gộp trên bàn Gantt

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/XepLich2Page.tsx` (panel dòng đang chọn)
- Modify: `frontend/src/pages/Xl2Gantt.tsx` (nhãn phân đoạn trên thanh)

**Interfaces:**
- Consumes: 2 route Task 4.
- Produces: `api.xepLich2.tach(token, dongId, cacPhan)`, `api.xepLich2.gop(token, dongId)`; `Xl2Dong.so_luong`, `.phan_doan_so`, `.phan_doan_tong`.

- [ ] **Step 1: Khai kiểu + hàm API**

Thêm vào `Xl2Dong` trong `frontend/src/api/client.ts`:

```typescript
  /** Phần việc của CHÍNH thanh này khi công đoạn bị tách. null = chưa tách (trọn bước). */
  so_luong: number | null;
  /** 1..N. Chưa tách = 1. */
  phan_doan_so: number;
  phan_doan_tong: number;
```

Và vào object `xepLich2`:

```typescript
    tach(token: string, dongId: number, cacPhan: number[]): Promise<{ dong: Xl2Dong[] }> {
      return authed<{ dong: Xl2Dong[] }>(`/api/xep-lich-2/dong/${dongId}/tach`, token, {
        method: "POST", body: JSON.stringify({ cac_phan: cacPhan }),
      });
    },
    gop(token: string, dongId: number): Promise<{ dong: Xl2Dong }> {
      return authed<{ dong: Xl2Dong }>(`/api/xep-lich-2/dong/${dongId}/gop`, token, {
        method: "POST",
      });
    },
```

> Khuôn `authed<T>(...)` phải khớp các hàm `xepLich2` khác trong cùng file — copy khuôn từ
> `luu(...)` ngay cạnh, đừng viết `fetch` tay.

- [ ] **Step 2: Nút Tách / Gộp trong panel dòng**

Trong `XepLich2Page.tsx`, ở panel của dòng đang chọn (`selDong`), thêm:

```tsx
{selDong && canUpdate && !selDong.is_locked && (
  selDong.phan_doan_tong > 1 ? (
    <Button variant="secondary" disabled={busy} onClick={() => void onGop(selDong.id)}>
      Gộp {selDong.phan_doan_tong} lần chạy
    </Button>
  ) : (
    <Button variant="secondary" disabled={busy || selDong.so_luong == null}
            title={selDong.so_luong == null ? "Bước chưa biết số lượng nên chưa chia được" : undefined}
            onClick={() => setTachMo(true)}>
      Tách lần chạy
    </Button>
  )
)}
```

Và hai handler:

```tsx
  const onTach = useCallback(async (dongId: number, cacPhan: number[]) => {
    setBusy(true);
    try {
      await api.xepLich2.tach(token, dongId, cacPhan);
      await reload();
      setToast({ text: `Đã tách thành ${cacPhan.length} lần chạy` });
    } catch (e) {
      // BE là nơi quyết đúng/sai (tổng phải khớp) — bày nguyên câu của nó, đừng diễn giải lại.
      setToast({ text: String((e as Error).message), loi: true });
    } finally {
      setBusy(false);
      setTachMo(false);
    }
  }, [token, reload]);

  const onGop = useCallback(async (dongId: number) => {
    setBusy(true);
    try {
      await api.xepLich2.gop(token, dongId);
      await reload();
      setToast({ text: "Đã gộp về một lần chạy" });
    } catch (e) {
      setToast({ text: String((e as Error).message), loi: true });
    } finally {
      setBusy(false);
    }
  }, [token, reload]);
```

Form tách: một ô số cho "chia thành mấy phần" và N ô số lượng, mặc định chia đều
`Math.round(so_luong / n)` với phần cuối gánh phần dư để tổng luôn khớp:

```tsx
function chiaDeu(tong: number, n: number): number[] {
  const moi = Math.floor(tong / n);
  const ra = Array.from({ length: n - 1 }, () => moi);
  // Phần CUỐI gánh dư — tổng phải khớp tuyệt đối, BE chặn nếu lệch.
  ra.push(tong - moi * (n - 1));
  return ra;
}
```

- [ ] **Step 3: Nhãn phân đoạn trên thanh**

Trong `Xl2Gantt.tsx`, sửa `buocLabel`:

```tsx
                      const buocLabel = dong.buoc_thu_tu != null ? `B${dong.buoc_thu_tu + 1}` : "";
                      // Thanh của công đoạn đã tách phải tự nói ra nó là lần chạy thứ mấy — không
                      // thì hai thanh cùng mã cùng bước nằm hai chỗ trông như lỗi trùng lịch.
                      const phanDoanLabel = dong.phan_doan_tong > 1
                        ? `${dong.phan_doan_so}/${dong.phan_doan_tong}`
                        : "";
```

Thêm vào `maBuoc` / `maBuocNgan`: `${phanDoanLabel ? `·${phanDoanLabel}` : ""}`, và vào `title`:
`${dong.so_luong != null ? ` · ${dong.so_luong.toLocaleString("vi-VN")}` : ""}`.

- [ ] **Step 4: Kiểm kiểu**

```bash
cd frontend && npx tsc --noEmit
```

Kỳ vọng: 0 lỗi.

- [ ] **Step 5: Commit** *(chỉ khi được yêu cầu)*

```bash
git add frontend/src/api/client.ts frontend/src/pages/XepLich2Page.tsx frontend/src/pages/Xl2Gantt.tsx
git commit -m "Xếp lịch 2: nút tách/gộp lần chạy và nhãn phân đoạn trên thanh"
```

---

### Task 6 (Pha 2): Repo trả DANH SÁCH lịch cho một công đoạn

**Files:**
- Modify: `backend/app/repositories/san_xuat_repo.py` (`thoi_gian_lsx_step` dòng 205, `thoi_gian_bg_step` dòng 212)
- Test: `backend/tests/test_san_xuat_release_phan_doan.py`

**Interfaces:**
- Produces:
  ```python
  def lich_lsx_step(self, lsx_cong_doan_id: int) -> list[tuple[int | None, object, object, int, float | None]]
  def lich_bg_step(self, bai_ghep_cong_doan_id: int) -> list[...]
  # mỗi phần tử: (may_id, start_at, finish_at, phan_doan_so, so_luong), sắp theo phan_doan_so
  ```
  Hai hàm cũ `thoi_gian_lsx_step` / `thoi_gian_bg_step` **giữ nguyên chữ ký** (trả phần tử đầu) để
  chỗ gọi cũ không vỡ — nhưng `snapshot.py` chuyển sang hàm mới ở Task 7.

- [ ] **Step 1: Viết test thất bại trước**

Tạo `backend/tests/test_san_xuat_release_phan_doan.py`:

```python
"""Phát hành lệnh có công đoạn ĐÃ TÁCH (spec-thuc-te-vs-ke-hoach §2.4, pha 2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.xep_lich import NGUON_LSX, TT_DA_XEP, XepLichCongDoan
from app.repositories.san_xuat_repo import SanXuatRepository

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def test_lich_lsx_step_tra_ve_du_cac_phan_doan(db):
    a = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=55, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=1, start_at=_T0,
                        finish_at=_T0 + timedelta(hours=3),
                        so_luong=6000, phan_doan_so=1, phan_doan_tong=2)
    db.add(a)
    db.flush()
    b = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=55, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=2, start_at=_T0 + timedelta(days=1),
                        finish_at=_T0 + timedelta(days=1, hours=2),
                        so_luong=4000, phan_doan_so=2, phan_doan_tong=2, goc_dong_id=a.id)
    db.add(b)
    db.commit()

    ra = SanXuatRepository(db).lich_lsx_step(55)
    assert [r[3] for r in ra] == [1, 2]
    assert [r[0] for r in ra] == [1, 2]
    assert [float(r[4]) for r in ra] == [6000.0, 4000.0]


def test_lich_lsx_step_buoc_chua_tach_van_tra_mot_phan_tu(db):
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=56, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=3, start_at=_T0,
                        finish_at=_T0 + timedelta(hours=4))
    db.add(d)
    db.commit()

    ra = SanXuatRepository(db).lich_lsx_step(56)
    assert len(ra) == 1
    assert ra[0][3] == 1 and ra[0][4] is None
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_san_xuat_release_phan_doan.py -q
```

Kỳ vọng: FAIL — `AttributeError: 'SanXuatRepository' object has no attribute 'lich_lsx_step'`.

- [ ] **Step 3: Cài đặt**

Trong `backend/app/repositories/san_xuat_repo.py`, cạnh `thoi_gian_lsx_step`:

```python
    def lich_lsx_step(self, lsx_cong_doan_id: int) -> list[tuple]:
        """MỌI phân đoạn đã xếp của một bước lệnh, sắp theo `phan_doan_so`.

        Trước đây một bước = một dòng lịch nên `thoi_gian_lsx_step` trả đúng một bộ. Từ khi tách
        được lần chạy, một bước có N dòng — phát hành phải đẻ N công việc, không thì phân đoạn 2
        trở đi biến mất khỏi bàn tổ mà không ai báo.
        """
        return [
            (r.may_id, r.start_at, r.finish_at, r.phan_doan_so, r.so_luong)
            for r in self.db.scalars(
                select(XepLichCongDoan)
                .where(XepLichCongDoan.lsx_cong_doan_id == lsx_cong_doan_id)
                .order_by(XepLichCongDoan.phan_doan_so, XepLichCongDoan.id)
            )
        ]

    def lich_bg_step(self, bai_ghep_cong_doan_id: int) -> list[tuple]:
        """Như `lich_lsx_step` nhưng cho bước chạy chung của bài ghép."""
        return [
            (r.may_id, r.start_at, r.finish_at, r.phan_doan_so, r.so_luong)
            for r in self.db.scalars(
                select(XepLichCongDoan)
                .where(XepLichCongDoan.bai_ghep_cong_doan_id == bai_ghep_cong_doan_id)
                .order_by(XepLichCongDoan.phan_doan_so, XepLichCongDoan.id)
            )
        ]
```

Giữ nguyên hai hàm cũ; nếu muốn khỏi lặp truy vấn thì viết lại chúng thành
`ra = self.lich_lsx_step(id); return (ra[0][0], ra[0][1], ra[0][2]) if ra else (None, None, None)`
— **kiểm đúng giá trị trả về hiện tại trước khi đổi**, đừng đổi mù.

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_san_xuat_release_phan_doan.py tests/test_san_xuat_release.py -q
```

Kỳ vọng: pass hết.

- [ ] **Step 5: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/repositories/san_xuat_repo.py backend/tests/test_san_xuat_release_phan_doan.py
git commit -m "Sản xuất: repo trả danh sách phân đoạn lịch của một công đoạn"
```

---

### Task 7 (Pha 2): Phát hành đẻ một công việc cho mỗi phân đoạn

**Files:**
- Modify: `backend/app/services/san_xuat/snapshot.py` (`dung_cong_viec` dòng 61, `dung_phu_thuoc` dòng 175, `dung_diem_toa` dòng 210)
- Test: `backend/tests/test_san_xuat_release_phan_doan.py` (thêm)

**Interfaces:**
- Consumes: `repo.lich_lsx_step`, `repo.lich_bg_step` (Task 6).
- Produces: `dung_cong_viec(...) -> dict[str, list[SanXuatCongViec]]` (ĐỔI kiểu trả về — mọi chỗ gọi phải sửa theo). `danh_dau_kcs_cuoi`, `dung_phu_thuoc`, `dung_diem_toa` nhận map kiểu mới.

- [ ] **Step 1: Viết test thất bại trước**

```python
def test_phat_hanh_buoc_da_tach_de_ra_hai_cong_viec(db, orders, lsx_svc, admin, customer):
    """Bước in tách 6.000 + 4.000 ⇒ tổ nhận HAI công việc, mỗi cái mang đúng phần của mình."""
    from app.models.san_xuat import SanXuatCongViec

    lsx, cd_in, goi = _lsx_da_xep_va_tach(db, orders, lsx_svc, admin, customer)  # helper file này
    cvs = list(db.scalars(
        select(SanXuatCongViec)
        .where(SanXuatCongViec.lsx_cong_doan_id == cd_in.id)
        .order_by(SanXuatCongViec.id)
    ))
    assert len(cvs) == 2
    assert sorted(float(c.so_luong_ra) for c in cvs) == [4000.0, 6000.0]
    assert {c.may_id for c in cvs} == {1, 2}
    assert cvs[0].du_kien_bat_dau != cvs[1].du_kien_bat_dau


def test_phu_thuoc_noi_theo_phan_doan_cuoi(db, orders, lsx_svc, admin, customer):
    """Bước SAU chỉ chạy được khi phân đoạn CUỐI của bước trước xong — nối vào phân đoạn cuối,
    không nối vào phân đoạn đầu (nối đầu là cho phép bước sau chạy khi mới xong 60%)."""
    ...
```

> Helper `_lsx_da_xep_va_tach` phải dựng: đơn → lệnh → routing → xếp lịch → tách bước in →
> phát hành, dùng lại fixture của `tests/test_san_xuat_release.py`. Đọc file đó trước và tái dùng
> đúng helper đang có ở đấy thay vì dựng bộ mới.

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_san_xuat_release_phan_doan.py -q -k phat_hanh
```

Kỳ vọng: FAIL — chỉ có 1 công việc.

- [ ] **Step 3: Sửa `dung_cong_viec`**

Đổi vòng lặp bước LSX (nhánh (2)) thành:

```python
    for lsx_id in sorted(lsx_ids):
        grp = nhom_by_lsx.get(lsx_id)
        for cd in repo.routing_steps(lsx_id):
            if cd.step_key in covered_step_keys:
                continue
            # MỘT công việc cho MỖI phân đoạn lịch. Bước chưa tách vẫn ra đúng một dòng —
            # `lich_lsx_step` trả [(may, start, finish, 1, None)] trong ca đó.
            lich = repo.lich_lsx_step(cd.id) or [(None, None, None, 1, None)]
            tong_phan_doan = len(lich)
            cvs: list[SanXuatCongViec] = []
            for may_id, start, finish, phan_doan_so, sl_phan in lich:
                # `so_luong_ra` của phân đoạn = phần của nó; bước chưa tách giữ số của routing.
                # KHÔNG chia `so_luong_vao` bằng tay ở đây: nó đi qua `he_so_quy_doi` của bước,
                # chia sai thang là hỏng cả định mức khoán lẫn bảng cân đối vật tư.
                ty_le = (float(sl_phan) / float(cd.so_luong_ra)
                         if (sl_phan is not None and cd.so_luong_ra) else 1.0)
                cv = SanXuatCongViec(
                    goi_id=goi.id, phien_ban_so=phien_ban_so,
                    nhom_id=grp.id if grp else None, lsx_id=lsx_id, bai_ghep_id=None,
                    lsx_cong_doan_id=cd.id, step_key=cd.step_key,
                    ten_cong_doan=(cd.ten if tong_phan_doan == 1
                                   else f"{cd.ten} (lần {phan_doan_so}/{tong_phan_doan})"),
                    nhom_cong_doan=cd.nhom, loai_buoc=cd.loai_buoc or BUOC_MAY,
                    department_id=cd.department_id, la_kcs=(cd.department_id in kcs_depts),
                    may_id=may_id or cd.may_id,
                    du_kien_bat_dau=start, du_kien_ket_thuc=finish,
                    so_luong_vao=(_num(cd.so_luong_vao) * ty_le
                                  if cd.so_luong_vao is not None else None),
                    so_luong_ra=(float(sl_phan) if sl_phan is not None else cd.so_luong_ra),
                    don_vi_vao=cd.don_vi_vao, don_vi_ra=cd.don_vi_ra,
                    he_so_quy_doi=cd.he_so_quy_doi,
                    dinh_muc_json=_dinh_muc(cd), khoan_json=cd.khoan_json, vat_tu_json=_vat_tu(cd),
                    trang_thai=CV_PHAT_HANH,
                )
                repo.add(cv)
                repo.flush()
                cvs.append(cv)
            cv_by_step[cd.step_key] = cvs
```

Làm y hệt cho nhánh (1) bài ghép với `repo.lich_bg_step(cd.id)`; ở đó `cv_by_step[cd.step_key] = cvs`
và `for sk in covered: cv_by_step[sk] = cvs`.

Đổi docstring và annotation trả về thành `dict[str, list[SanXuatCongViec]]`, kèm giải thích:

```python
    """Đẻ công việc cho gói phát hành; trả map `step_key` → DANH SÁCH công việc theo phân đoạn.

    Trước 31/08/2026 map này là `step_key → 1 công việc` vì một bước chỉ có một dòng lịch. Từ khi
    tách được lần chạy (spec-thuc-te-vs-ke-hoach §2.4) một bước có N dòng ⇒ N công việc, xếp theo
    `phan_doan_so`. Bước chưa tách vẫn ra danh sách 1 phần tử — bên gọi KHÔNG cần phân biệt.
    """
```

- [ ] **Step 4: Sửa ba chỗ tiêu thụ map**

`danh_dau_kcs_cuoi`, `dung_phu_thuoc`, `dung_diem_toa` đang lấy `cv_by_step[sk]` như một object.
Luật nối chuỗi:

```python
        # Nối chuỗi: bước SAU phụ thuộc phân đoạn CUỐI của bước trước, và trong cùng một bước thì
        # phân đoạn i phụ thuộc phân đoạn i-1. Nối vào phân đoạn ĐẦU là cho bước sau chạy khi mới
        # xong 60% — đúng thứ mà tách lần chạy sinh ra để tránh.
        truoc = cv_by_step.get(sk_truoc) or []
        sau = cv_by_step.get(sk_sau) or []
        if truoc and sau:
            _noi(truoc[-1], sau[0])
        for i in range(1, len(sau)):
            _noi(sau[i - 1], sau[i])
```

`danh_dau_kcs_cuoi`: đánh dấu **phân đoạn CUỐI** là KCS cuối — nhóm đóng khi mẻ cuối phân loại xong.

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_san_xuat_release_phan_doan.py tests/test_san_xuat_release.py tests/test_san_xuat_release_update.py tests/test_san_xuat_dong_nhom.py -q
```

Kỳ vọng: pass hết. Đây là nhóm test dễ đỏ nhất của cả plan — `cv_by_step` đổi kiểu.

- [ ] **Step 6: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/san_xuat/snapshot.py backend/tests/test_san_xuat_release_phan_doan.py
git commit -m "Sản xuất: phát hành đẻ một công việc cho mỗi phân đoạn lần chạy"
```

---

### Task 8: Nghiệm thu bằng dev-browser (BẮT BUỘC)

**Files:** không sửa file nào.

- [ ] **Step 1: Restart uvicorn** (đã thêm route + cột ⇒ migration phải chạy lúc boot; xem log có dòng `0247_xep_lich_phan_doan`).

- [ ] **Step 2: Đăng nhập** `admin` / `admin123`.

- [ ] **Step 3: Tách bằng chuột**

Vào Xếp lịch 2, chọn một thanh in đã có số lượng, bấm **Tách lần chạy**, gõ 2 phần `6000` và
`4000`, xác nhận. Ghi lại đã bấm gì.

- [ ] **Step 4: Kiểm 5 điểm**

1. Bàn Gantt có **hai thanh** cùng mã lệnh, nhãn `·1/2` và `·2/2`.
2. Thanh 2 nằm ở lane **Nháp — chọn để xếp máy · giờ** (chưa có giờ).
3. Kéo thanh 2 sang máy khác + ngày khác → lưu được, không báo trùng máy.
4. Thời lượng thanh 1 **ngắn hơn** thanh gốc trước khi tách, nhưng **không** đúng 60% (vì phần
   canh máy không chia) — mở tooltip đọc "chuẩn bị máy … · chạy …" để xác nhận.
5. Gõ tổng sai (6000 + 3000) → hiện thông báo lỗi của BE, **không** tách.

- [ ] **Step 5: Phát hành và kiểm bàn tổ**

Phát hành lệnh đó xuống tổ. Vào Thực hiện sản xuất: tổ phải thấy **hai** thẻ công việc cho cùng
công đoạn, tên có hậu tố `(lần 1/2)` / `(lần 2/2)`, mục tiêu 6.000 và 4.000.

- [ ] **Step 6: Gộp lại**

Về Xếp lịch 2, bấm **Gộp 2 lần chạy** trên một lệnh CHƯA phát hành → còn một thanh, số lượng
10.000. Xác nhận lệnh **đã phát hành** thì không gộp được (hoặc gộp được nhưng không đụng công
việc đã phát hành — chốt hành vi này với chủ dự án nếu test chưa nói rõ).

- [ ] **Step 7: Báo cáo** — liệt kê cụ thể từng bước đã bấm/gõ/thấy. Có đoạn nào tắt qua API thì
nói rõ ngay, đừng đợi hỏi.

---

## Self-Review

**1. Spec coverage**

| Yêu cầu spec §2.4 | Task |
| --- | --- |
| (1) `xep_lich_cong_doan` mọc chiều số lượng | Task 1 |
| (2) engine thời lượng chia tỉ lệ theo phần | Task 3 |
| (3) `thoi_gian_*_step` trả danh sách | Task 6 |
| (4) `dung_cong_viec` đẻ 1 CV/phân đoạn, `cv_by_step` thành list, `dung_phu_thuoc` nối chuỗi | Task 7 |
| (5) `dong_nhom` / `ban_giao` / `phan_bo` đếm theo công việc — có test chứng minh | Task 7 Step 5 (chạy `test_san_xuat_dong_nhom.py`) |
| Pha 1 = (1)(2)(3) + UI tách/gộp, chưa phát hành | Task 1–5 |
| Pha 2 = (4)(5) + phát hành nhiều phân đoạn | Task 6–8 |
| Bất biến tổng số lượng | Task 2 Step 1 (4 test) + Task 2 Step 3 (kiểm ở `tach`) |

**2. Placeholder scan** — hai chỗ còn `...` là **cố ý và có chỉ dẫn kèm**: tham số dependency của
route (Task 4 Step 4 — phải copy từ `PUT /dong/{dong_id}` để không đẻ quyền mới) và thân test
`test_phu_thuoc_noi_theo_phan_doan_cuoi` (Task 7 Step 1 — helper dựng cảnh phải tái dùng của
`test_san_xuat_release.py`). Mọi chỗ khác đều là code thật.

**3. Type consistency** — `tach(db, *, dong_id, cac_phan)` và `gop(db, *, dong_id)` dùng đúng chữ
ký đó ở Task 2 (định nghĩa), Task 4 Step 3 (service). `ty_le_trong_cum(dong, cum)` là đường tính
tỉ lệ DUY NHẤT (Task 2 Step 3 ghi chú bỏ `ty_le` một-tham-số), dùng ở Task 3 Step 3.
`lich_lsx_step` / `lich_bg_step` trả tuple 5 phần tử `(may_id, start, finish, phan_doan_so, so_luong)`
— khớp giữa Task 6 (định nghĩa + test) và Task 7 Step 3 (giải nén đúng 5 biến).
Tên cột `so_luong` / `phan_doan_so` / `phan_doan_tong` / `goc_dong_id` khớp giữa model (Task 1),
migration (Task 1 Step 4), DB_SCHEMA (Task 1 Step 5), service (Task 2), repo (Task 6) và TS
(Task 5 Step 1).

**Rủi ro lớn nhất đã nêu thành bước riêng:** Task 7 đổi KIỂU TRẢ VỀ của `dung_cong_viec` —
đây là chỗ dễ làm đỏ hàng loạt test phát hành. Task 7 Step 5 chạy đúng 4 file test bao quanh nó.

## Scope Check

Plan này tự đứng được sau **Pha 1** (Task 1–5): người lập kế hoạch tách được lần chạy trên bàn
Gantt và số liệu đúng, chỉ chưa phát hành nhiều phân đoạn. Nếu cần dừng sớm thì dừng ở đó — Pha 2
là một mảnh độc lập, không để lại trạng thái dở dang.

Plan này **không** phụ thuộc `docs/superpowers/plans/2026-08-31-thuc-te-phan-hoi-ke-hoach.md`,
nhưng làm sau plan đó thì lợi hơn: lớp thực tế đã có sẵn để nhìn từng phân đoạn chạy tới đâu.
