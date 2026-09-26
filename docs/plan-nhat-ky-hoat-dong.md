# Kế hoạch — màn Nhật ký hoạt động (`activity_log`)

Rà ngày 25/09/2026. Phạm vi soi: `GET /api/audit` → `ActivityService` → `AuditLogRepository` →
bảng `audit_logs`, màn `frontend/src/pages/ActivityLogPage.tsx`, ô quyền `activity_log` trong ma
trận, và những chỗ ĐÃ CÓ SẴN mà màn này chưa dùng (`catalog_registry`, `nhat_ky_danh_muc`, hub SSE).

Trạng thái: BÀN THIẾT KẾ. Chưa đụng code.

---

## 1. Kết luận một câu

Màn Nhật ký hiện là một **ảnh chụp 100 dòng cuối** được trang trí rất kỹ ở trình duyệt: mọi bộ lọc,
phân trang, xuất CSV đều chạy trên đúng 100 dòng đó. Ngoài chuyện thiếu lọc theo khoảng ngày, còn
**15 khoảng trống khác** — trong đó ba cái đụng tới tính tin cậy của chính vết audit (xoá người là
mất vết, không ghi đăng nhập, không ghi IP), và hai cái là "ô quyền nói dối".

---

## 2. Phát hiện

### 2.1 Nhóm A — máy chủ (gốc của mọi thứ)

| # | Phát hiện | Bằng chứng |
| --- | --- | --- |
| A1 | `GET /api/audit` **không nhận tham số nào**; trần cứng 100 dòng. Dòng thứ 101 trở đi không có đường nào lấy ra từ UI. | `routers/rbac.py:111`, `services/activity_service.py:14`, `repositories/audit_repo.py:77` |
| A2 | Không trả **tổng số bản ghi** ⇒ màn không thể nói "đang xem 25 / 48.120". | cùng trên |
| A3 | Không lọc theo **khoảng ngày**, theo **hành động**, theo **người thao tác**, không **tìm chuỗi** ở máy chủ. | cùng trên |
| A4 | **Scope của `activity_log` không ai đọc.** `require_permission` chỉ kiểm cờ boolean; endpoint trả toàn bộ bất kể vai được cấp phạm vi gì. Mà khoá này **không** nằm trong `SCOPELESS_MODULES` và **không** nằm trong `PHAM_VI_CHO_PHEP` ⇒ ma trận bày đủ ba lựa chọn "Của tôi / Cả phòng / Tất cả", chọn gì cũng như nhau. | `deps.py:635`, `services/role_service.py:51`, `components/PermissionMatrix.tsx:734,850` |
| A5 | **Không có ô quyền riêng cho việc XUẤT.** Ai mở được màn là tải được toàn bộ nhật ký, và **bản thân việc xuất không ghi lại một dòng audit nào** — trong khi màn Báo cáo kho đã làm đúng việc này (`kho_export`). | `routers/kho_baocao.py:831` |
| A6 | **Không ghi đăng nhập / đăng xuất / đăng nhập thất bại.** Đặt lại mật khẩu (`reset_password`), thu hồi phiên (`revoke_sessions`), khoá/mở tài khoản đều có dòng audit — riêng sự kiện truy cập thì trống. Một màn tên "audit trail" mà không biết ai đã vào hệ thống. | `routers/auth.py` không gọi `AuditLogRepository` |
| A7 | **Không có IP / thiết bị.** Bảng chỉ có `actor_user_id`, `action`, `target`, `detail`, `created_at`. | `models/audit.py` |
| A8 | **FK `actor_user_id → users.id` đang `ON DELETE CASCADE`.** Hôm nay chưa có endpoint xoá user nên chưa nổ, nhưng ngày ai đó thêm "xoá tài khoản" thì **toàn bộ vết của người đó biến mất im lặng** — đúng người cần soi nhất. Nhật ký phải sống lâu hơn người. | `models/audit.py:30` |
| A9 | **`actor_name` tra tại lúc đọc, không phải ảnh chụp.** Người đổi tên thì nhật ký cũ đổi theo. Và `actor_user_id = NULL` hiển thị "Hệ thống" — lẫn giữa seeder, tác vụ nền và "không rõ ai". | `services/activity_service.py:17-23` |
| A10 | **Nhật ký không append-only.** `create_collapsing` gộp thao tác lặp bằng cách **ghi đè `created_at` + `detail` của dòng cũ** — dòng nhảy vị trí thời gian. Cố ý (chống phình khi lưu nháp), nhưng phải biết rõ nó áp cho action nào trước khi chọn kiểu phân trang. | `repositories/audit_repo.py:39-66` |
| A11 | **Index chỉ đủ cho hai câu hỏi hiện có**: `created_at` (liệt kê theo thời gian) và `(target, created_at)` (tab Nhật ký từng bản ghi, mg `0301`). Lọc theo `action` / `actor_user_id` và tìm chuỗi trong `detail` sẽ **quét cả bảng** — mà chính migration `0301` đã ghi đây là "bảng phình nhanh nhất hệ". | `models/audit.py:25`, `db_migrations.py:13669` |
| A12 | **Không có chính sách lưu giữ / dọn.** Bảng chỉ lớn lên, không ai xoá, không archive. | không có mã nào xoá `audit_logs` |
| A13 | **Không có danh mục hành động do máy chủ cấp.** Backend đang ghi **231 mã action** khác nhau; FE tự khai tay **16**. | `grep 'action="…"'` = 231 mã duy nhất; `ActivityLogPage.tsx:44-150` = 16 khoá |
| A14 | **Không lọc được theo LOẠI đối tượng.** 11 màn danh mục dùng chung đúng ba mã `dm_tao`/`dm_sua`/`dm_xoa`, khác nhau chỉ ở `target = "{loai}:{id}"` ⇒ lọc theo hành động vô dụng với cả khối danh mục. | `services/nhat_ky_danh_muc.py:33-35` |
| A15 | **Test gần như trống**: đúng 2 ca — một action hiện ra trong danh sách, và 403 khi thiếu quyền. Không có ca nào cho lọc / phân trang / xuất. | `backend/tests/test_rbac_activity_api.py` |

### 2.2 Nhóm B — giao diện

| # | Phát hiện | Bằng chứng |
| --- | --- | --- |
| B1 | Bốn chip nhóm đều **0** trong khi "Tất cả" là 100: mã lạ rơi vào nhóm `other`, mà màn **không render tab "Khác"**. `categoryCounts.other` được tính rồi bỏ không dùng. | `ActivityLogPage.tsx:336-345`, `:605-655` |
| B2 | **215/231 mã hiện nhãn tiếng Anh tự sinh** ("Employee Create Account", "Payroll Set Salary") giữa UI tiếng Việt — hàm fallback title-case mã snake_case. | `ActivityLogPage.tsx:151-166` |
| B3 | `target` hiện **thô** dạng `employee:84`, không dịch ra tên bản ghi và **không bấm sang được**. Trong khi `catalog_registry` đã khai sẵn `loai → module → nhãn → path` đúng cho mục đích này. | `ActivityLogPage.tsx:742`, `catalog_registry.py:28-42` |
| B4 | Modal chi tiết có khối **"Dữ liệu thô (JSON Payload)"** + nút "Copy JSON" — ngôn ngữ lập trình viên đặt giữa màn nghiệp vụ, và lặp lại đúng bốn ô ngay phía trên. | `ActivityLogPage.tsx:975-990` |
| B5 | Modal **không đóng bằng Esc**, không `role="dialog"`, không bẫy focus. | không có `keydown`/`aria-` trong file |
| B6 | Chế độ Bảng **không sắp xếp được theo cột** (thứ tự cố định mới→cũ). | `ActivityLogPage.tsx:790-855` |
| B7 | Badge **"Đồng bộ Live"** là chữ trang trí: file không có `EventSource` lẫn `setInterval`, chỉ nạp một lần lúc mở màn. Trong khi hạ tầng SSE **đã có sẵn** và đang chạy thật cho luồng duyệt báo giá. CLAUDE.md: gửi/thông báo nội bộ = real-time. | `ActivityLogPage.tsx:474`, `routers/quotations.py:412-450` |
| B8 | Dropdown "Tất cả người thao tác" và "Tất cả hành động" **sinh từ chính 100 dòng đã tải** ⇒ người/hành động không có mặt trong 100 dòng cuối thì không tồn tại để chọn. | `ActivityLogPage.tsx:328-333` |
| B9 | **Không có URL state**: chọn xong bộ lọc không gửi link cho người khác được, F5 là mất. | không đọc/ghi query string |

### 2.3 Nhóm C — tài liệu

| # | Phát hiện | Bằng chứng |
| --- | --- | --- |
| C1 | `docs/DB_SCHEMA.md` ghi `actor_user_id` là "FK→users.id" trơn, **không nói CASCADE** — đọc tài liệu không thấy được rủi ro A8. | `docs/DB_SCHEMA.md:948` |

---

## 3. Bốn quyết định cần chốt trước khi làm

1. **Nhật ký có che tiền không?** `detail` đang chứa số tiền thật: `"giá gốc 27.800 → 29.000 đ/kg"`
   (`kho_gia_goc_service.py:92`), `"HĐ… <- đơn…: 45.000.000đ"` (`accounting_service.py:1321`),
   `"Đơn giá giờ máy mới: … VND/h"` (`machine_service.py:246`). Ai có ô Nhật ký là đọc hết, kể cả
   người không có quyền vào những màn đó. Việc này va vào luật "tiền chỉ người có quyền xem".
   Hai đường: (a) coi Nhật ký là quyền quản trị, chấp nhận — cấp cho rất ít người; (b) lọc dòng
   theo quyền module của người xem (làm được nếu có danh mục action → module ở mục 4.2).
2. **Phạm vi**: ép `all` (đưa `activity_log` vào `SCOPELESS_MODULES`, ô hiện mờ) hay thực thi thật
   (`own` = việc do chính mình làm, `department` = người cùng phòng)? Cách nào cũng được, nhưng
   phải chọn — để nguyên là ô quyền nói dối.
3. **Giữ bao lâu?** Không chốt thì bảng lớn vô hạn, và mọi con số hiệu năng ở mục 4 vô nghĩa.
4. **Có ghi IP / thiết bị không?** Ghi thì thêm 2 cột + migration + DB_SCHEMA; không ghi thì nói rõ
   để khỏi ai đó lại đặt câu hỏi này sau.

---

## 4. Thiết kế đề xuất

### 4.1 Hợp đồng API mới

```
GET /api/audit
  q            chuỗi tìm (khớp detail · target · tên người)
  tu_ngay      ISO date, mặc định = den_ngay - 30 ngày
  den_ngay     ISO date, mặc định = hôm nay
  action       lặp nhiều lần (action=dm_sua&action=create_order)
  loai         lặp nhiều lần — tiền tố của target ("employee", "giay"…)
  actor_id     lặp nhiều lần
  limit        ≤ 200, mặc định 50
  cursor       con trỏ keyset "created_at|id" của dòng cuối trang trước
→ { items: [...], total: int, cursor_tiep: str | null }
```

Chọn **keyset** thay vì offset: bảng nhận dòng mới liên tục, offset làm trang sau lặp/nhảy dòng.
Lưu ý A10 — `create_collapsing` có thể đẩy một dòng cũ lên đầu; chấp nhận (dòng xuất hiện hai lần
trong một phiên duyệt là chuyện nhỏ hơn việc bỏ sót dòng).

`total` tính riêng bằng `COUNT(*)` cùng bộ lọc, chỉ khi trang đầu — không đếm lại mỗi lần lật trang.

### 4.2 Danh mục hành động ở máy chủ (`audit_registry.py`)

Đây là **việc lớn nhất và là chìa khoá cho 5 phát hiện khác** (A4-tiền, A14, B1, B2, và lọc theo
nhóm). Một bảng khai tĩnh, cùng tinh thần `catalog_registry`:

```
HanhDong(ma="create_order", nhan="Tạo đơn hàng", nhom="kinh_doanh", module="don_hang_ban")
```

- `nhan` → hết nhãn tiếng Anh tự chế (B2).
- `nhom` → chip nhóm có ý nghĩa, đếm ở máy chủ (B1).
- `module` → nếu chốt phương án (b) ở mục 3.1 thì đây là chỗ gate dòng theo quyền người xem.
- `GET /api/audit/actions` trả danh mục này cho FE ⇒ dropdown đầy đủ 231 mã chứ không phải chỉ
  những mã tình cờ có trong trang hiện tại (B8).

Khai 231 mã là việc tay, chia theo phân hệ. Có guard test: mọi mã `action="…"` trong `app/` phải
có mặt trong registry, thiếu là `init` đỏ — cùng khuôn với guard `DB_SCHEMA.md`.

Riêng khối danh mục: `dm_tao`/`dm_sua`/`dm_xoa` khai một lần, nhãn ghép thêm loại lấy từ
`catalog_registry` (`"Sửa danh mục · Giấy"`).

### 4.3 Index cần thêm

- `(action, created_at)` — lọc theo hành động.
- `(actor_user_id, created_at)` — lọc theo người.
- Tìm chuỗi trong `detail`: **không** làm `ILIKE '%q%'` trần trên bảng lớn nhất hệ. Hai đường —
  (i) bắt buộc kèm khoảng ngày (mặc định 30 ngày) để Postgres cắt bằng index `created_at` trước;
  (ii) nếu vẫn chậm thì `pg_trgm` + GIN. Chọn (i) trước, đo rồi mới tính (ii).

Tên index đặt trùng đúng tên `create_all` sinh ra cho `index=True` ở model — bài học mg `0287`,
đã ghi ngay trên `_INDEX_0301`.

### 4.4 Toàn vẹn vết audit

- FK đổi `ON DELETE CASCADE` → **`ON DELETE SET NULL`**, kèm cột mới `actor_name_luc_do` (ảnh chụp
  tên lúc ghi). Giải quyết A8 + A9 cùng lúc. Migration phải `ALTER TABLE … DROP CONSTRAINT … ADD
  CONSTRAINT`, và cập nhật `DB_SCHEMA.md` cùng lúc (C1).
- Hai cột `ip` · `user_agent` nếu chốt ở mục 3.4.
- Ghi audit cho `login` · `logout` · `login_that_bai` (A6) và `audit_export` (A5).

---

## 5. Các đợt thực hiện

Mỗi đợt tự đứng được, verify xong mới sang đợt sau.

**Đợt 1 — máy chủ thành nguồn sự thật.** Hợp đồng API 4.1 + index 4.3. Chưa đụng FE (màn cũ vẫn
chạy vì tham số đều có mặc định). Test: lọc từng chiều, lọc chồng, keyset không lặp/không sót,
mặc định 30 ngày, `limit` bị chặn trần.

**Đợt 2 — danh mục hành động.** `audit_registry.py` + `GET /api/audit/actions` + guard test 231 mã.
Khai nhãn theo phân hệ, mỗi phân hệ một lượt để review được.

**Đợt 3 — FE nối lại.** Bỏ toàn bộ lọc/phân trang/CSV trong bộ nhớ; ô chọn khoảng ngày thật; chip
nhóm lấy count từ máy chủ (kèm "Khác"); dịch `target` + link mở bản ghi qua `catalog_registry`;
URL state; bỏ khối JSON thô; Esc + `role="dialog"`. Xác minh bằng dev-browser theo đúng luồng thật.

**Đợt 4 — xuất CSV đúng nghĩa.** `GET /api/audit/export` cùng bộ lọc, `StreamingResponse` (không
dựng cả file trong RAM), ô quyền riêng, và ghi một dòng `audit_export`.

**Đợt 5 — real-time.** Tái dùng hub SSE sẵn có. **Không** tự chèn dòng mới vào danh sách đang đọc —
hiện băng "Có N bản ghi mới · Xem" ở đầu, bấm mới nạp. Badge "Đồng bộ Live" khi đó mới đúng chữ.

**Đợt 6 — toàn vẹn + tài liệu.** FK `SET NULL` + `actor_name_luc_do` + (tuỳ chốt) IP/thiết bị +
audit đăng nhập/đăng xuất; cập nhật `DB_SCHEMA.md`.

**Đợt 7 — lưu giữ.** Chỉ làm khi chốt được mục 3.3.

---

## 6. Bẫy đã biết khi làm

- **Không có Alembic.** Mọi cột/index/FK mới phải viết vào `db_migrations.py` thì DB dev và prod mới
  nhận; `create_all` chỉ tạo bảng, không ALTER. Dev cũng là Postgres.
- **Đổi FK trên Postgres** phải DROP rồi ADD constraint; tên constraint do Postgres tự đặt, phải tra
  `information_schema` chứ đừng đoán.
- **`DB_SCHEMA.md` có guard test** — thêm cột mà quên ghi là `init` đỏ.
- **Migration cấm ORM full-select** khi backfill `actor_name_luc_do`: dùng raw SQL đích danh cột.
- **Sửa route/schema backend → restart uvicorn**, ở đây hot-reload không đáng tin.
- Ô chọn ngày: nhớ `min`/`max` cho `date`/`datetime-local`, không thì gõ nhầm ra năm 6 chữ số và
  nhận 422 câm.

---

## 7. Đã làm — chốt lại so với kế hoạch (25/09/2026)

Đợt 1 → 6 đã xong và đã xác minh bằng UI thật. Ba chỗ LỆCH kế hoạch, ghi ở đây để không phải đọc
ngược lịch sử:

**7.1 FK `actor_user_id` GIỮ `ON DELETE CASCADE` — không đổi sang `SET NULL` như mục 4.4.**
`backend/tests/test_user_fk_cascade.py` bắt buộc MỌI khoá ngoại trỏ `users.id` phải là CASCADE
(111/111 cột; các migration `0327`/`0328`/`0335` sinh ra chỉ để giữ luật này). Đổi riêng một cột là
đá thẳng vào luật đó, nên không tự quyết. Phần A9 vẫn làm trọn: cột `actor_name_luc_do` chụp tên
người thao tác ngay lúc ghi, nên đổi tên hay xoá tài khoản thì DÒNG CŨ VẪN NÓI ĐÚNG TÊN LÚC ĐÓ.
Rủi ro còn lại — xoá tài khoản là mất luôn các dòng nhật ký của người đó — đã ghi cảnh báo vào
`docs/DB_SCHEMA.md`. **Cần người quyết**: hoặc mở ngoại lệ cho `audit_logs` trong guard test rồi
chuyển `SET NULL`, hoặc chấp nhận CASCADE và coi việc xoá tài khoản là thao tác cấm.

**7.2 Đợt 7 (lưu giữ / xoá dòng cũ) CỐ Ý KHÔNG LÀM.** Xoá dữ liệu audit cần thẩm quyền riêng, không
nằm trong phạm vi "lọc + phân trang + nhãn". Mục 3.3 vẫn để ngỏ.

**7.3 `activity_log` là module KHÔNG PHẠM VI** (`SCOPELESS_MODULES`). Nhật ký không có "của tôi" —
scope `own` ở đây vô nghĩa và sẽ đẻ ra một hàng rào giả. Việc che dòng làm bằng đường khác: dòng nào
`audit_registry` biết thuộc màn nào mà người xem không mở được màn ấy thì ẩn, và **đếm số dòng bị ẩn
rồi nói ra** (băng vàng) chứ không nuốt im lặng.

Ngoài kế hoạch, ba lỗi phát hiện khi thao tác thật và đã vá cùng đợt:

- Nút nhanh đếm HỞ: "Hôm nay" ra khoảng `hôm qua → hôm nay`. Nay đếm BAO GỒM hôm nay.
- Có lọc mà vẫn ra kết quả thì không có đường lùi — nút "Đặt lại" chỉ nằm ở màn rỗng. Nay nút nằm
  ngay hàng lọc, hiện khi có bất kỳ bộ lọc nào (kể cả khoảng ngày khác mặc định).
- **URL state (đợt 3) ĐÃ GỠ.** Màn từng ghi bộ lọc ra `?nk_*` để F5 không mất và chia sẻ link
  được. Nhưng app không có router: AppShell điều hướng bằng state, URL luôn đứng yên ở `/`, và
  chính nó xoá hash deep-link QR ngay sau khi dùng vì "URL không còn đại diện cho màn đang
  mở". Ghi `?nk_*` là ngược lệ đó — tham số nằm lại khi sang màn khác rồi tự bật lại bộ lọc
  lúc quay về. Nay bỏ hẳn: vào màn là 30 ngày gần nhất, giống mọi màn còn lại.
- Nút "Xuất CSV" hiện cho cả người không có ô quyền `can_export`; bấm vào 403 câm. Nay ẩn nút,
  máy chủ vẫn là cổng thật.
