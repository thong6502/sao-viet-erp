# Rà & sửa giao diện điện thoại (375px) — theo từng module

> **Cho người/agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` hoặc
> `superpowers:executing-plans` để chạy plan này theo từng Task. Các bước dùng cú pháp checkbox
> (`- [ ]`) để đánh dấu tiến độ.

**Goal:** Mỗi màn của SVN dùng được thật trên điện thoại 375px — không mất nội dung, không chữ
chồng chữ, không chữ quá khổ, mọi nút/popup đều với tới và đọc được.

**Architecture:** Sửa TẬP TRUNG ở một file lớp phủ `frontend/src/styles/responsive.css` (nạp thứ
49/51 lúc chạy nên hoà đặc trưng là nó thắng), chia theo mục `§N` có ghi rõ triệu chứng + nguyên
nhân. Chỉ chạm file nguồn của trang khi lỗi KHÔNG sửa được bằng CSS (vd thiếu `className` để bám
vào). Mỗi Task = MỘT module: thao tác thật trên dev-browser ở 375px → chụp bằng chứng lỗi → viết
mục `§N` → thao tác lại đúng chỗ đó → chụp bằng chứng đã hết lỗi.

**Tech Stack:** React + Vite (FE `localhost:5173`), CSS thuần (không Tailwind), dev-browser CLI
(Playwright trong hộp cát QuickJS) để thao tác chuột/bàn phím thật và chụp màn hình.

**Spec:** Không có spec riêng. Nguồn yêu cầu là lời chủ dự án (31/08/2026):
*"có nhiều chỗ khi thao tác dưới điện thoại khó với khó nhìn á, tôi muốn bạn thao tác rồi chỉnh
chi tiết từng màn một sâu nhất có thể"* và *"nhiều module popup nút các thứ khi ở điện thoại thì
bị cắt mất lắm, hoặc chữ chồng lên nhau, hoặc chữ to đùng"*.
Bộ nhớ nền: `.claude/projects/D--jobs-SVN/memory/bay-giao-dien-dien-thoai-svn.md`.

---

## Global Constraints

Áp cho MỌI task, không nhắc lại trong từng task:

- **Khổ máy đo: 375 × 812** (iPhone chuẩn). Ngưỡng media mặc định `max-width: 768px`; dùng
  `1024px` khi luật cũng đúng cho máy tính bảng.
- **Nơi sửa: `frontend/src/styles/responsive.css`.** Thêm mục mới ở CUỐI file, đánh số tiếp
  (`§57`, `§58`, …), mở đầu bằng khối chú thích ghi: triệu chứng ĐÃ CHỤP ĐƯỢC, selector gốc gây
  lỗi kèm `file:line`, và vì sao chọn cách chữa này.
- **Có MỘT file CSS nữa nạp SAU `responsive.css`:** `frontend/src/styles/responsive-chu.css`
  (1334 dòng, SINH TỰ ĐỘNG bằng `scratchpad/sinh_san_chu.py`, import ở `main.tsx:11`). Nó nâng
  SÀN cỡ chữ lên 12px cho ~1000 bộ chọn ở `≤768px`, bằng `font-size: 12px !important`. Hệ quả:
  (1) đừng viết luật hạ cỡ chữ cho một lớp đã có trong file đó — sẽ thua; grep tên lớp ở đó
  trước; (2) **đừng sửa tay file đó**, nó bị sinh đè; (3) nếu cần thêm ngoại lệ thì sửa
  `sinh_san_chu.py` rồi sinh lại, và nói rõ lúc báo cáo.
- **KHÔNG dùng `!important`** trừ đúng hai ca: (1) đè `style={{…}}` inline trong JSX, (2) CSS gốc
  đã khai `!important`. Ghi rõ lý do trong chú thích.
- **Không đổi file CSS của trang** (`pages/*.css`) trừ khi luật ở `responsive.css` không thể thắng.
  Đổi thì phải nói rõ lúc báo cáo.
- **Xác minh = thao tác thật.** Vào màn bằng bấm nút hamburger → bấm mục sidebar. Lăn chuột từng
  nấc (`page.mouse.wheel`) chứ không `scrollTo`. Bấm nút bằng `page.click` toạ độ thật. **KHÔNG
  dùng API/curl thay bất kỳ bước nào.** Nếu buộc phải tắt qua API ở một đoạn, phải TỰ NÓI RÕ ngay
  lúc báo cáo.
- **Báo cáo phải cụ thể:** bấm gì, gõ gì, thấy gì ở từng bước; kèm tên file ảnh chụp.
- **Tối đa 2 dev-browser cùng lúc.** Mở đợt mới thì đóng đợt cũ. (4 trình duyệt song song từng
  làm backend quá tải, nhiều màn kẹt "Đang tải…" ⇒ kết quả không tin được.)
- **KHÔNG chạy `./init.ps1`.** Sau khi sửa `.tsx` thì `npx tsc --noEmit`. Sửa CSS thì kiểm cân
  ngoặc bằng script đếm `{`/`}`.
- **KHÔNG commit/push** cho tới khi chủ dự án yêu cầu. Cây làm việc đang có thay đổi của phiên
  khác (`backend/app/services/giu_cho_service.py`, `ke_hoach_vat_tu_service.py`, …) — nếu được
  yêu cầu commit thì phải liệt kê ĐÍCH DANH file, cấm `git add -A`.
- **Tiếng Việt** trong mọi chú thích CSS, tên mục, và báo cáo.

---

## Sáu khuôn lỗi — soi đúng sáu chỗ này trước khi dò lung tung

Đã đo toàn hệ: gần như mọi lỗi điện thoại của SVN rơi vào sáu khuôn dưới đây, không phải lỗi lẻ
từng màn. Mỗi task đều bắt đầu bằng việc soi sáu khuôn này.

| # | Khuôn | Dấu hiệu trên ảnh | Cách chữa mẫu |
|---|-------|-------------------|---------------|
| 1 | Hàng flex `justify-content: space-between`, con không khai `flex` | Tiêu đề rơi dọc một chữ (hoặc một ký tự) mỗi dòng | `flex-wrap: wrap` + cho khối chữ `flex: 1 1 200px` (đừng `1 1 100%`, sẽ gãy cả khi cụm nút bé) |
| 2 | `<table width:100%>` NẰM TRONG khung `overflow-x:auto` | Cột bóp còn ~30px, khung cuộn vô dụng | Đặt `min-width` cho **BẢNG** (§40, §49, §52) |
| 2b | Bảng KHÔNG có khung cuộn nào | Bảng bị cắt cụt ở mép thẻ | `display:block; overflow-x:auto` + `white-space:nowrap` trên `th/td` (§51, §53). Chỉ `display:block` KHÔNG đủ |
| 3 | Nút chỉ hiện khi `:hover` (`opacity: 0 → 1`) | Trên ảnh không thấy nút nào cả | Thêm nhánh `@media (hover: none)` (§28, §48) |
| 4 | `white-space:nowrap` + `text-overflow:ellipsis` trên TÊN | "Ban giá…" — nuốt mất chữ | Ở màn hẹp cho xuống dòng: `white-space:normal; overflow:visible; overflow-wrap:anywhere` (§45) |
| 5 | Dải nhiều ô chia đều (`flex:1`) mà chữ bên trong không cắt được | **Chữ chồng lên nhau** — chữ tràn hai bên vì canh giữa | Xoay DỌC ở màn hẹp (§54), đừng cho cuộn ngang nếu có vạch `position:absolute` |
| 6 | Cỡ chữ tiêu đề/số liệu khai cứng cho màn rộng | **Chữ to đùng**, tiêu đề chiếm 2-3 dòng, ô KPI vỡ | Hạ cỡ ở `≤768px` bằng `clamp()` hoặc giá trị cố định nhỏ hơn |

Ngoài ra hai lỗi phụ hay đi kèm:

- **Ô rỗng `<td colspan>`**: câu "Chưa có…" canh giữa một bảng rộng 900px ⇒ trên màn 375px chỉ đọc
  được mảnh. Chữa bằng `position:sticky; left:0; max-width:calc(100vw - 56px)` — CHỈ nhắm đích danh
  lớp khối rỗng, KHÔNG nhắm `td[colspan]` chung (dòng cộng/tổng phụ cũng dùng colspan). Xem §56.
- **Khay toast** `position:fixed; top:16` đè lên tiêu đề hộp thoại ⇒ dời xuống đáy (§46).

---

## Quy trình chuẩn cho MỘT module (dùng chung cho mọi Task)

Mỗi Task chỉ ghi phần KHÁC BIỆT; phần dưới đây là bộ khung không lặp lại.

**File kịch bản:** đặt trong thư mục nháp của phiên
(`…/scratchpad/`), ghép `lib_cham.js` + kịch bản riêng rồi chạy:

```bash
cat lib_cham.js b_<ten>.js > z_<ten>.js && dev-browser --browser <ten> --timeout 3000 run z_<ten>.js > V_<ten>.txt 2>&1
```

`lib_cham.js` đã có sẵn: `dangNhap(page)` (admin/admin123), `vaoMan(page, "<nhãn sidebar>")`,
`dsNut(page)`, `bamNhan(page, "<nhãn>")`, `dongHop(page)`, `lanNgang(page, css, tien, n, buoc)`.

**Luật trình duyệt (rút ra từ Task 4 vòng 1 — vì sai luật này mà mất nguyên một lượt):**

- Mỗi task dùng ĐÚNG MỘT instance, tên `t<N>`. **Không tạo instance phụ** dù chỉ để thử — mỗi
  instance là ~5 tiến trình chrome; 5 instance tồn đọng = 27 tiến trình, RAM trống còn 605MB/16GB
  và KHÔNG mở nổi trang nào nữa.
- CLI này **KHÔNG CÓ lệnh `kill`** — `dev-browser --help` chỉ liệt kê
  `run / install / install-skill / browsers / status / stop`. Đừng đi tìm cách đóng từng instance.
- Cần trạng thái sạch thì `page.goto('http://localhost:5173/')` rồi `dangNhap(page)` lại, đừng
  đổi sang instance mới.
- `dev-browser stop` dành RIÊNG cho người điều phối, dọn giữa hai task. Implementer không gọi.
- `dev-browser browsers` / `dev-browser status` cho biết đang có bao nhiêu instance — xem trước khi
  nghi ngờ "máy hỏng".

**Bảy bước cho mỗi module:**

1. **Vào màn** — `vaoMan(page, "<nhãn>")`, chờ 2200ms, chụp `-00`.
2. **Lăn xuống hết trang, mỗi nấc 300px, chụp từng nấc.** Đây là bước quan trọng nhất — DOM đo
   được không thay được việc MỞ ẢNH RA NHÌN.
   **Cảnh báo (phát hiện ở Task 2):** ĐỪNG dừng theo `window.scrollY`. Shell khoá cuộn ở thân
   trang (`global.css:41` `.shell__main { overflow: hidden }`) và cho cuộn trong `.shell__content`
   (`global.css:52` `overflow: auto`), nên `window.scrollY` LUÔN bằng 0 và vòng lăn tự dừng ngay
   nấc 1 — mỗi màn chỉ còn 2 ảnh. `lib_cham.js` đã sửa: `lanXuong()` nay dừng theo `viTriCuon()`,
   cộng `scrollTop` của mọi khung cuộn (ngăn kéo/hộp thoại có khung riêng). Nếu bạn tự viết vòng
   lăn thì dùng `viTriCuon(page)`, đừng dùng `window.scrollY`.
3. **Lăn ngang khung cuộn rộng nhất** 3 nấc × 280px, chụp từng nấc. Kiểm cột cuối có tới được không.
4. **Bấm HẾT nút/tab an toàn** (bỏ qua nút khớp `CAM_RX`: xoá/huỷ/duyệt/gửi/lưu/chốt/…). Sau mỗi
   lần bấm: chụp; nếu popup mở thì lăn xuống trong popup, chụp, rồi đóng.
5. **Mở bản ghi đầu tiên** (bấm dòng đầu của bảng) → lặp lại bước 2-4 bên trong ngăn kéo/hộp.
6. **Đo bằng số** để bắt lỗi mắt dễ bỏ sót:
   - tràn màn: phần tử có `right > innerWidth+3` hoặc `left < -3` mà KHÔNG có tổ tiên `overflow-x`;
   - chồng chữ: hai phần tử anh em có hình chữ nhật giao nhau;
   - chữ quá khổ: `font-size` tính được ≥ 24px trên phần tử có > 20 ký tự;
   - bảng chết cuộn: `scrollWidth > clientWidth` mà `overflow-x` là `hidden`/`visible`.
7. **Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Chỉ dựa vào số đo là bỏ sót phần lớn lỗi.

**Hai điều CẤM tuyệt đối khi thao tác (rút ra từ Task 2):**

- **Đừng bấm nút gọi `window.print()`** (nút "In phiếu", "In", "Xuất PDF"…). Hộp in của hệ điều
  hành nằm NGOÀI tầm CDP, nó treo phiên 90 giây rồi phải `dev-browser stop` — lệnh đó dừng cả
  daemon dùng chung và xoá trạng thái MỌI trình duyệt. Muốn soi bản in thì dùng
  `page.emulateMedia({ media: 'print' })` — vẫn là trang thật render CSS thật, không phải đi tắt.
- **Đừng bấm nút GHI DỮ LIỆU dù nhãn nghe vô hại.** Đọc handler trước khi bấm: ở Tính giá, nút
  "Tính giá" gọi thẳng `api.phieuTinhGia.update`, nút "Báo giá →" gọi thẳng `api.quotations.create`
  — cả hai KHÔNG có hộp xác nhận. Nút nào quyết định không bấm thì phải ghi RÕ LÝ DO trong báo cáo.

**Bộ đếm cảnh giác — những "lỗi" hay là báo động giả:**
- Ô tiêu đề bảng / nút bị bộ dò "chữ rơi dọc" chấm 3-5 dòng: chiều cao phần tử bị THỔI PHỒNG do
  hàng bảng cao hoặc do sàn chạm ngón 44px. Nhìn ảnh mới kết luận.
- Thanh tiến độ bị cắt (`x471-601`): cha có `overflow:hidden`, cắt đúng thiết kế.
- Màn kẹt "Đang tải…"/"Không đọc được dữ liệu": xem lại có phải do chạy quá nhiều trình duyệt.

**Sửa xong thì xác minh lại đúng chỗ đó**, không chụp lại cả màn rồi bảo "đã sửa": phải chụp đúng
popup/đúng bảng/đúng hàng nút vừa sửa, kèm số đo trước–sau.

---

## Hiện trạng — đã làm gì rồi (đừng làm lại)

`responsive.css` hiện có 33 mục, §26–§58 (§57 = trần cỡ chữ tiêu đề trang, §58 = Tính giá).
Các module ĐÃ rà và đã có bản vá kèm ảnh xác minh:

> **ĐỌC TRƯỚC KHI TIN BẢNG DƯỚI.** Mọi đợt quét TRƯỚC kế hoạch này chạy bằng `lanXuong()` bản cũ
> — hàm đó dừng theo `window.scrollY`, mà shell khoá cuộn ở thân trang, nên nó tự dừng ngay nấc 1
> và mỗi màn chỉ chụp 2 ảnh (phát hiện ở Task 2, đã sửa `lib_cham.js`). Vì vậy các module trong
> bảng dưới **đã được vá đúng những lỗi đã thấy, nhưng CHƯA được quét sâu** — phần dưới màn hình
> đầu tiên gần như chưa ai nhìn. Task 20 (quét lại toàn hệ) phải coi bảng này là "đã vá phần
> nổi", không phải "đã xong".

| Module | Mục đã vá | Ghi chú |
|--------|-----------|---------|
| Đơn hàng bán | §37 (ngăn kéo 580px), §54 (vòng đời 5 bước xoay dọc), §55 (đầu thẻ bước) | §53 cũng chạm (bảng "Giao hàng") |
| Khách hàng | §38 | |
| Chấm công | §39 | Còn tab chưa rà hết |
| Bù hao | §40 | |
| Hồ sơ nhân sự | §41 | |
| Phòng ban | §42, §45 | |
| Họ màn "purchase" (~19 màn) | §43 | băng tiêu đề + đầu khối |
| Bài ghép | §44 | mới chỉ thanh công cụ |
| Nhật ký | §47 | |
| Tính giá / Báo giá | §49, §52b | |
| Kho (ngăn kéo mặt hàng, bảng giá NCC) | §50, §51 | |
| Yêu cầu mua hàng | §52a | hộp "Tạo yêu cầu mua hàng" |
| Giao hàng (2 bảng trần) | §53 | |
| Toast toàn hệ | §46 | **CHƯA xác minh trên trình duyệt** |
| `.v-clone` (Báo giá) + `.dag-wire-delete` (DAG) | §48 | **CHƯA xác minh trên trình duyệt** |
| Ô rỗng `<td colspan>` toàn hệ | §56 | **CHƯA xác minh trên trình duyệt** |

Ba mục cuối là **nợ xác minh** — Task 0 phải trả.

---

## File Structure

| File | Trách nhiệm | Ai chạm |
|------|-------------|---------|
| `frontend/src/styles/responsive.css` | Toàn bộ lớp phủ màn hẹp. Mỗi lỗi = một mục `§N` có chú thích | mọi Task |
| `frontend/src/components/AppShell.tsx` | Đã thêm `className="apx-toastwrap"` cho khay toast (§46) | chỉ khi cần thêm `className` để CSS bám vào |
| `docs/superpowers/plans/2026-08-31-giao-dien-dien-thoai.md` | Chính file này — đánh dấu `- [x]` khi xong | mọi Task |
| `…/scratchpad/b_<ten>.js`, `z_<ten>.js`, `V_<ten>.txt` | Kịch bản + log dev-browser, KHÔNG vào git | mọi Task |
| `C:/Users/Windows10 Pro/.dev-browser/tmp/*.png` | Ảnh chụp bằng chứng | mọi Task |

---

# CÁC TASK

Thứ tự ưu tiên: trả nợ xác minh → module người dùng đụng nhiều nhất → danh mục → phần còn lại.
Mỗi Task đứng độc lập, xong là có thể nghiệm thu riêng.

---

### Task 0: Trả nợ xác minh §46, §48, §56

**Files:**
- Modify (nếu vá hụt): `frontend/src/styles/responsive.css` §46, §48, §56
- Script: `…/scratchpad/b_t0.js`

**Interfaces:**
- Consumes: ba mục CSS đã viết ở phiên trước.
- Produces: kết luận "ba mục này ĐÚNG" hoặc bản vá bổ sung — mọi Task sau đều dựa vào việc lớp
  phủ hiện tại là đáng tin.

- [x] **Bước 1: Làm toast hiện ra thật (§46)**

Vào **Kế hoạch vật tư** hoặc **Nhà cung cấp** — hai màn đã thấy toast "Kế hoạch vật tư vừa cập
nhật." tự nổ khi có sự kiện SSE. Nếu không đợi được, dùng đường an toàn: vào **Danh mục › Bù hao**,
sửa một ô rồi bấm **Lưu** (nút này nằm trong `CAM_RX` nên phải bấm TAY trong kịch bản riêng, có
chủ ý) — hệ hiện toast "Đã lưu".

```js
await vaoMan(page, 'Nhà cung cấp');
await page.waitForTimeout(2500);
// chờ tối đa 60s cho một toast bất kỳ
for (let i = 0; i < 30; i++) {
  const co = await page.evaluate(() => !!document.querySelector('.apx-toastwrap'));
  if (co) break;
  await page.waitForTimeout(2000);
}
await saveScreenshot(await page.screenshot(), 't0-toast.png');
console.log(JSON.stringify(await page.evaluate(() => {
  const t = document.querySelector('.apx-toastwrap');
  if (!t) return 'KHONG CO toast';
  const r = t.getBoundingClientRect(), st = getComputedStyle(t);
  return { x: Math.round(r.left) + '-' + Math.round(r.right), y: Math.round(r.top) + '-' + Math.round(r.bottom),
    top: st.top, bottom: st.bottom, cao: innerHeight };
})));
```

Kỳ vọng: `bottom` ≈ `76px`, `top: auto`, hộp nằm ở nửa dưới màn, KHÔNG đè lên tiêu đề hộp thoại.

- [x] **Bước 2: Xác minh `.v-clone` (§48) trong danh sách phiên bản Báo giá**

Vào **Báo giá in ấn** → bấm dòng đầu → tìm khối phiên bản (`.bgv .ver-item`). Đo `opacity` của
`.v-clone`.

```js
console.log(JSON.stringify(await page.evaluate(() => {
  const c = document.querySelector('.bgv .ver-item .v-clone');
  if (!c) return 'KHONG CO .v-clone';
  const r = c.getBoundingClientRect();
  return { opacity: getComputedStyle(c).opacity, w: Math.round(r.width), h: Math.round(r.height) };
})));
```

Kỳ vọng: `opacity: 1` (vì `@media (hover: none)`). **Lưu ý:** dev-browser chạy máy tính bàn nên
`hover: none` có thể KHÔNG khớp — nếu vậy phải bật giả lập cảm ứng
(`--device "iPhone 12"` hoặc `hasTouch: true`), hoặc đổi §48 sang
`@media (hover: none), (max-width: 768px)` như §47 đã làm. **Nếu đổi, ghi rõ lý do vào chú thích §48.**

- [x] **Bước 3: Xác minh `.dag-wire-delete` (§48) trong sơ đồ DAG**

Vào **Kế hoạch sản xuất** → tab **Lệnh sản xuất** → mở một lệnh → tab **Công đoạn** (sơ đồ DAG
mặc định) → tìm `.dag-wire-delete`. Đo `opacity` + `pointer-events`. Kỳ vọng `0.75` và `all`.
*(Sửa 31/08/2026 sau Task 0: bản đầu ghi "Danh mục › Loại sản phẩm" là SAI — `DagRoutingCanvas`
chỉ được `LsxRoutingTable.tsx` dùng, mà file đó chỉ xuất hiện trong `LsxDetailView.tsx`.)*

- [x] **Bước 4: Xác minh §56 — câu "Chưa có…" nằm trong tầm nhìn**

Vào **Kho hàng › Yêu cầu nhập xuất** → bấm tab **"Phiếu từ yêu cầu"** (hộp này đang rỗng) → lăn
ngang bảng hết cỡ → đo vị trí khối rỗng.

```js
await bamNhan(page, 'Phiếu từ yêu cầu');
await page.waitForTimeout(2200);
await lanNgang(page, '.rc__tablewrap', 't0-rong', 3, 260);
console.log(JSON.stringify(await page.evaluate(() => {
  const e = document.querySelector('.rc__empty-state-td > .rc__empty-state, .empty-state__cell > .empty-state');
  if (!e) return 'KHONG CO';
  const r = e.getBoundingClientRect();
  return { x: Math.round(r.left) + '-' + Math.round(r.right), pos: getComputedStyle(e).position,
    trongTam: r.left > -5 && r.right < innerWidth + 5 ? 'NAM TRONG MAN' : 'NGOAI MAN' };
})));
```

Kỳ vọng: `pos: sticky`, `trongTam: NAM TRONG MAN` kể cả khi đã kéo ngang hết cỡ.

- [x] **Bước 5: Mở cả 4 ảnh ra nhìn, ghi kết luận**

Với mỗi mục: ĐẠT / KHÔNG ĐẠT + ảnh nào chứng minh. Mục nào không đạt thì sửa ngay trong Task này
rồi lặp lại bước tương ứng.

- [x] **Bước 6: Kiểm cân ngoặc + đánh dấu**

```bash
python -c "import io;s=io.open('D:/jobs/SVN/frontend/src/styles/responsive.css',encoding='utf-8').read();d=0
for c in s: d += 1 if c=='{' else (-1 if c=='}' else 0)
print('depth',d,'muc',s.count('/* ===== §'))"
```

Kỳ vọng `depth 0`. Đánh dấu `- [x]` cho Task 0 trong file plan này.

---

### Task 1: Khuôn 6 — quét CỠ CHỮ toàn hệ ("chữ to đùng")

Chủ dự án nêu đích danh *"chữ to đùng"* nhưng chưa có mục nào trong `responsive.css` xử lý cỡ chữ.
Đây là task ĐO TRƯỚC, SỬA SAU — làm một lần cho cả hệ thay vì lặp trong từng module.

**Files:**
- Modify: `frontend/src/styles/responsive.css` (thêm §57)
- Script: `…/scratchpad/b_t1.js`

**Interfaces:**
- Produces: mục `§57` đặt trần cỡ chữ ở `≤768px`. Các Task module sau sẽ dựa vào §57 và chỉ vá
  thêm chỗ nào §57 không phủ.

- [x] **Bước 1: Đo cỡ chữ thật trên 8 màn đại diện**

Chạy hàm dò dưới đây trên: Dashboard · Báo giá in ấn · Đơn hàng bán · Kế hoạch sản xuất · Công nợ
phải trả · Yêu cầu nhập xuất · Phòng ban · Nhật ký.

```js
const doChu = () => page.evaluate(() => {
  const out = [];
  for (const e of document.querySelectorAll('.shell__content *, [role=dialog] *')) {
    if (e.children.length) continue;
    const t = (e.textContent || '').trim();
    if (t.length < 6) continue;
    const st = getComputedStyle(e);
    const fs = parseFloat(st.fontSize);
    if (fs < 22) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 4) continue;
    const lh = parseFloat(st.lineHeight) || fs * 1.3;
    out.push({
      cls: (typeof e.className === 'string' ? e.className : '').slice(0, 34),
      the: e.tagName, cỡ: Math.round(fs * 10) / 10,
      chữ: t.slice(0, 30), dòng: Math.round(r.height / lh),
      rộng: Math.round(r.width)
    });
  }
  return out.slice(0, 20);
});
```

Ghi lại: lớp nào, cỡ bao nhiêu, chiếm mấy dòng. Chụp ảnh kèm.

- [x] **Bước 2: Chốt trần và viết §57**

Quy tắc chốt (áp cho `≤768px`):
- Tiêu đề trang (`h1`, `.md-page__title`, `.rc__title`, …): trần **22px**.
- Tiêu đề khối (`h2`, `h3`, `.panel__hd h3`): trần **17px**.
- Số liệu lớn trong ô KPI (`.khsx-kpi-tile__val`, `.acct-summary-strip strong`, …): trần **20px**.
- Chữ thường KHÔNG hạ (dưới 16px trên điện thoại là khó đọc, hạ nữa là phản tác dụng).

Viết bằng `clamp()` để không "nhảy bậc" ở đúng 768px, ví dụ:

```css
@media (max-width: 768px) {
  .md-page__title,
  .rc__title {
    font-size: clamp(19px, 5.6vw, 22px);
    line-height: 1.22;
  }
}
```

**Chỉ liệt kê selector ĐÃ ĐO THẤY ≥ 22px ở bước 1** — không đoán, không quét bừa `h1, h2, h3`
(vài màn dùng `h3` cho nhãn nhỏ, hạ nữa là chữ tí hon).

- [x] **Bước 3: Xác minh lại đúng 8 màn đó**

Chạy lại `doChu()`. Kỳ vọng: không còn phần tử nào cỡ > 22px; tiêu đề trang xuống còn ≤ 2 dòng.
Chụp lại 8 ảnh, mở ra nhìn — **quan trọng: nhìn xem có chỗ nào giờ chữ QUÁ NHỎ không**, hạ quá tay
còn tệ hơn để nguyên.

- [x] **Bước 4: Kiểm cân ngoặc + đánh dấu `- [x]`**

---

### Task 2: Kinh doanh › Tính giá (màn danh sách + phiếu)

**Files:**
- Modify: `frontend/src/styles/responsive.css` (§58 nếu có lỗi)
- Script: `…/scratchpad/b_t2.js`

**Đường vào:** hamburger → **Tính giá**.

**Chỗ phải mở bằng tay (đừng chỉ lăn màn danh sách):**
- Nút **"+ Phiếu tính giá mới"** → hộp tạo phiếu (chọn khách, chọn loại SP).
- Mở phiếu đầu tiên → tab **Danh sách** / **Tính giá** / nút **Báo giá →** / **In phiếu**.
- Trong phiếu: **"+ Thêm sản phẩm"**, ô **Bình bài** (xuôi + nghịch), bảng **Chi tiết dòng giá vốn**.

**Nghi can đã biết:** `.tg-cost__tbl` và `.tg-complist__tbl` đã có `min-width` từ §49 — kiểm lại có
đủ không. `.rdx-cost .panel__hd` đã vá §49. Bảng bình bài và ô nhập khổ giấy CHƯA rà.

- [x] **Bước 1:** Chạy quy trình 7 bước (mục "Quy trình chuẩn"), lưu log `V_t2.txt`, ảnh tiền tố `t2`.
- [x] **Bước 2:** Mở TẤT CẢ ảnh, liệt kê lỗi theo 6 khuôn. Với mỗi lỗi ghi: ảnh nào, selector nào,
      `file:line` của CSS gốc.
- [x] **Bước 3:** Viết `§58` trong `responsive.css` (một mục cho cả module, nhóm theo khuôn).
- [x] **Bước 4:** Thao tác lại ĐÚNG các chỗ đã sửa, chụp ảnh sau, đo số trước–sau.
- [x] **Bước 5:** Kiểm cân ngoặc; đánh dấu `- [x]`; báo cáo cụ thể bấm gì/thấy gì.

---

### Task 2b: Gỡ sàn chữ 12px ra khỏi các BẢN IN (hồi quy do chính ta gây ra)

Task 2 phát hiện: bảng "1. NGUYÊN VẬT LIỆU" trong bản in phiếu tính giá vỡ tiêu đề GIỮA TỪ
("NGUY / ÊN / VẬT / LIỆU") ở khổ hẹp. Truy ra nguyên nhân KHÔNG phải thiết kế gốc:

- `pages/phieu-tinh-gia.css:151` khai `.ptg-tbl { font-size: 10px }`, `:158` khai
  `.ptg-tbl thead th { font-size: 9px }` — đúng cỡ cho khổ GIẤY.
- `styles/responsive-chu.css:932-933` liệt cả hai bộ chọn đó vào danh sách sàn chữ rồi ép
  `font-size: 12px !important` ở `≤768px`.
- Hệ quả đo được: chữ "NGUYÊN" phình từ ~39,6px lên **52,82px**, trong khi ô chỉ có **46px** nội
  dung ⇒ trình duyệt buộc phải cắt giữa từ.

Bản in đo theo KHỔ GIẤY, không theo bề ngang điện thoại. Áp sàn chữ điện thoại vào bản in là vô
nghĩa và phá bố cục. Task này thêm ngoại lệ "bản in" vào bộ sinh rồi sinh lại.

**Files:**
- Modify: `…/scratchpad/sinh_san_chu.py` (bộ sinh)
- Regenerate: `frontend/src/styles/responsive-chu.css` (KHÔNG sửa tay, chỉ sinh lại)
- Script: `…/scratchpad/b_t2b.js`

**Interfaces:**
- Produces: `responsive-chu.css` bản mới, KHÔNG còn bộ chọn nào của bản in. Các task module sau
  vẫn grep file này trước khi viết luật `font-size`, quy tắc không đổi.

- [x] **Bước 1: Chụp ảnh nền để hoàn tác được**

```bash
cp frontend/src/styles/responsive-chu.css "$SCRATCH/responsive-chu.TRUOC.css"
```

Rồi chạy lại bộ sinh Y NGUYÊN (chưa sửa gì) và `diff` với bản đang có. **Kỳ vọng: KHÔNG khác một
dòng nào.** Nếu khác, nghĩa là CSS nguồn đã đổi từ lúc sinh lần đầu — dừng lại, báo cáo phần khác
nhau đó TRƯỚC khi đi tiếp, vì lúc đó việc sinh lại sẽ kéo theo thay đổi ngoài ý định.

```bash
python "$SCRATCH/sinh_san_chu.py" frontend/src
diff "$SCRATCH/responsive-chu.TRUOC.css" frontend/src/styles/responsive-chu.css
```

- [x] **Bước 2: Liệt kê CHÍNH XÁC những gì thuộc "bản in"**

Đừng loại theo tên lớp — `.ptg-` có ít nhất hai họ khác nhau trong file (dòng 925-940 là bản in
phiếu tính giá, dòng 1162-1167 là `.ptg-table`/`.ptg-badge`/`.ptg-stat-label` của một màn KHÁC
hiện trên màn hình bình thường). Loại nhầm họ thứ hai là gỡ sàn chữ của một màn đang cần nó.

Hai tiêu chí ĐÚNG, dùng cả hai:

1. **Khai bên trong `@media print`** — hàm `quet()` hiện thu cả những khối này rồi hoisting chúng
   ra `@media (max-width: 768px)`, tức áp luật của giấy lên màn hình và ngược lại. Sửa `quet()`
   để bỏ qua mọi khối có tổ tiên là `@media print`.
2. **Nằm trong stylesheet của một tờ in** — thêm vào `BO_FILE`. Tự đi tìm danh sách file đó,
   đừng đoán: `grep -rln "@media print\|print-only\|@page" frontend/src --include=*.css` rồi ĐỌC
   từng file để phân biệt "file của tờ in" (toàn bộ file phục vụ một tờ giấy, ví dụ
   `pages/phieu-tinh-gia.css`, `components/print-sheet.css`) với "file màn hình có kèm vài luật in"
   (ví dụ `pages/bao-gia.css` — loại cả file là sai, tiêu chí 1 đã lo phần in của nó).

Ghi vào báo cáo: file nào bị loại cả file và VÌ SAO tin nó là tờ in.

- [x] **Bước 3: Sửa bộ sinh + sinh lại**

Sửa `sinh_san_chu.py` theo hai tiêu chí trên. Sửa luôn khối chú thích đầu file sinh ra: đoạn
"Ngoại lệ cố ý" hiện khai có ngoại lệ cho "chữ vẽ trong SVG" nhưng trong mã KHÔNG có bộ lọc nào
làm việc đó (`BO_BO_CHON` chỉ khớp `avatar`) — sửa cho khớp sự thật, và thêm ngoại lệ bản in.

Sinh lại, rồi `diff` với `responsive-chu.TRUOC.css`. **Đọc toàn bộ diff.** Mọi dòng biến mất phải
là bộ chọn của bản in. Một dòng nào biến mất mà không thuộc bản in ⇒ bộ lọc quá tay, sửa lại.
Báo cáo phải liệt kê số bộ chọn trước → sau và nhóm chúng theo lý do bị loại.

- [x] **Bước 4: Xác minh BẢN IN đã hết vỡ chữ**

Ở 375×812, mở phiếu tính giá `PTG-2026-0016` (bấm dòng đầu bảng), rồi
`await page.emulateMedia({ media: "print" })` — **ĐỪNG bấm nút "In phiếu"**, nó mở hộp in của hệ
điều hành và treo cả daemon dev-browser (xem mục cấm ở "Quy trình chuẩn").

Đo và chụp:
- Cỡ chữ thật của `.ptg-tbl thead th` — kỳ vọng trở lại **9px**, không còn 12px.
- Tiêu đề cột "NGUYÊN VẬT LIỆU" — kỳ vọng không còn ngắt giữa từ. **Mở ảnh ra nhìn**, đừng chỉ tin
  số đo.
- `tblScrollW` vs `sheetClientW` — kỳ vọng bằng nhau (không tràn).

- [x] **Bước 5: Xác minh MÀN HÌNH THƯỜNG không bị mất sàn chữ**

Đây là bước chống tác dụng phụ, đừng bỏ. Trên 3 màn hiện bình thường có chữ nhỏ — Nhật ký ·
Phòng ban · Yêu cầu nhập xuất — đo lại: **không phần tử nào có `font-size` tính được dưới 12px**.
Nếu có, bộ lọc đã loại nhầm; ghi rõ bộ chọn nào và sửa lại bộ lọc.

- [x] **Bước 6: Báo cáo**

Kèm: diff bộ chọn trước→sau, số đo bản in trước→sau, ảnh, kết quả bước 5, và câu trả lời cho câu
hỏi "còn tờ in nào khác trong hệ chưa kiểm không".

---


### Task 3: Kinh doanh › Báo giá in ấn (danh sách + ngăn kéo + bản in)

**Đường vào:** hamburger → **Báo giá in ấn**.

**Chỗ phải mở:**
- Nút **"+ Báo giá mới"**.
- Các tab lọc: Tất cả · Cần xử lý · Soạn · Chờ duyệt · Đã duyệt · Đã gửi khách · Khách chốt ·
  Đã lên đơn · Từ chối (dải này CUỘN NGANG — kiểm tab cuối có tới được không).
- Mở một báo giá → khối **phiên bản** (`.bgv .ver-item`, nút nhân bản `.v-clone` — đã vá §48,
  Task 0 xác minh), tab **Đính kèm**, nút **Xem bản in**.
- Bản in khách: đây là khung khổ giấy cố định, **KHÔNG vá theo màn hẹp** — chỉ kiểm nó cuộn được.

**Nghi can:** mã `BG26-0048` đã hết gãy dòng nhờ §52b. Bảng `.rdx-quote .q-card > table` đã có
`min-width: 860px`. Khối phiên bản và hộp đính kèm CHƯA rà.

- [x] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t3.txt`, ảnh tiền tố `t3`.
- [x] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [x] **Bước 3: Viết mục `§59`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [x] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [x] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 4: Kinh doanh › Khách hàng + Quy trình kinh doanh

Gộp hai màn nhẹ vào một task vì cùng phân hệ và cùng ít bảng.

**Đường vào:** **Khách hàng**, rồi **Quy trình kinh doanh**.

**Chỗ phải mở (Khách hàng):** nút thêm khách; mở một khách → các tab trong ngăn kéo
(Thông tin · **Chăm sóc** = lịch hẹn calendar · Đơn hàng · Công nợ). Lịch hẹn có popover kéo-dời —
kiểm popover có bị cắt mép màn không.

**Việc gộp từ Task 0 — xác minh §46 bằng toast THẬT:** tạo một lịch hẹn chăm sóc ở tab **Chăm
sóc**. Backend bắn sự kiện `hen_cham_soc_moi`, `AppShell.tsx:775` gọi `pushToast("📋 Bạn có hẹn
chăm sóc mới: …")`. Chụp lúc toast đang hiện, đo `.apx-toastwrap`: kỳ vọng `bottom: 76px`,
`top: auto`, hộp nằm nửa DƯỚI màn. Task 0 mới chỉ chứng minh được bằng node dựng thủ công.

**Chỗ phải mở (Quy trình kinh doanh):** 6 chip làn (Tất cả · Khách hàng · Kinh doanh · Sản xuất ·
Kho · Giao hàng); ô tìm bước; ba nút phóng to `-` `100%` `+` `↺`; bấm vào từng NÚT BƯỚC trong sơ
đồ (Yêu cầu báo giá, Xác nhận đơn hàng, …) xem có mở gì không.

**Nghi can:** §38 đã vá ngăn kéo khách hàng — kiểm còn sót. Sơ đồ `.qtkd__board` cuộn ngang
994px: kiểm nút bước ở rìa phải có bấm tới được không.

- [x] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t4.txt`, ảnh tiền tố `t4`.
- [x] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [x] **Bước 3: Viết mục `§60`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [x] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [x] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 5: Sản xuất › Kế hoạch sản xuất (danh sách + ngăn kéo lệnh)

**Đường vào:** **Kế hoạch sản xuất**.

**Chỗ phải mở:**
- Hai tab: **Hàng chờ tiếp nhận** · **Lệnh sản xuất** (dải tab này CUỘN NGANG và tab thứ hai đang
  bị cắt một nửa ở 375px — xem ảnh `B0a-n1.png`; cân nhắc hạ `gap` từ 24px xuống 8-12px để vừa,
  nhưng ĐO trước rồi mới chốt).
- Bấm một đơn ở "Hàng chờ tiếp nhận" → hộp tiếp nhận.
- Mở một lệnh → 5 tab **Thông tin chung · Quy cách · Công đoạn · Vật tư · Nhật ký**; nút
  **Chép mã**; nút **Mở bàn Kế hoạch sản xuất ↗**.
- Tab **Công đoạn** chứa **sơ đồ định tuyến DAG** (`DagRoutingCanvas`) — đây là nơi DUY NHẤT sơ đồ
  này xuất hiện. Kéo/thả khối, bấm nút xoá dây (`.dag-wire-delete`, đã vá §48 và Task 0 đã xác
  minh `opacity: 0.75`), đổi qua chế độ bảng.

**Nghi can:** lưới KPI trong ngăn kéo (SL ĐẶT / VÀO MÁY / GIẤY NGUYÊN / BÌNH BÀI / CÔNG ĐOẠN /
VẬT TƯ / HẠN GIAO / CÔNG THỢ) hiện đã 2 cột và nhìn ổn — xác nhận lại. Bảng công đoạn + bảng vật tư
trong tab CHƯA rà.

- [x] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t5.txt`, ảnh tiền tố `t5`.
- [x] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [x] **Bước 3: Viết mục `§61`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [x] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [x] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 6: Sản xuất › Bài ghép (sâu, không chỉ thanh công cụ)

**Đường vào:** **Bài ghép**.

**Chỗ phải mở:** ô tìm kiếm + cụm số đếm (đã vá §44 — xác nhận); mở một bài ghép → **sơ đồ bình
bài** (kéo/thả, phóng to), bảng thông số, nút đổi khổ, nút tính nghịch.

**Nghi can:** sơ đồ vẽ bằng SVG/canvas — kiểm nó co theo bề ngang màn hay tràn. `bai-ghep.css:1351`
đã có nhánh `@media (hover: none)`, không cần vá lại.

- [x] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t6.txt`, ảnh tiền tố `t6`.
- [x] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [x] **Bước 3: Viết mục `§62`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [x] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [x] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 7: Sản xuất › Xếp lịch công đoạn ("một bàn làm việc" + Gantt)

**Đường vào:** **Xếp lịch công đoạn**.

**Chỗ phải mở:** dải chọn máy/tổ; **Gantt theo máy**; bấm một thanh lệnh trên Gantt → hộp chi tiết;
danh sách **Xung đột & Nguy cơ trễ**; nút phát hành.

**Nghi can:** Gantt là màn rộng nhất hệ thống. Nhiều khả năng phải cho cả khung cuộn ngang + khoá
cột nhãn máy. Đây là task NẶNG nhất — nếu quá lớn, tách bước "Gantt" thành task riêng và ghi rõ.

- [x] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t7.txt`, ảnh tiền tố `t7`.
- [x] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [x] **Bước 3: Viết mục `§63`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [x] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [x] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 8: Sản xuất › Sửa chữa máy + Phiếu bảo trì

**Đường vào:** **Sửa chữa máy**, rồi **Phiếu bảo trì**.

**Chỗ phải mở:** nút tạo phiếu sửa chữa; mở một phiếu (vd SC-0009) → **cửa ảnh chứng thực** (khối
tải ảnh — kiểm ô tải ảnh và ảnh xem trước có tràn không); bảng lịch bảo trì.

**Đã ghi nhận (lỗi NGHIỆP VỤ, không phải giao diện — báo cáo chứ đừng tự vá):** phiếu SC-0009 có
tiêu đề ghi máy BE-04 nhưng ô **"Máy *"** lại hiện "— Chọn máy —"; danh mục máy có ba bản ghi trùng
`BE-01-COPY`, `BE-01-COPY2`, `BE-01-COPY3`.

- [x] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t8.txt`, ảnh tiền tố `t8`.
- [x] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [x] **Bước 3: Viết mục `§64`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [x] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [x] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.
- [x] **Bước 6:** Ghi hai lỗi nghiệp vụ trên vào báo cáo, KHÔNG tự sửa.

---

### Task 9: Sản xuất › Thực hiện SX — 6 màn tổ (Chế bản · In offset · Cán màng · Bế & Xén · Đóng gói · …)

**Đường vào:** các mục tổ được AppShell tiêm động vào sidebar.

**Đặc thù:** đây là màn cho THỢ, thiết kế TEXTLESS (QR / icon / màu / nút to). Lens nghiệm thu
riêng: *"người không biết chữ có dùng được không"* — nút phải to, biểu tượng phải rõ, không dựa
vào chữ nhỏ.

**Nghi can:** §35 đã vá "bàn làm việc 3 cột không chịu gập". Cần kiểm: nút ghi sản lượng, hộp quét
QR, hộp báo lỗi/lý do, nút KCS.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t9.txt`, ảnh tiền tố `t9`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§65`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.
- [ ] **Bước 6:** Nghiệm thu thêm bằng lens "không biết chữ": mỗi nút chính có đạt tối thiểu
      44×44px không; biểu tượng có ≥ 24px không. Ghi số đo.

---

### Task 10: Thu mua › Mua hàng + Nhà cung cấp

**Đường vào:** **Mua hàng**, rồi **Nhà cung cấp**.

**Chỗ phải mở (Mua hàng):** tab **Yêu cầu chờ xử lý** → bấm một dòng = lập đơn (hộp
`purchase__form-section-head` đã vá §43 — xác nhận); bảng dòng hàng trong đơn.

**Chỗ phải mở (Nhà cung cấp):** nút **"+ Thêm NCC"** → hộp 2 tab **Thông tin chung** ·
**Bảng giá vật tư**; mở một NCC → tab đánh giá.

**Nghi can:** hộp "Thêm nhà cung cấp mới" nhìn ổn trên ảnh `B2a-n1b.png`; tab "Bảng giá vật tư"
CHƯA mở lần nào — nhiều khả năng có bảng rộng.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t10.txt`, ảnh tiền tố `t10`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§66`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 11: Kế toán › Đơn mua hàng + Phiếu chi

**Đường vào:** **Đơn mua hàng**, rồi **Phiếu chi** (nhãn có thể là "Phiếu chi / UNC" tuỳ cờ
`UNC_ENABLED` ở `constants/features.ts:15`).

**Chỗ phải mở:** nút lập phiếu chi; hộp chọn đợt giao; bảng đối chiếu hoá đơn; nút in UNC.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t11.txt`, ảnh tiền tố `t11`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§67`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 12: Kho hàng › Yêu cầu nhập xuất (4 tổ hợp tab) + Báo cáo kho

**Đường vào:** **Yêu cầu nhập xuất**.

**Chỗ phải mở:** 2 tab VIỆC × 3 chiều = **Yêu cầu / Phiếu từ yêu cầu** × **Nhập / Xuất / Điều
chuyển** — phải đi HẾT sáu tổ hợp, mỗi tổ hợp lăn xuống + lăn ngang; ô chọn kho (`vsd ▾`); ô chọn
số dòng mỗi trang (`10 / trang ▾`); nút **Tạo yêu cầu** → hộp tạo; mở một yêu cầu → hộp cấp phát.

Rồi **Báo cáo kho**: sổ nhập-xuất, khoá kỳ, xuất MISA.

**Nghi can:** ô rỗng đã vá §56 (Task 0 xác minh). *Lưu ý dữ liệu:* tab "Phiếu từ yêu cầu" với bộ
lọc mặc định (Nhập · Cần cấp) hiện ĐÃ CÓ dòng, không còn rỗng — muốn xem trạng thái rỗng phải
chuyển chip lọc sang "Đã hủy". Bảng `rc__tablewrap kho-table-card` thừa 608px
— kiểm cột cuối tới được không.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t12.txt`, ảnh tiền tố `t12`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§68`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 13: Kho hàng › các kho đã khai báo (Giấy · NVL · Thành phẩm · Vật tư & Mực · Tồn kho)

**Đường vào:** các mục kho được AppShell tiêm động dưới section **Kho hàng**.

**Chỗ phải mở:** mở một mặt hàng → thẻ "hero" (đã vá §51 — xác nhận), **bảng báo giá NCC**
(đã vá §51 — xác nhận), tab ảnh vật liệu, nút chuyển kho, hộp QR.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t13.txt`, ảnh tiền tố `t13`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§69`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 14: Cấu hình danh mục — nhóm A (Loại sản phẩm · Công đoạn · Thiết bị & Máy móc · Khuôn)

Bốn màn này đều là `CatalogListPage` + `CatalogDrawer` nên lỗi thường CHUNG — vá một lần ăn cả bốn.

**Đường vào:** lần lượt 4 mục trong **Cấu hình danh mục**.

**Chỗ phải mở:** nút thêm; mở một bản ghi → ngăn kéo (`.rc-drawer__head` đã vá §50 — xác nhận);
với **Công đoạn** mở khối công thức; với **Thiết bị & Máy móc** mở tab **Lịch bảo trì**.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t14.txt`, ảnh tiền tố `t14`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§70`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 15: Cấu hình danh mục — nhóm B (Đơn vị & quy đổi · Bù hao · Công việc khoán · Lý do & lỗi SX)

**Nghi can:** **Bù hao** đã vá §40 (bảng dải, ô nhập 76px) — xác nhận lại. **Đơn vị & quy đổi** có
bảng cầu quy đổi hai chiều, CHƯA rà. **Công việc khoán** có bảng đơn giá nhiều công đoạn, CHƯA rà.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t15.txt`, ảnh tiền tố `t15`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§71`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 16: Cấu hình danh mục — nhóm C (Chủng loại giấy · Giấy · Vật tư khác · Thành phẩm · Khai báo kho)

**Nghi can:** bốn màn hàng hoá chung bảng `vat_tu_in_an` nên giao diện gần giống nhau. **Giấy** có
ô đơn giá/kg + khổ; **Thành phẩm** là hệ tự khai. **Khai báo kho** có lưới cấu hình.

Cả nhóm còn có nút **Xuất/Nhập Excel** (13 màn dùng chung hộp `ImportExcelDialog`) — mở hộp đó,
kiểm bảng xem trước lỗi (`rc__tablewrap` có `maxHeight: 40vh`) trên màn hẹp.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t16.txt`, ảnh tiền tố `t16`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§72`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 17: Nhân sự & Lương › Chấm công (mọi tab) + Nghỉ phép + Tăng ca

**Nghi can:** §39 đã vá tab "Lịch & ngày lễ". Các tab CHƯA rà: **Bảng công của tôi**, **Chốt
công**, **Vị trí chấm công** (có bản đồ radar GPS 2D — nhiều khả năng tràn), **Thiết lập**.

**Chỗ phải mở:** hộp khai vị trí (`LocationForm`), bản đồ `GpsRadarMap2D`, hộp duyệt nghỉ phép,
hộp đăng ký tăng ca.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t17.txt`, ảnh tiền tố `t17`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§73`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 18: Nhân sự & Lương › Lương + Nội quy công ty + Hồ sơ của tôi

**Nghi can:** bảng lương là bảng rộng nhất trong phân hệ nhân sự (nhiều cột khoản). **Hồ sơ của
tôi** có nhiều tab CHƯA rà hết.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t18.txt`, ảnh tiền tố `t18`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§74`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 19: Sản xuất › Kế hoạch vật tư

**Lưu ý:** module này đang được một PHIÊN KHÁC phát triển (`backend/app/services/ke_hoach_vat_tu_service.py`
đang có thay đổi chưa commit). **Chỉ sửa CSS lớp phủ, tuyệt đối không chạm file của module.**
Nếu màn còn đang dở, ghi "hoãn tới khi module chốt" và bỏ qua — đừng vá lên giao diện sắp đổi.

- [ ] **Bước 1: Chạy quy trình 7 bước** (mục "Quy trình chuẩn cho MỘT module" ở đầu file này):
      vào màn → lăn xuống từng nấc 300px chụp từng nấc → lăn ngang khung rộng nhất 3 nấc → bấm hết
      nút/tab an toàn (chụp + đóng popup sau mỗi lần) → mở bản ghi đầu rồi lặp lại → đo bằng số.
      Log `V_t19.txt`, ảnh tiền tố `t19`.
- [ ] **Bước 2: Mở TẤT CẢ ảnh vừa chụp ra nhìn.** Liệt kê lỗi theo sáu khuôn ở bảng đầu file; mỗi
      lỗi ghi rõ: ảnh nào chứng minh, selector nào hỏng, `file:line` của CSS gốc.
- [ ] **Bước 3: Viết mục `§75`** ở cuối `frontend/src/styles/responsive.css` — một mục cho cả
      module, nhóm theo khuôn, mở đầu bằng chú thích tiếng Việt ghi triệu chứng đã chụp + nguyên
      nhân + vì sao chữa như vậy.
- [ ] **Bước 4: Thao tác lại ĐÚNG những chỗ vừa sửa** bằng chuột/bàn phím thật, chụp ảnh sau, đo
      số trước–sau (bề ngang ô, số dòng, `scrollWidth/clientWidth`, có chồng nhau không).
- [ ] **Bước 5: Kiểm cân ngoặc** (`depth 0`), đánh dấu `- [x]` vào bảng theo dõi, báo cáo cụ thể
      đã bấm gì / gõ gì / thấy gì ở từng bước.

---

### Task 20: Rà lượt cuối — Dashboard, Giao hàng, Nhật ký, và quét lại toàn hệ

**Files:**
- Modify: `frontend/src/styles/responsive.css` (§76 nếu còn sót)

- [ ] **Bước 1: Quét lại 6 khuôn trên TOÀN BỘ màn đã sửa**

Chạy bộ đo (tràn màn · chồng chữ · chữ ≥22px · bảng chết cuộn) lần lượt qua mọi màn trong sidebar,
2 trình duyệt một đợt. Mục tiêu: danh sách rỗng.

- [ ] **Bước 2: Kiểm hồi quy trên màn RỘNG**

Đổi khổ về 1440×900, mở lại 8 màn đại diện, chụp ảnh. Mọi luật đều nằm trong `@media (max-width:
768px|1024px)` nên màn rộng PHẢI không đổi — nếu đổi là có luật viết lọt ra ngoài media query.

- [ ] **Bước 3: Ghi ba lỗi nghiệp vụ đã phát hiện vào báo cáo (KHÔNG tự sửa)**

1. `frontend/src/api/client.ts:88` — chuỗi lỗi bằng tiếng Anh trên giao diện tiếng Việt:
   `"Cannot reach the server. Check your connection and try again."`
2. **Dashboard** vẫn là trang giữ chỗ bằng tiếng Anh.
3. **Nhật ký** hiện tên hành động bằng tiếng Anh (`Approve Purchase Request`,
   `purchase_request:10`) thay vì tiếng Việt.

- [ ] **Bước 4: Cập nhật bộ nhớ**

Cập nhật `.claude/projects/D--jobs-SVN/memory/bay-giao-dien-dien-thoai-svn.md`: bổ sung khuôn 5
(chồng chữ) và khuôn 6 (chữ quá khổ) vào danh sách bốn khuôn hiện có.

- [ ] **Bước 5: Xin phép commit**

Liệt kê ĐÍCH DANH file của việc này (`frontend/src/styles/responsive.css`,
`frontend/src/components/AppShell.tsx`, `docs/superpowers/plans/2026-08-31-giao-dien-dien-thoai.md`)
rồi HỎI chủ dự án. Cấm `git add -A` — cây làm việc có thay đổi của phiên khác.

---

## Bảng theo dõi

| Task | Module | Mục CSS | Xong |
|------|--------|---------|------|
| 0 | Trả nợ xác minh §46 §48 §56 | — | [ ] |
| 1 | Quét cỡ chữ toàn hệ | §57 | [ ] |
| 2 | Tính giá | §58 | [ ] |
| 3 | Báo giá in ấn | §59 | [ ] |
| 4 | Khách hàng + Quy trình kinh doanh | §60 | [ ] |
| 5 | Kế hoạch sản xuất | §61 | [ ] |
| 6 | Bài ghép | §62 | [ ] |
| 7 | Xếp lịch công đoạn | §63 | [ ] |
| 8 | Sửa chữa máy + Phiếu bảo trì | §64 | [ ] |
| 9 | Thực hiện SX (6 màn tổ) | §65 | [ ] |
| 10 | Mua hàng + Nhà cung cấp | §66 | [ ] |
| 11 | Đơn mua hàng + Phiếu chi | §67 | [ ] |
| 12 | Yêu cầu nhập xuất + Báo cáo kho | §68 | [ ] |
| 13 | Các kho đã khai báo | §69 | [ ] |
| 14 | Danh mục nhóm A | §70 | [ ] |
| 15 | Danh mục nhóm B | §71 | [ ] |
| 16 | Danh mục nhóm C | §72 | [ ] |
| 17 | Chấm công + Nghỉ phép + Tăng ca | §73 | [ ] |
| 18 | Lương + Nội quy + Hồ sơ của tôi | §74 | [ ] |
| 19 | Kế hoạch vật tư | §75 | [ ] |
| 20 | Rà lượt cuối + hồi quy màn rộng | §76 | [ ] |
