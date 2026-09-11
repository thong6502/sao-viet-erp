# Sản xuất chỉ ghi số lượng · Bàn tổ trục LỆNH · Mẻ đủ chi tiết · Màn thợ — Plan thi công

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gỡ toàn bộ đường TIỀN KHOÁN khỏi Kế hoạch SX → Bài ghép → Thực hiện SX (giữ nguyên việc
kế hoạch chọn đầu việc + mọi định mức), đổi trục bàn tổ từ "công đoạn rời" sang "LỆNH / BÀI GHÉP",
làm mỗi mẻ đọc được trọn vẹn (sản lượng theo người luôn hiện), và cho thợ một màn chỉ thấy việc
của chính mình.

**Architecture:** Backend phân tầng `routers → services → repositories → DB`; engine chia sản
lượng (`services/san_xuat/phan_bo.py`) vẫn là HÀM THUẦN nên mặt đọc gọi lại được để dựng bản NHÁP
mà không ghi DB. Gom nhóm + phân trang theo LỆNH làm ở **máy chủ** (SQL `GROUP BY` + `LIMIT`),
FE chỉ vẽ. Không bảng mới, không cột mới — chỉ bỏ 3 cột `don_gia` và 1 bảng thưởng.

**Tech Stack:** Python 3 · FastAPI · SQLAlchemy 2 (không Alembic — migration tay trong
`backend/app/db_migrations.py`) · PostgreSQL (dev `127.0.0.1:5433/svn_erp_local`, prod PG16) ·
pytest + SQLite in-memory · React + TypeScript + Vite · vitest + testing-library.

**Spec:** [docs/superpowers/specs/2026-09-11-san-xuat-chi-ghi-so-luong-design.md](../specs/2026-09-11-san-xuat-chi-ghi-so-luong-design.md)

## Global Constraints

- **Ngôn ngữ UI: TIẾNG VIỆT 100%.** Nhãn/nút/tooltip/toast/badge không được có từ tiếng Anh.
  Ngoại lệ đã được chấp nhận: `Gantt`; viết tắt tiếng Việt như `BG` = bài ghép.
- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, không ALTER/DROP. Mọi thêm/bỏ cột phải viết vào
  `backend/app/db_migrations.py` và `MIGRATIONS.append((...))`. Số thứ tự kế tiếp: **0296**.
- **Migration cấm ORM full-select** — backfill/DDL phải raw SQL đích danh cột.
- **`docs/DB_SCHEMA.md` có guard test**: mọi bảng/cột trong model phải được ghi ở đó. Bỏ cột/bảng ⇒
  sửa `docs/DB_SCHEMA.md` TRONG CÙNG task.
- Cột Boolean: `server_default` phải là `false`/`true` (Python bool), không phải `"0"`/`"1"`.
  *(Plan này không thêm Boolean nào — ghi lại để không ai vô tình thêm.)*
- **ĐỪNG chạy `./init.ps1`.** Verify bằng `pytest` nhắm đúng file + `npx tsc --noEmit`. Không chạy
  cả bộ pytest cục bộ trước khi push — để CI GitHub chạy.
- **Không `python -c` trong `backend/`** — nó trỏ vào Postgres DEV thật. Muốn thăm dò thì viết test
  tạm rồi chạy bằng pytest.
- Không bật lại `SEED_DEMO` trên DB dev.
- Sửa route/schema backend ⇒ **RESTART uvicorn** (không hot-reload đáng tin).
- **Phân trang + lọc phải ở MÁY CHỦ.** Kéo cả bảng về rồi cắt trang trong JS là bị bác.
- Git: message tiếng Việt (thuật ngữ kỹ thuật giữ tiếng Anh), **không** trailer `Co-Authored-By`.
  Chỉ commit/push khi được yêu cầu.
- Sau khi xoá/ghi đè thứ gì đáng kể: nói rõ đã xoá cái gì, còn khôi phục được không.
- Không nối lệnh shell bằng `echo "===="` / `printf '---'`.

---

# ĐỢT A — Gỡ tiền khoán khỏi kế hoạch → sản xuất

## File structure của đợt A

| File | Trách nhiệm sau đợt A |
|---|---|
| `backend/app/db_migrations.py` | thêm `0296` (bỏ 3 cột `don_gia`) + `0297` (bỏ bảng thưởng tổ trưởng) |
| `backend/app/models/san_xuat_phan_bo.py` | 3 bảng phân bổ, KHÔNG còn cột `don_gia` |
| `backend/app/models/san_xuat_thuong_to_truong.py` | **XOÁ** |
| `backend/app/services/san_xuat/phan_bo.py` | engine CHIA SẢN LƯỢNG, không biết tiền |
| `backend/app/services/san_xuat/snapshot.py` | ảnh chụp bước, không gắn `don_gia_hd` |
| `backend/app/services/san_xuat/thuong_to_truong.py` | **XOÁ** |
| `backend/app/repositories/thuong_to_truong_repo.py` | **XOÁ** |
| `backend/app/services/piece_work_service.py` | `khoan_snapshot` chỉ còn `{rate_id, ten}` |
| `backend/app/services/lsx_service.py` | bỏ `don_gia_hieu_dung`/`_khoan_derived`/`_khoan_tu_kh` |
| `backend/app/services/bai_ghep_service.py` | bước chung ghim đầu việc, không tính tiền |
| `backend/app/repositories/production_output_repo.py` | seam lương: `unit_price` luôn 0 |
| `frontend/src/pages/ThsxExecPanels.tsx` | khối **"Chia sản lượng"**, không ô tiền |
| `frontend/src/pages/LsxBuocDrawer.tsx` · `LsxDetailView.tsx` · `LsxRoutingTable.tsx` | chọn đầu việc, không hiện tiền |
| `frontend/src/pages/BaiGhepBuocChungForm.tsx` · `BaiGhep2Page.tsx` | như trên |
| `frontend/src/pages/ThsxG5.tsx` · `kcs/KcsChotNhom.tsx` · `ThsxDrawer.tsx` | bỏ panel thưởng tổ trưởng |

---

### Task 1: Bỏ 3 cột `don_gia` + bảng thưởng tổ trưởng ở tầng DB

**Files:**
- Modify: `backend/app/db_migrations.py` (cuối file, sau `0295_quote_item_anh_minh_hoa`)
- Modify: `backend/app/models/san_xuat_phan_bo.py:130`, `:179`, `:211`
- Delete: `backend/app/models/san_xuat_thuong_to_truong.py`
- Modify: `backend/app/models/__init__.py:159`, `:333`
- Modify: `docs/DB_SCHEMA.md`
- Test: `backend/tests/test_migration_0296_bo_don_gia_phan_bo.py` (tạo mới)
- Delete: `backend/tests/test_migration_0266_thuong_to_truong.py`

**Interfaces:**
- Consumes: `_existing_columns(insp, table)` và `MIGRATIONS` list của `db_migrations.py`.
- Produces: model `SanXuatPhanBo` / `SanXuatPhanBoDong` / `SanXuatPhanBoBuTru` KHÔNG còn thuộc tính
  `don_gia`; tên `SanXuatThuongToTruong` không còn tồn tại trong `app.models`.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/test_migration_0296_bo_don_gia_phan_bo.py`:

```python
"""Migration 0296/0297: sản xuất thôi giữ TIỀN — bỏ 3 cột `don_gia` + bảng thưởng tổ trưởng.

Chạy migration trên một DB đã có cột/bảng cũ (mô phỏng DB dev đang sống), không phải trên DB
trắng do `create_all` dựng — `create_all` không bao giờ tạo cột đã xoá khỏi model nên test trên DB
trắng chứng minh được rất ít.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS


def _chay(ten_tien_to: str, db: Session) -> None:
    for ten, fn in MIGRATIONS:
        if ten.startswith(ten_tien_to):
            fn(db)
            return
    raise AssertionError(f"Không thấy migration {ten_tien_to} trong MIGRATIONS")


def test_0296_bo_cot_don_gia_cua_ba_bang_phan_bo():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        for bang in ("san_xuat_phan_bo", "san_xuat_phan_bo_dong", "san_xuat_phan_bo_bu_tru"):
            db.execute(text(
                f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY, don_gia NUMERIC(18,4) NOT NULL DEFAULT 0)"
            ))
        db.commit()
        _chay("0296_", db)
        insp = inspect(db.get_bind())
        for bang in ("san_xuat_phan_bo", "san_xuat_phan_bo_dong", "san_xuat_phan_bo_bu_tru"):
            assert "don_gia" not in {c["name"] for c in insp.get_columns(bang)}


def test_0296_chay_lai_khong_no():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE san_xuat_phan_bo (id INTEGER PRIMARY KEY)"))
        db.commit()
        _chay("0296_", db)   # bảng thiếu cột + hai bảng kia chưa tồn tại ⇒ vẫn phải im lặng đi qua
        _chay("0296_", db)


def test_0297_bo_bang_thuong_to_truong():
    eng = create_engine("sqlite://")
    with Session(eng) as db:
        db.execute(text("CREATE TABLE san_xuat_thuong_to_truong (id INTEGER PRIMARY KEY)"))
        db.commit()
        _chay("0297_", db)
        assert "san_xuat_thuong_to_truong" not in set(inspect(db.get_bind()).get_table_names())
        _chay("0297_", db)   # idempotent


def test_model_khong_con_cot_don_gia():
    from app.models.san_xuat_phan_bo import (
        SanXuatPhanBo, SanXuatPhanBoBuTru, SanXuatPhanBoDong,
    )

    for model in (SanXuatPhanBo, SanXuatPhanBoDong, SanXuatPhanBoBuTru):
        assert "don_gia" not in model.__table__.columns, model.__tablename__


def test_model_thuong_to_truong_da_go():
    import app.models as m

    assert not hasattr(m, "SanXuatThuongToTruong")
```

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_migration_0296_bo_don_gia_phan_bo.py -q`
Expected: FAIL — `AssertionError: Không thấy migration 0296_ trong MIGRATIONS`.

- [ ] **Step 3: Viết migration**

Nối vào cuối `backend/app/db_migrations.py`:

```python
def _migrate_bo_don_gia_phan_bo(db) -> None:
    """Sản xuất THÔI giữ tiền: bỏ `don_gia` ở 3 bảng phân bổ (chủ xưởng chốt 11/09/2026).

    *"Bên sản xuất với kế hoạch thì không cần liên quan tới lương khoán đâu, đó là việc của kế
    toán lương, bên sản xuất chỉ ghi nhận số lượng thôi."* Ba cột này là toàn bộ đường tiền ở tầng
    sản xuất; bỏ chúng thì `khoan_json.don_gia_hd` và `_don_gia_don_vi` mất chỗ chảy về.

    GIỮ `q_tra_luong` / `so_luong_tra_luong` / `q_ban_dia`: đó là SẢN LƯỢNG THEO NGƯỜI — thứ duy
    nhất kế toán lương cần nhận, và là dữ liệu thật do tổ ghi.

    Best-effort từng câu: SQLite < 3.35 từ chối `DROP COLUMN` → cột mồ côi vô hại vì model không
    map nữa. Mất số đơn giá đã ghim trong phân bổ đã chốt — chấp nhận được, chính chúng là số sai
    của cầu quy đổi đồng nhất (`kq.q_pay = kq.q_native`).
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    for bang in ("san_xuat_phan_bo", "san_xuat_phan_bo_dong", "san_xuat_phan_bo_bu_tru"):
        if bang not in tables or "don_gia" not in _existing_columns(insp, bang):
            continue
        try:
            db.execute(text(f"ALTER TABLE {bang} DROP COLUMN don_gia"))
            db.commit()
        except Exception:
            db.rollback()


MIGRATIONS.append(("0296_bo_don_gia_phan_bo", _migrate_bo_don_gia_phan_bo))


def _migrate_bo_bang_thuong_to_truong(db) -> None:
    """Bỏ bảng `san_xuat_thuong_to_truong` — thưởng/phạt tổ trưởng là việc của KẾ TOÁN LƯƠNG.

    Bảng này là bảng TIỀN thuần (`tien_khoan`, `rate_pct`, `so_tien`) do lúc ĐÓNG NHÓM ghi ra.
    Đóng nhóm là việc của sản xuất, mà sản xuất nay không ôm tiền nữa.

    GIỮ `payroll_lines.thuong_to_truong` (cột) và `piece_leader_bonus_brackets` (bảng bậc): cả hai
    thuộc phía bảng lương, màn "Khoán theo kỳ" của kế toán sẽ rót lại vào đúng cột ấy. Cột tạm về 0.

    Mất các dòng thưởng đã ghi. Không khôi phục được.
    """
    insp = inspect(db.get_bind())
    if "san_xuat_thuong_to_truong" not in set(insp.get_table_names()):
        return
    try:
        db.execute(text("DROP TABLE san_xuat_thuong_to_truong"))
        db.commit()
    except Exception:
        db.rollback()


MIGRATIONS.append(("0297_bo_bang_thuong_to_truong", _migrate_bo_bang_thuong_to_truong))
```

- [ ] **Step 4: Bỏ cột khỏi model + xoá model thưởng**

`backend/app/models/san_xuat_phan_bo.py` — xoá **3 dòng** (không đổi gì khác):

```python
    don_gia: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
```

Dòng `:130` (trong `SanXuatPhanBo`, ngay dưới `don_vi_tra_luong`), `:179` (trong
`SanXuatPhanBoDong`, ngay dưới `he_so_bac`), `:211` (trong `SanXuatPhanBoBuTru`, ngay dưới
`so_luong_tra_luong`).

Sửa docstring `SanXuatPhanBo` (dòng 107) cho khỏi nói dối:

```python
    """HEADER CHIA SẢN LƯỢNG của MỘT batch (§12.1). Một batch tối đa một bản chia (`batch_id`
    UNIQUE). Đóng băng tại lúc TÍNH: `q_tra_luong` (Q sau quy đổi), `tong_ty_le_ho_tro` (tổng P đã
    xác nhận), giữ RIÊNG sản lượng bản địa `q_ban_dia`/`don_vi_ban_dia` (§12.2). `ky_nam`/`ky_thang`
    = kỳ lương của batch (suy từ ngày batch) để lọc theo kỳ nhanh.

    KHÔNG có cột TIỀN nào (bỏ `don_gia` 11/09/2026): sản xuất ghi SỐ LƯỢNG, kế toán lương đổi ra
    tiền. Tên cột còn chữ "trả lương" vì đây đúng là sản lượng ĐEM ĐI TRẢ LƯƠNG — chỉ là phép nhân
    đơn giá không còn xảy ra ở tầng này.

    Trạng thái §12.3: draft (chưa chốt, công nhân chưa xem) → finalized (chốt, feed lương) →
    reopened (mở lại trước khi kỳ khoá) → finalized lại."""
```

Xoá file `backend/app/models/san_xuat_thuong_to_truong.py`. Trong
`backend/app/models/__init__.py` xoá dòng `from .san_xuat_thuong_to_truong import SanXuatThuongToTruong`
(`:159`) và `"SanXuatThuongToTruong",` trong `__all__` (`:333`).

- [ ] **Step 5: Cập nhật `docs/DB_SCHEMA.md`**

Xoá 3 dòng mô tả cột `don_gia` của `san_xuat_phan_bo`, `san_xuat_phan_bo_dong`,
`san_xuat_phan_bo_bu_tru`; xoá trọn khối bảng `san_xuat_thuong_to_truong`. Tìm bằng:

```bash
grep -n "don_gia" docs/DB_SCHEMA.md | grep -i phan_bo
```

- [ ] **Step 6: Xoá test cũ của bảng thưởng**

```bash
git rm backend/tests/test_migration_0266_thuong_to_truong.py backend/tests/test_thuong_to_truong.py
```

- [ ] **Step 7: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_migration_0296_bo_don_gia_phan_bo.py tests/test_db_schema_doc.py -q`
Expected: PASS cả hai file.

*(Tại bước này `tests/test_san_xuat_phan_bo.py` CÒN ĐỎ vì service vẫn gán `don_gia` — Task 2 chữa.)*

- [ ] **Step 8: Commit**

```bash
git add backend/app/db_migrations.py backend/app/models/san_xuat_phan_bo.py backend/app/models/__init__.py docs/DB_SCHEMA.md backend/tests/test_migration_0296_bo_don_gia_phan_bo.py
git commit -m "mg 0296/0297: bỏ cột don_gia của 3 bảng phân bổ + bỏ bảng thuong_to_truong"
```

---

### Task 2: Engine phân bổ thành engine CHIA SẢN LƯỢNG

**Files:**
- Modify: `backend/app/services/san_xuat/phan_bo.py:1-20` (docstring module), `:102-117`
  (`_don_gia_don_vi` — xoá), `:127`, `:145-146`, `:179`, `:282`, `:301`, `:504`
- Modify: `backend/app/schemas/san_xuat.py:349`, `:357`, `:381-385`
- Modify: `backend/app/services/san_xuat/board.py:759-762`, `:789`, `:799`
- Test: `backend/tests/test_san_xuat_phan_bo.py` (sửa bài đang có + thêm bài mới)

**Interfaces:**
- Consumes: `SanXuatPhanBo`/`SanXuatPhanBoDong`/`SanXuatPhanBoBuTru` không còn `don_gia` (Task 1).
- Produces: `_KetQuaTinh` không còn thuộc tính `don_gia`; `_tinh_batch(db, cv, batch, pb_repo) ->
  _KetQuaTinh` giữ nguyên chữ ký; dict dòng phân bổ có đúng khoá
  `{employee_id, department_id, la_ho_tro, ho_tro_id, ngay, so_luong_tra_luong, so_luong_ban_dia,
  trong_so, phut_thuc_te, he_so_bac}`. Schema `PhanBoDongOut` / `BuTruDongOut` /
  `PhanBoChiTietOut` không còn `don_gia` và `don_gia_tu_cong_thuc`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_san_xuat_phan_bo.py`:

```python
def test_engine_chia_khong_con_bat_ky_o_tien_nao(db, cv_co_khoan_va_batch):
    """Sản xuất ghi SỐ LƯỢNG. Ảnh chụp có đơn giá lẫn `don_gia_hd` thì engine vẫn phải làm như
    không thấy — không khoá tiền nào được lọt xuống dòng chia."""
    cv, batch = cv_co_khoan_va_batch
    cv.khoan_json = {**(cv.khoan_json or {}), "don_gia": 40.0, "don_gia_hd": 620.0,
                     "don_vi": "nhip", "cong_thuc": "50000 + don_gia_khoan * sl_ra"}
    db.flush()

    from app.repositories.san_xuat_phan_bo_repo import SanXuatPhanBoRepository
    from app.services.san_xuat.phan_bo import _tinh_batch

    kq = _tinh_batch(db, cv, batch, SanXuatPhanBoRepository(db))

    assert not hasattr(kq, "don_gia")
    assert kq.dong, "phải có dòng chia để bài này nói được điều gì"
    for d in kq.dong:
        assert "don_gia" not in d
    # Đơn vị trả lương = đơn vị RA của bước, không phải đơn vị TIỀN của đầu việc ("nhip").
    assert kq.don_vi_pay == cv.don_vi_ra


def test_module_phan_bo_khong_con_ham_don_gia():
    from app.services.san_xuat import phan_bo

    assert not hasattr(phan_bo, "_don_gia_don_vi")
```

Ngoài ra: mọi `assert ... don_gia ...` đang có trong file phải bỏ. Tìm bằng:

```bash
grep -n "don_gia" backend/tests/test_san_xuat_phan_bo.py
```

*(Fixture `cv_co_khoan_va_batch` — nếu file chưa có fixture cùng nghĩa thì dùng đúng fixture mà các
bài kế bên đang dùng để dựng `(cong_viec, batch)` có người tham gia + chấm công hợp lệ; đọc đầu
file trước khi viết.)*

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_san_xuat_phan_bo.py -q`
Expected: FAIL — `AttributeError`/`assert not hasattr(phan_bo, "_don_gia_don_vi")`.

- [ ] **Step 3: Sửa `phan_bo.py`**

a) Xoá trọn hàm `_don_gia_don_vi` (dòng 102–117) và thay bằng một hàm chỉ trả đơn vị:

```python
def _don_vi_tra_luong(cv: SanXuatCongViec) -> str | None:
    """Đơn vị của sản lượng đem chia = đơn vị RA của bước (thứ mà `batch.tot` đếm).

    Trước 11/09/2026 chỗ này còn trả kèm ĐƠN GIÁ lấy từ ảnh chụp `khoan_json`, và nhãn đơn vị đi
    theo đơn giá ấy (`đ/nhịp`, `đ/m²`). Cả hai đã bỏ: sản xuất ghi số lượng, kế toán lương định
    giá. Đơn vị TIỀN của đầu việc (`khoan_json.don_vi`) vì thế KHÔNG còn là câu trả lời ở đây —
    dán nó lên một con số đếm bằng tờ là nói sai đơn vị.
    """
    return cv.don_vi_ra or None
```

b) Trong `_KetQuaTinh.__init__` (dòng ~127) xoá `self.don_gia: float = 0.0`.

c) Trong `_tinh_batch` (dòng ~145) đổi:

```python
    kq.don_vi_pay = _don_vi_tra_luong(cv)
    kq.q_pay = kq.q_native  # sản lượng chia = sản lượng TỐT bản địa, không quy đổi
```

d) Xoá khoá `"don_gia": kq.don_gia,` ở cả hai dict dòng (dòng ~179 của nhánh hỗ trợ và ~282 của
nhánh tổ thực hiện).

e) Trong `_ap_header` (dòng ~301) xoá `header.don_gia = kq.don_gia`.

f) Trong `bu_tru` (dòng ~504) xoá `don_gia=float(header.don_gia or 0),`.

g) Sửa docstring module (dòng 1–20): xoá trọn đoạn giải thích `don_gia_hd` THẮNG `don_gia`, thay
bằng:

```python
"""§12 — CHIA SẢN LƯỢNG của một mẻ cho những người đã làm mẻ đó.

KHÔNG có tiền ở tầng này (11/09/2026). Engine chỉ trả lời một câu: mẻ ra `tot` đơn vị thì mỗi
người được ghi bao nhiêu. Trọng số = phút chấm công HỢP LỆ × hệ số bậc; phần người hỗ trợ = Q ×
tỷ lệ đã thỏa thuận, ghi cho TỔ GỐC; phần còn lại chia theo trọng số, làm tròn lớn-nhất-dư theo
milli-đơn-vị nên Σ = Q đúng bằng sản lượng tốt.

Đổi số lượng ra tiền là việc của KẾ TOÁN LƯƠNG, đọc sản lượng theo người ở
`repositories/production_output_repo.py`. Xem `docs/superpowers/specs/2026-09-11-san-xuat-chi-ghi-so-luong-design.md`.
"""
```

- [ ] **Step 4: Sửa schema + mặt đọc board**

`backend/app/schemas/san_xuat.py`: xoá `don_gia: float` khỏi `PhanBoDongOut` (`:349`) và
`BuTruDongOut` (`:357`); xoá `don_gia: float` + cả khối chú thích + `don_gia_tu_cong_thuc: bool = False`
khỏi `PhanBoChiTietOut` (`:381-385`).

`backend/app/services/san_xuat/board.py`: xoá `"don_gia": float(h.don_gia or 0),` + 4 dòng chú
thích + `"don_gia_tu_cong_thuc": ...` (`:759-762`); xoá `"don_gia": float(d.don_gia or 0),`
(`:789`) và `"don_gia": float(bt.don_gia or 0),` (`:799`).

- [ ] **Step 5: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_san_xuat_phan_bo.py tests/test_san_xuat_board.py tests/test_san_xuat_board_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/san_xuat/phan_bo.py backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py backend/tests/test_san_xuat_phan_bo.py
git commit -m "phan_bo: engine chia sản lượng, gỡ hết ô đơn giá khỏi tầng sản xuất"
```

---

### Task 3: Ảnh chụp đầu việc — giữ TÊN việc, bỏ GIÁ

**Files:**
- Modify: `backend/app/services/piece_work_service.py:62-95` (`khoan_snapshot`)
- Modify: `backend/app/services/san_xuat/snapshot.py:94-110` (bỏ `don_gia_hd` + service trễ)
- Modify: `backend/app/services/bien_cong_thuc.py:187` (biến `don_gia_khoan` thôi đọc `khoan_json`)
- Test: `backend/tests/test_khoan_dau_viec.py`

**Interfaces:**
- Consumes: không gì mới.
- Produces: `khoan_snapshot(rate, dm=None) -> dict` trả về **chỉ** `{"rate_id": int, "ten": str}`
  cộng `cong_thuc_gio` (khoá CÓ MẶT khi `dm is not None`, kể cả rỗng — dấu "ảnh chụp biết đầu việc
  có ô đo giờ riêng"). `_SoPhatHanh.khoan_json(cd)` trả thẳng ảnh chụp của bước, không gắn thêm khoá.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_khoan_dau_viec.py`:

```python
def test_khoan_snapshot_chi_con_ten_viec_khong_con_gia():
    """Kế hoạch vẫn CHỌN đầu việc (giữ `rate_id` + `ten` để kế toán lương tra bảng giá lúc tính
    lương), nhưng ảnh chụp KHÔNG ghim đơn giá / đơn vị tiền / công thức ra tiền nữa."""
    from app.services.piece_work_service import khoan_snapshot

    class _Rate:
        id = 7
        ten = "Bế hộp bánh · máy 1050"
        unit = "nhip"
        unit_price = 40.0

    class _Dm:
        cong_thuc_khoan = "50000 + don_gia_khoan * sl_ra"
        cong_thuc_gio = "sl_vao"
        nang_suat_nguoi_gio = 1200.0
        nang_suat_nguoi_gio_min = None
        nang_suat_nguoi_gio_max = None
        don_vi_nang_suat = "to_gio"
        so_nguoi_tieu_chuan = 2

    snap = khoan_snapshot(_Rate(), _Dm())

    assert snap["rate_id"] == 7
    assert snap["ten"] == "Bế hộp bánh · máy 1050"
    for khoa in ("don_gia", "don_vi", "cong_thuc"):
        assert khoa not in snap, khoa
    # Dấu "ảnh chụp MỚI, biết ô đo giờ riêng" phải còn — `dich_gio_cua_khoan` gác luật theo nó.
    assert snap["cong_thuc_gio"] == "sl_vao"


def test_snapshot_phat_hanh_khong_gan_don_gia_hd():
    from app.services.san_xuat import snapshot as sn

    assert not hasattr(sn, "_DonGiaHieuDung")
    assert "don_gia_hd" not in open(sn.__file__, encoding="utf-8").read()
```

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_khoan_dau_viec.py -q`
Expected: FAIL — `assert "don_gia" not in snap`.

- [ ] **Step 3: Sửa `khoan_snapshot`**

Thay thân hàm `backend/app/services/piece_work_service.py:62` bằng:

```python
def khoan_snapshot(rate, dm=None) -> dict:
    """Ảnh chụp ĐẦU VIỆC để ghim vào bước lệnh — chỉ TÊN VIỆC, không có giá.

    Từ 11/09/2026 sản xuất và kế hoạch không ôm tiền khoán nữa (chủ xưởng chốt: *"bên sản xuất chỉ
    ghi nhận số lượng thôi"*). Nên ảnh chụp bỏ `don_gia`, `don_vi` (đơn vị TIỀN) và `cong_thuc`
    (công thức RA TIỀN): ghim giá lúc phát hành là ghim một con số mà máy nào chạy, kíp mấy người,
    mấy màu mực, khuôn cũ hay mới đều làm nó đổi — những chiều engine không suy được.

    `rate_id` + `ten` thì GIỮ, và giữ vì lý do ngược lại: đó là CÁI TÊN của việc. Kế toán lương đọc
    tên đó rồi tra bảng giá tại thời điểm tính lương.

    `cong_thuc_gio` (cách đo GIỜ, tách hẳn khỏi cách đo tiền) vẫn chụp: thời lượng bước và Xếp lịch
    sống bằng nó. Khoá này CÓ MẶT kể cả khi rỗng — chính SỰ CÓ MẶT của nó là dấu "ảnh chụp biết đầu
    việc có ô đo giờ riêng", `dich_gio_cua_khoan` gác luật theo đúng dấu đó.

    Ảnh chụp CŨ trong DB vẫn còn các khoá tiền; không migrate (JSON không có schema, khoá mồ côi vô
    hại) — code thôi đọc chúng là đủ.
    """
    snap = {
        "rate_id": rate.id,
        "ten": getattr(rate, "ten", getattr(rate, "name", "")),
    }
    if dm is not None:
        snap["cong_thuc_gio"] = (getattr(dm, "cong_thuc_gio", None) or "").strip()
    return snap
```

*Trước khi sửa, đọc lại nguyên bản dòng 90–95 để bê nguyên phần `cong_thuc_gio` đang có (khoá này
đã tồn tại từ 07/09/2026) — đừng viết lại từ đầu, chỉ bỏ ba khoá tiền.*

- [ ] **Step 4: Sửa `snapshot.py`**

Trong `backend/app/services/san_xuat/snapshot.py`, hàm `khoan_json` (dòng 94–110) thu về:

```python
    def khoan_json(self, cd) -> dict | None:
        """`khoan_json` đem ghim vào công việc = ĐÚNG ảnh chụp của bước, không gắn thêm gì.

        Trước 11/09/2026 chỗ này gắn thêm `don_gia_hd` (đơn giá hiệu dụng) cho tầng trả lương.
        Đã bỏ cùng cả cơ chế tiền khoán ở sản xuất — xem spec 2026-09-11.
        """
        return getattr(cd, "khoan_json", None)
```

Xoá luôn lớp/hàm trễ `_DonGiaHieuDung` và mọi import chỉ còn nó dùng (`LsxService` trong file này
nếu không còn nơi nào gọi — kiểm bằng `grep -n "_lsx_svc\|LsxService" backend/app/services/san_xuat/snapshot.py`
trước khi xoá import).

- [ ] **Step 5: Sửa biến công thức `don_gia_khoan`**

`backend/app/services/bien_cong_thuc.py:187` — biến này lấy giá trị từ ảnh chụp
`khoan_json["don_gia"]` của bước. Ảnh chụp nay không có khoá đó. Sửa chú thích + nguồn để nó chỉ
còn có số ở ô công thức **của DANH MỤC** (nơi người khai đang gõ, có `rate` trong tay), còn ở tầng
lệnh thì là 0:

```python
    # Giá trị: đơn giá của ĐẦU VIỆC đang khai — chỉ có số ở ô công thức của DANH MỤC (màn Công
    # đoạn → định mức đầu việc), nơi người khai có sẵn dòng giá trong tay. Ở tầng LỆNH và tầng SẢN
    # XUẤT biến này bằng 0: hai tầng đó không còn nhân đơn giá nào (11/09/2026, spec
    # "Sản xuất chỉ ghi số lượng"). Công thức RA TIỀN vì thế chỉ chạy ở màn của kế toán lương.
```

- [ ] **Step 6: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_khoan_dau_viec.py tests/test_khoan_api.py tests/test_san_xuat_release.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/piece_work_service.py backend/app/services/san_xuat/snapshot.py backend/app/services/bien_cong_thuc.py backend/tests/test_khoan_dau_viec.py
git commit -m "khoan_snapshot: ảnh chụp đầu việc giữ tên việc, bỏ đơn giá và công thức ra tiền"
```

---

### Task 4: Gỡ tiền khoán khỏi tầng LỆNH (`lsx_service` + schema)

**Files:**
- Modify: `backend/app/services/lsx_service.py` — xoá `don_gia_hieu_dung` (`:1227`),
  `_khoan_derived` (`:929`), `_khoan_tu_kh` (`:1253`), khoá `khoan` của `xem_truoc_buoc` (`:1011`),
  4 khoá `tien_du_kien`/`sl_du_kien`/`don_vi_sl_du_kien`/`dien_giai_du_kien` (`:893-898`),
  `khoan_don_vi`/`khoan_don_gia` của payload bước (`:2749-2750`), `khoan_tien_tong` (`:2548`)
- Modify: `backend/app/schemas/lsx.py:317-318`, `:329-335`, `:517`
- Test: `backend/tests/test_khoan_api.py`, `backend/tests/test_cong_bo_phieu_va_de_khoan.py`

**Interfaces:**
- Consumes: `khoan_snapshot` chỉ có `{rate_id, ten, cong_thuc_gio}` (Task 3).
- Produces: payload bước lệnh còn `khoan_rate_id`, `khoan_ten`, `khoan_chon_duoc` (mỗi lựa chọn
  còn `{id, ten}` + các khoá định mức, KHÔNG còn `don_vi`/`don_gia`/`*_du_kien`);
  `xem_truoc_buoc()` trả `{step_key, may_id, so_nhan_cong_tieu_chuan, chiem_may_phut,
  thoi_luong_dien_giai}` — không còn khoá `khoan`. `LsxService` không còn phương thức
  `don_gia_hieu_dung`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_khoan_api.py`:

```python
def test_buoc_lenh_khong_con_o_tien_nao(client, lsx_co_buoc_khoan):
    """Kế hoạch VẪN chọn đầu việc chi tiết — nhưng không hiện tiền, vì tiền không còn tính ở đây."""
    lsx_id, step_key = lsx_co_buoc_khoan
    r = client.get(f"/api/lsx/{lsx_id}")
    assert r.status_code == 200
    d = r.json()

    assert "khoan_tien_tong" not in d
    buoc = next(b for b in d["cong_doans"] if b["step_key"] == step_key)
    assert buoc["khoan_rate_id"] is not None, "đầu việc đã chọn phải còn nguyên"
    assert buoc["khoan_ten"]
    for khoa in ("khoan_don_vi", "khoan_don_gia", "khoan_sl", "khoan_don_vi_sl",
                 "khoan_tien", "khoan_dien_giai", "khoan_thieu", "khoan_ly_do"):
        assert khoa not in buoc, khoa
    for chon in buoc["khoan_chon_duoc"]:
        for khoa in ("don_gia", "don_vi", "tien_du_kien", "sl_du_kien", "dien_giai_du_kien"):
            assert khoa not in chon, khoa


def test_xem_truoc_buoc_khong_tra_khoan(client, lsx_co_buoc_khoan):
    lsx_id, step_key = lsx_co_buoc_khoan
    r = client.post(f"/api/lsx/{lsx_id}/xem-truoc-buoc",
                    json={"step_key": step_key, "may_id": None})
    assert r.status_code == 200
    assert "khoan" not in r.json()
    assert "chiem_may_phut" in r.json(), "giờ chạy vẫn phải còn — định mức giữ nguyên"


def test_lsx_service_khong_con_don_gia_hieu_dung():
    from app.services.lsx_service import LsxService

    for ten in ("don_gia_hieu_dung", "_khoan_derived", "_khoan_tu_kh"):
        assert not hasattr(LsxService, ten), ten
```

*Tên fixture + đường endpoint `xem-truoc-buoc` phải đọc lại từ đầu `tests/test_khoan_api.py` và
`backend/app/routers/lsx.py` trước khi viết — dùng đúng tên đang có, đừng đẻ fixture mới.*

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_khoan_api.py -q`
Expected: FAIL — `assert "khoan_tien_tong" not in d`.

- [ ] **Step 3: Xoá ba hàm tiền khỏi `lsx_service.py`**

Xoá trọn:
- `def _khoan_derived(self, cd, quy_cach)` (dòng ~929, 11 dòng)
- `def don_gia_hieu_dung(self, cd, quy_cach)` (dòng ~1227, ~25 dòng)
- `def _khoan_tu_kh(self, cd, kh, quy_cach)` (dòng ~1253 tới hết hàm, gồm cả nhánh
  `cong_thuc_ra_tien` trả `{"khoan_sl": None, ...}` ở ~1199-1212)

Sau đó `grep -n "_khoan_tu_kh\|_khoan_derived\|don_gia_hieu_dung\|cong_thuc_ra_tien\|tien_khoan" backend/app`
và dọn mọi nơi gọi còn lại. `cong_thuc_ra_tien` (`bien_cong_thuc.py:252`) và `tien_khoan` **giữ**
nếu còn nơi khác dùng (danh mục), xoá nếu không — kiểm bằng grep, đừng đoán.

- [ ] **Step 4: Dọn payload + schema**

`lsx_service.py:893-898` — bỏ khối `if buoc is not None: item.update({...tien_du_kien...})` trong
`_dau_viec_option_dicts`, và bỏ hai khoá `"don_vi"` / `"don_gia"` của `item` (dòng ~889-891). Lựa
chọn đầu việc còn `{"id", "ten"}` + các khoá định mức + vật tư bung.

`lsx_service.py:2747-2755` — payload bước còn:

```python
            # --- Đầu việc khoán: CHỈ phần GHIM (tên việc kế hoạch đã chọn). Không có tiền ở tầng
            #     lệnh nữa (11/09/2026) — kế toán lương tra bảng giá theo `khoan_rate_id`.
            "khoan_rate_id": kh.get("rate_id"),
            "khoan_ten": kh.get("ten"),
            "khoan_chon_duoc": self._dau_viec_option_dicts(
                cd_obj, cd.department_id, buoc=cd, quy_cach=quy_cach),
```

`lsx_service.py:2548` — xoá dòng `"khoan_tien_tong": ...` + 2 dòng chú thích trên nó.

`lsx_service.py:1011` — trong `xem_truoc_buoc` xoá khoá `"khoan": self._khoan_tu_kh(...)` + 2 dòng
chú thích.

`backend/app/schemas/lsx.py` — xoá `khoan_don_vi` (`:317`), `khoan_don_gia` (`:318`), `khoan_sl`
(`:329`), `khoan_don_vi_sl` (`:330`), `khoan_dien_giai` (`:332`), `khoan_thieu` (`:334`),
`khoan_ly_do` (`:335`), `khoan_tien_tong` (`:517`).

- [ ] **Step 5: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_khoan_api.py tests/test_cong_bo_phieu_va_de_khoan.py tests/test_san_xuat_release.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/lsx_service.py backend/app/schemas/lsx.py backend/tests/test_khoan_api.py
git commit -m "lsx_service: gỡ tiền khoán khỏi tầng lệnh, giữ chọn đầu việc và định mức giờ"
```

---

### Task 5: Gỡ tiền khoán khỏi BÀI GHÉP

**Files:**
- Modify: `backend/app/services/bai_ghep_service.py:899-928` (bước chung ghim đầu việc)
- Modify: `backend/app/schemas/bai_ghep.py:388-398`
- Test: `backend/tests/test_bai_ghep*.py` (dùng file có sẵn cho bước chung — kiểm bằng
  `ls backend/tests | grep bai_ghep`)

**Interfaces:**
- Consumes: `khoan_snapshot` (Task 3), `_dau_viec_option_dicts` đã dọn (Task 4).
- Produces: dict bước chung bài ghép còn `khoan_rate_id`, `khoan_ten`, `khoan_chon_duoc`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào file test bước chung bài ghép:

```python
def test_buoc_chung_bai_ghep_khong_con_o_tien(client, bai_ghep_co_buoc_chung):
    bg_id = bai_ghep_co_buoc_chung
    r = client.get(f"/api/bai-ghep/{bg_id}/so-do")
    assert r.status_code == 200
    for g in r.json()["gop"]:
        assert "khoan_rate_id" in g, "đầu việc đã chọn phải còn"
        for khoa in ("khoan_don_vi", "khoan_don_gia", "khoan_sl", "khoan_don_vi_sl",
                     "khoan_tien", "khoan_dien_giai", "khoan_thieu", "khoan_ly_do"):
            assert khoa not in g, khoa
```

*Tên fixture + đường endpoint `so-do` phải đọc lại từ file test bài ghép đang có.*

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_bai_ghep_so_do.py -q` *(đổi tên file theo thực tế)*
Expected: FAIL — khoá tiền vẫn còn.

- [ ] **Step 3: Sửa `bai_ghep_service.py`**

Hàm dựng dict bước chung (dòng ~920-932) còn:

```python
        svc = self._lsx_svc()
        cd_obj = self.db.get(CongDoan, c.cong_doan_id) if c.cong_doan_id else None
        kh = c.khoan_json or {}
        return {
            # Đầu việc kế hoạch đã chọn — TÊN việc, không có tiền (11/09/2026, spec
            # "Sản xuất chỉ ghi số lượng"). Bài ghép là kế hoạch, cùng luật với bước lệnh.
            "khoan_rate_id": kh.get("rate_id"),
            "khoan_ten": kh.get("ten"),
            "khoan_chon_duoc": svc._dau_viec_option_dicts(
                cd_obj, c.department_id, buoc=c, quy_cach=quy_cach,
            ),
        }
```

Sửa docstring hàm đó: xoá đoạn nói về `khoan_thieu` / `BIEN_KHONG_CO_O_BAI` cho tiền, giữ phần nói
về quy cách tờ ghép nếu còn dùng cho giờ chạy.

Dòng `:899` (`chung.khoan_json = khoan_snapshot(rate, dm) ...`) và `:904`
(`chung.khoan_json.update(_dinh_muc_snapshot(dm))`) và `:908`
(`chung.don_vi_nang_suat = dich_gio_cua_khoan(chung.khoan_json)[0]`) **giữ nguyên** — đó là đường
định mức GIỜ, không phải tiền.

`backend/app/schemas/bai_ghep.py` — xoá `khoan_don_vi` (`:390`), `khoan_don_gia` (`:391`),
`khoan_sl` (`:393`), `khoan_don_vi_sl` (`:394`), `khoan_tien` (`:395`), `khoan_dien_giai` (`:396`),
`khoan_thieu` (`:397`), `khoan_ly_do` (`:398`).

- [ ] **Step 4: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_bai_ghep_so_do.py tests/test_khoan_dau_viec.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bai_ghep_service.py backend/app/schemas/bai_ghep.py backend/tests/
git commit -m "bài ghép: bước chung ghim đầu việc, bỏ ô tiền khoán"
```

---

### Task 6: Xoá chuỗi thưởng tổ trưởng + seam lương về 0

**Files:**
- Delete: `backend/app/services/san_xuat/thuong_to_truong.py`,
  `backend/app/repositories/thuong_to_truong_repo.py`
- Modify: `backend/app/routers/san_xuat.py:101`, `:117`, `:1299-1310`
- Modify: `backend/app/schemas/san_xuat.py:1056-1064` (xoá `ThuongToTruongOut`)
- Modify: nơi đóng nhóm gọi `thuong_to_truong.ghi(...)` — tìm bằng
  `grep -rn "thuong_to_truong" backend/app/services/san_xuat/`
- Modify: `backend/app/repositories/production_output_repo.py`
- Modify: `backend/app/models/piece_work.py:108-110` (chú thích nói "ĐÃ NỐI VÀO LUỒNG" — nay sai)
- Modify: `docs/CONG_THUC_TINH_LUONG.md` §6.1
- Test: `backend/tests/test_san_xuat_dong_nhom.py`, `backend/tests/test_san_xuat_g5_tich_hop.py`

**Interfaces:**
- Consumes: bảng `san_xuat_thuong_to_truong` đã bị xoá (Task 1).
- Produces: `ProductionOutputRepository.list_nguoi_by_period(year, month) -> list[_DongKhoan]`
  vẫn trả **dòng sản lượng thật** nhưng `unit_price=0.0`; không còn route
  `GET /api/san-xuat/kho/nhom/{id}/thuong-to-truong`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_san_xuat_dong_nhom.py`:

```python
def test_dong_nhom_khong_con_ghi_thuong_to_truong(db, nhom_du_dieu_kien_dong, client):
    """Đóng nhóm là việc của SẢN XUẤT; thưởng/phạt tổ trưởng là tiền, nên nó rời khỏi đây."""
    nhom_id = nhom_du_dieu_kien_dong
    r = client.post(f"/api/san-xuat/kho/nhom/{nhom_id}/dong")
    assert r.status_code == 200

    assert client.get(f"/api/san-xuat/kho/nhom/{nhom_id}/thuong-to-truong").status_code == 404

    import importlib
    try:
        importlib.import_module("app.services.san_xuat.thuong_to_truong")
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError("module thuong_to_truong phải bị xoá")


def test_seam_luong_tra_san_luong_nhung_don_gia_0(db, phan_bo_da_chot):
    """Sản lượng theo người là dữ liệu THẬT, vẫn chảy sang lương. Giá thì chưa — cột `khoan` về 0
    tới khi dựng màn "Khoán theo kỳ" của kế toán."""
    from app.repositories.production_output_repo import ProductionOutputRepository

    nam, thang = phan_bo_da_chot
    rows = ProductionOutputRepository(db).list_nguoi_by_period(nam, thang)
    assert rows, "phải có dòng sản lượng"
    assert all(r.quantity > 0 for r in rows)
    assert all(r.unit_price == 0.0 for r in rows)
```

*Tên fixture `nhom_du_dieu_kien_dong` / `phan_bo_da_chot` phải đọc lại từ chính hai file test đó và
dùng đúng fixture đang có.*

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_san_xuat_dong_nhom.py -q`
Expected: FAIL — route thưởng còn trả 200.

- [ ] **Step 3: Xoá chuỗi backend**

```bash
git rm backend/app/services/san_xuat/thuong_to_truong.py backend/app/repositories/thuong_to_truong_repo.py
```

`backend/app/routers/san_xuat.py`: xoá import `ThuongToTruongOut` (`:101`), import
`thuong_to_truong` (`:117`), và trọn route `thuong_to_truong_nhom` (`:1299-1310`).

`backend/app/schemas/san_xuat.py`: xoá class `ThuongToTruongOut` (`:1056` trở xuống hết class).

Trong service đóng nhóm: xoá lời gọi `thuong_to_truong.ghi(db, nhom_id=..., actor=...)` và mọi
dòng chú thích nói về nó. Đóng nhóm còn đúng việc đóng nhóm.

`backend/app/models/piece_work.py:108-110`: sửa chú thích của `PieceLeaderBonusBracket` — bảng bậc
**giữ** (là cấu hình LƯƠNG), nhưng đường nối vào sản xuất đã cắt:

```python
    CHƯA NỐI VÀO LUỒNG NÀO (11/09/2026): đường cũ đi qua `services/san_xuat/thuong_to_truong.py`
    lúc ĐÓNG NHÓM đã bị xoá cùng cơ chế tiền khoán ở sản xuất. Bảng bậc này là CẤU HÌNH LƯƠNG,
    màn "Khoán theo kỳ" của kế toán sẽ dùng lại nó để rót vào `payroll_lines.thuong_to_truong`.
```

- [ ] **Step 4: Sửa seam lương**

`backend/app/repositories/production_output_repo.py` — sửa docstring module + hai chỗ tạo
`_DongKhoan`:

```python
"""Nguồn SẢN LƯỢNG THEO NGƯỜI cho bảng lương (§12, seam của `PieceWorkService`).

Repo này biến DÒNG CHIA SẢN LƯỢNG ĐÃ CHỐT (§12.2) + DÒNG BÙ TRỪ đã sang kỳ (§12.3) thành các
"phiếu sản lượng theo người" mà seam cần.

**`unit_price` LUÔN 0 từ 11/09/2026** — và đó là chủ ý, không phải thiếu sót. Sản xuất ghi SỐ
LƯỢNG, kế toán lương đổi ra tiền; ba cột `don_gia` ở tầng sản xuất đã bỏ (mg 0296). Hệ quả phải
nói trước: cột `payroll_lines.khoan` = 0 cho MỌI người tới khi dựng màn "Khoán theo kỳ" của kế
toán lương — màn đó đọc chính các dòng sản lượng ở đây rồi tra `piece_rates` theo kỳ.

Sản lượng thì vẫn THẬT: đó là số tổ đã ghi và đã chốt. Xem
`docs/superpowers/specs/2026-09-11-san-xuat-chi-ghi-so-luong-design.md`.
"""
```

và trong cả hai vòng lặp:

```python
                    unit_price=0.0,   # sản xuất không định giá — xem docstring module
```

- [ ] **Step 5: Sửa doc lương**

`docs/CONG_THUC_TINH_LUONG.md` §6.1 đang nói `khoan` luôn = 0 nhưng nêu LÝ DO đã cũ (repo chưa
được nối). Giữ kết luận, đổi lý do: nay `deps.py` có nối `ProductionOutputRepository` thật, nhưng
đơn giá về 0 theo quyết định 11/09/2026; trỏ tới spec.

- [ ] **Step 6: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_san_xuat_dong_nhom.py tests/test_san_xuat_dong_nhom_api.py tests/test_san_xuat_g5_tich_hop.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A backend/app backend/tests docs/CONG_THUC_TINH_LUONG.md
git commit -m "gỡ chuỗi thưởng tổ trưởng khỏi đóng nhóm; seam lương trả sản lượng, đơn giá 0"
```

---

### Task 7: FE — gỡ mọi ô tiền khoán, đổi nhãn thành "Chia sản lượng"

**Files:**
- Modify: `frontend/src/pages/ThsxExecPanels.tsx:404-520` (`PhanBoBlock`)
- Modify: `frontend/src/api/client.ts` — `SxPhanBo` (bỏ `don_gia`, `don_gia_tu_cong_thuc`, `dong[].don_gia`,
  `bu_tru[].don_gia`), `LsxCongDoan*`/`LsxDauViecOption` (bỏ `khoan_don_vi`, `khoan_don_gia`,
  `khoan_sl`, `khoan_don_vi_sl`, `khoan_tien`, `khoan_dien_giai`, `khoan_thieu`, `khoan_ly_do`),
  `khoan_tien_tong`, `SxThuongToTruong`, `thuongToTruongNhom()`
- Modify: `frontend/src/pages/lsxBuoc.ts:99-102`, `:140-141`, `:240`, `:276-277`, `:347`, `:356`
- Modify: `frontend/src/pages/LsxBuocDrawer.tsx:296-302`, `:980-1005`
- Modify: `frontend/src/pages/LsxDetailView.tsx:934-940`
- Modify: `frontend/src/pages/LsxRoutingTable.tsx:378`, `:452`, `:462`
- Modify: `frontend/src/pages/BaiGhepBuocChungForm.tsx:162`, `:620-650`
- Modify: `frontend/src/pages/BaiGhep2Page.tsx:734`
- Modify: `frontend/src/pages/ThsxG5.tsx:626` (xoá `ThsxThuongToTruongPanel`),
  `frontend/src/pages/ThsxDrawer.tsx:50`, `:718`, `frontend/src/pages/kcs/KcsChotNhom.tsx:107`, `:161`,
  `frontend/src/pages/ThucHienSxPage.tsx:144` + nơi nạp `thuongTT`
- Modify: `frontend/src/test/baiGhepSoDoFixture.ts:102-105`
- Test: `frontend/src/pages/ThsxChiaSanLuong.test.tsx` (tạo mới)

**Interfaces:**
- Consumes: `SxPhanBo` không còn khoá tiền (BE Task 2).
- Produces: component `PhanBoBlock` đổi tiêu đề thành `"Chia sản lượng"`; bảng còn 4 cột
  `Người / SL / Bậc / Phút`.

- [ ] **Step 1: Viết test đỏ**

Tạo `frontend/src/pages/ThsxChiaSanLuong.test.tsx`:

```tsx
// Khối chia sản lượng của một mẻ: KHÔNG được có ô tiền nào (11/09/2026 — sản xuất chỉ ghi số lượng).
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PhanBoBlock } from "./ThsxExecPanels";
import type { SxBatch, SxPhanBo } from "../api/client";

const batch = {
  id: 1, bat_dau: "2026-09-11T07:00:00", ket_thuc: "2026-09-11T09:00:00",
  tong: 1000, tot: 980, hong: 20, don_vi: "to",
  mo_ta_loi: null, ghi_chu: null, version: 1, nguoi_tham_gia: [], lot_vao: [],
} as unknown as SxBatch;

const pb = {
  phan_bo_id: 5, batch_id: 1, trang_thai: "draft", version: 1,
  ngay: "2026-09-11", ky_nam: 2026, ky_thang: 9,
  q_tra_luong: 980, don_vi_tra_luong: "to",
  q_ban_dia: 980, don_vi_ban_dia: "to", tong_ty_le_ho_tro: 0,
  can_chot: true, canh_bao: [], thieu_cham_cong: [], loai_tru: [], bu_tru: [],
  dong: [
    { employee_id: 11, ho_ten: "Lê Văn A", department_id: 7, la_ho_tro: false,
      ngay: "2026-09-11", so_luong_tra_luong: 520, so_luong_ban_dia: 520,
      trong_so: 156, phut_thuc_te: 120, he_so_bac: 1.3 },
    { employee_id: 12, ho_ten: "Trần Thị B", department_id: 7, la_ho_tro: false,
      ngay: "2026-09-11", so_luong_tra_luong: 460, so_luong_ban_dia: 460,
      trong_so: 138, phut_thuc_te: 120, he_so_bac: 1.15 },
  ],
} as unknown as SxPhanBo;

const exec = {
  tinhPhanBo: vi.fn(), chotPhanBo: vi.fn(), moLaiPhanBo: vi.fn(),
  loaiTru: vi.fn(), goLoaiTru: vi.fn(),
} as never;

describe("Chia sản lượng", () => {
  it("đổi nhãn khỏi 'Phân bổ lương' và không hiện ô tiền nào", () => {
    render(
      <PhanBoBlock b={batch} pb={pb} canAssign busy={false}
        tenNguoi={new Map()} hoTroUngVien={[]} exec={exec} />,
    );
    expect(screen.getByText("Chia sản lượng")).toBeInTheDocument();
    expect(screen.queryByText(/Phân bổ lương/)).toBeNull();
    expect(screen.queryByText(/đơn giá/i)).toBeNull();
    expect(screen.queryByText(/theo công thức/)).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /Đơn giá/i })).toBeNull();
  });

  it("hiện sản lượng, bậc và PHÚT của từng người", () => {
    render(
      <PhanBoBlock b={batch} pb={pb} canAssign busy={false}
        tenNguoi={new Map()} hoTroUngVien={[]} exec={exec} />,
    );
    expect(screen.getByRole("columnheader", { name: /Phút/i })).toBeInTheDocument();
    expect(screen.getByText("Lê Văn A")).toBeInTheDocument();
    expect(screen.getByText("520")).toBeInTheDocument();
  });
});
```

`PhanBoBlock` hiện là hàm nội bộ ⇒ thêm `export` cho nó trong `ThsxExecPanels.tsx`.

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd frontend && npx vitest run src/pages/ThsxChiaSanLuong.test.tsx`
Expected: FAIL — không import được `PhanBoBlock` / không thấy chữ "Chia sản lượng".

- [ ] **Step 3: Sửa `PhanBoBlock`**

Trong `frontend/src/pages/ThsxExecPanels.tsx`:

- Đổi comment mốc `// ─── PHÂN BỔ LƯƠNG theo mẻ (§12) ───` thành `// ─── CHIA SẢN LƯỢNG theo mẻ (§12) ───`.
- `export function PhanBoBlock(...)`.
- Nhánh `if (!pb)`: đổi chữ `"Chưa phân bổ lương cho mẻ này."` → `"Chưa chia sản lượng cho mẻ này."`
  và nút `"Tính phân bổ"` → `"Chia sản lượng"`.
- Header: `<span className="thsx-x-pb__ttl">Chia sản lượng</span>`.
- Khối `thsx-x-pb__sum`: bỏ trọn `<span title={pb.don_gia_tu_cong_thuc ? ... }>…đơn giá…</span>`;
  dòng đầu đổi nhãn `Q trả lương` → `Sản lượng chia`.
- Bảng: `<tr><th>Người</th><th className="r">Sản lượng</th><th className="r">Bậc</th><th className="r">Phút</th></tr>`
  và ô cuối của mỗi dòng đổi từ `{num(d.don_gia)}` thành
  `{d.phut_thuc_te != null ? num(d.phut_thuc_te) : "—"}`.
- Các chữ còn lại: `"Giữ ở nháp — chưa chốt được"` giữ; `"Loại khỏi lương"` → `"Loại khỏi mẻ"`;
  `"Đã loại khỏi lương batch"` → `"Đã loại khỏi mẻ"`; tooltip `"Tính lại theo roster/sản lượng mới"`
  giữ. `BuTruForm` giữ (bù trừ là bù SẢN LƯỢNG, không phải tiền) — kiểm lại chữ trong form đó và
  bỏ chữ "lương" nếu có.

- [ ] **Step 4: Dọn type + các màn lệnh / bài ghép**

Theo danh sách file ở đầu task. Cách làm an toàn: sửa `client.ts` TRƯỚC rồi chạy
`npx tsc --noEmit` — trình biên dịch sẽ chỉ đúng từng chỗ còn đọc khoá đã bỏ.

- `LsxDetailView.tsx:934-940`: xoá trọn khối `{d.khoan_tien_tong > 0 && (...)}` (ô "công thợ dự
  kiến" của cả lệnh).
- `LsxBuocDrawer.tsx:296-302` + `:980-1005`: xoá `khoanXt` / `khoanLive` và khối hiện tiền; **giữ**
  ô chọn đầu việc (`khoan_rate_id` + `khoan_chon_duoc`) và ô năng suất/kíp.
- `LsxRoutingTable.tsx:452`, `:462`: bỏ `khoan_xem_truoc` khỏi `patch(...)`.
- `BaiGhepBuocChungForm.tsx` + `BaiGhep2Page.tsx:734`: bỏ `tienHien` / `commonStepLabor` và khối
  hiện tiền; giữ ô chọn đầu việc.
- `ThsxG5.tsx:626`: xoá `ThsxThuongToTruongPanel`; `ThsxDrawer.tsx:50,:718`,
  `kcs/KcsChotNhom.tsx:107,:161`, `ThucHienSxPage.tsx:144` + nơi gọi `api.sanXuat.thuongToTruongNhom`:
  xoá state + panel + lời gọi.
- `test/baiGhepSoDoFixture.ts:102-105`: xoá 4 khoá tiền.

- [ ] **Step 5: Soi chữ tiếng Việt còn sót**

```bash
cd frontend && grep -rn "đơn giá\|Đơn giá\|tiền công\|Phân bổ lương\|thưởng tổ trưởng" src/pages/ThsxExecPanels.tsx src/pages/ThsxDrawer.tsx src/pages/ThsxG5.tsx src/pages/LsxBuocDrawer.tsx src/pages/BaiGhepBuocChungForm.tsx
```

Kết quả mong đợi: rỗng.

- [ ] **Step 6: Chạy test + biên dịch — phải xanh**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/ThsxChiaSanLuong.test.tsx src/pages/ThsxCards.test.tsx src/pages/ThsxDanhSach.test.tsx src/pages/lsxBuoc.test.ts src/pages/BaiGhep2Page.test.tsx`
Expected: `tsc` không lỗi; vitest PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "FE: gỡ mọi ô tiền khoán khỏi bàn tổ/lệnh/bài ghép, đổi nhãn thành Chia sản lượng"
```

---

# ĐỢT B — Bàn tổ đổi trục sang LỆNH / BÀI GHÉP

## File structure của đợt B

| File | Trách nhiệm |
|---|---|
| `backend/app/repositories/san_xuat_repo.py` | `lenh_cua_to_phan_trang()` — GROUP BY + LIMIT ở SQL |
| `backend/app/services/san_xuat/board.py` | `work_items()` nhận `nhom` / `trang` / `co_trang` / cửa sổ ngày |
| `backend/app/schemas/san_xuat.py` | `LenhNhomOut`, `TrangOut`, `WorkItemsOut` mở rộng |
| `backend/app/routers/san_xuat.py` | query params mới của `GET /work-items` |
| `frontend/src/pages/ThsxLenhGroups.tsx` | **MỚI** — tầng LỆNH dùng chung cho view thẻ + danh sách |
| `frontend/src/pages/ThsxCards.tsx` · `ThsxDanhSach.tsx` | nhận `lenh` thay vì 3 khúc cửa sổ |
| `frontend/src/pages/ThucHienSxPage.tsx` | nạp theo trang, giữ trang khi SSE bump |

---

### Task 8: Repo — gom + phân trang theo LỆNH ở máy chủ

**Files:**
- Modify: `backend/app/repositories/san_xuat_repo.py` (thêm sau `cong_viec_cua_to`, dòng ~413)
- Test: `backend/tests/test_san_xuat_lenh_phan_trang.py` (tạo mới)

**Interfaces:**
- Consumes: `SanXuatCongViec`, `SanXuatGoiPhatHanh`, `GOI_DANG_PHAT_HANH`, `CV_HOAN_THANH`,
  `SanXuatRepository._duoc_giao_cho(employee_id)` (`:470`).
- Produces:
  ```python
  KhoaLenh = tuple[str, int | None]   # ("lsx"|"bai_ghep", id)
  def lenh_cua_to_phan_trang(
      self, department_ids: set[int], *, la_kcs: bool | None = None,
      employee_id: int | None = None, trang: int = 1, co_trang: int = 20,
  ) -> tuple[list[tuple[KhoaLenh, datetime | None, datetime | None]], int]
  def cong_viec_cua_lenh(
      self, department_ids: set[int], khoa: list[KhoaLenh], *,
      la_kcs: bool | None = None, employee_id: int | None = None,
  ) -> list[SanXuatCongViec]
  ```

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/test_san_xuat_lenh_phan_trang.py`:

```python
"""Bàn tổ đổi trục sang LỆNH: gom nhóm + cắt trang phải ở MÁY CHỦ, và đơn vị trang là LỆNH.

Cắt trang theo BƯỚC thì một lệnh bị xé qua hai trang — tổ trưởng mở trang 2 thấy một công đoạn
trơ trọi không biết của lệnh nào, đúng thứ chủ xưởng bác.
"""
from app.repositories.san_xuat_repo import SanXuatRepository


def test_gom_theo_lenh_va_cat_trang_theo_lenh(db, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    repo = SanXuatRepository(db)

    trang1, tong = repo.lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=2)
    assert tong == 3
    assert len(trang1) == 2

    trang2, tong2 = repo.lenh_cua_to_phan_trang({to_id}, trang=2, co_trang=2)
    assert tong2 == 3
    assert len(trang2) == 1
    assert {k for k, _, _ in trang1} & {k for k, _, _ in trang2} == set(), "trang không được trùng lệnh"


def test_sap_theo_buoc_som_nhat_cua_to_lenh_chua_xep_gio_don_cuoi(db, to_lenh_gio_lech):
    """Sắp theo giờ dự kiến của bước SỚM NHẤT của TỔ trong lệnh đó — không phải giờ của lệnh."""
    to_id, mong_doi = to_lenh_gio_lech   # mong_doi: list[KhoaLenh] đúng thứ tự
    rows, _ = SanXuatRepository(db).lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=50)
    assert [k for k, _, _ in rows] == mong_doi


def test_bai_ghep_la_mot_dong_khong_xe_theo_lenh_thanh_vien(db, to_co_bai_ghep_2_lenh):
    to_id = to_co_bai_ghep_2_lenh
    rows, tong = SanXuatRepository(db).lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=50)
    assert tong == 1
    assert rows[0][0][0] == "bai_ghep"


def test_lay_dung_buoc_cua_cac_lenh_trong_trang(db, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    repo = SanXuatRepository(db)
    trang1, _ = repo.lenh_cua_to_phan_trang({to_id}, trang=1, co_trang=2)
    khoa = [k for k, _, _ in trang1]
    rows = repo.cong_viec_cua_lenh({to_id}, khoa)
    assert rows
    for cv in rows:
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id else ("lsx", cv.lsx_id)
        assert k in khoa


def test_loc_theo_nguoi_duoc_giao_chay_o_SQL_truoc_khi_cat_trang(db, to_co_3_lenh_9_buoc, tho_chi_lam_lenh_thu_3):
    """Thợ chỉ được giao việc ở LỆNH thứ 3. Lọc sau khi cắt trang thì trang 1 rỗng — sai."""
    to_id = to_co_3_lenh_9_buoc
    emp_id = tho_chi_lam_lenh_thu_3
    rows, tong = SanXuatRepository(db).lenh_cua_to_phan_trang(
        {to_id}, employee_id=emp_id, trang=1, co_trang=2)
    assert tong == 1
    assert len(rows) == 1
```

*Bốn fixture (`to_co_3_lenh_9_buoc`, `to_lenh_gio_lech`, `to_co_bai_ghep_2_lenh`,
`tho_chi_lam_lenh_thu_3`) dựng bằng đúng helper phát hành mà `tests/test_san_xuat_board.py` đang
dùng — đọc file đó trước, tái dùng helper, đừng tự INSERT tay.*

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_san_xuat_lenh_phan_trang.py -q`
Expected: FAIL — `AttributeError: 'SanXuatRepository' object has no attribute 'lenh_cua_to_phan_trang'`.

- [ ] **Step 3: Viết repo**

Thêm vào `backend/app/repositories/san_xuat_repo.py` ngay sau `cong_viec_cua_to`:

```python
    # ---- Bàn tổ trục LỆNH (spec 2026-09-11) --------------------------------------------------

    @staticmethod
    def _khoa_lenh_cols():
        """(cột LOẠI nguồn, cột ID nguồn) suy ngay trong SQL — cùng luật với `board._item_dict`.

        Bài ghép THẮNG lệnh khi bước đeo cả hai: bài ghép chạy MỘT lần trên MỘT tờ, tổ nhìn nó là
        một việc. Xẻ nó theo từng lệnh thành viên là đẻ ra mấy dòng cho một lần chạy máy.
        """
        from sqlalchemy import case, literal

        co_bg = SanXuatCongViec.bai_ghep_id.is_not(None)
        loai = case((co_bg, literal("bai_ghep")), else_=literal("lsx"))
        nid = case((co_bg, SanXuatCongViec.bai_ghep_id), else_=SanXuatCongViec.lsx_id)
        return loai, nid

    def lenh_cua_to_phan_trang(
        self,
        department_ids: set[int],
        *,
        la_kcs: bool | None = None,
        employee_id: int | None = None,
        trang: int = 1,
        co_trang: int = 20,
    ) -> tuple[list[tuple[tuple[str, int | None], "datetime | None", "datetime | None"]], int]:
        """Một TRANG các LỆNH/BÀI GHÉP mà tổ phải làm + tổng số lệnh.

        Mỗi phần tử: `((loai, id), sớm_nhất, muộn_nhất)` — hai mốc là giờ dự kiến của bước SỚM/MUỘN
        NHẤT **của chính tổ này** trong lệnh đó, không phải mốc của cả lệnh: bàn tổ sắp theo thứ tự
        việc đến tay TỔ.

        Cắt trang theo LỆNH (không theo bước) và cắt ở SQL. `employee_id` (thợ mở bàn) lọc NGAY
        trong câu gom — lọc sau khi cắt trang thì trang 1 có thể rỗng trong khi trang 3 đầy việc.

        Lệnh chưa xếp giờ dồn CUỐI (`NULLS LAST` viết tay bằng CASE cho chạy cả PG lẫn SQLite).
        """
        if not department_ids:
            return [], 0
        from sqlalchemy import func, select as sa_select

        loai, nid = self._khoa_lenh_cols()
        som = func.min(SanXuatCongViec.du_kien_bat_dau)
        muon = func.max(SanXuatCongViec.du_kien_ket_thuc)
        dieu_kien = [
            SanXuatCongViec.department_id.in_(department_ids),
            SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
        ]
        if la_kcs is not None:
            dieu_kien.append(SanXuatCongViec.la_kcs.is_(la_kcs))
        if (giao := self._duoc_giao_cho(employee_id)) is not None:
            dieu_kien.append(giao)

        nhom = (
            sa_select(loai.label("loai"), nid.label("nid"),
                      som.label("som"), muon.label("muon"))
            .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
            .where(*dieu_kien)
            .group_by(loai, nid)
        )
        tong = self.db.scalar(
            sa_select(func.count()).select_from(nhom.subquery())
        ) or 0
        from sqlalchemy import case as sa_case

        co_trang = max(1, min(int(co_trang or 20), 100))
        trang = max(1, int(trang or 1))
        rows = self.db.execute(
            nhom.order_by(sa_case((som.is_(None), 1), else_=0), som, nid)
            .limit(co_trang)
            .offset((trang - 1) * co_trang)
        ).all()
        return [((r.loai, r.nid), r.som, r.muon) for r in rows], int(tong)

    def cong_viec_cua_lenh(
        self,
        department_ids: set[int],
        khoa: list[tuple[str, int | None]],
        *,
        la_kcs: bool | None = None,
        employee_id: int | None = None,
    ) -> list[SanXuatCongViec]:
        """Mọi bước CỦA TỔ thuộc các lệnh/bài ghép trong danh sách khoá — một truy vấn cho cả trang.

        Ghép điều kiện bằng ba nhánh OR đích danh thay vì `IN` trên tuple: `IN ((a,b),…)` không
        portable giữa Postgres và SQLite, mà phân trang thì bắt buộc chạy đúng trên cả hai.
        """
        if not department_ids or not khoa:
            return []
        from sqlalchemy import false, or_

        bg_ids = {i for loai, i in khoa if loai == "bai_ghep" and i is not None}
        lsx_ids = {i for loai, i in khoa if loai == "lsx" and i is not None}
        co_mo_coi = any(loai == "lsx" and i is None for loai, i in khoa)

        nhanh = []
        if bg_ids:
            nhanh.append(SanXuatCongViec.bai_ghep_id.in_(bg_ids))
        if lsx_ids:
            nhanh.append(
                (SanXuatCongViec.bai_ghep_id.is_(None))
                & (SanXuatCongViec.lsx_id.in_(lsx_ids))
            )
        if co_mo_coi:
            nhanh.append(
                (SanXuatCongViec.bai_ghep_id.is_(None))
                & (SanXuatCongViec.lsx_id.is_(None))
            )

        dieu_kien = [
            SanXuatCongViec.department_id.in_(department_ids),
            SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
            or_(*nhanh) if nhanh else false(),
        ]
        if la_kcs is not None:
            dieu_kien.append(SanXuatCongViec.la_kcs.is_(la_kcs))
        if (giao := self._duoc_giao_cho(employee_id)) is not None:
            dieu_kien.append(giao)

        rows = list(
            self.db.execute(
                select(SanXuatCongViec)
                .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
                .where(*dieu_kien)
            ).scalars()
        )
        rows.sort(key=lambda cv: (cv.du_kien_bat_dau is None, cv.du_kien_bat_dau, cv.id))
        return rows
```

Thêm `employee_id` vào `cong_viec_cua_to` (cho chế độ `phang` của Gantt) bằng đúng hai dòng:

```python
        if (giao := self._duoc_giao_cho(employee_id)) is not None:
            q = q.where(giao)
```

- [ ] **Step 4: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_san_xuat_lenh_phan_trang.py -q`
Expected: PASS (6 bài).

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/san_xuat_repo.py backend/tests/test_san_xuat_lenh_phan_trang.py
git commit -m "san_xuat_repo: gom + phân trang bàn tổ theo lệnh/bài ghép ở máy chủ"
```

---

### Task 9: Service + schema + router — `work_items` trả nhóm LỆNH

**Files:**
- Modify: `backend/app/services/san_xuat/board.py:274-305` (`work_items`), `:61-80` (`_la_tho`,
  `_loc_viec_cua_tho`)
- Modify: `backend/app/schemas/san_xuat.py:116-118` (`WorkItemsOut`)
- Modify: `backend/app/routers/san_xuat.py:371-386`
- Test: `backend/tests/test_san_xuat_board_api.py`

**Interfaces:**
- Consumes: `SanXuatRepository.lenh_cua_to_phan_trang` / `.cong_viec_cua_lenh` (Task 8).
- Produces:
  ```python
  def work_items(db, user, authz, *, team_id: int, mode: str = "production",
                 nhom: str = "lenh", trang: int = 1, co_trang: int = 20,
                 tu_ngay: date | None = None, den_ngay: date | None = None) -> dict
  ```
  `nhom="lenh"` → `{"team_id", "nhom": "lenh", "trang": {...}, "lenh": [LenhNhomOut...]}`;
  `nhom="phang"` → `{"team_id", "nhom": "phang", "cong_viec": [WorkItemOut...]}` (hình CŨ, giữ
  nguyên khoá `cong_viec` để Gantt không phải sửa).

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_san_xuat_board_api.py`:

```python
def test_work_items_mac_dinh_tra_nhom_lenh(client_to_truong, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    r = client_to_truong.get(f"/api/san-xuat/work-items?team_id={to_id}&co_trang=2")
    assert r.status_code == 200
    d = r.json()
    assert d["nhom"] == "lenh"
    assert d["trang"] == {"trang": 1, "co_trang": 2, "tong": 3}
    assert len(d["lenh"]) == 2
    l0 = d["lenh"][0]
    assert l0["nguon_loai"] in ("lsx", "bai_ghep")
    assert l0["nguon_ma"]
    assert l0["so_viec"] == len(l0["cong_viec"])
    assert set(l0["digest"]) == {"released", "running", "paused", "completed"}
    # Thẻ việc bên trong giữ ĐÚNG hình cũ — bốn view đọc chung một hình.
    assert {"id", "ten_cong_doan", "trang_thai", "du_kien_bat_dau", "quy_cach"} <= set(l0["cong_viec"][0])


def test_work_items_che_do_phang_giu_hinh_cu_cho_gantt(client_to_truong, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    r = client_to_truong.get(
        f"/api/san-xuat/work-items?team_id={to_id}&nhom=phang"
        "&tu_ngay=2026-09-01&den_ngay=2026-09-30")
    assert r.status_code == 200
    d = r.json()
    assert d["nhom"] == "phang"
    assert isinstance(d["cong_viec"], list) and d["cong_viec"]
    assert "lenh" not in d or d["lenh"] == []


def test_work_items_co_trang_bi_kep_tran_100(client_to_truong, to_co_3_lenh_9_buoc):
    to_id = to_co_3_lenh_9_buoc
    r = client_to_truong.get(f"/api/san-xuat/work-items?team_id={to_id}&co_trang=9999")
    assert r.status_code == 422, "trần phải do schema chặn, không để service tự bóp im lặng"
```

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_san_xuat_board_api.py -q`
Expected: FAIL — `KeyError: 'nhom'`.

- [ ] **Step 3: Viết schema**

`backend/app/schemas/san_xuat.py` — thay `WorkItemsOut` (`:116-118`):

```python
class TrangOut(BaseModel):
    """Vị trí trang + tổng số LỆNH (không phải tổng số bước) — đơn vị trang của bàn tổ là LỆNH."""
    trang: int
    co_trang: int
    tong: int


class LenhNhomOut(BaseModel):
    """Một LỆNH SX (hoặc BÀI GHÉP) trên bàn tổ, kèm các công đoạn CỦA TỔ trong lệnh ấy.

    Bài ghép là MỘT dòng, không xẻ theo lệnh thành viên: nó chạy một lần trên một tờ."""
    nguon_loai: str               # "lsx" | "bai_ghep"
    nguon_ma: str
    nguon_ten: str
    lsx_id: int | None = None
    bai_ghep_id: int | None = None
    som_nhat: datetime | None = None   # giờ dự kiến bước SỚM NHẤT của tổ trong lệnh
    muon_nhat: datetime | None = None
    so_viec: int
    digest: dict[str, int]             # released / running / paused / completed
    cong_viec: list[WorkItemOut]


class WorkItemsOut(BaseModel):
    team_id: int
    nhom: str = "lenh"                 # "lenh" (mặc định) | "phang" (Gantt)
    trang: TrangOut | None = None      # chỉ có ở nhom="lenh"
    lenh: list[LenhNhomOut] = []
    cong_viec: list[WorkItemOut] = []  # chỉ có ở nhom="phang" — hình CŨ, Gantt không phải sửa
```

- [ ] **Step 4: Viết service**

`backend/app/services/san_xuat/board.py` — thay `work_items` (dòng 274 tới hết hàm):

```python
def _digest(rows) -> dict[str, int]:
    """Đếm bước theo trạng thái cho nhãn của một lệnh — cùng bốn khoá mà FE `sxDigest` dùng."""
    d = {"released": 0, "running": 0, "paused": 0, "completed": 0}
    for cv in rows:
        d[cv.trang_thai if cv.trang_thai in d else "released"] += 1
    return d


def work_items(
    db: Session, user: User, authz: AuthorizationService, *, team_id: int,
    mode: str = "production",
    nhom: str = "lenh",
    trang: int = 1,
    co_trang: int = 20,
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
) -> dict:
    """Việc đã phát hành của MỘT tổ. Hai hình, chọn bằng `nhom`:

    · `"lenh"` (mặc định) — **bản ghi là LỆNH SX / BÀI GHÉP**, mỗi lệnh một dòng, bên trong là các
      công đoạn của chính tổ này. Chủ xưởng chốt 11/09/2026: *"lệnh hoặc bài ghép thôi, chứ không
      làm sao tôi biết được công đoạn đó cho lệnh nào"*. Gom nhóm + CẮT TRANG ở máy chủ, đơn vị
      trang là LỆNH.
    · `"phang"` — mảng bước phẳng như trước, cho view **Gantt** (trục thời gian không có tầng
      lệnh). Nhận thêm cửa sổ `tu_ngay`/`den_ngay` để Gantt chỉ kéo đúng khoảng đang xem thay vì
      cả bàn.

    THỢ (scope `own`, không phải tổ trưởng) chỉ thấy việc mình được giao — lọc bằng `employee_id`
    ĐẨY XUỐNG SQL, trước cả lúc gom lệnh và cắt trang (§6 spec).
    """
    repo = SanXuatRepository(db)
    _tos, ids = _to_thay_duoc(db, user, authz)
    if team_id not in ids:
        raise PermissionError("Ngoài phạm vi tổ được phép xem.")
    la_kcs = (mode == "kcs")
    emp_id: int | None = None
    if _la_tho(user, authz, next((d for d in _tos if d.id == team_id), None)):
        nv = SanXuatThucThiRepository(db).nhan_vien_theo_user(user.id)
        # Tài khoản chưa nối hồ sơ nhân viên ⇒ KHÔNG có việc nào, không rơi về "thấy hết".
        if nv is None:
            return ({"team_id": team_id, "nhom": "phang", "cong_viec": []} if nhom == "phang"
                    else {"team_id": team_id, "nhom": "lenh",
                          "trang": {"trang": trang, "co_trang": co_trang, "tong": 0}, "lenh": []})
        emp_id = nv.id

    if nhom == "phang":
        rows = repo.cong_viec_cua_to({team_id}, la_kcs=la_kcs, employee_id=emp_id)
        if tu_ngay is not None or den_ngay is not None:
            rows = [cv for cv in rows if _trong_cua_so(cv, tu_ngay, den_ngay)]
        return {"team_id": team_id, "nhom": "phang",
                "cong_viec": _dung_items(db, repo, rows)}

    khoa_trang, tong = repo.lenh_cua_to_phan_trang(
        {team_id}, la_kcs=la_kcs, employee_id=emp_id, trang=trang, co_trang=co_trang)
    khoa = [k for k, _, _ in khoa_trang]
    rows = repo.cong_viec_cua_lenh(
        {team_id}, khoa, la_kcs=la_kcs, employee_id=emp_id)
    items = _dung_items(db, repo, rows)
    item_theo_id = {it["id"]: it for it in items}
    cv_theo_khoa: dict[tuple[str, int | None], list] = {}
    for cv in rows:
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id else ("lsx", cv.lsx_id)
        cv_theo_khoa.setdefault(k, []).append(cv)

    lsx_map = repo.lsx_nhan({i for loai, i in khoa if loai == "lsx" and i})
    bg_map = repo.bai_ghep_nhan({i for loai, i in khoa if loai == "bai_ghep" and i})
    ra: list[dict] = []
    for (loai, nid), som, muon in khoa_trang:
        cvs = cv_theo_khoa.get((loai, nid), [])
        ma, ten = (bg_map if loai == "bai_ghep" else lsx_map).get(nid or 0, ("", ""))
        ra.append({
            "nguon_loai": loai,
            "nguon_ma": ma,
            "nguon_ten": ten,
            "lsx_id": nid if loai == "lsx" else None,
            "bai_ghep_id": nid if loai == "bai_ghep" else None,
            "som_nhat": lich_hien_thi(som),
            "muon_nhat": lich_hien_thi(muon),
            "so_viec": len(cvs),
            "digest": _digest(cvs),
            "cong_viec": [item_theo_id[cv.id] for cv in cvs if cv.id in item_theo_id],
        })
    return {"team_id": team_id, "nhom": "lenh",
            "trang": {"trang": trang, "co_trang": co_trang, "tong": tong},
            "lenh": ra}
```

Tách phần dựng `items` (nguyên khối `lsx_map`…`so_map`…`_item_dict` của bản cũ) thành hàm dùng
chung để hai nhánh không chép nhau:

```python
def _dung_items(db: Session, repo: SanXuatRepository, rows: list) -> list[dict]:
    """Dựng payload thẻ việc cho một tập bước — GỘP mọi truy vấn phụ, không N+1 theo dòng."""
    if not rows:
        return []
    lsx_map = repo.lsx_nhan({cv.lsx_id for cv in rows if cv.lsx_id})
    bg_map = repo.bai_ghep_nhan({cv.bai_ghep_id for cv in rows if cv.bai_ghep_id})
    may_map = repo.may_nhan({cv.may_id for cv in rows if cv.may_id})
    nhom_map = repo.nhom_nhan({cv.nhom_id for cv in rows if cv.nhom_id})
    phien_map = SanXuatThucThiRepository(db).phien_theo_cong_viec({cv.id for cv in rows})
    sl_repo = SanXuatSanLuongRepository(db)
    cv_ids = {cv.id for cv in rows}
    so_map = _so_lieu_map(rows, sl_repo.tong_tot_nhieu(cv_ids),
                          sl_repo.tong_thuc_nhan_nhieu(cv_ids))
    return [_item_dict(cv, lsx_map, bg_map, may_map, nhom_map, phien_map, so_map) for cv in rows]


def _trong_cua_so(cv, tu_ngay: date | None, den_ngay: date | None) -> bool:
    """Bước có GIAO với cửa sổ ngày? Bước chưa xếp giờ LUÔN giữ lại — nó nằm ở khúc "chưa định
    giờ" của cột trái, cắt nó theo cửa sổ là làm nó mất hẳn khỏi mọi trang."""
    if cv.du_kien_bat_dau is None or cv.du_kien_ket_thuc is None:
        return True
    if den_ngay is not None and cv.du_kien_bat_dau.date() > den_ngay:
        return False
    if tu_ngay is not None and cv.du_kien_ket_thuc.date() < tu_ngay:
        return False
    return True
```

Thêm `from datetime import date` vào import của `board.py` nếu chưa có.

`_loc_viec_cua_tho` (dòng 72) giờ chỉ còn phục vụ `work_item_chi_tiet` (dòng 530) — **giữ**, kèm
chú thích rằng đường bàn tổ đã chuyển sang lọc ở SQL.

- [ ] **Step 5: Viết router**

`backend/app/routers/san_xuat.py:371-386`:

```python
@router.get("/work-items", response_model=WorkItemsOut)
def work_items(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    authz: Annotated[AuthorizationService, Depends(get_authz)],
    team_id: int,
    mode: Literal["production", "kcs"] = "production",
    nhom: Literal["lenh", "phang"] = "lenh",
    trang: int = Query(1, ge=1),
    co_trang: int = Query(20, ge=1, le=100),
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
) -> dict:
    """Việc đã phát hành của MỘT tổ. `nhom=lenh` (mặc định) gom theo LỆNH/BÀI GHÉP và CẮT TRANG ở
    máy chủ — đơn vị trang là LỆNH. `nhom=phang` giữ hình cũ cho Gantt, kèm cửa sổ ngày.

    `co_trang` chặn ở schema (`le=100`) chứ không bóp im lặng trong service: client gửi 9999 phải
    biết mình gửi sai, không phải nhận về 100 dòng rồi tưởng đã lấy hết.
    """
    return _chay(lambda: board.work_items(
        db, user, authz, team_id=team_id, mode=mode, nhom=nhom,
        trang=trang, co_trang=co_trang, tu_ngay=tu_ngay, den_ngay=den_ngay,
    ))
```

Thêm `Query` vào import `fastapi` và `date` vào import `datetime` nếu chưa có.

- [ ] **Step 6: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_san_xuat_board_api.py tests/test_san_xuat_board.py tests/test_san_xuat_lenh_phan_trang.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py backend/app/routers/san_xuat.py backend/tests/test_san_xuat_board_api.py
git commit -m "work-items: trả nhóm LỆNH/BÀI GHÉP có phân trang máy chủ, giữ chế độ phẳng cho Gantt"
```

---

### Task 10: FE — tầng LỆNH trên hai view thẻ + danh sách

**Files:**
- Create: `frontend/src/pages/ThsxLenhGroups.tsx`
- Modify: `frontend/src/pages/ThsxCards.tsx:32-53`, `frontend/src/pages/ThsxDanhSach.tsx:72-105`
- Modify: `frontend/src/pages/ThucHienSxPage.tsx` (state `trang`, nạp `nhom=lenh`, thanh phân trang)
- Modify: `frontend/src/api/client.ts` (`SxLenhNhom`, `SxTrang`, `SxWorkItemsOut`, `workItems()`)
- Modify: `frontend/src/pages/thuc-hien-sx.css`
- Test: `frontend/src/pages/ThsxLenhGroups.test.tsx` (tạo mới)

**Interfaces:**
- Consumes: `GET /api/san-xuat/work-items?...&nhom=lenh&trang=&co_trang=` (Task 9).
- Produces:
  ```ts
  export interface SxLenhNhom {
    nguon_loai: string; nguon_ma: string; nguon_ten: string;
    lsx_id: number | null; bai_ghep_id: number | null;
    som_nhat: string | null; muon_nhat: string | null;
    so_viec: number;
    digest: { released: number; running: number; paused: number; completed: number };
    cong_viec: SxWorkItem[];
  }
  export interface SxTrang { trang: number; co_trang: number; tong: number }
  export function ThsxLenhGroups(props: {
    lenh: SxLenhNhom[]; selectedId: number | null;
    moDau?: string | null;
    render: (viec: SxWorkItem[]) => React.ReactNode;
  }): JSX.Element
  ```

- [ ] **Step 1: Viết test đỏ**

Tạo `frontend/src/pages/ThsxLenhGroups.test.tsx`:

```tsx
// Bản ghi của bàn tổ là LỆNH: dòng lệnh hiện mã + tên + số việc, bấm mới bung công đoạn.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThsxLenhGroups } from "./ThsxLenhGroups";
import type { SxLenhNhom } from "../api/client";

const lenh: SxLenhNhom[] = [
  {
    nguon_loai: "lsx", nguon_ma: "LSX26-0012", nguon_ten: "Hộp bánh 500g",
    lsx_id: 12, bai_ghep_id: null,
    som_nhat: "2026-09-11T07:30:00", muon_nhat: "2026-09-11T15:00:00",
    so_viec: 2,
    digest: { released: 1, running: 1, paused: 0, completed: 0 },
    cong_viec: [
      { id: 1, ten_cong_doan: "In 4 màu" } as never,
      { id: 2, ten_cong_doan: "Cán bóng" } as never,
    ],
  },
  {
    nguon_loai: "bai_ghep", nguon_ma: "BG26-0004", nguon_ten: "Ghép 3 lệnh",
    lsx_id: null, bai_ghep_id: 4,
    som_nhat: null, muon_nhat: null,
    so_viec: 1,
    digest: { released: 1, running: 0, paused: 0, completed: 0 },
    cong_viec: [{ id: 9, ten_cong_doan: "Bế" } as never],
  },
];

describe("ThsxLenhGroups", () => {
  it("mỗi lệnh một dòng, kèm mã và số việc", () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={null}
      render={(v) => <ul>{v.map((w) => <li key={w.id}>{w.ten_cong_doan}</li>)}</ul>} />);
    expect(screen.getByText("LSX26-0012")).toBeInTheDocument();
    expect(screen.getByText("Hộp bánh 500g")).toBeInTheDocument();
    expect(screen.getByText("BG26-0004")).toBeInTheDocument();
    expect(screen.getByText("2 việc")).toBeInTheDocument();
  });

  it("lệnh đầu mở sẵn, lệnh sau gấp — bấm mới bung công đoạn", async () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={null}
      render={(v) => <ul>{v.map((w) => <li key={w.id}>{w.ten_cong_doan}</li>)}</ul>} />);
    expect(screen.getByText("In 4 màu")).toBeInTheDocument();
    expect(screen.queryByText("Bế")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /BG26-0004/ }));
    expect(screen.getByText("Bế")).toBeInTheDocument();
  });

  it("lệnh chứa việc đang chọn thì luôn mở", () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={9}
      render={(v) => <ul>{v.map((w) => <li key={w.id}>{w.ten_cong_doan}</li>)}</ul>} />);
    expect(screen.getByText("Bế")).toBeInTheDocument();
  });

  it("lệnh chưa xếp giờ nói rõ là chưa xếp, không hiện ô giờ trống", () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={null}
      render={() => null} />);
    expect(screen.getByText("chưa xếp giờ")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd frontend && npx vitest run src/pages/ThsxLenhGroups.test.tsx`
Expected: FAIL — không resolve được `./ThsxLenhGroups`.

- [ ] **Step 3: Viết component**

Tạo `frontend/src/pages/ThsxLenhGroups.tsx`:

```tsx
// TẦNG LỆNH của bàn tổ — bản ghi của bàn là LỆNH SX (hoặc BÀI GHÉP), không phải công đoạn rời.
//
// Chủ xưởng chốt 11/09/2026: *"lệnh hoặc bài ghép thôi, chứ không làm sao tôi biết được công đoạn
// đó cho lệnh nào"*. Component này chỉ lo tầng ngoài (dòng lệnh + gấp/mở); công đoạn bên trong do
// nơi gọi vẽ qua `render` — nhờ vậy view "thẻ" và view "danh sách" dùng CHUNG một tầng lệnh mà
// vẫn giữ mật độ hiển thị riêng của mình.
import { useState, type ReactNode } from "react";
import { Icon } from "../components/Icons";
import type { SxLenhNhom, SxWorkItem } from "../api/client";
import { ngayGio } from "./keHoachSxShared";
import { sxNguonIcon } from "./thsxShared";

/** Khoá ổn định của một lệnh trên bàn (bài ghép và lệnh có thể trùng id). */
function khoaLenh(l: SxLenhNhom): string {
  return `${l.nguon_loai}:${l.lsx_id ?? l.bai_ghep_id ?? 0}`;
}

export function ThsxLenhGroups({
  lenh, selectedId, render,
}: {
  lenh: SxLenhNhom[];
  selectedId: number | null;
  render: (viec: SxWorkItem[]) => ReactNode;
}) {
  // Lệnh ĐẦU mở sẵn: mở bàn ra mà mọi thứ gấp hết thì tổ phải bấm thêm một nhịp mới thấy việc.
  const [gap, setGap] = useState<Set<string>>(new Set());
  return (
    <div className="thsx-lenh__scroll">
      {lenh.map((l, i) => {
        const k = khoaLenh(l);
        const coViecDangChon = l.cong_viec.some((w) => w.id === selectedId);
        const mo = coViecDangChon || (gap.has(k) ? false : i === 0 || gap.size > 0 ? !gap.has(k) && (i === 0 || gapMoTay.has(k)) : false);
        return null;
      })}
    </div>
  );
}
```

> Bản nháp trên **cố tình để lại điều kiện `mo` rối** để người thi công không chép máy móc — hãy
> dựng lại bằng state DƯƠNG (tập lệnh ĐANG MỞ) chứ đừng state ÂM (tập đang gấp), vì luật cần là
> *"lệnh đầu mở sẵn + lệnh chứa việc đang chọn luôn mở"*:

```tsx
export function ThsxLenhGroups({
  lenh, selectedId, render,
}: {
  lenh: SxLenhNhom[];
  selectedId: number | null;
  render: (viec: SxWorkItem[]) => ReactNode;
}) {
  const [moTay, setMoTay] = useState<Set<string> | null>(null);
  const macDinh = new Set(lenh.length ? [khoaLenh(lenh[0])] : []);
  const dangMo = moTay ?? macDinh;

  function bat(k: string) {
    const next = new Set(dangMo);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setMoTay(next);
  }

  if (lenh.length === 0) {
    return <p className="thsx-note">Tổ chưa có lệnh nào được phát hành.</p>;
  }

  return (
    <div className="thsx-lenh__scroll">
      {lenh.map((l) => {
        const k = khoaLenh(l);
        const mo = dangMo.has(k) || l.cong_viec.some((w) => w.id === selectedId);
        return (
          <section key={k} className={`thsx-lenh${mo ? " thsx-lenh--mo" : ""}`}>
            <button
              type="button" className="thsx-lenh__h" aria-expanded={mo}
              onClick={() => bat(k)}
            >
              <Icon name="chevron" size={13} className={mo ? "" : "thsx-rot-90"} />
              <Icon name={sxNguonIcon(l.nguon_loai)} size={15} className="thsx-lenh__ic" />
              <span className="thsx-lenh__ma thsx-num">{l.nguon_ma || "— không rõ lệnh —"}</span>
              <span className="thsx-lenh__ten">{l.nguon_ten}</span>
              <span className="thsx-lenh__spacer" />
              <span className="thsx-lenh__gio thsx-num">
                {l.som_nhat ? ngayGio(l.som_nhat) : "chưa xếp giờ"}
              </span>
              <span className="thsx-lenh__n thsx-num">{l.so_viec} việc</span>
              <LenhDigest d={l.digest} />
            </button>
            {mo && <div className="thsx-lenh__body">{render(l.cong_viec)}</div>}
          </section>
        );
      })}
    </div>
  );
}

/** Bốn con số trạng thái của lệnh — chỉ hiện con số khác 0, kèm chữ ở `title` cho người đọc màn. */
function LenhDigest({ d }: { d: SxLenhNhom["digest"] }) {
  const o: [keyof SxLenhNhom["digest"], string, string][] = [
    ["running", "Đang chạy", "thsx-lenh__dg--run"],
    ["paused", "Tạm dừng", "thsx-lenh__dg--pause"],
    ["released", "Chờ làm", "thsx-lenh__dg--wait"],
    ["completed", "Hoàn thành", "thsx-lenh__dg--done"],
  ];
  return (
    <span className="thsx-lenh__dg">
      {o.filter(([k]) => d[k] > 0).map(([k, nhan, cls]) => (
        <span key={k} className={cls} title={nhan}>{d[k]}</span>
      ))}
    </span>
  );
}
```

- [ ] **Step 4: Đấu vào hai view + controller**

`ThsxCards.tsx` / `ThsxDanhSach.tsx`: thay ba `CardSection`/`DsSection` theo cửa sổ bằng
`props.lenh` + `ThsxLenhGroups`, phần `render` trả đúng lưới thẻ / bảng đang có. Đổi `interface
Props` từ `{timed, outWin, untimed}` sang `{lenh: SxLenhNhom[]}` (giữ mọi callback thao tác).

`ThucHienSxPage.tsx`: thêm state `const [trang, setTrang] = useState(1)` + `tongLenh`; gọi
`api.sanXuat.workItems(token, {teamId, mode, nhom: view === "lich" ? "phang" : "lenh", trang,
coTrang: 20, tuNgay: win0, denNgay: win1})`; thanh phân trang dưới chân (`◀ Trang 1/3 ▶`, chữ tiếng
Việt). Đổi view sang "lịch" ⇒ gọi lại với `nhom=phang`. SSE bump (`eventTick`) ⇒ nạp lại **giữ
nguyên `trang`**, đừng nhảy về trang 1.

`client.ts`: thêm `SxLenhNhom`, `SxTrang`; đổi `workItems()` nhận object tham số và trả
`SxWorkItemsOut` với `lenh` + `trang` + `cong_viec`.

`thuc-hien-sx.css`: thêm khối `.thsx-lenh*`. **Kiểm bẫy đã biết:** đếm số định nghĩa selector
trước khi nghi CSS "không ăn" (`grep -c "\.thsx-lenh__h" src/pages/thuc-hien-sx.css`); `*/` trong
chú thích có thể nuốt cả khối `@media`.

- [ ] **Step 5: Chạy test + biên dịch**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/ThsxLenhGroups.test.tsx src/pages/ThsxCards.test.tsx src/pages/ThsxDanhSach.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "bàn tổ: tầng lệnh/bài ghép cho view thẻ và danh sách, phân trang theo lệnh"
```

---

# ĐỢT C — Mẻ đọc được trọn vẹn

### Task 11: Sản lượng theo người LUÔN hiện (bản nháp cho mẻ chưa chốt)

**Files:**
- Modify: `backend/app/services/san_xuat/board.py:571-600` (khối batch của drawer), `:745-805`
- Modify: `backend/app/schemas/san_xuat.py` (thêm `chia_du_kien` vào schema batch)
- Test: `backend/tests/test_san_xuat_san_luong.py`

**Interfaces:**
- Consumes: `_tinh_batch(db, cv, batch, pb_repo)` (hàm thuần, Task 2).
- Produces: mỗi phần tử `san_luong.batches[]` có thêm
  `chia_du_kien: {q: float, don_vi: str | null, dong: [{employee_id, ho_ten, so_luong,
  phut_thuc_te, he_so_bac, la_ho_tro}], can_chot: bool, canh_bao: list[str]} | None`.
  `None` chỉ khi mẻ ĐÃ có bản chia chốt (lúc đó đọc ở `phan_bo`).

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_san_xuat_san_luong.py`:

```python
def test_ghi_me_xong_la_thay_ngay_ai_duoc_may_to(client_to_truong, cv_2_nguoi_co_cham_cong):
    """Ghi mẻ xong PHẢI thấy ngay phần của từng người — không phải bấm 'Chia sản lượng' mới hiện.

    Đây là yêu cầu thẳng của chủ xưởng 11/09/2026 (*"hình như thiếu sản lượng"*): tổ trưởng ghi mẻ
    là biết luôn ai được bao nhiêu, số nháp cũng được, miễn có.
    """
    cv_id = cv_2_nguoi_co_cham_cong
    r = client_to_truong.post(f"/api/san-xuat/work-items/{cv_id}/batches", json={
        "bat_dau": "2026-09-11T07:00", "ket_thuc": "2026-09-11T09:00",
        "tong": 1000, "tot": 980, "hong": 20, "don_vi": "to",
        "mo_ta_loi": "nhăn góc", "ghi_chu": None,
    })
    assert r.status_code in (200, 201)

    d = client_to_truong.get(f"/api/san-xuat/work-items/{cv_id}").json()
    me = d["san_luong"]["batches"][0]
    chia = me["chia_du_kien"]
    assert chia is not None
    assert chia["q"] == 980
    assert len(chia["dong"]) == 2
    assert sum(x["so_luong"] for x in chia["dong"]) == 980, "Σ phải đúng bằng sản lượng tốt"
    for x in chia["dong"]:
        assert x["ho_ten"]
        assert x["phut_thuc_te"] > 0
        assert x["he_so_bac"] is not None
        assert "don_gia" not in x and "tien" not in x


def test_me_da_chot_thi_doc_o_ban_chot_khong_tra_nhap(client_to_truong, batch_da_chot_phan_bo):
    cv_id, _batch_id = batch_da_chot_phan_bo
    d = client_to_truong.get(f"/api/san-xuat/work-items/{cv_id}").json()
    me = d["san_luong"]["batches"][0]
    assert me["chia_du_kien"] is None
    assert d["phan_bo"][0]["trang_thai"] == "finalized"
```

*Đường POST ghi mẻ + tên fixture phải đọc lại từ chính `tests/test_san_xuat_san_luong.py`.*

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_san_xuat_san_luong.py -q`
Expected: FAIL — `KeyError: 'chia_du_kien'`.

- [ ] **Step 3: Viết service**

Trong `backend/app/services/san_xuat/board.py`, khối batch của drawer — thêm ngay sau vòng tính
`pb_flags`:

```python
    # Chia sản lượng NHÁP cho mẻ CHƯA có bản chia (spec 2026-09-11 §5.1): tổ trưởng ghi mẻ xong là
    # thấy ngay ai được bao nhiêu. `_tinh_batch` là HÀM THUẦN (không ghi DB) nên gọi ở mặt đọc là
    # an toàn — đúng cách khối `pb_flags` ngay trên đang làm cho bản chưa chốt.
    co_header = {h.batch_id for h in pb_headers}
    chia_nhap: dict[int, dict] = {}
    for b in batches:
        if b.id in co_header:
            continue
        kq = _tinh_batch(db, cv, b, pb)
        chia_nhap[b.id] = {
            "q": float(kq.q_pay or 0),
            "don_vi": kq.don_vi_pay,
            "can_chot": kq.can_chot,
            "canh_bao": kq.canh_bao,
            "dong": [
                {
                    "employee_id": d["employee_id"],
                    "ho_ten": _emp_ten(d["employee_id"]),
                    "so_luong": float(d["so_luong_tra_luong"] or 0),
                    "phut_thuc_te": d.get("phut_thuc_te"),
                    "he_so_bac": d.get("he_so_bac"),
                    "la_ho_tro": bool(d.get("la_ho_tro")),
                }
                for d in kq.dong
            ],
        }
```

`_emp_ten` chỉ tra `ten_map` đã nạp; `ten_map` dựng từ `emp_ids` **trước** khối này, nên phải bổ
sung người của bản nháp vào `emp_ids`. Cách gọn: tính `chia_nhap` TRƯỚC khi dựng `ten_map`, gom
`{d["employee_id"] for c in chia_nhap.values() for d in c["dong"]}` vào `emp_ids`, rồi điền tên ở
một vòng thứ hai:

```python
    for c in chia_nhap.values():
        for d in c["dong"]:
            d["ho_ten"] = _emp_ten(d["employee_id"])
```

Trong dict batch (dòng ~676) thêm khoá:

```python
                    "chia_du_kien": chia_nhap.get(b.id),
```

- [ ] **Step 4: Viết schema**

`backend/app/schemas/san_xuat.py` — thêm trước schema batch:

```python
class ChiaDongOut(BaseModel):
    """Một người trong bản CHIA SẢN LƯỢNG của mẻ. Không có ô tiền nào — xem spec 2026-09-11."""
    employee_id: int
    ho_ten: str
    so_luong: float
    phut_thuc_te: float | None = None
    he_so_bac: float | None = None
    la_ho_tro: bool = False


class ChiaDuKienOut(BaseModel):
    """Bản chia NHÁP tính lúc ĐỌC cho mẻ chưa có bản chia chốt (§5.1). Không lưu DB."""
    q: float
    don_vi: str | None = None
    can_chot: bool = True
    canh_bao: list[str] = []
    dong: list[ChiaDongOut] = []
```

và thêm `chia_du_kien: ChiaDuKienOut | None = None` vào schema batch của `san_luong`. *(Nhớ bẫy đã
biết: Pydantic **nuốt field im lặng** — field không khai ở schema Out thì FE nhận `undefined` mà
không có lỗi nào. Phải đi hết `dict service → schema → type TS`.)*

- [ ] **Step 5: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_san_xuat_san_luong.py tests/test_san_xuat_board_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py backend/tests/test_san_xuat_san_luong.py
git commit -m "mẻ: trả bản chia sản lượng nháp ngay khi ghi, không chờ bấm tính"
```

---

### Task 12: Mẻ mang theo máy · ca · sự cố dừng máy · đầu việc

**Files:**
- Modify: `backend/app/services/san_xuat/board.py` (khối batch)
- Modify: `backend/app/schemas/san_xuat.py` (schema batch)
- Test: `backend/tests/test_san_xuat_me_chi_tiet.py` (tạo mới)

**Interfaces:**
- Consumes: `SanXuatPhienChay` (`may_id`, `bat_dau`, `ket_thuc`, `loai_dong`, `ly_do`),
  `_may_thiet_bi_nhan(db, may_ids)` (`board.py:123`), `WorkShift` (`models/attendance.py` —
  kiểm tên module thật bằng `grep -rn "class WorkShift" backend/app/models/`).
- Produces: mỗi batch thêm `may_ten: str | None`, `ca_ten: str | None`,
  `su_co: [{bat_dau, ket_thuc, ly_do}]`, `dau_viec_ten: str | None`, `so_nguoi: int`.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/test_san_xuat_me_chi_tiet.py`:

```python
"""Mẻ phải đọc được trọn vẹn (spec 2026-09-11 §5.2) — không cột mới, mọi số đã có trong DB.

Chủ xưởng: *"tổ trưởng phải thấy được thông tin của từng mẻ và sản lượng các thứ, nói chung đầy đủ
và chi tiết để sau này hỗ trợ kế toán lương"*.
"""


def test_me_mang_theo_may_da_chay_no(client_to_truong, cv_co_phien_doi_may_va_2_me):
    """Máy đứng trên PHIÊN, không trên công việc: đổi máy giữa chừng thì mỗi mẻ một máy khác nhau.
    Đọc `cv.may_id` là luôn ra máy HIỆN TẠI — sai cho mẻ chạy trước lúc đổi."""
    cv_id, may_dau, may_sau = cv_co_phien_doi_may_va_2_me
    d = client_to_truong.get(f"/api/san-xuat/work-items/{cv_id}").json()
    mes = d["san_luong"]["batches"]
    assert [m["may_ten"] for m in mes] == [may_dau, may_sau]


def test_me_mang_theo_ca_va_su_co_dung_may(client_to_truong, cv_co_me_va_tam_dung):
    cv_id, ly_do = cv_co_me_va_tam_dung
    me = client_to_truong.get(f"/api/san-xuat/work-items/{cv_id}").json()["san_luong"]["batches"][0]
    assert me["ca_ten"], "ca phải suy được từ giờ bắt đầu mẻ"
    assert [s["ly_do"] for s in me["su_co"]] == [ly_do]


def test_me_mang_ten_dau_viec_ke_hoach_da_chon_nhung_khong_mang_gia(
    client_to_truong, cv_co_khoan_va_me,
):
    cv_id, ten_dau_viec = cv_co_khoan_va_me
    me = client_to_truong.get(f"/api/san-xuat/work-items/{cv_id}").json()["san_luong"]["batches"][0]
    assert me["dau_viec_ten"] == ten_dau_viec
    assert me["so_nguoi"] >= 1
    assert "don_gia" not in me and "tien" not in me
```

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_san_xuat_me_chi_tiet.py -q`
Expected: FAIL — `KeyError: 'may_ten'`.

- [ ] **Step 3: Viết helper thuần + nối vào dict batch**

Thêm vào `board.py`:

```python
def _phien_giao_me(phien_rows, b) -> list:
    """Các phiên chạy GIAO với cửa sổ mẻ. Nền của cả 'máy nào chạy mẻ này' lẫn 'mẻ này có dừng máy
    lần nào'. Ép `_aware` vì SQLite trả naive (bẫy naive/aware của module)."""
    bd, kt = _aware(b.bat_dau), _aware(b.ket_thuc)
    ra = []
    for p in phien_rows:
        pbd = _aware(p.bat_dau)
        pkt = _aware(p.ket_thuc) if p.ket_thuc is not None else None
        if pbd <= kt and (pkt is None or pkt >= bd):
            ra.append(p)
    return ra


def _ca_cua(shifts, dt) -> str | None:
    """Tên CA chứa mốc `dt` — so theo giờ-phút tường, ưu tiên ca sản xuất.

    Ca qua đêm (22:00–06:00) có `end < start`: khoảng của nó là "sau start HOẶC trước end".
    Không ca nào khớp ⇒ None, đừng đoán ca gần nhất: "ngoài ca" là một câu trả lời thật và tổ
    trưởng cần thấy đúng nó (mẻ chạy ngoài ca là chuyện phải giải thích).
    """
    if dt is None:
        return None
    t = _aware(dt).time()
    for s in sorted(shifts, key=lambda x: not bool(getattr(x, "ca_san_xuat", False))):
        a, b = s.start_time, s.end_time
        if a is None or b is None:
            continue
        trong = (a <= t < b) if a <= b else (t >= a or t < b)
        if trong:
            return s.name
    return None
```

Trong khối batch của drawer, trước vòng dựng dict:

```python
    # Máy + ca + sự cố của TỪNG mẻ — mọi số đã có sẵn, chỉ là chưa ai nối ra mặt đọc (§5.2).
    ca_list = AttendanceService(db).list_shifts(active_only=True)
    dau_viec_ten = ((cv.khoan_json or {}).get("ten") or None)
```

và trong dict của mỗi `b`:

```python
                    "ket_thuc": lich_hien_thi(b.ket_thuc),
                    "may_ten": next(
                        (phien_may_ten.get(p.may_id or 0) for p in _phien_giao_me(phien_rows, b)
                         if p.may_id), None),
                    "ca_ten": _ca_cua(ca_list, b.bat_dau),
                    "su_co": [
                        {"bat_dau": thuc_te_hien_thi(p.bat_dau),
                         "ket_thuc": thuc_te_hien_thi(p.ket_thuc),
                         "ly_do": p.ly_do}
                        for p in _phien_giao_me(phien_rows, b)
                        if p.loai_dong == "tam_dung" and p.ly_do
                    ],
                    "dau_viec_ten": dau_viec_ten,
                    "so_nguoi": len(_nguoi_trong_batch(khoang, ten_map, b)),
```

*`AttendanceService` + `list_shifts(active_only=True)` — kiểm đúng đường import và chữ ký bằng
`grep -n "def list_shifts" -B 5 backend/app/services/attendance_service.py` trước khi gọi; nếu
service đó đòi tham số khởi tạo khác thì dùng repo tương ứng, đừng đổi chữ ký của nó.*

- [ ] **Step 4: Viết schema**

Thêm vào schema batch: `may_ten: str | None = None`, `ca_ten: str | None = None`,
`dau_viec_ten: str | None = None`, `so_nguoi: int = 0`, và

```python
class MeSuCoOut(BaseModel):
    """Một lần DỪNG MÁY rơi vào cửa sổ mẻ — suy từ phiên `loai_dong='tam_dung'`, không bảng mới."""
    bat_dau: datetime | None = None
    ket_thuc: datetime | None = None
    ly_do: str | None = None
```

với `su_co: list[MeSuCoOut] = []`.

- [ ] **Step 5: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_san_xuat_me_chi_tiet.py tests/test_san_xuat_board_api.py tests/test_san_xuat_doi_may.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py backend/tests/test_san_xuat_me_chi_tiet.py
git commit -m "mẻ: trả kèm máy đã chạy, ca, sự cố dừng máy, tên đầu việc và số người"
```

---

### Task 13: FE — khối mẻ đầy đủ + "Chia sản lượng" luôn hiện

**Files:**
- Modify: `frontend/src/pages/ThsxExecPanels.tsx:360-400` (`BatchRow`), `:404+` (`PhanBoBlock`)
- Modify: `frontend/src/api/client.ts` (`SxBatch` thêm `may_ten`, `ca_ten`, `su_co`,
  `dau_viec_ten`, `so_nguoi`, `chia_du_kien`)
- Modify: `frontend/src/pages/thuc-hien-sx.css`
- Test: `frontend/src/pages/ThsxChiaSanLuong.test.tsx` (mở rộng)

**Interfaces:**
- Consumes: batch payload của Task 11 + 12.
- Produces: `BatchRow` hiện đủ 9 dòng thông tin; `PhanBoBlock` nhận thêm prop
  `chiaNhap?: SxBatch["chia_du_kien"]` và vẽ bảng nháp khi `pb == null`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `frontend/src/pages/ThsxChiaSanLuong.test.tsx`:

```tsx
it("mẻ chưa chốt vẫn hiện bảng chia sản lượng, có gắn nhãn nháp", () => {
  const nhap = {
    q: 980, don_vi: "to", can_chot: true, canh_bao: [],
    dong: [
      { employee_id: 11, ho_ten: "Lê Văn A", so_luong: 520, phut_thuc_te: 120, he_so_bac: 1.3, la_ho_tro: false },
      { employee_id: 12, ho_ten: "Trần Thị B", so_luong: 460, phut_thuc_te: 120, he_so_bac: 1.15, la_ho_tro: false },
    ],
  };
  render(<PhanBoBlock b={batch} pb={null} chiaNhap={nhap as never} canAssign busy={false}
    tenNguoi={new Map()} hoTroUngVien={[]} exec={exec} />);
  expect(screen.getByText("Chia sản lượng")).toBeInTheDocument();
  expect(screen.getByText("nháp")).toBeInTheDocument();
  expect(screen.getByText("Lê Văn A")).toBeInTheDocument();
  expect(screen.getByText("520")).toBeInTheDocument();
  expect(screen.queryByText(/Chưa chia sản lượng/)).toBeNull();
});
```

và một bài cho `BatchRow`:

```tsx
it("thân mẻ hiện máy, ca, giờ kết thúc, đầu việc, kíp và sự cố", async () => {
  const b = {
    ...batch,
    may_ten: "Komori 1050", ca_ten: "Ca 1", dau_viec_ten: "Bế hộp bánh · 1050",
    so_nguoi: 2,
    su_co: [{ bat_dau: "2026-09-11T08:00:00", ket_thuc: "2026-09-11T08:20:00", ly_do: "kẹt giấy" }],
    chia_du_kien: null,
  } as unknown as SxBatch;
  render(<BatchRow b={b} canAssign busy={false} pb={pb}
    tenNguoi={new Map()} hoTroUngVien={[]} exec={exec} />);
  await userEvent.click(screen.getByRole("button", { expanded: false }));
  for (const chu of ["Komori 1050", "Ca 1", "Bế hộp bánh · 1050", "kẹt giấy"]) {
    expect(screen.getByText(new RegExp(chu))).toBeInTheDocument();
  }
});
```

`BatchRow` cần `export`.

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd frontend && npx vitest run src/pages/ThsxChiaSanLuong.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Sửa `BatchRow`**

Header mẻ: thêm giờ kết thúc và số người sau giờ bắt đầu —
`{ngayGio(b.bat_dau)} – {gioNgan(b.ket_thuc)}` + `<span>{b.so_nguoi} người</span>`.

Thân mẻ: thêm các dòng `thsx-x-kv` (chỉ hiện khi có dữ liệu, đúng luật "vắng thì bỏ dòng, đừng bịa
0"):

```tsx
          {b.may_ten && <div className="thsx-x-kv"><span>Máy</span><b>{b.may_ten}</b></div>}
          {b.ca_ten && <div className="thsx-x-kv"><span>Ca</span><b>{b.ca_ten}</b></div>}
          {b.dau_viec_ten && (
            <div className="thsx-x-kv"><span>Đầu việc</span><b>{b.dau_viec_ten}</b></div>
          )}
          {b.su_co.length > 0 && (
            <div className="thsx-x-kv thsx-x-kv--bad"><span>Dừng máy</span>
              <span>{b.su_co.map((s) => `${gioNgan(s.bat_dau)}–${gioNgan(s.ket_thuc)}: ${s.ly_do ?? ""}`).join(" · ")}</span></div>
          )}
```

Truyền `chiaNhap={b.chia_du_kien}` xuống `PhanBoBlock`.

- [ ] **Step 4: Sửa `PhanBoBlock` cho nhánh nháp**

Nhánh `if (!pb)` đổi thành: có `chiaNhap` ⇒ vẽ đúng khối "Chia sản lượng" với pill `nháp` + bảng 4
cột + băng cảnh báo `chiaNhap.canh_bao` + nút `Chốt` bị khoá kèm `title="Bấm Chia sản lượng để
lưu bản chia rồi mới chốt được"`; không có `chiaNhap` ⇒ giữ câu "Chưa chia sản lượng cho mẻ này."
Tách bảng 4 cột thành component nội bộ `BangChia({dong})` để hai nhánh dùng chung, đừng chép.

- [ ] **Step 5: Chạy test + biên dịch**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/ThsxChiaSanLuong.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "FE mẻ: hiện máy/ca/đầu việc/kíp/sự cố và bảng chia sản lượng nháp ngay khi ghi mẻ"
```

---

# ĐỢT D — Màn của thợ

### Task 14: Trong mẻ, thợ chỉ thấy dòng của chính mình + luỹ kế tháng

**Files:**
- Modify: `backend/app/services/san_xuat/board.py` (`work_item_chi_tiet`, dòng ~530)
- Create: `backend/app/services/san_xuat/san_luong_cua_toi.py`
- Modify: `backend/app/routers/san_xuat.py` (route mới), `backend/app/schemas/san_xuat.py`
- Test: `backend/tests/test_san_xuat_man_tho.py` (tạo mới)

**Interfaces:**
- Consumes: `_la_tho`, `SanXuatThucThiRepository.nhan_vien_theo_user`,
  `SanXuatPhanBoDong`, `SanXuatPhanBo`, `PB_DA_CHOT`.
- Produces:
  ```python
  def san_luong_cua_toi(db, user, *, nam: int, thang: int) -> dict
  # -> {"nam", "thang", "employee_id", "theo_don_vi": [{"don_vi": str|None, "tong": float}],
  #     "so_me": int}
  ```
  Route `GET /api/san-xuat/toi/san-luong?nam=&thang=` (quyền `san_xuat:read`).

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/test_san_xuat_man_tho.py`:

```python
"""Màn của THỢ (spec 2026-09-11 §6): thấy lệnh mình làm, trong mẻ chỉ thấy dòng của mình, không tiền."""


def test_tho_chi_thay_dong_cua_minh_trong_me(client_tho_A, cv_2_nguoi_A_va_B):
    cv_id, ten_A, ten_B = cv_2_nguoi_A_va_B
    d = client_tho_A.get(f"/api/san-xuat/work-items/{cv_id}").json()

    moi_ten = [
        x["ho_ten"]
        for pb in d["phan_bo"] for x in pb["dong"]
    ] + [
        x["ho_ten"]
        for b in d["san_luong"]["batches"] if b["chia_du_kien"]
        for x in b["chia_du_kien"]["dong"]
    ]
    assert moi_ten, "phải có ít nhất một dòng để bài này nói được điều gì"
    assert set(moi_ten) == {ten_A}
    assert ten_B not in moi_ten


def test_to_truong_van_thay_ca_to(client_to_truong, cv_2_nguoi_A_va_B):
    cv_id, ten_A, ten_B = cv_2_nguoi_A_va_B
    d = client_to_truong.get(f"/api/san-xuat/work-items/{cv_id}").json()
    ten = {x["ho_ten"] for b in d["san_luong"]["batches"] if b["chia_du_kien"]
           for x in b["chia_du_kien"]["dong"]}
    assert {ten_A, ten_B} <= ten


def test_luy_ke_thang_cua_toi_chi_tra_cua_chinh_minh(client_tho_A, phan_bo_da_chot_2_nguoi):
    nam, thang, sl_cua_A = phan_bo_da_chot_2_nguoi
    r = client_tho_A.get(f"/api/san-xuat/toi/san-luong?nam={nam}&thang={thang}")
    assert r.status_code == 200
    d = r.json()
    assert sum(x["tong"] for x in d["theo_don_vi"]) == sl_cua_A
    assert "tien" not in str(d)


def test_luy_ke_khong_nhan_employee_id_tu_client(client_tho_A):
    r = client_tho_A.get("/api/san-xuat/toi/san-luong?nam=2026&thang=9&employee_id=999")
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        # Tham số lạ bị bỏ qua, không được dùng để xem sản lượng người khác.
        assert r.json()["employee_id"] != 999
```

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd backend && python -m pytest tests/test_san_xuat_man_tho.py -q`
Expected: FAIL — thợ vẫn thấy dòng của người khác; route `toi/san-luong` trả 404.

- [ ] **Step 3: Lọc dòng chia theo người trong `work_item_chi_tiet`**

Trong `board.py`, sau khi dựng `chia_nhap` và trước khi `return`, thêm:

```python
    # Thợ chỉ thấy PHẦN CỦA MÌNH (spec §6): phần người khác không phải việc của họ, và khoe ra là
    # mở đường cho so đo giữa hai người mà tổ trưởng không có mặt để giải thích. Tổ trưởng và cấp
    # trên phạm vi rộng vẫn thấy trọn bảng.
    if _la_tho(user, authz, next((d for d in _tos if d.id == cv.department_id), None)):
        nv = SanXuatThucThiRepository(db).nhan_vien_theo_user(user.id)
        chi_minh = nv.id if nv is not None else -1
        for c in chia_nhap.values():
            c["dong"] = [d for d in c["dong"] if d["employee_id"] == chi_minh]
        # `pb_headers`/`dong_map` là bản ĐÃ CHỐT — lọc cùng một luật.
        for hid, ds in list(dong_map.items()):
            dong_map[hid] = [d for d in ds if d.employee_id == chi_minh]
        for hid, bs in list(bu_tru_map.items()):
            bu_tru_map[hid] = [b for b in bs if b.employee_id == chi_minh]
```

*Đặt khối này SAU khi `dong_map` / `bu_tru_map` đã nạp và TRƯỚC `return` — đọc lại quanh dòng 540
để chèn đúng chỗ; `_tos` phải có sẵn trong scope (nếu chưa, lấy từ `_to_thay_duoc`).*

- [ ] **Step 4: Viết service luỹ kế tháng**

Tạo `backend/app/services/san_xuat/san_luong_cua_toi.py`:

```python
"""Luỹ kế SẢN LƯỢNG THÁNG của chính người đang đăng nhập (spec 2026-09-11 §6, mục 3).

Thợ cần một con số trả lời được câu *"tháng này tôi làm được bao nhiêu"* mà không phải chờ bảng
lương. Không có tiền ở đây — sản xuất ghi số lượng.

Chỉ đọc dòng chia ĐÃ CHỐT: bản nháp còn đổi theo chấm công và còn bị tính lại, đưa nó vào luỹ kế
là mỗi lần mở màn ra một số khác.

`employee_id` LUÔN suy từ token, KHÔNG nhận từ client — nếu nhận thì đây là cửa xem sản lượng của
bất kỳ ai chỉ bằng cách đổi một số trên URL.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models.san_xuat_phan_bo import PB_DA_CHOT, SanXuatPhanBo, SanXuatPhanBoDong
from ...models.user import User
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository


def _khoang_thang(nam: int, thang: int) -> tuple[date, date]:
    dau = date(nam, thang, 1)
    return dau, (date(nam + 1, 1, 1) if thang == 12 else date(nam, thang + 1, 1))


def san_luong_cua_toi(db: Session, user: User, *, nam: int, thang: int) -> dict:
    nv = SanXuatThucThiRepository(db).nhan_vien_theo_user(user.id)
    if nv is None:
        # Tài khoản chưa nối hồ sơ nhân sự ⇒ không có sản lượng nào, KHÔNG rơi về "của cả tổ".
        return {"nam": nam, "thang": thang, "employee_id": None,
                "theo_don_vi": [], "so_me": 0}
    dau, ke = _khoang_thang(nam, thang)
    rows = db.execute(
        select(SanXuatPhanBo.don_vi_tra_luong,
               func.sum(SanXuatPhanBoDong.so_luong_tra_luong),
               func.count(SanXuatPhanBoDong.id))
        .join(SanXuatPhanBo, SanXuatPhanBoDong.phan_bo_id == SanXuatPhanBo.id)
        .where(
            SanXuatPhanBoDong.employee_id == nv.id,
            SanXuatPhanBo.trang_thai == PB_DA_CHOT,
            SanXuatPhanBoDong.ngay >= dau,
            SanXuatPhanBoDong.ngay < ke,
        )
        .group_by(SanXuatPhanBo.don_vi_tra_luong)
    ).all()
    return {
        "nam": nam, "thang": thang, "employee_id": nv.id,
        "theo_don_vi": [{"don_vi": dv, "tong": float(t or 0)} for dv, t, _ in rows],
        "so_me": int(sum(n for _, _, n in rows)),
    }
```

Route:

```python
@router.get("/toi/san-luong", response_model=SanLuongCuaToiOut)
def san_luong_cua_toi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    nam: int = Query(..., ge=2000, le=2200),
    thang: int = Query(..., ge=1, le=12),
) -> dict:
    """Luỹ kế sản lượng tháng của CHÍNH người đăng nhập. Không nhận `employee_id` — xem service."""
    return _chay(lambda: san_luong_cua_toi_svc(db, user, nam=nam, thang=thang))
```

Schema:

```python
class SanLuongMotDonViOut(BaseModel):
    don_vi: str | None = None
    tong: float


class SanLuongCuaToiOut(BaseModel):
    """Luỹ kế sản lượng tháng của chính người đăng nhập. KHÔNG có ô tiền — spec 2026-09-11."""
    nam: int
    thang: int
    employee_id: int | None = None
    theo_don_vi: list[SanLuongMotDonViOut] = []
    so_me: int = 0
```

- [ ] **Step 5: Chạy test — phải xanh**

Run: `cd backend && python -m pytest tests/test_san_xuat_man_tho.py tests/test_san_xuat_board_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests/test_san_xuat_man_tho.py
git commit -m "màn thợ: trong mẻ chỉ thấy dòng của mình, thêm luỹ kế sản lượng tháng của tôi"
```

---

### Task 15: FE — băng "Sản lượng của tôi" cho thợ

**Files:**
- Modify: `frontend/src/pages/ThucHienSxPage.tsx` (băng trên cùng khi là thợ)
- Modify: `frontend/src/api/client.ts` (`SxSanLuongCuaToi`, `sanLuongCuaToi()`)
- Test: `frontend/src/pages/ThsxSanLuongCuaToi.test.tsx` (tạo mới)

**Interfaces:**
- Consumes: `GET /api/san-xuat/toi/san-luong` (Task 14).
- Produces: component `ThsxSanLuongCuaToi({ data }: { data: SxSanLuongCuaToi | null })`.

- [ ] **Step 1: Viết test đỏ**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThsxSanLuongCuaToi } from "./ThsxSanLuongCuaToi";

describe("Sản lượng của tôi", () => {
  it("hiện tổng theo từng đơn vị, không có ô tiền", () => {
    render(<ThsxSanLuongCuaToi data={{
      nam: 2026, thang: 9, employee_id: 11, so_me: 7,
      theo_don_vi: [{ don_vi: "to", tong: 12400 }, { don_vi: "cai", tong: 3100 }],
    }} />);
    expect(screen.getByText(/Sản lượng của tôi/)).toBeInTheDocument();
    expect(screen.getByText(/12.400/)).toBeInTheDocument();
    expect(screen.getByText(/7 mẻ/)).toBeInTheDocument();
    expect(screen.queryByText(/đ|đồng|tiền/)).toBeNull();
  });

  it("chưa có sản lượng thì nói rõ, không hiện 0 trống trơn", () => {
    render(<ThsxSanLuongCuaToi data={{
      nam: 2026, thang: 9, employee_id: 11, so_me: 0, theo_don_vi: [],
    }} />);
    expect(screen.getByText(/Tháng này chưa có mẻ nào được chốt/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Chạy test để thấy nó đỏ**

Run: `cd frontend && npx vitest run src/pages/ThsxSanLuongCuaToi.test.tsx`
Expected: FAIL — không resolve được module.

- [ ] **Step 3: Viết component + đấu vào trang**

Tạo `frontend/src/pages/ThsxSanLuongCuaToi.tsx` (dùng `num` của `keHoachSxShared` và `nhanDonVi`
của `lsxBuoc`; nhãn tiếng Việt; không ô tiền). Trong `ThucHienSxPage.tsx`: nạp khi `laTho` và
hiện băng ngay dưới top bar. `laTho` suy từ chính dữ liệu đã có ở FE (scope `own` + không phải tổ
trưởng) — nếu FE chưa biết điều đó thì **không đoán**: thêm `la_tho: bool` vào payload
`GET /teams` (service `board.teams` đã tính `to_tho` ở dòng ~96, chỉ việc trả ra) và đọc nó.

- [ ] **Step 4: Chạy test + biên dịch**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/ThsxSanLuongCuaToi.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py
git commit -m "FE màn thợ: băng sản lượng của tôi theo tháng"
```

---

### Task 16: Dọn tài liệu + XÁC MINH LUỒNG UI THẬT

**Files:**
- Modify: `docs/CONG_THUC_TINH_LUONG.md`, `docs/DATA_CONTRACTS.md`,
  `docs/design-thuc-hien-san-xuat-ui.md`
- Modify: `docs/DB_SCHEMA.md` (rà lại lần cuối)

- [ ] **Step 1: Rà chữ "khoán/đơn giá" còn sót trong doc sản xuất**

```bash
grep -rn "đơn giá khoán\|tiền khoán\|thưởng tổ trưởng" docs/design-thuc-hien-san-xuat-ui.md docs/DATA_CONTRACTS.md
```

Sửa từng chỗ để trỏ về spec mới; không xoá lịch sử, thêm câu *"ĐÃ GỠ 11/09/2026 — xem
`docs/superpowers/specs/2026-09-11-san-xuat-chi-ghi-so-luong-design.md`"*.

- [ ] **Step 2: Chạy guard test + bộ test của module**

Run: `cd backend && python -m pytest tests/test_db_schema_doc.py tests/test_san_xuat_board.py tests/test_san_xuat_board_api.py tests/test_san_xuat_phan_bo.py tests/test_san_xuat_san_luong.py tests/test_san_xuat_me_chi_tiet.py tests/test_san_xuat_man_tho.py tests/test_san_xuat_lenh_phan_trang.py tests/test_san_xuat_dong_nhom.py tests/test_khoan_api.py tests/test_khoan_dau_viec.py -q`
Expected: PASS toàn bộ.

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/`
Expected: PASS.

- [ ] **Step 3: Chạy migration trên DB dev**

Restart uvicorn (migration chạy lúc khởi động). Đọc log để chắc `0296` và `0297` đã chạy.
**Không** dùng `python -c` để kiểm — nó trỏ vào Postgres DEV thật; muốn kiểm thì viết test tạm.

- [ ] **Step 4: XÁC MINH LUỒNG UI THẬT — bắt buộc, không thay bằng API/curl bước nào**

Mở dev-browser (tối đa 5 instance, kill cái cũ trước), đăng nhập `admin` / mật khẩu
`SEED_ADMIN_PASSWORD`. Thao tác bằng chuột/bàn phím thật, ghi lại **đã bấm gì / gõ gì / thấy gì**
ở từng bước:

1. Bàn tổ → thấy **danh sách LỆNH** (mã + tên + số việc + digest), thanh phân trang dưới chân.
2. Bấm **▶** sang trang 2 → nội dung đổi, không trùng lệnh của trang 1.
3. Bung một lệnh → thấy các công đoạn **của tổ đó**.
4. Bấm một công đoạn → drawer mở; soi khối Sản lượng: **không có chữ "đơn giá"** ở đâu.
5. Bấm **Ghi mẻ**, gõ giờ + tổng + tốt, Lưu → mẻ xuất hiện; bung mẻ → thấy **Máy · Ca · Đầu việc ·
   kíp · Dừng máy (nếu có)** và bảng **Chia sản lượng** có pill `nháp`, đủ dòng từng người kèm
   **Phút** và **Bậc**, Σ đúng bằng số tốt.
6. Bấm **Chia sản lượng** → bản chia được lưu; bấm **Chốt** → pill đổi sang đã chốt.
7. Đổi view sang **Gantt** → vẽ đúng cửa sổ, không lỗi console.
8. Đăng xuất, đăng nhập một tài khoản **thợ** (`tho_<slug>N`) → bàn tổ chỉ có lệnh mà thợ đó có
   việc; bung mẻ → **chỉ dòng của chính mình**; băng **Sản lượng của tôi** hiện số tháng này.
9. Mở màn **Lệnh sản xuất** → drawer bước vẫn chọn được đầu việc, **không** hiện tiền; mặt lệnh
   không còn ô "công thợ dự kiến".
10. Mở màn **Bài ghép** → bước chung chọn được đầu việc, không hiện tiền.
11. Mở **Bảng lương** một kỳ → cột `Khoán` và `Thưởng/phạt tổ trưởng` = 0 (đúng như spec §3.5 đã
    báo trước), không màn nào nổ.

Kiểm console + network sau mỗi bước: `read_console_messages` không có lỗi, không request 4xx/5xx.

- [ ] **Step 5: Commit**

```bash
git add docs
git commit -m "docs: cập nhật tài liệu lương/hợp đồng dữ liệu theo quyết định sản xuất chỉ ghi số lượng"
```

---

## Tự soi lại plan

**1. Spec coverage.** §3.1 cột bỏ → Task 1. §3.2 ảnh chụp → Task 3. §3.3 danh mục không đụng →
không có task nào sửa `piece_rates`, đúng chủ ý. §3.4 bảng hàm gỡ → Task 2 (phan_bo), 3 (snapshot,
bien_cong_thuc), 4 (lsx_service), 5 (bai_ghep), 6 (thuong_to_truong, production_output_repo,
piece_work). §3.5 hệ quả → Task 6 Step 5 + Task 16 Step 4 mục 11. §4.1 ba tầng → Task 9 + 10.
§4.2 sắp + phân trang → Task 8 + 9. §5.1 chia luôn hiện → Task 11 + 13. §5.2 bảng thông tin mẻ →
Task 12 + 13. §6 màn thợ (3 điểm) → Task 8 (lọc ở SQL), 14 (dòng của mình + luỹ kế), 15 (băng).
§7 migration + DB_SCHEMA → Task 1. §9 kiểm thử → rải khắp + Task 16.

**2. Placeholder scan.** Không có "TBD"/"tương tự Task N". Ba chỗ cố tình bắt người thi công ĐỌC
code trước khi sửa, và đều nói rõ đọc file nào, tìm gì: tên fixture của các file test đang có;
chữ ký `AttendanceService.list_shifts`; vị trí chèn khối lọc trong `work_item_chi_tiet`. Đó là
kiểm-trước-khi-dựa, không phải placeholder. Task 10 Step 3 cố tình đưa một bản nháp SAI rồi bác nó
ngay bên dưới kèm bản đúng — giữ lại vì nó dạy đúng cái bẫy state-âm/state-dương.

**3. Type consistency.** `KhoaLenh = tuple[str, int | None]` dùng thống nhất ở Task 8 và 9.
`lenh_cua_to_phan_trang` trả `(list[(khoa, som, muon)], tong)` — Task 9 unpack đúng hình đó.
`SxLenhNhom` (TS) khớp `LenhNhomOut` (Pydantic) từng khoá. `chia_du_kien` cùng một hình ở Task 11
(service) → Task 11 (schema) → Task 13 (TS). `_don_vi_tra_luong` thay `_don_gia_don_vi` và Task 2
Step 1 có bài khẳng định tên cũ đã mất. `PhanBoBlock` / `BatchRow` / `ThsxLenhGroups` /
`ThsxSanLuongCuaToi` đều được `export` ở chính task viết test cho chúng.

Một điểm plan **cố ý không quyết**: sản lượng theo người vẫn do engine chia theo `phút × hệ số
bậc`. Bảng *Cán phủ* / *Tổ bồi* của xưởng ghi *"tỷ lệ nhóm tự phân chia"* — chủ xưởng chưa trả lời
câu đó nên plan giữ nguyên hiện trạng và ghi rõ ở spec §5.1; mở ô gõ tỷ lệ tay là một đợt riêng.
