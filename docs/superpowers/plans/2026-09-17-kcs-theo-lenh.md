# KCS theo LỆNH — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KCS đi theo lệnh (LSX → công đoạn → kết quả kiểm), một hành động "kiểm công đoạn", người KCS = thành viên tổ `is_kcs`, tổ bị kiểm nhận thông báo + "Đã xem", công đoạn cuối nhóm mở cửa nhập kho.

**Architecture:** Dùng lại `san_xuat_kcs_batch` / `san_xuat_kcs_loi` / `san_xuat_kcs_loi_anh`, bỏ các cột phân loại cũ (mg `0306`). Service `services/san_xuat/kcs.py` viết lại quanh `kiem_cong_doan`; `la_kcs_cuoi` suy từ công đoạn cuối của nhóm thành phẩm (bỏ điều kiện tổ). FE: một trang KCS mới (danh sách lệnh → chuỗi công đoạn → form kiểm), bàn tổ có dấu KCS + mục "Kết quả KCS" + dòng "KCS báo lỗi".

**Tech Stack:** FastAPI + SQLAlchemy (Postgres dev, SQLite test), React + TypeScript.

**Spec:** `docs/design-kcs-theo-lenh.md` (ĐÃ CHỐT 17/09/2026).

## Global Constraints

- Không Alembic: đổi cột qua `backend/app/db_migrations.py` (raw SQL, guard idempotent) + `docs/DB_SCHEMA.md`.
- Không thêm bảng. Người kiểm / người xem do server chốt từ tài khoản, không nằm trong schema In.
- Kiểm KHÔNG trừ số, KHÔNG đẻ `san_xuat_batch`, KHÔNG đổi trạng thái công việc.
- Gửi nội bộ = SSE tức thì. Phân trang + lọc ở máy chủ.
- UI tiếng Việt. Không hardcode tên phòng ban / vai.
- Verify: pytest nhắm file + `npx tsc --noEmit`; không chạy `./init.ps1`; restart uvicorn qua WMI sau khi sửa route; kiểm luồng bằng dev-browser thật.

---

### Task 1: Schema + quyền KCS theo tổ `is_kcs`

**Files:**
- Modify: `backend/app/db_migrations.py` (mg `0306_kcs_theo_lenh`; `chuyen_quyen_san_xuat_sang_to` không còn đòi `can_qc`)
- Modify: `backend/app/models/role.py`, `models/san_xuat.py`, `models/san_xuat_kcs.py`
- Modify: `backend/app/services/quyen_to.py`, `rbac_service.py`, `role_service.py`, `role_templates.py`, `repositories/rbac_repo.py`, `schemas/rbac.py`, `schemas/auth.py`, `routers/auth.py`
- Modify: `docs/DB_SCHEMA.md`
- Test: `backend/tests/test_kcs_theo_lenh.py` (mới), `tests/test_quyen_to.py`

**Interfaces — Produces:**
- `repositories/san_xuat_kcs_repo.SanXuatKcsRepository.la_thanh_vien_to_kcs(user_id) -> bool`, `.la_truong_to_kcs(user_id) -> bool`
- `services/san_xuat/kcs.la_nguoi_kcs(db, user) -> bool`, `gate_kcs(db, user)`, `gate_truong_kcs(db, user)` (PermissionError)
- `PermissionsOut.kcs: bool`, `PermissionsOut.truong_kcs: bool`

Migration `0306`: DROP `role_permissions.can_qc`, `san_xuat_cong_viec.la_kcs`, `san_xuat_kcs_batch.loai/kcs_department_id/batch_id`, `san_xuat_kcs_loi.trang_thai/ly_do_tu_choi`. Trước khi drop: lỗi cũ `to_chiu_id := cv.department_id`, `cong_doan_ref_id := batch.cong_viec_id` (khi NULL), `phan_hoi_luc := created_at` (coi như đã xem). Best-effort DROP như mg `0305`.

Tests: thành viên tổ `is_kcs` → `la_nguoi_kcs` True; tổ trưởng (head_user_id) → `la_truong_to_kcs`; tổ thường → False; migration chạy hai lần không lỗi và backfill đúng.

### Task 2: Ghi kết quả kiểm + "Đã xem"

**Files:**
- Rewrite: `backend/app/services/san_xuat/kcs.py`
- Modify: `backend/app/repositories/san_xuat_kcs_repo.py`, `backend/app/routers/san_xuat.py`, `backend/app/schemas/san_xuat.py`
- Test: `backend/tests/test_kcs_theo_lenh.py`; xoá `tests/test_san_xuat_kcs.py`, `tests/test_san_xuat_kcs_diem_kiem.py` (luồng cũ đã gỡ)

**Interfaces — Produces:**
- `kiem_cong_doan(db, *, user, cong_viec_id, so_dat, so_loi, checklist_ket_qua=None, ghi_chu=None, loi_mo_ta=None, anh=None) -> dict` với khoá `kcs_batch_id, loi_id, cong_viec_id, department_id, lsx_id, nhom_id, notify_user_ids, so_dat, so_loi, ten_cong_doan`
- `dieu_chinh_ket_qua(db, *, user, kcs_batch_id, so_luong_dat, so_luong_khong_dat, checklist_ket_qua=None, ghi_chu=None, expected_version) -> dict`
- `da_xem_loi(db, *, user, loi_id) -> dict` (gate Xác nhận sản lượng TRỌN tổ chịu)
- Routes: `POST /api/san-xuat/kcs/cong-viec/{id}/kiem` (multipart: so_dat, so_loi, checklist_json, ghi_chu, loi_mo_ta, files) · `PATCH /api/san-xuat/kcs/{batch_id}` · `POST /api/san-xuat/kcs/loi/{id}/da-xem`
- SSE: broadcast `san_xuat_kcs_changed`; publish `san_xuat_kcs_ket_qua` tới `notify_user_ids`.

Luật: người thuộc tổ KCS; công việc đang chạy / tạm dừng / đã xong; số không âm, đạt+lỗi>0; tiêu chí bắt buộc đủ; lỗi>0 ⇒ mô tả + ≥1 ảnh; công đoạn `la_kcs_cuoi` ⇒ Σ đạt ≤ Σ tốt tổ đã ghi. Gỡ route cũ: `POST /work-items/{id}/kcs`, `POST /kcs/{batch}/loi`, `POST /kcs/kiem`, `POST /kcs/loi/{id}/phan-hoi`, `GET /kcs/diem-kiem`, `GET /kcs/hop-thu`.

### Task 3: Công đoạn cuối của nhóm

**Files:**
- Modify: `backend/app/services/san_xuat/snapshot.py` (`danh_dau_kcs_cuoi`, bỏ `la_kcs`), `release.py` (bỏ `kcs_cuoi_thieu`, thông báo mới cho nhiều công đoạn cuối), `repositories/san_xuat_repo.py` (`cross_lsx_edges_chi_tiet` một truy vấn, bỏ lọc `la_kcs`), `services/lsx_service.py`, `schemas/lsx.py`, `schemas/lenh_san_xuat.py`, `services/lenh_sx/ho_so.py`
- Test: `tests/test_san_xuat_release.py`, `tests/test_san_xuat_release_phan_doan.py`, `tests/test_xep_lich_van_de.py`, `tests/test_xep_lich_2.py`

Luật: mỗi LSX thành viên lấy bước cuối routing, bỏ bước là `truoc` của cạnh nối chéo; gộp các ứng viên trỏ cùng công việc chung (bài ghép). Đúng một ⇒ bật `la_kcs_cuoi` cho mọi phân đoạn. Nhiều hơn một ⇒ vấn đề chặn phát hành `kcs_cuoi_nhieu`.

### Task 4: Kho + đóng nhóm + trạng thái lệnh

**Files:**
- Modify: `backend/app/services/san_xuat/kho.py` (`tao_yeu_cau_nhap_kho_cong_doan`), `dong_nhom.py`, `services/lenh_sx/trang_thai.py`, router kho/đóng thiếu
- Test: `tests/test_san_xuat_kho.py`, `tests/test_san_xuat_dong_nhom.py`, `tests/test_lenh_sx_trang_thai.py`

**Interfaces — Produces:**
- `tao_yeu_cau_nhap_kho_cong_doan(db, *, user, cong_viec_id) -> dict` (gate người KCS; tạo yêu cầu cho phần đạt còn lại của từng lần kiểm)
- Route `POST /api/san-xuat/kcs/cong-viec/{id}/yeu-cau-nhap-kho`; `POST /kho/nhom/{id}/dong-thieu` gate `gate_truong_kcs`

Đóng nhóm: điều kiện 3 = Σ(đạt+lỗi) công đoạn cuối ≥ Σ tốt của nó; bỏ `het_loi_kcs_cho`. Trạng thái lệnh: `_sx_da_xong` = mọi công việc xong; `_dang_o_kcs` = sx xong mà công đoạn cuối chưa kiểm đủ.

### Task 5: Mặt đọc

**Files:**
- Modify: `kcs.py` (đọc), `board.py` (bỏ mode kcs / `so_viec_kcs_cho` / `co_viec_kcs`; `cho_xac_nhan` thêm `kcs_loi`; item thêm `kcs_dat`/`kcs_loi`), `kcs_bao_cao.py` (bỏ lọc Loại/Tổ KCS, cột Người kiểm), `repositories/san_xuat_repo.py`, `schemas/san_xuat.py`, router
- Test: `tests/test_kcs_theo_lenh.py`, `tests/test_san_xuat_board.py`, `tests/test_san_xuat_kcs_bao_cao.py`

**Interfaces — Produces:**
- `GET /api/san-xuat/kcs/lenh?tim=&trang=&co=&da_dong=` → `{items:[{lsx_id, ma, ten, khach, nhom_ma, so_cong_doan, so_da_kiem, so_loi, cuoi:{tot, dat, da_yeu_cau}}], tong}`
- `GET /api/san-xuat/kcs/lenh/{lsx_id}` → `{lsx, cong_doan:[{cong_viec_id, ten, phan_doan, to_id, to_ten, trang_thai, tot, hong, don_vi, la_kcs_cuoi, checklist, so_lan_kiem, tong_dat, tong_loi, con_gui_kho, lan_kiem:[...]}]}`
- `GET /api/san-xuat/work-items/{id}/kcs` → `{cong_viec_id, checklist, lan_kiem:[{id, nguoi_kiem, luc, so_dat, so_loi, ket_luan, checklist, ghi_chu, loi:[{id, mo_ta, so_luong, anh, da_xem_luc, nguoi_xem}]}]}`

### Task 6: FE màn KCS

**Files:**
- Create: `frontend/src/pages/kcs/KcsTheoLenhPage.tsx`, `frontend/src/pages/kcs/KcsKiemForm.tsx`
- Modify: `frontend/src/api/client.ts`, `frontend/src/components/AppShell.tsx`, `frontend/src/auth/permissions.tsx`
- Delete: `KcsChayDialog.tsx`, `KcsResultDrawer.tsx`, `ThucHienKcsPage.tsx` (thay bằng trang mới; giữ `KcsDashboard.tsx`, `KcsChotNhom.tsx`)

### Task 7: FE bàn tổ

**Files:**
- Modify: `ThsxChoXacNhanBar.tsx` (dòng "KCS báo lỗi" + "Đã xem"), `ThsxDrawer` (mục "Kết quả KCS"), bảng việc (dấu KCS), `AppShell.tsx` (toast SSE `san_xuat_kcs_ket_qua`), gỡ chip `la_kcs` và cột KCS của `PermissionMatrix.tsx`

### Task 8: Xác minh

- pytest các file đã đụng; `npx tsc --noEmit`; restart uvicorn; chạy mg `0306` trên DB dev.
- dev-browser: tài khoản KCS kiểm một công đoạn tổ khác có lỗi + ảnh → tổ trưởng tổ đó thấy toast + dòng "KCS báo lỗi" + mục "Kết quả KCS" → bấm "Đã xem"; KCS kiểm công đoạn cuối → "Tạo yêu cầu nhập kho" → kho nhận.
