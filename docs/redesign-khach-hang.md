# Redesign module Khách hàng (spec-06 v2)

> Trạng thái: **ĐÃ CHỐT THIẾT KẾ — chờ "làm đi"**. Gộp mọi quyết định trong hội thoại
> 2026-07-14. Nguyên tắc: gộp vào màn/luồng đang có, bỏ số giả, ít thao tác.

## 0. Bối cảnh & mục tiêu

Module Khách hàng hiện trộn nhiều thứ "tự gán" và số **mock** (tier thân thiết, "trả đúng
hạn", gauge uy tín 88, widget "100% đúng hạn") gây hiểu nhầm. Đợt này:

1. **Rút gọn form** Thêm/Sửa còn đúng thông tin định danh + xuất hóa đơn.
2. **Bỏ mọi tự-phân-loại / badge fake**, thay bằng **thẻ gán tay** (`customer_tags`).
3. Đưa **chính sách tài chính** (hạn mức · điều khoản thanh toán · chiết khấu min/max ·
   biên lợi nhuận min/max) vào **sửa inline ở màn chi tiết**, gate bằng **1 quyền duy nhất**.

## 1. Quyết định đã chốt

| # | Quyết định |
|---|---|
| A | Form **Thêm = Sửa**, chỉ còn 6 mục: Mã KH (tự sinh `KH…`) · Tên · **Loại (Cá nhân/Công ty)** · Người phụ trách · MST · Địa chỉ (xuất HĐ) · Email (HĐĐT). |
| B | **Bỏ Trạng thái** (lead/active/inactive) khỏi UI + logic. Cột `status` để *dormant*. |
| C | **Bỏ hết** tier (thân thiết/đối tác/mới + sao) và badge/gauge/widget **fake** (trả đúng hạn, uy tín 88, "100% đúng hạn"). Badge = **thẻ gán tay**. |
| D | **Sửa chính sách tài chính INLINE** ở Dashboard chi tiết (thay widget "Thanh toán" fake). |
| E | **1 quyền chung** gate toàn bộ chính sách tài chính (mở rộng nghĩa `can_set_credit_terms`). |
| F | Chiết khấu **min/max** + biên **min/max** **THAY** 2 ô "chiết khấu mặc định" cũ (trade/buyer → dormant). |
| G | Loại: Cá nhân → **ẩn MST**; Công ty → **hiện MST (tùy chọn**, cảnh báo trùng mềm giữ nguyên). |

## 2. Thay đổi schema (migration 0060 — chỉ ADD COLUMN)

Bảng `customers`, thêm:

| Cột | Kiểu | Default | Ý nghĩa |
|---|---|---|---|
| `customer_kind` | VARCHAR(12) NOT NULL | `'cong_ty'` | `ca_nhan` \| `cong_ty` — quyết định hiện/ẩn MST. |
| `discount_min_pct` | FLOAT NULL | — | Sàn chiết khấu cho phép (%). |
| `discount_max_pct` | FLOAT NULL | — | Trần chiết khấu cho phép (%). |
| `margin_min_pct` | FLOAT NULL | — | Sàn biên lợi nhuận yêu cầu (%). |
| `margin_max_pct` | FLOAT NULL | — | Trần biên lợi nhuận (%). |

**Dormant (giữ cột, NGỪNG dùng — SQLite không drop gọn):** `status`,
`discount_trade_pct`, `discount_buyer_pct`. Cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test).

> Ràng buộc nhập (tầng service): mỗi % ∈ [0,100]; `min ≤ max` (cả chiết khấu lẫn biên);
> để trống = chưa đặt rào (không chặn báo giá). *Việc CHẶN báo giá theo rào này thuộc
> phân hệ Báo giá — đợt này chỉ LƯU + hiển thị, chưa nối engine (SEAM để lại).*

## 3. Thay đổi quyền RBAC (gộp về 1)

- **Giữ nguyên cột** `role_permissions.can_set_credit_terms` (đã thêm ở migration 0059) —
  **mở rộng nghĩa** thành "chính sách tài chính khách": hạn mức + điều khoản thanh toán +
  chiết khấu min/max + biên min/max.
- Label ma trận vai trò đổi: *"Thiết lập điều khoản tín dụng"* → **"Thiết lập chính sách
  tài chính"**. Cập nhật comment model + `DB_SCHEMA.md` + `rbac_service`/schema mô tả.
- **Module Khách hàng NGỪNG dùng** `view_discount` (2 field discount cũ bỏ). Cột/quyền
  `view_discount` vẫn còn cho module khác (kiểm lại lúc build — nếu chỉ Khách hàng dùng thì
  để dormant, không xóa cột).
- **Hiển thị vs sửa (đã chốt: cho xem hết):** TẤT CẢ mục tài chính (hạn mức · điều khoản ·
  chiết khấu min/max · biên min/max) **ai cũng xem** (read-only). **Sửa** cần
  `set_credit_terms`. Không ẩn theo quyền.

## 4. Form Thêm/Sửa (mục A, G)

- Dùng chung `CustomerFormDialog`, cùng field cho cả Thêm lẫn Sửa.
- **Field:** Mã KH (read-only) · Tên (bắt buộc) · **Loại** (radio/segmented Cá nhân/Công ty)
  · Người phụ trách · **MST** (chỉ hiện khi Công ty) · Địa chỉ · Email.
- **Người phụ trách:** mặc định chính mình; **khóa** khi không có quyền `reassign` (kể cả
  form Thêm — hiện đang cho chọn tự do, sẽ siết).
- **Bỏ khỏi form:** SĐT + Người liên hệ (→ **tab Liên hệ**), Hạn mức/Điều khoản/Chiết khấu
  (→ **mục D**), Trạng thái (bỏ).
- **Giữ cột** `phone`, `contact_name` (vẫn dùng cho tìm kiếm/hiển thị + tab Liên hệ), chỉ
  bỏ khỏi form.

## 5. Bỏ Trạng thái (mục B)

- FE: bỏ ô chọn trạng thái ở form; bỏ tab lọc theo trạng thái; bỏ badge trạng thái.
- BE: bỏ `status` khỏi payload create/update + validate + filter list. Cột `status` giữ
  default `active` để dữ liệu cũ không vỡ; không expose ra UI.

## 6. Bỏ tự phân loại + dùng thẻ (mục C)

**Bỏ (fake/tự gán):**
- Tier: `classify_tier`, `TIER_*`, `loyal_count`/`partner_count`, `CustomerStat.tier`,
  `CustomerRow.tier`, `CustomerDashboard.tier`.
- FE: `TierBadge`, ★ sao, cột "Tier" ở list, KPI "thân thiết/tổng", 2 tab lọc
  "Thân thiết"/"Đối tác lâu năm", tiêu đề header "KHÁCH THÂN THIẾT ★★★★".
- Mock: `mockAR`, `CreditGauge` (uy tín 88), badge "Trả đúng hạn", widget "Thanh toán"
  fake (100% đúng hạn / TB 12 ngày / trễ tối đa).

**Giữ (số THẬT):** doanh số 12T (bar) · số đơn · TB/đơn · cơ cấu SP (donut) · tần suất đặt
(heatmap) · Lịch sử mua hàng/báo giá · tab **Cần theo dõi** (care-task thật).

**Thay bằng thẻ:**
- Badge ở **list** + **header chi tiết** = `customer_tags` (nút "Gắn thẻ" đã có).
- List **lọc theo thẻ** (thay 2 tab tier). Giữ ô tìm kiếm + tab "Cần theo dõi".
- KPI header còn: **Tổng KH · Mới trong tháng · TB đơn · Doanh số** (đều thật).

## 7. Khối "Chính sách tài chính" — inline ở Dashboard chi tiết (mục D, E, F)

Thay `section` widget "Thanh toán" fake bằng card **"Chính sách tài chính"**:

```
┌ Chính sách tài chính ──────────────── [Sửa ✎ nếu có quyền] ┐
│ Hạn mức công nợ        50.000.000 đ                         │
│ Số ngày công nợ tối đa 30 ngày kể từ ngày xuất HĐ           │
│ Chiết khấu cho phép    0% – 10%                             │
│ Biên lợi nhuận         ≥ 15% (tối đa 40%)                   │
└────────────────────────────────────────────────────────────┘
```

> **Cập nhật 2026-07-15:** "Điều khoản thanh toán" (dropdown kiểu prepay/net-EOM + %
> trả trước + ghi chú) đã **BỎ** theo yêu cầu; thay bằng **một ô số** *"Số ngày công nợ
> tối đa"* (`payment_term_days`) — net terms tính từ ngày xuất hóa đơn. Cặp với hạn mức
> tiền thành chính sách "cho nợ". Mọi mục tài chính **ai cũng xem** (cho xem hết); chỉ
> `set_credit_terms` mới sửa.

- Read-only mặc định; bấm **Sửa ✎** (chỉ khi có quyền) → chuyển các dòng thành input tại
  chỗ → Lưu gọi **`PUT /api/customers/{id}/financial`** (endpoint RIÊNG, gate `set_credit_terms`).
  *Lý do tách khỏi PUT định-danh:* nếu dùng chung, form Thêm/Sửa (không gửi tài chính) sẽ
  vô tình XÓA hạn mức/rào. Endpoint riêng = mỗi lần lưu chỉ đụng đúng nhóm field của nó.
  Form Thêm/Sửa (`POST` / `PUT /api/customers/{id}`) chỉ còn field ĐỊNH DANH.
- Người thiếu quyền: thấy hạn mức + điều khoản (read-only), **không thấy** khối chiết
  khấu/biên và không có nút Sửa.
- Bỏ dòng hành vi fake (đúng hạn %, TB ngày trả) — nếu muốn giữ chỗ, ghi "Chờ phân hệ
  Công nợ".

## 8. Ảnh hưởng file (danh sách build)

**Backend**
- `models/customer.py` — +`customer_kind`, +4 cột bound; comment dormant cho status/discount cũ.
- `db_migrations.py` — migration `0060_customer_kind_and_pricing_bounds`.
- `schemas/customer.py` — Create/Update: +`customer_kind`, +4 bound, **bỏ** status/discount cũ
  khỏi input; `CustomerRow`: +kind/+bounds, **bỏ** tier/discount cũ; `CustomerKpis` bỏ
  loyal/partner; `CustomerDashboardOut` bỏ tier.
- `services/customer_service.py` — validate kind + bounds (0–100, min≤max), gate
  `allow_financial` (đổi tên khái niệm từ allow_credit_terms → phủ cả bounds); bỏ nhánh status.
- `services/customer_analytics.py` — bỏ tier khỏi list_stats + dashboard (giữ revenue/mix/heatmap).
- `routers/customers.py` — truyền quyền gộp; `_row` bỏ tier + ẩn bounds khi thiếu quyền;
  KPIs rút gọn; bỏ filter status; (giữ ẩn số nhạy cảm).
- `docs/DB_SCHEMA.md` — 5 cột mới + đổi mô tả `can_set_credit_terms`.
- `tests/` — sửa test tier/status/discount cũ; +test kind/MST + bounds + gate.

**Frontend**
- `api/client.ts` — `CustomerRow`/`CustomerInput`: +`customer_kind`+bounds, bỏ tier/status/discount cũ; `ModuleCapability` giữ `can_set_credit_terms` (đổi label chỗ dùng).
- `components/PermissionMatrix.tsx` — đổi label quyền; bỏ dòng `view_discount` của khach_hang.
- `pages/KhachHangPage.tsx` — form 6 field + Loại/MST; bỏ status; bỏ tier/mock/gauge; badge=thẻ;
  lọc theo thẻ; card "Chính sách tài chính" inline edit.
- `pages/khach-hang.css` — style Loại segmented, card tài chính, inline edit; dọn css tier/gauge.

## 9. Kế hoạch build theo phase (mỗi phase xanh mới sang tiếp)

1. **P1 Schema + RBAC**: migration 0060 + model + DB_SCHEMA + đổi nghĩa/label quyền.
2. **P2 Backend**: schema Pydantic + service (kind/bounds/gate, bỏ status) + analytics (bỏ tier)
   + router + tests. `init.ps1` xanh.
3. **P3 FE form**: Thêm/Sửa 6 field + Loại/MST + siết người phụ trách; bỏ status. `tsc` 0.
4. **P4 FE chi tiết**: card "Chính sách tài chính" inline edit (hạn mức/điều khoản/CK/biên);
   gỡ widget/gauge fake.
5. **P5 FE list/header**: thẻ thay tier; lọc theo thẻ; gỡ cột/KPI/tab tier.
6. **P6 Verify**: `init.ps1` (dán số thật) + `tsc` 0 + click thử 2 vai (có/không quyền).

## 10. Rủi ro / lưu ý

- **Cột dormant** (status, discount_trade/buyer): không xóa (SQLite + guard doc); chỉ ngừng
  dùng — ghi rõ "dormant" trong model + DB_SCHEMA để không hiểu nhầm.
- Bỏ tier đụng nhiều test (`test_customer_analytics_api`, `test_customers_api`) → sửa kèm.
- **Chưa nối engine Báo giá** với rào chiết khấu/biên — đợt này chỉ lưu+hiển thị (SEAM để lại).
- Có session khác trên repo → commit chỉ file mình đụng.
