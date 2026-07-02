# Context Map — Sổ liên đới chéo phân hệ (INDEX)

Ghi mọi "mối nối treo" giữa các phân hệ: phần một phân hệ **chưa làm được** vì phụ thuộc
phân hệ chưa build.

> ⚠️ **Nguồn sự thật KHÔNG phải file này.** Nguồn sự thật = **marker `SEAM-NN` trong code**
> + **test pytest skip/xfail mang đúng ID**. Bảng dưới chỉ là *index* để người đọc tra nhanh.
> Nếu bảng và code lệch nhau → tin code. (Lý tưởng: sinh bảng từ marker/test, không gõ tay hai nơi.)

Nền lý thuyết: Seam (Feathers) · Branch by Abstraction & Parallel Change (Fowler) ·
Dependency Inversion + Ports/Adapters (Martin/Cockburn) · Anti-Corruption Layer + Context Map (Evans) ·
Consumer-Driven Contract (Pact) · Acyclic Dependencies Principle (Martin).

## Trạng thái
⏳ chờ (đã dựng seam) · 🔨 đang back-fill · ✅ đã đấu nối & đóng seam

## Quy ước seam (bắt buộc khi tạo)
1. **ID ổn định** `SEAM-NN` (không tái dùng số đã đóng).
2. **Marker trong code** tại chỗ nối: `# SEAM-NN: chờ <phân hệ đích>` (Python) / `// SEAM-NN: ...` (TS)
   → `grep -r SEAM-NN` ra mọi chỗ cần back-fill.
3. **Placeholder = Stub tường minh**: `raise NotImplementedError("SEAM-NN chưa back-fill")` —
   KHÔNG trả giá trị giả im lặng (tránh bug ẩn / debt vô hình).
4. **Enabling point = 1 test skip/xfail** mang ID: `@pytest.mark.skip(reason="SEAM-NN <mô tả>")`
   → `./init.ps1` tự liệt kê seam còn treo; back-fill xong test chuyển XANH.
5. **Hướng phụ thuộc theo DIP**: bên *CẦN* (downstream) **sở hữu interface/port**; bên *cung cấp*
   (upstream) implement sau. Cấm FK/tham chiếu tạo **vòng lặp** (ADP).
6. **Đóng seam (Parallel Change · pha Contract — BẮT BUỘC)**: back-fill phải (a) test skip→xanh,
   (b) **xoá stub**, (c) đổi trạng thái ⏳→✅. Bỏ pha này = tệ hơn ban đầu.

## Sổ

| ID | Từ (module · file/interface) | Tới (module đích) | Loại seam | Contract (chữ ký/kỳ vọng) | Enabling point (test/marker) | Hướng | Trạng thái | Điều kiện đóng (DoD) |
|----|------------------------------|-------------------|-----------|----------------------------|------------------------------|-------|-----------|----------------------|
| _(workflow tự thêm khi chạy — hàng dưới là seam P0 biết trước, dựng khi build phân hệ liên quan)_ |
| SEAM-01 | Kinh doanh · order_progress (port) | Sản xuất · Job | port-interface | `get_production_progress(order_id) -> pct/status` | `test_seam_01` (skip) | KD→SX (downstream KD sở hữu port) | ⏳ | test_seam_01 xanh + xoá stub + entry ✅ |
| SEAM-02 | Kinh doanh · delivery_status (port) | Giao hàng | port-interface | `get_delivery_status(order_id) -> status` | `test_seam_02` (skip) | KD→GH | ⏳ | test_seam_02 xanh + xoá stub + entry ✅ |
| SEAM-03 | Sản phẩm · PaperMasterLookup (port) | Danh mục Giấy · dm_giay_vat_tu (PaperMaster) | port-interface | `get(paper_master_id) -> PaperMaster` · `list(q) -> [PaperMaster]` (cho `ProductComponent.paper_master_id`, §34:894) | `test_seam_03` (skip, reason="SEAM-03 chờ dm_giay_vat_tu (PaperMaster)") | SP→Giấy (downstream SP sở hữu port) | ⏳ | test_seam_03 xanh + xoá stub + entry ✅ |
| SEAM-04 | Kinh doanh · quotation_ref/deposit_payment (port) — spec-10 Đơn hàng bán · `backend/app/services/order_ports.py` | Báo giá + Tài chính (Payment) | port-interface | `quotation_ref(quotation_id) -> {approved, version, effective_from, total, customer_id, lines}` + `record_deposit/deposit_total(order_id) -> Payment(kind=deposit)`; gate ③→④ `approved AND deposit≥total·min_deposit_pct` | `test_seam_04_quotation_ref_and_deposit` (skip) + `test_seam_04_deposit_payment_stub_raises` (XANH) + `test_seam_04_quotation_ref_needs_repo` (XANH) — `backend/tests/test_seam_don_hang_ban.py` | KD→Báo giá/TC (downstream KD sở hữu port) | ⏳ (nửa **quotation_ref ĐÃ live** — Báo giá đã build feat-043..045, `QuotationRefAdapter` đọc live; nửa **deposit_payment TREO** — bảng Payment chưa build, feat-048) | test_seam_04 (deposit) xanh + xoá stub deposit + entry ✅ (khi Payment build) |
| SEAM-05 | Kinh doanh · proof_gate (port) — spec-10 Đơn hàng bán · `backend/app/services/order_ports.py` | Chế bản & Duyệt mẫu | port-interface | `proof_gate(order_id) -> {customer_approved: bool}` (read-only, chỉ-báo cổng ⑤→⑥) | `test_seam_05_proof_gate_indicator` (skip) + `test_seam_05_proof_gate_stub_raises` (XANH) — `backend/tests/test_seam_don_hang_ban.py` | KD→Chế bản | ⏳ (F6 chỉ-báo, feat-049 TREO) | test_seam_05 xanh + xoá stub + entry ✅ |
| SEAM-06 | Kinh doanh · customer_paper_lot (port) — spec-10 Đơn hàng bán · `backend/app/services/order_ports.py` | Kho | port-interface | `customer_paper_lot(order_id) -> [StockLot{ownership=customer, owner_customer_id, cost=0, actual_sheets}]` (read-only, ứng giấy khách) | `test_seam_06_customer_paper_lot` (skip) + `test_seam_06_customer_paper_lot_stub_raises` (XANH) — `backend/tests/test_seam_don_hang_ban.py` | KD→Kho | ⏳ (F4 ứng giấy, feat-049 TREO) | test_seam_06 xanh + xoá stub + entry ✅ |
| SEAM-07 | Kinh doanh · tinh_gia · PaperCostLookup (port) — spec-08 Tính giá | Danh mục Giấy / Kho · dm_giay_vat_tu/kho | port-interface | `get_price(paper_master_id, at_date) -> {per_ram, per_kg, lot_type, ownership}` (giá versioned + lô + giấy khách cost=0; §23:530, §12:361–362, §43#7:1212) | `test_seam_07` (skip, reason="SEAM-07 chờ giá giấy (PaperCost)") — `backend/tests/test_seam_tinh_gia.py` | Tính giá→Giấy/Kho (downstream sở hữu port) | ⏳ | test_seam_07 xanh + xoá stub + entry ✅ |
| SEAM-08 | Kinh doanh · tinh_gia · PieceRateLookup (port) — spec-08 Tính giá | Sản xuất · Tổ & Đầu việc | port-interface | `get_rate(operation_key, at_date) -> {unit, unit_price}` (đơn giá khoán nội bộ versioned; §41:1137, §43:1201) | `test_seam_08` (skip, reason="SEAM-08 chờ đơn giá khoán (PieceRate)") — `backend/tests/test_seam_tinh_gia.py` | Tính giá→Tổ&ĐV (downstream sở hữu port) | ⏳ | test_seam_08 xanh + xoá stub + entry ✅ |
| SEAM-09 | Kinh doanh · tinh_gia · NormLookup (port) — spec-08 Tính giá | Danh mục · Định mức & Bù hao | port-interface | `get_norm(norm_key, context, at_date) -> value` (yield_rate/running_waste_pct/makeready_per_color_side versioned; §31b:788–793, §43#3:1207) | `test_seam_09` (skip, reason="SEAM-09 chờ định mức/bù hao (Norm)") — `backend/tests/test_seam_tinh_gia.py` | Tính giá→Định mức (downstream sở hữu port) | ✅ | ĐÃ ĐÓNG (Phase 1B): Định mức & Bù hao (`norms`) đã build -> `get_norm` thực tế; stub raise đã bỏ, test XANH |
| SEAM-10 | Kinh doanh · tinh_gia · MachineSpecLookup (port) — spec-08 Tính giá | Thiết bị · may_moc | port-interface | `get(machine_id) -> {units_per_pass, max_sheet_w, max_sheet_h}` (số đơn vị máy cho số_pass; §31c:797–800, §23:534) | `test_seam_10` (skip, reason="SEAM-10 chờ specs máy (MachineSpec)") — `backend/tests/test_seam_tinh_gia.py` | Tính giá→Máy (downstream sở hữu port) | ⏳ | test_seam_10 xanh + xoá stub + entry ✅ |
| SEAM-11 | Kinh doanh · tinh_gia · ProductRead (port) — spec-08 Tính giá | Kinh doanh · san_pham (spec-07) | port-interface | `get(product_id) -> {components:[{component_type, finished_w/h, bleed, grain_direction, colors_front/back, page_count}]}` (đọc cấu phần SP; §34:893–894) | `test_seam_11` (skip, reason="SEAM-11 chờ đọc Sản phẩm (ProductRead)") — `backend/tests/test_seam_tinh_gia.py` | Tính giá→SP (downstream sở hữu port) | ⏳ | test_seam_11 xanh + xoá stub + entry ✅ |
| SEAM-12 | Kinh doanh · tinh_gia · OutsourcePriceLookup (port) — spec-08 Tính giá | Cung ứng · thu_mua (NCC) | port-interface | `get_rate(operation_key, supplier_id?, at_date) -> unit_price` (đơn giá NCC gia công cho execution_mode=outsourced; §14:389–390, §23:538) | `test_seam_12` (skip, reason="SEAM-12 chờ đơn giá NCC gia công (OutsourcePrice)") — `backend/tests/test_seam_tinh_gia.py` | Tính giá→NCC (downstream sở hữu port) | ⏳ | test_seam_12 xanh + xoá stub + entry ✅ |
| SEAM-13 | Kinh doanh · bao_gia · CostingResultPort (port) — spec-09 Báo giá · `backend/app/services/quotation_ports.py` | Kinh doanh · Tính giá (spec-08, costing engine) | port-interface | `get_costing_result(costing_id) -> {cost_von_total, unit_price_snapshot, norm_snapshot, effective_from/to}` (Báo giá snapshot copy-on-write giá **và** định mức; §34 L877-878, §43#5 L1209) | `test_seam_13_costing_result` (skip, reason="SEAM-13 Báo giá ← Tính giá (costing engine) chưa build") — `backend/tests/test_seam_quotation.py` | Báo giá→Tính giá (downstream Báo giá sở hữu port) | ⏳ | test_seam_13 xanh + xoá stub + entry ✅ |
| SEAM-14 | Kinh doanh · bao_gia · CustomerLookupPort (port) — spec-09 Báo giá · `backend/app/services/quotation_ports.py` | Kinh doanh · Khách hàng (CRM) | port-interface | `get_customer(customer_id) -> {name, tax_code, credit_status_display}` (read-only; Báo giá KHÔNG chặn hạn mức — chặn/override thuộc Đơn hàng bán, §34 L885) | `test_seam_14_customer_lookup` (XANH — `CustomerRefAdapter`) — `backend/tests/test_seam_quotation.py` | Báo giá→CRM (downstream Báo giá sở hữu port) | ✅ | ĐÃ ĐÓNG (feat-043): CRM (`customers`) đã build → `CustomerRefAdapter` đọc live; stub raise đã bỏ, test XANH |
| SEAM-16 | Kinh doanh · Khách hàng (CRM) · `CustomerReceivablePort` (port) — spec-06 · `backend/app/ports/customer_finance_port.py` | Tài chính–Kế toán · công nợ (`cong_no`) | port-interface | `get_ar_balance(customer_id) -> int (VND)` — dư nợ AR cho thẻ công nợ chỉ-đọc; stub RAISE (không bịa 0 → tránh che vượt hạn mức); §23 L528, §41 L1133 | `test_seam_16_receivable_balance` (skip) + `test_seam_16_stub_raises` — `backend/tests/test_seam_customer_finance.py` | CRM→Kế toán (downstream CRM sở hữu port) | ⏳ | test_seam_16 xanh + xoá stub + entry ✅ |
| SEAM-17 | Kinh doanh · Khách hàng (CRM) · `CreditOverridePort` (port) — spec-06 · idem | Kế toán (action `credit_override`, §37 L1065) | port-interface | `record_override(customer_id, over_amount, reason, approver_user_id) -> id` — vượt hạn mức KHÔNG chặn cứng (§34 L885-886); P1 (§35 L912) | `test_seam_17_credit_override` (skip) + `test_seam_17_stub_raises` — `backend/tests/test_seam_customer_finance.py` | CRM→Kế toán | ⏳ | test_seam_17 xanh + xoá stub + entry ✅ |
| SEAM-18 | Kinh doanh · Khách hàng (CRM) · netting AR↔AP (P1; chưa mở cổng ở P0) — spec-06 | Cung ứng / AP | port-interface | `net_ar_ap(customer_id) -> net` *(chốt chữ ký khi build P1)* — khách cũng là NCC (§34 L886), P1 (§35 L912) | `test_seam_18_netting_ar_ap` (skip) — `backend/tests/test_seam_customer_finance.py` | CRM→(Kế toán/Cung ứng) | ⏳ | test_seam_18 xanh + cổng thật + entry ✅ |
| SEAM-19 | Danh mục · Tài xế (`drivers`) · `DriverEmployeePort` (port) — spec-16 · `backend/app/ports/driver_hr_port.py` | Nhân sự (HCNS · `employees`) | port-interface (+ FK nullable) | `get_employee(employee_id) -> EmployeeRef?{id,name,code}` (đọc ref nhân viên cho tài xế nội bộ; `drivers.employee_id` = Integer/IX **KHÔNG FK** tới khi `employees` tồn tại — §16 L430, §43 L1229); stub RAISE (không bịa hồ sơ) | `test_seam_19_resolve_employee` (skip, reason="SEAM-19 chờ Nhân sự (employees)") + `test_seam_19_stub_raises` (XANH) — `backend/tests/test_seam_driver_hr.py` | Tài xế→Nhân sự (downstream Tài xế sở hữu port) | ⏳ | test_seam_19 xanh + thêm FK `drivers.employee_id→employees.id` + xoá stub + entry ✅ |
| SEAM-20 | Danh mục & Cấu hình · Khoản mục chi phí (`khoan_muc_chi_phi`) · `ExpenseItemUsageLookup` (port) — spec-14 · `backend/app/services/expense_item_ports.py` | Kế toán (`CashVoucher`/`AccountingMapping`/`JobCostLine`) | port-interface | `is_referenced(expense_item_id) -> bool` — guard hard-delete; stub RAISE (KHÔNG trả "an toàn để xoá" giả); tên FK consumer chưa vào DB_SCHEMA (§19 L471, §42 L1189) [chưa xác nhận]; Ẩn/Hiện (`is_active`) KHÔNG cần seam, chạy ngay | `test_seam_20` (skip, reason="SEAM-20 chờ Kế toán (CashVoucher/AccountingMapping/JobCostLine)") — `backend/tests/test_seam_khoan_muc_chi_phi.py` | Khoản mục→Kế toán (downstream Khoản mục sở hữu port) | ⏳ | test_seam_20 xanh + xoá stub + entry ✅ |
| SEAM-21 | Danh mục & Cấu hình · Phương tiện vận chuyển (`phuong_tien`) · `VehicleCarrierPort` (port) — spec-15 · `backend/app/ports/vehicle_carrier_port.py` | Cung ứng · `thu_mua` (NCC vận chuyển thuê ngoài) | port-interface (+ FK nullable) | `get_carrier(carrier_supplier_id) -> {name, tax_code}` (read-only, hiển thị nhà xe thuê; `vehicles.carrier_supplier_id` = Integer/IX **KHÔNG FK** tới khi `thu_mua` tồn tại — §15 L417, §18 L461, §42 L1202); stub RAISE (KHÔNG bịa bản ghi NCC → giữ `carrier_name` free-text fallback) [chưa xác nhận: bảng `vehicles`/`thu_mua` chưa vào DB_SCHEMA] | `test_seam_21_carrier_lookup` (skip, reason="SEAM-21 chờ Cung ứng · thu_mua (NCC)") + `test_seam_21_stub_raises` (XANH) — `backend/tests/test_seam_vehicle_carrier.py` | Phương tiện→Cung ứng (downstream Phương tiện sở hữu port) | ⏳ | test_seam_21 xanh + thêm FK `vehicles.carrier_supplier_id→thu_mua.id` + xoá stub + entry ✅ |
| SEAM-22 | Danh mục & Cấu hình · Giấy & Vật tư (`dm_giay_vat_tu`) · `PaperStockUsageLookup` (port) — spec-11 · `backend/app/ports/paper_stock_usage_port.py` | Kho · `StockLot` | port-interface | `is_referenced(paper_master_id) -> bool` — guard hard-delete Giấy; stub RAISE (KHÔNG trả "an toàn để xoá" giả); tham chiếu SP/Tính giá (`product_components.paper_master_id` L299 / `costing_paper_options.sheet_paper_master_id` L501) kiểm TRỰC TIẾP trong DB (không seam); Ẩn/Hiện (`is_active`) chạy ngay [chưa xác nhận: `StockLot`/bảng `paper_masters` chưa vào DB_SCHEMA] | `test_seam_22` (skip, reason="SEAM-22 chờ Kho (StockLot)") + `test_seam_22_stub_raises` (XANH) — `backend/tests/test_seam_paper_stock.py` | Giấy→Kho (downstream Giấy sở hữu port) | ⏳ | test_seam_22 xanh + xoá stub + entry ✅ |
| SEAM-23 | Kinh doanh · Báo giá (`bao_gia`) · `DiscountPolicyResolvePort` (port) — spec-13 · `backend/app/services/quotation_ports.py` | Danh mục & Cấu hình · Chiết khấu (`dm_chiet_khau` engine) | port-interface | `resolve_discount(scope, at_date, qty_basis) -> {discount_amount_vnd:int, policy_version:int, effective_from, effective_to}` (chính sách đang hiệu lực → **1 số VND** cho `quotations.discount`; % quy VND ở đây; đơn đã chốt KHÔNG hồi tố — snapshot §43#5) [chưa xác nhận: bảng `discount_policies`/`discount_tiers` + `module_key` `dm_chiet_khau` chưa có] | `test_seam_23_resolve_discount` (skip, reason="SEAM-23 Báo giá ← Chiết khấu (engine) chưa build") + `test_seam_23_stub_raises` (XANH) — `backend/tests/test_seam_quotation.py` | Báo giá→Chiết khấu (downstream Báo giá sở hữu port) | ⏳ | test_seam_23 xanh + xoá stub + entry ✅ |
| SEAM-24 | Kinh doanh · Sản phẩm (`san_pham`) · `ProductUsageLookup` (port) — spec-07 · `backend/app/ports/product_usage_port.py` | Kinh doanh · Tính giá / Báo giá / Đơn hàng (consumer của SP) | port-interface | `list_usages(product_id) -> [{doc_type ∈ {costing,quotation,order}, doc_id, doc_code, status, at}]` (panel **Được-dùng-ở-đâu** + drill-through, Object-Page SP) + `is_referenced(product_id) -> bool` (guard hard-delete) + `count_used() -> int` (KPI "đã dùng"); chiều **NGƯỢC** SEAM-11 (SEAM-11 = Tính giá→đọc-cấu-phần-SP; SEAM-24 = SP→liệt-kê-chứng-từ-dùng-nó, `costings.product_id` L467); stub RAISE (KHÔNG bịa danh sách dùng, KHÔNG trả "an toàn để xoá" giả) [chưa xác nhận: bảng `quotations`/`orders` where-used chưa đủ ở P0 — costing đọc trực tiếp được] | `test_seam_24` (skip, reason="SEAM-24 chờ consumer SP (Tính giá/Báo giá/Đơn hàng)") + `test_seam_24_stub_raises` (XANH) — `backend/tests/test_seam_san_pham.py` | Sản phẩm→consumer (downstream SP sở hữu port; DIP · tránh vòng lặp ADP) | ⏳ | test_seam_24 xanh + xoá stub + entry ✅ |

## Planner map — feat TREO ↔ seam (module Kinh doanh, plan 2026-07-01)

> Bảng dưới KHÔNG phải nguồn sự thật (vẫn là marker + test skip). Chỉ để tra: feat nào **TREO**
> vì phụ thuộc phân hệ chưa build, và đóng seam nào thì feat đó buildable. Các feat "làm ngay"
> (feat-027..031, 033..036, 038..039, 043..047) dựng màn + trạng thái seam tường minh ngay, KHÔNG
> đợi seam.

| Feat TREO | Spec | Chờ phân hệ | Seam(s) | Đóng seam ⇒ buildable |
|-----------|------|-------------|---------|------------------------|
| feat-032 | 06 Khách hàng · KH-05 (P1) | Kế toán/Công nợ · Cung ứng/AP | SEAM-17 (CreditOverride) · SEAM-18 (netting AR↔AP) | 17+18 xanh |
| feat-037 | 07 Sản phẩm · picker Giấy sống | Danh mục Giấy (`dm_giay_vat_tu`) | SEAM-03 (PaperMaster) | 03 xanh |
| feat-040 | 08 Tính giá · số pass + bù hao | Định mức & Bù hao · Thiết bị/Máy | SEAM-09 (Norm) · SEAM-10 (MachineSpec) | 09+10 xanh (plates/lượt-in làm ngay) |
| feat-041 | 08 Tính giá · gia công | Sản xuất·Tổ&Đầu việc · Cung ứng/NCC | SEAM-08 (PieceRate) · SEAM-12 (OutsourcePrice) | 08+12 xanh |
| feat-042 | 08 Tính giá · giá vốn/pool + so sánh | Giấy · Khoán · Định mức · Máy · NCC | SEAM-07·08·09·10·12 (SEAM-11 đọc SP có sẵn sau feat-033..036) | 07..12 xanh |
| feat-048 | 10 Đơn hàng · cọc + CreditOverride | Tài chính (Payment) · Kế toán | SEAM-04-payment (`deposit_payment`) · SEAM-17 | gate/khóa snapshot làm ngay; ghi cọc/override treo |
| feat-049 | 10 Đơn hàng · ứng giấy + proof + tiến độ/giao | Kho · Chế bản · Sản xuất · Giao hàng | SEAM-06 (customer_paper_lot) · SEAM-05 (proof_gate) · SEAM-01 (order_progress) · SEAM-02 (delivery_status) | 06+05+01+02 xanh |

> Ghi chú số hiệu (Planner cần chốt trước generate): (1) `tinh_gia` (spec-08) vs `tinh_gia_thanh`
> (module key đã seed ở `backend/app/seed.py`) — đề xuất dùng `tinh_gia_thanh` để khỏi đổi RBAC.
> (2) "spec-06" đụng Unit-levels/PBI-4009 (`test_unit_levels_api`, `models/unit_level.py`) — Khách hàng
> giữ tên file `spec-06-khach-hang.md` nhưng là bảng `customers` riêng, KHÔNG liên quan unit-levels.
> (3) `order_no` pattern chưa xác nhận (KHÔNG dùng `PB###` = mã phòng ban).

## Planner map — feat TREO ↔ seam (module Danh mục & Cấu hình, plan 2026-07-02)

> Nguồn sự thật vẫn là **marker `SEAM-NN` + test skip**. Bảng chỉ để tra. 6 spec (11..16) → 33 feat
> (feat-050..082). **29 làm ngay** (data-model + màn/screen dựng ngay KÈM trạng-thái-seam tường minh:
> "Chưa có phân hệ Kho/Kế toán/NCC/Nhân sự" thay vì trắng màn) + **4 TREO** (back-fill vào phân hệ
> chưa build). SEAM-22 (Giấy←Kho) và SEAM-23 (Báo giá←Chiết khấu) là **seam MỚI** đợt này. SEAM-19/20/21
> đã dựng từ P0 (port + test tồn tại) — build màn = **xác nhận** chứ không tạo lại.

| Feat TREO | Spec | Chờ phân hệ | Seam | Đóng seam ⇒ buildable |
|-----------|------|-------------|------|------------------------|
| feat-079 | 11 Giấy · xoá an toàn (guard hard-delete) | Kho (`StockLot`) | SEAM-22 (PaperStockUsageLookup) | 22 xanh (Ẩn/Hiện + guard tường minh làm ngay feat-055) |
| feat-080 | 14 Khoản mục chi phí · xoá an toàn | Kế toán (`CashVoucher`/`AccountingMapping`/`JobCostLine`) | SEAM-20 (ExpenseItemUsageLookup) | 20 xanh (Ẩn/Hiện làm ngay feat-070) |
| feat-081 | 15 Phương tiện · thẻ Nhà xe | Cung ứng (`thu_mua`/NCC) | SEAM-21 (VehicleCarrierPort) | 21 xanh + FK `vehicles.carrier_supplier_id→thu_mua.id` (fallback `carrier_name` làm ngay feat-074) |
| feat-082 | 16 Tài xế · thẻ Nhân viên | Nhân sự (`employees`) | SEAM-19 (DriverEmployeePort) | 19 xanh + FK `drivers.employee_id→employees.id` (fallback "Chưa có Nhân sự" làm ngay feat-078) |

> **Seam PROVIDER/back-fill làm-ngay (KHÔNG treo — phân hệ đích đã tồn tại):**
> - **feat-061** đóng **SEAM-09** (Định mức là PRODUCER — bảng `norms` chính nó cấp `get_norm`; Tính giá
>   downstream đã có port → back-fill + unskip `test_seam_09_norm_lookup` ngay khi `norms` live).
> - **feat-066** đóng **SEAM-23** (Chiết khấu engine cấp `resolve_discount`; Báo giá đã build feat-043..045
>   → wiring live ngay khi bảng chiết khấu live).
> - **SEAM-03** (SP đọc PaperMaster) / **SEAM-07** nửa `{per_ram,per_kg}` (Tính giá đọc giá giấy): build
>   `paper_masters`/`paper_costs` (feat-050) làm 2 seam đó **buildable**; back-fill thực hiện ở feat-037
>   (SEAM-03) và feat-042 (SEAM-07, đủ khi Kho cấp `{lot_type,ownership}`) — KHÔNG mở seam mới.
>
> Ghi chú số hiệu (Planner chốt trước generate): `dm_chiet_khau` (SEAM-23) chưa có trong §38 L1056 →
> đề xuất bổ sung `module_key`; enum `vehicle_type`/`expense_group`, đơn vị `capacity_kg`, tiền tố mã
> (`GY###`/`KM###`/`XE###`/`TX###`), `driver_type`, `scope_product_type` (chiết khấu) đều **[chưa xác
> nhận]** — chờ SVN, giữ nhãn trong feat.

## Loại seam thường gặp
- **port-interface** — bên cần định nghĩa interface, bên cung cấp implement (mặc định, linh hoạt nhất).
- **FK nullable** — cột khóa ngoại để trống tới khi bảng đích tồn tại (dùng cho quan hệ dữ liệu P0).
- **stub** — hàm/endpoint trả lỗi tường minh cho tới khi có thật.
- **event** — bên cung cấp phát sự kiện, bên cần lắng nghe (nới lỏng phụ thuộc nhất).
