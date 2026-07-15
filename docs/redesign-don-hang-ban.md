# Thiết kế Module Đơn hàng bán — Sao Việt Nhật ERP

> Khâu ④ luồng kinh doanh: **Báo giá đã duyệt → Chốt đơn**.
> Chốt 2026-07-15, sau 2 vòng phản biện nghiệp vụ (góc chủ nhà in + góc kiểm soát ERP).
> Nối tiếp: `redesign-luong-kinh-doanh.md` (§ Đơn hàng), `redesign-bao-gia.md` (cổng chốt ăn báo giá `accepted`).
>
> **Hiện trạng repo:** module Đơn hàng bị gỡ ở commit `df15765` ("giữ navbar + phần dùng chung") —
> vẫn CÒN tầng dữ liệu dùng chung `models/order.py` (bảng `orders` / `order_lines` / `order_approvals`)
> + `order_repo.py` (customer_analytics/exception_gate/seed đang dùng). ĐÃ XÓA: service/router/schema/
> ports/state/`payments.py`/FE page/tests. → "Dựng module" = **dựng lại tầng nghiệp vụ + FE trên bảng đã có**.

---

## 1. Phạm vi

- **Làm:** lập đơn (nháp) → thu cọc → cổng chốt → chốt (khóa đơn + khóa báo giá) → đẩy xuống Sản xuất.
- **Chỉ đặt SEAM (không làm nay):** thao tác duyệt bản in (ở Sản xuất), hóa đơn VAT + công nợ AR,
  hoàn cọc / tính tiền khi hủy, in bù / hàng bán trả lại, hoa hồng, số thực giao / dung sai.

## 2. Nguyên tắc (đã chốt với chủ đầu tư)

- **1 báo giá → 1 đơn TRỌN GÓI**; khóa báo giá ở **bước chốt** (hủy nháp → báo giá dùng lại).
- Giá + mặt hàng **khóa theo nguồn**; đổi quy cách/số lượng ⇒ **báo giá mới**, không sửa trên đơn.
- Kiểm soát nhắm vào **đường tiền + đường giá**, không rải đều lên thao tác hành chính (rải đều = duyệt mù).
- Đơn in mặc định là **hàng hóa** (HĐ khi giao — để dành); đơn **gia công** (khách ứng giấy) xử riêng.
- Cọc **không** xuất hóa đơn VAT (tiền trả trước).

## 3. Luồng end-to-end & vai

1. **Khách đồng ý báo giá** (NV Kinh doanh) — đánh dấu báo giá `accepted` + **đính kèm ≥1 chứng cứ cứng**
   (ảnh PO ký / Zalo-email ghi rõ "đồng ý báo giá số … ngày …"). Báo giá hết hạn ⇒ phải báo giá lại.
2. **Lập đơn nháp** (NV KD) — chọn nguồn (§4) → kế thừa thương mại → bổ sung PO / ngày giao / pháp nhân
   xuất HĐ / bản chất đơn. Đơn ở `draft`, chờ cọc.
3. **Thu cọc** (Kế toán) — ghi phiếu thu cọc (đa hình thức, §7), đính kèm minh chứng.
4. **Chốt đơn** (NV KD / TP KD) — đủ cổng (§8) → `ordered`, khóa cứng đơn + báo giá, đẩy Sản xuất.

## 4. Nguồn tạo đơn (`source_type`)

| Nguồn | Giá | Giá vốn | Duyệt tại đơn |
|---|---|---|---|
| **Từ báo giá đã duyệt** (`bao_gia`) | theo báo giá (bất biến) | ✅ từ báo giá | ❌ (GĐ đã duyệt ở khâu báo giá) |
| **Nhập giá tay** (`nhap_tay`) | Sale gõ | ❌ không có → "biên không xác định" | ✅ **luôn** cần TP/GĐ duyệt |

- Ghim nguồn báo giá bằng `quotation_id + quotation_version + quotation_effective_from` (copy-on-write).
- **Đơn bổ sung** (`order_kind = bo_sung`): in thêm mặt hàng cũ **giữ kẽm** → giá riêng rẻ hơn, lấy từ
  **một báo giá đã trừ kẽm**; bắt buộc trỏ **đơn gốc** (`parent_order_id`). Nếu tự đặt giá ⇒ cần duyệt như nhập tay.
  Điều kiện vật lý "kẽm còn tồn + dùng được, cùng máy/quy cách, trong hạn (~30 ngày)" = **guard nối Sản xuất** (seam,
  tổ trưởng in xác nhận); phần **bóc tách giảm giá đúng cấu phần** (trừ kẽm + CTP + phần canh máy, KHÔNG trừ
  giấy/mực/công chạy) là việc của **engine giá vốn**, không nhét vào field đơn.
- *(Đã bỏ: nguồn "nhân bản đơn cũ".)*

## 5. Trạng thái & 3 mốc mở khóa

`draft` (Nháp) → `ordered` (Đã chốt) → `cancelled` (Hủy). *(Bỏ `on_hold`, `change_order`.)*

`ordered` là trạng thái DUY NHẤT module quản. Ba mốc mở khóa là **điều kiện đọc-được**, không phải status mới:

1. **Chốt đơn** (cổng §8) → mở khóa *mua giấy + ra kẽm* (`material_gate` = đủ cọc).
2. **Khách ký duyệt bản in** → mở khóa *chạy máy* (`run_gate` = `proof_approved`). ⚠️ Thời điểm chốt thì market/
   bản bông thường CHƯA xong → **KHÔNG** nhét điều kiện này vào cổng chốt. Module chỉ **đặt sẵn field seam**
   (`proof_required`, `proof_approved_at/by`, `proof_attachment_id`); **thao tác duyệt bản in nằm ở phân hệ Sản xuất**.
   Với đơn `gia_cong` có brand khách → `proof_required = true` cứng.
3. Chạy máy (Sản xuất).

## 6. Kiểm soát & phê duyệt

- **% cọc = snapshot từ BÁO GIÁ đã duyệt** (`quotation.deposit_pct`, do kinh doanh nhập trên báo giá) — **khóa
  trên đơn** (chỉ đọc). Cổng chốt tính ngưỡng cọc trên **% đã ghim từ báo giá**. KHÔNG lấy từ hồ sơ khách; đơn
  không sửa % cọc. *(Chống "sale tự hạ % cọc" là việc khâu Báo giá — có thể đặt sàn % cọc theo khách ở đó; đợt
  này sale nhập tự do.)* **Số ngày công nợ KHÔNG giữ ở đơn** (chỉ dùng cho Hóa đơn/AR — để dành, khi làm sẽ kéo từ hồ sơ khách).
- **Giá từng dòng nguồn-báo-giá = bất biến:** dòng báo giá read-only trên UI; lúc chốt **đối chiếu cứng** với báo
  giá đã ghim (id+version) — lệch = chặn, buộc requote. → chặn trò "giữ `quotation_id` đã duyệt nhưng lén sửa giá
  dòng xuống, cổng vẫn xanh".
- **Đơn nhập tay + đơn bổ sung tự đặt giá:** BẮT `needs_approval` (TP/GĐ) trước khi chốt, qua `order_approvals`
  (tái dùng bảng đặc thù). Duyệt/từ chối **phải nêu lý do**.
- **Giá vốn trung thực:** đơn nhập tay không có `cost_snapshot` → báo cáo hiện **"biên: không xác định"**, TUYỆT ĐỐI
  không quy 0 thành biên 100%. `cost_basis` ∈ {`quote`, `none`}.
- **Bất biến sau khi tạo:** `source_type`, tham chiếu báo giá, `order_kind`, giá dòng, giá vốn — đổi = tạo nháp mới.
  **Vẫn sửa được ở nháp** (có log): pháp nhân xuất HĐ, người liên hệ, ngày giao, PO, bản chất đơn.

### 6.1 Luật "trình duyệt" — áp cho MỌI cổng cần quyền

- **Người CÓ quyền** → thao tác **thẳng** (Duyệt / Sửa / Hủy) + bắt lý do + ghi vết.
- **Người KHÔNG có quyền** → nút đổi thành **"Gửi / Trình"** → tạo yêu cầu → **chuyển tới người có quyền** →
  người đó **Duyệt / Từ chối** (bắt lý do). Không ai tự xử cái mình không có quyền. "Trình/Gửi" **không cần quyền riêng**.

| Hành động (cần quyền) | Quyền | Người có quyền | Người KHÔNG quyền |
|---|---|---|---|
| Duyệt đơn đặc thù (nhập tay / bổ sung tự đặt giá) | `can_approve_exception` | Duyệt/Từ chối thẳng | **"Trình duyệt"** → chờ TP/GĐ |
| Hủy đơn đã chốt | `can_approve_exception` | Hủy thẳng (lý do + lỗi ai) | **"Gửi yêu cầu hủy"** → chờ TP/GĐ |

**Cờ máy trạng thái phụ** `approval_state` ∈ {`none` · `pending` (đã trình) · `approved` · `rejected` (kèm lý do)}
— sống trên đơn `draft`, KHÔNG đẻ status chính mới. Sale bấm "Trình duyệt" → `pending` → hiện ở tab "Chờ duyệt"
của người có quyền → Duyệt (`approved`) / Từ chối (`rejected` + lý do → Sale sửa, trình lại). Cổng chốt (§8e) chỉ
mở khi `approved` với đơn cần duyệt.

## 7. Cọc & thu tiền (`order_deposits` — nhiều phiếu / 1 đơn, quyền `can_record_deposit` = Kế toán)

- Mỗi phiếu: `deposit_kind` ∈ {CK, tiền mặt, vật tư khách ứng, cấn trừ công nợ} · **số kỳ vọng vs số thực nhận** ·
  đối chiếu sao kê (**chỉ CK**) `reconciled_by/at` · người ghi + thời gian · **đính kèm minh chứng** (ảnh/PDF, lưu static).
- Cổng chốt tính trên **Σ số thực nhận (quy đổi)**, không phải số danh nghĩa. Số gợi ý = `deposit_pct × tổng gồm VAT`,
  nhập tay được (khách chuyển thiếu/dư).
- Sửa/xóa khi đơn **nháp**; sau chốt **khóa** (khóa cùng transaction với hành động chốt). Ghi nhầm sau chốt → hủy có
  lý do (ghi vết), không xóa trắng.

## 8. Cổng chốt đơn (checklist)

Nút "Chốt đơn" bật khi ĐỦ: **(a)** báo giá còn duyệt **và còn hạn hiệu lực** *(nếu nguồn = báo giá; hết hạn → chặn,
buộc báo giá lại)* · **(b)** Σ cọc **thực nhận** ≥ ngưỡng theo **% cọc ghim từ báo giá** · **(c)** đủ PO khách +
ngày giao cam kết · **(d)** có **chứng cứ khách đồng ý** · **(e)** nếu nhập tay / bổ-sung tự đặt giá:
`approval_state = approved` · **(f)** không đặc thù treo.

→ `ordered` + đóng dấu `ordered_at` / `ordered_by` + báo giá `converted_to_order` + push Sản xuất
**(idempotent theo `order_id`)**. Toàn bộ là **1 transaction compare-and-set** (`WHERE status='draft'`).

## 9. Đơn đặc thù

- Đơn từ **báo giá**: đã duyệt ở khâu báo giá (GĐ) — đơn **hiển thị lại** (loại trigger / người / ngày / ghi chú), không duyệt mới.
- Đơn **nhập tay / bổ sung tự đặt giá**: duyệt **tại đơn** theo §6.1 (`can_approve_exception`).

## 10. Hủy đơn + seam sản xuất (giữ móc, không kéo công thức)

- `ordered → cancelled`: người có `can_approve_exception` (TP/GĐ), hoặc người khác **"Gửi yêu cầu hủy"**. Bắt
  `cancel_reason` + `cancel_fault` ∈ {`khach`, `xuong`}.
- Chụp `cancel_stage_snapshot` = `production_stage` lúc hủy (map giai đoạn A/B/C/D của nghiệp vụ nhà in).
- Cọc **không xóa** — chỉ set `deposit_disposition = pending_settlement`. Việc quy ra hoàn bao nhiêu = phân hệ
  hoàn cọc sau đọc (stage + fault + Σ cọc). → audit + linkage tiền **không đứt**.
- `production_stage` ∈ {`none`, `plate_made`, `material_bought`, `printing`, `printed`} — **read-only với đơn**,
  do Sản xuất ghi qua 1 endpoint (seam).

**Bảng mốc xử cọc khi hủy (lỗi khách; lỗi xưởng thì đảo ngược = hoàn cọc)** — *tham chiếu nghiệp vụ, tính tiền ở phân hệ hoàn:*

| Giai đoạn (`cancel_stage_snapshot`) | Xưởng đã chi | Hướng xử cọc |
|---|---|---|
| A. chưa ra kẽm / chưa mua giấy | thiết kế, bình bài | hoàn gần đủ, trừ phí chế bản thực phát sinh |
| B. đã ra kẽm và/hoặc mua giấy | kẽm + CTP; giấy đặc chủng không trả được | trừ kẽm + CTP + giấy đặc chủng; giấy tiêu chuẩn nhập lại thì hoàn phần đó |
| C. đang in | + canh máy + giấy/mực đã tiêu + công chạy | cọc tiêu gần hết; thiếu → thu thêm |
| D. đã in xong / thành phẩm | toàn bộ giá thành | thu 100%, không hoàn |

## 11. Dữ liệu

**`orders`** — *giữ:* `order_no`(DH###), `customer_id`, `quotation_id/version/effective_from`, `order_kind`,
`parent_order_id`, `sale_user_id`, `status`, `vat_pct_estimate`, `cancel_reason`, `created_at`.
*Thêm:* `source_type`, `order_nature` {`hang_hoa`, `gia_cong`}, `approval_state`, `ordered_at`, `ordered_by`,
`delivery_committed_date`, `delivery_address`, `customer_po_no`, `invoice_entity_name`, `invoice_entity_tax_code`,
`deposit_pct` *(ghim từ báo giá)*, `cost_basis`, `needs_approval`, `proof_required`, `proof_approved_at`, `proof_by`,
`proof_attachment_id`, `production_stage`, `cancel_by`, `cancel_at`, `cancel_fault`, `cancel_stage_snapshot`,
`deposit_disposition`.
*Dormant:* `has_customer_paper` (thay bằng `order_nature`), `order_type` (cố định `theo_yc`), `cancelled_at_state`.

**`order_lines`** — *giữ:* `description`, `qty`, `unit_price_snapshot`, `norm_snapshot`, `cost_snapshot`,
`vat_pct_estimate`, `line_total`. Dòng nguồn-báo-giá **read-only**, đối chiếu báo giá đã ghim lúc chốt.

**Bảng mới:** `order_deposits` + `order_deposit_attachments` (§7); chứng cứ "khách đồng ý" = đính kèm trên đơn.
**Tái dùng:** `order_approvals` (duyệt tại đơn); **nhật ký** dùng cơ chế audit sẵn có (như Báo giá / Phiếu tính giá),
không đẻ bảng `order_events` mới.

## 12. Màn hình & thao tác (bám pattern `RebuildCatalogPage`)

- **Danh sách:** tabs *Tất cả · Nháp · Chờ duyệt · Chờ cọc · Sẵn sàng chốt · Đã chốt · Hủy* (có đếm); tìm mã / khách /
  PO; phạm vi *Của tôi · Cả phòng · Tất cả*. Cột: Mã · Khách · Báo giá (link) · Giá trị · **Cọc (tiến độ)** · Ngày
  giao · NV · Trạng thái; **chip cờ** (component `.badge-sem` + `Icon` line trong `Icons.tsx`, **KHÔNG emoji**): đặc
thù · gia công · không giá vốn · chờ duyệt · nháp quá N ngày. Icon toàn màn dùng bộ `Icon` nhà (lucide-react làm mẫu nếu thiếu glyph).
- **Chi tiết:** ① Thương mại (khóa) · ② Đặt hàng (Sale sửa khi nháp) · ③ Cọc (Kế toán) · ④ Duyệt (đặc thù hiển-thị-lại
  / nhập-tay duyệt-tại-đơn) · ⑤ Cổng chốt (checklist §8) · ⑥ Nhật ký hoạt động.

## 13. Phân quyền — module `don_hang_ban`

| Cổng | Quyền | Mới/Tái dùng | Ai cầm |
|---|---|---|---|
| Lập / sửa / **chốt** đơn của mình | `_rcu(own)` + `can_manage_status` | khung sẵn | NV KD |
| **Duyệt đơn đặc thù** *và* **hủy đơn đã chốt** | `can_approve_exception` | tái dùng | TP KD / GĐ |
| **Ghi phiếu thu cọc** | `can_record_deposit` | **mới (duy nhất của module)** | Kế toán |

Phạm vi dữ liệu: NV KD = *Của tôi* (`orders.sale_user_id`) · TP KD = *Cả phòng* · GĐ = *Tất cả*.
**Chuyển đơn** (đổi `sale_user_id`) khi sale nghỉ/chuyển — tái dùng cơ chế reassign của module Khách hàng (quyền cấp TP/GĐ).

## 14. Tình huống xử lý

Đổi quy cách → báo giá mới (không sửa đơn) · hủy khi nháp → báo giá dùng lại · hủy sau chốt → seam §10 · chậm/không
cọc → nằm nháp, không xuống SX · **báo giá hết hạn khi đơn còn nháp** → chặn chốt, buộc báo giá lại · **nháp quá N
ngày** → gắn cờ nhắc/lọc, KHÔNG tự xóa · **đổi NV phụ trách** → chuyển đơn (reassign như Khách hàng) · **dời ngày
giao / lịch giao** → module **Kế hoạch giao hàng** (SEAM-02); đơn chỉ giữ ngày cam kết ban đầu, không sửa sau chốt ·
giao nhiều đợt → khâu Giao hàng (sau).

## 15. Ràng buộc kỹ thuật (bắt buộc)

- Chốt = **1 transaction compare-and-set**; push SX **idempotent theo `order_id`**; cọc khóa **cùng transaction** với chốt.
- **Nhật ký append-only** cho mọi chuyển trạng thái + sửa field nhạy cảm (ai / khi / cũ→mới / lý do): trình duyệt, duyệt,
  từ chối, ghi/sửa cọc, chốt, hủy, nới cọc.
- Cột/bảng mới → `backend/app/db_migrations.py` (KHÔNG Alembic) + cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test).
- Boolean `server_default` = `false`/`true` (KHÔNG `"0"/"1"`).
- Phân tầng `routers → services → repositories → DB`; engine/logic nghiệp vụ ở services. Sửa route/schema → restart
  uvicorn; verify `./init.ps1` (pytest + compileall).

## 16. Phân pha build (khi "làm đi")

- **P1 — Khung đơn:** model bổ sung cột + `order_deposits`/attachments (migration) + schema + repo + service (tạo từ
  báo giá / nhập tay, kế thừa + snapshot dòng, `source_type`, `order_nature`) + router + FE list/detail. Chưa cọc/chốt.
- **P2 — Cọc:** `order_deposits` đa hình thức + quyền `can_record_deposit` + tiến độ cọc + minh chứng.
- **P3 — Kiểm soát & duyệt:** % cọc ghim từ báo giá (khóa trên đơn) · giá dòng bất biến · `needs_approval`/`approval_state`
  + luật trình-duyệt (§6.1) · giá vốn trung thực.
- **P4 — Cổng chốt:** checklist §8 + transaction compare-and-set + khóa báo giá + push SX (seam) + `ordered_at/by`.
- **P5 — Hủy + seam:** `cancel_*` + `production_stage` (read-only seam) + `deposit_disposition` + proof seam field.
- Xuyên suốt: nhật ký audit + RBAC scope + guard test `DB_SCHEMA.md`.
