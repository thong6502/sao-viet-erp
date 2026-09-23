# Dải routing trên bàn tổ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mỗi thẻ lệnh trên bàn tổ bày cả chuỗi công đoạn của lệnh — tổ chỉ bấm được bước của mình nhưng đọc được trạng thái, tổ giữ và số ra của các bước trước/sau.

**Architecture:** Đọc thêm từ snapshot gói phát hành (`san_xuat_cong_viec`), KHÔNG lọc `department_id`, rồi sắp theo `LsxCongDoan.thu_tu` tra qua `step_key`. Gắn mảng `routing` vào từng phần tử `lenh` của response `GET /api/san-xuat/work-items?nhom=lenh` đang có. Không bảng mới, không cột mới, không endpoint mới, không migration.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (backend), Pydantic v2 (schema), React + TypeScript + Vite (frontend), pytest + vitest.

**Spec:** `docs/design-dai-routing-tren-ban-to.md`

## Global Constraints

- **KHÔNG chạy `./init.ps1`.** Verify bằng pytest nhắm file + `npx tsc --noEmit`. Muốn chạy cả bộ thì hỏi trước.
- **KHÔNG thêm cột/bảng.** Không đụng `backend/app/db_migrations.py`, không đụng `docs/DB_SCHEMA.md` (guard test chỉ soi model, mà model không đổi).
- **KHÔNG `python -c` trong `backend/`** — nó trỏ thẳng vào Postgres DEV thật. Muốn thăm dò thì viết test tạm rồi chạy pytest.
- Commit message **tiếng Việt** (thuật ngữ kỹ thuật giữ tiếng Anh), **KHÔNG** dòng `Co-Authored-By`.
- Mọi text UI **tiếng Việt**. Không tiếng Anh trong giao diện.
- Pydantic v2: field không khai trong schema `Out` sẽ bị **nuốt im lặng** — thêm field phải đi hết `dict service → schema Out → type TS`.
- Sửa route/schema backend xong phải **restart uvicorn** (không hot-reload đáng tin ở đây).
- Ô của tổ khác **KHÔNG** mang `cong_viec_id` và **KHÔNG** lộ người / khoán / mẻ / vật tư / ảnh KCS.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/app/repositories/san_xuat_repo.py` | thêm `cong_viec_cua_goi_cho_lenh` (lấy bước MỌI tổ) + `thu_tu_theo_step_key` + `bai_ghep_phu_step_key` |
| `backend/app/repositories/san_xuat_san_luong_repo.py` | thêm `ban_giao_toi_nhieu_dich` (bản gộp của `ban_giao_toi_dich`, né N+1) |
| `backend/app/services/san_xuat/routing_dai.py` | **MỚI** — dựng mảng `routing` cho cả một trang lệnh. Tách file vì `board.py` đã 1200+ dòng |
| `backend/app/services/san_xuat/board.py` | nối `routing_dai.dung_routing` vào nhánh `nhom="lenh"` |
| `backend/app/schemas/san_xuat.py` | `RoutingBuocOut` + field `routing` trên `LenhNhomOut` |
| `frontend/src/api/client.ts` | type `SxRoutingBuoc` + field `routing` trên `SxLenhNhom` |
| `frontend/src/pages/ThsxDaiRouting.tsx` | **MỚI** — component dải 5 ô |
| `frontend/src/pages/ThsxLenhGroups.tsx` | chèn dải vào thân thẻ lệnh |
| `frontend/src/pages/thuc-hien-sx.css` | style `.thsx-dai*` |

---

### Task 1: Repo — lấy bước của MỌI tổ trong gói + thứ tự routing

**Files:**
- Modify: `backend/app/repositories/san_xuat_repo.py` (thêm sau `cong_viec_cua_goi`, dòng 346-354)
- Modify: `backend/app/repositories/san_xuat_san_luong_repo.py` (thêm sau `ban_giao_toi_dich`, dòng 380-388)
- Test: `backend/tests/test_san_xuat_routing_dai.py` (mới)

**Interfaces:**
- Consumes: `SanXuatRepository`, `SanXuatSanLuongRepository` đang có.
- Produces:
  - `SanXuatRepository.cong_viec_cua_goi_cho_lenh(goi_ids: set[int], lsx_ids: set[int]) -> list[SanXuatCongViec]`
  - `SanXuatRepository.thu_tu_theo_step_key(lsx_ids: set[int]) -> dict[str, tuple[int, int]]` — `{step_key: (lsx_id, thu_tu)}`
  - `SanXuatRepository.bai_ghep_phu_step_key(lsx_ids: set[int]) -> dict[int, list[str]]` — `{bai_ghep_cong_doan_id: [lsx_step_key, …]}`
  - `SanXuatSanLuongRepository.ban_giao_toi_nhieu_dich(cong_viec_ids) -> dict[int, list[SanXuatBanGiao]]`

- [ ] **Step 1: Viết test thất bại cho `cong_viec_cua_goi_cho_lenh`**

Tạo `backend/tests/test_san_xuat_routing_dai.py`:

```python
"""Dải routing trên bàn tổ (docs/design-dai-routing-tren-ban-to.md).

Bàn tổ chỉ lọc bước CỦA TỔ mình; dải cần bước của MỌI tổ trong cùng gói phát hành,
sắp theo thứ tự routing của lệnh.
"""
from __future__ import annotations

from app.repositories.san_xuat_repo import SanXuatRepository

from tests.test_san_xuat_ban_giao import (  # noqa: F401
    _T0,
    _batch,
    _hai_cv,
    _to_dich,
)
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def test_lay_buoc_cua_moi_to_trong_goi(db, orders, lsx_svc, admin, customer):
    """cv2 chuyển sang tổ khác — hàm vẫn phải trả CẢ HAI bước."""
    to, cv1, cv2, lsx_id = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAI-1")
    to_khac, _u = _to_dich(db, ma="TO-DAI-1-DICH")
    cv2.department_id = to_khac.id
    db.commit()

    repo = SanXuatRepository(db)
    rows = repo.cong_viec_cua_goi_cho_lenh({cv1.goi_id}, {lsx_id})
    ids = {cv.id for cv in rows}
    assert cv1.id in ids
    assert cv2.id in ids
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py -v
```

Expected: FAIL — `AttributeError: 'SanXuatRepository' object has no attribute 'cong_viec_cua_goi_cho_lenh'`

- [ ] **Step 3: Viết `cong_viec_cua_goi_cho_lenh`**

Chèn vào `backend/app/repositories/san_xuat_repo.py` ngay sau `cong_viec_cua_goi`:

```python
    def cong_viec_cua_goi_cho_lenh(
        self, goi_ids: set[int], lsx_ids: set[int]
    ) -> list[SanXuatCongViec]:
        """Bước của MỌI TỔ trong các gói đã cho — nguồn của dải routing trên bàn tổ.

        Khác `cong_viec_cua_lenh` ở đúng một chỗ, nhưng là chỗ cốt lõi: KHÔNG lọc
        `department_id`. Bàn tổ lọc theo tổ để ra danh sách VIỆC; dải thì cần cả chuỗi, kể cả
        bước của tổ khác.

        Lấy hai nhánh: bước RIÊNG của các lệnh trong trang, và MỌI bước chạy chung của bài ghép
        trong cùng gói (bước chung neo `bai_ghep_id`, `lsx_id` để trống nên không lọc theo lệnh
        được — bên gọi nối lại qua `bai_ghep_phu_step_key`).
        """
        if not goi_ids or not lsx_ids:
            return []
        from sqlalchemy import or_

        return list(
            self.db.execute(
                select(SanXuatCongViec)
                .where(
                    SanXuatCongViec.goi_id.in_(goi_ids),
                    or_(
                        SanXuatCongViec.lsx_id.in_(lsx_ids),
                        SanXuatCongViec.bai_ghep_cong_doan_id.is_not(None),
                    ),
                )
                .order_by(SanXuatCongViec.id)
            ).scalars()
        )
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py -v
```

Expected: PASS

- [ ] **Step 5: Viết test thất bại cho `thu_tu_theo_step_key`**

Thêm vào cuối `backend/tests/test_san_xuat_routing_dai.py`:

```python
def test_thu_tu_theo_step_key(db, orders, lsx_svc, admin, customer):
    """Map step_key → (lsx_id, thu_tu) để sắp dải; `san_xuat_cong_viec` không có cột thứ tự."""
    to, cv1, cv2, lsx_id = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAI-2")
    repo = SanXuatRepository(db)
    m = repo.thu_tu_theo_step_key({lsx_id})
    assert cv1.step_key in m
    assert cv2.step_key in m
    assert m[cv1.step_key][0] == lsx_id
    assert m[cv1.step_key][1] < m[cv2.step_key][1]
```

- [ ] **Step 6: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py::test_thu_tu_theo_step_key -v
```

Expected: FAIL — `AttributeError: … has no attribute 'thu_tu_theo_step_key'`

- [ ] **Step 7: Viết `thu_tu_theo_step_key` và `bai_ghep_phu_step_key`**

Chèn ngay sau `cong_viec_cua_goi_cho_lenh`:

```python
    def thu_tu_theo_step_key(self, lsx_ids: set[int]) -> dict[str, tuple[int, int]]:
        """{step_key: (lsx_id, thu_tu)} cho cả một trang bàn tổ — MỘT truy vấn.

        `san_xuat_cong_viec` KHÔNG có cột thứ tự, nên thứ tự dải phải tra ngược về
        `lsx_cong_doan.thu_tu`. Đọc routing SỐNG ở đây là an toàn: phát hành đã khoá routing
        (`da_phat_hanh`) nên `thu_tu` không đổi dưới chân snapshot.

        ĐỪNG sắp dải theo `du_kien_bat_dau` như `cong_viec_cua_lenh` làm cho danh sách việc —
        lệnh chưa đặt giờ thì mốc trống và dải nhảy lung tung.
        """
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(LsxCongDoan.step_key, LsxCongDoan.lsx_id, LsxCongDoan.thu_tu)
            .where(LsxCongDoan.lsx_id.in_(lsx_ids), LsxCongDoan.step_key.is_not(None))
        ).all()
        return {sk: (lid, tt) for sk, lid, tt in rows}

    def bai_ghep_phu_step_key(self, lsx_ids: set[int]) -> dict[int, list[str]]:
        """{bai_ghep_cong_doan_id: [lsx_step_key, …]} — bước chạy chung PHỦ lên bước nào của lệnh.

        Bước chung của bài ghép mang `step_key` của CHÍNH bài ghép, không phải của lệnh, nên nối
        vào dải của một lệnh phải đi qua bảng map này.
        """
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.bai_ghep_cong_doan_id, BaiGhepCongDoanMap.lsx_step_key)
            .where(BaiGhepCongDoanMap.lsx_id.in_(lsx_ids))
        ).all()
        ra: dict[int, list[str]] = {}
        for bgcd_id, sk in rows:
            if sk:
                ra.setdefault(bgcd_id, []).append(sk)
        return ra
```

Import ở đầu file nếu chưa có (kiểm bằng `grep -n "LsxCongDoan\|BaiGhepCongDoanMap" backend/app/repositories/san_xuat_repo.py | head`):

```python
from ..models.bai_ghep_cong_doan import BaiGhepCongDoanMap
from ..models.lsx import LsxCongDoan
```

- [ ] **Step 8: Chạy test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py -v
```

Expected: 2 passed

- [ ] **Step 9: Viết test thất bại cho `ban_giao_toi_nhieu_dich`**

Thêm vào cuối `backend/tests/test_san_xuat_routing_dai.py`:

```python
def test_ban_giao_toi_nhieu_dich_gop_mot_truy_van(db, orders, lsx_svc, admin, customer):
    """Bản GỘP của `ban_giao_toi_dich` — trang bàn tổ có 20 lệnh, gọi từng cái là N+1."""
    from app.repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
    from app.services.san_xuat import ban_giao

    to, cv1, cv2, _lsx = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAI-3")
    b = _batch(db, admin, cv1, tot=120)
    ban_giao.de_xuat(db, user=admin, nguon_cong_viec_id=cv1.id,
                     dich_cong_viec_id=cv2.id, batch_ids=[b])

    sl = SanXuatSanLuongRepository(db)
    m = sl.ban_giao_toi_nhieu_dich([cv1.id, cv2.id])
    assert cv1.id not in m
    assert len(m[cv2.id]) == 1
    assert float(m[cv2.id][0].so_luong) == 120.0
```

- [ ] **Step 10: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py::test_ban_giao_toi_nhieu_dich_gop_mot_truy_van -v
```

Expected: FAIL — `AttributeError: … has no attribute 'ban_giao_toi_nhieu_dich'`

- [ ] **Step 11: Viết `ban_giao_toi_nhieu_dich`**

Chèn vào `backend/app/repositories/san_xuat_san_luong_repo.py` ngay sau `ban_giao_toi_dich` (dòng 388):

```python
    def ban_giao_toi_nhieu_dich(self, cong_viec_ids) -> dict[int, list[SanXuatBanGiao]]:
        """{dich_cong_viec_id: [bàn giao nhận về]} cho một TẬP công việc — MỘT truy vấn gộp.

        Cùng lý do `tong_tot_nhieu` ra đời: dải routing của một trang bàn tổ hỏi "đã giao sang
        tôi chưa" cho tới 20 lệnh, gọi `ban_giao_toi_dich` từng cái là 20 truy vấn.

        Id không có bàn giao nào thì KHÔNG có mặt trong dict (bên gọi tự `.get(id, [])`).
        """
        ids = [i for i in set(cong_viec_ids) if i]
        if not ids:
            return {}
        rows = self.db.scalars(
            select(SanXuatBanGiao)
            .where(SanXuatBanGiao.dich_cong_viec_id.in_(ids))
            .order_by(SanXuatBanGiao.id)
        )
        ra: dict[int, list[SanXuatBanGiao]] = {}
        for bg in rows:
            ra.setdefault(bg.dich_cong_viec_id, []).append(bg)
        return ra
```

- [ ] **Step 12: Chạy cả file test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py -v
```

Expected: 3 passed

- [ ] **Step 13: Commit**

```bash
git add backend/app/repositories/san_xuat_repo.py backend/app/repositories/san_xuat_san_luong_repo.py backend/tests/test_san_xuat_routing_dai.py
git commit -m "feat(san-xuat): repo lấy bước mọi tổ trong gói + thứ tự routing cho dải bàn tổ"
```

---

### Task 2: Service — dựng mảng `routing` cho cả một trang

**Files:**
- Create: `backend/app/services/san_xuat/routing_dai.py`
- Test: `backend/tests/test_san_xuat_routing_dai.py` (thêm test)

**Interfaces:**
- Consumes: `cong_viec_cua_goi_cho_lenh`, `thu_tu_theo_step_key`, `bai_ghep_phu_step_key`, `ban_giao_toi_nhieu_dich` (Task 1); `SanXuatSanLuongRepository.tong_tot_nhieu`, `SanXuatRepository.to_ten_nhan`, `dau_vao.tran_ghi` (đã có).
- Produces: `dung_routing(db, repo, *, khoa, cv_cua_toi, to_cua_ban) -> dict[tuple[str, int | None], list[dict]]`
  - `khoa`: `list[tuple[str, int | None]]` — đúng biến `khoa` của `board.py:429`.
  - `cv_cua_toi`: `list[SanXuatCongViec]` — đúng biến `rows` của `board.py:431`.
  - `to_cua_ban`: `set[int]` — hợp của `tron` và `rieng` ở `board.py:410`.
  - Trả: `{("lsx", 14): [ô, ô, …]}`, mỗi ô là dict đúng hình `RoutingBuocOut` của Task 3.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_san_xuat_routing_dai.py`:

```python
def test_dung_routing_danh_dau_buoc_cua_toi(db, orders, lsx_svc, admin, customer):
    """Dải có cả hai bước; chỉ bước của tổ mình mang `la_cua_toi` và `cong_viec_id`."""
    from app.services.san_xuat.routing_dai import dung_routing

    to, cv1, cv2, lsx_id = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAI-4")
    to_khac, _u = _to_dich(db, ma="TO-DAI-4-DICH")
    cv1.department_id = to_khac.id
    db.commit()

    repo = SanXuatRepository(db)
    ra = dung_routing(db, repo, khoa=[("lsx", lsx_id)], cv_cua_toi=[cv2],
                      to_cua_ban={to.id})
    dai = ra[("lsx", lsx_id)]
    assert [o["ten_cong_doan"] for o in dai] == [cv1.ten_cong_doan, cv2.ten_cong_doan]
    assert dai[0]["la_cua_toi"] is False
    assert dai[0]["cong_viec_id"] is None
    assert dai[0]["to_ten"] == to_khac.name
    assert dai[1]["la_cua_toi"] is True
    assert dai[1]["cong_viec_id"] == cv2.id
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py::test_dung_routing_danh_dau_buoc_cua_toi -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.san_xuat.routing_dai'`

- [ ] **Step 3: Viết `routing_dai.py`**

Tạo `backend/app/services/san_xuat/routing_dai.py`:

```python
"""Dải ROUTING của lệnh trên bàn tổ (23/09/2026, `docs/design-dai-routing-tren-ban-to.md`).

Bàn tổ lọc `department_id` nên thẻ lệnh chỉ hiện bước của tổ mình. Module này dựng thêm CHUỖI
đầy đủ: tổ thấy mình đứng thứ mấy, bước trước đã ra bao nhiêu và đã giao sang chưa, làm xong thì
hàng đi đâu.

Tách khỏi `board.py` vì file đó đã hơn 1200 dòng và đây là một mặt đọc độc lập.

CHỈ ĐỌC, và đọc từ SNAPSHOT gói (`san_xuat_cong_viec`) — cùng nguyên tắc với cả `board.py`. Thứ
DUY NHẤT lấy từ routing sống là THỨ TỰ (`lsx_cong_doan.thu_tu`), an toàn vì phát hành đã khoá
routing.

Mức lộ ra cho bước của TỔ KHÁC: tên · tổ · trạng thái · kế hoạch/thực tế · đã giao. KHÔNG người,
KHÔNG khoán, KHÔNG mẻ, KHÔNG vật tư, KHÔNG ảnh KCS — và KHÔNG `cong_viec_id`, để FE không có
đường mở drawer việc của tổ khác.

HIỆU NĂNG: mọi truy vấn ở đây gom theo CẢ TRANG (tối đa 20 lệnh). Đừng gọi
`cong_viec_chang_truoc` / `cong_viec_chang_sau` trong vòng lặp — mỗi lần 3-4 truy vấn, nhân 20
lệnh × 5 bước là vỡ trang.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat_san_luong import BG_DIEU_CHINH, BG_XAC_NHAN
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from . import dau_vao

_DA_CHOT = (BG_XAC_NHAN, BG_DIEU_CHINH)


def _gop_trang_thai(tts: list[str]) -> str:
    """Trạng thái của MỘT BƯỚC gộp từ các lần chạy của nó (mg `0254`).

    Yếu nhất thắng: còn lần nào chờ làm thì cả bước là chờ làm. Có lần đang chạy ⇒ đang chạy
    (tổ cần thấy "bước này đã động vào"), rồi mới tới tạm dừng, cuối cùng hết xong mới là xong.
    """
    if "running" in tts:
        return "running"
    if "released" in tts:
        return "released"
    if "paused" in tts:
        return "paused"
    return "completed" if tts else "released"


def dung_routing(
    db: Session,
    repo: SanXuatRepository,
    *,
    khoa: list[tuple[str, int | None]],
    cv_cua_toi: list,
    to_cua_ban: set[int],
) -> dict[tuple[str, int | None], list[dict]]:
    """{("lsx", id): [ô, ô, …]} — dải routing của MỌI lệnh trong trang, ba truy vấn cho cả trang.

    `cv_cua_toi` là đúng các công việc bàn tổ đã lấy được (dùng để biết gói nào và bước nào là
    của mình). `to_cua_ban` là phạm vi tổ của bàn đang mở — bàn cấp gom nhiều tổ con nên
    "của tôi" có thể là nhiều ô.
    """
    lsx_ids = {i for loai, i in khoa if loai == "lsx" and i}
    goi_ids = {cv.goi_id for cv in cv_cua_toi if cv.goi_id}
    if not lsx_ids or not goi_ids:
        return {}

    sl = SanXuatSanLuongRepository(db)
    tat_ca = repo.cong_viec_cua_goi_cho_lenh(goi_ids, lsx_ids)
    thu_tu = repo.thu_tu_theo_step_key(lsx_ids)
    phu = repo.bai_ghep_phu_step_key(lsx_ids)
    tot = sl.tong_tot_nhieu({cv.id for cv in tat_ca})
    to_ten = repo.to_ten_nhan({cv.department_id for cv in tat_ca if cv.department_id})
    bg_map = sl.ban_giao_toi_nhieu_dich({cv.id for cv in cv_cua_toi})
    cv_toi_ids = {cv.id for cv in cv_cua_toi}

    # Gom công việc về từng (lsx_id, step_key của LỆNH). Bước chung của bài ghép đứng tên nhiều
    # bước lệnh một lúc, nên nó góp mặt vào dải của TỪNG lệnh nó phủ.
    gom: dict[tuple[int, str], list] = {}
    for cv in tat_ca:
        if cv.bai_ghep_cong_doan_id is not None:
            for sk in phu.get(cv.bai_ghep_cong_doan_id, []):
                lid = thu_tu.get(sk, (None, 0))[0]
                if lid in lsx_ids:
                    gom.setdefault((lid, sk), []).append(cv)
        elif cv.lsx_id in lsx_ids and cv.step_key:
            gom.setdefault((cv.lsx_id, cv.step_key), []).append(cv)

    ra: dict[tuple[str, int | None], list[dict]] = {}
    for lsx_id in lsx_ids:
        buoc = [(sk, cvs) for (lid, sk), cvs in gom.items() if lid == lsx_id]
        buoc.sort(key=lambda x: (thu_tu.get(x[0], (0, 10**6))[1], x[0]))
        dai: list[dict] = []
        for idx, (sk, cvs) in enumerate(buoc, start=1):
            dau = cvs[0]
            cua_toi = [c for c in cvs if c.id in cv_toi_ids]
            o = {
                "thu_tu": idx,
                "step_key": sk,
                "ten_cong_doan": _ten_buoc(cvs),
                "to_id": dau.department_id,
                "to_ten": to_ten.get(dau.department_id or 0),
                "la_cua_toi": bool(cua_toi),
                "la_kcs_cuoi": any(c.la_kcs_cuoi for c in cvs),
                "trang_thai": _gop_trang_thai([c.trang_thai for c in cvs]),
                "phan_doan_tong": max(c.phan_doan_tong for c in cvs),
                "chay_chung": dau.bai_ghep_cong_doan_id is not None,
                "ke_hoach": _cong(c.so_luong_ra for c in cvs),
                "thuc_te": sum(tot.get(c.id, 0.0) for c in cvs),
                "don_vi": dau.don_vi_ra,
                # Ba khoá dưới CHỈ có ở ô của mình — xem docstring module.
                "cong_viec_id": cua_toi[0].id if cua_toi else None,
                "da_giao_sang_toi": None,
                "tran_ghi": None,
            }
            if cua_toi:
                cv = cua_toi[0]
                nhan = sum(
                    float(b.so_luong or 0)
                    for b in bg_map.get(cv.id, [])
                    if b.trang_thai in _DA_CHOT
                )
                o["da_giao_sang_toi"] = nhan or None
                t = dau_vao.tran_ghi(sl, cv)
                o["tran_ghi"] = t.get("tran")
            dai.append(o)
        if len(dai) > 1:
            ra[("lsx", lsx_id)] = dai
    return ra


def _ten_buoc(cvs: list) -> str:
    """Tên bước: bước chưa tách lấy thẳng; bước tách thì bỏ hậu tố "(lần k/N)" của từng lần chạy
    để ô không mang tên của riêng lần chạy đầu."""
    ten = cvs[0].ten_cong_doan or ""
    if len(cvs) > 1 and " (lần " in ten:
        return ten.split(" (lần ")[0]
    return ten


def _cong(vals) -> float | None:
    so = [float(v) for v in vals if v is not None]
    return sum(so) if so else None
```

- [ ] **Step 4: Kiểm hình dạng `tran_ghi` trước khi tin vào `t.get("tran")`**

`dau_vao.tran_ghi` trả dict ở `backend/app/services/san_xuat/dau_vao.py:94`. Mở đọc đúng tên khoá:

```bash
cd backend && sed -n '67,102p' app/services/san_xuat/dau_vao.py
```

Nếu khoá không phải `"tran"` thì sửa dòng `o["tran_ghi"] = t.get("tran")` cho khớp, và sửa cả tên khoá trong test ở Task 3. Nếu hàm cần tham số khác `(sl, cv)` thì gọi đúng chữ ký nó có.

- [ ] **Step 5: Chạy test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py -v
```

Expected: 4 passed

- [ ] **Step 6: Viết test cho bước tách lần chạy gộp một ô**

Thêm vào cuối file test:

```python
def test_buoc_tach_lan_chay_gop_mot_o(db, orders, lsx_svc, admin, customer):
    """Một bước tách N lần chạy = MỘT ô trên dải; trạng thái lấy yếu nhất, số cộng dồn."""
    from app.services.san_xuat.routing_dai import _gop_trang_thai

    assert _gop_trang_thai(["completed", "released"]) == "released"
    assert _gop_trang_thai(["completed", "running"]) == "running"
    assert _gop_trang_thai(["completed", "completed"]) == "completed"
    assert _gop_trang_thai(["paused", "completed"]) == "paused"
    assert _gop_trang_thai([]) == "released"
```

- [ ] **Step 7: Chạy test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py -v
```

Expected: 5 passed

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/san_xuat/routing_dai.py backend/tests/test_san_xuat_routing_dai.py
git commit -m "feat(san-xuat): service dựng dải routing cho bàn tổ"
```

---

### Task 3: Nối vào response `/work-items` + schema

**Files:**
- Modify: `backend/app/services/san_xuat/board.py` (nhánh `nhom="lenh"`, dòng 424-470)
- Modify: `backend/app/schemas/san_xuat.py` (`LenhNhomOut`, dòng 140-157)
- Test: `backend/tests/test_san_xuat_routing_dai.py` (thêm test qua service `board`)

**Interfaces:**
- Consumes: `routing_dai.dung_routing` (Task 2).
- Produces: `board.work_items(...)` trả mỗi phần tử `lenh` kèm khoá `routing: list[dict]`; schema `RoutingBuocOut`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_san_xuat_routing_dai.py`:

```python
def test_work_items_tra_ve_dai_routing(db, orders, lsx_svc, admin, customer):
    """Dải đi CÙNG response work-items, không tách endpoint riêng — nhờ vậy nó nằm sẵn trong
    đường refetch theo tick SSE của bàn tổ."""
    from app.services.rbac_service import AuthorizationService
    from app.services.san_xuat import board

    to, cv1, cv2, lsx_id = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-DAI-5")
    to_khac, _u = _to_dich(db, ma="TO-DAI-5-DICH")
    cv1.department_id = to_khac.id
    db.commit()

    ra = board.work_items(db, admin, AuthorizationService(db), team_id=to.id, nhom="lenh")
    l = next(x for x in ra["lenh"] if x["lsx_id"] == lsx_id)
    assert len(l["routing"]) == 2
    assert [o["la_cua_toi"] for o in l["routing"]] == [False, True]
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py::test_work_items_tra_ve_dai_routing -v
```

Expected: FAIL — `KeyError: 'routing'`

- [ ] **Step 3: Xác minh chữ ký thật của `board.work_items`**

```bash
cd backend && grep -n "^def work_items" -A 14 app/services/san_xuat/board.py
```

Nếu tên hàm hoặc tham số khác với lời gọi ở test Step 1 thì **sửa test cho khớp code**, đừng đổi chữ ký hàm — router đang gọi nó.

- [ ] **Step 4: Nối `dung_routing` vào `board.py`**

Trong `backend/app/services/san_xuat/board.py`, thêm import cạnh `from . import dau_vao, viec_khoan`:

```python
from . import dau_vao, routing_dai, viec_khoan
```

Ngay sau dòng `rows = repo.cong_viec_cua_lenh(tron, khoa, employee_id=emp_id, rieng_ids=rieng)` (dòng 431), chèn:

```python
    # Dải routing: chuỗi công đoạn ĐẦY ĐỦ của lệnh, kể cả bước của tổ khác (chỉ đọc). Dựng từ
    # `rows` TRƯỚC khi lọc `trang_thai` — lọc trạng thái là thao tác của danh sách VIỆC, dải thì
    # phải luôn đủ chuỗi, không thì tổ lọc "đang chạy" một cái là dải cụt mất mấy bước.
    dai_theo_khoa = routing_dai.dung_routing(
        db, repo, khoa=khoa, cv_cua_toi=rows, to_cua_ban=tron | (rieng or set()),
    )
```

Trong vòng `for (loai, nid), som, muon in khoa_trang:`, thêm vào dict `ra.append({...})` một khoá, đặt ngay trước `"cong_viec"`:

```python
            "routing": dai_theo_khoa.get((loai, nid), []),
```

- [ ] **Step 5: Khai schema (nếu không khai, Pydantic NUỐT IM LẶNG field này)**

Trong `backend/app/schemas/san_xuat.py`, thêm ngay trước `class LenhNhomOut`:

```python
class RoutingBuocOut(BaseModel):
    """Một BƯỚC trên dải routing của thẻ lệnh (`docs/design-dai-routing-tren-ban-to.md`).

    Bước của tổ KHÁC chỉ mang bấy nhiêu: tên · tổ · trạng thái · số. `cong_viec_id` để None có
    chủ đích — FE không được có đường mở drawer việc của tổ khác."""
    thu_tu: int
    step_key: str | None = None
    ten_cong_doan: str
    to_id: int | None = None
    to_ten: str | None = None
    la_cua_toi: bool
    la_kcs_cuoi: bool
    trang_thai: str
    phan_doan_tong: int = 1
    chay_chung: bool = False          # bước chạy chung của bài ghép
    ke_hoach: float | None = None
    thuc_te: float = 0.0
    don_vi: str | None = None
    # Ba khoá dưới CHỈ có giá trị ở ô của chính tổ mình.
    cong_viec_id: int | None = None
    da_giao_sang_toi: float | None = None
    tran_ghi: float | None = None
```

Trong `class LenhNhomOut`, thêm ngay trước `cong_viec: list[WorkItemOut]`:

```python
    # Chuỗi công đoạn ĐẦY ĐỦ của lệnh (mọi tổ, chỉ đọc). Rỗng khi lệnh chỉ có một bước.
    routing: list[RoutingBuocOut] = []
```

- [ ] **Step 6: Chạy test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_san_xuat_routing_dai.py tests/test_san_xuat_board.py tests/test_san_xuat_board_api.py tests/test_san_xuat_lenh_phan_trang.py -v
```

Expected: tất cả PASS (test cũ không được đỏ — `routing` là field thêm, mặc định rỗng)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py backend/tests/test_san_xuat_routing_dai.py
git commit -m "feat(san-xuat): trả dải routing kèm response work-items"
```

---

### Task 4: Frontend — component dải + type

**Files:**
- Modify: `frontend/src/api/client.ts` (`SxLenhNhom`, dòng 1432-1445)
- Create: `frontend/src/pages/ThsxDaiRouting.tsx`
- Create: `frontend/src/pages/ThsxDaiRouting.test.tsx`
- Modify: `frontend/src/pages/ThsxLenhGroups.tsx` (thân thẻ lệnh)
- Modify: `frontend/src/pages/thuc-hien-sx.css`

**Interfaces:**
- Consumes: khoá `routing` của Task 3; `ThsxTrangThaiPill` + `ttMeta` từ `./thsxShared`; `Icon` từ `../components/Icons`.
- Produces: `export function ThsxDaiRouting({ dai }: { dai: SxRoutingBuoc[] })`; `export interface SxRoutingBuoc`.

- [ ] **Step 1: Thêm type vào `client.ts`**

Chèn ngay trước `export interface SxLenhNhom` (dòng 1432):

```ts
/** Một BƯỚC trên dải routing của thẻ lệnh — chuỗi công đoạn đầy đủ, kể cả bước của tổ khác.
 *  `cong_viec_id` chỉ có ở bước của CHÍNH tổ mình: bước tổ khác là chỉ-đọc, không mở drawer. */
export interface SxRoutingBuoc {
  thu_tu: number;
  step_key: string | null;
  ten_cong_doan: string;
  to_id: number | null;
  to_ten: string | null;
  la_cua_toi: boolean;
  la_kcs_cuoi: boolean;
  trang_thai: string;
  phan_doan_tong: number;
  chay_chung: boolean;
  ke_hoach: number | null;
  thuc_te: number;
  don_vi: string | null;
  cong_viec_id: number | null;
  da_giao_sang_toi: number | null;
  tran_ghi: number | null;
}
```

Trong `SxLenhNhom`, thêm ngay trước `cong_viec: SxWorkItem[];`:

```ts
  routing?: SxRoutingBuoc[];   // chuỗi công đoạn đầy đủ; rỗng khi lệnh chỉ có một bước
```

- [ ] **Step 2: Viết test thất bại cho component**

Tạo `frontend/src/pages/ThsxDaiRouting.test.tsx`:

```tsx
// Dải routing: tổ thấy cả chuỗi, bước của tổ khác là CHỈ ĐỌC (không nút, không mở được).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThsxDaiRouting } from "./ThsxDaiRouting";
import type { SxRoutingBuoc } from "../api/client";

function buoc(p: Partial<SxRoutingBuoc>): SxRoutingBuoc {
  return {
    thu_tu: 1, step_key: "s1", ten_cong_doan: "In", to_id: 1, to_ten: "Tổ in",
    la_cua_toi: false, la_kcs_cuoi: false, trang_thai: "completed",
    phan_doan_tong: 1, chay_chung: false, ke_hoach: 5300, thuc_te: 5300,
    don_vi: "tờ", cong_viec_id: null, da_giao_sang_toi: null, tran_ghi: null,
    ...p,
  };
}

const dai: SxRoutingBuoc[] = [
  buoc({ thu_tu: 1, ten_cong_doan: "In", to_ten: "Nhóm in 5 màu" }),
  buoc({ thu_tu: 2, ten_cong_doan: "Bế", to_ten: "Tổ bế", la_cua_toi: true,
         trang_thai: "running", cong_viec_id: 88, da_giao_sang_toi: 5220, tran_ghi: 10440 }),
  buoc({ thu_tu: 3, ten_cong_doan: "Dán", to_ten: "Tổ dán", trang_thai: "released" }),
];

describe("ThsxDaiRouting", () => {
  it("bày đủ chuỗi công đoạn kèm tổ giữ từng bước", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.getByText("In")).toBeInTheDocument();
    expect(screen.getByText("Bế")).toBeInTheDocument();
    expect(screen.getByText("Dán")).toBeInTheDocument();
    expect(screen.getByText("Nhóm in 5 màu")).toBeInTheDocument();
  });

  it("đánh dấu bước của tổ mình", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.getByText("Tổ của bạn")).toBeInTheDocument();
  });

  it("không ô nào bấm được — dải là chỉ đọc", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("nói rõ đã nhận bao nhiêu và trần ghi mẻ", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.getByText(/5\.220/)).toBeInTheDocument();
    expect(screen.getByText(/10\.440/)).toBeInTheDocument();
  });

  it("lệnh một bước thì không vẽ dải", () => {
    const { container } = render(<ThsxDaiRouting dai={[dai[0]]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

```bash
cd frontend && npx vitest run src/pages/ThsxDaiRouting.test.tsx
```

Expected: FAIL — không resolve được `./ThsxDaiRouting`

- [ ] **Step 4: Viết component**

Tạo `frontend/src/pages/ThsxDaiRouting.tsx`:

```tsx
// DẢI ROUTING của lệnh trên bàn tổ (docs/design-dai-routing-tren-ban-to.md).
//
// Tổ chỉ thao tác với bước của mình nhưng phải ĐỌC được cả chuỗi: bước trước xong chưa, ra bao
// nhiêu, đã giao sang chưa; làm xong thì hàng đi đâu. Trước đây thẻ lệnh chỉ hiện đúng bước của
// tổ nên câu đó phải hỏi miệng ngoài xưởng.
//
// CHỈ ĐỌC — không `<button>`, không `onClick`, không mở drawer. Bước của tổ khác không mang
// `cong_viec_id` nên cũng không có gì để mở.
import { Icon } from "../components/Icons";
import type { SxRoutingBuoc } from "../api/client";
import { ttMeta } from "./thsxShared";

/** Số kiểu Việt: 10.200 · 2,5 — cùng cách đọc với phần còn lại của bàn tổ. */
function so(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 3 });
}

/** Cửa sổ 5 ô quanh bước của mình; thừa hai đầu gom thành ô "+N".
 *  Không cuộn ngang: màn xưởng thao tác bằng tay, cuộn ngang là bẫy. */
function cuaSo(dai: SxRoutingBuoc[]): { truoc: number; hien: SxRoutingBuoc[]; sau: number } {
  if (dai.length <= 5) return { truoc: 0, hien: dai, sau: 0 };
  const i = Math.max(0, dai.findIndex((b) => b.la_cua_toi));
  let dau = Math.max(0, i - 2);
  if (dau + 5 > dai.length) dau = dai.length - 5;
  return { truoc: dau, hien: dai.slice(dau, dau + 5), sau: dai.length - dau - 5 };
}

function Gom({ n }: { n: number }) {
  return <span className="thsx-dai__gom" aria-label={`còn ${n} công đoạn nữa`}>+{n}</span>;
}

export function ThsxDaiRouting({ dai }: { dai: SxRoutingBuoc[] }) {
  // Lệnh một bước: vẽ một ô lẻ là nhiễu, không phải thông tin.
  if (!dai || dai.length < 2) return null;
  const { truoc, hien, sau } = cuaSo(dai);
  const toi = dai.find((b) => b.la_cua_toi);

  return (
    <div className="thsx-dai">
      <ol className="thsx-dai__list" aria-label="Chuỗi công đoạn của lệnh">
        {truoc > 0 && <li className="thsx-dai__o thsx-dai__o--gom"><Gom n={truoc} /></li>}
        {hien.map((b) => {
          const m = ttMeta(b.trang_thai);
          return (
            <li key={b.step_key ?? b.thu_tu}
                className={`thsx-dai__o${b.la_cua_toi ? " thsx-dai__o--toi" : ""}`}>
              <span className="thsx-dai__ten">
                {b.ten_cong_doan}
                {b.phan_doan_tong > 1 && <em className="thsx-dai__lan"> · {b.phan_doan_tong} lần chạy</em>}
              </span>
              <span className="thsx-dai__to">
                {b.la_cua_toi ? "Tổ của bạn" : (b.to_ten ?? "— chưa rõ tổ —")}
                {b.chay_chung && <em className="thsx-dai__chung"> · chạy chung</em>}
              </span>
              <span className={`thsx-tt ${m.cls} thsx-tt--xs`}>
                <Icon name={m.icon} size={11} /><span>{m.label}</span>
              </span>
              <span className="thsx-dai__so thsx-num">
                {b.thuc_te > 0 ? so(b.thuc_te) : (b.ke_hoach != null ? so(b.ke_hoach) : "—")}
                {b.don_vi ? ` ${b.don_vi}` : ""}
              </span>
              {b.la_kcs_cuoi && <span className="thsx-dai__cuoi">KCS cuối</span>}
            </li>
          );
        })}
        {sau > 0 && <li className="thsx-dai__o thsx-dai__o--gom"><Gom n={sau} /></li>}
      </ol>
      {toi?.da_giao_sang_toi != null && (
        <p className="thsx-dai__nhan">
          <Icon name="download" size={13} />
          <span>Đã nhận <b className="thsx-num">{so(toi.da_giao_sang_toi)}</b></span>
          {toi.tran_ghi != null && (
            <span className="thsx-dai__tran">
              → ghi mẻ tối đa <b className="thsx-num">{so(toi.tran_ghi)}</b>
              {toi.don_vi ? ` ${toi.don_vi}` : ""}
            </span>
          )}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Kiểm tên icon có thật trước khi chạy**

```bash
cd frontend && grep -n "download\|clock\|play\|pause\|check" src/components/Icons.tsx | head
```

Nếu `download` không có trong `IconName`, đổi sang một tên có thật trong file đó (ví dụ `box` hoặc `clipboard`). Icon sai tên làm `tsc` đỏ.

- [ ] **Step 6: Chạy test, xác nhận PASS**

```bash
cd frontend && npx vitest run src/pages/ThsxDaiRouting.test.tsx
```

Expected: 5 passed

- [ ] **Step 7: Viết CSS**

Thêm vào cuối `frontend/src/pages/thuc-hien-sx.css`:

```css
/* ===== DẢI ROUTING trên thẻ lệnh (docs/design-dai-routing-tren-ban-to.md) =================
   Chỉ đọc: ô tổ khác không bắt sự kiện, không đổi con trỏ. Không cuộn ngang — cửa sổ 5 ô do
   component cắt sẵn (xem `cuaSo`). */
.thsx-dai { padding: var(--sp-2) var(--sp-3) 0; }
.thsx-dai__list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
  grid-auto-flow: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.thsx-dai__o {
  display: flex;
  flex-direction: column;
  gap: 3px;
  align-items: flex-start;
  padding: 7px 9px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid transparent;
  min-width: 0;
  cursor: default;
}
.thsx-dai__o--toi { background: #fff; border-color: var(--rust); }
.thsx-dai__o--gom {
  align-items: center;
  justify-content: center;
  background: #eef2f7;
  max-width: 44px;
}
.thsx-dai__gom { color: #64748b; font-weight: var(--fw-bold); font-size: var(--fs-xs); }
/* Tên công đoạn KHÔNG ellipsis: nuốt mất "Bế tự động" thành "Bế tự..." là tổ đọc nhầm bước.
   Cho xuống dòng thay vì cắt. */
.thsx-dai__ten {
  font-size: var(--fs-sm);
  font-weight: var(--fw-bold);
  color: #0f172a;
  overflow-wrap: anywhere;
}
.thsx-dai__lan, .thsx-dai__chung { font-style: normal; color: #64748b; font-weight: 400; }
.thsx-dai__to { font-size: var(--fs-xs); color: #64748b; overflow-wrap: anywhere; }
.thsx-dai__o--toi .thsx-dai__to { color: var(--rust); font-weight: var(--fw-bold); }
.thsx-dai__so { font-size: var(--fs-xs); color: #475569; }
.thsx-dai__cuoi {
  font-size: 10px; color: #0f766e; background: #ccfbf1;
  border-radius: 99px; padding: 1px 7px;
}
.thsx-dai__nhan {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  margin: var(--sp-2) 0 0; font-size: var(--fs-xs); color: #475569;
}
.thsx-dai__nhan svg { color: #64748b; flex: none; }
.thsx-dai__tran { color: #b45309; }

/* Bề ngang hẹp: 3 ô, và cỡ chữ KHÔNG đóng cứng để không đè chữ. */
@media (max-width: 900px) {
  .thsx-dai__list { grid-auto-flow: row; grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
```

- [ ] **Step 8: Nối dải vào thẻ lệnh**

Trong `frontend/src/pages/ThsxLenhGroups.tsx`, thêm import:

```tsx
import { ThsxDaiRouting } from "./ThsxDaiRouting";
```

Tìm chỗ vẽ thân thẻ (`className="thsx-lenh__body"`) và đặt dải NGAY TRƯỚC `{render(l.cong_viec)}`:

```tsx
                <ThsxDaiRouting dai={l.routing ?? []} />
```

```bash
cd frontend && grep -n "thsx-lenh__body" -A 4 src/pages/ThsxLenhGroups.tsx
```

- [ ] **Step 9: Chạy test FE + tsc**

```bash
cd frontend && npx vitest run src/pages/ThsxDaiRouting.test.tsx src/pages/ThsxLenhGroups.test.tsx && npx tsc --noEmit
```

Expected: test PASS, `tsc` không báo lỗi

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/ThsxDaiRouting.tsx frontend/src/pages/ThsxDaiRouting.test.tsx frontend/src/pages/ThsxLenhGroups.tsx frontend/src/pages/thuc-hien-sx.css
git commit -m "feat(san-xuat): dải routing trên thẻ lệnh của bàn tổ"
```

---

### Task 5: Xác minh bằng dev-browser (BẮT BUỘC — luồng UI thật)

**Files:** không sửa file nào; chỉ sửa nếu phát hiện lỗi.

**Interfaces:** Consumes: toàn bộ Task 1-4.

CLAUDE.md của dự án: code xong một luồng nghiệp vụ có UI thì **BẮT BUỘC** thao tác lại đúng luồng đó bằng chuột/bàn phím thật trên dev-browser, **KHÔNG** dùng API/curl thay bất kỳ bước nào. Báo cáo phải liệt kê CỤ THỂ đã bấm gì, gõ gì, thấy gì ở từng bước.

- [ ] **Step 1: Khởi động BE + FE**

Đẻ tiến trình qua WMI `Win32_Process.Create` (Bash nền và `Start-Process` đều chết khi hết phiên). BE `--host localhost`, FE `localhost:5173`. Restart uvicorn là BẮT BUỘC ở Task này vì Task 3 sửa schema.

- [ ] **Step 2: Đăng nhập**

Mở `http://localhost:5173`, gõ `admin` / `admin123`. Input React cần set qua native setter nếu `type` không vào.

- [ ] **Step 3: Mở bàn Tổ bế**

Sidebar → Sản xuất → Tổ bế. Chụp màn.

- [ ] **Step 4: Đọc dải trên một thẻ lệnh nhiều công đoạn**

Xác nhận bằng mắt trên ảnh chụp:
- thẻ lệnh có dải công đoạn phía trên bảng việc;
- ô "Bế" viền cam, ghi "Tổ của bạn";
- các ô khác ghi đúng TÊN TỔ khác (không phải Tổ bế);
- dòng "Đã nhận … → ghi mẻ tối đa …" có số, không phải `NaN`/`undefined`.

Đếm số ô và đối chiếu với chuỗi công đoạn của chính lệnh đó ở màn Hồ sơ lệnh sản xuất.

- [ ] **Step 5: Bấm thử vào ô của tổ khác**

Click vào ô "In". Xác nhận KHÔNG có gì xảy ra: không mở drawer, không đổi trang, console không lỗi.

- [ ] **Step 6: Kiểm thao tác của bước mình vẫn chạy**

Bấm "Bắt đầu" (hoặc "Tạm dừng"/"Kết thúc" tuỳ trạng thái) trên bước của Tổ bế. Xác nhận nút vẫn hoạt động và dải cập nhật trạng thái sau khi màn tự nạp lại.

- [ ] **Step 7: Kiểm real-time chéo tổ**

Mở tab thứ hai vào bàn của tổ đứng TRƯỚC (ví dụ Tổ cán phủ), bấm Kết thúc một bước ở đó. Quay lại tab Tổ bế **không F5** — ô tương ứng trên dải phải tự đổi sang "Hoàn thành". Nếu không đổi, kiểm lại `eventTick` truyền xuống `ThucHienSxPage` (`AppShell.tsx:1401`).

- [ ] **Step 8: Kiểm bề ngang hẹp**

Thu cửa sổ xuống dưới 900px. Xác nhận dải xuống 3 ô/hàng, chữ không bị đè, không cuộn ngang.

- [ ] **Step 9: Kiểm console + network**

Đọc console: không lỗi đỏ. Đọc network: `/api/san-xuat/work-items` chỉ gọi MỘT lần cho một lần mở bàn (dải không đẻ request riêng).

- [ ] **Step 10: Commit nếu có sửa, rồi báo cáo**

Báo cáo liệt kê cụ thể từng bước đã bấm/gõ/thấy. Nếu buộc phải tắt qua API ở đoạn nào thì nói rõ ngay lúc báo cáo.

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §1 dải 5 ô, ô mình nhấn, ô khác chỉ đọc | 4 (component + CSS), 5 (kiểm bằng mắt) |
| §1 "Đã giao sang" + "chờ bạn giao" | 2 (`da_giao_sang_toi`), 4 (dòng "Đã nhận") |
| §1 dòng trần ghi mẻ | 2 (`tran_ghi` qua `dau_vao.tran_ghi`), 4 |
| §1 bước cuối ghi "KCS cuối" | 2 (`la_kcs_cuoi`), 4 (`.thsx-dai__cuoi`) |
| §2 nguồn từng số | 1, 2 |
| §2 thứ tự qua `LsxCongDoan.thu_tu` | 1 (`thu_tu_theo_step_key`) |
| §3 dải dài → cửa sổ 5 ô + "+N" | 4 (`cuaSo`) |
| §3 bước tách lần chạy gộp một ô | 2 (`_gop_trang_thai`, `_ten_buoc`, cộng dồn) |
| §3 bài ghép "chạy chung" | 1 (`bai_ghep_phu_step_key`), 2, 4 |
| §4 mức đọc chéo tổ, không lộ người/tiền | 2 (docstring + dict chỉ 15 khoá), 3 (schema khép kín) |
| §5 hợp đồng API + 3 truy vấn/trang | 2, 3 |
| §6 UI + bẫy màn hẹp | 4 (CSS + media query) |
| §7 real-time đã có sẵn | 3 (dải đi cùng response), 5 Step 7 |
| §8 không làm | tôn trọng xuyên suốt: không endpoint mới, không migration, không đụng `nhom="phang"` |

**Placeholder scan:** không có "TBD"/"tương tự Task N"/"xử lý lỗi phù hợp". Ba chỗ có bước KIỂM trước khi tin (Task 2 Step 4 hình dạng `tran_ghi`, Task 3 Step 3 chữ ký `work_items`, Task 4 Step 5 tên icon) — đó là kiểm chứng có chủ đích, không phải placeholder.

**Type consistency:** `dung_routing` dựng đúng 15 khoá; `RoutingBuocOut` khai đúng 15 khoá ấy; `SxRoutingBuoc` khai đúng 15 khoá ấy. `_gop_trang_thai` trả đúng 4 chuỗi mà `ttMeta` nhận. `cong_viec_cua_goi_cho_lenh(goi_ids, lsx_ids)` gọi ở Task 2 đúng thứ tự tham số.
