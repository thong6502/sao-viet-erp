# Spec — Kế hoạch vật tư (siết logic trên giữ chỗ hiện có)

> Bối cảnh: `GiuChoService` (giữ chỗ vật tư) đã được chủ dự án chốt và build ngày 17/08/2026
> (xem docstring `backend/app/services/giu_cho_service.py:1-38`). Bản spec này KHÔNG xây chức
> năng giữ chỗ mới — nó SIẾT một số điểm còn hở trên nền đã có: liên kết ngược về đúng dòng
> PMH, chặn sửa nhu cầu khi đang giữ, nối thật Kho ↔ Mua hàng (hiện chỉ là chỗ neo bỏ trống),
> và đẩy realtime. Bàn ngày 30/08/2026.

## 0. Hiện trạng — cái gì đã có, khỏi làm lại

Đối chiếu với code trước khi thiết kế để không tính lại đường đã có:

| Yêu cầu | Đã có ở đâu | Ghi chú |
|---|---|---|
| Bảng giữ chỗ, nguồn `kho`/`dang_ve` | `models/vat_tu_giu_cho.py:59-105`, migration `0208_giu_cho_vat_tu` (`db_migrations.py:8720-8789`) | Cột hiện có: `hang_loai/hang_id`, `lsx_id/bai_ghep_id` (đúng 1), `so_luong`, `nguon`, `ngay_ve`. **Chưa có** `purchase_request_line_id`. |
| 2 công tắc bật/tắt | `models/lsx.py:130-132` (`Lsx.giu_cho_bat`), `models/bai_ghep.py:63-66` (`BaiGhep.giu_cho_bat`) | |
| Giữ tồn tự do trước, bám hàng đang về sau, giữ một phần vẫn bật | `GiuChoService.bat()` / `nhat_them()` (`giu_cho_service.py:422`, `:441`) | Đúng thứ tự spec §3 đòi, theo ngày cần tăng dần. |
| Không giữ đích danh lô / không tự hết hạn / không cướp ưu tiên hộ | Docstring `giu_cho_service.py:31-37` + `NGUONG_GIU_LAU_NGAY` (`:58`) | Ba nguyên tắc "cố ý không làm" trùng khớp §"Mặc định đã khoá" của spec này. |
| Xuất kho chỉ ăn tồn tự do + phần chính chủ giữ; ghi sổ xong tự chuyển giữ chỗ → đã cấp | `GiuChoService.kiem_xuat()` / `tieu_thu()` (`:498`, `:527`), gọi từ `stock_voucher_service.py:293-297,341-346` | Đúng luật §3 "Xuất kho". |
| Đèn vật tư tổng quan LSX | `services/lsx_tong_quan.py:75-100` (`_den_vat_tu`), soi thẳng `GiuChoService.trang_thai()` | |
| Cửa chặn phát hành lịch thiếu vật tư | `xep_lich_2/release.py:44-123` (`soat_vat_tu`/`van_de_vat_tu`), `xep_lich_2/constraint.py:466` (`truoc_ngay_vat_tu`) | `xep_lich_2/context.py:200-218` (`ngay_vat_tu()`) đọc THẲNG bảng giữ chỗ (không chạy lại `can_doi()`) vì lý do hiệu năng (kéo-thả gọi liên tục) — **không phải** đường tính thứ hai, cùng ý nghĩa `xep_som_nhat`. |
| Chủ thể: lệnh đã ghép vào bài tính theo bài đại diện | `ke_hoach_vat_tu_service.py:833` (`_gom_nhu_cau`) | |
| Ngày cần: có lịch lấy `start_at`, chưa có lịch lùi từ hạn | `ke_hoach_vat_tu_service.py:400-410` (`_nap_lich`), `:414-438` (`_moc_tam`, kèm cờ suy được/lý do `chua_co_han`/`chua_gan_may`), `:440-445` (`_ngay_can_buoc` = start − `CAP_PHAT_TRUOC_PHUT`) | |
| 1 màn Kế hoạch vật tư, 2 cách gom | `frontend/src/pages/KeHoachVatTuPage.tsx` (toggle `hang`\|`lenh`), `VatTuKeHoachView.tsx`, `GiuChoTheoLenhView.tsx` | |
| Cầu nối "Nhập kho" từ đợt giao PMH | `StockRequest.purchase_delivery_id` (mg `0189_stock_request_purchase_delivery_id`), router `POST /api/kho/de-nghi` nhận field này, FE nút "Nhập kho" ở `DeliveriesBlock.tsx` → seed `KhoDeNghiPage.tsx` (khoá form, `purchase_delivery_id` gửi kèm), `purchase_service.py:3148-3166` tính `da_nhap_kho`/`stock_request_ma` cho mỗi đợt giao | **ĐÃ CÀI ĐẶT ĐẦY ĐỦ END-TO-END** (backend + FE) — KHÔNG phải làm mới, xem §3.3 sửa lại. `PurchaseDelivery.stock_voucher_id` (`models/purchase.py:414-417`) là field CHẾT (luôn `NULL`, không ai đọc/ghi) — implementation thật đi hướng khác (soft-ref ngược từ `StockRequest`), bỏ qua field này. |

Việc còn lại ở các mục dưới đây là phần THỰC SỰ mới hoặc đổi hành vi so với hiện trạng.

## 1. Kiến trúc và logic chung

- Không tạo chức năng giữ chỗ mới. `vat_tu_giu_cho` tiếp tục là sổ cam kết duy nhất.
- Một kết quả tính chung ở backend (đã đúng hướng: `KeHoachVatTuService.can_doi()` là nguồn
  NHU CẦU duy nhất, `GiuChoService` đọc lại chứ không tính lại — xem docstring `giu_cho_service.py:8-13`),
  dùng cho: cân đối theo mặt hàng · cân đối theo LSX/bài ghép · bật giữ chỗ · gợi ý mua · kiểm
  tra phát hành lịch · đèn vật tư tổng quan LSX. Giữ nguyên nguyên tắc này, không viết đường
  tính thứ hai ở bất kỳ chỗ mới nào (kể cả cầu nối Kho ↔ Mua hàng ở §3).
- Kho là nguồn tồn thật duy nhất (`StockLot`, FIFO theo lô — `models/stock_lot.py:61-125`); FE
  chỉ hiển thị kết quả backend, không tự tính tỷ lệ đủ hàng (xem §4, việc cần bỏ ở FE).

Thứ tự tính cho từng nhu cầu (đã đúng thứ tự trong `nhat_them()`):

1. Xác định nhu cầu và ngày cần của từng công đoạn (`can_doi()`, `_nap_lich`/`_moc_tam`).
2. Trừ lượng Kho đã ghi sổ xuất — phân bổ một lần theo ngày cần, tránh trừ lặp khi cùng vật tư
   xuất hiện ở nhiều công đoạn (`con_phai_co` = nhu cầu − đã cấp, gộp theo chủ thể ở
   `_nhu_cau_theo_chu_the`).
3. Áp phần đã giữ của đúng LSX/bài ghép.
4. Phân bổ thử tồn kho tự do (`ton_tu_do()`).
5. Phân bổ thử hàng đang về đủ điều kiện (`_lo_dang_ve()`).
6. Phần còn lại mới là thiếu cần mua.

Ưu tiên phân bổ: ngày cần sớm trước, ngày chưa xác định đứng cuối; cờ gấp chỉ cảnh báo, không
tự cướp chỗ đã giữ (đã đúng, không đổi).

## 2. Nhu cầu, nguồn và trạng thái

- Ngày cần: giữ nguyên `_nap_lich`/`_moc_tam`/`_ngay_can_buoc` đã có. Không đủ máy, thời lượng,
  đơn vị hoặc hạn → trả `Chưa rõ` (`khong_ro`), không mặc định là đủ — đã đúng.
- Chủ thể:
  - Giấy và vật tư bước chung thuộc bài ghép; vật tư bước riêng thuộc LSX thành viên — đã đúng
    ở `_gom_nhu_cau`.
  - **[MỚI]** Chỉ quy phiếu xuất từ LSX sang bài ghép nếu không có nhu cầu LSX tương ứng và có
    đúng một nhu cầu chung khớp; trường hợp mơ hồ phải cảnh báo. Vị trí vá:
    `stock_voucher_service.py:_gom_theo_hang_va_chu_the` (`:514-531`) hiện đọc thẳng
    `(rl.lsx_id, rl.bai_ghep_id)` từ dòng gốc — cần thêm bước re-map: nếu `lsx_id` không xuất
    hiện trong `_nhu_cau_theo_chu_the()` của `can_doi()` (tức lệnh đã ghép, nhu cầu đã chuyển
    sang bài), tìm đúng 1 bài ghép đang chứa `lsx_id` đó và dùng `bai_ghep_id` thay thế; nếu
    khớp 0 hoặc >1, chặn ghi sổ kèm thông báo mơ hồ (không đoán).
  - Tồn tự do trong kho chỉ trừ giữ chỗ có `nguon=kho`; giữ từ hàng đang về không được làm giảm
    tồn hiện tại — đã đúng (`ton_tu_do()` chỉ đọc `on_hand_map`, độc lập `dang_ve`).
  - Hàng đang về chỉ hợp lệ khi đơn đã đặt với NCC và có ngày dự kiến. Phiếu mới duyệt chỉ hiện
    dấu vết mua, không mở khoá lịch — cần rà `_hang_dang_ve()` (`ke_hoach_vat_tu_service.py:501-551`)
    xác nhận điều kiện lọc hiện tại (trạng thái đơn + có ngày) đã đủ chặt theo đúng câu này.

Mỗi dòng trả các lượng: `da_cap`, `da_giu_kho`, `da_giu_dang_ve`, `co_the_giu_kho`,
`co_the_giu_dang_ve`, `thieu`, `dang_linh` (chỉ thông tin tiến độ). **[MỚI]** — `can_doi()`/
`theo_chu_the()` hiện chỉ trả `con_phai_co`/`thieu`/`dang_giu` gộp, chưa tách `da_giu_kho` /
`da_giu_dang_ve` / `co_the_giu_*`; cần mở rộng để FE bỏ được phép tính riêng (xem §4).

Trạng thái hành động lấy mức xấu nhất: `Chưa rõ → Thiếu → Về muộn → Có thể giữ → Đã giữ → Đã
cấp` (đã có `_NANG` — cần bổ sung 2 mức `Có thể giữ`/`Đã cấp` vào thang hiện tại
`{khong_ro, do, ve_muon, vang, xanh, xam}`, đối chiếu bảng ánh xạ trạng thái cũ→mới khi viết
plan). Dòng hỗn hợp vẫn hiện đầy đủ từng lượng, không chỉ một màu tổng.

Gợi ý mua chỉ lấy phần thiếu sau toàn bộ phân bổ (đã đúng, `/de-nghi-mua` đọc `thieu`). Hàng đã
đặt nhưng về muộn không tạo mua trùng; hành động là hối NCC hoặc dời lịch — đã đúng tinh thần
(không có luồng tự tạo PMH trùng).

## 3. Giữ chỗ, Mua hàng và Kho

### 3.1 Liên kết `purchase_request_line_id` — **[MỚI]**

Bổ sung cột `purchase_request_line_id` (nullable, `FK purchase_request_lines.id ON DELETE SET
NULL` — soft đủ, không cần cứng vì dòng PMH có thể bị xoá khi PMH còn nháp) cho:

- `vat_tu_giu_cho` — dòng nguồn `dang_ve`. Dòng nguồn `kho` không gắn (không có PMH nào để gắn).
- Yêu cầu nhập kho sinh từ đợt giao mua hàng (xem 3.3) — `stock_requests` thêm
  `purchase_delivery_id` (không phải `purchase_request_line_id`, vì một đợt giao gộp nhiều dòng
  PMH — xem 3.3).

**Quyết định đã chốt (30/08/2026):** backfill dữ liệu giữ chỗ `dang_ve` hiện có trong DB dev
KHÔNG viết thuật toán khớp ngược theo mặt hàng+ngày+thứ tự PMH. Vì đây là dữ liệu demo, dev chưa
có prod thật (xem `docs/DB_SCHEMA.md` nguyên tắc "sửa đúng, không giữ tương thích ngược"),
migration mới chỉ cần: xoá sạch các dòng `vat_tu_giu_cho` hiện có (hoặc chỉ dòng `nguon=dang_ve`
nếu muốn giữ dòng `kho` — quyết định lúc viết plan tuỳ độ phức tạp), rồi gọi lại
`GiuChoService.nhat_them()` cho mọi chủ thể đang `giu_cho_bat=true` để dựng lại đúng theo cột
mới. Không cần đúng tuyệt đối với lịch sử cũ.

### 3.2 Giữ chỗ kho không neo lô

Đã đúng — `_dong()` (`giu_cho_service.py:596-601`) không ghi `stock_lot_id`, chỉ ghi cặp (mặt
hàng, số lượng). Không đổi.

### 3.3 Nhập kho — cầu nối Kho ↔ Mua hàng — **ĐÃ CÀI ĐẶT ĐẦY ĐỦ, chỉ còn vá bước 3 (giữ chỗ)**

**Sửa lại sau khi đối chiếu code (30/08/2026):** toàn bộ pipeline "nút Nhập kho trên đợt giao
PMH → tạo `StockRequest(REQ_NHAP, purchase_delivery_id=...)` điền sẵn khoá form → Kho kiểm
đếm/ghi sổ như luồng thường → đợt giao đổi nhãn 'Đã nhập · &lt;mã&gt;'" **đã chạy được thật**, cả
backend lẫn FE — KHÔNG phải làm mới:

- `StockRequest.purchase_delivery_id` đã có từ mg `0189_stock_request_purchase_delivery_id`
  (`models/stock_request.py`, soft-ref, không FK).
- `StockRequestService.create()` (`stock_request_service.py:91-131`) đã nhận `**header` gồm
  `purchase_delivery_id`, tạo = duyệt luôn (`trang_thai=REQ_APPROVED`, bỏ bước chờ duyệt từ
  06/08/2026).
- Router `POST /api/kho/de-nghi` (`routers/kho_request.py:357-373`) đã chuyển thẳng
  `payload.purchase_delivery_id` xuống service.
- `purchase_service.py:3148-3166` đã tính `da_nhap_kho`/`stock_request_id`/`stock_request_ma`
  cho mỗi đợt giao (JOIN `StockRequest.purchase_delivery_id`, loại trừ `REQ_CANCELLED`).
- FE: nút "Nhập kho" (`DeliveriesBlock.tsx:284-300`, quyền `kho:request`) → `nhapKhoTuDot()`
  (`PurchaseRequestsPage.tsx:84-117`, khớp `PurchaseDeliveryLine → PurchaseRequestLine` lấy
  `hang_loai/hang_id/đơn giá`) → `navigate("kho-main", {khoNhapSeed: {...}})` → `KhoPage.tsx` →
  `KhoDeNghiPage.tsx` (form khoá, trừ ô mặt hàng còn thiếu `hang_id`) → `save()` gọi
  `api.kho.deNghi.create(..., purchase_delivery_id: seedDeliveryId)`.
- `PurchaseDelivery.stock_voucher_id` (`models/purchase.py:414-417`, comment "chỗ neo") là field
  **CHẾT** — implementation thật đi hướng khác (soft-ref NGƯỢC từ `StockRequest`), không đụng
  tới field này. Giữ nguyên đúng quy ước dự án (không Alembic, không xoá cột) — không cần dọn.

**Phần THỰC SỰ còn thiếu (đây mới là việc của spec này) — bước "ghi sổ nhập → chuyển giữ chỗ":**

Khi Kho ghi sổ một `StockVoucher(NHẬP)` ứng với yêu cầu có `purchase_delivery_id` (tức bấm
"Ghi sổ" sau khi tạo phiếu từ yêu cầu Nhập-kho-từ-PMH), **hiện tại chỉ chạy `nhat_them()`** (đã
có, `stock_voucher_service.py::_apply_post` dòng ~341-346, nhánh NHẬP) — hàm này BÙ TIẾP cho các
chủ thể đang bật giữ theo tồn tự do MỚI, nhưng **không** làm bước trung gian bắt buộc trước đó:
chuyển đúng phần giữ hứa (`nguon=dang_ve`) đã bám vào lô này sang `nguon=kho` (dòng giữ chỗ tạo
CŨ NHẤT trước — khớp thứ tự `_lo_dang_ve()` đã cấp khi giữ hứa, không cần biết chính xác
`purchase_request_line_id` nào vì bảng giữ chỗ cố ý không neo dòng PMH cụ thể, chỉ theo tổng
(mặt hàng, ngày) — xem `_lo_dang_ve()`). Không có bước này thì `nhat_them()` một mình vẫn ĐÚNG
kết quả cuối cùng về mặt SỐ LƯỢNG (vì nó tính lại từ đầu dựa trên tồn/nhu cầu hiện tại), nhưng
**không đúng theo nghĩa "giữ chỗ hứa hoá thành giữ chỗ chắc"** — một dòng `dang_ve` có thể vẫn
đứng nguyên dù lô nó bám vào đã về, và một chủ thể KHÁC (không phải chủ nhân giữ hứa ban đầu) có
thể được `nhat_them()` cấp phần tồn mới trước, đảo lộn thứ tự ưu tiên ngày-cần đã cam kết lúc
giữ hứa.

→ Việc cần làm: hàm mới `GiuChoService.chuyen_dang_ve_sang_kho(hang: Hang, so_luong: float) ->
None`, gọi TRƯỚC `nhat_them()` trong `_apply_post` (nhánh NHẬP), chuyển tối đa `so_luong` từ các
dòng `nguon=dang_ve` của **đúng mặt hàng đó** sang `nguon=kho`, dòng `created_at` cũ nhất trước.
Phần `so_luong` vượt quá tổng đang giữ hứa của mặt hàng đó thì bỏ qua (tồn tự do tăng, để
`nhat_them()` phân bổ tiếp theo đúng thứ tự ngày cần — không tạo giữ chỗ mới ở bước này).

### 3.4 Xuất kho

Đã đúng ở `kiem_xuat()`/`tieu_thu()` — chỉ cần vá phần "quy phiếu xuất từ LSX sang bài ghép" đã
nêu ở §2.

### 3.5 PMH thay đổi — **[MỚI]**

- Lùi ngày giao dự kiến: cập nhật ngày chặn lịch (`ngay_ve` trên các dòng `dang_ve` tương ứng —
  cách khớp "tương ứng" theo đúng nguyên tắc §3.3 bước 3, không theo `purchase_request_line_id`
  đơn lẻ) + cảnh báo realtime cho chủ thể đang bám lô đó.
- Giảm số lượng dòng / huỷ PMH / huỷ dòng: nhả phần không còn nguồn. Thứ tự nhả: **dòng giữ chỗ
  tạo SAU trước** (LIFO theo `created_at`, ngược với thứ tự cấp phát khi nhận hàng) — không tự
  chuyển ngay sang nguồn khác, chỉ nhả và để `theo_chu_the()`/đèn vật tư báo thiếu lại như bình
  thường; người lập kế hoạch tự quyết bật giữ lại hoặc chờ.
- Ghi nhận đợt giao nhưng Kho chưa ghi sổ: vẫn là hàng chờ nhập (đứng ở bước `StockRequest`
  chưa duyệt/chưa cấp), chưa phải tồn thật — không đổi gì ở `_hang_dang_ve()`.

### 3.6 Nhu cầu thay đổi khi đang giữ — **[MỚI, chặn cứng]**

**Quyết định đã chốt (30/08/2026):** chặn cả hai kịch bản dưới, không chỉ kịch bản hẹp:

1. Sửa số lượng/quy cách công đoạn cần vật tư (`LsxCongDoanVatTu`) khi LSX/bài ghép chứa nó đang
   `giu_cho_bat=true`.
2. Ghép/tách bài ghép, đổi routing (thêm/bớt/đổi công đoạn), huỷ LSX khi LSX hoặc bài ghép liên
   quan đang `giu_cho_bat=true`.

Cả hai chặn bằng cách kiểm `giu_cho_bat` của (các) chủ thể liên quan ngay ở tầng service tương
ứng (LSX, routing, bài ghép), trả lỗi rõ ràng kiểu *"LSX-1050 đang giữ chỗ N kg giấy X — vào Kế
hoạch vật tư nhả trước khi sửa"* — không chặn ở FE đơn thuần (phải chặn ở backend, FE chỉ hiển
thị lỗi). Với thao tác ghép/tách bài: kiểm TẤT CẢ LSX thành viên liên quan trước khi cho ghép;
một LSX đang giữ chỗ riêng thì chặn cả thao tác ghép cho tới khi nhả.

Giữ lâu hoặc rơi khỏi phạm vi: tiếp tục cảnh báo (`giu_lau_chua_chay`, `_them_mo_coi` đã có),
không tự nhả — không đổi.

Mọi thao tác giữ, nhập, xuất và đối soát nguồn chạy trong một giao dịch, khoá nguồn theo thứ tự
ổn định (ví dụ luôn khoá theo `(hang_loai, hang_id)` tăng dần trước khi khoá theo chủ thể) và
chỉ commit một lần; lỗi giữa chừng phải rollback toàn bộ.

## 4. API và giao diện hiện có

- Giữ nguyên các endpoint và payload bật/tắt giữ chỗ (`POST /giu-cho/bat`, `/giu-cho/tat`).
- Mở rộng `/can-doi` và `/theo-lenh` bằng các lượng phân rã (§2) và nguồn PMH cụ thể (mảng các
  `purchase_request_line_id`/mã PMH đang góp cho phần `dang_ve` của dòng, để FE hiện được "đang
  bám đơn nào"); cập nhật enum trạng thái đồng bộ FE/BE (thang 6 mức ở §2).
- Kết quả đợt giao PMH trả rõ: đã tạo `StockRequest` hay chưa, trạng thái yêu cầu đó, đã ghi sổ
  nhập thực tế hay chưa (đọc qua `purchase_delivery_id` mới trên `stock_requests`).
- Giữ nguyên một màn Kế hoạch vật tư với hai cách gom (đã đúng cấu trúc, không đổi FE routing).
- **Bỏ phép tính `tồn/tổng cần` ở FE**: `VatTuKeHoachView.tsx` (dòng tính `pct` ở L493, L772) và
  `GiuChoTheoLenhView.tsx` (`pctGiu` ở L432, L631, L856) — đổi sang đọc thẳng trạng thái/lượng
  BE trả (§2), FE chỉ format hiển thị, không tính tỷ lệ.
- Không thêm màn hay luồng mua mới.
- Mọi thay đổi nguồn, tự nhả hoặc nhập/xuất Kho phải đẩy SSE để badge và toast cập nhật ngay —
  **[MỚI]** module vật tư/kho hiện chưa có kênh SSE riêng. Tái dùng `EventHub`
  (`backend/app/realtime.py`) theo đúng pattern endpoint mẫu `routers/quotations.py:408-447`:
  thêm `GET /api/ke-hoach-vat-tu/events` (hoặc gộp vào kênh có sẵn nếu FE đã nhận qua `eventTick`
  chung — xác nhận lúc viết plan bằng cách đọc `KeHoachVatTuPage.tsx:32,36-37`). Bắn sự kiện khi:
  bật/tắt giữ, `nhat_them()` tự bù, ghi sổ nhập/xuất kho liên quan giữ chỗ, PMH đổi (lùi
  ngày/giảm/huỷ).

## 5. Kiểm thử và nghiệm thu

- Cùng vật tư ở nhiều công đoạn không bị trừ `đã cấp` nhiều lần.
- Vật tư riêng của LSX trong bài ghép không bị quy nhầm sang bài.
- Giữ nguồn đang về không làm giảm tồn kho hiện tại và không cho LSX dùng tồn đã giữ của người
  khác.
- Hai thao tác giữ đồng thời không giữ vượt tồn hoặc vượt dòng PMH (kiểm tra khoá thứ tự ổn
  định ở §3.6 thực sự chặn race).
- Đơn mới duyệt không được giữ; đơn đã đặt có ngày được giữ; đơn không ngày báo chưa đủ điều
  kiện.
- PMH giao một phần, giảm, lùi ngày, hủy và giao vượt đều đối soát đúng.
- Tạo yêu cầu nhập (`StockRequest`) chưa làm tăng tồn; chỉ ghi sổ phiếu nhập mới tăng tồn và
  chuyển nguồn giữ (§3.3 bước 3).
- Xuất một phần, nhập nhiều đợt, điều chỉnh/hoàn trả không đếm đôi tồn và giữ chỗ.
- Hàng về muộn chặn ngày lịch nhưng không tạo đề nghị mua trùng.
- Sửa LSX/bài ghép đang giữ bị chặn cho tới khi nhả — CẢ hai kịch bản ở §3.6 (sửa số lượng công
  đoạn LẪN ghép/tách bài/đổi routing/huỷ LSX).
- Migration dữ liệu cũ không tạo giữ vượt nguồn (chạy `nhat_them()` sau khi xoá giữ chỗ demo cũ,
  kiểm tổng giữ ≤ tổng đang về thật).
- Kiểm tra rollback khi lỗi giữa ghi sổ Kho và cập nhật giữ chỗ.
- Chạy xác minh chuẩn `./init.ps1`, restart uvicorn sau thay đổi route/schema; kiểm luồng thật
  bằng browser (bật giữ → tạo đợt giao → bấm Nhập kho → Kho ghi sổ → xem giữ chỗ tự chuyển
  kho/tự bù) và soi UI bằng StyleSeed trước khi kết luận hoàn tất.

## Mặc định đã khóa

- Giữ chỗ hiện tại là nguồn cam kết vận hành.
- Không tự ưu tiên cờ gấp và không tự cướp chỗ cũ.
- Không tự hết hạn giữ chỗ.
- Thay đổi nhu cầu phải nhả trước — áp dụng CẢ sửa số lượng công đoạn LẪN ghép/tách bài, đổi
  routing, huỷ LSX (chốt 30/08/2026, xem §3.6).
- Cam kết cũ được bảo vệ; khi nguồn giảm, chỗ mới hơn bị nhả trước.

## Quyết định đã chốt trong buổi bàn (30/08/2026)

1. **Chặn sửa nhu cầu khi đang giữ chỗ**: chặn CẢ hai kịch bản — (a) sửa số lượng/quy cách ngay
   trên công đoạn của chủ thể đang giữ, VÀ (b) ghép/tách bài ghép, đổi routing, huỷ LSX khi chủ
   thể liên quan đang giữ. Ban đầu cân nhắc chỉ chặn (a) vì (b) là thao tác người trình bài làm
   thường xuyên khi thử phương án — nhưng chủ dự án chọn chặn cả hai để ưu tiên an toàn số liệu
   hơn tiện lợi thao tác.
2. **Nút "Nhập kho" trên đợt giao PMH**: tái dùng nguyên `StockRequest(REQ_NHAP)` đã có, chỉ
   thêm liên kết nguồn gốc (`purchase_delivery_id`) — không đẻ loại yêu cầu nhập riêng. **Cập
   nhật khi rà code viết plan: hướng này ĐÃ ĐƯỢC CÀI ĐẶT ĐẦY ĐỦ từ trước** (mg 0189 trở đi, cả
   backend lẫn FE) — quyết định ở đây hoá ra chỉ là XÁC NHẬN giữ nguyên thiết kế cũ, không phải
   việc mới. Việc thật còn thiếu đã thu hẹp về đúng bước "chuyển giữ chỗ dang_ve→kho khi ghi sổ
   nhập" — xem §3.3.
3. **Backfill giữ chỗ `dang_ve` cũ**: không viết thuật toán khớp ngược chính xác theo spec gốc.
   Vì dữ liệu hiện có toàn bộ là demo dev (chưa có prod thật), migration chỉ cần xoá giữ chỗ cũ
   rồi để `nhat_them()` dựng lại từ đầu theo cột mới.
