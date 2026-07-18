# BUILD PLAYBOOK — Module Kế hoạch & Lệnh sản xuất (autonomous run)

> Bắt đầu 2026-07-18. Build **tự chạy tối đa** (agent tự quyết nhánh chưa chốt + tự chấm UI, GHI RÕ giả định; user review cuối).
> **Nguồn sự thật logic:** `docs/spec-ke-hoach-san-xuat.md`. **Nền dữ liệu:** PTG (`PhieuThanhPhan`=lệnh · `PhieuThanhPham`=routing · `OrderLine.phieu_thanh_phan_id`=cầu).
> **Sống sót qua compact:** đọc lại file này + spec + memory (`da-vai-va-cong-nhan-it-hoc`, `chong-over-engineer-phan-bien-hai-chieu`, `module-ke-hoach-san-xuat`) + `git log accounting-wip`.

## 🔒 GUARDRAILS (không được vượt)
- Làm trên **`accounting-wip`**. KHÔNG đụng `main` / worktree `pricing-...` (đang có người graft đơn V4).
- **KHÔNG push** (deploy là quyền user). **Commit checkpoint mỗi chunk** (message tiếng Việt, không Co-Authored-By).
- **Chỉ thêm BẢNG MỚI** (create_all tự tạo) → KHÔNG sửa `db_migrations.py`/`order.py` (tránh đụng graft).
- KHÔNG đụng **engine tính giá**, **màn Đơn hàng bán**.
- KHÔNG xóa/ghi đè file lạ. Blocker cứng → dừng, ghi note vào PROGRESS, không đốt giờ.
- **Verify MỖI CHUNK = NHANH, KHÔNG chạy `init.ps1` đầy đủ** (626 test ~14ph, phí + hay treo): dùng `compileall` + **import-check** (`cd backend; python -c "import app..."`) + **targeted pytest** chỉ file test của chunk (`pytest backend/tests/test_<chunk>.py`). `init.ps1` ĐẦY ĐỦ **chỉ ở MỐC LỚN** (xong toàn bộ backend · trước UI · e2e cuối). Boolean server_default = bool `false`/`true`; cập nhật `DB_SCHEMA.md` khi ĐỔI model (guard test).
- **CHỈ 1 pytest/init.ps1 chạy TẠI MỘT THỜI ĐIỂM** (2 tiến trình pytest tranh chấp DB → treo; bài học 2026-07-18). Đợi cái đang chạy xong mới chạy cái kế.
- **File mới CHƯA wire vào router → `init.ps1` KHÔNG import nó** (pytest không đụng, compileall chỉ kiểm cú pháp). Phải **import-check riêng**: `cd backend; python -c "import app...."`.

## 🧭 NGUYÊN TẮC MỌI AGENT
- **TỰ CHẠY LIÊN TỤC — user VẮNG 5-6h, KHÔNG chờ / KHÔNG hỏi / KHÔNG đứng đợi duyệt.** Tự quyết hết + ghi giả định. Xong chunk → tự review → commit → chunk kế. Chỉ DỪNG khi **blocker cứng** không tự giải (ghi rõ PROGRESS rồi chuyển chunk độc lập khác nếu có).
- **MỞ RỘNG TỪ spec, KHÔNG "theo spec".** Spec = **HẠT GIỐNG** (nền để lớn, KHÔNG phải trần). Mỗi flow: đóng nhiều vai → thảo luận → **NGHĨ THÊM cái spec chưa có** (luồng thợ textless · ca thực tế · cái mỗi vai cần) → build cái **ĐÃ MỞ RỘNG** → **GHI phần mở rộng NGƯỢC vào `spec-ke-hoach-san-xuat.md`** (spec lớn dần). KHÔNG chép spec ra code. *(Spec là luật SO VỚI mockup; nhưng so với chính nó là nền để mở rộng.)*
- **MÁY CHỈ GHI NHẬN** — record-only, không auto-lọc/validate/MRP/quyết.
- Ghép ở **TỜ IN** + **cấu phần** (ruột/bìa/đóng cuốn). Lệnh = 1 ấn phẩm = 1 routing.
- **Không over-engineer** (đọc-đừng-chép · tái-dùng-đừng-đẻ-bảng · dẫn-xuất-để-engine).
- Ảnh mockup = **CHỈ tham khảo UI/UX**, không phải logic.
- **UI thợ = TEXTLESS:** QR quét là chính · icon+màu (xanh chạy/vàng dừng/đỏ lỗi)+ảnh mẫu+số to · nút TO · luồng CỐ ĐỊNH (phản xạ) · xác nhận=1 hành động · lỗi=chụp ảnh. Màn kế hoạch/quản lý mới nhiều chữ.
- UI qua **ui-ux-pro-max (soi+thiết kế) → styleseed → dev-browser**. Real-time notify bám **pattern báo giá**.
- **VERIFY UI = CHẠY THẬT, TỰ XEM (bắt buộc, không đoán):** bật **BE (uvicorn)** + **FE (dev server qua `.claude/launch.json`)** → `navigate` → **tự SCREENSHOT** + `read_page`/`computer`/`read_console_messages`/`read_network_requests` để tự kiểm luồng · vai trò/quyền · real-time notify · lens "thợ không biết chữ dùng bằng trí nhớ?". Lỗi → sửa source → chạy lại. **Lưu screenshot** vào handover cho user.

## 👥 PERSONAS (đóng vai khi design mỗi flow)
Thợ (ít học/không biết chữ/**trí nhớ** — gắt nhất) · Tổ trưởng · Kế hoạch·Điều độ · QC/KCS · Quản lý·chủ xưởng · Kho · (Sale chỉ chốt, không thấy ghép).

## 📦 CHUNKS
1. **Backend data** — 6 bảng (`lenh_sx·print_form·gang_placement·san_luong·ban_giao·qc_defect`) + register + `DB_SCHEMA.md` → init.ps1.
2. **Services** — bung · ghép · gán máy · duyệt mẫu · phát (cổng AND) · sản lượng · bàn giao · QC (QC→tổ trưởng xác nhận) · nhập kho đóng → init.ps1 + unit test.
3. **API** — schemas + routers + mount + real-time SSE (kiểu báo giá) → init.ps1 + smoke.
4. **Seed demo** — đơn/lệnh/tờ ghép mẫu để xem UI.
5. **UI · Tracking views** — list lệnh · Kanban (theo công đoạn) · Gantt · **Theo máy** · **Theo ca** (người literate; LOOK tham khảo mockup ảnh 1,2).
6. **UI · Detail lệnh** — giàu như mockup ảnh 3,4 (routing+QR · sản lượng realtime · job spec+imposition · BOM cần/tồn/thiếu · in phiếu) + **ghép + cấu phần**.
7. **UI · Màn kế hoạch** — ghép bài (chọn lệnh→tờ→số con) · gán máy · duyệt mẫu · phát (cổng AND).
8. **UI · Màn THỢ TEXTLESS** — quét QR ghi sản lượng (đạt/hỏng) · bàn giao (giao/nhận) + QC lỗi (tổ trưởng xác nhận). *(Mockup KHÔNG có — thiết kế MỚI cho thợ ít chữ/trí nhớ.)*
9. **Verify end-to-end** (chốt→…→đóng lệnh) + adversarial + **chạy FE+BE thật, screenshot**.
10. **(stretch)** in bù · hủy giữa chừng · thuê ngoài · OK sheet.

## 🔁 VÒNG LẶP MỖI CHUNK
`[panel đa-vai nếu cần quyết] → build → verify(init.ps1) → fail thì fix → adversarial verify (soi ngược) → commit checkpoint → cập nhật PROGRESS → chunk kế`.

---

## 📋 PROGRESS LOG (cập nhật liên tục)
- **2026-07-18** — Khởi động. Spec commit `7404bdb`. Playbook này tạo. **Chunk 1 (backend data): ĐANG CHẠY.**
- **2026-07-18** — **Chunk 2 (repositories + services): XONG (record-only).** Tạo
  `backend/app/repositories/lenh_san_xuat_repo.py` (`LenhSanXuatRepository` — CRUD/query 6 bảng +
  helper đọc chéo PTG/Đơn) + `backend/app/services/lenh_san_xuat_service.py` (`LenhSanXuatService` —
  bung · ghép/placement · gán máy · duyệt mẫu · phát[cổng AND] · sản lượng · bàn giao/nhận ·
  QC[nêu→tổ trưởng xác nhận] · nhập kho→suy XONG). Self-check `python -m compileall backend/app` =
  PASS (EXIT 0). CHƯA chạy init.ps1/pytest (orchestrator verify). Chưa build routers/schemas/SSE (Chunk 3).
- **Orchestrator (2026-07-18)** — **Chunk 1 XONG + commit `b613097`** (init.ps1: 615 passed/11 skipped). **Chunk 2 verify + commit:** review tay SẠCH (nghi bug `sua_placement` = KHÔNG, repo `update_placement` tự commit) · compileall PASS · **import-check runtime PASS**. Service logic CHƯA unit test riêng → **defer test qua Chunk 3 (API integration) + Chunk 9 (e2e)**. **Chunk 3 chờ init.ps1 no-regression xong mới chạy (single-pytest).**
- **2026-07-18** — **Chunk 3 (API: schemas + routers + mount + SSE + integration test): XONG.** Tạo
  `backend/app/schemas/lenh_san_xuat.py` (request/response DTO) + `backend/app/routers/lenh_san_xuat.py`
  (prefix `/api/lenh-sx`: bung/huy/duyệt mẫu · ghép/gán máy/phát/placement CRUD · sản lượng/bàn
  giao/xác nhận · QC nêu→xác nhận · nhập kho→đóng lệnh; map lỗi service→404/422/409; RBAC module
  `san_xuat`; SSE broadcast qua hub chung). Thêm helper ĐỌC append-only vào `lenh_san_xuat_service.py`
  (list/detail lệnh + tờ, KHÔNG đổi logic mutate Chunk 2) + DI `get_lenh_san_xuat_service` (deps.py)
  + mount (main.py). Test `backend/tests/test_lenh_sx_api.py` = **7 passed** (luồng bung→…→XONG + 3
  cổng: phát chặn thiếu máy/chưa duyệt · sản lượng chặn trước phát · bung idempotent + hủy + đơn hủy).
  Verify NHANH (không init.ps1): `compileall backend/app` EXIT 0 · `import app.main` OK · `pytest
  tests/test_lenh_sx_api.py -q` = 7 passed 25s. Mở rộng ghi ngược `spec-ke-hoach-san-xuat.md` §8.2.

## 🧩 GIẢ ĐỊNH TỰ QUYẾT (agent tự chốt khi spec chưa nói — user duyệt cuối)
**Chunk 2 (services record-only) — mở rộng đã ghi ngược vào `spec-ke-hoach-san-xuat.md`:**
1. **Bung IDEMPOTENT theo (đơn · ấn phẩm)** — `bung_lenh` chỉ tạo lệnh cho `phieu_thanh_phan_id`
   CHƯA có lệnh (đọc tập đã có qua `ptp_ids_with_lenh`). Chốt lại / gọi lại không nhân đôi; đơn
   khoá sau chốt nên grain (đơn·ptp) an toàn. Đơn `cancelled` → không bung.
2. **Sửa xếp bài SAU khi phát = CHẶN.** Thêm/sửa/xoá `gang_placement` chỉ khi tờ `cho_ghep`/
   `du_dieu_kien`; tờ `da_phat`/`in_xong` (đã xuống xưởng) → phải in bù/hủy (P1). Đây là cổng
   TÍNH TOÀN VẸN trạng thái (nhất quán §8), không phải "máy phán nghiệp vụ".
3. **Cổng cứng ghi sản lượng / bàn giao** = lệnh phải `dang_chay` (đã phát) hoặc `xong`. Cụ thể
   hoá §8 ("chỉ từ Phát mới cho ghi sản lượng") ở cấp LỆNH: `phat` tờ → mọi lệnh nháp trên tờ
   thành `dang_chay`.
4. **Trạng thái tờ in SUY RA tự động** (`cho_ghep ⇄ du_dieu_kien`) sau ghép/gán máy/duyệt mẫu/sửa
   placement — KHÔNG bấm tay, KHÔNG hạ cấp khi đã `da_phat`. `in_xong` chưa tự suy ở Chunk 2 (P0
   thiếu tín hiệu "in xong" rõ) → để Chunk 3/sau; cổng cứng dùng `da_phat`.
5. **Idempotent các mốc thời gian**: `duyet_mau` đã duyệt → GIỮ con dấu đầu (đóng băng snapshot,
   không đóng lại); `xac_nhan_nhan` / `to_truong_xac_nhan_qc` đã xác nhận → giữ mốc đầu.
6. **Đích "đủ SL"** = `OrderLine.qty` của ấn phẩm (lùi `PhieuThanhPhan.so_luong`; 0 = chưa biết →
   không tự XONG).
7. **Nhập kho từng phần**: `nhap_kho_thanh_pham(lenh, so_luong_nhap)` — `so_luong_nhap` = TỔNG SL
   thành phẩm đã nhập kho cho lệnh (caller/Chunk 3 cộng dồn từ phiếu Kho THẬT). `≥ đích` ⇒ lệnh
   `xong`. KHÔNG thêm cột cộng-dồn ở `lenh_sx` (nhập kho thật thuộc module Kho — đây chỉ suy trạng thái).
8. **Đơn "xong sản xuất" = SUY RA** (`order_production_done`: có ≥1 lệnh & mọi lệnh không-hủy đều
   `xong`). KHÔNG ghi `orders.status` — Order module sở hữu vòng đời đơn và CHƯA có trạng thái
   "xong SX"; không thêm để khỏi đụng `order.py` + migration (guardrail).
9. **Hủy lệnh** (`huy_lenh`): đánh dấu `huy`, GIỮ mọi log (sản lượng/bàn giao/QC) để truy; chặn hủy
   khi đã `xong`. Hủy-giữa-chừng chi tiết (rollback/quyết toán) = P1.
10. **Snapshot duyệt mẫu** `{user_id, to, chuc_vu, ten}` đọc HỒ SƠ nhân sự (`Employee` theo
    `user_id` → tổ = `Department.name`, chức vụ = `position`), lùi `User.name` khi chưa có hồ sơ —
    mirror `services/actor_display.py` (không suy vai từ hành động).

**Chunk 3 (API: schemas + routers + SSE) — mở rộng đã ghi ngược `spec-ke-hoach-san-xuat.md` §8.2:**
11. **Bung GỌI TAY** (spec chưa nói tự-động-khi-chốt hay gọi tay): chọn `POST /api/lenh-sx/lenh/bung
    {order_id}` gọi tay từ màn kế hoạch — KHÔNG hook vào chốt đơn (guardrail: không đụng `order.py`).
    Idempotent nên bấm lại vô hại. Tự-động-khi-chốt = có thể thêm sau bằng 1 lời gọi service ở
    OrderService (khi user muốn), không cần đổi API này.
12. **RBAC = module `san_xuat` có sẵn** (KHÔNG thêm module mới — tránh phình catalog + seed). Map
    action-bit chung: read/create/update/`approve`(duyệt mẫu + phát)/`cancel`(hủy)/`manage_status`
    (nhập kho). Admin (Giám đốc) có `_full` mọi module ⇒ chạy được ngay. **Tách vai công nhân
    (thợ/tổ trưởng/QC/kho) DEFER**: hệ RBAC là 1-vai/người × module × action-bit, seed CHƯA có vai
    công nhân riêng → không thể tách mịn mà không đẻ vai; khi cần, cấp tập-con action-bit cho từng
    vai, hoặc tách module `ke_hoach_sx`. Ghi rõ để user duyệt hướng.
13. **SSE = broadcast tín hiệu nhẹ qua hub CHUNG** (`app/realtime.py`, 1 worker) — client 1 kết nối
    `/api/quotations/events` nhận mọi `type`, tự lọc. KHÔNG dựng endpoint `/events` riêng cho module
    (hub + queue theo user là chung; thêm stream riêng = thừa). Payload kèm `to_nhan_id`/`to_bi_quy_id`
    để FE lọc đúng tổ. **Đẩy đích-danh theo tổ** (resolve `department_id`→`user_id` rồi `hub.publish`)
    = refinement Chunk 8 khi có tài khoản công nhân — hiện broadcast là đủ real-time, bám đúng cách
    `orders.py` broadcast `order_pending_changed`.
14. **Actor từ token** (người ghi sản lượng, người duyệt mẫu) — không nhận qua body (chống mạo danh).
15. **Helper đọc thêm ở service** (`list_lenh`/`lenh_detail`/`list_forms`/`form_detail`/`san_luong_of`/
    `lenh_on_form`) = APPEND-ONLY cho DTO, giữ layering router→service→repo, KHÔNG đổi logic mutate
    Chunk 2 (guardrail "wire vào, KHÔNG sửa" = không phá hành vi cũ; thêm read thuần được).
