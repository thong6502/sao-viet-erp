# Thực tế sản xuất phản hồi về Kế hoạch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Người lập kế hoạch nhìn thấy sản xuất đang chạy thật tới đâu ngay trên bàn Gantt Xếp lịch 2, có bộ dò báo lệch thực tế, và mọi nơi đếm sản lượng đều hiện con số "còn thiếu" so với mục tiêu bước.

**Architecture:** Lớp thực tế là **chỉ đọc, đè lên**. `xep_lich_2` nạp GỘP một map `xep_lich_cong_doan.id → tiến độ thật` (join `SanXuatCongViec` qua cặp neo `lsx_cong_doan_id` / `bai_ghep_cong_doan_id`), gắn vào payload thanh Gantt và nuôi một bộ dò thứ 13. Máy không bao giờ tự dời thanh. Con số "còn thiếu" là DẪN XUẤT (`so_luong_ra − tong_tot`), không thêm cột, không đổi cổng đóng nhóm.

**Tech Stack:** FastAPI + SQLAlchemy 2 (Postgres dev/prod, SQLite in-memory cho test) · React 18 + TypeScript + Vite · pytest.

**Spec:** `docs/spec-thuc-te-vs-ke-hoach.md` (§1.1, §1.2, §2.1–§2.3). Nền nghiệp vụ: `docs/spec-thuc-hien-san-xuat.md`, `docs/spec-xep-lich-2.md`.

## Global Constraints

- Ngôn ngữ code/comment/chuỗi UI: **tiếng Việt** (thuật ngữ kỹ thuật giữ tiếng Anh). Đây là quy ước đang chạy của repo.
- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, không ALTER. Plan này **không thêm cột nào** — nếu bạn thấy mình cần cột mới thì bạn đã đi lệch spec, dừng lại và hỏi.
- `docs/DB_SCHEMA.md` có guard test: mọi cột trong model phải được ghi ở đó. Plan này không thêm cột ⇒ không đụng file đó.
- Máy **không tự dời lịch** theo thực tế. Không ghi đè `start_at`/`finish_at`/`is_locked` của `xep_lich_cong_doan`.
- Bộ dò mới **luôn** `SEV_LUU_Y`, **không bao giờ** `SEV_CHAN`.
- **Không đổi 6 điều kiện đóng nhóm** trong `services/san_xuat/dong_nhom.py::_danh_gia`.
- Chuỗi `issue_key` cũ là state của người xử lý — **không đổi chuỗi nào đang có**, chỉ thêm tiền tố mới.
- Nạp dữ liệu phải GỘP (batch) theo lối `_nap_nhan` — cấm N+1 trong `workspace()`.
- Verify: `pytest` nhắm đúng file test đã đổi + `npx tsc --noEmit` trong `frontend/`. **Đừng chạy `./init.ps1`** và đừng chạy cả bộ test nếu chưa được yêu cầu.
- Sửa route/schema backend ⇒ **restart uvicorn** (repo này không hot-reload đáng tin).
- **Không commit hoặc push nếu chưa được yêu cầu.** Các bước "Commit" bên dưới chỉ thực hiện khi chủ dự án bảo commit; nếu chưa, dừng ở bước test xanh.

---

## File Structure

| File | Trách nhiệm |
| --- | --- |
| `backend/app/services/xep_lich_2/thuc_te.py` | **Tạo.** Nạp GỘP tiến độ thật cho một tập dòng lịch. Không biết gì về HTTP, không biết gì về Gantt. |
| `backend/app/services/xep_lich_2/service.py` | **Sửa.** `_dong_view` thêm khoá `thuc_te`; `workspace()` gọi nạp gộp một lần. |
| `backend/app/services/xep_lich_van_de_service.py` | **Sửa.** Hằng `K_LECH_THUC_TE`, `NGUONG_LECH_THUC_TE_PHUT`; bộ dò `_lech_thuc_te`; ghi vào `_build`. |
| `backend/app/services/san_xuat/board.py` | **Sửa.** Payload công việc + chi tiết mang `con_thieu`. |
| `backend/app/services/san_xuat/dong_nhom.py` | **Sửa.** Trả kèm `muc_tieu`/`da_dat`/`con_thieu` của nhóm — **không** đổi điều kiện đóng. |
| `backend/app/schemas/san_xuat.py` | **Sửa.** `SanLuongOut` + `WorkItemOut` mang trường mới (router `san_xuat` CÓ `response_model` ⇒ không khai là mất field). |
| `frontend/src/api/client.ts` | **Sửa.** `Xl2Dong.thuc_te`, `Xl2ThucTe`, `SxSanLuong.con_thieu`, `SxWorkItem.con_thieu`. |
| `frontend/src/pages/Xl2Gantt.tsx` | **Sửa.** Lớp đè tiến độ trong thanh + đuôi "quá giờ". |
| `frontend/src/pages/xep-lich-2.css` | **Sửa.** `.xl2-bar__thuc-te`, `.xl2-bar__qua-gio`. |
| `frontend/src/pages/ThsxExecPanels.tsx` | **Sửa.** Hiện "còn thiếu" ở khối Sản lượng. |
| `backend/tests/test_xep_lich_2_thuc_te.py` | **Tạo.** Test nạp gộp + bộ dò. |
| `backend/tests/test_san_xuat_con_thieu.py` | **Tạo.** Test con số còn thiếu ở bước và ở nhóm. |

---

### Task 1: Nạp gộp tiến độ thật cho dòng lịch

**Files:**
- Create: `backend/app/services/xep_lich_2/thuc_te.py`
- Test: `backend/tests/test_xep_lich_2_thuc_te.py`

**Interfaces:**
- Consumes: `app.models.san_xuat.SanXuatCongViec` (`lsx_cong_doan_id`, `bai_ghep_cong_doan_id`, `trang_thai`, `du_kien_bat_dau`, `du_kien_ket_thuc`, `so_luong_ra`, `don_vi_ra`, `phien_ban_so`, `goi_id`), `app.models.san_xuat_san_luong.SanXuatBatch` (`cong_viec_id`, `tot`, `hong`), `app.models.san_xuat.SanXuatPhienChay` (`cong_viec_id`, `bat_dau`, `ket_thuc`).
- Produces:
  ```python
  def nap_thuc_te(db: Session, rows: list) -> dict[int, dict]
  # rows: list[XepLichCongDoan] hoặc list[dict] có 'id' + 'lsx_cong_doan_id' + 'bai_ghep_cong_doan_id'
  # trả {xep_lich_cong_doan_id: {
  #   "cong_viec_id": int, "trang_thai": str,
  #   "bat_dau_thuc": datetime|None, "ket_thuc_thuc": datetime|None,
  #   "tong_tot": float, "tong_hong": float,
  #   "muc_tieu": float|None, "don_vi": str|None,
  #   "con_thieu": float|None, "phan_tram": float|None,
  #   "tre_bat_dau_phut": int|None, "tre_ket_thuc_phut": int|None,
  # }}
  ```

- [ ] **Step 1: Viết test thất bại trước**

Tạo `backend/tests/test_xep_lich_2_thuc_te.py`:

```python
"""Xếp lịch 2 — LỚP THỰC TẾ đè lên bàn Gantt (docs/spec-thuc-te-vs-ke-hoach.md §2.1).

Chỉ soi tầng hàm `services/xep_lich_2/thuc_te.py`: nó nhận danh sách dòng lịch, trả map tiến độ
thật. Dựng dàn cảnh bằng fixture luồng thật của thực hiện sản xuất (đơn → lệnh → phát hành vào tổ)
rồi tự gắn `xep_lich_cong_doan` trỏ đúng cặp neo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, SanXuatPhienChay
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.xep_lich import NGUON_LSX, TT_DA_XEP, XepLichCongDoan
from app.services.xep_lich_2.thuc_te import nap_thuc_te

from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _mot_cv, _to_khoan, admin, customer, db, lsx_svc, orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _dong_lich(db, cv) -> XepLichCongDoan:
    """Dòng lịch trỏ đúng bước LSX mà công việc đang neo."""
    d = XepLichCongDoan(
        nguon=NGUON_LSX, lsx_id=cv.lsx_id, lsx_cong_doan_id=cv.lsx_cong_doan_id,
        source_thu_tu=0, loai_buoc="to", trang_thai=TT_DA_XEP,
        start_at=_T0, finish_at=_T0 + timedelta(hours=4),
    )
    db.add(d)
    db.flush()
    return d


def test_chua_chay_thi_khong_co_dong_nao_trong_map(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT1")
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.commit()

    ra = nap_thuc_te(db, [d])
    assert ra[d.id]["trang_thai"] == cv.trang_thai
    assert ra[d.id]["bat_dau_thuc"] is None
    assert ra[d.id]["tong_tot"] == 0.0
    assert ra[d.id]["con_thieu"] == 10000.0


def test_dang_chay_co_batch_thi_tinh_phan_tram_va_con_thieu(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT2")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1, bat_dau=_T0 + timedelta(hours=2)))
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0 + timedelta(hours=2),
                        ket_thuc=_T0 + timedelta(hours=3), tong=6000, tot=5800, hong=200))
    db.commit()

    ra = nap_thuc_te(db, [d])[d.id]
    assert ra["tong_tot"] == 5800.0
    assert ra["tong_hong"] == 200.0
    assert ra["con_thieu"] == 4200.0
    assert ra["phan_tram"] == pytest.approx(58.0)
    assert ra["tre_bat_dau_phut"] == 120


def test_qua_gio_du_kien_ma_van_chay_thi_bao_tre_ket_thuc(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT3")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 100
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1, bat_dau=_T0))
    db.commit()

    ra = nap_thuc_te(db, [d], bay_gio=_T0 + timedelta(hours=7))[d.id]
    assert ra["ket_thuc_thuc"] is None
    assert ra["tre_ket_thuc_phut"] == 180


def test_xong_roi_thi_lay_moc_ket_thuc_phien_cuoi(db, orders, lsx_svc, admin, customer):
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT4")
    cv.trang_thai = CV_HOAN_THANH
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 100
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1,
                            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1)))
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=2,
                            bat_dau=_T0 + timedelta(hours=2),
                            ket_thuc=_T0 + timedelta(hours=5)))
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=5),
                        tong=100, tot=100, hong=0))
    db.commit()

    ra = nap_thuc_te(db, [d])[d.id]
    assert ra["bat_dau_thuc"].replace(tzinfo=timezone.utc) == _T0
    assert ra["ket_thuc_thuc"].replace(tzinfo=timezone.utc) == _T0 + timedelta(hours=5)
    assert ra["con_thieu"] == 0.0
    assert ra["tre_ket_thuc_phut"] == 60


def test_khong_co_cong_viec_thi_khong_co_khoa(db):
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_id=None, lsx_cong_doan_id=999_999,
                        source_thu_tu=0, loai_buoc="may", trang_thai=TT_DA_XEP)
    db.add(d)
    db.commit()
    assert nap_thuc_te(db, [d]) == {}


def test_danh_sach_rong_khong_chay_query(db):
    assert nap_thuc_te(db, []) == {}
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_xep_lich_2_thuc_te.py -q
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'app.services.xep_lich_2.thuc_te'`.

- [ ] **Step 3: Viết `thuc_te.py`**

Tạo `backend/app/services/xep_lich_2/thuc_te.py`:

```python
"""Lớp THỰC TẾ đè lên bàn Gantt — CHỈ ĐỌC (docs/spec-thuc-te-vs-ke-hoach.md §2.1).

Bàn xếp lịch dựng từ `xep_lich_cong_doan`; sản xuất ghi vào `san_xuat_*`. Hai tầng nối nhau bằng
cặp neo có sẵn: `lsx_cong_doan_id` và `bai_ghep_cong_doan_id`. Module này chỉ ĐỌC — máy KHÔNG tự
dời thanh (xem docstring `XepLichCongDoan`: "record-only, máy đề xuất, người quyết").

Nạp GỘP một lượt cho cả bàn, đúng lối `_nap_nhan` — bàn có vài trăm thanh, N+1 ở đây là chết.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models.san_xuat import SanXuatCongViec, SanXuatPhienChay
from ...models.san_xuat_san_luong import SanXuatBatch


def _aware(dt: datetime | None) -> datetime | None:
    """Giờ đọc từ SQLite về naive; so hai mốc lệch tz là ném TypeError giữa lúc dựng bàn."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _phut(sau: datetime | None, truoc: datetime | None) -> int | None:
    """Số phút `sau` muộn hơn `truoc`; None nếu thiếu mốc, 0 nếu không muộn."""
    a, b = _aware(sau), _aware(truoc)
    if a is None or b is None:
        return None
    return max(int((a - b).total_seconds() // 60), 0)


def _neo(r) -> tuple[str, int] | None:
    """Khoá neo của một dòng lịch: ('lsx', lsx_cong_doan_id) hoặc ('bg', bai_ghep_cong_doan_id)."""
    lsx_cd = r["lsx_cong_doan_id"] if isinstance(r, dict) else r.lsx_cong_doan_id
    bg_cd = r["bai_ghep_cong_doan_id"] if isinstance(r, dict) else r.bai_ghep_cong_doan_id
    if bg_cd:
        return ("bg", int(bg_cd))
    if lsx_cd:
        return ("lsx", int(lsx_cd))
    return None


def nap_thuc_te(db: Session, rows: list, *, bay_gio: datetime | None = None) -> dict[int, dict]:
    """`{xep_lich_cong_doan.id: tiến-độ-thật}` cho danh sách dòng lịch đã cho.

    Dòng không có công việc tương ứng (chưa phát hành, hoặc phát hành phiên bản khác) KHÔNG có
    khoá trong map — bên gọi cứ `.get()`, không cần biết vì sao vắng.

    Khi một công đoạn có nhiều công việc (phát hành nhiều phiên bản), lấy bản `phien_ban_so` LỚN
    NHẤT: đó là phiên bản đang hiệu lực, đúng thứ tổ đang chạy.
    """
    if not rows:
        return {}
    neo_map: dict[tuple[str, int], list[int]] = {}
    for r in rows:
        k = _neo(r)
        if k is None:
            continue
        neo_map.setdefault(k, []).append(r["id"] if isinstance(r, dict) else r.id)
    if not neo_map:
        return {}

    lsx_cds = [i for (loai, i) in neo_map if loai == "lsx"]
    bg_cds = [i for (loai, i) in neo_map if loai == "bg"]
    dieu_kien = []
    if lsx_cds:
        dieu_kien.append(SanXuatCongViec.lsx_cong_doan_id.in_(lsx_cds))
    if bg_cds:
        dieu_kien.append(SanXuatCongViec.bai_ghep_cong_doan_id.in_(bg_cds))
    from sqlalchemy import or_

    cvs = list(db.scalars(
        select(SanXuatCongViec).where(or_(*dieu_kien)).order_by(SanXuatCongViec.phien_ban_so)
    ))
    if not cvs:
        return {}

    # Bản SAU đè bản trước ⇒ còn lại đúng phiên bản lớn nhất cho mỗi neo.
    cv_theo_neo: dict[tuple[str, int], SanXuatCongViec] = {}
    for cv in cvs:
        if cv.bai_ghep_cong_doan_id:
            cv_theo_neo[("bg", int(cv.bai_ghep_cong_doan_id))] = cv
        elif cv.lsx_cong_doan_id:
            cv_theo_neo[("lsx", int(cv.lsx_cong_doan_id))] = cv

    cv_ids = [cv.id for cv in cv_theo_neo.values()]
    sl_map = {
        cid: (float(tot or 0), float(hong or 0))
        for cid, tot, hong in db.execute(
            select(SanXuatBatch.cong_viec_id,
                   func.coalesce(func.sum(SanXuatBatch.tot), 0),
                   func.coalesce(func.sum(SanXuatBatch.hong), 0))
            .where(SanXuatBatch.cong_viec_id.in_(cv_ids))
            .group_by(SanXuatBatch.cong_viec_id)
        ).all()
    }
    moc_map = {
        cid: (bd, kt, int(con_mo or 0))
        for cid, bd, kt, con_mo in db.execute(
            select(SanXuatPhienChay.cong_viec_id,
                   func.min(SanXuatPhienChay.bat_dau),
                   func.max(SanXuatPhienChay.ket_thuc),
                   func.count().filter(SanXuatPhienChay.ket_thuc.is_(None)))
            .where(SanXuatPhienChay.cong_viec_id.in_(cv_ids))
            .group_by(SanXuatPhienChay.cong_viec_id)
        ).all()
    }

    now = _aware(bay_gio) or datetime.now(timezone.utc)
    ra: dict[int, dict] = {}
    for khoa, cv in cv_theo_neo.items():
        tot, hong = sl_map.get(cv.id, (0.0, 0.0))
        bd, kt, con_mo = moc_map.get(cv.id, (None, None, 0))
        # Phiên còn mở ⇒ chưa xong, đừng lấy `max(ket_thuc)` của các phiên đã đóng làm giờ kết thúc.
        ket_thuc = None if con_mo else _aware(kt)
        muc_tieu = float(cv.so_luong_ra) if cv.so_luong_ra is not None else None
        con_thieu = max(muc_tieu - tot, 0.0) if muc_tieu is not None else None
        phan_tram = round(tot / muc_tieu * 100, 1) if muc_tieu else None
        # Quá giờ dự kiến mà chưa đóng ⇒ đo tới BÂY GIỜ; đã đóng ⇒ đo tới mốc đóng thật.
        tre_kt = _phut(ket_thuc or now, cv.du_kien_ket_thuc) if cv.du_kien_ket_thuc else None
        thong_tin = {
            "cong_viec_id": cv.id,
            "trang_thai": cv.trang_thai,
            "bat_dau_thuc": _aware(bd),
            "ket_thuc_thuc": ket_thuc,
            "tong_tot": tot,
            "tong_hong": hong,
            "muc_tieu": muc_tieu,
            "don_vi": cv.don_vi_ra,
            "con_thieu": con_thieu,
            "phan_tram": phan_tram,
            "tre_bat_dau_phut": _phut(bd, cv.du_kien_bat_dau) if cv.du_kien_bat_dau else None,
            "tre_ket_thuc_phut": tre_kt,
        }
        for dong_id in neo_map.get(khoa, []):
            ra[dong_id] = dict(thong_tin)
    return ra
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_xep_lich_2_thuc_te.py -q
```

Kỳ vọng: 6 passed.

- [ ] **Step 5: Commit** *(chỉ khi chủ dự án đã bảo commit)*

```bash
git add backend/app/services/xep_lich_2/thuc_te.py backend/tests/test_xep_lich_2_thuc_te.py
git commit -m "Xếp lịch 2: nạp gộp tiến độ thật của sản xuất cho dòng lịch"
```

---

### Task 2: Gắn lớp thực tế vào payload bàn Gantt

**Files:**
- Modify: `backend/app/services/xep_lich_2/service.py` (`_dong_view` ~dòng 894, `workspace` ~dòng 974)
- Modify: `frontend/src/api/client.ts` (`Xl2Dong` ~dòng 1084)
- Test: `backend/tests/test_xep_lich_2_thuc_te.py` (thêm test)

**Interfaces:**
- Consumes: `nap_thuc_te(db, rows, *, bay_gio=None) -> dict[int, dict]` (Task 1).
- Produces: mỗi phần tử `workspace()["dong"]` có khoá `thuc_te: dict | None`. TS: `Xl2Dong.thuc_te: Xl2ThucTe | null`.

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào cuối `backend/tests/test_xep_lich_2_thuc_te.py`:

```python
def test_ban_lam_viec_mang_theo_lop_thuc_te(db, orders, lsx_svc, admin, customer):
    """`workspace()` phải gắn `thuc_te` vào từng thanh — và MỌI thanh đều có khoá đó (None nếu
    chưa phát hành), để FE khỏi phải phân biệt 'thiếu khoá' với 'chưa chạy'."""
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.xep_lich_2_repo import XepLich2Repository
    from app.services.xep_lich_2 import XepLich2Service

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT5")
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = _T0
    cv.du_kien_ket_thuc = _T0 + timedelta(hours=4)
    cv.so_luong_ra = 1000
    cv.don_vi_ra = "tờ"
    d = _dong_lich(db, cv)
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
                        tong=400, tot=400, hong=0))
    db.commit()

    svc = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
    ban = svc.workspace(tu=_T0.date(), den=(_T0 + timedelta(days=1)).date())
    thanh = {row["id"]: row for row in ban["dong"]}
    assert "thuc_te" in thanh[d.id]
    assert thanh[d.id]["thuc_te"]["tong_tot"] == 400.0
    assert thanh[d.id]["thuc_te"]["phan_tram"] == pytest.approx(40.0)
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_xep_lich_2_thuc_te.py::test_ban_lam_viec_mang_theo_lop_thuc_te -q
```

Kỳ vọng: FAIL với `KeyError: 'thuc_te'` (hoặc `assert "thuc_te" in ...`).

- [ ] **Step 3: Sửa `service.py`**

Thêm import ở đầu file (cạnh các import `xep_lich_2` khác):

```python
from .thuc_te import nap_thuc_te
```

Đổi chữ ký `_dong_view` để nhận thêm map (giữ mặc định `None` để mọi chỗ gọi cũ không vỡ) và thêm khoá cuối dict trả về:

```python
    def _dong_view(self, r, nhan, tt: dict[int, dict] | None = None) -> dict:
        ...
        return {
            ...  # giữ nguyên 20 khoá đang có
            # Lớp THỰC TẾ — CHỈ ĐỌC, không bao giờ dời thanh (spec-thuc-te-vs-ke-hoach §2.1).
            # None = chưa phát hành / phát hành phiên bản khác ⇒ FE vẽ thanh trơn như trước.
            "thuc_te": (tt or {}).get(r.id),
        }
```

Trong `workspace()`, sau khi đã có `da_xep` + `nhap` và trước khi dựng `dong`:

```python
        nhan = self._nap_nhan(da_xep + nhap)
        # Nạp GỘP một lượt cho cả bàn — cùng lý do `_nap_nhan` tồn tại: bàn vài trăm thanh.
        tt = nap_thuc_te(self.repo.db, da_xep + nhap)
        dong = [self._dong_view(r, nhan, tt) for r in da_xep] + \
               [self._dong_view(r, nhan, tt) for r in nhap]
```

> Nếu `self.repo` không phơi `.db`, dùng session mà service đang giữ (`self.db`). Kiểm bằng `grep -n "self.db\|self.repo.db" backend/app/services/xep_lich_2/service.py` rồi dùng đúng cái đang có.

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_xep_lich_2_thuc_te.py tests/test_xep_lich_2.py -q
```

Kỳ vọng: tất cả pass (test cũ của `test_xep_lich_2.py` không được đỏ — `_dong_view` thêm khoá chứ không bỏ khoá nào).

- [ ] **Step 5: Khai kiểu ở FE**

Trong `frontend/src/api/client.ts`, ngay TRƯỚC `export interface Xl2Dong`:

```typescript
/** Lớp THỰC TẾ đè lên thanh Gantt — CHỈ ĐỌC. null khi bước chưa phát hành xuống tổ. */
export interface Xl2ThucTe {
  cong_viec_id: number;
  /** "released" | "running" | "paused" | "completed" (CV_* của model). */
  trang_thai: string;
  bat_dau_thuc: string | null;
  ket_thuc_thuc: string | null;
  tong_tot: number;
  tong_hong: number;
  /** Mục tiêu của BƯỚC (`san_xuat_cong_viec.so_luong_ra`), theo `don_vi`. */
  muc_tieu: number | null;
  don_vi: string | null;
  con_thieu: number | null;
  /** 0–100+; null khi bước không khai mục tiêu. */
  phan_tram: number | null;
  tre_bat_dau_phut: number | null;
  tre_ket_thuc_phut: number | null;
}
```

Và thêm trường cuối `Xl2Dong`:

```typescript
  /** Tiến độ THẬT của bước (spec-thuc-te-vs-ke-hoach §2.1). null = chưa phát hành. */
  thuc_te: Xl2ThucTe | null;
```

- [ ] **Step 6: Kiểm kiểu FE**

```bash
cd frontend && npx tsc --noEmit
```

Kỳ vọng: 0 lỗi.

- [ ] **Step 7: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/xep_lich_2/service.py backend/tests/test_xep_lich_2_thuc_te.py frontend/src/api/client.ts
git commit -m "Xếp lịch 2: thanh Gantt mang theo tiến độ thật"
```

---

### Task 3: Bộ dò thứ 13 — lệch thực tế

**Files:**
- Modify: `backend/app/services/xep_lich_van_de_service.py` (hằng ~dòng 60–72, `_build` ~dòng 147)
- Test: `backend/tests/test_xep_lich_van_de.py`

**Interfaces:**
- Consumes: `nap_thuc_te` (Task 1); `rows` của `_build` là output `self.xl.danh_sach()["items"]` — **các dict này đã có `id`, `lsx_id`, `bai_ghep_id`, `lsx_ma`, `cong_doan_ten`, `may_id`**, nhưng phải kiểm chúng có `lsx_cong_doan_id`/`bai_ghep_cong_doan_id` chưa; nếu chưa thì bổ sung hai khoá đó vào `danh_sach()` trước (một dòng mỗi khoá) — đó là điều kiện để `_neo()` hoạt động.
- Produces: issue dict `{"issue_key": f"lech_thuc_te:{dong_id}", "category": CAT_HAN, "severity": SEV_LUU_Y, "title", "nguyen_nhan", "impacts", "delay_phut", "group_key"}`.

- [ ] **Step 1: Viết test thất bại trước**

Thêm vào `backend/tests/test_xep_lich_van_de.py`:

```python
def test_lech_thuc_te_bat_dau_muon_thi_bao_luu_y(db, orders, lsx_svc, admin, customer):
    """Tổ vào việc muộn hơn 1 tiếng so với kế hoạch ⇒ có vấn đề `lech_thuc_te`, mức Nên xem.

    KHÔNG BAO GIỜ là mức Chặn: lệnh đã phát hành rồi mới có thực tế — chặn ở đây là chặn muộn.
    """
    from datetime import timedelta, timezone as _tz

    from app.models.san_xuat import CV_DANG_CHAY, SanXuatPhienChay
    from app.services.xep_lich_van_de_service import (
        CAT_HAN, K_LECH_THUC_TE, SEV_LUU_Y,
    )

    dong, cv = _dong_va_cong_viec(db, orders, lsx_svc, admin, customer)  # helper của file này
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = dong.start_at
    cv.du_kien_ket_thuc = dong.finish_at
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1,
                            bat_dau=dong.start_at + timedelta(hours=3)))
    db.commit()

    svc = _van_de_svc(db)  # helper của file này
    items = svc.liet_ke()["items"]
    it = next(i for i in items if i["issue_key"] == f"{K_LECH_THUC_TE}:{dong.id}")
    assert it["severity"] == SEV_LUU_Y
    assert it["category"] == CAT_HAN
    assert it["delay_phut"] == 180
    assert "muộn" in it["nguyen_nhan"]


def test_lech_thuc_te_dung_gio_thi_im_lang(db, orders, lsx_svc, admin, customer):
    from datetime import timedelta

    from app.models.san_xuat import CV_DANG_CHAY, SanXuatPhienChay
    from app.services.xep_lich_van_de_service import K_LECH_THUC_TE

    dong, cv = _dong_va_cong_viec(db, orders, lsx_svc, admin, customer)
    cv.trang_thai = CV_DANG_CHAY
    cv.du_kien_bat_dau = dong.start_at
    cv.du_kien_ket_thuc = dong.finish_at
    db.add(SanXuatPhienChay(cong_viec_id=cv.id, so_thu_tu=1,
                            bat_dau=dong.start_at + timedelta(minutes=15)))
    db.commit()

    keys = {i["issue_key"] for i in _van_de_svc(db).liet_ke()["items"]}
    assert f"{K_LECH_THUC_TE}:{dong.id}" not in keys
```

> Hai helper `_dong_va_cong_viec` và `_van_de_svc` phải viết trong chính file test này nếu chưa có; đọc đầu file `test_xep_lich_van_de.py` để dùng lại đúng fixture đang có ở đó thay vì dựng bộ mới.

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_xep_lich_van_de.py -q -k lech_thuc_te
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'K_LECH_THUC_TE'`.

- [ ] **Step 3: Thêm hằng + bộ dò**

Trong `backend/app/services/xep_lich_van_de_service.py`, thêm sau `K_QUA_TAI_TO`:

```python
K_LECH_THUC_TE = "lech_thuc_te"               # J: tổ chạy lệch mốc kế hoạch (vào muộn / quá giờ)

# Lệch bao nhiêu phút thì mới đáng nói. Dưới ngưỡng là nhiễu: ca sản xuất vốn xê dịch 15–30 phút
# vì bàn giao ca, vệ sinh máy, chờ pallet. Báo mọi lệch = người điều độ tắt hẳn hàng đèn.
NGUONG_LECH_THUC_TE_PHUT = 60
```

Thêm phương thức (đặt cạnh `_nguy_co_tre` cho dễ đọc):

```python
    def _lech_thuc_te(self, rows: list[dict]) -> list[dict]:
        """Thực tế ở xưởng lệch mốc đã xếp — CHỈ BÁO, không tự dời lịch.

        Mức luôn Nên xem. Lệnh đã phát hành mới có thực tế, nên chặn ở đây không cứu được gì; việc
        của điều độ là biết mà kéo lại tay (spec-thuc-te-vs-ke-hoach §2.2).
        """
        from .xep_lich_2.thuc_te import nap_thuc_te

        tt = nap_thuc_te(self.db, rows)
        out: list[dict] = []
        for r in rows:
            t = tt.get(r["id"])
            if not t:
                continue
            tre_bd = t["tre_bat_dau_phut"] or 0
            # Quá giờ chỉ tính khi việc CHƯA đóng — việc đã xong muộn là chuyện đã rồi, nó đã
            # phản ánh vào mốc bắt đầu của bước sau; báo hai lần là nhân đôi cùng một cái trễ.
            tre_kt = (t["tre_ket_thuc_phut"] or 0) if t["ket_thuc_thuc"] is None else 0
            if max(tre_bd, tre_kt) < NGUONG_LECH_THUC_TE_PHUT:
                continue
            if tre_kt >= tre_bd:
                txt = f"quá giờ dự kiến {_gio(tre_kt)}"
                ly_do = f"Bước vẫn đang chạy và đã quá mốc kết thúc dự kiến {_gio(tre_kt)}."
            else:
                txt = f"vào việc muộn {_gio(tre_bd)}"
                ly_do = f"Tổ bắt đầu muộn hơn mốc đã xếp {_gio(tre_bd)}."
            ma = r.get("lsx_ma") or r.get("bai_ghep_ma") or f"#{r['id']}"
            out.append({
                "issue_key": f"{K_LECH_THUC_TE}:{r['id']}",
                "category": CAT_HAN, "severity": SEV_LUU_Y,
                "title": f"{ma} · {r.get('cong_doan_ten') or 'bước'}: {txt}",
                "nguyen_nhan": ly_do,
                "impacts": self._impact([r]),
                "delay_phut": max(tre_bd, tre_kt),
                "group_key": (f"lsx:{r['lsx_id']}" if r.get("lsx_id")
                              else f"bai_ghep:{r.get('bai_ghep_id')}"),
            })
        return out
```

Và hàm phụ đặt cạnh `_fmt` ở đầu module:

```python
def _gio(phut: int) -> str:
    """Phút → '3g20' / '45ph' — đọc nhanh hơn '200 phút' trong tiêu đề vấn đề."""
    if phut < 60:
        return f"{phut}ph"
    g, p = divmod(phut, 60)
    return f"{g}g{p:02d}" if p else f"{g}g"
```

Cuối cùng nối vào `_build`, ngay sau `_thieu_vat_tu`:

```python
        issues += self._thieu_vat_tu(rows)
        issues += self._lech_thuc_te(rows)
```

> `self.db` phải tồn tại trên service. Kiểm bằng `grep -n "def __init__" -A 8 backend/app/services/xep_lich_van_de_service.py`; nếu service giữ session dưới tên khác thì dùng đúng tên đó.

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_xep_lich_van_de.py -q
```

Kỳ vọng: toàn bộ file pass (12 bộ dò cũ + 2 test mới).

- [ ] **Step 5: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/xep_lich_van_de_service.py backend/tests/test_xep_lich_van_de.py
git commit -m "Xếp lịch: bộ dò lệch thực tế (vào muộn / quá giờ), mức Nên xem"
```

---

### Task 4: Vẽ lớp thực tế lên thanh Gantt

**Files:**
- Modify: `frontend/src/pages/Xl2Gantt.tsx` (~dòng 736–825, trong callback dựng từng thanh)
- Modify: `frontend/src/pages/xep-lich-2.css`

**Interfaces:**
- Consumes: `Xl2Dong.thuc_te: Xl2ThucTe | null` (Task 2).
- Produces: không có API mới. Class CSS mới: `.xl2-bar__thuc-te`, `.xl2-bar__qua-gio`.

- [ ] **Step 1: Tính hai chỉ số ngay cạnh `setupPx` / `slackPx`**

Trong `Xl2Gantt.tsx`, ngay sau khối tính `slackPx`, thêm:

```tsx
                      // ── LỚP THỰC TẾ (spec-thuc-te-vs-ke-hoach §2.1) ────────────────────────
                      // Vẽ NẰM TRONG thanh, cùng ngôn ngữ hình với `__setup` / `__slack` — không
                      // treo râu dưới thanh (râu dưới trên màn này chỉ có một nghĩa: phụ thuộc).
                      const tt = dong.thuc_te;
                      const tienDoPx = timed && tt && tt.phan_tram != null
                        ? Math.min(Math.max(tt.phan_tram, 0), 100) / 100 * inner
                        : 0;
                      // Đuôi sọc: đang chạy mà đã quá mốc kết thúc dự kiến. Chỉ vẽ khi CHƯA đóng —
                      // việc đã xong muộn thì cái trễ đã nằm ở thanh sau, vẽ nữa là đếm hai lần.
                      const quaGio = !!tt && tt.ket_thuc_thuc == null
                        && (tt.tre_ket_thuc_phut ?? 0) >= 60;
                      const ttTitle = tt
                        ? ` · thực tế: ${tt.tong_tot}${tt.don_vi ? ` ${tt.don_vi}` : ""}`
                          + (tt.muc_tieu != null ? `/${tt.muc_tieu}` : "")
                          + (tt.con_thieu ? ` · còn thiếu ${tt.con_thieu}` : "")
                          + ((tt.tre_bat_dau_phut ?? 0) >= 60 ? ` · vào muộn ${tt.tre_bat_dau_phut}ph` : "")
                          + (quaGio ? ` · quá giờ ${tt.tre_ket_thuc_phut}ph` : "")
                        : "";
```

- [ ] **Step 2: Nối `ttTitle` vào tooltip và vẽ hai lớp**

Sửa thuộc tính `title` của `<button className={...xl2-bar...}>`: thêm `${ttTitle}` ngay sau `${btTitle}`.

Thêm class vào chuỗi `className` của cùng nút đó: `${quaGio ? " xl2-bar--qua-gio" : ""}`.

Thêm hai phần tử ngay SAU `<span className="xl2-bar__accent" />`, TRƯỚC khối `setupPx`:

```tsx
                          {/* Vệt tiến độ thật: nền mờ chạy từ mép trái, KHÔNG đè chữ. */}
                          {tienDoPx > 0 && tt && (
                            <span
                              className="xl2-bar__thuc-te"
                              style={{ width: tienDoPx }}
                              title={`Đã chạy ${tt.phan_tram}%`}
                              aria-hidden="true"
                            />
                          )}
                          {/* Đuôi sọc "còn đang chạy quá giờ" — mọc ra ngoài mép phải. */}
                          {quaGio && (
                            <span className="xl2-bar__qua-gio" aria-hidden="true" />
                          )}
```

- [ ] **Step 3: Thêm CSS**

Vào `frontend/src/pages/xep-lich-2.css`, cạnh khối `.xl2-bar__setup`:

```css
/* Lớp THỰC TẾ đè lên thanh kế hoạch — nền mờ, nằm DƯỚI chữ (z-index thấp hơn __body). */
.xl2-bar__thuc-te {
  position: absolute;
  inset-block: 0;
  inset-inline-start: 4px; /* chừa dải accent mép trái */
  background: color-mix(in srgb, var(--xl2-thuc-te, #22c55e) 26%, transparent);
  border-inline-end: 1px solid color-mix(in srgb, var(--xl2-thuc-te, #22c55e) 70%, transparent);
  pointer-events: none;
}

/* Đang chạy mà đã quá mốc kết thúc: đuôi sọc mọc ra ngoài mép phải thanh. */
.xl2-bar__qua-gio {
  position: absolute;
  inset-block: 25%;
  inset-inline-end: -14px;
  inline-size: 14px;
  background: repeating-linear-gradient(
    135deg,
    var(--xl2-tre, #ef4444) 0 3px,
    transparent 3px 6px
  );
  pointer-events: none;
}

.xl2-bar--qua-gio { outline: 1px solid color-mix(in srgb, var(--xl2-tre, #ef4444) 55%, transparent); }
```

> Trước khi thêm: `grep -c "\.xl2-bar__setup" frontend/src/pages/xep-lich-2.css`. Nếu ra > 1 thì file đã bị nhân đôi selector — sửa chuyện đó trước, không thì CSS mới "không ăn" mà không rõ vì sao.

- [ ] **Step 4: Kiểm kiểu + dựng**

```bash
cd frontend && npx tsc --noEmit
```

Kỳ vọng: 0 lỗi.

> CSS đổi mà trình duyệt không nhận: chạm mtime file (`touch frontend/src/pages/xep-lich-2.css`) — vite giữ transform rỗng trong cache, không cần restart.

- [ ] **Step 5: Commit** *(chỉ khi được yêu cầu)*

```bash
git add frontend/src/pages/Xl2Gantt.tsx frontend/src/pages/xep-lich-2.css
git commit -m "Xếp lịch 2: vẽ tiến độ thật và đuôi quá giờ lên thanh Gantt"
```

---

### Task 5: Con số "còn thiếu" ở công đoạn và ở nhóm thành phẩm

**Files:**
- Modify: `backend/app/services/san_xuat/board.py` (`_work_item`, khối `"san_luong"` của chi tiết)
- Modify: `backend/app/services/san_xuat/dong_nhom.py` (`dieu_kien_dong_nhom`)
- Modify: `backend/app/schemas/san_xuat.py` (`SanLuongOut`, `WorkItemOut`)
- Test: `backend/tests/test_san_xuat_con_thieu.py`

**Interfaces:**
- Consumes: `SanXuatSanLuongRepository.tong_tot(cong_viec_id) -> float`; `SanXuatCongViec.so_luong_ra`, `.don_vi_ra`, `.la_kcs_cuoi`.
- Produces:
  - `_work_item(...)["con_thieu"]: float | None`
  - chi tiết công việc: `san_luong["muc_tieu"]`, `san_luong["con_thieu"]`, `san_luong["don_vi"]`
  - `dieu_kien_dong_nhom(...)` trả thêm `"muc_tieu": float | None, "da_dat": float, "con_thieu": float | None`

- [ ] **Step 1: Viết test thất bại trước**

Tạo `backend/tests/test_san_xuat_con_thieu.py`:

```python
"""Con số CÒN THIẾU — dẫn xuất, chỉ để BÀY (docs/spec-thuc-te-vs-ke-hoach.md §2.3).

Cổng đóng nhóm KHÔNG đổi: `dong_nhom._danh_gia` vẫn đo "đã phân loại / đã nhận", cố ý không so
mục tiêu đơn (chú thích dòng 63 của module đó). Test dưới đây chốt đúng hai điều:
  · số còn thiếu XUẤT HIỆN ở bước và ở nhóm;
  · nó KHÔNG làm nhóm mất quyền đóng.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.san_xuat import CV_DANG_CHAY
from app.models.san_xuat_san_luong import SanXuatBatch
from app.services.san_xuat import dong_nhom

from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _mot_cv, _to_khoan, admin, customer, db, lsx_svc, orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _authz(db):
    """`chi_tiet_cong_viec` đòi `AuthorizationService` để lọc phạm vi tổ được xem.

    Dựng đúng như `deps.get_authorization_service` (`backend/app/deps.py:190`): nó nhận
    `RoleRepository`, KHÔNG nhận `Session`. Đừng truyền `None` — hàm gọi thẳng
    `_to_thay_duoc(db, user, authz)`, `None` sẽ nổ ở chỗ khác và che mất lỗi thật.
    """
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def test_buoc_chay_thieu_thi_con_thieu_bang_hieu(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT1")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "tờ"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=9400, tot=9400, hong=0))
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["muc_tieu"] == 10000.0
    assert ct["san_luong"]["con_thieu"] == 600.0
    assert ct["san_luong"]["don_vi"] == "tờ"


def test_chay_du_thi_con_thieu_bang_khong(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT2")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_ra = 500
    cv.don_vi_ra = "tờ"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
                        tong=520, tot=520, hong=0))
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["con_thieu"] == 0.0   # chạy dư KHÔNG ra số âm


def test_buoc_khong_khai_muc_tieu_thi_khong_bia_so(db, orders, lsx_svc, admin, customer):
    from app.services.san_xuat import board

    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT3")
    cv.trang_thai = CV_DANG_CHAY
    cv.so_luong_ra = None
    db.commit()

    ct = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    assert ct["san_luong"]["muc_tieu"] is None
    assert ct["san_luong"]["con_thieu"] is None
```

> Hàm chi tiết là `board.chi_tiet_cong_viec(db, user, authz, *, cong_viec_id)`
> (`backend/app/services/san_xuat/board.py:226`) — nó tự dựng repo bên trong, đừng truyền repo vào.
> `AuthorizationService` nằm ở `backend/app/services/rbac_service.py:127` và nhận `RoleRepository`,
> không nhận `Session`; `RoleRepository` ở `backend/app/repositories/rbac_repo.py:274`.

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_san_xuat_con_thieu.py -q
```

Kỳ vọng: FAIL — `KeyError: 'muc_tieu'`.

- [ ] **Step 3: Thêm số dẫn xuất vào `board.py`**

Trong khối `"san_luong"` của hàm chi tiết, đổi:

```python
        "san_luong": {
            "tong_tot": sl.tong_tot(cv.id),
            "da_giao": sl.tong_da_giao(cv.id),
            "batches": [...],
        },
```

thành:

```python
        "san_luong": _san_luong_block(sl, cv),
```

và thêm hàm phụ ở đầu module (cạnh `_work_item`):

```python
def _con_thieu(cv, tong_tot: float) -> tuple[float | None, float | None]:
    """(mục tiêu, còn thiếu) của MỘT bước — dẫn xuất, KHÔNG lưu cột.

    Mục tiêu là `so_luong_ra` (snapshot lúc phát hành, đã đúng `don_vi_ra`), nên số này so được
    thẳng với `tong_tot` mà không cần quy đổi. Bước không khai mục tiêu ⇒ trả None, đừng bịa 0:
    "còn thiếu 0" và "không biết thiếu bao nhiêu" là hai câu khác hẳn nhau.

    Chạy DƯ thì kẹp về 0 — số âm ở ô "còn thiếu" chỉ làm người đọc dừng lại đoán nghĩa.
    """
    if cv.so_luong_ra is None:
        return None, None
    muc_tieu = float(cv.so_luong_ra)
    return muc_tieu, max(muc_tieu - float(tong_tot), 0.0)


def _san_luong_block(sl, cv) -> dict:
    tot = sl.tong_tot(cv.id)
    muc_tieu, con_thieu = _con_thieu(cv, tot)
    return {
        "tong_tot": tot,
        "da_giao": sl.tong_da_giao(cv.id),
        "muc_tieu": muc_tieu,
        "con_thieu": con_thieu,
        "don_vi": cv.don_vi_ra,
        "batches": _batches_block(sl, cv),   # giữ NGUYÊN biểu thức list đang có, cắt ra hàm
    }
```

> Giữ nguyên nội dung list `batches` hiện tại — chỉ cắt nó thành `_batches_block(sl, cv)` để khối
> trên đọc được. Đừng đổi một khoá nào của phần tử batch.

Trong `_work_item(...)`, thêm hai khoá (nó đã có `sl` trong tầm với; nếu chưa, truyền vào một map
`tong_tot` nạp gộp thay vì gọi từng dòng — bàn tổ có thể có hàng chục công việc):

```python
        "muc_tieu_ra": float(cv.so_luong_ra) if cv.so_luong_ra is not None else None,
        "con_thieu": con_thieu_map.get(cv.id),
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_san_xuat_con_thieu.py tests/test_san_xuat_board.py -q
```

Kỳ vọng: pass hết. `test_san_xuat_board.py` không được đỏ.

- [ ] **Step 5: Khai schema (BẮT BUỘC — router này CÓ `response_model`)**

Trong `backend/app/schemas/san_xuat.py`, thêm vào `SanLuongOut`:

```python
    # Mục tiêu của BƯỚC (`san_xuat_cong_viec.so_luong_ra`) và phần chưa đạt — DẪN XUẤT, không lưu.
    # Không khai ở đây là Pydantic nuốt IM LẶNG: service trả dict, FE nhận undefined, không ai lỗi.
    muc_tieu: float | None = None
    con_thieu: float | None = None
    don_vi: str | None = None
```

và vào `WorkItemOut`:

```python
    muc_tieu_ra: float | None = None
    con_thieu: float | None = None
```

- [ ] **Step 6: Số của NHÓM thành phẩm**

Thêm test vào `backend/tests/test_san_xuat_con_thieu.py`:

```python
def test_nhom_van_du_dong_du_khi_chay_thieu_nhung_co_so_con_thieu(
    db, orders, lsx_svc, admin, customer,
):
    """Chốt hai vế cùng lúc: con số hiện ra, và cổng đóng nhóm KHÔNG đổi vì nó."""
    _to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-CT4")
    cv.trang_thai = CV_DANG_CHAY
    cv.la_kcs_cuoi = True
    cv.so_luong_ra = 10000
    cv.don_vi_ra = "cuốn"
    db.add(SanXuatBatch(cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=2),
                        tong=9400, tot=9400, hong=0))
    db.commit()

    dk = dong_nhom.dieu_kien_dong_nhom(db, nhom_id=cv.nhom_id)
    assert dk["muc_tieu"] == 10000.0
    assert dk["da_dat"] == 9400.0
    assert dk["con_thieu"] == 600.0
    # 6 điều kiện cũ còn nguyên — số còn thiếu KHÔNG phải điều kiện thứ 7.
    assert "con_thieu" not in dk.get("dieu_kien", {})
```

Trong `dong_nhom.py`, cuối `dieu_kien_dong_nhom` (KHÔNG đụng `_danh_gia`):

```python
    # Con số CÒN THIẾU của cả nhóm — CHỈ ĐỂ BÀY (spec-thuc-te-vs-ke-hoach §2.3).
    # `_danh_gia` vẫn giữ nguyên 6 điều kiện: nó đo "đã phân loại / đã nhận", CỐ Ý không so mục
    # tiêu đơn (chú thích dòng 63). Người bấm "đóng thiếu" trước đây bấm mù — nay thấy thiếu bao
    # nhiêu, nhưng quyền đóng không đổi.
    kcs_cuoi = [c for c in cong_viecs if c.la_kcs_cuoi and c.so_luong_ra is not None]
    muc_tieu = sum(float(c.so_luong_ra) for c in kcs_cuoi) if kcs_cuoi else None
    da_dat = sum(sl.tong_tot(c.id) for c in kcs_cuoi) if kcs_cuoi else 0.0
    ra["muc_tieu"] = muc_tieu
    ra["da_dat"] = da_dat
    ra["con_thieu"] = max(muc_tieu - da_dat, 0.0) if muc_tieu is not None else None
    return ra
```

> Tên biến `cong_viecs` / `sl` / `ra` phải khớp cái đang có trong hàm — đọc hàm trước khi chèn.

- [ ] **Step 7: Chạy test để chắc chắn nó XANH**

```bash
cd backend && python -m pytest tests/test_san_xuat_con_thieu.py tests/test_san_xuat_dong_nhom.py -q
```

Kỳ vọng: pass hết; `test_san_xuat_dong_nhom.py` không đỏ (cổng đóng không đổi).

- [ ] **Step 8: Commit** *(chỉ khi được yêu cầu)*

```bash
git add backend/app/services/san_xuat/board.py backend/app/services/san_xuat/dong_nhom.py backend/app/schemas/san_xuat.py backend/tests/test_san_xuat_con_thieu.py
git commit -m "Sản xuất: con số còn thiếu ở bước và ở nhóm (dẫn xuất, không đổi cổng đóng)"
```

---

### Task 6: Hiện "còn thiếu" ở drawer công đoạn

**Files:**
- Modify: `frontend/src/api/client.ts` (`SxSanLuong`, `SxWorkItem`)
- Modify: `frontend/src/pages/ThsxExecPanels.tsx` (khối Sản lượng)

**Interfaces:**
- Consumes: `san_luong.muc_tieu`, `san_luong.con_thieu`, `san_luong.don_vi` (Task 5).
- Produces: không có API mới.

- [ ] **Step 1: Khai kiểu**

Trong `frontend/src/api/client.ts`, thêm vào interface sản lượng của work-item (tìm bằng
`grep -n "tong_tot" frontend/src/api/client.ts`):

```typescript
  /** Mục tiêu của bước (`so_luong_ra` lúc phát hành) — null khi bước không khai. */
  muc_tieu: number | null;
  /** max(mục tiêu − tổng tốt, 0). null khi không có mục tiêu — KHÁC hẳn với 0. */
  con_thieu: number | null;
  don_vi: string | null;
```

và vào interface work-item:

```typescript
  muc_tieu_ra: number | null;
  con_thieu: number | null;
```

- [ ] **Step 2: Vẽ con số**

Trong `ThsxExecPanels.tsx`, ở khối tiêu đề phần Sản lượng, thêm ngay sau tổng tốt:

```tsx
        {sl.muc_tieu != null && (
          <span className={sl.con_thieu ? "thsx-x-pill thsx-x-pill--warn" : "thsx-x-pill"}>
            {sl.con_thieu
              ? `còn thiếu ${sl.con_thieu.toLocaleString("vi-VN")}${sl.don_vi ? ` ${sl.don_vi}` : ""}`
              : "đủ mục tiêu"}
          </span>
        )}
```

- [ ] **Step 3: Kiểm kiểu**

```bash
cd frontend && npx tsc --noEmit
```

Kỳ vọng: 0 lỗi.

- [ ] **Step 4: Commit** *(chỉ khi được yêu cầu)*

```bash
git add frontend/src/api/client.ts frontend/src/pages/ThsxExecPanels.tsx
git commit -m "Thực hiện SX: drawer công đoạn hiện số còn thiếu so với mục tiêu bước"
```

---

### Task 7: Nghiệm thu bằng dev-browser (BẮT BUỘC — luồng có UI)

**Files:** không sửa file nào. Đây là bước xác minh.

**Interfaces:** Consumes toàn bộ Task 1–6.

- [ ] **Step 1: Restart backend**

Sửa route/schema BE ⇒ phải restart uvicorn (repo này không hot-reload đáng tin). Đẻ tiến trình
qua WMI (`Win32_Process.Create`) — Bash nền và `Start-Process` đều chết khi hết phiên.
BE `127.0.0.1:8000`, FE `localhost:5173`.

- [ ] **Step 2: Đăng nhập**

`admin` / `admin123`. Ô input React phải set qua native setter khi gõ bằng script; gõ bằng bàn
phím thật thì không cần.

- [ ] **Step 3: Dựng dữ liệu THẬT bằng chuột — không dùng API**

Vào Thực hiện sản xuất, mở một công việc đã phát hành, bấm **Bắt đầu**, ghi một mẻ sản lượng
**ít hơn** mục tiêu (vd mục tiêu 10.000, ghi tốt 9.400). Ghi lại chính xác đã bấm nút nào.

- [ ] **Step 4: Kiểm 4 điểm hiển thị**

1. Drawer công đoạn: chip **"còn thiếu 600 …"** hiện đúng.
2. Xếp lịch 2 → bàn Gantt: thanh của đúng bước có **vệt tiến độ** phủ ~94% và tooltip đọc được
   "thực tế: 9400/10000 · còn thiếu 600".
3. Để việc chạy quá mốc kết thúc dự kiến (hoặc chỉnh `du_kien_ket_thuc` về quá khứ qua màn xếp
   lịch bằng chuột) → thanh mọc **đuôi sọc đỏ**.
4. Danh sách Xung đột & Nguy cơ: có dòng **"… quá giờ dự kiến …"** ở mức **Nên xem** (không phải
   Chặn), và **nút phát hành vẫn bấm được**.

- [ ] **Step 5: Kiểm cổng đóng nhóm KHÔNG đổi**

Đóng nhóm thành phẩm như trước: các điều kiện hiển thị vẫn đúng 6 mục, và con số còn thiếu chỉ
nằm cạnh chứ không biến thành điều kiện chặn.

- [ ] **Step 6: Báo cáo**

Liệt kê CỤ THỂ từng bước: đã bấm nút nào, gõ số gì, thấy gì. Nếu có bất kỳ đoạn nào phải tắt qua
API thay vì UI, **nói rõ ngay trong báo cáo**, đừng đợi bị hỏi.

---

## Self-Review

**1. Spec coverage**

| Yêu cầu spec | Task |
| --- | --- |
| §1.1 người lập KH mù trước thực tế | Task 1, 2, 4 |
| §1.2 không có con số còn thiếu | Task 5, 6 |
| §1.3 không tách được lần chạy | **Không thuộc plan này** — xem `2026-08-31-tach-lan-chay-cong-doan.md` |
| §2.1 lớp thực tế CHỈ ĐỌC, nối bằng cặp neo, nạp gộp | Task 1 (Step 3), Task 2 (Step 3) |
| §2.1 chỉ lấy phiên bản gói đang hiệu lực | Task 1 Step 3 (`order_by(phien_ban_so)` + đè) |
| §2.2 bộ dò thứ 13, luôn `SEV_LUU_Y`, ngưỡng 60 phút, `delay_phut` | Task 3 |
| §2.3 còn thiếu = dẫn xuất, không cột mới, không đổi cổng đóng | Task 5 (Step 3, 6) + test Step 6 |
| §3 không tự dời lịch | Global Constraints + Task 4 (chỉ vẽ) |

**2. Placeholder scan** — mọi bước code đều có code thật. Ba chỗ cố ý là *chỉ dẫn kiểm tra tại chỗ*
chứ không phải placeholder: tên session của `XepLich2Service` (Task 2 Step 3), tên session của
`XepLichVanDeService` (Task 3 Step 3), tên hàm chi tiết + tên biến trong `board.py`/`dong_nhom.py`
(Task 5). Mỗi chỗ đều kèm lệnh `grep` để tự xác định trong 10 giây.

**3. Type consistency** — `nap_thuc_te(db, rows, *, bay_gio=None)` dùng nhất quán ở Task 1 (định
nghĩa), Task 2 Step 3 (`nap_thuc_te(self.repo.db, da_xep + nhap)`), Task 3 Step 3
(`nap_thuc_te(self.db, rows)`). Khoá dict `tre_bat_dau_phut` / `tre_ket_thuc_phut` /
`ket_thuc_thuc` / `phan_tram` / `con_thieu` khớp giữa Python (Task 1), bộ dò (Task 3) và TS
`Xl2ThucTe` (Task 2 Step 5) và chỗ dùng (Task 4 Step 1). `muc_tieu`/`con_thieu`/`don_vi` khớp giữa
`_san_luong_block` (Task 5 Step 3), `SanLuongOut` (Task 5 Step 5) và `SxSanLuong` (Task 6 Step 1).

**Điều kiện tiên quyết của Task 3** — `rows` của `_build` phải mang `lsx_cong_doan_id` và
`bai_ghep_cong_doan_id`. Kiểm bằng `grep -n "lsx_cong_doan_id" backend/app/services/xep_lich_service.py`
trong hàm dựng `items`; nếu thiếu, thêm hai khoá đó vào dict dòng trước khi làm Task 3 — đây là
thay đổi một dòng, không phải task riêng.

## Scope Check

`docs/spec-thuc-te-vs-ke-hoach.md` mô tả ba lỗ hổng. Lỗ hổng §1.3 (tách lần chạy) đụng cấu trúc
`xep_lich_cong_doan` + `snapshot.dung_cong_viec` + `dung_phu_thuoc` — nó **không** chạy được chung
một plan với hai lỗ hổng kia và tự nó đã là một hệ thống hoàn chỉnh. Đã tách thành
`docs/superpowers/plans/2026-08-31-tach-lan-chay-cong-doan.md`.

Plan này đứng một mình được: xong Task 1–7 là người điều độ đã nhìn thấy thực tế và số còn thiếu,
không phụ thuộc plan tách lần chạy.
