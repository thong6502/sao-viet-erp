# SPEC — MODULE CÔNG ĐOẠN (Operation · Routing)

> **2 tầng:** `cong_doan` (danh mục thao tác + cách tính giá + máy) + `routing_step` (instance trên 1 job + hao lan truyền + actual).
> Là nơi **ráp số lượng hình học → tiền công**, và giữ **dòng kẽm (kem_line)**.
> Anh em với `spec-quy-tac-binh-bai.md`, `spec-may-thiet-bi.md`, `spec-san-pham.md`.

---

## 1. Tổng quan

### 1.1 Hai tầng
| Tầng | Là gì | Master? |
|---|---|---|
| **Danh mục công đoạn** | Loại thao tác (in, cắt, cán, bế, ép, đóng…) + cách tính giá + máy | ✓ Master |
| **Routing step** | Instance trên 1 job: SL vào/ra, giá tính ra, ước tính vs thực tế | Per job |

### 1.2 Trách nhiệm
- Quy đổi **số lượng hình học → basis_qty → tiền** cho từng bước.
- **Lan truyền hao NGƯỢC** qua chuỗi routing → biết số tờ in/tờ giấy phải mua.
- Giữ **kem_line** (giá vật tư bản, key theo khổ máy).

### 1.3 KHÔNG làm gì
- Không giữ BHR/khổ máy → **Máy**. Không giữ cách xếp → **Quy tắc bình bài**.
- Không giữ giá vật tư (giấy/mực/kẽm/khuôn đơn giá) → **Vật tư / Kẽm & khuôn** (chỉ *tham chiếu*).

---

## 2. Mô hình dữ liệu — TẦNG 1: `cong_doan` (danh mục)

| Field | Kiểu | Bắt buộc | Default | Mô tả |
|---|---|---|---|---|
| id | PK | ✓ | | |
| ma | string(30) unique | ✓ | | |
| ten | string(150) | ✓ | | Cắt xén, Cán màng, Bế, Ép kim, Đóng ghim… |
| nhom | enum(prepress, print, finishing) | ✓ | | |
| may_id | FK → máy | ✓ | | máy chạy công đoạn |
| che_do_tinh | enum(theo_gio, theo_san_luong) | ✓ | theo_san_luong | **trục tính tiền** (khác `pricing_basis`) |
| pricing_basis | enum(per_sheet, per_finished_area, per_finished_qty, per_book_page, per_position, per_bag, per_carton, per_area_sides, per_sheet_area, per_book_page_q4, per_other) | khi theo_san_luong | | **đơn vị** đo (§4.3) |
| setup_cost | money | | 0 | phí cố định/lần |
| setup_time | number | phút | 0 | (dùng khi theo_gio) |
| run_rate | money | | | đơn giá theo basis |
| rate_tiers[] | json | | | bậc thang §5.2 |
| first_unit_floor | money | | | **sàn cho bậc đầu** (VD 1.000 lượt đầu) — KHÁC `min_charge` |
| min_charge | money | | | giá sàn CẢ công đoạn |
| requires_tooling | bool | | false | cần khuôn/kẽm? |
| tooling_type | enum(khuon_be, khuon_ep, kem) | | | |
| spoilage_pct | pct | | 0 | hao gia công (bước này) — **KHÔNG áp cho bước in** (§4.4) |
| inline_flag | bool | | false | chạy inline cùng lượt in (VD phủ) → chống double-charge |
| active | bool | ✓ | true | |

---

## 3. Mô hình dữ liệu — TẦNG 2: `routing_step` (per job)

| Field | Kiểu | Mô tả |
|---|---|---|
| id | PK | |
| job_id / bao_gia_dong_id | FK | |
| sequence | int | thứ tự công đoạn |
| cong_doan_id | FK | → danh mục |
| may_id | FK | override máy |
| source | enum(inherited, manual) | từ routing_template hay user thêm (§6) |
| output_qty | number | **SL RA tốt** của bước (thành phẩm bước này) |
| spoilage_pct_override | pct | ghi đè hao bước (mặc định lấy từ danh mục) |
| input_qty | number | **SL VÀO** = tính ngược từ output + hao (§4.2) |
| basis_qty | number | quy đổi hình học theo pricing_basis (§4.3) |
| tooling_ref | FK → Kẽm&khuôn (instance) | khuôn/kẽm cụ thể đã dùng |
| reuse_tooling | bool | tái bản dùng lại khuôn → bỏ tooling_cost |
| setup_cost, run_cost, tooling_cost, total | money | ước tính |
| actual | json | {qty, gio, spoilage, chi_phi} thực tế từ SFDC (§7) |

---

## 4. Công thức

### 4.1 Tiền 1 công đoạn
```
theo_san_luong:  run_cost = run_rate × basis_qty   (áp bậc thang §5.2 nếu có)
theo_gio:        run_cost = BHR(máy) × (basis_qty / (toc_do×efficiency) + setup_time/60)
total = setup_cost + run_cost + tooling_cost
total = max(total, min_charge)              ← sàn cả công đoạn
tooling_cost = reuse_tooling ? 0 : tooling.one_time_cost   ← tái bản bỏ khuôn
```

### 4.2 Lan truyền HAO NGƯỢC (bug quan trọng đã sửa)
```
Tính từ bước CUỐI (thành phẩm) ngược lên:
  output_qty(bước cuối) = so_luong (đơn đặt)
  input_qty(bước i)     = output_qty(bước i) / (1 − spoilage_i)
  output_qty(bước i−1)  = input_qty(bước i)          ← ra của bước trước = vào của bước sau
...ngược tới bước IN → cộng bù hao máy (canh máy + %chạy) → ra SỐ TỜ IN cần
...→ phá giấy → SỐ TỜ NGUYÊN mua
```
> Không cascade thì **mua giấy/in THIẾU** vì mỗi công đoạn ăn thêm hao.

### 4.3 Bảng quy đổi `basis_qty` (dùng SL GROSS đã cộng hao)
Bộ đơn vị bao trùm chế bản · in · sau in (ctx: `so_to_in_gross`, `so_mat`, `dt_to_in_cm2`,
`dt_thanh_pham_cm2`, `so_luong_thanh_pham`, `so_trang`, `so_cuon`, `so_vi_tri`, `so_bao`, `so_thung`).

| pricing_basis | Nhãn | basis_qty = |
|---|---|---|
| per_sheet | Theo số tờ in | số tờ in gross |
| per_finished_area | Theo diện tích thành phẩm (cm²) | dt_thành_phẩm_cm² × SL thành phẩm |
| per_finished_qty | Theo số lượng thành phẩm | SL thành phẩm |
| per_book_page | Theo số trang sách | số trang × số cuốn |
| per_position | Theo số vị trí | số vị trí × SL thành phẩm |
| per_bag | Theo bao | số bao |
| per_carton | Theo thùng | số thùng |
| per_area_sides | Theo diện tích (cm²) và số mặt | dt_tờ_cm² × số mặt × số tờ in |
| per_sheet_area | Theo diện tích tờ in (cm²) | dt_tờ_cm² × số tờ in |
| per_book_page_q4 | Theo số trang sách chia 4 | (số trang × số cuốn) / 4 |
| per_other | Khác | 1 (nhập tay, giá phẳng) |

> **Chuyển đơn vị giữa bước** (tờ→tay→cuốn): input_qty bước sau suy từ output_qty bước trước theo đơn vị của nó (VD đóng cuốn: cuốn = số tờ ruột / số tay).

### 4.4 Chống trùng hao/chi phí (đã sửa)
```
Bước IN (nhom=print): hao TỜ chỉ lấy từ MÁY (bu_hao_canh_may_per_mau + bu_hao_chay_pct)
                      → cong_doan.spoilage_pct = 0 (KHÔNG áp) ← tránh trùng
Phủ inline (inline_flag=true, máy co_thap_phu): KHÔNG tạo công đoạn phủ riêng;
     cộng chi_phi_phu_per_m2 × dt_phủ vào run_cost bước IN (tính 1 lần)
Ghi kẽm CTP: công đoạn CTP = CHỈ công ghi (BHR×giờ); giá VẬT TƯ bản ở kem_line (§5.1) — KHÔNG tính 2 lần
```

---

## 5. KẼM (kem_line) & bậc thang

### 5.1 Dòng kẽm — công thức (đã sửa double-count tự trở)
```
so_forms = số tay (signature) hoặc 1 (flat/box/label)     ← "số tay/forms", KHÔNG phải số con!
so_kem_mặt_trước = (so_mau_truoc + so_mau_pha_truoc)
so_kem_mặt_sau   = (so_mau_sau  + so_mau_pha_sau)

so_kem = so_forms × ( tự_trở? max_distinct(2 mặt) : (so_kem_mặt_trước + so_kem_mặt_sau) )
   • sheetwise: cộng cả 2 mặt (mỗi mặt bộ kẽm riêng)
   • tự trở / work_and_tumble: 1 bộ kẽm mang cả 2 mặt → KHÔNG ×số mặt
   • perfector: cả 2 mặt (mỗi mặt bộ kẽm), passes gộp nhưng kẽm không gộp

kem_line = so_kem × don_gia_kem
don_gia_kem = lookup(Kẽm&khuôn, key = may_in.khoa_class)     ← giá theo khổ máy

GUARD: loai_may = press_digital → so_kem = 0, KHÔNG có kem_line (in click, không bản)
       chỉ sinh kem_line cho press_offset*/flexo/gravure
```

### 5.2 Bậc thang `rate_tiers[]`
```
rate_tier = { from_qty, rate, kieu(marginal | cumulative), driver(basis_qty | so_luot) }
Công in: first_unit_floor cho 1.000 lượt đầu (sàn bậc 0), rate giảm dần theo số lượng.
Phân biệt: first_unit_floor = sàn BẬC ĐẦU ; min_charge = sàn CẢ công đoạn (2 thứ khác nhau).
```

---

## 6. Routing template → routing step (seam khởi tạo)
```
Khi mở job:
  1. Bung loai_san_pham.routing_template[] → các routing_step (source = inherited)
  2. Trộn jobspec.finishing_chon[]        → routing_step (source = manual)
  3. Cho phép: đổi thứ tự, tắt/bật, sửa may_id, sửa spoilage_pct_override
  4. Engine chạy §4.2 (cascade hao) trên chuỗi đã chốt
```

---

## 7. Actual vs Estimate (SFDC)
```
routing_step.actual = { qty_tot, qty_hong, gio_may, gio_cong, chi_phi_vat_tu }
Seam SFDC: transaction key = (job_id, sequence, cong_doan_id)   ← theo BƯỚC, không chỉ theo máy
variance% = (actual.total − est.total) / est.total × 100   (theo bước + tổng job)
Job cost thực = Σ routing_step.actual + vật tư (giấy/mực/kẽm)
```

---

## 8. Validate & lỗi
| Code | Điều kiện | Loại |
|---|---|---|
| E-CD-BASIS | che_do_tinh=theo_san_luong nhưng thiếu pricing_basis | chặn |
| E-CD-HOUR-MAY | che_do_tinh=theo_gio nhưng thiếu may_id hoặc toc_do ≤ 0 | chặn |
| E-CD-TOOL | requires_tooling nhưng thiếu tooling_ref (khi báo giá) | chặn |
| E-CD-KEM-DIG | sinh kem_line cho máy digital | chặn |
| W-CD-PRINT-SPOIL | spoilage_pct > 0 trên bước in (trùng bù hao máy) | cảnh báo (ép 0) |
| W-CD-INLINE-DUP | có công đoạn phủ riêng trong khi máy chạy phủ inline | cảnh báo (gỡ) |
| W-CD-CTP-DUP | kem_line + công đoạn CTP cùng tính tiền bản | cảnh báo |
| W-CD-TIER | rate_tier thiếu from_qty/driver | cảnh báo |

---

## 9. Seed data
| ma | nhóm | máy | che_do_tinh | basis | rate (VN) | tooling |
|---|---|---|---|---|---|---|
| GHI-KEM | prepress | CTP-B1 | theo_gio | — | BHR×giờ | (bản = kem_line) |
| IN | print | OFF-74-4C | theo_san_luong | per_1000_luot | + first_unit_floor 1.000 lượt | kẽm |
| XEN | finishing | XEN-115 | theo_san_luong | per_ram | 50–70k/ram | — |
| CAN-BONG | finishing | CAN-BONG | theo_san_luong | per_m2 | 2.000–2.500đ/m², min 50m² | — |
| BE | finishing | die_cutter | theo_san_luong | per_pass | 150–200đ/lượt | khuon_be |
| EP-KIM | finishing | foil_press | theo_san_luong | per_pass | 300–500đ/lượt | khuon_ep |
| DONG-KEO | finishing | perfect_binder | theo_san_luong | per_book | 80–240đ/cuốn | — |
| SO-NHAY | finishing | numbering | theo_san_luong | per_number | 10đ/số | — |

---

## 10. Ranh giới & seam
```
MÁY              : BHR, tốc độ, bù hao, khoa_class (→ giá kẽm), chi_phi_phu_per_m2 (inline)
QUY TẮC BÌNH BÀI : số con/tay/blank, số tờ, so_forms (số tay) → feed công thức kẽm & basis_qty
SẢN PHẨM         : so_mau_truoc/sau + pha (per mặt), binding (tự trở/nested), routing_template
VẬT TƯ (VAT_TU)  : giá giấy/mực; ink_cost = don_gia_muc × (số lượt/1000) × số màu (+ coverage nếu có)
KẼM & KHUÔN      : don_gia_kem (key khoa_class); khuôn bế/ép (tooling_ref) + die-life (remaining hits)
BÁO GIÁ          : gom Σ công đoạn + kẽm + giấy + mực → overhead cty + margin + VAT
SFDC             : actual theo (job, sequence, công đoạn)
```

---

## 11. Changelog — fix từ phản biện
1. **kem_line**: `so_kem = so_forms × (tự_trở? 1 bộ : cả 2 mặt)` — hết double-count tự trở; `so_forms` = **số tay**, KHÔNG phải số con; guard digital = 0 kẽm; kẽm per-mặt (gồm màu pha mặt đó).
2. **Cascade hao ngược**: `input = output/(1−spoilage)` từ bước cuối lên → mua đủ giấy/in.
3. **Bỏ `per_hour_BHR`** khỏi pricing_basis (đó là `che_do_tinh`); validate chéo.
4. **Chống trùng**: bước in không áp `spoilage_pct` (lấy bù hao máy); phủ inline tính 1 lần ở bước in; CTP công ghi ≠ kem_line vật tư.
5. **Tooling instance**: `tooling_ref` + `reuse_tooling` (tái bản bỏ khuôn) + die-life ở Kẽm&khuôn.
6. **Seam routing_template → routing_step**: bung inherited + trộn manual + reorder/tắt; `source`.
7. **Bảng basis→hình học** + chuyển đơn vị giữa bước (tờ→tay→cuốn).
8. **rate_tier** có cấu trúc {from_qty, rate, marginal/cumulative, driver} + `first_unit_floor` tách khỏi `min_charge`.
9. **Actual** có cấu trúc + SFDC key theo (job, bước), không chỉ theo máy.
10. **theo_gio** bắt buộc may_id + tốc độ; lao động thủ công (thuê ngoài) đi đường labor rate.
11. **Mực**: công thức tiêu hao theo số màu × lượt (+ coverage), không bỏ số màu.
```
