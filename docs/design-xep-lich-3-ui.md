# Thiết kế UI — Xếp lịch 3 (một hàng một LỆNH)

> Đi kèm `spec-xep-lich-3.md` (nghiệp vụ + API). File này chỉ nói UI: bố cục, component, token,
> tương tác, bẫy. Bản phác thảo đã nghiệm: `docs/mockups/xep-lich-3.html` (mở trực tiếp bằng
> trình duyệt, tự chứa, không cần dev server).
> Anh em: `design-thuc-hien-san-xuat-ui.md` (khuôn tài liệu này), `spec-xep-lich-2.md` (màn bị ẩn).

---

## 1. Bối cảnh — cái gì đã có, cái gì dựng mới

Màn `xep_lich_2` bị **ẩn đường vào** (cờ ở `constants/features.ts`), code giữ nguyên. Màn 3 dựng
mới hoàn toàn ở FE: **không sửa** `XepLich2Page.tsx` · `Xl2Gantt.tsx` · `xl2Shared.tsx` ·
`xep-lich-2.css`.

Đơn vị trên Gantt đổi từ **công đoạn** sang **LỆNH**: một lệnh một hàng một thanh. Người dùng chỉ
còn một hành động — đặt/dời **giờ bắt đầu**; mọi số khác là dẫn xuất.

---

## 2. Soi precedent — bê cái gì, TRÁNH cái gì

### 2.1. `Xl2Gantt.tsx` — bê cơ chế kéo, bỏ phần còn lại

**BÊ**: khuôn `DragState` + `pointerdown` → `pointermove`/`pointerup`/`pointercancel` gắn trên
`window` qua một `AbortController` (`{ signal }`), cờ `draggedRef` để cú `click` sau khi kéo không
bị hiểu là "chọn". Đây là phần đã chạy ổn và khó viết lại cho đúng.

**TRÁNH**: lane theo máy · cụm (`Xl2Cluster`) · overlay band vấn đề · gợi ý khe · tách/gộp phân
đoạn · `Xl2Patch` nhiều trường. Màn 3 chỉ có **một** trường patch (`bat_dau_at`).

### 2.2. `keHoachSxShared.tsx` — kho mảnh dùng lại NGAY

`num` · `ngay` · `ngayGio` · `conLai` · `classHan` · `thoiLuong` · `thoiLuongNgan` ·
`TrangThaiPill` · `ChipGap` · `NguyCoTreChip`. Không viết lại định dạng ngày/giờ/số ở màn 3.

### 2.3. `xl2Shared.tsx` — thang thời gian: ĐỌC rồi COPY, đừng import

`buildLinearScale` · `XL2_PX_PER_MIN` · `ngayToWall` · `wallToNaive` giải đúng bài toán thang, nhưng
`xl2Shared` thuộc module **đang bị ẩn và sẽ gỡ**. Copy bốn hàm này vào `xl3Shared.tsx` (tổng ~40
dòng) thay vì import chéo — nếu không, ngày gỡ xl2 là màn 3 chết theo.

---

## 3. Bố cục màn — bốn tầng, trên xuống dưới

```
┌ Đầu màn ────────────────────────────────────────────────────────────────┐
│ Xếp lịch lệnh sản xuất                  [Tuần][2 tuần][Tháng] (Hôm nay) │
│ Đặt giờ bắt đầu cho cả lệnh — ngày kết thúc tự ra.                      │
│ Mỗi dòng 1 lệnh, kéo thanh để đổi mốc.  [‹ 7 ngày][10/09/2026][7 ngày ›]│
├ Dải số liệu (một hàng, VĂN XUÔI + số) ──────────────────────────────────┤
│ 4 lệnh trong cửa sổ · 2 chờ xếp · Cửa sổ 10/09→16/09 · Giờ chạy trong   │
│ cửa sổ 41h30 · Trễ hạn SX 1 · Ca sản xuất 06:00–22:00, nghỉ 11:00–12:00 │
├──────────────┬──────────────────────────────────────────────────────────┤
│ HÀNG CHỜ     │ GANTT — trục dọc là LỆNH                                 │
│ (242px)      │ ┌ nhãn hàng 264px ┬ N cột ngày (minmax(dmin,1fr)) ─────┐ │
│ thẻ kéo được │ │ LSX26-0089 [gấp]        SM74 │  T5 T6 T7 CN T2 …    │ │
│ · mã         │ │ Vỏ hộp Tết Kinh Đô (đủ)      │ ▓▓░▓▓▓░░░▓▓ xong …   │ │
│ · tên        │ │ CTCP Kinh Đô …    [TRỄ HẠN]  │      ┆hạn SX  ┊khách  │ │
│ · khách      │ │ 12.000 cái · 3.240 tờ · 4/tờ │ ‹▓▓░░  (cắt mép)     │ │
│ · hạn SX     │ └──────────────────────────────┴──────────────────────┘ │
│ · giờ chạy   │ Chú giải: máy chạy · nghỉ/ngoài ca · hạn SX · trễ hạn · │
│              │ ‹ › ra ngoài cửa sổ                                     │
├──────────────┴──────────────────────────────────────────────────────────┤
│ PANEL CHI TIẾT của lệnh đang chọn — 12 ô + băng lưu ý + bảng công đoạn  │
└─────────────────────────────────────────────────────────────────────────┘
```

Bố cục này là bản **gộp**, chốt 10/09/2026 sau khi người dùng xem cả hai phác thảo và nói "kết hợp
cả 2":

- **Giữ của bản đã chốt trước**: đầu màn hai dòng (tiêu đề + câu mục tiêu), bộ thu phóng
  `[Tuần][2 tuần][Tháng]` + nút **Hôm nay** ở góc phải, và **dải số liệu VĂN XUÔI** chạy hết bề
  ngang dưới đường kẻ — đọc thành câu, kể cả dòng "Ca sản xuất 06:00–22:00, nghỉ…" (dòng này giải
  thích mọi khoảng nhạt trên thanh nên phải nằm ngay đầu màn, đừng đẩy xuống chú giải).
- **Thêm từ ảnh Gantt tham chiếu**: phân trang cửa sổ `‹ N ngày` · ô chọn ngày · `N ngày ›`; nhãn
  hàng mang **máy canh phải** + **chip `TRỄ HẠN`** + tình trạng vật tư trong ngoặc; cột cuối tuần
  tô nền; mũi tên `‹ ›` khi thanh chạy ra ngoài cửa sổ; ô ngày **hôm nay** đánh dấu.
- **Không lấy của bản tham chiếu**: thanh trơn một lớp. Thanh của ta vẫn **hai lớp** vì bàn này để
  **xếp** chứ không chỉ để tra — khoảng nhạt giữa các khối là nghỉ/ngoài ca, là thông tin.

Panel chi tiết **nằm dưới, luôn hiện** (không phải drawer trượt): nó là nơi đọc, không phải nơi sửa,
và người điều độ so nó với thanh phía trên liên tục — drawer che mất Gantt là phản tác dụng.

Dưới **900px**: hàng chờ tụt xuống thành một dải trên Gantt (một cột). Khung Gantt luôn
`overflow-x: auto`.

**Bộ lái cửa sổ** (`Xl3ThanhLai`, nằm trong `XepLich3Page.tsx`) có **hai** trục, đừng lẫn:

| Trục | Điều khiển | Việc |
|---|---|---|
| Độ DÀI cửa sổ (thu phóng) | `[Tuần][2 tuần][Tháng]` | 7 / 14 / 30 ngày. Đổi mức thì **giữ TÂM** cửa sổ (`W0 = round(tâm cũ − N/2)`), không giữ mép trái — giữ mép trái làm nội dung nhảy đi mất. |
| VỊ TRÍ cửa sổ | `‹ N ngày` · `input[type=date]` · `N ngày ›` · pill **Hôm nay** | Hai mũi tên nhảy **trọn một cửa sổ** (`W0 ± N`), nhãn nút đổi theo mức đang chọn. Ô ngày trỏ ngày **ĐẦU** cửa sổ. **Hôm nay** đưa cửa sổ về ngày hiện tại. |

Mỗi lần đổi (cả hai trục) ⇒ gọi lại `GET /lich?tu=&den=`; **cấm cắt trong JS** (xem
`phan-trang-loc-o-may-chu`). Bề rộng tối thiểu một cột ngày và `min-width` của khung đổi theo mức:

| Mức | Số ngày | `--xl3-day-min` | `min-width` khung | 15 phút ≈ |
|---|---|---|---|---|
| Tuần | 7 | 110px | 264 + 7×110 = **1034px** | 1,1px |
| 2 tuần | 14 | 72px | 264 + 14×72 = **1272px** | 0,75px |
| Tháng | 30 | 40px | 264 + 30×40 = **1464px** | 0,4px |

Cột càng hẹp thì kéo chuột càng thô — xem §8, và đó là lý do bàn phím/ô giờ là đường chốt chính xác.

**Chỉ vẽ hàng của lệnh CHẠM cửa sổ.** Máy chủ đã lọc theo `tu`/`den` nên FE không được đẻ thêm hàng
trống không thanh. Ngoại lệ duy nhất: lệnh **đang bị kéo** luôn được vẽ, kể cả khi vừa bị đẩy ra
ngoài mép — hàng biến mất dưới con trỏ là đứt mạch kéo.

---

## 4. Component + trách nhiệm + tên file dự kiến

| File | Trách nhiệm |
|---|---|
| `pages/XepLich3Page.tsx` | khung + state + gọi API + quyền + SSE. KHÔNG vẽ thanh. |
| `pages/Xl3Gantt.tsx` | lưới ngày · thanh hai lớp · hai vạch hạn · kéo thả. Nhận `dong[]` + `onDoiMoc`. |
| `pages/Xl3HangCho.tsx` | cột trái: tìm · phân trang · thẻ kéo được. |
| `pages/Xl3ChiTiet.tsx` | panel 12 ô + băng lưu ý + bảng công đoạn + nút Phát hành. |
| `pages/xl3Shared.tsx` | hằng số bề rộng/chiều cao · thang thời gian (copy §2.3) · gom `MAU_BUOC`. |
| `pages/xep-lich-3.css` | scope `.xl3`, biến cục bộ. |
| `api/xepLich3.ts` | 7 endpoint của `spec-xep-lich-3.md` §6. |

---

## 5. Ánh xạ API → UI (bám schema, không bịa field)

**Thẻ hàng chờ** ← `GET /hang-cho`: `ma` · `ten` · `customer_name` · `han_hoan_thanh_sx` ·
`is_rush` · `so_to_ke_hoach` · tổng giờ chạy.

**Nhãn hàng Gantt** ← `GET /lich`: `ma` · `is_rush` · `ten` · `customer_name` · `so_luong_dat` +
`don_vi_tinh` · `so_to_ke_hoach` · `so_con`.

**Thanh** ← cùng dòng: `bat_dau_at` · `ket_thuc` (dẫn xuất) · `segs[]` (`{a, b, i}` — mốc đoạn chạy
+ chỉ số bước) · `han_hoan_thanh_sx` · `han_giao_khach`.

**Panel 12 ô** ← `GET /lenh/{id}`: `customer_name` · `order_no` + `customer_po_no` · `sale_name` ·
`so_luong_dat`/`don_vi_tinh`/`so_to_ke_hoach`/`so_con` · giấy + định lượng và khổ tờ in (đọc trong
`quy_cach_json`) · số màu + `so_kem` (cũng `quy_cach_json`) · `han_hoan_thanh_sx` ·
`han_giao_khach` · `nguoi_phu_trach_ten` · lịch (bắt đầu → kết thúc) · giờ chạy + giờ nghỉ/ngoài ca ·
kíp chuẩn cả lệnh (Σ `so_nhan_cong_tieu_chuan`).

**Chip đầu panel**: `is_rush` → "Lệnh gấp"; so `ket_thuc` với `han_hoan_thanh_sx` → "Trong hạn" /
"Trễ hạn SX"; `giu_cho_bat` + tóm tắt giữ chỗ → "Giữ đủ 100%" / "Thiếu N mặt hàng" / "Chưa bật giữ chỗ".

**Băng lưu ý** ← `luu_y_gui_xuong` (chỉ hiện khi có).

**Bảng công đoạn** ← `cong_doans[]`: `ten` · máy/tổ (`may_ten` hoặc tên tổ, `nha_cung_cap` nếu thuê
ngoài) · `so_luong_vao` + `don_vi_vao` · `so_nhan_cong_tieu_chuan` · giờ chạy (`chiem_may_phut`).
**Không có cột mốc bắt đầu/kết thúc.**

`quy_cach_json` là ảnh chụp — đọc phòng thủ, khoá nào trống thì **bỏ ô đó**, không bịa nhãn.

---

## 6. Token / màu / spacing (bám `styles/tokens.css`, CẤM hex thô)

Bọc `.xl3`, biến cục bộ đặt trên `.xl3` (không thêm `:root`). Bản mockup dùng hex thô vì nó phải
chạy độc lập ngoài repo — **code thật không được bê hex đó vào**.

| Vai trò | Token |
|---|---|
| Nền trang / nền thẻ | `--paper` / `--canvas` |
| Chữ chính / mờ / rất mờ | `--ink` / `--ash` / `--ash-2` |
| Đường kẻ | `--rule` / `--rule-soft` / `--rule-hair` |
| Accent (thanh đang chọn, nút Phát hành) | `--rust` / `--rust-deep` / `--rust-soft` |
| Font chữ / font SỐ-MÃ | `--ff-sans` / `--ff-num` + `font-variant-numeric: tabular-nums` |
| Cỡ chữ | `--fs-2xs`…`--fs-xl`; đậm `--fw-medium` / `--fw-bold` |
| Giãn cách | `--sp-1`…`--sp-8` |
| Bo góc | `--r-2` / `--r-3`; pill `--r-pill` |

Biến cục bộ `.xl3`: `--xl3-label-w: 264px` · `--xl3-bar-h: 30px` · `--xl3-row-h: 80px`; còn
`--xl3-day-min` và số ngày **đổi theo mức thu phóng** (bảng ở §3) nên đặt bằng JS lên phần tử khung,
không đóng cứng trong CSS. Nhãn hàng 264px và hàng 80px vì nhãn nay có **bốn** dòng (mã + máy · tên +
tình trạng VT · khách + chip trễ hạn · sản lượng) — 250×74 của bản phác thảo đầu chỉ vừa ba dòng.

Cột **cuối tuần / ngày lễ** tô `--rule-hair` (một bậc so với `--canvas`, đủ thấy mà không thành sọc),
tô **cả** ô tiêu đề **và** ô trong rãnh. Ô ngày **hôm nay**: số đổi `--rust` + một dấu `•` `--rust`
cạnh tên thứ — không tô nền, để không tranh với nền cuối tuần.

**Khối chạy trong thanh** — bốn sắc độ **cùng một họ** trung tính, đậm dần theo thứ tự bước:
`--ink` → `#334155` (đặt thành token cục bộ `--xl3-run-2`) → `--steel` → `--ash-2`. Cố ý **không**
cầu vồng: màu ở đây mã hoá *thứ tự*, không mã hoá *loại*. Ô màu trong bảng công đoạn phải lấy đúng
bốn giá trị này để hai chỗ khớp nhau.

| Trạng thái thanh | Biểu hiện |
|---|---|
| Bình thường | nền `--rule-soft`, khối chạy bốn sắc độ trên |
| Đang chọn | viền `--rust` + `box-shadow: 0 0 0 1px var(--rust)` |
| Đang kéo | `cursor: grabbing` |
| Trễ hạn SX | nền `--signal-soft` + khối chạy `--signal` |
| Cắt mép trái / phải | bỏ bo góc bên đó + mũi tên `‹` / `›` trên nền `--canvas` |

Trễ hạn có **ba** lớp báo, không lớp nào chỉ dựa vào màu: chip `TRỄ HẠN` ở nhãn hàng · `⚠ trễ hạn`
mở đầu nhãn cuối thanh · nền thanh và khối chạy đổi sang họ `--signal`. Panel dưới cũng hiện chip
"Trễ hạn SX". Chữ "trễ hạn" **không** đặt trong lòng thanh như ảnh tham chiếu — thanh của ta có khối
chạy bên trong, chữ đè lên là mất cả hai.

Hai vạch hạn cùng nằm trên hàng, **phân biệt bằng kiểu nét** chứ không chỉ bằng màu:
`dashed` + `--signal` cho hạn hoàn thành SX; `dotted` + `--ash-2` cho hạn giao khách.

---

## 7. Thanh hai lớp — cách vẽ

Thanh là **một** phần tử `.xl3-span` định vị theo `%` của dải, chứa các `.xl3-run` con định vị theo
`%` **của chính thanh**:

```
pctTho(m) = (m − winStart) / winLen × 100        ← THÔ: cho phép âm và > 100
kep(p)    = min(max(p, 0), 100)

p0 = pctTho(start);  p1 = pctTho(finish)
bỏ hàng nếu  p1 <= 0  hoặc  p0 >= 100            ← lệnh nằm hoàn toàn ngoài cửa sổ

left  = kep(p0)                                   ← thanh (đã kẹp vào cửa sổ)
width = kep(p1) − kep(p0)
left  = (pctTho(seg.a) − left) / width × 100      ← khối chạy, quy về pct CỦA THANH
width = (pctTho(seg.b) − pctTho(seg.a)) / width × 100
```

Điểm dễ sai: khối chạy **không** được tính theo `(seg.a − start)/(finish − start)` khi thanh bị cắt —
`start` thật nằm ngoài cửa sổ, còn `left/width` của thanh là giá trị **đã kẹp**, hai hệ quy chiếu
lệch nhau và các khối trượt khỏi cột ngày. Luôn đi qua `pctTho` rồi mới quy về pct của thanh, và cho
thanh `overflow: hidden` để phần thừa bị cắt gọn.

Đặt `width` khối chạy tối thiểu ~0.4% để đoạn vài phút không biến mất hẳn. Nền nhạt lộ ra giữa các
khối chính là nghỉ giữa ca · ngoài ca · ngày nghỉ — **đây là thông tin, không phải khe hở trang trí**,
nên đừng "sửa" bằng cách cho khối chạy dính liền.

**Mũi tên mép**: `p0 < 0` ⇒ thêm `‹` ở `left: 1px`; `p1 > 100` ⇒ thêm `›` ở `right: 1px`. Cả hai
`position: absolute; top: 50%; z-index: 2; pointer-events: none` và có nền `--canvas` để không lẫn
vào khối chạy đậm phía dưới. Mép bị cắt bỏ bo góc (`border-*-radius: 0`) — đó là tín hiệu "còn nữa".

Nhãn `xong <mốc>` là phần tử riêng, `left = kep(p1)`, `pointer-events: none`, `white-space: nowrap`.
**Đặt bên phải thanh** — trong thanh thì thanh hẹp là mất chữ, phía trên thanh thì đè nhãn vạch hạn
(đã dính ở bản phác thảo đầu). **Chỉ vẽ khi `p1 <= 100`**: thanh chạy ra ngoài cửa sổ mà vẫn dán nhãn
là dán vào mép phải, đọc thành "xong đúng lúc hết cửa sổ" — sai. Hai vạch hạn cũng vậy: `p < 0` hoặc
`p > 100` thì không vẽ.

---

## 8. State & tương tác

| Hành động | Hành vi |
|---|---|
| Bấm thanh | chọn lệnh → panel dưới đổi theo. Cú bấm sau khi kéo KHÔNG tính (`draggedRef`). |
| Kéo ngang thanh | `bat_dau_at += Δpx → phút`, bám **15 phút**; thanh + nhãn cập nhật ngay tại chỗ (lạc quan). |
| Nhả chuột | `PUT /lenh/{id}` kèm `expected_updated_at`. Server trả mốc **đã làm tròn** + `ket_thuc` mới ⇒ ghi lại theo server. |
| Mốc bị dời (ngoài ca/nghỉ/ngày nghỉ) | băng thông báo góc trên Gantt: *"Ngoài giờ chạy — đã dời sang 06:00 ngày 14/09"*, tự tắt sau ~2,4s. |
| Kéo thẻ hàng chờ thả vào lưới | `PUT` lần đầu; thẻ rời hàng chờ, hàng mới xuất hiện và được chọn. Thả ngoài lưới ⇒ không làm gì, thẻ về chỗ. |
| Kéo hai mép thanh | KHÔNG có. Độ dài là số dẫn xuất. |
| Chốt tới nấc 15 phút | 15 phút chỉ đáng **0,4–1,1px** tuỳ mức thu phóng (bảng §3). Kéo chuột chốt NGÀY + giờ thô; nấc 15 phút chốt bằng `←`/`→` hoặc ô giờ ở panel. Nói rõ trong microcopy, đừng để người dùng tưởng chuột hỏng. |
| Đổi mức thu phóng (Tuần / 2 tuần / Tháng) | giữ TÂM cửa sổ, đặt lại `--xl3-day-min` + `min-width` khung, rồi gọi lại `GET /lich?tu=&den=`. |
| 409 (người khác vừa dời) | giữ mốc của server, nói *"Lệnh vừa được người khác dời — đã cập nhật theo bản mới nhất"*. |
| Phát hành | `POST /phat-hanh/{id}`, không hỏi lại, không kiểm. Hàng đổi trạng thái + toast. |
| Đổi vị trí cửa sổ (`‹ N ngày` · ô ngày · `N ngày ›` · Hôm nay) | đổi `winStart` rồi gọi lại `GET /lich?tu=&den=`. Cấm cắt trong JS. |
| SSE | phát hành/thu hồi từ nơi khác ⇒ cập nhật hàng tương ứng, không reload cả bảng. |

Thứ tự hàng: theo `bat_dau_at` tăng dần. **Không sắp lại giữa lúc kéo** — thanh tuột khỏi con trỏ là
lỗi cảm giác tệ nhất của Gantt kéo thả.

---

## 9. Bàn phím & a11y

- Thanh là `role="button"` + `tabIndex=0` + `aria-label` dạng *"LSX26-0089 bắt đầu 10/09 08:30, xong
  11/09 09:15"*.
- Thanh đang focus: `←`/`→` dời **15 phút**, `Shift`+`←`/`→` dời **một ca**, `Enter` mở panel.
- `:focus-visible` viền `--rust` offset 2px trên mọi thứ bấm được (thẻ hàng chờ, thanh, nút, seg).
- Băng thông báo dùng `aria-live="polite"`.
- `prefers-reduced-motion` ⇒ tắt hiệu ứng hiện/ẩn của băng thông báo.

---

## 10. Bẫy / rủi ro cho agent BUILD

1. **Lưới bị bóp còn một ngày** (đã dính ở bản phác thảo đầu): hàng khai
   `grid-template-columns: 264px repeat(N, …)` nhưng chỉ đặt **hai** ô con ⇒ dải thời gian nhận đúng
   bề rộng một cột ngày, mọi thanh mảnh như que. Hàng chỉ có **hai** cột
   (`264px minmax(0, 1fr)`); lưới N ngày nằm **bên trong** dải.
2. **Hàng tiêu đề lệch dải**: tiêu đề chia `264px + minmax(0,1fr)` với lưới N ngày **bên trong** ô
   `1fr` đó, dải cũng chia `N × minmax(day-min,1fr)` bên trong `1fr`. Hai lớp chỉ khớp khi khung đủ
   rộng ⇒ `min-width` khung theo bảng §3, và **phải đặt lại mỗi lần đổi mức thu phóng** — quên là
   tiêu đề với thanh lệch nhau đúng lúc người dùng bấm "Tháng". Cách kiểm nhanh không cần mắt: đo
   `.track` và `.days` phải **bằng nhau** và N ô con phải **bằng nhau**.
3. **Khối chạy trượt cột khi thanh bị cắt mép**: quy khối chạy theo `start`/`finish` thật trong khi
   `left`/`width` của thanh đã bị kẹp vào cửa sổ ⇒ lệch hệ quy chiếu. Đi qua `pctTho` (§7).
4. **Giờ naive vs aware**: API trả **wall-clock naive** (giờ nhà máy) theo đúng lối
   `xep_lich_service._naive`. FE đọc thẳng bằng `ngayGio` của `keHoachSxShared`, **không** `new
   Date(iso)` trên chuỗi có `Z` — lệch 7 tiếng.
5. **`han_*` là DATE, không phải DATETIME** — dùng `ngay()` chứ không `ngayGio()`; vạch hạn trên
   Gantt neo vào **cuối ngày** đó (xem `spec-xep-lich-3.md` §5).
6. **`quy_cach_json` là ảnh chụp cũ** — khoá có thể trống. Trống thì bỏ ô, đừng in "null" hay bịa nhãn.
7. **Pydantic nuốt field im lặng**: thêm số nào cho panel là phải đi hết `dict service` → schema
   `Out` → type TS, sót một tầng là FE nhận `undefined` mà không ai báo lỗi.
8. **Đừng bật `SEED_DEMO`** để có dữ liệu xem thử trên DB dev đang có dữ liệu.
