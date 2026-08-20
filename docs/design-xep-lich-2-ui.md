# THIẾT KẾ UI — XẾP LỊCH CÔNG ĐOẠN 2 (một bàn làm việc)

> Bản thiết kế cho **agent BUILD**. Nguồn nghiệp vụ: `docs/spec-xep-lich-2.md`. Nguồn hệ màu/chữ:
> `docs/UI_DESIGN.md`. Đây là màn **thứ hai** của pha xếp lịch, khoá quyền riêng `xep_lich_2`,
> ghi vào **cùng bảng** `xep_lich_cong_doan` với màn cũ — *một lịch thật, hai cửa vào*.
>
> Người dùng: điều độ viên biết nghề, biết chữ (KHÔNG phải màn thợ textless).
>
> Nguyên tắc xuyên suốt: **MÁY CHỈ GHI NHẬN** — máy gợi ý và mô phỏng, người quyết. Mọi "phương án
> sửa" là **liên kết điều hướng** sang đúng module nguồn, KHÔNG phải nút tự-sửa-dữ-liệu.
>
> Prefix CSS đề xuất: **`.xl2-`** (không đè lên `.xlcd-` của màn cũ). Được phép **tái dùng** các
> primitive dùng-chung trong `keHoachSxShared.tsx` (liệt kê ở §3).

---

## MỤC LỤC

1. Soi màn cũ — giữ gì, bỏ/gộp gì, sửa gì
2. Cây component + lưới khung (grid layout)
3. Bảng token/spacing/typography tái dùng + prefix class mới
4. Đặc tả từng vùng + đủ trạng thái (rỗng · nạp · lỗi · chưa-có-dữ-liệu)
5. Ba mức kiểm soát — hiện thống nhất ở 4 vùng
6. Luồng thao tác chính
7. Real-time (eventTick / SSE `xep_lich_changed`)
8. A11y (bàn phím kéo-thả, aria, tương phản)
9. Ghi chú bàn giao cho agent BUILD

---

## 1. SOI MÀN CŨ — GIỮ / BỎ-GỘP / SỬA

Màn cũ = `XepLichPage.tsx` (2087 dòng) + `GanttBoard.tsx` + `XepLichVanDeView.tsx`. Nó **đã** được
kéo về "một board" ngày 18/08/2026 (view *Bảng* và *Vấn đề* đã xoá, Gantt là board duy nhất). Nên
điểm yếu "ba tab rời" mà spec §1 nêu **phần lớn đã được xử ở màn cũ** — việc của màn 2 KHÔNG phải
"gộp lại ba tab" mà là **làm lại đúng mô hình một-bàn + ba-mức trên hợp đồng API v2 mới**.

| Hạng mục màn cũ | Phán quyết | Lý do |
| --- | --- | --- |
| **Gantt là board duy nhất** (bar có đoạn setup, râu min/max, dry-lag, chip vấn đề) | **GIỮ mô hình, dựng lại** | Đúng hướng. Nhưng bar v2 phải đọc số từ `/api/xep-lich-2`, và **bỏ** mọi tô màu theo khổ/số màu/gsm (spec §6). |
| **Hàng chờ là POPUP** (`QueuePopup` mở từ badge) | **BỎ — đổi thành cột trái CỐ ĐỊNH** | Đây là điểm khác thật sự. Spec §8 muốn hàng chờ nằm **thường trực bên trái** cùng khung với Gantt, chia hai rổ *Có thể xếp* / *Bị chặn*. Popup bắt người dùng đóng/mở, mất mạch. |
| **Panel phải dính inline** (`.xlcd-side__box`, không phải modal) | **GIỮ mô hình sticky inline** | Đúng. Panel v2 (`.xl2-panel`) cũng sticky, không modal scrim. |
| **Dải chân charcoal** ("N chưa phát hành được · M nên xem" + nút Phát hành) | **GIỮ, mở rộng 2→3 số** | Màn cũ gộp mức còn 2 (`chan` / `luu_y`). Spec §7 cần **3 số**: chặn đặt lịch · chặn phát hành · cảnh báo. |
| **Mức vấn đề chỉ 2 bậc** (`XEP_LICH_SEV_META`: `chan` / `luu_y`) | **SỬA — nâng lên 3 mức** | `chan_dat_lich` / `chan_phat_hanh` / `canh_bao` (§5). Đây là thay đổi lõi của màn 2. |
| **`PreviewImpactDialog`** (Huỷ / Tìm khe trống / Chèn / Vẫn xếp) | **GIỮ mô hình preview-trước-khi-ghi** | Rất tốt, đúng "máy chỉ ghi nhận". Đổi nguồn số sang `POST /rows/{id}/preview`. |
| **Kéo-thả Pointer Events + AbortController + ghost + snap ca** | **GIỮ toàn bộ cơ chế** | Đã chín (`onBarDown/Move/Up`, `tryGan` một cửa preview, `onBarKey` mũi tên). Tái dùng ý tưởng, viết lại dưới prefix `.xl2-`. |
| **Nền ca / vùng khoá máy / nền tải tổ** (`lich-nen`, `xlcd-gtai`) | **GIỮ + THÊM nền ngày lễ** | v2 khác màn cũ: ngày lễ **vẫn xếp được**, chỉ tô nền khác + ghi chú tên lễ (spec §3, §10.1). Màn cũ để trống ngày nghỉ — **đừng chép lỗi này**. |
| **Cắt việc theo ca** (finish bị bẻ theo khung ca) | **BỎ HẲN** | v2: đã bắt đầu thì **chạy liên tục tới xong**, `finish = start + chiem_may_phut` theo giờ tường (spec §3, §10.2). Ca chỉ gác *giờ bắt đầu*. |
| **Cụm lane** | **SỬA — làm rõ 3 CỤM** | Máy · Tổ · **Nhà cung cấp**. Cụm NCC là điểm nhấn mới (gom theo `nha_cung_cap` chuẩn hoá), màn cũ mờ nhạt chỗ này. |
| **`_may_fit` (khổ/số màu/gsm)** | **KHÔNG GỌI** | spec §6: bỏ hẳn mọi kết luận theo khổ/số màu/định lượng. File còn cho màn cũ, v2 không đụng. |
| **"Phương án" trong drawer vấn đề** (`phuongAnCho` điều hướng) | **GIỮ mô hình điều hướng** | Đúng tinh thần "máy ghi nhận". Trường v2 tương ứng là `sua` (§5). |
| **Nút "Dời sang khe trống"** | **GIỮ** như một gợi ý trong panel | Rẻ, hữu ích. |

**Kết luận soi:** không bê nguyên màn cũ. Ba việc phải làm mới thật sự: (a) hàng chờ **cột trái cố
định** thay popup; (b) **ba mức** kiểm soát thay hai; (c) bám hợp đồng **`/api/xep-lich-2`** với luật
chạy-liên-tục + ngày-lễ-vẫn-xếp + cụm-NCC. Phần Gantt/preview/kéo-thả/panel-sticky thì kế thừa cơ chế.

---

## 2. CÂY COMPONENT + LƯỚI KHUNG

### 2.1 Cây component (mới, prefix `Xl2`)

```
XepLich2Page                         ← controller: state, fetch, SSE, quyền
├─ Xl2TopBar                         ← tìm kiếm + lọc + zoom + cửa sổ ngày
│   ├─ Xl2Search        (ô tìm LSX/bài/mã)
│   ├─ Xl2FilterChips   (máy · tổ · NCC · chưa xếp · có vấn đề · lệnh gấp)
│   ├─ Xl2ZoomToggle    (giờ · ca · ngày · tuần)
│   └─ Xl2WindowNav     (◀ 14 ngày ▶ · nhảy "Hôm nay")
├─ Xl2Body  (lưới 3 cột: hàng chờ | gantt | panel)
│   ├─ Xl2Queue                      ← CỘT TRÁI cố định
│   │   ├─ Xl2QueueBasket "Có thể xếp"   → n×Xl2QueueRow
│   │   └─ Xl2QueueBasket "Bị chặn"      → n×Xl2QueueRow (mờ, có lý do chặn)
│   ├─ Xl2Gantt                      ← GIỮA
│   │   ├─ Xl2GanttAxis  (trục thời gian; nền ca/lễ)
│   │   ├─ Xl2LaneCluster "Máy"   → n×Xl2Lane → n×Xl2Bar
│   │   ├─ Xl2LaneCluster "Tổ"    → n×Xl2Lane (+ nền tải người)
│   │   ├─ Xl2LaneCluster "NCC"   → n×Xl2Lane (thuê ngoài)
│   │   ├─ Xl2Park       (dải "chưa đặt giờ" cho bước đang kéo ra)
│   │   └─ Xl2GhostLayer (preview: bóng vị trí giả, KHÔNG ghi)
│   └─ Xl2Panel                      ← CỘT PHẢI sticky (không modal)
│       ├─ Xl2PanelHead   (LSX/bài + vị trí DAG + 2 hạn + đệm)
│       ├─ Xl2PanelDuration (3 mức thời lượng + nguồn tính)
│       ├─ Xl2PanelResource (máy/tổ/NCC + ca + tải)
│       ├─ Xl2PanelPeople   (số người kế hoạch + định biên + quân số tổ còn rảnh)
│       ├─ Xl2PanelMaterial (đã giữ / đang về / còn thiếu + ngày sớm nhất)
│       └─ Xl2IssueList     (danh sách 3-mức + liên kết "sua")
├─ Xl2Footbar                        ← DẢI CHÂN charcoal
│   ├─ Xl2FootCount ×3   (chặn đặt lịch · chặn phát hành · cảnh báo — bấm để nổi)
│   └─ Xl2ReleaseBtn     (phát hành theo LSX/bài đang chọn)
├─ Xl2PreviewDialog                  ← xác nhận preview → PUT
├─ Xl2RecallDialog                   ← thu hồi lịch đã phát hành (bắt lý do)
└─ Xl2ConflictDialog                 ← 409: hiện giá trị mới, cho tải lại
```

### 2.2 Lưới khung (CSS grid)

Tái dùng ý tưởng `.xlcd__grid.is-panel` của màn cũ nhưng **ba cột** (thêm hàng chờ trái cố định):

```
.xl2__grid {
  display: grid;
  grid-template-columns: minmax(280px, 320px)  minmax(0, 1fr)  minmax(340px, 440px);
  /*        hàng chờ (trái)         gantt (co giãn)     panel (phải)                 */
  gap: 0;                         /* các cột kề nhau, ngăn bằng viền 1px --rule-soft */
  height: calc(100dvh - <topbar> - <footbar>);
}
```

- **Top bar** và **foot bar** nằm ngoài grid (sticky trên/dưới), giống bố cục màn cũ.
- Mỗi cột **cuộn dọc độc lập** (`overflow-y:auto`); riêng cột Gantt cuộn được **cả ngang** (trục
  thời gian) — bọc trong `overflow-x:auto`, thân trang KHÔNG bao giờ cuộn ngang (luật `UI_DESIGN`).
- Trục thời gian và nhãn lane **dính** (`position:sticky` top / left) khi cuộn.
- **Thu gọn panel:** khi không chọn gì, cột phải hiện *empty state* mảnh (không ẩn cột, tránh layout
  nhảy — luật `content-jumping`). Có nút thu panel để nhường chỗ Gantt trên màn hẹp.
- **Responsive** (điều độ dùng laptop ≥1280 là chính): dưới 1180px → panel trượt thành lớp phủ phải
  (drawer) thay vì cột; dưới 900px → hàng chờ thu thành nút mở drawer trái. Không vỡ, không cuộn ngang.

Hằng số layout (kế thừa `GanttBoard`): `LABEL_W = 240` (bề rộng cột nhãn lane), `BAR_H = 26`.

---

## 3. TOKEN / SPACING / TYPOGRAPHY TÁI DÙNG + CLASS MỚI

### 3.1 Token màu (dùng NGUYÊN, không đẻ màu mới) — từ `UI_DESIGN.md`

| Vai trò | Token | Giá trị | Ghi chú |
| --- | --- | --- | --- |
| Nền màn / sau thẻ | `--paper` | `#f8fafc` | nền vùng trống |
| Mặt thẻ / bảng / ô | `--canvas` | `#ffffff` | thân hàng chờ, thân panel |
| Chữ chính / nền sidebar | `--ink` | `#0f172a` | tiêu đề, số |
| Chữ mờ | `--ash` | `#475569` | nhãn, meta |
| Chữ rất mờ | `--ash-2` | `#64748b` | gợi ý, placeholder |
| Viền ô/chip | `--rule` | `#cbd5e1` | |
| Viền thẻ / kẻ header | `--rule-soft` | `#e2e8f0` | ngăn 3 cột |
| Kẻ giữa hàng | `--rule-hair` | `#f1f5f9` | |
| Khối tối | `--charcoal` | `#0f172a` | dải chân, chip lọc đang chọn |
| **Accent** (chỉ 1) | `--rust` | `#c5400a` | nút primary · **viền phần tử đang chọn · vành focus** |
| Accent hover | `--rust-deep` | `#8a2d07` | |
| Bề mặt tô | `--rust-soft` | `#f4e2d6` | hover hàng · nền phần tử đang chọn |

**Màu ngữ nghĩa (đã có sẵn trong `xep-lich.css`, dùng lại — KHÔNG chế màu mới):**

| Họ | Token | Dùng cho ở v2 |
| --- | --- | --- |
| Đỏ | `--signal` / `--signal-soft` | **chặn đặt lịch** · trễ hạn · early-start |
| Xanh thép | `--steel` / `--steel-soft` | **chặn phát hành** (ổ khoá cửa phát hành) · đã khoá |
| Hổ phách | `--amber` / `--amber-soft` / `--amber-deep` | **cảnh báo** · sắp tới hạn · nền "chưa có máy" |
| Rêu | `--moss` / `--moss-soft` / `--moss-deep` | OK · đã giữ đủ vật tư · đã xử lý |
| Thang nhiệt | `--heat-1..4` | **chỉ** nền mức tải (đại lượng vô nghĩa/độ lớn), KHÔNG dùng cho status |

> Vì sao gán như trên xem §5. Điểm cốt: **`--rust` để yên cho accent** (chọn/focus), KHÔNG mượn rust
> làm một mức status trên thanh Gantt — nếu không, "thanh đang chọn" và "thanh chặn phát hành" sẽ
> đụng màu. Ba mức dùng ba HỌ khác nhau (đỏ / thép / hổ phách) + icon + chữ.

### 3.2 Spacing / bo góc / bóng

- Thang cách **4/8px** (luật `spacing-scale`). Gutter khối 12–16px, padding thẻ 12px.
- Bo góc: thẻ/panel 10px, pill r99, chip vuông-nhẹ 6px (theo `CategoryChip`/`NguyCoTreChip` sẵn có).
- Bóng **phẳng** (hệ đang dùng bóng rất nhẹ). Panel dính dùng **viền-trên 3px `--rust`** như
  `.xlcd-side__box` để báo "đây là ngữ cảnh đang chọn". KHÔNG đổ bóng nổi kiểu vật liệu.

### 3.3 Typography

- Chữ: **Be Vietnam Pro** (đang dùng toàn app). **JetBrains Mono chỉ cho SỐ** trong cột dữ liệu
  (giờ, số tờ, thời lượng, độ dư) — luật `number-tabular` để cột không nhảy.
- Thang cỡ: 11 · 11.5 · 12 · 14 · 16 · 18. Nhãn 11–11.5/600, thân 12–14/400, số nhấn 14/700.
- **Không** mono-IN-HOA cho nhãn tiếng Việt (bẫy đã ghi ở module Kế hoạch SX).

### 3.4 Primitive DÙNG CHUNG được phép tái dùng (`keHoachSxShared.tsx`)

Đọc trực tiếp, **đừng viết lại**:

| Hàm/Component | Chữ ký (tóm) | Dùng ở v2 |
| --- | --- | --- |
| `num(v)` | số → chuỗi có phân cách | mọi số |
| `ngay(v)` / `ngayGio(v)` | date / datetime → chuỗi | hạn (DATE ⇒ `ngay`), giờ chạy ⇒ `ngayGio` |
| `thoiLuong(phut)` | phút → "5h45" | thời lượng bar + panel |
| `classHan(dateStr)` / `classHanLich(...)` | class màu theo hạn | tô đỏ/hổ phách hạn |
| `ChuoiCongDoan({...})` | vẽ chuỗi DAG công đoạn | panel head |
| `EmptyState({...})` | khối rỗng có nhãn + hành động | mọi vùng trống |
| `Skeleton({rows,cols})` | khung xương khi nạp | hàng chờ / panel |
| `BangLoi({text,onRetry})` | khối lỗi + nút thử lại | mọi vùng lỗi |
| `boDoCua(issueKey)` | tiền tố issue_key → bộ dò | nhóm/điều hướng vấn đề |

> **KHÔNG tái dùng nguyên** `SevPill`/`XEP_LICH_SEV_META` vì nó chỉ có **2 mức**. Màn 2 cần **3 mức**
> ⇒ định nghĩa `Xl2MucPill` + `XL2_MUC_META` mới (§5). Vẫn giữ đúng phong cách pill (r99 · chấm/icon
> · luôn kèm chữ) cho nhất quán thị giác.

### 3.5 Prefix class mới

Tất cả CSS màn 2 nằm dưới **`.xl2-…`** (thân trang bọc `.xl2`). Không đụng `.xlcd-`. Đặt trong file
mới `frontend/src/pages/xep-lich-2.css` (BUILD tạo). Lý do: tránh bẫy tầng CSS (global.css bundle
cuối) và bẫy "sửa CSS không ăn vì trùng selector" đã ghi trong bộ nhớ dự án.

---

## 4. ĐẶC TẢ TỪNG VÙNG + ĐỦ TRẠNG THÁI

> Nhắc: Lát 1 dữ liệu backend **chưa đầy đủ**. Mọi vùng phải có trạng thái **"chưa có dữ liệu" tử
> tế** — KHÔNG vẽ số 0 giả như thể đã tính ra 0. Bốn trạng thái bắt buộc mỗi vùng: **nạp** (Skeleton)
> · **rỗng/chưa-có-dữ-liệu** (EmptyState có câu giải thích) · **lỗi** (BangLoi + thử lại) · **có dữ
> liệu**.

### 4.1 Top bar (`Xl2TopBar`)

- **Tìm kiếm**: ô search (icon `search`) lọc theo mã LSX/bài, tên khách. Gõ → lọc hàng chờ + làm
  nổi trên Gantt. Debounce ~250ms (luật `debounce-throttle`).
- **Chip lọc** (`Xl2FilterChips`): máy · tổ · NCC · *chưa xếp* · *có vấn đề* · *lệnh gấp*. Quy tắc
  chip theo `UI_DESIGN` §5: chip **đang chọn nền `--charcoal` chữ trắng** (KHÔNG phải rust). Mỗi chip
  hiện **số đếm** (facet) — bám bộ nhớ dự án "phân trang + lọc + số đếm ở MÁY CHỦ": số này lấy từ
  `GET /workspace`/`GET /queue`, KHÔNG đếm ở JS sau khi kéo cả bảng về.
- **Zoom** (`Xl2ZoomToggle`): 4 nấc *giờ · ca · ngày · tuần*. Toggle kiểu segmented, nấc đang chọn
  viền/nền theo accent. Mặc định **ngày** trong cửa sổ **14 ngày cuốn chiếu**.
- **Cửa sổ ngày** (`Xl2WindowNav`): ◀ ▶ dời 14 ngày; nút "Hôm nay". Hiện khoảng "18/08 – 31/08".
- *Trạng thái*: bar luôn hiển thị; khi `GET /workspace` đang nạp thì disable chip + hiện shimmer mảnh
  trên dải zoom (đừng để bar nhảy).

### 4.2 Hàng chờ trái (`Xl2Queue`) — hai rổ

Nguồn: `GET /queue` (phân trang, chia sẵn *có thể xếp* / *bị chặn* — spec §5, §9.2).

- **Rổ "Có thể xếp"**: LSX/bài routing + thời lượng hợp lệ (được tạo nháp dù vật tư chưa đủ). Mỗi
  hàng `Xl2QueueRow`:
  - Dòng 1: **mã** (LSX/`GB…` bài ghép, icon phân biệt `workflow`/`layers`) + tên khách + chip **GẤP**
    (icon `bell`) nếu `is_rush`.
  - Dòng 2 (meta, chữ `--ash`, số mono): **hạn SX** · **hạn giao** (tô theo `classHan`) · **vật tư**
    (chip trạng thái: đã đủ `--moss` / đang về `--amber` / thiếu `--signal`) · **"n/N công đoạn chưa
    xếp"**.
  - Đầu hàng: **thanh mức cao nhất** (viền trái 3px theo mức nặng nhất còn tồn — §5).
- **Rổ "Bị chặn"**: xem được, **mờ 0.6**, KHÔNG kéo được. Hiện **lý do chặn** (mã `muc=chan_dat_lich`
  + câu `cau`) và **liên kết `sua`** mở đúng module nguồn (vd thiếu tốc độ máy → mở Danh mục máy).
- **Chọn 1 hàng** → làm nổi **cả chuỗi** LSX/bài trên Gantt (spec §8) + đổ panel phải. Hàng đang chọn:
  nền `--rust-soft` + inset trái 3px `--rust` (đúng luật chọn của `UI_DESIGN`).
- *Trạng thái*:
  - **nạp**: `Skeleton rows=6 cols=2`.
  - **rỗng thật** (không còn gì chờ): `EmptyState` icon `check` — "Hết hàng chờ. Mọi LSX đã có lịch."
  - **chưa-có-dữ-liệu** (backend lát 1 chưa trả): `EmptyState` icon `help` — "Chưa nạp được hàng chờ
    từ máy chủ." + nút thử lại. **Đừng** hiện "0 lệnh" như kết luận.
  - **lỗi**: `BangLoi` + `onRetry`.
  - **cuối trang**: nút "Tải thêm" (phân trang máy chủ), KHÔNG cuộn-vô-tận âm thầm.

### 4.3 Gantt giữa (`Xl2Gantt`)

Nguồn: `GET /workspace` (lane · ca · lễ · quân số · tải · thanh trong cửa sổ).

- **Ba cụm lane** có tiêu đề cụm gập được: **Máy** (icon `printer`) · **Tổ** (icon `users`) · **Nhà
  cung cấp** (icon `truck`). Cụm NCC gom theo `nha_cung_cap` chuẩn hoá; chuỗi trống ⇒ lane **"Thuê
  ngoài — chưa rõ NCC"** (spec §6, §10.3).
- **Nền lane** (đọc, không kéo được): ca làm việc (nền nhạt) · **ngày lễ** (nền khác + nhãn tên lễ
  từ `special_days.name` — v2 VẪN cho xếp) · vùng máy hỏng/bảo trì `chan` (gạch chéo `--steel`) ·
  **tải người của tổ** (nền thang `--heat-1..4` theo % quân số).
- **Thanh việc** `Xl2Bar`:
  - Chiếm lịch theo **mức trung bình**; **râu** hai đầu = nhanh nhất ↔ chậm nhất. Máy chưa khai
    `toc_do_min/max` ⇒ **không vẽ râu**, ghi nhãn "chưa khai dải" (spec §3) — đừng vẽ râu 0.
  - Đoạn **setup** (makeready) tô nhạt đầu thanh; phần chạy tô đậm.
  - **Chạy liên tục qua cuối ca**: thanh KHÔNG bị cắt ở mép ca; phần tràn đêm vẫn liền khối (spec §3).
  - Bước **thuê ngoài**: thanh từ `start_at`→`finish_at`, KHÔNG có setup, KHÔNG chiếm máy/người; nằm
    trong cụm NCC.
  - **Chip mức** góc thanh (§5) + râu; nhãn mã LSX rút gọn, tooltip đầy đủ (luật `truncation-strategy`).
- **Dải Park** (`Xl2Park`): nơi chứa bước "chưa đặt giờ" khi người dùng kéo bước ra khỏi hàng chờ mà
  chưa thả vào lane — bám mô hình `xlcd-gpark`.
- **Preview** (`Xl2GhostLayer`): kéo/di một bước → vẽ **bóng vị trí giả** + gọi `POST /rows/{id}/preview`
  → hiện giờ kết thúc dự kiến · công đoạn bị ảnh hưởng · hạn mới · vấn đề mới. **Preview KHÔNG ghi**
  (spec §8/§9.2). Thả → mở `Xl2PreviewDialog` xác nhận rồi mới `PUT`.
- *Trạng thái*:
  - **nạp**: khung lane xám + shimmer trục.
  - **rỗng** (có lane, chưa có thanh nào trong cửa sổ): lane trống + câu mờ "Chưa có việc nào trong
    14 ngày này" — KHÔNG phải lỗi.
  - **chưa-có-dữ-liệu** (chưa có lane/ca): `EmptyState` icon `calendar` — "Chưa nạp được nền lịch
    (ca/máy/tổ) từ máy chủ." + thử lại.
  - **lỗi**: `BangLoi` phủ vùng Gantt + thử lại.

### 4.4 Panel phải (`Xl2Panel`) — sticky, không modal

Nguồn: `GET /context/{nguon}/{id}`. Chỉ hiện khi đã chọn 1 LSX/bài (hoặc 1 bước). Các khối (spec §8):

1. **Head**: mã LSX/bài + **vị trí trong DAG** (`ChuoiCongDoan`) + **hai hạn** (SX · giao khách) +
   **đệm** (số ngày dư, tô theo `classHanLich`).
2. **Ba mức thời lượng**: nhanh nhất / trung bình / chậm nhất + **nguồn tính** (vd "TB máy 6.000
   tờ/giờ · min 4.500 · max 7.500 · chuẩn bị 45'"). Nếu thiếu dải → ghi rõ "chưa khai dải".
3. **Tài nguyên**: máy / tổ / NCC + ca + **tải** hiện tại.
4. **Nhân lực**: số người **kế hoạch** + tham khảo **tối thiểu · tiêu chuẩn · tối đa** (KHÔNG phán
   xét) + **quân số tổ** khả dụng ngày đó và **phần còn rảnh**; nếu có dòng `to_quan_so_ngay` đè thì
   hiện **lý do** kèm.
5. **Vật tư**: đã giữ / đang về (kèm `ngay_ve`) / còn thiếu + **ngày sớm nhất** được bắt đầu.
6. **Danh sách 3-mức** (`Xl2IssueList`): mỗi vấn đề = `Xl2MucPill` + câu `cau` + nguồn `nguon` +
   ảnh hưởng `anh_huong` + **liên kết `sua`** (§5). Nhóm theo mức (chặn đặt lịch → chặn phát hành →
   cảnh báo).
- *Trạng thái*:
  - **chưa chọn gì**: `EmptyState` mảnh icon `maximize` — "Chọn một lệnh ở hàng chờ hoặc một thanh
    trên Gantt để xem chi tiết." (cột KHÔNG ẩn — tránh nhảy layout).
  - **nạp**: `Skeleton` trong khung panel.
  - **chưa-có-dữ-liệu từng khối** (vd chưa có vật tư): khối đó ghi "Chưa có dữ liệu vật tư" thay vì
    "0 kg" — mỗi khối tự chịu trạng thái riêng, đừng để một khối thiếu làm hỏng cả panel.
  - **lỗi**: `BangLoi` trong panel + thử lại (không sập cả trang).

### 4.5 Dải chân (`Xl2Footbar`) — charcoal

- **Ba số** (`Xl2FootCount`): "**N chặn đặt lịch** · **M chặn phát hành** · **K cảnh báo**", mỗi số
  có **chấm màu đúng mức** (§5). Bấm số → **làm nổi** đúng các thanh/LSX thuộc mức đó (cuộn tới +
  nhấp nháy 1 nhịp). Đây là cầu nối thay cho tab "Vấn đề" cũ.
- **Nút Phát hành** (`Xl2ReleaseBtn`): phát hành **độc lập theo LSX/bài đang chọn**. Disable khi còn
  `chan_phat_hanh`; hiện tooltip nêu lý do. Lịch đã phát hành **khoá**; muốn sửa phải **thu hồi có
  quyền + lý do** (`Xl2RecallDialog`) rồi phát hành lại (spec §8).
- *Trạng thái*: khi 3 số đều 0 **thật** (đã tính) → dải xanh nhạt "Không còn vướng mắc". Khi **chưa
  tính được** → hiện "—" mờ + tooltip "Chưa nạp được tổng vấn đề", KHÔNG hiện "0/0/0" giả.

---

## 5. BA MỨC KIỂM SOÁT — HIỆN THỐNG NHẤT Ở 4 VÙNG

Mỗi vấn đề trả về (spec §7): `muc` · `ma` · `cau` · `nguon` · `anh_huong` · `sua`.
`muc` ∈ **`chan_dat_lich`** | **`chan_phat_hanh`** | **`canh_bao`**.

> Ghi chú hợp đồng: task ban đầu từng nêu tên trường `{ ma, muc, mo_ta, nguon, goi_y }`. Bản
> **`spec-xep-lich-2.md` §7 là chuẩn**: dùng `cau` (câu người đọc) · `anh_huong` · `sua`. BUILD **hỏi
> backend chốt tên** trước khi map; nếu backend trả `mo_ta`/`goi_y` thì coi là alias của `cau`/`sua`.

### 5.1 Bảng gán màu · icon · nghĩa (ba HỌ khác nhau, rust để yên cho accent)

| Mức | Nghĩa | Họ màu (token) | Icon | Hệ quả |
| --- | --- | --- | --- | --- |
| `chan_dat_lich` | Không cho **lưu** dòng | **Đỏ** `--signal` / nền `--signal-soft` | `ban` | Nặng nhất |
| `chan_phat_hanh` | Lưu **nháp** được, **khoá cửa phát hành** | **Xanh thép** `--steel` / nền `--steel-soft` | `lock` | Trung bình |
| `canh_bao` | Cứ làm, **nên biết** | **Hổ phách** `--amber` / nền `--amber-soft` | `alert` | Nhẹ |

**Vì sao gán thế:**
- Đỏ = "chặn cứng, không đặt được" — trùng cách app đã dùng `--signal` cho trễ/xung đột.
- Xanh thép = "ổ khoá cửa phát hành" — app **đã** dùng `--steel` + icon `lock` cho trạng thái *đã
  khoá* (`.xlcd-lpill--khoa`, `.xlcd-chen__chan`). Nên `chan_phat_hanh` = "cửa phát hành đang khoá"
  ánh xạ tự nhiên vào steel + `lock`.
- Hổ phách = cảnh báo mềm — app đã dùng `--amber` cho *sắp tới hạn* / *chưa có máy*.
- **KHÔNG mượn `--rust`** cho bất kỳ mức nào: rust là màu **chọn/focus**, đặt lên thanh Gantt sẽ đụng
  "thanh đang chọn". Ba họ đỏ/thép/hổ-phách đủ tách và đều đã mang nghĩa sẵn.
- **Không chỉ-dựa-màu** (luật a11y): mỗi mức LUÔN đi kèm **icon + chữ nhãn** ("Chặn đặt lịch" / "Chặn
  phát hành" / "Cảnh báo"). Người mù màu vẫn phân biệt bằng icon `ban`/`lock`/`alert` + chữ.

Định nghĩa dùng chung (BUILD viết trong `xep-lich-2.css` + một map TS):

```
XL2_MUC_META = {
  chan_dat_lich:  { label: "Chặn đặt lịch",  icon: "ban",   cls: "xl2-muc--dat"  },
  chan_phat_hanh: { label: "Chặn phát hành", icon: "lock",  cls: "xl2-muc--ph"   },
  canh_bao:       { label: "Cảnh báo",       icon: "alert", cls: "xl2-muc--warn" },
}
// pill: <span class="xl2-mucpill {cls}"><Icon .../> {label}</span>   (r99, luôn có chữ)
```

### 5.2 Bốn vùng hiện mức NHƯ NHAU (nhất quán thị giác)

| Vùng | Cách hiện mức |
| --- | --- |
| **Hàng chờ** (`Xl2QueueRow`) | **Viền trái 3px** theo mức **nặng nhất** còn tồn của LSX/bài (đỏ > thép > hổ phách). Rổ "Bị chặn" = có `chan_dat_lich`. Meta hàng hiện `Xl2MucPill` nhỏ cho mức nặng nhất. |
| **Thanh Gantt** (`Xl2Bar`) | **Chip mức** ở góc thanh (icon + số vấn đề cùng mức). Viền thanh nhuốm nhẹ theo mức nặng nhất. Thanh có `chan_dat_lich` → viền đỏ đứt nét (chưa lưu được). |
| **Panel phải** (`Xl2IssueList`) | Danh sách **nhóm theo mức**, mỗi dòng `Xl2MucPill` + `cau` + `nguon` + `anh_huong` + liên kết `sua`. |
| **Dải chân** (`Xl2FootCount`) | **Ba số tổng** kèm chấm màu đúng mức; bấm → nổi các thanh/LSX của mức đó. |

Nhờ vậy một mức có **đúng một** {màu + icon + chữ} ở mọi nơi nó xuất hiện → người dùng học một lần,
đọc được ở cả bốn vùng.

### 5.3 "sua" = ĐIỀU HƯỚNG, không tự sửa (MÁY CHỈ GHI NHẬN)

`sua` cho biết **hành động + đích mở**. UI render thành **liên kết** (icon `link`/`chevron`) mở đúng
module nguồn — ví dụ:

| Mã (`ma`) | `sua` mở tới |
| --- | --- |
| `thieu_thoi_luong` / `thieu_quy_doi` | Danh mục **máy** / **công đoạn định mức** (khai tốc độ/năng suất/cầu quy đổi) |
| `trung_may` / `de_vung_khoa_may` | Kéo đổi khe trên **Gantt**, hoặc mở module **Kỹ thuật máy** (vùng hỏng/bảo trì — chỉ đọc) |
| `vuot_quan_so_to` | Màn **quân số tổ theo ngày** |
| `vat_tu_chua_du` / `vat_tu_chua_xac_dinh` / `vat_tu_chua_co_ngay` | Màn **Kế hoạch vật tư** / **Giữ chỗ** |
| `thieu_ca_hai_han` / `tre_han_sx` | Màn **Kế hoạch SX** (LSX) để sửa hạn; `tre_han_sx` mở **duyệt ngoại lệ** |
| `con_buoc_chua_xep` | Cuộn tới bước còn thiếu trong chính Gantt |

**Chỉ `tre_han_sx`** được **duyệt ngoại lệ kèm lý do** (spec §7.2) — nút này gate bằng bit
`approve_exception` (mg 0218). Các mã khác KHÔNG có nút "bỏ qua".

---

## 6. LUỒNG THAO TÁC CHÍNH

**F1 — Xếp một bước từ hàng chờ:**
1. Chọn LSX ở rổ *Có thể xếp* → chuỗi nổi trên Gantt + panel đổ.
2. Chọn 1 bước chưa xếp → Gantt gợi ý **tối đa 3 khe** (`POST /rows/{id}/suggestions`), ưu tiên
   tránh trễ/lệnh gấp trước, rồi mới gom giấy–khổ–bộ mực (spec §8).
3. Kéo bước vào khe (hoặc bấm 1 gợi ý) → **preview** (`POST …/preview`) vẽ bóng + hệ quả.
4. `Xl2PreviewDialog` xác nhận (nút: **Xếp vào đây** / **Tìm khe khác** / **Huỷ**) → `PUT /rows/{id}`
   kèm `expected_updated_at`.
5. Thành công → SSE làm mới; thất bại 409 → `Xl2ConflictDialog` (§7).

**F2 — Tạo lịch nháp cả LSX:** chọn LSX → "Tạo lịch nháp" (`POST /entities/{nguon}/{id}/draft`) →
khoá routing, sinh các bước ở Park/khe gợi ý → người tinh chỉnh từng bước như F1. Gỡ nháp:
`DELETE …/draft` (chỉ khi chưa phát hành).

**F3 — Phát hành:** khi panel không còn `chan_phat_hanh` → `Xl2ReleaseBtn` bật →
`POST /{nguon}/{id}/release`. Gate chạy ở **`release.py` dùng chung** (spec §9.3) nên không vượt luật.

**F4 — Thu hồi & sửa lịch đã phát hành:** `Xl2RecallDialog` bắt **lý do** → `POST …/recall` (cần bit
`approve`) → lịch mở khoá để sửa → phát hành lại.

**F5 — Duyệt ngoại lệ trễ hạn:** với `tre_han_sx`, nút "Duyệt ngoại lệ" (bit `approve_exception`) mở
ô nhập lý do → ghi vào `xep_lich_van_de` (dùng chung `issue_key` với màn cũ — spec §10.4).

**F6 — Điều hướng sửa nguồn:** bấm liên kết `sua` ở panel/hàng chờ → `navigate(...)` sang module
nguồn (không rời mạch: mở cùng cây điều hướng AppShell, focus đúng bản ghi).

---

## 7. REAL-TIME (eventTick / SSE `xep_lich_changed`)

- `XepLich2Page` nhận prop **`eventTick`** (giống mọi màn qua AppShell = `quoteTick`) và **`onBadgeStale`**.
- SSE qua **`connectQuoteEvents(token, onEvent)`** trong `api/client.ts` (fetch + ReadableStream vì
  EventSource không set được Authorization). Nghe **`xep_lich_changed`** (+ `lsx_changed` /
  `bai_ghep_changed`).
- Khi nhận sự kiện: **nạp lại** workspace + hàng chờ + panel đang mở, cập nhật **3 số dải chân** và
  **badge** — **KHÔNG bắt refresh, KHÔNG đổi màn** (luật sản phẩm "gửi/thông báo nội bộ = real-time").
- Mọi mutation ở v2 phải khiến backend `hub.broadcast({"type":"xep_lich_changed"})` (spec §9.2) — hai
  màn (cũ + 2) cùng nghe, cùng nhảy. Đây là **kịch bản test bắt buộc #11**.
- **Chống nhảy khi đang kéo**: nếu đang trong thao tác kéo-thả (`Xl2GhostLayer` active), **hoãn**
  áp cập nhật SSE tới khi thả xong, để bóng preview không bị giật (giữ mượt `gesture-feedback`).

---

## 8. A11Y

- **Bàn phím kéo-thả** (bắt buộc, kế thừa `onBarKey`): thanh nhận focus (`tabindex`), **mũi tên
  trái/phải** dời theo bước lưới thời gian, **lên/xuống** đổi lane, **Enter** = preview, **Enter lần
  2** = xác nhận, **Esc** = huỷ (luật `keyboard-shortcuts`: kéo-thả luôn có đường bàn phím thay thế).
- **Focus thấy rõ**: vành focus `--rust` 2–3px, **không** gỡ outline (luật `focus-states`).
- **aria**: mỗi thanh `role="button"` + `aria-label` đọc "LSX … · máy … · bắt đầu … · thời lượng …
  · mức cao nhất: Chặn phát hành". `Xl2IssueList` dùng `aria-live="polite"` để khi có vấn đề mới do
  SSE, trình đọc màn hình xướng lên. Dialog (`Xl2PreviewDialog`/`Recall`/`Conflict`) bẫy focus + `Esc`
  đóng + tiêu đề `role="dialog" aria-modal`.
- **Không chỉ-dựa-màu**: mọi mức/trạng thái luôn kèm icon + chữ (§5). Chip vật tư, chip mức đều có
  nhãn.
- **Tương phản** (đã kiểm trong `UI_DESIGN` §, đạt AA): `--ink`/`--canvas` 17.85:1; `--signal`/
  `--canvas` 5.11:1; `--rust`/`--canvas` 5.11:1; chữ trên `--charcoal` (dải chân) 17.06:1. Nền tải
  dùng thang nhiệt: **bậc 3 phải dùng chữ `--ink`**, bậc 4 dùng `--paper-contrast` (bẫy đảo chiều
  tương phản đã ghi trong `UI_DESIGN`).
- **Số dạng bảng**: cột giờ/thời lượng/độ dư dùng mono tabular để không nhảy (luật `number-tabular`).
- **Vùng cuộn**: mỗi cột cuộn riêng, tránh nested-scroll cướp cuộn chính (luật `scroll-behavior`);
  thân trang không cuộn ngang.
- **Reduced motion**: nhấp-nháy "làm nổi" khi bấm số dải chân phải tôn trọng `prefers-reduced-motion`
  (đổi sang đổi-viền tĩnh).

---

## 9. GHI CHÚ BÀN GIAO CHO AGENT BUILD

### 9.1 File tạo mới

| File | Vai trò |
| --- | --- |
| `frontend/src/pages/XepLich2Page.tsx` | Controller: state, fetch `/api/xep-lich-2`, SSE, quyền, dựng lưới 3 cột. |
| `frontend/src/pages/Xl2Gantt.tsx` (tách nếu lớn) | Gantt + lane cluster + bar + ghost + preview. |
| `frontend/src/pages/xep-lich-2.css` | Toàn bộ style prefix `.xl2-`. **KHÔNG** đụng `xep-lich.css`. |
| (map TS) `XL2_MUC_META` + `Xl2MucPill` | Đặt trong `keHoachSxShared.tsx` **hoặc** file riêng — 3 mức, dùng chung nếu màn khác cần. |

Tái dùng từ `keHoachSxShared.tsx`: `num`, `ngay`, `ngayGio`, `thoiLuong`, `classHan`, `classHanLich`,
`ChuoiCongDoan`, `EmptyState`, `Skeleton`, `BangLoi`, `boDoCua`. **Đọc** `GanttBoard.tsx` để kế thừa
cơ chế kéo-thả (`onBarDown/Move/Up`, `tryGan`, `onBarKey`, `LABEL_W`, `BAR_H`) — viết lại dưới `.xl2-`.

### 9.2 Nối vào khung app

- **AppShell** (`frontend/src/components/AppShell.tsx`): thêm nhánh
  `case "xep-lich-cong-doan-2": return <XepLich2Page navigate={navigate} eventTick={quoteTick}
  onBadgeStale={reloadBadges} focusLsxMa={navParams?.focusLsxMa ?? null} />;` — đặt **ngay dưới**
  `case "xep-lich-cong-doan"` (dòng ~1048). Prop **giống hệt** màn cũ để nhất quán.
- **Sidebar** (`frontend/src/components/Sidebar.tsx`): thêm mục trong nhóm `san-xuat`, **ngay dưới**
  "Xếp lịch công đoạn":
  `{ id: "xep-lich-cong-doan-2", label: "Xếp lịch công đoạn 2", icon: "calendar", module: "xep_lich_2" }`.
  (icon `calendar` để cùng họ với màn 1; nếu muốn phân biệt có thể `workflow`.)
- **Badge**: đăng ký badge cho id mới, cập nhật khi nhận `xep_lich_changed` (giống màn cũ). Badge
  **chỉ nạp một lần** khi vào màn rồi để SSE đẩy (bám commit gần nhất "badge chỉ nạp một lần").
- **Gate quyền**: bọc bằng `useCan("xep_lich_2", "view")`; nút Phát hành/Thu hồi/Duyệt-ngoại-lệ gate
  bằng các bit `approve` / `approve_exception` của module `xep_lich_2` (mg **0218** chép từ
  `xep_lich`). Người có `xep_lich` **không** tự động thấy màn 2 — đây là **cửa pilot riêng** (spec §11).

### 9.3 API client (`frontend/src/api/client.ts`)

Thêm nhóm hàm gọi `/api/xep-lich-2` (spec §9.2) — đề xuất `api.xepLich2.*`:
`workspace(params)`, `queue(params)`, `context(nguon,id)`, `draft(nguon,id)`, `deleteDraft(nguon,id)`,
`suggestions(rowId)`, `preview(rowId,body)`, `putRow(rowId, body /*kèm expected_updated_at*/)`,
`release(nguon,id)`, `recall(nguon,id,{ly_do})`. `nguon ∈ "lsx" | "bai_ghep"`.
**Xử lý 409**: khi `PUT`/`release` trả 409 → không ghi đè, mở `Xl2ConflictDialog` với giá trị mới
(kịch bản test #9).

### 9.4 Ranh giới KHÔNG làm (spec §11 — đừng vượt)

- **KHÔNG** gỡ/sửa màn cũ (`XepLichPage`, `GanttBoard`, `XepLichVanDeView`) — chúng vẫn chạy.
- **KHÔNG** đẻ bảng/cột lịch mới; chỉ có **1 migration quyền** (0218). Số dẫn xuất **tính lúc đọc**.
- **KHÔNG** gọi `_may_fit` / không kết luận theo khổ · số màu · gsm (spec §6, test #8).
- **KHÔNG** reset/checkout/commit/push. **KHÔNG** hợp nhất quyền, không đổi route/menu **cũ**.
- Đây là bản **thiết kế**; agent BUILD mới là người viết React/CSS. Sau khi build: chạy
  `styleseed-design-review` rồi `dev-browser` verify (theo CLAUDE.md), và verify BE bằng lệnh chuẩn dự án.

### 9.5 Đối chiếu 12 kịch bản test (spec §12) ↔ UI

| # | Kịch bản | UI phải thể hiện |
| --- | --- | --- |
| 1 | Bắt đầu trong ca, kết thúc sau cuối ca | Thanh liền khối tràn mép ca, không cắt (§4.3). |
| 2 | Ngày lễ vẫn xếp | Nền lễ + nhãn tên lễ, vẫn kéo được (§4.3). |
| 3 | Máy hỏng giữa khoảng chạy ⇒ chặn | `chan_dat_lich` `de_vung_khoa_may` đỏ + `ban` (§5). |
| 4 | Ba việc cùng tổ vượt quân số ⇒ chặn | `vuot_quan_so_to` đỏ; nền tải tổ chuyển bậc cao. |
| 5 | Kéo qua nửa đêm | Thanh liền, không báo lỗi. |
| 6 | Vật tư 4 trạng thái | Chip vật tư moss/amber/signal + mức `chan_phat_hanh` thép khi chưa đủ. |
| 7 | LSX thường/gấp/bài nhiều nhánh/thuê ngoài | Chip GẤP; cụm NCC; bài toả nhánh trong `ChuoiCongDoan`. |
| 8 | Không còn kết luận theo khổ/màu/gsm | Không có chip/màu nào theo các tiêu chí đó. |
| 9 | Hai người sửa 1 dòng ⇒ 409 | `Xl2ConflictDialog` (§7, §9.3). |
| 10 | Phát hành màn cũ không vượt gate v2 | Gate dùng chung `release.py`; UI không cần làm gì thêm. |
| 11 | SSE cập nhật không refresh | eventTick + `xep_lich_changed` (§7). |

---

## 10. REDESIGN BỐ CỤC — chốt 2026-08-19 (sau khi soi LIVE bằng ui-ux-pro-max)

> Bản build đầu (3 cột ngang hàng) đã chạy thật và **lộ rõ khi soi ảnh chụp live**: chật, không rõ
> mục đích, thanh Gantt illegible. User chốt lại **mục đích màn = BÀN PHÂN BỔ VIỆC → MÁY·GIỜ**
> (không phải bảng trình chiếu). Mọi thay đổi dưới đây phục vụ đúng mục đích đó. **Chỉ FE** — hợp
> đồng API v2 và 5 field dẫn xuất (`lsx_ma/bai_ghep_ma/ten_san_pham/cong_doan_ten/buoc_thu_tu`) đã có.

### 10.1 Bốn lỗi GỐC phải khử (lỗi bố cục/mật độ, không vá vặt)
1. **Ba cột ngang hàng** ⇒ Gantt (cái chính) bị bóp, cột phải rỗng chiếm 440px (chỗ đắt nhất).
2. **Thanh illegible ở zoom Ngày**: `showCd` chỉ hiện tên công đoạn khi bar ≥128px; bar ~90px ⇒ chỉ
   còn mã, mà mã trùng tiền tố `LSX26-`/`GB26-` ⇒ mọi thanh nhìn giống hệt.
3. **Ba mảng trắng** (cột phải rỗng + nửa dưới bàn + trục thời gian trống) ⇒ nhìn như chưa tải xong.
4. **Trọng số đảo**: thẻ hàng chờ to full-width, thanh lịch thật nhỏ/cụt. Màu phẳng xám-trên-trắng,
   mức "chặn phát hành" tô xám còn **chìm hơn** cảnh-báo-vàng.

### 10.2 Bố cục mới — "một mặt bàn + hai ngăn gọi-khi-cần"
- **Gantt = mặt bàn full-width** khi rảnh.
- **Cột phải: co về width 0 khi CHƯA chọn**, bung ra khi chọn 1 việc (đẩy Gantt hẹp lại); màn hẹp
  (<1180px) thì trượt đè như drawer. ⇒ hết 440px trắng nằm chờ. *(User chốt: "co về 0", KHÔNG phải
  drawer luôn, KHÔNG phải đổ tóm tắt xung đột.)*
- **Hàng chờ = rail trái dòng-gọn** (bỏ thẻ to full-width): mã badge + pill mức + hạn + chip gấp trên
  MỘT hàng; nút hành động ẩn, hiện khi hover/chọn. Rail **gập được** về icon. Lọc/đếm ưu tiên
  server-side; nếu API `hangCho` chưa hỗ trợ tìm/lọc thì làm **client-side trên tập đã nạp** (hàng chờ
  = tập "sẵn sàng chưa xếp", thường nhỏ) — **KHÔNG mở rộng backend** trong lượt này; nếu thấy buộc phải
  đụng BE thì DỪNG và báo.
- **Khay "CHƯA ĐẶT GIỜ" = dải ngang đáy bàn Gantt** — nguồn kéo-thả lên máy/giờ (đây chính là "việc
  cần phân bổ", đúng mục đích màn); đồng bộ hai chiều với rail trái. Thay cho lane đóng-gói lệch nhịp cũ.

### 10.3 Nhãn thanh — đọc được ở MỌI zoom (đổi chiến lược, không nới ngưỡng)
- **Bỏ tiền tố năm** trên thanh: hiện `0012 · Bế xén` (serial + công đoạn), mã đầy đủ ở tooltip/aria.
  Rút serial từ `lsx_ma`/`bai_ghep_ma` (phần sau dấu `-`); thiếu thì rơi về `#id`.
- Thanh đủ rộng: nhãn 2 phần trong thanh. **Thanh quá hẹp: nhãn TRÀN ra bên phải thanh** (không clip,
  không giấu) — bỏ hành vi cắt cứng `showCd` ở 128px.
- Giữ **mặc định zoom "Ngày"** + thêm nút **"Vừa khít"** (fit-to-content: tự chọn zoom theo mật độ việc
  trong cửa sổ). *(User chốt phương án nút vừa-khít, KHÔNG đổi mặc định sang Ca.)*
- "Râu" canh/chạy/khác: vẽ khi bar đủ rộng; dưới ngưỡng gộp 1 vạch màu.

### 10.4 Màu 3 mức — chốt ĐỎ · CAM · VÀNG NHẠT
| Mức | rank | Màu (token) | Ghi chú |
| --- | --- | --- | --- |
| Chặn đặt lịch | 3 | **`--signal`** (đỏ) | nặng nhất |
| Chặn phát hành | 2 | **cam/hổ phách đậm** (`--heat-*`/`--rust` họ cam đậm — KHÔNG dùng `--steel` xám nữa) | phải NỔI hơn cảnh báo |
| Cảnh báo | 1 | **vàng nhạt** | nhẹ nhất |

Quy tắc: đỏ = chặn cứng, cam = chặn phát hành, vàng nhạt = nhắc. **`--rust` chỉ dành cho viền
chọn/focus**, không bao giờ làm màu trạng thái. Chọn token cam đậm sẵn có trong `tokens.css`, không hex trần.

### 10.5 Thêm/sửa vặt cùng lượt
- **Top-bar**: thêm ô Tìm + dải chip lọc `Tất cả · Trễ · Chưa giờ · Xung đột` (có đếm facet); đưa CTA
  thật **"Phát hành"** lên top-bar (đang chôn trong dải digest). Mượn `OTim` + `.seg`/`chip-count` của
  mẫu đã ưng `pages/danh-muc/CatalogListPage.tsx` (charcoal = lọc đang chọn, rust = hành động).
- **Đếm số hết mập mờ**: cluster head ghi rõ `MÁY · 3 máy · 12 việc` (tách "số làn" vs "số việc");
  digest & cluster head **dùng chung một hàm đếm** để không lệch. Số dùng `--ff-num` tabular.
- **Empty/skeleton phân biệt** theo mẫu Danh mục (chưa-có / lọc-không-ra / tải-hỏng).
- Flowrail 3 bước: giữ nhưng thu gọn, không chiếm dải ngang riêng tốn chiều cao.

### 10.6 Ánh xạ Phase 4 (không bỏ tính năng nào)
overlay ca/lễ/khoá-máy/nhiệt-tải/đỉnh-quân-số → giữ dưới mặt bàn & đáy lane · "râu"+whisker → trong
thanh khi đủ rộng · **xoá-nháp + gợi-ý-≤3-khe → nút trong cột-phải (drawer) + trên dòng hàng chờ** ·
kéo-thả + PreviewImpactDialog + Undo → trên mặt bàn, khay "chưa đặt giờ" là nguồn kéo.

### 10.7 Ràng buộc build
Chỉ 4 file FE: `XepLich2Page.tsx`, `Xl2Gantt.tsx`, `xl2Shared.tsx`, `xep-lich-2.css`. Token-only (không
hex trần, không `:root` mới). Giữ real-time (eventTick/SSE), 3 mức, mô hình "máy chỉ ghi nhận". Không
migration, không đụng schema. Verify: `npx tsc --noEmit` EXIT 0 → styleseed ≥80 → soi LIVE trên browser.

---

*Hết. File này chỉ mô tả thiết kế; không chứa React/CSS thật (chỉ pseudo/khung ngắn). Agent BUILD
triển khai theo đây, hỏi backend chốt tên trường issue (`cau`/`sua` vs `mo_ta`/`goi_y`) trước khi map.*
