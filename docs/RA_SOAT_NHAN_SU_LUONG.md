# NHÂN SỰ & LƯƠNG — Tổng hợp chức năng và Rà soát xung đột

**Ngày rà:** 29/07/2026 · **Phạm vi:** module `nhan_su` + `luong`
**Cách rà:** đọc code + truy vết caller + đối chiếu DB thật, **không sửa gì**.

---

# PHẦN A — HỆ THỐNG ĐANG LÀM ĐƯỢC NHỮNG GÌ

## 1. Nhân sự

| Chức năng | Trạng thái |
|---|---|
| Hồ sơ nhân viên — wizard 5 bước (Định danh · Cá nhân · Lương & BHXH · Đính kèm · Tài khoản) | ✅ |
| Quá trình công tác — tự sinh mốc khi đổi trạng thái / chuyển tổ / nâng bậc | ✅ |
| Đính kèm hồ sơ (CCCD, hợp đồng, bằng cấp…) | ✅ |
| Nối / tạo tài khoản đăng nhập cho nhân viên | ✅ |
| Nhân viên tự gửi **yêu cầu cập nhật hồ sơ** → HCNS duyệt mới áp | ✅ |
| Cảnh báo trùng CCCD / số sổ BHXH (mềm, không chặn) | ✅ |
| Điều chuyển · nâng bậc · đổi trạng thái (thử việc → chính thức → nghỉ việc…) | ✅ |

## 2. Chấm công

| Chức năng | Trạng thái |
|---|---|
| Chấm công GPS — chặn cứng ngoài bán kính điểm chấm | ✅ |
| Khai **ca làm việc** (giờ vào/ra, ca qua đêm, dung sai, hệ số ca đêm) | ✅ |
| **Phân ca tháng** — lưới NV × ngày, 3 trạng thái ô (kế thừa / ca riêng / nghỉ) | ✅ |
| **Ca nền** theo mốc hiệu lực + gán hàng loạt cho cả tổ | ✅ |
| Áp nhanh **xoay ca 2-2-2** | ✅ |
| **Lịch sử thay đổi ca** — ai sửa, lúc nào, từ ca nào sang ca nào; phủ **5 đường** ghi | ✅ *mới 29/07* |
| **Thông báo real-time** cho NV bị đổi ca (badge + toast + hộp thư) | ✅ *mới 29/07* |
| Bảng công tháng · công qua nửa đêm · giờ đêm · tăng ca theo loại ngày | ✅ |
| **Đơn chỉnh công** — NV tự gửi, tối đa **5 ngày công/tháng** | ✅ |
| Lịch làm việc & ngày lễ — công chuẩn **động theo tháng** | ✅ |
| Chốt kỳ công (khoá sửa) | ✅ |

## 3. Nghỉ phép · Đi muộn/về sớm · Tăng ca

| Chức năng | Trạng thái |
|---|---|
| Đơn **nghỉ phép** theo loại, có/không lương, trừ quota — **tổ trưởng duyệt trong tổ** | ✅ *mới 29/07* |
| Đơn **đi muộn / về sớm / nghỉ nửa buổi** (module riêng) — có đơn thì không mất chuyên cần | ✅ |
| Đơn **tăng ca** — tổ trưởng duyệt (trong tổ), duyệt cả mẻ | ✅ *lỗ quyền đã vá 29/07 — xem C-2b* |
| Badge + toast real-time cho cả 3 luồng | ✅ |

## 4. Lương

| Chức năng | Trạng thái |
|---|---|
| **Bảng lương tháng** — Tạo → soát → Chốt → Xuất Excel + file chuyển khoản | ✅ |
| **Lương nhân viên** — khai mức theo mốc hiệu lực, giữ lịch sử | ✅ |
| **Tạm ứng** + **lương đợt 1** — duyệt, tự trừ, sàn 0 | ✅ |
| **Danh mục khoản thu nhập** — mỗi khoản một cờ *Chịu thuế*, quy trình 2 bước | ✅ |
| **Gán hàng loạt** khoản cho nhiều NV (lọc tổ, chọn cả nhóm, ô ghi đè) | ✅ *mới 29/07* |
| **Khoản phát sinh tháng này** (thưởng nóng) — không lặp sang kỳ sau | ✅ |
| Phiếu lương chi tiết cho NV tự xem | ✅ |
| **Thuế TNCN** — luỹ tiến 5 bậc · khấu trừ 10% · cam kết 08 | ✅ |
| **BHXH/BHYT/BHTN** 10,5% + 2 mức trần riêng · thử việc không đóng · BH nơi khác | ✅ |
| Chuyên cần trừ dần · phạt đi trễ tự động từ chấm công | ✅ |
| **Trần khấu trừ kỷ luật (Đ102)** — mặc định 30%, khai được, `0` = tắt trần | ✅ *mới 29/07* |
| **Đơn giá khoán** theo tổ, đơn vị gõ tự do + gợi ý | ✅ *mới 29/07* |
| **Thưởng/phạt tổ trưởng** theo bậc lũy tiến tỷ lệ hàng lỗi | ⚠️ **khai được, CHƯA ra tiền** |
| **Tiền khoán theo sản lượng** | ❌ **luôn = 0** |

---

# PHẦN B — XUNG ĐỘT ĐANG ẢNH HƯỞNG TIỀN 🔴

## B-1. Tổ Kho đang mất CẢ tăng ca LẪN khoán

**Bằng chứng:** DB có `departments.has_piece_work = true` cho tổ **Kho**.
`payroll_service.py:815` — `if has_piece_work or not _component_enabled(COMP_TANG_CA): ot_pay = 0.0`.

Logic gốc là *"khoán đã trả theo sản lượng nên thôi tăng ca"*. Nhưng khoán đang = 0 (B-2), nên:

> Người tổ Kho làm thêm giờ **không được trả tăng ca**, và cũng **không có khoán**.
> Họ chỉ còn lương công — **thiệt hơn** người tổ thường.

**Không sửa gì trong lần rà này.** Hai đường xử lý: bỏ tích "Làm khoán" ở tổ Kho (tăng ca chạy lại
ngay), hoặc giữ tích và chấp nhận tới khi mở lại khoán.

## B-2. Tiền khoán luôn = 0 — không có nguồn sản lượng

**Bằng chứng:**
- `PieceWorkService.khoan_map` gọi `self.outputs.list_nguoi_by_period(...)`
- `ProductionOutputRepository` **không tồn tại trong code**; `list_nguoi_by_period` cũng không có ở đâu
- `deps.py:413` — `PieceWorkService(piece)` truyền `outputs=None` ⇒ câu lệnh bị chặn trước khi chạy
- Bảng duy nhất tên giống là `phieu_thanh_pham` — đó là **phiếu tính giá**, không phải sản lượng

⇒ Khai đơn giá khoán, khai mốc thưởng/phạt tổ trưởng — **đều chưa ra tiền**.
Đây là **gốc rễ**: mở lại nguồn sản lượng thì cả khoán lẫn thưởng/phạt tổ trưởng sống lại cùng lúc.

---

# PHẦN C — XUNG ĐỘT VỀ QUYỀN & TÍNH ĐÚNG 🟠

## C-1. Quy tắc lương theo bậc: **khai được nhưng KHÔNG BAO GIỜ áp dụng**

**Bằng chứng:**
- API đầy đủ: `GET/POST/PUT/DELETE /api/luong/rules` (`payroll.py:270-295`)
- Người tiêu thụ duy nhất là `_lookup_rule` (`payroll_service.py:502`)
- **Truy vết caller: KHÔNG AI GỌI `_lookup_rule`** — grep toàn `backend/app/` chỉ ra chính dòng
  định nghĩa
- `_resolve_monthly` ghi thẳng trong docstring: *"Bỏ hẳn nhánh bậc/quy tắc"*

⇒ Ai tạo quy tắc lương theo bậc/thâm niên/giới tính qua API thì **quy tắc đó nằm chết trong DB**.
Đỡ nguy hiểm ở chỗ **frontend chưa có màn nào** cho phần này (chỉ `client.ts` có hàm gọi) — nhưng
API vẫn sống, và ai dựng màn lên là hiểu nhầm ngay.

Liên đới: `employees.pay_grade_key` (bậc chuẩn hoá) cũng **không phơi ra màn nào**.

## C-2. Duyệt tăng ca **KHÔNG kiểm phạm vi** — ✅ ĐÃ VÁ 29/07/2026

> **Đã xử lý.** Chủ báo lại đúng lỗ này; truy ra **bốn** chỗ cùng một bệnh, đã vá cả bốn:
> **tăng ca · nghỉ phép · tạm ứng · YC cập nhật hồ sơ**. Xem mục **C-2b** bên dưới.
> Phần mô tả gốc giữ nguyên để hiểu vì sao lỗi xảy ra.

**Bằng chứng (lúc rà, trước khi vá):**
- `overtime_service.list_requests` / `count_pending` **CÓ** `scope` ⇒ tổ trưởng không *thấy* phiếu tổ khác
- `_decide` (`overtime_service.py:164`) chỉ kiểm *phiếu tồn tại* + *đang chờ* — **không có tham số
  `scope`, không kiểm gì về phạm vi**
- Router gọi `svc.approve(actor=user, request_id=...)` — **không truyền scope**
  (`overtime.py:181, 207, 218`)

⇒ Biết `request_id` là **gọi thẳng API duyệt được phiếu tăng ca của bộ phận khác**. Giao diện có
che, nhưng API thì mở.

Đây là lỗ **quyền ghi**, và tăng ca ra tiền thật.

## C-2b. Đã vá thế nào (29/07/2026)

**Nguyên nhân gốc, nói một câu:** ô quyền `approve` chỉ trả lời *"được duyệt hay không"*, không
trả lời *"được duyệt CHO AI"*. Đường ĐỌC lọc phạm vi nên trên màn không thấy phiếu tổ khác —
nhưng đó là **che mắt, không phải khoá**.

**Chính sách chủ chốt:**

| Luồng | Ai duyệt | Trạng thái sau khi vá |
|---|---|---|
| Tăng ca | Tổ trưởng, **trong tổ** | Chốt phạm vi ở service; router truyền `scope` đủ 4 đường |
| Nghỉ phép | Tổ trưởng, **trong tổ** | **Cấp thêm quyền** (`_leave_lead`) + chốt phạm vi |
| Tạm ứng lương | **Nhân sự** | Quyền vốn đã đúng; thêm lớp khoá dự phòng |
| YC cập nhật hồ sơ | **Nhân sự** | Quyền vốn đã đúng; thêm lớp khoá dự phòng |

**Ba chỗ dễ sót mà việc cấp quyền nghỉ phép cho tổ trưởng làm lộ ra:**

1. **Danh mục loại nghỉ** dùng CHUNG ô quyền `approve` với duyệt đơn ⇒ cấp quyền duyệt là tổ
   trưởng sửa được danh mục loại nghỉ toàn công ty. Đã tách sang ô `update` (ô này trước đó
   không dùng ở module nghỉ phép nên không cướp quyền của ai).
2. **Hủy đơn**: `is_hr=True` trước đây nghĩa là *"hủy BẤT KỲ"* — an toàn khi chỉ HCNS có cờ đó,
   nhưng nay tổ trưởng cũng có. Đã siết về trong phạm vi.
3. **Lịch nghỉ** gác bằng `approve` và không lọc gì ⇒ tổ trưởng đọc được lịch nghỉ cả công ty.
   Đã lọc theo phạm vi.

**Chặn tái phát:** `scope` là tham số **BẮT BUỘC** (bỏ kiểu `scope=None → bỏ qua kiểm tra`, chính
cơ chế đó đã để bốn chỗ thủng mà không ai biết), cộng
`tests/test_duyet_phai_kiem_pham_vi.py` — **tự quét** mọi hàm `approve*`/`reject*`/`decide*` trong
`app/services`, thiếu `scope` là đỏ. Miễn trừ phải khai tay kèm lý do.

## C-2c. 🔴 Chỗ thứ NĂM — Đề nghị kho, CHƯA VÁ (ngoài phạm vi)

Test tự quét ở C-2b **tìm ra ngay lần chạy đầu** một chỗ thứ năm cùng bệnh, nằm ngoài Nhân sự &
Lương nên **cố ý chưa vá** (chủ 30/07: *"tôi bảo sửa phạm vi nhân sự và lương thôi mà"*).

**Thủng ở đâu:** `routers/kho_request.py::_act` — dùng chung cho **trình duyệt · duyệt · từ chối ·
huỷ** — lấy phiếu THẲNG theo id, không kiểm phạm vi. Trong khi:

- `list` CÓ lọc (`_scoped_filters`)
- hàm chặn `_require_visible` **đã có sẵn trong chính file đó**, nhưng chỉ được gọi ở **một chỗ:
  endpoint xem chi tiết**

⇒ Ai có `kho:approve` là duyệt được đề nghị của bộ phận khác chỉ cần biết mã phiếu. Đúng bệnh C-2:
**đọc thì chặn, ghi thì mở**.

**Cách vá:** một dòng — gọi `_require_visible(req, user, authz)` trong `_act`.

### 🔴 Cái bẫy phải biết TRƯỚC khi vá

Vá xong sẽ thấy **10 test của `tests/test_kho_de_nghi.py` đỏ**. Đừng tưởng mình làm sai.

Fixture `t_duyet` trong `_setup()` cho người duyệt scope **`own`** — tổ hợp mà **chính `seed.py`
chú thích là vô nghĩa**:

> *"Scope kho = DEPARTMENT: PHẢI thấy đề nghị của cả phòng SX (do NV tạo) mới duyệt được — scope
> `own` chỉ thấy đề nghị của chính mình nên không có gì để duyệt."*

`own` chỉ thấy phiếu của chính mình, mà tự duyệt thì bị SoD chặn ⇒ **không duyệt được gì**. Mười
test đó chạy được suốt là vì **đang sống nhờ chính lỗ hổng**.

**Xử đúng KHÔNG phải sửa 10 test** mà là sửa **một dòng fixture** về `SCOPE_DEPARTMENT` cho khớp
seed thật ⇒ **23/23 xanh** (đã thử nghiệm 30/07 rồi lùi lại theo yêu cầu chủ).

**Đã kiểm test có răng:** gỡ chốt ra thì kế toán duyệt được phiếu tổ Sản xuất ngay — **200** thay
vì 404.

**Được canh ở đâu:** rổ `LO_CHUA_VA` trong `tests/test_duyet_phai_kiem_pham_vi.py` (tách riêng khỏi
`MIEN_TRU` để không lẫn "an toàn" với "đang thủng"), kèm test ghim danh sách — thêm lỗ mới vào rổ
là test đỏ, buộc phải khai báo có ý thức.

**Chưa siết:** `late_early` vẫn để `scope: str | None = None`. Module đó truyền `scope` đủ mọi
đường nên không thủng — nhưng nên siết cho đồng bộ ở một đợt riêng.

## C-3. HAI trường "bậc thợ" song song, không đồng bộ

| Trường | Kiểu | Ở màn? | Ai dùng? |
|---|---|---|---|
| `employees.job_grade` | Free-text "3/7" | ✅ ô *"Loại / Bậc thợ"* | Chỉ hiển thị + ghi vào Quá trình công tác |
| `employees.pay_grade_key` | Chuẩn hoá `tho_1`… | ❌ không có màn | `_lookup_rule` — **đã chết** (C-1) |

⇒ Người dùng gõ bậc vào ô free-text, tưởng hệ thống hiểu; thực ra **không có gì đọc nó để tính
tiền**. Và trường được thiết kế để tính thì lại không khai được.

Đây chính là chỗ chủ hỏi *"dựa vào bậc tay thợ để chia phần trăm sản lượng"* — hiện **chưa có cơ
chế nào**, và cả hai trường trên đều không dùng được ngay: một cái là chữ tự do, một cái không có
màn và người tiêu thụ đã chết.

---

# PHẦN D — DỞ DANG / NỢ KỸ THUẬT 🟡

## D-1. Hàm/cột đã khai nhưng không ai dùng

| Thứ | Tình trạng | Nguy hiểm? |
|---|---|---|
| `payroll_params.advance_max_pct` | Trần tạm ứng **đã gỡ 24/07**; cột còn, không service nào đọc | Thấp — **không phơi ra màn** |
| `payroll_params.chuyen_can_default` | Mức mặc định công ty **đã bỏ**; chuyên cần chỉ khai theo từng người | Thấp — không phơi ra màn |
| `payroll_params.standard_cong_default` | Chỉ còn là **lưới dự phòng** khi chưa cấu hình Lịch làm việc | Thấp — không phơi ra màn |
| `employees.payroll_group` ("Nhóm lương") | Trơ — PRD v2 bỏ mức mặc định theo nhóm | Thấp — cố ý để ngoài màn |
| `PieceWorkService.leader_bonus_amount` | **Chưa có caller** — chờ nối khi có sản lượng | Thấp — **có test riêng**, cố ý |

> Ba tham số đầu đã được **gỡ khỏi form Cấu hình lương** — người dùng không sửa nhầm được. Đó là
> xử lý đúng: cột dormant mà vẫn cho sửa mới là bẫy.

## D-2. `dieu_chinh_luong` — engine cộng nhưng KHÔNG có ô nhập

- Engine cộng vào `gross` (`payroll_service.py:845`), phiếu lương đã có dòng riêng (sửa 28/07)
- API `LineUpdateIn` nhận được
- **Frontend không có ô nhập nào** — chỉ xuất hiện ở phần render phiếu

⇒ Muốn điều chỉnh lương ±, hiện phải gọi thẳng API. Không sai số, chỉ là thiếu đường vào.

## D-3. Năm lỗi TypeScript có sẵn — của phiên khác

`AppShell.tsx:104-105` (`sxTick`, `setSxTick`, `toSxRef`) và `ChamCongPage.tsx:87, 3276`
(`Repeat`, `openQuickFill`) — biến khai rồi không dùng. `npm run build` **đang đỏ**; verify bằng
`npx tsc --noEmit`. **Không phải phần Nhân sự & Lương**, tôi không đụng.

## D-4. `SEED_DEMO` đang TẮT

`backend/.env` — tôi tắt ngày 28/07 để dọn DB test từ đầu. **Bật lại `true` là toàn bộ dữ liệu demo
mọc lại** vào DB đang có (seed chạy mỗi lần khởi động app).

---

# PHẦN E — KHÔNG PHẢI XUNG ĐỘT (đã kiểm, đang đúng)

Những cặp dễ tưởng là mâu thuẫn nhưng thực ra đã xử lý:

| Cặp | Vì sao KHÔNG xung đột |
|---|---|
| `phep_nam` (cột tay) vs `luong_ngay_phep` (tự tính) | Cột tay **đã khai tử 28/07**, API không nhận; `_RESERVED` chặn cả việc tạo khoản danh mục trùng tên ⇒ hết đường trả hai lần |
| 6 cột thưởng cũ vs khoản danh mục | Cột cũ **ngừng ghi**, vẫn cộng để kỳ ĐÃ CHỐT giữ nguyên số; migration 0124 đã dời kỳ nháp |
| Drawer *"Lịch sử ca"* vs khối lịch sử | **Đã gộp 29/07** — khối C độc lập đã bỏ, lịch sử nằm trong drawer từng người |
| `employees.default_shift_id` vs `employee_shift_assignments` | `default_shift_id` là **cache tương thích**; `set_shift_assignment` ghi cả hai cùng lúc |
| Khoản `source='employee'` vs `source='line'` | **Đã vá lỗi cộng đôi 28/07** — `allowance` chỉ nuốt phần hồ sơ, phần phát sinh cộng riêng; có test hồi quy |
| Trần Đ102 vs khoản khấu trừ danh mục | Cố ý tách: trần dành cho **bồi thường/kỷ luật**; khấu trừ thoả thuận (mua đồng phục) nằm ngoài |

---

# PHẦN F — BẢNG TRA NHANH THAM SỐ (2026)

| Tham số | Giá trị | Sửa được ở màn? |
|---|---|---|
| Công chuẩn/tháng | **Động theo Lịch làm việc** (26 = dự phòng) | Lịch & Ngày lễ |
| Lương thử việc | 80% | ✅ |
| BHXH · BHYT · BHTN (NLĐ) | 8% · 1,5% · 1% = **10,5%** | ✅ |
| Trần đóng BHXH+BHYT | 50.600.000đ | ✅ |
| Trần đóng BHTN | 106.200.000đ | ✅ |
| Giảm trừ bản thân · người phụ thuộc | 15.500.000đ · 6.200.000đ | ✅ |
| Thuế TNCN | 5 bậc: 10/30/60/100tr @ 5/10/20/30/35% | ✅ |
| Tăng ca thường · CN · lễ | 150% · 200% · 300% | ✅ |
| Phụ cấp đêm · tăng ca đêm | +30% · +20% | ✅ |
| Số lần chỉnh công | 5 ngày/tháng | ✅ |
| Đoàn phí công đoàn | **0%** — hiện không trừ ai | ✅ |
| Trần khấu trừ kỷ luật (Đ102) | **30%** — mức LUẬT, `0` = tắt trần | ✅ *mới 29/07* |
| Trần tạm ứng | **Đã gỡ** — không còn giới hạn | — |

---

# PHẦN G — THỨ TỰ ĐỀ XUẤT XỬ LÝ

Không tự làm gì; đây là gợi ý thứ tự nếu chủ muốn tiếp.

| # | Việc | Vì sao trước |
|---|---|---|
| 1 | **Quyết tổ Kho** (B-1) | Đang mất tiền tăng ca **ngay tháng này**. Bỏ tích là xong trong 1 phút |
| ~~2~~ | ~~**Vá lỗ quyền duyệt tăng ca** (C-2)~~ | ✅ **XONG 29/07** — vá cả 4 luồng, xem C-2b |
| 3 | **Dựng lại nguồn sản lượng** (B-2) | Việc lớn nhất, mở khoá khoán + thưởng/phạt tổ trưởng + chia theo bậc |
| 4 | **Bậc thợ có hệ số** (C-3) | Phụ thuộc #3 — có sản lượng rồi mới chia được |
| 5 | Dọn `salary_rate_rules` (C-1) | Hoặc nối lại `_lookup_rule`, hoặc gỡ API để khỏi ai hiểu nhầm |
| 6 | Ô nhập `dieu_chinh_luong` (D-2) | Tiện dụng, không gấp — engine đã cộng, API đã nhận, chỉ thiếu đường vào từ màn |

---

**Ghi chú cuối:** phần **rà** trong tài liệu này không sửa một dòng code nào. Sau khi rà xong,
chủ yêu cầu bỏ chỗ viết cứng `0.30` trong engine ⇒ trần khấu trừ kỷ luật **đã thành tham số khai
được** (mặc định vẫn 30%, không đổi hành vi cũ). Đó là thay đổi DUY NHẤT phát sinh từ đợt rà này;
mọi phát hiện B/C/D khác vẫn **nguyên trạng, chưa đụng vào**. Mọi khẳng định ở
Phần B/C đều có dẫn chứng file:dòng và đã truy vết caller, không suy đoán.
