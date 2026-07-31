# REDESIGN — Tính giá (engine công thức, giá vốn theo sản lượng)

> Làm lại từ đầu module Tính giá. Bản này **thay thế** thiết kế cũ (engine cứng 4 rổ).
> Nguồn gốc: phiếu tính giá tay thật của xưởng (hộp đôi ITALY + rộ bông, 4.000 thành phẩm).
> Đơn vị đếm sản phẩm gọi là **"thành phẩm"** (không dùng tiếng lóng "con").

---

## 0. Một dòng

Engine = **máy thế-số-vào-công-thức**. **Giá vốn = Σ dòng NVL (vật tư — gồm giấy) + Σ dòng công
đoạn.** Mỗi dòng có **1 công thức** viết bằng **biến hệ thống**; engine thế số thật vào → **tổng
dòng** → ÷ số lượng = **đ/thành phẩm**; cộng dọc = giá vốn.

**Quy cách in** (mẫu in · cách in · màu in · số kẽm) là khối **mô tả cho sản xuất — KHÔNG phải rổ
chi phí**, nhưng **phơi vài biến** (số màu / mặt / kẽm) cho công thức dùng.

---

## 1. Nguyên tắc bất biến

1. **Chỉ ra giá vốn** — markup/VAT là việc của Báo giá.
2. **Engine không có luật ẩn** — mọi khác biệt cách tính đều nằm trong *công thức + biến*,
   không phán đoán trong code.
3. Tư duy theo **đ/thành phẩm**; tổng = đ/thành phẩm × số lượng.
4. **Auto + override**: ô danh mục tự điền, sửa đè được; ô thuần tính-ra thì khóa.
5. **Một engine duy nhất** — bỏ `pricing_engine.py`, model costing, và `tinh_gia_engine.py` cũ.
6. **Chi phí chỉ 2 loại dòng: NVL + Công đoạn** (giấy = NVL). Không còn "rổ A/B/C/D". Quy cách in
   KHÔNG phải rổ chi phí — chỉ mô tả + phơi biến.

---

## 2. Biến hệ thống (hợp đồng — dùng trong công thức)

| Biến | Nhãn | Nguồn | ĐVT |
|---|---|---|---|
| `dai_tp` `rong_tp` | dài/rộng khổ thành phẩm | nhập | m |
| `dai_nguyen` `rong_nguyen` | dài/rộng khổ giấy nguyên | nhập | m |
| `dai_in` `rong_in` | dài/rộng khổ giấy in | nhập | m |
| `so_luong` | số lượng (thành phẩm) | nhập | thành phẩm |
| `so_tp` | số thành phẩm/tờ | nhập | — |
| `so_mau` | số màu in | quy cách | màu |
| `so_mat` | số mặt in (1 mặt→1; 2 mặt/tự trở→2) | quy cách | mặt |
| `so_kem` | số bản kẽm | quy cách | bản |
| `to_dau_vao` | **số tờ đầu vào máy in** | hệ thống | tờ |
| `to_sau_in` | **số tờ TỐT còn lại sau in** | hệ thống | tờ |
| `to_qua_buoc` | **số tờ đi qua CHÍNH bước này** (chỉ có trong công thức của công đoạn) | hệ thống | tờ |
| *(field của item)* | vd `dinh_luong`, `don_gia_kg`, `don_gia_m2`, `don_gia_kem` | danh mục | kg/m², đ/… |

> Khổ nhập bằng **cm**, biến đưa vào công thức quy về **m** (để `× đ/m²`, `× đ/kg` ra thẳng).
> `so_mau/so_mat/so_kem` đến từ khối **Quy cách in** (§6) — quy cách không tự tính tiền, chỉ cấp biến.

---

## 3. Hai số tờ (trái tim)

Bù hao KHÔNG phải một cục cộng vào cuối — nó là **chuỗi NGƯỢC** đi từ cuối routing lên đầu.
Mỗi bước hỏi *"để nhả ra `ra` tờ tốt thì phải nhận vào bao nhiêu?"*:

```
vào(bước) = (ra(bước) + tờ_cố_định) / (1 − %/100)      # tờ thì CỘNG, % thì CHIA

to_net      = ⌈so_luong / so_tp⌉                        → tờ tốt cần ở CUỐI chuỗi
to_dau_vao  = ⌈vào(bước đầu chuỗi)⌉ + "+ Bù thêm"       → nuôi GIẤY + IN
to_sau_in   = ra(bước có nhom="print")                  → nuôi CÔNG ĐOẠN SAU IN
```

Bậc bù hao của mỗi bước tra theo `ra` của **chính bước đó**, nên bước in ở đầu chuỗi rơi vào bậc
CAO hơn bước xén ở cuối — đúng thực tế. (Cộng xuôi phẳng theo một `to_net` chung thì mọi bước tra
cùng một bậc → thiếu giấy ở đầu chuỗi.) Xem `services/bu_hao_engine.chuoi_nguoc`.

Người viết công thức tự chọn nhân với `to_dau_vao`, `to_sau_in` hay `to_qua_buoc` → tự quyết chi
phí thuộc trước/sau in. **Engine không cần cờ "trước/sau in"** (nếu thêm cờ đó thì thừa và đá nhau
với công thức — 2 nguồn sự thật).

> Ô **"− Hao"** (`hao_so_to`) ĐÃ BỎ: nó vốn là bản thay tay cho "tờ mất khi in", nay `to_sau_in`
> lấy thẳng từ bước in trong chuỗi ngược. Cột DB giữ lại, engine lờ đi.

---

## 4. Công thức & bộ tính

- **Toán tử:** `+ − × ÷ ( )` + hàm `ceil, floor, round, max, min`.
- **Token:** biến hệ thống (§2) + field của item; giá trị field **hiển thị ngay trong công thức**,
  vd `định_lượng(0,25)`, `đơn_giá_kg(17.100)`. Đổi giá ở danh mục → công thức tự đổi (sửa 1 chỗ).
- **An toàn:** bộ tính riêng (parse + whitelist token), **không** dùng `eval` của Python.
- Công thức lỗi / thiếu biến → dòng đó **0đ + cảnh báo**, không được crash.
- **Quy ước:** công thức trả **TỔNG dòng**; `đ/thành phẩm = tổng ÷ so_luong` (§8).

**Công thức mẫu (mỗi dòng chọn 1 kiểu — engine không khóa cứng):**

| Dòng | Kiểu | Công thức |
|---|---|---|
| Giấy (NVL) | theo kg | `dinh_luong × dai_nguyen × rong_nguyen × don_gia_kg × to_dau_vao` |
| Cán màng / vecni (công đoạn) | theo m² | `dai_in × rong_in × don_gia_m2 × to_sau_in` |
| In (công đoạn) | khoán 1 lượt | `to_dau_vao × so_mat × don_gia_luot` |
| Kẽm (công đoạn/NVL) | theo bản | `so_kem × don_gia_kem` |
| Khuôn (công đoạn) | trọn gói ÷ SL | `800000` → 800.000 ÷ so_luong = 200 đ/thành phẩm |

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
| "+ Bù thêm" (vào `to_dau_vao`) | [Nhập] | mặc định 0 — ô tay DUY NHẤT; "− Hao" đã bỏ |
| Danh sách công đoạn (thêm/xóa) | [Auto] | routing Loại SP; mỗi công đoạn có công thức + bù hao |
| Vật tư thêm | [Nhập] | danh mục vật tư in ấn; mỗi vật tư có công thức |
| **số tờ đầu vào / sau in · số thành phẩm/tờ (hình học) · đ/thành phẩm từng dòng · tổng** | [Hiện] | tính-ra, khóa |

**Số thành phẩm/tờ (hình học)** — số thành phẩm tối đa nhét vừa 1 tờ in, tự tính có xoay bài:
```
= max( ⌊dai_in/dai_tp⌋×⌊rong_in/rong_tp⌋ , ⌊dai_in/rong_tp⌋×⌊rong_in/dai_tp⌋ )
```
Chỉ để **đối chiếu cảnh báo**: nếu `so_tp` (nhập tay) > số hình học → cảnh báo "bình bài không vừa".
Tiền vẫn tính theo `so_tp` KTV gõ.

**Khối Quy cách in** (mô tả — KHÔNG tính tiền, in ra cho sản xuất đọc): mẫu in · **cách in**
(1 mặt / tự trở / trở nhíp / AB) · màu in (CMYK / màu pha / vecni bóng / mờ) · **SL kẽm** + khổ kẽm.

- **Số màu · số mặt · số kẽm** phơi thành biến (`so_mau/so_mat/so_kem`) cho công thức dùng.
- **Cách in KHÔNG có luật ẩn** — chỉ là nhãn; KTV tự nhập `so_mat` & `so_tp` cho đúng:
  - 1 mặt → `so_mat`=1
  - **AB** (2 mặt khác bài, 2 bộ kẽm) → `so_mat`=2, `so_tp` **giữ nguyên**
  - Tự trở / trở nhíp (1 bộ kẽm, lật tờ) → `so_mat`=2, `so_tp` **÷2**
- Chi tiết thuần sản xuất (mẫu in duyệt, chốt khổ kẽm cụ thể) có thể để trống ở tính giá → firm
  up khi **lên đơn / lệnh sản xuất**.

---

## 7. Danh mục phải thêm "ô công thức"

Chỉ **2 danh mục** cần ô công thức (khớp "chi phí = NVL + công đoạn"):

- **Vật tư in ấn** (`Material` — gồm **giấy · kẽm · mực · keo · màng**…): thêm `cong_thuc_gia`;
  field riêng phơi thành biến (giấy: `dinh_luong`, `don_gia_kg`).
- **Công đoạn** (`Operation`): thêm `cong_thuc_gia` (bù hao đã có, nối qua `bu_hao_id`).
- **Loại SP**: chỉ giữ **routing công đoạn mặc định** (tái dùng, không thêm công thức).

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

> ⚠️ **Neo này TÍNH THEO MÔ HÌNH CŨ, chưa cập nhật.** Từ khi bù hao đi ngược theo công đoạn (§3),
> `to_sau_in` không còn là `to_dau_vao − hao tay` mà là `ra` của bước in trong chuỗi — nên dòng
> Cán màng của ca này sẽ ra số khác. Cần chạy lại `scripts/verify_hop_doi.py` với một routing có
> bước IN rồi neo lại số. Chưa làm.

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
