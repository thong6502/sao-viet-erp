# PRD — Phiếu lương tự phục vụ: tra lại lịch sử + nói đúng lý do khi trống

Chốt với chủ ngày 17/08/2026. Phạm vi: màn **Hồ sơ của tôi → khối Phiếu lương**.
KHÔNG đụng engine tính tiền, KHÔNG đụng schema.

> **Neo theo TÊN HÀM, không theo số dòng.** Bài học 17/08/2026: số dòng trong
> `docs/CONG_THUC_TINH_LUONG.md` trôi hai lần trong một ngày.

---

## 0. Hai chốt của chủ

1. **Công bố không có ngày kết thúc ⇒ luôn mở.** Không cắt mốc, không dọn dữ liệu cũ.
   Tháng nào từng phát không thời hạn thì nhân viên tra lại được, kể cả tháng rất cũ.
2. **Tháng nào đang mở thì xem được tháng đó.** Không giới hạn 12 tháng, không trần cứng.
   Cửa sổ mở–đóng là công tắc DUY NHẤT.

Hệ quả cố ý: muốn khoá lịch sử thì đặt **giờ đóng** lúc công bố, không có đường nào khác.

---

## 1. Hai vấn đề đang có

### 1.1. Nhân viên không tra lại được phiếu tháng cũ

`latest_published_line_for_employee` (`payroll_repo.py`) lọc đúng các kỳ được xem rồi
**`limit(1)`** — ném hết chỉ giữ kỳ mới nhất. `GET /api/luong/payslip/me` cũng không
nhận tham số tháng. Cộng lại: chỉ có MỘT ô, tháng mới đè tháng cũ.

**Hệ quả tiền bạc:** tháng 7 phát "không thời hạn" vẫn biến mất ngay khi phát tháng 8.
Muốn cho xem lại tháng 7 thì phải **thu hồi tháng 8** — tức cắt phiếu hiện tại của cả
công ty. Ô "giờ đóng" vì thế gần như vô nghĩa với mọi tháng trừ tháng mới nhất.

### 1.2. Ba tình huống trống nói chung một câu

`HoSoCuaToiPage.tsx` gộp mọi trường hợp không có dòng lương thành
*"Chưa có kỳ lương nào"*. Backend trả `line = null` nên frontend không có gì để phân biệt.

**Hệ quả:** cuối tháng kế toán chốt xong chưa bấm phát, thợ mở điện thoại thấy
"chưa có kỳ lương nào" ⇒ tưởng bị sót lương ⇒ đi hỏi HCNS. Lặp lại hằng tháng.

---

## 2. Luật sau khi sửa

### 2.1. Kỳ nào nhân viên xem được — GIỮ NGUYÊN bộ lọc

```
đã công bố · đã tới giờ mở · chưa tới giờ đóng (hoặc không đặt hạn)
```

Khác một điểm duy nhất: **trả về TẤT CẢ** kỳ thoả, xếp mới → cũ, thay vì `limit(1)`.
Không nới lỏng điều kiện nào — kỳ chưa phát vẫn tuyệt đối không thấy.

### 2.2. Bốn câu cho bốn tình huống

| Tình huống | Suy từ | Câu nhân viên đọc |
|---|---|---|
| Chưa từng có bảng lương | không có dòng lương nào | Chưa có kỳ lương nào |
| Có bảng lương, chưa ai bấm phát | `cong_bo_luc` rỗng | Phiếu lương tháng 08/2026 đang được lập, chưa phát |
| Đã hẹn giờ, chưa tới giờ | `cong_bo_luc > bây giờ` | Phiếu lương tháng 08/2026 sẽ mở lúc 08:00 ngày 05/09 |
| Cửa sổ đã đóng | `dong_phieu_luc <= bây giờ` | Phiếu lương tháng 08/2026 đã đóng — liên hệ HCNS |

Dùng ở HAI chỗ, một dữ liệu:
- danh sách rỗng ⇒ câu chính giữa khối
- đã có phiếu tháng cũ để xem, tháng mới chưa phát ⇒ dòng ghi chú nhỏ dưới ô chọn kỳ

---

## 3. API — vẫn MỘT endpoint

`GET /api/luong/payslip/me` thêm hai tham số **tuỳ chọn**: `year`, `month`.

Không truyền ⇒ kỳ mới nhất đang mở ⇒ **hành vi y hệt hôm nay**. Client cũ không sửa vẫn chạy.

Trả thêm hai trường:

```
ky_xem_duoc : [{year, month, dong_phieu_luc}]      mới → cũ
cho_phat    : {year, month, tinh_trang, mo_luc} | null
```

**Ba ràng buộc BẮT BUỘC:**

1. **`cho_phat` không bao giờ kèm tiền.** Chỉ tháng + trạng thái. Cửa công bố sinh ra để
   NLĐ không đọc số chưa chốt; trả `line` rồi để giao diện tự ẩn là mở DevTools đọc được.
2. **`year`/`month` đi qua ĐÚNG bộ lọc công bố**, không phải lọc thêm sau khi đã lấy dòng.
   Gõ tay `?year=2026&month=3` cho kỳ chưa phát ⇒ rỗng, không rò một con số nào.
3. **Không thêm ô quyền.** Giữ chốt 12/08/2026: kiểm soát THỜI ĐIỂM, không kiểm soát AI.

Không tách endpoint riêng cho danh sách: màn Hồ sơ của tôi đã gọi 4 API mỗi lần mở,
thêm một vòng nữa cho thứ luôn đi kèm là thừa.

---

## 4. Màn hình — HAI chỗ, không phải một

> **Sửa 17/08/2026 sau khi soi code:** bản đầu của PRD này ghi nhầm là sửa ở Hồ sơ của tôi.
> Màn đó **chỉ có CHIP tóm tắt** (`StatChip` "Phiếu lương gần nhất"), bấm vào là điều hướng
> sang màn Lương. Phiếu ĐẦY ĐỦ nằm ở tab **"Phiếu lương của tôi"** trong `LuongPage.tsx`.

**Tab Phiếu lương của tôi (màn Lương)** — nơi làm việc chính:

- **Ô chọn kỳ** đặt cạnh nút "In phiếu". **Chỉ hiện khi có ≥ 2 kỳ** — một kỳ mà bày dropdown
  là thêm khối UI vô nghĩa. Mỗi dòng ghi kèm "xem tới ngày…" nếu kỳ đó có hạn.
- **Không nhớ lựa chọn cũ** — mở màn luôn về kỳ mới nhất. Người ta vào để xem lương
  tháng này; tra lại là việc phụ.
- Bốn câu ở §2.2 thay cho khối rỗng "Chưa có phiếu lương".
- Đang xem kỳ cũ mà kỳ mới chưa phát ⇒ **dòng ghi chú nhỏ** dưới nút In phiếu.

**Chip ở Hồ sơ của tôi** — chỉ đổi câu, không thêm ô chọn kỳ:

Phải nói **cùng một lý do** với tab kia. Hai màn nói hai kiểu thì thợ đọc chỗ này một câu,
bấm sang chỗ kia thấy câu khác — mất niềm tin vào cả hai.

---

## 5. Không đụng schema

Không bảng mới, không cột mới, **không migration**. Hai cột `payroll_periods.cong_bo_luc`
và `.dong_phieu_luc` đã đủ suy ra mọi trạng thái.

`latest_line_for_employee` (`payroll_repo.py`) hiện là **code chết** — không còn ai gọi,
chỉ còn bị nhắc trong docstring và `db_migrations.py`. Lần này dùng lại đúng nó để trả lời
*"có phiếu chưa phát không"*. Không sinh hàm mới trùng vai.

---

## 6. Đụng file

| File | Sửa gì |
|---|---|
| `repositories/payroll_repo.py` | 1 hàm liệt kê kỳ xem được (bỏ `limit(1)`); 1 hàm lấy phiếu theo tháng chỉ định, CÙNG bộ lọc |
| `services/payroll_service.py` | `my_payslip` nhận `year`/`month`, dựng `ky_xem_duoc` + `cho_phat` |
| `schemas/payroll.py` | `PayslipOut` thêm 2 trường optional |
| `routers/payroll.py` | 2 query param optional trên `payslip/me` |
| `frontend/src/api/client.ts` | type `KyXemDuoc` / `ChoPhat` + tham số `ky` |
| `frontend/src/pages/LuongPage.tsx` | ô chọn kỳ + 4 câu trống + dòng ghi chú (tab Phiếu lương của tôi) |
| `frontend/src/pages/HoSoCuaToiPage.tsx` | chip nói cùng lý do (không có ô chọn kỳ) |

Bảy file, không file nào đụng engine tính tiền.

**Một sửa ngoài danh sách, cố ý:** tách `_dieu_kien_xem_phieu` trong `payroll_repo.py` thành
helper dùng chung cho CẢ BA câu truy vấn. Ba chỗ chép tay cùng một bộ lọc thì lần sau đổi luật
công bố là sót một chỗ — mà chỗ sót đó chính là chỗ để lọt **số tiền của kỳ chưa phát**. Hành vi
của `latest_published_line_for_employee` không đổi (§8.4 vẫn đúng: không đổi ngữ nghĩa).

---

## 7. Test — thêm vào `tests/test_cong_bo_phieu_va_de_khoan.py`

| # | Ca | Kỳ vọng |
|---|---|---|
| 1 | không truyền tháng | ra kỳ mới nhất đang mở (chống thụt lùi hành vi cũ) |
| 2 | T7 + T8 cùng mở | `ky_xem_duoc` có 2 kỳ, mặc định trả T8 |
| 3 | **gõ tay tháng của kỳ CHƯA công bố** | rỗng, KHÔNG rò số — quan trọng nhất |
| 4 | gõ tay tháng của kỳ ĐÃ ĐÓNG | rỗng |
| 5 | kỳ hết hạn | rớt khỏi `ky_xem_duoc` |
| 6 | bốn trạng thái `cho_phat` | đúng câu, không kèm tiền |
| 7 | tài khoản chưa gắn hồ sơ NV | `has_employee = false` |

---

## 8. Cố ý KHÔNG làm

1. **Không thêm trần "12 tháng gần nhất"** — chủ chốt câu 2. Đã có giờ đóng làm công tắc,
   thêm trần cứng là hai chỗ cùng quyết một việc.
2. **Không dọn dữ liệu cũ trước khi triển khai** — chủ chốt câu 1: không hạn nghĩa là luôn mở.
   Bật lên là mọi kỳ từng phát không thời hạn hiện lại cùng lúc. **Đây là ý muốn, không phải lỗi.**
3. **Không cho nhân viên tải phiếu tháng cũ ra file** — ngoài phạm vi đợt này.
4. **Không đụng `latest_published_line_for_employee`** đang chạy cho nhánh mặc định.
