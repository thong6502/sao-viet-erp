# Thiết kế UI — Module KCS kiêm nhiệm (Task 9-10)

Thay cho pha `ui-ux-pro-max` (không có trong môi trường, người dùng đã chấp thuận controller tự
làm — xem `progress.md` mục "Task 9-10 — pha thiết kế UI"). Tài liệu này chốt layout TRƯỚC khi
build, đúng tinh thần §6.5 của `docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem.md` (soi UI hiện
có → chốt layout → giao đủ cho agent build → kiểm browser thật desktop + 375px).

Grounded qua research trực tiếp code (không suy đoán): `docs/design-thuc-hien-san-xuat-ui.md`
(đã duyệt styleseed 95/A cho module song song "Thực hiện SX"), `ThucHienSxPage.tsx`/`ThsxG5.tsx`/
`ThsxDrawer.tsx` (triển khai thật), `danh-muc/CatalogListPage.tsx`+`CatalogDrawer.tsx`+
`components/Drawer.tsx` (pattern list+drawer), `KhoBaoCaoPage.tsx` (KPI+chart+Excel), `charts.tsx`
(helper biểu đồ dùng chung), `AppShell.tsx` (nav/badge — ĐÃ CODE XONG từ Task 4), và
`styles/responsive.css` (lớp thích ứng màn hẹp TOÀN HỆ THỐNG, vừa merge — commit `0dde174`).

## 0. Quyết định nền tảng: theo họ `.rc`/`.md-page`, KHÔNG theo họ `.thsx`

`ThucHienSxPage` (`.thsx-*`) tự viết 2 breakpoint riêng (1180px/820px) vì nó ra đời TRƯỚC lớp
`responsive.css` toàn hệ thống. `responsive.css` (190 dòng, nạp SAU CÙNG ở `main.tsx`) sửa mobile
cho TOÀN BỘ hệ thống bằng cách bắt đúng TÊN CLASS đã có sẵn ở nhiều màn — `.rc`/`.md-page` (khung
trang), `.rc__toolbar`/`.rc__headrow`/`.rc__filterbar`/`.md-page__toolbar` (thanh công cụ),
`.rc__tabs`/`.rc__segs` (dải tab/chip), `.rc__tablewrap`/`.md-page__tablewrap` (khung bảng cuộn
ngang), `.md-page__dialog`/`.md-page__overlay` (hộp thoại/form 2 cột→1 cột) — KHÔNG bắt bất kỳ
class `.thsx-*` nào.

**Ruling 1**: `ThucHienKcsPage`/`KcsDashboard` xây trên khung `.md-page` + vay mượn nguyên xi các
class công cụ họ `.rc__*` ở trên (giống cách `KhoBaoCaoPage.tsx` đã làm — nó dùng `.rc__toolbar`
lồng trong khung `.md-page` riêng). Chỉ đặt class mới (`.kcs-*`) cho phần KHÔNG có tiền lệ (KPI
strip, hàng checklist, khối ảnh lỗi, card "Chờ KCS"). Nhờ vậy 90% việc thích ứng 375px là MIỄN
PHÍ qua `responsive.css`, không phải tự viết `@media` mới — chỉ viết `@media` riêng trong `kcs.css`
cho phần thật sự đặc thù (KPI strip, card list). Rủi ro nếu sai: phải viết lại toàn bộ breakpoint
bằng tay như `.thsx-*` đã làm — tốn công hơn, không đồng bộ khi `responsive.css` sửa sau này.

`KcsResultDrawer` dùng shell có sẵn `frontend/src/components/Drawer.tsx` (Esc-to-close, focus-trap,
`role="dialog" aria-modal`, khoá cuộn nền, class `.rc-drawer`) — KHÔNG viết cơ chế drawer mới,
KHÔNG copy cơ chế `.thsx-panel`.

## 1. `ThucHienKcsPage.tsx` — khung trang

```
<div className="md-page kcs-page">
  <header className="md-page__toolbar rc__headrow">
    <h1>KCS · {tên tổ}</h1>
    <div className="rc__unified-right">
      <button className="btn btn--ghost" onClick={openKiemDotXuat}>Kiểm đột xuất</button>
      <button className="btn btn--accent" onClick={xuatExcel} disabled={exporting}>Xuất Excel</button>
    </div>
  </header>

  <KcsDashboard filters={filters} onFiltersChange={setFilters} />   {/* KPI + biểu đồ + filter bar dùng chung — xem mục 2 */}

  <section className="kcs-section">
    <h2>Chờ KCS <span className="rc__count">{cho.length}</span></h2>
    {loadingCho ? <LoadingState/> : errorCho ? <ErrorState onRetry=.../> : cho.length === 0 ? <EmptyState text="Không có việc nào đang chờ KCS"/> : (
      <div className="rc__tablewrap"><table className="rc__table kcs-table--cho">…</table></div>
    )}
  </section>

  <section className="kcs-section">
    <h2>Kết quả đã ghi</h2>
    {/* cùng 3-trạng-thái loading/error/empty riêng biệt, KHÔNG dùng chung 1 khối */}
    <div className="rc__tablewrap"><table className="rc__table kcs-table--ketqua">…</table></div>
  </section>

  {drawerState && <KcsResultDrawer .../>}
</div>
```

**Khối "Chờ KCS"** (bảng, cột theo đúng §6.2): Mã đơn/LSX · Sản phẩm/Nhóm · Công đoạn · Đã bàn
giao · Đã kiểm · Còn chờ · [Ghi kết quả]. Click dòng HOẶC nút → mở `KcsResultDrawer` ở chế độ ghi
mới (`mode="ghi"`, kèm `cong_viec_id`).

**Khối "Kết quả đã ghi"** (lịch sử, bảng): Thời điểm · Đạt/Lỗi · Loại (Routing/Đột xuất — pill,
tái dùng style `.thsx-x-pill` đã có màu theo loại) · Trạng thái gửi kho · Người ghi. Click dòng →
mở `KcsResultDrawer` ở chế độ xem (`mode="xem"`, read-only, hiện checklist/ảnh/audit).

**3 trạng thái loading/error/empty TÁCH RIÊNG cho từng khối** (Task 9 mục 9) — không dùng 1 khối
chung "không có dữ liệu" cho cả lỗi API lẫn rỗng thật. Mẫu 3-ca đã có tiền lệ ở `.rc__empty-state`
(`CatalogListPage`, phân biệt "chưa có gì / lọc không ra / tải hỏng") — tái dùng đúng 3 thông điệp
khác nhau cho KCS: "Không có việc nào đang chờ KCS" (rỗng thật, không phải lỗi) / "Không có kết
quả khớp bộ lọc" (rỗng do filter) / "Không tải được — thử lại" kèm nút Thử lại (lỗi API).

## 2. `KcsDashboard.tsx` — KPI + biểu đồ + filter bar (Task 9 dựng khung, Task 10 nối đủ dữ liệu)

Cấu trúc (mirror `KhoBaoCaoPage.tsx` KPI strip + filter, nhưng số liệu từ
`GET /api/san-xuat/kcs/bao-cao`, schema `KcsBaoCaoOut` — Task 8 đã xong):

```
<section className="kcs-dash">
  <div className="rc__filterbar kcs-dash__filters">
    <input type="date" value={tu} onChange=.../>  <input type="date" value={den} onChange=.../>
    <Select value={loai} options={[Tất cả, Routing, Đột xuất]} .../>
    <Select value={congDoanId} options={...danh mục công đoạn...} .../>
    <input placeholder="Mã đơn/LSX" value={tuKhoa} onChange=.../>
    {/* nhom_loi_id, kcs_department_id: thêm nếu cần, không bắt buộc phải phơi hết 7 filter backend ra UI ngay - tối thiểu: tu/den/loai/cong_doan_id/tu_khoa cho v1, đủ đáp ứng §6.2 "bộ lọc gọn" */}
  </div>

  <div className="kcs-dash__strip">   {/* mirror .kho-dash__strip — dải ngang liền, KHÔNG card rời */}
    <div className="kcs-dash__seg"><span className="kcs-dash__label">Tổng lượt</span><span className="kcs-dash__val">{tong_luot}</span></div>
    <div className="kcs-dash__seg"><span className="kcs-dash__label">Tổng Đạt</span><span className="kcs-dash__val">{fmt(tong_dat)}</span></div>
    <div className="kcs-dash__seg"><span className="kcs-dash__label">Tổng Lỗi</span><span className="kcs-dash__val">{fmt(tong_loi)}</span></div>
    <div className="kcs-dash__seg"><span className="kcs-dash__label">Tỷ lệ đạt</span><span className="kcs-dash__val">{ty_le_dat != null ? `${(ty_le_dat*100).toFixed(1)}%` : "—"}</span></div>
  </div>

  <div className="kcs-dash__charts">   {/* 3 biểu đồ NHỎ, đúng §6.2 — KHÔNG thêm card trang trí (Task 10 mục 3) */}
    <MonthBars .../>  {/* xu hướng lỗi theo ngày — dùng theo_ngay[], trục X=ngay, Y=tong_loi (có thể thêm tong_dat cùng trục nếu MonthBars hỗ trợ multi-series, nếu không thì 1 series tong_loi là đủ tối thiểu) */}
    <MixDonut .../>   {/* nhóm lỗi nhiều nhất — dùng nhom_loi[], top 5 + "Khác" gộp phần còn lại nếu >5 mục */}
    <MixDonut .../>   {/* công đoạn/tổ bị ghi lỗi nhiều nhất — dùng cong_doan[] hoặc to[], chọn 1 trong 2 làm biểu đồ chính; cái còn lại hiện dạng bảng mini bên cạnh nếu chỗ cho phép, KHÔNG bắt buộc phải vẽ cả 2 thành chart nếu chật chỗ mobile */}
  </div>
</section>
```

**Ruling 2**: dùng `MonthBars`/`MixDonut` (`components/charts.tsx`, đã qua validator CVD/contrast,
đang dùng ở `KhachHangPage`/`LogsTab`) thay vì viết Recharts thô như `KhoBaoCaoPage.tsx` (2282
dòng, nặng, viết trước khi có helper dùng chung). Rủi ro nếu `MonthBars`/`MixDonut` không đủ linh
hoạt cho use-case cụ thể (VD: `MonthBars` giả định trục X theo THÁNG chứ không phải NGÀY) — kiểm
lại chữ ký 2 hàm này khi build, nếu không khớp thì viết Recharts thô CỤC BỘ cho biểu đồ đó (không
huỷ bỏ chủ trương "tái dùng trước, viết mới sau" cho biểu đồ còn lại).

**KPI KHÔNG tính lại ở FE** — dùng thẳng `tong_luot`/`tong_dat`/`tong_loi`/`ty_le_dat` từ response
BE (Task 10 mục 2). Filter state (tu/den/loai/cong_doan_id/tu_khoa) là NGUỒN DUY NHẤT truyền xuống
CẢ 3 nơi: gọi `GET /kcs/bao-cao` (KPI+chart), lọc bảng "Kết quả đã ghi" (lịch sử — gọi cùng backend
hay lọc từ cùng 1 nguồn dữ liệu, KHÔNG tự lọc JS trên tập đã tải), và query string của nút Xuất
Excel (Task 10 mục 1, mục 4) — implementer tự quyết cách nối state (Context/prop-drilling/URL
searchParams đều được, miễn LÀ MỘT nguồn).

## 3. `KcsResultDrawer.tsx` — form ghi kết quả

**Ruling 3 ("bốn bước tối giản" nghĩa là gì)**: §6.3 của plan mô tả 5 khối kết thúc bằng "MỘT nút
Lưu kết quả" — không phải wizard Tiếp/Trước như `EmployeeWizard.tsx` (modal 5-bước, có tiền lệ
trong repo nhưng KHÔNG khớp mô tả "một nút Lưu" của §6.3). Đọc "bốn bước" là 4 khối nội dung xếp
DỌC, cuộn liên tục trong MỘT drawer, ẩn/hiện theo điều kiện (progressive disclosure) — không có nút
"Tiếp"/"Trước" tách trang. Rủi ro nếu đọc sai: nếu ý định thật là wizard từng bước, sửa lại là việc
cục bộ trong `KcsResultDrawer.tsx` (đổi từ render-tất-cả-rồi-ẩn sang render-1-khối-tại-1-thời-điểm
+ nút điều hướng kiểu `.ns-steps`) — không ảnh hưởng backend/API.

Cấu trúc (dùng shell `Drawer.tsx`, class gốc `.rc-drawer` + `.kcs-drawer` cho phần riêng):

```
<Drawer open={true} onClose={...} title={mode === "ghi" ? "Ghi kết quả KCS" : "Chi tiết kết quả"}>
  <div className="kcs-drawer__ctx">      {/* Khối 1 — Ngữ cảnh, LUÔN chỉ đọc */}
    Đơn/LSX: {ma_lsx} · Công đoạn: {ten_cong_doan} · Tổ: {ten_to} · Máy: {ten_may}
    Còn chờ: {so_luong_con_cho} {don_vi}
  </div>

  <div className="kcs-drawer__checklist">   {/* Khối 2 — Checklist */}
    {checklist.map(tc => (
      <label className="kcs-check-row" key={tc.thu_tu}>
        <input type="checkbox" checked={dat[tc.thu_tu]} onChange=.../> {tc.ten} {tc.bat_buoc && <span className="kcs-check-row__req">*</span>}
        <input type="text" placeholder="Ghi chú (nếu có)" .../>
      </label>
    ))}
  </div>

  <div className="kcs-drawer__soluong">    {/* Khối 3 — Đạt/Lỗi */}
    <label>Số đạt <input type="number" min={0} value={soDat} onChange=.../></label>
    <label>Số lỗi <input type="number" min={0} value={soLoi} onChange=.../></label>
    {/* validate client: soDat + soLoi phải khớp so_luong_nhan (đã cố định từ context) — CHỈ CẢNH BÁO,
        backend là trọng tài cuối (Task 9 mục 5) */}
  </div>

  {soLoi > 0 && (                          /* Khối 4 — CHỈ hiện khi Lỗi > 0 (Task 9 mục 4) */
    <div className="kcs-drawer__loi">
      <Select label="Nhóm lỗi *" .../>
      <textarea placeholder="Mô tả lỗi"/>
      <Select label="Tổ/công đoạn liên quan" .../>   {/* to_chiu_id — OPTIONAL, "chưa xác định" hợp lệ theo Task 8 Ruling 4 */}
      <div className="kcs-drawer__anh">   {/* ảnh BẮT BUỘC ≥1 khi lỗi>0 — tái dùng logic AnhLuoi của ThsxG5.tsx */}
        {/* input file + preview grid + xoá, luật "giữ tối thiểu 1 ảnh" đã có sẵn ở kcs.py backend */}
      </div>
    </div>
  )}

  <footer className="kcs-drawer__foot">
    <button className="btn btn--accent" onClick={luuKetQua} disabled={!hopLe || saving}>Lưu kết quả</button>
  </footer>
</Drawer>
```

Sau khi lưu KCS CUỐI (`cv.la_kcs_cuoi`) và có `so_dat_chua_gui > 0`: hiện CTA riêng "Tạo yêu cầu
nhập kho ({so_dat_chua_gui} {don_vi})" — một nút, tự vô hiệu hoá khi đang gửi (chống bấm lặp,
đúng Task 9 mục 7 + Task 7 backend đã có `khoa_batch_kcs` chống race).

Không hiện (đúng §6.3): giờ bắt đầu/kết thúc, cỡ mẫu, giao người, nút bắt đầu/tạm dừng/kết thúc,
nút "gửi duyệt", khối phản hồi trách nhiệm (luồng đó là legacy — gỡ khỏi UI mới theo Task 11 mục 5,
Task 9 không cần dựng lại).

**Kiểm đột xuất** (Task 9 mục 6): nút "Kiểm đột xuất" ở `ThucHienKcsPage` mở CÙNG `KcsResultDrawer`
nhưng ở `mode="dot_xuat"` — thêm 1 bước chọn trước: picker công việc (tìm theo mã LSX/đơn, chọn tổ
bị kiểm) rồi mới vào lại đúng 4 khối ở trên (khối 1 "Ngữ cảnh" đổi thành kết quả vừa chọn thay vì
suy từ URL/route). Không cần màn riêng — cùng component, khác `mode`.

## 4. Nút Xuất Excel

**Ruling 4**: dùng ĐÚNG pattern `doExport`/`xuatExcel` đã có (`KhoBaoCaoPage.tsx:705-754`,
`CatalogListPage.tsx:226-240`) — fetch kèm `Authorization: Bearer <token>` → nhận blob → tạo
`<a>` ẩn → click → revoke URL. KHÔNG dùng `<a href="/api/...">` trần (thiếu header auth, endpoint
`/kcs/bao-cao/export.xlsx` gác quyền `export` qua Bearer token). Cần thêm 1 hàm trong `client.ts`
kiểu `api.sanXuat.kcs.baoCao.exportXlsxBlobUrl(token, filters)` (mirror chữ ký hàm kho đã có) — gọi
`GET /api/san-xuat/kcs/bao-cao/export.xlsx` kèm query string ĐÚNG BẰNG filter đang áp dụng cho
KPI/biểu đồ/lịch sử (Task 10 mục 1, mục 4). Nút disable khi đang export, tên file gợi ý
`Báo cáo KCS {tu}_{den}.xlsx` (khớp tinh thần Task 8's `_ten_file_xlsx`, không cần trùng ký tự vì
đây là tên hiển thị khi tải, backend đã tự đặt tên file thật qua header `Content-Disposition`).

## 5. `AppShell.tsx` — điểm nối (đã code sẵn từ Task 4, chỉ đổi 1 chỗ)

`AppShell.tsx:1157-1171` hiện đang render `<ThucHienSxPage mode="kcs" .../>` cho node
`thuc-hien-sx-kcs:{teamId}`. Đổi thành `<ThucHienKcsPage teamId={teamId} tenTo={t?.ten}
eventTick={quoteTick} onBadgeStale={reloadTeams} />`. KHÔNG đổi tên route/id (`thuc-hien-sx-kcs`,
KHÔNG phải `thuc-hien-kcs` như văn bản §6.1 của plan viết — xem Ruling 5) — nav/badge/SSE-refetch
đã hoạt động đúng, chỉ đổi component nào được render.

**Ruling 5 (đặt tên field/route)**: dùng ĐÚNG tên đã tồn tại trong code (`thuc-hien-sx-kcs`,
`so_viec_kcs_cho`, `co_viec_kcs`), KHÔNG đổi theo văn bản §6.1/§5.1 của plan (`thuc-hien-kcs`,
`so_kcs_cho`) — cùng logic Ruling đã ghi ở Task 6 (ledger: "GIỮ NGUYÊN code Task 4 — task-list
chưa bao giờ literal hoá tên field, chỉ mô tả hành vi bằng văn xuôi; đổi tên giờ là rework không
cần thiết, tốn hơn lợi"). Áp dụng nhất quán cho toàn bộ Task 9/10.

## 6. Dọn `ThsxG5.tsx`/`ThsxDrawer.tsx` (Task 9 diện "Sửa")

Theo §6.4: màn production (`mode="production"`) KHÔNG còn hiện KCS. Vì `ThucHienKcsPage` là trang
HOÀN TOÀN MỚI (không phải nhánh trong `ThucHienSxPage`), việc "sửa" `ThsxG5.tsx`/`ThsxDrawer.tsx`
chỉ cần: gỡ điều kiện render `ThsxKcsPanel`/`ThsxKhoPanel`/`ThsxDongNhomPanel`/`ThsxHopThuBar`
(2 hộp thư) khỏi luồng production — kiểm lại xem các panel này đang gate bằng `mode` prop hay bằng
`cv.la_kcs` (nếu bằng `cv.la_kcs` và API `workItems(mode="production")` đã tự loại bỏ các công việc
`la_kcs=true` từ Task 4, có thể KHÔNG CẦN sửa gì thêm ở đây — implementer tự xác nhận bằng cách đọc
code + kiểm dev-browser: mở màn Thực hiện SX thường, xác nhận không còn thấy khối KCS/Kho/Đóng nhóm
nào). Logic dùng chung có ích cho `KcsResultDrawer` (form ghi mẻ, ghi lỗi, upload ảnh) có thể ĐỌC
LẠI từ `ThsxG5.tsx` làm tham khảo triển khai (không phải import chéo — component cũ sẽ ngừng dùng ở
đường production, giữ nguyên cho tới Task 11 mới dọn hẳn theo kế hoạch "legacy cleanup").

## 7. Việc của Task 10 (không phải Task 9, ghi lại để brief Task 10 dùng)

Task 9 dựng KHUNG `KcsDashboard` (KPI strip + 3 biểu đồ + filter bar cơ bản) đã đủ TỰ HOẠT ĐỘNG
(gọi đúng API, hiện đúng số) — không phải placeholder rỗng. Task 10 việc còn lại: đảm bảo filter
bar ĐỒNG BỘ THẬT SỰ giữa KPI/chart/bảng lịch sử/Excel (nếu Task 9 làm mỗi nơi tự gọi API riêng với
state rời rạc, Task 10 phải hợp nhất về 1 state); test 6 kịch bản dữ liệu (không lỗi/chỉ có lỗi/
nhiều tổ/nhiều đơn); kiểm mobile không ép tràn trang cho riêng phần biểu đồ (`ResponsiveContainer`
của Recharts cần `width: 100%` + container cha có `overflow: hidden` hoặc `min-width: 0`, lỗi kinh
điển của grid/flex item không co được — implementer Task 10 tự kiểm bằng browser 375px thật).
