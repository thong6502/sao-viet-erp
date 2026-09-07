# Module Quản lý Tài sản cố định & Công cụ dụng cụ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng sổ tài sản cố định + công cụ dụng cụ cho kế toán: ghi tăng, tính khấu hao/phân bổ theo tháng có chốt kỳ, ba chứng từ biến động, kiểm kê tối giản, báo cáo xuất Excel.

**Architecture:** Theo tầng chuẩn của repo `routers → services → repositories → DB`. Engine khấu hao là hàm thuần trong `services/tai_san/khau_hao.py` (không đụng DB, test bằng số học). Mọi tài sản nằm trên MỘT bảng `tai_san` phân biệt bằng cột `loai` (`tscd`/`ccdc`); MỘT bảng `tai_san_bien_dong` gánh cả ba nghiệp vụ biến động thay vì ba bảng. Không có danh mục nhóm tài sản, không có ô tài khoản kế toán — chỉ ô ghi chú chữ tự do.

**Tech Stack:** FastAPI · SQLAlchemy 2 (Mapped/mapped_column) · Pydantic v2 · pytest · React + TypeScript (Vite) · openpyxl (xuất Excel, theo `services/bao_cao_cong_no_excel.py`).

**Spec:** `docs/superpowers/specs/2026-09-07-quan-ly-tai-san-ccdc-design.md`

## Global Constraints

- **KHÔNG có Alembic.** Bảng MỚI thì `create_all` tự dựng. Migration trong `backend/app/db_migrations.py` chỉ dùng để cấp quyền cho vai đã có trên DB live. Số tiếp theo: **0277** (mới nhất là `0276_cong_thuc_gio_dau_viec`).
- **Cột Boolean:** `server_default` phải là `false`/`true` (Python bool), KHÔNG phải `"0"`/`"1"` — chuỗi vỡ khi Postgres `create_all` trên DB trắng.
- **Tiền dùng `BigInteger`** (nguyên giá máy in tràn int32 — đã vỡ thật một lần trên Postgres).
- **`docs/DB_SCHEMA.md` có guard test** (`backend/tests/test_schema_documented.py`): mọi bảng/cột mới phải được ghi vào đó trong CÙNG task, không thì test đỏ.
- **Phân trang + lọc phải ở SERVER**, không kéo cả bảng về rồi cắt trong JS.
- **KHÔNG chạy `./init.ps1`.** Verify bằng `pytest` nhắm đúng file test, và `npx tsc --noEmit` cho frontend. Chạy cả bộ test phải hỏi trước.
- **Sửa route/schema backend → RESTART uvicorn** (không hot-reload đáng tin ở máy này).
- **Commit message tiếng Việt KHÔNG DẤU** (thuật ngữ kỹ thuật giữ tiếng Anh), một commit mỗi task.
- **Tên nghiệp vụ tiếng Việt không dấu** cho bảng/cột/field mới (`tai_san`, `nguyen_gia`, `ghi_chu_hach_toan`) — bám lối `kho_khoa_so`, `cong_no_khoa_so`.
- **Quyền:** module key `tai_san`, nhãn `"Tài sản & Công cụ dụng cụ"`. Dùng lại action có sẵn: `read` / `create` / `update` / `delete` / `export`, và **`close_book`** (`ACTION_CLOSE_BOOK`, cột `can_close_book` đã có trên `role_permissions`) cho chốt kỳ và mở kỳ. **Không thêm cột capability mới.**

---

## Mô hình tính khấu hao (đọc trước khi làm Task 2)

Bốn tình huống — nạp đầu kỳ, ghi tăng mới, nâng cấp, CCDC giảm một phần lô — đều quy về **một bộ ba trường trên `tai_san`**:

- `co_so_trich`: số tiền CÒN PHẢI TRÍCH tính từ mốc.
- `so_thang_con`: số tháng còn phải trích kể từ mốc.
- `moc_tu_ngay`: ngày bắt đầu áp dụng bộ cơ sở này.

Mức trích tròn tháng = `co_so_trich // so_thang_con`. Prorate theo ngày chỉ ở tháng chứa `moc_tu_ngay` (khi không phải ngày 1) và tháng ghi giảm. Luôn cap bởi `nguyen_gia - hao_mon_luy_ke`.

Bốn ca kiểm chứng (số dùng làm test thật):

| Ca | co_so_trich | so_thang_con | moc_tu_ngay | Mức trích |
|---|---|---|---|---|
| Komori ghi tăng 10/03/2026, NG 3.300.000.000, 120 tháng | 3.300.000.000 | 120 | 10/03/2026 | tháng 3: 19.516.129 (22/31 ngày) · từ tháng 4: 27.500.000 |
| Polar nạp đầu kỳ 01/01/2026, NG 450.000.000, đã trích 31 tháng / 116.250.000 | 333.750.000 | 89 | 01/01/2026 | 3.750.000 |
| Komori nâng cấp +180.000.000 từ 01/09/2026 (lũy kế 157.016.129) | 3.322.983.871 | 114 | 01/09/2026 | 29.148.981 |
| Lô 12 tấm cao su giảm 1 tấm từ 01/12/2026 (còn 20.900.000) | 20.900.000 | 19 | 01/12/2026 | 1.100.000 |

---

## File Structure

**Backend — tạo mới:**

- `backend/app/models/tai_san.py` — 6 bảng, một file (chúng đổi cùng nhau).
- `backend/app/schemas/tai_san.py` — Pydantic In/Out.
- `backend/app/repositories/tai_san_repo.py` — truy vấn DB.
- `backend/app/services/tai_san/__init__.py`
- `backend/app/services/tai_san/khau_hao.py` — engine thuần, không DB.
- `backend/app/services/tai_san/service.py` — nghiệp vụ sổ tài sản + biến động.
- `backend/app/services/tai_san/ky_service.py` — tính kỳ, chốt, mở.
- `backend/app/services/tai_san/kiem_ke_service.py` — đợt kiểm kê.
- `backend/app/services/tai_san/excel.py` — xuất bảng khấu hao.
- `backend/app/routers/tai_san.py` — toàn bộ endpoint.
- `backend/tests/test_tai_san_khau_hao.py` · `test_tai_san_service.py` · `test_tai_san_ky.py` · `test_tai_san_api.py`

**Backend — sửa:**

- `backend/app/models/__init__.py` — đăng ký model mới.
- `backend/app/main.py` — mount router.
- `backend/app/seed.py` — thêm `("tai_san", "Tài sản & Công cụ dụng cụ")` vào `MODULES` + cấp quyền cho vai "Kế toán".
- `backend/app/db_migrations.py` — migration `0277` cấp quyền trên DB live.
- `docs/DB_SCHEMA.md` — 6 bảng mới.

**Frontend — tạo mới:**

- `frontend/src/api/taiSan.ts`
- `frontend/src/pages/tai-san/index.ts` · `TaiSanPage.tsx` · `DanhSachView.tsx` · `GhiTangDialog.tsx` · `BienDongDialog.tsx` · `KhauHaoKyView.tsx` · `KiemKeView.tsx` · `tai-san.css`

**Frontend — sửa:**

- `frontend/src/components/Sidebar.tsx` — mục menu trong nhóm "Kế toán".
- `frontend/src/components/AppShell.tsx` — import + `case "tai-san"`.

---

### Task 1: Model + DB_SCHEMA + đăng ký

**Files:**
- Create: `backend/app/models/tai_san.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `docs/DB_SCHEMA.md`
- Test: `backend/tests/test_tai_san_model.py`

**Interfaces:**
- Produces: `TaiSan`, `TaiSanChiPhi`, `TaiSanBienDong`, `TaiSanKhauHao`, `TaiSanKy`, `TaiSanKiemKe`, `TaiSanKiemKeDong`; hằng `LOAI_TSCD="tscd"`, `LOAI_CCDC="ccdc"`, `BD_DIEU_CHUYEN="dieu_chuyen"`, `BD_NANG_CAP="nang_cap"`, `BD_GHI_GIAM="ghi_giam"`, `TT_DANG_DUNG="dang_dung"`, `TT_DA_GIAM="da_giam"`, `KY_MO="mo"`, `KY_DA_CHOT="da_chot"`.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_model.py
"""Model sổ tài sản — dựng bảng + ràng buộc. DB in-memory riêng, không đụng DB dev."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.models.tai_san import LOAI_TSCD, TT_DANG_DUNG, TaiSan, TaiSanKhauHao, TaiSanKy


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _ts(**over):
    base = dict(
        ma="TS-0001", ten="May in Komori 4 mau", loai=LOAI_TSCD,
        nguyen_gia=3_300_000_000, so_thang=120, ngay_su_dung=date(2026, 3, 10),
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
    )
    base.update(over)
    return TaiSan(**base)


def test_tao_tai_san_va_mac_dinh():
    db = _db()
    db.add(_ts())
    db.commit()
    t = db.query(TaiSan).one()
    assert t.trang_thai == TT_DANG_DUNG
    assert t.so_luong == 1
    assert t.hao_mon_luy_ke == 0
    assert t.ghi_chu_hach_toan is None


def test_ma_tai_san_khong_trung():
    db = _db()
    db.add(_ts())
    db.commit()
    db.add(_ts(ten="May khac"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_mot_ky_mot_dong_khau_hao_cho_moi_tai_san():
    db = _db()
    t = _ts()
    db.add(t)
    db.commit()
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=8,
                         muc_trich=27_500_000, luy_ke=157_016_129, con_lai=3_142_983_871))
    db.commit()
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=8,
                         muc_trich=1, luy_ke=1, con_lai=1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_ky_ke_toan_khong_trung_thang():
    db = _db()
    db.add(TaiSanKy(ky_nam=2026, ky_thang=8))
    db.commit()
    assert db.query(TaiSanKy).one().trang_thai == "mo"
    db.add(TaiSanKy(ky_nam=2026, ky_thang=8))
    with pytest.raises(IntegrityError):
        db.commit()
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_model.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.tai_san'`

- [ ] **Step 3: Viết model**

`backend/app/models/tai_san.py` — docstring tiếng Việt nêu rõ: một bảng cho cả TSCĐ lẫn CCDC, một bảng biến động cho ba nghiệp vụ, bộ ba `co_so_trich`/`so_thang_con`/`moc_tu_ngay` là đầu vào duy nhất của engine khấu hao.

```python
"""Sổ tài sản cố định & công cụ dụng cụ (kế toán).

MỘT bảng `tai_san` cho cả TSCĐ lẫn CCDC — phân biệt bằng `loai`. Không có danh mục nhóm tài
sản: số tháng khấu hao kế toán gõ thẳng vào phiếu (chủ chốt 07/09/2026 — danh mục nhóm chỉ
tiết kiệm một ô mỗi lần ghi tăng, đổi lại đẻ thêm một màn để sai).

KHÔNG có ô tài khoản kế toán. `ghi_chu_hach_toan` là chữ TỰ DO, module không hiểu nội dung,
chỉ in kèm ra bảng khấu hao cho kế toán nhập sang phần mềm kế toán bên ngoài.

Ba trường `co_so_trich` / `so_thang_con` / `moc_tu_ngay` là ĐẦU VÀO DUY NHẤT của engine khấu
hao — nạp đầu kỳ, ghi tăng, nâng cấp và CCDC giảm một phần lô đều quy về bộ ba này, nên engine
không cần biết tài sản đến từ đường nào.

Bảng MỚI → `create_all` tự dựng; migration 0277 chỉ cấp quyền cho vai đã có trên DB live.
"""
```

Cấu trúc cột (mọi cột tiền là `BigInteger`):

- `tai_san`: `id` PK · `ma` String(32) U IX · `ten` String(255) · `loai` String(8) IX · `so_luong` Integer default 1 · `don_gia` BigInteger nullable · `nguyen_gia` BigInteger · `so_thang` Integer · `ngay_su_dung` Date · `co_so_trich` BigInteger · `so_thang_con` Integer · `moc_tu_ngay` Date · `hao_mon_luy_ke` BigInteger default 0 · `nguon_vao` String(8) default `"ghi_tang"` · `hao_mon_dau_ky` BigInteger default 0 · `thang_da_trich_dau_ky` Integer default 0 · `bo_phan_id` FK `departments.id` ondelete SET NULL nullable IX · `nguoi_quan_ly` String(255) nullable · `vi_tri` String(255) nullable · `so_hoa_don` String(64) nullable · `nha_cung_cap` String(255) nullable · `ghi_chu_hach_toan` Text nullable · `ghi_chu` Text nullable · `trang_thai` String(12) default `"dang_dung"` IX · `ngay_giam` Date nullable · `created_by_user_id` FK `users.id` SET NULL nullable · `created_at` · `updated_at`.
- `tai_san_chi_phi`: `id` PK · `tai_san_id` FK CASCADE IX · `dien_giai` String(255) · `so_tien` BigInteger.
- `tai_san_bien_dong`: `id` PK · `tai_san_id` FK RESTRICT IX · `loai` String(16) IX · `ngay` Date IX · `so_tien` BigInteger nullable · `bo_phan_moi_id` FK `departments.id` SET NULL nullable · `so_thang_con_lai` Integer nullable · `so_luong_giam` Integer nullable · `ly_do` String(255) nullable · `ghi_chu_hach_toan` Text nullable · `nguoi_tao_id` FK `users.id` SET NULL nullable · `created_at`.
- `tai_san_khau_hao`: `id` PK · `tai_san_id` FK CASCADE IX · `ky_nam` Integer · `ky_thang` Integer · `muc_trich` BigInteger · `luy_ke` BigInteger · `con_lai` BigInteger · `bo_phan_id` FK SET NULL nullable · `ghi_chu_hach_toan` Text nullable · `UniqueConstraint("tai_san_id","ky_nam","ky_thang", name="uq_tai_san_khau_hao_ky")`.
- `tai_san_ky`: `id` PK · `ky_nam` Integer · `ky_thang` Integer · `trang_thai` String(8) default `"mo"` · `ngay_chot` DateTime(timezone=True) nullable · `nguoi_chot_id` FK `users.id` SET NULL nullable · `UniqueConstraint("ky_nam","ky_thang", name="uq_tai_san_ky")`.
- `tai_san_kiem_ke`: `id` PK · `ma` String(32) U · `ngay` Date · `bo_phan_id` FK SET NULL nullable · `trang_thai` String(12) default `"dang_kiem"` · `ghi_chu` Text nullable · `nguoi_tao_id` FK SET NULL nullable · `created_at`.
- `tai_san_kiem_ke_dong`: `id` PK · `dot_id` FK CASCADE IX · `tai_san_id` FK SET NULL nullable · `ket_qua` String(12) nullable · `ten_phat_hien` String(255) nullable · `tinh_trang` String(255) nullable · `ghi_chu` Text nullable.

- [ ] **Step 4: Đăng ký model**

Thêm `from .tai_san import *  # noqa` (hoặc import đích danh, theo đúng lối đang dùng) vào `backend/app/models/__init__.py`.

- [ ] **Step 5: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_model.py -q`
Expected: 4 passed

- [ ] **Step 6: Ghi 6 bảng vào DB_SCHEMA.md**

Mỗi bảng một mục `### \`ten_bang\`` + **Purpose** một dòng + bảng cột (Column / Type / Key / Null / Default / Meaning) + **Keys & indexes** + **Relationships**, đúng quy ước file đang dùng.

- [ ] **Step 7: Chạy guard schema**

Run: `cd backend && python -m pytest tests/test_schema_documented.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/tai_san.py backend/app/models/__init__.py backend/tests/test_tai_san_model.py docs/DB_SCHEMA.md
git commit -m "Model so tai san co dinh va cong cu dung cu (6 bang)"
```

---

### Task 2: Engine khấu hao (hàm thuần)

**Files:**
- Create: `backend/app/services/tai_san/__init__.py`, `backend/app/services/tai_san/khau_hao.py`
- Test: `backend/tests/test_tai_san_khau_hao.py`

**Interfaces:**
- Produces:
  - `muc_trich_thang(co_so_trich: int, so_thang_con: int) -> int`
  - `trich_mot_ky(*, co_so_trich: int, so_thang_con: int, moc_tu_ngay: date, nguyen_gia: int, luy_ke: int, nam: int, thang: int, ngay_giam: date | None = None) -> int`
  - `lich_du_kien(*, co_so_trich: int, so_thang_con: int, moc_tu_ngay: date, nguyen_gia: int, luy_ke: int, so_ky_toi_da: int = 400) -> list[DongDuKien]` với `DongDuKien(nam, thang, muc_trich, luy_ke, con_lai)` là dataclass frozen.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_khau_hao.py
"""Engine khấu hao — hàm thuần, không DB. Số trong test là 4 ca thật ở plan/spec."""
from datetime import date

from app.services.tai_san.khau_hao import lich_du_kien, muc_trich_thang, trich_mot_ky


def test_muc_trich_tron_thang():
    assert muc_trich_thang(3_300_000_000, 120) == 27_500_000


def test_thang_dau_tinh_theo_ngay():
    """Komori dùng từ 10/03/2026: 22/31 ngày của tháng 3."""
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=0, nam=2026, thang=3,
    ) == 19_516_129


def test_thang_tron_sau_thang_dau():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=19_516_129, nam=2026, thang=4,
    ) == 27_500_000


def test_chua_toi_moc_thi_khong_trich():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=0, nam=2026, thang=2,
    ) == 0


def test_nap_dau_ky_polar():
    """450tr / 120 tháng, đã trích 31 tháng ⇒ 333.750.000 chia 89 tháng."""
    assert trich_mot_ky(
        co_so_trich=333_750_000, so_thang_con=89, moc_tu_ngay=date(2026, 1, 1),
        nguyen_gia=450_000_000, luy_ke=116_250_000, nam=2026, thang=8,
    ) == 3_750_000


def test_sau_nang_cap():
    """Komori +180tr từ 01/09/2026: (3.480.000.000 − 157.016.129) / 114 tháng."""
    assert trich_mot_ky(
        co_so_trich=3_322_983_871, so_thang_con=114, moc_tu_ngay=date(2026, 9, 1),
        nguyen_gia=3_480_000_000, luy_ke=157_016_129, nam=2026, thang=9,
    ) == 29_148_981


def test_ccdc_giam_mot_phan_lo():
    """Lô 12 tấm cao su bỏ 1 tấm: 20.900.000 chia 19 tháng còn lại."""
    assert trich_mot_ky(
        co_so_trich=20_900_000, so_thang_con=19, moc_tu_ngay=date(2026, 12, 1),
        nguyen_gia=28_800_000, luy_ke=6_000_000, nam=2026, thang=12,
    ) == 1_100_000


def test_thang_ghi_giam_tinh_toi_ngay_giam():
    """Ngừng trích từ ngày giảm: 15/30 ngày của tháng 9."""
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=157_016_129, nam=2026, thang=9,
        ngay_giam=date(2026, 9, 15),
    ) == 13_750_000


def test_sau_ngay_giam_khong_trich_nua():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=170_766_129, nam=2026, thang=10,
        ngay_giam=date(2026, 9, 15),
    ) == 0


def test_ky_cuoi_khong_trich_qua_nguyen_gia():
    """Còn lại 1.000.000 mà mức tháng 27.500.000 ⇒ chỉ trích nốt 1.000.000."""
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=3_299_000_000, nam=2036, thang=3,
    ) == 1_000_000


def test_het_khau_hao_thi_thoi():
    assert trich_mot_ky(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=3_300_000_000, nam=2036, thang=4,
    ) == 0


def test_lich_du_kien_cong_du_bang_nguyen_gia():
    """Tổng mọi kỳ = nguyên giá — phần lẻ do làm tròn dồn vào kỳ cuối."""
    lich = lich_du_kien(
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
        nguyen_gia=3_300_000_000, luy_ke=0,
    )
    assert lich[0].nam == 2026 and lich[0].thang == 3
    assert lich[0].muc_trich == 19_516_129
    assert sum(d.muc_trich for d in lich) == 3_300_000_000
    assert lich[-1].con_lai == 0
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_khau_hao.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.tai_san'`

- [ ] **Step 3: Viết engine**

```python
# backend/app/services/tai_san/khau_hao.py
"""Engine khấu hao / phân bổ — HÀM THUẦN, không chạm DB.

Bốn đường vào sổ (nạp đầu kỳ · ghi tăng · nâng cấp · CCDC giảm một phần lô) đều quy về bộ ba
`co_so_trich` / `so_thang_con` / `moc_tu_ngay`, nên engine chỉ có một luật:

    mức tròn tháng = co_so_trich // so_thang_con

Prorate theo NGÀY chỉ ở hai chỗ: tháng chứa `moc_tu_ngay` (khi mốc không rơi vào ngày 1) và
tháng ghi giảm. Luôn cap bởi `nguyen_gia - luy_ke` nên kỳ cuối tự trích nốt phần lẻ do làm
tròn — không cần luật riêng cho kỳ cuối.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DongDuKien:
    nam: int
    thang: int
    muc_trich: int
    luy_ke: int
    con_lai: int


def _so_ngay(nam: int, thang: int) -> int:
    return calendar.monthrange(nam, thang)[1]


def _sang_thang(nam: int, thang: int) -> tuple[int, int]:
    return (nam + 1, 1) if thang == 12 else (nam, thang + 1)


def muc_trich_thang(co_so_trich: int, so_thang_con: int) -> int:
    """Mức trích tròn một tháng, làm tròn XUỐNG đồng."""
    if so_thang_con <= 0:
        raise ValueError("so_thang_con phải > 0")
    return int(co_so_trich) // int(so_thang_con)


def trich_mot_ky(
    *,
    co_so_trich: int,
    so_thang_con: int,
    moc_tu_ngay: date,
    nguyen_gia: int,
    luy_ke: int,
    nam: int,
    thang: int,
    ngay_giam: date | None = None,
) -> int:
    """Số tiền trích của ĐÚNG một kỳ (nam, thang). 0 nếu kỳ nằm ngoài đời tài sản."""
    con_lai = int(nguyen_gia) - int(luy_ke)
    if con_lai <= 0 or so_thang_con <= 0:
        return 0
    ngay_trong_thang = _so_ngay(nam, thang)
    dau_ky = date(nam, thang, 1)
    cuoi_ky = date(nam, thang, ngay_trong_thang)
    if moc_tu_ngay > cuoi_ky:
        return 0
    if ngay_giam is not None and ngay_giam < dau_ky:
        return 0
    tu = max(moc_tu_ngay, dau_ky)
    den = min(ngay_giam, cuoi_ky) if ngay_giam is not None else cuoi_ky
    if den < tu:
        return 0
    muc = muc_trich_thang(co_so_trich, so_thang_con)
    so_ngay_dung = (den - tu).days + 1
    if so_ngay_dung < ngay_trong_thang:
        muc = muc * so_ngay_dung // ngay_trong_thang
    return min(muc, con_lai)


def lich_du_kien(
    *,
    co_so_trich: int,
    so_thang_con: int,
    moc_tu_ngay: date,
    nguyen_gia: int,
    luy_ke: int,
    so_ky_toi_da: int = 400,
) -> list[DongDuKien]:
    """Bảng khấu hao dự kiến từ mốc tới khi hết giá trị — hiện ngay sau khi ghi tăng."""
    ra: list[DongDuKien] = []
    nam, thang = moc_tu_ngay.year, moc_tu_ngay.month
    dang_luy_ke = int(luy_ke)
    for _ in range(so_ky_toi_da):
        if dang_luy_ke >= nguyen_gia:
            break
        muc = trich_mot_ky(
            co_so_trich=co_so_trich, so_thang_con=so_thang_con, moc_tu_ngay=moc_tu_ngay,
            nguyen_gia=nguyen_gia, luy_ke=dang_luy_ke, nam=nam, thang=thang,
        )
        if muc > 0:
            dang_luy_ke += muc
            ra.append(DongDuKien(nam, thang, muc, dang_luy_ke, int(nguyen_gia) - dang_luy_ke))
        nam, thang = _sang_thang(nam, thang)
    return ra
```

`backend/app/services/tai_san/__init__.py` để rỗng (chỉ đánh dấu package).

- [ ] **Step 4: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_khau_hao.py -q`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tai_san/ backend/tests/test_tai_san_khau_hao.py
git commit -m "Engine khau hao tai san: mot luat co_so_trich chia so_thang_con"
```

---

### Task 3: Repository + service sổ tài sản (ghi tăng, nạp đầu kỳ, sửa, xoá)

**Files:**
- Create: `backend/app/repositories/tai_san_repo.py`, `backend/app/services/tai_san/service.py`
- Test: `backend/tests/test_tai_san_service.py`

**Interfaces:**
- Consumes: model Task 1, `lich_du_kien` Task 2.
- Produces:
  - `TaiSanRepository(db)` với `tao(**field) -> TaiSan`, `lay(id) -> TaiSan | None`, `tim_theo_ma(ma) -> TaiSan | None`, `danh_sach(*, q=None, loai=None, bo_phan_id=None, trang_thai=None, offset=0, limit=50) -> tuple[list[TaiSan], int]`, `co_ky_chot_lien_quan(tai_san_id) -> bool`, `xoa(ts)`.
  - `TaiSanService(repo)` với `ghi_tang(payload: dict, *, user_id: int | None = None) -> TaiSan`, `nap_dau_ky(payload, *, user_id=None) -> TaiSan`, `sua(id, payload) -> TaiSan`, `xoa(id) -> None`, `du_kien(id) -> list[DongDuKien]`, `sinh_ma(loai) -> str`.
  - Lỗi: `TaiSanNotFound`, `TaiSanTrung`, `TaiSanValidationError`, `TaiSanDaChotKy`.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_service.py
"""Sổ tài sản — ghi tăng, nạp đầu kỳ, chặn sửa sau khi kỳ đã chốt."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.tai_san import KY_DA_CHOT, LOAI_CCDC, LOAI_TSCD, TaiSanKhauHao, TaiSanKy
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.service import (
    TaiSanDaChotKy,
    TaiSanService,
    TaiSanTrung,
    TaiSanValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db))


def _komori(**over):
    base = dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[
            {"dien_giai": "Gia mua", "so_tien": 3_200_000_000},
            {"dien_giai": "Van chuyen", "so_tien": 40_000_000},
            {"dien_giai": "Lap dat chay thu", "so_tien": 60_000_000},
        ],
        ghi_chu_hach_toan="211 / 6274 - to In",
    )
    base.update(over)
    return base


def test_ghi_tang_cong_nguyen_gia_tu_cac_dong_chi_phi():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    assert t.nguyen_gia == 3_300_000_000
    assert t.co_so_trich == 3_300_000_000
    assert t.so_thang_con == 120
    assert t.moc_tu_ngay == date(2026, 3, 10)
    assert t.hao_mon_luy_ke == 0
    assert t.ma.startswith("TS-")
    assert t.ghi_chu_hach_toan == "211 / 6274 - to In"


def test_du_kien_hien_ngay_sau_ghi_tang():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    lich = svc.du_kien(t.id)
    assert lich[0].muc_trich == 19_516_129
    assert lich[1].muc_trich == 27_500_000
    assert sum(d.muc_trich for d in lich) == 3_300_000_000


def test_nap_dau_ky_tru_hao_mon_luy_ke():
    db, svc = _svc()
    t = svc.nap_dau_ky(dict(
        ten="May dao xen Polar", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2023, 6, 1), moc_tu_ngay=date(2026, 1, 1),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 450_000_000}],
        thang_da_trich_dau_ky=31, hao_mon_dau_ky=116_250_000,
    ))
    assert t.nguyen_gia == 450_000_000
    assert t.hao_mon_luy_ke == 116_250_000
    assert t.co_so_trich == 333_750_000
    assert t.so_thang_con == 89
    assert svc.du_kien(t.id)[0].muc_trich == 3_750_000


def test_ccdc_nhap_theo_lo():
    db, svc = _svc()
    t = svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))
    assert t.nguyen_gia == 28_800_000
    assert svc.du_kien(t.id)[0].muc_trich == 1_200_000


def test_ten_trung_ma_thi_bao_loi():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    with pytest.raises(TaiSanTrung):
        svc.ghi_tang(_komori(ma=t.ma))


def test_so_thang_phai_duong():
    db, svc = _svc()
    with pytest.raises(TaiSanValidationError):
        svc.ghi_tang(_komori(so_thang=0))


def test_nguyen_gia_phai_duong():
    db, svc = _svc()
    with pytest.raises(TaiSanValidationError):
        svc.ghi_tang(_komori(chi_phi=[]))


def test_chan_sua_o_anh_huong_so_khi_ky_da_chot():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    db.add(TaiSanKy(ky_nam=2026, ky_thang=3, trang_thai=KY_DA_CHOT))
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=3,
                         muc_trich=19_516_129, luy_ke=19_516_129, con_lai=3_280_483_871))
    db.commit()
    with pytest.raises(TaiSanDaChotKy):
        svc.sua(t.id, {"so_thang": 96})
    # ô mô tả vẫn sửa được
    t2 = svc.sua(t.id, {"vi_tri": "Xuong 2", "ghi_chu_hach_toan": "211 / 6274 - to Be"})
    assert t2.vi_tri == "Xuong 2"


def test_chan_xoa_khi_da_co_ky_chot():
    db, svc = _svc()
    t = svc.ghi_tang(_komori())
    db.add(TaiSanKy(ky_nam=2026, ky_thang=3, trang_thai=KY_DA_CHOT))
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=3,
                         muc_trich=19_516_129, luy_ke=19_516_129, con_lai=3_280_483_871))
    db.commit()
    with pytest.raises(TaiSanDaChotKy):
        svc.xoa(t.id)
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.tai_san_repo'`

- [ ] **Step 3: Viết repository**

`TaiSanRepository` chỉ chứa truy vấn: `danh_sach` lọc `q` (LIKE trên `ma`/`ten`), `loai`, `bo_phan_id`, `trang_thai`, trả `(rows, tong)` — **cắt trang bằng `.offset().limit()` ở SQL**, đếm bằng `select(func.count())`. `co_ky_chot_lien_quan(tai_san_id)` = tồn tại `TaiSanKhauHao` của tài sản đó ở kỳ mà `TaiSanKy.trang_thai == KY_DA_CHOT`.

- [ ] **Step 4: Viết service**

`TaiSanService`:
- `sinh_ma(loai)`: `TS-0001` cho `tscd`, `CC-0001` cho `ccdc` — số tăng dần theo `max` hiện có, khoá theo tiền tố.
- `ghi_tang`: nguyên giá = tổng `chi_phi` nếu có dòng, ngược lại `so_luong * don_gia`; validate `so_thang > 0`, `nguyen_gia > 0`, `ngay_su_dung` bắt buộc; đặt `co_so_trich = nguyen_gia`, `so_thang_con = so_thang`, `moc_tu_ngay = ngay_su_dung`, `nguon_vao = "ghi_tang"`.
- `nap_dau_ky`: thêm validate `0 <= hao_mon_dau_ky < nguyen_gia`, `0 <= thang_da_trich_dau_ky < so_thang`, `moc_tu_ngay` bắt buộc; đặt `hao_mon_luy_ke = hao_mon_dau_ky`, `co_so_trich = nguyen_gia - hao_mon_dau_ky`, `so_thang_con = so_thang - thang_da_trich_dau_ky`, `nguon_vao = "dau_ky"`.
- `sua`: nếu `co_ky_chot_lien_quan` thì chặn mọi field trong `O_ANH_HUONG_SO = {"nguyen_gia","so_thang","ngay_su_dung","co_so_trich","so_thang_con","moc_tu_ngay","so_luong","don_gia","hao_mon_dau_ky","thang_da_trich_dau_ky","chi_phi"}` (raise `TaiSanDaChotKy`), các ô còn lại vẫn cho sửa.
- `xoa`: chặn nếu `co_ky_chot_lien_quan`.
- `du_kien`: gọi `lich_du_kien` với bộ ba của tài sản.

- [ ] **Step 5: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_service.py -q`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/tai_san_repo.py backend/app/services/tai_san/service.py backend/tests/test_tai_san_service.py
git commit -m "Service so tai san: ghi tang, nap du dau ky, chan sua sau khi chot ky"
```

---

### Task 4: Kỳ khấu hao — tính, chốt, mở

**Files:**
- Create: `backend/app/services/tai_san/ky_service.py`
- Test: `backend/tests/test_tai_san_ky.py`

**Interfaces:**
- Consumes: `trich_mot_ky` (Task 2), `TaiSanRepository` (Task 3).
- Produces: `KyService(db)` với
  - `tinh(nam: int, thang: int) -> list[TaiSanKhauHao]` — tính và LƯU dòng khấu hao, ghi đè nếu kỳ chưa chốt.
  - `bang(nam, thang) -> list[dict]` — dòng kèm `ten`, `ma`, `bo_phan_ten`, `nguyen_gia`, `muc_trich`, `luy_ke`, `con_lai`, `ghi_chu_hach_toan`.
  - `chot(nam, thang, *, user_id=None) -> TaiSanKy`
  - `mo(nam, thang) -> TaiSanKy`
  - Lỗi: `KyDaChot`, `KyTruocChuaChot`, `KyKhongTonTai`.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_ky.py
"""Kỳ khấu hao: tính lại được khi chưa chốt, khoá cứng khi đã chốt."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.tai_san import KY_DA_CHOT, LOAI_TSCD
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.ky_service import KyDaChot, KyService, KyTruocChuaChot
from app.services.tai_san.service import TaiSanService


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db)), KyService(db)


def _komori(svc):
    return svc.ghi_tang(dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 3_300_000_000}],
    ))


def test_tinh_ky_dau_tien_theo_ngay():
    db, svc, ky = _moi_truong()
    _komori(svc)
    dong = ky.tinh(2026, 3)
    assert len(dong) == 1
    assert dong[0].muc_trich == 19_516_129
    assert dong[0].luy_ke == 19_516_129
    assert dong[0].con_lai == 3_280_483_871


def test_tinh_lai_ky_chua_chot_thi_ghi_de_khong_cong_don():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    dong = ky.tinh(2026, 3)
    assert len(dong) == 1
    assert dong[0].luy_ke == 19_516_129


def test_luy_ke_cong_don_qua_cac_ky():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    dong = ky.tinh(2026, 4)
    assert dong[0].muc_trich == 27_500_000
    assert dong[0].luy_ke == 47_016_129
    db.refresh(t)
    assert t.hao_mon_luy_ke == 47_016_129


def test_chot_roi_thi_khong_tinh_lai_duoc():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    with pytest.raises(KyDaChot):
        ky.tinh(2026, 3)


def test_chot_hai_lan_bi_chan():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    with pytest.raises(KyDaChot):
        ky.chot(2026, 3)


def test_khong_duoc_nhay_coc_khi_ky_truoc_con_mo():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.tinh(2026, 4)
    with pytest.raises(KyTruocChuaChot):
        ky.chot(2026, 4)


def test_mo_lai_ky_da_chot():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    k = ky.mo(2026, 3)
    assert k.trang_thai == "mo"
    assert ky.tinh(2026, 3)[0].muc_trich == 19_516_129


def test_bang_ky_co_cot_ghi_chu_hach_toan():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    svc.sua(t.id, {"ghi_chu_hach_toan": "211 / 6274 - to In"})
    ky.tinh(2026, 3)
    hang = ky.bang(2026, 3)[0]
    assert hang["ghi_chu_hach_toan"] == "211 / 6274 - to In"
    assert hang["ma"] == t.ma
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_ky.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.tai_san.ky_service'`

- [ ] **Step 3: Viết `KyService`**

- `tinh(nam, thang)`: nếu `TaiSanKy` của kỳ đó `da_chot` → `KyDaChot`. Xoá dòng `TaiSanKhauHao` cũ của đúng kỳ đó (ghi đè, không cộng dồn), duyệt mọi tài sản `dang_dung` **và** tài sản `da_giam` có `ngay_giam` rơi trong kỳ; gọi `trich_mot_ky` với `luy_ke` = `hao_mon_luy_ke` hiện tại; bỏ qua dòng mức trích 0; ghi `bo_phan_id` = bộ phận HIỆN TẠI của tài sản (điều chuyển giữa tháng ⇒ trọn tháng về bộ phận cuối kỳ) và `ghi_chu_hach_toan` chép từ tài sản. Tạo `TaiSanKy` trạng thái `mo` nếu chưa có. **Không** cập nhật `hao_mon_luy_ke` ở bước tính.
- `chot(nam, thang)`: chặn nếu đã chốt; chặn nếu tồn tại kỳ TRƯỚC có dòng khấu hao mà chưa `da_chot` (`KyTruocChuaChot`); cộng `muc_trich` của kỳ vào `hao_mon_luy_ke` của từng tài sản; đánh dấu `da_chot`, ghi `ngay_chot`, `nguoi_chot_id`.
- `mo(nam, thang)`: chặn nếu tồn tại kỳ SAU đã chốt; trừ ngược `muc_trich` khỏi `hao_mon_luy_ke`; đổi trạng thái về `mo`.

- [ ] **Step 4: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_ky.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tai_san/ky_service.py backend/tests/test_tai_san_ky.py
git commit -m "Ky khau hao tai san: tinh lai duoc khi chua chot, khoa cung sau khi chot"
```

---

### Task 5: Ba chứng từ biến động

**Files:**
- Modify: `backend/app/services/tai_san/service.py`
- Test: `backend/tests/test_tai_san_bien_dong.py`

**Interfaces:**
- Produces trên `TaiSanService`:
  - `dieu_chuyen(id, *, ngay: date, bo_phan_moi_id: int, ly_do: str | None = None, ghi_chu_hach_toan: str | None = None, user_id=None) -> TaiSanBienDong`
  - `nang_cap(id, *, ngay: date, so_tien: int, so_thang_con_lai: int, ly_do=None, ghi_chu_hach_toan=None, user_id=None) -> TaiSanBienDong`
  - `ghi_giam(id, *, ngay: date, ly_do: str, gia_ban: int | None = None, so_luong_giam: int | None = None, ghi_chu_hach_toan=None, user_id=None) -> TaiSanBienDong`
  - `TaiSanValidationError` cho tham số sai; `TaiSanDaChotKy` khi ngày chứng từ rơi vào kỳ đã chốt.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_bien_dong.py
"""Ba chứng từ biến động: điều chuyển · nâng cấp · ghi giảm (kể cả CCDC một phần lô)."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.tai_san import LOAI_CCDC, LOAI_TSCD, TT_DA_GIAM
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.ky_service import KyService
from app.services.tai_san.service import TaiSanDaChotKy, TaiSanService, TaiSanValidationError


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db)), KyService(db)


def _komori(svc):
    return svc.ghi_tang(dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 3_300_000_000}],
    ))


def test_dieu_chuyen_doi_bo_phan_khong_dung_toi_so():
    db, svc, ky = _moi_truong()
    to_be = Department(name="To Be")
    db.add(to_be)
    db.commit()
    t = _komori(svc)
    svc.dieu_chuyen(t.id, ngay=date(2026, 9, 15), bo_phan_moi_id=to_be.id, ly_do="Chuyen to")
    db.refresh(t)
    assert t.bo_phan_id == to_be.id
    assert t.nguyen_gia == 3_300_000_000
    assert t.co_so_trich == 3_300_000_000


def test_nang_cap_tinh_lai_muc_trich_tu_ky_sau():
    """Komori +180tr từ 01/09/2026, lũy kế 157.016.129 ⇒ 3.322.983.871 / 114 = 29.148.981."""
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    for nam, thang in [(2026, 3), (2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8)]:
        ky.tinh(nam, thang)
        ky.chot(nam, thang)
    db.refresh(t)
    assert t.hao_mon_luy_ke == 157_016_129

    svc.nang_cap(t.id, ngay=date(2026, 9, 1), so_tien=180_000_000, so_thang_con_lai=114)
    db.refresh(t)
    assert t.nguyen_gia == 3_480_000_000
    assert t.hao_mon_luy_ke == 157_016_129
    assert t.co_so_trich == 3_322_983_871
    assert t.so_thang_con == 114
    assert ky.tinh(2026, 9)[0].muc_trich == 29_148_981


def test_ghi_giam_ngung_trich_va_bao_chenh_lech():
    db, svc, ky = _moi_truong()
    t = svc.nap_dau_ky(dict(
        ten="May in 2 mau cu", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2016, 1, 1), moc_tu_ngay=date(2026, 1, 1),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 800_000_000}],
        thang_da_trich_dau_ky=93, hao_mon_dau_ky=620_000_000,
    ))
    bd = svc.ghi_giam(t.id, ngay=date(2026, 1, 1), ly_do="Nhuong ban", gia_ban=200_000_000)
    db.refresh(t)
    assert t.trang_thai == TT_DA_GIAM
    assert t.ngay_giam == date(2026, 1, 1)
    assert bd.so_tien == 200_000_000
    # giá trị còn lại 180.000.000 → chênh +20.000.000
    assert svc.chenh_lech_thanh_ly(t.id) == 20_000_000
    assert ky.tinh(2026, 2) == []


def test_ccdc_ghi_giam_mot_phan_lo():
    """12 tấm cao su, đã phân bổ 5 kỳ (6.000.000), bỏ 1 tấm từ 01/12/2026."""
    db, svc, ky = _moi_truong()
    t = svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))
    for thang in (7, 8, 9, 10, 11):
        ky.tinh(2026, thang)
        ky.chot(2026, thang)
    db.refresh(t)
    assert t.hao_mon_luy_ke == 6_000_000

    svc.ghi_giam(t.id, ngay=date(2026, 12, 1), ly_do="Rach 1 tam", so_luong_giam=1)
    db.refresh(t)
    assert t.so_luong == 11
    assert t.trang_thai == "dang_dung"      # lô còn sống
    assert t.co_so_trich == 20_900_000
    assert t.so_thang_con == 19
    assert ky.tinh(2026, 12)[0].muc_trich == 1_100_000


def test_chan_chung_tu_roi_vao_ky_da_chot():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    with pytest.raises(TaiSanDaChotKy):
        svc.nang_cap(t.id, ngay=date(2026, 3, 20), so_tien=10_000_000, so_thang_con_lai=100)


def test_nang_cap_so_thang_con_lai_phai_duong():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    with pytest.raises(TaiSanValidationError):
        svc.nang_cap(t.id, ngay=date(2026, 4, 1), so_tien=10_000_000, so_thang_con_lai=0)


def test_ghi_giam_so_luong_khong_vuot_ton():
    db, svc, ky = _moi_truong()
    t = svc.ghi_tang(dict(
        ten="Tam cao su offset", loai=LOAI_CCDC, so_luong=12, don_gia=2_400_000,
        so_thang=24, ngay_su_dung=date(2026, 7, 1),
    ))
    with pytest.raises(TaiSanValidationError):
        svc.ghi_giam(t.id, ngay=date(2026, 8, 1), ly_do="Mat", so_luong_giam=20)
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_bien_dong.py -q`
Expected: FAIL — `AttributeError: 'TaiSanService' object has no attribute 'dieu_chuyen'`

- [ ] **Step 3: Viết ba nghiệp vụ**

Luật chung: mọi chứng từ đều gọi `_chan_ky_da_chot(ngay)` trước (kỳ chứa `ngay` đã `da_chot` ⇒ `TaiSanDaChotKy`), và ghi một hàng `TaiSanBienDong`.

- `dieu_chuyen`: chỉ đổi `tai_san.bo_phan_id`. Không đụng số.
- `nang_cap`: validate `so_tien > 0`, `so_thang_con_lai > 0`; `nguyen_gia += so_tien`; giữ nguyên `hao_mon_luy_ke`; `co_so_trich = nguyen_gia_moi - hao_mon_luy_ke`; `so_thang_con = so_thang_con_lai`; `moc_tu_ngay = ngày đầu tháng của kỳ SAU ngày chứng từ` (chứng từ ngày 01 của tháng thì áp ngay tháng đó).
- `ghi_giam` không có `so_luong_giam` (hoặc giảm hết lô): `trang_thai = da_giam`, `ngay_giam = ngay`; `so_tien` lưu giá bán.
- `ghi_giam` có `so_luong_giam` với CCDC: validate `0 < so_luong_giam <= so_luong`; `gia_tri_con_lai = nguyen_gia - hao_mon_luy_ke`; `gia_tri_bo = gia_tri_con_lai * so_luong_giam // so_luong`; `so_luong -= so_luong_giam`; `co_so_trich = gia_tri_con_lai - gia_tri_bo`; `so_thang_con = so_thang - (số kỳ đã có dòng khấu hao)`; `moc_tu_ngay` = đầu tháng của kỳ chứa `ngay`; lô vẫn `dang_dung`.
- `chenh_lech_thanh_ly(id) -> int | None`: `gia_ban - (nguyen_gia - hao_mon_luy_ke)` của chứng từ ghi giảm mới nhất.

- [ ] **Step 4: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_bien_dong.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tai_san/service.py backend/tests/test_tai_san_bien_dong.py
git commit -m "Ba chung tu bien dong tai san: dieu chuyen, nang cap, ghi giam"
```

---

### Task 6: Schemas + Router + quyền + mount

**Files:**
- Create: `backend/app/schemas/tai_san.py`, `backend/app/routers/tai_san.py`
- Modify: `backend/app/main.py`, `backend/app/seed.py`, `backend/app/db_migrations.py`
- Test: `backend/tests/test_tai_san_api.py`

**Interfaces:**
- Consumes: `TaiSanService` (Task 3, 5), `KyService` (Task 4).
- Produces endpoint dưới prefix `/api/tai-san`, `MODULE = "tai_san"`:
  - `GET /` (read) — `?q=&loai=&bo_phan_id=&trang_thai=&offset=&limit=` → `TaiSanListOut{items, total}`
  - `POST /` (create) — body `TaiSanIn` có `nguon_vao`
  - `GET /{id}` (read) → `TaiSanDetailOut` gồm `chi_phi`, `bien_dong`, `khau_hao`
  - `PUT /{id}` (update) · `DELETE /{id}` (delete)
  - `GET /{id}/du-kien` (read) → `list[DongDuKienOut]`
  - `POST /{id}/bien-dong` (update) — body `BienDongIn{loai, ngay, ...}`
  - `GET /ky` (read) → `list[KyOut]`
  - `POST /ky/{nam}/{thang}/tinh` (update) → `BangKyOut`
  - `GET /ky/{nam}/{thang}/bang` (read) → `BangKyOut`
  - `POST /ky/{nam}/{thang}/chot` (close_book) · `POST /ky/{nam}/{thang}/mo` (close_book)

⚠️ Route TĨNH `/ky...` phải khai **TRƯỚC** `/{tai_san_id}` — FastAPI khớp theo thứ tự khai, để sau thì `"ky"` rơi vào `{tai_san_id}` và ăn 422.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_api.py
"""HTTP contract + cổng quyền của module Tài sản. Dùng fixture `client` (app thật, SQLite RAM)."""


def _token(client, seed_credentials):
    r = client.post("/api/auth/login", json=seed_credentials)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_can_dang_nhap_moi_xem_duoc(client):
    assert client.get("/api/tai-san").status_code == 401


def test_ghi_tang_roi_doc_lai(client, seed_credentials):
    h = _token(client, seed_credentials)
    r = client.post("/api/tai-san", headers=h, json={
        "ten": "May in Komori 4 mau", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-03-10", "nguon_vao": "ghi_tang",
        "chi_phi": [
            {"dien_giai": "Gia mua", "so_tien": 3200000000},
            {"dien_giai": "Van chuyen", "so_tien": 40000000},
            {"dien_giai": "Lap dat chay thu", "so_tien": 60000000},
        ],
        "ghi_chu_hach_toan": "211 / 6274 - to In",
    })
    assert r.status_code == 201, r.text
    ts = r.json()
    assert ts["nguyen_gia"] == 3300000000
    assert ts["ghi_chu_hach_toan"] == "211 / 6274 - to In"

    ds = client.get("/api/tai-san", headers=h).json()
    assert ds["total"] == 1
    assert ds["items"][0]["ma"] == ts["ma"]

    du_kien = client.get(f"/api/tai-san/{ts['id']}/du-kien", headers=h).json()
    assert du_kien[0]["muc_trich"] == 19516129


def test_loc_va_phan_trang_o_may_chu(client, seed_credentials):
    h = _token(client, seed_credentials)
    for i in range(3):
        client.post("/api/tai-san", headers=h, json={
            "ten": f"Tam cao su {i}", "loai": "ccdc", "so_luong": 12, "don_gia": 2400000,
            "so_thang": 24, "ngay_su_dung": "2026-07-01", "nguon_vao": "ghi_tang",
        })
    r = client.get("/api/tai-san?loai=ccdc&limit=2&offset=0", headers=h).json()
    assert r["total"] == 3
    assert len(r["items"]) == 2


def test_luong_ky_tinh_chot_mo(client, seed_credentials):
    h = _token(client, seed_credentials)
    client.post("/api/tai-san", headers=h, json={
        "ten": "May in Komori 4 mau", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-03-10", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 3300000000}],
    })
    bang = client.post("/api/tai-san/ky/2026/3/tinh", headers=h).json()
    assert bang["tong_muc_trich"] == 19516129
    assert bang["trang_thai"] == "mo"

    assert client.post("/api/tai-san/ky/2026/3/chot", headers=h).status_code == 200
    assert client.post("/api/tai-san/ky/2026/3/tinh", headers=h).status_code == 409

    assert client.post("/api/tai-san/ky/2026/3/mo", headers=h).status_code == 200
    assert client.post("/api/tai-san/ky/2026/3/tinh", headers=h).status_code == 200


def test_bien_dong_qua_api(client, seed_credentials):
    h = _token(client, seed_credentials)
    ts = client.post("/api/tai-san", headers=h, json={
        "ten": "May dao xen Polar", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-01-01", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 450000000}],
    }).json()
    r = client.post(f"/api/tai-san/{ts['id']}/bien-dong", headers=h, json={
        "loai": "ghi_giam", "ngay": "2026-02-01", "ly_do": "Thanh ly", "gia_ban": 200000000,
    })
    assert r.status_code == 201, r.text
    ct = client.get(f"/api/tai-san/{ts['id']}", headers=h).json()
    assert ct["trang_thai"] == "da_giam"
    assert len(ct["bien_dong"]) == 1


def test_route_ky_khong_bi_nuot_boi_route_id(client, seed_credentials):
    h = _token(client, seed_credentials)
    assert client.get("/api/tai-san/ky", headers=h).status_code == 200
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_api.py -q`
Expected: FAIL — 404 vì router chưa mount

- [ ] **Step 3: Viết schemas + router, mount vào app**

- `schemas/tai_san.py`: `ChiPhiIn/Out`, `TaiSanIn`, `TaiSanRow`, `TaiSanListOut{items, total}`, `TaiSanDetailOut`, `BienDongIn/Out`, `DongDuKienOut`, `KyOut`, `HangBangKyOut`, `BangKyOut{nam, thang, trang_thai, tong_muc_trich, items}`.
  ⚠️ Service trả dict thì **mọi field phải khai trong schema Out**, không khai là Pydantic nuốt im lặng và FE nhận `undefined`.
- `routers/tai_san.py`: khai `_DOC = require_permission(MODULE, "read")`, `_GHI = require_permission(MODULE, "update")`, `_TAO = require_permission(MODULE, "create")`, `_XOA = require_permission(MODULE, "delete")`, `_CHOT = require_permission(MODULE, "close_book")`. Map lỗi service → HTTP: `TaiSanNotFound`→404, `TaiSanTrung`→409, `TaiSanValidationError`→422, `TaiSanDaChotKy`/`KyDaChot`/`KyTruocChuaChot`→409.
- `main.py`: `app.include_router(tai_san.router)  # sổ tài sản cố định + CCDC (module quyền tai_san)`.

- [ ] **Step 4: Thêm module quyền vào seed**

Trong `backend/app/seed.py`: thêm `("tai_san", "Tài sản & Công cụ dụng cụ")` vào `MODULES` ngay sau `("tk_ngan_hang", ...)` (menu Kế toán), và cấp cho vai `"Kế toán"`:

```python
            # Sổ tài sản cố định + CCDC: lập phiếu, chạy khấu hao, CHỐT KỲ (`can_close_book`).
            "tai_san": {**_rcu(SCOPE_ALL), "can_close_book": True, "can_export": True},
```

- [ ] **Step 5: Migration 0277 cấp quyền trên DB live**

Thêm vào cuối `backend/app/db_migrations.py`: `_migrate_quyen_tai_san(db)` — nếu bảng `modules` chưa có key `tai_san` thì bỏ qua (seed sẽ tạo ở lần khởi động này), còn lại cấp `can_read/can_create/can_update/can_close_book/can_export` cho mọi vai đang có `can_read` trên `phieu_chi`. **Raw SQL đích danh cột** (ORM full-select kéo cột do migration sau thêm → vỡ deploy trên DB trung gian). Đăng ký: `MIGRATIONS.append(("0277_quyen_tai_san", _migrate_quyen_tai_san))`.

- [ ] **Step 6: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_api.py -q`
Expected: 6 passed

Run: `cd backend && python -m pytest tests/test_rbac_seed.py -q`
Expected: PASS (module mới không làm vỡ đếm module đã seed — nếu test đếm cứng số module thì cập nhật con số trong CÙNG commit này)

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/tai_san.py backend/app/routers/tai_san.py backend/app/main.py backend/app/seed.py backend/app/db_migrations.py backend/tests/test_tai_san_api.py
git commit -m "API so tai san + module quyen tai_san (mg 0277)"
```

---

### Task 7: Xuất Excel bảng khấu hao kỳ

**Files:**
- Create: `backend/app/services/tai_san/excel.py`
- Modify: `backend/app/routers/tai_san.py`
- Test: `backend/tests/test_tai_san_excel.py`

**Interfaces:**
- Produces: `xuat_bang_ky(rows: list[dict], *, nam: int, thang: int) -> bytes`; endpoint `GET /api/tai-san/ky/{nam}/{thang}/excel` (quyền `export`) trả `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_excel.py
"""Bảng khấu hao xuất Excel — cột cuối phải là Ghi chú hạch toán (kế toán nhập tay sang phần mềm kế toán)."""
from io import BytesIO

from openpyxl import load_workbook

from app.services.tai_san.excel import xuat_bang_ky


def _rows():
    return [{
        "ma": "TS-0001", "ten": "May in Komori 4 mau", "bo_phan_ten": "To In",
        "nguyen_gia": 3_300_000_000, "muc_trich": 27_500_000,
        "luy_ke": 157_016_129, "con_lai": 3_142_983_871,
        "ghi_chu_hach_toan": "211 / 6274 - to In",
    }]


def test_file_excel_co_dung_cot_va_dong_tong():
    wb = load_workbook(BytesIO(xuat_bang_ky(_rows(), nam=2026, thang=8)))
    ws = wb.active
    tieu_de = [c.value for c in ws[1]]
    assert tieu_de[0] == "Mã"
    assert tieu_de[-1] == "Ghi chú hạch toán"
    assert ws.cell(row=2, column=1).value == "TS-0001"
    assert ws.cell(row=2, column=len(tieu_de)).value == "211 / 6274 - to In"
    # dòng cuối là TỔNG mức trích
    assert ws.cell(row=3, column=5).value == 27_500_000
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_excel.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.tai_san.excel'`

- [ ] **Step 3: Viết `xuat_bang_ky` + endpoint**

Theo lối `services/bao_cao_cong_no_excel.py`: `openpyxl.Workbook()`, tiêu đề `["Mã","Tên tài sản","Bộ phận","Nguyên giá","Trích kỳ này","Lũy kế","Còn lại","Ghi chú hạch toán"]`, định dạng số `#,##0`, dòng TỔNG cuối bảng, `freeze_panes="A2"`, trả `bytes`.

- [ ] **Step 4: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_excel.py -q`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tai_san/excel.py backend/app/routers/tai_san.py backend/tests/test_tai_san_excel.py
git commit -m "Xuat Excel bang khau hao ky tai san"
```

---

### Task 8: Kiểm kê (mức tối giản)

**Files:**
- Create: `backend/app/services/tai_san/kiem_ke_service.py`
- Modify: `backend/app/routers/tai_san.py`, `backend/app/schemas/tai_san.py`
- Test: `backend/tests/test_tai_san_kiem_ke.py`

**Interfaces:**
- Produces: `KiemKeService(db)` với `tao_dot(*, ngay, bo_phan_id=None, user_id=None) -> TaiSanKiemKe` (tự bung dòng cho mọi tài sản `dang_dung` thuộc bộ phận), `ghi_ket_qua(dot_id, dong_id, *, ket_qua, tinh_trang=None, ghi_chu=None)`, `them_phat_hien(dot_id, *, ten_phat_hien, ghi_chu=None)`, `ket_thuc(dot_id) -> dict{thieu: [...], thua: [...]}`.
- Endpoint: `POST /api/tai-san/kiem-ke` (create) · `GET /api/tai-san/kiem-ke` (read) · `GET /api/tai-san/kiem-ke/{id}` (read) · `PUT /api/tai-san/kiem-ke/{id}/dong/{dong_id}` (update) · `POST /api/tai-san/kiem-ke/{id}/ket-thuc` (update). ⚠️ Khai TRƯỚC `/{tai_san_id}`.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_tai_san_kiem_ke.py
"""Đợt kiểm kê: bung danh sách phải có → đối chiếu tay → ra thiếu/thừa."""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.tai_san import LOAI_TSCD
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.kiem_ke_service import KiemKeService
from app.services.tai_san.service import TaiSanService


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db)), KiemKeService(db)


def _hai_tai_san(svc):
    a = svc.ghi_tang(dict(ten="May A", loai=LOAI_TSCD, so_thang=120, ngay_su_dung=date(2026, 1, 1),
                          chi_phi=[{"dien_giai": "NG", "so_tien": 100_000_000}]))
    b = svc.ghi_tang(dict(ten="May B", loai=LOAI_TSCD, so_thang=120, ngay_su_dung=date(2026, 1, 1),
                          chi_phi=[{"dien_giai": "NG", "so_tien": 200_000_000}]))
    return a, b


def test_tao_dot_bung_du_danh_sach():
    db, svc, kk = _moi_truong()
    _hai_tai_san(svc)
    dot = kk.tao_dot(ngay=date(2026, 12, 31))
    assert len(dot.dong) == 2


def test_ket_thuc_ra_danh_sach_thieu_va_thua():
    db, svc, kk = _moi_truong()
    a, b = _hai_tai_san(svc)
    dot = kk.tao_dot(ngay=date(2026, 12, 31))
    d_a = next(d for d in dot.dong if d.tai_san_id == a.id)
    d_b = next(d for d in dot.dong if d.tai_san_id == b.id)
    kk.ghi_ket_qua(dot.id, d_a.id, ket_qua="co")
    kk.ghi_ket_qua(dot.id, d_b.id, ket_qua="khong_thay", ghi_chu="Khong tim thay tai xuong")
    kk.them_phat_hien(dot.id, ten_phat_hien="May dan keo chua vao so")

    ket = kk.ket_thuc(dot.id)
    assert [x["ten"] for x in ket["thieu"]] == ["May B"]
    assert [x["ten"] for x in ket["thua"]] == ["May dan keo chua vao so"]
    assert kk.lay(dot.id).trang_thai == "da_ket"
```

- [ ] **Step 2: Chạy test cho chắc là đỏ**

Run: `cd backend && python -m pytest tests/test_tai_san_kiem_ke.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.tai_san.kiem_ke_service'`

- [ ] **Step 3: Viết service + endpoint**

- [ ] **Step 4: Chạy test cho chắc là xanh**

Run: `cd backend && python -m pytest tests/test_tai_san_kiem_ke.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tai_san/kiem_ke_service.py backend/app/routers/tai_san.py backend/app/schemas/tai_san.py backend/tests/test_tai_san_kiem_ke.py
git commit -m "Kiem ke tai san muc toi gian: bung danh sach, doi chieu tay, ra thieu thua"
```

---

### Task 9: Frontend — API client + màn danh sách + ghi tăng

**Files:**
- Create: `frontend/src/api/taiSan.ts`, `frontend/src/pages/tai-san/index.ts`, `TaiSanPage.tsx`, `DanhSachView.tsx`, `GhiTangDialog.tsx`, `tai-san.css`
- Modify: `frontend/src/components/Sidebar.tsx`, `frontend/src/components/AppShell.tsx`

**Interfaces:**
- Consumes: endpoint Task 6.
- Produces: `taiSanApi` với `danhSach(params)`, `chiTiet(id)`, `ghiTang(body)`, `sua(id, body)`, `xoa(id)`, `duKien(id)`, `bienDong(id, body)`, `dsKy()`, `tinhKy(nam, thang)`, `bangKy(nam, thang)`, `chotKy(nam, thang)`, `moKy(nam, thang)`, `excelKy(nam, thang)`; type `TaiSanRow`, `TaiSanChiTiet`, `BangKy`, `DongDuKien`. Component `TaiSanPage` nhận `{ navigate }`.

- [ ] **Step 1: Viết api module**

`frontend/src/api/taiSan.ts` — dùng chung `authed` của `client.ts` (KHÔNG sửa `client.ts`, file đó đang bị nhánh khác đụng). Khai nhãn dùng chung ở một chỗ:

```ts
export const NHAN_LOAI: Record<string, string> = { tscd: "Tài sản cố định", ccdc: "Công cụ dụng cụ" };
export const NHAN_TRANG_THAI: Record<string, string> = { dang_dung: "Đang dùng", da_giam: "Đã ghi giảm" };
export const NHAN_BIEN_DONG: Record<string, string> = {
  dieu_chuyen: "Điều chuyển", nang_cap: "Nâng cấp", ghi_giam: "Ghi giảm",
};
```

- [ ] **Step 2: Viết màn danh sách + dialog ghi tăng**

`TaiSanPage` có 3 tab: *Danh sách* · *Khấu hao theo kỳ* (Task 10) · *Kiểm kê* (Task 11).

`DanhSachView`: ô tìm, lọc loại/bộ phận/trạng thái, phân trang — **mọi thứ gửi lên server**, không lọc trong JS. Cột: Mã · Tên · Loại · Bộ phận · Nguyên giá · Đã hao mòn · Còn lại · Trạng thái.

`GhiTangDialog`: chọn Loại; bảng dòng cấu thành nguyên giá (thêm/xoá dòng, tự cộng tổng); ô Số tháng có microcopy `Tham khảo: máy in 7–15 năm · công cụ dụng cụ tối đa 3 năm`; ô Ngày đưa vào sử dụng; Bộ phận / Người quản lý / Vị trí; ô Ghi chú hạch toán; công tắc *Nạp số dư đầu kỳ* mở thêm hai ô bắt buộc **Số tháng đã trích** + **Hao mòn lũy kế**. Với CCDC hiện thêm Số lượng + Đơn giá thay cho bảng dòng chi phí. Sau khi lưu, hiện ngay bảng khấu hao dự kiến (gọi `duKien`).

⚠️ Ô ngày dùng `type="date"` có `min`/`max` — datetime-local từng đẻ năm 6 chữ số và ăn 422 câm.

- [ ] **Step 3: Nối vào menu và khung app**

`Sidebar.tsx` — thêm vào nhóm `ke-toan`, ngay sau `ke-toan-tai-khoan-ngan-hang`:

```tsx
      {
        id: "tai-san",
        label: "Tài sản & CCDC",
        icon: "database",
        module: "tai_san",
      },
```

`AppShell.tsx` — `import { TaiSanPage } from "../pages/tai-san";` và trong `renderContent()`:

```tsx
      case "tai-san":
        return <TaiSanPage navigate={navigate} />;
```

- [ ] **Step 4: Kiểm kiểu**

Run: `cd frontend && npx tsc --noEmit`
Expected: không lỗi

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/taiSan.ts frontend/src/pages/tai-san frontend/src/components/Sidebar.tsx frontend/src/components/AppShell.tsx
git commit -m "Man Tai san & CCDC: danh sach loc o may chu + dialog ghi tang"
```

---

### Task 10: Frontend — tab khấu hao theo kỳ

**Files:**
- Create: `frontend/src/pages/tai-san/KhauHaoKyView.tsx`
- Modify: `frontend/src/pages/tai-san/TaiSanPage.tsx`

**Interfaces:**
- Consumes: `taiSanApi.tinhKy/bangKy/chotKy/moKy/excelKy` (Task 9).

- [ ] **Step 1: Viết view**

Chọn tháng bằng `MonthPicker` có sẵn (`components/MonthPicker.tsx`). Nút *Tính khấu hao tháng này* → bảng: Mã · Tên · Bộ phận · Nguyên giá · Trích tháng này · Lũy kế · Còn lại · Ghi chú hạch toán, có dòng TỔNG. Nút *Xuất Excel*. Nút *Chốt kỳ* (chỉ hiện khi có quyền `close_book`, đọc từ `caps` của AppShell) và *Mở lại kỳ* khi kỳ đã chốt. Kỳ đã chốt hiển thị băng khoá + ẩn nút Tính.

Lỗi 409 phải hiện đúng câu của server (kỳ đã chốt / kỳ trước chưa chốt), không nuốt thành "có lỗi".

- [ ] **Step 2: Kiểm kiểu**

Run: `cd frontend && npx tsc --noEmit`
Expected: không lỗi

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/tai-san
git commit -m "Tab khau hao theo ky: tinh, xuat Excel, chot va mo ky"
```

---

### Task 11: Frontend — biến động + kiểm kê

**Files:**
- Create: `frontend/src/pages/tai-san/BienDongDialog.tsx`, `frontend/src/pages/tai-san/KiemKeView.tsx`
- Modify: `frontend/src/pages/tai-san/DanhSachView.tsx`, `TaiSanPage.tsx`

- [ ] **Step 1: Dialog biến động**

Một dialog, ba chế độ chọn bằng tab: *Điều chuyển* (bộ phận mới, ngày, lý do) · *Nâng cấp* (số tiền, số tháng còn dùng, ngày) · *Ghi giảm* (lý do chọn từ danh sách `thanh_ly / nhuong_ban / mat / hong / gop_von`, ngày, giá bán, và với CCDC thêm ô Số lượng giảm). Sau khi lưu, mở lại chi tiết để thấy dòng biến động mới và mức trích đã đổi. Với ghi giảm có giá bán, hiện chênh lệch server trả về.

- [ ] **Step 2: Tab kiểm kê**

Tạo đợt (ngày + bộ phận) → bảng dòng với nút *Có* / *Không thấy* trên từng dòng và ô Tình trạng → nút *Thêm phát hiện ngoài sổ* → *Kết thúc đợt* hiện hai danh sách thiếu/thừa.

- [ ] **Step 3: Kiểm kiểu**

Run: `cd frontend && npx tsc --noEmit`
Expected: không lỗi

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/tai-san
git commit -m "Dialog bien dong + tab kiem ke cua man Tai san"
```

---

### Task 12: Nghiệm thu bằng UI thật

**Files:** không sửa code trừ khi phát hiện lỗi.

Bắt buộc theo CLAUDE.md: luồng nghiệp vụ có UI phải thao tác lại bằng chuột/bàn phím thật trên dev-browser, **không dùng API/curl thay bất kỳ bước nào**, kể cả bước dựng dữ liệu.

- [ ] **Step 1: Bật server**

Bật uvicorn + vite bằng `Win32_Process.Create` qua WMI (Bash nền và `Start-Process` đều chết khi hết phiên). FE `localhost:5173`, BE `127.0.0.1:8000`. Đăng nhập `admin` / `admin123`.

- [ ] **Step 2: Đi hết luồng, ghi lại từng bước**

1. Vào *Kế toán → Tài sản & CCDC*, bấm **Ghi tăng**, gõ máy Komori với ba dòng chi phí 3.200.000.000 + 40.000.000 + 60.000.000, số tháng 120, ngày 10/03/2026 → kiểm tổng nguyên giá hiện 3.300.000.000 và bảng dự kiến dòng đầu 19.516.129.
2. Ghi tăng lô CCDC 12 tấm cao su, đơn giá 2.400.000, 24 tháng → nguyên giá 28.800.000, dự kiến 1.200.000/tháng.
3. Bật công tắc *Nạp số dư đầu kỳ*, nhập máy Polar 450.000.000 với 31 tháng đã trích và lũy kế 116.250.000 → dự kiến 3.750.000/tháng.
4. Tab *Khấu hao theo kỳ*: chọn tháng 03/2026, bấm Tính → soát bảng, bấm **Chốt kỳ**, kiểm băng khoá hiện lên và nút Tính biến mất.
5. Bấm **Mở lại kỳ**, Tính lại, kiểm số không nhân đôi.
6. Trên máy Komori bấm **Biến động → Nâng cấp** 180.000.000, 114 tháng, ngày 01/09/2026 → mở chi tiết kiểm nguyên giá 3.480.000.000 và tính kỳ 09/2026 ra 29.148.981.
7. **Ghi giảm** máy Polar lý do Nhượng bán, giá bán 200.000.000 → kiểm chênh lệch hiện đúng và tài sản chuyển trạng thái Đã ghi giảm.
8. Tab *Kiểm kê*: tạo đợt, tick một dòng Có, một dòng Không thấy, thêm một phát hiện ngoài sổ, kết thúc đợt → kiểm hai danh sách.
9. Bấm **Xuất Excel** kỳ 03/2026, mở file kiểm cột cuối là Ghi chú hạch toán.

- [ ] **Step 3: Viết báo cáo nghiệm thu**

Liệt kê CỤ THỂ đã bấm gì, gõ gì, thấy gì ở từng bước. Nếu vì lý do nào đó phải tắt qua API ở một đoạn, nói rõ ngay trong báo cáo.

- [ ] **Step 4: Commit (nếu có sửa lỗi phát hiện lúc nghiệm thu)**

```bash
git add -A
git commit -m "Va loi phat hien khi nghiem thu UI man Tai san"
```

---

## Self-Review

**Spec coverage:** §2 phạm vi → Task 1–11 · §3 ô ghi chú hạch toán → Task 1 (cột), 6 (schema), 7 (cột Excel), 9 (ô nhập) · §4 quy tắc tính → Task 2 · §5.1 số dư đầu kỳ → Task 3 · §5.2 ghi tăng → Task 3, 9 · §5.3 kỳ + chốt → Task 4, 10 · §5.4–5.6 ba chứng từ → Task 5, 11 · §5.7 CCDC theo lô + giảm một phần → Task 3, 5 · §5.8 kiểm kê → Task 8, 11 · §6 dữ liệu → Task 1 · §7 phân quyền → Task 6 · §8 ca biên → Task 2 (trích theo ngày, cap kỳ cuối, hết khấu hao), Task 3 (chặn sửa/xoá sau chốt), Task 4 (chốt hai lần, nhảy cóc kỳ) · §9 điểm cần xác nhận → ngưỡng 30 triệu **chưa** có task.

**Bổ sung:** ngưỡng cảnh báo 30.000.000 làm trong Task 9 Step 2 — dialog ghi tăng hiện cảnh báo mềm khi nguyên giá dưới ngưỡng mà loại là `tscd`, kèm nút chuyển sang CCDC; ngưỡng đọc từ hằng `NGUONG_TSCD = 30_000_000` khai trong `frontend/src/api/taiSan.ts` (một chỗ, đổi sau không phải dò).

**Type consistency:** `co_so_trich`/`so_thang_con`/`moc_tu_ngay` dùng nhất quán từ Task 1 → 5. `trich_mot_ky` giữ nguyên chữ ký ở Task 2 và 4. `TaiSanListOut{items, total}` khớp giữa Task 6 và 9.
