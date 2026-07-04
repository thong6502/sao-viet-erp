# Vật tư & Đơn giá vật tư (danh mục #2) — thiết kế đầy đủ

> **Vai trò:** Danh mục #2 trong [DANH_MUC_TINH_GIA.md](./DANH_MUC_TINH_GIA.md). Nuôi trực tiếp
> **Tiền giấy**, **Tiền mực**, và vật tư phụ/bao bì trong Giá thành trực tiếp.
> **Engine:** [pricing_engine.py](../backend/app/services/pricing_engine.py) đọc material + material_costs.
> Khổ giấy lấy từ danh mục **Khổ giấy** ([[svn-khogiay-full-spec]]); hao hụt ở **Định mức #7** ([DINH_MUC_BU_HAO.md](./DINH_MUC_BU_HAO.md)).

---

## 1. Quyết định đã chốt (2026-07-04)
1. **Mực chuyển hẳn về Vật tư:** mực là 1 material (nhóm `ink`), đơn giá ở `material_costs`
   (`price_unit='nghin_luot'` = đ/1.000 lượt). Engine đọc giá mực **từ material**, **bỏ** norm
   `ink_cost_per_1000_impressions` của #7.
2. **NCC = string (MVP):** `default_supplier` trên material + `supplier` trên từng dòng giá — không
   dựng catalog NCC riêng (giống `outsource_supplier` ở Công đoạn).
3. **Phạm vi đầy đủ:** 2 tab + form 4 tab + bậc số lượng + price_type/vat/transport/moq/lead_time +
   version + link khổ giấy + Test quy đổi/tính tiền + diễn giải nguồn giá.

## 2. Nhóm vs Loại
- `material_group` (mới, trục UI): `paper` · `ink` · `film` · `glue` · `packaging` · `auxiliary`.
- `material_type` (giữ nguyên, trục ENGINE): paper/carton/decal/pp/canvas/formex/lamination/film/glue/chemical.
  Engine quyết định **tính theo tờ hay m²** dựa trên `material_type` — KHÔNG đổi. `material_group` chỉ để
  gom nhóm + đổi field form (giống norm_key ⇄ waste_group ở #7).

## 3. Schema — `materials` (evolve in-place)
Giữ: code, name, material_type, unit, min_fee, width/height/gsm/thickness_mm, default_waste_pct,
min_purchase_qty, paper_family, surface, is_active. **Thêm:**

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `material_group` | VARCHAR(20) | 1 trong 6 nhóm; backfill từ material_type |
| `default_supplier` | VARCHAR(150) | NCC mặc định (string) |
| `base_uom` / `purchase_uom` / `consumption_uom` | VARCHAR(16) | ĐVT tồn/mua/tiêu hao |
| `conversion_method` | VARCHAR(24) | `gsm_area` (kg↔tờ) · `ream_500` · `area_m2` · `fixed_factor` · `none` |
| `conversion_factor` | NUMERIC(12,4) | hệ số cố định (1 ram=500 tờ) |
| `ink_type` / `ink_color_system` / `ink_color_code` | VARCHAR | nhóm ink |
| `film_type` | VARCHAR(32) | nhóm film |
| `version` | INTEGER default 1 | version tường minh |

## 4. Schema — `material_costs` (evolve in-place)
Giữ: material_id, price_unit, unit_price, effective_from/to. **Thêm:**

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `supplier` | VARCHAR(150) | NCC của dòng giá |
| `paper_size_id` | INTEGER FK paper_sizes | giá theo khổ (nullable) |
| `price_type` | VARCHAR(20) default 'standard' | purchase / standard / temporary |
| `vat_included` | BOOLEAN default false | thông tin |
| `transport_fee` | BIGINT default 0 | phí vận chuyển (cộng 1 lần vào dòng giấy) |
| `moq` | NUMERIC(12,2) default 0 | SL mua tối thiểu (thông tin) |
| `lead_time_days` | INTEGER default 0 | thông tin |
| `quantity_from` / `quantity_to` | NUMERIC(14,2) | **bậc số lượng** (nửa-mở [from,to)) |
| `version` | INTEGER default 1 | version |

**Unique "hiện hành"** đổi: (material_id, price_unit, coalesce(quantity_from), coalesce(quantity_to),
coalesce(supplier), coalesce(paper_size_id)) WHERE effective_to IS NULL — cho phép nhiều bậc/NCC/khổ cùng lúc.

## 5. Engine dùng thế nào
- **Tiền giấy:** `số tờ mua × đơn giá` với quy đổi theo `price_unit`: `to` (nguyên giá) · `ram` (÷500) ·
  `kg` (kg/tờ = rộng×cao/10000 × gsm/1000) · `m2` (×diện tích tờ). Cộng `transport_fee`. Giữ min_fee.
- **Chọn giá theo bậc:** trong các dòng giá hiệu lực, chọn dòng có `[quantity_from, quantity_to)` chứa
  **số tờ mua** (bậc null = mọi SL). Ưu tiên bậc cụ thể; hòa → effective_from mới nhất.
- **Tiền mực (mới):** tìm material nhóm `ink` (spec truyền `ink_material_id`, hoặc mực active mặc định),
  lấy giá `price_unit='nghin_luot'` → `Tiền mực = ⌈lượt-màu/1000⌉ × đơn giá`. Không còn đọc norm.
- **Nguồn giá:** dòng chi phí ghi `price_code`/`supplier` để diễn giải "Nguồn giá: PRICE_x" trên Tính giá.

## 6. API `/api/materials`
Giữ CRUD + `/costs` + `/clone` + `/toggle-active`. Thêm field mới vào schema; `/costs` nhận đủ
field bậc/NCC/khổ; thêm **`POST /convert`** (test quy đổi) và **`POST /price-test`** (test tính tiền
giấy/mực/màng), `GET /{id}/costs/history`.

## 7. UI — 2 tab
- **Tab Danh mục vật tư:** list (Mã/Tên/Nhóm/Loại/ĐVT/NCC/Trạng thái) + lọc nhóm/loại/NCC/trạng thái;
  form **4 tab** (Thông tin chung · Thuộc tính theo nhóm · Đơn vị & quy đổi + preview · Bảng giá hiện hành).
- **Tab Bảng giá:** thêm/sửa giá với NCC + khổ + đơn vị + bậc SL + price_type + vat/transport/moq/lead_time +
  effective; **Test quy đổi** + **Test tính tiền**.

## 8. Validation §12
Tên không trùng · nhóm bắt buộc · giấy cần GSM nếu giá theo kg · đơn giá ≥0 · đơn vị giá hợp nhóm ·
ram cần hệ số (mặc định 500) · overlap ngày cùng (vật tư+NCC+khổ+đơn vị+bậc) · không sửa giá đã dùng
snapshot (tạo version) · vật tư inactive không chọn ở phiếu mới.

## 9. Dữ liệu mẫu §10
Giấy Couche/Ivory/Duplex/Kraft (giá kg) · **Mực** C/M/Y/K/Pantone (giá nghin_luot) · Màng bóng/mờ/metalize
(m²) · Keo hộp/gáy (kg) · Bao bì thùng carton/pallet (cái).

---
*Tạo 2026-07-04. Tái thiết kế danh mục #2. Mực dời từ norm (#7) sang material theo quyết định B.*
