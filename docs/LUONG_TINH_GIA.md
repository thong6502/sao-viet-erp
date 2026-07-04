# Luồng Tính giá — thiết kế baseline module Tính giá (MVP)

> **Phạm vi:** Màn **Tính giá** = ra **giá thành trực tiếp (giá vốn kỹ thuật)**. Màn **Báo giá** = giá bán (margin/chiết khấu/VAT) — tài liệu riêng.
> **Nguyên tắc:** engine KHÔNG hard-code hệ số bình bài / công thức — mọi hệ số lấy từ **danh mục** (versioned). MVP chỉ **in offset** (đã bỏ in kỹ thuật số).
> **Ghi chú tham chiếu:** "mục N" (mục 7/8/9/12/14) = **mã backlog cũ** (checklist §15 / DANH_MUC_TINH_GIA), **KHÔNG phải section** của tài liệu này.
> **Nguồn:** thống nhất qua review domain (chủ đầu tư) 2026-07-04. Nền công thức: [DATA_CONTRACTS.md](./DATA_CONTRACTS.md) · [DANH_MUC_TINH_GIA.md](./DANH_MUC_TINH_GIA.md) · nghiệm thu [NGHIEM_THU_KHAY_CARTON.md](./NGHIEM_THU_KHAY_CARTON.md).

---

## 1. Ranh giới Tính giá ↔ Báo giá

```
Màn TÍNH GIÁ  →  GIÁ THÀNH TRỰC TIẾP (giá vốn kỹ thuật)   ← địa hạt kỹ thuật
Màn BÁO GIÁ   →  + Margin − Chiết khấu + VAT → GIÁ BÁN     ← địa hạt thương mại
```
- Báo giá **snapshot** giá thành từ Tính giá (không tính lại).
- **Overhead xưởng tạm thời được HẤP THỤ vào đơn giá giờ máy / đơn giá công đoạn** — không có dòng overhead riêng (ghi rõ để sau khỏi tranh luận).

---

## 2. Danh mục & Cấu hình (8 trang)

| # | Trang | Ghi chú |
|---|---|---|
| 1 | Loại sản phẩm & Quy tắc tính | Định nghĩa sản phẩm + logic tính |
| 2 | Vật tư & Đơn giá vật tư | Giấy, mực, màng, keo, bao bì |
| 3 | Máy móc & Đơn giá giờ máy | Có setup, vệ sinh, đổi màu, đổi kẽm |
| 4 | Công đoạn & Đơn giá gia công | Nội bộ / thuê ngoài |
| 5 | Đơn giá kẽm & khuôn | **Tách: kẽm in · khuôn bế · khuôn ép kim** |
| 6 | Định mức & Bù hao | setup waste, running waste, tỷ lệ đạt |
| 7 | **Khổ giấy tiêu chuẩn** 🆕 | Khổ giấy mua, khổ tờ in |
| 8 | **Kiểu bình bài** 🆕 | Hệ số bình bài — KHÔNG hard-code trong engine |
| — | ~~Đơn giá in kỹ thuật số~~ ❌ | Bỏ (MVP chỉ offset) |

### 2.1 DM Kiểu bình bài (field)

| Field | Ý nghĩa | Ví dụ |
|---|---|---|
| Tên kiểu bình | | 1 mặt · A-B · tự trở · trở nhíp |
| **Hệ số thành phẩm** | Quy đổi số con hình học → số con thành phẩm | 1 · 1 · **½** · tùy |
| **Số lượt qua máy** *(cấu hình, KHÔNG suy từ tên)* | Số lần tờ chạy qua máy | 1 · 2 · 2 · 2 |
| **Hệ số bộ kẽm** | Số bộ kẽm cần | 1 · 2 · 1 · tùy |
| **Hệ số lượt in màu** | Nhân (tờ SX × màu) → lượt tiêu hao mực; **mặc định = số mặt in** | 1 · 2 · 2 · tùy |
| Số mặt in | | 1 · 2 · 2 · 2 |
| Áp dụng cho | | Tờ rơi, hộp, sách, nhãn |
| Có cho phép xoay bài | | Có / Không |
| Ghi chú kỹ thuật | Diễn giải cho người dùng | |

> ⚠️ **"Số lượt qua máy" phải là field cấu hình**, không gán cứng theo tên kiểu — vì máy có perfecting (in 2 mặt 1 lượt) thì khác. Bảng dưới chỉ là **giá trị mặc định gợi ý**:

| Kiểu | Hệ số bộ kẽm | Số lượt qua máy |
|---|---|---|
| 1 mặt | 1 | 1 |
| A-B / trước-sau riêng | thường 2 | thường 2 |
| Tự trở | thường 1 | thường 2 |
| Trở nhíp | thường 1 hoặc 2 | thường 2 |

### 2.2 DM Công đoạn — field bổ sung

| Field | Bắt buộc | Lý do |
|---|---|---|
| **`basis_quantity`** (đơn vị nhân đơn giá) | ✅ | engine phải biết lấy lượng nào: tờ / cái / cuốn / m² / mét dài / lượt |
| **`pricing_method`** | ✅ | lượng×đơn giá · theo giờ máy · khoán · thuê ngoài |
| Có phát sinh khuôn không | | bế, ép kim, dập nổi → khuôn tính riêng |
| Có hao hụt không | | tính ngược sản lượng (tỷ lệ đạt) |
| Nội bộ / thuê ngoài / cả hai | | linh hoạt khi báo giá |
| **Thời gian setup** *(backlog: mục 12)* | | ngoài *phí* setup, cần *thời gian* setup |
| **Đơn giá nhân công đa hình thức** *(backlog: mục 14)* | | giờ / ca / sản phẩm / khoán |

**`basis_quantity` — ví dụ:**
| Công đoạn | basis_quantity |
|---|---|
| Cán màng | m² |
| Bế | tờ |
| Xén | lượt dao / tờ |
| Ép kim | cm² / lượt ép |
| Đóng ghim | cuốn |
| Dán hộp | cái |
| Đóng gói | thùng / cái |

---

## 3. Luồng tính giá (sơ đồ)

```
┌── NHẬP PHIẾU (màn Tính giá) ──────────────────────────────┐
│ • Loại sản phẩm            ← DM Loại sản phẩm             │
│ • Khổ thành phẩm, SL, số màu, số mặt                     │
│ • Khổ tờ in                ← DM Khổ giấy chuẩn (mục 7)    │
│ • Kiểu bình bài            ← DM Kiểu bình bài (mục 8)     │
│ • Giấy, Máy in             ← DM Vật tư, DM Máy            │
│ • Công đoạn gia công       ← DM Công đoạn (nội bộ/ngoài)  │
└───────────────────────────┬───────────────────────────────┘
                            ▼  ENGINE
 1. Số con thành phẩm/tờ = (số con hình học) × Hệ số thành phẩm
 2. Số tờ lý thuyết  = ceil(SL / số con thành phẩm/tờ)
 3. Số tờ sản xuất   = tính NGƯỢC từ cuối chuỗi (tỷ lệ đạt + setup mỗi công đoạn)
                       tới khâu in: + makeready + running%
 4. Số tờ mua giấy   = số tờ sản xuất + hao hụt giấy riêng (nếu có)
 5. Tiền giấy   = số tờ mua giấy × đơn giá giấy   ← quy đổi ram/kg/m²
 6. Tiền kẽm    = màu × Số bộ kẽm × Số form/tay × đơn giá 1 bản kẽm
 7. Tiền mực    = ⌈Lượt in màu/1000⌉ × đơn giá/1000 lượt   (Lượt in màu = tờ SX × màu × Hệ số lượt in màu)
 8. Công in     = Giờ máy × đơn giá giờ
                  Giờ máy = setup + (số tờ SX × Số lượt qua máy)/tốc độ + vệ sinh/đổi màu/đổi kẽm
 9. Gia công    = Σ (nội bộ | thuê ngoài)
                            ▼
10. ══ GIÁ THÀNH TRỰC TIẾP ══ = 5+6+7+8+9 (+ bao bì nếu có)
    Giá thành/đơn vị = Giá thành trực tiếp / SL
    (mỗi dòng hiện DIỄN GIẢI CÔNG THỨC lên UI)
                            ▼
   [SANG BÁO GIÁ]  + Margin − Chiết khấu + VAT → GIÁ BÁN
```

---

## 4. Công thức chi tiết

### 4.1 Số con thành phẩm
```
Số con hình học = max(
   floor(khổ_in_khả_dụng_W / con_W) × floor(khổ_in_khả_dụng_H / con_H),
   floor(khổ_in_khả_dụng_W / con_H) × floor(khổ_in_khả_dụng_H / con_W)   ← nếu cho xoay
)
   khổ_in_khả_dụng = khổ tờ in − nhíp − xén ;  con = khổ TP + bleed + gutter
Số con thành phẩm/tờ = Số con hình học × Hệ số thành phẩm   ← từ DM Kiểu bình bài
```

### 4.2 Số tờ (3 lớp)
```
Số tờ lý thuyết = ceil(SL / số con thành phẩm/tờ)

Số tờ sản xuất  = tính NGƯỢC từ cuối:
   cần trước công đoạn N = ceil(cần sau N / tỷ lệ đạt N) + bù hao setup N
   … tới khâu in:  + makeready(∝ màu) + running%

Số tờ mua giấy  = Số tờ sản xuất + hao hụt giấy riêng (cắt/bốc dỡ) nếu có
```

### 4.3 Giấy
```
Tiền giấy = Số tờ mua giấy × đơn giá giấy   (quy đổi: 1 ram=500 tờ; kg↔tờ qua gsm×khổ; m²)
```

### 4.4 Kẽm
```
Tiền kẽm = Số màu × Số bộ kẽm × Số form in × Đơn giá 1 bản kẽm
```
| Biến | Nghĩa |
|---|---|
| Số màu | 1, 2, 4, Pantone… |
| Số bộ kẽm (`plate_sets`) | do **DM Kiểu bình bài** quyết định (không suy từ tên kiểu) |
| Số form in (`print_form_count`) | số bố cục bình bài cần chế kẽm; **sách: = số tay sách** (`signature_count`) |
| Đơn giá 1 bản kẽm | theo khổ kẽm / máy in |

Ví dụ **Số form in**: Tờ rơi 2 mặt → **1** · Catalogue 16 trang → thường **1 tay** · Sách 64 trang (tay 16) → **4 tay**

### 4.5 Mực — 2 chế độ (MVP dùng chế độ 1)
```
Lượt in màu = Số tờ sản xuất × Số màu × Hệ số lượt in màu   ← Hệ số lượt in màu từ DM Kiểu bình bài
   (mặc định Hệ số = Số mặt in; ≠ "Số lượt qua máy" [giờ máy]; ≠ "Số bộ kẽm" [kẽm] — 3 đại lượng RIÊNG)
Chế độ 1 (MVP):     Tiền mực = ⌈Lượt in màu / 1000⌉ × đơn giá/1.000 lượt   (field `ink_count_basis` chọn cách đếm)
Chế độ 2 (sau này): Tiền mực = Diện tích in × Độ phủ × Định mức tiêu hao × Đơn giá mực
```

### 4.6 Công in
```
Số tờ tính giờ máy = Số tờ sản xuất × Số lượt qua máy
Giờ máy = setup + (Số tờ tính giờ máy / Tốc độ máy) + t/g vệ sinh + đổi màu + đổi kẽm
Công in = Giờ máy × Đơn giá giờ máy
```

### 4.7 Gia công
```
Nội bộ     = (giờ máy | lượng) × đơn giá + nhân công + setup + hao hụt
Thuê ngoài = sản lượng × đơn giá NCC + setup + vận chuyển + hao hụt
```

### 4.8 Giá thành trực tiếp
```
GIÁ THÀNH TRỰC TIẾP = Giấy + Kẽm + Mực + Công in + Gia công (+ Bao bì nếu có)
   (Overhead xưởng đã hấp thụ vào đơn giá giờ máy/công đoạn — chưa phải "giá thành đầy đủ")
Giá thành/đơn vị = Giá thành trực tiếp / SL thành phẩm đạt
```

---

## 5. Quy ước thuật ngữ (tránh lẫn "khuôn")

| Thuật ngữ | Nghĩa | Nuôi chi phí |
|---|---|---|
| **Số bộ kẽm** (`plate_sets`) | số bộ bản kẽm in (do Kiểu bình bài) | Tiền kẽm |
| **Số form in** (`print_form_count`) | số bố cục bình bài cần chế kẽm | Tiền kẽm (nhân) |
| **Số tay sách** (`signature_count`) | số tay của sách/catalogue; mỗi tay = 1 form | = Số form in khi là sách |
| **Khuôn bế** | dies cắt — **KHÁC kẽm** | Gia công (bế) |
| **Khuôn ép kim / dập nổi** | dies ép — **KHÁC kẽm** | Gia công (ép/dập) |

---

## 6. Overhead
Tạm thời **KHÔNG có dòng overhead riêng**. Điện, khấu hao, quản lý xưởng, bảo trì… được **cộng sẵn vào đơn giá giờ máy / đơn giá công đoạn** khi khai danh mục. Khi cần tách "giá thành đầy đủ", thêm lớp phân bổ sau (ngoài phạm vi MVP).

---

## 7. Snapshot (chốt báo giá — copy-on-write)
Lưu **toàn bộ**, không chỉ tổng tiền:
```
input (quy cách) + đơn giá (giấy/kẽm/mực/giờ máy) + định mức + công thức
+ số con + số tờ (lý thuyết/sản xuất/mua giấy) + kiểu bình bài + máy + công đoạn
+ version danh mục / version công thức
+ người tính giá + thời điểm tính + trạng thái báo giá
```
→ Đơn giá vật tư đổi sau này, báo giá cũ vẫn truy được tại sao ra số đó. 1 phiếu tính lại nhiều lần → phân biệt bằng version + thời điểm.

---

## 8. Hiển thị công thức trên UI (3 lớp mỗi dòng)
```
Kết quả:   400.000đ
Công thức: 4 bản × 100.000đ/bản
Diễn giải: 4 bản = 4 màu × 1 bộ kẽm × 1 form/tay
```
Ví dụ khác:
```
Số tờ:  263 tờ = ceil(1.000 / 4 con) + 10 bù hao setup + 3 hao chạy
Công in: 625.000đ = (0.75 setup + 3.000×1 lượt / 6.000 tờ/giờ) × 500.000đ/giờ
```
→ Thấy số lạ là truy được ngay công thức, sửa đúng chỗ (danh mục nào).

---

## 9. Trạng thái hiện tại vs cần làm

| Phần | Engine hiện có | Cần làm |
|---|---|---|
| Số con hình học, số tờ ngược chuỗi, giấy (ram/kg/m²), mực 1-núm, công in giờ máy, snapshot | ✅ | — |
| Gia công nội bộ / thuê ngoài | 🟡 hiện **nhập tay tổng tiền** | công thức **tự động theo DM Công đoạn** |
| **DM Kiểu bình bài** (hệ số thành phẩm / bộ kẽm / lượt qua máy) | ❌ | 🆕 danh mục #8 *(backlog: mục 9)* |
| **Số lượt qua máy nhân vào giờ máy** | ❌ | 🆕 (kèm Kiểu bình bài) |
| **DM Khổ giấy tiêu chuẩn** | ❌ | 🆕 danh mục #7 *(backlog: mục 7)* |
| **Thời gian setup công đoạn + NC đa hình thức** | ❌ | 🆕 field DM Công đoạn *(backlog: mục 12, 14)* |
| **Số tờ mua giấy (hao giấy riêng)** | ❌ | 🆕 nhẹ |
| Bỏ nhánh in kỹ thuật số | (còn) | 🆕 gỡ khỏi nav |

---

## 10. Quy tắc làm tròn (rounding policy)

| Đại lượng | Làm tròn |
|---|---|
| Số con/tờ | **floor** (không lấy con lẻ) |
| Số tờ (lý thuyết / sản xuất / mua giấy) | **ceil** (không in thiếu) |
| Số lượt / 1.000 (mực) | **ceil** (hoặc theo cấu hình) |
| Tiền từng dòng chi phí | làm tròn VND theo cấu hình |
| Giá thành / đơn vị | làm tròn theo cấu hình |

> Ghi cố định ngay từ đầu để tránh lệch vài tờ / vài đồng, sau khó đối chiếu.

---

## 11. Validation tối thiểu (dev + QA)

- số con thành phẩm/tờ **> 0**
- số tờ sản xuất **≥** số tờ lý thuyết
- số tờ mua giấy **≥** số tờ sản xuất
- **0 < tỷ lệ đạt ≤ 1**
- đơn giá **không âm**
- khổ thành phẩm **< khổ in khả dụng** (đã trừ nhíp/xén, cộng bleed)
- công đoạn có khuôn → **phải có đơn giá khuôn HOẶC cho nhập tay**
- kiểu bình bài yêu cầu số bộ kẽm → **phải có đơn giá kẽm**
- mỗi công đoạn **bắt buộc** có `basis_quantity` + `pricing_method`

---

## 12. Test case nghiệm thu tối thiểu (engine)

| # | Case | Kiểm điểm chính | Trạng thái |
|---|---|---|---|
| 1 | Tờ rơi 1 mặt, không gia công | số con, số tờ, giấy, kẽm = màu×1 | cần viết |
| 2 | Tờ rơi 2 mặt, A-B | số bộ kẽm & form theo A-B | cần viết |
| 3 | Tự trở, 4 màu, có kẽm | kẽm÷2, con÷2, lượt×2 | ⚠️ chờ phiếu tự trở thật |
| 4 | Khay carton, bế + dán | = **golden #1 KHAY CARTON** | ✅ đã có |
| 5 | Catalogue nhiều trang, nhiều tay | số tay = form, cộng dồn cấu phần | cần BOM động (sau) |

> Mỗi case: **input + expected output + diễn giải công thức**. Case 4 đã đóng băng (`test_pricing_golden_khay_carton.py`); case 3 làm theo DATA_CONTRACTS, nghiệm thu lại khi có phiếu thật.

---
*Tạo 2026-07-04. Baseline thiết kế module Tính giá — **v1.0 code-ready**. Đã áp: 4 sửa cuối + 5 chỉnh làm rõ + 4 bổ sung code-ready (Hệ số lượt in màu · tách Số form in/Số tay sách + `print_form_count`/`signature_count` · `basis_quantity`+`pricing_method` cho Công đoạn · §11 Validation + §12 Test case). Quyết định: mực giữ 1-núm + field `ink_count_basis`. CHƯA code.*
