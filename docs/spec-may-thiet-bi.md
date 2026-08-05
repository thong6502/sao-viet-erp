# SPEC — MODULE THIẾT BỊ / MÁY (Machine · Cost Center)

> Master data mọi **máy sản xuất**, mỗi máy = **một cost center có đơn giá giờ (BHR)**.
> Cấp dữ liệu cho **2 engine**: ① Bình bài (khổ máy, nhíp, số units) · ② Tính giá (BHR, tốc độ, bù hao).
> Anh em với `spec-quy-tac-binh-bai.md`, `spec-san-pham.md`, `spec-cong-doan.md`.

---

## 1. Tổng quan

### 1.1 Bản chất
- 1 bảng master `may_thiet_bi`, phân biệt bằng **`loai_may`** (discriminator) → bật/tắt nhóm field theo loại.
- Mỗi máy vừa là **cost center** (mang BHR để tính tiền công) vừa là **spec năng lực** (khổ, số màu, tốc độ...).

### 1.2 Trách nhiệm
- Giữ **ràng buộc vật lý** engine bình bài cần: khổ máy (max/min), **nhíp `gripper_mm`**, số units, cho phép tự trở.
- Giữ **đơn giá giờ máy (BHR)** + tốc độ + bù hao để engine tính giá tính tiền công + số lượt + hao giấy.
- Nối kế toán: tài sản, tài khoản GL, thu thập dữ liệu xưởng (SFDC) để đối soát giờ thực tế.

### 1.3 KHÔNG làm gì (ranh giới)
- Không giữ: cách xếp (layout) → **Quy tắc bình bài**.
- Không giữ: đơn giá per-m²/pass/ram của gia công → **Công đoạn** (máy chỉ giữ BHR + năng lực).
- Không giữ: giá kẽm/khuôn → **danh mục Kẽm & khuôn**; giấy/mực → **Vật tư** (`VAT_TU_DON_GIA.md`).
- Không tự chọn khổ tờ in — đó là việc **engine** (dựa Máy + Tờ nguyên). **Tờ in không khai.**

---

## 2. Vị trí trong hệ thống
```
   QUY TẮC BÌNH BÀI ┐
   MÁY (khổ, nhíp,  ├─► ENGINE BÌNH BÀI ─► con/tay/blank · tờ in · tờ nguyên · kẽm · %hao
   số units, tự trở)│                                │
   SẢN PHẨM         │                                ▼
   TỜ NGUYÊN        ┘         ENGINE TÍNH GIÁ ◄── MÁY (BHR, tốc độ, bù hao) + CÔNG ĐOẠN + VẬT TƯ
                                       ▼
                              tiền giấy · kẽm · in · gia công → BÁO GIÁ (overhead cty + margin + VAT)
```
Liên kết:
```
CONG_DOAN.may_id            → may_thiet_bi.id      (công đoạn chạy trên máy)
may_thiet_bi.ma_tai_san     → Sổ tài sản (khấu hao)
may_thiet_bi.ma_TK_cost_center → GL (hạch toán)
may_thiet_bi.khoa_class     → giá kẽm trong danh mục Kẽm & khuôn (kem_line, xem spec-cong-doan §kẽm)
```

---

## 3. Mô hình dữ liệu

### 3.1 Nhóm NHẬN DIỆN (mọi máy)
| Field | Kiểu | Bắt buộc | Default | Ràng buộc / Mô tả |
|---|---|---|---|---|
| id | PK | ✓ | | |
| ma | string(30) unique | ✓ | | mã máy (VD `OFF-74-4C`), không đổi sau tạo |
| ten | string(150) | ✓ | | tên hiển thị |
| loai_may | enum | ✓ | | discriminator §3.2 |
| finishing_subtype | enum | khi finishing | | §3.7 |
| nhom_cost_center | FK | ✓ | | nhóm (in / chế bản / sau in) |
| phong_ban | FK | | | bộ phận (cho phân bổ tải, đa xưởng) |
| dia_diem | string | | | nhà máy / site (đa cơ sở) |
| hang_san_xuat | string | | | Heidelberg / Komori / RMGT… |
| model | string | | | |
| so_seri | string | | | asset tag |
| trang_thai | enum(active, maintenance, retired) | ✓ | active | `active` mới cho báo giá. **Không có field `active` riêng** — suy từ đây. |
| ghi_chu | text | | | |

### 3.2 `loai_may` (discriminator)
| Mã | Máy |
|---|---|
| press_offset_sheet | in offset tờ rời (chủ lực) |
| press_offset_web | in offset cuộn |
| press_digital | in kỹ thuật số (toner/inkjet) |
| press_flexo_label | flexo cuộn hẹp (tem nhãn) |
| press_gravure | in ống đồng |
| wide_format | in khổ lớn (inkjet) |
| prepress_ctp | ghi kẽm CTP |
| finishing | sau in (kèm `finishing_subtype`) |
| thue_ngoai | gia công thuê ngoài (cost center ảo) |
| other | khác (screen/pad/typo… — xem §3.8) |

### 3.3 Nhóm TÀI SẢN / TÀI CHÍNH
| Field | Kiểu | Bắt buộc | Default | Mô tả |
|---|---|---|---|---|
| ma_tai_san | FK | | | nối Sổ tài sản (đối soát khấu hao) |
| ma_TK_cost_center | string | | | tài khoản GL (hạch toán chi phí) |
| nha_cung_cap | string | | | |
| ngay_dua_vao_su_dung | date | | | mốc bắt đầu khấu hao (≠ năm sản xuất) |
| het_han_bao_hanh | date | | | |
| phuong_phap_khau_hao | enum(duong_thang, so_du_giam_dan) | | duong_thang | |

### 3.4 Nhóm CHI PHÍ — BHR (mọi máy, cho tính giá)
> **BHR = đơn giá giờ máy GIÁ VỐN.** Đã sửa theo phản biện cost-accounting (§8 changelog).

| Field | Kiểu | Đơn vị | Default | Mô tả |
|---|---|---|---|---|
| nguon_bhr | enum(nhap_truc_tiep, dung_tu_von) | | dung_tu_von | *(đổi tên từ `che_do_gia` để hết trùng với Công đoạn)* |
| don_gia_gio_BHR | money | đ/giờ | | nếu nhập trực tiếp |
| von_dau_tu | money | đ | | vốn mua máy |
| gia_tri_thu_hoi | money | đ | 0 | **giá trị thu hồi (salvage)** — trừ khi khấu hao |
| nam_khau_hao | int | năm | 8 | |
| lai_von_pct | pct | %/năm | | lãi suất/chi phí vốn |
| gio_lam_nam | int | giờ/năm | 2000 | giờ vận hành danh nghĩa |
| availability_pct | pct | % | 85 | tỉ lệ sẵn sàng (đã trừ downtime + bảo trì) |
| productivity_pct | pct | % | 85 | tỉ lệ hữu dụng (giờ tính phí / giờ sẵn sàng) |
| efficiency_pct | pct | % | 80 | hiệu suất tốc độ (derate **tốc độ** ở run-time, KHÔNG vào giờ tính phí) |
| so_nhan_cong | number | người | 1 | crew đứng máy (perfector có thể 2–3) |
| luong_gio | money | đ/giờ | | lương cơ bản/giờ 1 người |
| luong_burden_pct | pct | % | 30 | phụ cấp + BHXH + thuế (25–40%) |
| cong_suat_kW | number | kW | | công suất điện lắp đặt (nameplate) |
| he_so_tai_dien | number | | 0.65 | hệ số tải thực (0,6–0,8) — máy không kéo full kW |
| don_gia_dien | money | đ/kWh | | |
| bao_hiem_nam | money | đ/năm | 0 | bảo hiểm máy |
| dien_tich_san_m2 | number | m² | | diện tích chiếm sàn (phân bổ thuê mặt bằng) |
| don_gia_thue_m2_nam | money | đ/m²/năm | | (cấu hình chung hoặc theo site) |
| bao_tri_gio | money | đ/giờ | | bảo trì phân bổ |
| overhead_gio | money | đ/giờ | | **CHỈ chi phí gián tiếp CÒN LẠI** — KHÔNG chứa lãi vốn/bảo hiểm/mặt bằng/điện/bảo trì/lương (đã tách ra) |
| don_gia_ban_gio | money | đ/giờ | | *(tùy chọn)* giá bán/giờ = BHR × (1+markup) nếu shop markup theo máy |
| markup_pct | pct | % | | markup theo cost center (margin tổng ở **Báo giá**) |
| ngay_cap_nhat_bhr | date | | | **rà lại tối thiểu hằng năm** |

### 3.5 Nhóm NĂNG LỰC / TỐC ĐỘ (mọi máy)
| Field | Kiểu | Đơn vị | Mô tả |
|---|---|---|---|
| toc_do | number | | **Tốc độ TRUNG BÌNH** (nhãn UI đổi 03/08/2026; tên cột giữ nguyên). Số DUY NHẤT chảy vào Tính giá / Lệnh SX / Xếp lịch |
| toc_do_min | number | | Tốc độ tối thiểu — **CHỈ ĐỂ KHAI**, không vào công thức nào (mg 0152) |
| toc_do_max | number | | Tốc độ tối đa — **CHỈ ĐỂ KHAI** (mg 0152) |
| don_vi_toc_do | mã `<đơn vị đếm>_gio` | | **SUY RA từ danh mục `don_vi_do`** — chủ tự thêm/xoá đơn vị ở màn "Đơn vị & quy đổi" là danh sách chọn tự đổi theo. KHÔNG còn là enum cứng. VARCHAR(32) sau mg 0153 |
| makeready_time_default | number | phút | thời gian canh máy — **3 kiểu khai**: để trống · gõ tổng · theo từng khoản (chi tiết trong `fields_theo_loai.chuan_bi_khoan`, tổng TỰ CỘNG và khoá chỉ đọc) |
| thoi_gian_rua_muc | number | phút | rửa mực/đổi màu (TÁCH khỏi canh máy; đổi đậm→nhạt lâu hơn) |
| min_stock_gsm | int | gsm | định lượng nhỏ nhất chạy được |
| max_stock_gsm | int | gsm | định lượng lớn nhất |
| vat_lieu_ho_tro_class | enum[] | | loại vật liệu (tráng/không tráng/carton/nhựa/decal/foil) |
| so_may_song_song | int | | số máy giống hệt trong cost center (chia lương crew) |
| may_thay_the | FK[] | | máy thay thế khi quá tải (scheduling) |
| so_ca | int | | số ca/ngày |
| lich_lam_viec_id | FK | | lịch/ca (scheduling) |
| chi_so_dem_luot | bigint | | đồng hồ lượt in tích lũy (bảo trì/định giá lại/click-life) |

### 3.6 Nhóm BẢO TRÌ
| Field | Kiểu | Mô tả |
|---|---|---|
| ngay_bao_tri_gan_nhat | date | |
| chu_ky_bao_tri | number + đơn vị(giờ/lượt) | định kỳ bảo trì |
| ngay_bao_tri_ke_tiep | date | tính từ chu kỳ |
| nhat_ky_hong | table | log hỏng/dừng máy (→ availability thực) |

### 3.7 Field theo `loai_may`

**A. `press_offset_sheet`** (chi tiết nhất — ★ = engine bình bài cần)
| Field | Kiểu | Đơn vị | Default | Engine dùng | Mô tả |
|---|---|---|---|---|---|
| kho_max_dai ★ | int | mm | | Bình bài | |
| kho_max_rong ★ | int | mm | | Bình bài | |
| kho_min_dai ★ | int | mm | | Bình bài | |
| kho_min_rong ★ | int | mm | | Bình bài | |
| gripper_mm ★ | int | mm | 12 | Bình bài | cạnh nhíp không in (9,5–15) — **tên khớp `spec-quy-tac-binh-bai.md` §5.0/§13** |
| le_hong_mm | int | mm | 5 | Bình bài | *(tùy chọn)* lề máy tối thiểu; engine lấy `max(rule.side_margin, máy.le_hong)` |
| duoi_thang_mau_mm | int | mm | 8 | Bình bài | *(tùy chọn)* đuôi thang màu máy; `max(rule.tail, máy.duoi)` |
| so_units ★ | int | | | Đếm lượt/kẽm | số đơn vị in (1/2/4/5/6/8…) |
| units_truoc / units_sau | int | | | Perfector | phân bổ units 2 mặt (perfector 4/4 = 4+4) |
| kho_ban_in | int×int | mm | | Validate | khổ bản kẽm máy nhận (kiểm kẽm CTP vừa máy) |
| so_zone_muc | int | | | CIP3 | số vùng chốt mực (preset CIP3, mô hình bù hao) |
| co_thap_phu | bool | | false | Công đoạn | có tháp phủ inline |
| loai_phu | enum(aqueous, uv, vecni) | | | | |
| chi_phi_phu_per_m2 | money | đ/m² | | Công đoạn | **consumable phủ** (không phải giấy/mực) — tính 1 lần ở bước in (xem inline_rule spec-cong-doan) |
| co_tro_mat | bool | | false | Lượt | perfector (in 2 mặt 1 lượt tự động) |
| cho_phep_tu_tro | bool | | true | Lượt/kẽm | work-and-turn (1 bộ kẽm, lật chồng giấy) |
| cho_phep_tro_dau_duoi | bool | | false | Lượt | work-and-tumble (đổi cạnh nhíp) |
| uv_capable | bool | | false | | |
| bu_hao_canh_may_per_mau | int | tờ | 100 | Bù hao | tờ canh máy **mỗi màu/mặt** (scale theo số màu) |
| bu_hao_chay_pct | pct | % | 3 | Bù hao | % hao chạy theo run |
| toc_do_sph | int | tờ/giờ | | Tính giá | tốc độ đỉnh |
| ho_tro_cip3 | bool | | false | Bù hao | preset chốt mực → giảm bù hao 40–60% |
| do_day_giay_min/max_micron | int | µm | | | |
| khoa_class | enum(52,74,79,102, custom) | | | Seam kẽm | **lớp khổ máy** (tra giá kẽm + lọc/khớp job như thợ nghĩ) |

**B. `press_offset_web`**
```
web_width_mm, cut_off_mm (= π×đường_kính_trục), che_do_say(heatset|coldset),
folder_type(jaw|chopper), so_web (ribbons), so_trang_quanh (pages around),
hao_web: {waste_moi_lan_noi_cuon_m, web_break_pct}   ← mô hình hao theo mét/cuộn, KHÔNG dùng bu_hao_canh_may sheet
```

**C. `press_digital`**
```
cong_nghe(toner | inkjet_production)   ← discriminator
[toner]  click_mono, click_mau, size_factor(A3=2), per_mat, min_click
[inkjet] don_gia_muc_per_m2 (hoặc per_ml + coverage), phi_dung_dich_lot,
         head_replacement_amortization   ← inkjet tính theo mực/diện tích, KHÔNG dùng click
ho_tro_vdp(bool), tram_trang_thu5(white/clear station)
```

**D. `press_flexo_label`**
```
web_width_mm, repeat_min_mm, repeat_max_mm, circular_pitch, so_rang_max,
so_units (stations), anilox_lpi, anilox_bcm (thể tích mực — cần để tính mực),
cure_type(UV|LED|hot_air), inline_diecut → tooling_ref (Kẽm&khuôn),
inline_lam(bool), cold_foil(bool), matrix_waste_model
```

**E. `press_gravure`**
```
web_width_mm, cylinder_repeat_min/max, so_units(stations),
engraving_cost_basis, cylinder → tooling_ref (Kẽm&khuôn, per màu, amortize theo volume),
che_do_say(solvent/dry), web_tension
Cơ sở tính: per_met chạy cuộn (không phải tờ).
```

**F. `prepress_ctp`**
```
plate_max_size, plate_min_size, loai_ban(nhiet_830 | violet_405),
do_phan_giai(2400–3600 dpi), screen_ruling_max,
xu_ly_ban(processless | chemical) + chi_phi_developer, punch_bender(register),
toc_do_ghi(bản/giờ)
SEAM: ctp_output(số kẽm) → kem_line ; ctp → CIP3 → chốt mực máy (so_zone_muc)
GHI RÕ: CTP = CHỈ công ghi (BHR×giờ); giá vật tư bản ở kem_line — KHÔNG tính 2 lần.
```

**G. `wide_format`**
```
max_print_width, media_class(roll | rigid | both), ink_technology(aqueous|eco_solvent|solvent|uv|latex|dye_sub),
don_gia_muc_per_m2 (hoặc per_ml + coverage), so_dau_in(heads), do_phan_giai,
white_ink_capable(bool), cutter_inline(bool)
Cơ sở tính: per_m2 diện tích in + mực (khác hẳn tờ/lượt).
```

**H. `finishing` + `finishing_subtype`** (mỗi subtype 1 khối field)
| finishing_subtype | Field đặc thù |
|---|---|
| guillotine | max_cut_length, clamp_pressure |
| buckle_folder / knife_folder | fold_types[], so_plate_gap, max_sheet |
| saddle_stitcher | so_pocket, max_pages, cover_feeder, three_knife_trim |
| perfect_binder | so_clamp, spine_min/max, adhesive(EVA|PUR) |
| wireo | pitch(3:1|2:1), max_thickness |
| laminator | max_width, film(gloss|matt|soft_touch), hot_cold |
| die_cutter | tonnage, foil/emboss_stations, die → tooling_ref |
| foil_press | foil_type, nhiet_do |
| uv_coater | spot_vs_flood, cấp_phủ |

> Giá per-unit của gia công **KHÔNG** ở đây — ở **Công đoạn** (máy chỉ giữ năng lực + BHR).

**I. `thue_ngoai`** (cost center ảo)
```
nha_cung_cap, don_gia (per_to | per_m2 | per_sp), markup_pct, min_charge, lead_time_ngay
Routing vẫn trỏ tới được; giá = đơn giá NCC × SL × (1+markup), sàn min_charge.
```

---

## 4. Công thức BHR (v3 — đã vá cost-accounting)

### 4.1 Giờ tính phí (chargeable hours)
```
gio_tinh_phi = gio_lam_nam × availability_pct × productivity_pct
# efficiency_pct KHÔNG vào đây — nó derate TỐC ĐỘ ở run-time (§5)
# bảo trì/downtime đã nằm trong availability → KHÔNG trừ 2 lần
```

### 4.2 BHR = Σ chi phí ĐỨNG (chia chung gio_tinh_phi) + chi phí CHẠY (theo giờ chạy)
```
# --- Chi phí ĐỨNG: tất cả chia CÙNG gio_tinh_phi ---
khau_hao_gio = (von_dau_tu − gia_tri_thu_hoi) / (nam_khau_hao × gio_tinh_phi)
lai_von_gio  = ((von_dau_tu + gia_tri_thu_hoi)/2 × lai_von_pct) / gio_tinh_phi     ← vốn BÌNH QUÂN
bao_hiem_gio = bao_hiem_nam / gio_tinh_phi
mat_bang_gio = (dien_tich_san_m2 × don_gia_thue_m2_nam) / gio_tinh_phi
lao_dong_gio = luong_gio × (1 + luong_burden_pct) × so_nhan_cong / so_may_song_song
bao_tri_gio  = (đã nhập/giờ)
overhead_gio = (CHỈ gián tiếp còn lại)

# --- Chi phí CHẠY: theo giờ chạy thực (không phải standing) ---
dien_gio     = cong_suat_kW × he_so_tai_dien × don_gia_dien

BHR = khau_hao_gio + lai_von_gio + bao_hiem_gio + mat_bang_gio
    + lao_dong_gio + bao_tri_gio + overhead_gio + dien_gio
# BHR LOẠI TRỪ giấy + mực (tính riêng theo job)
don_gia_ban_gio = BHR × (1 + markup_pct)     # margin tổng ở Báo giá
```

### 4.3 Ví dụ số (máy offset 4 màu khổ 74)
```
von 4,0 tỷ · thu hồi 0,4 tỷ · khấu hao 8 năm · gio_lam_nam 2000 · avail 0,90 · prod 0,83
gio_tinh_phi = 2000 × 0,90 × 0,83 ≈ 1.500 giờ

khau_hao_gio = (4,0 − 0,4) tỷ / (8 × 1500)          = 300.000 đ/giờ
lai_von_gio  = (4,0+0,4)/2 tỷ × 10% / 1500           = 146.700 đ/giờ   (KHÔNG phải 293k)
bao_hiem_gio = 40 tr / 1500                           =  26.700
mat_bang_gio = 40 m² × 1,2 tr/m²/năm / 1500           =  32.000
lao_dong_gio = 60.000 × 1,3 × 2 người / 1 máy         = 156.000
bao_tri_gio                                           =  30.000
overhead_gio (còn lại)                                =  50.000
dien_gio     = 80 kW × 0,65 × 3.000                   = 156.000
────────────────────────────────────────────────────────────────
BHR ≈ 897.000 đ/giờ    →  don_gia_ban ≈ 897k × 1,15 ≈ 1.030.000 đ/giờ
```
> Cao hơn con số 600k tôi ước lúc trước vì đã tính đủ **crew 2 người có phụ cấp + điện thực + lãi vốn** — đây mới là BHR đúng.

---

## 5. Công thức MÁY đóng góp vào tính giá

### 5.1 Số lượt in (từ tờ GROSS)
```
so_to_gross = số tờ tốt + bù hao (canh máy + %chạy)     ← xem cascade hao ở spec-cong-doan
passes:
  in 1 mặt / mỗi mặt riêng:  passes_mặt = ceil(so_mau_mặt / so_units)
  perfector 4/4:  passes = 1  NẾU (so_mau_truoc ≤ units_truoc) VÀ (so_mau_sau ≤ units_sau)
                  ngược lại → thêm lượt cho phần vượt
  tự trở (work_turn): passes = 2 (chạy trước, lật, chạy sau) — nhưng 1 bộ kẽm, 1 canh máy (§5.2)
so_luot = so_to_gross × passes
```

### 5.2 Canh máy & tự trở (ĐÃ SỬA — bug quan trọng)
```
canh_may (tờ + giờ):
  sheetwise 2 mặt:  ×2   (2 bộ kẽm, 2 lần lên khuôn)
  tự trở:           ×1   (1 bộ kẽm) + hao tái định vị nhỏ  ← KHÔNG ×2
  perfector:        ×1   (lên cả 2 mặt 1 lần)
tự trở còn: giấy ÷2 (1 tờ cắt đôi ra 2 thành phẩm — đã phản ánh ở con/tờ của bình bài)
```

### 5.3 Tốc độ thực (efficiency)
```
toc_do_thuc = toc_do × efficiency_pct
gio_chay = so_luot / toc_do_thuc
tien_cong_may = (gio_chay + gio_canh_may) × BHR    [hoặc dùng per-1000-lượt ở Công đoạn]
```

---

## 6. Hợp đồng engine (Máy cấp gì)
```
CHO BÌNH BÀI: { gripper_mm, kho_max/min, so_units, cho_phep_tu_tro, cho_phep_tro_dau_duoi,
                le_hong_mm?, duoi_thang_mau_mm?, truc?{repeat, pitch, dia} }
CHO TÍNH GIÁ: { BHR / don_gia_ban_gio, toc_do × efficiency, makeready_time, thoi_gian_rua_muc,
                bu_hao_canh_may_per_mau, bu_hao_chay_pct, units_truoc/sau, khoa_class,
                chi_phi_phu_per_m2?, click_*? (digital), don_gia_muc_per_m2? (wide/inkjet) }
CHO SCHEDULING: { toc_do, lich, so_ca, so_may_song_song, may_thay_the, availability_pct }
```

---

## 7. Seed data
| ma | loai_may | field đặc thù |
|---|---|---|
| OFF-74-4C | press_offset_sheet | max 740×530, min 210×280, gripper 12, so_units 4, khoa_class 74, sph 13.000, canh máy 100/màu, CIP3 |
| OFF-102-5C | press_offset_sheet | max 1020×720, so_units 5+coater, uv, perfector (units 5+5), khoa_class 102 |
| DIG-SRA3 | press_digital | cong_nghe=toner, max 330×487, click_mau 1.200đ/mặt, VDP |
| CTP-B1 | prepress_ctp | ban ≤ 1030×790, nhiệt, 2400dpi, processless, 20 bản/giờ |
| XEN-115 | finishing (guillotine) | max_cut 1150, gsm 60–400 |
| CAN-BONG | finishing (laminator) | max_width 720, film gloss, hot |
| GC-CANMANG | thue_ngoai | NCC X, per_m2, min 50m², markup 15% |

---

## 8. Validate & lỗi
| Code | Điều kiện | Loại |
|---|---|---|
| E-MAY-KHO | kho_min > kho_max | chặn |
| E-MAY-NHIP | gripper_mm ≥ kho_min_rong | chặn |
| E-MAY-BHR0 | BHR ≤ 0 hoặc gio_tinh_phi ≤ 0 | chặn |
| E-MAY-SPEED | toc_do / toc_do_min / toc_do_max ≤ 0 | chặn |
| E-MAY-SPEED-RANGE | min > max, hoặc min > trung bình, hoặc max < trung bình | chặn (chỉ kiểm ô ĐÃ khai — không ép khai đủ ba) |
| E-MAY-JOBFIT | job: khổ in > kho_max hoặc < kho_min | chặn (khi báo giá) |
| W-MAY-GSM | job_gsm ngoài [min,max]_stock_gsm | cảnh báo |
| W-MAY-PROD | productivity/availability ngoài [50,98]% | cảnh báo |
| W-MAY-OVH | overhead_gio nghi trùng dòng đã itemize (lãi/BH/mặt bằng/điện/bảo trì/lương) | cảnh báo |
| W-MAY-BHR-OLD | ngay_cap_nhat_bhr > 12 tháng | cảnh báo |
| E-MAY-CTP-FIT | kẽm CTP > kho_ban_in của máy in dùng nó | chặn |

---

## 9. Ranh giới & seam
```
QUY TẮC BÌNH BÀI : cách xếp, side_margin/tail_colorbar (product-intent). Máy giữ gripper (+ le_hong/duoi tùy chọn); engine = max(rule, máy).
SẢN PHẨM         : khổ TP, số trang, binding, dieline, số màu/mặt
CÔNG ĐOẠN        : đơn giá gia công per-basis; kem_line (giá kẽm ← máy.khoa_class); công ghi CTP (BHR)
VẬT TƯ (VAT_TU)  : giấy (tờ nguyên, caliper) + mực (định mức) — BHR loại trừ
KẼM & KHUÔN      : giá kẽm theo khoa_class; khuôn bế/ép (tooling_ref)
BÁO GIÁ          : overhead công ty + margin + chiết khấu + VAT (KHÁC markup theo máy)
KẾ TOÁN          : ma_tai_san → khấu hao; ma_TK → GL
SFDC             : giờ/số lượng thực tế theo job+công đoạn → đối soát BHR & bù hao
```

---

## 10. Changelog — fix từ phản biện (6 agent)
1. **Lãi vốn** → tính trên **vốn bình quân** `((von+thu_hồi)/2)`, không phải vốn đầy (trước gấp đôi).
2. **Mọi chi phí đứng** (khấu hao/lãi/BH/mặt bằng/overhead) chia **CÙNG `gio_tinh_phi`**; chỉ điện/chạy dùng giờ chạy.
3. **Điện** thêm `he_so_tai_dien` (0,6–0,8) — không kéo full kW.
4. **Giờ tính phí** dùng `availability × productivity`; `efficiency` derate **tốc độ** (run-time); bảo trì trong availability (hết trùng).
5. **Lương** thêm `luong_burden_pct` (+25–40%) + chia `so_may_song_song`.
6. **Tự trở**: canh máy ×1 (KHÔNG ×2), giấy ÷2 — sửa bug cũ.
7. **Perfector**: passes=1 chỉ khi 2 mặt vừa units; `units_truoc/units_sau`.
8. **overhead_gio** = chỉ phần gián tiếp CÒN LẠI (chống trùng).
9. **Số lượt** từ tờ **GROSS** (tốt + canh máy + spoilage).
10. **Thêm capability** cho 3 loại rỗng: `press_gravure`, `wide_format`, `finishing_subtype`; `press_digital` toner/inkjet; CTP `do_phan_giai/processless`; web folder/ribbon/hao cuộn; flexo `anilox_bcm/stations/cure/inline`.
11. **Thêm** salvage, tài sản/GL, SFDC, đồng hồ lượt, bảo trì, rửa mực tách, capacity song song/thay thế, khổ bản, zone mực, substrate class, khoa_class, ca/site.
12. **Seam**: `khoa_class → giá kẽm`; CTP = công ghi (không trùng kem_line vật tư); coating consumable tính 1 lần ở bước in.
13. **Đổi tên** `che_do_gia → nguon_bhr` (hết trùng với Công đoạn); bỏ field `active` (suy từ `trang_thai`).
