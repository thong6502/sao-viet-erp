# Thiết kế lại Luồng Kinh doanh — Sao Việt Nhật ERP

> Trạng thái: **BẢN THIẾT KẾ — CHƯA BUILD**. Khách hàng (CRM) + Tính giá đã xong.
> Doc này thiết kế phần còn lại của luồng bán:
> **Báo giá → Chốt đơn → Duyệt mẫu → (Sản xuất) → Giao hàng → Hóa đơn + Công nợ → Quyết toán.**
> Con số thương mại (tỷ lệ cọc, hạn mức…) đánh dấu ⏳ chờ SVN xác nhận — KHÔNG hardcode, phải versioned.
> Nguồn nền: `DOMAIN_NHA_MAY_IN.md` §8/§9/§32/§34/§42, `CROSS_MODULE_LINKS.md` (seam), `DB_SCHEMA.md`.

---

## 1. Mục tiêu & phạm vi

- **Nối liền mắt xích đang đứt:** hiện luồng chạy thật tới **Đơn hàng nháp** rồi **đứt cứng ở "chốt đơn"**
  vì thiếu ghi cọc / hạn mức / hóa đơn / công nợ (SEAM‑04/16/17 stub).
- **Dựng "lát Tài chính mỏng"** trong ERP để chốt đơn + thu tiền + công nợ chạy thật, theo ranh giới HYBRID → MISA.
- **Mở nhóm "Giao hàng"** (kế hoạch giao · điều phối · giao thực tế/POD) — theo dõi tiến độ thực hiện đơn.
- **Đính kèm file thiết kế** (khách gửi / mình làm) + **phiếu bàn giao** giữa các bộ phận.
- **Ngoài phạm vi (để MISA / phân hệ khác):** phát hành hóa đơn GTGT pháp lý, sổ cái/BCTC/tờ khai thuế (MISA);
  chế bản/duyệt mẫu chi tiết (phân hệ Chế bản); lệnh sản xuất chi tiết (phân hệ Sản xuất — đã có khung).

## 2. Nguyên tắc nền (đã chốt với chủ đầu tư)

| # | Nguyên tắc | Hệ quả thiết kế |
|---|---|---|
| N1 | **Kế toán = HYBRID → MISA** | ERP ghi **cọc/thu tiền + công nợ AR + hạn mức**; chỉ **ghi nhận số/ngày hóa đơn từ MISA**, KHÔNG tự phát hành HĐ GTGT |
| N2 | **Đơn đặc thù → GĐ duyệt** | Margin thấp / dưới giá vốn / giá trị cao / vượt hạn mức → chặn chốt tới khi **GĐ duyệt** (`order_approvals`, có lý do + audit) |
| N3 | **Cọc = gate cứng chốt đơn** | `draft→ordered` cần `báo giá duyệt AND cọc ≥ total·min_deposit_pct` |
| N4 | **Duyệt mẫu = gate cứng vào SX** | chưa khách ký duyệt → không SX/giao (giữ chỗ; phụ thuộc phân hệ Chế bản) |
| N5 | **Hóa đơn theo lần giao** (NĐ123/2020 Đ9 + NĐ70/2025) | HĐ xuất **khi giao**; giao nhiều đợt → nhiều HĐ; **cọc KHÔNG xuất HĐ** |
| N6 | **Giao thiếu là bình thường** | đơn hoàn thành dần; hóa đơn/công nợ theo **phần đã giao thực tế** |
| N7 | **Artwork luôn có chỗ chốt** | mỗi dòng SP phải có 1 file thiết kế "chốt" trước khi ra kẽm (khách gửi hoặc mình làm) |
| N8 | **Bàn giao chéo bộ phận = 1 phiếu** | ai giao · cho ai · món gì+SL · ký nhận 2 đầu · thời điểm — dùng **khuôn phiếu chung** |
| N9 | **Hoa hồng sales** | % gắn **từng đơn** (base = giá trị đơn), **mở dần theo tiền thu**, chi qua **Lương** |
| N10 | **Chiết khấu cuối năm** | Bậc % **cấu hình**, doanh số = **tiền đã thu**, **GĐ duyệt**, giảm trừ DT → MISA |

## 3. Luồng end-to-end (target)

> ⚠️ **Ký hiệu ①→⑭ chỉ để tham chiếu bước trong doc — KHÔNG hiển thị lên UI.** Màn dùng nhãn tiếng Việt tự nhiên (Báo giá · Chốt đơn · Kế hoạch giao hàng…).

| Bước | Ai | Chứng từ | Kế toán chạm | Gate |
|---|---|---|---|---|
| ① Yêu cầu mua hàng | KD | Phiếu yêu cầu | — | |
| ②' Tính giá *(đã có)* | KD/estimator | Phiếu tính giá | — | |
| ③ Báo giá | KD | Báo giá (theo khoảng SL) | — (không chặn hạn mức) | quá hạn → expired |
| ④ **Chốt đơn** | KD + Kế toán | Đơn (DHB…) + **Phiếu thu cọc** | 🟡 hạn mức · 🟡 cọc | 🔴 **cọc ≥ ngưỡng AND báo giá duyệt** |
| ⑤ **Duyệt mẫu** | Chế bản + KH | **Bản mẫu (proof) đã ký** → chốt artwork | — | 🔴 chưa ký → không SX |
| ⑥–⑫ Sản xuất → nhập kho TP | Sản xuất/Kho | Lệnh SX, phiếu xuất/nhập | — | (phân hệ Sản xuất) |
| ⑧ **Kế hoạch giao** | KD | Đợt giao dự kiến | — | (lập sớm, song song từ ④) |
| ⑨ **Điều phối giao** | Tổ trưởng giao | Phân công | — | đợt "sẵn sàng" |
| ⑩ **Giao thực tế** | NV giao | **Phiếu giao/POD** | — | mốc hóa đơn |
| ⑬ **Hóa đơn + công nợ** | Kế toán | **Ghi nhận HĐ (từ MISA)** + phiếu thu | 🔴 HĐ · doanh thu (MISA) · AR | |
| ⑭ Quyết toán job | Kế toán + QL | Báo cáo lãi/lỗ job | giá thành thực vs báo giá | (pha sau) |

## 4. Kiến trúc dữ liệu

### 4.1 Giữ nguyên (đã có)
`customers` (credit_limit, điều khoản TT, chiết khấu) · `quotes`/`quote_versions`/`quote_items` (Báo giá) ·
`orders`/`order_lines` (Đơn hàng bán, tới nháp; có `quotation_id/version`, `has_customer_paper`, `vat_pct_estimate`, `unit_price_snapshot`).
**Sửa nhỏ:** đóng mắt chết `accepted → converted_to_order` — khi tạo đơn từ báo giá thì **khóa báo giá gốc** (tránh tạo đơn thứ 2 từ cùng báo giá).

### 4.2 Lát Tài chính mỏng (mới — đóng SEAM‑04/16/17)

**`payments`** — thu tiền bán (cọc + các đợt):
`id · order_id · customer_id · kind(deposit|partial|final) · amount · method(cash|bank) · paid_at · voucher_no · note · created_by`
→ `deposit_total(order_id) = Σ(kind=deposit)` **đóng SEAM‑04**. Định khoản (xuất MISA sau): Nợ 111/112 / Có 131. **Cọc KHÔNG sinh hóa đơn** (N5).

**`sales_invoices`** — *ghi nhận* hóa đơn phát hành ở MISA (không tự sinh số pháp lý):
`id · order_id · invoice_no(từ MISA) · invoice_date · amount · vat_amount · total · delivery_doc_id(nguồn giao) · status · note`
→ mỗi lần giao ⇒ một (hoặc gộp) hóa đơn cho **phần đã giao**.

**Công nợ AR** — **suy diễn, không bảng riêng (v1):**
`AR(customer) = Σ sales_invoices.total − Σ payments.amount`. Cọc trả trước ⇒ AR âm (khách ứng trước); có HĐ ⇒ AR dương. **đóng SEAM‑16** (`get_ar_balance`).
*(Có thể thêm ledger `receivable_entries` khi cần tuổi nợ chi tiết — pha sau.)*

**`order_approvals`** — duyệt **đơn đặc thù** (GĐ) — **đóng SEAM‑17** (tổng quát hóa "override hạn mức"):
`id · order_id · triggers(json) · trigger_detail · status(cho_duyet|da_duyet|tu_choi) · reason · approver_user_id · decided_at · note`
Hệ **tự soi đơn khi chốt**; trip bất kỳ điều kiện nào → sinh yêu cầu duyệt → **chờ GĐ duyệt** mới cho chốt. Ghi audit (điều kiện trip + số liệu + người duyệt). **Điều kiện trip** (ngưỡng versioned, cấu hình được):

- **Biên lợi nhuận thấp** — margin đơn < `min_margin_pct`.
- **Bán dưới giá vốn** — giá bán < giá vốn (đơn/dòng).
- **Giá trị đơn cao** — tổng đơn > `high_value_threshold`.
- **Vượt hạn mức công nợ** — `AR_dự_phóng = AR + total_đơn − cọc > credit_limit`.

Duyệt: **GĐ** (RBAC `order.approve_exception`). Mở rộng sau: khách mới, điều khoản TT bất thường…

### 4.3 Nhóm Giao hàng (mới — hỗ trợ đóng SEAM‑02)

**`delivery_lines`** — đợt giao (grain: đơn → dòng SP → đợt):
`id · order_id · order_line_id · seq · địa_chỉ ·`
**kế hoạch:** `planned_date · planned_qty ·`
**điều phối:** `assigned_to(NV giao) ·`
**thực tế:** `actual_date · actual_qty · delivery_doc_id ·`
**trạng thái:** `status(cho_sx|san_sang|da_phan|dang_giao|da_giao|giao_mot_phan)`
→ `%HT = actual_qty/planned_qty`; rollup theo đơn. Giao thiếu ⇒ phần còn lại lập đợt mới.

**`delivery_docs`** — phiếu giao/biên bản/POD (gom các đợt cùng chuyến):
`id · doc_no · delivered_at · delivered_by · receiver · note` (1 phiếu ↔ nhiều `delivery_lines`). Chính là "Chứng từ liên quan" trong mẫu báo cáo giao hàng.
*(Là một hiện thực của khuôn phiếu bàn giao §4.5 với `to_dept = khách`.)*

### 4.4 Đính kèm file & bản mẫu (Artwork / Proof)

Nguyên tắc N7: **artwork luôn có 1 chỗ chốt trên dòng SP**. Hai đường vào:

| Tình huống | Đính vào | Bắt buộc? |
|---|---|---|
| Khách gửi file lúc hỏi giá | **dòng Báo giá** (`quote_item`) — file tham khảo cho estimator | ⏳ tùy |
| Ra đơn, mình tự thiết kế | **Yêu cầu làm mẫu** → **bản mẫu (proof)** gửi khách duyệt → bản duyệt chốt thành **artwork trên `order_line`** | ✅ trước khi ra kẽm |
| Khách gửi file in-ready lúc ra đơn | thẳng vào **artwork `order_line`** (vẫn preflight) | ✅ |

Khớp cờ **"Tích chọn đơn cần tạo mẫu"**: khách có file → khỏi tạo mẫu; chưa có → tick "cần tạo mẫu" → mình thiết kế.

**`attachments`** (dùng chung — tận dụng hạ tầng đính kèm đã có ở nhan_su nếu được):
`id · owner_type(quote_item|order_line|proof_version) · owner_id · file_name · path · file_role(khach_gui|thiet_ke_noi_bo|ban_mau|khac) · version · uploaded_by · uploaded_at · note`

**`proof_versions`** — bản mẫu duyệt (theo dõi "tình trạng mẫu / ngày duyệt mẫu"):
`id · order_line_id · version · attachment_id · status(gui_khach|khach_duyet|yeu_cau_sua) · sent_at · approved_at · approved_by_customer`
→ mỗi lần sửa = version mới; bản `khach_duyet` = artwork chốt.

### 4.5 Phiếu bàn giao nội bộ — khuôn chung (N8)

**Ý tưởng:** ~5 loại phiếu bàn giao khác tên nhưng cùng trả lời 6 câu hỏi:
*ai giao → cho ai · theo đơn nào · món gì+bao nhiêu · ai ký nhận · lúc nào · kèm gì.*
→ dùng **1 lõi dữ liệu chung**, điền khác nhau cho từng mối bàn giao. **Chung ruột, khác vỏ** (mỗi phiếu vẫn render trong màn module sở hữu nó, KHÔNG gộp thành 1 màn).

**Lõi chung — `handoff_vouchers`:**
`id · doc_no · voucher_type · from_dept · to_dept · order_id · giao_by · nhan_by · handed_at · status(cho_nhan|da_nhan) · extra_json · note`
**`handoff_items`:** `id · voucher_id · order_line_id · qty · note`

**Phần riêng theo loại** (giữ tùy biến mà không đụng lõi):
- **field lặt vặt** → `extra_json` (không cần migration).
- **field nặng, cần validate** → bảng phụ riêng loại (vd `pod_details`: ảnh ký, GPS, tình trạng; `stock_in_details`: số lô, vị trí kệ).
- **layout màn + mẫu in** → mỗi module tự render/in theo mẫu riêng (đọc cùng dữ liệu).

**Bản đồ các mối bàn giao:**

| Bàn giao | Phiếu | Module sở hữu | v1 |
|---|---|---|---|
| KD → Chế bản | **Yêu cầu làm mẫu** (kèm artwork) | Kinh doanh (đơn) | ✅ in-scope |
| Chế bản → Sản xuất | Bàn giao mẫu duyệt + kẽm | Chế bản/Sản xuất | ⏳ seam |
| Sản xuất → Kho | Nhập kho thành phẩm | Kho | ⏳ |
| Kho → Giao hàng | Xuất kho giao | Kho | ⏳ |
| Giao hàng → **Khách** | **Phiếu giao/POD** | Giao hàng | ✅ in-scope (§4.3) |

**Quy tắc "thoát khuôn":** nếu 1 phiếu tiến hóa tới mức không còn là "bàn giao" (vd gánh định khoản/phân bổ chi phí) → tách ra model riêng. Rủi ro thấp vì v1 chỉ đưa **2 phiếu** vào khuôn.

### 4.6 Hoa hồng sales (base = giá trị đơn, mở dần theo tiền thu)

- **% hoa hồng:** ô trên **từng đơn** (`orders.commission_pct`), mặc định lấy theo nhân viên sales (`employees.commission_pct`, versioned) — sửa được từng đơn.
- **Tổng hoa hồng(đơn) = giá trị đơn × %** (biết trước ngay khi chốt). **Mở dần theo tiền thu:** thu X% tiền → được X% hoa hồng ⇒ về số học `= Σ payments(đơn) × %`. Thu đủ → đủ hoa hồng.
- **Chi trả:** cộng thẳng vào **bảng lương** — seam KD→Lương: Lương gọi `sales_commission(nhân_viên, kỳ)` = tổng hoa hồng mở khóa trong kỳ. *(module `luong` đã chừa "hoa hồng KD".)*
- **Duyệt:** theo quy trình duyệt/chi của Lương (không duyệt riêng). **Kế toán:** chi phí bán hàng (641) qua lương → MISA.
- **Data mới:** 2 cột `orders.commission_pct` + `employees.commission_pct`; KHÔNG bảng mới (accrual suy diễn từ `payments`).
- ⏳ cấu hình: "giá trị đơn" tính **trước VAT** (mặc định) hay gồm VAT.

### 4.7 Chiết khấu khách cuối năm (rebate theo doanh số đã thu)

- **Chính sách:** bảng bậc % **cấu hình được** (versioned) — `rebate_tiers(min_revenue · pct · hiệu_lực)`. Vd ≥1 tỷ → 2%, ≥3 tỷ → 3%.
- **Cơ sở doanh số:** **tiền khách ĐÃ TRẢ THẬT trong năm** = Σ payments(khách, trong năm).
- **Tính (cuối năm):** mỗi khách `doanh_số_đã_thu × %(bậc)` → số tiền chiết khấu đề xuất.
- **Duyệt:** **GĐ duyệt** danh sách. **Kế toán:** giảm trừ doanh thu (TK 521) → chứng từ điều chỉnh ở **MISA** (ERP tính+duyệt+đề xuất, MISA phát hành).
- **Data mới:** `rebate_tiers(min_revenue · pct · hiệu_lực)` + `year_end_rebates(id · customer_id · year · revenue_paid · pct · amount · status(cho_duyet|da_duyet) · approver_user_id · decided_at)`.
- **Màn:** chức năng cuối kỳ trong nhóm Kinh doanh — "Chiết khấu cuối năm": chạy tính → danh sách → GĐ duyệt → đẩy MISA.

### 4.8 Hàng bán trả lại / In bù

Tách 2 bản chất khác nhau (hàng in riêng ít trả hàng thật):

- **Trả hàng (hoàn/giảm):** khách trả → **hóa đơn điều chỉnh giảm** (MISA) + **giảm công nợ AR** + nhập lại kho nếu còn dùng. Ghi lý do.
- **In bù / in lại do lỗi:** lỗi SX/KCS → in lại phần lỗi, **nội bộ — KHÔNG xuất lại HĐ, không thu thêm tiền khách**; chi phí in bù tính vào **giá thành job** (lãi/lỗ). Gắn `fault_party` (lỗi ai chịu).
- **Data mới:** `sales_returns(id · order_id · delivery_doc_id · qty · type(tra_hang|in_bu) · reason · fault_party · credit_note_no(nếu trả hàng, từ MISA) · created_by)`.
- **Nối:** trả hàng → giảm AR + đẩy MISA (HĐ điều chỉnh); in bù → lệnh SX bù (seam Sản xuất) + vào quyết toán job (§8 Pha E).

### 4.9 Cơ chế nối MISA (MISA SME — qua file Excel)

Ranh giới HYBRID (N1): ERP giữ chi tiết bán, MISA làm sổ + phát hành HĐ. Nối bằng **file Excel** (MISA SME có sẵn "nhập khẩu chứng từ từ Excel"), CHƯA dùng API.

- **Hướng chính:** ERP **xuất Excel theo mẫu MISA SME** → kế toán **import vào MISA SME**.
- **3 file xuất định kỳ (theo tháng/lô):**
  1. **Chứng từ bán hàng / hóa đơn** — đơn/giao cần xuất HĐ (khách · hàng · SL · đơn giá · VAT) → MISA phát hành HĐ.
  2. **Phiếu thu** — cọc + thu nốt → MISA ghi Nợ 111/112 / Có 131.
  3. **Bút toán tổng hợp cuối kỳ** — doanh thu 511 · giá vốn 632 · công nợ 131 · thuế 3331 · chiết khấu 521 · hoa hồng 641 (theo bảng định khoản `AccountingMapping`, DOMAIN §42).
- **Chiều ngược:** **số/ngày hóa đơn** từ MISA nhập về ERP → cập nhật `sales_invoices` (khớp công nợ AR).
- **Kỳ đẩy:** theo **tháng** (hoặc theo lô).
- ⏳ Cần lấy **mẫu cột Excel import thật của MISA SME** bên SVN để khớp template. Nâng API sau nếu chuyển AMIS/meInvoice.

## 5. Hai cổng chặn

- **Cổng ④ Chốt đơn** (`order_state`):
  `can_confirm = quote_approved AND deposit_paid ≥ total·min_deposit_pct AND (không còn order_approvals treo)`.
  `order_approvals` treo = có điều kiện đặc thù (margin thấp / dưới giá vốn / giá trị cao / vượt hạn mức) chưa được GĐ duyệt. Engine đã tính đúng số học — chỉ chờ `payments` để có `deposit_paid` thật; nút "Chốt đơn" hết disabled.
- **Cổng ⑤ Duyệt mẫu** (SEAM‑05): giữ chỗ, `proof_gate(order_id)` — nay nối vào `proof_versions` (bản `khach_duyet`). Nếu chưa có phân hệ Chế bản đầy đủ → hiển thị trạng thái tường minh, KHÔNG bịa "đã duyệt".

## 6. Nhóm "Giao hàng" — màn & vai trò

**3 màn:**
1. **Kế hoạch giao hàng** (board chéo các đơn) — mỗi dòng = 1 đợt giao; cột KH↔TT (ngày+SL) + thanh **%HT**; lọc/nhóm theo ngày·khách·trạng thái. Cũng là "Báo cáo theo dõi thực hiện đơn hàng".
2. **Điều phối giao hàng** — tổ trưởng phân đợt/chuyến cho NV giao (chế độ có quyền của board 1).
3. **Việc giao của tôi** — NV giao xem đợt được phân → tick giao thực tế → POD *(bám pattern self-service "Hồ sơ của tôi")*.

**Sở hữu trường (RBAC theo vai):**

| Trường | KD | Tổ trưởng điều phối | NV giao |
|---|---|---|---|
| ngày/SL **kế hoạch** + địa chỉ | ✍️ | 👁 | 👁 |
| **phân công** người giao | 👁 | ✍️ | 👁 |
| ngày/SL **thực tế** + POD | 👁 | ✅ duyệt | ✍️ |

**Trình bày:** không copy grid Excel — board nhóm theo ngày giao, mỗi dòng SP có thanh %HT, mở drawer xem/tick từng đợt; bám pattern `RebuildCatalogPage`.

**Module key mới:** `giao_hang` — scope: KD thấy đợt của **đơn mình**; tổ trưởng thấy **tất cả + phân công**; NV thấy **việc của mình**. *(Cân nhắc thêm key `cong_no` cho thẻ công nợ AR; gate `can_view_debt` đã có sẵn.)*

**Nối tiền:** đợt **sẵn sàng điều phối** khi `đơn=ordered + (duyệt mẫu) + (SX xong)`; **giao thực tế (POD)** ⇒ mốc `sales_invoices` + tăng AR cho phần đã giao.

## 7. Đóng seam (không mở seam mới)

| Seam | Đích | Trước | Sau doc này |
|---|---|---|---|
| SEAM‑04 (deposit) | Tài chính·Payment | ⏳ stub | ✅ `payments` — **A1 ĐÃ build** (feat-048), cọc → mở cổng chốt |
| SEAM‑16 (AR balance) | Kế toán·công nợ | ⏳ stub | ⏳ **HOÃN Pha D** — chưa có hóa đơn thì AR = −cọc là số giả; giữ stub raise (không bịa 0) |
| SEAM‑17 (duyệt đơn đặc thù) | GĐ / Kế toán | ⏳ stub | 🔜 **A2** `order_approvals` (đơn đặc thù: giá trị cao / biên thấp; hạn mức → Pha D) |
| SEAM‑02 (delivery status) | Giao hàng | ⏳ stub | ✅ nhóm Giao hàng |
| SEAM‑05 (proof gate) | Chế bản | ⏳ stub | 🟡 nối `proof_versions`; phần Chế bản sâu **giữ seam** |
| SEAM‑01 (order progress) | Sản xuất | ⏳ stub | ⏳ **giữ** (chờ Sản xuất) |
| SEAM‑06 (customer paper) | Kho | ⚠️ nửa vời | ⏳ giữ (wire khi làm Kho) |

Phiếu bàn giao Chế bản/Kho **tái dùng seam có sẵn**, không tạo mối nối mới.

## 8. Phân pha triển khai (khi "làm đi")

- **Pha A — Lát Tài chính:** `payments` (cọc) + AR suy diễn + `order_approvals` (duyệt đơn đặc thù, GĐ) → **mở khóa chốt đơn**. Cắm vào màn Đơn hàng bán (ghi cọc + cảnh báo/duyệt đặc thù + nút Chốt đơn hết disabled).
- **Pha B — Nhóm Giao hàng:** `delivery_lines` + `delivery_docs` + 3 màn + RBAC. KD khai đợt giao trên Đơn hàng; board + điều phối + việc-của-tôi.
- **Pha C — File & Phiếu bàn giao:** `attachments` + `proof_versions` (artwork/proof) + `handoff_vouchers` khuôn chung (v1: Yêu cầu làm mẫu + POD).
- **Pha D — Hóa đơn & thu nốt + Hoa hồng:** `sales_invoices` (ghi nhận từ MISA) theo POD + thu `partial/final` + thẻ công nợ AR (tuổi nợ, nhắc nợ) + **hoa hồng sales** (§4.6: `commission_pct` + seam KD→Lương).
- **Pha D' — Chiết khấu cuối năm:** `rebate_tiers` + `year_end_rebates` + màn "Chiết khấu cuối năm" (§4.7) — chạy cuối kỳ, GĐ duyệt, đẩy MISA.
- **Pha E — Quyết toán job:** lãi/lỗ đơn (giá thành thực vs báo giá) — phụ thuộc chi phí Sản xuất, để sau.
- **Xuyên suốt:** phân quyền scope (§11) áp từ Pha A; **nối MISA file** (§4.9) đi cùng Pha D; **trả hàng/in bù** (§4.8) + **báo cáo bán hàng** (§12) ở Pha D/E.

## 9. Ràng buộc kỹ thuật (bắt buộc)

- Cột/bảng mới → viết vào `backend/app/db_migrations.py` (KHÔNG có Alembic); cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test).
- Cột Boolean `server_default` = `false`/`true` (KHÔNG `"0"/"1"`) — vd `approved_by_customer` default `false`.
- Sửa route/schema → **restart uvicorn**; verify bằng `./init.ps1` (pytest + compileall).
- Mỗi seam đóng: test skip → xanh + xoá stub + đổi trạng thái ⏳→✅ theo Context Map.
- Backend phân tầng `routers → services → repositories → DB`; logic nghiệp vụ + engine ở services.

## 10. Điểm còn treo (⏳ chờ SVN) + giả định tạm

| Điểm | Giả định tạm (để dựng khung) |
|---|---|
| Đơn in = **hàng hóa** hay **dịch vụ**? | Mặc định **hàng hóa** (HĐ khi giao, cọc không HĐ); đơn ứng giấy khách xử lý riêng |
| **% cọc** | ✅ **Chỉnh được**: theo khách (hồ sơ CRM `prepay_pct`) → khách chưa đặt thì **mặc định chung 50%** |
| **Base cọc** | ✅ **GỒM VAT** (chốt: cọc = % × giá trị đơn đã cộng VAT) |
| Ai duyệt **đơn đặc thù** (vượt hạn mức / margin thấp / giá trị cao) | ✅ **GĐ** (RBAC `order.approve_exception`, qua `order_approvals`) |
| Điều khoản thanh toán | Dùng `payment_term_type` sẵn để tính hạn nợ (pha D) |
| 2 màn Báo giá/Đơn hàng | **Giữ nền + cắm thêm** lát Tài chính (không dựng lại từ đầu) |
| Mã đơn | Đề xuất **`DHB{tháng}/{năm}-{số}`** (theo mẫu thực tế), chờ xác nhận |
| Artwork bắt buộc/không | Tạm **bắt buộc có artwork chốt** trước ra kẽm |
| Ngưỡng đơn đặc thù | `min_margin_pct` / `high_value_threshold` — để **cấu hình versioned**, chưa chốt số |
| "Giá trị đơn" cho hoa hồng | Mặc định **trước VAT** (doanh thu); gồm VAT thì đổi sau |
| Hoa hồng / Chiết khấu cuối năm | ✅ chốt: hoa hồng %/đơn theo tiền thu (§4.6); rebate bậc % trên tiền đã thu, GĐ duyệt (§4.7) |

## 11. Phân quyền dữ liệu phòng Kinh doanh (scope)

Dùng cơ chế **phạm vi dữ liệu sẵn có** của RBAC (**Của tôi / Cả phòng / Tất cả**) — không làm mới. Gán mức theo vai:

| Vai | Phạm vi | Thấy gì |
|---|---|---|
| **Nhân viên KD** | **Của tôi** | Chỉ khách hàng · báo giá · đơn · hoa hồng · báo cáo **mình phụ trách** |
| **Trưởng phòng KD** | **Cả phòng** | Toàn bộ dữ liệu **phòng Kinh doanh** |
| **Giám đốc** | **Tất cả** | Toàn bộ (mọi phòng) + duyệt đơn đặc thù (§4.2) + chiết khấu (§4.7) |

- **Lọc "của tôi"** dựa trên trường người phụ trách đã có: `quotes.salesperson_id`, `orders.sale_user_id`, và khách hàng (owner).
- Áp **nhất quán** cho: Khách hàng · Báo giá · Đơn hàng · Kế hoạch giao (đơn của mình) · Hoa hồng · Báo cáo bán hàng.
- ⚠️ Đảm bảo **Khách hàng có trường "người phụ trách" cấp cá nhân** để lọc "của tôi" (CRM hiện có scope theo phòng; bổ sung owner cá nhân nếu thiếu).

## 12. Báo cáo bán hàng

Mọi báo cáo **tuân theo scope §11** (nhân viên thấy của mình; trưởng phòng/GĐ thấy cả phòng/tất cả).

- **Doanh số bán hàng** — theo kỳ / khách / sales / sản phẩm.
- **Phân tích đơn hàng** — số đơn · giá trị · lãi-lỗ ước tính.
- **Theo dõi thực hiện đơn** — tiến độ giao (chính là board Kế hoạch giao hàng §6).
- **Công nợ** — tuổi nợ AR theo khách · **Hoa hồng** — theo sales/kỳ.
- **Trình bày:** dashboard + bảng lọc/xuất; bám tokens/pattern có sẵn (không grid Excel thô).

## 13. Không làm (out of scope)

Phát hành HĐ GTGT pháp lý · sổ cái/BCTC/tờ khai thuế (MISA) · web‑to‑print · netting AR↔AP (SEAM‑18, P1) ·
engine chiết khấu tự động (SEAM‑23, chiết khấu hiện nhập tay) · lệnh sản xuất chi tiết & chế bản sâu (phân hệ riêng).
