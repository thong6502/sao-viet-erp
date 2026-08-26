# PRD — Thu mua đợt 2: lịch sử trạng thái · gộp trường · Excel · thông báo

**Ngày chốt:** 07/08/2026 · **Phân hệ:** `thu_mua` (chạm nhẹ `ke_toan`)
**Nguồn:** danh sách đầu việc của chủ 07/08/2026, sau khi đã hỏi–đáp làm rõ.

> Nối tiếp `prd-mua-hang-cong-no.md` (đợt 1: đợt giao · phiếu chi · công nợ). Đợt này KHÔNG đụng
> công thức tiền.

---

## 0. Bảy đầu việc → năm việc phải làm

| # | Chủ yêu cầu | Kết luận |
|---|---|---|
| 1 | Gộp *Mục đích* và *Ghi chú* | ✅ LÀM — §1 |
| 2 | Lịch sử trạng thái của phiếu | ✅ LÀM — §2 |
| 3 | Import/Export Excel vật tư NCC | ✅ LÀM — §3 |
| 4 | Tách quyền "Đơn mua hàng" ở Kế toán | ❌ **KHÔNG LÀM** — chủ chỉ hỏi chỗ cấp quyền, đã trả lời (§6) |
| 5 | Badge thông báo | ✅ LÀM — §4 |
| 6 | *Giao một phần* không rõ bao nhiêu | ✅ LÀM — §5 |
| 7 | Quyền xem tất cả phiếu của mọi nhân viên | ❌ **KHÔNG LÀM** — đã có sẵn, chỉ cần đổi scope vai (§6) |

---

## 1. Gộp *Mục đích* + *Ghi chú*

### Vấn đề thật, không chỉ là gộp ô

`note` của cả `department_purchase_requests` lẫn `purchase_requests` **đang bị dùng cho hai việc**:
ghi chú của người lập, VÀ lý do từ chối/huỷ. `cancel()` chạy `row.note = (reason or "").strip() or
row.note` — **ghi đè mất ghi chú gốc**. Gộp ô mà không gỡ chuyện này là gộp luôn cả lỗi.

### Cách làm

| Việc | Chi tiết |
|---|---|
| Thêm cột `content` (Text) | Ô GỘP, nhãn **"Nội dung / mục đích"**, bắt buộc |
| Thêm cột `reject_reason` (Text NULL) | Lý do **từ chối · huỷ · đóng đơn · mở lại đơn** |
| `purpose` · `note` | Thành **DORMANT** — giữ cột (không có Alembic), thôi đọc thôi ghi |
| Migration | `content = purpose || (note ? ' — ' + note : '')` cho mọi hàng cũ. Không mất chữ nào |

Giao diện: một ô textarea thay hai ô. Lý do từ chối/huỷ hiện thành **dòng đỏ riêng** trên phiếu,
không lẫn vào nội dung.

> **Vì sao tách `reject_reason` chứ không nối vào cuối `content`:** nối thì không lọc được *"những
> đơn bị từ chối vì lý do gì"*, và người lập sửa nội dung là xoá luôn lý do người duyệt đã ghi.

### Đã làm — và hai chỗ suýt hụt (07/08/2026)

**Trần 500 ký tự.** `purpose` là `String(500)`, `content` là `Text`. Schema vào vẫn bắt `purpose`
non-empty ⇒ ô gộp (tối đa 4000) gõ quá 500 là ăn 422 mà người dùng không hiểu vì sao. Đã nới
`purpose` thành optional ở `DepartmentPurchaseRequestIn` · `PurchaseRequestIn` ·
`PurchaseRequestBatchIn`; chỗ chặn rỗng vẫn nằm ở service (thông báo tiếng Việt rõ hơn 422 của
pydantic).

**`content` của PHIẾU MUA không hề được ghi.** `PurchaseRequestRepository._build` và `update` nhận
tham số `content` nhưng quên gán vào row ⇒ cột luôn NULL, màn hình rơi về `content or purpose` nên
*trông vẫn đúng* — chỉ cụt ở ký tự 500. Không có test nào bắt được vì mọi nội dung trong test đều
ngắn. Đã gán ở cả hai đường, và thêm test nội dung ~960 ký tự đi trọn vòng tạo YCMH → tạo PMH.

**Nội dung phiếu chi** có trần 500 bên kế toán ⇒ chỗ tự điền "Thanh toán PMH-xxx - <nội dung>" phải
`slice(0, 500)`, không thì đơn có mô tả dài là bấm *Lập phiếu chi* không được.

---

## 2. ⭐ Lịch sử trạng thái

### Bảng MỚI `purchase_status_history` — dùng chung YCMH + PMH

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int PK | |
| `doc_type` | String(8), **IX** | `ycmh` \| `pmh` |
| `doc_id` | int, **IX** | id của YCMH hoặc PMH. **Soft ref** — hai bảng khác nhau nên không FK được |
| `from_status` | String(24) NULL | NULL = dòng đầu tiên (lúc tạo) |
| `to_status` | String(24) | |
| `changed_by_user_id` | FK `users` SET NULL | **NULL = MÁY tự suy** |
| `source` | String(8) | `nguoi` \| `may` |
| `reason` | Text NULL | Lý do từ chối/huỷ/đóng đơn/mở lại |
| `created_at` | DateTime(tz), **IX** | |

INDEX `(doc_type, doc_id, id)` — màn chi tiết luôn hỏi theo đúng bộ này.

### Vì sao bảng riêng, không dùng `audit_logs`

`audit_logs.detail` là **chữ tự do** (`"PMH-x — lý do y"`). Suy ngược ra *"trạng thái trước đó là
gì"* từ chữ tự do là đoán — mà đoán trượt thì màn hiện sai và **không báo lỗi**.

### Vì sao phải có cột `source`

Trạng thái YCMH là số **SUY RA** từ các phiếu con (`_tinh_lai_trang_thai_ycmh`) — duyệt một PMH thì
YCMH tự nhảy, **không ai bấm gì**. Không phân biệt người/máy thì lịch sử hiện một dòng đổi trạng
thái không có tên ai, người đọc tưởng mất dữ liệu.

### ⚠️ Chốt kỹ thuật — MỘT CỬA

Hiện có **7 chỗ** trong `purchase_service.py` gán thẳng `row.status = ...`. Rải lệnh ghi lịch sử ra
7 chỗ thì **chắc chắn sót** — đúng bệnh `_tinh_lai_trang_thai_ycmh` đã mắc: 6/7 mốc quên suy lại,
và YCMH treo sai trạng thái hàng tháng không ai biết.

Nên: gom về **một hàm duy nhất**

```python
def _dat_trang_thai(row, moi, *, doc_type, actor=None, ly_do=None) -> None:
    """Cửa DUY NHẤT để đổi trạng thái. Không đổi thì KHÔNG ghi dòng nào."""
```

Mọi chỗ khác gọi qua nó. `actor=None` ⇒ `source='may'`.

### Luật ghi

1. **Chỉ ghi khi trạng thái THỰC SỰ đổi.** YCMH được suy lại ở mọi thao tác chạm phiếu con; suy ra
   trùng trạng thái cũ thì bỏ qua — nếu không mỗi cú bấm đẻ một dòng rác.
2. **Chỉ ghi ĐỔI TRẠNG THÁI.** Sửa nội dung, sửa dòng hàng… vẫn thuộc `audit_logs`. Bảng này mà
   thành nơi ghi mọi thứ là nó phình vô ích.
3. Bảng chỉ phình, không bao giờ co. Vài trăm phiếu/tháng chưa đáng lo; khi nào chậm thì cắt theo
   mốc ngày, **đừng bỏ luật 1**.

### Dữ liệu cũ — KHÔNG backfill

Phiếu lập trước ngày lên bản mới hiện *"Chưa ghi nhận — phiếu lập trước khi hệ theo dõi lịch sử"*.
Đúng nếp `NULL = phiếu cũ` dùng khắp module. Backfill là **bịa ra ngày giờ không ai biết**.

### Hiển thị

Khối *Lịch sử trạng thái* trong drawer chi tiết (cả YCMH và PMH), mới nhất trên cùng:

```
Đã mua → Giao một phần     hệ tự suy         7/8 09:10
Đã duyệt → Đã mua          Nguyễn Văn A      7/8 08:45
Chờ duyệt → Đã duyệt       Trần Thị B        6/8 14:32   "Đồng ý mua"
Nháp → Chờ duyệt           Nguyễn Văn A      6/8 14:10
```

---

## 3. Import / Export Excel — vật tư nhà cung cấp

**Vào:** `Thu mua → Nhà cung cấp` → mở một NCC → mục *Mặt hàng*

| Nút | Việc |
|---|---|
| **Tải mẫu** | File `.xlsx` có sẵn tiêu đề + 2 dòng ví dụ + ghi chú từng cột |
| **Xuất Excel** | Danh mục mặt hàng **hiện có** của đúng NCC đang mở |
| **Nhập Excel** | **THÊM VÀO** danh mục hiện có (chủ chốt), **1 file cho 1 NCC** |

Cột: `Tên hàng*` · `Đơn vị*` · `Đơn giá*` · `VAT %` · `Ghi chú`

### Luật nhập

- **THÊM VÀO, không thay thế.** Mặt hàng cũ giữ nguyên. Thay thế toàn bộ là một cú bấm xoá sạch
  danh mục mà không ai lường trước.
- **Trùng tên hàng + đơn vị** với dòng đã có ⇒ **cập nhật đơn giá/VAT/ghi chú** của dòng đó, không
  đẻ dòng thứ hai. Hai dòng cùng tên cùng ĐVT khác giá thì form phiếu mua không biết chọn cái nào.
- **Hỏng dòng nào báo dòng đó**, kèm số dòng Excel + lý do. Nhập được bao nhiêu ăn bấy nhiêu, KHÔNG
  huỷ cả file vì một dòng sai — file 200 dòng mà sai dòng 197 thì bắt sửa rồi nhập lại cả file là
  hành người dùng.
- Trần **500 dòng/file**, và nói rõ trên màn.

Quyền: **`thu_mua:read`** cho *Tải mẫu* + *Xuất Excel*, **`thu_mua:update`** cho *Nhập Excel*. Hai
file kia chỉ bày lại đúng thứ người ta đã nhìn thấy trên màn; nhập mới là thay bảng giá.

### ⚠️ Chốt kỹ thuật — nhập KHÔNG ghi thẳng DB

Bảng giá nằm **trong form sửa NCC**, và cả form được lưu bằng một cú `PUT /api/suppliers/{id}`
mang theo **toàn bộ** danh sách mặt hàng. Nên endpoint nhập chỉ **ĐỌC** file rồi trả về
`{items, errors, total_rows}`; giao diện gộp vào form, người dùng xem lại rồi bấm *Lưu nhà cung
cấp* mới vào sổ.

> Ghi thẳng DB ở bước nhập thì chính cú lưu form đó — vẫn đang giữ danh sách **cũ** trong state —
> sẽ **xoá mất** phần vừa nhập. Mất dữ liệu mà không ai hiểu vì sao.

Hệ quả tốt kèm theo: NCC **đang tạo mới** (chưa có `id`) cũng nhập được, nên endpoint không nhận
`supplier_id`.

| Endpoint | Việc |
|---|---|
| `GET /api/suppliers/items/template.xlsx` | File mẫu |
| `GET /api/suppliers/{id}/items/export.xlsx` | Bảng giá hiện có của NCC đó |
| `POST /api/suppliers/items/import` | Đọc file → `{items, errors, total_rows}`, **không ghi** |

Gộp trùng làm **hai lớp**: `_khoa_vat_tu` (service) lo trùng *trong file*, `gopVatTu`
(SuppliersPage) lo trùng *với danh sách đang có*. Hai chỗ phải dùng **cùng một khoá** — tên + đơn
vị, bỏ hoa/thường và khoảng trắng thừa; lệch nhau thì máy nói trùng mà màn hình nói không.

---

## 4. Badge thông báo Thu mua

Hạ tầng **đã có sẵn** — SSE `hub.broadcast` + state `badges` trong `AppShell` + nếp
`notify-summary` (xem `routers/orders.py`, `routers/attendance.py`). Đợt này chỉ **thêm endpoint
cho Thu mua rồi nối vào**, không dựng mới.

`GET /api/purchase-requests/notify-summary` trả 3 con số:

| Đếm | Ý nghĩa | Ai thấy |
|---|---|---|
| `ycmh_cho_lap_phieu` | YCMH ở *Chờ mua* — việc đang nằm trên bàn thu mua | có `thu_mua:read` |
| `pmh_bi_tu_choi` | PMH `rejected` mà YCMH nguồn vẫn *Chờ mua* — **phải lập lại**, dễ bị bỏ quên nhất | có `thu_mua:read` |
| `dot_giao_qua_han` | Đợt giao quá hạn trả mà còn nợ | có `ke_toan:read` |

Badge = tổng 3 số, gắn ở mục sidebar **Thu mua**. Nhảy NGAY qua SSE (`purchase_changed`,
`accounting_changed` — cả hai đã broadcast sẵn), không bắt refresh — đúng nguyên tắc sản phẩm
"gửi/thông báo nội bộ = real-time".

Đếm theo **PHẠM VI của người xem** (`_purchase_scope`): nhân viên scope `own` chỉ đếm việc của mình.
Đếm toàn công ty cho người chỉ thấy phiếu của mình là badge báo 5 mà mở ra có 1.

---

## 5. YCMH — *Giao một phần* thì giao bao nhiêu

**Vào:** `Thu mua → Yêu cầu mua hàng` → chi tiết

Dữ liệu **đã có sẵn** trong `fulfilment` (`ordered_quantity`, `received_quantity`) — chỉ là màn chưa
hiện. Đây là việc nhẹ nhất trong đợt.

| Chỗ | Trước | Sau |
|---|---|---|
| Cột *Tình trạng* từng dòng | `Giao một phần` | `Giao một phần · 700/1.000 tờ` |
| Badge trạng thái YCMH | `Đang mua` | `Đang mua` + dòng phụ *"3/5 mặt hàng đã về đủ"* |

Số đã giao lấy từ `received_quantity` của dòng PMH — vốn là Σ các đợt giao (đợt 1 đã làm).

---

## 6. Hai việc KHÔNG làm — và vì sao

### ④ Quyền "Đơn mua hàng"

Đã trả lời chủ 07/08/2026, không phát sinh việc. Cấp quyền ở: `Vai trò` → module **Kế toán** → tick
*Xem*. Ba tầng cùng trỏ về key `ke_toan`:

| Tầng | Chỗ khai |
|---|---|
| Menu | `Sidebar.tsx` — mục cha `Kế toán thu mua` khai `module: "ke_toan"`, 3 mục con **thừa hưởng** |
| Cổng vào màn | `MODULES_BY_NAV_ID` — mục con lấy module của cha |
| API | `routers/accounting.py` — `require_permission("ke_toan", "read")` |

Hệ quả cần biết: tick ô đó là mở **cả ba** màn (Đơn mua hàng · Phiếu chi · Công nợ). Muốn tách rời
thì phải cấp module quyền riêng cho màn Đơn mua hàng — **chủ chưa yêu cầu**, đừng tự làm.

### ⑦ Quyền xem tất cả phiếu

**Đã có sẵn.** Hệ không phân theo chức danh mà theo **scope** của vai (`_purchase_scope`):

| Scope | Thấy |
|---|---|
| `all` | Tất cả phiếu của mọi người |
| `department` | Phiếu của người cùng phòng ban |
| `own` | Chỉ phiếu mình lập |

"Chỉ giám đốc thấy hết" là do vai giám đốc đang để scope `all`, không phải luật cứng. Muốn ai đó
thấy hết thì vào `Vai trò` đổi scope module *Thu mua* thành **Tất cả**.

> Thứ hệ CHƯA có: *"xem được hết nhưng không sửa/duyệt của người khác"*. Scope hiện áp cho cả đọc
> lẫn ghi (`_request_ghi` dùng chung `_co_duoc_xem` — cố ý, vì ghi không được rộng hơn đọc). Cần
> tách thì đó là việc riêng, chủ nói thì làm.

---

## 7. Migration

| # | Việc |
|---|---|
| M1 | Bảng mới `purchase_status_history` — `create_all` lo, **nhớ export ở `models/__init__.py`** |
| M2 | `ADD COLUMN` `content` + `reject_reason` cho `department_purchase_requests` và `purchase_requests` |
| M3 | Dồn dữ liệu: `content = purpose` nối `note` (nếu có). **Không** xoá `purpose`/`note` |
| M4 | Cập nhật `docs/DB_SCHEMA.md` **cùng commit** — thiếu là `./init.ps1` đỏ |

---

## 8. Test bắt buộc

1. Đổi trạng thái người bấm → 1 dòng lịch sử, `source='nguoi'`, có tên
2. Duyệt PMH kéo YCMH đổi → dòng của YCMH có `source='may'`, `changed_by` NULL
3. Suy lại YCMH mà **không đổi** trạng thái → **không** đẻ dòng nào
4. Từ chối/huỷ có lý do → lý do vào `reject_reason`, **không** đè `content`
5. Phiếu cũ (trước migration) → `content` đúng bằng `purpose` nối `note`
5b. Nội dung ~960 ký tự → YCMH và PMH đều giữ **nguyên văn**, không cụt ở 500
5c. Chỉ gửi `content` (không `purpose`/`note`) → tạo được; trống cả hai → 422 có chữ "Noi dung"
6. Import Excel: dòng hỏng báo đúng số dòng, dòng lành vẫn vào
7. Import trùng tên+ĐVT → **cập nhật**, không đẻ dòng thứ hai
8. Import quá 500 dòng → chặn
9. `notify-summary` đếm theo **scope** — người scope `own` không thấy việc của người khác
10. YCMH *Giao một phần* → API trả đủ `ordered_quantity` + `received_quantity` từng dòng
