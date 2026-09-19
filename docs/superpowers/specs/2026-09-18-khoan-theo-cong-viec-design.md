# Khoán theo CÔNG VIỆC · Định mức vật tư về công đoạn · Gỡ đầu việc và kíp — Thiết kế

**Ngày chốt:** 18/09/2026
**Phạm vi:** Danh mục Công đoạn · Danh mục Công việc khoán · Lệnh SX (routing) · Bài ghép ·
Thực hiện SX (bàn tổ, ghi mẻ) · Xếp lịch.

---

## 1. Quyết định gốc của chủ xưởng

> *"Bỏ đầu việc định mức và tổ cho công đoạn. Thêm tab vật tư để chọn nhiều vật tư và thiết công
> thức định mức cho từng vật tư. Ở module công việc khoán thêm tab công thức khoán."*
>
> *"Bỏ công việc chi tiết và kíp dưới lsx — vật tư được bung theo công đoạn — tổ thì không có thời
> gian (hoặc để nhập tay thời gian kế hoạch)."*
>
> *"Dưới sản xuất sẽ xuất hiện tất cả các công việc khoán ở tổ đó, chỉ chọn được một trong đó, nhập
> số lượng cho công việc đó — nó là ghi mẻ đó nhưng cho công việc chứ không phải công đoạn nữa.
> Phải hiển thị cả đơn giá, đơn vị tính, ghi chú và danh sách việc phát sinh của việc đó. Có thể
> chọn một hoặc nhiều việc phát sinh rồi nhập số lượng."*
>
> *"Việc phát sinh như lên khuôn không cộng vào sản lượng."*
>
> *"Về phần tính giá khoán thì để sau — ví dụ cán màng thì tính đơn giá / m², còn số lượng này là
> khác."*
>
> *"Xoá v2 và đổi tên v3 thành `xep_lich`."*

**Ranh giới mới, một câu:** *công đoạn* trả lời **làm gì, tốn vật tư gì**; *công việc khoán* trả
lời **thợ làm việc gì, tính tiền ra sao**; *mẻ* ghi **làm được bao nhiêu** — ba thứ rời nhau, không
còn bảng lai ghép `cong_doan_dau_viec` đứng giữa.

## 2. Ba hiểu lầm phải nói trước, vì cả bản này treo lên chúng

1. **Số lượng ghi mẻ KHÔNG phải thừa số của đơn giá.** Nó là sản lượng làm được (tờ, con), y hệt
   hôm nay. Tiền khoán tính sau, ở tầng lương, bằng `cong_thuc_khoan` của chính công việc đó —
   cán màng đổi sản lượng + quy cách lệnh ra m² rồi mới nhân đ/m². Số của mẻ là **đầu vào** của
   công thức.
2. **Đơn giá bày ở bàn tổ chỉ để nhận diện việc.** Không có ô thành tiền, không có phép nhân nào ở
   màn sản xuất. Nguyên tắc 1 của bản 11/09/2026 vẫn đứng nguyên, bản này **không** đảo ngược nó.
3. **Việc phát sinh không bao giờ là sản lượng.** "Lên khuôn 1 lần" chỉ ra tiền; nó không cộng
   tiến độ, không đẩy sang KCS, không vào bàn giao, không vào chia sản lượng theo người.

Hệ quả sung sướng: **đơn vị của mẻ giữ nguyên `don_vi_ra` của bước**, nên tiến độ · KCS · bàn giao ·
đóng nhóm đủ · nhập kho thành phẩm **không phải sửa một dòng nào**.

## 3. Đo trước khi gỡ — dữ liệu dev không có xung đột

Đếm trên `svn_erp_trong` ngày 18/09/2026 (chỉ đọc):

| Kiểm | Kết quả | Nghĩa |
|---|---|---|
| `cong_doan_dau_viec` | 27 dòng | |
| công việc khoán khai ở >1 công đoạn | **0** | dồn `cong_thuc_khoan` lên `piece_rates` là 1-1, không mất công thức nào |
| cùng vật tư ở >1 đầu việc của một công đoạn, công thức khác nhau | **0** | backfill vật tư lên công đoạn là gộp sạch |
| công đoạn có >1 tổ phụ trách | **0** | `cong_doan_to` (mg `0312`, làm 18/09) chưa ai dùng, gỡ không mất gì |
| công việc khoán mỗi tổ | cao nhất 17, còn lại 1–6 | danh sách ở bàn tổ cần ô tìm khi dài |
| việc phát sinh đã khai | 1 dòng | |

## 4. Danh mục Công đoạn

### 4.1 Gỡ

| Bỏ | Ghi chú |
|---|---|
| bảng `cong_doan_dau_viec` | cùng mọi cột định mức: `nang_suat_nguoi_gio(_min/_max)`, `don_vi_nang_suat`, `so_nguoi_tieu_chuan`, `cong_thuc_khoan`, `cong_thuc_gio` |
| bảng `cong_doan_dau_viec_vat_tu` | nội dung chuyển lên `cong_doan_vat_tu` (§4.2) trước khi drop |
| bảng `cong_doan_to` + `CongDoan.department_ids` / `.to_mac_dinh_id` | |
| FE field `dau_viec_dinh_muc` + `fields/DinhMucDauViec.tsx` | |
| FE field `department_ids` ở `CFG_CONG_DOAN` + handler `setToPhuTrach` | `fields/ToMulti.tsx` **giữ lại** — Công việc khoán vẫn dùng |

`cong_thuc_gio` của đầu việc mất cùng bảng. Đây là đường tính thời lượng bước tổ — thay bằng §5.3.

### 4.2 Thêm: bảng `cong_doan_vat_tu` + tab **Vật tư**

```
cong_doan_vat_tu
  id                PK
  cong_doan_id      FK cong_doan.id  ON DELETE CASCADE
  vat_tu_id         soft-ref vat_tu_in_an.id   (như cong_doan_dau_viec_vat_tu hôm nay)
  thu_tu            int
  cong_thuc_luong   Text | NULL      — ra LƯỢNG theo ĐVT của vật tư
  UNIQUE (cong_doan_id, vat_tu_id)
```

Vẫn **không có cột số lượng chết** — lý do y nguyên bảng cũ: định mức tuỳ quy cách từng lệnh. Chưa
khai công thức thì bước lệnh **không bung** dòng đó kèm câu lý do, không đoán.

Chỉ nhận `vat_tu_in_an`. Giấy vẫn đi đường riêng (người lập lệnh chọn `hang_loai="giay"` ở bước) —
đưa giấy vào đây là đẻ nguồn thứ hai cho một số bình bài đã chốt.

FE: khai `tabsKhai` cho `CFG_CONG_DOAN`, tách group `"Vật tư"` ra tab riêng. Cơ chế đã có sẵn
([CatalogDrawer.tsx:579](../../frontend/src/pages/danh-muc/CatalogDrawer.tsx)), không phải dựng mới.
Bảng trong tab: Mã · Tên · ĐVT · Công thức định mức — bê nguyên hình bảng con đang nằm trong
`DinhMucDauViec.tsx:236-285`.

## 5. Danh mục Công việc khoán — tab **Công thức khoán**

Thêm `piece_rates.cong_thuc_khoan: Text | NULL`, bày thành tab formula riêng (dùng `nhanTab` như
`cong_doan.cong_thuc_gia` đang làm). Giá trị nó trả là **LƯỢNG theo ĐVT của đơn giá**, engine lương
mới nhân `unit_price`.

Đây là quay ngược mg `0274` (công thức từng dời từ `piece_rates` xuống `cong_doan_dau_viec`). Lý do
hồi đó — *"cùng đầu việc ở hai công đoạn đếm khác nhau"* — tan khi mỗi công việc khoán đã mang mã
riêng của xưởng, đã mã hoá sẵn khổ / số màu / số lớp. §3 đo được 0 xung đột, nên backfill 1-1.

Bộ biến của công thức: quy cách lệnh (dài, rộng, số màu…) **+ `sl` = số lượng của mẻ**. Không có
`sl` thì cán màng không ra m². Rà `services/bien_cong_thuc.py` để mở đúng biến này cho ngữ cảnh
lương, không mở bừa cả bộ.

Việc phát sinh **không** có công thức: tiền của nó = số lượng × `don_gia` thẳng.

## 6. Lệnh sản xuất

### 6.1 Gỡ khỏi bước

| Bảng | Cột bỏ |
|---|---|
| `lsx_cong_doan` | `khoan_json`, `so_nhan_cong_tieu_chuan` |
| `bai_ghep_cong_doan` | hai cột song sinh cùng tên |
| `san_xuat_cong_viec` | `khoan_json` (ảnh chụp lúc phát hành) |

Kéo theo ở backend: `lsx_service._khoan_mac_dinh` · `_khoan_thu` · `_dinh_muc_snapshot` ·
`_dau_viec_option_dicts` · khoá `khoan` của `xem_truoc_buoc`; endpoint `GET /api/lsx/{id}/dau-viec-options`;
`piece_work_service.khoan_snapshot` (xoá hàm); `board.py:997` (`dau_viec_ten`).
FE: section "Đầu việc thợ làm" và section kíp trong [LsxBuocDrawer.tsx](../../frontend/src/pages/LsxBuocDrawer.tsx),
bản song sinh trong `BaiGhepBuocChungForm.tsx`.

### 6.2 Vật tư bung theo CÔNG ĐOẠN

`_vat_tu_bung` đổi nguồn từ `dau_viec.vat_tus` sang `cong_doan.vat_tus`. Đây là **đơn giản hoá**,
không phải thêm việc: hôm nay hàm phải đợi bước đã chọn đầu việc mới bung được; sau đổi thì mọi
bước có `cong_doan_id` là bung ngay lúc tạo lệnh. MRP hưởng theo vì nó đọc `lsx_cong_doan_vat_tu`
chứ không đọc danh mục.

Cờ `tu_dong` giữ nguyên luật: máy chừa ra dòng người đã sửa.

### 6.3 Thời lượng bước TỔ — gõ tay

Thêm `lsx_cong_doan.thoi_luong_tay_phut: Numeric(10,2) | NULL` (và cột song sinh ở
`bai_ghep_cong_doan`). `thoi_luong_buoc` đổi nhánh bước tổ:

- có `thoi_luong_tay_phut` ⇒ dùng số đó (cộng `phat_sinh_phut` như cũ);
- trống ⇒ trả 0 **kèm câu cảnh báo "bước tổ chưa khai giờ kế hoạch"**, không bịa.

Bước MÁY và THUÊ NGOÀI **không đổi** — chúng đọc sống `may_thiet_bi.toc_do`, chưa bao giờ dính
`cong_doan_dau_viec`.

### 6.4 Tổ của bước — chọn tay

Cột `lsx_cong_doan.department_id` **giữ nguyên**. Chỉ đổi nguồn options ở
[LsxBuocDrawer.tsx:856](../../frontend/src/pages/LsxBuocDrawer.tsx): trước lọc theo danh sách tổ của
công đoạn, sau liệt kê **toàn bộ tổ sản xuất**, mặc định trống. Bỏ nhãn
*"(không còn phụ trách công đoạn)"* vì hết cơ sở so sánh.

Hình màn không đổi, chỉ đổi dữ liệu nạp vào select. Bước để trống tổ thì **không lên bàn tổ nào** —
cảnh báo ở màn Kế hoạch SX, không chặn phát hành.

## 7. Bàn tổ — ghi mẻ theo CÔNG VIỆC KHOÁN

### 7.1 Dữ liệu

```
san_xuat_batch           + piece_rate_id   soft-ref piece_rates.id, NULL trong giai đoạn chuyển

san_xuat_batch_phat_sinh   (bảng mới)
  id                PK
  batch_id          FK san_xuat_batch.id ON DELETE CASCADE
  viec_phat_sinh_id soft-ref cong_viec_khoan_phat_sinh.id
  so_luong          Numeric(18,3)
  created_at
  UNIQUE (batch_id, viec_phat_sinh_id)
```

**Không ghim giá, không ghim ĐVT** vào cả hai chỗ — cùng lý do bản 11/09: kế toán lương tra bảng
giá tại thời điểm tính lương. Ghim là dựng lại đúng cái bệnh đã chữa.

`tong` / `tot` / `hong` / `don_vi` của mẻ **giữ nguyên hoàn toàn**, kể cả ràng buộc `don_vi` phải
khớp `cv.don_vi_ra` ([san_luong.py:216](../../backend/app/services/san_xuat/san_luong.py)).

### 7.2 API

`BatchIn` thêm `piece_rate_id: int` và `phat_sinh: [{viec_phat_sinh_id, so_luong}]`.

Danh sách việc để chọn **nhúng thẳng vào `chi_tiet_cong_viec`** (một call, tổ đông nhất mới 17
việc): công việc khoán mà `piece_rates.department_ids` chứa `cv.department_id`, mỗi việc kèm `ten`,
`unit` + tên đơn vị, `unit_price`, `note`, và `viec_phat_sinh[]` (`ten`, `don_gia`, `don_vi`).

Luật chặn ở service: `piece_rate_id` phải thuộc đúng tổ của công việc; mỗi
`viec_phat_sinh_id` phải thuộc đúng `piece_rate_id` vừa chọn; `so_luong` > 0.

### 7.3 Phân bổ người

`_tinh_batch` **không đổi** — vẫn chia `batch.tot` theo phút chấm công hợp lệ. Việc phát sinh đứng
ngoài hẳn: *"lên khuôn 1 lần"* chia đều cho kíp 5 người thành 0,2 lần/người là số vô nghĩa. Nó nằm
ở cấp mẻ, để màn kế toán lương xử.

### 7.4 Màn

`BatchForm` ([ThsxExecPanels.tsx:297](../../frontend/src/pages/ThsxExecPanels.tsx)) thêm hai khối,
đặt **trên** các ô số lượng đang có:

- **Chọn việc**: danh sách thẻ chọn-một, mỗi thẻ hiện tên việc · đơn giá · ĐVT · ghi chú. Có ô tìm
  khi tổ có trên 8 việc. Nút to, chữ lớn — đây là màn xưởng.
- **Việc phát sinh**: hiện sau khi đã chọn việc, danh sách tick-nhiều, mỗi dòng tên · đơn giá · ĐVT
  và một ô số lượng. Không tick thì không gửi gì.

Không có ô thành tiền ở bất kỳ đâu trong hai khối này.

## 8. Xếp lịch — còn đúng MỘT module

Trước 18/09/2026: menu chỉ còn một mục nhãn "Xếp lịch", nhưng bên trong là `xep_lich_3`;
`xep_lich_2` bị ẩn bằng cờ `XEP_LICH_2_ENABLED` mà code vẫn nằm nguyên; `xep_lich` (v1) đã xoá
19/08/2026.

**ĐÃ LÀM 18/09/2026** (tách khỏi phần khoán, chạy trước):

- **Xoá trọn v2** — `routers/xep_lich_2.py`, `repositories/xep_lich_2_repo.py`,
  `schemas/xep_lich_2.py`, các module MÀN của `services/xep_lich_2/`, `XepLich2Page.tsx`,
  `Xl2Gantt.tsx`, `xl2Shared.tsx`, `xep-lich-2.css`, cờ `XEP_LICH_2_ENABLED`, mục nav, khoá quyền
  `xep_lich_2` trong `seed.py` + ma trận, và mọi bài test của v2.
- **Giữ lại 4 module LUẬT của v2** — `constraint`, `phan_doan`, `release`, `thuc_te` chuyển vào
  `services/xep_lich/`. Chúng KHÔNG chết: `services/san_xuat/release.py`,
  `xep_lich_van_de_service.py` và bàn cấp lệnh đang gọi. (`phan_doan.tach`/`gop` mất người gọi
  cùng router v2 — giữ vì `cac_phan_doan`/`ty_le_trong_cum` còn dùng, xem tombstone trong
  `test_xep_lich_phan_doan.py`.)
- **Đổi tên v3 → `xep_lich`** — router (`/api/xep-lich`), `services/xep_lich_3/` →
  `services/xep_lich/`, lớp `XepLich3*` → `XepLichLenh*` (không lấy `XepLich*` vì
  `xep_lich_service.py` đã chiếm), `XepLich3Page.tsx` → `XepLichPage.tsx`, `Xl3*` → `Xl*`,
  route id `xep-lich-3` → `xep-lich`, lớp CSS `xl3-` → `xl-`, sự kiện SSE gộp về
  `xep_lich_changed`, khoá quyền `xep_lich_3` → `xep_lich` (mg `0314`).

**CÒN NỢ** — thuộc phần khoán, làm cùng §2:

- **Cắt đường kíp**: `_so_nguoi_dong` ([xep_lich_service.py:926](../../backend/app/services/xep_lich_service.py)),
  phép `gio *= so_nguoi` ở `:857`, và ba chỗ trong `services/xep_lich/service.py` (`:313` qua
  `thoi_luong_buoc`, `:472`, `:1068`).
- **Rà nốt `services/xep_lich_service.py`**: phần chỉ phục vụ màn v2 chưa gỡ — chưa gỡ vì bàn cấp
  lệnh và `moc.py` còn đi qua đó, phải tách lúc cắt kíp mới an toàn.

## 9. Đổi dữ liệu

Số hiệu tiếp theo `0315`. `0314_gop_xep_lich` **đã viết và chạy** 18/09/2026, tách khỏi bản này —
chủ dự án chốt gỡ đánh số xếp lịch trước, không đợi khoán:

| Migration | Việc |
|---|---|
| `0314_gop_xep_lich` ✔ | chép quyền `xep_lich_3` → `xep_lich` cho mọi vai; xoá khoá `xep_lich_2` và `xep_lich_3` |

Còn lại là của bản này:

| Migration | Việc |
|---|---|
| `0315_cong_doan_vat_tu` | tạo `cong_doan_vat_tu`; **backfill** từ `cong_doan_dau_viec_vat_tu` theo `cong_doan_id` của đầu việc cha, trùng `(cong_doan_id, vat_tu_id)` thì giữ dòng đầu |
| `0316_cong_thuc_khoan_ve_cong_viec_khoan` | thêm `piece_rates.cong_thuc_khoan`; **backfill** từ `cong_doan_dau_viec.cong_thuc_khoan` (1-1, §3) |
| `0317_bo_dau_viec_va_to_cua_cong_doan` | drop `cong_doan_dau_viec_vat_tu`, `cong_doan_dau_viec`, `cong_doan_to` |
| `0318_bo_khoan_va_kip_khoi_buoc` | drop `khoan_json` + `so_nhan_cong_tieu_chuan` ở `lsx_cong_doan`, `bai_ghep_cong_doan`, `san_xuat_cong_viec` |
| `0319_gio_ke_hoach_tay` | thêm `thoi_luong_tay_phut` ở `lsx_cong_doan` + `bai_ghep_cong_doan` |
| `0320_me_theo_cong_viec_khoan` | thêm `san_xuat_batch.piece_rate_id`; tạo `san_xuat_batch_phat_sinh` |

Backfill viết **raw SQL đích danh cột**, không ORM full-select — ORM kéo cột do migration sau thêm
sẽ vỡ trên DB trung gian.

`0315` và `0316` phải chạy **trước** `0317`, nếu không mất dữ liệu.

`docs/DB_SCHEMA.md` sửa **cùng lúc** — guard test bắt.

**Dữ liệu mất:** năng suất người-giờ, đơn vị năng suất, kíp chuẩn, `cong_thuc_gio` của 27 dòng định
mức đầu việc; danh sách tổ phụ trách của công đoạn; các ảnh chụp `khoan_json` trên lệnh đã phát
hành. Không khôi phục được sau khi migration chạy. Chấp nhận được vì prod đang DB trắng và `seed_luong_ban_sx.py`
dựng lại được phần danh mục.

## 10. Hệ quả phải nói trước

- **Ngày kết thúc dự kiến của lệnh sẽ hụt** nếu còn bước tổ chưa gõ giờ kế hoạch. Màn Xếp lịch
  cảnh báo chứ không chặn — nhưng nghĩa là ngày hẹn khách có lúc không tự ra được nữa.
- **Detector "vượt quân số tổ" trong Xếp lịch tắt** cùng với kíp. Ghi lại thành nợ, không cố cứu
  bằng một con số bịa.
- **Luật "bắt đầu việc phải nêu lý do lệch số người"** (`san_xuat_phien_chay.ly_do_so_nguoi`) mất
  mốc so sánh ⇒ gỡ ràng buộc, giữ cột để người vẫn ghi chú được.
- **Dấu trang cũ `/xep-lich-3` hỏng.**
- **`payroll_lines.khoan` vẫn = 0** cho tới khi dựng màn "Khoán theo kỳ". Khác trước ở chỗ: sau bản
  này màn đó đã có **đủ** đầu vào — `piece_rate_id` + sản lượng theo người + `cong_thuc_khoan` +
  `unit_price` + việc phát sinh.
- **Chặn xoá công việc khoán** đổi nguồn: hôm nay dựa `CongDoanDauViec.piece_rate_id` và
  `khoan_json.rate_id`; sau bản này dựa `san_xuat_batch.piece_rate_id`.

## 11. Không làm (bản này)

- Màn **"Khoán theo kỳ"** của kế toán lương — nơi đổi sản lượng + việc phát sinh ra tiền. Pha sau.
- **Công thức cho việc phát sinh** — nó là số lượng × đơn giá thẳng.
- **Chia việc phát sinh theo từng người** — xem §7.3.
- **Giấy trong tab Vật tư của công đoạn** — xem §4.2.
- **Gỡ cột `cong_doan.nang_suat`** và các cột legacy khác của công đoạn — không dính bản này.

## 12. Kiểm thử

**Backend** (pytest nhắm file): `test_cong_doan.py` · `test_cong_doan_bon_cong_thuc_http.py` ·
`test_cong_viec_khoan.py` · `test_khoan_dau_viec.py` · `test_lsx_service.py` · `test_khsx_ui_contract.py` ·
`test_bai_ghep_service.py` · `test_danh_muc_tham_chieu.py` · `test_import_excel.py` ·
`test_san_xuat_san_luong.py` · `test_san_xuat_board.py` · `test_san_xuat_phan_bo.py` ·
`test_db_schema_doc.py` + bài mới cho từng migration `0315`–`0320`.
Xoá: `test_migration_0270_gop_dinh_muc_nhan_luc.py` · `test_migration_0272_0274_cong_thuc_ve_cong_doan.py` ·
`test_migration_0281_go_so_nguoi_bo_tri.py` · mọi bài của `xep_lich_2`.

**Frontend:** `npx tsc --noEmit` + bài mới cho khối chọn việc khoán và khối việc phát sinh trong
`BatchForm` (phải **không** có chữ "thành tiền").

**Luồng UI thật** — bắt buộc trước khi báo xong, không thay bất kỳ bước nào bằng curl:
khai một công đoạn với 2 vật tư + công thức định mức → khai công thức khoán cho một công việc khoán
→ tạo lệnh, thấy vật tư tự bung theo công đoạn, gõ giờ kế hoạch cho bước tổ, chọn tổ → phát hành →
mở bàn tổ → chọn công việc khoán (thấy đơn giá · ĐVT · ghi chú) → nhập sản lượng → tick 2 việc phát
sinh, nhập số lượng → lưu → mở lại mẻ thấy đủ, và tiến độ chỉ cộng phần sản lượng, **không** cộng
việc phát sinh.
