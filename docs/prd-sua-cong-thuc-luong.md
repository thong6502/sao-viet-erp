# PRD — Sửa công thức lương & quyền xem phiếu lương

**Ngày**: 12/08/2026 · **Nguồn**: chủ chốt, 6 mục
**Tiền đề**: `docs/CONG_THUC_TINH_LUONG.md` (công thức đang chạy) · `docs/SO_TAY_TINH_LUONG_KE_TOAN.md` (bản cho kế toán)
**Trạng thái**: 🟢 **ĐÃ CHỐT HẾT, SẴN SÀNG CODE** — bắt đầu từ đợt A (§10).

---

## 0. Đo trước khi bàn

Bảy mục chủ chốt nêu, đối chiếu với mã đang chạy:

| # | Mục | Tiền đề có đúng không | Ghi chú nhanh |
|---|---|---|---|
| 1 | Tăng ca đang gồm lương trách nhiệm | ✅ **ĐÚNG** | `mức_nền = vị_trí + trách_nhiệm`, đơn giá giờ chia từ đó |
| 2 | Thưởng cơm khi tăng ca | — | **Chưa có khái niệm này**; cơm hiện theo CA và theo NGÀY ĐI LÀM |
| 3 | BHXH đang không gồm trách nhiệm | ✅ **ĐÚNG** | `insurance_base = luong_vi_tri` thôi |
| 4 | Đoàn phí đang tính trên thực lĩnh | ❌ **SAI TIỀN ĐỀ** | Nó đang tính trên **mức đóng BH**, không phải thực lĩnh |
| 5 | TNCN = Tổng − BH − phụ thuộc − bản thân − công đoàn | ⚠️ Engine **đang thiếu vế đoàn phí** | Bảng lương thật của công ty CÓ trừ ⇒ **sửa engine cho khớp** (§5) |
| 6 | Ai gán hồ sơ cũng xem được phiếu lương | ✅ **ĐÚNG** | Vá bằng **CÔNG BỐ**, không thêm ô quyền — chủ chốt chọn đường 2 (§6) |
| 7 | Muốn sửa khoản *Từ hồ sơ* cho riêng một tháng | — | **Chưa làm được**, code chặn có chủ ý (§6c) |

> **Điểm đáng chú ý nhất**: mục 1 và mục 3 **ngược chiều nhau** so với hiện trạng. Tăng ca đang
> *thừa* trách nhiệm, còn BHXH đang *thiếu* trách nhiệm. Sửa cả hai là **đảo đúng chỗ**, không phải
> hai việc rời rạc.

---

## 1. Tăng ca tính trên LƯƠNG CƠ BẢN, bỏ lương trách nhiệm

**Hiện tại**
```
mức_nền        = lương_vị_trí + lương_trách_nhiệm
đơn_giá_giờ    = (mức_nền × hệ_số_thử_việc) ÷ công_chuẩn ÷ giờ_mỗi_ngày
tiền_tăng_ca   = đơn_giá_giờ × số_giờ × hệ_số_loại_ngày
```
**Neo** — `payroll_service.py:806` (`eff_monthly`), `:845-846` · doc §5.1.

**Đổi thành**
```
đơn_giá_giờ = (lương_vị_trí × hệ_số_thử_việc) ÷ công_chuẩn ÷ giờ_mỗi_ngày
```

**Đụng đâu** — Engine đã có sẵn biến `lương_vị_trí_hiệu_lực` (doc §3.1) dùng cho ngày phép có
lương. Việc cần làm là cho đơn giá giờ đọc biến đó thay vì `eff_monthly`. **Không cột mới, không
migration.**

**Ảnh hưởng RA TIỀN** — mọi NV có lương trách nhiệm **giảm tiền tăng ca**. Ví dụ vị trí 8tr +
trách nhiệm 2tr, công chuẩn 26, 8h/ngày:

| | Đơn giá giờ | 10h tăng ca ngày thường (×1,5) |
|---|---|---|
| Hiện tại | 10.000.000 ÷ 26 ÷ 8 = **48.077đ** | 721.155đ |
| Sau khi sửa | 8.000.000 ÷ 26 ÷ 8 = **38.462đ** | **576.930đ** |
| Chênh | −20% | **−144.225đ** |

**Bẫy**
1. Đơn giá giờ còn là gốc của **premium ca đêm** và **premium làm ngày nghỉ/lễ** — sửa một chỗ là
   cả ba khoản cùng giảm. ✅ **Chủ chốt xác nhận 12/08/2026: "Đúng, giảm cả."**
2. Hồ sơ **CŨ** chỉ khai `base_amount` (không tách vị trí/trách nhiệm) — engine coi cả cục là
   lương vị trí, nên nhóm này **không đổi gì**. Đừng tưởng sửa xong ai cũng giảm.

---

## 2. Thưởng tiền cơm khi TĂNG CA

**Hiện tại — chưa có.** Tiền cơm đang là khoản theo **CA** và theo **NGÀY CÓ ĐI LÀM**:
```
tiền_cơm = Σ_ca  work_shifts.meal_allowance(ca) × số_ngày_làm_ca_đó
```
Đếm ngày có `công ≥ phu_cap_ca_min_cong` (mặc định 0,5). Tăng ca **không hề tham gia**.
**Neo** — `payroll_service.py:875-901` · doc §5.6.

**Đổi thành — thêm suất cơm TĂNG CA, độc lập với suất cơm ca:**

| Loại ngày | Điều kiện có suất cơm tăng ca |
|---|---|
| **Ngày LÀM VIỆC** theo Lịch chung | tăng ca **≥ ngưỡng** (mặc định 3 giờ) trong NGÀY đó |
| **Ngày NGHỈ** theo Lịch chung — gồm cả **NGÀY LỄ** | **cứ có tăng ca là có suất**, 1 giờ cũng tính |

✅ **ĐÃ CHỐT 12/08/2026: theo LỊCH NGHỈ**, không cứng ngày Chủ nhật. Luật hỏi đúng một câu —
`calendar.is_working_day(ngày)`:

* `False` (lịch bảo nghỉ) → nhánh **cứ tăng ca là có cơm**
* `True` (ngày làm việc) → nhánh **≥ ngưỡng giờ**

Nhờ vậy đổi tuần làm việc ở màn Lịch chung là luật tự đi theo, **không phải sửa code**.

> ⚠️ **HỆ QUẢ PHẢI BIẾT: ngày lễ tự động vào nhánh "cứ tăng ca là có cơm".** `is_working_day` trả
> `False` cho cả nghỉ hàng tuần LẪN ngày lễ (30/4, 2/9…). Đúng tinh thần *"đi làm vào ngày đáng ra
> được nghỉ thì đãi ngộ tốt hơn"*, và ngày lễ còn đáng hơn Chủ nhật. Nhưng nếu chủ chốt muốn ngày
> lễ đi nhánh ≥3h thì phải tách riêng — nói trước khi code.
>
> **Ngày `off1x` cũng trả `False`** ⇒ cũng vào nhánh dễ. Ngày off1x vốn là "nghỉ nhưng làm chỉ 1×,
> không hệ số" — cho suất cơm ở đây là nới hơn cách engine đang đối xử với nó ở mọi chỗ khác.
> Ghi lại để lúc test không tưởng là lỗi.

Cả **ngưỡng giờ** lẫn **mức tiền** đều khai ở **Cấu hình lương** (chủ chốt: *"cái này mình setup
động nha"*), không cứng trong code.

### ⚠️ Mục này TỐN NHẤT — cần cột mới + migration

Ảnh chụp kỳ công hiện chỉ giữ **TỔNG phút tăng ca cả tháng** (`ot_minutes`), không giữ **phút tăng
ca TỪNG NGÀY**. Mà luật mới hỏi *"ngày nào tăng ca ≥ 3 giờ"* — câu hỏi theo ngày.

Nên phải thêm một danh sách theo ngày vào ảnh chụp, giống cách `late_off_days` đang làm:
`attendance_period_lines.ot_days_json` (+ migration, + cập nhật `DB_SCHEMA.md`, + khớp CẢ HAI nhánh
`metrics_map`). Đây đúng lớp lỗi doc đã cảnh báo hai lần: **thiếu một khoá ở nhánh ảnh chụp là số
nhảy đúng lúc chốt công**.

**Bẫy**
1. Suất cơm tăng ca **độc lập** với suất cơm ca — một ngày có thể ăn cả hai. Cần chốt lúc dựng màn
   Cấu hình: hai dòng riêng, đừng gộp thành một ô "tiền cơm".
2. ✅ **Miễn thuế TNCN** (chốt 12/08/2026) — đi chung nhóm cơm ca, miễn toàn bộ, không trần.
3. Ngưỡng khai theo **GIỜ** hay **PHÚT**? Chấm công đếm bằng phút. Khai 3 giờ mà người ta tăng ca
   2h59' thì trượt suất — đúng luật, nhưng phải nói trước với xưởng.

---

## 3. Lương đóng bảo hiểm = lương cơ bản + lương trách nhiệm

**Hiện tại**
```
insurance_base = lương_vị_trí          (KHÔNG cộng trách nhiệm, KHÔNG × hệ số thử việc)
```
**Neo** — `payroll_service.py:981` · doc §8.2. Ghi chú trong code dẫn lại chốt cũ của chủ chốt
ngày 20/07/2026: *"Lương vị trí CHÍNH LÀ lương cơ bản, dựa vào đó đóng bảo hiểm"* — **nay đảo lại**.

**Đổi thành**
```
insurance_base = lương_vị_trí + lương_trách_nhiệm
```
Giữ nguyên: **không** prorate theo công, **không** × hệ số thử việc, vẫn kẹp trần `bh_base_cap` /
`bhtn_base_cap`.

**Ảnh hưởng RA TIỀN** — NV có trách nhiệm bị **trừ BHXH nhiều hơn** (10,5% phần tăng thêm), công ty
cũng **đóng nhiều hơn** (21,5%). Ví dụ trách nhiệm 2tr: NV mất thêm **210.000đ/tháng**.

**Bẫy** — `insurance_base` bị **đóng băng** trên dòng lương lúc "Tính lại". Sửa hồ sơ lương mà
không bấm Tính lại thì bảng lương vẫn mức đóng cũ (doc §8.2 bẫy 6).

---

## 4. Phí công đoàn — **tiền đề sai, nhưng kết quả mong muốn tự đạt**

**Chủ chốt nói**: *"không phải thực lĩnh × 0,5% mà là (cơ bản + trách nhiệm) × 0,5%"*.

**Đo thật**: engine **chưa bao giờ** tính trên thực lĩnh. Cả hai đường đều tính trên mức đóng BH:
```
đoàn_phí = insurance_base × cong_doan_rate
```
**Neo** — `payroll_service.py:992` (đường Tính lại) và `:1471-1472` (đường Sửa 1 ô).

⇒ **Sau khi làm mục 3, mục này TỰ ĐÚNG** — vì `insurance_base` lúc đó chính là cơ bản + trách nhiệm.
**Không phải sửa gì thêm.**

> Nếu chủ chốt nhìn thấy một con số trông như "×0,5% của thực lĩnh", nhiều khả năng đó là **lỗi #3
> đã biết** trong doc Phần 14: đường *Sửa 1 ô* tính lại đoàn phí mà **quên kiểm cờ đoàn viên**, nên
> người **không phải đoàn viên** vẫn bị trừ sau mỗi lần sửa dòng. Lỗi này độc lập với mục 4 và
> **nên vá cùng đợt** — bản vá đã có sẵn trong doc.

---

## 5. TNCN — giải đáp: **gần đúng, sai một vế**

**Chủ chốt hỏi**: *"Hiện tại của mình có phải là Tổng tiền − Bảo hiểm − Phụ thuộc − gia cảnh bản
thân − công đoàn?"*

**Công thức thật đang chạy** (doc §9.1 → §9.3):
```
thu_nhập_chịu_thuế = gross_trước_phạt − (tăng ca + premium ca đêm + cơm ca
                                          + phụ cấp ca + khoản danh mục miễn thuế)

thu_nhập_TÍNH_thuế = max(0,  thu_nhập_chịu_thuế
                             − bảo_hiểm
                             − giảm_trừ_bản_thân (15.500.000)
                             − giảm_trừ_người_phụ_thuộc (6.200.000 × số người) )
```

| Vế chủ chốt nêu | Thực tế |
|---|---|
| Tổng tiền | ⚠️ Không phải tổng thô — **đã trừ 5 khoản miễn thuế trước** (tăng ca, premium ca đêm, cơm ca, phụ cấp ca, khoản danh mục miễn) |
| − Bảo hiểm | ✅ Có |
| − Giảm trừ bản thân | ✅ Có |
| − Người phụ thuộc | ✅ Có |
| − Công đoàn | ❌ **KHÔNG có** |

### ✅ ĐÃ CHỐT: TRỪ đoàn phí trước thuế

Chủ chốt đưa **bảng lương thật đang dùng** (12/08/2026). Khối "Các khoản giảm trừ" gồm 5 cột:
Bản thân · NPT số người · NPT số giảm · **BH bắt buộc** · **Đoàn phí công đoàn** → cột "Tổng Cộng".

Kiểm lại số trên bảng:
```
15.500.000 + 6.200.000 + 1.102.080 + 52.480 = 22.854.560   ← đúng bằng cột "Tổng Cộng"
```
Đoàn phí **nằm trong khối giảm trừ**, trừ trước khi ra thu nhập tính thuế. ⇒ **Engine phải làm theo.**

**Bảng đó còn xác nhận luôn mục 3 và mục 4** — soi ngược ra gốc tính:

| | Số trên bảng | ÷ tỷ lệ | Gốc suy ra |
|---|---|---|---|
| BH bắt buộc | 1.102.080 | ÷ 10,5% | **10.496.000** |
| Đoàn phí | 52.480 | ÷ 0,5% | **10.496.000** |

**Cùng một gốc** ⇒ đoàn phí đi chung gốc với BH (mục 4 ✓), và gốc đó là mức nền đầy đủ chứ không
phải riêng lương cơ bản (mục 3 ✓). Ba mục 3–4–5 khớp thành một khối nhất quán.

**Ghi để sau này không ai ngỡ ngàng**: danh sách giảm trừ ở Thông tư 111/2013 Đ9 gồm giảm trừ gia
cảnh · bảo hiểm bắt buộc & hưu trí tự nguyện · từ thiện–nhân đạo–khuyến học — **không có đoàn phí**.
Trừ nó là **cố ý làm khác**, theo cách công ty đang hạch toán. Ghi lại đây để lúc quyết toán thuế
biết chỗ mà giải trình, KHÔNG phải để bàn lại.

**Đổi thành**
```
thu_nhập_TÍNH_thuế = max(0, thu_nhập_chịu_thuế − bảo_hiểm − ĐOÀN_PHÍ − giảm_trừ_gia_cảnh)
```
**Đụng đâu** — `_auto_pit` (`payroll_service.py:445`) thêm tham số `cong_doan`; dòng `:475` trừ thêm
một vế. Hai chỗ gọi phải truyền: `:1001` (Tính lại) và `:490` `_apply_auto_pit` (Sửa 1 ô).

⚠️ **BẪY THỨ TỰ — đường "Sửa 1 ô" đang sai thứ tự sẵn.** `_apply_auto_pit(ln)` chạy ở `:1451`/`:1457`,
còn `ln.cong_doan` mãi `:1471` mới tính lại. Thuế bắt đầu phụ thuộc đoàn phí thì thứ tự này làm
**thuế ăn số đoàn phí CŨ**. Phải dời khối tính `cong_doan` lên TRƯỚC khối TNCN. Không dời là hai
đường "Tính lại" / "Sửa 1 ô" ra hai con số — đúng lớp lỗi đã dính nhiều lần ở file này.

**Điều đáng lưu ý hơn** — vì **tiền tăng ca được miễn thuế toàn bộ**, mục 1 (giảm tiền tăng ca)
làm **phần thu nhập chịu thuế TĂNG tương ứng**. Người có trách nhiệm vừa giảm tăng ca, vừa tăng
BHXH, **vừa có thể tăng thuế**. Ba đầu cùng lúc.

---

## 6. Phiếu lương — ~~cấp quyền mới xem được~~ → **CÔNG BỐ mới xem được**

⚠️ **ĐỔI HƯỚNG 12/08/2026.** Yêu cầu ban đầu: *"Phiếu lương được cấp quyền mới xem được nha; hiện
tại là ai gán hồ sơ cũng xem được"*. Bàn tiếp thì chủ chốt chọn **đường 2 — bỏ lớp quyền, chỉ giữ
lớp công bố**.

### Hai đường đã cân

| | Cách | Đánh đổi |
|---|---|---|
| (1) | **Quyền** (AI) + **Công bố** (KHI NÀO) | Siết được từng vai. Đổi lại: quên tick là NV không thấy phiếu, gọi điện hỏi HCNS |
| **(2)** ✅ | **Chỉ Công bố** | Gọn, không có ô nào để quên. Đổi lại: mọi NV có hồ sơ đều xem phiếu CỦA CHÍNH MÌNH |

**Vì sao (2) đúng hơn**: phiếu lương là tiền của chính người ta — ai cũng có quyền xem lương của
mình. Thứ thật sự cần kiểm soát là **THỜI ĐIỂM**: đừng để họ thấy con số còn đang tính. Không phải
*ai* được xem.

⇒ **Không thêm ô quyền nào. Không có nút "cấp cho tất cả vai".** Cổng `self_service:read` ở
`GET /payslip/me` **giữ nguyên**; cái mới là bộ lọc công bố ở §6b.

---

## 6b. CÔNG BỐ PHIẾU LƯƠNG — nút bấm + hẹn giờ

✅ **ĐÃ CHỐT 12/08/2026**: *"cho một nút cấp quyền toàn bộ và có thể hẹn giờ xem được phiếu"* →
*"cho nó nút bấm ấy"*. **Một nút trên màn Lương, không thêm màn cấu hình.**

### Vì sao mục này sinh ra — một lỗ tìm được lúc soi

**Nhân viên đang xem được phiếu lương của kỳ NHÁP.** `latest_line_for_employee`
(`payroll_repo.py:368`) lấy dòng lương của kỳ mới nhất và **không lọc trạng thái kỳ**. HCNS vừa bấm
"Tính lại", số còn đang soát, thợ đã mở điện thoại xem được; HCNS sửa tiếp thì số đổi, không ai báo.

Quyền (mục 6) trả lời *AI được xem*. Mục này trả lời *KHI NÀO phiếu mở ra* — hai câu khác nhau,
cần cả hai.

### Cách làm — MỘT cột, không có bộ hẹn giờ chạy nền

```
payroll_periods.cong_bo_luc   (DateTime, NULL = chưa công bố)
```

| Thao tác | Ghi gì |
|---|---|
| **Công bố ngay** | `cong_bo_luc = bây giờ` |
| **Hẹn giờ** | `cong_bo_luc = thời điểm tương lai` |
| **Thu hồi** | `cong_bo_luc = NULL` |

Điều kiện NV thấy phiếu: `cong_bo_luc IS NOT NULL AND cong_bo_luc <= bây_giờ`.

**Kiểm lúc ĐỌC, không cần cron.** "Hẹn giờ" chỉ là ghi một mốc tương lai rồi để phép so ngày tự
đúng. Không job nền ⇒ không có chuyện job chết mà không ai biết, không lệch múi giờ, không phải lo
scale nhiều worker.

### Luật đi kèm

1. **Chỉ công bố được kỳ ĐÃ CHỐT.** Kỳ nháp không có nút — số chưa đóng băng thì không phát ra
   ngoài. Đây chính là cái bịt lỗ ở trên.
2. **Mở lại kỳ lương ⇒ tự thu hồi công bố** (`cong_bo_luc = NULL`). Mở lại nghĩa là số sắp đổi;
   để phiếu mở là NLĐ đọc một con số sắp khác.
3. Nút nằm cạnh *Chốt* / *Đánh dấu đã chi* trên thanh công cụ màn Lương, gác bằng **ô Chốt bảng
   lương (`luong:lock`)** — KHÔNG thêm ô quyền mới. Nhất quán với đường 2: bớt ô để quên. Ngoài
   đời người chốt bảng lương và người phát phiếu cũng là một (HCNS), và lỡ tay thì có nút Thu hồi.
   Cần tách vai thật thì thêm cột sau — rẻ hơn là làm đủ 5 chặng đường ống cho một nút chưa ai dùng.
4. Kỳ đã công bố hiện nhãn **"Đã công bố · 08:00 10/06"**; kỳ hẹn giờ hiện **"Hẹn 08:00 10/06"**.

### Đụng đâu

| | |
|---|---|
| Cột mới | `payroll_periods.cong_bo_luc` + migration + `DB_SCHEMA.md` |
| Ô quyền mới | **KHÔNG có** — dùng ô Chốt bảng lương (xem luật 3) |
| Service | `my_payslip` lọc theo `cong_bo_luc`; `reopen_period` xoá mốc |
| API | `POST /api/luong/cong-bo` · `POST /api/luong/thu-hoi` |
| Giao diện | nút + hộp chọn giờ ở màn Lương |

---

## 6c. MỤC 7 — Đè khoản "Từ hồ sơ" cho riêng một kỳ

**Chủ chốt hỏi 12/08/2026**: *"gán cho nó Hỗ trợ chi phí đi lại, nhưng tháng này nó đi nhiều hơn
thì tôi muốn sửa thì sao?"*

**Hiện tại: KHÔNG sửa được.** Code chặn thẳng (`payroll_service.py:1319`):

> *"Khoản này chép từ hồ sơ nhân viên — sửa ở Lương → Lương nhân viên, không sửa trực tiếp trên
> bảng lương."*

### Vì sao chặn — và vì sao chặn là ĐÚNG với code hiện tại

`replace_employee_line_components` (`payroll_component_repo.py:134`) **xoá sạch rồi ghi lại** mọi
dòng `source='employee'` mỗi lần bấm *Tính lại*. Dòng `source='line'` (thưởng nóng) thì sống sót —
cố ý, có ghi chú hẳn hoi.

Nên nếu mở khoá cho sửa mà không làm gì thêm: HCNS sửa 200.000 → 350.000, hôm sau ai bấm *Tính lại*
là **về 200.000 âm thầm**. Mất tiền không dấu vết — đúng loại lỗi tệ nhất.

### Đường vòng dùng được NGAY (chưa cần code)

Bấm **`+ Thêm khoản phát sinh`**, khai phần **CHÊNH**:
```
Hỗ trợ chi phí đi lại       200.000   ← từ hồ sơ, để nguyên
Đi lại vượt tháng 8         150.000   ← thêm tay, source='line', sống qua Tính lại
```
Nhớ chọn **Miễn thuế** cho khớp dòng gốc.

**KHÔNG sửa ở hồ sơ lương** cho việc này: sửa ở đó đổi cho tháng này **và mọi tháng sau**, phải nhớ
quay lại sửa ngược. Quên một lần là trả sai mãi mãi.

Nhược: phiếu lương hiện **2 dòng** thay vì 1 dòng 350.000.

### Đổi thành

Sửa thẳng ô số tiền trên dòng *Từ hồ sơ*. Dòng đó được đánh dấu **"đã sửa cho kỳ này"** và:

| | |
|---|---|
| *Tính lại* | **KHÔNG ghi đè** dòng đã đè |
| Hồ sơ lương | **KHÔNG đổi** — tháng sau tự về mức cũ |
| Nút **"Trả về theo hồ sơ"** | bỏ đè, dòng lại đi theo hồ sơ như thường |

### Cách làm — một cột

```
payroll_line_components.da_de_tay   (Boolean, default false)
```

| Chỗ | Sửa gì |
|---|---|
| `update_line_component` (`:1319`) | Bỏ chặn `source != line`; sửa dòng `employee` ⇒ set `da_de_tay = true` |
| `replace_employee_line_components` (`:134`) | Chỉ xoá `source='employee' AND NOT da_de_tay` |
| `generate` | Bỏ qua khoản hồ sơ nào đã có dòng đè cùng `code` — nếu không sẽ sinh **dòng trùng** |
| Giao diện | Ô số tiền sửa được + nhãn "đã sửa cho kỳ này" + nút "Trả về theo hồ sơ" |

⚠️ **Bẫy dễ vỡ nhất là vế `generate`.** Dòng đè vẫn mang `source='employee'` để không bị nhầm với
thưởng nóng, nên nếu `generate` không biết bỏ qua thì mỗi lần Tính lại lại **thêm một dòng nữa** —
NV ăn tiền hai lần. Test phải có ca: *đè → Tính lại → vẫn đúng MỘT dòng, đúng số đã đè*.

### Vì sao xếp vào đợt B

Cùng nhóm "có migration" với mục 6 và §6b, và độc lập hoàn toàn với công thức lương của đợt A.

---

## 7. Ảnh hưởng dây chuyền — đọc trước khi quyết

**Ba mục ra tiền cùng lúc, cùng một nhóm người** (NV có lương trách nhiệm):

| | Chiều |
|---|---|
| Mục 1 — tăng ca bỏ trách nhiệm | 🔻 giảm thu nhập |
| Mục 3 — BHXH thêm trách nhiệm | 🔻 giảm thực lĩnh (đóng nhiều hơn) |
| Hệ quả mục 1 lên thuế | 🔻 tăng thu nhập chịu thuế (tăng ca miễn thuế ít đi) |

**Nên tính thử một tháng thật trước khi áp**, đối chiếu vài người tiêu biểu. Không nên vừa sửa vừa
chốt lương.

**Kỳ đã chốt / đã chi**: **không đụng.** Số đã đóng băng trên dòng lương. Chỉ kỳ **nháp** đổi, và
chỉ khi bấm **Tính lại** — vòng khoá công ⇄ lương vừa dựng ở đợt trước đã bắt buộc điều đó.

**Doc phải sửa CẢ HAI**: `CONG_THUC_TINH_LUONG.md` (§3.1, §5.1, §5.6, §8.2, §8.5) và
`SO_TAY_TINH_LUONG_KE_TOAN.md`. Sửa một bên là hai bên nói hai kiểu.

---

## 8. Các câu phải chốt trước khi code — ✅ ĐÃ CHỐT HẾT (12/08/2026)

1. ~~**Mục 1** — premium ca đêm / ngày nghỉ có giảm theo không?~~ ✅ **ĐÃ CHỐT 12/08/2026:
   GIẢM CẢ.** Một đơn giá giờ duy nhất cho tăng ca + premium ca đêm + premium làm ngày nghỉ/lễ,
   tất cả bám lương vị trí. ⇒ **Đợt A không còn vướng gì.**
2. ~~**Mục 2** — cơm tăng ca có miễn thuế không?~~ ✅ **ĐÃ CHỐT 12/08/2026: CÓ MIỄN**, đi
   chung nhóm với cơm ca (miễn toàn bộ, không trần).
3. ~~**Mục 2** — "chủ nhật" theo Lịch chung hay cứng Chủ nhật?~~ ✅ **ĐÃ CHỐT 12/08/2026:
   THEO LỊCH NGHỈ** (`is_working_day`). Ngày lễ **tự động** vào nhánh dễ — xem hộp cảnh báo ở §2.
4. ~~**Mục 6** — migration có cấp bù quyền xem phiếu lương không?~~ ✅ **ĐÃ CHỐT 12/08/2026:
   KHÔNG cấp bù**, thay bằng **nút "Cấp cho tất cả vai"** ở màn Vai trò — quản trị bấm một phát.
   Kèm theo: **nút Công bố phiếu lương + hẹn giờ** (§6b).
5. ~~**Mục 5** — giữ nguyên hay trừ đoàn phí trước thuế?~~ ✅ **ĐÃ CHỐT 12/08/2026: TRỪ** —
   chủ chốt đưa bảng lương thật, đoàn phí nằm trong khối giảm trừ (§5).

---

## 9. Thứ tự đề xuất

| Đợt | Việc | Migration |
|---|---|---|
| **A** | Mục 1 + Mục 3 (+ mục 4 tự đúng) + **Mục 5** (trừ đoàn phí trước thuế) | không |
| **B** | **§6b công bố/hẹn giờ** + **§6c mục 7 đè khoản** (mục 6 gộp vào §6b) | có (2 cột) |
| **C** | Mục 2 — cơm tăng ca | có (`ot_days_json` + cấu hình) |
| **—** | Lỗi #3 đã biết: đoàn phí sống lại khi sửa dòng | không |

Đợt A trước vì **không cần migration** và trả lời đúng câu hỏi tiền lương chủ chốt đang gấp. Đợt C
để sau cùng vì nó là mục duy nhất phải đụng vào ảnh chụp kỳ công.

---

## 10. ĐỢT A — việc phải làm, theo đúng thứ tự

Ba mục 1 · 3 · 5 đều nằm trong **một hàm** (`payroll_service._compute`) và **một hàm phụ**
(`_auto_pit`). Không migration, không cột mới. Nhưng thứ tự đụng vào có ý nghĩa — xem A4.

### A1 · Mục 3 — mức đóng bảo hiểm (làm TRƯỚC)

`payroll_service.py:981`
```python
insurance_base = float(getattr(salary, "luong_vi_tri", 0) or 0)            # cũ
insurance_base = luong_vi_tri + luong_trach_nhiem                          # mới
```
Làm trước vì **đoàn phí và BHXH đều đọc biến này** — sửa xong là mục 4 tự đúng luôn.
Giữ nguyên: không prorate theo công · không × hệ số thử việc · vẫn kẹp `bh_base_cap`/`bhtn_base_cap`.

### A2 · Mục 1 — đơn giá giờ bỏ lương trách nhiệm

`payroll_service.py:845-846` — đổi mẫu số từ `eff_monthly` sang **lương vị trí hiệu lực**
(biến đã có sẵn, đang dùng cho ngày phép có lương).

⚠️ Kéo theo **premium ca đêm** và **premium làm ngày nghỉ/lễ** cùng giảm — chung một đơn giá.
Đây là §8 câu 1, chưa chốt.

### A3 · Mục 5 — trừ đoàn phí trước thuế

1. `_auto_pit` (`:445`) thêm tham số `cong_doan: float = 0.0`
2. `:475` — `taxable = max(0, assessable − bhxh − cong_doan − deduction)`
3. Chỗ gọi 1: `:1001` (đường **Tính lại**) truyền `cong_doan` vừa tính ở `:992`
4. Chỗ gọi 2: `_apply_auto_pit` (`:490`) truyền `float(ln.cong_doan)`

### A4 · ⚠️ DỜI THỨ TỰ ở đường "Sửa 1 ô" — không làm là hỏng

Hiện tại `update_line` chạy sai thứ tự, và **chỉ lộ ra khi thuế bắt đầu phụ thuộc đoàn phí**:

```
:1451/:1457   _apply_auto_pit(ln)      ← tính THUẾ
:1471         ln.cong_doan = ...       ← tính ĐOÀN PHÍ (sau)
```

Để nguyên thì thuế ăn số đoàn phí **CŨ**, còn đường *Tính lại* dùng số mới ⇒ **hai đường ra hai con
số**. Phải dời khối `cong_doan` lên **trước** khối TNCN.

### A5 · Vá kèm lỗi #3 đã biết (doc Phần 14)

`:1471` quên kiểm cờ đoàn viên ⇒ người **không phải đoàn viên** vẫn bị trừ đoàn phí sau mỗi lần sửa
dòng. Nay lỗi này còn **lây sang thuế** (đoàn phí ma làm giảm thuế), nên bắt buộc vá cùng:
```python
ln.cong_doan = 0.0 if (ln.is_probation or not union_member) else ...
```

### A6 · Test phải có

| Ca | Chốt điều gì |
|---|---|
| Mức đóng BH = vị trí + trách nhiệm | mục 3 |
| Đoàn phí = mức đóng BH × tỷ lệ (không phải thực lĩnh) | mục 4 |
| Đơn giá giờ chỉ dùng lương vị trí | mục 1 |
| Thu nhập tính thuế có trừ đoàn phí | mục 5 |
| **"Tính lại" và "Sửa 1 ô" ra CÙNG một số thuế** | A4 — ca quan trọng nhất |
| Không phải đoàn viên ⇒ đoàn phí 0 **và** thuế không được giảm | A5 |
| Hồ sơ cũ chỉ có `base_amount` ⇒ không đổi gì | §1 bẫy 2 |

### A7 · Đối chiếu số thật trước khi coi là xong

Khớp công thức **chưa chắc khớp số**. Sau khi sửa:

1. Chạy lại tháng **05/2026**, đặt cạnh file `lương thuế T 05.2026.xlsx` của kế toán, dò từng người.
2. **Tìm một người có thu nhập tính thuế > 10 triệu** để kiểm cách cộng thuế. Dòng duy nhất nhìn
   được trên ảnh có thu nhập tính thuế 2,8tr — **nằm gọn trong bậc 1**, nên không phân biệt được
   *cộng từng bậc* (đúng) với *nhân một hệ số bậc* (sai). Nếu bảng kế toán đang nhân hệ số bậc thì
   chênh lệch **lớn hơn nhiều** so với chuyện đoàn phí: người 45tr chênh 3,5 triệu/tháng.
3. Bảng của họ **không có cột** premium ca đêm và phụ cấp ca — hai khoản engine mình cũng miễn
   thuế. Cần xác nhận xưởng có dùng không, hay họ gộp vào cột khác.

### A8 · Sửa doc — CẢ HAI bản

`CONG_THUC_TINH_LUONG.md` §3.1 · §5.1 · §8.2 · §8.5 · §9.3 · Phần 14 (gỡ lỗi #3 khi đã vá)
`SO_TAY_TINH_LUONG_KE_TOAN.md` — bản cho kế toán đọc.

Sửa một bên là hai bên nói hai kiểu — đúng cái CLAUDE.md dặn.
