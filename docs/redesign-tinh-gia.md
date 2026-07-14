# REDESIGN — Tính giá (engine công thức, giá vốn theo sản lượng)

> Làm lại từ đầu module Tính giá. Bản này **thay thế** thiết kế cũ (engine cứng 4 rổ).
> Nguồn gốc: phiếu tính giá tay thật của xưởng (hộp đôi ITALY + rộ bông, 4.000 thành phẩm).
> Đơn vị đếm sản phẩm gọi là **"thành phẩm"** (không dùng tiếng lóng "con").

---

## 0. Một dòng

Engine = **máy thế-số-vào-công-thức**. Mỗi giấy / công đoạn / vật tư có **1 công thức** viết
bằng **biến hệ thống**; lúc tính, engine thế số thật vào → ra **tiền tổng** → ÷ số lượng =
**đ/thành phẩm**; cộng dọc = **giá vốn**.

---

## 1. Nguyên tắc bất biến

1. **Chỉ ra giá vốn** — markup/VAT là việc của Báo giá.
2. **Engine không có luật ẩn** — mọi khác biệt cách tính đều nằm trong *công thức + biến*,
   không phán đoán trong code.
3. Tư duy theo **đ/thành phẩm**; tổng = đ/thành phẩm × số lượng.
4. **Auto + override**: ô danh mục tự điền, sửa đè được; ô thuần tính-ra thì khóa.
5. **Một engine duy nhất** — bỏ `pricing_engine.py`, model costing, và `tinh_gia_engine.py` cũ.

---

## 2. Biến hệ thống (hợp đồng — dùng trong công thức)

| Biến | Nhãn | Nguồn | ĐVT |
|---|---|---|---|
| `dai_tp` `rong_tp` | dài/rộng khổ thành phẩm | nhập | m |
| `dai_nguyen` `rong_nguyen` | dài/rộng khổ giấy nguyên | nhập | m |
| `dai_in` `rong_in` | dài/rộng khổ giấy in | nhập | m |
| `so_luong` | số lượng (thành phẩm) | nhập | thành phẩm |
| `so_tp` | số thành phẩm/tờ | nhập | — |
| `to_dau_vao` | **số tờ đầu vào máy in** | hệ thống | tờ |
| `to_sau_in` | **số tờ còn lại sau in** | hệ thống | tờ |
| *(field của item)* | vd `dinh_luong`, `don_gia` | danh mục | kg/m², đ/… |

> Khổ nhập bằng **cm**, biến đưa vào công thức quy về **m** (để `× đ/m²`, `× đ/kg` ra thẳng).

---

## 3. Hai số tờ (trái tim)

```
to_dau_vao  = ⌈so_luong / so_tp⌉ + Σ(bù hao mỗi công đoạn) + số bù nhập tay   → nuôi GIẤY + IN
to_sau_in   = to_dau_vao − số hao nhập tay                                     → nuôi CÔNG ĐOẠN SAU IN
```

Người viết công thức tự chọn nhân với `to_dau_vao` hay `to_sau_in` → tự quyết chi phí thuộc
trước/sau in. **Engine không cần cờ "trước/sau in"** (nếu thêm cờ đó thì thừa và đá nhau với
công thức — 2 nguồn sự thật).

---

## 4. Công thức & bộ tính

- **Toán tử:** `+ − × ÷ ( )` + hàm `ceil, floor, round, max, min`.
- **Token:** biến hệ thống (§2) + field của item; giá trị field **hiển thị ngay trong công thức**,
  vd `định_lượng(0,25)`, `đơn_giá_kg(17.100)`. Đổi giá ở danh mục → công thức tự đổi (sửa 1 chỗ).
- **An toàn:** bộ tính riêng (parse + whitelist token), **không** dùng `eval` của Python.
- Công thức lỗi / thiếu biến → dòng đó **0đ + cảnh báo**, không được crash.

---

## 5. Bù hao — tái dùng module có sẵn

- Quy tắc bù hao = **bậc theo số lượng** → giá trị (**tờ** | **%**); hoặc **cộng cố định (tờ)**.
- Công đoạn nối quy tắc qua `kieu_bu_hao`; `bu_hao_engine` dò bậc theo `so_luong`.
  Không nối → dùng `so_to_bu_hao` (cộng cố định).
- Đơn vị `%` **nhân thẳng với `so_luong`** → ra số tờ bù (vd `1,5% × 40.000 = 600 tờ`),
  cộng **thẳng** vào `to_dau_vao`, KHÔNG chia `so_tp`.
- Σ bù hao các công đoạn → cộng vào `to_dau_vao`.

---

## 6. Nhập liệu (form phiếu)

Nhãn tầng: **[Nhập]** KTV gõ · **[Auto]** tự điền từ danh mục, sửa đè được · **[Hiện]** tự tính, khóa.

| Field | Tầng | Nguồn / ghi chú |
|---|---|---|
| Tên thành phẩm · khổ thành phẩm (D×R) · số lượng | [Nhập] | — |
| Loại sản phẩm | [Nhập] | → auto bung danh sách công đoạn mặc định |
| Máy in | [Nhập] | → auto khổ máy |
| Nguồn giấy: **Công ty** \| **Khách cấp** | [Nhập] | Khách cấp → **bỏ tiền giấy** |
| Loại giấy (nếu Công ty) | [Nhập] | → công thức + field giấy (định lượng, đơn giá/kg) |
| Khổ giấy nguyên (D×R) · khổ giấy in (D×R) | [Nhập] | cảnh báo nếu khổ in > khổ máy |
| Số thành phẩm/tờ (`so_tp`) | [Nhập] | cảnh báo bình bài (so với số thành phẩm/tờ hình học) |
| Số bù (vào `to_dau_vao`) · số hao (ra `to_sau_in`) | [Nhập] | mặc định 0 |
| Danh sách công đoạn (thêm/xóa) | [Auto] | routing Loại SP; mỗi công đoạn có công thức + bù hao |
| Vật tư thêm | [Nhập] | danh mục vật tư in ấn; mỗi vật tư có công thức |
| **số tờ đầu vào / sau in · số thành phẩm/tờ (hình học) · đ/thành phẩm từng dòng · tổng** | [Hiện] | tính-ra, khóa |

**Số thành phẩm/tờ (hình học)** — số thành phẩm tối đa nhét vừa 1 tờ in, tự tính có xoay bài:
```
= max( ⌊dai_in/dai_tp⌋×⌊rong_in/rong_tp⌋ , ⌊dai_in/rong_tp⌋×⌊rong_in/dai_tp⌋ )
```
Chỉ để **đối chiếu cảnh báo**: nếu `so_tp` (nhập tay) > số hình học → cảnh báo "bình bài không vừa".
Tiền vẫn tính theo `so_tp` KTV gõ.

---

## 7. Danh mục phải thêm "ô công thức"

- **Giấy** (Material paper): `cong_thuc_gia` + field định lượng, đơn giá/kg.
- **Công đoạn** (Operation): `cong_thuc_gia` (bù hao đã có).
- **Vật tư in ấn** (Material): `cong_thuc_gia`.
- **Loại SP**: danh sách công đoạn mặc định (đã có routing → tái dùng, không dựng lại).

---

## 8. Ra tiền & hiển thị (3 lớp mỗi dòng)

Mỗi dòng hiện **đ/thành phẩm** + tổng + công thức đã thế số:
```
Cán màng bóng    285 đ/thành phẩm   (tổng 1.140.048đ)
  = dài_in(0,435) × rộng_in(0,64) × đơn_giá_m²(1.950) × tờ_sau_in(2.100)
```
`đ/thành phẩm = tổng dòng ÷ so_luong`. Bảng phẳng theo thứ tự phiếu tay (giấy → in → công đoạn →
vật tư) + dòng **TỔNG (giá vốn) đ/thành phẩm**. Không markup ở màn này.

---

## 9. Cảnh báo (không chặn)

- Khổ in > khổ máy.
- `so_tp` > số thành phẩm/tờ hình học (bình bài không vừa).
- Công thức lỗi / thiếu biến → dòng 0đ.
- Giấy khách cấp → bỏ tiền giấy.

---

## 10. Ghép nhiều mã

Coi là **1 sản phẩm trên 1 tờ**: nhập `so_luong` tổng + `so_tp` tổng. Không chia chi phí riêng
theo mã.

---

## 11. Snapshot (khi Báo giá chốt)

Freeze: input + công thức + giá trị mọi biến + version danh mục → sau này truy được **tại sao ra
số đó**, dù đơn giá danh mục đã đổi.

---

## 12. Làm tròn

Số thành phẩm/tờ **floor** · số tờ **ceil** · % bù hao **ceil** · tiền mỗi dòng **round** ·
đ/thành phẩm **round**.

---

## 13. Golden test neo (phiếu hộp đôi thật)

```
SL 4.000 · số thành phẩm/tờ 2 · khổ in 0,435×0,64 · khổ nguyên 0,445×0,64
giấy D250 (đl 0,25 kg/m², 17.100 đ/kg) · bù 250 (đầu vào) · hao 150 (sau in)

to_dau_vao = 4000/2 + 250 = 2.250
to_sau_in  = 2.250 − 150 = 2.100
Giấy     = 0,25×0,445×0,64×17.100×2.250 = 2.739.375 → 685 đ/thành phẩm   ✓
Cán màng = 0,435×0,64×1.950×2.100       = 1.140.048 → 285 đ/thành phẩm   ✓
```
(Các dòng còn lại neo tiếp khi cấu hình đủ công thức; đích cuối = **3.001 đ/thành phẩm**.)

---

## 14. Dọn kiến trúc & lộ trình

Bỏ `pricing_engine.py` + model costing + `tinh_gia_engine.py` → **1 engine công thức**.
Viết lại golden trên engine mới. **Báo giá tạm vẫn ăn `Estimate` cũ** — rewire Tính giá → Báo giá
là việc riêng, làm sau.

Ràng buộc repo (CLAUDE.md): không Alembic → đổi cột viết vào `backend/app/db_migrations.py`;
cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test); Boolean `server_default` = `true`/`false`.

---

## 15. Ngoài phạm vi (defer)

Rewire sang Báo giá · in theo giờ máy · web/cuộn · sách nhiều tay (BOM động) · mực theo độ phủ.

---

## 16. Đã chốt (trước còn treo)

- Định lượng **lưu thẳng kg/m²** (0,25) — biến `dinh_luong` dùng luôn, không quy đổi.
- `%` bù hao **nhân với `so_luong`** → ra số tờ, cộng thẳng vào `to_dau_vao` (không chia `so_tp`).

---
*Tạo lại 2026-07-14. Nguồn: phiếu tính giá tay thật (hộp đôi ITALY + rộ bông). Đơn vị đếm =
"thành phẩm". CHƯA code.*
