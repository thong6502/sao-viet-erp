# HƯỚNG DẪN SỬ DỤNG — CHẤM CÔNG · TĂNG CA · LƯƠNG

**Phiên bản:** 1.0
**Ngày cập nhật:** 05/08/2026
**Phạm vi:** toàn bộ chức năng trong `Nhân sự & Lương → Chấm công` và `Nhân sự & Lương → Lương`, kể cả các chức năng ẩn/dở dang — ghi rõ để người dùng không nhầm "chưa thấy" với "chưa có".

> Quy ước trong tài liệu này: 🔴 = chức năng **chưa hoạt động** dù có vẻ tồn tại (đã khai được nhưng không ra kết quả, hoặc PRD mô tả nhưng code chưa làm) — đọc kỹ trước khi báo lỗi hoặc đi tìm nút không có thật.

---

# PHẦN A — CHẤM CÔNG

Menu: **Nhân sự & Lương → Chấm công**. Màn có **9 tab**; 3 tab đầu ai cũng thấy (self-service), 6 tab sau cần quyền.

| # | Tab | Cần quyền |
|---|---|---|
| 1 | Chấm công của tôi | không cần — ai đăng nhập và có hồ sơ NV cũng thấy |
| 2 | Công của tôi | không cần |
| 3 | Đi muộn / về sớm / nghỉ nửa buổi | không cần (xin cho chính mình) |
| 4 | Điểm chấm công | `nhan_su:create/update/delete` |
| 5 | Khai ca (A. Ca làm việc · B. Phân ca tháng) | `nhan_su:create/update/delete` |
| 6 | Lịch & Ngày lễ | `nhan_su:create/update/delete` |
| 7 | Nhật ký chấm công | `nhan_su:read` |
| 8 | Bảng công tháng | `nhan_su:read` |
| 9 | Yêu cầu chỉnh công | `nhan_su:read` (xem/duyệt), `nhan_su:adjust` (chấm bù tay, duyệt) |

## A.1. Khai điểm chấm công (GPS)

Tab **Điểm chấm công**. Đây là danh mục các "tâm geofence" — nhân viên chấm công được khi đứng gần bất kỳ điểm nào trong danh mục này, không phải đúng 1 điểm cố định.

Khai mỗi điểm: **Tên** (bắt buộc), **Toạ độ** (lấy từ bản đồ hoặc nhập tay), **Bán kính cho phép** (mặc định gợi ý 150 m khi tạo mới, có nút chọn nhanh 50/100/150/200/500 m), **Ghi chú**, **Đang dùng**.

> Bán kính khai **theo từng điểm**, không có một số chung cho toàn công ty. Muốn siết/nới cho một xưởng/kho cụ thể thì sửa đúng điểm đó.

## A.2. Khai ca làm việc

Tab **Khai ca → khối A. Ca làm việc**. Mỗi ca có:

| Trường | Mặc định khi tạo mới | Ghi chú |
|---|---|---|
| Tên ca | — | bắt buộc |
| Giờ vào / Giờ ra | 08:00 / 17:00 | tick "Ca qua đêm" nếu giờ ra nhỏ hơn giờ vào (VD 22:00→06:00) |
| Dung sai đi muộn (phút) | 5 | 0–240, đến trong khoảng này không tính trễ |
| **Phụ cấp cơm (đ)** | 25.000 | riêng cho từng ca, tự cộng vào lương theo số ngày làm ca đó |
| **Phụ cấp ca (đ)** | 50.000 | riêng cho từng ca, tự cộng vào lương theo số ngày làm ca đó |
| Hệ số ca đêm | 1,3 (+30%) | chỉ hiện khi tick "Ca qua đêm"; áp cho phần giờ rơi khung 22h–06h |
| Đang dùng | Có | |

Xoá ca bị chặn nếu ca đang được gán (ca nền của ai đó, ô lưới phân ca, hoặc còn là ca mặc định cũ) — lúc đó chỉ chuyển được sang **Ngừng dùng**.

> Xem cách hai khoản Phụ cấp cơm/Phụ cấp ca ra tiền thật ở mục **C.2 / C.3** (phần Lương).

## A.3. Phân ca — ba lớp, không đè sai nhau

Tab **Khai ca → khối B. Phân ca tháng**. Ca thật của một người vào một ngày cụ thể được xác định theo đúng thứ tự ưu tiên sau (lớp sau chỉ dùng khi lớp trước không có dữ liệu):

1. **Ô lưới ngày** (`employee_shift_days`) — phân riêng cho đúng 1 người, đúng 1 ngày. Ô đánh dấu **Nghỉ** cho ngày đó vẫn thuộc lớp này nhưng **trong suốt với việc chấm công** — đi làm hôm đó vẫn được tính công 1× bình thường (không phải là "khoá cứng không cho làm"), chỉ là dấu hiệu lịch xoay ca.
2. **Ca nền theo mốc hiệu lực** (`employee_shift_assignments`) — ca mặc định hằng ngày, gán theo ngày bắt đầu áp dụng, không cần gán lại từng ngày.
3. **`default_shift_id`** trên hồ sơ — chỉ dùng khi người đó **chưa từng có mốc ca nền nào**. Đã có ít nhất 1 mốc thì các ngày trước mốc đầu tiên coi là **không có ca** (không rơi về mặc định nữa).

**Thao tác:**

- **Gán ca nền cho từng người**: chọn người, chọn ca, chọn ngày hiệu lực.
- **Gán hàng loạt cho cả tổ**: chọn tổ + ca + ngày hiệu lực, áp cho mọi người trong tổ trong một lần. Người vào làm SAU ngày chọn sẽ tự lùi mốc về đúng ngày vào làm (không bị gán ca trước khi họ tồn tại). Người ngoài phạm vi/không hợp lệ báo rõ lý do, không âm thầm bỏ qua.
- **Phân ca riêng cho một ngày cụ thể** trên lưới NV × ngày.
- **Đặt một ngày là Nghỉ** trên lưới.
- 🔴 **Áp nhanh xoay ca (VD 2-2-2)**: tính năng đã dựng xong trong code nhưng **đang bị ẩn khỏi giao diện** theo quyết định nội bộ 28/07/2026 — hiện không có nút này trên màn thật. Đừng đi tìm.

**Lịch sử/Nhật ký thay đổi ca**: mọi lần đổi ca nền hoặc ô ngày đều ghi log (trước/sau, ai đổi, đổi từ đường nào). Trường hợp trước và sau giống hệt nhau thì **không ghi** (tránh rác khi lưu cả tháng). Lần gán ca đầu tiên khi tạo hồ sơ mới **không ghi log** (chưa có ca cũ để so).

**Thông báo real-time**: nhân viên bị đổi ca nhận thông báo tức thì (badge + có thể xem lại trong hộp thư riêng của mình, mục A.9), không phải chờ refresh hay đợi ai báo miệng.

## A.4. Chấm công hằng ngày (tab "Chấm công của tôi")

- Bấm **Chấm vào / Chấm ra**. Vị trí lấy từ GPS trình duyệt, gửi kèm mỗi lượt chấm.
- Ngoài bán kính của MỌI điểm chấm công đang hoạt động → **chặn cứng**, không ghi log.
- Chỉ chấm **Vào** được trong cửa sổ từ 60 phút trước giờ vào ca cho tới hết giờ ca — không cho chấm sớm quá 60 phút.
- Sau khi đã Ra ca chính, muốn chấm Vào lại (đi làm thêm) thì **bắt buộc đã có phiếu Tăng ca đã duyệt phủ đúng khung giờ đó** — không có phiếu thì bị chặn ngay từ bước chấm, kèm thông báo rõ ràng (xem thêm Phần B).
- Chấm nhiều lần trong ngày (ra ngoài rồi quay lại) là bình thường, hệ ghi lại **tất cả**, không hỏi lý do và không giới hạn số lần.
- Lượt Ra sau nửa đêm vẫn được ghép đúng vào ca đang mở (trong vòng 8 giờ kể từ giờ tan ca) — không bị "mồ côi" khi ca vắt qua hai ngày lịch.

## A.5. Cách hệ tính công một ngày

```
Khung ca (phút) = giờ ra − giờ vào (nếu ca qua đêm thì +24h)
Thời gian có mặt = min(giờ ra thực, giờ ra ca) − max(giờ vào thực đã bù dung sai, giờ vào ca)
Công ngày = min(1.0, làm tròn 2 số lẻ của Thời gian có mặt / Khung ca)
```

- Vào trễ trong phạm vi **dung sai** của ca (mặc định 5 phút) → coi như đúng giờ, không trừ công.
- Vào trễ vượt dung sai → tính đúng theo số phút thật (không có mức phạt "được ăn cả ngã về không").
- **Không bấm Ra ca chính** (dù có bấm Vào) → công ngày đó = **0**, đánh dấu "chưa hoàn tất" để người soát dễ nhìn ra.
- **Ca qua nửa đêm không bị cắt đôi thành hai ngày sai lệch** — hệ quy mọi mốc giờ về cùng một trục tuyến tính trước khi so sánh, nên ca 22h→06h tính đúng là một khối liền mạch.
- Chấm nhiều phiên trong ngày: **phiên đầu tiên** (VÀO sớm nhất → RA của lần Ra đầu sau khi Vào) tính là **ca chính**; các phiên sau (Vào lại → Ra) tính là **tăng ca** — xem Phần B để biết khi nào phần này ra tiền.

## A.6. "Công của tôi" — xem lại lịch làm việc cá nhân

Tab **Công của tôi**: lưới ngày trong tháng, mỗi ngày hiện giờ vào/ra và số công. Phân biệt rõ 3 loại ngày không đi làm bằng dấu khác nhau: **ngày nghỉ theo lịch** (CN/ngày nghỉ tuần), **ngày nghỉ phép đã duyệt**, **ngày lễ**. Tháng chưa có dữ liệu hiện dòng nhắc, không để trắng trơn gây hiểu nhầm là lỗi.

## A.7. Đi muộn / về sớm / nghỉ nửa buổi

Tab **Đi muộn / về sớm / nghỉ nửa buổi**. Đây là loại đơn RIÊNG, không dùng chung với Nghỉ phép — dùng cho các khoảng vắng ngắn trong ngày (không phải nghỉ cả ngày).

- Ai cũng tự xin được cho chính mình; tổ trưởng/HCNS có quyền duyệt khai hộ và **duyệt luôn** khi tạo (không qua bước chờ).
- Mỗi phiếu tối đa 1 ngày công, chỉ 1 phiếu còn hiệu lực cho mỗi ngày công.
- **Không bị chặn ngày tương lai** — có thể xin trước cho một ngày sắp tới (khác với Yêu cầu chỉnh công ở mục A.11, vốn chỉ áp dụng cho ngày ĐÃ QUA).
- Khi tạo đơn, chọn một trong hai:
  - **Không trừ vào quỹ phép** → phần thời gian vắng **không được trả lương**.
  - **Trừ vào quỹ phép năm** → thời gian vắng làm tròn LÊN nửa ngày phép (vắng ≤ nửa ca → trừ 0,5 ngày phép; vượt nửa ca → trừ 1 ngày phép), và phần vắng đó **vẫn được trả lương** như đi làm bình thường. Hết quỹ phép năm thì bị chặn ngay, báo rõ còn bao nhiêu ngày.
- Có đơn (dù chọn nhánh nào) thì phần trễ/sớm đúng bằng đơn đó được **miễn phạt đi trễ/về sớm tự động** — chỉ phần VƯỢT quá đơn mới bị tính phạt.
- Duyệt theo phạm vi: tổ trưởng chỉ duyệt được người trong tổ mình.

## A.8. Lịch làm việc & Ngày lễ

Tab **Lịch & Ngày lễ**.

- **Tuần làm việc**: tick 7 ngày trong tuần, ngày nào là ngày làm. Mặc định Thứ 2 – Thứ 7 làm, Chủ Nhật nghỉ. Phải giữ ít nhất 1 ngày làm trong tuần.
- **Ngày đặc biệt**: khai theo từng ngày cụ thể, 3 loại:
  - **Nghỉ (lễ)** — có cờ "có lương" (mặc định có) → người không đi làm vẫn hưởng lương ngày đó; người đi làm hưởng thêm theo hệ số ngày lễ (xem Phần B/C).
  - **Làm bù** — biến một ngày lẽ ra nghỉ theo lịch tuần thành ngày làm bình thường (hoán đổi nghỉ).
  - **Off1x** — xem giải thích riêng ngay dưới đây.
- **Công chuẩn/tháng tính ĐỘNG** theo đúng lịch này (đếm số ngày làm việc thật trong tháng) — không còn cố định 26 ngày như trước.

### Ngày "Off1x" là gì

Đây là loại ngày **nghỉ, nhưng ai đi làm thì chỉ nhận đúng 1× lương ngày công, KHÔNG nhân hệ số ngày lễ/ngày nghỉ tuần** (khác hẳn ngày Nghỉ lễ thường — đi làm ngày lễ thường được nhân 2×/3×). Nghỉ ở nhà thì không có lương ngày đó (không giống ngày Lễ có lương dù không đi làm).

Cơ chế: công của ngày off1x bị tách khỏi tổng công "chính" (nơi tính hệ số lễ/nghỉ tuần) và dồn riêng vào một khoản khác chỉ trả đúng 1× — không bị "trần công tháng" nuốt mất, và cũng không bị tính vào diện phạt đi trễ/về sớm tự động.

## A.9. Bảng công tháng

Tab **Bảng công tháng** — bảng tổng hợp cả công ty theo tháng, mỗi hàng 1 người: mã/tên/phòng ban/ca (hoặc "Nhiều ca" nếu dùng hơn 1 ca trong tháng), lưới 1..31 ngày, và các cột tổng: tổng ngày công, tổng nghỉ phép (có lương/không lương tách riêng), số ngày nghỉ lễ, tổng giờ, tổng công, phút tăng ca, công được miễn (thiếu công nhưng có đơn xin — vẫn giữ chuyên cần dù không cộng vào tổng công).

- Người **mới vào giữa tháng**: vẫn có dòng, công chỉ tính từ ngày vào làm.
- Người **nghỉ việc giữa tháng**: vẫn có dòng, công tính tới đúng ngày nghỉ.
- Có nút xuất CSV.

## A.10. Chốt kỳ công / Mở lại kỳ công

**Chốt kỳ công** (nút trên Bảng công tháng): chụp toàn bộ số liệu tháng thành một "ảnh đóng băng" — lương sau này đọc đúng ảnh này, không đọc số đang biến động.

**Bị chặn chốt** nếu tháng đó còn: đơn nghỉ phép, phiếu đi muộn/về sớm, hoặc yêu cầu chỉnh công **đang ở trạng thái chờ duyệt** — hệ báo rõ còn bao nhiêu đơn mỗi loại.

**Sau khi chốt**: mọi thao tác sửa chấm công/ca của tháng đó (chấm bù tay, xoá lượt chấm, gửi yêu cầu chỉnh công, sửa phân ca) đều bị khoá.

**Mở lại kỳ công**: xoá ảnh, quay về sửa được. ⚠️ **Bị chặn nếu kỳ lương (bên module Lương) của cùng tháng đã ở trạng thái "Đã chốt" HOẶC "Đã chi"** — thông báo phân biệt rõ hai trường hợp:
- Đã chi: *"Kỳ lương tháng này ĐÃ CHI — tiền đã phát, không mở lại kỳ công."*
- Đã chốt (chưa chi): *"Kỳ lương tháng này đã chốt — không mở lại kỳ công."*

Muốn sửa sai sót của một tháng đã chi lương: bên Lương bấm **Hủy đã chi** → **Mở lại** kỳ lương → lúc đó kỳ công mới mở lại được. Nếu không muốn lùi cả kỳ lương, xử bằng truy lĩnh/khấu trừ ở kỳ sau.

## A.11. Yêu cầu chỉnh công

Tab **Yêu cầu chỉnh công** — dùng khi quên chấm công cho một ngày **đã qua**.

- Nhân viên tự gửi, chọn ngày + giờ muốn khai bù + lý do: **Quên chấm** / **Máy hỏng, mất điện, sự cố** / **Được duyệt (đi công tác/họp...)** / **Khác**.
- **Chặn cứng ngày tương lai** — khác với Đi muộn/về sớm (mục A.7), mục này chỉ áp dụng cho ngày đã qua.
- Chặn nếu kỳ công tháng đó đã chốt.
- **Hạn mức 5 ngày công/tháng** cho mỗi người (khai được ở Cấu hình lương, `0` = không giới hạn) — tính theo **số ngày công khác nhau**, không theo số đơn (một ngày gửi cả phiếu Vào lẫn Ra chỉ tốn 1 lượt trong hạn mức). Đơn bị từ chối hoặc huỷ trả lại lượt.
- Quản lý (quyền chỉnh công) duyệt → hệ tự sinh một lượt chấm công tay đúng giờ đã xin, rồi **tính lại công từ dữ liệu chấm công** như bình thường — không có chuyện ghi đè thẳng số công.
- HCNS **chấm bù trực tiếp** (không qua đơn xin) cho nhân viên thì **không bị tính vào hạn mức 5 ngày/tháng** — nhưng vẫn bị chặn ngày tương lai và kỳ công đã chốt.

## A.12. Phạm vi quyền theo từng chức năng

| Chức năng | Ai làm được | Phạm vi |
|---|---|---|
| Chấm công / xem log / xem công của chính mình | Ai cũng làm được | chỉ của bản thân |
| Khai điểm chấm công, ca, Lịch & Ngày lễ | Người có quyền cấu hình Nhân sự | toàn công ty (đây là danh mục dùng chung) |
| Xem log/Bảng công/Yêu cầu chỉnh công của người khác | Người có quyền xem Nhân sự | theo phạm vi được cấp: chỉ mình / cả tổ / toàn công ty |
| Chấm bù tay, duyệt/từ chối Yêu cầu chỉnh công | Người có quyền chỉnh công | theo phạm vi |
| Chốt/Mở lại kỳ công | Người có quyền chỉnh công | toàn công ty theo tháng, không tách theo người |
| Lưới Phân ca tháng | Người có quyền xem/sửa Nhân sự | tổ trưởng chỉ xem/sửa được tổ mình |
| Duyệt Đi muộn/về sớm | Quyền duyệt riêng của module này | tách biệt hoàn toàn với quyền Nhân sự chung |

Mọi danh sách/tìm kiếm đều tự lọc theo phạm vi — tìm ngoài phạm vi sẽ ra **rỗng**, không bao giờ trả về dữ liệu ngoài quyền.

---

# PHẦN B — TĂNG CA

Menu: **Nhân sự & Lương → Tăng ca** — 2 tab: **Của tôi** và **Duyệt**.

## B.1. Đăng ký tăng ca

Tab **Của tôi**: chọn ngày công, giờ bắt đầu – giờ kết thúc dự kiến, lý do (không bắt buộc). Tối đa 1 phiếu tăng ca còn hiệu lực cho mỗi ngày công, một phiếu không quá 12 giờ.

Hệ thống **không bắt buộc phải đăng ký trước khi làm** — có thể gửi phiếu trước hoặc sau khi đã tăng ca thật, miễn phiếu được duyệt trước khi bảng công/lương của kỳ đó được chốt thì phần giờ đó vẫn ra tiền đúng (xem B.3). Tuy vậy nên đăng ký sớm để tổ trưởng chủ động sắp xếp.

Sửa phiếu chỉ được khi còn **Chờ duyệt**, và chỉ chính người tạo mới sửa được (kể cả tổ trưởng cũng không sửa hộ phiếu người khác).

## B.2. Duyệt tăng ca

Tab **Duyệt**: tổ trưởng chỉ thấy và duyệt được phiếu của **người trong tổ mình**; HCNS/Admin thấy toàn công ty.

- **Duyệt cả mẻ**: tick nhiều phiếu rồi duyệt/từ chối một lần. Phiếu nào ngoài phạm vi của người duyệt hoặc không còn ở trạng thái chờ sẽ tự **bỏ qua**, không báo lỗi làm gián đoạn cả mẻ.
- **Từ chối bắt buộc ghi lý do**.
- Tổ trưởng/HCNS cũng tạo được phiếu **thay** cho nhân viên (khai hộ) — phiếu tạo kiểu này **tự động ở trạng thái Đã duyệt luôn**, không qua bước chờ.

## B.3. Cách hệ tính giờ tăng ca ra tiền

Không dùng một mốc giờ cố định nào (VD "sau 17h30") — hệ lấy đúng phần **giao nhau** giữa:

1. Khoảng thời gian nhân viên **thực sự chấm công thêm** sau khi đã Ra ca chính (phải có đủ 1 cặp Vào–Ra riêng cho phần này, thiếu 1 trong 2 lượt thì phần đó tính = 0), và
2. Khung giờ ghi trên **phiếu tăng ca đã ở trạng thái Đã duyệt**.

Nói cách khác: **phiếu là giấy phép + mức trần**. Chấm công ít hơn phiếu → tính theo thực tế đi làm. Chấm công nhiều hơn phiếu cho phép → chỉ tính tới đúng mức trần ghi trong phiếu, phần vượt không được trả. Không có phiếu (hoặc phiếu chưa duyệt/bị từ chối) → phần đó = 0 giờ tăng ca, dù có bấm chấm công thật.

> Công của **ca chính** hoàn toàn độc lập, không bị ảnh hưởng bởi việc có hay không có phiếu tăng ca.

## B.4. Hệ số tăng ca theo loại ngày — khai được ở Cấu hình lương

| Loại | Hệ số mặc định | Ghi chú |
|---|---|---|
| Tăng ca ngày thường | 150% | |
| Tăng ca ngày nghỉ tuần | 200% | |
| Tăng ca ngày lễ | 300% | |
| Làm nguyên công (cả ngày) vào ngày nghỉ tuần | 200% | khác tăng ca — đây là đi làm nguyên 1 công vào đúng ngày lẽ ra được nghỉ |
| Làm nguyên công vào ngày lễ | 300% | |

Cả 5 số này sửa được ở **Cấu hình lương → tab Cơ chế lương theo bộ phận → khối "Hệ số làm thêm & ngày đặc biệt"**.

## B.5. 🔴 "Bậc thang tăng ca theo giờ ra" — CHƯA CÓ trên hệ thống thật

Có tài liệu thiết kế nội bộ mô tả một cơ chế phức tạp hơn: làm tới 21h–23h59 được +25.000đ, làm tới 00h–1h sáng được +75.000đ kèm nghỉ bù nửa buổi sáng hôm sau, làm tới 6h–8h sáng được +125.000đ kèm nghỉ bù nguyên ngày. **Cơ chế này CHƯA được lập trình** — hệ thống hiện tại chỉ tính tăng ca theo hệ số % của mục B.4 (thường/nghỉ tuần/lễ), không có bảng mốc giờ rời rạc nào ở trên. Đừng tìm nút hay số tiền này trên màn thật, và đừng dùng làm căn cứ đối chiếu khi test.

## B.6. Tăng ca qua nửa đêm

Được xử lý đúng — giờ tăng ca vắt qua 00:00 không bị cắt đôi hay tính sai ngày, kể cả phần rơi vào khung giờ đêm (22h–06h, xem B.9) cũng được cộng đủ dù nằm ở "ngày hôm sau" theo đồng hồ.

## B.7. Trần tăng ca

- **1 phiếu tối đa 12 giờ** (đối chiếu tổng giờ làm + tăng ca trong ngày theo luật lao động).
- **Tối đa 1 phiếu còn hiệu lực cho mỗi ngày công**/người.
- 🔴 **Chưa có giới hạn tổng số giờ tăng ca theo tháng hoặc theo năm.** Luật lao động quy định trần 40 giờ/tháng và 200 giờ/năm (300 giờ/năm với một số ngành), nhưng hệ thống hiện tại **không cộng dồn và không cảnh báo/chặn** theo hai mốc này. Nếu doanh nghiệp cần kiểm soát mức này, hiện phải theo dõi thủ công.

## B.8. 🔴 Nghỉ bù sau tăng ca khuya — CHƯA CÓ

Không có cơ chế tự động sinh ngày/buổi nghỉ bù sau khi tăng ca tới khuya. Muốn cho nghỉ bù, hiện phải xử lý thủ công qua module Nghỉ phép như một trường hợp bình thường.

## B.9. Tiền tăng ca vào lương thế nào

```
đơn giá ngày   = (lương vị trí + lương trách nhiệm) × tỷ lệ thử việc (nếu có) / công chuẩn tháng
đơn giá giờ    = đơn giá ngày / giờ công chuẩn mỗi ngày (mặc định 8)

Tiền tăng ca = đơn giá giờ × (giờ TC ngày thường × 150% + giờ TC ngày nghỉ tuần × 200% + giờ TC ngày lễ × 300%)
             + đơn giá ngày × [(số công làm nguyên ngày lễ) × (300% − 1) + (số công làm nguyên ngày nghỉ tuần) × (200% − 1)]

Phụ cấp ca đêm = đơn giá giờ × số giờ rơi khung 22h–06h × 30%
               (+ thêm 20% nữa cho phần giờ ĐÊM mà cũng là TĂNG CA, tức hai phụ cấp cộng dồn đúng phần chồng lấn)
```

Đơn giá ngày/giờ tính trên **lương vị trí + lương trách nhiệm** — **không gồm** chuyên cần, phụ cấp thâm niên/khác, tiền cơm/phụ cấp ca. Các khoản đó cộng riêng vào lương, không ảnh hưởng đơn giá giờ làm căn cứ tính tăng ca.

**Tổ đang bật "Làm khoán"**: tăng ca theo giờ = 0 (khoán thay thế tăng ca) — xem thêm mục C.14.

## B.10. Miễn thuế TNCN

Toàn bộ **tiền tăng ca + phụ cấp ca đêm** được **miễn thuế TNCN 100%** — không chỉ phần trả thêm so với ngày thường mà miễn cả khoản gốc, theo chốt riêng của doanh nghiệp (rộng hơn cách hiểu thông thường của luật thuế, là quyết định có chủ đích chứ không phải thiếu sót). Cơ chế này nằm cứng trong công thức tính thuế, tách biệt với "Danh mục khoản thu nhập" (mục C.3) — hai đường miễn thuế không chồng lấn nhau.

## B.11. Lưu ý khi test — huỷ phiếu tăng ca của người khác

Khi rà soát, phát hiện hàm **Huỷ phiếu tăng ca** hiện chỉ kiểm tra "người bấm có quyền duyệt hay không", **chưa kiểm tra phạm vi (scope)** giống hệt như nút Duyệt/Từ chối đã được vá. Về lý thuyết một tổ trưởng có quyền duyệt tăng ca có thể huỷ được phiếu của tổ khác nếu biết đúng mã phiếu, dù màn hình bình thường không hiện phiếu đó cho họ. Đây là điểm **cần kiểm tra kỹ khi test bảo mật/phân quyền**, chưa xác nhận có khai thác được qua giao diện thật hay không.

---

# PHẦN C — LƯƠNG

Menu: **Nhân sự & Lương → Lương** — các tab: **Bảng lương tháng** · **Lương nhân viên** · **Tạm ứng** · **Cấu hình lương** · **Phiếu lương của tôi** (self-service).

## C.1. Cấu hình lương — 3 sub-tab, nơi mọi con số luật nằm

### Sub-tab 1 — "Cơ chế lương theo bộ phận"

**Khối "Áp dụng toàn công ty"** (luật chung, không tách theo tổ):

| Tham số | Mặc định |
|---|---|
| Giờ công chuẩn/ngày | 8 giờ |
| % lương thử việc | 80% |
| Hạn mức chỉnh công/tháng | 5 ngày (0 = không giới hạn) |
| Công tối thiểu để hưởng phụ cấp cơm/phụ cấp ca của một ca | 0,5 công |

**Khối "Hệ số làm thêm & ngày đặc biệt"**: 5 hệ số tăng ca/làm nguyên công (xem B.4) + phụ cấp ca đêm 30% + phụ cấp tăng ca đêm 20%.

**Khối "Cơ chế lương theo TỪNG bộ phận"** (chọn tổ, 3 công tắc):
- **Chuyên cần** — bật/tắt; số tiền vẫn khai riêng cho từng người ở hồ sơ lương.
- **Lương khoán/sản lượng** — bật thì tổ chuyển sang trả theo sản lượng; xem cảnh báo ở mục C.14.
- **Tăng ca** — bật/tắt; **loại trừ với Khoán**, bật cái này tự tắt cái kia và ngược lại.

### Sub-tab 2 — "Danh mục khoản thu nhập"

Đây là nơi quản lý mọi khoản phụ cấp/khấu trừ ngoài lương cơ bản (trang phục, tiền nhà, đi lại, thưởng…), mỗi khoản có cờ **Chịu thuế / Miễn thuế**. Chi tiết đầy đủ:

- Mỗi khoản: Tên, Loại (**Thu** — cộng vào lương / **Trừ** — khấu trừ), cờ **Chịu thuế**, thứ tự hiển thị, số nhân viên đang dùng.
- **Thêm khoản mới**: gõ tên, chọn loại, tick hay không tick chịu thuế — hiện ngay ở hồ sơ lương và phiếu lương.
- **Xoá**: khoản **chưa từng dùng ở kỳ lương nào** thì xoá hẳn được. Khoản **đã dùng** chỉ chuyển được sang **Ngưng dùng** (biến mất khỏi form nhập mới, phiếu lương kỳ cũ vẫn giữ nguyên số).
- **Đổi cờ Chịu thuế/Miễn thuế** chỉ ảnh hưởng kỳ lương **tính từ đó về sau**, kỳ đã chốt giữ nguyên.
- **Gán cho từng người**: mở ở màn Lương nhân viên (mục C.4), không gán được ở đây.
- **Gán hàng loạt cho nhiều người** (nút "Gán cho nhân viên" trên mỗi khoản):
  1. Chọn **"Tất cả nhân viên đang làm việc"** (chính thức + thử việc, tự loại người đã nghỉ) hoặc **"Chọn cụ thể"**.
  2. Ở chế độ chọn cụ thể: lọc theo tên/mã hoặc theo phòng ban/tổ, có nút **"Chọn tất cả đang hiện"** để chọn nguyên cả tổ trong 2 cú bấm.
  3. Ô **"Ghi đè mức riêng đã có"** mặc định **TẮT** — người đã có mức riêng của khoản này bị khoá không cho tick lại (an toàn, tránh sửa nhầm). Bật ô này lên mới cho sửa đè, kèm cảnh báo đỏ "không hoàn tác được" và bảng xem trước "X → Y".
  4. Lưu xong báo tách rõ 3 số: đã thêm mới bao nhiêu người · ghi đè bao nhiêu người · bỏ qua bao nhiêu người (đã có mức riêng, không ghi đè).
  5. Tổ trưởng chỉ gán được cho người trong tổ mình.

### Sub-tab 3 — "Bảo hiểm & Thuế"

| Tham số | Mặc định |
|---|---|
| BHXH — người lao động đóng / công ty đóng | 8% / 17,5% |
| BHYT — người lao động / công ty | 1,5% / 3% |
| BHTN — người lao động / công ty | 1% / 1% |
| Trần đóng BHXH+BHYT | 50.600.000đ (0 = tắt trần) |
| Trần đóng BHTN | 106.200.000đ (0 = tắt trần) |
| Đoàn phí công đoàn (chỉ người có tick "Đoàn viên") | 0% |
| TNLĐ-BNN (chỉ áp khi NV có BH đóng nơi khác, công ty chịu, không trừ lương) | 0,5% |
| Không đóng BHXH nếu nghỉ không lương từ … ngày trong tháng | 14 ngày (0 = tắt luật) |
| Trần khấu trừ kỷ luật (Điều 102 BLLĐ) | 30% (0 = tắt trần) |
| Giảm trừ bản thân (tính thuế TNCN) | 15.500.000đ |
| Giảm trừ mỗi người phụ thuộc | 6.200.000đ |
| Biểu thuế TNCN luỹ tiến | 5 bậc — xem C.8 |
| Bảng phạt đi trễ/về sớm (tự động, theo phút) | 4 bậc — xem C.8 |
| Khấu trừ 10% tại nguồn (HĐ dưới 3 tháng/thời vụ) — tỷ lệ / ngưỡng áp dụng | 10% / từ 2.000.000đ mỗi lần trả |

> 🔴 **Không có UI đổi "cách tính thuế TNCN" (`pit_mode`) cho từng người** — dù backend có hỗ trợ 3 kiểu (luỹ tiến thường / khấu trừ 10% / miễn theo cam kết 08, xem C.8), khối chọn kiểu này đã bị ẩn khỏi cả màn Hồ sơ nhân sự lẫn màn Lương nhân viên. Muốn đổi kiểu tính thuế cho một người hiện chỉ làm được qua API trực tiếp — báo Admin nếu cần.

## C.2. Tiền cơm & Phụ cấp ca — tự tính theo ca thực làm

Đã có ở tài liệu hướng dẫn chung (mục 2.8 của HUONG_DAN_SU_DUNG_NHAN_SU_THU_MUA_KE_TOAN.md), nhắc lại công thức chính xác:

```
Với mỗi CA một người có làm trong tháng:
  nếu số ngày công của ca đó ≥ ngưỡng tối thiểu (mặc định 0,5 công, sửa ở C.1):
      cộng TRỌN VẸN mức Phụ cấp cơm của ca đó × số ngày đạt ngưỡng
      cộng TRỌN VẸN mức Phụ cấp ca của ca đó   × số ngày đạt ngưỡng
```

Không chia tỷ lệ theo công thực tế — đạt ngưỡng là được nguyên suất, không đạt là 0 của ngày đó. Cả hai khoản miễn thuế TNCN toàn bộ.

## C.3. Chuyên cần

Khai riêng theo từng người (mức cố định/tháng) ở màn Lương nhân viên. Tổ chỉ còn công tắc bật/tắt loại chuyên cần (C.1), không khai mức chung.

```
Tỷ lệ hưởng = max(0, 1 − 0,5 × số ngày nghỉ trong tháng)
```
Nghỉ 0,5 ngày → còn 75%; nghỉ 1 ngày → còn 50%; nghỉ ≥ 2 ngày → mất hết.

## C.4. Lương nhân viên — Thiết lập lương (điều chỉnh & giữ lịch sử)

Tìm nhân viên → **Thiết lập lương** → nhập **Hiệu lực từ** → sửa các ô → **Lưu điều chỉnh**. Mỗi lần lưu với ngày hiệu lực mới tạo một **mốc mới**, giữ nguyên lịch sử — xem đúng số của từng kỳ theo đúng ngày hiệu lực áp dụng cho kỳ đó.

Các ô trong màn Sửa lương:
- Lương vị trí (bắt buộc >0, cũng là mức đóng BHXH), Lương trách nhiệm.
- Chuyên cần, Phụ cấp thâm niên, Phụ cấp khác (cộng phẳng, không chia theo công).
- **Lương trả 1 lần** (dùng cho "Lương đợt 1" — xem C.6).
- **"+ Thêm khoản thu nhập"** — gán/gỡ từng khoản trong Danh mục khoản thu nhập (C.1) cho riêng người này, mỗi dòng hiện badge Chịu thuế/Miễn thuế.
- Ô **"Phụ cấp ca (đã ngưng)"** — chỉ để đọc, không còn ra tiền từ 03/08/2026 (xem C.2 để sửa đúng chỗ).

## C.5. Bảng lương tháng — vòng đời đầy đủ

Trạng thái đi qua **Nháp → Đã chốt → Đã chi**, mỗi trạng thái có đúng bộ nút riêng:

| Trạng thái | Nút | Ý nghĩa |
|---|---|---|
| Chưa có kỳ | **Khởi tạo bảng lương** | máy tự kéo công + mức lương + tạm ứng, điền hết |
| Nháp | **↻ Tính lại** · **🔒 Chốt** | còn sửa được từng dòng |
| Đã chốt | **Mở lại** · **💵 Đã chi** | số đã khoá, chưa phát tiền |
| Đã chi | **↩ Hủy đã chi** | tiền đã phát, quay về Đã chốt nếu cần sửa |
| Bất kỳ (đã có kỳ) | **⬇ Xuất Excel** | tải bảng lương |
| Đã chốt / Đã chi | **⬇ File chuyển khoản** | chỉ xuất khi số đã khoá |

> **"Tính lại" KHÔNG xoá số đã sửa tay** — chỉ tính lại phần tự động (công, mức nền, BHXH, tạm ứng, khoản gán theo hồ sơ). Các ô đã sửa thủ công ở một dòng cụ thể (vi phạm, thưởng, ghi chú, khoản phát sinh riêng của kỳ, thuế đã tự nhập tay, phạt đi trễ đã sửa tay) đều **giữ nguyên** qua các lần Tính lại.

**Xuất Excel** (`export.xlsx`): 21 cột đầy đủ — Mã, Họ tên, Phòng/Tổ, Loại, Công, Lương công, Chuyên cần, Phụ cấp, Khoán, Tăng ca, Ca đêm, Ca đêm (giờ×hệ số), Cơm ca, Phụ cấp ca, Vi phạm, Thưởng, Tổng, BHXH, TNCN, Tạm ứng, Thực lĩnh.

**File chuyển khoản** (`bank.xlsx`): 6 cột — Mã, Họ tên, Số tài khoản, Ngân hàng, Số tiền, Nội dung (tự sinh "Luong T{tháng}/{năm} - {mã NV}"). **Tự động bỏ qua người có Thực lĩnh ≤ 0** (thường do tạm ứng vượt lương tháng đó).

### Sửa một dòng lương (nút "Sửa lương" trên từng người trong Bảng lương tháng)

- Sửa tay các khoản: đi trễ/nghỉ không phép, điện thoại vượt trội, phạt biên bản, phạt đồng phục/5S, giảm trừ khác.
- **Khối "Khoản phát sinh tháng này" (thưởng nóng)**: chọn khoản từ danh mục + nhập số tiền + ghi chú, **lưu ngay lập tức** (không cần bấm nút Lưu chung của dòng). Khoản này gắn riêng với đúng kỳ lương đang sửa, **không lặp sang kỳ sau** — muốn khoản nào lặp hằng tháng thì gán ở hồ sơ lương (C.4), không khai ở đây.
- 🔴 **"Điều chỉnh lương ±"**: có ở tầng dữ liệu và được engine cộng vào tổng lương, nhưng **hiện KHÔNG có ô nhập nào trên form Sửa lương**. Chỉ hiện ra ở phần render phiếu lương nếu số đó đã tồn tại từ trước (do gọi thẳng API hoặc dữ liệu cũ). Muốn dùng khoản này hiện phải nhờ Admin nhập qua API.

## C.6. Tạm ứng và Lương đợt 1

Tab **Tạm ứng** — hai loại phiếu **tách riêng nhau hoàn toàn**, dù cùng cơ chế trừ vào lương cuối kỳ:

| | Tạm ứng thường | Lương đợt 1 |
|---|---|---|
| Ai tạo | Nhân viên tự xin, hoặc HCNS tạo hộ | HCNS tạo (nút "+ Phiếu lương đợt 1") |
| Số tiền | Gõ tay | Tự điền theo mức "Lương trả 1 lần" đã khai sẵn ở hồ sơ (C.4), sửa được |
| Hiện trên phiếu lương | dòng "Tạm ứng đã nhận" | dòng "Thanh toán lương đợt 1" |

- **Duyệt**: quyền Nhân sự (mặc định chỉ HCNS/Admin có).
- **"Sàn 0"**: Thực lĩnh cuối kỳ (đợt 2) **không bao giờ âm** — dù tổng tạm ứng + lương đợt 1 đã trả giữa tháng vượt quá lương thực tính, hệ vẫn chặn ở 0, không đòi ngược lại nhân viên.
- 🔴 Trần % tạm ứng theo lương từng tháng **đã bị gỡ bỏ** (không còn giới hạn tạm ứng tối đa theo %) — chỉ còn chặn "sàn 0" ở trên.

## C.7. Thuế TNCN — chi tiết đầy đủ

**Biểu thuế luỹ tiến 5 bậc (mặc định, sửa được ở Cấu hình lương):**

| Bậc | Thu nhập tính thuế/tháng | Thuế suất |
|---|---|---|
| 1 | đến 10.000.000đ | 5% |
| 2 | đến 30.000.000đ | 10% |
| 3 | đến 60.000.000đ | 20% |
| 4 | đến 100.000.000đ | 30% |
| 5 | trên 100.000.000đ | 35% |

**Giảm trừ**: bản thân 15.500.000đ + 6.200.000đ/người phụ thuộc. Số người phụ thuộc khai ở **Hồ sơ nhân sự**, không khai ở màn Lương.

**Công thức:**
```
Thu nhập chịu thuế = Tổng thu nhập − tiền tăng ca/ca đêm (miễn 100%, xem B.10)
                                    − các khoản Danh mục có cờ "Miễn thuế" (C.1)
                                    − Phụ cấp cơm/Phụ cấp ca (miễn 100%, xem C.2)
Thu nhập tính thuế = max(0, Thu nhập chịu thuế − BHXH đã đóng − Giảm trừ bản thân − Giảm trừ người phụ thuộc)
Thuế TNCN = tính luỹ tiến từng phần qua 5 bậc trên
```

**Ba cách tính khác nhau theo loại hợp đồng** (chọn ở hồ sơ từng người — nhưng hiện KHÔNG sửa được qua UI, xem cảnh báo ở C.1):
- **Luỹ tiến từng phần** (mặc định) — công thức trên.
- **Khấu trừ 10% tại nguồn** — dùng cho hợp đồng dưới 3 tháng/thời vụ, chỉ áp khi thu nhập từ 2.000.000đ/lần trả trở lên, khấu trừ thẳng 10% trên thu nhập chịu thuế, **không** qua bảng luỹ tiến, **không** giảm trừ gia cảnh.
- **Cam kết 08** — người lao động đã cam kết cả năm chưa tới ngưỡng chịu thuế → thuế = 0.

🔴 Nhắc lại: 3 kiểu tính thuế này chọn được ở tầng dữ liệu, nhưng **màn hình chọn hiện bị ẩn** — mọi người đang mặc định chạy theo kiểu luỹ tiến trừ khi có ai chỉnh DB tay.

## C.8. BHXH/BHYT/BHTN — chi tiết đầy đủ

- Tỷ lệ NLĐ đóng (trừ vào lương): BHXH 8% + BHYT 1,5% + BHTN 1% = **10,5%**, tính trên **Lương vị trí** (mức đóng bảo hiểm) — không cộng thêm lương trách nhiệm/phụ cấp.
- Tỷ lệ NSDLĐ đóng (công ty chịu, KHÔNG trừ lương NV, chỉ để tham khảo chi phí): BHXH 17,5% + BHYT 3% + BHTN 1% = **21,5%**.
- Hai mức trần riêng: BHXH+BHYT trần **50.600.000đ**, BHTN trần **106.200.000đ** (đặt `0` = tắt trần).
- **Nhân viên thử việc không đóng bất kỳ khoản bảo hiểm nào** (kể cả công đoàn).
- **Nghỉ không lương từ 14 ngày làm việc trở lên trong tháng** (theo QĐ 595/QĐ-BHXH Điều 42.4) → tháng đó **không đóng BHXH** — số ngày này sửa được ở Cấu hình lương, `0` = tắt hẳn luật này.
- **Công đoàn phí**: mặc định 0%, chỉ trừ người có tick "Đoàn viên công đoàn" ở hồ sơ.
- **TNLĐ-BNN 0,5%**: chỉ áp cho người có bảo hiểm đóng nơi khác — công ty tự chịu khoản này, không trừ lương, không hiện trên bảng lương tháng (chỉ tham khảo ở Cấu hình lương).

## C.9. Trần khấu trừ kỷ luật (Điều 102 Bộ luật Lao động)

Mặc định **30%**, `0` = tắt trần hoàn toàn.

```
base = Tổng thu nhập trước thuế − BHXH − Thuế TNCN
room = max(0, 30% × base − tiền trừ lỗi hàng khoán)
Số tiền phạt thực trừ = min(Tổng các khoản phạt, room)
```

Trần này **gộp chung** các khoản: giảm trừ khác (vi phạm), phạt đi trễ/về sớm tự động (bảng 4 bậc dưới đây), phạt điện thoại vượt trội, phạt biên bản, phạt đồng phục/5S, trừ lỗi hàng khoán.

**Không nằm trong trần này** (trừ thẳng vào thực lĩnh, không giới hạn): các khoản **loại "Trừ"** trong Danh mục khoản thu nhập (VD: mua đồng phục, ứng tiền cá nhân) — đây là khoản thoả thuận, khác bản chất với khoản kỷ luật.

**Bảng phạt đi trễ/về sớm tự động** (mặc định, theo số phút vượt dung sai của ca):

| Số phút | Mức phạt/lần |
|---|---|
| đến 15 phút | 20.000đ |
| đến 30 phút | 40.000đ |
| đến 60 phút | 100.000đ |
| trên 60 phút | 150.000đ |

## C.10. Phiếu lương chi tiết — bố cục đầy đủ

Xem ở tab **Phiếu lương của tôi** (nhân viên tự xem) hoặc nút **In phiếu** trên Bảng lương tháng (HCNS/Kế toán xem của bất kỳ ai trong phạm vi). Bố cục 2 cột:

**Các khoản THU**: Lương theo công (kèm dòng phụ "trong đó: lương ngày phép" nếu có) · Cơm ca · Phụ cấp ca (theo ca làm) · Phụ cấp ca đêm (giờ × hệ số) · Phụ cấp thâm niên · Phụ cấp khác · Chuyên cần · Lương khoán · Tăng ca · từng khoản trong Danh mục (cả khoản gán theo hồ sơ lẫn khoản phát sinh riêng kỳ này) · Điều chỉnh lương (nếu khác 0) → **TỔNG THU**.

**Các khoản TRỪ**: BHXH/BHYT/BHTN (3 dòng riêng, kèm % trong nhãn) · Công đoàn · Thuế TNCN · Đi trễ/nghỉ không phép · Điện thoại vượt trội · Phạt biên bản · Đồng phục/phạt 5S · Giảm trừ khác · khoản Danh mục loại Trừ · Thanh toán lương đợt 1 · Tạm ứng đã nhận → **TỔNG TRỪ**.

Cuối phiếu: **THỰC NHẬN**.

> 🔴 Hai dòng **"Thu nhập tính thuế TNCN"** và **"Thu nhập miễn thuế"** (đúng như định hướng gộp minh bạch thuế) đã được lập trình xong ở cả backend lẫn giao diện, nhưng khối hiển thị này **đang bị ẩn tạm thời trên phiếu lương thật** — không thấy hai dòng này khi in/xem phiếu hôm nay dù dữ liệu đã có sẵn trong hệ thống.

## C.11. Tiền khoán theo sản lượng

🔴 **Luôn = 0đ** trên mọi phiếu lương, kể cả tổ đã bật "Lương khoán/sản lượng" và đã khai đầy đủ đơn giá khoán ở Cấu hình lương. Lý do: hệ thống chưa có nguồn dữ liệu sản lượng thật để tính ra tiền (đang chờ nối với Lệnh sản xuất). Tổ đã bật khoán còn bị **tự động tắt tăng ca** (vì hai khoản loại trừ nhau — B.9/C.1), nên người trong tổ đó **hiện chỉ còn lương công + chuyên cần + phụ cấp**, mất cả phần tăng ca lẫn khoán. Trước khi chạy lương thật cho một tổ có bật khoán, cân nhắc kỹ có nên tạm tắt khoán để họ được tính tăng ca hay không.

## C.12. Phạm vi quyền trong module Lương

| Chức năng | Ai làm được |
|---|---|
| Xem Phiếu lương của tôi / Tạm ứng của tôi | Ai đăng nhập cũng thấy, chỉ dữ liệu của chính mình |
| Xem Bảng lương tháng, Cấu hình lương | Cần quyền xem module Lương (`luong:view_salary` trở lên) |
| Sửa lương, tính/chốt/chi bảng lương, cấu hình | Cần quyền sửa module Lương (`luong:update`) |
| Duyệt Tạm ứng / Lương đợt 1 | Quyền Nhân sự (mặc định HCNS/Admin) |

---

### Đầu mối hỗ trợ

Quản trị viên hệ thống của doanh nghiệp. Khi báo lỗi, ghi rõ: mục nào trong tài liệu này, tháng/kỳ đang thao tác, mã nhân viên, ảnh màn hình.
