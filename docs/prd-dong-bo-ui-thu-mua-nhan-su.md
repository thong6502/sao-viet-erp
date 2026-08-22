# PRD — Đồng bộ UI: THU MUA & NHÂN SỰ / LƯƠNG

**Nguồn**: audit UI/UX 05/08/2026 (26 lỗi) + đối chiếu code ngày 08/08/2026.
**Phạm vi**: 3 màn Thu mua + 8 màn Nhân sự & Lương. **Không** đụng nghiệp vụ tính toán, **không** viết lại, **không** sửa `styles/global.css`.
**Chuẩn tham chiếu**: `docs/UI_DESIGN.md` (đã có, 253 dòng) — PRD này trỏ vào nó, không chép lại.

**Ba quyết định của chủ, chốt ngày 08/08/2026** (chi tiết mục 7):

| | Câu hỏi | Chủ chốt | Hệ quả |
|---|---|---|---|
| 7.1 | Nội quy công ty nằm nhóm nào | **Chuyển xuống Nhân sự** | Đổi 1 chỗ trong sidebar, eyebrow = `Nhân sự & Lương` |
| 7.2 | Xuất Excel: đổi nhãn hay làm file thật | **Làm file `.xlsx` THẬT** | Việc đổi từ NHỎ → VỪA và **kéo theo backend**. Xem 3.2 và 4 |
| 7.3 | Radar Chấm công | **Tô lại, KHÔNG gỡ** | Giữ chức năng báo trong/ngoài vùng chấm công. Đợt 3 |

---

## 0. Chốt trong một trang

| Việc | Số màn | Đợt |
|---|---|---|
| Mất đường tới dữ liệu (bảng cắt im lặng, lỗi API đọc thành "chưa có") | 3 | 1 |
| Ngày tháng tiếng Anh · gõ 1 phím = 1 request | 4 | 1 |
| Xuất `.xlsx` THẬT cho Hồ sơ nhân sự (có backend) | 1 | 1 |
| Đồng bộ nút chính, eyebrow, cột thao tác, empty state, pager | 11 | 2 |
| Thẻ KPI Nhà cung cấp, radar Chấm công, tách `.eyebrow` | 3 | 3 |
| URL riêng cho từng màn (D02) | toàn app | Đợt R (nhánh riêng) |
| 2 lần click mới đổi màn (D01) | toàn app | **Chưa giao dev — chờ QA** |

**Ba quyết định đã chốt** (mục 7). Còn D01 và D02 chờ QA / chờ chọn phương án.

---

## 1. KHÔNG LÀM — và vì sao

Đọc mục này trước. Ai làm mấy việc dưới đây là làm thừa.

### 1.1 Đã lỗi thời — code hiện tại đã khác báo cáo

| Mã | Báo cáo nói | Code thật hôm nay | Kết luận |
|---|---|---|---|
| D13 | "3 màn Thu mua, nút Tìm mỗi màn một kiểu" | Cả 3 màn **đã bỏ nút Tìm** (comment: `SuppliersPage.tsx:643-645`, `DepartmentPurchaseRequestsPage.tsx:455-457`, `PurchaseRequestsPage.tsx:1282-1284, 1431-1433`) | Bỏ. Chỉ còn phần **vị trí ô tìm** + debounce là việc thật |
| D16 | "kiến trúc header không đồng nhất" (Thu mua) | 3 màn **đã cùng khuôn** `md-page__head` + `eyebrow` + `h1` + `sub` | Bỏ phần header. Chỉ còn phần **vị trí nút chính** |
| D17 | "tên cột lúc Thao tác lúc Hành động" (Thu mua) | 4/4 bảng Thu mua **đã là "Thao tác"** | Bỏ trong Thu mua. **Còn đúng** ở Lương (`LuongPage.tsx:1575, 3008, 3577` = "Hành động") → làm bên đó |
| D15 | "trộn Không có / Chưa có" (Thu mua) | 3 màn Thu mua **100% dùng "Chưa có"**; các câu "Không…" còn lại là thông báo lỗi | Bỏ vế "trộn". Vế "sơ sài" **còn đúng và nặng** → làm |

### 1.2 Ngoài phạm vi — phân hệ khác

| Mục | Màn | Vì sao không làm |
|---|---|---|
| D04 · D10 · D12 · D14 · D15 · D16 · D17 | **Đơn mua hàng · Phiếu chi · Công nợ phải trả** | Sidebar xếp cả 3 vào section **Kế toán** → item cha "Kế toán thu mua" (`Sidebar.tsx:110-134`). Là phân hệ Kế toán, không phải Thu mua. Đụng vào là kéo theo `PaymentReceiptsPage` + `AccountingBankAccountsPage` (dùng chung `accounting.css`, có `!important` ở `:16`) — hai màn **đã bị gỡ khỏi menu**, không ai QA được |
| D01 nhánh "menu cha nuốt click đầu" | Kế toán thu mua | `Sidebar.tsx:364` — mục **duy nhất** có `children` là "Kế toán thu mua". Lỗi thật, sửa 1 dòng, nhưng thuộc Kế toán. Ghi backlog |
| Gom 7 họ thẻ KPI toàn app | Báo giá · KHSX · Khách hàng · Đơn hàng bán | D12 đếm được `summary-card`, `metric-card`, `stat-card`, `cc-ts-kpi-card`… ở phân hệ khác. Trong PRD này chỉ đụng **một** thẻ: `supplier-stat-card` |
| Nhấc `EmptyState` từ `pages/keHoachSxShared.tsx:345` lên `components/` | Sản xuất · Bài ghép · Xếp lịch · LSX | Đổi đường import của 4 màn Sản xuất đang chạy tốt. **Thay vào đó**: tạo `components/EmptyState.tsx` MỚI, bê nguyên dáng, không động vào bản Sản xuất. Nợ kỹ thuật có chủ ý — ghi 1 dòng TODO để hợp nhất khi Sản xuất vào phạm vi |
| Sửa `.btn--primary` / `.btn--accent` trong `styles/global.css` | toàn hệ thống | 49 chỗ khai `primary`, 44 chỗ khai `accent`, **233 chỗ dùng `<Button>` không khai variant**. Đổi ở gốc = đổi màu hàng trăm nút trong một nhát, mọi ảnh chụp hướng dẫn cũ lệch. **CẤM** |
| Đổi drawer Nhà cung cấp thành modal (hoặc ngược lại) | Nhà cung cấp | Drawer chứa layout tab + luồng nhập/xuất Excel vật tư — **phần vừa sửa 05-06/08**. Đụng vào là dễ vỡ nhất, mà chỉ để "cho giống". Giữ nguyên: modal và drawer là hai vai khác nhau (sửa nhanh vs. làm việc lâu trong hồ sơ) |
| Thêm CTA "Tạo phiếu mua" ở toolbar màn Mua hàng | Mua hàng | `openCreatePurchaseRequest(row)` **luôn** khởi từ một YCMH (kéo theo dòng vật tư + gợi ý NCC). Nút cấp trang buộc phải quyết định "phiếu rỗng hay bắt chọn YCMH" — đó là **mở nhánh nghiệp vụ mới**, không phải việc UI. Chỉ gỡ cái spacer treo vô nghĩa |
| Thêm cột "Thao tác" vào bảng Hồ sơ nhân sự | Hồ sơ nhân sự | Bảng đang click cả dòng để mở drawer (`NhanSuPage.tsx:717-721`). Thêm cột = phải chặn bubbling khắp nơi, đổi thói quen người dùng, không được gì |
| Gộp `ns__kpi` về dạng thẻ | Hồ sơ nhân sự | `nhan-su.css:129-133` ghi rõ: đã **cố ý** hạ 4 card cao 90px xuống dải pill 34px để trả ~62px cho bảng. Nó là **bộ lọc**, không phải thẻ thống kê. Đi ngược quyết định cũ |

### 1.3 Chờ xác nhận trước khi giao dev

| Mã | Vì sao chưa giao | Ai làm bước tiếp |
|---|---|---|
| **D01** (2 lần click) | Cơ chế chứng minh được bằng code, nhưng **chưa tái hiện được**. Xem mục 7 | **QA** dựng lại lỗi bằng e2e |
| ~~D25~~ | **ĐÃ CHỐT 08/08**: tô lại, không gỡ. Vẫn phải dọn 3 khối CSS trùng TRƯỚC — xem 7.3 | Dev, đợt 3 |
| ~~D21~~ | **ĐÃ CHỐT 08/08**: làm file `.xlsx` thật, có backend — xem 7.2 | Dev, đợt 1 |
| **D02** (URL riêng) | Việc LỚN, không tách theo phân hệ được | **Chủ** chốt phương án (mục 6) |

---

## 2. CHUẨN CHUNG — mỗi hạng mục MỘT quy tắc

Áp cho **mọi** màn trong phạm vi. Màn mẫu là màn đang làm đúng — bám theo, đừng sáng tác.

### 2.1 Header trang

**Quy tắc**: đủ **3 tầng, đúng thứ tự** — `eyebrow` → `h1` 26px → `sub` một câu.
**Màn mẫu**: `frontend/src/pages/PurchaseRequestsPage.tsx:1248-1255` (CSS `pages/master-data.css:10-24`).
**Không** bắt đổi `ns__title`/`ns__sub` sang `md-page__*` — giữ class cũ, chỉ **bổ sung tầng eyebrow**. Đổi class kéo theo canh dòng của `ns2__headact` (`nhan-su.css:48-57`), không đáng.

| Trước | Sau |
|---|---|
| `ns__title` + `ns__sub`, không eyebrow (5 màn NS&L) | `.eyebrow` + `ns__title` + `ns__sub` |
| `<div className="ns__eyebrow">` — **class không có CSS ở bất kỳ file nào**, render chữ thường 15px (`NoiQuyPage.tsx:176`) | `<p className="eyebrow">` — micro-label 10px mono HOA, `global.css:25-33` |

Cảnh báo dev: thêm eyebrow đẩy `ns__title` xuống ~14-16px → phải soát lại canh dòng cụm nút header ở `NhanSuPage.tsx:510-531`.

### 2.2 Eyebrow — nội dung

**Quy tắc**: eyebrow = **tên SECTION trong sidebar, chép nguyên văn, một cấp**. Không ghi tên item, không ghi hai cấp.
**Màn mẫu**: `frontend/src/pages/DepartmentsPage.tsx:1474` → `<p className="eyebrow">Nhân sự &amp; Lương</p>`, khớp `Sidebar.tsx:179`.

| Màn | Trước | Sau |
|---|---|---|
| Yêu cầu mua hàng | `Phòng ban` | `Thu mua` — và `md-page__sub` phải nói rõ vai, vì màn mở cho 6 nhóm quyền (`Sidebar.tsx:96-103`): *"Phòng ban của bạn gửi yêu cầu vật tư sang Thu mua."* |
| Mua hàng · Nhà cung cấp | `Thu mua` | giữ nguyên |
| Hồ sơ nhân sự · Chấm công · Nghỉ phép · Tăng ca · Lương | (không có) | `Nhân sự & Lương` |
| Nội quy công ty | `HÀNH CHÍNH NHÂN SỰ` (gõ HOA tay, class chết) | phụ thuộc quyết định 7.1 |

**Cấm**: dùng lại `.eyebrow` làm nhãn section trong thân trang. Hiện đang bị dùng 5 chỗ (`PurchaseRequestsPage.tsx:1260, 1657`; `DepartmentPurchaseRequestsPage.tsx:633, 677, 698`) — một lớp gánh 2 vai, restyle eyebrow là vỡ thân trang. Tách sang `.md-page__section-label` (chép y nguyên khai báo hiện tại, không đổi hình). **Đợt 3.**

### 2.3 Nút chính

**Nguồn sự thật**: `docs/UI_DESIGN.md:54` — `--rust` `#c5400a` là màu nút hành động chính; `UI_DESIGN.md` §5 — `--charcoal` `#0f172a` là **chip lọc đang chọn**. Code đặt tên ngược (`.btn--primary` = ink = navy), nên ai đọc doc rồi gõ `variant="primary"` sẽ ra navy.

**Quy tắc chốt cho 2 phân hệ này**:

| Vai | Dùng | Ghi chú |
|---|---|---|
| Hành động chính (tạo mới · gửi · khởi tạo · submit · chốt kỳ) | `variant="accent"` | **Tối đa MỘT nút cam** trên mỗi màn và mỗi hộp thoại |
| Hành động phụ | `variant="ghost"` | |
| Hành động phá huỷ / từ chối | `variant="danger"` | |
| `variant="primary"` (navy) | **không dùng nữa** trong 2 phân hệ | Navy đang trùng màu chip lọc đang chọn → nhìn không phân biệt được "nút bấm được" với "bộ lọc đang bật" |
| Nút tự vẽ ngoài hệ `.btn` | **cấm** | |

**Hệ quả bắt buộc**: `ns__kpi.is-active` hiện nền **cam** (`nhan-su.css:134-231`) — pill lọc mà cam là phạm đúng luật trên. Đổi nền active sang `--charcoal`. Việc này đi kèm D04, không tách.

| Trước | Sau | File |
|---|---|---|
| `+ Thêm NCC` = primary/navy | accent | `SuppliersPage.tsx:664` |
| `+ Tạo yêu cầu mua` = primary/navy | accent | `DepartmentPurchaseRequestsPage.tsx:473` |
| `Lưu hợp đồng` = ghost, cạnh `Ghi đợt giao` = accent **trong cùng một DetailModal** | accent | `PurchaseRequestsPage.tsx:2437-2447` vs `:2601-2609` |
| `ns-btn-primary` — gradient cam tự chế `linear-gradient(135deg,#c5400a,#ea580c)` + shadow cam | `<Button variant="accent">`, xoá class | `NhanSuPage.tsx:522-529`, `nhan-su.css:79-100` |
| `cc-btn-cta-compact` — ép `background:#0f172a !important`, navy hardcode không qua token | `<Button variant="accent">` | `NghiPhepPage.tsx:414, 426, 1014`, `nghi-phep.css:148-162` |
| `↻ Tính lại` navy **và** `Khởi tạo bảng lương` cam — cùng việc sinh bảng lương, hai màu | cả hai accent (hai nút không hiện đồng thời). Nếu QA thấy chúng hiện cùng lúc: Khởi tạo giữ accent, Tính lại hạ ghost | `LuongPage.tsx:483-489` và `:731-739` |
| `Chốt kỳ` = `cc-ts-btn-lock` navy | accent + giữ ConfirmDialog | `ChamCongPage.tsx:6335-6339` |
| `<Button variant="primary">` | accent | `NoiQuyPage.tsx:181-183` |

Cảnh báo dev: `cc-btn-cta-compact` viết **toàn `!important`** (padding, radius, border, shadow) — gỡ class là nút mất hình dạng, phải thay đủ 6 thuộc tính.

### 2.4 Empty state

**Quy tắc**: tạo `frontend/src/components/EmptyState.tsx` (icon 44px + title + sub + action tuỳ chọn), CSS `components/empty-state.css`. Mọi ô rỗng trong 2 phân hệ dùng nó.
**Màn mẫu dáng**: `frontend/src/pages/BaiGhepPage.tsx:335-343`. **Màn mẫu 2 nhánh lọc/rỗng**: `XepLichPage.tsx:730` (nút *Xoá lọc*) và `:741`. **Màn mẫu nhánh lỗi**: `AccountingPayablesPage.tsx:286-309`.

**Luật chữ — ba ca, không được gộp**:

| Ca | Câu | Hành động kèm |
|---|---|---|
| Có từ khoá / bộ lọc đang bật, kết quả rỗng | `Không tìm thấy … phù hợp` | nút **Xoá lọc** |
| Danh sách trống hoàn toàn | `Chưa có …` | CTA tạo mới (nếu người dùng có quyền) |
| **API lỗi** | `Chưa đọc được số liệu — xem thông báo lỗi ở trên` | **cấm** đổ về câu "Chưa có" |

Ca thứ ba là lỗi thật, không phải thẩm mỹ: khi API chết mà bảng in "Chưa có…", người đọc lướt tưởng thật sự không có dữ liệu. `AccountingPayablesPage.tsx:42-44` ghi luật sống còn *"im lặng không được đồng nghĩa với hết nợ"* — luật đó áp cho cả 2 phân hệ này.

**Điều kiện tiên quyết (làm trước, không được bỏ)**: class `ns__empty` đang dùng **chung cho cả trạng thái ĐANG TẢI** (`NhanSuPage.tsx:937, 3196, 3283, 3349`; `ChamCongPage.tsx:1623, 2654, 4258, 6364, 7052`). Tô nó thành khối cao có icon là mọi màn lúc tải sẽ **nhảy layout rồi co lại**. Phải tách class trạng thái tải (`ns__loading`) **trước** khi tô.

| Trước | Sau |
|---|---|
| `.md-page__empty` và `.md-page__status` — **không một dòng CSS nào trong toàn repo** (đã grep hết `*.css`), ô rỗng là `<td>` mặc định: chữ thường, canh trái, không icon, không CTA | `<EmptyState>` |
| `ns__empty` dùng >25 chỗ, không CSS, vài chỗ chèn `style` tay đỡ xấu (`NghiPhepPage.tsx:1028` padding 40, `:1317` padding 32px 16px) | `<EmptyState>` + `ns__loading` riêng |
| `nqr__state` chỉ set height 180px (`noi-quy.css:37`) | `<EmptyState>` |
| `lg-table-empty-state` (`luong.css:725-760`), `el-empty`, `.pdot__empty` (`purchase.css:1182-1189`) — đã đầy đủ | giữ, dùng làm tham chiếu; hợp nhất ở đợt sau |
| `Không có ai sắp hết thử việc.` và `Chưa có nhân viên nào.` nằm **trong cùng một ô** (`NhanSuPage.tsx:794-795`) | tách đúng ca theo bảng trên |

Cảnh báo dev: các ô này là `<td colSpan={…}>` tính tay, riêng `SuppliersPage.tsx:739` là `colSpan={canUpdate ? 5 : 4}` — **số cột đổi theo quyền**. Bọc thêm div mà quên giữ biểu thức là ô rỗng lệch cột với người không có quyền sửa.

### 2.5 Thẻ thống kê

**Quy tắc**: dải **pill gộp** theo `UI_DESIGN.md:88-99` — inline-flex, r99, cao ~38px, vòng icon 26px + số + nhãn, vạch chia 1px×18px. **Cấm** 4 thẻ cao ≥80px xếp 4 cột. Icon lấy từ `components/Icons.tsx`, **cấm emoji**.
**Màn mẫu**: `frontend/src/pages/DepartmentsPage.tsx:1482-1512` (CSS `redesign-phong-ban.css:33`). Bản tokens-hoá sạch hơn để tham khảo: `payables.css:8-95` (chỉ đọc, không sửa — ngoài phạm vi).

| Trước | Sau |
|---|---|
| `supplier-stat-card` — 3 thẻ cao, icon là **emoji** 🏢 / ✓ / – (`SuppliersPage.tsx:594-622`, `purchase.css:829-903`); là bản clone lệch của `cc-calendar-stat-card` (khác r-3/r-5, `--rule`/`--rule-soft`, box-shadow hard-code, không hover) | dải pill + `<Icon>` |
| `.md-page__stat-card` / `.md-page__stats` — đã có sẵn ở `master-data.css:27-57` nhưng **không file .tsx nào dùng** (CSS chết) | **xoá**, đừng hồi sinh: nó là dạng thẻ, đã bị `UI_DESIGN.md` §4 loại |

Cảnh báo dev: emoji ✓ và – đang được canh bằng font-size riêng cho từng biến thể (`purchase.css:861-871`: `--green`/`--amber` 20px trong khi mặc định 18px). Chuyển sang `<Icon>` thì bỏ hết mấy dòng đó, không thì lệch baseline.
**Không đụng**: `ns__kpi` (là bộ lọc), `lg-kpi-card`, `cc-kpi-card`, `cc-calendar-stat-card`, `cc-today-metric-item`, `cc-emp-cal-summary-card`, `cc-radar-metric-chip` — gom 7 họ là dự án riêng.

### 2.6 Thanh tìm

**Quy tắc**: `<form role="search">` + icon trong ô + `aria-label`, đặt trong `.md-page__toolbar` **ngoài card** ở cấp trang. **Debounce 300ms.**
**Màn mẫu**: `frontend/src/pages/BaoGiaPage.tsx:235-248` (CSS `bao-gia.css:1349`).

| Trước | Sau |
|---|---|
| 4 ô tìm **live-search từng phím, không debounce** — deps của load là `[token,q,status]` (`DepartmentPurchaseRequestsPage.tsx:166`), `[token,q,status,page]` (`PurchaseRequestsPage.tsx:716`), `[token,sourceQ,…]` (`:682`), `[token,q,status,selectedGroup,page]` (`SuppliersPage.tsx:366`) ⇒ **gõ 10 ký tự = 10 request** | debounce 300ms |
| Ô tìm trong drawer NCC dựng bằng **inline style** `display:flex;gap:10px;maxWidth:280px` (`SuppliersPage.tsx:1310-1323`) | dùng class chuẩn |
| Ô tìm cục bộ trong card "Yêu cầu từ phòng ban" (`PurchaseRequestsPage.tsx:1265-1285`) | **giữ nguyên vị trí trong card**. Kéo ra ngoài sẽ nằm cạnh toolbar bảng Phiếu mua ngay dưới → cùng màn 2 ô tìm dính nhau, tệ hơn |

Cảnh báo dev: khi thêm debounce phải **giữ nguyên `setPage(1)` đang chạy trong `onChange`** (`PurchaseRequestsPage.tsx:1428`, `SuppliersPage.tsx:640`). Bỏ sót thì lọc xong người dùng đứng ở trang 3 rỗng.

### 2.7 Footer bảng / phân trang

**Quy tắc**: `.md-page__pager` **ngoài card**; cụm nút bọc `.md-page__pager-btns` (`master-data.css:253`); chữ `Tổng số: {n} {đơn vị} · Trang x/y`; nút `ghost`; chỉ hiện khi có dòng. **Cỡ trang chuẩn = 20** cho mọi bảng danh sách chính.
**Màn mẫu**: `frontend/src/pages/SuppliersPage.tsx:881-900`.

| Trước | Sau |
|---|---|
| Kiểu A: `.purchase__source-foot` trong card, "Trang x/y" **kẹp giữa** hai nút (`PurchaseRequestsPage.tsx:1385-1410`) | giữ vị trí trong card, đổi chuỗi + thứ tự về chuẩn |
| Kiểu C: `DepartmentPurchaseRequestsPage.tsx:593-595` — chỉ có "Tổng {total} yêu cầu", **không hề có phân trang**, trong khi load ghim cứng `size: 100` (`:155`) ⇒ **quá 100 yêu cầu là bảng cắt im lặng**, số "Tổng" vẫn đúng, người dùng không có đường tới phần còn lại | thêm pager đầy đủ, `size` 100 → 20 |
| Cỡ trang: 10 / 20 / 12 / 100 cứng | 20 |

Cảnh báo dev (bẫy lớn): màn Yêu cầu mua hàng có liên thông `focusRequestCode` (`DepartmentPurchaseRequestsPage.tsx:239-243`) — kế toán bấm mã YCMH từ PMH/Phiếu chi sẽ đổ mã vào ô tìm. **Không reset page về 1 là nhảy vào trang rỗng, tính năng truy vết ngược chết im lặng.** Phải reset page khi đổi `q`/`status` và khi nhận `focusRequestCode`. Hạ 100 → 20 đổi thói quen người dùng (hiện thấy hết trong 1 màn) — báo trước.

### 2.8 Cột thao tác

**Quy tắc**: `<th className="md-page__actions-col">Thao tác</th>` (canh **phải**, kể cả `<th>` — xem chú thích `master-data.css:180-185`); nút = `RowActionButton dense` (icon + tooltip CSS + `aria-label` + trạng thái loading); hành động nguy hiểm dùng prop `danger`; `stopPropagation` nếu `<tr>` có `onClick`.
**Màn mẫu**: `frontend/src/pages/PurchaseRequestsPage.tsx:1546` + thân `actionButtons` tại `:1106-1224`. Component: `frontend/src/components/RowActionButton.tsx:25`.

| Trước | Sau |
|---|---|
| `<th></th>` **rỗng, không aria-label** (`LuongPage.tsx:763`, `NhanSuPage.tsx:946`) | `<th className="md-page__actions-col">Thao tác</th>` |
| `<th>Hành động</th>` (`LuongPage.tsx:1575, 3008, 3577`) | như trên |
| `<th style={{textAlign:"center"}}>Thao tác</th>` (`NghiPhepPage.tsx:1102, 1259`), `nqr__action-head` center (`NoiQuyPage.tsx:210`), `<th aria-label="Thao tác" />` rỗng (`CauHinhLuongTab.tsx:1444, 1836`; `ChamCongPage.tsx:7611`) | như trên |
| `<th>` trơn ⇒ tiêu đề canh trái còn nút canh phải (3/4 bảng Thu mua) | như trên |
| Ô **trộn** icon `RowActionButton` cạnh 2 nút chữ "Sửa"/"Huỷ" (`DepartmentPurchaseRequestsPage.tsx:558-586`) | toàn icon |
| Nút `<Button variant="ghost">Tạo phiếu</Button>` cỡ đầy đủ, thiếu `.md-page__rowbtn` nên padding 8×14 thay vì 2×10 (`PurchaseRequestsPage.tsx:1366-1377`) | `RowActionButton dense` |
| 2 nút chữ "Xem/Sửa" + "Ngừng"/"Mở" (`SuppliersPage.tsx:856-869`) | icon; **toggle phải đổi icon theo trạng thái** |
| Nút chữ `.lg-rowact` (`LuongPage.tsx:838-853`), nút inline-style (`NghiPhepPage.tsx:1134-1135`), `cc-btn-approve-sm`/`reject-sm`/`cancel-sm` (`NghiPhepPage.tsx:1308-1310`), `nqr__delete` (`NoiQuyPage.tsx:239-247`) | `RowActionButton`, giữ biến thể `danger` |

Cảnh báo dev:
- Nút "Ngừng"/"Mở" là **toggle đổi nhãn theo trạng thái** (`SuppliersPage.tsx:868`) — đổi thiếu icon là người dùng bấm nhầm ngừng hợp tác NCC.
- `actionButtons` dùng **chung** cho ô bảng (`dense=true`) và footer DetailModal (`dense=false`, `PurchaseRequestsPage.tsx:1564`) — sửa một tham số là đổi cả hai chỗ.
- Bảng lương **16 cột**, `.lg-rowact .btn` chỉ có `margin-left:4px` (`luong.css:287`) — đổi chữ sang icon làm cột co lại, phải kiểm lại độ giãn cả bảng.
- Ép hết về component chung mà **quên biến thể danger** là mất tín hiệu nguy hiểm ở "Xoá"/"Từ chối".

### 2.9 Định dạng ngày – tiền

**Quy tắc**: dùng `frontend/src/utils/format.ts` — `money` (:9) · `fmtDate` (:21) · `fmtDateISO` (:49) · `fmtDateTime` (:71) · `hanGiao` (:30) · `amountInWords` (:126). **Cấm đẻ helper mới trong file màn.**

| Trước | Sau |
|---|---|
| `ChamCongPage.tsx:127, 2697` — `fmtDateTime`, `fmtDateVN` cục bộ | import từ `utils/format` |
| `NghiPhepPage.tsx:29` — `fmtDate` cục bộ | như trên |
| `NhanSuPage.tsx:102` — tự viết `fmtDate` dù `:29` **đã import** `money` từ format | như trên |
| `LuongPage.tsx:552` — gọi thẳng `toLocaleDateString` dù `:44` **đã import** `fmtDateTime` | như trên |

**Ngoại lệ hợp lệ — đừng "sửa"**: `LuongPage.tsx:62` (`money` không hậu tố "đ", đã nêu ở `format.ts:5`).

---

## 3. VIỆC TỪNG MÀN

### 3.1 Thu mua

| Màn | Mã | Sửa gì | Công | Rủi ro |
|---|---|---|---|---|
| **Mua hàng** `PurchaseRequestsPage.tsx` | D04 | `Lưu hợp đồng` (:2437) ghost → accent, khớp `Ghi đợt giao` (:2601) trong cùng modal | NHỎ | Không |
| | D16 | Gỡ `.md-page__toolbar-spacer` treo vô nghĩa (:1450). **Không** thêm CTA cấp trang | NHỎ | Không |
| | D13 | Debounce 300ms cho 2 ô tìm (:1265, :1414), giữ `setPage(1)` | NHỎ | Quên `setPage` → trang rỗng |
| | D14 | Chuẩn hoá footer kiểu A (:1385) về chuỗi/thứ tự chuẩn; `PAGE_SIZE` 10 → 20 (:41), `SOURCE_PAGE_SIZE` giữ 20 (:42) | NHỎ | Không |
| | D15 | 2 ô rỗng (:1325, :1483) → `EmptyState` 3 nhánh | NHỎ | `colSpan` tính tay |
| | D17 | `<th>` (:1313, :1471) thêm `md-page__actions-col`; `Tạo phiếu` (:1366) → `RowActionButton dense` | NHỎ | `actionButtons` dùng chung dense/không dense (:1564) |
| **Yêu cầu mua hàng** `DepartmentPurchaseRequestsPage.tsx` | **D14** | **`size:100` cứng (:155) → 20 + thêm `.md-page__pager`; reset page khi đổi q/status và khi nhận `focusRequestCode`** | **VỪA** | **CAO — bẫy truy vết ngược (:239-243)** |
| | D10 | Eyebrow `Phòng ban` → `Thu mua` (:433); sub nói rõ vai cho 6 nhóm quyền | NHỎ | Không |
| | D04 | `+ Tạo yêu cầu mua` (:473) → accent; submit dialog (:877) giữ accent | NHỎ | Không |
| | D13 | Debounce, giữ reset page | NHỎ | Như trên |
| | D15 | Ô rỗng (:509) → `EmptyState` | NHỎ | Không |
| | D17 | `<th>` (:497) + ô thao tác trộn icon/chữ (:558-586) → toàn icon | NHỎ | Không |
| **Nhà cung cấp** `SuppliersPage.tsx` | D04 | `+ Thêm NCC` (:664) → accent | NHỎ | Không |
| | D13 | Ô tìm drawer inline-style (:1310) → class chuẩn; debounce ô chính (:640) | NHỎ | Không |
| | D14 | `PAGE_SIZE` 12 → 20 (:26) | NHỎ | Không |
| | D15 | Ô rỗng (:739, :1513) → `EmptyState`, **giữ `colSpan={canUpdate?5:4}`** | NHỎ | Lệch cột với người không quyền sửa |
| | D17 | 2 nút chữ (:856-869) → `RowActionButton dense`, toggle đổi icon theo trạng thái | NHỎ | Bấm nhầm ngừng NCC |
| | D12 | 3 thẻ emoji (:594-622, `purchase.css:829-903`) → dải pill + `<Icon>`; xoá CSS chết `.md-page__stat-card` | VỪA | Bỏ quên font-size riêng của icon → lệch baseline |

### 3.2 Nhân sự & Lương

| Màn | Mã | Sửa gì | Công | Rủi ro |
|---|---|---|---|---|
| **Hồ sơ nhân sự** `NhanSuPage.tsx` | **D21** | **CHỦ CHỐT: làm file `.xlsx` THẬT.** Hiện `exportExcel()` (:430-483) nối chuỗi CSV, blob `text/csv`, tên file `.csv`, và **chỉ lấy 200 người đầu** (:440) — cắt im lặng. Thay bằng: endpoint `GET /api/employees/export.xlsx` (openpyxl, đã là dep) + giao diện tải blob. Bỏ trần 200 | **VỪA** (có backend) | **CAO — RBAC**: endpoint PHẢI dùng lại `_scope_for(authz, user)` và ĐÚNG bộ lọc của màn (`employees.py:242`). Làm ẩu = người scope `own` tải được cả công ty. Bắt buộc chạy `./init.ps1` |
| | D04 | `ns-btn-primary` gradient cam tự chế → `Button accent`; **đổi `ns__kpi.is-active` từ cam sang charcoal** | VỪA | Rà lại tương phản chữ trắng + hover + shadow ở cả header và drawer |
| | D10 | Thêm eyebrow (:503) | NHỎ | Canh dòng `ns2__headact` (:510-531) |
| | D15 | **Tách `ns__loading` khỏi `ns__empty` trước**, rồi `EmptyState` (:707, 792, 979, 1762, 3318) | VỪA | Không tách → nhảy layout mỗi lần tải |
| | D17 | `<th></th>` rỗng (:946) → có nhãn. **Không** thêm cột thao tác vào bảng chính | NHỎ | Không |
| | fmt | `fmtDate` cục bộ (:102) → `utils/format` | NHỎ | Không |
| **Lương** `LuongPage.tsx` | **D06** | 3 ô `input type="month"` phơi native, hiện "August 2026" (:436-446, :2952-2961, :3707-3712) → ẩn input + tự vẽ nhãn `Tháng {m} / {y}`. **Mẫu có sẵn cùng phân hệ**: `ChamCongPage.tsx:1585-1600` + `cham-cong.css:1960-1968` | NHỎ | Click label chỉ focus — phải gọi `showPicker()` có fallback. Ô ":3707" nằm **trong form**: ẩn input là mất focus-ring + validation, phải tự vẽ lại |
| | D04 | `Tính lại` (:483) và `Khởi tạo bảng lương` (:731) → cùng accent | NHỎ | Nếu QA thấy hiện đồng thời: hạ `Tính lại` xuống ghost |
| | D21 | Ký tự `⬇` gõ trong text (:529-546) → `<Icon name="download">`; nhãn "Xuất Excel" **giữ nguyên** (backend sinh .xlsx thật) | NHỎ | Không |
| | D10 | Thêm eyebrow (:175) | NHỎ | Không |
| | D15 | `ns__empty` (:858, 1634, 2776) → `EmptyState` + luật 3 ca | NHỎ | Không |
| | D17 | `Hành động` → `Thao tác` (:1575, 3008, 3577); `<th></th>` (:763) → có nhãn; `.lg-rowact` nút chữ (:838) → `RowActionButton` | VỪA | Bảng 16 cột — kiểm lại độ giãn sau khi co cột |
| | fmt | `:552` `toLocaleDateString` → `fmtDateTime` | NHỎ | Không |
| **Chấm công** `ChamCongPage.tsx` | D06 | `cc-ts-input-month` (:6279) → pattern nhãn VN đã có sẵn **trong chính file này** | NHỎ | Không |
| | D21 | `Xuất CSV` (:6320) icon `FileEdit` (**biểu tượng bút sửa cho việc tải xuống**) → `<Icon name="download">`; nhãn giữ nguyên (đúng sự thật) | NHỎ | Không |
| | D04 | `Chốt kỳ` (:6335) → accent | NHỎ | Không |
| | D10 | Thêm eyebrow (:263) | NHỎ | Không |
| | D15 | Tách loading (:1623, 2654, 4258, 6364, 7052) khỏi empty (:1631, 2942, 4567, 6407, 7308) | VỪA | Nhảy layout nếu tách sót |
| | D17 | Thống nhất `<th>` (:1829, :7611); `cc-btn-*-sm` → `RowActionButton`, giữ danger | VỪA | Mất tín hiệu nguy hiểm nếu quên danger |
| | fmt | `:127, :2697` → `utils/format` | NHỎ | Không |
| | **D25** | Radar HUD quân sự (:377-697): nền `#0b1329` hardcode **trong JSX** (:463), neon `#4ade80`/`#f87171` ngoài token, 3 animation lặp vô hạn không tắt được, chữ HOA kiểu phim điệp viên. **Vỏ card trắng ruột đen — lệch ngay trong chính thẻ đó** | VỪA→LỚN | **CAO** — xem 8.3 |
| **Nghỉ phép** `NghiPhepPage.tsx` | D04 | `cc-btn-cta-compact` navy `!important` (:414, 426, 1014) → `Button accent` | VỪA | Gỡ class là mất hình dạng — thay đủ 6 thuộc tính `!important` |
| | D10 | Thêm eyebrow (:98) | NHỎ | Không |
| | D15 | `ns__empty` + inline-style padding (:761, 766, 768, 1028, 1317) → `EmptyState` | NHỎ | Không |
| | D17 | `<th style={{textAlign:"center"}}>` (:1102, 1259) → `md-page__actions-col`; nút inline-style (:1134) và `cc-btn-*-sm` (:1308) → `RowActionButton` giữ danger | VỪA | Như trên |
| | fmt | `fmtDate` (:29) → `utils/format` | NHỎ | Không |
| **Tăng ca** `TangCaPage.tsx` | D10 | Thêm eyebrow (:466) | NHỎ | Không |
| **Nội quy công ty** `NoiQuyPage.tsx` | D10 | `ns__eyebrow` (class không có CSS) → `.eyebrow`; nội dung theo quyết định 7.1 | NHỎ | Cần chốt IA trước |
| | D04 | `variant="primary"` (:181) → accent | NHỎ | Không |
| | D15 | `nqr__state` (:215, 219) → `EmptyState`; chữ ở `:220` đã đúng luật 3 ca, giữ | NHỎ | Không |
| | D17 | `nqr__action-head` center (:210) → canh phải; `nqr__delete` (:239) → `RowActionButton danger` | NHỎ | Không |
| **Cấu hình lương** `CauHinhLuongTab.tsx` | D17 | `<th aria-label="Thao tác" />` rỗng (:1444, :1836) → có chữ; nút trong `.cl-table td.act` → `RowActionButton` | NHỎ | `.cl-table td.act .btn` chỉ có `margin-left:4px` (`luong.css:960`) — cột co lại |
| **Phòng ban** `DepartmentsPage.tsx` | — | **KHÔNG SỬA — là màn mẫu** cho eyebrow (:1474) và dải pill (:1482-1512) | — | — |

---

## 4. THỨ TỰ LÀM

Nguyên tắc xếp: **thứ ăn thời gian và làm mất dữ liệu của người dùng trước, thứ đẹp mắt sau.** Không đợt nào phụ thuộc đợt sau.

### Đợt 1 — mất dữ liệu & ăn ngày công (ưu tiên cao nhất)

| # | Việc | Màn | Vì sao đứng đây |
|---|---|---|---|
| 1 | Phân trang màn Yêu cầu mua hàng (`size:100` → 20 + pager) | Yêu cầu mua hàng | Đây là **mất đường tới dữ liệu**, không phải chuyện đẹp xấu. Quá 100 yêu cầu là bảng cắt im lặng mà số "Tổng" vẫn đúng — người dùng không biết mình đang thiếu gì |
| 2 | Tách nhánh **lỗi API** ra khỏi empty state (áp `EmptyState` ca thứ 3) | cả 2 phân hệ | API chết mà bảng in "Chưa có…" là **báo sai sự thật**. Đúng sự cố 05/08/2026 |
| 3 | Tách `ns__loading` khỏi `ns__empty` | Hồ sơ NS · Chấm công | Điều kiện tiên quyết của mọi việc empty state ở đợt 2. Làm sau là phải sửa lại |
| 4 | Month picker tiếng Việt (D06) | Lương ×3, Chấm công ×1 | Kế toán đọc kỳ lương **mỗi ngày**. "August 2026" là đọc nhầm tháng, không phải xấu |
| 5 | Debounce 300ms 4 ô tìm | 3 màn Thu mua | Gõ 10 phím = 10 request. Ô tìm giật là ăn thời gian trực tiếp |
| 6 | **Endpoint xuất `.xlsx` thật** + bỏ trần 200 (chủ chốt 7.2) | Hồ sơ nhân sự | Nhãn đang nói dối, VÀ cắt im lặng ở người thứ 201. Đây là việc DUY NHẤT của đợt 1 có backend ⇒ tách ticket riêng, nghiệm thu bằng `./init.ps1` |
| 7 | `<th>` rỗng không aria-label | Lương (:763), Hồ sơ NS (:946) | Lỗi tiếp cận, không phải thẩm mỹ |

Ra khỏi đợt 1 là hết mọi chỗ hệ thống **nói sai** hoặc **giấu** dữ liệu.

### Đợt 2 — đồng bộ nhìn thấy được

Thứ tự trong đợt: **(a) dựng `components/EmptyState.tsx` → (b) D04 nút chính + `ns__kpi` charcoal → (c) D10 eyebrow → (d) D17 cột thao tác → (e) D14 chuẩn hoá pager + PAGE_SIZE=20 → (f) D15 áp EmptyState hàng loạt → (g) dọn helper format.**

Vì sao thứ tự này: EmptyState phải có trước mới áp được (f); D04 phải xong trước D17 vì `RowActionButton` dựng trên `<Button>` nên kéo theo hệ variant — làm ngược là sửa hai lần.

### Đợt 3 — nặng, rủi ro, hoặc thuần thẩm mỹ

| # | Việc | Điều kiện |
|---|---|---|
| 1 | Tách `.eyebrow` khỏi nhãn section thân trang → `.md-page__section-label` | không |
| 2 | Thẻ KPI Nhà cung cấp → dải pill + Icon, xoá CSS chết `.md-page__stat-card` | không |
| 3 | Radar Chấm công (D25) | **Phải dọn 3 khối CSS trùng trước** + chủ chốt hướng (7.3) |

### Đợt R (chạy nhánh riêng, song song) — D02 URL riêng

Không nhét vào đợt 1-3 vì nó đụng `AppShell.tsx` dùng chung cho **cả app**, không tách theo phân hệ được. Chi tiết mục 6.

---

## 5. D01 — "phải click 2 lần mới đổi màn"

### 5.1 Tình trạng xác minh: **CHƯA TÁI HIỆN ĐƯỢC — chưa giao dev**

| Đã làm | Kết quả |
|---|---|
| Truy cơ chế bằng code | **Có giả thuyết chắc**: sidebar là cột flex thường, rộng 244px, **không** `position`, **không** `z-index` (`components/sidebar.css:4-19`). Mọi drawer/modal là `position:fixed; inset:0` và tự đóng khi bấm nền. Không tổ tiên nào tạo containing block mới (`global.css:36-56` chỉ có flex + overflow) ⇒ tấm nền phủ **trọn viewport, kể cả sidebar**. Đang mở drawer mà bấm menu: cú 1 rơi vào nền → đóng drawer; cú 2 mới chạm nút |
| Loại giả thuyết "chặn khi form dirty" | **Loại**. `AppShell.tsx:681` `onSelect={(id)=>navigate(id)}` không có guard. Guard dirty đều nội bộ trong màn: `ChamCongPage.tsx:3909-3922` chỉ bọc nút đổi tháng; `CauHinhLuongTab.tsx:419-429` chỉ bọc đổi bộ phận/tab con. Hai `beforeunload` chỉ bắn khi F5/đóng tab |
| Loại giả thuyết "focus/blur nuốt click" | **Loại**. 10 popover đóng bằng `document mousedown` đều không phủ toàn màn; `XepLichPage.tsx:2180-2189` nghe `click` ở pha bubbling nên handler của nút chạy trước |
| Dựng unit test | **Không dựng được**. "Cú bấm rơi vào nền" là hit-test theo layout — jsdom không mô phỏng |

Ghi chú nặng thêm: `ConfirmDialog.tsx:81` và `DetailModal.tsx:43` đóng ở `onMouseDown` — nền biến mất giữa mousedown và mouseup nên trình duyệt **không phát sinh sự kiện click nào cả**, mất trọn cú bấm đầu, không có cách nào bắt được ở tầng React.

### 5.2 Yêu cầu với QA — làm TRƯỚC khi giao dev

Playwright đã nằm sẵn trong `frontend/package.json` devDependencies. Kịch bản tối thiểu:

1. Mở một màn danh mục bất kỳ → bấm **Sửa** để hiện drawer → bấm một mục sidebar → **đếm số lần bấm** cho tới khi đổi màn.
2. Lặp với: `DetailModal` ở màn Mua hàng, drawer NCC (`SuppliersPage.tsx:907`), drawer Chấm công (`cham-cong.css:4265`).
3. Lặp **khi không mở drawer nào** — nếu vẫn 2 lần thì giả thuyết trên **sai**, phải điều tra lại từ đầu.

Ghi vào phiếu QA: màn nào, đang mở gì, bao nhiêu lần bấm, có video.

### 5.3 Nếu QA xác nhận — hướng sửa (chưa phải lệnh)

**Cấm** nâng `z-index` sidebar lên trên nền: phá ngữ nghĩa modal (đang sửa dở vẫn đổi màn được, mất nháp, drawer treo lơ lửng phía sau).
Hướng đúng: khi có drawer/modal mở thì bấm sidebar phải **đóng drawer VÀ chuyển màn trong cùng một cú** — nâng trạng thái "đang mở drawer" lên `AppShell` hoặc đăng ký guard chung. Đụng **20 màn có overlay**, trong đó `RebuildCatalogPage.tsx:358, 1247` là drawer **dùng chung cho 10 màn danh mục** — sửa sai là hỏng cả 10. Và phải nối vào `DiscardChangesDialog` cho các màn có nháp (Chấm công, Cấu hình lương, form YCMH), không thì rời màn = mất dữ liệu.

Việc này **vượt phạm vi 2 phân hệ** (20 màn). Nếu QA xác nhận, mở PRD riêng.

---

## 6. D02 — không có URL riêng cho từng màn

### 6.1 Hiện trạng

Không có router. `frontend/package.json:12-17` chỉ có `lucide-react`, `react`, `react-dom`, `recharts`. Điều hướng là **state thuần**: `useState("dashboard")` tại `AppShell.tsx:94`, `navigate` tại `:128-131` chỉ `setState`. Grep toàn `src`: **không một chỗ nào** dùng `window.history` / `location` / `pushState` / `popstate` / `hashchange`.

Hệ quả: URL đứng yên `/`; **F5 rơi về Dashboard**; Back **thoát hẳn khỏi app**; không bookmark được màn nào; không gửi link cho đồng nghiệp được.

Quy mô: ~40 màn (switch `AppShell.tsx:557-673` = 25 case + default; 10 màn danh mục qua `REBUILD_CONFIGS`; 4 nhánh đặc biệt). **18 chỗ gọi điều hướng, 15 nằm ngoài AppShell.**

**Hai tin tốt (giảm công đáng kể)**:
- Hạ tầng đã sẵn: `frontend/nginx.conf:51-53` có `try_files $uri $uri/ /index.html`; Vite dev fallback sẵn. **Không phải sửa hạ tầng.**
- Cổng phân quyền cho deep-link **đã có**: `AppShell.tsx:479-492` tính `baseId` + `allowed`, `:471-477` chặn khi `readable` chưa tải, `:509-524` render 403. Vào thẳng URL cấm vẫn ra 403 đúng — **không cần viết mới**.

Dọn trước: ba trường `NavParams` **đã chết** (khai ở `AppShell.tsx:58-88`, không nơi nào đọc): `customer` (:61), `estimateId` (:66), `openEstimateId` (:68). Xoá trước cho đỡ phải nghĩ cách đưa object `PinnedCustomer` vào URL.

### 6.2 Hai phương án

| | **Nhẹ** — đồng bộ state ↔ hash | **Đầy đủ** — `react-router-dom` |
|---|---|---|
| Sửa gì | ~1 file. Giữ nguyên chữ ký `navigate(id, params)` ⇒ **15 call site không phải đổi**. Chỉ thêm vào `AppShell`: đọc hash lúc mount thay `useState("dashboard")`, `history.pushState` trong `navigate` (:128), listener `popstate` | Thêm dependency; chuyển switch `:557-673` thành ~40 route; 15 call site → `useNavigate`; `Sidebar.tsx:359-378, 384-392` đổi `button` → `NavLink` |
| Map URL | Đã có quy ước `id:tham-so` tách bằng dấu hai chấm (`AppShell.tsx:479, 536`) → map thẳng `#/kho-item/12` | `/kho-item/12` |
| Được gì | Back / Forward / F5 / bookmark chạy ngay. Không thêm thư viện. Hash không cần cấu hình server | Chuẩn, mở rộng được. Thêm ctrl+click / mở tab mới. **Sửa luôn D01 nhánh menu cha** |
| Mất gì | URL có dấu `#`, không SEO (ERP nội bộ — không quan trọng). Chỉ chở được tham số vô hướng. Chưa có URL cho tab-trong-màn / drawer / bộ lọc | Đắt hơn nhiều, đổi 40 nơi cùng lúc, khối lượng QA lớn |

### 6.3 Cái gì sẽ vỡ — **cả hai phương án đều dính**

| # | Vỡ gì | Vì sao | Bắt buộc làm |
|---|---|---|---|
| 1 | **Bấm mã YCMH lần 2 không thấy gì** | `AppShell.tsx:126-127` ghi rõ mỗi lượt `navigate` tạo object `params` **MỚI** để effect bên màn đích chạy lại kể cả khi đang ở đúng màn đó. `DepartmentPurchaseRequestsPage.tsx:245-257` phụ thuộc **đúng vào identity** của `seedLines`. URL thì hai lần bấm cùng mã cho ra chuỗi giống hệt → effect không chạy lại | Kèm **nonce** trong URL, hoặc ref đếm lượt |
| 2 | `purchaseSeedLines` không lên URL được | Là **mảng object** (`AppShell.tsx:80`, sinh ở `KhoTonKhoPage.tsx:280-286`). Ép nhét ra URL dài ngoằng và lộ dữ liệu | Giữ trong state, chấp nhận link đó không bookmark được |
| 3 | **Back = mất nháp im lặng** | Guard hiện chỉ là `beforeunload` (`ChamCongPage.tsx:3811-3819`, `CauHinhLuongTab.tsx:408-416`) — **không bắn khi đổi route trong SPA**. Có URL rồi thì Back đi qua màn dirty mà không hỏi | Nối `DiscardChangesDialog` vào Chấm công + Cấu hình lương **cùng lúc**, không để sau |
| 4 | Badge đứng im / menu con không tự bung khi vào deep-link | `key={baseId}` (`AppShell.tsx:527, 551, 555`) điều khiển remount `RebuildCatalogPage`; effect nạp badge bám `activeId` (`:268-271`); effect tự bung menu cha bám `activeId` (`Sidebar.tsx:281-287`) | Giữ nguyên cả ba chỗ khi đổi nguồn sự thật |

### 6.4 Khuyến nghị

**Làm phương án NHẸ, một lần cho cả app, trên nhánh riêng, sau khi Đợt 1 xong.**

Lý do: F5 mất màn là thứ ăn thời gian hằng ngày thật (kế toán mở lương, lỡ F5, quay về Dashboard), nên không đáng hoãn vô hạn. Nhưng nó đụng `AppShell` dùng chung — **không** nhét chung nhánh với đợt 1-2 được, vì một lỗi ở đây làm cả 40 màn không mở được, che mất kết quả của các việc nhỏ.

**Không** chọn phương án đầy đủ lúc này: khối lượng 40 route + 15 call site + QA không tương xứng với thứ nhận lại, trong khi phương án nhẹ giải quyết đúng cái báo cáo đòi (URL **cấp màn**). Khi nào cần ctrl+click / mở tab mới thì nâng cấp sau — phương án nhẹ không cản đường.

**Điều kiện bắt buộc để nghiệm thu**: 4 mục ở 6.3 phải có bằng chứng đã xử lý, đặc biệt (1) nonce và (3) `DiscardChangesDialog`.

---

## 7. Ba quyết định — ĐÃ CHỐT 08/08/2026

### 7.1 Mục "Nội quy công ty" nằm ở nhóm nào? — ✅ CHỐT: phương án A

Sidebar đang xếp nó ở section **"Tổng quan"** (`Sidebar.tsx:49-55`) trong khi nội dung là tài liệu hành chính nhân sự, và header tự ghi "HÀNH CHÍNH NHÂN SỰ".

| Phương án | Việc kèm theo |
|---|---|
| **A ✅ ĐÃ CHỌN** — chuyển mục sang section "Nhân sự & Lương" | Đổi 1 chỗ trong `Sidebar.tsx`, eyebrow = `Nhân sự & Lương`, khớp luôn nội dung màn |
| B — giữ ở "Tổng quan" | **KHÔNG CHỌN** |

Đây là quyết định kiến trúc thông tin, không phải việc UI — nên hỏi, không tự làm.
Chủ chốt 08/08/2026: **chuyển xuống Nhân sự**.

### 7.2 "Xuất Excel" ở Hồ sơ nhân sự: đổi nhãn hay làm file thật? — ✅ CHỐT: phương án B (làm thật)

| Phương án | Công | Đụng gì |
|---|---|---|
| A — đổi nhãn thành "Xuất CSV" | NHỎ | ~~Không~~ — **KHÔNG CHỌN** |
| **B — sinh `.xlsx` thật ✅ ĐÃ CHỌN** | VỪA | Thêm `GET /api/employees/export.xlsx` (router + service, openpyxl đã là dep, cùng khuôn với file xuất bảng lương). Bắt buộc chạy lại `./init.ps1` |

**Ràng buộc bắt buộc của phương án B — dán vào ticket:**

1. **Quyền phải khớp màn.** Dùng lại `_scope_for(authz, user)` và **đúng bộ lọc** đang truyền ở
   `routers/employees.py:242` (`q`, `department_id`, `status`, `sort`). Người có phạm vi `own`
   tải file ra chỉ được thấy đúng phần họ xem được trên màn. Đây là rủi ro lớn nhất của cả đợt 1.
2. **Bỏ trần 200.** Trần `size` ở endpoint danh sách là `le=200`; endpoint xuất **không** đi qua
   đường phân trang đó. Không được "tăng số cho to" — phải lấy trọn theo phạm vi.
3. **Giữ nguyên 8 cột đang có** (Mã · Họ tên · Phòng/Tổ · Chức danh · Bậc tay nghề · Trạng thái ·
   Ngày vào · Tài khoản). Đổi cột là việc khác, không nhét vào đây.
4. **Test bắt buộc**: tải được file mở lên đúng số dòng; người có phạm vi hẹp không tải được người
   ngoài phạm vi; bộ lọc trên màn phản ánh đúng vào file.

Bỏ giới hạn `size:200` (`NhanSuPage.tsx:440`) **không** làm bằng cách tăng số bừa — request sẽ nặng lên; phải phân trang/stream phía server. Đợt 1 chỉ **hiện cảnh báo** khi bị cắt.

### 7.3 Radar GPS ở Chấm công (D25): tô lại hay thay? — ✅ CHỐT: phương án A (tô lại)

| Phương án | Công | Rủi ro |
|---|---|---|
| **A ✅ ĐÃ CHỌN** — giữ chức năng, tô lại theo token | VỪA–LỚN | Phải dọn **3 khối CSS trùng** (`cham-cong.css:313-420`, `988-1150`, `5281-5336`) trước, không thì sửa vào chỗ đã bị đè, không thấy đổi gì. Màu nền nằm trong **JSX** (`ChamCongPage.tsx:463` `fill="#0b1329"`) nên sửa CSS không đủ. Thêm `@media (prefers-reduced-motion)` cho 3 animation lặp vô hạn. Bỏ chữ HOA kiểu HUD |
| B — gỡ radar | NHỎ | **KHÔNG CHỌN.** Gỡ là mất tín hiệu trong/ngoài vùng chấm công |

Dù chọn gì, **không xoá trơn**. Xếp đợt 3.

---

## 8. Cách nghiệm thu

Checklist bấm được. Mỗi dòng phải tự kiểm được trong ≤30 giây, không cần đọc code. Chưa tick đủ thì chưa xong đợt.

### Đợt 1

| # | Bấm gì | Phải thấy |
|---|---|---|
| 1 | Vào **Yêu cầu mua hàng** khi có >20 yêu cầu | Có chân trang "Tổng số: N yêu cầu · Trang 1/x" + nút Trước/Sau bấm được. Cộng số dòng qua các trang = số ở "Tổng" |
| 2 | Gõ từ khoá vào ô tìm khi đang ở **trang 3** | Nhảy về trang 1, có kết quả — không phải trang rỗng |
| 3 | Từ Phiếu chi bấm mã YCMH → quay lại → bấm **lại lần 2** cùng mã | Cả hai lần đều nhảy đúng vào yêu cầu đó |
| 4 | Tắt mạng (DevTools offline) rồi mở lần lượt 3 màn Thu mua + Hồ sơ NS + Lương | Bảng ghi **"Chưa đọc được số liệu — xem thông báo lỗi ở trên"**. **Không màn nào** ghi "Chưa có…" |
| 5 | Mở Hồ sơ nhân sự / Chấm công, nhìn lúc đang tải | Vùng bảng **không nhảy cao rồi co lại** |
| 6 | Mở Lương, nhìn ô chọn tháng (3 chỗ: toolbar, tab Tạm ứng, form Đề nghị tạm ứng) + Chấm công Bảng công tháng | Chữ **"Tháng 8 / 2026"** tiếng Việt. Bấm vào bung được lịch. Tab bàn phím tới thấy rõ đang focus ở đâu |
| 7 | Mở DevTools > Network, gõ 10 ký tự vào mỗi ô tìm (4 ô) | **Tối đa 2 request**, không phải 10 |
| 8 | Hồ sơ nhân sự → nút xuất | Nhãn ghi **"Xuất CSV"**, file tải về đuôi `.csv` — nhãn và file khớp nhau |
| 9 | Hồ sơ nhân sự khi có >200 nhân viên → bấm xuất | Có cảnh báo nói rõ chỉ xuất 200 dòng đầu |
| 10 | Dùng screen reader (hoặc DevTools > Accessibility) đọc header bảng lương + bảng Yêu cầu cập nhật | Cột cuối đọc ra **"Thao tác"**, không im lặng |

### Đợt 2

| # | Bấm gì | Phải thấy |
|---|---|---|
| 11 | Mở lần lượt 11 màn trong phạm vi | Mỗi màn có **đúng 3 tầng** header: nhãn nhỏ HOA → tiêu đề lớn → một câu mô tả |
| 12 | So nhãn nhỏ HOA với tên nhóm trong sidebar | **Khớp từng chữ**. Yêu cầu mua hàng ghi "Thu mua" (không phải "Phòng ban"). 5 màn NS&L ghi "Nhân sự & Lương" |
| 13 | Đếm nút **cam** trên mỗi màn và trong mỗi hộp thoại | Tối đa **1**. Không còn nút navy nào trong 2 phân hệ |
| 14 | Mở màn Hồ sơ nhân sự, nhìn dải pill lọc đang chọn | Nền **đen than**, không phải cam — phân biệt được với nút hành động |
| 15 | Mở DetailModal của PMH, so nút "Lưu hợp đồng" và "Ghi đợt giao" | **Cùng màu cam**, cùng cỡ |
| 16 | Lọc cho ra rỗng (gõ từ khoá vô nghĩa) ở từng bảng | Ô rỗng có icon + tiêu đề **"Không tìm thấy … phù hợp"** + nút **Xoá lọc** bấm được |
| 17 | Xoá hết lọc, xem bảng thật sự chưa có dữ liệu | Ô rỗng ghi **"Chưa có …"** + hướng dẫn cách tạo |
| 18 | Đăng nhập bằng tài khoản **không có quyền sửa** NCC, lọc cho rỗng | Ô rỗng vẫn **trải đúng hết chiều ngang bảng**, không lệch cột |
| 19 | Nhìn tiêu đề cột cuối của mọi bảng | Chữ **"Thao tác"**, canh **phải**, thẳng hàng với nút bên dưới |
| 20 | Rê chuột lên mọi nút trong cột thao tác | Ra tooltip. Nút "Ngừng/Mở" NCC **đổi icon** theo trạng thái dòng |
| 21 | Bấm nút trong cột thao tác ở bảng có click-cả-dòng | Chỉ chạy hành động, **không** mở drawer kèm |
| 22 | Bấm nút xoá / từ chối | Vẫn **đỏ**, vẫn có hộp xác nhận |
| 23 | So chân trang 4 bảng danh sách chính | Cùng chuỗi "Tổng số: N … · Trang x/y", cùng dáng nút, **có khoảng cách giữa 3 phần tử** (không dính nhau) |
| 24 | Đếm số dòng mỗi trang | **20** ở mọi bảng danh sách chính |
| 25 | Grep `fmtDate\|fmtDateTime\|vnd\s*=` trong 8 file NS&L + 3 file Thu mua | **0 định nghĩa cục bộ** (trừ ngoại lệ `LuongPage.tsx:62` đã ghi chú) |
| 26 | Chạy `./init.ps1` | PASS |

### Đợt 3

| # | Bấm gì | Phải thấy |
|---|---|---|
| 27 | Mở Nhà cung cấp | Dải pill r99 cao ~38px, icon vẽ (**không emoji**), **không** thẻ cao đẩy bảng xuống. So cạnh màn Phòng ban thấy cùng dáng |
| 28 | Grep `md-page__stat-card` trong `*.css` và `*.tsx` | 0 kết quả (đã xoá CSS chết) |
| 29 | Mở Chấm công > Chấm công của tôi | Radar cùng tông với thẻ trắng bao quanh nó; không còn nền đen `#0b1329`; vẫn đọc được **trong/ngoài vùng chấm công** |
| 30 | Bật "Giảm chuyển động" trong hệ điều hành, mở lại | Tia quét và sóng lan **dừng** |
| 31 | Grep `\.eyebrow` trong `*.tsx` | Chỉ còn ở header trang; nhãn section thân trang dùng class riêng |

### Đợt R (D02)

| # | Bấm gì | Phải thấy |
|---|---|---|
| 32 | Vào Lương → **F5** | Vẫn ở Lương, không rơi về Dashboard |
| 33 | Đi Lương → Chấm công → Nghỉ phép, bấm **Back** 2 lần | Về đúng Lương, không thoát app |
| 34 | Copy URL màn Yêu cầu mua hàng, dán sang tab mới | Mở đúng màn đó |
| 35 | Dán URL một màn **không có quyền** | Ra trang 403, không phải màn trắng |
| 36 | Từ Phiếu chi bấm mã YCMH **2 lần liên tiếp** cùng mã | Cả 2 lần đều nhảy đúng (kiểm nonce) |
| 37 | Sửa dở ở Cấu hình lương → bấm **Back** | **Hỏi trước khi bỏ nháp**, không mất im lặng |
| 38 | Vào thẳng URL một màn danh mục | Menu cha **tự bung**, badge nạp đúng |

---

## 9. Ràng buộc kỹ thuật — dán vào ticket

1. **Cấm** sửa `.btn--primary` / `.btn--accent` trong `frontend/src/styles/global.css`. 5+ màn ngoài phạm vi đang override/dựa vào (`auth.css:295`, `bao-gia.css:1015`, `khach-hang.css:1225`, `luong.css:582`, `xep-lich.css:1269`).
2. `global.css` bundle **SAU** mọi page CSS (`UI_DESIGN.md` §10) ⇒ page CSS **không** override được `.card`/`.btn`. Muốn đổi thì đổi variant ở chỗ dùng, không đè CSS.
3. `cham-cong.css` có nhiều khối định nghĩa **trùng cùng tên class**, khối sau đè khối trước. Trước khi sửa bất kỳ class nào trong file này: grep hết các khối, xác định khối nào đang có hiệu lực.
4. `cc-calendar-stat-card` định nghĩa trong `nghi-phep.css` nhưng `ChamCongPage` cũng import — sửa file này là đụng màn kia.
5. Không đụng backend trong PRD này. Nếu buộc phải (chỉ có phương án 8.2-B), phải cập nhật `docs/DB_SCHEMA.md` + `backend/app/db_migrations.py` và chạy `./init.ps1`.
6. Verify **duy nhất** bằng `./init.ps1`. Sửa route/schema backend thì restart uvicorn.
