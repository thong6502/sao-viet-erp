# Quyền xem chi tiết giá vốn + Nhóm dùng chung Kinh doanh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm một quyền chi tiết gác phần "ruột giá" của màn Tính giá, và một cơ chế "nhóm dùng chung" cho phép vài người ở phạm vi *Của tôi* thấy + sửa dữ liệu của nhau trên đúng bốn màn khối Kinh doanh.

**Architecture:** Quyền mới tái dùng cột `role_permissions.can_view_cost` đã có (module Kho đang dùng) — chỉ khai thêm cho module `tinh_gia_thanh`, không migration. Nhóm dùng chung là hai bảng mới (`nhom_dung_chung`, `nhom_dung_chung_thanh_vien`) cộng một hàm duy nhất trả tập user-id dùng chung; bốn repository của khối Kinh doanh gọi hàm đó ở đúng nhánh `own` của chúng.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (Python), React + TypeScript + Vite, pytest, PostgreSQL (dev/prod) / SQLite in-memory (test).

**Spec:** `docs/superpowers/specs/2026-09-24-quyen-xem-chi-tiet-gia-von-va-nhom-dung-chung-kd-design.md`

## Global Constraints

- **KHÔNG chạy `./init.ps1`.** Verify bằng pytest nhắm đúng file (`python -m pytest backend/tests/<file>.py -v` từ gốc repo) và `npx tsc --noEmit` trong `frontend/`. Muốn chạy cả bộ pytest thì hỏi chủ dự án trước.
- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, không ALTER. Bảng/cột mới phải viết vào `backend/app/db_migrations.py`.
- Migration backfill dùng **raw SQL đích danh cột**, không dùng ORM full-select.
- Cột Boolean: `server_default` phải là `false`/`true` (bool Python), không phải `"0"`/`"1"`.
- Thêm bảng/cột ⇒ cập nhật `docs/DB_SCHEMA.md` **trong cùng thay đổi** (guard `backend/tests/test_schema_documented.py`).
- UI **tiếng Việt**, không chen tiếng Anh.
- Commit message tiếng Việt (thuật ngữ kỹ thuật giữ tiếng Anh), **không** thêm dòng `Co-Authored-By`.
- Sửa route/schema backend ⇒ phải RESTART uvicorn (dev không hot-reload đáng tin).
- Pydantic nuốt field im lặng: thêm/bớt field phải đi hết chuỗi dict → schema → type TS.
- Nhóm dùng chung **chỉ** áp cho `tinh_gia_thanh`, `bao_gia`, `don_hang_ban`, `khach_hang`. Không màn nào khác.
- Nhóm **mở rộng dữ liệu, không nâng quyền**: mọi ô quyền vẫn tính theo vai của người đang thao tác.

## File Structure

**Việc 1 — quyền xem chi tiết giá vốn**

| File | Trách nhiệm |
|---|---|
| `backend/app/routers/phieu_tinh_gia.py` | Gác `view_cost` ở các đường ghi + lộ ruột; GET chi tiết trả bản rút gọn khi thiếu quyền |
| `backend/app/routers/tinh_gia.py` | Gác `view_cost` cho `/binh-bai` và `/preview` |
| `backend/app/schemas/phieu_tinh_gia.py` | Thêm `ThanhPhanRutGonOut` + `PhieuTinhGiaOutRutGon` |
| `backend/app/seed.py` | Vai mẫu: bật `can_view_cost` cho vai có thao tác Tính giá |
| `frontend/src/components/PermissionMatrix.tsx` | Chip "Xem chi tiết giá vốn" ở dòng `tinh_gia_thanh` + luật tự bật theo Thao tác |
| `frontend/src/pages/PhieuTinhGiaDetailView.tsx` | Ẩn bảng chi tiết, chặn mở thẻ sản phẩm, gỡ nút In phiếu |
| `backend/tests/test_quyen_xem_chi_tiet_gia_von.py` | Test mới (tạo) |

**Việc 2 — nhóm dùng chung**

| File | Trách nhiệm |
|---|---|
| `backend/app/models/nhom_dung_chung.py` | Hai model (tạo) |
| `backend/app/models/__init__.py` | Đăng ký model để `create_all` thấy |
| `backend/app/db_migrations.py` | Migration `0333` tạo hai bảng |
| `docs/DB_SCHEMA.md` | Hai section bảng mới |
| `backend/app/repositories/org_scope.py` | Hàm `nhom_dung_chung_user_ids` — nguồn duy nhất |
| `backend/app/repositories/quotation_repo.py`, `order_repo.py`, `customer_repo.py` | Nhánh `own` gọi hàm trên |
| `backend/app/routers/phieu_tinh_gia.py` | `_owner_ids_for_scope` gọi hàm trên |
| `backend/app/repositories/nhom_dung_chung_repo.py` | CRUD nhóm (tạo) |
| `backend/app/schemas/nhom_dung_chung.py` | Schema vào/ra (tạo) |
| `backend/app/routers/nhom_dung_chung.py` | API, gác `phong_ban:manage_permissions` (tạo) |
| `backend/app/main.py` | Mount router |
| `frontend/src/api/client.ts` | 5 hàm gọi API nhóm |
| `frontend/src/pages/nhan-su-luong/phong-ban/NhomDungChungModal.tsx` | Hộp thoại gộp/sửa nhóm (tạo — KHÔNG nhét vào `DepartmentsPage.tsx` đang 3157 dòng) |
| `frontend/src/pages/nhan-su-luong/phong-ban/DepartmentsPage.tsx` | Nút "Gộp nhóm dùng chung — Kinh doanh" + chip tên nhóm |
| `backend/tests/test_nhom_dung_chung_kd.py` | Test mới (tạo) |

---

### Task 1: Chặn ở máy chủ các đường lộ ruột giá của Tính giá

**Files:**
- Modify: `backend/app/routers/phieu_tinh_gia.py:311` (POST), `:355` (GET san-pham-tai-ban/{id}), `:343` (GET san-pham-tai-ban), `:388` (PUT)
- Modify: `backend/app/routers/tinh_gia.py:49` (POST binh-bai), `:73` (POST preview)
- Test: `backend/tests/test_quyen_xem_chi_tiet_gia_von.py` (tạo)

**Interfaces:**
- Consumes: `require_permission(module_key, action)` từ `backend/app/deps.py`; action key `"view_cost"` đã có trong `rbac_service.ACTION_VIEW_COST`.
- Produces: các đường trên trả 403 khi vai thiếu `can_view_cost` trên `tinh_gia_thanh`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_quyen_xem_chi_tiet_gia_von.py`. Dựng user theo đúng khuôn của `backend/tests/test_fine_permissions_api.py` (hàm `_user_with_role`) — chép nguyên hàm đó sang file mới, đừng import chéo giữa hai file test.

```python
"""Quyền chi tiết `tinh_gia_thanh:view_cost` — gác RUỘT GIÁ của màn Tính giá.

Vai có Xem (và cả vai có Sửa) nhưng THIẾU `can_view_cost` thì:
  - không gọi được các đường bày cấu hình sản phẩm / bình bài / preview,
  - GET chi tiết phiếu không còn phần diễn giải.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

MODULE = "tinh_gia_thanh"


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _user_with_role(username: str, module_key: str, **perm) -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        depts = DepartmentRepository(db)
        roles = RoleRepository(db)
        kd = depts.get_by_name("Kinh doanh")
        role_name = f"role-{username}"
        role = roles.get_by_name_and_department(role_name, kd.id)
        if role is None:
            role = roles.create(name=role_name, department_id=kd.id)
        roles.set_permission(role_id=role.id, module_key=module_key, scope=SCOPE_ALL, **perm)
        u = users.get_by_username(username)
        if u is None:
            u = users.create(
                username=username, name=username, password_hash=hash_password("x")
            )
        u.department_id = kd.id
        u.role_id = role.id
        db.commit()
        return create_access_token(subject=u.username)
    finally:
        db.close()


def test_thieu_view_cost_khong_binh_bai_duoc(client):
    token = _user_with_role("kd_khong_ruot", MODULE, can_read=True)
    r = client.post(
        "/api/tinh-gia/binh-bai",
        headers=_h(token),
        json={"kho_in_dai": 650, "kho_in_rong": 450,
              "dai_thanh_pham": 100, "rong_thanh_pham": 80},
    )
    assert r.status_code == 403


def test_thieu_view_cost_khong_tao_duoc_phieu(client):
    token = _user_with_role("kd_khong_ruot_2", MODULE, can_read=True, can_create=True)
    r = client.post("/api/phieu-tinh-gia", headers=_h(token), json={"ten_san_pham": "Thử"})
    assert r.status_code == 403


def test_co_view_cost_thi_binh_bai_duoc(client):
    token = _user_with_role("kd_co_ruot", MODULE, can_read=True, can_view_cost=True)
    r = client.post(
        "/api/tinh-gia/binh-bai",
        headers=_h(token),
        json={"kho_in_dai": 650, "kho_in_rong": 450,
              "dai_thanh_pham": 100, "rong_thanh_pham": 80},
    )
    assert r.status_code == 200
```

Fixture `client` lấy từ `backend/tests/conftest.py` — kiểm tên fixture thật trong conftest trước khi chạy; nếu conftest đặt tên khác (vd `api`), đổi cho khớp chứ đừng tự thêm fixture mới.

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

Run: `python -m pytest backend/tests/test_quyen_xem_chi_tiet_gia_von.py -v`
Expected: FAIL — hai test đầu trả 200/201 thay vì 403.

- [ ] **Step 3: Gác quyền ở router**

Trong `backend/app/routers/tinh_gia.py`, đổi dependency của cả hai endpoint từ `"read"` sang `"view_cost"`:

```python
@router.post("/binh-bai")
def binh_bai(
    payload: BinhBaiIn,
    _: Annotated[User, Depends(require_permission(MODULE, "view_cost"))],
) -> dict:
```

Làm y hệt cho `@router.post("/preview")`.

Trong `backend/app/routers/phieu_tinh_gia.py`, thêm một dependency phụ cho bốn endpoint (POST `""`, PUT `/{p_id}`, GET `/san-pham-tai-ban`, GET `/san-pham-tai-ban/{id}`) — giữ nguyên dependency cũ vì nó vẫn phải gác create/update:

```python
RuotGia = Annotated[User, Depends(require_permission(MODULE, "view_cost"))]
```

rồi thêm tham số `_ruot: RuotGia,` vào chữ ký của bốn hàm đó. DELETE `/{p_id}` **giữ nguyên** (xoá phiếu không lộ ruột).

- [ ] **Step 4: Chạy lại test**

Run: `python -m pytest backend/tests/test_quyen_xem_chi_tiet_gia_von.py -v`
Expected: PASS cả ba.

- [ ] **Step 5: Chạy test hồi quy của Tính giá**

Run: `python -m pytest backend/tests/ -k "tinh_gia or phieu" -v`
Expected: PASS. Test nào đỏ vì vai test thiếu `can_view_cost` thì bổ sung cờ đó vào vai trong chính test ấy — đừng nới lỏng router.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/phieu_tinh_gia.py backend/app/routers/tinh_gia.py backend/tests/test_quyen_xem_chi_tiet_gia_von.py
git commit -m "tinh_gia: gác quyền view_cost cho các đường lộ ruột giá (bình bài, preview, tạo/sửa phiếu, sản phẩm tái bản)"
```

---

### Task 2: GET chi tiết phiếu trả bản rút gọn khi thiếu quyền

**Files:**
- Modify: `backend/app/schemas/phieu_tinh_gia.py:266-288`
- Modify: `backend/app/routers/phieu_tinh_gia.py:367-386`
- Test: `backend/tests/test_quyen_xem_chi_tiet_gia_von.py`

**Interfaces:**
- Consumes: `PhieuTinhGiaOut` (đã có).
- Produces: `PhieuTinhGiaOutRutGon` — header + `thanh_phans: list[ThanhPhanRutGonOut]`, **không** có `result`, `warnings`, `danh_muc_doi`. `ThanhPhanRutGonOut` gồm đúng: `id`, `thu_tu`, `ten`, `loai_thanh_phan`, `so_luong`, `don_vi_tinh`, `gia_von_tp`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_quyen_xem_chi_tiet_gia_von.py`:

```python
def _tao_phieu(client) -> int:
    """Người ĐỦ quyền lập sẵn một phiếu để test người THIẾU quyền mở nó."""
    token = _user_with_role(
        "kd_lap_phieu", MODULE,
        can_read=True, can_create=True, can_update=True, can_view_cost=True,
    )
    r = client.post(
        "/api/phieu-tinh-gia",
        headers=_h(token),
        json={"ten_san_pham": "Hộp giấy thử", "so_luong": 1000},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_thieu_view_cost_mo_phieu_khong_thay_dien_giai(client):
    p_id = _tao_phieu(client)
    token = _user_with_role("kd_chi_xem", MODULE, can_read=True)
    r = client.get(f"/api/phieu-tinh-gia/{p_id}", headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    # Vẫn thấy phần đi chào khách được
    assert body["ma"]
    assert "tong_gia_von" in body and "gia_von_don" in body
    # Không còn ruột giá
    assert "result" not in body
    assert "warnings" not in body
    assert "danh_muc_doi" not in body
    for tp in body["thanh_phans"]:
        assert "giay_id" not in tp
        assert "don_gia_giay" not in tp
        assert "may_id" not in tp
        assert "gia_von_tp" in tp


def test_co_view_cost_mo_phieu_thay_du(client):
    p_id = _tao_phieu(client)
    token = _user_with_role("kd_xem_du", MODULE, can_read=True, can_view_cost=True)
    r = client.get(f"/api/phieu-tinh-gia/{p_id}", headers=_h(token))
    assert r.status_code == 200
    assert "result" in r.json()
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

Run: `python -m pytest backend/tests/test_quyen_xem_chi_tiet_gia_von.py -k rut_gon -v`
(nếu tên test không khớp `-k` thì chạy cả file)
Expected: FAIL — `result` vẫn có trong phản hồi.

- [ ] **Step 3: Thêm schema rút gọn**

Cuối phần PHIẾU của `backend/app/schemas/phieu_tinh_gia.py`, ngay sau `PhieuTinhGiaOut`:

```python
class ThanhPhanRutGonOut(BaseModel):
    """Dòng sản phẩm KHÔNG kèm cấu hình — cho vai thiếu `tinh_gia_thanh:view_cost`.

    Đủ để bày bảng "Sản phẩm trong phiếu" (tên · loại · SL · giá vốn) và đi chào khách;
    KHÔNG có giấy/khổ/máy/công đoạn — tức không có gì suy ngược ra định mức hay giá mua vào.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    thu_tu: int
    ten: str
    loai_thanh_phan: str
    so_luong: int
    don_vi_tinh: str
    gia_von_tp: float


class PhieuTinhGiaOutRutGon(BaseModel):
    """Phiếu KHÔNG kèm ruột giá — thiếu `view_cost` thì GET /{id} trả cái này.

    Cố ý là một model RIÊNG chứ không phải `PhieuTinhGiaOut` với vài field None: model riêng
    thì field thừa không thể lọt ra theo đường "quên cắt một chỗ".
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten_san_pham: str
    kho_thanh_pham: str | None = None
    loai_san_pham_id: int | None = None
    so_luong: int
    tong_gia_von: float
    gia_von_don: float
    ktv: str | None = None
    ghi_chu: str | None = None
    thanh_phans: list[ThanhPhanRutGonOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

- [ ] **Step 4: Router chọn model theo quyền**

Trong `backend/app/routers/phieu_tinh_gia.py`, đổi endpoint GET `/{p_id}`:

```python
@router.get("/{p_id}", response_model=None)
def get_item(
    p_id: int,
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PhieuTinhGiaOut | PhieuTinhGiaOutRutGon:
    p = _fetch_in_scope(db, p_id, user, authz)
    # Thiếu `view_cost` → KHÔNG dựng `PhieuTinhGiaOut` (dựng rồi cắt là để ngỏ đường quên cắt).
    if not authz.can(user, MODULE, "view_cost"):
        return PhieuTinhGiaOutRutGon.model_validate(p)
    out = PhieuTinhGiaOut.model_validate(p)
    ...  # phần còn lại giữ nguyên
```

Nhớ import hai model mới ở đầu file, cạnh `PhieuTinhGiaOut`.

- [ ] **Step 5: Chạy lại test**

Run: `python -m pytest backend/tests/test_quyen_xem_chi_tiet_gia_von.py -v`
Expected: PASS toàn file.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/phieu_tinh_gia.py backend/app/routers/phieu_tinh_gia.py backend/tests/test_quyen_xem_chi_tiet_gia_von.py
git commit -m "tinh_gia: thiếu view_cost thì GET phiếu trả bản rút gọn, không kèm diễn giải"
```

---

### Task 3: Chip "Xem chi tiết giá vốn" trong ma trận phân quyền

**Files:**
- Modify: `frontend/src/components/PermissionMatrix.tsx` (map `FINE_ACTIONS`, ~dòng 85-130)
- Modify: `backend/app/seed.py` (vai mẫu khối Kinh doanh, ~dòng 620-680)

**Interfaces:**
- Consumes: `ActionKey` đã có `"can_view_cost"`; `FINE_ACTIONS: Record<string, {key, keys?, label, hint?}[]>`.
- Produces: dòng `tinh_gia_thanh` trong ma trận hiện chip `1/1 chi tiết`.

- [ ] **Step 1: Khai chip vào ma trận**

Thêm vào `FINE_ACTIONS` trong `frontend/src/components/PermissionMatrix.tsx`, đặt ngay trước khoá `bao_gia` cho khớp thứ tự khối Kinh doanh:

```ts
  // Tính giá: ô DUY NHẤT gác "ruột giá" — bảng Chi tiết dòng giá vốn + thẻ sản phẩm (chỗ khai
  // giấy/khổ/công đoạn). Thiếu ô này vẫn mở được phiếu và vẫn thấy giá vốn tổng + đơn giá bình
  // quân (đủ đi chào khách), chỉ không thấy VÌ SAO ra con số đó. Dùng lại cột `can_view_cost`
  // của Kho — cùng nghĩa "xem giá vốn", không đẻ cột mới.
  tinh_gia_thanh: [
    {
      key: "can_view_cost",
      label: "Xem chi tiết giá vốn",
      hint: "Xem bảng “Chi tiết dòng giá vốn” (diễn giải từng dòng: khổ giấy · số tờ · đơn giá kg · tiền từng công đoạn) và mở thẻ sản phẩm để xem/khai cấu hình. Thiếu ô này thì vẫn mở được phiếu, vẫn thấy giá vốn tổng và đơn giá bình quân, nhưng không thấy cách ra con số. Vai có quyền chỉnh sửa Tính giá BẮT BUỘC có ô này (lập phiếu tức là phải mở thẻ ra khai) nên ô tự bật và khoá.",
    },
  ],
```

- [ ] **Step 2: Luật tự bật theo cột Thao tác**

Trong cùng file, tìm chỗ xử lý bật/tắt công tắc `WRITE_ACTIONS` và chỗ render ô chi tiết. Thêm:

```ts
//: Ô chi tiết BẮT BUỘC bật khi module có quyền chỉnh sửa — bật kèm, khoá không cho tắt.
const FINE_THEO_WRITE: Record<string, ActionKey> = {
  tinh_gia_thanh: "can_view_cost",
};

const HINT_FINE_KHOA_THEO_WRITE =
  "Vai có quyền chỉnh sửa Tính giá buộc phải xem được chi tiết giá vốn — lập hoặc sửa phiếu " +
  "chính là mở thẻ sản phẩm ra khai. Tắt “Chỉnh sửa” thì ô này mở khoá lại.";
```

Khi người dùng bật công tắc Chỉnh sửa của một module có trong `FINE_THEO_WRITE`, set luôn cờ chi tiết tương ứng = true; khi module đó đang có write, render ô chi tiết ở trạng thái `disabled` + `title={HINT_FINE_KHOA_THEO_WRITE}`. Bám đúng cách file này đang khoá các ô đòi Phạm vi "Tất cả" (`SCOPE_ALL` guard) — chép cùng lối render `disabled`, đừng tự nghĩ lối mới.

- [ ] **Step 3: Kiểm kiểu TypeScript**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: không lỗi.

- [ ] **Step 4: Bật cờ trong vai mẫu của seed**

Trong `backend/app/seed.py`, mọi vai mẫu đang khai `"tinh_gia_thanh"` bằng `_full(...)` hoặc `_rcu(...)` (có thao tác) phải thêm `can_view_cost=True`. Ví dụ với vai NV Kinh doanh (~dòng 672):

```python
            "tinh_gia_thanh": _rcu(SCOPE_OWN, can_view_cost=True),
```

Vai chỉ `_read(...)` giữ nguyên (không bật) — đó chính là trường hợp dùng của tính năng này.

- [ ] **Step 5: Chạy test RBAC seed**

Run: `python -m pytest backend/tests/test_rbac_seed.py backend/tests/test_giao_dien_khop_may_chu.py backend/tests/test_ma_tran_quyen_khop_thanh_ben.py -v`
Expected: PASS. Guard `test_giao_dien_khop_may_chu` đỏ nghĩa là giao diện hỏi ô mà máy chủ chưa gác — quay lại Task 1 xem thiếu endpoint nào.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/PermissionMatrix.tsx backend/app/seed.py
git commit -m "phan_quyen: thêm ô chi tiết Xem chi tiết giá vốn cho dòng Tính giá, tự bật khi vai có chỉnh sửa"
```

---

### Task 4: Màn Tính giá — ẩn ruột giá và gỡ hẳn nút In phiếu

**Files:**
- Modify: `frontend/src/pages/PhieuTinhGiaDetailView.tsx:2001-2010` (nút In), `:2161` (click mở thẻ), `:2389-2392` (khối Chi tiết dòng giá vốn)
- Modify: `frontend/src/pages/tinh-gia.css:1570` (chỉ nếu có style chỉ dùng cho bản in)

**Interfaces:**
- Consumes: `useCan()` từ `frontend/src/auth/permissions.tsx` — `can("tinh_gia_thanh", "view_cost")`.
- Produces: không.

- [ ] **Step 1: Gỡ nút In phiếu**

Xoá nguyên khối `<Button variant="secondary" onClick={() => window.print()} ...>In phiếu</Button>` (quanh dòng 2001). Không để lại nút ẩn theo quyền — spec §3.2b chốt gỡ hẳn cho mọi vai.

Grep `window.print` trong file để chắc không còn lối gọi nào khác của màn này:

```bash
grep -n "window.print" frontend/src/pages/PhieuTinhGiaDetailView.tsx
```

Nếu `frontend/src/pages/tinh-gia.css` có khối `@media print` chỉ phục vụ nút vừa gỡ thì xoá luôn; khối dùng chung với màn khác thì giữ.

- [ ] **Step 2: Lấy cờ quyền trong component**

Ngay đầu component của màn chi tiết:

```tsx
  const can = useCan();
  const xemRuotGia = can("tinh_gia_thanh", "view_cost");
```

Import `useCan` từ `../auth/permissions` (kiểm đường dẫn tương đối thật của file trước khi gõ).

- [ ] **Step 3: Ẩn bảng Chi tiết dòng giá vốn**

Đổi điều kiện render (dòng ~2392):

```tsx
            {xemRuotGia && result && comps.length > 0 ? (
```

- [ ] **Step 4: Chặn mở thẻ sản phẩm**

Dòng ~2161, hàng sản phẩm:

```tsx
                              onClick={() => { if (xemRuotGia) setEditingUid(c.uid); }}
```

Và bỏ con trỏ tay khi không có quyền: thêm `style={{ cursor: xemRuotGia ? undefined : "default" }}` vào chính hàng đó. Hai nút nhân bản / xoá trong hàng giữ nguyên (chúng theo quyền chỉnh sửa, mà quyền chỉnh sửa đã kéo theo `view_cost`).

- [ ] **Step 5: Kiểm kiểu + build**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: không lỗi.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/PhieuTinhGiaDetailView.tsx frontend/src/pages/tinh-gia.css
git commit -m "tinh_gia: ẩn bảng chi tiết giá vốn + không mở thẻ sản phẩm khi thiếu quyền; gỡ hẳn nút In phiếu"
```

---

### Task 5: Hai bảng nhóm dùng chung + migration + DB_SCHEMA

**Files:**
- Create: `backend/app/models/nhom_dung_chung.py`
- Modify: `backend/app/models/__init__.py:122` (khu vực import model)
- Modify: `backend/app/db_migrations.py` (cuối file, sau `0332`)
- Modify: `docs/DB_SCHEMA.md`
- Test: `backend/tests/test_nhom_dung_chung_kd.py` (tạo)

**Interfaces:**
- Produces: `NhomDungChung(id, ten, created_by, created_at)`, `NhomDungChungThanhVien(id, nhom_id, user_id, added_by, added_at)`; tên bảng `nhom_dung_chung`, `nhom_dung_chung_thanh_vien`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_nhom_dung_chung_kd.py`:

```python
"""Nhóm dùng chung (khối Kinh doanh) — hai người ở phạm vi "Của tôi" dùng chung dữ liệu."""
from __future__ import annotations

from app.models.nhom_dung_chung import NhomDungChung, NhomDungChungThanhVien


def test_hai_bang_ton_tai_va_ghi_duoc(db):
    nhom = NhomDungChung(ten="Cặp KD 1", created_by=None)
    db.add(nhom)
    db.flush()
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=1, added_by=None))
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=2, added_by=None))
    db.flush()
    assert db.query(NhomDungChungThanhVien).filter_by(nhom_id=nhom.id).count() == 2
```

Fixture `db` đã có sẵn trong `backend/tests/conftest.py` (chạy `drop_all` + `create_all` mỗi test).

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

Run: `python -m pytest backend/tests/test_nhom_dung_chung_kd.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.nhom_dung_chung`.

- [ ] **Step 3: Viết model**

Tạo `backend/app/models/nhom_dung_chung.py`:

```python
"""Nhóm DÙNG CHUNG dữ liệu — khối Kinh doanh.

Hai người cùng một nhóm thì, ở BỐN màn `tinh_gia_thanh` · `bao_gia` · `don_hang_ban` ·
`khach_hang`, phạm vi "Của tôi" được hiểu rộng ra: của tôi + của người cùng nhóm. Nhóm chỉ
MỞ RỘNG DỮ LIỆU, KHÔNG nâng quyền — mọi ô quyền vẫn tính theo vai của người đang thao tác.

CỐ Ý không gắn nhóm vào phòng ban: hai người khác phòng vẫn gộp chung được. Cũng CỐ Ý không
cho chọn module lúc tạo nhóm — bốn màn là cứng; khối khác cần thì đẻ loại nhóm riêng.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NhomDungChung(Base):
    __tablename__ = "nhom_dung_chung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ten: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class NhomDungChungThanhVien(Base):
    __tablename__ = "nhom_dung_chung_thanh_vien"
    __table_args__ = (
        UniqueConstraint("nhom_id", "user_id", name="uq_nhom_dung_chung_thanh_vien"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nhom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nhom_dung_chung.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    added_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
```

Thêm vào `backend/app/models/__init__.py`, cạnh các import model khác:

```python
from .nhom_dung_chung import NhomDungChung, NhomDungChungThanhVien
```

- [ ] **Step 4: Chạy lại test**

Run: `python -m pytest backend/tests/test_nhom_dung_chung_kd.py -v`
Expected: PASS.

- [ ] **Step 5: Viết migration 0333**

Cuối `backend/app/db_migrations.py`, sau dòng đăng ký `0332`:

```python
def _migrate_nhom_dung_chung_kd(db: Session) -> None:
    """0333 — hai bảng NHÓM DÙNG CHUNG (khối Kinh doanh).

    `create_all` chỉ tạo bảng trên DB trắng; DB dev/prod đang chạy phải đi qua đây.
    Idempotent: `CREATE TABLE IF NOT EXISTS`. Không backfill — nhóm mở đầu rỗng, người
    không thuộc nhóm nào thì hành vi y như trước khi có tính năng.
    """
    bind = db.get_bind()
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if bind.dialect.name == "sqlite" else "SERIAL PRIMARY KEY"
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS nhom_dung_chung ("
        f"id {pk}, "
        "ten VARCHAR(255) NOT NULL, "
        "created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, "
        "created_at TIMESTAMP NOT NULL, "
        "CONSTRAINT uq_nhom_dung_chung_ten UNIQUE (ten))"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS nhom_dung_chung_thanh_vien ("
        f"id {pk}, "
        "nhom_id INTEGER NOT NULL REFERENCES nhom_dung_chung(id) ON DELETE CASCADE, "
        "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "added_by INTEGER REFERENCES users(id) ON DELETE SET NULL, "
        "added_at TIMESTAMP NOT NULL, "
        "CONSTRAINT uq_nhom_dung_chung_thanh_vien UNIQUE (nhom_id, user_id))"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_nhom_dung_chung_thanh_vien_nhom_id "
        "ON nhom_dung_chung_thanh_vien (nhom_id)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_nhom_dung_chung_thanh_vien_user_id "
        "ON nhom_dung_chung_thanh_vien (user_id)"
    ))


MIGRATIONS.append(("0333_nhom_dung_chung_kd", _migrate_nhom_dung_chung_kd))
```

- [ ] **Step 6: Ghi DB_SCHEMA.md**

Thêm hai section theo đúng khuôn các section khác trong `docs/DB_SCHEMA.md` (`### \`ten_bang\`` + **Purpose:** + **Tất cả cột:**), liệt kê đủ mọi cột của hai model — guard `test_schema_documented.py` so khớp từng cột.

- [ ] **Step 7: Chạy guard schema**

Run: `python -m pytest backend/tests/test_schema_documented.py backend/tests/test_nhom_dung_chung_kd.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/nhom_dung_chung.py backend/app/models/__init__.py backend/app/db_migrations.py docs/DB_SCHEMA.md backend/tests/test_nhom_dung_chung_kd.py
git commit -m "nhom_dung_chung: thêm bảng nhom_dung_chung + thành viên, migration 0333, ghi DB_SCHEMA"
```

---

### Task 6: Hàm tập user-id dùng chung + nối vào bốn màn

**Files:**
- Modify: `backend/app/repositories/org_scope.py`
- Modify: `backend/app/routers/phieu_tinh_gia.py:54-66`
- Modify: `backend/app/repositories/quotation_repo.py:115-126` và `:167-172`
- Modify: `backend/app/repositories/order_repo.py:57-63` và `:74-78`
- Modify: `backend/app/repositories/customer_repo.py:104-110` và `can_access`
- Test: `backend/tests/test_nhom_dung_chung_kd.py`

**Interfaces:**
- Produces: `nhom_dung_chung_user_ids(db: Session, user_id: int) -> set[int]` trong `org_scope.py` — trả `{user_id}` ∪ mọi thành viên của mọi nhóm mà `user_id` thuộc. Người không thuộc nhóm nào → đúng `{user_id}`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_nhom_dung_chung_kd.py`:

```python
from app.repositories.org_scope import nhom_dung_chung_user_ids


def test_khong_thuoc_nhom_thi_chi_chinh_minh(db):
    assert nhom_dung_chung_user_ids(db, 7) == {7}


def test_cung_nhom_thi_thay_nhau(db):
    nhom = NhomDungChung(ten="Cặp KD 2", created_by=None)
    db.add(nhom)
    db.flush()
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=10, added_by=None))
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=11, added_by=None))
    db.flush()
    assert nhom_dung_chung_user_ids(db, 10) == {10, 11}
    assert nhom_dung_chung_user_ids(db, 11) == {10, 11}


def test_nhieu_nhom_thi_lay_hop(db):
    a = NhomDungChung(ten="Cặp A", created_by=None)
    b = NhomDungChung(ten="Cặp B", created_by=None)
    db.add_all([a, b])
    db.flush()
    db.add_all([
        NhomDungChungThanhVien(nhom_id=a.id, user_id=20, added_by=None),
        NhomDungChungThanhVien(nhom_id=a.id, user_id=21, added_by=None),
        NhomDungChungThanhVien(nhom_id=b.id, user_id=20, added_by=None),
        NhomDungChungThanhVien(nhom_id=b.id, user_id=22, added_by=None),
    ])
    db.flush()
    assert nhom_dung_chung_user_ids(db, 20) == {20, 21, 22}
    assert nhom_dung_chung_user_ids(db, 21) == {20, 21}
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

Run: `python -m pytest backend/tests/test_nhom_dung_chung_kd.py -v`
Expected: FAIL — `ImportError: cannot import name 'nhom_dung_chung_user_ids'`.

- [ ] **Step 3: Viết hàm**

Thêm vào cuối `backend/app/repositories/org_scope.py`:

```python
def nhom_dung_chung_user_ids(db: Session, user_id: int) -> set[int]:
    """Tập user-id DÙNG CHUNG dữ liệu với `user_id` — gồm cả chính nó.

    Đây là NGUỒN DUY NHẤT của nghĩa "Của tôi" mở rộng ở bốn màn khối Kinh doanh
    (`tinh_gia_thanh` · `bao_gia` · `don_hang_ban` · `khach_hang`). Không nơi nào khác được
    tự truy vấn hai bảng nhóm để lọc dữ liệu.

    Người không thuộc nhóm nào → `{user_id}`: hành vi y hệt trước khi có tính năng.
    """
    tv = NhomDungChungThanhVien
    nhom_cua_toi = select(tv.nhom_id).where(tv.user_id == user_id)
    ids = db.execute(select(tv.user_id).where(tv.nhom_id.in_(nhom_cua_toi))).scalars().all()
    return set(ids) | {user_id}
```

Import `NhomDungChungThanhVien` và `select` ở đầu file (kiểm xem `select` đã import chưa trước khi thêm trùng).

- [ ] **Step 4: Chạy lại test**

Run: `python -m pytest backend/tests/test_nhom_dung_chung_kd.py -v`
Expected: PASS.

- [ ] **Step 5: Nối vào bốn màn**

`backend/app/routers/phieu_tinh_gia.py` — `_owner_ids_for_scope`, đổi dòng cuối:

```python
    return nhom_dung_chung_user_ids(db, user.id)
```

(Dòng `return {user.id}` cũ phục vụ cả nhánh `own` lẫn nhánh `department` của người chưa có phòng — cả hai đều là "của tôi", nên cùng mở rộng theo nhóm.) Cập nhật docstring của hàm cho khớp.

`backend/app/repositories/quotation_repo.py`:

```python
        if scope == SCOPE_OWN:
            return Quote.salesperson_id.in_(nhom_dung_chung_user_ids(self.db, actor.id))
```

và trong `can_access`:

```python
        if scope == SCOPE_OWN:
            return quote.salesperson_id in nhom_dung_chung_user_ids(self.db, actor.id)
```

`backend/app/repositories/order_repo.py` — y hệt với `Order.sale_user_id` / `order.sale_user_id`.

`backend/app/repositories/customer_repo.py` — y hệt với `Customer.sale_user_id` / `customer.sale_user_id`.

Nhánh `SCOPE_DEPARTMENT` và `SCOPE_ALL` của cả bốn nơi **không đụng tới**.

- [ ] **Step 6: Viết test đầu-cuối cho hai màn đại diện**

Thêm vào `backend/tests/test_nhom_dung_chung_kd.py` hai test qua API: A và B đều scope `own`, cùng nhóm ⇒ A `GET /api/phieu-tinh-gia/{id}` của B trả 200; C khác nhóm ⇒ 404. Dựng vai bằng đúng hàm `_user_with_role` (chép từ `test_fine_permissions_api.py`, có kèm `can_view_cost=True` để không vướng Task 1), và dựng nhóm bằng model trực tiếp qua `SessionLocal()`.

Làm thêm cặp test y hệt cho `GET /api/quotations/{id}` (đường thật của màn Báo giá — kiểm tên route trong `backend/app/routers/quotations.py` trước khi gõ).

- [ ] **Step 7: Chạy test hồi quy của bốn màn**

Run: `python -m pytest backend/tests/ -k "nhom_dung_chung or quotation or order or customer or phieu" -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/repositories/org_scope.py backend/app/repositories/quotation_repo.py backend/app/repositories/order_repo.py backend/app/repositories/customer_repo.py backend/app/routers/phieu_tinh_gia.py backend/tests/test_nhom_dung_chung_kd.py
git commit -m "nhom_dung_chung: phạm vi Của tôi của 4 màn Kinh doanh đọc theo nhóm, một hàm nguồn duy nhất"
```

---

### Task 7: API quản lý nhóm dùng chung

**Files:**
- Create: `backend/app/schemas/nhom_dung_chung.py`, `backend/app/repositories/nhom_dung_chung_repo.py`, `backend/app/routers/nhom_dung_chung.py`
- Modify: `backend/app/main.py:58` (import) và `:145-163` (mount)
- Test: `backend/tests/test_nhom_dung_chung_kd.py`

**Interfaces:**
- Produces: `GET /api/nhom-dung-chung` (danh sách nhóm kèm thành viên) · `POST /api/nhom-dung-chung` (`{ten, user_ids}`) · `PATCH /api/nhom-dung-chung/{id}` (`{ten?, user_ids?}` — `user_ids` là thay-toàn-bộ) · `DELETE /api/nhom-dung-chung/{id}`. Mọi đường gác `require_permission("phong_ban", "manage_permissions")`.
- Schema ra: `NhomOut{id, ten, thanh_viens: list[ThanhVienOut{user_id, ho_ten, username}], created_at}`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_nhom_dung_chung_kd.py` (hai helper `_h` và `_user_with_role` đã được chép vào file này ở Task 6 Step 6 — nếu chưa thì chép trước, nguyên văn như trong Task 1 Step 1):

```python
def test_thieu_quyen_khong_tao_duoc_nhom(client):
    token = _user_with_role("kd_thuong", "tinh_gia_thanh", can_read=True)
    r = client.post("/api/nhom-dung-chung", headers=_h(token),
                    json={"ten": "Cặp lén", "user_ids": [1, 2]})
    assert r.status_code == 403


def test_co_quyen_thi_tao_va_sua_duoc_nhom(client):
    token = _user_with_role("qtri_quyen", "phong_ban",
                            can_read=True, can_manage_permissions=True)
    r = client.post("/api/nhom-dung-chung", headers=_h(token),
                    json={"ten": "Cặp KD 9", "user_ids": []})
    assert r.status_code == 201, r.text
    nhom_id = r.json()["id"]

    r = client.get("/api/nhom-dung-chung", headers=_h(token))
    assert r.status_code == 200
    assert any(n["id"] == nhom_id for n in r.json())

    r = client.patch(f"/api/nhom-dung-chung/{nhom_id}", headers=_h(token),
                     json={"ten": "Cặp KD 9 (đổi tên)"})
    assert r.status_code == 200
    assert r.json()["ten"] == "Cặp KD 9 (đổi tên)"

    r = client.delete(f"/api/nhom-dung-chung/{nhom_id}", headers=_h(token))
    assert r.status_code == 200
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

Run: `python -m pytest backend/tests/test_nhom_dung_chung_kd.py -k nhom -v`
Expected: FAIL — 404 vì chưa có route.

- [ ] **Step 3: Viết schema + repository + router**

`backend/app/schemas/nhom_dung_chung.py`:

```python
"""Schema vào/ra của Nhóm dùng chung (khối Kinh doanh)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ThanhVienOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    ho_ten: str
    username: str


class NhomOut(BaseModel):
    id: int
    ten: str
    thanh_viens: list[ThanhVienOut] = Field(default_factory=list)
    created_at: datetime | None = None


class NhomCreate(BaseModel):
    ten: str = Field(min_length=1, max_length=255)
    user_ids: list[int] = Field(default_factory=list)


class NhomUpdate(BaseModel):
    """`user_ids` gửi lên là THAY TOÀN BỘ danh sách thành viên (không phải thêm dồn)."""
    ten: str | None = Field(default=None, min_length=1, max_length=255)
    user_ids: list[int] | None = None
```

`backend/app/repositories/nhom_dung_chung_repo.py` — `NhomDungChungRepository(db)` với `list_all()`, `create(ten, user_ids, actor_id)`, `update(nhom_id, ten, user_ids, actor_id)`, `delete(nhom_id)`. `update` với `user_ids` khác `None` thì xoá sạch thành viên cũ rồi ghi lại danh sách mới; tên trùng ⇒ `ValueError("Tên nhóm đã tồn tại")`.

`backend/app/routers/nhom_dung_chung.py`:

```python
"""Nhóm dùng chung (khối Kinh doanh) — CRUD.

Gộp nhóm = cho người này thấy dữ liệu của người kia, cùng loại với việc CẤP QUYỀN, nên gác
bằng ô đã có `phong_ban:manage_permissions` thay vì đẻ ô quyền mới. Mọi thao tác ghi vết.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.nhom_dung_chung_repo import NhomDungChungRepository
from ..schemas.nhom_dung_chung import NhomCreate, NhomOut, NhomUpdate

router = APIRouter(prefix="/api/nhom-dung-chung", tags=["nhom-dung-chung"])
MODULE = "phong_ban"
```

Bốn endpoint như phần **Interfaces**. Mỗi thao tác ghi `AuditLogRepository(db).create(...)` với `action` lần lượt `"create_nhom_dung_chung"` / `"update_nhom_dung_chung"` / `"delete_nhom_dung_chung"`, `target=f"nhom_dung_chung:{id}"`, `detail` nêu tên nhóm và danh sách người thêm/bớt. Tên trùng trả `409`.

Mount trong `backend/app/main.py`: thêm `nhom_dung_chung` vào khối import routers (~dòng 58) và `app.include_router(nhom_dung_chung.router)` cạnh `app.include_router(rbac.router)`.

- [ ] **Step 4: Chạy lại test**

Run: `python -m pytest backend/tests/test_nhom_dung_chung_kd.py -v`
Expected: PASS toàn file.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/nhom_dung_chung.py backend/app/repositories/nhom_dung_chung_repo.py backend/app/routers/nhom_dung_chung.py backend/app/main.py backend/tests/test_nhom_dung_chung_kd.py
git commit -m "nhom_dung_chung: API tạo/sửa/xoá nhóm, gác bằng phong_ban:manage_permissions, ghi vết đầy đủ"
```

---

### Task 8: Giao diện gộp nhóm ở màn Phòng ban

**Files:**
- Create: `frontend/src/pages/nhan-su-luong/phong-ban/NhomDungChungModal.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/nhan-su-luong/phong-ban/DepartmentsPage.tsx` (thanh thao tác hàng loạt tab Nhân sự, quanh `selectedMemberIds` — dòng 247, 597-600, 783-824)

**Interfaces:**
- Consumes: `api.nhomDungChung.list/create/update/remove(token, ...)`; `selectedMemberIds` (là **employee_id**, phải đổi sang `user_id` bằng `members.filter(m => selectedMemberIds.has(m.employee_id) && m.user_id != null)` — đúng cách `bulkAssignRole` đang làm ở dòng 818).
- Produces: `NhomDungChungModal` nhận props `{ token, userIds, onClose, onSaved }`.

- [ ] **Step 1: Thêm hàm gọi API**

Trong `frontend/src/api/client.ts`, thêm nhóm hàm `nhomDungChung` với `list`, `create`, `update`, `remove`, kèm type `NhomDungChung { id: number; ten: string; thanh_viens: { user_id: number; ho_ten: string; username: string }[]; created_at?: string }`. Bám đúng khuôn các nhóm hàm sẵn có trong file (cùng cách truyền token, cùng cách xử lý lỗi).

- [ ] **Step 2: Viết modal**

`NhomDungChungModal.tsx`: mở ra hiện hai lựa chọn — *Tạo nhóm mới* (ô nhập tên) hoặc *Thêm vào nhóm đã có* (dropdown từ `list()`), kèm danh sách người đang chọn. Nút chính **"Gộp nhóm"**; lưu xong gọi `onSaved()`. Trong modal có mục quản lý: đổi tên nhóm, bỏ từng người, xoá nhóm (hỏi xác nhận trước khi xoá).

Toàn bộ chữ tiếng Việt. Không hiện dòng phụ liệt kê bốn màn (chủ dự án chốt 24/09).

- [ ] **Step 3: Nối vào DepartmentsPage**

Trong thanh thao tác hàng loạt của tab Nhân sự (chỗ đang có nút Điều chuyển / Gán vai trò), thêm:

```tsx
        <Button
          variant="secondary"
          disabled={selectedWithAccount.length === 0}
          onClick={() => setMoNhomDungChung(true)}
        >
          Gộp nhóm dùng chung — Kinh doanh
        </Button>
```

Nút chỉ hiện khi `can("phong_ban", "manage_permissions")`. Trong danh sách nhân sự, người thuộc nhóm nào thì hiện chip tên nhóm cạnh tên; bấm chip mở đúng modal đó ở chế độ sửa nhóm.

- [ ] **Step 4: Kiểm kiểu**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: không lỗi.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/nhan-su-luong/phong-ban/NhomDungChungModal.tsx frontend/src/pages/nhan-su-luong/phong-ban/DepartmentsPage.tsx
git commit -m "phong_ban: nút Gộp nhóm dùng chung — Kinh doanh ở tab Nhân sự + modal quản lý nhóm"
```

---

### Task 9: Xác minh bằng giao diện thật

**Files:** không sửa (trừ khi phát hiện lỗi).

Bắt buộc theo `CLAUDE.md`: thao tác lại đúng luồng bằng chuột/bàn phím thật trên dev-browser, **không** dùng API/curl thay bất kỳ bước nào. Báo cáo phải liệt kê cụ thể đã bấm gì, gõ gì, thấy gì ở từng bước.

- [ ] **Step 1: Khởi động lại backend**

Sửa route + schema ⇒ uvicorn phải restart (dev không hot-reload đáng tin). Đẻ tiến trình qua `Win32_Process.Create`, backend `--host localhost`, frontend `localhost:5173`.

- [ ] **Step 2: Kiểm việc 1 — vai thiếu quyền**

Đăng nhập admin → màn Phòng ban → tab Vai trò & Quyền → tạo vai thử ở phòng Kinh doanh, bật Xem cho Tính giá, **tắt** "Xem chi tiết giá vốn", Phạm vi "Tất cả" → Lưu. Gán vai đó cho một tài khoản thử. Đăng nhập tài khoản đó, mở một phiếu tính giá có sẵn. Ghi lại: có thấy bảng Chi tiết dòng giá vốn không, bấm vào dòng sản phẩm có mở thẻ không, còn nút In phiếu không, có thấy giá vốn tổng và đơn giá bình quân không.

- [ ] **Step 3: Kiểm việc 1 — vai đủ quyền**

Bật lại ô "Xem chi tiết giá vốn" cho vai đó → Lưu → đăng nhập lại tài khoản thử → mở lại phiếu. Ghi lại: bảng chi tiết đã hiện, bấm dòng sản phẩm mở được thẻ. Xác nhận nút In phiếu **không còn** kể cả với admin.

- [ ] **Step 4: Kiểm việc 1 — ràng buộc ma trận**

Ở ma trận, bật công tắc Chỉnh sửa cho dòng Tính giá của vai thử. Ghi lại: ô "Xem chi tiết giá vốn" có tự bật và khoá không, chú thích hiện gì khi rê chuột.

- [ ] **Step 5: Kiểm việc 2 — gộp nhóm**

Tạo hai tài khoản thử A và B trong phòng Kinh doanh, cùng một vai có Phạm vi **Của tôi** ở cả bốn dòng khối Kinh doanh. Đăng nhập A, lập một phiếu tính giá mới (gõ tên sản phẩm, số lượng, thêm sản phẩm, bấm Tính giá & lưu) — ghi lại mã phiếu. Đăng nhập B, mở danh sách Tính giá: ghi lại có thấy phiếu của A không (phải **không**).

Đăng nhập admin → Phòng ban → tab Nhân sự → tick A và B → bấm "Gộp nhóm dùng chung — Kinh doanh" → đặt tên → Gộp.

Đăng nhập lại B, mở danh sách Tính giá: ghi lại đã thấy phiếu của A chưa, mở ra và sửa thử một ô rồi lưu, kiểm "Người lập" còn là A không.

- [ ] **Step 6: Kiểm việc 2 — không lan sang màn khác**

Vẫn tài khoản B: mở màn Lương và Hồ sơ nhân sự. Ghi lại: có thấy dữ liệu của A không (phải **không**).

- [ ] **Step 7: Kiểm việc 2 — gỡ khỏi nhóm**

Admin gỡ B khỏi nhóm. Đăng nhập lại B, mở danh sách Tính giá: ghi lại phiếu của A đã biến mất chưa.

- [ ] **Step 8: Báo cáo**

Viết báo cáo liệt kê từng bước trên kèm kết quả quan sát được. Nếu vì lý do nào đó buộc phải dùng API ở một đoạn, nói rõ ngay trong báo cáo.

---

## Ghi chú cho người thực thi

- Test hiện có của bốn màn Kinh doanh dựng vai bằng `roles.set_permission(...)`. Sau Task 1, test nào lập/sửa phiếu tính giá mà không khai `can_view_cost=True` sẽ đỏ — bổ sung cờ vào chính test đó, **không** nới router.
- `docs/DB_SCHEMA.md` có hook chấm working tree. Stash một phần làm hook đỏ oan: gộp WIP vào cây trước rồi commit, đừng `--no-verify`.
- Cây làm việc lúc lập kế hoạch đang có sẵn nhiều file dở của đợt RBAC khác (`git status` hơn 30 file). Xác nhận với chủ dự án trước khi commit để không gộp nhầm.
