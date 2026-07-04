# Nghiệm thu công thức Tính giá — phiếu vàng ĐAI QUẤN THE FISSHER (NextPrint)

> **Vai trò:** Phiếu thật của NextPrint dùng làm **"đáp án chuẩn" (golden case)** để kiểm chứng engine tính giá SVN. Mọi thay đổi engine phải giữ phiếu này khớp.
> **Nguồn:** ảnh phiếu tính giá NextPrint (Trí Thành Software) — số phiếu QUO-049/07, ngày 03/07/2026.
> **Liên quan:** [DATA_CONTRACTS.md](./DATA_CONTRACTS.md) (công thức) · [DANH_MUC_TINH_GIA.md](./DANH_MUC_TINH_GIA.md) (danh mục).

---

## 1. Dữ liệu đầu vào

| Thông số | Giá trị |
|---|---|
| Ấn phẩm | ĐAI QUẤN THE FISSHER PRICE 470700-215.9×1003.3MM |
| SL đặt in | 20.000 cái |
| Khổ thành phẩm | ≈ 21,59 × 100,33 cm (215.9×1003.3 mm) |
| Khổ trải / khổ tờ in | 68 × 101,50 cm |
| Màu / mặt | 6 màu / 1 mặt |
| Giấy | Duplex D400, khổ 68×101,50 |
| Máy in | HEIDELBERG 72×102 - 7 màu |
| Kẽm | CTP ghi kẽm, khổ 79×103 |
| Gia công | CM-Waterbase UV bóng 1 mặt · TB-Bế cấn hộp (khuôn mới N-0728) · TP-Kiểm phẩm · TD-Cột thành phẩm |
| Bên A cấp | file + giấy phép (khách cấp) |

---

## 2. Nghiệm thu tay — đối chiếu từng số

| Bước | Công thức | Bấm tay | NextPrint | Khớp |
|---|---|---|---|---|
| Số con/khổ | floor(68/21,59) × floor(101,5/100,33) = 3×1 | **3** | 3 | ✅ |
| Số tờ tốt | ceil(20.000 / 3) | **6.667** | 6.666 *(giấy)* / 6.667 *(lượt)* | ⚠️ NextPrint tự lệch |
| Makeready | norm (SVN cấu hình) | 250 | 250 | ✅ |
| Tổng tờ | tờ tốt + makeready | 6.666+250 = 6.916 | 6.916 | ✅ |
| Tiền giấy | tổng tờ × đơn giá/tờ = 6.916 × 5.384 | **37.235.744** | 37.235.744 | ✅ |
| Số kẽm | màu × **số bộ khuôn** × tay = 6 × **1** × 1 | **6** | 6 | ✅ |
| Tiền kẽm | 6 × 100.000 | 600.000 | 600.000 | ✅ |
| Công in | đơn giá × màu × tờ (đơn giá = 0) | 0 | 0 | ✅ |
| Cán UV | 1.000/tờ × 6.666 | 6.666.000 | 6.666.000 | ✅ |
| Bế cấn | 250/tờ × 6.666 | 1.666.500 | 1.666.500 | ✅ |
| Tổng gia công | 6.666.000 + 1.666.500 | 8.332.500 | 8.332.500 | ✅ |
| **Tổng giá vốn** | giấy + kẽm + gia công = 37.235.744+600.000+8.332.500 | **46.168.244** | — | ✅ |
| Đơn giá gốc | 46.168.244 / 20.000 | 2.308,4 | **2.308** | ✅ |
| Đơn giá bán | HS lời = 1 → làm tròn lên bội 10 | 2.310 | **2.310** | ✅ |

**Kiểm tra chéo (bản PDF):** Giấy 1.861,79/cái + Công(kẽm+GC) 446,63/cái = 2.308/cái → ×20.000 = 46.200.000. ✅

---

## 3. Sáu quyết định đã chốt (2026-07-03)

| # | Quyết định | Ghi chú |
|---|---|---|
| **1** | **Số tờ luôn `ceil`**, nhất quán mọi chỗ (giấy = lượt = gia công) | Bỏ kiểu NextPrint chỗ 6.666 chỗ 6.667. **Giá trị chuẩn SVN = 6.667** (⇒ tổng tờ 6.917). |
| **2** | **Gia công tính trên số tờ TỐT, KHÔNG gồm makeready** | Tờ canh máy bỏ trước gia công. Hao riêng của gia công xử lý bằng **tỷ lệ đạt** (reverse chain). |
| **3** | **Makeready = norm SVN cấu hình** (tra theo màu/máy) | Phiếu này 250 tờ cho 6 màu. Engine mặc định chỉ là fallback. |
| **4** | **Kẽm tra giá theo KHỔ KẼM** (79×103), tách khổ giấy | `PlateDieRate` định giá theo khổ bản kẽm/máy CTP. |
| **5** | **Công in là dòng riêng, cho nhập 0** | Engine vẫn tính theo lượt-màu (D1); SVN nhập 0 thì ra 0. |
| **6** | **Làm tròn giá bán lên bội số 10** (cấu hình được) | 2.308 → 2.310. Quy tắc ở lớp Báo giá. |

> ⚠️ **Lưu ý giá trị chuẩn SVN ≠ NextPrint 1 tờ:** do quyết định #1 (ceil), SVN sẽ tính **6.917 tờ** (không phải 6.916). Chênh 1 tờ (~5.384đ) là **cố ý** (an toàn, không thiếu hàng). Golden test SVN assert **6.917**, không phải 6.916.

---

## 4. Quan hệ Đơn hàng ↔ Tính giá (từ phiếu này)

- Trên NextPrint, đơn giá dòng **Danh sách ấn phẩm** (872) là **ô gõ tay tự do**, **KHÔNG đồng bộ** từ bài tính giá (2.308/2.310). Phần mềm nhận cả giá **dưới giá vốn** mà **không cảnh báo**.
- **Quyết định SVN (tốt hơn NextPrint):**
  1. Đơn giá dòng đơn hàng **mặc định lấy từ báo giá/tính giá**, vẫn **cho sửa tay**.
  2. Giá gõ tay **< giá vốn → cảnh báo "bán dưới giá vốn"** (không chặn, ghi audit).
  3. **Snapshot copy-on-write khi chốt** — khóa cả giá vốn lẫn giá bán.

---

## 5. Điều phiếu này XÁC NHẬN cho thiết kế

- ✅ **D2 (kẽm theo bình bài):** "in 1 mặt" → số bộ khuôn = 1 → kẽm = màu×1×tay. *(Ca này trùng công thức cũ vì 1 mặt; khác biệt D2 chỉ lộ ở tự trở.)*
- ✅ **D1 (công in theo lượt-màu):** NextPrint để cột "số lượt" = số tờ, **số màu là thừa số riêng** → công in ∝ màu × tờ. *(Ca này đơn giá = 0 nên không kiểm được rate bằng số.)*
- ✅ **Tiền giấy dùng TỔNG tờ** (gồm makeready).
- ✅ **Gia công theo TỜ**, trên số tờ tốt.

## 6. Điểm phiếu này CHƯA phủ (cần golden case thứ 2)

- Job **tự trở** (để kiểm D2: số bộ khuôn = 1 dù 2 mặt).
- Công in **đơn giá ≠ 0** (để kiểm rate D1 bằng số).
- Sản phẩm **nhiều cấu phần** (bìa+ruột — D3 BOM).
- Giấy tính theo **kg** với nguồn "mua mới" (ca này giấy quy từ kg: 5.384đ/tờ ≈ 19.500đ/kg × 0,276 kg/tờ — khớp, nhưng chưa test tự động).

---
*Tạo 2026-07-03. Golden case #1. Test tự động: `backend/tests/test_pricing_golden_khay_carton.py`.*
