# Đề nghị cấp vật tư theo công đoạn — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tổ trưởng đứng tại công đoạn của mình, thấy vật tư kế hoạch đã tính sẵn, sửa số cho khớp thực tế rồi gửi thẳng sang kho — không màn hình mới, không bước duyệt.

**Architecture:** Hai bảng SẢN XUẤT ghi bản đối chiếu đầy đủ (kể cả dòng xin 0); yêu cầu kho là ẢNH CHIẾU chỉ chứa dòng dương, nối 1–1 bằng `san_xuat_vat_tu_de_nghi.stock_request_id`. Khi chưa có phiếu nào, sửa = đồng bộ đè lên chính yêu cầu kho đó (giữ mã, giữ id); có phiếu rồi = khoá, muốn thêm thì tạo lần bổ sung. Kho điều chỉnh thực xuất ghi vào cột mới `sl_chot_thuc_xuat` chứ **không** hạ `sl_duyet`.

**Tech Stack:** FastAPI + SQLAlchemy 2 (Postgres dev/prod, SQLite in-memory cho test) · React 18 + TypeScript + Vite · pytest.

**Spec:** `docs/spec-de-nghi-cap-vat-tu-cong-doan.md`. Nền: `docs/spec-kho-de-nghi.md`, `docs/spec-thuc-hien-san-xuat.md`, `docs/spec-ke-hoach-vat-tu.md`.

> **THAY THẾ:** plan này thay hẳn Task 16–22 (Phần B) của
> `docs/superpowers/plans/2026-08-30-ke-hoach-vat-tu.md`. Phần đó nối kho ở MỨC DÒNG
> (`stock_request_lines.sx_cong_viec_id`) và hạ `sl_duyet` khi điều chỉnh — cả hai đều đã bị bác.
> **Đừng thi công Task 16–22.** Trước khi bắt đầu, mở file đó và ghi một dòng cảnh báo ngay dưới
> tiêu đề "PHẦN B" rằng phần này đã bị plan 31/08 thay thế.

## Global Constraints

- Ngôn ngữ code/comment/chuỗi UI: **tiếng Việt** (thuật ngữ kỹ thuật giữ tiếng Anh).
- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, không ALTER. Bảng mới thì `create_all` tự dựng, nhưng **cột mới trên bảng cũ bắt buộc viết migration** — nếu không DB dev/prod không nhận. Dev cũng là Postgres.
- Cột Boolean: `server_default` phải là `false()`/`true()` của SQLAlchemy, **không** phải `"0"`/`"1"`.
- `docs/DB_SCHEMA.md` có guard test: **mọi bảng/cột mới phải ghi vào đó cùng lúc**, không thì `init` FAIL.
- Migration **cấm ORM full-select** để backfill — dùng raw SQL đích danh cột.
- Phân tầng `routers → services → repositories → DB`. Luật nghiệp vụ nằm ở services; router chỉ điều phối; truy vấn DB chỉ trong repositories.
- **Quyền:** router gác `san_xuat:assign_work`; service đòi thêm **đang là tổ trưởng đúng tổ**; **KHÔNG** đòi `kho:request`.
- **Không bao giờ chặn bắt đầu / kết thúc công đoạn vì lý do vật tư.**
- BE **luôn quy đổi lại** số client gửi lên bằng engine đơn vị sẵn có. Không tin số client.
- `WorkItemChiTietOut` **CÓ** `response_model` (`backend/app/routers/san_xuat.py:365`) ⇒ Pydantic nuốt IM LẶNG mọi field chưa khai. Thêm field phải đi hết chuỗi: dict (`board.py`) → schema Out → type TS → chỗ dùng.
- Verify: `pytest` nhắm đúng file test đã đổi + `npx tsc --noEmit`. **Đừng chạy `./init.ps1`**; đừng chạy cả bộ test nếu chưa được yêu cầu.
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

| File | Trách nhiệm |
| --- | --- |
| `backend/app/models/san_xuat_vat_tu.py` | **Tạo.** `SanXuatVatTuDeNghi` + `SanXuatVatTuDeNghiDong`. |
| `backend/app/models/__init__.py` | **Sửa.** Export 2 model mới (để `create_all` thấy). |
| `backend/app/models/stock_request.py` | **Sửa.** `StockRequestLine.sl_chot_thuc_xuat`. |
| `backend/app/db_migrations.py` | **Sửa.** `0246_sx_vat_tu_de_nghi`. |
| `docs/DB_SCHEMA.md` | **Sửa.** 2 bảng mới + 1 cột mới. |
| `backend/app/services/ke_hoach_vat_tu_service.py` | **Sửa.** Phương thức công khai `nhu_cau_cua_cong_viec`. |
| `backend/app/repositories/san_xuat_vat_tu_repo.py` | **Tạo.** Truy vấn đề nghị + dòng + phiếu theo công việc. |
| `backend/app/services/san_xuat/vat_tu_de_nghi.py` | **Tạo.** Toàn bộ luật tạo/sửa/đối chiếu. |
| `backend/app/services/stock_request_service.py` | **Sửa.** `dong_bo_tu_san_xuat` (chỉ dùng cho SX), `_muc_tieu_hieu_luc`, `refresh_fulfillment`. |
| `backend/app/services/stock_voucher_service.py` | **Sửa.** `dieu_chinh_xuat` ghi `sl_chot_thuc_xuat`. |
| `backend/app/services/san_xuat/board.py` | **Sửa.** Khối `vat_tu_cap` + đổi nguồn phiếu. |
| `backend/app/repositories/san_xuat_san_luong_repo.py` | **Sửa.** `voucher_xuat_cua_cong_viec` thay `voucher_xuat_cua_lsx`. |
| `backend/app/schemas/san_xuat.py` | **Sửa.** `VatTuCapOut` + nhánh con; gắn vào `WorkItemChiTietOut`. |
| `backend/app/schemas/stock.py` | **Sửa.** `StockRequestLineOut` + `StockRequestOut` mở rộng. |
| `backend/app/routers/san_xuat.py` | **Sửa.** 2 route material-requests. |
| `frontend/src/api/client.ts` | **Sửa.** Types + 2 hàm gọi + 2 sự kiện SSE. |
| `frontend/src/pages/ThsxExecPanels.tsx` | **Sửa.** Khối Vật tư mới + form trong drawer. |
| `frontend/src/pages/KhoYeuCauPage.tsx` | **Sửa.** Cột tổ/công đoạn/giờ cần + "thực xuất N / yêu cầu M". |
| `frontend/src/components/AppShell.tsx` | **Sửa.** Nhận `san_xuat_vat_tu_de_nghi_changed`. |
| `backend/tests/test_sx_vat_tu_de_nghi.py` | **Tạo.** Luật tạo/sửa/khoá/lý do/quyền. |
| `backend/tests/test_kho_dieu_chinh_xuat.py` | **Tạo.** `sl_chot_thuc_xuat` + `sl_con_lai`. |

---

### Task 1: Hai bảng mới + cột `sl_chot_thuc_xuat`

**Files:**
- Create: `backend/app/models/san_xuat_vat_tu.py`
- Modify: `backend/app/models/__init__.py`, `backend/app/models/stock_request.py`, `backend/app/db_migrations.py`, `docs/DB_SCHEMA.md`
- Test: `backend/tests/test_sx_vat_tu_de_nghi.py`

**Interfaces:**
- Produces: `SanXuatVatTuDeNghi`, `SanXuatVatTuDeNghiDong`, hằng `DN_LAN_DAU = "lan_dau"`, `DN_BO_SUNG = "bo_sung"`; `StockRequestLine.sl_chot_thuc_xuat: float | None`; migration id `0246_sx_vat_tu_de_nghi`.

- [ ] **Step 1: Viết test thất bại trước**

Tạo `backend/tests/test_sx_vat_tu_de_nghi.py`:

```python
"""Đề nghị cấp vật tư theo công đoạn (docs/spec-de-nghi-cap-vat-tu-cong-doan.md).

Hai bảng SẢN XUẤT giữ bản đối chiếu ĐẦY ĐỦ (kể cả dòng xin 0); yêu cầu kho là ẢNH CHIẾU chỉ chứa
dòng dương. Test file này chốt: cấu trúc, luật lý do, luật khoá, luật quyền, và luật "sửa hết về 0".
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.san_xuat_vat_tu import (
    DN_BO_SUNG, DN_LAN_DAU, SanXuatVatTuDeNghi, SanXuatVatTuDeNghiDong,
)

_T0 = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


def test_mot_cong_viec_khong_co_hai_lan_cung_so(db):
    for _ in range(2):
        db.add(SanXuatVatTuDeNghi(cong_viec_id=1, lan_so=1, loai=DN_LAN_DAU, can_luc=_T0))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_mot_de_nghi_khong_co_hai_dong_cung_mat_hang(db):
    dn = SanXuatVatTuDeNghi(cong_viec_id=2, lan_so=1, loai=DN_LAN_DAU, can_luc=_T0)
    db.add(dn)
    db.flush()
    for _ in range(2):
        db.add(SanXuatVatTuDeNghiDong(
            de_nghi_id=dn.id, hang_loai="giay", hang_id=9, dvt="tờ", dvt_goc="kg",
            sl_ke_hoach=100, sl_ke_hoach_goc=12, sl_yeu_cau=100, sl_yeu_cau_goc=12,
        ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_mot_yeu_cau_kho_chi_thuoc_mot_de_nghi(db):
    for lan in (1, 2):
        db.add(SanXuatVatTuDeNghi(cong_viec_id=3, lan_so=lan, loai=DN_LAN_DAU,
                                  can_luc=_T0, stock_request_id=555))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_dong_yeu_cau_kho_mac_dinh_chua_chot_thuc_xuat(db):
    """`sl_chot_thuc_xuat` NULL = kho CHƯA điều chỉnh. KHÁC hẳn 0 (đã chốt là không xuất gì)."""
    from app.models.stock_request import StockRequestLine

    ln = StockRequestLine(request_id=1, hang_loai="giay", hang_id=1, dvt="kg", sl_de_nghi=100)
    assert ln.sl_chot_thuc_xuat is None


def test_migration_0246_co_trong_danh_sach():
    from app.db_migrations import MIGRATIONS
    assert any(ma == "0246_sx_vat_tu_de_nghi" for ma, _fn in MIGRATIONS)
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py -q
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'app.models.san_xuat_vat_tu'`.

- [ ] **Step 3: Viết model**

Tạo `backend/app/models/san_xuat_vat_tu.py`:

```python
"""Đề nghị cấp vật tư của TỔ tại một công đoạn (docs/spec-de-nghi-cap-vat-tu-cong-doan.md §2).

Vì sao là bảng RIÊNG chứ không nhét vào `stock_requests`: hai bảng này giữ BẢN ĐỐI CHIẾU của sản
xuất — kế hoạch bao nhiêu, tổ xin bao nhiêu, lệch vì lý do gì — kể cả những dòng tổ xin 0. Yêu cầu
kho chỉ là ẢNH CHIẾU của phần DƯƠNG: kho không cần biết "kế hoạch có mà tổ không lấy", và cũng
không được phép thấy lý do lệch (spec §7). Nhét chung một bảng là bắt kho gánh ngữ nghĩa của sản
xuất, rồi mọi màn kho phải học cách bỏ qua dòng 0.

Bảng MỚI → `create_all` tự dựng; migration `0246` chỉ cần cho cột thêm vào bảng CŨ.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# Lần đầu = ảnh của kế hoạch. Bổ sung = phát sinh sau khi kho đã lập phiếu cho lần trước.
DN_LAN_DAU = "lan_dau"
DN_BO_SUNG = "bo_sung"
DE_NGHI_LOAI = (DN_LAN_DAU, DN_BO_SUNG)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatVatTuDeNghi(Base):
    """Một LẦN tổ đề nghị cấp vật tư cho một công đoạn."""

    __tablename__ = "san_xuat_vat_tu_de_nghi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_viec_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    lan_so: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    loai: Mapped[str] = mapped_column(String(12), nullable=False, default=DN_LAN_DAU)
    # GIỜ cần thật. `stock_requests.ngay_can` chỉ có DATE, mà ca chiều cần hàng lúc 13h30 khác hẳn
    # ca sáng cần lúc 6h — kho soạn theo giờ chứ không theo ngày.
    can_luc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Yêu cầu kho ảnh chiếu. NULL khi MỌI dòng bằng 0 — tổ xác nhận không cần cấp gì, không có
    # việc gì cho kho làm, nên không đẻ chứng từ rỗng.
    stock_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    dongs: Mapped[list["SanXuatVatTuDeNghiDong"]] = relationship(
        "SanXuatVatTuDeNghiDong", back_populates="de_nghi",
        cascade="all, delete-orphan", order_by="SanXuatVatTuDeNghiDong.id",
    )

    __table_args__ = (
        UniqueConstraint("cong_viec_id", "lan_so", name="uq_sx_vt_de_nghi_cv_lan"),
        # Một yêu cầu kho chỉ thuộc đúng một lần đề nghị — nếu không thì "sửa lần 2" có thể
        # ghi đè yêu cầu của lần 1 mà không ai phát hiện.
        UniqueConstraint("stock_request_id", name="uq_sx_vt_de_nghi_stock_request"),
    )


class SanXuatVatTuDeNghiDong(Base):
    """Một mặt hàng trong một lần đề nghị.

    Lần ĐẦU lưu MỌI vật tư kế hoạch, kể cả dòng tổ xin 0 — để về sau đọc được "kế hoạch có, tổ
    không lấy", câu đó không suy ngược được từ yêu cầu kho (yêu cầu kho chỉ chứa dòng dương).
    Vật tư ngoài kế hoạch: `sl_ke_hoach = 0`.

    Bốn con số vì phải so được HAI thang: `sl_*` theo đơn vị người ta nhìn (tờ, ram, thùng) để bản
    in đúng chữ, `sl_*_goc` theo đơn vị gốc để MÁY so lệch. So bằng đơn vị người khai là so 100 tờ
    với 12 kg.
    """

    __tablename__ = "san_xuat_vat_tu_de_nghi_dong"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    de_nghi_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("san_xuat_vat_tu_de_nghi.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    hang_loai: Mapped[str] = mapped_column(String(8), nullable=False)
    hang_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dvt: Mapped[str] = mapped_column(String(24), nullable=False)
    dvt_goc: Mapped[str] = mapped_column(String(24), nullable=False)
    sl_ke_hoach: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    sl_ke_hoach_goc: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    sl_yeu_cau: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    sl_yeu_cau_goc: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    ly_do_chenh_lech: Mapped[str | None] = mapped_column(String(500), nullable=True)

    de_nghi: Mapped[SanXuatVatTuDeNghi] = relationship(
        "SanXuatVatTuDeNghi", back_populates="dongs"
    )

    __table_args__ = (
        UniqueConstraint("de_nghi_id", "hang_loai", "hang_id", name="uq_sx_vt_dn_dong_hang"),
    )
```

- [ ] **Step 4: Export model + thêm cột kho**

Trong `backend/app/models/__init__.py`, thêm import 2 model mới đúng khuôn các model khác đang có
(`create_all` chỉ dựng bảng của model đã được import).

Trong `backend/app/models/stock_request.py`, thêm vào `StockRequestLine` ngay sau `sl_da_ung`:

```python
    # KHO CHỐT THỰC XUẤT (spec-de-nghi-cap-vat-tu-cong-doan §2.3): sau khi điều chỉnh phiếu xuất,
    # đây là con số CUỐI CÙNG kho công nhận đã cấp cho dòng này. NULL = chưa điều chỉnh lần nào.
    #
    # Vì sao KHÔNG hạ `sl_duyet` cho gọn: `sl_duyet` là "đã đồng ý cấp bao nhiêu" — hạ nó đi thì
    # xin-100-xuất-70 và xin-70-xuất-70 trở nên không phân biệt được, mà đúng khoảng lệch đó là
    # thứ tổ trưởng cần nhìn lại. Mục tiêu hiệu lực = cột này nếu có, không thì `sl_duyet`.
    sl_chot_thuc_xuat: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
```

Cập nhật docstring của lớp: câu *"còn lại = `sl_duyet - sl_da_ung`"* đổi thành
*"còn lại = `coalesce(sl_chot_thuc_xuat, sl_duyet) - sl_da_ung`, kẹp về ≥ 0"*.

- [ ] **Step 5: Migration 0246**

Cuối `backend/app/db_migrations.py`:

```python
def _migrate_sx_vat_tu_de_nghi(db: Session) -> None:
    """`stock_request_lines.sl_chot_thuc_xuat` — số kho CHỐT đã thực xuất cho một dòng yêu cầu.

    Hai bảng `san_xuat_vat_tu_de_nghi*` là bảng MỚI nên `create_all` tự dựng; migration này chỉ lo
    cột thêm vào bảng CŨ (spec-de-nghi-cap-vat-tu-cong-doan §2.3).

    Hàng CŨ giữ NULL = "chưa điều chỉnh lần nào" ⇒ mục tiêu hiệu lực của chúng vẫn là `sl_duyet`,
    tức mọi yêu cầu đang chạy KHÔNG đổi trạng thái một li nào sau migration. Đừng backfill về
    `sl_da_ung`: làm thế là tuyên bố mọi yêu cầu cấp dở dang đều "đã chốt xong", xoá sạch phần
    còn thiếu của chúng.
    """
    insp = inspect(db.get_bind())
    if "stock_request_lines" not in set(insp.get_table_names()):
        return
    if "sl_chot_thuc_xuat" in _existing_columns(insp, "stock_request_lines"):
        return
    db.execute(text(
        "ALTER TABLE stock_request_lines ADD COLUMN sl_chot_thuc_xuat NUMERIC(14,2)"
    ))
    db.commit()


MIGRATIONS.append(("0246_sx_vat_tu_de_nghi", _migrate_sx_vat_tu_de_nghi))
```

- [ ] **Step 6: Ghi `docs/DB_SCHEMA.md`**

Thêm 2 mục bảng mới (theo đúng khuôn các mục khác: `### \`ten_bang\``, **Purpose**, bảng cột) và
một dòng vào bảng `stock_request_lines`:

```markdown
| `sl_chot_thuc_xuat` | `Numeric(14,2)` → `NUMERIC` | — | yes | — | Số kho CHỐT đã thực xuất cho dòng này sau khi điều chỉnh phiếu xuất. NULL = chưa điều chỉnh. Mục tiêu hiệu lực của dòng = `coalesce(sl_chot_thuc_xuat, sl_duyet)`; `còn lại = max(mục tiêu − sl_da_ung, 0)`. Thêm qua migration `0246`. |
```

- [ ] **Step 7: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py -q
```

Kỳ vọng: 5 passed. Nếu guard DB_SCHEMA đỏ, thông báo nêu đích danh bảng/cột thiếu.

- [ ] **Step 8: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/models/san_xuat_vat_tu.py backend/app/models/__init__.py backend/app/models/stock_request.py backend/app/db_migrations.py docs/DB_SCHEMA.md backend/tests/test_sx_vat_tu_de_nghi.py
git commit -m "Vật tư công đoạn: 2 bảng đề nghị + cột sl_chot_thuc_xuat (mg 0246)"
```

---

### Task 2: `nhu_cau_cua_cong_viec` — nguồn kế hoạch của một công đoạn

**Files:**
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py`
- Test: `backend/tests/test_sx_vat_tu_de_nghi.py` (thêm)

**Interfaces:**
- Consumes: `_lenh_trong_pham_vi`, `_bai_trong_pham_vi`, `_gom_nhu_cau`, `_nap_mat_hang`, `_quy_doi_dong`, `_ve_goc` (đều đã có trong `KeHoachVatTuService`); `SanXuatCongViec.lsx_id`, `.bai_ghep_id`, `.lsx_cong_doan_id`, `.bai_ghep_cong_doan_id`.
- Produces:
  ```python
  def nhu_cau_cua_cong_viec(self, cv) -> list[dict]
  # [{"hang_loai": str, "hang_id": int, "ten": str,
  #   "dvt": str, "sl": float,            # đơn vị KẾ HOẠCH quen thuộc
  #   "dvt_goc": str, "sl_goc": float}]   # đơn vị GỐC để máy so lệch
  ```

- [ ] **Step 1: Viết test thất bại trước**

```python
def test_nhu_cau_cua_cong_viec_tra_ca_hai_thang_don_vi(db, orders, lsx_svc, admin, customer):
    """Bước IN của một lệnh phải ra dòng GIẤY, kèm cả đơn vị kế hoạch lẫn đơn vị gốc.

    KHÔNG lấy từ `SanXuatCongViec.vat_tu_json`: snapshot đó chỉ có vật tư khai TAY ở bước, không
    có giấy — mà giấy mới là thứ tổ in cần xin.
    """
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT1")
    kh = _kh_service(db)          # helper của file này, dựng đúng chuỗi như routers/ke_hoach_vat_tu.py
    ra = kh.nhu_cau_cua_cong_viec(cv)

    assert ra, "bước phải có ít nhất một dòng nhu cầu"
    d = ra[0]
    assert set(d) >= {"hang_loai", "hang_id", "ten", "dvt", "sl", "dvt_goc", "sl_goc"}
    assert d["sl"] > 0 and d["sl_goc"] > 0


def test_nhu_cau_gop_trung_theo_mat_hang(db, orders, lsx_svc, admin, customer):
    """Hai dòng cùng mặt hàng (vd khai tay trùng loại giấy) phải gộp thành MỘT sau khi về đơn vị
    gốc — không thì tổ nhìn thấy hai dòng y hệt và không biết sửa dòng nào."""
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT2")
    ra = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    khoa = [(d["hang_loai"], d["hang_id"]) for d in ra]
    assert len(khoa) == len(set(khoa))
```

> Helper `_kh_service(db)` dựng `KeHoachVatTuService` đúng bộ repo như
> `backend/app/routers/ke_hoach_vat_tu.py::get_service()` — copy từ đó, **đừng** tự ghép bộ repo
> khác (ghép thiếu một repo là engine im lặng trả rỗng).

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py -q -k nhu_cau
```

Kỳ vọng: FAIL — `AttributeError: 'KeHoachVatTuService' object has no attribute 'nhu_cau_cua_cong_viec'`.

- [ ] **Step 3: Cài đặt**

Trong `backend/app/services/ke_hoach_vat_tu_service.py`, thêm phương thức CÔNG KHAI (đặt cạnh
`vat_tu_hieu_luc`, dòng 745 — nó là hàng xóm đúng nghĩa nhất):

```python
    def nhu_cau_cua_cong_viec(self, cv) -> list[dict]:
        """Vật tư KẾ HOẠCH của MỘT công việc sản xuất (spec-de-nghi-cap-vat-tu-cong-doan §3).

        Đi qua đúng `_gom_nhu_cau` mà bảng cân đối đang dùng, rồi LỌC về đúng bước — không viết
        lại MRP. Hai nguồn tính nhu cầu thì sớm muộn lệch, và lệch ở đây là tổ xin sai số.

        KHÔNG đọc `cv.vat_tu_json`: snapshot ấy chỉ có vật tư khai TAY ở bước, không có giấy.

        Giấy neo ở bước ĐẦU TIÊN thật sự tiêu thụ giấy (`_buoc_dau_dong_giay`), nên chỉ công việc
        của bước đó mới thấy dòng giấy — đúng nghiệp vụ: tổ cán màng không đi xin giấy in.
        """
        lsx_id = cv.lsx_id
        bai_id = cv.bai_ghep_id
        if not lsx_id and not bai_id:
            return []
        lenh = self._lenh_trong_pham_vi({lsx_id} if lsx_id else None)
        lenh_map = {l.id: l for l in lenh}
        bais = self._bai_trong_pham_vi(set(lenh_map))
        if bai_id and not any(b.id == bai_id for b in bais):
            bais = self._bai_trong_pham_vi({lsx_id} if lsx_id else set()) or bais
        thanh_vien = {tv.lsx_id for b in bais for tv in b.thanh_viens}
        tho, _bo_qua = self._gom_nhu_cau(lenh, lenh_map, bais, thanh_vien)

        # Neo về ĐÚNG bước: dòng lệnh so `buoc_id` với `lsx_cong_doan_id`, dòng bài so với
        # `bai_ghep_cong_doan_id` (hai không gian id khác nhau — cặp `(lsx_id, bai_ghep_id)` trên
        # dòng đã phân biệt sẵn, xem chú thích `_dong_bai`).
        neo_lsx = cv.lsx_cong_doan_id
        neo_bg = cv.bai_ghep_cong_doan_id
        cua_buoc = [
            d for d in tho
            if (d["bai_ghep_id"] and neo_bg and d["buoc_id"] == neo_bg)
            or (d["lsx_id"] and neo_lsx and d["lsx_id"] == lsx_id and d["buoc_id"] == neo_lsx)
        ]
        if not cua_buoc:
            return []

        self._nap_mat_hang(cua_buoc)
        self._quy_doi_dong(cua_buoc)

        # Gộp trùng SAU khi đã về đơn vị gốc — gộp trước là cộng 100 tờ với 12 kg.
        gom: dict[tuple, dict] = {}
        for d in cua_buoc:
            loai, hid = d["hang"]
            k = (loai, int(hid))
            cu = gom.get(k)
            if cu is None:
                gom[k] = {
                    "hang_loai": loai, "hang_id": int(hid),
                    "ten": d.get("ten_hang") or d.get("ten") or f"#{hid}",
                    "dvt": d["dvt"], "sl": float(d["sl"] or 0),
                    "dvt_goc": d.get("dvt_goc") or d["dvt"],
                    "sl_goc": float(d.get("sl_goc") or d["sl"] or 0),
                }
            else:
                cu["sl_goc"] += float(d.get("sl_goc") or 0)
                # Đơn vị hiển thị chỉ cộng được khi TRÙNG; khác đơn vị thì bày theo đơn vị GỐC,
                # đừng cộng bừa hai thang rồi in ra một con số không có nghĩa.
                if cu["dvt"] == d["dvt"]:
                    cu["sl"] += float(d["sl"] or 0)
                else:
                    cu["dvt"] = cu["dvt_goc"]
                    cu["sl"] = cu["sl_goc"]
        return list(gom.values())
```

> Tên khoá `ten_hang` / `dvt_goc` / `sl_goc` mà `_nap_mat_hang` + `_quy_doi_dong` đặt vào dòng có
> thể khác. **Trước khi viết, đọc `sed -n '1022,1051p' backend/app/services/ke_hoach_vat_tu_service.py`**
> và dùng ĐÚNG tên khoá hai hàm đó tạo ra.

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py tests/test_ke_hoach_vat_tu.py -q
```

Kỳ vọng: pass hết (file kế hoạch vật tư không được đỏ — ta chỉ THÊM phương thức).

- [ ] **Step 5: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/ke_hoach_vat_tu_service.py backend/tests/test_sx_vat_tu_de_nghi.py
git commit -m "Kế hoạch vật tư: phương thức công khai nhu cầu của một công việc sản xuất"
```

---

### Task 3: Repository + luật tạo đề nghị

**Files:**
- Create: `backend/app/repositories/san_xuat_vat_tu_repo.py`, `backend/app/services/san_xuat/vat_tu_de_nghi.py`
- Test: `backend/tests/test_sx_vat_tu_de_nghi.py` (thêm)

**Interfaces:**
- Consumes: `nhu_cau_cua_cong_viec` (Task 2); `_gate_to_truong(db, user, department_id)` từ `services/san_xuat/vat_tu_nhan.py:19` (tái dùng, **không** viết cổng thứ hai); `StockRequestService.create(user=..., loai="XUAT", lines=[...], **header)`.
- Produces:
  ```python
  class SanXuatVatTuRepository:
      def de_nghi(self, de_nghi_id) -> SanXuatVatTuDeNghi | None
      def cac_de_nghi(self, cong_viec_id) -> list[SanXuatVatTuDeNghi]
      def lan_ke_tiep(self, cong_viec_id) -> int
      def co_voucher(self, stock_request_id) -> bool

  def tao(db, *, user, cong_viec_id: int, can_luc, lines: list[dict]) -> dict
  class VatTuDeNghiError(Exception): ...
  ```

- [ ] **Step 1: Viết test thất bại trước**

```python
def test_tao_luu_ca_dong_xin_0_va_chi_gui_kho_dong_duong(
    db, orders, lsx_svc, admin, customer,
):
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT3")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    assert len(kh) >= 1

    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"],
              "dvt": kh[0]["dvt"], "sl_yeu_cau": 0, "ly_do_chenh_lech": "Tổ còn tồn tại chỗ"}]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    dn = db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"])
    assert dn.lan_so == 1 and dn.loai == DN_LAN_DAU
    assert len(dn.dongs) == len(kh)          # lưu MỌI vật tư kế hoạch, kể cả dòng 0
    assert dn.stock_request_id is None       # không dòng dương ⇒ KHÔNG đẻ chứng từ kho


def test_tao_co_dong_duong_thi_de_yeu_cau_kho_approved(db, orders, lsx_svc, admin, customer):
    from app.models.stock_request import REQ_APPROVED, REQ_XUAT, StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT4")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    ra = V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)

    req = db.get(StockRequest, ra["stock_request_id"])
    assert req.loai == REQ_XUAT
    assert req.trang_thai == REQ_APPROVED
    assert req.bo_phan_id == cv.department_id     # tổ của CÔNG ĐOẠN, không phải phòng của user
    assert req.nguoi_tao_id == admin.id
    assert req.ngay_can == _T0.date()
    assert all(float(l.sl_de_nghi) > 0 for l in req.lines)


def test_khop_ke_hoach_thi_khong_doi_ly_do(db, orders, lsx_svc, admin, customer):
    """Xin đúng số kế hoạch (sau quy đổi) ⇒ không phải giải thích gì."""
    ...  # dựng như test trên, không truyền `ly_do_chenh_lech`, assert không raise


def test_lech_ke_hoach_ma_thieu_ly_do_thi_chan(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT5")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"],
              "dvt": kh[0]["dvt"], "sl_yeu_cau": kh[0]["sl"] * 1.5}]
    with pytest.raises(VatTuDeNghiError) as e:
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    assert "lý do" in str(e.value).lower()


def test_khong_phai_to_truong_thi_chan(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT6")
    to.head_user_id = None          # không ai là tổ trưởng ⇒ kể cả admin cũng không ghi được
    db.commit()
    with pytest.raises(PermissionError):
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=[])


def test_dang_co_de_nghi_sua_duoc_thi_khong_tao_them(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V
    from tests.test_san_xuat_thuc_thi import _mot_cv  # noqa

    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-VT7")
    to.head_user_id = admin.id
    db.commit()
    kh = _kh_service(db).nhu_cau_cua_cong_viec(cv)
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"],
              "dvt": k["dvt"], "sl_yeu_cau": k["sl"]} for k in kh]
    V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    with pytest.raises(VatTuDeNghiError) as e:
        V.tao(db, user=admin, cong_viec_id=cv.id, can_luc=_T0, lines=lines)
    assert "sửa" in str(e.value).lower()
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py -q -k "tao or ly_do or to_truong or sua_duoc"
```

Kỳ vọng: FAIL — `ModuleNotFoundError: app.services.san_xuat.vat_tu_de_nghi`.

- [ ] **Step 3: Viết repository**

Tạo `backend/app/repositories/san_xuat_vat_tu_repo.py`:

```python
"""Truy vấn cho đề nghị cấp vật tư theo công đoạn."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models.san_xuat_vat_tu import SanXuatVatTuDeNghi, SanXuatVatTuDeNghiDong
from ..models.stock_voucher import StockVoucher


class SanXuatVatTuRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def de_nghi(self, de_nghi_id: int) -> SanXuatVatTuDeNghi | None:
        return self.db.scalars(
            select(SanXuatVatTuDeNghi)
            .options(selectinload(SanXuatVatTuDeNghi.dongs))
            .where(SanXuatVatTuDeNghi.id == de_nghi_id)
        ).first()

    def cac_de_nghi(self, cong_viec_id: int) -> list[SanXuatVatTuDeNghi]:
        return list(self.db.scalars(
            select(SanXuatVatTuDeNghi)
            .options(selectinload(SanXuatVatTuDeNghi.dongs))
            .where(SanXuatVatTuDeNghi.cong_viec_id == cong_viec_id)
            .order_by(SanXuatVatTuDeNghi.lan_so)
        ))

    def lan_ke_tiep(self, cong_viec_id: int) -> int:
        cao = self.db.scalar(
            select(func.max(SanXuatVatTuDeNghi.lan_so))
            .where(SanXuatVatTuDeNghi.cong_viec_id == cong_viec_id)
        )
        return int(cao or 0) + 1

    def co_voucher(self, stock_request_id: int | None) -> bool:
        """Yêu cầu kho đã có BẤT KỲ phiếu nào chưa — kể cả nháp, kể cả đã huỷ.

        Không lọc trạng thái phiếu: kho đã bắt tay soạn (dù nháp) thì con số đã đi vào đầu người
        soạn; sửa sau lưng họ là nguồn đẻ ra chênh lệch mà không ai truy được.
        """
        if not stock_request_id:
            return False
        return self.db.scalar(
            select(func.count()).select_from(StockVoucher)
            .where(StockVoucher.request_id == stock_request_id)
        ) > 0
```

- [ ] **Step 4: Viết service — phần tạo**

Tạo `backend/app/services/san_xuat/vat_tu_de_nghi.py`:

```python
"""Tổ trưởng đề nghị cấp vật tư cho công đoạn của mình (spec-de-nghi-cap-vat-tu-cong-doan §5).

Ranh giới an ninh THỰC nằm ở đây, không ở router: router chỉ gác bit thô `san_xuat:assign_work`
(mọi tổ trưởng SX đều có), còn "đúng tổ nào" thì chỉ tầng này biết. Tái dùng `_gate_to_truong` của
`vat_tu_nhan.py` — hai cổng cùng nghĩa mà viết hai lần là mời chúng lệch nhau.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ...models.san_xuat_vat_tu import (
    DN_BO_SUNG, DN_LAN_DAU, SanXuatVatTuDeNghi, SanXuatVatTuDeNghiDong,
)
from ...models.stock_request import REQ_XUAT
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_vat_tu_repo import SanXuatVatTuRepository
from ..realtime import hub
from .vat_tu_nhan import _gate_to_truong

_EPS = 0.0005      # cùng dung sai làm tròn với `san_luong.tao_batch`


class VatTuDeNghiError(Exception):
    """Lỗi NGHIỆP VỤ (400) — khác `PermissionError` (403)."""


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _chuan_hoa(db, kh_svc, cv, lines: list[dict], *, bat_buoc_ly_do: bool) -> list[dict]:
    """Trộn kế hoạch với số tổ khai, QUY ĐỔI LẠI ở BE, và bắt lý do đúng luật (§3, §4).

    Không tin đơn vị/số của client: nó chỉ nói "xin 3 ram" — quy 3 ram ra bao nhiêu kg là việc của
    engine đơn vị, và phải là CÙNG engine mà bảng cân đối dùng, không thì hai bên đếm hai kiểu.
    """
    kh = {(k["hang_loai"], int(k["hang_id"])): k for k in kh_svc.nhu_cau_cua_cong_viec(cv)}
    khai: dict[tuple, dict] = {}
    for ln in lines:
        k = (ln["hang_loai"], int(ln["hang_id"]))
        if k in khai:
            raise VatTuDeNghiError("Một mặt hàng chỉ được khai một dòng — gộp số lượng lại.")
        khai[k] = ln

    ra: list[dict] = []
    for k in list(kh) + [k for k in khai if k not in kh]:
        k_row = kh.get(k)
        ln = khai.get(k)
        # Dòng NGOÀI kế hoạch mà xin 0 là vô nghĩa — không lưu (§4).
        if k_row is None and (ln is None or _f(ln.get("sl_yeu_cau")) <= _EPS):
            continue
        dvt = (ln or {}).get("dvt") or (k_row or {})["dvt"]
        sl = _f((ln or {}).get("sl_yeu_cau"))
        goc = kh_svc.ve_don_vi_goc(k[0], k[1], dvt, sl)   # (sl_goc, dvt_goc)
        kh_goc = _f((k_row or {}).get("sl_goc"))
        ly_do = ((ln or {}).get("ly_do_chenh_lech") or "").strip() or None
        lech = abs(goc[0] - kh_goc) > _EPS
        # Ngoài kế hoạch + số dương ⇒ luôn phải giải thích. Bổ sung ⇒ mọi dòng khác 0 phải giải
        # thích (kế hoạch đã dùng hết ở lần đầu, xin thêm là một quyết định mới).
        can_ly_do = lech or (k_row is None and goc[0] > _EPS) \
            or (bat_buoc_ly_do and goc[0] > _EPS)
        if can_ly_do and not ly_do:
            ten = (k_row or {}).get("ten") or f"#{k[1]}"
            raise VatTuDeNghiError(f"«{ten}» lệch kế hoạch — phải ghi lý do.")
        ra.append({
            "hang_loai": k[0], "hang_id": k[1],
            "ten": (k_row or {}).get("ten") or f"#{k[1]}",
            "dvt": dvt, "dvt_goc": goc[1],
            "sl_ke_hoach": _f((k_row or {}).get("sl")), "sl_ke_hoach_goc": kh_goc,
            "sl_yeu_cau": sl, "sl_yeu_cau_goc": goc[0],
            "ly_do_chenh_lech": ly_do,
        })
    return ra


def _lines_kho(cv, dongs: list[dict]) -> list[dict]:
    """Dòng yêu cầu kho = phần DƯƠNG của bản đối chiếu. Kho không thấy dòng 0, không thấy lý do."""
    return [
        {"hang_loai": d["hang_loai"], "hang_id": d["hang_id"], "dvt": d["dvt"],
         "sl_de_nghi": d["sl_yeu_cau"],
         "lsx_id": cv.lsx_id, "bai_ghep_id": cv.bai_ghep_id}
        for d in dongs if d["sl_yeu_cau"] > _EPS
    ]


def tao(db: Session, *, user, cong_viec_id: int, can_luc: datetime,
        lines: list[dict], kh_svc=None, req_svc=None) -> dict:
    """Tạo một LẦN đề nghị. Lần 1 = `lan_dau`, từ lần 2 trở đi = `bo_sung`."""
    repo = SanXuatRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate_to_truong(db, user, cv.department_id)

    vt_repo = SanXuatVatTuRepository(db)
    cac = vt_repo.cac_de_nghi(cong_viec_id)
    if cac and not vt_repo.co_voucher(cac[-1].stock_request_id):
        raise VatTuDeNghiError(
            "Đang có đề nghị chưa được kho lập phiếu — hãy sửa đề nghị đó thay vì tạo lần mới.")

    lan_so = vt_repo.lan_ke_tiep(cong_viec_id)
    loai = DN_LAN_DAU if lan_so == 1 else DN_BO_SUNG
    kh_svc = kh_svc or _kh_service(db)
    dongs = _chuan_hoa(db, kh_svc, cv, lines, bat_buoc_ly_do=(loai == DN_BO_SUNG))

    dn = SanXuatVatTuDeNghi(
        cong_viec_id=cong_viec_id, lan_so=lan_so, loai=loai, can_luc=can_luc,
        created_by_id=getattr(user, "id", None), updated_by_id=getattr(user, "id", None),
    )
    db.add(dn)
    db.flush()
    for d in dongs:
        db.add(SanXuatVatTuDeNghiDong(de_nghi_id=dn.id, **{
            k: v for k, v in d.items() if k != "ten"
        }))

    kho_lines = _lines_kho(cv, dongs)
    if kho_lines:
        req_svc = req_svc or _req_service(db)
        req = req_svc.create(
            user=user, loai=REQ_XUAT, lines=kho_lines,
            # `bo_phan_id` phải khai TAY: mặc định của `create` là `user.department_id` — phòng của
            # người bấm, không phải TỔ của công đoạn. Để mặc định là yêu cầu hiện sai bộ phận trên
            # bản in và lệch scope `department` của kho.
            bo_phan_id=cv.department_id,
            ngay_can=can_luc.date(),
            ghi_chu=f"Cấp vật tư công đoạn «{cv.ten_cong_doan}» (lần {lan_so}).",
        )
        dn.stock_request_id = req.id

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None), action="san_xuat_de_nghi_vat_tu",
        target=f"san_xuat_cong_viec:{cong_viec_id}",
        detail=f"lần {lan_so} · {len(kho_lines)} dòng gửi kho",
    )
    db.commit()
    hub.broadcast({"type": "san_xuat_vat_tu_de_nghi_changed",
                   "cong_viec_id": cong_viec_id})
    return {"de_nghi_id": dn.id, "stock_request_id": dn.stock_request_id, "lan_so": lan_so}
```

Hai hàm dựng service (`_kh_service`, `_req_service`) copy đúng chuỗi repo từ
`backend/app/routers/ke_hoach_vat_tu.py::get_service()` và `backend/app/routers/kho.py` — **đừng
tự ghép bộ khác**, thiếu một repo là engine im lặng trả rỗng.

`kh_svc.ve_don_vi_goc(hang_loai, hang_id, dvt, sl) -> (sl_goc, dvt_goc)` là wrapper công khai mỏng
quanh `KeHoachVatTuService._ve_goc` — thêm nó trong Task 2 nếu chưa có (một hàm 3 dòng, đừng gọi
`_ve_goc` từ ngoài).

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py -q
```

- [ ] **Step 6: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/repositories/san_xuat_vat_tu_repo.py backend/app/services/san_xuat/vat_tu_de_nghi.py backend/tests/test_sx_vat_tu_de_nghi.py
git commit -m "Vật tư công đoạn: luật tạo đề nghị + sinh yêu cầu kho"
```

---

### Task 4: Sửa đề nghị — đồng bộ, huỷ về 0, khôi phục, khoá

**Files:**
- Modify: `backend/app/services/stock_request_service.py`
- Modify: `backend/app/services/san_xuat/vat_tu_de_nghi.py`
- Test: `backend/tests/test_sx_vat_tu_de_nghi.py` (thêm)

**Interfaces:**
- Produces:
  ```python
  # stock_request_service.py
  def dong_bo_tu_san_xuat(self, req_id: int, lines: list[dict], *, user, ngay_can) -> StockRequest
  def huy_tu_san_xuat(self, req_id: int, *, user) -> StockRequest
  def khoi_phuc_tu_san_xuat(self, req_id: int, lines: list[dict], *, user, ngay_can) -> StockRequest
  # vat_tu_de_nghi.py
  def sua(db, *, user, cong_viec_id: int, de_nghi_id: int, can_luc, lines) -> dict
  ```

- [ ] **Step 1: Viết test thất bại trước**

```python
def test_sua_truoc_khi_co_phieu_thi_de_len_chinh_yeu_cau_cu(db, orders, lsx_svc, admin, customer):
    """Giữ MÃ và ID — kho đã nhìn thấy số DNX… đó rồi, đổi mã là bắt họ đi tìm lại."""
    from app.models.stock_request import StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, ma_cu, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VT8")
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
              "sl_yeu_cau": k["sl"] * 2, "ly_do_chenh_lech": "Chạy bù mẻ hỏng"} for k in kh]
    V.sua(db, user=admin, cong_viec_id=_cv_id(db, dn_id), de_nghi_id=dn_id,
          can_luc=_T0, lines=lines)

    req = db.get(StockRequest, req_id)
    assert req.ma == ma_cu and req.id == req_id
    assert float(req.lines[0].sl_de_nghi) == pytest.approx(kh[0]["sl"] * 2)
    assert float(req.lines[0].sl_duyet) == float(req.lines[0].sl_de_nghi)


def test_sua_het_ve_0_thi_huy_yeu_cau_nhung_giu_ma(db, orders, lsx_svc, admin, customer):
    from app.models.stock_request import REQ_CANCELLED, StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, ma_cu, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VT9")
    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
              "sl_yeu_cau": 0, "ly_do_chenh_lech": "Tổ đã có sẵn"} for k in kh]
    V.sua(db, user=admin, cong_viec_id=_cv_id(db, dn_id), de_nghi_id=dn_id,
          can_luc=_T0, lines=lines)

    req = db.get(StockRequest, req_id)
    assert req.trang_thai == REQ_CANCELLED
    assert req.ma == ma_cu
    assert req.lines == []
    assert "không cần cấp" in (req.ly_do_huy or "")
    # Bản ghi SẢN XUẤT vẫn còn nguyên và vẫn trỏ vào yêu cầu đó.
    assert db.get(SanXuatVatTuDeNghi, dn_id).stock_request_id == req_id


def test_nhap_lai_so_duong_thi_khoi_phuc_dung_yeu_cau_cu(db, orders, lsx_svc, admin, customer):
    from app.models.stock_request import REQ_APPROVED, StockRequest
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, ma_cu, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTA")
    cv_id = _cv_id(db, dn_id)
    ve0 = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
            "sl_yeu_cau": 0, "ly_do_chenh_lech": "nhầm"} for k in kh]
    V.sua(db, user=admin, cong_viec_id=cv_id, de_nghi_id=dn_id, can_luc=_T0, lines=ve0)
    lai = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
            "sl_yeu_cau": k["sl"]} for k in kh]
    V.sua(db, user=admin, cong_viec_id=cv_id, de_nghi_id=dn_id, can_luc=_T0, lines=lai)

    req = db.get(StockRequest, req_id)
    assert req.trang_thai == REQ_APPROVED
    assert req.ma == ma_cu            # KHÔNG đẻ mã mới
    assert len(req.lines) == len(kh)


def test_co_phieu_roi_thi_sua_bi_chan_va_khong_doi_gi(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat.vat_tu_de_nghi import VatTuDeNghiError
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTB")
    _lap_phieu_nhap_kho_cho(db, req_id)      # helper: đẻ 1 StockVoucher NHÁP cho yêu cầu
    truoc = [(l.id, float(l.sl_de_nghi)) for l in db.get(StockRequest, req_id).lines]

    lines = [{"hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "dvt": k["dvt"],
              "sl_yeu_cau": k["sl"] * 3, "ly_do_chenh_lech": "x"} for k in kh]
    with pytest.raises(VatTuDeNghiError) as e:
        V.sua(db, user=admin, cong_viec_id=_cv_id(db, dn_id), de_nghi_id=dn_id,
              can_luc=_T0, lines=lines)
    assert "phiếu" in str(e.value).lower()
    db.rollback()
    assert [(l.id, float(l.sl_de_nghi)) for l in db.get(StockRequest, req_id).lines] == truoc


def test_khoa_roi_thi_tao_duoc_lan_bo_sung(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import vat_tu_de_nghi as V

    dn_id, req_id, _ma, kh = _tao_de_nghi(db, orders, lsx_svc, admin, customer, "TO-VTC")
    _lap_phieu_nhap_kho_cho(db, req_id)
    cv_id = _cv_id(db, dn_id)
    lines = [{"hang_loai": kh[0]["hang_loai"], "hang_id": kh[0]["hang_id"], "dvt": kh[0]["dvt"],
              "sl_yeu_cau": 10, "ly_do_chenh_lech": "Bù hao khi canh máy"}]
    ra = V.tao(db, user=admin, cong_viec_id=cv_id, can_luc=_T0, lines=lines)
    assert ra["lan_so"] == 2
    assert db.get(SanXuatVatTuDeNghi, ra["de_nghi_id"]).loai == DN_BO_SUNG
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py -q -k "sua or khoi_phuc or bo_sung"
```

- [ ] **Step 3: Ba phương thức đồng bộ trong `StockRequestService`**

```python
    # --- ĐỒNG BỘ TỪ SẢN XUẤT (spec-de-nghi-cap-vat-tu-cong-doan §5.2–§5.3) -------------------
    # KHÔNG tái dùng `update()`: nó chạy `_require_editable`, mà yêu cầu do sản xuất tạo đã ở
    # `approved` ngay từ đầu (create tự duyệt). Ba hàm dưới là đường RIÊNG, chỉ tầng
    # `services/san_xuat/vat_tu_de_nghi.py` được gọi — mọi cửa khác vẫn giữ luật "đã duyệt là khoá".

    def dong_bo_tu_san_xuat(self, req_id: int, lines: list[dict], *, user, ngay_can):
        """Thay TOÀN BỘ dòng bằng dữ liệu mới, giữ nguyên mã và id."""
        self.requests.lock_for_update(req_id)
        req = self.requests.get_with_lines(req_id)
        if req is None:
            raise StockRequestError("Không tìm thấy yêu cầu.")
        if self._co_voucher(req.id):
            raise StockRequestError("Kho đã lập phiếu cho yêu cầu này — không sửa được nữa.")
        self._validate_lines(lines)
        req.lines.clear()
        self.requests.db.flush()
        for ln in lines:
            req.lines.append(StockRequestLine(**ln, sl_duyet=ln["sl_de_nghi"]))
        req.ngay_can = ngay_can
        req.trang_thai = REQ_APPROVED
        req.ly_do_huy = None
        req = self.requests.save(req)
        # Hộp yêu cầu kho phải thấy con số mới NGAY — số cũ đang nằm trên màn của thủ kho.
        self._notify(req, "Yêu cầu vừa được cập nhật", targeted=False)
        return req

    def huy_tu_san_xuat(self, req_id: int, *, user):
        """Tổ xác nhận không cần cấp gì: xoá dòng, chuyển `cancelled`, GIỮ mã và link."""
        self.requests.lock_for_update(req_id)
        req = self.requests.get_with_lines(req_id)
        if req is None:
            raise StockRequestError("Không tìm thấy yêu cầu.")
        if self._co_voucher(req.id):
            raise StockRequestError("Kho đã lập phiếu cho yêu cầu này — không huỷ được nữa.")
        req.lines.clear()
        req.trang_thai = REQ_CANCELLED
        req.ly_do_huy = "Tổ xác nhận không cần cấp"
        req = self.requests.save(req)
        self._notify(req, "Tổ xác nhận không cần cấp", targeted=False)
        return req

    def khoi_phuc_tu_san_xuat(self, req_id: int, lines: list[dict], *, user, ngay_can):
        """Tổ nhập lại số dương sau khi đã về 0 — dựng lại dòng trên CHÍNH yêu cầu đó.

        Không đẻ mã mới: một lần đề nghị của tổ là một chứng từ, tổ đổi ý ba lần trước khi kho
        động tay không phải là ba chứng từ.
        """
        return self.dong_bo_tu_san_xuat(req_id, lines, user=user, ngay_can=ngay_can)

    def _co_voucher(self, req_id: int) -> bool:
        """Có BẤT KỲ phiếu nào chưa — kể cả nháp, kể cả đã huỷ (spec §5.2)."""
        from ..models.stock_voucher import StockVoucher
        return self.requests.db.scalar(
            select(func.count()).select_from(StockVoucher)
            .where(StockVoucher.request_id == req_id)
        ) > 0
```

- [ ] **Step 4: Hàm `sua` trong `vat_tu_de_nghi.py`**

```python
def sua(db: Session, *, user, cong_viec_id: int, de_nghi_id: int,
        can_luc: datetime, lines: list[dict], kh_svc=None, req_svc=None) -> dict:
    """Sửa một lần đề nghị CHƯA bị kho lập phiếu (spec §5.2–§5.4).

    Kiểm khoá phải chạy TRONG transaction, ngay trước khi ghi — kiểm ở router rồi mới vào service
    là mở đúng khe cho kho bấm "lập phiếu" ở giữa hai thời điểm đó.
    """
    repo = SanXuatRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate_to_truong(db, user, cv.department_id)

    vt_repo = SanXuatVatTuRepository(db)
    dn = vt_repo.de_nghi(de_nghi_id)
    if dn is None or dn.cong_viec_id != cong_viec_id:
        raise ValueError("Không tìm thấy đề nghị của công đoạn này.")
    if vt_repo.co_voucher(dn.stock_request_id):
        raise VatTuDeNghiError("Kho đã lập phiếu cho đề nghị này — hãy tạo yêu cầu bổ sung.")

    kh_svc = kh_svc or _kh_service(db)
    dongs = _chuan_hoa(db, kh_svc, cv, lines, bat_buoc_ly_do=(dn.loai == DN_BO_SUNG))

    dn.dongs.clear()
    db.flush()
    for d in dongs:
        db.add(SanXuatVatTuDeNghiDong(de_nghi_id=dn.id, **{
            k: v for k, v in d.items() if k != "ten"
        }))
    dn.can_luc = can_luc
    dn.updated_by_id = getattr(user, "id", None)

    kho_lines = _lines_kho(cv, dongs)
    req_svc = req_svc or _req_service(db)
    if dn.stock_request_id is None:
        # Lần đầu toàn 0, nay có số dương ⇒ giờ mới đẻ chứng từ kho.
        if kho_lines:
            req = req_svc.create(
                user=user, loai=REQ_XUAT, lines=kho_lines, bo_phan_id=cv.department_id,
                ngay_can=can_luc.date(),
                ghi_chu=f"Cấp vật tư công đoạn «{cv.ten_cong_doan}» (lần {dn.lan_so}).",
            )
            dn.stock_request_id = req.id
    elif kho_lines:
        req_svc.khoi_phuc_tu_san_xuat(dn.stock_request_id, kho_lines,
                                      user=user, ngay_can=can_luc.date())
    else:
        req_svc.huy_tu_san_xuat(dn.stock_request_id, user=user)

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None), action="san_xuat_sua_de_nghi_vat_tu",
        target=f"san_xuat_vat_tu_de_nghi:{dn.id}",
        detail=f"{len(kho_lines)} dòng gửi kho",
    )
    db.commit()
    hub.broadcast({"type": "san_xuat_vat_tu_de_nghi_changed", "cong_viec_id": cong_viec_id})
    # Bắn LẠI tín hiệu kho: con số trên màn thủ kho vừa đổi (spec §7 phần realtime).
    hub.broadcast({"type": "stock_request_pending_changed"})
    return {"de_nghi_id": dn.id, "stock_request_id": dn.stock_request_id}
```

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py tests/test_kho_yeu_cau.py -q
```

Kỳ vọng: pass hết; test kho cũ không đỏ (ta chỉ THÊM đường riêng, `update()` không đổi).

- [ ] **Step 6: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/stock_request_service.py backend/app/services/san_xuat/vat_tu_de_nghi.py backend/tests/test_sx_vat_tu_de_nghi.py
git commit -m "Vật tư công đoạn: sửa đề nghị đồng bộ đè yêu cầu kho, huỷ và khôi phục giữ mã"
```

---

### Task 5: Kho điều chỉnh thực xuất → `sl_chot_thuc_xuat`

**Files:**
- Modify: `backend/app/services/stock_voucher_service.py` (`dieu_chinh_xuat`, dòng 405–518)
- Modify: `backend/app/services/stock_request_service.py` (`refresh_fulfillment`, dòng 518)
- Test: `backend/tests/test_kho_dieu_chinh_xuat.py`

**Interfaces:**
- Produces: `StockRequestService.muc_tieu_hieu_luc(line) -> float` và `con_lai(line) -> float` (staticmethod, dùng chung cho service lẫn schema).

- [ ] **Step 1: Viết test thất bại trước**

Tạo `backend/tests/test_kho_dieu_chinh_xuat.py`:

```python
"""Điều chỉnh phiếu xuất khi SX dùng ít hơn số đã xuất (spec-de-nghi-cap-vat-tu-cong-doan §2.3, §5.5).

Hai bảng số phải phân biệt được:
  · xin 100, xuất 100, điều chỉnh còn 70 ⇒ chốt 70, CÒN LẠI 0, Hoàn tất;
  · xin 100, kho mới xuất 70, KHÔNG điều chỉnh ⇒ chốt NULL, CÒN LẠI 30, Cấp một phần.
Trước đây `dieu_chinh_xuat` chỉ hạ `sl_da_ung` nên hai ca trên trông y hệt nhau — tổ trưởng nhìn
thấy "còn thiếu 30" ở ca đầu, đi hỏi kho một câu vô nghĩa.
"""
from __future__ import annotations

import pytest


def test_dieu_chinh_ghi_chot_thuc_xuat_va_dong_yeu_cau(db, ...):
    req, v = _xin_100_xuat_100(db, ...)      # helper dựng luồng kho thật
    svc = _voucher_service(db)
    svc.dieu_chinh_xuat(v.id, {v.lines[0].id: 70}, user=_thu_kho(db))

    ln = db.get(StockRequestLine, req.lines[0].id)
    assert float(ln.sl_de_nghi) == 100
    assert float(ln.sl_duyet) == 100          # KHÔNG hạ
    assert float(ln.sl_da_ung) == 70
    assert float(ln.sl_chot_thuc_xuat) == 70
    assert _con_lai(ln) == 0
    assert db.get(StockRequest, req.id).trang_thai == REQ_DONE


def test_xuat_thieu_ma_khong_dieu_chinh_thi_van_con_lai(db, ...):
    req, _v = _xin_100_xuat_70(db, ...)
    ln = db.get(StockRequestLine, req.lines[0].id)
    assert ln.sl_chot_thuc_xuat is None
    assert _con_lai(ln) == 30
    assert db.get(StockRequest, req.id).trang_thai == REQ_PARTIAL


def test_dieu_chinh_hai_lan_thi_chot_bang_tong_thuc_xuat_hien_tai(db, ...):
    """Chốt là TỔNG đã xuất hiện tại, không phải hiệu của lần điều chỉnh cuối."""
    req, v = _xin_100_xuat_100(db, ...)
    svc = _voucher_service(db)
    svc.dieu_chinh_xuat(v.id, {v.lines[0].id: 80}, user=_thu_kho(db))
    svc.dieu_chinh_xuat(v.id, {v.lines[0].id: 60}, user=_thu_kho(db))
    ln = db.get(StockRequestLine, req.lines[0].id)
    assert float(ln.sl_chot_thuc_xuat) == 60
```

> `...` trong chữ ký test = fixture kho đang có. Đọc `backend/tests/test_kho_phieu*.py` /
> `test_kho_yeu_cau.py` (`ls backend/tests | grep kho`) và tái dùng ĐÚNG fixture + helper ở đó.
> Ghi chú của plan cũ: **hiện chưa có test nào chạm `dieu_chinh_xuat`** — đây là test đầu tiên,
> nên dựng helper cẩn thận, nó sẽ được dùng lại.

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_kho_dieu_chinh_xuat.py -q
```

- [ ] **Step 3: Ghi `sl_chot_thuc_xuat`**

Trong `dieu_chinh_xuat`, ngay sau dòng `rl.sl_da_ung = max(0.0, float(rl.sl_da_ung) - con_bo)`:

```python
            # CHỐT thực xuất = TỔNG đã xuất hiện tại của dòng yêu cầu này, không phải hiệu của
            # riêng lần điều chỉnh cuối — điều chỉnh hai lần (100→80→60) phải ra 60, không ra 20.
            # Ghi cột riêng thay vì hạ `sl_duyet`: hạ `sl_duyet` thì xin-100-xuất-70 và
            # xin-70-xuất-70 hoá ra không phân biệt được (spec §2.3).
            rl.sl_chot_thuc_xuat = float(rl.sl_da_ung)
```

- [ ] **Step 4: Mục tiêu hiệu lực trong `refresh_fulfillment`**

Trong `StockRequestService`, thêm staticmethod và dùng nó:

```python
    @staticmethod
    def muc_tieu_hieu_luc(ln) -> float:
        """Mục tiêu HIỆU LỰC của một dòng: kho đã chốt thực xuất thì lấy số chốt, chưa thì `sl_duyet`.

        NULL ≠ 0: NULL là "kho chưa điều chỉnh lần nào", 0 là "chốt rằng không xuất gì".
        """
        chot = getattr(ln, "sl_chot_thuc_xuat", None)
        return float(chot) if chot is not None else float(ln.sl_duyet)

    @staticmethod
    def con_lai(ln) -> float:
        return max(StockRequestService.muc_tieu_hieu_luc(ln) - float(ln.sl_da_ung), 0.0)
```

và đổi `refresh_fulfillment`:

```python
        done = all(float(ln.sl_da_ung) >= self.muc_tieu_hieu_luc(ln) for ln in req.lines)
```

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_kho_dieu_chinh_xuat.py tests/test_kho_yeu_cau.py -q
```

- [ ] **Step 6: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/stock_voucher_service.py backend/app/services/stock_request_service.py backend/tests/test_kho_dieu_chinh_xuat.py
git commit -m "Kho: điều chỉnh xuất ghi sl_chot_thuc_xuat, còn lại tính theo mục tiêu hiệu lực"
```

---

### Task 6: Hai route material-requests

**Files:**
- Modify: `backend/app/routers/san_xuat.py`, `backend/app/schemas/san_xuat.py`
- Test: `backend/tests/test_sx_vat_tu_de_nghi.py` (thêm)

**Interfaces:**
- Produces:
  - `POST /api/san-xuat/work-items/{cong_viec_id}/material-requests`
  - `PUT  /api/san-xuat/work-items/{cong_viec_id}/material-requests/{de_nghi_id}`
  - Body: `VatTuDeNghiIn { can_luc: datetime; lines: list[VatTuDeNghiDongIn] }`,
    `VatTuDeNghiDongIn { hang_loai: str; hang_id: int; dvt: str; sl_yeu_cau: float; ly_do_chenh_lech: str | None }`

- [ ] **Step 1: Viết test thất bại trước**

```python
def test_route_gac_assign_work_va_to_truong(db, client_admin, client_ke_hoach, ...):
    """Người LẬP KẾ HOẠCH có `san_xuat:read` nhưng không phải tổ trưởng ⇒ 403, không phải 200."""
    ...
    r = client_ke_hoach.post(f"/api/san-xuat/work-items/{cv_id}/material-requests",
                             json={"can_luc": _T0.isoformat(), "lines": lines})
    assert r.status_code == 403

    r2 = client_admin.post(f"/api/san-xuat/work-items/{cv_id}/material-requests",
                           json={"can_luc": _T0.isoformat(), "lines": lines})
    assert r2.status_code == 201


def test_route_khong_doi_quyen_kho(db, client_to_truong_khong_co_kho, ...):
    """Tổ trưởng KHÔNG có `kho:request` vẫn gửi được — kho không duyệt, quyền kho không liên quan."""
    r = client_to_truong_khong_co_kho.post(...)
    assert r.status_code == 201
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ** — 404.

- [ ] **Step 3: Schema vào**

Trong `backend/app/schemas/san_xuat.py`:

```python
class VatTuDeNghiDongIn(BaseModel):
    hang_loai: str
    hang_id: int
    dvt: str
    sl_yeu_cau: float = 0.0
    ly_do_chenh_lech: str | None = None


class VatTuDeNghiIn(BaseModel):
    # GIỜ cần, không phải ngày: kho soạn theo ca. `stock_requests.ngay_can` chỉ lưu phần DATE.
    can_luc: datetime
    lines: list[VatTuDeNghiDongIn] = []
```

- [ ] **Step 4: Route**

Trong `backend/app/routers/san_xuat.py`, cạnh các route `assign_work` (~dòng 400):

```python
@router.post("/work-items/{cong_viec_id}/material-requests",
             status_code=status.HTTP_201_CREATED, response_model=None)
def tao_de_nghi_vat_tu(
    cong_viec_id: int,
    body: VatTuDeNghiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
):
    """Tổ đề nghị cấp vật tư cho công đoạn (spec-de-nghi-cap-vat-tu-cong-doan §6).

    Bit `assign_work` chỉ là cổng THÔ — ranh giới thật ("đúng tổ trưởng của tổ nào") nằm trong
    service, giống hệt `phan-cong`. KHÔNG đòi `kho:request`: kho không duyệt yêu cầu này.
    """
    try:
        return vat_tu_de_nghi.tao(
            db, user=user, cong_viec_id=cong_viec_id, can_luc=body.can_luc,
            lines=[l.model_dump() for l in body.lines],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except VatTuDeNghiError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put("/work-items/{cong_viec_id}/material-requests/{de_nghi_id}", response_model=None)
def sua_de_nghi_vat_tu(
    cong_viec_id: int,
    de_nghi_id: int,
    body: VatTuDeNghiIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "assign_work"))],
):
    """`de_nghi_id` là id ĐỀ NGHỊ SẢN XUẤT, không phải id yêu cầu kho — đừng nhầm hai không gian id."""
    try:
        return vat_tu_de_nghi.sua(
            db, user=user, cong_viec_id=cong_viec_id, de_nghi_id=de_nghi_id,
            can_luc=body.can_luc, lines=[l.model_dump() for l in body.lines],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except VatTuDeNghiError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
```

- [ ] **Step 5: Chạy test + restart uvicorn**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py -q
```

- [ ] **Step 6: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/routers/san_xuat.py backend/app/schemas/san_xuat.py backend/tests/test_sx_vat_tu_de_nghi.py
git commit -m "Vật tư công đoạn: 2 API tạo/sửa đề nghị, gác assign_work + đúng tổ trưởng"
```

---

### Task 7: `vat_tu_cap` trong chi tiết công việc + đổi nguồn phiếu

**Files:**
- Modify: `backend/app/repositories/san_xuat_san_luong_repo.py` (`voucher_xuat_cua_lsx`, dòng 299)
- Modify: `backend/app/services/san_xuat/board.py` (dòng 306)
- Modify: `backend/app/schemas/san_xuat.py`
- Test: `backend/tests/test_sx_vat_tu_de_nghi.py` (thêm)

**Interfaces:**
- Produces:
  ```python
  def voucher_xuat_cua_cong_viec(self, cv, stock_request_ids: list[int]) -> tuple[list[StockVoucher], bool]
  # (danh sách phiếu, la_du_lieu_cu)
  ```
  Khối `vat_tu_cap` = `{ke_hoach, cac_de_nghi, doi_chieu, de_nghi_co_the_sua_id, co_the_tao_bo_sung}`.

- [ ] **Step 1: Viết test thất bại trước**

```python
def _authz(db):
    """`chi_tiet_cong_viec(db, user, authz, *, cong_viec_id)` — `authz` nhận `RoleRepository`,
    KHÔNG nhận `Session` (dựng đúng như `deps.get_authorization_service`, `backend/app/deps.py:190`)."""
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def test_doi_chieu_gom_ca_ba_con_so(db, orders, lsx_svc, admin, customer):
    """Kế hoạch / đã yêu cầu / kho thực xuất — mỗi mặt hàng một dòng, cộng dồn qua MỌI lần."""
    ...
    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    d = ct["vat_tu_cap"]["doi_chieu"][0]
    assert set(d) >= {"hang_loai", "hang_id", "ten", "dvt",
                      "sl_ke_hoach", "sl_yeu_cau", "sl_thuc_xuat",
                      "lech_ke_hoach", "lech_thuc_te", "cac_ly_do"}
    assert d["lech_ke_hoach"] == pytest.approx(d["sl_yeu_cau"] - d["sl_ke_hoach"])
    assert d["lech_thuc_te"] == pytest.approx(d["sl_thuc_xuat"] - d["sl_yeu_cau"])


def test_cong_doan_co_de_nghi_thi_khong_lay_phieu_theo_lsx(db, ...):
    """Công đoạn đã nối link mới KHÔNG được trộn đường lùi — nếu không, tổ in thấy cả phiếu của
    tổ cán màng chỉ vì hai bên cùng một LSX."""
    ...
    assert {v["voucher_id"] for v in ct["vat_tu"]} == {phieu_cua_de_nghi.id}
    assert ct["vat_tu_cap"]["du_lieu_cu"] is False


def test_cong_doan_chua_tung_co_de_nghi_thi_lui_ve_lsx_va_danh_dau(db, ...):
    ...
    assert ct["vat_tu_cap"]["du_lieu_cu"] is True


def test_field_moi_khong_bi_pydantic_nuot(db, client_admin, ...):
    """`WorkItemChiTietOut` CÓ response_model ⇒ field chưa khai bị bỏ IM LẶNG. Test qua HTTP."""
    r = client_admin.get(f"/api/san-xuat/work-items/{cv_id}")
    assert r.status_code == 200
    assert "vat_tu_cap" in r.json()
    assert "doi_chieu" in r.json()["vat_tu_cap"]
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

- [ ] **Step 3: Đổi truy vấn phiếu**

Trong `backend/app/repositories/san_xuat_san_luong_repo.py`, thêm (giữ nguyên hàm cũ để không vỡ
chỗ gọi khác — kiểm bằng `grep -rn "voucher_xuat_cua_lsx" backend/`):

```python
    def voucher_xuat_cua_cong_viec(self, cv, stock_request_ids: list[int]):
        """Phiếu XUẤT đã ghi sổ mà tổ của CÔNG ĐOẠN này cần xác nhận.

        Công đoạn đã có đề nghị ⇒ CHỈ lấy phiếu của các yêu cầu liên kết. Đường lùi theo `lsx_id`
        chỉ dành cho công đoạn CHƯA TỪNG có đề nghị (dữ liệu trước 31/08/2026) — trộn hai đường là
        cho tổ in thấy cả phiếu của tổ cán màng chỉ vì chung một LSX.

        Bài ghép KHÔNG có đường lùi: dòng yêu cầu cũ khai `lsx_id`, mà bước chung của bài không
        thuộc LSX nào — lùi ở đây là trả về danh sách sai chứ không phải danh sách thiếu.

        Trả `(phiếu, la_du_lieu_cu)`.
        """
        if stock_request_ids:
            return list(self.db.scalars(
                select(StockVoucher)
                .where(StockVoucher.loai == VOUCHER_XUAT,
                       StockVoucher.trang_thai == VOUCHER_POSTED,
                       StockVoucher.request_id.in_(stock_request_ids))
                .order_by(StockVoucher.id)
            )), False
        if cv.bai_ghep_id or not cv.lsx_id:
            return [], False
        return self.voucher_xuat_cua_lsx(cv.lsx_id), True
```

Trong `board.py` dòng 306, đổi:

```python
    vt_repo = SanXuatVatTuRepository(db)
    cac_dn = vt_repo.cac_de_nghi(cv.id)
    req_ids = [d.stock_request_id for d in cac_dn if d.stock_request_id]
    vouchers, du_lieu_cu = sl.voucher_xuat_cua_cong_viec(cv, req_ids)
```

- [ ] **Step 4: Dựng khối `vat_tu_cap`**

Trong `board.py`, thêm hàm phụ và gắn vào dict trả về:

```python
def _vat_tu_cap(db, sl, kh_svc, cv, cac_dn, vt_repo, du_lieu_cu: bool) -> dict:
    """Khối vật tư cấp của drawer công đoạn (spec-de-nghi-cap-vat-tu-cong-doan §6).

    Ba con số của mỗi mặt hàng cộng dồn qua MỌI lần đề nghị — lần bổ sung là CỘNG THÊM, không ghi
    đè lần trước. `sl_thuc_xuat` lấy từ dòng phiếu `posted` HIỆN TẠI (ưu tiên `sl_goc`), tức là số
    SAU điều chỉnh: đọc `sl_da_ung` cũng ra số đó, nhưng đọc thẳng chứng từ thì không phụ thuộc
    thứ tự các bước cập nhật.
    """
    ke_hoach = kh_svc.nhu_cau_cua_cong_viec(cv)
    thuc_xuat = sl.thuc_xuat_theo_hang([d.stock_request_id for d in cac_dn if d.stock_request_id])

    gom: dict[tuple, dict] = {}
    for k in ke_hoach:
        gom[(k["hang_loai"], k["hang_id"])] = {
            "hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "ten": k["ten"],
            "dvt": k["dvt"], "sl_ke_hoach": k["sl"], "sl_yeu_cau": 0.0,
            "sl_thuc_xuat": 0.0, "cac_ly_do": [],
        }
    for dn in cac_dn:
        for d in dn.dongs:
            key = (d.hang_loai, d.hang_id)
            row = gom.setdefault(key, {
                "hang_loai": d.hang_loai, "hang_id": d.hang_id,
                "ten": sl.ten_hang(d.hang_loai, d.hang_id), "dvt": d.dvt,
                "sl_ke_hoach": float(d.sl_ke_hoach), "sl_yeu_cau": 0.0,
                "sl_thuc_xuat": 0.0, "cac_ly_do": [],
            })
            row["sl_yeu_cau"] += float(d.sl_yeu_cau)
            if d.ly_do_chenh_lech:
                row["cac_ly_do"].append({"lan_so": dn.lan_so, "ly_do": d.ly_do_chenh_lech})
    for key, sl_ra in thuc_xuat.items():
        if key in gom:
            gom[key]["sl_thuc_xuat"] = sl_ra

    doi_chieu = []
    for row in gom.values():
        row["lech_ke_hoach"] = row["sl_yeu_cau"] - row["sl_ke_hoach"]
        row["lech_thuc_te"] = row["sl_thuc_xuat"] - row["sl_yeu_cau"]
        doi_chieu.append(row)

    lan_cuoi = cac_dn[-1] if cac_dn else None
    con_sua_duoc = bool(lan_cuoi) and not vt_repo.co_voucher(lan_cuoi.stock_request_id)
    return {
        "ke_hoach": ke_hoach,
        "cac_de_nghi": [{
            "id": d.id, "lan_so": d.lan_so, "loai": d.loai, "can_luc": d.can_luc,
            "stock_request_id": d.stock_request_id,
            "stock_request_ma": sl.ma_yeu_cau(d.stock_request_id),
            "stock_request_trang_thai": sl.trang_thai_yeu_cau(d.stock_request_id),
            "created_by_id": d.created_by_id, "updated_by_id": d.updated_by_id,
            "created_at": d.created_at, "updated_at": d.updated_at,
        } for d in cac_dn],
        "doi_chieu": doi_chieu,
        "de_nghi_co_the_sua_id": lan_cuoi.id if con_sua_duoc else None,
        "co_the_tao_bo_sung": (not cac_dn) or (not con_sua_duoc),
        "du_lieu_cu": du_lieu_cu,
    }
```

Ba hàm repo phụ (`thuc_xuat_theo_hang`, `ten_hang`, `ma_yeu_cau`/`trang_thai_yeu_cau`) viết vào
`san_xuat_san_luong_repo.py` — mỗi cái một truy vấn GỘP, **không** gọi trong vòng lặp.
`thuc_xuat_theo_hang` gom `StockVoucherLine.sl_goc` của phiếu `posted` theo `(hang_loai, hang_id)`.

- [ ] **Step 5: Khai schema ra (BẮT BUỘC)**

Trong `backend/app/schemas/san_xuat.py`:

```python
class VatTuCapDoiChieuOut(BaseModel):
    hang_loai: str
    hang_id: int
    ten: str
    dvt: str
    sl_ke_hoach: float
    sl_yeu_cau: float
    sl_thuc_xuat: float
    lech_ke_hoach: float
    lech_thuc_te: float
    cac_ly_do: list[dict] = []


class VatTuCapLanOut(BaseModel):
    id: int
    lan_so: int
    loai: str
    can_luc: datetime
    stock_request_id: int | None = None
    stock_request_ma: str | None = None
    stock_request_trang_thai: str | None = None
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime
    updated_at: datetime


class VatTuCapOut(BaseModel):
    ke_hoach: list[dict] = []
    cac_de_nghi: list[VatTuCapLanOut] = []
    doi_chieu: list[VatTuCapDoiChieuOut] = []
    de_nghi_co_the_sua_id: int | None = None
    co_the_tao_bo_sung: bool = True
    # Công đoạn chưa từng có đề nghị nên phiếu đang lấy theo đường lùi `lsx_id` — UI phải nói rõ
    # đây là dữ liệu trước 31/08/2026, đừng để người đọc tưởng nó cùng độ tin cậy.
    du_lieu_cu: bool = False
```

và vào `WorkItemChiTietOut` (GIỮ `vat_tu` cũ trong giai đoạn chuyển tiếp):

```python
    vat_tu: list[VatTuNhanOut]
    vat_tu_cap: VatTuCapOut = VatTuCapOut()
```

- [ ] **Step 6: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_sx_vat_tu_de_nghi.py tests/test_san_xuat_board.py tests/test_san_xuat_board_api.py tests/test_san_xuat_vat_tu_nhan.py -q
```

- [ ] **Step 7: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/repositories/san_xuat_san_luong_repo.py backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py backend/tests/test_sx_vat_tu_de_nghi.py
git commit -m "Vật tư công đoạn: khối đối chiếu trong drawer, phiếu lấy theo công việc thay vì theo LSX"
```

---

### Task 8: Màn kho — tổ, công đoạn, giờ cần, "thực xuất N / yêu cầu M"

**Files:**
- Modify: `backend/app/schemas/stock.py`, `backend/app/services/stock_request_service.py` (chỗ dựng dict ra)
- Modify: `frontend/src/api/client.ts`, `frontend/src/pages/KhoYeuCauPage.tsx`

**Interfaces:**
- Produces: `StockRequestLineOut.sl_chot_thuc_xuat: float | None`, `.sl_con_lai: float`;
  `StockRequestOut.can_luc: datetime | None`, `.san_xuat_cong_viec_id: int | None`,
  `.san_xuat_cong_doan_ten: str | None`.

- [ ] **Step 1: Viết test thất bại trước**

```python
def test_api_yeu_cau_bay_gio_can_va_cong_doan(db, client_thu_kho, ...):
    r = client_thu_kho.get(f"/api/kho/yeu-cau/{req_id}")
    body = r.json()
    assert body["can_luc"] is not None
    assert body["san_xuat_cong_doan_ten"]
    assert body["lines"][0]["sl_con_lai"] == 0
    assert body["lines"][0]["sl_chot_thuc_xuat"] == 70


def test_api_yeu_cau_kho_thuong_khong_co_cong_doan(db, client_thu_kho, ...):
    """Yêu cầu do bộ phận khác lập vẫn trả 3 field đó nhưng đều null — FE không phải phân nhánh."""
    body = client_thu_kho.get(f"/api/kho/yeu-cau/{req_thuong_id}").json()
    assert body["can_luc"] is None
    assert body["san_xuat_cong_viec_id"] is None
    assert body["san_xuat_cong_doan_ten"] is None
```

- [ ] **Step 2: Chạy test → ĐỎ.**

- [ ] **Step 3: Mở rộng schema + chỗ dựng dict**

Trong `backend/app/schemas/stock.py`:

```python
class StockRequestLineOut(BaseModel):
    ...
    # Kho đã CHỐT thực xuất bao nhiêu (null = chưa điều chỉnh lần nào).
    sl_chot_thuc_xuat: float | None = None
    # `max(coalesce(sl_chot_thuc_xuat, sl_duyet) - sl_da_ung, 0)` — tính, KHÔNG lưu.
    sl_con_lai: float = 0.0
```

```python
class StockRequestOut(BaseModel):
    ...
    # GIỜ cần thật (từ đề nghị sản xuất). `ngay_can` chỉ có DATE nên không diễn đạt được ca chiều.
    can_luc: datetime | None = None
    san_xuat_cong_viec_id: int | None = None
    san_xuat_cong_doan_ten: str | None = None
```

Trong service, chỗ dựng dict ra của yêu cầu: điền `sl_con_lai = self.con_lai(ln)` cho từng dòng,
và nạp GỘP `can_luc` / `cong_viec_id` / `cong_doan_ten` bằng MỘT truy vấn join
`san_xuat_vat_tu_de_nghi` → `san_xuat_cong_viec` theo tập `request_id` — **không** truy vấn trong
vòng lặp (hộp yêu cầu kho hiện hàng trăm dòng).

- [ ] **Step 4: FE**

`frontend/src/api/client.ts`: thêm đúng 5 field trên vào 2 interface tương ứng.

`KhoYeuCauPage.tsx`:
- cột **Bộ phận** hiện thêm tên công đoạn khi có (`san_xuat_cong_doan_ten`);
- cột **Cần lúc** ưu tiên `can_luc` (giờ) rồi mới tới `ngay_can` (ngày);
- ô số lượng của dòng: khi `sl_chot_thuc_xuat != null` hiện **"thực xuất 70 / yêu cầu 100"** và
  trạng thái Hoàn tất — **không** hiện "còn thiếu 30";
- **không** hiện `ly_do_chenh_lech` ở đâu cả (kho không xử lý lý do lệch kế hoạch);
- **không** thêm nút duyệt, không thêm "Đã soạn xong";
- tự nạp lại khi nhận `stock_request_pending_changed` (đã có sẵn, kiểm là nó gọi refetch cả danh
  sách chứ không chỉ badge).

- [ ] **Step 5: Kiểm**

```bash
cd backend && python -m pytest tests/test_kho_yeu_cau.py tests/test_kho_dieu_chinh_xuat.py -q
cd ../frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/schemas/stock.py backend/app/services/stock_request_service.py frontend/src/api/client.ts frontend/src/pages/KhoYeuCauPage.tsx
git commit -m "Kho: hộp yêu cầu hiện tổ/công đoạn/giờ cần và thực xuất đã chốt"
```

---

### Task 9: Khối Vật tư trong drawer công đoạn — HAI LƯỢT

**Files:**
- Modify: `frontend/src/api/client.ts`, `frontend/src/pages/ThsxExecPanels.tsx`, `frontend/src/components/AppShell.tsx`

**Interfaces:**
- Consumes: `chiTiet.vat_tu_cap` (Task 7), 2 route (Task 6).
- Produces: `api.sanXuat.deNghiVatTu(token, congViecId, body)`, `api.sanXuat.suaDeNghiVatTu(token, congViecId, deNghiId, body)`.

- [ ] **Step 1: Lượt THIẾT KẾ (agent riêng, chưa viết code sản phẩm)**

Dispatch một agent thiết kế với nhiệm vụ: đọc `VatTuSection` hiện tại
(`frontend/src/pages/ThsxExecPanels.tsx:767–800`) và các class `thsx-psec`/`thsx-x-*` đang dùng,
rồi CHỐT trên giấy:
- bố cục bảng 6 cột `Vật tư | Kế hoạch | Đã yêu cầu | Kho thực xuất | Chênh lệch | Lý do`;
- dải lịch sử các lần (mã kho · giờ cần · người tạo/sửa · trạng thái kho);
- 4 trạng thái nút: `Yêu cầu cấp vật tư` · `Sửa đề nghị` · `Yêu cầu bổ sung` · `Xác nhận nhận`;
- form trong drawer: điền sẵn kế hoạch + `du_kien_bat_dau`, sửa được giờ cần, tăng/giảm/về 0,
  thêm mặt hàng bằng `MaterialCombobox` (đã có ở `frontend/src/components/MaterialCombobox.tsx`),
  ô lý do chỉ hiện khi dòng lần đầu lệch, luôn hiện + bắt buộc với dòng bổ sung khác 0.
Đầu ra là mô tả bố cục + tên class, **không** phải code sản phẩm.

- [ ] **Step 2: Lượt CÀI ĐẶT (agent khác)**

Thêm types + 2 hàm API vào `client.ts` (khuôn `authed<T>` copy từ hàm `sanXuat` cạnh đó), rồi dựng
khối theo đúng bố cục đã chốt. Ba luật không được quên:

```tsx
// Khối Vật tư LUÔN hiện — kể cả chưa có phiếu nào. Bản cũ `if (vt.length === 0) return null;`
// khiến tổ trưởng không có cửa nào để bắt đầu xin vật tư (spec §7).
```

```tsx
// FE cảnh báo SỚM, BE quyết ĐÚNG/SAI. Không tự chặn nút khi thấy thiếu lý do — quy đổi đơn vị
// xảy ra ở BE, FE đoán "lệch" bằng số chưa quy đổi sẽ chặn nhầm những dòng thật ra khớp.
```

```tsx
// Vật tư KHÔNG BAO GIỜ chặn bắt đầu/kết thúc công đoạn (spec §8). Đừng gài `disabled` của nút
// Bắt đầu/Kết thúc vào trạng thái vật tư.
```

- [ ] **Step 3: Sự kiện SSE**

Trong `client.ts`, thêm vào union:

```typescript
  | { type: "san_xuat_vat_tu_de_nghi_changed"; cong_viec_id: number }
```

Trong `AppShell.tsx`, nhận sự kiện đó và refetch drawer đang mở nếu trùng `cong_viec_id`. Gate
toast theo quyền đọc `san_xuat` giống `san_xuat_nhom_dong` (`AppShell.tsx:733`). **Không** thêm
trung tâm thông báo mới.

- [ ] **Step 4: Kiểm kiểu**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: `styleseed-design-review`** trên khối vừa dựng.

- [ ] **Step 6: Commit** *(chỉ khi được yêu cầu)*

```bash
git add frontend/src/api/client.ts frontend/src/pages/ThsxExecPanels.tsx frontend/src/components/AppShell.tsx
git commit -m "Thực hiện SX: khối Vật tư cấp trong drawer công đoạn + realtime"
```

---

### Task 10: Nghiệm thu bằng dev-browser (BẮT BUỘC)

**Files:** không sửa file nào.

- [ ] **Step 1: Restart uvicorn.** Xem log có dòng `0246_sx_vat_tu_de_nghi`.

- [ ] **Step 2: Đăng nhập** tài khoản **tổ trưởng thật** của tổ đang giữ công đoạn (không phải
admin, để chứng minh cổng quyền chạy đúng). Nếu chưa có, gán `head_user_id` cho tổ qua màn Nhân sự
bằng chuột.

- [ ] **Step 3: Luồng 1 — xin đúng kế hoạch**

Mở drawer công đoạn → khối Vật tư hiện sẵn kế hoạch → bấm **Yêu cầu cấp vật tư** → giữ nguyên số →
gửi. Kiểm: mã `DNX…` hiện trong lịch sử; sang màn Kho (tab khác) thấy yêu cầu mới **tự nhảy** không
cần F5, có tên tổ + tên công đoạn + giờ cần.

- [ ] **Step 4: Luồng 2 — sửa trước khi kho lập phiếu**

Quay lại drawer → **Sửa đề nghị** → tăng một dòng, gõ lý do → lưu. Kiểm: bên kho **cùng mã DNX đó**
đổi số, không đẻ mã mới.

- [ ] **Step 5: Luồng 3 — sửa hết về 0**

Sửa mọi dòng về 0 → lưu. Kiểm: yêu cầu kho chuyển **Đã hủy** với ghi chú "Tổ xác nhận không cần
cấp", mã giữ nguyên. Rồi nhập lại số dương → **cùng mã đó** sống lại ở Đã duyệt.

- [ ] **Step 6: Luồng 4 — khoá + bổ sung**

Sang kho lập phiếu xuất (bằng chuột) → quay lại drawer: nút đổi thành **Yêu cầu bổ sung**, không
còn **Sửa đề nghị**. Bấm bổ sung, xin thêm 1 dòng kèm lý do → lần 2 xuất hiện trong lịch sử, tổng
ở bảng đối chiếu **cộng dồn** chứ không ghi đè.

- [ ] **Step 7: Luồng 5 — điều chỉnh thực xuất**

Kho ghi sổ phiếu xuất 100, rồi bấm **Điều chỉnh** còn 70. Kiểm:
- màn kho hiện **"thực xuất 70 / yêu cầu 100"**, trạng thái **Hoàn tất** (KHÔNG phải "còn thiếu 30");
- drawer công đoạn: cột **Kho thực xuất** = 70, **Chênh lệch** yêu-cầu↔thực-tế = −30.

- [ ] **Step 8: Luồng 6 — quyền**

Đăng nhập bằng người **lập kế hoạch** (có `san_xuat:read`, không phải tổ trưởng): mở cùng drawer →
**không** thấy nút gửi/sửa; nếu gọi thẳng API thì 403. Đăng nhập tổ trưởng **tổ khác**: cũng bị chặn.

- [ ] **Step 9: Luồng 7 — không chặn sản xuất**

Với công đoạn CHƯA xin vật tư lần nào: bấm **Bắt đầu** rồi **Kết thúc** — cả hai phải chạy bình thường.

- [ ] **Step 10: Báo cáo** — liệt kê CỤ THỂ từng bước đã bấm gì / gõ gì / thấy gì. Có đoạn nào
tắt qua API thay vì UI thì **nói rõ ngay**, đừng đợi hỏi.

---

## Self-Review

**1. Spec coverage**

| Mục spec | Task |
| --- | --- |
| §2.1 bảng `san_xuat_vat_tu_de_nghi` + 2 UNIQUE | Task 1 (Step 3, test Step 1) |
| §2.2 bảng dòng + UNIQUE + lưu dòng 0 + ngoài-kế-hoạch = 0 | Task 1 (Step 3), Task 3 (Step 4 `_chuan_hoa`) |
| §2.3 `sl_chot_thuc_xuat` + bảng 2 tình huống | Task 1 (Step 4, 5), Task 5 |
| §2 migration `0246` + DB_SCHEMA + hàng cũ NULL | Task 1 (Step 5, 6) |
| §3 `nhu_cau_cua_cong_viec`, không `_gom_nhu_cau` trực tiếp, không `vat_tu_json`, giấy ở bước đầu, bài ghép, gộp sau quy đổi, hai thang đơn vị | Task 2 |
| §3 BE luôn quy đổi lại | Task 3 (Step 4 `_chuan_hoa` gọi `ve_don_vi_goc`) |
| §4 năm ca luật lý do | Task 3 (Step 4 `can_ly_do`), test Step 1 |
| §5.1 tám bước tạo | Task 3 (Step 4 `tao`) |
| §5.2 đồng bộ trước phiếu, không dùng `update()` | Task 4 (Step 3 `dong_bo_tu_san_xuat`) |
| §5.3 về 0 → cancelled giữ mã; nhập lại → khôi phục | Task 4 (Step 3, 4), test Step 1 |
| §5.4 khoá khi có phiếu, kiểm trong transaction, lần bổ sung, tối đa 1 lần sửa được, cộng dồn | Task 3 (`tao`), Task 4 (`sua`), Task 7 (`co_the_tao_bo_sung`) |
| §5.5 `dieu_chinh_xuat` ghi chốt = tổng thực xuất hiện tại | Task 5 |
| §6 hai route, `de_nghi_id` là id SX, gác `assign_work` + tổ trưởng, không đòi `kho:request` | Task 6 |
| §6 `vat_tu_cap` 5 khoá + dòng đối chiếu đủ trường | Task 7 |
| §6 thay `voucher_xuat_cua_lsx`, đường lùi có đánh dấu, bài ghép không lùi | Task 7 (Step 3) |
| §6 mở rộng API kho 5 field | Task 8 |
| §7 FE drawer, 4 trạng thái nút, form, khối luôn hiện | Task 9 |
| §7 `KhoYeuCauPage` | Task 8 (Step 4) |
| §7 realtime 2 sự kiện | Task 4 (Step 4 bắn), Task 9 (Step 3 nhận) |
| §7 UI hai lượt + styleseed | Task 9 (Step 1, 2, 5) |
| §8 không chặn bắt đầu/kết thúc | Task 9 (Step 2 chú thích), Task 10 (Step 9 kiểm) |

**2. Placeholder scan** — các `...` còn lại đều là **chữ ký fixture kho/HTTP chưa xác định**
(Task 5 Step 1, Task 6 Step 1, Task 7 Step 1, Task 8 Step 1) và mỗi chỗ đều kèm lệnh tìm fixture
đang có. Đây là chỗ plan CỐ Ý không đoán: dựng fixture sai tên còn tệ hơn để trống, vì nó chạy
được và đo nhầm thứ. Không có "TODO" / "xử lý lỗi phù hợp" / "tương tự Task N" ở đâu.

**3. Type consistency**
- `nhu_cau_cua_cong_viec(cv) -> list[dict]` với đúng 7 khoá `hang_loai/hang_id/ten/dvt/sl/dvt_goc/sl_goc`:
  định nghĩa Task 2, dùng Task 3 (`_chuan_hoa`), Task 7 (`_vat_tu_cap`).
- `ve_don_vi_goc(hang_loai, hang_id, dvt, sl) -> (sl_goc, dvt_goc)`: khai Task 2 (ghi chú Step 3),
  dùng Task 3 Step 4.
- `tao(db, *, user, cong_viec_id, can_luc, lines)` và
  `sua(db, *, user, cong_viec_id, de_nghi_id, can_luc, lines)`: khớp giữa Task 3/4 (định nghĩa),
  Task 6 (router), test.
- `VatTuDeNghiError` (400) vs `PermissionError` (403) vs `ValueError` (404): thống nhất Task 3, 4, 6.
- `co_voucher(stock_request_id)` (repo SX) và `_co_voucher(req_id)` (StockRequestService) cùng
  ngữ nghĩa "bất kỳ phiếu nào, kể cả nháp/huỷ" — Task 3 Step 3 và Task 4 Step 3.
- `muc_tieu_hieu_luc` / `con_lai` là staticmethod của `StockRequestService`, dùng ở
  `refresh_fulfillment` (Task 5 Step 4) và chỗ dựng `sl_con_lai` (Task 8 Step 3) — MỘT đường tính.
- `vat_tu_cap` 6 khoá (`ke_hoach`, `cac_de_nghi`, `doi_chieu`, `de_nghi_co_the_sua_id`,
  `co_the_tao_bo_sung`, `du_lieu_cu`): dict Task 7 Step 4 ≡ `VatTuCapOut` Task 7 Step 5 ≡ TS Task 9.
  *(Spec §6 kể 5 khoá; `du_lieu_cu` là khoá thứ 6, sinh ra từ yêu cầu "đánh dấu dữ liệu cũ" cũng ở
  §6 — không phải khoá tự nghĩ thêm.)*

**Bẫy đã cắm biển trong plan:** `_gate_to_truong` tái dùng chứ không viết lại (Task 3);
`bo_phan_id` phải khai tay vì mặc định là `user.department_id` (Task 3 Step 4);
`WorkItemChiTietOut` có `response_model` nên field mới phải khai schema (Task 7 Step 5);
kiểm khoá phải ở TRONG transaction (Task 4 Step 4).

## Scope Check

Plan này là MỘT hệ thống hoàn chỉnh: xong Task 1–10 là tổ trưởng xin được vật tư, kho cấp được,
hai bên đối chiếu được. Nó **không** lấn sang bàn giao / KCS / ghi nhận lỗi / chia sản lượng
(spec §8) — mấy chuyện đó nằm ở
`docs/superpowers/plans/2026-08-31-thuc-te-phan-hoi-ke-hoach.md` và
`docs/superpowers/plans/2026-08-31-tach-lan-chay-cong-doan.md`, chạy độc lập được với plan này.

Có thể dừng sau **Task 8** nếu cần bàn giao sớm phần BE + màn kho: khi đó tổ chưa có UI để bấm,
nhưng không có gì dở dang trong DB.
