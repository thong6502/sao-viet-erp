# DATA CONTRACTS — Công thức & cấu trúc dữ liệu Tính giá (bản chốt trước khi code)

> **Vai trò:** Đây là bản đặc tả "**tính thế nào**", đi kèm bản "**khai cái gì**" là [DANH_MUC_TINH_GIA.md](./DANH_MUC_TINH_GIA.md).
> **Nguyên tắc:** mọi con số trên phiếu phải truy được về `số lượng × đơn giá`; đơn giá lấy từ danh mục (versioned), snapshot khi chốt.
> **Liên quan:** [THI_TRUONG_PHAN_MEM_IN.md](./THI_TRUONG_PHAN_MEM_IN.md) · [DOMAIN_NHA_MAY_IN.md](./DOMAIN_NHA_MAY_IN.md)

---

## 1. Quyết định đã chốt (decision log)

| # | Vấn đề | Quyết định |
|---|---|---|
| **D1** | Công in tính theo lần ép hay lượt màu | **Theo LƯỢT MÀU** — bỏ mô hình "số lần ép / số núm mực". Công in = `màu × mặt × tờ × đơn giá/lượt-màu`. |
| **D2** | Số kẽm | **Tính theo KIỂU BÌNH BÀI** (số bộ khuôn), không cứ ×số mặt. Xem §3. |
| **D3** | Sản phẩm nhiều cấu phần | **Có cấu trúc BOM đa cấu phần** (bìa/ruột/mặt+sóng…). Xem §4. |
| **D4** | Margin | Theo **lãi suất**: `Giá bán = Giá thành / (1 − lãi)`. (Ở màn Báo giá.) |

**Hệ quả của D1:** đơn giá công in trong danh mục Máy in phải được đặt **theo đúng quy ước lượt-màu** (giá cho 1 lượt-màu-tờ), không phải cho 1 lần chạy máy. Nhờ đó lượt in dùng `màu × mặt × tờ` — **trùng công thức mực**, hết mâu thuẫn nội bộ.

---

## 2. Công thức Giá thành (per TAY IN → cấu phần → sản phẩm)

Giá thành cộng dồn từ dưới lên: **Tay in → Cấu phần → Sản phẩm**.

```text
Cho mỗi TAY IN của một cấu phần:
  Số con/khổ   = tính từ (khổ tờ in − chừa nhíp − chừa xén) / (khổ trải + gutter)
                 → TÍNH tự động + CHO OVERRIDE (lưu cả giá trị tính và giá trị dùng)
  Số tờ tốt    = ceil( SL_cấu_phần / Số con/khổ )
  Số tờ in     = Số tờ tốt / ∏(tỷ lệ đạt gia công hạ nguồn)      (nếu có)
                 + makeready(máy, số màu)          ← số tờ canh máy, ∝ số màu
                 + running% × Số tờ tốt            ← hao chạy máy
                 (làm tròn ceil TỪNG tay in, trước khi cộng)

  Tiền giấy    = Số tờ in × đơn giá giấy(nguồn)     (xem §6 nguồn giấy)
  Số bộ khuôn  = theo kiểu bình bài                 (§3)
  Số kẽm       = số màu × Số bộ khuôn × Số tay in
  Tiền kẽm     = Số kẽm × đơn giá kẽm(khổ)
  Lượt màu     = số màu × số mặt × Số tờ in
  Tiền công in = Lượt màu × đơn giá công in         ← D1 (theo lượt màu)
  Tiền mực     = ceil(Lượt màu / 1000) × đơn giá mực/1000  (× hệ số độ phủ nếu bao bì)

Cho mỗi CÔNG ĐOẠN GIA CÔNG của cấu phần:
  Lượng gia công = theo đơn vị của công đoạn:
     - m²        → dùng KHỔ TRẢI × số sản phẩm            (KHÔNG dùng khổ thành phẩm)
     - nghìn cái → số sản phẩm / 1000
     - vị trí/tờ/mặt → theo cấu hình
  Tiền gia công  = Lượng × đơn giá(×(1+%bù hao nếu có))

Cho mỗi VẬT TƯ:
  Tiền vật tư = SL × đơn giá × (1 + %bù hao)

────────────────────────────────────────────
Giá thành cấu phần = Σ(giấy + kẽm + công in + mực) tất cả tay in
                   + Σ tiền gia công của cấu phần + Σ tiền vật tư
Giá thành sản phẩm = Σ giá thành các cấu phần
                   + Σ công đoạn RÁP/chung (dán, đóng gói, KCS…)
                   + phí cố định (thiết kế, làm mẫu, in thử, quản lý…)
Giá thành / đơn vị = Giá thành sản phẩm / SL đặt in
```

---

## 3. §D2 — Số kẽm theo kiểu bình bài

Bổ sung trường **`số bộ khuôn`** vào danh mục **Quy cách bình bài (⑰)**:

| Kiểu bình bài | Số bộ khuôn | Số lần tờ qua máy | Ghi chú |
|---|---|---|---|
| In 1 mặt | 1 | 1 | Chỉ in 1 mặt |
| **Tự trở** (work-and-turn) | **1** | **2** | 1 bộ kẽm mang cả 2 mặt; cắt đôi sau in → số con thực = con/khổ ÷ 2 |
| **Trở nhíp / sheetwise** | **2** | 1 (mỗi khuôn) | 2 bộ kẽm riêng cho 2 mặt |
| **A-B** (2 sản phẩm/tờ) | theo cấu hình | 1 | Khai riêng số bộ khuôn |

```text
Số kẽm = số màu × Số bộ khuôn × Số tay in
```

> Lưu ý tự trở: dùng chung kẽm (rẻ kẽm) nhưng **tờ qua máy 2 lần** → lượt màu vẫn = `màu × 2 mặt × tờ`, và **số con hữu ích chia đôi** (vì mỗi tờ ra 2 nửa giống nhau, cắt đôi). Engine phải xử lý đúng chỗ này khi tính Số con/khổ.

---

## 4. §D3 — Cấu trúc BOM đa cấu phần

**Đây là thực thể của PHIẾU tính giá, không phải danh mục.**

```text
BaiTinhGia (1 sản phẩm, SL đặt in)
 ├─ CauPhan (n)                         ← 1 sản phẩm có 1..n cấu phần
 │    • loại cấu phần        ← DM Loại thành phần
 │    • vật liệu             ← DM Giấy  HOẶC  DM Tấm/Sóng carton
 │    • khổ thành phẩm (ngang×dọc[×cao])
 │    • khổ trải (kèm tai dán/bleed)    ← dùng cho m² gia công & số con
 │    • SL cấu phần = SL sản phẩm × (số cái cấu phần / sản phẩm)
 │    ├─ TayIn (n)                       ← ghép bài: 1..n tay in / cấu phần
 │    │    • kiểu bình bài  ← DM ⑰ (→ số bộ khuôn)
 │    │    • số màu, số mặt ← DM Loại màu
 │    │    • giấy/khổ tờ in, máy in
 │    │    → (tính giấy + kẽm + công in + mực theo §2)
 │    └─ CongDoanGiaCong (n)  ← DM Công đoạn (cán/bồi/bế…)  [+ Khuôn bế nếu có]
 └─ CongDoanRap / Chung (n)             ← dán ráp, đóng gói, KCS (áp cho cả sản phẩm)
```

### Ví dụ: KHAY CARTON (theo ảnh NextPrint)
```text
Sản phẩm: KHAY CARTON — SL 15.850 cái
 └─ CauPhan #1 "Mặt khay"
      • vật liệu: Giấy Duplex 230, khổ tờ 39,5×54
      • TayIn #1: bình "in 1 mặt", số màu 1 (hoặc TIN-KHÔNG IN nếu không in)
      • Công đoạn:
          - BỒI SÓNG E  → thêm vật liệu Tấm/Sóng E (đơn vị m² theo khổ trải)
          - BẾ CẤN HỘP  → + Khuôn bế (chi phí khuôn 1 lần) + đơn giá bế/1000
          - DÁN HỘP / CỘT thành phẩm
 └─ (không có cấu phần #2 — khay 1 mảnh)
```
> Hàng **hộp bồi sóng** = 1 cấu phần nhưng **2 vật liệu** (mặt in + tấm sóng) + keo + công đoạn bồi. Tấm sóng khai ở **DM Tấm/Sóng** (sóng E/B/EB, định lượng lớp mặt+sóng), không nhét vào "họ giấy".

---

## 5. Bù hao — định nghĩa MỘT LẦN (chống đếm trùng)

Ba loại hao khác bản chất, **không được cộng lẫn**:

| Loại | Bản chất | Áp vào | Đơn vị |
|---|---|---|---|
| **Makeready** | Tờ hỏng lúc canh máy | Mỗi **tay in**, **∝ số màu** | số tờ (cố định) |
| **Running** | Hao trong lúc chạy máy | Mỗi tay in | % × số tờ tốt |
| **Tỷ lệ đạt (yield)** | Hụt ở **gia công hạ nguồn** (bế/cán hỏng) | Ngược chuỗi: cần in **nhiều hơn** để bù | `∏ tỷ lệ đạt` |

```text
Số tờ in = ceil( SL / Số con / ∏(tỷ lệ đạt) ) + makeready(tay×màu) + running% × số tờ tốt
```
> "Tỷ lệ đạt" là hao ở công đoạn SAU in → chia ở tử số (cần in dư). "Makeready/running" là hao TẠI máy in → cộng thêm. Tuyệt đối không lấy %hao gia công cộng vào hao chạy máy.

---

## 6. Nguồn giấy & quy đổi đơn vị

**Nhánh theo nguồn giấy (trường `nguồn` ở DM Giấy):**
| Nguồn | Giá dùng |
|---|---|
| **Mua mới** | Bảng giá danh mục (versioned) |
| **Kho** | Giá tồn (bình quân / theo lô) — KHÔNG lấy bảng giá |
| **Khách cấp** | **Chi phí giấy = 0** (chỉ tính hao + công) |

**Quy đổi kg ↔ tờ** (khi giấy bán theo kg):
```text
KL 1 tờ (kg) = (dài_m × rộng_m × gsm) / 1000
Đơn giá/tờ   = Đơn giá/kg × KL 1 tờ
```

---

## 7. Số con trên khổ — tính + override

- **Mặc định TÍNH** từ khổ trải + chừa nhíp/xén/gutter so với khổ tờ in (thử cả 2 chiều xoay).
- **Cho người dùng OVERRIDE**, lưu **cả giá trị tính và giá trị dùng**; nếu lệch → **cảnh báo** (không chặn).
- Với **tự trở**: số con hữu ích = con/khổ ÷ 2 (§3).

---

## 8. Thay đổi danh mục cần thêm (so với DANH_MUC_TINH_GIA.md)

| Danh mục | Thêm trường |
|---|---|
| ⑰ Quy cách bình bài | **số bộ khuôn**, số lần tờ qua máy |
| Giấy | công thức quy đổi kg↔tờ dùng gsm + khổ; nhánh giá theo `nguồn` |
| Máy in | đơn giá công in **theo lượt-màu** (ghi rõ quy ước D1) |
| (mới) **Khuôn bế/cấn** | chi phí khuôn 1 lần + đơn giá bế/1000 |
| (mới) **Tấm/Sóng carton** | loại sóng (E/B/EB), định lượng lớp mặt+sóng, đơn giá (m²/tờ) |
| Định mức & Bù hao | tách rõ makeready(tay×màu) / running% / tỷ lệ đạt |

---

## 9. Nghiệm thu trước khi code

1. **Chạy tay phiếu KHAY CARTON** (ảnh NextPrint) theo §2–§5 → đối chiếu số con, số tờ, tiền giấy, số kẽm, tiền công/mực, m² bồi/bế với phiếu gốc. Khớp mới code.
2. Chạy thêm **1 job đơn giản** (tờ rơi 1 cấu phần) để chắc luồng cơ bản đúng.
3. Chốt các con số norm thực của SVN (đơn giá, makeready, %hao, tỷ lệ đạt) — dữ liệu này SVN cấp.

---
*Tạo 2026-07-03. Chốt: D1 công in theo lượt màu · D2 kẽm theo bình bài · D3 BOM đa cấu phần · D4 margin theo lãi suất.*
