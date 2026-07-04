# Kế hoạch giá thành ngành in — lộ trình cho SVN

> **Vai trò:** Biến mô hình giá thành đầy đủ ngành in (BOM động + Routing + Overhead) thành lộ trình cụ thể cho SVN: mỗi nhóm dữ liệu ghi rõ *đã có gì / thiếu gì / làm trước-sau*.
> **Nguyên tắc:** KHÔNG rewrite. Engine hiện tại đã phủ ~70% mô hình; chỉ **mọc thêm** phần thiếu. Mọi thứ quy về 3 khối **BOM (vật tư) + Routing (công đoạn) + Overhead (chi phí chung)** — không công thức đặc biệt.
> **Liên quan:** [DANH_MUC_TINH_GIA.md](./DANH_MUC_TINH_GIA.md) · [DATA_CONTRACTS.md](./DATA_CONTRACTS.md) · [NGHIEM_THU_KHAY_CARTON.md](./NGHIEM_THU_KHAY_CARTON.md)

---

## 1. Đối chiếu nhóm dữ liệu → SVN

| # | Nhóm dữ liệu | SVN đã có | Thiếu | Ưu tiên |
|---|---|---|---|---|
| 1 | Thông tin sản phẩm in | `product_type_catalog` + input phiếu | Quy cách đóng gói, mức chất lượng | P1 |
| 2 | Định mức NVL (giấy/mực/kẽm/màng/keo/phụ) | `Material`+`MaterialCost` (ram/tờ/kg/m², gsm, quy đổi) | — | ✅ đủ |
| 3 | Khổ giấy / khổ máy / bình bài | Máy `max_w/h` + engine tính số con (hình học: lề nhíp/xén/bleed/gutter, xoay) | Danh mục khổ giấy chuẩn; 4 kiểu bình bài (số bộ khuôn) | P1 |
| 4 | Routing (trước in / in / sau in) | `Operation`+`OperationRate` (nhập tay theo phiếu) | **Routing template** tự áp theo loại SP | P2 |
| 5 | Máy móc + năng suất | `Machine`+`MachineRate` (tốc độ, setup, giờ máy) | Số nhân công/máy, công suất theo ca | P2 |
| 6 | Nhân công trực tiếp | `OperationRate.labor_rate` | Lương khoán theo **Tổ & Đầu việc** | P2 |
| 7 | Hao hụt & bù hao | `Norm` (makeready, running, waste, yield) | — | ✅ đủ |
| 8 | **BOM động** | Engine tính vật tư *cứng*, 1 vật liệu/phiếu | **Khai BOM theo quy cách + đa cấu phần** | 🔴 **Trụ mới #1** |
| 9 | Bảng giá vật tư + NCC | `MaterialCost` versioned theo thời điểm | NCC, MOQ, lead time, VAT, vận chuyển vào giá vốn | P1 |
| 10 | Thuê ngoài | `execution_mode=outsourced` (nhập tay) | Bảng giá gia công ngoài + NCC | P2 |
| 11 | Chi phí chung (điện, khấu hao, quản lý…) | — | **Gộp vào đơn giá sẵn có** (giờ máy/gia công) — KHÔNG tách dòng | ⚪ không xây |
| 12 | Công thức tổng giá thành | Engine cộng dồn `cost_lines` | — | ✅ đủ |
| 13 | Luồng tính giá | `EstimateService` (nhập → số con → vật tư → công đoạn → hao hụt → ra giá) | Chèn bước BOM (khi làm đa cấu phần) | — |
| 14 | Checklist khai báo | — | dùng làm phụ lục | tham chiếu |

> **Chi phí chung (overhead) — quyết định BỎ tách dòng riêng.** Cho user **tự cộng điện/khấu hao/quản lý vào đơn giá sẵn có** (đơn giá giờ máy đã gồm điện+khấu hao; đơn giá gia công đã gồm quản lý). Lý do: (1) engine **đã ra giá đúng mà không cần overhead** — golden KHAY CARTON chứng minh; (2) nếu user đã cộng vào đơn giá rồi mà mình thêm dòng overhead riêng → **tính trùng, đội giá sai**. Cái giá: không xem tách bạch được "trong giá này điện/khấu hao bao nhiêu" — chấp nhận để gọn (xưởng vừa & nhỏ hầu hết làm kiểu gộp).

> **MVP (bộ tối thiểu để bấm ra 1 báo giá):** Sản phẩm · Vật tư · Đơn giá · Máy · Công đoạn · Định mức · Báo giá — **SVN đã có đủ**. Job thường (1 loại giấy) **dùng luôn engine hiện tại, không cần thêm gì**.

---

## 2. Trụ mới duy nhất — BOM động

Biến vật tư từ "cứng trong code" → "khai báo được theo quy cách".

- `BomTemplate` theo **loại sản phẩm** → nhiều `BomLine`; mỗi dòng = {vật tư · đơn vị · **công thức lượng** theo quy cách (số trang, khổ, số con, diện tích) · %bù hao}.
- **Đa cấu phần** (bìa Couche + ruột Ford): 1 sản phẩm → n cấu phần → mỗi cấu phần có vật liệu + tay in riêng rồi cộng lại (chính là gap #7 đang hoãn).
- Engine đọc BOM thay vì `material_id` đơn.

> **Chỉ cần khi làm sản phẩm nhiều cấu phần** (sách, hộp bồi sóng…). **Job thường 1 loại giấy → engine hiện tại đã đủ**, không cần BOM động. → Không phải làm ngay.

### Spec chốt (P0 — chưa code)

```
PHIẾU (1 sản phẩm, SL đặt)
 ├─ Cấu phần 1  → 1 giấy + khổ + màu/mặt  → chạy engine hiện tại (giấy/kẽm/mực/công) + gia công riêng
 ├─ Cấu phần 2  → (tương tự)
 └─ Công đoạn RÁP CHUNG (vào bìa, đóng gáy, đóng gói) — cấp sản phẩm
Giá thành = Σ cấu phần + Σ ráp chung
```

**Hai quyết định đã chốt (2026-07-03):**
1. **Khai cấu phần NGAY TRÊN PHIẾU** (user bấm "thêm cấu phần") — **KHÔNG làm mẫu sẵn** theo loại sản phẩm (để sau nếu cần).
2. **Mỗi cấu phần = 1 tay in** (1 loại giấy). **KHÔNG chia nhiều tay in** — sách nhiều tay để phase sau.

**Hệ quả:**
- **Job thường = 1 cấu phần** → chạy y hệt engine hiện tại, không đổi gì.
- **Đa cấu phần = thêm cấu phần 2, 3…** → mỗi cái chạy lại engine cũ rồi cộng.
- Việc code thật sự chỉ gồm: (a) cho phiếu chứa **danh sách cấu phần**; (b) **lặp engine** qua từng cấu phần; (c) thêm mục **công đoạn ráp chung**. **Không có công thức mới.**

*(Overhead / phân bổ chi phí chung: đã BỎ — xem ghi chú §11 mục 1. Cho gộp vào đơn giá sẵn, không tách dòng.)*

---

## 3. Lộ trình (thứ tự làm)

| Phase | Làm gì | Vì sao |
|---|---|---|
| **Hiện tại** | Job thường (1 loại giấy) — **dùng luôn engine đang chạy** | Đã đủ, golden test xanh |
| **Khi cần** | BOM động 1 cấu phần (khai công thức lượng vật tư) | Nền cho đa cấu phần |
| **Sau đó** | Đa cấu phần (bìa + ruột) + routing template | Việc lớn nhất, chỉ làm khi có job thật cần |
| **Bổ sung** | NCC / MOQ / VAT / vận chuyển vào giá vốn (§9); gia công ngoài (§10) | Khi phát sinh nhu cầu |

---

## 4. Ranh giới — KHÔNG làm (tránh phình)

- Không cho user gõ công thức tự do (giữ cấu hình tham số + template).
- Không rewrite engine đang chạy.
- Kế toán / bút toán → vẫn đẩy MISA, không tự dựng sổ cái.

---
*Tạo 2026-07-03. Overhead đã bỏ (gộp vào đơn giá). Trụ mới duy nhất = BOM động, chỉ làm khi có sản phẩm đa cấu phần. Job thường dùng engine hiện tại. Chưa code.*
