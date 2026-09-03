# Danh mục cần khai báo để TÍNH GIÁ (giá vốn → giá bán)

> **Phạm vi:** Chỉ bàn **Tính giá** (giá thành/giá vốn nội bộ). *Tính giá ≠ Báo giá* — báo giá là bước gói lại + chiết khấu + bậc số lượng + giá riêng theo khách, tham chiếu kết quả tính giá.
> **Cơ sở:** Công thức cost-plus offset + logic giainoffset + đối chiếu thực tế màn Tính giá của **NextPrint (Trí Thành Software)**. Không đọc code — suy từ domain & UI đối thủ.
> **Liên quan:** [THI_TRUONG_PHAN_MEM_IN.md](./THI_TRUONG_PHAN_MEM_IN.md) · [DOMAIN_NHA_MAY_IN.md](./DOMAIN_NHA_MAY_IN.md)

> **Đối chiếu code (09/2026):** tài liệu này tự nhận "không đọc code — suy từ domain & UI đối thủ"
> (dòng trên), nên phần lớn nội dung là **NHU CẦU nghiệp vụ**, không phải mô tả engine đang chạy.
> Hai điểm rà soát thấy lệch hẳn với code thật:
> 1. **Mục ③ "Chế bản/Kẽm"** (§2, §7): không có danh mục "đơn giá kẽm theo khổ" nào đang sống. Có
>    bảng `plate_die_rates` với seed, nhưng router đã gỡ (`backend/app/main.py:159-161`), không có
>    trang UI, và **không dòng code tính giá nào đọc bảng này** (0 kết quả trong
>    `thanh_phan_engine.py`). Đơn giá kẽm hiện tại là **hằng số gõ thẳng vào công thức của Công
>    đoạn "Chế bản"** trong danh mục Công đoạn (`cong_thuc_gia`, ví dụ `so_kem * 95000`) — đổi giá
>    kẽm là sửa công thức đó, không phải sửa một danh mục giá riêng.
> 2. **§9.2 "Định nghĩa Margin"**: công thức thật KHÔNG phải `Giá thành / (1 − lãi_suất)`. Engine
>    Báo giá dùng mô hình **markup trên giá vốn**: `giá bán = giá vốn × (1 + markup/100)`, mặc định
>    markup 20%, VAT mặc định 10% (`backend/app/services/quotation_service.py:479-481`) — đúng cái
>    công thức mà mục này liệt kê là "❌ Không dùng" (dòng dưới). Xem đính chính chi tiết tại §9.2.

---

## 0. TÓM TẮT — cần khai những danh mục nào để tính được giá

### 🔴 Bắt buộc — thiếu 1 trong số này là KHÔNG ra được giá

| Danh mục | Cho ra khoản gì |
|---|---|
| **1. Giấy** (họ giấy, gsm, khổ, đơn giá /tờ & /kg) | Tiền giấy |
| **2. Máy in** (khổ máy, **số núm mực**, đơn giá công in) | Tiền công in |
| **3. Chế bản / Kẽm** (đơn giá theo khổ) | Tiền kẽm |
| **4. Mực** (đơn giá VND/1.000 lượt) | Tiền mực |
| **5. Công đoạn gia công** (đơn giá + đơn vị tính) | Tiền cán/bế/dán… |
| **6. Quy cách bình bài** (1 mặt/tự trở/trở nhíp/A-B) | Ra **số con, số tờ, số kẽm** |
| **7. Định mức & Bù hao** (chừa nhíp/xén, bù hao canh máy, %hao) | Ra **số tờ in** |
| **8. Loại màu** (CMYK/pha, số màu) | Ra số kẽm & số lượt mực |
| **9. Loại ấn phẩm** + **ĐVT** + **Đơn vị gia công** | Khung phiếu |

### ⚪ Nền tảng — danh mục con được các mục trên "chọn từ" (khai trước)

**Họ giấy** · **Khổ chuẩn** · **Nhà cung cấp (NCC)** · **Tổ & Đầu việc** (nơi khai **đơn giá khoán** — dùng chung cho tính giá + lương) · **Loại thành phần/cấu phần**.

### 🟡 Thêm khi làm hàng HỘP / BAO BÌ carton

**Vật tư khác** (keo, màng cán…) · **Khuôn bế/cấn** (chi phí làm khuôn 1 lần) · **Tấm/Sóng carton** (sóng E/B/EB — "họ giấy" không tả được) · **Kiểu đóng gói** (nếu tính riêng).

> **Ngắn nhất:** tính **giá thành** cần **9 danh mục đỏ** (+ vài danh mục nền); làm **hộp carton** thêm **khuôn bế + tấm sóng**.
> *(Lãi/chiết khấu/VAT không phải danh mục — là dữ liệu nhập ở màn Báo giá.)*
>
> ⚠️ **Công thức tính (đã chốt):** khai đủ danh mục vẫn cần đúng công thức. Quyết định: (D1) công in tính **theo lượt màu** — bỏ mô hình số lần ép; (D2) **số kẽm theo kiểu bình bài** (tự trở ≠ trở nhíp) — GIỮ; (D3) **cấu trúc BOM đa cấu phần** cho hàng hộp — GIỮ. Chi tiết công thức & cấu trúc: **[DATA_CONTRACTS.md](./DATA_CONTRACTS.md)**.

---

## 1. Mô hình cốt lõi

Giá vốn của một ấn phẩm luôn có dạng:

```
Giá vốn = Σ (Số lượng_dòng × Đơn giá_dòng)  +  Phí cố định
Giá bán = Giá vốn × hệ_số_lời  +  Thuế
```

Với **mỗi dòng chi phí** (giấy, kẽm, công in, mực, gia công, vật tư, đóng gói), engine phải trả lời 2 câu hỏi — mỗi câu = một loại danh mục:

| Câu hỏi | Loại danh mục |
|---|---|
| "**Số lượng** ở đâu ra?" (số con → số tờ → số lượt) | **Danh mục ĐỊNH MỨC** |
| "**Đơn giá** ở đâu ra?" (nuôi tiền) | **Danh mục ĐƠN GIÁ** |

Cộng thêm **Danh mục CHỌN** (cấu trúc phiếu) và **Tham số** (ra giá bán). Đó là toàn bộ khung.

> **Mẹo kiểm tra nhanh:** mỗi **dropdown** trên form tính giá = một danh mục phải khai; mỗi **con số tự nhảy** (số con, số tờ, số lượt, thành tiền) = kết quả của một danh mục *đơn giá* × một danh mục *định mức*. Ô đơn giá hiện `0` ngoài ý muốn → gần như chắc chắn thiếu bản ghi trong danh mục tương ứng.

---

## 2. NHÓM 1 — Danh mục ĐƠN GIÁ (nuôi tiền) · tất cả P0

| # | Danh mục | Thiếu nó → mất biến gì | Khai gì |
|---|---|---|---|
| ① | **Giấy** | Chi phí *Giấy* = 0 | Loại giấy × định lượng (gsm) × khổ tờ → **đơn giá/tờ (hoặc /kg)**, versioned; nguồn giấy (Công ty / Khách cấp → giá 0) |
| ② | **Máy in + đơn giá công in** | Chi phí *Công in* = 0 | Khổ máy, số núm mực, hỗ trợ trở-lật; **đơn giá công in** (theo lượt/giờ) + hệ số khoán; gồm cả "máy gia công ngoài" |
| ③ | **Chế bản / Kẽm** | Chi phí *Trước in* = 0 | Đơn giá kẽm theo khổ + hệ số khoán chế bản |
| ④ | **Định mức mực** | Chi phí *Mực* = 0 | Đơn giá mực = **VND / 1.000 lượt in** (1 núm); tráng phủ có giá mực riêng |
| ⑤ | **Công đoạn gia công** | Chi phí *Sau in* = 0 | Mỗi công đoạn (cán/bồi/bế/dán/kiểm…): **đơn giá + đơn vị tính riêng** (m² / nghìn cái / vị trí / trang / mặt) + hệ số khoán |

---

## 3. NHÓM 2 — Danh mục ĐỊNH MỨC (nuôi số lượng) · P0

| # | Danh mục | Quyết định biến nào |
|---|---|---|
| ⑥ | **Quy cách in / Kiểu bình bài** (1 mặt · tự trở · trở nhíp · A-B · perfecting · tùy chỉnh) | → **Số con trên khổ** → số tờ, số kẽm, số lượt |
| ⑦ | **Định mức & Bù hao** (chừa nhíp / sản / lay kít / đuôi giấy / cả giấy; bù hao makeready + running %; tỷ lệ đạt từng công đoạn) | → **Số tờ in** = ceil(SL / số con / ∏ tỷ lệ đạt) + bù hao |

> ⑥ và ⑦ **dễ bị bỏ quên nhưng tối quan trọng**: thiếu chúng, engine ra được *đơn giá* nhưng **không biết nhân với bao nhiêu tờ** → phải nhập tay, sai số cao. Đây đúng là chỗ NextPrint đầu tư kỹ (5 loại "chừa" giấy + bù hao từng công đoạn).

> **Trạng thái ⑥ (đã làm đủ spec A–E):** danh mục Kiểu bình bài khai đủ 4 bộ hệ số engine dùng độc lập — `finished_factor` (số con thành phẩm) · `pass_count` (giờ máy) · `plate_set_factor` (tiền kẽm) · `ink_pass_factor` (tiền mực) — cùng Nhóm kiểu, điều kiện áp dụng (loại SP / máy / khổ / số mặt / ưu tiên) và version-chain (sửa kiểu đã dùng ⇒ tạo phiên bản mới, báo giá cũ giữ số đã chốt). Màn **Tính giá** có dropdown chọn kiểu (mã ổn định `ONE_SIDE/TU_TRO/TRO_NHIP/AB/PERFECTING/CUSTOM`); engine resolve theo **code → name → suy số mặt**. Chi tiết cột: [DB_SCHEMA.md → `imposition_types`](./DB_SCHEMA.md).

---

## 4. NHÓM 3 — Danh mục CHỌN (cấu trúc phiếu) · P0 về lưu trữ

| # | Danh mục | Vai trò |
|---|---|---|
| ⑧ | **Loại ấn phẩm** (tờ rơi / hộp / sách…) | Khung + cấu hình mặc định (số mặt, gia công điển hình) |
| ⑨ | **ĐVT** (cái / cuốn / kg…) | Đơn vị đếm & bán |
| ⑩ | **Loại thành phần / cấu phần** (bìa, ruột, khay…) | Sản phẩm nhiều cấu phần → mỗi cấu phần tính giấy + in riêng rồi cộng |
| ⑪ | **Loại màu** (CMYK / pha-Pantone) | Số màu × hệ số → số kẽm × số lượt (có thể mặc định CMYK) |

---

## 5. NHÓM 4 — Danh mục hỗ trợ · P1 (chưa có vẫn tính được job đơn giản)

| # | Danh mục | Dùng khi |
|---|---|---|
| ⑫ | **Vật tư khác** (màng cán, keo, ghim…) — đơn giá + % bù hao | Job có vật tư phụ |
| ⑬ | **Kiểu đóng gói** — đơn giá công đóng gói/thùng | Job cần đóng gói |
| ⑭ | **Nhà cung cấp / ĐV gia công ngoài** — định tuyến + giá khoán | Có công đoạn thuê ngoài |

---

## 6. NHÓM 5 — Tham số ra GIÁ BÁN (ranh giới sang báo giá)

| # | Tham số | Vai trò |
|---|---|---|
| ⑮ | **Hệ số lợi nhuận / lãi suất** (bậc thang hoặc theo dòng) | `Giá bán = Giá vốn / (100% − lãi)` |
| ⑯ | **Thuế suất** (VAT, TNDN), **hoa hồng**, **làm tròn** | Ra đơn giá bán cuối |

---

## 7. Sơ đồ: Danh mục → Biến công thức

```
                         ┌─────────────────────────────────────────────┐
   INPUT theo từng lần    │  SL đặt in · Khổ thành phẩm · Số mặt · Số màu │
   (không phải danh mục)  └───────────────────────┬─────────────────────┘
                                                  │
        ┌─────────────────────────────────────────┼──────────────────────────────┐
        ▼                                          ▼                              ▼
  ⑥ Quy cách bình bài ─────► SỐ CON/KHỔ      ⑪ Loại màu ─────► SỐ MÀU        ⑧⑨⑩ Loại ấn phẩm/
        │                        │                                  │              ĐVT/Cấu phần
        ▼                        ▼                                  ▼            (khung phiếu)
  ⑦ Định mức & Bù hao ─► SỐ TỜ IN = ceil(SL/số con/∏đạt)+bù hao   SỐ KẼM = màu×mặt
        │                        │                                  │
        │           ┌────────────┼──────────────┐                   │
        ▼           ▼            ▼              ▼                    ▼
   SỐ LƯỢT     ① Giấy       ② Máy+công in   ④ Định mức mực     ③ Chế bản/Kẽm
  = màu×tờ     ×đơn giá     ×đơn giá×lượt   ×(lượt/1000)       ×đơn giá kẽm
        │           │            │              │                    │
        └───────────┴─────┬──────┴──────────────┴────────────────────┘
                          ▼
                    + ⑤ Gia công (×đơn vị riêng)  + ⑫ Vật tư  + ⑬ Đóng gói  + Phí cố định
                          ▼
                   ══════ GIÁ VỐN ══════
                          │
                          ▼  × ⑮ hệ số lời   + ⑯ VAT/TNDN/hoa hồng
                   ══════ GIÁ BÁN ══════   ◄── (từ đây trở đi là địa hạt BÁO GIÁ)
```

---

## 8. Kết luận — bộ tối thiểu để "bấm ra được giá"

- **Ra GIÁ VỐN:** cần **10 danh mục P0** → ① Giấy · ② Máy + công in · ③ Chế bản/kẽm · ④ Định mức mực · ⑤ Công đoạn gia công · ⑥ Quy cách bình bài · ⑦ Định mức & bù hao · ⑧ Loại ấn phẩm · ⑨ ĐVT · ⑪ Loại màu.
- **Ra GIÁ BÁN:** thêm **⑮ hệ số lợi nhuận + ⑯ thuế**.
- **Job phức tạp:** thêm **⑫ Vật tư · ⑬ Đóng gói · ⑭ NCC gia công**.

**Điểm nhấn thiết kế cho SVN:** đa số người xây phần mềm in nhớ khai **đơn giá (Nhóm 1)** nhưng **quên Nhóm 2 (định mức & bình bài)** — thiếu Nhóm 2 thì hệ thống không tự ra số lượng, buộc nhập tay, sai số cao. Ba khác biệt đáng học từ NextPrint: (a) **nguồn giấy / khách cung cấp** (giá 0) là một trạng thái phải mô hình hóa; (b) **máy in gộp luôn "gia công ngoài"** thành một dòng máy; (c) **bù hao bình bài rất chi tiết** (chừa nhíp / sản / lay kít / đuôi giấy / cả giấy) — SVN nên nâng danh mục định mức lên đúng độ chi tiết này.

---

## 9. Lớp Báo giá — từ Giá thành ra Giá bán

> **Ranh giới:** màn Tính giá dừng ở **Giá thành (giá vốn)**. Báo giá là lớp đắp thêm, tham chiếu (snapshot) Giá thành chứ không tính lại.

### 9.1 Công thức (thứ tự & nền tính là bắt buộc)

```text
① Giá thành                     (từ Tính giá — snapshot, cố định)
② + Margin  → Giá bán gộp
③ − Chiết khấu → Giá bán thuần (chưa VAT)      ← chiết khấu TRỪ
④ + VAT → Giá bán cuối (đã gồm thuế)           ← VAT tính trên nền ③, KHÔNG phải ①
```

- **Chiết khấu là phép TRỪ** (giảm giá), không cộng.
- **VAT luôn tính SAU CÙNG, trên nền đã trừ chiết khấu** — không tính trên giá thành.

### 9.2 Định nghĩa Margin — CHỐT lúc viết tài liệu: theo **Lãi suất**; CODE THẬT: theo **Markup**

> **Đối chiếu code (09/2026) — mục này ĐÃ LỖI THỜI.** Phần dưới đây (công thức + ví dụ) là bản CHỐT
> lúc viết tài liệu, dùng mô hình "lãi trên doanh số". Engine Báo giá đang chạy KHÔNG dùng mô hình
> này — nó dùng đúng thứ mà mục này gắn nhãn "❌ Không dùng": **markup trên giá vốn**
> (`backend/app/services/quotation_service.py:479-481`):
> ```text
> Giá bán gộp = Giá vốn × (1 + markup / 100)      # markup mặc định 20%
> ```
> Giữ nguyên nội dung cũ bên dưới để lưu lịch sử thiết kế; đừng lấy công thức `/ (1 − lãi_suất)`
> làm căn cứ code hiện tại.

```text
Giá bán gộp = Giá thành / (1 − lãi_suất)
```

- `lãi_suất` = **% trên doanh số** (cách nhà in VN quen nói "lãi 20%") → luôn **< 100%**.
- Có thể để **bậc thang theo giá vốn** (như giainoffset).
- ❌ **Không** dùng markup theo hệ số (`× (1+m)`) — đã loại để tránh hiểu nhầm. *(Ghi chú
  09/2026: code thật đi ngược lại đúng điều này — xem callout ngay trên.)*

**Ví dụ theo bản CHỐT cũ (giá thành 100, lãi 20%, chiết khấu 5%, VAT 8%) — không phải số engine
thật sẽ ra:**

| Bước | Phép tính | Kết quả |
|---|---|---|
| ② Giá bán gộp | 100 / (1 − 20%) | 125 |
| ③ − Chiết khấu 5% | 125 − 6.25 | 118.75 |
| ④ + VAT 8% | 118.75 × 1.08 | **128.25** |

**Ví dụ theo code thật (giá vốn 100, markup 20%, VAT 10% mặc định):**

| Bước | Phép tính | Kết quả |
|---|---|---|
| ② Giá bán gộp | 100 × (1 + 20%) | 120 |
| ④ + VAT 10% (bỏ qua chiết khấu) | 120 × 1.10 | **132** |

### 9.3 Chỉ số cho nhập ở màn Báo giá

| Chỉ số | Kiểu nhập | Ghi chú |
|---|---|---|
| **Lãi suất** | % (có thể bậc thang / theo khách) | Mặc định lấy ở Tính giá, cho override |
| **Chiết khấu** | **% hoặc số tiền tuyệt đối** | Hỗ trợ cả hai; mức lớn → **có duyệt** |
| **VAT %** | % (8/10) | Mặc định theo loại hàng, cho sửa |
| **Phí khác** | số tiền | Vận chuyển, phát sinh, làm mẫu… nếu chưa gộp giá thành |
| **Bậc số lượng (price break)** | bảng SL → đơn giá | Báo giá thường 2–3 mức SL |
| **Làm tròn giá bán** | cờ + mức làm tròn | (NextPrint có sẵn) |
| **Hiệu lực / điều khoản** | ngày, text | Ngày hết hạn, điều khoản thanh toán |

### 9.4 Lưu ý thiết kế (từ domain SVN)

1. **Snapshot giá copy-on-write khi chốt báo giá** — khóa Giá thành + lãi suất + chiết khấu tại thời điểm chốt; giá giấy/vật tư đổi sau đó không làm sai báo giá đã gửi. (Construct P0 bắt buộc.)
2. **Chiết khấu & lãi suất cho override có duyệt + ghi audit**, không chặn cứng — linh hoạt nhưng truy vết được ai giảm giá.

---
*Tạo 2026-07-03 từ nghiên cứu domain + đối chiếu màn Tính giá NextPrint. Mục 9 (Lớp Báo giá) bổ sung sau khi chốt phương pháp lãi suất.*
