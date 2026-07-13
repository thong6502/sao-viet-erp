# REDESIGN — Module Báo giá (Quotation)

> Trạng thái: **BẢN THIẾT KẾ — CHƯA BUILD** (chưa "làm đi"). Dọn Báo giá về **1 nguồn giá vốn**
> (`PhieuTinhGia`), thay **máy trạng thái** theo SVN chốt, **auto-fill từ CRM**, bám **mẫu báo giá thật**,
> và vá loạt bug đang lộ.
> Nguồn nền: `redesign-tinh-gia.md` (giá vốn — nguồn chuẩn), `PLAN_UI_TINH_GIA_BAO_GIA.md` (luật giá bán
> đã khóa), `redesign-luong-kinh-doanh.md` (§11 phân quyền KD, cổng chốt đơn ăn báo giá `accepted`).
> Con số nghiệp vụ (gói biên, ngưỡng đặc thù) **versioned/cấu hình** — KHÔNG hardcode.

---

## 0. Bối cảnh & quyết định đã chốt

**Vì sao redesign:** module Báo giá đang **kẹt giữa cuộc migrate `Estimate` → `PhieuTinhGia`** (BG‑1 làm,
BG‑4 chưa dọn). UI hôm nay (git `3844b4d`, 2026‑07‑13) đã cắt đường Estimate — báo giá **chỉ khởi từ
PhieuTinhGia** — nhưng backend + màn detail vẫn còn dấu vết cũ, đẻ ra cảm giác "sai sai thiếu thiếu".

**Quyết định đã chốt với chủ đầu tư:**

| # | Quyết định | Ghi chú |
|---|---|---|
| Q1 | Duyệt nội bộ ("Chờ duyệt → Đã duyệt") **chỉ áp báo giá ĐẶC THÙ** | biên < 15% / dưới giá vốn / ≥ 1 tỷ; tái dùng `exception_gate` + `QuoteApproval` (BG‑2) |
| Q2 | **KHÔNG** tách trạng thái "Đã gửi khách" | `sent` gánh luôn nghĩa "Đã duyệt" (đã sẵn sàng/đã gửi, chờ khách) — đúng **7 trạng thái** |
| Q3 | Đổi lớn (SL/chất liệu/gia công/giá vốn) → **HỦY + báo giá mới**; đổi nhỏ → sửa tại chỗ khi Nháp | **gỡ** luồng đa‑phiên‑bản (`requote`/so sánh version) |
| Q4 | GĐ từ chối duyệt → **quay về Nháp** + banner lý do | giữ 7 trạng thái (không đẻ status thứ 8) |
| Q5 | "GĐ duyệt" = vai **Giám đốc Kinh doanh** (mới), không phải GĐ công ty | cầm `can_approve_exception` |
| Q6 | Nguồn giá vốn chuẩn = **`PhieuTinhGia`** | dọn `Estimate` (BG‑4) |

## 1. Mục tiêu & phạm vi

- **Một nguồn giá vốn:** Báo giá chỉ khởi & đọc giá vốn từ `PhieuTinhGia`; gỡ đường `Estimate` khỏi luồng.
- **Máy trạng thái mới** (7 trạng thái) + cổng duyệt nội bộ cho đơn đặc thù + hủy có phân loại lý do.
- **Auto-fill từ CRM** khi chọn khách (người liên hệ chính + địa chỉ giao mặc định) — snapshot, sửa được.
- **Bám mẫu báo giá thật** (người liên hệ, ĐC giao hàng, MÃ PO, 3 ô ký) — giữ design system SVN.
- **Vá UI:** link mở phiếu tính giá, chọn/gán khách ở detail, **MarginPicker** per‑dòng.
- **RBAC** vai **Giám đốc Kinh doanh** duyệt đặc thù.
- **Ngoài phạm vi:** engine giá vốn (thuộc `redesign-tinh-gia.md`); phí ship theo điểm giao (seam Tính giá/Giao
  hàng, để pha sau — `redesign-luong-kinh-doanh` §6); phát hành HĐ GTGT (MISA); duyệt chiết khấu cuối năm.

## 2. Nguồn giá vốn = `PhieuTinhGia` (dọn `Estimate` — BG‑4)

**Căn cứ hội tụ:** (1) `redesign-tinh-gia.md` = module giá vốn redesign; (2) git 2026‑07‑13:
`1904ebc` "dựng lại Báo giá nguồn từ PhieuTinhGia" + `3844b4d` "báo giá chỉ khởi từ PhieuTinhGia (1 PTG→1 BG)";
(3) màn "Tính giá" đang chạy = `TinhGiaPage` → `PhieuTinhGia{List,Detail}View`.

- **Giữ:** `_create_from_ptg` (1 PTG → 1 báo giá; dòng = từng `PhieuThanhPhan`; giá vốn khóa = `gia_von_tp`
  snapshot copy‑on‑write) + guard `active_for_phieu` (1 PTG → 1 báo giá đang hiệu lực).
- **Gỡ khỏi luồng báo giá:** `create_quotation` đường `picks`/`estimate_id`/`selected_option_ids`
  (`quotation_service.py`), nhóm API `estimates` chỉ còn phục vụ **đọc dữ liệu cũ** — không tạo báo giá mới.
- **Field per‑dòng đi theo PTG:** dùng `QuoteItem.phieu_thanh_phan_id` làm tham chiếu nguồn chuẩn;
  `estimate_id`/`estimate_option_id`/`estimate_number` là legacy (giữ cho bản ghi cũ, ẩn dần).

## 3. Máy trạng thái (7 trạng thái)

```
Nháp ─┬─ (thường) ─────────────── Gửi khách ─────────────────► Đã duyệt
      └─ (đặc thù) ── Trình duyệt ──► Chờ duyệt ─┬─ GĐ Duyệt ──► Đã duyệt
                                                 └─ GĐ Từ chối ─► Nháp  (banner đỏ + lý do)

Đã duyệt ─┬─ Khách đồng ý ──► Khách hàng đồng ý ──► [Đơn hàng tạo đơn → converted_to_order (khóa)]
          ├─ Khách từ chối ──► Khách hàng từ chối
          └─ quá hạn ───────► Hết hiệu lực

Hủy báo giá ◄── từ (Nháp · Chờ duyệt · Đã duyệt · Khách đồng ý-khi-CHƯA-lên-đơn) — kèm lý do phân loại
```

| Enum (giữ tên cũ) | Nhãn UI | Ý nghĩa |
|---|---|---|
| `draft` | Nháp | soạn, sửa tự do |
| `pending_approval` **(MỚI)** | Chờ duyệt | **chỉ đặc thù** — đã trình Giám đốc KD |
| `sent` | Đã duyệt *(thường hiện "Đã gửi khách")* | qua cửa (thường: gửi thẳng · đặc thù: GĐ KD đã duyệt) = đã gửi khách, chờ phản hồi (giữ `sent_at`) |
| `accepted` | Khách hàng đồng ý | khách chốt → cổng chốt đơn (`redesign-luong-kinh-doanh` N3) đọc trạng thái này |
| `rejected` | Khách hàng từ chối | khách từ chối **sau** khi gửi |
| `expired` | Hết hiệu lực | quá `valid_until` (time guard) |
| `cancelled` | Hủy báo giá | + lý do phân loại |
| `converted_to_order` | *(ẩn)* Đã lên đơn | khóa **1 báo giá = 1 đơn** — vá B7 |

**Luật:**
- **Đặc thù** (`exception_eval` có trigger): chặn `draft → sent`; buộc `draft → pending_approval → sent`.
  Thường: `draft → sent` thẳng. Nút hiện theo `exception`: có trigger → "Trình duyệt", không → "Gửi khách".
- **GĐ KD Duyệt/Từ chối** ghi `QuoteApproval(decision, note)` (đã có) — không cần bảng mới. Duyệt "bao phủ"
  (`_approval_covers`) → `sent`; báo giá đổi xấu đi sau đó → `stale` → phải trình lại.
- **Từ chối duyệt (Q4):** `pending_approval → draft`, lưu lý do vào `QuoteApproval(decision=rejected, note)`;
  UI hiện **banner đỏ** "GĐ KD trả lại: <lý do> — sửa & trình lại" cho tới khi trình lại. Sales: sửa → Trình
  duyệt lại **hoặc** Hủy.
- **Khóa báo giá gốc (vá B7):** khi Đơn hàng tạo đơn từ báo giá `accepted` → set `converted_to_order`
  (đóng "mắt chết" `redesign-luong-kinh-doanh` §4.1). Chặn tạo đơn thứ 2 từ cùng báo giá.
- **Phân biệt 2 "từ chối":** `rejected` = **khách** từ chối (sau gửi) ≠ GĐ từ chối duyệt (nội bộ, → Nháp).

## 4. Auto-fill từ CRM khi chọn khách

Rule-based từ data sẵn có (khớp luật UI "ít thao tác"). Khi gắn khách vào báo giá, tự điền **2 thứ**
(đều **snapshot** để bản in không đổi khi CRM sửa sau; đều **sửa được / chọn cái khác**):

| Trường báo giá | Nguồn CRM | Quy tắc |
|---|---|---|
| **Người liên hệ** (tên · SĐT · chức vụ) | `CustomerContact.is_primary` | preselect liên hệ chính; nhiều liên hệ → dropdown; fallback `customer.contact_name/phone` |
| **ĐC giao hàng** (địa chỉ · SĐT nhận) | `CustomerAddress.is_default` | preselect điểm Mặc định; nhiều điểm → dropdown |

**Đã BỎ (theo chủ đầu tư):** ĐC trụ sở (bỏ luôn lựa chọn "như trên"); auto-fill Chiết khấu / Điều khoản
thanh toán (ô điều khoản nhập tay hiện có thì giữ, chỉ không tự kéo từ hồ sơ khách); note "ký bài / gửi
khách duyệt".

## 5. Thay đổi schema (field mới)

Cột/bảng mới → viết vào `backend/app/db_migrations.py` + cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test).

**`Quote`** (header):
- `contact_name_snapshot: str | None` — người liên hệ trên báo giá (snapshot).
- `contact_phone_snapshot: str | None`.
- `contact_title_snapshot: str | None` — chức vụ (tùy chọn hiển thị).
- `delivery_address` — **đã có**, chỉ wire auto-fill + cho chọn điểm.
- `status` — thêm giá trị `pending_approval` vào tập enum (string, không cần đổi kiểu cột).

**`QuoteItem`** (dòng):
- `po_code: str | None` — cột **MÃ PO** trên mẫu thật.

> Boolean nếu phát sinh: `server_default` = `false`/`true` (không `"0"/"1"`). `pending_approval` chỉ là chuỗi
> mới → không cần migration cột, chỉ cập nhật hằng số + `quotation_state.py`.

## 6. Vá UI (gộp vào detail sẵn có — KHÔNG dựng màn mới)

Màn detail = `QuotationDetailView` trong `frontend/src/pages/BaoGiaPage.tsx`.

- **B3 — chọn/gán khách ở detail:** thêm ô chọn khách (CRM) trong card **Khách hàng** khi báo giá còn `draft`
  (hiện chỉ dialog Tạo mới có, lại `disabled={isEdit}`). Kèm auto-fill §4. Mọi đường tạo (kể cả tạo nhanh từ
  Tính giá) **phải có khách** hoặc cho gán sau.
- **B2 — link phiếu tính giá:** dòng "Phiếu tính giá" (card Khách hàng) + `↳` per‑dòng → **link bấm mở
  `PhieuTinhGia`** (dùng `phieu_thanh_phan_id` → phiếu nguồn), thay vì text trơ chỉ hiểu `estimate_number`
  (nên BG từ PTG hiện "—"). PLAN_UI Phase 6 đã spec "link mở phiếu" — build thiếu.
- **MarginPicker per‑dòng:** click ô **markup** của từng dòng → popover **MarginPicker** =
  **4 gói biên** (Tiêu chuẩn 25% · Khách quen 18% · Đơn gấp/khó 35% · Cạnh tranh 12%) + **slider** + ô %
  đồng bộ, áp **riêng dòng đó**. Giữ nút **"áp chung mọi dòng"** ở panel. **Dùng chung 1 component** cho cả
  áp‑chung (1 dòng) lẫn per‑dòng (đa dòng) — lấp lỗ PLAN_UI Phase 7 "…ẩn khi đa dòng". Per‑dòng vẫn đi qua
  `update_quotation` (persist `QuoteItem.margin_percent` — đã có), popover chỉ là lớp UI.

## 7. Hủy & đổi (Q3)

- **Đổi lớn** (khách đổi SL / chất liệu / thêm gia công, hoặc **giá NVL tăng cao**) → **HỦY + báo giá mới**
  từ phiếu tính giá mới (vì giá vốn khóa đã lệch). **Gỡ** nút "Tạo phiên bản mới" (`requote`) + UI so sánh
  phiên bản (B6 tự hết). Giữ cấu trúc H‑V‑I nhưng **luôn 1 phiên bản**.
- **Đổi nhỏ** (markup / điều khoản / hiệu lực) → sửa tại chỗ khi còn `draft`.
- **Hủy** cần **lý do phân loại**: `doi_sl · doi_chat_lieu · them_gia_cong · gia_nvl_tang · khac` (+ ghi chú
  tự do) — để báo cáo. Cho hủy từ `draft / pending_approval / sent / accepted` (accepted chỉ khi **chưa**
  `converted_to_order`).

## 8. Dọn nợ kỹ thuật (config-hóa, hết hardcode)

- **B4 — markup / VAT hardcode:** `_create_from_ptg` đang cứng `default_margin=20.0`, `default_vat=10.0`
  (`quotation_service.py`). Đưa **gói biên** (4 gói + nhãn + %) và **VAT mặc định** thành **cấu hình
  versioned** — MarginPicker & tạo báo giá đọc từ config; sửa số không đụng code (luật "không hardcode số
  nghiệp vụ", PLAN_UI Phase 7).
- **B5 — snapshot chỉ freeze đường Estimate:** nhánh "gửi khách" chỉ set `internal_cost_snapshot_json` khi
  `quote.estimate_id` → BG từ PTG **rơi freeze**. Sửa: freeze snapshot giá vốn cho **đường PTG** tại mốc
  chuyển `sent` (Đã duyệt) — từ `PhieuThanhPhan`/`gia_von_tp` đã khóa lúc tạo.

## 9. Bản in (bám mẫu thật, giữ design system SVN)

Không bê nguyên quốc hiệu "CỘNG HÒA…" + lưới Excel thô của mẫu cũ — **giữ letterhead Sao Việt Nhật** + tokens
kem/gạch nung. **Hút đủ field mẫu thật:**
- Dòng **khách hàng + MST**, **người liên hệ (tên · SĐT)**, **ĐC giao hàng**.
- Bảng dòng: STT · **MÃ PO** · Diễn giải (tên + spec) · ĐVT · Số lượng · Đơn giá · Ghi chú · Tổng.
- **3 ô ký:** NV Kinh doanh · Trợ lý · **Phê duyệt** (ô Phê duyệt nối trạng thái đặc thù → Giám đốc KD duyệt).
- Không in trụ sở (đã bỏ §4).

## 10. RBAC — vai Giám đốc Kinh doanh

Cơ chế **đã có**: cờ `can_approve_exception` (tách khỏi `can_approve`), gác endpoint duyệt báo giá
(`require_permission("bao_gia","approve_exception")`) + kèm quyền xem con số biên/giá vốn (router strip số
với người không có quyền). **Thiếu:** vai giữ cờ đang là `Giám đốc` (Ban giám đốc / Admin) — phòng Kinh doanh
chưa có vai duyệt đặc thù. **Thêm vai "Giám đốc Kinh doanh"** → 3 tầng:

| Vai (phòng Kinh doanh) | Scope | Quyền |
|---|---|---|
| **NV Sales** | Của mình | ĐỦ thao tác THƯỜNG trên báo giá của mình (`_full` scope own: gửi khách · ghi nhận Khách đồng ý/từ chối · hủy · xuất PDF · tạo bản mới) + **thấy số biên** (tự set biên khi soạn) + lập **Phiếu tính giá** của mình; **KHÔNG** duyệt đặc thù |
| **Trưởng phòng KD** | Cả phòng | như trên (cả phòng) + **`can_approve_exception`** trên **`bao_gia` + `don_hang_ban`** (duyệt đặc thù báo giá & đơn), điều chuyển khách |
| **Giám đốc Kinh doanh** *(mới)* | Cả phòng / Tất cả | + **`can_approve_exception`** (bao_gia + don_hang_ban) = duyệt "Chờ duyệt→Đã duyệt/Từ chối" |
| *(Giám đốc công ty = Admin)* | Tất cả | super-role — giữ nguyên |

- **Chủ đầu tư chốt (P8):** các thao tác THƯỜNG (gửi/ghi nhận khách đồng ý-từ chối/hủy/PDF/tạo bản mới) **không tách
  quyền vụn — mọi NV kinh doanh đều có** (NV Sales = `_full(SCOPE_OWN)` trên `bao_gia`, KHÔNG `approve_exception`).
  Chỉ **báo giá ĐẶC THÙ** (biên thấp / dưới vốn / giá trị cao) mới bắt buộc **TRÌNH DUYỆT** → gửi tới người có
  `approve_exception` (**TP KD hoặc GĐ KD**). Người duyệt **đồng ý HAY từ chối đều PHẢI nêu lý do** (enforce ở
  `record_approval` + FE). "Gửi báo giá" ≠ "Duyệt đặc thù".
- **Tính giá theo phạm vi (P8, migration 0053):** `phieu_tinh_gia.created_by` (chủ sở hữu) → NV Sales scope "Của tôi"
  chỉ thấy phiếu MÌNH lập; TP KD/GĐ scope phòng/tất cả thấy hết (lọc `list`/`get`/`update`/`delete`, ngoài phạm vi = 404).
  Backfill `created_by` từ `ktv` (khớp name/username) cho dữ liệu cũ.
- Sửa `seed_roles` (`seed.py`): NV Sales `bao_gia`=`_full(SCOPE_OWN)` + `tinh_gia_thanh`=`_rcu(SCOPE_OWN)`; TP KD
  +`can_approve_exception` trên `bao_gia`+`don_hang_ban`. `seed_roles` upsert quyền tại chỗ mỗi lần khởi động → tự
  đồng bộ cả DB prod.

## 11. Bug list (đã re-verify tại HEAD `3844b4d`, 2026‑07‑13)

| # | Bug | Trạng thái | Vá tại § |
|---|---|---|---|
| B1 | Dual path Estimate/PTG | UI đã PTG-only; backend Estimate = dead code chờ dọn | §2 |
| B2 | Link phiếu tính giá ra "—" (chỉ hiểu `estimate_number`) | còn | §6 |
| B3 | Không gán/đổi khách ở detail | còn | §6 |
| B4 | markup 20% / VAT 10% hardcode | còn (`quotation_service.py`) | §8 |
| B5 | snapshot chỉ freeze đường Estimate | còn | §8 |
| B6 | `requote` rơi ref per‑dòng | biến mất khi gỡ requote | §7 |
| B7 | Không khóa `converted_to_order` → tạo nhiều đơn / 1 báo giá | còn | §3 |

## 12. Ràng buộc kỹ thuật & phân pha

**Ràng buộc (CLAUDE.md):**
- KHÔNG Alembic → cột mới viết vào `db_migrations.py`; dev drop `dev.db`; cập nhật `DB_SCHEMA.md` (guard test).
- Boolean `server_default` = `false`/`true`.
- Sửa route/schema → **restart uvicorn**; verify `./init.ps1` (pytest + compileall), dán kết quả thật.
- Backend phân tầng `routers → services → repositories`; logic ở services.

**Phân pha (khi "làm đi"):**
- **P1 — Trạng thái & khóa:** `pending_approval` + máy trạng thái + từ chối duyệt (§3) + khóa
  `converted_to_order` (B7).
- **P2 — Auto-fill & field:** contact/po_code + wire delivery (§4, §5) + gỡ hardcode markup/VAT (B4).
- **P3 — Vá UI detail:** chọn khách + link PTG + MarginPicker per‑dòng (§6).
- **P4 — Bản in:** mẫu thật (§9).
- **P5 — RBAC:** vai Giám đốc Kinh doanh (§10).
- **P6 — Dọn Estimate:** BG‑4 (§2) + freeze snapshot đường PTG (B5).

## 13. Điểm treo / phối hợp

- ⚠️ `frontend/src/pages/BaoGiaPage.tsx` + `bao-gia.css` **đang có sửa chưa commit** (HEAD `3844b4d`) → có
  session/worktree khác đang chạm màn Báo giá. Khi "làm đi" phải đồng bộ trước, tránh giẫm chân.
- Gói biên & ngưỡng đặc thù (1 tỷ / 15%) đã ở `exception_gate` dùng chung Báo giá + Đơn hàng — màn cấu hình
  versioned là việc chung, để pha sau.
- Phí ship theo điểm giao: `CustomerAddress` giờ chỉ dùng điền **ĐC giao**; tính phí = seam Tính giá/Giao
  hàng (`redesign-luong-kinh-doanh` §6), pha sau.
