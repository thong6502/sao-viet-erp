# SPEC — ENGINE TÍNH GIÁ (Costing / Quoting Engine)

> **Bộ não ráp giá.** Input từ 6 nguồn (Sản phẩm · Quy tắc bình bài · Máy · Công đoạn · Kho hàng · cấu hình Báo giá) → pipeline → **giá bán** (theo từng bậc SL, đã VAT).
> KHÔNG khai liệu — chỉ **logic tính**. Dữ liệu ở 6 module kia.
> Anh em: `spec-quy-tac-binh-bai.md`, `spec-may-thiet-bi.md`, `spec-san-pham.md`, `spec-cong-doan.md`.

---

## 1. Tổng quan

### 1.1 Bản chất
Engine là **hàm thuần**: `giá = f(JobSpec, Máy, Kho, cấu hình Báo giá)`.

### 1.2 Ba tầng
```
① MODULE MASTER (khai liệu) → ② ENGINE (pipeline) → ③ BÁO GIÁ (thương mại)
```

### 1.3 Nguyên tắc bất biến
- **Tờ in không khai** — engine tính ra.
- **Sản phẩm = 1..n BỘ PHẬN (component)** — mỗi bộ phận chạy engine riêng rồi cộng (§4.0).
- **Hao lan truyền ngược** — mua đủ giấy/in.
- **Mỗi chi phí tính đúng 1 lần** — chống trùng.
- **Làm tròn 1 lần ở cuối** — không làm tròn giữa chừng.

---

## 2. Vị trí trong hệ thống
```
   SẢN PHẨM (JobSpec → components; +rule/routing/VAT) ┐
   MÁY (khổ/nhíp/units/BHR/bù hao/khoa_class)          │
   KHO HÀNG (giấy: khổ/gsm/caliper/thớ/giá; mực; bản)   ├─► ENGINE ─► BÁO GIÁ
   CÔNG ĐOẠN (danh mục + routing)                       │   (§4)       (§6)
   DIELINE/khuôn (khổ trải hộp)                         ┘
```

---

## 3. Thực thể engine cần

### 3.1 `giay_nguyen` (mặt hàng GIẤY trong Kho hàng)
| Field | Kiểu | Mô tả |
|---|---|---|
| id · ten | | |
| kho_dai, kho_rong | int(mm) | khổ tờ nguyên |
| gsm | int | định lượng |
| caliper_micron | int | độ dày (spine/creep — gsm ≠ caliper) |
| tho | enum(canh_dai, canh_ngan) | thớ |
| don_vi_gia | enum(kg, ram, to) | đơn vị bán |
| don_gia | money | giá theo đơn vị |
| ton | number | tồn |

> Mực + bản kẽm cũng là **mặt hàng Kho**. Engine đọc bằng **khóa Kho**; thiếu mặt hàng → **báo lỗi**, KHÔNG âm thầm tính 0.

### 3.2 `bao_gia` (HEADER thương mại)
| Field | Kiểu | Mô tả |
|---|---|---|
| khach_hang_id | FK | |
| overhead_cty_pct | pct | G&A công ty (KHÁC overhead giờ máy; xem §6.4 tranche) |
| he_so_lai | number | **hệ số cộng lãi** — xem §6.2 (markup vs margin) |
| kieu_lai | enum(markup_tren_von, margin_tren_gia_ban) | cách hiểu he_so_lai |
| chiet_khau_pct | pct | chiết khấu thương mại (trong base VAT) |
| don_toi_thieu | money | **MOQ** — sàn giá net trước VAT |
| bac_so_luong[] | json | nhiều bậc SL (engine chạy lại toàn bộ mỗi bậc) |
| vat_rate | enum(0, 5, 8, 10) | theo Loại SP, theo ngày hóa đơn |
| hieu_luc_den · dieu_khoan | | |

### 3.3 `component` (BỘ PHẬN — mới, mấu chốt)
Sản phẩm chia thành **bộ phận** in/gia công độc lập:
| structural_type | Bộ phận |
|---|---|
| flat / box / label | 1 bộ phận |
| multipage | **ruột + bìa** (2), + chèn/insert nếu có |
| hộp có ngăn | thân + ngăn + nắp… |

Mỗi component mang: khổ (trải), giấy, số màu trước/sau (+pha), số mặt, số tay (nếu ruột), imposition rule, finishing riêng. **Bìa rời = 1 component** (không phải trường hợp đặc biệt).

### 3.4 Dieline
Hộp mới: khổ trải suy từ 3D + `kieu_hop` (spec-san-pham §3.4); có khuôn → `dieline_id`. Nesting theo **yield**, không phải grid (§4.3).

---

## 4. PIPELINE (chạy cho MỖI bậc số lượng)

### 4.0 Cấu trúc tổng — CASCADE 2 TẦNG (CUỐN trước, rồi COMPONENT)
> Hao **lan truyền ngược** cả 2 tầng: đóng cuốn là bước cuối → nở ngược lên **số cuốn** → nở lên **số lượng từng bộ phận** → mới chạy engine bộ phận. Hao đóng cuốn là **HỆ SỐ NHÂN SỐ LƯỢNG**, KHÔNG phải khoản tiền cộng thêm.
```
for mỗi bậc so_luong:
   components + qty_per_cuon (BOM §4.0b)

   ── TẦNG CUỐN (backward) ──
   cuon_good = so_luong
   for mỗi bước assembly k (m bước, từ cuối → đầu):
       cuon_in(k) = cuon_out(k) / (1 − spoilage_assembly_k)
   cuon_effective = cuon_in(bước đầu)          # số cuốn phải VÀO dây đóng

   ── TẦNG COMPONENT ──
   for mỗi component c:
       output(cuối)_c = cuon_effective × qty_per_cuon_c     # §4.0b
       (kết quả cạnh) = CHẠY §4.1–4.6 (sheet HOẶC web) từ output đó

   gia_von = Σ components
           + ASSEMBLY LABOR (§4.7, tính trên cuon_effective — KHÔNG cộng lại hao)
           + CHẾ BẢN/PROOF (§4.8)   + ĐÓNG GÓI/GIAO HÀNG (§4.9)
   giá bán = LẮP RÁP BÁO GIÁ (§6)
```

### 4.0b BOM — hệ số `qty_per_cuon` mỗi bộ phận
```
bìa      : 1
ruột     : số_tay (= so_forms của ruột)
insert   : số_insert_mỗi_cuốn
box thân : 1 ; box ngăn/insert : n
→ output(cuối)_c = cuon_effective × qty_per_cuon_c   (áp cho MỌI số bộ phận, không chỉ 2)
```

### 4.1 Bình bài (mỗi component)
Gọi engine bình bài theo `layout_mode`:
- step_repeat → con/tờ in ; signature → **số tay** + con/tờ ; nesting → blank/tờ (yield) ; repeat_around → tem/vòng.
- OUT: đơn_vị/tờ in, khổ tờ in, **tờ_in/tờ_nguyên** (xả giấy), work_style/tự trở, **so_forms** (§12 định nghĩa).

### 4.2 Routing (mỗi component)
Bung `routing_template` (source=inherited) + `finishing_chon` (manual) → danh sách công đoạn có thứ tự.

### 4.3 Chọn NHÁNH VẬT LIỆU (deterministic theo `material_form` mỗi component)
```
material_form = web_roll (có web/core/repeat) → NHÁNH WEB (§4.3w)
              = sheet   (còn lại)             → NHÁNH SHEET (§4.4–4.5)

SHEET: con/tờ ← BÌNH BÀI.
   • flat / multipage : con/tờ bình thường
   • BOX : con/tờ = SỐ BLANK NGUYÊN đếm từ dieline (bình bài), KHÔNG dùng tỉ lệ diện tích;
           rồi §4.4–4.5 chạy y hệt. (matrix waste đã nằm trong con/tờ.)
```

### 4.3w Nhánh WEB (tem cuộn / offset cuộn) — cascade theo MÉT (không tờ nguyên)
```
required        = output(cuối)_component (đã nở hao ngược)
tem_per_repeat  = số tem quanh trục / 1 làn ; lanes = số tem ngang khổ
net_met   = ceil( required / (tem_per_repeat × lanes) ) × repeat_length
gross_met = net_met / (1 − run_waste_pct) + setup_waste_m (mỗi màu/đổi cuộn)
số_vòng   = gross_met / repeat_length
⑦ Vật liệu = web_width(m) × gross_met × gsm → kg   [hoặc per_m2]
⑧ Kẽm     = 1 xi-lanh / màu (giá theo repeat/khổ, KHÔNG theo tờ)
⑨ Mực     = đơn_giá × số_vòng × số màu (× coverage)
⑩ In      = per_m2 hoặc per_1000_vòng (không perfector/tự trở)
→ KHÔNG có "tờ nguyên", KHÔNG phá giấy §4.5.
```

### 4.4 Cascade hao ngược cấp SHEET (mỗi component sheet)
```
output(bước cuối)_c = cuon_effective × qty_per_cuon_c   (§4.0/§4.0b — ĐÃ nở hao đóng cuốn)
for i = cuối → đầu:  input_qty(i) = output_qty(i) / (1 − spoilage_i)   [override được từng bước]
                     output_qty(i−1) = input_qty(i)
→ đổi đơn vị (con/tay → tờ) tới bước IN → so_to_in_net
bù_hao_canh_máy = so_mau × bù_hao_canh_may_per_mau × so_forms      (tự trở: so_forms×1)
so_to_in_gross  = so_to_in_net + bù_hao_canh_máy + so_to_in_net × bù_hao_chạy_pct
```
> **Makeready & sàn theo FORM:** bù hao canh máy ×`so_forms`; `first_unit_floor`/`min_charge` công in áp **theo form**, không gộp chung — nếu không, job nhiều tay bị thiếu canh máy.

### 4.5 Phá giấy (component sheet)
```
so_to_nguyen = ceil(so_to_in_gross / tờ_in_per_nguyên)      ← 2 mức tờ khác nhau!
kg_giay = kho_nguyên_dai(cm) × kho_nguyên_rong(cm) × gsm × so_to_nguyen / 10.000.000
```
> **Cân theo TỜ NGUYÊN đã mua** (khổ lớn), KHÔNG theo tờ in đã cắt.

### 4.6 Dòng chi phí (mỗi component)
```
⑦ GIẤY   = quy_đổi(kg / số tờ nguyên, don_vi_gia) × don_gia            [Kho]
⑧ KẼM    = kem_line (§5.1); digital=0; web=cylinder/màu
⑨ MỰC    = Σ mặt: đơn_giá_mực(coverage band, loại mực) × (số_lượt/1000) × số_màu_mặt   [Kho]
⑩ IN     = per_1000_lượt (sàn 1.000 đầu, bậc thang) HOẶC BHR×giờ (§5.2)
⑪ GIA CÔNG = Σ finishing riêng component (§5.3)
```

### 4.7 Đóng cuốn / Assembly (cấp CUỐN — chuỗi 1..m bước, CHỈ tính LABOR)
```
ASSEMBLY = 1..m công đoạn cấp cuốn (bắt bộ → vào bìa → xén 3 mặt …), mỗi bước:
   { setup, rate_per_cuon, consumable(keo/chỉ/ghim/lò xo), spoilage_assembly_k }
Hao đóng cuốn ĐÃ nở ngược ở §4.0 (thành cuon_effective) → ở đây CHỈ tính LABOR:
   tiền = Σ bước ( setup_k + rate_per_cuon_k × cuon_qty(k) + consumable_k )
   cuon_qty(k) = số cuốn vào bước k (từ cascade cuốn §4.0)
→ KHÔNG cộng "spoilage" thành tiền lần nữa (nó đã là số lượng, không phải chi phí).
```

### 4.8 Chế bản & Proof (1 lần/job)
```
CHẾ BẢN/THIẾT KẾ: cố định/job hoặc theo giờ; toggle "khách cấp file" = 0
GHI KẼM (CTP):    công ghi = BHR×giờ (routing CTP) — KHÁC giá bản (kem_line §5.1)
PROOF:            tùy chọn — proof số/proof ướt × số lần × đơn giá
```

### 4.9 Đóng gói & Giao hàng
```
ĐÓNG GÓI  = ceil(SL / SP_mỗi_thùng) × giá_thùng + màng/dây
GIAO HÀNG = phẳng | theo khoảng cách | theo khối lượng/thể tích (tùy chọn)
```

**v1 ĐÃ CÀI (mg `0244`) — chỉ nhánh PHẲNG, nhập tay theo SẢN PHẨM.** Mục ⑤ "Giao hàng" trong modal
sản phẩm của Tính giá: một ô tiền `phieu_thanh_phan.phi_giao_hang` = TỔNG phí chở cho toàn bộ sản
lượng của sản phẩm đó (khoản MỘT LẦN, không nhân SL). Engine đẻ nó thành nhóm kết quả `giao_hang`
(chỉ xuất hiện khi phí > 0), cộng thẳng vào `gia_von_tp` ⇒ **chịu markup** khi sang Báo giá — chốt:
phí giao hàng là một phần GIÁ THÀNH, không phải khoản thu hộ. Đơn giá hiện kèm phép chia
`phí ÷ SL` để thấy đơn nhỏ đang gánh bao nhiêu.

Gắn vào SẢN PHẨM (không phải phiếu) vì Báo giá markup theo từng `gia_von_tp`; gắn vào sản phẩm
(không phải BƯỚC như `phi_khuon`) vì chở hàng không nằm trong routing.

**NGOÀI phạm vi v1:** ĐÓNG GÓI (thùng/màng/dây) và hai nhánh tính GIAO HÀNG theo vùng·km·khối
lượng — vẫn cần danh mục ở TODO cuối file.

---

## 5. Công thức từng dòng

### 5.1 Kẽm (spec-cong-doan §5.1)
```
so_kem_mặt = so_mau_process_mặt + so_mau_pha_mặt
so_kem(component) = so_forms × ( tự_trở ? distinct(2 mặt) : (so_kem_trước + so_kem_sau) )
TIỀN KẼM = so_kem × don_gia_kem(key = máy.khoa_class)    [bản = mặt hàng Kho]
GUARD: digital → 0 ; web → 1 xi-lanh/màu (theo repeat, không theo tờ)
CTP: chỉ tính CÔNG GHI (§4.8) — KHÔNG cộng lại giá bản
```

### 5.2 Công in (số lượt)
```
passes:  sheetwise: ceil(mau_trước/units) + ceil(mau_sau/units)
         perfector: 1 nếu (mau_trước ≤ units_trước) và (mau_sau ≤ units_sau), else +lượt
         tự trở:    2 (2 lần chạy, 1 bộ kẽm, canh máy ×1)
số_lượt = so_to_in_gross × passes
TIỀN IN = max( first_unit_floor, Σ bậc((số_lượt/1000) × rate_tier) )
          [hoặc BHR × (số_lượt/(toc_do×efficiency) + giờ_canh_máy)]
```
> **số_lượt đếm LƯỢT (mặt), không phải lượt-màu.** Mực (⑨) nhân lại số màu.

### 5.3 Gia công (mỗi bước)
```
basis_qty: per_ram=tờ/500 · per_m2=dt_tờ×tờ×mặt · per_pass=lượt · per_book=cuốn · per_number=con
tiền = setup + run_rate×basis_qty + (reuse_tooling? 0 : giá_khuôn) ; sàn max(., min_charge)
```

---

## 6. LẮP RÁP BÁO GIÁ (thương mại) — đã sửa

### 6.1 Thứ tự (làm tròn 1 LẦN ở cuối)
```
gia_von                                              (Σ component + assembly + chế bản + gói/giao)
gia_thanh   = gia_von × (1 + overhead_cty_pct)       ← G&A công ty (tranche riêng §6.4)
gia_truoc_ck= áp LÃI theo §6.2
gia_net     = gia_truoc_ck × (1 − chiet_khau_pct)    ← chiết khấu THƯƠNG MẠI (trong base VAT)
gia_net     = max(gia_net, don_toi_thieu)            ← SÀN MOQ (trên net TRƯỚC VAT)
VAT         = gia_net × vat_rate
gia_ban     = gia_net + VAT
don_gia_ban = gia_ban / so_luong
→ chỉ round(gia_net), round(VAT), round(gia_ban) ở BƯỚC CUỐI
```

### 6.2 Lãi — markup vs margin (bẫy kinh điển)
```
kieu_lai = markup_tren_von     : gia_truoc_ck = gia_thanh × (1 + he_so_lai)
kieu_lai = margin_tren_gia_ban : gia_truoc_ck = gia_thanh / (1 − he_so_lai)
Quy đổi: markup = margin / (1 − margin)   (margin 30% = markup 42,86%)
```
> UI phải ghi RÕ đang nhập markup hay margin — không để 1 số hiểu 2 nghĩa.

### 6.3 VAT
- Trên **net SAU chiết khấu + SAU sàn MOQ**. Không tính VAT trước chiết khấu.
- `vat_rate` cấu hình theo Loại SP + ngày hóa đơn (sách 5%, in thường 8/10%).
- Chiết khấu **thanh toán** (nếu có) là khoản KHÔNG giảm base VAT — mô hình riêng.

### 6.4 Hai tầng lãi — không trùng (tranche rời)
```
markup theo MÁY (BHR × (1+markup)) : CHỈ THU HỒI CHI PHÍ máy (khấu hao/điện/mặt bằng) —
                                     KHÔNG chứa lãi; đã LOẠI khỏi overhead_cty
overhead_cty_pct                    : CHỈ G&A ngoài máy (base = giá vốn ĐÃ gồm markup máy;
                                     nếu calibrate trên chi phí trực tiếp thì áp trước khi cộng markup máy)
he_so_lai (Báo giá)                 : LÃI THUẦN — tranche lãi DUY NHẤT, áp 1 lần
→ xuất breakdown: trực tiếp + thu hồi máy + overhead + lãi = giá trước CK (assert không trùng)
```
> **Chốt:** lãi chỉ nằm ở `he_so_lai`. `markup theo máy` = 0% lãi. Nếu shop muốn máy có lãi riêng thì `he_so_lai` phải áp trên (trực tiếp+overhead) rồi CỘNG markup máy sau — không nhân lãi lên markup máy.

### 6.5 Bậc số lượng
Mỗi bậc **chạy lại TOÀN BỘ** §4–§6 (bình bài lại, phân bổ lại cố định, xét lại chiết khấu + MOQ). **KHÔNG** nhân tuyến tính đơn giá bậc khác.

---

## 7. VÍ DỤ

### 7A. Name card 10.000 · 4/4 · Couché 300 · máy khổ 74 (1 bộ phận, flat)
> **2 mức tờ (đừng nhầm):** tờ nguyên 65×86 → cắt đôi → **2 tờ in 43×65** (vừa máy 74).
```
con/tờ IN = 44   →   con/tờ NGUYÊN = 44 × 2 = 88
tờ in NET = ceil(10.000/44) = 228 tờ in       (= 114 tờ nguyên)
+ bù hao : canh máy ~100 tờ in + 2% chạy → tờ in GROSS ≈ 333   (= 167 tờ nguyên)
```
| Dòng | Tính | Tiền |
|---|---|---|
| ⑦ Giấy | 65×86×300×167/1e7 = 28,01 kg × 30k | **840.000** |
| ⑧ Kẽm | 1×(4+4)=8 × 100k (khổ 74) | **800.000** |
| ⑨ Mực | Σ 2 mặt × (**lượt/mặt 333**/1000 × 4 × ~8k) = 2×10,7k | **~21.000** |
| ⑩ In | passes=2 → 333×2 = 666 lượt (đếm mặt) < 1.000 → sàn | **350.000** |
| ⑪ Gia công | cán 1 mặt (0,43×0,65)×333 = 93 m²×2.200 = 205k · cắt 1 ram = 60k *(bo góc thêm bế)* | **265.000** |
| ⑫ Chế bản | 1 lần | **150.000** |
| **GIÁ VỐN** | | **2.426.000** |

**Báo giá:** +overhead 15% = 2.790k → **markup** 20% = 3.348k → chiết khấu 0 → net 3.348k → +VAT 8% = **3.616.000đ** → **362đ/cái** *(làm tròn 1 lần ở cuối)*.
> **Bẫy đã sửa:** mực đếm **lượt/mặt (333)**, không phải lượt gộp 666 → không nhân đôi. (`số_lượt` ⑩ đếm mặt để tính công in; mực ⑨ dùng lượt-mỗi-mặt rồi nhân số màu.)

### 7B. Catalogue 1.000 cuốn, A4, ruột 32 trang 4/4 + bìa 4/4 cán bóng (ĐA BỘ PHẬN)
```
── TẦNG CUỐN (nở hao đóng keo TRƯỚC) ──
cuon_good = 1.000 ; đóng keo hao 2% → cuon_effective = 1000/0,98 ≈ 1.021 cuốn

── TẦNG COMPONENT (từ cuon_effective) ──
COMP1 RUỘT : qty_per_cuon = số tay = ceil(32/16) = 2 → output = 1.021×2 = 2.042 tay
             kẽm ruột = 2 tay × 4 màu × 2 mặt = 16 ; rồi §4.4 cộng bù hao canh máy (×so_forms=2)
             → giấy ruột + kẽm 16 + in ruột
COMP2 BÌA  : qty_per_cuon = 1 → output = 1.021 tờ ; giấy bìa (loại khác)
             kẽm bìa = 1×(4+4) = 8 ; §4.4 + bù hao ; + CÁN BÓNG (finishing riêng bìa)
ASSEMBLY   : ĐÓNG KEO — LABOR trên 1.021 cuốn (setup+rate×cuốn+keo) — hao đã tính ở số lượng
CHẾ BẢN    : 1 lần
GIÁ VỐN = (ruột) + (bìa) + (đóng keo labor) + chế bản + gói/giao
```
→ **Bìa = component riêng** (kẽm/giấy/in/gia công riêng). Hao đóng keo **nở vào 2.042 tay & 1.021 tờ** (đúng nguyên tắc hao ngược), KHÔNG cộng thành tiền ở bước đóng.

---

## 8. Guards / edge case
| Tình huống | Xử lý |
|---|---|
| Digital | kẽm=0; click_*/mực-m² |
| Tự trở | lượt×2, kẽm×1, canh máy×1, giấy÷2 |
| Perfector | passes=1 chỉ khi 2 mặt vừa units; kẽm cả 2 mặt |
| Phủ inline | tính 1 lần ở bước in, không thêm công đoạn phủ |
| CTP | công ghi (BHR) ≠ giá bản (kem_line) |
| Bù hao in | chỉ từ máy; công đoạn in spoilage=0 |
| Tái bản | dùng lại kẽm/khuôn → bỏ tiền kẽm/khuôn |
| Đa bộ phận | mỗi component chạy riêng + assembly (§4.0) |
| Tem cuộn | nhánh web, không tờ nguyên (§4.3) |
| Hộp | nesting/yield + matrix waste → giấy (§4.3) |
| Gang nhiều mẫu | 1 tờ = carrier nhiều slot; kẽm/tờ tính 1 lần, phân bổ theo slot (entity GangSheet — làm sau) |
| Thớ | jobspec > rule > default; chặn xoay nếu vi phạm |

---

## 9. Hợp đồng I/O
```
INPUT:
  jobspec → components[]; so_luong(bậc); loai_san_pham(rule_id, routing_template, vat_rate)
  may_in{ khổ, nhíp, units, BHR, bù hao, khoa_class, tự trở, perfector, efficiency }
  kho{ giay(khổ,gsm,caliper,thớ,giá,tồn), muc(giá theo coverage/loại), ban_kem(giá theo khoa_class) }
  bao_gia{ overhead_cty, kieu_lai/he_so_lai, chiết khấu, don_toi_thieu, bậc SL, vat }
OUTPUT (mỗi bậc SL):
  { per_component: {con/tay/blank, khổ tờ in, số tờ in, số tờ nguyên, kg, giấy/kẽm/mực/in/gia công},
    assembly, chế bản, proof, gói, giao,
    giá vốn, breakdown(trực tiếp/máy/overhead/lãi),
    giá thành, giá net, MOQ_applied, VAT, giá bán, đơn giá,
    warnings[] }
```

---

## 10. Validate & lỗi
| Code | Điều kiện | Loại |
|---|---|---|
| E-TG-FIT | khổ in > khổ máy | chặn |
| E-TG-KHO-MISS | mặt hàng Kho (giấy/mực/bản) không tồn tại | chặn (không tính 0) |
| E-TG-BINHBAI0 | bình bài trả 0 | chặn |
| E-TG-KEM-DIG | kem_line cho digital | chặn |
| E-TG-COMP | multipage thiếu component bìa khi has_cover | chặn |
| W-TG-CASCADE | tổng hao > 25% | cảnh báo |
| W-TG-LAI | he_so_lai/overhead ngoài dải; hoặc kieu_lai chưa chọn | cảnh báo |
| W-TG-MOQ | net < don_toi_thieu (đã nâng lên sàn) | thông báo |
| W-TG-VAT | vat_rate ∉ {0,5,8,10} | cảnh báo |

---

## 11. Ranh giới & seam
```
SẢN PHẨM  : JobSpec → components + rule_id + routing_template + vat_rate
QUY TẮC BB: con/tay/blank, số tờ, so_forms, work_style
MÁY       : khổ/nhíp/units/BHR/bù hao/khoa_class/tự trở/efficiency
CÔNG ĐOẠN : danh mục + routing + basis/rate/min/tooling + assembly
KHO HÀNG  : giá giấy/mực/bản + caliper + tồn (khóa Kho; thiếu → lỗi)   ← thay Vật tư đã xóa
BÁO GIÁ   : overhead cty + lãi(markup/margin) + chiết khấu + MOQ + bậc SL + VAT
SFDC      : actual → đối soát vốn ước tính vs thực tế
```

---

## 12. Định nghĩa chuẩn `so_forms` (số tay/bản-mẫu)
```
so_forms = số BỘ KẼM PHÂN BIỆT của 1 component:
   flat/box/label : 1
   signature      : số tay = ceil(số_trang / trang_mỗi_tay)
Chủ sở hữu: engine bình bài (spec-quy-tac-binh-bai). Kẽm & bình bài & công-đoạn-theo-tay
đều đọc CÙNG giá trị này, không tự tính lại. (KHÔNG phải số con/số hình lên khuôn.)
```

---

## 13. Changelog — fix từ phản biện
1. **Model component/BOM**: sản phẩm = 1..n bộ phận; mỗi bộ phận chạy engine riêng → cộng + **assembly (đóng cuốn)**. Bìa = component (§3.3, §4.0, §7B).
2. **Nhánh sheet vs web**: tem cuộn tính m² web, không tờ nguyên; hộp nesting/yield + matrix waste (§4.3).
3. **markup vs margin**: tách `kieu_lai` + công thức + quy đổi (§6.2) — hết bẫy.
4. **Thứ tự thương mại**: VAT trên net sau chiết khấu; **MOQ** sàn trước VAT; **làm tròn 1 lần cuối** (§6.1).
5. **2 tầng lãi tranche rời** (máy markup / overhead cty / lãi) — chống trùng (§6.4).
6. **Thêm dòng**: chế bản/thiết kế (toggle khách cấp file), proof, đóng gói, giao hàng (§4.8–4.9).
7. **Mực theo coverage/màu/loại** (§4.6 ⑨).
8. **Ví dụ §7A** rõ 2 mức tờ (con/tờ in vs con/tờ nguyên) + làm tròn đúng; **thêm §7B đa bộ phận**.
9. **Kho hàng khóa** + lỗi khi thiếu mặt hàng (không tính 0) (§3.1, E-TG-KHO-MISS).
10. **`so_forms` định nghĩa chuẩn** + chủ sở hữu (§12).
11. **Gang** = carrier nhiều slot, kẽm/tờ 1 lần, phân bổ theo slot (§8, GangSheet làm sau).
12. **Bậc SL chạy lại toàn bộ**, không nhân tuyến tính (§6.5).

### Vòng 2 (critique sạch) — fix thêm
13. **Hao đóng cuốn nở NGƯỢC vào số lượng bộ phận** (§4.0), KHÔNG cộng thành tiền ở §4.7 — cascade 2 tầng (cuốn → component). *(bug lớn nhất)*
14. **BOM `qty_per_cuon`** (bìa=1, ruột=số tay, insert=n) — chạy đúng cho ≥3 bộ phận (§4.0b).
15. **Assembly = chuỗi 1..m bước** cấp cuốn, chỉ tính LABOR (§4.7).
16. **Makeready ×`so_forms`** + sàn công in theo form (§4.4) — hết giả định 1-form.
17. **Nhánh WEB có cascade mét riêng** (§4.3w); **box = sheet sub-case**, con/tờ = blank nguyên từ dieline (không tỉ lệ diện tích) (§4.3).
18. **Mực đếm lượt/mặt** (không nhân đôi) — sửa §7A: giá vốn 2.426k → 362đ/cái (trước sai 404đ).
19. **Tranche lãi rõ**: markup máy = 0% lãi; lãi chỉ ở `he_so_lai` (§6.4).

### TODO nhỏ còn lại (chưa vào spec — làm khi build)
- `coverage/độ_phủ` per mặt trên JobSpec + bảng band trên Kho mực (mực chính xác hơn).
- Danh mục **Đóng gói/Giao hàng** (thùng→giá, SP/thùng, cước theo vùng/kg) cho §4.9 — v1 đã có ô phí giao hàng PHẲNG nhập tay theo sản phẩm, còn thiếu đúng phần danh mục này.
- Dòng **AA/PE** (sửa của khách tính tiền / lỗi nhà in miễn phí) + **rush surcharge**.
- Module **Chính sách giá** sở hữu overhead_cty/he_so_lai/chiết khấu/MOQ (global + override theo khách).
- Điều khoản báo giá: đặt cọc, thanh toán, hiệu lực, tiền tệ → vào §9 output.
- `repeat_length` (label) + giá xi-lanh (web) vào JobSpec/Kho.
