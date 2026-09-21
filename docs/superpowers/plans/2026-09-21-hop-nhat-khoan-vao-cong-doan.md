# Hợp nhất Khoán vào Công đoạn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ module Công việc khoán độc lập, cấu hình một bộ Khoán trên mỗi Công đoạn và tự lấy cấu hình đó khi ghi mẻ mà vẫn đọc được lịch sử cũ.

**Architecture:** Thêm aggregate 1–1 `CongDoanKhoan` dưới `CongDoan`, kèm các dòng `CongDoanKhoanPhatSinh`; API Công đoạn đọc/ghi aggregate trong cùng giao dịch. Mẻ mới giữ cột legacy `piece_rate_id` cho lịch sử nhưng dùng khóa nguồn mới và ảnh chụp từ Công đoạn; mẻ cũ tiếp tục đi đường đối chiếu cũ.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic, SQLite/PostgreSQL, React, TypeScript, Vitest/Testing Library, pytest.

**Lưu ý Git:** Không commit vì quy tắc dự án chỉ cho commit khi người dùng yêu cầu.

---

### Task 1: Mô hình dữ liệu Khoán của Công đoạn

**Files:**
- Modify: `backend/app/models/cong_doan.py`
- Modify: `backend/app/models/san_xuat_san_luong.py`
- Modify: `backend/app/db_migrations.py`
- Modify: `docs/DB_SCHEMA.md`
- Create: `backend/tests/test_migration_cong_doan_khoan.py`

- [ ] **Step 1: Viết test migration thất bại**

Tạo DB tối thiểu, chạy migration mới hai lần và khẳng định có `cong_doan_khoan`, `cong_doan_khoan_phat_sinh`, khóa duy nhất theo `cong_doan_id`, cùng các cột nguồn mới trên mẻ.

```python
assert {"cong_doan_id", "unit", "unit_price", "cong_thuc_khoan"} <= cols("cong_doan_khoan")
assert {"khoan_cong_doan_id"} <= cols("san_xuat_batch")
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `python -m pytest backend/tests/test_migration_cong_doan_khoan.py -q`

Expected: FAIL vì bảng/cột mới chưa tồn tại.

- [ ] **Step 3: Thêm model và migration tối thiểu**

```python
class CongDoanKhoan(Base):
    __tablename__ = "cong_doan_khoan"
    __table_args__ = (UniqueConstraint("cong_doan_id", name="uq_cong_doan_khoan_cong_doan"),)
    id = mapped_column(Integer, primary_key=True)
    cong_doan_id = mapped_column(ForeignKey("cong_doan.id", ondelete="CASCADE"), nullable=False)
    unit = mapped_column(String(24), nullable=False)
    unit_price = mapped_column(Numeric(18, 2), nullable=False)
    cong_thuc_khoan = mapped_column(Text)
```

Thêm bảng con phát sinh, quan hệ ORM, `khoan_cong_doan_id` nullable trên `SanXuatBatch`, migration idempotent và mô tả schema. Không xóa bảng cũ.

- [ ] **Step 4: Chạy test và xác nhận GREEN**

Run: `python -m pytest backend/tests/test_migration_cong_doan_khoan.py -q`

Expected: PASS.

### Task 2: API Công đoạn đọc/ghi tab Khoán

**Files:**
- Modify: `backend/app/schemas/cong_doan.py`
- Modify: `backend/app/repositories/cong_doan_repo.py`
- Modify: `backend/app/services/cong_doan_service.py`
- Modify: `backend/app/services/nhat_ky_danh_muc.py`
- Modify: `backend/tests/test_cong_doan.py`
- Create: `backend/tests/test_cong_doan_khoan.py`

- [ ] **Step 1: Viết test HTTP/service thất bại**

Bao phủ tạo, đọc, sửa, xóa trắng, giá `0`, thiếu đơn vị, giá âm, việc phát sinh trùng tên và rollback khi lỗi.

```python
body["khoan"] = {
    "unit": "to", "unit_price": 25, "cong_thuc_khoan": "sl_ra",
    "viec_phat_sinh": [{"ten": "Thay kẽm", "don_gia": 100000, "don_vi": "kem"}],
}
r = client.post("/api/cong-doan", json=body, headers=h)
assert r.status_code == 201
assert r.json()["khoan"]["unit_price"] == 25
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `python -m pytest backend/tests/test_cong_doan_khoan.py -q`

Expected: FAIL vì schema chưa nhận/trả `khoan`.

- [ ] **Step 3: Cài đặt aggregate và validation**

Thêm `CongDoanKhoanIn/Row`, eager-load quan hệ, thay trọn danh sách phát sinh, chuẩn hóa công thức, kiểm đơn vị có thật, giá không âm và tên không trùng.

```python
if khoan and (not khoan.get("unit") or khoan.get("unit_price") is None):
    raise CongDoanValidationError("Cấu hình khoán cần đủ đơn vị tính và đơn giá.")
```

Khối `khoan=None` hoặc rỗng xóa aggregate. Nhật ký Công đoạn chụp nội dung Khoán và các việc phát sinh.

- [ ] **Step 4: Chạy test và xác nhận GREEN**

Run: `python -m pytest backend/tests/test_cong_doan_khoan.py backend/tests/test_cong_doan.py -q`

Expected: PASS.

### Task 3: Ghi mẻ tự lấy Khoán theo Công đoạn

**Files:**
- Modify: `backend/app/repositories/san_xuat_san_luong_repo.py`
- Modify: `backend/app/services/san_xuat/viec_khoan.py`
- Modify: `backend/app/services/san_xuat/san_luong.py`
- Modify: `backend/app/services/san_xuat/board.py`
- Modify: `backend/app/schemas/san_xuat.py`
- Modify: `backend/tests/san_xuat_me_fixtures.py`
- Modify: `backend/tests/test_san_xuat_viec_khoan.py`

- [ ] **Step 1: Viết test luồng mẻ mới thất bại**

Bao phủ tự chụp giá theo Công đoạn dù payload không có `piece_rate_id`, công đoạn chưa cấu hình vẫn ghi được, phát sinh sai công đoạn bị chặn, sửa giá không đổi ảnh chụp, và mẻ legacy vẫn đọc được.

```python
kq = tao_batch(db, user=admin, cong_viec_id=cv.id, phat_sinh=[], **so_luong)
b = db.get(SanXuatBatch, kq["batch_id"])
assert b.piece_rate_id is None
assert b.khoan_cong_doan_id == cd.khoan.id
assert float(b.don_gia_khoan_snapshot) == 25
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `python -m pytest backend/tests/test_san_xuat_viec_khoan.py -q`

Expected: FAIL vì service vẫn bắt chọn `piece_rate_id`.

- [ ] **Step 3: Đổi nguồn snapshot và đối chiếu**

Server suy `CongDoan` từ `SanXuatCongViec`, không nhận nguồn khoán do client chọn. Mẻ mới ghi `khoan_cong_doan_id`, snapshot tên công đoạn/đơn vị/giá và dòng phát sinh mới; mẻ có `piece_rate_id` tiếp tục dùng code legacy khi hiển thị/đối chiếu.

```python
o_khoan, cac_phat_sinh = chuan_hoa_khi_ghi(
    db, cong_doan_id=cv.cong_doan_id, phat_sinh=phat_sinh,
)
```

- [ ] **Step 4: Chạy test và xác nhận GREEN**

Run: `python -m pytest backend/tests/test_san_xuat_viec_khoan.py backend/tests/test_san_xuat_me_chi_tiet.py backend/tests/test_san_xuat_san_luong_to.py -q`

Expected: PASS.

### Task 4: Gỡ module và quyền Công việc khoán khỏi luồng mới

**Files:**
- Modify: `backend/app/catalog_registry.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/role_templates.py`
- Modify: `backend/app/db_migrations.py`
- Modify: `backend/tests/test_catalog_registry.py`
- Modify: `backend/tests/test_roles_permissions.py`

- [ ] **Step 1: Sửa test kỳ vọng module cũ biến mất**

```python
assert "cong_viec_khoan" not in {d.key for d in DANH_MUC}
assert "dm_cong_viec_khoan" not in module_keys(db)
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `python -m pytest backend/tests/test_catalog_registry.py backend/tests/test_roles_permissions.py -q`

Expected: FAIL vì registry/quyền cũ còn tồn tại.

- [ ] **Step 3: Gỡ đường công khai và migration quyền**

Gỡ registry, router include, role template và quyền DB. Giữ model/repository legacy để đọc mẻ cũ.

- [ ] **Step 4: Chạy test và xác nhận GREEN**

Run: `python -m pytest backend/tests/test_catalog_registry.py backend/tests/test_roles_permissions.py -q`

Expected: PASS.

### Task 5: Tab Khoán trong drawer Công đoạn

**Files:**
- Modify: `frontend/src/pages/rebuildCatalogConfigs.tsx`
- Modify: `frontend/src/pages/danh-muc/types.ts`
- Modify: `frontend/src/pages/danh-muc/CatalogDrawer.tsx`
- Modify: `frontend/src/pages/danh-muc/fields/ViecPhatSinh.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/rebuildCatalogConfigs.test.tsx`
- Modify: `frontend/src/pages/danh-muc/CatalogDrawer.test.tsx`

- [ ] **Step 1: Viết test UI thất bại**

Kiểm tra tab theo thứ tự `Thông tin, Khoán, Vật tư, Công thức tính giá, Nhật ký`, cấu hình cũ không còn trong `REBUILD_CONFIGS`, và payload Công đoạn chứa khối `khoan`.

```tsx
expect(screen.getAllByRole("tab").map((x) => x.textContent)).toEqual([
  "Thông tin", "Khoán", "Vật tư", "Công thức tính giá", "Nhật ký",
]);
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `npm --prefix frontend test -- --run src/pages/rebuildCatalogConfigs.test.tsx src/pages/danh-muc/CatalogDrawer.test.tsx`

Expected: FAIL vì chưa có tab Khoán trên Công đoạn.

- [ ] **Step 3: Cài đặt tab và trạng thái**

Dùng style/component hiện hữu. Tab có khối Đơn giá, Công thức khoán với ghi chú “Đang lưu cấu hình, chưa áp dụng tính tự động”, và Việc phát sinh. Form khởi tạo `khoan=null`, gửi cả aggregate trong nút Lưu chung và chuyển tab khi server trả lỗi Khoán.

- [ ] **Step 4: Chạy test và xác nhận GREEN**

Run: `npm --prefix frontend test -- --run src/pages/rebuildCatalogConfigs.test.tsx src/pages/danh-muc/CatalogDrawer.test.tsx`

Expected: PASS.

### Task 6: Bỏ chọn Công việc khoán ở form ghi mẻ

**Files:**
- Modify: `frontend/src/pages/ThsxExecPanels.tsx`
- Modify: `frontend/src/pages/ThsxBatchRow.test.tsx`
- Modify: `frontend/src/api/client.ts`
- Add or modify: `frontend/src/pages/ThsxExecPanels.test.tsx`

- [ ] **Step 1: Viết test UI thất bại**

Kiểm tra form không còn radio Công việc khoán, hiển thị một cấu hình cố định của Công đoạn, chỉ gửi danh sách phát sinh, và công đoạn chưa cấu hình vẫn ghi mẻ được.

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `npm --prefix frontend test -- --run src/pages/ThsxExecPanels.test.tsx src/pages/ThsxBatchRow.test.tsx`

Expected: FAIL vì UI vẫn yêu cầu chọn một công việc khoán.

- [ ] **Step 3: Cài đặt UI ghi mẻ mới**

Loại state/radio `piece_rate_id`; đọc cấu hình Khoán do API công việc trả về, hiển thị giá cố định và giữ editor số lượng phát sinh.

- [ ] **Step 4: Chạy test và xác nhận GREEN**

Run: `npm --prefix frontend test -- --run src/pages/ThsxExecPanels.test.tsx src/pages/ThsxBatchRow.test.tsx`

Expected: PASS.

### Task 7: Kiểm chứng toàn hệ thống và UI

**Files:**
- Review only: toàn bộ diff

- [ ] **Step 1: Chạy StyleSeed review**

Chấm `CatalogDrawer.tsx`, cấu hình Công đoạn và form ghi mẻ; sửa các điểm có bằng chứng cho tới khi đạt ít nhất 80/100.

- [ ] **Step 2: Kiểm giao diện chạy thật**

Mở drawer Công đoạn, xác nhận thứ tự tab, trạng thái trống, lỗi validation, cấu hình có việc phát sinh và form ghi mẻ không còn radio chọn việc.

- [ ] **Step 3: Chạy lệnh xác minh duy nhất**

Run: `./init.ps1`

Expected: toàn bộ pytest, frontend tests/typecheck/build và guard schema đều PASS.

- [ ] **Step 4: Rà yêu cầu và diff**

Đối chiếu đủ 13 tiêu chí nghiệm thu trong spec, chạy `git diff --check`, báo rõ bước nào không thể thực hiện nếu có.
