# REDESIGN — Module Tính giá (giá vốn theo sản lượng)

> Làm lại UI/UX + logic module Tính giá (`PhieuTinhGia`, component-based, engine
> `tinh_gia_engine` / `thanh_phan_engine`). Công cụ nội bộ KTV ra **giá vốn** — KHÔNG
> markup/VAT/giá bán (việc của Báo giá; luật đã khóa trong `PLAN_UI_TINH_GIA_BAO_GIA.md`).
> Bản này là bản ĐƠN GIẢN, khác `spec-tinh-gia.md` (engine đầy đủ). Anh em: `spec-cong-doan.md`,
> `spec-may-thiet-bi.md`, `spec-san-pham.md`.

---

## 1. Mục tiêu & nguyên tắc bất biến

1. **Theo sản lượng** — mọi khoản = đơn giá × sản lượng đo được (tờ / bản / lượt / basis).
   BỎ tính theo giờ máy (BHR).
2. **Không hệ số** — mọi "hệ số khoán / quy đổi" trong tính giá vốn đều = 1 → gỡ hẳn khỏi
   model lẫn UI.
3. **Auto + override** — mọi ô tự điền từ danh mục (smart default), KTV luôn sửa đè được;
   chỉ số thuần-tính-ra là read-only.
4. **Khởi đầu từ Loại sản phẩm** — chọn nó trước, tự bung khung phiếu.
5. Giá vốn thôi; **làm tròn 1 lần ở cuối**.

---

## 2. Bốn khổ & hai mức tờ (nền tảng logic — không được lẫn)

```
① GIẤY NGUYÊN (mua)  ──xả cho vừa Máy──►  ② TỜ IN (chạy máy)  ──bình bài──►  ③ THÀNH PHẨM × ④ con/tờ
```

| Khổ | Nghĩa | Nguồn |
|---|---|---|
| ① Khổ giấy nguyên | tờ giấy MUA về từ NCC | danh mục Giấy `giay_nguyen.kho_dai/kho_rong` |
| ② Khổ tờ in | tờ ĐƯA VÀO MÁY, vừa `may.kho_max` | xả từ ① cho vừa Máy; = ① nếu không cắt |
| ③ Khổ thành phẩm | sản phẩm CUỐI khách nhận | KTV nhập |
| ④ con/tờ | số thành phẩm trên 1 tờ in | tự bình bài ③ lên ② |

**Hai phép chia:**
- **Xả giấy** (① → ②): `tờ_in / tờ_nguyên` — cần khổ Máy để biết cắt mấy mảnh.
- **Bình bài** (② → ④): `con / tờ_in` — công thức hình học, trên khổ ② trừ 5 chừa.

**Mỗi chi phí ăn khổ khác nhau (mấu chốt "2 mức tờ"):**
- Giấy (tiền mua) → theo **① tờ nguyên** (đúng cả khi giấy bán theo kg lẫn theo tờ/ram).
- Công in / số lượt → theo **② tờ in**.

Bình bài chết: module `imposition_rule` đã bị xóa (chỉ còn `.pyc` mồ côi); `LoaiSanPham.imposition_rule_id`
trỏ vào khoảng không. Bản này KHÔNG dùng nó — port công thức hình học từ `pricing_engine.py` (đã có).

---

## 3. Luồng nhập (ít thao tác, rule-based)

```
Chọn LOẠI SP  → bung: số thành phần (structural_type) + routing công đoạn ĐẦY ĐỦ + gợi ý giấy (default_stock_class)
Chọn MÁY      → khổ in ② + gripper + 5 chừa mặc định + khoa_class (giá kẽm)
Chọn GIẤY     → khổ nguyên ① + đơn giá (kg | tờ)
KTV nhập:     Số lượng · Khổ thành phẩm ③ · Số màu (mặt A / mặt B)
→ TỰ bình bài ra ④ con/tờ → TỰ ra số tờ → bấm Tính → bảng 4 nhóm giá vốn
```

Mọi ô "auto" đều sửa đè được; ô đã lệch khỏi giá trị auto có dấu hiệu + nút "về mặc định".

---

## 4. Engine — sản lượng & công thức (giá vốn 4 nhóm)

Nhóm phiếu: **A Giấy · B Công in · C Chế bản (kẽm) · D Gia công sau in.**

```
usable_w = khổ_in②_rộng − (xén + tay kê + nhíp + đuôi + cà gáy)
usable_h = khổ_in②_dài  − (xén + tay kê + nhíp + đuôi + cà gáy)
con/tờ ④  = max( (usable_w // w_tp)×(usable_h // h_tp) , (usable_w // h_tp)×(usable_h // w_tp) )
             (w_tp/h_tp = khổ thành phẩm ③; max = tự chọn hướng đặt tốt hơn)   ← port pricing_engine

tờ in NET   = ceil(SL / con/tờ)
tờ in GROSS = NET + bù hao (canh máy + % chạy, từ danh mục Bù hao)         ← KHÔNG hệ số
tờ nguyên   = ceil(GROSS / số mảnh xả)        (ẩn khỏi UI; chỉ để tính tiền giấy)

A Giấy    = tờ nguyên → quy đổi (kg | tờ) × đơn giá        [theo don_vi_gia của giấy]
C Kẽm     = (màu A + màu B) × số tờ-mẫu × đơn giá kẽm(khoa_class)
B Công in = (tờ GROSS × số mặt) lượt × đơn giá/1000 lượt   [MỰC GỘP trong đơn giá công in]
D Gia công= Σ công đoạn: đơn giá × basis_qty (tờ | ram | m² | con | lượt…)

GIÁ VỐN = A + B + C + D          gia_von_don = GIÁ VỐN / SL
```

- **Số lượt đếm mặt, KHÔNG nhân số màu** (máy nhiều màu in 1 lượt hết màu; số màu chỉ đẻ ra kẽm).
- Quy cách: 1 mặt → passes 1; 2 mặt / tự trở → passes 2.
- Ngoài phạm vi: nhánh web (tem cuộn), đóng cuốn nhiều tay / assembly, in theo giờ máy.

---

## 5. Bộ field (3 tầng)

Nhãn: `[Nhập]` = KTV gõ gốc · `[Auto]` = tự điền từ danh mục, SỬA ĐÈ được · `[Hiện]` = tự tính, read-only.

### Thành phần (khung)
| Field | Tầng | Nguồn |
|---|---|---|
| Loại thành phần (tờ rời / ruột / bìa…) | [Auto] | `structural_type` Loại SP |
| Tên thành phần | [Auto] | tên Loại SP |
| Khổ thành phẩm ③ (+ mở rộng) | [Nhập] | — (ô gốc quan trọng nhất) |
| Tay gấp 1&2 | [Auto] | ẩn nếu loại không gấp |
| Số tờ / sản phẩm | [Auto] | mặc định 1, ẩn với tờ rời |

### Giấy in
| Field | Tầng | Nguồn |
|---|---|---|
| Loại giấy & định lượng | [Auto] | gợi ý theo `default_stock_class` |
| Khổ giấy nguyên ① | [Auto] | tự điền khi chọn giấy |
| Đơn giá giấy (kg / tờ) | [Auto] | theo `don_vi_gia` giấy |
| Nguồn giấy (Công ty / Khách) | [Auto] | mặc định Công ty |
| Bù hao (số tờ cộng thêm) | [Auto] | danh mục Bù hao (theo màu/con/SL) |
| 5 chừa: xén · tay kê · nhíp · đuôi · cà gáy | [Auto] | theo Máy, sửa được |

> ẩn khỏi UI: số tờ nguyên, kg giấy (vẫn tính ngầm để ra tiền giấy).

### Kỹ thuật in
| Field | Tầng | Nguồn |
|---|---|---|
| Có in không? | [Nhập] | mặc định có |
| Khách cung cấp (File / Thiết kế) | [Auto] | — |
| Chế bản (loại + đơn giá) | [Auto] | routing + đơn giá danh mục |
| Quy cách in (1 mặt / 2 mặt / tự trở) | [Nhập] | — |
| Khổ in ② | [Auto] | xả từ ① cho vừa Máy |
| Số con ④ | [Auto] | tự bình bài (③ lên ② trừ chừa) |
| Máy in | [Auto] | gợi ý theo khổ; ra khổ in + gripper + khoa_class |
| Tráng phủ / Sấy | [Auto] | — |
| Đơn giá công in | [Auto] | danh mục Công đoạn (nhóm print), mực gộp |
| tờ in net / gross · số lượt | [Hiện] | tự tính |

### Màu in (đã gộp — không SEL/Pan/Nền, không hệ số)
| Field | Tầng |
|---|---|
| Số màu mặt A / số màu mặt B | [Nhập] |
| Số kẽm = (màu A + màu B) × số tờ-mẫu | [Hiện] |

### Gia công sau in (nhiều dòng)
| Field | Tầng |
|---|---|
| Công đoạn (chọn) | [Auto] từ routing Loại SP |
| Đơn giá / SL / diện tích / số mặt | [Auto] danh mục, sửa được |
| Nhà cung cấp (thuê ngoài) | [Nhập] tùy chọn |
| Thành tiền dòng | [Hiện] |

---

## 6. Thay đổi schema

**Gỡ cột** (hệ số / trung gian không dùng — tính giá vốn không có hệ số):
`he_so_sel`, `he_so_pan`, `he_so_nen`, `che_ban_he_so`, `he_so_cong_in`, `bu_hao_he_so`, `loi_nhuan`.

Ràng buộc repo (`CLAUDE.md`):
- KHÔNG Alembic → thay đổi cột phải viết vào `backend/app/db_migrations.py`; dev drop `dev.db`.
- Guard test `docs/DB_SCHEMA.md`: cập nhật cùng lúc khi đổi model, nếu không `./init.ps1` FAIL.
- Boolean `server_default` = `true`/`false` (Python bool), không `"0"/"1"`.

---

## 7. UI/UX

- **List** (`PhieuTinhGiaListView`): giữ — đã bám `RebuildCatalogPage`.
- **Detail**: THIẾT KẾ LẠI TỪ ĐẦU sau khi xem hiện trạng bằng `dev-browser`. Form cũ chỉ là nguồn
  field/dữ liệu, KHÔNG phải mẫu thẩm mỹ — không mô phỏng layout cũ.
  - Nguyên tắc: 2 vùng (form thành phần ↔ tổng giá vốn), phân cấp thông tin rõ, mật độ vừa.
  - Icon: **SVG line-icon** theo codebase (`SearchIcon`/`EmptyIcon`), `stroke=currentColor`.
    TUYỆT ĐỐI KHÔNG emoji.
  - Hiện `[Hiện]` (số con / tờ / lượt / kẽm / thành tiền) ngay cạnh ô liên quan để KTV soi số.
  - Ẩn field theo ngữ cảnh loại thành phần (tờ rời ẩn tay gấp / số tờ-sp).
  - Ô đã sửa-đè: dấu hiệu + nút "về mặc định".
  - Panel tổng "TỔNG GIÁ VỐN" + subtotal 4 nhóm.
- Bắt buộc: `styleseed-design-review` + `dev-browser` (screenshot thật) xác nhận TRƯỚC KHI báo xong.

---

## 8. Ngoài phạm vi (defer)

- Nhánh web (tem cuộn), đóng cuốn nhiều tay / assembly, in theo giờ máy.
- Nối lại module `imposition_rule` (đã xóa).
- Nối Tính giá → Báo giá: Báo giá vẫn ăn `Estimate` cũ (FK `estimate_id`). `PhieuTinhGia` hiện là
  công cụ giá vốn ĐỘC LẬP — quyết định rewire là việc riêng, sau.

---

## 9. Quy trình build & bàn giao

1. `dev-browser`: mở app, chụp UI Tính giá hiện tại (xem hiện trạng, không để anchor thẩm mỹ).
2. Backend: build engine (§4) + schema (§6); verify `./init.ps1` (pytest + compileall), dán kết quả thật.
3. UI/UX: có thể giao 1 agent build, kèm brief ngữ cảnh đầy đủ:
   - doc này + hợp đồng API engine (input/output) + field 3 tầng (§5)
   - pattern repo: `RebuildCatalogPage`, inline SVG icon, panel tổng giá vốn
   - ràng buộc: không emoji, chạy `styleseed-design-review`.
4. Verify: `styleseed` + `dev-browser` (screenshot) → mới báo xong.
