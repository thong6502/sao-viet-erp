# Nhập kho thành phẩm qua "Yêu cầu nhập xuất" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KCS gửi thành phẩm vào sổ kho THẬT (yêu cầu NHẬP → phiếu nhập → lô), bỏ sổ kho riêng của sản xuất; lô mang giá gốc 0 (kế toán kho nhập sau) + giá bán lấy từ đơn; lô nhớ lô gốc qua điều chuyển; giao hàng xuất đúng lô của đơn.

**Architecture:** Thành phẩm khai theo CỤM BÁN (luật `gop-nhom.ts`, viết lại một bản Python ở `thanh_pham_khai_bao`). `services/san_xuat/kho.py` còn hai việc: tạo yêu cầu NHẬP (gọi `StockRequestService.create(commit=False)`) và đọc số đã gửi/đã nhận. Mọi chỗ đọc ngược (bối cảnh lệnh, trạng thái, hồ sơ, KCS, báo cáo KCS) đọc dòng yêu cầu có `san_xuat_cong_viec_id`. Lô gốc = cột `lo_goc_id` trên lô + dòng phiếu nhập, điều chuyển ghi, ghi sổ chép. Sửa giá gốc = một service kho, sửa lô gốc + mọi lô con trong một giao dịch.

**Tech Stack:** FastAPI + SQLAlchemy (Postgres dev, SQLite test), React + TypeScript.

**Spec:** `docs/design-nhap-kho-thanh-pham-qua-yeu-cau-nhap-xuat.md` (chủ chốt 17/09/2026, "làm đi").

## Global Constraints

- Không Alembic: cột qua `backend/app/db_migrations.py` (raw SQL, idempotent, không ORM full-select) + `docs/DB_SCHEMA.md`.
- 4 cột mới đều nullable, soft ref, không FK: `stock_requests.san_xuat_cong_viec_id` (Integer, index), `stock_request_lines.don_gia_ban` (BIGINT), `stock_lots.lo_goc_id` (Integer, index), `stock_voucher_lines.lo_goc_id` (Integer, index).
- Không `hang_loai` thứ ba: thành phẩm là `vat_tu` có `la_thanh_pham = true`.
- Giá gốc lúc nhập = 0. Giá bán = Σ `line_total` cụm ÷ SL cụm, tròn tới đồng; không vào báo cáo NXT.
- Quyền: tạo = `gate_kcs`; nhận = quyền Hộp yêu cầu sẵn có; xem/sửa giá = `kho:view_cost`. Không đẻ quyền mới.
- Gửi nội bộ = SSE tức thì. Phân trang + lọc ở máy chủ. UI tiếng Việt. Danh mục kho động, không hardcode kho.
- Verify: pytest nhắm file + `npx tsc --noEmit`; không chạy `./init.ps1`; restart uvicorn qua WMI; kiểm luồng bằng dev-browser thật, báo cáo từng thao tác.

---

### Task 0: Thành phẩm theo cụm bán + giao hàng theo cụm

**Files:**
- Modify: `backend/app/services/thanh_pham_khai_bao.py`, `backend/app/services/delivery_service.py`
- Modify (FE): form lập yêu cầu giao + form giao thiếu (gom dòng theo cụm, gửi dòng đầu cụm)
- Test: `backend/tests/test_thanh_pham_cum.py` (mới)

**Interfaces — Produces:**
- `CumBan` (dataclass): `khoa: str`, `ten: str`, `dvt: str | None` (TÊN đơn vị như dòng đơn), `so_luong: float`, `dong: list[OrderLine]` (thứ tự dòng đơn), `thanh_tien: int` (Σ `line_total`).
- `cum_ban(order) -> list[CumBan]`; `cum_cua_dong(order, order_line_id) -> CumBan | None`
- `khai_cum(db, order, cum) -> VatTuInAn`; `khai_mot_dong(db, order, line)` trả mã CỤM của dòng; `khai_cho_don` khai mỗi cụm một lần.
- `gia_ban_cum(cum) -> int | None` (None khi SL ≤ 0 hoặc Σ thành tiền ≤ 0).

Luật khoá: nhãn `nhom` chuẩn hoá (trim + lower) + `|` + SL; không nhãn ⇒ `line:<id>`. Tên cụm = nhãn (trim); đơn vị = `dvt_nhom` hoặc ĐVT dòng đầu; SL = SL dòng đầu.

Giao hàng: `tao_yeu_cau` nhận dòng bất kỳ của cụm, bung ra MỌI dòng của cụm cùng SL (hai dòng cùng cụm khác SL ⇒ lỗi); dòng đầu cụm mang `hang_id`, dòng theo sau để trống mặt hàng. `hang_can_xuat` bỏ qua dòng theo sau (đầu cụm có mặt trong yêu cầu), vẫn báo lỗi dòng trống mặt hàng mà không thuộc cụm nào. `_ghi_dong_thuc_nhan` (giao thiếu) bung số thực nhận ra mọi dòng của cụm.

Tests: đơn không nhãn = một mã/dòng; Ruột 500 + Bìa 500 cùng nhãn = một mã tên nhãn, ĐVT cụm; cùng nhãn khác SL = hai mã; giá bán cụm; yêu cầu giao bung dòng + xuất kho một dòng; giao thiếu ghi cả cụm.

### Task 1: Cột + tạo yêu cầu NHẬP từ KCS

**Files:**
- Modify: `backend/app/db_migrations.py` (mg `0309_nhap_kho_thanh_pham_cot`), `models/stock_request.py`, `models/stock_lot.py`, `models/stock_voucher.py`, `repositories/stock_request_repo.py` (`_HEADER_FIELDS`, `_build_line` nhận `don_gia_ban`), `docs/DB_SCHEMA.md`
- Rewrite: `backend/app/services/san_xuat/kho.py`
- Modify: `backend/app/routers/san_xuat.py` (route tạo yêu cầu trả khuôn mới)
- Test: `backend/tests/test_san_xuat_nhap_kho_tp.py` (mới; thay `test_san_xuat_kho.py`, `test_san_xuat_kho_dich.py`)

**Interfaces — Produces:**
- `tao_yeu_cau_nhap_kho_cong_doan(db, *, user, cong_viec_id) -> dict` khoá `request_id, ma, cong_viec_id, so_luong, don_vi, dong: [{hang_id, ma_hang, ten_hang, dvt, sl_de_nghi, don_gia_ban}]`. Tự commit rồi `thong_bao_yeu_cau_moi`.
- `KhongConSoDuGuiKho(ValueError)` giữ nguyên (router 409).
- `dong_nhap_kho_cua_cong_viec(db, cong_viec_ids) -> dict[int, list[DongNhapKhoTp]]`
- `DongNhapKhoTp` (dataclass): `request_id, request_ma, trang_thai, line_id, cong_viec_id, lsx_id, hang_id, dvt, sl_de_nghi, sl_hieu_luc, sl_da_nhan, he_so_kcs, created_at, created_by, updated_at`; thuộc tính `con_hieu_luc` (False khi huỷ/từ chối), `sl_da_de_nghi_kcs` (đã đề nghị quy về đơn vị KCS theo luật §4).
- `so_con_gui_kho(db, cv, dong) -> float` = min(Σ đạt, Σ tốt) − Σ `sl_da_de_nghi_kcs`.

Luật: `gate_kcs`; `cv.la_kcs_cuoi`; khoá lần kiểm `FOR UPDATE` trước khi đọc; nhóm → cụm theo dòng đơn của các lệnh trong nhóm; một cụm ⇒ một dòng SL = số gửi; nhiều cụm ⇒ chia theo SL cụm / Σ SL các cụm (dòng cuối nhận phần dư); quy đổi đơn vị KCS → `don_vi_gia` qua `quy_ve_goc`, lỗi báo lời nghiệp vụ; `lsx_id` = thân chính; `don_gia = 0`; `don_gia_ban` theo Task 0; `ghi_chu` "Nhập thành phẩm từ KCS · <mã lệnh> · <tên>"; `kho_id` trống.

Tests: dòng đơn lẻ; cụm Ruột + Bìa (một dòng, giá bán cụm); nhóm hai cụm (chia); đơn vị lệch quy đổi được / không quy đổi được / TP chưa khai đơn vị; dòng chưa có thành tiền (giá bán trống); bấm lần hai 409; kho huỷ trả số về; ghi sổ một phần rồi huỷ trả phần chưa nhận.

### Task 1c: Lô gốc qua điều chuyển

**Files:** `backend/app/services/stock_voucher_service.py` (`suggest_allocation` trả `lo_goc_id`; `create` nhánh `_dc_dest` chép `lo_goc_id`; `_apply_post` ghi `lo_goc_id` lên lô), `backend/app/repositories/stock_voucher_repo.py` (nếu dựng dòng bằng danh sách cột), `backend/app/repositories/stock_lot_repo.py`
- Test: `backend/tests/test_kho_lo_goc.py` (mới)

**Interfaces — Produces:**
- `StockLotRepository.nguon_lo(lot_ids) -> dict[int, dict]` khoá `lo_goc_id, lsx_id, lsx_ma, order_id, order_ma, customer_id, khach_hang, don_gia_ban, tu_kcs: bool`
- `goc_cua(lot) = lot.lo_goc_id or lot.id`

Tests: A → B → C trỏ về một lô gốc; lô ở kho đích đọc ra đúng đơn/khách/giá bán.

### Task 1d: Sửa giá gốc + danh sách "Thành phẩm chưa có giá gốc"

**Files:**
- Create: `backend/app/services/kho_gia_goc_service.py`
- Modify: `backend/app/routers/kho_voucher.py` (`PATCH /api/kho/phieu/lo/{lot_id}/gia-goc`), `backend/app/routers/kho_baocao.py` (`GET /api/kho/bao-cao/thanh-pham-chua-gia-goc`, phân trang máy chủ), schemas
- FE: `frontend/src/pages/KhoBaoCaoPage.tsx` (mục mới), `frontend/src/api/client.ts`
- Test: `backend/tests/test_kho_gia_goc.py` (mới)

**Interfaces — Produces:**
- `sua_gia_goc(db, *, user, lot_id, don_gia) -> dict` (`don_gia` theo đơn vị dòng phiếu nhập của lô gốc) — sửa `stock_voucher_lines.don_gia` + `stock_lots.don_gia_nhap` của lô gốc và mọi lô `lo_goc_id` = nó; chặn kỳ khoá theo kho + ngày nhập từng lô; chặn lô không phải thành phẩm nhập từ KCS; audit `kho_sua_gia_goc` cũ → mới.
- `ds_chua_gia_goc(db, *, q, chi_chua_gia, page, size) -> {items, total}`.

Tests: sửa xong NXT + giá trị phiếu xuất đã ghi sổ ra số mới, kể cả lô đã điều chuyển; kỳ khoá ở kho đích chặn; thiếu `kho:view_cost` bị 403; lô giấy/vật tư bị chặn.

### Task 1b: Lô theo đơn khi xuất cho Giao hàng

**Files:** `stock_voucher_service.py` (`suggest_allocation(..., order_id=None)`; `create` XUẤT chặn lô khác khách), `routers/kho_voucher.py` (`/lo/goi-y` nhận yêu cầu → đơn; `/lo/danh-sach` + `StockLotOut` thêm nguồn lô), FE lô trong `KhoYeuCauPage.tsx` / `KhoTonKhoPage.tsx`
- Test: `backend/tests/test_kho_lo_theo_don.py` (mới)

Luật: gợi ý lô của đúng đơn trước → lô không có nguồn → lô đơn khác cùng khách; bỏ lô khách khác. Lập phiếu chọn lô khách khác ⇒ lỗi "Lô … sản xuất cho khách …". Lô đơn khác cùng khách ⇒ FE hiện "Lô này sản xuất cho đơn DH…".

### Task 2: Đọc ngược

**Files:** `services/lenh_sx/boi_canh.py` (`nhap_kho_yc` → `nhap_kho_tp: dict[int, list[DongNhapKhoTp]]`, cầu công việc/nhóm), `lenh_sx/trang_thai.py`, `lenh_sx/ho_so.py` (`_kho`, timeline, `_giao_hang` đọc `on_hand_by_kho`), `schemas/lenh_san_xuat.py`, `san_xuat/kcs.py` (`_lan_kiem_ra`, `_tom_cuoi`, `_con_yeu_cau_kho_chan`, chuỗi công đoạn), `san_xuat/kcs_bao_cao.py`, `schemas/san_xuat.py`
- Test: sửa `test_lenh_sx_boi_canh.py`, `test_lenh_sx_trang_thai.py`, `test_lenh_sx_ho_so.py`, `test_san_xuat_kcs*.py`, `test_san_xuat_g5_tich_hop.py`

### Task 3: SSE khi kho ghi sổ

`routers/kho_voucher.post_voucher`: sau `svc.post`, yêu cầu có `san_xuat_cong_viec_id` ⇒ phát sự kiện `san_xuat_kho` (khuôn `_phat_sse_kho`). Test gọi API ghi sổ, bắt broadcast.

### Task 4: Gỡ sổ kho sản xuất

Gỡ endpoint `/kho/hop-thu`, `/kho/nhom/{id}`, `/kho/yeu-cau/{id}/xac-nhan`; model `san_xuat_kho`, repo, schema, `YC_*`; mg `0310_go_so_kho_san_xuat` drop 3 bảng (+ DB_SCHEMA). Pytest nhắm: `test_san_xuat_nhap_kho_tp`, `test_thanh_pham_cum`, `test_kho_*` mới, `test_san_xuat_kcs*`, `test_lenh_sx_*`, `test_stock_request*`, `test_delivery*`, `test_san_xuat_g5_tich_hop`.

### Task 5: Frontend

`KcsChuoiCongDoan` (mã DNN + đề nghị/kho đã nhận, bấm mở Yêu cầu nhập xuất), `KcsTheoLenhPage`, `LenhSxHoSoView` (khối Kho, Giao hàng), `KcsChotNhom`, lô thành phẩm "chưa có giá gốc" + giá bán + đơn/khách ở Tồn kho, mục Báo cáo kho mới; gỡ phần Kho khỏi `ThsxG5`/`ThucHienSxPage` + client; `npx tsc --noEmit`.

### Task 6: Xác minh bằng dev-browser

Chín bước ở spec §12.6, thao tác thật, báo cáo từng bước đã bấm/gõ/thấy.
