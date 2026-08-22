# PRD — Danh mục khoản thu nhập & thu nhập chịu thuế TNCN (27/07/2026)

> Nguồn sự thật: 2 file kế toán đang dùng thật —
> `lương thuế T 05.2026.xlsx` (7 sheet, 118 người) và `BẢNG LƯƠNG T05.2026 (duyệt).xlsx` (68 sheet).
> Mọi con số trong tài liệu này lấy trực tiếp từ đó, không phải giả định.

## 1. Vì sao làm

Chủ nêu 3 việc:

1. **Cấu hình được khoản nào chịu thuế TNCN, khoản nào không.** *"Họ muốn có danh mục list các mục
   đóng thuế; tích vào thì cái đó chịu thuế, không tích thì thôi; và họ có thể thêm hoặc xoá."*
2. **Hiển thị tổng thu nhập chịu thuế và tổng lương thực nhận.**
3. **Chỗ khai hồ sơ nhân sự, mục "các khoản phụ cấp khác" đang phải điền một cục tổng.**

Việc 3 chính là gốc rễ của việc 1. ERP đang gộp mọi phụ cấp vào MỘT ô
(`employee_salaries.allowance`, chú thích trong code: *"Phụ cấp KHÁC (gộp: xăng/điện thoại/kiêm
nhiệm…)"*). Vì gộp một cục nên engine thuế (`payroll_service._auto_pit`) chỉ miễn được **tăng ca +
ca đêm** — hai khoản duy nhất còn tách được. Mọi phụ cấp khác bị tính thuế hết, không có đường nào
để phân biệt.

Trong khi đó kế toán phân loại rất chi tiết. Đối chiếu 118 dòng sheet `TÍNH THUẾ TNCN`:

| Nhóm | Các khoản |
|---|---|
| **MIỄN thuế** | Trang phục · Trợ cấp tiền nhà · Hỗ trợ chi phí đi lại · Tiền ăn ca/CN/GH · Thêm giờ 150H · Thêm NCCN 200H |
| **CHỊU thuế** | Chuyên cần · lương vị trí · lương sản lượng · các khoản thưởng · và phần còn lại |

**Hệ quả bằng tiền:** chạy bảng lương tháng 5/2026 trên ERP hiện tại thì TNCN **thu thừa khoảng
485.000đ/tháng** so với bảng kế toán (≈5,8 triệu/năm), vì trang phục / tiền nhà / đi lại / tiền cơm
đều bị tính thuế oan.

## 2. Chốt của chủ

| # | Quyết định | Ghi chú |
|---|---|---|
| 1 | **Danh mục khoản thu nhập có ô tích "Chịu thuế"** — HCNS tự thêm / xoá / bật tắt | cốt lõi |
| 2 | **Mặc định theo NHÓM LƯƠNG** (`payroll_group`) | KHÔNG theo chức vụ: ô `employees.position` là chữ tự do, gõ lệch một khoảng trắng thành vị trí khác |
| 3 | **Miễn toàn bộ, KHÔNG áp trần luật** | giữ đúng cách file Excel đang chạy — rủi ro ở mục 7 |
| 4 | **Giữ nguyên 2 ô lương trong hồ sơ** | "Lương cơ bản (đóng BH)" vẫn vừa là gốc đóng BH vừa là phần cứng mức nền |

**Về quyết định 4:** file `BL CT` giữ **ba** con số lương riêng cho mỗi người — `Lương BHXH 2026`
(6.841.000) · `Lương vị trí` (5.400.000) · `Trách Nhiệm` (2.700.000), và đã kiểm **97/97 người cả
ba đều khác nhau**. Nhưng đó là dấu vết của thời làm tay. Lên hệ thống thì gộp còn hai, đúng như
`docs/prd-cau-hinh-luong.md` (v2.2, 20/07) đã chốt: *"Lương vị trí = lương cơ bản = MỨC ĐÓNG BH"*,
và tài liệu đó ghi sẵn số 6.841.000 của chính chị Phan Thị Huệ.
⇒ **Phần lương/bảo hiểm KHÔNG phải sửa gì trong đợt này.**

## 3. Thiết kế

### 3.1 Danh mục khoản thu nhập — bảng mới `payroll_components`

Mỗi khoản là một dòng cấu hình. HCNS tự quản, không cần lập trình viên:

| Cột | Ý nghĩa |
|---|---|
| `code` · `name` | mã + tên hiện trên phiếu lương (vd `trang_phuc` · "Trang phục") |
| `kind` | `thu` (cộng vào tổng lương) hoặc `tru` (khấu trừ) |
| **`is_taxable`** | **có tính vào thu nhập chịu thuế TNCN hay không** — chính là ô tích chủ yêu cầu |
| `in_insurance_base` | có cộng vào gốc đóng BH không (mặc định **không**) |
| `sort_order` · `is_active` | thứ tự hiện trên phiếu + bật/tắt |

Seed sẵn đúng danh mục trong file của chủ (15 khoản thu + 6 khoản trừ), gắn cờ `is_taxable` theo
đúng bảng ở mục 1.

**Thêm / xoá:**
- **Thêm** — nút "+ Thêm khoản": gõ tên, chọn Thu/Trừ, tích hay không tích "Chịu thuế". Xong là
  khoản đó hiện ngay ở hồ sơ nhân sự và trên phiếu lương.
- **Xoá** — khoản **chưa từng dùng ở kỳ lương nào** thì xoá hẳn. Khoản **đã dùng rồi** thì hệ thống
  KHÔNG cho xoá cứng, chỉ chuyển sang **Ngưng dùng** (`is_active = false`): biến mất khỏi mọi form
  nhập mới, nhưng phiếu lương và bảng lương các kỳ CŨ vẫn hiện đúng số đã trả.
  > *Vì sao chặn: xoá cứng một khoản đã nằm trong kỳ đã chốt thì phiếu lương cũ mất dòng, tổng không
  > còn khớp chữ ký người nhận — sai lệch không ai truy ngược ra được.*

  Thông điệp nói thẳng: *"Khoản này đã dùng ở N kỳ lương nên chỉ ngưng dùng được, không xoá."*
- **Đổi cờ "Chịu thuế"** chỉ ảnh hưởng kỳ tính **từ đó về sau**; kỳ đã chốt giữ nguyên số cũ.

### 3.2 Giá trị: mặc định theo NHÓM LƯƠNG, đè theo NGƯỜI

- `payroll_group_components` — mức mặc định của từng khoản cho từng nhóm lương. Thêm người mới vào
  nhóm là tự có đủ phụ cấp, không phải gõ lại 15 ô.
- `employee_salary_components` — giá trị riêng của từng người; có thì **ĐÈ** mặc định nhóm.

Tái dùng đúng khuôn `payroll_rules` đang chạy (tra theo `payroll_group`, có `effective_from`).

### 3.3 Engine — `payroll_service`

- Gốc đóng bảo hiểm: **KHÔNG đổi** (vẫn `luong_vi_tri`). Trần BHXH/BHTN giữ nguyên.
- `_auto_pit` đổi chữ ký: thay vì trừ cứng `ot_pay + night_pay + night_premium_pay`, nhận
  **`exempt_total`** = Σ các khoản có `is_taxable = false`. Tăng ca và ca đêm trở thành 2 dòng danh
  mục `is_taxable = false` — hết hard-code, và chủ tự bật tắt được nếu luật đổi.
- Thêm 2 cột snapshot trên `payroll_lines`: `thu_nhap_chiu_thue` và `thu_nhap_mien_thue` — vừa để
  giải trình, vừa để phiếu lương hiện được (việc 2).

### 3.4 Màn hình

| Màn | Thay đổi |
|---|---|
| **Hồ sơ nhân sự** | Thay ô "Các khoản phụ cấp khác" (một cục) bằng **danh sách từng khoản**, mỗi dòng có chip `Chịu thuế` / `Miễn thuế` ngay cạnh số tiền. Ô cũ giữ ở chế độ chỉ-đọc nếu còn số liệu, kèm nhắc tách ra. |
| **Cấu hình lương** | Thêm tab **Danh mục khoản thu nhập**: bảng khoản + cột `Chịu thuế` bật/tắt + bảng mức mặc định theo nhóm lương. Gộp vào màn đã có, không dựng màn mới. |
| **Phiếu lương** | Thêm 2 dòng tổng: **Tổng thu nhập chịu thuế** và **Thực nhận** (việc 2). Bố cục 2 cột "Các khoản thu / Các khoản trừ" bám mẫu `PHIEU LUONG CT` kế toán đang phát cho công nhân. |
| **Bảng lương** | 2 cột mới tương ứng, xuất Excel kèm theo. |

## 4. Việc KHÔNG làm

- Không áp trần miễn thuế (chốt 3).
- Không đụng **bảng thuế TNCN** — ERP đã đúng 5 bậc 2026 (10/30/60/100 triệu — 5/10/20/30/35%), đã
  đối chiếu khớp sheet bằng 3 người có thu nhập tính thuế trên 5 triệu.
- Không đụng **giảm trừ gia cảnh** — 15.500.000 / 6.200.000 đã khớp.
- Không đụng **trần BHXH 50,6tr / BHTN 106,2tr** — cả xưởng không ai chạm tới (cao nhất 10.496.000).
- Không đụng **gốc đóng bảo hiểm** (chốt 4).
- **Không trừ đoàn phí công đoàn vào thu nhập tính thuế.** Sheet kế toán CÓ trừ, nhưng luật chỉ cho
  trừ bảo hiểm bắt buộc + giảm trừ gia cảnh + từ thiện/khuyến học + hưu trí tự nguyện. Giữ ERP đúng
  luật; chênh rất nhỏ (~2.600đ/người/tháng).

## 5. Lỗi phát hiện trong chính 2 file Excel

Không phải để trách ai — đây là lý do nghiệp vụ này nên nằm trong hệ thống thay vì bảng tính:

1. Cột **"Cộng"** ở sheet `TÍNH THUẾ TNCN` **cộng nhầm cả Chuyên cần** vào tổng miễn thuế. Số thuế
   vẫn đúng vì công thức không dùng cột đó, nhưng ai đọc cột tổng là hiểu sai.
2. **3 người quên điền giảm trừ bản thân** (NV00016, NV00088, NV00089) ⇒ dòng thuế bỏ trống. Riêng
   NV00089 có thu nhập chịu thuế **22.115.385đ** mà không ra đồng thuế nào.
3. Dòng TGĐ ở `BL CT` và `PHIEU LUONG CT` đang là **`#REF!`** ở Tổng lương và Thực nhận — công thức vỡ.
4. Sheet **`bac thue`** vẫn là **bảng 7 bậc CŨ** (kèm link Facebook/YouTube một nhóm dạy kế toán).
   Không dùng để tính, nhưng ai tra nhầm là ra sai thuế.
5. Ô A1 sheet `DS tham gia BH` còn tên **"CÔNG TY CỔ PHẦN CẤP NƯỚC DIỄN CHÂU"** — file mẫu, quên xoá.

## 6. DB + migration

- **3 bảng MỚI** (`payroll_components`, `payroll_group_components`, `employee_salary_components`) ⇒
  **KHÔNG cần migration**, `create_all` lo. Nhưng **BẮT BUỘC** export ở `models/__init__.py` và ghi
  `docs/DB_SCHEMA.md` — guard test `tests/test_schema_documented.py` sẽ đỏ nếu quên.
- **2 cột MỚI** trên `payroll_lines` (`thu_nhap_chiu_thue`, `thu_nhap_mien_thue`) ⇒ **migration 0115**.
- KHÔNG đụng `employee_salaries`.

## 7. Rủi ro

- ⚠️ **Không áp trần miễn thuế** (chốt của chủ). Luật miễn tiền ăn ca ≤ 730.000đ/tháng và đồng phục
  ≤ 5.000.000đ/năm. Hiện tiền cơm cao nhất 450.000đ và trang phục 400.000đ/tháng (4,8tr/năm) nên
  **chưa vượt**. Nếu sau này nâng lên là khai thiếu thuế mà hệ thống không hề cảnh báo.
  → Đề xuất tối thiểu: hiện **cảnh báo mềm** khi vượt ngưỡng, không chặn.
- ⚠️ **Trợ cấp tiền nhà** và **hỗ trợ chi phí đi lại** đang được kế toán miễn thuế toàn bộ. Theo luật
  hai khoản này thường **chịu thuế** (tiền nhà chỉ miễn phần vượt 15% thu nhập chịu thuế; phụ cấp đi
  lại cố định hằng tháng là chịu thuế). Danh mục cho phép đổi cờ bất cứ lúc nào — **nên hỏi lại kế
  toán trước khi chạy thật.**
- Đụng TIỀN ⇒ chạy thử một kỳ và đối chiếu trước khi áp.

## 8. Tests

- ⭐ **Đối chiếu số thật**: nhập nguyên bảng tháng 5/2026 → TNCN từng người khớp cột `Thuế TNCN Phải
  Khấu trừ` của kế toán, sai số ≤ 1đ. Đây là test quan trọng nhất — dữ liệu đối chứng đã có sẵn.
- Khoản `is_taxable = false` không vào thu nhập chịu thuế; bật cờ thành `true` thì thuế tăng đúng
  phần đó.
- **Hồi quy bảo hiểm**: gốc đóng BH vẫn là `luong_vi_tri` ⇒ số bảo hiểm và đoàn phí **không đổi một
  đồng** so với trước.
- Mặc định theo nhóm lương áp đúng; giá trị riêng của người ĐÈ được mặc định.
- Xoá khoản chưa dùng ⇒ xoá được. Xoá khoản đã dùng ở kỳ đã chốt ⇒ **chặn**, chuyển ngưng dùng, và
  phiếu lương kỳ cũ **vẫn hiện đủ dòng**.
- Đổi cờ `is_taxable` KHÔNG làm đổi số của kỳ đã chốt.
- **Hồi quy**: hồ sơ cũ chỉ có `allowance` một cục ⇒ lương ra **y hệt số cũ**.

## 9. Verify

- `./init.ps1` (chạy từ gốc repo) · `cd frontend && npm run build`.
- Smoke: Cấu hình lương → Danh mục khoản thu nhập → bỏ tích "Chịu thuế" của Trang phục → tính lại kỳ
  5/2026 → thuế của người có trang phục giảm đúng phần đó; phiếu lương hiện đủ 2 dòng **Tổng thu
  nhập chịu thuế** và **Thực nhận**.
- Sửa route/schema backend xong **RESTART uvicorn**.
