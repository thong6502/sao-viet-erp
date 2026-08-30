# Kế hoạch vật tư — siết logic trên giữ chỗ hiện có Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Siết logic của tính năng **giữ chỗ vật tư** (`GiuChoService`, đã có từ 17/08/2026) và cầu nối
**Nhập kho ↔ Mua hàng** đã có sẵn — KHÔNG xây tính năng mới. Cụ thể: (1) mỗi dòng giữ hứa (`nguon=dang_ve`)
biết CHÍNH XÁC nó bám dòng phiếu mua nào, để đối soát đúng khi PMH đổi; (2) hàng nhập kho tự chuyển
"hứa" → "có thật", không còn khoá lịch theo một ngày về đã lỗi thời; (3) người dùng thấy trạng thái
giữ chỗ 6 mức (Chưa rõ → Thiếu → Về muộn → Có thể giữ → Đã giữ → Đã cấp) thay vì chỉ 3 trạng thái cũ;
(4) xuất kho quy đúng lệnh đã ghép về bài đại diện; (5) sửa số lượng/routing/ghép-tách bài bị chặn khi
liên quan đang giữ chỗ; (6) mọi thay đổi đẩy real-time qua kênh SSE chung.

**Architecture:** Không có service/bảng mới. Mọi việc là MỞ RỘNG `GiuChoService`
(`backend/app/services/giu_cho_service.py`) và các điểm nó đã cắm vào: `KeHoachVatTuService`
(nguồn nhu cầu, không đổi luật), `StockVoucherService` (Nhập/Xuất kho gọi vào), `PurchaseService`
(PMH đổi thì gọi ra), `LsxService`/`BaiGhepService` (chặn sửa khi đang giữ). Một cột mới
(`purchase_request_line_id`) trên bảng `vat_tu_giu_cho` là thay đổi schema DUY NHẤT.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend, Postgres dev/prod, SQLite test), React/TypeScript
(frontend), pytest, `./init.ps1` (pytest + compileall) là lệnh verify chuẩn.

**Spec:** [docs/spec-ke-hoach-vat-tu.md](../../spec-ke-hoach-vat-tu.md)

## Global Constraints

- KHÔNG có Alembic — thêm cột PHẢI qua `backend/app/db_migrations.py` (idempotent, tự kiểm bảng/cột
  đã có chưa) + cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test bắt buộc mọi cột phải có mặt ở đó).
- Migration tiếp theo là **`0245`** (cuối cùng hiện tại: `0244_phi_giao_hang_san_pham`).
- Nguồn NHU CẦU DUY NHẤT là `KeHoachVatTuService.can_doi()` — không viết đường tính nhu cầu thứ hai.
- `can_doi()` giữ nguyên GIỮ-CHỖ-AGNOSTIC (không đọc bảng `vat_tu_giu_cho`) — mọi số giữ-chỗ-biết
  được TÍNH THÊM ở lớp `GiuChoService`, không sửa `can_doi()`.
- Sửa route/schema backend → phải RESTART uvicorn (không hot-reload đáng tin ở đây).
- Luồng có UI → BẮT BUỘC thao tác lại bằng chuột/bàn phím thật trên dev-browser trước khi báo xong,
  không dùng API/curl thay bước nào (Task cuối của plan này dành riêng cho việc đó).
- Không tự chạy `./init.ps1` toàn bộ — verify từng task bằng `pytest <file>::<test> -v` nhắm đúng
  file/test vừa sửa; chỉ chạy bộ đầy đủ khi được yêu cầu.
- Tiếng Việt trong code/docstring/message lỗi, giữ đúng giọng văn đã có trong từng file (lý do trước,
  kết luận sau — xem các đoạn code hiện tại làm mẫu).

---

### Task 1: Migration 0245 — cột `purchase_request_line_id` trên `vat_tu_giu_cho`

**Files:**
- Modify: `backend/app/models/vat_tu_giu_cho.py:83-89`
- Modify: `backend/app/db_migrations.py` (thêm hàm mới sau dòng 10866, cuối file)
- Modify: `docs/DB_SCHEMA.md:4003-4011` (bảng `vat_tu_giu_cho`)
- Test: `backend/tests/test_giu_cho_vat_tu.py` (thêm test migration ở cuối file)

**Interfaces:**
- Produces: cột `VatTuGiuCho.purchase_request_line_id: int | None` — soft FK
  `purchase_request_lines.id` (`ondelete="SET NULL"`), CHỈ có ý nghĩa khi `nguon == NGUON_DANG_VE`.
  Task 2 sẽ là nơi đầu tiên GHI giá trị thật vào cột này.

- [ ] **Step 1: Viết test migration idempotent (thất bại trước)**

Thêm vào cuối `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== MIGRATION 0245 ==================


def test_migration_them_cot_purchase_request_line_id(db):
    """Cột mới phải tồn tại, nullable, và chạy lại migration không vỡ (idempotent)."""
    from sqlalchemy import inspect

    from app.db_migrations import run_migrations

    insp = inspect(db.get_bind())
    cols = {c["name"] for c in insp.get_columns("vat_tu_giu_cho")}
    assert "purchase_request_line_id" in cols

    # Chạy lại lần hai — no-op, không raise.
    run_migrations(db)
```

- [ ] **Step 2: Chạy test — phải FAIL** (cột chưa tồn tại)

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_migration_them_cot_purchase_request_line_id -v`
Expected: FAIL — `AssertionError` (cột không có trong `cols`).

- [ ] **Step 3: Thêm cột vào model**

Sửa `backend/app/models/vat_tu_giu_cho.py`, ngay sau `bai_ghep_id` (dòng 86-88):

```python
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
```

- [ ] **Step 4: Thêm migration 0245**

Thêm vào cuối `backend/app/db_migrations.py` (sau dòng 10866, `MIGRATIONS.append(("0244_...`):

```python


def _migrate_giu_cho_purchase_request_line_id(db: Session) -> None:
    """`vat_tu_giu_cho.purchase_request_line_id` — dòng PHIẾU MUA làm phát sinh phần giữ hứa
    (`nguon='dang_ve'`), để đối soát khi PMH đổi (dời ngày, giảm/huỷ SL, đóng đơn) biết CHÍNH XÁC
    dòng nào bị ảnh hưởng thay vì đoán theo mặt hàng (docs/spec-ke-hoach-vat-tu.md §3.1, §3.5).

    Dòng `dang_ve` CŨ (trước migration) không tra ngược được về đúng dòng phiếu nào — XOÁ SẠCH rồi
    để `nhat_them()` tự dựng lại theo luật mới ở lần chạy kế tiếp. Dữ liệu demo (`SEED_DEMO`),
    không phải số liệu khách hàng thật (docs/spec-ke-hoach-vat-tu.md, "Quyết định đã chốt
    30/08/2026"). Dòng `nguon='kho'` giữ nguyên — không liên quan tới cột này.

    No-op khi bảng chưa có / cột đã có.
    """
    insp = inspect(db.get_bind())
    if "vat_tu_giu_cho" not in insp.get_table_names():
        return
    if "purchase_request_line_id" in _existing_columns(insp, "vat_tu_giu_cho"):
        return
    db.execute(text(
        "ALTER TABLE vat_tu_giu_cho ADD COLUMN purchase_request_line_id INTEGER"
    ))
    db.execute(text("DELETE FROM vat_tu_giu_cho WHERE nguon = 'dang_ve'"))
    db.commit()
    _dung_lai_giu_cho_dang_ve(db)


def _dung_lai_giu_cho_dang_ve(db: Session) -> None:
    """Sau khi xoá sạch dòng `dang_ve` cũ (không tra được `purchase_request_line_id`), dựng lại
    đúng theo cột mới cho MỌI chủ thể đang bật giữ chỗ — đúng "Quyết định đã chốt 30/08/2026"
    (docs/spec-ke-hoach-vat-tu.md §3.1: "...rồi gọi lại GiuChoService.nhat_them() cho mọi chủ thể
    đang giu_cho_bat=true để dựng lại đúng theo cột mới"). Không gọi thì chủ thể đó "mất" phần
    hứa cho tới lần Nhập kho/Bật-Tắt kế tiếp mới được bù lại — im lặng suốt khoảng đó.

    Import cục bộ vào tầng service — LỆ RIÊNG của hàm này, không phải quy ước chung của
    `db_migrations.py` (mọi migration khác trong file chỉ động DDL/backfill SQL thuần). Đây là
    backfill NGHIỆP VỤ (nhặt lại đúng tồn tự do + lô đang về theo luật `nhat_them()`), không phải
    một câu UPDATE cột đơn thuần, nên buộc phải dựng lại đúng chuỗi service như
    `routers/ke_hoach_vat_tu.py::get_service()` — không tính tay lại một đường khác sẽ có lúc lệch.

    An toàn gọi ở thời điểm boot: migration chạy TUẦN TỰ, 0245 là migration hiện tại CUỐI CÙNG,
    nên mọi bảng/cột mà `KeHoachVatTuService`/`GiuChoService` cần đọc (routing, stock_lots,
    purchase_request_lines...) đã ở trạng thái đã-migrate-đủ trước khi hàm này chạy.
    """
    from .models.bai_ghep import BaiGhep
    from .models.lsx import Lsx
    from .repositories.bai_ghep_repo import BaiGhepRepository
    from .repositories.don_vi_do_repo import DonViDoRepository
    from .repositories.lsx_repo import LsxRepository
    from .repositories.purchase_repo import PurchaseRequestRepository
    from .repositories.stock_lot_repo import StockLotRepository
    from .repositories.stock_request_repo import StockRequestRepository
    from .repositories.supplier_repo import SupplierRepository
    from .repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from .services.giu_cho_service import GiuChoService
    from .services.ke_hoach_vat_tu_service import KeHoachVatTuService
    from .services.vat_lieu_kho_service import VatLieuKhoService

    hang = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    kh = KeHoachVatTuService(
        db, lsx_repo=LsxRepository(db), bai_ghep_repo=BaiGhepRepository(db), hang=hang,
        lots=StockLotRepository(db), requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db), suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )
    giu = GiuChoService(db, kh)
    for lsx_id in [r[0] for r in db.query(Lsx.id).filter(Lsx.giu_cho_bat.is_(True)).all()]:
        giu.nhat_them(chi_chu_the=(lsx_id, None))
    for bai_id in [r[0] for r in db.query(BaiGhep.id).filter(BaiGhep.giu_cho_bat.is_(True)).all()]:
        giu.nhat_them(chi_chu_the=(None, bai_id))


MIGRATIONS.append(("0245_giu_cho_purchase_request_line_id",
                    _migrate_giu_cho_purchase_request_line_id))
```

- [ ] **Step 5: Chạy test — phải PASS**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_migration_them_cot_purchase_request_line_id -v`
Expected: PASS

- [ ] **Step 5b: Viết + chạy test cho phần dựng lại (backfill nghiệp vụ)**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`, ngay dưới test Step 1:

```python
def test_migration_backfill_dung_lai_nhat_them_cho_chu_the_dang_bat(db, kh, customer):
    """Chủ thể đã BẬT giữ chỗ từ trước (cờ `giu_cho_bat=true`), dòng `dang_ve` của nó vừa bị
    migration xoá sạch — hàm backfill `_dung_lai_giu_cho_dang_ve` phải tự gọi lại `nhat_them()`
    cho chủ thể đó, không để nó "trắng tay" tới lần Nhập kho/Bật-Tắt kế tiếp."""
    from app.db_migrations import _dung_lai_giu_cho_dang_ve
    from app.services.giu_cho_service import GiuChoService

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)

    # Mô phỏng "đã bật từ trước migration": bật cờ THẲNG qua ORM, KHÔNG gọi svc.bat() (gọi bat()
    # sẽ tự nhat_them() ngay, làm mất ý nghĩa của test — ta cần trạng thái "cờ bật nhưng CHƯA có
    # dòng giữ", đúng như sau khi migration xoá sạch dang_ve).
    a.giu_cho_bat = True
    db.commit()

    svc = GiuChoService(db, kh)
    assert not svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None), "chưa gọi nhat_them nên phải trống"

    _dung_lai_giu_cho_dang_ve(db)

    rows = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert rows, "backfill phải tự dựng lại giữ chỗ cho chủ thể đang bật"
```

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_migration_backfill_dung_lai_nhat_them_cho_chu_the_dang_bat -v`
Expected: PASS (hàm đã viết ở Step 4 cùng migration).

- [ ] **Step 6: Cập nhật `docs/DB_SCHEMA.md`**

Trong bảng cột của `vat_tu_giu_cho`, sửa dòng `bai_ghep_id` (giữ nguyên) và CHÈN một dòng mới ngay
sau nó, trước dòng `so_luong` (khớp đúng `docs/DB_SCHEMA.md:4004-4005`):

```markdown
| `bai_ghep_id` | `Integer` | **FK→bai_ghep.id** (CASCADE), IX | yes | — | Chủ thể giữ chỗ khi lệnh đã GHÉP — bài đại diện, lệnh thành viên không giữ riêng. |
| `purchase_request_line_id` | `Integer` | **FK→purchase_request_lines.id** (SET NULL), IX | yes | — | [MỚI 30/08/2026] Dòng phiếu mua làm phát sinh phần giữ — CHỈ có ý nghĩa khi `nguon='dang_ve'`. Để đối soát đúng dòng khi PMH đổi thay vì đoán theo mặt hàng. |
| `so_luong` | `Numeric(14,2)` | — | no | — | Theo **ĐƠN VỊ GỐC** của mặt hàng (`don_vi_gia`) — cùng thang `stock_lots.sl_con_lai`, khỏi quy đổi lần nữa khi trừ tồn tự do. |
```

Và sửa dòng "Tất cả cột" (`docs/DB_SCHEMA.md:4011`):

```markdown
**Tất cả cột:** `id`, `hang_loai`, `hang_id`, `lsx_id`, `bai_ghep_id`, `purchase_request_line_id`, `so_luong`, `nguon`, `ngay_ve`, `created_at`, `updated_at`.
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/vat_tu_giu_cho.py backend/app/db_migrations.py docs/DB_SCHEMA.md backend/tests/test_giu_cho_vat_tu.py
git commit -m "Giữ chỗ: thêm cột purchase_request_line_id (mg 0245) để đối soát đúng dòng phiếu mua"
```

---

### Task 2: `_hang_dang_ve()` mang `line_id`; `nhat_them()` gán `purchase_request_line_id`

**Files:**
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py:501-551` (`_hang_dang_ve`)
- Modify: `backend/app/services/giu_cho_service.py:441` (`nhat_them`), `:555-601` (`_lo_dang_ve`, `_dong`)
- Test: `backend/tests/test_giu_cho_vat_tu.py`, `backend/tests/test_ke_hoach_vat_tu.py`

**Interfaces:**
- Consumes: `PurchaseRequestLine.id` (đã có).
- Produces: `KeHoachVatTuService._hang_dang_ve() -> dict[tuple, list[tuple[date, float, str | None, int]]]`
  (4-tuple, thêm `line_id` ở cuối). `GiuChoService._lo_dang_ve() -> dict[Hang, list[tuple[date, float, int]]]`
  (3-tuple: ngày, số CÒN TRỐNG, `line_id`). `GiuChoService._dong(..., purchase_request_line_id=None)`
  — tham số MỚI, optional, mặc định `None` (nhánh `NGUON_KHO` không truyền).

- [ ] **Step 1: Viết test thất bại trước — dòng `dang_ve` mới đẻ ra phải mang đúng `purchase_request_line_id`**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`, dưới nhóm "HÀNG ĐANG VỀ" (tạo nhóm mới nếu chưa
có; đặt gần các test dùng `_phieu_mua`):

```python
# ================== HÀNG ĐANG VỀ MANG ĐÚNG DÒNG PHIẾU ==================


def test_nhat_them_gan_dung_purchase_request_line_id(db, svc, kh, customer):
    """Dòng giữ `dang_ve` mới đẻ ra phải bám ĐÚNG dòng phiếu mua đã sinh ra lô đang về đó — không
    thì đối soát sau này (Task 3) không biết nhả theo dòng nào."""
    from app.models.vat_tu_giu_cho import NGUON_DANG_VE
    from app.models.purchase import PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()

    svc.bat(lsx_id=a.id)

    dong = db.query(db.query(type(a)).session.get_bind() and None) if False else None  # placeholder xoá
    rows = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    ve = [r for r in rows if r.nguon == NGUON_DANG_VE]
    assert ve, "phải giữ được từ lô đang về"
    assert all(r.purchase_request_line_id == line.id for r in ve)
```

Xoá ngay dòng `dong = ...` (rác do soạn nhanh) trước khi lưu — bản THẬT của test không có dòng đó,
chỉ giữ:

```python
def test_nhat_them_gan_dung_purchase_request_line_id(db, svc, kh, customer):
    """Dòng giữ `dang_ve` mới đẻ ra phải bám ĐÚNG dòng phiếu mua đã sinh ra lô đang về đó — không
    thì đối soát sau này (Task 3) không biết nhả theo dòng nào."""
    from app.models.purchase import PurchaseRequestLine
    from app.models.vat_tu_giu_cho import NGUON_DANG_VE

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()

    svc.bat(lsx_id=a.id)

    rows = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    ve = [r for r in rows if r.nguon == NGUON_DANG_VE]
    assert ve, "phải giữ được từ lô đang về"
    assert all(r.purchase_request_line_id == line.id for r in ve)
```

- [ ] **Step 2: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_nhat_them_gan_dung_purchase_request_line_id -v`
Expected: FAIL — `AssertionError` (mọi `r.purchase_request_line_id` đang là `None`).

- [ ] **Step 3: `_hang_dang_ve()` mang thêm `line_id`**

Sửa `backend/app/services/ke_hoach_vat_tu_service.py:501-551`. Đổi type hint (dòng 501) và câu
`ra.setdefault(...).append(...)` (dòng 547-548):

```python
    def _hang_dang_ve(self) -> dict[tuple, list[tuple[date, float, str | None, int]]]:
        """`{hang: [(ngày về, số còn về, mã phiếu mua, id dòng phiếu)]}` đã sắp theo ngày — đơn vị GỐC.
```

(giữ nguyên phần docstring còn lại, chỉ đổi dòng đầu và type hint). Rồi sửa thân vòng lặp:

```python
                kq = self._ve_goc(hang, ln.unit, con_ve)
                if "sl" in kq:
                    ra.setdefault(hang, []).append(
                        (ngay_ve, kq["sl"], getattr(phieu, "code", None), int(ln.id)))
```

- [ ] **Step 4: `_lo_dang_ve()` giữ + trả `line_id`**

Sửa `backend/app/services/giu_cho_service.py:555-581`:

```python
    def _lo_dang_ve(self, bang: dict, hangs: list[Hang]) -> dict[Hang, list[tuple[date, float, int]]]:
        """Lô đang về CÒN TRỐNG chỗ = số đang về − phần đã có chủ (`nguon='dang_ve'`).

        Trừ phần đã giữ hứa, không thì hai lệnh cùng bám một lô và cả hai đều tưởng mình có hàng.
        Đơn giản hoá có chủ ý: trừ theo TỔNG rồi cắt dần từ lô sớm nhất, không truy từng lô ai giữ
        — bảng giữ chỗ cố ý không neo lô nào (xem docstring model).

        Mang theo `line_id` của CHÍNH dòng phiếu còn lại đó — `nhat_them()` cần nó để ghi đúng
        `purchase_request_line_id` lên dòng giữ chỗ mới, cho đối soát sau này bám đúng dòng.
        """
        ra: dict[Hang, list[tuple[date, float, int]]] = {}
        da_hua = {h: 0.0 for h in hangs}
        for r in self.db.query(VatTuGiuCho).filter(VatTuGiuCho.nguon == NGUON_DANG_VE).all():
            h = (r.hang_loai, r.hang_id)
            if h in da_hua:
                da_hua[h] += _f(r.so_luong)
        for hang, ds in self.kh._hang_dang_ve().items():
            if hang not in set(hangs):
                continue
            con_hua = da_hua.get(hang, 0.0)
            con_lai: list[tuple[date, float, int]] = []
            for ngay, sl, _ma, line_id in ds:
                bot = min(con_hua, sl)
                con_hua -= bot
                if sl - bot > 0:
                    con_lai.append((ngay, sl - bot, line_id))
            ra[hang] = con_lai
        return ra
```

- [ ] **Step 5: `nhat_them()` truyền `line_id` xuống `_dong()`; `_dong()` nhận tham số mới**

Sửa `backend/app/services/giu_cho_service.py:478-492` (vòng `while` trong `nhat_them`):

```python
                # 2) Còn thiếu thì bám lô ĐANG VỀ, sớm trước.
                i = 0
                while con > 0 and i < len(ve.get(hang, [])):
                    ngay, sl, line_id = ve[hang][i]
                    lay = round(min(con, sl), 2)
                    if lay > 0:
                        ve[hang][i] = (ngay, sl - lay, line_id)
                        con -= lay
                        moi.append(self._dong(chu, hang, lay, NGUON_DANG_VE, ngay, line_id))
                    # Lô còn ≤0.004 coi như cạn (đúng biên Numeric(14,2), khớp `tieu_thu`) → sang lô
                    # kế; không thì đã lấp đủ `con`, dừng.
                    if ve[hang][i][1] <= 0.004:
                        i += 1
                    else:
                        break
```

Sửa `_dong()` (dòng 596-601):

```python
    @staticmethod
    def _dong(chu: tuple, hang: Hang, sl: float, nguon: str, ngay: date | None,
              purchase_request_line_id: int | None = None) -> VatTuGiuCho:
        return VatTuGiuCho(
            hang_loai=hang[0], hang_id=hang[1], lsx_id=chu[0], bai_ghep_id=chu[1],
            so_luong=round(sl, 2), nguon=nguon, ngay_ve=ngay,
            purchase_request_line_id=purchase_request_line_id,
        )
```

(Nhánh `NGUON_KHO` ở dòng 477 — `moi.append(self._dong(chu, hang, lay, NGUON_KHO, None))` — giữ
nguyên, không truyền tham số mới, mặc định `None` đúng ý nghĩa "kho không gắn dòng phiếu nào".)

- [ ] **Step 6: Chạy test Task 2 — phải PASS, rồi chạy cả file để chắc không phá test cũ**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -v`
Expected: PASS toàn bộ.

Run: `cd backend && python -m pytest tests/test_ke_hoach_vat_tu.py -v`
Expected: PASS toàn bộ (đổi type hint/4-tuple không đổi hành vi các test cũ vì chúng star-unpack
hoặc chỉ đọc `[0]`/`[1]`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ke_hoach_vat_tu_service.py backend/app/services/giu_cho_service.py backend/tests/test_giu_cho_vat_tu.py
git commit -m "Giữ chỗ: gắn purchase_request_line_id lên dòng giữ hứa mới, xuyên suốt _hang_dang_ve → nhat_them"
```

---

### Task 3: `GiuChoService.doi_soat_dang_ve()` / `doi_soat_dang_ve_don()`

**Files:**
- Modify: `backend/app/services/giu_cho_service.py` (thêm 2 method mới, khu vực "GHI")
- Modify: `docs/spec-ke-hoach-vat-tu.md` (sửa câu sai ở §3.5)
- Test: `backend/tests/test_giu_cho_vat_tu.py`

**Interfaces:**
- Consumes: `KeHoachVatTuService._hang_dang_ve()` (Task 2, 4-tuple), `VatTuGiuCho.purchase_request_line_id`
  (Task 1).
- Produces: `GiuChoService.doi_soat_dang_ve(purchase_request_line_id: int) -> None`,
  `GiuChoService.doi_soat_dang_ve_don(purchase_request_id: int) -> None`. Task 4 gọi
  `doi_soat_dang_ve_don`.

**Phạm vi §3.5 "lùi ngày giao dự kiến" — đã rà, KHÔNG có endpoint để gọi vào (không phải bỏ sót):**
spec §3.5 đòi khi lùi `expected_receipt_date` trên PMH đã duyệt phải "cập nhật ngày chặn lịch +
cảnh báo realtime". Đã grep toàn bộ `purchase_service.py` tìm hàm sửa `expected_receipt_date` sau
khi đơn đã duyệt — KHÔNG có: `update_request()` chỉ cho sửa khi `row.status in (PR_DRAFT,
PR_REJECTED)`, không bao giờ trùng lúc với khi PMH đã có dòng `dang_ve` đang giữ (`dong_dang_ve()`
đòi trạng thái đã duyệt/mua/giao một phần trở lên). Tức hiện tại KHÔNG CÓ đường để người dùng thật
sự lùi ngày trên một PMH đang giữ chỗ — không có hook để gọi `doi_soat_dang_ve` vào. `doi_soat_dang_ve`
vẫn ĐÃ đúng theo hướng tới (đọc lại `ngay_ve` sống từ `_hang_dang_ve()` mỗi lần chạy — Step 4, biến
`ngay_ve`), nên NẾU sau này có người thêm endpoint sửa ngày, chỉ cần gọi `doi_soat_dang_ve_don()`
là đủ, không cần sửa gì thêm ở đây. KHÔNG thêm endpoint sửa ngày mới trong plan này — ngoài phạm
vi "siết logic trên nền đã có", spec không yêu cầu xây UI/API mới (§4: "Không thêm màn hay luồng
mua mới").

- [ ] **Step 1: Sửa câu sai trong spec (không phải code, làm trước để khỏi quên)**

Trong `docs/spec-ke-hoach-vat-tu.md`, tìm câu ở §3.5 nói "Ghi nhận đợt giao nhưng Kho chưa ghi sổ...
không đổi gì ở `_hang_dang_ve()`" — câu này SAI: `da_giao_theo_dong()` (`purchase_service.py:239-254`)
đọc `PurchaseDeliveryLine.quantity` của MỌI đợt giao đã ghi (kể cả khi Kho CHƯA lập phiếu nhập), nên
ghi một đợt giao làm `con_ve` giảm NGAY LẬP TỨC, trước khi Kho ghi sổ. Sửa câu đó thành: "Ghi nhận
đợt giao là ghi nhận HÀNG ĐÃ VỀ TỪ NCC (dù Kho chưa lập phiếu nhập) — `da_giao_theo_dong()` cộng nó
vào 'đã giao' ngay, nên `con_ve` giảm ngay khi đợt giao được ghi, không đợi Kho ghi sổ."

- [ ] **Step 2: Viết test thất bại trước — giảm số lượng dòng PMH thì nhả THEO MỚI NHẤT trước**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== ĐỐI SOÁT KHI PMH ĐỔI ==================


def _dot_giao(db, phieu, line, *, so_luong) -> None:
    """Ghi MỘT đợt giao cho dòng phiếu — đủ để `da_giao_theo_dong()` cộng vào 'đã giao', khớp
    hành vi `PurchaseService.ghi_dot_giao` mà không phải dựng toàn bộ service."""
    from app.models.purchase import PurchaseDelivery, PurchaseDeliveryLine

    dot = PurchaseDelivery(purchase_request_id=phieu.id, seq_no=1, delivery_date=HOM_NAY)
    db.add(dot)
    db.flush()
    db.add(PurchaseDeliveryLine(delivery_id=dot.id, purchase_request_line_id=line.id,
                                quantity=so_luong))
    db.commit()


def test_doi_soat_nha_moi_nhat_truoc_khi_con_ve_co_lai(db, svc, kh, customer):
    """Bảo vệ cam kết CŨ: khi phần hứa co lại, dòng giữ MỚI TẠO bị nhả trước, dòng CŨ giữ nguyên."""
    from app.models.purchase import PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1000)  # cần nhiều, ăn hết lô
    _phieu_mua(db, hang=_giay_hang(g), so_luong=200, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()

    svc.bat(lsx_id=a.id)
    truoc = sum(_f(r.so_luong) for r in svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None))
    assert truoc > 0, "phải giữ được từ lô đang về"

    # NCC chỉ giao 50/200 — con_ve giảm còn 150.
    _dot_giao(db, phieu, line, so_luong=50)

    svc.doi_soat_dang_ve(line.id)

    sau = sum(_f(r.so_luong) for r in svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None))
    assert sau == pytest.approx(min(truoc, 150), abs=0.01), (
        f"phải nhả bớt xuống còn tối đa 150 (con_ve mới), thực tế còn {sau}"
    )
```

(Import `PurchaseRequest`, `_f` đã có sẵn ở đầu file test hoặc trong `giu_cho_service`; nếu `_f`
chưa import trong test file thì dùng `float(...)` trực tiếp thay vì `_f(...)`.)

- [ ] **Step 3: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_doi_soat_nha_moi_nhat_truoc_khi_con_ve_co_lai -v`
Expected: FAIL — `AttributeError: 'GiuChoService' object has no attribute 'doi_soat_dang_ve'`.

- [ ] **Step 4: Viết `doi_soat_dang_ve` + `doi_soat_dang_ve_don`**

Thêm vào `backend/app/services/giu_cho_service.py`, trong khu vực `# ================== GHI ==================`,
ngay sau `tat()` (sau dòng 439, trước `nhat_them`):

```python
    def doi_soat_dang_ve(self, purchase_request_line_id: int) -> None:
        """PMH đổi (đợt giao mới/sửa/xoá, huỷ đơn, đóng đơn, dời ngày) ⇒ đối lại phần giữ HỨA
        (`nguon='dang_ve'`) đã bám DÒNG PHIẾU này.

        CHỈ NHẢ, không bao giờ tự thêm: phần hứa GIÃN ra (đơn mở lại, giao ít hơn ban đầu dự
        kiến...) là việc của `nhat_them()` ở lần hàng-về/bật-giữ kế tiếp, không phải việc của hàm
        đối soát này. Nhả THEO MỚI NHẤT trước (`created_at` giảm dần) — bảo vệ cam kết CŨ, đúng
        mặc định đã khoá "cam kết cũ được bảo vệ; chỗ mới hơn bị nhả trước".

        Đọc lại `KeHoachVatTuService._hang_dang_ve()` (nguồn DUY NHẤT của "còn về bao nhiêu", đã
        quy đổi đơn vị gốc + trừ đúng luật `da_giao_theo_dong`) thay vì tính lại — tái dùng, không
        đẻ đường tính thứ hai sẽ có lúc lệch.
        """
        held = (
            self.db.query(VatTuGiuCho)
            .filter(VatTuGiuCho.purchase_request_line_id == purchase_request_line_id,
                    VatTuGiuCho.nguon == NGUON_DANG_VE)
            .order_by(VatTuGiuCho.created_at.desc())
            .all()
        )
        if not held:
            return
        hang = (held[0].hang_loai, held[0].hang_id)
        con_ve, ngay_ve = 0.0, None
        for ngay, sl, _ma, line_id in self.kh._hang_dang_ve().get(hang, []):
            if line_id == purchase_request_line_id:
                con_ve, ngay_ve = sl, ngay
                break
        da_giu = sum(_f(r.so_luong) for r in held)
        thua = round(da_giu - con_ve, 4)
        con_lai = held
        if thua > 0:
            con_lai = []
            for r in held:
                if thua > 0:
                    bot = min(thua, _f(r.so_luong))
                    thua = round(thua - bot, 4)
                    if _f(r.so_luong) - bot <= 0.004:
                        self.db.delete(r)
                        continue
                    r.so_luong = round(_f(r.so_luong) - bot, 2)
                con_lai.append(r)
        if ngay_ve is not None:
            for r in con_lai:
                r.ngay_ve = ngay_ve
        self.db.commit()

    def doi_soat_dang_ve_don(self, purchase_request_id: int) -> None:
        """Đối lại MỌI dòng của MỘT PMH — gọi khi sự kiện xảy ra ở CẤP ĐƠN (huỷ, đóng, mở lại, đợt
        giao đổi) mà không rõ trước dòng nào bị ảnh hưởng, nên đối hết cho chắc."""
        from ..models.purchase import PurchaseRequestLine

        for ln in (self.db.query(PurchaseRequestLine)
                   .filter(PurchaseRequestLine.purchase_request_id == purchase_request_id)
                   .all()):
            if ln.hang_loai and ln.hang_id:
                self.doi_soat_dang_ve(ln.id)
```

- [ ] **Step 5: Chạy test — phải PASS**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_doi_soat_nha_moi_nhat_truoc_khi_con_ve_co_lai -v`
Expected: PASS

- [ ] **Step 6: Thêm test nhánh huỷ hẳn (con_ve về 0 ⇒ nhả sạch)**

```python
def test_doi_soat_nha_sach_khi_dong_khong_con_trong_hang_dang_ve(db, svc, kh, customer):
    """Phiếu rời khỏi trạng thái 'đang về' (đóng/huỷ) ⇒ `_hang_dang_ve()` không còn dòng nào của
    nó ⇒ đối soát phải nhả SẠCH phần đã giữ theo dòng đó."""
    from app.models.purchase import PR_CANCELLED, PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()
    svc.bat(lsx_id=a.id)
    assert svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None), "phải giữ được trước đã"

    phieu.status = PR_CANCELLED   # mô phỏng PurchaseService.cancel() đã đổi trạng thái
    db.commit()

    svc.doi_soat_dang_ve(line.id)

    con = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert not any(r.purchase_request_line_id == line.id for r in con)
```

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -k doi_soat -v`
Expected: PASS cả hai test.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/giu_cho_service.py docs/spec-ke-hoach-vat-tu.md backend/tests/test_giu_cho_vat_tu.py
git commit -m "Giữ chỗ: đối soát dang_ve theo dòng phiếu mua khi PMH đổi (doi_soat_dang_ve)"
```

---

### Task 4: Hook đối soát vào `PurchaseService` + `deps.py`

**Files:**
- Modify: `backend/app/services/purchase_service.py:563-586,2758-2809,2930-2963`
- Modify: `backend/app/deps.py:688-713`
- Test: `backend/tests/test_purchases_api.py` (file test PMH thật — `test_purchase_delivery.py`
  KHÔNG tồn tại, đừng tìm)

**Interfaces:**
- Consumes: `GiuChoService.doi_soat_dang_ve_don(purchase_request_id: int) -> None` (Task 3).
- Produces: `PurchaseService(..., giu_cho=None)` — tham số MỚI, optional. `deps.get_purchase_service`
  giờ LUÔN truyền một `GiuChoService` thật (không còn `None` ở đường chạy thật qua FastAPI).

- [ ] **Step 1: Xác định file test PMH đang có để cắm test vào đúng chỗ**

Run: `cd backend && python -m pytest --collect-only -q tests/ 2>&1 | grep -i "delivery\|dot_giao\|purchase_request" | head -30`

(Lệnh trên chỉ để ĐỌC danh sách test hiện có — không sửa gì. Ghi lại tên file có sẵn fixture dựng
`PurchaseService` + `PurchaseRequest` + đợt giao, dùng file đó cho Step 2. Nếu không file nào khớp,
dùng `backend/tests/test_giu_cho_vat_tu.py` và tự dựng `PurchaseService` bằng các repo đã import sẵn
ở đầu file đó.)

- [ ] **Step 2: Viết test thất bại trước — huỷ PMH nhả sạch giữ chỗ**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py` (tái dùng fixture `db`, `kh`, `customer` đã có):

```python
# ================== HOOK PurchaseService ⇄ GIỮ CHỖ ==================


def _thu_mua(db, kh) -> "PurchaseService":
    from app.repositories.department_purchase_repo import DepartmentPurchaseRequestRepository
    from app.repositories.purchase_repo import PurchaseStatusHistoryRepository
    from app.repositories.user_repo import UserRepository
    from app.repositories.department_repo import DepartmentRepository
    from app.repositories.audit_repo import AuditLogRepository
    from app.services.authorization_service import AuthorizationService
    from app.services.purchase_service import PurchaseService

    return PurchaseService(
        suppliers=SupplierRepository(db),
        department_requests=DepartmentPurchaseRequestRepository(db),
        requests=PurchaseRequestRepository(db),
        users=UserRepository(db),
        departments=DepartmentRepository(db),
        audit=AuditLogRepository(db),
        authz=AuthorizationService(db),
        lich_su=PurchaseStatusHistoryRepository(db),
        giu_cho=GiuChoService(db, kh),
    )


def test_huy_pmh_nha_sach_giu_cho_dang_ve(db, svc, kh, customer):
    """Huỷ PMH → PMH rời khỏi trạng thái 'đang về' → GiuChoService.doi_soat_dang_ve_don phải chạy
    và nhả sạch phần giữ hứa theo phiếu đó, KHÔNG cần ai gọi tay `nhat_them`/`doi_soat_dang_ve`."""
    from app.services.purchase_service import PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    svc.bat(lsx_id=a.id)
    assert svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None), "phải giữ được trước đã"

    thu_mua = _thu_mua(db, kh)
    admin = type("A", (), {"id": 1})()
    thu_mua.cancel(phieu.id, reason="Không mua nữa", actor=admin)

    con = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert not any(_f(r.so_luong) > 0 for r in [rr for rr in con
                                                if getattr(rr, "purchase_request_line_id", None)]), (
        "huỷ PMH phải nhả hết phần giữ hứa bám phiếu đó"
    )
```

Nếu `thu_mua.cancel(...)` đòi quyền (`authz.can`) mà `AuthorizationService(db)` không có sẵn dữ liệu
quyền cho `admin` giả — sửa test dùng actor thật lấy từ `seed_all` (đã chạy trong fixture `db`):
thay `admin = type("A", (), {"id": 1})()` bằng
`admin = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(username="admin").first()`.
Nếu vẫn vướng quyền, đơn giản hoá: gọi thẳng `svc.giu_cho... ` không cần — MỤC TIÊU test là hành vi
của `cancel()`, nên nếu quyền chặn thì phải dùng đúng actor có quyền `ke_toan:approve` HOẶC actor là
`created_by_user_id` của phiếu với `row.status == PR_DRAFT`. Vì `_phieu_mua()` helper tạo phiếu ở
`PR_PURCHASED` (không phải DRAFT), actor PHẢI có quyền `ke_toan:approve` — dùng user admin đã seed.

- [ ] **Step 3: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_huy_pmh_nha_sach_giu_cho_dang_ve -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'giu_cho'`.

- [ ] **Step 4: Thêm `giu_cho=None` vào `PurchaseService.__init__`**

Sửa `backend/app/services/purchase_service.py:563-586`:

```python
class PurchaseService:
    def __init__(
        self,
        suppliers: SupplierRepository,
        department_requests: DepartmentPurchaseRequestRepository,
        requests: PurchaseRequestRepository,
        users: UserRepository,
        departments: DepartmentRepository,
        audit: AuditLogRepository,
        authz: AuthorizationService,
        lich_su: PurchaseStatusHistoryRepository,
        hang=None,
        giu_cho=None,
    ) -> None:
        self.lich_su = lich_su
        self.suppliers = suppliers
        self.department_requests = department_requests
        self.requests = requests
        self.users = users
        self.departments = departments
        self.audit = audit
        self.authz = authz
        # `VatLieuKhoService` — tra danh mục gốc + quy đổi đơn vị, để bảng giá NCC gắn được về
        # mặt hàng và so được giá. None → bỏ qua phần gắn (giữ tương thích với test cũ).
        self.hang = hang
        # `GiuChoService` — TUỲ CHỌN (30/08/2026), cùng nếp với `hang`. Vắng thì PMH chạy y như
        # trước (test cũ không phải kéo theo cả bảng cân đối); có mặt thì đợt giao đổi / huỷ đơn /
        # đóng đơn / mở lại đơn tự đối lại phần giữ HỨA đã bám đúng dòng phiếu — xem
        # `_doi_soat_giu_cho`.
        self.giu_cho = giu_cho
```

- [ ] **Step 5: Thêm `_doi_soat_giu_cho` + gọi từ `_sau_khi_doi_dot`, `dong_don`, `cancel`**

Sửa `_sau_khi_doi_dot` (`backend/app/services/purchase_service.py:2758-2763`):

```python
    def _sau_khi_doi_dot(self, row: PurchaseRequest) -> None:
        """Suy lại trạng thái phiếu VÀ trạng thái YCMH nguồn sau khi tập đợt giao đổi."""
        self._chan_tong_dot_vuot_don(row)
        self._suy_trang_thai_nhan_hang(row)
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request)
        self._doi_soat_giu_cho(row)

    def _doi_soat_giu_cho(self, row: PurchaseRequest) -> None:
        """Đợt giao vừa đổi (ghi/sửa/xoá), hoặc đơn vừa đóng/huỷ/mở lại ⇒ giữ chỗ đối lại phần
        hứa đã bám PHIẾU này. TUỲ CHỌN — vắng `giu_cho` thì bỏ qua, PMH chạy y như trước
        30/08/2026."""
        if self.giu_cho is not None:
            self.giu_cho.doi_soat_dang_ve_don(row.id)
```

Sửa `dong_don` — thêm 1 dòng ngay sau `saved = self.requests.save(row)` (`backend/app/services/purchase_service.py:2802`):

```python
        saved = self.requests.save(row)
        self._doi_soat_giu_cho(row)
        self.audit.create(
            actor_user_id=actor.id,
            action="close_purchase_request",
            target=f"purchase_request:{row.id}",
            detail=f"{row.code} — {ly_do}",
        )
        return self._to_request_out(saved)
```

Sửa `cancel` — thêm 1 dòng ngay sau `saved = self.requests.save(row)` (`backend/app/services/purchase_service.py:2961`):

```python
        saved = self.requests.save(row)
        self._doi_soat_giu_cho(row)
        self.audit.create(actor_user_id=actor.id, action="cancel_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)
```

- [ ] **Step 6: Wire `giu_cho` thật vào `deps.get_purchase_service`**

Sửa `backend/app/deps.py:688-713`:

```python
def get_purchase_service(
    suppliers: Annotated[SupplierRepository, Depends(get_supplier_repository)],
    department_requests: Annotated[
        DepartmentPurchaseRequestRepository,
        Depends(get_department_purchase_request_repository),
    ],
    requests: Annotated[PurchaseRequestRepository, Depends(get_purchase_request_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    lich_su: Annotated[
        PurchaseStatusHistoryRepository, Depends(get_purchase_status_history_repository)
    ],
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> PurchaseService:
    # `hang` = danh mục gốc (Giấy + Vật tư khác): bảng giá NCC gắn về mặt hàng và so giá qua đó.
    from .repositories.bai_ghep_repo import BaiGhepRepository
    from .repositories.don_vi_do_repo import DonViDoRepository
    from .repositories.lsx_repo import LsxRepository
    from .repositories.stock_lot_repo import StockLotRepository
    from .repositories.stock_request_repo import StockRequestRepository
    from .repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from .services.giu_cho_service import GiuChoService
    from .services.ke_hoach_vat_tu_service import KeHoachVatTuService
    from .services.vat_lieu_kho_service import VatLieuKhoService

    hang = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    # `GiuChoService` (30/08/2026) — huỷ/đóng đơn/đổi đợt giao phải tự đối lại phần giữ hứa. Dựng
    # đúng cách `routers/ke_hoach_vat_tu.py::get_service()` dựng, để không lệch số với màn Kế
    # hoạch vật tư.
    kh_vt = KeHoachVatTuService(
        db,
        lsx_repo=LsxRepository(db),
        bai_ghep_repo=BaiGhepRepository(db),
        hang=hang,
        lots=StockLotRepository(db),
        requests=StockRequestRepository(db),
        purchases=requests,
        suppliers=suppliers,
        don_vi=DonViDoRepository(db),
    )
    return PurchaseService(
        suppliers, department_requests, requests, users, departments, audit, authz, lich_su,
        hang=hang, giu_cho=GiuChoService(db, kh_vt),
    )
```

- [ ] **Step 7: Chạy test — phải PASS, rồi chạy toàn bộ test thu mua để chắc không phá gì**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_huy_pmh_nha_sach_giu_cho_dang_ve -v`
Expected: PASS

Run: `cd backend && python -m pytest tests/ -k "purchase" -v`
Expected: PASS toàn bộ (tham số `giu_cho=None` mặc định giữ nguyên hành vi ở mọi test cũ không
truyền nó).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/purchase_service.py backend/app/deps.py backend/tests/test_giu_cho_vat_tu.py
git commit -m "Thu mua: gọi GiuChoService.doi_soat_dang_ve_don khi đợt giao đổi / huỷ / đóng đơn"
```

---

### Task 5: `chuyen_dang_ve_sang_kho()` — hàng nhập kho tự chuyển "hứa" → "có thật"

**Files:**
- Modify: `backend/app/services/giu_cho_service.py` (thêm method mới)
- Modify: `backend/app/services/stock_voucher_service.py:339-346` (nhánh NHẬP của `_apply_post`)
- Test: `backend/tests/test_giu_cho_vat_tu.py`

**Interfaces:**
- Produces: `GiuChoService.chuyen_dang_ve_sang_kho(hang: Hang, so_luong: float) -> None`.
- Consumes trong `StockVoucherService`: `self.giu_cho.chuyen_dang_ve_sang_kho(...)` gọi TRƯỚC
  `self.giu_cho.nhat_them()` trong nhánh NHẬP.

- [ ] **Step 1: Viết test thất bại trước — hàng về đúng như hứa thì hết bị khoá theo ngày**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== NHẬP KHO CHUYỂN HỨA → THẬT ==================


def test_chuyen_dang_ve_sang_kho_go_khoa_ngay(db, svc, kh, customer):
    """Hàng đang về (hứa, khoá lịch tới `ngay_ve`) nhập kho xong phải chuyển thành `nguon=kho`
    (không ngày nào khoá nữa) — không thì lệnh vẫn bị chặn lịch dù hàng đã nằm trong kho."""
    from app.models.vat_tu_giu_cho import NGUON_DANG_VE, NGUON_KHO

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    svc.bat(lsx_id=a.id)
    tt_truoc = svc.trang_thai(lsx_id=a.id)
    assert tt_truoc["xep_som_nhat"] is not None, "đang giữ hứa nên phải có ngày khoá lịch"

    svc.chuyen_dang_ve_sang_kho(_giay_hang(g), 100)

    rows = svc.repo.cua_chu_the(lsx_id=a.id, bai_ghep_id=None)
    assert all(r.nguon == NGUON_KHO for r in rows), "phải chuyển hết sang kho"
    assert not any(r.nguon == NGUON_DANG_VE for r in rows)
    tt_sau = svc.trang_thai(lsx_id=a.id)
    assert tt_sau["xep_som_nhat"] is None, "hàng đã có thật thì không còn ngày nào khoá lịch nữa"
```

- [ ] **Step 2: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_chuyen_dang_ve_sang_kho_go_khoa_ngay -v`
Expected: FAIL — `AttributeError: 'GiuChoService' object has no attribute 'chuyen_dang_ve_sang_kho'`.

- [ ] **Step 3: Viết `chuyen_dang_ve_sang_kho`**

Thêm vào `backend/app/services/giu_cho_service.py`, ngay sau `nhat_them()` (sau dòng 494, trước
`# ================== KHO GỌI VÀO ==================`):

```python
    def chuyen_dang_ve_sang_kho(self, hang: Hang, so_luong: float) -> None:
        """Hàng NHẬP KHO xong: phần đang giữ HỨA (`dang_ve`) của CHÍNH mặt hàng đó phải chuyển
        thành giữ THẬT (`kho`) — không thì chủ thể vẫn bị `xep_som_nhat` khoá tới một `ngay_ve`
        đã lỗi thời, dù hàng nó bám vào đang nằm ngay trong kho.

        `nhat_them()` KHÔNG tự làm việc này: nó chỉ ĐẺ THÊM dòng cho phần còn `thieu`, không đụng
        tới dòng CŨ đã đủ — một chủ thể đã giữ đủ từ `dang_ve` thì `nhat_them()` không bao giờ
        chạm lại vào dòng đó.

        Cũ nhất trước (`created_at` tăng dần) — cùng luật "cam kết cũ được bảo vệ" của mọi chỗ nhả
        khác trong file này. Cố ý KHÔNG neo theo `purchase_request_line_id` cụ thể: giữ chỗ chỉ ăn
        theo (mặt hàng, số lượng), không đích danh lô/dòng phiếu nào (luật ② docstring model).
        """
        con = round(float(so_luong), 2)
        if con <= 0:
            return
        rows = (
            self.db.query(VatTuGiuCho)
            .filter(VatTuGiuCho.hang_loai == hang[0], VatTuGiuCho.hang_id == hang[1],
                    VatTuGiuCho.nguon == NGUON_DANG_VE)
            .order_by(VatTuGiuCho.created_at.asc())
            .all()
        )
        for r in rows:
            if con <= 0:
                break
            bot = round(min(con, _f(r.so_luong)), 2)
            if bot <= 0:
                continue
            con -= bot
            if _f(r.so_luong) - bot <= 0.004:
                r.nguon = NGUON_KHO
                r.ngay_ve = None
                r.purchase_request_line_id = None
            else:
                r.so_luong = round(_f(r.so_luong) - bot, 2)
                self.db.add(VatTuGiuCho(
                    hang_loai=hang[0], hang_id=hang[1], lsx_id=r.lsx_id,
                    bai_ghep_id=r.bai_ghep_id, so_luong=bot, nguon=NGUON_KHO, ngay_ve=None,
                    purchase_request_line_id=None,
                ))
        self.db.commit()
```

- [ ] **Step 4: Chạy test — phải PASS**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_chuyen_dang_ve_sang_kho_go_khoa_ngay -v`
Expected: PASS

- [ ] **Step 5: Wire vào `_apply_post` nhánh NHẬP**

Sửa `backend/app/services/stock_voucher_service.py:339-346`:

```python
        if self.giu_cho is not None:
            if v.loai == VOUCHER_XUAT:
                for (hang, chu), sl in self._gom_theo_hang_va_chu_the(v, lines_by_id).items():
                    if chu != (None, None):
                        self.giu_cho.tieu_thu(hang=hang, so_luong=sl,
                                              lsx_id=chu[0], bai_ghep_id=chu[1])
            else:
                # Hàng vừa vào kho: TRƯỚC hết, phần đang giữ HỨA của đúng mặt hàng này (nếu có)
                # phải chuyển thành giữ THẬT — không thì lệnh bị khoá lịch theo một ngày về đã
                # thành quá khứ dù hàng đã nằm trong kho (xem `chuyen_dang_ve_sang_kho`).
                for hang, sl in self._gom_theo_hang_nhap(v).items():
                    self.giu_cho.chuyen_dang_ve_sang_kho(hang, sl)
                self.giu_cho.nhat_them()
```

Thêm helper `_gom_theo_hang_nhap` ngay trước `_gom_theo_hang_va_chu_the`
(`backend/app/services/stock_voucher_service.py:514`):

```python
    @staticmethod
    def _gom_theo_hang_nhap(v) -> dict[tuple, float]:
        """`{(hang_loai, hang_id): Σ sl_goc}` của MỘT phiếu NHẬP — vào kho bao nhiêu, theo mặt
        hàng, không cần biết chủ thể (nhập kho không gắn lệnh nào)."""
        ra: dict[tuple, float] = {}
        for ln in v.lines:
            h = (ln.hang_loai, ln.hang_id)
            ra[h] = ra.get(h, 0.0) + float(ln.sl_goc)
        return ra

```

- [ ] **Step 6: Chạy test kho để chắc không phá luồng nhập cũ**

Run: `cd backend && python -m pytest tests/ -k "stock_voucher or kho" -v`
Expected: PASS toàn bộ.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/giu_cho_service.py backend/app/services/stock_voucher_service.py backend/tests/test_giu_cho_vat_tu.py
git commit -m "Kho: nhập hàng tự chuyển giữ-hứa (dang_ve) thành giữ-thật (kho), gỡ khoá lịch lỗi thời"
```

---

### Task 6: Tách `da_giu_kho` / `da_giu_dang_ve` trong `trang_thai()`

**Files:**
- Modify: `backend/app/services/giu_cho_service.py:134-181`
- Test: `backend/tests/test_giu_cho_vat_tu.py`

**Interfaces:**
- Produces: `GiuChoService.trang_thai(...)` trả thêm 3 khoá: `"da_giu_kho": dict[Hang, float]`,
  `"da_giu_dang_ve": dict[Hang, float]`, `"nguon_dang_ve": dict[Hang, list[dict]]` (mỗi phần tử
  `{"purchase_request_line_id": int, "so_luong": float}` — CHƯA có mã PMH, việc tra `ma_pmh` gộp
  theo lô thuộc Task 7/8 để tránh N+1 khi `theo_chu_the()` lặp qua MỌI chủ thể) — cạnh `"dang_giu"`
  cũ, KHÔNG xoá `"dang_giu"` (vẫn dùng ở `xep_lich_2/service.py:820` và nội bộ
  `giu_cho_service.py:219`). Phục vụ spec §4: "nguồn PMH cụ thể... để FE hiện được 'đang bám đơn
  nào'".

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== TÁCH NGUỒN TRONG trang_thai() ==================


def test_trang_thai_tach_da_giu_kho_va_dang_ve(db, svc, kh, customer):
    """`trang_thai()` phải tách được giữ THẬT (kho) và giữ HỨA (đang về), VÀ trả ra ĐÚNG dòng PMH
    nào đang góp cho phần hứa đó — không thì màn không biết phần nào đã chắc, phần nào còn treo
    theo ngày về, và không biết đang bám đơn nào để hối NCC."""
    from app.models.purchase import PurchaseRequestLine

    g = _giay(db)
    _ton(db, _giay_hang(g), 5)   # đủ 5 kg thật, còn thiếu phải bám hàng đang về
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()

    tt = svc.bat(lsx_id=a.id)

    hang = _giay_hang(g)
    assert tt["da_giu_kho"].get(hang, 0) == pytest.approx(5, abs=0.01)
    assert tt["da_giu_dang_ve"].get(hang, 0) == pytest.approx(16.77 - 5, abs=0.05)
    # Tổng hai nguồn phải khớp `dang_giu` cũ — không phá số cũ, chỉ tách thêm.
    assert tt["da_giu_kho"][hang] + tt["da_giu_dang_ve"][hang] == pytest.approx(
        tt["dang_giu"][hang], abs=0.01
    )
    nguon = tt["nguon_dang_ve"].get(hang, [])
    assert nguon and all(n["purchase_request_line_id"] == line.id for n in nguon)
    assert sum(n["so_luong"] for n in nguon) == pytest.approx(tt["da_giu_dang_ve"][hang], abs=0.01)
```

- [ ] **Step 2: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_trang_thai_tach_da_giu_kho_va_dang_ve -v`
Expected: FAIL — `KeyError: 'da_giu_kho'`.

- [ ] **Step 3: Sửa `trang_thai()`**

Sửa `backend/app/services/giu_cho_service.py:155-181`:

```python
        giu_theo_hang: dict[Hang, float] = {}
        giu_kho: dict[Hang, float] = {}
        giu_dang_ve: dict[Hang, float] = {}
        nguon_dang_ve: dict[Hang, list[dict]] = {}
        for r in dang:
            h = (r.hang_loai, r.hang_id)
            giu_theo_hang[h] = giu_theo_hang.get(h, 0.0) + _f(r.so_luong)
            if r.nguon == NGUON_KHO:
                giu_kho[h] = giu_kho.get(h, 0.0) + _f(r.so_luong)
            else:
                giu_dang_ve[h] = giu_dang_ve.get(h, 0.0) + _f(r.so_luong)
                if r.purchase_request_line_id is not None:
                    nguon_dang_ve.setdefault(h, []).append({
                        "purchase_request_line_id": r.purchase_request_line_id,
                        "so_luong": _f(r.so_luong),
                    })

        thieu: dict[Hang, float] = {}
        khong_ro = False
        for h, o in can.items():
            if o["khong_ro"]:
                khong_ro = True
            con = round(o["can"] - giu_theo_hang.get(h, 0.0), 4)
            if con > 0:
                thieu[h] = con

        ngay_ve = [r.ngay_ve for r in dang if r.nguon == NGUON_DANG_VE and r.ngay_ve]
        return {
            "bat": self._co_bat(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id),
            "du": not thieu and not khong_ro and bool(can),
            "khong_ro": khong_ro,
            "thieu": thieu,
            "dang_giu": giu_theo_hang,
            # [MỚI 30/08/2026] Tách theo nguồn — màn "Theo lệnh" cần biết phần nào CHẮC (kho) và
            # phần nào còn TREO theo ngày về (dang_ve). `dang_giu` (tổng) giữ nguyên cho chỗ đã
            # dùng cũ (`xep_lich_2`, `_them_mo_coi`).
            "da_giu_kho": giu_kho,
            "da_giu_dang_ve": giu_dang_ve,
            # Dòng PMH cụ thể đang góp cho phần hứa — CHƯA có mã PMH (tra gộp ở tầng gọi, xem
            # `giu_theo_chu_the_hang`/`gan_giu_cho_vao_bang`, Task 7/8).
            "nguon_dang_ve": nguon_dang_ve,
            "xep_som_nhat": max(ngay_ve) if ngay_ve else None,
            # Dòng giữ chỗ CŨ NHẤT — mốc đếm "giữ bao lâu rồi". Lấy min chứ không lấy max: nhặt
            # thêm khi hàng về đẻ dòng mới, lấy max là mỗi lần bù hàng lại reset đồng hồ về 0 và
            # chỗ giữ lâu nhất thì không bao giờ nổi lên danh sách.
            "giu_tu": min((r.created_at for r in dang), default=None),
        }
```

- [ ] **Step 4: Chạy test — phải PASS, rồi chạy cả file**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/giu_cho_service.py backend/tests/test_giu_cho_vat_tu.py
git commit -m "Giữ chỗ: tách da_giu_kho / da_giu_dang_ve + nguon_dang_ve trong trang_thai()"
```

---

### Task 7: `giu_theo_chu_the_hang()` — trạng thái giữ 6 mức + có-thể-giữ; wire vào `theo_chu_the()`

**Files:**
- Modify: `backend/app/services/giu_cho_service.py` (thêm method mới + sửa `theo_chu_the`)
- Modify: `backend/app/schemas/ke_hoach_vat_tu.py:152-187` (`TheoLenhHang`)
- Modify: `frontend/src/api/client.ts:7474-7504` (`TheoLenhHang` TS)
- Test: `backend/tests/test_giu_cho_vat_tu.py`

**Interfaces:**
- Consumes: `GiuChoService.trang_thai()` (Task 6, `da_giu_kho`/`da_giu_dang_ve`/`nguon_dang_ve`),
  `GiuChoService.ton_tu_do()`, `GiuChoService._lo_dang_ve()` (Task 2, 3-tuple).
- Produces: `GiuChoService.giu_theo_chu_the_hang(bang: dict, gom: dict | None = None) -> None`
  (MUTATE `gom` — thêm `h["da_giu_kho"]`, `h["da_giu_dang_ve"]`, `h["co_the_giu_kho"]`,
  `h["co_the_giu_dang_ve"]`, `h["trang_thai_giu"]`, `h["nguon_dang_ve"]` vào MỖI mặt hàng của MỖI
  chủ thể). Enum `trang_thai_giu`: `"khong_ro" | "thieu" | "ve_muon" | "co_the_giu" | "da_giu" |
  "da_cap"`. `h["nguon_dang_ve"]: list[{"purchase_request_line_id": int, "ma_pmh": str | None,
  "so_luong": float}]` — phục vụ spec §4 "để FE hiện được đang bám đơn nào". `TheoLenhHang`
  (Pydantic + TS) có thêm 6 field cùng tên.

- [ ] **Step 1: Viết test thất bại trước — chủ thể CHƯA bật giữ chỗ, tồn đủ ⇒ "co_the_giu"; sau khi bật ⇒ "da_giu"; mã PMH đang bám lộ ra ở `nguon_dang_ve`**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== TRẠNG THÁI GIỮ 6 MỨC ==================


def test_giu_theo_chu_the_hang_co_the_giu_roi_thanh_da_giu(db, svc, kh, customer):
    """Chưa bật giữ chỗ nhưng tồn đủ ⇒ `co_the_giu` (chưa giữ, biết là giữ được). Bật xong ⇒
    `da_giu`. Không tồn/không đủ để giữ ⇒ vẫn `thieu`/`ve_muon`/`khong_ro` như can_doi() gốc."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    hang = _giay_hang(g)

    bang = kh.can_doi()
    gom = svc._gom_theo_chu_the(bang)
    svc.giu_theo_chu_the_hang(bang, gom)
    h = gom[(a.id, None)]["hang"][hang]
    assert h["trang_thai_giu"] == "co_the_giu", h
    assert h["co_the_giu_kho"] == pytest.approx(16.77, abs=0.05)
    assert h["da_giu_kho"] == 0 and h["da_giu_dang_ve"] == 0

    svc.bat(lsx_id=a.id)
    bang2 = kh.can_doi()
    gom2 = svc._gom_theo_chu_the(bang2)
    svc.giu_theo_chu_the_hang(bang2, gom2)
    h2 = gom2[(a.id, None)]["hang"][hang]
    assert h2["trang_thai_giu"] == "da_giu", h2
    assert h2["da_giu_kho"] == pytest.approx(16.77, abs=0.05)
    assert h2["co_the_giu_kho"] == 0


def test_giu_theo_chu_the_hang_lo_ma_pmh_dang_bam(db, svc, kh, customer):
    """Phần giữ HỨA phải lộ ra ĐÚNG mã PMH đang góp cho nó (spec §4: 'để FE hiện được đang bám đơn
    nào') — không chỉ số lượng trần."""
    from app.models.purchase import PurchaseRequest, PurchaseRequestLine

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)   # ≈ 16,77 kg
    _phieu_mua(db, hang=_giay_hang(g), so_luong=100, ngay_ve=MAI)
    phieu = db.query(PurchaseRequest).order_by(PurchaseRequest.id.desc()).first()
    line = db.query(PurchaseRequestLine).order_by(PurchaseRequestLine.id.desc()).first()
    hang = _giay_hang(g)

    svc.bat(lsx_id=a.id)
    bang = kh.can_doi()
    gom = svc._gom_theo_chu_the(bang)
    svc.giu_theo_chu_the_hang(bang, gom)

    nguon = gom[(a.id, None)]["hang"][hang]["nguon_dang_ve"]
    assert nguon, "phải liệt kê nguồn PMH đang bám"
    assert nguon[0]["purchase_request_line_id"] == line.id
    assert nguon[0]["ma_pmh"] == phieu.code
```

- [ ] **Step 2: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_giu_theo_chu_the_hang_co_the_giu_roi_thanh_da_giu -v`
Expected: FAIL — `AttributeError: 'GiuChoService' object has no attribute 'giu_theo_chu_the_hang'`.

- [ ] **Step 3: Viết `_mau_giu` + `giu_theo_chu_the_hang`**

Thêm vào `backend/app/services/giu_cho_service.py`, ngay sau `_thu_tu_chu_the` (sau dòng 594, trước
`_dong`):

```python
    @staticmethod
    def _mau_giu(mau: str, da_kho: float, da_ve: float, can: float) -> str:
        """Nhãn 6 mức: Chưa rõ → Thiếu → Về muộn → Có thể giữ → Đã giữ → Đã cấp.

        `khong_ro`/`do`/`ve_muon` là SỰ THẬT về hàng (từ `can_doi()`), giữ chỗ không đổi được gì —
        pass-through nguyên vẹn (`do` đổi tên hiển thị thành `thieu` cho khớp bộ từ mới). `xam` =
        kho ĐÃ CẤP (xuất rồi) — giữ chỗ không còn ý nghĩa, luôn `da_cap`. Chỉ `xanh`/`vang` (đủ
        THEO can_doi(), tức hệ THỪA sức lo) mới cần hỏi tiếp CHÍNH chủ thể này đã thật sự giữ được
        phần của nó chưa: giữ đủ ⇒ `da_giu`, chưa ⇒ `co_the_giu`.
        """
        if mau == "do":
            return "thieu"
        if mau in ("khong_ro", "ve_muon"):
            return mau
        if mau == "xam":
            return "da_cap"
        return "da_giu" if (da_kho + da_ve) + 1e-6 >= can else "co_the_giu"

    def giu_theo_chu_the_hang(self, bang: dict, gom: dict[tuple, dict] | None = None) -> None:
        """Với MỖI (chủ thể, mặt hàng) trong `gom`, gắn thêm `da_giu_kho`/`da_giu_dang_ve` (đã
        giữ, tách nguồn), `co_the_giu_kho`/`co_the_giu_dang_ve` (NẾU bật giữ chỗ NGAY BÂY GIỜ thì
        giữ được thêm bao nhiêu), `trang_thai_giu` (nhãn 6 mức) và `nguon_dang_ve` (mã PMH cụ thể
        đang góp cho phần hứa — spec §4) — MUTATE thẳng vào `gom`.

        "Có thể giữ" là câu hỏi ĐỘC LẬP theo từng chủ thể: so với tồn tự do / lô đang về CÒN TRỐNG
        HIỆN TẠI — con số này đã trừ hết mọi chỗ đang giữ THẬT của MỌI chủ thể khác rồi (xem
        `ton_tu_do`/`_lo_dang_ve`), nên KHÔNG cần mô phỏng nhiều chủ thể tranh nhau nữa: "nếu CHỈ
        MÌNH tôi bật thì được bao nhiêu", không phải "nếu MỌI người cùng bật thì ai được bao
        nhiêu" (đó là việc CỦA `nhat_them()` khi nó thật sự chạy, theo đúng thứ tự ngày cần).

        Tra `ma_pmh` GỘP MỘT LẦN cho toàn bộ `gom` (không phải mỗi dòng một query) — `theo_chu_the()`
        gọi hàm này cho MỌI chủ thể trong bảng, N+1 ở đây là N có thể lên tới hàng trăm lệnh.
        """
        from sqlalchemy import select as _select

        from ..models.purchase import PurchaseRequest, PurchaseRequestLine

        if gom is None:
            gom = self._gom_theo_chu_the(bang)
        hangs = sorted({h for o in gom.values() for h in o["hang"]})
        tu_do = self.ton_tu_do(hangs)
        ve_tong: dict[Hang, float] = {
            h: sum(sl for _, sl, _lid in ds) for h, ds in self._lo_dang_ve(bang, hangs).items()
        }
        tt_by_chu: dict[tuple, dict] = {}
        line_ids: set[int] = set()
        for chu in gom:
            lsx_id, bg_id = chu
            tt = self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bg_id, bang=bang)
            tt_by_chu[chu] = tt
            for ds in tt["nguon_dang_ve"].values():
                line_ids.update(n["purchase_request_line_id"] for n in ds)
        ma_pmh: dict[int, str | None] = {}
        if line_ids:
            ma_pmh = dict(self.db.execute(
                _select(PurchaseRequestLine.id, PurchaseRequest.code)
                .join(PurchaseRequest, PurchaseRequest.id == PurchaseRequestLine.purchase_request_id)
                .where(PurchaseRequestLine.id.in_(line_ids))
            ).all())
        for chu, o in gom.items():
            tt = tt_by_chu[chu]
            for hang, h in o["hang"].items():
                da_kho = round(_f(tt["da_giu_kho"].get(hang)), 4)
                da_ve = round(_f(tt["da_giu_dang_ve"].get(hang)), 4)
                h["da_giu_kho"] = da_kho
                h["da_giu_dang_ve"] = da_ve
                h["nguon_dang_ve"] = [
                    {
                        "purchase_request_line_id": n["purchase_request_line_id"],
                        "ma_pmh": ma_pmh.get(n["purchase_request_line_id"]),
                        "so_luong": n["so_luong"],
                    }
                    for n in tt["nguon_dang_ve"].get(hang, [])
                ]
                # SỬA khi cài (30/08/2026): bản đầu viết `con = h["thieu"]` — SAI. `thieu` là
                # thiếu theo `can_doi()` (đã so tồn TOÀN HỆ), nên khi tồn đủ nó = 0 và
                # "có thể giữ" ra 0 đúng lúc câu hỏi có nghĩa nhất. Phần còn CHƯA GIỮ của
                # chính chủ thể mới là thứ cần đo.
                con = max(0.0, round(_f(h["can"]) - da_kho - da_ve, 4))
                co_kho = round(min(con, _f(tu_do.get(hang))), 4)
                co_ve = round(min(con - co_kho, _f(ve_tong.get(hang))), 4)
                h["co_the_giu_kho"] = co_kho
                h["co_the_giu_dang_ve"] = co_ve
                h["trang_thai_giu"] = self._mau_giu(h["trang_thai"], da_kho, da_ve, h["can"])
```

- [ ] **Step 4: Chạy test — phải PASS**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_giu_theo_chu_the_hang_co_the_giu_roi_thanh_da_giu tests/test_giu_cho_vat_tu.py::test_giu_theo_chu_the_hang_lo_ma_pmh_dang_bam -v`
Expected: PASS cả hai.

- [ ] **Step 5: Wire vào `theo_chu_the()`**

Sửa `backend/app/services/giu_cho_service.py:203-210`:

```python
        bang = self.kh.can_doi()
        gom = self._gom_theo_chu_the(bang)

        da_xep_lsx, da_xep_bai = self.repo.chu_the_da_xep_lich()
        gio = datetime.now(timezone.utc)

        self._them_mo_coi(gom)
        self.giu_theo_chu_the_hang(bang, gom)
        dang_thieu = self._chu_the_dang_thieu(gom)
```

- [ ] **Step 6: Mở rộng schema `TheoLenhHang`**

Sửa `backend/app/schemas/ke_hoach_vat_tu.py:152-187` (`TheoLenhHang`), thêm 6 field mới ngay sau
`dang_giu: float = 0` (giữ nguyên field cũ, chỉ chèn thêm):

```python
    dang_giu: float = 0
    # [MỚI 30/08/2026] Tách nguồn + trạng thái giữ 6 mức. Xem `GiuChoService.giu_theo_chu_the_hang`.
    da_giu_kho: float = 0
    da_giu_dang_ve: float = 0
    co_the_giu_kho: float = 0
    co_the_giu_dang_ve: float = 0
    trang_thai_giu: str = "xam"
    # Mã PMH cụ thể đang góp cho phần `da_giu_dang_ve` (spec §4 "để FE hiện được đang bám đơn
    # nào") — mỗi phần tử {"purchase_request_line_id": int, "ma_pmh": str|None, "so_luong": float}.
    nguon_dang_ve: list[dict] = []
```

- [ ] **Step 7: Mở rộng TS `TheoLenhHang`**

Sửa `frontend/src/api/client.ts`, ngay sau khai báo `CanDoiMau` (dòng 7344), thêm type mới:

```typescript
/** Trạng thái GIỮ CHỖ 6 mức — khác `CanDoiMau` (3 mức trung tính gộp lại): ở đây tách được "đã
 *  giữ" khỏi "có thể giữ nhưng chưa bật" khỏi "đã cấp thật". */
export type TrangThaiGiu = "khong_ro" | "thieu" | "ve_muon" | "co_the_giu" | "da_giu" | "da_cap";
```

Rồi sửa `TheoLenhHang` (dòng 7474-7504), thêm 6 field ngay sau `dang_giu: number;`:

```typescript
  /** Theo ĐƠN VỊ GỐC, đã trừ phần kho cấp rồi. */
  can: number;
  thieu: number;
  dang_giu: number;
  /** [MỚI 30/08/2026] Tách nguồn phần đã giữ + trạng thái giữ 6 mức — xem `TrangThaiGiu`. */
  da_giu_kho: number;
  da_giu_dang_ve: number;
  co_the_giu_kho: number;
  co_the_giu_dang_ve: number;
  trang_thai_giu: TrangThaiGiu;
  /** Mã PMH cụ thể đang góp cho `da_giu_dang_ve` — để hiện "đang bám đơn nào". */
  nguon_dang_ve: { purchase_request_line_id: number; ma_pmh: string | null; so_luong: number }[];
```

- [ ] **Step 8: Chạy lại toàn bộ test giữ chỗ + kiểm TypeScript**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -v`
Expected: PASS toàn bộ.

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS — không lỗi kiểu (chưa file nào TIÊU THỤ field mới nên không lỗi "unused", chỉ kiểm
cú pháp interface hợp lệ).

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/giu_cho_service.py backend/app/schemas/ke_hoach_vat_tu.py frontend/src/api/client.ts backend/tests/test_giu_cho_vat_tu.py
git commit -m "Giữ chỗ: trạng thái 6 mức (giu_theo_chu_the_hang) + co_the_giu_*, wire vào theo_chu_the/TheoLenhHang"
```

---

### Task 8: `gan_giu_cho_vao_bang()` — wire vào router `/can-doi` + schema `CanDoiDong`

**Files:**
- Modify: `backend/app/services/giu_cho_service.py` (thêm method mới)
- Modify: `backend/app/routers/ke_hoach_vat_tu.py:86-96`
- Modify: `backend/app/schemas/ke_hoach_vat_tu.py:14-67` (`CanDoiDong`)
- Modify: `frontend/src/api/client.ts:7346-7388` (`CanDoiDong`)
- Test: `backend/tests/test_giu_cho_vat_tu.py`

**Interfaces:**
- Consumes: `GiuChoService._gom_theo_chu_the`, `GiuChoService.giu_theo_chu_the_hang` (Task 7).
- Produces: `GiuChoService.gan_giu_cho_vao_bang(bang: dict) -> None` (MUTATE — gắn 6 field mới lên
  MỖI dòng `CanDoiDong` trong `bang["items"][*]["dong"]`, kể cả `nguon_dang_ve`). Router
  `GET /can-doi` giờ nhận thêm dependency `giu: GiuCho`.

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== GẮN GIỮ CHỖ VÀO BẢNG /can-doi ==================


def test_gan_giu_cho_vao_bang_dan_dung_dong(db, svc, kh, customer):
    """Mỗi dòng của bảng /can-doi phải nhận đúng con số giữ-chỗ của (chủ thể, mặt hàng) nó thuộc
    về — dòng nào không thuộc chủ thể nào (mồ côi cả hai) thì bỏ qua, không lỗi."""
    g = _giay(db)
    _ton(db, _giay_hang(g), 100)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    svc.bat(lsx_id=a.id)

    bang = kh.can_doi()
    svc.gan_giu_cho_vao_bang(bang)

    dong = [d for nhom in bang["items"] if nhom["loai_nhom"] == "vat_tu"
            for d in nhom["dong"] if d.get("lsx_id") == a.id]
    assert dong, "phải có ít nhất một dòng của lệnh A"
    assert dong[0]["trang_thai_giu"] == "da_giu"
    assert dong[0]["da_giu_kho"] == pytest.approx(16.77, abs=0.05)
```

- [ ] **Step 2: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_gan_giu_cho_vao_bang_dan_dung_dong -v`
Expected: FAIL — `AttributeError: 'GiuChoService' object has no attribute 'gan_giu_cho_vao_bang'`.

- [ ] **Step 3: Viết `gan_giu_cho_vao_bang`**

Thêm vào `backend/app/services/giu_cho_service.py`, ngay sau `giu_theo_chu_the_hang` (Task 7):

```python
    def gan_giu_cho_vao_bang(self, bang: dict) -> None:
        """Gắn 6 trường giữ-chỗ (`da_giu_kho`, `da_giu_dang_ve`, `co_the_giu_kho`,
        `co_the_giu_dang_ve`, `trang_thai_giu`, `nguon_dang_ve`) vào TỪNG DÒNG của bảng `/can-doi`
        — MUTATE thẳng vào `bang`.

        Giữ chỗ gộp theo (chủ thể, mặt hàng), KHÔNG theo TỪNG BƯỚC — một chủ thể ăn cùng món ở
        hai bước thì CÙNG một chỗ giữ trả lời cho CẢ HAI dòng (giữ hộ cả chuỗi, không tách được ai
        giữ phần nào). Mỗi dòng vì vậy nhận NGUYÊN con số gộp của (chủ thể, mặt hàng) nó thuộc về
        — không phải phần RIÊNG của dòng đó. Muốn số RIÊNG từng lệnh, xem màn "Theo lệnh"
        (`theo_chu_the`).
        """
        gom = self._gom_theo_chu_the(bang)
        self.giu_theo_chu_the_hang(bang, gom)
        tra_cuu: dict[tuple, dict] = {}
        for chu, o in gom.items():
            for hang, h in o["hang"].items():
                tra_cuu[(chu, hang)] = h
        for nhom in bang.get("items", []):
            if nhom.get("loai_nhom") != "vat_tu":
                continue
            hang = (nhom["hang_loai"], nhom["hang_id"])
            for d in nhom.get("dong", []):
                chu = (d.get("lsx_id"), d.get("bai_ghep_id"))
                h = tra_cuu.get((chu, hang))
                if h is None:
                    continue
                d["da_giu_kho"] = h["da_giu_kho"]
                d["da_giu_dang_ve"] = h["da_giu_dang_ve"]
                d["co_the_giu_kho"] = h["co_the_giu_kho"]
                d["co_the_giu_dang_ve"] = h["co_the_giu_dang_ve"]
                d["trang_thai_giu"] = h["trang_thai_giu"]
                d["nguon_dang_ve"] = h["nguon_dang_ve"]
```

- [ ] **Step 4: Chạy test — phải PASS**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_gan_giu_cho_vao_bang_dan_dung_dong -v`
Expected: PASS

- [ ] **Step 5: Mở rộng schema `CanDoiDong`**

Sửa `backend/app/schemas/ke_hoach_vat_tu.py:14-67` (`CanDoiDong`), thêm 6 field ngay sau
`trang_thai: CanDoiMau` (field đã có):

```python
    trang_thai: CanDoiMau
    # [MỚI 30/08/2026] Giữ chỗ gộp theo (chủ thể, mặt hàng) của DÒNG này — KHÔNG phải phần riêng
    # của dòng khi cùng chủ thể ăn cùng món ở nhiều bước (xem `GiuChoService.gan_giu_cho_vao_bang`).
    da_giu_kho: float | None = None
    da_giu_dang_ve: float | None = None
    co_the_giu_kho: float | None = None
    co_the_giu_dang_ve: float | None = None
    trang_thai_giu: str | None = None
    nguon_dang_ve: list[dict] | None = None
```

- [ ] **Step 6: Mở rộng TS `CanDoiDong`**

Sửa `frontend/src/api/client.ts:7346-7388` (`CanDoiDong`), thêm 6 field ngay sau
`trang_thai: CanDoiMau;`:

```typescript
  trang_thai: CanDoiMau;
  /** [MỚI 30/08/2026] Giữ chỗ gộp theo (chủ thể, mặt hàng) — KHÔNG phải phần riêng của dòng khi
   *  cùng chủ thể ăn cùng món ở nhiều bước. */
  da_giu_kho: number | null;
  da_giu_dang_ve: number | null;
  co_the_giu_kho: number | null;
  co_the_giu_dang_ve: number | null;
  trang_thai_giu: TrangThaiGiu | null;
  nguon_dang_ve: { purchase_request_line_id: number; ma_pmh: string | null; so_luong: number }[] | null;
```

- [ ] **Step 7: Wire router `/can-doi`**

Sửa `backend/app/routers/ke_hoach_vat_tu.py:86-96`:

```python
@router.get("/can-doi", response_model=CanDoiOut)
def can_doi(
    svc: Service,
    giu: GiuCho,
    _user: Annotated[object, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None, description="Mã lệnh / mã hoặc tên mặt hàng"),
    chi_thieu: bool = Query(default=False, description="Chỉ nhóm có dòng đỏ"),
) -> CanDoiOut:
    try:
        bang = svc.can_doi(q=q, chi_thieu=chi_thieu)
        giu.gan_giu_cho_vao_bang(bang)
        return CanDoiOut(**bang)
    except KeHoachVatTuError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
```

- [ ] **Step 8: Chạy lại test + kiểm TypeScript**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -v`
Expected: PASS toàn bộ.

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 9: Restart backend, gọi thử `/can-doi` qua trình duyệt dev để xác nhận field mới có mặt**

(Không cần UI tiêu thụ — chỉ xác nhận API không vỡ. Dùng dev-browser mở
`http://127.0.0.1:8000/docs`, thử `GET /api/ke-hoach-vat-tu/can-doi`, kiểm response JSON có
`da_giu_kho`/`trang_thai_giu` trên từng dòng `vat_tu`.)

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/giu_cho_service.py backend/app/routers/ke_hoach_vat_tu.py backend/app/schemas/ke_hoach_vat_tu.py frontend/src/api/client.ts backend/tests/test_giu_cho_vat_tu.py
git commit -m "Giữ chỗ: gắn trạng thái 6 mức + co_the_giu_* vào bảng /can-doi (gan_giu_cho_vao_bang)"
```

---

### Task 9: Chặn sửa số lượng / routing / xoá LSX khi đang giữ chỗ

**Files:**
- Modify: `backend/app/services/lsx_service.py:2634-2678,2700-2708,3041-3055`
- Test: `backend/tests/test_lsx_service.py` hoặc `backend/tests/test_giu_cho_vat_tu.py` (dùng file
  nào đã có fixture `LsxService` dựng sẵn — kiểm bằng Glob trước khi viết)

**Interfaces:**
- Produces: `LsxService._chan_dang_giu_cho(lsx: Lsx) -> None` — raise `LsxConflict` nếu
  `lsx.giu_cho_bat`. Gọi từ `replace_routing` (nên tự động áp dụng cho cả `xem_truoc_routing`, vì
  nó gọi `replace_routing(commit=False)`), `xoa`, và `update` (chỉ khi patch đổi `so_luong_dat`
  hoặc `quy_cach`).

**Phạm vi spec §3.6 kịch bản (b) — phía BÀI GHÉP đã chặn xong từ trước, task này KHÔNG đụng
`bai_ghep_service.py`:** spec §3.6 chốt "chặn CẢ hai kịch bản" — (a) sửa số lượng/quy cách công
đoạn, (b) ghép/tách bài ghép, đổi routing, huỷ LSX khi liên quan đang giữ. Đã grep toàn bộ
`backend/app/services/bai_ghep_service.py`: `_chan_dang_giu_cho(bg)` (dòng 226-242, chặn khi
`bg.giu_cho_bat`) và `_chan_lenh_dang_giu_cho(lsx_ids)` (dòng 244-262, chặn khi bất kỳ LSX thành
viên nào đang `giu_cho_bat`) đã tồn tại và đã được gọi ở **11 vị trí** trong file đó (thêm/rút
thành viên, ghép, tách, xoá bài...) — TRÙNG với thời điểm `GiuChoService` build 17/08/2026, không
phải việc của spec này. Việc CÒN THIẾU và LÀ VIỆC CỦA TASK NÀY chỉ là khoảng trống ở phía LSX
ĐỘC LẬP (chưa/không nằm trong bài ghép nào): `replace_routing`/`xoa`/`update` của `lsx_service.py`
KHÔNG hề kiểm `giu_cho_bat` — một LSX đứng riêng đang giữ chỗ vẫn sửa/xoá được vô tư, đúng lỗ hổng
spec đang siết.

- [ ] **Step 1: Tìm file test LSX đã có fixture sẵn**

Run: `cd backend && python -m pytest --collect-only -q tests/test_lsx_service.py 2>&1 | head -20`

(Chỉ để xác nhận file tồn tại và có test đang chạy được — không sửa. Nếu file không tồn tại, dùng
`backend/tests/test_giu_cho_vat_tu.py`, đã có sẵn `_lenh`/`svc`/`customer`/`kh` fixture.)

- [ ] **Step 2: Viết test thất bại trước — sửa `so_luong_dat` khi đang giữ chỗ phải bị chặn**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== CHẶN SỬA KHI ĐANG GIỮ CHỖ (LSX) ==================


def _lsx_svc(db) -> "LsxService":
    from app.repositories.lsx_repo import LsxRepository
    from app.repositories.audit_repo import AuditLogRepository
    from app.services.lsx_service import LsxService

    return LsxService(db, repo=LsxRepository(db), audit=AuditLogRepository(db))


def test_sua_so_luong_dat_khi_dang_giu_cho_bi_chan(db, svc, customer):
    """Đang giữ chỗ mà sửa SL đặt là đổi luôn số vật tư cần ⇒ phải chặn, giống cách bài ghép đã
    chặn thêm/rút thành viên khi đang giữ (`BaiGhepService._chan_dang_giu_cho`)."""
    from app.services.lsx_service import LsxConflict

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _ton(db, _giay_hang(g), 100)
    svc.bat(lsx_id=a.id)

    lsx_svc = _lsx_svc(db)
    payload = type("P", (), {"model_dump": lambda self, exclude_unset=True: {"so_luong_dat": 2000}})()
    admin = db.query(__import__("app.models.user", fromlist=["User"]).User).first()
    with pytest.raises(LsxConflict, match="giữ chỗ"):
        lsx_svc.update(lsx_id=a.id, payload=payload, actor=admin)
```

Nếu constructor `LsxService(db, repo=..., audit=...)` không khớp chữ ký thật (thiếu tham số bắt
buộc khác) — đọc `backend/app/services/lsx_service.py` phần đầu file (`class LsxService: def
__init__`) để lấy đúng danh sách tham số trước khi sửa `_lsx_svc()` cho khớp. Đây là điểm DUY NHẤT
trong plan chưa grep chữ ký `__init__` của `LsxService` — kiểm tra bằng
`Grep "class LsxService" -A 20 backend/app/services/lsx_service.py` trước khi chạy test.

- [ ] **Step 3: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_sua_so_luong_dat_khi_dang_giu_cho_bi_chan -v`
Expected: FAIL (guard chưa tồn tại — `update()` chạy qua, không raise).

- [ ] **Step 4: Thêm `_chan_dang_giu_cho`**

Thêm vào `backend/app/services/lsx_service.py`, ngay TRƯỚC `replace_routing` (trước dòng 2700):

```python
    def _chan_dang_giu_cho(self, lsx: Lsx) -> None:
        """Lệnh đang giữ chỗ vật tư → không đổi số lượng/quy cách/routing, không xoá.

        Đối xứng với `BaiGhepService._chan_dang_giu_cho`/`_chan_lenh_dang_giu_cho` ở phía bài ghép
        — nới ở phía lệnh sẽ vô hiệu hoá khoá phía bài (LSX đứng riêng vẫn đổi được số vật tư cần
        mà giữ chỗ không hay biết). Có ĐƯỜNG LÙI: nhả chỗ ở màn Kế hoạch vật tư rồi làm — chặn
        cứng không lối ra sẽ biến giữ chỗ thành cái khoá vĩnh viễn.

        Chặn CẢ preview (`replace_routing(commit=False)`, tức `xem_truoc_routing`): số trên màn
        xem trước đã dùng để người dùng QUYẾT ĐỊNH có nhả chỗ hay không — cho preview chạy qua thì
        màn nói dối, bấm Lưu thật mới báo lỗi.
        """
        if getattr(lsx, "giu_cho_bat", False):
            raise LsxConflict(
                f"Lệnh {lsx.ma} đang giữ chỗ vật tư — nhả chỗ ở màn Kế hoạch vật tư trước khi sửa "
                "số lượng, quy cách, routing hoặc xoá lệnh."
            )

```

- [ ] **Step 5: Gọi từ `replace_routing`, `xoa`, `update`**

Sửa `backend/app/services/lsx_service.py:2702-2708` (`replace_routing`):

```python
        lsx = self.get(lsx_id)
        if lsx.trang_thai == TT_DA_LAP_KE_HOACH:
            raise LsxConflict("Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi sửa routing")
        order = self.db.get(Order, lsx.order_id)
        if order is not None and order.status == STATUS_CANCELLED:
            raise LsxConflict("Đơn đã hủy — không thể sửa routing")
        self._chan_dang_giu_cho(lsx)
```

Sửa `backend/app/services/lsx_service.py:3053-3055` (`xoa`):

```python
        if ghep_ma:
            raise LsxConflict(f"LSX đang trong bài ghép {ghep_ma} — gỡ khỏi bài trước khi xoá")
        self._chan_dang_giu_cho(lsx)
```

Sửa `backend/app/services/lsx_service.py:2642-2652` (`update`) — chèn guard NGAY SAU vòng lặp field
thuần, TRƯỚC khối `quy_cach`:

```python
        for field in (
            "ten", "so_luong_dat", "don_vi_tinh",
            "so_con", "han_hoan_thanh_sx", "is_rush", "may_id",
            "nguoi_phu_trach_id", "ghi_chu",
        ):
            if field in data and getattr(lsx, field) != data[field]:
                setattr(lsx, field, data[field])
                changed.append(field)
        # Đổi SL đặt / quy cách là đổi luôn số vật tư cần — chặn khi đang giữ chỗ, cùng luật với
        # routing (`replace_routing`) và xoá lệnh (`xoa`). Field khác (tên, ghi chú, người phụ
        # trách...) không đụng vật tư nên KHÔNG chặn.
        if ("so_luong_dat" in changed or data.get("quy_cach")):
            self._chan_dang_giu_cho(lsx)
        # THÔNG SỐ (ảnh chụp) đổi → trộn vào rồi tính lại mọi số dẫn xuất. Đặt TRƯỚC chuỗi ngược
        # vì nó có thể đổi `so_con` (bình bài lại) — thứ chuỗi ngược lấy làm hệ số cầu.
        if data.get("quy_cach"):
```

- [ ] **Step 6: Chạy test — phải PASS**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_sua_so_luong_dat_khi_dang_giu_cho_bi_chan -v`
Expected: PASS

- [ ] **Step 7: Thêm test cho `replace_routing`/`xoa` + chạy lại toàn bộ test LSX**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
def test_xoa_lsx_khi_dang_giu_cho_bi_chan(db, svc, customer):
    from app.services.lsx_service import LsxConflict

    g = _giay(db)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    _ton(db, _giay_hang(g), 100)
    svc.bat(lsx_id=a.id)

    lsx_svc = _lsx_svc(db)
    admin = db.query(__import__("app.models.user", fromlist=["User"]).User).first()
    with pytest.raises(LsxConflict, match="giữ chỗ"):
        lsx_svc.xoa(lsx_id=a.id, actor=admin)
```

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -v && python -m pytest tests/test_lsx_service.py -v`
Expected: PASS toàn bộ cả hai file (file `test_lsx_service.py` xác nhận guard mới không phá luồng
sửa LSX bình thường khi KHÔNG giữ chỗ).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/lsx_service.py backend/tests/test_giu_cho_vat_tu.py
git commit -m "LSX: chặn sửa SL/quy cách/routing/xoá lệnh khi đang giữ chỗ vật tư"
```

---

### Task 10: Xuất kho — quy LSX đã ghép về bài đại diện

**Files:**
- Modify: `backend/app/services/stock_voucher_service.py:515-532` (`_gom_theo_hang_va_chu_the`)
- Test: `backend/tests/test_giu_cho_vat_tu.py` hoặc file test kho có sẵn dựng `StockVoucherService`

**Interfaces:**
- Consumes: `self.giu_cho: GiuChoService | None` (đã có sẵn trên `StockVoucherService`, optional);
  `GiuChoService.kh: KeHoachVatTuService` (đã có, từ constructor `GiuChoService(db, kh)`);
  `KeHoachVatTuService._nhu_cau_theo_chu_the(bang) -> dict[(lsx_id|None, bai_ghep_id|None), dict[hang, float]]`
  (hàm nội bộ ĐÃ CÓ, dùng ở `nhat_them()` — xem trích đoạn ở Task 11).
- Produces: `StockVoucherService._gom_theo_hang_va_chu_the(v, lines_by_id) -> dict[tuple, float]`
  — chuyển từ `@staticmethod` sang INSTANCE method (dùng `self.vouchers.db`), hành vi giống hệt cũ
  TRỪ khi dòng yêu cầu trỏ một LSX đã bị ghép (có mặt trong `BaiGhepThanhVien`) VÀ `can_doi()`
  không còn nhu cầu RIÊNG của đúng LSX đó cho đúng mặt hàng đó — CHỈ khi đó chủ thể mới quy về
  `(None, bai_ghep_id)`. Mơ hồ (không khớp bên nào) → raise `StockVoucherError`, KHÔNG đoán.

**Quyết định thiết kế (đọc trước khi viết code):** Bản nháp đầu của task này quy MỌI dòng yêu cầu
trỏ LSX-đã-ghép về bài, bất kể mặt hàng đó có phải "vật tư riêng bước" của chính LSX hay không — vi
phạm đúng điều spec §2 cảnh báo ("Vật tư riêng của LSX trong bài ghép không bị quy nhầm sang bài").
Điều kiện ĐÚNG (theo spec §2, câu "Chỉ quy phiếu xuất từ LSX sang bài ghép NẾU không có nhu cầu LSX
tương ứng VÀ có đúng một nhu cầu chung khớp; trường hợp mơ hồ phải cảnh báo") là: tra lại
`can_doi()` — chỉ quy khi mặt hàng KHÔNG còn nằm trong nhu cầu riêng `(lsx_id, None)` của chính LSX
đó. `BaiGhepThanhVien` có UniqueConstraint trên `lsx_id` (một LSX chỉ thuộc ĐÚNG MỘT bài ghép, xem
`backend/app/models/bai_ghep.py`) nên "nhiều bài khớp cùng lúc" không thể xảy ra — mơ hồ còn lại
duy nhất là "không khớp bên nào" (mặt hàng không nằm trong nhu cầu riêng CŨNG không nằm trong nhu
cầu bài) — trường hợp đó chặn ghi sổ, không đoán.

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== XUẤT KHO QUY LSX ĐÃ GHÉP VỀ BÀI ==================


def _dung_svcv(db, kh):
    from app.repositories.stock_voucher_repo import StockVoucherRepository
    from app.services.giu_cho_service import GiuChoService
    from app.services.stock_voucher_service import StockVoucherService

    return StockVoucherService(
        vouchers=StockVoucherRepository(db), requests=None, lots=None, sequence=None,
        request_service=None, hang=kh.hang, giu_cho=GiuChoService(db, kh),
    )


def _dung_phieu_xuat(db, hang, *, lsx_id, bai_ghep_id, kho_id=None):
    """Dựng thẳng 1 StockRequest (1 dòng) + 1 StockVoucher XUẤT khớp dòng đó — trả `(voucher,
    {request_line_id: request_line})` để gọi thẳng `_gom_theo_hang_va_chu_the`."""
    from app.models.stock_request import StockRequest, StockRequestLine, REQUEST_APPROVED
    from app.models.stock_voucher import StockVoucher, StockVoucherLine, VOUCHER_XUAT

    req = StockRequest(status=REQUEST_APPROVED, kho_id=kho_id)
    db.add(req)
    db.flush()
    rl = StockRequestLine(request_id=req.id, hang_loai=hang[0], hang_id=hang[1], sl_duyet=10,
                          sl_da_ung=0, don_vi="kg", lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
    db.add(rl)
    db.commit()

    v = StockVoucher(request_id=req.id, loai=VOUCHER_XUAT, kho_id=req.kho_id, trang_thai="nhap")
    db.add(v)
    db.flush()
    db.add(StockVoucherLine(voucher_id=v.id, request_line_id=rl.id, hang_loai=hang[0],
                            hang_id=hang[1], so_luong=10, sl_goc=10, don_vi="kg", lot_id=None))
    db.commit()
    return v, {rl.id: rl}


def test_gom_theo_hang_va_chu_the_quy_ve_bai_ghep(db, kh, customer):
    """Dòng yêu cầu kho khai `lsx_id` (lúc lập yêu cầu, lệnh còn ĐỘC LẬP) nhưng LSX đó SAU ĐÓ bị
    cuốn vào bài ghép — giấy LUÔN thuộc bài một khi đã ghép (spec §2: "Giấy... thuộc bài ghép"), nên
    `can_doi()` không còn nhu cầu riêng `(a.id, None)` cho giấy nữa. `kiem_xuat`/`tieu_thu` phải tra
    ĐÚNG chủ thể BÀI (nơi giữ chỗ dồn về), chứ không phải LSX đơn lẻ (nơi không còn giữ gì)."""
    from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien

    g = _giay(db)
    hang = _giay_hang(g)
    a = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=200)
    bg = BaiGhep(ma="GB-1", ten="Bài 1", trang_thai="nhap")
    db.add(bg)
    db.flush()
    db.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id))
    db.commit()

    svcv = _dung_svcv(db, kh)
    v, lines_by_id = _dung_phieu_xuat(db, hang, lsx_id=a.id, bai_ghep_id=None)
    ra = svcv._gom_theo_hang_va_chu_the(v, lines_by_id)
    assert (hang, (None, bg.id)) in ra, f"phải quy về bài ghép, thực tế: {ra}"
    assert (hang, (a.id, None)) not in ra


def test_gom_theo_hang_va_chu_the_khong_ghep_giu_nguyen_chu_the_lsx(db, kh, customer):
    """LSX KHÔNG nằm trong bài ghép nào (`ghep_cua` rỗng) — dòng yêu cầu khai `lsx_id` phải giữ
    NGUYÊN chủ thể LSX, không bị đụng tới. Đây là ca phổ biến nhất (đa số LSX không ghép) và cũng
    chứng minh nhánh "vật tư riêng không bị quy nhầm": vì `a` không hề thuộc bài nào, guard
    `lsx_id in ghep_cua` sai ngay từ đầu, không có cơ hội quy nhầm."""
    g = _giay(db)
    hang = _giay_hang(g)
    a = _lenh(db, customer, ma="LSX-B", giay_id=g.id, so_to_nguyen=200)
    db.commit()

    svcv = _dung_svcv(db, kh)
    v, lines_by_id = _dung_phieu_xuat(db, hang, lsx_id=a.id, bai_ghep_id=None)
    ra = svcv._gom_theo_hang_va_chu_the(v, lines_by_id)
    assert (hang, (a.id, None)) in ra
    assert all(chu != (None, None) for _, chu in ra)


def test_gom_theo_hang_va_chu_the_mo_ho_chan_ghi_so(db, kh, customer):
    """LSX đã ghép, nhưng mặt hàng trên dòng yêu cầu KHÔNG khớp nhu cầu riêng của LSX lẫn nhu cầu
    của bài (hàng lạ, không nằm trong routing của ai) — mơ hồ, phải chặn ghi sổ thay vì đoán, đúng
    spec §2 "trường hợp mơ hồ phải cảnh báo"."""
    from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
    from app.services.stock_voucher_service import StockVoucherError

    g = _giay(db)
    g_la = _giay(db, ma="GIAY-LA")  # giấy khác, KHÔNG nằm trong routing của `a` hay của bài
    hang_la = _giay_hang(g_la)
    a = _lenh(db, customer, ma="LSX-C", giay_id=g.id, so_to_nguyen=200)
    bg = BaiGhep(ma="GB-2", ten="Bài 2", trang_thai="nhap")
    db.add(bg)
    db.flush()
    db.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=a.id))
    db.commit()

    svcv = _dung_svcv(db, kh)
    v, lines_by_id = _dung_phieu_xuat(db, hang_la, lsx_id=a.id, bai_ghep_id=None)
    try:
        svcv._gom_theo_hang_va_chu_the(v, lines_by_id)
        assert False, "phải raise StockVoucherError vì mơ hồ, không được đoán"
    except StockVoucherError:
        pass
```

(Nếu `_giay(db, ma=...)` chưa nhận tham số `ma` — đọc helper hiện có trong file, thêm tham số optional
`ma: str | None = None` giữ nguyên hành vi mặc định khi không truyền, chỉ đổi mã khi có truyền. Nếu
`StockRequest`/`StockVoucher` đòi thêm field bắt buộc mà test trên thiếu — đọc model tương ứng, thêm
field còn thiếu với giá trị hợp lệ tối thiểu.)

- [ ] **Step 2: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -k "gom_theo_hang_va_chu_the" -v`
Expected: FAIL cả 3 test — `test_..._quy_ve_bai_ghep` sai vì `ra` vẫn có `(hang, (a.id, None))`;
2 test còn lại lỗi vì `_dung_svcv`/`_dung_phieu_xuat`/`StockVoucherError` chưa tồn tại đúng chỗ hoặc
`_gom_theo_hang_va_chu_the` chưa nhận `self.giu_cho`.

- [ ] **Step 3: Sửa `_gom_theo_hang_va_chu_the`**

Sửa `backend/app/services/stock_voucher_service.py:514-532`, đổi `@staticmethod` thành instance
method + thêm logic quy đổi CÓ KIỂM NHU CẦU THẬT (không chỉ theo cấu trúc bảng ghép):

```python
    def _gom_theo_hang_va_chu_the(self, v, lines_by_id: dict) -> dict[tuple, float]:
        """`{((hang_loai, hang_id), (lsx_id, bai_ghep_id)): Σ sl_goc}` của phiếu.

        Gộp theo ĐƠN VỊ GỐC (`sl_goc`) vì giữ chỗ đếm bằng đơn vị gốc — so `so_luong` (đơn vị người
        khai) với chỗ giữ là so hai thang khác nhau, đúng bẫy mà cửa kiểm lô ngay trên đã dặn.

        Chủ thể lấy từ DÒNG YÊU CẦU: phiếu kho không tự biết xuất cho lệnh nào, `stock_request_lines`
        mới là chỗ khai.

        [MỚI 30/08/2026] Dòng yêu cầu có thể khai `lsx_id` từ lúc lệnh còn ĐỘC LẬP, nhưng lệnh đó
        SAU ĐÓ bị cuốn vào bài ghép. Giữ chỗ theo NHU CẦU THẬT (`can_doi()`), KHÔNG theo cấu trúc
        bảng ghép: vật tư RIÊNG bước của LSX thành viên vẫn thuộc LSX dù đã ghép (spec §2); chỉ vật
        tư CHUNG (giấy + vật tư bước chung) mới thuộc bài. Vì vậy CHỈ quy `(lsx_id, None)` sang
        `(None, bai_ghep_id)` khi `can_doi()` KHÔNG còn nhu cầu riêng của đúng LSX cho đúng mặt hàng
        này — nếu vẫn còn, giữ nguyên chủ thể LSX (không quy nhầm vật tư riêng sang bài). Mơ hồ
        (không khớp nhu cầu riêng LẪN nhu cầu bài) → chặn ghi sổ, không đoán (spec §2). Chỉ chạy khi
        có `self.giu_cho` — không giữ chỗ thì không có gì phải bảo vệ, giữ hành vi CŨ (đọc thẳng
        `lsx_id`/`bai_ghep_id` từ dòng yêu cầu).
        """
        from sqlalchemy import select

        from ..models.bai_ghep import BaiGhepThanhVien

        nhu_cau = None
        ghep_cua: dict[int, int] = {}
        if self.giu_cho is not None:
            lsx_can_tra = {
                getattr(rl, "lsx_id", None)
                for rl in lines_by_id.values()
                if getattr(rl, "lsx_id", None) is not None
                and getattr(rl, "bai_ghep_id", None) is None
            }
            if lsx_can_tra:
                ghep_cua = dict(self.vouchers.db.execute(
                    select(BaiGhepThanhVien.lsx_id, BaiGhepThanhVien.bai_ghep_id)
                    .where(BaiGhepThanhVien.lsx_id.in_(lsx_can_tra))
                ).all())
            if ghep_cua:
                # SỬA khi cài: `_nhu_cau_theo_chu_the` nằm trên GiuChoService, KHÔNG phải `kh`.
                nhu_cau = self.giu_cho._nhu_cau_theo_chu_the(self.giu_cho.kh.can_doi())

        ra: dict[tuple, float] = {}
        for ln in v.lines:
            rl = lines_by_id.get(ln.request_line_id)
            lsx_id = getattr(rl, "lsx_id", None)
            bg_id = getattr(rl, "bai_ghep_id", None)
            hang = (ln.hang_loai, ln.hang_id)
            if nhu_cau is not None and lsx_id is not None and bg_id is None and lsx_id in ghep_cua:
                if hang not in nhu_cau.get((lsx_id, None), {}):
                    bid = ghep_cua[lsx_id]
                    if hang in nhu_cau.get((None, bid), {}):
                        lsx_id, bg_id = None, bid
                    else:
                        raise StockVoucherError(
                            f"Không xác định được {hang[0]}#{hang[1]} thuộc lệnh #{lsx_id} riêng "
                            f"hay bài ghép #{bid} — vào Kế hoạch vật tư kiểm lại trước khi ghi sổ."
                        )
            khoa = (hang, (lsx_id, bg_id))
            ra[khoa] = ra.get(khoa, 0.0) + float(ln.sl_goc)
        return ra
```

`StockVoucherError` đã định nghĩa NGAY TRONG file này (`stock_voucher_service.py:52`, class-level,
cùng module với `StockVoucherService`) — dùng thẳng, không cần import gì thêm. `self.giu_cho` cũng
đã là tham số constructor sẵn có (`__init__(..., giu_cho=None)`, dòng 57-58) — không cần đổi chữ ký.

- [ ] **Step 4: Chạy test — phải PASS, rồi chạy lại toàn bộ test kho**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -k "gom_theo_hang_va_chu_the" -v`
Expected: PASS cả 3 test.

Run: `cd backend && python -m pytest tests/ -k "stock_voucher" -v`
Expected: PASS toàn bộ (chuyển static→instance method không đổi API bên ngoài, hai call site
`self._gom_theo_hang_va_chu_the(...)` ở `_apply_post` đã tự dùng `self.` sẵn theo Python — kiểm lại
bằng Grep `_gom_theo_hang_va_chu_the` trong file để chắc không còn lời gọi kiểu
`StockVoucherService._gom_theo_hang_va_chu_the(...)` ở đâu khác; cả hai call site hiện có đều đã
nằm trong nhánh `if self.giu_cho is not None:` nên hàm luôn có `self.giu_cho` khi logic quy đổi
thực sự chạy tới — không cần lo `AttributeError`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stock_voucher_service.py backend/tests/test_giu_cho_vat_tu.py
git commit -m "Kho: xuất kho quy LSX đã ghép về chủ thể bài ghép theo nhu cầu thật, chặn khi mơ hồ"
```

---

### Task 11: Khoá nguồn theo thứ tự ổn định (đối chiếu spec §3.6)

**Files:**
- Modify: `backend/app/services/giu_cho_service.py` (thêm `_khoa_nguon`, wire vào `nhat_them`,
  `chuyen_dang_ve_sang_kho`, `doi_soat_dang_ve`, `kiem_xuat`)
- Test: `backend/tests/test_giu_cho_vat_tu.py`

**Interfaces:**
- Produces: `GiuChoService._khoa_nguon(hangs: list[Hang]) -> None`.

**Phạm vi thật sự làm được (đọc trước khi implement, tránh hiểu nhầm là khoá tuyệt đối):** spec
§3.6 đòi "mọi thao tác giữ, nhập, xuất và đối soát nguồn chạy trong MỘT giao dịch... chỉ commit
MỘT LẦN". `GiuChoRepository.them()`/`xoa_cua_chu_the()` và `GiuChoService.tieu_thu()` đã TỰ COMMIT
độc lập từ trước khi có plan này (xem `giu_cho_repo.py:47-51,39-45` và `giu_cho_service.py:550`)
— quy ước NÀY xuyên suốt module, đổi nó thành "một giao dịch duy nhất" là việc TÁI CẤU TRÚC lớn,
đụng tới mọi service gọi vào (`StockVoucherService`, `PurchaseService`...), ngoài phạm vi siết
logic của spec này. Việc LÀM ĐƯỢC và ĐỦ để spec §5's test "hai thao tác giữ đồng thời không giữ
vượt tồn" thật sự đúng: khoá DÒNG GỐC của mặt hàng (`SELECT ... FOR UPDATE`) NGAY TỪ BƯỚC ĐỌC ĐẦU
TIÊN của mỗi thao tác — hai giao dịch cùng đụng một mặt hàng thì giao dịch sau phải CHỜ tới khi
giao dịch trước tới điểm tự-commit gần nhất (nhả khoá), lúc đó số đã ĐÃ ghi nhận xong, giao dịch
sau đọc lại state MỚI chứ không đọc song song state CŨ rồi cùng ghi đè — đúng thứ đang cần chặn.
Khoá theo (hang_loai, hang_id) TĂNG DẦN (đúng ví dụ spec nêu) để hai giao dịch chạm nhiều mặt hàng
theo thứ tự khác nhau không tự khoá chéo nhau (deadlock).

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào `backend/tests/test_giu_cho_vat_tu.py`:

```python
# ================== KHOÁ NGUỒN — GIAO DỊCH MỘT LẦN ==================


def test_khoa_nguon_khong_loi_va_theo_thu_tu_on_dinh(db, svc):
    """`_khoa_nguon` phải chạy được (không lỗi) khi truyền LỘN thứ tự — tự sắp lại theo
    (hang_loai, hang_id) TĂNG DẦN trước khi khoá — và không lỗi khi gọi LẦN HAI trong CÙNG giao
    dịch (mô phỏng `nhat_them()` rồi `kiem_xuat()` cùng chạm một mặt hàng trong một lượt xử lý).

    SQLite (test) coi `FOR UPDATE` là no-op — cùng giới hạn đã ghi nhận ở
    `stock_voucher_repo.py::khoa_de_ghi_so` — nên test này chỉ xác nhận KHÔNG VỠ, không xác nhận
    chặn concurrent thật (chỉ Postgres dev/prod mới khoá thật)."""
    g1 = _giay(db, ma="GY-1")
    g2 = _giay(db, ma="GY-2")

    svc._khoa_nguon([("giay", g2.id), ("giay", g1.id)])
    svc._khoa_nguon([("giay", g1.id)])
```

- [ ] **Step 2: Chạy test — phải FAIL**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_khoa_nguon_khong_loi_va_theo_thu_tu_on_dinh -v`
Expected: FAIL — `AttributeError: 'GiuChoService' object has no attribute '_khoa_nguon'`.

- [ ] **Step 3: Viết `_khoa_nguon`**

Thêm vào `backend/app/services/giu_cho_service.py`, ngay sau `# ================== phụ ==================`
(trước `_lo_dang_ve`, dòng 555):

```python
    def _khoa_nguon(self, hangs: list[Hang]) -> None:
        """Khoá DÒNG GỐC (danh mục Giấy/Vật tư khác) của từng mặt hàng — `SELECT ... FOR UPDATE`,
        sắp theo (hang_loai, hang_id) TĂNG DẦN trước khi khoá. Thứ tự cố định: hai giao dịch cùng
        đụng một tập mặt hàng, dù gọi theo thứ tự khác nhau, luôn khoá theo CÙNG một trình tự —
        không bao giờ khoá chéo (deadlock).

        Neo vào bảng GỐC chứ không phải `vat_tu_giu_cho`: một mặt hàng CHƯA từng được giữ chỗ thì
        không có dòng `vat_tu_giu_cho` nào để khoá, nhưng dòng gốc (mặt hàng ở danh mục) luôn có
        sẵn. Cùng khuôn với khoá header phiếu kho chống ghi sổ hai lần
        (`stock_voucher_repo.py::khoa_de_ghi_so`) — SQLite (test) coi FOR UPDATE là no-op,
        Postgres (dev/prod) khoá thật.
        """
        from sqlalchemy import select as _select

        from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn

        for hang_loai, hang_id in sorted(set(hangs)):
            model = GiayNguyen if hang_loai == "giay" else VatTuInAn
            self.db.execute(_select(model.id).where(model.id == hang_id).with_for_update())
```

- [ ] **Step 4: Chạy test — phải PASS**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py::test_khoa_nguon_khong_loi_va_theo_thu_tu_on_dinh -v`
Expected: PASS

- [ ] **Step 5: Wire vào `nhat_them()`**

Sửa `backend/app/services/giu_cho_service.py:456-458`:

```python
        hangs = sorted({h for m in nhu_cau.values() for h in m})
        self._khoa_nguon(hangs)
        tu_do = self.ton_tu_do(hangs)
        ve = self._lo_dang_ve(bang, hangs)
```

- [ ] **Step 6: Wire vào `kiem_xuat()`**

Sửa `backend/app/services/giu_cho_service.py:498-510` — thêm 1 dòng ngay đầu thân hàm, sau
docstring:

```python
    def kiem_xuat(self, *, hang: Hang, so_luong: float,
                  lsx_id: int | None = None, bai_ghep_id: int | None = None) -> str | None:
        """Kho sắp xuất `so_luong` của `hang` cho ai đó — có lấn vào chỗ người khác giữ không?

        Trả câu từ chối, hoặc `None` nếu xuất được.

        Được phép lấy: **tồn tự do + phần CHÍNH chủ thể này đang giữ**. Vế sau là mấu chốt — xuất
        cho lệnh A thì chính chỗ A giữ phải dùng được, không thì giữ chỗ tự khoá chân người giữ.

        Xuất KHÔNG gắn lệnh nào (`lsx_id`/`bai_ghep_id` đều trống — lĩnh chung, bù hao, mẫu) thì
        chỉ được ăn phần tự do.
        """
        self._khoa_nguon([hang])
        tu_do = _f(self.ton_tu_do([hang]).get(hang))
```

(Phần thân còn lại của `kiem_xuat()` giữ nguyên y hệt, chỉ chèn thêm dòng `self._khoa_nguon([hang])`
ở trên.)

- [ ] **Step 7: Wire vào `chuyen_dang_ve_sang_kho()` (Task 5) và `doi_soat_dang_ve()` (Task 3)**

Sửa đầu thân `chuyen_dang_ve_sang_kho()` (đã viết ở Task 5) — thêm dòng khoá ngay sau dòng
`if con <= 0: return`:

```python
        con = round(float(so_luong), 2)
        if con <= 0:
            return
        self._khoa_nguon([hang])
        rows = (
```

Sửa đầu thân `doi_soat_dang_ve()` (đã viết ở Task 3) — thêm dòng khoá ngay sau dòng xác định
`hang`:

```python
        hang = (held[0].hang_loai, held[0].hang_id)
        self._khoa_nguon([hang])
        con_ve, ngay_ve = 0.0, None
```

- [ ] **Step 8: Chạy lại TOÀN BỘ test giữ chỗ**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -v`
Expected: PASS toàn bộ — khoá thêm vào không đổi kết quả tính toán ở SQLite (no-op), chỉ xác nhận
không phá luồng cũ.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/giu_cho_service.py backend/tests/test_giu_cho_vat_tu.py
git commit -m "Giữ chỗ: khoá dòng gốc mặt hàng (FOR UPDATE, thứ tự ổn định) trước mọi thao tác giữ/nhập/xuất/đối soát"
```

---

### Task 12: SSE backend — real-time cho Kế hoạch vật tư

**Files:**
- Modify: `backend/app/services/giu_cho_service.py` (thêm `hub.broadcast` ở các điểm ghi)
- Test: không cần test mới (broadcast không có assertion hợp lý ở tầng unit; xác nhận bằng đọc lại
  code + Task 15 xác nhận qua UI thật)

**Interfaces:**
- Consumes: `backend.app.realtime.hub.broadcast(dict) -> None` (đã có, dùng trực tiếp).

- [ ] **Step 1: Thêm import `hub`**

Sửa đầu `backend/app/services/giu_cho_service.py` (sau `from ..repositories.giu_cho_repo import
GiuChoRepository`, dòng 48):

```python
from ..realtime import hub
from ..repositories.giu_cho_repo import GiuChoRepository
```

- [ ] **Step 2: Broadcast sau `bat()` / `tat()`**

Sửa `backend/app/services/giu_cho_service.py:422-439`:

```python
    def bat(self, *, lsx_id: int | None = None, bai_ghep_id: int | None = None) -> dict:
        """Bật công tắc rồi nhặt được bao nhiêu hay bấy nhiêu.

        Nhặt TỒN TỰ DO trước, thiếu thì bám lô đang về theo ngày tăng dần — hàng có thật bao giờ
        cũng hơn hàng mới hứa, và lô về sớm hơn thì ràng buộc lịch nhẹ hơn.
        """
        self._doi_co(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id, bat=True)
        # MỘT lượt dựng bảng cho cả ba việc (nhặt · soi lại · trả kết quả). Bảng không phụ thuộc
        # bảng giữ chỗ nên các dòng vừa nhặt không làm nó cũ đi.
        bang = self.kh.can_doi()
        self.nhat_them(chi_chu_the=(lsx_id, bai_ghep_id), bang=bang)
        hub.broadcast({"type": "ke_hoach_vat_tu_thay_doi"})
        return self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id, bang=bang)

    def tat(self, *, lsx_id: int | None = None, bai_ghep_id: int | None = None) -> dict:
        """Nhả HẾT. Không phải hoàn tác — bật lại có thể chẳng còn gì, nơi gọi phải hỏi trước."""
        self.repo.xoa_cua_chu_the(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
        self._doi_co(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id, bat=False)
        hub.broadcast({"type": "ke_hoach_vat_tu_thay_doi"})
        return self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
```

- [ ] **Step 3: Broadcast sau `nhat_them()` (chỉ khi thật sự đẻ dòng mới), `chuyen_dang_ve_sang_kho()`, `doi_soat_dang_ve()`**

Sửa cuối `nhat_them()` (`backend/app/services/giu_cho_service.py:493-494`):

```python
        self.repo.them(moi)
        if moi:
            hub.broadcast({"type": "ke_hoach_vat_tu_thay_doi"})
        return len(moi)
```

Sửa cuối `chuyen_dang_ve_sang_kho()` (Task 5, dòng cuối `self.db.commit()`):

```python
        self.db.commit()
        hub.broadcast({"type": "ke_hoach_vat_tu_thay_doi"})
```

Sửa cuối `doi_soat_dang_ve()` (Task 3, dòng cuối `self.db.commit()`):

```python
        self.db.commit()
        hub.broadcast({"type": "ke_hoach_vat_tu_thay_doi"})
```

- [ ] **Step 4: Chạy lại TOÀN BỘ test giữ chỗ để chắc `hub.broadcast` không vỡ gì (không có event loop trong test)**

Run: `cd backend && python -m pytest tests/test_giu_cho_vat_tu.py -v`
Expected: PASS toàn bộ — `hub.broadcast` là fire-and-forget tới danh sách kênh SSE đang mở, KHÔNG
kênh nào mở trong test nên không có side-effect nào cần assert; nếu FAIL vì lỗi import/kiểu, đọc
`backend/app/realtime.py` để xác nhận `hub.broadcast(dict)` không yêu cầu event loop đang chạy
(hầu hết các service khác trong dự án đã gọi trực tiếp trong test — theo đúng mẫu
`stock_request_service.py`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/giu_cho_service.py
git commit -m "Giữ chỗ: broadcast SSE khi bật/tắt/nhặt thêm/chuyển kho/đối soát"
```

---

### Task 13: SSE frontend — mở kênh cho `ke_hoach_vat_tu` + toast

**Files:**
- Modify: `frontend/src/components/appShellRealtime.ts`
- Modify: `frontend/src/components/AppShell.tsx:576-611`

**Interfaces:**
- Consumes: `hub.broadcast({"type": "ke_hoach_vat_tu_thay_doi"})` (Task 12).
- Produces: kênh SSE chung mở cho user có quyền đọc module `ke_hoach_vat_tu`; mọi event bump
  `quoteTick` (đã có cơ chế chung, không cần sửa gì khác) + 1 toast ngắn.

- [ ] **Step 1: Thêm `ke_hoach_vat_tu` vào `REALTIME_MODULES`**

Sửa `frontend/src/components/appShellRealtime.ts`:

```typescript
const REALTIME_MODULES = new Set([
  "bao_gia", "don_hang_ban", "khach_hang", "luong", "san_xuat", "bai_ghep_2",
  "xep_lich_2", "kho", "tang_ca", "cham_cong", "thu_mua", "yeu_cau_mua_hang", "ke_toan",
  "phieu_chi", "phieu_thu", "ke_hoach_vat_tu",
]);
```

- [ ] **Step 2: Thêm vào cổng inline trong `AppShell.tsx`**

Sửa `frontend/src/components/AppShell.tsx:578-582`:

```typescript
    if (!token || readable === null || !(readable.has("bao_gia") || readable.has("don_hang_ban") || readable.has("khach_hang") || readable.has("luong") || readable.has("san_xuat") || readable.has("kho") || readable.has("tang_ca") || readable.has("cham_cong") || readable.has("thu_mua") || readable.has("yeu_cau_mua_hang") || readable.has("ke_toan") ||
      readable.has("phieu_chi") || readable.has("phieu_thu") || readable.has("ke_hoach_vat_tu") ||
      // Tài xế thường CHỈ có ô `giao_hang` — không mở cổng ở đây thì họ không kết nối
      // SSE, và mọi thông báo chuyến gửi cho họ rơi vào hư không.
      readable.has("giao_hang"))) return;
```

- [ ] **Step 3: Thêm toast ngắn khi có sự kiện giữ chỗ**

Sửa `frontend/src/components/AppShell.tsx`, ngay sau khối `quote_decision` (tìm đoạn kết thúc bằng
`reloadBadges();` sau dòng 609 trong đoạn đã đọc — thêm một nhánh `else if` mới cùng cấp):

```typescript
      if (e.type === "ke_hoach_vat_tu_thay_doi") {
        pushToast("Kế hoạch vật tư vừa cập nhật.", "info");
        return;
      }
```

Đặt nhánh này NGAY SAU dòng `setQuoteTick((n) => n + 1);` ở L601 (trước khối `if (e.type ===
"quote_decision")`), để tick đã kịp bump cho MỌI event (kể cả event này) trước khi return sớm.

- [ ] **Step 4: Kiểm TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/appShellRealtime.ts frontend/src/components/AppShell.tsx
git commit -m "SSE: mở kênh real-time cho module Kế hoạch vật tư"
```

---

### Task 14: FE `GiuChoTheoLenhView.tsx` — dùng `trang_thai_giu` thay `trang_thai`

**Files:**
- Modify: `frontend/src/pages/GiuChoTheoLenhView.tsx:29-40,428-431,487,629-631,746,852-856,1025`

**Interfaces:**
- Consumes: `TheoLenhHang.trang_thai_giu: TrangThaiGiu` (Task 7).

- [ ] **Step 1: Thêm bảng nhãn/màu cho `trang_thai_giu`**

Sửa `frontend/src/pages/GiuChoTheoLenhView.tsx`, ngay sau `MAU_VATTU`/`mauVatTu` (dòng 29-40):

```typescript
const MAU_VATTU: Record<string, { label: string; cls: string; dotColor: string }> = {
  xam: { label: "Đã cấp", cls: "khvt-stream-chip--xam", dotColor: "var(--ash-2)" },
  xanh: { label: "Đủ tồn", cls: "khvt-stream-chip--xanh", dotColor: "var(--moss)" },
  vang: { label: "Chờ hàng về", cls: "khvt-stream-chip--vang", dotColor: "var(--kh-canhbao-fg)" },
  do: { label: "Thiếu cần mua", cls: "khvt-stream-chip--do", dotColor: "var(--kh-thieu-fg)" },
  khong_ro: { label: "Chưa rõ ĐVT", cls: "khvt-stream-chip--khongro", dotColor: "var(--steel)" },
  ve_muon: { label: "Hàng về muộn", cls: "khvt-stream-chip--vemuon", dotColor: "var(--kh-vemuon-fg)" },
};

function mauVatTu(mau: CanDoiMau) {
  return MAU_VATTU[mau] ?? { label: String(mau), cls: "khvt-stream-chip--khongro", dotColor: "var(--steel)" };
}

/** [MỚI 30/08/2026] Nhãn/màu cho trạng thái GIỮ CHỖ 6 mức — thay `MAU_VATTU`/`mauVatTu` ở màn này,
 *  vì đây LÀ màn "giữ chỗ theo lệnh": `co_the_giu`/`da_giu`/`da_cap` mới đúng câu hỏi màn này trả
 *  lời ("lệnh này chạy được chưa"), không phải `xanh`/`vang`/`xam` của can_doi() (chỉ nói "hệ CÓ
 *  đủ hàng không", không nói "CHÍNH LỆNH NÀY đã giữ được chưa"). */
const MAU_VATTU_GIU: Record<string, { label: string; cls: string; dotColor: string }> = {
  khong_ro: { label: "Chưa rõ ĐVT", cls: "khvt-stream-chip--khongro", dotColor: "var(--steel)" },
  thieu: { label: "Thiếu cần mua", cls: "khvt-stream-chip--do", dotColor: "var(--kh-thieu-fg)" },
  ve_muon: { label: "Hàng về muộn", cls: "khvt-stream-chip--vemuon", dotColor: "var(--kh-vemuon-fg)" },
  co_the_giu: { label: "Có thể giữ", cls: "khvt-stream-chip--vang", dotColor: "var(--kh-canhbao-fg)" },
  da_giu: { label: "Đã giữ", cls: "khvt-stream-chip--xanh", dotColor: "var(--moss)" },
  da_cap: { label: "Đã cấp", cls: "khvt-stream-chip--xam", dotColor: "var(--ash-2)" },
};

function mauVatTuGiu(mau: TrangThaiGiu) {
  return MAU_VATTU_GIU[mau] ?? { label: String(mau), cls: "khvt-stream-chip--khongro", dotColor: "var(--steel)" };
}
```

- [ ] **Step 2: Import `TrangThaiGiu`**

Sửa import ở đầu file (dòng 4-14), thêm `type TrangThaiGiu`:

```typescript
import {
  ApiError,
  api,
  type CanDoiKhoaDong,
  type CanDoiMau,
  type DeNghiMuaXemTruoc,
  type HangLoai,
  type TheoLenhHang,
  type TheoLenhOut,
  type TheoLenhRow,
  type TrangThaiGiu,
} from "../api/client";
```

- [ ] **Step 3: Đổi 3 chỗ tính `soMonDu` — dùng `trang_thai_giu` thay vì `trang_thai`**

Sửa CẢ BA vị trí (dòng 430, 629, 854) — mẫu đổi giống nhau, ví dụ dòng 430:

```typescript
                  const soMonDu = r.hang.filter((h) => h.trang_thai_giu === "da_cap" || h.trang_thai_giu === "da_giu").length;
```

(Áp dụng ĐÚNG câu thay thế này ở cả 3 nơi: dòng 430 trong bảng dòng chảy, dòng 629 trong chế độ
thẻ, dòng 854 trong drawer chi tiết — cả ba đang viết y hệt
`r.hang.filter((h) => h.trang_thai === "xanh" || h.trang_thai === "xam").length`.)

Lý do đổi: `trang_thai` cũ (của `can_doi()`) chỉ nói "hệ THEO LÝ THUYẾT có đủ hàng không", không
nói "CHÍNH LỆNH NÀY đã giữ được phần của nó chưa" — một lệnh chưa bật giữ chỗ vẫn có thể hiện
`xanh`/`xam` (hệ đủ hàng) trong khi thực tế lệnh CHƯA GIỮ ĐƯỢC GÌ, khiến "Độ sẵn sàng vật tư" báo
sai. `trang_thai_giu` (`da_cap`/`da_giu`) mới đúng nghĩa "lệnh NÀY đã có phần đó thật".

- [ ] **Step 4: Đổi 3 chỗ `mauVatTu(h.trang_thai)` → `mauVatTuGiu(h.trang_thai_giu)`**

Sửa CẢ BA vị trí (dòng 487, 746, 1025):

```typescript
                            const meta = mauVatTuGiu(h.trang_thai_giu);
```

- [ ] **Step 5: Kiểm TypeScript + build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/GiuChoTheoLenhView.tsx
git commit -m "FE: màn Theo lệnh dùng trạng thái giữ 6 mức (trang_thai_giu) thay can_doi() thô"
```

---

### Task 15: Kiểm thử tích hợp toàn luồng qua dev-browser thật

**Files:** không sửa code — chỉ vận hành + xác nhận (bắt buộc theo CLAUDE.md: luồng có UI phải thao
tác lại bằng chuột/bàn phím thật trước khi báo xong).

- [ ] **Step 1: Restart backend + frontend dev server**

Backend PHẢI restart (đổi route/schema nhiều nơi, không hot-reload đáng tin). Dùng cách đã ghi
trong bộ nhớ dự án (đẻ qua WMI `Win32_Process.Create`, KHÔNG dùng Bash nền/Start-Process — chết khi
hết phiên). BE tại `127.0.0.1:8000`, FE tại `localhost:5173`.

- [ ] **Step 2: Đăng nhập dev-browser**

Mở `http://localhost:5173`, đăng nhập `admin` / `admin123` (`SEED_ADMIN_PASSWORD`, KHÔNG phải
`123456` — input React cần set qua JS native setter nếu gõ trực tiếp không ăn).

- [ ] **Step 3: Luồng 1 — Nhập kho tự chuyển giữ hứa → giữ thật (Task 5)**

Từ dev-browser: vào Kế hoạch sản xuất → Kế hoạch vật tư → tìm/mở một lệnh còn thiếu vật tư có phiếu
mua đang về. Bấm BẬT giữ chỗ cho lệnh đó (nếu chưa bật). Ghi lại "Xếp sớm nhất" (ngày bị khoá) đang
hiện trên thẻ. Sang màn Kho → Nhập kho, lập MỘT phiếu nhập cho đúng mặt hàng/đủ số lượng lệnh đang
giữ hứa, GHI SỔ phiếu đó bằng nút trên UI. Quay lại Kế hoạch vật tư (không F5 — chờ SSE tự cập
nhật, hoặc F5 nếu SSE chưa kịp), xác nhận: thẻ lệnh đó KHÔNG còn "Xếp sớm nhất" bị khoá (đã null),
và trạng thái mặt hàng đổi từ "Đã giữ (chờ hàng về)" sang "Đã giữ" không kèm ngày.

- [ ] **Step 4: Luồng 2 — Huỷ PMH tự nhả giữ chỗ (Task 3, 4)**

Tìm một lệnh khác đang giữ chỗ MỘT PHẦN nhờ hàng đang về (chưa nhập kho). Ghi lại số đang giữ. Sang
Mua hàng, mở đúng PMH cấp cho lệnh đó, bấm HUỶ ĐƠN bằng nút UI (nhập lý do khi được hỏi). Quay lại
Kế hoạch vật tư, xác nhận phần giữ hứa của lệnh đó đã GIẢM ĐÚNG bằng số vừa mất (không giảm toàn bộ
nếu lệnh còn giữ được từ nguồn khác).

- [ ] **Step 5: Luồng 3 — Chặn sửa khi đang giữ chỗ (Task 9)**

Với một lệnh đang BẬT giữ chỗ: mở drawer sửa Số lượng đặt hoặc Thông số (quy cách) trên UI, thử Lưu
— xác nhận hệ báo lỗi rõ ràng ("đang giữ chỗ vật tư — nhả chỗ...") và KHÔNG lưu được. Bấm TẮT giữ
chỗ, thử lại — xác nhận lần này Lưu được bình thường.

- [ ] **Step 6: Luồng 4 — Trạng thái giữ 6 mức hiện đúng trên màn Theo lệnh (Task 7, 14)**

Trên màn "Theo lệnh", xác nhận: một lệnh CHƯA bật giữ chỗ nhưng tồn kho đủ hiện nhãn "Có thể giữ"
(không phải "Đủ tồn" cũ); sau khi bấm Bật, cùng mặt hàng đó đổi sang "Đã giữ". Chụp lại 1 ảnh màn
hình xác nhận nhãn mới hiển thị đúng.

- [ ] **Step 7: Báo cáo kết quả**

Liệt kê CỤ THỂ từng bước đã bấm/gõ/thấy ở Task 15 (không nói chung chung "đã test UI") — theo đúng
yêu cầu CLAUDE.md. Nếu bất kỳ luồng nào phải tắt qua API để dựng dữ liệu (vd tạo PMH/phiếu mua
nhanh vì UI luồng đó không phải trọng tâm), phải khai rõ NGAY trong báo cáo, không đợi hỏi.

---

# PHẦN B — Đề nghị cấp vật tư theo công đoạn (bổ sung 30/08/2026)

> ## ⛔ PHẦN B ĐÃ BỊ THAY THẾ — ĐỪNG THI CÔNG TASK 16–22
>
> Chủ dự án chốt lại thiết kế ngày **31/08/2026**. Bản chốt đó nằm ở
> `docs/spec-de-nghi-cap-vat-tu-cong-doan.md`, plan thi công ở
> `docs/superpowers/plans/2026-08-31-de-nghi-cap-vat-tu-cong-doan.md`.
>
> Phần B dưới đây **mâu thuẫn** với bản chốt ở bốn điểm, không phải chỉ khác cách viết:
>
> 1. Nối kho ở **mức DÒNG** (`stock_request_lines.sx_cong_viec_id`) — bản chốt nối ở **mức PHIẾU**
>    (`san_xuat_vat_tu_de_nghi.stock_request_id`, 1–1).
> 2. Điều chỉnh thực xuất bằng cách **hạ `sl_duyet`** — bản chốt giữ nguyên `sl_duyet` và ghi cột
>    mới `sl_chot_thuc_xuat`, vì hạ `sl_duyet` làm xin-100-xuất-70 và xin-70-xuất-70 không phân
>    biệt được nữa.
> 3. Nguồn kế hoạch gọi `vat_tu_theo_buoc` — bản chốt gọi
>    `KeHoachVatTuService.nhu_cau_cua_cong_viec`.
> 4. Không có `lan_so` / `loai` (lần đầu vs bổ sung) / `dvt_goc` / `sl_*_goc`, và không có luồng
>    huỷ-khi-về-0 rồi khôi phục giữ mã.
>
> Migration `0246` ở Task 16 cũng **không phải** migration `0246` của bản chốt — cùng số, khác nội
> dung. Chỉ có MỘT `0246` được tồn tại: bản của plan 31/08.
>
> Phần A (Task 1–15) **vẫn còn hiệu lực** và đã thi công xong.


**Goal:** Gộp chức năng yêu cầu vật tư vào khối **Vật tư** của công đoạn đang có ở màn Thực hiện sản
xuất. Tổ trưởng chủ động tạo/sửa đề nghị; hệ thống tự điền theo kế hoạch; kho tiếp tục xử lý bằng
luồng đề nghị → phiếu xuất hiện tại. KHÔNG màn mới, KHÔNG cho người lập kế hoạch tham gia, KHÔNG
thêm bước duyệt hay trạng thái "Đã soạn xong".

**Architecture:** Một bảng đối chiếu MỚI ở phía sản xuất (`san_xuat_vat_tu_de_nghi` +
`..._dong`) giữ quyết định của tổ trưởng — kể cả quyết định "không cần cấp" (số `0`). Phần **dương**
của bảng đó đẻ ra `StockRequest`/`StockRequestLine` hiện có (tự duyệt), nên kho không học luồng mới.
Nguồn tự điền là `KeHoachVatTuService.can_doi()` chiếu xuống đúng `buoc_id` — cùng khuôn với
`vat_tu_hieu_luc()` đã có tại [ke_hoach_vat_tu_service.py:725](../../../backend/app/services/ke_hoach_vat_tu_service.py:725),
không viết đường tính nhu cầu thứ hai.

## Kết luận nghiệp vụ đã khóa (Phần B)

1. Không chặn bắt đầu sản xuất vì chưa có đề nghị hoặc chưa nhận vật tư.
2. Không có màn báo cáo tổng hợp trong đợt này; truy vết nằm ngay tại công đoạn.
3. Không lưu phiên bản từng lần sửa đề nghị — chỉ giữ người tạo, người sửa cuối và dữ liệu mới nhất.
4. Không có bước duyệt, không có trạng thái "Đã soạn xong".
5. Mỗi công đoạn tối đa MỘT đề nghị đang sửa được; kho đã lập bất kỳ phiếu nào thì khóa, muốn thêm
   thì tạo **đề nghị bổ sung**.
6. Toàn bộ dòng bằng `0` ⇒ chỉ lưu quyết định sản xuất, kho không nhận yêu cầu rỗng.
7. Mọi so sánh số lượng làm ở **đơn vị gốc**; form vẫn mặc định đơn vị quen dùng trong kế hoạch.

## Va chạm với luật đang chạy — phải xử đúng chỗ, đừng nới bừa

Ba chỗ dưới đây là lý do Phần B không thể "cắm thẳng" vào luồng kho. Đọc trước khi viết code.

1. **"Đã duyệt là khoá" — và mọi yêu cầu kho ở hệ này SINH RA đã `approved`.** Bước duyệt đã bị bỏ
   từ 06/08/2026: `StockRequestService.create()` set thẳng `REQ_APPROVED` + `sl_duyet = sl_de_nghi`
   ngay lúc tạo ([stock_request_service.py:117-127](../../../backend/app/services/stock_request_service.py:117)),
   với lý do ghi trong code là "tạo xong khoá luôn". Mà `update()` mở đầu bằng `_require_editable()`
   ⇒ chỉ `draft`/`pending` mới qua ([stock_request_service.py:172](../../../backend/app/services/stock_request_service.py:172),
   `REQUEST_EDITABLE` tại [stock_request.py:54](../../../backend/app/models/stock_request.py:54)).
   Nghĩa là **không có yêu cầu nào sửa được qua cửa update của kho**, chứ không phải "sửa được lúc
   còn nháp". Phần B lại đòi *vẫn sửa được cho tới khi kho lập phiếu*. **Không nới `REQUEST_EDITABLE`**
   — nới là mở cửa cho mọi module sửa yêu cầu đã duyệt. Đường đi: cửa sửa nằm ở service SẢN XUẤT,
   thao tác trên đề nghị SX rồi ĐỒNG BỘ xuống `stock_request_lines` của đúng yêu cầu do chính nó
   sinh ra (gọi `requests.replace_lines` / sửa `req.lines` trực tiếp, KHÔNG qua `update()`), và chỉ
   khi yêu cầu đó **chưa có phiếu nào trỏ tới**. Đổi `sl_de_nghi` thì phải đổi `sl_duyet` cùng lúc —
   `sl_duyet` mới là mốc kho được ứng tới.
2. **`sl_de_nghi > 0` là CheckConstraint DB**
   ([stock_request.py:191](../../../backend/app/models/stock_request.py:191)). Dòng `0` KHÔNG thể tồn
   tại bên kho — khớp với luật 6 ở trên: dòng `0` sống ở bảng SX, không đẩy sang kho. Đừng "sửa" ràng
   buộc này.
3. **`dieu_chinh_xuat` hiện GIẢM `sl_da_ung`**
   ([stock_voucher_service.py:503](../../../backend/app/services/stock_voucher_service.py:503)) — đó
   là "Option 2 chốt 2026-08-28": trả hàng xong thì yêu cầu quay lại *"còn N chưa cấp"*. Phần B **đảo
   quyết định đó**: hạ **mốc hoàn tất** (`sl_duyet`) xuống số thực xuất để đề nghị ĐÓNG. Task 20 làm
   việc này và phải giữ nguyên ca "kho cấp thiếu, chưa có thao tác trả" vẫn ở `partial`.

**Ghi chú cơ hội (NGOÀI phạm vi đợt này, đừng tự làm):** khi `stock_request_lines` mang được chiều
BƯỚC (Task 16), điều kiện để gỡ "Hệ quả CHƯA XỬ" ở
[`_da_cap_dang_linh()`](../../../backend/app/services/ke_hoach_vat_tu_service.py:455) — khoá 3 phần
tử làm lệnh ăn cùng một món ở hai bước bị trừ "đã cấp" hai lần — mới bắt đầu có. Ghi lại ở đây để
lần sau không phải tìm lại; muốn làm thì mở đợt riêng.

**Ràng buộc verify:** giữ nguyên Global Constraints ở đầu plan (verify bằng `pytest <file>::<test>`
nhắm đúng file vừa sửa, không tự chạy `./init.ps1` toàn bộ). Bản mô tả gốc của Phần B ghi "chạy xác
minh duy nhất `./init.ps1`" — chỉ chạy bộ đầy đủ khi chủ dự án yêu cầu.

---

### Task 16: Bảng đối chiếu vật tư theo công đoạn + chiều BƯỚC cho dòng yêu cầu kho

**Files:**
- Create: `backend/app/models/san_xuat_vat_tu.py` (2 bảng mới)
- Modify: `backend/app/models/stock_request.py` (thêm `sx_cong_viec_id` vào `StockRequestLine`)
- Modify: `backend/app/db_migrations.py` (migration `0246`, thêm cuối file)
- Modify: `docs/DB_SCHEMA.md` — 2 bảng mới + cột mới ở mục `stock_request_lines` (`:5479`)
- Test: `backend/tests/test_san_xuat_vat_tu_de_nghi.py` (mới)

**Interfaces:**
- Produces `SanXuatVatTuDeNghi`: `cong_viec_id` (FK `san_xuat_cong_viec`, CASCADE), `lan` (1 = lần
  đầu, ≥2 = bổ sung), `can_luc` (DateTime tz — thời điểm cần vật tư), `stock_request_id` (soft ref,
  NULL khi toàn bộ dòng bằng `0`), `nguoi_tao_id`, `nguoi_sua_id`, `created_at`, `updated_at`.
- Produces `SanXuatVatTuDeNghiDong`: `de_nghi_id`, `hang_loai`, `hang_id`, `dvt`, `sl_ke_hoach`,
  `sl_yeu_cau` (**cho phép `0`** — khác `stock_request_lines`), `ly_do_chenh_lech`,
  `stock_request_line_id` (soft ref, NULL với dòng `0`).
- Produces cột `StockRequestLine.sx_cong_viec_id: int | None` — soft ref `san_xuat_cong_viec.id`,
  index; NULL với mọi dòng cũ và mọi dòng không sinh từ màn công đoạn.

- [ ] **Step 1: Viết test thất bại** — 2 bảng mới tồn tại sau `create_all`; `sl_yeu_cau = 0` lưu
  được; cột `sx_cong_viec_id` có mặt trên `stock_request_lines`; chạy lại `run_migrations` không vỡ.
- [ ] **Step 2: Chạy test — phải FAIL.**
- [ ] **Step 3: Dựng 2 model mới.** Bảng MỚI thì `create_all` tự dựng, không cần migration (xem ghi
  chú [stock_request.py:12](../../../backend/app/models/stock_request.py:12)). Numeric dùng
  `Numeric(14, 2)` cho khớp dòng yêu cầu kho. `sl_yeu_cau >= 0` (KHÔNG `> 0`).
- [ ] **Step 4: Thêm cột `sx_cong_viec_id` + migration `0246`.** Migration số kế tiếp sau `0245` của
  Phần A — nếu Phần A chưa chạy thì vẫn giữ thứ tự này, không đổi số. Soft ref (không FK cứng), cùng
  khuôn `purchase_delivery_id`/`delivery_trip_id` đã có.
- [ ] **Step 5: Cập nhật `docs/DB_SCHEMA.md`** cùng lúc — guard test bắt mọi cột phải có mặt.
- [ ] **Step 6: Chạy lại test — PASS.**

---

### Task 17: Nguồn tự điền — chiếu `can_doi()` xuống đúng công đoạn

**Files:**
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py` (thêm phép chiếu theo bước)
- Test: `backend/tests/test_ke_hoach_vat_tu.py`

**Interfaces:**
- Produces `KeHoachVatTuService.vat_tu_theo_buoc(*, lsx_id, bai_ghep_id, buoc_id) -> list[dict]` —
  mỗi phần tử `{hang_loai, hang_id, ma, ten, dvt_goi_y, sl_ke_hoach}`.

- [ ] **Step 1: Test thất bại** — công đoạn của LSX trả đúng vật tư bước riêng; công đoạn chung của
  bài ghép trả GIẤY + vật tư bước chung; một lệnh ăn cùng món ở hai bước thì mỗi bước chỉ thấy phần
  của mình.
- [ ] **Step 2: Chạy test — FAIL.**
- [ ] **Step 3: Cài đặt** bằng cách lọc `can_doi()["items"] → dong` theo `buoc_id` (dòng nhu cầu đã
  mang sẵn `buoc_id`, xem [:753](../../../backend/app/services/ke_hoach_vat_tu_service.py:753)) —
  KHÔNG đọc `vat_tu_json`, KHÔNG viết phép tính nhu cầu thứ hai. `dvt_goi_y` = đơn vị hiển thị mà kế
  hoạch đang dùng; `sl_ke_hoach` giữ ở **đơn vị gốc** để so sánh, phần hiển thị quy sau.
- [ ] **Step 4: Nối vào phía sản xuất** — công việc snapshot mang `lsx_cong_doan_id` /
  `bai_ghep_cong_doan_id`, đó là `buoc_id` cần truyền vào.
- [ ] **Step 5: Chạy test — PASS.**

---

### Task 18: Service + API tạo/sửa đề nghị cấp vật tư

**Files:**
- Create: `backend/app/services/san_xuat/vat_tu_de_nghi.py`
- Modify: `backend/app/routers/san_xuat.py`
- Modify: `backend/app/schemas/san_xuat.py`
- Test: `backend/tests/test_san_xuat_vat_tu_de_nghi.py`

**Interfaces:**
- `POST /api/san-xuat/work-items/{id}/material-requests`
- `PUT  /api/san-xuat/work-items/{id}/material-requests/{request_id}`
- Payload: `{can_luc, dong: [{hang_loai, hang_id, dvt, sl_yeu_cau, ly_do_chenh_lech}]}`.

- [ ] **Step 1: Test thất bại cho toàn bộ luật:**
  - Tổ trưởng ĐÚNG tổ tạo được; người lập kế hoạch / quản lý ngoài tổ / thiếu quyền bị chặn.
  - Khớp kế hoạch ⇒ không cần lý do. Tăng / giảm / bỏ / thêm ngoài kế hoạch ⇒ **bắt buộc** lý do.
    Mọi dòng của đề nghị **bổ sung** ⇒ bắt buộc lý do.
  - Toàn bộ `0` ⇒ lưu được, `stock_request_id` NULL, kho không thấy gì.
  - Kho chưa lập phiếu ⇒ `PUT` sửa được, số bên kho đổi theo.
  - Kho đã lập phiếu ⇒ `PUT` bị chặn, phải tạo đề nghị bổ sung (`lan + 1`).
  - Mỗi công đoạn tối đa một đề nghị đang sửa được.
- [ ] **Step 2: Chạy test — FAIL.**
- [ ] **Step 3: Gate quyền.** Cần `san_xuat:assign_work` **và** đang là tổ trưởng đúng tổ — dùng lại
  `_gate` ở [thuc_thi.py](../../../backend/app/services/san_xuat/thuc_thi.py), KHÔNG đòi `kho:request`.
- [ ] **Step 4: Ghi bảng SX trước, sinh yêu cầu kho sau — QUA `StockRequestService.create()`.**
  Chỉ dòng `sl_yeu_cau > 0` mới xuống kho. **Đừng dựng `StockRequest` bằng ORM thẳng**: `create()`
  là chỗ sinh mã `DNX…` (`generate_flat_code`), chạy `_validate_lines` (mặt hàng có thật + đơn vị quy
  được về gốc + không trùng mặt hàng), tự duyệt, rồi `_notify` + `_notif_kho_moi` để Hộp yêu cầu kho
  nhảy badge ngay. Bỏ qua nó là mất cả năm thứ.
  Tham số: `loai=REQ_XUAT`, `lines=[...]`, `ngay_can` = phần NGÀY của `can_luc`, và **`bo_phan_id`
  truyền TƯỜNG MINH** = tổ của công đoạn — mặc định của `create()` là `user.department_id` (bộ phận
  người tạo), không phải tổ thực hiện. Phần "tự duyệt" KHÔNG cần viết lại: `create()` đã làm.
  Dòng mang `lsx_id`/`bai_ghep_id` đúng chủ thể của công đoạn + `sx_cong_viec_id`.
- [ ] **Step 5: Sửa đề nghị.** Chặn khi yêu cầu kho đã có bất kỳ `StockVoucherLine` nào trỏ tới
  (không phân biệt nháp/đã ghi sổ). **Không gọi `StockRequestService.update()`** — nó vấp
  `_require_editable` (xem va chạm 1). Sửa dòng trực tiếp: cập nhật `sl_de_nghi` **và** `sl_duyet`
  cùng lúc, xoá dòng về `0`, thêm dòng mới; chạy lại `_validate_lines` cho dòng mới thêm để không lọt
  mặt hàng lạ. Ghi `nguoi_sua_id` + `updated_at`; KHÔNG lưu phiên bản.
- [ ] **Step 6: Chạy test — PASS.**

---

### Task 19: Chi tiết công đoạn trả bảng đối chiếu + lọc phiếu theo công đoạn + SSE

**Files:**
- Modify: `backend/app/services/san_xuat/board.py:396` (khối `vat_tu`)
- Modify: `backend/app/repositories/san_xuat_san_luong_repo.py:299` (`voucher_xuat_cua_lsx`)
- Modify: `backend/app/schemas/san_xuat.py` (`WorkItemChiTietOut` — **bắt buộc**, xem cảnh báo dưới)
- Modify: `backend/app/routers/san_xuat.py` (phát SSE)
- Modify: `frontend/src/api/client.ts` (type `SxWorkItemChiTiet` + khai type sự kiện mới)

⚠️ `/work-items/{id}` có `response_model=WorkItemChiTietOut`
([routers/san_xuat.py:365](../../../backend/app/routers/san_xuat.py:365)). Field service trả về mà
schema Out không khai thì Pydantic **bỏ im lặng, không báo lỗi** — FE nhận `undefined`. Thêm
`vat_tu_de_nghi` phải đi đủ 4 chặng: dict ở `board.py` → `WorkItemChiTietOut` → type TS → chỗ dùng.
- Test: `backend/tests/test_san_xuat_vat_tu_de_nghi.py`

- [ ] **Step 1: Test thất bại** — chi tiết công đoạn trả `vat_tu_de_nghi` gồm: các lần đề nghị +
  trạng thái kho, bảng đối chiếu `kế hoạch – tổng yêu cầu – thực xuất`, chênh lệch + lý do + người
  chịu trách nhiệm + thời điểm, và hai cờ `co_the_sua` / `co_the_bo_sung`. Nhiều lần bổ sung phải
  **cộng dồn** đúng ở cột "tổng yêu cầu".
- [ ] **Step 2: Chạy test — FAIL.**
- [ ] **Step 3: Lọc phiếu theo công đoạn — VÀ vá luôn lỗ bài ghép.** Hai lỗi cùng chỗ:
  (a) `voucher_xuat_cua_lsx` join theo `StockRequestLine.lsx_id` ⇒ phiếu của công đoạn A hiện cả ở
  công đoạn B cùng LSX; (b) [board.py:306](../../../backend/app/services/san_xuat/board.py:306) gọi
  `sl.voucher_xuat_cua_lsx(cv.lsx_id) **if cv.lsx_id else []**` ⇒ công việc CHUNG của bài ghép
  (`lsx_id = None`, `bai_ghep_id` mới có giá trị) **luôn trả khối vật tư rỗng** — đúng những công
  đoạn ăn giấy nhiều nhất lại không thấy phiếu nào. Đổi thành một hàm nhận cả hai chiều: ưu tiên
  `sx_cong_viec_id ==` công việc đang mở; dòng CŨ chưa có liên kết thì **fallback theo `lsx_id`
  HOẶC `bai_ghep_id`** tuỳ công việc (không mất dữ liệu cũ).
- [ ] **Step 4: SSE.** Luồng TẠO đã có sẵn real-time nhờ `_notify` + `_notif_kho_moi` bên trong
  `StockRequestService.create()` — không phát thêm, phát thêm là kho nhận hai lần. Chỉ cần thêm sự
  kiện cho luồng **SỬA** (không đi qua `create()`). Dùng đúng khuôn 7 chỗ phát SSE đã có trong
  router — phát SAU commit. Khai type ở `client.ts` (union sự kiện hiện thiếu nhiều loại
  `san_xuat_*`, đừng thêm mà không khai).
- [ ] **Step 5: Chạy test — PASS.**

---

### Task 20: Trả vật tư — hạ mốc hoàn tất thay vì mở lại "còn thiếu"

**Files:**
- Modify: `backend/app/services/stock_voucher_service.py:400-510` (`dieu_chinh_xuat`)
- Test: `backend/tests/test_kho_de_nghi.py` — thêm mục mới. ⚠️ Hiện **KHÔNG có test nào chạm
  `dieu_chinh_xuat`** (grep toàn `backend/tests` trả rỗng), nên Task này viết test đầu tiên cho nó;
  `test_kho_phieu.py` không tồn tại, đừng tìm.

- [ ] **Step 1: Test thất bại:**
  - Yêu cầu 100, kho xuất 100, thủ kho điều chỉnh còn 70 ⇒ lô `+30`; `sl_de_nghi` giữ **100**;
    `sl_da_ung = 70`; `sl_duyet` hạ xuống **70**; yêu cầu chuyển `done`, KHÔNG báo "còn thiếu 30".
  - Yêu cầu 100, kho mới cấp 70, **chưa** điều chỉnh ⇒ vẫn `partial`, `sl_duyet` giữ **100**.
- [ ] **Step 2: Chạy test — FAIL** (hiện `sl_da_ung` bị giảm ⇒ quay lại "còn 30 chưa cấp").
- [ ] **Step 3: Đổi luật.** Thay vì `rl.sl_da_ung -= con_bo`
  ([:503](../../../backend/app/services/stock_voucher_service.py:503)), giữ nguyên `sl_da_ung` = số
  thực xuất sau điều chỉnh và hạ `rl.sl_duyet` xuống bằng nó. Sửa docstring "Option 2 chốt
  2026-08-28" cho khớp quyết định mới, ghi rõ ngày đảo và lý do — đừng để hai câu chuyện trong một
  file. Giữ nguyên phần trả tồn về lô và `giu_cho.nhat_them()`.
- [ ] **Step 4: Giữ audit hiện có** — người sửa, thời điểm, `100 → 70`, lý do. Chỉ thủ kho thao tác;
  không cần tổ trưởng xác nhận, không tạo phiếu trả riêng.
- [ ] **Step 5: Chạy test — PASS.**

---

### Task 21: FE — khối Vật tư của công đoạn

**Files:**
- Modify: `frontend/src/pages/ThsxExecPanels.tsx:767` (khối "Vật tư nhận")
- Modify: `frontend/src/pages/ThucHienSxPage.tsx` (state + gọi API + `eventTick`)
- Modify: `frontend/src/pages/KhoYeuCauPage.tsx` — màn "Hộp yêu cầu kho"; đã có cột Bộ phận
  (`bo_phan_ten`) và "Cần ngày" (`ngay_can`), cần thêm **công đoạn** và **giờ**

- [ ] **Step 1: Bỏ `if (vt.length === 0) return null`** tại
  [ThsxExecPanels.tsx:773](../../../frontend/src/pages/ThsxExecPanels.tsx:773) — khối Vật tư LUÔN
  hiện, kể cả chưa có phiếu nào.
- [ ] **Step 2: Bảng đối chiếu** `Kế hoạch | Tổ trưởng yêu cầu | Kho thực xuất | Chênh lệch | Lý do`.
- [ ] **Step 3: Hành động theo trạng thái** — `Yêu cầu cấp vật tư` / `Sửa đề nghị` / `Yêu cầu bổ
  sung`; `Xác nhận nhận` giữ nguyên hành vi cũ.
- [ ] **Step 4: Form ngay trong drawer công đoạn** — tự điền vật tư + giờ bắt đầu dự kiến, cho tìm
  thêm giấy/vật tư từ danh mục chung, chỉ mở ô lý do khi có chênh lệch.
- [ ] **Step 5: Màn kho** hiện tổ, công đoạn, giờ cần; KHÔNG hiện quy trình duyệt, KHÔNG bắt kho đọc
  lý do nghiệp vụ của tổ. ⚠️ **`stock_requests.ngay_can` là kiểu `Date`, không có giờ**
  ([stock_request.py:90](../../../backend/app/models/stock_request.py:90)). "Giờ cần" phải đọc
  `can_luc` của đề nghị SX qua liên kết `sx_cong_viec_id` — KHÔNG thêm cột giờ vào `stock_requests`
  (kho không có nghiệp vụ nào cần giờ ngoài ca này).
- [ ] **Step 6: Quy trình hai agent cho UI** — agent soi–thiết kế trước, agent build riêng; sau build
  kiểm bằng dev-browser và styleseed.

---

### Task 22: Nghiệm thu Phần B qua dev-browser thật

**Files:** không sửa code.

- [ ] **Step 1: Restart uvicorn** (đổi route/schema) + FE dev server.
- [ ] **Step 2:** Đăng nhập bằng tài khoản **tổ trưởng** (không phải admin) để kiểm gate thật.
- [ ] **Step 3:** Mở một công đoạn → khối Vật tư → `Yêu cầu cấp vật tư`: xác nhận tự điền đúng giấy +
  vật tư của công đoạn (LSX và bài ghép kiểm riêng hai ca).
- [ ] **Step 4:** Sửa một dòng lệch kế hoạch mà KHÔNG nhập lý do ⇒ phải bị chặn; nhập lý do ⇒ lưu được.
- [ ] **Step 5:** Đặt toàn bộ về `0`, lưu ⇒ mở màn Kho xác nhận **không** có yêu cầu nào mới.
- [ ] **Step 6:** Tạo đề nghị dương ⇒ màn Kho thấy ngay (không F5). Sửa lại khi kho chưa lập phiếu ⇒
  kho tải lại thấy số mới. Kho lập phiếu ⇒ quay lại công đoạn, nút đã đổi sang `Yêu cầu bổ sung`.
- [ ] **Step 7:** Mở một công đoạn KHÁC cùng LSX ⇒ phiếu của công đoạn trên không xuất hiện nhầm.
- [ ] **Step 8:** Kho điều chỉnh phiếu `100 → 70` ⇒ tồn lô `+30`, đề nghị đóng ở thực xuất `70`,
  không báo còn thiếu.
- [ ] **Step 9: Báo cáo** liệt kê cụ thể đã bấm gì / gõ gì / thấy gì ở từng bước. Nếu có đoạn nào
  phải tắt qua API, khai rõ ngay trong báo cáo.
