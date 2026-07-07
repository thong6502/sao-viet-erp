# SPEC — MODULE QUY TẮC BÌNH BÀI (Imposition Rule)

> Master data khai báo **cách bình bài**, tái dùng cho nhiều sản phẩm, có **version (v1, v2, v3)**.
> Là **mắt xích đầu tiên của engine tính giá** + có **live preview bằng ảnh** + **live công thức**.

---

## 1. Tổng quan

### 1.1 Bản chất
Quy tắc bình bài quyết định **số con / tay / blank trên 1 tờ in** — con số kéo theo toàn bộ tiền giấy, tiền kẽm, tiền in, tiền gia công. Nó không phải form nhập liệu chết mà là **đầu vào sống của engine tính giá**.

### 1.2 Ba trụ của module
1. **Nối engine tính giá:** output bình bài chảy thẳng vào các dòng chi phí (§7).
2. **Live preview bằng ảnh:** mỗi thay đổi nhập liệu → vẽ lại sơ đồ tờ in tức thì (§9.4).
3. **Live công thức:** panel công thức thay số real-time + hiện luôn tác động tới tiền (§9.5).

### 1.3 Trách nhiệm
- Lưu **cách xếp** (step-and-repeat / tay sách / dàn khuôn / lặp theo trục) + tham số layout dùng chung.
- Cung cấp cho engine đủ tham số tính: số con/tay/blank → số tờ in → số tờ nguyên → % hao → kẽm.
- Quản lý version + cho phép báo giá ghim đúng version đã dùng.

### 1.4 KHÔNG làm gì (ranh giới)
- Không giữ: nhíp, khổ máy, thông số trục → **Máy in**.
- Không giữ: khổ thành phẩm, số trang, kiểu đóng (binding), dieline, bleed thật → **Sản phẩm**.
- Không tự chọn khổ tờ in — đó là việc của **engine** (dựa Máy in + Tờ nguyên). Quy tắc chỉ mô tả *cách xếp*.

---

## 2. Vị trí trong hệ thống

```
              QUY TẮC BÌNH BÀI (version)  ┐
              MÁY IN (nhíp, khổ máy, trục) ├─►  ENGINE BÌNH BÀI  ─►  con/tay/blank · tờ in · tờ nguyên · kẽm · %hao
              SẢN PHẨM (khổ, trang, ...)   │                              │
              TỜ NGUYÊN (khổ, gsm, giá)    ┘                              ▼
                                                              ENGINE TÍNH GIÁ (§7)
                                                                         ▼
                                                    tiền giấy · kẽm · in · gia công → giá bán
```

Liên kết:
```
LOẠI SẢN PHẨM.imposition_rule_id → quy_tac_binh_bai.id      (gán ở module Loại SP)
quy_tac_binh_bai ─1..n─► quy_tac_binh_bai_version           (v1, v2, v3)
bao_gia_dong / lenh_sx ─► (rule_id + version_no)            (ghim để tái lập)
```

---

## 3. Mô hình dữ liệu

### 3.1 `quy_tac_binh_bai` (HEADER — danh tính)

| Field | Kiểu | Bắt buộc | Default | Ràng buộc / Mô tả |
|---|---|---|---|---|
| id | PK | ✓ | | |
| ma | string(30) unique | ✓ | | viết hoa, khoá nghiệp vụ, không đổi sau tạo |
| ten | string(150) | ✓ | | tên hiển thị |
| mo_ta | text | | null | ghi chú cách dùng |
| trang_thai | enum(active, inactive) | ✓ | active | inactive = ẩn khi gán; không xoá nếu đang tham chiếu |
| created_at | datetime | ✓ | now | |
| created_by | FK user | ✓ | | |
| updated_at | datetime | | | cập nhật khi sửa header |

> Header **không chứa cấu hình bình bài** — mọi tham số nằm ở version.

### 3.2 `quy_tac_binh_bai_version` (VERSION — cấu hình)

**Quản lý version**

| Field | Kiểu | Bắt buộc | Default | Ràng buộc |
|---|---|---|---|---|
| id | PK | ✓ | | |
| rule_id | FK → header | ✓ | | |
| version_no | int | ✓ | | 1, 2, 3… ; `unique(rule_id, version_no)` |
| is_current | bool | ✓ | true | đúng **1** dòng `true` mỗi rule |
| ghi_chu_version | string(255) | | null | lý do đổi version |
| created_at | datetime | ✓ | now | |
| created_by | FK user | ✓ | | |

**Công tắc chính**

| Field | Kiểu | Default | Mô tả |
|---|---|---|---|
| layout_mode | enum(step_repeat, signature, nesting, repeat_around) | step_repeat | quyết định thuật toán + nhóm field có hiệu lực. Là "loại của quy tắc" (4 giá trị), KHÁC loại sản phẩm (nhiều loại SP → 1 mode) |

**Hình học chung (mọi mode) — cả 6 field đều ảnh hưởng giá (§7.3)**

| Field | Kiểu | Default | Mô tả · tác động giá |
|---|---|---|---|
| side_margin_mm | number | 5 | lề hông 2 bên tờ in → ↑ thì con/tờ ↓ → giấy ↑ |
| tail_colorbar_mm | number | 8 | dải thang màu đuôi tờ → ↑ thì con/tờ ↓ |
| gutter_mm | number | 4 | rãnh giữa 2 con → ↑ thì con/tờ ↓ ; gang-run cần ≥ 2·bleed + mạch dao (~6–10mm) |
| allow_rotate | bool | true | xét con ở cả 2 hướng, lấy hướng nhiều con hơn → thường giấy ↓ |
| grain_constraint | enum(none, canh_dai, song_song_gay, theo_song) | none | ràng buộc thớ; ép hướng xấu → con ↓ → giấy ↑ |
| bleed_default_mm | number | 3 | bleed mặc định nếu SP không khai riêng (SP ghi đè được) |

**Field theo `layout_mode` (chỉ có hiệu lực khi đúng mode)**

*A. step_repeat*
| Field | Kiểu | Default | Mô tả |
|---|---|---|---|
| allow_gang | bool | false | cho ghép nhiều job khác nhau chung 1 tờ in → chia sẻ tờ+kẽm |
| min_gutter_mm | number | 4 | rãnh tối thiểu khi ghép bài |

*B. signature*
| Field | Kiểu | Default | Mô tả |
|---|---|---|---|
| pages_per_sig | enum(4, 8, 16, 32, auto) | auto | trang mỗi tay. auto = engine chọn tay lớn nhất mà (trang/tay ÷ 2) trang vừa 1 mặt tờ in ≤ khổ máy |
| work_style | enum(sheetwise, work_turn) | sheetwise | sheetwise: kẽm = tay×màu×2. work_turn: 1 bộ kẽm cả 2 mặt, cắt đôi ra 2 cuốn → kẽm = tay×màu |

*(binding lấy từ Sản phẩm; creep suy ra từ binding — không khai ở đây.)*

*C. nesting*
| Field | Kiểu | Default | Mô tả |
|---|---|---|---|
| nest_method | enum(grid, true_shape) | grid | grid: xếp lưới chữ nhật. true_shape: nest hình thật (tiết kiệm hơn) |
| matrix_allowance_mm | number | 5 | chừa khung thải (matrix) giữa blank |

*(dieline lấy từ Sản phẩm.)*

*D. repeat_around*
| Field | Kiểu | Default | Mô tả |
|---|---|---|---|
| lanes | int / auto | auto | số làn tem ngang khổ cuộn. auto = floor(khổ cuộn / (rộng tem + gap)) |
| gap_around_mm | number | 3 | khoảng cách giữa tem theo chu vi |

*(bước răng, đường kính trục lấy từ Máy in.)*

**Guardrails (ngưỡng cảnh báo/chặn)**

| Field | Kiểu | Mô tả |
|---|---|---|
| min_pages | int | cảnh báo nếu số trang < ngưỡng (keo ≥ 40) |
| max_pages | int | cảnh báo/chặn nếu vượt (ghim ≤ 64) |
| min_spine_mm | number | cảnh báo gáy quá mỏng khi đóng keo |
| warn_on_grain_violation | bool (default true) | bật cảnh báo khi hướng đặt vi phạm grain_constraint |

### 3.3 `folding_scheme` (bảng phụ — dùng cho signature)

| Field | Kiểu | Mô tả |
|---|---|---|
| id | PK | |
| scheme_code | enum(F4, F8, F16, F32) | sơ đồ gấp (F16 = tay 16 trang) |
| folds | int | số lần gấp (F16 = 3) |
| page_position_map | json | ánh xạ trang → vị trí ô trên tờ in (mỗi mặt) |
| rotation_map | json | góc xoay từng trang (0 / 180°) |
| work_style | enum(sheetwise, work_turn) | sơ đồ áp cho kiểu trở nào |

Ví dụ `page_position_map` tay 8 trang (F8, 1 tờ gấp 2 lần):
```
Mặt trước (2×2):  [ 5 | 4 ]        Mặt sau (2×2):  [ 3 | 6 ]
                  [ 8 | 1 ]                        [ 2 | 7 ]
rotation: hàng trên xoay 180°
```

### 3.4 Ghim ở nơi tiêu thụ
`bao_gia_dong` / `lenh_san_xuat` lưu thêm `rule_id + version_no` → mở lại luôn ra đúng số cũ dù rule đã lên version mới.

---

## 4. Versioning (v1, v2, v3)

### 4.1 Trạng thái
Mỗi version chỉ có cờ `is_current` (true/false). Không có draft/archived — chỉ **v1, v2, v3**, cái mới nhất `is_current = true`.

### 4.2 Chuyển đổi
```
TẠO RULE MỚI  → sinh version v1 (is_current = true)
SỬA CẤU HÌNH  → clone version is_current
                → version_no = max(version_no)+1
                → version mới is_current = true
                → version cũ  is_current = false (giữ nguyên, khoá)
XEM LẠI       → chọn version bất kỳ để xem (v cũ chỉ đọc)
```

### 4.3 Bất biến & xoá
- Version `is_current = false` → immutable (chỉ đọc), không xoá.
- Version đang bị báo giá/lệnh SX ghim → không xoá.
- Xoá header chỉ khi không có SP gán VÀ không có báo giá ghim; ngược lại chỉ cho `inactive`.

### 4.4 Ảnh hưởng tới báo giá
| Tình huống | Version dùng |
|---|---|
| Lập báo giá mới | version `is_current` |
| Mở lại / in lại báo giá cũ | version đã ghim (`version_no` trên dòng báo giá) |
| Rule lên v3 sau khi báo giá ghim v2 | báo giá cũ vẫn dùng v2 |
| Tái bản (rerun) job cũ | mặc định version đã ghim; user chọn "cập nhật version mới" thủ công |

---

## 5. Thuật toán từng `layout_mode`

### 5.0 Lõi hình học chung (mọi mode gọi)
```
FUNCTION usable_area(tờ_in, máy, rule):
    Wu = tờ_in.rộng - 2·rule.side_margin_mm
    Lu = tờ_in.dài  - máy.gripper_mm - rule.tail_colorbar_mm
    return (Wu, Lu)

FUNCTION fit_count(Wu, Lu, w, h, gutter, allow_rotate):
    n0  = floor((Wu+gutter)/(w+gutter)) × floor((Lu+gutter)/(h+gutter))
    n90 = allow_rotate ? floor((Wu+gutter)/(h+gutter)) × floor((Lu+gutter)/(w+gutter)) : 0
    return max(n0, n90)

FUNCTION waste_pct(count, dt_con, dt_tờ_in):
    return 1 − (count × dt_con) / dt_tờ_in

RÀNG BUỘC luôn kiểm: tờ_in ≤ khổ_máy(max) & ≥ min & hướng thoả grain_constraint
```

### 5.1 step_repeat — Xếp con giống hệt
**Dùng cho:** name card, tờ rơi, poster, lịch tờ, tem rời.
```
cell_w = rộng_tp + 2·bleed
cell_h = dài_tp  + 2·bleed
(Wu, Lu) = usable_area(tờ_in, máy, rule)
con_per_sheet = fit_count(Wu, Lu, cell_w, cell_h, gutter, allow_rotate)
```
**Ví dụ:** name card 90×53, bleed 2 → cell 94×57. Tờ in 430×650, nhíp 12, lề 5, thang màu 8, gutter 4:
usable 420×630 → n0 = floor(424/98)×floor(634/61) = 4×10 = 40 ; n90 = 6×6 = 36 → **40 con/tờ in**.
**Edge:** con lớn hơn vùng in được → `con_per_sheet = 0` → lỗi E-FIT-0.

### 5.2 signature — Bình tay sách
**Dùng cho:** sách, catalogue, tạp chí, brochure nhiều trang.
```
[A] Chọn trang/tay
    if pages_per_sig == auto:
        pages_per_sig = max{4,8,16,32} sao cho (pages_per_sig ÷ 2) trang
                        xếp vừa 1 MẶT tờ in ≤ khổ máy   (gọi step_repeat cho trang)
[B] Số tay
    số_tay = ceil(P / pages_per_sig)
    dư = P mod pages_per_sig
    if dư > 0: tay cuối dùng scheme nhỏ hơn (vd dư 4 → 1 tay F4) HOẶC chèn trang trắng
[C] Sơ đồ trang
    với mỗi tay: tra folding_scheme[F(pages_per_sig)] → page_position_map + rotation_map
    thứ tự trang theo binding:
        saddle (ghim) → xếp LỒNG (nested): tay ngoài mang trang (1, cuối)
        perfect (keo) → xếp CHỒNG (gathered): mỗi tay 1 khối trang liên tục
[D] Creep (chỉ saddle)
    tay thứ k từ trong: offset_k ≈ caliper_ruột × k → dịch trang về gáy
[E] Kẽm
    số_kẽm = số_tay × số_màu × (work_style == sheetwise ? 2 : 1)
[F] Tờ in
    số_tờ_in = số_tay × Q + bù_hao_mỗi_tay
[G] Bìa (nếu SP.cover_separate)
    bình riêng 1 tay bìa; spine = (P/2) × caliper_ruột; giấy bìa riêng
```
**Ví dụ:** sách A5, P=96, keo, 4/4, sheetwise, Q=1000, tay auto=16:
số_tay = 6 ; kẽm = 6×4×2 = **48** ; tờ in = 6×1000 + ~900 = **~6.900** ; spine = 48×caliper ; creep = 0 (keo). Bìa in riêng.
**Edge:** P không bội 4 → chèn trang trắng (W-P4). Ghim mà P > max_pages → W-PAGES-MAX.

### 5.3 nesting — Dàn khuôn bao bì
**Dùng cho:** hộp giấy, bao bì (blank từ dieline).
```
if nest_method == grid:
    blanks = floor(Wu/(blank_w+matrix)) × floor(Lu/(blank_h+matrix))  (2 hướng, tôn trọng thớ/sóng)
if nest_method == true_shape:
    blanks = nest hình thật (xếp so le/xoay) → nhiều hơn grid
matrix_pct = 1 − (blanks × dt_blank)/(dt_tờ_in)
```
**Ví dụ:** blank hộp 250×180, tờ in 720×1020, grid, matrix 5:
floor(1020/255)×floor(720/185) = 4×3 = **12 blank/tờ**, matrix_pct ≈ **26%**.

### 5.4 repeat_around — Lặp theo trục (tem nhãn cuộn)
**Dùng cho:** tem/nhãn decal in cuộn (flexo).
```
repeat_length = số_răng × bước_răng            (từ Máy in)
tem_quanh_trục = floor(repeat_length / (cao_tem + gap_around))
if lanes == auto:
    lanes = floor(khổ_cuộn / (rộng_tem + gap_around))
tem_per_vòng = lanes × tem_quanh_trục
tem_per_m    = tem_per_vòng / (repeat_length/1000)
```

---

## 6. Hợp đồng engine (I/O)

```
INPUT:
  rule_version  : { layout_mode, side_margin, tail_colorbar, gutter, allow_rotate,
                    grain_constraint, bleed_default, <mode fields>, <guardrails> }
  may_in        : { gripper_mm, max_w, max_h, min_w, min_h, truc?{teeth, pitch, dia} }
  san_pham      : { dài_tp, rộng_tp, bleed?, so_trang?, binding?, cover_separate?, dieline? }
  to_nguyen     : { dài_ng, rộng_ng, gsm, gia_kg, thớ }
  so_luong, so_mau_truoc, so_mau_sau

OUTPUT:
  { layout_mode,
    kho_to_in : { dài, rộng, kiểu_cắt_từ_tờ_nguyên },
    don_vi_per_to_in,          // con | tay | blank | tem
    to_in_per_nguyen,
    tong_don_vi_per_nguyen,
    so_to_in, so_to_nguyen, so_kem,
    so_tay?, danh_sach_tay?, spine_mm?, creep_mm?,
    hao_hinh_hoc_pct,
    warnings: [ {code, message} ] }
```

---

## 7. TÍCH HỢP ENGINE TÍNH GIÁ (trụ #1)

### 7.1 Bình bài là đầu chuỗi tính giá
Output bình bài là **input bắt buộc** của mọi dòng chi phí. Không có nó, không tính được tiền.

### 7.2 Chuỗi tính (ấn phẩm phẳng)
```
① số con/tờ in            ← BÌNH BÀI
② số tờ in cần   = ceil(SL / số con/tờ in)                        ← dùng ①
③ số tờ in chạy  = ② + bù_hao_canh_máy + %chạy                    ← bù hao sản xuất (TÁCH khỏi %hao hình học)
④ tờ in/tờ nguyên         ← BÌNH BÀI (xả giấy)
⑤ số tờ nguyên   = ceil(③ / ④)                                   ← dùng ④
⑥ kg giấy        = dài_ng × rộng_ng × gsm × ⑤ / 10.000.000
⑦ TIỀN GIẤY      = ⑥ × giá_kg
⑧ số kẽm                  ← BÌNH BÀI (màu×mặt | tay×màu×mặt)
⑨ TIỀN KẼM       = ⑧ × đơn_giá_kẽm
⑩ lượt in        = ③ × passes(số mặt)
⑪ TIỀN IN        = phí_canh_máy + (⑩/1000 × đơn_giá_1000)         [hoặc giờ máy BHR]
⑫ TIỀN GIA CÔNG  = Σ per-op (m² = ③ × dt_tờ_in × mặt; hoặc theo thành phẩm)
⑬ TỔNG           = ⑦+⑨+⑪+⑫+... → +overhead → ×(1+margin) → +VAT
```

> **Phân biệt 2 hao:** `%hao hình học` (§5, phần trống trên tờ — quyết số con) ≠ `bù hao sản xuất` (③ — tờ canh máy + spoilage). Cả hai vào giá nhưng ở 2 chỗ khác nhau.

### 7.3 Field quy tắc nào → đẩy giá nào
| Field rule | Ảnh hưởng | Dòng giá |
|---|---|---|
| side_margin / tail / gutter ↑ | con/tờ ↓ → tờ ↑ | ⑦ giấy, ⑪ in |
| allow_rotate | thường con ↑ | ⑦ giấy ↓ |
| allow_gang | chia sẻ tờ + kẽm | ⑦⑨ ↓/job |
| grain_constraint | có thể ép hướng xấu → con ↓ | ⑦ giấy ↑ |
| pages_per_sig ↑ | số tay ↓ | ⑨ kẽm ↓ (cần máy lớn) |
| work_style = work_turn | kẽm ÷ 2 | ⑨ kẽm ↓ |
| nest_method = true_shape | blank/tờ ↑ | ⑦ giấy ↓ |
| matrix_allowance ↑ | blank/tờ ↓ | ⑦ giấy ↑ |

### 7.4 Ví dụ end-to-end (rule → tiền)
Rule `PHANG-NUP`; con name card 90×53 (+2 bleed); tờ nguyên 65×86 150gsm 30k/kg; máy khổ 74; SL 10.000:
```
① con/tờ in (43×65) = 44        ② tờ in cần = ceil(10000/44) = 228
③ tờ in chạy = 228 + 150 + 2% ≈ 383   ④ tờ in/nguyên = 2   ⑤ tờ nguyên = 192
⑥ kg = 65×86×150×192 / 1e7 = 16.1 kg   ⑦ TIỀN GIẤY = 16.1×30k = 483.000đ
⑧ kẽm = 4×2 = 8   ⑨ TIỀN KẼM = 8×100k = 800.000đ
⑩ lượt in = 383×2 = 766   ⑪ TIỀN IN ≈ phí canh máy + 766/1000×đơn giá
⑫ gia công (bế/cán) ...   ⑬ TỔNG → +overhead → ×margin → +VAT
```
→ Đổi 1 field rule (vd gutter 4→8) là ⑦⑪ đổi ngay — chính là cái live formula §9.5 hiển thị.

---

## 8. Bảng thử (Test Bench) — nền cho preview & công thức

Quy tắc là **generic** (không có khổ thật). Để preview/công thức vẽ được, màn sửa quy tắc có panel **Bảng thử** cho user nhập bộ số mẫu:
```
Con mẫu   : dài × rộng (+ số trang nếu signature)
Tờ nguyên : khổ + gsm + giá/kg
Máy in    : chọn máy (kéo nhíp + khổ máy) hoặc nhập tay
SL + số màu (trước/sau)
```
→ Engine chạy trên bộ mẫu này để render ảnh + công thức + tiền. **Bảng thử không lưu vào rule** — chỉ để xem thử.

---

## 9. UI CHI TIẾT

### 9.1 Bố cục màn sửa quy tắc (3 cột)
```
┌───────────────┬────────────────────┬─────────────────────┐
│ CỘT TRÁI      │ CỘT GIỮA           │ CỘT PHẢI            │
│ Form cấu hình │ LIVE PREVIEW (ảnh) │ LIVE CÔNG THỨC      │
│ + Bảng thử    │ sơ đồ tờ in        │ + tác động tiền     │
└───────────────┴────────────────────┴─────────────────────┘
```

### 9.2 Cột trái — Form
Header (mã/tên/mô tả) · dropdown version (v cũ chỉ đọc) · `layout_mode` (đổi → ẩn/hiện field) · hình học chung · field theo mode · guardrails · **Bảng thử**. Nút **[Lưu → đẻ version mới]**.

### 9.3 Cơ chế cập nhật (chung cho preview + công thức)
- Mỗi thay đổi nhập liệu (field rule hoặc Bảng thử) → **debounce ~150ms → gọi engine → re-render cả preview + công thức**.
- Đổi `layout_mode` → đổi cả loại preview + bộ công thức.
- Trạng thái lỗi (không vừa máy) → preview đỏ + công thức hiện lý do.

### 9.4 Cột giữa — LIVE PREVIEW BẰNG ẢNH (trụ #2)
Render sơ đồ tờ in (SVG/canvas) cập nhật theo từng action.

**Thành phần vẽ (mọi mode):**
- Khung tờ in (tỉ lệ thật), dải **nhíp** (xám + nhãn "nhíp Xmm"), **lề hông** + **thang màu** (nhạt), **vùng in được** (viền).
- **Vùng trống/hao** tô sọc + nhãn `hao 23%`.
- Badge tổng: `40 con/tờ in`.

**Khác nhau theo mode:**
| mode | Preview vẽ gì |
|---|---|
| step_repeat | lưới con giống nhau, đánh số, mũi tên hướng; gang → tô màu khác nhau theo job |
| signature | 1 tờ in với ô trang đánh số theo folding_scheme, đường gấp (nét đứt), trang xoay 180° vẽ ngược, chỉ báo creep nếu ghim |
| nesting | blank theo dieline xếp lên tờ, khung thải (matrix) tô sọc + `%matrix` |
| repeat_around | trục trải phẳng: lanes × repeat, khoảng gap, nhãn `tem/vòng` |

**Phản ứng theo field (action → ảnh):**
| Thay đổi | Preview đổi |
|---|---|
| gutter ↑ | khe giữa con giãn ra, số con giảm |
| side/tail ↑ | vùng in được co lại, con giảm |
| allow_rotate bật | con xoay 90°, sắp lại lưới |
| pages_per_sig 8→16 | sơ đồ tay đổi, đánh số lại, thêm đường gấp |
| work_turn | vẽ 2 nửa đối xứng, ghi "cắt đôi → 2 cuốn" |
| matrix ↑ (nesting) | blank thưa ra, vùng thải rộng thêm |
| con không vừa máy | preview **đỏ**, chữ "Không vừa khổ máy" |

### 9.5 Cột phải — LIVE CÔNG THỨC (trụ #3)
Panel hiện công thức đang áp + thay số real-time + kết quả, chia 2 khối:

**Khối A — Bình bài (theo mode):**
```
cell      = rộng+2·bleed             = 90 + 2·2   = 94
usable_w  = tờ_in.rộng − 2·lề         = 430 − 10   = 420
usable_h  = tờ_in.dài − nhíp − thang  = 650 − 12 − 8 = 630
con/tờ    = floor((420+4)/(94+4)) × floor((630+4)/(57+4))
          = 4 × 10 = 40
hao hình học = 1 − (40×94×57)/(430×650) = 23.4%
```
Mỗi số **highlight cập nhật** khi field liên quan đổi.

**Khối B — Tác động TIỀN (nối §7):**
```
tờ in cần = ceil(SL/con)      = ceil(10000/40) = 250
tờ in chạy= 250 + bù hao      = ~410
tờ nguyên = ceil(410/2)       = 205
kg giấy   = 65×86×150×205/1e7 = 17.2 kg
TIỀN GIẤY = 17.2 × 30.000     = 516.000đ
số kẽm    = 4×2 = 8  → TIỀN KẼM = 800.000đ
```
→ Sửa gutter 4→8: user thấy ngay con 40→36, tờ nguyên tăng, TIỀN GIẤY nhảy lên. Đây là điểm nối trực tiếp bình bài ↔ giá.

**Tương tác:** hover 1 dòng công thức → highlight phần tương ứng trên preview (VD hover `usable_h` → sáng dải nhíp + thang màu).

### 9.6 Lịch sử version
Bảng: version_no · người tạo · thời gian · ghi chú · [Xem] [So sánh]. Version cũ chỉ đọc; **preview + công thức vẫn chạy** trên version cũ để đối chiếu.

---

## 10. Validate & lỗi

| Code | Điều kiện | Loại | Thể hiện trên UI |
|---|---|---|---|
| E-FIT-0 | con/blank không vừa vùng in được | Lỗi (chặn) | preview đỏ + công thức "con/tờ = 0" |
| E-MODE-REQ | thiếu field bắt buộc của mode | Lỗi | "Thiếu tham số cho kiểu bình bài" |
| W-GRAIN | hướng đặt vi phạm grain_constraint | Cảnh báo | badge vàng trên preview |
| W-PAGES-MIN | P < min_pages | Cảnh báo | "Thấp hơn ngưỡng đóng keo (≥40)" |
| W-PAGES-MAX | P > max_pages (ghim) | Cảnh báo/chặn | "Vượt giới hạn ghim (≤64) — nên chuyển keo" |
| W-SPINE | spine < min_spine_mm | Cảnh báo | "Gáy quá mỏng để đóng keo" |
| W-P4 | P không bội số 4 | Cảnh báo + auto | "Đã chèn trang trắng cho đủ bội số 4" |
| W-GANG-GUTTER | gutter < min_gutter khi gang | Cảnh báo | khe đỏ trên preview |

---

## 11. Seed data

| ma | ten | layout_mode | tham số |
|---|---|---|---|
| PHANG-NUP | Ấn phẩm phẳng n-up | step_repeat | allow_gang=true, gutter=4, side=5, tail=8 |
| SACH-KEO-16 | Sách đóng keo tay 16 | signature | pages_per_sig=16, sheetwise, grain=song_song_gay, min_pages=40 |
| SACH-GHIM-8 | Sách đóng ghim tay 8 | signature | pages_per_sig=8, sheetwise, max_pages=64 |
| HOP-BE | Hộp giấy dàn khuôn | nesting | nest=grid, matrix=5, grain=theo_song |
| TEM-CUON | Tem nhãn cuộn | repeat_around | gap=3, lanes=auto |

Tất cả seed ở **version v1, is_current=true**.
`folding_scheme`: seed F4, F8, F16, F32 (page_position_map + rotation_map, cả sheetwise & work_turn) — cấp dữ liệu cho preview signature.

---

## 12. Ràng buộc toàn vẹn
1. `ma` unique, không đổi sau tạo.
2. Mỗi rule đúng 1 version `is_current = true`.
3. Version `is_current = false` immutable, không xoá.
4. Không xoá version bị báo giá/lệnh SX ghim.
5. Không xoá header đang có sản phẩm gán → chỉ `inactive`.
6. Sửa cấu hình = luôn đẻ version mới, không sửa đè.
7. Đẻ version mới không đụng báo giá cũ (giữ `version_no` đã ghim).
8. `layout_mode` version cũ giữ nguyên; đổi mode = version mới.
9. Bảng thử không lưu vào rule.

---

## 13. Ranh giới (field ở module khác)
```
MÁY IN    : gripper_mm, max_w/max_h/min_w/min_h, trục{teeth, pitch, dia}
SẢN PHẨM  : khổ thành phẩm (dài/rộng), số trang P, binding (ghim/keo/khâu),
            cover_separate, dieline, bleed thật
SUY RA    : creep (từ binding), số tay, khổ tờ in, số tờ in, %hao
ENGINE GIÁ: tiêu thụ output bình bài (§7) — module này phải "feed" đúng, không tự tính tiền
```
