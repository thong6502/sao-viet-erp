# Đơn vị tính giá công đoạn — công thức tính lượng & tiền

Tài liệu gộp: cách tính **lượng** (basis) và **tiền** cho công đoạn trong SVN. Có **2 engine song song**
theo mô hình tái thiết (strangler):

| | Đang chạy trong Báo giá (LIVE) | Bộ mới (danh mục "Công đoạn") |
|---|---|---|
| Danh mục / model | `operations` (`op.unit`) | `cong_doan` (`pricing_basis`) |
| Engine | `services/pricing_engine.py` ✅ đã nối Báo giá | `services/routing_engine.py::basis_qty` ⛔ chưa nối |
| Số đơn vị | 4 (tờ / m² / cái / SP) | 11 (theo bảng ngành in) |

> **Trạng thái:** báo giá thật hiện dùng `operations` (4 đơn vị bên dưới). Bộ 11 đơn vị ở màn
> **Công đoạn** hiện là danh mục chuẩn hóa, **chưa tác động số báo giá** cho tới khi nối
> `routing_engine` vào `pricing_engine`.

---

## A. Engine ĐANG CHẠY — `pricing_engine.py` (danh mục `operations`, `op.unit`)

Ký hiệu:
- `qty_at_op` = lượng **tại bước** đó. Bước cuối = SL đặt; bước trước cộng dồn bù hao các bước sau
  (cascade hao ngược `reverse_snaps`), nên bước càng sớm lượng càng lớn hơn SL đặt một chút.
- `pieces_per_sheet` = số con trên 1 tờ in (từ bình bài / imposition).

Ví dụ dùng chung: **đơn 10.000 thành phẩm, 8 con/tờ, khổ tờ 65×86 cm**.

### 1. `to` — Theo tờ in
```
lượng = ⌈ qty_at_op / pieces_per_sheet ⌉
tiền  = lượng × đơn_giá  (+ setup_fee)
```
VD: ⌈10.000 / 8⌉ = **1.250 tờ**; đơn giá 300đ/tờ ⇒ 1.250 × 300 = **375.000đ**.

### 2. `m2` — Theo mét vuông
```
dt_1_tờ = rộng_cm × cao_cm / 10.000        (cm² → m²)
số_tờ   = ⌈ qty_at_op / pieces_per_sheet ⌉
lượng   = số_tờ × dt_1_tờ
tiền    = lượng × đơn_giá
```
VD: dt_1_tờ = 65×86/10.000 = **0,559 m²**; số_tờ = 1.250 → lượng = 1.250 × 0,559 = **698,75 m²**;
đơn giá 2.200đ/m² ⇒ **1.537.250đ**.

### 3. `cuon` / `cai` / `san_pham` — Theo thành phẩm
```
lượng = qty_at_op          (đúng số thành phẩm, không quy đổi)
tiền  = lượng × đơn_giá
```
VD: lượng = **10.000**; đơn giá 180đ/cái ⇒ **1.800.000đ**.

### 4. (đơn vị khác) → mặc định như mục 3 (theo thành phẩm)

### Chuỗi ra tiền (theo `internal_pricing_method`)
```
per_qty  (mặc định):  tiền = lượng × đơn_giá + setup_fee
per_hour:             tiền = (setup_giờ + lượng/tốc_độ_máy) × đơn_giá_giờ_máy
combined:             tiền = lượng × đơn_giá + giờ_máy × đơn_giá_giờ + setup_fee
```
Rồi cộng **nhân công** (theo SP / giờ / ca / khoán) và ép **giá tối thiểu** nếu có:
```
giờ_máy   = setup_giờ + lượng / tốc_độ_máy
nhân_công = SP:   lượng × đơn_giá_NC
            giờ:  số_người × giờ_máy × đơn_giá_NC_giờ
            ca:   đơn_giá_ca
            khoán: tiền_khoán
tổng_bước = max(setup + run_cost + nhân_công, giá_tối_thiểu)
```

---

## B. Engine MỚI — `routing_engine.basis_qty` (danh mục `cong_doan`, `pricing_basis`)

Chuỗi tiền 1 công đoạn:
```
run_cost = đơn_giá × basis_qty     (có bậc thang → áp bậc; có "giá 1.000 đầu" → lấy sàn first_unit_floor)
total    = setup_cost + run_cost + tiền_khuôn
total    = max(total, giá_tối_thiểu)
```

`basis_qty` quy đổi mỗi đơn vị → lượng tính tiền, từ ctx đơn hàng
(`so_to_in_gross`, `so_mat`, `dt_to_in_cm2`, `dt_thanh_pham_cm2`, `so_luong_thanh_pham`,
`so_trang`, `so_cuon`, `so_vi_tri`, `so_bao`, `so_thung`):

| `pricing_basis` | Nhãn | `basis_qty` = |
|---|---|---|
| `per_sheet` | Theo số tờ in | số tờ in gross |
| `per_finished_area` | Theo diện tích thành phẩm (cm²) | dt_thành_phẩm_cm² × SL thành phẩm |
| `per_finished_qty` | Theo số lượng thành phẩm | SL thành phẩm |
| `per_book_page` | Theo số trang sách | số trang × số cuốn |
| `per_position` | Theo số vị trí | số vị trí × SL thành phẩm |
| `per_bag` | Theo bao | số bao |
| `per_carton` | Theo thùng | số thùng |
| `per_area_sides` | Theo diện tích (cm²) và số mặt | dt_tờ_cm² × số mặt × số tờ in |
| `per_sheet_area` | Theo diện tích tờ in (cm²) | dt_tờ_cm² × số tờ in |
| `per_book_page_q4` | Theo số trang sách chia 4 | (số trang × số cuốn) / 4 |
| `per_other` | Khác | 1 (giá phẳng, nhập tay) |

Giải thích vài mục dễ nhầm:
- **số tờ in (gross)** = số tờ đã cộng bù hao (không phải số thành phẩm).
- **diện tích & số mặt**: cán/phủ 2 mặt thì × số mặt; tính trên toàn bộ tờ in đã chạy.
- **trang sách chia 4**: 1 tờ gấp ra 4 trang (in sách) → quy công theo "tay" thay vì từng trang.
- **vị trí**: ép kim/bế nhiều vị trí trên 1 thành phẩm → nhân số vị trí với số lượng.
- **Khác** = basis 1 nên `run_cost = đơn_giá` (một mức cố định).

---

## C. Việc còn lại để bộ 11 đơn vị tác động báo giá

Nối `routing_engine` vào `pricing_engine` (thay/bổ sung khối "Operation Cost Lines"):
dựng `ctx` từ dữ liệu đơn (số tờ in gross, diện tích cm², SL thành phẩm, số trang/cuốn,
số vị trí, quy cách bao/thùng) → gọi `basis_qty` theo `cong_doan.pricing_basis` → ra tiền.
Một số ctx (số trang, số vị trí, quy cách đóng gói) cần bổ sung ở dữ liệu đơn/loại sản phẩm.
