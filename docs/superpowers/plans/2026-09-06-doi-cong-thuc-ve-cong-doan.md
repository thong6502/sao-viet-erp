# Dời công thức tính lượng về màn Công đoạn — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển bốn công thức "một bước ăn bao nhiêu" về khai tại **màn Công đoạn** — giờ chạy và giá theo cặp (công đoạn × máy), tiền công theo đầu việc, định mức vật tư theo từng dòng vật tư — rồi gỡ ba ô công thức cũ ở Máy móc / Công việc khoán / Vật tư khác.

**Architecture:** Thêm một bảng nối `cong_doan_may` (mỗi dòng = một máy chạy được công đoạn, mang hai ô công thức) và hai cột công thức xuống hai bảng con đã có của công đoạn (`cong_doan_dau_viec`, `cong_doan_dau_viec_vat_tu`). Bốn nơi engine đang đọc công thức từ danh mục nguồn được trỏ sang chỗ mới, giữ nguyên mọi luật ghim/đọc-sống hiện hành. Ô "Số lượt chạy qua máy" mở cho mọi loại bước (mặc định 1) và trở thành chip công thức mới.

**Tech Stack:** FastAPI + SQLAlchemy 2 (Postgres prod/dev, SQLite in-memory cho test), Pydantic v2, React 18 + TypeScript + Vite, pytest, vitest.

**Spec:** Không có file spec riêng. Thiết kế đã chốt với chủ dự án trong hội thoại ngày **06/09/2026** và được chép nguyên vào mục "Thiết kế đã chốt" ngay dưới — executor đọc mục đó thay cho spec.

---

## Thiết kế đã chốt (06/09/2026)

**Vì sao dời.** Công thức lượng hiện treo ở *nguồn* (cái máy, đầu việc khoán, món vật tư) nên mọi công đoạn dùng nguồn đó phải xài chung một cách tính. Thực tế mỗi công đoạn cần một số khác nhau:

- Cùng "Mực offset Cyan": công đoạn In khổ lớn 79 × 109 thì 1 kg chạy ~8.000 tờ, công đoạn In khổ nhỏ 11 × 11 thì ~40.000 tờ.
- Cùng đầu việc trong một công đoạn: mực ăn theo **số tờ** (`sl_vao / 40000`), dung môi rửa máy ăn theo **số lần rửa = số màu** (`so_mau * 0.3`) — in 5.000 tờ hay 50.000 tờ vẫn 1,2 kg.
- Cùng công đoạn In: máy 5 màu khổ lớn và máy 2 màu khổ nhỏ có đơn giá khác nhau, nên công thức giá phải theo máy.

**Bốn ô mới, tất cả nằm trong drawer Công đoạn:**

| Ô | Neo vào | Ra cái gì | Ai đọc | Sống hay ghim |
|---|---|---|---|---|
| Công thức giờ chạy | dòng `cong_doan_may` | LƯỢNG theo đơn vị tốc độ của máy | Kế hoạch SX · Xếp lịch 2 · Bài ghép 2 · Kế hoạch vật tư | đọc **sống** theo máy đang gán |
| Công thức giá | dòng `cong_doan_may` | TIỀN | Phiếu tính giá — ghi đè `cong_doan.cong_thuc_gia` khi thành phần có chọn máy | đọc lúc bấm Tính, chốt vào ảnh chụp phiếu |
| Công thức tính tiền công | dòng `cong_doan_dau_viec` | LƯỢNG theo đơn vị đơn giá khoán | Kế hoạch SX | **ghim** vào bước lúc chọn đầu việc (giữ luật hôm nay) |
| Công thức định mức vật tư | dòng `cong_doan_dau_viec_vat_tu` | LƯỢNG theo ĐVT của vật tư | Kế hoạch SX (bung BOM của bước) · Kế hoạch vật tư | tính lúc lưu công đoạn, số chốt vào bước |

**Quyết định kèm theo:**

1. **Nhóm máy giữ nguyên cột `cong_doan.nhom_may_cho_phep`**, đổi vai thành *bộ lọc để chọn máy* trong drawer. Luật chặn gán máy ở bước đọc **danh sách máy đã chọn** khi công đoạn có khai; công đoạn chưa khai máy nào thì lùi về luật nhóm như hiện nay. Không để hai luật chạy song song.
2. **Ô công thức giá chỉ hiện khi `cong_doan.nhom == "print"`** — dùng enum nhóm có sẵn trong code, KHÔNG so tên nhóm máy "Máy in" (tên nhóm máy là danh mục người dùng sửa được; đóng cứng tên vào code là hỏng ngay khi ai đó đổi tên).
3. **Máy gán ở bước mà không nằm trong danh sách công đoạn** → không có công thức riêng → lùi về cầu quy đổi, đúng hành vi hiện nay khi ô để trống.
4. **Chip `so_luot_chay` chỉ mở ở ô công thức loại `quy_doi`** (giờ chạy, tiền công, định mức vật tư), KHÔNG mở ở ô loại `cong_doan` (công thức giá) — tầng phiếu tính giá đã có `so_mat` và engine chưa bơm số lượt ở vòng lặp bước của nó.
5. **Ô "Số lượt chạy qua máy" hiện ở MỌI loại bước, mặc định 1** (hôm nay bị ép `None` khi bước là tổ). Không mở tiền khoán cho bước máy — tiền công vẫn chỉ tính ở bước tổ.

   ⚠️ **Số lượt KHÔNG tự nhân vào GIỜ của bước tổ.** Tra `thoi_luong_buoc` (lsx_service.py:226) thấy hai nhánh khác hẳn nhau: nhánh máy `_chay(toc_do) = vao × 60 ÷ toc_do × luot` có nhân lượt; nhánh tổ `_chay_to(muc) = vao ÷ (muc × người) × 60` **không** nhân. Plan này GIỮ NGUYÊN cả hai — đổi nhánh tổ là làm mọi bước tổ đang có (số lượt sắp được backfill thành 1) đổi giờ ngay lần deploy kế, một thay đổi ngoài phạm vi chủ dự án giao. Hệ quả người dùng phải biết: **ở bước tổ, gõ số lượt 2 làm đổi TIỀN CÔNG (qua chip trong công thức) chứ không đổi GIỜ.** Muốn giờ cũng gấp đôi thì nhân tay vào ô "Phát sinh (phút)", hoặc mở một việc riêng để bàn có nên nhân lượt vào nhánh tổ không. Task 7 phải viết đúng câu này vào hint dưới ô cho bước tổ.
6. **Giấy giữ nguyên ô "Công thức tính lượng"** của nó (`giay_nguyen.cong_thuc_luong`). Chỉ ba ô của Máy / Công việc khoán / Vật tư khác bị gỡ.
7. **Backfill**: khoán và vật tư backfill được bằng raw SQL vì ngữ nghĩa giữ nguyên (một công thức nguồn chép xuống mọi dòng đang dùng nguồn đó). Máy KHÔNG backfill — bảng `cong_doan_may` sinh ra rỗng, người dùng tự chọn máy rồi khai.

---

## Global Constraints

Mọi task đều chịu các ràng buộc sau. Đọc kỹ trước khi viết dòng code đầu tiên.

- **Ngôn ngữ**: comment, docstring, commit message, nhãn UI đều tiếng Việt (thuật ngữ kỹ thuật giữ tiếng Anh). Comment phải nói **vì sao**, không kể lại code làm gì.
- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, KHÔNG ALTER. Thêm/đổi/xoá cột phải viết hàm migration idempotent trong `backend/app/db_migrations.py` rồi `MIGRATIONS.append(("<số>_<slug>", <hàm>))` ở cuối file. Dev cũng là Postgres — migration là đường DUY NHẤT.
- **Migration cấm ORM full-select.** Backfill trong migration phải là raw SQL đích danh cột (`SELECT id, cong_thuc_luong FROM ...`), vì ORM full-select kéo cả cột do migration SAU thêm → vỡ deploy trên DB trung gian.
- **Cột Boolean**: `server_default` phải là `sa_false()` / `sa_true()`, KHÔNG phải `"0"` / `"1"`.
- **`docs/DB_SCHEMA.md` có guard test** (`backend/tests/test_schema_documented.py`): mọi bảng/cột trong model phải được ghi vào đó. Thêm/xoá cột → sửa `docs/DB_SCHEMA.md` **cùng lúc**, không để sang task sau.
- **KHÔNG chạy `./init.ps1`** (chủ dự án cấm). Verify bằng `python -m pytest <file cụ thể> -q` chạy **từ trong `backend/`**, và `npx tsc --noEmit` / `npx vitest run <file>` chạy **từ trong `frontend/`**.
- **KHÔNG chạy `python -c` trần trong `backend/`** — nó trỏ vào Postgres dev thật. Muốn thăm dò DB thì viết test tạm chạy dưới pytest, hoặc script chỉ-đọc đặt NGOÀI `backend/`.
- **Sửa route/schema/service backend → RESTART uvicorn.** Ở máy này hot-reload không đáng tin.
- **Commit sau mỗi task**, message tiếng Việt, **KHÔNG** thêm dòng `Co-Authored-By`. **KHÔNG push** trừ khi chủ dự án yêu cầu.
- **Không giữ tương thích ngược**: dự án đang dev, prod DB trắng, chưa có user thật. Sửa cho ĐÚNG, đừng đẻ nhánh tương thích.
- **Luồng nghiệp vụ có UI thì phải nghiệm thu bằng chuột/bàn phím thật trên dev-browser** trước khi báo xong (Task 9–11 và Task 14). KHÔNG dùng API/curl thay bất kỳ bước nào; nếu buộc phải tắt qua API ở một đoạn thì phải nói rõ ngay lúc báo cáo.

---

## Bản đồ file

**Backend — tạo mới**

| File | Trách nhiệm |
|---|---|
| `backend/tests/test_cong_doan_may.py` | Test bảng nối công đoạn × máy: CRUD, unique, cascade, validate máy tồn tại |
| `backend/tests/test_cong_thuc_ve_cong_doan.py` | Test bốn công thức đọc đúng chỗ mới (giờ · tiền công · vật tư · giá) |

**Backend — sửa**

| File | Sửa gì |
|---|---|
| `backend/app/models/cong_doan.py` | `CongDoanMay` (mới) · `CongDoanDauViec.cong_thuc_khoan` · `CongDoanDauViecVatTu.cong_thuc_luong` · bỏ property `vat_tu_ids` |
| `backend/app/models/may_thiet_bi.py` | Xoá cột `cong_thuc_luong` (Task 13) |
| `backend/app/models/piece_work.py` | Xoá cột `cong_thuc_luong` (Task 13) |
| `backend/app/models/vat_lieu_kho.py` | Xoá cột `cong_thuc_luong` của `VatTuInAn` — **giữ** của `GiayNguyen` (Task 13) |
| `backend/app/schemas/cong_doan.py` | `CongDoanMayIn/Row` · `CongDoanDauViecVatTuIn` · `cong_thuc_khoan` · `vat_tu_ids` → `vat_tus` |
| `backend/app/schemas/may_thiet_bi.py`, `cong_viec_khoan.py`, `vat_lieu_kho.py` | Bỏ `cong_thuc_luong` + hai khoá `_truoc` / `_sua_luc` (Task 13) |
| `backend/app/repositories/cong_doan_repo.py` | `_replace_may` · `_replace_dinh_muc` nhận `vat_tus` có công thức · eager-load |
| `backend/app/repositories/may_thiet_bi_repo.py`, `cong_viec_khoan_repo.py`, `vat_lieu_kho_repo.py` | Bỏ `cong_thuc_luong` khỏi tuple cột (Task 13) |
| `backend/app/routers/may_thiet_bi.py`, `cong_viec_khoan.py`, `vat_lieu_kho.py` | Bỏ `cong_thuc_truong=` (Task 13) |
| `backend/app/services/cong_doan_service.py` | Validate `may_lam_duoc` + validate công thức của ba ô mới |
| `backend/app/services/lsx_service.py` | `sl_tinh_cua_buoc` · `_khoan_tu_kh` · `_vat_tu_bung` · `_luong_vat_tu` · `so_luot_chay` cho bước tổ |
| `backend/app/services/piece_work_service.py` | `khoan_snapshot(rate, dm=None)` lấy công thức từ định mức |
| `backend/app/services/tinh_gia_service.py` | `_cong_doan_to_dict(..., ct_gia_may=None)` + truyền `tp.may_id` |
| `backend/app/services/bien_cong_thuc.py` | Chip `so_luot_chay` + hằng `MAC_DINH_TANG_LENH` |
| `backend/app/services/bai_ghep_service.py` | `_may_sai_loai` đọc danh sách máy của công đoạn |
| `backend/app/services/xep_lich_service.py` | `_top_may` lọc theo danh sách máy của công đoạn |
| `backend/app/services/catalog_excel_specs.py` | Sheet con "Máy của công đoạn" + cột công thức ở hai sheet con sẵn có; bỏ 3 cột cũ |
| `backend/app/db_migrations.py` | `0271` · `0272` · `0273` |
| `backend/app/seed_rebuild.py`, `import_danh_muc_prod.py` | Bỏ `cong_thuc_luong=` cho máy/khoán/vật tư (Task 13) |
| `docs/DB_SCHEMA.md` | Bảng mới + cột mới + cột đã xoá |

**Frontend — sửa**

| File | Sửa gì |
|---|---|
| `frontend/src/pages/danh-muc/types.ts` | `DinhMucRow.cong_thuc_khoan` · `vat_tus` · `MayCongDoanRow` |
| `frontend/src/pages/danh-muc/fields/MayCuaCongDoan.tsx` (**mới**) | Bảng máy của công đoạn + panel hai ô công thức |
| `frontend/src/pages/danh-muc/fields/DinhMucDauViec.tsx` | Cột "Công thức tính tiền công" + hàng phụ vật tư đổi thành bảng có cột công thức |
| `frontend/src/pages/danh-muc/fields/index.ts` | Export field mới |
| `frontend/src/pages/danh-muc/CatalogDrawer.tsx` | Nhánh render `type: "may-cua-cong-doan"` |
| `frontend/src/pages/rebuildCatalogConfigs.tsx` | Thêm field `may_lam_duoc` vào CFG_CONG_DOAN; bỏ ô `cong_thuc_luong` khỏi CFG_MAY / CFG_CONG_VIEC_KHOAN / CFG_VAT_TU |
| `frontend/src/pages/lsxBuoc.ts` | Bỏ `r.loai_buoc === "to" ? null : luot` |
| `frontend/src/pages/LsxBuocDrawer.tsx` | Ô số lượt hiện cho mọi loại bước |
| `frontend/src/api/client.ts` | Kiểu `CongDoanMay`, `DinhMucRow` |

---

## Task 1: Bảng nối `cong_doan_may`

**Files:**
- Modify: `backend/app/models/cong_doan.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/schemas/cong_doan.py`
- Modify: `backend/app/repositories/cong_doan_repo.py`
- Modify: `backend/app/services/cong_doan_service.py`
- Modify: `backend/app/db_migrations.py` (cuối file)
- Modify: `docs/DB_SCHEMA.md`
- Test: `backend/tests/test_cong_doan_may.py` (tạo mới)

**Interfaces:**
- Produces: model `CongDoanMay` với cột `id, cong_doan_id, may_id, cong_thuc_gio, cong_thuc_gia, thu_tu`; quan hệ `CongDoan.may_lam_duoc: list[CongDoanMay]`; schema `CongDoanMayIn(may_id: int, cong_thuc_gio: str | None, cong_thuc_gia: str | None)` và `CongDoanMayRow(CongDoanMayIn)` thêm `id: int`; khoá `may_lam_duoc` trên `CongDoanIn`/`CongDoanOut`; migration `0271_cong_doan_may`.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/test_cong_doan_may.py`:

```python
"""Bảng nối công đoạn × máy — nơi khai công thức giờ chạy và công thức giá theo từng máy.

Vì sao có bảng này (06/09/2026): "một bước chạy trên máy này bằng bao nhiêu <đơn vị tốc độ>" và
"máy này tính tiền thế nào" đều là giao của VIỆC và MÁY. Treo ở máy thì mọi công đoạn dùng chung;
treo ở công đoạn thì mọi máy dùng chung — cả hai cách cũ đều sai một nửa.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.cong_doan import CongDoan, CongDoanMay
from app.models.may_thiet_bi import MayThietBi


def _cd(db, ma="CD-M1") -> CongDoan:
    cd = CongDoan(ma=ma, ten="In AB", nhom="print")
    db.add(cd)
    db.flush()
    return cd


def _may(db, ma="MAY-1") -> MayThietBi:
    m = MayThietBi(ma=ma, ten="Komori 5 màu", loai_may="Máy in")
    db.add(m)
    db.flush()
    return m


def test_mot_cong_doan_giu_nhieu_may_moi_may_mot_cap_cong_thuc(db):
    cd, m1, m2 = _cd(db), _may(db, "MAY-1"), _may(db, "MAY-2")
    cd.may_lam_duoc.append(CongDoanMay(
        may_id=m1.id, cong_thuc_gio="sl_vao * so_mau / 5", cong_thuc_gia="sl_vao * 180", thu_tu=0))
    cd.may_lam_duoc.append(CongDoanMay(
        may_id=m2.id, cong_thuc_gio="sl_vao * so_mau / 2", cong_thuc_gia="sl_vao * 90", thu_tu=1))
    db.commit()
    db.refresh(cd)
    assert [r.may_id for r in cd.may_lam_duoc] == [m1.id, m2.id]
    assert cd.may_lam_duoc[0].cong_thuc_gio == "sl_vao * so_mau / 5"
    assert cd.may_lam_duoc[1].cong_thuc_gia == "sl_vao * 90"


def test_mot_may_khong_khai_hai_lan_trong_cung_cong_doan(db):
    cd, m = _cd(db), _may(db)
    cd.may_lam_duoc.append(CongDoanMay(may_id=m.id, thu_tu=0))
    db.commit()
    cd.may_lam_duoc.append(CongDoanMay(may_id=m.id, thu_tu=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_xoa_cong_doan_keo_theo_dong_may(db):
    cd, m = _cd(db), _may(db)
    cd.may_lam_duoc.append(CongDoanMay(may_id=m.id, thu_tu=0))
    db.commit()
    db.delete(cd)
    db.commit()
    assert db.query(CongDoanMay).count() == 0
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

Từ `backend/`:

```bash
python -m pytest tests/test_cong_doan_may.py -q
```

Kỳ vọng: FAIL với `ImportError: cannot import name 'CongDoanMay'`.

- [ ] **Step 3: Thêm model**

Trong `backend/app/models/cong_doan.py`, thêm vào quan hệ của `CongDoan` (ngay sau `dau_viec_dinh_muc`):

```python
    # MÁY chạy được công đoạn này, mỗi dòng mang cách tính GIỜ và cách tính GIÁ của riêng cặp
    # (công đoạn, máy). Xem `CongDoanMay` để biết vì sao không treo ở máy hay ở công đoạn.
    may_lam_duoc: Mapped[list["CongDoanMay"]] = relationship(
        "CongDoanMay", back_populates="cong_doan", order_by="CongDoanMay.thu_tu",
        cascade="all, delete-orphan",
    )
```

Thêm class mới ở cuối file:

```python
class CongDoanMay(Base):
    """Một MÁY chạy được công đoạn này, kèm cách đo giờ và cách tính giá của riêng cặp đó.

    Vì sao là bảng nối chứ không phải cột trên máy hay trên công đoạn (06/09/2026): cả hai con số
    đều là giao của VIỆC × MÁY.
      · `cong_thuc_gio` — treo ở máy (`may_thiet_bi.cong_thuc_luong` cũ) thì mọi công đoạn chạy
        máy đó dùng chung một cách đo, trong khi In khổ lớn và In khổ nhỏ đo khác nhau.
      · `cong_thuc_gia` — treo ở công đoạn (`cong_doan.cong_thuc_gia`) thì mọi máy dùng chung một
        đơn giá, trong khi máy 5 màu khổ lớn và máy 2 màu khổ nhỏ có giá khác nhau.

    `may_id` là SOFT-REF (không FK) — cùng lối `piece_rate_id`/`vat_tu_id` ở hai bảng con kia:
    danh mục máy có vòng đời riêng, service chặn id không tồn tại hoặc máy đã thanh lý.

    `cong_thuc_gio` ra LƯỢNG theo đơn vị TỐC ĐỘ của máy, không ra giờ — engine vẫn tự chia tốc độ.
    `cong_thuc_gia` ra TIỀN, và GHI ĐÈ `cong_doan.cong_thuc_gia` khi phiếu tính giá có chọn máy.
    Cả hai để trống = lùi về hành vi cũ (cầu quy đổi cho giờ · công thức của công đoạn cho giá).
    """

    __tablename__ = "cong_doan_may"
    __table_args__ = (
        UniqueConstraint("cong_doan_id", "may_id", name="uq_cd_may"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    may_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    cong_thuc_gio: Mapped[str | None] = mapped_column(Text, nullable=True)
    cong_thuc_gia: Mapped[str | None] = mapped_column(Text, nullable=True)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cong_doan: Mapped["CongDoan"] = relationship("CongDoan", back_populates="may_lam_duoc")
```

Trong `backend/app/models/__init__.py`, sửa dòng import và `__all__`:

```python
from .cong_doan import CongDoan, CongDoanDauViec, CongDoanDauViecVatTu, CongDoanMay
```

và thêm `"CongDoanMay",` vào `__all__` ngay sau `"CongDoanDauViecVatTu",`.

- [ ] **Step 4: Chạy test, phải xanh**

```bash
python -m pytest tests/test_cong_doan_may.py -q
```

Kỳ vọng: 3 passed.

- [ ] **Step 5: Thêm schema**

Trong `backend/app/schemas/cong_doan.py`, thêm trước `class CongDoanIn`:

```python
class CongDoanMayIn(BaseModel):
    may_id: int
    # Ra LƯỢNG theo đơn vị TỐC ĐỘ của máy (không ra giờ — engine vẫn chia tốc độ). Trống = lùi về
    # cầu quy đổi, đúng hành vi của ô "Cách đo lượng" cũ trên máy khi để trống.
    cong_thuc_gio: str | None = None
    # Ra TIỀN, GHI ĐÈ `cong_doan.cong_thuc_gia` khi phiếu tính giá có chọn đúng máy này.
    cong_thuc_gia: str | None = None


class CongDoanMayRow(CongDoanMayIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
```

Thêm vào `CongDoanIn` (đặt ngay dưới `nhom_may_cho_phep`):

```python
    # Máy CỤ THỂ chạy được công đoạn, mỗi dòng mang công thức giờ + công thức giá của riêng nó.
    # `nhom_may_cho_phep` ngay trên chỉ còn là BỘ LỌC để chọn máy trong drawer.
    may_lam_duoc: list[CongDoanMayIn] = Field(default_factory=list)
```

Tìm schema Out (class có `dau_viec_dinh_muc: list[CongDoanDauViecRow]`, khoảng dòng 122) và thêm:

```python
    may_lam_duoc: list[CongDoanMayRow] = Field(default_factory=list)
```

- [ ] **Step 6: Repo thay-trọn-bộ + eager load**

Trong `backend/app/repositories/cong_doan_repo.py`:

Sửa import ở đầu file:

```python
from ..models.cong_doan import CongDoan, CongDoanDauViec, CongDoanDauViecVatTu, CongDoanMay
```

Thêm `selectinload(CongDoan.may_lam_duoc)` vào chỗ đang có `selectinload(CongDoan.dau_viec_dinh_muc)` (dòng ~40):

```python
            selectinload(CongDoan.dau_viec_dinh_muc).selectinload(CongDoanDauViec.vat_tus),
            selectinload(CongDoan.may_lam_duoc),
```

Sửa `_sau_gan`:

```python
    def _sau_gan(self, cd: CongDoan, data: dict) -> None:
        self._replace_dinh_muc(cd, data.get("dau_viec_dinh_muc") or [])
        self._replace_may(cd, data.get("may_lam_duoc") or [])
```

Thêm method mới ngay sau `_replace_dinh_muc`:

```python
    def _replace_may(self, cd: CongDoan, rows: list[dict]) -> None:
        """Thay TRỌN danh sách máy của công đoạn.

        `flush()` giữa xoá và thêm vì cùng lý do với `_replace_dinh_muc`: trong MỘT flush
        SQLAlchemy phát INSERT trước DELETE cho cùng bảng, nên giữ lại đúng một máy cũ là đụng
        `uq_cd_may` → 500.
        """
        if cd.may_lam_duoc:
            cd.may_lam_duoc.clear()
            if cd.id is not None:
                self.db.flush()
        for i, r in enumerate(rows):
            r = dict(r)
            r.pop("id", None)          # khoá chỉ-đọc của schema Row, client có thể gửi ngược lên
            r["thu_tu"] = i
            cd.may_lam_duoc.append(CongDoanMay(**r))
```

Thêm `"may_lam_duoc"` vào danh sách khoá bảng-con mà repo tự xử lý nếu file có một tuple như vậy (tìm `"dau_viec_dinh_muc"` trong file và làm giống hệt).

- [ ] **Step 7: Service validate máy**

Trong `backend/app/services/cong_doan_service.py`, ngay sau khối lấy `dinh_muc = data.get("dau_viec_dinh_muc") or []` (dòng ~56), thêm:

```python
        # Máy phải CÓ THẬT và còn dùng — `may_id` là soft-ref nên không có FK gác hộ. Máy đã thanh
        # lý mà vẫn nằm trong danh sách thì bước lệnh gán được một máy không tồn tại trên bàn xếp.
        may_rows = data.get("may_lam_duoc") or []
        may_ids = [int(r["may_id"]) for r in may_rows if r.get("may_id")]
        if len(set(may_ids)) != len(may_ids):
            raise ValueError("Một máy chỉ khai được một lần trong công đoạn.")
        if may_ids:
            song = {
                m.id: m for m in self.db.execute(
                    select(MayThietBi).where(
                        MayThietBi.id.in_(may_ids), MayThietBi.active.is_(True))
                ).scalars()
            }
            thieu = [i for i in may_ids if i not in song]
            if thieu:
                raise ValueError(
                    f"Máy không còn trong danh mục hoặc đã thanh lý: {', '.join(map(str, thieu))}.")
```

Thêm import ở đầu file nếu chưa có:

```python
from sqlalchemy import select

from ..models.may_thiet_bi import MayThietBi
```

(Đã tra: `MayThietBi.active` có thật — `backend/app/models/may_thiet_bi.py:141`, nghĩa "xưởng còn máy này không"; máy dừng tạm vì bảo trì vẫn `active=True`. Dùng thẳng, không cần kiểm lại.)

- [ ] **Step 8: Migration 0271**

Cuối `backend/app/db_migrations.py`, sau dòng `MIGRATIONS.append(("0270_gop_dinh_muc_nhan_luc", ...))`:

```python
def _migrate_cong_doan_may(db) -> None:
    """Bảng nối công đoạn × máy (06/09/2026) — nơi khai công thức giờ chạy + công thức giá theo máy.

    Nghiệp vụ: "một bước chạy trên máy này bằng bao nhiêu" và "máy này tính tiền thế nào" đều là
    giao của VIỆC × MÁY, nên phải có một dòng cho mỗi cặp. Trước đây cách đo giờ treo ở MÁY (mọi
    công đoạn chạy máy đó dùng chung) còn cách tính giá treo ở CÔNG ĐOẠN (mọi máy dùng chung).

    KHÔNG backfill từ `cong_doan.nhom_may_cho_phep`: nhóm cho phép thường phủ hàng chục máy, đẻ
    ra bằng ấy dòng rỗng chỉ để người dùng phải xoá bớt. Bảng sinh ra RỖNG, ai cần thì tự chọn máy.
    """
    insp = inspect(db.get_bind())
    if "cong_doan_may" in set(insp.get_table_names()):
        return
    db.execute(text(
        "CREATE TABLE cong_doan_may ("
        " id SERIAL PRIMARY KEY,"
        " cong_doan_id INTEGER NOT NULL REFERENCES cong_doan(id) ON DELETE CASCADE,"
        " may_id INTEGER NOT NULL,"
        " cong_thuc_gio TEXT,"
        " cong_thuc_gia TEXT,"
        " thu_tu INTEGER NOT NULL DEFAULT 0,"
        " CONSTRAINT uq_cd_may UNIQUE (cong_doan_id, may_id))"
    ))
    db.execute(text("CREATE INDEX ix_cong_doan_may_cong_doan_id ON cong_doan_may (cong_doan_id)"))
    db.execute(text("CREATE INDEX ix_cong_doan_may_may_id ON cong_doan_may (may_id)"))
    db.commit()


MIGRATIONS.append(("0271_cong_doan_may", _migrate_cong_doan_may))
```

- [ ] **Step 9: Ghi `docs/DB_SCHEMA.md`**

Tìm mục bảng `cong_doan_dau_viec_vat_tu` trong `docs/DB_SCHEMA.md` và thêm ngay sau nó một mục cùng khuôn:

```markdown
### `cong_doan_may`

Máy chạy được một công đoạn, kèm cách đo giờ và cách tính giá của riêng cặp (công đoạn, máy).

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| `id` | Integer PK | |
| `cong_doan_id` | Integer FK → `cong_doan.id` | ON DELETE CASCADE |
| `may_id` | Integer | soft-ref → `may_thiet_bi.id` |
| `cong_thuc_gio` | Text | ra LƯỢNG theo đơn vị tốc độ của máy; trống = cầu quy đổi |
| `cong_thuc_gia` | Text | ra TIỀN, ghi đè `cong_doan.cong_thuc_gia` khi phiếu chọn máy này |
| `thu_tu` | Integer | thứ tự hiển thị |

Unique: `(cong_doan_id, may_id)` — `uq_cd_may`.
```

Đối chiếu đúng khuôn của các bảng khác trong file trước khi dán (đọc mục `cong_doan_dau_viec` để copy đúng định dạng cột/tiêu đề).

- [ ] **Step 10: Chạy test**

```bash
python -m pytest tests/test_cong_doan_may.py tests/test_cong_doan.py tests/test_schema_documented.py -q
```

Kỳ vọng: tất cả pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/models/cong_doan.py backend/app/models/__init__.py backend/app/schemas/cong_doan.py backend/app/repositories/cong_doan_repo.py backend/app/services/cong_doan_service.py backend/app/db_migrations.py backend/tests/test_cong_doan_may.py docs/DB_SCHEMA.md
git commit -m "Cong doan: them bang noi cong doan x may, mang cong thuc gio va cong thuc gia rieng"
```

---

## Task 2: Công thức tiền công và công thức định mức vật tư xuống hai bảng con

**Files:**
- Modify: `backend/app/models/cong_doan.py`
- Modify: `backend/app/schemas/cong_doan.py`
- Modify: `backend/app/repositories/cong_doan_repo.py`
- Modify: `backend/app/services/catalog_excel_specs.py`
- Modify: `backend/app/db_migrations.py`
- Modify: `docs/DB_SCHEMA.md`
- Test: `backend/tests/test_cong_doan_may.py` (thêm test)

**Interfaces:**
- Consumes: model `CongDoanMay` từ Task 1.
- Produces: cột `cong_doan_dau_viec.cong_thuc_khoan` (Text) và `cong_doan_dau_viec_vat_tu.cong_thuc_luong` (Text); schema `CongDoanDauViecVatTuIn(vat_tu_id: int, cong_thuc_luong: str | None)`; khoá `CongDoanDauViecIn.vat_tus: list[CongDoanDauViecVatTuIn]` **thay** `vat_tu_ids: list[int]`; migration `0272_cong_thuc_ve_cong_doan`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào cuối `backend/tests/test_cong_doan_may.py`:

```python
def test_dau_viec_giu_cong_thuc_tien_cong_va_moi_vat_tu_mot_cong_thuc(db):
    """Mực ăn theo SỐ TỜ, dung môi rửa máy ăn theo SỐ MÀU — cùng đầu việc, cùng ĐVT kg."""
    from app.models.cong_doan import CongDoanDauViec, CongDoanDauViecVatTu

    cd = _cd(db, "CD-M9")
    dv = CongDoanDauViec(
        piece_rate_id=1, nang_suat_nguoi_gio=100, so_nguoi_tieu_chuan=2,
        cong_thuc_khoan="sl_vao * so_luot_chay")
    dv.vat_tus.append(CongDoanDauViecVatTu(
        vat_tu_id=11, thu_tu=0, cong_thuc_luong="sl_vao / 40000"))
    dv.vat_tus.append(CongDoanDauViecVatTu(
        vat_tu_id=12, thu_tu=1, cong_thuc_luong="so_mau * 0.3"))
    cd.dau_viec_dinh_muc.append(dv)
    db.commit()
    db.refresh(cd)
    got = cd.dau_viec_dinh_muc[0]
    assert got.cong_thuc_khoan == "sl_vao * so_luot_chay"
    assert [v.cong_thuc_luong for v in got.vat_tus] == ["sl_vao / 40000", "so_mau * 0.3"]
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_cong_doan_may.py::test_dau_viec_giu_cong_thuc_tien_cong_va_moi_vat_tu_mot_cong_thuc -q
```

Kỳ vọng: FAIL với `TypeError: 'cong_thuc_khoan' is an invalid keyword argument`.

- [ ] **Step 3: Thêm hai cột vào model**

Trong `backend/app/models/cong_doan.py`, thêm vào `CongDoanDauViec` ngay sau `so_nguoi_tieu_chuan`:

```python
    # CÔNG THỨC TÍNH TIỀN CÔNG của đầu việc này TRONG công đoạn này (06/09/2026).
    #
    # Ra LƯỢNG theo đơn vị của ĐƠN GIÁ KHOÁN rồi engine mới nhân đơn giá — tên ô trên màn là
    # "Công thức tính tiền công" cho người khai dễ hiểu, nhưng giá trị nó trả là lượng.
    #
    # Vì sao chuyển từ `piece_rates.cong_thuc_luong` xuống đây: cùng một đầu việc làm ở hai công
    # đoạn khác nhau thì đếm khác nhau (in khổ lớn / khổ nhỏ), mà treo ở bảng đơn giá thì cả hai
    # buộc dùng chung một cách đo.
    #
    # ⚠️ VẪN GHÌM vào bước lệnh qua `khoan_snapshot` — sửa ở đây KHÔNG xê dịch tiền công của lệnh
    # đã phát. Muốn bước cũ ăn công thức mới thì chọn lại đầu việc ở bước đó.
    cong_thuc_khoan: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Thêm vào `CongDoanDauViecVatTu` ngay sau `thu_tu`:

```python
    # ĐỊNH MỨC của CHÍNH món này TRONG chính đầu việc này (06/09/2026) — ra LƯỢNG theo ĐVT của vật
    # tư. Trước đây khai ở `vat_tu_in_an.cong_thuc_luong` nên mọi công đoạn dùng món đó lĩnh chung
    # một con số: cùng "Mực Cyan" mà In khổ 79×109 ăn 1 kg / 8.000 tờ, In khổ 11×11 ăn 1 kg /
    # 40.000 tờ. Trống = chưa khai ⇒ bước lệnh KHÔNG bung dòng đó, kèm câu lý do (không đoán).
    cong_thuc_luong: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Xoá property `vat_tu_ids` khỏi `CongDoanDauViec` (khối `@property def vat_tu_ids`) — từ nay API nói bằng `vat_tus` để chở được công thức, giữ hai hình dạng là mời khai lệch.

- [ ] **Step 4: Chạy test, phải xanh**

```bash
python -m pytest tests/test_cong_doan_may.py -q
```

Kỳ vọng: 4 passed.

- [ ] **Step 5: Sửa schema**

Trong `backend/app/schemas/cong_doan.py`, thêm trước `class CongDoanDauViecIn`:

```python
class CongDoanDauViecVatTuIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    vat_tu_id: int
    # Định mức của CHÍNH món này trong CHÍNH đầu việc này — ra LƯỢNG theo ĐVT của vật tư.
    cong_thuc_luong: str | None = None
```

Trong `CongDoanDauViecIn`, **thay** khối `vat_tu_ids` bằng:

```python
    # CÔNG THỨC TÍNH TIỀN CÔNG của đầu việc này trong công đoạn này (06/09/2026) — ra LƯỢNG theo
    # đơn vị đơn giá khoán, engine nhân đơn giá sau. Ghim vào bước lệnh lúc chọn đầu việc.
    cong_thuc_khoan: str | None = None
    # VẬT TƯ đầu việc tiêu thụ. Trước 06/09/2026 chỉ là `vat_tu_ids: list[int]` (danh sách thuần);
    # nay mỗi dòng mang công thức định mức của riêng nó vì hai món cùng ĐVT ăn khác hẳn nhau.
    vat_tus: list[CongDoanDauViecVatTuIn] = Field(default_factory=list)
```

- [ ] **Step 6: Repo đọc `vat_tus`**

Trong `backend/app/repositories/cong_doan_repo.py`, sửa vòng lặp trong `_replace_dinh_muc`:

```python
        for r in rows:
            # `vat_tus` là DANH SÁCH CON, không phải cột — tách ra trước khi dựng model.
            r = dict(r)
            vts = r.pop("vat_tus", None) or []
            r.pop("id", None)          # khoá chỉ-đọc của schema Row, client có thể gửi ngược lên
            dv = CongDoanDauViec(**r)
            dv.vat_tus.extend(
                CongDoanDauViecVatTu(
                    vat_tu_id=int(v["vat_tu_id"]), thu_tu=i,
                    cong_thuc_luong=(v.get("cong_thuc_luong") or None),
                )
                for i, v in enumerate(vts)
            )
            cd.dau_viec_dinh_muc.append(dv)
```

- [ ] **Step 7: Sửa Excel spec**

Trong `backend/app/services/catalog_excel_specs.py`:

`_doc_dau_viec_hien_co` — thêm khoá công thức vào dict trả về, ngay sau `"so_nguoi_tieu_chuan"`:

```python
            "cong_thuc_khoan": dv.cong_thuc_khoan,
```

`_giu_dau_viec` — đổi thân hàm:

```python
def _giu_dau_viec(obj, ctx: NguCanh) -> list[dict]:
    """Định mức đầu việc ĐANG CÓ, đủ cả `vat_tus` — gán lại khi file KHÔNG có sheet đó.

    `CongDoanRepository._sau_gan` thay TRỌN bảng con mỗi lần ghi, kể cả khi khoá vắng mặt trong
    `data`; không gán lại là nhập một file thiếu sheet cũng xoá sạch định mức của mọi công đoạn.
    """
    ra = _doc_dau_viec_hien_co(obj, ctx)
    for dong, dv in zip(ra, getattr(obj, "dau_viec_dinh_muc", None) or [], strict=False):
        dong["vat_tus"] = [
            {"vat_tu_id": v.vat_tu_id, "cong_thuc_luong": v.cong_thuc_luong}
            for v in dv.vat_tus
        ]
    return ra
```

`_doc_vat_tu_dau_viec` — đổi thân hàm để chở thêm công thức:

```python
def _doc_vat_tu_dau_viec(obj, ctx: NguCanh) -> list[dict]:
    return [
        {"piece_rate_id": dv.piece_rate_id, "vat_tu_id": v.vat_tu_id,
         "cong_thuc_luong": v.cong_thuc_luong}
        for dv in (getattr(obj, "dau_viec_dinh_muc", None) or [])
        for v in dv.vat_tus
    ]
```

`_gop_vat_tu_dau_viec` — đổi thân hàm:

```python
def _gop_vat_tu_dau_viec(du_lieu: dict, rieng: dict, _ctx: NguCanh) -> None:
    """Nối sheet "Vật tư đầu việc" vào đúng dòng đầu việc (khoá: mã công việc khoán)."""
    dong = rieng.get("Vật tư đầu việc")
    if dong is None:
        return
    theo_dv: dict[Any, list[dict]] = {}
    for r in dong:
        if r.get("vat_tu_id"):
            theo_dv.setdefault(r.get("piece_rate_id"), []).append({
                "vat_tu_id": int(r["vat_tu_id"]),
                "cong_thuc_luong": (r.get("cong_thuc_luong") or None),
            })
    for dv in du_lieu.get("dau_viec_dinh_muc") or []:
        dv["vat_tus"] = theo_dv.get(dv.get("piece_rate_id"), [])
```

Trong `SheetCon("Đầu việc định mức", ...)`, thêm cột sau `Cot("Đơn vị năng suất", ...)`:

```python
                Cot("Công thức tính tiền công", "cong_thuc_khoan", rong=36),
```

Trong `SheetCon("Vật tư đầu việc", ...)` (tìm bằng `grep -n '"Vật tư đầu việc"' backend/app/services/catalog_excel_specs.py`), thêm cột cuối:

```python
                Cot("Công thức định mức", "cong_thuc_luong", rong=36),
```

Thêm `SheetCon` mới cho máy của công đoạn, ngay sau `SheetCon("Đầu việc định mức", ...)`. Dùng `TRA_MAY` nếu file đã có bộ tra máy theo mã; kiểm bằng `grep -n "TRA_" backend/app/services/catalog_excel_specs.py`. Nếu chưa có thì dựng theo đúng khuôn `TRA_DAU_VIEC` đang có trong file:

```python
        SheetCon(
            "Máy của công đoạn", field="may_lam_duoc",
            cot=(
                Cot("Mã máy", "may_id", doc=TRA_MAY.doc, ghi=TRA_MAY.ghi, rong=22),
                Cot("Công thức giờ chạy", "cong_thuc_gio", rong=36),
                Cot("Công thức giá", "cong_thuc_gia", rong=36),
            ),
        ),
```

- [ ] **Step 8: Migration 0272 (thêm cột + backfill)**

Cuối `backend/app/db_migrations.py`:

```python
def _migrate_cong_thuc_ve_cong_doan(db) -> None:
    """Hai ô công thức xuống bảng con của công đoạn + backfill từ hai ô cũ (06/09/2026).

    Nghiệp vụ: "việc này khoán theo lượng nào" và "món này ăn bao nhiêu" đều đổi theo TỪNG CÔNG
    ĐOẠN. Khai ở bảng đơn giá khoán / bảng vật tư thì mọi công đoạn dùng chung một con số — cùng
    "Mực Cyan" mà In khổ 79×109 ăn 1 kg / 8.000 tờ, In khổ 11×11 ăn 1 kg / 40.000 tờ.

    Backfill CHÉP XUỐNG, không đoán: mỗi dòng con nhận đúng công thức của nguồn nó đang trỏ tới,
    nên số của lệnh không đổi ngay sau khi chạy migration. Người dùng sửa lại từng công đoạn sau.
    Chỉ chép khi ô đích còn TRỐNG — chạy lại migration không đè cấu hình đã sửa tay.

    Raw SQL đích danh cột (không ORM): ORM full-select kéo cả cột do migration SAU thêm, vỡ deploy
    trên DB trung gian.
    """
    insp = inspect(db.get_bind())
    bang_co = set(insp.get_table_names())

    if "cong_doan_dau_viec" in bang_co:
        if "cong_thuc_khoan" not in _existing_columns(insp, "cong_doan_dau_viec"):
            db.execute(text("ALTER TABLE cong_doan_dau_viec ADD COLUMN cong_thuc_khoan TEXT"))
        if "piece_rates" in bang_co and "cong_thuc_luong" in _existing_columns(insp, "piece_rates"):
            db.execute(text(
                "UPDATE cong_doan_dau_viec SET cong_thuc_khoan = ("
                "  SELECT pr.cong_thuc_luong FROM piece_rates pr"
                "   WHERE pr.id = cong_doan_dau_viec.piece_rate_id) "
                "WHERE (cong_thuc_khoan IS NULL OR cong_thuc_khoan = '') "
                "  AND EXISTS (SELECT 1 FROM piece_rates pr"
                "               WHERE pr.id = cong_doan_dau_viec.piece_rate_id"
                "                 AND pr.cong_thuc_luong IS NOT NULL"
                "                 AND pr.cong_thuc_luong <> '')"
            ))

    if "cong_doan_dau_viec_vat_tu" in bang_co:
        if "cong_thuc_luong" not in _existing_columns(insp, "cong_doan_dau_viec_vat_tu"):
            db.execute(text(
                "ALTER TABLE cong_doan_dau_viec_vat_tu ADD COLUMN cong_thuc_luong TEXT"))
        if "vat_tu_in_an" in bang_co and "cong_thuc_luong" in _existing_columns(insp, "vat_tu_in_an"):
            db.execute(text(
                "UPDATE cong_doan_dau_viec_vat_tu SET cong_thuc_luong = ("
                "  SELECT vt.cong_thuc_luong FROM vat_tu_in_an vt"
                "   WHERE vt.id = cong_doan_dau_viec_vat_tu.vat_tu_id) "
                "WHERE (cong_thuc_luong IS NULL OR cong_thuc_luong = '') "
                "  AND EXISTS (SELECT 1 FROM vat_tu_in_an vt"
                "               WHERE vt.id = cong_doan_dau_viec_vat_tu.vat_tu_id"
                "                 AND vt.cong_thuc_luong IS NOT NULL"
                "                 AND vt.cong_thuc_luong <> '')"
            ))
    db.commit()


MIGRATIONS.append(("0272_cong_thuc_ve_cong_doan", _migrate_cong_thuc_ve_cong_doan))
```

⚠️ Backfill viết bằng **truy vấn con tương quan**, KHÔNG dùng `UPDATE ... FROM`. Lý do: `db_migrations.py` chưa có tiền lệ `UPDATE ... FROM` nào (đã tra), mà cả chục test kiểu `test_cong_viec_khoan_migration.py` gọi THẲNG hàm migration trên SQLite in-memory — cú pháp riêng của Postgres sẽ vỡ ngay khi ai đó viết test cho `0272`. Truy vấn con chạy đúng trên cả hai.

- [ ] **Step 9: Ghi `docs/DB_SCHEMA.md`**

Thêm dòng `cong_thuc_khoan | Text | công thức tính tiền công của đầu việc trong công đoạn này` vào bảng `cong_doan_dau_viec`, và dòng `cong_thuc_luong | Text | định mức món này trong đầu việc này` vào bảng `cong_doan_dau_viec_vat_tu`.

- [ ] **Step 10: Chạy test**

```bash
python -m pytest tests/test_cong_doan_may.py tests/test_cong_doan.py tests/test_import_excel.py tests/test_schema_documented.py -q
```

Test Excel sẽ đỏ ở chỗ khai `vat_tu_ids` — sửa các fixture trong `backend/tests/test_import_excel.py` sang hình dạng `vat_tus: [{"vat_tu_id": N, "cong_thuc_luong": None}]`. Tìm bằng `grep -n "vat_tu_ids" backend/tests/`.

- [ ] **Step 11: Commit**

```bash
git add backend/app/models/cong_doan.py backend/app/schemas/cong_doan.py backend/app/repositories/cong_doan_repo.py backend/app/services/catalog_excel_specs.py backend/app/db_migrations.py backend/tests docs/DB_SCHEMA.md
git commit -m "Cong doan: cong thuc tien cong xuong dau viec, cong thuc dinh muc xuong tung dong vat tu"
```

---

## Task 3: Giờ chạy đọc công thức của cặp (công đoạn × máy)

**Files:**
- Modify: `backend/app/services/lsx_service.py` (`sl_tinh_cua_buoc`, ~dòng 800–824)
- Test: `backend/tests/test_cong_thuc_ve_cong_doan.py` (tạo mới)

**Interfaces:**
- Consumes: `CongDoanMay.cong_thuc_gio` từ Task 1.
- Produces: method `LsxService._ct_gio_cua_may(cong_doan_id: int | None, may_id: int | None) -> str` trả chuỗi công thức hoặc `""`.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/test_cong_thuc_ve_cong_doan.py`. Dựng theo đúng khuôn `test_cong_thuc_luong_cua_MAY_ra_luong_theo_don_vi_toc_do` đang có ở `backend/tests/test_lsx_service.py:1900` — mở file đó đọc trước, dùng chung fixture `db, orders, lsx_svc, admin, customer`:

```python
"""Bốn công thức mới đọc ĐÚNG chỗ mới (06/09/2026) — xem plan 2026-09-06-doi-cong-thuc-ve-cong-doan."""
from __future__ import annotations

from app.models.cong_doan import CongDoan, CongDoanMay
from app.models.may_thiet_bi import MayThietBi

from tests.test_lsx_service import (  # noqa: F401 — fixture dùng chung
    admin, customer, db, lsx_svc, orders,
)


def test_gio_chay_doc_cong_thuc_cua_cap_cong_doan_va_may(db, orders, lsx_svc, admin, customer):
    """Cùng một máy, hai công đoạn ⇒ hai cách đo khác nhau. Đó là lý do bảng nối ra đời."""
    cd = CongDoan(ma="CD-G1", ten="In khổ nhỏ", nhom="print", don_vi_vao="to", don_vi_ra="to")
    may = MayThietBi(ma="MAY-G1", ten="Komori 5 màu", loai_may="Máy in",
                     toc_do=6000, don_vi_toc_do="to_gio")
    db.add_all([cd, may])
    db.flush()
    cd.may_lam_duoc.append(CongDoanMay(may_id=may.id, cong_thuc_gio="sl_vao * so_mau / 5",
                                       thu_tu=0))
    db.commit()

    class _Buoc:
        loai_buoc = "may"
        cong_doan_id = cd.id
        may_id = may.id
        so_luong_vao = 1000
        so_luong_ra = 1000
        don_vi_vao = "to"
        don_vi_ra = "to"
        so_luot_chay = 1
        khoan_json = None

    got = lsx_svc.sl_tinh_cua_buoc(_Buoc(), may, {"so_mau": 5})
    assert got is not None
    assert round(got[0]) == 1000, "1000 tờ × 5 màu ÷ 5 = 1000 lượt"


def test_may_khong_nam_trong_danh_sach_cong_doan_thi_lui_ve_cau_quy_doi(
        db, orders, lsx_svc, admin, customer):
    """Không khai cặp ⇒ không có công thức riêng ⇒ hành vi y như ô để trống hôm nay."""
    cd = CongDoan(ma="CD-G2", ten="Bế", nhom="finishing", don_vi_vao="to", don_vi_ra="to")
    may = MayThietBi(ma="MAY-G2", ten="Yawa 1050", loai_may="Bế",
                     toc_do=4000, don_vi_toc_do="to_gio")
    db.add_all([cd, may])
    db.commit()

    class _Buoc:
        loai_buoc = "may"
        cong_doan_id = cd.id
        may_id = may.id
        so_luong_vao = 800
        so_luong_ra = 800
        don_vi_vao = "to"
        don_vi_ra = "to"
        so_luot_chay = 1
        khoan_json = None

    got = lsx_svc.sl_tinh_cua_buoc(_Buoc(), may, {})
    assert got is not None and round(got[0]) == 800, "cùng đơn vị ⇒ cầu quy đổi trả nguyên số"
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py -q
```

Kỳ vọng: test đầu FAIL (chưa ai đọc `cong_thuc_gio`, số ra 1000 hay không tuỳ cầu quy đổi — nếu tình cờ xanh thì đổi công thức test thành `sl_vao * so_mau / 2` và kỳ vọng 2500 để phân biệt rõ).

- [ ] **Step 3: Thêm helper tra công thức giờ**

Trong `backend/app/services/lsx_service.py`, thêm method ngay TRƯỚC `sl_tinh_cua_buoc`:

```python
    def _ct_gio_cua_may(self, cong_doan_id, may_id) -> str:
        """Công thức GIỜ CHẠY của cặp (công đoạn, máy) — `""` khi cặp chưa khai.

        Nhớ trong `self._ct_gio_cache` vì `sl_tinh_cua_buoc` bị gọi cho TỪNG bước trong vòng lặp
        của bốn service ngoài (bài ghép · xếp lịch · kế hoạch vật tư); hỏi DB mỗi bước là N+1.
        """
        if not cong_doan_id or not may_id:
            return ""
        khoa = (int(cong_doan_id), int(may_id))
        if not hasattr(self, "_ct_gio_cache"):
            self._ct_gio_cache: dict[tuple[int, int], str] = {}
        if khoa not in self._ct_gio_cache:
            ct = self.db.execute(
                select(CongDoanMay.cong_thuc_gio).where(
                    CongDoanMay.cong_doan_id == khoa[0], CongDoanMay.may_id == khoa[1])
            ).scalar()
            self._ct_gio_cache[khoa] = (ct or "").strip()
        return self._ct_gio_cache[khoa]
```

Thêm `CongDoanMay` vào import model công đoạn ở đầu file (tìm dòng đang import `CongDoan`).

- [ ] **Step 4: Trỏ `sl_tinh_cua_buoc` sang chỗ mới**

Trong `sl_tinh_cua_buoc`, thay nhánh máy:

```python
        if loai in (LB_MAY, LB_THUE_NGOAI):
            dich = ma_don_vi_toc_do(may)
            # 06/09/2026: cách đo lấy từ cặp (CÔNG ĐOẠN × MÁY), không còn từ `may.cong_thuc_luong`.
            # Cùng một máy chạy hai công đoạn thì đo khác nhau — In khổ 79×109 và In khổ 11×11
            # không thể chung một công thức. Đọc SỐNG (không ghim): đổi máy là đổi cách đo.
            ct_rieng = self._ct_gio_cua_may(
                getattr(cd, "cong_doan_id", None), getattr(may, "id", None))
```

- [ ] **Step 5: Chạy test**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py -q
```

Kỳ vọng: 2 passed.

- [ ] **Step 6: Chạy test hồi quy vùng thời lượng**

```bash
python -m pytest tests/test_lsx_service.py tests/test_xep_lich_service.py tests/test_bai_ghep_service.py -q
```

Test `test_cong_thuc_luong_cua_MAY_ra_luong_theo_don_vi_toc_do` (~`test_lsx_service.py:1900`) và test cạnh nó ở dòng ~1963 sẽ đỏ vì gán `may.cong_thuc_luong`. Sửa chúng sang khai qua `CongDoanMay` — giữ nguyên số kỳ vọng, chỉ đổi chỗ khai; cập nhật docstring ghi rõ mốc `06/09/2026`. Cũng sửa `tests/test_lsx_service.py:845` (`may.cong_thuc_luong = "sl_vao * 0.559"`) và `tests/test_bai_ghep_service.py:1278,1469`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/lsx_service.py backend/tests
git commit -m "Gio chay doc cong thuc cua cap cong doan x may thay vi cua rieng may"
```

---

## Task 4: Tiền công ghim từ định mức đầu việc của công đoạn

**Files:**
- Modify: `backend/app/services/piece_work_service.py` (`khoan_snapshot`, ~dòng 62–85)
- Modify: `backend/app/services/lsx_service.py` (`_dinh_muc_snapshot` và hai chỗ gọi `khoan_snapshot`, ~dòng 549 và ~2901)
- Test: `backend/tests/test_cong_thuc_ve_cong_doan.py`

**Interfaces:**
- Consumes: `CongDoanDauViec.cong_thuc_khoan` từ Task 2.
- Produces: `khoan_snapshot(rate, dm=None) -> dict` — khi `dm` có `cong_thuc_khoan` thì ảnh chụp mang khoá `"cong_thuc"` lấy từ đó; không có `dm` thì ảnh chụp KHÔNG có khoá `"cong_thuc"`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_cong_thuc_ve_cong_doan.py`:

```python
def test_anh_chup_dau_viec_lay_cong_thuc_tu_dinh_muc_cua_cong_doan():
    """Ảnh chụp ghim CÔNG THỨC CỦA CÔNG ĐOẠN, không phải của bảng đơn giá khoán."""
    from types import SimpleNamespace

    from app.services.piece_work_service import khoan_snapshot

    rate = SimpleNamespace(id=7, ten="In offset", unit="to", unit_price=120)
    dm = SimpleNamespace(cong_thuc_khoan="sl_vao * so_luot_chay")

    assert "cong_thuc" not in khoan_snapshot(rate)
    assert khoan_snapshot(rate, dm)["cong_thuc"] == "sl_vao * so_luot_chay"
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py::test_anh_chup_dau_viec_lay_cong_thuc_tu_dinh_muc_cua_cong_doan -q
```

Kỳ vọng: FAIL với `TypeError: khoan_snapshot() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Sửa `khoan_snapshot`**

Trong `backend/app/services/piece_work_service.py`, đổi chữ ký và thân hàm (giữ nguyên phần dựng `snap` đang có, chỉ đổi nguồn công thức):

```python
def khoan_snapshot(rate, dm=None) -> dict:
```

và thay khối lấy công thức:

```python
    # `cong_thuc` (06/09/2026) lấy từ ĐỊNH MỨC ĐẦU VIỆC CỦA CÔNG ĐOẠN (`cong_doan_dau_viec.
    # cong_thuc_khoan`), không còn từ `piece_rates.cong_thuc_luong`: cùng một đầu việc làm ở hai
    # công đoạn khác nhau thì đếm khác nhau.
    #
    # ⚠️ VẪN GHÌM cùng lúc với đơn giá — sửa công thức ở danh mục KHÔNG xê dịch tiền công của lệnh
    # đã phát. Bước cũ muốn ăn công thức mới thì chọn lại đầu việc.
    if (ct := (getattr(dm, "cong_thuc_khoan", None) or "").strip()):
        snap["cong_thuc"] = ct
```

Cập nhật docstring của hàm cho khớp nguồn mới.

- [ ] **Step 4: Truyền `dm` vào hai chỗ gọi**

Trong `backend/app/services/lsx_service.py`:

Chỗ ~dòng 549 (trong `replace_routing`) — hiện là `row.khoan_json = khoan_snapshot(rate) if rate is not None else None`, ngay dưới đó đã có khối tra `dm`. Đảo thứ tự để `dm` có trước:

```python
                dm = next((x for x in (getattr(cd_obj, "dau_viec_dinh_muc", None) or [])
                           if rate is not None and x.piece_rate_id == rate.id), None)
                row.khoan_json = khoan_snapshot(rate, dm) if rate is not None else None
                if rate is not None and dm is not None:
                    row.khoan_json.update(_dinh_muc_snapshot(dm))
                    # KÍP theo CÔNG ĐOẠN, áp cho MỌI loại bước (06/09/2026). Còn NĂNG SUẤT
                    # người-giờ thì chỉ bước tổ mới chia — bước máy chia theo tốc độ máy.
                    _ke_thua("so_nhan_cong_tieu_chuan", int(dm.so_nguoi_tieu_chuan))
                    _ke_thua("so_nhan_cong", int(dm.so_nguoi_tieu_chuan))
```

Chỗ `_khoan_mac_dinh` (~dòng 549 khối `snap = khoan_snapshot(chosen)`): đổi thành

```python
        dm = assoc.get(chosen.id)
        snap = khoan_snapshot(chosen, dm)
        if dm is not None:
            snap.update(_dinh_muc_snapshot(dm))
        return snap
```

Chỗ ~dòng 2901 (`row.khoan_json = khoan_snapshot(rate) if rate is not None else None`): áp cùng khuôn — tra `dm` trước, truyền vào.

Chỗ ~dòng 731 (`kq_t = self._khoan_tu_kh(buoc, khoan_snapshot(rate), quy_cach)` — dropdown chấm điểm từng lựa chọn): tra `dm` của rate đó trong `cd_obj.dau_viec_dinh_muc` rồi truyền vào, nếu không dropdown sẽ hiện tiền khác với lúc lưu.

Chỗ `backend/app/services/bai_ghep_service.py:895` (`chung.khoan_json = khoan_snapshot(rate) if rate is not None else None`): khối ngay dưới đã tra `dm` (dòng 898) — đảo thứ tự y hệt.

- [ ] **Step 5: Chạy test**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py tests/test_lsx_service.py tests/test_bai_ghep_service.py -q
```

Các test đang gán `rate.cong_thuc_luong` (`test_lsx_service.py` dòng 1772, 1844, 1879, 1891) sẽ đỏ. Sửa chúng sang khai `cong_thuc_khoan` trên dòng `CongDoanDauViec` tương ứng, giữ nguyên số kỳ vọng.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/piece_work_service.py backend/app/services/lsx_service.py backend/app/services/bai_ghep_service.py backend/tests
git commit -m "Tien cong ghim tu dinh muc dau viec cua cong doan thay vi tu bang don gia khoan"
```

---

## Task 5: Định mức vật tư đọc công thức của từng dòng vật tư

**Files:**
- Modify: `backend/app/services/lsx_service.py` (`_vat_tu_bung` ~563–620, `_goi_y_luong_vat_tu` ~620–660, `_luong_vat_tu` ~660–710)
- Test: `backend/tests/test_cong_thuc_ve_cong_doan.py`

**Interfaces:**
- Consumes: `CongDoanDauViecVatTu.cong_thuc_luong` từ Task 2.
- Produces: `_luong_vat_tu(dvt, ctx, *, mat=None, cong_thuc="")` — công thức truyền vào thay cho đọc `mat.cong_thuc_luong`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_cong_thuc_ve_cong_doan.py`:

```python
def test_hai_vat_tu_cung_kg_trong_mot_dau_viec_an_theo_hai_cach(db, orders, lsx_svc, admin,
                                                                customer):
    """Mực ăn theo SỐ TỜ, dung môi rửa máy ăn theo SỐ MÀU — đúng ca đã bàn với chủ dự án."""
    from types import SimpleNamespace

    from app.models.cong_doan import CongDoanDauViec, CongDoanDauViecVatTu
    from app.models.vat_lieu_kho import VatTuInAn

    muc = VatTuInAn(ma="VT-MUC-C", ten="Mực offset Cyan", don_vi_gia="kg", active=True)
    dm_moi = VatTuInAn(ma="VT-DM-01", ten="Dung môi rửa máy in", don_vi_gia="kg", active=True)
    db.add_all([muc, dm_moi])
    db.flush()

    dv = CongDoanDauViec(piece_rate_id=1, nang_suat_nguoi_gio=100, so_nguoi_tieu_chuan=2)
    dv.vat_tus.append(CongDoanDauViecVatTu(
        vat_tu_id=muc.id, thu_tu=0, cong_thuc_luong="sl_vao / 40000"))
    dv.vat_tus.append(CongDoanDauViecVatTu(
        vat_tu_id=dm_moi.id, thu_tu=1, cong_thuc_luong="so_mau * 0.3"))
    db.add(dv)
    db.commit()

    buoc = SimpleNamespace(so_luong_vao=5000, so_luong_ra=5000, so_luot_chay=1)
    ra, canh_bao = lsx_svc._vat_tu_bung(dv, buoc, {"so_mau": 4})

    theo_ma = {r["ma"]: r["so_luong"] for r in ra}
    assert theo_ma["VT-MUC-C"] == 0.125, "5.000 tờ ÷ 40.000 = 0,125 kg"
    assert theo_ma["VT-DM-01"] == 1.2, "4 màu × 0,3 = 1,2 kg — KHÔNG dính số tờ"
    assert canh_bao == []


def test_dong_vat_tu_chua_khai_cong_thuc_thi_bo_ra_kem_ly_do(db, orders, lsx_svc, admin, customer):
    """KHÔNG ĐOÁN: thà người kế hoạch tự thêm còn hơn bung một con số sai trông như thật."""
    from types import SimpleNamespace

    from app.models.cong_doan import CongDoanDauViec, CongDoanDauViecVatTu
    from app.models.vat_lieu_kho import VatTuInAn

    keo = VatTuInAn(ma="VT-KEO-9", ten="Keo vào gáy", don_vi_gia="kg", active=True)
    db.add(keo)
    db.flush()
    dv = CongDoanDauViec(piece_rate_id=1, nang_suat_nguoi_gio=100, so_nguoi_tieu_chuan=1)
    dv.vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0, cong_thuc_luong=None))
    db.add(dv)
    db.commit()

    ra, canh_bao = lsx_svc._vat_tu_bung(
        dv, SimpleNamespace(so_luong_vao=100, so_luong_ra=100, so_luot_chay=1), {})
    assert ra == []
    assert len(canh_bao) == 1 and "Keo vào gáy" in canh_bao[0]
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py -k vat_tu -q
```

Kỳ vọng: FAIL — hiện `_luong_vat_tu` đọc `mat.cong_thuc_luong` (chưa khai) nên cả hai món rơi vào cảnh báo.

- [ ] **Step 3: Đổi `_luong_vat_tu` nhận công thức từ ngoài**

Trong `backend/app/services/lsx_service.py`, sửa chữ ký và hai dòng đầu thân hàm:

```python
    def _luong_vat_tu(self, dvt: str, ctx: dict, *,
                      mat=None, cong_thuc: str = "") -> tuple[float | None, str | None, str]:
        """Số lượng một vật tư đo bằng `dvt`. Trả `(số, diễn giải, lý do nếu tịt)`.

        MỘT đường duy nhất: công thức của DÒNG VẬT TƯ trong đầu việc của công đoạn
        (`cong_doan_dau_viec_vat_tu.cong_thuc_luong`, 06/09/2026) — nơi gọi truyền vào qua
        `cong_thuc`. Trước đó công thức treo ở CHÍNH MÓN HÀNG (`vat_tu_in_an.cong_thuc_luong`),
        nên mọi công đoạn dùng món đó lĩnh chung một con số: cùng "Mực Cyan" mà In khổ 79×109 ăn
        1 kg / 8.000 tờ, In khổ 11×11 ăn 1 kg / 40.000 tờ.

        Đường "quy đổi từ đơn vị của BƯỚC sang đơn vị vật tư" (BFS trên cầu quy đổi) GỠ 18/08/2026:
        cầu quy đổi chỉ được chở quan hệ BẤT BIẾN, còn "một tờ ăn mấy kg keo" đổi theo từng món và
        từng quy cách.

        KHÔNG ĐOÁN: chưa khai thì trả lý do kèm chỗ khai, drawer để ô trống cho người kế hoạch.
        """
        ten = getattr(mat, "ten", None) or dvt
        dv_ten = (self._don_vis().get(dvt.strip().lower()) or {}).get("ten") or dvt
        rieng = (cong_thuc or "").strip()
        if not rieng:
            return None, None, (
                f"chưa khai công thức định mức. Mở danh mục Công đoạn → sửa công đoạn → bảng "
                f"“Đầu việc và định mức của tổ” → bấm dòng “{ten}” trong khối vật tư → điền ô "
                f"“Công thức định mức” (ra {dv_ten}).")
```

Phần còn lại của hàm giữ nguyên.

- [ ] **Step 4: Truyền công thức từ `_vat_tu_bung`**

Trong `_vat_tu_bung`, sửa dòng gọi:

```python
            so_luong, dien_giai, ly_do = self._luong_vat_tu(
                dvt, ctx, mat=mat, cong_thuc=(v.cong_thuc_luong or ""))
```

- [ ] **Step 5: Sửa `_goi_y_luong_vat_tu`**

Hàm này quét TOÀN BỘ danh mục vật tư để gợi ý số khi người kế hoạch chọn một món mới — nó không đứng trong một đầu việc nào nên không có công thức để mượn. Đổi thân hàm để nói thẳng điều đó thay vì trả một danh sách "chưa khai" dài dằng dặc:

```python
    def _goi_y_luong_vat_tu(self, buoc, quy_cach: dict | None) -> list[dict]:
        """`[{vat_tu_id, so_luong, dien_giai, ly_do}]` cho MỌI vật tư đang dùng, theo bước này.

        Từ 06/09/2026 định mức khai theo DÒNG VẬT TƯ TRONG ĐẦU VIỆC của công đoạn, nên một món
        đứng ngoài mọi đầu việc thì không có công thức nào để gợi ý — trả `so_luong=None` kèm lý do
        chỉ thẳng chỗ khai. Món ĐANG nằm trong đầu việc của chính bước này thì mượn công thức của
        dòng đó, để chọn lại đúng món đã khai vẫn ra số ngay.
        """
        sl = _f(getattr(buoc, "so_luong_vao", 0))
        if sl <= 0:
            return []
        ctx = {**ngu_canh_lenh(quy_cach or {}), **MAC_DINH_TANG_LENH,
               "sl_vao": sl, "sl_ra": _f(getattr(buoc, "so_luong_ra", 0)),
               "so_luot_chay": float(max(int(getattr(buoc, "so_luot_chay", 1) or 1), 1))}
        # Công thức của những món ĐÃ khai trong đầu việc đang gắn ở bước này.
        ct_theo_mon: dict[int, str] = {}
        kh = getattr(buoc, "khoan_json", None) or {}
        rate_id = int(kh.get("rate_id") or 0)
        cd_obj = (self.db.get(CongDoan, buoc.cong_doan_id)
                  if getattr(buoc, "cong_doan_id", None) else None)
        if cd_obj is not None and rate_id:
            for dv in (getattr(cd_obj, "dau_viec_dinh_muc", None) or []):
                if dv.piece_rate_id == rate_id:
                    ct_theo_mon = {v.vat_tu_id: (v.cong_thuc_luong or "") for v in dv.vat_tus}
                    break
        ra: list[dict] = []
        for mat in self.db.execute(
            select(VatTuInAn).where(VatTuInAn.active.is_(True))
        ).scalars():
            dvt = (mat.don_vi_gia or "").strip()
            if not dvt:
                continue
            so_luong, dien_giai, ly_do = self._luong_vat_tu(
                dvt, ctx, mat=mat, cong_thuc=ct_theo_mon.get(mat.id, ""))
            ra.append({
                "vat_tu_id": mat.id,
                "so_luong": None if so_luong is None else round(so_luong, 3),
                "dien_giai": dien_giai,
                "ly_do": ly_do or None,
            })
        return ra
```

`MAC_DINH_TANG_LENH` đến từ Task 8 — cho tới lúc đó dùng `KHUON_MAC_DINH` và bỏ khoá `so_luot_chay`; Task 8 sẽ quay lại đổi. Ghi một dòng `# Task 8 đổi sang MAC_DINH_TANG_LENH` để không quên.

Trong `_vat_tu_bung` cũng thêm `"so_luot_chay"` vào `ctx` theo đúng cách trên.

- [ ] **Step 6: Chạy test**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py tests/test_lsx_service.py tests/test_ke_hoach_vat_tu.py -q
```

Các test ở `test_lsx_service.py` dòng 1257, 1327, 1351, 1377, 1418, 1451, 1487, 1732 đang gán `VatTuInAn(cong_thuc_luong=...)` sẽ đỏ. Sửa từng cái sang khai `cong_thuc_luong` trên dòng `CongDoanDauViecVatTu` tương ứng, giữ nguyên số kỳ vọng. Test `test_cong_thuc_luong_cua_VAT_TU_thang_cong_thuc_cua_don_vi` (dòng 1397) nói về một luật đã gỡ từ mg `0215` — đổi tên thành `test_dinh_muc_vat_tu_lay_tu_dong_cua_dau_viec` và viết lại docstring theo luật mới.

`test_ke_hoach_vat_tu.py` dòng 1398/1400 gán `kem.cong_thuc_luong` / `mang.cong_thuc_luong` — hai món này đi đường BOM của bước nên cũng phải chuyển. Dòng 97/102/590 là GIẤY (`GiayNguyen`) — **giữ nguyên**, giấy không đổi.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/lsx_service.py backend/tests
git commit -m "Dinh muc vat tu doc cong thuc cua tung dong vat tu trong dau viec cua cong doan"
```

---

## Task 6: Công thức giá của máy ghi đè công thức giá của công đoạn

**Files:**
- Modify: `backend/app/services/tinh_gia_service.py` (`_cong_doan_to_dict` ~31–65, vòng lặp `thanh_phams` ~165–175)
- Test: `backend/tests/test_cong_thuc_ve_cong_doan.py`

**Interfaces:**
- Consumes: `CongDoanMay.cong_thuc_gia` từ Task 1.
- Produces: `_cong_doan_to_dict(cd, tram=None, *, ct_gia_may: str | None = None) -> dict`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_cong_thuc_ve_cong_doan.py`:

```python
def test_cong_thuc_gia_cua_may_ghi_de_cua_cong_doan(db):
    """Máy 5 màu khổ lớn và máy 2 màu khổ nhỏ có đơn giá khác nhau — nên giá phải theo máy."""
    from app.services.tinh_gia_service import _cong_doan_to_dict

    cd = CongDoan(ma="CD-P1", ten="In AB", nhom="print", cong_thuc_gia="to_dau_vao * 300")
    db.add(cd)
    db.commit()

    assert _cong_doan_to_dict(cd)["cong_thuc_gia"] == "to_dau_vao * 300"
    assert _cong_doan_to_dict(cd, ct_gia_may="to_dau_vao * 180")["cong_thuc_gia"] \
        == "to_dau_vao * 180"
    # Cặp có dòng nhưng ô công thức để TRỐNG ⇒ vẫn dùng công thức chung, không về rỗng.
    assert _cong_doan_to_dict(cd, ct_gia_may="")["cong_thuc_gia"] == "to_dau_vao * 300"
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py::test_cong_thuc_gia_cua_may_ghi_de_cua_cong_doan -q
```

Kỳ vọng: FAIL với `TypeError: _cong_doan_to_dict() got an unexpected keyword argument 'ct_gia_may'`.

- [ ] **Step 3: Sửa `_cong_doan_to_dict`**

```python
def _cong_doan_to_dict(cd: CongDoan, tram: dict[str, str] | None = None,
                       *, ct_gia_may: str | None = None) -> dict:
```

và đổi dòng bơm công thức:

```python
        # 06/09/2026: công thức của CẶP (công đoạn, máy) thắng công thức chung của công đoạn — mỗi
        # máy in một đơn giá. Chỉ thắng khi cặp đó THẬT SỰ khai; cặp có dòng mà ô trống thì vẫn
        # dùng công thức chung, không để phiếu ra 0đ vì một ô người ta cố ý bỏ trống.
        "cong_thuc_gia": (ct_gia_may or "").strip() or cd.cong_thuc_gia,
```

- [ ] **Step 4: Truyền công thức của máy từ vòng lặp thành phần**

Trong cùng file, ngay TRƯỚC vòng `for row in sorted(tp.thanh_phams, ...)`, thêm:

```python
    # Máy in được chọn ở khối In của THÀNH PHẦN (`PhieuThanhPhan.may_id`) — đây là chỗ DUY NHẤT
    # phiếu tính giá chọn máy, nên chỉ dòng công đoạn nhóm In mới có cơ hội ăn công thức riêng.
    # Đọc MỘT lần cho cả thành phần, không hỏi lại từng dòng.
    ct_gia_theo_cd: dict[int, str] = {}
    if tp.may_id is not None:
        ct_gia_theo_cd = {
            int(cd_id): (ct or "")
            for cd_id, ct in db.execute(
                select(CongDoanMay.cong_doan_id, CongDoanMay.cong_thuc_gia)
                .where(CongDoanMay.may_id == int(tp.may_id))
            ).all()
        }
```

và đổi dòng gọi:

```python
                rd["cong_doan"] = _cong_doan_to_dict(
                    cd, tram, ct_gia_may=ct_gia_theo_cd.get(cd.id))
```

Thêm import `CongDoanMay` và `select` ở đầu file nếu thiếu.

- [ ] **Step 5: Chạy test**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py tests/test_phieu_tinh_gia.py tests/test_catalog_costing_read.py -q
```

Kỳ vọng: tất cả pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tinh_gia_service.py backend/tests
git commit -m "Phieu tinh gia: cong thuc gia cua may ghi de cong thuc gia cua cong doan"
```

---

## Task 7: Ô "Số lượt chạy qua máy" hiện ở mọi loại bước, mặc định 1

**Files:**
- Modify: `backend/app/services/lsx_service.py` (~dòng 365)
- Modify: `frontend/src/pages/lsxBuoc.ts` (~dòng 547)
- Modify: `frontend/src/pages/LsxBuocDrawer.tsx` (~dòng 1350–1370)
- Test: `backend/tests/test_cong_thuc_ve_cong_doan.py`, `backend/tests/test_khsx_ui_contract.py`

**Interfaces:**
- Produces: `so_luot_chay` luôn là số nguyên ≥ 1 trong dict bước (không còn `None` cho bước tổ) — Task 8 dựa vào đây để bơm chip.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_cong_thuc_ve_cong_doan.py`:

Dòng cần đổi nằm trong `thoi_luong_buoc(cd, may=None, sl_tinh=None)` — hàm MODULE-LEVEL ở `backend/app/services/lsx_service.py:226`, nhận `cd` kiểu vịt nên test được thẳng bằng `SimpleNamespace`, không cần fixture DB. Mẫu có sẵn: `backend/tests/test_dong_giay.py:307-322`.

```python
def test_buoc_to_van_bao_so_luot_chay_mac_dinh_mot():
    """Chủ chốt 06/09/2026: "mặc định là 1 cái số lượt qua máy ấy cho dù chọn loại bước là tổ".

    Trước đó `thoi_luong_buoc` ép `None` cho bước tổ, nên chip `so_luot_chay` trong công thức tiền
    công không có số nào để thế — mà tiền công thì CHỈ tính ở bước tổ.
    """
    from types import SimpleNamespace

    from app.services.lsx_service import thoi_luong_buoc

    to = SimpleNamespace(
        loai_buoc="to", so_luot_chay=2, nang_suat=100, so_nhan_cong=2,
        so_nhan_cong_tieu_chuan=2, phat_sinh_phut=0, so_luong_vao=1000,
        don_vi_vao="to", khoan_json={})
    dg = thoi_luong_buoc(to, None, (1000.0, "to", ""))["dien_giai"]
    assert dg["so_luot_chay"] == 2

    to.so_luot_chay = None      # chưa khai ⇒ hiểu là 1, không phải "không có"
    assert thoi_luong_buoc(to, None, (1000.0, "to", ""))["dien_giai"]["so_luot_chay"] == 1


def test_so_luot_KHONG_nhan_vao_gio_cua_buoc_to():
    """Khoá lại quyết định 06/09/2026: nhánh tổ giữ nguyên công thức, KHÔNG nhân lượt.

    Nhánh máy `_chay` có `× luot`, nhánh tổ `_chay_to` thì không. Đổi nhánh tổ là làm mọi bước tổ
    đang có đổi giờ ngay lần deploy kế — ngoài phạm vi. Số lượt ở bước tổ chỉ đi vào TIỀN CÔNG.
    """
    from types import SimpleNamespace

    from app.services.lsx_service import thoi_luong_buoc

    def _phut(luot):
        to = SimpleNamespace(
            loai_buoc="to", so_luot_chay=luot, nang_suat=100, so_nhan_cong=1,
            so_nhan_cong_tieu_chuan=1, phat_sinh_phut=0, so_luong_vao=1000,
            don_vi_vao="to", khoan_json={})
        return thoi_luong_buoc(to, None, (1000.0, "to", ""))["chiem_may_phut"]

    assert _phut(2) == _phut(1), "bước tổ: đổi số lượt KHÔNG đổi giờ"
```

⚠️ Kiểm tên khoá trả về (`dien_giai`, `chiem_may_phut`) bằng cách đọc phần `return` cuối `thoi_luong_buoc` trước khi chạy — hàm trả dict phẳng hay lồng thì assert phải bám đúng.

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py -k so_luot -q
```

Kỳ vọng: FAIL vì bước tổ trả `None`.

- [ ] **Step 3: Bỏ luật ép `None` ở backend**

Dòng ~365 của `backend/app/services/lsx_service.py`:

```python
        # 06/09/2026: MỌI loại bước đều có số lượt, mặc định 1. Trước đó bước tổ bị ép `None` —
        # nhưng công thức tiền công (chỉ chạy ở bước tổ) cần chip `so_luot_chay` có số thật.
        "so_luot_chay": luot,
```

- [ ] **Step 4: Bỏ luật ép `null` ở frontend**

`frontend/src/pages/lsxBuoc.ts` dòng ~547:

```ts
    // 06/09/2026: bước tổ cũng gửi số lượt (mặc định 1) — chip `so_luot_chay` của công thức tiền
    // công cần số thật, mà tiền công chỉ tính ở bước tổ.
    so_luot_chay: luot,
```

`frontend/src/pages/LsxBuocDrawer.tsx`: tìm khối bọc ô "SỐ LƯỢT CHẠY QUA MÁY" bằng `grep -n "SỐ LƯỢT CHẠY QUA MÁY" frontend/src/pages/LsxBuocDrawer.tsx`, rồi bỏ điều kiện ẩn theo `loai_buoc` (nếu có). Giữ hint cũ cho bước máy; với bước tổ (`row.loai_buoc === "to"`) đổi hint thành đúng câu nói rõ giới hạn, để người kế hoạch không tưởng nhầm là giờ cũng đổi:

```
Số lần hàng đi qua bước này — mặc định 1. Ở bước tổ, số này chỉ vào công thức tính tiền công; giờ của bước KHÔNG đổi theo.
```

- [ ] **Step 5: Chạy test**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py tests/test_lsx_service.py tests/test_khsx_ui_contract.py -q
```

Từ `frontend/`:

```bash
npx tsc --noEmit
```

`test_khsx_ui_contract.py` là test đối chiếu CHUỖI trong mã nguồn FE — nếu nó đỏ vì hint đổi thì cập nhật chuỗi kỳ vọng kèm comment mốc `06/09/2026`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/lsx_service.py frontend/src/pages/lsxBuoc.ts frontend/src/pages/LsxBuocDrawer.tsx backend/tests
git commit -m "So luot chay qua may hien o moi loai buoc, mac dinh 1"
```

---

## Task 8: Chip `so_luot_chay` vào từ điển biến

**Files:**
- Modify: `backend/app/services/bien_cong_thuc.py`
- Modify: `backend/app/services/lsx_service.py` (mọi chỗ bơm `KHUON_MAC_DINH`)
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py` (~dòng 322)
- Test: `backend/tests/test_bien_cong_thuc.py`

**Interfaces:**
- Consumes: `so_luot_chay` luôn ≥ 1 từ Task 7.
- Produces: chip `so_luot_chay` thuộc `LOAI_QUY_DOI`; hằng `MAC_DINH_TANG_LENH: dict[str, float]` = `KHUON_MAC_DINH` cộng `{"so_luot_chay": 1.0}`.

- [ ] **Step 1: Viết test đỏ**

Sửa `backend/tests/test_bien_cong_thuc.py`:

```python
    assert dem == {LOAI_GIAY: 19, LOAI_VAT_TU: 18, LOAI_CONG_DOAN: 22, LOAI_QUY_DOI: 24}, dem
```

và tìm định nghĩa `CUA_BUOC` trong file, thêm `"so_luot_chay"`:

```python
# 06/09/2026: `so_luot_chay` là chip TẦNG BƯỚC thứ sáu, CHỈ mở ở ô quy đổi (giờ chạy · tiền công ·
# định mức vật tư). KHÔNG mở ở ô công đoạn: tầng phiếu tính giá đã có `so_mat`, và engine tiền
# chưa bơm số lượt trong vòng lặp bước của nó — mở ra là công thức giá ăn NameError.
CUA_BUOC = frozenset({"sl_vao", "sl_ra", "dai_khuon", "rong_khuon", "so_khuon", "so_luot_chay"})
```

Sửa dòng 98 cho khớp: `assert ma_hop_le(LOAI_QUY_DOI) - chung == {"dinh_luong"} | CUA_BUOC`.

Sửa dòng 105–106: `so_luot_chay` không thuộc `LOAI_CONG_DOAN` nên `CUA_BUOC <= ma_hop_le(LOAI_CONG_DOAN)` sẽ sai — đổi thành:

```python
    assert (CUA_BUOC - {"so_luot_chay"}) <= ma_hop_le(LOAI_CONG_DOAN)
    assert CUA_BUOC <= ma_hop_le(LOAI_QUY_DOI)
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_bien_cong_thuc.py -q
```

Kỳ vọng: FAIL ở `dem` — Quy đổi đang là 23.

- [ ] **Step 3: Khai chip**

Trong `backend/app/services/bien_cong_thuc.py`, thêm vào `_BANG` ngay sau `sl_ra`:

```python
    # SỐ LƯỢT của chính bước (06/09/2026). Nguồn: ô "Số lượt chạy qua máy" ở drawer bước, nay hiện
    # cho MỌI loại bước với mặc định 1. In trở 2 mặt = 2 lượt ⇒ công thợ và mực đều gấp đôi.
    #
    # KHÔNG mở cho ô công đoạn (công thức TIỀN): engine tiền chưa bơm số lượt trong vòng lặp bước,
    # mở ra là công thức giá vỡ NameError. Tầng đó đã có `so_mat` nói cùng một chuyện.
    #
    # ⚠️ ĐỪNG gõ chip này vào công thức GIỜ CHẠY của máy: engine ĐÃ tự nhân số lượt vào giờ máy
    # (`SL ÷ tốc độ × lượt` ở `thoi_luong_buoc`). Viết `sl_vao * so_luot_chay` ở đó là đếm HAI LẦN.
    ("so_luot_chay", "Số lượt qua máy", "Số lần hàng đi qua chính bước này (in trở 2 mặt = 2)",
     "lượt", "ô Số lượt chạy qua máy của bước — mặc định 1", (LOAI_QUY_DOI,)),
```

Thêm chip vào `_TANG_BUOC`:

```python
_TANG_BUOC: frozenset[str] = frozenset(
    {"sl_vao", "sl_ra", "dai_khuon", "rong_khuon", "so_khuon", "so_luot_chay"}
)
```

Thêm hằng ngay sau `KHUON_MAC_DINH`:

```python
# Mặc định cho MỌI chip tầng bước khi chạy ở TẦNG LỆNH (không đứng trong một bước cụ thể) — vd
# công thức lượng của GIẤY ở kế hoạch vật tư. Nơi nào BIẾT bước thì bơm số thật đè lên.
MAC_DINH_TANG_LENH: dict[str, float] = {**KHUON_MAC_DINH, "so_luot_chay": 1.0}
```

- [ ] **Step 4: Bơm giá trị ở mọi nơi gọi**

Đổi mọi chỗ `{**ngu_canh_lenh(...), **KHUON_MAC_DINH, ...}` sang `MAC_DINH_TANG_LENH`. Tìm bằng:

```bash
grep -rn "KHUON_MAC_DINH" backend/app
```

Ở `backend/app/services/lsx_service.py` (`_sl_theo_don_vi`, `_khoan_theo_cong_thuc`, `_vat_tu_bung`, `_goi_y_luong_vat_tu`) phải bơm số THẬT đè lên mặc định:

```python
               "so_luot_chay": float(max(int(getattr(cd, "so_luot_chay", 1) or 1), 1)),
```

(đổi `cd` thành đúng tên biến bước ở từng hàm).

Ở `backend/app/services/ke_hoach_vat_tu_service.py` dòng ~322 chỉ đổi hằng — đường đó chạy ở tầng lệnh cho GIẤY, không có bước nào để hỏi.

Sửa cả import của các file đó.

- [ ] **Step 5: Chạy test**

```bash
python -m pytest tests/test_bien_cong_thuc.py tests/test_quy_doi.py tests/test_lsx_service.py tests/test_ke_hoach_vat_tu.py tests/test_cong_thuc_ve_cong_doan.py -q
```

Kỳ vọng: tất cả pass. Chip tự hiện trên UI vì frontend nạp danh sách từ `GET /api/bien-cong-thuc`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/bien_cong_thuc.py backend/app/services/lsx_service.py backend/app/services/ke_hoach_vat_tu_service.py backend/tests
git commit -m "Them chip so_luot_chay cho o cong thuc quy doi, bom gia tri o moi tang"
```

---

## Task 9: Khối "Máy chạy được công đoạn này" trong drawer Công đoạn

**Files:**
- Create: `frontend/src/pages/danh-muc/fields/MayCuaCongDoan.tsx`
- Modify: `frontend/src/pages/danh-muc/fields/index.ts`
- Modify: `frontend/src/pages/danh-muc/types.ts`
- Modify: `frontend/src/pages/danh-muc/CatalogDrawer.tsx`
- Modify: `frontend/src/pages/rebuildCatalogConfigs.tsx`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/pages/danh-muc/fields/MayCuaCongDoan.test.tsx` (tạo mới)

**Interfaces:**
- Consumes: API `may_lam_duoc: CongDoanMayRow[]` từ Task 1.
- Produces: field type `"may-cua-cong-doan"` trong `rebuildCatalogConfigs`; kiểu TS `MayCongDoanRow { may_id: number; cong_thuc_gio?: string | null; cong_thuc_gia?: string | null }`.

- [ ] **Step 1: Thêm kiểu TS**

Trong `frontend/src/pages/danh-muc/types.ts`:

```ts
/** Một MÁY chạy được công đoạn, mang cách đo giờ và cách tính giá của riêng cặp (công đoạn, máy).
 *  Vì sao không treo ở máy: cùng một máy chạy hai công đoạn thì đo khác nhau (06/09/2026). */
export interface MayCongDoanRow {
  may_id: number;
  cong_thuc_gio?: string | null;
  /** Chỉ có nghĩa với công đoạn nhóm In — phiếu tính giá chỉ chọn máy ở khối In của thành phần. */
  cong_thuc_gia?: string | null;
}
```

Trong `frontend/src/api/client.ts`, thêm `may_lam_duoc?: MayCongDoanRow[] | null;` vào interface công đoạn (cạnh `nhom_may_cho_phep`, dòng ~5505).

- [ ] **Step 2: Viết test đỏ**

Tạo `frontend/src/pages/danh-muc/fields/MayCuaCongDoan.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { MayCuaCongDoanField } from "./MayCuaCongDoan";
import { AuthContext, type AuthState } from "../../../auth/AuthContext";

// `token: null` ⇒ `useBienCongThuc` bên trong `FormulaField` KHÔNG gọi API (từ điển rỗng, chip
// hiện mã thay nhãn). Đúng mẫu `frontend/src/pages/FormulaField.test.tsx:20-26`.
const AUTH: AuthState = {
  status: "anonymous", user: null, token: null,
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const MAY = [
  { id: 1, ma: "MAY-01", ten: "Komori 5 màu", loai_may: "Máy in" },
  { id: 2, ma: "MAY-02", ten: "Yawa 1050", loai_may: "Bế" },
];

function bay(props: Parameters<typeof MayCuaCongDoanField>[0]) {
  return render(
    <AuthContext.Provider value={AUTH}><MayCuaCongDoanField {...props} /></AuthContext.Provider>,
  );
}

describe("MayCuaCongDoanField", () => {
  it("chỉ bày máy thuộc nhóm đã tick", () => {
    bay({ value: [], options: MAY, nhomChoPhep: ["Máy in"], nhomCongDoan: "print",
          onChange: () => {} });
    expect(screen.getByText(/Komori 5 màu/)).toBeInTheDocument();
    expect(screen.queryByText(/Yawa 1050/)).not.toBeInTheDocument();
  });

  it("bấm dòng máy thì bung panel hai ô công thức", async () => {
    const user = userEvent.setup();
    bay({ value: [{ may_id: 1 }], options: MAY, nhomChoPhep: ["Máy in"], nhomCongDoan: "print",
          onChange: () => {} });
    await user.click(screen.getByRole("button", { name: /Komori 5 màu/ }));
    // `nhanO` render ra `<span className="rc-formula__editor-label">`, KHÔNG phải `<label for>`
    // ⇒ dùng `getByText`, `getByLabelText` sẽ không thấy.
    expect(screen.getByText("Công thức giờ chạy")).toBeInTheDocument();
    expect(screen.getByText("Công thức giá")).toBeInTheDocument();
  });

  it("công đoạn KHÔNG thuộc nhóm In thì không có ô công thức giá", async () => {
    const user = userEvent.setup();
    bay({ value: [{ may_id: 2 }], options: MAY, nhomChoPhep: ["Bế"], nhomCongDoan: "finishing",
          onChange: () => {} });
    await user.click(screen.getByRole("button", { name: /Yawa 1050/ }));
    expect(screen.getByText("Công thức giờ chạy")).toBeInTheDocument();
    expect(screen.queryByText("Công thức giá")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Chạy test để chắc nó đỏ**

Từ `frontend/`:

```bash
npx vitest run src/pages/danh-muc/fields/MayCuaCongDoan.test.tsx
```

Kỳ vọng: FAIL — file component chưa tồn tại.

- [ ] **Step 4: Viết component**

Tạo `frontend/src/pages/danh-muc/fields/MayCuaCongDoan.tsx`. Đọc `DinhMucDauViec.tsx` trước để copy đúng class CSS và lối bung hàng phụ; đọc `FormulaField.tsx` để biết cách nhúng ô soạn công thức (`loaiO: "quy_doi"` cho giờ chạy, `"cong_doan"` cho giá).

```tsx
// MÁY chạy được công đoạn này, mỗi dòng mang cách đo GIỜ và cách tính GIÁ của riêng cặp đó.
//
// Vì sao là bảng ở đây chứ không phải cột trên máy (06/09/2026): cùng một máy chạy hai công đoạn
// thì đo khác nhau — In khổ 79×109 và In khổ 11×11 không thể chung một công thức. Cùng lẽ đó,
// đơn giá cũng theo máy: máy 5 màu khổ lớn và máy 2 màu khổ nhỏ có giá khác nhau.
//
// Hàng tick "Máy làm được công đoạn này" (nhóm máy) nay chỉ là BỘ LỌC cho bảng này.
import { Fragment, useMemo, useState } from "react";

import { TrashIcon } from "../icons";
import type { MayCongDoanRow, Row } from "../types";
import { FormulaField } from "./FormulaField";

export function MayCuaCongDoanField({ value, options, nhomChoPhep, nhomCongDoan, onChange }: {
  value: MayCongDoanRow[]; options: Row[]; nhomChoPhep: string[];
  nhomCongDoan: string; onChange: (v: MayCongDoanRow[]) => void;
}) {
  const chon = Array.isArray(value) ? value : [];
  // Nhóm chưa tick ⇒ bày MỌI máy: "chưa khai = không ràng buộc", cùng luật với nơi gán máy ở bước.
  const duocChon = useMemo(
    () => (nhomChoPhep.length === 0
      ? options
      : options.filter((o) => nhomChoPhep.includes(String(o.loai_may)))),
    [options, nhomChoPhep],
  );
  const theoId = useMemo(() => new Map(options.map((o) => [Number(o.id), o])), [options]);
  const daChon = new Set(chon.map((r) => r.may_id));
  const [mo, setMo] = useState<number | null>(null);
  const patch = (i: number, p: Partial<MayCongDoanRow>) =>
    onChange(chon.map((r, j) => (j === i ? { ...r, ...p } : r)));
  // Chỉ công đoạn nhóm In mới có ô giá: phiếu tính giá chỉ chọn máy ở khối In của thành phần, nên
  // công thức giá khai cho máy bế/cán sẽ không có đường nào chảy tới. Dùng ENUM nhóm công đoạn
  // (`print`) chứ KHÔNG so tên nhóm máy — tên nhóm máy là danh mục người dùng sửa được.
  const coOGia = nhomCongDoan === "print";

  return <div className="rc-bands rc-bands--dinh-muc">
    <div className="rc-dinh-muc-wrapper">
      <table className="rc-dinh-muc-table">
        <thead><tr>
          <th className="rc-col--left">Máy</th>
          <th className="rc-col--left">Cách đo giờ chạy</th>
          {coOGia && <th className="rc-col--left">Cách tính giá</th>}
          <th className="rc-col--center" style={{ width: 36 }} />
        </tr></thead>
        <tbody>
          {chon.length === 0 && <tr><td colSpan={coOGia ? 4 : 3} className="rc-bands__empty">
            {duocChon.length === 0
              ? "Chưa có máy nào thuộc nhóm đã tick ở trên."
              : "Chưa chọn máy nào cho công đoạn này."}
          </td></tr>}
          {chon.map((r, i) => {
            const may = theoId.get(r.may_id);
            const dangMo = mo === r.may_id;
            return <Fragment key={r.may_id}>
              <tr>
                <td className="rc-col--left rc-dinh-muc-name">
                  <button type="button" className="rc-dm-vt__pill" onClick={() => setMo(dangMo ? null : r.may_id)}>
                    {may ? `${String(may.ma)} · ${String(may.ten)}` : `#${r.may_id}`}
                  </button>
                </td>
                <td className="rc-col--left rc-dinh-muc-unit">{r.cong_thuc_gio || "—"}</td>
                {coOGia && <td className="rc-col--left rc-dinh-muc-unit">{r.cong_thuc_gia || "—"}</td>}
                <td className="rc-col--center">
                  <button type="button" className="rc-bands__del"
                    onClick={() => onChange(chon.filter((_, j) => j !== i))}><TrashIcon /></button>
                </td>
              </tr>
              {dangMo && <tr className="rc-dm-vt__row"><td colSpan={coOGia ? 4 : 3}>
                <div className="rc-dm-vt">
                  {/* `id` phải DUY NHẤT: bảng có thể mở nhiều panel, trùng id là hai ô dính nhau. */}
                  <FormulaField
                    id={`ct-gio-${r.may_id}`} configPrefix="/api/cong-doan" loaiO="quy_doi"
                    nhanO="Công thức giờ chạy"
                    goY="Ra LƯỢNG theo đơn vị tốc độ của máy. Bỏ trống = hệ tự quy đổi. vd máy 5 màu chạy 2 lượt: sl_vao * so_mau / 5. ĐỪNG nhân so_luot_chay — hệ đã tự nhân."
                    value={r.cong_thuc_gio ?? ""}
                    onChange={(v) => patch(i, { cong_thuc_gio: v })} />
                  {coOGia && <FormulaField
                    id={`ct-gia-${r.may_id}`} configPrefix="/api/cong-doan" loaiO="cong_doan"
                    nhanO="Công thức giá"
                    goY="Ghi đè công thức giá của công đoạn khi phiếu tính giá chọn đúng máy này. Bỏ trống = dùng công thức chung."
                    value={r.cong_thuc_gia ?? ""}
                    onChange={(v) => patch(i, { cong_thuc_gia: v })} />}
                </div>
              </td></tr>}
            </Fragment>;
          })}
        </tbody>
      </table>
    </div>
    <div className="rc-dinh-muc-add">
      <select className="rc-dinh-muc-add__select" value=""
        onChange={(e) => {
          const id = Number(e.target.value);
          if (id) onChange([...chon, { may_id: id, cong_thuc_gio: null, cong_thuc_gia: null }]);
        }}>
        <option value="">＋ Chọn máy cho công đoạn</option>
        {duocChon.filter((o) => !daChon.has(Number(o.id))).map((o) => (
          <option key={o.id} value={o.id}>{String(o.ma)} · {String(o.ten)}</option>
        ))}
      </select>
    </div>
  </div>;
}
```

**Chữ ký `FormulaField` (đã tra, `fields/FormulaField.tsx:200-231`) — dùng đúng tên props này ở cả Task 9, 10, 11:** `value: string` · `onChange: (v: string) => void` · `configPrefix: string` (**bắt buộc**, dùng `"/api/cong-doan"` cho cả bốn ô mới vì chúng đều là bảng con của công đoạn) · `loaiO?: string` · `nhanO?: React.ReactNode` — **đây là NHÃN ô**, không phải `label` · `goY?: string` — **đây là câu gợi ý/placeholder**, không phải `hint` · `id?: string` (mặc định `"formula-textarea"`, phải đặt DUY NHẤT khi có nhiều ô trên một màn) · `an?: string[]` · `bienGoiY?: string[]` · `recordId` / `truocGiaTri` / `truocSuaLuc` cho lịch sử sửa. Component tự lấy từ điển chip qua `useBienCongThuc()` (cần `AuthContext`), nên không phải truyền `bienGoiY`. Nó render độc lập, không đòi khung `CatalogDrawer`.

- [ ] **Step 5: Nối vào drawer + config**

Trong `frontend/src/pages/danh-muc/fields/index.ts`, thêm `export { MayCuaCongDoanField } from "./MayCuaCongDoan";`.

Trong `frontend/src/pages/danh-muc/CatalogDrawer.tsx`, tìm nhánh render `type === "dau-viec-dinh-muc"` và thêm nhánh song song:

```tsx
  if (f.type === "may-cua-cong-doan") {
    return <MayCuaCongDoanField
      value={(form.may_lam_duoc as MayCongDoanRow[]) ?? []}
      options={refData[f.refPrefix ?? ""] ?? []}
      nhomChoPhep={(form.nhom_may_cho_phep as string[]) ?? []}
      nhomCongDoan={String(form.nhom ?? "")}
      onChange={(v) => setForm((prev) => ({ ...prev, may_lam_duoc: v }))} />;
  }
```

Trong `frontend/src/pages/rebuildCatalogConfigs.tsx`, thêm ngay SAU field `nhom_may_cho_phep`:

```tsx
    // Máy CỤ THỂ + công thức của riêng từng cặp (06/09/2026). Hàng tick ngay trên chỉ còn là bộ
    // lọc cho bảng này; luật chặn gán máy ở bước đọc DANH SÁCH này khi công đoạn có khai.
    { key: "may_lam_duoc", label: "Máy chạy được công đoạn này", type: "may-cua-cong-doan",
      refPrefix: "/api/may-thiet-bi", refParams: { active: true, size: 500 },
      group: "Lệnh sản xuất" },
```

Kiểm đường API máy đúng chưa bằng `grep -n "may-thiet-bi" frontend/src/pages/rebuildCatalogConfigs.tsx`.

- [ ] **Step 6: Chạy test**

Từ `frontend/`:

```bash
npx vitest run src/pages/danh-muc/fields/MayCuaCongDoan.test.tsx src/pages/rebuildCatalogConfigs.test.tsx && npx tsc --noEmit
```

- [ ] **Step 7: Nghiệm thu bằng chuột thật trên dev-browser**

Restart uvicorn, mở FE, đăng nhập, vào **Cấu hình danh mục → Công đoạn → sửa một công đoạn nhóm In**. Bằng chuột/bàn phím thật:
1. Tick nhóm "Máy in" ở hàng "Máy làm được công đoạn này".
2. Bấm dropdown "＋ Chọn máy cho công đoạn", chọn một máy in.
3. Bấm vào dòng máy vừa thêm → thấy hai ô công thức.
4. Gõ `sl_vao * so_mau / 5` vào ô giờ chạy và `to_dau_vao * 180` vào ô giá.
5. Bấm "Lưu thay đổi", đóng drawer, mở lại → hai công thức còn nguyên.
6. Mở một công đoạn nhóm `finishing` (vd Bế), lặp bước 1–3 → chỉ có MỘT ô công thức, không có ô giá.

Ghi lại đã bấm gì / gõ gì / thấy gì ở từng bước khi báo cáo.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/danh-muc frontend/src/pages/rebuildCatalogConfigs.tsx frontend/src/api/client.ts
git commit -m "Drawer Cong doan: bang may chay duoc cong doan, bam tung may de khai cong thuc gio va gia"
```

---

## Task 10: Cột "Công thức tính tiền công" ở bảng đầu việc

**Files:**
- Modify: `frontend/src/pages/danh-muc/fields/DinhMucDauViec.tsx`
- Modify: `frontend/src/pages/danh-muc/types.ts`
- Test: `frontend/src/pages/danh-muc/fields/DinhMucDauViec.test.tsx` (tạo mới nếu chưa có)

**Interfaces:**
- Consumes: `cong_thuc_khoan` trên `DinhMucRow` (Task 2).

- [ ] **Step 1: Thêm khoá vào kiểu TS**

Trong `frontend/src/pages/danh-muc/types.ts`, thêm vào `DinhMucRow`:

```ts
  /** Công thức tính TIỀN CÔNG của đầu việc này trong CÔNG ĐOẠN này (06/09/2026). Ra LƯỢNG theo
   *  đơn vị đơn giá khoán, server nhân đơn giá sau. Ghim vào bước lệnh lúc chọn đầu việc. */
  cong_thuc_khoan?: string | null;
```

- [ ] **Step 2: Viết test đỏ**

Tạo `frontend/src/pages/danh-muc/fields/DinhMucDauViec.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DinhMucDauViecField } from "./DinhMucDauViec";
import { AuthContext, type AuthState } from "../../../auth/AuthContext";

// Component tự nạp danh mục vật tư khi mount — chặn lại để test không đụng mạng.
vi.mock("../../../api/rebuildCatalog", () => ({
  crud: () => ({ list: async () => ({ items: [] }) }),
}));

// `token: null` ⇒ `useBienCongThuc` trong `FormulaField` không gọi API.
const AUTH: AuthState = {
  status: "anonymous", user: null, token: null,
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const OPT = [{ id: 1, ma: "KH-0002", ten: "In offset", department_id: 5, don_vi_ten: "tờ" }];
const ROW = [{ piece_rate_id: 1, nang_suat_nguoi_gio: 6000, so_nguoi_tieu_chuan: 2, vat_tus: [] }];

function bay(value = ROW) {
  return render(
    <AuthContext.Provider value={AUTH}>
      <DinhMucDauViecField value={value} options={OPT} departmentId={5} donViVao="to"
        onChange={() => {}} />
    </AuthContext.Provider>,
  );
}

describe("DinhMucDauViecField — công thức tiền công", () => {
  it("bấm tên đầu việc thì bung ô công thức tính tiền công", async () => {
    const user = userEvent.setup();
    bay();
    await user.click(screen.getByRole("button", { name: /In offset/ }));
    // `nhanO` render ra `<span>`, không phải `<label for>` ⇒ `getByText`.
    expect(screen.getByText("Công thức tính tiền công")).toBeInTheDocument();
  });
});
```

⚠️ Đọc `DinhMucDauViecField` xem chữ ký props thật (`value` / `options` / `departmentId` / `donViVao` / `onChange`) trước khi dán — chỉnh lời gọi cho khớp.

- [ ] **Step 3: Chạy test để chắc nó đỏ**

```bash
npx vitest run src/pages/danh-muc/fields/DinhMucDauViec.test.tsx
```

Kỳ vọng: FAIL — tên đầu việc hiện đang là text tĩnh, không phải nút.

- [ ] **Step 4: Sửa component**

Trong `DinhMucDauViec.tsx`:

Đổi ô tên đầu việc thành nút bung panel:

```tsx
            <td className="rc-col--left rc-dinh-muc-name">
              {/* Bấm tên để bung panel công thức tính tiền công — cùng lối bấm-dòng-mở-panel với
                  bảng máy và bảng vật tư, để ba chỗ khai công thức trong drawer này thao tác giống
                  nhau (06/09/2026). */}
              <button type="button" className="rc-dm-vt__pill"
                onClick={() => setMoCongThuc(moCt === r.piece_rate_id ? null : r.piece_rate_id)}>
                {opt ? `${opt.ma} · ${opt.ten}` : `#${r.piece_rate_id}`}
              </button>
            </td>
```

Thêm state `const [moCt, setMoCongThuc] = useState<number | null>(null);` cạnh `moVatTu`.

Thêm hàng phụ ngay sau hàng chính (trước hàng phụ vật tư):

```tsx
          {moCt === r.piece_rate_id && <tr className="rc-dm-vt__row"><td colSpan={9}>
            <div className="rc-dm-vt">
              <FormulaField
                id={`ct-khoan-${r.piece_rate_id}`} configPrefix="/api/cong-doan" loaiO="quy_doi"
                nhanO="Công thức tính tiền công"
                goY="Ra LƯỢNG theo đơn vị đơn giá khoán, hệ nhân đơn giá sau. Bỏ trống = hệ tự quy đổi. vd in trở 2 lượt: sl_vao * so_luot_chay. Lệnh ĐÃ phát giữ cách đo cũ."
                value={r.cong_thuc_khoan ?? ""}
                onChange={(v) => patch(i, { cong_thuc_khoan: v })} />
            </div>
          </td></tr>}
```

Thêm cột hiển thị công thức vào `<thead>` (giữa "Kíp chuẩn" và "Vật tư") và ô tương ứng trong hàng chính — nhớ tăng `colSpan` của các hàng phụ và của hàng "chưa chọn đầu việc" từ 8 lên 9.

- [ ] **Step 5: Chạy test**

```bash
npx vitest run src/pages/danh-muc/fields/DinhMucDauViec.test.tsx && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/danh-muc
git commit -m "Bang dau viec: them cot va panel khai cong thuc tinh tien cong"
```

---

## Task 11: Vật tư thành bảng, thêm cột "Công thức định mức"

**Files:**
- Modify: `frontend/src/pages/danh-muc/fields/DinhMucDauViec.tsx`
- Modify: `frontend/src/pages/danh-muc/types.ts`
- Test: `frontend/src/pages/danh-muc/fields/DinhMucDauViec.test.tsx`

**Interfaces:**
- Consumes: `vat_tus: [{vat_tu_id, cong_thuc_luong}]` (Task 2) thay `vat_tu_ids: number[]`.

- [ ] **Step 1: Đổi kiểu TS**

Trong `frontend/src/pages/danh-muc/types.ts`, **thay** khối `vat_tu_ids` trong `DinhMucRow`:

```ts
  /** VẬT TƯ đầu việc này tiêu thụ, mỗi dòng mang ĐỊNH MỨC của riêng nó (06/09/2026). Trước đây
   *  chỉ là danh sách id và công thức treo ở món hàng — nhưng mực ăn theo SỐ TỜ còn dung môi rửa
   *  máy ăn theo SỐ MÀU, cùng ĐVT kg mà hai cách hoàn toàn khác. */
  vat_tus?: { vat_tu_id: number; cong_thuc_luong?: string | null }[];
```

- [ ] **Step 2: Viết test đỏ**

Thêm vào `DinhMucDauViec.test.tsx`:

```tsx
  it("khối vật tư là BẢNG có cột công thức định mức, bấm dòng thì mở ô soạn", async () => {
    const user = userEvent.setup();
    const row = [{
      piece_rate_id: 1, nang_suat_nguoi_gio: 6000, so_nguoi_tieu_chuan: 2,
      vat_tus: [{ vat_tu_id: 11, cong_thuc_luong: "sl_vao / 40000" }],
    }];
    render(<DinhMucDauViecField value={row} options={OPT} departmentId={5} donViVao="to"
      onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /1 vật tư/ }));
    expect(screen.getByText("Công thức định mức")).toBeInTheDocument();
    expect(screen.getByText("sl_vao / 40000")).toBeInTheDocument();
  });
```

- [ ] **Step 3: Chạy test để chắc nó đỏ**

```bash
npx vitest run src/pages/danh-muc/fields/DinhMucDauViec.test.tsx
```

- [ ] **Step 4: Đổi khối vật tư từ danh sách chip sang bảng**

Trong `DinhMucDauViec.tsx`, thay toàn bộ khối `{mo && <tr className="rc-dm-vt__row">...}` bằng:

```tsx
          {mo && <tr className="rc-dm-vt__row"><td colSpan={9}>
            <div className="rc-dm-vt">
              <table className="rc-dinh-muc-table">
                <thead><tr>
                  <th className="rc-col--left">Mã</th>
                  <th className="rc-col--left">Tên vật tư</th>
                  <th className="rc-col--unit">ĐVT</th>
                  <th className="rc-col--left">Công thức định mức</th>
                  <th className="rc-col--center" style={{ width: 36 }} />
                </tr></thead>
                <tbody>
                  {vts.length === 0 && <tr><td colSpan={5} className="rc-bands__empty">
                    Chưa gắn vật tư nào.
                  </td></tr>}
                  {vts.map((v, k) => { const vt = vatTuTheoId.get(v.vat_tu_id); return (
                    <Fragment key={v.vat_tu_id}>
                      <tr>
                        <td className="rc-col--left">
                          <button type="button" className="rc-dm-vt__pill"
                            onClick={() => setMoVtCt(moVtCt === v.vat_tu_id ? null : v.vat_tu_id)}>
                            {String(vt?.ma ?? `#${v.vat_tu_id}`)}
                          </button>
                        </td>
                        <td className="rc-col--left">{String(vt?.ten ?? "(đã gỡ khỏi danh mục)")}</td>
                        <td className="rc-col--unit">{String(vt?.don_vi_gia ?? "—")}</td>
                        <td className="rc-col--left rc-dinh-muc-unit">{v.cong_thuc_luong || "—"}</td>
                        <td className="rc-col--center">
                          <button type="button" className="rc-bands__del" title="Bỏ vật tư khỏi đầu việc"
                            onClick={() => patch(i, { vat_tus: vts.filter((_, m) => m !== k) })}>
                            <TrashIcon />
                          </button>
                        </td>
                      </tr>
                      {moVtCt === v.vat_tu_id && <tr><td colSpan={5}>
                        <FormulaField
                          id={`ct-vt-${r.piece_rate_id}-${v.vat_tu_id}`}
                          configPrefix="/api/cong-doan" loaiO="quy_doi"
                          nhanO="Công thức định mức"
                          goY="Ra LƯỢNG theo ĐVT của vật tư. vd mực ăn theo số tờ: sl_vao / 40000 · dung môi rửa máy ăn theo số màu: so_mau * 0.3. Bỏ trống = bước lệnh KHÔNG bung dòng này."
                          value={v.cong_thuc_luong ?? ""}
                          onChange={(nv) => patch(i, {
                            vat_tus: vts.map((x, m) => (m === k ? { ...x, cong_thuc_luong: nv } : x)),
                          })} />
                      </td></tr>}
                    </Fragment>
                  ); })}
                </tbody>
              </table>
              <select className="rc-dinh-muc-add__select" value=""
                onChange={(e) => { const id = Number(e.target.value); if (id)
                  patch(i, { vat_tus: [...vts, { vat_tu_id: id, cong_thuc_luong: null }] }); }}>
                <option value="">＋ chọn từ danh mục vật tư khác</option>
                {vatTu.filter((v) => !vts.some((x) => x.vat_tu_id === Number(v.id))).map((v) => (
                  <option key={v.id} value={v.id}>{String(v.ma)} · {String(v.ten)} ({String(v.don_vi_gia ?? "—")})</option>
                ))}
              </select>
              <p className="rc-dm-vt__note">
                Định mức khai <b>theo từng món</b>: mực ăn theo số tờ, dung môi rửa máy ăn theo số màu.
              </p>
            </div>
          </td></tr>}
```

Đổi dòng khai biến ở đầu vòng lặp: `const vts = r.vat_tus ?? [];` (thay `vtIds`), và mọi chỗ dùng `vtIds.length` → `vts.length`. Thêm state `const [moVtCt, setMoVtCt] = useState<number | null>(null);`.

Sửa dòng khởi tạo đầu việc mới ở dropdown cuối component: `vat_tu_ids: []` → `vat_tus: []`.

- [ ] **Step 5: Chạy test**

```bash
npx vitest run src/pages/danh-muc/fields/DinhMucDauViec.test.tsx && npx tsc --noEmit
```

- [ ] **Step 6: Nghiệm thu bằng chuột thật trên dev-browser**

Vào **Cấu hình danh mục → Công đoạn → sửa "In AB- Máy in-11 x 11-khổ nhỏ"**:
1. Bấm tên "KH-0002 · In offset" → gõ `sl_vao * so_luot_chay` vào ô công thức tính tiền công.
2. Bấm nút "5 vật tư" → thấy BẢNG 5 dòng có cột "Công thức định mức".
3. Bấm mã `VT-MUC-C` → gõ `sl_vao / 40000`; bấm `VT-DM-01` → gõ `so_mau * 0.3`.
4. Bấm "Lưu thay đổi", đóng, mở lại → cả ba công thức còn nguyên và cột hiện đúng chữ.
5. Sang **Kế hoạch SX**, mở một lệnh có bước dùng công đoạn đó, chọn đầu việc "In offset" → khối "Vật tư cần dùng" bung ra 0,125 kg mực và 1,2 kg dung môi cho lệnh 5.000 tờ 4 màu (điều chỉnh số theo lệnh thật đang có).

Ghi lại đã bấm gì / gõ gì / thấy gì ở từng bước.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/danh-muc
git commit -m "Khoi vat tu cua dau viec thanh bang, moi dong khai cong thuc dinh muc rieng"
```

---

## Task 12: Luật chặn gán máy đọc danh sách máy của công đoạn

**Files:**
- Modify: `backend/app/services/bai_ghep_service.py` (`_may_sai_loai` ~1789–1800)
- Modify: `backend/app/services/xep_lich_service.py` (`_top_may` ~1530–1560)
- Test: `backend/tests/test_cong_thuc_ve_cong_doan.py`

**Interfaces:**
- Consumes: `CongDoan.may_lam_duoc` từ Task 1.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_cong_thuc_ve_cong_doan.py`:

```python
def test_cong_doan_da_chon_may_thi_luat_chan_doc_danh_sach_may(db):
    """Khai danh sách máy CỤ THỂ thì nó thắng luật nhóm — hai luật song song là mời khai lệch."""
    from app.services.bai_ghep_service import BaiGhepService

    cd = CongDoan(ma="CD-R1", ten="In AB", nhom="print", nhom_may_cho_phep=["Máy in"])
    m_ok = MayThietBi(ma="MAY-R1", ten="Komori", loai_may="Máy in")
    m_cung_nhom = MayThietBi(ma="MAY-R2", ten="Heidelberg", loai_may="Máy in")
    db.add_all([cd, m_ok, m_cung_nhom])
    db.flush()
    cd.may_lam_duoc.append(CongDoanMay(may_id=m_ok.id, thu_tu=0))
    db.commit()

    # Máy CÙNG NHÓM nhưng KHÔNG nằm trong danh sách của công đoạn ⇒ vẫn bị chặn.
    assert BaiGhepService.may_ngoai_cong_doan(cd, m_cung_nhom) is True
    assert BaiGhepService.may_ngoai_cong_doan(cd, m_ok) is False


def test_cong_doan_chua_chon_may_thi_lui_ve_luat_nhom(db):
    from app.services.bai_ghep_service import BaiGhepService

    cd = CongDoan(ma="CD-R2", ten="Bế", nhom="finishing", nhom_may_cho_phep=["Bế"])
    m_be = MayThietBi(ma="MAY-R3", ten="Yawa", loai_may="Bế")
    m_in = MayThietBi(ma="MAY-R4", ten="Komori", loai_may="Máy in")
    db.add_all([cd, m_be, m_in])
    db.commit()

    assert BaiGhepService.may_ngoai_cong_doan(cd, m_be) is False
    assert BaiGhepService.may_ngoai_cong_doan(cd, m_in) is True
```

- [ ] **Step 2: Chạy test để chắc nó đỏ**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py -k may_ngoai -q
```

Kỳ vọng: FAIL — `may_ngoai_cong_doan` chưa tồn tại.

- [ ] **Step 3: Viết hàm dùng chung**

Trong `backend/app/services/bai_ghep_service.py`, thêm staticmethod vào `BaiGhepService`:

```python
    @staticmethod
    def may_ngoai_cong_doan(cd, may) -> bool:
        """Máy này có bị công đoạn từ chối không?

        HAI TẦNG, tầng dưới chỉ chạy khi tầng trên im (06/09/2026):
          ① Công đoạn đã CHỌN MÁY cụ thể ⇒ chỉ máy trong danh sách được nhận. Danh sách này là chỗ
             khai công thức giờ/giá theo máy, nên máy ngoài nó cũng không có công thức để chạy.
          ② Chưa chọn máy nào ⇒ lùi về luật NHÓM (`nhom_may_cho_phep`) như trước.
        Chưa khai cả hai ⇒ không ràng buộc gì, đúng lối "chưa khai = không chặn" của cả hệ.
        """
        if cd is None or may is None:
            return False
        ds = [r.may_id for r in (getattr(cd, "may_lam_duoc", None) or [])]
        if ds:
            return int(getattr(may, "id", 0) or 0) not in ds
        allowed = (getattr(cd, "nhom_may_cho_phep", None) or [])
        return bool(allowed) and (getattr(may, "loai_may", None) not in allowed)
```

Sửa `_may_sai_loai` (dòng ~1789) gọi vào hàm này thay vì tự so `nhom_may_cho_phep`; giữ nguyên câu cảnh báo trả ra, chỉ đổi nguồn phán quyết và bổ sung một câu khi bị chặn ở tầng ①: `"Máy … không nằm trong danh sách máy của công đoạn …"`.

- [ ] **Step 4: Sửa `xep_lich_service._top_may`**

Ở `backend/app/services/xep_lich_service.py` dòng ~1552, thay khối `allow = (getattr(cd, "nhom_may_cho_phep", None) or [])` bằng lời gọi `BaiGhepService.may_ngoai_cong_doan(cd, may)` để lọc, giữ nguyên phần sắp xếp theo giờ xong. Import ở đầu hàm (không đặt ở đầu file nếu file đang tránh import vòng — kiểm bằng `grep -n "bai_ghep_service" backend/app/services/xep_lich_service.py`).

- [ ] **Step 5: Chạy test**

```bash
python -m pytest tests/test_cong_thuc_ve_cong_doan.py tests/test_bai_ghep_service.py tests/test_xep_lich_service.py tests/test_xep_lich_dot2.py -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/bai_ghep_service.py backend/app/services/xep_lich_service.py backend/tests
git commit -m "Chan gan may doc danh sach may cua cong doan truoc, chua khai thi lui ve luat nhom"
```

---

## Task 13: Gỡ ba ô công thức cũ

**Files:**
- Modify: `backend/app/models/may_thiet_bi.py`, `piece_work.py`, `vat_lieu_kho.py`
- Modify: `backend/app/schemas/may_thiet_bi.py`, `cong_viec_khoan.py`, `vat_lieu_kho.py`
- Modify: `backend/app/repositories/may_thiet_bi_repo.py`, `cong_viec_khoan_repo.py`, `vat_lieu_kho_repo.py`
- Modify: `backend/app/routers/may_thiet_bi.py`, `cong_viec_khoan.py`, `vat_lieu_kho.py`
- Modify: `backend/app/services/catalog_excel_specs.py`, `nhat_ky_danh_muc.py`
- Modify: `backend/app/seed_rebuild.py`, `import_danh_muc_prod.py`
- Modify: `backend/app/db_migrations.py`
- Modify: `frontend/src/pages/rebuildCatalogConfigs.tsx`
- Modify: `docs/DB_SCHEMA.md`

**Interfaces:**
- Consumes: mọi consumer đã trỏ sang chỗ mới (Task 3, 4, 5).

- [ ] **Step 1: Kiểm không còn ai đọc**

```bash
grep -rn "cong_thuc_luong" backend/app/services backend/app/routers | grep -v giay_nguyen
```

Kỳ vọng: chỉ còn đường GIẤY (`ke_hoach_vat_tu_service.py` với guard `hang[0] == HANG_GIAY`, và `_CT_LUONG_GIAY_CAN` trong seed). Nếu còn chỗ khác thì quay lại Task 3–5 xử nốt **trước khi** gỡ cột.

- [ ] **Step 2: Gỡ ô khỏi UI**

Trong `frontend/src/pages/rebuildCatalogConfigs.tsx`, xoá ba field và thay bằng ghi chú (giữ khuôn "ô đã gỡ" mà file đang dùng ở nhiều chỗ):

- Dòng ~269 (CFG_MAY): xoá field `cong_thuc_luong`, thay bằng
  `// Ô "Cách đo lượng theo đơn vị tốc độ" ĐÃ GỠ (06/09/2026): cách đo nay khai theo CẶP (công đoạn × máy) ở drawer Công đoạn — cùng một máy chạy hai công đoạn thì đo khác nhau.`
- Dòng ~510 (CFG_CONG_VIEC_KHOAN): xoá field, thay bằng
  `// Ô "Cách đo lượng khoán" ĐÃ GỠ (06/09/2026): khai ở dòng đầu việc trong drawer Công đoạn.`
- Dòng ~658 (CFG_VAT_TU): xoá field, thay bằng
  `// Ô "Công thức tính lượng" ĐÃ GỠ (06/09/2026): định mức khai theo TỪNG DÒNG vật tư trong đầu việc của công đoạn. Ô của GIẤY (CFG_GIAY) GIỮ NGUYÊN — câu hỏi khác.`

Sửa `frontend/src/pages/rebuildCatalogConfigs.test.tsx` dòng 133/146/148/170 cho khớp: dòng 148 (`CFG_GIAY`) giữ nguyên, ba dòng còn lại đổi thành assert ô KHÔNG còn.

- [ ] **Step 3: Gỡ khỏi backend**

- `models/may_thiet_bi.py`: xoá `cong_thuc_luong`, để lại ghi chú mốc như khuôn đã dùng cho `so_nhan_cong`.
- `models/piece_work.py`: xoá `cong_thuc_luong` của `PieceRate`, để lại ghi chú.
- `models/vat_lieu_kho.py`: xoá `cong_thuc_luong` của `VatTuInAn` (dòng ~162). **GIỮ** của `GiayNguyen` (dòng ~91).
- Ba file `schemas/`: xoá `cong_thuc_luong` cùng hai khoá `cong_thuc_luong_truoc` / `cong_thuc_luong_sua_luc` — nhưng CHỈ ở schema Vật tư khác, không đụng schema Giấy trong cùng file `vat_lieu_kho.py`.
- Ba file `repositories/`: bỏ `"cong_thuc_luong"` khỏi tuple cột (giữ ở tuple của Giấy).
- Ba file `routers/`: bỏ tham số `cong_thuc_truong="cong_thuc_luong"` — router Giấy (`vat_lieu_kho.py:135`) GIỮ.
- `services/catalog_excel_specs.py`: xoá `Cot("Công thức lượng", "cong_thuc_luong", ...)` ở spec Máy, Công việc khoán, Vật tư khác; giữ ở spec Giấy. Xác định spec nào là spec nào bằng cách đọc quanh từng dòng (268 · 405 · 424 · 733).
- `services/nhat_ky_danh_muc.py`: giữ nguyên `CONG_THUC_TRUONG` và nhãn — Giấy còn dùng. Thêm nhãn cho ba trường mới:

```python
    "cong_thuc_gio": "Công thức giờ chạy",
    "cong_thuc_khoan": "Công thức tính tiền công",
    "may_lam_duoc": "Máy chạy được công đoạn này",
```

- `seed_rebuild.py`: dòng 296–308 là GIẤY — giữ. `import_danh_muc_prod.py`: bỏ `cong_thuc_luong=ct_luong` ở khối máy (dòng ~230) và `cong_thuc_luong=ct` ở khối đầu việc khoán (dòng ~439); giữ khối giấy (dòng ~131). Xoá luôn biến `ct_luong` / `ct` nếu không còn ai dùng, và cập nhật docstring đầu file (dòng 19–20).

- [ ] **Step 4: Migration 0273**

```python
def _migrate_go_ba_o_cong_thuc_luong(db) -> None:
    """Gỡ ba ô "cách đo lượng" khỏi Máy · Công việc khoán · Vật tư khác (06/09/2026).

    Nghiệp vụ: cách đo giờ nay khai theo CẶP (công đoạn × máy), cách đo tiền công theo dòng đầu
    việc của công đoạn, định mức vật tư theo dòng vật tư của đầu việc — cả ba đã được `0272`
    chép sang. Giữ ba ô cũ song song là để hai nguồn cho một câu hỏi, sớm muộn khai lệch.

    GIẤY (`giay_nguyen.cong_thuc_luong`) GIỮ NGUYÊN: nó trả lời "một lệnh cần bao nhiêu kg giấy",
    câu hỏi của MẶT HÀNG chứ không của bước, và không có công đoạn nào để neo vào.

    Chỉ DROP khi cột còn: DB fresh (create_all theo model đã bỏ cột) rơi vào nhánh bỏ qua.
    """
    insp = inspect(db.get_bind())
    bang_co = set(insp.get_table_names())
    for bang in ("may_thiet_bi", "piece_rates", "vat_tu_in_an"):
        if bang not in bang_co:
            continue
        if "cong_thuc_luong" in _existing_columns(insp, bang):
            db.execute(text(f"ALTER TABLE {bang} DROP COLUMN cong_thuc_luong"))
    db.commit()


MIGRATIONS.append(("0273_go_ba_o_cong_thuc_luong", _migrate_go_ba_o_cong_thuc_luong))
```

- [ ] **Step 5: Cập nhật `docs/DB_SCHEMA.md`**

Xoá dòng `cong_thuc_luong` khỏi ba bảng `may_thiet_bi`, `piece_rates`, `vat_tu_in_an`. **Giữ** ở `giay_nguyen`.

- [ ] **Step 6: Dọn test cũ**

```bash
grep -rn "cong_thuc_luong" backend/tests
```

Sửa từng chỗ còn trỏ vào ba bảng đã gỡ. Riêng `backend/tests/test_cong_viec_khoan_migration.py` kiểm migration `_migrate_cong_thuc_luong_may_va_khoan` — migration cũ đó vẫn phải chạy được trên DB đời cũ (nó thêm cột, rồi `0273` xoá đi; kết quả bằng DB fresh). Giữ test, thêm một dòng comment nói rõ chuỗi thêm-rồi-xoá này là cố ý. `test_import_danh_muc_prod.py` dòng 45–48: bỏ `MayThietBi` và `PieceRate` khỏi danh sách, đổi `VatTuInAn` còn `["cong_thuc_gia"]`, giữ `GiayNguyen`.

- [ ] **Step 7: Chạy test**

Từ `backend/`:

```bash
python -m pytest tests/ -q -x
```

Từ `frontend/`:

```bash
npx vitest run && npx tsc --noEmit
```

- [ ] **Step 8: Commit**

```bash
git add backend frontend docs
git commit -m "Go ba o cach do luong o May, Cong viec khoan, Vat tu khac - da chuyen ve man Cong doan"
```

---

## Task 14: Nghiệm thu trọn luồng bằng UI thật

**Files:** không sửa file nào — task này là cửa nghiệm thu.

- [x] **Step 1: Restart uvicorn và kiểm migration đã chạy**

Restart uvicorn (backend đổi nhiều route/schema/service, hot-reload ở máy này không đáng tin). Xem log khởi động có ba dòng `0271` · `0272` · `0273` chạy xong không lỗi.

- [x] **Step 2: Khai đủ bốn công thức bằng chuột thật**

Vào **Cấu hình danh mục → Công đoạn**, mở một công đoạn nhóm In:
1. Tick nhóm "Máy in" → chọn một máy in → bấm dòng máy → gõ công thức giờ chạy và công thức giá.
2. Bấm tên đầu việc → gõ công thức tính tiền công có dùng chip `so_luot_chay`.
3. Bấm nút vật tư → gõ công thức định mức cho hai món khác nhau (một theo `sl_vao`, một theo `so_mau`).
4. Lưu, đóng, mở lại → cả bốn công thức còn nguyên.

- [x] **Step 3: Kiểm ba con số ở Kế hoạch SX**

Mở một lệnh SX có bước dùng đúng công đoạn đó:
1. Gán đúng máy đã khai → tab "Tiến độ & Thời gian" hiện dòng "Nguồn tính" và số phút khớp công thức giờ chạy vừa gõ.
2. Đổi ô "Số lượt chạy qua máy" từ 1 sang 2. Ở **bước máy**: giờ chạy gấp đôi. Ở **bước tổ**: giờ GIỮ NGUYÊN (đúng như quyết định §5), chỉ tiền công gấp đôi vì công thức có chip `so_luot_chay` — kiểm cả hai, đừng chỉ kiểm bước máy rồi kết luận chung.
3. Khối "Vật tư cần dùng" bung ra hai dòng với hai con số tính theo hai công thức khác nhau.

- [x] **Step 4: Kiểm ghi đè giá ở Phiếu tính giá**

Mở một phiếu tính giá, ở thành phần có khối In:
1. Chọn máy chưa khai công thức giá → bấm Tính → dòng công đoạn In dùng công thức chung của công đoạn.
2. Đổi sang máy ĐÃ khai công thức giá → bấm Tính lại → dòng đó đổi số theo công thức của máy, và cột "Công thức thế số" hiện đúng công thức của máy.

- [x] **Step 5: Kiểm ô cũ đã biến mất**

Mở **Danh mục → Thiết bị & Máy móc** → sửa một máy: không còn tab/ô "Cách đo lượng theo đơn vị tốc độ".
Mở **Công việc khoán** → sửa một đầu việc: không còn ô "Cách đo lượng khoán".
Mở **Vật tư khác** → sửa một món: không còn ô "Công thức tính lượng".
Mở **Giấy** → sửa một loại giấy: ô "Công thức tính lượng" VẪN CÒN.

- [x] **Step 6: Báo cáo**

Liệt kê CỤ THỂ đã bấm gì / gõ gì / thấy gì ở từng bước trên. Nếu có đoạn nào buộc phải đi qua API thay vì UI thì nói rõ ngay trong báo cáo, không đợi hỏi.

---

## Rà lại plan

**Phủ thiết kế:** bốn ô mới (Task 1, 2 dựng chỗ khai · Task 3, 4, 5, 6 nối engine · Task 9, 10, 11 dựng UI), gỡ ba ô cũ (Task 13), số lượt ở mọi bước (Task 7), chip mới (Task 8), luật gán máy (Task 12), nghiệm thu (Task 14). Không có mục nào của thiết kế thiếu task.

**Tên gọi dùng xuyên suốt** — dùng đúng chính tả này ở mọi task:

| Thứ | Tên |
|---|---|
| Bảng nối | `cong_doan_may` · model `CongDoanMay` |
| Quan hệ trên `CongDoan` | `may_lam_duoc` |
| Cột công thức giờ | `cong_doan_may.cong_thuc_gio` |
| Cột công thức giá theo máy | `cong_doan_may.cong_thuc_gia` |
| Cột công thức tiền công | `cong_doan_dau_viec.cong_thuc_khoan` |
| Cột định mức vật tư | `cong_doan_dau_viec_vat_tu.cong_thuc_luong` |
| Khoá API vật tư của đầu việc | `vat_tus` (thay `vat_tu_ids`) |
| Helper tra công thức giờ | `LsxService._ct_gio_cua_may(cong_doan_id, may_id)` |
| Ảnh chụp khoán | `khoan_snapshot(rate, dm=None)` |
| Dict công đoạn cho engine giá | `_cong_doan_to_dict(cd, tram=None, *, ct_gia_may=None)` |
| Luật chặn máy | `BaiGhepService.may_ngoai_cong_doan(cd, may)` |
| Hằng mặc định tầng lệnh | `MAC_DINH_TANG_LENH` |
| Chip mới | `so_luot_chay`, chỉ thuộc `LOAI_QUY_DOI` |
| Field FE | `type: "may-cua-cong-doan"`, component `MayCuaCongDoanField` |
| Props ô công thức | `nhanO` = nhãn · `goY` = câu gợi ý · `configPrefix="/api/cong-doan"` · `id` duy nhất |

**Đã tra sẵn, executor KHÔNG phải đoán:** chữ ký `FormulaField` (`fields/FormulaField.tsx:200`, nhãn là `nhanO` chứ không phải `label`, render ra `<span>` nên test dùng `getByText`); hàm chứa dòng `so_luot_chay` là `thoi_luong_buoc` (`lsx_service.py:226`, module-level, test được bằng `SimpleNamespace`); `MayThietBi.active` có thật (`may_thiet_bi.py:141`); `db_migrations.py` KHÔNG có tiền lệ `UPDATE ... FROM` và có cả chục test gọi thẳng migration trên SQLite ⇒ backfill `0272` viết bằng truy vấn con tương quan.

**Hai chỗ vẫn phải đọc code trước khi gõ:** chữ ký props thật của `DinhMucDauViecField` (Task 10 Step 2) và tên khoá trả về của `thoi_luong_buoc` (Task 7 Step 1).

**Một hệ quả người dùng cần biết, đã ghi vào hint và vào bước nghiệm thu:** ở bước tổ, số lượt đổi TIỀN CÔNG chứ không đổi GIỜ — nhánh tổ của `thoi_luong_buoc` không nhân lượt và plan này cố ý giữ nguyên.
