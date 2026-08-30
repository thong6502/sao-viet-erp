# Spec — Đề nghị cấp vật tư theo công đoạn

> Biên bản chốt của chủ dự án ngày 31/08/2026. Thay thế Task 16–22 (Phần B) của
> `docs/superpowers/plans/2026-08-30-ke-hoach-vat-tu.md` — phần đó dựng theo mô hình cũ (nối kho
> ở MỨC DÒNG, hạ `sl_duyet` khi điều chỉnh) và **không còn hiệu lực**.
> Plan thi công: `docs/superpowers/plans/2026-08-31-de-nghi-cap-vat-tu-cong-doan.md`.

## 1. Mục tiêu và phạm vi

Tổ trưởng đứng tại công đoạn của mình, thấy vật tư **kế hoạch** đã tính sẵn, sửa số cho khớp
thực tế rồi gửi thẳng sang kho. Không màn hình mới, không bước duyệt, không trạng thái
"Đã soạn xong", không báo cáo tổng hợp. Gộp vào **khối Vật tư sẵn có** của drawer công đoạn.

**Không bao giờ chặn bắt đầu / kết thúc công đoạn vì lý do vật tư.**

## 2. Mô hình dữ liệu

### 2.1 `san_xuat_vat_tu_de_nghi` (bảng mới)

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| `id` | int PK | |
| `cong_viec_id` | FK `san_xuat_cong_viec.id` | |
| `lan_so` | int | 1, 2, 3… |
| `loai` | str | `lan_dau` \| `bo_sung` |
| `can_luc` | datetime | giờ cần thật (kho `ngay_can` chỉ có DATE) |
| `stock_request_id` | int, null | null khi mọi dòng = 0 |
| `created_by_id`, `updated_by_id` | FK users | |
| `created_at`, `updated_at` | datetime | |

UNIQUE `(cong_viec_id, lan_so)`. UNIQUE `stock_request_id` khi có giá trị.
Không lịch sử từng lần sửa, không version nghiệp vụ.

### 2.2 `san_xuat_vat_tu_de_nghi_dong` (bảng mới)

`de_nghi_id`, `hang_loai`, `hang_id`, `dvt`, `dvt_goc`, `sl_ke_hoach`, `sl_ke_hoach_goc`,
`sl_yeu_cau`, `sl_yeu_cau_goc`, `ly_do_chenh_lech`. UNIQUE `(de_nghi_id, hang_loai, hang_id)`.

- **Lần đầu lưu MỌI vật tư kế hoạch**, kể cả dòng xin 0 — để đối chiếu về sau đọc được
  "kế hoạch có, tổ không lấy".
- Vật tư ngoài kế hoạch: `sl_ke_hoach = 0`.
- Lần bổ sung chỉ lưu dòng của chính nó, nhưng vẫn mang `sl_ke_hoach` gốc để màn đối chiếu so được.

### 2.3 `stock_request_lines.sl_chot_thuc_xuat` (cột mới, null)

Mục tiêu hiệu lực = `sl_chot_thuc_xuat` nếu có, không thì `sl_duyet`.
`còn lại = max(mục tiêu − sl_da_ung, 0)`.

| Tình huống | `sl_de_nghi` | `sl_duyet` | `sl_da_ung` | `sl_chot_thuc_xuat` | `sl_con_lai` | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| Xin 100, xuất 100, điều chỉnh còn 70 | 100 | 100 | 70 | **70** | 0 | Hoàn tất |
| Xin 100, kho mới xuất 70, không điều chỉnh | 100 | 100 | 70 | null | 30 | Cấp một phần |

Migration `0246_sx_vat_tu_de_nghi`: hai bảng + cột mới; hàng cũ giữ `sl_chot_thuc_xuat = null`.
Cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test bắt buộc).

## 3. Nguồn kế hoạch và quy đổi

Tách một phương thức CÔNG KHAI từ `KeHoachVatTuService`, tên `nhu_cau_cua_cong_viec`, nhận một
`SanXuatCongViec`.

Bắt buộc:

- **Không** gọi thẳng `_gom_nhu_cau`, **không** viết lại MRP.
- **Không** dựa vào `SanXuatCongViec.vat_tu_json` — snapshot đó không phủ hết phần giấy.
- Giải theo `lsx_id` / `bai_ghep_id`, neo theo `lsx_cong_doan_id` / `bai_ghep_cong_doan_id`.
- Giấy lấy ở **bước đầu tiên thật sự tiêu thụ giấy** (`_buoc_dau_dong_giay`).
- Hỗ trợ công đoạn bài ghép.
- Gộp trùng theo `(hang_loai, hang_id)` **sau khi** quy về đơn vị gốc.
- Trả cả đơn vị kế hoạch quen thuộc lẫn số theo đơn vị gốc.

BE **luôn quy đổi lại** số client gửi lên bằng engine đơn vị sẵn có. Không tin số của client.

## 4. Luật lý do chênh lệch

| Ca | Lý do |
| --- | --- |
| Khớp kế hoạch sau quy đổi | không cần |
| Tăng / giảm / về 0 một vật tư có trong kế hoạch | **bắt buộc** |
| Vật tư ngoài kế hoạch, số > 0 | **bắt buộc** |
| Mọi dòng khác 0 của lần bổ sung | **bắt buộc** |
| Dòng ngoài kế hoạch = 0 | vô nghĩa — không lưu |

So sánh bằng **số theo đơn vị gốc**.

## 5. Service và luồng đồng bộ kho

Service mới `services/san_xuat/vat_tu_de_nghi.py` + repository riêng.

### 5.1 Tạo

1. Khoá công việc.
2. Kiểm người gọi đang là **tổ trưởng đúng tổ** của công đoạn.
3. Kiểm chưa có đề nghị nào còn sửa được.
4. Lấy kế hoạch từ engine.
5. Chuẩn hoá / gộp trùng / kiểm lý do.
6. Lưu bản đối chiếu sản xuất ĐẦY ĐỦ (kể cả dòng 0).
7. Nếu có dòng dương → gọi `StockRequestService` tạo yêu cầu `XUAT` ở trạng thái `approved`,
   `bo_phan_id` = tổ của công đoạn, `nguoi_tao_id` = tổ trưởng đang thao tác,
   `ngay_can = can_luc.date()`, mỗi dòng mang `lsx_id`/`bai_ghep_id`, **chỉ dòng > 0**.
8. Mọi dòng = 0 → **không tạo yêu cầu kho**.

### 5.2 Sửa (đồng bộ trước khi có phiếu)

Thêm phương thức đồng bộ **dành riêng cho sản xuất** vào `StockRequestService` — KHÔNG dùng API
update thường vì yêu cầu đã ở `approved` (`_require_editable` sẽ chặn).

1. Khoá yêu cầu.
2. Kiểm **không có `StockVoucher` nào** — kể cả nháp, kể cả đã huỷ.
3. Thay toàn bộ dòng bằng dữ liệu dương mới nhất.
4. `sl_de_nghi` và `sl_duyet` = số mới.
5. Giữ nguyên mã và id.
6. Bắn lại SSE kho.

### 5.3 Sửa hết về 0

Giữ bản ghi sản xuất; xoá dòng của yêu cầu kho; chuyển yêu cầu sang `cancelled` với ghi chú hệ
thống **"Tổ xác nhận không cần cấp"**; **giữ link và mã**.
Tổ nhập lại số dương khi chưa có phiếu nào → **khôi phục chính yêu cầu đó** về `approved` và dựng
lại dòng. Không bao giờ đẻ mã mới.

### 5.4 Khoá

Yêu cầu bị khoá ngay khi yêu cầu kho liên kết **có bất kỳ phiếu nào**.
`PUT` phải kiểm lại **trong transaction** và trả lỗi nghiệp vụ mà không sửa gì.
`POST` kế tiếp tạo `lan_so + 1`, `loai = bo_sung`.
Mỗi công đoạn tối đa **một** đề nghị còn sửa được. Tổng cộng dồn qua mọi lần; không ghi đè lần cũ.

### 5.5 `StockVoucherService.dieu_chinh_xuat`

Sau khi giảm dòng phiếu + `sl_goc`, trả phần dư về đúng lô, giảm `StockRequestLine.sl_da_ung`:
**tính lại tổng đã xuất hiện tại của từng dòng yêu cầu bị ảnh hưởng và gán vào
`sl_chot_thuc_xuat`**, rồi chạy lại `refresh_fulfillment`. Giữ nguyên nhật ký (ai, lúc nào,
trước → sau, lý do).
Chỉ `kho:create` được điều chỉnh. Không cần tổ trưởng xác nhận. Không phiếu trả.

## 6. API

```
POST /api/san-xuat/work-items/{cong_viec_id}/material-requests
PUT  /api/san-xuat/work-items/{cong_viec_id}/material-requests/{de_nghi_id}
```

Payload: `{can_luc, lines: [{hang_loai, hang_id, dvt, sl_yeu_cau, ly_do_chenh_lech}]}`.
`de_nghi_id` là id **đề nghị sản xuất**, không phải id yêu cầu kho.

Router gác `san_xuat:assign_work`; service đòi thêm **tổ trưởng đúng tổ**; **không** đòi
`kho:request`. Người lập kế hoạch, quản lý ngoài tổ, tổ trưởng tổ khác → chặn hết.

`WorkItemChiTietOut` giữ nguyên `vat_tu` trong giai đoạn chuyển tiếp và thêm `vat_tu_cap`:
`{ke_hoach, cac_de_nghi, doi_chieu, de_nghi_co_the_sua_id, co_the_tao_bo_sung}`.
Mỗi dòng đối chiếu trả: mặt hàng + đơn vị, kế hoạch, tổng đã yêu cầu, thực xuất chốt, lệch
kế-hoạch↔yêu-cầu, lệch yêu-cầu↔thực-tế, lý do từng lần, người tạo / người sửa cuối / mốc giờ.
**Thực xuất tính từ dòng phiếu `posted` hiện tại sau điều chỉnh, ưu tiên `sl_goc`.**

Thay `voucher_xuat_cua_lsx` bằng truy vấn **theo công việc**: công đoạn có đề nghị sản xuất → chỉ
lấy phiếu của các `stock_request_id` liên kết; chưa từng có → lùi về `lsx_id` và **đánh dấu dữ
liệu cũ**; không trộn đường lùi vào công đoạn đã có link mới; bài ghép dùng link, không dùng
đường lùi. Xác nhận nhận vật tư vẫn khoá theo `voucher_id`.

API kho: giữ nguyên payload `POST /api/kho/phieu/{voucher_id}/dieu-chinh-xuat`; mở rộng output
`StockRequestLineOut.sl_chot_thuc_xuat`, `StockRequestLineOut.sl_con_lai`,
`StockRequestOut.can_luc`, `StockRequestOut.san_xuat_cong_viec_id`,
`StockRequestOut.san_xuat_cong_doan_ten` (null với yêu cầu kho thường).

## 7. Frontend

Mở rộng `ThsxExecPanels.tsx`, **không** trang mới. Khối Vật tư **luôn hiện**.
Cột: `Vật tư | Kế hoạch | Đã yêu cầu | Kho thực xuất | Chênh lệch | Lý do`, kèm lịch sử các lần
(mã kho, giờ cần, người tạo/sửa, trạng thái kho).

Nút: chưa có lần nào → **Yêu cầu cấp vật tư**; đang có lần sửa được → **Sửa đề nghị**; lần cuối đã
có phiếu → **Yêu cầu bổ sung**; phiếu đã ghi sổ chưa xác nhận → giữ **Xác nhận nhận**.

Form nằm trong drawer, điền sẵn kế hoạch + `du_kien_bat_dau`, cho sửa giờ cần, cho tăng/giảm/về 0,
cho thêm mặt hàng qua `MaterialCombobox` + API đơn vị sẵn có (hàng ngoài kế hoạch mặc định đơn vị
gốc danh mục), chỉ hiện ô lý do khi dòng lần đầu lệch, luôn hiện và bắt buộc lý do cho dòng bổ
sung khác 0. FE cảnh báo sớm, **BE quyết đúng/sai**.

`KhoYeuCauPage.tsx`: hiện tổ yêu cầu, tên công đoạn, giờ cần chính xác; tự nạp lại qua SSE;
**không** hiện lý do lệch kế hoạch; không nút duyệt, không "Đã soạn xong". Yêu cầu 100 đã điều
chỉnh còn 70 hiển thị **"thực xuất 70 / yêu cầu 100"**, trạng thái Hoàn tất — không phải
"còn thiếu 30".

Realtime: giữ `stock_request_pending_changed` cho lúc tạo và **bắn lại** khi đồng bộ trước phiếu;
thao tác phía sản xuất bắn `san_xuat_vat_tu_de_nghi_changed`; thêm cả hai vào union kiểu FE;
không trung tâm thông báo mới.

UI làm **hai lượt**: một agent thiết kế khảo sát khối Vật tư hiện tại và chốt bố cục + form,
rồi một agent khác cài đặt. Sau đó kiểm luồng thật trên dev-browser và chạy styleseed-design-review.

## 8. Giả định đã khoá

- Không lấn sang bàn giao, KCS, ghi nhận lỗi, chia sản lượng.
- Người lập kế hoạch không tham gia.
- Tổ trưởng chịu trách nhiệm duy nhất về số đã yêu cầu.
- Kho không duyệt, không xử lý lý do lệch.
- Không bao giờ chặn bắt đầu/kết thúc công đoạn vì vật tư.
- Không phiếu trả riêng. Không lịch sử từng lần sửa. Không báo cáo tổng hợp.
- **Không commit hoặc push nếu chưa được yêu cầu.**
