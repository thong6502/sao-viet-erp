# GAP — Module Đơn hàng bán (chốt trước khi code)

> Trạng thái: **BẢN CHỐT ĐỂ DUYỆT** — bàn xong mới code. Nguồn: đóng vai NV kinh doanh
> (`sale1` — Lê Sale Một) dùng hết chức năng trên app chạy thật + soi code. Mỗi mục kèm bằng
> chứng code (file:line) và/hoặc trải nghiệm thao tác.

## 0. Phạm vi (khoanh rõ để khỏi lạc đề)

**Module này lo:** lập đơn (nháp) → thu cọc → cổng chốt → chốt (khóa đơn + khóa báo giá) →
bàn giao. Trạng thái quản: `draft → ordered → cancelled`.

**NGOÀI phạm vi — KHÔNG tính là gap của module này:**

| Việc | Lý do ngoài phạm vi |
|---|---|
| Duyệt mẫu (proof) có audit | Khâu **ngoài đời**, không đưa lên hệ thống |
| Giao hàng / số thực giao / POD | Thuộc **module "Kế hoạch giao hàng" riêng** (làm sau) |
| Hóa đơn VAT / công nợ (AR) | Downstream sau giao — module khác |
| Tạo Lệnh sản xuất (LSX) | **Seam** sang module Sản xuất (module SX nhận, không build ở đây) |

---

## 4 VIỆC CẦN LÀM (đúng phạm vi module)

### Việc 1 — [NẶNG] Mở ô nhập **% cọc** trên đơn + sửa cổng cọc

**Vấn đề.** Không có đường nhập `deposit_pct` từ đơn → nó luôn NULL → cổng "đủ cọc mới chốt"
bị **vô hiệu**. Tự tay đã **chốt DH019 với 0đ cọc**.

**Bằng chứng.**
- `OrderCreate` / `OrderUpdate` **không có** `deposit_pct` — [schemas/order.py:90-119](../backend/app/schemas/order.py#L90). OrderUpdate ghi rõ "chỉ thông tin đặt hàng".
- `_create_from_quotation` ghim `quote.deposit_pct` (thực tế NULL); `_create_manual` set `deposit_pct=None` — [order_service.py:475](../backend/app/services/order_service.py#L475).
- Cổng chốt (b) đọc `deposit_ok`; khi `deposit_pct=None` → `deposit_required=0` → `deposit_ok=True` → pass — [order_service.py:198-200](../backend/app/services/order_service.py#L198).
- DB: **13/19 đơn `deposit_pct` = NULL**; đơn tạo thật DH019 = NULL (chỉ 6 đơn seed hardcode 30).

**Đề xuất (gộp vào màn sẵn có, không dựng mới).**
- Thêm ô **% cọc** vào **modal Tạo đơn** + **EditForm** (sửa khi còn nháp).
- Thêm `deposit_pct` vào `OrderCreate` + `OrderUpdate`; service set + validate `0 ≤ pct ≤ 100`.
- Gợi ý mặc định (không bắt buộc): prefill từ hồ sơ khách (CRM) hoặc báo giá nếu có, **nhưng sale sửa được trên đơn** (đúng nguyên tắc: % cọc nhập từ đơn).
- **Không cần migration:** cột `orders.deposit_pct` **đã tồn tại** — chỉ thiếu đường ghi.

**Ưu tiên: CAO** (cổng cọc là chức năng đặc trưng của chính module này).

---

### Việc 2 — [NẶNG] Sửa trình "Sửa vai trò" làm rơi quyền **ghi cọc**

**Vấn đề.** Vai "Kế toán bán hàng" ở DB có `can_record_deposit=1` và server enforce đúng,
nhưng trình Sửa vai trò hiện toggle **TẮT** và **một lần bấm Lưu là ghi đè quyền về false** →
mất quyền ghi cọc của Kế toán.

**Bằng chứng.**
- `PermissionRow` (dùng cho **cả đọc lẫn ghi** — `PermissionMatrixIn`) **thiếu** `can_record_deposit`; có `can_approve_exception` (dòng 272) nhưng không có dòng record_deposit — [schemas/rbac.py:240-277](../backend/app/schemas/rbac.py#L240).
- Quyền được nối đủ ở mọi nơi khác: model [role.py:171](../backend/app/models/role.py#L171), seed [seed.py:169,285](../backend/app/seed.py#L169), enforce [orders.py:247](../backend/app/routers/orders.py#L247), `/auth/me` [rbac_service.py:143](../backend/app/services/rbac_service.py#L143), frontend `can()` [permissions.tsx:92](../frontend/src/auth/permissions.tsx#L92).
- Repo default False → Lưu thiếu field = ghi đè false — [rbac_repo.py:252](../backend/app/repositories/rbac_repo.py#L252).

**Đề xuất.** Thêm `can_record_deposit: bool = False` vào `PermissionRow`; đảm bảo router update
truyền field này. Test: mở Sửa vai trò "Kế toán bán hàng" thấy "Ghi phiếu thu cọc" **ON**, bấm
Lưu **không mất**. **Không cần migration** (cột role_permissions.can_record_deposit đã có — migration 0067).

**Ưu tiên: CAO** (rẻ, chặn rủi ro mất quyền âm thầm).

---

### Việc 3 — Real-time + "hộp việc theo vai" cho bàn giao nội bộ

**Vấn đề.** Một đơn đi qua tay Sale → Kế toán (ghi cọc) → TP (duyệt) → Sale (chốt), nhưng các
mốc bàn giao **im lặng** — không badge, không toast. Tự tay: trình duyệt DH020 xong là mù,
không biết TP xử lý lúc nào. Vi phạm nguyên tắc "gửi/thông báo nội bộ = real-time".

**Bằng chứng.**
- `order_service` **không** `hub.publish` gì (grep 0 kết quả); hạ tầng SSE có sẵn [realtime.py](../backend/app/realtime.py) và **chỉ báo giá dùng** [quotations.py:658,689](../backend/app/routers/quotations.py#L658).
- Chuông Topbar hiện chỉ đếm **nghỉ phép** (verify sống ở mọi vai).
- List chỉ là tab lọc chung, không cá nhân hóa theo vai.

**Đề xuất.**
- Gắn `hub.publish/broadcast` vào các mốc trong `order_service`: lập đơn (→ Kế toán), ghi **đủ cọc** (→ Sale), trình duyệt (→ TP), duyệt/từ chối (→ Sale). + badge chuông + toast tức thì.
- Thêm **"hộp việc theo vai"** (gộp vào list sẵn có, thêm view/tab — không màn mới): Kế toán = "đơn chờ ghi cọc"; TP = "đơn chờ duyệt"; Sale = "đủ cọc chờ chốt" + "sắp trễ hạn".

**Ưu tiên: TRUNG BÌNH-CAO** (hạ tầng có sẵn, gỡ đúng chỗ đau mỗi ngày).

---

### Việc 4 — Lối "gia hạn / xin báo giá lại" ngay từ đơn

**Vấn đề.** Khi báo giá nguồn hết hạn, cổng chốt chặn *"Báo giá đã hết hạn — cần báo giá lại"*
nhưng **không có lối xử lý từ đơn** → NV kẹt cứng. Tự tay: mọi quote `accepted` trong demo đều
hết hạn, phải sửa DB mới chốt được.

**Bằng chứng.** Cổng chốt (a): `valid_until < today` → blocker — [order_service.py:196-197](../backend/app/services/order_service.py#L196). DB: toàn bộ quote accepted đã quá hạn.

**Đề xuất (cần chốt hướng + quyền).** Ở cổng chốt, khi blocker là "báo giá hết hạn", thêm nút
**"Xin gia hạn báo giá"** hoặc **"Báo giá lại từ đơn"** (nhảy sang màn Báo giá kèm context, hoặc
cho TP/GĐ gia hạn nhanh). Đây là **seam nhẹ sang module Báo giá** — nêu để chốt hướng, ai được
gia hạn thì bàn thêm.

**Ưu tiên: TRUNG BÌNH** (chặn thực tế nhưng cần bàn quyền).

---

### Việc 5 — [NẶNG · SEAM MỚI] Thu cọc = **Phiếu thu THẬT** (Kế toán) lập từ đơn

> Trạng thái: **ĐÃ CHỐT HƯỚNG (2026-07-17), CHỜ LÀM.** Việc 1–4 đã xong + commit.

**Vấn đề.** "Thu cọc" hiện là bản ghi `OrderDeposit` **tự chứa** trong đơn — KHÔNG đẻ ra Phiếu
thu kế toán, không vào sổ quỹ. Yêu cầu đúng: Kế toán **lập Phiếu thu thật** (module Kế toán) TỪ
đơn, phiếu thu link `order_id`; **thu đủ (theo phiếu thu đã thực thu `received`) mới `đủ cọc`** →
Sale mới sang bước sau. Giống luồng lập Phiếu thu từ Phiếu chi.

**Thực trạng — 2 hệ tách rời.**
- `OrderDeposit` (đơn) — standalone, không link kế toán.
- `PaymentReceipt` (Phiếu thu) — **hardwire vào Phiếu chi**: `payment_voucher_id` + `purchase_request_id`
  + snapshot NCC/voucher đều **NOT NULL** (`models/accounting.py:224-254`); chỉ lập từ
  `POST /payment-vouchers/{id}/receipts`. Không có `order_id`, không có nguồn "cọc khách".

**Quyết định đã chốt (Hướng A).**
1. **PaymentReceipt đa nguồn:** thêm `source_type` ('phieu_chi' | 'don_hang_ban') + `order_id`
   (nullable). **Nới NULLABLE** 4 cột nhánh Phiếu chi (`payment_voucher_id`, `purchase_request_id`,
   `voucher_code_snapshot`, `purchase_code_snapshot`, `supplier_name_snapshot`) để nhánh đơn khỏi cần;
   thêm snapshot **khách + mã đơn** cho nhánh đơn. Nhánh Phiếu chi giữ nguyên hành vi (validate
   source_type='phieu_chi' bắt buộc đủ các cột cũ).
2. **Lập từ drawer đơn** — Kế toán bấm ngay trên đơn. Endpoint mới tạo `PaymentReceipt(source=đơn)`,
   gate **`record_deposit`** (dùng lại quyền "Ghi phiếu thu cọc" của Kế toán bán hàng — KHÔNG quyền mới).
3. **Cổng đủ cọc đọc lại:** `deposit_received` = Σ `PaymentReceipt(order_id, status=received)`;
   `deposit_ok = received ≥ required`. Bỏ đọc từ OrderDeposit.
4. **Bỏ hẳn `OrderDeposit` + `OrderDepositAttachment`** (model + bảng + endpoint add/update/delete +
   attachment). Minh chứng cọc → `PaymentReceiptAttachment` (đã có).
5. Phiếu thu cọc hiện trong **màn Phiếu thu Kế toán** (cùng danh sách), nguồn = đơn.

**Điểm phải lo khi code (vùng vỡ-DB).**
- **Migration BẮT BUỘC** (`db_migrations.py`): (a) ALTER `payment_receipts` — thêm `source_type`
  (server_default `'phieu_chi'` cho data cũ), `order_id`, snapshot khách; nới NOT NULL các cột nhánh
  Phiếu chi (SQLite không ALTER cột dễ → dùng kỹ thuật **recreate table** đã có trong db_migrations).
  (b) **Drop** `order_deposits` + `order_deposit_attachments`. Cập nhật `DB_SCHEMA.md` (guard test) cùng lúc.
- **Data cọc cũ:** module đơn hàng bán **CHƯA live** → OrderDeposit chỉ là seed throwaway → **drop,
  KHÔNG migrate** (dev drop dev.db; prod chưa có data thật). ⚠️ *Cần xác nhận không có prod data.*
- **Seed:** đơn seed "đủ cọc" (DH008/013/…) đổi sang tạo `PaymentReceipt(source=đơn, received)`.
- **Trạng thái phiếu thu cọc:** Kế toán bấm = đã thu → tạo thẳng `received` (cổng chỉ tính `received`);
  hoặc theo mẫu 2 bước `waiting → xác nhận đã thu` như nhánh Phiếu chi. *(chốt khi code)*
- **Số chứng từ:** cấp code PT qua document sequence sẵn có.
- **Real-time (Việc 3) giữ:** đủ cọc (received ≥ required) → publish Sale toast.

**Ưu tiên: CAO nhưng NẶNG** — schema surgery bảng kế toán lõi (đang có data + test) + drop bảng.
Làm theo tầng, verify `./init.ps1` sau mỗi bước lớn.

---

## Phụ lục — điểm nhẹ (nhặt khi tiện)

- **Dropdown "Phạm vi"** bày lựa chọn chết cho NV Sales (chọn Cả phòng/Tất cả không đổi gì vì backend kẹp về own) → nên **ẩn options vượt scope** của vai. Không rò dữ liệu (an toàn), chỉ gây hiểu nhầm.
- **Đơn vị tính** trên dòng đơn (tờ/ram/kg/cuốn/cái) — hiện `qty` là số trần.
- **Reorder 1-chạm** (in lại y hệt, giữ kẽm) & lối **đổi đơn nhẹ** khi đang chạy (hiện chỉ có "đơn bổ sung" = in thêm).

---

## Nhật ký kiểm chứng (đã làm thật trên app)

Vai `sale1` (Lê Sale Một): duyệt list/tab/lọc; **tạo** đơn nhập tay DH020 (auto "Chờ duyệt");
mở flow **đơn bổ sung** (chọn đơn gốc DH019); **sửa** đủ field + Lưu; **trình duyệt** DH020;
**chốt** DH019 end-to-end (sau khi gia hạn quote để bỏ chặn — thấy chốt được với **0đ cọc**);
**hủy** DH020 có lý do; duyệt 3 tab drawer + timeline 5 bước + nhật ký.

> Dữ liệu test còn lại trong DB demo: DH019 (đã chốt), DH020 (đã hủy), BG26-0003 gia hạn tới
> 31/12/2026. Có thể revert nếu cần.
