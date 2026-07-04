# Định mức & Bù hao (danh mục #7) — thiết kế đầy đủ

> **Vai trò:** Danh mục #7 trong [DANH_MUC_TINH_GIA.md](./DANH_MUC_TINH_GIA.md). KHÔNG tính tiền
> trực tiếp — nó nuôi các hệ số để engine ra **số tờ sản xuất** và **số tờ mua giấy** từ số lượng đặt.
> **Chuỗi:** `Số tờ lý thuyết → Số tờ sản xuất → Số tờ mua giấy`.
> **Engine:** [pricing_engine.py](../backend/app/services/pricing_engine.py) đọc danh mục này qua
> [norm_service.py](../backend/app/services/norm_service.py). Kết quả hiển thị trên màn **Tính giá**.

---

## 1. Bốn nhóm định mức (`waste_group`)

| Nhóm | Ý nghĩa | Áp trong chuỗi |
|---|---|---|
| `YIELD_RATE` | Tỷ lệ đạt từng công đoạn (gộp cả "hao công đoạn") | Tính ngược: `trước = ceil(sau / đạt)` |
| `SETUP_WASTE` | Bù hao setup / makeready (canh máy, canh màu) | Cộng thêm số tờ cố định |
| `RUNNING_WASTE` | Hao chạy máy theo % sản lượng | Cộng thêm `base × %` |
| `PAPER_EXTRA_WASTE` | Hao giấy riêng để tính **số tờ mua giấy** | Cộng vào tờ mua |

> Đơn giá mực (`ink_cost_per_1000_impressions`) **không** thuộc 4 nhóm này — nó là *đơn giá* (danh mục
> ④ Mực), engine vẫn đọc như cũ, không hiển thị trong trang 4-nhóm.

## 2. Công thức chuỗi (engine)

```text
Số tờ lý thuyết     = ceil(SL / số con)
── Chuỗi ngược qua CĐ sau in (dán → bế → cán), mỗi CĐ:
      trước = ceil(sau / tỷ_lệ_đạt[CĐ]) + setup[CĐ]
── Khâu in:
      sau_yield   = ceil(tờ_cần_in / tỷ_lệ_đạt_in)
      makeready   = clamp(fixed + per_color×màu + per_side×mặt, min, max)     ← CỘNG
      running     = clamp(ceil(sau_yield × running%), min, max)               ← CỘNG (không ÷(1−p))
      Số tờ SX    = sau_yield + makeready + running
── Giấy:
      hao_giấy    = clamp(theo %SX / cố định / theo ram, min, max)
      Số tờ mua   = (Số tờ SX + hao_giấy nếu cộng-vào-mua) ÷ số tờ in / tờ mua
```

Ví dụ (spec): SL 1.000, 4 con/tờ, 250 tờ LT, 4 màu, 2 mặt, in đạt 97%, makeready 100+30/màu, running 3%:

```text
Cần trước in  = ceil(250 / 0.97)            = 258 tờ
Makeready     = 100 + 30 × 4                = 220 tờ
Running       = ceil(258 × 3%)              =   8 tờ
Số tờ SX      = 258 + 220 + 8              = 486 tờ
Hao giấy 1%   = ceil(486 × 1%)             =   5 tờ
Số tờ mua     = 486 + 5                     = 491 tờ
```

## 3. `calculation_method` theo nhóm

| Nhóm | Method | Công thức |
|---|---|---|
| `YIELD_RATE` | `PERCENT` | `trước = ceil(sau / value)`; `value ∈ (0,1]` |
| `SETUP_WASTE` | `FIXED` · `PER_COLOR` · `PER_SIDE` · `COMBINED` · `PER_COLOR_SIDE`(legacy) | `clamp(setup_waste_qty + per_color×màu + per_side×mặt, min, max)`; legacy = `value×màu×mặt` |
| `RUNNING_WASTE` | `PERCENT` | `clamp(ceil(base × value), min, max)`; chọn theo dải SL qua `qty_min/qty_max` |
| `PAPER_EXTRA_WASTE` | `PERCENT` · `FIXED` · `PER_REAM` | `clamp(...)`; cờ `paper_add_to_purchase` |

## 4. Schema `norms` (evolve in-place, giữ PK)

Cột **giữ nguyên:** `id`, `norm_key` (khóa tra cứu nội bộ), `value`, `product_type`, `machine_id`,
`operation_id`, `operation_key`, `qty_min`, `qty_max`, `context`(+`context_key`), `effective_from/to`,
`note`, `created_at/updated_at`.

Cột **thêm mới** (mirror `imposition_types`, `server_default` để tương thích DB cũ):

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `code`, `name` | VARCHAR | Mã & tên rule (hiển thị, diễn giải) |
| `waste_group` | VARCHAR(24) | 1 trong 4 nhóm; NULL = rule đơn-giá cũ (mực) |
| `calculation_method` | VARCHAR(24) | tùy nhóm |
| `applicable_product_types` | JSON | multi-select; NULL/[] = tất cả |
| `applicable_machine_ids` | JSON | multi-select; NULL/[] = tất cả |
| `setup_waste_qty` / `_per_color` / `_per_side` | NUMERIC(12,3) | SETUP_WASTE |
| `min_waste_qty` / `max_waste_qty` | NUMERIC(12,3) | clamp (SETUP/RUNNING/PAPER) |
| `paper_add_to_purchase` | BOOLEAN default TRUE | PAPER_EXTRA_WASTE |
| `priority` | INTEGER default 100 | phá hòa sau điểm specificity |
| `version` | INTEGER default 1 | version tường minh trong chuỗi |
| `used_count` | INTEGER default 0 | khóa sửa khi đã dùng snapshot |
| `created_by` / `updated_by` | INTEGER FK users | audit |

**`norm_key` ⇄ `waste_group`** (service tự suy khi tạo):
`YIELD_RATE↔yield_rate` · `SETUP_WASTE↔makeready_per_color_side` · `RUNNING_WASTE↔running_waste_pct`
· `PAPER_EXTRA_WASTE↔paper_extra_waste`. Rule mực giữ `norm_key=ink_cost_per_1000_impressions`,
`waste_group=NULL`.

**Migration** (`_migrate_norms_waste_groups` trong [db_migrations.py](../backend/app/db_migrations.py)):
ADD COLUMN + backfill `waste_group` từ `norm_key`; **quy `waste_pct_of_operation` (hao) → `yield_rate`
với value = 1 − hao** (gộp khái niệm — quyết định #1).

## 5. Chọn rule & versioning

- **Chọn khi trùng phạm vi:** `specificity_score → priority → effective_from DESC → id DESC`.
  Specificity: product/machine/operation_id = 10; operation_key = 5; có dải SL = 5; +1 mỗi chiều context.
- **Version:** chuỗi theo `effective_from` (tạo bản mới ngày sau ⇒ đóng bản cũ, `version+1`); chống
  chồng lấn ngày. Không xóa cứng rule đã/đang hiệu lực — chỉ **Đóng** hoặc **tạo version mới**.

## 6. API `/api/norms`

`GET ""` (list + lọc) · `POST ""` (tạo) · `POST /{id}/close` · `DELETE /{id}` (chỉ rule tương lai)
· **`POST /{id}/duplicate`** (sao chép) · **`GET /{id}/history`** (chuỗi version) · **`POST /test`**
(chạy thử chuỗi §2, trả về từng bước cho tab Test nhanh — không ghi DB).

## 7. UI — trang Định mức & Bù hao

- **Danh sách:** cột Mã · Tên · Nhóm(badge) · Công đoạn · Cách tính · Giá trị · Áp dụng · Ưu tiên · Trạng thái.
  Lọc: nhóm · công đoạn · loại SP · máy · trạng thái · ngày hiệu lực. Action: Thêm · Sao chép · Tạo version · Đóng · Lịch sử · Test.
- **Form 5 khối:** ① Thông tin chung → ② Phạm vi áp dụng (multi-select SP/máy, dải SL, ưu tiên) →
  ③ Cách tính (đổi field theo `waste_group`, **preview realtime**) → ④ Hiệu lực/version → ⑤ **Test nhanh**.
- **Test nhanh:** nhập SL / số con / số tờ LT / màu / mặt / công đoạn / máy → gọi `POST /test` →
  hiện từng bước ra số tờ.

## 8. Diễn giải trên màn Tính giá

Panel diễn giải thêm block **"Định mức & Bù hao áp dụng"** liệt kê từng bước (tỷ lệ đạt → makeready →
running → tờ SX → hao giấy → tờ mua), **mỗi dòng nêu rule** (`code v{version}`), để khi số tờ "lạ" biết
sửa ở danh mục nào.

## 9. Validation (§7 spec)

Mã không trùng · `yield ∈ (0,1]` · running/setup không âm · `min ≤ max` · `qty_from ≤ qty_to` ·
trùng phạm vi cùng priority = Error, khác priority = Warning · không sửa rule đã dùng snapshot (tạo
version mới) · ngày hiệu lực các version không chồng lấn · **cảnh báo `yield < 80%`**.

## 10. Dữ liệu mẫu (seed, gated `SEED_DEMO`)

Nhóm A (tỷ lệ đạt): In 97% · Cán 99% · Bế 98% · Dán 99% · Xén 99.5%.
Nhóm B (setup): In 100 cố định + 30/màu + 50/mặt · Bế 30 · Cán 20.
Nhóm C (running): In 1–500=5%, 501–2.000=3%, >2.000=2% · Bế 1.5% · Cán 1%.
Nhóm D (hao giấy): cắt 1% · bốc dỡ 10 tờ · dự phòng 5 tờ/ram.

---
*Tạo 2026-07-04. Tái thiết kế danh mục #7 theo spec Định mức & Bù hao. Xem [DATA_CONTRACTS.md](./DATA_CONTRACTS.md) cho công thức tính giá tổng thể.*
