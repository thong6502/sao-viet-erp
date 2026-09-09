# NVL chính chọn tay trên bước — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ hẳn cơ chế hệ tự suy "lệnh này ăn giấy gì, ở bước nào"; thay bằng người lập lệnh tự chọn NVL chính từ danh mục Giấy và đặt vào đúng bước tiêu thụ, trong chính khối vật tư của bước.

**Architecture:** `lsx_cong_doan_vat_tu` đổi từ "chỉ trỏ `vat_tu_in_an`" sang cặp `(hang_loai, hang_id)` — đúng khuôn mà `stock_lots` / `vat_tu_giu_cho` / `stock_requests` / `san_xuat_vat_tu_de_nghi_dong` đã dùng sẵn, nên toàn bộ hạ nguồn (giữ chỗ, đề nghị cấp, phiếu kho) không phải sửa. Lượng của dòng giấy suy bằng **công thức lượng của chính loại giấy đó** (`giay_nguyen.cong_thuc_luong`), chạy trên ngữ cảnh bước (đã có sẵn `dai_nguyen`/`rong_nguyen`/`dinh_luong`/`to_nguyen` + `sl_vao`/`sl_ra`/`so_luot_chay`) và ghi ra **đơn vị gốc của giấy** (kg). Đường cũ `quy_cach_json.giay_id + so_to_nguyen` bị **cắt hẳn** ở lệnh — giữ nguyên ở BÀI GHÉP.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (Postgres dev/prod, SQLite in-memory cho test), React + TypeScript + Vite, pytest, vitest.

**Spec:** Quyết định thiết kế chốt trong hội thoại 08/09/2026, ghi lại nguyên văn ở mục "Bối cảnh & quyết định" ngay dưới. Spec nền còn hiệu lực: `docs/spec-ke-hoach-vat-tu.md` (bảng cân đối), `backend/app/services/dong_giay.py` (5 chặng dòng giấy).

## Bối cảnh & quyết định

Hiện tại, ở tab **Vật tư** của một lệnh, dòng `Giấy C300 · NVL chính · 553 tờ nguyên` không do ai chọn. Nó là **dòng ảo**: FE lấy `quy_cach_json.giay_id` rồi `buocSap.find(c => c.tren_dong_giay)` để chọn bước treo lên; BE làm y hệt bằng `_buoc_dau_dong_giay`. Không ai bấm, không sửa được, không xoá được, không thêm loại thứ hai được.

Chủ dự án chốt (nguyên văn):

> "bỏ logic suy giấy từ công đoạn — thêm logic được chọn nguyên vật liệu chính từ danh mục giấy"

và, về việc mồi sẵn một dòng giấy lúc tạo lệnh:

> "bỏ, nó nằm ngoài ý của tôi"

Nên: **lệnh mới tạo ra KHÔNG có dòng giấy nào.** Người lập lệnh tự chọn.

Đường cũ bị cắt dứt, không chạy song song — giữ cả hai là một nhu cầu bị đếm hai lần.

BÀI GHÉP giữ nguyên `bai_ghep.giay_id`: giấy in của một lượt chạy chung thuộc về BÀI, không thuộc lệnh nào. Bước bị bài buộc chung vốn đã bị loại khỏi vòng vật tư của lệnh (`bi_buoc_chung_de`), nên hai đường không đụng nhau và không cần luật mới.

## Global Constraints

- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, KHÔNG ALTER. Thêm/đổi cột phải viết vào `backend/app/db_migrations.py`. Dev cũng là Postgres.
- Migration **cấm ORM full-select** — backfill phải raw SQL đích danh cột.
- Cột Boolean: `server_default` phải là `false()`/`true()` (Python bool), KHÔNG phải `"0"`/`"1"`.
- `docs/DB_SCHEMA.md` có **guard test**: mọi bảng/cột trong model phải được ghi vào đó. Thêm cột → cập nhật DB_SCHEMA.md **cùng lượt**.
- **KHÔNG chạy `./init.ps1`** (chủ dự án cấm). Verify bằng `pytest` nhắm đúng file + `npx tsc --noEmit` / `npx vitest run <file>`.
- **KHÔNG chạy pytest full cục bộ trước push** — để CI GitHub chạy.
- `python -c` trần trong `backend/` đụng **DB dev thật** — muốn thăm dò phải viết test tạm rồi chạy qua pytest.
- Danh mục là **ĐỘNG** — cấm hardcode tên/mã món trong engine.
- Sửa route/schema backend → **RESTART uvicorn** (không hot-reload đáng tin).
- Commit message tiếng Việt (thuật ngữ kỹ thuật giữ tiếng Anh), **không** `Co-Authored-By`.
- Luồng nghiệp vụ có UI → phải thao tác lại bằng chuột/bàn phím thật trên dev-browser trước khi báo xong; KHÔNG dùng API/curl thay bất kỳ bước nào.

## File Structure

**Backend — model & schema**
- `backend/app/models/lsx.py` — `LsxCongDoanVatTu` thêm `hang_loai`; đổi `UniqueConstraint`.
- `backend/app/db_migrations.py` — migration `0280`: thêm cột + đổi unique constraint.
- `docs/DB_SCHEMA.md` — mục `lsx_cong_doan_vat_tu`.
- `backend/app/schemas/lsx.py` — `LsxBuocVatTuIn` / `LsxBuocVatTuOut` mang `hang_loai`.

**Backend — engine lệnh** (`backend/app/services/lsx_service.py`)
- `_mon_active()` (mới, thay chỗ dùng của `_vat_tu_active`) — gộp Giấy + Vật tư thành `{(hang_loai, id): obj}`.
- `_luong_vat_tu` — thêm nhánh nguồn công thức cho giấy.
- `_goi_y_luong_vat_tu` — gợi ý cho cả hai loại, khoá `(hang_loai, id)`.
- `_vat_tu_bung`, `_bung_vat_tu_dau_viec` — ghi `hang_loai="vat_tu"`.
- `replace_routing` — nhận + kiểm `hang_loai`.
- `_soi_danh_muc` / `dong_bo_danh_muc` + `backend/app/services/lsx_danh_muc_doi.py::vat_tu_lech` — khoá theo cặp.

**Backend — bảng cân đối** (`backend/app/services/ke_hoach_vat_tu_service.py`)
- Gỡ vòng sinh dòng giấy từ `quy_cach_json.giay_id` cho LỆNH; gỡ `_buoc_dau_dong_giay`.
- `_dong_lenh` cho dòng vật tư bước → truyền `(vt.hang_loai, vt.vat_tu_id)`.
- `_ve_goc` — cờ chạy công thức mặt hàng đổi từ "là giấy" sang "dòng đến từ đường tổng-lệnh" (chỉ còn BÀI GHÉP).

**Frontend**
- `frontend/src/api/client.ts` — kiểu `vat_tus` + `vat_tu_goi_y` mang `hang_loai`.
- `frontend/src/pages/lsxVatTu.ts` — gỡ suy `buocGiay`; phân nhóm theo `hang_loai`.
- `frontend/src/pages/LsxBuocDrawer.tsx` — dropdown hai nhóm (Giấy · Vật tư), payload mang `hang_loai`.
- `frontend/src/pages/LsxDetailView.tsx` — nạp thêm danh mục Giấy.

**Tests**
- `backend/tests/test_lsx_service.py` — chọn giấy ở bước, ra kg.
- `backend/tests/test_ke_hoach_vat_tu.py` — helper `_lenh` đổi seam; test giấy-theo-bước.
- `backend/tests/test_giu_cho_vat_tu.py`, `test_lenh_sx_ho_so.py`, `test_sx_vat_tu_de_nghi.py` — dựng `LsxCongDoanVatTu` thêm `hang_loai`.
- `frontend/src/pages/lsxVatTu.test.ts` — viết lại 3 test giấy.

---

### Task 1: Cột `hang_loai` trên dòng vật tư của bước

Nền cho mọi task sau. Sau task này DB nhận được dòng giấy, nhưng chưa ai ghi.

**Files:**
- Modify: `backend/app/models/lsx.py` (class `LsxCongDoanVatTu`)
- Modify: `backend/app/db_migrations.py` (cuối file)
- Modify: `docs/DB_SCHEMA.md:4003-4009`
- Test: `backend/tests/test_lsx_service.py`

**Interfaces:**
- Produces: `LsxCongDoanVatTu.hang_loai: str` — `"giay"` | `"vat_tu"`, NOT NULL, server_default `'vat_tu'`. Cột id giữ nguyên tên `vat_tu_id` (nay mang nghĩa `hang_id`). Unique key mới: `(lsx_cong_doan_id, hang_loai, vat_tu_id)`.

- [x] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_lsx_service.py`:

```python
def test_dong_vat_tu_cua_buoc_mang_hang_loai_va_cho_trung_id_khac_loai(db):
    """Giấy #7 và Vật tư #7 là HAI món khác nhau — unique key phải gồm cả `hang_loai`."""
    from app.models.lsx import LsxCongDoanVatTu

    assert LsxCongDoanVatTu.hang_loai is not None
    cols = {c.name for c in LsxCongDoanVatTu.__table__.columns}
    assert "hang_loai" in cols
    uq = next(c for c in LsxCongDoanVatTu.__table__.constraints
              if getattr(c, "name", "") == "uq_lsx_buoc_vat_tu")
    assert [c.name for c in uq.columns] == ["lsx_cong_doan_id", "hang_loai", "vat_tu_id"]
```

- [x] **Step 2: Chạy test cho chắc nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_lsx_service.py::test_dong_vat_tu_cua_buoc_mang_hang_loai_va_cho_trung_id_khac_loai -q
```

Kỳ vọng: FAIL — `AttributeError: type object 'LsxCongDoanVatTu' has no attribute 'hang_loai'`.

- [x] **Step 3: Thêm cột vào model**

Trong `backend/app/models/lsx.py`, class `LsxCongDoanVatTu`, đổi `__table_args__` và thêm cột ngay trên `vat_tu_id`:

```python
class LsxCongDoanVatTu(Base):
    __tablename__ = "lsx_cong_doan_vat_tu"
    __table_args__ = (
        UniqueConstraint("lsx_cong_doan_id", "hang_loai", "vat_tu_id",
                         name="uq_lsx_buoc_vat_tu"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lsx_cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx_cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # LOẠI MẶT HÀNG của dòng — `"giay"` (danh mục Giấy) hay `"vat_tu"` (danh mục Vật tư khác).
    # Cặp `(hang_loai, vat_tu_id)` là cùng khuôn `stock_lots` / `vat_tu_giu_cho` / `stock_requests`
    # đã dùng, nên bảng cân đối và mọi tầng kho hạ nguồn nhận dòng giấy mà không phải rẽ nhánh.
    #
    # Vì sao KHÔNG đổi tên cột `vat_tu_id` thành `hang_id`: nó là khoá đọc ở 8 file + 5 file test,
    # đổi tên chỉ để cho đẹp là một lượt sửa rộng không đổi hành vi. Đọc nó là `hang_id`.
    hang_loai: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="vat_tu", default="vat_tu", index=True
    )
    vat_tu_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
```

- [x] **Step 4: Viết migration `0280`**

Thêm vào **cuối** `backend/app/db_migrations.py`:

```python
def _migrate_hang_loai_vat_tu_buoc(db: Session) -> None:
    """`lsx_cong_doan_vat_tu.hang_loai` — bước chọn được NVL chính từ danh mục GIẤY (08/09/2026).

    Trước đây bảng chỉ trỏ `vat_tu_in_an`, còn giấy đi một đường riêng suy từ `quy_cach_json.giay_id`
    rồi tự treo lên "bước đầu tiên chạm tờ". Đường suy đó đã gỡ: người lập lệnh tự chọn giấy và tự
    đặt vào bước ăn nó, nên dòng của bước phải phân biệt được hai danh mục.

    Cặp `(hang_loai, hang_id)` là khuôn có sẵn ở `stock_lots` / `vat_tu_giu_cho` / `stock_requests`
    / `san_xuat_vat_tu_de_nghi_dong` — dùng lại để hạ nguồn (giữ chỗ, đề nghị cấp, phiếu kho) nhận
    dòng giấy mà không phải sửa gì.

    Dòng CŨ đều là vật tư ⇒ backfill `'vat_tu'` bằng chính `server_default`. Unique key phải nới ra
    ba cột: Giấy #7 và Vật tư #7 là hai món khác nhau, khoá hai cột sẽ chặn nhầm.

    Raw SQL đích danh cột, KHÔNG ORM full-select. No-op khi bảng chưa có / cột đã có.
    """
    insp = inspect(db.get_bind())
    if "lsx_cong_doan_vat_tu" not in set(insp.get_table_names()):
        return
    if "hang_loai" in _existing_columns(insp, "lsx_cong_doan_vat_tu"):
        return
    db.execute(text(
        "ALTER TABLE lsx_cong_doan_vat_tu "
        "ADD COLUMN hang_loai VARCHAR(8) NOT NULL DEFAULT 'vat_tu'"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_lsx_cong_doan_vat_tu_hang_loai "
        "ON lsx_cong_doan_vat_tu (hang_loai)"
    ))
    # Unique key nới từ 2 → 3 cột. Tên ràng buộc giữ nguyên để model và DB không lệch tên.
    # Postgres: DROP rồi ADD. SQLite không ALTER được constraint — nhưng test dựng bảng bằng
    # `create_all` từ model (đã mang khoá mới) nên nhánh này chỉ chạy trên Postgres.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text(
            "ALTER TABLE lsx_cong_doan_vat_tu DROP CONSTRAINT IF EXISTS uq_lsx_buoc_vat_tu"
        ))
        db.execute(text(
            "ALTER TABLE lsx_cong_doan_vat_tu ADD CONSTRAINT uq_lsx_buoc_vat_tu "
            "UNIQUE (lsx_cong_doan_id, hang_loai, vat_tu_id)"
        ))
    db.commit()


MIGRATIONS.append(("0280_hang_loai_vat_tu_buoc", _migrate_hang_loai_vat_tu_buoc))
```

- [x] **Step 5: Cập nhật `docs/DB_SCHEMA.md`**

Trong mục `### \`lsx_cong_doan_vat_tu\`` (khoảng dòng 4003), sửa dòng "Tất cả cột" và thêm một đoạn giải thích ngay dưới:

```markdown
**Tất cả cột:** `id`, `lsx_cong_doan_id`, `hang_loai`, `vat_tu_id`, `vat_tu_ma_snapshot`, `vat_tu_ten_snapshot`, `don_vi_snapshot`, `so_luong`, `thu_tu`, `tu_dong`.

`hang_loai` (VARCHAR(8) NOT NULL DEFAULT `'vat_tu'`, IX, mg `0280`): **danh mục nào chứa món này** — `'giay'` → `giay_nguyen`, `'vat_tu'` → `vat_tu_in_an`. Cặp `(hang_loai, vat_tu_id)` cùng khuôn `stock_lots` / `vat_tu_giu_cho` / `stock_requests`, nên bảng cân đối và tầng kho nhận dòng giấy không phải rẽ nhánh. Cột id vẫn tên `vat_tu_id` nhưng **đọc là `hang_id`**. Unique key gồm cả ba cột: Giấy #7 và Vật tư #7 là hai món khác nhau.
```

- [x] **Step 6: Chạy test cho XANH**

```bash
cd backend && python -m pytest tests/test_lsx_service.py::test_dong_vat_tu_cua_buoc_mang_hang_loai_va_cho_trung_id_khac_loai -q
```

Kỳ vọng: PASS.

- [x] **Step 7: Commit**

```bash
git add backend/app/models/lsx.py backend/app/db_migrations.py docs/DB_SCHEMA.md backend/tests/test_lsx_service.py
git commit -m "Them cot hang_loai cho dong vat tu cua buoc lenh (mg 0280)"
```

---

### Task 2: Engine lệnh nhận danh mục Giấy — gợi ý lượng ra kg

Sau task này, server tính được số kg cho một dòng giấy đặt ở bước, nhưng client chưa gửi được.

**Files:**
- Modify: `backend/app/services/lsx_service.py` (`_vat_tu_active` :480, `_vat_tu_bung` :602, `_goi_y_luong_vat_tu` :654, `_luong_vat_tu` :715)
- Test: `backend/tests/test_lsx_service.py`

**Interfaces:**
- Consumes: `LsxCongDoanVatTu.hang_loai` (Task 1).
- Produces:
  - `LsxService._mon_active() -> dict[tuple[str, int], object]` — `{("giay", id): GiayNguyen, ("vat_tu", id): VatTuInAn}`, chỉ món `active`.
  - `_luong_vat_tu(dvt, ctx, *, mat=None, cong_thuc="", hang_loai="vat_tu")` — giấy dùng `mat.cong_thuc_luong` khi `cong_thuc` rỗng.
  - `_goi_y_luong_vat_tu` trả thêm khoá `"hang_loai"` mỗi phần tử.
  - `_vat_tu_bung` trả thêm khoá `"hang_loai": "vat_tu"` mỗi dòng.

- [x] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_lsx_service.py`:

```python
def test_goi_y_luong_co_ca_GIAY_va_ra_kg_bang_cong_thuc_cua_chinh_loai_giay(db, svc_lsx_lenh):
    """Giấy chọn tay ở bước ⇒ lượng suy bằng `giay_nguyen.cong_thuc_luong`, ra ĐƠN VỊ GỐC (kg).

    Không có đầu việc nào khai giấy — đó chính là ca thật: giấy tuỳ từng đơn, không khai ở danh mục
    công đoạn được. Nên nguồn công thức phải là CHÍNH MÓN GIẤY, khác hẳn mực (khai ở đầu việc).
    """
    from app.models.vat_lieu_kho import GiayNguyen

    lsx, buoc = svc_lsx_lenh          # lệnh 1 bước, quy cách mang khổ nguyên + gsm + to_nguyen
    g = GiayNguyen(
        ma="GY-C300", ten="Giấy C300", gsm=300, kho_dai=860, kho_rong=650, don_vi_gia="kg",
        cong_thuc_luong="dinh_luong * dai_nguyen * rong_nguyen * to_nguyen",
    )
    db.add(g)
    db.commit()

    svc = LsxService(db)
    goi_y = svc._goi_y_luong_vat_tu(buoc, quy_cach_bien(lsx))
    dong = next(x for x in goi_y if x["hang_loai"] == "giay" and x["vat_tu_id"] == g.id)

    # 0,3 × 0,86 × 0,65 × 553 tờ nguyên = 92,73 kg
    assert dong["so_luong"] == pytest.approx(92.73, abs=0.01)
    assert dong["ly_do"] is None
```

Fixture `svc_lsx_lenh` (thêm cùng file, ngay trên test):

```python
@pytest.fixture()
def svc_lsx_lenh(db, customer):
    """Lệnh tối thiểu: 1 bước in, quy cách đủ khổ nguyên + định lượng + số tờ nguyên."""
    from app.models.lsx import Lsx, LsxCongDoan, TT_SAN_SANG

    l = Lsx(ma="LSX-GIAY", ten="LSX-GIAY", so_luong_dat=2000, so_to_nguyen=553, so_con=9,
            trang_thai=TT_SAN_SANG,
            quy_cach_json={"kho_nguyen_dai": 860, "kho_nguyen_rong": 650, "gsm": 300})
    db.add(l)
    db.flush()
    b = LsxCongDoan(lsx_id=l.id, thu_tu=1, ten="In offset", loai_buoc="may",
                    don_vi_vao="to_nguyen", don_vi_ra="to",
                    so_luong_vao=553, so_luong_ra=553)
    db.add(b)
    db.commit()
    return l, b
```

- [x] **Step 2: Chạy test cho chắc nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_lsx_service.py::test_goi_y_luong_co_ca_GIAY_va_ra_kg_bang_cong_thuc_cua_chinh_loai_giay -q
```

Kỳ vọng: FAIL — `StopIteration` (gợi ý không có dòng nào `hang_loai == "giay"`).

- [x] **Step 3: Thay `_vat_tu_active` bằng `_mon_active`**

Trong `backend/app/services/lsx_service.py`, thay nguyên hàm `_vat_tu_active` (dòng 480–491):

```python
    def _mon_active(self) -> dict[tuple[str, int], object]:
        """Mọi MÓN đang dùng, khoá `(hang_loai, id)` — CACHE theo service.

        GỘP hai danh mục (08/09/2026): từ khi bước chọn được NVL chính, khối vật tư của bước ăn cả
        `giay_nguyen` lẫn `vat_tu_in_an`. Hỏi rời hai bảng ở ba nơi (`_vat_tu_bung`,
        `_goi_y_luong_vat_tu`, `_soi_danh_muc`) cho MỖI bước là đúng bài N+1 đã dính một lần ở màn
        đơn hàng — cả hai bảng đều vài chục dòng nên nạp trọn một lượt rẻ hơn hẳn.
        """
        if self._mon_cache is None:
            ra: dict[tuple[str, int], object] = {}
            for m in self.db.execute(
                    select(VatTuInAn).where(VatTuInAn.active.is_(True))).scalars():
                ra[(HANG_VAT_TU, m.id)] = m
            for g in self.db.execute(
                    select(GiayNguyen).where(GiayNguyen.active.is_(True))).scalars():
                ra[(HANG_GIAY, g.id)] = g
            self._mon_cache = ra
        return self._mon_cache

    def _vat_tu_active(self) -> list:
        """Chỉ VẬT TƯ KHÁC — đường của đầu việc, vốn không bao giờ khai giấy."""
        return [m for (hl, _i), m in self._mon_active().items() if hl == HANG_VAT_TU]
```

Đổi khởi tạo cache ở `__init__` (dòng 466):

```python
        self._mon_cache: dict[tuple[str, int], object] | None = None
```

Thêm import ở đầu file, cạnh import `VatTuInAn` đang có:

```python
from ..models.vat_lieu_kho import HANG_GIAY, HANG_VAT_TU, GiayNguyen, VatTuInAn
```

- [x] **Step 4: Cho `_luong_vat_tu` biết nguồn công thức của giấy**

Sửa chữ ký và đoạn đầu của `_luong_vat_tu` (dòng 715):

```python
    def _luong_vat_tu(self, dvt: str, ctx: dict, *, mat=None, cong_thuc: str = "",
                      hang_loai: str = HANG_VAT_TU) -> tuple[float | None, str | None, str]:
```

Ngay dưới `rieng = (cong_thuc or "").strip()`, chèn:

```python
        # GIẤY (08/09/2026): công thức nằm ở CHÍNH MÓN (`giay_nguyen.cong_thuc_luong`), không ở
        # đầu việc. Giấy tuỳ TỪNG ĐƠN — "chạy sóng" hôm nay ăn kraft, mai ăn duplex — nên không
        # khai trước ở danh mục công đoạn được. Đây là lý do đúng để món tự mang công thức, khác
        # hẳn mực: cùng "Mực Cyan" mà hai khổ in ăn hai định mức, nên mực phải khai theo đầu việc.
        if not rieng and hang_loai == HANG_GIAY:
            rieng = (getattr(mat, "cong_thuc_luong", None) or "").strip()
```

Và đổi câu lý do khi vẫn rỗng, để nó chỉ đúng chỗ khai của từng loại:

```python
        if not rieng:
            if hang_loai == HANG_GIAY:
                return None, None, (
                    f"chưa khai công thức định mức. Mở danh mục Giấy → sửa “{ten}” → điền ô "
                    f"“Công thức tính lượng” (ra {dv_ten}).")
            return None, None, (
                f"chưa khai công thức định mức. Mở danh mục Công đoạn → sửa công đoạn → bảng "
                f"“Đầu việc và định mức của tổ” → bấm dòng “{ten}” trong khối vật tư → điền ô "
                f"“Công thức định mức” (ra {dv_ten}).")
```

- [x] **Step 5: `_goi_y_luong_vat_tu` quét cả hai danh mục**

Trong `_goi_y_luong_vat_tu` (dòng 654), thay vòng lặp cuối:

```python
        ra: list[dict] = []
        for (hang_loai, mon_id), mat in self._mon_active().items():
            dvt = (mat.don_vi_gia or "").strip()
            if not dvt:
                continue
            so_luong, dien_giai, ly_do = self._luong_vat_tu(
                dvt, ctx, mat=mat,
                cong_thuc=("" if hang_loai == HANG_GIAY else ct_theo_mon.get(mon_id, "")),
                hang_loai=hang_loai)
            ra.append({
                "hang_loai": hang_loai,
                "vat_tu_id": mon_id,
                "so_luong": None if so_luong is None else round(so_luong, 3),
                "dien_giai": dien_giai,
                "ly_do": ly_do or None,
            })
        return ra
```

- [x] **Step 6: `_vat_tu_bung` đóng dấu `hang_loai`**

Trong `_vat_tu_bung` (dòng 602), dòng `ra.append({...})` thêm khoá đầu:

```python
            ra.append({
                "hang_loai": HANG_VAT_TU,
                "vat_tu_id": mat.id, "ma": mat.ma, "ten": mat.ten, "don_vi": dvt,
                "so_luong": round(so_luong, 3), "dien_giai": dien_giai,
            })
```

- [x] **Step 7: Chạy test cho XANH**

```bash
cd backend && python -m pytest tests/test_lsx_service.py -q -k "goi_y_luong or vat_tu"
```

Kỳ vọng: PASS toàn bộ.

- [x] **Step 8: Commit**

```bash
git add backend/app/services/lsx_service.py backend/tests/test_lsx_service.py
git commit -m "Engine lenh nhan danh muc Giay: goi y luong NVL chinh ra kg theo cong thuc cua chinh loai giay"
```

---

### Task 3: Lưu routing ghi được dòng giấy

Sau task này, API nhận `hang_loai` và ghi đúng bảng; FE chưa gửi.

**Files:**
- Modify: `backend/app/schemas/lsx.py:110-126`
- Modify: `backend/app/services/lsx_service.py` (`replace_routing` khối `vat_tus` :3271-3310, `_buoc_dict` :2486-2494, `_bung_vat_tu_dau_viec` :1550-1580)
- Modify: `backend/app/services/lsx_danh_muc_doi.py` (`vat_tu_lech`)
- Modify: `backend/app/services/lsx_service.py` (`_soi_danh_muc` :3008-3020, `dong_bo_danh_muc` :3076-3086)
- Test: `backend/tests/test_lsx_service.py`

**Interfaces:**
- Consumes: `_mon_active()`, `_luong_vat_tu(..., hang_loai=)` (Task 2).
- Produces: `LsxBuocVatTuIn.hang_loai: str = "vat_tu"`, `LsxBuocVatTuOut.hang_loai: str`. `vat_tu_lech` khoá theo `(hang_loai, vat_tu_id)`.

- [x] **Step 1: Viết test thất bại**

```python
def test_luu_routing_ghi_duoc_dong_GIAY_va_giu_qua_lan_luu_thu_hai(db, svc_lsx_lenh):
    """Giấy chọn tay là dòng NGƯỜI KHAI — lưu lại lần hai không được làm mất nó."""
    from app.models.lsx import LsxCongDoanVatTu
    from app.models.vat_lieu_kho import GiayNguyen

    lsx, buoc = svc_lsx_lenh
    g = GiayNguyen(ma="GY-C300", ten="Giấy C300", gsm=300, kho_dai=860, kho_rong=650,
                   don_vi_gia="kg",
                   cong_thuc_luong="dinh_luong * dai_nguyen * rong_nguyen * to_nguyen")
    db.add(g)
    db.commit()

    svc = LsxService(db)
    payload = [{
        "step_key": buoc.step_key, "cong_doan_id": buoc.cong_doan_id, "ten": buoc.ten,
        "vat_tus": [{"hang_loai": "giay", "vat_tu_id": g.id, "so_luong": 92.73,
                     "tu_dong": False}],
    }]
    svc.replace_routing(lsx_id=lsx.id, payloads=payload, actor=None)
    svc.replace_routing(lsx_id=lsx.id, payloads=payload, actor=None)

    rows = db.query(LsxCongDoanVatTu).filter_by(lsx_cong_doan_id=buoc.id).all()
    assert len(rows) == 1
    assert (rows[0].hang_loai, rows[0].vat_tu_id) == ("giay", g.id)
    assert rows[0].don_vi_snapshot == "kg"
    assert rows[0].vat_tu_ten_snapshot == "Giấy C300"
```

- [x] **Step 2: Chạy test cho chắc nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_lsx_service.py::test_luu_routing_ghi_duoc_dong_GIAY_va_giu_qua_lan_luu_thu_hai -q
```

Kỳ vọng: FAIL — `LsxValidationError: Vật tư không tồn tại` (id giấy tra trong `vat_tu_in_an`).

- [x] **Step 3: Schema nhận `hang_loai`**

Trong `backend/app/schemas/lsx.py`:

```python
class LsxBuocVatTuIn(BaseModel):
    # Danh mục nào chứa món — `"giay"` (NVL chính, chọn tay) hay `"vat_tu"` (mực/keo/màng).
    # Mặc định `"vat_tu"`: client cũ không gửi thì hiểu như trước khi có NVL chính.
    hang_loai: Literal["giay", "vat_tu"] = "vat_tu"
    vat_tu_id: int
    so_luong: float = Field(gt=0)
    # True = dòng MÁY bung khi chọn công việc khoán ⇒ lần bung sau thay được. False = người tự thêm
    # hoặc đã sửa số ⇒ máy chừa ra. Mặc định False: client cũ không gửi thì coi như người khai.
    tu_dong: bool = False


class LsxBuocVatTuOut(BaseModel):
    id: int
    hang_loai: str = "vat_tu"
    vat_tu_id: int
    vat_tu_ma: str
    vat_tu_ten: str
    don_vi: str
    so_luong: float
    tu_dong: bool = False
```

- [x] **Step 4: `replace_routing` tra đúng danh mục**

Trong `backend/app/services/lsx_service.py`, thay khối kiểm + ghi `vat_tus` (dòng 3274–3310):

```python
            vat_tus = d.get("vat_tus") or []
            caps = [(str(v.get("hang_loai") or HANG_VAT_TU), int(v.get("vat_tu_id") or 0))
                    for v in vat_tus]
            if len(caps) != len(set(caps)):
                raise LsxValidationError("Một vật tư không được chọn trùng trong cùng công đoạn")
            # Món ĐÃ nằm trên bước từ trước — giữ lại được kể cả khi danh mục đã ngừng nó. Chặn cả
            # hai kiểu như trước thì một lệnh cũ có vật tư ngừng dùng là KHÔNG LƯU LẠI ĐƯỢC routing
            # nữa, kể cả khi người ta chỉ sửa cái khác.
            dang_co = {(v.hang_loai, int(v.vat_tu_id)) for v in row.vat_tus if v.vat_tu_id}
            mons = self._mon_active()
            thieu = [c for c in caps if c not in mons and c not in dang_co]
            if thieu:
                raise LsxValidationError("Vật tư không tồn tại hoặc đã ngừng dùng")
            row.vat_tus.clear()
            # FLUSH giữa xoá và thêm: bảng có UNIQUE (lsx_cong_doan_id, hang_loai, vat_tu_id), mà
            # lưu lại bước với ĐÚNG món cũ là xoá rồi thêm lại chính cặp đó. Không ép DELETE chạy
            # trước thì SQLAlchemy gộp một lượt và INSERT đụng hàng chưa kịp xoá → 500 ngay khi bấm
            # Lưu lần thứ hai mà không đổi gì.
            self.db.flush()
            cu_theo_cap = {(v.hang_loai, int(v.vat_tu_id)): v for v in row.vat_tus}
            for pos, (item, cap) in enumerate(zip(vat_tus, caps)):
                mon = mons.get(cap) or cu_theo_cap.get(cap)
                row.vat_tus.append(LsxCongDoanVatTu(
                    hang_loai=cap[0],
                    vat_tu_id=cap[1],
                    # `or ""`: đơn vị gốc có thể CHƯA KHAI (nullable từ 2026-08-08) còn cột
                    # snapshot NOT NULL — không chặn thì IntegrityError 500.
                    vat_tu_ma_snapshot=getattr(mon, "ma", "") or "",
                    vat_tu_ten_snapshot=getattr(mon, "ten", "") or "",
                    don_vi_snapshot=getattr(mon, "don_vi_gia", "") or "",
                    so_luong=float(item["so_luong"]), thu_tu=pos,
                    # Cờ MÁY BUNG / NGƯỜI KHAI đi theo từng dòng: lần bung sau chỉ thay dòng máy,
                    # dòng người đã sửa thì chừa ra. Client cũ không gửi ⇒ False = người khai.
                    tu_dong=bool(item.get("tu_dong")),
                ))
```

> ⚠️ `cu_theo_cap` phải dựng **trước** `row.vat_tus.clear()`. Đưa dòng đó lên ngay trên `row.vat_tus.clear()`.

- [x] **Step 5: Đường đọc trả `hang_loai`**

Trong `_buoc_dict` (dòng 2486), thêm khoá:

```python
            "vat_tus": [
                {"id": v.id, "hang_loai": v.hang_loai, "vat_tu_id": v.vat_tu_id,
                 "vat_tu_ma": v.vat_tu_ma_snapshot, "vat_tu_ten": v.vat_tu_ten_snapshot,
                 "don_vi": v.don_vi_snapshot, "so_luong": _f(v.so_luong),
                 "tu_dong": bool(v.tu_dong)}
                for v in cd.vat_tus
            ],
```

Trong `_bung_vat_tu_dau_viec` (dòng 1574) và `dong_bo_danh_muc` (dòng 3083), thêm `hang_loai=v.get("hang_loai") or HANG_VAT_TU` / `hang_loai=r.get("hang_loai") or HANG_VAT_TU` vào `LsxCongDoanVatTu(...)`.

- [x] **Step 6: `vat_tu_lech` khoá theo cặp**

Trong `backend/app/services/lsx_danh_muc_doi.py`, đổi hai dict khoá:

```python
    # Khoá theo CẶP `(hang_loai, id)` (08/09/2026): bước nay ăn cả giấy lẫn vật tư, mà Giấy #7 và
    # Vật tư #7 là hai món khác nhau. Khoá bằng id trần thì "cập nhật theo danh mục" đè số của
    # dòng giấy bằng số của một món mực trùng id.
    def _cap(v: dict) -> tuple[str, int]:
        return (str(v.get("hang_loai") or "vat_tu"), int(v["vat_tu_id"]))

    cu_theo_id = {_cap(v): v for v in hien_co if v.get("vat_tu_id")}
    moi_theo_id = {_cap(v): v for v in theo_danh_muc if v.get("vat_tu_id")}
```

Trong `_soi_danh_muc` (dòng 3010) và `dong_bo_danh_muc` (dòng 3076), đổi khoá `moi_theo_id` / `dat_lai` sang cặp tương ứng:

```python
                hien_co = [
                    {"hang_loai": v.hang_loai, "vat_tu_id": v.vat_tu_id, "ma": v.vat_tu_ma_snapshot,
                     "ten": v.vat_tu_ten_snapshot, "don_vi": v.don_vi_snapshot,
                     "so_luong": _f(v.so_luong), "tu_dong": bool(v.tu_dong)}
                    for v in cd.vat_tus
                ]
```

```python
                moi_theo_id = {(r.get("hang_loai") or HANG_VAT_TU, int(r["vat_tu_id"])): r
                               for r in moi_rows}
```

```python
            dat_lai = {(r.get("hang_loai") or HANG_VAT_TU, int(r["vat_tu_id"])): r
                       for r in ap["vat_tu_dat_lai"]}
            for v in cd.vat_tus:
                if (r := dat_lai.get((v.hang_loai, int(v.vat_tu_id)))) is not None:
                    v.so_luong = float(r["so_luong"])
```

- [x] **Step 7: Chạy test cho XANH**

```bash
cd backend && python -m pytest tests/test_lsx_service.py -q
```

Kỳ vọng: PASS toàn bộ file.

- [x] **Step 8: Commit**

```bash
git add backend/app/schemas/lsx.py backend/app/services/lsx_service.py backend/app/services/lsx_danh_muc_doi.py backend/tests/test_lsx_service.py
git commit -m "Luu routing ghi duoc dong giay tren buoc; khoa vat tu doi sang cap (hang_loai, id)"
```

---

### Task 4: Bảng cân đối bỏ suy giấy, đọc dòng giấy của bước

Đây là task cắt đường cũ. Sau task này bảng cân đối chỉ còn biết giấy qua dòng của bước (lệnh) và `bai_ghep.giay_id` (bài).

**Files:**
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py` (`_ve_goc` :280-330, `_buoc_dau_dong_giay` :367-384, vòng giấy lệnh :960-990, `_dong_lenh`/vòng vật tư :1010-1022, `_quy_doi_dong` :1131-1145)
- Test: `backend/tests/test_ke_hoach_vat_tu.py`

**Interfaces:**
- Consumes: `LsxCongDoanVatTu.hang_loai` (Task 1), đường ghi (Task 3).
- Produces: dòng thô mang thêm khoá `"ct_mat_hang": bool` — `True` chỉ cho dòng giấy của BÀI GHÉP.

- [x] **Step 1: Viết test thất bại**

```python
def test_lenh_KHONG_con_tu_sinh_dong_giay_tu_quy_cach(db, svc, customer):
    """Đường cũ đã cắt: `quy_cach_json.giay_id` không còn đẻ nhu cầu giấy nào."""
    g = _giay(db)
    _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI, giay_o_buoc=False)
    bang = svc.can_doi()
    assert not [x for x in bang["items"] if x["hang_loai"] == "giay"]


def test_giay_chon_tay_o_BUOC_len_bang_voi_ngay_can_cua_dung_buoc_do(db, svc, customer):
    """Giấy neo vào CHÍNH bước mang nó — không phải "bước đầu tiên chạm tờ" nữa."""
    g = _giay(db)
    l = _lenh(db, customer, ma="LSX-A", giay_id=g.id, so_to_nguyen=1_000, han=MAI)
    nhom = _nhom(svc.can_doi(), g)
    assert nhom["tong_nhu_cau"] == pytest.approx(83.85, abs=0.01)   # 1.000 tờ × 0,08385 kg
```

- [x] **Step 2: Chạy test cho chắc nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_ke_hoach_vat_tu.py::test_lenh_KHONG_con_tu_sinh_dong_giay_tu_quy_cach -q
```

Kỳ vọng: FAIL — vẫn còn dòng giấy sinh từ quy cách.

- [x] **Step 3: Đổi seam của helper test**

Trong `backend/tests/test_ke_hoach_vat_tu.py`, sửa `_lenh` để nó gắn dòng giấy lên bước — đây là chỗ ~40 test hiện có đi qua, đổi một nơi là cả file theo:

```python
def _lenh(db, customer, *, ma, giay_id, so_to_nguyen, han=None, nguon_giay=None,
          buoc=True, giay_o_buoc=True) -> Lsx:
    """Lệnh test. `giay_o_buoc=True` gắn dòng GIẤY lên bước — đường DUY NHẤT từ 08/09/2026.

    `quy_cach_json.giay_id` vẫn ghi vì quy cách còn nhiều thứ khác đọc nó (khổ, định lượng), nhưng
    nó KHÔNG còn đẻ nhu cầu giấy — muốn kiểm ca "lệnh chưa chọn giấy" thì truyền `giay_o_buoc=False`.
    """
    from app.models.lsx import LsxCongDoanVatTu
    from app.models.vat_lieu_kho import GiayNguyen

    o = _don(db, customer)
    qc = {"giay_id": giay_id, "kho_nguyen_dai": 860, "kho_nguyen_rong": 650, "gsm": 150}
    if nguon_giay:
        qc["nguon_giay"] = nguon_giay
    l = Lsx(
        ma=ma, ten=ma, order_id=o.id, order_line_id=o._line.id,
        so_luong_dat=1_000, so_to_nguyen=so_to_nguyen, so_con=1,
        han_hoan_thanh_sx=han, quy_cach_json=qc, trang_thai=TT_SAN_SANG,
    )
    db.add(l)
    db.flush()
    if buoc:
        b = LsxCongDoan(
            lsx_id=l.id, thu_tu=1, ten="In offset", loai_buoc="may", may_id=_may(db).id,
            don_vi_vao="to_nguyen", don_vi_ra="to",
            so_luong_vao=so_to_nguyen, so_luong_ra=so_to_nguyen,
        )
        db.add(b)
        db.flush()
        if giay_o_buoc:
            g = db.get(GiayNguyen, giay_id)
            # 1 tờ 65×86 định lượng 150 = 0,08385 kg — số này là kết quả công thức lượng của giấy,
            # `LsxService` đã tính lúc lưu bước. Bảng cân đối lấy thẳng, không tính lại.
            db.add(LsxCongDoanVatTu(
                lsx_cong_doan_id=b.id, hang_loai="giay", hang_id_unused=None,
                vat_tu_id=giay_id, vat_tu_ma_snapshot=g.ma, vat_tu_ten_snapshot=g.ten,
                don_vi_snapshot=g.don_vi_gia or "kg",
                so_luong=round(so_to_nguyen * 0.08385, 3), thu_tu=0, tu_dong=False,
            ))
    db.commit()
    return l
```

> Bỏ `hang_id_unused=None` — nó không phải cột thật, viết nhầm là `TypeError`. Dòng đúng chỉ gồm `hang_loai="giay"` và `vat_tu_id=giay_id`.

- [x] **Step 4: Gỡ vòng sinh dòng giấy của lệnh**

Trong `backend/app/services/ke_hoach_vat_tu_service.py`, xoá nguyên vòng `for l in lenh:` sinh dòng giấy (dòng ~962–990, từ `if l.id in thanh_vien: continue` tới hết `tho.append(self._dong_lenh(l, ("giay", ...)))`), thay bằng một khối ghi chú:

```python
        # --- giấy của LỆNH: ĐÃ GỠ 08/09/2026 -------------------------------
        # Trước đây lệnh tự đẻ một dòng giấy từ `quy_cach_json.giay_id` + `so_to_nguyen`, rồi treo
        # ngày cần lên "bước đầu tiên chạm tờ" (`_buoc_dau_dong_giay`). Hai chỗ đoán, hai chỗ sai:
        # người dùng không chọn được giấy nào khác, không đổi được bước tiêu thụ, và một lệnh chỉ
        # ôm được ĐÚNG MỘT loại giấy — trong khi hộp carton cần giấy mặt + giấy sóng + giấy đáy,
        # mỗi loại vào một bước khác nhau.
        #
        # Nay giấy là một DÒNG VẬT TƯ của bước (`lsx_cong_doan_vat_tu` với `hang_loai='giay'`), đi
        # chung vòng "vật tư khai tay ở bước lệnh" ngay dưới. Ngày cần lấy theo CHÍNH bước mang nó.
        # BÀI GHÉP giữ nguyên `bai_ghep.giay_id`: giấy in của một lượt chạy chung thuộc về BÀI.
```

Xoá luôn hàm `_buoc_dau_dong_giay` (dòng 367–384) và mọi chỗ gọi nó. Giữ `_dv_giay` — bài ghép còn dùng.

- [x] **Step 5: Vòng vật tư bước đọc `hang_loai`**

Sửa dòng ~1019:

```python
                tho.append(
                    self._dong_lenh(l, (vt.hang_loai, int(vt.vat_tu_id)), vt.don_vi_snapshot,
                                    _f(vt.so_luong), cd)
                )
```

- [x] **Step 6: `_ve_goc` chỉ chạy công thức mặt hàng cho BÀI GHÉP**

Trong `_ve_goc`, thay điều kiện `ct` (dòng ~320):

```python
        # ⚠️ CHỈ cho dòng đến từ đường TỔNG-LỆNH — nay chỉ còn GIẤY CỦA BÀI GHÉP (08/09/2026).
        # Công thức lượng của giấy trả TỔNG của cả lệnh/bài, tính từ `to_nguyen` trong quy cách.
        # Dòng giấy của BƯỚC thì `so_luong` đã LÀ kg — `LsxService._luong_vat_tu` tính lúc lưu bước
        # bằng ngữ cảnh đầy đủ có cả `sl_vao`/`sl_ra`. Chạy lại ở đây là tính lần hai bằng ngữ cảnh
        # nghèo hơn và vứt số thật của bước, đúng lớp hỏng đã thấy với vật tư ở LSX26-0020.
        ct = (getattr(obj, "cong_thuc_luong", None) or "").strip() if (
            tong_lenh and hang[0] == HANG_GIAY) else ""
```

Và ở `_quy_doi_dong` (dòng ~1136), truyền cờ theo từng dòng thay vì bật cứng:

```python
            # `tong_lenh` bật theo TỪNG DÒNG: chỉ dòng giấy của BÀI GHÉP mang số tờ và cần công
            # thức mặt hàng để ra kg. Dòng vật tư/giấy của BƯỚC đã mang sẵn số theo đơn vị gốc.
            kq = self._ve_goc(d["hang"], d["dvt"], d["sl"], d.get("qc"),
                              tong_lenh=bool(d.get("ct_mat_hang")))
```

Trong `_dong_bai` thêm `"ct_mat_hang": True` cho dòng giấy của bài; `_dong_lenh` để mặc định vắng (falsy).

> Cách gọn nhất: `_dong_bai` nhận thêm tham số `ct_mat_hang: bool = False` và vòng giấy của bài truyền `True`; vòng vật tư của bài truyền mặc định.

- [x] **Step 7: Chạy test cho XANH**

```bash
cd backend && python -m pytest tests/test_ke_hoach_vat_tu.py -q
```

Kỳ vọng: PASS toàn bộ file. Test nào còn đỏ là test cố ý kiểm đường cũ — đọc tên test, sửa kỳ vọng theo luật mới (giấy đến từ bước), **không** khôi phục đường cũ.

- [x] **Step 8: Chạy các file test hạ nguồn**

```bash
cd backend && python -m pytest tests/test_giu_cho_vat_tu.py tests/test_lenh_sx_ho_so.py tests/test_sx_vat_tu_de_nghi.py -q
```

Chỗ đỏ chỉ nên là dựng `LsxCongDoanVatTu(...)` thiếu `hang_loai` — thêm `hang_loai="vat_tu"` vào từng chỗ dựng.

- [x] **Step 9: Commit**

```bash
git add backend/app/services/ke_hoach_vat_tu_service.py backend/tests/
git commit -m "Bang can doi bo suy giay tu cong doan, doc dong giay cua buoc; bai ghep giu nguyen"
```

---

### Task 5: FE — bảng kê vật tư của lệnh bỏ dòng giấy ảo

**Files:**
- Modify: `frontend/src/api/client.ts:2452-2470`
- Modify: `frontend/src/pages/lsxVatTu.ts:78-130`
- Test: `frontend/src/pages/lsxVatTu.test.ts`

**Interfaces:**
- Consumes: `LsxCongDoanOut.vat_tus[].hang_loai` (Task 3).
- Produces: `bangKeVatTu` không còn đọc `quyCach`/`soToNguyen`/`donViToNguyen` để dựng dòng giấy; nhóm `nvl` suy từ `hang_loai === "giay"`.

- [x] **Step 1: Sửa test hiện có cho ĐỎ**

Trong `frontend/src/pages/lsxVatTu.test.ts`, thay test `"giấy treo vào bước ĐẦU TIÊN TRÊN DÒNG GIẤY..."` bằng:

```typescript
  it("KHÔNG tự sinh dòng giấy — bước nào không khai giấy thì không có NVL chính", () => {
    // 08/09/2026: giấy do người lập lệnh tự chọn và tự đặt vào bước. Tự treo lên "bước đầu tiên
    // chạm tờ" là đoán sai bước tiêu thụ, mà bước tiêu thụ chính là thứ suy ra NGÀY CẦN giấy.
    const b = ke(chuoiSach()).buocs;
    expect(b.flatMap((x) => x.dong).filter((d) => d.nhom === "nvl")).toHaveLength(0);
  });

  it("giấy khai ở ĐÚNG bước nào thì nằm ở bước đó, và đếm là NVL chính", () => {
    const chuoi = chuoiSach();
    chuoi[1].vat_tus = [...chuoi[1].vat_tus, giay(3, "Ford 70 65×86", 435.94)];
    const b = ke(chuoi).buocs;
    expect(b[0].dong.filter((d) => d.nhom === "nvl")).toHaveLength(0);
    const nvl = b[1].dong.filter((d) => d.nhom === "nvl");
    expect(nvl).toHaveLength(1);
    expect(nvl[0]).toMatchObject({ khoa: "giay:3", ten: "Ford 70 65×86",
                                   so_luong: 435.94, chu_thich: "NVL chính" });
  });

  it("hai loại giấy ở HAI bước là hai dòng NVL chính, không gộp", () => {
    // Hộp carton: giấy sóng vào bước chạy sóng, giấy mặt vào bước bồi. Đây chính là ca mà đường
    // cũ (một `giay_id` cho cả lệnh) không chứa nổi.
    const chuoi = chuoiSach();
    chuoi[1].vat_tus = [...chuoi[1].vat_tus, giay(3, "Giấy sóng E", 120)];
    chuoi[2].vat_tus = [giay(4, "Duplex 250 mặt", 80)];
    const tong = ke(chuoi).tong.filter((t) => t.nhom === "nvl");
    expect(tong.map((t) => t.khoa).sort()).toEqual(["giay:3", "giay:4"]);
  });
```

Thêm helper `giay` cạnh `vt`:

```typescript
function giay(id: number, ten: string, so_luong: number, don_vi = "kg"): VatTuDong {
  return { id: id * 100, hang_loai: "giay", vat_tu_id: id, vat_tu_ma: `GY-${id}`,
           vat_tu_ten: ten, don_vi, so_luong, tu_dong: false } as VatTuDong;
}
```

Và sửa `vt` để đóng dấu `hang_loai: "vat_tu"`.

- [x] **Step 2: Chạy test cho chắc nó ĐỎ**

```bash
cd frontend && npx vitest run src/pages/lsxVatTu.test.ts
```

Kỳ vọng: FAIL — vẫn có dòng `nvl` ảo ở bước In.

- [x] **Step 3: Gỡ suy giấy trong `lsxVatTu.ts`**

Xoá ba dòng `buocGiay` / `giayId` / `coGiay` / `giayTen` (dòng ~86–91) và khối `if (coGiay ...)` (dòng ~96–110). Thay vòng vật tư bằng:

```typescript
    for (const v of c.vat_tus ?? []) {
      // NVL chính = dòng lấy từ danh mục GIẤY. Người lập lệnh tự chọn và tự đặt vào bước ăn nó
      // (08/09/2026) — trước đó hệ tự treo giấy lên "bước đầu tiên chạm tờ", đoán cả loại lẫn bước.
      const laGiay = v.hang_loai === "giay";
      dong.push({
        nhom: laGiay ? "nvl" : "vat_tu",
        khoa: `${laGiay ? "giay" : "vat_tu"}:${v.vat_tu_id}`,
        ma: v.vat_tu_ma ?? null,
        ten: v.vat_tu_ten ?? "",
        so_luong: soHoac0(v.so_luong),
        don_vi: nhanDv(v.don_vi),
        chu_thich: laGiay ? "NVL chính" : null,
      });
    }
```

Đổi chữ ký `bangKeVatTu` — bỏ ba tham số nay không ai đọc:

```typescript
export function bangKeVatTu(args: { congDoans: LsxCongDoan[] }): BangKeVatTu {
  const { congDoans } = args;
```

Sửa đầu file, khối comment "Ba nhóm cố ý KHÔNG gộp":

```typescript
//   · `nvl`     — giấy. Dòng lấy từ danh mục Giấy, người lập lệnh tự chọn và tự đặt vào bước ăn nó.
//                 Một lệnh có thể có NHIỀU loại (hộp carton: giấy mặt · giấy sóng · giấy đáy).
```

- [x] **Step 4: Sửa kiểu TS + nơi gọi**

`frontend/src/api/client.ts` dòng 2452:

```typescript
  vat_tus: { id: number; hang_loai: "giay" | "vat_tu"; vat_tu_id: number; vat_tu_ma: string;
             vat_tu_ten: string; don_vi: string; so_luong: number; tu_dong?: boolean }[];
```

dòng 2465:

```typescript
  vat_tu_goi_y: {
    hang_loai: "giay" | "vat_tu";
    vat_tu_id: number;
    so_luong: number | null;
    dien_giai: string | null;
    ly_do: string | null;
  }[];
```

Sửa nơi gọi `bangKeVatTu` trong `LsxVatTuPanel.tsx` (bỏ ba tham số đã gỡ) và hàm `ke()` trong test.

- [x] **Step 5: Chạy test + type-check cho XANH**

```bash
cd frontend && npx vitest run src/pages/lsxVatTu.test.ts && npx tsc --noEmit
```

Kỳ vọng: PASS + không lỗi type.

- [x] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/lsxVatTu.ts frontend/src/pages/lsxVatTu.test.ts frontend/src/pages/LsxVatTuPanel.tsx
git commit -m "Bang ke vat tu cua lenh bo dong giay ao, NVL chinh suy tu hang_loai"
```

---

### Task 6: FE — drawer bước chọn được giấy

**Files:**
- Modify: `frontend/src/pages/LsxDetailView.tsx:239, 374-377`
- Modify: `frontend/src/pages/LsxBuocDrawer.tsx:121, 240-295, 1041-1250`
- Modify: `frontend/src/pages/lsxBuoc.ts` (payload `vat_tus`)
- Modify: `frontend/src/pages/LsxRoutingTable.tsx:100, 126` (truyền prop)

**Interfaces:**
- Consumes: `vat_tu_goi_y[].hang_loai`, `vat_tus[].hang_loai` (Task 5).
- Produces: `RefRow` mang `hangLoai: "giay" | "vat_tu"`; payload `vat_tus` gửi `hang_loai`.

- [x] **Step 1: Nạp thêm danh mục Giấy**

Trong `LsxDetailView.tsx`, thay khối nạp `vatTuRefs` (dòng 374–376):

```typescript
    Promise.all([
      crud("/api/vat-lieu-kho/giay").list(token, { active: true }),
      crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true }),
    ]).then(([giay, vt]) =>
      // Giấy đứng TRƯỚC: người lập lệnh mở khối vật tư của bước trước in là để chọn NVL chính.
      setVatTuRefs([
        ...giay.items.map((g) => ({ id: g.id, ten: g.ten, ma: String(g.ma),
                                    donVi: String(g.don_vi_gia ?? ""), hangLoai: "giay" as const })),
        ...vt.items.map((v) => ({ id: v.id, ten: v.ten, ma: String(v.ma),
                                  donVi: String(v.don_vi_gia ?? ""), hangLoai: "vat_tu" as const })),
      ])
    ).catch(() => setVatTuRefs(null));
```

Thêm `hangLoai` vào type `RefRow` (nơi khai — grep `interface RefRow`), là optional để các dropdown khác không phải sửa.

- [x] **Step 2: Dropdown chia hai nhóm**

Trong `LsxBuocDrawer.tsx`, thay `<select>` thêm vật tư (dòng ~1216–1246):

```tsx
                              <select
                                className="khsx-vattu-select-clean"
                                value=""
                                onChange={(e) => {
                                  const [hl, idTxt] = e.target.value.split(":");
                                  const id = Number(idTxt);
                                  const item = vatTuRefs.find(
                                    (v) => v.id === id && (v.hangLoai ?? "vat_tu") === hl);
                                  if (!item) return;
                                  if (row.vat_tus.some(
                                    (v) => v.vat_tu_id === id && v.hang_loai === hl)) return;
                                  const goiY = row.vat_tu_goi_y.find(
                                    (g) => g.vat_tu_id === id && g.hang_loai === hl);
                                  set("vat_tus", [
                                    ...row.vat_tus,
                                    {
                                      hang_loai: hl as "giay" | "vat_tu",
                                      vat_tu_id: id,
                                      vat_tu_ma: item.ma ?? "",
                                      vat_tu_ten: item.ten,
                                      don_vi: item.donVi ?? "",
                                      so_luong: goiY?.so_luong != null ? String(goiY.so_luong) : "",
                                      tu_dong: false,
                                    },
                                  ]);
                                }}
                              >
                                <option value="">— Thêm vật tư vào công đoạn —</option>
                                {(["giay", "vat_tu"] as const).map((hl) => {
                                  const ds = vatTuRefs.filter(
                                    (x) => (x.hangLoai ?? "vat_tu") === hl
                                      && !row.vat_tus.some(
                                        (v) => v.vat_tu_id === x.id && v.hang_loai === hl));
                                  if (!ds.length) return null;
                                  return (
                                    <optgroup key={hl}
                                      label={hl === "giay"
                                        ? "Giấy — nguyên vật liệu chính"
                                        : "Vật tư khác — mực · keo · màng"}>
                                      {ds.map((x) => (
                                        <option key={`${hl}:${x.id}`} value={`${hl}:${x.id}`}>
                                          {x.ma} · {x.ten} ({nhanDonVi(x.donVi)})
                                        </option>
                                      ))}
                                    </optgroup>
                                  );
                                })}
                              </select>
```

- [x] **Step 3: Mọi chỗ so `vat_tu_id` trong drawer đổi sang cặp**

Trong `LsxBuocDrawer.tsx` sửa các chỗ so khoá đơn (dòng 284, 1058-1073, 1108, 1117, 1137, 1176, 1194) thành so cặp `(hang_loai, vat_tu_id)`. Ví dụ dòng 1058:

```tsx
                      row.vat_tus.some((v) => {
                        const g = row.vat_tu_goi_y.find(
                          (x) => x.vat_tu_id === v.vat_tu_id && x.hang_loai === v.hang_loai);
```

và `key` của `<tr>` (dòng 1117):

```tsx
                            <tr className="khsx-vattu-tr" key={`${v.hang_loai}:${v.vat_tu_id}`}>
```

Dòng bung theo khoán (dòng 282–293) đóng dấu `hang_loai: "vat_tu"` cho các dòng mới.

- [x] **Step 4: Payload gửi `hang_loai`**

Trong `frontend/src/pages/lsxBuoc.ts`, chỗ dựng `vat_tus` cho payload lưu routing, thêm `hang_loai: v.hang_loai ?? "vat_tu"`.

- [x] **Step 5: Type-check + test FE**

```bash
cd frontend && npx tsc --noEmit && npx vitest run src/pages/lsxBuoc.test.ts src/pages/lsxVatTu.test.ts
```

Kỳ vọng: không lỗi type, test PASS.

- [x] **Step 6: Commit**

```bash
git add frontend/src/pages/LsxDetailView.tsx frontend/src/pages/LsxBuocDrawer.tsx frontend/src/pages/lsxBuoc.ts frontend/src/pages/LsxRoutingTable.tsx
git commit -m "Drawer buoc chon duoc NVL chinh tu danh muc Giay"
```

---

### Task 7: Xác minh luồng thật trên dev-browser

**Files:** không sửa file — đây là cửa nghiệm thu bắt buộc của dự án.

- [x] **Step 1: Khởi động BE + FE**

Bật uvicorn qua WMI (`Win32_Process.Create`, KHÔNG dùng Bash nền/Start-Process — chúng chết khi hết phiên), BE `127.0.0.1:8000`, FE `localhost:5173`. Đăng nhập `admin` / `admin123`.

- [x] **Step 2: Thao tác đúng luồng bằng chuột/bàn phím thật**

KHÔNG dùng API/curl thay bất kỳ bước nào, kể cả để dựng dữ liệu.

1. Kế hoạch sản xuất → mở một lệnh có bước In.
2. Tab **Vật tư** → xác nhận **không còn** dòng `Giấy … · NVL chính` tự sinh.
3. Tab **Công đoạn** → mở bước In → tab **Vật tư** của drawer.
4. Dropdown "Thêm vật tư vào công đoạn" → xác nhận có nhóm **Giấy — nguyên vật liệu chính**.
5. Chọn một loại giấy → xác nhận ô số lượng **tự điền kg** (không phải tờ).
6. Lưu → mở lại → xác nhận dòng còn nguyên, nhãn "Đã sửa".
7. Thêm loại giấy **thứ hai** vào một bước khác → lưu → tab Vật tư của lệnh hiện **hai** dòng NVL chính ở hai bước.
8. Kế hoạch vật tư → xác nhận cả hai loại giấy lên bảng cân đối, mỗi dòng mang ngày cần của **bước mang nó**.

- [x] **Step 3: Báo cáo**

Liệt kê CỤ THỂ đã bấm gì / gõ gì / thấy gì ở từng bước trên. Nếu vì lý do nào đó buộc phải tắt qua API ở một đoạn, **nói rõ ngay lúc báo cáo**.

---

## Self-Review

**Spec coverage**
- "bỏ logic suy giấy từ công đoạn" → Task 4 Step 4 (BE `_buoc_dau_dong_giay` + vòng giấy lệnh), Task 5 Step 3 (FE `buocGiay`). ✔
- "thêm logic được chọn NVL chính từ danh mục giấy" → Task 1 (cột), Task 2 (lượng), Task 3 (ghi), Task 6 (cửa chọn). ✔
- "bỏ mồi sẵn dòng giấy lúc tạo lệnh" → không có task nào thêm dòng giấy lúc `tao()`; Task 4 Step 4 nói rõ lệnh mới không có dòng giấy nào. ✔
- "cắt dứt đường cũ, không chạy song song" → Task 4 Step 4. ✔
- "bài ghép giữ nguyên" → Task 4 Step 4 + Step 6 (`ct_mat_hang` chỉ bật cho bài). ✔

**Placeholder scan** — không có TBD/TODO; mọi step code đều có khối code thật. Một chỗ cố ý cảnh báo lỗi viết nhầm (`hang_id_unused`) đã ghi rõ phải bỏ.

**Type consistency**
- `hang_loai` là `str` ở model, `Literal["giay","vat_tu"]` ở schema in, `"giay" | "vat_tu"` ở TS — nhất quán.
- `_mon_active()` trả `dict[tuple[str,int], object]` — dùng ở Task 2 Step 5, Task 3 Step 4, cùng dạng khoá.
- `vat_tu_goi_y` mang `hang_loai` từ Task 2 Step 5 (BE) tới Task 5 Step 4 (TS) tới Task 6 Step 2 (dùng) — khớp.
- `bangKeVatTu({ congDoans })` đổi chữ ký ở Task 5 Step 3, nơi gọi sửa cùng lượt ở Step 4.
