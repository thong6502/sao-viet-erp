# Thiết kế UI — "Hồ sơ lệnh sản xuất" (màn DANH SÁCH, Task 11)

> Trạng thái: **BẢN TRÌNH CHỐT** — chưa được duyệt, chưa dựng dòng code nào.
> Phạm vi tài liệu: **CHỈ phần DANH SÁCH** (Task 11). Màn hồ sơ chi tiết MỘT lệnh là Task 12,
> thiết kế riêng — ở đây chỉ chừa đúng một đường sang nó (§6.8).
> Backend **đã xong** (Task 9-10) và **KHÔNG đụng tới**. Mọi trường dưới đây bám đúng
> `backend/app/routers/lenh_san_xuat.py` + `schemas/lenh_san_xuat.py` +
> `services/lenh_sx/danh_sach.py`. Chỗ nào máy chủ chưa trả thì ghi thẳng ở §11, không vẽ ô ra
> rồi mong có dữ liệu.

**Định danh — giữ nguyên, đừng "sửa cho nhất quán":** nhãn hiển thị **"Hồ sơ lệnh sản xuất"**;
khoá quyền `lenh_san_xuat`; prefix `/api/lenh-san-xuat`; nav id `lenh-san-xuat`; file
`frontend/src/pages/LenhSanXuatPage.tsx` + `frontend/src/pages/lenh-san-xuat.css`; scope CSS `.hslsx`.

---

## 1. Màn này là gì, và nó KHÔNG phải cái gì

Đây là bàn của người **đi tra**: điều độ, QC, trưởng phòng KD, sale — mở ra để trả lời đúng một
câu *"lệnh này đang ở đâu, có kịp không"*. Nó **không ghi gì cả**.

| | Kế hoạch sản xuất (`KeHoachSXPage`, đã có) | Hồ sơ lệnh sản xuất (màn này) |
|---|---|---|
| Vai | người **LẬP** lệnh | người **TRA** lệnh |
| Tập dữ liệu | mọi lệnh, kể cả nháp | **chỉ `da_phat_hanh`** (`pham_vi.loc_lsx_da_phat_hanh`) |
| Ghi | tạo LSX, sửa routing, phát hành | **không một nút ghi nào** |
| Quyền | `san_xuat` | `lenh_san_xuat` (module RIÊNG) |

**Danh sách đóng những gì KHÔNG được có trên màn** (để agent BUILD không "tiện tay" thêm vào):
không **Tạo LSX**, không **Xuất Excel**, không **Nhập Excel**, không **Nhân bản**, không **Xóa**,
không nút điều hành (**Bắt đầu / Tạm dừng / Kết thúc / Giao người / Rút người**), không sửa routing.
Toàn bộ control bấm được trên màn chỉ có 5 loại: **đổi tab · đổi bộ lọc · gõ ô tìm · lật trang ·
mở hồ sơ**.

**Ràng buộc TIỀN (cứng, toàn module):** response không có `don_gia` / `gia_von` / `thanh_tien` /
`luong_khoan` / `chi_phi` — có bài canh `test_khong_lo_tien` giữ. Vì vậy **không thiết kế ô nào cần
số tiền**: không cột giá trị đơn, không "tổng tiền đang chạy trên chuyền", không tooltip nào nhắc
tiền. Đây là chủ ý: màn cho xưởng xem, không phải cho kế toán.

---

## 2. Hierarchy — mắt đi theo thứ tự nào, và vì sao đúng thứ tự đó

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ ① HEADER   Hồ sơ lệnh sản xuất  ·pill «N lệnh»·  [CHỈ XEM]                           │
│            Lệnh đã phát hành — theo dõi tới đâu. Tạo/sửa lệnh ở Kế hoạch sản xuất.   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ ② KPI      ┌──────────┐┌──────────┐┌──────────┐┌──────────┐                          │
│            │ Đang SX  ││ CĐ xong  ││ Dự kiến  ││ KCS đạt  │   ← toàn phạm vi,        │
│            │   47     ││ hôm nay  ││   trễ    ││ hôm nay  │     KHÔNG theo bộ lọc    │
│            │          ││    18    ││    6     ││  97,2 %  │                          │
│            └──────────┘└──────────┘└──────────┘└──────────┘                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ ③ LỌC      🔎 [Tìm mã lệnh, tên sản phẩm, số đơn, khách…]                            │
│            [Nhóm CĐ ▾] [Máy ▾] [Ưu tiên ▾]  Hạn SX: [từ]→[đến]  (Chỉ lệnh trễ) [Xóa] │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ ④ TAB      ‹Tất cả 132› ‹Đang SX 61› ‹Cảnh báo 14› ‹KCS 9› ‹Chờ nhập kho 7›          │
│              ‹Sẵn sàng giao 5› ‹Hoàn thành 36›                                       │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ ⑤ BẢNG     Mã │ Sản phẩm/SL │ Khách │ Máy/người │ Công đoạn + tiến độ │ Hạn/Dự kiến  │
│                                                        │ Trạng thái │ →              │
│            (khung riêng: cuộn NGANG + cuộn DỌC, thead ghim)                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ ⑥ CHÂN     Tổng N lệnh · Trang 2/6                                  [Trước] [Sau]    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Vì sao đúng thứ tự này:**

1. **KPI trước** vì nó trả lời câu hỏi *không cần tìm gì cả*: "hôm nay nhà máy thế nào". Người mở
   màn mà chưa biết mình tìm lệnh nào thì đọc 4 số này là xong việc, khỏi cuộn.
2. **Lọc TRƯỚC tab** — đây là điểm bắt buộc, không phải gu. Số trên mỗi tab là **facet của tập ĐÃ
   LỌC** (`dem_theo_tab`, xem `danh_sach.py:358-360`). Đặt tab lên trên bộ lọc thì người dùng gõ
   một chữ vào ô tìm rồi thấy cả bảy con số phía trên tự đổi — nguyên nhân nằm dưới kết quả, đọc
   ngược. Đặt lọc trên tab thì dòng chảy đúng chiều nhân quả: *thu hẹp tập → chia tập đã hẹp →
   đọc dòng*.
3. **Tab trước bảng** vì tab là lát cắt CUỐI CÙNG trước khi ra dòng, và nó là thứ điều độ bấm
   nhiều nhất trong ngày (Đang SX ↔ Cảnh báo). Để nó dính sát mép trên bảng thì tay không phải đi xa.
4. **Pager ở chân**, không ở đầu: trang chỉ có nghĩa sau khi đã nhìn hết dòng.

**Một cái bẫy đọc số phải xử ngay ở đây:** dải KPI lấy từ `GET /summary`, mà router `summary`
**không nhận một tham số lọc nào** — nó luôn là toàn phạm vi của token. Bảng thì đã lọc. Hai con số
"47 đang SX" (KPI) và "61 ở tab Đang SX" **không bao giờ khớp** và đó là đúng. Nên dải KPI phải
đeo nhãn phụ **"Toàn phạm vi của bạn · không đổi theo bộ lọc"** ngay dưới hàng thẻ. Thiếu câu này
là mỗi tuần có một người đi hỏi vì sao số lệch.

---

## 3. Bốn thẻ KPI

Nguồn: `GET /api/lenh-san-xuat/summary` → `LenhSxSummaryOut` (4 trường, đúng 4 thẻ, không thừa
không thiếu). "Hôm nay" ở đây là **ngày GIỜ XƯỞNG (+7)**, không phải ngày UTC — xưởng chạy ca đêm.

| # | Nhãn thẻ | Trường | Đơn vị / định dạng | Chú thích phải có (tooltip hoặc dòng phụ) |
|---|---|---|---|---|
| 1 | **Đang sản xuất** | `dang_sx` | số nguyên, `lệnh` | "Lệnh chưa ra khỏi nhà máy. **Không** bằng số ở tab Đang SX — lệnh đang chạy mà dính cảnh báo nằm ở tab Cảnh báo, nhưng nó vẫn đang sản xuất." |
| 2 | **Công đoạn xong hôm nay** | `cong_doan_xong_hom_nay` | số nguyên, `công đoạn` | "Đếm theo công đoạn, không theo lệnh. Một ca in ghép phục vụ nhiều lệnh vẫn tính **một**." |
| 3 | **Dự kiến trễ** | `du_kien_tre` | số nguyên, `lệnh` | "Lệnh **chưa xong** mà dự kiến vượt hạn SX nội bộ. Là tập con của thẻ Đang sản xuất. Bộ lọc «Chỉ lệnh trễ» rộng hơn thẻ này: nó đếm cả lệnh đã giao xong nhưng xong trễ." |
| 4 | **KCS đạt hôm nay** | `ty_le_kcs_dat_hom_nay` | `%` một chữ số thập phân | "Tính theo **số lượng** (Σ đạt / Σ nhận), không phải trung bình cộng các lô." |

**Ba luật hiển thị bắt buộc, mỗi luật vá một lời nói dối cụ thể:**

- Thẻ 4 nhận `null` ⇒ hiện **`—`** kèm dòng phụ *"Chưa kiểm lô nào hôm nay"*. **Cấm** đổ `0` vào
  đó: "0 % đạt" là một tiếng báo động sai, và nó sẽ nổ mỗi sáng sớm trước lô KCS đầu tiên.
- Đang tải ⇒ thẻ hiện **thanh shimmer**, không hiện `0`. Số 0 lúc đang tải là một khẳng định sai
  về nhà máy.
- Thẻ 3 tô **`--signal` / `--signal-soft`** khi `> 0`, còn `= 0` thì để trung tính như ba thẻ kia.
  Ba thẻ 1-2-4 **luôn** trung tính (`--paper` nền, `--rule-soft` viền): chúng là số đo, không phải
  báo động; tô màu cả bốn thì màu hết mang tin.

**Thẻ KPI KHÔNG bấm được** — quyết định tự chốt, lý do ở §12.

Dựng theo khuôn `.khsx-kpi-tile` của `ke-hoach-sx.css:1255-1345` (flex cột, `flex: 1 1 0`,
`align-items: stretch` ở hàng cha) — bê cấu trúc, đổi tiền tố sang `.hslsx-kpi`.
**Nhãn thẻ cho xuống dòng thoải mái** (`overflow-wrap: anywhere`), không `nowrap`, không ellipsis:
đó chính là bẫy (d) ở §9.

---

## 4. Ô tìm kiếm + bộ lọc

Toàn bộ lọc chạy **ở máy chủ**. Không có một dòng `rows.filter(...)` nào trong màn — bảng chỉ cầm
một trang, lọc trong JS sẽ biến ô tìm thành "tìm trong trang này".

| Control | Tham số | Giá trị | Ghi chú |
|---|---|---|---|
| Ô tìm | `q` | chuỗi ≤ 200 | Debounce **300 ms** bằng `useTre` (đã có ở `lib/useTre`). |
| Nhóm công đoạn | `nhom_cong_doan` | `prepress` · `print` · `finishing` · `other` | Enum 4 giá trị của `cong_doan.NHOM` (`models/cong_doan.py:25`) — **không** phải danh mục động. |
| Máy | `may_id` | id máy | Nguồn danh sách là một LỖ HỔNG, xem §11.2. |
| Ưu tiên | `uu_tien` | `gap` · `binh_thuong` | Cột thật là `lsx.is_rush` (Boolean). |
| Hạn SX từ → đến | `tu_ngay` / `den_ngay` | `date` | Soi `han_hoan_thanh_sx` (hạn **nội bộ**), không phải hạn giao khách. |
| Chỉ lệnh trễ | `tre` | `true` khi bật; **không gửi** khi tắt | Toggle 2 nấc. Không làm nấc "chỉ lệnh không trễ" — không ai hỏi câu đó. |

**Microcopy đã chốt (dùng đúng chữ này):**

- Placeholder ô tìm: **`Tìm mã lệnh, tên sản phẩm, số đơn, khách hàng`** — liệt kê đúng 4 thứ mà
  `_loc_sql` thật sự tìm (`Lsx.ma`, `Lsx.ten`, `Order.order_no`, `Customer.name`). Hứa nhiều hơn
  bốn thứ này là hứa suông.
- Nhãn cụm ngày: **`Hạn SX`** (không phải "Hạn"), kèm hint nhỏ dưới cụm:
  **`Lệnh chưa khai hạn SX không nằm trong khoảng nào.`** — vì `NULL` không khớp phép so nào, đặt
  khoảng ngày là chúng biến mất khỏi bảng. Không nói ra thì người dùng tưởng mất lệnh.
- Nhãn 4 nhóm công đoạn: lấy đúng map đó ở
  `frontend/src/pages/keHoachSxShared.tsx` → `export const NHOM_CONG_DOAN`
  (`prepress`→Chế bản · `print`→In · `finishing`→Gia công sau in · `other`→Dịch vụ khác).
  **Đừng gõ lại bốn chữ đó lần thứ hai.**
  *(Bản đầu của mục này trỏ sang `rebuildCatalogConfigs.tsx:21`. Task 11 đã CHUYỂN hằng sang
  `keHoachSxShared.tsx` — module dùng chung sẵn có của họ màn Sản xuất — vì import
  `rebuildCatalogConfigs` sẽ kéo trọn bộ máy 13 màn danh mục vào bundle của một màn tra cứu.
  `rebuildCatalogConfigs.tsx` nay import lại hằng đó, vẫn MỘT nguồn nhãn duy nhất.)*
- Nút **`Xóa bộ lọc`** chỉ mọc khi có ít nhất một thứ đang bật (kể cả `q` và tab ≠ Tất cả); bấm =
  về `q=""`, mọi select về "Tất cả", tắt `tre`, xoá khoảng ngày, **và** về tab Tất cả, `page=1`.

**Ô ngày — bẫy đã dính rồi, chặn sẵn:** `<input type="date">` cho gõ năm 6 chữ số và đẻ giá trị rác
→ 422 câm. Đặt `min="2000-01-01"` `max="2999-12-31"` trên cả hai ô, và **chỉ gửi tham số khi giá trị
parse ra ngày hợp lệ** — phân biệt "ô trống" (không gửi) với "gõ sai" (không gửi + viền cảnh báo).

**Đổi bất kỳ bộ lọc nào (kể cả tab) ⇒ `setPage(1)`** — khuôn `CatalogListPage.tsx:72`. Đứng ở trang
7 rồi gõ tìm còn 3 kết quả là bảng trống trơn.

---

## 5. Bảy tab

Nguồn giá trị: `danh_sach.TAB_CHO_PHEP` = `("tat_ca",) + trang_thai.TAB_CHINH`. **Chuỗi khoá là
hợp đồng** (đi thẳng ra URL) — đừng đổi.

| # | Nhãn | `tab=` | Lọc theo điều kiện gì (`trang_thai.trang_thai_chinh`) | Số đếm |
|---|---|---|---|---|
| 1 | **Tất cả** | `tat_ca` | không lọc trạng thái | `dem_theo_tab.tat_ca` |
| 2 | **Đang SX** | `dang_sx` | không rơi vào 5 nhánh dưới — lệnh còn trên chuyền | `dem_theo_tab.dang_sx` |
| 3 | **Cảnh báo** | `canh_bao` | `co_canh_bao()` không rỗng (sự cố · tạm dừng · trễ hạn · KCS không đạt · thiếu vật tư) | `dem_theo_tab.canh_bao` |
| 4 | **KCS** | `kcs` | mọi bước không-KCS đã xong, còn bước KCS chưa đóng | `dem_theo_tab.kcs` |
| 5 | **Chờ nhập kho** | `cho_nhap_kho` | SX xong + KCS cuối đã chốt được hàng đạt, kho chưa nhận | `dem_theo_tab.cho_nhap_kho` |
| 6 | **Sẵn sàng giao** | `san_sang_giao` | SX xong + kho **đã xác nhận nhận** ít nhất một phần | `dem_theo_tab.san_sang_giao` |
| 7 | **Hoàn thành** | `hoan_thanh` | khách đã **thực nhận** đủ `so_luong_dat` | `dem_theo_tab.hoan_thanh` |

Thứ tự trái→phải = thứ tự trong `TAB_CHINH`, tức **dòng chảy của lệnh**, với Cảnh báo chen ngay
sau Đang SX vì đó là hai tab được bấm nhiều nhất.

**Ba luật về con số trên tab — sai một cái là bảng nói dối:**

1. Số **lấy nguyên từ `dem_theo_tab` của máy chủ**. Cấm đếm từ `items` của trang đang xem: trang
   cầm 50 dòng mà tập có 132, tab sẽ hiện một con số sai mà không ai thấy sai.
2. `dem_theo_tab` **không bị chính `tab` đang chọn lọc lại** — nên bấm sang tab khác thì bảy con số
   **đứng yên**; chỉ đổi ô tìm / bộ lọc mới làm chúng đổi. Nếu thấy chúng về 0 khi bấm tab thì có
   người đã tính lại ở FE — sửa lại cho đúng.
3. Pill "N lệnh" cạnh tiêu đề = **`dem_theo_tab.tat_ca`** (tổng theo bộ lọc, **không** theo tab).
   Còn `total` của response là tổng **sau cả tab** và chỉ dùng cho `Pager`. Hai số khác nhau, đừng
   hoán chỗ — đứng ở tab "Chờ nhập kho" mà tiêu đề tụt xuống 7 thì người ta tưởng cả hệ có 7 lệnh.
   (Đúng bài học `tongTheoTim` ở `CatalogListPage.tsx:181-184`.)
4. Đang tải ⇒ tab hiện nhãn **không kèm số** (chỗ số để trống), **không** hiện `0`.

Hình thức: bê `.khsx-tabs` / `.khsx-tabs__btn` (`ke-hoach-sx.css:1353-1387`) — nền trắng, viền
`--rule-soft`, tab đang chọn nền `--charcoal` chữ trắng. Đúng ngôn ngữ app: **charcoal = lựa chọn
lọc, rust = hành động** — màn này không có hành động nào nên rust chỉ xuất hiện ở focus ring và
chip GẤP.

---

## 6. Bảng

### 6.1. Khung bảng

```html
<div class="hslsx__tablewrap">   <!-- overflow: auto · max-height: calc(100vh - 340px) -->
  <table class="hslsx__table">   <!-- table-layout: fixed · min-width: 1180px -->
```

- **`min-width: 1180px` trên `<table>`, KHÔNG `width: 100%`.** Đây là bẫy (b) ở §9: bảng
  `width:100%` nằm trong khung `overflow-x:auto` bị ép đúng bề ngang khung nên cột không nở, khung
  cuộn thành vô dụng.
- `max-height` + `thead { position: sticky; top: 0 }`: thanh cuộn ngang luôn nằm ngay dưới các hàng
  đang thấy, không bị đẩy xuống tận đáy trang ngoài tầm nhìn.
- `overscroll-behavior-x: contain` trên khung: vuốt ngang hết bảng thì **dừng**, không kéo cả trang
  đi theo.
- **Không** đặt `overflow-x: hidden` lên container trang (nó phá `position: sticky` của `thead`).
  Thay vào đó mọi khối con khai `min-width: 0`, và **chỉ** `.hslsx__tablewrap` được phép cuộn ngang.

### 6.2. Tám cột

`table-layout: fixed`. Cột mũi tên khai px, bảy cột còn lại khai `%` (chia phần còn lại).

| # | Cột | Rộng | Nội dung | Cắt chữ? |
|---|---|---|---|---|
| 1 | **Mã** | `11%` (~124px) | `ma` trong badge mã (`--ff-num`, tabular-nums) + chip **GẤP** khi `is_rush` | **KHÔNG BAO GIỜ** — `nowrap`, không ellipsis. Mã là định danh; cắt mã là hỏng cả dòng. |
| 2 | **Sản phẩm / SL** | `20%` (~226px) | dòng 1 `ten`; dòng 2 `so_luong_dat` + `don_vi_tinh`, thêm `· đã giao {da_giao}` **chỉ khi `da_giao > 0`** | Xuống dòng, clamp **2 dòng** + `title` đủ chữ ở ≥769px; **bỏ clamp** ở ≤768px |
| 3 | **Khách** | `13%` (~147px) | dòng 1 `khach_hang`; dòng 2 `sale` (nhỏ, `--ash-2`) | như cột 2 |
| 4 | **Máy / người** | `13%` (~147px) | dòng 1 `may`; dòng 2 `nguoi[]` — hiện **2 tên đầu + `+N`**, `title` đủ tên | cắt **từ cuối** (thứ tự mảng là thứ tự giao) |
| 5 | **Công đoạn + tiến độ** | `17%` (~192px) | dòng 1 `buoc_hien_tai` + chip nhóm CĐ; dòng 2 thanh tiến độ + `%` | nhãn bước clamp 1 dòng + `title` |
| 6 | **Hạn / Dự kiến** | `12%` (~136px) | dòng 1 `han_hoan_thanh_sx` (tô theo độ gấp); dòng 2 `du_kien_xong`; `han_giao_khach` ở `title` | `nowrap` (ngày ngắn, không cần co) |
| 7 | **Trạng thái** | `14%` (~158px) | pill trạng thái chính + tối đa **2** badge cảnh báo + `+N` | badge tự xuống dòng |
| 8 | (mũi tên) | **`48px` cố định** | nút mở hồ sơ | **không co, không ẩn** |

**Cột không bao giờ cắt chữ:** cột 1 (Mã) và cột 8 (mũi tên). Cột 6 `nowrap` nhưng nội dung là ngày
`dd/mm/yyyy` nên không có gì để cắt. Bốn cột còn lại được xuống dòng — **không cột nào dùng
`text-overflow: ellipsis` trên TÊN** (bẫy (d), §9).

### 6.3. Cột 5 — thanh tiến độ và cái cờ "ước tính"

`tien_do_pct` (0..100) + `tien_do_uoc_tinh` (bool). **Cờ phải ra tới mặt màn**: 40 % "đo được" và
40 % "ước tính" là hai mức tin cậy khác hẳn nhau, gộp làm một là mời điều độ ra quyết định trên con
số họ tưởng chắc hơn thực tế.

- `tien_do_uoc_tinh === false` ⇒ `42%`, thanh nền đặc.
- `tien_do_uoc_tinh === true` ⇒ **`~42%`** (có dấu ngã), thanh **vân sọc mảnh** (không chỉ đổi màu),
  `title="Ước tính theo thời lượng kế hoạch — bước chưa khai sản lượng"`.
- Thanh khai `role="progressbar"` + `aria-valuenow/valuemin/valuemax` + `aria-valuetext`
  (`"42 phần trăm"` / `"khoảng 42 phần trăm, ước tính"`).
- `gio_may` (giờ chạy thực tế) **không có cột riêng** — nó vào `title` của ô: *"Đã chạy 12,5 giờ
  máy"*. Kèm cảnh báo cho người đọc code: **đừng cộng `gio_may` qua nhiều lệnh** — một lượt in ghép
  3 lệnh được đếm đủ cho cả 3, cộng lại sẽ vượt giờ máy thật của xưởng.

### 6.4. Cột 6 — hai mốc, đừng lẫn

- Dòng trên là **`han_hoan_thanh_sx`** (hạn SX **nội bộ**) — đúng cột mà `tre_han` và bộ lọc ngày
  lấy làm mốc, nên ba chỗ nói cùng một chuyện. Tô bằng `classHan` (đã có ở `keHoachSxShared.tsx:46`):
  quá hạn → `--late`, còn ≤3 ngày → `--soon`.
- Dòng dưới là **`du_kien_xong`** (`datetime`, dùng `ngayGio()`). `null` ⇒ **`Chưa đủ dữ liệu`**
  chứ không phải `—`: máy chủ cố ý im khi có bước thiếu thời lượng, thà im còn hơn bịa một mốc mà
  điều độ sẽ đem đi hứa với khách.
- `han_giao_khach` chỉ nằm trong `title` (*"Hạn giao khách: 12/09/2026"*): cột đã chật, và trễ SX ≠
  trễ giao là hai chuyện khác nhau — bày cạnh nhau là mời so nhầm.
- `han_hoan_thanh_sx` là **`date`** không phải `datetime` ⇒ format bằng `ngay()`, **không** `ngayGio()`.

### 6.5. Cột 7 — pill trạng thái + badge cảnh báo

Pill trạng thái (6 giá trị, luôn có **chữ**, không chỉ dựa màu — a11y):

| `trang_thai` | Nhãn pill | Họ màu |
|---|---|---|
| `dang_sx` | Đang SX | `--steel` / `--steel-soft` |
| `canh_bao` | Cảnh báo | `--signal` / `--signal-soft` |
| `kcs` | KCS | `--plum` / `--plum-soft` |
| `cho_nhap_kho` | Chờ nhập kho | `--amber` / `--amber-soft` |
| `san_sang_giao` | Sẵn sàng giao | `--moss` / `--moss-soft` |
| `hoan_thanh` | Hoàn thành | `--ash` trên `--rule-hair` |

Badge cảnh báo (`canh_bao[]`, thứ tự máy chủ trả đã ổn định — **giữ nguyên**, đừng sort lại):

| mã | Nhãn badge | Họ màu |
|---|---|---|
| `su_co` | Sự cố | `--signal` |
| `tam_dung` | Tạm dừng | `--amber` |
| `tre_han` | Trễ hạn | `--signal` |
| `kcs_khong_dat` | KCS không đạt | `--signal` |
| `thieu_vat_tu` | Thiếu vật tư | `--amber` |

Pill và badge **không nói trùng nhau**: pill trả lời *"lệnh đang ở khâu nào"*, badge trả lời
*"vì cái gì mà nó bị giữ lại"*. Hiện tối đa 2 badge rồi `+N` (có `title` đủ chữ) để chiều cao hàng
không giật.

### 6.6. Chip GẤP

`is_rush === true` ⇒ chip **`GẤP`** cạnh mã, tái dùng `ChipGap()` của `keHoachSxShared.tsx:192`
(`.khsx-chip--rush`). Đây là chỗ **duy nhất** trên màn dùng tông rust ngoài focus ring. Lệnh gấp
cũng được máy chủ sắp lên đầu (`_khoa_sap`: gấp → hạn gần → mã), nên chip và thứ tự bảng cùng nói
một chuyện.

### 6.7. Bấm vào hàng

Cả hàng bấm được bằng **chuột** (`onClick` trên `<tr>`, hover đổi nền `--rust-soft`). Nhưng
**KHÔNG** gán `role="button"` lên `<tr>` — gán vai nút cho hàng là xoá luôn vai `row` của nó, trình
đọc màn hình mất cấu trúc bảng (không còn đọc được "cột Trạng thái: …"). Đường bàn phím đi qua nút
mũi tên ở cột 8 (§6.8). Bài học này đã trả giá một lần ở `CatalogListPage.tsx:415-420`.

### 6.8. Cột 8 — mũi tên mở hồ sơ (đường sang Task 12)

```jsx
<button type="button" className="hslsx__open"
        aria-label={`Mở hồ sơ lệnh ${r.ma} — ${r.ten ?? "chưa đặt tên"}`}
        onClick={(e) => { e.stopPropagation(); onMoHoSo(r.id); }}>
  <Icon name="chevron" size={16} />   {/* xoay −90° bằng CSS: icon `chevron` chỉ xuống */}
</button>
```

- Prop `onMoHoSo?: (id: number) => void` là **điểm nối duy nhất** sang Task 12. Task 11 không tự
  dựng màn đích, không tự đặt route.
- **Cột luôn tồn tại** với bề rộng 48px cố định, kể cả lúc Task 12 chưa nối — để layout không nhảy
  khi nối vào.
- Khi `onMoHoSo` chưa được truyền: **ô để RỖNG**, không vẽ nút xám. Nút xám vẫn là một lời mời;
  người ta sẽ hover đi hover lại tìm cách bật nó lên.
- Mũi tên **luôn hiện (opacity 1)**, không phải `opacity:0` + `:hover`. Đây là bẫy (c) ở §9 —
  cảm ứng không có trạng thái rê, thao tác coi như không tồn tại.

### 6.9. Phân trang — ở MÁY CHỦ

- `page` + `page_size`, **`PAGE_SIZE = 50`** (đúng `danh_sach.PAGE_SIZE_MAC_DINH`). Khai là hằng
  cục bộ trong `LenhSanXuatPage.tsx`, **không export**.
  *Vì sao 50 chứ không phải 20 như màn danh mục:* chi phí một request ở đây **không** phụ thuộc
  `page_size` — tầng 1 quét trọn tập rồi tầng 2 mới cắt trang (xem docstring `danh_sach.py:21-33`).
  Trang nhỏ = nhiều request = nhiều lượt quét. Bảng có `max-height` + cuộn dọc nên 50 dòng vẫn gọn.
- Dùng `<Pager>` sẵn có (`components/Pager.tsx`), `unit="lệnh"`, `total` = `total` của response
  (**không** `items.length`), `loading` để khoá nút chống bấm dồn.
- Gọi `trangHopLe(page, total, PAGE_SIZE)` trong `.then()` mỗi lần tải. Màn này không xoá dòng,
  nhưng `total` vẫn co lại khi người khác đổi trạng thái lệnh (SSE) — đang đứng trang 6 mà tập tụt
  còn 4 trang thì bảng rỗng trơn.
- Bảng rỗng ⇒ **ẩn** Pager (khối rỗng đã nói giúp rồi).

---

## 7. Ba trạng thái: đang tải · rỗng · lỗi

Hai request **độc lập** (`/summary` và `/`), nên **ba trạng thái này áp riêng cho từng khối**: KPI
hỏng không được kéo bảng chết theo, và ngược lại.

### 7.1. Đang tải

| Khối | Hiện gì |
|---|---|
| KPI | 4 thẻ giữ nguyên khung + nhãn, chỗ số là **thanh shimmer**. Cấm hiện `0`. |
| Tab | nhãn tab bình thường, **chỗ số để trống**. Cấm hiện `0`. |
| Bảng | **skeleton 8 hàng × 8 cột** (tái dùng `Skeleton` của `keHoachSxShared.tsx:386`, truyền `cols={8}`), giữ nguyên `thead` để bề ngang cột không nhảy khi dữ liệu về. |
| Pager | ẩn (chưa biết `total`). |

Lần tải **lại** (đổi tab / lọc / lật trang) mà bảng **đang có dữ liệu**: giữ nguyên dòng cũ, chỉ
làm mờ nhẹ (`opacity: .55`) + khoá nút Pager. Thay bảng bằng skeleton mỗi lần bấm tab là màn nhấp
nháy liên tục.

### 7.2. Rỗng — ba ca khác hẳn nhau, đừng gộp

Hàng `<tr>` duy nhất, `colSpan={8}`, dùng `EmptyState` (`keHoachSxShared.tsx:402`).

| Ca | Điều kiện | Chữ chính | Chữ phụ | Nút |
|---|---|---|---|---|
| (a) chưa có gì | không lọc, không tab, `dem_theo_tab.tat_ca === 0` | **`Chưa có lệnh sản xuất nào đã phát hành trong phạm vi của bạn.`** | `Lệnh còn đang lập vẫn nằm ở màn Kế hoạch sản xuất.` | **không nút** (màn chỉ đọc — không mời tạo lệnh) |
| (b) bộ lọc không ra | có `q`/lọc bất kỳ | **`Không có lệnh nào khớp bộ lọc.`** | `Thử bỏ bớt điều kiện, hoặc mở rộng khoảng hạn SX.` | `Xóa bộ lọc` |
| (c) chỉ do tab | `dem_theo_tab[tab] === 0` mà `dem_theo_tab.tat_ca > 0` | **`Tab «Chờ nhập kho» hiện không có lệnh nào.`** (chèn đúng nhãn tab) | — | `Về tab Tất cả` |

Icon rỗng: `clipboard` (ca a/c) · `search` (ca b), cỡ 44.

### 7.3. Lỗi

| Ca | Hiện gì |
|---|---|
| Bảng hỏng **khi đang rỗng** | Khối rỗng đổi mặt: icon `alert` màu `--signal`, chữ chính **`Không tải được danh sách lệnh.`**, chữ phụ = **message thật** từ `ApiError` (hoặc `Máy chủ không phản hồi.`), nút **`Tải lại`**. |
| Bảng hỏng **khi đang có dữ liệu** | Giữ nguyên bảng cũ + banner `banner--error` phía trên: `Không làm mới được danh sách.` + nút `Tải lại`. Bảng cũ vẫn đọc được còn hơn màn trắng. |
| KPI hỏng | 4 thẻ hiện `—`, một dòng nhỏ dưới dải: **`Không tải được số tổng hợp.`** + nút chữ `Thử lại`. **Không** chặn bảng. |
| 403 (ngoài phạm vi) | **`Bạn không có quyền xem hồ sơ lệnh sản xuất.`** — không nút Tải lại (thử lại cũng thế). Bình thường cổng quyền ở `AppShell` đã chặn trước; nhánh này lo ca scope đổi giữa phiên. |

**Cấm** cả hai chỗ (banner + khối rỗng) cùng kêu một lỗi kèm hai nút "Tải lại" — người dùng phải
đoán bấm cái nào. Hoặc banner, hoặc khối rỗng, không cả hai.

---

## 8. Bàn phím & trợ năng

### 8.1. Dải tab — `tablist` thật, kích hoạt THỦ CÔNG

```html
<div role="tablist" aria-label="Lọc lệnh theo trạng thái">
  <button role="tab" id="hslsx-tab-dang_sx"
          aria-selected="true" aria-controls="hslsx-panel" tabindex="0">…</button>
  …
</div>
<div id="hslsx-panel" role="tabpanel" aria-labelledby="hslsx-tab-dang_sx" tabindex="0"> …bảng… </div>
```

- **Roving tabindex**: chỉ tab đang chọn có `tabIndex={0}`, sáu tab kia `tabIndex={-1}`. Cả dải là
  **MỘT** tab-stop.
- `←` `→` **chỉ dời focus**, không đổi tab. `Enter` / `Space` mới đổi. Đây là **kích hoạt thủ công**
  và nó bắt buộc ở đây: mỗi lần đổi tab là một request về máy chủ; kích hoạt tự động khi lướt phím
  sẽ bắn 6 request liên tiếp.
- `Home` / `End` nhảy tab đầu / cuối.
- Chọn `role="tablist"` (khác `role="group"` + `aria-pressed` mà `CatalogListPage` dùng cho chip
  lọc) vì ở đây **luôn có đúng một** trong bảy đang chọn và nó đổi nội dung của một panel — đúng
  định nghĩa tabs. Đổi lại thì **phải** kèm điều hướng mũi tên: một `tablist` không đi được bằng
  phím mũi tên còn tệ hơn bảy cái nút thường.

### 8.2. Thứ tự tab-stop trên màn

1. Ô tìm kiếm → 2. nút xoá ô tìm (chỉ khi có chữ) → 3. select **Nhóm CĐ** → 4. select **Máy**
(nếu hiện) → 5. select **Ưu tiên** → 6. ô **Hạn từ** → 7. ô **Hạn đến** → 8. toggle **Chỉ lệnh
trễ** → 9. nút **Xóa bộ lọc** (nếu hiện) → 10. **dải tab (1 stop)** → 11. **khung bảng** (`tabindex=0`
để cuộn được bằng phím khi bảng rộng hơn khung) → 12. **mũi tên từng dòng**, theo thứ tự dòng →
13. **Trước** → 14. **Sau**.

Bốn thẻ KPI **không** nằm trong luồng tab-stop (không phải control — xem §12, quyết định 1).

### 8.3. Focus ring

```css
.hslsx :focus-visible { outline: 2px solid var(--rust); outline-offset: 2px; border-radius: var(--r-2); }
```

- `:focus-visible` chứ không `:focus` — bấm chuột không nháy vòng, đi phím thì luôn thấy.
- **Cấm `outline: none`** ở bất cứ đâu trong `lenh-san-xuat.css`, kể cả trên `<tr>` và trên nút
  mũi tên.
- Trên nền tab đang chọn (`--charcoal`) thì rust vẫn đủ tương phản; không cần biến thể riêng.

### 8.4. Còn lại

- Mọi pill / badge **luôn có chữ**, không bao giờ chỉ có màu hay chỉ có chấm.
- Vùng đếm tổng (`Tổng N lệnh`) khai `aria-live="polite"`: đổi bộ lọc thì trình đọc màn hình biết
  kết quả vừa đổi, không phải người dùng tự đi dò.
- `<table>` có `<caption class="sr-only">Danh sách lệnh sản xuất đã phát hành</caption>`;
  `<th scope="col">` cho cả 8 cột; cột 8 có tiêu đề ẩn (`<span class="sr-only">Mở hồ sơ</span>`) —
  `<th>` rỗng làm trình đọc màn hình đọc "cột trống".
- Mọi `title` dùng để bù chữ bị cắt **phải** có bản `sr-only` đi kèm hoặc nằm trong `aria-label`:
  `title` không tới được người dùng bàn phím và cảm ứng.

---

## 9. Màn hẹp — và bốn khuôn lỗi phải né sẵn

Dự án đã rà toàn hệ ở 375 px và thấy gần như mọi lỗi điện thoại rơi vào **đúng bốn khuôn**. Màn này
né sẵn từ lúc thiết kế, không đợi vá:

| Khuôn lỗi | Né thế nào ở màn này |
|---|---|
| **(a) `justify-content: space-between` bóp chữ** | Header và hàng lọc **không** dùng `space-between`. Dùng `.hslsx__spacer { flex: 1 }` như `.rc__spacer`, mọi hàng khai `flex-wrap: wrap`, khối chữ khai `flex: 1 1 <basis>` để nó là thứ được nở chứ không phải thứ duy nhất bị co. |
| **(b) bảng `width:100%` trong khung cuộn** | `<table>` khai **`min-width: 1180px`**, tuyệt đối không `width: 100%`. |
| **(c) nút chỉ hiện khi `:hover`** | Mũi tên cột 8 **luôn** `opacity: 1`. Hover chỉ đổi màu nền. Thêm nhánh `@media (hover: none)` để bỏ mọi hiệu ứng hover-only. |
| **(d) `ellipsis` nuốt tên** | Không `text-overflow: ellipsis` trên `ten` / `khach_hang` / `buoc_hien_tai`. Desktop dùng `-webkit-line-clamp: 2` + `title`; **≤768px bỏ clamp** — trên điện thoại thà xuống dòng. Nhãn KPI dùng `overflow-wrap: anywhere`. |

**Breakpoint (bám đúng ba nấc app đang dùng: 1024 / 768 / 480):**

| Nấc | Đổi gì |
|---|---|
| **≤1024px** | Dải KPI 4 cột → **lưới 2×2** (`grid-template-columns: repeat(2, minmax(0,1fr))`). Hàng lọc xuống dòng; ô tìm chiếm trọn dòng (`flex: 1 1 100%`). `max-height` của khung bảng nới thành `calc(100vh - 260px)`. |
| **≤768px** | Dải **tab cuộn ngang trong chính nó** (`flex-wrap: nowrap; overflow-x: auto; scroll-snap-type: x proximity`) thay vì wrap thành 3 hàng cao ngất — kèm `-webkit-overflow-scrolling: touch`. Cụm **Hạn SX từ→đến** xuống một dòng riêng. Bỏ `line-clamp` ở cột 2/3/5. Bỏ hover-only. |
| **≤480px** | KPI giữ **2×2** (ở 375px: (375−32 padding−8 gap)/2 ≈ 167px/thẻ — vẫn đọc được; ép 1 cột là phải cuộn để thấy thẻ thứ 4). Cỡ chữ nhãn KPI xuống `--fs-2xs`. Nút Pager to lên `min-height: 40px` cho ngón tay. |

**Không ẩn cột nào trên màn hẹp.** Bảng vẫn đủ 8 cột và cuộn ngang **trong khung riêng** — ẩn cột
là giấu mất dữ liệu người ta mở màn ra để tìm. Bù lại, ở ≤768px hiện một dòng chữ nhỏ (`--ash-2`)
ngay dưới khung bảng: **`Vuốt ngang để xem thêm cột →`**, chỉ khi `scrollWidth > clientWidth`.

**Thân trang không bao giờ cuộn ngang.** Chỉ `.hslsx__tablewrap` được cuộn ngang.

---

## 10. Ánh xạ API → UI (bám đúng schema, không bịa trường)

Thêm nhánh `api.lenhSanXuat` vào `frontend/src/api/client.ts`, dùng helper `authed<T>` sẵn có.

| Hành động | Endpoint | Method client dự kiến | Trả về |
|---|---|---|---|
| Nạp 4 KPI | `GET /api/lenh-san-xuat/summary` | `api.lenhSanXuat.summary(token)` | `LenhSxSummaryOut` |
| Nạp bảng | `GET /api/lenh-san-xuat?tab&q&page&page_size&nhom_cong_doan&may_id&uu_tien&tre&tu_ngay&den_ngay` | `api.lenhSanXuat.danhSach(token, params)` | `LenhSxListOut` |
| (Task 12) hồ sơ 1 lệnh | `GET /api/lenh-san-xuat/{id}` | — | `LenhSxHoSoOut` |

**Type TS phải mirror ĐÚNG `LenhSxItem`** — 21 trường:
`id · ma · ten · khach_hang · khach_hang_id · sale · so_luong_dat · don_vi_tinh · da_giao ·
is_rush · buoc_hien_tai · nhom_cong_doan · may · nguoi[] · tien_do_pct · tien_do_uoc_tinh ·
gio_may · han_hoan_thanh_sx · han_giao_khach · du_kien_xong · trang_thai · canh_bao[]`.

`LenhSxListOut`: `items · total · page · page_size · dem_theo_tab`.

> **Bẫy Pydantic của repo:** service trả `dict`, router khai `response_model` ⇒ trường không có
> trong schema bị **nuốt im lặng**, FE nhận `undefined`, không lỗi, không cảnh báo. Nên **không
> thêm trường nào ở FE mà không có trong schema** — và nếu Task 12 cần thêm thì phải đi hết chuỗi
> `danh_sach._dong()` → schema → type TS.

**Hai trường trả về mà màn này KHÔNG dùng, ghi rõ để đừng ai tưởng quên:**
- `khach_hang_id` — không dùng. Muốn bấm tên khách để nhảy sang màn Khách hàng thì cần quyền
  `khach_hang`, mà vai QC / tổ trưởng không có ⇒ bày link ra là mời ăn 403 giữa luồng.
- `page` / `page_size` trong response — chỉ để đối chiếu; `Pager` đọc state của FE.

**Realtime (Bước 4 của plan, ghi ở đây cho trọn thiết kế):** thêm `lenh_san_xuat` và
`theo_doi_san_xuat` vào `REALTIME_MODULES` (`components/appShellRealtime.ts` — hiện chưa có hai
khoá này, nên vai chỉ có `lenh_san_xuat` **không mở nổi kênh SSE**). Khi nhận sự kiện SX:
- **Gộp sự kiện, debounce 2 giây** rồi mới gọi lại — chuyền chạy thì sự kiện tới liên tục, refetch
  mỗi cái là bảng nhấp nháy dưới tay người đang đọc.
- Gọi lại **cả `/summary` lẫn danh sách**, **giữ nguyên** `page` / `tab` / bộ lọc / vị trí cuộn.
- **Không toast.** Bảng tra cứu không phải chỗ báo tin. Thay vào đó chân bảng hiện dòng nhỏ
  `Vừa cập nhật HH:MM`.

---

## 11. API còn thiếu gì so với thiết kế

### 11.1. Lệnh ở tab Cảnh báo mất dấu khâu đang đứng — *chấp nhận được, không chặn*

`trang_thai_chinh` trả **đúng một** giá trị và Cảnh báo **ăn trước** ba khâu sau. Nên một lệnh
đang ở khâu KCS mà dính sự cố sẽ hiện `trang_thai = "canh_bao"`, và bảng **không có trường nào**
nói nó đang ở KCS. Giảm nhẹ: cột 5 vẫn hiện `buoc_hien_tai` + `nhom_cong_doan` nên không mù hẳn.
**Không xin thêm trường** cho Task 11 — nếu về sau thấy cần thì đó là một trường `khau` tách khỏi
`trang_thai`, việc của backend.

### 11.2. Bộ lọc **Máy** không có nguồn danh sách trong phạm vi quyền — *lỗ hổng thật*

API nhận `may_id`, nhưng **không endpoint nào dưới `/api/lenh-san-xuat` trả danh sách máy**. Nguồn
duy nhất đang có là `GET /api/may-thiet-bi`, mà nó gác bằng
`require_any_permission(("dm_thiet_bi","read"), ("tinh_gia_thanh","read"))`
(`routers/may_thiet_bi.py:52`). Đối chiếu `seed.ROLES`: vai **QC** có `lenh_san_xuat` nhưng
**không có** cả hai quyền đó ⇒ **403**. Không thể suy danh sách từ `items` vì bảng chỉ cầm một
trang.

**Xử lý ở Task 11:** gọi thử `/api/may-thiet-bi`; **403 hoặc lỗi ⇒ ẩn hẳn ô lọc Máy** (không bày
một select rỗng — nút bày ra để rồi từ chối là đúng thứ dự án đã bỏ công gỡ ở màn danh mục). Ba bộ
lọc còn lại vẫn chạy.

**Đề xuất cho chủ dự án (ngoài phạm vi Task 11):** thêm `GET /api/lenh-san-xuat/bo-loc` gác bằng
chính `lenh_san_xuat:read`, trả danh sách máy **có xuất hiện trong tập lệnh của phạm vi người gọi**
(kèm số lệnh mỗi máy). Vừa lấp lỗ quyền, vừa cho ra một select **ngắn và đúng** thay vì cả danh mục
máy — và nó dùng lại được cho Task 12.

### 11.3. Không có `may_id` trên dòng — *nhỏ, ghi để biết*

`LenhSxItem` chỉ có `may` (tên). Nên **không** làm được thao tác "bấm tên máy trên dòng để lọc theo
máy đó" — sẽ phải dò ngược tên → id. Thiết kế này **không dùng** thao tác đó.

### 11.4. KPI không nhận bộ lọc — *cố ý, đã xử ở §2*

`GET /summary` không có tham số lọc nào. Đã xử bằng nhãn *"Toàn phạm vi của bạn · không đổi theo bộ
lọc"*. Đừng "sửa" bằng cách tự tính KPI ở FE từ `items`: trang chỉ có 50 dòng.

---

## 12. Những chỗ plan không nói, tôi tự chốt

| # | Quyết định | Vì sao | Đổi được không |
|---|---|---|---|
| 1 | **Thẻ KPI không bấm được** | Định làm thẻ "Dự kiến trễ" bấm ra bộ lọc `tre=true`, nhưng hai con số **không khớp**: KPI đếm lệnh *chưa xong* mà trễ, còn `tre=true` trả cả lệnh **đã giao xong nhưng xong trễ** ⇒ bấm một cái ra số lớn hơn cái vừa đọc. Đó là kiểu lệch làm mất lòng tin vào cả màn. Đổi lại: giữ toggle **"Chỉ lệnh trễ"** ở hàng lọc + một câu chú thích nói rõ hai tập khác nhau. | Được — nếu chủ dự án chấp nhận số lệch, hoặc backend tách `tre_chua_xong`. |
| 2 | **`PAGE_SIZE = 50`** (màn danh mục dùng 20) | Chi phí một request không phụ thuộc `page_size` — tầng 1 quét cả tập rồi mới cắt. Trang nhỏ = nhiều lượt quét hơn. 50 cũng đúng mặc định máy chủ nên không đẻ ra con số thứ hai phải nhớ. | Được, 25 nếu thấy dòng quá dày. |
| 3 | **`role="tablist"` + kích hoạt thủ công** cho 7 tab | Đúng một tab luôn được chọn và nó đổi nội dung panel ⇒ tabs thật, khác chip lọc `aria-pressed` của màn danh mục. Kích hoạt thủ công (Enter/Space) để lướt phím không bắn 6 request. | Được — lùi về `role="group"` + `aria-pressed` cũng hợp lệ, chỉ mất điều hướng mũi tên. |
| 4 | **Không ẩn cột nào ở màn hẹp**, bảng cuộn ngang đủ 8 cột | Ẩn cột là giấu mất dữ liệu người ta mở màn ra để tìm. Bù bằng gợi ý "Vuốt ngang…". | Được, nhưng nếu ẩn thì phải có đường xem lại (mở rộng dòng), không ẩn suông. |
| 5 | **SSE debounce 2s, không toast, giữ nguyên vị trí** | Nguyên tắc "thông báo nội bộ = real-time" của dự án nhắm vào **việc gửi giữa người với người**. Đây là bảng tra cứu; toast mỗi lần một tổ bấm Kết thúc là làm phiền, và refetch không debounce là bảng nhảy dưới tay. | Được. |
| 6 | **Bộ lọc Máy tự ẩn khi 403** thay vì bày select rỗng | Bày nút để rồi từ chối là lỗi dự án đã bỏ công gỡ ở màn danh mục. | Không nên đổi — trừ khi làm §11.2. |
| 7 | **`gio_may` vào `title`**, không có cột riêng | Bảng đã 8 cột; và số này không cộng qua nhiều lệnh được (in ghép đếm đủ cho mọi lệnh) nên nó không phải số để quét, chỉ để tra một dòng. | Được. |
| 8 | **Scope CSS `.hslsx`** | `.lsx` chưa có ai dùng làm class nhưng `lsx` là định danh JS ở khắp repo — dễ grep nhầm. `.khsx` là Kế hoạch SX, `.thsx` là Thực hiện SX, nên `.hslsx` = Hồ Sơ Lệnh SX, không đụng ai. | Được. |

---

## 13. Token / hình thức — bám `styles/tokens.css`, cấm hex thô

Bọc mọi rule trong `.hslsx`. Không thêm biến `:root`. Hai màn Sản xuất đứng cạnh nhau nên hệ màu và
spacing lấy từ `ke-hoach-sx.css`.

| Vai trò | Token |
|---|---|
| Nền trang / nền thẻ, khung bảng | `--paper` / `--canvas` |
| Chữ chính / mờ / rất mờ | `--ink` / `--ash` / `--ash-2` |
| Đường kẻ | `--rule` / `--rule-soft` / `--rule-hair` |
| Tab đang chọn | `--charcoal` nền, `--on-charcoal` chữ |
| Chip GẤP · focus ring · hover hàng | `--rust` / `--rust-deep` / `--rust-soft` |
| Trạng thái | `--steel` · `--signal` · `--plum` · `--amber` · `--moss` (+ `-soft`) |
| Mã, số lượng, %, giờ, ngày | `--ff-num` + `font-variant-numeric: tabular-nums` |
| Chữ thường (tên SP, khách, công đoạn) | `--ff-sans` — **đừng** dùng `--ff-num` cho chữ |
| Cỡ chữ / giãn cách / bo góc | `--fs-*` · `--sp-*` (thang 4px) · `--r-2`/`--r-3`/`--r-5`, pill `--r-pill` |

Bề rộng trang: `max-width: 1360px; margin: 0 auto; padding: var(--sp-5) var(--sp-6)` — rộng hơn
`.khsx` (1280) vì bảng 8 cột, và đúng bằng `min-width` của bảng + padding nên ở màn desktop thường
bảng **không phải cuộn ngang lần nào**.

Ép font cho control (bẫy đã dính ở `.khsx`):
```css
.hslsx button, .hslsx input, .hslsx select { font-family: inherit; }
```

**Cấm** hex thô trong `lenh-san-xuat.css` — kể cả các hex đang nằm trong `ke-hoach-sx.css`
(`#f8fafc`, `#0f172a`, `#e2e8f0`…). Bê **cấu trúc**, không bê giá trị: dùng token tương đương.

---

## 14. Nhắc cho agent BUILD (Bước 3 trở đi)

1. **Không có nút ghi nào.** Đọc lại §1 trước khi thêm bất cứ `<Button variant="accent">` nào.
2. **Không bịa trường.** Mọi ô bám §10. Pydantic nuốt trường lạ im lặng — FE nhận `undefined` và
   không ai thấy lỗi.
3. **Không một số tiền nào**, kể cả trong `title`.
4. **Lọc + đếm + cắt trang đều ở máy chủ.** Không `rows.filter`, không `rows.slice`, không đếm tab
   từ `items`.
5. **Bê từ `CatalogListPage.tsx`:** khuôn `load()` một-request-một-trang, `setPage(1)` khi đổi lọc,
   `trangHopLe` sau mỗi lần tải, ba ca rỗng tách bạch, nút mở dòng là `<button>` thật trong ô chứ
   không phải `role="button"` trên `<tr>`.
6. **Bê từ `keHoachSxShared.tsx`, đừng chép:** `ngay` · `ngayGio` · `num` · `classHan` · `ChipGap` ·
   `EmptyState` · `BangLoi` · `Skeleton`. Pill trạng thái của màn này là **bộ mới** (6 giá trị của
   `TAB_CHINH`) — khai trong `LenhSanXuatPage.tsx`, đừng nhét vào `keHoachSxShared` (nó là nhãn của
   màn Kế hoạch, hai bộ khác nhau).
7. **`han_hoan_thanh_sx` / `han_giao_khach` là `date`** ⇒ `ngay()`. **`du_kien_xong` là `datetime`**
   ⇒ `ngayGio()`. Nhầm là ra "12/09/2026 07:00" cho một cái không có giờ.
8. **Bốn khuôn lỗi điện thoại (§9) né NGAY lúc viết CSS**, đừng để dồn sang lượt rà 375px.
9. **Không đụng `AppShell.tsx` / `Sidebar.tsx`** cho tới khi chủ dự án chốt bản thiết kế này
   (Bước 2 của plan). Đó là cổng thật, không phải thủ tục.
10. **Verify:** `npx tsc --noEmit` + soi màn thật trên dev-browser (bấm **từng** tab trong 7 tab và
    đọc số đếm · gõ mã có thật rồi mã không có thật · đổi từng bộ lọc · sang trang 2 rồi về trang 1
    · cuộn bảng hết sang phải · thu cửa sổ còn 390px). Không dùng API/curl thay bất kỳ bước nào.
