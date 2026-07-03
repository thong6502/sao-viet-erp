# Plan UI/UX — Tính giá & Báo giá theo prototype "ERP Mỹ An Phú"

> Nguồn tham khảo: `https://inan5.superbai.io/pages/17-tinh-gia.html` và `02-bao-gia.html`
> (đã khảo sát list + detail cả 2 trang, 2026-07-03).
> Kết luận thẩm định: **phù hợp ~85%** — prototype cùng tư duy domain với kiến trúc SVN
> (giá vốn khóa từ phiếu tính giá, báo giá theo phiên bản, markup tách khỏi giá vốn),
> chi phí chuyển chủ yếu là tầng trình bày frontend.

## Logic nghiệp vụ đã chốt (KHÓA — không bàn lại)

1. **Báo giá không bao giờ soạn tay.** Mọi dòng báo giá sinh từ **picker phiếu tính giá**
   đã tính xong (`status=calculated`, `can_create_quote=true`).
2. **1 báo giá = pick từ NHIỀU phiếu tính giá** (khách hỏi nhiều sản phẩm cùng lúc →
   gộp 1 báo giá). Mỗi dòng item = 1 phiếu + 1 mức số lượng đã chọn.
3. **Giá vốn đóng băng per dòng** (snapshot SEAM-13: `total_cost_snapshot`,
   `internal_cost_snapshot_json`) — Báo giá chỉ đọc, "không chỉnh ở đây".
4. **Markup/VAT là việc của Báo giá**: gói biên (%), slider, giá bán, VAT, tổng — per dòng
   hoặc áp chung; Tính giá chỉ ra giá vốn nội bộ.
5. **Giữ điểm mạnh hiện có, không copy ngược prototype**:
   - Đa mức số lượng mỗi phiếu tính giá (prototype chỉ 1 SL) — GIỮ.
   - Định mức mực **đ/1000 lượt-màu** versioned (prototype dùng kg) — GIỮ engine, chỉ học cách trình bày.
6. **Hoãn** (ngoài đợt này): duyệt nội bộ 2 cấp (Chờ sếp duyệt/Duyệt/Trả lại), tab
   "Thông tin SX" (checklist ra lệnh SX — chưa có module Sản xuất), thảo luận/comment.

## Mapping prototype ↔ code hiện có

| Prototype | SVN |
| --- | --- |
| "Giá vốn KHÓA TỪ PTG — không chỉnh ở đây" | SEAM-13 `EstimateCostingAdapter` + snapshot copy-on-write |
| Phiên bản v1/v2/v3 + lý do + so sánh | `Quote → QuoteVersion(change_reason) → QuoteItem` |
| Soạn → Gửi khách → Khách chốt/Từ chối → Đã lên đơn | statuses draft/sent/accepted/rejected/expired/converted_to_order |
| Timeline Hoạt động | `QuoteActivityLog` |
| Bảng tính giá vốn [REALTIME] | `POST /api/estimates/preview` (live preview đã có) |
| Tham chiếu ↳ PTG ↔ BG | `estimate_id`/`estimate_option_id` |
| Thẩm mỹ kem + gạch nung + panel tối | Design system hiện tại — không cần re-theme |

## Các phase

> Nguyên tắc thứ tự: Tính giá trước (vùng an toàn), Báo giá sau cùng (đợi backend
> H-V-I ổn định — chuỗi import quotation/order phải lành thì backend mới restart được).
> Phase 0–4 gần như thuần frontend, không reset DB.

### Phase 0 — Component dùng chung (`frontend/src/components/`)

- `StatusTabs` — thanh tab trạng thái + đếm số (có tab kiểu "Cần tôi xử lý").
- `Timeline` — dòng thời gian hoạt động (icon, title, meta ngày·người).
- `DarkSummaryPanel` — panel tổng tiền nền tối (số to, subtitle, các dòng con, ghi chú).
- Style bảng nhóm section (section header trong tbody).

### Phase 1 — List Tính giá (`TinhGiaPage.tsx` + API additive)

- Tab đếm số thay dropdown lọc trạng thái: Tất cả / Nháp / Đã tính / Lỗi chặn.
- Cột Sản phẩm 2 tầng: tên + dòng spec (`20×30 cm · Couche 150gsm · 4 màu`).
- Cột **Giá vốn/đơn** cạnh tổng; cột Ngày + người lập; chip công nghệ (offset/digital).
- Backend additive (code trước, hiệu lực sau restart): bổ sung field list
  (`spec_summary`, `machine_type`...) — frontend render khi có, fallback khi chưa.

### Phase 2 — Form Tính giá: lưới + cảnh báo inline

- Nén 8 section dọc → lưới 2–3 cột như prototype (SL / khổ thành phẩm / giấy / khổ giấy / tay kê...).
- Gia công sau in = chip bật/tắt (giữ chọn Nội bộ/Outsource trong chip mở rộng).
- **Cảnh báo live preview đặt ngay dưới ô liên quan** (vượt khổ → dưới ô khổ giấy).
- Giá trị tự tính (số kẽm, số tờ) hiện ô nền tô, không cho sửa.
- Sidebar nâng thành `DarkSummaryPanel` "TỔNG GIÁ VỐN (NỘI BỘ)" + subtotal
  Vật tư / Khuôn·Bản / Máy+Công / Gia công + ghi chú "chưa cộng lợi nhuận".

### Phase 3 — Sơ đồ bình bản trực quan (wow #1 của Tính giá)

- `ImpositionDiagram.tsx`: SVG tờ giấy + xếp con đánh số, vẽ vùng nhíp/xén/bleed/chừa giữa.
- **Phải dùng đúng công thức engine** (`pricing_engine` auto-imposition) để hình không nói dối số.
- Panel kèm: bố cục N×M, con/tờ, hiệu suất kê %, cập nhật realtime cùng preview.
- Thuần frontend.

### Phase 4 — Trang kết quả: bảng nhóm khu + box thông số SX

- Bảng phân rã nhóm section theo `category`: NGUYÊN VẬT LIỆU (material+ink) /
  KHUÔN·BẢN (plate_die+click_ink) / MÁY + CÔNG (machine) / GIA CÔNG SAU IN
  (operation+packing) / PHÍ PHÁT SINH (outsource+delivery+other).
- Mỗi dòng: mô tả phụ + đơn giá kèm đơn vị ("450đ/lượt").
- Box "THÔNG SỐ SẢN XUẤT" trên đầu (từ calc snapshot: con/tờ, tờ in, hao hụt, lượt-tờ, giờ máy).
- GIỮ: bảng so sánh đa mức SL + panel "Diễn giải cách tính".

### Phase 5 — List Báo giá *(chờ backend H-V-I chạy)*

- Tab trạng thái đếm số + "Cần tôi xử lý"; cột phiên bản (chip vN + số bản);
  ↳ link mã Tính giá; giá bán + markup%; chip tuổi phiếu "Đã gửi N ngày · cần follow-up"
  (tính từ `sent_at`, thuần frontend).

### Phase 6 — Picker đa phiếu + Detail Báo giá (wow #2, trung tâm)

- **Picker 2 cột**: trái = phiếu đủ điều kiện (search, spec, các mức SL + giá vốn);
  phải = giỏ dòng đã pick (`↳ mã phiếu · SP · SL · giá vốn khóa · % biên · giá bán`).
  Áp gói biên chung hoặc per dòng. Từ trang Tính giá, "Tạo báo giá" pre-pick phiếu đang mở.
- **Detail**: trái = khối "🔒 Giá vốn — khóa từ phiếu tính giá" (read-only, link mở phiếu)
  kèm điều khoản, hiệu lực, lý do phiên bản, lịch sử phiên bản (so sánh 2 bản);
  phải = panel tối GIÁ BÁN ĐỀ XUẤT (4 gói biên 12/18/25/35 làm shortcut UI, slider,
  ô % tự do) → Lợi nhuận → Giá bán → VAT → Tổng, tính sống; card Khách hàng; Timeline.
- Action theo trạng thái (Gửi khách / Khách chốt / Từ chối / Tạo đơn hàng) + **"Xem in"**
  (print CSS báo giá gửi khách).
- **Delta backend (additive, cần điều phối với nhánh backend Báo giá đang làm)**:
  - `QuoteItem.estimate_id` (FK per dòng) — phục vụ 1 BG nhiều phiếu.
  - Picker API nhận danh sách `(estimate_id, option_ids[])`.
  - Gom chung 1 lần reset `dev.db` (backup trước).

### Phase 7 — Tùy chọn sau cùng

- Duyệt nội bộ 2 cấp (PTG "Đã duyệt·khóa"; BG "Chờ sếp duyệt→Duyệt/Trả lại").
- Gói biên cấu hình được trên UI (luật dự án: không hardcode số liệu nghiệp vụ).
- Thảo luận/comment.

### Seed — nối Tính giá ↔ Báo giá (2026-07-03)

`seed_sales_history` trước đây tạo báo giá "trơ" (QuoteItem `estimate_id=None`, giá vốn = total×0.8 bịa).
Đã sửa: thêm helper `_mk_estimate()` tạo `Estimate`(mã TG qua `SequenceService("costing")`, status
`converted_to_quote`) + `EstimateOption`; `_mk_quote()` giờ tạo phiếu tính giá NGUỒN rồi set
`QuoteItem.estimate_id/estimate_option_id/product_spec_text` + `Quote.estimate_id`. Số tiền giữ nguyên
(giá vốn=total×0.8, biên 20% → khớp cũ). Thêm 1 báo giá **nháp đa dòng** (Catalogue+Tờ rơi = 2 phiếu, giữ
demo BG-nhiều-dòng) + 2 phiếu **'calculated' độc lập** cho picker "Báo giá mới" không rỗng sau reset.
Đã reset `dev.db` (backup `dev.db.bak-linkseed`) + restart. **Verify API**: 11/11 báo giá có `estimate_refs`
(TG25/TG26); detail có `estimate_id`+`estimate_number`+`product_spec_text`; `GET /api/estimates/{id}`→200
(mở được phiếu); picker có 2 phiếu calculated. Pattern hand-create theo `tests/test_quotations_api.py::_mk_estimate`
(spec tối thiểu `{finished_width,finished_height,colors,sides}`, `warnings_json=[]`, không cần chạy engine).

## Rủi ro & ràng buộc

1. Backend Báo giá đang chuyển đổi H-V-I ở nhánh song song → Phase 5–6 xếp cuối,
   delta schema cài khi chuỗi import ổn định. Không sửa đè vùng đó.
2. Không Alembic → cột mới = reset `dev.db` (gom 1 lần, backup `dev.db.bak-*`).
3. Sơ đồ bình bản phải mirror đúng công thức engine (usable = khổ − nhíp − 2×xén,
   con = thành phẩm + 2×bleed + chừa giữa) — sai là hình lừa người dùng.
4. Backend hiện KHÔNG restart được cho tới khi chuỗi import quotation/order lành —
   mọi thay đổi backend đợt này chỉ verify được sau đó.

## Tiến độ

- [x] Phase 0 — component chung (`StatusTabs`, `Timeline`, `DarkSummaryPanel`, `ui-blocks.css`) — verify browser 2026-07-03
- [x] Phase 1 — list Tính giá (tabs đếm số, sản phẩm 2 tầng, giá vốn/đơn, cột cập nhật; backend additive:
      `EstimateRow` +6 field, `GET /api/estimates/stats`, filter `has_blocking` — CHỜ restart backend mới hiệu lực,
      frontend fallback sạch khi backend cũ)
- [x] Phase 2 — sidebar form → `DarkSummaryPanel` "TỔNG GIÁ VỐN (NỘI BỘ)" + subtotal nhóm — verify browser
- [x] Phase 3 — sơ đồ bình bản SVG (`ImpositionDiagram`, mirror công thức engine; 21×29,7/65×86 → 2×4 xoay 90° = 8 con,
      hiệu suất 89%; case vượt khổ vẽ đỏ + cảnh báo) — verify browser
- [x] Phase 4 — kết quả: box "Thông số sản xuất" + bảng nhóm 5 khu + đơn giá kèm đơn vị (đ/tờ, đ/lượt...) — verify browser
- [x] Phase 5 — list Báo giá: tabs đếm số (`GET /api/quotations/stats`, filter `need_action`),
      chip vN + số phiên bản, sản phẩm + ↳ mã phiếu TG, biên %, tuổi phiếu "gửi N ngày" — verify browser
- [x] Phase 6 — picker đa phiếu (giỏ chip, mỗi phiếu kéo mức SL + giá vốn khóa; create gửi `picks[]`)
      + detail panel "GIÁ BÁN ĐỀ XUẤT" 4 gói biên áp cả phiếu khi nháp — verify e2e:
      BG26-0011 pick TG26-0002+0003 → 4 dòng → gói 12% → tổng 20.284.000 → 18.440.000
- [x] Phase 7 — **Detail "ý hệt" prototype inan5 (2026-07-03, parity UI)**: user chốt inan5 là chuẩn → sửa SVN.
      Chuyển `QuotationDetailDialog` (modal 4 tab) → `QuotationDetailView` (trang 2 cột in-page, `.bgv`,
      list⇄editor toggle như inan5). Trái: card giá vốn khóa dạng bảng dòng (SP+↳PTG+spec · SL · giá vốn ·
      markup% editable từng dòng · thành tiền VAT) + điều khoản/hiệu lực/lý do + follow-up "Theo dõi gửi khách"
      (kênh/ngày gửi/hạn/đã gửi N ngày + "Ghi nhận đã liên hệ") + Lịch sử phiên bản + "So sánh". Phải: panel tối
      "GIÁ BÁN ĐỀ XUẤT" với 4 gói biên + **slider + ô % nhập tay đồng bộ** (1 dòng) / ẩn khi đa dòng, đơn giá/cái,
      toggle "Bắt buộc cấp trên duyệt", breakdown sống; card Khách hàng; timeline Hoạt động; Thảo luận (role selector).
      **Xem in = bản song ngữ VN/EN letterhead MY AN PHU** (bảng chưa-VAT, 5 ghi chú, 2 ô ký). CSS port `.bgv`+`.qpdf`
      vào `bao-gia.css` (thêm `--paper-2`,`--rust-2`; tokens còn lại trùng SVN). Backend-backed chạy thật (margin
      persist qua PUT + reload, transitions, requote, pdf). **Mockup parity-UI (localStorage, chưa backend):** thảo
      luận (`bgv_comments_*`), nhân bản, ghi nhận liên hệ (`bgv_contact_*`), toggle duyệt (`bgv_appr_*`). Verify e2e:
      BG26-0005 (sent, 1 dòng) layout+follow-up+in; BG26-0011 (nháp, 4 dòng) sửa markup dòng 1 12→30 → total
      18.440.000→19.489.143 persist thật; thảo luận gửi OK; typecheck sạch. **TODO nối backend sau:** comment/duplicate/
      contact-log/approval-2-cấp. **Bản in đã đổi letterhead sang Sao Việt Nhật** (logo thật
      `assets/sao-viet-nhat-logo-mark.png` + const `SVN_COMPANY`); các trường pháp lý (địa chỉ/MST/điện thoại/
      email/website/người gửi) để "—" chờ khảo sát — KHÔNG bịa (luật "không hardcode số liệu"). Điền `SVN_COMPANY`
      trong `BaoGiaPage.tsx` khi có giấy phép kinh doanh Sao Việt Nhật.

Backend đã heal + hoàn tất (commit a79fa6e): chuỗi import lành, `QuoteItem.estimate_id`,
create đa phiếu strict, suite 298 pass. Bug bắt được khi làm: CHECK estimates thiếu
converted_to_quote; picker gọi get_estimate không tồn tại; orders router đọc field cũ;
seed đếm tay quote_number lệch SequenceService (đụng UNIQUE khi tạo phiếu mới).

Fix kèm theo khi verify: label máy in dùng nhầm `process_type` ("in") thay vì `machine_type` →
Mitsubishi offset từng hiện "- Khổ lớn"; select `.tg__statusfilter` bị `.input{width:100%}` đè → giãn nguyên hàng.
