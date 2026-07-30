# UI_DESIGN.md — Hệ thiết kế SVN

> **Nguồn chân lý cho mọi quyết định thị giác.** File này từng bị xoá (commit `ebb650d`)
> trong khi 8 chỗ trong code vẫn trích dẫn nó — dựng lại 2026-07-30, luật rút từ **code
> thật** của hai màn đã được chủ dự án chấp nhận: `nhan-su.css` (Hồ sơ nhân sự) và
> `redesign-phong-ban.css` (Phòng ban).
>
> Hiện thân trong code: `frontend/src/styles/tokens.css` (giá trị) +
> `frontend/src/styles/global.css` (primitive dùng chung). **Đổi luật ở đây thì phải đổi
> cả hai file đó cùng lúc**, đừng để doc và code nói hai chuyện.

## 0. Một câu tóm cả hệ

> Neutral **lạnh** (slate) làm nền, accent **ấm** (rust) làm điểm nhấn duy nhất, màu phụ
> chỉ được xuất hiện ở **liều nhỏ**, và mật độ phải **gọn** — chỉ số gộp thành dải mảnh,
> không phải thẻ cao.

Ba lỗi hay gặp nhất, theo đúng thứ tự mức độ phá hoại:

1. Nhiều accent cùng lúc (mỗi thẻ một màu) → giao diện "cầu vồng", màu mất nghĩa.
2. Màu ở liều lớn (tô cả thẻ, vạch màu ngang đầu thẻ) → gắt, và chỗ *không* có việc lại
   nổi hơn chỗ *có* việc.
3. Bỏ sạch màu để "cho an toàn" → đơn điệu, mất mốc cho mắt bám.

Nấc đúng nằm giữa 2 và 3: **màu vẫn nhiều, nhưng liều nhỏ.**

---

## 1. Neutral — MỘT nhiệt độ cho toàn hệ (slate)

Chín slot, không thêm không bớt. Mọi màn dùng đúng bộ này qua token.

| Slot | Token | Giá trị | Dùng cho |
|---|---|---|---|
| nền app | `--paper` | `#f8fafc` | nền màn hình, nền sau thẻ |
| mặt thẻ | `--canvas` | `#ffffff` | thẻ, ô nhập, thân bảng |
| chữ chính | `--ink` | `#0f172a` | tiêu đề, số, chữ cần đọc — **và nền sidebar** |
| chữ mờ | `--ash` | `#475569` | nhãn, phụ đề, meta |
| chữ rất mờ | `--ash-2` | `#64748b` | gợi ý, placeholder, chú thích |
| viền đậm | `--rule` | `#cbd5e1` | viền ô nhập, viền chip nghỉ |
| viền nhạt | `--rule-soft` | `#e2e8f0` | viền thẻ, kẻ dưới header bảng |
| viền mảnh nhất | `--rule-hair` | `#f1f5f9` | kẻ giữa các hàng bảng |
| khối tối | `--charcoal` | `#0f172a` | chip lọc đang chọn, panel tối |

**Chỉ có 3 bậc chữ.** Cần bậc thứ tư thì dùng cỡ chữ hoặc độ đậm, đừng đẻ màu mới.

## 2. Accent — MỘT màu, và nó ẤM

Neutral lạnh + accent ấm là cặp có chủ ý (hình 3 làm đúng thế: `--rdx-primary: #c5400a`
trên nền slate). **Không** đổi accent theo neutral.

| Token | Giá trị | Dùng ở |
|---|---|---|
| `--rust` | `#c5400a` | nút primary · toggle chế độ đang chọn · viền phần tử đang chọn · vành focus |
| `--rust-deep` | `#8a2d07` | hover của nút rust · chữ trên nền rust-soft |
| `--rust-soft` | `#f4e2d6` | **bề mặt được tô**: hover hàng · hover nút phụ · nền phần tử đang chọn · vòng icon |

**Hover hàng bảng dùng tint rust, KHÔNG dùng xám.** Xám trên nền trắng gần như không thấy,
và nó biến bảng thành thứ chết. (Bản gốc: `.rdx-quote tbody tr.click:hover td`.)

**Nền dải tiêu đề bảng là `--paper`, KHÔNG phải `--rust-soft`** — xem §6. Tô đào cả dải
tiêu đề là quá liều: nó biến thứ chỉ cần "đủ tách" thành mảng màu tranh chú ý với dữ liệu
bên dưới.

Vì sao dải tiêu đề vẫn phải có tint — nguyên văn lý do đã ghi trong `nhan-su.css`:

> *"chữ xám trên nền kem gần như chìm vào thân bảng, mắt không có mốc để bám khi quét cột"*

## 3. Màu phụ — chỉ được xuất hiện ở LIỀU NHỎ

**Cho phép**: vòng icon ≤ 26px · pill có chấm · ô avatar · chấm trạng thái.
**CẤM**: tô nền cả thẻ · vạch màu ngang đầu thẻ · gradient mảng lớn · một màu khác cho mỗi thẻ.

```
vòng icon 26px   nền pastel + chữ đậm CÙNG HỌ
                 #ecfdf5 + #059669   ·   #fffbeb + #d97706   ·   #eef2ff + #4f46e5
badge trạng thái pill r99 · chấm 6px · padding 3px 10px · 11.5px/600 · gap 6px
chấm trên avatar #10b981 đang làm · #f59e0b thử việc · #8b5cf6 nghỉ dài · #ef4444 đã nghỉ
                 (viền 2px màu nền, để chấm nổi trên avatar)
```

**Màu phụ phải mang NGHĨA.** Đừng lấy màu ngữ nghĩa gán cho thứ vô nghĩa: màu avatar sinh
từ hash tên khách, nên nếu tô `moss` (=tốt) thì người dùng đọc ra thông tin không hề có.
Thứ vô nghĩa thì dùng thang một họ (`--heat-1..4`) hoặc để trung tính.

Trạng thái **không được** chỉ báo bằng màu — luôn kèm chấm, icon, hoặc chữ.

## 4. Chỉ số (KPI) — dải pill gộp, KHÔNG phải thẻ

```
dải     inline-flex · gap 12px · border-radius 99px · padding 5px 16px   → cao ~38px
mỗi ô   vòng icon 26px  +  số 14px/700  +  nhãn 11px/600
chia ô  vạch 1px × 18px
```

**CẤM 4 thẻ KPI cao ≥ 80px xếp 4 cột.** Đó là 84px cho thứ đọc mất 1 giây, và nó đẩy
bảng dữ liệu — nội dung thật của màn — xuống dưới màn hình.

Bản mẫu: `.rdx-compact-kpi` trong `redesign-phong-ban.css`.

## 5. Chip lọc

| Trạng thái | Quy tắc |
|---|---|
| nghỉ | nền `--canvas` · viền `--rule` · 12px/600 · padding 4px 12px · r99 |
| hover | viền + chữ rust, nền `--rust-soft` |
| **đang chọn** | nền `--charcoal`, chữ `--on-charcoal` — **không phải rust** |
| số đếm trong chip | 10.5px/700 · `color: inherit` |

**Rust dành cho HÀNH ĐỘNG và TOGGLE CHẾ ĐỘ; charcoal dành cho LỰA CHỌN LỌC.** Nhờ vậy
nhìn một cái là biết đâu là nút bấm được, đâu là bộ lọc đang bật. Khớp `.seg.is-active`
đã có trong `global.css`.

## 6. Bảng — MỘT spec cho mọi màn

Bản gốc: `.rdx-quote` trong `bao-gia.css` (bảng đã được chốt là đẹp). Mọi bảng danh sách
theo đúng bộ số này — **đừng mỗi màn một kiểu**.

```
wrap    nền --canvas · viền 1px --rule · --r-5 · overflow hidden
table   border-collapse: COLLAPSE (không separate — để kẻ 1.5px dưới header liền mạch)
        font-size 13.5px
th      10.5px / 700 / HOA / letter-spacing .07em / --ash / căn trái
        padding 10px 14px
        nền --paper  +  kẻ dưới 1.5px --rule        ← cặp BẮT BUỘC đi cùng nhau
td      padding 12px 14px · kẻ dưới 1px --rule-hair · vertical-align middle
        hàng CUỐI bỏ kẻ (đã có viền ngoài)
hover   nền --rust-soft
chọn    nền --rust-soft + box-shadow inset 3px 0 0 --rust (viền trái)
số      --ff-num + font-variant-numeric: tabular-nums · cột căn PHẢI
```

**Vì sao nền `--paper` mà vẫn thấy được dải tiêu đề:** `--paper` một mình chỉ lệch
**1.046:1** so với `--canvas` — gần như vô hình. Thứ thật sự tách dải tiêu đề là **kẻ
1.5px** (dày hơn kẻ `--rule-hair` giữa các hàng). Bỏ một trong hai là header chìm ngay.

Ba bậc kẻ, phân vai rõ: viền ngoài `--rule` 1px → dưới header `--rule` **1.5px** → giữa
hàng `--rule-hair` 1px.

## 7. Chữ

Một font cho toàn bộ **chữ**: **Be Vietnam Pro** (`--ff-sans`), 4 weight 400/500/600/700.

`--ff-num` (JetBrains Mono) **chỉ** dùng cho **số và mã** — tiền, số lượng, giờ, %, mã
phiếu, công thức. Lý do bắt buộc: Be Vietnam Pro có chữ số **rộng khác nhau** (số `1` =
385 so với số `4` = 710 trên 1000em) và **không có feature `tnum`**, nên cột số dùng sans
sẽ so le và CSS không cứu được. Luôn đi kèm `font-variant-numeric: tabular-nums`.

Nhãn HOA giãn cách là hiệu ứng của `text-transform: uppercase` + `letter-spacing`,
**không phải** của font — đừng vì cái đó mà lôi font thứ hai vào chữ.

Thang cỡ: `--fs-2xs 11` → `--fs-2xl 26`. **Không** dùng cỡ nửa pixel (11.5 / 12.5 / 13.5)
và **không** xuống dưới 11px.

## 8. Hình khối, nhịp, chuyển động

- **Bán kính**: chỉ `--r-2 4` · `--r-3 6` · `--r-5 10` · `--r-6 12` · `--r-pill`. Ngoại lệ
  hợp lệ: `50%` cho vòng tròn. Đừng viết số thô trùng với token.
- **Khoảng cách**: thang 4px (`--sp-1..16`). Khoảng *quanh* một nhóm phải lớn hơn khoảng
  *bên trong* nó.
- **Đổ bóng**: hệ này **PHẲNG mặc định**. `--shadow-1` (hairline 1px) cho thẻ thường,
  `--shadow-4` cho vật nổi, `--shadow-lg` cho modal. Không tự pha bóng mới.
- **Chuyển động**: `--duration-fast 120ms` / `--duration-base 140ms` /
  `--duration-enter 400ms`, easing `--easing-standard`. Không viết `0.2s ease` rời rạc.
  Mọi chuyển động phải tôn trọng `prefers-reduced-motion` (đã có guard trong `global.css`).
- **Icon**: Lucide, một bộ duy nhất, `currentColor`. Không dùng emoji làm icon.

## 9. Tương phản — kiểm bằng số, không bằng mắt

Chữ thường ≥ **4.5:1**, chữ lớn / thành phần UI ≥ **3:1** (WCAG AA).
Số dưới đây đo trên bảng **slate** hiện hành (2026-07-30), không phải bảng ấm cũ.

**Đạt** — dùng thoải mái cho chữ thường:

| Cặp | Tỷ lệ | | Cặp | Tỷ lệ |
|---|---|---|---|---|
| `--ink` / `--canvas` | 17.85:1 | | `--ink` / `--rust-soft` | 14.19:1 |
| `--ash` / `--canvas` | 7.58:1 | | `--ash` / `--rust-soft` | 6.02:1 |
| `--rust` / `--canvas` | 5.11:1 | | `--rust-deep` / `--rust-soft` | 6.79:1 |
| `--rust-deep` / `--canvas` | 8.54:1 | | `--on-charcoal` / `--charcoal` | 17.06:1 |
| `--ink` / `--heat-1` | 13.19:1 | | `--ink` / `--heat-2` | 9.45:1 |
| `--ink` / `--heat-3` | 5.85:1 | | `--paper-contrast` / `--heat-4` | 4.88:1 |

`--ash-2` = `#64748b` (slate-500) đạt **4.76:1** / **4.55:1** — dùng được cho chữ.

> Cố ý **không** lấy slate-400 `#94a3b8` dù nó là bậc "đúng" theo thang Tailwind: chỉ đạt
> **2.56:1**, trượt AA, mà token này đang dùng ở 358 chỗ phần lớn là chữ. Bảng ấm cũ cũng
> đã trượt (3.24:1) — lần này sửa hẳn ở token thay vì đi vá 358 chỗ.

**KHÔNG đạt** — đừng dùng cho chữ thường:

| Cặp | Tỷ lệ | Phải làm gì |
|---|---|---|
| `--paper-contrast` trên `--heat-3` | **2.92:1** | bậc 3 phải dùng chữ `--ink` (5.85:1) |
| `--ash-2` trên `--rule-soft` / `--rule` | < 4.5 | chữ trên nền viền-nhạt phải là `--ash` trở lên |

Thang nhiệt **đổi chiều tương phản ở bậc 3**: bậc 1–3 chữ `--ink`, bậc 4 chữ
`--paper-contrast`.

**Độ thấy được của nền** (không phải chữ, nên WCAG không áp — nhưng phải phân biệt được):
`--rust-soft` lệch **1.258:1** so với `--canvas` — rõ nhất trong các sắc nền, nên nó là
lựa chọn đúng cho header bảng và hover hàng. (`--rule-soft` 1.233 · `--rule-hair` 1.096 ·
`--paper` 1.046 — `--paper` gần như không thấy trên thẻ trắng.)

## 10. BẪY CASCADE — đọc trước khi sửa CSS

**`global.css` được bundle SAU toàn bộ page CSS.** Đo trên bản build thật
(`dist/assets/index-*.css`):

```
   49.144  bao-gia      .rdx-quote .q-card
  288.624  nhan-su      .ns__table
  370.569  khach-hang   .kh__tablewrap
  638.914  global.css   .card          ← global nằm CUỐI
  639.734  global.css   .btn
  641.843  global.css   .seg
```

Hệ quả: **page CSS KHÔNG thể override primitive của global.css bằng thứ tự cascade.**
`.kh__tablewrap { padding: 0 }` bị `.card { padding: var(--sp-8) }` đè, và bảng thụt vào
32px thành khung-trong-khung. Đây là nguyên nhân gốc của đống `!important` trong repo —
người viết trước gặp đúng bẫy này rồi vá bằng `!important`.

**Cách làm đúng, theo thứ tự ưu tiên:**

1. **Đừng gắn primitive global rồi định override nó.** Cần một khung khác `.card` thì viết
   class riêng và **không kèm `.card`** — Báo giá làm đúng: chỉ `.q-card`.
2. Cần đè thật thì **tăng độ cụ thể** (`.kh__x.card`, `.rdx-quote .q-card`), đừng dùng
   `!important`.
3. `!important` là phương án cuối, và phải ghi chú đè cái gì.

## 11. Luật viết CSS

- **Không hex thô.** Mọi giá trị màu đi qua token. Cần sắc mới → bàn rồi thêm vào
  `tokens.css`, đừng nhúng tại chỗ.
- **Không khai một selector hai lần trong cùng file.** Bản SAU thắng âm thầm, và đó chính
  là lý do `khach-hang.css` từng phải rắc 98 `!important` (2026-07: 56 selector bị nhân đôi).
  Sửa CSS "không ăn" thì **đếm số định nghĩa selector trước**, đừng thêm `!important`.
- **`!important` là mùi lỗi**, không phải công cụ. Gặp nó thì đi tìm cái đang bị nó đè.
- **`var(--x)` phải tồn tại.** `var(--sp-1-5)` không có token và không fallback ⇒ khai báo
  hỏng hoàn toàn, thuộc tính bị bỏ (đã vỡ thật: 3 chỗ `gap` = 0).
- **Mỗi màn một tiền tố BEM riêng** (`.kh__`, `.ns__`, `.rdx-`, `.khsx__`…) — không đụng nhau.
- Trạng thái (hover/active/selected) phải **khác nền gốc**. Ánh xạ màu máy móc rất dễ làm
  hai màu khác nhau trùng thành một token ⇒ mất hẳn phản hồi.

## 12. Việc còn mở

- Giá trị token ngữ nghĩa (`--moss/--amber/--signal/--plum/--steel`) đang là bản **trầm**
  của hệ cũ, còn §3 lấy cặp pastel **tươi hơn** của hình 3. Chưa hợp nhất — quyết sau khi
  soi thực tế trên nền slate mới.
- 56 selector bị nhân đôi + 89 `!important` trong `khach-hang.css` chưa dọn (cần chạy app
  để kiểm từng thay đổi kích thước).
- Cỡ chữ lệch thang (9px ×13, 10.5/11.5/12.5/13.5/15px) trong `khach-hang.css` chưa chuẩn hoá.
